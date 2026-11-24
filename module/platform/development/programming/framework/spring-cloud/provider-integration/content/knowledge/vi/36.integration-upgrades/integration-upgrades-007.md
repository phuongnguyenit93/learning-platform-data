# Kiểm thử hồi quy hành vi và tương thích dữ liệu đang lưu

Một bản nâng cấp có thể biên dịch thành công, vượt qua unit test và vẫn làm hỏng dữ liệu đã được ghi bởi phiên bản trước. Ví dụ: model mới đổi tên enum, serializer thay cách biểu diễn thời gian, migration thêm cột bắt buộc nhưng không backfill, hoặc consumer mới không đọc được message còn nằm trong queue từ tuần trước. Lỗi chỉ xuất hiện khi ứng dụng gặp dữ liệu thật đã tồn tại.

Vì vậy, kiểm thử hồi quy khi nâng cấp Spring Boot và thư viện Spring Cloud phải kiểm tra cả **hành vi của ứng dụng** lẫn **khả năng đọc, ghi và chuyển đổi dữ liệu qua nhiều phiên bản**. Cần giữ các mẫu dữ liệu đại diện cho phiên bản cũ, chạy migration trên database có dữ liệu, kiểm tra payload đã lưu và kiểm thử các luồng cloud thực tế. Một bài test chỉ tạo database rỗng hoặc publish message mới rồi consume ngay sẽ không chứng minh được dữ liệu cũ vẫn tương thích.

Bài thuộc chương **Nâng cấp tích hợp** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Bài tập trung vào regression test cho database, object storage, message broker, serialization và các thay đổi provider SDK.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt regression test hành vi, integration test, contract test và data migration test.
- Xác định các phiên bản ứng dụng cần tương thích trong quá trình rolling deployment và replay dữ liệu.
- Tạo bộ golden fixtures đại diện cho payload, record và object đã được ghi bởi phiên bản cũ.
- Kiểm thử schema evolution cho JSON, Avro, Protocol Buffers và message envelope.
- Chạy database migration trên snapshot có dữ liệu và xác minh các invariant sau migration.
- Kiểm tra metadata, checksum, versioning và conditional write của object storage.
- Kiểm thử message ordering, duplicate, redelivery, ack, dead-letter và idempotency.
- Sử dụng Testcontainers, emulator và cloud sandbox đúng phạm vi.
- Phát hiện khác biệt giữa emulator và dịch vụ managed thực tế.
- Thiết kế canary, backfill, đối soát và rollback có tính đến dữ liệu đã ghi.

## 2. Vì sao nâng cấp cần kiểm thử dữ liệu cũ?

Ứng dụng cloud thường lưu dữ liệu ở nhiều nơi. Mỗi nơi có vòng đời và quy tắc tương thích riêng:

| Nơi lưu dữ liệu | Dữ liệu cần bảo vệ | Lỗi thường gặp sau nâng cấp |
| --- | --- | --- |
| Database quan hệ | Row, schema, index, constraint, sequence | Migration mất dữ liệu, đổi kiểu cột, default sai, query cũ không còn chạy |
| NoSQL | Partition key, sort key, document attributes, index | Key encoding đổi, kiểu attribute đổi, item cũ không được deserialize |
| Object storage | Bytes, metadata, tags, content type, version ID, checksum | ETag bị hiểu nhầm là checksum, metadata mất, URL/version cũ không đọc được |
| Message broker | Payload, headers, schema version, message ID, ordering key | Consumer mới không đọc message cũ, duplicate hoặc ack sai |
| Cache | Serialized value, key format, TTL | Cache cũ không deserialize hoặc key namespace thay đổi |
| Secret/config store | Tên key, version, format, encoding | Ứng dụng đọc nhầm version hoặc không còn parse được secret |
| Search/index | Document mapping, analyzer, query fields | Index cũ không tương thích với query mới |

Một regression test chỉ kiểm tra kết quả HTTP hoặc method return chưa đủ. Cần kiểm tra cả tác động đã được ghi lại: row trong database, object trong bucket, event trong queue và side effect được thực hiện đúng số lần.

### 2.1. Phân biệt các hướng tương thích

Khi nhiều phiên bản cùng tồn tại, hãy diễn đạt tương thích theo hướng writer và reader thay vì chỉ ghi chung chung “backward compatible”.

| Kiểm tra | Câu hỏi |
| --- | --- |
| Reader mới đọc dữ liệu cũ | Phiên bản N có đọc được record/message do N-1 ghi không? |
| Reader cũ đọc dữ liệu mới | Trong rolling deployment, consumer N-1 có đọc được payload do producer N ghi không? |
| Reader mới đọc dữ liệu đã chuyển đổi | Sau migration, code mới có hiểu được cả record cũ và record đã backfill không? |
| Replay dữ liệu cũ | Message/object được phát lại sau nhiều ngày hoặc nhiều tháng có còn đọc được không? |
| Rollback code | Code N-1 có chạy an toàn trên schema đã được mở rộng bởi N không? |

Trong tài liệu schema registry, thuật ngữ forward/backward compatibility có thể được định nghĩa theo hướng writer/reader riêng. Vì vậy, test plan nên ghi rõ cặp phiên bản và hướng đọc, ví dụ `writer=N-1, reader=N`, thay vì chỉ ghi “test backward compatibility”.

### 2.2. Lập ma trận phiên bản

Ví dụ ứng dụng triển khai theo rolling update:

| Writer / Reader | N-1 reader | N reader |
| --- | --- | --- |
| N-1 writer | Luồng hiện tại | Bắt buộc kiểm tra dữ liệu cũ |
| N writer | Kiểm tra nếu rollback/consumer cũ còn chạy | Luồng mới |

Nếu queue giữ message lâu, thời gian tương thích phải bao phủ thời gian retention và replay. Nếu database còn record từ nhiều năm trước, bộ fixture phải bao phủ các phiên bản schema còn tồn tại trong production, không chỉ phiên bản ngay trước lần deploy.

## 3. Thiết kế bộ dữ liệu regression
+
Bộ dữ liệu regression phải đại diện cho dữ liệu đã tồn tại, gồm cả trường hợp phổ biến và dữ liệu biên. Không nên tạo tất cả fixture từ model mới vì serializer mới có thể vô tình chuẩn hóa hoặc loại bỏ đúng trường hợp cũ cần kiểm tra.

### 3.1. Golden fixtures theo phiên bản

Lưu fixture theo phiên bản writer hoặc schema:

```text
src/test/resources/compatibility/
  invoice/
    v1/
      invoice-paid.json
      invoice-null-customer.json
      invoice-large-amount.json
    v2/
      invoice-issued.json
      invoice-with-currency.json
  events/
    v1/
      invoice-created.json
    v2/
      invoice-created.json
      invoice-cancelled.json
  objects/
    v1/
      metadata.json
      expected-sha256.txt
    v2/
      metadata.json
      expected-sha256.txt
```

Mỗi fixture cần ghi rõ:

- Phiên bản ứng dụng hoặc schema đã tạo dữ liệu.
- Format/encoding, content type và compression nếu có.
- Mốc thời gian và timezone.
- Các giả định nghiệp vụ liên quan đến default hoặc field bị thiếu.
- Kết quả đọc mong đợi.
- Checksum nếu fixture chứa bytes hoặc object.

Không sửa fixture cũ để phù hợp với model mới. Khi contract thay đổi có chủ đích, thêm fixture version mới và giữ fixture cũ để tiếp tục kiểm tra reader mới.

### 3.2. Những trường hợp biên nên có

Một bộ fixture cho invoice có thể bao gồm:

- Field bị thiếu hoàn toàn và field có giá trị `null`.
- Enum chứa giá trị đã bị xóa hoặc không còn được code mới biết.
- Decimal có nhiều chữ số thập phân, số âm và giá trị sát giới hạn.
- Timestamp có timezone khác UTC, thời điểm chuyển ngày và độ chính xác nano/millisecond.
- Chuỗi Unicode, ký tự tổ hợp, tên dài và dữ liệu có dấu.
- Mảng rỗng, mảng lớn, object lồng nhau và field không được định nghĩa trong model hiện tại.
- ID cũ, ID có prefix, UUID và key có phân biệt hoa thường.
- Payload rỗng, payload lớn, dữ liệu nén và binary.
- Trường hợp duplicate event hoặc event đến không đúng thứ tự.

Nếu dữ liệu cũ có thể chứa field lạ, kiểm tra consumer mới có thể bỏ qua, lưu giữ hoặc từ chối field đó theo đúng contract. Không tự động xóa dữ liệu không nhận biết được nếu nghiệp vụ yêu cầu bảo toàn.

### 3.3. Không đưa dữ liệu nhạy cảm vào fixture

Tạo fixture từ dữ liệu production đã được ẩn danh hoặc tổng hợp. Không lưu access token, connection string, secret, thông tin cá nhân có thể nhận diện hoặc khóa mã hóa vào repository. Nếu fixture cần kiểm tra mã hóa, dùng khóa test riêng và dữ liệu giả lập.

## 4. Kiểm thử database migration trên dữ liệu có sẵn

Kiểm tra migration trên database rỗng chỉ chứng minh schema mới tạo được. Production thường có hàng triệu row, giá trị null lịch sử, dữ liệu được ghi bởi nhiều phiên bản và index có kích thước lớn.

### 4.1. Kiểm tra từ nhiều baseline

Với mỗi baseline còn tồn tại trong production, tạo database từ schema/version đó, nạp fixture và chạy migration đến phiên bản đích.

| Baseline | Nội dung test |
| --- | --- |
| Database mới | Toàn bộ migration chạy từ đầu |
| Schema N-2 | Migration đi qua các phiên bản trung gian |
| Schema N-1 | Nâng cấp trực tiếp từ bản gần nhất |
| Snapshot dữ liệu đại diện | Row cũ, null, duplicate, giá trị biên và dữ liệu lớn |
| Snapshot quy mô gần production | Thời gian migration, lock, index build, transaction và dung lượng |

Nếu dự án dùng Flyway, versioned migration là lịch sử thay đổi được quản lý theo thứ tự. Không sửa migration đã được áp dụng ở môi trường dùng chung; hãy tạo migration mới. `flyway validate` kiểm tra migration đã áp dụng với migration hiện có, bao gồm tên, loại và checksum. Đây là kiểm tra lịch sử migration, không thay thế việc kiểm tra dữ liệu sau khi chạy migration.

### 4.2. Kiểm tra invariant trước và sau migration

Trước khi chạy migration, ghi lại các invariant cần giữ:

- Tổng số row theo bảng và theo trạng thái.
- Số lượng null/empty ở các field quan trọng.
- Tổng tiền hoặc tổng số lượng theo nhóm nghiệp vụ.
- Số lượng khóa ngoại mồ côi.
- Tính duy nhất của business key.
- Min/max timestamp và các khoảng dữ liệu lịch sử.
- Tổng số object/event tham chiếu đến record.
- Các checksum hoặc digest của trường dữ liệu quan trọng.

Sau migration, chạy lại các truy vấn đối soát. Chỉ so sánh row count là chưa đủ: migration có thể giữ số row nhưng làm sai giá trị, timezone hoặc precision.

### 4.3. Ví dụ migration mở rộng schema

Giả sử schema cũ lưu `amount` nhưng chưa có `currency`. Nếu ứng dụng mới yêu cầu currency, không nên thêm cột `NOT NULL` mà không xử lý row cũ.

Migration mở rộng:

```sql
-- V2__add_currency_to_invoice.sql
ALTER TABLE invoice
    ADD COLUMN currency CHAR(3);

UPDATE invoice
SET currency = 'VND'
WHERE currency IS NULL;

ALTER TABLE invoice
    ALTER COLUMN currency SET NOT NULL;
```

Ví dụ chỉ đúng nếu mọi row cũ thực sự được hiểu là VND. Nếu currency cũ phụ thuộc tenant hoặc thời điểm giao dịch, phải backfill bằng dữ liệu nguồn có căn cứ. Không dùng currency hiện tại của hệ thống để đoán currency của giao dịch lịch sử.

### 4.4. Expand-contract cho migration có rolling deployment

Khi schema thay đổi lớn, triển khai theo nhiều bước:

1. **Expand:** thêm cột/bảng mới ở trạng thái tương thích; giữ cột cũ.
2. **Deploy code tương thích:** code đọc được cả định dạng cũ và mới, ghi song song khi cần.
3. **Backfill:** chuyển dữ liệu cũ theo batch có checkpoint và khả năng chạy lại.
4. **Reconcile:** so sánh số row, giá trị và invariant giữa hai dạng.
5. **Switch read:** chuyển reader sang cột/format mới.
6. **Observe:** giữ thời gian quan sát và xác nhận không còn consumer cần format cũ.
7. **Contract:** xóa cột/constraint cũ trong một migration riêng sau khi rollback window kết thúc.

Không thực hiện expand và contract trong cùng một release nếu phiên bản ứng dụng cũ vẫn có thể chạy trong rolling deployment hoặc cần rollback.

### 4.5. Test migration bằng Testcontainers và Flyway

Spring Boot hỗ trợ Testcontainers; với container được nhận diện, `@ServiceConnection` tạo connection details để auto-configuration sử dụng. Cần thêm `spring-boot-testcontainers` trong test scope. Connection details này được ưu tiên hơn connection-related properties; điều này hữu ích khi test cần dùng database container thay vì endpoint trong file cấu hình.

Ví dụ:

```java
@Testcontainers
class InvoiceMigrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void migratesExistingInvoiceWithoutChangingItsMeaning() throws Exception {
        var dataSource = new org.postgresql.ds.PGSimpleDataSource();
        dataSource.setURL(postgres.getJdbcUrl());
        dataSource.setUser(postgres.getUsername());
        dataSource.setPassword(postgres.getPassword());

        Flyway oldVersion = Flyway.configure()
            .dataSource(dataSource)
            .locations("classpath:db/migration")
            .target(MigrationVersion.fromVersion("1"))
            .load();

        oldVersion.migrate();

        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(
                 "INSERT INTO invoice(id, amount, status, created_at) " +
                 "VALUES (?, ?, ?, ?)")) {
            statement.setObject(1, UUID.fromString(
                "8e52a9c8-3d11-4d7e-a932-3d6bcb54f1a0"));
            statement.setBigDecimal(2, new BigDecimal("125.50"));
            statement.setString(3, "PAID");
            statement.setObject(4, OffsetDateTime.parse(
                "2025-10-12T09:30:00+07:00"));
            statement.executeUpdate();
        }

        Flyway latest = Flyway.configure()
            .dataSource(dataSource)
            .locations("classpath:db/migration")
            .load();

        latest.migrate();

        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(
                 "SELECT amount, status, currency FROM invoice WHERE id = ?")) {
            statement.setObject(1, UUID.fromString(
                "8e52a9c8-3d11-4d7e-a932-3d6bcb54f1a0"));

            try (var result = statement.executeQuery()) {
                assertTrue(result.next());
                assertEquals(new BigDecimal("125.50"), result.getBigDecimal("amount"));
                assertEquals("PAID", result.getString("status"));
                assertEquals("VND", result.getString("currency"));
            }
        }
    }
}
```

Trong dự án thật, thay `VND` bằng quy tắc backfill được xác minh từ nghiệp vụ. Bổ sung fixture cho row null, amount âm/biên, timestamp và khóa ngoại. Có thể dùng `@SpringBootTest` cùng `@ServiceConnection` cho test auto-configuration của repository sau khi migration hoàn tất.

## 5. Kiểm thử tương thích JSON, serializer và message schema
+
Message đang nằm trong SQS, Pub/Sub hoặc Service Bus có thể được consumer đọc sau khi producer đã nâng cấp. Do đó, kiểm tra serializer mới tạo ra JSON hợp lệ chưa đủ; cần chứng minh consumer mới đọc được payload đã được ghi từ trước.

### 5.1. Giữ message envelope ổn định

Một event nên có metadata đủ để consumer nhận biết phiên bản và xử lý duplicate:

```json
{
  "eventId": "evt-2025-000184",
  "eventType": "InvoiceIssued",
  "schemaVersion": 1,
  "occurredAt": "2025-10-12T09:30:00+07:00",
  "aggregateId": "invoice-100184",
  "payload": {
    "amount": 125.50,
    "status": "PAID"
  }
}
```

Khi bổ sung currency, có thể tạo schema version mới:

```json
{
  "eventId": "evt-2025-000184",
  "eventType": "InvoiceIssued",
  "schemaVersion": 2,
  "occurredAt": "2025-10-12T09:30:00+07:00",
  "aggregateId": "invoice-100184",
  "payload": {
    "amount": 125.50,
    "currency": "VND",
    "status": "PAID"
  }
}
```

Consumer mới phải đọc được version 1 theo quy tắc nghiệp vụ đã công bố. Không mặc định mọi invoice cũ đều dùng currency của cấu hình hiện tại nếu dữ liệu nguồn không chứng minh điều đó.

### 5.2. Test writer/reader theo phiên bản

Tạo các test riêng:

- Đọc fixture v1 bằng model/consumer hiện tại.
- Đọc fixture v2 bằng consumer hiện tại.
- Ghi payload mới rồi xác minh field, type, content type và header.
- Nếu rolling deployment yêu cầu, thử consumer cũ đọc payload mới.
- Thử unknown enum, field bổ sung, field thiếu, `null` và field có kiểu không mong đợi.
- Replay cùng event hai lần để xác minh idempotency.
- Thử message được ghi trước nhiều phiên bản và vẫn nằm trong retention period.

Không so sánh JSON chỉ theo thứ tự field. JSON object không yêu cầu thứ tự thuộc tính; hãy so sánh cấu trúc và giá trị theo contract. Với binary Avro/Protobuf, kiểm tra schema và wire compatibility thay vì so sánh byte output nếu serialization không đảm bảo byte-for-byte ổn định.

### 5.3. Avro và Protocol Buffers

Với Avro, cần phân biệt writer schema của message và reader schema của consumer. Spring Cloud Stream Schema Registry dùng content type mang version/schema reference để tìm writer schema, sau đó thực hiện schema resolution với reader schema. Test nên giữ fixture được ghi bởi mỗi schema version còn được sử dụng.

Với Protocol Buffers:

- Không tái sử dụng field number đã từng phát hành.
- Khi bỏ field, reserve field number/name theo quy tắc protobuf.
- Giữ đúng wire type và semantics của field.
- Test payload nhị phân cũ với generated class mới.
- Kiểm tra enum value mới/không biết và default của scalar field.

Google Pub/Sub hỗ trợ schema Avro và Protocol Buffers. Pub/Sub kiểm tra message publish theo schema gắn với topic; các revision của schema phải tương thích forward và backward với nhau. Dù vậy, ứng dụng vẫn cần test logic chuyển đổi và default ở reader của chính nó.

### 5.4. Spring Cloud Contract và contract test

Spring Cloud Contract hỗ trợ producer-driven và consumer-driven contract testing. Dùng contract để kiểm tra HTTP API và message boundary giữa các service:

- Producer test xác minh payload, headers và status mà service phát ra.
- Consumer test xác minh consumer chấp nhận contract của producer.
- Stub test giúp service chạy độc lập trong CI.
- Integration test với broker thật/emulator kiểm tra binding, serialization, ack và retry.

Contract test không thay thế test nghiệp vụ đầy đủ hoặc migration test trên dữ liệu lưu trữ. Một contract có thể đúng nhưng consumer vẫn xử lý sai giá trị lịch sử.

## 6. Kiểm thử object storage và dữ liệu nhị phân

Object storage giữ cả bytes và metadata. Một bản nâng cấp SDK hoặc cách upload có thể thay đổi content type, metadata, checksum, versioning, encryption hoặc conditional write.

### 6.1. Không dùng ETag làm checksum tổng quát

| Provider | Điều cần kiểm tra |
| --- | --- |
| Amazon S3 | ETag không phải lúc nào cũng là MD5 của toàn object, đặc biệt với multipart upload hoặc SSE-KMS/SSE-C; dùng checksum rõ ràng |
| Google Cloud Storage | CRC32C là checksum được khuyến nghị; MD5 không có cho composite object hoặc một số multipart upload |
| Azure Blob Storage | Kiểm tra Content-MD5/CRC64 khi dùng; ETag dùng cho conditional request và optimistic concurrency |

Đối với S3, SDK hiện đại có thể tự tính checksum; hành vi mặc định thay đổi theo version SDK. Hãy kiểm tra checksum thực tế được lưu và so sánh với checksum tính từ bytes. Không viết test giả định ETag luôn bằng MD5.

### 6.2. Bộ test object storage

Với mỗi object fixture, kiểm tra:

- Bytes tải về khớp checksum mong đợi.
- Content type, content encoding, content disposition và metadata.
- Object key, prefix, Unicode và ký tự đặc biệt.
- Encryption mode/KMS key và quyền đọc.
- Multipart upload và object lớn.
- Range download và resume.
- Conditional write bằng ETag/version.
- Versioning, delete marker và restore nếu bucket/account bật versioning.
- Retention, lifecycle và object lock nếu ứng dụng phụ thuộc.

Với S3 Versioning, `PUT` tạo version mới và `DELETE` không chỉ định version ID tạo delete marker. Test cần xác minh hành vi restore hoặc đọc version cụ thể nếu nghiệp vụ dựa vào versioning. Với Azure Blob, ETag đổi sau write; `If-Match` giúp phát hiện object bị cập nhật đồng thời. Với GCS, dùng CRC32C để xác minh toàn object khi download/upload.

### 6.3. Kiểm tra metadata như một phần của contract

Metadata có thể chứa business ID, tenant, content classification hoặc schema version. Nếu code mới đổi tên metadata key hoặc chữ hoa/thường, object vẫn tải được nhưng downstream job có thể không phân loại đúng.

Lập expected metadata theo contract và so sánh key/value sau upload. Nếu metadata cần thay đổi, viết migration hoặc backfill rõ ràng; đừng giả định chỉ cập nhật code là các object đã lưu tự đổi theo.

## 7. Kiểm thử message broker và hành vi consumer

Dữ liệu trong broker có thể tồn tại lâu hơn một phiên bản ứng dụng. Khi nâng SDK hoặc Spring Cloud integration, kiểm tra message cũ, header, settlement và duplicate.

### 7.1. Kiểm tra các thuộc tính của message

Với SQS/SNS, Pub/Sub, Service Bus, test:

- Body bytes và content type.
- Message ID, correlation ID và application properties/attributes.
- Schema version và event type.
- Ordering key/session/partition key nếu có.
- Visibility timeout hoặc lock duration.
- Ack/complete/abandon/nack behavior.
- Retry count, dead-letter reason và redelivery.
- Message TTL, retention và scheduled delivery.
- Duplicate detection và idempotency key.

Azure Service Bus có thể redeliver message nếu lock bị mất, consumer restart hoặc operation thành công nhưng acknowledgement bị mất. Duplicate detection dựa trên MessageId trong cửa sổ cấu hình; nó không thay thế idempotent processing ở consumer. Test cả send-side retry lẫn receive-side redelivery.

### 7.2. Test idempotency bằng dữ liệu thật

Một consumer có thể nhận cùng event nhiều lần. Test cần xác minh:

1. Lần đầu xử lý event tạo đúng side effect.
2. Lần thứ hai với cùng event ID không tạo thêm invoice, payment hoặc ledger entry.
3. Nếu xử lý lần đầu lỗi giữa chừng, retry có thể tiếp tục an toàn.
4. Message chỉ được ack/complete sau khi trạng thái nghiệp vụ đã được commit.
5. Duplicate event không làm tăng số tiền hoặc thay đổi trạng thái sai.

Nếu dùng outbox/inbox, test transaction boundary và unique constraint của event ID. Nếu gửi message rồi mới commit database, hoặc commit rồi mới gửi mà không có outbox, có thể tạo mất event hoặc duplicate khi process crash.

## 8. Dùng Testcontainers và emulator đúng phạm vi
+
Local integration test giảm chi phí và tăng tốc feedback, nhưng emulator không mô phỏng toàn bộ dịch vụ managed. Hãy chia test thành ba tầng:

| Tầng | Mục tiêu | Môi trường |
| --- | --- | --- |
| Unit/contract | Serializer, mapper, domain rule, schema compatibility | JUnit, fixture, Spring Cloud Contract |
| Local integration | Repository, SDK call, message flow, object metadata cơ bản | Testcontainers, emulator |
| Cloud sandbox | IAM/RBAC, encryption, versioning, retention, quota, managed identity và service-specific behavior | Tài khoản/project test riêng |

### 8.1. Spring Boot Testcontainers

Spring Boot hỗ trợ `@ServiceConnection` để tự tạo connection details cho container được nhận diện. Cần thêm `spring-boot-testcontainers` trong test scope. Connection details được ưu tiên hơn connection-related configuration properties; điều này hữu ích khi test cần dùng database container thay vì endpoint trong file cấu hình.

Ví dụ PostgreSQL:

```java
@Testcontainers
@SpringBootTest
class InvoiceRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    InvoiceRepository repository;

    @Test
    void readsInvoiceAfterSchemaMigration() {
        Invoice invoice = repository.findById("invoice-100184")
            .orElseThrow();

        assertEquals(new BigDecimal("125.50"), invoice.amount());
        assertEquals("VND", invoice.currency());
    }
}
```

Test trên cần có fixture đã được nạp vào database sau migration. Với migration regression, dùng cách chạy schema từ baseline cũ, chèn fixture, rồi áp dụng migration mới như ví dụ ở phần database.

### 8.2. AWS

Có thể dùng DynamoDB Local cho repository test và môi trường sandbox cho service behavior. DynamoDB Local không mô phỏng đầy đủ managed service: account/region ở client không được hỗ trợ, provisioned throughput bị bỏ qua và parallel scan không được hỗ trợ. Vì vậy không dùng nó để kết luận quota, throughput hoặc behavior theo region đúng production.

Với S3, kiểm tra checksum, metadata, versioning, encryption và IAM trên bucket sandbox. Nếu dùng emulator bên thứ ba, ghi rõ những API/feature được mô phỏng và xác minh các behavior quan trọng trên AWS thật.

### 8.3. Google Cloud

Pub/Sub emulator hỗ trợ publish/receive, ordering, replay, dead-letter forwarding, retry policy, filtering và Avro schema. Tuy nhiên, emulator không hỗ trợ IAM operations, configurable message retention hoặc subscription expiration; schema Protocol Buffers cũng nằm trong danh sách giới hạn được công bố.

Do đó:

- Dùng emulator để test serialization, publish/consume, ordering và retry cơ bản.
- Dùng project sandbox để test IAM, schema revision thực tế, retention và quyền.
- Dùng fixture schema revision cũ để kiểm tra consumer mới.
- Dùng checksum CRC32C khi kiểm tra object Cloud Storage.

### 8.4. Azure

Azurite hỗ trợ Blob, Queue và Table Storage. Nó không hỗ trợ Azure Files hoặc Azure Data Lake Storage Gen2; endpoint local cũng khác endpoint cloud. Dùng Azurite cho CRUD, metadata và basic storage behavior, rồi test các feature không được mô phỏng trên tài khoản sandbox.

Azure Service Bus emulator hỗ trợ AMQP TCP và test tuần tự, nhưng có các giới hạn đã công bố: không hỗ trợ Microsoft Entra ID, partitioned entities, AMQP WebSockets hoặc large messages; data/entity không persist sau khi container restart. Không dùng emulator để chứng minh managed identity, partition behavior, disaster recovery hoặc retention trong production.

### 8.5. Bảng lựa chọn môi trường

| Hành vi | Unit/fixture | Emulator | Cloud sandbox |
| --- | --- | --- | --- |
| JSON/Avro decode payload cũ | Có | Có thể | Không bắt buộc |
| Database migration | Không đủ | Testcontainers DB | Staging snapshot nếu cần scale |
| S3 checksum/versioning/KMS | Fixture checksum | Emulator tùy chọn | Cần cho behavior AWS-specific |
| Pub/Sub publish/ordering | Có thể mock | Có | Cần cho IAM/retention |
| Azure Blob metadata | Fixture | Azurite | Cần cho feature không được Azurite hỗ trợ |
| Service Bus Entra ID/partition | Không | Không | Cần |
| IAM/RBAC/managed identity | Không | Thường không | Cần |
| Quota/performance/latency | Benchmark giả lập | Không đủ | Cần |

## 9. Xây dựng regression suite theo thay đổi

Không chạy mọi test với mọi commit nếu chi phí quá cao. Gắn mỗi thay đổi với một bộ test tối thiểu và chạy full compatibility suite trước khi release.

| Loại thay đổi | Test bắt buộc |
| --- | --- |
| Nâng Spring Boot/Jackson | Golden JSON fixtures, unknown field/enum, timestamp, decimal, null |
| Nâng provider SDK | Client configuration, checksum, metadata, retry, timeout, resource close |
| Đổi database schema | Migration từ baseline cũ, data invariant, old/new code compatibility |
| Đổi message converter | Old writer/new reader, new writer/old reader, replay, headers |
| Đổi queue/subscription | Ordering, ack, redelivery, duplicate, DLQ |
| Đổi object storage API | Bytes/checksum, metadata, versioning, conditional write |
| Đổi identity | Principal thực tế, permission, denied case, key/secret access |
| Đổi endpoint/region | Resource mapping, encoding, TLS và data residency |

Một regression suite nên có tên test thể hiện cặp phiên bản, ví dụ `readsInvoiceV1FixtureWithCurrentModel`, `migratesSchemaV3ToV5WithHistoricalRows`, `consumerV2ProcessesEventV1` và `s3MultipartUploadPreservesFullObjectChecksum`.

## 10. Kiểm tra dữ liệu sau migration và sau deploy

Sau khi migration hoặc deploy, chạy các bước đối soát có thể lặp lại:

1. Đếm record/object/message theo nhóm nghiệp vụ.
2. Kiểm tra null/default/enum distribution.
3. Tính checksum cho tập dữ liệu hoặc object đã chọn.
4. So sánh business aggregate: tổng tiền, số invoice, số payment, trạng thái.
5. Kiểm tra dead-letter queue và retry backlog.
6. Kiểm tra consumer lag và message age.
7. Xác minh object metadata, content type và encryption.
8. Kiểm tra log deserialize failure và unknown schema version.
9. Kiểm tra database migration history và migration checksum.
10. Lưu kết quả đối soát theo release để có thể so sánh lại.

Đối soát cần phân biệt sai khác dự kiến và sai khác lỗi. Ví dụ, migration chuẩn hóa timestamp về UTC có thể làm chuỗi hiển thị thay đổi nhưng instant phải giữ nguyên. Viết test so sánh instant thay vì so sánh string nếu contract cho phép chuẩn hóa timezone.

## 11. Triển khai canary và rollback có tính đến dữ liệu

Một bản code cũ có thể không đọc được dữ liệu do code mới ghi. Vì vậy, rollback image không phải lúc nào cũng đủ.

Trước khi deploy:

- Chốt schema compatibility window.
- Xác định phiên bản consumer còn chạy và message retention.
- Giữ reader có thể đọc format cũ trong thời gian replay/rollback.
- Có snapshot/backup database theo chính sách.
- Bật versioning/retention cho object nếu nghiệp vụ cần khôi phục.
- Ghi lại schema version và migration state.
- Chuẩn bị feature flag để chuyển read/write path.

Trong canary:

- Chuyển một phần traffic hoặc một nhóm tenant.
- So sánh kết quả đọc giữa code cũ và code mới trên cùng dữ liệu (shadow read khi phù hợp).
- Kiểm tra lỗi deserialize, query latency, duplicate, DLQ và checksum mismatch.
- Theo dõi số record được backfill và số record còn ở format cũ.

Khi rollback:

- Xác minh code cũ đọc được schema đã expand.
- Không chạy destructive contract migration trước khi hết rollback window.
- Không xóa object version hoặc message cần cho replay.
- Nếu code mới đã ghi payload mới, giữ adapter/reader tương thích hoặc chạy migration ngược có kiểm chứng.
- Đối soát lại side effect và idempotency trước khi phát lại message.

## 12. Những lỗi hồi quy thường gặp
+
| Triệu chứng | Nguyên nhân | Cách phát hiện |
| --- | --- | --- |
| Record cũ không deserialize | Field thiếu, enum mới, kiểu dữ liệu đổi | Golden fixtures theo writer version |
| Tổng tiền thay đổi sau migration | Decimal scale/rounding hoặc currency default sai | Aggregate invariant và precision test |
| Timestamp lệch giờ | Local timezone, parse format hoặc precision khác | Fixture có offset và so sánh Instant |
| Object upload đúng nhưng downstream không đọc | Content type/encoding/metadata đổi | Object metadata contract test |
| Checksum mismatch giả | Dùng ETag như MD5 cho multipart/encrypted object | So sánh checksum thuật toán rõ ràng |
| Consumer xử lý hai lần | At-least-once delivery hoặc ack sau side effect | Replay cùng MessageId và idempotency test |
| Message cũ vào DLQ sau deploy | Consumer mới không đọc schema/header cũ | Replay fixture trên broker test |
| Emulator pass nhưng production fail | Emulator không mô phỏng IAM/feature managed | Cloud sandbox test |
| Rollback không chạy | Code cũ không đọc format/schema mới | Compatibility matrix N-1/N |
| Migration timeout/lock lớn | Dữ liệu production lớn hơn fixture | Snapshot quy mô đại diện và migration timing |
| Backfill chạy hai lần làm sai dữ liệu | Job không idempotent hoặc thiếu checkpoint | Chạy lại job và đối soát kết quả |
| Versioned object không được khôi phục | Hiểu nhầm delete marker hoặc version ID | Test versioning/restore trên cloud sandbox |

## 13. Bài thực hành: kiểm thử hồi quy invoice-service qua hai phiên bản

**Bối cảnh:** invoice-service phiên bản N-1 lưu invoice trong PostgreSQL, PDF trong S3 và phát InvoiceCreated vào SQS. Phiên bản N bổ sung currency, đổi message envelope và nâng AWS SDK. Production vẫn còn record và message do N-1 ghi.

### Bước 1 — Thu thập dữ liệu mẫu

Tạo fixture từ N-1:

- Invoice đã thanh toán, invoice bị hủy và invoice thiếu customer reference.
- PDF nhỏ và PDF lớn được upload bằng single-part/multipart.
- Message v1 có eventId, eventType, occurredAt và payload cũ.
- Metadata S3 có content type và checksum đã biết.

Ẩn danh dữ liệu, giữ nguyên kiểu dữ liệu, null, precision và cấu trúc quan trọng.

### Bước 2 — Chạy database migration

- Tạo PostgreSQL container.
- Chạy Flyway đến schema N-1.
- Insert các fixture N-1.
- Chạy migration đến schema N.
- Kiểm tra amount, status, created_at, currency và foreign key.
- Chạy lại invariant và kiểm tra migration history.

### Bước 3 — Kiểm tra serializer và reader

- Consumer N đọc tất cả message v1.
- Producer N ghi message v2.
- Nếu rolling deployment còn consumer N-1, kiểm tra consumer N-1 đọc được v2 hoặc giữ feature flag để producer tiếp tục ghi v1 trong cửa sổ rollout.
- Publish lại cùng event ID và xác minh không tạo invoice thứ hai.
- Kiểm tra unknown enum và field thiếu.

### Bước 4 — Kiểm tra S3

- Tải PDF v1 bằng code N.
- So sánh bytes bằng SHA-256 hoặc checksum đã lưu.
- Kiểm tra Content-Type, metadata, encryption và version ID.
- Upload PDF mới bằng multipart, xác minh full-object checksum.
- Không dùng ETag làm giả định MD5 cho mọi object.

### Bước 5 — Chạy provider sandbox test

- Dùng IAM role test có quyền đọc/ghi đúng bucket và queue.
- Kiểm tra SQS redelivery, visibility timeout và DLQ.
- Kiểm tra quyền KMS nếu bucket dùng SSE-KMS.
- Đối chiếu object metadata và message attributes sau khi SDK mới ghi.

### Bước 6 — Kiểm tra rollback

- Khởi động code N-1 trên schema đã expand.
- Đọc invoice đã được N cập nhật.
- Đọc event v2 nếu consumer cũ còn trong phạm vi tương thích.
- Nếu code N-1 không thể đọc v2, xác nhận producer có thể quay về v1 trước khi bật rollback hoặc giữ adapter đọc v2.

### Bước 7 — Canary và đối soát

Deploy một nhóm instance N, so sánh tổng invoice, tổng tiền, số event, số message DLQ, checksum object và lỗi deserialize. Chỉ mở rộng rollout khi các invariant đạt và không có dữ liệu cũ bị loại khỏi luồng xử lý.

## 14. Checklist review trước khi merge

- [ ] Đã lập ma trận writer/reader giữa N-1 và N.
- [ ] Đã lưu golden fixtures theo phiên bản writer/schema.
- [ ] Fixture có field thiếu/null, enum lạ, decimal, timestamp và Unicode.
- [ ] Đã kiểm tra không có secret hoặc dữ liệu cá nhân trong fixture.
- [ ] Đã chạy migration từ schema cũ có dữ liệu.
- [ ] Đã xác minh row count và business invariants trước/sau migration.
- [ ] Đã kiểm tra Flyway migration history và checksum.
- [ ] Đã kiểm tra code cũ chạy trên schema expand trong rollback window.
- [ ] Đã test consumer mới đọc message cũ và replay.
- [ ] Đã test idempotency, duplicate, ordering, ack và DLQ.
- [ ] Đã kiểm tra content type, metadata, checksum và versioning của object.
- [ ] Không dùng ETag làm checksum tổng quát.
- [ ] Đã kiểm tra emulator limitations và có cloud sandbox test cho feature quan trọng.
- [ ] Đã kiểm tra IAM/RBAC, KMS và managed identity bằng principal test.
- [ ] Đã chạy canary và đối soát dữ liệu sau deploy.
- [ ] Đã chuẩn bị rollback cho code, schema, object và message.

## 15. Câu hỏi tự kiểm tra

1. Vì sao compile và unit test pass chưa chứng minh dữ liệu cũ tương thích?
2. Phân biệt regression test, contract test và migration test như thế nào?
3. Vì sao nên lưu golden fixture theo phiên bản writer?
4. Reader N cần kiểm tra dữ liệu do writer N-1 ghi trong trường hợp nào?
5. Tại sao cần test reader N-1 với dữ liệu do writer N ghi khi rolling deployment?
6. Vì sao không sửa migration Flyway đã được áp dụng?
7. Expand-contract giúp rollback an toàn như thế nào?
8. Những invariant nào cần đối soát ngoài row count?
9. Vì sao ETag của S3 không phải lúc nào cũng là MD5?
10. CRC32C có vai trò gì khi kiểm tra object Cloud Storage?
11. Azure Blob ETag hỗ trợ optimistic concurrency như thế nào?
12. Vì sao Pub/Sub emulator không thể chứng minh IAM behavior?
13. Azure Service Bus emulator thiếu những feature managed nào cần kiểm thử trên cloud?
14. Vì sao duplicate detection không thay thế idempotent consumer?
15. Khi nào cần giữ reader cho schema cũ sau khi deploy schema mới?
16. Rollback cần kiểm tra những dữ liệu nào ngoài database schema?

## 16. Ghi nhớ

Kiểm thử hồi quy cho nâng cấp cloud phải bắt đầu từ dữ liệu đã được ghi bởi các phiên bản trước. Giữ fixture theo writer/schema version, chạy migration trên database có dữ liệu và kiểm tra invariant nghiệp vụ sau chuyển đổi. Với message, kiểm tra cả old-writer/new-reader và new-writer/old-reader khi rolling deployment hoặc replay yêu cầu. Với object storage, kiểm tra bytes, metadata, checksum và versioning.

Testcontainers và emulator giúp tăng tốc integration test nhưng không mô phỏng đầy đủ IAM, quota, retention, managed identity hoặc mọi service feature. Hãy kết hợp unit/contract test, local integration và cloud sandbox. **Một bản nâng cấp chỉ sẵn sàng khi code mới đọc đúng dữ liệu cũ, dữ liệu mới vẫn nằm trong compatibility window và rollback không làm mất khả năng phục hồi.**

## Tài liệu tham khảo chính thức

- [Spring Boot — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Flyway — Validate migrations](https://documentation.red-gate.com/flyway/reference/commands/validate)
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Cloud Stream — Schema Registry and schema evolution](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html)
- [AWS — S3 object integrity and checksums](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html)
- [AWS SDK for Java 2.x — S3 checksums](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/s3-checksums.html)
- [AWS — How S3 Versioning works](https://docs.aws.amazon.com/AmazonS3/latest/userguide/versioning-workflows.html)
- [AWS — DynamoDB Local usage notes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.UsageNotes.html)
- [Google Cloud — Pub/Sub schema overview](https://docs.cloud.google.com/pubsub/docs/schemas)
- [Google Cloud — Pub/Sub emulator and limitations](https://docs.cloud.google.com/pubsub/docs/emulator)
- [Google Cloud — Cloud Storage data validation and checksums](https://docs.cloud.google.com/storage/docs/data-validation)
- [Microsoft — Azurite and Azure Storage differences](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite)
- [Microsoft — Run automated tests using Azurite](https://learn.microsoft.com/en-us/azure/storage/blobs/use-azurite-to-run-automated-tests)
- [Microsoft — Azure Service Bus emulator overview and limitations](https://learn.microsoft.com/en-us/azure/service-bus-messaging/overview-emulator)
- [Microsoft — Service Bus message loss, duplicates and idempotency](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-message-loss-and-duplicates)
- [Microsoft — Azure Blob conditional headers and ETag](https://learn.microsoft.com/en-us/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations)

