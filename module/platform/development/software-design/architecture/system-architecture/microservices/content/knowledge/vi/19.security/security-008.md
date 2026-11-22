# Bảo vệ broker, hàng đợi và quyền xuất bản hoặc nhận thông điệp

**Phạm vi:** Bảo mật trong kiến trúc hệ thống và microservices; áp dụng cho các hệ thống truyền thông điệp như Kafka, RabbitMQ và dịch vụ hàng đợi được quản lý. Bài học tập trung vào ranh giới tin cậy, xác thực dịch vụ, phân quyền xuất bản/nhận thông điệp, bảo vệ dữ liệu và vận hành an toàn.

Một hệ thống dùng thông điệp thường có nhiều dịch vụ giao tiếp gián tiếp. Order Service phát sự kiện tạo đơn hàng, Payment Service và Inventory Service nhận sự kiện để thực hiện công việc tương ứng. Broker giúp tách thời điểm gửi và nhận, nhưng cũng trở thành một điểm tập trung của **quyền truy cập, dữ liệu nhạy cảm và khả năng gây ảnh hưởng đến nhiều dịch vụ cùng lúc**.

Nếu một dịch vụ bị chiếm quyền có thể xuất bản thông điệp lên mọi topic, kẻ tấn công có thể giả mạo sự kiện thanh toán. Nếu một tài khoản có thể đọc mọi queue, dữ liệu khách hàng của nhiều nghiệp vụ có thể bị lộ. Nếu một client được phép xóa topic, thay đổi quyền hoặc tạo hàng nghìn kết nối, toàn bộ luồng xử lý có thể ngừng hoạt động. Vì vậy, bảo mật broker phải được thiết kế như một **ranh giới tin cậy riêng**, kể cả khi các dịch vụ đều chạy trong mạng nội bộ.

Mục tiêu của bài: xác định ai được kết nối, ai được làm gì trên tài nguyên nào, thông điệp nào được tin cậy, và cách giới hạn thiệt hại khi một danh tính hoặc một dịch vụ gặp sự cố.

## 1. Mô hình tư duy: broker là điểm kiểm soát, không phải nơi mọi dịch vụ được tin cậy như nhau

~~~mermaid
flowchart LR
    O[Order Service] -->|publish| B[(Message Broker)]
    B -->|consume| P[Payment Service]
    B -->|consume| I[Inventory Service]
    B -->|consume| A[Analytics Service]
    M[Platform Admin] -->|quản trị có kiểm soát| B
    X[Ứng dụng lạ / tài khoản bị lộ] -.->|phải bị từ chối| B
~~~

Dù tất cả mũi tên cùng đi qua broker, chúng phải mang **danh tính và quyền khác nhau**. Một kết nối TCP tới broker không đồng nghĩa client được quyền xem mọi topic, tạo queue, sửa cấu hình hoặc đọc dữ liệu của dịch vụ khác.

Có bốn câu hỏi cần trả lời riêng biệt:

1. **Kết nối có được phép không?** Network policy, firewall, private endpoint, TLS và giới hạn nguồn kết nối.
2. **Client là ai?** Xác thực bằng danh tính dịch vụ, chứng chỉ, cơ chế SASL, IAM hoặc token phù hợp với broker.
3. **Client được làm gì?** Phân quyền theo tài nguyên và thao tác: publish, consume, subscribe, tạo/xóa/chỉnh sửa topology, quản lý consumer group, quản trị cluster.
4. **Thông điệp có hợp lệ và an toàn không?** Schema, nguồn phát, phiên bản, nội dung, độ nhạy, tính toàn vẹn, chống trùng lặp và quy tắc xử lý.

Bốn câu hỏi bổ sung cho nhau. Mạng riêng giúp giảm bề mặt tấn công nhưng không thay thế xác thực. Xác thực đúng danh tính không tự động cho quyền publish. ACL đúng cũng không bảo đảm payload do một producer đã được cấp quyền luôn đúng nghiệp vụ.

## 2. Phân biệt broker, topic, exchange, queue và consumer group

Các broker không dùng cùng mô hình tài nguyên, nên chính sách bảo mật phải bám sát cơ chế thực tế.

| Khái niệm | Vai trò | Điểm cần bảo vệ |
|---|---|---|
| **Broker/cluster** | Hạ tầng nhận, lưu, định tuyến hoặc phân phối thông điệp | Cổng kết nối, tài khoản quản trị, cấu hình TLS, API điều hành |
| **Topic (Kafka)** | Luồng bản ghi được phân vùng, có retention; nhiều consumer group có thể đọc độc lập | Quyền Write/Read/Describe/Alter/Create theo chính sách |
| **Consumer group (Kafka)** | Nhóm phối hợp đọc, phân chia partition và theo dõi offset | Quyền tham gia/đọc group, tránh nhóm lạ can thiệp tiến độ |
| **Exchange (RabbitMQ)** | Điểm producer publish đến; định tuyến theo binding/routing key | Quyền publish, thiết lập và thay đổi tuyến |
| **Queue (RabbitMQ)** | Nơi consumer lấy thông điệp; nhiều consumer có thể cạnh tranh đọc | Quyền consume, quyền thao tác queue và ảnh hưởng đến backlog |
| **Virtual host (RabbitMQ)** | Không gian tên và ranh giới quyền trong cùng broker | Phân quyền theo vhost, tránh tài khoản dùng chung |
| **DLQ/DLT** | Hàng đợi/topic chứa thông điệp xử lý thất bại | Quyền xem, ghi, phát lại, retention và dữ liệu nhạy cảm |

**Kafka:** producer ghi vào topic; consumer đọc topic và tham gia một consumer group. Việc có quyền đọc topic không nhất thiết đủ nếu broker còn yêu cầu quyền trên group. Topic không hoạt động như một queue RabbitMQ bị xóa thông điệp ngay khi một consumer ACK.

**RabbitMQ:** producer thường publish vào exchange; exchange định tuyến đến queue dựa trên binding; consumer đọc từ queue. Phân quyền configure/write/read áp dụng theo tên tài nguyên trong vhost, và một số loại exchange còn có chính sách riêng như quyền topic theo routing key. Quyền publish vào exchange không mặc nhiên cấp quyền đọc queue đích.

**Các dịch vụ quản lý như SQS, SNS hoặc Pub/Sub:** danh tính và quyền thường biểu diễn qua IAM, resource policy hoặc service account. Phải đọc ma trận hành động của từng nhà cung cấp: tên thao tác và phạm vi quyền không hoàn toàn tương ứng với Kafka/RabbitMQ.

Không được sao chép nguyên cấu hình ACL của broker này sang broker khác chỉ vì cả hai đều có khái niệm producer và consumer.

## 3. Mô hình đe dọa: điều gì xảy ra khi một ranh giới bị vượt qua?

### 3.1. Giả mạo producer

Kẻ tấn công hoặc dịch vụ bị chiếm quyền gửi sự kiện **OrderPaid**, **RefundApproved** hoặc **UserRoleChanged** giả. Consumer có thể tin payload và thực hiện thanh toán, chuyển trạng thái hoặc mở quyền sai. Rủi ro đặc biệt lớn nếu sự kiện được dùng như một mệnh lệnh nghiệp vụ mà không kiểm tra nguồn và trạng thái.

### 3.2. Đọc trái phép

Một consumer với quyền đọc rộng có thể trích xuất PII, địa chỉ, token hoặc thông tin giao dịch từ topic và DLQ. Retention dài làm tăng khoảng thời gian dữ liệu có thể bị lấy. Dữ liệu trong header, key, partition key và log lỗi cũng có thể nhạy cảm.

### 3.3. Leo thang quyền quản trị

Tài khoản ứng dụng được cấp quyền create/alter/delete quá rộng có thể đổi retention, xóa queue/topic, thiết lập binding đến nơi ngoài ý muốn, sửa ACL hoặc tạo tài nguyên gây cạn dung lượng. Một credential dùng chung với tài khoản vận hành khiến không thể xác định dịch vụ gây thay đổi.

### 3.4. Từ chối dịch vụ

Producer gửi message quá lớn, hàng loạt message, payload nén bất thường hoặc tạo vô số kết nối. Consumer có thể giữ ACK, xử lý quá chậm hoặc gây retry liên tục khiến backlog tăng. Tấn công có thể xảy ra cả khi tài khoản có quyền publish hợp lệ.

### 3.5. Phát lại và xử lý trùng

Một thông điệp bị phát lại từ DLQ hoặc consumer xử lý lại sau lỗi mạng có thể gây tác dụng phụ lặp: trừ tiền hai lần, gửi email hai lần, tạo hai đơn. Cơ chế delivery ít nhất một lần (at-least-once) đòi hỏi thiết kế idempotency; quyền truy cập broker không tự loại bỏ lỗi nghiệp vụ này.

### 3.6. Lộ bí mật kết nối

Mật khẩu SASL, khóa riêng TLS, token hoặc chuỗi kết nối trong log, image, repository, cấu hình CI/CD và dashboard có thể cho phép kẻ tấn công hành động như một dịch vụ hợp lệ. Cần xem credential của broker là bí mật có vòng đời quản lý rõ ràng.

**Ranh giới bảo vệ** gồm client → broker, broker → broker/replica, client → schema registry, công cụ quản trị → broker và hệ thống quản lý khóa → broker. Mỗi ranh giới cần quyết định riêng về danh tính, quyền, TLS, logging và khả năng thu hồi.

## 4. Nguyên tắc thiết kế quyền: tối thiểu, tách vai trò và mặc định từ chối

Chính sách bảo mật nên xuất phát từ các quy tắc sau:

1. **Danh tính riêng cho từng workload**: Order Service, Payment Service và công cụ vận hành dùng các principal/service account khác nhau. Tránh một tài khoản chung cho nhiều ứng dụng.
2. **Chỉ cấp thao tác cần dùng**: producer cần publish thì không mặc nhiên có consume; consumer không mặc nhiên có configure hoặc delete.
3. **Chỉ cấp tài nguyên cần dùng**: ưu tiên tên topic/queue/exchange cụ thể hoặc namespace hẹp; tránh wildcard trên toàn cluster.
4. **Tách người vận hành khỏi ứng dụng**: provisioning topology, thay đổi ACL, xóa dữ liệu, thay retention là quyền quản trị, cấp cho công cụ/role riêng.
5. **Mặc định từ chối**: không có quyền phù hợp thì broker phải từ chối. Cấu hình “allow all” dùng cho chạy thử không được tồn tại trong môi trường nhiều dịch vụ.
6. **Phạm vi theo môi trường**: tài khoản development không sử dụng credential hoặc quyền trên production.
7. **Quyền có thời hạn và có thể thu hồi**: có cơ chế xoay khóa, vô hiệu hóa credential, thu hồi token/chứng chỉ và xác định tác động.
8. **Lưu dấu vết thay đổi chính sách**: ai sửa ACL, đổi principal, thay cấu hình broker và từ lúc nào.

Một ứng dụng đã được cấp **Write** lên topic A có thể gửi nhiều loại payload về mặt kỹ thuật; người thiết kế vẫn phải áp dụng quy tắc nghiệp vụ để không biến quyền ghi vào topic thành quyền thực thi hành động bất kỳ. Điều này đặc biệt quan trọng với các sự kiện có tác dụng phụ mạnh.

## 5. Bảng phân quyền cho hệ thống đặt hàng

Giả sử hệ thống có Order Service, Payment Service, Inventory Service, Analytics Service và một nhóm quản trị hạ tầng. Ta định nghĩa:

- Luồng sự kiện **orders.created** do Order Service phát.
- Luồng **payments.completed** do Payment Service phát sau khi đã xác nhận thanh toán.
- Consumer group **payment-workers** và **inventory-workers** xử lý đơn hàng độc lập.
- Analytics Service nhận bản sao dữ liệu đã được giảm nhạy cảm hoặc chỉ nhận các trường được phép.
- Platform Admin quản lý topology/ACL qua quy trình thay đổi được kiểm soát.

| Danh tính | Được phép | Không được mặc định cấp |
|---|---|---|
| **order-service** | Publish orders.created; đọc các luồng phản hồi cần thiết nếu được thiết kế | Đọc mọi sự kiện thanh toán, xóa topic, sửa ACL |
| **payment-service** | Consume orders.created bằng group payment-workers; publish payments.completed | Publish orders.created, đọc queue riêng của Inventory, quản trị broker |
| **inventory-service** | Consume orders.created bằng group inventory-workers; publish sự kiện tồn kho của mình | Consume dữ liệu thanh toán nhạy cảm, alter topic |
| **analytics-service** | Consume topic dữ liệu đã chọn/làm sạch bằng group của Analytics | Đọc mọi topic gốc chứa PII, publish sự kiện nghiệp vụ |
| **platform-provisioner** | Tạo tài nguyên và áp ACL theo mẫu được duyệt | Sử dụng thông thường như producer/consumer nghiệp vụ |
| **platform-observer** | Xem metric và thông tin vận hành cần thiết | Đọc payload nhạy cảm hoặc xóa thông điệp chỉ vì cần dashboard |

Bảng trên là **ma trận quyền nghiệp vụ**, chưa phải cú pháp áp dụng cho một broker cụ thể. Khi triển khai, phải ánh xạ sang đầy đủ resource, operation và scope mà broker yêu cầu.

Quyền tối thiểu còn cần xét các phụ thuộc phụ: consumer group, transaction ID, schema registry subject, topic retry, DLQ, queue reply, routing key, namespace và tác vụ khởi tạo. Những quyền này không nên được cấp rộng chỉ để “ứng dụng kết nối được”.

## 6. Xác thực dịch vụ: chứng minh client thực sự là ai

### 6.1. TLS và mTLS

**TLS** bảo vệ dữ liệu khi truyền giữa client và broker trước nghe lén và sửa đổi trên đường mạng. Client phải kiểm tra chứng chỉ server, tên máy chủ và chuỗi tin cậy; tắt xác minh certificate/hostname làm giảm mạnh tác dụng bảo vệ.

**mTLS** bổ sung chứng chỉ client để broker xác thực danh tính phía gọi. Danh tính trích ra từ chứng chỉ phải được map một cách ổn định sang principal/role phù hợp. Chứng chỉ không nên được sao chép giữa nhiều dịch vụ.

Quản lý chứng chỉ phải bao gồm:
- Cấp phát từ CA tin cậy của môi trường, bảo vệ private key và phân quyền đọc file/secret.
- Theo dõi hạn chứng chỉ, gia hạn và xoay vòng trước khi hết hạn.
- Xác định điều gì xảy ra khi chứng chỉ hoặc CA bị thu hồi.
- Cấu hình hostname/SAN đúng, đồng bộ cơ chế truststore trên từng client.
- Xem riêng kết nối giữa các node broker, controller, proxy, replication và công cụ quản trị.

Mạng private hoặc service mesh hỗ trợ bảo vệ đường truyền nhưng **không tự cấp đúng quyền đọc/ghi trên từng topic/queue**. Khi terminate TLS ở proxy, phải hiểu đoạn kết nối còn lại có được mã hóa và xác thực hay không.

### 6.2. SASL, token và IAM

Kafka có thể dùng các cơ chế SASL phù hợp như SCRAM hoặc OAuth, kết hợp TLS theo cấu hình. Một số môi trường cũng xác thực bằng mTLS hoặc cơ chế IAM của nhà cung cấp. RabbitMQ thường dùng user/vhost với cơ chế xác thực, TLS hoặc plugin xác thực bổ sung. Broker managed có thể nhận service account và IAM.

Không chọn cơ chế chỉ vì “cấu hình ít nhất”. Hãy xem khả năng **cấp phát tự động, xoay vòng, thu hồi, phạm vi quyền, kiểm toán và tương thích client**.

Bí mật kết nối nên được nạp từ secret manager hoặc nguồn bí mật có kiểm soát; không đặt mật khẩu trong source code, tài liệu, Docker image hoặc đầu ra debug. Hạn chế in header authorization, chuỗi kết nối và payload khi lỗi.

### 6.3. Xác thực không đồng nghĩa phân quyền

Một client có thể được xác thực thành công rồi vẫn phải nhận lỗi **authorization denied** khi cố publish sai topic hoặc tham gia group không được phép. Đây là hành vi đúng. Không “chữa” lỗi bằng quyền wildcard trước khi xác định chính xác resource bị từ chối.

Lưu ý: cơ chế xác thực, principal và danh sách thao tác trong ACL thay đổi theo sản phẩm/phiên bản/nhà cung cấp. Cần dùng tài liệu tương ứng với cụm đang vận hành để kiểm tra khả năng hỗ trợ.

## 7. Kafka: ACL theo principal, topic, consumer group và tác vụ quản trị

Ở mô hình Kafka, một policy thường được biểu diễn qua **principal – operation – resource – pattern**. Ví dụ:

| Principal | Resource | Operation | Mục đích |
|---|---|---|---|
| User:order-service | Topic orders.created | Write | Phát sự kiện đơn hàng |
| User:payment-service | Topic orders.created | Read | Đọc sự kiện đơn hàng |
| User:payment-service | Group payment-workers | Read | Tham gia nhóm xử lý payment |
| User:payment-service | Topic payments.completed | Write | Phát kết quả thanh toán |
| User:inventory-service | Topic orders.created | Read | Đọc sự kiện để giữ hàng |
| User:inventory-service | Group inventory-workers | Read | Tham gia nhóm xử lý inventory |

Minh họa tạo ACL qua Kafka CLI; lệnh thực tế cần tham số kết nối bảo mật và quyền quản trị riêng:

~~~bash
# Người vận hành với principal quản trị, không chạy bằng tài khoản ứng dụng.
kafka-acls.sh \
  --bootstrap-server kafka.internal.example:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:order-service \
  --operation Write \
  --topic orders.created

kafka-acls.sh \
  --bootstrap-server kafka.internal.example:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:payment-service \
  --operation Read \
  --topic orders.created

kafka-acls.sh \
  --bootstrap-server kafka.internal.example:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:payment-service \
  --operation Read \
  --group payment-workers
~~~

Đây là minh họa **cơ chế cấp quyền**, không phải tập ACL đầy đủ để đưa thẳng vào production. Client còn có thể cần các thao tác Describe hoặc quyền khác tùy phiên bản, cấu hình, nhóm thao tác, transactional producer và cách áp ACL. Cần ghi lại đúng nhu cầu thực tế rồi mới thêm quyền.

Các điểm dễ bỏ sót:

- **Group permission:** consumer phải được cấp quyền tương ứng trên consumer group. Nếu group quá rộng, client có thể tham gia nhóm không thuộc trách nhiệm của mình, làm thay đổi cách phân phối partition và tiến độ xử lý.
- **Pattern tiền tố hoặc wildcard:** chỉ dùng khi namespace đủ hẹp và có quy trình đặt tên đáng tin cậy. Một ACL cho mọi topic có thể làm mất ranh giới giữa hệ thống.
- **Auto-create topic:** nếu để producer tự tạo topic mà không kiểm soát, lỗi chính tả hoặc credential bị lộ có thể sinh tài nguyên không mong muốn. Cân nhắc provisioning tập trung.
- **Transactional producer:** transaction ID và quyền giao dịch phải được cấp đúng mục tiêu; không mặc định mọi producer đều cần.
- **Schema Registry:** ACL topic Kafka không nhất thiết bảo vệ schema registry. Subject/schema API cần cơ chế xác thực và phân quyền riêng.
- **Chính sách Allow/Deny và super user:** phải hiểu thứ tự áp dụng và các ngoại lệ. Đừng kiểm tra chính sách bằng tài khoản superuser vì kết quả có thể che giấu lỗi phân quyền.
- **ACL và log metadata:** cần bảo vệ cả thao tác xem cấu trúc cụm, danh sách topic và metadata nhạy cảm trong phạm vi mà broker hỗ trợ.

Nếu ứng dụng nhận lỗi ủy quyền, hãy xác định principal thực tế, resource, operation, cluster và client đang dùng trước khi sửa. Thêm quyền Create/Alter/Delete để sửa lỗi Read là dấu hiệu mô hình phân quyền đang bị mở rộng sai.

## 8. RabbitMQ: virtual host, configure/write/read và quyền định tuyến

RabbitMQ dùng mô hình khác Kafka. Với AMQP 0-9-1 thông dụng, quyền trên một vhost được phân thành các mẫu tên tài nguyên:

- **configure:** tạo, xóa hoặc thay đổi định nghĩa exchange/queue theo thao tác và cơ chế của RabbitMQ.
- **write:** xuất bản thông điệp lên exchange hoặc thao tác cần ghi vào tài nguyên.
- **read:** tiêu thụ thông điệp từ queue hoặc thao tác cần đọc từ tài nguyên.
- **topic permissions:** với topic exchange, có thể cần kiểm soát thêm quyền routing key theo cơ chế hỗ trợ.

Ví dụ muốn bảo vệ nghiệp vụ đặt hàng trong vhost **/commerce**:

~~~text
/commerce
  exchange: orders.events
  queues:
    payments.orders
    inventory.orders

order-service:
  publish -> exchange orders.events
  consume -> không cấp

payment-service:
  consume -> queue payments.orders
  publish -> chỉ các exchange nghiệp vụ riêng nếu thực sự cần

inventory-service:
  consume -> queue inventory.orders
  publish -> chỉ các exchange nghiệp vụ riêng nếu thực sự cần

platform-provisioner:
  tạo exchange, queue và binding theo change request được duyệt
~~~

Chính sách có thể được gán bằng các biểu thức chính quy cho tên exchange/queue. Ví dụ dưới đây chỉ để minh họa ý tưởng tách quyền; tên user, vhost, binding và routing key phải được chuẩn hóa theo topology thực tế:

~~~bash
# Quyền mẫu theo thứ tự: configure-regex, write-regex, read-regex.
# Không cấp configure hay read cho producer.
rabbitmqctl set_permissions -p /commerce \
  order-service "^$" "^orders[.]events$" "^$"

# Không cấp configure hay write cho consumer chỉ-đọc.
rabbitmqctl set_permissions -p /commerce \
  payment-service "^$" "^$" "^payments[.]orders$"
~~~

**Cảnh báo về topology:** kết nối, khai báo exchange/queue, bind queue, publish và consume có những phép kiểm tra quyền khác nhau. Những đoạn ứng dụng tự động khai báo topology khi khởi động có thể lỗi dưới quyền tối thiểu; một hướng thiết kế là **provision trước bằng danh tính vận hành**, rồi cho ứng dụng quyền publish/consume cần thiết. Với topic exchange, xem thêm quyền routing key nếu broker yêu cầu. Hai lệnh minh họa không thay thế việc lập bảng tất cả thao tác của client.

Tách vhost là cách cô lập namespace hữu ích, nhưng không nhất thiết là cách ly vật lý về CPU, bộ nhớ, disk hoặc network. Một tenant bắn traffic cực lớn vẫn có thể ảnh hưởng cluster dùng chung nếu thiếu quota và giới hạn kết nối.

Tránh dùng tài khoản guest mặc định hoặc tài khoản quản trị làm credential chạy ứng dụng. Management UI/API phải có danh tính và quyền riêng, giới hạn kết nối mạng, bật TLS và lưu audit nếu có khả năng.

## 9. Truy cập theo lớp: mạng, ứng dụng và điều hành

Một cấu hình an toàn phải có nhiều hàng rào với mục tiêu khác nhau:

| Lớp | Ví dụ bảo vệ | Không thay thế được |
|---|---|---|
| **Mạng** | Private endpoint, firewall, security group, NetworkPolicy, chỉ mở port cần thiết | ACL producer/consumer |
| **Đường truyền** | TLS, mTLS, xác thực server, mã hóa replication/management | Quy tắc xử lý payload |
| **Danh tính** | Service account, SASL, IAM, chứng chỉ workload | Quyền thao tác cụ thể |
| **Phân quyền** | ACL topic/group, vhost, IAM resource policy | Kiểm tra schema và nghiệp vụ |
| **Tài nguyên** | Quota, giới hạn connection, message size, retention, disk protection | Bí mật và tính riêng tư dữ liệu |
| **Vận hành** | Audit log, MFA với quản trị, break-glass, giám sát thay đổi | Hạn chế quyền ứng dụng |

Một kiến trúc ví dụ:

~~~mermaid
flowchart TB
    subgraph Apps["Vùng chạy dịch vụ"]
        O[Order Service / producer]
        P[Payment Service / consumer]
    end
    subgraph Private["Vùng mạng riêng"]
        F[Firewall / Network Policy]
        B[(Broker)]
        S[(Secret Manager / CA)]
    end
    subgraph Ops["Mặt phẳng điều hành"]
        A[Admin qua kết nối bảo vệ]
        L[Audit + Metrics]
    end
    O -->|TLS, identity, ACL write| F
    P -->|TLS, identity, ACL read| F
    F --> B
    S -.->|cấp/đổi credential| O
    S -.->|cấp/đổi credential| P
    A -->|quyền quản trị hạn chế| B
    B --> L
~~~

Không mở cổng broker, JMX, API quản trị hoặc dashboard ra Internet công khai nếu không có nhu cầu được chứng minh và các biện pháp bảo vệ tương ứng. Đường truy cập từ CI/CD, môi trường staging, máy phát triển và công cụ phân tích cũng phải nằm trong mô hình đe dọa.

Trên Kubernetes, NetworkPolicy phụ thuộc vào plugin mạng có thực thi policy; tự khai báo policy không tự chứng minh traffic đã được chặn. Khi dùng secret volume hoặc environment variable, cần kiểm soát quyền xem pod, log, dump và cấu hình cluster.

## 10. Bảo mật dữ liệu trong thông điệp

### 10.1. Phân loại và giảm dữ liệu

Broker có thể giữ payload lâu hơn vòng đời của một HTTP request. Hãy phân loại nội dung trước khi phát:

- **Public/internal:** có thể chia sẻ trong những dịch vụ được cho phép.
- **Confidential:** chứa dữ liệu khách hàng, tài chính, vận hành; cần người nhận và retention cụ thể.
- **Restricted/secret:** mật khẩu, private key, access token hoặc dữ liệu phải bảo vệ đặc biệt; thường không nên phát qua sự kiện nghiệp vụ thông thường.

Nếu sự kiện chỉ cần **orderId, status, occurredAt**, không nên gửi toàn bộ đối tượng Order có số điện thoại, địa chỉ, giá trị nội bộ và thông tin thanh toán. Tương tự, không đặt PII làm tên topic, routing key, message key hay header khi không cần thiết; các trường này dễ lọt vào metric và log.

### 10.2. Mã hóa khi lưu và ở tầng payload

- **Encryption in transit:** TLS bảo vệ client ↔ broker và các đường truyền khác theo thiết kế.
- **Encryption at rest:** mã hóa ổ đĩa/storage và snapshot/backup khi broker hoặc nền tảng hỗ trợ; quản lý khóa và quyền truy cập bản sao lưu.
- **Application-level encryption:** mã hóa từng payload hoặc trường nhạy cảm trước khi publish nếu cần bảo đảm broker operator hoặc hạ tầng trung gian không đọc được nội dung.

Mã hóa ở mức payload có chi phí: phân phối khóa cho consumer, rotate key, hỗ trợ replay dữ liệu cũ, tìm kiếm và kiểm tra schema. Có thể dùng mã hóa bao (envelope encryption) với khóa dữ liệu và dịch vụ quản lý khóa, kèm key ID/version trong metadata không nhạy cảm. Không đặt khóa giải mã vào message.

TLS và mã hóa storage **không đủ** nếu credential consumer bị lộ và quyền đọc quá rộng. Ngược lại, mã hóa payload không giúp chống xóa topic hoặc cạn dung lượng broker.

### 10.3. Retention, backup và xóa dữ liệu

Định nghĩa thời gian lưu, chính sách compaction, retention theo chủ đề, DLQ retention, backup retention, quyền truy cập bản snapshot và khả năng xóa khi cần. Với Kafka compacted topic, cần hiểu retention tombstone và dữ liệu còn tồn tại trên replica/backup theo thời gian. Không hứa xóa tức thì toàn bộ bản sao chỉ nhờ xóa một message logic.

DLQ thường chứa payload gốc và stack trace nên có thể **nhạy cảm hơn luồng chính**. Hạn chế quyền xem DLQ, che dữ liệu trong log và đặt retention phù hợp.

## 11. Tin cậy thông điệp: schema, nguồn gốc và tính toàn vẹn

Broker xác thực producer tại thời điểm kết nối, nhưng consumer cần tiếp tục coi payload là **dữ liệu đầu vào không đáng tin tuyệt đối**. Một producer được cấp quyền vẫn có thể bị lỗi hoặc bị chiếm quyền.

Consumer nên kiểm tra:

1. **Schema và version:** message có đúng kiểu, trường bắt buộc, giới hạn kích thước và phiên bản tương thích không?
2. **Nguồn phát hợp lệ:** sự kiện này thuộc trách nhiệm của producer nào? Có chính sách topic/identity ràng buộc nguồn phát không?
3. **Trạng thái nghiệp vụ:** một sự kiện PaymentCompleted có khớp order, payment attempt và trạng thái lưu trữ hiện tại không?
4. **Giới hạn chi phí xử lý:** kích thước, số phần tử lồng nhau, tỷ lệ giải nén, số bước gọi downstream và deadline có trong mức an toàn không?
5. **Tính lặp lại:** eventId, idempotency key và trạng thái xử lý có ngăn thao tác trùng không?
6. **Độ mới / vòng đời:** xử lý event trễ, replay và sự kiện lệch thứ tự theo quy tắc nghiệp vụ.

Ví dụ event envelope:

~~~json
{
  "eventId": "evt-ord-2001-v1",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "ord-2001",
  "occurredAt": "2026-11-12T02:00:00Z",
  "producer": "order-service",
  "data": {
    "orderId": "ord-2001",
    "customerRef": "cust-opaque-51",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
~~~

Trường **producer** do bên gửi khai báo chỉ là metadata để đối chiếu; bản thân nó **không chứng minh danh tính**. Nguồn xác thực đáng tin phải đến từ kết nối/credential, policy tuyến publish, hoặc chữ ký/biện pháp xác thực payload có khóa được quản lý phù hợp với yêu cầu.

Nếu message đi qua nhiều broker, bridge hoặc hệ thống bên thứ ba, broker đích có thể chỉ nhìn thấy danh tính của bridge. Khi cần chứng minh nhà phát gốc xuyên các tầng trung gian, cân nhắc chữ ký số hoặc một cơ chế xác minh nguồn gốc đầu cuối. Không ký rồi tin cậy toàn bộ message nếu không có quy trình quản lý khóa và chống replay.

## 12. An toàn xử lý: ACK, retry, DLQ và phát lại

Bảo mật không chỉ dừng ở ai được consume. Hành vi xử lý sai có thể tạo điều kiện gian lận hoặc mất dữ liệu.

- **ACK/commit sau mốc xử lý đúng:** đừng xác nhận đã xử lý khi nghiệp vụ chưa đủ điều kiện hoàn tất; dùng hợp đồng phù hợp với framework/broker.
- **Retry có giới hạn:** giới hạn số lần, delay/backoff, tránh vòng lặp tức thì gây tấn công khuếch đại hoặc làm nghẽn queue.
- **Poison message:** payload sai phải được cách ly hoặc đưa vào DLQ có kiểm soát; không để một record làm kẹt vô hạn partition/queue.
- **DLQ ACL:** chỉ consumer/worker được chỉ định và công cụ phát lại có thẩm quyền mới được ghi/đọc; replay cần ghi lý do, người thực hiện và phạm vi.
- **Idempotency:** ghi dấu eventId hoặc khóa nghiệp vụ và thực thi tác vụ có thể lặp an toàn. Đặc biệt quan trọng với thanh toán, tồn kho và gửi thông báo.
- **Thứ tự và phiên bản:** consumer phải định nghĩa cách xử lý sự kiện cũ đến sau sự kiện mới; xác minh sequence/version với trạng thái hiện tại khi cần.
- **Transactional outbox/inbox:** nếu DB và broker không cùng giao dịch, sử dụng outbox để giảm nguy cơ DB commit rồi publish lỗi; consumer inbox/idempotency hỗ trợ không lặp tác dụng phụ.
- **Không xem “exactly-once” ở broker là toàn bộ nghiệp vụ exactly-once:** giao dịch Kafka hoặc công cụ cụ thể chỉ bao phủ ranh giới đã được định nghĩa, không tự bảo đảm side effect tại mọi DB/API bên ngoài.

Khi phát lại DLQ, hãy thực hiện qua công cụ riêng với quyền hạn chế và chế độ quan sát. Một thao tác replay hàng triệu bản ghi có thể gây quá tải hệ thống hoặc tái kích hoạt giao dịch nhạy cảm.

## 13. Quota và chống lạm dụng tài nguyên

Dù một producer hoàn toàn hợp lệ, nó vẫn có thể làm broker nghẽn bằng traffic quá mức hoặc message lớn. Hãy thiết lập ngân sách theo principal/tenant, khả năng của broker và hợp đồng nghiệp vụ.

| Tài nguyên | Ví dụ giới hạn | Rủi ro nếu bỏ qua |
|---|---|---|
| Kết nối và channel | Số connection/session/channel theo workload | Cạn file descriptor, thread hoặc memory |
| Publish rate / byte rate | Thông điệp/giây, byte/giây, producer quota | Disk/network bão hòa |
| Message size | Kích thước tối đa của bản tin và batch | Cạn RAM, tắc mạng, lỗi downstream |
| Queue depth / backlog | Chiều dài queue, tuổi message, TTL | Tích lũy dữ liệu, disk đầy |
| Consumer concurrency | Số worker và prefetch | DB/API downstream bị quá tải |
| Topic/partition/queue count | Hạn chế tự tạo tài nguyên | Tăng metadata và tài nguyên quản lý |
| Retention | Theo loại dữ liệu và SLA | Chi phí lưu trữ, kéo dài cửa sổ rò rỉ |
| Retry/DLQ flow | Số lần thử lại và tốc độ phát lại | Retry storm, vòng lặp dead-letter |

Chính sách có thể nằm tại client, gateway, service, broker, proxy hoặc cloud service. Không giả định một limit phía client đủ bảo vệ trước client bị chiếm quyền: broker hoặc lớp hạ tầng đáng tin cũng cần chặn tài nguyên.

Thiết kế **backpressure** để upstream giảm phát khi downstream chậm; theo dõi lag và queue age; ưu tiên từ chối hoặc trì hoãn có kiểm soát hơn là để broker tràn disk. Với queue bền vững, quyết định loại hoặc xóa message phải tuân thủ hợp đồng nghiệp vụ và khả năng khôi phục.

## 14. Cô lập nhiều tenant, môi trường và hệ thống

Nếu các tenant dùng chung broker, cần lựa chọn mức độ cách ly dựa trên ảnh hưởng sự cố:

- **Tách cluster:** ranh giới tài nguyên mạnh hơn, vận hành tốn kém hơn; phù hợp khi yêu cầu cách ly cao.
- **Tách namespace/vhost/topic prefix và ACL:** giảm chi phí nhưng vẫn chia sẻ một số tài nguyên vật lý; cần quota và quy tắc naming.
- **Tách principal cho mỗi tenant/workload:** dễ thu hồi quyền và giám sát phạm vi bị lộ.
- **Tách môi trường:** không dùng tài khoản prod trên dev/staging hoặc để broker dev kết nối ngược sang prod không kiểm soát.
- **Tách mã hóa/khóa:** khi cần, khóa theo tenant hoặc phân lớp nhạy cảm giúp giới hạn hậu quả khi khóa bị lộ.

Ví dụ namespace hợp lệ: **tenant-a.orders.created** và **tenant-b.orders.created** với ACL theo đúng tiền tố của tenant. Tuy nhiên, nếu client được phép tự tạo topic dưới tiền tố tùy ý hoặc một công cụ dùng wildcard quá rộng, việc đặt tên chỉ tạo cảm giác an toàn. Phải kiểm thử hành vi thực tế của ACL và deny rule.

Khi dịch vụ trung gian aggregate sự kiện của nhiều tenant, nó cần trách nhiệm rõ ràng về lọc dữ liệu, ghi log, hạn mức, privacy và các principal dùng khi phát lại. Một “analytics consumer” không nên được cấp quyền đọc toàn bộ dữ liệu thô chỉ vì thuận tiện.

## 15. Quan sát và kiểm toán quyền truy cập

Bảo mật cần chứng cứ vận hành để trả lời “ai đã làm gì, khi nào và từ đâu?”. Nên quan sát:

- Số lần **authentication failed** và **authorization denied**, phân nhóm theo principal, source, operation, resource và thời điểm.
- Những principal đột nhiên phát/đọc topic chưa từng dùng; thay đổi lưu lượng hoặc consumer group bất thường.
- Kết nối từ IP/namespace/workload ngoài danh sách dự kiến; TLS handshake failure; chứng chỉ sắp hết hạn.
- Số connection/channel, publish byte rate, message size, backlog, consumer lag, disk và broker throttling.
- Sự kiện thay đổi ACL, role, vhost, topic, queue, binding, retention, DLQ và các quyền quản trị.
- Hành động phát lại, xóa, purge, đổi offset hoặc reset group, cùng người phê duyệt và phạm vi ảnh hưởng.
- Lỗi schema, poison message, tỷ lệ retry, tỷ lệ từ chối và số message bị cách ly.
- Tỷ lệ consumer xử lý đúng, độ trễ xử lý và sự kiện nghiệp vụ bất thường có liên quan đến nguồn phát.

Không ghi payload, access token, khóa hay dữ liệu cá nhân thô vào audit log chỉ để “đủ bằng chứng”. Dùng event ID, request/correlation ID, principal ID, tên resource và kết quả thao tác với chính sách phân quyền truy cập log rõ ràng.

**Phân biệt ba loại log:**
- **Broker audit:** ai kết nối, xin quyền gì, quyền được cấp hay bị từ chối.
- **Application log:** event nào được gửi/nhận/xử lý, kết quả nghiệp vụ và lý do từ chối.
- **Change log:** ai thay ACL/cấu hình, qua phiên bản triển khai/change request nào.

Chỉ nhìn dashboard “consumer lag = 0” không chứng minh hệ thống an toàn: một consumer trái phép vẫn có thể đọc payload mà không làm chậm nhóm chính.

## 16. Quy trình triển khai phân quyền theo từng bước

### Bước 1: Vẽ luồng dữ liệu và quyền

Với mỗi luồng, ghi **producer, destination, consumer, nhóm nhận, dữ liệu nhạy cảm, retention, chủ sở hữu, quyền cần cấp và phản ứng khi lỗi**. Đừng dùng sơ đồ chung “service A → broker → service B” để thay thế phân tích tên resource.

### Bước 2: Chọn danh tính và cơ chế cấp phát

Cấp mỗi workload một principal riêng; dùng TLS/mTLS/SASL/IAM phù hợp với broker và môi trường. Lưu credential trong secret manager; thiết kế rotation và thu hồi trước khi đưa vào production.

### Bước 3: Provision topology bằng quyền riêng

Tạo topic/queue/exchange/binding qua pipeline vận hành, phân quyền cụ thể và hạn chế auto-create nếu phù hợp. Producer/consumer nghiệp vụ không được cấp quyền quản trị chỉ để tự khởi tạo mọi tài nguyên.

### Bước 4: Áp ACL mặc định từ chối

Viết ma trận quyền **resource × operation × principal**; triển khai ACL với phạm vi hẹp, tránh wildcard và kiểm tra cả group, DLQ, retry topic, schema registry, transaction ID nếu có.

### Bước 5: Kiểm tra cả đường hợp lệ và đường bị cấm

Ví dụ, order-service được publish orders.created nhưng không được consume payments.completed; payment-service được consume orders.created bằng group của chính nó nhưng không được xóa topic hoặc tham gia group inventory-workers. Dùng credential thật của từng workload trong môi trường kiểm thử, không dùng admin để chứng minh một quyền ứng dụng.

### Bước 6: Bổ sung giới hạn tài nguyên và xử lý payload

Đặt message size, quota, queue depth/TTL, consumer concurrency, retry budget; thêm schema validation, idempotency và chính sách DLQ/replay. Viết điều kiện chấp nhận và từ chối thành test kỹ thuật của ứng dụng.

### Bước 7: Bật giám sát và diễn tập thu hồi

Đo authentication/authorization failures, traffic theo principal, thay đổi ACL, lag và saturation. Diễn tập khóa credential của một service, xác nhận service khác vẫn hoạt động; biết cách rotate key, rollback policy và khôi phục luồng đã dừng.

## 17. Tình huống tổng hợp: bảo vệ luồng OrderCreated

**Bối cảnh:** Order Service ghi đơn vào cơ sở dữ liệu và phát OrderCreated. Payment Service, Inventory Service và Analytics Service muốn phản ứng độc lập.

**Thiết kế đề xuất:**

~~~text
Order Service (principal: order-service)
  -> transactional outbox
  -> publisher: chỉ WRITE orders.created
  -> Kafka topic: orders.created
       -> payment-service: READ topic + group payment-workers
       -> inventory-service: READ topic + group inventory-workers
       -> analytics-service: READ topic dữ liệu đã lọc, nếu chính sách cho phép

Platform Provisioner
  -> CREATE/ALTER tài nguyên theo pipeline
  -> cập nhật ACL qua change request

Audit & Monitoring
  -> principal, resource, operation, outcome
  -> không ghi payload chứa PII

DLT / Replay
  -> principal riêng, quyền tối thiểu và ghi dấu phát lại
~~~

Quy trình luồng hợp lệ:

1. Order Service commit đơn và outbox record trong cùng giao dịch DB.
2. Publisher đọc outbox và phát event trên kết nối được xác thực, TLS bảo vệ.
3. Broker xác thực principal **order-service**, kiểm tra quyền Write trên **orders.created** và chấp nhận thông điệp hợp lệ theo giới hạn cấu hình.
4. Payment Service kết nối với principal riêng, chỉ được đọc topic và group của nó; validate schema và kiểm tra trạng thái nghiệp vụ.
5. Payment xử lý có idempotency, ghi kết quả và công bố sự kiện **payments.completed** bằng quyền publish được cấp riêng.
6. Inventory và Analytics xử lý theo hợp đồng của mình; không nhờ vào quyền của Payment.
7. Nếu message lỗi, consumer xử lý retry có ngân sách, cách ly vào DLT khi cần; công cụ replay có quyền riêng.

Các tình huống bị từ chối:

- **analytics-service** cố publish **payments.completed** → broker từ chối vì thiếu Write.
- **payment-service** cố dùng group **inventory-workers** → broker từ chối nếu ACL group được cấu hình đủ hẹp.
- **order-service** cố xóa topic **orders.created** → bị từ chối vì không có quyền Delete/Alter.
- Client có credential hợp lệ nhưng dùng endpoint/topic của môi trường khác → không được kết nối hoặc không có ACL tương ứng.
- Một message có schema sai hoặc trạng thái nghiệp vụ không hợp lệ → consumer cách ly/từ chối xử lý theo hợp đồng, dù broker đã chấp nhận bản tin.

**Giới hạn của giải pháp:** ACL trên topic không thể tự phân biệt hai event có cùng quyền Write mà khác nội dung nghiệp vụ. Các sự kiện như PaymentCompleted phải được kiểm tra nguồn dữ liệu có thẩm quyền, trạng thái hiện tại, idempotency và nguyên tắc phân chia trách nhiệm. Khi cần sự bảo đảm mạnh về nguồn gốc đầu cuối, thêm lớp xác minh phù hợp.

## 18. Sự cố giả định: lộ credential của một producer

Giả sử credential của service gửi thông báo bị lộ. Tài khoản này chỉ được ghi lên **notifications.requested** và bị giới hạn throughput.

**Tác động được giới hạn:** kẻ tấn công có thể phát sự kiện thông báo giả trong phạm vi quota, nhưng không thể đọc topic đơn hàng, xóa queue thanh toán hoặc sửa ACL nếu chính sách thực thi đúng. Dù vậy, việc gửi notification giả vẫn nghiêm trọng; consumer phải kiểm tra yêu cầu nghiệp vụ và nguồn phát, không gửi nội dung tùy ý chỉ vì event đến từ topic được phép.

Quy trình phản ứng thực tế:

1. Cảnh báo phát hiện sự thay đổi bất thường trong publish rate hoặc nguồn kết nối.
2. Vô hiệu hóa principal/credential bị lộ và chặn nguồn kết nối nếu cần.
3. Xác định chính xác topic, thời gian, số lượng event và consumer có thể bị ảnh hưởng qua audit/metric.
4. Xoay credential và kiểm tra secret distribution; tìm nguồn rò rỉ trong CI/CD, log, image, cấu hình.
5. Khoanh vùng các event đáng ngờ; ngăn consumer thực thi hành động nguy hiểm, dùng công cụ bù trừ hoặc phục hồi khi cần.
6. Khôi phục công việc hợp lệ với credential mới, giám sát authorization failures và traffic.
7. Cập nhật chính sách theo nguyên nhân: quyền quá rộng, thiếu quota, thiếu schema validation, nguồn publish không được kiểm tra hoặc khả năng xoay secret yếu.

Một hệ thống không thể chứng minh đã an toàn chỉ bằng việc đổi mật khẩu. Cần xác định những hành động credential cũ có thể làm và hậu quả đã xảy ra.

## 19. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng cùng user cho nhiều microservice | Không quy trách nhiệm, lộ một secret ảnh hưởng nhiều dịch vụ | Principal riêng cho từng workload |
| Dùng admin credential trong ứng dụng | Client có thể sửa/xóa tài nguyên và ACL | Tách quyền vận hành khỏi publish/consume |
| Tin cậy mọi client trong VPC | Dịch vụ bị chiếm quyền có thể truy cập chéo | Authn/Authz ở broker, mạng riêng vẫn cần |
| Cấp wildcard topic/group | Đọc/ghi vượt phạm vi, can thiệp nhóm xử lý | ACL theo tên hoặc prefix hẹp |
| Chỉ cấp ACL topic Kafka mà quên group | Consumer lỗi phân quyền hoặc được sửa bằng wildcard không cần thiết | Thiết kế đủ Topic và Group |
| Tự khai báo topology ở mọi service | Phải mở rộng configure/create ngoài nhu cầu | Provision topology tập trung |
| Bảo vệ queue nhưng không bảo vệ exchange/binding | Luồng publish hoặc định tuyến bị lợi dụng | Kiểm tra đầy đủ tài nguyên RabbitMQ |
| TLS không xác minh hostname/cert | Dễ bị giả mạo server trên đường truyền | Xác minh server, CA và vòng đời cert |
| Mặc định log toàn bộ message | Rò PII, token và dữ liệu nghiệp vụ | Log metadata tối thiểu, che trường nhạy cảm |
| DLQ được cấp quyền đọc cho mọi nhóm | Lộ dữ liệu thô và sự kiện lỗi | ACL, retention, replay role riêng |
| Không giới hạn kích thước và lưu lượng | Broker đầy disk/RAM, ảnh hưởng tenant khác | Quota, size limit, backpressure |
| Tin trường producer trong JSON là xác thực | Có thể giả mạo nguồn nghiệp vụ | Bind nguồn phát với identity/policy hoặc chữ ký khi cần |
| Tin rằng broker “exactly-once” giải quyết mọi side effect | Thanh toán, tồn kho có thể thực thi trùng | Idempotency và giao dịch ở ranh giới nghiệp vụ |
| Không diễn tập thu hồi credential | Khó khoanh vùng khi bị lộ | Rotation, revocation và runbook |
| Chỉ xem lag/throughput | Không phát hiện consumer trái phép hay thay ACL | Audit authn/authz và config change |

## 20. Bài tập thực hành

**Bài 1 — Ma trận quyền:** Hệ thống có Catalog Service, Price Service, Cart Service và Recommendation Service. Tạo bảng principal, topic/exchange/queue, thao tác publish/consume, group, độ nhạy dữ liệu và quyền bị cấm. Chỉ ra dịch vụ nào cần quyền quản trị; giải thích vì sao ứng dụng nghiệp vụ thông thường không cần quyền đó.

**Bài 2 — Kafka:** Producer A ghi topic **orders.created**; Consumer B thuộc group **fraud-detection**. Hãy liệt kê resource và operation cần cho A, B. Sau đó xác định chính sách phải từ chối khi B thử tham gia group khác hoặc khi A thử đọc topic **payments.completed**. Nêu cách kiểm tra bằng principal ứng dụng thay vì tài khoản admin.

**Bài 3 — RabbitMQ:** Một publisher gửi vào exchange **billing.events**; hai queue nhận thông điệp theo routing key khác nhau. Thiết kế vhost, quyền configure/write/read, quyền topic theo routing key nếu cần, quyền tạo binding và danh tính quản trị topology. Điều gì xảy ra nếu publisher được quyền configure tất cả?

**Bài 4 — Dữ liệu nhạy cảm:** OrderCreated đang chứa email, số điện thoại, địa chỉ đầy đủ và token thanh toán; Analytics chỉ cần orderId và trạng thái. Thiết kế payload mới, luồng dữ liệu đã lọc, retention, quyền đọc, mã hóa và chính sách DLQ.

**Bài 5 — Diễn tập lộ credential:** Giả định một consumer account bị lộ. Hãy nêu cách thu hồi, danh sách quyền cần rà soát, metric/audit cần truy vấn, cách bảo đảm các consumer khác vẫn hoạt động và điều kiện khôi phục an toàn.

**Bài 6 — Tấn công quá tải:** Một producer hợp lệ đột nhiên tăng publish 100 lần và gửi message rất lớn. Xác định quota theo principal, max message size, kết nối, queue limit, consumer concurrency, DLQ/retry policy và cách quan sát để phân biệt nghẽn broker với lỗi nghiệp vụ.

## 21. Ghi nhớ

- **Xác thực là biết client là ai; phân quyền là giới hạn client được làm gì và trên tài nguyên nào.**
- **Kafka cần xem topic và consumer group; RabbitMQ cần xem vhost, exchange, queue, configure/write/read và khi phù hợp cả routing key.** Các managed service dùng mô hình IAM/resource policy riêng.
- **Producer/consumer dùng principal riêng với quyền tối thiểu.** Tạo/xóa topology, sửa ACL và phát lại hàng loạt thuộc vai trò được quản trị.
- **TLS, mạng riêng và mã hóa lưu trữ chỉ bảo vệ một phần.** Vẫn cần kiểm tra schema, nội dung, danh tính nguồn phát, quyền nghiệp vụ và idempotency.
- **DLQ, backup, header, schema registry và log cũng nằm trong phạm vi bảo mật.** Không chỉ bảo vệ topic chính.
- **Quota, giới hạn kích thước, backpressure, retry budget và quan sát an ninh** giúp giới hạn ảnh hưởng khi client bị lỗi hoặc bị chiếm quyền.
- **Luôn kiểm tra cả thao tác được cho phép lẫn thao tác phải bị từ chối**, rồi diễn tập thu hồi credential và khôi phục luồng.

Broker là trung tâm vận chuyển thông điệp; ranh giới bảo mật phải được giữ nhất quán từ danh tính kết nối, quyền trên tài nguyên, tính hợp lệ của bản tin cho đến vận hành và ứng phó sự cố. Khi từng microservice chỉ có quyền cần thiết và mọi đường xử lý đều có giới hạn rõ ràng, hệ thống giảm được phạm vi ảnh hưởng của một dịch vụ lỗi hoặc bị xâm nhập.
