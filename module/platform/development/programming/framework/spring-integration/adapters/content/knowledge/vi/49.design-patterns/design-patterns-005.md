# Claim Check với Message Store trong Spring Integration Adapters

> **Chương:** Design patterns  
> **Chủ đề:** Claim check với message store  
> **Phạm vi module:** SPRING_INTEGRATION_ADAPTERS — kết nối hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel. Bài này tập trung vào Claim Check trong các luồng file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; thiết kế hợp đồng message, lưu/khôi phục payload, xử lý lỗi, bảo mật, giao dịch và vòng đời dữ liệu.

## 1. Bài toán: payload lớn, nhưng hệ thống trung gian chỉ cần một tham chiếu

Hãy tưởng tượng hệ thống nhận một báo cáo PDF dung lượng 80 MB qua HTTP, cần chuyển yêu cầu kiểm tra sang một hàng đợi broker rồi gửi đến dịch vụ phân tích. Broker có giới hạn kích thước message, các router chỉ cần biết mã hồ sơ và loại xử lý; không có lý do để tải 80 MB qua mọi bước điều phối.

**Claim Check** là một Enterprise Integration Pattern (EIP) giúp **tạm cất một phần hoặc toàn bộ nội dung message ở kho lưu trữ**, rồi truyền qua integration flow một **tham chiếu/claim token** nhỏ hơn. Tại nơi cần dữ liệu, consumer sử dụng token để **lấy lại nội dung gốc** từ kho được kiểm soát.

~~~mermaid
sequenceDiagram
    participant P as Producer / Inbound Adapter
    participant IN as Claim Check In
    participant STORE as Message Store
    participant CH as Channel / Broker
    participant OUT as Claim Check Out
    participant H as Business Handler
    P->>IN: Message chứa payload lớn
    IN->>STORE: Lưu message / payload
    STORE-->>IN: Claim token
    IN->>CH: Message chứa claim token
    CH->>OUT: Claim token
    OUT->>STORE: Tra dữ liệu theo token
    STORE-->>OUT: Original message / payload
    OUT->>H: Message được phục hồi
    H-->>OUT: Business result / commit
    Note over STORE,H: Xóa claim chỉ khi chính sách hoàn tất cho phép
~~~

### 1.1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Trình bày Claim Check và phân biệt với **Message Store**, **Content Enricher**, **Message Filter**, **Splitter** và **Idempotent Consumer**.
2. Hiểu vai trò của **ClaimCheckInTransformer**, **ClaimCheckOutTransformer**, **MessageStore** và **MessageChannel** trong Spring Integration.
3. Quyết định **lưu toàn bộ Message, chỉ lưu payload, hay dùng kho object ngoài kèm metadata**, thay vì mặc định database chịu được mọi file.
4. Tạo hợp đồng claim token có ID, nguồn, tenant, version, quyền truy cập, TTL và kiểm tra tính toàn vẹn.
5. Kết nối flow Claim Check với File/SFTP, HTTP, JMS, AMQP, Kafka và các adapter dùng database.
6. Phân biệt **đã lưu**, **đã publish token**, **đã lấy lại**, **đã xử lý/commit**, **đã xóa** — các trạng thái không tương đương.
7. Xử lý lỗi mất claim, duplicate token, retry sau crash, token hết hạn, consumer cạnh tranh và fan-out.
8. Thiết kế security, retention, cleanup, observability và kiểm thử end-to-end.

### 1.2. Sản phẩm của bài thực hành

Người học sẽ thiết kế một pipeline giả lập: một file CSV hoặc tài liệu lớn được nhận qua File/SFTP/HTTP, cất vào kho dùng chung, đưa **ClaimReference** qua MessageChannel/broker, sau đó consumer kiểm tra quyền và lấy dữ liệu để xử lý. Bài lab yêu cầu có cả **đường thành công**, **đường lỗi**, **khôi phục sau restart** và **bằng chứng không xóa claim trước khi consumer hoàn tất**.

**Lưu ý:** các tên ID, endpoint, schema và dữ liệu trong bài đều là minh họa. Không dùng kho production hoặc dữ liệu cá nhân thật khi chạy lab.

## 2. Claim Check Pattern vận hành thế nào?

Trong EIP, “claim check” gợi hình ảnh gửi hành lý tại quầy rồi nhận một phiếu để lấy lại. Trong tích hợp hệ thống:

- **Hành lý** là original payload hoặc original message.
- **Quầy giữ** là persistent store hoặc một kho được quản lý.
- **Phiếu nhận** là claim token/reference.
- **Người nhận** là một downstream consumer được phép truy xuất.

### 2.1. Năm bước cơ bản

1. **Nhận dữ liệu:** inbound adapter tạo Message chứa nội dung cần xử lý.
2. **Claim check in:** lưu message hoặc nội dung lớn vào kho, sinh/nhận mã định danh ổn định.
3. **Chuyển token:** gửi message nhỏ chứa claim ID (và metadata tối thiểu) qua channel/broker.
4. **Claim check out:** consumer nhận token, xác minh hợp lệ rồi lấy lại dữ liệu.
5. **Xử lý và thu dọn:** handler hoàn thành nghiệp vụ; claim được giữ hoặc dọn theo **completion, retry, fan-out, audit và retention policy**.

### 2.2. Vì sao cần truyền token?

| Vấn đề khi truyền payload nguyên vẹn | Claim Check có thể giúp | Điều Claim Check không tự giải quyết |
| --- | --- | --- |
| Broker hạn chế kích thước record/message | Gửi reference nhỏ | Kho lưu phải chứa/đọc được payload lớn |
| Router, filter chỉ cần metadata | Chuyển token + routing metadata | Nếu router cần đọc payload vẫn phải lấy dữ liệu |
| Nhiều thành phần trung gian sao chép byte lớn | Giảm byte qua các channel trung gian | Tổng I/O vẫn gồm lưu và đọc kho |
| Dữ liệu cần giữ lâu để retry/audit | Kho lưu được quản trị riêng | TTL, backup, access control và cleanup phải thiết kế |
| Các worker chạy ở instance khác nhau | Reference tới kho dùng chung | Local path/in-memory store không tự chia sẻ được |
| Payload có thông tin nhạy cảm | Có thể hạn chế hệ trung gian nhìn thấy nội dung | Claim token có thể trở thành đường truy cập trái phép |

Claim Check là **đánh đổi I/O mạng qua broker lấy I/O lưu và khôi phục**, không phải thủ thuật nén, mã hóa hay đảm bảo performance cao hơn trong mọi workload.

### 2.3. Phân biệt Claim Check với các pattern khác

| Pattern | Chức năng chính | Điểm khác Claim Check |
| --- | --- | --- |
| **Claim Check** | Cất payload/message, truyền token, lấy lại sau | Thay nội dung lớn bằng reference tạm/thường trực |
| **Content Enricher** | Bổ sung dữ liệu từ nguồn khác | Không bắt buộc cất message ban đầu rồi lấy lại |
| **Message Filter** | Giữ hoặc loại message theo điều kiện | Không có hợp đồng lưu/retrieval nội dung |
| **Splitter/Aggregator** | Chia/gom message | Không tự làm message bớt lớn do chuyển reference |
| **Idempotent Consumer** | Ngăn áp dụng cùng một thao tác nhiều lần | Token trỏ cùng payload chưa chứng minh business chỉ chạy một lần |
| **Message Store** | Cung cấp API lưu/truy xuất Message | Là thành phần lưu; Claim Check là pattern dùng thành phần ấy |
| **Transactional Outbox** | Gắn thay đổi DB với ý định publish event | Giải quyết atomic publish, có thể kết hợp Claim Check |
| **Object storage link** | Tham chiếu một object lưu ngoài | Có thể là implementation của Claim Check nếu có contract store/redeem |

### 2.4. Không nhầm Claim Check với queue

**MessageStore** nơi giữ original message không tự là một **work queue** phân phối công việc. Một broker/JMS/Kafka/QueueChannel có thể mang token đi, còn store giữ dữ liệu thực. Việc có một claim trong store không đồng nghĩa đã có một message trong broker; việc xóa token khỏi broker không tự xóa object trong store.

## 3. Hai vòng đời tách biệt: message vận chuyển và dữ liệu được claim

Một thiết kế đúng phải theo dõi **delivery lifecycle** và **claim lifecycle** riêng.

### 3.1. Vòng đời token khi truyền qua broker

~~~text
CREATED -> PUBLISHED -> DELIVERED -> PROCESSING -> ACKNOWLEDGED
                         |
                         +--> REDELIVERED / RETRY / DEAD-LETTER
~~~

### 3.2. Vòng đời nội dung trong Message Store

~~~text
PREPARED -> STORED -> AVAILABLE -> RETRIEVED
                         |           |
                         |           +--> IN_USE / COMPLETED
                         |
                         +--> EXPIRED_PENDING_CLEANUP
                                     |
                                     +--> DELETED / RETAINED_FOR_AUDIT
~~~

Đây là mô hình nghiệp vụ gợi ý, **không phải enum có sẵn** của Spring Integration. Các trạng thái claim phải được định nghĩa trong ứng dụng nếu cần theo dõi; MessageStore interface không mặc định là một workflow engine.

### 3.3. Các mốc dễ bị hiểu nhầm

| Mốc | Ý nghĩa | Chưa thể kết luận |
| --- | --- | --- |
| Lưu message thành công | Kho có dữ liệu | Broker đã nhận token chưa |
| Publish token thành công | Transport ghi nhận một bước theo contract | Consumer lấy lại được payload chưa |
| Retrieve claim thành công | Consumer đọc được nội dung | Business handler đã commit chưa |
| Handler trả về | Một bước xử lý đã hoàn tất theo luồng gọi | Các tác động async/ngoài transaction đã xong chưa |
| Broker ack/offset commit | Broker/consumer group ghi nhận tiến độ | Claim đã được dọn đúng hạn chưa |
| Xóa claim | Dữ liệu không còn trong store ở đường đó | Business không còn cần retry/audit/fan-out chưa |

### 3.4. Cửa sổ lỗi điển hình

~~~mermaid
flowchart TD
    STORE["Lưu original message"] --> PUB{"Publish token thành công?"}
    PUB -->|Không| ORPHAN["Claim mồ côi / pending publish"]
    PUB -->|Có| TAKE["Consumer nhận token"]
    TAKE --> RET{"Retrieve được claim?"}
    RET -->|Không| MISSING["Missing / expired / unauthorized / store unavailable"]
    RET -->|Có| PROCESS["Business handler"]
    PROCESS --> COMMIT{"Commit đạt?"}
    COMMIT -->|Không| RETRY["Retry/requeue, giữ dữ liệu cần thiết"]
    COMMIT -->|Có| ACK["Ack theo broker/transport"]
    ACK --> CLEAN["Cleanup khi tất cả nghĩa vụ kết thúc"]
    ORPHAN --> RECON["Outbox/reconciliation/garbage collection"]
    MISSING --> RECON
    RETRY --> PROCESS
~~~

**Quy tắc quan trọng:** Không xóa dữ liệu chỉ vì **đã lấy ra (retrieved)** nếu downstream còn khả năng thất bại. Tùy đặc tính của flow, việc xóa ngay khi Claim Check Out có thể làm mọi lần redelivery sau đó thiếu payload.

## 4. Claim check token nên chứa những gì?

Một token tốt phải **nhỏ, khó đoán, không lộ payload**, dễ xác minh và có thể truy vết; nhưng token **không thay thế authorization**.

### 4.1. Envelope tham chiếu minh họa

~~~json
{
  "claimId": "clm-lab-7e8d03ac",
  "claimSchemaVersion": 1,
  "sourceSystem": "partner-sftp-lab",
  "tenantId": "TENANT-LAB-01",
  "payloadKind": "ORDER_CSV",
  "contentType": "text/csv",
  "businessKey": "PARTNER-A/DOC-2026-0041",
  "contentVersion": 2,
  "sizeBytes": 83886080,
  "createdAt": "2026-11-23T10:00:00+07:00",
  "expiresAt": "2026-11-30T10:00:00+07:00",
  "checksumSha256": "<digest-redacted-for-example>"
}
~~~

Đây là một **contract mở rộng do ứng dụng tự thiết kế**, **không phải payload mặc định** mà Spring Integration ClaimCheckInTransformer tạo ra. Transformer Claim Check In của Spring Integration thường đưa **ID message được lưu** vào payload của message tiếp theo; nếu muốn envelope có owner, tenant, expiry, checksum thì cần xây thêm metadata/transformer ở flow của mình.

### 4.2. Các trường và trách nhiệm

| Trường | Nguồn đáng tin | Công dụng |
| --- | --- | --- |
| claimId | Store/producer tin cậy | Tra cứu dữ liệu; không tự nhận là chứng cứ phân quyền |
| tenantId | Identity/policy hoặc nguồn được xác minh | Cách ly dữ liệu giữa tenant |
| sourceSystem | Cấu hình connector và principal | Audit nguồn dữ liệu |
| businessKey | Hợp đồng producer | Idempotency và reconciliation |
| contentVersion | Schema/business version | Phát hiện stale/ghi đè |
| sizeBytes/contentType | Từ dữ liệu được kiểm tra | Chặn file quá lớn, kiểm soát parser |
| checksum | Tính sau khi lưu nội dung | So tính toàn vẹn khi lấy ra |
| createdAt/expiresAt | Server và retention policy | Cleanup/TTL; không do client tự nâng tùy ý |
| owner/allowedConsumer | Registry hoặc policy nội bộ | Kiểm soát quyền redeem |
| traceId | Context tracing đáng tin | Liên kết request, store và consumer |

### 4.3. Token nên là ID hay URL?

- **Opaque claim ID** (ID không chứa thông tin nhạy cảm) phù hợp khi consumer truy xuất qua một service/store adapter có kiểm tra quyền.
- **Object key** của object storage có thể lưu nội bộ; phải chống truy cập chéo tenant hoặc đọc object tùy ý.
- **Signed URL có thời hạn** có thể dùng trong một số luồng download, nhưng URL chính là khả năng truy cập trong khoảng hiệu lực: không log tràn lan, giới hạn TTL/scope và giải quyết replay.
- **Local file path** chỉ phù hợp khi consumer có thể truy cập đúng cùng storage và security boundary; không tự có hiệu lực xuyên pod/server.

**Đừng đặt raw payload, password hoặc access token vào claim token**. Nếu ai có claim ID là truy xuất được nội dung mà không cần quyền, token trở thành bearer credential nhạy cảm và phải được bảo vệ tương xứng — tốt hơn là có kiểm tra identity và authorization khi redeem.

## 5. Cần cất toàn bộ Message hay chỉ một phần payload?

Có hai lựa chọn chính:

1. **Full-message Claim Check:** lưu Message gồm payload và headers vào MessageStore; token thay thế nội dung trong đoạn flow trung gian. Spring Integration có transformer cho kiểu này.
2. **Payload/object Claim Check:** cất byte lớn ở object storage hoặc một kho chuyên dụng, giữ lại envelope metadata nhỏ. Ở downstream cần một handler/enricher đọc object và tái lập payload/hợp đồng cần thiết.

### 5.1. So sánh hai kiểu

| Tiêu chí | Full-message store | Object/payload store |
| --- | --- | --- |
| Dữ liệu lưu | Spring Message (payload + headers phù hợp lưu trữ) | Blob/object bytes, metadata riêng |
| Dễ tích hợp ClaimCheckIn/Out | Có thể dùng transformer hỗ trợ | Thường cần adapter/transformer tùy chỉnh |
| Payload rất lớn | Phụ thuộc khả năng serialize/blob/DB của MessageStore | Object storage thường phù hợp hơn khi kích thước lớn |
| Versioning | Cần quản lý Java serialization/header compatibility | Có thể dùng schema object/content version độc lập |
| Bảo mật | Quyền truy cập MessageStore và những headers được lưu | Bucket/object ACL và service để redeem |
| Cleanup | MessageStore remove/retention do hệ thống quản lý | Object lifecycle + metadata cleanup |
| Fan-out | Một message ID có thể bị nhiều nhánh đọc | Một object có thể nhiều reader, quản lý retention chung |

### 5.2. Header nào không nên cất hoặc khôi phục mù quáng?

Trong một Spring Message có thể có **replyChannel, errorChannel, correlation, transport headers, tracing**, đôi khi còn chứa đối tượng channel nội bộ hoặc nội dung không phù hợp serialization. Không nên hứa rằng mọi loại header có thể serialize rồi khôi phục an toàn qua JVM/broker/restart.

Đặc biệt:

- **replyChannel nội bộ** không phải địa chỉ mạng có thể đưa nguyên object tới JVM khác.
- **HTTP/JMS/AMQP/Kafka headers** có thể chứa thông tin routing, authentication hoặc kiểu dữ liệu riêng của adapter.
- **SecurityContext/thread-local** không tự được khôi phục từ MessageStore; phải xác thực/ủy quyền lại khi consumer chạy.
- **Trace headers** nên truyền đúng chuẩn, nhưng không trở thành dữ liệu được client tùy ý đặt để kiểm soát quyền.

### 5.3. Khi nào Claim Check không đáng dùng?

Nếu payload chỉ vài KB, channel/broker xử lý tốt, không có bước routing nào muốn tránh copy, thì thêm kho riêng sẽ tạo **điểm lỗi mới**, I/O, latency, TTL và yêu cầu bảo mật. Claim Check chỉ có ích khi lợi ích truyền **reference** vượt chi phí lưu, lấy lại, sao lưu và cleanup.

## 6. Các thành phần Claim Check trong Spring Integration

Spring Integration hiện thực Claim Check thông qua các **transformer** phối hợp với **MessageStore**. Cần phân biệt tên class của framework với state machine nghiệp vụ do ta tự thiết kế.

### 6.1. Các thành phần chính

| Thành phần | Vai trò | Điều cần biết |
| --- | --- | --- |
| **ClaimCheckInTransformer** | Lưu original Message vào MessageStore và tạo claim-check message | Payload trên đường đi tiếp thường là ID của message được lưu |
| **ClaimCheckOutTransformer** | Dùng ID claim để tra và khôi phục original Message từ store | Có chính sách giữ/xóa message đã lấy, cần gắn với retry |
| **MessageStore** | Abstraction lưu, lấy và xóa Message theo ID | Không mặc định có TTL, giao dịch xuyên broker hoặc encryption |
| **SimpleMessageStore** | MessageStore lưu trong bộ nhớ, phù hợp demo/test | Không chia sẻ giữa các JVM và không bền qua restart |
| **JdbcMessageStore** | MessageStore dựa trên database | Cần schema, transaction, serializer, quản trị dữ liệu và vận hành |
| **MessageChannel** | Kênh mang message chứa token hoặc payload | Channel không nhất thiết là persistent store |
| **Service Activator** | Business handler xử lý dữ liệu đã restore | Phải hoàn thành đúng contract trước cleanup |

**Quan trọng:** Tên thành phần trên thuộc hệ sinh thái Spring Integration, nhưng API constructor, Java DSL helper, thuộc tính XML và cách serialize có thể khác giữa các phiên bản Spring Integration. Khi đưa vào ứng dụng thật, sử dụng đúng Spring Integration reference/API của phiên bản dependency; không áp dụng nguyên cấu hình giả định cho mọi phiên bản.

### 6.2. Ranh giới lưu trữ

~~~mermaid
flowchart LR
    S["File/HTTP/SFTP Inbound"] --> IN["ClaimCheckInTransformer"]
    IN --> STORE[("MessageStore")]
    IN --> TOKEN["Token-only MessageChannel"]
    TOKEN --> BROKER["JMS/AMQP/Kafka Adapter"]
    BROKER --> RECEIVE["Inbound Adapter"]
    RECEIVE --> OUT["ClaimCheckOutTransformer / Redeem Service"]
    STORE --> OUT
    OUT --> HANDLER["Business Handler"]
    HANDLER --> DB[("Business DB")]
    HANDLER --> GC["Cleanup Coordinator"]
    GC --> STORE
~~~

**Tình huống cross-JVM:** nếu consumer bên kia broker chạy trong một process khác, hai phía phải truy cập được **cùng một kho lưu hoặc API claim**, có cùng cách diễn giải token và cùng quyền truy xuất. **SimpleMessageStore** chỉ được khai báo riêng ở hai JVM không tạo một store dùng chung.

### 6.3. API MessageStore thường dùng ở mức khái niệm

~~~text
addMessage(originalMessage)
    -> lưu original Message theo message headers ID

getMessage(messageId)
    -> đọc original Message, không mặc nhiên xóa

removeMessage(messageId)
    -> lấy/xóa theo hợp đồng của store nếu được phép
~~~

Với claim-check transformer có sẵn, thường không cần tự thực hiện các bước lưu/lấy trên trong business handler. Nhưng khi thiết kế retention, custom adapter hoặc sửa lỗi, cần hiểu **MessageStore là nơi dữ liệu nằm**, còn message chứa token là **đường vận chuyển**.

### 6.4. MessageStore khác MessageGroupStore và ChannelMessageStore

Một số thành phần Spring Integration dùng cơ chế lưu **message group** cho aggregator/resequencer hoặc lưu message **ở một persistent channel**. Chúng có thể dùng các interface và schema khác với một Claim Check message đơn lẻ. Không suy luận rằng chỉ cần khai báo một bean MessageStore thì mọi QueueChannel, aggregator và broker đều dùng chung cơ chế lưu.

Đặt trách nhiệm riêng:

- **Claim store** lưu dữ liệu cần redeem theo claim ID.
- **Message queue/store** quản lý thứ tự, ack hoặc việc nhận work.
- **Business DB** lưu kết quả nghiệp vụ.
- **Audit/metadata store** ghi trạng thái publish, retrieve, completion và cleanup.

## 7. XML cấu hình Claim Check trong một flow Spring Integration

Cấu hình XML sau minh họa cách kết nối claim-check-in/out với MessageStore trong **một ứng dụng**. Đây là cách trình bày có tính khái niệm và gần với namespace của Spring Integration; khi copy vào dự án, cần khai báo schema/version tương thích và áp dụng chính sách lưu trữ của môi trường.

### 7.1. Một flow hai chặng trong JVM

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <!-- Demo only: store in memory, not durable across restarts. -->
    <bean id="claimMessageStore"
          class="org.springframework.integration.store.SimpleMessageStore"/>

    <int:channel id="largeMessages"/>
    <int:channel id="claimTokens"/>
    <int:channel id="restoredMessages"/>

    <int:claim-check-in
        input-channel="largeMessages"
        output-channel="claimTokens"
        message-store="claimMessageStore"/>

    <int:claim-check-out
        input-channel="claimTokens"
        output-channel="restoredMessages"
        message-store="claimMessageStore"
        remove-message="false"/>
</beans>
~~~

Với cấu hình này, message gửi vào **largeMessages** được biến thành một **claim-check message**. Để minh họa end-to-end, **claimTokens** đang nối trực tiếp với bước khôi phục. Ở thiết kế thực, tại vị trí đó bạn có thể thêm router, outbound adapter hoặc broker, nhưng điều này đòi hỏi **store dùng chung, serialization tương thích và thiết kế ack/cleanup**.

**Chú ý về remove-message:** lựa chọn giữ original message khi redeem giúp thực hành retry mà không mất dữ liệu. Nếu dùng cấu hình tự xóa sau khi nhận lại, việc xóa có thể xảy ra **trước business commit** ở downstream; cần kiểm chứng toàn flow trước khi chọn. Tên và giá trị mặc định của thuộc tính phải được kiểm tra theo phiên bản Spring Integration cụ thể.

### 7.2. Khi nào không dùng chỉ một channel liên tiếp?

Ví dụ trên để học. Trong dự án thật, nếu đưa token qua broker:

~~~text
Producer JVM:
  HTTP/File/SFTP inbound
      → Claim Check In (shared store)
      → token channel
      → JMS/AMQP/Kafka outbound adapter

Consumer JVM:
  JMS/AMQP/Kafka inbound adapter
      → token validation/authorization
      → Claim Check Out (same shared store)
      → business handler
      → acknowledge/commit theo contract
      → cleanup coordinator
~~~

**Không được** đặt ClaimCheckOutTransformer ở producer rồi tưởng token đã đi qua broker, hoặc gửi original binary ở một header khác khiến kích thước message vẫn quá giới hạn. Cần kiểm tra **message thật đi trên transport** chỉ còn metadata nhỏ.

### 7.3. Vì sao không nên bật xóa-on-read khi chưa thiết kế retry?

Giả sử consumer lấy claim, transformer **xóa original ngay**, sau đó handler gặp DB timeout. Broker có thể redeliver token nhưng store đã mất original message. Kết quả là một công việc **không thể khôi phục bằng retry thông thường**.

Một chính sách an toàn hơn trong nhiều trường hợp:

1. Claim Check Out **đọc, chưa xóa**.
2. Handler kiểm tra và commit nghiệp vụ.
3. Broker ack/offset commit phù hợp.
4. Claim chuyển sang trạng thái đủ điều kiện cleanup khi không còn consumer/obligation cần dữ liệu.
5. GC xóa theo retention/safety window, có audit.

Điều này **không tạo một transaction atomic qua broker và store**; cần xử lý crash/reconciliation như các phần sau trình bày.

## 8. Java 17: thao tác MessageStore để hiểu Claim Check

Bài lab nhỏ này dùng **SimpleMessageStore**, MessageBuilder và MessageHeaders.ID để nhìn rõ quy trình cất rồi lấy lại dữ liệu. Đây **không phải** một ứng dụng Spring Boot production và chưa có bảo mật, TTL hoặc broker.

### 8.1. Đoạn mã minh họa API store

~~~java
import java.util.UUID;

import org.springframework.integration.store.MessageStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class ClaimStoreLab {

    public static void main(String[] args) {
        MessageStore store = new SimpleMessageStore();

        Message<String> original = MessageBuilder
                .withPayload("large-payload-placeholder")
                .setHeader("businessKey", "DOC-LAB-0041")
                .build();

        // Store a Message; the original MessageHeaders ID is its lookup key.
        store.addMessage(original);
        UUID claimId = original.getHeaders().getId();

        // Token travels separately; for demonstration use a UUID value.
        System.out.println("Claim token: " + claimId);

        Message<?> restored = store.getMessage(claimId);
        if (restored == null) {
            throw new IllegalStateException("Missing claim");
        }
        System.out.println("Restored: " + restored.getPayload());

        // Cleanup only after an explicitly verified completion in real flows.
        store.removeMessage(claimId);
        System.out.println("After cleanup: " + store.getMessage(claimId));
    }
}
~~~

Khi chạy trong project có **spring-integration-core** phù hợp, bạn sẽ thấy một ID để tra cứu message, payload được khôi phục và truy vấn cuối trả về không còn message sau khi remove. Đây là thí nghiệm **store API**, chưa có ClaimCheckInTransformer thực sự hoặc một MessageChannel vận chuyển token.

### 8.2. Từ thí nghiệm API sang transformer của framework

Phần Claim Check In/Out thực tế nên sử dụng transformer của Spring Integration khi đáp ứng nhu cầu. Về mặt trách nhiệm:

~~~text
ClaimCheckInTransformer:
  original Message
    → MessageStore.addMessage(...)
    → Message có payload là claim ID

ClaimCheckOutTransformer:
  Message có payload claim ID
    → MessageStore.getMessage(...)
    → restored original Message
    → tùy cấu hình, có thể remove stored message
~~~

Đây là sơ đồ logic, không cam kết mọi header hoặc kiểu dữ liệu có cùng hình dạng trong tất cả phiên bản. Một transformer tự viết cần định nghĩa **header propagation, ID canonicalization, error behavior và retention** rõ ràng; không nên thay implementation có sẵn bằng một vài dòng code mà bỏ qua những khía cạnh ấy.

### 8.3. Các giới hạn của SimpleMessageStore

- **Dữ liệu nằm trong RAM**, mất khi ứng dụng dừng và không chia sẻ giữa nhiều pods.
- Không phù hợp file 80 MB x số lượng lớn nếu không có memory budget.
- Không tự có encryption at rest, backup hoặc retention policy như một kho bền vững.
- Hai instance cùng tạo SimpleMessageStore sẽ có **hai tập ID độc lập**.
- Không tự hỗ trợ gửi token qua Kafka/JMS rồi redeem từ process khác.

Thí nghiệm này chỉ dùng để hiểu **message store API**, không chứng minh tính bền vững của một thiết kế cross-service.

## 9. MessageStore bền vững và kho object ngoài

### 9.1. Khi chọn JdbcMessageStore

Một **JdbcMessageStore** có thể lưu message trong relational database phù hợp cho các flow cần restart/recovery. Tuy nhiên:

| Vấn đề | Cần xác định |
| --- | --- |
| Schema/table | Tạo schema tương thích phiên bản Spring Integration và DB |
| Serialization | Payload/headers lưu được, tương thích khi nâng cấp Java/class |
| Transaction | Khi add/get/remove commit? Có tham gia transaction nào? |
| Dung lượng | BLOB/table growth, index, backup, vacuum/maintenance |
| Connection pool | Số lượt claim-in/out, concurrency và DB saturation |
| Security | DB user quyền tối thiểu, encryption, quản trị backup |
| Expiry/cleanup | Ai xóa theo retention; có checkpoint/fan-out an toàn không |
| Availability | DB tạm offline thì producer/consumer làm gì |

**Không coi JdbcMessageStore là object storage vô hạn**. Nếu mỗi message là video hoặc dataset hàng GB, việc serialize toàn Message vào DB có thể gây bottleneck, backup nặng và rủi ro schema/serialization khi triển khai phiên bản mới.

### 9.2. Lưu object lớn ngoài store

Với file/binary lớn, một thiết kế khác là lưu payload vào **object storage hoặc một kho file dùng chung bền vững**, rồi dùng metadata store để quản lý claim ID, object key, owner, size, checksum, TTL và trạng thái.

~~~mermaid
flowchart LR
    IN["HTTP/SFTP/File inbound"] --> OBJ["Upload immutable object"]
    OBJ --> BLOB[("Shared Object Storage")]
    OBJ --> META[("Claim Metadata DB")]
    META --> TOKEN["Claim Reference"]
    TOKEN --> BROKER["Broker / MessageChannel"]
    BROKER --> AUTH["Validate claim + caller"]
    AUTH --> META
    AUTH --> FETCH["Fetch + checksum verify"]
    BLOB --> FETCH
    FETCH --> BIZ["Business processing"]
    BIZ --> CLEAN["Retention / Cleanup"]
    CLEAN --> BLOB
    CLEAN --> META
~~~

**Lưu ý:** Đây là một implementation Claim Check tự thiết kế, **không đồng nghĩa** chỉ cấu hình ClaimCheckInTransformer với JdbcMessageStore rồi tự động có bucket object storage. Bạn phải xây service/adapter làm việc với object key, storage permissions, metadata, streaming và cleanup.

### 9.3. Bảo đảm object hoàn tất trước khi publish token

Khi upload payload:

1. Nhận dữ liệu vào khu **staging**; giới hạn content length, kiểm tra loại dữ liệu/antimalware theo policy.
2. Ghi object hoàn chỉnh; kiểm tra checksum/size và durable write theo storage contract.
3. Ghi metadata claim trạng thái AVAILABLE cùng object key bất biến.
4. Chỉ publish token khi object và metadata đã thực sự sẵn sàng.
5. Nếu publish lỗi, giữ record pending/outbox để retry thay vì bỏ mất ý định phát token.

Không publish token trỏ đến file đang upload dở. Với remote object storage, cần hiểu semantics của object visibility, multipart upload và cách công bố final object của provider.

### 9.4. Immutable object và content version

Nên tránh overwrite cùng một object key khi một token còn được consumer sử dụng. Một claim ID nên trỏ tới **phiên bản nội dung bất biến hoặc được version hóa**, để retry cùng token không trả về hai payload khác nhau. Nếu dữ liệu phải cập nhật, tạo version/claim mới với liên kết nghiệp vụ rõ ràng.

### 9.5. Checksum là kiểm tra toàn vẹn, không phải xác thực nguồn

SHA-256 giúp phát hiện byte khác sau lưu/chuyển. Nhưng nếu attacker sửa cả payload **và** checksum trong metadata không được bảo vệ, checksum không còn ý nghĩa an ninh. Kết hợp kiểm soát ghi metadata, nguồn tin cậy, object integrity và audit. Với nội dung rất nhạy cảm có thể cần chữ ký hoặc MAC theo threat model.

## 10. Gắn Claim Check với từng adapter và giao thức

Claim Check giải quyết cách **truyền reference**, không thay đổi bản chất delivery của adapter nguồn. Cùng một pattern nhưng việc phát hiện dữ liệu, ack, quyền truy xuất và timeout của File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC rất khác nhau.

### 10.1. File inbound adapter

~~~text
Shared folder / incoming file
    → File inbound MessageSource được poll
    → kiểm tra file ready + schema
    → cất nội dung vào claim store
    → phát claim token tới MessageChannel/broker
    → downstream nhận token, fetch dữ liệu, xử lý
    → archive/delete nguồn theo completion policy
~~~

Nếu file đã nằm trên một **shared durable filesystem** mà mọi consumer đều được phép đọc, token có thể tham chiếu tới object/path trong kho đó, nhưng phải cân nhắc path traversal, quyền truy xuất và khả năng file bị overwrite/xóa. **Local path của producer không tự tồn tại trong container consumer**.

**Đừng đánh dấu file processed ngay khi claim-in** nếu token chưa được publish và xử lý; nếu cần làm vậy, phải có outbox/reconciliation bảo đảm tiếp tục pipeline.

### 10.2. SFTP inbound/streaming adapter

SFTP thích hợp để nhận file lớn nhưng có hai thời điểm cần tách:

1. **Tải từ SFTP về staging/object store**: hoàn tất transfer, xác minh size/checksum hoặc marker theo producer contract.
2. **Công bố token để xử lý**: chỉ sau khi dữ liệu hoàn tất và có thể đọc ở nơi consumer dùng.

SFTP streaming adapter có thể cho phép đọc stream thay vì copy file local, nhưng phải quản lý **session/stream lifecycle**. Nếu chỉ lưu object InputStream hoặc file handle đang mở vào một MessageStore dựa trên serialization, lần redeem sau restart hoặc ở JVM khác có thể không sử dụng được. Hãy lưu **bytes/object bền vững**, metadata và chỉ truyền token.

### 10.3. HTTP inbound gateway và outbound gateway

Với HTTP:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant IG as HTTP Inbound Gateway
    participant S as Storage Service
    participant MQ as Work Broker
    participant W as Worker
    C->>IG: Upload content
    IG->>S: Store complete object + metadata
    S-->>IG: claimId
    IG->>MQ: Publish reference
    IG-->>C: 202 Accepted + jobId
    MQ->>W: Deliver reference
    W->>S: Authorized redeem
    S-->>W: Content
    W->>W: Validate + business commit
~~~

Khi upload lớn:

- Thiết lập giới hạn kích thước request, streaming/multipart và thời gian upload.
- Không giữ toàn bộ binary trong heap chỉ vì HTTP converter tạo byte[].
- Nếu HTTP client retry upload sau timeout, dùng idempotency key hoặc trạng thái job để tránh lưu nhiều bản và phát nhiều work.
- **HTTP 202 Accepted** phải nói rõ điều gì đã được lưu bền vững. Chỉ tạo token trong RAM rồi trả 202 là không đủ nếu cần khả năng khôi phục.
- Nếu HTTP outbound gateway dùng token để gọi hệ khác, cần phân biệt hệ đó muốn **URL lấy payload** hay cần binary nguyên bản. Một dịch vụ không hỗ trợ Claim Check sẽ không hiểu claimId.

### 10.4. JMS Queue

JMS phù hợp để phân phối **work token** thay vì các message binary rất lớn:

~~~text
ClaimCheckIn + shared store
   → JMS outbound adapter (payload = claim token)
   → durable queue theo cấu hình
   → JMS message-driven inbound adapter
   → ClaimCheckOut/redeem
   → idempotent handler
   → broker acknowledgment theo container/transaction
~~~

Những điểm phải thiết kế:

- Token được broker giữ/re-deliver theo hợp đồng JMS, **không tự bảo vệ dữ liệu trong claim store**.
- JMS listener timeout hoặc crash có thể làm một token được giao lại.
- Không xóa dữ liệu ngay khi listener nhận token nếu handler còn cần retry.
- Message store và JMS broker là **hai tài nguyên khác nhau**; không có atomic transaction mặc định.
- Nếu durable message còn nhưng claim TTL đã hết, broker redelivery sẽ dẫn tới **missing claim**.

### 10.5. AMQP/RabbitMQ Queue

RabbitMQ có giới hạn và chi phí khi vận chuyển message lớn; dùng claim reference có thể làm broker nhẹ hơn. Tuy nhiên:

- **Prefetch** có thể giữ nhiều token unacked trên một worker; nếu mỗi claim tải file vài trăm MB, tổng I/O/storage concurrency có thể rất lớn dù broker message nhỏ.
- Ack/nack/requeue phải liên kết **đúng thời điểm business commit** hoặc durable handoff được thiết kế.
- Dead-letter queue chứa **token**, không nhất thiết chứa original payload. Không thể replay DLQ nếu claim bị xóa trước khi triage.
- Với fan-out qua nhiều queue, mỗi subscription có thể cần redeem cùng payload. Cleanup phải đợi đủ các nghĩa vụ hoặc dùng **claim/reference riêng**.

### 10.6. Kafka topic

Kafka là log phân partition. Thay vì đặt binary lớn trong record, có thể publish **claim envelope** nhỏ tới topic:

~~~json
{
  "eventId": "EVT-LAB-0119",
  "eventType": "DocumentReady",
  "claimId": "clm-lab-7e8d03ac",
  "tenantId": "TENANT-LAB-01",
  "documentVersion": 2
}
~~~

**Điểm đặc biệt với Kafka:** record có thể được đọc lại từ offset cũ, có thể tồn tại lâu theo retention và được nhiều **consumer groups** xử lý ở các thời điểm khác nhau. Claim bị xóa khi group A hoàn tất có thể khiến group B hoặc một lần replay historical không còn dữ liệu.

Phải xác định:

1. **Bao nhiêu consumer groups** cần payload, trong thời gian bao lâu?
2. Retention của claim có tương thích thời gian broker/topic retention và yêu cầu replay không?
3. Có giữ original lâu hơn hoặc snapshot/rebuild lại từ nguồn được không?
4. Khi offset được commit, đã đạt business commit chưa?
5. Consumer lag dài có làm claim hết hạn trước khi được nhận?
6. Nếu consumer group mới đăng ký từ offset cũ, quyền lấy lại những claim cũ được xử lý thế nào?

**Kafka consumer client poll** bên dưới listener không biến Claim Check thành PollingConsumer của QueueChannel; một Kafka message-driven inbound adapter vẫn xử lý record từ container.

### 10.7. JDBC/database

Database có thể tham gia **hai vai trò riêng**:

- **Claim storage:** JdbcMessageStore hoặc claim metadata table giữ dữ liệu/reference.
- **Business storage/outbox:** bảng nghiệp vụ và hàng outbox/processed inbox bảo đảm kết quả và ý định phát token.

Không nên dùng một bảng duy nhất với cột status mơ hồ cho tất cả trạng thái. Nếu DB là nơi giữ object lớn, cần thiết kế BLOB/schema/backup và giới hạn dung lượng. Nếu DB chỉ giữ object key, cần bảo đảm **tính nhất quán giữa object store và metadata DB**.

### 10.8. Bảng chọn tích hợp

| Nguồn/vận chuyển | Claim lưu đâu? | Điều cần chống |
| --- | --- | --- |
| File → JMS | Shared object/DB store | File chưa hoàn tất, token publish lỗi |
| SFTP → AMQP | Durable shared store | Session lỗi, duplicate download, DLQ mất payload |
| HTTP → Kafka | Object store + metadata | Client retry, consumer lag, multi-group replay |
| JDBC outbox → broker | Shared claim store/outbox | Crash giữa persist và publish, duplicate token |
| QueueChannel trong JVM | Có thể SimpleMessageStore cho lab | Restart mất token gốc, memory pressure |
| HTTP gateway → remote processor | Object store hoặc truyền payload thực khi cần | Unauthorized redeem, timeout/unknown side effect |

## 11. Atomicity: lưu payload và publish token không cùng một thao tác

Đây là bài toán độ tin cậy quan trọng nhất của Claim Check. Cất payload vào một DB/object store và publish token tới JMS/AMQP/Kafka **thường là hai hệ độc lập**.

### 11.1. Bốn cửa sổ lỗi

| Cửa sổ | Điều xảy ra | Hậu quả nếu không có recovery |
| --- | --- | --- |
| **A: store OK → publish chưa thực hiện** | Process chết sau khi lưu claim | Claim mồ côi, work không được xử lý |
| **B: publish OK → ACK producer mất** | Không rõ token đã tới broker chưa | Publish lại có thể tạo token delivery trùng |
| **C: token tới consumer → store không truy xuất được** | DB/network/auth lỗi hoặc data chưa AVAILABLE | Work không tiến triển, retry hoặc DLQ |
| **D: business commit OK → cleanup chưa chạy** | Consumer chết trước mark/dọn claim | Dữ liệu tồn dư trong store, tốn chi phí |

Không được giải quyết cửa sổ A bằng cách **xóa claim ngay khi publish lỗi** nếu còn một khả năng broker đã thực sự nhận token. Cần trạng thái/correlation để reconcile và thiết kế retry idempotent.

### 11.2. Claim + Outbox ở cùng DB

Nếu original message, claim metadata và outbox record được lưu bằng **một DB transaction có thể tham gia cùng TransactionManager**, có thể:

~~~text
BEGIN TRANSACTION
    insert stored payload / claim metadata
    insert outbox event {claimId, messageType, tenant}
COMMIT

Outbox relay:
    read pending event
    publish claim token to broker
    mark outbox sent (with retry)
~~~

Nếu relay publish thành công nhưng chết trước mark sent, nó có thể publish **lại cùng claimId/eventId**. Consumer phải idempotent. Nếu object store ngoài DB, transaction DB trên không tự atomic với object upload; thêm trạng thái PREPARED/AVAILABLE và garbage collection.

### 11.3. Không dùng try/catch làm distributed transaction

~~~text
try:
    store.save(payload)
    broker.publish(token)
catch:
    store.delete(payload)
~~~

Đây là **thiết kế thiếu an toàn** nếu broker đã nhận token nhưng response thất lạc. Việc xóa khiến token được giao tới consumer nhưng không redeem được. Cần **outbox, idempotent publish, retry và reconciliation**, không dựa vào thứ tự gọi API trong một try/catch.

### 11.4. Khi nào một transaction manager có thể hỗ trợ?

Tùy JDBC, JMS và cấu hình transaction, một số thành phần có thể tham gia giao dịch được phối hợp trong phạm vi cụ thể. Nhưng **không mặc định** có atomic transaction giữa SFTP, HTTP, object storage, Kafka và DB. Ngay cả khi dùng transaction advice trên poller, cần kiểm tra source/target thực sự tham gia và recovery theo contract.

### 11.5. Trạng thái metadata gợi ý

~~~text
PREPARING
  → AVAILABLE
  → PUBLISHED
  → IN_USE
  → COMPLETED
  → ELIGIBLE_FOR_CLEANUP
  → DELETED

  Có thể phát sinh: PUBLISH_RETRY, RETRIEVE_RETRY,
                   QUARANTINED, ORPHAN_CANDIDATE
~~~

**Đây là application state machine**, không phải enum bắt buộc của Spring Integration. Việc trạng thái **COMPLETED** có nghĩa gì cần mô tả theo số consumer/subscriptions và business outcome, đặc biệt khi một claim phục vụ nhiều nhóm.

## 12. Retry, duplicate token và business idempotency

### 12.1. Hai kiểu duplicate khác nhau

- **Duplicate token delivery:** cùng claimId xuất hiện nhiều lần trên broker hoặc được replay.
- **Duplicate business command:** hai claimIds khác nhau lại chứa một thao tác nghiệp vụ giống nhau.

Nếu chỉ dedupe theo claimId, kiểu thứ hai vẫn tạo side effect trùng. Cần business key phù hợp và, khi cần, kiểm tra hash/version payload.

### 12.2. Consumer an toàn khi nhận token

~~~text
consume(token):
    validateSourceAndTenant(token)
    metadata = loadClaimMetadata(token.claimId)
    authorizeConsumerForClaim(metadata)
    require(metadata.status == AVAILABLE or permitted equivalent)

    payload = fetchClaimContent(metadata)
    verifySizeChecksumSchema(payload, metadata)

    with businessTransaction:
        if processedInbox.exists(consumerName, businessKey):
            return ALREADY_COMPLETED
        processIdempotently(payload)
        processedInbox.insert(consumerName, businessKey, resultRef)
        commit

    acknowledgeTransportAccordingToContract()
    recordClaimConsumerCompletion(token.claimId, consumerName)
    cleanupLaterWhenSafe()
~~~

Giả mã **không** thay thế locking/unique constraint, transaction isolation, exception mapping hay khả năng trả ack của adapter. **Không** thiết kế delete claim trong finally để tránh xóa khi handler lỗi.

### 12.3. Retry policy theo loại lỗi

| Lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| **Store tạm offline** | JDBC timeout/HTTP 503 từ claim service | Retry/backoff, không ack thành công giả |
| **Claim chưa AVAILABLE** | Upload object chưa commit | Chờ/retry bounded, điều tra publish-before-ready |
| **Claim không tồn tại** | Token sai, xóa sớm, TTL hết | Phân loại mất dữ liệu, quarantine/escalate |
| **Sai tenant/không đủ quyền** | Consumer truy xuất claim khác phạm vi | Từ chối và audit, không tự retry để vượt kiểm soát |
| **Checksum mismatch** | Object bị đổi/corrupt | Quarantine, không xử lý nội dung chưa tin cậy |
| **Schema invalid** | CSV/JSON không hợp contract | DLQ/quarantine, không retry vô hạn |
| **Business transient** | DB target mất kết nối | Retry/idempotency, giữ claim |
| **Business permanent** | Lệnh không hợp lệ theo quy tắc | Outcome rõ, retention theo chính sách |
| **Cleanup lỗi** | Object delete API timeout | Retry cleanup độc lập, không sửa trạng thái business thành FAILED |

### 12.4. DLQ chứa token không chứa nội dung gốc

Nếu một poison message được chuyển DLQ ở ngày thứ hai, nhưng claim hết hạn/xóa ở ngày thứ nhất, người vận hành sẽ không thể xem hoặc replay dữ liệu. Vì vậy **retention của claim** phải tính cả **queue backlog, retry window, DLQ dwell time và thời gian điều tra sự cố**.

Với dữ liệu nhạy cảm cần xóa sớm, không thể chỉ kéo dài TTL vô hạn cho tiện debug; phải cân bằng retention policy, cơ chế replay khác hoặc lưu bằng chứng/metadata được phép mà không giữ toàn bộ nội dung.

### 12.5. Khi một token được fan-out

~~~mermaid
flowchart TD
    CLAIM["Claim ID C1"] --> TOPIC["Kafka topic / AMQP exchange"]
    TOPIC --> BILL["Billing group/queue"]
    TOPIC --> ANALYTICS["Analytics group/queue"]
    TOPIC --> SEARCH["Search index group/queue"]
    BILL --> STORE[("Shared Claim Store")]
    ANALYTICS --> STORE
    SEARCH --> STORE
~~~

**Sai:** Billing redeem rồi xóa claim ngay; Analytics mới nhận token sau đó và không có nội dung.

**Đúng:** dùng policy theo số subscribers bắt buộc, consumer-specific completion markers, TTL/safety window hoặc **claims riêng** nếu mỗi nhánh phải sở hữu vòng đời riêng. Với Kafka, nhóm consumer mới/replay cũ là trường hợp đặc biệt: cần tuyên bố rõ **giới hạn historical replay** của claim.

## 13. Concurrency và Claim Check trong Competing Consumers

Claim Check thường kết hợp với Competing Consumers để phân phối work nhẹ qua broker, trong khi dữ liệu lớn nằm ở store. Nhưng số worker tăng sẽ tăng **đồng thời truy cập claim store**.

### 13.1. Một token được giao lại cho hai worker?

Trong queue thông thường, một message thường có một consumer xử lý trong một lần giao, nhưng khi ack lỗi, session hết hạn hoặc worker crash, một token có thể được giao lại cho worker khác. Nếu consumer A vẫn đang xử lý chậm khi B nhận lại, **cả hai có thể cùng truy xuất claim**.

Nếu dùng **destructive get/delete** ngay lần redeem đầu, B có thể không đọc được. Nếu giữ claim, cả hai có thể đọc; khi đó **business idempotency/concurrency** phải bảo vệ side effect. Không dùng delete-on-read như cơ chế lock nghiệp vụ khi không có hợp đồng atomic phù hợp.

### 13.2. Một số chiến lược

| Chiến lược | Phù hợp | Giới hạn |
| --- | --- | --- |
| **Read-only shared claim** | Payload immutable, nhiều readers/retry | Cần TTL/cleanup và business idempotency |
| **One-time redeem** | Work một lần và không cần retry/fan-out | Dễ mất khả năng retry nếu xóa quá sớm |
| **Claim lease** | Muốn theo dõi worker đang sở hữu work | Lease expiry có thể tạo đồng thời; cần fencing |
| **Per-subscriber completion** | Fan-out nhiều nghiệp vụ | Phải biết subscription nào bắt buộc và retention |
| **Separate claims** | Mỗi consumer có lifecycle độc lập | Thêm storage overhead và quản lý reference |

### 13.3. QueueChannel trong JVM

Nếu một **QueueChannel** mang claim ID và nhiều **PollingConsumer** rút từ cùng channel, việc lấy message khỏi queue **không đồng nghĩa** đã xử lý dữ liệu trong store. Bản thân QueueChannel dùng memory không tự cung cấp durable ack/retry. Đối với công việc quan trọng, cần broker/message store bền vững hoặc cơ chế recovery/claim có thiết kế rõ.

### 13.4. Kafka partition ordering không bảo vệ vòng đời claim

Kafka giữ thứ tự record trong một partition theo contract, nhưng hai claim references có thể trỏ tới **cùng object version hoặc hai versions**. Handler vẫn cần kiểm tra **business version**; không nên ghi đè trạng thái mới bằng dữ liệu cũ chỉ vì một claim được retrieve muộn.

## 14. Bảo mật Claim Check: token không phải giấy phép đọc dữ liệu

Một thiết kế Claim Check có thể làm broker **không cần mang payload nhạy cảm**, nhưng lại tạo ra **một API tra dữ liệu từ claimId**. Nếu API này cho phép bất kỳ caller nào có ID truy xuất nội dung, nó có thể trở thành lỗ hổng BOLA/IDOR (Broken Object Level Authorization).

### 14.1. Những tài sản cần bảo vệ

| Tài sản | Nguy cơ | Kiểm soát |
| --- | --- | --- |
| Claim token | Bị đọc từ log hoặc broker message | ID khó đoán, redaction, giới hạn quyền topic/queue |
| Claim metadata | Bị sửa tenant/owner/expiry/object key | Quyền ghi chặt, audit, immutable fields |
| Payload trong store | Đọc trộm hoặc thay byte | Authentication, authorization, encryption, checksum |
| Service credential | Bị lạm dụng tải toàn bộ object | Least privilege, rotation, không để trong message |
| Object URL | Bị forward hoặc dùng lại ngoài dự kiến | TTL/scope, signed URL policy khi cần |
| File path | Path traversal hoặc đọc file khác | Path canonicalization/allowlist, không tin path từ token |
| Header của original Message | Mang reply channel, identity hoặc secret | Header filtering, serialization policy |
| Audit/debug logs | Chứa raw payload hoặc claim key nhạy cảm | Redaction và retention phù hợp |

### 14.2. Quy trình redeem an toàn

~~~text
receive(token):
  authenticateConsumerService()
  validateTokenShapeAndVersion(token)
  metadata = trustedClaimRegistry.lookup(token.claimId)
  require(metadata.tenantId == authorizedTenantContext)
  authorize(consumerIdentity, metadata.allowedOperations)
  require(claimNotExpiredOrExplicitlyRetained(metadata))
  require(metadata.status in allowedStates)
  streamObjectFromTrustedKey(metadata.objectKey)
  verifyPayloadIntegrityAndSchema()
  logSafeAuditEvent()
~~~

**Không lấy tenant hoặc allowedOperations duy nhất từ JSON token chưa xác thực.** Các trường có trong token phục vụ routing/observability; quyền truy cập phải được quyết định dựa trên identity và metadata từ nguồn đáng tin.

### 14.3. Opaque ID vẫn có rủi ro

UUID ngẫu nhiên khó đoán hơn ID tăng dần, nhưng vẫn có thể bị lộ trong:

- Broker topic mà nhiều ứng dụng có quyền subscribe.
- HTTP access log, exception trace hoặc message headers.
- DLQ dashboard, log tập trung, ticket hỗ trợ.
- Email/chat chứa đường dẫn debug.
- Application metrics nếu dùng claimId làm label.

Do vậy, **khó đoán không thay kiểm tra quyền**. Khi claim rất nhạy cảm, chỉ trả một reference tối thiểu; không cho phép trực tiếp đọc object bằng claimId không qua authorization.

### 14.4. Mã hóa và vòng đời key

- **Encryption in transit:** TLS khi gọi object store, DB, HTTP API hoặc broker nếu transport yêu cầu.
- **Encryption at rest:** theo phân loại dữ liệu; lưu ý backup và snapshot cũng phải bảo vệ.
- **Key rotation:** thiết kế version/key ID để vẫn đọc được dữ liệu còn retention hợp lệ trong giai đoạn chuyển đổi.
- **Data deletion:** khi có yêu cầu xóa, cần tính cả object, metadata, cache, backup, bản sao cho fan-out và DLQ theo chính sách.
- **Secret management:** không nhúng mật khẩu SFTP, DB password hoặc cloud secret vào ClaimReference.

### 14.5. File và parser không đáng tin

File đến từ SFTP/HTTP có thể chứa nội dung lớn, sai định dạng, bị nén cực mạnh hoặc payload độc hại. Claim Check không làm dữ liệu trở nên an toàn. Cần kiểm soát:

1. Content length và max expanded size khi giải nén.
2. Content type thực tế, file extension và schema.
3. Parser time/memory limits.
4. Antivirus/malware scanning nếu threat model yêu cầu.
5. Quarantine khi dữ liệu chưa đạt điều kiện an toàn.
6. Quyền filesystem/temp-file và dọn staging.

### 14.6. Kiểm toán mà không lộ nội dung

Audit nên ghi **claimId dạng hạn chế, consumer identity, tenant được kiểm chứng, hành động STORE/REDEEM/DELETE, timestamp, outcome, correlation/trace ID**. Với claim ID có thể cấp quyền trực tiếp, cân nhắc băm/redact ID trong log thông thường và giữ lookup an toàn ở kho audit chuyên dụng.

## 15. TTL, retention và garbage collection

Một claim được tạo thành công nhưng không bao giờ xóa sẽ thành **dữ liệu tồn dư**. Một claim bị xóa quá sớm khiến downstream không thể retry. Vì vậy phải thiết kế vòng đời ngay từ đầu.

### 15.1. Công thức tư duy cho thời hạn lưu

~~~text
requiredRetention >=
  expectedQueueWait
  + maximumProcessingAndRetryWindow
  + incidentReviewOrDLQReplayWindow
  + safetyMargin
~~~

Đây là **quan hệ thiết kế**, không phải công thức SLA chuẩn. Khi có nhiều consumer groups hoặc lịch sử Kafka cần replay nhiều tháng, retention phải dựa trên **nhóm phụ thuộc lâu nhất** hoặc cơ chế tái dựng dữ liệu gốc. Đồng thời không được vượt giới hạn pháp lý/chính sách xóa dữ liệu.

### 15.2. Bốn câu hỏi trước khi xóa

1. Đã có **business completion** được xác minh chưa?
2. Có **pending token, retry, unacked message hoặc DLQ entry** còn cần claim không?
3. Có **subscriber/group khác** cần redeem nội dung không?
4. Có **retention/audit/legal hold** yêu cầu giữ hay xóa trong thời hạn riêng không?

Không áp dụng “claim đã được GET một lần → delete ngay” làm chính sách chung, vì retrieval và successful processing là hai mốc khác nhau.

### 15.3. Bộ trạng thái cleanup tham khảo

| Trạng thái | Điều kiện | Hành động |
| --- | --- | --- |
| **AVAILABLE** | Payload đã lưu đầy đủ | Consumer hợp lệ có thể redeem |
| **PUBLISH_PENDING** | Dữ liệu đã sẵn nhưng chưa chứng minh token publish | Retry/outbox, không xóa sớm |
| **IN_USE** | Một hoặc nhiều consumer đang xử lý | Theo dõi lease/attempt; không xóa mù |
| **COMPLETED** | Nghĩa vụ nghiệp vụ hoàn tất theo contract | Đánh giá retention và các nhóm liên quan |
| **CLEANUP_ELIGIBLE** | Hết phụ thuộc, không có hold và tới mốc hợp lệ | Giao job xóa |
| **DELETING** | Đang xóa object/metadata | Retry idempotent khi lỗi |
| **DELETED** | Đã xác nhận xóa theo phạm vi đã định | Audit deletion marker có dữ liệu tối thiểu |
| **ORPHAN_CANDIDATE** | Có dữ liệu nhưng không có đường work hợp lệ sau ngưỡng | Reconcile trước khi xóa |

Một MessageStore cơ bản **không bắt buộc cung cấp các trạng thái này**; chúng là gợi ý cho application metadata/claim service để vận hành các flow phức tạp.

### 15.4. Garbage collector không được đoán

GC chạy theo lịch có thể tìm:

- Claim đã COMMITTED/ACKED và quá retention.
- Claim **PREPARED/PUBLISH_PENDING** quá lâu, cần đối soát với outbox/broker.
- Claim không còn metadata hoặc object không còn claim record.
- Token còn trong DLQ nhưng object sắp hết hạn.
- Object phiên bản cũ không còn bất kỳ consumer cần sử dụng.

Một job GC phải:

- Chỉ xóa khi điều kiện xác nhận được **từ nguồn tin cậy**.
- Có giới hạn batch, rate limit và retry.
- Ghi audit số item đã kiểm tra/đã xóa/chưa xóa và lý do.
- Có dry-run/report mode trong giai đoạn triển khai ban đầu.
- Không làm giảm khả năng replay đã cam kết với consumer.

### 15.5. Object delete và metadata delete không atomic

Nếu object storage xóa thành công nhưng DB metadata chưa cập nhật, một lần retry xóa cần coi object không tồn tại là **đã đạt điều kiện**, nếu phù hợp contract. Nếu DB metadata xóa trước nhưng object còn, có thể tạo **object mồ côi** không còn đường audit/cleanup. Chọn thứ tự, trạng thái DELETING và reconciliation để tránh mất dấu.

### 15.6. GDPR/retention không phải chỉ đổi TTL

Chính sách riêng tư có thể yêu cầu xóa theo dữ liệu/nhân sự/tenant hoặc retention một khoảng thời gian nhất định. Claim Check có thể tạo thêm bản sao payload, cache, log, backup và DLQ. Hãy lập **data inventory** cho tất cả nơi lưu, không chỉ bản ghi trong MessageStore.

## 16. Chi phí hiệu năng, streaming và backpressure

Claim Check thường tiết kiệm lưu lượng broker nhưng thêm **một lần ghi và một lần đọc** dữ liệu, có thể nhiều hơn nếu retry/fan-out.

### 16.1. Ước lượng đơn giản

Giả sử mỗi file dung lượng **80 MiB**, có **100 file/giờ**:

~~~text
Input bytes ≈ 80 MiB × 100 = 8,000 MiB / giờ

Không Claim Check, một hoặc nhiều hop transport có thể phải
mang phần lớn payload trên đường tích hợp.

Có Claim Check, broker chủ yếu mang token nhỏ; object store phải
ghi khoảng 8,000 MiB/giờ và đọc ít nhất khoảng đó nếu mỗi file
được tiêu thụ đúng một lần.
~~~

Nếu ba consumer groups đều redeem toàn bộ nội dung, **tổng read throughput** có thể xấp xỉ ba lần lượng dữ liệu đầu vào, chưa tính retries. Vì vậy Claim Check không làm tổng bytes I/O biến mất; nó **chuyển nơi phát sinh tải**.

### 16.2. Những điểm nghẽn thường gặp

| Thành phần | Dấu hiệu | Biện pháp |
| --- | --- | --- |
| Claim-in storage | Upload latency cao, connection pool đầy | Streaming, bounded concurrency, storage tuning |
| Broker | Message lớn/throughput kém | Token nhỏ, giới hạn headers |
| Claim-out store | Nhiều readers, 429/503, DB locks | Read concurrency limit, cache có kiểm soát |
| Consumer heap | Byte array lớn, OOM | Stream/chunk file, giảm concurrency |
| Disk staging | Temp files không dọn, disk full | Cleanup, quota, monitoring |
| Metadata DB | Claim lookup/cleanup chậm | Index, batch GC, tránh hot row |
| Security scanning | CPU/time tăng khi file lớn | Bounded pipeline, scheduling và timeout |

### 16.3. Streaming có thực sự giải quyết memory?

Streaming giúp không phải giữ toàn bộ object trong một byte[] duy nhất, nhưng:

- Stream phải được đóng đúng cách khi thành công hoặc lỗi.
- Retry có thể cần **mở một stream mới** từ object store; không thể reuse một InputStream đã đọc hết.
- Data validation/checksum có thể cần xử lý từng chunk.
- Multipart upload/download có giới hạn chunk và cơ chế resume riêng.
- Consumer có thể phải hỗ trợ streaming hoặc ghi staging bền vững.

Không truyền InputStream object qua JMS/Kafka rồi tưởng phía kia có thể đọc được. Transport cần mang **reference**, còn stream được mở ở nơi consumer truy xuất.

### 16.4. Bounded concurrency

Nếu mỗi consumer có thể mở một file 80 MiB và xử lý 20 file song song, áp lực I/O, heap, disk, parser và store connection có thể rất lớn. Điều tiết cả hai tầng:

1. **Số work tokens được dispatch** (broker prefetch, listener concurrency, QueueChannel capacity).
2. **Số payload lớn đang được redeem/process** (semaphore/bulkhead riêng).

Mức concurrency tối ưu phụ thuộc kích thước file, throughput store, CPU parse và sink. Không tự tăng 100 workers chỉ vì token broker rất nhỏ.

### 16.5. Cache claim content?

Cache có thể giảm repeated reads nhưng tạo thêm dữ liệu nhạy cảm và nguy cơ stale:

- Cache key cần claim ID **kèm version/tenant** theo contract.
- Không cache nội dung nhạy cảm vô hạn trong RAM.
- Có TTL phù hợp và chính sách xóa/eviction.
- Không để consumer đọc dữ liệu cũ khi cùng object key bị ghi đè.
- Mọi cache phải được tính trong data retention/privacy scope.

## 17. Startup, shutdown và lifecycle của claim store

### 17.1. Startup

- [ ] MessageStore hoặc object store dùng chung sẵn sàng trước khi nhận work cần redeem.
- [ ] Producer/consumer dùng cùng contract claim ID, schema, serializer và object version.
- [ ] Phân quyền read/write/delete được tách theo service role.
- [ ] Metadata/claim registry có migration/index đúng phiên bản.
- [ ] Có health check **store lookup/write/read** phù hợp, không chỉ ping TCP.
- [ ] Nếu token vẫn có trong broker sau restart, store phải giữ được claim tương ứng.
- [ ] TTL/cleanup job được cấu hình nhưng không xóa pending work ngoài ý muốn.
- [ ] Không cho dev/test kết nối cùng store/queue production một cách vô ý.

### 17.2. Graceful shutdown

~~~text
Ngừng nhận token mới
    ↓
Cho consumer đang redeem/process hoàn tất trong giới hạn
    ↓
Commit hoặc rollback/để broker redeliver theo contract
    ↓
Đóng input stream, temp file và connection
    ↓
Để claim còn nguyên nếu công việc chưa thực sự hoàn tất
    ↓
Đóng service/container
~~~

Nếu process bị kill giữa business commit và broker ack, token có thể redeliver. Business idempotency ngăn tác động trùng; claim data phải còn đủ lâu cho retry. Nếu **cleanup chạy độc lập**, nó cần nhìn thấy trạng thái in-flight/retry thay vì chỉ dựa trên lần GET gần nhất.

### 17.3. Rolling deploy và thay đổi schema

Trong rolling deployment có thể có producer mới, consumer cũ hoặc ngược lại. Claim metadata, object serialization và payload schema phải có **version/capability strategy** để cả hai bên tương thích trong cửa sổ triển khai. Đặc biệt, serialize nguyên Java object qua JdbcMessageStore có thể gặp vấn đề khi đổi class/package/serialVersionUID; cân nhắc lưu payload có schema ổn định hoặc có migration.

### 17.4. Store/region failover

Khi primary store mất kết nối:

- Consumer không được coi **missing due to outage** là dữ liệu không tồn tại thật.
- Retry có backoff, circuit breaker và alert.
- Không ack token thành công nếu chưa đạt điều kiện nghiệp vụ.
- Nếu chuyển sang replica, kiểm tra consistency/replication lag và object version.
- Không tạo claim ID mới không liên quan nếu cần retry cùng công việc.

### 17.5. Không chỉ cần tính sẵn sàng của broker

Broker có thể chạy hoàn hảo, token được giao ngay, nhưng claim store không truy xuất được. Vì vậy health dashboard phải đánh giá **end-to-end** từ token tới payload và business commit, không chỉ queue depth hoặc consumer connected.

## 18. Observability: đo cả token và nội dung

Một dashboard chỉ có **broker messages published/consumed** sẽ bỏ sót nhiều loại lỗi Claim Check. Cần tách các chỉ số của **transport**, **claim store** và **business processing**.

### 18.1. Metrics cần quan sát

| Metric | Ý nghĩa | Dấu hiệu bất thường |
| --- | --- | --- |
| **claims stored** | Số object/message được cất thành công | Store nhận nhiều nhưng broker không publish |
| **claim bytes stored** | Tổng dung lượng ghi vào store | Tăng nhanh, quota/backup nguy cơ quá tải |
| **claim publish pending** | Claim sẵn sàng nhưng token chưa phát xác nhận | Outbox/relay bị kẹt, orphan candidates |
| **tokens published** | Số token được broker nhận theo contract | Chênh nhiều với claims stored |
| **tokens delivered** | Số token consumer nhận | Có thể tăng khi redelivery |
| **claim redeem success** | Số lần lấy được nội dung hợp lệ | Chỉ chứng minh retrieve, chưa phải business commit |
| **claim redeem denied** | Bị chặn bởi authn/authz | Có thể có sai service role hoặc abuse |
| **claim missing/expired** | Không tìm thấy hoặc token hết hạn | Xóa sớm, wrong store, TTL sai |
| **checksum mismatch** | Dữ liệu trả ra khác metadata | Corruption, overwrite hoặc tấn công |
| **business commit success** | Số tác vụ nghiệp vụ hoàn tất | Không tăng dù token nhận nhiều |
| **duplicate business suppressed** | Dedupe ngăn side effect lặp | Tăng sau restart/rebalance |
| **oldest unprocessed token age** | Độ trễ công việc còn pending | Vượt yêu cầu nghiệp vụ |
| **DLQ pending/age** | Token cần người xử lý | Token sắp hết hạn khi chưa triage |
| **orphan claim count/bytes** | Dữ liệu không có nghĩa vụ publish/replay hợp lệ | Cleanup không chạy hoặc mất outbox |
| **cleanup eligible/deleted** | Dữ liệu đã đủ điều kiện và được xóa | Eligible tăng nhưng delete không tiến triển |
| **store latency P50/P95/P99** | Độ trễ ghi/đọc object/DB | Store bottleneck/overload |
| **active redeem streams** | Số tải/stream đồng thời | I/O và memory pressure |

Các chỉ số nên phân nhóm theo **flow, source, target, type, environment** và lỗi; tránh gắn từng claimId hoặc businessKey vào metric label vì cardinality cao và nguy cơ lộ dữ liệu.

### 18.2. Trace qua hai hệ

~~~text
traceId=TRACE-LAB-47
  span A: sftp.receive         → 2.1 s
  span B: claim.store          → 1.7 s
  span C: broker.publish       → 0.08 s
  span D: broker.wait          → 0.9 s
  span E: claim.redeem         → 1.4 s
  span F: business.validate    → 0.12 s
  span G: database.commit      → 0.25 s
  span H: claim.cleanup        → async later
~~~

Đây là trace giả lập. Correlation qua broker cần truyền **trace context** được kiểm soát, không phải serialize nguyên thread-local. Thời gian broker.wait có thể được đo từ timestamp có nguồn đáng tin; đồng hồ giữa host khác nhau có sai lệch, nên xác định cách đo.

### 18.3. Audit event minh họa

~~~json
{
  "claimIdRef": "claim-hash-lab-7a0e",
  "action": "REDEEM",
  "consumerService": "invoice-worker",
  "tenantId": "TENANT-LAB-01",
  "source": "partner-sftp-lab",
  "objectVersion": 2,
  "sizeBytes": 83886080,
  "outcome": "SUCCESS",
  "traceId": "TRACE-LAB-47",
  "occurredAt": "2026-11-23T14:05:00+07:00"
}
~~~

**Đây không phải log do framework tự phát.** Nếu claim ID hoặc object key được xem là bí mật, chỉ lưu mã tham chiếu an toàn trong log phổ thông; audit store riêng có quyền xem phù hợp. Không ghi raw token/service credential hoặc payload nhạy cảm.

### 18.4. Sự cố “tokens consumed OK nhưng business zero”

Quy trình kiểm tra:

1. So **tokens delivered** với **claim redeem success**.
2. Nếu redeem lỗi, tìm missing/expired/denied/store unavailable.
3. Nếu redeem thành công, so **business commit success** với parse errors/DB failures.
4. Nếu business commit thành công mà broker cứ redeliver, kiểm tra ack/offset và idempotency.
5. Nếu business hoàn tất nhưng claim bytes không giảm, kiểm tra cleanup eligibility/GC.

### 18.5. Ba cảnh báo hữu ích

- **Missing claim after publish:** số token đã nhận nhưng retrieve trả NOT_FOUND/EXPIRED vượt ngưỡng.
- **Orphan storage growth:** claim bytes lưu tăng liên tục nhưng token publish hoặc cleanup không theo kịp.
- **No business progress:** nguồn còn token nhưng last business commit quá lâu, bất kể broker healthy.

## 19. Runbook sự cố Claim Check

### 19.1. Runbook A — Consumer nhận token nhưng không tìm thấy payload

1. Ghi lại claimId (theo chính sách bảo mật), source, consumer, tenant, publish time và target store.
2. Phân biệt **404 thật**, **store tạm lỗi**, **quyền bị từ chối**, **token hết hạn** và **metadata chưa AVAILABLE**.
3. Kiểm tra producer/consumer có dùng **cùng environment/region/store namespace** không.
4. Kiểm tra object tồn tại/version phù hợp và có bị GC xóa sớm không.
5. Nếu còn nguồn gốc, khôi phục object/claim theo quy trình được cho phép và giữ business key.
6. Không ack “thành công” khi chưa có payload; lưu exception/DLQ/retry với owner.
7. Sửa TTL/cleanup/publish ordering và bổ sung regression test.

### 19.2. Runbook B — Message store đầy dung lượng

1. Đo số claim/bytes theo source, độ tuổi, trạng thái, orphan candidates.
2. Tìm backlog broker, DLQ và consumer groups chưa hoàn tất.
3. Xác định job GC có lỗi, quyền delete sai, metadata drift hay policy retention quá rộng.
4. Tăng quota tạm thời nếu được phép để khôi phục tiến triển.
5. Chỉ xóa nhóm claim **đủ điều kiện và đã đối soát**; không chạy lệnh xóa hàng loạt theo tuổi mù quáng.
6. Tối ưu file size, streaming, compression phù hợp và TTL policy.

### 19.3. Runbook C — Token trùng sau broker restart

1. Tra workId/businessKey và audit token publish/ack trước restart.
2. Kiểm tra consumer idempotency; bản business đã commit chưa?
3. Nếu đã xử lý, đánh dấu duplicate theo contract và ack phù hợp; **không tạo side effect mới**.
4. Nếu chưa xử lý, redeem claim và xử lý lại.
5. Không xóa claim chỉ để loại duplicate nếu có consumer khác còn cần.

### 19.4. Runbook D — DLQ không replay được vì claim hết hạn

1. Xác minh claim thực sự đã bị xóa hay chỉ denied/store unavailable.
2. Đánh giá có nguồn dữ liệu nguyên bản hoặc backup hợp lệ để tái dựng không.
3. Nếu có, tạo claim mới với **liên kết business key/event ID** rõ để không tăng tác động nghiệp vụ.
4. Nếu không có, ghi sự cố mất dữ liệu theo mức nghiêm trọng và thông báo owner.
5. Cập nhật retention tính cả DLQ investigation/replay window.
6. Tránh giữ vô thời hạn mọi dữ liệu nhạy cảm như một giải pháp chống lỗi.

### 19.5. Runbook E — Fan-out: một nhóm đã xử lý, nhóm khác bị missing

Kiểm tra **per-subscriber completion**, thời điểm cleanup, số groups được công nhận và ownership của claim. Nếu claim bị xóa sau khi nhóm đầu tiên hoàn tất, phải sửa policy: giữ tới đủ nhóm bắt buộc, cấp claims độc lập hoặc bảo đảm có khả năng replay từ nguồn.

### 19.6. Runbook F — Payload sai checksum

Quarantine object/claim, ngừng business processing với byte chưa được tin cậy, kiểm tra object version/overwrites, metadata writes, serialization và ranh giới bảo mật. Không tự cập nhật checksum theo byte hiện tại để “cho test xanh” khi chưa xác minh nguồn đúng.

### 19.7. Runbook G — HTTP client timeout khi upload

Kiểm tra upload staging/object complete, metadata AVAILABLE, token published và job status. Nếu request mới mang cùng idempotency key, trả kết quả/trạng thái đã lưu thay vì tạo object hoặc phát token trùng vô điều kiện. Dọn staging mồ côi theo an toàn.

### 19.8. Runbook H — Rollback/redeploy gây lỗi deserialization

Xác định schema/class version của original Message, serializer, Java library versions và tính tương thích giữa producer/consumer. Có thể cần chạy consumer/transformer tương thích để migrate hoặc đọc dữ liệu cũ; đừng xóa claim hàng loạt hoặc ép deserialize không kiểm soát. Tương lai nên ưu tiên payload schema có version ổn định và định dạng liên thông khi đi qua nhiều JVM.

## 20. Hands-on project: Claim Check trong pipeline tài liệu

**Mục tiêu lab:** Từ một file giả có payload lớn, lưu bền vững vào claim store, phát token nhỏ tới consumer, phục hồi dữ liệu, ghi kết quả nghiệp vụ với idempotency và dọn claim **sau khi hoàn tất**. Bắt đầu bằng store trong memory để hiểu API rồi mở rộng sang shared store/broker test.

### 20.1. Hệ thống DemoDocs

Một tổ chức giả lập nhận báo cáo CSV của đối tác. Mỗi file có một **documentId** và version bất biến. Mục tiêu là kiểm tra schema và ghi các dòng hợp lệ vào database thử nghiệm. Một worker dùng dữ liệu để lập chỉ mục tìm kiếm, worker khác tạo báo cáo kiểm toán (fan-out tùy chọn).

Fixture:

~~~csv
document_id,document_version,order_id,amount
DOC-LAB-0041,2,ORDER-LAB-087,120000
DOC-LAB-0041,2,ORDER-LAB-088,175000
~~~

**Dữ liệu là giả định.** Khi thực hành, không sử dụng dữ liệu khách hàng thật, token thật, credential production hoặc bucket production.

### 20.2. Kiến trúc thực hành hai pha

~~~mermaid
flowchart TD
    FILE["Phase A: Local file / HTTP mock"] --> VALID["File readiness + validation"]
    VALID --> STORE["Claim In: store payload"]
    STORE --> BLOB[("Shared Store / Phase A memory")]
    STORE --> REF["Claim token envelope"]
    REF --> TRANSPORT["Phase A channel / Phase B broker"]
    TRANSPORT --> AUTH["Validate tenant + claim"]
    AUTH --> FETCH["Claim Out: retrieve"]
    BLOB --> FETCH
    FETCH --> PROCESS["Parse CSV + idempotent DB commit"]
    PROCESS --> ACK["Ack / status commit"]
    ACK --> GC["Cleanup after completion/retention"]
    GC --> BLOB
    FETCH -->|Invalid content| DLQ["Quarantine + owner"]
~~~

### 20.3. Giai đoạn A — Hiểu lưu và lấy bằng SimpleMessageStore

1. Tạo một **MessageStore** trong memory (xem Java ở phần 8).
2. Tạo Message với payload là một String/file metadata giả có businessKey.
3. Lưu Message và lấy **MessageHeaders.ID** làm claim token.
4. Đặt token vào một message riêng gửi qua DirectChannel hoặc QueueChannel test.
5. Consumer tra token, lấy original message, kiểm tra payload và headers.
6. Không xóa claim trước khi consumer báo business success.
7. Xóa claim sau khi kiểm chứng; thử lấy lại và ghi kỳ vọng NOT_FOUND.

**Giới hạn:** lab memory không chứng minh restart recovery, cross-instance hoặc broker durability.

### 20.4. Giai đoạn B — Dùng kho chia sẻ

1. Chọn **JdbcMessageStore** hoặc object store + metadata DB ở môi trường thử có quyền.
2. Định nghĩa serializer/schema, object size limits và retention.
3. Tạo claim ở producer process.
4. Mở một consumer process/JVM khác, truy cập **cùng store** và redeem thành công.
5. Tắt producer; consumer vẫn phải lấy claim nếu contract yêu cầu.
6. Ghi audit claimId ref, version, size, checksum và thời gian lưu/đọc.
7. Kiểm tra khi store down: consumer retry/backoff, không mất token sớm.

### 20.5. Giai đoạn C — Đưa token qua broker

1. Chọn **JMS hoặc RabbitMQ broker test**, cấu hình queue có durability phù hợp.
2. Claim-in nhận file; store original trước khi publish.
3. Publish token nhỏ qua outbound adapter, ghi correlation/workId.
4. Message-driven inbound adapter chuyển token cho consumer.
5. Consumer validate tenant/owner, claim-out và parse.
6. Handler ghi DB với business key **partner + documentId + version** và unique constraint.
7. Chỉ ack broker sau điều kiện commit theo listener contract; không xóa claim trước.
8. Dọn claim khi trạng thái các consumer bắt buộc và retention cho phép.

### 20.6. Giai đoạn D — Thử các cửa sổ lỗi

| Thử nghiệm | Cách mô phỏng | Kỳ vọng |
| --- | --- | --- |
| **D1** | Producer chết sau STORE trước PUBLISH | Có outbox/pending state để publish lại hoặc GC orphan an toàn |
| **D2** | Broker nhận token nhưng producer không nhận ACK | Publish trùng cùng token/eventId vẫn an toàn |
| **D3** | Store offline khi consumer retrieve | Retry/backoff, không ack success giả |
| **D4** | Business DB commit rồi consumer chết trước ack | Redelivery không tạo bản ghi trùng |
| **D5** | Consumer retrieve rồi handler parse lỗi | Claim còn cho retry/quarantine đúng policy |
| **D6** | Claim TTL hết hạn trước khi DLQ replay | Phát hiện gap, không báo đã khôi phục nếu payload mất |
| **D7** | Fan-out tới hai consumers, consumer A xong trước | Không xóa claim khi B còn cần |
| **D8** | Consumer gửi claim ID của tenant khác | Authorization DENY, không trả payload |
| **D9** | Object bị thay byte nhưng giữ metadata cũ | Checksum mismatch, quarantine |
| **D10** | 100 work đồng thời, store giới hạn connection | Backpressure, không OOM và có metrics |

### 20.7. Kiểm thử về kích thước thật sự của token

Tạo một message có payload giả 5 MiB và một claim token vài chục byte. Quan sát **payload bytes gửi qua broker**, không chỉ kích thước object Java in-memory. Header routing, serializer và protocol overhead làm message vận chuyển lớn hơn token thuần, nhưng vẫn phải **không mang 5 MiB binary** nếu mục đích Claim Check là tránh truyền binary qua broker.

### 20.8. Kiểm thử về thời gian hoàn tất

Ghi timestamp các mốc:

~~~text
claimStoredAt
tokenPublishedAt
tokenReceivedAt
claimRedeemedAt
businessCommittedAt
brokerAcknowledgedAt
claimCleanupEligibleAt
claimDeletedAt
~~~

Không được có **claimDeletedAt trước businessCommittedAt** trong mô hình retry cần dữ liệu. Nếu có nhiều consumer, điều kiện cleanup còn phải xét completion của từng nhóm bắt buộc.

### 20.9. Sản phẩm bàn giao của lab

| Sản phẩm | Bằng chứng tối thiểu |
| --- | --- |
| Sơ đồ pipeline | Nguồn, claim store, broker, consumer, business DB, GC |
| Message contract | Claim reference, version, tenant, business key |
| Claim store config | Loại store, retention, serializer, ACL, resource limits |
| Producer flow | File ready, store-before-publish, outbox/retry |
| Consumer flow | Authn/authz, retrieve, checksum, idempotent commit |
| Test run | Expected/Actual, logs/traces an toàn, failure injection |
| Cleanup plan | Điều kiện giữ/xóa theo retry/DLQ/fan-out, audit |
| Runbook | Missing claim, store offline, duplicate, expired, orphan |
| Known limits | Những thứ chưa được kiểm chứng với hạ tầng thật |

## 21. Ma trận kiểm thử Claim Check với Message Store

Các mã test dưới đây là **yêu cầu kỳ vọng**, không phải tuyên bố rằng test đã được chạy. Mỗi ca cần ghi **Input, Expected, Actual, Result, Evidence, Owner**; nếu chưa có bằng chứng thực nghiệm thì giữ **PENDING/UNKNOWN**.

### 21.1. Hợp đồng và storage

| ID | Tình huống | Điều kiện PASS |
| --- | --- | --- |
| **CL-01** | ClaimCheckIn nhận original Message | Có claim ID, store chứa original theo đúng key |
| **CL-02** | Message token gửi đi | Transport không mang original binary lớn ngoài ý định |
| **CL-03** | ClaimCheckOut nhận token hợp lệ | Khôi phục đúng payload và metadata được hỗ trợ |
| **CL-04** | Token ID không tồn tại | Trả lỗi missing có phân loại; không tự tạo payload rỗng |
| **CL-05** | Dùng SimpleMessageStore trong một JVM | Lưu/lấy hoạt động trong thời gian JVM còn sống |
| **CL-06** | Restart JVM với SimpleMessageStore | Ghi nhận giới hạn: claim trong memory mất |
| **CL-07** | Producer và consumer có SimpleMessageStore riêng | Consumer không tìm claim của producer; test xác nhận sai cấu hình |
| **CL-08** | Dùng shared durable store | Consumer JVM khác redeem thành công qua restart |
| **CL-09** | Payload không serialize được trong JdbcMessageStore | Lỗi rõ/loại trừ; không publish token hỏng |
| **CL-10** | Thay schema/class version rồi redeploy | Có xử lý compatibility/migration rõ |
| **CL-11** | Số byte gốc và byte phục hồi | Content hash/size đúng theo hợp đồng |
| **CL-12** | Thay object trong store nhưng không đổi version | Phát hiện mismatch/overwrite bất hợp lệ |

### 21.2. Giao nhận và xử lý sự cố

| ID | Tình huống | Điều kiện PASS |
| --- | --- | --- |
| **CL-13** | Producer crash sau store, trước publish | Outbox/reconciliation nhận diện claim chưa phát |
| **CL-14** | Broker publish thành công nhưng ACK producer mất | Retry không tạo side effect trùng |
| **CL-15** | Token publish trước khi object AVAILABLE | Consumer không xử lý incomplete object; lỗi được phát hiện |
| **CL-16** | Store unavailable tạm thời | Retry/backoff, không ack thành công giả |
| **CL-17** | Retrieve thành công nhưng parse/DB lỗi | Claim không bị xóa sớm; có retry/quarantine |
| **CL-18** | DB commit thành công, broker ack mất | Redelivery an toàn nhờ idempotency |
| **CL-19** | Token được gửi lại với message ID khác | Business key nhận diện duplicate đúng |
| **CL-20** | Hai claim IDs khác nhau cùng business command | Unique key bảo vệ tác động nghiệp vụ |
| **CL-21** | Cùng claimId nhưng metadata/payload conflict | Từ chối/điều tra, không đọc nội dung sai |
| **CL-22** | Poison payload/schema không hỗ trợ | DLQ/quarantine có owner, không retry vô hạn |
| **CL-23** | DLQ token được replay sau khi sửa code | Claim còn, dữ liệu được xử lý một lần theo nghiệp vụ |
| **CL-24** | Token expired trước DLQ replay | Không báo success giả; có quy trình mất/khôi phục dữ liệu |

### 21.3. Security, concurrency và lifecycle

| ID | Tình huống | Điều kiện PASS |
| --- | --- | --- |
| **CL-25** | Consumer tenant A redeem token tenant B | Authorization DENY, không lộ payload |
| **CL-26** | Token xuất hiện trong log | Log thông thường redact/hash claim key nhạy cảm |
| **CL-27** | Metadata bị client đổi allowedConsumer | Server dùng metadata đáng tin, không cấp quyền |
| **CL-28** | Signed URL hết hạn hoặc dùng ngoài scope | Từ chối truy xuất theo policy |
| **CL-29** | Content checksum bị sai | Dừng xử lý, quarantine, audit |
| **CL-30** | File nén vượt expanded-size limit | Parser bị chặn trước khi cạn tài nguyên |
| **CL-31** | JMS/AMQP queue redeliver token cho worker khác | Store còn dữ liệu; business idempotent |
| **CL-32** | Hai workers redeem cùng claim đồng thời | Không xóa sớm, không tạo business duplicate |
| **CL-33** | Kafka hai groups cần cùng claim | Group A hoàn tất không làm B mất payload |
| **CL-34** | Kafka replay offset cũ sau claim TTL | Hệ thống tuân thủ retention contract đã công bố |
| **CL-35** | Mover/Leaver của owner hoặc thu hồi quyền service | Không còn truy xuất trái phép, có xử lý claim còn pending |
| **CL-36** | Cleanup sau completion | Delete xảy ra sau điều kiện an toàn và có audit |
| **CL-37** | Cleanup thất bại tạm thời | Retry idempotent, không làm business status sai |
| **CL-38** | Object xóa rồi metadata chưa xóa | Job có thể retry và đối soát an toàn |
| **CL-39** | MessageStore đạt quota | Backpressure/alert, không phát token trỏ claim hỏng |
| **CL-40** | Shutdown/restart giữa xử lý | Khôi phục hoặc báo UNKNOWN đúng contract, không âm thầm mất work |
| **CL-41** | Có nhiều claims đã lưu mà không publish | Orphan metrics/GC phát hiện |
| **CL-42** | Consumer nhận token nhưng store ở sai region | Error/fallback/reconciliation, không đọc nhầm claim cùng ID |
| **CL-43** | Fan-out một nhánh lỗi kéo dài | Retention/ownership rõ, nhánh khác không bị xóa claim sớm |
| **CL-44** | Object key trỏ path ngoài vùng cho phép | Từ chối path traversal/unauthorized object |

### 21.4. Mẫu kết quả một ca khó

~~~yaml
testCase: CL-18
claimId: clm-lab-7e8d03ac
businessKey: PARTNER-A/DOC-2026-0041
scenario: "DB commit success; consumer crashes before broker ack"
expected: >
  The token is redelivered; payload can still be redeemed;
  business effect remains one; cleanup waits for completion.
actual: "Fill with actual observations"
result: PENDING
evidenceRef: "lab://tests/CL-18"
owner: claim-check-lab
verifiedAt: null
~~~

**Không** chuyển result sang PASS chỉ vì có code idempotency trên giấy. Phải mô phỏng crash đúng điểm, kiểm tra **business DB**, **claim store**, **broker state** và kết quả cleanup.

### 21.5. Những phép thử quan trọng nhất

Sáu ca thường bộc lộ lỗi thiết kế:

1. **CL-13:** store OK nhưng publish chưa xác nhận.
2. **CL-17:** claim đã lấy ra nhưng handler thất bại.
3. **CL-18:** business commit OK nhưng broker ack mất.
4. **CL-25:** token của tenant khác không thể redeem.
5. **CL-33:** nhóm subscriber đầu hoàn tất nhưng nhóm sau còn cần dữ liệu.
6. **CL-36:** cleanup không chạy trước khi hết nghĩa vụ.

Nếu các ca này chưa có bằng chứng, một sơ đồ Claim Check “chạy thành công khi không lỗi” vẫn chưa đủ để nói flow đáng tin.

## 22. Anti-patterns và checklist trước production

### 22.1. Những sai lầm thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Dùng Claim Check cho mọi message vài byte** | Tăng store I/O và latency vô ích | Chỉ dùng khi lợi ích rõ ràng |
| **Cho binary vào header sau claim-in** | Broker vẫn nhận payload lớn | Kiểm tra serialized transport envelope |
| **Dùng SimpleMessageStore giữa hai JVM** | Consumer không tìm dữ liệu | Shared durable store/API |
| **Lưu File/InputStream object rồi mong đọc sau restart** | Handle/session không còn hợp lệ | Persist bytes/object + metadata |
| **Xóa claim khi Claim Check Out retrieve** | Handler lỗi thì retry không có payload | Dọn sau completion/retention |
| **Xóa claim ngay khi publish bị timeout** | Broker có thể đã nhận token | Outbox + reconciliation, không delete mù |
| **Coi MessageStore là durable work queue** | Không có ack/dispatch như broker | Tách claim storage và work transport |
| **Tin claimId là bằng chứng authorization** | BOLA/IDOR, cross-tenant data leak | Authn/authz từng lần redeem |
| **Dùng object key có thể đoán và public read** | Đọc trộm payload | Private bucket, service proxy/ACL, signed URL kiểm soát |
| **Không có schema/version trong claim** | Consumer đọc sai payload sau rollout | Version contract và migration |
| **Chỉ dedupe theo claimId** | Hai claims cùng business command vẫn chạy trùng | Business idempotency key |
| **Lưu token vào Kafka với TTL object rất ngắn** | Historical replay/consumer lag mất payload | Retention contract hoặc khả năng tái dựng |
| **Dùng chung claim rồi xóa sau subscriber đầu** | Các subscriber khác missing payload | Per-consumer completion/retention |
| **Không có orphan cleanup** | Object store tăng mãi | GC có đối soát và audit |
| **GC xóa mọi claim quá X ngày** | Mất dữ liệu DLQ/retry/legal hold | Cleanup dựa trên trạng thái và nghĩa vụ |
| **Đưa full payload vào debug log** | Rò dữ liệu và chi phí log lớn | Log metadata an toàn |
| **Nạp mọi object vào byte[]** | OOM/GC pressure | Streaming/chunking với giới hạn |
| **Giới hạn broker concurrency nhưng không giới hạn redeem** | Store quá tải dù tokens nhỏ | Bulkhead riêng cho store reads |
| **Coi checksum là xác thực nguồn** | Attacker sửa cả data và metadata | Bảo vệ metadata, authorization/signature |
| **Không tách store 404 với store outage** | Đánh dấu mất dữ liệu khi chỉ là timeout | Error taxonomy và retry |
| **Trả HTTP 202 trước khi dữ liệu bền vững** | Client tin work đã nhận nhưng process chết làm mất | Persist job/claim/outbox trước accepted |
| **Dùng local path cross-container** | Consumer không thấy file hoặc đọc nhầm path | Shared object store + scoped key |

### 22.2. Checklist thiết kế

- [ ] Có lý do kỹ thuật/kinh tế để dùng Claim Check thay vì truyền payload trực tiếp.
- [ ] Đã xác định phần nội dung lưu đi: toàn Message, payload hay object bytes.
- [ ] Token nhỏ, bất biến theo nội dung/version và không chứa secret.
- [ ] Có metadata đáng tin về source, tenant, object version, TTL và checksum.
- [ ] Consumer được xác thực và cấp quyền **từng lần redeem**, không chỉ có claimId.
- [ ] Store dùng chung và bền vững nếu token đi qua nhiều JVM/broker.
- [ ] Không serialize những header/channel/context không tương thích hoặc nhạy cảm.
- [ ] Payload hoàn chỉnh/AVAILABLE trước khi publish token.
- [ ] Có outbox/retry/reconciliation cho khoảng trống giữa store và publish.
- [ ] Có idempotency theo business operation khi token bị giao lại.
- [ ] Broker ack/offset phù hợp điều kiện business commit.
- [ ] Đã kiểm thử lỗi sau retrieve trước business commit.
- [ ] Đã kiểm thử lỗi sau business commit trước broker ack.
- [ ] Không xóa claim trước khi mọi nhóm còn cần dữ liệu đã hoàn tất theo contract.
- [ ] Retention đủ cho backlog, retry, DLQ và replay đã cam kết.
- [ ] Garbage collector có eligibility, trạng thái, audit và dry-run khi cần.
- [ ] Có cơ chế phân biệt missing/expired/unauthorized/store unavailable.
- [ ] Dùng streaming/size limits để tránh OOM và payload độc hại.
- [ ] Redeem concurrency được giới hạn theo store/DB/object throughput.
- [ ] Các file/object tạm, backup, cache và log nằm trong data lifecycle policy.
- [ ] Có metrics store/publish/redeem/commit/cleanup, không chỉ broker receive.
- [ ] Có runbook cho missing claim, orphan, duplicate, fan-out và DLQ expiry.
- [ ] Đã thử restart producer/consumer và thay đổi schema phiên bản.
- [ ] Có bằng chứng kiểm thử âm tính, readback và cleanup ở môi trường được phép.

### 22.3. Cây quyết định áp dụng Claim Check

~~~mermaid
flowchart TD
    START{"Payload lớn / nhạy cảm / nhiều hop?"}
    START -->|Không đáng kể| DIRECT["Truyền message trực tiếp nếu phù hợp"]
    START -->|Có| STORE{"Payload lưu ở đâu?"}
    STORE -->|Spring Message vừa phải| MSG["MessageStore + ClaimCheckIn/Out"]
    STORE -->|File/object rất lớn| OBJ["Object storage + metadata + custom redeem"]
    MSG --> SHARED{"Consumer chạy khác JVM?"}
    OBJ --> SHARED
    SHARED -->|Có| DURABLE["Shared durable store + authz"]
    SHARED -->|Không| LOCAL["Lab có thể dùng in-memory; production đánh giá durability"]
    DURABLE --> SAFE["Store before publish + recovery"]
    LOCAL --> SAFE
    SAFE --> DELIVERY["Ack + business idempotency + retry"]
    DELIVERY --> RETAIN["Retention + DLQ/fan-out + GC"]
    RETAIN --> VALIDATE["Test crash, unauthorized redeem, missing data"]
~~~

Nếu bạn chưa giải thích được **“claim còn tồn tại bao lâu và ai có quyền xóa nó?”**, chưa nên coi việc publish một UUID nhỏ là hoàn thành Claim Check Pattern.

## 23. Rubric thực hành, câu hỏi và tổng kết

### 23.1. Rubric tự đánh giá

Đánh giá từng tiêu chí theo thang **0–3**: 0 chưa có; 1 mới mô tả; 2 đã triển khai nhưng chưa kiểm chứng đầy đủ; 3 có kiểm thử thực tế, bằng chứng và xử lý lỗi.

| Tiêu chí | Mức 3 cần chứng minh |
| --- | --- |
| **Hiểu pattern** | Phân biệt Claim Check, MessageStore, broker và idempotency |
| **Message contract** | Token có ID/version/tenant/business key, payload không lộ |
| **Store design** | Chọn in-memory/JDBC/object store đúng quy mô và durability |
| **Claim-in** | Object hoàn chỉnh trước publish, outbox/recovery |
| **Claim-out** | Authorized redeem, checksum/schema và xử lý missing |
| **Business semantics** | Commit và ack đúng contract, side effect idempotent |
| **Multi-consumer** | Fan-out/competing/replay không xóa claim sớm |
| **Retention** | TTL/cleanup có state và khả năng đối soát |
| **Security** | Chặn cross-tenant, bảo vệ object/credential/log |
| **Performance** | Đo throughput store, stream/memory, bounded concurrency |
| **Operations** | Metrics, runbooks, DLQ, orphan detection |
| **Validation** | Fault injection, restart, evidence, test âm tính |

**Tổng tối đa minh họa: 36 điểm.** Rubric này hỗ trợ tự học, không phải tiêu chuẩn hoặc chứng nhận chính thức của Spring Integration.

### 23.2. Câu hỏi tự kiểm tra

1. Claim Check khác **message compression** và **message filtering** ở điểm nào?
2. ClaimCheckInTransformer của Spring Integration dùng thành phần lưu nào để cất original Message?
3. Vì sao một **SimpleMessageStore riêng ở từng JVM** không làm việc khi token đi qua broker tới service khác?
4. ClaimCheckOutTransformer khôi phục dữ liệu thành công có chứng minh nghiệp vụ đã commit không?
5. Điều gì xảy ra nếu original Message bị xóa sau retrieve nhưng handler sau đó ném exception?
6. Vì sao token chứa UUID khó đoán vẫn cần authorization khi redeem?
7. Nếu producer store thành công nhưng broker publish thất bại, nên xử lý orphan bằng cách nào?
8. Khi Kafka có ba consumer groups, vì sao xóa claim sau group đầu có thể gây lỗi?
9. Một DLQ chứa claim ID nhưng không có original payload sẽ ảnh hưởng replay thế nào?
10. Idempotency theo claimId có đủ khi cùng business command được gửi dưới hai claims khác nhau không?
11. Vì sao HTTP 202 Accepted nên gắn với một state/job bền vững theo contract?
12. Khi lưu file lớn, vì sao không nên serialize InputStream như một object dùng chung?
13. Metrics nào giúp phân biệt lỗi broker không gửi token và lỗi store không redeem được?
14. Checksum có giúp xác minh người gửi file là người có thẩm quyền không?
15. Khi xóa object và metadata nằm ở hai hệ thống khác nhau, cần tính điều gì?

**Gợi ý:** (1) cất nội dung và gửi reference; (2) MessageStore; (3) in-memory không chia sẻ và mất qua restart; (4) không; (5) retry mất payload; (6) claim ID không phải quyền; (7) outbox/reconciliation/GC theo trạng thái; (8) nhóm khác/replay còn cần; (9) không phục hồi được work nếu không có nguồn khác; (10) không, cần business key; (11) crash recovery; (12) stream handle không portable và không bền; (13) publish pending vs redeem failures; (14) không; (15) trạng thái xóa, idempotent retry, orphan reconciliation.

### 23.3. Tổng kết

**Claim Check với Message Store** cho phép giữ original message/payload ở một nơi được quản lý và chỉ truyền **tham chiếu nhỏ** qua các adapter, gateway, poller và MessageChannel. Trong **Spring Integration**, ClaimCheckInTransformer và ClaimCheckOutTransformer hỗ trợ quy trình lưu/khôi phục Message qua **MessageStore**; khi payload rất lớn hoặc consumer chạy khác JVM, có thể cần **shared durable store hoặc object storage + claim metadata/service** thay vì dùng memory.

Pattern này hữu ích khi kết hợp **File/SFTP/HTTP inbound** với **JMS/AMQP/Kafka broker** hay **JDBC business storage**, nhưng nó không tự mang tới exactly-once, bảo mật, transaction xuyên hệ thống hoặc cleanup an toàn. Một thiết kế đáng tin phải giải quyết **store-before-publish, outbox/retry, authorization từng lần redeem, idempotency ở business commit, retention cho DLQ/fan-out, GC và observability**.

**Nguyên tắc cuối cùng:** *Token chỉ giúp chỉ đường tới dữ liệu; tính đúng của hệ thống được chứng minh ở việc dữ liệu còn đọc được đúng người, đúng phiên bản, đúng thời điểm và được dọn chỉ sau khi mọi nghĩa vụ xử lý hợp lệ đã hoàn tất.*
