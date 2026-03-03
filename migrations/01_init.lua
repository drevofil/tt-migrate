local helpers = require('tt-migrations.helpers')

local function apply()
    box.schema.space.create('bands', {
        if_not_exists = true,
        format = {
            { name = 'id', type = 'integer' },
            { name = 'bucket_id', type = 'unsigned' },
            { name = 'band_name', type = 'string' },
            { name = 'year', type = 'integer' }
        },
    })
    box.space.bands:create_index('primary_key', { parts = {'id'}, if_not_exists = true})
    box.space.bands:create_index('bucket_id', { parts = {'bucket_id'}, unique = false, if_not_exists = true})
    helpers.register_sharding_key('bands', {'id'})

    return true
end

return {
    apply = {
        scenario = apply,
    }
}
