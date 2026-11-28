# Tham số bắt buộc, giá trị mặc định, kiểu dữ liệu và miền giá trị

## Mục tiêu và bối cảnh

Khi nền tảng gọi một service broker để tạo hoặc cập nhật service instance, request có thể mang theo một đối tượng parameters. Đối tượng này cho phép người dùng tùy chỉnh cấu hình của dịch vụ theo service plan đã chọn, chẳng hạn dung lượng lưu trữ, vùng triển khai, chế độ sao lưu, số kết nối hoặc thời gian lưu dữ liệu.

Trong module Spring Cloud Service Broker, parameters là một phần của hợp đồng giữa platform, broker và hệ thống cung cấp tài nguyên. Broker phải công bố dữ liệu đầu vào được hỗ trợ, kiểm tra request ở phía server, áp dụng giá trị mặc định theo chính sách và chuyển cấu hình hợp lệ xuống backend. Nếu chỉ dựa vào biểu mẫu ở giao diện platform, một client khác vẫn có thể gửi dữ liệu sai kiểu, thiếu trường bắt buộc hoặc vượt giới hạn.

Bài học này tập trung vào bốn khía cạnh của tham số đầu vào:

- **Tham số bắt buộc:** trường nào phải xuất hiện để broker có thể thực hiện yêu cầu.
- **Giá trị mặc định:** giá trị broker áp dụng khi người dùng không cung cấp một trường tùy chọn.
- **Kiểu dữ liệu:** chuỗi, số nguyên, số thực, boolean, object hoặc array.
- **Miền giá trị:** khoảng số hợp lệ, tập giá trị cho phép, độ dài chuỗi, mẫu định dạng và các ràng buộc nghiệp vụ.

Sau bài học, bạn có thể đọc schema parameters trong catalog OSB, thiết kế schema theo từng service plan và thao tác, phân biệt dữ liệu bị thiếu với giá trị null, chuẩn hóa và validate parameters trong ứng dụng Spring, đồng thời kiểm thử các trường hợp hợp lệ và không hợp lệ.

## 1. Parameters xuất hiện ở đâu trong OSB API?

Parameters thường được gửi trong request của các thao tác vòng đời. Tùy thao tác, chúng có thể được dùng để tạo instance, cập nhật instance hoặc tạo binding.

| Thao tác | Endpoint điển hình | Ý nghĩa của parameters |
|---|---|---|
| Provision | PUT /v2/service_instances/{instance_id} | Cấu hình ban đầu của tài nguyên |
| Update | PATCH /v2/service_instances/{instance_id} | Các thay đổi người dùng muốn áp dụng |
| Bind | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Tùy chọn riêng cho consumer hoặc quyền truy cập |
| Deprovision | DELETE /v2/service_instances/{instance_id} | Không phải nơi gửi cấu hình tạo mới; broker dùng định danh và dữ liệu đã lưu để thu hồi |

Một request provision rút gọn có thể như sau:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "organization_guid": "org-100",
  "space_guid": "space-200",
  "parameters": {
    "storage_gb": 50,
    "region": "ap-southeast-1",
    "backup_enabled": true
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Trong ví dụ này:

- service_id xác định loại dịch vụ mà broker công bố.
- plan_id xác định cấp dịch vụ được chọn.
- parameters chứa tùy chọn do người dùng cung cấp cho dịch vụ.
- context chứa thông tin nền tảng hoặc môi trường mà broker dùng để xử lý yêu cầu.

Parameters và context có mục đích khác nhau. Parameters là đầu vào cấu hình sản phẩm do người dùng lựa chọn; context là thông tin ngữ cảnh được platform cung cấp theo hợp đồng tích hợp. Không nên lấy một trường trong parameters làm nguồn xác thực tenant nếu tenant identity phải được xác định từ thông tin platform đã xác thực.

### 1.1. Schema được công bố trong catalog

OSB API cho phép broker mô tả schema cho parameters trong phần schemas của service plan. Schema có thể được khai báo riêng cho:

- service_instance.create: parameters khi provision.
- service_instance.update: parameters khi update.
- service_binding.create: parameters khi bind.

Việc tách schema theo thao tác giúp broker công bố đúng trường được phép ở từng giai đoạn. Ví dụ, storage_gb có thể được dùng khi provision và update, trong khi role có thể chỉ xuất hiện ở binding.

Schema giúp platform hiển thị biểu mẫu và kiểm tra dữ liệu trước khi gửi request. Tuy nhiên, broker vẫn phải validate ở server vì không phải mọi client đều dùng giao diện platform hoặc thực hiện kiểm tra phía client.

## 2. Phân biệt bắt buộc, tùy chọn và mặc định

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Required | Trường phải có trong request | engine_version |
| Optional | Trường có thể bỏ qua | maintenance_window |
| Default | Giá trị broker chọn khi trường không được gửi | backup_enabled mặc định true |

Giả sử dịch vụ database yêu cầu engine_version, cho phép người dùng chọn storage_gb và có mặc định backup_enabled=true.

| Parameter | Required | Default | Ý nghĩa |
|---|---:|---|---|
| engine_version | Có | Không có | Phiên bản engine phải được chọn rõ |
| storage_gb | Không | 20 | Dung lượng mặc định 20 GB |
| backup_enabled | Không | true | Bật sao lưu nếu không chỉ định |
| maintenance_window | Không | Không có | Không đặt cửa sổ bảo trì nếu người dùng bỏ trống |

Trong JSON Schema, danh sách required thể hiện các trường phải xuất hiện. Thuộc tính default thường là một annotation mô tả giá trị mặc định. Việc khai báo default trong schema không có nghĩa mọi validator tự động chèn giá trị đó vào request. Broker phải chủ động áp dụng default trong logic chuẩn hóa.

Ví dụ:

~~~json
{
  "type": "object",
  "required": ["engine_version"],
  "properties": {
    "engine_version": {
      "type": "string",
      "enum": ["15", "16"]
    },
    "storage_gb": {
      "type": "integer",
      "minimum": 20,
      "maximum": 500,
      "default": 20
    },
    "backup_enabled": {
      "type": "boolean",
      "default": true
    }
  }
}
~~~

Ở schema này, engine_version phải có mặt; storage_gb và backup_enabled có thể vắng mặt. Khi người dùng không gửi storage_gb, broker có thể chuẩn hóa thành 20. Khi người dùng không gửi backup_enabled, broker có thể chuẩn hóa thành true.

### 2.1. Trường bị thiếu và trường null

Một lỗi thường gặp là coi trường không có trong JSON giống trường có giá trị null. Hai trường hợp khác nhau:

~~~json
{
  "storage_gb": 50
}
~~~

Trường region bị thiếu. Broker có thể áp dụng default nếu đã định nghĩa.

~~~json
{
  "storage_gb": 50,
  "region": null
}
~~~

Trường region có mặt nhưng giá trị là null. Nếu schema yêu cầu region có kiểu string, null không hợp lệ. Broker không nên âm thầm chuyển null thành default trừ khi hợp đồng sản phẩm quy định rõ hành vi đó.

Một chính sách dễ hiểu là:

- Trường vắng mặt: áp dụng default nếu có; nếu required thì trả lỗi validation.
- Trường có giá trị: kiểm tra đúng kiểu và miền giá trị.
- Trường có null: chỉ chấp nhận nếu schema và chính sách nghiệp vụ cho phép null.
- Trường không được nhận diện: từ chối hoặc xử lý theo chính sách tương thích đã công bố; không âm thầm bỏ qua nếu điều đó có thể che giấu lỗi cấu hình.

### 2.2. Default phải được áp dụng ở đúng thời điểm

Broker nên áp dụng default sau khi xác định service và plan, nhưng trước khi lưu cấu hình cuối cùng hoặc gọi backend. Quy trình khái quát:

1. Nhận parameters từ request.
2. Kiểm tra request thuộc service và plan hợp lệ.
3. Tạo bản sao dữ liệu đầu vào để xử lý.
4. Bổ sung default cho những trường vắng mặt.
5. Kiểm tra kiểu dữ liệu và miền giá trị trên dữ liệu đã chuẩn hóa.
6. Áp dụng các quy tắc nghiệp vụ liên trường.
7. Lưu cấu hình đã chuẩn hóa và chuyển lệnh xuống backend.

Không sửa trực tiếp map đầu vào dùng chung nếu thư viện hoặc các thành phần khác có thể còn tham chiếu đến nó. Hãy tạo một cấu trúc dữ liệu chuẩn hóa mới để dễ kiểm tra và audit.

## 3. Kiểu dữ liệu của parameters

JSON Schema mô tả kiểu dữ liệu bằng thuộc tính type. Các kiểu thường dùng:

| Kiểu | Dữ liệu JSON | Ví dụ |
|---|---|---|
| string | Chuỗi ký tự | "ap-southeast-1" |
| integer | Số nguyên | 50 |
| number | Số có thể có phần thập phân | 1.5 |
| boolean | true hoặc false | true |
| object | Đối tượng gồm các trường con | {"retention_days": 7} |
| array | Danh sách phần tử | ["read", "write"] |

Kiểu dữ liệu phải phản ánh ý nghĩa của tham số. Không nên dùng string cho mọi trường chỉ để dễ nhận dữ liệu. Ví dụ, storage_gb nên là integer để có thể kiểm tra min/max và tránh việc "fifty" được chấp nhận rồi mới thất bại khi gọi backend.

### 3.1. String

Chuỗi thường dùng cho tên region, engine version, mã cấu hình hoặc nhãn tùy chọn. Có thể giới hạn độ dài bằng minLength và maxLength, hoặc dùng pattern khi định dạng có quy tắc.

~~~json
{
  "region": {
    "type": "string",
    "minLength": 3,
    "maxLength": 32,
    "pattern": "^[a-z0-9-]+$"
  }
}
~~~

Nếu chỉ cho phép một tập region đã hỗ trợ, dùng enum thay vì chỉ kiểm tra chuỗi có đúng định dạng:

~~~json
{
  "region": {
    "type": "string",
    "enum": ["ap-southeast-1", "ap-northeast-1"]
  }
}
~~~

Pattern chỉ kiểm tra hình dạng chuỗi. Nó không chứng minh region đó tồn tại hoặc broker có quota để cấp tài nguyên tại region đó. Broker vẫn cần kiểm tra khả năng backend và chính sách tenant.

### 3.2. Integer và number

Dùng integer cho số lượng nguyên như dung lượng GB, số replica hoặc số kết nối tối đa. Dùng number cho giá trị có phần thập phân như tỷ lệ hoặc hệ số.

~~~json
{
  "storage_gb": {
    "type": "integer",
    "minimum": 20,
    "maximum": 500
  },
  "cpu_cores": {
    "type": "number",
    "minimum": 0.5,
    "maximum": 16
  }
}
~~~

Các giới hạn minimum và maximum là ràng buộc bao gồm cả biên. Nếu cần loại trừ biên, JSON Schema Draft 4 có các thuộc tính exclusiveMinimum và exclusiveMaximum. Phải chọn đúng draft mà OSB API và validator đang sử dụng.

Không nên parse số bằng cách ép kiểu tùy tiện. Chẳng hạn, giá trị JSON 20.5 không thể được làm tròn âm thầm thành 20 nếu trường yêu cầu integer. Việc chuyển đổi phải giữ nguyên ý nghĩa và từ chối dữ liệu không tương thích.

### 3.3. Boolean

Boolean phù hợp với tùy chọn bật/tắt:

~~~json
{
  "backup_enabled": {
    "type": "boolean",
    "default": true
  }
}
~~~

Không nên chấp nhận chuỗi "true" hoặc "false" thay cho boolean nếu schema yêu cầu boolean. Một số giao diện có thể gửi chuỗi do cách serialize form; broker nên báo lỗi kiểu dữ liệu rõ ràng để client sửa request.

### 3.4. Object và array

Object dùng khi một nhóm tham số có cấu trúc riêng. Ví dụ:

~~~json
{
  "backup": {
    "type": "object",
    "properties": {
      "enabled": {
        "type": "boolean",
        "default": true
      },
      "retention_days": {
        "type": "integer",
        "minimum": 1,
        "maximum": 90
      }
    },
    "required": ["retention_days"],
    "additionalProperties": false
  }
}
~~~

Array dùng khi tham số là danh sách:

~~~json
{
  "allowed_cidrs": {
    "type": "array",
    "items": {
      "type": "string",
      "pattern": "^[0-9./:a-fA-F]+$"
    },
    "minItems": 1,
    "maxItems": 20,
    "uniqueItems": true
  }
}
~~~

Pattern trong ví dụ CIDR chỉ là minh họa định dạng sơ bộ; regex đơn giản không thay thế parser IP/CIDR thực sự. Broker nên parse từng phần tử bằng thư viện mạng phù hợp để xác nhận subnet hợp lệ và áp dụng chính sách mạng.

## 4. Miền giá trị và các ràng buộc

Kiểu dữ liệu chỉ trả lời "giá trị thuộc loại gì?". Miền giá trị trả lời "giá trị nào được phép?".

Các ràng buộc thường dùng:

| Ràng buộc | Áp dụng cho | Mục đích |
|---|---|---|
| enum | string, number | Chỉ chấp nhận tập giá trị định trước |
| minimum / maximum | number, integer | Giới hạn khoảng số |
| minLength / maxLength | string | Giới hạn độ dài |
| pattern | string | Kiểm tra định dạng |
| minItems / maxItems | array | Giới hạn số phần tử |
| uniqueItems | array | Không cho phần tử trùng |
| required | object | Bắt buộc trường con |
| additionalProperties | object | Kiểm soát trường ngoài schema |
| properties | object | Định nghĩa các trường con |
| items | array | Định nghĩa kiểu và schema phần tử |

Ví dụ schema cho cấu hình một service plan:

~~~json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "additionalProperties": false,
  "required": ["engine_version"],
  "properties": {
    "engine_version": {
      "type": "string",
      "enum": ["15", "16"]
    },
    "storage_gb": {
      "type": "integer",
      "minimum": 20,
      "maximum": 500,
      "default": 20
    },
    "backup_enabled": {
      "type": "boolean",
      "default": true
    },
    "region": {
      "type": "string",
      "enum": ["ap-southeast-1", "ap-northeast-1"],
      "default": "ap-southeast-1"
    },
    "maintenance_window": {
      "type": "string",
      "pattern": "^(MON|TUE|WED|THU|FRI|SAT|SUN):([01][0-9]|2[0-3]):[0-5][0-9]$"
    }
  }
}
~~~

Với schema này:

- engine_version là bắt buộc và chỉ nhận 15 hoặc 16.
- storage_gb là số nguyên từ 20 đến 500; nếu vắng mặt, broker áp dụng 20.
- backup_enabled là boolean; nếu vắng mặt, broker áp dụng true.
- region chỉ nhận hai region đã liệt kê; nếu vắng mặt, broker áp dụng ap-southeast-1.
- maintenance_window là tùy chọn và phải theo định dạng ngày trong tuần cùng giờ UTC hoặc múi giờ đã được sản phẩm quy định.

Regex của maintenance_window chỉ kiểm tra định dạng. Broker cần quy định rõ múi giờ và có thể cần kiểm tra thêm chính sách bảo trì của backend. Schema không thay thế kiểm tra nghiệp vụ theo trạng thái thực tế của tài nguyên.

### 4.1. additionalProperties và tương thích

Khi additionalProperties=false, request có trường ngoài schema sẽ bị từ chối. Điều này giúp phát hiện lỗi chính tả và ngăn client gửi nhầm thuộc tính. Tuy nhiên, khi mở rộng catalog, cần quản lý tương thích: thêm trường mới có thể cần cập nhật schema và versioning tài liệu, còn client cũ phải tiếp tục hoạt động theo chính sách đã công bố.

Nếu cho phép additionalProperties, broker vẫn nên quyết định cách xử lý trường không nhận diện. Không chuyển mọi thuộc tính lạ xuống backend một cách tự động. Cần whitelist trường và kiểm tra quyền trước khi thực hiện thao tác có ảnh hưởng tài nguyên.

## 5. Khai báo schema trong service plan

OSB API gắn schema parameters với service plan và thao tác tương ứng. Ví dụ catalog có thể công bố schema tạo instance:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "managed-postgresql",
      "description": "PostgreSQL duoc quan ly",
      "bindable": true,
      "plans": [
        {
          "id": "plan-standard",
          "name": "standard",
          "description": "Plan database tieu chuan",
          "schemas": {
            "service_instance": {
              "create": {
                "parameters": {
                  "$schema": "http://json-schema.org/draft-04/schema#",
                  "type": "object",
                  "required": ["engine_version"],
                  "properties": {
                    "engine_version": {
                      "type": "string",
                      "enum": ["15", "16"]
                    },
                    "storage_gb": {
                      "type": "integer",
                      "minimum": 20,
                      "maximum": 500,
                      "default": 20
                    }
                  }
                }
              }
            }
          }
        }
      ]
    }
  ]
}
~~~

Schema này thuộc plan-standard. Một plan khác có thể cho phép dung lượng tối đa cao hơn hoặc cung cấp các region khác nhau. Broker cần kiểm tra parameters theo đúng plan ID của request, không dùng chung một bộ giới hạn cho mọi plan nếu sản phẩm có chính sách khác nhau.

### 5.1. Schema create và update khác nhau

Schema create mô tả cấu hình ban đầu. Schema update mô tả các trường được phép thay đổi sau khi instance đã tồn tại.

Ví dụ, provision yêu cầu engine_version và cho phép storage_gb. Update có thể chỉ cho phép storage_gb và backup_enabled:

~~~json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "required": ["engine_version"],
          "properties": {
            "engine_version": {
              "type": "string",
              "enum": ["15", "16"]
            },
            "storage_gb": {
              "type": "integer",
              "minimum": 20,
              "maximum": 500,
              "default": 20
            }
          }
        }
      },
      "update": {
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 20,
              "maximum": 1000
            },
            "backup_enabled": {
              "type": "boolean"
            }
          }
        }
      }
    }
  }
}
~~~

Trong ví dụ, engine_version không xuất hiện trong schema update, nên client không được yêu cầu thay đổi phiên bản engine bằng thao tác update này. Schema update cũng không đặt default cho storage_gb: nếu người dùng chỉ thay backup_enabled, broker không được tự đặt storage_gb về 20 và vô tình làm thay đổi cấu hình hiện tại.

### 5.2. Schema cho binding

Binding parameters có thể khác hoàn toàn parameters của instance. Ví dụ, người dùng có thể yêu cầu quyền read-only hoặc read-write cho một ứng dụng:

~~~json
{
  "schemas": {
    "service_binding": {
      "create": {
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "role": {
              "type": "string",
              "enum": ["read-only", "read-write"],
              "default": "read-only"
            }
          }
        }
      }
    }
  }
}
~~~

Quyền được yêu cầu trong parameters phải được giới hạn bởi chính sách của tenant và service plan. Không để client tự yêu cầu quyền quản trị chỉ vì schema cho phép một chuỗi role bất kỳ.

## 6. Validation phía server trong Spring Cloud Service Broker

Catalog schema giúp mô tả đầu vào, nhưng broker vẫn là ranh giới tin cậy cuối cùng. Mọi request cần được xác thực và kiểm tra trước khi thay đổi trạng thái hoặc gọi backend.

Một pipeline xử lý phù hợp:

~~~mermaid
flowchart TD
    A[Nhận request OSB] --> B[Xác thực platform và định danh]
    B --> C[Tra service definition và plan]
    C --> D[Chọn schema theo thao tác]
    D --> E[Kiểm tra kiểu và miền giá trị]
    E --> F[Áp dụng default cho trường vắng mặt]
    F --> G[Kiểm tra quy tắc nghiệp vụ]
    G --> H[Chuẩn hóa cấu hình]
    H --> I[Lưu operation và instance]
    I --> J[Gọi backend hoặc xếp hàng công việc]
    E -->|Không hợp lệ| X[Trả lỗi request]
    G -->|Vi phạm chính sách| X
~~~

Thứ tự có thể được triển khai theo validator cụ thể, nhưng các nguyên tắc phải được giữ:

- Chọn schema dựa trên service, plan và operation.
- Không tin dữ liệu từ client chỉ vì catalog đã công bố schema.
- Kiểm tra kiểu và miền giá trị trước khi gọi backend.
- Áp dụng default một cách xác định.
- Kiểm tra quota, quyền tenant và khả năng backend.
- Chỉ lưu trạng thái đã được chuẩn hóa sau khi các kiểm tra cần thiết thành công.

### 6.1. Lấy parameters từ request

Spring Cloud Open Service Broker cung cấp request model cho từng thao tác. Service implementation nhận request tương ứng và đọc parameters từ model. Với provision, luồng nghiệp vụ có thể bắt đầu như sau:

~~~java
Map<String, Object> supplied =
        request.getParameters();

NormalizedParameters normalized =
        parameterNormalizer.normalize(
                request.getServiceDefinitionId(),
                request.getPlanId(),
                OperationType.CREATE,
                supplied
        );
~~~

Đoạn mã trên minh họa tầng application service. Kiểu request cụ thể và chữ ký method cần khớp phiên bản Spring Cloud Open Service Broker đang dùng. Không nên đặt toàn bộ logic validate trong HTTP controller; hãy gom thành một thành phần domain/application có thể tái sử dụng cho các thao tác và kiểm thử độc lập.

### 6.2. Chuẩn hóa default

Một normalizer có thể nhận bản sao parameters, bổ sung giá trị mặc định và trả về cấu trúc mới:

~~~java
public Map<String, Object> applyDefaults(
        Map<String, Object> supplied,
        Map<String, Object> defaults) {

    Map<String, Object> normalized = new HashMap<>(supplied);

    defaults.forEach((name, value) ->
            normalized.putIfAbsent(name, value));

    return Map.copyOf(normalized);
}
~~~

Đây là đoạn minh họa. Trong implementation thực tế, cần xác định cách xử lý null, object lồng nhau, giá trị mặc định có thể thay đổi theo plan và các collection mutable. Map.copyOf không chấp nhận null; nếu schema cho phép null thì cần cấu trúc dữ liệu phù hợp hoặc từ chối null rõ ràng.

Đối với object lồng nhau, việc áp dụng default có thể cần đệ quy theo schema. Không chỉ dùng putIfAbsent ở cấp ngoài nếu các trường con cũng có default.

### 6.3. Kiểm tra kiểu và miền giá trị

Có thể dùng một thư viện JSON Schema validator tương thích với draft mà OSB API đang công bố. Quy trình thường là:

1. Chuyển parameters thành JSON node hoặc cấu trúc dữ liệu mà validator hỗ trợ.
2. Nạp schema của đúng service plan và thao tác.
3. Chạy validation.
4. Thu thập các lỗi theo JSON Pointer hoặc đường dẫn trường.
5. Chuyển lỗi thành response OSB API có mô tả rõ ràng, không lộ stack trace hoặc thông tin nội bộ.

Không tự viết validator regex cho mọi kiểu dữ liệu. Các ràng buộc như number, object, array, nested required và additionalProperties nên được xử lý bởi JSON Schema validator đã được kiểm chứng. Những quy tắc liên quan đến quota hoặc trạng thái backend vẫn cần kiểm tra riêng trong domain service.

### 6.4. Quy tắc nghiệp vụ vượt ngoài schema

JSON Schema kiểm tra hình dạng dữ liệu, nhưng không diễn đạt được mọi quy tắc nghiệp vụ phụ thuộc vào trạng thái hoặc tenant.

Ví dụ:

- storage_gb không vượt quota còn lại của organization.
- Region phải được bật cho tenant hiện tại.
- Plan production yêu cầu backup_enabled=true.
- Không thể giảm dung lượng xuống thấp hơn dung lượng dữ liệu đang sử dụng.
- maintenance_window không được trùng thời điểm bảo trì bắt buộc của hệ thống.
- Role binding phải nằm trong tập quyền mà tenant được cấp.

Các quy tắc này cần nằm trong domain service hoặc policy service. Đừng cố nhồi toàn bộ logic nghiệp vụ vào JSON Schema.

## 7. Xử lý parameters khi update

Update khác provision vì instance đã có cấu hình trước đó. Parameters trong PATCH thường mô tả những trường người dùng muốn thay đổi. Broker cần kết hợp dữ liệu update với cấu hình hiện tại theo chính sách rõ ràng.

Ví dụ instance đang có:

~~~json
{
  "engine_version": "16",
  "storage_gb": 100,
  "backup_enabled": true,
  "region": "ap-southeast-1"
}
~~~

Request update chỉ thay dung lượng:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "storage_gb": 200
  },
  "previous_values": {
    "plan_id": "plan-standard"
  }
}
~~~

Broker cần giữ nguyên engine_version, backup_enabled và region, chỉ cập nhật storage_gb. Không áp dụng lại toàn bộ default create vào cấu hình hiện có vì việc đó có thể ghi đè lựa chọn trước đây.

Một quy trình update điển hình:

1. Tải instance và cấu hình đã lưu.
2. Kiểm tra tenant, trạng thái instance và plan hiện tại.
3. Chọn schema update của plan đích.
4. Validate các trường mà request cung cấp.
5. Merge theo quy tắc PATCH của sản phẩm.
6. Kiểm tra chuyển đổi plan và các ràng buộc không thể đảo ngược.
7. Lưu cấu hình mong muốn và tạo operation.
8. Điều phối backend, theo dõi kết quả và cập nhật trạng thái.

Không mặc định mọi trường bị thiếu trong update đều được thay bằng default. Trường bị thiếu thường có nghĩa là giữ nguyên giá trị hiện tại. Hành vi cụ thể phải nhất quán với hợp đồng update và cách platform gửi request.

## 8. Bảo mật và an toàn dữ liệu đầu vào

Parameters là dữ liệu không đáng tin cậy. Một request hợp lệ về JSON vẫn có thể gây rủi ro nếu broker dùng dữ liệu đó để tạo tài nguyên hoặc gọi API quản trị.

Các nguyên tắc quan trọng:

- Giới hạn kích thước request và độ sâu object lồng nhau.
- Giới hạn số phần tử array và độ dài chuỗi.
- Whitelist các trường được phép.
- Kiểm tra kiểu và miền giá trị ở server.
- Không dùng parameters để ghi đè tenant identity hoặc quyền platform.
- Không đưa secret vào catalog schema hoặc mô tả lỗi.
- Không log toàn bộ request nếu có trường nhạy cảm.
- Kiểm tra URL, hostname, địa chỉ IP và DNS khi parameters có thể ảnh hưởng kết nối mạng.
- Không ghép chuỗi đầu vào trực tiếp vào SQL, shell command, tên resource hoặc manifest.
- Dùng parameterized query và API client có kiểm soát.

Nếu parameters chứa password do người dùng tự đặt, cần quyết định có thực sự cần trường đó hay broker nên tự sinh secret. Khi bắt buộc nhận secret, chỉ xử lý trong vùng bảo mật, mã hóa khi lưu và che dữ liệu ở log, trace và response lỗi.

## 9. Idempotency và cấu hình đã chuẩn hóa

Request có thể được platform gửi lại khi timeout. Vì vậy, broker cần kết hợp idempotency với việc chuẩn hóa parameters.

Ví dụ, lần đầu request bỏ storage_gb và broker áp dụng default 20. Platform không nhận được response và gửi lại request. Nếu default đã thay đổi thành 30 giữa hai lần, broker không được vô tình biến cùng một yêu cầu thành cấu hình khác.

Cách xử lý:

- Lưu cấu hình đã chuẩn hóa cùng instance hoặc operation ngay khi chấp nhận request.
- Lưu plan ID, service ID và thông tin phiên bản schema/chính sách cần thiết.
- Với request lặp, tra instance/operation theo định danh ổn định trước khi chạy lại workflow.
- Không tính lại default theo cấu hình mới nếu request đã được chấp nhận và lưu trước đó.
- So sánh request fingerprint theo chính sách canonicalization nhất quán.

Một fingerprint hợp lý có thể được tạo từ service ID, plan ID và parameters đã chuẩn hóa. Cần quyết định rõ thứ tự key, cách biểu diễn số và xử lý giá trị null để hai JSON có cùng ý nghĩa không bị xem là hai request khác nhau.

## 10. Kiểm thử required, default, type và range

Một bộ test tốt phải kiểm tra cả trường hợp hợp lệ lẫn ranh giới và dữ liệu sai.

| Trường hợp | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Thiếu required | Không có engine_version | Từ chối validation |
| Required hợp lệ | engine_version="16" | Chấp nhận |
| Sai enum | engine_version="17" | Từ chối |
| Bỏ trường có default | Không có storage_gb | Chuẩn hóa storage_gb=20 |
| Giá trị đúng biên dưới | storage_gb=20 | Chấp nhận |
| Giá trị đúng biên trên | storage_gb=500 | Chấp nhận |
| Dưới minimum | storage_gb=19 | Từ chối |
| Trên maximum | storage_gb=501 | Từ chối |
| Sai kiểu | storage_gb="50" | Từ chối |
| Null không được phép | backup_enabled=null | Từ chối |
| Trường lạ | admin_mode=true | Từ chối nếu additionalProperties=false |
| Update thiếu trường | Chỉ gửi backup_enabled | Giữ nguyên các trường khác |

### 10.1. Unit test cho normalizer và validator

Có thể tách kiểm tra default thành unit test độc lập:

~~~java
@Test
void appliesDefaultWhenOptionalParameterIsAbsent() {
    Map<String, Object> supplied = Map.of(
            "engine_version", "16"
    );

    Map<String, Object> normalized =
            parameterNormalizer.normalizeCreate(supplied);

    assertThat(normalized)
            .containsEntry("storage_gb", 20)
            .containsEntry("backup_enabled", true);
}
~~~

Và kiểm tra trường bắt buộc:

~~~java
@Test
void rejectsMissingRequiredParameter() {
    Map<String, Object> supplied = Map.of(
            "storage_gb", 50
    );

    assertThatThrownBy(() ->
            parameterNormalizer.normalizeCreate(supplied))
            .isInstanceOf(ParameterValidationException.class);
}
~~~

Đây là ví dụ minh họa cho API nội bộ của normalizer. Tên method, exception và assertion library phụ thuộc implementation của project.

### 10.2. Kiểm thử qua endpoint OSB

Ngoài unit test, gửi request qua endpoint OSB để xác nhận:

- Catalog công bố đúng schema của plan.
- Request hợp lệ đi tới service implementation.
- Request sai schema được trả lỗi theo giao thức.
- Request không tạo operation hoặc tài nguyên backend khi validation thất bại.
- Request update không làm mất các trường không được thay đổi.
- Retry cùng instance ID không áp dụng default hoặc tạo tài nguyên lặp ngoài ý muốn.

## 11. Những lỗi thiết kế thường gặp

- **Chỉ validate ở giao diện:** client khác có thể gửi dữ liệu sai trực tiếp tới broker.
- **Khai báo default nhưng không áp dụng:** người dùng bỏ trường và backend nhận null hoặc thiếu cấu hình.
- **Coi null giống trường bị thiếu:** broker có thể âm thầm thay đổi ý nghĩa request.
- **Dùng string cho mọi giá trị:** mất khả năng kiểm tra kiểu và có thể gây lỗi khi gọi backend.
- **Không giới hạn miền giá trị:** người dùng có thể yêu cầu dung lượng, replica hoặc retention vượt khả năng cung cấp.
- **Dùng schema create cho update:** request update có thể vô tình đặt lại các trường không được gửi.
- **Cho phép trường lạ đi xuống backend:** tạo rủi ro bảo mật và hành vi không dự đoán.
- **Áp dụng default trước khi biết plan:** cùng một tham số có thể có default khác nhau theo plan.
- **Tính lại default khi retry:** cùng request có thể tạo ra cấu hình khác sau khi chính sách thay đổi.
- **Chỉ kiểm tra schema:** quota, quyền tenant và trạng thái backend vẫn có thể làm yêu cầu không hợp lệ.

## 12. Quy trình thiết kế parameters cho một service plan

Khi thêm một tham số mới, hãy thực hiện theo trình tự:

1. Xác định use case mà tham số điều khiển.
2. Chọn kiểu dữ liệu đúng với ý nghĩa.
3. Xác định trường bắt buộc hay tùy chọn.
4. Nếu có default, xác định giá trị và nơi áp dụng.
5. Xác định miền giá trị, enum và giới hạn biên.
6. Quyết định tham số thuộc create, update hay binding.
7. Công bố schema trong đúng service plan.
8. Validate lại ở server và áp dụng quy tắc nghiệp vụ.
9. Lưu cấu hình đã chuẩn hóa để phục vụ retry và reconciliation.
10. Viết test cho giá trị hợp lệ, thiếu trường, null, sai kiểu và biên.

Ví dụ, khi thêm tham số storage_gb cho plan Standard, nhóm phát triển cần thống nhất đơn vị GB, mức tối thiểu, mức tối đa, default, khả năng tăng/giảm khi update và cách backend thực hiện thay đổi. Nếu các quyết định này chưa rõ, schema có thể hợp lệ về cú pháp nhưng không phản ánh đúng sản phẩm.

## Kết luận

Parameters là hợp đồng cấu hình giữa platform và service broker. JSON Schema trong catalog giúp mô tả tham số bắt buộc, giá trị mặc định, kiểu dữ liệu và miền giá trị cho từng thao tác của service plan. Tuy nhiên, schema chỉ mô tả và hỗ trợ kiểm tra hình dạng dữ liệu; broker vẫn phải validate ở server, áp dụng default có chủ đích, kiểm tra quy tắc nghiệp vụ và lưu cấu hình đã chuẩn hóa.

Trong Spring Cloud Service Broker, hãy chọn schema đúng cho create, update và binding; phân biệt trường bị thiếu với null; giữ cấu hình update không làm mất giá trị hiện tại; và kết hợp validation với idempotency. Cách làm này giúp catalog dễ hiểu, request an toàn và backend nhận được cấu hình nhất quán trong suốt vòng đời service instance.
