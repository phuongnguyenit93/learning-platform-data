# Mã hóa khi lưu trữ và giới hạn của Kafka đối với xóa dữ liệu cá nhân

Kafka là một distributed commit log: record được ghi nối tiếp vào partition, nhân bản giữa broker và giữ lại theo retention hoặc cleanup policy. Thiết kế này phù hợp với event streaming và replay, nhưng tạo ra thách thức khi hệ thống cần xóa dữ liệu cá nhân theo yêu cầu của chủ thể dữ liệu.

Cần phân biệt hai mục tiêu:

- **Encryption at rest:** bảo vệ dữ liệu khi nằm trên disk, volume, snapshot hoặc backup.
- **Data erasure:** làm cho dữ liệu thuộc một cá nhân không còn được truy cập hoặc khôi phục theo chính sách đã cam kết.

Mã hóa disk không tự động xóa một record. Tombstone trong compacted topic cũng không phải thao tác xóa vật lý tức thời. Muốn đáp ứng yêu cầu xóa, phải theo dõi dữ liệu qua topic, replica, backup, state store, dead-letter topic và mọi hệ thống downstream.

Kafka cung cấp retention, compaction, tombstone và API xóa log theo offset. Các cơ chế này có phạm vi cụ thể; chúng không phải API xóa tùy ý một event ở mọi nơi. Kiến trúc cần kết hợp data minimization, mã hóa, quản lý khóa, định danh dữ liệu và quy trình xóa xuyên hệ thống.

## 1. Dữ liệu Kafka tồn tại ở những đâu?

Một event sau khi producer gửi vào Kafka có thể xuất hiện ở nhiều nơi:

- Log segment và index trên broker leader.
- Replica của partition trên các broker khác.
- Page cache, filesystem cache và thiết bị lưu trữ.
- Snapshot hoặc backup của volume/broker.
- Topic retry và dead-letter topic (DLT).
- Repartition/changelog topic của Kafka Streams.
- Local state store trên disk của Streams application.
- Kafka Connect sink và hệ thống đích.
- Consumer database, search index, data lake, cache hoặc object storage.
- Log ứng dụng, tracing, audit và bản export phục vụ hỗ trợ.

~~~mermaid
flowchart TD
    P["Producer"] --> T["Kafka topic / partition"]
    T --> R["Broker replicas"]
    T --> C["Consumer"]
    C --> D["Database / Search / Data lake"]
    T --> X["Kafka Connect"]
    X --> E["External systems"]
    T --> S["Kafka Streams"]
    S --> L["Local state store"]
    S --> H["Changelog / repartition topics"]
    T --> B["Backup / snapshot / archive"]
    T --> Q["Retry / DLT"]
~~~

Xóa record khỏi một topic không tự xóa các bản sao đã được consumer ghi vào database, file export hoặc data lake. Một quy trình xóa hoàn chỉnh phải xác định tất cả nơi dữ liệu được sao chép và owner chịu trách nhiệm xóa tại từng nơi.

## 2. TLS in transit khác encryption at rest

TLS bảo vệ dữ liệu khi client và broker truyền thông qua mạng. Nó không tự mã hóa các log segment được ghi trên disk.

| Cơ chế | Bảo vệ | Không tự giải quyết |
|---|---|---|
| TLS / SSL | Dữ liệu trên đường truyền | Log segment, backup hoặc local state đã lưu |
| SASL_SSL | TLS transport và SASL authentication | Encryption at rest |
| Disk/volume encryption | Dữ liệu trên thiết bị lưu trữ khi volume ở trạng thái được bảo vệ | Người có quyền truy cập volume đang mount hoặc broker process |
| Object storage encryption | Object/backup tại storage service | Bản sao plaintext ở consumer hoặc ứng dụng |
| Application-level encryption | Field/payload đã mã hóa trước khi gửi Kafka | Metadata không mã hóa, key management và bản plaintext ở nơi giải mã |

Không được giả định rằng security.protocol=SSL đã bật mã hóa log trên broker. Kafka broker ghi record vào log theo format Kafka; encryption at rest thường được cung cấp bởi hạ tầng lưu trữ hoặc lớp mã hóa của ứng dụng.

## 3. Encryption at rest ở tầng hạ tầng

Cách triển khai phổ biến là mã hóa volume hoặc disk chứa Kafka data directory bằng tính năng của hệ điều hành, storage platform hoặc cloud provider.

Ví dụ về phạm vi cần mã hóa:

- Các volume chứa log.dirs của broker.
- Volume chứa metadata/log data của KRaft nếu được lưu riêng.
- Local state directory của Kafka Streams.
- Disk chứa Kafka Connect logs hoặc file tạm có payload.
- Snapshot, backup, archive và bản sao disaster recovery.
- Volume lưu file cấu hình có chứa secret nếu không thể tách secret sang secret manager.

~~~mermaid
flowchart TB
    K["Kafka broker process"] --> V["Encrypted volume"]
    V --> D["Log segments / indexes"]
    V --> M["KRaft metadata / local files"]
    V --> S["Snapshots / backups"]
    KM["KMS / key service"] --> V
~~~

Cách này giúp bảo vệ thiết bị hoặc snapshot khi bị lấy khỏi môi trường đang chạy. Nó thường ít thay đổi ứng dụng và có thể mã hóa toàn bộ file mà broker tạo ra.

### 3.1. Giới hạn của disk encryption

Khi volume đã được mount và broker process có quyền đọc, dữ liệu được giải mã trong quá trình sử dụng. Vì vậy disk encryption không ngăn:

- Người có quyền root hoặc quyền truy cập broker đọc log.
- Ứng dụng có quyền đọc file lấy được dữ liệu.
- Consumer có quyền đọc topic lấy được payload.
- Admin hoặc malware truy cập process/volume đang hoạt động.
- Payload bị ghi ra log ứng dụng ở dạng plaintext.

Cần kết hợp IAM, OS permissions, Kafka ACL, network isolation, secret management, audit và mã hóa payload nếu threat model yêu cầu.

### 3.2. Quản lý khóa cho volume

Nếu dùng cloud KMS hoặc HSM, nên tách quyền quản lý key khỏi quyền quản trị Kafka:

- Broker workload chỉ được dùng key cần thiết.
- Operator Kafka không mặc nhiên có quyền export key material.
- Có audit cho thao tác tạo, rotate, disable và destroy key.
- Có backup/recovery plan cho key nếu cần giữ khả năng phục hồi dữ liệu.
- Kiểm tra tác động khi KMS không khả dụng hoặc key bị disable.

Mất key có thể khiến dữ liệu không đọc được dù disk còn nguyên. Đây là một failure mode về availability, không chỉ là biện pháp bảo mật.

## 4. Application-level encryption và field-level encryption

Nếu cần bảo vệ PII ngay cả khi broker, operator hoặc consumer không được phép đọc nội dung, có thể mã hóa payload ở producer trước khi gửi Kafka.

Ví dụ event có dữ liệu thông thường và dữ liệu cá nhân:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "CustomerRegistered",
  "customerRef": "cust-token-7f2a",
  "occurredAt": "2026-11-20T10:30:00Z",
  "personalData": {
    "algorithm": "AES-256-GCM",
    "keyId": "customer-data-key-v4",
    "nonce": "base64-encoded-nonce",
    "ciphertext": "base64-encoded-ciphertext"
  }
}
~~~

Các field không nhạy cảm vẫn có thể được consumer dùng để routing, correlation hoặc xử lý luồng. Nội dung nhạy cảm chỉ được giải mã bởi workload có quyền truy cập key.

### 4.1. Envelope encryption

Mô hình envelope encryption dùng hai lớp khóa:

- **DEK (Data Encryption Key):** mã hóa payload hoặc field dữ liệu.
- **KEK (Key Encryption Key):** do KMS/HSM quản lý, dùng để mã hóa (wrap) DEK.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Plaintext PII"] --> B["Generate DEK"]
    B --> C["AEAD encrypt data with DEK"]
    B --> D["KMS wraps DEK with KEK"]
    C --> E["Ciphertext + nonce + metadata"]
    D --> F["Wrapped DEK"]
    E --> G["Kafka record"]
    F --> G
    G --> H["Authorized consumer"]
    H --> I["KMS unwrap DEK"]
    I --> J["Decrypt ciphertext"]
~~~

Broker lưu ciphertext và wrapped DEK. Consumer được cấp quyền mới có thể yêu cầu KMS unwrap DEK rồi giải mã payload.

Cần dùng thư viện mật mã đã được kiểm chứng và authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305. Với AES-GCM, không được tái sử dụng nonce với cùng một key. Không tự thiết kế thuật toán, nonce format hoặc key derivation.

### 4.2. Metadata cũng có thể là dữ liệu cá nhân

Mã hóa riêng field personalData không bảo vệ tất cả thông tin có thể nhận diện một cá nhân. Các trường sau cũng có thể nhạy cảm:

- Kafka key chứa email, số điện thoại hoặc customer ID.
- Header chứa tên, địa chỉ IP hoặc token.
- Topic name hoặc routing key thể hiện danh tính.
- Timestamp kết hợp với dữ liệu công khai.
- Correlation ID có thể tra ngược về một người.
- Error message hoặc stack trace chứa payload.

Thiết kế event nên dùng identifier giả danh (pseudonymous reference) hoặc token thay cho PII trực tiếp khi consumer không cần biết danh tính thật. Pseudonymization không đồng nghĩa anonymization: nếu vẫn có bảng ánh xạ để tra lại, dữ liệu vẫn có thể là dữ liệu cá nhân.

### 4.3. Mã hóa toàn payload hay chỉ field nhạy cảm?

| Cách làm | Ưu điểm | Hạn chế |
|---|---|---|
| Mã hóa toàn payload | Broker và consumer không có key không đọc được nội dung | Khó filter, transform, schema inspection và analytics |
| Mã hóa field PII | Consumer vẫn xử lý phần không nhạy cảm | Dễ bỏ sót field nhạy cảm; schema phức tạp hơn |
| Tokenization | Consumer dùng token ổn định để join/routing | Cần token vault hoặc dịch vụ ánh xạ được bảo vệ |
| Pseudonymization | Giảm dữ liệu nhận diện trực tiếp | Vẫn cần bảo vệ bảng ánh xạ và chống re-identification |

Chọn phạm vi mã hóa dựa trên data classification và nhu cầu xử lý. Không đưa plaintext vào Kafka headers hoặc key chỉ vì payload đã được mã hóa.

## 5. Key lifecycle, rotation và crypto-erasure

Mã hóa chỉ hữu ích khi khóa được quản lý an toàn. Cần xác định:

- Ai được tạo và sử dụng key?
- Key được lưu ở KMS/HSM hay file?
- DEK có được lưu plaintext ở đâu không?
- Có thể rotate KEK mà không mã hóa lại toàn bộ event không?
- Key có được cache trong consumer process không?
- Khi thu hồi key, các replica/cache/backup của key được xử lý thế nào?
- Có cần giữ key để đáp ứng retention pháp lý hoặc điều tra không?

### 5.1. Rotation

Với envelope encryption, có thể rotate KEK và re-wrap DEK. Payload ciphertext không cần thay đổi nếu DEK vẫn giữ nguyên. Khi rotate DEK, cần giải mã và mã hóa lại dữ liệu hoặc dùng một cơ chế migration có kiểm soát.

Record nên chứa key identifier/version để consumer biết key nào cần dùng, nhưng không chứa secret key material.

### 5.2. Crypto-erasure

Crypto-erasure (xóa bằng khóa) là làm cho ciphertext không còn giải mã được bằng cách hủy key material cần thiết. Đây có thể là một phần của quy trình xóa, nhưng chỉ hiệu quả nếu:

- Dữ liệu nhạy cảm thực sự đã được mã hóa trước khi lưu.
- Không có bản plaintext ở nơi khác.
- Không còn bản DEK plaintext trong cache, dump, log hoặc backup.
- Không còn bản sao key có thể khôi phục từ backup/replica.
- Key bị hủy là key duy nhất có thể giải mã dữ liệu mục tiêu.
- Metadata còn lại không tự nó nhận diện được cá nhân.

Nếu nhiều người dùng chia sẻ cùng một KEK, hủy KEK có thể làm mất khả năng giải mã dữ liệu của tất cả họ. Vì vậy, crypto-erasure theo từng chủ thể cần thiết kế key hierarchy và phạm vi key ngay từ đầu.

Một mô hình có thể dùng DEK riêng theo subject hoặc theo nhóm dữ liệu của subject, với key material được quản lý ngoài Kafka. Không đặt wrapped DEK trong record nếu thiết kế xóa yêu cầu phải hủy khả năng unwrap và hệ thống vẫn giữ wrapped key có thể giải mã bằng KEK chung. Cần đánh giá toàn bộ đường khôi phục key trước khi tuyên bố crypto-erasure hoàn tất.

### 5.3. Key deletion có thể ảnh hưởng availability

Nếu hủy nhầm key, dữ liệu hợp lệ cũng có thể mất vĩnh viễn. Trước khi hủy key cần:

1. Xác minh subject và phạm vi dữ liệu.
2. Kiểm tra legal hold/retention obligation.
3. Xác định tất cả event và bản sao liên quan.
4. Xác minh không còn consumer hoặc service cần giải mã dữ liệu.
5. Thực hiện theo quy trình phê duyệt và audit.
6. Xác minh key không thể được khôi phục theo backup policy.
7. Ghi nhận kết quả và bằng chứng thực thi.

Không xem thao tác disable key tạm thời là destroy key. Một số KMS có trạng thái pending deletion hoặc thời gian chờ khôi phục; cần theo dõi đến trạng thái cuối theo policy.

## 6. Kafka lưu record theo log: vì sao xóa một event khó?

Kafka partition là log append-only. Producer ghi record mới ở cuối log; broker không hỗ trợ cập nhật tùy ý một record cũ tại một offset.

Một event có thể đã được đọc bởi nhiều consumer và nhân bản sang nhiều hệ thống trước khi có yêu cầu xóa. Vì vậy không có một thao tác đơn giản tương đương DELETE WHERE customer_id = ... áp dụng xuyên mọi bản sao Kafka.

Kafka có các cơ chế cleanup:

- cleanup.policy=delete: xóa segment theo retention time/size.
- cleanup.policy=compact: giữ phiên bản mới nhất theo key sau khi log cleaner xử lý.
- Tombstone: record có key và value null trong compacted topic, biểu thị key đã bị xóa.
- DeleteRecords API: xóa phần log trước một offset trên từng partition.
- Delete topic: yêu cầu xóa toàn bộ topic và dữ liệu partition liên quan.

Mỗi cơ chế có phạm vi và thời điểm hoàn tất khác nhau.

## 7. Retention với cleanup.policy=delete

Ví dụ topic giữ log trong 7 ngày:

~~~properties
cleanup.policy=delete
retention.ms=604800000
retention.bytes=-1
~~~

retention.ms và retention.bytes xác định điều kiện segment đủ tuổi hoặc vượt dung lượng để được xóa. Kafka xóa theo segment, không xóa một record tùy ý ngay khi đủ chính xác 7 ngày.

Điều đó có nghĩa:

- Segment đang active có thể chưa được xóa ngay cả khi một record đã cũ.
- Việc xóa phụ thuộc segment rollover và chu kỳ kiểm tra retention.
- Retention time là chính sách lưu log, không phải deadline xóa vật lý tuyệt đối cho từng record.
- Replica cũng cần thực hiện cleanup theo cơ chế broker.
- Backup, snapshot và consumer copies không tự bị ảnh hưởng.

Các cấu hình thường cần xem cùng nhau gồm:

| Cấu hình | Ý nghĩa |
|---|---|
| cleanup.policy | Chọn delete, compact hoặc kết hợp |
| retention.ms | Thời gian retention cho delete policy |
| retention.bytes | Giới hạn dung lượng log cho delete policy |
| segment.ms | Ngưỡng thời gian để roll segment |
| segment.bytes | Ngưỡng kích thước để roll segment |
| file.delete.delay.ms | Thời gian chờ trước khi file segment bị xóa sau khi được đánh dấu |

Giảm retention.ms có thể làm dữ liệu cũ sớm đủ điều kiện cleanup nhưng không bảo đảm file bị xóa ngay lập tức trên tất cả storage và backup.

## 8. Compaction và tombstone trong compacted topic

Compaction giữ lại giá trị mới nhất theo key sau khi log cleaner xử lý. Cơ chế này thường dùng cho topic lưu trạng thái hiện tại hoặc changelog.

Ví dụ topic có các record:

~~~text
offset 10: key=customer-7, value={email: old@example.net}
offset 18: key=customer-7, value={email: new@example.net}
offset 25: key=customer-7, value=null
~~~

Record offset 25 là tombstone. Nó biểu thị key customer-7 đã bị xóa. Sau khi compaction xử lý, các giá trị cũ của key có thể bị loại bỏ và tombstone được giữ trong một khoảng thời gian theo delete.retention.ms.

Cấu hình ví dụ:

~~~properties
cleanup.policy=compact
delete.retention.ms=86400000
~~~

### 8.1. Tombstone không phải secure erase

Tombstone là một record mới trong log, không phải lệnh ghi đè ngay lập tức lên mọi byte của record cũ.

Sau khi tombstone được ghi:

- Consumer đang đọc log có thể quan sát tombstone.
- Log cleaner cần thời gian để xử lý các segment đủ điều kiện.
- Record cũ có thể vẫn tồn tại trong segment chưa compact.
- Replica và backup có thể còn dữ liệu cũ.
- Consumer đã materialize dữ liệu sang database phải tự xóa bản sao.
- Sau delete.retention.ms, tombstone có thể được dọn khỏi compacted log.

delete.retention.ms là thời gian tombstone được giữ để consumer có cơ hội quan sát delete; nó không phải cam kết xóa PII khỏi mọi storage sau đúng thời gian đó.

Consumer offline lâu hơn tombstone retention có thể không nhìn thấy tombstone nếu nó quay lại đọc từ offset cũ sau khi tombstone đã bị dọn. Vì vậy cần có chính sách bootstrap/rebuild phù hợp và không dùng tombstone làm cơ chế thông báo duy nhất nếu consumer có thể offline không giới hạn.

### 8.2. Key của topic quyết định phạm vi xóa

Compaction làm việc theo Kafka record key. Nếu mỗi event dùng event ID khác nhau làm key, tombstone cho customer-7 không tự xóa các event cũ có key là evt-1, evt-2.

Để xóa dữ liệu theo subject trong compacted topic, cần thiết kế key phù hợp hoặc duy trì index ánh xạ subject tới tất cả key/record cần xử lý. Không đổi key của event đã phát chỉ để tiện xóa nếu việc đó phá ordering, partition mapping hoặc contract consumer.

## 9. DeleteRecords chỉ xóa prefix của partition

Kafka Admin API có thể xóa record trước một offset trong một partition. Đây là thao tác cắt bỏ phần đầu log, không phải tìm và xóa một record theo điều kiện bất kỳ.

Ví dụ khái niệm:

~~~text
Partition 0:
offset 0  1  2  3  4  5  6  7  8  9
          ^^^^^^^^^
          Xóa record trước offset 3

Log start offset sau thao tác có thể tiến lên 3.
~~~

DeleteRecords phù hợp khi cần bỏ một prefix đã xác định của partition, chẳng hạn dữ liệu trước một checkpoint. Nó không thể xóa riêng mọi event của một customer nếu các event của nhiều customer xen kẽ theo offset.

Nếu một subject có record ở offset 3, 20 và 500, xóa trước offset 500 sẽ đồng thời loại bỏ record của những subject khác ở offset nhỏ hơn 500. Do đó không dùng DeleteRecords như câu lệnh xóa theo customer ID.

## 10. Delete topic không đồng nghĩa xóa toàn bộ mọi bản sao

Xóa topic yêu cầu Kafka loại bỏ topic và partition log trên cluster. Quá trình này là bất đồng bộ; broker cần xử lý metadata và file log tương ứng.

Topic deletion không tự xóa:

- Bản copy ở cluster MirrorMaker/replication khác.
- Snapshot hoặc backup đã tạo trước đó.
- Consumer database, search index hoặc object storage.
- Retry/DLT topic có bản sao event.
- Kafka Streams local state hoặc changelog topic riêng.
- File export, application log và tracing.
- Bản dữ liệu đã tải xuống bởi người dùng hoặc hệ thống khác.

Không xóa topic dùng chung chỉ để xóa một subject. Nếu topic chứa dữ liệu của nhiều chủ thể, cần cơ chế xóa theo record/key hoặc thiết kế encryption/tokenization phù hợp.

## 11. Thiết kế event để hỗ trợ xóa dữ liệu cá nhân

Xóa dữ liệu dễ hơn nếu ngay từ đầu event không chứa PII không cần thiết.

Các nguyên tắc:

1. Dùng opaque subject reference thay cho email/số điện thoại trong Kafka key.
2. Tách dữ liệu định danh khỏi event nghiệp vụ nếu consumer không cần.
3. Chỉ đưa field cần thiết vào payload.
4. Mã hóa field nhạy cảm bằng DEK phù hợp.
5. Gắn event ID, subject reference, schema version và correlation metadata có kiểm soát.
6. Duy trì index để biết subject liên quan tới event/key/topic nào.
7. Định nghĩa retention theo data classification và mục đích xử lý.
8. Không ghi PII vào log hoặc metric label.

Ví dụ event tối giản:

~~~json
{
  "eventId": "evt-204",
  "eventType": "OrderPlaced",
  "subjectRef": "subj-opaque-91a2",
  "aggregateId": "order-501",
  "occurredAt": "2026-11-20T11:00:00Z",
  "data": {
    "orderTotal": 850000,
    "currency": "VND"
  }
}
~~~

Thông tin như tên, email và địa chỉ có thể được giữ trong hệ thống customer profile có kiểm soát riêng. Consumer chỉ nhận subject reference và gọi dịch vụ có quyền khi thật sự cần dữ liệu định danh.

Nếu subject reference có thể ánh xạ về một cá nhân, nó vẫn cần được quản lý như dữ liệu giả danh và không được chia sẻ rộng tùy tiện.

## 12. Dùng tombstone và delete event cho projection

Một consumer materialize trạng thái customer vào compacted topic hoặc database có thể nhận delete event để xóa projection.

Ví dụ tombstone Kafka:

~~~java
producer.send(
    new ProducerRecord<String, CustomerProfile>(
        "customer-profile",
        subjectRef,
        null
    )
);
~~~

Record có key subjectRef và value null. Consumer hoặc compaction sẽ xử lý key đó theo semantics của compacted topic.

Nếu projection được lưu ở database, consumer phải thực hiện delete/redaction trong database và commit Kafka offset theo quy trình an toàn. Nếu process crash sau database delete nhưng trước offset commit, consumer có thể nhận tombstone lại; thao tác delete cần idempotent.

Với nhiều topic có key khác nhau, cần phát delete event phù hợp tới từng projection hoặc dùng một deletion workflow điều phối các consumer. Một tombstone ở một topic không tự lan truyền sang mọi topic khác.

## 13. Xóa trong Kafka Streams state store và changelog

Kafka Streams có thể giữ PII trong:

- Local RocksDB state store.
- Changelog topic của state store.
- Repartition topic.
- Output topic.
- Local state backup hoặc snapshot.

Khi xóa một key khỏi logged state store, Kafka Streams có thể ghi tombstone vào changelog. Tuy nhiên, điều đó không có nghĩa local disk và changelog bị ghi đè vật lý ngay lập tức.

Để xử lý yêu cầu xóa:

- Xác định store nào chứa subject hoặc dữ liệu liên quan.
- Thiết kế processor/command để xóa key hoặc cập nhật state thành dạng đã redacted.
- Đảm bảo changelog nhận delete/tombstone.
- Kiểm tra standby replica và task restore.
- Xem xét local state directory, snapshot và backup.
- Nếu state store không có index theo subject, có thể cần thiết kế lại hoặc rebuild state có kiểm soát.

Nếu state store chứa aggregate value tổng hợp từ nhiều subject, không thể xóa một subject bằng cách xóa nguyên key mà không ảnh hưởng dữ liệu của người khác. Cần lưu đủ lineage hoặc có cách tính lại aggregate từ nguồn còn hợp lệ.

## 14. Kafka Connect, retry topic và DLT cũng chứa dữ liệu

Kafka Connect có thể sao chép record sang hệ thống đích. Một số connector còn ghi lỗi vào dead-letter queue topic kèm header chứa exception hoặc metadata.

Cần xem xét:

- Source topic và sink destination.
- Retry topic và DLT.
- Connector error context và log.
- Sink database/index/table.
- Export/archive do connector tạo.
- Connect worker internal topics và config secrets.

Nếu payload chứa PII, DLT không được xem là nơi lưu lỗi vô hại. Cần áp dụng retention, ACL, encryption at rest và quy trình xóa tương đương topic chính.

Kafka Connect internal config topic có thể chứa cấu hình connector và thông tin nhạy cảm tùy cách khai báo. Dùng secret provider/config provider phù hợp, giới hạn quyền REST API và bảo vệ internal topics.

## 15. Replica, MirrorMaker, backup và disaster recovery

Replication tăng durability nhưng cũng tạo thêm bản sao dữ liệu. Xóa ở leader không phải bằng chứng mọi bản sao đã được xử lý.

Các bản sao cần kiểm kê:

| Nơi lưu | Việc cần làm khi xóa |
|---|---|
| Partition replicas trong cùng cluster | Xác minh cleanup/compaction trên broker theo policy |
| MirrorMaker hoặc cluster DR | Gửi deletion workflow tới cluster đích hoặc áp dụng retention/key strategy |
| Snapshot volume | Xóa/expire theo backup lifecycle và xác minh restore policy |
| Object storage archive | Xóa object hoặc áp dụng lifecycle/crypto-erasure theo thiết kế |
| Consumer database | Xóa/redact projection theo subject reference |
| Search index/cache | Xóa document/key và cache entry |
| Local state store | Xóa key/rebuild store, xử lý changelog và snapshot |
| Log/tracing/analytics | Xóa hoặc redaction theo retention và data policy |

Backup thường được thiết kế để không thể sửa từng record. Có thể giữ backup trong một khoảng thời gian cố định, giới hạn quyền restore và bảo đảm mọi lần restore đều chạy lại deletion ledger để không hồi sinh dữ liệu đã bị yêu cầu xóa.

Một quy trình restore nên áp dụng lại các yêu cầu xóa còn hiệu lực trước khi đưa dữ liệu trở lại phục vụ người dùng.

## 16. Quy trình xử lý yêu cầu xóa dữ liệu cá nhân

Một quy trình có thể triển khai theo các bước:

1. Xác minh yêu cầu và danh tính người yêu cầu theo quy trình của tổ chức.
2. Xác định subject reference, customer IDs và alias liên quan.
3. Tra cứu data lineage/index để tìm topic, key, event ID và hệ thống downstream.
4. Kiểm tra legal hold, nghĩa vụ lưu trữ hoặc ngoại lệ áp dụng.
5. Ngừng tạo event mới chứa dữ liệu cần xóa nếu nghiệp vụ cho phép.
6. Xóa/redact dữ liệu trong database và các projection.
7. Phát tombstone/delete event cho compacted topics hoặc projection tương ứng.
8. Xử lý retry/DLT, changelog, state store và các topic phụ.
9. Thực hiện DeleteRecords/topic cleanup nếu phạm vi offset/topic phù hợp; không dùng để xóa chọn lọc giữa log.
10. Xử lý replica, mirror cluster, archive và backup theo policy.
11. Nếu dùng crypto-erasure, xác minh key scope và hoàn tất key destruction theo quy trình.
12. Kiểm tra log, trace, export và các bản sao ngoài Kafka.
13. Ghi lại bằng chứng, trạng thái từng hệ thống và ngoại lệ còn tồn tại.
14. Áp dụng deletion ledger sau mọi lần restore/DR.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu xóa"] --> B["Xác minh subject và phạm vi"]
    B --> C["Tra cứu lineage / data inventory"]
    C --> D{"Có legal hold hoặc ngoại lệ?"}
    D -->|Có| E["Đưa vào quy trình xử lý ngoại lệ"]
    D -->|Không| F["Xóa hoặc redact nguồn và projection"]
    F --> G["Tombstone / delete workflow"]
    G --> H["Kafka topics, DLT, Streams state"]
    H --> I["Replicas, mirrors, backups, sinks"]
    I --> J["Kiểm tra và ghi nhận bằng chứng"]
    J --> K["Cập nhật deletion ledger"]
~~~

Đây là quy trình kỹ thuật tham khảo. Nghĩa vụ pháp lý, thời hạn và ngoại lệ cần được xác định bởi chính sách bảo vệ dữ liệu và tư vấn pháp lý của tổ chức.

## 17. Kiểm thử xóa và encryption at rest

Không chỉ kiểm tra rằng API trả về thành công. Cần kiểm thử trạng thái sau cleanup và khả năng dữ liệu bị hồi sinh.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Volume encryption | Kiểm tra cấu hình storage/KMS và snapshot | Volume/backup được mã hóa theo policy |
| TLS và at-rest | Kiểm tra riêng TLS handshake và storage encryption | Không nhầm hai lớp bảo vệ |
| PII trong Kafka payload | Đọc record bằng consumer không có key | Chỉ thấy ciphertext ở field đã mã hóa |
| PII trong key/header | Quét sample record và header | Không còn identifier nhạy cảm ngoài dự kiến |
| Tombstone | Produce key với value null rồi đọc compacted topic | Consumer nhận delete theo semantics và compaction xử lý sau |
| Compaction | Theo dõi log cleaner và segment | Record cũ được dọn theo cơ chế nền, không giả định tức thời |
| DeleteRecords | Xóa prefix ở partition test | Log start offset tiến; record trước offset không đọc được |
| Topic deletion | Xóa topic thử nghiệm | Topic/partition log được dọn theo lifecycle broker |
| Consumer projection | Gửi delete event và restart consumer | Database/index không hồi sinh dữ liệu |
| DLT/retry | Tạo record lỗi có PII rồi thực hiện deletion | Bản sao ở retry/DLT cũng được xử lý |
| Kafka Streams state | Xóa subject state, restart task | State không xuất hiện lại từ changelog cũ |
| Backup restore | Restore snapshot vào môi trường test | Deletion ledger được áp dụng trước khi mở truy cập |
| Crypto-erasure | Thu hồi/hủy key theo quy trình thử nghiệm | Ciphertext không thể giải mã bằng key còn khả dụng |

Dùng dữ liệu giả lập trong kiểm thử. Không đưa dữ liệu cá nhân thật vào log test, screenshot, command history hoặc báo cáo không được kiểm soát.

## 18. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ TLS đã mã hóa Kafka log trên disk | Data at rest vẫn có thể đọc từ storage | Bật volume/storage encryption hoặc application encryption |
| Nghĩ retention.ms là deadline xóa record chính xác | Segment và bản sao có thể còn tồn tại sau thời điểm đó | Hiểu segment rollover, cleanup cycle và backup policy |
| Gửi tombstone nhưng dùng event ID làm key | Không xóa được các event khác của cùng subject | Thiết kế key/index theo subject hoặc deletion workflow |
| Coi tombstone là secure erase | Record cũ có thể còn trong segment/replica/backup | Kết hợp compaction, storage lifecycle và downstream deletion |
| Dùng DeleteRecords để xóa customer | Xóa cả prefix chứa dữ liệu người khác | Dùng tombstone/key strategy hoặc mã hóa theo subject |
| Xóa topic chính nhưng bỏ DLT/retry | PII vẫn còn trong topic phụ | Quản lý lineage cho toàn bộ topic |
| Xóa DB nhưng quên Kafka Streams state | PII còn trong local store/changelog | Xóa state, xử lý changelog và restore |
| Hủy key dùng chung cho nhiều người | Làm mất khả năng giải mã dữ liệu hợp lệ | Phân tách key scope và kiểm soát blast radius |
| Chỉ xóa bản active, bỏ backup | Dữ liệu có thể hồi sinh khi restore | Deletion ledger và backup lifecycle |
| Ghi PII vào log/trace | Dữ liệu ngoài Kafka vẫn tồn tại | Mask/redact và giới hạn retention log |

## 19. Checklist thiết kế và vận hành

- [ ] Đã phân loại PII và xác định field thực sự cần đưa vào event.
- [ ] Không đưa PII trực tiếp vào Kafka key/header nếu không cần.
- [ ] Đã phân biệt TLS in transit và encryption at rest.
- [ ] Broker data volume, KRaft metadata, local state và backup được mã hóa theo policy.
- [ ] Đã đánh giá application-level/field-level encryption cho dữ liệu nhạy cảm.
- [ ] Dùng AEAD và thư viện crypto đã được kiểm chứng.
- [ ] DEK/KEK được quản lý bằng KMS/HSM hoặc hệ thống quản lý khóa phù hợp.
- [ ] Có quy trình rotate, revoke, backup và destroy key.
- [ ] Crypto-erasure có phạm vi key riêng và kiểm tra mọi bản sao key/plaintext.
- [ ] Topic retention được chọn theo mục đích và segment semantics.
- [ ] Hiểu compaction, tombstone và delete.retention.ms.
- [ ] Không coi DeleteRecords là xóa record tùy ý theo điều kiện.
- [ ] Có subject-to-event/key index hoặc data lineage để tìm bản sao.
- [ ] Retry, DLT, repartition, changelog và output topics nằm trong deletion inventory.
- [ ] Consumer projection, database, cache, search và data lake có quy trình xóa.
- [ ] Mirror cluster, snapshot, archive và backup có lifecycle riêng.
- [ ] Restore/DR áp dụng deletion ledger trước khi mở truy cập.
- [ ] Có metric/audit để theo dõi yêu cầu xóa và kết quả từng hệ thống.
- [ ] Kiểm thử cả việc dữ liệu không bị hồi sinh sau restart/restore.
- [ ] Có owner, SLA, ngoại lệ và bằng chứng hoàn thành cho mỗi yêu cầu.

Kafka có thể mã hóa kết nối, giữ dữ liệu theo retention, compact theo key và phát tombstone để biểu thị xóa. Tuy nhiên, các cơ chế này không cung cấp một lệnh xóa PII tùy ý và tức thời khỏi mọi bản sao. Cần kết hợp encryption at rest ở tầng storage, application-level encryption cho field nhạy cảm, quản lý khóa có kiểm soát và data lineage để tìm mọi nơi lưu dữ liệu. Quy trình xóa phải bao gồm topic chính, replica, DLT, state store, consumer database, mirror cluster và backup; sau mỗi lần restore cũng phải áp dụng lại deletion ledger để dữ liệu đã xóa không quay trở lại.
