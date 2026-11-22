# Đọc ghi nhiều dòng CSV theo từng bản ghi

CSV thường được dùng để trao đổi dữ liệu dạng bảng: đơn hàng, khách hàng, danh sách sản phẩm, dữ liệu kế toán hoặc file import/export từ hệ thống đối tác. Khi file chỉ có vài chục dòng, đọc toàn bộ thành một danh sách rồi xử lý có thể đơn giản. Nhưng với file lớn, cách đó làm tăng bộ nhớ sử dụng, khiến ứng dụng khó kiểm soát lỗi từng bản ghi và khó duy trì luồng xử lý ổn định.

Jackson CSV cung cấp module `jackson-dataformat-csv` để ánh xạ giữa bản ghi CSV và kiểu Java. Hai API quan trọng cho xử lý nhiều bản ghi theo luồng là `MappingIterator<T>` khi đọc và `SequenceWriter` khi ghi. Chúng cho phép ứng dụng xử lý từng record tuần tự mà không cần tạo một collection chứa toàn bộ file.

Khi làm việc với CSV, cần nhớ rằng một record logic không nhất thiết tương ứng với một dòng vật lý. Một field được đặt trong dấu nháy có thể chứa dấu phẩy hoặc ký tự xuống dòng. Vì vậy, hãy để parser CSV xác định ranh giới record, thay vì tự chia file bằng `readLine()` hoặc `split(",")`.

## 1. CSV gồm nhiều record và field

Một file CSV cơ bản có thể có header và nhiều record:

~~~csv
orderId,customer,quantity,unitPrice
ORD-1001,Lan,2,125000.50
ORD-1002,Minh,1,89000.00
ORD-1003,An,4,45000.00
~~~

Mỗi record gồm các field phân tách bằng dấu phẩy. Header mô tả tên cột, các record tiếp theo chứa dữ liệu.

CSV không có hệ thống kiểu dữ liệu phong phú như JSON hoặc XML. Về bản chất, field thường được đọc từ văn bản rồi chuyển đổi sang kiểu Java theo schema và target type. Ví dụ:

- `orderId` được ánh xạ thành `String`.
- `quantity` được chuyển thành `int`.
- `unitPrice` được chuyển thành `BigDecimal`.
- Ngày tháng có thể cần định dạng cụ thể.
- Field rỗng cần một chính sách riêng: chuỗi rỗng, null, giá trị mặc định hay lỗi validation.

Không nên giả định mọi file CSV đều có cùng dấu phân cách, encoding, quy tắc quote hoặc header. Hợp đồng file cần xác định các quy tắc này trước khi parse.

## 2. Vì sao xử lý theo từng bản ghi?

Giả sử file có vài triệu record. Cách đọc tất cả vào `List<OrderRow>` sẽ tạo một object cho mỗi record và giữ chúng trong heap cho tới khi xử lý xong:

~~~java
List<OrderRow> rows = mapper
    .readerFor(OrderRow.class)
    .with(schema)
    .<OrderRow>readValues(input)
    .readAll();

for (OrderRow row : rows) {
    process(row);
}
~~~

Cách này dễ viết nhưng có một số hạn chế:

- Bộ nhớ tăng theo số lượng record.
- Thời gian chờ trước khi xử lý record đầu tiên có thể dài.
- Một lỗi ở record sau có thể làm cả thao tác đọc danh sách thất bại.
- Khó áp dụng backpressure hoặc batch commit.
- Không phù hợp với file lớn hơn nhiều so với heap khả dụng.

Đọc theo từng record giúp bộ nhớ gần như không phụ thuộc tổng số dòng, nếu ứng dụng không giữ lại những record đã xử lý:

~~~text
CSV input
   |
   v
CsvMapper / parser
   |
   v
MappingIterator<OrderRow>
   |
   +--> record 1 --> validate --> process
   |
   +--> record 2 --> validate --> process
   |
   +--> record 3 --> validate --> process
   |
   +--> ...
~~~

Mỗi lần gọi `nextValue()` lấy ra một record tiếp theo. Ứng dụng có thể validate, ghi database, phát event hoặc ghi kết quả rồi giải phóng tham chiếu tới record trước.

## 3. Thêm Jackson CSV dependency

Với Gradle, khai báo module CSV cùng dòng phiên bản Jackson đang được dự án quản lý:

~~~gradle
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-csv")
}
~~~

Nếu dự án không dùng BOM hoặc dependency management, cần khai báo version tương thích với `jackson-core`, `jackson-annotations` và `jackson-databind`. Không trộn các phiên bản Jackson khác nhau trong cùng runtime.

Các import chính:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;
import com.fasterxml.jackson.databind.MappingIterator;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.SequenceWriter;
~~~

`CsvMapper` mở rộng Databind cho định dạng CSV. Nó dùng `CsvSchema` để xác định tên cột, thứ tự cột, header và một số quy tắc định dạng CSV.

## 4. Tạo DTO cho một record

Mỗi CSV record thường được ánh xạ thành một object Java. Ví dụ:

~~~java
import java.math.BigDecimal;

public class OrderRow {
    private String orderId;
    private String customer;
    private int quantity;
    private BigDecimal unitPrice;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public String getCustomer() {
        return customer;
    }

    public void setCustomer(String customer) {
        this.customer = customer;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}
~~~

DTO nên phản ánh hợp đồng CSV, không nhất thiết là entity JPA. Việc dùng một kiểu trung gian giúp tách parsing và validation khỏi persistence model. Nó cũng tránh để CSV field trực tiếp thay đổi entity hoặc các thuộc tính nhạy cảm.

Với Java record, Jackson CSV có thể hỗ trợ record tùy phiên bản Databind và cấu hình creator. Nếu gặp vấn đề constructor/parameter name hoặc version compatibility, JavaBean DTO với getter/setter là một lựa chọn đơn giản và dễ tương thích.

## 5. Khai báo schema có header

Khi file có header, schema cần biết header sẽ được đọc từ record đầu tiên. Có thể tạo schema từ DTO:

~~~java
CsvMapper mapper = new CsvMapper();

CsvSchema schema = mapper
    .schemaFor(OrderRow.class)
    .withHeader();
~~~

`schemaFor(OrderRow.class)` tạo schema dựa trên property mà Jackson nhận diện. `withHeader()` bật chế độ dùng hàng đầu làm header.

Đọc file theo từng record:

~~~java
try (Reader input = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8)) {

    ObjectReader reader = mapper
        .readerFor(OrderRow.class)
        .with(schema);

    try (MappingIterator<OrderRow> rows = reader.readValues(input)) {
        while (rows.hasNextValue()) {
            OrderRow row = rows.nextValue();
            process(row);
        }
    }
}
~~~

Các bước:

1. Mở file bằng `Reader` với encoding đã thống nhất, ví dụ UTF-8.
2. Tạo `ObjectReader` cho kiểu record.
3. Gắn `CsvSchema` có header.
4. Gọi `readValues(input)` để nhận `MappingIterator`.
5. Lặp `hasNextValue()` và `nextValue()`.
6. Xử lý xong từng record rồi chuyển sang record tiếp theo.
7. Đóng iterator và input khi hoàn tất hoặc khi có lỗi.

`MappingIterator` là abstraction quan trọng cho đọc nhiều giá trị từ một nguồn. Không gọi `readAll()` nếu mục tiêu là giữ bộ nhớ thấp, vì phương thức đó materialize các record thành collection.

## 6. Dùng schema rỗng khi header quyết định tên cột

Nếu tên cột trong file là nguồn quyết định và thứ tự cột có thể khác nhau, có thể dùng schema chỉ bật header:

~~~java
CsvSchema schema = CsvSchema.emptySchema().withHeader();

ObjectReader reader = mapper
    .readerFor(OrderRow.class)
    .with(schema);
~~~

Parser đọc header để xác định tên cột tương ứng với property. Cách này hữu ích khi file có cùng tập tên cột nhưng producer có thể đổi thứ tự.

Ví dụ file A:

~~~csv
orderId,customer,quantity,unitPrice
ORD-1,Lan,2,100.00
~~~

File B:

~~~csv
customer,unitPrice,orderId,quantity
Lan,100.00,ORD-1,2
~~~

Với header-based schema, parser có thể ánh xạ theo tên cột thay vì phụ thuộc vị trí cố định, miễn tên cột khớp với property hoặc alias mà Jackson nhận diện.

Nếu cần kiểm soát chặt danh sách cột, hãy khai báo schema rõ ràng và kiểm tra header trước khi xử lý dữ liệu. Đừng dựa vào việc một parser tolerant sẽ tự phát hiện mọi typo ở header.

## 7. Đọc CSV không có header

Một số hệ thống xuất file không có header:

~~~csv
ORD-1001,Lan,2,125000.50
ORD-1002,Minh,1,89000.00
~~~

Trong trường hợp này, thứ tự cột là một phần của hợp đồng. Tạo schema theo đúng thứ tự:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("orderId")
    .addColumn("customer")
    .addColumn("quantity")
    .addColumn("unitPrice")
    .build();
~~~

Sau đó đọc:

~~~java
ObjectReader reader = mapper
    .readerFor(OrderRow.class)
    .with(schema);

try (MappingIterator<OrderRow> rows = reader.readValues(input)) {
    while (rows.hasNextValue()) {
        process(rows.nextValue());
    }
}
~~~

Không bật `withHeader()` khi file không có header. Nếu bật nhầm, record dữ liệu đầu tiên có thể bị hiểu là tên cột và bị mất khỏi dữ liệu thực tế.

Khi không có header, việc thay đổi thứ tự cột là thay đổi hợp đồng. Nên lưu schema/version của file trong metadata, tên file hoặc manifest import để chọn đúng cấu hình.

## 8. Đọc từng record bằng MappingIterator

`MappingIterator<T>` cung cấp các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `hasNextValue()` | Kiểm tra còn record có thể đọc; có thể ném `IOException` |
| `nextValue()` | Đọc và trả về record tiếp theo |
| `hasNext()` | Kiểm tra còn phần tử theo giao diện Iterator |
| `next()` | Lấy phần tử tiếp theo theo giao diện Iterator |
| `readAll()` | Đọc tất cả phần còn lại vào collection |
| `close()` | Đóng parser/tài nguyên đọc mà iterator sở hữu |

Đối với luồng đọc có thể phát sinh I/O hoặc lỗi mapping, `hasNextValue()` và `nextValue()` cho phép xử lý lỗi bằng `IOException` rõ ràng. Ví dụ:

~~~java
try (MappingIterator<OrderRow> rows = reader.readValues(input)) {
    while (rows.hasNextValue()) {
        OrderRow row = rows.nextValue();
        process(row);
    }
}
~~~

Nếu cần giữ số record đã xử lý, dùng bộ đếm tăng sau mỗi record đọc thành công. Đừng giả định số record bằng số dòng vật lý của file, vì field có thể chứa newline bên trong dấu quote.

## 9. CSV record không đồng nghĩa với dòng vật lý

CSV cho phép field có dấu phẩy, dấu quote và newline nếu được quote đúng cách. Ví dụ:

~~~csv
id,description,amount
1,"Book, Java edition",100.00
2,"Line one
Line two",200.00
3,"He said ""hello""",50.00
~~~

Record thứ hai trải dài trên hai dòng vật lý nhưng vẫn là một record CSV. Record thứ ba chứa dấu quote được escape bằng cách nhân đôi dấu quote.

Vì vậy, không nên làm:

~~~java
// Sai cho CSV tổng quát.
String line;
while ((line = bufferedReader.readLine()) != null) {
    String[] columns = line.split(",");
    process(columns);
}
~~~

Đoạn code này hỏng khi field có dấu phẩy, quote hoặc newline. Nó cũng không xử lý đầy đủ các quy tắc escaping và encoding.

Hãy để `CsvMapper` và parser CSV quản lý ranh giới record. Trong log, nên phân biệt:

- Record index: thứ tự record logic trong file.
- Physical line: dòng văn bản mà parser đang đọc, nếu parser cung cấp thông tin đó.

Khi báo lỗi, record index thường là thông tin ổn định hơn cho người dùng file CSV.

## 10. Kiểm tra và validate từng record

Parsing thành công không đồng nghĩa dữ liệu nghiệp vụ hợp lệ. Sau khi Jackson tạo `OrderRow`, ứng dụng cần kiểm tra các quy tắc:

~~~java
private void validate(OrderRow row, long recordNumber) {
    if (row.getOrderId() == null || row.getOrderId().isBlank()) {
        throw new InvalidCsvRecordException(
            recordNumber,
            "orderId is required"
        );
    }

    if (row.getQuantity() <= 0) {
        throw new InvalidCsvRecordException(
            recordNumber,
            "quantity must be greater than zero"
        );
    }

    if (row.getUnitPrice() == null
            || row.getUnitPrice().signum() < 0) {
        throw new InvalidCsvRecordException(
            recordNumber,
            "unitPrice must be zero or positive"
        );
    }
}
~~~

Có thể dùng Bean Validation:

~~~java
public class OrderRow {
    @NotBlank
    private String orderId;

    @NotBlank
    private String customer;

    @Positive
    private int quantity;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal unitPrice;

    // Getter và setter.
}
~~~

Sau khi parse, gọi `Validator.validate(row)` cho từng record. Jackson CSV không tự chạy Bean Validation chỉ vì DTO có annotation. Ứng dụng cần gọi validator hoặc thực hiện validation trong một bước riêng.

Nếu dùng primitive như `int`, cần cân nhắc trường hợp cột thiếu/rỗng có thể dẫn tới giá trị mặc định hoặc lỗi coercion theo cấu hình. Với dữ liệu import cần phân biệt thiếu và zero, wrapper `Integer` hoặc DTO field dạng `String` ở bước raw parsing có thể giúp biểu diễn rõ hơn.

## 11. Phân biệt field rỗng, null và thiếu cột

CSV không có cú pháp null thống nhất. Các trường hợp sau có thể mang ý nghĩa khác nhau:

~~~csv
id,name,comment
1,Lan,
2,Minh,""
3,An,NULL
4,Binh,hello
~~~

Tùy schema và parser feature, field trống hoặc `""` có thể được ánh xạ thành chuỗi rỗng, null hoặc một giá trị khác. Chuỗi `NULL` thường chỉ là văn bản literal trừ khi ứng dụng tự quy định.

Cần xác định hợp đồng:

- Empty field có nghĩa là chuỗi rỗng hay null?
- Cột không có trong header có được phép không?
- Record thiếu cột cuối có được chấp nhận không?
- Cột thừa có bị từ chối hay bỏ qua?
- Giá trị `NULL`, `N/A` hoặc `-` có quy ước đặc biệt không?

Jackson CSV có các feature cho việc xử lý cột thiếu, cột thừa, dòng trống và giá trị rỗng. Tên và hành vi cụ thể cần kiểm tra theo phiên bản module đang dùng. Không nên bật các feature tolerant mà không kiểm thử trường hợp biên.

Nếu file đến từ đối tác và null semantics quan trọng, hãy chuẩn hóa bằng một lớp import rõ ràng hoặc giữ raw field dạng string rồi chuyển đổi theo quy tắc nghiệp vụ.

## 12. Ghi nhiều record theo luồng bằng SequenceWriter

Khi xuất CSV, không cần tạo một chuỗi khổng lồ trong bộ nhớ. `SequenceWriter` ghi từng object nối tiếp vào một generator.

Tạo schema có header:

~~~java
CsvSchema schema = mapper
    .schemaFor(OrderRow.class)
    .withHeader();
~~~

Ghi từng record:

~~~java
try (Writer output = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8);
     SequenceWriter rows = mapper.writer(schema).writeValues(output)) {

    for (OrderRow row : orderRows) {
        rows.write(row);
    }
}
~~~

`writeValues(output)` tạo writer cho nhiều root values liên tiếp. Mỗi lần gọi `write(row)`, Jackson ghi một CSV record theo schema. Nếu schema có header, header được ghi theo cấu hình của schema khi sequence bắt đầu.

Với một nguồn dữ liệu lớn, hãy lấy record theo từng trang hoặc từng batch rồi ghi tuần tự:

~~~java
try (Writer output = Files.newBufferedWriter(path, StandardCharsets.UTF_8);
     SequenceWriter rows = mapper.writer(schema).writeValues(output)) {

    int page = 0;
    while (true) {
        List<OrderRow> batch = repository.fetchPage(page++, 500);
        if (batch.isEmpty()) {
            break;
        }

        for (OrderRow row : batch) {
            rows.write(row);
        }
    }
}
~~~

Ví dụ trên giữ mỗi batch khoảng 500 record trong bộ nhớ. Có thể thay repository paging bằng cursor/stream nếu tầng dữ liệu hỗ trợ. Cần quản lý transaction và tài nguyên database phù hợp với thời gian xuất file.

### 12.1. Ghi tất cả bằng một lần gọi

Với dữ liệu nhỏ đã có sẵn trong collection, `ObjectWriter` cũng có thể ghi nhiều giá trị:

~~~java
mapper.writer(schema).writeValue(output, orderRows);
~~~

Đây là cách ngắn gọn khi dữ liệu đã có trong bộ nhớ. Khi cần kiểm soát rõ việc lấy và ghi từng record, `SequenceWriter` thể hiện luồng streaming trực tiếp hơn.

Không nên gọi `writeValueAsString()` cho từng record rồi nối các chuỗi bằng dấu phẩy. CSV cần quản lý quote, escape, line separator và header; để Jackson ghi toàn bộ record qua schema.

## 13. Schema khi ghi có header và không có header

Có header:

~~~java
CsvSchema schema = mapper
    .schemaFor(OrderRow.class)
    .withHeader();
~~~

Không có header:

~~~java
CsvSchema schema = mapper.schemaFor(OrderRow.class);
~~~

Hoặc khai báo thứ tự cột rõ ràng:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("orderId")
    .addColumn("customer")
    .addColumn("quantity")
    .addColumn("unitPrice")
    .build();
~~~

Schema quyết định thứ tự và tên cột. Với hợp đồng tích hợp, nên dùng schema tường minh để tránh việc thêm property vào DTO vô tình làm thay đổi output CSV.

Nếu schema được tạo từ class, thứ tự property phụ thuộc introspection và cấu hình Jackson. Hãy kiểm tra header và thứ tự cột bằng test contract, nhất là khi file được consumer khác sử dụng.

## 14. Cấu hình dấu phân cách, quote và line separator

CSV thường dùng dấu phẩy, nhưng một số file dùng dấu chấm phẩy hoặc tab. Có thể cấu hình `CsvSchema` với separator phù hợp:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("orderId")
    .addColumn("customer")
    .addColumn("quantity")
    .setColumnSeparator(';')
    .build()
    .withHeader();
~~~

Các quy tắc quote/escape và line separator cũng thuộc schema/parser configuration. Jackson CSV cung cấp các phương thức cấu hình schema tương ứng, nhưng API cụ thể có thể thay đổi theo phiên bản. Hãy kiểm tra Javadoc của `CsvSchema` trong dependency đang dùng và kiểm thử bằng file mẫu thực tế.

Ví dụ CSV dùng dấu chấm phẩy:

~~~csv
orderId;customer;quantity
ORD-1;Lan;2
ORD-2;Minh;1
~~~

Không tự thay dấu phẩy bằng dấu chấm phẩy trên chuỗi CSV sau khi ghi. Dữ liệu field có thể chứa cả hai ký tự; separator phải được cấu hình ở parser/writer.

Nếu consumer yêu cầu CRLF (`\r\n`) hoặc một kiểu quote cụ thể, hãy cấu hình line separator/quote char ở schema hoặc writer tương ứng. Kiểm tra cả byte output và khả năng đọc lại bằng parser của consumer.

## 15. Xử lý lỗi khi đọc theo record

Lỗi có thể xảy ra ở nhiều cấp:

- Lỗi cú pháp CSV: quote không đóng, dấu phân cách sai hoặc dữ liệu bị cắt.
- Lỗi mapping: giá trị không chuyển được sang kiểu Java.
- Lỗi validation: record parse được nhưng vi phạm quy tắc nghiệp vụ.
- Lỗi hạ tầng: stream đọc bị ngắt hoặc file không truy cập được.

Khi dùng `MappingIterator`, lỗi có thể xuất hiện khi gọi `hasNextValue()` hoặc `nextValue()`. Bao quanh vòng lặp bằng xử lý lỗi phù hợp:

~~~java
long recordNumber = 0;

try (MappingIterator<OrderRow> rows = reader.readValues(input)) {
    while (rows.hasNextValue()) {
        OrderRow row = rows.nextValue();
        recordNumber++;

        validate(row, recordNumber);
        process(row);
    }
} catch (IOException exception) {
    throw new CsvImportException(
        "Could not read CSV near record " + (recordNumber + 1),
        exception
    );
}
~~~

`recordNumber + 1` chỉ là ước lượng record đang đọc nếu lỗi xảy ra trong parser trước khi `nextValue()` trả về. Với thông báo chính xác hơn, có thể khai thác location/line metadata từ exception hoặc parser nếu phiên bản cung cấp. Nhớ rằng physical line có thể khác logical record number.

Không bắt `Exception` quá rộng quanh toàn bộ import rồi đổi tất cả thành “CSV không hợp lệ”. Lỗi từ `process(row)` có thể là lỗi database hoặc lỗi nghiệp vụ; phân loại riêng để không báo sai nguyên nhân.

## 16. Tiếp tục hay dừng khi một record lỗi?

Có hai chính sách import phổ biến.

### 16.1. Fail fast

Dừng toàn bộ import khi gặp record đầu tiên không hợp lệ:

~~~java
while (rows.hasNextValue()) {
    OrderRow row = rows.nextValue();
    validate(row, recordNumber);
    process(row);
}
~~~

Phù hợp khi:

- File là một giao dịch logic cần toàn bộ hoặc không gì cả.
- Các record phụ thuộc lẫn nhau.
- Sai một record khiến các record còn lại không thể xử lý an toàn.
- Hợp đồng import yêu cầu file phải hợp lệ hoàn toàn.

Nếu đã ghi một số record vào database trước khi lỗi xảy ra, cần xác định transaction rollback được toàn bộ hay có trạng thái import dở dang. Đọc streaming không tự đảm bảo tính atomic.

### 16.2. Tiếp tục và thu thập lỗi theo record

Nếu nghiệp vụ cho phép import record hợp lệ và báo lại record lỗi, có thể xử lý từng record riêng:

~~~java
List<CsvRowError> errors = new ArrayList<>();
long recordNumber = 0;

try (MappingIterator<OrderRow> rows = reader.readValues(input)) {
    while (rows.hasNextValue()) {
        recordNumber++;

        try {
            OrderRow row = rows.nextValue();
            validate(row, recordNumber);
            process(row);
        } catch (InvalidCsvRecordException exception) {
            errors.add(new CsvRowError(
                recordNumber,
                exception.getMessage()
            ));
        }
    }
}
~~~

Đoạn code này chỉ có thể tiếp tục khi parser vẫn ở trạng thái đọc được và lỗi được phát hiện sau khi một record đã được parse hoàn chỉnh. Nếu cú pháp CSV bị hỏng đến mức parser không xác định được ranh giới record tiếp theo, không nên cố bỏ qua tùy tiện.

Không bắt mọi `IOException` trong thân vòng lặp để tiếp tục. Lỗi đọc stream hoặc lỗi cấu trúc parser thường cần dừng luồng. Hãy phân biệt lỗi validation của một object với lỗi parser khiến không thể đồng bộ lại vị trí record.

Đối với file lớn, không giữ mọi lỗi trong một `List` vô hạn. Có thể ghi lỗi ra file riêng, database staging hoặc giới hạn số lỗi được lưu/hiển thị.

## 17. Xử lý theo batch và transaction

Xử lý từng record tối ưu bộ nhớ, nhưng ghi database một record mỗi transaction có thể tốn chi phí. Có thể gom thành batch nhỏ:

~~~java
List<OrderRow> batch = new ArrayList<>(500);

while (rows.hasNextValue()) {
    OrderRow row = rows.nextValue();
    validate(row, recordNumber);
    batch.add(row);

    if (batch.size() == 500) {
        importService.saveBatch(batch);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    importService.saveBatch(batch);
}
~~~

Batch giúp cân bằng:

- Bộ nhớ giới hạn bởi kích thước batch.
- Ít lần round-trip database hơn.
- Có thể commit từng batch.
- Có thể ghi checkpoint để resume.

Tuy nhiên, commit từng batch có nghĩa import có thể hoàn thành một phần. Nếu cần atomic toàn file, transaction kéo dài có thể gây lock và giữ tài nguyên lâu; một mô hình staging table hoặc job import có trạng thái thường phù hợp hơn.

Một pipeline có thể có các trạng thái:

~~~text
RECEIVED
   |
   v
PARSING
   |
   +--> record valid --> STAGING
   |
   +--> record invalid --> ERROR_REPORT
   |
   v
VALIDATED
   |
   v
COMMIT / PUBLISH
   |
   v
COMPLETED
~~~

Việc parse, validate, stage và commit nên có ranh giới rõ. Không nên để việc đọc CSV trực tiếp tạo ra side effect không thể đảo ngược trước khi biết file có đáp ứng yêu cầu hay không.

## 18. Ghi CSV từ nguồn dữ liệu streaming

Nếu dữ liệu xuất đến từ database, tránh tải toàn bộ bảng vào `List`. Có thể dùng cursor, iterator hoặc paging:

~~~java
try (Writer output = Files.newBufferedWriter(
        exportPath,
        StandardCharsets.UTF_8);
     SequenceWriter csv = mapper.writer(schema).writeValues(output);
     Stream<OrderRow> source = repository.streamExportRows()) {

    source.forEach(row -> {
        try {
            csv.write(row);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    });
}
~~~

Ví dụ trên minh họa luồng dữ liệu, nhưng việc ném checked exception từ lambda cần được chuyển đổi cẩn thận và xử lý lại ở boundary. Có thể dùng vòng lặp iterator nếu muốn giữ `IOException` trong chữ ký mà không bọc thành unchecked exception.

Cũng cần chú ý transaction và cursor của repository. Một stream database thường phải được tiêu thụ trong phạm vi transaction/session còn mở. Đừng trả stream ra ngoài rồi đóng transaction trước khi ghi CSV.

## 19. Ghi file an toàn và xử lý lỗi giữa chừng

Khi xuất file lớn, lỗi có thể xảy ra sau khi đã ghi một phần. Nếu ghi trực tiếp vào file đích, consumer có thể nhìn thấy file chưa hoàn chỉnh.

Một quy trình an toàn hơn:

1. Ghi vào file tạm trong cùng filesystem.
2. Đóng `SequenceWriter` và output stream để flush dữ liệu.
3. Kiểm tra số record và trạng thái xuất.
4. Nếu thành công, rename/move file tạm sang tên đích theo thao tác atomic nếu filesystem hỗ trợ.
5. Nếu thất bại, xóa file tạm theo chính sách dọn dẹp.

Ví dụ khung:

~~~java
Path temporary = exportPath.resolveSibling(
    exportPath.getFileName() + ".part"
);

try {
    try (Writer output = Files.newBufferedWriter(
            temporary,
            StandardCharsets.UTF_8);
         SequenceWriter csv = mapper.writer(schema).writeValues(output)) {

        for (OrderRow row : source) {
            csv.write(row);
        }
    }

    Files.move(
        temporary,
        exportPath,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.ATOMIC_MOVE
    );
} catch (IOException exception) {
    Files.deleteIfExists(temporary);
    throw new CsvExportException("CSV export failed", exception);
}
~~~

`ATOMIC_MOVE` phụ thuộc filesystem và có thể không được hỗ trợ. Nếu không hỗ trợ, cần quyết định fallback phù hợp. Không nên xóa file đích cũ trước khi file mới đã hoàn tất nếu muốn giữ bản export đang được consumer sử dụng.

Với file import, có thể ghi kết quả xử lý và error report thành các file tạm rồi công bố chúng cùng một job manifest sau khi hoàn tất.

## 20. Streaming không tự động giải quyết mọi giới hạn tài nguyên

`MappingIterator` và `SequenceWriter` giảm nhu cầu giữ toàn bộ record trong heap, nhưng ứng dụng vẫn cần giới hạn:

- Kích thước file/request tối đa.
- Độ dài field và số lượng cột.
- Số lượng record tối đa hoặc thời gian job.
- Kích thước batch.
- Số lượng lỗi được lưu.
- Số job import/export chạy đồng thời.
- Tốc độ đọc/ghi và áp lực lên database hoặc downstream service.

Một field có thể chứa chuỗi rất lớn; một record có thể có rất nhiều cột. Streaming theo record không ngăn một record đơn lẻ chiếm nhiều bộ nhớ.

Hãy kiểm soát cả tầng upload/HTTP, parser configuration và application processing. Với file không tin cậy, cần có giới hạn thời gian, dung lượng và quyền truy cập filesystem phù hợp.

## 21. CSV injection khi xuất dữ liệu cho spreadsheet

Nếu CSV được mở trong Excel hoặc một ứng dụng spreadsheet, field bắt đầu bằng các ký tự như `=`, `+`, `-` hoặc `@` có thể bị diễn giải thành công thức. Đây là rủi ro CSV/formula injection khi dữ liệu chứa nội dung do người dùng kiểm soát.

Ví dụ field:

~~~csv
customer,comment
Lan,"=HYPERLINK(""https://example.invalid"",""open"")"
~~~

Jackson CSV sẽ quote/escape theo quy tắc CSV; việc đó không nhất thiết ngăn spreadsheet thực thi công thức. Nếu file dành cho người dùng mở trong spreadsheet, cần một chính sách xuất an toàn theo consumer, chẳng hạn prefix giá trị nguy hiểm theo quy ước đã kiểm thử hoặc xuất định dạng không thực thi công thức. Việc thêm dấu nháy CSV đơn thuần không phải biện pháp đủ trong mọi spreadsheet.

Không áp dụng biến đổi này cho mọi tích hợp máy-máy một cách tùy tiện, vì nó làm thay đổi dữ liệu. Hãy xác định rõ mục đích file và tách serializer/export profile dành cho spreadsheet nếu cần.

## 22. Kiểm thử đọc và ghi nhiều record

Test đọc nhiều record:

~~~java
@Test
void readsCsvRecordsOneByOne() throws Exception {
    CsvMapper mapper = new CsvMapper();
    CsvSchema schema = CsvSchema.emptySchema().withHeader();

    String csv = """
        orderId,customer,quantity,unitPrice
        ORD-1,Lan,2,100.00
        ORD-2,Minh,1,50.00
        """;

    ObjectReader reader = mapper
        .readerFor(OrderRow.class)
        .with(schema);

    List<String> ids = new ArrayList<>();

    try (MappingIterator<OrderRow> rows =
            reader.readValues(new StringReader(csv))) {
        while (rows.hasNextValue()) {
            ids.add(rows.nextValue().getOrderId());
        }
    }

    assertEquals(List.of("ORD-1", "ORD-2"), ids);
}
~~~

Test ghi nhiều record:

~~~java
@Test
void writesHeaderAndMultipleRecords() throws Exception {
    CsvMapper mapper = new CsvMapper();
    CsvSchema schema = mapper
        .schemaFor(OrderRow.class)
        .withHeader();

    OrderRow first = new OrderRow();
    first.setOrderId("ORD-1");
    first.setCustomer("Lan");
    first.setQuantity(2);
    first.setUnitPrice(new BigDecimal("100.00"));

    OrderRow second = new OrderRow();
    second.setOrderId("ORD-2");
    second.setCustomer("Minh");
    second.setQuantity(1);
    second.setUnitPrice(new BigDecimal("50.00"));

    StringWriter output = new StringWriter();

    try (SequenceWriter rows = mapper.writer(schema).writeValues(output)) {
        rows.write(first);
        rows.write(second);
    }

    String csv = output.toString();
    assertTrue(csv.startsWith("orderId,customer,quantity,unitPrice"));
    assertTrue(csv.contains("ORD-1"));
    assertTrue(csv.contains("ORD-2"));
}
~~~

Đối với test contract, so sánh nội dung CSV chính xác khi thứ tự cột, separator và line separator là yêu cầu bắt buộc. Nếu chỉ kiểm tra các chuỗi con, test có thể không phát hiện cột bị đảo thứ tự hoặc record bị ghép sai.

Bổ sung test cho:

- Header bị thiếu hoặc có tên sai.
- Thứ tự header thay đổi.
- File không có header.
- Field chứa dấu phẩy, dấu quote và newline.
- Record thiếu/thừa cột.
- Field rỗng, quoted empty và marker null.
- Giá trị số sai định dạng.
- Dòng trống.
- Encoding không đúng.
- Lỗi parser ở giữa file.
- Lỗi xử lý nghiệp vụ ở một record.
- Output file tạm không được công bố nếu ghi thất bại.

## 23. Ví dụ một service import hoàn chỉnh theo record

Một service import có thể kết hợp reader, validation, batch và error context:

~~~java
public ImportSummary importFile(Path path) {
    CsvSchema schema = CsvSchema.emptySchema().withHeader();
    ObjectReader reader = csvMapper
        .readerFor(OrderRow.class)
        .with(schema);

    long recordNumber = 0;
    long imported = 0;
    List<CsvRowError> errors = new ArrayList<>();

    try (Reader input = Files.newBufferedReader(
            path,
            StandardCharsets.UTF_8);
         MappingIterator<OrderRow> rows = reader.readValues(input)) {

        while (rows.hasNextValue()) {
            recordNumber++;

            try {
                OrderRow row = rows.nextValue();
                validator.validate(row);
                orderImportService.importOne(row);
                imported++;
            } catch (ConstraintViolationException
                    | InvalidCsvRecordException exception) {
                errors.add(new CsvRowError(
                    recordNumber,
                    exception.getMessage()
                ));
            }
        }

        return new ImportSummary(recordNumber, imported, errors);

    } catch (IOException exception) {
        throw new CsvImportException(
            "Could not read CSV file " + path.getFileName(),
            exception
        );
    }
}
~~~

Đây là skeleton minh họa. Nếu `rows.nextValue()` ném lỗi parse/mapping, `IOException` ở ngoài sẽ dừng import; chỉ các lỗi validation được bắt bên trong mới cho phép tiếp tục. Nếu muốn tiếp tục sau mapping error, cần xác định parser có thể phục hồi an toàn tại ranh giới record hay không. Không nên giả định mọi lỗi CSV đều có thể skip một record.

Với file rất lớn, thay `List<CsvRowError>` bằng error sink hoặc file report streaming. Nếu cần batch transaction, hãy thay `importOne()` bằng staging/batch service và xác định rõ cách xử lý partial commit.

## 24. Những lỗi thường gặp

### Dùng readAll() cho file lớn

`readAll()` tạo collection chứa toàn bộ record. Dùng vòng lặp `MappingIterator` để xử lý từng record.

### Dùng readLine() và split(",")

Cách này hỏng với dấu phẩy, quote và newline trong field. Dùng CSV parser.

### Nhầm record với dòng vật lý

Một quoted field có thể chứa newline. Đếm record logic bằng vòng lặp iterator, không đếm `readLine()`.

### Bật header cho file không có header

Record đầu tiên có thể bị hiểu thành tên cột. Dùng schema không header và khai báo đúng thứ tự.

### Dựa vào thứ tự DTO mà không kiểm tra schema

Thêm property có thể làm thay đổi CSV output. Dùng schema tường minh và contract test.

### Nghĩ rằng Jackson tự validate nghiệp vụ

Jackson chỉ ánh xạ dữ liệu. Gọi Bean Validation hoặc logic domain cho từng record.

### Nuốt mọi lỗi để tiếp tục

Parser có thể mất khả năng xác định ranh giới record. Chỉ tiếp tục với lỗi record đã parse hoàn chỉnh và có thể xử lý an toàn.

### Giữ tất cả lỗi trong bộ nhớ

Error list cũng có thể tăng vô hạn. Ghi lỗi ra sink hoặc giới hạn số lượng.

### Không đóng iterator/writer

Tài nguyên parser/generator và file có thể bị giữ mở. Dùng try-with-resources.

### Ghi trực tiếp vào file đích

Lỗi giữa chừng có thể để lại file nửa chừng. Ghi file tạm rồi công bố khi hoàn tất.

### Nghĩ streaming loại bỏ mọi giới hạn bộ nhớ

Một field đơn lẻ hoặc một batch vẫn có thể quá lớn. Giới hạn file, field, record và concurrency.

### Không xem xét CSV injection

Quote CSV không ngăn spreadsheet diễn giải công thức. Xác định profile export an toàn theo consumer.

## 25. Quy trình đọc/ghi CSV nhiều record

1. Xác định delimiter, quote/escape, encoding, line separator và quy ước null/empty.
2. Xác định file có header hay không và header có thể đổi thứ tự không.
3. Tạo DTO riêng cho một CSV record.
4. Khai báo `CsvSchema` tường minh hoặc tạo từ DTO theo hợp đồng.
5. Dùng `CsvMapper` và `ObjectReader` để tạo `MappingIterator`.
6. Lặp `hasNextValue()`/`nextValue()` và xử lý từng record.
7. Validate field và quy tắc nghiệp vụ ngay sau khi parse.
8. Chọn fail-fast hay tiếp tục theo record dựa trên khả năng parser phục hồi và chính sách import.
9. Dùng batch/staging khi cần cân bằng bộ nhớ, transaction và hiệu năng.
10. Khi xuất, dùng `SequenceWriter` để ghi từng object vào stream.
11. Với file lớn, lấy dữ liệu theo cursor/page thay vì materialize toàn bộ collection.
12. Đóng iterator, writer và stream bằng try-with-resources.
13. Ghi file tạm rồi rename khi export hoàn tất.
14. Giới hạn kích thước file, field, record, batch, lỗi và concurrency.
15. Test header, thứ tự cột, quote, newline, null, encoding và lỗi giữa file.

## 26. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Đọc CSV nhiều record | `ObjectReader.readValues(...)` |
| Xử lý record tuần tự | `MappingIterator<T>` |
| Tránh tải toàn bộ file vào heap | Không gọi `readAll()` |
| Đọc file có header | `CsvSchema.withHeader()` |
| Đọc file không header | Schema khai báo thứ tự cột, không bật header |
| Header quyết định tên cột | `CsvSchema.emptySchema().withHeader()` |
| Ghi nhiều record | `ObjectWriter.writeValues(...)` và `SequenceWriter` |
| Ghi header | Schema có `withHeader()` |
| Ghi theo batch | Lặp batch và gọi `SequenceWriter.write(...)` |
| Xử lý dấu phân cách | Cấu hình `CsvSchema` |
| Field có comma/quote/newline | Để CSV parser/writer xử lý quoting |
| Validation từng record | Bean Validation hoặc domain validation |
| Báo lỗi theo vị trí | Record index và parser location nếu có |
| Xuất file an toàn | Ghi `.part`, đóng writer rồi move |
| Bảo vệ file import | Giới hạn kích thước, field, record và concurrency |

## 27. Kết luận

Đọc ghi CSV nhiều dòng theo từng bản ghi giúp xử lý file lớn với bộ nhớ có giới hạn và cho phép kiểm soát validation, lỗi và transaction theo từng record hoặc batch. Với Jackson CSV, `CsvMapper` và `CsvSchema` định nghĩa cách ánh xạ cột; `MappingIterator<T>` đọc tuần tự từng record; `SequenceWriter` ghi tuần tự nhiều object ra stream.

Hãy để parser quản lý ranh giới record vì một record CSV có thể trải dài nhiều dòng vật lý. Xác định rõ header, thứ tự cột, delimiter, quote, encoding và null semantics; validate từng object sau khi parse; chọn chính sách fail-fast hay tiếp tục có chủ đích; và dùng batch/staging khi cần quản lý transaction. Khi export, ghi từng record qua `SequenceWriter`, đóng tài nguyên đúng cách và công bố file sau khi hoàn tất. Streaming giảm bộ nhớ tổng thể, nhưng vẫn cần giới hạn kích thước field, file, batch và số job chạy đồng thời.
