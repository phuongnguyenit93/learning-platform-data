# Thêm processor validate và map dữ liệu trong dự án Spring Batch

Trong một dự án Spring Batch, dữ liệu được đọc từ CSV, database hoặc API thường chưa ở dạng mà nghiệp vụ có thể sử dụng trực tiếp. Các trường có thể dư khoảng trắng, sai kiểu ngày, mang mã trạng thái không hợp lệ hoặc thiếu thông tin bắt buộc. Nếu đưa thẳng dữ liệu thô từ `ItemReader` sang `ItemWriter`, hệ thống sẽ phải dựa vào constraint của database hoặc lỗi ở writer để phát hiện vấn đề; đến lúc đó rất khó giải thích bản ghi nào sai và tại sao.

Bài thực hành này tập trung vào **thêm `ItemProcessor` để validate và map dữ liệu** trong luồng xử lý Spring Batch. Chúng ta sẽ xây dựng một ví dụ nhập đơn hàng từ CSV vào database: reader đọc giá trị dạng chuỗi, processor **chuẩn hóa → kiểm tra → chuyển sang model đầu ra**, và writer chỉ nhận những bản ghi đã hợp lệ.

Bài học được trình bày độc lập để có thể áp dụng vào một dự án hiện có hoặc dùng làm khuôn mẫu thực hành. Những tên Job, lớp và bảng dưới đây là ví dụ, không giả định một cấu trúc code đã tồn tại sẵn. Mã triển khai chính hướng tới **Java 17, Spring Boot 3.x và Spring Batch 5.x**. Khi dùng Spring Batch 6.x, một số package và API builder đã thay đổi; cần chỉnh import/cấu hình theo phiên bản thực tế.

## 1. Mục tiêu và yêu cầu đầu ra

Sau bài học, người học có thể:

1. Xác định trách nhiệm của `ItemReader`, `ItemProcessor` và `ItemWriter` trong chunk-oriented Step.
2. Tạo model **đầu vào thô** và **đầu ra đã chuẩn hóa** thay vì ghi trực tiếp từ CSV vào entity database.
3. Kiểm tra trường bắt buộc, mã trạng thái, ngày, số tiền và tập giá trị được hỗ trợ.
4. Map kiểu dữ liệu từ `String` sang `LocalDate`, `BigDecimal` và những field của model đích.
5. Phân biệt **filter bằng `return null`**, **skip vì exception đã được cho phép** và **fail Step** khi gặp lỗi nghiêm trọng.
6. Nối processor vào Step, thiết kế báo cáo lỗi và kiểm tra counters.
7. Viết unit test cho processor và integration test cho luồng Reader → Processor → Writer.
8. Nhận diện ảnh hưởng của retry, restart, transaction và chạy song song đối với processor.

Kết quả kỳ vọng là một Job chỉ ghi **đơn hàng đủ điều kiện**, có bộ đếm rõ ràng cho bản ghi bị lọc và bản ghi lỗi, đồng thời không dựa vào dữ liệu giả định “lúc nào cũng sạch”.

## 2. Luồng xử lý của dự án

Ta chọn ví dụ `importOrdersJob` nạp CSV đơn hàng vào bảng `accepted_order`:

```text
CSV file
  |
  v
FlatFileItemReader<RawOrder>
  |
  |  Dữ liệu còn ở dạng chuỗi:
  |  orderDate = "2026-11-16"
  |  amount    = "125.50"
  |  currency  = "usd"
  v
ItemProcessor<RawOrder, PreparedOrder>
  |
  +-- trim và chuẩn hóa mã
  +-- kiểm tra trường bắt buộc
  +-- parse ngày và số tiền
  +-- kiểm tra quy tắc nghiệp vụ
  +-- map sang PreparedOrder
  |
  +-- lỗi dữ liệu hợp lệ để skip --> SkipListener / báo cáo lỗi
  |
  +-- trạng thái DRAFT --> return null (filter)
  |
  v
JdbcBatchItemWriter<PreparedOrder>
  |
  v
accepted_order (PostgreSQL)
```

Trong một chunk Step, Spring Batch gọi:

```java
O output = processor.process(input);
```

Với `I` là kiểu item reader trả về và `O` là kiểu item writer nhận. `ItemProcessor<I, O>` không bắt buộc phải giữ nguyên kiểu `I == O`.

Đây là điểm quan trọng của bài thực hành: dữ liệu CSV có trường `amount` dạng `String`, nhưng writer chỉ nhận `BigDecimal` đã qua validation; dữ liệu CSV có `order_date` dạng text, nhưng writer nhận `LocalDate`.

### Phân định trách nhiệm

| Thành phần | Nên làm | Nên tránh |
| --- | --- | --- |
| `ItemReader` | Đọc dòng/record, tách cột, tạo `RawOrder`, cung cấp source location khi có thể. | Gánh toàn bộ quy tắc nghiệp vụ hoặc âm thầm sửa dữ liệu không hợp lệ. |
| `ItemProcessor` | Chuẩn hóa, validate, filter theo rule, map sang `PreparedOrder`. | Ghi database, gọi remote service có side effect hoặc thay đổi dữ liệu dùng chung tùy tiện. |
| `ItemWriter` | Ghi các item hợp lệ theo transaction, idempotency và constraint. | Cố đoán ý nghĩa của dữ liệu thô hoặc tự xử lý mọi lỗi validation. |
| `SkipListener` | Ghi nhận item bị skip sau quyết định của fault-tolerant Step. | Coi mọi exception tạm thời là rejected item cuối cùng. |

Đặt validation ở processor giúp test từng quy tắc độc lập mà không phải mở kết nối database hoặc khởi chạy cả Job.

## 3. Định nghĩa hợp đồng dữ liệu mẫu

### 3.1. CSV đầu vào

Tạo một file mẫu ở `src/test/resources/orders-fixture.csv`:

```csv
source_row_id,order_id,customer_code,order_date,amount,currency,order_status
r-01,ord-1001,cus-01,2026-11-16,125.50,usd,READY
r-02,ord-1002,cus-02,2026-11-16,0,USD,READY
r-03,ord-1003,cus-03,2026-11-16,45.00,eur,DRAFT
r-04,ord-1004,,2026-11-16,33.40,USD,READY
r-05,ord-1005,cus-05,2026-11-17,99.99,USD,READY
r-06,ord-1006,cus-06,2026-11-16,12.999,USD,READY
r-07,ord-1007,cus-07,2026-11-16,not-a-number,USD,READY
r-08,ord-1008,cus-08,2026-11-16,40.00,gbp,READY
r-09,ord-1009,cus-09,2026-11-16,7.50,USD,READY
```

Mỗi dòng có một `source_row_id` để tra cứu khi lỗi. Trong dữ liệu thật, khóa nguồn phải ổn định theo file/dataset và đủ duy nhất; `r-01` ở hai file khác nhau không phải cùng một occurrence.

### 3.2. Quy tắc nghiệp vụ minh họa

| Trường | Quy tắc |
| --- | --- |
| `source_row_id` | Bắt buộc, dùng để định vị bản ghi nguồn. |
| `order_id` | Bắt buộc; trim, chuyển chữ hoa; chỉ cho phép chữ cái, số và dấu gạch ngang. |
| `customer_code` | Bắt buộc; trim, chuyển chữ hoa; chỉ cho phép chữ cái, số và dấu gạch ngang. |
| `order_date` | Ngày ISO `yyyy-MM-dd`, phải parse được thành `LocalDate`. |
| `amount` | Số thập phân dương, tối đa 2 chữ số sau dấu thập phân, không lớn hơn 1.000.000,00 theo currency tương ứng. |
| `currency` | Chỉ chấp nhận `USD` hoặc `EUR` trong phiên bản bài tập này; viết hoa mã. |
| `order_status` | `READY` được xử lý; `DRAFT` được filter; giá trị khác là lỗi dữ liệu. |

Giới hạn USD/EUR và hai chữ số thập phân được chọn **chỉ để làm ví dụ nhất quán**. Nếu dự án hỗ trợ JPY, VND hoặc nhiều đơn vị tiền tệ khác, không áp đặt cùng số chữ số thập phân cho mọi currency; cần có quy tắc theo currency và hợp đồng nghiệp vụ thật.

### 3.3. Kết quả dự kiến với fixture

| Source row | Kết quả | Lý do |
| --- | --- | --- |
| `r-01` | Ghi vào bảng | Hợp lệ, mã được chuẩn hóa. |
| `r-02` | Process skip | Số tiền không dương. |
| `r-03` | Filter | Trạng thái `DRAFT` chưa cần nhập. |
| `r-04` | Process skip | Thiếu `customer_code`. |
| `r-05` | Ghi vào bảng | Hợp lệ. |
| `r-06` | Process skip | `12.999` có quá 2 chữ số thập phân. |
| `r-07` | Process skip | `amount` không parse được. |
| `r-08` | Process skip | Currency `GBP` không nằm trong tập hỗ trợ của bài tập. |
| `r-09` | Ghi vào bảng | Hợp lệ. |

Tổng cộng 9 record nguồn, **3 bản ghi hợp lệ**, **1 bản ghi filtered** và **5 bản ghi process-skipped**. Những con số này là kỳ vọng của fixture để dùng trong kiểm thử, không phải ngưỡng chung cho mọi Job.

## 4. Dependency và môi trường Spring Batch

Trong một dự án Gradle với Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Nếu muốn thử `BeanValidatingItemProcessor` với Jakarta Bean Validation trong phần mở rộng, bổ sung:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Spring Boot cần một `DataSource` và `PlatformTransactionManager` cho Job/Step phù hợp; Spring Batch cần schema metadata của `JobRepository`. Database test nên được cô lập với production.

Với test tích hợp, có thể tắt khởi chạy Job tự động khi Spring Boot tạo context:

```java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderImportIT {
    // Tự khởi chạy Job sau khi đã chuẩn bị dữ liệu.
}
```

Ví dụ trong bài dùng **PostgreSQL** để minh họa bảng kết quả và cú pháp upsert. Nếu dùng H2, MySQL hoặc Oracle, cần điều chỉnh SQL phù hợp. Không tự động thực thi script dọn bảng production để chạy fixture.

## 5. Tạo model đầu vào thô: `RawOrder`

Không nên dùng trực tiếp entity JPA hoặc model database làm đối tượng đọc CSV. Một model đầu vào độc lập giúp nhận những giá trị chưa hợp lệ mà không cần ép kiểu quá sớm.

Tạo `RawOrder.java`:

```java
package example.batch.orders;

public record RawOrder(
        String sourceRowId,
        String orderId,
        String customerCode,
        String orderDate,
        String amount,
        String currency,
        String orderStatus) {
}
```

Ở giai đoạn này, **tất cả field là `String`**. Vì vậy:

- Dòng có `amount=not-a-number` vẫn có thể tạo `RawOrder`, và processor phân loại thành lỗi `AMOUNT_INVALID_FORMAT`.
- Dòng có `customer_code` trống vẫn vào processor để nhận lỗi validation cụ thể.
- Reader chỉ chịu trách nhiệm tách cột theo định dạng CSV.

Điều này phù hợp khi muốn đưa phần lớn lỗi dữ liệu nghiệp vụ vào processor. Nó không có nghĩa reader không thể lỗi: dòng CSV bị sai cấu trúc, thiếu cột, lỗi encoding hoặc tài nguyên không đọc được vẫn có thể gây `FlatFileParseException`/lỗi I/O. Chính sách read skip cần được thiết kế riêng.

## 6. Tạo model đầu ra: `PreparedOrder`

Model đầu ra thể hiện **hợp đồng của item đã qua validation**:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.time.LocalDate;

public record PreparedOrder(
        String sourceRowId,
        String orderId,
        String customerCode,
        LocalDate orderDate,
        BigDecimal amount,
        String currency) {
}
```

Khác với `RawOrder`:

- `orderDate` là `LocalDate`, không còn là chuỗi có thể chứa giá trị ngày sai.
- `amount` là `BigDecimal` với scale được kiểm soát.
- `orderId`, `customerCode` và `currency` đã được chuẩn hóa.
- Chỉ có những item đáp ứng chính sách `READY` mới được tạo thành output.

### Vì sao dùng `BigDecimal` thay cho `double`?

Với tiền tệ, `double` biểu diễn nhị phân có thể gây sai số làm tròn. `BigDecimal` cho phép kiểm soát phép toán thập phân, scale và quy tắc làm tròn rõ ràng.

Không nên tự động dùng `setScale(2, RoundingMode.HALF_UP)` để biến `12.999` thành `13.00` nếu hợp đồng đầu vào yêu cầu tối đa hai chữ số thập phân. Bài này chủ động **reject precision sai** thay vì âm thầm sửa.

## 7. Định nghĩa exception validation có mã lỗi

Để một bản ghi lỗi có thể được báo cáo rõ ràng, nên dùng exception riêng mang **mã lỗi ổn định**, thay vì phụ thuộc vào message của `NumberFormatException` hoặc `DateTimeParseException`.

Tạo `OrderValidationException.java`:

```java
package example.batch.orders;

public final class OrderValidationException
        extends RuntimeException {

    private final String errorCode;
    private final String sourceRowId;

    public OrderValidationException(
            String errorCode,
            String sourceRowId) {

        // Message không chứa raw payload nhạy cảm.
        super(errorCode);
        this.errorCode = errorCode;
        this.sourceRowId = sourceRowId;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getSourceRowId() {
        return sourceRowId;
    }
}
```

Ví dụ mã lỗi:

| `errorCode` | Ý nghĩa |
| --- | --- |
| `SOURCE_ROW_ID_REQUIRED` | Không có định danh nguồn. |
| `ORDER_STATUS_REQUIRED` | Thiếu trạng thái đơn. |
| `ORDER_STATUS_UNSUPPORTED` | Trạng thái nằm ngoài tập cho phép. |
| `ORDER_ID_REQUIRED` | Thiếu mã đơn hàng. |
| `ORDER_ID_INVALID` | Mã đơn có ký tự không được hỗ trợ. |
| `CUSTOMER_CODE_REQUIRED` | Thiếu mã khách hàng. |
| `CUSTOMER_CODE_INVALID` | Mã khách hàng không hợp lệ. |
| `ORDER_DATE_INVALID` | Ngày sai định dạng hoặc không tồn tại. |
| `AMOUNT_INVALID_FORMAT` | Số tiền không parse được. |
| `AMOUNT_TOO_MANY_DECIMALS` | Số tiền có nhiều hơn 2 chữ số thập phân. |
| `AMOUNT_NOT_POSITIVE` | Số tiền không dương. |
| `AMOUNT_OUT_OF_RANGE` | Số tiền vượt giới hạn nghiệp vụ. |
| `CURRENCY_UNSUPPORTED` | Đơn vị tiền tệ không được hỗ trợ. |

Có thể dùng enum cho error code trong hệ thống lớn. Với bài này, chuỗi hằng dễ đọc và dễ kiểm tra. Không nhất thiết đưa toàn bộ giá trị CSV sai vào message của exception: log và báo cáo lỗi cần tuân thủ nguyên tắc bảo vệ dữ liệu.

## 8. Viết `OrderProcessor`: validate và map

Dưới đây là processor thuần Java, không gọi database/HTTP, không lưu trạng thái mutable giữa các item.

Tạo `OrderProcessor.java`:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Set;

import org.springframework.batch.item.ItemProcessor;

public final class OrderProcessor
        implements ItemProcessor<RawOrder, PreparedOrder> {

    private static final Set<String> SUPPORTED_CURRENCIES =
            Set.of("USD", "EUR");

    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000.00");

    @Override
    public PreparedOrder process(RawOrder raw) {
        String sourceKey =
                required(raw.sourceRowId(),
                        "SOURCE_ROW_ID_REQUIRED", "unknown");

        String status = required(
                raw.orderStatus(),
                "ORDER_STATUS_REQUIRED",
                sourceKey).toUpperCase(Locale.ROOT);

        // Quyết định nghiệp vụ: DRAFT chưa được nhập vào hệ thống đích.
        if ("DRAFT".equals(status)) {
            return null; // filter, không phải skip
        }

        if (!"READY".equals(status)) {
            throw invalid("ORDER_STATUS_UNSUPPORTED", sourceKey);
        }

        String orderId = normalizedCode(
                raw.orderId(), "ORDER_ID", sourceKey);

        String customerCode = normalizedCode(
                raw.customerCode(), "CUSTOMER_CODE", sourceKey);

        LocalDate date = parseDate(raw.orderDate(), sourceKey);
        BigDecimal amount = parseAmount(raw.amount(), sourceKey);

        String currency = required(
                raw.currency(),
                "CURRENCY_UNSUPPORTED",
                sourceKey).toUpperCase(Locale.ROOT);

        if (!SUPPORTED_CURRENCIES.contains(currency)) {
            throw invalid("CURRENCY_UNSUPPORTED", sourceKey);
        }

        return new PreparedOrder(
                sourceKey,
                orderId,
                customerCode,
                date,
                amount,
                currency
        );
    }

    private static String required(
            String raw,
            String code,
            String sourceKey) {

        if (raw == null || raw.isBlank()) {
            throw invalid(code, sourceKey);
        }

        return raw.trim();
    }

    private static String normalizedCode(
            String raw,
            String fieldName,
            String sourceKey) {

        String value = required(
                raw,
                fieldName + "_REQUIRED",
                sourceKey).toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]+")) {
            throw invalid(fieldName + "_INVALID", sourceKey);
        }

        return value;
    }

    private static LocalDate parseDate(
            String raw,
            String sourceKey) {

        String value = required(
                raw, "ORDER_DATE_INVALID", sourceKey);

        try {
            return LocalDate.parse(value); // ISO yyyy-MM-dd
        } catch (DateTimeParseException ex) {
            throw invalid("ORDER_DATE_INVALID", sourceKey);
        }
    }

    private static BigDecimal parseAmount(
            String raw,
            String sourceKey) {

        String value = required(
                raw, "AMOUNT_INVALID_FORMAT", sourceKey);

        final BigDecimal amount;
        try {
            amount = new BigDecimal(value);
        } catch (NumberFormatException ex) {
            throw invalid("AMOUNT_INVALID_FORMAT", sourceKey);
        }

        final BigDecimal normalized;
        try {
            normalized = amount.setScale(
                    2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw invalid(
                    "AMOUNT_TOO_MANY_DECIMALS", sourceKey);
        }

        if (normalized.signum() <= 0) {
            throw invalid("AMOUNT_NOT_POSITIVE", sourceKey);
        }

        if (normalized.compareTo(MAX_AMOUNT) > 0) {
            throw invalid("AMOUNT_OUT_OF_RANGE", sourceKey);
        }

        return normalized;
    }

    private static OrderValidationException invalid(
            String code, String sourceKey) {
        return new OrderValidationException(code, sourceKey);
    }
}
```

### Giải thích thứ tự xử lý

1. **Giữ khóa nguồn** để khi xảy ra lỗi có thể biết record nào gặp vấn đề.
2. **Kiểm tra status trước**: bài tập quy định `DRAFT` được filter, nên các field khác của DRAFT không phải kiểm tra như một đơn sẵn sàng.
3. **Kiểm tra status không hỗ trợ** để không vô tình nạp một trạng thái chưa có hợp đồng nghiệp vụ.
4. **Chuẩn hóa ID** bằng `trim` và `toUpperCase(Locale.ROOT)`. Việc dùng `Locale.ROOT` tránh thay đổi cách viết hoa theo locale của JVM.
5. **Parse ngày** bằng `LocalDate.parse` để không có những chuỗi ngày giả như `2026-02-30`.
6. **Parse số tiền** bằng `BigDecimal` và yêu cầu scale 2 chính xác. `RoundingMode.UNNECESSARY` chủ động ném lỗi nếu cần làm tròn.
7. **Kiểm tra currency** theo tập mã đã được bài tập công bố.
8. **Tạo model mới** `PreparedOrder` chỉ khi tất cả điều kiện đã đạt.

**Thứ tự validate là một quyết định nghiệp vụ.** Ở ví dụ này, `DRAFT` được lọc trước khi kiểm tra tiền và ngày. Nếu quy trình yêu cầu phát hiện lỗi chất lượng dữ liệu trên **mọi** dòng (kể cả DRAFT), hãy đổi policy: validate các trường cần đánh giá trước rồi mới filter. Đừng âm thầm thay đổi thứ tự mà không cập nhật số liệu và test.

### Có nên tự động sửa dữ liệu?

Chuẩn hóa khoảng trắng hoặc chữ hoa là một phép biến đổi có thể chấp nhận nếu hợp đồng nghiệp vụ quy định rõ. Ngược lại:

- `12.999` thành `13.00` là thay đổi giá trị tiền; không nên làm tròn tùy tiện.
- Ngày `11/16/2026` không nên tự đoán thành một định dạng khác nếu nguồn đã cam kết ISO.
- Currency `GBP` không nên tự đổi thành `USD`.
- Thiếu customer code không nên tạo một mã ngẫu nhiên.

Quy tắc cơ bản: **normalize thứ có quy tắc xác định, reject thứ thiếu cơ sở xác thực**.

## 9. `return null`, ném exception và lỗi hạ tầng

`ItemProcessor` có ba kết quả quan trọng:

```text
processor.process(rawOrder)
       |
       +-- returns PreparedOrder ---> Writer
       |
       +-- returns null -----------> Filtered item
       |
       +-- throws exception -------> Fault-tolerant policy
                                    |
                                    +-- skip allowed -> skip
                                    +-- retry allowed -> retry
                                    +-- not allowed -> fail
```

| Tình huống | Processor nên làm | Bộ đếm thường liên quan |
| --- | --- | --- |
| `READY` hợp lệ | Trả `PreparedOrder` | `readCount`, sau đó `writeCount` nếu ghi thành công. |
| `DRAFT` chưa cần nhập | Trả `null` | `filterCount`. |
| Số tiền âm | Ném `OrderValidationException` | `processSkipCount` nếu exception được skip. |
| Currency không hỗ trợ | Ném `OrderValidationException` | `processSkipCount` nếu exception được skip. |
| Database không truy cập được | Không biến thành validation exception | Retry/fail theo lỗi hạ tầng. |
| Bug logic bất ngờ | Để fail và được điều tra | Không skip tất cả exception một cách rộng rãi. |

**Không dùng `return null` để che mọi lỗi.** Vì filter không tự tạo `SkipListener` event, một Job có thể báo hoàn thành nhưng âm thầm bỏ nhiều dữ liệu nếu programmer dùng `null` làm kết quả của tất cả lỗi.

Tương tự, không cấu hình `skip(Exception.class)` chỉ để Job luôn có trạng thái `COMPLETED`. Điều đó có thể che lỗi writer/database, sai mapping hoặc sự cố hệ thống.

## 10. Tạo `FlatFileItemReader` cho `RawOrder`

Reader dùng tên cột để map các trường CSV vào model thô. Vì tất cả field đều là `String`, việc convert ngày và tiền xảy ra ở processor.

```java
package example.batch.orders;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

@Configuration
public class OrderReaderConfig {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader() {
        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("orderReader")
                .resource(
                        new ClassPathResource("orders-fixture.csv"))
                .linesToSkip(1)
                .delimited()
                .names(
                        "source_row_id",
                        "order_id",
                        "customer_code",
                        "order_date",
                        "amount",
                        "currency",
                        "order_status")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("source_row_id"),
                        fields.readString("order_id"),
                        fields.readString("customer_code"),
                        fields.readString("order_date"),
                        fields.readString("amount"),
                        fields.readString("currency"),
                        fields.readString("order_status")))
                .build();
    }
}
```

### Vai trò của `@StepScope`

`@StepScope` hữu ích khi reader cần tham số từ `JobParameters` hoặc một nguồn động được chọn ở thời điểm Step chạy. Trong ví dụ reader dùng file cố định để thực hành. Khi đưa lên môi trường thật, nên chọn input bằng một **dataset ID** đã được backend xác nhận, thay vì nhận một đường dẫn file tùy ý từ client.

Ví dụ ý tưởng late binding:

```java
@Value("#{jobParameters['inputDatasetId']}")
String datasetId
```

Sau đó một service tin cậy ánh xạ `datasetId` sang tài nguyên được phép đọc. Không nối trực tiếp giá trị không đáng tin cậy vào một đường dẫn tuyệt đối hoặc URL remote.

### Những lỗi cần xử lý ở reader

- File không tồn tại, không đọc được hoặc encoding sai: có thể làm Job fail.
- Dòng CSV thiếu/thừa cột hoặc dấu nháy hỏng: có thể gây parse error.
- Tên cột không đúng schema: nên fail rõ ràng, không đoán dữ liệu.
- Một cột `amount` là chuỗi `not-a-number`: với reader này vẫn được chuyển vào `RawOrder` để processor quyết định lỗi.

Reader trả về item thô có ý nghĩa giúp phân loại lỗi rõ ràng, nhưng không loại bỏ nhu cầu kiểm tra schema nguồn.

## 11. Tạo bảng đích và `JdbcBatchItemWriter`

Ví dụ schema PostgreSQL:

```sql
CREATE TABLE accepted_order (
    order_id       VARCHAR(64) PRIMARY KEY,
    source_row_id  VARCHAR(128) NOT NULL,
    customer_code  VARCHAR(64) NOT NULL,
    order_date     DATE NOT NULL,
    amount         NUMERIC(18, 2) NOT NULL,
    currency       VARCHAR(3) NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT accepted_order_amount_positive
        CHECK (amount > 0),
    CONSTRAINT accepted_order_currency_allowed
        CHECK (currency IN ('USD', 'EUR'))
);
```

Những constraint ở database **bổ sung lớp bảo vệ**, không thay thế validation ở processor. Ví dụ nếu một lỗi code bypass processor, constraint `amount > 0` vẫn bảo vệ dữ liệu. Tuy nhiên constraint có thể làm transaction writer rollback, nên không nên coi nó là cơ chế báo lỗi chất lượng dữ liệu duy nhất.

Writer dùng JDBC với parameter binding, không ghép giá trị đầu vào trực tiếp vào câu SQL:

```java
package example.batch.orders;

import javax.sql.DataSource;
import java.sql.Date;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration
public class OrderWriterConfig {

    @Bean
    JdbcBatchItemWriter<PreparedOrder> orderWriter(
            DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<PreparedOrder>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO accepted_order (
                        order_id, source_row_id, customer_code,
                        order_date, amount, currency)
                    VALUES (
                        :orderId, :sourceRowId, :customerCode,
                        :orderDate, :amount, :currency)
                    ON CONFLICT (order_id) DO UPDATE SET
                        source_row_id = EXCLUDED.source_row_id,
                        customer_code = EXCLUDED.customer_code,
                        order_date = EXCLUDED.order_date,
                        amount = EXCLUDED.amount,
                        currency = EXCLUDED.currency,
                        updated_at = CURRENT_TIMESTAMP
                    """)
                .itemSqlParameterSourceProvider(order ->
                        new MapSqlParameterSource()
                                .addValue("orderId", order.orderId())
                                .addValue(
                                        "sourceRowId",
                                        order.sourceRowId())
                                .addValue(
                                        "customerCode",
                                        order.customerCode())
                                .addValue(
                                        "orderDate",
                                        Date.valueOf(order.orderDate()))
                                .addValue("amount", order.amount())
                                .addValue("currency", order.currency()))
                .build();
    }
}
```

SQL trên dùng `ON CONFLICT` của PostgreSQL nhằm minh họa cách viết **idempotent upsert** theo `order_id`. Trong dự án thật, cần quyết định rõ khi chạy lại một đơn hàng đã tồn tại:

- **Giữ nguyên**, nếu đây là immutable event.
- **Cập nhật có điều kiện theo version**, nếu dữ liệu được phép sửa.
- **Báo conflict**, nếu bản ghi nguồn mới mâu thuẫn với bản ghi đã commit.
- **Upsert như ví dụ**, chỉ nếu quy tắc nghiệp vụ cho phép ghi đè.

Không sử dụng upsert chỉ để “làm cho Job không bị lỗi” nếu điều đó có thể che mất dữ liệu mâu thuẫn. Với mục tiêu thực hành, lựa chọn này giúp việc chạy lại fixture ít gây trùng khi test chưa dọn bảng đúng cách, nhưng test vẫn cần cô lập dữ liệu.

### Vì sao writer nhận `PreparedOrder`?

Writer không cần biết chuỗi `"not-a-number"` là gì hoặc phân loại mã trạng thái `DRAFT`. Nếu processor trả item, writer có thể tin rằng *những quy tắc đã định nghĩa* được áp dụng. Tất nhiên, writer vẫn cần xử lý lỗi database, ràng buộc khóa duy nhất, timeout và transaction.

## 12. Nối processor vào Step và Job

Tạo configuration cho Step và Job. Các bean reader, processor và writer được truyền bằng dependency injection.

```java
package example.batch.orders;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportJobConfig {

    @Bean
    OrderProcessor orderProcessor() {
        return new OrderProcessor();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            OrderProcessor orderProcessor,
            JdbcBatchItemWriter<PreparedOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<RawOrder, PreparedOrder>chunk(
                        100, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .faultTolerant()
                .skip(OrderValidationException.class)
                .skipLimit(10)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

Đây là cấu hình **Spring Batch 5.x**. Ở phiên bản khác, tên package/constructor và cách đăng ký Job có thể thay đổi.

### Giải thích cấu hình

- `<RawOrder, PreparedOrder>chunk(...)` khai báo rõ kiểu đầu vào và đầu ra trong chu trình.
- `reader(orderReader)` đọc CSV thành `RawOrder`.
- `processor(orderProcessor)` validate và map. Các item `DRAFT` trả `null` được filter.
- `writer(orderWriter)` chỉ nhận `PreparedOrder`.
- `faultTolerant()` bật cơ chế xử lý lỗi của Step.
- `skip(OrderValidationException.class)` chỉ cho phép skip lỗi validation có chủ đích.
- `skipLimit(10)` giới hạn tối đa tổng skip trong Step.

Với fixture 9 dòng có 5 process skip, Step vẫn nằm trong giới hạn. Khi số skip vượt ngưỡng, Step có thể fail thay vì lặng lẽ bỏ thêm dữ liệu.

### Có cần `skip(FlatFileParseException.class)` không?

Không bắt buộc. Bài thực hành này cố ý **không** bỏ qua lỗi đọc CSV sai cấu trúc để phân biệt:

- **Dữ liệu nghiệp vụ sai** như số tiền không hợp lệ: đưa vào `RawOrder` rồi skip ở processor.
- **Định dạng nguồn/schema hỏng** như thiếu cột quan trọng: ưu tiên fail để điều tra.

Nếu nghiệp vụ cho phép skip từng dòng CSV bị hỏng, có thể bổ sung `skip(FlatFileParseException.class)` cùng quy tắc báo cáo read skip, nhưng phải kiểm tra rằng reader vẫn có thể tiếp tục đến dòng sau một cách an toàn.

## 13. Xem kết quả trong `StepExecution`

Sau khi Job chạy xong, `JobExecution` và `StepExecution` cho biết số lượng đã đọc, lọc, skip và ghi.

Với fixture ở mục 3, kỳ vọng:

```text
Job: importOrdersJob
Status: COMPLETED

Step: importOrdersStep
readCount         = 9
writeCount        = 3
filterCount       = 1
readSkipCount     = 0
processSkipCount  = 5
writeSkipCount    = 0
skipCount         = 5
```

Các số này dựa trên đường đi của ví dụ: tất cả 9 dòng CSV được reader map thành `RawOrder`; 1 dòng bị filter; 5 dòng ném `OrderValidationException` và được skip; 3 dòng được ghi thành công.

### Những hiểu nhầm về counters

- **`readCount`** không nhất thiết bằng số dòng vật lý trong file đối với mọi reader; header, multiline record và read skip có thể ảnh hưởng.
- **`filterCount`** khác **`processSkipCount`**. Filter thường là một quyết định hợp lệ, còn skip là xử lý lỗi theo policy.
- **`writeCount`** không luôn bằng `readCount` do filter, skip hoặc flow.
- Trong trường hợp retry/rollback, số lần callback processor chạy không phải lúc nào cũng bằng số item unique hoặc số dòng log.
- `BatchStatus.COMPLETED` không bảo đảm mọi input được chấp nhận; còn phải xem chất lượng dữ liệu và bộ đếm.

Đối với một quy trình data quality nghiêm ngặt, có thể thêm quality gate: nếu quá nhiều item bị skip, Job sẽ bị đánh dấu không đạt tiêu chí ngay cả khi tổng skip vẫn dưới `skipLimit`. Ngưỡng này phải được định nghĩa theo số dòng và tỷ lệ lỗi nghiệp vụ cụ thể.

## 14. Báo cáo lỗi validation qua `SkipListener`

Chỉ tăng `processSkipCount` chưa đủ nếu người vận hành cần biết bản ghi nào bị loại. Spring Batch cung cấp `SkipListener<I, O>` để nhận sự kiện khi một item đã được quyết định skip.

Ví dụ đơn giản ghi log **mã lỗi và khóa nguồn**, không log toàn bộ nội dung thô:

```java
package example.batch.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipLoggingListener
        implements SkipListener<RawOrder, PreparedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipLoggingListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        // Lỗi READ có thể chưa có RawOrder được tạo.
        log.warn(
                "batch.order.skip phase=READ exceptionType={}",
                error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            RawOrder raw,
            Throwable error) {

        if (error instanceof OrderValidationException validation) {
            log.warn(
                    "batch.order.skip phase=PROCESS "
                        + "sourceRowId={} errorCode={}",
                    validation.getSourceRowId(),
                    validation.getErrorCode());
        } else {
            log.warn(
                    "batch.order.skip phase=PROCESS "
                        + "sourceRowId={} exceptionType={}",
                    raw.sourceRowId(),
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onSkipInWrite(
            PreparedOrder order,
            Throwable error) {

        log.warn(
                "batch.order.skip phase=WRITE "
                    + "sourceRowId={} exceptionType={}",
                order.sourceRowId(),
                error.getClass().getSimpleName());
    }
}
```

Đăng ký bean và gắn vào Step:

```java
@Bean
OrderSkipLoggingListener orderSkipLoggingListener() {
    return new OrderSkipLoggingListener();
}

// Trong chuỗi StepBuilder sau .skipLimit(10):
.listener(orderSkipLoggingListener)
```

Nếu chỉ tạo Spring bean mà không gắn listener vào Step, không nên mặc định callback sẽ được gọi.

### Lưu rejected item lâu dài

Đối với dự án cần xử lý lại dữ liệu lỗi, nên thiết kế một bảng/luồng báo cáo có:

```text
jobExecutionId
stepExecutionId
sourceDatasetId
sourceRowId
phase = READ | PROCESS | WRITE
errorCode
reportedAt
resolutionStatus
```

Có thể ghi báo cáo qua JDBC từ `SkipListener` bằng một sink được thiết kế nhất quán transaction. Với Step chunk-oriented, các callback skip được Spring Batch tổ chức trong quy trình fault-tolerant processing; cần cân nhắc rằng rollback/retry hoặc báo cáo ở **datasource khác** có thể làm số record báo cáo và skip count chưa đồng nhất nếu không xử lý dedup.

Không gửi HTTP hoặc email trực tiếp cho từng item lỗi trong listener nếu việc đó tạo side effect không thể rollback và làm chậm chunk. Nếu cần thông báo, có thể ghi outbox trong transaction phù hợp rồi xuất sự kiện ở worker riêng.

### Không coi filter là rejected item nếu chưa được yêu cầu

`DRAFT` trong bài này được filter, không phát ra `onSkipInProcess`. Nếu nghiệp vụ muốn báo cáo cả các dòng DRAFT, có thể bổ sung một luồng ghi nhận filtered item riêng hoặc đổi hợp đồng “DRAFT không hợp lệ” thành validation exception. Chọn một ý nghĩa nhất quán; không trộn `filterCount` vào `skipCount` trong dashboard.

## 15. Unit test processor: kiểm tra quy tắc không cần Spring Context

Phần lớn lỗi validation/map nên được phát hiện bằng unit test đơn giản. Vì `OrderProcessor` là class thuần, có thể gọi `process(...)` trực tiếp mà không cần `@SpringBootTest` hay database.

Ví dụ JUnit Jupiter và AssertJ:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void mapsAndNormalizesReadyOrder() {
        RawOrder raw = new RawOrder(
                " r-01 ",
                " ord-1001 ",
                " cus-01 ",
                "2026-11-16",
                " 125.50 ",
                " usd ",
                " ready ");

        PreparedOrder actual = processor.process(raw);

        assertThat(actual).isEqualTo(new PreparedOrder(
                "r-01",
                "ORD-1001",
                "CUS-01",
                LocalDate.of(2026, 11, 16),
                new BigDecimal("125.50"),
                "USD"));
    }

    @Test
    void draftOrderIsFiltered() {
        RawOrder draft = new RawOrder(
                "r-03", "ord-1003", "cus-03",
                "2026-11-16", "45.00", "EUR", "DRAFT");

        assertThat(processor.process(draft)).isNull();
    }

    @Test
    void rejectsNonPositiveAmount() {
        RawOrder raw = readyOrder("0");

        assertThatThrownBy(() -> processor.process(raw))
                .isInstanceOf(OrderValidationException.class)
                .satisfies(error -> assertThat(
                        ((OrderValidationException) error)
                                .getErrorCode())
                        .isEqualTo("AMOUNT_NOT_POSITIVE"));
    }

    @Test
    void rejectsAmountWithExcessPrecision() {
        RawOrder raw = readyOrder("12.999");

        assertThatThrownBy(() -> processor.process(raw))
                .isInstanceOf(OrderValidationException.class)
                .satisfies(error -> assertThat(
                        ((OrderValidationException) error)
                                .getErrorCode())
                        .isEqualTo("AMOUNT_TOO_MANY_DECIMALS"));
    }

    @Test
    void rejectsUnsupportedCurrency() {
        RawOrder raw = new RawOrder(
                "r-08", "ord-1008", "cus-08",
                "2026-11-16", "40.00", "GBP", "READY");

        assertThatThrownBy(() -> processor.process(raw))
                .isInstanceOf(OrderValidationException.class)
                .satisfies(error -> assertThat(
                        ((OrderValidationException) error)
                                .getErrorCode())
                        .isEqualTo("CURRENCY_UNSUPPORTED"));
    }

    private static RawOrder readyOrder(String amount) {
        return new RawOrder(
                "r-test", "ord-test", "cus-test",
                "2026-11-16", amount, "USD", "READY");
    }
}
```

Đây là tập test đại diện. Có thể thêm test cho `order_date=2026-02-30`, customer code thiếu, status không hỗ trợ, amount không phải số, amount vượt giới hạn và ID chứa ký tự không hợp lệ.

### Boundary testing rất quan trọng

Một vài giá trị nên thử:

| Field | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| `amount` | `0.01` | Hợp lệ. |
| `amount` | `0` hoặc `-0.01` | `AMOUNT_NOT_POSITIVE`. |
| `amount` | `1000000.00` | Hợp lệ theo giới hạn bài tập. |
| `amount` | `1000000.01` | `AMOUNT_OUT_OF_RANGE`. |
| `amount` | `1.2` | Chuẩn hóa thành `1.20`. |
| `amount` | `1.234` | `AMOUNT_TOO_MANY_DECIMALS`. |
| `amount` | `abc` | `AMOUNT_INVALID_FORMAT`. |
| `order_date` | `2026-02-28` | Hợp lệ. |
| `order_date` | `2026-02-30` | `ORDER_DATE_INVALID`. |
| `order_status` | `draft` | Filter sau chuẩn hóa. |
| `order_status` | `UNKNOWN` | `ORDER_STATUS_UNSUPPORTED`. |
| `currency` | ` usd ` | Map thành `USD`. |
| `currency` | `gbp` | `CURRENCY_UNSUPPORTED` trong bài tập. |

Nên dùng `@ParameterizedTest` cho nhiều bộ input, nhưng vẫn giữ những ca quan trọng đọc được và có `errorCode` rõ ràng khi thất bại.

## 16. Integration test: chạy Reader → Processor → Writer

Unit test chỉ chứng minh logic processor. Integration test xác nhận cấu hình Step thực sự sử dụng processor, skip policy được áp dụng, số liệu Step chính xác và writer nhận đúng model.

Với Spring Batch 5.x, `spring-batch-test` cung cấp `@SpringBatchTest`, `JobLauncherTestUtils` và `JobRepositoryTestUtils`.

Ví dụ:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderImportIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job job;

    @BeforeEach
    void resetFixture() {
        // Chỉ xóa dữ liệu trong DB/schema test riêng.
        jdbcTemplate.update("DELETE FROM accepted_order");
        jobRepositoryTestUtils.removeJobExecutions();
        jobLauncherTestUtils.setJob(job);
    }

    @Test
    void validatesFiltersAndWritesPreparedOrders()
            throws Exception {

        var parameters = new JobParametersBuilder()
                .addString(
                        "testRunId",
                        UUID.randomUUID().toString(),
                        true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        StepExecution step = execution.getStepExecutions().stream()
                .filter(value -> "importOrdersStep".equals(
                        value.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(step.getReadCount()).isEqualTo(9);
        assertThat(step.getWriteCount()).isEqualTo(3);
        assertThat(step.getFilterCount()).isEqualTo(1);
        assertThat(step.getReadSkipCount()).isZero();
        assertThat(step.getProcessSkipCount()).isEqualTo(5);
        assertThat(step.getWriteSkipCount()).isZero();
        assertThat(step.getSkipCount()).isEqualTo(5);

        Integer numberOfOrders = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM accepted_order",
                Integer.class);

        assertThat(numberOfOrders).isEqualTo(3);

        String customerCode = jdbcTemplate.queryForObject(
                """
                SELECT customer_code
                  FROM accepted_order
                 WHERE order_id = ?
                """,
                String.class,
                "ORD-1001");

        assertThat(customerCode).isEqualTo("CUS-01");

        BigDecimal amount = jdbcTemplate.queryForObject(
                """
                SELECT amount
                  FROM accepted_order
                 WHERE order_id = ?
                """,
                BigDecimal.class,
                "ORD-1001");

        assertThat(amount)
                .isEqualByComparingTo(new BigDecimal("125.50"));
    }
}
```

### Điều kiện của integration test

- `src/test/resources/orders-fixture.csv` tồn tại và đúng 9 dòng dữ liệu được mô tả.
- Spring Boot nạp được Job và các bean reader/processor/writer.
- `accepted_order` và schema metadata Spring Batch đã được tạo trong database **test**, không phải production.
- `JobLauncherTestUtils` thực thi Job đồng bộ trong phép test, hoặc test phải đợi trạng thái cuối nếu launcher bất đồng bộ.
- Các test không dùng chung bảng khi chạy song song mà không cô lập, vì `DELETE` trong `@BeforeEach` có thể xóa dữ liệu của test khác.
- Job không tự động khởi chạy khi tạo context do `spring.batch.job.enabled=false`.
- Writer upsert theo `order_id` như ví dụ, không có trigger DB phụ làm thay đổi số bản ghi.

Nếu cần isolation mạnh hơn, dùng database/schema riêng cho test hoặc Testcontainers. `@Transactional` ở method test không mặc định rollback các transaction mà Spring Batch mở và commit trong Step.

### Cần assert dữ liệu, không chỉ counters

Một Step có thể có `writeCount=3` nhưng writer map sai customer, date hoặc currency. Vì vậy integration test nên truy vấn một hoặc nhiều record đích để chứng minh mapping đúng và kiểm tra không có business key trùng.

Nếu ứng dụng không cho phép upsert và writer dùng INSERT thông thường, cần kiểm tra hành vi xung đột khóa duy nhất theo hợp đồng nghiệp vụ thật.

## 17. Test vượt `skipLimit` và lỗi không được skip

### 17.1. Vượt giới hạn

Cấu hình `skipLimit(2)` nhưng file có ít nhất ba item gây `OrderValidationException`. Khi Spring Batch cần skip vượt giới hạn, Step chuyển sang lỗi và Job thường `FAILED` theo flow.

Test cần assert:

- `JobExecution.getStatus() == BatchStatus.FAILED`.
- Metadata Step có thông tin failure.
- Những chunk đã commit trước khi lỗi **có thể còn dữ liệu**.
- Không mặc định mọi record phía sau lỗi đều đã được đọc hoặc xử lý.

Đây là cơ chế ngăn việc “Job báo thành công dù nguồn lỗi hàng loạt”.

### 17.2. Lỗi không skippable

Cho writer gặp lỗi database, ví dụ mất kết nối hoặc schema không tồn tại. Vì Step chỉ cấu hình skip `OrderValidationException`, lỗi hạ tầng không được chuyển thành “bad order” rồi bỏ qua.

**Nguyên tắc:** lỗi dữ liệu của một item và lỗi khiến hạ tầng không xử lý được là hai loại khác nhau. Không nên ép mọi exception thành `OrderValidationException` trong một `catch(Exception e)` rộng.

### 17.3. Lỗi đọc nguồn

Nếu CSV thiếu cột, có thể phát sinh `FlatFileParseException` trước khi processor được gọi. Đó không phải `processSkipCount`. Cần có test riêng nếu dữ liệu nguồn có thể bị hỏng cấu trúc; policy nên xác định khi nào skip read error và khi nào dừng toàn Job.

## 18. Mapping nâng cao: composite processor

Nếu logic validation và mapping ngày càng lớn, có thể tách thành các processor nhỏ:

```text
RawOrder
   |
   v
NormalizeProcessor
   |
   v
ValidationProcessor
   |
   v
MapToPreparedOrderProcessor
   |
   v
PreparedOrder
```

Spring Batch có `CompositeItemProcessor` để nối các delegate theo thứ tự. Đây là lựa chọn khi từng giai đoạn cần tái sử dụng hoặc test riêng.

Ví dụ cấu trúc:

```java
@Bean
CompositeItemProcessor<RawOrder, PreparedOrder>
compositeOrderProcessor(
        ItemProcessor<RawOrder, NormalizedRawOrder> normalizer,
        ItemProcessor<NormalizedRawOrder, PreparedOrder>
                validatorAndMapper) {

    var composite =
            new CompositeItemProcessor<RawOrder, PreparedOrder>();

    composite.setDelegates(
            java.util.List.of(normalizer, validatorAndMapper));

    return composite;
}
```

`NormalizedRawOrder` là **kiểu trung gian do ứng dụng tự định nghĩa**; muốn chạy ví dụ này phải tạo class đó cùng các delegate. Đoạn mã minh họa cơ chế tổ chức, không phải bản thay thế trực tiếp của `OrderProcessor` đã triển khai ở trên.

### Lưu ý khi dùng composite

- Nếu một delegate trả `null`, item bị filter theo hợp đồng processor; các delegate tiếp theo không nên nhận một item đã bị loại.
- Exception do bất kỳ delegate nào ném sẽ được Step xử lý theo skip/retry policy chung.
- Nếu một delegate có state mutable, không tự động an toàn khi Step chạy đa luồng.
- Dùng composite khi nó làm code dễ hiểu hơn; với bài toán nhỏ, một processor thuần với helper methods thường đơn giản hơn.

## 19. Có nên dùng Jakarta Bean Validation?

Với model có nhiều constraint dạng khai báo, có thể dùng **Jakarta Bean Validation**:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.DecimalMin;

public record OrderCandidate(
        @NotBlank String orderId,
        @NotBlank String customerCode,
        @NotNull java.time.LocalDate orderDate,
        @NotNull @DecimalMin("0.01")
        java.math.BigDecimal amount) {
}
```

Spring Batch có các processor/validator hỗ trợ kiểm tra bean, ví dụ `BeanValidatingItemProcessor` hoặc `ValidatingItemProcessor` với validator tương ứng, tùy phiên bản. Một luồng có thể là:

```text
RawOrder
   |
   v
Map sang OrderCandidate có typed fields
   |
   v
Bean Validation
   |
   v
PreparedOrder
```

Bean Validation hữu ích cho các constraint như `@NotNull`, `@Size`, `@Pattern`, `@DecimalMin`. Nhưng nó không thay thế mọi logic nghiệp vụ:

- Parse ngày/số tiền từ raw text vẫn cần xử lý rõ ràng.
- Chính sách `DRAFT` được filter cần quyết định cụ thể.
- Tập currency cho phép có thể phụ thuộc phiên bản hợp đồng.
- Một số kiểm tra cần dữ liệu tham chiếu đã được snapshot.
- Kiểm tra duplicate/order đã tồn tại cần transaction và idempotency ở writer/database.

Nếu dùng processor validator có chế độ **filter invalid bean** thay vì ném lỗi, cần hiểu rằng nó có thể làm những bản ghi không hợp lệ trở thành filtered items thay vì skipped items. Chọn chính sách dựa trên yêu cầu báo cáo data quality.

## 20. Tránh gọi remote service trong processor của chunk

Một anti-pattern thường gặp:

```java
@Override
public PreparedOrder process(RawOrder raw) {
    // Ví dụ không nên dùng mặc định:
    Customer customer = remoteCustomerApi.get(raw.customerCode());
    ...
}
```

Với chunk-oriented Step, processor thường được gọi trong transaction của chunk. Nếu mỗi item gọi HTTP, transaction có thể tồn tại lâu, giữ connection/lock và gặp retry/rollback. Một lookup từ xa cũng có thể trả kết quả khác nhau giữa lần đầu và lần restart.

Các hướng thay thế:

1. **Prefetch reference data** trong một giai đoạn riêng, lưu snapshot theo `JobInstance` hoặc business date.
2. **Tra bảng local/staging** đã được chuẩn bị trước khi Step chạy.
3. **Dùng cache có version/TTL rõ ràng** nếu dữ liệu ít thay đổi và restart semantics cho phép.
4. Với remote operation có side effect, **ghi ý định bền vững vào outbox** và dùng dispatcher riêng sau commit.

Nếu không thể tránh remote lookup trong processor, phải cấu hình timeout, retry có giới hạn, quan sát transaction duration và kiểm tra khả năng xử lý lại. Nhưng đây không nên là cách mặc định cho bài toán chỉ cần chuẩn hóa/validate/map CSV.

## 21. Tính đúng đắn khi restart Job

Một Job có thể fail sau khi vài chunk đã commit. Khi restart cùng `JobInstance`, Spring Batch dựa vào metadata và execution context để tiếp tục theo khả năng của reader/Step.

Với processor, những nguyên tắc quan trọng:

- **Deterministic:** cùng raw item và cùng rules version nên cho cùng `PreparedOrder` hoặc cùng error code.
- **Stateless:** không lưu counter/current item vào field mutable của singleton processor nếu không quản lý state rõ ràng.
- **Không side effect:** không gửi email, HTTP POST hoặc cập nhật database ngay trong `process()`.
- **Reference data có version:** nếu validation dựa vào quy tắc thay đổi theo thời gian, cố định version/dataset khi cần kết quả restart tái lập.
- **Writer idempotent theo hợp đồng:** các chunk được xử lý lại không được gây dữ liệu trùng hoặc biến đổi sai.
- **Giữ metadata:** không xóa `BATCH_JOB_EXECUTION`/`ExecutionContext` giữa lần fail và restart.

### Ví dụ mapping không deterministic

```java
return new PreparedOrder(
    raw.sourceRowId(),
    raw.orderId(),
    raw.customerCode(),
    LocalDate.now(),   // Không ổn nếu ngày phải đến từ dữ liệu nguồn.
    ...
);
```

Ngày do đồng hồ hiện tại có thể đổi khi restart. Nếu nghiệp vụ cần ngày xử lý, hãy nhận nó từ CSV hoặc từ **identifying JobParameters** đã được xác định rõ, thay vì gọi `LocalDate.now()` cho mỗi item.

Tương tự, sinh UUID mới trong processor mỗi lần gọi có thể khiến writer tạo bản ghi mới khi retry. Cần khóa nghiệp vụ ổn định hoặc tạo ID một lần và lưu bền vững.

## 22. Thread safety và hiệu năng của processor

`OrderProcessor` trong bài dùng các hằng immutable (`Set.of`, `BigDecimal`), biến cục bộ và đối tượng kết quả mới nên phù hợp để sử dụng trong những tình huống nhiều thread gọi đồng thời, với giả định các thư viện dùng trong helper là thread-safe như ở đây.

Không nên viết:

```java
public class UnsafeProcessor
        implements ItemProcessor<RawOrder, PreparedOrder> {

    private String currentOrderId; // mutable shared state

    @Override
    public PreparedOrder process(RawOrder item) {
        currentOrderId = item.orderId();
        // Thread khác có thể ghi đè currentOrderId.
        ...
    }
}
```

Khi Step dùng `TaskExecutor` hoặc partitioning, cùng một instance processor có thể bị nhiều thread truy cập tùy cấu hình bean. Hãy giữ processor **stateless**, hoặc dùng state isolation rõ ràng và thread-safe.

### Performance

Các thao tác trim, uppercase, parse ngày và `BigDecimal` thường rẻ hơn round-trip tới database/HTTP. Tuy nhiên với hàng triệu item:

- Regex `String.matches` có chi phí tạo/kiểm tra pattern; nếu cần tối ưu, có thể precompile `Pattern` immutable.
- Tránh format/parse qua lại không cần thiết.
- Không ghi log INFO cho từng item hợp lệ.
- Không gọi database để kiểm tra duplicate cho từng item nếu có thể dùng constraint/batch lookup.
- Đo throughput và GC trước khi tối ưu; không thay đổi rule để “benchmark nhanh hơn”.

Việc tăng thread count có thể không cải thiện nếu writer/database đang nghẽn. Trước khi scale multi-threaded Step, cần chắc chắn reader và writer an toàn theo cấu hình concurrency đó.

## 23. Logging và báo cáo chất lượng dữ liệu

Một Job có thể kết thúc `COMPLETED` nhưng đã skip 5/9 bản ghi. Trong môi trường production, tỷ lệ này có thể không chấp nhận được.

Nên phân biệt:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `BatchStatus` | Job/Step hoàn thành theo chính sách thực thi hay không. |
| `readCount` | Số item reader trả thành công. |
| `filterCount` | Những item được loại theo quy tắc hợp lệ. |
| `processSkipCount` | Những item có exception ở processor được skip. |
| `writeCount` | Số item writer ghi theo thống kê Step. |
| `errorCode` | Phân loại lý do item bị loại, phục vụ sửa dữ liệu. |
| `sourceDatasetId` / `sourceRowId` | Dùng để đối chiếu với nguồn. |
| `jobInstanceId` / `jobExecutionId` | Liên kết với lịch sử restart và metadata. |

Một báo cáo có thể là:

```json
{
  "jobName": "importOrdersJob",
  "jobExecutionId": 811,
  "dataset": "orders-fixture",
  "status": "COMPLETED",
  "readCount": 9,
  "writeCount": 3,
  "filterCount": 1,
  "readSkipCount": 0,
  "processSkipCount": 5,
  "writeSkipCount": 0,
  "totalSkipCount": 5
}
```

Số liệu trên là fixture minh họa. Trong production, không nên dùng mỗi `jobExecutionId` làm tag metric vì giá trị mới được tạo liên tục, gây cardinality cao. Có thể log ID để tra cứu chi tiết, còn metrics gắn nhãn `jobName`, `stepName`, `status` và các error code hữu hạn.

Nếu quy trình có quality gate, có thể đặt ngưỡng tổng skip và/hoặc tỷ lệ lỗi, nhưng phải xác định rõ mẫu số: số bản ghi vật lý, số item đọc thành công hay số input trong manifest. Đừng suy luận số dòng vật lý của mọi file chỉ từ `readCount`.

## 24. Những lỗi thường gặp khi thêm processor

### 24.1. Quên gắn processor vào Step

Việc khai báo bean `OrderProcessor` chưa đủ:

```java
.reader(orderReader)
// thiếu .processor(orderProcessor)
.writer(orderWriter)
```

Nếu Step có kiểu generic đầu ra phù hợp hoặc dùng raw types, luồng có thể chạy mà không áp dụng validation/map như mong đợi. Cần gắn `.processor(...)` và test dữ liệu output.

### 24.2. Dùng chung một model cho raw và prepared

Nếu model có `amount: BigDecimal` ngay tại reader, dữ liệu `not-a-number` lỗi trước khi processor có cơ hội phân loại. Đây không luôn sai, nhưng khác mục tiêu “processor validate/map” của bài này. Hãy chọn rõ lớp chịu trách nhiệm parse và error reporting.

### 24.3. Dùng `double` để parse tiền

Dễ tạo sai số và không có chính sách scale rõ ràng. Ưu tiên `BigDecimal`, xác định giới hạn và quy tắc rounding/reject.

### 24.4. Sửa input mutable trong processor

Việc thay đổi đối tượng đầu vào có thể ảnh hưởng retry, caching hoặc những component khác. Trả model mới immutable giúp giảm side effect và đơn giản hóa unit test.

### 24.5. Trả `null` cho mọi lỗi

Điều này biến lỗi dữ liệu thành filter, không tăng `skipCount` hoặc gọi `SkipListener`. Phải tách đúng “không thuộc phạm vi xử lý” và “dữ liệu không hợp lệ”.

### 24.6. Bắt mọi exception rồi biến thành lỗi dữ liệu

Ví dụ:

```java
try {
    ...
} catch (Exception ex) {
    throw new OrderValidationException("INVALID_ORDER", sourceId);
}
```

Cách này có thể che bug lập trình hoặc lỗi hạ tầng. Chỉ bắt những exception có nghĩa rõ ràng như `NumberFormatException` và `DateTimeParseException` tại đúng điểm parse.

### 24.7. Không quy định thứ tự filter/validate

Một record `DRAFT` có dữ liệu không hợp lệ sẽ được filter hay skip? Cả hai có thể là policy hợp lệ nhưng phải được xác định trước. Trong bài này `DRAFT` được filter sau khi validate source key và status; các field còn lại không cần hợp lệ.

### 24.8. Cho rằng `skipLimit` giới hạn riêng từng giai đoạn

`skipLimit(10)` mặc định là giới hạn tổng số skip ở Step, bao gồm read/process/write. Nó không cấp 10 lượt cho mỗi loại. Nếu cần quy tắc tùy biến, dùng `SkipPolicy` với hợp đồng rõ ràng.

### 24.9. Dựa vào database constraint để thay thế validation

Constraint là lớp bảo vệ cuối nhưng lỗi writer có thể làm rollback cả chunk. Processor nên phát hiện lỗi thuộc phạm vi có thể xác định trước, giúp cung cấp error code và dữ liệu báo cáo rõ ràng.

### 24.10. Quên idempotency khi chạy lại

Nếu writer luôn insert với khóa mới, restart có thể ghi trùng. Thiết kế khóa nghiệp vụ và xử lý xung đột phù hợp; đừng dùng random ID trong processor cho record đáng lẽ có identity ổn định.

### 24.11. Ghi toàn bộ dữ liệu thô vào log

CSV có thể chứa email, số điện thoại, địa chỉ hoặc PII. Log `sourceRowId` và error code đã được phép; giữ raw payload ở vùng quarantine bảo mật nếu thực sự cần.

### 24.12. Chỉ kiểm tra Job `COMPLETED`

Job có thể hoàn thành dù đã filter/skip số lượng lớn. Unit test processor, Step counters, rejection report và dữ liệu thực tế ở writer đều cần được kiểm tra ở mức phù hợp.

## 25. Bài tập mở rộng: thêm quy tắc nghiệp vụ mới

Sau khi chạy được ví dụ, thực hiện các yêu cầu:

### Bài tập A – Validation theo ngày nghiệp vụ

Job nhận `businessDate` từ `JobParameters`. Chỉ những đơn có `order_date <= businessDate` mới hợp lệ.

- Xác định `businessDate` là identifying parameter nếu nó đại diện cho đơn vị công việc.
- Dùng `@StepScope` hoặc một component được cấu hình theo execution để đưa ngày vào processor.
- Không dùng `LocalDate.now()` cho từng item.
- Thêm error code `ORDER_DATE_AFTER_BUSINESS_DATE`.
- Test một ngày bằng, một ngày trước và một ngày sau mốc.

### Bài tập B – Tách filter và rejection report

Thêm trạng thái `CANCELLED` được filter giống DRAFT, nhưng cần tổng hợp cả số lượng theo từng lý do filter.

- Thiết kế bộ đếm filter có ý nghĩa nghiệp vụ.
- Không gọi `onSkipInProcess` cho filtered item theo mặc định.
- Nếu cần lưu log audit, không tạo side effect không idempotent trong `process()`.
- Assert `filterCount` và `processSkipCount` độc lập.

### Bài tập C – Duplicate order

Hai dòng CSV có cùng `order_id` nhưng `amount` khác nhau.

- Xác định xem đây là lỗi data quality hay bản cập nhật hợp lệ.
- Không cố giải quyết bằng `Set` mutable trong singleton processor nếu Step có concurrency/restart.
- Cân nhắc unique constraint, staging table và policy theo version.
- Test trường hợp dữ liệu không mâu thuẫn và dữ liệu mâu thuẫn.

### Bài tập D – Tăng giới hạn chất lượng

Thử fixture chứa 50 bản ghi lỗi trên 100 dòng với `skipLimit(10)`.

- Dự đoán trạng thái Step khi vượt giới hạn.
- Kiểm tra dữ liệu đã commit ở các chunk trước.
- Xác nhận báo cáo chỉ có những rejection đã được ghi bền vững.
- Thêm quality gate theo tỷ lệ, với mẫu số lấy từ manifest đầu vào.

### Bài tập E – Restart

Cố ý gây lỗi writer sau một hoặc nhiều chunk.

- Giữ nguyên identifying JobParameters khi restart.
- Không xóa metadata ở giữa hai lần chạy.
- Đảm bảo processor cho kết quả deterministic.
- Xác minh không có đơn trùng sau khi restart.
- Đối chiếu `JobInstance` và hai `JobExecution` khác nhau trong metadata.

## 26. Bản đồ triển khai cho dự án

Một cấu trúc file có thể tổ chức như sau:

```text
src/
├── main/
│   └── java/example/batch/orders/
│       ├── RawOrder.java
│       ├── PreparedOrder.java
│       ├── OrderValidationException.java
│       ├── OrderProcessor.java
│       ├── OrderReaderConfig.java
│       ├── OrderWriterConfig.java
│       ├── OrderImportJobConfig.java
│       └── OrderSkipLoggingListener.java
└── test/
    ├── java/example/batch/orders/
    │   ├── OrderProcessorTest.java
    │   └── OrderImportIT.java
    └── resources/
        └── orders-fixture.csv
```

Các lớp trong cấu trúc là ví dụ để định hướng tổ chức. Dự án thực tế có thể tách module `batch-domain`, `batch-infrastructure` và `batch-application` hoặc sử dụng package theo feature.

Trình tự xây dựng đề xuất:

1. Chốt hợp đồng input CSV và trạng thái nghiệp vụ.
2. Tạo `RawOrder` và `PreparedOrder`.
3. Tạo exception chứa `errorCode`.
4. Viết processor thuần và unit test.
5. Tạo reader map String, không parse dữ liệu nghiệp vụ quá sớm.
6. Tạo writer với parameter binding và constraint.
7. Lắp Job/Step và chọn skip policy.
8. Gắn `SkipListener` cho lỗi dữ liệu cần truy vết.
9. Chạy integration test trên DB riêng, so sánh counters với bảng đích.
10. Thử lỗi biên, retry/restart và trường hợp vượt skip limit.
11. Thử dataset lớn hơn, theo dõi throughput và chất lượng dữ liệu.
12. Chốt quy trình xử lý/reprocess rejected item trước khi đưa Job vào lịch thực tế.

**Kết quả hoàn chỉnh của bài thực hành** không chỉ là một class `ItemProcessor` có thể compile. Đó là một pipeline có hợp đồng rõ ràng: nguồn dữ liệu nào được đọc, cách bản ghi được chuẩn hóa, điều kiện được nhận/lọc/từ chối, dữ liệu đã chuẩn hóa được ghi ra sao và người vận hành biết kết quả qua những chỉ số nào.

## Tài liệu tham khảo

- [Spring Batch Reference – Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): nguyên tắc `ItemProcessor<I, O>`, filtering và biến đổi item.
- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vòng đời read, process, write và transaction.
- [Spring Batch Reference – Flat File Item Readers](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): cấu hình `FlatFileItemReader` cho CSV và các nguồn text.
- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): fault-tolerant Step, `skipLimit` và các exception được phép skip.
- [Spring Batch Reference – Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `SkipListener` và các listener liên quan.
- [Spring Batch Reference – Bean Validation](https://docs.spring.io/spring-batch/reference/processor.html): các cách validation trong processing pipeline.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): `spring-batch-test`, chạy Job/Step và xác nhận kết quả.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): nguyên tắc transaction và propagation.

