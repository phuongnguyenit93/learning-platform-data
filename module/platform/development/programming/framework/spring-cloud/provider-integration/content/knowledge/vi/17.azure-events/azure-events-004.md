# Checkpoint, quyền sở hữu partition và khôi phục consumer

Azure Event Hubs lưu event theo partition trong một khoảng retention. Consumer đọc stream theo vị trí và cần ghi nhận tiến độ để tiếp tục sau khi process restart, container bị thay thế hoặc một instance khác nhận partition. **Checkpoint** lưu vị trí đọc đã được xử lý; **partition ownership** xác định processor instance nào đang đảm nhiệm partition trong một consumer group; **recovery** là quá trình tiếp tục xử lý sau lỗi mà không bỏ sót event và kiểm soát được việc đọc lại.

Trong chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, bài học này hướng dẫn vận hành consumer Spring Boot với EventProcessorClient, Azure Blob checkpoint store và Microsoft Entra ID. Người học sẽ thiết kế checkpoint đúng thời điểm, hiểu ownership và rebalance, khôi phục sau crash hoặc mất mạng, xử lý duplicate và poison event, kiểm tra retention, bảo vệ quyền truy cập và xây dựng runbook cho hệ thống production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa partition, consumer group, ownership record, offset, sequence number và checkpoint.
- Phân biệt **event đã nhận**, **event đã xử lý**, **checkpoint đã lưu** và **event đã được archive**.
- Mô tả cách EventProcessorClient phối hợp ownership và cân bằng partition giữa nhiều instance.
- Chọn checkpoint store, initial position, tần suất checkpoint và chính sách replay phù hợp.
- Phân tích các cửa sổ lỗi: chết trước commit, sau commit nhưng trước checkpoint, checkpoint thất bại và mất ownership.
- Thiết kế consumer idempotent, inbox/dedup, quarantine và xử lý poison event.
- Cấu hình EventProcessorClient trong Spring Boot với Managed Identity và Azure RBAC.
- Vận hành graceful shutdown, scale-out/in, recovery và kiểm thử trên môi trường cô lập.
- Xây dựng dashboard/runbook dựa trên consumer lag, checkpoint age, ownership và retention.

## 2. Các khái niệm và ranh giới trạng thái

### 2.1. Partition, consumer group và processor instance

Event Hub được chia thành các **partition**; mỗi partition là một log event có thứ tự riêng. Một **consumer group** tạo vị trí đọc logic độc lập cho một workload. Trong cùng consumer group, nhiều processor instance phối hợp để chia partition. Mỗi instance có thể sở hữu một hoặc nhiều partition, tùy số partition và trạng thái cân bằng.

Ví dụ event hub có 8 partition:
- Một instance có thể sở hữu cả 8.
- Hai instance có thể chia khoảng 4 + 4.
- Bốn instance có thể chia khoảng 2 mỗi instance.
- Mười instance không tạo ra mười luồng đọc độc lập nếu chỉ có 8 partition; một số instance có thể không sở hữu partition.

Consumer group khác nhau có tiến độ và ownership riêng. Analytics và fraud detection có thể đọc cùng event hub mà không chia sẻ checkpoint. Ngược lại, các replica của cùng một ứng dụng logic phải dùng **cùng consumer group và cùng checkpoint store** để phối hợp.

### 2.2. Offset, sequence number và checkpoint

- **Offset** là vị trí event trong log của một partition, thường được SDK biểu diễn bằng chuỗi.
- **Sequence number** là số thứ tự tăng dần của event trong partition.
- **Checkpoint** là bản ghi tiến độ mà consumer đã lưu bền vững để tiếp tục đọc sau đó.
- **Enqueued time** là thời điểm Event Hubs tiếp nhận event, hữu ích để đo tuổi event và độ trễ ingest.
- **Ownership record** là trạng thái phối hợp cho biết processor instance nào đang nắm quyền xử lý một partition trong consumer group.

Offset và sequence number thuộc phạm vi partition, không phải số thứ tự toàn event hub. Checkpoint không có nghĩa event đã được xử lý đúng một lần; nó chỉ lưu vị trí mà ứng dụng quyết định có thể tiếp tục từ đó.

### 2.3. Bốn trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Nơi quan sát |
|---|---|---|
| Received | Processor đã nhận event từ Event Hubs | Callback và metadata event |
| Processed | Side effect nghiệp vụ đã hoàn tất hoặc event đã được quarantine bền vững | Database, inbox, quarantine store |
| Checkpointed | Vị trí đọc đã được lưu vào checkpoint store | Blob checkpoint metadata |
| Archived | Event đã được lưu vào kho lưu trữ dài hạn nếu kiến trúc yêu cầu | Blob/ADLS hoặc data lake |

Không nên suy ra **processed** từ **received**, hoặc suy ra **archived** từ **checkpointed**. Checkpoint store không chứa toàn bộ event body và không thay thế Event Hubs Capture.

## 3. Vì sao cần checkpoint?

Consumer có thể dừng vì deployment, crash, mất mạng, hết quota, lỗi credential, node bị thu hồi hoặc rebalance. Khi khởi động lại, processor cần biết nên tiếp tục đọc từ đâu.

Nếu không lưu checkpoint, ứng dụng có thể phải bắt đầu từ initial position, gây đọc lại nhiều dữ liệu hoặc bỏ qua phần lịch sử nếu chọn vị trí không phù hợp. Nếu checkpoint lưu sai thời điểm, consumer có thể bỏ qua event chưa xử lý. Vì vậy checkpoint là một phần của **correctness contract** giữa stream và ứng dụng.

~~~mermaid
flowchart LR
    EH["Event Hubs partition"] --> R["Read event at offset N"]
    R --> H["Business handler"]
    H --> DB["Commit side effect"]
    DB --> CP["Persist checkpoint N"]
    CP --> NEXT["Continue with next events"]
    CP -. "Failure before save" .-> REPLAY["Resume from older checkpoint"]
    REPLAY --> H
~~~

Một checkpoint store đúng giúp processor khôi phục vị trí đọc; nó không tự khôi phục transaction database, không đảm bảo handler idempotent và không làm retention của Event Hubs dài hơn.

## 4. Blob checkpoint store và partition ownership

### 4.1. Blob checkpoint store lưu những gì?

Azure SDK cung cấp package **azure-messaging-eventhubs-checkpointstore-blob** với BlobCheckpointStore. Store sử dụng Blob Storage để giữ metadata ownership và checkpoint cho từng partition/consumer group/event hub theo quy ước của SDK.

Hai nhóm thông tin chính:
- **Ownership:** owner ID của processor, partition ID, thông tin cập nhật/expiry và metadata phục vụ phối hợp.
- **Checkpoint:** offset/sequence number đã được consumer lưu cho partition.

Ứng dụng không nên tự sửa hoặc xóa các blob metadata này khi processor đang chạy. Định dạng và cách đặt tên là chi tiết triển khai của thư viện; dùng SDK checkpoint store để quản lý thay vì tự tạo lease/record song song.

### 4.2. Ownership được phối hợp như thế nào?

Ở mức khái niệm, mỗi processor instance có một owner ID. Các instance đọc danh sách ownership trong checkpoint store, xác định partition chưa có owner hoặc ownership đã hết hạn, sau đó cố gắng nhận ownership theo cơ chế đồng bộ của store. Instance đang sở hữu partition định kỳ cập nhật ownership để thể hiện nó còn hoạt động.

Khi một instance mới tham gia hoặc một instance cũ ngừng cập nhật ownership:
1. Processor instances phát hiện trạng thái ownership thay đổi ở chu kỳ load balancing.
2. Một instance có thể nhận thêm partition chưa có owner hoặc partition đã hết hạn.
3. Instance cũ có thể đóng processor cho partition được chuyển giao.
4. Instance mới bắt đầu đọc từ checkpoint đã lưu hoặc initial position nếu chưa có checkpoint.
5. Event chưa được checkpoint có thể được đọc lại.

Việc nhận ownership dựa trên cơ chế cập nhật có điều kiện của checkpoint store và thuật toán load balancing của SDK. Không nên tự giả định rằng một process bị mất mạng sẽ lập tức bị thu hồi quyền; ownership expiry và chu kỳ cân bằng tạo ra một khoảng trễ phát hiện.

### 4.3. Ownership không phải khóa nghiệp vụ

Ownership giúp các processor instance phối hợp đọc partition trong cùng consumer group. Nó không phải distributed lock để bảo vệ database row, không bảo vệ side effect ở HTTP API và không bảo đảm event chỉ chạy một lần.

Trong tình huống mạng phân vùng, instance cũ có thể chưa biết nó đã mất ownership trong khi instance khác bắt đầu nhận partition sau expiry. Vì vậy ứng dụng vẫn phải chấp nhận duplicate/replay và dùng idempotency ở tầng nghiệp vụ. Không dùng ownership record làm cơ chế duy nhất để ngăn hai payment hoặc hai lần cập nhật database.

### 4.4. Một checkpoint store cho nhiều instance cùng workload

Các instance của cùng một consumer group phải nhìn thấy cùng checkpoint store để phối hợp ownership và tiến độ. Các consumer group khác nhau có thể có checkpoint riêng; có thể dùng cùng storage account/container nếu cấu hình SDK và quyền cho phép, nhưng nên thiết kế scope/container riêng theo workload hoặc môi trường khi cần cách ly vận hành và bảo mật.

Không dùng chung checkpoint namespace/container một cách thiếu quy ước giữa:
- Dev và production.
- Hai event hub khác nhau nhưng cùng tên consumer group.
- Hai ứng dụng logic có mục tiêu xử lý khác nhau.
- Một test run tạm thời và processor production.

Checkpoint store nên có lifecycle dài hơn process/pod; không tạo container mới ngẫu nhiên mỗi lần deploy vì processor mới sẽ không tìm thấy checkpoint cũ.

## 5. Vòng đời partition ownership trong EventProcessorClient

### 5.1. Khi processor khởi động

Một EventProcessorClient thường thực hiện:
1. Tạo hoặc sử dụng client Event Hubs với namespace, hub và consumer group đã cấu hình.
2. Đọc thông tin partition và ownership/checkpoint từ store.
3. Tham gia load balancing với các instance khác trong cùng group.
4. Nhận ownership của partition được phân công.
5. Xác định vị trí bắt đầu đọc: checkpoint đã lưu hoặc initial position.
6. Gọi callback xử lý event và callback xử lý lỗi theo hoạt động của processor.

Ứng dụng không cần tự viết thuật toán phân chia partition nếu dùng EventProcessorClient. Tuy vậy, phải cấu hình cùng consumer group, checkpoint store, credential và resource ID giữa các replica của cùng workload.

### 5.2. Khi processor chạy ổn định

Processor định kỳ duy trì ownership và kiểm tra cân bằng. Event được nhận từ các partition mà instance đang sở hữu. Ứng dụng có thể checkpoint theo từng event, batch hoặc khoảng thời gian dựa trên replay budget.

Khi một partition được chuyển giao, processor đóng xử lý partition đó theo lifecycle SDK và instance khác có thể tiếp quản. Callback partition close/initialization nếu được dùng giúp ứng dụng quản lý resource theo partition; không lưu trạng thái nghiệp vụ duy nhất trong bộ nhớ của instance vì partition có thể chuyển sang instance khác.

### 5.3. Khi scale-out

Khi thêm replica:
- Instance mới đăng ký owner ID.
- Các processor hiện có và instance mới cùng quan sát ownership.
- Load balancing có thể chuyển một số partition để phân phối tải.
- Instance mới bắt đầu từ checkpoint đã lưu.
- Trong lúc chuyển giao có thể có thời gian ngắn giảm throughput và phát sinh replay.

Không kỳ vọng scale-out lập tức tăng throughput theo tỷ lệ tuyến tính. Số partition giới hạn số processor có thể đồng thời sở hữu partition trong cùng group. Nếu bottleneck nằm ở database, Blob checkpoint store hoặc handler, thêm pod có thể làm tải downstream tăng mà không tăng tốc độ xử lý hữu ích.

### 5.4. Khi scale-in hoặc instance dừng

Khi instance dừng có kiểm soát:
- Gọi stop theo lifecycle SDK.
- Cho processor nhường ownership và đóng các tài nguyên partition.
- Hoàn tất callback đang chạy trong thời gian shutdown được cấp nếu có thể.
- Không checkpoint event chưa commit.
- Instance còn lại nhận partition sau khi ownership được giải phóng hoặc hết hạn.

Nếu process bị kill đột ngột, ownership có thể còn tồn tại tới khi hết hạn. Instance khác không nhất thiết tiếp quản ngay. Cấu hình termination grace period của container cần đủ thời gian cho shutdown, nhưng không được kéo dài vô hạn làm deployment treo.

## 6. Initial position và resume

### 6.1. Khi chưa có checkpoint

Khi consumer group/partition chưa có checkpoint, processor cần initial position. Các lựa chọn thường gặp:
- **Earliest:** đọc từ event sớm nhất còn trong retention.
- **Latest:** bắt đầu từ event mới được ghi sau thời điểm bắt đầu.
- **Enqueued time:** bắt đầu từ một thời điểm đã chọn.
- **Offset/sequence number:** bắt đầu từ vị trí cụ thể nếu vị trí còn khả dụng.

Chọn initial position theo mục tiêu workload:
- Projection cần dựng lại trạng thái có thể cần earliest trong retention hoặc archive.
- Consumer chỉ nhận event mới từ thời điểm triển khai có thể chọn latest.
- Backfill có thể chọn thời điểm hoặc offset cụ thể trong một consumer group riêng.

Không để mặc định initial position quyết định production mà không được ghi rõ trong cấu hình và runbook.

### 6.2. Khi checkpoint đã tồn tại

Khi checkpoint cho partition tồn tại và còn hợp lệ, processor tiếp tục từ checkpoint đó. Initial position không phải công cụ reset tiến độ mỗi lần restart. Nếu cần replay:
- Tạo consumer group mới với initial position phù hợp.
- Dùng consumer/processor replay riêng có giới hạn tốc độ.
- Dùng archive/Capture nếu dữ liệu cần replay đã hết retention.
- Thực hiện reset checkpoint chỉ theo quy trình được hỗ trợ, có backup/đối chiếu và khi processor không còn tranh chấp ownership.

Không xóa checkpoint blob để “sửa lỗi” trong khi processor production vẫn chạy. Việc đó có thể làm processor đọc lại nhiều event, tạo duplicate hoặc gây ownership churn.

### 6.3. Retention và checkpoint cũ

Checkpoint lưu vị trí nhưng Event Hubs chỉ giữ event trong khoảng retention được cấu hình. Nếu consumer ngừng lâu hơn retention, event tại offset cũ có thể đã bị loại bỏ. Checkpoint không thể kéo event đã hết retention trở lại.

Khi phát hiện checkpoint không còn nằm trong dữ liệu khả dụng:
- Xác định retention hiện tại và thời điểm consumer ngừng.
- Kiểm tra có archive/Capture hay nguồn dữ liệu khác để backfill không.
- Chọn initial position có chủ đích cho dữ liệu còn lại.
- Ghi nhận khoảng dữ liệu có thể thiếu và thông báo chủ sở hữu nghiệp vụ.
- Không âm thầm chuyển sang latest nếu yêu cầu nghiệp vụ cần đầy đủ lịch sử.

## 7. Checkpoint đúng thời điểm: commit trước, checkpoint sau

### 7.1. Cửa sổ lỗi

Giả sử consumer nhận event E, cập nhật database rồi checkpoint:
- **Checkpoint trước database commit:** nếu process chết giữa hai bước, checkpoint đã tiến nhưng side effect chưa bền vững; event có thể bị bỏ qua.
- **Database commit trước checkpoint:** nếu process chết giữa hai bước, event có thể được đọc lại; cần idempotency để không lặp side effect.
- **Database commit và dedup cùng transaction trước checkpoint:** event đọc lại nhưng consumer nhận biết đã xử lý.
- **Quarantine bền vững trước checkpoint:** event lỗi không thể xử lý được có thể được cách ly rồi bỏ qua theo policy rõ ràng.

~~~mermaid
sequenceDiagram
    participant EH as Event Hubs
    participant C as Consumer
    participant DB as Database
    participant B as Blob checkpoint store
    EH->>C: Event E at offset N
    C->>DB: Commit business effect + inbox(E)
    DB-->>C: Commit OK
    C->>B: Save checkpoint N
    B-->>C: Checkpoint saved
    Note over C,B: Nếu checkpoint thất bại, E có thể replay
~~~

Không có transaction atomic mặc định giữa database nghiệp vụ và Blob checkpoint store. Vì vậy, duplicate sau commit nhưng trước checkpoint là tình huống bình thường cần được thiết kế, không phải ngoại lệ không thể xảy ra.

### 7.2. Checkpoint mỗi event hay theo batch?

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Mỗi event | Replay window nhỏ | Nhiều thao tác Blob/checkpoint, có thể giảm throughput |
| Theo số lượng event | Giảm số lần ghi checkpoint | Có thể replay nhiều event đã xử lý |
| Theo thời gian | Dễ đặt giới hạn thời gian replay | Số event replay thay đổi theo throughput |
| Sau batch DB commit | Đồng bộ tiến độ với batch bền vững | Phải biết chính xác batch nào đã commit và không có event trước đó còn pending |

Chọn theo throughput, thời gian xử lý, chi phí checkpoint store, RPO xử lý và khả năng idempotency. Nếu checkpoint theo batch, chỉ checkpoint tới event cuối cùng của **chuỗi liên tục đã hoàn tất**. Không được checkpoint vượt qua event trước đó còn đang xử lý.

### 7.3. Không để xử lý song song làm checkpoint vượt event lỗi

Trong một partition, Event Hubs đọc theo thứ tự. Nhưng nếu callback đẩy event vào executor rồi xử lý bất đồng bộ, event sau có thể hoàn tất trước event trước. Nếu checkpoint tại event sau, event trước chưa xong có thể bị bỏ qua sau restart.

Các lựa chọn:
- Xử lý tuần tự theo partition.
- Song song theo aggregate key nhưng duy trì thứ tự và watermark hoàn tất liên tục.
- Lưu trạng thái xử lý bền vững để có thể tiếp tục/reconcile.
- Chỉ cập nhật checkpoint tới offset/sequence cuối cùng mà tất cả event trước đó đã hoàn tất hoặc quarantine.
- Giới hạn số event in-flight để tránh hàng đợi nội bộ vô hạn.

## 8. Idempotency và inbox để chống xử lý trùng

Consumer Event Hubs thường phải chấp nhận at-least-once processing do replay, rebalance và checkpoint failure. Dùng event ID nghiệp vụ ổn định, không chỉ offset.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction:
1. Insert event ID vào bảng processed_event.
2. Nếu unique conflict, event đã được xử lý; bỏ qua side effect.
3. Nếu insert thành công, cập nhật projection/trạng thái nghiệp vụ.
4. Commit.
5. Chỉ sau khi handler trả thành công mới checkpoint.

Ví dụ SQL minh họa:

~~~sql
INSERT INTO processed_event (consumer_name, event_id)
VALUES ('order-projection', :event_id)
ON CONFLICT DO NOTHING;
~~~

Nếu số hàng insert bằng 0, event đã được ghi nhận. Cần bảo đảm insert dedup và side effect nằm trong **cùng transaction**; nếu tách hai transaction, process có thể ghi dedup rồi chết trước side effect, làm mất xử lý khi replay.

Ngoài event ID, có thể lưu payload hash hoặc schema version để phát hiện cùng ID nhưng payload khác. Retention của bảng dedup phải dài hơn khoảng thời gian event có thể được replay hoặc gửi lại.

## 9. Khôi phục sau các loại sự cố

### 9.1. Process/container bị crash

1. Orchestrator phát hiện instance không còn healthy.
2. Ownership record của instance cũ không được cập nhật nữa.
3. Sau khi ownership hết hạn và load balancing chạy, instance còn lại có thể nhận partition.
4. Instance mới đọc checkpoint gần nhất.
5. Event sau checkpoint được đọc lại.
6. Dedup/inbox ngăn side effect đã commit bị lặp.

Theo dõi thời gian ownership expiry và load-balancing interval để ước lượng recovery time. Không coi một giá trị interval là SLA; thời gian thực còn phụ thuộc mạng, Blob, Event Hubs và trạng thái các instance.

### 9.2. Mất kết nối Blob checkpoint store

Processor có thể vẫn kết nối Event Hubs nhưng không đọc/ghi ownership hoặc checkpoint. Khi đó:
- Xác minh DNS, firewall, private endpoint và TLS của Blob.
- Xác minh principal runtime và Storage Blob Data Contributor.
- Kiểm tra container URL/account và Region.
- Xem lỗi checkpoint/ownership trong log processor.
- Không tự tạo container hoặc đổi storage account bằng quyền runtime nếu IaC sở hữu tài nguyên.
- Sau khi kết nối phục hồi, kiểm tra checkpoint thực tế và khả năng replay.

Không giả định checkpoint update đã thành công chỉ vì handler không ném exception. Nếu Blob request timeout, kết quả lưu có thể chưa rõ; khi restart, đọc checkpoint thực tế từ store và dự kiến duplicate.

### 9.3. Mất kết nối Event Hubs

Khi namespace hoặc đường mạng gặp sự cố:
- Processor có thể ngừng nhận event hoặc phát sinh lỗi kết nối.
- Ownership heartbeat có thể không được duy trì tùy phụ thuộc store và SDK.
- Producer vẫn có thể gửi vào hub nếu đường đi producer độc lập.
- Khi kết nối phục hồi, processor tiếp tục từ checkpoint, có thể phát sinh replay.

Phân biệt lỗi Event Hubs, lỗi DNS/private endpoint, lỗi Entra token, lỗi RBAC và lỗi Blob checkpoint. Một lỗi 403 không phải lỗi quota; một timeout không chứng minh event đã bị mất.

### 9.4. Instance cũ quay lại sau khi ownership đã chuyển

Instance cũ có thể phục hồi network sau khi instance khác đã nhận partition. SDK dùng ownership coordination để quản lý quyền đọc; tuy nhiên, không thiết kế side effect dựa trên giả định không bao giờ có overlap hoặc duplicate trong mọi failure mode.

Handler vẫn phải idempotent. Với thao tác có tính không thể lặp như thanh toán, gửi email hoặc gọi API đối tác, dùng idempotency key tại hệ thống đích hoặc outbox/workflow có trạng thái bền vững.

### 9.5. Checkpoint bị xóa hoặc hỏng

Trước khi thay đổi:
- Dừng các processor instance của consumer group liên quan theo quy trình.
- Xác minh event hub, consumer group, partition và checkpoint store đúng.
- Kiểm tra backup/soft delete/versioning của Blob nếu có cấu hình.
- Xác định initial position và khoảng dữ liệu cần đọc lại.
- Đánh giá tác động side effect và tốc độ replay.
- Thực hiện thay đổi có phê duyệt, sau đó khởi động một instance canary và quan sát trước khi scale.

Không xóa toàn bộ container checkpoint để xử lý một partition đơn lẻ nếu chưa hiểu cấu trúc metadata và tác động tới các consumer group khác.

## 10. Poison event, quarantine và replay

Event Hubs là stream log, không phải queue có DLQ tích hợp như Service Bus. Một event sai schema hoặc gây lỗi nghiệp vụ có thể khiến consumer liên tục gặp lại lỗi nếu checkpoint không tiến. Cần định nghĩa rõ chính sách:

- **Transient failure:** retry có giới hạn trong handler hoặc tạm dừng partition processing; không checkpoint qua event chưa xử lý.
- **Permanent/schema failure:** ghi event và metadata cần thiết vào quarantine store/queue một cách bền vững; chỉ checkpoint sau khi quarantine thành công và policy cho phép.
- **Unknown outcome:** kiểm tra inbox/idempotency record hoặc đối soát hệ thống đích trước khi thử lại side effect.
- **Manual intervention:** dừng/giới hạn processor theo runbook khi không thể quyết định tự động.

Quarantine record nên có event ID, partition ID, offset, sequence number, enqueued time, schema version, loại lỗi và correlation ID. Hạn chế lưu raw payload; nếu cần, mã hóa và phân quyền chặt.

Replay cần có công cụ riêng:
- Chọn consumer group mới hoặc khoảng offset/time rõ ràng.
- Giới hạn tốc độ replay để không làm quá tải database.
- Gắn replay run ID và theo dõi số event thành công/thất bại.
- Giữ event ID gốc để consumer dedup.
- Không publish lại event bằng ID mới nếu mục tiêu là xử lý lại cùng ý định mà không có liên kết với event gốc.
- Có kế hoạch dừng và tiếp tục replay.

## 11. Cấu hình EventProcessorClient trong Spring Boot

### 11.1. Dependencies và configuration properties

Ví dụ cần các thư viện Azure SDK tương thích:
- azure-messaging-eventhubs
- azure-messaging-eventhubs-checkpointstore-blob
- azure-storage-blob
- azure-identity

Dùng BOM phù hợp với Spring Boot và Spring Cloud Azure đang sử dụng. Không trộn phiên bản SDK không tương thích.

Ví dụ property tự định nghĩa:

~~~yaml
app:
  event-hubs:
    namespace: orders-prod.servicebus.windows.net
    event-hub-name: order-events
    consumer-group: order-projection
    checkpoint-container-url: https://ordersprodstore.blob.core.windows.net/eventhub-checkpoints
    initial-position: earliest
~~~

Các khóa app.* là property của ứng dụng trong ví dụ, không phải property auto-configuration chung cho mọi Spring Cloud Azure version. Production phải lấy endpoint và resource ID từ deployment manifest đáng tin cậy; không hardcode credential.

### 11.2. Tạo credential và checkpoint client

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobContainerClientBuilder;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "app.event-hubs")
record EventHubProperties(
        String namespace,
        String eventHubName,
        String consumerGroup,
        String checkpointContainerUrl,
        String initialPosition) {}

@Configuration
@EnableConfigurationProperties(EventHubProperties.class)
class EventHubStorageConfiguration {

    @Bean
    DefaultAzureCredential defaultAzureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    BlobContainerAsyncClient checkpointContainer(
            EventHubProperties properties,
            DefaultAzureCredential credential) {
        return new BlobContainerClientBuilder()
                .endpoint(properties.checkpointContainerUrl())
                .credential(credential)
                .buildAsyncClient();
    }
}
~~~

DefaultAzureCredential chọn credential phù hợp theo môi trường và thứ tự provider chain của phiên bản SDK. Local developer credential có thể khác Managed Identity hoặc Workload Identity khi chạy trên Azure. Phải xác minh principal thực tế và role assignment trên storage account/container.

### 11.3. Tạo processor và cập nhật checkpoint

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventProcessorConfiguration {

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer,
            OrderEventHandler handler) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .processEvent(context -> {
                    // Handler phải commit side effect hoặc quarantine bền vững.
                    handler.handle(context.getEventData());

                    // Chỉ cập nhật checkpoint sau khi handler trả thành công.
                    context.updateCheckpoint();
                })
                .processError(error -> {
                    // Dùng logger/metrics có cấu trúc trong production.
                    // Không ghi token hoặc raw payload nhạy cảm.
                    System.err.println(
                            "Event processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();
    }
}
~~~

Đây là skeleton theo API Azure SDK for Java; đối chiếu method signatures với phiên bản dependency thực tế. Bean processor được dùng lại trong suốt lifecycle ứng dụng. Không tạo processor mới theo từng request hoặc mỗi lần xử lý event.

### 11.4. Start và stop theo lifecycle

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
class EventProcessorLifecycle implements ApplicationRunner {
    private final EventProcessorClient processor;

    EventProcessorLifecycle(EventProcessorClient processor) {
        this.processor = processor;
    }

    @Override
    public void run(ApplicationArguments args) {
        processor.start();
    }
}
~~~

Bean processor dùng destroy method stop để Spring dừng client khi context đóng. Trong production:
- Cấu hình termination grace period đủ cho shutdown.
- Không nhận thêm công việc khi instance chuẩn bị dừng.
- Theo dõi callback đang chạy và transaction database.
- Không checkpoint event đang xử lý dở.
- Đảm bảo Blob/DB client chưa bị đóng trước processor.
- Sau shutdown không thành công, chấp nhận replay từ checkpoint gần nhất và deduplicate.

Nếu dùng Spring lifecycle interface thay ApplicationRunner, phải bảo đảm start/stop không bị gọi nhiều lần và thứ tự phụ thuộc được quản lý rõ.

### 11.5. Initial position chỉ áp dụng khi chưa có checkpoint

Cấu hình initial position cần được ánh xạ vào API EventProcessorClient phù hợp phiên bản SDK và áp dụng cho từng partition. Khi checkpoint đã tồn tại, processor thường resume theo checkpoint. Không dùng việc thay initial position như cách reset tiến độ đã lưu.

Nếu muốn replay, ưu tiên consumer group riêng và runbook có giới hạn tốc độ. Tránh xóa checkpoint production khi processor vẫn hoạt động.

## 12. Xử lý event an toàn trước checkpoint

Một handler cần:
1. Validate event ID, event type và schema version.
2. Mở transaction database.
3. Insert event ID vào inbox/processed-event table có unique constraint.
4. Nếu event đã xử lý, kết thúc handler thành công mà không lặp side effect.
5. Nếu event mới, cập nhật dữ liệu nghiệp vụ.
6. Commit transaction.
7. Callback mới cập nhật checkpoint.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Lệnh insert:

~~~sql
INSERT INTO processed_event (consumer_name, event_id)
VALUES ('order-projection', :event_id)
ON CONFLICT DO NOTHING;
~~~

Nếu insert không tạo row mới, event đã được xử lý trước đó. Bảng dedup và thay đổi nghiệp vụ phải ở cùng transaction. Nếu event ID bị dùng lại với payload khác, ghi nhận conflict thay vì im lặng coi là duplicate hợp lệ.

Checkpoint không nằm trong transaction database. Do đó, DB commit thành công nhưng Blob checkpoint update thất bại sẽ dẫn đến replay; inbox đảm bảo side effect không lặp. Ngược lại, tuyệt đối không checkpoint trước commit.

## 13. Scale, rebalance và khả năng phục hồi

### 13.1. Số partition giới hạn parallelism

Trong một consumer group, một partition chỉ được một processor instance sở hữu tại một thời điểm theo cơ chế coordination thông thường. Nếu event hub có 6 partition, thêm 20 pod không tạo 20 partition worker hữu ích. Pod dư có thể không sở hữu partition.

Trước khi scale:
- Xem partition count và phân bố tải.
- Đo event processing duration, CPU, DB latency và checkpoint latency.
- Kiểm tra có hot partition do partition key lệch không.
- Tránh restart/scale liên tục làm ownership rebalance lặp.
- Xem xét tăng partition chỉ khi tier hỗ trợ và đã đánh giá ordering/key mapping.

### 13.2. Rebalance có thể tạo replay

Khi ownership chuyển từ instance A sang B, B bắt đầu từ checkpoint gần nhất. Các event A đã xử lý nhưng chưa checkpoint có thể được B đọc lại. Đây là cửa sổ replay dự kiến. Nếu checkpoint quá thưa, lượng replay tăng; nếu checkpoint quá thường xuyên, overhead Blob tăng.

### 13.3. Một partition xử lý chậm

Một partition có thể lag do:
- Hot partition.
- Event lớn hoặc handler xử lý lâu.
- DB connection pool cạn.
- Gọi API ngoài đồng bộ.
- Blob checkpoint store chậm.
- Callback xử lý song song nhưng giữ thứ tự không đúng.

Thêm instance không chia một partition cho nhiều owner trong cùng consumer group. Tối ưu handler, phân bố key hoặc tách workload mới giải quyết được nguyên nhân.

## 14. Monitoring và chỉ số sức khỏe consumer

Không chỉ theo dõi processor đang running. Một processor có thể chạy nhưng không tiến checkpoint hoặc lag tăng liên tục.

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active processor instances | Số instance đang tham gia | Instance giảm bất ngờ hoặc tăng/giảm liên tục |
| Partition ownership count | Số partition mỗi instance đang sở hữu | Một instance không sở hữu partition hoặc phân bố lệch kéo dài |
| Ownership change/rebalance | Tần suất chuyển partition | Rebalance liên tục, shutdown không sạch |
| Last checkpoint time | Thời điểm checkpoint gần nhất | Không tiến trong thời gian bất thường |
| Checkpoint age | Tuổi checkpoint theo partition | Replay window và nguy cơ lag tăng |
| Consumer lag | Chênh lệch vị trí đọc với cuối stream | Consumer không theo kịp ingestion |
| Event processing duration | Thời gian xử lý callback | Handler chậm hoặc downstream nghẽn |
| Checkpoint failures | Lỗi lưu tiến độ | Blob permission/network/timeout |
| Duplicate suppressed | Event replay đã được dedup | Tăng đột biến sau deploy/rebalance |
| Quarantine count | Event không thể xử lý bình thường | Schema drift hoặc producer lỗi |
| Oldest unprocessed event age | Tuổi event cũ nhất chưa hoàn tất | SLA nghiệp vụ có thể bị vi phạm |

Consumer lag có thể được ước tính bằng sequence/offset hoặc thời gian enqueue của event mới nhất so với tiến độ consumer. Event Hubs metrics không phải lúc nào cũng cung cấp một metric consumer lag đủ chi tiết cho từng ứng dụng; nên phát application metrics từ processor và checkpoint store. Không dùng offset của hai partition khác nhau để tính một chênh lệch toàn cục đơn giản.

### 14.1. Alert nên gắn với runbook

Ví dụ:
- Checkpoint age vượt ngưỡng theo SLO.
- Consumer lag tăng liên tục.
- Processor instance stopped hoặc không có ownership.
- Blob checkpoint write bị 403/timeout.
- Ownership thay đổi liên tục.
- Quarantine tăng nhanh.
- Event processing p95/p99 tăng bất thường.
- Event sắp hết retention trước khi consumer xử lý.

Mỗi alert cần owner, severity, dashboard, request/partition context và bước kiểm tra identity/network. Không đặt một ngưỡng số cố định cho mọi event hub; baseline phụ thuộc throughput, retention và yêu cầu nghiệp vụ.

## 15. Runbook khôi phục consumer

### 15.1. Consumer dừng hoàn toàn

1. Xác minh trạng thái deployment, pod/process, health và nguyên nhân shutdown.
2. Kiểm tra namespace, event hub, consumer group và checkpoint container trong cấu hình.
3. Xác minh runtime principal và role Event Hubs Data Receiver.
4. Xác minh Blob Data Contributor, DNS, firewall và private endpoint.
5. Kiểm tra ownership record và checkpoint age; không xóa metadata.
6. Khởi động một instance canary, xác nhận nhận ownership và đọc tiếp từ checkpoint.
7. Theo dõi lag, duplicate, DB và checkpoint trước khi scale đầy đủ.

### 15.2. Consumer chạy nhưng không tiến checkpoint

1. Kiểm tra handler có block, retry vô hạn hoặc transaction timeout.
2. Kiểm tra Blob write error, RBAC, token và network.
3. Kiểm tra callback có gọi updateCheckpoint sau khi xử lý thành công.
4. Xác minh không có exception bị nuốt hoặc checkpoint gọi trước commit.
5. Kiểm tra batch/async processing có làm checkpoint vượt event chưa hoàn tất không.
6. Chỉ thay đổi checkpoint theo quy trình recovery có phê duyệt.

### 15.3. Lag lớn và gần hết retention

1. Xác định ingestion rate và processing rate.
2. Kiểm tra partition nào nóng hoặc không có owner.
3. Kiểm tra downstream DB, thread pool, Blob checkpoint và network.
4. Giảm producer rate nếu có thể và tăng consumer capacity trong giới hạn partition.
5. Nếu cần replay/backfill, dùng archive/Capture hoặc nguồn dữ liệu được duy trì.
6. Ghi nhận khoảng dữ liệu không còn trong retention và xử lý theo yêu cầu nghiệp vụ.

### 15.4. Sau deploy, event bị xử lý lại

1. So sánh thời điểm deploy, shutdown và checkpoint gần nhất.
2. Kiểm tra ownership rebalance và checkpoint store.
3. Đo duplicate suppression trong inbox.
4. Xác minh side effect ngoài DB có idempotency key không.
5. Không reset checkpoint để loại bỏ duplicate; xử lý nguyên nhân và đối soát nghiệp vụ.

## 16. Kiểm thử recovery trên môi trường riêng

Dùng event hub, consumer group và Blob checkpoint container test riêng. Không reset checkpoint production, xóa ownership blob hoặc gây network failure trên tài nguyên thật chỉ để thử.

| Kịch bản | Cách thử | Kết quả mong đợi |
|---|---|---|
| Restart bình thường | Dừng/start processor có kiểm soát | Resume từ checkpoint |
| Crash sau DB commit trước checkpoint | Kill test process tại fault point | Event replay nhưng dedup ngăn side effect lặp |
| Crash trước DB commit | Kill trước commit | Event được đọc lại và xử lý |
| Blob checkpoint 403 | Dùng identity test thiếu data role | Checkpoint lỗi được quan sát; không báo tiến độ giả |
| Blob network unavailable | Chặn endpoint trong môi trường test | Processor báo lỗi, recovery sau khi mạng phục hồi |
| Instance scale-out | Tăng số instance cùng consumer group | Ownership phân phối lại |
| Instance scale-in | Dừng một processor | Partition được instance khác nhận sau coordination |
| Ownership expiry | Mô phỏng instance không cập nhật ownership | Instance còn lại có thể tiếp quản theo thời gian expiry |
| Duplicate event | Gửi lại cùng event ID | Một side effect nghiệp vụ |
| Poison event | Gửi payload sai schema | Quarantine hoặc dừng theo policy; không bỏ qua âm thầm |
| Checkpoint cũ hơn retention | Dùng test hub/retention phù hợp | Cảnh báo và xử lý initial position/archive rõ ràng |
| Replay từ consumer group mới | Đọc từ earliest trên test | Replay được kiểm soát và idempotent |
| Event out of order | Gửi aggregate version đảo thứ tự | Consumer phát hiện gap/stale event |
| Graceful shutdown | SIGTERM trong lúc xử lý | Dừng sạch hoặc replay an toàn |
| Cross-environment access | Identity dev truy cập checkpoint/event hub prod | RBAC/network từ chối |

Test nên thu thập event ID, partition ID, offset, sequence number, checkpoint timestamp, owner ID đã lọc và correlation ID để phân tích. Không log token hoặc raw payload nhạy cảm.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Checkpoint trước DB commit | Mất side effect sau crash | Commit trước, checkpoint sau |
| Chia sẻ checkpoint giữa workload logic khác nhau | Tiến độ/ownership xung đột | Consumer group riêng và quy ước store |
| Tạo checkpoint container mới mỗi deploy | Mất khả năng resume từ checkpoint cũ | Resource ổn định do IaC quản lý |
| Consumer group riêng cho từng pod | Mỗi pod đọc stream độc lập, nhân tải | Cùng workload dùng chung group |
| Nuốt exception rồi checkpoint | Event lỗi bị bỏ qua | Quarantine bền vững hoặc dừng xử lý có kiểm soát |
| Tin rằng ownership ngăn duplicate | Side effect lặp khi crash/rebalance | Inbox/idempotency ở database |
| Checkpoint quá thường xuyên | Tăng I/O/chi phí, giảm throughput | Đo và chọn batch/interval |
| Checkpoint quá thưa | Replay window lớn | Đặt replay budget và dedup |
| Xử lý bất đồng bộ rồi checkpoint vượt event | Bỏ qua event còn pending | Sequential hoặc contiguous completion watermark |
| Reset checkpoint production tùy tiện | Replay lớn và duplicate | Runbook, approval, canary và đối soát |
| Dùng initial position để reset mỗi restart | Đọc sai vị trí hoặc bỏ dữ liệu | Chỉ áp dụng initial position khi chưa có checkpoint |
| Không lưu archive nhưng yêu cầu replay dài hạn | Dữ liệu đã hết retention không khôi phục được | Capture/ADLS archive và retention riêng |

## 18. Checklist trước production

- **Identity:** Processor có Event Hubs Data Receiver; checkpoint store có Storage Blob Data Contributor đúng scope.
- **Resources:** Namespace, hub, consumer group và Blob container ổn định, tách theo môi trường/workload.
- **Ownership:** Các replica cùng group và cùng checkpoint store; load balancing và rebalance được quan sát.
- **Initial position:** Được cấu hình rõ; biết hành vi khi chưa có checkpoint.
- **Checkpoint:** Chỉ sau side effect bền vững; checkpoint frequency dựa trên replay budget.
- **Idempotency:** Event ID ổn định, unique constraint/inbox và side effect ngoài DB có cơ chế chống trùng.
- **Ordering:** Không checkpoint vượt event chưa hoàn tất; aggregate version được kiểm tra khi cần.
- **Retention:** Consumer có khả năng theo kịp; archive/Capture đáp ứng yêu cầu replay dài hạn.
- **Lifecycle:** Start/stop theo Spring lifecycle; termination grace period và graceful shutdown đã test.
- **Failure handling:** Có retry giới hạn, quarantine, runbook cho Blob/Event Hubs/network/identity failure.
- **Observability:** Ownership, checkpoint age, consumer lag, processing duration, duplicate và quarantine có metrics/alerts.
- **Recovery:** Đã test crash trước/sau commit, checkpoint failure, scale, replay và retention expiry.
- **Security:** Không lưu credential tĩnh trong source; log đã loại bỏ secret và payload nhạy cảm.
- **Cost:** Theo dõi Event Hubs tier/throughput, Blob checkpoint operations, retention, Capture, network và monitoring.

## 19. Tổng kết

**Checkpoint** lưu vị trí đọc đã được xử lý; **partition ownership** phối hợp processor instances trong cùng consumer group; **recovery** tiếp tục từ checkpoint sau crash, rebalance hoặc mất kết nối. Ba cơ chế phối hợp nhưng không tạo exactly-once transaction giữa Event Hubs, Blob Storage và database nghiệp vụ.

Khi vận hành Spring Boot với EventProcessorClient, hãy dùng checkpoint store bền vững, cùng consumer group cho các replica của một workload, commit side effect trước checkpoint, deduplicate theo event ID và kiểm soát replay trong retention. Kết hợp Managed Identity, RBAC tối thiểu, graceful shutdown, metrics theo partition và runbook recovery sẽ giúp consumer tiếp tục xử lý có kiểm soát khi instance, mạng hoặc dịch vụ gặp sự cố.

