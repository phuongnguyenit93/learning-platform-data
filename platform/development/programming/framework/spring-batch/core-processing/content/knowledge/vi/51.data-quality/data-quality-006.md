# Duplicate detection trong Spring Batch: phát hiện dữ liệu trùng và xử lý nhất quán

## 1. Duplicate detection là gì?

Trong **Spring Batch Core Processing**, *duplicate detection* là việc nhận diện hai hay nhiều bản ghi đầu vào đại diện cho **cùng một thực thể, cùng một sự kiện hoặc cùng một thao tác nghiệp vụ** theo quy tắc đã xác định.

Một job nhập đơn hàng có thể gặp dữ liệu trùng vì:

- File đối tác chứa cùng một đơn hàng hai lần.
- Cùng một file được gửi hoặc chạy lại sau khi hệ thống mất kết nối.
- API phân trang trả về một record trong hai trang.
- Message broker giao lại một sự kiện chưa được xác nhận.
- Job rollback rồi retry hoặc restart và nhìn thấy lại bản ghi đã từng xử lý.
- Hai worker hoặc hai job chạy đồng thời cùng lấy dữ liệu của một khoảng thời gian.

Nếu không phát hiện và xử lý trùng, batch có thể tạo hai đơn hàng, ghi hai giao dịch kế toán hoặc gửi thông báo hai lần. Tuy nhiên **không phải mọi bản ghi có cùng một trường đều là bản ghi trùng**. Ví dụ một khách hàng đặt hai đơn có cùng số tiền là điều bình thường; hai lần cập nhật trạng thái của cùng đơn hàng cũng có thể là hai sự kiện hợp lệ.

Mục tiêu trước tiên là định nghĩa **thế nào là trùng**, sau đó chọn vị trí kiểm tra và chính sách xử lý phù hợp.

Ví dụ:

```text
File orders-20250512.csv

source,order_id,amount
PARTNER_A, O-101 ,120000
PARTNER_A,O-102,50000
PARTNER_A,o-101,120000
PARTNER_B,O-101,30000
```

Nếu quy tắc khóa trùng là `(source, normalized_order_id, business_date)`, dòng thứ nhất và thứ ba là trùng nhau; dòng thứ tư không trùng vì thuộc nguồn `PARTNER_B`. Nếu mã đơn hàng duy nhất toàn hệ thống, kết luận lại khác. Quy tắc phải xuất phát từ mô hình nghiệp vụ, không thể chọn chỉ vì hai chuỗi trông giống nhau.

### Kết quả mong đợi

Sau một lần nhập dữ liệu, hệ thống cần biết:

| Kết quả | Ý nghĩa |
|---|---|
| `ACCEPTED` | Bản ghi mới, được phép đi tiếp |
| `EXACT_DUPLICATE` | Cùng khóa và cùng nội dung theo tiêu chí đã thống nhất |
| `CONFLICTING_DUPLICATE` | Cùng khóa nhưng nội dung nghiệp vụ khác nhau |
| `INVALID_KEY` | Không tạo được khóa hợp lệ (rỗng, sai định dạng, thiếu trường bắt buộc) |
| `REPLAYED_EVENT` | Sự kiện đã được xử lý trong một lần chạy trước |
| `POSSIBLE_DUPLICATE` | Chỉ giống nhau theo quy tắc gần đúng, cần đánh giá thêm |

Không nên gộp tất cả thành một nhãn “duplicate” rồi bỏ qua. **Trùng hoàn toàn**, **đụng khóa dữ liệu** và **một sự kiện hợp lệ mới của cùng thực thể** có thể cần ba hành vi khác nhau.

## 2. Phân biệt các phạm vi trùng lặp

| Phạm vi | Ví dụ | Kỹ thuật phù hợp |
|---|---|---|
| **Trong một chunk** | Hai item cùng mã trong 200 item chuẩn bị ghi | Kiểm tra khóa trong nhóm; unique constraint vẫn là lớp bảo vệ cuối |
| **Giữa các chunk trong cùng execution** | Item ở chunk thứ nhất trùng item ở chunk thứ năm | Bảng staging/index unique hoặc state bền vững |
| **Giữa các lần chạy/restart** | Job đọc lại sự kiện đã commit từ lần trước | Business idempotency key, DB unique/upsert |
| **Giữa các file/nguồn** | Cùng đơn được gửi ở hai file khác nhau | Khóa gồm namespace nguồn hoặc global business identifier theo hợp đồng |
| **Giữa các worker/partition** | Hai worker xử lý cùng ID | Ràng buộc unique/atomic operation ở nơi lưu chung |
| **Trùng gần đúng** | Tên, địa chỉ, email gần giống | Quy tắc matching có xác suất, review/quarantine |

Một bộ nhớ `HashSet` trên một JVM chỉ nhìn thấy trạng thái của instance chứa nó. Nó không giải quyết đầy đủ tình huống hai worker độc lập, dữ liệu đã commit của lần chạy trước hoặc khôi phục sau sự cố.

## 3. Thiết kế business key trước khi viết code

**Business key** là tổ hợp thuộc tính giúp nhận diện một bản ghi hoặc một thao tác theo quy tắc nghiệp vụ.

Ví dụ:

- Đơn hàng: `(sourceSystem, externalOrderId)`.
- Giao dịch thanh toán: `(provider, providerTransactionId)`.
- Sự kiện cập nhật: `(sourceSystem, sourceEventId)`.
- Bản ghi tổng hợp theo ngày: `(businessDate, accountId, metricType)`.
- Một snapshot phiên bản: `(entityId, effectiveDate, version)`.

Nếu việc sửa đơn hàng được gửi dưới dạng một **event mới** có cùng `externalOrderId` nhưng `eventId` hoặc `version` khác, thì deduplicate dựa vào `externalOrderId` đơn lẻ sẽ làm mất bản cập nhật hợp lệ.

### 3.1. Ba câu hỏi để chốt khóa

1. **Khóa có bao gồm nguồn không?** `O-101` từ hai đối tác có phải cùng một đơn không?
2. **Khóa có bao gồm ngày hay phiên bản không?** Cùng ID ở hai business date là một bản ghi mới hay dữ liệu phát lại?
3. **Khóa tồn tại bao lâu?** Mãi mãi, theo cửa sổ bảy ngày, hay chỉ trong một import batch?

Không có khóa nào phù hợp với mọi bảng. Cần lưu quy tắc trong hợp đồng dữ liệu và mã xử lý để có thể audit hoặc xử lý lại.

### 3.2. Chuẩn hóa khóa trước khi so sánh

Dữ liệu thường khác nhau ở khoảng trắng, chữ hoa/chữ thường và định dạng. Ví dụ:

```text
" O-101 "
"o-101"
"O-101"
```

Nếu đối tác định nghĩa mã đơn **không phân biệt hoa/thường**, ba giá trị này cùng một khóa. Ta có thể chuẩn hóa bằng `strip()` và `toUpperCase(Locale.ROOT)`.

```java
import java.util.Locale;

public final class BusinessKeyNormalizer {

    private BusinessKeyNormalizer() {
    }

    public static String normalizeRequired(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Business key is missing");
        }

        String canonical = raw.strip().toUpperCase(Locale.ROOT);

        if (canonical.isBlank()) {
            throw new IllegalArgumentException("Business key is blank");
        }

        return canonical;
    }
}
```

`Locale.ROOT` giữ phép đổi hoa/chữ thường ít phụ thuộc locale mặc định của máy chạy. Tuy nhiên việc chuẩn hóa **phải theo hợp đồng của nguồn dữ liệu**: một mã nhạy với chữ hoa/chữ thường có thể coi `abc` và `ABC` là hai giá trị khác nhau. Không tự động xóa dấu tiếng Việt, loại dấu câu hoặc chuyển `00123` thành `123` nếu những khác biệt đó có ý nghĩa nghiệp vụ.

Với Unicode, một số hệ thống cần chuẩn hóa dạng ký tự bằng `java.text.Normalizer` (NFC/NFKC) để so sánh ổn định; hãy xác định rõ phép chuẩn hóa có làm gộp nhầm định danh hợp lệ không.

### 3.3. Tránh dùng key có thể rỗng

Nếu mã đơn hàng thiếu, không nên tự gán khóa `UNKNOWN` cho mọi bản ghi. Khi đó các bản ghi khác nhau có thể bị gộp thành một “bản ghi trùng” giả.

Hãy kiểm tra và đưa item vào nhóm dữ liệu lỗi (`INVALID_KEY`), hoặc cho step thất bại tùy quy tắc. Khi dùng database, cần chú ý một số hệ quản trị cho phép nhiều `NULL` trong unique constraint; vì vậy các cột tạo khóa dedup nên khai báo `NOT NULL` khi hợp đồng yêu cầu.

## 4. Chọn chính sách xử lý duplicate

Sau khi nhận diện khóa trùng, còn phải quyết định item nào được giữ.

| Chính sách | Mô tả | Tình huống dùng |
|---|---|---|
| **First wins** | Giữ bản xuất hiện đầu tiên, bỏ bản sau | File đã có thứ tự ưu tiên đáng tin cậy |
| **Last wins** | Giữ bản sau cùng theo một thứ tự xác định | Snapshot mới thay snapshot cũ |
| **Latest event time wins** | Chọn theo timestamp sự kiện và tie-breaker | Nguồn gửi nhiều phiên bản có thời gian nghiệp vụ |
| **Highest version wins** | Chọn phiên bản lớn nhất | Dữ liệu có version monotonic |
| **Reject all conflicts** | Không nhập khi cùng key mà nội dung khác nhau | Dữ liệu tài chính hoặc kiểm toán nghiêm ngặt |
| **Merge** | Kết hợp một số trường từ nhiều bản ghi | Hợp nhất hồ sơ khách hàng với quy tắc đầy đủ |
| **Manual review** | Đưa vào quarantine | Không thể chọn an toàn bằng quy tắc tự động |

**First wins theo thứ tự đọc** chỉ có nghĩa rõ khi thứ tự dữ liệu được bảo đảm. Nếu reader phân trang không có `ORDER BY`, file nhập song song hoặc partition chạy đồng thời, “bản đầu tiên” có thể thay đổi giữa các lần chạy.

Cần định nghĩa **tie-breaker** rõ ràng. Ví dụ chọn bản mới nhất theo `eventTime DESC, eventSequence DESC, immutableEventId DESC`, với giả định các thuộc tính đó ổn định và đáng tin. Nếu hai bản ghi có cùng `eventTime` mà giá trị khác nhau, chỉ chọn ngẫu nhiên một bản sẽ gây khó truy vết.

### 4.1. Exact duplicate và conflicting duplicate

Ví dụ hai bản ghi cùng khóa:

```json
{"source":"PARTNER_A","orderId":"O-101","amount":120000}
{"source":"PARTNER_A","orderId":"O-101","amount":120000}
```

Có thể coi là bản phát lại không làm thay đổi dữ liệu.

Ngược lại:

```json
{"source":"PARTNER_A","orderId":"O-101","amount":120000}
{"source":"PARTNER_A","orderId":"O-101","amount":900000}
```

Đây là **xung đột dữ liệu**. `ON CONFLICT DO NOTHING` sẽ âm thầm bỏ bản thứ hai, nhưng có thể che một sửa đổi hợp lệ hoặc lỗi nghiêm trọng. Nếu yêu cầu là “đơn hàng chỉ có một số tiền”, phải xác minh payload, version và chính sách conflict, sau đó có thể dừng hoặc quarantine.

## 5. Duplicate detection nằm ở đâu trong Spring Batch?

Một step chunk-oriented thường có chuỗi:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Transaction commit / ExecutionContext checkpoint
```

Có thể đặt kiểm tra duplicate ở ba nơi, với các hệ quả khác nhau.

### 5.1. Ở Reader hoặc query nguồn

Reader có thể đọc tập dữ liệu đã được loại trùng bằng SQL hoặc một bước staging. Ví dụ query lấy mỗi khóa một bản theo quy tắc deterministic.

Ưu điểm: ít item đi vào processor/writer. Nhược điểm: có thể không ghi lại lịch sử đầy đủ những bản ghi bị loại nếu không lưu dữ liệu thô, và query phức tạp có thể làm tăng tải database.

### 5.2. Ở Processor

Processor có thể chuẩn hóa key, phát hiện một số trường hợp trùng và trả `null` để **filter** item.

```java
@Override
public CleanOrder process(RawOrder item) {
    if (isDuplicate(item)) {
        return null; // Filter; không phải exception skip.
    }
    return normalize(item);
}
```

Đây chỉ là minh họa khái niệm: `isDuplicate(...)` phải được thiết kế đúng tính nhất quán, giao dịch và concurrency. Nếu processor dùng một `HashSet` mutable trong JVM, có thể tạo lỗi khi rollback/retry/restart; phần sau sẽ giải thích.

Trong Spring Batch:

- Processor trả `null` ⇒ tăng `filterCount`.
- Reader ném exception được skip ⇒ tăng `readSkipCount`.
- Processor ném exception được skip ⇒ tăng `processSkipCount`.
- Writer ném exception được skip ⇒ tăng `writeSkipCount`.

**Duplicate được loại theo quy tắc nghiệp vụ thường là filter hoặc kết quả riêng trong database, không nên mặc định ném exception để tăng skip count.**

### 5.3. Ở Writer / Database

Ràng buộc `UNIQUE` ở database giúp bảo vệ tính duy nhất ngay cả khi có **nhiều worker hoặc nhiều tiến trình cạnh tranh**. Với SQL hỗ trợ thao tác atomic như PostgreSQL `ON CONFLICT`, writer có thể chèn bản ghi nếu chưa tồn tại, bỏ qua bản trùng, hoặc cập nhật theo policy rõ ràng.

Đây thường là lớp bảo đảm cuối khi duplicate có thể xuất hiện sau rollback/restart hoặc từ nhiều nguồn.

## 6. Vì sao `HashSet` trong ItemProcessor có thể không an toàn?

Một ví dụ đơn giản:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.batch.item.ItemProcessor;

public class InMemoryDedupProcessor
        implements ItemProcessor<String, String> {

    private final Set<String> seen = new HashSet<>();

    @Override
    public String process(String item) {
        return seen.add(item) ? item : null;
    }
}
```

Cách này hoạt động trong một vòng duyệt danh sách đơn giản, nhưng **không đủ an toàn cho fault-tolerant Spring Batch production**.

### 6.1. Lỗi sau rollback

Giả sử processor thấy `O-101` và thêm vào `seen`. Sau đó writer lỗi, transaction rollback:

```text
Process O-101
    |
    +-- seen.add("O-101") -> true
    |
Writer gặp lỗi
    |
Transaction rollback trong database
    |
Retry chunk
    |
Process O-101 lại
    |
    +-- seen.add("O-101") -> false
    |
Filter O-101 dù nó chưa được commit thành công
```

`HashSet` nằm trong bộ nhớ Java, **không rollback theo transaction của database**. Lần xử lý lại có thể bỏ mất bản ghi hợp lệ.

Ngoài ra, tùy cấu hình, Spring Batch có thể cache kết quả processor khi retry. Hành vi cụ thể còn tùy fault-tolerance policy và việc bật/tắt processor transactionality. Thiết kế an toàn không nên dựa vào giả định processor chỉ chạy đúng một lần cho mỗi item.

### 6.2. Lỗi khi restart

Nếu job đã commit một số chunk rồi tiến trình chết, `HashSet` trong JVM mới thường rỗng. Các bản ghi đã ghi ở lần trước không còn được nhận biết bởi set đó. Ngược lại, nếu muốn ghi `seen` vào `ExecutionContext`, tập key có thể rất lớn và tốn chi phí serialize/checkpoint, chưa kể rủi ro nhất quán giữa checkpoint và side effect.

### 6.3. Lỗi khi chạy song song

`HashSet` thông thường không thread-safe; nhiều worker JVM lại có mỗi set riêng. Đổi sang `ConcurrentHashMap.newKeySet()` chỉ xử lý truy cập đồng thời trong **cùng JVM**, không biến set thành nguồn dữ liệu bền vững và không cho nó khả năng rollback transaction.

**Cách dùng phù hợp:** `HashSet` có thể hữu ích cho validation nhỏ, thuần bộ nhớ, trong một phép tính có đầu vào cố định và không liên quan tới commit/restart. Để bảo đảm duy nhất khi ghi dữ liệu batch, nên dựa vào khóa nghiệp vụ và storage có thao tác atomic.

## 7. Kiến trúc ổn định: chuẩn hóa ở processor, deduplicate ở database

Một kiến trúc thông dụng:

```text
             CSV / API / Message
                       |
                       v
                   ItemReader
                       |
                       v
             Normalize / Validate
                 ItemProcessor
                       |
                       v
              JDBC Batch Writer
                       |
                       v
        PostgreSQL UNIQUE business key
               /             \
       insert thành công    conflict
               |             |
               v             v
          stage_orders    DO NOTHING / audit / reject
               |
               v
          Commit chunk
```

Dữ liệu có khóa được chuẩn hóa một cách deterministic ở processor. Database là nơi phân xử cuối cùng về tính duy nhất bằng index/constraint. Khi một chunk rollback, phần insert chưa commit rollback theo, và lần retry có thể thử lại an toàn.

### 7.1. Thiết kế bảng staging

Giả sử nghiệp vụ định nghĩa một đơn hàng duy nhất bởi `(businessDate, sourceName, normalizedOrderId)`:

```sql
CREATE TABLE stage_orders (
    business_date DATE NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    order_id_norm VARCHAR(128) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    inserted_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_stage_order
        UNIQUE (business_date, source_name, order_id_norm)
);
```

Đây là SQL ví dụ **cho PostgreSQL**. Nếu cùng một đơn hàng có thể phát sinh trên nhiều ngày nhưng vẫn cần duy nhất toàn hệ thống, không được chọn `business_date` như một phần khóa duy nhất chỉ vì batch chạy theo ngày. Ngược lại, nếu dữ liệu là snapshot theo ngày thì thêm `business_date` có thể đúng.

Một ràng buộc `UNIQUE` hoạt động độc lập với số JVM, số thread, số partition và thời điểm dữ liệu được gửi đến, miễn là mọi luồng ghi vào **cùng storage authoritative**.

### 7.2. Các record Java cho reader và processor

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record RawOrder(
        String sourceName,
        String orderId,
        BigDecimal amount
) {
}

public record CleanOrder(
        LocalDate businessDate,
        String sourceName,
        String normalizedOrderId,
        BigDecimal amount
) {
}
```

`RawOrder` mô tả dữ liệu đọc được; `CleanOrder` đã có key chuẩn hóa và ngày nghiệp vụ.

### 7.3. Processor thuần hàm

```java
import java.time.LocalDate;

import org.springframework.batch.item.ItemProcessor;

public final class NormalizeOrderProcessor
        implements ItemProcessor<RawOrder, CleanOrder> {

    private final LocalDate businessDate;

    public NormalizeOrderProcessor(LocalDate businessDate) {
        this.businessDate = businessDate;
    }

    @Override
    public CleanOrder process(RawOrder raw) {
        String source = BusinessKeyNormalizer.normalizeRequired(
                raw.sourceName());

        String orderId = BusinessKeyNormalizer.normalizeRequired(
                raw.orderId());

        if (raw.amount() == null) {
            throw new IllegalArgumentException("Amount is missing");
        }

        return new CleanOrder(
                businessDate,
                source,
                orderId,
                raw.amount()
        );
    }
}
```

Processor không lưu `seen`, không gọi network và không tự ghi database. Cùng một input và `businessDate` sẽ cho cùng một output; do đó xử lý lại item sau rollback **không tạo tác dụng phụ trong processor**.

Nếu giá trị amount âm hoặc vượt biên là lỗi dữ liệu, thêm validation phù hợp theo hợp đồng nghiệp vụ. Không trộn quy tắc duplicate với validation khác khi thiết kế exception/skip.

### 7.4. Reader dùng file cố định và JobParameters

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<RawOrder> rawOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("rawOrderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .saveState(true)
            .linesToSkip(1)
            .delimited()
            .names("source", "order_id", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("source"),
                    fields.readString("order_id"),
                    fields.readBigDecimal("amount")))
            .build();
}
```

`@StepScope` tạo reader gắn với execution, đồng thời cho phép nhận `inputFile` từ `JobParameters`. `saveState(true)` cho phép reader hỗ trợ checkpoint/restart khi dữ liệu nguồn giữ nguyên; không nên đổi nội dung file giữa fail và restart mà kỳ vọng offset vẫn đúng.

### 7.5. Processor nhận business date cố định

```java
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
ItemProcessor<RawOrder, CleanOrder> normalizedOrderProcessor(
        @Value("#{jobParameters['businessDate']}")
        String businessDateText) {

    return new NormalizeOrderProcessor(
            LocalDate.parse(businessDateText)
    );
}
```

Ngày nghiệp vụ là dữ liệu cố định cho execution. Không tạo key dựa trên `LocalDate.now()` trong từng lời gọi processor vì ngày có thể đổi khi batch chạy qua nửa đêm hoặc được restart vào ngày khác.

### 7.6. Writer dùng `JdbcBatchItemWriter` và `ON CONFLICT`

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<CleanOrder> stagingOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<CleanOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO stage_orders (
                    business_date,
                    source_name,
                    order_id_norm,
                    amount
                )
                VALUES (
                    :businessDate,
                    :sourceName,
                    :normalizedOrderId,
                    :amount
                )
                ON CONFLICT (
                    business_date,
                    source_name,
                    order_id_norm
                ) DO NOTHING
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("businessDate", item.businessDate())
                            .addValue("sourceName", item.sourceName())
                            .addValue("normalizedOrderId",
                                    item.normalizedOrderId())
                            .addValue("amount", item.amount()))
            .assertUpdates(false)
            .build();
}
```

`ON CONFLICT DO NOTHING` của PostgreSQL làm thao tác chèn trở thành một lựa chọn **atomic theo unique constraint**: bản ghi đầu tiên được lưu, các thao tác chèn cùng key không thêm bản ghi mới. Khi nhiều worker cạnh tranh, constraint trong database là nơi quyết định.

Ở writer, `assertUpdates(false)` cho phép trường hợp lệnh chèn không ảnh hưởng dòng nào vì duplicate. Nếu bật `assertUpdates(true)`, writer có thể coi update count bằng 0 là lỗi, trái với chủ đích “duplicate thì bỏ qua”.

**Giới hạn rất quan trọng:** Cấu hình trên triển khai chính sách **first committed row wins** tại storage. Nó không kiểm tra hai payload cùng key có số tiền khác nhau hay không. Nếu có thể có conflicting duplicate, cần thiết kế lưu dữ liệu thô, so payload và áp dụng một conflict policy rõ ràng trước khi lựa chọn item thắng.

### 7.7. Step cấu hình chunk và transaction

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step dedupStageStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> rawOrderReader,
        ItemProcessor<RawOrder, CleanOrder> normalizedOrderProcessor,
        ItemWriter<CleanOrder> stagingOrderWriter) {

    return new StepBuilder("dedupStageStep", repository)
            .<RawOrder, CleanOrder>chunk(200, transactionManager)
            .reader(rawOrderReader)
            .processor(normalizedOrderProcessor)
            .writer(stagingOrderWriter)
            .build();
}
```

`chunk(200, ...)` là commit interval ví dụ, không phải giới hạn duplicate. Điều quan trọng là writer và transaction manager quản lý **cùng database transaction** cho bảng staging. Nếu code mở connection ngoài transaction và tự commit từng item, rollback/restart sẽ khác.

Nếu job có flow nhiều step, tạo `Job` với `JobBuilder` và đặt `dedupStageStep` vào luồng. Các ví dụ này dùng kiểu builder của **Spring Batch 5.x**.

### 7.8. Số bản ghi ghi ra thực tế

Với file ví dụ có ba dòng cùng ý nghĩa:

```text
PARTNER_A, O-101 ,120000
PARTNER_A,O-102,50000
PARTNER_A,o-101,120000
```

Processor có thể trả về **3 `CleanOrder`**; writer được gọi với ba item, nhưng unique constraint làm bảng staging chỉ có **2 dòng**.

Vì vậy:

- `StepExecution.readCount` có thể là `3`.
- `StepExecution.writeCount` có thể là `3` (writer đã nhận và xử lý ba item theo thống kê Batch).
- `StepExecution.filterCount` là `0` (processor không trả `null`).
- `StepExecution.skipCount` là `0` (không có exception được skip).
- **Số dòng thực sự được insert** là `2`.

Không được dùng `writeCount` rồi kết luận ba bản ghi đã tồn tại trong bảng. Để báo cáo duplicate chính xác, cần dữ liệu từ outbox/audit/staging hoặc đếm theo policy trong một quy trình đối soát phù hợp.

## 8. Khi cần báo cáo bản ghi trùng: lưu raw staging trước

`ON CONFLICT DO NOTHING` giúp ghi idempotent, nhưng nếu yêu cầu là **đếm, phân loại và giải thích mọi duplicate**, chỉ lưu một bản ghi sau conflict không đủ thông tin.

Có thể chia ingestion thành hai bước:

```text
Step 1: nhận nguyên trạng từng dòng vào raw staging
        (kèm file ID, line number, payload, event time)
    |
    v
Step 2: chuẩn hóa key và phân nhóm duplicate
    |
    +-- bản duy nhất      --> accepted
    +-- bản trùng y hệt  --> duplicate audit
    +-- bản trùng xung đột --> quarantine/review
    |
    v
Step 3: apply dữ liệu được chấp nhận vào bảng nghiệp vụ
```

### 8.1. Bảng lưu mọi record đầu vào

Ví dụ PostgreSQL:

```sql
CREATE TABLE raw_order_import (
    ingest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_id VARCHAR(128) NOT NULL,
    business_date DATE NOT NULL,
    source_name VARCHAR(64) NOT NULL,
    order_id_norm VARCHAR(128) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    source_line_no BIGINT NOT NULL,
    CONSTRAINT uq_raw_source_line
        UNIQUE (import_id, source_line_no)
);
```

Khóa `(import_id, source_line_no)` chống chèn lặp **chính cùng một dòng của cùng file/import** nếu job retry/restart. `import_id` phải ổn định khi restart, ví dụ file checksum hoặc ID từ hệ thống nhận file, không sinh tùy tiện mỗi lần chạy.

Bảng lưu đầy đủ raw rows cho phép tính chính xác số duplicate và giữ bằng chứng khi hai record cùng business key nhưng khác amount.

### 8.2. Tìm nhóm trùng bằng SQL

```sql
SELECT
    business_date,
    source_name,
    order_id_norm,
    COUNT(*) AS occurrence_count,
    COUNT(DISTINCT amount) AS distinct_amount_count
FROM raw_order_import
WHERE import_id = :importId
GROUP BY
    business_date,
    source_name,
    order_id_norm
HAVING COUNT(*) > 1
ORDER BY occurrence_count DESC, source_name, order_id_norm;
```

Nếu `distinct_amount_count=1`, các bản ghi giống nhau ít nhất ở trường `amount`; đó **chưa chắc** là exact duplicate nếu payload còn nhiều trường khác. Muốn đánh giá exact, cần so toàn bộ trường nghiệp vụ có ý nghĩa hoặc so hash từ biểu diễn canonical đã xác định.

Nếu `distinct_amount_count>1`, nhóm có xung đột về số tiền và cần chính sách xử lý riêng.

### 8.3. Chọn bản thắng theo quy tắc deterministic

Ví dụ nghiệp vụ yêu cầu giữ bản có `event_time` mới nhất, sau đó ưu tiên dòng nguồn có `source_line_no` lớn hơn; nếu vẫn hòa, dùng `ingest_id` ổn định.

```sql
WITH ranked AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                business_date, source_name, order_id_norm
            ORDER BY
                event_time DESC,
                source_line_no DESC,
                ingest_id DESC
        ) AS rn
    FROM raw_order_import r
    WHERE import_id = :importId
)
SELECT
    business_date,
    source_name,
    order_id_norm,
    amount,
    event_time
FROM ranked
WHERE rn = 1;
```

Đây là ví dụ **last by event-time wins**, không mặc định áp dụng cho mọi dữ liệu. Nếu `event_time` từ nguồn không đáng tin hoặc nếu file thay đổi thứ tự, ưu tiên cần được thay theo metadata nghiệp vụ phù hợp. `ROW_NUMBER()` chỉ đảm bảo lựa chọn xác định khi `ORDER BY` có tie-breaker ổn định.

Đặc biệt, không áp dụng query “lấy bản mới nhất” trên một nhóm dữ liệu đã thiếu record vì trước đó writer dùng `DO NOTHING` bỏ các bản khác.

## 9. Phân biệt xử lý duplicate với các counter Spring Batch

Spring Batch có sẵn bộ đếm read/write/filter/skip, nhưng **không có một counter chuẩn “duplicateCount” áp dụng mọi chính sách nghiệp vụ**.

| Hành vi | `readCount` | `filterCount` | `skipCount` | Số dòng DB |
|---|---|---|---|---|
| Processor nhận item và trả đối tượng | Tăng | Không tăng | Không tăng | Tùy writer |
| Processor nhận item rồi trả `null` vì trùng | Tăng | Tăng | Không tăng | Không ghi item đó |
| Processor ném lỗi được phép skip | Tăng khi read thành công | Không nhất thiết tăng | Tăng ở process skip | Không ghi item bị skip |
| Writer `ON CONFLICT DO NOTHING` | Tăng khi đọc thành công | Không tăng | Không tăng | Có thể không tăng |
| Writer ném unique constraint exception và step fail | Tăng theo số item đã đọc | Không nhất thiết | Không tăng nếu không skip | Chunk có thể rollback |

Do đó, dashboard nên có **business metric riêng**:

```text
inputRecords      = 100000
normalizedValid   = 99900
duplicateExact    = 50
duplicateConflict = 20
invalidKey        = 30
acceptedUnique    = 99900 - 50 - 20 = 99830
```

Đây là số minh họa, với giả định từng item chỉ thuộc một nhóm loại trừ nhau. Nếu hệ thống chọn một bản thắng từ mỗi nhóm xung đột, công thức accepted phải phản ánh số item thắng và số item bị loại thực tế.

**Một tỷ lệ duplicate hữu ích** là:

```text
duplicateRate = duplicateOccurrences / totalEligibleInputRows
```

Cần định nghĩa rõ **mẫu số** và “occurrence”: một nhóm có năm dòng giống nhau tính là **bốn bản thừa** hay **một nhóm duplicate**? Hai chỉ số khác nhau và nên đặt tên tương ứng.

## 10. Idempotency khi retry, rollback và restart

Deduplication và idempotency có liên quan nhưng không hoàn toàn giống nhau:

- **Duplicate detection** hỏi: “Bản ghi này có trùng với bản khác theo quy tắc không?”
- **Idempotency** hỏi: “Nếu cùng thao tác được thực hiện lại, trạng thái cuối có thay đổi ngoài ý muốn không?”

Với Spring Batch, idempotency đặc biệt quan trọng do chunk có thể rollback, job có thể retry hoặc người vận hành restart.

### 10.1. Duplicate trong cùng chunk

Giả sử input có hai `O-101` và chunk size 100. Nếu writer chèn cả hai, unique constraint và `ON CONFLICT DO NOTHING` đảm bảo chỉ một dòng xuất hiện trong database. Hành vi này còn phụ thuộc chính sách xử lý payload trùng đã chọn.

### 10.2. Duplicate giữa các chunk

`O-101` xuất hiện ở chunk 1 và chunk 20. Vì cả hai cập nhật cùng một bảng có unique constraint, lần sau sẽ bị database xử lý theo conflict policy. Không cần giữ mọi key từ đầu job trong heap JVM.

### 10.3. Rollback một chunk

```text
Chunk 1: O-101, O-102 -> COMMIT
Chunk 2: O-103, O-104 -> writer lỗi -> ROLLBACK
Retry chunk 2:
   O-103, O-104 -> thử lại -> COMMIT
```

Khi writer sử dụng cùng transaction do Spring Batch quản lý, insert của chunk 2 đã rollback không còn được xem là đã commit. Retry có thể chèn lại và tiến đến trạng thái đúng. Với processor chứa `HashSet` không transaction-aware, kết quả lại có thể khác.

### 10.4. Restart execution mới

Sau một lần `JobExecution` thất bại, restart tạo một `JobExecution` khác cho cùng `JobInstance`. Reader hỗ trợ `ItemStream` có thể khôi phục checkpoint, nhưng một số item vẫn có thể được đọc lại tùy thời điểm commit và recovery. Unique constraint theo business key giúp writer chấp nhận phát lại không làm nhân đôi dữ liệu.

**Đừng dùng `jobExecutionId` làm key dedup nghiệp vụ** nếu muốn chống trùng qua restart: execution ID sẽ thay đổi. Dùng khóa nguồn hoặc business key ổn định tương ứng với điều kiện cần bảo vệ.

### 10.5. Side effect ngoài database

Giả sử khi ghi đơn, writer còn gọi HTTP gửi SMS. Transaction của database rollback **không hoàn tác SMS đã gửi**. Dù unique constraint ngăn đơn hàng trùng, người dùng vẫn có thể nhận hai SMS khi retry.

Thiết kế phù hợp hơn:

```text
Batch transaction:
  insert/update đơn hàng
  insert outbox event có business key unique
  COMMIT
     |
     v
Outbox publisher
     |
     v
Consumer idempotent xử lý event
```

Outbox và consumer idempotency cần được thiết kế riêng; **không có bảo đảm exactly-once trên hai hệ thống độc lập chỉ vì dùng Spring Batch transaction**. Với sự kiện giao lại, consumer kiểm tra một khóa bền vững trước khi áp dụng tác động nghiệp vụ.

## 11. Chạy song song, partitioning và duplicate race condition

Khi batch được tăng concurrency, hai worker có thể gặp cùng bản ghi ở cùng thời điểm:

```text
Worker A                       Worker B
--------                       --------
check key O-101: chưa có       check key O-101: chưa có
       |                              |
       +---------- insert ------------+
                      |
              database UNIQUE
                      |
             chỉ một insert thắng
```

Kiểu logic **“SELECT kiểm tra tồn tại rồi INSERT”** không atomic: cả hai worker đều có thể thấy “chưa có”. Nếu không có unique constraint, hai bản ghi có thể được ghi vào bảng.

**Giải pháp:** Dùng unique constraint và một thao tác ghi atomic của database phù hợp; ví dụ PostgreSQL `INSERT ... ON CONFLICT`. Khi gặp duplicate, chọn xử lý `DO NOTHING`, `DO UPDATE` hoặc lỗi + quarantine theo policy.

### 11.1. Partitioning theo key có giúp không?

Nếu các partition được chia bằng hàm hash ổn định của business key, cùng khóa thường đến cùng một worker. Điều này giảm cạnh tranh và giúp locality. Tuy nhiên, partitioning **không thay thế unique constraint** vì:

- Input có thể chứa trùng trong chính partition.
- Một partition có thể được retry/restart.
- Job khác có thể chạy song song.
- Quy tắc partition hoặc mapping có thể thay đổi theo số worker.
- Dữ liệu lịch sử đã nằm trong bảng trước khi job chạy.

### 11.2. Tính duy nhất theo cửa sổ thời gian

Một số hệ thống chỉ chống trùng trong 24 giờ, ví dụ event ID có thể được tái sử dụng sau thời hạn. Khi đó schema, TTL và partitioning phải phản ánh retention window.

Cần cẩn thận: nếu dọn key cũ trước khi một message phát lại đến, cùng event có thể được xử lý lần thứ hai. TTL phải được chọn theo khoảng redelivery/retry thực tế và hợp đồng nghiệp vụ, không chỉ theo kích thước cache mong muốn.

### 11.3. Cache/Bloom filter

Redis `SETNX` hoặc Bloom filter có thể giúp phát hiện sớm bản ghi đã thấy, nhưng:

- Redis có TTL và transaction khác database chính; lỗi giữa hai nơi có thể để lại state lệch.
- Bloom filter có **false positive**, nên có thể đánh dấu nhầm một bản ghi mới là trùng.
- Cache không phải nguồn dữ liệu duy nhất khi cần audit và chống trùng qua restart.
- Nếu dùng cache để giảm tải, vẫn nên có bước xác nhận từ storage authoritative trước khi loại vĩnh viễn một bản ghi quan trọng.

Đặc biệt với dữ liệu tài chính, không nên dùng xác suất Bloom filter làm điều kiện duy nhất để bỏ bản ghi hợp lệ.

## 12. Duplicate detection theo business entity và theo event

Hai mô hình phổ biến có cách chọn key khác nhau.

### 12.1. Snapshot hoặc master data

Ví dụ nhận hồ sơ khách hàng theo ngày. Cùng `customerId` trong file mới có thể là phiên bản cập nhật hợp lệ. Nếu bạn chọn key `customerId` và bỏ mọi bản sau, dữ liệu sẽ không cập nhật.

Có thể thiết kế:

- Khóa entity: `customerId`.
- Khóa version: `(customerId, sourceVersion)`.
- Chọn bản có `sourceVersion` lớn nhất hoặc cập nhật theo optimistic locking.
- Từ chối bản có version cũ hơn, nhưng có thể ghi audit.

### 12.2. Event log

Ví dụ một đơn hàng có ba sự kiện:

```text
event-001: OrderCreated(orderId=O-101)
event-002: PaymentConfirmed(orderId=O-101)
event-003: OrderShipped(orderId=O-101)
```

Ba sự kiện cùng `orderId` nhưng **không trùng**. Nếu broker phát lại `event-002`, phải dedup bằng **`eventId`**, không phải `orderId`.

Một bảng inbox event:

```sql
CREATE TABLE processed_inbox (
    source_system VARCHAR(80) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_system, event_id)
);
```

Trong cùng transaction với business update, ứng dụng kiểm tra/chèn inbox key và chỉ áp dụng event mới. Cách triển khai phải bảo đảm rằng “đánh dấu đã xử lý” và business effect có transaction semantics tương thích; nếu đánh dấu sớm trong một transaction khác, retry có thể bỏ mất event chưa được xử lý.

## 13. Duplicate gần đúng và data matching

Không phải dữ liệu nào cũng có exact ID. Trong CRM hoặc dữ liệu khách hàng, hai bản ghi có thể tương đồng:

```text
"Nguyen Van A", "090 123 4567"
"Nguyễn Văn A", "0901234567"
```

Đây là bài toán **record linkage / fuzzy matching**, khó hơn exact duplicate. Các phương pháp có thể gồm:

- Chuẩn hóa số điện thoại theo quốc gia.
- Chuẩn hóa địa chỉ và ký tự Unicode.
- Ghép nhiều trường với trọng số.
- Edit distance, Jaro–Winkler hoặc token similarity.
- Blocking theo một khóa thô để hạn chế số cặp cần so sánh.
- Tách thành nhóm tự động chấp nhận, tự động loại và cần người duyệt.

Nếu dùng threshold similarity, phải đo **false positive** (gộp nhầm hai người khác nhau) và **false negative** (không gộp hai bản thực sự trùng). Không nên sử dụng fuzzy score thay thế business event ID khi hệ thống đã có một định danh đáng tin cậy.

Đối với dữ liệu nhạy cảm, thiết kế matching cần bảo vệ quyền truy cập và tuân thủ chính sách lưu trữ; không log tràn lan tên, số điện thoại hoặc địa chỉ vào metric tags.

## 14. Kiểm thử duplicate detection bằng dữ liệu cố định

### 14.1. Unit test chuẩn hóa khóa

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class BusinessKeyNormalizerTest {

    @Test
    void normalizesWhitespaceAndCase() {
        assertEquals(
                "O-101",
                BusinessKeyNormalizer.normalizeRequired(" o-101 ")
        );
    }

    @Test
    void rejectsMissingOrBlankKey() {
        assertThrows(
                IllegalArgumentException.class,
                () -> BusinessKeyNormalizer.normalizeRequired(null)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> BusinessKeyNormalizer.normalizeRequired("  ")
        );
    }
}
```

Đây là unit test thuần Java; không cần tải Spring context hay database.

### 14.2. Unit test processor thuần hàm

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

class NormalizeOrderProcessorTest {

    @Test
    void sameLogicalKeyProducesSameCanonicalKey() throws Exception {
        NormalizeOrderProcessor processor =
                new NormalizeOrderProcessor(
                        LocalDate.of(2025, 5, 12));

        CleanOrder first = processor.process(new RawOrder(
                "PARTNER_A", " O-101 ", new BigDecimal("120000")));

        CleanOrder replay = processor.process(new RawOrder(
                "partner_a", "o-101", new BigDecimal("120000")));

        assertEquals(first.sourceName(), replay.sourceName());
        assertEquals(
                first.normalizedOrderId(),
                replay.normalizedOrderId());
        assertEquals(first.businessDate(), replay.businessDate());
    }
}
```

Test này xác nhận canonical key ổn định. Nó **chưa chứng minh item được dedup ở database**; để xác minh atomic uniqueness và transaction cần integration test.

### 14.3. Integration test với PostgreSQL

Vì ví dụ writer dùng PostgreSQL `ON CONFLICT`, test quan trọng nên chạy với **PostgreSQL test database** (có thể dùng Testcontainers), thay vì khẳng định H2 có semantics hoàn toàn tương đương.

Một kịch bản:

```text
Input:
  PARTNER_A, O-101 ,120000
  PARTNER_A,O-102,50000
  PARTNER_A,o-101,120000

Step:
  readCount   = 3
  filterCount = 0
  writeCount  = 3
  skipCount   = 0

DB after commit:
  2 rows in stage_orders
  PARTNER_A / O-101 / 120000
  PARTNER_A / O-102 / 50000
```

Test có thể dùng `spring-batch-test` và `JobLauncherTestUtils.launchJob(parameters)`. Ví dụ phần assertion khi đã cấu hình test context với job và database PostgreSQL:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class DedupJobAssertions {

    @Autowired
    JobLauncherTestUtils batchTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void shouldPersistOnlyUniqueCanonicalOrders() throws Exception {
        // Fixture chứa ba dòng của ví dụ và đã được tạo ở test setup.
        String inputFile = "/tmp/dedup-orders-fixture.csv";

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2025-05-12")
                .addString("inputFile", inputFile)
                .toJobParameters();

        JobExecution result = batchTestUtils.launchJob(parameters);
        StepExecution step = result.getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, result.getStatus());
        assertEquals(3L, step.getReadCount());
        assertEquals(3L, step.getWriteCount());
        assertEquals(0L, step.getFilterCount());

        Integer inserted = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM stage_orders
                WHERE business_date = ?
                """,
                Integer.class,
                LocalDate.of(2025, 5, 12));

        assertEquals(2, inserted);
    }
}
```

Đoạn trên là **khung assertion**, không phải test class độc lập có thể chạy khi chưa cấu hình Spring context, PostgreSQL datasource, schema và fixture. Trong test thực, tạo fixture bằng `@TempDir` rồi truyền đường dẫn thực, bật `@SpringBatchTest`/`@SpringBootTest` cho cấu hình job, và cô lập `JobRepository` để các lượt test không trùng identifying `JobParameters`.

Bổ sung các assertion kiểm tra **đúng giá trị amount/source/key**, thay vì chỉ kiểm tra count, để không bỏ sót trường hợp hai bản trùng key nhưng dữ liệu sai được giữ.

### 14.4. Test rollback và restart

Tạo writer lỗi ở cuối chunk, để database rollback. Sau đó cho writer thành công và chạy lại từ checkpoint. Kỳ vọng:

- Không thiếu order vì processor đã đánh dấu key trong bộ nhớ rồi không phục hồi.
- Không nhân đôi hàng trong database.
- Không gửi tác động ngoài hệ thống hai lần khi replay.
- `JobExecution` mới dùng cùng identifying business parameters khi restart.
- Với dữ liệu đầu vào bất biến, số unique record cuối cùng giống khi job chạy một mạch từ đầu.

Một test khác nên chạy **hai job đồng thời** thử chèn cùng key để xác nhận unique constraint bảo vệ cạnh tranh. Không nên chỉ kiểm tra `HashSet` với hai thread rồi kết luận chống trùng đã an toàn.

### 14.5. Test conflicting duplicate

Input:

```csv
source,order_id,amount
PARTNER_A,O-101,120000
PARTNER_A,O-101,900000
```

Nếu chính sách là **reject conflicting duplicate**, test phải xác nhận cả hai bản không được tự động chấp nhận như dữ liệu bình thường; audit/quarantine có đủ ID nguồn, payload đã được bảo vệ, và lý do xung đột. Nếu chính sách là **highest version wins**, fixture cần có trường version và thứ tự rõ ràng.

## 15. Monitoring: đếm duplicate và phát hiện bất thường

Tỷ lệ duplicate là chỉ số chất lượng dữ liệu quan trọng vì có thể phản ánh:

- Nguồn upstream gửi lại file.
- Cấu hình scheduler chạy chồng lấp.
- API có vấn đề pagination hoặc event broker redelivery.
- Sai khóa dedup sau khi schema thay đổi.
- Cơ chế retry/restart gây phát lại không mong muốn.
- Thay đổi quy tắc chuẩn hóa khóa gây gộp nhầm.

Một dashboard có thể hiển thị:

| Metric | Ví dụ | Mục tiêu |
|---|---:|---|
| `input_rows_total` | 100.000 | Dữ liệu nhập vào |
| `unique_keys_total` | 99.820 | Số khóa nghiệp vụ phân biệt |
| `duplicate_extra_rows_total` | 180 | Số lần xuất hiện thừa |
| `conflicting_keys_total` | 7 | Số nhóm có payload xung đột |
| `invalid_keys_total` | 15 | Dữ liệu không có khóa hợp lệ |
| `duplicate_rate` | 0,18% | Theo dõi biến động |
| `dedup_stage_duration_seconds` | Theo execution | Hiệu năng bước dedup |

Đây là số minh họa. Một nhóm năm bản giống nhau tạo **bốn extra rows** nhưng chỉ **một nhóm có duplicate**.

**Không đặt từng `orderId`, `eventId`, `jobExecutionId` hoặc nội dung payload làm label Prometheus.** Các label biến đổi theo từng item gây high cardinality và có thể lộ dữ liệu. Nên dùng label ít biến động như `jobName`, `sourceSystem`, `duplicateType` và đưa ID chi tiết vào log/audit có quyền truy cập phù hợp.

### 15.1. Ngưỡng cảnh báo theo nguồn

Không dùng ngưỡng chung cho mọi loại dữ liệu. Một nguồn message at-least-once có thể có một tỷ lệ phát lại bình thường, trong khi dữ liệu giao dịch ngân hàng trong một file chốt ngày có thể yêu cầu không có conflicting duplicate nào.

Ví dụ một chính sách vận hành:

```text
duplicateExactRate > 2%     -> cảnh báo kiểm tra upstream
conflictingDuplicateCount > 0 -> chặn công bố dữ liệu
invalidKeyCount > 0         -> chuyển quarantine
```

Các ngưỡng là ví dụ, cần lựa chọn theo SLA/chất lượng dữ liệu thực tế. Cũng nên theo dõi **thay đổi đột ngột so với baseline** của từng nguồn, vì một tỷ lệ “bình thường” trong hôm nay có thể là dấu hiệu upstream lỗi nếu hôm qua gần như không có duplicate.

## 16. Hiệu năng và dung lượng của duplicate detection

Giải pháp exact dedup có nhiều lựa chọn, không có một cách tối ưu cho mọi dữ liệu.

| Phương án | Bộ nhớ Java | Khả năng restart | Concurrency | Ưu/nhược điểm chính |
|---|---|---|---|---|
| `HashSet` trong processor | Tăng theo số key | Kém nếu không có cơ chế state bền vững | Giới hạn trong JVM | Nhanh cho dữ liệu nhỏ; dễ sai khi rollback |
| Sort + so sánh bản kế tiếp | Nhỏ nếu đầu vào đã sort | Phụ thuộc checkpoint, thứ tự nguồn | Cần partition có thứ tự | Hiệu quả khi nguồn lớn và sort xác định |
| SQL `GROUP BY`/`ROW_NUMBER()` trên raw staging | Chủ yếu ở DB | Tốt nếu staging bền vững | DB xử lý | Dễ audit, có thể tốn sort/index |
| DB `UNIQUE` + atomic insert | Nhỏ ở JVM | Tốt với retry/restart | Tốt nếu DB đúng cấu hình | Bảo đảm duy nhất ở storage; cần policy conflict |
| External dedup cache | Tùy cache | Theo retention/durability | Phụ thuộc hạ tầng | Giảm tải nhanh; cần đồng bộ với DB |
| Bloom filter | Nhỏ | Phụ thuộc lưu trạng thái | Có thể phân tán | Có false positive, không phù hợp làm kiểm chứng cuối |

### 16.1. Index và độ lớn khóa

Unique index giúp chống trùng nhưng cũng có chi phí ghi và lưu trữ. Với hàng chục triệu bản ghi, cần đánh giá:

- Kích thước cột `sourceName`, `orderId` và composite key.
- Phân vùng dữ liệu theo ngày nếu nghiệp vụ thật sự có key theo ngày.
- Tỷ lệ insert mới so với insert bị conflict.
- Số writer concurrent và lock contention.
- Batch size/chunk size và transaction log/WAL.
- Cơ chế dọn dữ liệu staging sau thời gian retention.

Nếu business key rất dài, có thể cân nhắc một key digest để tối ưu lưu trữ, nhưng **hash có xác suất collision**. Với hệ thống cần tuyệt đối phân biệt ID, giữ hoặc so sánh giá trị gốc ở bước xác nhận thay vì coi một digest rút gọn là chứng cứ duy nhất.

### 16.2. Đếm toàn bộ key bằng SELECT trước khi INSERT

Một thiết kế thường thấy:

```text
SELECT count(*) WHERE key = ?
nếu 0:
    INSERT ...
```

Điều này vừa tạo thêm truy vấn cho mỗi item, vừa có race condition khi chạy song song. Nếu database hỗ trợ unique constraint và atomic upsert, nên ưu tiên cơ chế đó. Dùng `SELECT` khi cần lấy payload cũ để xử lý xung đột, nhưng quyết định cuối vẫn phải an toàn trước thay đổi đồng thời.

## 17. Quy trình thiết kế data quality cho duplicate

Khi xây một pipeline ingest mới, có thể đi theo trình tự:

1. **Xác định định danh nguồn và event/business semantics.** Cùng order ID có thể là duplicate hay phiên bản update?
2. **Chốt canonical key.** Nêu rõ whitespace, case, Unicode, nullable và namespace.
3. **Quy định phạm vi.** Trùng trong file, trong business date, qua nhiều file hay toàn lịch sử?
4. **Quy định chính sách.** First/last/version/merge/reject; xung đột payload xử lý thế nào?
5. **Lưu lineage.** File ID, source line, source event ID, business date và version đủ để trace.
6. **Chọn nơi bảo đảm cuối.** Dùng unique constraint hoặc storage có atomic conditional write.
7. **Thiết kế retry/restart.** Kiểm tra chunk rollback, checkpoint và side effect ngoài transaction.
8. **Định nghĩa metrics.** Phân biệt extra rows, duplicate groups, conflicts và accepted unique.
9. **Kiểm thử concurrency.** Hai worker và hai execution ghi cùng key.
10. **Thiết kế recovery.** Có thể replay import, reclassify xung đột và xuất báo cáo audit mà không làm mất dữ liệu gốc.

Các quyết định này nên được ghi thành một hợp đồng dữ liệu. Một thay đổi tưởng như nhỏ ở hàm normalize có thể khiến hàng triệu key khác nhau được gộp, nên cần quản lý phiên bản quy tắc nếu dữ liệu lịch sử có thể bị ảnh hưởng.

## 18. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Phương án phù hợp hơn |
|---|---|---|
| Coi cùng số tiền là cùng giao dịch | Bỏ mất giao dịch hợp lệ | Dùng source transaction ID và scope đúng |
| Dùng `HashSet` mutable trong processor để chống trùng production | Không rollback, mất state khi restart | Unique constraint/atomic store |
| Dùng `ConcurrentHashMap` rồi nghĩ đã an toàn qua nhiều JVM | Worker khác không chia sẻ bộ nhớ | Storage chung có transaction |
| Dùng `jobExecutionId` làm khóa chống trùng qua restart | Mỗi restart có ID mới | Business/event key ổn định |
| Dùng `ON CONFLICT DO NOTHING` cho mọi xung đột | Che update hợp lệ và sai lệch amount | Tách exact duplicate và conflict |
| Chọn “bản cuối” khi không có thứ tự ổn định | Kết quả phụ thuộc schedule/parallelism | Version/event time + tie-breaker |
| Dùng `skip(Exception.class)` để xử lý duplicate | Che lỗi database và lỗi code | Filter có kiểm soát hoặc conflict SQL |
| Coi `writeCount` là số dòng DB mới chèn | Báo cáo sai khi INSERT bị conflict | Query số dòng thực hoặc audit riêng |
| Dùng `SELECT` rồi `INSERT` mà không có unique index | Race condition giữa worker | Atomic insert/upsert + unique constraint |
| Không giữ raw data trước khi dedup | Không giải thích được conflict | Raw staging/quarantine có lineage |
| Chỉ dùng Bloom filter để quyết định bỏ dữ liệu | False positive làm mất bản ghi | Xác nhận bằng authoritative store |
| Cache key có TTL quá ngắn | Event phát lại sau TTL được xử lý trùng | Retention theo hợp đồng redelivery |
| Thay dữ liệu file giữa restart | Checkpoint không còn trỏ đúng record | Immutable file/version/checksum |
| Test chỉ trên một thread | Không phát hiện race condition | Integration test concurrency |
| Thiếu metric conflict | Job “thành công” nhưng dữ liệu sai | Báo cáo data-quality outcomes |
| Log toàn bộ payload khách hàng | Lộ dữ liệu và log quá lớn | ID/lineage an toàn, quarantine có kiểm soát |

## 19. Bài tập thực hành: nhập đơn hàng từ nhiều nguồn

Thiết kế job `importPartnerOrders` nhập file CSV mỗi ngày từ hai đối tác. Dữ liệu có các trường:

```csv
source,order_id,amount,event_id,event_time,source_version
PARTNER_A,O-101,120000,E-001,2025-05-12T00:00:00Z,1
PARTNER_A,o-101,120000,E-001,2025-05-12T00:00:00Z,1
PARTNER_A,O-101,130000,E-008,2025-05-13T00:00:00Z,2
PARTNER_B,O-101,30000,E-200,2025-05-12T00:00:00Z,1
```

Yêu cầu:

1. Định nghĩa khóa **event duplicate** `(source, event_id)` và khóa **entity** `(source, normalized_order_id)`. Giải thích vì sao không nên dùng cùng một khóa cho cả hai.
2. Viết hàm normalize ID dựa trên `strip()` và `Locale.ROOT`, đồng thời test khi input rỗng hoặc thiếu.
3. Tạo bảng raw staging lưu toàn bộ input cùng file ID và line number, chống chèn lại cùng dòng khi restart.
4. Tạo bảng event inbox với unique constraint theo `(source, event_id)`.
5. Thiết kế rule: nếu cùng event ID và payload giống nhau thì coi là replay; nếu cùng event ID nhưng payload khác nhau thì quarantine.
6. Thiết kế rule cập nhật đơn hàng: version lớn hơn được áp dụng, version bằng nhau nhưng payload khác nhau là conflict.
7. Dùng `JdbcBatchItemWriter` hoặc JDBC writer tùy biến để xử lý atomic insert/upsert với transaction của step.
8. Tạo một chunk có bản ghi trùng rồi cố ý rollback. Chứng minh retry không làm mất item hợp lệ.
9. Restart từ execution thất bại với đúng `JobParameters`. Chứng minh không sinh thêm event inbox hoặc nhân đôi đơn hàng.
10. Chạy hai worker đồng thời cùng chèn `E-001`. Kiểm tra unique constraint chống trùng.
11. Viết integration test bằng PostgreSQL với fixture cố định; assert dữ liệu cuối, bản ghi conflict, số duplicate và `StepExecution` counters.
12. Thiết kế dashboard hiển thị input rows, unique events, replay count, conflict count, batch duration và lỗi theo đối tác.

**Câu hỏi ôn tập:** Một job có `readCount=1000`, `writeCount=1000`, `filterCount=0` và không có skip. Writer dùng PostgreSQL `INSERT ... ON CONFLICT DO NOTHING`. Có thể kết luận bảng đã có thêm 1000 dòng mới không?

**Trả lời:** **Không.** `writeCount` đếm item mà Spring Batch đưa cho writer theo cơ chế của framework, trong khi lệnh `DO NOTHING` có thể không chèn dòng mới cho những key đã tồn tại. Muốn biết số dòng thực sự được chèn, cần đọc kết quả cập nhật đáng tin cậy, dùng bảng audit/outbox, hoặc đối soát dữ liệu trong database theo hợp đồng đã xác định.

## 20. Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chu kỳ `read/process/write`, chunk và transaction.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): `ItemProcessor` trả `null` để filter item.
- [Spring Batch Reference — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): cách sử dụng `JdbcBatchItemWriter` và các reader JDBC.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault tolerance và retry.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): phân biệt exception được skip với item được filter.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `ExecutionContext`, checkpoint và restart.
- [Spring Framework JDBC — Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html#jdbc-batch): giao tiếp database theo batch.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): semantics `ON CONFLICT DO NOTHING` và `DO UPDATE`.
- [PostgreSQL — Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS): bảo đảm tính duy nhất trong database.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): `ROW_NUMBER()` và ranking để chọn bản ghi theo thứ tự xác định.
