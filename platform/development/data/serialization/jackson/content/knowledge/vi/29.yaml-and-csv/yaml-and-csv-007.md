# Đọc ghi giá trị trống và null theo schema CSV

CSV là định dạng bảng đơn giản: mỗi record là một dòng và mỗi cột là một field được phân tách bằng dấu phân cách. Khác JSON, CSV không có token `null` riêng. Một field rỗng có thể được hiểu là chuỗi rỗng, giá trị null, dữ liệu bị thiếu hoặc giá trị mặc định tùy theo hợp đồng của file.

Khi dùng Jackson CSV, cần định nghĩa rõ schema của dữ liệu: tên và thứ tự cột, kiểu cột, header, cách biểu diễn null, cách xử lý field rỗng và số cột thiếu. Jackson cung cấp `CsvSchema` để mô tả cấu trúc bảng, `CsvMapper` để đọc/ghi CSV và `withNullValue()` để cấu hình chuỗi đại diện cho giá trị null.

Điểm quan trọng là **CSV không tự phân biệt null với empty**. Nếu ứng dụng cần giữ hai trạng thái khác nhau, producer và consumer phải thống nhất một quy ước, ví dụ dùng `\\N` cho null và để field trống cho chuỗi rỗng. Cùng một quy ước phải được áp dụng khi đọc, ghi, kiểm thử và trao đổi file với hệ thống khác.

## 1. CSV không có giá trị null nguyên thủy

JSON có thể biểu diễn rõ ba trường hợp:

```json
{
  "nickname": null,
  "comment": "",
  "status": "ACTIVE"
}
```

CSV thường chỉ có các field dạng text:

```csv
nickname,comment,status
,,ACTIVE
```

Trong dòng CSV trên, hai field đầu đều rỗng. Chỉ nhìn vào file, consumer không thể biết field đầu là null còn field thứ hai là chuỗi rỗng.

Các trạng thái cần phân biệt:

| Trạng thái dữ liệu | Ý nghĩa trong ứng dụng | Vấn đề khi biểu diễn CSV |
|---|---|---|
| Null | Không có giá trị | CSV không có token null chuẩn |
| Empty string | Có giá trị chuỗi với độ dài 0 | Thường cũng được ghi thành field rỗng |
| Missing column | Record không cung cấp cột đó | Khác field có mặt nhưng rỗng |
| Whitespace-only | Có chuỗi gồm khoảng trắng | Có thể bị trim tùy parser/configuration |
| Literal sentinel | Chuỗi thực tế trùng marker null, ví dụ `\\N` | Có thể bị hiểu nhầm thành null nếu không có quy ước escape |

Vì vậy, không nên để mỗi thành phần tự suy đoán ý nghĩa của field rỗng. Hãy định nghĩa quy tắc trong CSV contract hoặc schema tài liệu của hệ thống.

## 2. Jackson CSV: CsvMapper và CsvSchema

Jackson cung cấp module `jackson-dataformat-csv`. Lớp `CsvMapper` là mapper chuyên xử lý CSV; `CsvSchema` mô tả tên, thứ tự và kiểu của các cột.

**Maven:**

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-csv</artifactId>
    <version>${jackson.version}</version>
</dependency>
```

**Gradle:**

```groovy
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-csv:${jacksonVersion}")
```

Nên dùng cùng dòng version Jackson với `jackson-core` và `jackson-databind`, hoặc để Jackson BOM quản lý dependency. Tránh trộn các module khác major/minor không tương thích.

Tạo mapper:

```java
CsvMapper csvMapper = new CsvMapper();
```

Tạo schema:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id", CsvSchema.ColumnType.NUMBER)
    .addColumn("name", CsvSchema.ColumnType.STRING)
    .addColumn("comment", CsvSchema.ColumnType.STRING)
    .addColumn("active", CsvSchema.ColumnType.BOOLEAN)
    .build()
    .withHeader();
```

Schema trên xác định bốn cột theo đúng thứ tự và cho biết dòng đầu chứa header. `ColumnType` giúp Jackson hiểu cách xử lý giá trị của cột, nhưng nó không thay thế quy tắc null/empty của hợp đồng dữ liệu.

## 3. Định nghĩa marker cho null bằng withNullValue()

Để phân biệt null với chuỗi rỗng, có thể dành riêng một chuỗi làm marker. Ví dụ:

- `\\N` biểu diễn null.
- Field rỗng biểu diễn empty string.
- Các field còn lại biểu diễn giá trị thực.

Jackson CSV hỗ trợ cấu hình marker qua `CsvSchema.withNullValue()`:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id", CsvSchema.ColumnType.NUMBER)
    .addColumn("name", CsvSchema.ColumnType.STRING)
    .addColumn("comment", CsvSchema.ColumnType.STRING)
    .build()
    .withHeader()
    .withNullValue("\\N");
```

Với schema này, chuỗi `\\N` là representation được dành cho giá trị null khi Jackson đọc/ghi theo schema. Marker phải được thống nhất với producer và consumer khác; một hệ thống ngoài không biết quy ước này có thể xem `\\N` là chuỗi văn bản thông thường.

### 3.1. Ví dụ CSV phân biệt null và empty

```csv
id,name,comment
1,An,\\N
2,Binh,
3,Chi,Hello
```

Ý nghĩa theo contract:

| id | name | comment trong file | Giá trị Java mong đợi |
|---:|---|---|---|
| 1 | An | `\\N` | `null` |
| 2 | Binh | field rỗng | `""` |
| 3 | Chi | `Hello` | `"Hello"` |

Đây là cách biểu diễn rõ ràng hơn so với dùng field rỗng cho cả null và empty string.

### 3.2. Marker null phải là một giá trị dành riêng

Nếu người dùng thực sự nhập chuỗi `\\N`, Jackson có thể diễn giải nó thành null theo schema. Do đó, marker phải được dành riêng trong contract hoặc có một quy tắc escape riêng cho giá trị văn bản trùng marker.

Ví dụ contract có thể quy định:

- `\\N` không bao giờ là dữ liệu văn bản hợp lệ; nó luôn có nghĩa null.
- Nếu cần lưu đúng chuỗi `\\N`, producer phải escape theo một quy ước được thống nhất trước, hoặc dùng một representation khác.

Không nên dựa vào việc field được quote hay không quote để phân biệt marker null với chuỗi thường nếu chưa xác nhận behavior của đúng CSV parser/version. CSV consumer khác nhau có thể chuẩn hóa quoted và unquoted field theo cách khác nhau.

### 3.3. Chọn marker phù hợp

Marker nên:

- Không trùng với giá trị văn bản hợp lệ thường gặp.
- Dễ nhận diện khi kiểm tra file bằng mắt.
- Được ghi trong tài liệu schema/interface.
- Được dùng nhất quán ở cả chiều đọc và ghi.
- Có quy tắc xử lý rõ nếu dữ liệu thực tế trùng marker.

Các hệ thống thường dùng `\\N`, `NULL` hoặc một sentinel riêng. Không có marker nào là chuẩn chung cho mọi CSV; nó là một phần của contract ứng dụng.

## 4. Ánh xạ CSV vào POJO với null marker

DTO nên dùng kiểu tham chiếu cho những cột có thể null:

```java
public class CustomerRow {
    private Integer id;
    private String name;
    private String comment;

    public CustomerRow() {
    }

    public Integer getId() {
        return id;
    }

    public void setId(Integer id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }
}
```

Schema:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id", CsvSchema.ColumnType.NUMBER)
    .addColumn("name", CsvSchema.ColumnType.STRING)
    .addColumn("comment", CsvSchema.ColumnType.STRING)
    .build()
    .withHeader()
    .withNullValue("\\N");
```

Đọc dữ liệu:

```java
String csv = """
    id,name,comment
    1,An,\\N
    2,Binh,
    3,Chi,Hello
    """;

MappingIterator<CustomerRow> rows = csvMapper
    .readerFor(CustomerRow.class)
    .with(schema)
    .readValues(csv);

List<CustomerRow> customers = rows.readAll();
```

Theo contract marker đã chọn, `comment` của dòng đầu là null; dòng thứ hai là chuỗi rỗng; dòng thứ ba là `Hello`.

### 4.1. Vì sao nên dùng wrapper type như Integer?

Nếu cột có thể null, hãy dùng `Integer`, `Long`, `Boolean` hoặc `BigDecimal` thay cho primitive `int`, `long`, `boolean`.

Primitive không thể giữ null:

```java
private int age;
```

Nếu dữ liệu đầu vào không có giá trị, property primitive có thể giữ default `0` hoặc nhận coercion tùy parser/configuration. Điều này làm mất sự khác biệt giữa “không có giá trị” và “giá trị bằng zero”.

Dùng wrapper type:

```java
private Integer age;
```

giúp model biểu diễn được null. Sau khi đọc, ứng dụng có thể validate xem null có được phép theo contract hay không.

## 5. Đọc CSV thành Map hoặc JsonNode

Khi schema thay đổi hoặc ứng dụng cần xử lý dữ liệu linh hoạt, có thể đọc CSV thành Map thay vì một DTO cố định:

```java
MappingIterator<Map<String, String>> rows = csvMapper
    .readerFor(Map.class)
    .with(schema)
    .readValues(csv);

List<Map<String, String>> values = rows.readAll();
```

Kiểu `Map<String, String>` hữu ích khi muốn giữ nội dung từng cột ở dạng text và tự quyết định conversion sau đó. Tuy nhiên, cần kiểm tra behavior null marker của kiểu đích và phiên bản Jackson đang dùng; nếu cần phân biệt chính xác null/empty, hãy test trực tiếp trên Map cũng như POJO.

Có thể chuyển kết quả Map sang `JsonNode` để xử lý dạng tree:

```java
Map<String, Object> row = csvMapper.convertValue(
    sourceRow,
    new TypeReference<Map<String, Object>>() {}
);

JsonNode node = csvMapper.valueToTree(row);
```

Không nên chuyển qua nhiều representation nếu chỉ cần bind trực tiếp vào DTO. Map/tree hữu ích khi schema động, cần chuẩn hóa key hoặc cần xử lý extension field.

## 6. Ghi POJO ra CSV và giữ null/empty

Khi ghi CSV, `CsvSchema` cũng quyết định representation của null. Dùng cùng marker đã thống nhất:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id", CsvSchema.ColumnType.NUMBER)
    .addColumn("name", CsvSchema.ColumnType.STRING)
    .addColumn("comment", CsvSchema.ColumnType.STRING)
    .build()
    .withHeader()
    .withNullValue("\\N");

CustomerRow first = new CustomerRow();
first.setId(1);
first.setName("An");
first.setComment(null);

CustomerRow second = new CustomerRow();
second.setId(2);
second.setName("Binh");
second.setComment("");

String csv = csvMapper.writer(schema)
    .writeValueAsString(List.of(first, second));
```

Với marker `\\N`, giá trị null được ghi theo null representation đã cấu hình; chuỗi rỗng là một giá trị string rỗng. Hãy kiểm tra output thực tế bằng đúng version Jackson CSV của dự án và đọc lại bằng cùng schema để xác nhận round-trip.

### 6.1. Ghi nhiều record bằng SequenceWriter

Với dữ liệu lớn hoặc muốn ghi tuần tự vào stream/file, có thể dùng `SequenceWriter`:

```java
ObjectWriter writer = csvMapper.writer(schema);

try (SequenceWriter sequence = writer.writeValues(outputStream)) {
    for (CustomerRow row : customers) {
        sequence.write(row);
    }
}
```

Schema có header sẽ ghi header theo cấu hình của writer/schema. Dùng `SequenceWriter` giúp ghi từng record mà không cần gom toàn bộ danh sách thành một object lớn. Tuy nhiên, giới hạn tổng file, số record và thời gian xử lý vẫn cần được quản lý ở tầng ứng dụng.

### 6.2. Không loại bỏ cột chỉ vì giá trị null

CSV là định dạng theo cột. Nếu một row có null ở một cột, thường vẫn cần giữ vị trí cột đó bằng null marker hoặc field rỗng theo contract. Bỏ hẳn field khỏi giữa dòng sẽ làm lệch vị trí các cột tiếp theo.

`CsvSchema` định nghĩa các cột theo thứ tự. Hãy giữ đúng số lượng và vị trí field cho từng record, nhất là khi consumer đọc CSV theo vị trí thay vì header.

## 7. Phân biệt null, empty và missing column

Ba trường hợp này cần được quy định riêng.

### 7.1. Null có marker tường minh

```csv
id,name,comment
1,An,\\N
```

`comment` được gửi rõ ràng với marker null.

### 7.2. Empty field

```csv
id,name,comment
2,Binh,
```

Record có ba cột; cột `comment` hiện diện nhưng không có nội dung. Theo contract đã chọn, đây là chuỗi rỗng.

### 7.3. Missing trailing column

```csv
id,name,comment
3,Chi
```

Record chỉ có hai field, trong khi schema có ba cột. Đây là trường hợp thiếu cột ở cuối dòng, khác với cột thứ ba hiện diện nhưng rỗng.

Jackson CSV có các tùy chọn parser liên quan đến việc xử lý column bị thiếu, chẳng hạn `INSERT_NULLS_FOR_MISSING_COLUMNS` ở các version hỗ trợ. Hành vi mặc định và feature có thể khác theo version; cần quyết định rõ liệu record ngắn hơn schema sẽ bị từ chối, được điền null hay để property không được gán.

Không dùng `withNullValue()` để giải quyết missing column. Null marker chỉ là representation của một field có giá trị sentinel; nó không tự xác định số cột của record.

### 7.4. Missing column ở giữa dòng

CSV dùng dấu phân cách để xác định vị trí. Nếu một cột ở giữa bị thiếu, producer vẫn phải giữ dấu phân cách tương ứng để các giá trị sau không bị dịch sang cột sai.

Ví dụ schema `id,name,comment,status`:

```csv
1,An,,ACTIVE
```

`comment` là field rỗng, còn `status` vẫn ở cột thứ tư. Nếu producer xóa dấu phân cách, parser có thể gán `ACTIVE` vào `comment`, dẫn đến sai dữ liệu.

## 8. Xử lý chuỗi rỗng theo parser feature

Jackson CSV có các parser feature ảnh hưởng cách xử lý field rỗng, chẳng hạn `EMPTY_STRING_AS_NULL` trong các phiên bản hỗ trợ. Feature này có thể làm field rỗng được diễn giải thành null.

Ví dụ bật feature:

```java
CsvMapper mapper = CsvMapper.builder()
    .enable(CsvParser.Feature.EMPTY_STRING_AS_NULL)
    .build();
```

Khi bật, cần kiểm tra cách feature tương tác với `CsvSchema.withNullValue()` và kiểu cột trong đúng phiên bản đang dùng. Nếu contract cần phân biệt null với empty string, không bật một tùy chọn toàn mapper biến mọi field rỗng thành null; dùng marker riêng là cách biểu đạt rõ ràng hơn.

### 8.1. TRIM_SPACES cũng thay đổi dữ liệu

Parser feature `TRIM_SPACES` có thể loại khoảng trắng ở đầu/cuối field. Điều này có nghĩa:

```csv
id,name
1,"  An  "
```

có thể được đọc khác nhau khi trim bật hoặc tắt. Whitespace-only string không giống empty string. Nếu khoảng trắng là dữ liệu có ý nghĩa, không bật trim toàn cục mà không có yêu cầu rõ ràng.

### 8.2. Cấu hình parser là chính sách toàn mapper/schema

Các parser feature thường áp dụng ở phạm vi mapper/parser, không phải một annotation riêng cho từng cột. Nếu cột A cần empty-as-null nhưng cột B cần giữ empty string, một feature toàn mapper có thể quá rộng.

Khi semantics khác nhau theo cột, hãy:

- Dùng null marker tường minh thống nhất nếu contract cho phép.
- Dùng custom deserializer/converter cho property cần quy tắc riêng.
- Đọc vào DTO trung gian dạng string rồi chuẩn hóa theo từng cột.
- Tách schema/mapper theo loại file nếu các contract thực sự khác nhau.

## 9. ColumnType và chuyển đổi giá trị

`CsvSchema.ColumnType` mô tả loại cột mà CSV mapper mong đợi. Các loại thường dùng gồm:

| ColumnType | Dữ liệu dự kiến |
|---|---|
| `STRING` | Text |
| `NUMBER` | Giá trị số |
| `BOOLEAN` | Boolean |
| `ARRAY` | Nội dung collection theo quy ước CSV array của Jackson |

Ví dụ:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id", CsvSchema.ColumnType.NUMBER)
    .addColumn("enabled", CsvSchema.ColumnType.BOOLEAN)
    .addColumn("description", CsvSchema.ColumnType.STRING)
    .build()
    .withHeader()
    .withNullValue("\\N");
```

`ColumnType.NUMBER` không phải giới hạn range nghiệp vụ. Một số có thể đúng cú pháp nhưng vẫn quá lớn hoặc có precision không phù hợp. Hãy dùng kiểu Java phù hợp và validation sau khi đọc.

### 9.1. Dùng wrapper type khi cột có thể null

```java
public class InventoryRow {
    private Long productId;
    private Integer quantity;
    private Boolean active;
}
```

Wrapper types cho phép giữ null. Nếu dùng `long`, `int` hoặc `boolean`, ứng dụng có thể mất thông tin null do primitive không có trạng thái null.

### 9.2. Numeric field rỗng và null marker

Nếu cột `quantity` có thể null, dùng null marker rõ ràng:

```csv
productId,quantity
P-01,10
P-02,\\N
```

Đừng mặc định rằng một numeric field rỗng có cùng semantics ở mọi parser hoặc coercion configuration. Hãy test `\\N`, empty field, zero và giá trị không phải số riêng biệt.

## 10. Schema header, thứ tự cột và strictness

Header giúp ánh xạ theo tên cột:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("name")
    .addColumn("comment")
    .build()
    .withHeader()
    .withNullValue("\\N");
```

CSV:

```csv
id,name,comment
1,An,\\N
```

Khi không có header, schema cần xác định thứ tự cột và việc mapping dựa vào vị trí. Nếu producer đổi thứ tự, dữ liệu có thể bị gán nhầm property.

Với file từ đối tác, hãy xác định:

- Có header hay không.
- Header có bắt buộc khớp chính xác không.
- Cột lạ có được phép không.
- Cột thiếu có bị từ chối hay được điền giá trị không.
- Thứ tự cột có được phép thay đổi không.
- Null marker và empty field được diễn giải thế nào.

Các tùy chọn như strict header handling và parser handling cho missing/trailing columns cần được cấu hình theo contract. Không nên bật chế độ lenient trên mọi file nếu ứng dụng cần phát hiện schema drift.

## 11. Kiểm soát null theo từng cột

`CsvSchema.withNullValue()` đặt marker null cho schema. Trong nhiều hợp đồng CSV, một marker chung như `\\N` là lựa chọn dễ trao đổi nhất.

Nếu một file có semantics khác nhau theo cột, ví dụ:

- `middleName` empty string là giá trị hợp lệ.
- `birthDate` empty field có nghĩa null.
- `comment` dùng `N/A` để biểu diễn không áp dụng.

thì một null marker toàn schema có thể chưa đủ. Không nên ép mọi cột dùng cùng một ý nghĩa cho empty field.

Một cách xử lý là đọc CSV vào DTO trung gian chứa chuỗi:

```java
public class RawCustomerRow {
    private String middleName;
    private String birthDate;
    private String comment;
}
```

Sau đó chuyển đổi theo từng cột:

```java
String middleName = raw.getMiddleName();
String birthDate = raw.getBirthDate().isBlank()
    ? null
    : raw.getBirthDate();
String comment = "N/A".equals(raw.getComment())
    ? null
    : raw.getComment();
```

Đây chỉ là ví dụ đơn giản; code production cần kiểm tra null trước khi gọi `isBlank()` và định nghĩa có trim hay không. Tách bước parse thô và normalize theo cột giúp semantics rõ ràng, dễ test và không buộc parser toàn cục phải đoán nghiệp vụ.

## 12. Null marker và CSV escaping

CSV có quy tắc quote/escape cho dấu phẩy, dấu quote và newline nằm trong field. Ví dụ:

```csv
id,comment
1,"Contains, comma"
2,"Contains ""quotes"""
```

Quote giúp giữ dấu phẩy và dấu quote bên trong một field. Nhưng quote không tự tạo một null type chuẩn. Một field được quote thành `""` vẫn thường là empty string theo semantics CSV phổ biến; đừng dùng quote để thay thế null marker nếu producer/consumer chưa thống nhất.

Khi marker null có thể xuất hiện như dữ liệu thật, cần một quy tắc escape ở cấp contract. Ví dụ contract có thể dành riêng `\\N` và quy định giá trị văn bản bắt đầu bằng backslash phải được escape. Jackson CSV không thể tự suy ra quy tắc nghiệp vụ này nếu ứng dụng không triển khai.

Hãy test các trường hợp:

- Null marker `\\N`.
- Chuỗi rỗng.
- Chuỗi literal `\\N` nếu contract cho phép.
- Chuỗi có dấu phẩy.
- Chuỗi có dấu quote.
- Chuỗi có newline.
- Chuỗi có khoảng trắng đầu/cuối.

## 13. Đọc và ghi với cùng một schema

Để round-trip không mất thông tin, dùng cùng quy ước schema khi ghi và đọc:

```java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id", CsvSchema.ColumnType.NUMBER)
    .addColumn("name", CsvSchema.ColumnType.STRING)
    .addColumn("comment", CsvSchema.ColumnType.STRING)
    .build()
    .withHeader()
    .withNullValue("\\N");

CustomerRow row = new CustomerRow();
row.setId(1);
row.setName("An");
row.setComment(null);

String csv = csvMapper.writer(schema).writeValueAsString(row);

CustomerRow restored = csvMapper.readerFor(CustomerRow.class)
    .with(schema)
    .readValue(csv);
```

Nếu writer dùng `\\N` nhưng reader không cấu hình cùng marker, giá trị có thể trở thành chuỗi literal thay vì null. Ngược lại, nếu reader dành `\\N` cho null nhưng writer ghi chuỗi văn bản `\\N` mà không escape, dữ liệu có thể bị mất.

Nên đóng gói schema vào một thành phần dùng chung:

```java
public final class CustomerCsvFormat {
    private CustomerCsvFormat() {
    }

    public static CsvSchema schema() {
        return CsvSchema.builder()
            .addColumn("id", CsvSchema.ColumnType.NUMBER)
            .addColumn("name", CsvSchema.ColumnType.STRING)
            .addColumn("comment", CsvSchema.ColumnType.STRING)
            .build()
            .withHeader()
            .withNullValue("\\N");
    }
}
```

Producer và consumer nội bộ cùng gọi `CustomerCsvFormat.schema()` để tránh cấu hình lệch nhau. Với đối tác ngoài, schema/marker cần được ghi rõ trong tài liệu giao tiếp.

## 14. Xử lý CSV thiếu cột và cột dư

Số field trong mỗi record cần phù hợp với schema. Ví dụ schema có ba cột:

```csv
id,name,comment
1,An,Hello
2,Binh
```

Dòng thứ hai thiếu field cuối. Đây không phải cùng trường hợp với:

```csv
id,name,comment
1,An,Hello
2,Binh,
```

Ở dòng thứ hai của ví dụ sau, field `comment` có mặt nhưng rỗng.

Jackson CSV có các parser option liên quan đến missing columns và trailing columns. Tùy version, có thể chọn chèn null cho cột thiếu, bỏ qua field dư hoặc báo lỗi. Hãy đọc Javadoc của đúng version và chọn policy rõ ràng; không dựa vào behavior mặc định khi file là contract quan trọng.

Với import tài chính hoặc dữ liệu định danh, thường nên từ chối record sai số cột để tránh dịch dữ liệu. Với feed mở rộng có version schema, có thể chấp nhận cột mới theo một cơ chế được quản lý và ghi nhận.

## 15. Tích hợp validation sau khi đọc CSV

CSV schema kiểm soát cấu trúc cột và parser conversion. Bean Validation có thể kiểm tra giá trị Java sau khi bind:

```java
public class CustomerRow {
    @NotNull
    @Positive
    private Integer id;

    @NotBlank
    @Size(max = 80)
    private String name;

    @Size(max = 500)
    private String comment;
}
```

Sau khi đọc record:

```java
for (CustomerRow row : rows) {
    Set<ConstraintViolation<CustomerRow>> violations = validator.validate(row);
    if (!violations.isEmpty()) {
        // Ghi nhận row number và các field vi phạm
    }
}
```

Phân biệt các lớp kiểm tra:

- `CsvSchema`: tên/thứ tự/kiểu cột và marker null.
- CSV parser: cú pháp CSV, quote/escape, số cột và parser feature.
- Bean Validation: null, empty, độ dài, range và constraint trên object.
- Domain layer: quy tắc nghiệp vụ như mã khách hàng có tồn tại hay không.

Không nên dùng empty/null parser feature để thay thế validation bắt buộc. Ví dụ, nếu `name` không được null hoặc blank, dùng `@NotBlank` và trả lỗi theo row/column rõ ràng.

## 16. Hiệu năng và đọc file lớn

Với file CSV lớn, không nên luôn gọi `readAll()` nếu không cần giữ toàn bộ record trong bộ nhớ. Dùng `MappingIterator` để đọc tuần tự:

```java
try (MappingIterator<CustomerRow> iterator = csvMapper
        .readerFor(CustomerRow.class)
        .with(schema)
        .readValues(inputStream)) {

    long rowNumber = 1; // Header là dòng đầu nếu schema.withHeader() được dùng.
    while (iterator.hasNextValue()) {
        CustomerRow row = iterator.nextValue();
        rowNumber++;
        process(row, rowNumber);
    }
}
```

Đọc tuần tự giúp giới hạn bộ nhớ cho batch lớn. Vẫn cần giới hạn kích thước file, số record, độ dài field và thời gian xử lý ở tầng import.

Nếu ghi file lớn, dùng `SequenceWriter` và `OutputStream` thay vì gom tất cả output thành một `String`.

## 17. Những lỗi thường gặp

**Cho rằng CSV có null literal chuẩn.** CSV không có token null phổ quát. Định nghĩa marker như `\\N` trong contract và cấu hình `withNullValue()`.

**Dùng field rỗng cho cả null và empty string.** Thông tin bị mất. Dùng marker riêng nếu cần phân biệt.

**Cấu hình null marker khi ghi nhưng quên cấu hình khi đọc.** Writer và reader phải dùng cùng schema/marker.

**Cho rằng quote phân biệt null và empty.** Quoted empty và unquoted empty thường cùng là empty field theo semantics CSV phổ biến. Không dựa vào quote nếu chưa kiểm tra parser/contract.

**Dùng `int` hoặc `boolean` cho cột có thể null.** Primitive không giữ null. Dùng `Integer`/`Boolean` nếu cần biểu diễn absent/null.

**Nhầm missing column với empty field.** Record ngắn hơn schema khác với record có dấu phân cách nhưng field rỗng. Xác định parser policy cho missing/trailing columns.

**Bật `EMPTY_STRING_AS_NULL` trên mapper dùng chung.** Feature có thể biến empty thành null ở phạm vi rộng và làm mất chuỗi rỗng có ý nghĩa. Chỉ bật khi contract yêu cầu.

**Bật `TRIM_SPACES` mà không xem whitespace là dữ liệu.** Khoảng trắng có thể có ý nghĩa. Trim là một thay đổi dữ liệu, không chỉ là tiện ích hiển thị.

**Cho rằng ColumnType.NUMBER giới hạn range nghiệp vụ.** ColumnType mô tả kiểu cột; dùng kiểu Java và validation để kiểm tra range/precision.

**Không xử lý marker collision.** Nếu chuỗi thực tế bằng marker null, reader có thể hiểu nhầm thành null. Dành riêng marker hoặc định nghĩa escape.

**Gom file lớn vào List/String.** Dùng `MappingIterator` và `SequenceWriter` để xử lý tuần tự khi cần.

## 18. Kiểm thử null và empty theo schema

Hãy kiểm thử tối thiểu các trường hợp:

| Input field | Kết quả mong muốn theo contract marker `\\N` |
|---|---|
| `\\N` | null |
| Field rỗng | `""` |
| `hello` | `"hello"` |
| `0` trong cột number | Số 0 |
| `\\N` trong cột number | null nếu marker/schema được hỗ trợ cho cột đó |
| Field thiếu ở cuối row | Theo missing-column policy đã cấu hình |
| Field dư | Theo strictness policy đã cấu hình |
| Chuỗi chỉ có spaces | Giữ nguyên hoặc trim theo contract |
| Literal marker trong dữ liệu thật | Theo quy tắc escape/dành riêng marker |

Ví dụ JUnit minh họa đọc null marker và empty string:

```java
class CustomerCsvTest {
    private final CsvMapper mapper = new CsvMapper();

    private final CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name", CsvSchema.ColumnType.STRING)
        .addColumn("comment", CsvSchema.ColumnType.STRING)
        .build()
        .withHeader()
        .withNullValue("\\N");

    @Test
    void readsNullMarkerAndEmptyStringDifferently() throws Exception {
        String csv = """
            id,name,comment
            1,An,\\N
            2,Binh,
            """;

        List<CustomerRow> rows = mapper.readerFor(CustomerRow.class)
            .with(schema)
            .<CustomerRow>readValues(csv)
            .readAll();

        assertNull(rows.get(0).getComment());
        assertEquals("", rows.get(1).getComment());
    }
}
```

Đây là ví dụ kiểm thử cho contract đã chọn; hãy chạy với version Jackson CSV thực tế và xác nhận parser xử lý marker/empty đúng như mong đợi. Nếu một version hoặc kiểu đích có behavior khác, điều chỉnh schema/parser feature hoặc dùng DTO trung gian để giữ semantics rõ ràng.

### 18.1. Test round-trip

```java
@Test
void writesAndReadsNullWithoutLosingEmptyString() throws Exception {
    CustomerRow nullComment = new CustomerRow();
    nullComment.setId(1);
    nullComment.setName("An");
    nullComment.setComment(null);

    CustomerRow emptyComment = new CustomerRow();
    emptyComment.setId(2);
    emptyComment.setName("Binh");
    emptyComment.setComment("");

    String csv = mapper.writer(schema)
        .writeValueAsString(List.of(nullComment, emptyComment));

    List<CustomerRow> restored = mapper.readerFor(CustomerRow.class)
        .with(schema)
        .<CustomerRow>readValues(csv)
        .readAll();

    assertNull(restored.get(0).getComment());
    assertEquals("", restored.get(1).getComment());
}
```

Round-trip là kiểm tra quan trọng vì một cấu hình có thể đọc được file của đối tác nhưng writer lại tạo representation khác. Nếu CSV được trao đổi giữa nhiều hệ thống, hãy có fixture do producer thật tạo ra và kiểm tra cả file do ứng dụng xuất.

## 19. Quy trình thiết kế CSV null/empty

1. Xác định mỗi cột có thể nhận null, empty string, whitespace hay không.
2. Xác định field thiếu có khác null/empty hay không.
3. Chọn marker null dành riêng, ví dụ `\\N`, nếu cần phân biệt null với empty.
4. Ghi marker vào CSV contract và quy định cách xử lý literal trùng marker.
5. Khai báo `CsvSchema` với đúng tên, thứ tự và `ColumnType` của từng cột.
6. Dùng `withHeader()` khi file có header và xác định strictness cho header/cột dư/thiếu.
7. Dùng `withNullValue()` nhất quán cho reader và writer.
8. Chỉ bật parser feature empty-as-null hoặc trim-spaces khi contract yêu cầu rõ.
9. Dùng wrapper type cho cột có thể null.
10. Validate range, required và độ dài sau khi bind; dùng domain logic cho kiểm tra nghiệp vụ.
11. Dùng `MappingIterator`/`SequenceWriter` cho file lớn.
12. Test null marker, empty, missing, extra, whitespace, quote, delimiter, numeric zero và round-trip trên đúng version Jackson CSV.

## Kết luận

CSV không có token null chuẩn nên Jackson cần một quy ước để phân biệt null với chuỗi rỗng. `CsvSchema.withNullValue()` cho phép dành riêng một marker như `\\N`; field rỗng có thể giữ ý nghĩa empty string theo contract. `CsvSchema` đồng thời mô tả tên, thứ tự và `ColumnType` của cột, còn `CsvMapper` đọc/ghi dữ liệu theo schema đó. Cần tách null, empty, whitespace và missing column; dùng wrapper type khi giá trị có thể null; chỉ bật parser feature như `EMPTY_STRING_AS_NULL` hoặc `TRIM_SPACES` khi hợp đồng yêu cầu. Reader và writer phải dùng cùng schema/marker, đồng thời cần kiểm thử round-trip và các trường hợp thiếu/dư cột để tránh mất hoặc dịch dữ liệu.
