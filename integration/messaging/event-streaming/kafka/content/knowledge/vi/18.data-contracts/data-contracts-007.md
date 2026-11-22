# Tiến hóa schema của key và hệ quả đối với phân vùng, compaction

Trong Kafka, key của record vừa có thể được dùng để định tuyến record vào partition, vừa là định danh mà log compaction sử dụng để gom các phiên bản của cùng một khóa. Vì vậy, key không chỉ là một object Java có vài field. Điều quyết định partitioning và compaction là **byte sau khi key được serialize**.

Khi schema của key thay đổi, cùng một thực thể nghiệp vụ có thể được serialize thành byte khác trước. Với partitioner mặc định của Java producer, thay đổi byte có thể làm key được ánh xạ sang partition khác. Ngay cả khi hai dạng byte vẫn rơi vào cùng partition, log compaction vẫn xem chúng là hai key khác nhau nếu byte không giống nhau. Một tombstone dùng encoding mới cũng không xóa được record cũ mang encoding cũ.

Đây là rủi ro đặc biệt quan trọng với topic dùng compact hoặc compact,delete để lưu trạng thái mới nhất theo key. Schema Registry có thể xác nhận schema mới tương thích với schema cũ, nhưng compatibility không bảo đảm byte key ổn định, partition mapping ổn định hay compaction nhận diện hai encoding là cùng một thực thể.

## 1. Key trong Kafka có hai vai trò quan trọng

Một Kafka record có key, value và headers. Producer serialize key và value thành byte trước khi gửi đến broker.

Key thường được dùng cho hai mục đích:

1. **Partitioning:** chọn partition để các record liên quan có thể được xử lý cùng nhau và giữ thứ tự trong một partition.
2. **Log compaction:** xác định những record nào thuộc cùng một key để giữ lại phiên bản mới nhất và xử lý tombstone.

Ví dụ topic customer-state lưu trạng thái khách hàng:

~~~text
key=customer-42  value={name: "An", status: "ACTIVE"}
key=customer-42  value={name: "An", status: "VIP"}
key=customer-42  value={name: "An", status: "SUSPENDED"}
~~~

Nếu ba record có cùng serialized key bytes và nằm trong cùng partition, compaction có thể giữ lại record mới nhất của key đó sau khi log cleaner xử lý.

Nếu lần ghi cuối dùng key bytes khác với hai lần trước, Kafka có thể xem nó là một key khác dù ứng dụng giải mã cả hai thành cùng customerId.

### 1.1. Kafka broker không so sánh object nghiệp vụ

Broker nhận byte của key. Broker không deserialize Avro, JSON, Protobuf hay Java object để so sánh ý nghĩa field.

Ví dụ hai object Java:

~~~java
new CustomerKey("customer-42")
new CustomerKeyV2("customer-42", "tenant-a")
~~~

Có thể biểu diễn cùng một khách hàng theo góc nhìn nghiệp vụ, nhưng serializer có thể tạo ra hai mảng byte khác nhau.

Đối với Kafka, hai mảng byte khác nhau là hai key khác nhau cho mục đích compaction. Việc ứng dụng có thể giải mã chúng về cùng customerId không làm broker tự hiểu chúng tương đương.

### 1.2. Phân biệt logical key và serialized key

| Khái niệm | Ví dụ | Nơi được sử dụng |
|---|---|---|
| Logical key | customerId = customer-42 | Quy tắc nghiệp vụ của ứng dụng |
| Key object | CustomerKey(customer-42) | Kiểu dữ liệu trong Java |
| Serialized key | byte array do serializer tạo | Producer partitioner và Kafka record |
| Partition | partition 3 | Nơi record được append |
| Compaction key identity | Byte key trong partition | Log cleaner |

Khi thiết kế schema evolution, phải xem xét cả logical key lẫn serialized key. Giữ nguyên giá trị customerId chưa đủ để bảo đảm hai record có cùng serialized key.

## 2. Partitioner chọn partition từ serialized key bytes

Với Java Kafka producer dùng partitioner mặc định, record có key thường được định tuyến bằng hash của serialized key bytes và số partition hiện có.

Có thể mô tả khái quát:

\[
partition = positiveHash(serializedKeyBytes) \bmod partitionCount
\]

Trong Java client mặc định, phép hash keyed record thường dựa trên Murmur2. Partitioner nhận byte key sau serialize, không nhận trực tiếp object nghiệp vụ.

Ví dụ cùng topic có 8 partition:

~~~text
Logical key: customer-42

Encoding A:
  bytes = [01 00 2A 7F ...]
  hash   = H(bytes A)
  result = partition 3

Encoding B:
  bytes = [02 00 91 42 ...]
  hash   = H(bytes B)
  result = partition 6
~~~

Số partition trong ví dụ chỉ minh họa. Hai encoding khác nhau có thể rơi vào cùng partition do hash collision hoặc có thể rơi vào partition khác. Không được giả định key mới chắc chắn đổi partition; điều chắc chắn là byte key đã đổi và compaction identity đã đổi.

### 2.1. Cùng logical key không bảo đảm cùng partition

Giả sử producer cũ và producer mới cùng phát customerId customer-42:

~~~text
Producer cũ:
  CustomerKeyV1(customerId="customer-42")
  -> Avro serializer V1
  -> key bytes A
  -> partition 3

Producer mới:
  CustomerKeyV2(customerId="customer-42", region="north")
  -> Avro serializer V2
  -> key bytes B
  -> partition 6
~~~

Consumer group có thể xử lý partition 3 và partition 6 đồng thời. Vì Kafka chỉ giữ thứ tự trong từng partition, event mới của customer-42 có thể được xử lý trước event cũ.

Nếu topic được dùng như changelog trạng thái, một khách hàng có thể xuất hiện như hai dòng độc lập thay vì một dòng được cập nhật.

### 2.2. Khi nào mapping có thể thay đổi?

Partition mapping có thể thay đổi khi:

- Key schema thay đổi làm serialized bytes thay đổi.
- Schema ID trong wire format thay đổi.
- Serializer thay đổi encoding, field order hoặc cách biểu diễn.
- Chuẩn hóa chuỗi thay đổi, ví dụ chữ hoa/thường hoặc Unicode normalization.
- Một producer dùng custom partitioner còn producer khác dùng partitioner mặc định.
- Partition count thay đổi.
- Một producer chỉ định partition tường minh.
- Cấu hình partitioner hoặc client version thay đổi hành vi.

Nếu producer chỉ định partition tường minh, key hash không quyết định partition cho record đó. Tuy nhiên, serialized key bytes vẫn quyết định identity dùng cho compaction.

## 3. Schema Registry và byte key

Schema Registry quản lý schema và compatibility giữa các phiên bản. Serializer thường ghi thông tin nhận diện schema vào wire format để deserializer biết schema writer cần dùng.

Với Confluent wire format cho Avro, record thường có magic byte và schema ID trước phần Avro datum. Các định dạng Protobuf và JSON Schema có framing riêng theo serializer. Đây là chi tiết của wire format Confluent; các serializer hoặc registry khác có thể dùng cách đóng gói khác.

Ví dụ minh họa:

~~~text
Avro key với schema ID 101:
  [magic byte][schema ID 101][Avro datum]

Avro key với schema ID 205:
  [magic byte][schema ID 205][Avro datum]
~~~

Ngay cả khi phần dữ liệu nghiệp vụ biểu diễn cùng customerId, schema ID khác nhau đã có thể làm toàn bộ serialized key bytes khác nhau.

### 3.1. Schema mới tương thích vẫn có thể tạo key bytes mới

Giả sử schema V1:

~~~json
{
  "type": "record",
  "name": "CustomerKey",
  "fields": [
    {"name": "customerId", "type": "string"}
  ]
}
~~~

Schema V2 thêm field có default:

~~~json
{
  "type": "record",
  "name": "CustomerKey",
  "fields": [
    {"name": "customerId", "type": "string"},
    {"name": "region", "type": ["null", "string"], "default": null}
  ]
}
~~~

Schema V2 có thể tương thích với V1 theo một số compatibility mode nếu field mới được thiết kế đúng. Nhưng compatibility chỉ nói về khả năng đọc/ghi schema theo quy tắc registry. Nó không cam kết serializer V1 và V2 tạo ra cùng byte key.

Nếu wire format chứa schema ID, ID mới cũng có thể làm byte prefix khác. Nếu datum encoding thay đổi, phần payload cũng có thể khác.

### 3.2. Compatibility và partition stability là hai kiểm tra riêng

| Kiểm tra | Câu hỏi | Điều nó không bảo đảm |
|---|---|---|
| Schema compatibility | Reader cũ/mới có đọc được dữ liệu theo policy không? | Không bảo đảm key bytes giống nhau |
| Partition stability | Cùng logical entity có tiếp tục vào cùng partition không? | Không bảo đảm schema reader tương thích |
| Compaction identity | Record cập nhật/tombstone có dùng đúng key bytes cũ không? | Không tự suy luận logical equivalence |
| Business compatibility | Field và ý nghĩa nghiệp vụ có còn đúng không? | Không bảo đảm wire format ổn định |

Không nên dùng kết quả compatibility check để kết luận key schema có thể triển khai an toàn trên topic compacted. Cần thêm kiểm tra serialized bytes, partition mapping và tombstone behavior.

### 3.3. Key subject và value subject

Trong nhiều cấu hình Schema Registry, key schema và value schema được quản lý như hai subject riêng. Với TopicNameStrategy, tên subject thường có hậu tố key hoặc value theo tên topic. Naming strategy khác có thể thay đổi cách nhóm schema.

Cần kiểm tra compatibility policy của key subject độc lập với value subject. Một policy áp dụng cho value không tự động chứng minh key evolution an toàn.

## 4. Log compaction dùng byte key trong từng partition

Topic có cleanup policy compact sẽ được Kafka log cleaner xử lý để giữ lại record mới nhất cho mỗi key. Compaction hoạt động theo partition, không gom các record cùng logical key trên toàn topic bằng cách deserialize value hoặc key schema.

Ví dụ trước compaction:

~~~text
partition 1:
offset 10  key=A  value=ACTIVE
offset 11  key=B  value=ACTIVE
offset 12  key=A  value=VIP
offset 13  key=A  value=SUSPENDED
offset 14  key=B  value=BLOCKED
~~~

Sau khi compaction xử lý, log có thể giữ record mới nhất của từng key:

~~~text
partition 1:
offset 13  key=A  value=SUSPENDED
offset 14  key=B  value=BLOCKED
~~~

Compaction chạy bất đồng bộ. Không nên kỳ vọng record cũ biến mất ngay sau khi producer gửi bản cập nhật mới.

### 4.1. Hai byte key khác nhau là hai key compaction khác nhau

Giả sử hai record cùng đại diện customer-42 nhưng được serialize khác nhau:

~~~text
Record cũ:
  key bytes = [schemaId=101, datum=customer-42]
  value     = ACTIVE

Record mới:
  key bytes = [schemaId=205, datum=customer-42, region=north]
  value     = SUSPENDED
~~~

Log cleaner xem chúng là hai key bytes khác nhau. Sau compaction, cả hai record có thể vẫn được giữ:

~~~text
key bytes A -> customer-42 -> ACTIVE
key bytes B -> customer-42 -> SUSPENDED
~~~

Một consumer dựng lại state bằng cách đọc compacted topic có thể nhìn thấy hai record và không biết chúng là cùng một logical customer nếu không có migration logic.

Nếu hai byte key khác nhau nhưng hash cùng partition, chúng vẫn là hai key compaction khác nhau. Nếu chúng được hash sang partition khác, mỗi partition còn được compact độc lập.

### 4.2. Compaction không phải database upsert theo business ID

Kafka compacted topic thường được dùng như changelog hoặc nguồn dựng lại state. Nhưng compaction không hiểu câu lệnh kiểu:

~~~sql
UPDATE customer_state
SET status = 'SUSPENDED'
WHERE customer_id = 'customer-42';
~~~

Nó chỉ nhận diện key bytes trong partition. Nếu key encoding thay đổi, record mới không tự cập nhật record cũ theo logical customerId.

Vì vậy, định dạng key trên compacted topic nên được xem như một phần của data contract ổn định lâu dài.

## 5. Tombstone và xóa state trong compacted topic

Trong compacted topic, tombstone là record có **key khác null và value bằng null**. Tombstone báo rằng key đó đã bị xóa.

Ví dụ:

~~~text
key=customer-42 value={status: "ACTIVE"}
key=customer-42 value={status: "SUSPENDED"}
key=customer-42 value=null
~~~

Sau khi log cleaner xử lý và tombstone hết thời gian giữ theo cấu hình, các record cũ của đúng key bytes có thể được loại bỏ.

### 5.1. Null key không phải tombstone

| Key | Value | Ý nghĩa trong compacted topic |
|---|---|---|
| Non-null | Non-null | Record có trạng thái cho key |
| Non-null | Null | Tombstone cho đúng key bytes |
| Null | Non-null | Record không có key để compaction gom theo key |
| Null | Null | Không phải cách xóa một logical key |

Tombstone cần key bytes không null để chỉ ra khóa cần xóa. Gửi value null với key null không xóa customer nào.

### 5.2. Tombstone encoding mới không xóa key encoding cũ

Giả sử topic từng lưu customer-42 bằng encoding A. Sau khi đổi schema, producer gửi tombstone bằng encoding B:

~~~text
Record cũ:
  key bytes A -> customer-42
  value = ACTIVE

Tombstone mới:
  key bytes B -> customer-42
  value = null
~~~

Nếu A khác B, tombstone B chỉ xóa key B. Nó không xóa record key A. Sau compaction, trạng thái ACTIVE cũ có thể vẫn tồn tại.

Đây là một trong những lỗi nguy hiểm nhất khi thay đổi schema key của compacted topic: ứng dụng tưởng đã xóa entity nhưng consumer rebuild state vẫn khôi phục record cũ.

### 5.3. Tombstone phải được gửi đến đúng partition

Compaction chỉ diễn ra trong một partition. Để xóa record cũ, tombstone phải có:

- Serialized key bytes trùng chính xác với key cũ.
- Được append vào partition chứa record cũ.
- Value null.
- Được giữ đủ lâu để các consumer cần đọc tombstone có cơ hội nhận.

Nếu partition count hoặc partitioner đã thay đổi, gửi cùng old key qua partitioner hiện tại có thể đưa tombstone sang partition khác. Trong migration, có thể cần ghi rõ partition cũ và dùng serializer tạo đúng byte encoding cũ.

### 5.4. Tombstone không xóa ngay lập tức

Tombstone được giữ trong một khoảng thời gian cấu hình bằng delete.retention.ms để consumer có thời gian nhìn thấy thao tác xóa. Sau đó log cleaner có thể loại tombstone cùng các record cũ liên quan.

Compaction và tombstone cleanup là bất đồng bộ. Consumer khởi tạo state từ compacted topic phải đọc đủ lịch sử liên quan hoặc sử dụng snapshot/offset phù hợp. Không nên giả định tombstone sẽ tồn tại mãi hoặc biến mất ngay sau khi gửi.

## 6. Thay đổi partition count cũng ảnh hưởng key và compaction

Ngay cả khi serialized key bytes không thay đổi, tăng số partition có thể làm mapping của key thay đổi vì phép hash được lấy modulo partition count.

Ví dụ:

~~~text
Trước:
  partitionCount = 4
  customer-42 -> P1

Sau:
  partitionCount = 8
  customer-42 -> P5
~~~

Đây là mapping minh họa. Không phải mọi key đều đổi partition, nhưng một tập key đáng kể có thể được ánh xạ khác khi partition count thay đổi.

Record cũ vẫn nằm trong partition cũ. Kafka không tự di chuyển dữ liệu cũ sang partition mới và compaction không hợp nhất hai partition.

Nếu consumer đọc compacted topic để dựng state, cùng logical key có thể xuất hiện ở partition cũ và partition mới.

### 6.1. Schema change và partition expansion có thể cộng dồn rủi ro

Có hai thay đổi độc lập:

1. Key serializer tạo byte mới.
2. Partition count thay đổi.

Nếu cả hai diễn ra trong cùng một lần rollout, khó xác định record mới chuyển partition do nguyên nhân nào. Việc rollback cũng phức tạp hơn vì producer cũ và mới có thể cùng ghi các encoding khác nhau.

Nên tách các thay đổi, kiểm tra mapping trước và lên kế hoạch migration cho compacted topic.

## 7. Giữ key ổn định khi value schema cần tiến hóa

Một thiết kế an toàn thường là giữ key nhỏ, ổn định và độc lập với schema payload.

Ví dụ:

~~~java
public record CustomerState(
    String customerId,
    String name,
    String email,
    String region,
    String status,
    long version
) {}
~~~

Producer dùng customerId dạng chuỗi làm key và schema evolution chỉ áp dụng cho value:

~~~java
CustomerStateAvro avroValue = toAvro(state);

ProducerRecord<String, CustomerStateAvro> record =
    new ProducerRecord<>(
        "customer-state",
        state.customerId(),
        avroValue
    );

kafkaTemplate.send(record);
~~~

Cấu hình serializer minh họa:

~~~properties
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=io.confluent.kafka.serializers.KafkaAvroSerializer
~~~

Trong mô hình này:

- Key luôn là chuỗi customerId theo một quy tắc canonical.
- CustomerStateAvro là SpecificRecord được generate từ Avro schema; state là domain object được map sang Avro trước khi gửi.
- Value có thể tiến hóa schema độc lập.
- Thêm field vào CustomerState không làm thay đổi serialized key.
- Compaction tiếp tục nhận diện các phiên bản state bằng cùng key bytes.
- Tombstone chỉ cần dùng cùng StringSerializer và cùng customerId.

Đây là lựa chọn đơn giản nếu business identity có thể biểu diễn bằng một chuỗi hoặc binary identifier ổn định.

### 7.1. Key nên chứa ít field

Không nên đưa mọi thuộc tính có thể thay đổi vào key. Ví dụ không dùng cả customerId, displayName, region và tier nếu region hoặc tier có thể đổi.

Key tốt nên đại diện cho identity bất biến:

~~~text
customerId = customer-42
~~~

Thông tin có thể thay đổi nằm trong value:

~~~json
{
  "customerId": "customer-42",
  "region": "north",
  "tier": "GOLD",
  "status": "ACTIVE",
  "version": 12
}
~~~

Nếu key cần composite, xác định encoding canonical ngay từ đầu, ví dụ tenantId + customerId với delimiter/length-prefix rõ ràng. Không thay đổi cách nối hoặc chuẩn hóa giữa các producer.

### 7.2. Canonicalization là một phần của contract

Các giá trị sau có thể mang ý nghĩa giống nhau với business nhưng tạo byte khác nhau:

~~~text
Customer-42
customer-42
customer-42 với một dấu cách ở cuối
Unicode NFC form
Unicode NFD form
~~~

Cần thống nhất:

- Case sensitivity.
- Unicode normalization.
- Leading/trailing whitespace.
- Delimiter và escaping cho composite key.
- Charset, thường là UTF-8.
- Null và empty string semantics.
- Quy tắc versioning của key format.

Không tự động trim hoặc lowercase key nếu business phân biệt hai giá trị đó. Canonicalization phải là quy tắc nghiệp vụ được công bố trong contract.

## 8. Khi nào key schema thực sự cần tiến hóa?

Có thể có các yêu cầu:

- Thêm tenant ID vào key để tách namespace.
- Chuyển từ numeric ID sang composite ID.
- Chuẩn hóa định dạng UUID.
- Thêm namespace hoặc loại entity.
- Chuyển từ JSON key sang Avro/Protobuf key.
- Thay đổi encoding do serializer hoặc Schema Registry.

Trước khi thay đổi, cần trả lời:

1. Logical identity có thay đổi không?
2. Serialized bytes có thay đổi không?
3. Key có thể được hash sang partition khác không?
4. Topic có dùng compaction không?
5. Consumer có lưu state theo key không?
6. Có tombstone hoặc delete event nào cần dùng encoding cũ không?
7. Producer cũ và mới có thể chạy đồng thời không?
8. Có cần đọc lại toàn bộ topic để dựng state không?

Nếu chỉ muốn thêm metadata cho consumer, có thể đưa field vào value hoặc headers thay vì key. Nếu key thực sự phải đổi, hãy coi đó là một migration data contract, không phải một refactor serializer đơn giản.

## 9. Schema compatibility không đủ cho key migration

Schema Registry có thể dùng các compatibility mode như BACKWARD, FORWARD, FULL và các biến thể transitive. Policy cụ thể quyết định schema mới có thể được đọc bởi reader cũ hoặc ngược lại trong phạm vi nào.

Nhưng các mode này không kiểm tra:

- Hai logical key có serialize thành cùng byte không.
- Key có tiếp tục hash vào cùng partition không.
- Tombstone mới có xóa được record cũ không.
- Consumer state store có xuất hiện hai entry cho cùng entity không.
- Hai producer version có dùng cùng partitioner không.
- Partition count có thay đổi trong rollout không.

Vì vậy, quy trình review key schema cần thêm byte-level contract test.

### 9.1. Kiểm tra serialized bytes

Một test có thể serialize cùng logical ID bằng serializer cũ và mới, sau đó so sánh:

~~~java
byte[] oldBytes = oldKeySerializer.serialize(
    "customer-state",
    oldKey
);

byte[] newBytes = newKeySerializer.serialize(
    "customer-state",
    newKey
);

boolean sameEncoding = Arrays.equals(oldBytes, newBytes);
~~~

Nếu key bytes khác nhau, không nhất thiết migration bị cấm, nhưng phải đánh giá partition mapping và compaction identity. Test này cần chạy với đúng cấu hình serializer, schema ID, subject naming strategy và registry behavior dự kiến trong production.

### 9.2. Kiểm tra partition mapping

Với partitioner mặc định, có thể dùng cùng thuật toán và partition count để tính mapping dự kiến. Tuy nhiên, test thực tế nên dùng đúng Kafka client version và cấu hình partitioner của mọi producer.

Cần kiểm tra:

- Key V1 và V2 có đi vào cùng partition không?
- Producer Java và producer từ ngôn ngữ khác có cùng mapping không?
- Mapping thay đổi khi partition count thay đổi không?
- Custom partitioner có được triển khai nhất quán không?
- Có producer nào chỉ định partition tường minh không?

Không chỉ kiểm tra một key mẫu. Nên lấy tập key đại diện và đo tỷ lệ remap.

## 10. Chiến lược migration khi key encoding phải thay đổi

Nếu key bytes bắt buộc phải thay đổi, chọn một chiến lược có thể kiểm soát dữ liệu cũ, dữ liệu mới và tombstone.

### 10.1. Phương án A: giữ key bytes ổn định, chỉ đổi value schema

Đây thường là phương án ít rủi ro nhất:

- Giữ StringSerializer hoặc một canonical binary key.
- Giữ cùng logical key format qua các phiên bản.
- Thay đổi schema của value độc lập.
- Đưa version và metadata mới vào value hoặc headers.
- Giữ cùng partition mapping và compaction identity.

Phương án này phù hợp khi identity của entity không thay đổi.

### 10.2. Phương án B: tạo topic version mới

Nếu key format mới thay đổi identity hoặc partitioning, tạo topic mới thường dễ kiểm soát hơn sửa tại chỗ.

Quy trình khái quát:

1. Xác định schema key mới và partition count mục tiêu.
2. Tạo topic mới với cleanup policy, retention và replication phù hợp.
3. Đọc dữ liệu hiện tại hoặc snapshot để dựng lại state.
4. Chuyển đổi key sang encoding mới.
5. Publish dữ liệu sang topic mới với key mới.
6. Đồng bộ các thay đổi phát sinh trong lúc backfill bằng outbox/CDC hoặc dual-write có sequence.
7. So sánh số entity, version mới nhất và trạng thái giữa hai topic.
8. Chuyển consumer sang topic mới tại một watermark đã xác định.
9. Dừng ghi topic cũ sau khi xác nhận không còn producer/consumer phụ thuộc.
10. Giữ topic cũ theo thời gian rollback và retention đã thống nhất.

Cần tránh backfill và live update ghi đè lẫn nhau. Dùng aggregate version hoặc watermark để xác định record nào mới hơn.

### 10.3. Phương án C: tombstone các encoding cũ

Nếu phải giữ nguyên topic compacted và loại bỏ key encoding cũ, cần gửi tombstone cho từng serialized key cũ.

Quy trình:

1. Xác định mọi encoding cũ từng được dùng cho cùng logical entity.
2. Tái tạo chính xác byte key cũ hoặc lấy byte gốc từ dữ liệu lưu trữ.
3. Xác định partition chứa record cũ.
4. Publish tombstone có đúng byte key cũ và value null vào partition đó.
5. Publish record mới bằng key encoding mới theo partition mapping mới.
6. Theo dõi compaction và delete retention.
7. Dựng lại state từ đầu để xác minh key cũ không còn xuất hiện sau khi compaction hoàn tất.

Nếu entity từng được ghi bằng nhiều schema ID hoặc nhiều phiên bản serializer, có thể phải tombstone nhiều byte encoding khác nhau. Chỉ gửi tombstone theo object mới không đủ.

### 10.4. Gửi tombstone với byte key cũ

Trong migration, có thể dùng ByteArraySerializer để gửi chính xác key bytes cũ và chỉ định partition cũ:

~~~java
byte[] oldSerializedKey = loadOriginalKeyBytes(entityId);
int oldPartition = lookupOriginalPartition(entityId);

ProducerRecord<byte[], byte[]> tombstone =
    new ProducerRecord<>(
        "customer-state",
        oldPartition,
        oldSerializedKey,
        null
    );

byteArrayProducer.send(tombstone);
~~~

Đoạn mã minh họa nguyên tắc; producer cần cấu hình ByteArraySerializer cho cả key và value. Cần lấy đúng partition cũ từ metadata migration đáng tin cậy. Không tính partition cũ bằng partition count hiện tại nếu topic đã được mở rộng sau khi record cũ được ghi.

Nếu không có byte key cũ, cần khôi phục đúng serializer/schema ID đã tạo record lịch sử. Không thể suy ra chắc chắn byte cũ chỉ từ logical ID nếu quy tắc serialization đã thay đổi.

### 10.5. Không dual-write hai encoding vào cùng compacted topic một cách tùy tiện

Nếu publish cả key V1 và key V2 cho cùng entity vào cùng compacted topic, compaction sẽ coi chúng là hai key. Consumer có thể thấy hai state độc lập.

Dual-write có thể hữu ích trong migration có kiểm soát, nhưng cần:

- Gắn migration marker hoặc version.
- Xác định consumer nào đọc encoding nào.
- Không để side effect bị thực hiện hai lần.
- Có chiến lược tombstone key cũ.
- Có watermark/cutover rõ ràng.
- Xác minh state sau compaction.

Thường dễ vận hành hơn nếu dual-write sang hai topic version riêng, rồi chuyển consumer sang topic mới sau khi backfill và đối soát.

## 11. Producer cũ và mới chạy đồng thời

Trong rollout rolling deployment, producer cũ và mới có thể cùng hoạt động. Nếu key schema khác nhau, cùng entity có thể được ghi bằng hai encoding.

~~~text
Producer V1 -------- key bytes A ----+
                                     |
                                     v
                                customer-state
                                     ^
                                     |
Producer V2 -------- key bytes B ----+
~~~

Hậu quả:

- Logical entity xuất hiện dưới hai key bytes.
- Hai producer có thể chọn hai partition khác nhau.
- Consumer có thể xử lý hai luồng song song.
- Compaction giữ hai key riêng.
- Tombstone của V2 không xóa record V1.
- Rollback producer không tự hợp nhất state đã ghi bằng encoding mới.

Trước rollout, cần xác định thời điểm producer cũ dừng, cách xử lý record đã ghi và cách consumer đọc dữ liệu hỗn hợp. Không chỉ dựa vào việc schema mới backward compatible.

## 12. Ảnh hưởng tới Kafka Streams và state store

Kafka Streams dùng key để phân vùng dữ liệu và quản lý state store. Nếu key bytes hoặc partition mapping thay đổi, topology có thể quan sát cùng logical entity như một key khác hoặc ở task khác.

Ví dụ một KTable lưu customer state theo key:

~~~java
KTable<String, CustomerState> customers =
    builder.table(
        "customer-state",
        Consumed.with(Serdes.String(), customerStateSerde)
    );
~~~

Nếu key vẫn là String customerId và serde không đổi, value schema có thể tiến hóa độc lập mà state key vẫn ổn định.

Nếu chuyển sang Avro key có schema ID khác, state store/changelog có thể lưu các key bytes khác nhau cho cùng logical customer. Cần xem xét migration state store, repartition topic và application reset/rebuild strategy.

### 12.1. Repartition sau khi đổi key

Nếu topology đổi key bằng selectKey hoặc map, các thao tác grouping/join/stateful tiếp theo có thể cần repartition. Repartition tạo topic trung gian và phân phối theo key mới.

Nếu key mới là một encoding khác, mapping mới có thể khác. Hãy kiểm tra topology và state store trước khi triển khai. Không giả định thay đổi serde chỉ là thay đổi cách hiển thị key.

### 12.2. Rebuild state có thể cần thiết

Nếu state store đã chứa key encoding cũ, có thể cần:

- Dừng hoặc nâng version application có kiểm soát.
- Tạo application ID/state store mới nếu cần cô lập state.
- Rebuild từ topic đã migration.
- Đối soát số entity và version.
- Chuyển traffic sau khi state mới đạt watermark.
- Giữ đường rollback nếu state mới không đúng.

Chỉ xóa local state store mà không hiểu changelog và input topic có thể khiến ứng dụng dựng lại cùng lỗi hoặc mất khả năng phục hồi.

## 13. Thiết kế key contract bền vững

Một key contract nên được tài liệu hóa như một phần của API dữ liệu.

Nội dung nên có:

| Thuộc tính | Ví dụ | Quy tắc |
|---|---|---|
| Logical identity | customerId | Không đổi trong vòng đời entity |
| Serialized format | UTF-8 string | Cố định |
| Canonicalization | lowercase UUID hoặc exact ID | Được quy định rõ |
| Null semantics | Không cho phép null | Producer validate |
| Partitioning | Java default keyed partitioner | Producer cùng cấu hình |
| Schema evolution | Key format frozen | Metadata mới đưa vào value |
| Delete semantics | Non-null key + null value | Dùng đúng key bytes |
| Partition count | 12 partitions | Thay đổi phải qua migration review |
| Compatibility | Key subject policy | Kiểm tra độc lập với value subject |

Một nguyên tắc hữu ích là giữ key như một định danh kỹ thuật tối thiểu. Đặt các field mô tả, trạng thái và thuộc tính có thể thay đổi trong value.

### 13.1. Composite key cần encoding không mơ hồ

Nếu cần tenantId và customerId, không nên nối chuỗi tùy tiện:

~~~text
tenant + "-" + customer
~~~

Nếu giá trị có thể chứa dấu phân cách, hai cặp khác nhau có thể tạo cùng chuỗi. Dùng length-prefix, escaping chuẩn hoặc định dạng canonical được version hóa.

Ví dụ biểu diễn khái niệm:

~~~text
tenantLength | tenantBytes | customerLength | customerBytes
~~~

Nếu thay đổi encoding composite sau khi topic đã có dữ liệu, đây vẫn là một key migration và cần xử lý old key bytes/tombstone.

## 14. Checklist trước khi thay đổi key schema

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Logical identity | Entity ID có thay đổi hay chỉ schema object thay đổi? |
| Serialized bytes | Byte key trước và sau có giống nhau không? |
| Schema Registry | Key subject có compatibility policy riêng không? |
| Wire format | Schema ID/framing có làm byte prefix thay đổi không? |
| Partitioner | Các producer có dùng cùng partitioning rule không? |
| Partition count | Số partition có thay đổi trong cùng rollout không? |
| Compaction | Topic có cleanup.policy=compact hoặc compact,delete không? |
| Tombstone | Có thể tái tạo đúng old key bytes và partition không? |
| Producer rollout | Producer V1 và V2 có chạy đồng thời không? |
| Consumer | Consumer có thể thấy cùng entity dưới hai key khác nhau không? |
| Kafka Streams | State store/changelog có cần rebuild không? |
| Migration | Có topic mới, backfill, watermark và cutover plan không? |
| Rollback | Có thể quay lại producer cũ mà không tạo thêm key identity không? |
| Validation | Có byte-level, partition mapping và compaction test không? |

## 15. Lab: quan sát key schema ảnh hưởng đến partition và compaction

Có thể tạo một topic thử nghiệm với cleanup policy compact và hai producer dùng key serializer khác nhau.

### Bước 1: Tạo topic compacted

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic customer-state-lab \
  --partitions 4 \
  --replication-factor 1 \
  --config cleanup.policy=compact
~~~

Replication factor 1 chỉ phù hợp môi trường lab đơn broker, không phải cấu hình production.

### Bước 2: Ghi key bằng encoding cũ

Ghi trạng thái customer-42 bằng key serializer V1. Lưu lại serialized bytes, partition và offset của record.

### Bước 3: Ghi cùng logical ID bằng encoding mới

Dùng schema/serializer V2 để serialize customer-42. So sánh byte array với V1 và kiểm tra partition được chọn.

Không chỉ nhìn giá trị key sau deserialize; cần ghi lại byte representation hoặc hash để thấy sự khác biệt.

### Bước 4: Quan sát compacted topic

Chờ log cleaner chạy. Đọc lại topic bằng consumer phù hợp serializer. Nếu byte key khác nhau, có thể thấy hai logical record cùng customerId nhưng khác key encoding.

Compaction là bất đồng bộ; lab cần chờ cleaner xử lý segment đủ điều kiện. Không kết luận compaction lỗi chỉ vì record cũ vẫn xuất hiện ngay sau khi publish.

### Bước 5: Gửi tombstone

Gửi value null với key V2 rồi quan sát kết quả. Tombstone V2 không xóa record V1 nếu byte key khác nhau.

Sau đó gửi tombstone bằng đúng byte key V1 vào partition cũ và chờ compaction. So sánh state được dựng lại trước và sau.

### Bước 6: Thử thay đổi partition count

Tạo một topic lab khác hoặc tăng partition count trong môi trường thử nghiệm. Tính lại mapping của một tập key và quan sát record cũ/new partition. Không thực hiện thí nghiệm thay đổi partition count trên topic production chỉ để kiểm chứng.

## 16. Những hiểu lầm thường gặp

- **“Cùng customerId nghĩa là Kafka xem là cùng key.”** Kafka sử dụng serialized key bytes.
- **“Schema Registry compatibility bảo đảm partition không đổi.”** Compatibility không kiểm tra hash mapping hoặc byte identity.
- **“Thêm field có default là thay đổi an toàn cho key.”** Schema mới có thể tạo schema ID và serialized bytes khác.
- **“Cùng key hash vào cùng partition mãi mãi.”** Partition count hoặc partitioner thay đổi có thể làm mapping đổi.
- **“Compaction gom record theo logical ID.”** Compaction nhận diện byte key trong từng partition.
- **“Tombstone value null sẽ xóa mọi phiên bản của entity.”** Tombstone chỉ xóa đúng key bytes trong đúng partition.
- **“Tombstone mới có thể xóa key cũ sau khi deserialize.”** Broker không deserialize để so sánh schema.
- **“Compaction diễn ra ngay khi gửi record mới.”** Log cleaner chạy bất đồng bộ.
- **“Tăng partition chỉ ảnh hưởng throughput.”** Nó có thể ảnh hưởng key mapping, ordering và compacted state.
- **“Đổi key serializer có thể rollback đơn giản.”** Record đã ghi bằng encoding mới vẫn tồn tại và có thể tạo logical duplicate.
- **“Kafka Streams tự hợp nhất key cũ và mới.”** State store và repartition phụ thuộc serialized key/serde và topology.

## 17. Kết luận

Key của Kafka cần được quản lý như một data contract ổn định. Partitioner sử dụng serialized key bytes để chọn partition; log compaction dùng byte key trong từng partition để nhận diện các phiên bản của cùng khóa. Thay đổi schema có thể làm byte key thay đổi dù logical ID không đổi. Khi đó record có thể đi sang partition khác, compaction giữ hai key riêng và tombstone mới không xóa được record cũ.

Schema compatibility là điều kiện cần cho khả năng đọc dữ liệu giữa các phiên bản, nhưng không thay thế kiểm tra byte identity, partition mapping và tombstone behavior. Với compacted topic, nên giữ key nhỏ, canonical và ổn định; cho schema tiến hóa chủ yếu ở value. Nếu key bắt buộc phải đổi, hãy thực hiện migration có kiểm soát bằng topic version mới hoặc tombstone đúng byte key cũ và đúng partition, kèm backfill, watermark, đối soát và kế hoạch rollback.

Trước khi rollout, hãy test serialized bytes bằng đúng serializer production, tính mapping với đúng partition count và chạy thử compaction/tombstone trên topic lab. Điều này giúp phát hiện sớm logical duplicate, stale state và lỗi xóa dữ liệu trước khi chúng xuất hiện trong hệ thống thực tế.
