# FieldSet và kiểu dữ liệu

Trong Spring Batch, `FieldSet` là đối tượng biểu diễn các field đã được tách từ một dòng file. Nó cung cấp cách đọc giá trị theo vị trí hoặc theo tên, đồng thời hỗ trợ chuyển đổi dữ liệu văn bản sang các kiểu Java như `int`, `long`, `BigDecimal`, `Date` và `boolean`.

Với flat-file processing, luồng thông thường là: `LineTokenizer` tách một dòng thành `FieldSet`, sau đó `FieldSetMapper` ánh xạ FieldSet thành object nghiệp vụ. Hiểu rõ hai thành phần này giúp kiểm soát kiểu dữ liệu, định dạng ngày tháng, giá trị rỗng và lỗi dữ liệu đầu vào.

## 1. FieldSet là gì?

`FieldSet` là abstraction của Spring Batch tương tự một dòng trong bảng dữ liệu: mỗi field có một giá trị và có thể được truy cập bằng index hoặc tên cột.

Ví dụ file `orders.csv`:

```csv
order_id,customer_id,amount,quantity,business_date
00001234,CUST-18,1250.75,2,2026-11-15
00001235,CUST-21,89.90,1,2026-11-15
```

Sau khi tokenizer tách dòng thứ hai, FieldSet có thể được hình dung như sau:

| Index | Tên field | Giá trị dạng text |
|---:|---|---|
| 0 | `order_id` | `00001234` |
| 1 | `customer_id` | `CUST-18` |
| 2 | `amount` | `1250.75` |
| 3 | `quantity` | `2` |
| 4 | `business_date` | `2026-11-15` |

FieldSet không phải object nghiệp vụ cuối cùng. Nó giữ các giá trị đã tách từ dòng file; bước mapping sẽ chuyển chúng thành kiểu dữ liệu mà ứng dụng cần.

## 2. Luồng LineTokenizer và FieldSetMapper

Trong một flat-file reader, `LineMapper` phối hợp hai bước:

1. `LineTokenizer` phân tích một dòng và tạo `FieldSet`.
2. `FieldSetMapper` đọc FieldSet và tạo object đích.

```text
Một dòng trong file
        |
        v
   LineTokenizer
        |
        v
     FieldSet
        |
        v
   FieldSetMapper
        |
        v
  Order / DTO nghiệp vụ
        |
        v
   ItemProcessor
```

Spring Batch cung cấp một số tokenizer phổ biến:

| Tokenizer | Cách tách | Trường hợp sử dụng |
|---|---|---|
| `DelimitedLineTokenizer` | Tách theo dấu phân cách như dấu phẩy hoặc tab | CSV, TSV và file có delimiter. |
| `FixedLengthTokenizer` | Tách theo các khoảng vị trí cố định | File có layout độ rộng cố định. |

`DefaultLineMapper` thường được dùng để kết hợp tokenizer và mapper:

```java
DefaultLineMapper<Order> lineMapper = new DefaultLineMapper<>();
lineMapper.setLineTokenizer(tokenizer);
lineMapper.setFieldSetMapper(fieldSetMapper);
```

Reader gọi LineMapper cho từng dòng dữ liệu và nhận về object `Order`.

## 3. Đọc FieldSet theo tên hoặc index

FieldSet cho phép đọc giá trị bằng index:

```java
String orderId = fieldSet.readString(0);
String customerId = fieldSet.readString(1);
BigDecimal amount = fieldSet.readBigDecimal(2);
int quantity = fieldSet.readInt(3);
```

Hoặc đọc theo tên:

```java
String orderId = fieldSet.readString("order_id");
String customerId = fieldSet.readString("customer_id");
BigDecimal amount = fieldSet.readBigDecimal("amount");
int quantity = fieldSet.readInt("quantity");
```

Đọc theo tên thường dễ bảo trì hơn vì không phụ thuộc trực tiếp vào thứ tự cột trong code. Tuy nhiên, tên field phải được tokenizer khai báo chính xác. Nếu không có tên, hoặc tên bị sai, việc truy cập theo tên sẽ không hoạt động như mong muốn.

Các phương thức đọc kiểu thường dùng gồm:

| Phương thức | Kiểu kết quả |
|---|---|
| `readString(...)` | `String` |
| `readInt(...)` | `int` |
| `readLong(...)` | `long` |
| `readShort(...)` | `short` |
| `readFloat(...)` | `float` |
| `readDouble(...)` | `double` |
| `readBigDecimal(...)` | `BigDecimal` |
| `readBoolean(...)` | `boolean` |
| `readDate(...)` | `java.util.Date` |

Một số phương thức có overload nhận index hoặc tên field. Với ngày tháng và dữ liệu cần định dạng cụ thể, hãy đọc chuỗi rồi parse bằng formatter tường minh để kiểm soát format và lỗi.

## 4. FieldSetMapper ánh xạ dữ liệu thành object

`FieldSetMapper<T>` là interface chuyển một FieldSet thành object kiểu `T`:

```java
public interface FieldSetMapper<T> {
    T mapFieldSet(FieldSet fieldSet) throws BindException;
}
```

Ví dụ DTO:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record Order(
        String orderId,
        String customerId,
        BigDecimal amount,
        int quantity,
        LocalDate businessDate) {
}
```

Mapper tùy chỉnh:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.batch.item.file.mapping.FieldSetMapper;
import org.springframework.batch.item.file.transform.FieldSet;

public class OrderFieldSetMapper implements FieldSetMapper<Order> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public Order mapFieldSet(FieldSet fieldSet) {
        String orderId = fieldSet.readString("order_id");
        String customerId = fieldSet.readString("customer_id");
        BigDecimal amount = fieldSet.readBigDecimal("amount");
        int quantity = fieldSet.readInt("quantity");
        LocalDate businessDate = LocalDate.parse(
                fieldSet.readString("business_date"), DATE_FORMAT);

        return new Order(
                orderId,
                customerId,
                amount,
                quantity,
                businessDate);
    }
}
```

Mapper tùy chỉnh phù hợp khi cần parse `LocalDate`, chuẩn hóa chuỗi, áp dụng default hoặc kiểm tra dữ liệu trước khi tạo object. Ví dụ giữ `orderId` ở dạng `String` để không làm mất các số 0 ở đầu.

## 5. Dùng BeanWrapperFieldSetMapper

Nếu tên field trong file tương ứng với property của JavaBean, có thể dùng `BeanWrapperFieldSetMapper` thay vì tự viết mapper.

Ví dụ JavaBean:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public class OrderRecord {

    private String orderId;
    private String customerId;
    private BigDecimal amount;
    private Integer quantity;
    private LocalDate businessDate;

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public LocalDate getBusinessDate() { return businessDate; }
    public void setBusinessDate(LocalDate businessDate) {
        this.businessDate = businessDate;
    }
}
```

Cấu hình mapper:

```java
import org.springframework.batch.item.file.mapping.BeanWrapperFieldSetMapper;

BeanWrapperFieldSetMapper<OrderRecord> mapper =
        new BeanWrapperFieldSetMapper<>();
mapper.setTargetType(OrderRecord.class);
mapper.setStrict(true);
```

`BeanWrapperFieldSetMapper` dùng cơ chế bean property binding để ánh xạ field vào property tương ứng. JavaBean cần có cách tạo instance và setter phù hợp. Tên field/tokenizer nên tương ứng với tên property; ví dụ `orderId` có thể map vào property `orderId`.

Với các kiểu đặc biệt như `LocalDate`, enum hoặc format số phụ thuộc locale, cần bảo đảm có converter/editor phù hợp. Nếu mapping cần quy tắc phức tạp hoặc xử lý lỗi chi tiết, custom `FieldSetMapper` thường dễ kiểm soát hơn.

## 6. Khai báo tokenizer và tên field

Ví dụ dùng `DelimitedLineTokenizer` cho CSV:

```java
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;

DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
tokenizer.setDelimiter(",");
tokenizer.setNames(
        "order_id",
        "customer_id",
        "amount",
        "quantity",
        "business_date");
tokenizer.setStrict(true);
```

Tên field là hợp đồng giữa file nguồn và mapper. Khi thay đổi thứ tự cột, nếu tokenizer vẫn gán tên theo thứ tự cũ thì mapper có thể nhận sai dữ liệu dù không phát sinh lỗi kiểu.

`strict(true)` yêu cầu số field trong dòng phù hợp với cấu hình names. Khi file có số cột không đúng, tokenizer báo lỗi thay vì âm thầm tạo FieldSet thiếu hoặc thừa field theo cấu hình strict. Với file có định dạng không cố định, cần xác định chính sách rõ ràng cho từng loại dòng.

Khi dùng CSV có dấu phẩy bên trong giá trị, cần xử lý quote đúng chuẩn. Ví dụ:

```csv
order_id,customer_name,amount
1001,"Nguyen Van A, Branch 2",125.50
```

Không nên tự gọi `String.split(",")` để parse CSV vì nó không hiểu dấu phẩy nằm trong quoted field. Hãy dùng tokenizer có hỗ trợ quote hoặc thư viện CSV chuyên dụng.

## 7. FieldSet với file fixed-length

Không phải flat file nào cũng dùng delimiter. Một số hệ thống cũ xuất file theo độ rộng cột cố định:

```text
00001234CUST-18     000012507520261115
```

Có thể dùng `FixedLengthTokenizer` để khai báo các khoảng ký tự:

```java
import org.springframework.batch.item.file.transform.FixedLengthTokenizer;
import org.springframework.batch.item.file.transform.Range;

FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setNames("order_id", "customer_id", "amount", "date_text");
tokenizer.setColumns(
        new Range(1, 8),
        new Range(9, 18),
        new Range(19, 28),
        new Range(29, 36));
tokenizer.setStrict(true);
```

Các range trong ví dụ là vị trí ký tự bắt đầu/kết thúc theo cách đánh số của API `Range`. Cần xác nhận layout file với đặc tả nguồn, đặc biệt khi file có padding, dấu âm, decimal implied hoặc encoding nhiều byte. Với fixed-length record, độ dài thường được định nghĩa theo ký tự hoặc byte bởi hệ thống nguồn; không được tự giả định hai cách đo này giống nhau với mọi charset.

Sau khi tokenizer tạo FieldSet, cùng một `FieldSetMapper` có thể được dùng để chuyển đổi kiểu dữ liệu như với CSV.

## 8. Chuyển đổi String sang kiểu số

Giá trị đọc từ file ban đầu là text. `FieldSet` hỗ trợ các phương thức đọc kiểu số:

```java
int quantity = fieldSet.readInt("quantity");
long accountNumber = fieldSet.readLong("account_number");
BigDecimal amount = fieldSet.readBigDecimal("amount");
```

### Dùng BigDecimal cho tiền tệ

Không nên dùng `float` hoặc `double` để lưu giá trị tiền tệ nếu cần độ chính xác thập phân. Dùng `BigDecimal`:

```java
BigDecimal amount = new BigDecimal(fieldSet.readString("amount"));
```

`BigDecimal` giữ độ chính xác thập phân theo chuỗi đầu vào. Nếu cần chuẩn hóa scale, có thể dùng `setScale()` với `RoundingMode` được xác định theo quy tắc nghiệp vụ.

```java
BigDecimal normalized = amount.setScale(2, RoundingMode.UNNECESSARY);
```

`UNNECESSARY` sẽ ném exception nếu phải làm tròn. Nếu nghiệp vụ cho phép làm tròn, chọn rõ `HALF_UP`, `HALF_EVEN` hoặc quy tắc tương ứng; không để việc làm tròn diễn ra ngầm.

### Dấu phân cách thập phân và locale

File nguồn cần thống nhất quy ước số. Ví dụ `1250.75` và `1.250,75` là hai biểu diễn khác nhau. `readBigDecimal()` thường phù hợp với chuỗi số theo format chuẩn dùng dấu chấm thập phân. Nếu nguồn dùng locale khác, hãy parse bằng `DecimalFormat` với locale rõ ràng hoặc chuẩn hóa dữ liệu trước khi tạo BigDecimal.

Không nên xóa mọi dấu phẩy một cách máy móc vì có thể biến `1,25` thành `125` thay vì `1.25`.

## 9. Chuyển đổi ngày tháng và thời gian

File thường biểu diễn ngày dưới dạng chuỗi. Nên khai báo format rõ ràng và parse thành kiểu Java phù hợp:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu");
LocalDate date = LocalDate.parse("15/11/2026", formatter);
```

Với định dạng ISO như `2026-11-15`, dùng `DateTimeFormatter.ISO_LOCAL_DATE`. Với timestamp có timezone, cân nhắc `OffsetDateTime` hoặc `Instant`; với thời gian địa phương không có timezone, dùng `LocalDateTime` theo hợp đồng dữ liệu.

Không nên dùng `LocalDateTime` cho timestamp toàn cục nếu nguồn thực tế có timezone mà không truyền kèm offset. Cần xác định timezone của nguồn và chuyển đổi nhất quán.

Khi parse thất bại, `DateTimeParseException` chứa thông tin về giá trị không phù hợp. Có thể để Step thất bại, skip bản ghi theo policy hoặc ghi reject record tùy yêu cầu nghiệp vụ.

## 10. Boolean và enum

Không phải mọi file đều biểu diễn boolean bằng `true`/`false`. Nguồn có thể dùng `Y/N`, `1/0`, `ACTIVE/INACTIVE`. Nên chuẩn hóa các giá trị được chấp nhận:

```java
private boolean parseActive(String value) {
    return switch (value.trim().toUpperCase(Locale.ROOT)) {
        case "Y", "YES", "1", "TRUE" -> true;
        case "N", "NO", "0", "FALSE" -> false;
        default -> throw new IllegalArgumentException(
                "Unsupported active flag: " + value);
    };
}
```

Enum cũng nên parse có kiểm soát:

```java
OrderStatus status;
try {
    status = OrderStatus.valueOf(
            fieldSet.readString("status").trim().toUpperCase(Locale.ROOT));
} catch (IllegalArgumentException ex) {
    throw new InvalidOrderException("Unknown order status", ex);
}
```

Không nên để giá trị lạ tự động trở thành `false` hoặc một enum mặc định nếu điều đó làm thay đổi ý nghĩa nghiệp vụ. Giá trị không nhận diện được cần được ghi nhận hoặc xử lý theo policy lỗi.

## 11. Null, chuỗi rỗng và giá trị mặc định

Trong file text, các trường hợp sau không nhất thiết có cùng ý nghĩa:

```text
1001,,125.50
1002,"",125.50
1003,NULL,125.50
```

- Field không có ký tự giữa hai delimiter có thể được tokenizer trả về chuỗi rỗng.
- Quoted empty field cũng có thể biểu diễn chuỗi rỗng tùy tokenizer.
- Chuỗi `NULL` chỉ là text nếu nguồn không quy định rõ nó đại diện null.

Với field tùy chọn, đọc String trước rồi chuẩn hóa:

```java
String note = fieldSet.readString("note");
String normalizedNote = note == null || note.isBlank()
        ? null
        : note.trim();
```

Với số tùy chọn, không gọi trực tiếp `readInt()` khi field có thể rỗng. Hãy kiểm tra text trước:

```java
String quantityText = fieldSet.readString("quantity").trim();
Integer quantity = quantityText.isEmpty()
        ? null
        : Integer.valueOf(quantityText);
```

Chỉ dùng default khi nghiệp vụ định nghĩa rõ. Ví dụ quantity rỗng có thể mặc định 1 trong một số định dạng, nhưng có thể phải xem là lỗi ở định dạng khác. Không tự đổi dữ liệu thiếu thành 0 vì điều đó có thể làm sai báo cáo hoặc số tiền.

## 12. Kiểm tra và chuẩn hóa dữ liệu trong mapper

FieldSetMapper là nơi phù hợp để thực hiện chuyển đổi cú pháp và kiểm tra điều kiện cơ bản của một dòng. Ví dụ:

```java
public class OrderFieldSetMapper implements FieldSetMapper<Order> {

    @Override
    public Order mapFieldSet(FieldSet fieldSet) {
        String orderId = fieldSet.readString("order_id").trim();
        String customerId = fieldSet.readString("customer_id").trim();
        String amountText = fieldSet.readString("amount").trim();

        if (orderId.isEmpty()) {
            throw new InvalidOrderException("order_id is required");
        }
        if (customerId.isEmpty()) {
            throw new InvalidOrderException("customer_id is required");
        }

        BigDecimal amount = new BigDecimal(amountText);
        if (amount.signum() < 0) {
            throw new InvalidOrderException("amount cannot be negative");
        }

        return new Order(
                orderId,
                customerId,
                amount,
                fieldSet.readInt("quantity"),
                LocalDate.parse(fieldSet.readString("business_date")));
    }
}
```

Mapper nên tập trung vào việc biến đổi một dòng thành object và kiểm tra dữ liệu cục bộ. Các quy tắc nghiệp vụ cần truy vấn nhiều hệ thống, cập nhật database hoặc phụ thuộc trạng thái toàn Job thường phù hợp hơn với `ItemProcessor` hoặc service nghiệp vụ.

## 13. Cấu hình FlatFileItemReader với FieldSetMapper

Có thể kết nối tokenizer và mapper bằng `DefaultLineMapper` rồi truyền vào `FlatFileItemReader`:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
tokenizer.setDelimiter(",");
tokenizer.setNames(
        "order_id",
        "customer_id",
        "amount",
        "quantity",
        "business_date");
tokenizer.setStrict(true);

DefaultLineMapper<Order> lineMapper = new DefaultLineMapper<>();
lineMapper.setLineTokenizer(tokenizer);
lineMapper.setFieldSetMapper(new OrderFieldSetMapper());

FlatFileItemReader<Order> reader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource("/data/in/orders.csv"))
                .encoding("UTF-8")
                .linesToSkip(1)
                .lineMapper(lineMapper)
                .saveState(true)
                .build();
```

Trong ứng dụng Spring, nên khai báo reader thành bean `@StepScope` nếu resource hoặc cấu hình tokenizer phụ thuộc JobParameters. Ví dụ trên dùng đường dẫn cố định để làm rõ cách kết nối LineTokenizer và FieldSetMapper.

## 14. Xử lý lỗi mapping và dữ liệu không hợp lệ

Các lỗi thường gặp khi ánh xạ FieldSet:

- Số field không khớp với layout.
- Tên field sai hoặc thiếu.
- Chuỗi số chứa ký tự không hợp lệ.
- Ngày không đúng format.
- Enum có giá trị không được hỗ trợ.
- Field bắt buộc bị rỗng.
- Giá trị vượt miền biểu diễn của kiểu đích.

Có thể xử lý lỗi bằng cách:

1. Fail Step nếu dữ liệu sai làm mất tính đúng đắn của toàn bộ file.
2. Skip dòng lỗi nếu nghiệp vụ cho phép bỏ qua một số record và có giới hạn.
3. Ghi reject record với số dòng, file nguồn, giá trị lỗi và lý do.
4. Dùng validation Step để kiểm tra header/schema trước khi import.

Nếu cấu hình skip, hãy chọn exception cụ thể. Ví dụ `InvalidOrderException` cho lỗi nghiệp vụ của dòng; lỗi cấu hình file hoặc thiếu header có thể cần làm Job thất bại thay vì skip hàng loạt.

`FlatFileParseException` có thể cung cấp thông tin dòng và nội dung nguồn khi mapping dòng thất bại. Cần cân nhắc dữ liệu nhạy cảm trước khi ghi nguyên dòng file vào log hoặc reject table.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng index nhưng thứ tự cột thay đổi | Mapper đọc nhầm field mà không nhất thiết phát sinh lỗi. | Đặt tên field trong tokenizer và đọc theo tên. |
| Chuyển mã đơn hàng sang số | Mất số 0 ở đầu hoặc định dạng ký tự. | Giữ identifier ở dạng `String`. |
| Dùng `double` cho tiền tệ | Sai số biểu diễn dấu phẩy động. | Dùng `BigDecimal`. |
| Dùng format ngày mặc định | Kết quả phụ thuộc locale hoặc format môi trường. | Parse bằng `DateTimeFormatter` rõ ràng. |
| Dùng `split(",")` cho CSV | Không xử lý quoted field có dấu phẩy hoặc quote. | Dùng `DelimitedLineTokenizer` hoặc thư viện CSV. |
| Xem chuỗi `NULL` như null mặc định | Quy ước của nguồn chưa được xác định. | Thống nhất null marker và chuẩn hóa trong mapper. |
| Field rỗng được chuyển thẳng sang primitive | Có thể gây lỗi parse hoặc mất phân biệt null/0. | Đọc String, kiểm tra rỗng rồi chuyển sang wrapper type khi cần. |
| BeanWrapper không map được property | Tên field không khớp hoặc JavaBean thiếu setter/constructor phù hợp. | Kiểm tra tên property hoặc dùng custom FieldSetMapper. |
| Bỏ qua mọi lỗi mapping | Dữ liệu sai có thể bị che giấu. | Phân loại exception, giới hạn skip và ghi reject. |

## Kết luận

`FieldSet` biểu diễn các giá trị đã được `LineTokenizer` tách từ một dòng file; `FieldSetMapper` chuyển chúng thành object nghiệp vụ. Có thể đọc theo tên hoặc index, dùng các phương thức `readInt`, `readLong`, `readBigDecimal` và các kiểu tương ứng, hoặc tự parse khi cần format cụ thể. `BeanWrapperFieldSetMapper` phù hợp với JavaBean có property tương ứng, còn mapper tùy chỉnh giúp kiểm soát ngày tháng, locale, enum, null và validation. Hãy giữ identifier ở dạng String khi cần bảo toàn số 0 đầu, dùng BigDecimal cho tiền tệ, khai báo format rõ ràng và phân loại lỗi mapping theo chính sách fail/skip để dữ liệu file được chuyển đổi chính xác.
