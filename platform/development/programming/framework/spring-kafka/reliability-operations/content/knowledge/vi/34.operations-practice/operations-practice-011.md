# Viết runbook replay DLT trong Spring Kafka Reliability Operations

## 1. Mục tiêu: đưa bản ghi lỗi trở lại luồng xử lý một cách kiểm soát

Trong một ứng dụng Spring Kafka, consumer có thể gặp message không thể xử lý sau số lần retry cho phép. Thay vì chặn vĩnh viễn partition, ứng dụng thường chuyển message sang **Dead Letter Topic (DLT)** để lưu bằng chứng lỗi và cho phép xử lý lại sau. Một DLT có thể chứa hàng nghìn bản ghi đến từ nhiều nguyên nhân, nhưng **không phải bản ghi nào cũng nên replay ngay**.

Ví dụ:

~~~text
orders.events
     |
     v
@KafkaListener
     |
     +-- Xử lý thành công --> Database / downstream events
     |
     +-- Lỗi tạm thời --> Retry có giới hạn
                               |
                               +-- Phục hồi --> Tiếp tục xử lý
                               |
                               +-- Hết retry --> orders.events.DLT
                                                     |
                                                     v
                                              Triage + sửa lỗi
                                                     |
                                                     v
                                              Replay có kiểm soát
                                                     |
                                                     v
                                          Consumer xử lý lại + đối soát
~~~

**Replay DLT** là đọc lại một tập record đã được đưa vào DLT, sau đó phát hành chúng tới nơi xử lý đã được phê duyệt (thường là topic gốc hoặc một recovery topic). Nếu thực hiện không cẩn thận, thao tác này có thể tạo message trùng, đảo thứ tự nghiệp vụ, lặp lại poison message, gửi dữ liệu sai schema hoặc gây quá tải consumer.

Runbook là **hướng dẫn hành động cho người vận hành**: nêu điều kiện bắt đầu, quyền phê duyệt, thao tác chính xác, ngưỡng dừng, bằng chứng kiểm tra và cách phục hồi khi replay gặp lỗi. Đây không chỉ là tài liệu mô tả cách chạy một command.

Mục tiêu thực hành:

1. Phân loại nguyên nhân record vào DLT và chỉ chọn record có thể xử lý lại.
2. Khoanh vùng chính xác theo **topic, partition, offset**, không replay tràn lan.
3. Kiểm tra **payload, schema, key, headers, retention và thứ tự** trước khi gửi lại.
4. Đảm bảo **idempotency**, giới hạn tốc độ, khả năng dừng và audit.
5. Thực hiện **dry-run → canary → replay theo lô → đối soát**.
6. Biết điều gì được bảo đảm bởi Kafka, điều gì vẫn phải kiểm tra ở database và các external side effects.
7. Thiết kế bài kiểm thử và xử lý sự cố theo tiêu chí có thể quan sát.

Ví dụ dùng Spring Kafka theo phong cách **3.x**, Kafka Java clients và Java 17. Những API phụ thuộc phiên bản, cấu hình DLT và CLI cần được xác nhận theo release đang chạy trước khi vận hành production.

## 2. Phân biệt DLT, retry topic, quarantine và topic gốc

Một số hệ thống dùng cùng chữ viết tắt nhưng ngữ nghĩa khác nhau. Cần xác nhận kiến trúc thật trước khi chọn replay target.

| Thành phần | Vai trò | Có nên replay trực tiếp? |
|---|---|---|
| **Topic gốc** | Dòng event nghiệp vụ chính | Có thể, sau khi đã đánh giá contract consumer |
| **Retry topic** | Tạm giữ event để tự retry theo lịch/backoff | Thường do framework quản lý, không tự đẩy record vào nếu chưa rõ topology |
| **Dead Letter Topic** | Lưu event không xử lý được theo retry/recovery policy | Nguồn triage và replay có kiểm soát |
| **Recovery topic** | Topic riêng để xử lý lại qua pipeline đã được kiểm thử | Có thể là lựa chọn an toàn hơn khi cần phân luồng |
| **Quarantine store** | Kho chứa payload lỗi có phân quyền, audit và retention | Thường cần công cụ recovery riêng; không mặc định là Kafka topic |
| **Audit/replay ledger** | Ghi record nào đã được chọn/gửi/xác minh | Không phải nguồn event nghiệp vụ |

Trong Spring Kafka, DLT có thể được tạo thông qua **DeadLetterPublishingRecoverer**, **DefaultErrorHandler**, **@RetryableTopic** hoặc cơ chế tùy biến. Cách đặt tên và chọn partition không nhất thiết là topic gốc cộng hậu tố ".DLT" ở mọi dự án.

Ví dụ:

~~~text
orders.events
orders.events-retry-1000
orders.events-retry-10000
orders.events-dlt
~~~

Tên trên chỉ minh họa một topology có retry topics. Một dự án khác có thể dùng:

~~~text
orders.events
orders.events.DLT
~~~

**Không suy ra tên topic/partition chỉ từ thói quen.** Tìm cấu hình recoverer, destination resolver, listener container, topic provisioning và quyền ACL của deployment thật.

### Đã vào DLT có nghĩa gì?

Thường có nghĩa **consumer đã quyết định chuyển message sang tuyến xử lý lỗi** sau khi không giải quyết được theo policy. Nó **không chứng minh**:

- Payload đã được lưu nguyên vẹn như ban đầu trong mọi error path.
- Message đã được xử lý thành công một phần hay chưa.
- Producer DLT đã commit an toàn nếu hệ thống gặp crash đúng lúc recover.
- Offset của consumer gốc đã được commit trong mọi trường hợp.
- Lỗi hiện tại đã được sửa.
- Replay lại sẽ được xử lý đúng một lần.

Phải kiểm tra cả DLT record, consumer group offsets, database/output thực và cơ chế recoverer.

## 3. Một sự cố mẫu để xây runbook

Giả sử dịch vụ **orders-worker** dùng một consumer group đọc topic **orders.events** và ghi trạng thái đơn hàng vào database.

~~~text
Source topic:      orders.events
Dead letter topic: orders.events.DLT
Consumer group:    orders-worker-v1
Recovery target:   orders.events
Business key:      orderId
Event ID:          eventId
~~~

Trong một đợt mất kết nối database kéo dài, listener retry vài lần rồi đưa các message chưa xử lý được sang DLT. Sau khi database phục hồi, DLT vẫn chứa một số record.

Mục tiêu của đợt vận hành:

~~~text
Incident: INC-KAFKA-2026-015 (ví dụ)
Scope:    15 record đã được xác minh trong DLT
Cause:    transient database unavailability
Fix:      DB connections phục hồi, health và integration test đạt
Action:   replay có giới hạn sang recovery target đã duyệt
Exit:     đúng 15 event được xử lý hoặc ghi nhận từng ngoại lệ
~~~

Các tên, số lượng và incident ID là **dữ liệu minh họa**. Runbook thực tế phải được điền bằng evidence đọc từ môi trường, không dùng nguyên các offset/key giả trong lệnh production.

### Khác biệt giữa mục tiêu kỹ thuật và mục tiêu nghiệp vụ

**Mục tiêu kỹ thuật:** producer replay đã gửi record, broker ACK, consumer recovery nhận message.

**Mục tiêu nghiệp vụ:** đúng order được cập nhật; không duplicate payment, inventory reservation, email hoặc DB row; event hợp lệ không bị bỏ sót; dữ liệu cuối đạt reconciliation contract.

Chỉ khi mục tiêu nghiệp vụ đạt hoặc có exception được phê duyệt mới nên đóng runbook.

## 4. Nguyên tắc an toàn bắt buộc

Trước khi thao tác, cần thống nhất các bất biến:

1. **Không tự động replay toàn bộ DLT** khi vừa phát hiện lỗi.
2. **Không replay trước khi có bằng chứng lỗi gốc đã được sửa hoặc có đường xử lý mới phù hợp.**
3. **Không giả định DLT record chưa tạo side effect.** Handler có thể đã ghi DB/API trước khi lỗi.
4. **Không tin metadata từ message như một quyền chọn đích gửi.** Target topic cần allowlist của vận hành.
5. **Không đổi business key, eventId hoặc schema bừa bãi** khi replay.
6. **Không ghi payload nhạy cảm ra ticket/log/console**; dùng reference và storage có quyền truy cập.
7. **Không coi producer ACK là downstream processing success.**
8. **Không cam kết exactly-once chỉ nhờ replay tool.** Xem idempotency và kết quả commit mơ hồ.
9. **Không tự reset offsets của consumer group gốc** để thay thế replay DLT.
10. **Có phê duyệt, giới hạn lượng, giới hạn tốc độ, ngưỡng dừng và kế hoạch phục hồi**.
11. **Có audit bất biến** mô tả nguồn, đích, phạm vi, operator, thời điểm và outcome.
12. **Chỉ đụng tới production theo change/incident procedure đã được phê duyệt**.

DLT replay là thao tác có thể tạo **side effect mới lên hệ thống nghiệp vụ**. Quyền chạy phải tách khỏi quyền chỉ xem lag/metadata nếu môi trường có yêu cầu phân quyền nghiêm ngặt.

## 5. Thông tin bắt buộc trong phiếu chạy runbook

Mỗi lượt replay nên có một **Replay Operation ID** và record duyệt riêng:

| Trường | Nội dung cần ghi |
|---|---|
| incidentId | Incident hoặc change ticket |
| replayOperationId | ID duy nhất cho đợt replay; giữ nguyên khi retry command |
| service / owner | Service sở hữu consumer và người chịu trách nhiệm |
| environment / cluster | Production/staging và Kafka cluster alias |
| sourceDLT | Topic thực chứa failed records |
| targetTopic | Topic đã được cho phép phát lại |
| partitions / offsets | Danh sách chính xác hoặc range đã snapshot |
| inputWindow | Khoảng thời gian phát sinh sự cố, dùng để hỗ trợ triage |
| rootCause | Nguyên nhân đã xác định và bằng chứng |
| fixEvidence | PR/release/config/database health/test xác nhận đã sửa |
| schemaVersion | Loại dữ liệu và điều kiện compatibility |
| idempotencyPlan | Business key, eventId, dedup store và xử lý commit ambiguity |
| expectedCount | Số record được duyệt và lý do loại trừ |
| maxRate | Giới hạn messages/s, bytes/s hoặc in-flight requests |
| canaryScope | Số record nhỏ ban đầu, đã được lựa chọn rõ |
| stopConditions | Tiêu chí tự dừng hoặc operator dừng |
| approval | Người và thời điểm phê duyệt |
| reconciliation | Phép kiểm chứng dữ liệu cuối |
| auditLocation | Kho lưu bằng chứng an toàn |

Ví dụ một manifest vận hành:

~~~yaml
incidentId: INC-KAFKA-2026-015
replayOperationId: REPLAY-2026-015-A
environment: production
clusterAlias: prod-kafka-a
service: orders-worker
sourceTopic: orders.events.DLT
targetTopic: orders.events

selection:
  - partition: 0
    offsets: [3811, 3812]
  - partition: 2
    offsets: [9024]

expectedSelectedCount: 3
dryRunRequired: true
canaryCount: 1
maxMessagesPerSecond: 2
maxInFlight: 1

rootCause: DB_CONNECTION_TIMEOUT
fixEvidence: CHG-2026-092
idempotencyPolicy: orders-event-id-v2
schemaCompatibility: VERIFIED
approvalStatus: APPROVED
~~~

Đây là **manifest mô tả cho quy trình**, không phải định dạng mặc định mà Spring Kafka hay Kafka CLI có thể thực thi. Công cụ replay cần có schema/validator riêng và không tự suy diễn rằng chỉ cần thấy chữ APPROVED trong một file do người dùng cung cấp là đủ thẩm quyền.

### Khi cần khoanh vùng bằng range

Ví dụ chọn partition 0, offsets 3811 đến 3850: phải định nghĩa range là **inclusive** hay **exclusive**, chụp high watermark/last stable offset ở thời điểm chọn và ghi rõ số record thực đọc được. Offset trong Kafka không phải danh sách số liên tiếp của business records vì aborted transactions, retention và control records có thể tạo khoảng trống.

Với tình huống cần bảo đảm chắc chắn, một **danh sách tuple (topic, partition, offset)** đã duyệt thường an toàn hơn một range rộng chưa kiểm kê.

## 6. Pha 0 — Kích hoạt, trách nhiệm và điều kiện dừng

Trước khi mở công cụ replay:

1. Có incident/change ID và một operator được phân công.
2. Xác định đúng Kafka cluster, namespace, consumer group và môi trường.
3. Có quyền đọc DLT, quyền ghi target, quyền xem metric và quyền tra cứu business output.
4. Xác minh **không có replayer khác đang chạy cùng phạm vi**; dùng lock/lease hoặc một cơ chế coordination được triển khai.
5. Dừng auto-replay của chính phạm vi đó nếu nó sẽ đụng tới đợt manual replay.
6. Ghi lại trạng thái hệ thống trước thay đổi và ai sẽ xác nhận kết quả.
7. Chuẩn bị cơ chế dừng/suspend nếu consumer hoặc downstream phát sinh lỗi.

**Stop conditions** mẫu:

- Tỷ lệ processing error hoặc DLT mới tăng vượt ngưỡng đã phê duyệt.
- Phát hiện duplicate business side effect.
- Producer timeout hoặc transaction commit outcome không rõ vượt ngưỡng.
- Consumer lag tăng liên tục và không có throughput tương ứng.
- Schema/deserialization error xuất hiện trở lại.
- Database latency/connection pool gần quá tải.
- Số record gửi vượt selectedCount hoặc sai target topic/partition.
- Audit ledger hoặc nguồn metrics không hoạt động, khiến không thể xác nhận tiến độ.

Ngưỡng cụ thể phải căn theo service SLO và tải production. Không nên dùng một giá trị maxRate cố định cho mọi topic.

## 7. Pha 1 — Triage nguyên nhân record đi vào DLT

**Replay trước khi sửa lỗi gốc** thường chỉ đưa record quay lại DLT lần nữa.

| Failure category | Ví dụ | Hướng xử lý trước replay |
|---|---|---|
| **TRANSIENT_DEPENDENCY** | DB/API tạm unavailable, timeout | Xác nhận dependency đã ổn định và rate phù hợp |
| **RATE_LIMIT** | HTTP 429 từ downstream | Xử lý Retry-After, quota/backoff, giảm replay rate |
| **DESERIALIZATION** | Payload không parse được, schema không tương thích | Sửa serializer/schema hoặc dùng conversion/quarantine |
| **VALIDATION** | Thiếu trường, dữ liệu sai nghiệp vụ | Sửa dữ liệu theo quy trình có audit; không blindly replay |
| **APPLICATION_BUG** | NullPointerException hoặc logic sai | Deploy fix, regression test đúng payload |
| **AUTHORIZATION** | ACL, token hoặc cert không hợp lệ | Sửa quyền/chứng chỉ, kiểm tra scope |
| **POISON_MESSAGE** | Record luôn gây exception | Quarantine, patch, skip/reject theo contract |
| **OUT_OF_ORDER** | Event cũ đến sau trạng thái mới | Đánh giá version/sequence; có thể không được replay |
| **DUPLICATE** | Event đã được xử lý trước khi recoverer phát DLT | Đối soát và dedup, không tạo side effect lần hai |
| **UNKNOWN** | Không đủ exception/broker evidence | Dừng, không replay theo đoán |

**Không tin rằng cùng một DLT chỉ chứa một loại lỗi**. Có thể xảy ra nhiều incident khác nhau trong retention window. Một lệnh replay theo topic toàn phần có thể lẫn cả lỗi schema và lỗi nghiệp vụ vĩnh viễn.

### Nguồn dữ liệu triage

- Consumer logs/trace có **exception category**, eventId hoặc source offset.
- Headers do Spring Kafka recovery mechanism tạo.
- Metrics retry exhausted, DLT publish rate, rebalance.
- Consumer group committed offsets, deployment/version history.
- Schema registry/migration history.
- Database hoặc downstream receipt theo eventId.
- Replay audit từ các lần xử lý trước.

Không copy raw exception hoặc toàn bộ payload vào ticket có quyền truy cập rộng. Sử dụng reference được bảo vệ để mở dữ liệu khi cần.

## 8. Metadata DLT của Spring Kafka cần hiểu đúng

**DeadLetterPublishingRecoverer** có thể bổ sung các headers mô tả record gốc và exception:

- Original topic.
- Original partition và offset.
- Original consumer group trong những trường hợp/phiên bản hỗ trợ.
- Thời điểm record gốc.
- Exception class, message, stack trace hoặc metadata failure.

Trong code, Spring Kafka cung cấp các constant có tên liên quan **KafkaHeaders.DLT_ORIGINAL_TOPIC**, **DLT_ORIGINAL_PARTITION**, **DLT_ORIGINAL_OFFSET** và các headers exception; **tên/giá trị thực tế phụ thuộc version và recoverer config**.

Ví dụ cấu trúc quan sát được:

~~~text
DLT topic:        orders.events.DLT
DLT partition:    2
DLT offset:       9024
Kafka key:        O101
Original topic:   orders.events
Original partition: 2
Original offset:  6201
Failure category: DB_CONNECTION_TIMEOUT
~~~

Đây là sơ đồ metadata giả định, không phải raw dump headers. Một số header như original partition/offset là **dữ liệu nhị phân theo representation framework**, không được tự chuyển thành chuỗi UTF-8 rồi parse integer.

**DLT tuple** và **original tuple** là hai loại định danh khác nhau:

~~~text
Source record:
  orders.events / partition=2 / offset=6201

Failed copy:
  orders.events.DLT / partition=2 / offset=9024
~~~

Để chọn một DLT record **phải sử dụng tuple của chính DLT**. Original topic/partition/offset giúp truy vết record ban đầu nhưng không thay thế vị trí của bản sao trên DLT.

### Headers có thể thiếu hoặc chứa thông tin nhạy cảm

Không phải DLT record nào cũng có đủ headers. Nếu recoverer tùy biến không ghi original offset hoặc record đi qua nhiều retry topics, metadata có thể khác kỳ vọng.

Exception headers có thể chứa raw input, token, PII hoặc SQL details. Không phát tán chúng sang topic gốc một cách mặc định. Chỉ giữ lại application headers cần cho deserializer và nghiệp vụ; headers phục vụ riêng DLT/recovery cần được xử lý theo policy.

**Không sử dụng giá trị original-topic trong header như một destination tùy ý**. Message header là dữ liệu, không phải quyết định vận hành có thẩm quyền.

## 9. Pha 2 — Kiểm kê DLT và đóng băng phạm vi

Kiểm kê có thể thực hiện bằng công cụ nội bộ, AdminClient và consumer đọc metadata. Nên ghi:

- Topic/partition/offset của từng DLT record.
- Key có thể dùng để đối soát, theo chính sách bảo mật.
- EventId, schema ID/version hoặc type header nếu có.
- Original topic/partition/offset nếu đáng tin.
- Exception category và số lần replay trước đó.
- Record timestamp và trạng thái retention.
- Downstream state hiện tại: đã xử lý hay chưa.

### Kafka CLI để xem topic và group

Ví dụ các lệnh đọc-only:

~~~bash
# Xem partitions, replicas và ISR của DLT.
kafka-topics.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --describe \
  --topic orders.events.DLT

# Xem lag/offset của consumer group gốc.
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --describe \
  --group orders-worker-v1

# Xem policy retention / cleanup ở topic.
kafka-configs.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --describe
~~~

Đây là lệnh mẫu cho Kafka CLI tương thích. Trên cluster có SASL/TLS, phải đưa các tùy chọn cấu hình client đã được cấp quyền theo hướng dẫn của tổ chức; không hardcode password vào shell history.

**kafka-configs.sh --describe** không luôn hiển thị mọi default đang có hiệu lực. Muốn xác nhận chính xác retention/cleanup khi chưa override, cần xem effective config bằng AdminClient hoặc hạ tầng quản trị có quyền phù hợp.

### Không dump toàn bộ DLT bằng console consumer vào terminal chung

Phản mẫu:

~~~bash
# Không chạy mù ở production:
kafka-console-consumer.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --topic orders.events.DLT \
  --from-beginning
~~~

Lệnh này có thể in **payload nhạy cảm**, tạo lượng output lớn và khiến người vận hành lẫn nhiều incident. Nó cũng không tạo manifest chọn chính xác tuple và không tự đảm bảo header/schema được bảo toàn khi sau đó pipe sang producer.

Nên dùng công cụ read-only hỗ trợ **offset chính xác, giới hạn bytes, redaction và export metadata đã allowlist**.

### Snapshot của phạm vi

DLT là log đang thay đổi. Nếu chọn “mọi record hiện có” lúc bắt đầu, cần chụp **end offset/last stable offset** cho từng partition và định nghĩa giới hạn đọc. Nếu DLT tiếp tục nhận record mới trong lúc replay, chúng **không tự thuộc đợt replay cũ**.

Đối với topic có compaction hoặc retention thấp, selected record có thể biến mất trước lúc thao tác. Khi không đọc được offset đã duyệt, báo **SOURCE_NOT_AVAILABLE**, không tự lấy record kế tiếp để đủ số lượng.

## 10. Chọn replay target và hình thức xử lý

Có bốn chiến lược phổ biến:

| Chiến lược | Khi phù hợp | Rủi ro cần quản lý |
|---|---|---|
| **Replay về topic gốc** | Lỗi đã sửa, consumer gốc xử lý đúng, ordering cho phép | Đọc lại sau event mới, trùng side effect, loop về DLT |
| **Replay sang recovery topic** | Cần nhóm consumer riêng, giảm tải hoặc kiểm thử phiên bản mới | Routing/schema khác, phải rõ ai xử lý |
| **Transform rồi replay** | Payload cũ cần migration được duyệt | Thay đổi semantics; cần lưu bản gốc và phép biến đổi |
| **Quarantine/không replay** | Poison data, event hết hiệu lực, đã được xử lý, không đủ bằng chứng | Cần quyết định nghiệp vụ/audit để không mất dữ liệu âm thầm |

### Replay về topic gốc không phải “quay ngược thời gian”

Kafka append replayed record ở **offset mới**. Record được phát lại có thể xuất hiện sau những event mới hơn của cùng order.

~~~text
Original:
  order O101 v1 (failed -> DLT)
  order O101 v2 (processed)

Replay v1 later:
  order O101 v1 (new Kafka offset)
~~~

Nếu consumer cập nhật trạng thái theo thứ tự nhận mà không kiểm tra version, v1 có thể **ghi đè dữ liệu mới**. Với hệ thống event-sourced hoặc state machine, phải xét **event sequence/version, current business state và policy xử lý event cũ**.

### Khi cần giữ nguyên partition

Kafka producer có thể gửi vào partition cụ thể hoặc để partitioner chọn theo key. Việc hardcode **original partition** là nguy hiểm nếu:

- Topic gốc đã tăng/giảm số partition hoặc là target khác.
- Key serializer/partitioner thay đổi.
- Topic DLT partition layout khác topic gốc.
- Replay cần được phân phối lại vào recovery pipeline.

Runbook phải ghi rõ **partition routing policy**. Với key ổn định và topic gốc không thay cấu trúc, có thể để producer hash key theo partitioner đã được kiểm thử; nhưng không tự kết luận thứ tự lịch sử được khôi phục.

## 11. Schema, serializer và dữ liệu thô

Kafka record không tự mang tên Java class. Payload có thể là JSON, Avro, Protobuf, String hoặc binary protocol khác. Với **ErrorHandlingDeserializer**, thông tin lỗi deserialize và dữ liệu gốc có thể được đưa vào recovery flow theo cách phụ thuộc Spring Kafka version và cấu hình recoverer.

Điều quan trọng là **bản copy trên DLT không chắc có value đã deserialize thành object nghiệp vụ**. Đôi khi nên dùng **byte[]** để không làm dữ liệu biến đổi qua một serializer khác khi replay.

### Những điểm cần xác nhận

1. Key serializer và value serializer ở producer nguồn.
2. Format Kafka record **trong DLT**: bytes, String, JSON, Avro, v.v.
3. Schema ID hoặc type headers cần thiết để consumer đích deserialize.
4. Registry subject naming strategy: có thể phụ thuộc tên topic.
5. Consumer hiện tại có còn hỗ trợ schema của record cũ không.
6. Custom headers nào là business contract, header nào chỉ dùng bởi recoverer.
7. Có cần transform/migrate record hay không; ai phê duyệt việc đó.

Ví dụ đối với payload Avro dùng Schema Registry: copy byte[] có thể giữ schema ID trong payload, nhưng consumer đích vẫn cần quyền truy cập registry và schema compatibility phù hợp. Nếu **đổi topic** trong chiến lược replay, subject naming strategy có thể có implications; không tuyên bố byte[] copy luôn an toàn khi không biết format.

### Tombstone (null value) không phải record lỗi thông thường

Trong compacted topic, record có **value=null** có thể mang ý nghĩa xóa logical key. Nếu replay một tombstone cũ vào topic đang có state mới, nó có thể làm downstream xóa dữ liệu hiện tại.

Vì vậy, runbook phải phân loại riêng tombstone, xác nhận tính hợp lệ theo business sequence và có phê duyệt trước khi replay.

### Giữ headers theo allowlist

Có thể cần giữ **eventId**, **schemaVersion**, **content-type**, hoặc các type headers mà consumer thực dùng. Không gửi lại đầy đủ exception stack trace DLT headers. Cũng không thêm một header replay làm thay đổi parser của consumer nếu consumer đang whitelist nghiêm ngặt các headers.

## 12. Idempotency: điều kiện để replay an toàn

Kafka producer có thể nhận ACK khi append replayed record, nhưng trong một sự cố network lúc ACK bị mất, operator không biết send đã thành công hay chưa. Nếu chạy lệnh lại, một event có thể được phát hai lần.

~~~text
DLT replayer sends event E101
              |
              v
Kafka broker appended event
              |
              v
ACK lost / process crashes
              |
              v
Operator retries same replay request
              |
              v
Duplicate event E101 possible
~~~

Kafka producer idempotence giúp xử lý một số dạng producer retry trong cùng session và partition theo Kafka semantics, **không tự ngăn duplicate khi operator chạy lại một replay operation mới**.

### Business idempotency key

Ưu tiên dùng một định danh ổn định từ event gốc:

~~~text
eventId = E101
orderId = O101
operation = APPLY_ORDER_STATUS
~~~

Một bảng dedup ví dụ:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong transaction database của handler, insert dedup key và thay đổi nghiệp vụ phải được sắp đặt sao cho nếu transaction rollback, marker dedup không bị commit riêng. Unique key giúp chặn cùng eventId được áp dụng nhiều lần theo contract, nhưng phải có policy khi eventId bị thiếu hoặc payload của cùng ID khác nhau.

Không dùng **DLT offset** làm khóa business idempotency vì replay tạo một record mới với offset khác. Không sinh eventId mới cho cùng business event chỉ vì đang replay nếu mục tiêu là dedup cùng thao tác.

### Khi side effect nằm ngoài database

Nếu handler gọi:

- Payment API.
- Inventory reservation API.
- Email/SMS gateway.
- External REST service.

thì database dedup marker chưa chắc chặn được thao tác đã thành công nhưng mất response. Cần idempotency key ở chính external service, receipt lookup, outbox hoặc reconciliation/compensation phù hợp.

**Không phát lại trên production nếu nguy cơ nhân đôi tác động không có biện pháp kiểm soát đã được duyệt.**

## 13. Replay ledger: theo dõi từng record

Audit nên phân biệt **đã chọn**, **đã gửi**, **đã được Kafka ACK**, và **đã được consumer xử lý nghiệp vụ**.

Một schema minh họa:

~~~sql
CREATE TABLE dlt_replay_ledger (
    operation_id       VARCHAR(100) NOT NULL,
    source_topic       VARCHAR(250) NOT NULL,
    source_partition   INTEGER NOT NULL,
    source_offset      BIGINT NOT NULL,
    target_topic       VARCHAR(250) NOT NULL,
    event_ref          VARCHAR(150),
    state              VARCHAR(40) NOT NULL,
    attempt_count      INTEGER NOT NULL,
    target_partition   INTEGER,
    target_offset      BIGINT,
    updated_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (
        operation_id, source_topic, source_partition, source_offset
    )
);
~~~

Trạng thái gợi ý:

~~~text
SELECTED
    |
    v
VALIDATED
    |
    v
READY
    |
    v
SENDING
    |
    +--> SEND_FAILED / COMMIT_UNCONFIRMED
    |
    v
SENT_ACKED
    |
    v
DOWNSTREAM_VERIFIED
    |
    v
CLOSED
~~~

Đây là mô hình audit, không phải trạng thái mặc định của Spring Kafka. Khi update ledger và Kafka send dùng **hai resource transaction khác nhau**, có thể có khoảng hở:

~~~text
Kafka append thành công
       |
       v
Process crash trước khi ledger chuyển SENT_ACKED
~~~

Do đó ledger không biến replay thành exactly-once tự động. Nếu trạng thái mơ hồ, dùng **eventId/business reconciliation** để quyết định có retry hay không; trạng thái **COMMIT_UNCONFIRMED** cần được xử lý minh bạch.

### Giữ replayOperationId ổn định

Nếu operator chạy lại **chính đợt replay** sau failure, không tùy tiện sinh replayOperationId mới để bỏ qua ledger hoặc lock. Operation ID dùng cho audit; **business eventId** mới là khóa chống double application ở downstream.

## 14. Pha 3 — Preflight trước khi gửi một record

Preflight nên có cả kiểm tra hệ thống và dữ liệu.

### 14.1. Kiểm tra nguyên nhân đã được khắc phục

- Bản sửa code/config đã rollout đúng môi trường.
- Dependency database/API ổn định trong khoảng quan sát có ý nghĩa.
- Lỗi auth/ACL/schema đã được khắc phục.
- Regression test cho **chính failure category** đã đạt.
- Retry/DLT handler hiện tại không tạo vòng lặp mới.

### 14.2. Kiểm tra phạm vi và dữ liệu

- Có danh sách source DLT topic/partition/offset đã duyệt.
- Record còn tồn tại, chưa vượt retention/compaction.
- Event ID/key, schema và headers phù hợp với target.
- Tombstone, outdated event hoặc conflict được tách khỏi danh sách.
- Downstream state đã được kiểm tra đối với nguy cơ xử lý trùng.
- Có expected count và method đối soát, không dựa đơn thuần số offset.

### 14.3. Kiểm tra nguồn lực

- Broker/target topic có ISR và trạng thái hoạt động phù hợp.
- Consumer lag, lỗi, throughput và DB connection pool đủ headroom.
- Replay producer có quyền WRITE target; reader có quyền READ DLT.
- Backpressure/rate limit và stop switch hoạt động.
- Audit ledger và monitoring có thể ghi nhận.
- Không có đồng thời một auto-replay khác với cùng phạm vi.

Nếu một điều kiện quan trọng chưa xác minh được, gắn **BLOCKED/UNKNOWN** và không tự coi preflight PASS.

## 15. Pha 4 — Dry-run không phát hành Kafka output

Dry-run của một replay tool cần **không gọi producer.send**. Thay vào đó:

1. Đọc từng record theo tuple đã duyệt.
2. Xác nhận offset chính xác tồn tại.
3. Kiểm tra key/value lengths, loại payload và schema compatibility.
4. Xác thực routing policy và approved target.
5. Áp dụng filter headers trong bộ nhớ để xem headers nào sẽ giữ.
6. Tính số record eligible, blocked, unknown.
7. Xuất **manifest/preview an toàn**, không raw payload.

Ví dụ report:

~~~json
{
  "operationId": "REPLAY-2026-015-A",
  "mode": "DRY_RUN",
  "selected": 15,
  "eligible": 12,
  "blocked": 2,
  "unknown": 1,
  "willSend": false,
  "targetTopic": "orders.events",
  "reasonSummary": {
    "TRANSIENT_DEPENDENCY": 12,
    "OUTDATED_EVENT": 2,
    "SCHEMA_NOT_VERIFIED": 1
  }
}
~~~

**Không chuyển tất cả 15 record sang replay chỉ để đạt expectedCount=15.** Hai record cũ và một record chưa rõ schema phải theo quyết định riêng.

Dry-run nên có một dấu hiệu kỹ thuật chứng minh **producer invocation count = 0**; không chỉ một dòng log “dry run”.

## 16. Pha 5 — Canary replay với một số record được chọn

Sau khi dry-run và được duyệt:

1. Chọn một đến vài record đại diện, ưu tiên trường hợp dễ đối soát và có side effect an toàn.
2. Ghi nhận DLT tuple, business eventId và expected target behavior.
3. Replay với **maxInFlight=1** và rate thấp.
4. Chờ ACK của Kafka send/transaction commit theo công cụ.
5. Theo dõi consumer nhận record và handler outcome.
6. Query database/downstream receipt để đối soát business key.
7. Kiểm tra DLT mới không tăng do chính record canary.
8. Xác nhận không phát sinh duplicate hoặc event cũ ghi đè state mới.
9. Chỉ mở rộng nếu người chịu trách nhiệm xác nhận evidence đạt.

Nếu canary thất bại, **STOP**. Không tăng rate hay mở rộng phạm vi để “xem có ổn với nhiều dữ liệu hơn không”.

### Canary không đồng nghĩa “message đã được Kafka ACK”

Ví dụ:

~~~text
Replay producer:
  sent + broker ACK

Target consumer:
  deserialization FAILED
  retry exhausted
  DLT again
~~~

Send ACK chỉ chứng minh Kafka nhận bản phát lại theo cấu hình ACK; nó **không chứng minh handler thành công**. Canary chỉ PASS khi đối soát nghiệp vụ hoặc downstream receipt đạt yêu cầu.

## 17. Pha 6 — Replay theo lô có giới hạn

Sau canary, chia danh sách eligible thành những **batch nhỏ và xác định**:

~~~text
Eligible manifest: 12 records
    |
    +-- Batch 1: 3 records -> verify
    |
    +-- Batch 2: 3 records -> verify
    |
    +-- Batch 3: 3 records -> verify
    |
    +-- Batch 4: 3 records -> verify
~~~

Lưu ý:

- Giữ max rate, max in-flight và tổng số record tối đa.
- Dừng giữa các batch nếu error/DLT/lag/DB latency tăng.
- Ghi ledger theo source tuple và operationId.
- Không tự mở rộng sang DLT records đến **sau snapshot**.
- Nếu có thứ tự theo business key, xác định nhóm, sequence và routing policy.
- Không xoá record khỏi DLT sau khi gửi; retention/compaction là chính sách riêng.

### Backpressure quan trọng hơn tốc độ replay cao

Một hệ thống đang hồi phục từ outage có thể còn backlog trên topic gốc. Replay 100.000 record/s ngay lập tức có thể làm consumer, database hoặc external API quá tải lần hai.

Nên giới hạn **records/s và bytes/s** nếu payload chênh lệch lớn. Với downstream API có rate limits, điều chỉnh theo khả năng xử lý thực và tránh đẩy DLT recovery vào cùng cơ chế retry storm ban đầu.

### Kafka ordering

Ngay cả khi replay source offsets theo thứ tự tăng dần, chúng được append thành **offset mới** trên target. Nếu có producer khác đang hoạt động đồng thời, thứ tự giữa replay và live traffic không bảo đảm như lịch sử ban đầu.

Với event có sequence/version, consumer nên từ chối hoặc lưu riêng event cũ, không mặc định áp dụng bản replay vào state hiện tại.

## 18. Ví dụ công cụ replay một record bằng Spring Kafka

Phần này mô tả một **helper có scope nhỏ để phục vụ runbook**: đọc đúng một DLT record theo (partition, offset), optional dry-run, rồi phát sang target đã allowlist. Nó giúp minh họa thao tác chính, **không phải CLI production hoàn chỉnh**.

Thiết kế sử dụng:

- **ConsumerFactory<byte[], byte[]>** chuyên dùng cho DLT với ByteArrayDeserializer.
- **KafkaTemplate<byte[], byte[]>** chuyên dùng cho replay với ByteArraySerializer.
- Consumer **enable.auto.commit=false**, **isolation.level=read_committed**.
- **assign + seek** tới source partition và offset chính xác.
- **Không commit DLT consumer group offset** khi thao tác thủ công theo tuple.
- **Không lấy target từ original-topic header**.
- **Không copy toàn bộ exception headers** sang topic đích.
- **Không thay event ID hay key bytes**.

### 18.1. Replay request

~~~java
package com.example.kafka.operations;

public record ReplayRequest(
        String incidentId,
        String operationId,
        String sourceTopic,
        int sourcePartition,
        long sourceOffset,
        String targetTopic,
        boolean dryRun) {
}
~~~

Trong production, request phải đi qua **approval/authorization**, input schema validation, rate limit, lock và ledger. Không cho caller chỉ định target topic tùy ý qua HTTP query parameter.

### 18.2. Service giới hạn đúng một DLT tuple

~~~java
package com.example.kafka.operations;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class SingleRecordDltReplayer {

    private static final Set<String> ALLOWED_HEADERS =
            Set.of("eventId", "schemaVersion", "content-type",
                   "__TypeId__");

    private final ConsumerFactory<byte[], byte[]> consumerFactory;
    private final KafkaTemplate<byte[], byte[]> replayTemplate;

    public SingleRecordDltReplayer(
            ConsumerFactory<byte[], byte[]> consumerFactory,
            KafkaTemplate<byte[], byte[]> replayTemplate) {
        this.consumerFactory = consumerFactory;
        this.replayTemplate = replayTemplate;
    }

    public String replayOne(ReplayRequest request) throws Exception {
        validateRequest(request);

        TopicPartition source = new TopicPartition(
                request.sourceTopic(), request.sourcePartition());

        try (Consumer<byte[], byte[]> consumer =
                consumerFactory.createConsumer()) {

            // Manual assignment: không tham gia group balancing.
            consumer.assign(List.of(source));
            consumer.seek(source, request.sourceOffset());

            var records = consumer.poll(Duration.ofSeconds(5));
            ConsumerRecord<byte[], byte[]> selected = null;

            for (var record : records.records(source)) {
                if (record.offset() == request.sourceOffset()) {
                    selected = record;
                    break;
                }
            }

            if (selected == null) {
                throw new IllegalStateException(
                        "SOURCE_OFFSET_NOT_AVAILABLE");
            }

            // Không log key/value hoặc raw exception headers.
            if (request.dryRun()) {
                return "DRY_RUN_RECORD_VALIDATED";
            }

            Headers outgoingHeaders =
                    filterHeaders(selected.headers());
            outgoingHeaders.add(
                    "x-replay-operation-id",
                    request.operationId()
                            .getBytes(StandardCharsets.UTF_8));

            // partition=null: định tuyến theo key/partitioner.
            // timestamp=null: dùng timestamp do producer/broker chọn.
            ProducerRecord<byte[], byte[]> outgoing =
                    new ProducerRecord<>(
                            request.targetTopic(),
                            null,
                            null,
                            selected.key(),
                            selected.value(),
                            outgoingHeaders);

            var sendResult =
                    replayTemplate.send(outgoing)
                            .get(15, TimeUnit.SECONDS);

            // Thông tin ACK được trả cho audit layer.
            // KHÔNG coi đây là downstream business success.
            return "SENT_ACKED:"
                    + sendResult.getRecordMetadata().partition()
                    + ":"
                    + sendResult.getRecordMetadata().offset();
        }
    }

    private void validateRequest(ReplayRequest request) {
        if (request == null
                || request.operationId() == null
                || request.operationId().isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_REPLAY_OPERATION");
        }

        if (request.sourcePartition() < 0
                || request.sourceOffset() < 0) {
            throw new IllegalArgumentException(
                    "INVALID_SOURCE_POSITION");
        }

        // Ví dụ allowlist chặt cho một pipeline.
        if (!"orders.events.DLT".equals(request.sourceTopic())
                || !"orders.events".equals(request.targetTopic())) {
            throw new IllegalArgumentException(
                    "UNAPPROVED_TOPIC_MAPPING");
        }
    }

    private Headers filterHeaders(Headers sourceHeaders) {
        RecordHeaders result = new RecordHeaders();

        sourceHeaders.forEach(header -> {
            if (ALLOWED_HEADERS.contains(header.key())) {
                byte[] sourceValue = header.value();
                byte[] copy = sourceValue == null
                        ? null
                        : Arrays.copyOf(
                                sourceValue, sourceValue.length);
                result.add(header.key(), copy);
            }
        });

        return result;
    }
}
~~~

**Giới hạn có chủ đích của ví dụ:**

1. Một lần gọi chỉ chọn **một offset**, không tự đọc cả topic hoặc range.
2. Nếu offset không có trong dữ liệu hiện đọc được, helper **fail**, không thay bằng record tiếp theo.
3. Source và target bị giới hạn bằng literal allowlist. Dự án thật nên đọc approved mapping từ policy có kiểm soát.
4. Header allowlist **chỉ là ví dụ**, cần căn theo serializer/header contract của ứng dụng. Có hệ thống không dùng __TypeId__; có hệ thống cần headers khác.
5. Producer được inject phải là **dedicated byte-array KafkaTemplate** có security, bootstrap servers và ACK settings phù hợp; không tự dùng template nghiệp vụ đang serialize DTO.
6. Nếu replayTemplate được cấu hình là transactional, lời gọi send cần chạy trong transaction scope thích hợp; ví dụ giả định template gửi **không transactional** để tập trung vào bounded replay.
7. Dry-run ở helper chỉ kiểm tra offset có thể đọc được; full runbook còn cần schema, idempotency, downstream state và approval validation.
8. Ví dụ **không có audit ledger, distributed lock, rate limiter, timeout toàn đợt hoặc CLI parser**. Không đưa nguyên service này ra endpoint public để vận hành production.
9. Việc gọi send và chờ ACK không tạo giao dịch nguyên tử với replay ledger hoặc kết quả xử lý downstream.

### 18.3. Cấu hình dedicated byte-array client

Ví dụ cấu hình Kafka client properties (mang tính minh họa):

~~~properties
# DLT reader
key.deserializer=org.apache.kafka.common.serialization.ByteArrayDeserializer
value.deserializer=org.apache.kafka.common.serialization.ByteArrayDeserializer
enable.auto.commit=false
isolation.level=read_committed

# Replay producer
key.serializer=org.apache.kafka.common.serialization.ByteArraySerializer
value.serializer=org.apache.kafka.common.serialization.ByteArraySerializer
acks=all
enable.idempotence=true
~~~

ConsumerFactory và ProducerFactory phải được tạo từ **bootstrap servers và security properties được cấp từ cấu hình an toàn**. Không dùng SASL password hoặc token literal trong source. Với transactional DLT hoặc original data, read_committed giúp tránh replay các records thuộc transaction bị abort.

**Byte-array replay không tự chứng minh schema compatibility**. Nó chỉ tránh một bước deserialize/reserialize không cần thiết; business compatibility phải được kiểm chứng riêng.

## 19. Vì sao không dùng một @KafkaListener DLT tự phát lại mọi record?

Một mẫu code nguy hiểm:

~~~java
@KafkaListener(topics = "orders.events.DLT",
        groupId = "dlt-auto-replay")
public void replay(String payload) {
    kafkaTemplate.send("orders.events", payload);
}
~~~

Vấn đề:

- Listener có thể tiêu thụ **mọi record mới tới DLT** ngay cả khi chưa sửa lỗi.
- Không có selection theo incident/offset.
- Có thể mất key, headers và original serialization.
- Không có approval, dry-run, canary hoặc kiểm tra current business state.
- Dễ tạo vòng lặp **original → DLT → original → DLT**.
- Nếu offset của replay listener được commit nhưng send outcome không rõ, recovery khó đối soát.

Nếu thiết kế một DLT listener tự động có chủ đích, phải có **routing policy, retry budget, idempotency, rate limits, monitoring và hành vi stop/quarantine** được kiểm thử. Đối với **manual incident replay**, thường nên dùng công cụ one-shot theo manifest được duyệt hơn là listener luôn hoạt động.

## 20. DLT replay khác consumer group offset reset

Một số người vận hành muốn dùng consumer group offset reset để “đọc lại message gốc”. Đây là một thao tác khác hoàn toàn:

| Hành động | Phạm vi | Rủi ro |
|---|---|---|
| Replay một DLT tuple | Một bản ghi đã được chọn cụ thể | Duplicate tại target nếu replay lại |
| Replay danh sách DLT tuples | Tập lỗi đã duyệt | Cần audit và đối soát từng record |
| Reset group offset | Ảnh hưởng toàn bộ record kể từ vị trí offset mới trong partition/group | Rất nhiều message hợp lệ có thể bị xử lý lại |
| Tạo consumer group mới | Đọc theo offset reset policy của group mới | Có thể đọc từ đầu hoặc bỏ lỡ record |
| Republish từ backup | Phụ thuộc source snapshot | Có thể thiếu headers/key và lịch sử ordering |

**Không dùng kafka-consumer-groups --reset-offsets như cách thay thế trực tiếp cho DLT replay**. Nếu cần reset, đó phải là runbook riêng: dừng/điều phối group, snapshot offsets, dự đoán phạm vi record và xác minh dedup.

## 21. Tương tác giữa replay và Spring Kafka retry/DLT handler

Khi record phát lại vào target topic, nó đi qua consumer và error handler hiện hành. Nếu lỗi chưa được giải quyết:

~~~text
DLT replay
    |
    v
Original topic
    |
    v
Listener fails
    |
    +-- Retry 1
    +-- Retry 2
    +-- Recovery
    |
    v
DLT again
~~~

Nếu replayer lại tự động tiêu thụ DLT mới, hệ thống có thể rơi vào vòng lặp vô hạn. Cần:

- Chỉ replay selection đã snapshot.
- Theo dõi **DLT inflow** trong và sau replay.
- Giới hạn tổng số lần recovery theo eventId/operation, không chỉ theo Kafka offset.
- Gắn replay metadata an toàn nếu consumer chấp nhận và không làm hỏng schema.
- Quarantine record phát lại thất bại cùng **replayOperationId** để điều tra.
- Dừng khi số lỗi mới vượt threshold.

### @RetryableTopic và non-blocking retry

Một số ứng dụng dùng retry topics do @RetryableTopic tạo ra. Chúng có lịch/backoff và consumer containers riêng. Replay trực tiếp vào một retry topic trung gian có thể bỏ qua quy trình đã kiểm thử hoặc thay đổi attempt tracking.

**Ưu tiên target đã được thiết kế riêng cho recovery** (topic gốc hoặc recovery topic) thay vì tự đoán tên của một retry topic do framework quản lý. Phải đọc cấu hình hiện hành và kiểm thử một record trước.

## 22. Bảo đảm gửi Kafka và trường hợp commit không rõ

Với một producer nontransactional, phương thức send có thể được broker ACK theo acks policy. Nếu kết nối lỗi đúng lúc, ứng dụng có thể không biết record đã được append hay chưa.

Với transactional producer, thao tác gửi có thể ACK **trước khi transaction commit**. Consumer read_committed chỉ nhìn thấy dữ liệu đã commit, không thấy dữ liệu từ transaction bị abort.

~~~text
Transactional replay producer
    |
    +-- send A, send B
    |
    +-- send ACKs received
    |
    +-- commitTransaction
             |
             +-- committed -> visible to read_committed
             +-- aborted   -> not visible
             +-- ACK lost  -> outcome uncertain to client
~~~

**Replay ledger ở database không tự commit cùng Kafka transaction**. Nếu ứng dụng crash giữa hai tài nguyên, vẫn có khoảng hở. Cần chống trùng bằng eventId/business logic và đối soát.

Nếu cần phát một nhóm record cùng Kafka transaction, có thể dùng KafkaTemplate.executeInTransaction với ProducerFactory transactional và giới hạn nhóm nhỏ. Nhưng:

- Transaction nên ngắn, không giữ mở trong lúc chờ phê duyệt hay kiểm tra DB lâu.
- Cần xử lý producer fencing và transaction timeout.
- Transaction Kafka không bao phủ mọi side effect ngoài Kafka.
- Commit ACK ambiguity vẫn phải có recovery policy.

Không chọn transaction chỉ để gắn nhãn “exactly once” khi chưa có yêu cầu và test phù hợp.

## 23. Pha 7 — Đối soát sau replay

Sau mỗi canary/batch, phải đối soát **expected, sent, received, applied**:

~~~text
Selected for replay:        12
Blocked before replay:       3
Sent / broker ACK:          12
Downstream received:        12
Business applied:           10
Already processed (dedup):   2
Unexpected DLT re-entry:     0
Unresolved:                  0
~~~

Ví dụ trên cho thấy **business applied 10 không nhất thiết là lỗi** nếu hai events đã được xử lý trước và dedup đúng. Điều quan trọng là từng event có **kết quả nghiệp vụ hợp lệ**.

### Reconciliation theo business key

Ví dụ giả định bảng nghiệp vụ order_event_application có eventId duy nhất:

~~~sql
SELECT
    event_id,
    COUNT(*) AS applied_count
FROM order_event_application
WHERE batch_id = :batchId
GROUP BY event_id
HAVING COUNT(*) <> 1;
~~~

Với hệ thống có một số events được dedup vì đã xử lý trước, cần so **expected logical state** thay vì ép số lần xử lý vật lý bằng một.

Một phép kiểm tra anti-join ở hệ thống đối soát riêng:

~~~sql
SELECT e.event_id
FROM approved_replay_expected e
LEFT JOIN order_event_application a
       ON a.event_id = e.event_id
WHERE a.event_id IS NULL;
~~~

Các bảng là ví dụ. Trong production phải dùng schema/dataset thật đã được kiểm tra. Khi event không có tác động DB (ví dụ publish tiếp Kafka hoặc gửi notification), cần dùng downstream receipt, output topic hoặc audit tương đương.

### Kiểm tra theo source tuple

Một report nên phân biệt:

| Source DLT tuple | Decision | Kafka send | Downstream outcome | Final |
|---|---|---|---|---|
| p0/o3811 | Replay | ACK | Applied | VERIFIED |
| p0/o3812 | Replay | ACK | Deduplicated legitimately | VERIFIED |
| p2/o9024 | Block | Not sent | Schema unknown | BLOCKED |

Đừng xóa hàng BLOCKED khỏi report để khiến tỷ lệ hoàn thành trông đẹp hơn.

## 24. Xử lý lỗi trong lúc replay

### 24.1. Producer send thất bại trước ACK

Hành động:

1. Stop batch đang chạy.
2. Ghi source tuple và failure category, **không raw payload**.
3. Kiểm tra broker/ACL/network/timeout.
4. Đánh giá ACK outcome có thực sự rõ hay không.
5. Reconcile với target bằng eventId nếu outcome mơ hồ.
6. Chỉ retry theo approved idempotency policy.

### 24.2. Record đã gửi nhưng downstream lại vào DLT

Hành động:

1. Stop tiếp tục gửi cùng loại record.
2. Lấy DLT tuple mới và liên kết với eventId/operationId.
3. Phân loại lỗi mới; không mặc định vẫn là lỗi gốc.
4. Nếu là regression của bản sửa, rollback/canary stop theo runbook deployment.
5. Quarantine record, bổ sung test và chỉ replay tiếp sau khi có fix.

### 24.3. Audit ledger bị lỗi

Nếu Kafka send đã thành công nhưng update ledger thất bại, đánh dấu trạng thái **UNCONFIRMED** trong incident log/cơ chế recovery phù hợp. Không chạy lại lệnh để “cho ledger có ACK” trước khi kiểm tra event đã hiện diện và downstream đã xử lý chưa.

### 24.4. Consumer lag tăng mạnh

Giảm hoặc dừng replay rate, kiểm tra consumer concurrency, poll interval, retry, DB latency và nhóm partition đang nghẽn. Đừng tăng consumer concurrency vô hạn nếu partition count, DB connections hoặc ordering không cho phép.

### 24.5. Replay nhầm topic hoặc sai schema

Dừng ngay, ghi lại target partition/offset đã gửi, đánh giá những consumer nào đã đọc và side effects nào đã xảy ra. Kafka log append không có thao tác “rollback tất cả record đã publish” một cách đơn giản. Cần plan xử lý downstream/compensation và phối hợp owner topic.

## 25. Không có nút undo cho Kafka replay đã commit

Nếu record replay đã xuất hiện ở target topic, **xóa thông tin trong replay ledger không xóa record Kafka**. Việc “thu hồi” cần phụ thuộc vào hợp đồng nghiệp vụ:

- Gửi compensating event được định nghĩa trong domain.
- Đánh dấu event đã bị supersede/invalidated theo schema hỗ trợ.
- Hoàn tác DB state bằng transaction nghiệp vụ được phê duyệt.
- Tra receipt và bù trừ external side effects.
- Dừng consumer để khoanh vùng, đánh giá phạm vi đã xử lý.

Không phát một tombstone hoặc reset offsets tùy tiện để làm “undo”; tombstone có semantics riêng với compacted topics, còn offset reset có thể replay thêm nhiều event khác.

### Recovery sau khi dừng giữa chừng

Nếu operator dừng replay sau năm record trong mười record:

~~~text
Approved: 10
SENT_ACKED: 5
DOWNSTREAM_VERIFIED: 4
UNCONFIRMED: 1
NOT_SENT: 5
~~~

Trước khi resume:

1. Reconcile một record UNCONFIRMED.
2. Kiểm tra bốn record VERIFIED vẫn đạt business state.
3. Chỉ gửi những record chắc chắn NOT_SENT, hoặc dùng idempotent replay cho record cần retry.
4. Giữ nguyên operationId và selection; không mở rộng scope ngẫu nhiên.
5. Kiểm tra lại điều kiện preflight, canary nếu có thay đổi môi trường.

## 26. DLT retention và bảo toàn bằng chứng

Kafka topic có thể được cấu hình **retention.ms**, **retention.bytes** hoặc **cleanup.policy**. DLT không phải kho lưu trữ vô hạn.

Rủi ro:

- Record hết retention trong lúc đợi fix.
- Topic compacted làm mất bản DLT cùng key.
- Partition/broker thay đổi và offset cũ không còn đọc được.
- Event chứa PII cần retention/deletion policy nghiêm ngặt.

Quy trình:

1. Từ lúc mở incident, đánh giá **thời gian còn lại trước retention**.
2. Nếu chưa thể sửa trong retention window, cân nhắc sao lưu **có kiểm soát** sang quarantine object store, mã hóa và phân quyền.
3. Lưu checksum/metadata nguồn để kiểm chứng, nhưng không đưa secret/PII vào ticket.
4. Không tự kéo dài DLT retention trên production mà không xét storage capacity, security và approval.
5. Khi dữ liệu đã biến mất, báo **SOURCE_EXPIRED**; không bịa record hoặc tự replay một offset khác.

**Kafka log offset không phải mã định danh tồn tại vĩnh viễn.** Với retention/compaction, cùng vị trí có thể không còn business record để đọc; không nên lưu mỗi offset rồi bỏ hết business event reference và evidence khác.

## 27. Bảo mật và quyền hạn của replay tooling

DLT có thể chứa dữ liệu lỗi, payload thô, exception stack trace hoặc security-sensitive headers. Công cụ vận hành phải:

- Xác thực operator và authorize theo cluster/source/target.
- Chỉ cho target từ **mapping allowlist**, không nhận topic bất kỳ từ payload.
- Dùng Kafka principal có quyền tối thiểu: đọc DLT và ghi target được duyệt.
- Không in raw payload/headers exception vào console, Slack hoặc ticket.
- Mã hóa secrets, không ghi credential trong command history.
- Bảo vệ manifest, audit/ledger, replay snapshots và quarantine store.
- Có hai-person approval nếu nghiệp vụ yêu cầu.
- Không biến tool thành public API có thể bị gọi tùy ý.
- Bảo vệ bằng timeout, batch limit, max bytes và rate limit.
- Định nghĩa retention và quyền truy cập đối với replay artifacts.

**Không dùng plain hash của email/phone làm bằng chứng ẩn danh mạnh.** Nếu cần correlation theo người hoặc business object, dùng reference/ID được phê duyệt và cơ chế pseudonymization thích hợp.

### Điều gì được log?

~~~text
event=dlt.replay.started
incidentId=INC-KAFKA-2026-015
operationId=REPLAY-2026-015-A
sourceTopic=orders.events.DLT
targetTopic=orders.events
selectedCount=12
rateLimit=2

event=dlt.replay.record.acked
operationId=REPLAY-2026-015-A
sourcePartition=0
sourceOffset=3811
targetPartition=1
targetOffset=92010

event=dlt.replay.stopped
operationId=REPLAY-2026-015-A
reasonCode=DOWNSTREAM_ERROR_RATE_EXCEEDED
~~~

Các giá trị chỉ mang tính minh họa. Không log raw key, value, access token, header Authorization hay exception message chưa được phân loại an toàn.

## 28. Metrics và dashboard theo dõi đợt replay

Nên quan sát **replay metrics** cùng **consumer/downstream metrics**:

| Metric / tín hiệu | Mục đích |
|---|---|
| Selected/eligible/blocked counts | Phạm vi thực tế, dữ liệu chưa đủ điều kiện |
| Replay send attempts | Tốc độ và số lần gửi |
| Replay ACK success/failure | Lỗi producer hoặc broker |
| Unconfirmed send outcomes | Trường hợp cần reconcile trước retry |
| Downstream applied/deduplicated | Kết quả nghiệp vụ |
| DLT inflow mới | Phát hiện loop hoặc fix chưa đạt |
| Consumer lag | Backpressure và khả năng theo kịp |
| Retry/exception rate | Lỗi mới ở target consumer |
| DB/API latency, connection pool | Downstream capacity |
| Producer request latency/timeout | Kafka health và publish overhead |
| Replay age/time-to-recovery | SLA vận hành |

Với Prometheus, metric names có thể do ứng dụng tự định nghĩa, ví dụ:

~~~text
dlt_replay_selected_total
dlt_replay_sent_total
dlt_replay_unconfirmed_total
dlt_replay_downstream_verified_total
dlt_replay_reentry_total
~~~

Đây là tên gợi ý, **không phải metric mặc định của Spring Kafka**. Tránh gắn eventId, orderId hoặc operationId tùy ý vào labels có cardinality cao; đưa các ID đó vào audit/log có phân quyền.

### Dấu hiệu cần stop

Một số chỉ số có thể tăng trong lúc replay mà vẫn là bình thường (ví dụ lag tăng ngắn hạn khi producer gửi nhiều). Runbook phải có **threshold và thời gian quan sát** để tránh dừng tùy tiện hoặc bỏ qua sự cố. Với nghiệp vụ có side effect nhạy cảm như payment, một duplicate đã xác nhận có thể đủ để dừng ngay.

## 29. Kiểm thử runbook trước khi vận hành production

Chạy replay trong test/staging với **EmbeddedKafka hoặc Testcontainers** và một database test có schema đại diện.

### Mô hình test

~~~text
Test producer -> orders.events
                      |
                      v
               Listener fails
                      |
                      v
                DLT publisher
                      |
                      v
              orders.events.DLT
                      |
                      v
              Dry-run / replay tool
                      |
                      v
              orders.events / recovery
                      |
                      v
              Fixed listener + test DB
~~~

Nên có cả test dùng DLT thật từ **Spring Kafka recoverer** và test riêng cho tool đọc DLT theo tuple. Nếu chỉ tự tạo một DLT record giả có key/value đúng, test có thể bỏ qua header khác biệt khi deserialization error xảy ra thực tế.

### Ma trận test tối thiểu

| ID | Kịch bản | Điều cần chứng minh |
|---|---|---|
| RP-01 | Transient DB error, đã fix | Replay một record → downstream xử lý đúng |
| RP-02 | Dry-run | Không có producer send; preview hợp lệ |
| RP-03 | Chọn chính xác offset | Không gửi record nằm ngoài selection |
| RP-04 | Offset không còn tồn tại | Fail SOURCE_OFFSET_NOT_AVAILABLE |
| RP-05 | Wrong target mapping | Reject trước send |
| RP-06 | Deserialization failure | Preserve bytes/headers cần thiết hoặc block |
| RP-07 | Key null | Có partition policy và đánh giá ordering |
| RP-08 | Tombstone | Không replay khi chưa có authorization |
| RP-09 | Record đã được xử lý | Business dedup chặn duplicate side effect |
| RP-10 | Kafka ACK lost | Outcome được reconcile; không blind resend |
| RP-11 | Replayed record lại vào DLT | Stop theo threshold và trace operation |
| RP-12 | Sender crash sau ACK trước ledger update | Resume không làm duplicate business effect |
| RP-13 | Source/target có partition count khác | Routing policy xác định, không tin original partition |
| RP-14 | Old event sau event mới | Version/sequence không ghi đè state mới |
| RP-15 | Payload/schema cũ | Consumer đích hỗ trợ hoặc quarantine |
| RP-16 | Multiple operators | Lock ngăn chạy trùng selection |
| RP-17 | Rate limit/backpressure | Tool không vượt threshold |
| RP-18 | DLT retention hết hạn | Báo source expired, không lấy nhầm record |
| RP-19 | Transaction abort ở source | read_committed không replay aborted data |
| RP-20 | Credential/ACL sai | Không log secret và không gửi nhầm |
| RP-21 | Replay partial rồi resume | Ledger/audit và outcome cuối nhất quán |
| RP-22 | Replay target event có side effect API | Idempotency key ngăn side effect trùng |

### Integration test với Spring Kafka

Một test có thể dùng:

~~~java
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.events", "orders.events.DLT"},
    brokerProperties = {
        "offsets.topic.replication.factor=1",
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1"
    }
)
class DltReplayIntegrationTest {

    // Test context có KafkaTemplate, consumer factories,
    // DLT recoverer, listener và database test.
    //
    // 1. Gửi input E101.
    // 2. Ép listener fail tới khi DLT nhận record.
    // 3. Kiểm tra DLT tuple/key/headers theo contract.
    // 4. Chạy dry-run: không có output mới.
    // 5. Sửa mock dependency.
    // 6. Replay đúng một tuple đã duyệt.
    // 7. Chờ downstream receipt với timeout.
    // 8. Query DB: E101 áp dụng đúng một lần.
    // 9. Không có DLT re-entry ngoài dự kiến.
}
~~~

Đây là **skeleton** của integration test; cần thêm Spring test context, dependencies, imports, setup, consumer assignment và assertions cụ thể theo phiên bản đang dùng. Nó mô tả bằng chứng cần tạo, không phải mã tự chạy độc lập.

### Không dùng sleep để kết luận replay thành công

Ví dụ phản mẫu:

~~~java
replayTool.replayOne(request);
Thread.sleep(500);
assertEquals(1, outputCount);
~~~

Test như vậy có thể flaky vì broker, consumer assignment, retry và database latency. Dùng polling có deadline hoặc Awaitility để chờ điều kiện cụ thể:

~~~java
await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertEquals(1, countAppliedEvent("E101")));
~~~

Đoạn này giả định **Awaitility** và các helper assertions đã được thêm vào test dependencies. Kiểm thử cần assert **event đúng được xử lý**, không chỉ một counter chung tăng lên.

## 30. Hai tình huống thực hành đối lập

### Tình huống A — Lỗi tạm thời từ database

**Hiện tượng:** order event E101 nằm ở DLT vì DB connection timeout.

**Phân tích:** payload/schema hợp lệ; consumer retry hết; DB đã phục hồi; output chưa ghi theo eventId; dedup logic sẵn sàng.

**Quy trình:**

1. Tạo incident và approved manifest cho đúng DLT tuple.
2. Kiểm tra database health và chạy thử một fixture tương tự.
3. Dry-run xác nhận key/value/schema và target.
4. Canary replay E101 với rate thấp.
5. Chờ Kafka ACK, kiểm tra consumer xử lý.
6. Query database theo eventId; kết quả đúng một logical application.
7. Theo dõi DLT inflow, lag và DB health.
8. Cập nhật ledger thành DOWNSTREAM_VERIFIED, đóng incident sau reconciliation.

**Bài học:** có thể replay sau khi **nguyên nhân đã sửa**, với idempotency và đối soát rõ ràng.

### Tình huống B — Payload không tương thích schema

**Hiện tượng:** DLT record E202 có payload từ serializer cũ, consumer mới không parse được.

**Phân tích:** replay nguyên bytes về topic gốc sẽ gây cùng lỗi. Cần xác định version schema, migration path và compatibility.

**Quy trình:**

1. Dừng replay; đánh dấu E202 BLOCKED_SCHEMA.
2. Lấy bản gốc và metadata qua công cụ có phân quyền.
3. Xác định parser/schema version cũ, quy tắc biến đổi nếu được phép.
4. Tạo migration function có unit/integration tests dùng payload synthetic.
5. Đánh giá liệu payload sau migrate còn giữ **same business event identity** hay tạo event version mới theo policy.
6. Được phê duyệt mới phát hành sang recovery topic hoặc target tương thích.
7. Đối soát output cuối và giữ audit liên kết source tuple → transformed record.

**Bài học:** không phải mọi DLT là transient failure; một số cần **data repair workflow** chứ không phải thao tác resend.

## 31. Runbook copy-ready cho ca vận hành

Mẫu dưới đây có thể điền cho một đợt replay cụ thể.

### Thông tin

~~~text
Runbook: Spring Kafka DLT Replay
Incident/Change ID: __________________
Environment/Cluster: _________________
Service/Consumer Group: ______________
Source DLT: __________________________
Target Topic: ________________________
Replay Operation ID: _________________
Selected Tuple Manifest: _____________
Expected Eligible Count: _____________
Root Cause Category: _________________
Fix Evidence: _______________________
Schema Compatibility Evidence: _______
Idempotency / Receipt Strategy: ______
Approval / Owner: ___________________
Rate Limit / Max In Flight: __________
Stop Conditions: ____________________
Audit Location: _____________________
~~~

### Các pha thực hiện

| Pha | Thao tác | Gate hoàn thành |
|---|---|---|
| 0. Authorization | Xác định owner, scope, approval và lock | APPROVED |
| 1. Root-cause triage | Phân loại lỗi và xác nhận fix | FIX_VERIFIED |
| 2. Inventory | Chụp DLT tuples, schema, status nghiệp vụ | SCOPE_FROZEN |
| 3. Preflight | Kiểm tra routing, ACL, retention, capacity, dedup | PREFLIGHT_PASS |
| 4. Dry-run | Đọc selection, không gửi Kafka | NO_SEND / ELIGIBLE_CONFIRMED |
| 5. Canary | Replay số record ít và đối soát | CANARY_VERIFIED |
| 6. Bounded replay | Replay batch/rate nhỏ, monitor stop conditions | SEND_COMPLETE_OR_STOPPED |
| 7. Reconciliation | So expected, ACK, applied, dedup, DLT re-entry | DOWNSTREAM_VERIFIED |
| 8. Closure | Lưu evidence, blocked items, action và lessons | CLOSED |

Nếu bất kỳ gate Critical nào FAIL hoặc UNKNOWN, **không tự nhảy sang pha sau**. Với thao tác đã phát record Kafka, recovery phải dựa vào state bền vững và idempotency; không có rollback tự động chỉ bằng việc đổi status trong ticket.

### Quy tắc báo cáo kết quả cuối

~~~text
STATUS: COMPLETED / PARTIAL / BLOCKED / FAILED
OPERATION_ID:
SOURCE_DLT:
TARGET_TOPIC:
SELECTED_COUNT:
ELIGIBLE_COUNT:
BLOCKED_COUNT:
SENT_ACKED_COUNT:
DOWNSTREAM_VERIFIED_COUNT:
DEDUPLICATED_COUNT:
DLT_REENTRY_COUNT:
UNCONFIRMED_COUNT:
UNRESOLVED_TUPLES:
APPROVER:
EVIDENCE_LINKS:
FOLLOW_UP:
~~~

**COMPLETED** chỉ khi các record eligible đã có **downstream outcome hợp lệ** và các record blocked được ghi nhận rõ, không phải khi số Kafka sends bằng selectedCount.

## 32. Những sai lầm thường gặp

**Replay toàn bộ DLT để “dọn sạch”.** Một topic có thể chứa nhiều loại lỗi và incident; replay tất cả có thể tạo outage lần hai.

**Không sửa nguyên nhân gốc trước replay.** Message tiếp tục rơi lại DLT, tạo vòng lặp.

**Nhầm DLT offset với original offset.** Hai topic có offsets độc lập.

**Tin header original-topic như một routing command.** Headers là dữ liệu, không thay thế approved target allowlist.

**Pipe console consumer sang console producer.** Có thể mất key, headers, schema metadata và audit; dễ lộ payload.

**Coi ACK send là xử lý nghiệp vụ thành công.** Consumer có thể tiếp tục fail/deserialization error.

**Sinh eventId mới cho mỗi attempt.** Làm mất cơ sở business dedup.

**Tin rằng Kafka idempotent producer chặn mọi replay duplicate.** Chạy tool hai lần có thể phát cùng event hai lần; downstream phải idempotent.

**Copy mọi DLT exception headers.** Có thể mang stack trace, PII hoặc dữ liệu không còn phù hợp với consumer gốc.

**Không xem schema/serializer.** Copy bytes không đủ nếu consumer target không đọc được.

**Bỏ qua tombstone và out-of-order events.** Replay event cũ có thể xóa/ghi đè state mới.

**Cố giữ original partition mà không kiểm tra target partitions.** Có thể sai partition hoặc ordering khi topic đổi.

**Reset consumer group offsets để thay thế replay.** Là thao tác phạm vi rộng, có thể gây duplicate/skip.

**Chạy replay tốc độ lớn khi hệ thống vừa hồi phục.** Dễ làm DB/API tiếp tục quá tải.

**Dùng DLT listener tự động luôn bật mà không có gate.** Có thể liên tục phát lại poison messages.

**Đánh dấu ledger thành SENT trước khi broker xác nhận.** Gây sai trạng thái, khó phục hồi.

**Gửi lại ngay khi ACK bị mất.** Outcome có thể đã thành công; cần reconcile.

**Không lưu những record bị block.** Làm incident báo hoàn thành giả dù vẫn còn thiếu dữ liệu.

**Không giữ evidence khi DLT retention sắp hết.** Có thể mất khả năng điều tra/replay.

**Không có kế hoạch dừng hoặc compensation.** Kafka append đã commit không có nút undo đơn giản.

**Dùng raw payload và exception trong log runbook.** Có nguy cơ rò PII và secrets.

## 33. Nguyên tắc vận hành cốt lõi

Replay DLT đáng tin cậy không phải thao tác **đọc lại rồi gửi Kafka**. Đó là một workflow có phạm vi rõ và các cổng kiểm soát:

1. **Triage**: chứng minh vì sao record lỗi và liệu lỗi đã được sửa chưa.
2. **Select**: đóng băng danh sách DLT tuples, không tự kéo thêm dữ liệu ngoài incident.
3. **Validate**: kiểm tra business state, schema, key, headers, target và authorization.
4. **Dry-run**: xác nhận khả năng đọc/định tuyến mà **không publish**.
5. **Canary**: gửi rất ít record, xác minh downstream outcome thực.
6. **Bounded replay**: rate limit, batch limit, audit và stop switch.
7. **Reconcile**: kiểm tra đúng business state, dedup, DLT re-entry và unresolved cases.
8. **Close**: lưu bằng chứng và follow-up; không tự coi ACK là COMPLETED.

Khi runbook mô tả **chính xác ai được phép làm gì, trên record nào, với điều kiện gì, và bằng chứng nào xác nhận thành công**, đội vận hành có thể phục hồi các message bị đưa vào DLT mà không vô tình tạo thêm mất dữ liệu, duplicate side effects hoặc một vòng lặp retry mới. Đó là tiêu chuẩn của một quy trình **Spring Kafka Reliability Operations** có thể kiểm thử và sử dụng an toàn trong sự cố thực tế.
