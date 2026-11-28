# Schema tham số cấp phát, cập nhật instance và tạo binding

Trong Open Service Broker API (OSB API), platform gửi cấu hình riêng của dịch vụ qua field `parameters` trong JSON body của các request provision, update và binding. Vì mỗi service plan có thể nhận một tập tham số khác nhau, broker cần công bố cấu trúc và quy tắc của các tham số đó trong catalog để platform có thể tạo biểu mẫu, hướng dẫn người dùng và kiểm tra dữ liệu trước khi gửi request.

OSB sử dụng JSON Schema để mô tả các tham số đầu vào. Schema giúp platform và broker hiểu cùng một contract: tên field, kiểu dữ liệu, field bắt buộc, giá trị hợp lệ và giới hạn. Broker vẫn phải kiểm tra dữ liệu ở phía server trước khi thay đổi tài nguyên, bởi dữ liệu đến từ client không bao giờ được xem là đáng tin chỉ vì platform đã hiển thị một biểu mẫu dựa trên schema.

## 1. `parameters` là gì?

`parameters` là một JSON object chứa cấu hình riêng của service instance hoặc service binding. Đây là phần dữ liệu do service broker định nghĩa theo từng dịch vụ và plan, không phải một tập field cố định được OSB quy định cho mọi broker.

Ví dụ, một PostgreSQL service có thể nhận các tham số khi provision:

```json
{
  "service_id": "postgresql",
  "plan_id": "standard",
  "parameters": {
    "storage_gb": 100,
    "region": "ap-southeast-1",
    "high_availability": true
  }
}
```

Trong ví dụ này:

- `service_id` và `plan_id` là field giao thức OSB để xác định offering và plan.
- `parameters` là object cấu hình nghiệp vụ do broker định nghĩa.
- `storage_gb`, `region` và `high_availability` là các field riêng của dịch vụ PostgreSQL giả định.

Không đưa các field giao thức như `service_id`, `plan_id`, `context` hoặc `bind_resource` vào schema `parameters`. Chúng có vị trí và ý nghĩa riêng trong request OSB.

## 2. Schema được công bố ở đâu trong catalog?

OSB đặt `schemas` bên trong từng **Service Plan**, bởi các plan khác nhau có thể chấp nhận tập tham số khác nhau. Cấu trúc tổng quát như sau:

```text
Service Offering
└── plans[]
    └── schemas
        ├── service_instance
        │   ├── create
        │   │   └── parameters: JSON Schema
        │   └── update
        │       └── parameters: JSON Schema
        └── service_binding
            └── create
                └── parameters: JSON Schema
```

| Nhánh schema | Áp dụng cho request | Mục đích |
|---|---|---|
| `schemas.service_instance.create.parameters` | `PUT /v2/service_instances/{instance_id}` | Mô tả cấu hình khi provision instance |
| `schemas.service_instance.update.parameters` | `PATCH /v2/service_instances/{instance_id}` | Mô tả cấu hình khi cập nhật instance |
| `schemas.service_binding.create.parameters` | `PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Mô tả tùy chọn khi tạo binding |

Các nhánh schema là tùy chọn. Broker có thể chỉ công bố schema create nếu không hỗ trợ update, hoặc chỉ công bố schema binding khi plan cho phép bind. Không có schema không có nghĩa là `parameters` bị cấm; nó có nghĩa catalog không cung cấp mô tả JSON Schema cho nhánh đó.

Schema thuộc về plan, không phải schema chung cho toàn bộ service definition. Ví dụ, plan `standard` có thể giới hạn dung lượng 10–200 GB, trong khi plan `enterprise` cho phép 100–5000 GB và thêm cấu hình high availability.

## 3. JSON Schema trong OSB

Trong mỗi nhánh, object `parameters` chứa một JSON Schema mô tả chính object tham số mà platform sẽ gửi. OSB yêu cầu:

- Nếu catalog có khai báo schema cho parameters, platform **MUST** hỗ trợ tối thiểu JSON Schema Draft 4.
- Platform **SHOULD** sẵn sàng hỗ trợ các phiên bản JSON Schema mới hơn.
- Khóa `$schema` **MUST** xuất hiện để xác định phiên bản JSON Schema.
- Schema **MUST NOT** chứa external reference (`$ref` trỏ ra ngoài schema).
- Schema không được lớn hơn 64 KB.

Ví dụ phần đầu của schema Draft 4:

```json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 10,
      "maximum": 500
    }
  },
  "required": ["storage_gb"],
  "additionalProperties": false
}
```

Schema trên quy định `parameters` phải là object, có field `storage_gb` kiểu integer trong khoảng 10 đến 500, bắt buộc phải có field này và không chấp nhận field ngoài danh sách `properties`.

### 3.1. Các keyword thường dùng

| Keyword | Ý nghĩa | Ví dụ |
|---|---|---|
| `$schema` | Khai báo phiên bản JSON Schema | `http://json-schema.org/draft-04/schema#` |
| `type` | Kiểu dữ liệu của object hoặc property | `object`, `string`, `integer`, `number`, `boolean`, `array` |
| `properties` | Định nghĩa các field hợp lệ | `storage_gb`, `region` |
| `required` | Danh sách field bắt buộc | `["storage_gb", "region"]` |
| `additionalProperties` | Có chấp nhận field chưa khai báo hay không | `false` |
| `enum` | Tập giá trị được phép | `["read-only", "read-write"]` |
| `minimum`, `maximum` | Giới hạn số | `minimum: 10` |
| `minLength`, `maxLength` | Giới hạn độ dài chuỗi | `minLength: 3` |
| `pattern` | Biểu thức chính quy cho chuỗi | `^[a-z][a-z0-9-]*$` |
| `items` | Schema cho từng phần tử trong array | `items: {"type":"string"}` |
| `minItems`, `maxItems` | Giới hạn số phần tử array | `maxItems: 5` |
| `minimum`, `maximum` | Giới hạn giá trị số; `exclusiveMinimum` và `exclusiveMaximum` dùng boolean trong Draft 4 để loại trừ biên | `minimum: 1`, `exclusiveMinimum: true` |

Nên mô tả schema vừa đủ để platform tạo form dễ hiểu và kiểm tra các ràng buộc tĩnh. Những điều kiện phụ thuộc trạng thái hiện tại, quota, quyền của người dùng hoặc khả năng của provider vẫn phải được kiểm tra trong nghiệp vụ broker.

### 3.2. `required` và `additionalProperties`

`required` là mảng tên property bắt buộc. Nếu `storage_gb` nằm trong `required`, request không có field này phải bị từ chối khi broker xác thực schema.

`additionalProperties: false` ngăn người dùng gửi nhầm field hoặc field không được hỗ trợ. Tuy nhiên, nếu broker cần khả năng mở rộng hoặc tương thích ngược, có thể không đặt giá trị này hoặc thiết kế schema cho phép field mở rộng. Khi thay đổi schema theo hướng chặt hơn, cần đánh giá những request cũ mà platform hoặc người dùng vẫn đang gửi.

### 3.3. Default, format và validation động

Trong JSON Schema Draft 4, `default` là metadata gợi ý giá trị mặc định cho client; chỉ khai báo `default` không bảo đảm validator tự chèn giá trị đó vào object. Nếu broker muốn dùng giá trị mặc định, cần áp dụng rõ ràng trong logic nghiệp vụ và lưu giá trị thực tế đã chọn.

Các kiểm tra `format` như email hoặc hostname có thể được validator triển khai khác nhau. Với các điều kiện quan trọng, hãy kiểm tra thêm bằng logic ứng dụng. JSON Schema cũng không thể tự xác định một region còn quota hay một plan có thể nâng cấp từ trạng thái hiện tại hay không; các điều kiện này cần truy vấn dữ liệu runtime.

## 4. Schema cho provision instance

`service_instance.create.parameters` mô tả cấu hình gửi trong request provision. Ví dụ, một plan PostgreSQL yêu cầu vùng triển khai và dung lượng lưu trữ, đồng thời cho phép bật high availability:

```json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "title": "Storage (GB)",
      "description": "Dung lượng database cần cấp phát.",
      "minimum": 10,
      "maximum": 500
    },
    "region": {
      "type": "string",
      "title": "Region",
      "enum": ["ap-southeast-1", "ap-northeast-1", "eu-west-1"]
    },
    "high_availability": {
      "type": "boolean",
      "default": false
    }
  },
  "required": ["storage_gb", "region"],
  "additionalProperties": false
}
```

Khi platform hỗ trợ hiển thị schema, người dùng có thể thấy trường nhập dung lượng, danh sách chọn region và checkbox high availability. Broker vẫn phải kiểm tra dung lượng có phù hợp với quota của tenant, region có đang hoạt động và plan có cho phép high availability hay không.

Request tương ứng:

```http
PUT /v2/service_instances/pg-orders-01
Content-Type: application/json
X-Broker-API-Version: 2.16

{
  "service_id": "postgresql",
  "plan_id": "standard",
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-82",
    "space_guid": "space-31"
  },
  "organization_guid": "org-82",
  "space_guid": "space-31",
  "parameters": {
    "storage_gb": 100,
    "region": "ap-southeast-1",
    "high_availability": true
  }
}
```

Nếu `parameters` không có trong request, broker không có cấu hình do người dùng cung cấp qua field này và cần áp dụng chính sách mặc định của service. Nếu có object nhưng thiếu field bắt buộc theo schema, broker nên trả lỗi validation trước khi bắt đầu cấp phát tài nguyên.

## 5. Schema cho update instance

`service_instance.update.parameters` mô tả tham số được phép gửi khi cập nhật instance. Đây là schema riêng, có thể khác schema create. Một số tham số chỉ được chọn lúc tạo tài nguyên; một số tham số khác có thể thay đổi sau khi instance đã hoạt động.

Ví dụ schema update cho phép thay đổi dung lượng và bật/tắt backup:

```json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 10,
      "maximum": 1000
    },
    "backup_enabled": {
      "type": "boolean"
    }
  },
  "additionalProperties": false
}
```

Ở đây không khai báo `required`, vì người dùng có thể chỉ muốn thay đổi một trong hai tham số. Ví dụ request chỉ tăng dung lượng:

```http
PATCH /v2/service_instances/pg-orders-01?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: 2.16

{
  "service_id": "postgresql",
  "parameters": {
    "storage_gb": 200
  },
  "previous_values": {
    "plan_id": "standard"
  }
}
```

OSB quy định nếu field `parameters` hoàn toàn không xuất hiện trong request update, broker **MUST NOT** thay đổi parameters của instance do request đó. Nếu `parameters` có mặt, platform gửi các giá trị người dùng yêu cầu thay đổi; platform không nên tự gửi lại toàn bộ tham số hiện tại nếu người dùng không chọn thay đổi chúng. Vì vậy, broker cần xác định rõ semantics của từng tham số, ví dụ cập nhật một phần hay thay thế một nhóm cấu hình, và giữ hành vi nhất quán.

`previous_values` cung cấp thông tin trước khi cập nhật, thường hữu ích khi chuyển plan. Nó không phải object `parameters` mới và không thay thế schema update. Broker phải kiểm tra thay đổi có hợp lệ với trạng thái instance hiện tại, quota, plan đích và các operation đang chạy hay không.

Nếu update có thể mất thời gian, broker cần xử lý theo quy tắc asynchronous OSB: chỉ trả `202 Accepted` khi request cho phép async bằng `accepts_incomplete=true`, lưu operation và cung cấp trạng thái qua endpoint `last_operation`.

## 6. Schema cho tạo binding

`service_binding.create.parameters` mô tả tùy chọn khi tạo binding. Các tham số này thường điều chỉnh quyền hoặc cách ứng dụng sử dụng instance, không phải cấu hình cấp phát database gốc.

Ví dụ, ứng dụng được chọn quyền `read-only` hoặc `read-write` và giới hạn connection pool:

```json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "properties": {
    "access_mode": {
      "type": "string",
      "enum": ["read-only", "read-write"],
      "default": "read-only"
    },
    "connection_pool": {
      "type": "integer",
      "minimum": 1,
      "maximum": 50
    }
  },
  "required": ["access_mode"],
  "additionalProperties": false
}
```

Request binding:

```http
PUT /v2/service_instances/pg-orders-01/service_bindings/bind-orders-api
Content-Type: application/json
X-Broker-API-Version: 2.16

{
  "service_id": "postgresql",
  "plan_id": "standard",
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-82",
    "space_guid": "space-31"
  },
  "bind_resource": {
    "app_guid": "app-orders-api"
  },
  "parameters": {
    "access_mode": "read-write",
    "connection_pool": 20
  }
}
```

`bind_resource` cung cấp thông tin platform về consumer hoặc route; `parameters` chứa tùy chọn riêng do người dùng chọn cho binding. Broker phải kiểm tra cả hai nguồn dữ liệu theo chính sách bảo mật. Không nên để client tự truyền password hoặc token tùy ý nếu broker có thể tự sinh credentials và quản lý vòng đời thu hồi.

Nếu plan không bindable, platform không được gửi yêu cầu binding. Nếu plan bindable, broker xử lý schema binding create riêng với schema provision và update.

## 7. Catalog JSON đầy đủ cho một plan

Ví dụ sau đặt cả ba schema trong object `schemas` của plan `standard`:

```json
{
  "services": [
    {
      "id": "postgresql",
      "name": "PostgreSQL",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plans": [
        {
          "id": "standard",
          "name": "standard",
          "description": "PostgreSQL for standard workloads",
          "free": false,
          "schemas": {
            "service_instance": {
              "create": {
                "parameters": {
                  "$schema": "http://json-schema.org/draft-04/schema#",
                  "type": "object",
                  "properties": {
                    "storage_gb": {
                      "type": "integer",
                      "minimum": 10,
                      "maximum": 500
                    },
                    "region": {
                      "type": "string",
                      "enum": ["ap-southeast-1", "eu-west-1"]
                    }
                  },
                  "required": ["storage_gb", "region"],
                  "additionalProperties": false
                }
              },
              "update": {
                "parameters": {
                  "$schema": "http://json-schema.org/draft-04/schema#",
                  "type": "object",
                  "properties": {
                    "storage_gb": {
                      "type": "integer",
                      "minimum": 10,
                      "maximum": 1000
                    },
                    "backup_enabled": {
                      "type": "boolean"
                    }
                  },
                  "additionalProperties": false
                }
              }
            },
            "service_binding": {
              "create": {
                "parameters": {
                  "$schema": "http://json-schema.org/draft-04/schema#",
                  "type": "object",
                  "properties": {
                    "access_mode": {
                      "type": "string",
                      "enum": ["read-only", "read-write"]
                    },
                    "connection_pool": {
                      "type": "integer",
                      "minimum": 1,
                      "maximum": 50
                    }
                  },
                  "required": ["access_mode"],
                  "additionalProperties": false
                }
              }
            }
          }
        }
      ]
    }
  ]
}
```

Một platform hỗ trợ schema có thể đọc nhánh tương ứng theo operation và plan đã chọn. Không dùng schema create để validate update hoặc binding; mỗi operation có schema riêng.

## 8. Khai báo schema bằng Spring Cloud Open Service Broker

Spring Cloud Open Service Broker biểu diễn schema bằng các model trong package `org.springframework.cloud.servicebroker.model.catalog`:

| Model | Trách nhiệm |
|---|---|
| `MethodSchema` | Giữ JSON Schema cho parameters của một operation |
| `ServiceInstanceSchema` | Chứa schema create và update của instance |
| `ServiceBindingSchema` | Chứa schema create của binding |
| `Schemas` | Gom schema instance và binding cho một plan |
| `Plan` | Gắn `Schemas` vào plan được công bố trong catalog |

Ví dụ sử dụng API model của Spring Cloud Open Service Broker 4.4.1:

```java
import java.util.List;
import java.util.Map;

import org.springframework.cloud.servicebroker.model.catalog.MethodSchema;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.Schemas;
import org.springframework.cloud.servicebroker.model.catalog.ServiceBindingSchema;
import org.springframework.cloud.servicebroker.model.catalog.ServiceInstanceSchema;

Map<String, Object> createParametersSchema = Map.of(
        "$schema", "http://json-schema.org/draft-04/schema#",
        "type", "object",
        "properties", Map.of(
                "storage_gb", Map.of(
                        "type", "integer",
                        "minimum", 10,
                        "maximum", 500),
                "region", Map.of(
                        "type", "string",
                        "enum", List.of("ap-southeast-1", "eu-west-1"))),
        "required", List.of("storage_gb", "region"),
        "additionalProperties", false);

Map<String, Object> updateParametersSchema = Map.of(
        "$schema", "http://json-schema.org/draft-04/schema#",
        "type", "object",
        "properties", Map.of(
                "storage_gb", Map.of(
                        "type", "integer",
                        "minimum", 10,
                        "maximum", 1000),
                "backup_enabled", Map.of("type", "boolean")),
        "additionalProperties", false);

Map<String, Object> bindingParametersSchema = Map.of(
        "$schema", "http://json-schema.org/draft-04/schema#",
        "type", "object",
        "properties", Map.of(
                "access_mode", Map.of(
                        "type", "string",
                        "enum", List.of("read-only", "read-write")),
                "connection_pool", Map.of(
                        "type", "integer",
                        "minimum", 1,
                        "maximum", 50)),
        "required", List.of("access_mode"),
        "additionalProperties", false);

MethodSchema createSchema = new MethodSchema(createParametersSchema);
MethodSchema updateSchema = new MethodSchema(updateParametersSchema);
MethodSchema bindingSchema = new MethodSchema(bindingParametersSchema);

Schemas schemas = new Schemas(
        new ServiceInstanceSchema(createSchema, updateSchema),
        new ServiceBindingSchema(bindingSchema));

Plan standardPlan = Plan.builder()
        .id("standard")
        .name("standard")
        .description("PostgreSQL for standard workloads")
        .free(false)
        .schemas(schemas)
        .build();
```

Đoạn code minh họa cách tạo các model catalog và gắn schema vào `Plan`. Các map bên trong là JSON Schema thông thường, vì vậy có thể được xây dựng từ cấu hình, file JSON hoặc code. Khi dùng phiên bản thư viện khác 4.4.1, cần đối chiếu constructor và builder tương ứng trong API docs của phiên bản đó.

## 9. Đọc và validate parameters trong service implementation

Spring Cloud Open Service Broker ánh xạ JSON body thành request model rồi chuyển request cho service interface. Với request parameterized, `AsyncParameterizedServiceInstanceRequest.getParameters()` cung cấp `Map<String, Object>` đã được chuyển từ JSON object. Tài liệu API của framework nêu rõ broker chịu trách nhiệm xác thực nội dung parameters về tính đúng đắn và khả năng áp dụng; việc platform đã dùng schema để dựng form không thay thế bước kiểm tra này.

Ví dụ luồng provision:

```java
@Service
public class PostgreSqlInstanceService implements ServiceInstanceService {

    private final ProvisioningUseCase provisioning;
    private final ParameterValidator parameterValidator;

    public PostgreSqlInstanceService(
            ProvisioningUseCase provisioning,
            ParameterValidator parameterValidator) {
        this.provisioning = provisioning;
        this.parameterValidator = parameterValidator;
    }

    @Override
    public Mono<CreateServiceInstanceResponse> createServiceInstance(
            CreateServiceInstanceRequest request) {
        Map<String, Object> parameters = request.getParameters();

        return parameterValidator.validateCreate(
                        request.getPlanId(), parameters)
                .then(provisioning.provision(request, parameters));
    }
}
```

`ParameterValidator` và `ProvisioningUseCase` là abstraction do ứng dụng xây dựng, không phải class mặc định của Spring Cloud Open Service Broker. Đây là skeleton minh họa luồng xử lý; imports và các phương thức interface khác được lược bỏ. Ví dụ tập trung vào việc lấy parameters, validate theo plan và chỉ sau đó mới gọi use case cấp phát. Với request update và binding, dùng validator riêng tương ứng với schema của operation đó.

### 9.1. Các lớp kiểm tra nên thực hiện

1. **Cấu trúc JSON:** `parameters` phải là object nếu được gửi; kiểm tra kiểu dữ liệu và cấu trúc lồng nhau.
2. **Schema theo plan và operation:** kiểm tra field bắt buộc, enum, giới hạn số, độ dài và field không được phép.
3. **Quy tắc nghiệp vụ:** kiểm tra quota, region, khả năng của provider, quyền người dùng và giới hạn của plan.
4. **Trạng thái tài nguyên:** kiểm tra instance đang ở trạng thái cho phép update hoặc binding; tránh xung đột với operation đang chạy.
5. **An toàn dữ liệu:** lọc log, giới hạn kích thước, chống injection ở các adapter và bảo vệ secrets.

JSON Schema giúp xác định dữ liệu có đúng hình dạng hay không. Nó không thay thế kiểm tra quyền, kiểm tra quota hoặc kiểm tra trạng thái tài nguyên.

### 9.2. Xử lý lỗi validation

Nếu request sai cấu trúc hoặc thiếu dữ liệu bắt buộc, broker nên trả `400 Bad Request` với mô tả dễ hiểu và không bắt đầu provision/update/binding. Nếu cấu trúc hợp lệ nhưng yêu cầu không thể thực hiện theo trạng thái hiện tại hoặc vượt giới hạn nghiệp vụ, broker có thể trả lỗi phù hợp theo đặc tả, chẳng hạn `422 Unprocessable Entity` cho một thay đổi không được hỗ trợ.

Khi trả lỗi `4xx`, tài nguyên broker phải không thay đổi về mặt ngữ nghĩa do request bị từ chối. Vì vậy, nên validate trước side effect; nếu phải gọi provider trước để xác minh một điều kiện động, cần thiết kế transaction, compensation hoặc cơ chế đối soát thích hợp.

## 10. Khác biệt giữa create, update và binding

| Tiêu chí | Provision | Update | Binding |
|---|---|---|---|
| Schema | `service_instance.create` | `service_instance.update` | `service_binding.create` |
| Endpoint | `PUT /v2/service_instances/{id}` | `PATCH /v2/service_instances/{id}` | `PUT /v2/service_instances/{id}/service_bindings/{binding_id}` |
| Mục tiêu | Cấu hình tài nguyên mới | Thay đổi cấu hình instance hiện có | Cấu hình quyền hoặc thông tin sử dụng cho consumer |
| Ví dụ parameters | `storage_gb`, `region`, `high_availability` | `storage_gb`, `backup_enabled` | `access_mode`, `connection_pool` |
| Trạng thái ảnh hưởng | Chưa có instance hoặc ID đã tồn tại | Instance phải ở trạng thái có thể update | Instance phải tồn tại và cho phép bind |
| Xử lý async | Có thể cần `accepts_incomplete=true` | Có thể cần `accepts_incomplete=true` | Có thể cần `accepts_incomplete=true` |

Không nên tái sử dụng một schema duy nhất cho cả ba operation chỉ vì chúng có một vài field trùng nhau. Tách schema giúp broker thể hiện rõ field nào chỉ có ý nghĩa khi provision, field nào có thể cập nhật và field nào chỉ điều khiển quyền của consumer.

## 11. Tương thích schema và tiến hóa API

Schema được platform lấy từ catalog và có thể được cache. Khi thay đổi schema, cần xem đó là thay đổi contract với client:

- Thêm property tùy chọn thường ít phá vỡ tương thích hơn thêm property bắt buộc.
- Thu hẹp `enum`, giảm `maximum`, tăng `minimum` hoặc bật `additionalProperties: false` có thể khiến request cũ không còn hợp lệ.
- Đổi kiểu dữ liệu của property có thể làm hỏng biểu mẫu, client và automation đã tạo dựa trên catalog trước đó.
- Xóa property đang được sử dụng có thể làm người dùng không thể update hoặc tạo binding với cấu hình cũ.
- Schema phải nằm trong giới hạn kích thước và không dùng external `$ref`.

Khi cần thay đổi lớn, cân nhắc tạo plan hoặc phiên bản offering mới thay vì làm schema hiện tại không tương thích đột ngột. Giữ ổn định service ID và plan ID của tài nguyên đang tồn tại để platform tiếp tục quản lý các instance cũ.

## 12. Bảo mật khi xử lý tham số

Parameters có thể chứa dữ liệu nhạy cảm như tên người dùng, thông tin billing hoặc cấu hình kết nối. Một số nguyên tắc cần áp dụng:

- Không ghi toàn bộ `parameters` vào log hoặc tracing khi chưa lọc dữ liệu nhạy cảm.
- Không trả lại các giá trị nhạy cảm trong fetch instance nếu không cần thiết; OSB cho phép broker bỏ qua một phần hoặc toàn bộ parameters khi fetch vì lý do bảo mật.
- Không dùng schema làm cơ chế phân quyền. Người dùng có thể sửa request trực tiếp dù platform đã ẩn field trên giao diện.
- Giới hạn kích thước request, độ sâu object và số phần tử array để tránh tiêu thụ tài nguyên quá mức.
- Chuẩn hóa và validate mọi giá trị trước khi ghép vào câu lệnh SQL, shell command hoặc request gửi tới provider.
- Tách tham số cấu hình instance khỏi credentials của binding; credentials nên do broker sinh và quản lý vòng đời thu hồi khi có thể.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt `schemas` ở cấp service thay vì plan | Catalog không theo đúng cấu trúc OSB | Đặt schema trong object plan tương ứng |
| Dùng chung create schema cho update và binding | Platform hiển thị hoặc kiểm tra sai field | Khai báo từng nhánh operation riêng |
| Thiếu `$schema` | Catalog không đáp ứng yêu cầu JSON Schema của OSB | Khai báo URI Draft 4 hoặc phiên bản được hỗ trợ |
| Dùng external `$ref` | Schema không tuân thủ giới hạn OSB | Nhúng schema cần thiết trực tiếp vào object |
| Tin rằng platform đã validate nên broker không cần kiểm tra | Request trực tiếp có thể vượt qua UI validation | Validate ở phía broker trước side effect |
| Đặt `required` cho mọi field update | Người dùng không thể gửi thay đổi một phần | Chỉ bắt buộc field thật sự cần trong update |
| Coi `default` tự động được áp dụng | Giá trị thực tế khác với điều người viết schema kỳ vọng | Áp dụng default rõ ràng trong nghiệp vụ |
| Dùng JSON Schema để kiểm tra quota runtime | Dữ liệu hợp lệ về cấu trúc nhưng không thể cấp phát | Kiểm tra quota và trạng thái trong use case |
| Ghi secrets trong parameters vào log | Lộ thông tin truy cập hoặc dữ liệu billing | Redact log và quản lý secret an toàn |

## 14. Checklist triển khai

- [ ] Mỗi schema được đặt trong `schemas` của đúng Service Plan.
- [ ] Tách `service_instance.create`, `service_instance.update` và `service_binding.create`.
- [ ] Mỗi JSON Schema có `$schema` và tuân thủ Draft 4 trở lên theo khả năng platform.
- [ ] Không có external `$ref`; kích thước schema không vượt 64 KB.
- [ ] `properties`, `required`, `enum`, giới hạn số và `additionalProperties` phản ánh đúng contract.
- [ ] Broker validate parameters theo operation và plan ở phía server.
- [ ] Broker kiểm tra thêm quota, quyền, trạng thái instance và điều kiện provider.
- [ ] Request update không có field `parameters` thì không làm thay đổi parameters hiện tại.
- [ ] Giá trị mặc định được áp dụng rõ ràng trong code nếu cần.
- [ ] Log và response không để lộ dữ liệu nhạy cảm.
- [ ] Kiểm thử request hợp lệ, thiếu field, sai kiểu, sai enum, vượt giới hạn và field không được phép.

## 15. Tài liệu tham khảo

- [Open Service Broker API Specification v2.16 — Catalog, Service Plan và Schemas](https://github.com/cloudfoundry/servicebroker/blob/v2.16/spec.md)
- [JSON Schema Draft 4](https://json-schema.org/draft-04/schema)
- [Spring Cloud Open Service Broker 4.4.1 — Plan API](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/model/catalog/Plan.html)
- [Spring Cloud Open Service Broker 4.4.1 — MethodSchema API](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/model/catalog/MethodSchema.html)
- [Spring Cloud Open Service Broker 4.4.1 — Schemas API](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/model/catalog/Schemas.html)
- [Spring Cloud Open Service Broker 4.4.1 — AsyncParameterizedServiceInstanceRequest API](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/model/instance/AsyncParameterizedServiceInstanceRequest.html)

Ví dụ JSON Schema trong bài sử dụng Draft 4 và ví dụ Java dựa trên model catalog của Spring Cloud Open Service Broker 4.4.1. Khi triển khai, hãy chọn phiên bản thư viện tương thích với Spring Boot và dependency management của dự án.
