# Metadata, labels và thuộc tính mở rộng theo phiên bản hỗ trợ

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker công bố catalog và quản lý vòng đời service instance, binding theo Open Service Broker API (OSB API). Ngoài các định danh và trường cấu hình cốt lõi, catalog còn có metadata, tags, requires, schemas và một số thuộc tính capability. Các trường này giúp platform phân loại dịch vụ, hiển thị thông tin cho người dùng, kiểm tra khả năng tích hợp và quyết định endpoint truy xuất nào có thể sử dụng.

Khi platform cần khôi phục trạng thái sau restart hoặc đồng bộ lại tài nguyên, broker còn có thể công bố khả năng truy xuất service instance và binding. Hai việc cần được phân biệt: metadata trong catalog mô tả offering/plan mà broker cung cấp; retrieval endpoint trả trạng thái của một instance hoặc binding cụ thể. Metadata không thay thế dữ liệu vòng đời, và một trường mở rộng chỉ có ý nghĩa khi cả broker lẫn platform hiểu cách sử dụng nó.

Bài học này hướng dẫn cách phân biệt tags, metadata và các thuộc tính mở rộng; cách công bố capability truy xuất; cách xử lý trường phụ thuộc phiên bản OSB API; và cách tổ chức dữ liệu trong Spring Cloud Service Broker để tương thích với nhiều platform.

## 1. Các lớp dữ liệu trong OSB API

OSB API có nhiều cấp dữ liệu. Trước khi thiết kế metadata, cần xác định dữ liệu thuộc service offering, plan, instance hay binding.

| Cấp dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Service offering | Mô tả một loại dịch vụ mà broker cung cấp | PostgreSQL, Redis, RabbitMQ |
| Service plan | Mô tả cấp dịch vụ hoặc cấu hình có thể chọn | small, standard, enterprise |
| Service instance | Một tài nguyên đã được provision theo offering và plan | Database orders của tenant A |
| Service binding | Một quan hệ truy cập giữa instance và consumer | Credential của billing-api |
| Operation | Một lần provision, update hoặc deprovision đang được theo dõi | Operation nâng cấp database |

Catalog mô tả service offering và plan. Nó có thể chứa tên, mô tả, tags, metadata, yêu cầu platform, schema và capability flags. Catalog không phải nơi lưu trạng thái từng instance hoặc credentials đang hoạt động.

Service instance và binding được quản lý bằng các endpoint vòng đời. Nếu broker công bố capability retrieval, platform có thể gọi GET để lấy lại thông tin của tài nguyên đã tồn tại. Vì vậy, nên thiết kế model riêng cho catalog metadata, instance state và binding state, dù chúng có thể cùng được lưu trong một database.

## 2. Tags là nhãn phân loại dịch vụ

Trường **tags** trong service definition là danh sách chuỗi dùng để phân loại hoặc hỗ trợ platform tìm kiếm offering. Tags nên ngắn gọn, ổn định và có ý nghĩa với người dùng hoặc giao diện marketplace.

Ví dụ:

~~~json
{
  "id": "service-postgresql",
  "name": "postgresql",
  "description": "Managed PostgreSQL database",
  "bindable": true,
  "tags": [
    "relational",
    "sql",
    "database",
    "postgresql"
  ],
  "plans": []
}
~~~

Tags có thể giúp platform nhóm các dịch vụ theo loại công nghệ hoặc công dụng. Một số ví dụ:

| Nhóm dịch vụ | Tags gợi ý |
|---|---|
| PostgreSQL | relational, sql, database |
| Redis | cache, key-value, in-memory |
| RabbitMQ | messaging, amqp, queue |
| Object storage | object-storage, blob, files |
| Search engine | search, indexing, analytics |

Tags không phải cơ chế phân quyền. Không dùng tag như private, internal hoặc admin để quyết định ai được phép provision dịch vụ. Authorization phải dựa trên danh tính caller, tenant context và policy phía broker/platform.

Không nên đưa vào tags các thông tin thay đổi thường xuyên như trạng thái instance, số lượng kết nối hiện tại hoặc quota còn lại. Những dữ liệu này không mô tả bản chất offering và sẽ khiến catalog trở nên khó cache hoặc không nhất quán.

## 3. Metadata cung cấp thông tin hiển thị và thuộc tính mở rộng

Trường **metadata** là object chứa thông tin bổ sung. Trong catalog, metadata thường giúp platform hiển thị service hoặc plan trong marketplace. OSB API quy định một số quy ước metadata phổ biến, nhưng các giá trị bổ sung có thể phụ thuộc platform và broker.

Ví dụ service metadata:

~~~json
{
  "id": "service-postgresql",
  "name": "postgresql",
  "description": "Managed PostgreSQL database",
  "metadata": {
    "displayName": "PostgreSQL",
    "imageUrl": "https://assets.example.invalid/postgresql.png",
    "longDescription": "Cơ sở dữ liệu quan hệ được quản lý cho ứng dụng.",
    "providerDisplayName": "Example Platform",
    "documentationUrl": "https://docs.example.invalid/postgresql",
    "supportUrl": "https://support.example.invalid",
    "bullets": [
      "Tự động sao lưu",
      "Mã hóa kết nối",
      "Theo dõi hiệu năng"
    ]
  },
  "plans": []
}
~~~

Các URL trong ví dụ dùng miền minh họa. Khi triển khai thật, chỉ công bố URL đã được kiểm soát và có thể truy cập từ môi trường platform.

Metadata thường được dùng để trình bày thông tin. Platform có thể hiển thị một số key quen thuộc, bỏ qua key không biết hoặc dùng metadata theo quy ước riêng. Do đó, broker không nên giả định mọi platform đều render mọi thuộc tính giống nhau.

### 3.1. Các metadata key thường gặp

| Key | Ý nghĩa |
|---|---|
| **displayName** | Tên thân thiện để hiển thị |
| **imageUrl** | URL ảnh hoặc biểu tượng dịch vụ |
| **longDescription** | Mô tả dài hơn description cơ bản |
| **providerDisplayName** | Tên nhà cung cấp hiển thị |
| **documentationUrl** | Đường dẫn tài liệu hướng dẫn |
| **supportUrl** | Đường dẫn hỗ trợ |
| **bullets** | Danh sách điểm nổi bật |
| **costs** | Thông tin chi phí theo quy ước mà platform hỗ trợ |

Các key trên phục vụ hiển thị và discovery. Không đưa password, API key, connection string, địa chỉ quản trị nội bộ hoặc dữ liệu cá nhân vào metadata. Catalog có thể được đọc bởi nhiều người dùng platform; metadata không phải secret store.

### 3.2. Metadata ở service và plan

Service metadata mô tả offering nói chung, ví dụ tên nhà cung cấp, hình ảnh, mô tả dài và tài liệu. Plan metadata mô tả điểm khác biệt của một cấp dịch vụ, ví dụ số lượng tính năng, mức hỗ trợ hoặc chi phí.

Ví dụ:

~~~json
{
  "id": "plan-standard",
  "name": "standard",
  "description": "Plan dành cho ứng dụng production",
  "metadata": {
    "displayName": "Standard",
    "bullets": [
      "Dung lượng lớn hơn",
      "Backup tự động",
      "Hỗ trợ production"
    ],
    "costs": [
      {
        "amount": {
          "usd": 49
        },
        "unit": "MONTHLY"
      }
    ]
  }
}
~~~

Metadata chi phí cần tuân theo cấu trúc mà OSB API và platform hỗ trợ. Không dùng metadata costs làm nguồn tính phí có thẩm quyền nếu hệ thống billing thực tế lấy giá từ một nguồn khác. Nếu giá thay đổi, catalog và hệ thống tính phí cần có quy trình đồng bộ.

### 3.3. Thuộc tính mở rộng do broker định nghĩa

Broker có thể cần công bố các thông tin đặc thù như engine family, compliance tier, vùng hỗ trợ hoặc loại endpoint. Trước khi thêm key riêng, cần xác định:

- Platform nào sẽ đọc key đó?
- Key có ổn định giữa các phiên bản catalog không?
- Giá trị có ảnh hưởng đến lựa chọn plan hoặc policy không?
- Nếu platform không hiểu key, có thể bỏ qua an toàn không?
- Key có vô tình tiết lộ cấu hình nội bộ hoặc thông tin nhạy cảm không?

Nên dùng namespace rõ ràng cho metadata riêng, chẳng hạn tên miền hoặc tiền tố thuộc tổ chức, để tránh xung đột với key chuẩn. Metadata mở rộng nên là dữ liệu mô tả; không dùng nó để thay thế các trường chuẩn như bindable, plan_updateable hoặc tags.

## 4. Phân biệt tags, metadata, requires và schemas

Các trường này đều cung cấp thông tin bổ sung nhưng có ý nghĩa khác nhau.

| Trường | Loại dữ liệu | Câu hỏi mà trường trả lời |
|---|---|---|
| **tags** | Danh sách nhãn | Dịch vụ thuộc nhóm nào? |
| **metadata** | Object mô tả và thuộc tính hiển thị | Người dùng cần biết thêm điều gì về dịch vụ/plan? |
| **requires** | Danh sách khả năng platform cần có | Platform cần hỗ trợ tính năng nào để cung cấp dịch vụ? |
| **schemas** | JSON Schema cho parameters | Người dùng có thể nhập cấu hình nào? |
| **capability flags** | Boolean hoặc thuộc tính hợp đồng | Broker có hỗ trợ một thao tác hay khả năng cụ thể không? |

Ví dụ, tags có thể chứa database và relational; metadata có thể chứa displayName và documentationUrl; requires có thể cho biết service cần volume mount; schemas mô tả parameters; bindable và instances_retrievable thể hiện capability.

Không nên thay một trường chuẩn bằng metadata tùy chỉnh. Nếu broker hỗ trợ binding, hãy dùng bindable theo hợp đồng. Nếu broker hỗ trợ retrieval, hãy công bố capability retrieval tương ứng. Metadata có thể bổ sung cách trình bày, nhưng platform không nên phải phân tích một key riêng để hiểu hành vi chuẩn.

## 5. requires mô tả tính năng platform cần hỗ trợ

Trường **requires** là danh sách các capability mà platform cần có để cung cấp service offering. Các giá trị thường gặp trong OSB API gồm:

- **syslog_drain**: platform có thể nhận và chuyển tiếp log theo cơ chế syslog drain.
- **route_forwarding**: platform hỗ trợ chuyển tiếp route hoặc traffic theo mô hình route service.
- **volume_mount**: platform hỗ trợ gắn volume vào workload.

Ví dụ:

~~~json
{
  "id": "service-log-collector",
  "name": "log-collector",
  "description": "Dịch vụ thu thập log",
  "requires": [
    "syslog_drain"
  ],
  "bindable": true,
  "plans": []
}
~~~

Broker công bố yêu cầu; platform quyết định offering có phù hợp với khả năng của nó hay không. Nếu platform không hỗ trợ capability được yêu cầu, nó có thể không hiển thị hoặc không cho phép người dùng tạo dịch vụ đó.

Không dùng requires như danh sách tính năng mà broker tự có. Nó mô tả điều kiện từ phía platform. Ví dụ, một broker có thể hỗ trợ route service nhưng platform triển khai không hỗ trợ route forwarding; việc broker có API nội bộ không khiến platform tự động đáp ứng capability.

## 6. schemas mô tả tham số đầu vào theo operation

Một plan có thể công bố JSON Schema cho các thao tác nhận parameters:

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
              "maximum": 500
            }
          },
          "required": [
            "storage_gb"
          ]
        }
      },
      "update": {
        "parameters": {
          "type": "object",
          "properties": {
            "backup_enabled": {
              "type": "boolean"
            }
          }
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
          }
        }
      }
    }
  }
}
~~~

Schema cho create instance, update instance và create binding có thể khác nhau. Platform dùng chúng để dựng biểu mẫu hoặc kiểm tra dữ liệu trước khi gửi. Broker vẫn phải validate lại request ở phía server và kiểm tra quota, authorization, trạng thái instance cũng như khả năng provider.

Schema không phải metadata hiển thị tùy ý. Nó là hợp đồng cấu trúc của parameters. Nếu thay đổi schema, cần xem xét compatibility với platform đang cache catalog và client đã gửi request theo phiên bản trước.

## 7. dashboard_client là thuộc tính riêng, không phải metadata tùy ý

Một service có thể công bố **dashboard_client** khi broker tích hợp dashboard với cơ chế đăng nhập hoặc chuyển hướng được OSB API hỗ trợ. Object này có các thông tin như client ID, secret và redirect URI theo hợp đồng tương ứng.

Không nên chuyển dashboard_client vào metadata tự định nghĩa chỉ để tiện serialize. Trường chuẩn giúp platform hiểu cấu trúc và cách sử dụng. Đồng thời, vì object có thể chứa secret, cần bảo vệ response catalog, quyền truy cập và log theo yêu cầu bảo mật của phiên bản API và platform.

Dashboard client cũng không giống dashboard URL của một instance. Dashboard client là thông tin tích hợp client; dashboard URL có thể là địa chỉ dashboard cụ thể gắn với instance hoặc kết quả retrieval nếu broker hỗ trợ.

## 8. maintenance_info mô tả phiên bản bảo trì của plan

Một số phiên bản OSB API hỗ trợ thuộc tính **maintenance_info** trên plan. Thuộc tính này có thể mô tả phiên bản bảo trì và nội dung liên quan để platform hiển thị hoặc điều phối việc cập nhật.

Ví dụ:

~~~json
{
  "id": "plan-standard",
  "name": "standard",
  "description": "Managed PostgreSQL",
  "maintenance_info": {
    "version": "14.8.3",
    "description": "Bản bảo trì PostgreSQL với cập nhật bảo mật và sửa lỗi."
  }
}
~~~

Thông tin này nên phản ánh phiên bản bảo trì mà broker thực sự quản lý. Không dùng maintenance_info để thay thế service plan ID hoặc tự biểu diễn mọi lần update cấu hình. Plan ID định danh cấp dịch vụ; maintenance_info mô tả phiên bản bảo trì theo semantics của OSB API.

Vì maintenance_info phụ thuộc phiên bản API được hỗ trợ, broker phải kiểm tra compatibility matrix trước khi serialize. Nếu thư viện hoặc platform đang dùng chưa hỗ trợ field đó, không nên giả định field sẽ được hiểu đúng chỉ vì JSON serializer cho phép thêm thuộc tính.

## 9. Capability retrieval cho service instance và binding

Ngoài catalog metadata, OSB API có các capability cho phép platform truy vấn trạng thái của tài nguyên đã được tạo.

Hai capability cần phân biệt:

| Capability | Ý nghĩa | Endpoint |
|---|---|---|
| **instances_retrievable** | Broker hỗ trợ truy xuất thông tin service instance | GET service instance |
| **bindings_retrievable** | Broker hỗ trợ truy xuất thông tin service binding | GET service binding |

Ví dụ service công bố:

~~~json
{
  "id": "service-postgresql",
  "name": "postgresql",
  "bindable": true,
  "instances_retrievable": true,
  "bindings_retrievable": true,
  "plans": []
}
~~~

Chỉ khai báo true nếu broker có thể trả dữ liệu retrieval nhất quán theo hợp đồng. Nếu capability false hoặc không được công bố, platform không nên giả định endpoint tương ứng có thể được sử dụng.

Retrieval hữu ích khi platform cần đồng bộ trạng thái sau khi controller restart, kiểm tra tài nguyên do broker quản lý hoặc khôi phục dữ liệu binding. GET retrieval phải là thao tác đọc; không được vô tình tạo lại credential, cập nhật plan hoặc gọi một lệnh provider có side effect.

## 10. Truy xuất service instance

Khi broker công bố instances_retrievable, platform có thể gọi endpoint GET service instance theo OSB API:

~~~http
GET /v2/service_instances/{instance_id}?service_id=service-postgresql&plan_id=plan-standard
X-Broker-API-Version: 2.17
~~~

Query parameters service_id và plan_id giúp broker nhận diện offering và plan mà platform đang truy vấn theo hợp đồng retrieval. Broker nên kiểm tra chúng khớp với dữ liệu instance đã lưu, không dùng query parameter để tự thay đổi service hoặc plan.

Response có thể chứa các thông tin theo schema retrieval của phiên bản API, ví dụ:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "dashboard_url": "https://dashboard.example.invalid/instances/instance-7f3a",
  "parameters": {
    "storage_gb": 100,
    "backup_enabled": true
  }
}
~~~

Các giá trị là minh họa. Broker chỉ trả các field được hợp đồng và phiên bản hỗ trợ. Không trả secret binding trong response service instance retrieval. Nếu cần hiển thị dashboard, URL phải được tạo hoặc lấy từ nguồn tin cậy, có kiểm tra quyền và không chứa credential nhạy cảm.

Retrieval response nên phản ánh cấu hình đang có hiệu lực. Nếu instance đang trong một update bất đồng bộ, broker cần có quy tắc rõ ràng về việc trả trạng thái hiện tại và các thông tin thuộc operation; không báo plan đích như đã áp dụng trước khi provider hoàn tất.

## 11. Truy xuất service binding

Khi broker công bố bindings_retrievable, platform có thể truy vấn một binding:

~~~http
GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}?service_id=service-postgresql&plan_id=plan-standard
X-Broker-API-Version: 2.17
~~~

Response có thể chứa các thuộc tính tương ứng với loại binding và khả năng của broker:

~~~json
{
  "credentials": {
    "hostname": "db.internal.example",
    "port": 5432,
    "database": "orders",
    "username": "orders_reader",
    "password": "example-secret"
  },
  "parameters": {
    "role": "read_only"
  }
}
~~~

Vì response có thể chứa credentials, endpoint cần được xác thực và phân quyền chặt chẽ. Broker phải xác minh binding thuộc instance trong path và caller có quyền truy xuất. Không dùng binding ID hoặc operation token như bằng chứng xác thực.

Nếu broker không thể khôi phục credentials đã tạo, cần xác định chính sách retrieval phù hợp. Một số provider không cho đọc lại password ở dạng rõ; broker có thể cần lưu secret an toàn hoặc thiết kế credential có thể tái tạo. Không trả credentials rỗng rồi coi retrieval thành công nếu platform cần chúng để khôi phục binding.

Các thuộc tính như syslog drain URL, route service URL hoặc volume mounts chỉ được trả khi binding và service hỗ trợ loại tài nguyên tương ứng theo hợp đồng. Không thêm các field riêng vào response nếu chưa có quy tắc tương thích.

## 12. Phân biệt metadata, parameters, context và retrieval data

Bốn nhóm dữ liệu này dễ bị gộp nhầm vì đều có thể biểu diễn bằng JSON object.

| Nhóm | Nơi xuất hiện | Mục đích | Ví dụ |
|---|---|---|---|
| Catalog metadata | Service hoặc plan trong catalog | Hiển thị và mô tả offering | displayName, documentationUrl, bullets |
| Parameters | Request provision/update/bind và schema tương ứng | Cấu hình do caller cung cấp | storage_gb, backup_enabled, role |
| Context | Request từ platform | Mô tả môi trường và phạm vi platform | organization, space, cluster, namespace |
| Retrieval data | Response GET instance/binding | Trạng thái hoặc dữ liệu hiện tại của tài nguyên | service_id, plan_id, parameters, credentials |

Không lưu credentials vào catalog metadata. Không dùng context làm nơi chứa thông tin cấu hình người dùng. Không đưa trạng thái instance động vào tags của service. Cũng không coi metadata mô tả là dữ liệu chuẩn để khôi phục tài nguyên.

## 13. Phiên bản OSB API và khả năng tương thích

OSB API sử dụng header **X-Broker-API-Version** để platform thông báo phiên bản giao thức mà nó sử dụng. Các field và capability có thể được bổ sung qua những phiên bản minor. Vì vậy, việc hỗ trợ một endpoint hoặc field phải được đánh giá theo phiên bản mà broker tuyên bố hỗ trợ.

Không nên giả định mọi platform đều dùng cùng minor version hoặc mọi phiên bản Spring Cloud Open Service Broker đều ánh xạ đầy đủ tất cả field mới. Cần duy trì một bảng tương thích nội bộ dựa trên phiên bản đặc tả và dependency thực tế.

Một ma trận có thể dùng khi review:

| Thành phần | Cần kiểm tra | Cách xử lý |
|---|---|---|
| tags và metadata | Cấu trúc service/plan có được thư viện serialize đúng không | Contract test catalog |
| requires | Giá trị capability có được platform hỗ trợ không | Kiểm tra tài liệu platform |
| schemas | JSON Schema có nằm đúng nhánh create/update/bind không | Kiểm tra response catalog và validation |
| dashboard_client | Model và bảo vệ secret có đúng phiên bản không | Kiểm tra dependency và security policy |
| maintenance_info | Phiên bản API và model có hỗ trợ field không | Chỉ công bố khi hai phía tương thích |
| instances_retrievable | Capability và GET endpoint có được hỗ trợ không | Test retrieval instance |
| bindings_retrievable | Capability và GET endpoint có được hỗ trợ không | Test retrieval binding |
| allow_context_updates | Platform và broker có hỗ trợ cập nhật context không | Chỉ bật khi semantics được triển khai |
| X-Broker-API-Version | Phiên bản request có nằm trong dải hỗ trợ không | Validate trên mọi request |

Bảng này là checklist tương thích, không phải khẳng định mọi field đều được giới thiệu cùng một minor version. Khi cần xác định chính xác phiên bản đầu tiên của một thuộc tính, phải đối chiếu đặc tả OSB API và phiên bản thư viện đang dùng. Không suy ra số phiên bản từ tên field hoặc từ khả năng serialize JSON.

### 13.1. Validate phiên bản ở lớp biên

Broker nên parse header phiên bản thành major/minor, kiểm tra dải được hỗ trợ và áp dụng quy tắc tương thích cho request. Không chỉ kiểm tra ở catalog rồi bỏ qua retrieval endpoints.

Ví dụ pseudocode:

~~~java
public void validateApiVersion(String header) {
    OsbApiVersion requested = OsbApiVersion.parse(header);

    if (!supportedVersions.contains(requested)) {
        throw new UnsupportedOsbApiVersionException(header);
    }
}
~~~

Trong thực tế, có thể hỗ trợ một dải minor version hoặc một tập phiên bản đã kiểm thử. Nếu một field chỉ có trong phiên bản mới hơn, broker cần tránh đưa field đó vào response cho request phiên bản cũ khi điều đó vi phạm hợp đồng.

### 13.2. Unknown fields và mở rộng có namespace

Khi thêm metadata key riêng, dùng namespace để tránh trùng tên với key chuẩn hoặc key của platform khác. Với field chuẩn mới, không tự ý serialize cho mọi phiên bản nếu client cũ không hiểu semantics.

Đối với dữ liệu JSON mở rộng, cần xác định hành vi khi platform bỏ qua field chưa biết. Không dựa vào một key metadata riêng để thực hiện quyết định bảo mật hoặc cấp phát quan trọng nếu platform không có nghĩa vụ đọc key đó.

## 14. Quản lý metadata trong Spring Cloud Service Broker

Trong ứng dụng Spring, nên tách nguồn catalog khỏi logic vòng đời instance:

- **Catalog configuration/provider:** định nghĩa service, plan, tags, requires, metadata và schemas.
- **Capability policy:** quyết định offering nào hỗ trợ binding, update hoặc retrieval.
- **Instance repository:** lưu trạng thái và cấu hình service instance.
- **Binding repository:** lưu binding metadata và secret reference.
- **Retrieval service:** đọc trạng thái instance/binding và tạo response theo OSB API.
- **Version compatibility layer:** kiểm tra header và chọn response phù hợp.

Không nên xây catalog metadata bằng cách đọc ngược mọi instance đang chạy. Catalog là mô tả khả năng cung cấp; retrieval data là trạng thái tài nguyên cụ thể. Hai nguồn có vòng đời và cách cache khác nhau.

Ví dụ model nội bộ:

~~~java
public record ServiceCatalogMetadata(
    List<String> tags,
    Map<String, Object> metadata,
    List<String> requires
) {}

public record RetrievalCapabilities(
    boolean instancesRetrievable,
    boolean bindingsRetrievable,
    boolean allowContextUpdates
) {}
~~~

Đây là model nội bộ minh họa. Model catalog chính thức của Spring Cloud Open Service Broker có thể khác theo phiên bản. Hãy map các giá trị này vào model thư viện đang dùng thay vì tự giả định constructor hoặc builder cụ thể.

### 14.1. Retrieval service chỉ đọc trạng thái đã lưu

Pseudocode truy xuất instance:

~~~java
public ServiceInstanceView retrieveInstance(
        String instanceId,
        String serviceId,
        String planId) {

    ServiceInstance instance =
        instanceRepository.requireById(instanceId);

    authorization.requireCanRetrieve(instance);

    if (!instance.getServiceId().equals(serviceId)
            || !instance.getPlanId().equals(planId)) {
        throw new RetrievalRequestMismatchException();
    }

    return ServiceInstanceView.from(instance);
}
~~~

Retrieval service đọc dữ liệu đã được lifecycle coordinator cập nhật. Không gọi provision hoặc update provider từ GET endpoint. Nếu trạng thái provider chưa đồng bộ, dùng worker hoặc reconciliation để cập nhật state store rồi retrieval đọc bản ghi mới nhất đã xác nhận.

### 14.2. Không trả dữ liệu nhạy cảm từ catalog

Catalog metadata thường có phạm vi hiển thị rộng hơn instance retrieval. Vì vậy:

- Chỉ công bố mô tả, URL và thuộc tính mà người dùng được phép xem.
- Không đặt dashboard client secret vào metadata tùy chỉnh.
- Không công bố địa chỉ quản trị hoặc credential provider.
- Không đưa tenant-specific secret vào catalog dùng chung.
- Kiểm tra URL ngoài trước khi hiển thị để tránh dẫn người dùng đến endpoint giả mạo.

Binding retrieval là trường hợp riêng vì response có thể chứa credentials. Cần bảo vệ endpoint và secret store ở mức cao hơn dữ liệu catalog.

## 15. Cache, thay đổi catalog và tính ổn định của metadata

Platform có thể cache catalog để giảm số request. Vì vậy, metadata và tags nên thay đổi có kiểm soát.

Một số nguyên tắc:

- Giữ service ID và plan ID ổn định.
- Chỉ đổi displayName hoặc description khi cần cập nhật hiển thị.
- Tránh thay đổi ý nghĩa của metadata key đang được platform tích hợp.
- Nếu thêm key mở rộng, duy trì namespace và mô tả.
- Không dùng metadata cache làm trạng thái thực tế của instance.
- Đồng bộ catalog với capability implementation và schema validator.
- Có kế hoạch chuyển tiếp khi bỏ một key hoặc thay đổi cấu trúc.

Nếu metadata được dùng cho automation của platform, nó đã trở thành một phần hợp đồng tích hợp. Khi đó cần versioning, contract tests và thông báo thay đổi giống như API field.

## 16. Kiểm thử catalog và retrieval

Kiểm thử cần xác nhận cả cấu trúc JSON lẫn hành vi của endpoint.

| Nhóm kiểm thử | Trường hợp cần xác minh |
|---|---|
| Catalog shape | tags, metadata, requires và schemas được serialize đúng |
| Metadata | Các key chuẩn có kiểu và nội dung phù hợp |
| Extension | Metadata key riêng có namespace, không chứa secret |
| Capability | Flag true chỉ khi endpoint tương ứng hoạt động |
| Instance retrieval | GET trả service_id, plan_id và dữ liệu được hỗ trợ |
| Binding retrieval | GET trả dữ liệu binding cần thiết và bảo vệ credentials |
| Query consistency | service_id và plan_id khớp bản ghi instance |
| Authorization | Caller không truy xuất instance/binding của tenant khác |
| Version | Request phiên bản không hỗ trợ bị từ chối theo contract |
| Legacy client | Response không đưa field mới sai phiên bản |
| Cache | Thay đổi catalog được platform nhận theo quy trình đã định |
| No side effect | GET retrieval không tạo, cập nhật hoặc thu hồi tài nguyên |

Một kịch bản contract test có thể gồm:

1. Gọi GET catalog và xác nhận service/plan IDs ổn định.
2. Xác nhận tags, metadata, requires và schemas đúng cấu trúc.
3. Xác nhận capability retrieval phản ánh implementation.
4. Tạo instance bằng luồng OSB thông thường.
5. Gọi GET service instance và kiểm tra dữ liệu phản ánh trạng thái đã lưu.
6. Tạo binding rồi gọi GET binding.
7. Xác nhận credentials chỉ trả cho caller đã xác thực và được authorize.
8. Gửi request với phiên bản API không được hỗ trợ và kiểm tra error response.
9. Xác nhận các GET không gọi provider side effect.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng tags làm authorization | Người dùng có thể truy cập offering ngoài quyền | Authorization dựa trên identity và policy |
| Đưa secret vào metadata | Rò rỉ qua catalog | Dùng secret manager và response binding được bảo vệ |
| Gộp metadata với parameters | Platform hiển thị nhầm dữ liệu cấu hình | Giữ đúng vị trí catalog metadata và request parameters |
| Dùng metadata riêng thay capability chuẩn | Platform không hiểu hành vi | Dùng capability flags theo OSB |
| Công bố instances_retrievable nhưng không có GET handler | Platform không đồng bộ được instance | Chỉ công bố khi endpoint hoàn chỉnh |
| Công bố bindings_retrievable nhưng không khôi phục được credentials | Retrieval response không dùng được | Lưu secret an toàn hoặc thiết kế credential có thể tái tạo |
| Trả plan đích khi update chưa xong | State retrieval không phản ánh thực tế | Trả current state đã xác nhận |
| Serialize field mới cho phiên bản cũ | Vi phạm tương thích | Version-aware response mapping |
| Coi mọi platform render metadata giống nhau | Giao diện hoặc automation không nhất quán | Chỉ dựa vào key chuẩn và kiểm thử platform |
| GET retrieval gọi provider mỗi lần | Tăng latency và tải hệ thống | Đọc state store, đồng bộ bằng worker/reconciliation |

## 18. Checklist thiết kế metadata và retrieval

Trước khi phát hành catalog và retrieval capability, hãy xác nhận:

- [ ] Tags chỉ dùng để phân loại và discovery, không dùng làm cơ chế phân quyền.
- [ ] Metadata service và plan được phân tách đúng cấp.
- [ ] Các metadata key chuẩn có nội dung và kiểu dữ liệu phù hợp.
- [ ] Metadata mở rộng có namespace, tài liệu và chiến lược tương thích.
- [ ] Catalog không chứa password, token hoặc thông tin quản trị nhạy cảm.
- [ ] Requires chỉ khai báo capability platform mà service thực sự cần.
- [ ] Schemas mô tả đúng parameters của create, update và binding.
- [ ] Dashboard client được xử lý theo field chuẩn và chính sách bảo mật.
- [ ] Maintenance information chỉ được công bố khi phiên bản hỗ trợ.
- [ ] Capability instances_retrievable khớp với GET instance endpoint.
- [ ] Capability bindings_retrievable khớp với GET binding endpoint.
- [ ] Retrieval xác thực service ID, plan ID và ownership.
- [ ] Retrieval response phản ánh trạng thái đã xác nhận và không tạo side effect.
- [ ] Credentials trong binding retrieval được bảo vệ như secret.
- [ ] Header X-Broker-API-Version được kiểm tra trên mọi request.
- [ ] Có contract test cho catalog, retrieval, version và authorization.

Metadata và tags giúp platform hiểu và trình bày service offering; requires, schemas và capability flags mô tả điều kiện tích hợp và hành vi broker; retrieval endpoints giúp platform đọc lại trạng thái của instance và binding. Khi các nhóm dữ liệu được đặt đúng vị trí, công bố theo phiên bản API đã hỗ trợ và kiểm thử bằng contract thực tế, Spring Cloud Service Broker có thể mở rộng catalog và khả năng đồng bộ mà vẫn giữ được tính tương thích, bảo mật và nhất quán giữa nhiều platform.
