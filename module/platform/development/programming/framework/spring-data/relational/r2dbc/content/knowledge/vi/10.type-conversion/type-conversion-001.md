# Các kiểu dữ liệu Java và kiểu cột được hỗ trợ

Khi dùng Spring Data R2DBC, mỗi thuộc tính Java được ánh xạ thành một hoặc nhiều cột trong cơ sở dữ liệu quan hệ. Để đọc và ghi thành công, kiểu Java, quy tắc chuyển đổi của Spring Data, kiểu cột SQL và khả năng của R2DBC driver phải tương thích với nhau.

Có hai lớp xử lý cần phân biệt:

1. **Spring Data mapping và conversion** xác định thuộc tính entity tương ứng với cột nào, chuyển đổi các kiểu miền nghiệp vụ và chuẩn bị giá trị cho thao tác persistence.
2. **R2DBC driver codec** mã hóa giá trị Java thành kiểu dữ liệu mà database nhận được và giải mã giá trị database thành kiểu Java khi đọc kết quả.

Vì vậy, một kiểu có thể được Spring Data nhận diện là kiểu đơn giản nhưng vẫn cần driver hỗ trợ kiểu dữ liệu tương ứng. Khả năng cụ thể còn phụ thuộc hệ quản trị cơ sở dữ liệu, driver và phiên bản đang sử dụng. Không có một bảng ánh xạ duy nhất bảo đảm mọi kiểu SQL đặc thù hoạt động giống nhau trên tất cả database.

## 1. Nguyên tắc ánh xạ kiểu dữ liệu

Spring Data R2DBC sử dụng metadata entity để xác định tên bảng, tên cột, khóa chính và các thuộc tính cần persistence. Với các kiểu đơn giản, mỗi thuộc tính thường tương ứng với một cột. Các kiểu phức tạp có thể cần chiến lược khác như embedded mapping, collection mapping hoặc custom conversion.

Ví dụ:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;

    private Boolean active;
}
```

Trong ví dụ, `displayName` được ánh xạ vào cột `display_name` nhờ `@Column`. Nếu không khai báo tên cột, Spring Data áp dụng naming strategy của mapping context. Kiểu Java `String` và `Boolean` cần được driver chuyển đổi sang kiểu cột tương ứng của database.

Các annotation mapping không tự tạo schema. Bảng và cột phải tồn tại, thường được quản lý bằng migration. Kiểu cột trong schema cần có độ rộng, precision, scale và khả năng null phù hợp với dữ liệu mà ứng dụng ghi.

## 2. Bảng tham chiếu Java type và SQL column type

Bảng dưới đây mô tả các cặp ánh xạ thường gặp. Đây là hướng dẫn lựa chọn kiểu cột phổ biến; kiểu native chính xác và khả năng chuyển đổi phải được kiểm tra với database cùng R2DBC driver của dự án.

| Kiểu Java | Kiểu cột SQL thường dùng | Ghi chú |
|---|---|---|
| `boolean`, `Boolean` | `BOOLEAN` | Kiểu wrapper `Boolean` biểu diễn được `NULL`; primitive `boolean` thì không. |
| `byte`, `Byte` | `SMALLINT` hoặc kiểu số nhỏ tương ứng | Kiểm tra miền giá trị và khả năng hỗ trợ của database. |
| `short`, `Short` | `SMALLINT` | Phù hợp số nguyên có miền giá trị nhỏ. |
| `int`, `Integer` | `INTEGER` | Dùng cho số nguyên 32-bit. |
| `long`, `Long` | `BIGINT` | Dùng cho số nguyên 64-bit và ID dạng số. |
| `float`, `Float` | `REAL` | Số dấu phẩy động độ chính xác đơn; không phù hợp tiền tệ. |
| `double`, `Double` | `DOUBLE PRECISION` | Số dấu phẩy động độ chính xác kép; vẫn có sai số biểu diễn nhị phân. |
| `BigDecimal` | `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` | Phù hợp giá trị cần độ chính xác thập phân; chọn precision và scale rõ ràng. |
| `BigInteger` | `NUMERIC` hoặc kiểu số nguyên lớn mà database hỗ trợ | Cần kiểm tra giới hạn và codec; đôi khi cần custom conversion. |
| `String` | `VARCHAR(n)`, `CHAR(n)`, `TEXT`, `CLOB` | Chọn độ dài và kiểu lưu trữ theo nội dung. |
| `char`, `Character` | `CHAR(1)` hoặc `VARCHAR` | Kiểm tra cách driver xử lý ký tự và chuỗi. |
| `byte[]` | `BINARY`, `VARBINARY`, `BLOB`, `BYTEA` | Dùng cho dữ liệu nhị phân; tên kiểu tùy database. |
| `UUID` | Kiểu `UUID` native hoặc `CHAR`/`VARCHAR`/binary | Phụ thuộc database và driver. |
| `LocalDate` | `DATE` | Chỉ biểu diễn ngày, không có giờ hoặc múi giờ. |
| `LocalTime` | `TIME` | Biểu diễn giờ trong ngày, không có ngày và múi giờ. |
| `LocalDateTime` | `TIMESTAMP` không múi giờ | Không tự biểu diễn một thời điểm tuyệt đối nếu thiếu quy ước múi giờ. |
| `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` hoặc kiểu tương đương | Hỗ trợ offset tùy driver; semantics lưu trữ khác nhau giữa database. |
| `Instant` | Cột timestamp biểu diễn thời điểm UTC | Cần quy ước rõ khi chuyển đổi qua driver và database. |
| `ZonedDateTime` | Thường chuyển thành timestamp/instant và lưu zone riêng nếu cần | Không phải database nào cũng lưu được region ID như `Europe/Paris`. |
| `Enum` | Thường là `VARCHAR`/`CHAR` | Có thể cần custom converter cho mã nghiệp vụ hoặc native enum của database. |
| JSON value/object | Kiểu JSON/JSONB hoặc text | Phụ thuộc driver codec hoặc custom converter. |
| SQL array | Kiểu ARRAY của database | Hỗ trợ khác nhau theo driver; không đồng nghĩa với collection mapping của Spring Data. |

Không nên chọn kiểu SQL chỉ dựa vào tên Java. Hãy xem thêm miền giá trị, độ chính xác, khả năng null, cách so sánh và cách database lưu trữ kiểu đó.

## 3. Kiểu số và độ chính xác

### 3.1 Số nguyên

Các kiểu `short`, `int` và `long` thường ánh xạ lần lượt đến `SMALLINT`, `INTEGER` và `BIGINT`. Chọn kiểu cột đủ lớn cho miền giá trị dự kiến, đồng thời tránh dùng kiểu quá nhỏ nếu ID hoặc bộ đếm có thể tăng theo thời gian.

Các kiểu unsigned trong một số database không có ánh xạ Java tương ứng một cách đồng nhất. Ví dụ, một cột unsigned có thể chứa giá trị lớn hơn miền dương của kiểu Java signed cùng kích thước. Nếu cần dùng kiểu unsigned, hãy kiểm tra codec của driver và cân nhắc kiểu Java lớn hơn hoặc custom conversion.

### 3.2 Số dấu phẩy động và tiền tệ

`float` và `double` dùng biểu diễn dấu phẩy động nhị phân. Nhiều giá trị thập phân như `0.1` không thể biểu diễn chính xác bằng dạng nhị phân hữu hạn. Vì vậy, không nên dùng chúng cho tiền tệ, số dư hoặc phép tính yêu cầu độ chính xác thập phân.

Với dữ liệu tiền tệ, thường dùng `BigDecimal` và cột `DECIMAL(p,s)` hoặc `NUMERIC(p,s)`:

```java
@Column("total_amount")
private BigDecimal totalAmount;
```

Ví dụ schema:

```sql
total_amount DECIMAL(19, 4) NOT NULL
```

Trong `DECIMAL(p,s)`, `p` là tổng số chữ số tối đa và `s` là số chữ số sau dấu thập phân. Nếu ứng dụng ghi giá trị có scale lớn hơn scale cột, database có thể làm tròn, cắt hoặc từ chối tùy hệ quản trị và cấu hình. Hãy xác định quy tắc làm tròn trong nghiệp vụ thay vì để hành vi mặc định của database quyết định.

`BigDecimal` cũng cần được tạo đúng cách trong Java. Khi khởi tạo từ literal dấu phẩy động, sai số nhị phân có thể đã xuất hiện trước khi ghi database. Nên tạo từ chuỗi hoặc từ giá trị nguyên theo đơn vị nhỏ nhất khi phù hợp.

### 3.3 Precision và scale phải đồng bộ

Ví dụ một trường giá tiền được định nghĩa `DECIMAL(12,2)` chỉ cho tối đa 12 chữ số tổng cộng, trong đó có 2 chữ số thập phân. Nếu nghiệp vụ cho phép số lớn hơn, schema phải được thiết kế lại. Việc chỉ khai báo `BigDecimal` trong Java không tự mở rộng precision của cột.

## 4. Chuỗi, ký tự và dữ liệu nhị phân

`String` thường ánh xạ vào `VARCHAR`, `CHAR` hoặc kiểu văn bản lớn như `TEXT`/`CLOB`. Chọn `VARCHAR(n)` cho dữ liệu có giới hạn độ dài rõ ràng như mã quốc gia hoặc mã tiền tệ; chọn kiểu text lớn hơn cho nội dung tự do. Cần xem giới hạn độ dài theo ký tự hay byte và cách database xử lý Unicode.

`char` hoặc `Character` có thể dùng cho một ký tự, nhưng nhiều ứng dụng vẫn dùng `String` với cột `CHAR(1)` hoặc `VARCHAR(1)` để tránh khác biệt codec và quy tắc padding giữa các database.

`byte[]` phù hợp dữ liệu nhị phân như hash, token hoặc nội dung nhỏ. Với file lớn, không nên mặc định tải toàn bộ vào một mảng byte trong bộ nhớ. Hãy cân nhắc lưu file ở object storage và chỉ giữ metadata hoặc URI trong database, hoặc dùng API/chiến lược streaming mà driver hỗ trợ.

Tên kiểu nhị phân không thống nhất: PostgreSQL có `BYTEA`, một số database dùng `BLOB`, `VARBINARY` hoặc `BINARY`. Driver cần hỗ trợ việc mã hóa/giải mã kiểu cột tương ứng.

## 5. Ngày giờ và múi giờ

Ngày giờ là nhóm kiểu dễ gây lỗi vì tên Java có thể biểu diễn những ý nghĩa khác nhau. Cần phân biệt ngày lịch, giờ địa phương, thời điểm tuyệt đối và múi giờ.

| Kiểu Java | Ý nghĩa | Kiểu SQL thường dùng |
|---|---|---|
| `LocalDate` | Ngày lịch, ví dụ ngày sinh | `DATE` |
| `LocalTime` | Giờ trong ngày, ví dụ giờ mở cửa | `TIME` |
| `LocalDateTime` | Ngày và giờ địa phương, không có offset | `TIMESTAMP` không múi giờ |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | `TIMESTAMP WITH TIME ZONE` nếu driver hỗ trợ phù hợp |
| `Instant` | Một thời điểm trên timeline UTC | Kiểu timestamp có quy ước lưu instant |
| `ZonedDateTime` | Ngày giờ kèm zone ID và quy tắc vùng | Thường cần lưu instant/offset và zone ID riêng nếu cần khôi phục đầy đủ |

`LocalDateTime` không xác định được một thời điểm tuyệt đối nếu không biết múi giờ. Ví dụ `2026-11-15T09:00` có thể tương ứng với các thời điểm UTC khác nhau tùy vùng. Với thời điểm sự kiện như lúc thanh toán hoặc tạo bản ghi, thường dùng `Instant` hoặc `OffsetDateTime` theo quy ước của hệ thống.

Không phải mọi database giữ nguyên offset hoặc zone ID khi lưu timestamp. Một số hệ quản trị chuẩn hóa về UTC hoặc chỉ giữ giá trị thời điểm. Nếu nghiệp vụ cần biết múi giờ vùng ban đầu, chẳng hạn `Asia/Ho_Chi_Minh`, hãy lưu zone ID riêng bên cạnh timestamp.

Ví dụ entity:

```java
@Table("payment")
public class Payment {
    @Id
    private UUID id;

    private LocalDate paidOn;

    private Instant createdAt;

    private OffsetDateTime confirmedAt;
}
```

Ví dụ này chỉ minh họa ý nghĩa các kiểu. Trước khi dùng đồng thời `Instant` và `OffsetDateTime`, cần thống nhất cách database và driver biểu diễn chúng để tránh chuyển đổi kép hoặc mất thông tin offset.

Các kiểu thời gian cũ như `java.util.Date` hoặc `java.sql.Timestamp` có thể xuất hiện trong codebase, nhưng `java.time` thường diễn đạt ý nghĩa rõ ràng hơn và nên được ưu tiên trong domain model mới. Khả năng hỗ trợ cụ thể vẫn cần kiểm tra với phiên bản Spring Data và driver.

## 6. UUID, enum và kiểu đặc thù

### 6.1 UUID

`UUID` thường được dùng làm khóa chính hoặc mã định danh phân tán. PostgreSQL có kiểu `UUID` native; database khác có thể lưu dưới dạng chuỗi hoặc binary. Nếu lưu UUID thành `VARCHAR`, cần thống nhất định dạng chuẩn và độ dài cột. Nếu dùng kiểu native, kiểm tra driver có codec cho `UUID` hay không.

### 6.2 Enum

Spring Data thường chuyển enum thành tên hằng dạng chuỗi khi dùng conversion mặc định. Vì vậy, cột `VARCHAR` thường là lựa chọn dễ tương thích:

```java
public enum PaymentStatus {
    PENDING,
    CONFIRMED,
    FAILED
}

@Table("payment")
public class Payment {
    @Id
    private UUID id;

    private PaymentStatus status;
}
```

Lưu tên enum có nghĩa là đổi tên hằng Java có thể ảnh hưởng dữ liệu đã lưu. Nếu cần mã ổn định như `P`, `C` hoặc `F`, hãy dùng thuộc tính mã nghiệp vụ và custom converter. Với native enum type của database, cần kiểm tra codec và conversion tương ứng của driver; không nên giả định enum Java tự động khớp mọi native enum.

### 6.3 JSON và kiểu riêng của database

JSON, JSONB, network address, geometry, interval, range và các kiểu vendor-specific thường cần codec riêng hoặc custom converter. Một số driver cung cấp lớp Java riêng để biểu diễn các kiểu này. Ứng dụng cần phụ thuộc đúng driver và cấu hình conversion tương ứng.

Nếu một kiểu đặc thù chỉ dùng trong một database, nên giữ phần phụ thuộc driver ở tầng persistence. Có thể chuyển kiểu driver thành kiểu domain ổn định thông qua converter để phần nghiệp vụ không phải phụ thuộc trực tiếp vào lớp codec của vendor.

## 7. Collection, array và object phức tạp

Không nên đánh đồng collection Java với SQL array hoặc collection mapping của Spring Data Relational.

- Một thuộc tính `List<OrderLine>` có thể biểu diễn các phần tử thuộc aggregate và thường được ánh xạ bằng `@MappedCollection` vào bảng con.
- Một thuộc tính `List<String>` có thể được lưu thành SQL array nếu database và driver hỗ trợ kiểu array cùng codec tương ứng.
- Một thuộc tính object cần lưu vào một cột có thể cần custom converter, ví dụ serialize thành JSON.
- Một nhóm thuộc tính value object có thể dùng `@Embedded` để trải thành nhiều cột trong cùng hàng.

Lựa chọn phụ thuộc cấu trúc dữ liệu và cách truy vấn. Nếu cần lọc, join hoặc ràng buộc từng phần tử, bảng quan hệ riêng thường thuận tiện hơn. Nếu dữ liệu là một giá trị linh hoạt và ít truy vấn từng phần, JSON hoặc array có thể phù hợp hơn, tùy khả năng database.

## 8. Xử lý NULL và kiểu Java nullable

SQL có giá trị `NULL`, nhưng primitive Java không biểu diễn được trạng thái này. Ví dụ `int` chỉ có một giá trị số tại runtime; nó không thể phân biệt cột `NULL` với số 0 nếu mapping buộc phải gán vào primitive.

Với cột có thể `NULL`, nên dùng wrapper hoặc kiểu tham chiếu:

```java
private Integer retryCount;
private Boolean verified;
private BigDecimal discount;
```

Thay vì:

```java
private int retryCount;
private boolean verified;
```

Nếu cột là `NOT NULL` và domain model có giá trị mặc định rõ ràng, primitive có thể phù hợp. Dù vậy, cần bảo đảm mọi đường ghi đều cung cấp giá trị hợp lệ.

Khi dùng `DatabaseClient`, bind `NULL` cần khai báo kiểu Java vì giá trị null không đủ thông tin để driver suy ra SQL type:

```java
databaseClient.sql("""
        INSERT INTO customer (name, note)
        VALUES (:name, :note)
        """)
    .bind("name", customerName)
    .bindNull("note", String.class)
    .fetch()
    .rowsUpdated();
```

API bind cụ thể có thể khác đôi chút theo phiên bản Spring Framework/Spring R2DBC. Nguyên tắc là khi bind null, phải cung cấp kiểu đích để driver tạo tham số có kiểu phù hợp.

## 9. Khi kiểu Java không được driver hỗ trợ trực tiếp

Nếu Spring Data biết cách ánh xạ entity nhưng driver không biết mã hóa một kiểu Java thành kiểu cột, thao tác có thể thất bại khi bind hoặc đọc kết quả. Một số biểu hiện thường gặp là lỗi codec, lỗi chuyển đổi kiểu, lỗi không hỗ trợ Java type hoặc database báo kiểu tham số không tương thích.

Có thể xử lý theo các hướng sau:

1. Chọn kiểu Java chuẩn được driver hỗ trợ trực tiếp, nếu vẫn giữ đúng ý nghĩa nghiệp vụ.
2. Chọn kiểu cột SQL phổ biến hơn, nếu schema có thể thay đổi.
3. Đăng ký custom converter của Spring Data để chuyển đổi giữa kiểu domain và kiểu đơn giản mà driver hỗ trợ.
4. Dùng codec/kiểu dữ liệu riêng của driver khi cần tận dụng native type của database.
5. Dùng SQL tường minh và projection/row mapping riêng nếu truy vấn trả về cấu trúc đặc biệt.

Custom converter có thể được khai báo theo hai chiều. Ví dụ, domain type `Money` được lưu thành `BigDecimal` trong một cột:

```java
@WritingConverter
public class MoneyWriteConverter implements Converter<Money, BigDecimal> {
    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}

@ReadingConverter
public class MoneyReadConverter implements Converter<BigDecimal, Money> {
    @Override
    public Money convert(BigDecimal source) {
        return new Money(source, "VND");
    }
}
```

Đây là ví dụ minh họa; `Money` là kiểu domain do ứng dụng định nghĩa. Nếu currency có thể thay đổi, không nên hard-code `VND` trong converter mà cần lưu currency code ở cột riêng hoặc chọn cấu trúc embedded phù hợp. Converter đọc và ghi phải có ngữ nghĩa rõ ràng, đặc biệt khi kiểu nguồn và đích có thể được chuyển đổi theo nhiều hướng.

Đăng ký converter trong custom conversions của Spring Data R2DBC. Khi kế thừa `AbstractR2dbcConfiguration`, có thể dùng hook custom converter mà phiên bản Spring Data đang dùng cung cấp. Với cấu hình khác, khai báo custom conversions theo cơ chế được hỗ trợ bởi phiên bản đó. Không chỉ tạo class converter mà quên đăng ký; Spring Data sẽ không tự sử dụng converter chưa được đưa vào cấu hình.

## 10. Phối hợp kiểu Java với schema database

Một entity đơn giản có thể được thiết kế cùng schema như sau. Ví dụ SQL dùng PostgreSQL để minh họa các kiểu native cụ thể:

```sql
CREATE TABLE payment (
    id UUID PRIMARY KEY,
    amount NUMERIC(19, 4) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    paid_on DATE,
    created_at TIMESTAMPTZ NOT NULL,
    receipt BYTEA
);
```

Entity tương ứng:

```java
@Table("payment")
public class Payment {

    @Id
    private UUID id;

    private BigDecimal amount;

    @Column("currency_code")
    private String currencyCode;

    private PaymentStatus status;

    @Column("paid_on")
    private LocalDate paidOn;

    @Column("created_at")
    private Instant createdAt;

    private byte[] receipt;
}
```

Ví dụ giả định PostgreSQL R2DBC driver và phiên bản Spring Data đang dùng hỗ trợ các kiểu Java được chọn. `TIMESTAMPTZ` là cách viết thường dùng của PostgreSQL cho `timestamp with time zone`; database lưu thời điểm theo semantics của kiểu này, không lưu nguyên zone ID của máy khách. Nếu cần zone ID, hãy có cột riêng.

Trong thực tế, schema và entity phải được cập nhật cùng nhau. Khi đổi kiểu Java, cần xem xét migration dữ liệu, độ chính xác, giá trị null hiện có, index, constraint và tương thích với các phiên bản ứng dụng đang chạy song song trong quá trình rollout.

## 11. Cách kiểm tra một kiểu dữ liệu trước khi sử dụng

Khi đưa kiểu Java mới vào entity, hãy xác định:

1. Kiểu đó thuộc nhóm đơn giản được Spring Data hỗ trợ trực tiếp, object cần embedded mapping, collection thuộc aggregate hay kiểu cần converter?
2. Database có kiểu cột nào phù hợp với ý nghĩa và miền giá trị của dữ liệu?
3. R2DBC driver đang dùng có codec cho kiểu Java và kiểu cột đó không?
4. Kiểu dữ liệu có cần giữ precision, scale, offset, zone ID, thứ tự hoặc định dạng đặc biệt không?
5. Cột có cho phép `NULL` không, và kiểu Java có biểu diễn được trạng thái đó không?
6. Nếu dùng custom converter, đã đăng ký cả chiều đọc và ghi phù hợp chưa?
7. Migration schema có tương thích với mapping và dữ liệu đã tồn tại không?

Nên kiểm tra cả hai chiều bằng một thao tác ghi rồi đọc lại trên đúng loại database và driver được triển khai. Kiểm tra các giá trị biên như số lớn nhất, số thập phân nhiều chữ số, chuỗi Unicode, giá trị `NULL`, ngày giờ ở ranh giới múi giờ và dữ liệu nhị phân lớn. Một phép thử chỉ chạy với database giả lập hoặc driver khác có thể không phát hiện khác biệt codec của môi trường thật.

Spring Data R2DBC hỗ trợ ánh xạ nhiều kiểu Java phổ biến sang cột quan hệ, nhưng khả năng cuối cùng được quyết định bởi sự phối hợp giữa mapping metadata, conversion service, R2DBC driver và hệ quản trị cơ sở dữ liệu. Chọn kiểu Java thể hiện đúng ý nghĩa domain, chọn kiểu cột phù hợp và bổ sung converter/codec khi cần sẽ giúp dữ liệu được lưu và đọc nhất quán qua các môi trường triển khai.
