# Dự án xử lý thông điệp bằng Streaming, Queue và Java workers

## 1. Mục tiêu và sản phẩm cần hoàn thành

Trong chương **Dự án tích hợp và đánh giá** của module **CLOUD_PROVIDERS_ORACLE**, dự án này kết hợp Oracle Cloud Infrastructure (OCI) Streaming, Queue, Compute, IAM, VCN và một cơ sở dữ liệu Oracle thành đường ống xử lý đơn hàng bất đồng bộ. Người học cần chứng minh hệ thống vẫn cho ra kết quả đúng khi thông điệp được giao lại, tiến trình bị dừng giữa chừng hoặc cơ sở dữ liệu tạm thời không truy cập được.

Sản phẩm cuối cùng gồm một chương trình Java phát sự kiện, một Java dispatcher chuyển sự kiện từ Streaming sang Queue, các Java worker cạnh tranh nhận tác vụ và cơ sở dữ liệu lưu kết quả. Hạ tầng phải có phân quyền theo vai trò, giám sát, quy trình khôi phục, cách triển khai lặp lại và phương án kiểm soát chi phí.

Sau dự án, người học có thể:

- Giải thích khi nào cần nhật ký sự kiện có khả năng replay và khi nào cần hàng đợi công việc.
- Xác định chính xác ranh giới xác nhận thành công ở producer, dispatcher và worker.
- Triển khai xử lý idempotent bằng khóa duy nhất và giao dịch cơ sở dữ liệu.
- Đo độ trễ, backlog, tốc độ xử lý và khả năng phục hồi khi có lỗi.
- Bảo vệ luồng dữ liệu bằng IAM, kết nối mạng và cách quản lý thông tin xác thực phù hợp.
- Trình bày bằng chứng nghiệm thu, đánh đổi kiến trúc và giới hạn của kết quả thử nghiệm.

Các cấu hình và mục tiêu hiệu năng dưới đây là **lựa chọn cho bài lab**, không phải giới hạn dịch vụ, cam kết SLA hay mức giá của OCI.

## 2. Đề bài nghiệp vụ và phạm vi

Một hệ thống bán hàng phát sự kiện khi đơn hàng được chấp nhận. Mỗi sự kiện hợp lệ cần tạo đúng một yêu cầu chuẩn bị giao hàng trong bảng nghiệp vụ.

Luồng chuẩn:

1. Producer tạo sự kiện `OrderAccepted` với `eventId` ổn định.
2. Producer gửi sự kiện vào stream `orders-events`.
3. Dispatcher đọc stream bằng consumer group `fulfillment-dispatch-v1`.
4. Dispatcher chuyển nguyên envelope sang queue `fulfillment-tasks`.
5. Worker đọc tác vụ, xác thực dữ liệu và ghi cơ sở dữ liệu.
6. Worker chỉ xóa thông điệp khỏi Queue sau khi giao dịch nghiệp vụ đã commit.

Kết quả nghiệp vụ của dự án là bản ghi `READY_FOR_FULFILLMENT`. Dự án chưa gọi hãng vận chuyển, chưa thu tiền và chưa gửi email thực tế. Những hành động bên ngoài cơ sở dữ liệu cần giao thức idempotency riêng nếu được bổ sung.

Ba bất biến cần bảo vệ:

| Bất biến | Cách diễn đạt có thể kiểm tra |
| --- | --- |
| Không bỏ qua sự kiện đã nhận trách nhiệm | Mỗi sự kiện producer xác nhận được dịch vụ nhận phải đến kết quả nghiệp vụ hoặc trạng thái lỗi có thể đối soát, trong cửa sổ lưu giữ và điều kiện phục hồi đã thiết kế |
| Một hiệu ứng nghiệp vụ cho một sự kiện | Cặp `eventId` và tên hiệu ứng chỉ được ghi nhận một lần, kể cả khi thông điệp vận chuyển xuất hiện nhiều lần |
| Không xác nhận trước khi chuyển giao bền vững | Dispatcher chưa tiến checkpoint nếu chưa chuyển giao xong; worker chưa xóa thông điệp nếu chưa commit dữ liệu |

Từ “đúng một lần” trong bất biến thứ hai chỉ mô tả hiệu ứng được bảo vệ trong giao dịch cơ sở dữ liệu. Hệ thống vẫn chấp nhận việc publish hoặc delivery lặp. Không có giao dịch phân tán mặc định bao trùm Streaming, Queue và Oracle Database.

## 3. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    P["Java producer"] -->|"OrderAccepted"| S["OCI Streaming: orders-events"]
    S -->|"Consumer group"| D["Java dispatcher"]
    D -->|"Chuyển envelope"| Q["OCI Queue: fulfillment-tasks"]
    Q --> W1["Java worker A"]
    Q --> W2["Java worker B"]
    W1 -->|"Giao dịch JDBC"| DB[("Oracle Database / Autonomous Database")]
    W2 -->|"Giao dịch JDBC"| DB
    Q -->|"Vượt ngưỡng delivery"| DLQ["Dead letter queue"]
    D -->|"Dữ liệu không chuyển được"| QUAR["Kho cách ly bền vững"]
    S -. "Consumer group replay riêng" .-> R["Công cụ replay"]
    R -. "Giữ eventId" .-> Q
    D -. "Log, metric" .-> O["OCI Logging / Monitoring"]
    W1 -. "Log, metric" .-> O
    W2 -. "Log, metric" .-> O
~~~

Trong bản tối thiểu, dispatcher và worker chạy trên Compute trong private subnet. Producer có thể chạy trên máy phát tải đã được cấp quyền riêng. Cơ sở dữ liệu Oracle dùng private endpoint nếu môi trường lab hỗ trợ cấu hình đó.

Kho cách ly dành cho trường hợp dispatcher không thể đưa một bản ghi vào Queue, chẳng hạn envelope vượt ngưỡng ứng dụng. Có thể dùng bảng quarantine trong cơ sở dữ liệu với khóa `(stream_id, partition_id, source_offset)`. Nếu không triển khai kho này, dispatcher phải dừng tiến checkpoint và phát cảnh báo; không được bỏ qua bản ghi rồi tiếp tục.

Kho cách ly của dispatcher khác với DLQ của Queue. Một sự kiện chưa vào Queue không thể được bảo vệ bằng DLQ của Queue.

### Vì sao dùng cả Streaming và Queue?

Streaming giữ nhật ký để nhiều nhóm độc lập đọc và để phát lại dữ liệu trong thời hạn lưu giữ. Queue là điểm đệm công việc, giúp các worker chia tải và xử lý giao lại từng tác vụ. Không bắt buộc mọi ứng dụng đều cần cả hai; dự án dùng cả hai để thực hành sự khác biệt và ranh giới chuyển giao.

Một phương án chỉ có Queue phù hợp hơn nếu không cần lịch sử sự kiện để đọc lại. Một phương án chỉ có Streaming có thể phù hợp nếu nhóm xử lý tự đảm nhận điều phối công việc và retry. Trong báo cáo, người học phải giải thích lợi ích của thành phần bổ sung so với chi phí và vận hành phát sinh.

## 4. Hiểu đúng ngữ nghĩa trước khi viết code

| Khía cạnh | Streaming trong dự án | Queue trong dự án |
| --- | --- | --- |
| Mô hình dữ liệu | Nhật ký phân vùng, đọc bằng cursor | Hàng đợi tác vụ, nhận cùng receipt |
| Tiến độ | Vị trí đã commit của consumer group | Xóa thông điệp sau xử lý |
| Đọc lại | Có thể đọc lại trong cửa sổ retention | Thông điệp đã xóa không còn để replay từ hàng đợi |
| Song song | Partition được chia giữa thành viên cùng group | Worker cạnh tranh nhận tác vụ ở cấu hình cơ bản đã chọn |
| Thứ tự | Bảo đảm trong phạm vi partition | Thiết kế nghiệp vụ không dựa vào thứ tự nhận hoặc hoàn thành |
| Lỗi ứng dụng | Có thể đọc lại phần chưa commit | Có thể giao lại khi hết visibility timeout |
| Dữ liệu lỗi | Cần chiến lược của ứng dụng | Có cơ chế DLQ theo cấu hình delivery |

Streaming là append-only log và có thể replay trong thời gian retention. Thứ tự trong partition không đồng nghĩa thứ tự toàn stream; sự kiện qua Queue và nhiều worker cũng không giữ mặc nhiên thứ tự hoàn thành nghiệp vụ. [Tổng quan Streaming](https://docs.oracle.com/en-us/iaas/Content/Streaming/Concepts/streamingoverview.htm).

Consumer group giúp chia partition cho dispatcher. Mỗi instance phải có tên riêng; thêm instance vượt số partition không tạo thêm khả năng đọc song song cho group. Với `commitOnGet=true`, lần lấy tiếp theo commit tiến độ của lần lấy trước; dispatcher vì thế phải hoàn tất chuyển giao batch trước lần lấy kế tiếp. [Sử dụng consumer groups](https://docs.oracle.com/en-us/iaas/Content/Streaming/Tasks/using_consumer_groups.htm).

Queue trả về receipt để worker cập nhật visibility hoặc xóa thông điệp. Receipt là dữ liệu của lần nhận, không thay thế `eventId`. Worker phải dùng receipt của delivery đang xử lý. Chọn visibility phù hợp và long polling giúp tránh giao lại sớm hoặc gọi API liên tục khi queue rỗng. [Nhận thông điệp từ Queue](https://docs.oracle.com/en-us/iaas/Content/queue/consume-messages.htm).

Một dòng log “đã nhận message” chưa chứng minh nghiệp vụ đã thành công. Một phản hồi HTTP thành công của API dạng batch cũng không thay thế việc xem kết quả từng phần tử khi API có kết quả riêng cho từng message.

## 5. Hợp đồng sự kiện và quy tắc định danh

### 5.1. Envelope đề xuất

~~~json
{
  "eventId": "evt-lab-000001",
  "eventType": "OrderAccepted",
  "schemaVersion": 1,
  "occurredAt": "2026-11-01T03:15:00Z",
  "correlationId": "corr-lab-001",
  "orderId": "ORD-LAB-000001",
  "payload": {
    "customerId": "CUS-LAB-001",
    "amountMinor": 159000,
    "currency": "VND"
  }
}
~~~

`amountMinor` là số nguyên theo đơn vị tiền nhỏ nhất mà ứng dụng quy ước cho từng đồng tiền. Với VND trong bài lab, giá trị trên là 159.000 đồng. Tránh dùng `double` cho số tiền.

Quy tắc bắt buộc:

- Producer tạo `eventId` một lần trước lần publish đầu tiên; mọi lần retry dùng lại ID và cùng nội dung.
- `orderId` được dùng làm key khi publish vào Streaming để nhóm sự kiện liên quan. Đây chưa phải cơ chế bảo đảm thứ tự xuyên suốt hệ thống.
- `schemaVersion` điều khiển bộ đọc; không tự suy đoán phiên bản từ các field tình cờ có mặt.
- Worker chỉ chấp nhận `eventType=OrderAccepted`, phiên bản được hỗ trợ, ID không rỗng, số tiền dương và đồng tiền nằm trong danh sách của ứng dụng.
- Giới hạn độ dài ID, kích thước UTF-8 và trường bắt buộc phải được kiểm tra trước khi ghi cơ sở dữ liệu.
- Payload không chứa mật khẩu, khóa truy cập hoặc dữ liệu cá nhân không cần cho tác vụ.

### 5.2. Phân biệt các loại ID

| Giá trị | Vai trò | Có dùng làm khóa chống lặp nghiệp vụ không? |
| --- | --- | --- |
| `eventId` | Danh tính sự kiện do producer quản lý | Có, kết hợp tên hiệu ứng |
| `orderId` | Danh tính đối tượng nghiệp vụ | Có thể là ràng buộc nghiệp vụ bổ sung |
| Stream partition và offset | Vị trí vận chuyển trong stream | Dùng truy vết nguồn, không thay event ID |
| Queue message ID | Danh tính bản sao trong Queue | Không, publish lại có thể tạo bản sao khác |
| Queue receipt | Quyền thao tác trên lần nhận hiện tại | Không |
| `correlationId` | Nối log của một luồng xử lý | Không nhất thiết duy nhất |

Dispatcher giữ nguyên chuỗi JSON UTF-8 trong bản cơ bản. Nhờ vậy có thể tính SHA-256 trên chính chuỗi sự kiện để phát hiện một `eventId` bị dùng lại với nội dung khác.

Nếu một thành phần parse rồi serialize lại JSON, thứ tự thuộc tính hoặc biểu diễn số có thể đổi. Khi đó phải thống nhất quy tắc canonicalization trước khi hash; không được coi hai bản JSON khác byte là bằng nhau chỉ vì có cùng ID. Hash phát hiện xung đột nội dung, không xác thực danh tính người gửi.

Đặt tên hiệu ứng là `create-fulfillment:v1`. Một bản nâng cấp sửa lỗi nhưng vẫn tạo cùng hiệu ứng phải giữ tên này khi replay. Đổi tên hiệu ứng chỉ để vượt cơ chế chống lặp có thể làm phát sinh tác dụng phụ lần hai.

## 6. Chuẩn bị tài nguyên và cấu hình lab

### 6.1. Kiến thức và quyền cần có

Người thực hiện cần biết Java, JDBC, HTTP, JSON, giao dịch cơ sở dữ liệu và IAM cơ bản của OCI. Chuẩn bị tenancy, compartment riêng cho bài lab, hạn mức tài nguyên phù hợp, quyền triển khai được quản trị viên giao và đường truy cập quản trị Compute.

Chọn một region có các dịch vụ cần dùng. Kiểm tra khả năng cấp phát trước khi phát tải. Không mặc định mọi tenancy đều được cấp sẵn tài nguyên miễn phí hoặc có cùng quota.

### 6.2. Danh mục tối thiểu

| Thành phần | Cấu hình khởi điểm của lab | Điều cần ghi lại |
| --- | --- | --- |
| Compartment | Một compartment dành cho capstone | OCID, owner, thời điểm dọn dẹp |
| VCN | Private subnet cho ứng dụng và đường ra HTTPS | CIDR, route table, NSG |
| Streaming | Một stream pool, một stream, 3 partition, retention 24 giờ | Stream OCID, messages endpoint |
| Queue | Một queue, retention 24 giờ, visibility 60 giây, long poll 20 giây | Queue OCID, messages endpoint, ngưỡng delivery |
| Dispatcher | Một instance ban đầu, sau đó hai instance | Group name, instance name riêng |
| Worker | Một rồi hai tiến trình Java | Số luồng, số kết nối JDBC, giới hạn batch |
| Oracle Database | Một schema ứng dụng | Cách kết nối TLS, tài khoản ứng dụng |
| Quan sát | Log tập trung và dashboard | Cửa sổ đo, rule cảnh báo, retention log |

Chọn ngưỡng delivery ban đầu là 5 trong cấu hình lab nếu được dịch vụ chấp nhận. Khi thử DLQ, đối chiếu trạng thái thực tế và cấu hình đang dùng; không giả định số lần gọi API nhất định luôn trùng với thời điểm thông điệp chuyển DLQ.

Các khoảng retention phải lớn hơn tổng thời gian ngừng dịch vụ dự kiến, thời gian xử lý bù và biên an toàn. Retention 24 giờ ở đây chỉ phục vụ buổi thực hành có thời lượng ngắn.

### 6.3. Cấu hình ứng dụng

~~~properties
OCI_REGION=<region-cua-lab>
STREAM_ID=<stream-ocid>
STREAM_MESSAGES_ENDPOINT=<messages-endpoint-cua-stream>
STREAM_GROUP=fulfillment-dispatch-v1
STREAM_INSTANCE=dispatcher-a
STREAM_BATCH_LIMIT=10

QUEUE_ID=<queue-ocid>
QUEUE_MESSAGES_ENDPOINT=<messages-endpoint-cua-queue>
QUEUE_VISIBILITY_SECONDS=60
QUEUE_POLL_SECONDS=20
QUEUE_BATCH_LIMIT=1

WORKER_EFFECT=create-fulfillment:v1
WORKER_THREADS=1
DB_JDBC_URL=<jdbc-url-tls>
DB_USER=<tai-khoan-ung-dung>
DB_SECRET_REFERENCE=<tham-chieu-bi-mat>
~~~

Bắt đầu với queue batch bằng 1 để nhìn rõ vòng đời từng delivery. Sau khi hệ thống đúng, mới tăng batch và số luồng. Nếu nhận 10 message rồi xử lý tuần tự, visibility của những message cuối đã bắt đầu đếm từ lúc cả batch được nhận.

Lấy endpoint từ thông tin tài nguyên, không tự ghép tên host theo region. Queue có API quản trị và messages endpoint; client nhận, gửi, cập nhật hoặc xóa thông điệp phải trỏ đến messages endpoint của queue tương ứng. [Queue messages endpoint](https://docs.oracle.com/en-us/iaas/Content/queue/messages.htm).

## 7. IAM, thông tin xác thực và mạng

### 7.1. Tách ba vai trò chạy ứng dụng

Tạo dynamic group riêng cho Compute của producer, dispatcher và worker nếu các thành phần đó chạy trên OCI. Có thể ràng buộc membership theo instance OCID; không gom tất cả instance trong tenancy vào một vai trò rộng chỉ để thử nhanh.

Ví dụ policy dữ liệu, với các placeholder phải được thay bằng tài nguyên lab:

~~~text
Allow dynamic-group LabOrderProducers to use stream-push in compartment OciMessagingLab where target.stream.id = '<stream_ocid>'

Allow dynamic-group LabDispatchers to use stream-pull in compartment OciMessagingLab where target.stream.id = '<stream_ocid>'

Allow dynamic-group LabDispatchers to use queue-push in compartment OciMessagingLab where target.queue.id = '<queue_ocid>'

Allow dynamic-group LabFulfillmentWorkers to use queue-pull in compartment OciMessagingLab where target.queue.id = '<queue_ocid>'
~~~

`stream-push` và `stream-pull` tách quyền phát và đọc stream. `queue-push` tách quyền gửi, còn `queue-pull` phục vụ nhận và thao tác delivery. Không cấp quyền tạo/xóa tài nguyên cho tiến trình ứng dụng chỉ vì cần gửi nhận message. [Policy Streaming](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/streamingpolicyreference.htm), [Policy Queue](https://docs.oracle.com/en-us/iaas/Content/queue/policy-reference.htm).

Ví dụ trên không cấp quyền đọc metadata tài nguyên, lấy secret hay gửi log/metric. Nếu ứng dụng tự gọi `GetQueue`, đọc secret từ Vault hoặc đẩy telemetry bằng SDK, bổ sung đúng quyền cho chức năng đó. Có thể cấp endpoint qua cấu hình triển khai để tiến trình xử lý không cần tự khám phá metadata.

IAM cho Queue không thay thế quyền `INSERT` hoặc `SELECT` trong schema Oracle. Tài khoản ứng dụng chỉ được phép truy cập các bảng cần dùng; tài khoản tạo bảng và tài khoản vận hành hạ tầng nên được quản lý riêng.

Trên Compute, dùng instance principals để tránh chép API private key vào máy ảo. Khi chạy producer trên máy cá nhân, dùng profile OCI dành cho lab với quyền tương ứng. Mật khẩu cơ sở dữ liệu, wallet và API key không được đóng gói vào JAR, image hoặc source control.

### 7.2. Đường kết nối phải được chứng minh

Với endpoint công khai của Streaming và Queue, private subnet cần đường ra được cho phép, chẳng hạn NAT Gateway, cùng DNS và egress HTTPS thích hợp. Nếu dùng private endpoint của một dịch vụ, cấu hình route, DNS và NSG theo endpoint đó; không suy ra các dịch vụ có cùng mô hình private connectivity.

Worker cần đường kết nối TLS đến cơ sở dữ liệu. NSG chỉ cho phép nguồn ứng dụng và cổng listener đang dùng. Truy cập quản trị qua Bastion hoặc đường quản trị đã được tổ chức phê duyệt.

Thử riêng hai nhóm lỗi:

- Mạng hoặc DNS hỏng: không kết nối được, timeout, không phân giải được host.
- Xác thực hoặc phân quyền hỏng: yêu cầu đến dịch vụ nhưng bị từ chối.

Ghi request ID khi dịch vụ trả về. Đừng sửa policy thành quyền toàn tenancy để che một lỗi endpoint hoặc route table.

## 8. Tổ chức ứng dụng Java

Có thể dùng Java 17 trở lên và Maven cho ứng dụng thực hành. Tách ba entry point để triển khai và tăng tài nguyên độc lập:

~~~text
producer       -> tạo dữ liệu, publish, lưu manifest đối soát
dispatcher     -> đọc Streaming, chuyển sang Queue, quản lý tiến độ
worker         -> nhận Queue, xác thực, giao dịch JDBC, xóa delivery
shared         -> envelope, validation, mã lỗi và telemetry
~~~

Dùng OCI Java SDK 3.x với một phiên bản cụ thể đã được nhóm lựa chọn và cố định trong cấu hình build. Những dependency chính gồm:

| Dependency | Mục đích |
| --- | --- |
| `com.oracle.oci.sdk:oci-java-sdk-bom` | Đồng bộ phiên bản các module OCI SDK |
| `com.oracle.oci.sdk:oci-java-sdk-streaming` | Client Streaming |
| `com.oracle.oci.sdk:oci-java-sdk-queue` | Client Queue |
| `com.oracle.oci.sdk:oci-java-sdk-common-httpclient-jersey3` | HTTP transport được chọn cho ví dụ |
| Oracle JDBC driver tương thích JDK và database | Giao dịch cơ sở dữ liệu |
| Thư viện JSON và logging do dự án chọn | Parse envelope, ghi log có cấu trúc |

Ở SDK 3.x, cần khai báo HTTP transport phù hợp thay vì chỉ thêm module dịch vụ. BOM giúp tránh trộn phiên bản các module. [Thiết lập SDK cho Java](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm).

Các đoạn Java dưới đây là **đoạn trích tích hợp**, không phải toàn bộ ứng dụng có thể chạy ngay. Người học cần bổ sung bootstrap, cấu hình, bộ parse JSON, lớp lưu dữ liệu, log và cơ chế supervisor. Tên phương thức như `publishAndVerify` hoặc `applyAtomically` là hợp đồng ứng dụng, không phải API có sẵn của OCI.

Ví dụ tạo Queue client trên Compute:

~~~java
import com.oracle.bmc.ClientConfiguration;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.queue.QueueClient;

var provider = InstancePrincipalsAuthenticationDetailsProvider.builder().build();

var clientConfig = ClientConfiguration.builder()
        .connectionTimeoutMillis(5_000)
        .readTimeoutMillis(35_000)
        .build();

QueueClient queue = QueueClient.builder()
        .endpoint(queueMessagesEndpoint)
        .configuration(clientConfig)
        .build(provider);
~~~

`queueMessagesEndpoint` lấy từ cấu hình của queue thật. Client được tái sử dụng trong vòng đời tiến trình và đóng khi shutdown. Read timeout phải chứa được long poll đã cấu hình cộng độ trễ mạng; nếu đổi long poll cần xem lại timeout.

Tránh import wildcard đồng thời các package `streaming.requests` và `queue.requests` vì cả hai có những tên như `GetMessagesRequest`. Ví dụ dispatcher dùng tên đầy đủ để thể hiện rõ dịch vụ đang gọi.

## 9. Xây producer và sổ đối soát đầu vào

Producer tạo một tập sự kiện có thể tái lập, chẳng hạn 1.000 đơn hàng hợp lệ với ID mang tiền tố của lần chạy. Trước khi publish, lưu danh sách `eventId` và hash tương ứng vào manifest của lần thử. Đây là dữ liệu nghiệm thu, không phải log tùy ý bị bỏ khi tiến trình kết thúc.

Quy trình:

~~~text
tạo eventId + orderId + envelope
ghi envelope vào manifest đầu vào
gửi vào Streaming, key = UTF-8(orderId), value = UTF-8(envelope)
đọc kết quả publish
    từng phần tử thành công -> ghi CONFIRMED cùng partition/offset nếu có
    từng phần tử thất bại rõ ràng -> phân loại lỗi và retry phù hợp
    timeout hoặc mất phản hồi -> ghi UNKNOWN, retry cùng eventId và nội dung
~~~

Streaming trả kết quả riêng cho từng phần tử của `PutMessages`, bao gồm lỗi nếu append thất bại. Vì vậy producer không được đánh dấu cả batch thành công chỉ dựa trên mã HTTP. [Kết quả publish từng phần tử](https://docs.oracle.com/en-us/iaas/tools/java/3.72.1/com/oracle/bmc/streaming/model/PutMessagesResultEntry.html).

Không chuyển byte JSON thành chuỗi Base64 rồi lại đưa chuỗi đó vào trường byte của Java SDK nếu không có lý do ở tầng ứng dụng. Phân biệt biểu diễn payload trên wire với kiểu dữ liệu SDK; một hợp đồng encode/decode hai lần không khớp sẽ làm worker nhận nội dung sai. Mẫu CLI của Oracle dùng Base64 cho các giá trị message trong JSON đầu vào. [Publish thông điệp thử](https://docs.oracle.com/en-us/iaas/Content/Streaming/Tasks/publishingmessages.htm).

Khi thử cơ chế giao lặp, publish lại đúng một số envelope đã có. Khi thử xung đột định danh, gửi một envelope khác nội dung nhưng giữ nguyên `eventId`. Đây là hai tình huống khác nhau và phải có hai kết quả quan sát khác nhau.

Manifest nên phân biệt:

- `CONFIRMED`: producer nhận được xác nhận thành công.
- `UNKNOWN`: yêu cầu có thể đã được dịch vụ nhận nhưng producer không biết kết quả.
- `REJECTED`: thất bại đã được xác định và không được tính như đầu vào thành công.

Kết thúc thử nghiệm, mọi ID ở nhóm `UNKNOWN` phải được đối soát hoặc retry có kiểm soát; không được xóa nhóm này khỏi báo cáo để làm tỷ lệ thành công đẹp hơn.

## 10. Xây dispatcher: chuyển giao trước, tiến checkpoint sau

### 10.1. Luồng cơ bản

Chọn `commitOnGet=true` và xử lý batch đồng bộ trong bản đầu tiên. Không prefetch batch tiếp theo khi batch hiện tại còn message chưa được Queue chấp nhận.

~~~java
import com.oracle.bmc.streaming.StreamClient;
import com.oracle.bmc.streaming.model.CreateGroupCursorDetails;
import com.oracle.bmc.streaming.requests.CreateGroupCursorRequest;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

static void dispatch(
        StreamClient stream,
        String streamId,
        String groupName,
        String instanceName,
        Consumer<byte[]> publishAndVerify,
        AtomicBoolean running) throws InterruptedException {

    var details = CreateGroupCursorDetails.builder()
            .groupName(groupName)
            .instanceName(instanceName)
            .type(CreateGroupCursorDetails.Type.TrimHorizon)
            .commitOnGet(true)
            .build();

    String cursor = stream.createGroupCursor(
            CreateGroupCursorRequest.builder()
                    .streamId(streamId)
                    .createGroupCursorDetails(details)
                    .build())
            .getCursor().getValue();

    while (running.get()) {
        var response = stream.getMessages(
                com.oracle.bmc.streaming.requests.GetMessagesRequest.builder()
                        .streamId(streamId)
                        .cursor(cursor)
                        .limit(10)
                        .build());

        for (var message : response.getItems()) {
            // Chỉ return khi Queue đã xác nhận nhận bền vững.
            // Lỗi chưa giải quyết phải throw, không được nuốt exception.
            publishAndVerify.accept(message.getValue());
        }

        cursor = response.getOpcNextCursor();

        if (response.getItems().isEmpty()) {
            Thread.sleep(500);
        }
    }
}
~~~

Cursor được tạo với một group name ổn định và instance name riêng cho mỗi tiến trình. Ví dụ tạo group cursor dùng đúng các trường của Java SDK. [CreateGroupCursor bằng Java](https://docs.oracle.com/en-us/iaas/tools/java-sdk-examples/latest/streaming/CreateGroupCursorExample.java.html).

Lần `GetMessages` kế tiếp là điểm có thể commit batch trước. Phép gán biến `cursor` trong Java chưa tự commit trên dịch vụ. Nếu tiến trình dừng sau khi gửi thành công nhưng trước lần lấy kế tiếp, batch có thể được đọc lại và được gửi lại vào Queue; worker phải chịu được điều này.

Hợp đồng của `publishAndVerify`:

1. Kiểm tra kích thước và chuyển byte thành chuỗi theo UTF-8 hợp lệ, không tự sửa dữ liệu hỏng.
2. Gửi nguyên envelope vào Queue bằng `PutMessages` tại messages endpoint.
3. Xem đầy đủ kết quả mà API trả về; không coi việc chỉ gửi request là thành công.
4. Với timeout chưa rõ kết quả, cho phép retry cùng nội dung và ID, chấp nhận khả năng tạo bản sao.
5. Với lỗi chưa xử lý được, ném exception để vòng đọc không tiến sang batch kế tiếp.

Queue nhận chuỗi nội dung; Streaming Java SDK trả byte của message. Quy tắc decode phải thống nhất. Metadata nguồn như stream ID, partition và offset có thể ghi vào log hoặc wrapper đã thiết kế trước, nhưng không làm mất danh tính sự kiện.

### 10.2. Phục hồi và batch bị lỗi một phần

Giả sử dispatcher đọc 10 message và gửi được 6 message đầu trước khi lỗi mạng. Nếu chưa có chuyển giao bền vững cho 4 message cuối, dispatcher không được gọi vòng lấy tiếp theo để vô tình commit cả batch.

Bản đầu tiên có thể kết thúc vòng xử lý khi lỗi, chờ backoff ở supervisor rồi tạo lại group cursor bằng **cùng group name**. Những message đã chuyển nhưng chưa được checkpoint có thể xuất hiện lại. Không tạo group name ngẫu nhiên sau mỗi lần restart vì sẽ làm thay đổi phạm vi đọc và khả năng đối soát.

Nếu chọn retry lâu trong cùng tiến trình, phải quản lý heartbeat và thời gian sống cursor theo API. Đoạn trích trên chưa cài đặt heartbeat; nó phù hợp với batch nhỏ và chuyển giao ngắn. Khi quyền sở hữu partition không còn chắc chắn, dừng sử dụng trạng thái cũ và tham gia group lại. Không tiếp tục commit dựa trên giả định instance vẫn giữ partition.

Với manual commit, tạo cursor bằng `commitOnGet=false` rồi chỉ gọi `ConsumerCommit` sau chuyển giao thành công; dùng cursor mới được API trả về. Đây là hướng nâng cao, cần xử lý thêm heartbeat, rebalance và lỗi commit, không được trộn với vòng auto commit mà không thiết kế lại. [Commit offset thủ công](https://docs.oracle.com/en-us/iaas/Content/Streaming/Tasks/commit-consumer-group.htm).

### 10.3. Poison record trước Queue

Nếu message không thể chuyển vào Queue do lỗi dữ liệu cố định:

- Bản tối thiểu: dừng tiến checkpoint, cảnh báo và yêu cầu người vận hành xử lý trước khi retention kết thúc.
- Bản mở rộng: lưu nguyên dữ liệu nguồn và lý do vào quarantine bền vững, với khóa duy nhất theo vị trí stream; chỉ sau khi lưu thành công mới coi bản ghi đã được chuyển giao trách nhiệm.

Không ghi log rồi bỏ qua. Log có thể không chứa đủ payload, hết retention hoặc bị sampling nên không tự trở thành kho khôi phục.

## 11. Thiết kế giao dịch chống lặp trong Oracle Database

### 11.1. Schema tối thiểu

~~~sql
CREATE TABLE event_receipts (
    event_id        VARCHAR2(64 CHAR) NOT NULL,
    effect_name     VARCHAR2(64 CHAR) NOT NULL,
    payload_sha256  CHAR(64 CHAR) NOT NULL,
    processed_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_event_receipts PRIMARY KEY (event_id, effect_name)
);

CREATE TABLE fulfillment_jobs (
    order_id         VARCHAR2(64 CHAR) NOT NULL,
    source_event_id  VARCHAR2(64 CHAR) NOT NULL,
    amount_minor     NUMBER(18, 0) NOT NULL,
    currency         VARCHAR2(3 CHAR) NOT NULL,
    job_status       VARCHAR2(32 CHAR) NOT NULL,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_fulfillment_jobs PRIMARY KEY (order_id),
    CONSTRAINT uq_fulfillment_source UNIQUE (source_event_id),
    CONSTRAINT ck_fulfillment_amount CHECK (amount_minor > 0),
    CONSTRAINT ck_fulfillment_status CHECK (
        job_status = 'READY_FOR_FULFILLMENT'
    )
);
~~~

Ứng dụng kiểm tra số tiền vừa phạm vi `long` vừa độ chính xác `NUMBER(18,0)` đã chọn. Mỗi đơn hàng của bài lab có một sự kiện chấp nhận hợp lệ. Nếu cùng `orderId` xuất hiện với sự kiện mới mang ý nghĩa khác, đó là vấn đề nghiệp vụ cần phân loại; không được âm thầm coi là trùng message.

`event_receipts` đồng thời là inbox chống lặp. Chỉ xóa lịch sử inbox sau khi đã xác định đầy đủ khoảng thời gian có thể replay hoặc redrive, kể cả dữ liệu lưu bên ngoài Queue. Nếu xóa inbox sớm rồi replay, rào chắn chống lặp sẽ thay đổi.

### 11.2. Thuật toán bắt buộc của lớp lưu trữ

~~~text
parse + validate envelope
tính SHA-256 theo quy tắc dữ liệu đã thống nhất
mở JDBC connection, autoCommit = false

thử INSERT event_receipts(eventId, effectName, hash)
    nếu lỗi unique ở chính lệnh INSERT receipt:
        rollback
        đọc receipt đã tồn tại
        nếu hash khác -> lỗi xung đột định danh, không xác nhận thành công
        nếu hash giống -> trả ALREADY_APPLIED
        nếu không đọc được -> trả lỗi có thể retry
    nếu lỗi khác -> rollback, truyền lỗi

INSERT fulfillment_jobs(...)
commit
trả APPLIED

nếu bất kỳ bước ghi hoặc commit nào lỗi:
    rollback nếu còn thực hiện được
    truyền lỗi; không yêu cầu xóa Queue message
~~~

Hai lệnh insert phải dùng **cùng connection và cùng giao dịch**. Không commit receipt trước rồi mới tạo fulfillment job. Ràng buộc duy nhất trong cơ sở dữ liệu giải quyết cuộc đua khi hai worker cùng xử lý một event; một phép `SELECT` trước `INSERT` ở Java không đủ thay thế ràng buộc này.

Chỉ xử lý lỗi trùng khóa theo ngữ cảnh của lệnh insert receipt. Nếu insert `fulfillment_jobs` vi phạm khóa `order_id` hoặc `source_event_id`, phải rollback và kiểm tra xung đột nghiệp vụ; không bắt mọi lỗi unique rồi trả thành công.

Khi commit bị timeout, ứng dụng có thể chưa biết giao dịch đã hoàn tất hay chưa. Worker giữ thông điệp để có thể giao lại; lần xử lý sau dùng inbox để phân biệt đã áp dụng hay cần áp dụng. Không suy luận “commit ném exception nên chắc chắn chưa ghi”.

### 11.3. Tại sao không dùng bộ nhớ cục bộ?

Một `ConcurrentHashMap` chỉ nhớ những ID trên một tiến trình, mất khi restart và không phối hợp với instance khác. Một file đánh dấu riêng cũng không giao dịch nguyên tử với thay đổi dữ liệu. Bộ nhớ có thể làm cache để giảm đọc, nhưng quyết định cuối cùng vẫn phải dựa trên trạng thái dùng chung có ràng buộc giao dịch.

Nếu bổ sung phát sự kiện `FulfillmentPrepared` sau khi commit, dùng transactional outbox: ghi dữ liệu nghiệp vụ và outbox trong cùng giao dịch, rồi một publisher riêng chuyển outbox ra dịch vụ. Outbox publisher vẫn có thể gửi lặp; bên nhận tiếp tục cần idempotency. Không gọi dịch vụ ngoài ở giữa giao dịch và mặc định rollback database sẽ hoàn tác được lời gọi đó.

## 12. Xây Java worker nhận Queue

### 12.1. Nhận, ghi dữ liệu, rồi xóa

Đoạn trích sau xử lý một delivery mỗi lần để làm rõ thứ tự:

~~~java
import com.oracle.bmc.queue.QueueClient;
import com.oracle.bmc.queue.requests.DeleteMessageRequest;
import com.oracle.bmc.queue.requests.GetMessagesRequest;

interface EffectStore {
    // Chỉ return khi APPLIED đã commit hoặc ALREADY_APPLIED đã xác minh.
    // Dữ liệu không hợp lệ, xung đột và lỗi hạ tầng phải throw.
    void applyAtomically(String envelope) throws Exception;
}

static void pollOnce(
        QueueClient queue,
        String queueId,
        EffectStore store) throws Exception {

    var response = queue.getMessages(
            GetMessagesRequest.builder()
                    .queueId(queueId)
                    .limit(1)
                    .timeoutInSeconds(20)
                    .visibilityInSeconds(60)
                    .build());

    for (var message : response.getGetMessages().getMessages()) {
        store.applyAtomically(message.getContent());

        queue.deleteMessage(
                DeleteMessageRequest.builder()
                        .queueId(queueId)
                        .messageReceipt(message.getReceipt())
                        .build());
    }
}
~~~

`GetMessagesResponse` của Queue chứa mô hình `GetMessages`, còn phản hồi Streaming chứa danh sách `items`; hai kiểu này không thể thay thế cho nhau chỉ vì trùng tên thao tác. [Queue GetMessagesResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/queue/responses/GetMessagesResponse.html), [Streaming GetMessagesResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/streaming/responses/GetMessagesResponse.html).

Vòng chạy bên ngoài gọi `pollOnce`, phân loại exception, ghi telemetry và áp dụng backoff có giới hạn. Một exception của lần xử lý không được dẫn đến khối `finally` luôn xóa message. Nếu database đã commit nhưng `DeleteMessage` thất bại, ghi nhận trạng thái “ack chưa chắc chắn”; giao lại sau đó phải trả `ALREADY_APPLIED` và thử xóa bằng receipt mới.

### 12.2. Visibility timeout và tác vụ dài

Giả sử thời gian xử lý thông thường dưới 2 giây nhưng đôi lúc truy vấn mất 35 giây. Visibility 60 giây có thể là giá trị khởi đầu hợp lý cho lab, sau đó cần điều chỉnh từ số liệu thật.

Ngân sách phải tính từ lúc nhận message, gồm thời gian chờ trong executor, xử lý, commit, retry ngắn và gửi yêu cầu xóa:

~~~text
visibility
    > thời gian chờ trước xử lý
    + thời gian xử lý có xét đuôi phân phối
    + thời gian commit và xóa
    + biên an toàn
~~~

Nếu tác vụ dài hơn ngân sách, worker gia hạn trước khi hết hạn bằng `UpdateMessage` với receipt hiện tại. Việc cập nhật chỉ thay đổi visibility, không thay thế commit nghiệp vụ và không kéo dài message vô hạn qua thời hạn retention. [Cập nhật visibility](https://docs.oracle.com/en-us/iaas/Content/queue/update-messages.htm).

Một tác vụ chạy 3 phút cần cơ chế gia hạn riêng; chỉ đặt bộ hẹn giờ trong chính luồng đang bị chặn ở JDBC sẽ không bảo đảm hẹn giờ được chạy. Khi không thể xác nhận quyền giữ delivery, cho phép lần xử lý đang chạy thất bại an toàn hoặc hoàn tất dưới bảo vệ của inbox; không dựa vào visibility như khóa nghiệp vụ duy nhất.

### 12.3. Shutdown và giới hạn tài nguyên

Khi nhận tín hiệu dừng:

1. Ngừng nhận tác vụ mới.
2. Cho tác vụ đang chạy hoàn tất trong thời gian grace đã đặt.
3. Chỉ xóa những delivery đã commit hoặc được xác minh trùng hợp lệ.
4. Để các delivery còn lại có thể được giao lại.
5. Đóng executor, connection pool và SDK client.

Giới hạn số message đang giữ phải phù hợp với số luồng, connection pool và visibility. Executor có hàng đợi không giới hạn có thể làm message hết visibility trước khi bắt đầu xử lý dù CPU trung bình còn thấp.

## 13. Retry, DLQ và replay có kiểm soát

### 13.1. Phân loại lỗi trước khi retry

| Nhóm lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Tạm thời | Timeout mạng, throttling, database gián đoạn ngắn | Retry có giới hạn, backoff và jitter; giữ danh tính sự kiện |
| Cấu hình hoặc quyền | Sai endpoint, sai credential, thiếu IAM | Cảnh báo, giảm hoặc dừng nhận; sửa cấu hình trước khi tiếp tục |
| Dữ liệu cố định | JSON hỏng, phiên bản không hỗ trợ, số tiền sai | Không retry nóng; để đi DLQ hoặc chuyển quarantine theo thiết kế |
| Xung đột nghiệp vụ | Cùng event ID khác hash, một order bị chấp nhận mâu thuẫn | Cách ly, giữ bằng chứng, không trả thành công như bản trùng |
| Chưa biết kết quả | Publish, commit hoặc delete bị mất phản hồi | Đối soát hoặc cho giao lại; dùng idempotency để xử lý an toàn |

Công thức backoff có thể dùng:

~~~text
giới hạn chờ = min(cap, base × 2^attempt)
thời gian chờ thực tế = ngẫu nhiên từ 0 đến giới hạn chờ
~~~

Ví dụ lab đặt `base=200 ms`, `cap=5 s` cho retry ngắn trong ứng dụng. Đây là cấu hình minh họa. Phải cộng ngân sách retry của SDK và ứng dụng; ba tầng cùng retry nhiều lần có thể làm một tác vụ vượt visibility và giữ hết kết nối JDBC.

Nếu database ngừng vài phút, circuit breaker nên hạn chế xử lý và tạm dừng nhận thêm. Tiếp tục lấy cùng dữ liệu trong khi phụ thuộc chắc chắn chưa phục hồi có thể làm tăng delivery count và đẩy nhiều tác vụ hợp lệ vào DLQ.

### 13.2. Vòng đời DLQ

Queue có DLQ cho thông điệp vượt ngưỡng delivery theo cấu hình. Dữ liệu trong DLQ vẫn có thời hạn lưu giữ; việc vào DLQ không phải sao lưu vĩnh viễn. Nhận message để kiểm tra cũng có thể ảnh hưởng delivery count nên không polling Console tùy tiện trong lúc đo thử nghiệm. [Dead letter queues](https://docs.oracle.com/en-us/iaas/Content/queue/deadletterqueues.htm), [Lưu ý khi polling Queue](https://docs.oracle.com/en-us/iaas/Content/queue/consume-messages-queue.htm).

Runbook redrive:

1. Xác định nguyên nhân: lỗi dữ liệu, lỗi code hay lỗi hạ tầng.
2. Ghi lại định danh, hash, thời điểm và lý do xử lý; hạn chế sao chép payload nhạy cảm.
3. Sửa nguyên nhân và thử với một mẫu nhỏ.
4. Publish lại các sự kiện hợp lệ vào queue đích với tốc độ giới hạn.
5. Giữ nguyên `eventId` và nội dung nếu đây là cùng sự kiện được xử lý lại.
6. Chỉ xóa bản trong DLQ sau khi lần publish đích đã được xác nhận.
7. Đối soát kết quả và theo dõi khả năng quay lại DLQ.

Crash giữa bước publish và xóa DLQ có thể tạo bản sao. Cơ chế inbox bảo vệ hiệu ứng, tương tự cửa sổ crash của dispatcher.

Nếu nghiệp vụ cần thay đổi nội dung một sự kiện lỗi, tạo sự kiện sửa chữa có ID mới và tham chiếu về bản gốc. Không âm thầm sửa dữ liệu rồi giữ nguyên ID, vì điều đó phá vỡ hợp đồng bất biến của envelope.

### 13.3. Replay từ Streaming

Replay dùng consumer group riêng, chẳng hạn `fulfillment-replay-run-01`, hoặc cơ chế đọc theo partition và vị trí đã lưu. Xác định trước phạm vi thời gian, nguồn dữ liệu, queue đích và tốc độ tối đa.

Với group đã tồn tại, không giả định thay `TrimHorizon` hoặc thời điểm trong lời gọi tạo cursor sẽ tự đặt lại tiến độ của group. Cần dùng group mới hoặc thao tác cập nhật vị trí được hỗ trợ, sau khi đã đánh giá ảnh hưởng đến consumer đang chạy.

Phát lại cùng một tập sự kiện đã thành công phải tạo thêm số lần nhận và số lần phát hiện trùng, nhưng không tăng số fulfillment job. Replay không phục hồi được thông điệp đã hết retention nếu không có bản lưu độc lập.

## 14. Các bước triển khai và mốc kiểm chứng

### Mốc 1: Chuẩn bị hạ tầng

Tạo compartment và gắn tag phục vụ owner, môi trường, dự án và ngày dọn dẹp. Tạo mạng, đường ra, NSG, stream pool, stream, queue, schema cơ sở dữ liệu và nhóm quyền.

Có thể triển khai bằng Terraform với OCI provider, trực tiếp hoặc qua OCI Resource Manager. Lưu biến đầu vào và outputs cần thiết như OCID, endpoint, subnet; bảo vệ state vì state có thể chứa dữ liệu nhạy cảm. Không đưa mật khẩu vào biến văn bản được commit cùng mã nguồn.

Mốc đạt khi tài nguyên tồn tại, endpoint được lấy đúng và có danh sách cấu hình để tái tạo. Việc chỉ có ảnh Console chưa chứng minh hạ tầng có thể triển khai lặp lại.

### Mốc 2: Kiểm tra kết nối và quyền từng thành phần

Thử producer publish một message, dispatcher đọc được stream và gửi được Queue, worker nhận và kết nối database. Dùng đúng danh tính của từng tiến trình.

Sau đó thử hành động ngoài quyền trên tài nguyên lab: producer không được nhận Queue; worker không được publish vào stream hoặc xóa tài nguyên. Ghi kết quả bị từ chối cùng request ID nếu có.

Nếu các vai trò dùng chung một Compute instance và cùng instance principal, không thể coi chúng là ba danh tính IAM độc lập chỉ vì chạy ba process. Muốn kiểm chứng phân quyền runtime riêng phải triển khai trên instance hoặc cơ chế danh tính riêng phù hợp.

### Mốc 3: Hoàn thành luồng một sự kiện

Chạy theo thứ tự:

1. Khởi tạo schema và nạp cấu hình.
2. Khởi động một worker.
3. Khởi động một dispatcher với group name cố định.
4. Publish một envelope hợp lệ.
5. Xác nhận có một receipt và một fulfillment job.
6. Xác nhận message được xóa khỏi Queue sau thành công.

Ở mốc này chưa tăng batch, chưa thêm xử lý song song. Ghi lại `eventId`, partition/offset, Queue message ID và kết quả giao dịch để theo dõi xuyên suốt.

### Mốc 4: Chứng minh chống lặp và phục hồi

Publish lại envelope cũ; kết quả dữ liệu không tăng. Dừng worker sau commit nhưng trước delete rồi chạy lại; kết quả vẫn không tăng. Dừng dispatcher sau khi Queue nhận nhưng trước checkpoint; bản được chuyển lại vẫn chỉ tạo một hiệu ứng.

### Mốc 5: Tăng tải và vận hành

Tăng worker, thực hiện bộ lỗi có kiểm soát, đo backlog, chạy redrive/replay và ghi lại cấu hình tốt nhất trong phạm vi chi phí đã chọn. Khi đổi batch hoặc concurrency, đo lại visibility và connection pool.

Người học cần cung cấp lệnh build, lệnh chạy ba entry point và cấu hình triển khai tương ứng với ứng dụng mình xây dựng. Các đoạn trích trong bài không thay cho những đầu vào tái lập đó.

## 15. Bộ nghiệm thu thực hành

### 15.1. Dữ liệu chạy chuẩn

Tạo một lần chạy có tiền tố ID riêng, gồm:

- 1.000 sự kiện hợp lệ, mỗi sự kiện thuộc một đơn hàng riêng.
- 100 lần publish thêm của các envelope hợp lệ đã có, giữ nguyên byte nội dung.
- 10 sự kiện lỗi nghiệp vụ có ID riêng, chẳng hạn `amountMinor=-1`.

Tổng số lần publish dự kiến là 1.110; số sự kiện logic là 1.010, trong đó 1.000 hợp lệ và 10 cố ý sai. Retry do lỗi hạ tầng có thể làm số bản sao thực tế cao hơn. Mỗi bản ghi phải được theo dõi bằng manifest, không dùng số lần gọi API làm số đơn hàng.

Sau khi hệ thống xử lý ổn định:

- Có đúng 1.000 receipt của hiệu ứng `create-fulfillment:v1` cho tập hợp hợp lệ.
- Có đúng 1.000 fulfillment job khớp ID và dữ liệu đã phát.
- Mười sự kiện sai không tạo job; được xác định trong DLQ hoặc kho lỗi đã thiết kế.
- Những bản trùng không tạo thêm kết quả.
- Không còn ID hợp lệ nào chưa có lời giải thích trong đối soát.

Nếu manifest còn `UNKNOWN`, chưa thể kết luận đủ đầu vào. Cần giải quyết hoặc đưa rõ vào giới hạn kết quả.

### 15.2. Ma trận thử lỗi

| Tình huống | Cách tạo trong lab | Dấu hiệu nghiệm thu |
| --- | --- | --- |
| Publish cùng sự kiện hai lần | Dùng lại envelope | Job không tăng, bộ đếm trùng tăng |
| Dispatcher chết sau enqueue | Gắn failpoint sau publish thành công và trước lần get kế | Có thể gửi lại; không tạo job lặp |
| Worker chết trước commit | Failpoint trước commit rồi dừng tiến trình | Giao dịch không hoàn tất được rollback; message có thể giao lại |
| Worker chết sau commit | Failpoint ngay sau lớp lưu trữ return, trước delete | Delivery sau phát hiện đã áp dụng |
| Tác vụ vượt visibility | Chèn độ trễ trong xử lý | Có thể giao lại; inbox vẫn bảo vệ dữ liệu |
| Gia hạn visibility | Bật bộ gia hạn cho tác vụ dài | Giảm giao lại ngoài ý muốn; ghi nhận kết quả gia hạn |
| Database gián đoạn | Chặn kết nối có thời hạn trong lab | Không delete trước commit; sau phục hồi xử lý được hoặc có kế hoạch redrive |
| Queue tạm không truy cập được | Chặn egress của dispatcher | Stream không được checkpoint vượt chuyển giao chưa xong |
| Message sai phiên bản | Gửi version chưa hỗ trợ | Không tạo job; có phân loại lỗi và đường xử lý |
| Cùng event ID, nội dung khác | Đổi số tiền nhưng giữ ID | Phát hiện conflict, không coi là trùng hợp lệ |
| Tăng hoặc giảm dispatcher | Thêm/bớt instance name trong cùng group | Rebalance có thể xảy ra, không mất kết quả |
| Replay dữ liệu đã xử lý | Group replay riêng, giữ event ID | Không tăng fulfillment job |

Failpoint nên được điều khiển theo một `eventId` thử nghiệm và tắt sau một lần. Không thử lỗi bằng cách xóa tài nguyên dùng chung hoặc vô hiệu hóa quyền rộng của tenancy.

Một tiến trình được dừng đúng chỗ tạo bằng chứng mạnh hơn việc chỉ dừng ngẫu nhiên rồi khẳng định đã thử cửa sổ lỗi. Lưu log trước failpoint và kết quả sau phục hồi.

### 15.3. Đối soát theo tập hợp và theo nội dung

Gọi:

- `V` là tập ID hợp lệ đã được xác nhận hoặc đối soát thành công ở đầu vào.
- `D` là tập ID có receipt đúng hiệu ứng trong database.
- `J` là tập ID nguồn của fulfillment job trong lần chạy.

Khi hoàn tất:

~~~text
V \ D = rỗng
D \ V = rỗng
D = J
nội dung job khớp orderId, amountMinor và currency trong manifest
~~~

So sánh tập ID trước, so sánh số lượng sau. Hai bên cùng có 1.000 dòng vẫn có thể bị thiếu một ID và thừa một ID khác.

Ví dụ truy vấn trong phạm vi tiền tố của lần chạy:

~~~sql
SELECT COUNT(*) AS receipt_count
FROM event_receipts
WHERE effect_name = 'create-fulfillment:v1'
  AND event_id LIKE 'evt-run01-%';

SELECT COUNT(*) AS job_count
FROM fulfillment_jobs
WHERE source_event_id LIKE 'evt-run01-%';

SELECT event_id
FROM event_receipts
WHERE effect_name = 'create-fulfillment:v1'
  AND event_id LIKE 'evt-run01-%'
MINUS
SELECT source_event_id
FROM fulfillment_jobs
WHERE source_event_id LIKE 'evt-run01-%';
~~~

Cần kiểm tra chiều ngược lại và đối chiếu manifest trong chương trình nghiệm thu. Truy vấn `MINUS` trên chỉ tìm receipt không có job, chưa chứng minh đã nhận đầy đủ mọi sự kiện producer gửi.

## 16. Quan sát hệ thống và mục tiêu hiệu năng

### 16.1. Dashboard tối thiểu

Các tên dưới đây là **metric ứng dụng đề xuất**, không phải tên metric mặc định được cam kết sẵn của OCI.

| Metric | Câu hỏi cần trả lời |
| --- | --- |
| `producer_confirmed_total` | Đã có bao nhiêu lần publish được xác nhận? |
| `producer_unknown_total` | Có bao nhiêu yêu cầu chưa rõ kết quả? |
| `dispatcher_forwarded_total` | Bao nhiêu lần chuyển giao đã được Queue xác nhận? |
| `dispatcher_forward_error_total` | Lỗi chuyển giao tập trung ở loại nào? |
| `worker_delivery_total` | Đã nhận bao nhiêu delivery, gồm cả bản lặp? |
| `worker_applied_total` | Có bao nhiêu hiệu ứng mới đã commit? |
| `worker_duplicate_total` | Có bao nhiêu sự kiện trùng nội dung đã được xác minh? |
| `worker_conflict_total` | Có xung đột cùng ID khác dữ liệu không? |
| `worker_ack_error_total` | Có commit xong nhưng xóa Queue thất bại không? |
| `worker_processing_seconds` | p50, p95, p99 thời gian xử lý là bao nhiêu? |
| `pipeline_end_to_end_seconds` | Mất bao lâu từ tạo sự kiện đến hiệu ứng nghiệp vụ? |
| `db_connection_wait_seconds` | Luồng có bị nghẽn ở connection pool không? |

Bổ sung số visible/in-flight của queue và DLQ từ API/metric dịch vụ đang dùng. Queue statistics là số liệu xấp xỉ khi producer và consumer còn chạy; dùng database và manifest để đối soát kết quả cuối. [Queue statistics](https://docs.oracle.com/en-us/iaas/Content/queue/queue-statistics.htm).

Với Streaming, theo dõi độ chậm bằng số liệu dịch vụ hoặc tuổi của bản ghi chưa xử lý. Offset không nên bị dùng như bộ đếm message chính xác; không giả định phép trừ hai offset luôn bằng số bản ghi còn lại.

Log nên có component, instance, event ID, correlation ID, vị trí nguồn nếu biết, Queue message ID, delivery count nếu có, kết quả, mã lỗi và request ID. Không dùng event ID làm dimension metric có số lượng giá trị không giới hạn; dùng log để truy từng ID. Không log toàn bộ receipt, secret, wallet hoặc payload khách hàng.

### 16.2. Mục tiêu cho lần chạy chuẩn

Có thể chọn mục tiêu ban đầu:

- Luồng không lỗi: 1.000 sự kiện hợp lệ hoàn tất trong 5 phút.
- Khi hệ thống đã ấm và không có backlog: p95 từ tạo sự kiện đến commit dưới 5 giây.
- Khi một worker dừng: hệ thống tiếp tục có tiến triển và xử lý hết dữ liệu sau phục hồi trong thời hạn thử nghiệm.
- Bất kỳ sai khác dữ liệu nào trong đối soát đều làm nghiệm thu thất bại.

Đây là tiêu chí học tập. Báo cáo phải ghi cấu hình Compute, số worker, số partition, kích thước message, batch, giới hạn database và thời lượng thử. Độ trễ đầu cuối dựa trên timestamp giữa nhiều máy cần đồng bộ đồng hồ; đo thời lượng nội bộ tiến trình bằng đồng hồ đơn điệu.

### 16.3. Ước lượng năng lực và backpressure

Gọi `lambda` là tốc độ vào, `mu` là tốc độ xử lý trung bình mỗi worker và `N` là số worker. Để backlog có khả năng giảm khi đầu vào vẫn tiếp tục:

~~~text
N × mu > lambda
thời gian xử lý bù gần đúng = backlog / (N × mu - lambda)
~~~

Ví dụ đầu vào 40 message/giây, mỗi worker xử lý được 25 message/giây, hai worker cho năng lực 50 message/giây. Backlog 3.000 message cần khoảng 300 giây để giảm hết trong mô hình lý tưởng. Độ trễ database, retry và tranh chấp có thể làm thời gian thật dài hơn.

Nếu không có phần năng lực dư, tăng retention chỉ kéo dài thời gian trước khi dữ liệu hết hạn. Cần giảm tốc độ phát, tăng tài nguyên hiệu quả hoặc tối ưu nút thắt.

Không tăng worker vô hạn: khi database đã bão hòa, nhiều luồng hơn có thể làm tăng chờ kết nối, timeout và giao lặp. Giới hạn prefetch và số tác vụ đang xử lý giúp tạo backpressure có kiểm soát.

## 17. Runbook vận hành và tính sẵn sàng

### Khi backlog tăng

1. Xác định nghẽn ở Streaming-to-Queue, Queue-to-worker hay database.
2. Đọc tốc độ vào, tốc độ hoàn tất, số lỗi, in-flight và thời gian chờ JDBC.
3. So sánh thời gian phục hồi dự kiến với retention còn lại.
4. Giảm phát tải hoặc tăng thành phần đúng nút thắt.
5. Theo dõi backlog có thực sự giảm sau thay đổi.

Nếu Queue ít message nhưng tuổi sự kiện trên stream tăng, tăng worker thường không giải quyết được dispatcher đang mất quyền hoặc không kết nối Queue.

### Khi DLQ tăng

Dừng redrive hàng loạt, lấy mẫu có kiểm soát, phân loại lỗi và xác định bản phát hành liên quan. Nếu nhiều message hợp lệ vào DLQ vì database ngừng, khôi phục phụ thuộc trước rồi redrive có giới hạn. Không chỉ tăng ngưỡng delivery để che lỗi kéo dài.

### Khi một instance mất

Có thể chạy hai dispatcher trên hai Compute instance với cùng group và tên instance khác nhau. Worker cũng chạy trên các instance tách biệt; lựa chọn fault domain hoặc availability domain phù hợp với region và thiết kế hạ tầng.

Hai process trên một máy giúp thử concurrency nhưng không chứng minh chịu được mất máy. Dịch vụ messaging được quản lý cũng không loại bỏ điểm lỗi ở chương trình, kết nối database, secret hoặc quá trình triển khai.

Cơ sở dữ liệu phải được khôi phục nhất quán giữa bảng inbox và bảng nghiệp vụ. Khôi phục một bảng về thời điểm khác bảng còn lại có thể tạo trạng thái “đã xử lý” nhưng thiếu hiệu ứng, hoặc tạo cơ hội áp dụng lại.

### Khi hết retention hoặc mất bản lưu nguồn

Xác định dữ liệu nào còn trong stream, queue, DLQ, manifest và bản lưu độc lập. Công bố phạm vi có thể phục hồi, đối soát các ID bị ảnh hưởng và dùng quy trình sửa chữa nghiệp vụ nếu cần. Không tuyên bố không mất dữ liệu chỉ vì không thấy exception trong worker.

## 18. Tự động hóa, phát hành và chi phí

Đóng gói producer, dispatcher và worker với phiên bản artifact rõ ràng. Quy trình triển khai nên gồm kiểm tra cấu hình, migration schema tương thích, chạy thử ít dữ liệu và kiểm tra metric sau phát hành.

Trong bản nâng cấp, ưu tiên khả năng đọc đồng thời phiên bản sự kiện đang tồn tại. Không xóa hỗ trợ schema cũ khi stream, queue hoặc DLQ còn chứa sự kiện phiên bản đó. Một lần rollback ứng dụng cũng cần tương thích với schema database đã triển khai.

Chi phí cần theo dõi theo thành phần:

| Thành phần | Yếu tố cần đo và giới hạn |
| --- | --- |
| Streaming | Partition, lưu lượng, retention theo cách tính phí áp dụng |
| Queue | Số request, retry, polling rỗng, kích thước message |
| Compute | Số instance, cấu hình CPU/RAM, thời gian chạy, boot volume |
| Database | Cấu hình xử lý, lưu trữ, backup và số kết nối |
| Mạng | Đường ra, NAT và lưu lượng liên quan theo cấu hình thật |
| Quan sát | Dung lượng log, retention và số metric/dimension |

Lấy biểu phí áp dụng cho region và tenancy khi lập dự toán; không dùng số tiền cố định trong bài như cam kết. Đặt ngân sách thực hành, cảnh báo sử dụng và giới hạn phát tải trong công cụ của dự án. Một cảnh báo ngân sách không được coi là cơ chế tự dừng producer nếu chưa có tự động hóa thực hiện việc đó.

Dọn tài nguyên theo thứ tự có kiểm soát:

1. Dừng producer và ghi trạng thái manifest.
2. Cho hệ thống xử lý hết hoặc lưu lại phần cần giữ.
3. Dừng dispatcher, worker và cơ chế tự khởi động lại.
4. Lưu bằng chứng cần thiết, sau đó xóa tài nguyên chuyên dùng của lab theo danh sách đã ghi.
5. Kiểm tra tài nguyên còn tính phí như volume, database, backup, endpoint hoặc log.
6. Thu hồi quyền và thông tin xác thực chỉ được tạo cho dự án.

Không xóa stream hoặc queue trước khi đối soát xong rồi dùng database hiện có làm bằng chứng duy nhất về đầu vào.

## 19. Hồ sơ nộp và thang đánh giá

Bài nộp của người học gồm mã nguồn ba thành phần, dependency/version cố định, hướng dẫn build và chạy, mô tả hạ tầng có thể tái lập, schema, cấu hình mẫu không chứa secret, manifest, kết quả thử lỗi, dashboard và runbook.

Báo cáo cần trả lời được ba vấn đề bằng bằng chứng: hệ thống đã nhận những gì, đã tạo hiệu ứng gì, và mỗi điểm ngắt giữa hai thành phần được phục hồi ra sao.

| Hạng mục | Điểm tối đa | Bằng chứng |
| --- | --- | --- |
| Hợp đồng và kiến trúc | 15 | Vai trò từng dịch vụ, ID, ranh giới xác nhận, giả định retention |
| Producer và dispatcher | 20 | Kết quả từng phần tử, cursor/group ổn định, chuyển giao trước checkpoint |
| Worker và tính đúng dữ liệu | 25 | Giao dịch inbox + nghiệp vụ, hash conflict, delete sau commit |
| Thử lỗi và khôi phục | 15 | Failpoint, replay/redrive, đối soát theo ID và nội dung |
| IAM và mạng | 10 | Vai trò riêng, kiểm tra quyền âm, kết nối được giới hạn |
| Quan sát, triển khai và chi phí | 15 | Metric, cấu hình tái lập, kết quả tải, runbook, dọn tài nguyên |
| **Tổng** | **100** | |

Dự án chỉ được xem là đạt khi không còn sai khác dữ liệu chưa giải thích và đã chứng minh phục hồi ở hai cửa sổ quan trọng: dispatcher sau enqueue nhưng trước checkpoint; worker sau commit nhưng trước delete.

Các trường hợp cần sửa trước khi nghiệm thu, bất kể tổng điểm: xóa message trước commit; bỏ qua message lỗi rồi tiến checkpoint; coi mọi lỗi unique là bản trùng hợp lệ; hoặc tuyên bố bảo đảm đầu cuối đúng một lần mà không xác định phạm vi giao dịch.

## 20. Hướng mở rộng sau khi hoàn thành bản cơ bản

Chọn một hướng và giữ nguyên bộ kiểm chứng tính đúng dữ liệu:

- Thêm consumer group độc lập để tạo projection báo cáo mà không thay đổi group điều phối.
- Bổ sung outbox để phát kết quả nghiệp vụ, rồi thử crash sau publish nhưng trước đánh dấu outbox.
- Hỗ trợ chuỗi sự kiện trên cùng đơn hàng bằng sequence/version và quy tắc chuyển trạng thái; kiểm thử sự kiện đến muộn.
- Lưu dữ liệu nguồn phục vụ phục hồi dài hơn retention, kèm danh mục và cơ chế tránh replay nhầm.
- Tự động điều chỉnh worker theo backlog cùng giới hạn kết nối database.
- Thực hiện diễn tập khôi phục database và chứng minh inbox nhất quán với dữ liệu nghiệp vụ.

Mỗi hướng mở rộng phải chỉ ra bất biến mới, cách quan sát và kịch bản thất bại. Thành công của capstone được thể hiện ở khả năng giải thích và tái lập kết quả khi có lỗi, cùng đường đi của một thông điệp từ lúc producer nhận trách nhiệm đến khi hiệu ứng nghiệp vụ đã được lưu bền vững.
