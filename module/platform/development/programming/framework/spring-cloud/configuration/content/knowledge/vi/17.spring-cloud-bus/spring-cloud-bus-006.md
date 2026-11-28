# Địa chỉ đích cho toàn hệ thống, một dịch vụ hoặc một instance

Spring Cloud Bus phân phối sự kiện qua message broker để nhiều ứng dụng Spring Cloud có thể nhận cùng một thông báo, chẳng hạn yêu cầu refresh cấu hình. Khi phát sự kiện, người vận hành có thể chọn phạm vi nhận: toàn bộ hệ thống, tất cả instance của một dịch vụ hoặc một instance cụ thể.

Phạm vi này được xác định bằng **destination pattern** so khớp với ID của ứng dụng trên Bus. Pattern giúp giới hạn tác động của một sự kiện, nhưng chỉ hoạt động chính xác khi mỗi instance có ID rõ ràng và duy nhất. Cần phân biệt destination pattern này với tên exchange hoặc topic mà broker dùng để vận chuyển sự kiện: hai giá trị phục vụ hai mục đích khác nhau.

Bài học này giải thích cách Spring Cloud Bus định danh instance, cách chọn đích broadcast, service-level và instance-level, cách gửi refresh hoặc thay đổi Environment tới phạm vi mong muốn, cũng như cách bảo vệ endpoint và xác minh sự kiện đã được xử lý.

Sau bài học, bạn có thể:

- Phân biệt đích logic của sự kiện Bus với exchange/topic vật lý trên broker.
- Giải thích vai trò của <code>spring.cloud.bus.id</code> và tính duy nhất của instance ID.
- Gửi sự kiện tới toàn hệ thống, mọi instance của một dịch vụ hoặc một instance cụ thể.
- Dùng destination pattern theo quy tắc PathMatcher.
- Chọn phạm vi phù hợp cho <code>busrefresh</code> và <code>busenv</code>.
- Kiểm tra broker, endpoint, ID và trạng thái xử lý khi sự kiện không tới đúng đích.
- Giới hạn quyền phát sự kiện để tránh refresh ngoài phạm vi cần thiết.

## 1. Destination trong Spring Cloud Bus có nghĩa gì?

Một hệ thống có thể gồm nhiều ứng dụng và nhiều replica:

~~~mermaid
flowchart TD
    O["Operator / automation"] -->|"POST busrefresh + destination"| A["Một Bus instance"]
    A --> B["Message broker"]
    B --> C["orders-service instance 1"]
    B --> D["orders-service instance 2"]
    B --> E["inventory-service instance 1"]
    B --> F["billing-service instance 1"]
    C --> G["Match destination?"]
    D --> H["Match destination?"]
    E --> I["Match destination?"]
    F --> J["Match destination?"]
~~~

Một Bus event có thể mang thông tin nguồn phát và destination pattern. Các ứng dụng tham gia cùng Bus nhận sự kiện từ broker; mỗi instance so khớp destination với ID của chính nó để quyết định có thực hiện hành động hay không.

Destination pattern trả lời câu hỏi: **instance nào được yêu cầu xử lý sự kiện?**

Nó không phải địa chỉ HTTP của instance, IP, hostname hay tên queue riêng cho từng ứng dụng. Người vận hành không cần gọi trực tiếp từng replica. Họ gửi một sự kiện lên Bus và để cơ chế định tuyến logic chọn các instance phù hợp.

Ví dụ:

- <code>**</code>: tất cả instance tham gia Bus.
- <code>orders-service:**</code>: tất cả instance có Bus ID nằm trong nhóm <code>orders-service</code>.
- <code>orders-service:8082:pod-7</code>: một instance có Bus ID chính xác như chuỗi này.

Các chuỗi ví dụ phụ thuộc quy ước ID của hệ thống. Nếu Bus ID thực tế không có tiền tố <code>orders-service</code>, pattern <code>orders-service:**</code> sẽ không khớp.

## 2. Bus ID xác định từng instance

Mỗi ứng dụng tham gia Bus có một ID để phân biệt nó với các instance khác. Thuộc tính cấu hình quan trọng là:

~~~yaml
spring:
  cloud:
    bus:
      id: orders-service:8082:pod-7
~~~

Trong ví dụ, <code>orders-service:8082:pod-7</code> là ID minh họa của một instance. Một cách tổ chức thường dùng là ghép tên ứng dụng với port và một định danh instance do nền tảng cấp.

Có thể cấu hình động:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    bus:
      id: "${spring.application.name}:${server.port}:${INSTANCE_ID}"
~~~

<code>INSTANCE_ID</code> nên được nền tảng triển khai cấp riêng cho từng replica, ví dụ pod name, container ID rút gọn hoặc instance index ổn định trong vòng đời process. Nếu các replica dùng chung một ID, destination cụ thể có thể khớp nhiều instance hoặc sự kiện bị xử lý không rõ ràng.

### Đừng mặc định ID chỉ có application name

Nếu mọi replica đều có ID là <code>orders-service</code>, Bus không thể phân biệt một instance với instance khác. Khi cần target một replica, ID phải mang thành phần phân biệt instance.

Một số phiên bản hoặc môi trường có thể tự tạo Bus ID từ tên ứng dụng, port, index hoặc giá trị ngẫu nhiên. Cấu trúc mặc định có thể khác nhau theo phiên bản và môi trường triển khai. Khi vận hành, hãy kiểm tra ID thực tế của từng instance; nếu cần một quy ước ổn định, cấu hình <code>spring.cloud.bus.id</code> tường minh.

### Quy tắc cho ID

- Duy nhất giữa các instance đang tham gia cùng Bus.
- Ổn định đủ lâu để người vận hành có thể xác định đích.
- Có tiền tố tên dịch vụ thống nhất nếu muốn dùng pattern theo service.
- Có thành phần phân biệt replica khi cần target một instance.
- Không chứa thông tin bí mật hoặc dữ liệu cá nhân.
- Không thay đổi tùy tiện giữa các lần restart nếu automation dựa vào ID.

## 3. Broadcast tới toàn bộ hệ thống

Khi muốn mọi instance tham gia Bus xử lý sự kiện, có thể gửi broadcast không chỉ rõ destination:

~~~http
POST /actuator/busrefresh
~~~

Hoặc dùng destination pattern tổng quát khi endpoint hỗ trợ path destination:

~~~http
POST /actuator/busrefresh/**
~~~

<code>**</code> là pattern rộng, thường khớp mọi Bus ID. Đây là phạm vi có tác động lớn nhất. Với thay đổi cấu hình chung, broadcast có thể phù hợp, nhưng cần xác thực candidate trước và theo dõi kết quả trên toàn bộ instance.

Ví dụ lệnh gọi minh họa:

~~~bash
curl -X POST \
  -H "Authorization: Bearer $BUS_OPERATOR_TOKEN" \
  https://config-admin.internal/actuator/busrefresh
~~~

Token trong ví dụ được cấp từ hệ thống xác thực của môi trường triển khai. Không ghi token thật vào script trong repository hoặc lịch sử shell dùng chung.

Broadcast không có nghĩa mọi instance sẽ đổi cấu hình cùng một thời điểm. Sự kiện được vận chuyển bất đồng bộ qua broker; mỗi instance xử lý theo thời điểm nhận được và theo trạng thái riêng.

## 4. Gửi sự kiện tới mọi instance của một dịch vụ

Khi thay đổi chỉ áp dụng cho một ứng dụng, hãy dùng pattern giới hạn theo tiền tố Bus ID của dịch vụ.

Ví dụ các instance có ID:

~~~text
orders-service:8081:pod-a
orders-service:8082:pod-b
orders-service:8083:pod-c
inventory-service:8081:pod-d
billing-service:8081:pod-e
~~~

Để refresh mọi instance của <code>orders-service</code>, gửi:

~~~http
POST /actuator/busrefresh/orders-service:**
~~~

Pattern <code>orders-service:**</code> khớp các ID bắt đầu bằng <code>orders-service:</code> và có phần tiếp theo bất kỳ. Các instance <code>inventory-service</code> và <code>billing-service</code> không thuộc phạm vi này.

Nếu ID được tổ chức theo môi trường, chẳng hạn:

~~~text
orders-service:prod:pod-a
orders-service:prod:pod-b
orders-service:staging:pod-c
~~~

có thể chọn pattern hẹp hơn:

~~~http
POST /actuator/busrefresh/orders-service:prod:**
~~~

Cách này hữu ích khi cùng một Bus có nhiều môi trường hoặc nhóm triển khai. Chỉ dùng pattern khi cấu trúc ID đã được chuẩn hóa và có kiểm thử khớp/không khớp.

### Service name phải khớp Bus ID

Destination pattern so khớp với Bus ID, không tự động suy luận từ tên deployment, Kubernetes Service hoặc Eureka service ID. Nếu ID thực tế được đặt là <code>orders:pod-a</code>, pattern <code>orders-service:**</code> sẽ không khớp.

Khi thiết kế, hãy chọn một quy ước duy nhất, ví dụ:

~~~text
<application-name>:<environment>:<instance-id>
~~~

Sau đó cấu hình tất cả replica theo cùng quy ước. Pattern theo dịch vụ và môi trường sẽ dễ đọc, dễ audit hơn.

## 5. Gửi sự kiện tới một instance cụ thể

Khi cần canary hoặc xử lý một replica lỗi, dùng pattern khớp đúng Bus ID của instance đó.

Với danh sách ID ở trên, có thể gửi:

~~~http
POST /actuator/busrefresh/orders-service:8082:pod-b
~~~

Đây là đích chính xác nếu instance đang có ID <code>orders-service:8082:pod-b</code>. Nếu ID được sinh tự động, hãy lấy giá trị đang hoạt động từ log hoặc thông tin chẩn đoán an toàn thay vì tự đoán từ port.

Một số lưu ý:

- Đảm bảo ID là duy nhất trong Bus.
- Xác nhận instance vẫn đang chạy và đã kết nối broker.
- Kiểm tra destination có khớp đúng một ID.
- Theo dõi log và metric của chính instance đó sau khi gửi.
- Nếu instance đã thay thế hoặc restart và ID thay đổi, cập nhật đích trước khi gửi lại.

Target một instance phù hợp để kiểm tra cấu hình mới trên canary. Sau khi instance đó vượt qua kiểm tra, có thể mở rộng tới nhóm dịch vụ hoặc toàn hệ thống.

## 6. PathMatcher và cách đọc destination pattern

Spring Cloud Bus dùng cơ chế so khớp pattern cho destination. Các ví dụ thông dụng sử dụng kiểu wildcard theo phong cách Ant:

| Pattern | Ý nghĩa dự kiến |
|---|---|
| <code>**</code> | Mọi Bus ID |
| <code>orders-service:**</code> | Mọi instance thuộc tiền tố <code>orders-service</code> |
| <code>orders-service:prod:**</code> | Mọi instance của orders trong môi trường prod nếu ID theo quy ước này |
| <code>orders-service:8082:pod-b</code> | ID chính xác của một instance |

Trong pattern, <code>*</code> thường khớp một phần trong một đoạn, còn <code>**</code> có thể khớp phần còn lại qua nhiều đoạn. Vì Bus ID thường là chuỗi có dấu phân cách như <code>:</code>, cần kiểm thử pattern với đúng <code>PathMatcher</code> và cấu trúc ID của phiên bản đang chạy.

Đừng coi ví dụ pattern là biểu thức regex. Không dùng các ký hiệu regex như <code>.*</code> trừ khi cơ chế matcher của ứng dụng được cấu hình rõ để hỗ trợ chúng.

Một test định tuyến nên kiểm tra cả hai trường hợp:

- **Positive match:** ID mong muốn được chọn.
- **Negative match:** ID ngoài phạm vi không xử lý event.

Điều này đặc biệt quan trọng với pattern rộng như <code>orders-service:**</code> hoặc <code>**</code>.

## 7. Destination pattern khác tên exchange/topic của broker

Spring Cloud Bus cần message broker để truyền sự kiện. Tùy dependency, broker có thể là RabbitMQ hoặc Kafka.

Một cấu hình minh họa:

~~~yaml
spring:
  cloud:
    bus:
      destination: springCloudBus
~~~

<code>spring.cloud.bus.destination</code> chỉ định tên destination vật lý mà Bus sử dụng trên broker theo binder và phiên bản tương ứng, ví dụ exchange hoặc topic. Nó không phải pattern chọn ứng dụng nhận sự kiện.

Hai lớp cần phân biệt:

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Broker destination | <code>springCloudBus</code> | Nơi message được publish/consume trên broker |
| Bus ID | <code>orders-service:8082:pod-b</code> | Danh tính một instance |
| Event destination pattern | <code>orders-service:**</code> | Chọn instance nào xử lý event |

Nếu đổi tên broker destination, tất cả ứng dụng tham gia cùng Bus phải được cấu hình tương thích để cùng giao tiếp trên đúng broker destination. Nếu một nhóm client nghe topic khác, chúng sẽ không nhận được sự kiện dù destination pattern đúng.

Ngược lại, nếu broker destination giống nhau nhưng pattern không khớp Bus ID, message có thể tới ứng dụng nhưng ứng dụng không thực hiện hành động.

### Ví dụ với RabbitMQ và Kafka

Với RabbitMQ, Bus thường dùng exchange để fan-out hoặc định tuyến thông điệp theo cấu hình binder. Với Kafka, Bus thường dùng topic mà các instance subscribe. Tên vật lý, kiểu exchange, consumer group và cấu hình binder phụ thuộc starter và phiên bản.

Không tự tạo một queue riêng theo từng Bus ID chỉ vì muốn gửi tới một instance. Việc chọn instance được thực hiện bằng event destination matching của Bus; topology broker vẫn cần theo mô hình mà binder của Spring Cloud Bus yêu cầu.

## 8. Dùng destination cho busrefresh và busenv

Spring Cloud Bus có thể phát nhiều loại remote event. Hai endpoint thường gặp là:

- <code>POST /actuator/busrefresh</code>: yêu cầu client refresh cấu hình.
- <code>POST /actuator/busenv</code>: phát thay đổi Environment, chẳng hạn cập nhật một thuộc tính cho các instance được chọn.

Có thể kết hợp destination với từng endpoint nếu phiên bản đang dùng cung cấp mapping path tương ứng:

~~~http
POST /actuator/busrefresh/orders-service:**
POST /actuator/busenv/orders-service:prod:**
~~~

<code>busrefresh</code> thường khiến client lấy lại cấu hình từ Config Server và làm mới các thành phần hỗ trợ refresh. <code>busenv</code> gửi một thay đổi Environment qua Bus; nó không thay thế quy trình quản trị cấu hình trong Git và cần được dùng thận trọng vì có thể tạo trạng thái khác với nguồn cấu hình chuẩn.

Với <code>busenv</code>, cần xác định chính xác key, value, phạm vi và thời gian tồn tại theo phiên bản. Không dùng endpoint này để truyền secret hoặc dữ liệu nhạy cảm trong payload.

Các endpoint và cách expose có thể thay đổi theo phiên bản Spring Cloud. Kiểm tra endpoint thực tế đã được Actuator đăng ký trước khi đưa vào automation.

## 9. Chọn phạm vi theo mục tiêu vận hành

Không phải mọi thay đổi đều cần broadcast.

| Tình huống | Phạm vi nên cân nhắc | Lý do |
|---|---|---|
| Thay đổi một tham số chỉ thuộc orders | <code>orders-service:**</code> | Không tác động ứng dụng khác |
| Kiểm tra candidate trên một replica | ID chính xác của canary | Giới hạn phạm vi thử nghiệm |
| Thay đổi cấu hình chung mà mọi ứng dụng sử dụng | <code>**</code> sau khi kiểm thử | Cần áp dụng rộng |
| Một replica bị lệch cấu hình | ID chính xác của replica | Sửa có mục tiêu |
| Thay đổi chỉ áp dụng orders production | <code>orders-service:prod:**</code> | Không chạm staging |
| Thay đổi broker hoặc topology Bus | Kế hoạch rollout hạ tầng riêng | Tất cả participant cần tương thích |

Một chiến lược an toàn là mở rộng phạm vi dần:

1. Gửi tới một instance canary.
2. Xác nhận refresh và luồng nghiệp vụ.
3. Gửi tới các replica còn lại của dịch vụ.
4. Theo dõi lỗi và config version.
5. Chỉ broadcast toàn hệ thống khi thay đổi thực sự áp dụng cho tất cả.

Nếu thay đổi có rủi ro cao, không dùng broadcast làm bước thử đầu tiên.

## 10. Cấu hình ID và broker trong ứng dụng

Ví dụ cấu hình cho một instance orders:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    bus:
      id: "${spring.application.name}:${server.port}:${INSTANCE_ID}"
      destination: springCloudBus
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    username: ${BUS_USERNAME}
    password: ${BUS_PASSWORD}
~~~

Trong ví dụ:

- <code>spring.application.name</code> giúp nhận diện dịch vụ.
- <code>spring.cloud.bus.id</code> định danh instance.
- <code>spring.cloud.bus.destination</code> chọn destination vật lý trên broker.
- Các thuộc tính RabbitMQ xác định kết nối tới broker.

Mỗi replica phải có <code>INSTANCE_ID</code> khác nhau. Nếu chạy nhiều ứng dụng trong nhiều môi trường, nên đưa môi trường vào ID để pattern có thể giới hạn đúng nhóm.

Với Kafka, cấu hình broker và binder sẽ khác; phần Bus ID và logic destination pattern vẫn là lớp định tuyến logic của Bus.

Không ghi username/password thật vào file cấu hình được commit. Dùng secret manager, biến môi trường hoặc cơ chế cấp credential của nền tảng. Trong production, kết nối broker nên dùng TLS và ACL giới hạn quyền publish/consume theo nhu cầu.

## 11. Bật và bảo vệ endpoint Bus

Để gọi endpoint từ HTTP, ứng dụng cần dependency Bus phù hợp, ví dụ starter Bus cho RabbitMQ hoặc Kafka, cùng Actuator.

Ví dụ expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh,busenv
~~~

Expose endpoint không đồng nghĩa endpoint đã được bảo vệ. Cần cấu hình Spring Security để chỉ tài khoản hoặc service account vận hành được phép gọi các POST endpoint.

Các biện pháp cần có:

- Chỉ mở endpoint Bus trong mạng quản trị hoặc qua gateway nội bộ.
- Yêu cầu xác thực mạnh và role riêng cho refresh.
- Phân biệt quyền broadcast toàn hệ thống với quyền target một dịch vụ.
- Kiểm tra destination pattern theo allowlist nếu có API điều phối bên ngoài.
- Ghi audit người gọi, thời điểm, endpoint, destination và event ID.
- Bảo vệ broker bằng TLS, authentication và ACL.
- Không ghi token, password hoặc payload secret vào log.

Quyền gọi <code>/actuator/busrefresh/**</code> có thể tác động tới nhiều dịch vụ. Hãy giới hạn quyền theo nguyên tắc tối thiểu và yêu cầu phê duyệt cho broadcast có phạm vi lớn.

## 12. Sự kiện bất đồng bộ: gửi thành công chưa phải xử lý thành công

Khi endpoint nhận request, ứng dụng phát một event lên Bus. Broker nhận và phân phối message theo topology đã cấu hình. Các instance nhận message rồi so khớp destination. Vì thế, HTTP response thành công từ endpoint chỉ xác nhận bước phát event được chấp nhận theo cơ chế hiện tại; nó không chứng minh mọi instance mục tiêu đã refresh thành công.

Có thể xảy ra:

- Instance đang dừng hoặc mất kết nối broker.
- Broker retry hoặc phân phối lại message.
- Instance nhận event nhưng refresh Config Server thất bại.
- Instance refresh thành công nhưng bean hoặc resource tạo lại lỗi ở request tiếp theo.
- Các replica xử lý event ở những thời điểm khác nhau.

Do đó, cần theo dõi kết quả ở từng instance:

- Bus ID và application name.
- Event ID hoặc correlation ID nếu có.
- Destination pattern.
- Config label/commit được nạp.
- Thời điểm nhận event và kết quả refresh.
- Lỗi trong quá trình bind hoặc khởi tạo bean.
- Readiness và metric nghiệp vụ sau refresh.

Nếu cần xác nhận đầy đủ, xây dựng cơ chế acknowledgement hoặc trạng thái rollout ở tầng vận hành. Không giả định Spring Cloud Bus tự cung cấp báo cáo hoàn tất đồng bộ cho toàn bộ instance.

## 13. Chẩn đoán khi destination không tới đúng đích

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không instance nào xử lý event | Broker destination sai hoặc không có consumer | Kiểm tra kết nối, topic/exchange và log binder |
| Tất cả ứng dụng đều refresh dù chỉ muốn một service | Pattern quá rộng hoặc Bus ID không theo quy ước | Ghi nhận ID thật và kiểm thử PathMatcher |
| Không instance nào trong service được chọn | Tiền tố pattern không khớp Bus ID | So sánh <code>spring.cloud.bus.id</code> với destination |
| Một instance cụ thể không nhận mục tiêu | ID sai, instance đã restart hoặc trùng ID | Lấy ID hiện tại từ đúng replica |
| Event tới broker nhưng không có hành động | Destination không match hoặc event type không được hỗ trợ | Kiểm tra matcher và loại event |
| Một số replica refresh, số khác không | Mất kết nối broker, consumer lỗi hoặc replica chưa sẵn sàng | Kiểm tra trạng thái từng instance |
| Endpoint trả 401/403 | Thiếu quyền hoặc token không hợp lệ | Kiểm tra security policy |
| Endpoint trả 404 | Endpoint chưa được bật/expose hoặc mapping khác phiên bản | Kiểm tra dependency và Actuator mappings |
| Refresh xử lý nhưng luồng vẫn lỗi | Cấu hình mới sai hoặc bean không hỗ trợ refresh | Kiểm tra config version, binding và resource lifecycle |

Quy trình kiểm tra nên đi theo thứ tự:

1. Xác nhận endpoint và loại event được bật.
2. Xác nhận ứng dụng phát event kết nối được broker.
3. Xác nhận tất cả participant dùng đúng broker destination.
4. Lấy Bus ID thực tế của các instance mục tiêu.
5. Kiểm tra pattern có match đúng các ID đó hay không.
6. Kiểm tra log nhận event và kết quả refresh của từng instance.
7. So sánh Config Server label/commit và giá trị hiệu lực sau refresh.

Không dùng một lần gọi thành công ở node phát làm bằng chứng rằng tất cả node mục tiêu đã xử lý.

## 14. Ví dụ hoàn chỉnh: refresh canary, dịch vụ rồi toàn hệ thống

Giả sử các instance có ID:

~~~text
orders-service:prod:pod-a
orders-service:prod:pod-b
inventory-service:prod:pod-c
billing-service:prod:pod-d
~~~

**Bước 1: Canary một instance orders**

~~~http
POST /actuator/busrefresh/orders-service:prod:pod-a
~~~

Kiểm tra pod-a đã nạp đúng label và luồng nghiệp vụ hoạt động.

**Bước 2: Mở rộng tới orders production**

~~~http
POST /actuator/busrefresh/orders-service:prod:**
~~~

Theo dõi cả pod-a và pod-b, xác nhận chúng cùng dùng phiên bản cấu hình dự kiến.

**Bước 3: Broadcast toàn hệ thống nếu thay đổi là cấu hình chung**

~~~http
POST /actuator/busrefresh/**
~~~

Theo dõi orders, inventory và billing. Nếu chỉ thay đổi thuộc orders, dừng ở bước 2; không cần broadcast.

Ví dụ này giả định Bus ID đã được cấu hình theo đúng quy ước. Trước khi chạy trong production, hãy xác nhận path destination, PathMatcher, endpoint mapping và quyền vận hành của phiên bản Spring Cloud đang sử dụng.

## 15. Checklist thiết kế destination và vận hành

- [ ] Mỗi instance có Bus ID duy nhất trong hệ thống.
- [ ] Bus ID có quy ước tiền tố ứng dụng và định danh replica rõ ràng.
- [ ] Đã kiểm tra ID thực tế thay vì giả định cấu trúc mặc định.
- [ ] Đã phân biệt destination pattern với <code>spring.cloud.bus.destination</code> của broker.
- [ ] Đã kiểm thử pattern <code>**</code>, pattern theo service và ID cụ thể.
- [ ] Đã xác nhận endpoint <code>busrefresh</code>/<code>busenv</code> và path mapping theo phiên bản.
- [ ] Đã chọn phạm vi nhỏ nhất phù hợp với thay đổi.
- [ ] Canary được refresh và kiểm tra trước khi mở rộng.
- [ ] Broker có TLS, authentication và ACL phù hợp.
- [ ] Actuator POST endpoints chỉ mở cho danh tính vận hành được phép.
- [ ] Có audit người gọi, destination, event và thời điểm.
- [ ] Theo dõi kết quả xử lý trên từng instance; không chỉ dựa vào HTTP response của node phát.
- [ ] Có kế hoạch xử lý instance offline, event retry và refresh thất bại.
- [ ] Không truyền hoặc log secret trong event payload.

Spring Cloud Bus cho phép gửi cùng một loại sự kiện tới các phạm vi khác nhau bằng destination pattern: toàn hệ thống, nhóm instance của một dịch vụ hoặc một instance cụ thể. Muốn định tuyến đáng tin cậy, cần đặt Bus ID duy nhất theo quy ước, giữ broker destination thống nhất giữa các participant và xác minh pattern khớp đúng ID runtime. Kết hợp canary, bảo mật endpoint và theo dõi kết quả từng instance giúp sự kiện refresh được phát đúng phạm vi và có thể kiểm chứng sau khi gửi.

