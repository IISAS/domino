import enum


class RepositorySource(str, enum.Enum):
    github = 'github'
    default = 'default'

    @enum.member
    class Config:
        use_enum_values = True


class Permission(str, enum.Enum):
    owner = 'owner'
    admin = 'admin'
    write = 'write'
    read = 'read'

    @enum.member
    class Config:
        use_enum_values = True


class MembersPermissions(str, enum.Enum):
    admin = 'admin'
    write = 'write'
    read = 'read'

class UserWorkspaceStatus(str, enum.Enum):
    pending = 'pending'
    accepted = 'accepted'
    rejected = 'rejected'

    @enum.member
    class Config:
        use_enum_values = True


class WorkflowScheduleInterval(str, enum.Enum):
    none = 'none'
    once = 'once'
    hourly = 'hourly'
    daily = 'daily'
    weekly = 'weekly'
    monthly = 'monthly'
    yearly = 'yearly'

    @enum.member
    class Config:
        use_enum_values = True