# Điều kiện áp dụng OSB API và giới hạn của mô hình broker

Open Service Broker API (OSB API) chuẩn hóa cách một nền tảng ứng dụng yêu cầu dịch vụ bên ngoài được cung cấp và quản lý. Thông qua một hợp đồng HTTP thống nhất, nền tảng có thể khám phá danh mục dịch vụ, chọn gói dịch vụ, cấp phát một service instance, tạo binding để ứng dụng sử dụng dịch vụ, cập nhật cấu hình và thu hồi tài nguyên khi không còn cần thiết.

OSB API phù hợp khi tổ chức muốn đưa các dịch vụ như cơ sở dữ liệu, hàng đợi thông điệp, bộ nhớ hoặc dịch vụ SaaS vào quy trình tự phục vụ của nền tảng. Tuy nhiên, API chỉ chuẩn hóa giao tiếp và vòng đời ở mức điều khiển. Nó không tự triển khai hạ tầng, không quy định mọi dịch vụ phải có cùng cách vận hành và cũng không bảo đảm một dịch vụ broker có thể chạy giống nhau trên mọi nền tảng.

Bài học này giải thích các điều kiện cần có để áp dụng OSB API, cách mô hình broker phối hợp với nền tảng, những giới hạn cần tính đến và vai trò của Spring Cloud Open Service Broker khi xây dựng broker bằng Spring.

## 1. OSB API giải quyết vấn đề gì?

Khi một nhóm phát triển ứng dụng cần cơ sở dữ liệu hoặc một dịch vụ hạ tầng, họ thường phải gửi yêu cầu cho đội vận hành. Đội vận hành tạo tài nguyên, cấu hình quyền truy cập, cấp thông tin kết nối rồi hướng dẫn nhóm phát triển tích hợp. Khi ứng dụng ngừng sử dụng dịch vụ, tài nguyên và thông tin xác thực cũng cần được thu hồi.

Nếu mỗi loại dịch vụ có một quy trình riêng, nền tảng phải biết cách gọi API riêng của từng nhà cung cấp. Điều này khiến việc tích hợp, tự động hóa và vận hành nhiều dịch vụ trở nên phức tạp.

OSB API tạo ra một hợp đồng chung giữa **platform** và **service broker**:

- Platform là nền tảng quản lý ứng dụng và gửi yêu cầu sử dụng dịch vụ. Cloud Foundry là ví dụ có tích hợp OSB API. Với Kubernetes, thường cần một thành phần tích hợp như controller, operator hoặc adapter có khả năng đóng vai trò OSB client.
- Service broker là dịch vụ cung cấp API theo chuẩn OSB. Broker công bố catalog, xác định các plan và điều phối việc tạo, cập nhật, binding hoặc xóa tài nguyên.
- Backing service là dịch vụ thực tế mà người dùng cần, chẳng hạn PostgreSQL, Redis, RabbitMQ hoặc một dịch vụ SaaS. Broker có thể tạo tài nguyên trực tiếp hoặc gọi API của nhà cung cấp để thực hiện việc đó.
- Ứng dụng tiêu thụ backing service thông qua thông tin kết nối và quyền truy cập do quá trình binding cung cấp.

Broker thuộc lớp điều khiển (control plane). Nó nhận yêu cầu, kiểm tra điều kiện, lưu trạng thái và điều phối thao tác. Dữ liệu nghiệp vụ của ứng dụng thường đi trực tiếp giữa ứng dụng và backing service; broker không nhất thiết nằm trên đường truyền dữ liệu đó.

~~~mermaid
flowchart LR
    P[Platform / OSB client] -->|HTTP OSB API| B[Service broker]
    B -->|API nhà cung cấp hoặc SDK| I[Hạ tầng / nhà cung cấp]
    I --> S[Backing service]
    P -->|Cấp thông tin binding| A[Ứng dụng]
    A -->|Kết nối trực tiếp| S
~~~

Sự phân tách này giúp nền tảng có một cách quản lý dịch vụ nhất quán mà không cần nhúng toàn bộ logic riêng của từng nhà cung cấp vào nền tảng.

## 2. Khi nào nên áp dụng OSB API?

OSB API có giá trị rõ nhất khi một dịch vụ cần được cung cấp theo yêu cầu và có vòng đời có thể tự động hóa. Một số tình huống điển hình:

- Nền tảng cần cho phép nhóm phát triển tự tạo cơ sở dữ liệu, cache, message broker hoặc bucket lưu trữ theo một gói dịch vụ đã được quản trị phê duyệt.
- Nhiều nhóm ứng dụng cần dùng chung một quy trình tạo dịch vụ, cấp quyền truy cập, thay đổi cấu hình và thu hồi tài nguyên.
- Một tổ chức có nhiều nhà cung cấp hoặc nhiều loại backing service và muốn nền tảng gọi chúng qua cùng một giao thức.
- Đội vận hành cần kiểm soát tài nguyên theo tenant, tổ chức, không gian làm việc hoặc ứng dụng, đồng thời ghi nhận ai đã yêu cầu thao tác nào.
- Việc tạo tài nguyên có thể mất thời gian và cần một cơ chế báo trạng thái để platform theo dõi tiến trình.

Ví dụ, một nền tảng có thể công bố dịch vụ PostgreSQL với hai plan: gói thử nghiệm có dung lượng nhỏ và gói production có dung lượng lớn hơn, sao lưu định kỳ cùng chính sách sẵn sàng cao. Nhóm phát triển chọn plan trong catalog. Platform gửi yêu cầu tới broker; broker tạo database và user tương ứng, sau đó trả về thông tin binding để ứng dụng kết nối.

OSB API không nhất thiết phù hợp với mọi API quản lý dịch vụ. Nếu một tài nguyên đã tồn tại cố định, không có nhu cầu cấp phát theo yêu cầu, không có khái niệm instance hoặc binding, và cũng không cần vòng đời do platform quản lý, tích hợp trực tiếp có thể đơn giản hơn. Tương tự, một thao tác xử lý tức thời cho từng HTTP request thường không nên được mô hình hóa thành một service instance dài hạn.

## 3. Những điều kiện cần có trước khi triển khai

Áp dụng OSB API thành công đòi hỏi cả platform, broker và hệ thống phía sau đáp ứng các điều kiện kỹ thuật và vận hành.

### 3.1. Platform phải có OSB client hoặc lớp tích hợp tương thích

Platform cần có khả năng gọi các endpoint OSB, gửi đúng cấu trúc request, quản lý định danh instance và binding, cũng như xử lý các phản hồi đồng bộ hoặc bất đồng bộ.

Cloud Foundry có thể tích hợp trực tiếp với service broker tuân thủ OSB API. Với Kubernetes, cần xác định rõ thành phần nào đóng vai trò OSB client. Có thể sử dụng một integration layer, controller hoặc operator để chuyển yêu cầu từ tài nguyên Kubernetes sang các lời gọi OSB API. Việc Kubernetes có workload và controller không đồng nghĩa mọi cụm Kubernetes đều tự động hỗ trợ OSB API.

Trước khi triển khai, cần xác nhận:

- Platform hoặc adapter hỗ trợ phiên bản OSB API mà broker cung cấp.
- Platform có thể đăng ký broker, lưu thông tin xác thực và gọi broker qua mạng.
- Platform hiểu cách xử lý các thao tác cần thời gian và có thể truy vấn trạng thái khi cần.
- Platform có quy trình quản lý vòng đời của service instance và binding phù hợp với mô hình của broker.

### 3.2. Broker phải công bố catalog và plan ổn định

Catalog mô tả những dịch vụ mà broker cung cấp. Mỗi service có định danh ổn định, tên, mô tả, khả năng binding và danh sách plan. Mỗi plan cũng có định danh ổn định cùng thông tin mô tả và các thuộc tính liên quan.

Ví dụ rút gọn về catalog:

~~~json
{
  "services": [
    {
      "id": "postgres-service-id",
      "name": "postgresql",
      "description": "Dịch vụ cơ sở dữ liệu PostgreSQL",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "postgres-small-plan-id",
          "name": "small",
          "description": "Gói thử nghiệm với tài nguyên giới hạn",
          "free": false
        },
        {
          "id": "postgres-production-plan-id",
          "name": "production",
          "description": "Gói production có tài nguyên lớn hơn",
          "free": false
        }
      ]
    }
  ]
}
~~~

Các định danh service và plan được platform sử dụng trong những yêu cầu tiếp theo. Vì vậy, broker cần giữ chúng ổn định qua các lần triển khai. Đổi tên hiển thị thường ít ảnh hưởng hơn việc thay đổi ID. Nếu cần ngừng cung cấp một plan, cần có chính sách chuyển đổi và tương thích cho những instance đã được tạo từ plan đó.

Thuộc tính bindable cho biết service có hỗ trợ tạo binding hay không. Thuộc tính plan_updateable cho biết service có cho phép chuyển plan trong quá trình cập nhật hay không. Khai báo khả năng trong catalog phải phản ánh đúng hành vi mà broker thực sự hỗ trợ.

### 3.3. Hệ thống phía sau phải có khả năng tự động hóa

Broker chỉ có thể thực hiện vòng đời dịch vụ nếu backing service hoặc nhà cung cấp có cơ chế thao tác bằng chương trình. Cơ chế đó có thể là REST API, SDK, Kubernetes API, CLI có thể tự động hóa hoặc một hệ thống nội bộ.

Cần làm rõ cách thực hiện ít nhất các công việc sau:

- Tạo tài nguyên mới theo service và plan được chọn.
- Cấu hình tài nguyên, giới hạn dung lượng và chính sách truy cập.
- Tạo, xoay vòng hoặc thu hồi thông tin xác thực.
- Thay đổi cấu hình hoặc plan nếu dịch vụ hỗ trợ.
- Xóa tài nguyên và xử lý dữ liệu còn lại theo chính sách.
- Kiểm tra trạng thái thực tế sau khi thao tác thành công hoặc thất bại.

Nếu thao tác phía nhà cung cấp không thể tự động hóa, broker có thể trở thành một lớp nhận yêu cầu nhưng vẫn phải chờ con người xử lý. Cách làm đó làm giảm đáng kể lợi ích tự phục vụ của OSB API.

### 3.4. Broker phải lưu trạng thái bền vững

Broker cần ghi nhận mối quan hệ giữa ID do platform gửi và tài nguyên thực tế ở phía nhà cung cấp. Tối thiểu, trạng thái thường cần lưu:

- ID của service instance và binding.
- Service ID, plan ID và thông tin tenant hoặc context liên quan.
- ID tài nguyên do nhà cung cấp trả về.
- Trạng thái vòng đời hiện tại.
- Thông tin thao tác bất đồng bộ đang chạy.
- Tham chiếu tới secret hoặc thông tin kết nối cần thiết, được bảo vệ phù hợp.

Không nên phụ thuộc hoàn toàn vào bộ nhớ của một tiến trình ứng dụng. Khi broker khởi động lại hoặc chạy nhiều replica, nó vẫn phải nhận ra instance đã tồn tại, biết thao tác nào đang chạy và tránh tạo tài nguyên trùng lặp.

Trạng thái lưu trong broker cũng cần có cách đối chiếu với trạng thái thực tế ở nhà cung cấp. Ví dụ, một database có thể đã được tạo thành công nhưng broker bị dừng trước khi ghi nhận kết quả. Nếu không có cơ chế phục hồi hoặc đối soát, lần retry có thể tạo thêm database ngoài ý muốn.

### 3.5. Phải có định danh, bảo mật và phân tách tenant

Broker thường có quyền tạo và xóa tài nguyên trên hệ thống phía sau, nên endpoint của broker là một ranh giới bảo mật quan trọng.

Cần triển khai TLS cho kết nối, xác thực platform, phân quyền theo từng loại thao tác và quản lý secret an toàn. Thông tin xác thực của backing service không nên xuất hiện trong log, thông báo lỗi hoặc dữ liệu quan sát không được bảo vệ.

Broker phải xác định rõ tenant sở hữu service instance. Các giá trị context do platform gửi có thể giúp broker biết yêu cầu đến từ tổ chức, space, ứng dụng hoặc môi trường nào. Broker cần xác thực và kiểm tra quyền trước khi cho phép đọc, binding, cập nhật hoặc xóa tài nguyên.

Không được tin cậy mù quáng các tham số do client gửi, kể cả tên tenant hoặc thông tin context. Cần kiểm tra chúng theo danh tính platform đã xác thực và chính sách nội bộ.

## 4. Các thao tác vòng đời trong OSB API

OSB API mô hình hóa dịch vụ qua catalog, service instance và service binding. Các thao tác thường gặp được trình bày dưới đây theo trình tự sử dụng.

### 4.1. Khám phá catalog

Platform gọi endpoint catalog để lấy danh sách service và plan mà broker công bố. Từ thông tin này, platform biết dịch vụ nào có thể được chọn, có hỗ trợ binding hay không và có cho phép thay đổi plan hay không.

Ví dụ endpoint:

~~~http
GET /v2/catalog
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
Authorization: <thông-tin-xác-thực>
~~~

Catalog không phải nơi lưu trạng thái của từng instance. Nó mô tả các lựa chọn dịch vụ mà broker đang cung cấp.

### 4.2. Provision một service instance

Khi người dùng chọn service và plan, platform gửi yêu cầu tạo instance. Request thường chứa service ID, plan ID, context của platform, thông tin tổ chức hoặc không gian làm việc khi phù hợp, cùng các tham số cấu hình.

Ví dụ request rút gọn:

~~~http
PUT /v2/service_instances/instance-123?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
~~~

~~~json
{
  "service_id": "postgres-service-id",
  "plan_id": "postgres-small-plan-id",
  "organization_guid": "org-456",
  "space_guid": "space-789",
  "parameters": {
    "database_name": "orders"
  }
}
~~~

Các trường tổ chức và không gian làm việc thường gắn với ngữ cảnh Cloud Foundry; nền tảng khác có thể cung cấp context theo cách riêng. Broker cần dựa trên hợp đồng và phiên bản API mà platform hỗ trợ để xử lý đúng các trường được gửi.

Kết quả provision có thể hoàn tất ngay hoặc cần thời gian. Nếu hoàn tất đồng bộ, broker trả kết quả thành công theo hợp đồng OSB. Nếu cần xử lý bất đồng bộ và platform đã cho phép bằng accepts_incomplete, broker trả phản hồi cho biết thao tác đang được theo dõi. Broker cần lưu trạng thái để platform có thể truy vấn tiếp.

### 4.3. Theo dõi thao tác bất đồng bộ

Tạo database, cấp cluster hoặc cấu hình tài nguyên lớn có thể kéo dài. Giữ một HTTP request mở trong suốt quá trình không phải lúc nào cũng phù hợp. OSB API hỗ trợ mô hình bất đồng bộ cho những thao tác vòng đời như provision, update và deprovision.

Sau phản hồi cho biết thao tác đang chạy, platform có thể gọi endpoint last_operation để hỏi trạng thái:

~~~http
GET /v2/service_instances/instance-123/last_operation?service_id=postgres-service-id&plan_id=postgres-small-plan-id&operation=operation-456
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
~~~

Broker trả về trạng thái thao tác, thường thuộc một trong các trường hợp: đang thực hiện, thành công hoặc thất bại. Nếu thao tác chưa kết thúc, platform có thể truy vấn lại theo chính sách polling của nó.

Broker cần lưu mã thao tác và trạng thái đủ bền vững để nhiều replica cùng phục vụ request. Khi trả về lỗi, nên cung cấp mô tả có ích cho người vận hành nhưng không để lộ secret, thông tin xác thực hoặc chi tiết nội bộ nhạy cảm.

Nếu thao tác cần chạy bất đồng bộ nhưng platform không chấp nhận xử lý bất đồng bộ, broker phải phản hồi theo quy tắc của OSB API thay vì âm thầm giữ request hoặc giả vờ đã hoàn tất.

### 4.4. Update service instance

Update được dùng khi cần thay đổi plan hoặc tham số của một instance đã tồn tại, trong phạm vi service cho phép. Ví dụ, nhóm phát triển chuyển database từ plan small sang plan production.

Broker cần xác định thay đổi có được hỗ trợ hay không, có yêu cầu downtime hay không, có cần sao lưu hoặc di chuyển dữ liệu hay không. Thuộc tính plan_updateable trong catalog phải nhất quán với khả năng thực tế.

Không phải mọi thay đổi tham số đều có thể áp dụng trực tiếp. Có thay đổi chỉ được chấp nhận khi tạo instance mới; có thay đổi cần một quy trình chuyển đổi nhiều bước. Broker cần mô tả rõ các giới hạn đó trong tài liệu dịch vụ và xử lý lỗi có thể phục hồi.

### 4.5. Bind để ứng dụng sử dụng dịch vụ

Provision tạo service instance; binding tạo thông tin truy cập cho một consumer cụ thể. Platform gửi yêu cầu bind với ID instance và ID binding. Broker kiểm tra instance tồn tại, service có hỗ trợ binding và consumer được phép sử dụng dịch vụ.

Kết quả binding có thể chứa credentials, URI kết nối, endpoint hoặc thông tin cần thiết để platform cung cấp cho ứng dụng. Ví dụ, broker có thể tạo một database user riêng cho ứng dụng thay vì dùng chung tài khoản quản trị của database.

Một binding nên có phạm vi quyền rõ ràng. Nếu hai ứng dụng cùng dùng một database, broker có thể cấp hai bộ thông tin xác thực khác nhau để có thể thu hồi quyền của một ứng dụng mà không làm gián đoạn ứng dụng còn lại.

### 4.6. Unbind và deprovision

Unbind thu hồi quyền truy cập được cấp cho một binding. Ví dụ, broker xóa database user dành riêng cho ứng dụng hoặc thu hồi credential tương ứng.

Deprovision xóa service instance khi platform hoặc người dùng yêu cầu thu hồi dịch vụ. Broker cần kiểm tra service ID, plan ID, quyền sở hữu và trạng thái hiện tại trước khi xóa tài nguyên phía nhà cung cấp.

Hai thao tác có ý nghĩa khác nhau: unbind thu hồi một liên kết tiêu thụ dịch vụ; deprovision thu hồi chính instance. Chính sách xóa dữ liệu, lưu trữ bản sao lưu và thời gian lưu giữ cần được thiết kế rõ ràng. OSB API không tự quyết định chính sách dữ liệu của tổ chức.

## 5. Idempotency, xử lý lỗi và tính nhất quán

Platform có thể gửi lại request khi timeout, mất kết nối hoặc không nhận được phản hồi. Vì vậy broker phải thiết kế thao tác có khả năng chịu retry.

Với cùng một service instance ID và cùng nội dung yêu cầu, một lần retry không được tạo ra một tài nguyên độc lập ngoài ý muốn. Broker nên dùng ID do platform cung cấp làm khóa đối chiếu, kết hợp với trạng thái lưu bền vững và định danh tài nguyên phía nhà cung cấp. Nếu ID đã tồn tại nhưng request mới yêu cầu service hoặc plan không tương thích, broker cần trả lỗi phù hợp thay vì ghi đè trạng thái cũ.

Idempotency không có nghĩa là mọi request đều thành công hoặc không bao giờ có lỗi. Nó có nghĩa là việc lặp lại cùng một thao tác trong điều kiện tương đương không tạo ra tác dụng phụ trùng lặp. Các thao tác xóa và thu hồi quyền cũng cần được thiết kế để retry an toàn.

Một quy trình provision có thể gặp tình huống:

1. Broker nhận yêu cầu và ghi nhận instance ở trạng thái đang tạo.
2. Broker gọi API nhà cung cấp để tạo database.
3. Nhà cung cấp tạo database thành công.
4. Kết nối giữa broker và nhà cung cấp bị ngắt trước khi broker nhận được kết quả.
5. Platform retry yêu cầu provision.

Ở bước cuối, broker cần tra cứu trạng thái hoặc đối chiếu theo khóa định danh để nhận ra database đã được tạo. Nếu broker gọi lệnh tạo mới mà không kiểm tra, hệ thống có thể phát sinh database trùng lặp.

Các thao tác nhiều bước cũng cần tính đến lỗi giữa chừng. Ví dụ, tạo database thành công nhưng tạo user thất bại. Broker phải xác định có thể retry bước tạo user, tiếp tục từ trạng thái hiện tại hay cần xóa tài nguyên đã tạo để hoàn tác. OSB API không cung cấp một giao dịch phân tán tự động giữa broker và nhà cung cấp; logic phục hồi thuộc trách nhiệm triển khai của broker.

## 6. Vai trò và giới hạn của Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp các abstraction và cơ chế tích hợp trong ứng dụng Spring để xây dựng một service broker tuân theo OSB API. Framework giúp xử lý phần giao tiếp và mô hình request/response theo hợp đồng, từ đó nhóm phát triển tập trung vào logic dịch vụ.

Trong một ứng dụng Spring Boot, phần triển khai thường cần định nghĩa catalog, logic quản lý service instance, logic binding và các thành phần hỗ trợ lưu trạng thái hoặc gọi nhà cung cấp. Khi platform gửi request OSB, framework định tuyến request đến phần xử lý tương ứng; phần nghiệp vụ của broker thực hiện công việc thực tế trên backing service.

~~~mermaid
flowchart TD
    A[Platform] -->|OSB HTTP request| B[Spring Boot broker]
    B --> C[Spring Cloud Open Service Broker]
    C --> D[Logic catalog và vòng đời]
    D --> E[(Kho trạng thái broker)]
    D --> F[Client API / SDK nhà cung cấp]
    F --> G[Backing service]
~~~

Framework giúp triển khai hợp đồng OSB trong ứng dụng Spring, nhưng không tự quyết định các vấn đề sau:

- Cách tạo database, cluster, queue hoặc tài nguyên cụ thể của nhà cung cấp.
- Cách lưu trữ trạng thái bền vững, xử lý đồng thời và phục hồi sau sự cố.
- Chính sách phân quyền, cách bảo vệ secret và phân tách dữ liệu giữa tenant.
- Quy tắc retry, idempotency và xử lý các thao tác bất đồng bộ ở tầng nghiệp vụ.
- Cách đăng ký broker với platform, cấu hình mạng, TLS và xác thực trong môi trường triển khai.
- Chính sách backup, giám sát, tính phí, giới hạn sử dụng và hỗ trợ vận hành.

Cần kiểm tra phiên bản Spring Cloud Open Service Broker đang dùng tương thích với phiên bản OSB API mà platform yêu cầu. Không nên giả định mọi phiên bản framework đều hỗ trợ mọi tính năng hoặc phiên bản mới nhất của đặc tả. Các phần mở rộng và hành vi riêng của platform cũng cần được kiểm tra trong môi trường tích hợp thực tế.

## 7. Giới hạn của mô hình service broker

OSB API tạo ra một giao thức thống nhất, nhưng không biến mọi dịch vụ thành một sản phẩm có ngữ nghĩa giống nhau. Những giới hạn dưới đây ảnh hưởng trực tiếp đến khả năng thiết kế và vận hành.

### 7.1. Chuẩn hóa giao thức, không chuẩn hóa bản chất dịch vụ

Hai broker có thể cùng công bố một service theo OSB API nhưng khác nhau về tham số, hiệu năng, tính sẵn sàng, chính sách sao lưu và cách tính phí. Một plan tên production ở nhà cung cấp này không nhất thiết tương đương plan production ở nhà cung cấp khác.

Platform có thể dùng cùng một quy trình để tạo và binding, nhưng ứng dụng vẫn có thể phụ thuộc vào tính năng riêng của backing service. Vì vậy, khả năng chuyển đổi giữa các broker không tự động đồng nghĩa với khả năng chuyển ứng dụng và dữ liệu mà không cần thay đổi.

### 7.2. Broker không thay thế data plane

Broker quản lý vòng đời và cấp thông tin truy cập. Việc truyền dữ liệu, định tuyến mạng, kiểm soát lưu lượng, mã hóa đầu cuối và hiệu năng truy vấn vẫn phụ thuộc vào backing service cùng hạ tầng mạng.

Nếu ứng dụng không thể kết nối tới endpoint được trả về, thao tác provision thành công cũng chưa đủ để chứng minh dịch vụ đã sẵn sàng cho ứng dụng. Cần kiểm tra DNS, network policy, firewall, TLS, route và quyền truy cập ở môi trường triển khai.

### 7.3. Không có giao dịch phân tán và rollback tự động

Một thao tác có thể liên quan đến database, hệ thống IAM, secret store và nền tảng đám mây. OSB API không điều phối các hệ thống đó thành một giao dịch nguyên tử.

Broker phải tự thiết kế trạng thái trung gian, retry, timeout, bù trừ và đối soát. Có trường hợp không thể rollback hoàn toàn, chẳng hạn dữ liệu đã được ghi vào database trước khi một bước cấu hình sau đó thất bại. Những trường hợp như vậy cần chính sách xử lý và thông báo rõ ràng.

### 7.4. Vòng đời instance và binding có giới hạn biểu đạt

Mô hình service instance và binding phù hợp với nhiều dịch vụ hạ tầng, nhưng không phải mọi quy trình đều có thể biểu diễn tự nhiên bằng hai khái niệm này.

Một quy trình gồm nhiều tài nguyên có phụ thuộc phức tạp, nhiều giai đoạn phê duyệt hoặc cần tương tác liên tục có thể cần một lớp điều phối riêng. Broker vẫn có thể gọi workflow đó, nhưng platform chỉ nhìn thấy các thao tác và trạng thái mà broker biểu diễn qua OSB API.

### 7.5. Tính năng phụ thuộc vào platform

OSB API chuẩn hóa request và response, nhưng platform quyết định cách hiển thị catalog, cách gắn dịch vụ với ứng dụng, cách truyền context, cách xử lý credential và cách polling thao tác bất đồng bộ.

Cloud Foundry và một integration layer trên Kubernetes có thể có mô hình context, định danh và trải nghiệm người dùng khác nhau. Broker cần hiểu những khác biệt đó và kiểm thử với từng platform. Không nên coi việc một broker hoạt động trên một platform là bằng chứng rằng nó sẽ hoạt động nguyên trạng trên platform khác.

### 7.6. Broker trở thành thành phần quan trọng của hệ thống vận hành

Nếu broker ngừng hoạt động, platform có thể không tạo, cập nhật hoặc thu hồi được dịch vụ qua broker đó. Những ứng dụng đã có thông tin kết nối có thể vẫn tiếp tục giao tiếp trực tiếp với backing service, nhưng các thao tác quản lý vòng đời sẽ bị ảnh hưởng.

Do đó broker cần được triển khai với khả năng quan sát, log, metric, cảnh báo, sao lưu trạng thái và phục hồi phù hợp. Cần theo dõi cả trạng thái broker lẫn trạng thái tài nguyên phía nhà cung cấp để phát hiện sai lệch.

### 7.7. OSB API không cung cấp sẵn toàn bộ năng lực quản trị

Đặc tả không tự cung cấp hệ thống billing, quota tổng thể, SLA, backup, disaster recovery, audit, quản lý chi phí hoặc quy trình hỗ trợ người dùng. Broker hoặc các hệ thống xung quanh phải bổ sung những năng lực này nếu yêu cầu vận hành cần đến.

Các chính sách như giới hạn số instance trên mỗi tenant, giới hạn dung lượng, thời gian lưu giữ dữ liệu sau khi xóa và quy trình khôi phục cần được thiết kế riêng. Việc công bố plan trong catalog không tự động thực thi tất cả các chính sách đó.

## 8. Ví dụ chọn mô hình cho một dịch vụ PostgreSQL

Giả sử một tổ chức cung cấp PostgreSQL cho các nhóm phát triển. Mỗi nhóm có thể chọn plan small hoặc production.

1. Broker công bố service PostgreSQL cùng hai plan trong catalog.
2. Platform hiển thị catalog cho người dùng có quyền.
3. Người dùng chọn plan small và yêu cầu tạo service instance.
4. Broker xác thực yêu cầu, lưu trạng thái và gọi API của hạ tầng để tạo database.
5. Nếu quá trình tạo kéo dài, broker trả trạng thái xử lý bất đồng bộ; platform truy vấn last_operation cho đến khi hoàn tất.
6. Người dùng gắn service instance với ứng dụng. Platform gọi binding; broker tạo user riêng và trả thông tin kết nối.
7. Ứng dụng sử dụng credential được cấp để kết nối trực tiếp tới PostgreSQL.
8. Khi ứng dụng ngừng sử dụng database, platform gọi unbind để thu hồi user hoặc quyền truy cập tương ứng.
9. Khi người dùng yêu cầu xóa service instance, platform gọi deprovision; broker áp dụng chính sách dữ liệu rồi xóa tài nguyên.

Trong ví dụ này, OSB API giúp chuẩn hóa cách platform yêu cầu dịch vụ và theo dõi vòng đời. Broker vẫn phải tự quyết định cách tạo database, cách tạo user, chính sách sao lưu, cách xử lý dữ liệu khi xóa và cách phục hồi nếu nhà cung cấp gặp lỗi.

Nếu tổ chức muốn dùng cùng broker cho Cloud Foundry và Kubernetes, cần kiểm tra cách mỗi platform gửi context, quản lý binding và xử lý trạng thái. Có thể cần adapter hoặc cấu hình riêng để chuyển mô hình của từng platform về cùng logic nghiệp vụ của broker.

## 9. Bảng quyết định áp dụng

| Nhu cầu | Mức độ phù hợp | Lý do |
|---|---|---|
| Cấp phát database hoặc message broker theo yêu cầu | Cao | Có service instance, plan và vòng đời rõ ràng |
| Cấp credential riêng cho từng ứng dụng | Cao | Binding biểu diễn quyền truy cập của consumer |
| Quản lý nhiều nhà cung cấp qua một giao thức | Cao | OSB API chuẩn hóa cách platform gọi broker |
| Dịch vụ cần tạo tài nguyên lâu và theo dõi tiến trình | Cao nếu platform hỗ trợ async | Có thể dùng thao tác bất đồng bộ và truy vấn trạng thái |
| Một endpoint cố định, không cần cấp phát hoặc thu hồi | Thấp | Không có nhiều lợi ích từ mô hình instance và binding |
| Tác vụ ngắn cho từng request của ứng dụng | Thấp | Vòng đời service instance không phù hợp với từng request |
| Workflow nhiều bước cần phê duyệt và điều phối phức tạp | Tùy trường hợp | Có thể cần workflow engine hoặc lớp điều phối bổ sung |
| Dịch vụ yêu cầu tính năng riêng của một nhà cung cấp | Có điều kiện | Giao thức chung không loại bỏ khác biệt về ngữ nghĩa dịch vụ |

Trước khi chọn OSB API, nhóm kiến trúc nên trả lời được các câu hỏi: platform nào sẽ gọi broker; phiên bản API nào được hỗ trợ; service và plan được định danh ra sao; thao tác nào có thể bất đồng bộ; trạng thái được lưu ở đâu; retry có an toàn không; binding chứa những quyền gì; và dữ liệu được xử lý thế nào khi deprovision.

## 10. Checklist triển khai

Có thể dùng checklist sau trong giai đoạn thiết kế và tích hợp:

- [ ] Platform hoặc adapter đã xác nhận hỗ trợ OSB API và phiên bản tương ứng.
- [ ] Broker công bố catalog với service ID, plan ID và khả năng binding chính xác.
- [ ] Các thao tác provision, update, bind, unbind và deprovision có định nghĩa rõ.
- [ ] Hệ thống phía sau có API hoặc cơ chế tự động hóa cần thiết.
- [ ] Trạng thái instance, binding và thao tác được lưu bền vững.
- [ ] Retry không tạo tài nguyên hoặc credential trùng lặp.
- [ ] Thao tác dài có cơ chế bất đồng bộ và truy vấn trạng thái.
- [ ] TLS, xác thực, phân quyền tenant và bảo vệ secret đã được thiết kế.
- [ ] Có cách phục hồi khi broker hoặc nhà cung cấp lỗi giữa chừng.
- [ ] Có giám sát, log, cảnh báo và quy trình đối soát trạng thái tài nguyên.
- [ ] Chính sách backup, xóa dữ liệu, quota và hỗ trợ vận hành đã được xác định.
- [ ] Đã kiểm thử với từng platform mục tiêu, bao gồm các trường hợp timeout, retry và thao tác thất bại.

OSB API là lựa chọn phù hợp khi tổ chức cần một hợp đồng chung để platform quản lý dịch vụ có vòng đời rõ ràng. Hiệu quả của mô hình phụ thuộc vào khả năng tự động hóa của backing service, độ tin cậy của broker, cách platform tích hợp và các chính sách vận hành được xây dựng xung quanh. Spring Cloud Open Service Broker hỗ trợ phần triển khai hợp đồng trong ứng dụng Spring; logic cấp phát, bảo mật, trạng thái và tích hợp nhà cung cấp vẫn cần được thiết kế cho từng hệ thống cụ thể.

