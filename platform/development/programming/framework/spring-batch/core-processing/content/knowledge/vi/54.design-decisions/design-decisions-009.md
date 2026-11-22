# Chọn output transaction hay outbox trong Spring Batch

Khi thiết kế đầu ra của một Spring Batch job, một câu hỏi quyết định độ tin cậy là: **kết quả phải được ghi vào một tài nguyên có transaction, hay còn phải phát sự kiện/gọi hệ thống bên ngoài sau khi dữ liệu đã được ghi?** Câu trả lời ảnh hưởng trực tiếp tới khả năng rollback, retry, restart, chống ghi trùng, độ trễ công bố và cách xử lý khi một process chết giữa hai thao tác.

Ví dụ, job chốt sổ đọc 10.000 giao dịch, ghi các bút toán vào PostgreSQL rồi phát sự kiện `LedgerPosted` cho dịch vụ báo cáo:

~~~text
Input -> Spring Batch -> PostgreSQL ledger -> Message broker -> Reporting service
~~~

Nếu writer ghi database thành công nhưng ứng dụng chết trước khi gửi sự kiện, bản ghi kế toán đã tồn tại trong khi downstream không biết về nó. Nếu đảo thứ tự để gửi sự kiện trước rồi ghi database, downstream có thể nhận một sự kiện về giao dịch mà database chưa bao giờ commit. Chỉ bao toàn bộ code bằng `@Transactional` không khiến PostgreSQL, HTTP API và broker tự trở thành **một giao dịch nguyên tử**.

**Thông điệp chính:** *Output transaction* là nền tảng khi toàn bộ thay đổi cần bảo đảm thuộc cùng một tài nguyên giao dịch. *Transactional outbox* là lựa chọn phổ biến khi cần **commit dữ liệu nghiệp vụ và ghi ý định phát sự kiện cùng một transaction**, sau đó giao sự kiện bằng cơ chế bất đồng bộ có retry và idempotency. Hai cơ chế **không loại trừ nhau**: outbox **sử dụng chính database transaction** để bảo vệ phần ghi ban đầu.

Bài này thuộc **Spring Batch Core Processing → Quyết định thiết kế**, tập trung vào tiêu chí chọn kiến trúc, semantics của chunk, rủi ro hai lần ghi (*dual write*), ví dụ Spring Batch 5.x/Java 17+/PostgreSQL, cách vận hành outbox và các kịch bản lỗi cần kiểm chứng.

## 1. Hiểu đúng hai phương án

### 1.1. Output transaction

Writer thực hiện các thay đổi trên tài nguyên có transactional semantics trong transaction của chunk, ví dụ một database:

~~~mermaid
flowchart LR
    A["Reader"] --> B["Processor"]
    B --> C["Chunk transaction"]
    C --> D["INSERT/UPDATE ledger"]
    D --> E{"Commit"}
    E -->|Thành công| F["Dữ liệu đã commit"]
    E -->|Lỗi| G["Rollback chunk"]
~~~

Nếu database writer và `PlatformTransactionManager` thật sự dùng **cùng datasource/transaction**, lỗi trước commit thường khiến các thay đổi của chunk được rollback. Những chunk trước đó đã commit **không** bị rollback cùng chunk hiện tại.

Đây là mô hình phù hợp khi kết quả cần thiết nằm trong **một ranh giới giao dịch**, ví dụ ghi nhiều bảng trong cùng PostgreSQL database hoặc cập nhật một bảng đích có unique business key.

### 1.2. Transactional outbox

Writer ghi **dữ liệu nghiệp vụ và hàng outbox** vào cùng database transaction:

~~~mermaid
flowchart LR
    A["Spring Batch chunk"] --> B["Transaction DB"]
    B --> C["Business rows"]
    B --> D["Outbox event PENDING"]
    D --> E["Outbox dispatcher / CDC"]
    E --> F["Broker / API"]
    F --> G["Consumer có idempotency"]
~~~

Database commit quyết định **cả hai bản ghi cùng tồn tại hoặc cùng rollback**. Một dispatcher riêng đọc outbox đã commit rồi phát thông điệp. Khi dispatcher crash hoặc broker tạm lỗi, event vẫn còn trong database để gửi lại.

Điều outbox **không bảo đảm** là hai hành động “broker đã nhận event” và “database đã đánh dấu `SENT`” luôn nguyên tử. Nếu gửi thành công rồi crash trước lúc đánh dấu, dispatcher có thể gửi lại. Vì vậy outbox thường cung cấp **at-least-once delivery**, không phải exactly-once end-to-end; consumer cần cơ chế idempotent.

### 1.3. Không phải một lựa chọn nhị phân tuyệt đối

| Câu hỏi | Output transaction | Transactional outbox |
|---|---|---|
| Dữ liệu ghi vào một database duy nhất? | Thường là lựa chọn trực tiếp, đơn giản. | Có thể không cần nếu không có event/side effect ngoài DB. |
| Cần ghi DB **và** phát event tới broker? | Transaction của DB **không** bao phủ broker. | Thường phù hợp nếu chấp nhận phát bất đồng bộ. |
| Cần gọi HTTP API bên ngoài? | Không rollback API bằng DB transaction. | Có thể lưu *delivery intent* để dispatcher gọi API với idempotency key. |
| Cần downstream nhận event ngay trong cùng request? | Không giải quyết atomicity hai hệ thống. | Có độ trễ phát; có thể không đáp ứng yêu cầu đồng bộ tức thời. |
| Có thể replay mà không tạo dữ liệu trùng? | Cần idempotent writer khi restart. | Cần unique key ở outbox **và** consumer idempotent. |
| Chi phí vận hành | Một writer và transaction manager. | Thêm bảng, dispatcher/CDC, retry, giám sát backlog và cleanup. |

**Quy tắc ngắn:** Nếu chỉ cần ghi dữ liệu bền vững trong một database, ưu tiên transaction và thiết kế writer đúng. Nếu cần **ghi database rồi thông báo tới một hệ thống khác mà không được bỏ mất ý định thông báo**, cân nhắc transactional outbox.

## 2. Đầu tiên phải xác định yêu cầu nhất quán

Trước khi chọn công nghệ, cần đặt câu hỏi nghiệp vụ:

1. **Tập kết quả đích là gì?** Chỉ bảng dữ liệu, hay còn một sự kiện, file, email, HTTP request, message broker?
2. **Có được phép downstream nhận thông tin chậm không?** Outbox tách xử lý thành hai giai đoạn, nên thường là *eventual consistency*.
3. **Nếu một event được gửi lặp lại, hệ thống nhận có bảo vệ được không?** Phải có business key/event ID ổn định.
4. **Nếu producer crash, event cần còn lại bao lâu?** Retention và khả năng khôi phục từ outbox phải được tính toán.
5. **Có yêu cầu thứ tự sự kiện không?** Hai event cho cùng tài khoản có thể cần thứ tự, còn hai tài khoản độc lập thì không.
6. **Có phải tất cả kết quả được công bố cùng lúc không?** Commit theo chunk và outbox có thể cho downstream thấy **một phần** lô dữ liệu trước khi toàn bộ job kết thúc.
7. **Ai chịu trách nhiệm khi broker/API không khả dụng nhiều giờ?** Job có thể hoàn tất ghi DB trong khi backlog outbox vẫn chưa được chuyển.
8. **Có kiểm tra đối chiếu nguồn/đích không?** `COMPLETED` của batch không tự chứng minh thông điệp đã được consumer xử lý.

Một hệ thống báo cáo tham khảo có thể chấp nhận chậm vài phút và sự kiện gửi lặp. Một hệ thống tài chính bắt buộc đúng một bút toán mỗi event có thể cần ràng buộc unique, audit và reconciliation mạnh hơn. “Đảm bảo nhất quán” cần được diễn đạt thành **các invariant kiểm chứng được**, thay vì chỉ đặt tên kiến trúc là outbox.

## 3. Transaction boundary của chunk trong Spring Batch

Một chunk-oriented step thường chạy reader, processor, writer và checkpoint qua các ranh giới xử lý được Spring Batch điều phối:

~~~text
Chunk 1: read A,B,C -> process -> write -> COMMIT
Chunk 2: read D,E,F -> process -> write -> ROLLBACK nếu lỗi
Chunk 3: chưa chạy hoặc xử lý tiếp theo fault-tolerance policy
~~~

Với một writer JDBC dùng cùng `DataSource` và `PlatformTransactionManager` của step, các lệnh ghi trong chunk có thể cùng commit/rollback:

~~~java
@Bean
Step ledgerStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<LedgerRecord> reader,
        ItemProcessor<LedgerRecord, LedgerRecord> processor,
        ItemWriter<LedgerRecord> writer) {

    return new StepBuilder("ledgerStep", jobRepository)
        .<LedgerRecord, LedgerRecord>chunk(100, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Ví dụ giả định các bean `reader`, `processor`, `writer` và `JobRepository` đã được định nghĩa. Dấu mấu chốt là **`writer` phải dùng database connection tham gia `businessTransactionManager`**. Nếu writer mở một connection riêng với `autoCommit=true` hoặc gọi service dùng `REQUIRES_NEW`, rollback của chunk có thể không hoàn tác thao tác đã commit riêng.

### Những điều transaction giải quyết

- Các thay đổi trong cùng một database transaction có thể được commit hoặc rollback cùng nhau.
- Nếu writer ném exception trước commit và rollback hoạt động đúng, dữ liệu chunk chưa được commit không xuất hiện ở đích.
- Có thể kết hợp nhiều bảng nghiệp vụ trong cùng transaction, như `ledger_entry` và `audit_entry`.
- Ràng buộc unique trên business key bảo vệ dữ liệu khỏi duplicate khi input/restart bị replay.

### Những điều transaction không tự giải quyết

- Những chunk trước **đã commit** không rollback khi chunk sau thất bại.
- `@Transactional` trên service ghi DB không tự cuốn email, file, HTTP hay broker vào cùng transaction.
- Commit outcome có thể **không rõ** nếu process mất kết nối đúng lúc database nhận COMMIT.
- `JobRepository` và database nghiệp vụ có thể dùng hai `DataSource`/transaction manager khác nhau; metadata/checkpoint và output không tự động commit cùng nhau.
- Transaction thành công chưa chứng minh mọi input nghiệp vụ hợp lệ, đủ và không trùng; vẫn cần reconciliation.

Nếu kết quả chỉ tồn tại ở một DB có transaction, đây thường đã là mô hình đủ tốt khi kết hợp business key, replay-safety và kiểm tra đầu ra.

## 4. Ví dụ: chọn transaction trực tiếp khi chỉ ghi PostgreSQL

Giả sử job ghi các bút toán vào bảng:

~~~sql
CREATE TABLE ledger_entry (
    event_id VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    business_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`event_id` là business/event key ổn định theo nguồn, không phải UUID ngẫu nhiên mới ở mỗi lần retry.

Ví dụ writer với `JdbcBatchItemWriter`:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
JdbcBatchItemWriter<LedgerRecord> ledgerWriter(DataSource businessDataSource) {
    return new JdbcBatchItemWriterBuilder<LedgerRecord>()
        .dataSource(businessDataSource)
        .sql("""
            INSERT INTO ledger_entry(
                event_id, account_id, amount, business_date)
            VALUES (:eventId, :accountId, :amount, :businessDate)
            ON CONFLICT (event_id) DO NOTHING
            """)
        .beanMapped()
        .assertUpdates(false)
        .build();
}
~~~

Ví dụ giả định `LedgerRecord` là JavaBean/record có property tương ứng `eventId`, `accountId`, `amount`, `businessDate` và datasource thuộc transaction manager của step. `ON CONFLICT` là cú pháp PostgreSQL; database khác có cú pháp riêng.

**Vì sao `assertUpdates(false)`?** Nếu item đã được ghi ở lần trước và SQL chọn `DO NOTHING`, một execution mới có thể thấy 0 hàng được chèn. Không muốn coi 0 update là lỗi kỹ thuật trong chính sách này. Tuy nhiên, `DO NOTHING` **không chứng minh** payload của event cũ và mới giống nhau: nếu `event_id` trùng mà `amount` khác, cần báo vi phạm tính nhất quán thay vì âm thầm bỏ khác biệt. Một production writer có thể đối chiếu checksum/nội dung đã lưu hoặc dùng UPSERT có điều kiện để phát hiện conflict bất thường.

Trong tình huống này, thêm outbox không tạo lợi ích rõ nếu không có event hoặc tác động bên ngoài database. Một transaction đúng + khóa nghiệp vụ duy nhất + reconciliation có thể đơn giản và phù hợp hơn.

## 5. Vì sao “ghi DB rồi gửi message” trực tiếp gây dual-write

Giả sử writer làm hai việc:

~~~java
// Anti-pattern nếu cần bảo đảm DB commit và event delivery nhất quán.
ledgerRepository.save(record);
messagePublisher.send("ledger-posted", event);
~~~

Dù phương thức được bao bằng `@Transactional` cho database, broker không mặc nhiên tham gia transaction ấy.

### Gửi sau khi ghi nhưng trước DB commit

~~~text
T1  INSERT ledger trong transaction
T2  Broker nhận LedgerPosted
T3  DB commit thất bại -> ROLLBACK

Kết quả: consumer nhận sự kiện nhưng ledger không tồn tại.
~~~

Consumer có thể tạo báo cáo hoặc gửi thông báo dựa vào một bút toán chưa bao giờ commit. Nếu lỗi xảy ra khi writer đang chạy và Spring Batch retry, event còn có thể được gửi thêm lần nữa.

### Gửi sau khi commit

~~~text
T1  INSERT ledger
T2  COMMIT database thành công
T3  Process crash
T4  Không có event LedgerPosted

Kết quả: ledger tồn tại nhưng consumer không nhận sự kiện.
~~~

Đưa lệnh gửi vào callback sau commit giúp tránh trường hợp gửi event từ dữ liệu chưa commit, nhưng **không đóng được cửa sổ crash giữa commit và gửi**. Nếu hệ thống cần bảo đảm eventual delivery, chỉ một `afterCommit` callback trong JVM thường không đủ.

### Đảo thứ tự gửi trước khi ghi

~~~text
T1  Gửi event thành công
T2  DB insert thất bại

Kết quả: consumer thấy sự kiện không có bản ghi gốc.
~~~

Đổi thứ tự không loại bỏ vấn đề; nó chỉ đổi loại sai lệch. Muốn xử lý đúng, cần xác định một **nguồn chân lý cho ý định phát event** được commit cùng trạng thái nghiệp vụ.

## 6. Transactional outbox giải bài toán gì?

Transactional outbox tách việc phát thông điệp thành hai giai đoạn:

**Giai đoạn A — Trong chunk transaction của Spring Batch**

~~~text
BEGIN transaction
  INSERT ledger_entry(...)
  INSERT outbox_event(event_id, payload, status='PENDING')
COMMIT transaction
~~~

Nếu commit thất bại, **cả business row lẫn outbox row rollback**. Nếu commit thành công, **cả hai cùng tồn tại** để dispatcher tiếp tục.

**Giai đoạn B — Sau commit**

~~~text
Outbox dispatcher
  -> đọc event PENDING
  -> gửi tới broker/API
  -> sau xác nhận gửi thành công, đánh dấu SENT
~~~

Dispatcher có thể chạy theo lịch ngắn, service riêng hoặc change data capture (CDC) từ database transaction log. Cả polling lẫn CDC đều cần chính sách vận hành, retention và kiểm soát duplicate.

**Bảo đảm cốt lõi:** Trạng thái nghiệp vụ và *ý định phát event* được commit nguyên tử **trong một database**. Nó không đồng nghĩa event đã được giao tới consumer ngay khi batch step `COMPLETED`.

### Outbox không giải quyết cái gì?

- Không tạo atomic commit giữa database và broker tại thời điểm dispatcher gửi.
- Không bảo đảm consumer chỉ nhận message một lần.
- Không tự xử lý thứ tự các event của cùng aggregate nếu dispatcher chạy song song không được thiết kế.
- Không tự làm external API idempotent; người nhận vẫn có thể tạo side effect lặp.
- Không tự hoàn tác việc đã gửi email, gọi HTTP hoặc ghi file trước khi event được enqueue.
- Không đảm bảo toàn bộ batch được công bố một lần: mỗi **chunk** có thể commit outbox event và được dispatch khi job vẫn đang chạy.

## 7. Thiết kế schema outbox trong cùng database nghiệp vụ

Ví dụ PostgreSQL cho `ledger_entry` và `outbox_event`:

~~~sql
CREATE TABLE ledger_entry (
    event_id VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    business_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_event (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(140) NOT NULL UNIQUE,
    aggregate_key VARCHAR(100) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    owner_token UUID,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ,
    CONSTRAINT outbox_status_chk
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'SENT', 'DEAD'))
);

CREATE INDEX idx_outbox_dispatch
    ON outbox_event(status, created_at, id);
~~~

**Các trường quan trọng:**

| Trường | Mục đích |
|---|---|
| `id` | ID nội bộ của hàng outbox, thuận tiện claim/batch polling. |
| `event_id` | ID **ổn định** của sự kiện nghiệp vụ; unique để chống tạo lại outbox khi replay. |
| `aggregate_key` | Tài khoản/đơn hàng/đối tượng dùng khi cần bảo đảm thứ tự per aggregate. |
| `event_type` | Phân loại event và hỗ trợ schema evolution. |
| `payload` | Thông điệp được tạo từ dữ liệu đã commit; cần schema version và bảo vệ thông tin nhạy cảm. |
| `status` | Theo dõi PENDING, IN_FLIGHT, SENT, DEAD theo quy tắc dispatcher. |
| `attempt_count` | Số lần claim/phát theo thiết kế; không tự chứng minh broker nhận bao nhiêu lần. |
| `owner_token`, `locked_until` | Phối hợp nhiều dispatcher và xử lý worker crash. |
| `created_at`, `sent_at` | Đo độ trễ từ lúc commit tới lúc phát thành công. |

**Outbox row phải nằm trong cùng database transaction với `ledger_entry`.** Tạo outbox trong một datasource khác, hoặc gọi service lưu outbox bằng `REQUIRES_NEW`, phá vỡ bảo đảm atomicity ban đầu. “Có một bảng tên outbox” chưa đồng nghĩa hệ thống đã triển khai transactional outbox đúng.

### Khóa event nên chọn thế nào?

Ví dụ với một sự kiện `LedgerPosted` cho event nghiệp vụ:

~~~text
event_id = "LEDGER_POSTED:" + sourceEventId
~~~

ID này phải ổn định khi chunk retry/restart, và không thay đổi do `jobExecutionId` hoặc timestamp của lần chạy. Nếu cùng source event có nhiều loại sự kiện hợp lệ, nên đưa event type/sequence hoặc version nghiệp vụ vào key một cách có chủ đích.

Không nên tạo UUID ngẫu nhiên mới cho **mỗi lần writer được gọi** nếu một item có thể bị replay: sẽ tạo nhiều outbox event khác nhau cho cùng một tác động. UUID mới vẫn có thể dùng làm `id` nội bộ, nhưng phải có **unique business/event key** đủ mạnh để nhận diện sự kiện trùng.

## 8. Ví dụ Spring Batch 5: ghi ledger và outbox trong cùng chunk transaction

Giả sử `LedgerRecord` có các field:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record LedgerRecord(
    String eventId,
    String accountId,
    BigDecimal amount,
    LocalDate businessDate
) {}
~~~

Writer dùng `JdbcTemplate` **được cấu hình từ cùng `DataSource`** mà transaction manager của step quản lý:

~~~java
import java.util.Map;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class LedgerOutboxWriter implements ItemWriter<LedgerRecord> {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public LedgerOutboxWriter(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public void write(Chunk<? extends LedgerRecord> chunk) throws Exception {
        for (LedgerRecord record : chunk) {
            String eventId = "LEDGER_POSTED:" + record.eventId();

            // 1. Business output trong transaction của chunk.
            jdbc.update("""
                INSERT INTO ledger_entry(
                    event_id, account_id, amount, business_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                record.eventId(),
                record.accountId(),
                record.amount(),
                record.businessDate()
            );

            // 2. Chỉ tạo intent; không gọi broker trực tiếp ở đây.
            String payload = mapper.writeValueAsString(Map.of(
                "eventId", eventId,
                "sourceEventId", record.eventId(),
                "accountId", record.accountId(),
                "amount", record.amount().toPlainString(),
                "businessDate", record.businessDate().toString(),
                "schemaVersion", 1
            ));

            jdbc.update("""
                INSERT INTO outbox_event(
                    event_id, aggregate_key, event_type, payload, status)
                VALUES (?, ?, ?, CAST(? AS jsonb), 'PENDING')
                ON CONFLICT (event_id) DO NOTHING
                """,
                eventId,
                record.accountId(),
                "LEDGER_POSTED",
                payload
            );
        }
    }
}
~~~

Trong cấu hình step:

~~~java
@Bean
Step ledgerOutboxStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        ItemReader<LedgerRecord> reader,
        ItemWriter<LedgerRecord> ledgerOutboxWriter) {

    return new StepBuilder("ledgerOutboxStep", jobRepository)
        .<LedgerRecord, LedgerRecord>chunk(100, businessTransactionManager)
        .reader(reader)
        .writer(ledgerOutboxWriter)
        .build();
}
~~~

Để ví dụ đáp ứng mục tiêu, cần các điều kiện:

1. Bean `JdbcTemplate` của writer phải được khởi tạo bằng **businessDataSource** mà `businessTransactionManager` dùng; nếu nhiều `DataSource`, cần qualifier rõ.
2. Writer **không** tự gọi `commit()`, không sử dụng `REQUIRES_NEW` và không gửi broker trong vòng lặp.
3. Hai câu `INSERT` thuộc cùng transaction của chunk. Lỗi sau insert đầu tiên nhưng trước insert thứ hai sẽ làm rollback cả hai khi transaction hoạt động đúng.
4. `event_id` của ledger và `event_id` outbox có ràng buộc unique phù hợp khi restart/replay.
5. Payload có **schema version**; downstream được thiết kế để đọc phiên bản đó. Ví dụ payload đưa `accountId` và amount ra ngoài chỉ khi chính sách bảo mật cho phép.
6. `DO NOTHING` là quyết định idempotency của ví dụ, **không thay thế kiểm tra conflict**. Trong production, khi một `sourceEventId` được gửi lại với nội dung khác, cần phát hiện và xử lý mismatch thay vì coi như thành công im lặng.

### Ghi nhận sự thật khi writer bị gọi lại

Spring Batch có thể retry writer trong fault-tolerant step hoặc restart cùng `JobInstance` sau `FAILED`. Khi đó `write(...)` có thể nhận một record đã được ghi trong chunk trước hoặc do metadata chưa xác nhận commit ở thời điểm crash.

Unique key ngăn tạo hàng mới cho cùng business event, và outbox unique key ngăn tạo **ý định phát thứ hai**. Nhưng việc dispatcher có thể gửi cùng một outbox row nhiều lần vẫn cần consumer idempotency riêng.

## 9. Vì sao không gửi message trong ItemWriteListener.afterWrite?

Một ý tưởng phổ biến:

~~~java
@Override
public void afterWrite(Chunk<? extends LedgerRecord> items) {
    publisher.send(items); // Không phải bảo đảm post-commit.
}
~~~

`ItemWriteListener.afterWrite` thường chạy **sau khi writer hoàn tất nhưng trước transaction commit của chunk**. Nếu gửi ngay tại đây, message có thể đến broker dù commit sau đó thất bại.

Chuyển sang callback sau commit giúp tránh gửi khi transaction rollback, nhưng không giải quyết trường hợp **commit xong rồi process chết trước callback/send**. Ngoài ra gửi message trong quá trình giữ DB transaction mở có thể làm transaction kéo dài, giữ khóa và cản trở throughput.

Vì vậy, khi yêu cầu là không mất ý định thông báo, **đừng coi callback trong JVM là bộ lưu trữ bền vững**. Dùng outbox record đã commit hoặc một cơ chế durable queue được tích hợp vào thiết kế nhất quán tương đương.

## 10. Dispatcher lấy event như thế nào?

Có hai cách phổ biến:

**Polling publisher:** Một service định kỳ lấy các event chưa gửi từ bảng outbox, phát rồi đánh dấu trạng thái. Ưu điểm là dễ triển khai khi database hỗ trợ; nhược điểm là phải quản lý polling, contention, retry, cleanup và ordering.

**Change Data Capture (CDC):** Công cụ như một CDC connector đọc transaction log của database và chuyển thay đổi outbox thành message. Ưu điểm có thể giảm polling; đổi lại cần vận hành connector, replication slot/log retention, mapping schema, snapshot/recovery và giải quyết duplicate/ordering.

Không có cách nào tự biến bài toán hai tài nguyên thành exactly-once end-to-end. Cần dựa trên **event ID ổn định**, trạng thái dispatcher và idempotency ở consumer.

### Claim bằng SQL để nhiều dispatcher không cùng lấy event

Khi nhiều instance dispatcher chạy song song, cách đơn giản như `SELECT ... WHERE status='PENDING'` rồi gửi có race: hai worker cùng thấy một hàng. Có thể dùng transaction claim dựa trên row-level locking. Ví dụ PostgreSQL:

~~~sql
-- Thực thi lệnh này trong một transaction ngắn.
WITH candidate AS (
    SELECT id
    FROM outbox_event
    WHERE status = 'PENDING'
       OR (status = 'IN_FLIGHT' AND locked_until < CURRENT_TIMESTAMP)
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE outbox_event AS o
SET status = 'IN_FLIGHT',
    owner_token = :ownerToken,
    locked_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = attempt_count + 1
FROM candidate AS c
WHERE o.id = c.id
RETURNING o.id, o.event_id, o.aggregate_key, o.event_type, o.payload;
~~~

SQL trên chỉ là **một claim lease mẫu**, không phải hệ thống hoàn chỉnh:

- `FOR UPDATE SKIP LOCKED` tránh đợi các hàng đang bị transaction khác khóa; transaction claim cần ngắn rồi commit.
- Sau khi claim, dispatcher **gửi ngoài transaction claim**, tránh giữ khóa database mở trong lúc broker/network chậm.
- `locked_until` giúp event được lấy lại khi worker crash; nhưng khi lease hết hạn, worker cũ **có thể vẫn đang gửi**.
- `owner_token` cho phép kiểm tra ownership khi đánh dấu đã gửi. Cần thiết kế lease renewal/timeout và idempotency ở nơi nhận.
- `attempt_count` hỗ trợ retry policy và giám sát nhưng **không phải bằng chứng số lần consumer thực sự xử lý**.

Sau khi broker **xác nhận** đã nhận sự kiện, dispatcher đánh dấu `SENT` bằng transaction ngắn:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    sent_at = CURRENT_TIMESTAMP,
    owner_token = NULL,
    locked_until = NULL
WHERE id = :outboxId
  AND status = 'IN_FLIGHT'
  AND owner_token = :ownerToken;
~~~

Nếu số hàng update bằng **0**, ownership có thể đã bị worker khác lấy lại hoặc trạng thái đã thay đổi. Cần tra cứu/đối soát, không tự coi event vẫn thuộc worker cũ.

Nếu broker client gửi bất đồng bộ và `send(...)` chỉ trả future, **không đánh dấu SENT ngay sau khi gọi phương thức**; phải chờ acknowledgement theo hợp đồng publisher. Nếu broker xác nhận thành công nhưng transaction đánh dấu `SENT` thất bại, event có thể được gửi lại. Đây là hành vi cần dự kiến, không phải một race có thể biến mất hoàn toàn nhờ locking.

### Pseudocode dispatcher

~~~java
// Pseudocode: repo.claim() và repo.markSent() mỗi hàm có
// transaction riêng, ngắn; publisher.sendAndAwaitAck()
// chỉ trả về sau khi broker xác nhận theo hợp đồng.

void dispatchOne() {
    UUID owner = UUID.randomUUID();
    OutboxEvent event = outboxRepository.claimOne(owner);
    if (event == null) {
        return;
    }

    try {
        publisher.sendAndAwaitAck(
            event.eventId(),
            event.aggregateKey(),
            event.payload()
        );
        outboxRepository.markSent(event.id(), owner);
    } catch (TransientPublishException error) {
        outboxRepository.recordFailure(event.id(), owner, error);
        // Giữ khả năng retry và cho monitoring thấy backlog.
    }
}
~~~

Các interface, record và exception trong snippet là **khái niệm ứng dụng**, không phải API Spring Batch tự cung cấp. Code thật cần quy tắc backoff, timeout, lease renewal, max attempts, xử lý worker crash và log an toàn. Không nên retry message lỗi vĩnh viễn vô hạn đến mức làm tắc toàn hàng đợi.

### “Mark SENT trước rồi gửi” là anti-pattern

~~~text
Mark SENT -> DB commit -> crash -> chưa gửi broker
~~~

Event có thể mất vĩnh viễn nếu dispatcher chỉ lấy `PENDING`. Cách đúng thông thường là **gửi và nhận xác nhận trước, sau đó đánh dấu đã gửi**; chấp nhận rủi ro gửi lặp và xử lý nó bằng idempotency.

## 11. Consumer cần idempotency

Giả sử dispatcher gửi `LedgerPosted(eventId=LEDGER_POSTED:TX-001)`, broker nhận thành công nhưng app crash trước khi cập nhật outbox `SENT`. Sau restart, sự kiện được gửi lần hai. Nếu consumer thực hiện:

~~~sql
UPDATE account_summary
SET total = total + :amount
WHERE account_id = :accountId;
~~~

thì hai lần nhận cùng event sẽ cộng tiền hai lần. Consumer phải giữ một dấu vết **đã xử lý event ID này** trong cùng transaction với tác động nghiệp vụ, hoặc thực hiện thao tác idempotent khác.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(140) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một consumer transaction:

~~~text
BEGIN
  INSERT processed_event(consumer_name, event_id)
    ON CONFLICT DO NOTHING;

  Nếu INSERT tạo một hàng mới:
      UPDATE summary theo event
  Nếu INSERT không tạo hàng:
      Event đã xử lý -> không cập nhật summary lần nữa
COMMIT
ACK message sau khi commit
~~~

Điều kiện bắt buộc: **insert marker và cập nhật business output nằm trong cùng database transaction**. Nếu marker commit trước còn summary update fail, consumer có thể xem event là đã xử lý dù dữ liệu chưa cập nhật. Nếu summary update commit trước marker, retry có thể tạo tác động trùng.

### Ví dụ consumer dùng JdbcTemplate

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerEventConsumerService {

    private final JdbcTemplate jdbc;

    public LedgerEventConsumerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean apply(
            String consumerName,
            String eventId,
            String accountId,
            java.math.BigDecimal amount) {

        int inserted = jdbc.update("""
            INSERT INTO processed_event(consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            consumerName, eventId
        );

        if (inserted == 0) {
            return false; // Trùng event, không áp dụng lần nữa.
        }

        int updated = jdbc.update("""
            UPDATE account_summary
            SET total = total + ?
            WHERE account_id = ?
            """,
            amount, accountId
        );

        if (updated != 1) {
            throw new IllegalStateException("ACCOUNT_SUMMARY_MISSING");
        }

        return true;
    }
}
~~~

Ví dụ giả định `processed_event` và `account_summary` thuộc cùng database/transaction manager, Spring transaction management đã bật và lời gọi `apply(...)` đi qua Spring proxy. Nếu không update được summary, exception làm rollback **cả marker và summary update**, cho phép retry.

Consumer nhận message cần ACK theo đúng API của broker **sau khi** transaction nghiệp vụ đã commit; chi tiết ACK phụ thuộc Kafka, RabbitMQ hoặc hệ thống khác. Với consumer gọi API ngoài transaction, một bảng marker DB riêng vẫn chưa bảo đảm atomicity với API; phải dựa vào idempotency key ở phía API, trạng thái remote hoặc mô hình saga/compensation phù hợp.

**Idempotent consumer** không chỉ chống duplicate của outbox: nó còn hữu ích trước retry của broker, consumer crash sau commit, redelivery và xử lý lại từ offset.

## 12. Ma trận failure: transaction vs outbox

Để chọn đúng, hãy mô tả những điểm process có thể chết:

| Điểm lỗi | Chỉ ghi DB transaction | DB + transactional outbox | Cần chú ý thêm |
|---|---|---|---|
| Writer lỗi trước commit | Chunk rollback. | Business row và outbox row cùng rollback. | Điều kiện là cùng transaction thật. |
| Writer thành công nhưng commit lỗi | Không được mặc định dữ liệu đã lưu. | Không được mặc định cả hai đã lưu. | Khi commit outcome không rõ, kiểm tra theo business key. |
| Commit thành công, process chết ngay sau đó | Data đã ở DB. | Data và event `PENDING` cùng tồn tại. | Dispatcher có thể tiếp tục độc lập. |
| Broker/API không khả dụng | Không có yêu cầu gửi nếu chỉ ghi DB. | Event backlog; retry sau. | Alert, retention, backoff, capacity. |
| Broker nhận message nhưng dispatcher chết | Không áp dụng nếu không gửi. | Có thể phát lại cùng event. | Consumer idempotency. |
| Dispatcher đánh dấu SENT thất bại | Không áp dụng. | Có thể phát lại dù broker đã ACK. | Không coi đây là lỗi mất event. |
| Consumer đã commit rồi chết trước broker ACK | Không áp dụng. | Broker có thể redeliver. | Consumer marker + business update cùng transaction. |
| Có nhiều dispatcher | Không áp dụng. | Cần claim/lease hoặc CDC coordination. | Locking không thay idempotency. |
| Job restart/replay item | Writer cần unique key để tránh ghi trùng. | Cả business key và outbox event key phải ổn định. | Không sinh event ID mới theo execution. |

Ma trận này chỉ đúng theo giả định kỹ thuật đã nêu. Với writer đa datasource, file hoặc HTTP không transactional, cần bổ sung tình huống riêng cho từng đích. **Một nhãn “transactional” trên code không chứng minh các hệ thống đích thực sự commit cùng nhau.**

## 13. Restart Spring Batch khi outbox đã có event

Giả sử `JobInstance` xử lý `businessDate=2026-11-15`:

~~~text
JobInstance 410
  |
  +-- JobExecution 8102 FAILED
  |     chunk 1: ledger + outbox COMMITTED
  |     chunk 2: ROLLBACK
  |
  +-- JobExecution 8103 COMPLETED
        restart cùng instance; tiếp tục theo checkpoint
~~~

Khi restart:

- Chunk 1 có thể vẫn tồn tại trong DB và outbox; không nên tạo event ID mới cho cùng giao dịch.
- Một record có thể bị reader/writer replay do các tình huống checkpoint hoặc commit outcome không rõ. Unique business key ở DB và event key outbox giảm nguy cơ tạo trùng.
- Dispatcher **không phụ thuộc trực tiếp vào `JobExecution`** để biết event nào được phát. Nó dựa vào hàng outbox đã commit.
- `JobExecution 8103 COMPLETED` không đồng nghĩa tất cả event outbox đã được broker ACK hoặc consumer xử lý.
- Không xóa metadata `BATCH_*` rồi chạy lại bằng `run.id` ngẫu nhiên để “sửa” một trường hợp restart khó. Cần giữ đúng JobInstance và đối soát output đã commit.

### Metadata repo có thể ở database khác

Nếu `JobRepository` dùng database A và ledger/outbox dùng database B, transaction của checkpoint và transaction nghiệp vụ **không tự động là một giao dịch nguyên tử**. Khi process crash, có thể thấy database B đã commit nhưng metadata ở A chưa phản ánh hoàn toàn tiến độ.

Đây là một lý do cần **idempotent business writer** và **reconciliation**, kể cả khi đã dùng outbox. Nếu việc đảm bảo cùng một transaction cho repository và output là yêu cầu cứng, phải thiết kế datasource/transaction boundary thực sự phù hợp; không dựa vào việc đặt tên hai transaction manager giống nhau.

## 14. Outbox và tính nguyên tử của toàn bộ batch

Một điểm dễ bỏ qua: **Spring Batch chunk transaction không đồng nghĩa transaction cho cả job**. Nếu chunk size là 100, sau chunk 1 database có thể commit ledger rows và outbox events; dispatcher có thể phát ngay khi job còn xử lý chunk 2.

~~~text
T1 chunk 1 commit -> outbox event bắt đầu được dispatch
T2 downstream tiêu thụ một phần kết quả
T3 chunk 2 lỗi -> JobExecution FAILED
~~~

Nếu nghiệp vụ cho phép streaming incremental output, điều này có thể đúng. Nhưng nếu yêu cầu là **“chỉ công bố dữ liệu sau khi toàn bộ lô được đối chiếu thành công”**, phải thiết kế thêm **publish gate**:

1. Writer ghi ledger hoặc staging rows và outbox intent theo `batchKey`.
2. Event chưa đủ điều kiện dispatch khi batch chưa được duyệt; hoặc writer chỉ ghi staging, chưa tạo event công bố.
3. Step reconciliation kiểm tra count, sum, business keys và reject policy.
4. Sau khi đạt, một transaction cập nhật trạng thái batch `APPROVED` và tạo các outbox event cần công bố, hoặc tạo một `BatchPublished` event mô tả version đã sẵn sàng.
5. Dispatcher chỉ phát sự kiện hợp lệ theo trạng thái và hợp đồng công bố.

Ví dụ kiến trúc:

~~~mermaid
flowchart TD
    A["Load chunks -> staging by batchKey"] --> B["Reconcile data quality"]
    B --> C{"PASS?"}
    C -->|Không| D["Mark FAIL / không publish"]
    C -->|Có| E["DB transaction: mark APPROVED\n+ insert BatchPublished outbox event"]
    E --> F["Dispatcher"]
    F --> G["Consumers đọc batch version đã approved"]
~~~

**Không nhất thiết tạo một outbox event cho mỗi item.** Nếu downstream chỉ cần biết toàn bộ tập dữ liệu đã sẵn sàng trong DB, một event `BatchPublished` theo `batchKey/version` có thể đơn giản hơn hàng triệu item events. Ngược lại, nếu consumer cần xử lý từng giao dịch riêng và độ trễ theo item là mục tiêu, event-per-item có thể phù hợp hơn. Cần quyết định **granularity** theo hợp đồng.

## 15. Ordering, duplicate và schema evolution

### Thứ tự event

Nếu một tài khoản có hai event:

~~~text
Account A:
  event 1 -> tăng số dư
  event 2 -> đóng tài khoản
~~~

Dispatcher song song có thể gửi event 2 trước event 1 nếu chỉ chọn theo `created_at` và cho nhiều worker nhận hàng độc lập. `ORDER BY created_at` trong truy vấn polling **không tự bảo đảm thứ tự được broker/consumer quan sát** khi có nhiều dispatcher, retry hoặc partition.

Các lựa chọn:

- Sử dụng `aggregate_key` làm message partition/routing key để broker có thể giữ ordering trong phạm vi partition khi được cấu hình đúng.
- Ghi `aggregate_version` hoặc sequence tăng có kiểm soát và consumer xác thực thứ tự trước khi áp dụng.
- Chỉ cho một worker xử lý một aggregate trong một thời điểm khi yêu cầu ordering mạnh.
- Khi cần strict ordering qua retry, có thể chặn event phiên bản sau cho đến khi event trước được xác nhận, thay vì chỉ sắp xếp query.

Không dùng một timestamp đơn lẻ làm bằng chứng thứ tự tuyệt đối giữa transaction đồng thời, nhất là khi nhiều node có đồng hồ khác nhau.

### Schema của event

Payload nên có `eventType`, `schemaVersion`, business/event ID và các field cần thiết. Khi schema thay đổi, dispatcher có thể đang giữ các event PENDING được tạo từ phiên bản trước, nên consumer cần tương thích hoặc có migration.

Không serialize nguyên object JPA/domain rồi phát nếu nó vô tình mang password, PII hoặc các trường nội bộ không thuộc hợp đồng. Outbox payload được lưu bền vững trong DB và có thể được chuyển ra broker; hãy giới hạn dữ liệu, phân quyền và retention.

### Duplicate là trạng thái bình thường phải xử lý

Ngay cả khi claim outbox bằng row lock rất tốt, duplicate vẫn có thể do crash sau publish ACK trước `markSent`. Cần thiết kế từ đầu sao cho gửi một event hai lần **không làm trạng thái nghiệp vụ cuối thay đổi sai**.

## 16. Polling hay CDC?

| Tiêu chí | Polling publisher | CDC outbox |
|---|---|---|
| Cơ chế | Query bảng outbox theo lịch, claim/lease rồi gửi. | Đọc transaction log thay đổi của database, chuyển event đã commit. |
| Triển khai ban đầu | Dễ hiểu nếu có SQL/worker infrastructure. | Cần connector, quyền và quản lý change stream. |
| Độ trễ | Phụ thuộc polling interval/backlog. | Có thể thấp nhưng phụ thuộc pipeline CDC và tải. |
| Tải database | Query/index/cleanup định kỳ. | Đọc log và sử dụng replication/CDC resources. |
| Đa worker | Cần claim, lease, backoff và xử lý concurrency. | Cần cấu hình connector/partition/ownership phù hợp. |
| Ordering | Phải thiết kế theo aggregate/partition. | Cũng cần xác định thứ tự theo nguồn và phía broker. |
| Duplicate/replay | Có thể phát lại sau crash/lease expiry. | Có thể phát lại sau failover/offset recovery. |
| Vận hành | Theo dõi backlog, stuck lease, dead events. | Theo dõi lag, connector health, replication slot/log retention. |

CDC không miễn trừ idempotency ở consumer. Đồng thời, nếu CDC đọc một outbox table có status được cập nhật nhiều lần, phải cấu hình chỉ phát **sự kiện nghiệp vụ đúng** (ví dụ row insert/event envelope) thay vì biến mọi thay đổi trạng thái thành event gửi tới consumer.

## 17. Khi nào cân nhắc các phương án khác?

### 17.1. Gửi trực tiếp với best-effort

Nếu mất một thông báo không ảnh hưởng đến tính đúng đắn, hoặc downstream có thể tái tạo toàn bộ trạng thái từ DB qua lần đồng bộ định kỳ, direct publishing có thể được chấp nhận. Nhưng cần **ghi rõ chấp nhận mất event/độ lệch**; không mô tả nó như bảo đảm exactly-once.

### 17.2. Chỉ output vào broker

Nếu job **chỉ** sản xuất message và không cần commit dữ liệu nghiệp vụ trong DB khác, có thể dùng producer transaction/ack của broker theo hợp đồng. Khi đó bài toán khác với dual write DB + broker. Dù producer có transaction, consumer vẫn cần hiểu replay/offset và bảo đảm output cuối; producer transaction không tự biến mọi side effect downstream thành exactly-once.

### 17.3. Hai-phase commit (XA/2PC)

Trong môi trường cần một transaction logic trên nhiều tài nguyên **có hỗ trợ XA**, có thể xem xét JTA/XA và hai-phase commit. Tuy nhiên:

- Mỗi tài nguyên/driver/broker phải hỗ trợ đúng chuẩn và tham gia được.
- Thiết lập, transaction recovery và vận hành phức tạp.
- Có nguy cơ blocking, coordinator failure hoặc giảm throughput.
- Không phải mọi API ngoài hoặc storage đều tham gia XA.

Đối với nhiều hệ thống event-driven, transactional outbox đơn giản hơn trong vận hành và phù hợp eventual consistency; nhưng không có nghĩa XA “luôn sai” hoặc outbox “luôn đúng”. Phải dựa trên yêu cầu atomicity và khả năng thực tế của các tài nguyên.

### 17.4. Saga và compensation

Khi một chuỗi thao tác nghiệp vụ kéo dài qua nhiều service mà không thể có global transaction, có thể áp dụng saga, trạng thái bù trừ và idempotency. Outbox có thể là cơ chế **phát event bền vững** cho từng bước saga, nhưng không thay thế logic compensation.

### 17.5. File/object storage

Nếu đầu ra là CSV/Parquet/file trên object storage, transaction DB không tự rollback file. Một mô hình phù hợp có thể là:

- Ghi vào path/version tạm, không để consumer đọc.
- Kiểm tra số dòng, checksum và schema.
- Công bố manifest/pointer sau khi file hoàn tất và đạt quality gate.
- Có quy trình cleanup file tạm và retry/idempotency.

Outbox chỉ cần nếu còn phải phát event “file đã sẵn sàng” tới hệ thống khác. Atomic rename phụ thuộc filesystem và vị trí nguồn/đích; không mặc định một thao tác move trên object storage là atomic với DB.

## 18. Hiệu năng và chi phí vận hành

### Chi phí của transaction output

Ghi vào một DB transaction theo chunk thường đơn giản hơn, nhưng vẫn cần:

- Chọn `chunkSize` để cân bằng số commit, bộ nhớ, thời gian giữ lock và khả năng rollback.
- Giới hạn connection pool và concurrency của các partition.
- Tạo index/unique constraint phục vụ business key.
- Cấu hình timeout/lock và lỗi retry cụ thể, không retry vô hạn.
- Theo dõi commit/rollback counts và đối soát khi commit outcome không rõ.

### Chi phí của outbox

Thêm outbox tạo write amplification: mỗi thay đổi nghiệp vụ có thể cần thêm một hàng event, index và transaction log. Còn có:

- Dung lượng outbox PENDING/SENT, bloat/index maintenance, retention.
- Dispatcher capacity và giới hạn số event gửi mỗi giây.
- Broker quota, publish timeout và retry backoff.
- Theo dõi lỗi serialization/schema và event “poison”.
- Duplicate delivery phải được xử lý ở consumer.
- Chi phí reconciliation nếu nguồn/đích không đồng bộ.

Nếu job xuất hàng chục triệu event, hãy đo throughput của cả DB writer, outbox publisher, broker và consumer. `JobExecution.COMPLETED` có thể diễn ra trước khi dispatcher chuyển hết backlog; **tốc độ xử lý cuối cùng có thể bị giới hạn ở hệ thống ngoài**, không phải ở chunk writer.

### Outbox không nên trở thành “bảng SENT vô hạn”

Sau khi event đã `SENT` và vượt thời gian audit/khả năng replay được yêu cầu, cần có cơ chế lưu trữ lâu dài hoặc cleanup theo chính sách:

- Không xóa `PENDING`/`IN_FLIGHT` đang chờ delivery.
- Không dọn quá sớm event cần đối soát hoặc replay.
- Dọn theo chunk/partition phù hợp, tránh transaction delete khổng lồ.
- Nếu dùng CDC, kiểm tra tương tác giữa dọn bảng, replication log và connector.

Kế hoạch retention cần xuất phát từ SLA, audit và mục tiêu khôi phục, không chỉ mục tiêu làm bảng nhỏ đi.

## 19. Monitoring phải theo hai vòng đời

Khi dùng outbox, có **hai khái niệm thành công khác nhau**:

1. **Batch output persisted:** dữ liệu nghiệp vụ và event intent đã commit.
2. **Event delivered/consumed:** dispatcher đã phát event và downstream xử lý theo hợp đồng.

Không nên hiển thị một dấu `COMPLETED` duy nhất cho cả hai.

| Vòng đời | Chỉ số nên theo dõi |
|---|---|
| Spring Batch step | `readCount`, `writeCount`, `commitCount`, `rollbackCount`, `BatchStatus`, `ExitStatus`. |
| Kết quả nghiệp vụ DB | Số hàng/sum theo business key, unique business IDs, mismatch/reject. |
| Outbox pending | Count PENDING, tuổi event cũ nhất chưa gửi, backlog theo loại event. |
| Dispatcher | Publish attempts, thành công/thất bại, retry, claim lease hết hạn. |
| Dead-letter/quarantine | Số event `DEAD`, nguyên nhân đã chuẩn hóa, tuổi sự cố. |
| Broker | ACK/nack, latency, redelivery, lag theo partition nếu có. |
| Consumer | Event trùng được bỏ qua, xử lý thành công, lỗi nghiệp vụ, kết quả đích. |
| End-to-end | Độ trễ từ business DB commit đến consumer result, số sự kiện thiếu/thừa theo reconciliation. |

Một log outbox an toàn:

~~~json
{
  "event": "outbox.dispatch.completed",
  "jobName": "dailyLedgerJob",
  "batchKey": "2026-11-15:store-A",
  "jobExecutionId": 8102,
  "outboxId": 12005,
  "eventId": "LEDGER_POSTED:TX-001",
  "eventType": "LEDGER_POSTED",
  "attempt": 2,
  "result": "SENT",
  "durationMs": 48
}
~~~

Đây là schema **do ứng dụng định nghĩa**, không phải log mặc định Spring Batch. Event ID và business key cần được đánh giá về phân loại dữ liệu trước khi logging; không log đầy đủ payload có PII hoặc secrets. Nếu `JobRepository` và dispatcher nằm ở process khác nhau, các correlation fields cần được lưu bền vững hoặc truyền trong outbox envelope.

Không dùng `eventId`, `jobExecutionId` hoặc correlation ID duy nhất làm metric label thông thường, vì cardinality sẽ tăng mạnh. Để ID chi tiết trong log/audit/tracing, còn metrics dùng nhãn hữu hạn như `eventType`, `status` và nhóm lỗi.

## 20. Kiểm thử các failure quan trọng

Một bộ test triển khai outbox đáng tin cậy không thể chỉ chạy happy path. Cần gây lỗi tại các thời điểm cụ thể và kiểm tra **trạng thái đã commit**, kể cả sau restart.

| Kịch bản | Cách tạo lỗi | Invariant cần xác nhận |
|---|---|---|
| Writer DB lỗi trước outbox insert | SQL constraint hoặc exception có chủ đích | Không có business row/outbox row sau rollback chunk. |
| Lỗi sau business insert nhưng trước outbox insert | Throw trong writer giữa hai lệnh | Cả hai rollback nếu cùng transaction. |
| Lỗi sau outbox insert nhưng trước commit | Throw sau lệnh thứ hai | Cả hai rollback; không có intent “mồ côi”. |
| Commit thành công, job process crash | Dừng process sau commit trong test có điều khiển | Business row và PENDING outbox tồn tại, dispatcher vẫn có thể gửi. |
| Job restart/replay cùng event | Gọi lại với cùng business ID | Không tạo ledger/outbox duplicate. |
| Hai writer đồng thời cùng business event | Concurrency test trên DB có unique constraint | Chỉ một kết quả nghiệp vụ và một event intent hợp lệ. |
| Broker tạm offline | Fake publisher trả lỗi | Outbox không bị xóa; có retry/backoff và backlog rõ. |
| Publish ACK thành công nhưng mark SENT lỗi | Fault injection sau ACK | Event có thể gửi lại; consumer không áp dụng tác động hai lần. |
| Consumer nhận duplicate | Gửi cùng event ID hai lần | Business output đúng một lần. |
| Dispatcher crash khi giữ lease | Tắt worker sau claim | Event được claim lại sau timeout mà không mất. |
| Hai dispatcher chạy song song | Cùng claim PENDING | Không có tác động nghiệp vụ trùng ở consumer; ownership/lease nhất quán. |
| Poison event | Payload không tương thích hoặc lỗi vĩnh viễn | Chuyển `DEAD`/quarantine theo policy, cảnh báo; không biến mất âm thầm. |
| Event ordering | Hai event cùng aggregate, retry event trước | Consumer thấy và áp dụng đúng thứ tự hoặc phát hiện thiếu sequence theo hợp đồng. |
| Reconciliation gate fail | Output count/sum sai | Không công bố `BatchPublished` thành công. |

### Test rollback thực sự

Trong integration test, có thể dùng một writer test ghi `ledger_entry` rồi ném exception trước lệnh tạo outbox. Khi chunk rollback, query database sau step và assert:

~~~sql
SELECT COUNT(*)
FROM ledger_entry
WHERE event_id = 'TX-TEST-1';

SELECT COUNT(*)
FROM outbox_event
WHERE event_id = 'LEDGER_POSTED:TX-TEST-1';
~~~

Cả hai count cần bằng **0** khi rollback đúng, datasource/transaction manager đúng và test chưa có hàng từ lần trước. Đừng chỉ assert Spring Batch báo `FAILED` rồi kết luận rollback đã diễn ra: writer có thể vô tình mở connection auto-commit riêng.

### Test happy path có duplicate delivery

1. Chạy batch với một event `TX-TEST-1`.
2. Xác nhận DB có một ledger row và một outbox row PENDING.
3. Dispatcher gửi event, consumer áp dụng kết quả và commit.
4. Giả lập lỗi trước cập nhật `SENT` ở outbox.
5. Cho dispatcher gửi lại cùng event ID.
6. Assert consumer output vẫn chỉ có **một tác động nghiệp vụ** và marker xử lý event không trùng.

Một test như vậy chứng minh phần idempotency cần thiết trong điều kiện outbox **at-least-once**, thay vì chỉ kiểm tra dispatcher gọi publisher một lần trong happy path.

### Test batch-level publish gate

Chuẩn bị ba input, khiến một record bị writer reject ngoài chính sách hoặc làm tổng tiền đầu ra sai so với manifest. Sau load, reconciliation phải `FAILED` hoặc trả kết quả quality gate không đạt; consumer **không** được nhận `BatchPublished` thành công cho version đó. Nếu event-per-item được phát trước khi gate kiểm tra, kiến trúc đã không đáp ứng yêu cầu “chỉ công bố sau khi toàn bộ batch đúng”.

## 21. Quy trình chọn kiến trúc theo tình huống

| Tình huống | Phương án khởi đầu phù hợp | Điểm cần xác nhận |
|---|---|---|
| Job import CSV vào một bảng PostgreSQL | **Output transaction** với JDBC writer, unique key, reconciliation | Reader/writer cùng transaction manager; restart không duplicate. |
| Job ghi nhiều bảng trong cùng database | **Một transaction của chunk** | Không có delegate tự commit riêng; ràng buộc dữ liệu đúng. |
| Ghi DB và phát Kafka event | **DB transaction + outbox** | Event ID ổn định, dispatcher, consumer idempotent, backlog monitoring. |
| Ghi DB và gọi API đối tác bắt buộc nhận | **Outbox/intent + dispatcher** khi API cho idempotency/tra trạng thái | Timeout ambiguity, retry, eventual consistency, compensation. |
| Chỉ xuất event vào broker | Dùng **producer semantics của broker** theo yêu cầu | Không nhầm broker transaction với transaction DB khác. |
| Ghi file CSV và công bố khi batch xong | **File tạm + validation + publish manifest/rename** | Atomicity/visibility của storage; cleanup sau crash. |
| Tính kết quả cả lô rồi thông báo sẵn sàng | **Staging + reconciliation gate + BatchPublished outbox event** | Không phát sự kiện thành công trước khi quality gate PASS. |
| Nhiều DB hoặc service cần đồng bộ | Cân nhắc **outbox, saga/compensation hoặc XA nếu tài nguyên hỗ trợ** | Yêu cầu latency/atomicity và chi phí vận hành cụ thể. |

### Luồng quyết định

~~~mermaid
flowchart TD
    A["Output thực sự gồm những gì?"] --> B{"Chỉ một tài nguyên\ntransactional?"}
    B -->|Có| C["Dùng chunk transaction\n+ idempotent writer"]
    B -->|Không| D{"Có thể chấp nhận\nphát bất đồng bộ?"}
    D -->|Có| E{"Có database nguồn chân lý\nđể commit intent?"}
    E -->|Có| F["DB transaction + outbox\n+ at-least-once dispatcher\n+ idempotent consumer"]
    E -->|Không| G["Thiết kế durable intent khác\nhoặc cơ chế messaging phù hợp"]
    D -->|Không| H["Xem lại yêu cầu atomicity\nXA nếu tất cả hỗ trợ\nhoặc thiết kế compensation"]
    C --> I["Kiểm thử crash/restart\nvà reconciliation"]
    F --> I
    G --> I
    H --> I
~~~

**Không dùng outbox chỉ vì hệ thống có message broker.** Nếu job chỉ đọc data rồi xuất message và không có một database cần commit trạng thái nghiệp vụ, có thể không có vấn đề dual-write mà outbox cần giải quyết. Ngược lại, nếu có DB+broker cần bền vững, direct send với `@Transactional` thường không giải quyết được atomicity.

## 22. Những sai lầm thường gặp

**“Outbox thay thế database transaction.”** Sai: outbox **cần cùng transaction** để commit business row và event intent. Hai transaction riêng phá bảo đảm nguyên tử ban đầu.

**“`@Transactional` quanh `save()` và `send()` là đủ.”** Không đúng nếu broker hoặc API không tham gia transaction coordinator phù hợp. Database rollback không hoàn tác message đã nhận.

**“Gửi message trong `afterWrite` thì chắc chắn đã commit.”** Callback thường chạy trước commit của chunk; gửi tại đó có thể phát event khi DB còn rollback được.

**“Gửi trong `afterCommit` thì không thể mất event.”** Process vẫn có thể crash sau commit trước khi callback/send hoàn tất. Cần durable intent nếu bắt buộc eventual delivery.

**“Dispatcher có lock thì không còn duplicate.”** Lock giúp giảm tranh chấp claim; crash sau publish ACK trước mark SENT vẫn tạo duplicate. Idempotent consumer là bắt buộc khi tác động cần đúng một lần.

**“Cứ đánh dấu SENT trước khi gửi để tránh duplicate.”** Nếu crash sau mark, event có thể bị mất. Thường phải gửi/nhận ACK trước và chấp nhận gửi lại.

**“Một lần JobExecution COMPLETED là mọi message đã tới consumer.”** Outbox có vòng đời riêng; batch có thể kết thúc khi backlog chưa được dispatch. Cần monitoring delivery và đối soát.

**“Dùng UUID mới mỗi lần retry là tốt nhất.”** Với event đã xử lý, UUID mới khiến unique event ID không nhận diện được trùng. Event key nên ổn định theo business identity.

**“Có outbox thì không cần unique business key ở ledger.”** Writer vẫn có thể replay sau crash hoặc restart; ledger phải tự bảo vệ output trùng theo nghiệp vụ.

**“Polling ORDER BY created_at là đủ giữ ordering.”** Với nhiều dispatcher, lease expiry, broker partitioning và retry, thứ tự có thể thay đổi. Cần sequence/aggregate policy nếu ordering là invariant.

**“Outbox event-per-item luôn tốt hơn BatchPublished.”** Không. Khi chỉ công bố sau reconciliation, một event cho toàn batch hoặc cơ chế staging có thể phù hợp hơn.

**“Xóa hết event SENT là được.”** Retention/cleanup phải xét audit, replay, CDC connector và chính sách phục hồi; không xóa dữ liệu PENDING hay DEAD chưa xử lý chỉ vì tiết kiệm dung lượng.

**“Đưa toàn bộ domain object vào payload sẽ tiện.”** Dễ làm lộ dữ liệu nhạy cảm và khiến consumer phụ thuộc schema nội bộ; chỉ xuất dữ liệu theo hợp đồng event versioned.

## 23. Quy trình triển khai từng bước

1. **Ghi invariant nghiệp vụ.** Xác định business key, yêu cầu không mất event, độ trễ chấp nhận được, ordering và mức chấp nhận duplicate.
2. **Vẽ ranh giới transaction.** Tài nguyên nào thuộc chunk transaction? Database của `JobRepository` và business DB có trùng không? Có thao tác tự commit không?
3. **Chọn mô hình output.** Nếu chỉ một DB, dùng transaction + idempotent writer. Nếu cần DB + broker/API đáng tin cậy, thêm outbox trong cùng transaction.
4. **Định nghĩa event contract.** Event ID ổn định, aggregate key, schema version, payload được phép xuất và các field giúp consumer chống trùng.
5. **Bảo vệ writer khi restart.** Ràng buộc unique/conditional update, giữ identifying `JobParameters` và kiểm tra conflict payload.
6. **Thiết kế dispatcher.** Claim/lease hoặc CDC, confirmation, retry/backoff, dead-letter/quarantine, retention và concurrency limits.
7. **Thiết kế idempotent consumer.** Dùng marker cùng transaction của business output hoặc idempotency key ở hệ thống đích, có chính sách ACK sau commit.
8. **Quyết định granularity công bố.** Event từng item hay một event sau khi toàn bộ batch đạt reconciliation; không để consumer đọc kết quả chưa được duyệt nếu yêu cầu atomic batch publication.
9. **Bổ sung monitoring.** Phân biệt batch persisted với event delivered, theo dõi backlog, tuổi pending, lỗi publish và kết quả đích.
10. **Kiểm thử crash và retry.** Fault injection trước/sau DB commit, sau broker ACK, lease hết hạn, consumer redelivery và job restart.
11. **Xây quy trình vận hành.** Khi nào replay event, khi nào quarantine, cách tra event theo business key và cách xử lý mismatch mà không tạo duplicate.

## Kết luận

**Chọn output transaction hay outbox** thực chất là chọn **ranh giới bảo đảm nhất quán** cho đầu ra của Spring Batch. Nếu job chỉ cần thay đổi dữ liệu trong một database transaction, một writer đúng transaction, unique business key và kiểm tra kết quả thường là giải pháp đơn giản, mạnh và dễ vận hành. Nếu job cần **ghi dữ liệu rồi thông báo bền vững tới hệ thống khác**, transactional outbox giải quyết cửa sổ crash giữa commit DB và phát thông điệp bằng cách lưu *event intent* cùng transaction nghiệp vụ.

Outbox không đem lại exactly-once end-to-end: dispatcher vẫn có thể gửi lặp, consumer phải idempotent, và batch `COMPLETED` không đồng nghĩa mọi event đã được xử lý ở downstream. Khi đã xác định rõ transaction boundary, retry/restart semantics, event key, publish gate, ordering và monitoring, mỗi phương án mới thực sự đem lại mức độ nhất quán mà nghiệp vụ yêu cầu — không chỉ làm job chạy thành công về mặt kỹ thuật.
