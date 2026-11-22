# Data type và format validation trong Spring Batch Core Processing

Một batch job có thể đọc hết file và báo `COMPLETED` nhưng dữ liệu đầu ra vẫn sai: ngày `2026-02-30` được tự động sửa thành ngày khác, `1,234` bị hiểu nhầm là số thập phân hay số có dấu phân nhóm, mã định danh `000123` bị mất số 0 đầu hoặc giá tiền bị làm tròn mà người cung cấp không biết. **Data type và format validation** là việc xác nhận dữ liệu đầu vào tuân thủ hợp đồng kiểu dữ liệu, cú pháp, độ chính xác và cách biểu diễn trước khi chuyển thành đối tượng nghiệp vụ.

Trong Spring Batch, cần quyết định **kiểm tra ở đâu** trên tuyến `ItemReader → ItemProcessor → ItemWriter`, lỗi nào khiến job thất bại, lỗi nào được phép skip, cách thống kê bản ghi sai và cách giữ kết quả nhất quán khi restart. Bài này giải thích những lựa chọn đó qua ví dụ CSV nhập đơn hàng, sử dụng **Spring Batch 5.2.x, Spring Framework 6.x và Java 17** làm mốc cho các ví dụ Java.

## 1. Phân biệt ba mức validation

| Mức | Kiểm tra điều gì? | Ví dụ lỗi | Vị trí phù hợp |
| --- | --- | --- | --- |
| **Structure / schema** | Encoding, header, số cột, thứ tự, delimiter, schema version | Thiếu cột `quantity`, một dòng CSV có 5 trường thay vì 4 | Preflight, `LineTokenizer`, `ItemReader` |
| **Data type / format** | Giá trị text có thể parse chính xác thành kiểu Java theo một format đã công bố không? | `quantity=three`, `businessDate=2026-02-30`, `unitPrice=12.345` | `FieldSetMapper` hoặc `ItemProcessor` |
| **Domain / semantic** | Giá trị đúng kiểu có thỏa mãn quy tắc nghiệp vụ không? | `quantity=0`, đơn hàng đã tồn tại, ngày ngoài kỳ xử lý | `ItemProcessor`, validator nghiệp vụ, database constraint |

Ví dụ `2026-11-15` là ngày hợp lệ về kiểu và format nhưng có thể sai kỳ nghiệp vụ nếu job chỉ nhận dữ liệu ngày `2026-11-14`. Ngược lại, `2026-02-30` là giá trị lịch không tồn tại; không nên chờ lớp nghiệp vụ mới phát hiện.

Một thiết kế dễ kiểm soát:

```text
File / API / Database
       |
       v
Preflight: encoding, header, schema, nguồn dữ liệu
       |
       v
ItemReader + LineTokenizer
       | lỗi cấu trúc --> read error
       v
RawOrderRow (các trường dạng String)
       |
       v
ItemProcessor: strict parsing và format validation
       | lỗi chuyển kiểu --> process error
       v
TypedOrderRow (LocalDate, int, BigDecimal)
       |
       v
Domain validation / đối chiếu
       | lỗi nghiệp vụ --> fail, skip hoặc filter theo policy
       v
ItemWriter + database constraints
       |
       v
Dữ liệu đã commit
```

Không bắt buộc mọi ứng dụng đều tạo đủ ba tầng Java riêng. Với format đơn giản, `FieldSetMapper` có thể chuyển kiểu ngay trong reader. Nhưng giữ raw string đến processor giúp tách rõ lỗi **cấu trúc file** với lỗi **giá trị không hợp lệ**, dễ viết unit test và báo cáo chất lượng dữ liệu theo mã lỗi.

## 2. Bắt đầu bằng hợp đồng dữ liệu

Giả sử nguồn cung cấp CSV:

```csv
orderId,businessDate,quantity,unitPrice
ORD-000101,2026-11-15,2,45.50
ORD-000102,2026-11-15,5,10.00
ORD-000103,2026-11-15,1,99.99
```

Hợp đồng cho ví dụ:

| Trường | Kiểu đích | Format được nhận | Quy tắc bổ sung |
| --- | --- | --- | --- |
| `orderId` | `String` | `ORD-` và đúng 6 chữ số ASCII | Không tự xóa khoảng trắng hoặc đổi chữ hoa/thường |
| `businessDate` | `LocalDate` | ISO `uuuu-MM-dd`, ví dụ `2026-11-15` | Phải tồn tại trong lịch, năm/tháng/ngày hợp lệ |
| `quantity` | `int` | Chỉ chữ số ASCII, không dấu hoặc dấu phân nhóm | Từ 1 đến 999.999, không cho `03` |
| `unitPrice` | `BigDecimal` | Dấu chấm thập phân, 0–2 chữ số phần lẻ, không dấu phân nhóm | Lớn hơn 0; tối đa 8 chữ số phần nguyên |

Ngoài các cột, contract còn phải chỉ rõ **UTF-8**, dấu phẩy làm delimiter, quy tắc quoted field, header bắt buộc, phiên bản schema, cách biểu diễn `null`, dòng trống, thứ tự cột và định nghĩa ngày nghiệp vụ. Các quyết định như có chấp nhận `45.5` và chuẩn hóa thành `45.50` hay bắt buộc ghi đúng `45.50` phải được nêu ra trước khi code.

Nếu nhận dữ liệu từ nhiều quốc gia, tránh đoán định dạng số theo `Locale.getDefault()`. `1.234,56` có thể là một nghìn hai trăm ba mươi bốn phẩy năm sáu ở một locale, nhưng không phải định dạng tiền đã chọn ở bảng trên. Tương tự, một mã `00123` là identifier nên thường giữ dạng `String`; đổi sang `int` sẽ mất số 0 đầu.

## 3. Chọn kiểu Java đúng ý nghĩa

| Dữ liệu | Kiểu thường phù hợp | Sai lầm phổ biến |
| --- | --- | --- |
| Ngày nghiệp vụ không có giờ | `LocalDate` | Gắn timezone không cần thiết, dẫn đến lệch ngày |
| Timestamp mang thời điểm tuyệt đối | `Instant` hoặc `OffsetDateTime` | Parse chuỗi thiếu offset rồi tự coi là UTC |
| Số lượng nguyên | `int`/`long`/`BigInteger` theo biên | Ép `3.5` thành `3` hoặc tràn số |
| Số tiền/decimal chính xác | `BigDecimal` | `double`/`float` và làm tròn nhầm |
| Mã order, SKU, số tài khoản | `String` hoặc value object | Xóa số 0 đầu, đổi định dạng |
| Trạng thái hữu hạn | `enum` với mapping tường minh | Chấp nhận mọi text và phát hiện lỗi quá muộn |
| Boolean từ text | `Boolean` với token được định nghĩa | Mặc nhiên chấp nhận `yes`, `1`, `Y` khi contract chỉ có `true`/`false` |

Với ngày, nên parse bằng parser strict:

```java
DateTimeFormatter format = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate day = LocalDate.parse("2026-11-15", format);
```

`ResolverStyle.STRICT` từ chối ngày không tồn tại như `2026-02-30`. Trong pattern, `uuuu` là proleptic year; `yyyy` là year-of-era, cần cẩn trọng nếu dùng strict parsing mà không có era. `DateTimeFormatter.ISO_LOCAL_DATE` cũng phù hợp khi contract là ISO date.

Với tiền:

```java
BigDecimal price = new BigDecimal("45.50");
```

Không dùng `new BigDecimal(45.50)` với literal `double` vì giá trị floating-point có thể không biểu diễn chính xác số thập phân. Chính sách số chữ số thập phân, precision và làm tròn nên được công bố rõ ràng.

## 4. Đọc CSV thành raw string bằng `FlatFileItemReader`

Ví dụ dưới dùng `FlatFileItemReaderBuilder` và `@StepScope`. Reader chỉ tách các trường, chưa ép kiểu ngày/số:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class OrdersReaderConfig {

    public record RawOrderRow(
            String orderId,
            String businessDate,
            String quantity,
            String unitPrice) {
    }

    @Bean
    @StepScope
    public FlatFileItemReader<RawOrderRow> rawOrdersReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrderRow>()
                .name("rawOrdersReader")
                .resource(new FileSystemResource(inputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .linesToSkip(1)
                .skippedLinesCallback(header -> {
                    String expected =
                            "orderId,businessDate,quantity,unitPrice";
                    if (!expected.equals(header)) {
                        throw new IllegalArgumentException(
                                "Unexpected CSV header");
                    }
                })
                .delimited()
                .delimiter(",")
                .names("orderId", "businessDate", "quantity", "unitPrice")
                .fieldSetMapper(fields -> new RawOrderRow(
                        fields.readString("orderId"),
                        fields.readString("businessDate"),
                        fields.readString("quantity"),
                        fields.readString("unitPrice")))
                .build();
    }
}
```

Nhờ trả về `RawOrderRow`, chuỗi `unitPrice="12.345"` chưa được làm tròn hoặc ép thành `double` trước khi validation chạy. `DelimitedLineTokenizer` chịu trách nhiệm tách trường CSV; khi được cấu hình strict về số token (mặc định nghiêm ngặt), nó báo lỗi với dòng thiếu/thừa cột. `FlatFileItemReader` bao bọc lỗi mapping/tokenizing của một dòng bằng `FlatFileParseException`, nhờ đó có thể biết dòng nào không parse được.

Callback cho dòng header là **kiểm tra cấp file**: nếu header sai thứ tự hoặc khác format, reader sẽ không tiếp tục như thể file hợp lệ. `linesToSkip(1)` tự nó chỉ bỏ qua dòng đầu, không xác minh tên cột. Đoạn callback trên cố ý yêu cầu header giống tuyệt đối; nếu có BOM hoặc nhiều phiên bản schema, hãy thiết kế preflight chuẩn hóa/nhận diện có chủ đích thay vì vô tình chấp nhận một header khác.

Đây là ví dụ đọc file được chọn qua `JobParameters`. Trong ứng dụng vận hành, phải giới hạn `inputFile` trong thư mục/nguồn được phép đọc, chặn path traversal và ghi nhận checksum hoặc version của nguồn. File CSV có quoted field chứa newline cần `RecordSeparatorPolicy` thích hợp; không dùng `line.split(",")` để tự tách các trường được quote.

## 5. Validation processor: strict parsing thành DTO có kiểu

Định nghĩa DTO kết quả và exception mang mã lý do ổn định:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record ValidOrderRow(
        String orderId,
        LocalDate businessDate,
        int quantity,
        BigDecimal unitPrice) {
}
```

```java
public class InvalidOrderRowException extends RuntimeException {
    private final String reasonCode;

    public InvalidOrderRowException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String getReasonCode() {
        return reasonCode;
    }
}
```

Chuyển kiểu và kiểm tra format trong một `ItemProcessor`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.regex.Pattern;

import org.springframework.batch.item.ItemProcessor;

public class OrderTypeAndFormatProcessor
        implements ItemProcessor<OrdersReaderConfig.RawOrderRow, ValidOrderRow> {

    private static final Pattern ORDER_ID =
            Pattern.compile("ORD-[0-9]{6}");
    private static final Pattern QUANTITY =
            Pattern.compile("[1-9][0-9]{0,5}");
    private static final Pattern PRICE =
            Pattern.compile("(?:0|[1-9][0-9]{0,7})(?:\\.[0-9]{1,2})?");

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("uuuu-MM-dd")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public ValidOrderRow process(OrdersReaderConfig.RawOrderRow row) {
        if (row == null) {
            throw new InvalidOrderRowException("MISSING_ROW");
        }
        if (!matches(ORDER_ID, row.orderId())) {
            throw new InvalidOrderRowException("INVALID_ORDER_ID");
        }

        LocalDate date;
        try {
            date = LocalDate.parse(row.businessDate(), DATE_FORMAT);
        } catch (DateTimeParseException | NullPointerException e) {
            throw new InvalidOrderRowException("INVALID_DATE_FORMAT");
        }

        if (!matches(QUANTITY, row.quantity())) {
            throw new InvalidOrderRowException("INVALID_QUANTITY_FORMAT");
        }
        // Regex giới hạn tối đa 6 chữ số nên không thể tràn int.
        int quantity = Integer.parseInt(row.quantity());

        if (!matches(PRICE, row.unitPrice())) {
            throw new InvalidOrderRowException("INVALID_PRICE_FORMAT");
        }
        BigDecimal price = new BigDecimal(row.unitPrice());
        if (price.signum() <= 0) {
            throw new InvalidOrderRowException("NON_POSITIVE_PRICE");
        }
        // Chỉ chuẩn hóa scale, không thực hiện làm tròn.
        price = price.setScale(2);

        return new ValidOrderRow(row.orderId(), date, quantity, price);
    }

    private static boolean matches(Pattern regex, String value) {
        return value != null && regex.matcher(value).matches();
    }
}
```

Những quyết định quan trọng trong đoạn code:

- `ORD-000101` hợp lệ; `ord-000101`, `ORD-101` và khoảng trắng thừa bị từ chối.
- `2026-11-15` hợp lệ; `2026-02-30`, `2026/11/15` và chuỗi rỗng bị từ chối.
- `3` hợp lệ; `0`, `-3`, `3.0`, `03`, `three` không hợp lệ theo contract mẫu.
- `45.5` hợp lệ và được biểu diễn lại thành `45.50`; `12.345`, `1,234.50`, `1e3`, `-2.00` bị từ chối.
- `0.00` có cú pháp số hợp lệ nhưng không hợp lệ về quy tắc nghiệp vụ vì giá phải dương.

Đó là **quy định minh họa**, không phải Spring Batch tự ép buộc. Nếu đối tác có quyền gửi `0003` hoặc dấu phân nhóm số, phải thay data contract, parser và bộ test đồng bộ. Tránh tự động gọi `trim()`, `replace(",", ".")` hoặc đổi chữ hoa/thường một cách không công bố.

## 6. Chuyển kiểu trong reader hay processor?

Spring Batch cung cấp phương thức `FieldSet.readString()`, `readInt()`, `readLong()`, `readBigDecimal()`, `readDate()`... để parse ngay ở lớp mapping. Ví dụ:

```java
// Minh họa FieldSetMapper, với TypedInput do ứng dụng định nghĩa.
fields -> new TypedInput(
        fields.readString("orderId"),
        fields.readDate("businessDate", "yyyy-MM-dd"),
        fields.readInt("quantity"),
        fields.readBigDecimal("unitPrice"))
```

Nếu `readInt` không chuyển được `three`, lỗi phát sinh trong reader; tùy cách wrapper và skip policy, nó có thể trở thành **read skip**. Nếu reader trả toàn bộ `RawOrderRow` rồi processor từ chối `three`, nó trở thành **process skip** khi được cho phép. `FieldSet.readBigDecimal()` có thể parse `12.345` thành giá trị decimal hợp lệ về kỹ thuật, nhưng contract chỉ cho tối đa hai chữ số phần lẻ, nên vẫn cần validation thêm.

| Tình huống | Parse trong mapper của reader | Parse trong processor |
| --- | --- | --- |
| Thiếu/thừa cột CSV | Read error | Vẫn là read error do không tạo được raw object |
| `quantity=three` | Read error nếu mapper gọi `readInt` | Process error theo mã `INVALID_QUANTITY_FORMAT` |
| `unitPrice=12.345` | Có thể parse được nếu không kiểm tra scale | Bị từ chối theo regex contract |
| `businessDate=2026-02-30` | Tùy parser/date policy của mapper | Parser strict từ chối rõ ràng |
| Duplicate order ID | Thường cần business logic bên ngoài reader | Thích hợp kiểm tra ở processor/service |

Parse sớm ở reader giúp code ngắn với file ổn định; parse trong processor giúp kiểm tra rõ lý do và dùng lại logic cho nhiều nguồn dữ liệu. **Vị trí validation ảnh hưởng cách đếm `readSkipCount` và `processSkipCount`**, nên dashboard chất lượng cần biết pipeline được thiết kế theo cách nào.

## 7. Bean Validation cho các đối tượng đã có kiểu

Với `jakarta.validation`, có thể mô tả constraint trên DTO:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import jakarta.validation.constraints.*;

public record TypedOrder(
        @NotBlank
        @Pattern(regexp = "ORD-[0-9]{6}")
        String orderId,

        @NotNull
        LocalDate businessDate,

        @Min(1)
        int quantity,

        @NotNull
        @DecimalMin("0.01")
        @Digits(integer = 8, fraction = 2)
        BigDecimal unitPrice) {
}
```

Spring Batch có `BeanValidatingItemProcessor<T>`. Nó cần Jakarta Bean Validation API và một provider tương thích như Hibernate Validator. Khi dùng Spring Boot, dependency thường là `spring-boot-starter-validation`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

```java
import org.springframework.batch.item.validator.BeanValidatingItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
BeanValidatingItemProcessor<TypedOrder> typedOrderValidator()
        throws Exception {
    BeanValidatingItemProcessor<TypedOrder> p =
            new BeanValidatingItemProcessor<>();
    p.setFilter(false);
    p.afterPropertiesSet();
    return p;
}
```

Bean Validation không tự xác định cách parse chuỗi `1.234,56`, cũng không tự biến chuỗi ngày thành `LocalDate` theo format dự án. Nó cần một đối tượng **đã được chuyển kiểu đúng**; có thể nối parser và validator bằng `CompositeItemProcessor`.

Lựa chọn `setFilter(false)` quan trọng: vi phạm constraint gây `ValidationException`, có thể fail hoặc skip theo chính sách. Với `setFilter(true)`, processor trả `null` cho đối tượng vi phạm, làm tăng `filterCount`; điều này chỉ thích hợp nếu nghiệp vụ thật sự muốn xem invalid record là **filter bình thường**. Nếu đang đánh giá chất lượng input, âm thầm filter hết các lỗi khiến báo cáo skip mất ý nghĩa.

## 8. Cấu hình skip có kiểm soát ở chunk step

Ví dụ cấu hình Spring Batch 5.2.x dùng reader và validator ở trên, với writer được ứng dụng cung cấp:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersStepConfig {

    @Bean
    public OrderTypeAndFormatProcessor orderTypeAndFormatProcessor() {
        return new OrderTypeAndFormatProcessor();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<OrdersReaderConfig.RawOrderRow> rawOrdersReader,
            OrderTypeAndFormatProcessor orderTypeAndFormatProcessor,
            ItemWriter<ValidOrderRow> validOrdersWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrdersReaderConfig.RawOrderRow, ValidOrderRow>
                        chunk(50, transactionManager)
                .reader(rawOrdersReader)
                .processor(orderTypeAndFormatProcessor)
                .writer(validOrdersWriter)
                .faultTolerant()
                .skip(FlatFileParseException.class)
                .skip(InvalidOrderRowException.class)
                .skipLimit(20)
                .listener(new OrderQualitySkipListener())
                .build();
    }
}
```

Trong cấu hình này:

1. Lỗi tokenizing/mapping một dòng CSV có thể thành `FlatFileParseException` ở pha read.
2. Lỗi format hoặc kiểu do `OrderTypeAndFormatProcessor` phát sinh `InvalidOrderRowException` ở pha process.
3. Cả hai loại được phép skip trong giới hạn tổng `20` cho ba pha read/process/write.
4. Lỗi hạ tầng như database mất kết nối, lỗi tài nguyên input không mở được hoặc lỗi không thuộc skip policy sẽ **không được tự động bỏ qua**.

`validOrdersWriter` cần là bean thật của ứng dụng, chẳng hạn writer JDBC có constraint và transaction thích hợp. Đoạn này giả định `JobRepository` và `PlatformTransactionManager` đã được cấu hình đúng; nếu có nhiều writer/reader cùng kiểu, dùng `@Qualifier`. Callback kiểm tra header khi mở reader là lỗi **cấp file**, không nên bị coi như một dòng parse lỗi rồi skip để tiếp tục nhập sai schema.

**`skipLimit` giới hạn tổng skip**, không chia thành quota riêng cho read và process. Một chương trình yêu cầu độ chính xác cao có thể chọn fail-fast với dữ liệu sai thay vì cấu hình skip.

## 9. Log/quarantine bản ghi sai bằng `SkipListener`

`SkipListener` có callback riêng khi một item thực sự bị bỏ qua:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public class OrderQualitySkipListener
        implements SkipListener<OrdersReaderConfig.RawOrderRow, ValidOrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderQualitySkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        if (error instanceof FlatFileParseException parseError) {
            log.warn("batch.validation.skipped phase=read line={} type={}",
                    parseError.getLineNumber(),
                    parseError.getClass().getSimpleName());
        } else {
            log.warn("batch.validation.skipped phase=read type={}",
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onSkipInProcess(
            OrdersReaderConfig.RawOrderRow row, Throwable error) {
        if (error instanceof InvalidOrderRowException invalid) {
            log.warn(
                    "batch.validation.skipped phase=process reason={}",
                    invalid.getReasonCode());
        } else {
            log.warn("batch.validation.skipped phase=process type={}",
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onSkipInWrite(ValidOrderRow item, Throwable error) {
        log.warn("batch.validation.skipped phase=write type={}",
                error.getClass().getSimpleName());
    }
}
```

`FlatFileParseException.getLineNumber()` cho biết vị trí lỗi khi reader parse; nếu cần số dòng nguồn cho mọi lỗi ở **processor**, raw DTO hoặc hệ thống đọc phải giữ metadata vị trí một cách phù hợp. Processor exception không tự mang số dòng vật lý.

Không nên log nguyên `row`, `error.getMessage()` hay `FlatFileParseException.getInput()` nếu có thể chứa PII, token hoặc thông tin thanh toán. Event chất lượng dữ liệu nên ghi **`jobExecutionId`, `stepExecutionId`, tên nguồn đã cho phép, mã lỗi, vị trí record và schema version**; dữ liệu gốc cần vùng quarantine được phân quyền và có retention rõ ràng.

Ghi quarantine có thể là một side effect ngoài transaction của chunk. Khi retry/restart, event có thể bị phát lại; cần idempotency key để tránh lưu bản ghi lỗi trùng. Không đếm `ItemReadListener.onReadError` như số record bị skip: retry hoặc rollback có thể gọi callback lỗi nhiều lần.

## 10. Một ví dụ tổng hợp và số liệu kỳ vọng

Giả sử file:

```csv
orderId,businessDate,quantity,unitPrice
ORD-000101,2026-11-15,2,45.50
ORD-000102,2026-02-30,3,20.00
ORD-000103,2026-11-15,three,15.00
ORD-000104,2026-11-15,1,12.345
ORD-000105,2026-11-15,5,10.00
ORD-000106,2026-11-15,1,8.25,EXTRA
ORD-000107,2026-11-15,1,99.99
```

| Dòng vật lý | Kết quả | Phân loại |
| --- | --- | --- |
| 1 | Header chính xác; không tính item | Header validation |
| 2 | Được ghi | Hợp lệ |
| 3 | Ngày không tồn tại | Process skip |
| 4 | Số lượng không đúng format | Process skip |
| 5 | Giá có ba chữ số phần lẻ | Process skip |
| 6 | Được ghi | Hợp lệ |
| 7 | Thừa cột CSV | Read skip |
| 8 | Được ghi | Hợp lệ |

Nếu writer ghi thành công và không có rollback ảnh hưởng kết quả cuối, `StepExecution` dự kiến:

```text
readCount          = 6
writeCount         = 3
filterCount        = 0
readSkipCount      = 1
processSkipCount   = 3
writeSkipCount     = 0
skipCount          = 4
```

Khi chuyển format parsing sang mapper của reader, một số lỗi type có thể chuyển từ `processSkipCount` sang `readSkipCount`. Vì vậy dashboard nên theo dõi **tổng skip** và **mã nguyên nhân**, đồng thời hiểu nơi xảy ra validation. `filterCount` dành cho processor trả `null`, không cộng vào `skipCount`. Retry thành công không tự biến item thành skip.

## 11. Test logic validation mà không cần Spring context

Processor là Java class thuần nên có thể unit test nhanh bằng JUnit Jupiter:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderTypeAndFormatProcessorTest {

    private final OrderTypeAndFormatProcessor processor =
            new OrderTypeAndFormatProcessor();

    @Test
    void acceptsStrictDateIntegerAndDecimal() throws Exception {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000101", "2026-11-15", "2", "45.5");

        ValidOrderRow actual = processor.process(input);

        assertEquals("ORD-000101", actual.orderId());
        assertEquals(LocalDate.of(2026, 11, 15), actual.businessDate());
        assertEquals(2, actual.quantity());
        assertEquals(new BigDecimal("45.50"), actual.unitPrice());
    }

    @Test
    void rejectsImpossibleCalendarDate() {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000102", "2026-02-30", "1", "10.00");

        var ex = assertThrows(InvalidOrderRowException.class,
                () -> processor.process(input));

        assertEquals("INVALID_DATE_FORMAT", ex.getReasonCode());
    }

    @Test
    void rejectsPriceWithUnexpectedScale() {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000103", "2026-11-15", "1", "12.345");

        var ex = assertThrows(InvalidOrderRowException.class,
                () -> processor.process(input));

        assertEquals("INVALID_PRICE_FORMAT", ex.getReasonCode());
    }

    @Test
    void rejectsNonIntegerQuantityToken() {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000104", "2026-11-15", "3.0", "10.00");

        var ex = assertThrows(InvalidOrderRowException.class,
                () -> processor.process(input));

        assertEquals("INVALID_QUANTITY_FORMAT", ex.getReasonCode());
    }
}
```

Nên mở rộng bằng `@ParameterizedTest` với edge cases:

| Trường | Input | Kỳ vọng theo contract mẫu |
| --- | --- | --- |
| Ngày | `2024-02-29` | Hợp lệ (năm nhuận) |
| Ngày | `2025-02-29`, `2026-13-01` | Bị từ chối |
| Ngày | `15/11/2026`, `2026/11/15` | Bị từ chối |
| Số lượng | `1`, `999999` | Hợp lệ |
| Số lượng | `0`, `-1`, `1000000`, `1.5` | Bị từ chối |
| Giá | `0.01`, `45.50`, `45.5` | Hợp lệ |
| Giá | `0.00`, `45.555`, `1,000.00` | Bị từ chối |
| ID | `ORD-000101` | Hợp lệ |
| ID | `ord-000101`, `ORD-101` | Bị từ chối |

### Integration test cần bổ sung điều gì?

Unit test chỉ chứng minh processor hoạt động; chưa chứng minh CSV tokenizer, charset, header, `@StepScope` và skip policy được tích hợp đúng. Dùng fixture thật trong `src/test/resources` hoặc một file tạm có chủ đích, chạy step với `spring-batch-test` rồi xác nhận:

- Header sai làm job/step fail-fast theo file policy.
- Dòng thừa/thiếu cột đi vào read error; giá/ngày sai đi vào process error.
- `readCount`, `writeCount`, `readSkipCount`, `processSkipCount` khớp fixture.
- Writer chỉ nhận `ValidOrderRow` đạt yêu cầu.
- Lần restart không xử lý lặp hoặc bỏ sót dữ liệu do checkpoint/schema thay đổi.

Trong test chạy job có `JobRepository`, nên dùng database test cô lập; cùng `JobInstance` đã `COMPLETED` sẽ không được khởi chạy lại với cùng identifying `JobParameters` theo cách thông thường.

## 12. Preflight file và validate `JobParameters`

Không nên đợi xử lý 80.000 bản ghi mới phát hiện toàn bộ file có sai delimiter, schema hoặc kỳ dữ liệu. Với lỗi cấp file, hãy kiểm tra sớm:

1. Tài nguyên tồn tại, đúng vùng đọc và có kích thước hợp lý.
2. Encoding và BOM đúng hợp đồng; decoding lỗi phải có chính sách rõ.
3. Header, số cột, schema version, trailer/checksum đúng kỳ vọng.
4. `inputFile` và `businessDate` thuộc kỳ, tenant và nguồn được phép.
5. File có immutable version/checksum để restart đúng nguồn.

Spring Batch có `JobParametersValidator` để kiểm tra tham số trước khi job chạy:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public class ImportJobParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");
        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFile is required");
        }

        String businessDate = parameters.getString("businessDate");
        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }
    }
}
```

Gắn qua job builder:

```java
new JobBuilder("importOrders", jobRepository)
        .validator(new ImportJobParametersValidator())
        .start(importOrdersStep)
        .build();
```

Ví dụ chỉ minh họa trường bắt buộc; trong dự án thật cần kiểm tra cả format ngày và quyền truy cập file. `JobParametersValidator` chỉ validate **đầu vào cấp job**, không thay thế validation từng dòng CSV.

## 13. Normalize định dạng có kiểm soát

Nếu hệ thống nhận nhiều format hợp lệ, nên có **format theo source/version**:

```text
Source A: 2026-11-15  -- ISO yyyy-MM-dd --> LocalDate
Source B: 15/11/2026  -- dd/MM/uuuu    --> LocalDate
                                            |
                                            v
                                   2026-11-15 (ISO output)
```

Không tự động thử mọi format dự đoán được. Nếu parse số theo `NumberFormat` của locale, cần xác nhận parser đã **consume toàn bộ input** và không bỏ qua phần thừa. Nếu input là timestamp thay vì ngày, chuyển sang timezone nghiệp vụ trước khi lấy `LocalDate`:

```java
Instant timestamp = Instant.parse("2026-11-15T23:30:00Z");
LocalDate businessDay = timestamp
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();
```

Ví dụ thời điểm cuối ngày UTC có thể thuộc ngày kế tiếp ở Việt Nam. Với currency, nếu chấp nhận số có dấu phân nhóm hoặc dấu thập phân khác, tokenizer CSV, locale và số chữ số phần lẻ phải cùng tuân theo hợp đồng. Mọi bước normalize như trim/case folding nên được test và có metric riêng khi cần đánh giá chất lượng nguồn.

## 14. Fail, skip, filter và quarantine: chọn theo rủi ro nghiệp vụ

| Dạng lỗi | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Sai header/schema/encoding của cả file | Fail-fast | Không biết các cột có còn map đúng không |
| Một vài record riêng lẻ không đúng format | Skip giới hạn + quarantine nếu policy cho phép | Giữ phần input đúng, vẫn báo cáo dữ liệu xấu |
| Sai giá tiền của giao dịch quan trọng | Fail hoặc skip với kiểm soát chặt | Không ghi giá trị đoán được, tránh sai lệch tiền |
| Bản ghi hợp lệ nhưng ngoài phạm vi nhập | Filter có chủ đích | Không phải lỗi dữ liệu |
| DB/API mất kết nối hoặc metadata ghi lỗi | Fail/retry theo loại lỗi hạ tầng | Skip format không giúp sửa lỗi hạ tầng |
| Tỷ lệ invalid cao bất thường | Fail quality gate | Tránh job hoàn tất với kết quả không đủ tin cậy |

Ngoài `skipLimit` tuyệt đối, hệ thống có thể đặt **quality gate theo tỷ lệ** như tối đa 1% record lỗi. Phải nêu rõ mẫu số: dòng vật lý, item đọc thành công hay `readCount + readSkipCount`. Tỷ lệ này cần dựa trên ý nghĩa của reader/processor, không nên dùng một công thức chung cho mọi job.

Một bản ghi quarantine tối thiểu có thể như sau:

```json
{
  "jobExecutionId": 4812,
  "stepExecutionId": 9207,
  "source": "orders-2026-11-15-v1.csv",
  "recordNumber": 1234,
  "phase": "process",
  "reasonCode": "INVALID_DATE_FORMAT",
  "schemaVersion": "1"
}
```

Đây là schema **ứng dụng tự định nghĩa**, không phải một event Spring Batch tự sinh. Nếu cần lưu giá trị gốc để sửa dữ liệu, phải có vùng lưu và quyền truy cập thích hợp; không đưa nguyên raw record vào log chung. Quarantine writer cũng cần idempotency khi replay/restart.

## 15. Theo dõi chất lượng từ `StepExecution`

Các counter hữu ích cho báo cáo:

| Counter | Ý nghĩa |
| --- | --- |
| `readCount` | Item đọc thành công |
| `writeCount` | Item writer xử lý thành công |
| `filterCount` | Item bị processor trả `null` |
| `readSkipCount` | Item lỗi được skip ở read |
| `processSkipCount` | Item lỗi được skip ở process |
| `writeSkipCount` | Item lỗi được skip ở write |
| `skipCount` | Tổng `readSkipCount + processSkipCount + writeSkipCount` |
| `rollbackCount` | Số lần rollback mà framework ghi nhận |

Có thể ghi tổng kết ở `StepExecutionListener.afterStep`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class DataQualityStepListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(DataQualityStepListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "step={} status={} read={} write={} filter={} " +
                "readSkip={} processSkip={} writeSkip={} rollback={}",
                step.getStepName(), step.getStatus(),
                step.getReadCount(), step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(), step.getProcessSkipCount(),
                step.getWriteSkipCount(), step.getRollbackCount());
        return null; // Giữ ExitStatus hiện có.
    }
}
```

Gắn listener trong `StepBuilder` bằng `.listener(new DataQualityStepListener())`. Lịch sử có thể đọc qua `JobExplorer` hoặc bảng `BATCH_STEP_EXECUTION` ở JDBC repository. Các count là dữ liệu của **một `StepExecution`**; khi restart có thể có nhiều execution, cần chọn đúng ID để tránh cộng sai hoặc đếm trùng số record nghiệp vụ.

`writeCount=0` không tự chứng minh job lỗi vì có thể file rỗng hợp lệ; ngược lại `COMPLETED` với hàng nghìn skip có thể vẫn không đạt SLA chất lượng. Báo cáo nên kết hợp `BatchStatus`, các counter, nguồn, schema version, kỳ nghiệp vụ, ngưỡng cho phép và số bản ghi dự kiến.

## 16. Restart và tính tái lập của validation

Reader có state như `FlatFileItemReader` có thể lưu vị trí đọc vào `ExecutionContext`, giúp restart từ checkpoint đã ghi. Nếu file nguồn bị thay đổi thứ tự/thêm xóa dòng giữa failure và restart, checkpoint có thể trỏ đến **item khác**. Nếu parser/validator được deploy thay đổi giữa hai lần chạy, cùng một chuỗi cũng có thể cho kết quả khác.

Những thực hành quan trọng:

1. Gắn input vào tên logic và **checksum/version bất biến**; kiểm tra nguồn có giữ nguyên trước restart hay không.
2. Version hóa contract type/format, có quy trình migration khi thay đổi.
3. Không dùng locale, timezone hoặc clock mặc định cho parse kết quả phải có tính lặp lại.
4. Thiết kế writer idempotent theo business key, nhất là khi ghi ra API/queue không nằm trong transaction repository.
5. Khi mục tiêu là **restart cùng `JobInstance`**, giữ nguyên identifying `JobParameters`; không thêm UUID/timestamp để tạo instance khác.

Đừng chỉ so `StepExecution.writeCount` để chứng minh dữ liệu đích không trùng: một item có thể bị thử lại sau rollback, còn hệ thống bên ngoài có thể nhận side effect trước khi checkpoint commit.

## 17. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `2026-02-30` được đổi thành ngày khác | Date parser lenient/smart | Dùng `ResolverStyle.STRICT` và test ngày không tồn tại |
| `1.234,56` parse khác nhau giữa máy | Dựa vào locale mặc định | Chỉ định format và locale theo contract |
| Sai số khi tính tiền | Dùng `float`/`double` | `BigDecimal` từ chuỗi, scale/rounding có chủ đích |
| `000123` mất số 0 đầu | Ép mã định danh thành số | Giữ `String` |
| `readSkipCount` thay đổi khi refactor parser | Chuyển validation từ processor sang reader | Báo cáo theo tổng skip và reason code, hiểu vị trí validation |
| Header sai mà job vẫn cố xử lý | Chỉ `linesToSkip(1)` | Preflight/header callback để fail-fast |
| Không xác định được dòng lỗi trong processor | Raw DTO không lưu nguồn/line number | Bổ sung metadata nguồn khi cần trace |
| Callback lỗi xuất hiện nhiều hơn skip count | Retry/rollback | Dùng counter `StepExecution` và `SkipListener` |
| Test trên CI cho kết quả ngày khác | Default timezone/locale/clock | Cố định các yếu tố môi trường |
| Record được ghi hai lần sau restart | File thay đổi hoặc writer không idempotent | Dùng checksum, checkpoint và business key |
| Quarantine chứa nhiều sự kiện trùng | Ghi ngoài transaction/retry | Idempotency key và deduplication |
| Invalid nhiều nhưng job vẫn `COMPLETED` | Skip policy quá rộng, thiếu quality gate | Ngưỡng skip/tỷ lệ, cảnh báo và kiểm tra chất lượng |

## 18. Tài liệu tham khảo

Ví dụ mã dùng **Spring Batch 5.2.x**. Với Spring Batch 6.x, một số package/API có thay đổi, cần dùng tài liệu đúng phiên bản dự án; các nguyên tắc type/format validation, fail/skip và reproducible input vẫn áp dụng.

- [Spring Batch 5.2 — FlatFileItemReader và flat file handling](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch 5.2 — Item processing và validating input](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-processing.html)
- [Spring Batch 5.2 — Configuring skip logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch 5.2 — Intercepting execution và SkipListener](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 API — FlatFileItemReaderBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/file/builder/FlatFileItemReaderBuilder.html)
- [Spring Batch 5.2 API — BeanValidatingItemProcessor](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/validator/BeanValidatingItemProcessor.html)
- [Spring Batch 5.2 API — JobParametersValidator](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersValidator.html)
- [Java 17 API — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

Một pipeline Spring Batch đáng tin cậy cần **data contract rõ ràng**, kiểm tra cấu trúc trước khi xử lý, chuyển kiểu và format bằng parser có quy tắc nghiêm ngặt rồi kiểm tra nghiệp vụ trước khi ghi. Đặt validation ở reader hoặc processor có chủ đích giúp thống kê lỗi chính xác; chọn fail-fast, skip hoặc filter theo mức độ rủi ro; giữ thông tin nguồn và mã lỗi đủ để điều tra mà không lộ dữ liệu nhạy cảm. Cuối cùng, input, parser và writer phải ổn định qua restart để lần chạy lại không biến cùng dữ liệu thành một kết quả khác.
