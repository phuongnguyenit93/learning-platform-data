# Quan hệ giữa dịch vụ, gói dịch vụ, thực thể dịch vụ và liên kết

Trong một Service Broker theo Open Service Broker API (OSB API), bốn khái niệm **dịch vụ (service)**, **gói dịch vụ (service plan)**, **thực thể dịch vụ (service instance)** và **liên kết dịch vụ (service binding)** mô tả bốn lớp khác nhau của cùng một vòng đời cung cấp tài nguyên. Dịch vụ và gói dịch vụ mô tả những gì broker có thể cung cấp; service instance là tài nguyên cụ thể được tạo từ một lựa chọn trong catalog; service binding cấp thông tin kết nối hoặc quyền truy cập cho một ứng dụng hay workload sử dụng tài nguyên đó.

Spring Cloud Service Broker giúp triển khai ranh giới API và các xử lý vòng đời này trong một ứng dụng Spring. Khi thiết kế broker, cần giữ rõ quan hệ giữa các đối tượng để catalog phản ánh đúng khả năng cung cấp, thao tác provision/update/deprovision tác động đúng instance, còn bind/unbind quản lý quyền truy cập độc lập với vòng đời tài nguyên.

## 1. Bốn khái niệm trong mô hình

### 1.1. Dịch vụ — Service

Service là **định nghĩa của một loại dịch vụ** mà broker công bố cho nền tảng. Nó là mục trong catalog, không phải một database hay queue đã chạy. Một service definition mô tả tên, mã định danh, mô tả, khả năng bind và tập plan mà người dùng có thể chọn.

Ví dụ, broker có thể công bố service mang tên `postgresql`. Định nghĩa này cho biết broker có khả năng cung cấp PostgreSQL và nền tảng có thể yêu cầu tạo các instance từ dịch vụ đó. Service ID là định danh ổn định mà các request OSB API dùng để tham chiếu định nghĩa này; tên hiển thị có thể thân thiện hơn nhưng không nên được dùng thay cho ID trong logic xử lý.

Một service definition thường có các thông tin:

- **ID và name:** ID dùng trong giao tiếp API; name giúp người dùng nhận diện dịch vụ.
- **Description và metadata:** giải thích chức năng, tài liệu, biểu tượng hoặc thông tin hiển thị trên giao diện nền tảng.
- **bindable:** cho biết instance của service có hỗ trợ tạo binding hay không.
- **plans:** danh sách các gói dịch vụ thuộc service.
- **plan_updateable:** cho biết broker công bố khả năng đổi plan của instance sau khi tạo hay không. Broker vẫn phải kiểm tra khả năng và điều kiện của từng lần cập nhật.

Service definition thường thay đổi ít hơn các instance. Việc đổi tên hiển thị hoặc mô tả không đồng nghĩa với việc thay đổi tài nguyên đang chạy. Ngược lại, xóa một service khỏi catalog cũng không nên khiến broker tự ý xóa các instance đã được cấp phát từ service đó.

### 1.2. Gói dịch vụ — Service Plan

Plan là **một lựa chọn cấu hình hoặc cấp dịch vụ nằm bên trong một service**. Nếu service trả lời “broker cung cấp loại dịch vụ nào?”, plan trả lời “người dùng muốn loại cấu hình, dung lượng hoặc tính năng nào của dịch vụ đó?”.

Với service PostgreSQL, broker có thể công bố:

| Plan | Cấu hình minh họa | Mục đích |
|---|---|---|
| `starter` | 1 vCPU, 1 GB RAM, dung lượng nhỏ | Thử nghiệm hoặc môi trường phát triển |
| `standard` | 2 vCPU, 4 GB RAM, sao lưu định kỳ | Ứng dụng thông thường |
| `production` | Tài nguyên lớn hơn, HA và chính sách sao lưu chặt hơn | Hệ thống sản xuất |

Các con số trên chỉ minh họa cách phân biệt plan; cấu hình thật do broker và hạ tầng phía sau quyết định.

Mỗi plan có ID riêng, tên, mô tả và metadata. Trong catalog OSB API, plan được lồng trong service definition. Vì vậy, một plan không phải một service độc lập: plan chỉ có ý nghĩa khi được xác định cùng service chứa nó. Cặp `service_id` và `plan_id` cho biết chính xác lựa chọn mà nền tảng yêu cầu.

Plan có thể đại diện cho:

- Quy mô tài nguyên: CPU, RAM, dung lượng lưu trữ, số kết nối.
- Mức độ sẵn sàng: đơn nút, replica, multi-zone hoặc HA.
- Tính năng: backup, monitoring, encryption, read replica.
- Chính sách vận hành: thời hạn lưu trữ, giới hạn sử dụng, SLA hoặc mức hỗ trợ.

Không nên xem plan chỉ là một nhãn giá. Khi tạo instance, broker cần chuyển plan thành cấu hình thực tế và lưu lại lựa chọn đó. Nếu plan bị ẩn khỏi catalog trong tương lai, broker vẫn cần đủ dữ liệu để quản lý các instance hiện hữu và xử lý những request hợp lệ liên quan đến chúng.

### 1.3. Thực thể dịch vụ — Service Instance

Service instance là **một lần cấp phát cụ thể** của một service theo một plan. Đây là tài nguyên có trạng thái và vòng đời riêng, ví dụ một database PostgreSQL cụ thể, một cụm Redis, một hàng đợi message hoặc một bucket lưu trữ.

Nếu service là định nghĩa `postgresql` và plan là `production`, instance có thể là database dành cho hệ thống đơn hàng. Một instance khác có thể dùng cùng service nhưng chọn plan `starter` cho môi trường thử nghiệm. Hai instance này là hai tài nguyên độc lập dù cùng xuất phát từ một service definition.

Một service instance thường gắn với:

- **instance_id:** định danh do nền tảng gửi trong đường dẫn API; broker dùng để tra cứu và quản lý instance.
- **service_id:** service definition đã chọn khi tạo instance.
- **plan_id:** plan được chọn cho instance.
- **context:** thông tin về nền tảng, tổ chức, không gian hoặc workload tạo yêu cầu; cấu trúc cụ thể phụ thuộc nền tảng.
- **parameters:** tham số tùy chọn để tùy biến cấu hình trong phạm vi broker cho phép.
- **state và operation:** trạng thái cấp phát, cập nhật hoặc thu hồi; mã operation dùng khi thao tác chạy bất đồng bộ.
- **thông tin tài nguyên phía sau:** định danh database, cluster, queue hoặc tài nguyên thật mà broker quản lý.

Trong vòng đời thông thường, một instance được tạo từ một service và một plan tại một thời điểm. Nó có thể được cập nhật sang plan khác nếu service hỗ trợ và broker chấp nhận việc chuyển đổi. Việc đổi plan có thể đòi hỏi nâng cấp tài nguyên, di chuyển dữ liệu hoặc thay đổi cấu hình; vì vậy không được coi việc đổi plan là thay một chuỗi trong cơ sở dữ liệu.

Service instance là đối tượng mà các thao tác **provision**, **update** và **deprovision** quản lý. Việc tạo hay xóa binding không đồng nghĩa với việc tạo hay xóa instance.

### 1.4. Liên kết dịch vụ — Service Binding

Service binding là **mối quan hệ cấp quyền sử dụng giữa một service instance và một consumer**. Consumer thường là ứng dụng hoặc workload cần kết nối đến tài nguyên được cấp phát.

Ví dụ, một database có thể được dùng bởi cả `orders-api` và `billing-worker`. Broker có thể tạo hai binding riêng, mỗi binding có một binding ID và một bộ thông tin xác thực riêng. Cách làm này cho phép thu hồi quyền của một consumer mà không phải xóa database hoặc làm gián đoạn consumer còn lại.

Một binding thường chứa hoặc tham chiếu đến:

- **binding_id:** định danh của lần liên kết do nền tảng gửi.
- **instance_id:** instance mà consumer muốn sử dụng.
- **consumer context:** thông tin nhận diện ứng dụng hoặc workload, nếu nền tảng cung cấp.
- **credentials:** thông tin xác thực hoặc cấu hình kết nối mà consumer cần, chẳng hạn hostname, port, database, username, password hoặc token.
- **trạng thái và secret reference:** trạng thái binding và tham chiếu đến nơi lưu secret nếu broker không lưu bí mật trực tiếp trong bản ghi.

Binding không nhất thiết đồng nghĩa với một kết nối mạng đang mở. Nó thường là một bản ghi cấp quyền và một tập thông tin cấu hình để ứng dụng có thể tự kết nối. Tùy loại dịch vụ, thao tác bind có thể tạo database user, cấp role, tạo token, tạo policy hoặc sinh một cấu hình kết nối.

Một instance có thể có nhiều binding. Mỗi binding có thể được tạo và thu hồi độc lập. Khi unbind một consumer, broker thu hồi quyền hoặc credential của binding đó; các binding khác và bản thân instance vẫn tiếp tục tồn tại.

## 2. Quan hệ và lực lượng giữa các đối tượng

Có thể hình dung cấu trúc từ catalog đến tài nguyên đang chạy như sau:

~~~mermaid
flowchart TD
    C["Catalog của broker"] --> S["Service definition"]
    S --> P1["Plan: starter"]
    S --> P2["Plan: standard"]
    S --> P3["Plan: production"]
    S -->|"service_id + plan_id"| I["Service instance"]
    P1 --> I
    P2 --> I
    P3 --> I
    I --> B1["Binding: orders-api"]
    I --> B2["Binding: billing-worker"]
    B1 --> K1["Credentials / quyền truy cập riêng"]
    B2 --> K2["Credentials / quyền truy cập riêng"]
~~~

Quan hệ chính:

| Quan hệ | Ý nghĩa |
|---|---|
| Catalog — Service | Một catalog công bố nhiều service definition. |
| Service — Plan | Một service có thể có nhiều plan; mỗi plan thuộc một service. |
| Service + Plan — Instance | Một yêu cầu provision chọn một service và một plan để tạo một instance cụ thể. |
| Instance — Binding | Một instance có thể chưa có binding, có một binding hoặc có nhiều binding. |
| Binding — Consumer | Mỗi binding đại diện cho quyền sử dụng của một consumer đối với instance. |

Các quan hệ này có một số hệ quả quan trọng:

1. **Plan không sở hữu instance.** Instance tham chiếu cả service và plan đã chọn. Broker cần xác minh plan thực sự thuộc service được gửi trong request.
2. **Binding phụ thuộc vào instance.** Không thể tạo binding hợp lệ nếu instance chưa tồn tại, đang bị thu hồi hoặc không cho phép bind.
3. **Binding không sở hữu tài nguyên.** Xóa một binding chỉ thu hồi quyền của consumer tương ứng; deprovision instance mới là thao tác thu hồi tài nguyên.
4. **Catalog là mô tả khả năng cung cấp.** Catalog không phải danh sách đầy đủ các instance đang chạy. Việc đọc catalog không nên tạo tài nguyên hoặc làm thay đổi trạng thái instance.
5. **ID có vai trò khác nhau.** service ID, plan ID, instance ID và binding ID không thể thay thế cho nhau. Broker phải kiểm tra từng ID trong đúng ngữ cảnh.

## 3. Biểu diễn quan hệ trong catalog OSB API

Nền tảng lấy catalog từ broker qua endpoint `GET /v2/catalog`. Một mục catalog minh họa có thể có dạng:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Cơ sở dữ liệu quan hệ PostgreSQL được quản lý",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-postgresql-starter",
          "name": "starter",
          "description": "Gói nhỏ cho môi trường phát triển",
          "free": true
        },
        {
          "id": "plan-postgresql-production",
          "name": "production",
          "description": "Gói có tài nguyên và khả năng sẵn sàng cao hơn",
          "free": false
        }
      ]
    }
  ]
}
~~~

Ví dụ này cho thấy plan được khai báo trong service. Trường `bindable` mô tả khả năng bind của service; nếu giá trị là `false`, nền tảng không nên cho phép tạo binding cho instance thuộc service đó. Trường `plan_updateable` công bố khả năng cập nhật plan ở cấp service. Broker vẫn cần kiểm tra request, trạng thái instance, plan đích và các giới hạn chuyển đổi trước khi thực hiện.

Các ID trong ví dụ là giá trị minh họa. Trong hệ thống thật, ID cần ổn định qua các lần khởi động và triển khai broker. Không tạo ID ngẫu nhiên mới mỗi lần trả catalog, vì nền tảng sẽ không thể đối chiếu lựa chọn đã lưu với các request vòng đời sau đó.

## 4. Vòng đời từ service đến binding

### 4.1. Công bố catalog và chọn plan

Đầu tiên, broker công bố catalog. Nền tảng đọc danh sách service và plan, sau đó hiển thị lựa chọn phù hợp với người dùng hoặc quy trình tự động. Ở bước này chưa có service instance nào được tạo.

Nền tảng cần lưu các ID đã chọn. Khi người dùng chọn service `postgresql` và plan `production`, nền tảng sẽ dùng đúng `service_id` và `plan_id` đó khi gửi yêu cầu provision. Broker không nên suy ra plan từ tên hiển thị hoặc tự chọn một plan mặc định nếu request thiếu dữ liệu bắt buộc.

### 4.2. Provision — tạo service instance

Nền tảng gửi yêu cầu tạo instance đến:

`PUT /v2/service_instances/{instance_id}`

Request thường chứa `service_id`, `plan_id`, context của nền tảng và các parameters tùy chọn. Broker thực hiện các bước chính:

1. Xác thực request và kiểm tra service ID có được broker hỗ trợ.
2. Kiểm tra plan ID tồn tại và thuộc đúng service ID.
3. Kiểm tra context, quyền của tenant và các parameters theo chính sách.
4. Ghi nhận yêu cầu tạo instance với instance ID để xử lý idempotency.
5. Tạo tài nguyên phía sau hoặc gửi công việc đến hệ thống quản lý hạ tầng.
6. Lưu quan hệ giữa instance ID, service ID, plan ID, trạng thái và tài nguyên thực tế.

Nếu tài nguyên được tạo ngay, broker trả kết quả thành công theo hợp đồng OSB API. Nếu thao tác mất thời gian, broker có thể chấp nhận xử lý bất đồng bộ khi request cho phép, trả về mã operation và nền tảng truy vấn:

`GET /v2/service_instances/{instance_id}/last_operation`

Broker cập nhật trạng thái operation cho đến khi hoàn tất hoặc thất bại. Trong thời gian đang provision, instance không nên được coi là sẵn sàng để bind.

Ví dụ request rút gọn:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-production",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "database_name": "orders"
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Các trường context và định danh tổ chức/không gian phụ thuộc nền tảng tích hợp. Broker nên chuẩn hóa chúng thành mô hình nội bộ rõ ràng, tránh để logic nghiệp vụ phụ thuộc vào một cấu trúc context tùy biến không được kiểm tra.

### 4.3. Bind — tạo liên kết cho consumer

Sau khi instance ở trạng thái sẵn sàng và service cho phép bind, nền tảng gửi yêu cầu đến:

`PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}`

Request tham chiếu đến service ID, plan ID và có thể kèm thông tin consumer như app GUID, bind resource hoặc parameters. Broker cần xác minh:

- Instance tồn tại và thuộc đúng service/plan được request tham chiếu.
- Instance đã provision thành công và chưa bắt đầu deprovision.
- Service có khả năng bind.
- Consumer được phép truy cập instance theo chính sách tenant và quyền.
- Binding ID chưa được dùng cho một quan hệ khác.

Sau đó broker tạo quyền truy cập riêng cho consumer. Với PostgreSQL, thao tác này có thể tạo một user chỉ có quyền trên database cần dùng; với message broker, thao tác có thể tạo user và quyền trên một tập queue; với object storage, thao tác có thể cấp credential hoặc policy giới hạn trên bucket.

Response binding trả thông tin mà nền tảng chuyển cho consumer, thường nằm trong trường `credentials`. Ví dụ:

~~~json
{
  "credentials": {
    "uri": "postgresql://db.example.internal:5432/orders",
    "hostname": "db.example.internal",
    "port": 5432,
    "database": "orders",
    "username": "orders_api",
    "password": "<secret>"
  }
}
~~~

Thông tin trong ví dụ chỉ minh họa cấu trúc. Broker không nên ghi password hoặc token vào log, không đưa secret vào thông báo lỗi và không trả credential của binding khác. Mỗi consumer nên có credential riêng để có thể thu hồi và kiểm toán độc lập.

### 4.4. Unbind — thu hồi một liên kết

Khi ứng dụng không còn cần dịch vụ, nền tảng gửi yêu cầu xóa binding:

`DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}`

Broker tìm binding theo cặp instance ID và binding ID, thu hồi credential hoặc quyền đã cấp, rồi cập nhật trạng thái binding. Ví dụ với PostgreSQL, broker có thể khóa hoặc xóa user được tạo cho binding và thu hồi các quyền liên quan.

Unbind chỉ tác động đến consumer được định danh bởi binding đó. Nếu instance còn binding của `billing-worker`, việc unbind `orders-api` không được xóa credential hoặc quyền của `billing-worker`.

### 4.5. Update và deprovision — thay đổi hoặc thu hồi instance

Khi nền tảng yêu cầu cập nhật instance, broker xử lý qua:

`PATCH /v2/service_instances/{instance_id}`

Request có thể thay đổi plan hoặc parameters theo khả năng được công bố và chính sách của broker. Broker phải xác minh plan mới thuộc đúng service, kiểm tra khả năng chuyển đổi và lưu trạng thái operation nếu cập nhật bất đồng bộ. Việc đổi plan có thể cần nâng cấp tài nguyên, điều chỉnh quota hoặc di chuyển dữ liệu; cần có chiến lược xử lý lỗi và phục hồi.

Khi người dùng xóa dịch vụ, nền tảng gửi:

`DELETE /v2/service_instances/{instance_id}`

Broker thu hồi tài nguyên thật và đánh dấu instance đã bị xóa sau khi hoàn tất. Nền tảng thường điều phối unbind trước deprovision để thu hồi quyền của các consumer. Broker cũng cần bảo vệ trường hợp request bị gửi lặp, thao tác đang chạy hoặc tài nguyên phía sau đã bị xóa trước đó.

## 5. Ví dụ xuyên suốt: một database, nhiều consumer

Giả sử broker công bố service PostgreSQL với hai plan `starter` và `production`. Nhóm phát triển tạo instance `orders-db-prod` bằng plan `production`.

Sau khi provision hoàn tất, nền tảng tạo hai binding:

| Đối tượng | Tham chiếu | Vai trò |
|---|---|---|
| Service | `svc-postgresql` | Định nghĩa dịch vụ PostgreSQL |
| Plan | `plan-postgresql-production` | Cấu hình được chọn |
| Instance | `orders-db-prod` | Database cụ thể cho hệ thống đơn hàng |
| Binding A | `orders-api-binding` | Credential riêng cho API đơn hàng |
| Binding B | `billing-worker-binding` | Credential riêng cho worker thanh toán |

Hai ứng dụng có thể cùng truy cập một database nhưng sử dụng user và quyền riêng. Khi `orders-api` ngừng sử dụng database, broker unbind Binding A và thu hồi user tương ứng. Binding B vẫn hoạt động. Chỉ khi toàn bộ nhu cầu sử dụng kết thúc và nền tảng yêu cầu deprovision, broker mới thu hồi database instance.

Ví dụ này cho thấy vì sao cần tách instance và binding. Nếu broker gộp credential vào bản ghi instance, việc thu hồi một consumer có thể làm hỏng quyền truy cập của các consumer khác. Nếu broker coi unbind là deprovision, một ứng dụng rời đi có thể vô tình xóa tài nguyên dùng chung.

## 6. Lưu trữ quan hệ và quản lý trạng thái trong broker

Một mô hình dữ liệu nội bộ có thể tách thành các nhóm sau:

| Bản ghi | Khóa/quan hệ chính | Dữ liệu quan trọng |
|---|---|---|
| Service definition | `service_id` | Tên, mô tả, bindable, chính sách plan update |
| Plan definition | `plan_id`, `service_id` | Cấu hình, giới hạn và tính năng |
| Service instance | `instance_id` | `service_id`, `plan_id`, tenant/context, trạng thái, resource reference |
| Operation | `operation_id`, `instance_id` | Loại thao tác, trạng thái, lỗi, thời điểm cập nhật |
| Service binding | `instance_id`, `binding_id` | Consumer, trạng thái, secret reference |
| Credential/secret | Secret reference | Bí mật hoặc thông tin tham chiếu đến secret store |

Ràng buộc dữ liệu nên phản ánh quan hệ nghiệp vụ:

- Mỗi instance phải tham chiếu đến một service và một plan hợp lệ.
- Plan được gắn với service tương ứng; không chấp nhận cặp service/plan không hợp lệ.
- Mỗi binding thuộc về một instance.
- Binding ID phải được định danh trong phạm vi phù hợp với hợp đồng API và cách lưu trữ của broker.
- Không xóa bản ghi service/plan theo cách làm mất khả năng nhận diện các instance cũ; cần có chiến lược ngừng cung cấp hoặc lưu phiên bản metadata.
- Secret cần được quản lý bằng cơ chế bảo mật riêng, chẳng hạn secret manager hoặc kho mã hóa, và chỉ lưu tham chiếu trong bản ghi nghiệp vụ khi phù hợp.

Instance và operation có vòng đời bất đồng bộ. Một mô hình trạng thái đơn giản có thể gồm `provisioning`, `available`, `updating`, `deprovisioning`, `failed` và `deleted`. Tên trạng thái nội bộ có thể khác, nhưng phải ánh xạ nhất quán sang kết quả operation theo OSB API. Broker cần lưu trạng thái trước khi thực hiện công việc dài, sau đó cập nhật kết quả một cách an toàn để request retry hoặc tiến trình khởi động lại không tạo thêm tài nguyên ngoài ý muốn.

## 7. Idempotency và xử lý request lặp

Nền tảng có thể retry khi timeout hoặc mất kết nối. Vì thế broker phải thiết kế các thao tác theo hướng idempotent:

- **Provision:** cùng instance ID và cùng lựa chọn service/plan phải được nhận diện là cùng một yêu cầu logic. Nếu request lặp đến khi thao tác trước đang chạy, broker trả trạng thái phù hợp thay vì tạo database thứ hai.
- **Bind:** cùng cặp instance ID và binding ID không được tạo nhiều user hoặc nhiều bộ credential không kiểm soát. Nếu binding đã tồn tại, broker cần trả kết quả phù hợp với trạng thái hiện có.
- **Update:** tránh chạy đồng thời hai lần thay đổi plan trên cùng instance nếu thao tác trước chưa hoàn tất.
- **Unbind/deprovision:** request lặp sau khi quyền hoặc tài nguyên đã được thu hồi cần được xử lý an toàn theo hợp đồng API và trạng thái lưu trữ.

Khi cùng một ID được gửi với nội dung mâu thuẫn, chẳng hạn instance ID đã gắn với service khác, broker cần trả lỗi phù hợp và ghi nhận sự kiện để điều tra. Không được âm thầm ghi đè quan hệ cũ.

## 8. Bảo mật theo ranh giới instance và binding

Service, plan, instance và binding là các ranh giới bảo mật khác nhau:

- **Catalog:** chỉ công bố metadata được phép hiển thị; không đưa secret, địa chỉ quản trị nội bộ hoặc thông tin tenant riêng vào catalog công khai.
- **Service và plan:** xác minh ID từ catalog và kiểm tra các giới hạn của plan ở phía broker. Không tin parameters do người dùng gửi nếu chúng có thể vượt quota hoặc thay đổi quyền.
- **Instance:** gắn instance với tenant/context đã xác thực; mọi thao tác update và deprovision phải kiểm tra quyền sở hữu hoặc quyền quản trị.
- **Binding:** cấp quyền tối thiểu cho từng consumer, tạo credential riêng và có khả năng thu hồi độc lập. Bảo vệ response chứa credential, log, trace và hệ thống lưu secret.
- **Vận chuyển và xác thực:** bảo vệ kết nối broker-platform bằng TLS và cơ chế xác thực broker phù hợp với nền tảng tích hợp.

Việc tách credential theo binding giúp giới hạn phạm vi ảnh hưởng khi một ứng dụng bị lộ thông tin xác thực. Khi rotate secret, broker cần phối hợp cập nhật quyền và thông tin consumer theo khả năng nền tảng; tránh xóa credential cũ trước khi consumer có cơ hội chuyển đổi nếu quy trình yêu cầu chuyển tiếp.

## 9. Ánh xạ trách nhiệm trong Spring Cloud Service Broker

Trong ứng dụng Spring Cloud Service Broker, có thể tổ chức xử lý theo đúng ranh giới của OSB API:

- Thành phần cung cấp catalog xây dựng danh sách service definition và plan để nền tảng truy vấn.
- Thành phần quản lý service instance xử lý provision, lấy trạng thái operation, update và deprovision.
- Thành phần quản lý service instance binding xử lý bind và unbind, bao gồm việc tạo, lưu, trả và thu hồi credential.
- Lớp nghiệp vụ/hạ tầng phía sau thực hiện công việc thật như tạo database, cấu hình cluster, tạo user, cấp policy và thu hồi tài nguyên.
- Kho dữ liệu lưu quan hệ và trạng thái; kho secret quản lý bí mật; bộ xử lý nền thực hiện các thao tác dài.

Nên giữ logic kiểm tra quan hệ trong lớp nghiệp vụ dùng chung, thay vì chỉ kiểm tra ở controller. Chẳng hạn, thao tác bind phải tải instance, xác minh service/plan, kiểm tra trạng thái và quyền bind trước khi cấp credential. Cách tổ chức này giúp các đường gọi đồng bộ, bất đồng bộ và tác vụ nền dùng cùng một quy tắc.

Một luồng xử lý ở mức khái niệm:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant P as Nền tảng
    participant B as Spring Cloud Broker
    participant R as Hạ tầng dịch vụ
    participant A as Ứng dụng

    U->>P: Chọn service và plan
    P->>B: GET /v2/catalog
    B-->>P: Service definitions và plans
    P->>B: PUT service_instances/{instance_id}
    B->>R: Tạo tài nguyên theo plan
    R-->>B: Kết quả provision
    B-->>P: Instance đã sẵn sàng hoặc operation
    P->>B: PUT service_bindings/{binding_id}
    B->>R: Tạo credential/quyền riêng
    R-->>B: Credential hoặc secret reference
    B-->>P: Binding credentials
    P-->>A: Cung cấp cấu hình kết nối
    A->>R: Sử dụng dịch vụ
    P->>B: DELETE service_bindings/{binding_id}
    B->>R: Thu hồi quyền của consumer
    P->>B: DELETE service_instances/{instance_id}
    B->>R: Thu hồi tài nguyên
~~~

Các tên thành phần và cách triển khai cụ thể có thể thay đổi theo phiên bản thư viện và kiến trúc ứng dụng. Điều cần giữ ổn định là ranh giới trách nhiệm: catalog mô tả lựa chọn; instance quản lý tài nguyên; binding quản lý quyền truy cập của consumer.

## 10. Tích hợp với Cloud Foundry và Kubernetes

**Cloud Foundry** là một nền tảng tiêu biểu sử dụng OSB API. Nền tảng đọc catalog của broker, cho phép người dùng chọn service/plan, tạo service instance và yêu cầu binding cho ứng dụng. Context của Cloud Foundry giúp broker nhận diện tổ chức, space hoặc thông tin nền tảng cần thiết. Broker phải xác minh context theo cơ chế tin cậy của kết nối, không coi các giá trị nhận từ request là bằng chứng xác thực độc lập.

**Kubernetes** có nhiều cách tích hợp dịch vụ bên ngoài. Một thành phần điều khiển hoặc adapter có thể gọi broker theo OSB API, sau đó chuyển thông tin binding thành Secret hoặc cấu hình mà Pod sử dụng. Một số hệ thống dùng Service Binding Specification, operator hoặc controller riêng để biểu diễn kết nối giữa workload và dịch vụ. Không nên giả định mọi cụm Kubernetes đều cung cấp sẵn một client OSB API giống Cloud Foundry; cần xác định rõ thành phần nào chịu trách nhiệm gọi broker, lưu trạng thái và phân phối secret.

Dù nền tảng khác nhau, mô hình quan hệ vẫn giữ nguyên:

1. Service và plan là lựa chọn được broker công bố.
2. Nền tảng tạo một instance ID để theo dõi tài nguyên được cấp phát.
3. Nền tảng yêu cầu binding cho từng consumer cần sử dụng tài nguyên.
4. Broker trả thông tin kết nối theo cơ chế bảo mật của nền tảng.
5. Khi workload không còn cần dịch vụ, binding được thu hồi; instance được deprovision khi không còn nhu cầu sử dụng.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Service là database đã chạy | Service là định nghĩa trong catalog; database cụ thể là service instance. |
| Plan là một service khác | Plan là một lựa chọn thuộc một service definition. |
| Tạo instance đồng nghĩa tạo binding | Provision tạo tài nguyên; bind cấp quyền cho một consumer. |
| Một instance chỉ có một ứng dụng dùng | Một instance có thể có nhiều binding độc lập nếu service hỗ trợ. |
| Unbind sẽ xóa database | Unbind thu hồi quyền của một consumer; deprovision mới thu hồi instance. |
| Xóa service khỏi catalog sẽ xóa mọi instance | Thay đổi catalog không tự động thay thế quy trình deprovision từng instance. |
| Binding chỉ là chuỗi URL kết nối | Binding là quan hệ quản lý vòng đời và quyền truy cập; credentials chỉ là một phần của nó. |
| Plan updateable nghĩa là đổi plan luôn an toàn | Broker vẫn phải kiểm tra khả năng chuyển đổi, trạng thái, quota và tác động dữ liệu. |

## 12. Nguyên tắc thiết kế cần ghi nhớ

Khi xây dựng broker bằng Spring Cloud, hãy giữ bốn lớp khái niệm riêng biệt trong mô hình dữ liệu và xử lý:

- **Service** mô tả loại dịch vụ mà broker cung cấp.
- **Plan** mô tả lựa chọn cấu hình thuộc service.
- **Service instance** là tài nguyên cụ thể được tạo từ service và plan.
- **Service binding** là quyền sử dụng và thông tin kết nối của một consumer đối với instance.

Từ cách phân tách đó, các thao tác OSB API trở nên rõ ràng: catalog công bố service/plan; provision tạo instance; update thay đổi cấu hình hoặc plan của instance; bind tạo quyền truy cập; unbind thu hồi quyền của một consumer; deprovision thu hồi tài nguyên. Lưu đúng các quan hệ ID, trạng thái và operation giúp broker xử lý retry, bất đồng bộ và nhiều consumer an toàn, đồng thời giúp tích hợp Cloud Foundry hoặc các adapter trên Kubernetes mà không làm lẫn vòng đời tài nguyên với vòng đời quyền truy cập.

