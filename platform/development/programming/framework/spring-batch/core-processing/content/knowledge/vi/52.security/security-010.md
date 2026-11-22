# Validate input tránh injection trong Spring Batch

## 1. Vì sao batch processing vẫn có nguy cơ injection?

Spring Batch thường chạy phía máy chủ, không có biểu mẫu web và nhiều khi nhận dữ liệu từ hệ thống “nội bộ”. Điều đó **không có nghĩa đầu vào đáng tin cậy**. Một job có thể đọc file CSV do đối tác gửi, bảng staging do hệ thống khác ghi, payload từ API, message queue, tên file qua `JobParameters` hoặc cấu hình do người vận hành truyền vào.

Nếu dữ liệu đầu vào được ghép trực tiếp vào **câu SQL, đường dẫn file, biểu thức, câu lệnh hệ điều hành hoặc nội dung xuất ra ứng dụng khác**, một giá trị vốn chỉ là dữ liệu có thể bị diễn giải thành **chỉ thị điều khiển**.

Ví dụ:

```text
Scheduler / REST / Operator
             |
             v
      JobParameters -------------+
             |                  |
             v                  v
File / API / Queue          Dynamic config
             |                  |
             v                  v
         ItemReader         SQL / Path / URL
             |
             v
        ItemProcessor
             |
             v
         ItemWriter
             |
             v
     Database / CSV / API
```

Một lỗi trong bước tạo câu SQL ở reader hoặc writer có thể ảnh hưởng hàng triệu bản ghi. Một tham số `inputFile` không được kiểm soát có thể khiến job đọc file ngoài thư mục nhập liệu. Một tên trường được ghép vào `ORDER BY` có thể khiến query chạy theo cấu trúc không dự kiến. Một giá trị bắt đầu bằng dấu `=` trong file CSV xuất ra có thể bị ứng dụng bảng tính hiểu như công thức.

**Validate input tránh injection** trong Spring Batch có hai mục tiêu riêng nhưng bổ trợ nhau:

1. **Kiểm tra hợp đồng dữ liệu**: kiểu, định dạng, độ dài, phạm vi, giá trị hợp lệ và quyền sử dụng.
2. **Dùng API an toàn tại điểm dữ liệu đi vào một ngôn ngữ khác**: bind parameter cho SQL, allowlist identifier, kiểm soát filesystem path, tránh shell, mã hóa/định dạng an toàn khi xuất.

Validation **không thay thế** prepared statements. Prepared statements **không thay thế** kiểm tra nghiệp vụ. Cần cả hai.

### Ví dụ đầu vào không an toàn

Giả sử `orderId` lấy từ CSV:

```text
O-101
O'BRIEN
x' OR '1'='1
```

Một `orderId` chứa dấu nháy đơn có thể hoàn toàn hợp lệ theo hợp đồng đối tác. Nếu chỉ “xóa mọi dấu nháy” để tránh SQL injection, dữ liệu bị sửa sai mà vẫn không giải quyết đầy đủ nguy cơ ở những chỗ ghép chuỗi khác. Cách đúng là **bind nguyên giá trị như một tham số SQL**, đồng thời validate định dạng nếu nghiệp vụ có quy tắc mã đơn rõ ràng.

## 2. Xác định ranh giới tin cậy trong Spring Batch

| Nguồn vào | Ví dụ | Nguy cơ cần lưu ý | Cơ chế kiểm soát |
|---|---|---|---|
| `JobParameters` | `businessDate`, `inputKey`, `tenant` | Path traversal, chọn sai tập dữ liệu, đưa tên bảng/cột động vào SQL | Validate trước khi job chạy, allowlist |
| CSV/TSV | `orderId`, `amount`, ghi chú tự do | SQL injection nếu ghép query, dữ liệu quá dài, CSV formula injection khi xuất | Parse, validate schema, bind SQL, escape theo output context |
| Database staging | Giá trị do hệ thống upstream ghi | Second-order injection khi đọc rồi dùng để tạo SQL động | Xem như dữ liệu không tin cậy, bind lại |
| API / message | `sourceUrl`, `eventId`, filter | SSRF, replay, injection vào query hoặc shell | Đích kết nối cố định, schema validation, idempotency |
| XML / JSON | Trường nested, số lượng phần tử, entity | XML external entity (XXE), parser/resource exhaustion | Parser an toàn, giới hạn độ sâu/kích thước |
| File path / object key | `../../...`, tên file giống nhau | Đọc/ghi ngoài vùng cho phép, symlink escape | Chỉ nhận logical key, canonical path và quyền truy cập tối thiểu |
| Tên cột/bảng/thứ tự | `sortBy=createdAt` | Không thể bind SQL identifier như value | Mapping allowlist tới hằng số trong code |
| Tham số cho OS process | Tên file/đối số tùy ý | Shell/argument injection | Tránh shell, cố định executable/options, validate argument |

**Nguyên tắc trust boundary:** File nằm trong bucket của công ty, bản ghi đã đi qua một queue được xác thực hoặc tham số đến từ scheduler vẫn có thể bị sai, lỗi đồng bộ hoặc chứa dữ liệu độc hại. Mọi đầu vào vượt vào bước thực thi đặc quyền cao hơn đều cần được kiểm soát phù hợp.

## 3. Quy trình kiểm soát: parse → validate → normalize → bind → encode

Một pipeline an toàn có thể hình dung như sau:

```text
Raw input
   |
   v
Parse đúng định dạng, giới hạn kích thước
   |
   v
Validate trường bắt buộc, kiểu, độ dài, domain
   |
   v
Normalize những trường được phép chuẩn hóa
   |
   v
Business rule / authorization / idempotency
   |
   v
Bind qua API tham số hóa hoặc chọn cấu trúc từ allowlist
   |
   v
Encode đúng ngữ cảnh đầu ra, nếu xuất sang format khác
```

Mỗi bước có mục đích khác nhau:

- **Parse**: chuyển dữ liệu thô sang kiểu có cấu trúc; lỗi cú pháp phải được nhận diện.
- **Validate**: từ chối giá trị không đáp ứng hợp đồng, chẳng hạn `amount=-99` hay `businessDate` sai dạng.
- **Normalize**: chuẩn hóa mã khi nghiệp vụ cho phép, ví dụ bỏ khoảng trắng đầu/cuối của mã khách hàng.
- **Authorize**: xác định một job/nguồn/tenant có được phép truy cập tập dữ liệu đó không.
- **Bind**: truyền giá trị vào SQL bằng placeholder thay vì nối chuỗi.
- **Encode output**: nếu đưa dữ liệu sang HTML, CSV mở bằng spreadsheet hoặc định dạng khác, xử lý đúng ngữ cảnh *đích*.

Không nên dùng một hàm “sanitize tất cả ký tự nguy hiểm” áp dụng chung cho SQL, path, HTML và CSV. Mỗi ngôn ngữ đầu ra có luật diễn giải riêng.

## 4. Validate `JobParameters` trước khi thực thi job

`JobParameters` là điểm vào đặc biệt nguy hiểm nếu một job hỗ trợ tham số kiểu `inputFile`, `schema`, `table`, `where` hoặc `command`. Các giá trị này có thể do REST endpoint, scheduler, command line hoặc công cụ vận hành đưa vào.

Giả sử job `importPayments` chỉ chấp nhận:

- `businessDate`: ngày ISO-8601, ví dụ `2025-05-12`.
- `inputKey`: **tên file đơn**, chỉ chữ Latin, số, gạch dưới/gạch ngang, đuôi `.csv`; không cho phép đường dẫn.
- `sourceSystem`: một trong `PARTNER_A` và `PARTNER_B`.

### 4.1. Validator tập trung cho tham số job

Spring Batch có giao diện `JobParametersValidator` để kiểm tra tham số trước khi job bắt đầu xử lý.

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class ImportJobParametersValidator
        implements JobParametersValidator {

    private static final Pattern INPUT_KEY = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9_-]{0,79}\\.csv"
    );

    private static final Set<String> ALLOWED_SOURCES =
            Set.of("PARTNER_A", "PARTNER_B");

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters == null) {
            throw new JobParametersInvalidException(
                    "Job parameters are required");
        }

        String businessDate = parameters.getString("businessDate");
        String inputKey = parameters.getString("inputKey");
        String sourceSystem = parameters.getString("sourceSystem");

        if (businessDate == null) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must be an ISO date");
        }

        if (inputKey == null
                || !INPUT_KEY.matcher(inputKey).matches()) {
            throw new JobParametersInvalidException(
                    "inputKey must be a simple .csv file name");
        }

        if (!ALLOWED_SOURCES.contains(sourceSystem)) {
            throw new JobParametersInvalidException(
                    "sourceSystem is not allowed");
        }
    }
}
```

**Điểm đáng chú ý:** `matcher(...).matches()` so khớp **toàn bộ** giá trị. Nếu chỉ dùng tìm một đoạn hợp lệ ở giữa chuỗi, một đường dẫn có phần cuối hợp lệ vẫn có thể lọt qua.

Pattern trên chỉ là hợp đồng ví dụ; nó **không hỗ trợ Unicode trong tên file** và giới hạn tên 80 ký tự trước `.csv`. Những lựa chọn này phải khớp nhu cầu thực tế. Nếu ứng dụng nhận object key có thư mục, nên thiết kế allowlist/canonicalization tương ứng thay vì nới lỏng một cách tùy tiện.

Không chỉ kiểm tra string ngày bằng regex `\d{4}-\d{2}-\d{2}`: chuỗi có hình thức giống ngày vẫn có thể là ngày không tồn tại. `LocalDate.parse(...)` kiểm tra cả tính hợp lệ của lịch.

### 4.2. Đăng ký validator khi xây job

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job importPaymentsJob(
        JobRepository repository,
        Step importPaymentsStep) {

    return new JobBuilder("importPaymentsJob", repository)
            .validator(new ImportJobParametersValidator())
            .start(importPaymentsStep)
            .build();
}
```

Khi tham số không hợp lệ, job bị từ chối ở bước validation thay vì để reader hoặc writer tiến hành các tác vụ có side effect. Lớp API khởi chạy job vẫn nên validate request và kiểm tra quyền truy cập trước khi gọi `JobLauncher`; validator ở job là một lớp bảo vệ bổ sung, **không thay thế authorization**.

### 4.3. Validate trước, không làm biến đổi định danh tùy tiện

`JobParameters` có thể là identifying parameters xác định `JobInstance`. Không tự thay ngày nghiệp vụ hoặc đổi tên file trong mỗi lần retry/restart bằng `LocalDate.now()` hay một chuỗi mới tùy ý: làm thế có thể khiến restart thực chất thành một job instance mới, đọc lại dữ liệu ngoài mong đợi.

Một thực hành tốt là chốt `businessDate`, `inputKey` và `sourceSystem` tại lúc launch; mọi lần restart dùng lại các tham số định danh phù hợp.

## 5. SQL injection: **luôn bind giá trị SQL**

Một điểm injection phổ biến nhất trong batch là reader xây query từ một trường CSV hoặc `JobParameters`.

### 5.1. Ví dụ sai: nối chuỗi vào query

```java
// KHÔNG DÙNG
String sql = "SELECT id, amount FROM payments "
        + "WHERE external_id = '" + externalId + "'";

jdbcTemplate.query(sql, rowMapper);
```

Nếu `externalId` chứa dấu nháy hoặc cú pháp SQL khác, giá trị này bị chèn vào **cấu trúc câu lệnh**. Hậu quả có thể là truy vấn lỗi hoặc thay đổi điều kiện lọc. Đừng nghĩ batch an toàn chỉ vì query được tạo bên phía server: nguồn tham số vẫn có thể không đáng tin.

### 5.2. Ví dụ đúng với `NamedParameterJdbcTemplate`

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public record PaymentLookup(
        long id,
        String externalId,
        BigDecimal amount
) {
}

public final class PaymentLookupRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public PaymentLookupRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<PaymentLookup> findByExternalId(String externalId) {
        String sql = """
                SELECT id, external_id, amount
                  FROM payments
                 WHERE external_id = :externalId
                """;

        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("externalId", externalId);

        return jdbc.query(
                sql,
                parameters,
                (rs, rowNum) -> new PaymentLookup(
                        rs.getLong("id"),
                        rs.getString("external_id"),
                        rs.getBigDecimal("amount"))
        );
    }
}
```

`:externalId` là placeholder cho **giá trị**, không phải đoạn SQL. Driver xử lý giá trị nhận vào như dữ liệu, kể cả khi nó chứa dấu nháy hoặc chuỗi trông giống điều kiện SQL.

Với `JdbcTemplate` thuần cũng có thể dùng dấu `?`:

```java
String sql = "UPDATE payments SET status = ? WHERE external_id = ?";

jdbcTemplate.update(sql, "VERIFIED", externalId);
```

**Không thay thế placeholder bằng xử lý chuỗi thủ công**, ví dụ `replace("'", "''")` hoặc xóa ký tự `;`. Escaping thủ công dễ thiếu trường hợp về encoding, ngữ cảnh SQL và driver. Dùng API parameter binding là biện pháp cốt lõi.

### 5.3. Giá trị hợp lệ có thể chứa ký tự đặc biệt

Ví dụ tên khách hàng `O'Brien` là dữ liệu hợp lệ. Prepared statements cho phép truyền chuỗi này như một value. Nếu validation nghiệp vụ cho phép dấu nháy, không cần xóa nó chỉ để tránh SQL injection.

Cần phân biệt một lần nữa:

- **Validation** quyết định tên/mã nào hợp lệ theo hợp đồng.
- **Parameter binding** ngăn giá trị làm thay đổi cấu trúc query.

### 5.4. Với JPA/JPQL cũng phải bind

```java
var query = entityManager.createQuery(
        """
        select p
          from PaymentEntity p
         where p.externalId = :externalId
        """,
        PaymentEntity.class
);

query.setParameter("externalId", externalId);
List<PaymentEntity> result = query.getResultList();
```

Đừng chuyển nguy cơ từ JDBC sang JPQL bằng cách nối `externalId` trực tiếp vào chuỗi query. Dù ứng dụng dùng ORM, nguyên tắc vẫn như nhau: **giá trị đầu vào phải là tham số**.

### 5.5. `LIKE` và wildcard

Binding chống SQL injection, nhưng chưa tự giải quyết yêu cầu nghiệp vụ của tìm kiếm `LIKE`. Giá trị `%` và `_` có ý nghĩa wildcard trong SQL `LIKE` trên nhiều database. Nếu người dùng muốn tìm *chuỗi literal*, phải escape wildcard theo database và định nghĩa `ESCAPE` phù hợp, sau đó **vẫn bind tham số**.

Đây là vấn đề **query semantics**, không nên đánh đồng với việc “prepared statement có thể bị SQL injection”.

## 6. Parameter binding không áp dụng cho tên bảng, cột và `ORDER BY`

Placeholder SQL dùng để truyền **giá trị**, không dùng để thay thế SQL identifier hoặc cấu trúc.

Ví dụ không có ý nghĩa như mong muốn:

```sql
SELECT id, amount FROM payments ORDER BY :columnName
```

Trong nhiều database, `:columnName` được xem là **giá trị hằng**, chứ không trở thành tên cột để sắp xếp. Để cho phép người vận hành chọn cách sort, cần **ánh xạ từ allowlist sang tên cột cố định**.

### 6.1. Enum allowlist cho sort column

```java
public enum PaymentSortColumn {

    ID("id"),
    CREATED_AT("created_at"),
    AMOUNT("amount");

    private final String sqlName;

    PaymentSortColumn(String sqlName) {
        this.sqlName = sqlName;
    }

    public String sqlName() {
        return sqlName;
    }

    public static PaymentSortColumn fromInput(String raw) {
        return switch (raw) {
            case "id" -> ID;
            case "createdAt" -> CREATED_AT;
            case "amount" -> AMOUNT;
            default -> throw new IllegalArgumentException(
                    "Unsupported sort column");
        };
    }
}
```

Cách tạo query:

```java
PaymentSortColumn sort = PaymentSortColumn.fromInput(requestedSort);
String direction = switch (requestedDirection) {
    case "asc" -> "ASC";
    case "desc" -> "DESC";
    default -> throw new IllegalArgumentException(
            "Unsupported sort direction");
};

String sql = """
        SELECT id, external_id, amount
          FROM payments
         WHERE source_system = :sourceSystem
        ORDER BY
        """ + sort.sqlName() + " " + direction;

MapSqlParameterSource args = new MapSqlParameterSource()
        .addValue("sourceSystem", sourceSystem);

jdbc.query(sql, args, paymentRowMapper);
```

Ở đây, phần được nối vào SQL chỉ xuất phát từ **hằng số nằm trong code qua enum/switch**. Chuỗi người dùng nhập không bao giờ được nối trực tiếp.

Trong job batch, nên tránh hoàn toàn `tableName` hoặc `whereClause` tự do từ `JobParameters`. Nếu có nhiều bảng đích, hãy map một logical destination key sang một danh sách tên bảng cố định do ứng dụng quản lý và kiểm soát quyền truy cập.

### 6.2. Chọn tenant hoặc schema động

Nếu một job có tham số `tenantId`, không nên làm:

```java
// KHÔNG DÙNG:
String sql = "SELECT * FROM " + tenantId + ".payments";
```

Thay vì đưa `tenantId` thành tên schema trực tiếp, có thể:

- Chọn datasource/schema đã cấu hình sẵn theo tenant được phép.
- Map tenant key sang một tập identifier cố định có allowlist.
- Sử dụng row-level tenant filtering với bind parameter nếu kiến trúc cho phép.
- Kiểm tra authorization: user/job được phép truy cập tenant đó không?

**Allowlist tên schema và authorization tenant là hai điều kiện khác nhau.** Một giá trị có trong allowlist không chứng minh bên gọi được quyền truy cập dữ liệu của tenant đó.

## 7. `JdbcBatchItemWriter`: SQL cố định, parameter được bind

Với Spring Batch, `JdbcBatchItemWriter` giúp ghi nhiều item bằng SQL có parameter thay vì tạo một chuỗi SQL mới từ mỗi item.

### 7.1. DTO đã validate

```java
import java.math.BigDecimal;

public record ValidatedPayment(
        String externalId,
        BigDecimal amount,
        String currency
) {
}
```

### 7.2. Writer an toàn

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<ValidatedPayment> paymentWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ValidatedPayment>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO staged_payments (
                    external_id,
                    amount,
                    currency
                ) VALUES (
                    :externalId,
                    :amount,
                    :currency
                )
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("externalId", item.externalId())
                            .addValue("amount", item.amount())
                            .addValue("currency", item.currency()))
            .build();
}
```

`JdbcBatchItemWriter` dùng câu SQL cố định và truyền tham số từng item qua Spring JDBC. Dù giá trị `externalId` chứa ký tự đặc biệt, nó vẫn là dữ liệu. Đây là cách viết an toàn hơn so với nối một chuỗi `"INSERT ... VALUES ('" + value + "')"` trong vòng lặp.

Cần thêm constraint phù hợp ở database, chẳng hạn `UNIQUE(source_system, external_id)` nếu đó là business key. Prepared statements **không tự ngăn bản ghi trùng, dữ liệu sai kiểu, tham số quá dài hoặc ghi đè dữ liệu sai tenant**; các vấn đề này cần validation và ràng buộc dữ liệu riêng.

## 8. Validate nội dung từng item trong `ItemProcessor`

Dữ liệu thô nên được đọc thành một kiểu biểu diễn đầu vào rồi validate ở ranh giới hợp lý. Với file CSV, reader có thể parse trường thành chuỗi, sau đó processor kiểm tra kiểu và chính sách nghiệp vụ trước khi đưa sang writer.

### 8.1. Raw DTO và exception của validation

```java
public record RawPayment(
        String externalId,
        String amountText,
        String currency
) {
}
```

```java
public final class InvalidPaymentException
        extends RuntimeException {

    public InvalidPaymentException(String message) {
        super(message);
    }
}
```

### 8.2. Processor kiểm tra định dạng, độ dài và khoảng giá trị

```java
import java.math.BigDecimal;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.batch.item.ItemProcessor;

public final class ValidatePaymentProcessor
        implements ItemProcessor<RawPayment, ValidatedPayment> {

    private static final Pattern EXTERNAL_ID =
            Pattern.compile("P-[A-Z0-9]{1,40}");

    private static final Set<String> CURRENCIES =
            Set.of("VND", "USD");

    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000000000.00");

    @Override
    public ValidatedPayment process(RawPayment raw) {
        if (raw == null) {
            throw new InvalidPaymentException("Missing row");
        }

        String id = requireText(raw.externalId(), "externalId");
        String amountText = requireText(
                raw.amountText(), "amount");
        String currency = requireText(
                raw.currency(), "currency");

        if (!EXTERNAL_ID.matcher(id).matches()) {
            throw new InvalidPaymentException(
                    "Invalid externalId format");
        }

        if (!CURRENCIES.contains(currency)) {
            throw new InvalidPaymentException(
                    "Unsupported currency");
        }

        if (amountText.length() > 40) {
            throw new InvalidPaymentException(
                    "Amount text is too long");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(amountText);
        } catch (NumberFormatException ex) {
            throw new InvalidPaymentException(
                    "Amount is not numeric");
        }

        if (amount.scale() > 2
                || amount.signum() <= 0
                || amount.compareTo(MAX_AMOUNT) > 0) {
            throw new InvalidPaymentException(
                    "Amount is out of allowed range");
        }

        return new ValidatedPayment(id, amount, currency);
    }

    private static String requireText(
            String raw, String fieldName) {

        if (raw == null) {
            throw new InvalidPaymentException(
                    fieldName + " is required");
        }

        String value = raw.strip();

        if (value.isEmpty()) {
            throw new InvalidPaymentException(
                    fieldName + " is blank");
        }

        return value;
    }
}
```

**Thiết kế của ví dụ này là chủ ý:** Mã thanh toán chỉ chấp nhận `P-` và chữ/số hoa, amount tối đa hai chữ số thập phân, currency thuộc tập cho phép. Đây là **hợp đồng minh họa**, không phải quy tắc chung cho tất cả hệ thống thanh toán. Nếu dữ liệu thực cho phép mã chứa dấu nháy, tiếng Việt hoặc ký tự khác, hãy điều chỉnh validation theo nghiệp vụ **và vẫn bind SQL**.

Không dựa duy nhất vào việc “lọc mọi dấu nháy” hay “cấm chuỗi SELECT” để tránh injection: attacker có thể tìm nhiều cách biểu diễn khác, còn dữ liệu hợp lệ có thể bị hỏng.

### 8.3. Nên parse ở reader hay processor?

Có hai cách hợp lệ:

- **Reader parse kiểu ngay**: một chuỗi amount sai có thể tạo `FlatFileParseException` và được phân loại là lỗi reader.
- **Reader trả Raw DTO, processor validate**: `InvalidPaymentException` thuộc giai đoạn process, có thể được quản lý và audit theo `processSkipCount`.

Lựa chọn tùy mục tiêu phân loại lỗi và hợp đồng dữ liệu. **Không cố gắng làm cho mọi lỗi trở thành read skip.** Điểm quan trọng là dữ liệu không hợp lệ không đi tới writer, và hệ thống có thể giải thích vì sao một item bị loại.

### 8.4. Bean Validation

Với DTO phức tạp, có thể sử dụng Jakarta Bean Validation (`jakarta.validation`) bằng annotation như `@NotBlank`, `@Size`, `@Pattern`, `@Positive`. Trong Spring Boot 3, namespace là `jakarta.validation` (khác `javax.validation` ở các phiên bản cũ).

Ví dụ:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record PartnerReference(
        @NotBlank
        @Size(max = 64)
        @Pattern(regexp = "[A-Za-z0-9_-]+")
        String partnerCode
) {
}
```

Annotation **không tự chạy chỉ vì record được tạo**. Cần một `Validator` được tích hợp vào pipeline hoặc được gọi tường minh, ví dụ bằng Spring Batch `BeanValidatingItemProcessor` nếu dự án dùng đúng module và dependency liên quan, hoặc một processor tự gọi `jakarta.validation.Validator.validate(...)` rồi xử lý violations.

Bean Validation kiểm tra hợp đồng của item; nó cũng **không thay thế** PreparedStatement khi ghi vào database.

## 9. Path traversal: không cho `JobParameters` chọn file tùy ý

Một job đọc file có thể nhận `inputFile` từ bên ngoài. Nếu ứng dụng nối nó trực tiếp với thư mục gốc:

```java
// KHÔNG DÙNG:
Path file = Path.of("/srv/batch/inbox", inputFile);
Files.readString(file);
```

Giá trị như `../secrets/config.txt` có thể đi ra ngoài vùng nhập liệu. Trên một số hệ thống, symlink bên trong thư mục inbox cũng có thể trỏ đến vị trí khác.

### 9.1. Ưu tiên logical key và tên file allowlist

Thay vì cho phép người dùng truyền đường dẫn tuyệt đối, chỉ nhận một `inputKey` như `partner-a-20250512.csv`. Ứng dụng tự quyết định thư mục thực.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

public final class InputFileResolver {

    private static final Pattern SIMPLE_NAME = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9_-]{0,79}\\.csv"
    );

    private final Path allowedRoot;

    public InputFileResolver(Path root) throws IOException {
        this.allowedRoot = root.toRealPath();
    }

    public Path resolve(String inputKey) throws IOException {
        if (inputKey == null
                || !SIMPLE_NAME.matcher(inputKey).matches()) {
            throw new IllegalArgumentException(
                    "Invalid input file key");
        }

        Path requested = allowedRoot.resolve(inputKey).normalize();

        if (!requested.startsWith(allowedRoot)) {
            throw new SecurityException(
                    "Path escapes allowed input directory");
        }

        // Mặc định toRealPath đi theo symlink.
        Path actual = requested.toRealPath();

        if (!actual.startsWith(allowedRoot)
                || !Files.isRegularFile(actual)) {
            throw new SecurityException(
                    "Input is outside allowed files");
        }

        return actual;
    }
}
```

Ví dụ:

```text
inputKey=partner-a-20250512.csv  -> hợp lệ nếu file tồn tại trong root
inputKey=../../secret.txt        -> từ chối
inputKey=/etc/passwd             -> từ chối
inputKey=subdir/file.csv         -> từ chối theo policy tên file đơn
```

Phép so sánh `Path.startsWith(Path)` làm việc theo **thành phần đường dẫn**, khác phép kiểm tra chuỗi ký tự thô như `file.toString().startsWith("/srv/batch")`, vốn dễ chấp nhận nhầm đường dẫn có tiền tố giống nhau.

**Giới hạn bảo mật:** Kiểm tra `toRealPath()` rồi mở file ở bước sau vẫn có thể tồn tại race condition nếu attacker có quyền thay symlink hoặc nội dung thư mục giữa hai thao tác. Với nguồn đe dọa đó, cần bảo vệ thư mục đầu vào bằng quyền filesystem, hạn chế khả năng ghi/đổi tên, hoặc dùng cơ chế mở file an toàn gắn với directory handle trên nền tảng hỗ trợ. Canonicalization là một lớp phòng vệ, không thay thế OS permissions.

### 9.2. Kết hợp với `FlatFileItemReader`

```java
import java.io.IOException;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<RawPayment> paymentReader(
        @Value("#{jobParameters['inputKey']}") String inputKey,
        InputFileResolver resolver) throws IOException {

    return new FlatFileItemReaderBuilder<RawPayment>()
            .name("paymentReader")
            .resource(new FileSystemResource(
                    resolver.resolve(inputKey)))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("external_id", "amount", "currency")
            .fieldSetMapper(fields -> new RawPayment(
                    fields.readString("external_id"),
                    fields.readString("amount"),
                    fields.readString("currency")))
            .build();
}
```

`strict(true)` giúp file thiếu hoặc không đọc được tạo lỗi thay vì ngầm hiểu là nguồn rỗng. `@StepScope` cho phép dùng tham số của execution đúng lúc reader được tạo. Tuy nhiên, **SpEL trong `@Value` không thực hiện validation bảo mật thay ứng dụng**; hàm `InputFileResolver.resolve(...)` vẫn cần kiểm tra đầu vào.

Nếu file có thể bị thay giữa các lần restart, checkpoint số dòng có thể trỏ sang dữ liệu khác. Nên giữ nguyên file/version/checksum của mỗi `JobInstance`.

### 9.3. Giới hạn kích thước file và số dòng

Đường dẫn an toàn chưa có nghĩa nội dung file an toàn. Một file cực lớn, một dòng dài hàng chục MB hoặc một trường có vài triệu ký tự có thể tiêu thụ nhiều bộ nhớ/CPU.

Cần xác định:

- Giới hạn dung lượng file trước khi xử lý.
- Giới hạn độ dài dòng, số cột và độ dài từng trường.
- Schema/header và encoding được phép.
- Giới hạn số record hoặc timeout nhập liệu theo SLA.
- Hành động khi dữ liệu quá ngưỡng: fail hoặc quarantine, không im lặng cắt chuỗi rồi ghi sai dữ liệu.

Các giới hạn này nên được áp dụng **càng gần nguồn càng tốt**. `chunk(100)` là giới hạn số item trong chunk, **không phải** giới hạn độ dài một item hay kích thước toàn file.

## 10. Injection qua output: CSV formula injection

Một tình huống có thể xuất hiện ngay cả khi **SQL đã bind đúng**: job xuất dữ liệu đầu ra sang CSV để người vận hành mở bằng Excel, LibreOffice hoặc một ứng dụng bảng tính khác.

Ví dụ trường `customerNote` từ hệ thống ngoài bắt đầu bằng ký tự công thức:

```csv
order_id,customer_note
O-101,"=1+1"
```

Khi được mở bằng ứng dụng bảng tính, giá trị có thể được diễn giải là **công thức** thay vì chuỗi văn bản. Một số công thức có thể gây rủi ro tùy ứng dụng và cấu hình bảo mật.

**CSV formula injection khác SQL injection**: các dấu nháy hợp lệ của CSV chỉ bao bọc field, không bảo đảm ứng dụng bảng tính coi giá trị bên trong là văn bản thuần.

Cách xử lý tùy hợp đồng:

1. Nếu xuất XLSX, ưu tiên **ghi cell với kiểu dữ liệu text** thay vì tự tạo công thức.
2. Với CSV dự kiến mở bằng spreadsheet, áp dụng policy escape/neutralize các giá trị có thể được diễn giải thành công thức.
3. Kiểm tra cả dấu `=`, `+`, `-`, `@` và ký tự whitespace/control ở đầu; một số phần mềm có hành vi khác nhau.
4. Test bằng đúng ứng dụng và phiên bản mà người nhận sử dụng; **không có một phép escape CSV đơn giản bảo đảm giống nhau ở mọi ứng dụng/import mode**.
5. Với file dữ liệu trao đổi máy–máy, không tự thêm dấu nháy đơn vào mọi giá trị nếu làm thay đổi contract của hệ thống nhận. Có thể cần một định dạng và kênh xuất khác dành cho người dùng cuối.

Đây là ví dụ cho nguyên tắc: **một chuỗi an toàn để lưu vào database không tự động an toàn ở mọi nơi nó được hiển thị hoặc thực thi**.

## 11. URL, shell và các bề mặt injection khác

### 11.1. SSRF nếu job nhận URL tùy ý

Một job tải file từ `sourceUrl` do API truyền vào có thể bị lợi dụng để gọi vào địa chỉ nội bộ hoặc dịch vụ mà job server có quyền truy cập.

**Không nên:**

```java
// sourceUrl đến từ JobParameters và không được kiểm soát:
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(sourceUrl))
        .GET()
        .build();
```

Một mô hình an toàn hơn là chỉ nhận `sourceSystem=PARTNER_A` rồi **chọn endpoint đã cấu hình trước** cho đối tác đó. Nếu bắt buộc hỗ trợ URL động, cần kiểm tra scheme, hostname, port, redirect, DNS/IP đích sau khi resolve, và áp dụng network egress controls. Kiểm tra prefix chuỗi như `url.startsWith("https://trusted")` không đủ an toàn.

### 11.2. Command injection

Nếu job cần gọi công cụ ngoài để chuyển định dạng file, đừng tạo chuỗi shell từ input:

```java
// KHÔNG DÙNG:
String command = "converter --input " + inputKey;
Runtime.getRuntime().exec(command);
```

Một cách tốt hơn là tránh shell và dùng API Java hoặc `ProcessBuilder` với executable/đối số tách biệt, nhưng **vẫn phải validate argument** để ngăn option injection và kiểm soát đường dẫn thực:

```java
ProcessBuilder builder = new ProcessBuilder(
        "/usr/local/bin/converter",
        "--input",
        validatedAbsolutePath.toString(),
        "--output",
        validatedOutputPath.toString()
);
```

Đoạn trên chỉ mô tả cách tách arguments, **không tự đủ an toàn**: executable phải do ứng dụng kiểm soát; `validatedAbsolutePath`, `validatedOutputPath` phải nằm trong vùng cho phép; các option động cũng cần allowlist; process cần timeout và quyền OS tối thiểu.

### 11.3. XML External Entity (XXE)

Nếu batch dùng XML reader, cần ngăn parser tự tải external entities hoặc DTD không được phép. Ví dụ đối với StAX:

```java
import javax.xml.stream.XMLInputFactory;

XMLInputFactory factory = XMLInputFactory.newFactory();

factory.setProperty(
        XMLInputFactory.SUPPORT_DTD,
        false
);

factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        false
);
```

Khi dùng `StaxEventItemReader` hoặc XML parser khác, phải bảo đảm **parser thực sự được sử dụng** trong reader có cấu hình an toàn đó, không chỉ tạo một factory rồi bỏ không. Ngoài XXE, cần xem cả giới hạn độ sâu, kích thước document và các kiểu tiêu thụ tài nguyên quá mức.

### 11.4. Expression và template injection

Spring Batch dùng SpEL ở các bean step-scoped/job-scoped, ví dụ:

```java
@Value("#{jobParameters['businessDate']}")
String businessDate
```

Ở đây expression là **câu cố định do developer viết** và chỉ đọc giá trị tham số. Giá trị nhận được không nên bị đem đi **tạo một expression mới** rồi evaluate như code.

Tránh thiết kế “nhận một chuỗi `expression` từ CSV/jobParameters và nhờ expression engine thực thi” nếu không có môi trường sandbox/capability hạn chế và nhu cầu thực sự rõ ràng. Trong phần lớn batch nhập dữ liệu, tốt hơn là map logical rule key sang một tập predicate do ứng dụng định nghĩa.

## 12. Kiểm soát lỗi: skip, fail hay quarantine?

Trong Spring Batch, không phải dữ liệu không hợp lệ nào cũng cần dừng toàn job, nhưng **lỗi bảo mật** không nên bị bỏ qua một cách mù quáng.

| Lỗi | Chính sách gợi ý |
|---|---|
| Một dòng có amount sai kiểu trong file mà nghiệp vụ cho phép bỏ qua | Process skip có giới hạn và audit |
| Mã đơn sai định dạng | Quarantine hoặc skip theo quality threshold |
| `inputKey` cố truy cập ngoài vùng cho phép | Từ chối job ở giai đoạn tham số / reader initialization; audit |
| Tham số chọn tenant không được cấp quyền | Từ chối launch, không xử lý dữ liệu |
| Header CSV không khớp schema mong đợi | Fail fast hoặc quarantine toàn file |
| Lỗi dữ liệu diện rộng vượt ngưỡng | Fail step; không âm thầm “COMPLETED” với dữ liệu thiếu |
| Database báo lỗi SQL hoặc unique constraint ngoài policy | Phân loại cụ thể; không `skip(Exception.class)` đại trà |
| Payload chứa nội dung ký tự đặc biệt nhưng thuộc contract hợp lệ | Tiếp nhận, dùng binding/output encoding phù hợp |

### 12.1. Skip có kiểm soát cho lỗi validation nghiệp vụ

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
Step importPaymentsStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawPayment> paymentReader,
        ItemProcessor<RawPayment, ValidatedPayment> validator,
        ItemWriter<ValidatedPayment> paymentWriter) {

    return new StepBuilder("importPaymentsStep", repository)
            .<RawPayment, ValidatedPayment>chunk(
                    100, transactionManager)
            .reader(paymentReader)
            .processor(validator)
            .writer(paymentWriter)
            .faultTolerant()
            .skip(InvalidPaymentException.class)
            .skipLimit(10)
            .build();
}
```

Ví dụ này chỉ skip lỗi **được phân loại rõ** là `InvalidPaymentException`, chứ không skip mọi `RuntimeException` hoặc SQL exception. `skipLimit(10)` là ngưỡng tổng skip của step, không phải ngưỡng riêng biệt cho mọi loại lỗi.

Nếu dữ liệu quá nhạy cảm để chấp nhận thiếu bản ghi, không bật skip và cho step fail. Với hệ thống thanh toán, validation có thể phải nghiêm ngặt hơn ví dụ trên.

### 12.2. Audit mà không lộ dữ liệu

Một bản ghi log tốt:

```text
event=batch.input.rejected
jobName=importPaymentsJob
jobExecutionId=501
sourceSystem=PARTNER_A
inputKey=partner-a-20250512.csv
sourceLine=47
errorCode=INVALID_AMOUNT
action=QUARANTINED
```

Không log trực tiếp token, mật khẩu, raw HTTP header, nguyên connection string hoặc toàn bộ payload từ bên ngoài. Với đầu vào không đáng tin, còn cần tránh **log injection** bằng ký tự xuống dòng/điều khiển và tránh làm nổ cardinality khi tạo metric tags.

Nên có cơ chế lưu mẫu dữ liệu lỗi vào kho quarantine được phân quyền, mã hóa và có retention policy, thay vì đặt toàn bộ thông tin nhạy cảm trong log ứng dụng.

## 13. Authorization, least privilege và tenant isolation

Validation là cần thiết nhưng vẫn không thay thế quyền truy cập.

Một yêu cầu `businessDate=2025-05-12` có thể đúng cú pháp, nhưng caller không được phép chạy job nhập dữ liệu của đối tác khác. Một `inputKey` khớp allowlist có thể trỏ tới file đúng định dạng nhưng thuộc tenant khác.

Các lớp cần có:

1. **Caller authorization**: endpoint/console chỉ cho vai trò được phép launch/restart/stop job.
2. **Source authorization**: caller/job được phép chọn `sourceSystem`, `inputKey` hay tenant đó.
3. **Database least privilege**: tài khoản JDBC chỉ được đọc/ghi các bảng cần thiết, không cần quyền tạo/drop schema.
4. **Filesystem least privilege**: process chỉ có quyền đọc inbox phù hợp và ghi output vào vùng riêng; không đọc được secrets ngoài phạm vi.
5. **Network egress policy**: worker chỉ truy cập các endpoint cần thiết.
6. **Secret handling**: credential qua secret manager/config bảo mật, không đưa vào `JobParameters` chỉ để tiện hiển thị.

Những biện pháp này **giảm mức độ ảnh hưởng** nếu một đường validation có lỗi. Không thể coi SQL parameter binding là lá chắn cho việc đọc nhầm tenant khi quyền truy cập không được kiểm tra.

## 14. Kiểm thử input validation và injection

Security test phải kiểm tra cả **trường hợp hợp lệ có ký tự đặc biệt** lẫn **đầu vào cố tình đi ngoài hợp đồng**. Không nên chỉ assert rằng một regex chặn dấu nháy đơn rồi kết luận đã chống SQL injection.

### 14.1. Unit test `JobParametersValidator`

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

class ImportJobParametersValidatorTest {

    private final ImportJobParametersValidator validator =
            new ImportJobParametersValidator();

    private JobParameters parameters(
            String businessDate,
            String inputKey,
            String sourceSystem) {

        return new JobParametersBuilder()
                .addString("businessDate", businessDate)
                .addString("inputKey", inputKey)
                .addString("sourceSystem", sourceSystem)
                .toJobParameters();
    }

    @Test
    void acceptsValidParameters() {
        assertDoesNotThrow(() -> validator.validate(
                parameters(
                        "2025-05-12",
                        "partner-a-20250512.csv",
                        "PARTNER_A")
        ));
    }

    @Test
    void rejectsParentDirectoryTraversal() {
        assertThrows(
                JobParametersInvalidException.class,
                () -> validator.validate(
                        parameters(
                                "2025-05-12",
                                "../secret.csv",
                                "PARTNER_A"))
        );
    }

    @Test
    void rejectsInvalidCalendarDate() {
        assertThrows(
                JobParametersInvalidException.class,
                () -> validator.validate(
                        parameters(
                                "2025-02-30",
                                "orders.csv",
                                "PARTNER_A"))
        );
    }

    @Test
    void rejectsUnsupportedSource() {
        assertThrows(
                JobParametersInvalidException.class,
                () -> validator.validate(
                        parameters(
                                "2025-05-12",
                                "orders.csv",
                                "UNKNOWN"))
        );
    }
}
```

Chạy test này không cần cơ sở dữ liệu hoặc chạy job. Test kiểm tra hợp đồng tham số, không khẳng định cách OS xử lý symlink hoặc database xử lý SQL.

### 14.2. Unit test processor với input xấu

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class ValidatePaymentProcessorTest {

    private final ValidatePaymentProcessor processor =
            new ValidatePaymentProcessor();

    @Test
    void acceptsValidPayment() throws Exception {
        ValidatedPayment actual = processor.process(
                new RawPayment("P-101", "125000.00", "VND"));

        assertEquals("P-101", actual.externalId());
        assertEquals(new BigDecimal("125000.00"), actual.amount());
    }

    @Test
    void rejectsUnexpectedIdStructure() {
        assertThrows(
                InvalidPaymentException.class,
                () -> processor.process(
                        new RawPayment(
                                "P-101' OR '1'='1",
                                "125000",
                                "VND"))
        );
    }

    @Test
    void rejectsInvalidAmount() {
        assertThrows(
                InvalidPaymentException.class,
                () -> processor.process(
                        new RawPayment("P-101", "not-a-number", "VND"))
        );
    }

    @Test
    void rejectsOversizedAmountText() {
        assertThrows(
                InvalidPaymentException.class,
                () -> processor.process(
                        new RawPayment(
                                "P-101",
                                "9".repeat(1000),
                                "VND"))
        );
    }
}
```

Ở đây ID có dấu nháy bị chặn do **hợp đồng mã `P-[A-Z0-9]{1,40}`**, không phải vì SQL parameter binding không xử lý được dấu nháy. Nếu ID cần hỗ trợ dấu nháy hợp lệ, test nên xác nhận writer vẫn truyền nó qua parameter binding mà không đổi cấu trúc SQL.

### 14.3. Integration test chứng minh giá trị SQL không thành điều kiện query

Một test Spring Boot với `@JdbcTest` có thể đưa chuỗi trông giống SQL vào **tham số bind** và xác nhận nó được xem như một giá trị nguyên vẹn.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@JdbcTest
class ParameterizedQuerySecurityTest {

    @Autowired
    NamedParameterJdbcTemplate jdbc;

    @BeforeEach
    void setUp() {
        jdbc.getJdbcTemplate().execute(
                "DROP TABLE IF EXISTS test_customers");

        jdbc.getJdbcTemplate().execute("""
                CREATE TABLE test_customers (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(128) NOT NULL
                )
                """);

        jdbc.getJdbcTemplate().update(
                "INSERT INTO test_customers(id, name) VALUES (?, ?)",
                1L,
                "Alice");
    }

    @Test
    void suspiciousTextMustBeTreatedAsOneValue() {
        String untrustedName = "x' OR '1'='1";

        Integer count = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                  FROM test_customers
                 WHERE name = :name
                """,
                Map.of("name", untrustedName),
                Integer.class
        );

        // Không truy cập mọi dòng thông qua cú pháp do input tạo ra.
        assertEquals(0, count);

        Integer stillOneRow = jdbc.getJdbcTemplate()
                .queryForObject(
                        "SELECT COUNT(*) FROM test_customers",
                        Integer.class);

        assertEquals(1, stillOneRow);
    }
}
```

Test trên dùng database nhúng được Spring Boot `@JdbcTest` cấu hình (ví dụ H2 có trong test classpath). Nó kiểm tra đúng câu query với parameter binding; không thay thế thử nghiệm bảo mật cho **mọi query khác** trong ứng dụng.

### 14.4. Test path resolver với `@TempDir`

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class InputFileResolverTest {

    @TempDir
    Path tempDirectory;

    @Test
    void acceptsFileInsideAllowedRoot() throws Exception {
        Path file = tempDirectory.resolve("orders.csv");
        Files.writeString(file, "external_id,amount,currency\n");

        InputFileResolver resolver =
                new InputFileResolver(tempDirectory);

        assertEquals(file.toRealPath(), resolver.resolve("orders.csv"));
    }

    @Test
    void rejectsTraversalBeforeOpeningFile() throws Exception {
        InputFileResolver resolver =
                new InputFileResolver(tempDirectory);

        assertThrows(
                IllegalArgumentException.class,
                () -> resolver.resolve("../other.csv")
        );
    }
}
```

Trường hợp symlink escape nên có test riêng trên hệ điều hành có hỗ trợ tạo symlink và quyền tương ứng. Không nên bắt toàn bộ test chạy ở mọi CI phải tạo symlink khi môi trường không cho phép; mục tiêu vẫn phải được kiểm tra bằng integration/security test thích hợp.

### 14.5. Bộ dữ liệu test nên có gì?

| Trường hợp | Ví dụ | Mục tiêu |
|---|---|---|
| Input hợp lệ | `P-101`, `125000.00` | Không chặn dữ liệu bình thường |
| Ký tự đặc biệt hợp lệ | Tên `O'Brien` | Không phá dữ liệu chỉ vì có dấu nháy |
| Chuỗi trông giống SQL | `x' OR '1'='1` | Parameter binding, không biến thành SQL |
| Tên cột không được phép | `sortBy=arbitraryColumn` | Allowlist từ chối |
| Path traversal | `../secret.csv` | Không mở file ngoài root |
| Path tuyệt đối | `/etc/passwd` | Không nhận trong input key |
| File cực lớn / dòng quá dài | Input vượt quota | Fail an toàn, không làm cạn tài nguyên |
| Source/tenant sai quyền | `PARTNER_B` từ caller không được phép | Authorization |
| Amount không hợp lệ | `NaN`, số âm, quá dài | Validation |
| Spreadsheet formula | Field bắt đầu `=` | Output CSV/XLSX được xử lý theo policy |
| XML có external entity | DTD/entity từ nguồn không tin cậy | Parser không tải tài nguyên ngoài |
| Retry/restart | Chạy lại cùng file/version | Không phát lại side effect ngoài ý muốn |

Tách các loại test: **unit test** cho validator/processor; **integration test** cho JDBC và filesystem; **job/step test** cho wiring, skip limit, transaction và restart. Một regex unit test đơn lẻ không chứng minh cả pipeline an toàn.

## 15. Monitoring và phản ứng khi phát hiện đầu vào đáng ngờ

Một batch chạy tự động thường không có người theo dõi từng bản ghi. Cần thiết kế tín hiệu vận hành để những thay đổi bất thường ở dữ liệu không bị che giấu.

### Các chỉ số hữu ích

| Metric | Ý nghĩa |
|---|---|
| `input_validation_rejections_total` | Số item bị từ chối vì không đúng schema/contract |
| `batch_job_launch_rejected_total` | Số yêu cầu launch bị từ chối do tham số/quyền |
| `input_path_validation_failure_total` | Số lần phát hiện input key/path không được phép |
| `batch_process_skip_total` | Số item bị skip ở processor |
| `input_quarantine_records_total` | Số record phải xem xét riêng |
| `batch_step_failed_total` | Số step thất bại, gồm lỗi định dạng diện rộng |
| `source_schema_mismatch_total` | Số file/event không đúng schema đã định nghĩa |

Tên metric là ví dụ do ứng dụng tự định nghĩa, **không phải tên meter mặc định của Spring Batch**. Có thể kết hợp với `StepExecution.readSkipCount`, `processSkipCount`, `writeSkipCount` và `BatchStatus` để hiểu chất lượng dữ liệu.

Không gắn từng payload, customer ID, giá trị path hoặc exception message làm nhãn metric; chúng có độ biến động cao và có thể tiết lộ dữ liệu. Dùng nhãn có cardinality thấp như `jobName`, `sourceSystem`, `errorCode`.

### Khi phát hiện tấn công hoặc dữ liệu sai diện rộng

- Ngừng publish kết quả nghiệp vụ nếu ngưỡng chất lượng/an toàn không đạt.
- Ghi lại `jobExecutionId`, file ID/version và nguồn phát sinh.
- Cách ly dữ liệu, hạn chế thông tin nhạy cảm trong log.
- Xác minh có job khác đang dùng cùng dữ liệu hoặc bị điều phối nhầm không.
- Kiểm tra DB changes đã commit và khả năng rollback/restart.
- Ưu tiên sửa lỗi tại boundary và thêm regression test trước khi chạy lại.
- Đừng tự tăng `skipLimit` hoặc bỏ validation chỉ để biến một job `FAILED` thành `COMPLETED`.

## 16. Anti-pattern và cách thay thế

| Anti-pattern | Vấn đề | Thay bằng |
|---|---|---|
| Nối `orderId` trực tiếp vào SQL | SQL injection, lỗi với dấu nháy | `PreparedStatement` / `NamedParameterJdbcTemplate` |
| Chỉ escape dấu `'` | Không xử lý mọi ngữ cảnh SQL | Parameter binding |
| `ORDER BY ` + giá trị người dùng | Không bind identifier được | Enum/allowlist identifier |
| Chọn tên bảng/schema từ `JobParameters` không kiểm soát | Đọc/ghi dữ liệu sai vùng | Mapping logical key sang cấu hình cố định + authorization |
| Dùng `Path.of(root, inputKey)` trực tiếp | Path traversal/symlink escape | Logical key, canonicalization, OS permissions |
| Dùng `String.startsWith` để kiểm tra đường dẫn | Dễ so nhầm tiền tố chuỗi | `Path.startsWith(Path)` và real path |
| Nhận URL bất kỳ để reader tải | SSRF, truy cập hệ thống nội bộ | Định nghĩa endpoint theo source key |
| Gọi shell với tham số nối chuỗi | Command injection | Tránh shell, executable/options allowlist |
| Evaluate expression từ nội dung file | Expression injection | Rule key mapping cố định |
| Cho parser XML tải external entity | XXE và đọc tài nguyên không mong muốn | Tắt DTD/external entities trong parser thực sự sử dụng |
| Nghĩ PreparedStatement kiểm tra chất lượng dữ liệu | SQL an toàn nhưng amount có thể âm/sai | Validation và ràng buộc DB |
| `skip(Exception.class)` để không fail job | Che lỗi bảo mật/hạ tầng | Skip loại lỗi đã phân loại, có ngưỡng |
| In raw payload nguy hiểm vào log | Lộ dữ liệu, log injection | Log code, ID, line number đã kiểm soát |
| Ghi CSV mà không xét ứng dụng mở file | Spreadsheet formula injection | Output encoding/kiểu cell theo đích |
| Test chỉ với dữ liệu đẹp | Lỗi boundary còn nguyên | Test input xấu, quá dài, path, replay |
| Dùng `LocalDate.now()` khi restart | Đổi tập dữ liệu giữa các lượt chạy | Business date trong `JobParameters` |
| Chạy job bằng tài khoản DB quá rộng quyền | Tăng mức độ thiệt hại nếu bị khai thác | Least-privilege DB user |
| Dùng validation ở một nơi duy nhất | Đường chạy khác có thể bỏ qua kiểm tra | Boundary validation + safe sink APIs + DB constraints |

## 17. Bài tập thực hành: xây import pipeline an toàn

Xây dựng job `secureImportPayments` nhập CSV từ đối tác, theo ngày nghiệp vụ. File chứa `external_id`, `amount`, `currency` và `note`. Kết quả lưu vào bảng `staged_payments`.

Yêu cầu:

1. Định nghĩa `JobParameters` gồm `businessDate`, `inputKey`, `sourceSystem`. Validate ngay khi job bắt đầu: ngày thật, tên file đơn `.csv` và source thuộc tập cho phép.
2. Cấu hình `InputFileResolver` chỉ cho phép reader mở file bên trong một inbox root do ứng dụng cấu hình. Từ chối `../`, đường dẫn tuyệt đối và symlink ra ngoài.
3. Reader phải giới hạn dung lượng file, kiểm tra schema/header và parse mỗi dòng thành `RawPayment`.
4. Processor kiểm tra mã, amount, currency và độ dài note; quyết định rõ lỗi nào được quarantine, lỗi nào làm toàn job fail.
5. Writer dùng `JdbcBatchItemWriter` và named parameters; không nối trường đầu vào vào SQL.
6. Nếu có tùy chọn sort, chỉ chọn `id`, `createdAt` hoặc `amount` qua enum allowlist. Không nhận raw `ORDER BY` hoặc `WHERE` từ tham số job.
7. Tạo unique constraint theo business key và kiểm tra restart/retry không tạo duplicate transaction.
8. Viết unit test cho input key, business date, source, amount và processor. Thử cả ký tự đặc biệt hợp lệ lẫn input có cú pháp SQL.
9. Viết integration test JDBC chứng minh payload chứa `' OR '1'='1` vẫn là một giá trị bound, không thay đổi kết quả query.
10. Tạo một output CSV cho người dùng. Dùng trường `note` bắt đầu bằng ký tự công thức và xác minh phương án output encoding của ứng dụng đích.
11. Thiết lập metric theo `errorCode` và log đã loại bỏ dữ liệu nhạy cảm.
12. Kiểm tra caller thuộc đối tác A không thể launch job đọc file của đối tác B dù `sourceSystem` của B là giá trị hợp lệ về mặt schema.

**Câu hỏi ôn tập:** Nếu input đã được validate bằng regex không chứa dấu nháy đơn, có thể bỏ PreparedStatement để tự nối SQL không?

**Trả lời:** **Không.** Regex chỉ thể hiện một phần hợp đồng dữ liệu và có thể thay đổi hoặc bị bỏ qua ở đường code khác. Bất kỳ giá trị không tin cậy nào đi vào SQL vẫn phải được truyền qua parameter binding. Khi phải thay đổi cấu trúc SQL (ví dụ tên cột), dùng allowlist các cấu trúc cố định do ứng dụng định nghĩa.

## 18. Tài liệu tham khảo

- [Spring Batch Reference — Job Parameters Validator](https://docs.spring.io/spring-batch/reference/job/configuring.html): kiểm tra `JobParameters` trước khi thực thi.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vai trò `ItemReader`, `ItemProcessor`, `ItemWriter` và transaction.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): lọc hoặc validate item trong processor.
- [Spring Batch Reference — Database Item Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): `JdbcBatchItemWriter` và ghi dữ liệu với JDBC.
- [Spring Framework Reference — JDBC Parameter Binding](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `NamedParameterJdbcTemplate` và binding.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): prepared statements, allowlist identifiers và least privilege.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): rủi ro đường dẫn file do input điều khiển.
- [OWASP — CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection): spreadsheet formula injection khi xuất dữ liệu.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): kiểm soát URL/endpoint từ bên ngoài.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): cấu hình XML parser chống XXE.
- [Java SE — Path API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `normalize`, `toRealPath`, `startsWith` và xử lý đường dẫn.
