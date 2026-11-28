# Mô tả tham số bằng JSON Schema trong danh mục dịch vụ

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker được xây dựng theo Open Service Broker API (OSB API). Broker công bố service offering và service plan để platform hiển thị cho người dùng. Khi tạo service instance, cập nhật instance hoặc tạo binding, platform có thể gửi thêm các tham số cấu hình. JSON Schema trong catalog mô tả cấu trúc và giới hạn của những tham số đó.

JSON Schema tạo ra một hợp đồng dữ liệu có thể đọc được bằng máy. Platform có thể dùng schema để dựng biểu mẫu, hiển thị hướng dẫn, kiểm tra kiểu dữ liệu và cảnh báo giá trị ngoài giới hạn trước khi gửi request. Broker dùng cùng hợp đồng làm cơ sở validate request ở phía server. Nhờ vậy, người dùng hiểu rõ tùy chọn của từng plan và broker nhận được dữ liệu có cấu trúc nhất quán.

Schema mô tả riêng đối tượng **parameters** của từng thao tác. Nó không thay thế toàn bộ request OSB, không mô tả credentials mà broker trả về và không thay thế quy tắc nghiệp vụ hoặc kiểm tra quyền trong broker.

## 1. JSON Schema nằm ở đâu trong OSB catalog?

Platform tải catalog từ broker qua endpoint:

~~~http
GET /v2/catalog
X-Broker-API-Version: 2.17
~~~

Catalog trả về danh sách service offering. Mỗi service có thể có nhiều plan; schema tham số được khai báo ở cấp plan vì các plan khác nhau có thể chấp nhận cấu hình khác nhau.

Trong OSB API, phần schema của một plan được chia theo loại tài nguyên và thao tác:

| Vị trí trong catalog | Request được mô tả | Ý nghĩa |
|---|---|---|
| **schemas.service_instance.create.parameters** | Provision service instance | Tham số khi tạo instance |
| **schemas.service_instance.update.parameters** | Update service instance | Tham số khi thay đổi cấu hình hoặc plan |
| **schemas.service_binding.create.parameters** | Create service binding | Tham số riêng khi tạo binding |

Một plan có thể công bố một, nhiều hoặc không công bố các schema này, tùy khả năng và nhu cầu của broker. Nếu không có schema cho một thao tác, platform có thể không dựng được biểu mẫu chi tiết từ catalog; broker vẫn cần xác định hành vi khi nhận parameters.

Sơ đồ cấu trúc rút gọn:

~~~text
Catalog
└── services[]
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
~~~

Schema nằm bên trong plan. Không nên đặt một schema chung ở cấp service rồi giả định mọi plan đều có cùng tham số. Ví dụ, plan **small** có thể cho phép dung lượng từ 10 đến 50 GB, còn plan **enterprise** có thể cho phép từ 100 đến 2.000 GB và thêm chính sách backup nâng cao.

## 2. Phân biệt parameters với các trường khác của OSB request

Trong request OSB, parameters chỉ là một phần của payload. Những trường như service ID, plan ID, context và định danh instance có vai trò riêng.

| Thành phần | Nguồn và mục đích | Có được mô tả bằng schema parameters không? |
|---|---|---|
| **service_id** | Định danh service offering trong catalog | Không |
| **plan_id** | Định danh plan được platform lựa chọn | Không |
| **context** | Ngữ cảnh platform, tenant, organization hoặc namespace | Không |
| **parameters** | Các tùy chọn cấu hình do người dùng hoặc client cung cấp | Có |
| **instance_id** | Định danh service instance trong URL | Không |
| **binding_id** | Định danh binding trong URL | Không |
| **credentials** | Thông tin kết nối do broker trả về sau khi bind | Không |

Ví dụ một request provision:

~~~http
PUT /v2/service_instances/instance-7f3a?accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-small",
  "context": {
    "platform": "kubernetes",
    "namespace": "payments"
  },
  "parameters": {
    "storage_gb": 20,
    "database_name": "payment_db",
    "backup_enabled": true
  }
}
~~~

Schema được khai báo trong catalog cho thao tác create sẽ mô tả đối tượng **parameters** gồm storage_gb, database_name và backup_enabled. Schema không mô tả service_id, plan_id, context hoặc query parameter accepts_incomplete.

Sự phân biệt này giúp broker tổ chức validation thành hai lớp: kiểm tra cấu trúc request OSB và kiểm tra dữ liệu cấu hình theo schema của plan. Sau đó, application service còn có thể thực hiện kiểm tra nghiệp vụ sâu hơn.

## 3. Một schema provision hoàn chỉnh

Giả sử broker cung cấp PostgreSQL với plan nhỏ. Người dùng được chọn dung lượng lưu trữ, tên database, vùng triển khai và chính sách backup.

Ví dụ catalog rút gọn:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "postgresql",
      "description": "Cơ sở dữ liệu PostgreSQL được quản lý",
      "bindable": true,
      "plans": [
        {
          "id": "plan-small",
          "name": "small",
          "description": "PostgreSQL cho ứng dụng quy mô nhỏ",
          "schemas": {
            "service_instance": {
              "create": {
                "parameters": {
                  "type": "object",
                  "properties": {
                    "storage_gb": {
                      "type": "integer",
                      "title": "Dung lượng lưu trữ",
                      "description": "Dung lượng database tính bằng GB",
                      "minimum": 10,
                      "maximum": 50,
                      "default": 20
                    },
                    "database_name": {
                      "type": "string",
                      "title": "Tên database",
                      "minLength": 1,
                      "maxLength": 40,
                      "pattern": "^[a-z][a-z0-9_]*$",
                      "description": "Bắt đầu bằng chữ thường; chỉ dùng chữ thường, số và dấu gạch dưới."
                    },
                    "region": {
                      "type": "string",
                      "enum": [
                        "ap-southeast-1",
                        "ap-southeast-2"
                      ]
                    },
                    "backup_enabled": {
                      "type": "boolean",
                      "default": true
                    }
                  },
                  "required": [
                    "storage_gb",
                    "database_name"
                  ],
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
~~~

Các ID trong ví dụ là giá trị minh họa. Trong hệ thống thật, service ID và plan ID phải ổn định để platform nhận diện cùng một offering qua nhiều lần tải catalog.

Các thuộc tính thường gặp trong JSON Schema có ý nghĩa như sau:

- **type** xác định kiểu dữ liệu, chẳng hạn object, string, integer, number, boolean hoặc array.
- **properties** mô tả các thuộc tính được phép có trong object.
- **required** liệt kê các thuộc tính phải xuất hiện.
- **minimum** và **maximum** giới hạn giá trị số.
- **minLength** và **maxLength** giới hạn độ dài chuỗi.
- **enum** giới hạn giá trị trong một tập lựa chọn.
- **pattern** áp dụng biểu thức chính quy cho chuỗi.
- **default** mô tả giá trị mặc định mà client có thể dùng khi người dùng bỏ trống.
- **additionalProperties** quy định có cho phép thuộc tính ngoài danh sách hay không.
- **title** và **description** cung cấp nhãn và hướng dẫn cho giao diện.

Khi người dùng nhập storage_gb bằng 80, schema báo giá trị vượt quá mức tối đa của plan nhỏ. Khi nhập database_name có dấu cách hoặc ký tự viết hoa, pattern không thỏa mãn. Khi gửi thêm debug_mode nhưng schema đặt additionalProperties là false, validator sẽ từ chối thuộc tính ngoài hợp đồng.

Không phải mọi giao diện platform đều hiển thị mọi keyword JSON Schema. title, description, enum và giới hạn số thường hữu ích cho biểu mẫu; broker vẫn phải validate dữ liệu thực nhận, kể cả khi platform không hỗ trợ một keyword nào đó.

## 4. Required, default và additionalProperties

Ba nhóm keyword này thường gây nhầm lẫn khi thiết kế schema.

### 4.1. required kiểm tra sự hiện diện

required áp dụng cho object hiện tại. Nếu schema có:

~~~json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer"
    },
    "database_name": {
      "type": "string"
    }
  },
  "required": [
    "storage_gb",
    "database_name"
  ]
}
~~~

thì cả hai thuộc tính phải có mặt. Giá trị null không tự động được coi là hợp lệ; nếu muốn cho phép null, schema phải mô tả rõ kiểu dữ liệu phù hợp theo dialect JSON Schema đang sử dụng.

Cũng cần phân biệt trường parameters của request với các trường bên trong parameters. Nếu schema có required gồm storage_gb, điều đó yêu cầu object parameters phải có storage_gb. Nó không tự động quyết định broker xử lý thế nào khi toàn bộ trường parameters bị bỏ qua. Quy tắc đó cần được xác định trong hợp đồng API và logic nghiệp vụ.

### 4.2. default là gợi ý, không phải lệnh cấp phát

Trong JSON Schema, default là metadata mô tả giá trị mặc định. Không nên giả định mọi JSON Schema validator sẽ tự chèn giá trị này vào object đầu vào.

Ví dụ:

~~~json
{
  "backup_enabled": {
    "type": "boolean",
    "default": true
  }
}
~~~

Nếu người dùng không gửi backup_enabled, broker phải có chính sách rõ ràng: áp dụng mặc định ở application service, lấy mặc định từ cấu hình plan hoặc yêu cầu người dùng gửi giá trị. Cần bảo đảm giá trị được hiển thị trong catalog khớp với hành vi thực tế khi provision.

Nếu người dùng gửi backup_enabled bằng false, broker không được thay bằng true chỉ vì schema có default. Giá trị do caller cung cấp phải được xử lý theo quy tắc validation và plan.

### 4.3. additionalProperties kiểm soát trường ngoài hợp đồng

Nếu đặt:

~~~json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer"
    }
  },
  "additionalProperties": false
}
~~~

thì object chỉ được có các thuộc tính đã khai báo. Điều này giúp phát hiện lỗi đánh máy và tránh người dùng gửi cấu hình không được hỗ trợ.

Nếu để mặc định hoặc đặt additionalProperties là true, schema có thể chấp nhận thuộc tính chưa biết. Cách này linh hoạt hơn khi mở rộng nhưng có thể che giấu lỗi chính tả. Lựa chọn cần dựa trên chiến lược tương thích: nếu muốn từ chối rõ ràng mọi field lạ, dùng false; nếu cần mở rộng có kiểm soát, hãy định nghĩa quy tắc cho các field mở rộng.

Không nên âm thầm bỏ qua tham số không được hỗ trợ khi nó có thể làm thay đổi kỳ vọng của người dùng. Nếu một phiên bản broker không hiểu field mới, response lỗi có mô tả thường an toàn hơn việc provision với cấu hình thiếu.

## 5. Schema cho update service instance

Tham số khi tạo instance thường khác tham số khi cập nhật. OSB catalog cho phép plan mô tả schema riêng tại **schemas.service_instance.update.parameters**.

Ví dụ plan cho phép thay đổi dung lượng và bật/tắt backup:

~~~json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 10,
              "maximum": 50
            },
            "backup_enabled": {
              "type": "boolean"
            }
          },
          "required": [
            "storage_gb"
          ],
          "additionalProperties": false
        }
      },
      "update": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 10,
              "maximum": 100
            },
            "backup_enabled": {
              "type": "boolean"
            }
          },
          "additionalProperties": false
        }
      }
    }
  }
}
~~~

Schema create và update có thể khác nhau. Ví dụ, create giới hạn tối đa 50 GB cho plan nhỏ, trong khi update có thể cho phép tăng đến 100 GB nếu broker hỗ trợ mở rộng tại chỗ. Một số thay đổi như vùng triển khai hoặc engine version có thể chỉ được chọn lúc tạo vì không thể chuyển đổi an toàn sau đó.

Update request sử dụng endpoint:

~~~http
PATCH /v2/service_instances/{instance_id}
~~~

Payload có trường parameters theo schema update của plan. Vì đây là thao tác cập nhật, broker cần phân biệt:

- Thuộc tính không xuất hiện: caller không yêu cầu thay đổi thuộc tính đó.
- Thuộc tính xuất hiện với giá trị mới: áp dụng thay đổi nếu plan và provider cho phép.
- Thuộc tính xuất hiện với giá trị null: chỉ chấp nhận nếu schema và quy tắc nghiệp vụ định nghĩa rõ ý nghĩa.
- Object rỗng: có thể là không có thay đổi; không tự diễn giải thành reset toàn bộ cấu hình.

Schema chỉ kiểm tra hình dạng và giới hạn dữ liệu. Application service phải kiểm tra trạng thái instance hiện tại, khả năng cập nhật của plan, quota và điều kiện chuyển đổi. Ví dụ, tăng dung lượng có thể hợp lệ nhưng giảm dung lượng dưới mức đã sử dụng có thể không được phép.

## 6. Schema cho service binding

Một binding có thể cần tham số riêng. Ví dụ, người dùng muốn tạo một database user chỉ có quyền đọc hoặc một user có quyền đọc ghi. Tham số này thuộc schema:

**schemas.service_binding.create.parameters**

Ví dụ:

~~~json
{
  "schemas": {
    "service_binding": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "role": {
              "type": "string",
              "enum": [
                "read_only",
                "read_write"
              ],
              "default": "read_write",
              "description": "Quyền của tài khoản ứng dụng."
            },
            "connection_limit": {
              "type": "integer",
              "minimum": 1,
              "maximum": 20,
              "default": 5
            }
          },
          "additionalProperties": false
        }
      }
    }
  }
}
~~~

Platform có thể dùng schema này để hỏi người dùng quyền truy cập mong muốn cho từng binding. Khi nhận bind request, broker validate parameters rồi yêu cầu provider tạo credential đúng phạm vi.

Cần phân biệt tham số đầu vào binding với credentials đầu ra:

| Dữ liệu | Hướng truyền | Ví dụ |
|---|---|---|
| Binding parameters | Platform gửi đến broker | role, connection_limit |
| Binding credentials | Broker trả về platform | hostname, port, username, password |

Không đặt password do broker sinh ra trong schema input. Schema không phải nơi lưu secret, và catalog thường được nhiều người dùng platform truy cập. Nếu một sản phẩm có nhu cầu nhận secret do người dùng cung cấp làm input, phải cân nhắc kỹ việc bảo vệ trong UI, request, log, persistence và audit; không được đưa giá trị bí mật thực vào catalog.

## 7. Một plan, nhiều schema theo thao tác

Một plan có thể có schema cho create, update và binding. Các schema có thể chia sẻ một số quy tắc nhưng không nhất thiết giống nhau.

Ví dụ tổng hợp:

~~~json
{
  "id": "plan-standard",
  "name": "standard",
  "description": "PostgreSQL cho ứng dụng production",
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 20,
              "maximum": 500
            },
            "region": {
              "type": "string",
              "enum": [
                "ap-southeast-1",
                "ap-southeast-2"
              ]
            },
            "backup_enabled": {
              "type": "boolean",
              "default": true
            }
          },
          "required": [
            "storage_gb",
            "region"
          ],
          "additionalProperties": false
        }
      },
      "update": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 20,
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
          "type": "object",
          "properties": {
            "role": {
              "type": "string",
              "enum": [
                "read_only",
                "read_write"
              ]
            }
          },
          "required": [
            "role"
          ],
          "additionalProperties": false
        }
      }
    }
  }
}
~~~

Từ ví dụ này, platform biết:

- Khi provision, người dùng phải chọn dung lượng và vùng triển khai.
- Khi update, người dùng có thể thay đổi dung lượng và backup.
- Khi bind, người dùng phải chọn quyền của tài khoản ứng dụng.

Broker vẫn phải kiểm tra khả năng thực tế của provider. Một schema hợp lệ chỉ nói dữ liệu đúng hình dạng; nó không chứng minh rằng vùng triển khai còn quota, tài nguyên đang sẵn sàng hoặc user có thể được tạo.

## 8. Validation ở platform và validation ở broker

Catalog schema có thể giúp platform xây dựng giao diện nhập liệu, nhưng platform không phải ranh giới tin cậy duy nhất. Broker phải xác thực lại mọi request.

Có thể chia validation thành các lớp:

| Lớp | Ví dụ kiểm tra | Thành phần chịu trách nhiệm |
|---|---|---|
| JSON parsing | Body là JSON hợp lệ, object đúng cấu trúc | HTTP/serialization layer |
| JSON Schema | Kiểu dữ liệu, required, enum, min/max, pattern | Schema validator trong broker |
| Catalog consistency | Service ID và plan ID có tồn tại, schema thuộc đúng plan | Catalog/application service |
| Authorization | Caller có quyền thao tác trên instance hoặc binding | Security/domain policy |
| Business validation | Quota, trạng thái instance, khả năng mở rộng, region còn hỗ trợ | Application service |
| Provider validation | Provider có chấp nhận cấu hình và có tài nguyên hay không | Provider adapter |

Ví dụ, storage_gb bằng 40 có thể vượt qua schema của plan. Tuy nhiên, nếu tenant đã dùng hết quota, broker vẫn phải từ chối ở lớp nghiệp vụ. Nếu provider không còn capacity tại region đã chọn, adapter phải trả lỗi phù hợp để application service chuyển thành response OSB.

### 8.1. Không chỉ kiểm tra kiểu dữ liệu

JSON Schema có thể kiểm tra kiểu, giới hạn và một số quan hệ cấu trúc. Các quy tắc như sau thường cần logic nghiệp vụ:

- storage_gb không được nhỏ hơn dung lượng dữ liệu hiện tại.
- Region chỉ được phép với tenant có quyền triển khai tại region đó.
- backup_enabled bắt buộc là true đối với dữ liệu thuộc chính sách nhất định.
- Một plan không được chuyển sang plan khác khi instance đang migration.
- Số binding active không được vượt giới hạn của plan.

Có thể kết hợp schema validation với validator nghiệp vụ. Không nên cố nhồi toàn bộ logic provider vào một JSON Schema phức tạp; schema nên mô tả hợp đồng input mà platform có thể hiểu, còn các quy tắc động được kiểm tra trong application service.

### 8.2. Giá trị thiếu, null và kiểu không đúng

Cần xác định rõ ba trường hợp:

- Không gửi thuộc tính.
- Gửi thuộc tính với giá trị null.
- Gửi thuộc tính với kiểu dữ liệu sai.

Ví dụ, storage_gb không gửi có thể vi phạm required. Giá trị "20" là chuỗi, không phải số nguyên nếu schema yêu cầu integer. Giá trị null cũng không hợp lệ trừ khi schema cho phép. Không nên tự động ép chuỗi thành số nếu điều đó làm thay đổi hợp đồng hoặc che giấu lỗi client.

## 9. Ánh xạ JSON Schema vào Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp mô hình catalog để broker công bố service definitions, plans và schema. Tùy phiên bản thư viện, các model thường được tổ chức quanh các khái niệm như Catalog, ServiceDefinition, Plan, Schemas, ServiceInstanceSchema và ServiceBindingSchema.

Một kiến trúc triển khai nên tách ba trách nhiệm:

1. **Catalog provider:** tạo catalog nhất quán và gắn schema phù hợp với từng plan.
2. **Parameter validator:** validate object parameters theo schema được chọn từ catalog.
3. **Application service:** kiểm tra quy tắc nghiệp vụ và điều phối provider adapter.

Không nên để schema chỉ tồn tại trong tài liệu hoặc UI. Catalog response và server-side validator cần dùng cùng một nguồn định nghĩa hoặc cùng một bộ quy tắc để tránh drift.

Sơ đồ luồng:

~~~mermaid
flowchart TD
    A["Broker Catalog Service"] --> B["Service offering và plan"]
    B --> C["Schemas: create / update / binding"]
    C --> D["GET /v2/catalog"]
    D --> E["Platform hiển thị form tham số"]
    E --> F["Request parameters"]
    F --> G["Broker API"]
    G --> H["Chọn schema theo service, plan và operation"]
    H --> I["JSON Schema validation"]
    I --> J{"Hợp lệ?"}
    J -->|Không| K["OSB error response"]
    J -->|Có| L["Business validation"]
    L --> M["Application service"]
    M --> N["Provider adapter"]
~~~

Khi catalog được cấu hình tĩnh, cần bảo đảm mọi instance broker trả cùng service ID, plan ID và schema. Nếu catalog được sinh động theo tenant hoặc môi trường, phải bảo đảm platform không nhận một schema rồi gửi request tới broker instance có catalog khác.

### 9.1. Mô hình catalog trong Spring

Với Spring Cloud Open Service Broker, catalog thường được cung cấp qua implementation của CatalogService hoặc cấu hình catalog theo cách thư viện hỗ trợ ở phiên bản đang dùng. Mỗi Plan gắn với offering có thể mang Schemas tương ứng.

Các model schema có thể biểu diễn:

- Schema create/update cho service instance.
- Schema create cho service binding.
- JSON Schema cho object parameters của từng operation.

Tên constructor, builder và cách đăng ký bean có thể thay đổi theo phiên bản thư viện. Vì vậy, hãy đối chiếu API model của dependency đang sử dụng, nhưng giữ nguyên cấu trúc dữ liệu OSB trong response catalog.

### 9.2. Chọn schema đúng theo request

Khi nhận request, broker cần xác định operation trước khi validate:

| Operation | Schema được chọn |
|---|---|
| Provision | service_instance.create.parameters |
| Update | service_instance.update.parameters |
| Bind | service_binding.create.parameters |

Không validate provision bằng schema update chỉ vì cả hai đều có trường storage_gb. Không validate binding bằng schema instance create. Cùng tên thuộc tính có thể có ý nghĩa và giới hạn khác nhau theo operation.

Nếu schema không được công bố hoặc không có validator tương ứng, broker phải áp dụng chính sách đã định nghĩa cho trường hợp đó. Không được tự hiểu rằng thiếu schema có nghĩa mọi input đều an toàn.

## 10. Ví dụ validator ở tầng nghiệp vụ

Giả sử broker nhận parameters dưới dạng JSON object. Một cách tiếp cận là dùng JSON Schema validator để kiểm tra cấu trúc trước, sau đó map dữ liệu đã hợp lệ thành command có kiểu rõ ràng.

Pseudocode Java minh họa:

~~~java
public ProvisionCommand toProvisionCommand(
        String serviceId,
        String planId,
        JsonNode parameters,
        PlatformContext context) {

    PlanDefinition plan = catalog.requirePlan(serviceId, planId);

    schemaValidator.validate(
        plan.instanceCreateSchema(),
        parameters
    );

    int storageGb = parameters.path("storage_gb").asInt();
    String databaseName = parameters.path("database_name").asText();

    businessPolicy.requireStorageWithinTenantQuota(context, storageGb);
    businessPolicy.requireDatabaseNameAvailable(context, databaseName);

    return new ProvisionCommand(
        serviceId,
        planId,
        storageGb,
        databaseName,
        context
    );
}
~~~

Đây là pseudocode thể hiện thứ tự trách nhiệm; schemaValidator, PlanDefinition và businessPolicy là abstraction của ứng dụng, không phải API cố định của Spring Cloud Open Service Broker.

Sau khi command được tạo, lifecycle coordinator có thể thực hiện provision đồng bộ hoặc tạo operation bất đồng bộ. Schema validation nên hoàn tất trước khi ghi nhận một operation cấp phát, để request sai không tạo ra job nền vô ích.

Nếu validation thất bại, broker trả lỗi theo hợp đồng OSB. Nội dung lỗi nên chỉ ra đường dẫn thuộc tính và quy tắc bị vi phạm, ví dụ parameters.storage_gb phải nhỏ hơn hoặc bằng 50. Không đưa stack trace, SQL, credential hoặc chi tiết provider vào error description.

## 11. Versioning schema và tương thích ngược

Schema được platform tải qua catalog, có thể được cache trong một khoảng thời gian. Vì vậy, thay đổi schema là thay đổi hợp đồng input và cần có chiến lược tương thích.

Một số thay đổi thường ít gây phá vỡ:

- Thêm thuộc tính tùy chọn với hành vi mặc định rõ ràng.
- Thêm mô tả hoặc title.
- Mở rộng enum khi mọi consumer liên quan có thể xử lý giá trị mới.
- Nới giới hạn số hoặc độ dài nếu provider và plan cho phép.

Một số thay đổi có nguy cơ phá vỡ:

- Thêm field vào required.
- Đổi kiểu dữ liệu từ integer sang string.
- Xóa thuộc tính đang được sử dụng.
- Thu hẹp enum, minimum, maximum hoặc pattern.
- Đặt additionalProperties thành false trong khi trước đó client gửi các field mở rộng.
- Thay đổi ý nghĩa của default hoặc cách broker xử lý field bị bỏ qua.

Khi thay đổi schema, cần xem xét cả catalog cache và các request đang chạy. Platform có thể vẫn gửi parameters theo schema cũ sau khi broker đã triển khai phiên bản mới. Một chiến lược an toàn là duy trì khả năng xử lý tương thích trong thời gian chuyển tiếp, hoặc phát hành plan/version mới nếu thay đổi không thể tương thích.

Không nên thay đổi ý nghĩa của một plan ID đã được platform sử dụng mà không có kế hoạch migration. Plan ID ổn định là định danh hợp đồng; nếu cấu hình hoặc giới hạn thay đổi, broker cần xác định ảnh hưởng tới các instance đã được provision từ plan đó.

## 12. Bảo mật và dữ liệu nhạy cảm trong parameters

Parameters là dữ liệu do client gửi, nên phải được xem là input không đáng tin cậy. Một schema hợp lệ không có nghĩa dữ liệu an toàn để đưa thẳng vào SQL, shell command, tên tài nguyên hoặc URL.

Các nguyên tắc quan trọng:

- Giới hạn kích thước request và độ sâu JSON để tránh payload quá lớn hoặc cấu trúc gây quá tải.
- Validate kiểu, giới hạn, enum và pattern trước khi xử lý.
- Không ghép trực tiếp input vào SQL hoặc command line; dùng parameterized query và API có kiểu.
- Escape hoặc encode dữ liệu theo đúng ngữ cảnh khi đưa vào cấu hình hoặc log.
- Không log toàn bộ parameters nếu có khả năng chứa token, password, khóa hoặc dữ liệu cá nhân.
- Phân quyền theo tenant và context trước khi sử dụng tham số ảnh hưởng đến vùng triển khai hoặc tài nguyên.
- Không để schema catalog tiết lộ thông tin hạ tầng nội bộ hoặc secret.
- Lưu parameters cần thiết để phục hồi operation theo chính sách tối thiểu hóa dữ liệu và mã hóa phù hợp.

Nếu một parameter nhạy cảm là bắt buộc, hãy cân nhắc cơ chế secret input mà platform hỗ trợ. Không dựa vào việc ẩn field trong giao diện như một biện pháp bảo mật. Request vẫn phải được xác thực, truyền qua TLS, kiểm soát quyền truy cập và làm sạch khỏi log.

## 13. Kiểm thử schema và contract

Kiểm thử nên xác nhận cả schema được công bố lẫn cách broker thực sự xử lý request.

| Nhóm kiểm thử | Trường hợp cần xác minh |
|---|---|
| Catalog | Schema xuất hiện đúng trong plan và đúng operation |
| Kiểu dữ liệu | String gửi vào field integer bị từ chối |
| Required | Thiếu field bắt buộc bị từ chối |
| Numeric range | Giá trị dưới minimum hoặc trên maximum bị từ chối |
| Enum | Giá trị ngoài danh sách bị từ chối |
| Pattern/length | Chuỗi sai định dạng hoặc quá dài bị từ chối |
| Additional properties | Field lạ được xử lý đúng theo cấu hình |
| Defaults | Field bị bỏ qua được áp dụng theo chính sách mặc định |
| Update | Chỉ thay đổi các field được phép và giữ nguyên field không gửi |
| Binding | Binding parameters được validate theo schema riêng |
| Business rules | Dữ liệu hợp lệ theo schema nhưng vượt quota vẫn bị từ chối |
| Security | Input độc hại không được đưa trực tiếp vào SQL, shell hoặc log |
| Compatibility | Request theo schema cũ được xử lý theo chính sách chuyển tiếp |

Ví dụ một tập ca kiểm thử cho schema plan nhỏ:

~~~text
storage_gb = 20                         -> hợp lệ
storage_gb = 80                         -> vượt maximum
storage_gb = "20"                       -> sai kiểu
database_name = "payment_db"            -> hợp lệ
database_name = "Payment DB"            -> sai pattern
database_name bị bỏ qua                 -> thiếu required
unknown_option = true                   -> bị từ chối nếu additionalProperties=false
backup_enabled bị bỏ qua                -> áp dụng default theo business policy
~~~

Ngoài unit test cho validator, nên có contract test kiểm tra response GET /v2/catalog. Test này bảo đảm schema được serialize đúng cấu trúc OSB và platform có thể nhận được các schema mà broker tuyên bố hỗ trợ.

## 14. Quy trình thiết kế schema cho một service plan

Khi bổ sung một plan mới, nhóm phát triển có thể đi theo quy trình sau:

1. Xác định các thao tác nhận input: create instance, update instance và create binding.
2. Liệt kê field người dùng có thể cấu hình ở từng thao tác.
3. Với mỗi field, xác định kiểu, bắt buộc/tùy chọn, miền giá trị, default và mức nhạy cảm.
4. Viết JSON Schema ở đúng nhánh của plan.
5. Xác định chính sách cho parameters bị thiếu, object rỗng, null và field không biết.
6. Triển khai server-side validation theo cùng nguồn quy tắc.
7. Bổ sung business validation cho quota, ownership, trạng thái instance và khả năng provider.
8. Viết contract test cho catalog và test validation cho request.
9. Đánh giá tác động tương thích trước khi thay đổi schema đang được platform sử dụng.
10. Ghi lại hành vi mặc định và lỗi validation để đội vận hành có thể hỗ trợ người dùng.

Có thể dùng bảng quyết định sau khi review:

| Câu hỏi | Quyết định cần ghi nhận |
|---|---|
| Schema thuộc thao tác nào? | Create, update hay binding create |
| Schema nằm trong plan nào? | Plan ID và offering ID |
| Field nào bắt buộc? | Danh sách required |
| Field nào có default? | Giá trị và nơi áp dụng default |
| Có chấp nhận field lạ không? | Chính sách additionalProperties |
| Có dữ liệu nhạy cảm không? | Phương thức truyền, lưu và log |
| Có quy tắc động không? | Business validator và provider check |
| Có phá vỡ client cũ không? | Kế hoạch versioning/transition |

Khi JSON Schema được đặt đúng vị trí trong catalog, mô tả rõ tham số của từng thao tác và được dùng nhất quán với validation phía broker, platform có thể giúp người dùng nhập cấu hình chính xác hơn. Broker vẫn giữ quyền kiểm soát cuối cùng đối với dữ liệu, quota, quyền truy cập và khả năng của provider. Điều đó tạo ra một hợp đồng input rõ ràng, dễ kiểm thử và ổn định cho các service plan trong Spring Cloud Service Broker.
