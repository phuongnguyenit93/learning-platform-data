# Khai báo cột, thứ tự và dòng tiêu đề cho CSV

CSV là định dạng văn bản dạng bảng. Mỗi dòng biểu diễn một record, các field được phân tách bằng ký tự delimiter như dấu phẩy hoặc dấu chấm phẩy. CSV không tự mang metadata về tên property Java, kiểu dữ liệu hay ý nghĩa của từng cột. Vì vậy, khi dùng Jackson để đọc và ghi CSV, ứng dụng cần một schema xác định **cột nào tồn tại, tên cột là gì, thứ tự cột ra sao và dòng đầu có phải header hay không**.

Trong Jackson CSV, lớp trung tâm là **CsvSchema**. Schema là hợp đồng giữa dữ liệu Java và các cột CSV. **CsvMapper** dùng schema để serialize object thành dòng CSV hoặc deserialize các dòng CSV thành object. Nếu schema không rõ ràng, dữ liệu có thể bị lệch cột, header bị ghi như dữ liệu, giá trị đi vào sai property hoặc consumer đọc file theo một thứ tự khác với writer.

## 1. CSV không tự mô tả cấu trúc như JSON

JSON object mang tên property cùng giá trị:

~~~json
{
  "employeeId": 101,
  "fullName": "Nguyen An",
  "department": "Engineering"
}
~~~

CSV chỉ có các dòng và field:

~~~csv
employeeId,fullName,department
101,Nguyen An,Engineering
~~~

CSV không có cú pháp chuẩn để nói rằng cột thứ nhất là employeeId hoặc có kiểu Java long. Những thông tin đó đến từ dòng header hoặc schema do ứng dụng cung cấp.

Một file CSV thường có hai phần:

1. Header (nếu có): tên cột, thường là dòng đầu tiên.
2. Data rows: các dòng dữ liệu, mỗi dòng có các field theo thứ tự cột.

Header là một quy ước của file CSV, không phải thành phần bắt buộc trong mọi CSV. Có file không có header; consumer phải biết schema từ tài liệu, cấu hình hoặc vị trí cột.

## 2. Jackson CSV và CsvMapper

Jackson cung cấp module jackson-dataformat-csv. Module này có CsvMapper, một mapper chuyên cho định dạng CSV, cùng CsvSchema để mô tả cấu trúc bảng.

Với Maven, thêm dependency cùng version line với các artifact Jackson khác:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-csv</artifactId>
</dependency>
~~~

Nếu project quản lý Jackson bằng BOM, để BOM chọn version thay vì đặt version riêng lẻ cho module CSV. Trộn jackson-dataformat-csv với Databind/Core không tương thích có thể gây lỗi compile hoặc runtime.

Tạo mapper:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;

CsvMapper csvMapper = new CsvMapper();
~~~

Có thể đăng ký thêm module Jackson cần thiết, ví dụ Java Time module nếu DTO chứa kiểu java.time:

~~~java
CsvMapper csvMapper = new CsvMapper();
csvMapper.registerModule(new JavaTimeModule());
~~~

CsvMapper vẫn sử dụng cơ chế serializer/deserializer và annotation của Jackson Databind. Tuy nhiên, schema CSV còn quyết định cách các property được ánh xạ vào cột.

## 3. CsvSchema là hợp đồng cột

Một schema mô tả:

- Tên từng cột.
- Thứ tự cột.
- Kiểu cột nếu được khai báo.
- Header có xuất hiện hoặc được đọc hay không.
- Một số quy tắc định dạng như delimiter, quote, escape và null marker.

Ví dụ schema ba cột:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName")
        .addColumn("department")
        .build();
~~~

Các cột được thêm theo thứ tự gọi addColumn. Trong ví dụ, thứ tự là employeeId, fullName, department.

Khi dùng schema này để ghi CSV, các giá trị được xuất theo thứ tự đó. Vì vậy, thứ tự cột nên được xem là một phần của contract, đặc biệt với file được import bởi hệ thống khác.

ColumnType.NUMBER cho Jackson biết cột được xem là dữ liệu số. Nếu không chỉ định type, cột thường được xử lý như string. Type metadata không thay thế validation nghiệp vụ và không làm CSV trở thành định dạng có kiểu mạnh như JSON Schema.

## 4. Khai báo header bằng withHeader()

Nếu file cần có dòng tiêu đề, bật header trên schema:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName")
        .addColumn("department")
        .build()
        .withHeader();
~~~

Khi serialize một object:

~~~java
public record Employee(
        long employeeId,
        String fullName,
        String department
) {}

Employee employee = new Employee(
        101,
        "Nguyen An",
        "Engineering"
);

String csv = csvMapper.writer(schema)
        .writeValueAsString(employee);
~~~

CSV có dạng:

~~~csv
employeeId,fullName,department
101,Nguyen An,Engineering
~~~

Header lấy tên từ các column trong schema. Dữ liệu của object được ghi vào các cột theo schema đó.

Nếu không gọi withHeader(), schema không yêu cầu writer xuất dòng tiêu đề. Khi đó output chỉ có data row:

~~~csv
101,Nguyen An,Engineering
~~~

Hãy chọn một chính sách header cho từng loại file và giữ nhất quán giữa producer và consumer.

## 5. Đọc CSV có header

Nếu file CSV có header và tên cột có thể được khám phá từ dòng đầu, dùng schema rỗng có header:

~~~java
CsvSchema schema = CsvSchema.emptySchema().withHeader();

MappingIterator<Employee> rows = csvMapper
        .readerFor(Employee.class)
        .with(schema)
        .readValues(csv);
~~~

Dòng header cung cấp tên cột cho parser. Jackson có thể ánh xạ tên đó vào property của kiểu đích theo metadata Jackson, ví dụ property name hoặc JsonProperty.

Đọc các dòng:

~~~java
List<Employee> employees = new ArrayList<>();

try (MappingIterator<Employee> rows = csvMapper
        .readerFor(Employee.class)
        .with(CsvSchema.emptySchema().withHeader())
        .readValues(csv)) {

    while (rows.hasNextValue()) {
        employees.add(rows.nextValue());
    }
}
~~~

Dùng MappingIterator phù hợp khi file có nhiều record. Nó cho phép đọc từng dòng thay vì phải coi toàn bộ CSV như một object đơn.

Header phải khớp với contract của DTO. Nếu header dùng employee_id nhưng property Java là employeeId, hãy khai báo mapping tên rõ ràng, ví dụ JsonProperty("employee_id").

## 6. Đọc CSV không có header

Nếu file không có header, consumer phải biết thứ tự cột từ trước. Hãy dùng schema có danh sách cột tường minh và không bật header:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName")
        .addColumn("department")
        .build();

String csv = """
        101,Nguyen An,Engineering
        102,Tran Binh,Finance
        """;

List<Employee> employees = new ArrayList<>();

try (MappingIterator<Employee> rows = csvMapper
        .readerFor(Employee.class)
        .with(schema)
        .readValues(csv)) {

    while (rows.hasNextValue()) {
        employees.add(rows.nextValue());
    }
}
~~~

Vì không có tên cột trong file, Jackson dựa vào schema để hiểu field đầu tiên là employeeId, field thứ hai là fullName và field thứ ba là department.

Nếu writer xuất header nhưng reader dùng schema không header, dòng tiêu đề có thể bị hiểu thành data row và gây lỗi chuyển kiểu. Ngược lại, nếu reader chờ header nhưng file không có, dòng dữ liệu đầu tiên có thể bị dùng làm tên cột. Header mode phải khớp giữa hai phía.

## 7. Kiểm soát thứ tự cột bằng schema tường minh

Cách chắc chắn nhất để giữ thứ tự export là xây dựng schema bằng CsvSchema.builder():

~~~java
CsvSchema exportSchema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("department")
        .addColumn("fullName")
        .build()
        .withHeader();
~~~

Output theo schema này sẽ có thứ tự employeeId, department, fullName, dù thứ tự field trong class Java khác:

~~~csv
employeeId,department,fullName
101,Engineering,Nguyen An
~~~

Đừng mặc định thứ tự khai báo field Java luôn là thứ tự CSV mong muốn. Refactor class, thêm property hoặc thay đổi introspection có thể làm schema tự sinh khác với contract mà hệ thống downstream đang chờ.

Với file trao đổi ổn định, nên khai báo schema export riêng cho từng phiên bản hoặc từng use case.

## 8. Tạo schema từ POJO bằng schemaFor()

Khi muốn dùng các property mà Jackson nhận diện trên một class, có thể sinh schema từ POJO:

~~~java
CsvSchema schema = csvMapper.schemaFor(Employee.class)
        .withHeader();
~~~

Đây là cách ngắn gọn khi schema CSV có thể theo metadata của class. Nó giúp giảm việc khai báo lại từng column.

Tuy nhiên, nếu thứ tự và danh sách cột là hợp đồng quan trọng, hãy xác định rõ thứ tự property bằng JsonPropertyOrder hoặc dùng schema builder tường minh.

Ví dụ:

~~~java
@JsonPropertyOrder({
        "employeeId",
        "fullName",
        "department"
})
public record Employee(
        long employeeId,
        String fullName,
        String department
) {}
~~~

Sau đó:

~~~java
CsvSchema schema = csvMapper.schemaFor(Employee.class)
        .withHeader();
~~~

JsonPropertyOrder điều khiển thứ tự property mà Jackson introspect. Schema tường minh vẫn hữu ích hơn khi các endpoint cần những tập cột hoặc thứ tự khác nhau cho cùng một class.

## 9. Đổi tên header bằng JsonProperty

Tên cột trong file không bắt buộc phải giống tên field Java. Dùng JsonProperty để công bố tên CSV:

~~~java
public record Employee(
        @JsonProperty("employee_id")
        long employeeId,

        @JsonProperty("full_name")
        String fullName,

        @JsonProperty("department_name")
        String department
) {}
~~~

Schema được sinh từ class sẽ sử dụng tên property mà Jackson nhận diện. Với schema viết tay, hãy dùng đúng tên cột theo contract:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employee_id", CsvSchema.ColumnType.NUMBER)
        .addColumn("full_name")
        .addColumn("department_name")
        .build()
        .withHeader();
~~~

Header:

~~~csv
employee_id,full_name,department_name
101,Nguyen An,Engineering
~~~

Việc đổi tên Java property không nhất thiết phải đổi tên CSV nếu JsonProperty giữ nguyên contract. Ngược lại, đổi tên header là một thay đổi contract cần xem xét khả năng tương thích với consumer.

## 10. Đọc header linh hoạt khi thứ tự cột đầu vào thay đổi

Một số file do người dùng hoặc hệ thống đối tác tạo có cùng tên cột nhưng thứ tự khác nhau:

~~~csv
department,employee_id,full_name
Engineering,101,Nguyen An
~~~

Nếu reader được cấu hình theo vị trí cố định, việc đổi thứ tự có thể đưa dữ liệu vào sai property. Với file có header, schema header-driven cho phép Jackson dùng tên cột thay vì chỉ dựa vào vị trí:

~~~java
CsvSchema inputSchema = CsvSchema.emptySchema().withHeader();

try (MappingIterator<Employee> rows = csvMapper
        .readerFor(Employee.class)
        .with(inputSchema)
        .readValues(csv)) {

    while (rows.hasNextValue()) {
        Employee employee = rows.nextValue();
        // Xử lý employee.
    }
}
~~~

Đây là lựa chọn hữu ích khi thứ tự cột không được đảm bảo nhưng tên header ổn định.

Nếu cần kiểm soát nghiêm ngặt, ứng dụng vẫn nên kiểm tra header trước khi đọc dữ liệu: tên cột bắt buộc có đủ không, có cột trùng không, có cột lạ không và tên có đúng chính tả/case theo contract không. Không nên âm thầm chấp nhận một file có header thiếu hoặc bị đổi tên nếu các field đó quan trọng.

## 11. Map tên cột và DTO

Với dữ liệu CSV linh hoạt, có thể đọc từng dòng thành map:

~~~java
CsvSchema schema = CsvSchema.emptySchema().withHeader();

MappingIterator<Map<String, String>> rows = csvMapper
        .readerFor(Map.class)
        .with(schema)
        .readValues(csv);
~~~

Ví dụ file:

~~~csv
employee_id,full_name,department
101,Nguyen An,Engineering
102,Tran Binh,Finance
~~~

Mỗi row map các header name đến giá trị cột tương ứng. Cách này hữu ích khi file có tập cột thay đổi, chưa biết DTO đích tại compile time, cần kiểm tra header trước khi map sang domain model hoặc muốn giữ lại cột mở rộng.

Map không tự cung cấp kiểu nghiệp vụ. Giá trị CSV thường được đọc như text khi dùng map tổng quát; ứng dụng phải parse và validate số, ngày giờ, boolean hoặc enum theo schema riêng.

## 12. Khai báo kiểu cột

CSV là văn bản, nhưng schema có thể cung cấp gợi ý kiểu cho Jackson. Ví dụ:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName", CsvSchema.ColumnType.STRING)
        .addColumn("salary", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();
~~~

Kiểu cột giúp Jackson lựa chọn cách xử lý token và biểu diễn dữ liệu. Dù vậy, CSV không mang kiểu dữ liệu tự mô tả khi được chuyển cho consumer khác. Một chương trình đọc CSV có thể coi tất cả field là string.

Vì thế, schema type trong Jackson cần đi cùng tài liệu contract. Ví dụ employeeId phải là số nguyên dương, salary là decimal với quy tắc precision cụ thể, startDate theo ISO date. Việc parse được một number không đồng nghĩa number đó hợp lệ về nghiệp vụ.

## 13. CSV chỉ có một dòng header

Với withHeader(), header là dòng đầu tiên của bảng. Không lặp lại header ở giữa file trừ khi một format legacy quy định rõ.

Ví dụ không nên:

~~~csv
employee_id,full_name
101,Nguyen An
employee_id,full_name
102,Tran Binh
~~~

Dòng header lặp lại có thể bị đọc như một record bình thường và làm lỗi chuyển kiểu employee_id thành số.

Nếu file được ghép từ nhiều phần, hãy bỏ header trùng trong bước tạo file hoặc xử lý rõ ràng trước khi đưa vào CsvMapper. Không giả định parser tự nhận diện mọi dòng header lặp.

## 14. Chọn cột xuất ra bằng schema

Một class Java có thể có nhiều property hơn số cột của một file export. Schema tường minh giúp chọn đúng các cột thuộc contract:

~~~java
public class Employee {
    private long id;
    private String name;
    private String department;
    private String internalNote;
    private String accessToken;

    // getters/setters
}
~~~

Schema export:

~~~java
CsvSchema exportSchema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .addColumn("department")
        .build()
        .withHeader();
~~~

Schema xác định các cột writer sẽ tạo. Những property nội bộ như internalNote hoặc accessToken không nên được đưa vào file chỉ vì chúng tồn tại trong object. Với dữ liệu nhạy cảm, hãy thiết kế export DTO chỉ chứa field được phép xuất; schema là một lớp kiểm soát format, không thay thế kiểm soát quyền dữ liệu.

## 15. Tên cột, dấu cách và tên property không chuẩn

CSV header có thể chứa tên như:

~~~csv
Employee ID,Full Name,Department Name
101,Nguyen An,Engineering
~~~

Tên có dấu cách không phải Java identifier. Có thể ánh xạ bằng JsonProperty:

~~~java
public record Employee(
        @JsonProperty("Employee ID") long employeeId,
        @JsonProperty("Full Name") String fullName,
        @JsonProperty("Department Name") String department
) {}
~~~

Hoặc khai báo các tên này trong CsvSchema.builder(). Header phải khớp chính xác với tên mà schema/metadata mong đợi; hãy xác định rõ chính sách chữ hoa/thường, khoảng trắng đầu cuối và ký tự Unicode.

Không nên tự động trim hoặc đổi case header mà không có quy tắc. Hai tên cột khác nhau có thể bị nhập nhằng nếu normalize quá rộng.

## 16. Delimiter: dấu phẩy hay dấu chấm phẩy

CSV thường dùng dấu phẩy, nhưng một số môi trường xuất file dùng dấu chấm phẩy hoặc tab. Schema có thể thay đổi column separator:

~~~java
CsvSchema semicolonSchema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName")
        .addColumn("department")
        .setColumnSeparator(';')
        .build()
        .withHeader();
~~~

Output:

~~~csv
employeeId;fullName;department
101;Nguyen An;Engineering
~~~

Reader và writer phải thống nhất delimiter. Nếu writer dùng dấu chấm phẩy nhưng reader dùng dấu phẩy, parser có thể xem cả dòng là một cột duy nhất.

Đừng chọn delimiter dựa vào việc dữ liệu hiện tại tình cờ không chứa ký tự đó. Field text có thể chứa cả dấu phẩy, dấu chấm phẩy hoặc tab; quy tắc quote vẫn cần được áp dụng.

## 17. Quote, escape và field có dấu phẩy hoặc newline

CSV cần quy tắc quote để biểu diễn field chứa delimiter, dấu quote hoặc newline. Jackson CSV xử lý việc quoting/escaping thông qua generator theo schema và cấu hình.

Ví dụ dữ liệu:

~~~java
Employee employee = new Employee(
        101,
        "An, Nguyen",
        "Engineering"
);
~~~

CSV hợp lệ có thể là:

~~~csv
employeeId,fullName,department
101,"An, Nguyen",Engineering
~~~

Nếu field chứa dấu quote, CSV thường nhân đôi quote bên trong field:

~~~csv
101,"An ""AJ"" Nguyen",Engineering
~~~

Nếu field chứa newline, toàn bộ field cần được quote để newline không bị hiểu là kết thúc record. Không tự ghép CSV bằng String.join(",") hoặc nối chuỗi thủ công; cách đó dễ tạo file sai khi dữ liệu có delimiter, quote, newline hoặc ký tự escape.

Hãy dùng CsvMapper và schema để Jackson ghi các field. Khi đọc file từ hệ thống khác, kiểm tra quote/escape convention mà producer sử dụng.

## 18. Dòng kết thúc và encoding

CSV thường được trao đổi dưới dạng văn bản UTF-8. Với dữ liệu có dấu tiếng Việt, hãy dùng encoding rõ ràng khi ghi byte hoặc đọc file. Không dựa vào charset mặc định của hệ điều hành.

Ví dụ ghi UTF-8:

~~~java
byte[] csvBytes = csvMapper.writer(schema)
        .writeValueAsBytes(employees);
~~~

Khi cần ghi vào file:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    csvMapper.writer(schema).writeValue(output, employees);
}
~~~

Jackson xử lý serialization; stream/file vẫn cần được đóng đúng cách bằng try-with-resources.

Dòng kết thúc có thể là LF hoặc CRLF tùy contract và môi trường consumer. Nếu file được mở bằng công cụ legacy, kiểm tra yêu cầu line ending và cấu hình schema/target output tương ứng. Đừng thay line ending tùy tiện sau khi đã serialize nếu việc đó có thể làm hỏng field multiline hoặc byte-level signature.

## 19. Null, empty string và null marker trong CSV

CSV không có literal null chuẩn dùng chung. Một ô trống có thể được hiểu là chuỗi rỗng, giá trị null hoặc giá trị bị thiếu theo quy ước của consumer.

Vì vậy, nếu cần phân biệt null với empty string, hai phía phải thống nhất một marker. CsvSchema cho phép cấu hình null value marker, ví dụ:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("nickname")
        .build()
        .withHeader()
        .withNullValue("\\N");
~~~

Khi dùng marker như \N, phải xác định cách xử lý nếu dữ liệu thật sự chứa chính chuỗi \N, và kiểm thử cả hai chiều. Marker không phải quy ước phổ quát của mọi CSV consumer; tài liệu import/export phải công bố nó.

Nếu không có null marker, hãy ghi rõ ô trống được hiểu là null hay empty string. Không thể suy ra semantics từ CSV thuần túy một cách chắc chắn.

## 20. Cột ngày giờ và kiểu nghiệp vụ

Ngày giờ trong CSV cũng chỉ là text theo một format đã thỏa thuận. Nếu DTO chứa LocalDate, Instant hoặc OffsetDateTime, hãy đăng ký module Java Time và xác định format/zone rõ ràng.

Ví dụ DTO:

~~~java
public record EmployeeExport(
        long employeeId,
        String fullName,
        LocalDate startDate
) {}
~~~

Mapper:

~~~java
CsvMapper csvMapper = new CsvMapper();
csvMapper.registerModule(new JavaTimeModule());
~~~

Schema có cột ngày dưới dạng text:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName")
        .addColumn("startDate")
        .build()
        .withHeader();
~~~

Nếu consumer yêu cầu yyyy-MM-dd, dd/MM/yyyy hoặc timestamp UTC, hãy cấu hình format tương ứng bằng annotation/custom serializer và test output. Không để locale hoặc timezone mặc định của máy quyết định nội dung CSV.

## 21. Cột lồng nhau và DTO export

CSV là bảng phẳng, trong khi Java object có thể chứa nested object và collection:

~~~java
public record Address(String city, String country) {}

public record Employee(
        long id,
        String name,
        Address address
) {}
~~~

Một nested object không tự động có cách biểu diễn cột duy nhất. Hãy quyết định contract phẳng:

~~~java
public record EmployeeCsvRow(
        long id,
        String name,
        String city,
        String country
) {}
~~~

Map từ domain object sang CSV row:

~~~java
EmployeeCsvRow row = new EmployeeCsvRow(
        employee.id(),
        employee.name(),
        employee.address().city(),
        employee.address().country()
);
~~~

Nếu cần lưu một cấu trúc phức tạp vào một cột, phải chọn encoding rõ ràng, ví dụ JSON text trong một CSV field. Đây là một format lồng nhau và consumer phải parse thêm một bước; không nên ngầm giả định CSV hiểu nested object.

Với export public, DTO riêng giúp danh sách cột ổn định, tránh xuất nhầm property nội bộ và tách contract CSV khỏi domain model.

## 22. Ghi nhiều record và streaming

Với file lớn, không nên ghép toàn bộ CSV vào một String nếu không cần. Dùng SequenceWriter để ghi tuần tự:

~~~java
try (SequenceWriter writer = csvMapper.writer(schema)
        .writeValues(outputStream)) {
    for (Employee employee : employees) {
        writer.write(employee);
    }
}
~~~

Với schema có header, writer phát header theo cấu hình khi bắt đầu chuỗi dữ liệu. Hãy kiểm tra output thực tế và không tự ghi thêm một header thủ công trước SequenceWriter, nếu không file có thể có header lặp.

Đọc streaming:

~~~java
try (MappingIterator<Employee> rows = csvMapper
        .readerFor(Employee.class)
        .with(CsvSchema.emptySchema().withHeader())
        .readValues(inputStream)) {

    while (rows.hasNextValue()) {
        Employee employee = rows.nextValue();
        process(employee);
    }
}
~~~

MappingIterator cho phép xử lý từng record và giảm nhu cầu giữ toàn bộ file trong heap. Hãy đóng iterator/stream đúng cách. Nếu dữ liệu đầu vào đến từ upload lớn, nên áp dụng giới hạn kích thước, số dòng và validation theo từng row.

## 23. Kiểm tra header trước khi import

Với file từ đối tác hoặc người dùng, không nên tin rằng header luôn đúng. Một bước kiểm tra nên xác nhận:

- Có header nếu contract yêu cầu.
- Tất cả cột bắt buộc đều xuất hiện.
- Không có duplicate header.
- Không có tên cột bị sai chính tả hoặc đổi case ngoài quy định.
- Cột không hỗ trợ có được phép xuất hiện hay phải từ chối.
- Số field mỗi record phù hợp schema.
- Header không bị BOM hoặc whitespace ngoài ý muốn.

Nếu dùng schema rỗng với header để map linh hoạt, ứng dụng có thể đọc tên cột từ file, nhưng validation contract vẫn thuộc về ứng dụng. Có thể đọc header/parse dòng đầu bằng parser hoặc một bước tiền xử lý phù hợp, sau đó chỉ tiếp tục mapping khi header hợp lệ.

Với import quan trọng, hãy trả lỗi có số dòng và tên cột để người gửi sửa file. Không âm thầm dịch cột hoặc bỏ field bắt buộc.

## 24. Kiểm tra số cột và dữ liệu sai định dạng

Một dòng có ít hoặc nhiều field hơn schema có thể là lỗi dữ liệu hoặc dấu hiệu file dùng sai delimiter. Hãy kiểm tra các trường hợp:

- Thiếu field ở cuối dòng.
- Thừa field.
- Dòng trống.
- Field số chứa chữ.
- Ngày giờ không đúng format.
- Quote không đóng.
- Newline nằm trong field được quote.
- Header trùng hoặc thiếu.
- Dòng dữ liệu có header lặp.

Không phải mọi trường hợp đều có cùng exception. Jackson có thể báo lỗi parser hoặc mapping tùy vị trí lỗi và cấu hình. Hãy giữ thông tin dòng/record trong thông báo lỗi, đồng thời không log toàn bộ dữ liệu nhạy cảm.

## 25. Schema cố định và schema suy ra từ POJO: chọn thế nào?

| Cách | Điểm mạnh | Hạn chế |
|---|---|---|
| CsvSchema.builder() | Kiểm soát tên, thứ tự và type của từng cột | Phải cập nhật schema khi contract đổi |
| schemaFor(MyType.class) | Tái sử dụng property metadata của POJO | Thứ tự/list cột phụ thuộc introspection và annotation |
| CsvSchema.emptySchema().withHeader() | Linh hoạt khi input header quyết định tên/vị trí cột | Cần validation header và xử lý cột thiếu/lạ |
| Schema không header | Phù hợp format cố định theo vị trí | Consumer phải biết thứ tự chính xác từ trước |

Một hệ thống thường dùng nhiều schema: schema export công khai cố định theo contract; schema import có header để chấp nhận thứ tự cột do đối tác cung cấp; schema legacy cho phiên bản file cũ; schema nội bộ cho một job/batch cụ thể.

Không cần ép một schema dùng cho mọi luồng. Điều quan trọng là mỗi schema có tên/ý nghĩa rõ và được kiểm thử với file mẫu tương ứng.

## 26. Phiên bản hóa CSV contract

CSV thường không có field schemaVersion tự nhiên như JSON. Khi format thay đổi, có thể version hóa qua tên file/thư mục export, metadata đi kèm file, API endpoint/version, header marker hoặc một file manifest riêng, hay quy ước phiên bản trong tài liệu tích hợp.

Ví dụ version 1:

~~~csv
employee_id,full_name
101,Nguyen An
~~~

Version 2 thêm department:

~~~csv
employee_id,full_name,department
101,Nguyen An,Engineering
~~~

Reader cũ có thể không biết cột mới; reader mới có thể cần default cho dữ liệu v1. Hãy quyết định rõ có chấp nhận cột mới không, department thiếu được hiểu thế nào và liệu consumer cũ có từ chối field thừa.

Không đổi tên hoặc đổi thứ tự cột trong một file không header nếu không version hóa contract. Với header-based import, tên cột giúp chịu được thay đổi thứ tự, nhưng không tự giải quyết đổi tên, missing column hoặc type change.

## 27. Ví dụ đầy đủ: schema export cố định và đọc lại

DTO:

~~~java
public record EmployeeCsvRow(
        @JsonProperty("employee_id") long employeeId,
        @JsonProperty("full_name") String fullName,
        @JsonProperty("department") String department
) {}
~~~

Schema export:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employee_id", CsvSchema.ColumnType.NUMBER)
        .addColumn("full_name")
        .addColumn("department")
        .build()
        .withHeader();
~~~

Ghi:

~~~java
CsvMapper mapper = new CsvMapper();

List<EmployeeCsvRow> employees = List.of(
        new EmployeeCsvRow(101, "Nguyen An", "Engineering"),
        new EmployeeCsvRow(102, "Tran Binh", "Finance")
);

String csv = mapper.writer(schema)
        .writeValueAsString(employees);
~~~

CSV dự kiến:

~~~csv
employee_id,full_name,department
101,Nguyen An,Engineering
102,Tran Binh,Finance
~~~

Đọc lại bằng schema có header:

~~~java
List<EmployeeCsvRow> restored = new ArrayList<>();

try (MappingIterator<EmployeeCsvRow> rows = mapper
        .readerFor(EmployeeCsvRow.class)
        .with(CsvSchema.emptySchema().withHeader())
        .readValues(csv)) {

    while (rows.hasNextValue()) {
        restored.add(rows.nextValue());
    }
}
~~~

Test nên xác nhận số record, giá trị và thứ tự row nếu thứ tự file có ý nghĩa:

~~~java
assertEquals(2, restored.size());
assertEquals(101L, restored.get(0).employeeId());
assertEquals("Nguyen An", restored.get(0).fullName());
assertEquals("Finance", restored.get(1).department());
~~~

Đừng chỉ kiểm tra file không rỗng. Hãy kiểm tra header, thứ tự cột và các field có ký tự đặc biệt.

## 28. Test header và thứ tự cột

Có thể kiểm tra dòng đầu của output để xác nhận contract:

~~~java
String csv = mapper.writer(schema).writeValueAsString(employees);
String header = csv.lines().findFirst().orElseThrow();

assertEquals("employee_id,full_name,department", header);
~~~

Đây là test phù hợp khi header và thứ tự cột là contract lexical cần giữ. Với các test nội dung khác, có thể đọc CSV bằng schema rồi so sánh từng property thay vì so sánh toàn bộ chuỗi.

Nếu delimiter là dấu chấm phẩy, assertion header phải dùng đúng delimiter. Nếu tên cột chứa ký tự cần quote, header có thể được quote; khi đó nên kiểm tra qua parser thay vì giả định dòng đầu luôn là chuỗi đơn giản.

## 29. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Header bị đọc thành record | Reader không bật header | Dùng schema có header hoặc bỏ header đúng contract |
| Dòng dữ liệu đầu bị mất | Reader chờ header nhưng file không có | Dùng schema headerless |
| Dữ liệu vào sai property | Schema vị trí khác thứ tự file | Dùng header-based schema hoặc thống nhất thứ tự |
| Chỉ đọc được một cột | Delimiter cấu hình không khớp | Kiểm tra column separator |
| Header không khớp DTO | Tên CSV khác property Java | Dùng JsonProperty hoặc schema column name |
| Thứ tự export thay đổi | Dựa vào introspection mặc định | Dùng schema builder hoặc JsonPropertyOrder |
| Field chứa dấu phẩy làm lệch cột | Tự ghép chuỗi hoặc quote sai | Để CsvMapper xử lý quoting |
| Null và empty bị nhập nhằng | CSV không có null literal chuẩn | Thống nhất null marker hoặc quy ước ô trống |
| File lớn tốn nhiều heap | Đọc toàn bộ file vào list/string | Dùng MappingIterator và SequenceWriter |
| Consumer cũ lỗi sau khi thêm cột | CSV contract đổi mà không version hóa | Quy định forward compatibility hoặc version file |

## 30. Quy trình thiết kế cột và header

Khi tạo một CSV contract mới:

1. Xác định DTO/row model chỉ chứa các field được phép xuất.
2. Liệt kê tên header chính xác, kể cả case và dấu cách.
3. Xác định thứ tự cột theo yêu cầu consumer.
4. Chọn schema tường minh hoặc sinh từ POJO có JsonPropertyOrder.
5. Quyết định file có header hay không.
6. Chốt delimiter, quote/escape, line ending và encoding.
7. Định nghĩa cách biểu diễn null, empty string, ngày giờ và số.
8. Nếu input header có thể thay đổi thứ tự, dùng header-driven schema và validate tên cột.
9. Chọn cách đọc/ghi streaming cho file lớn.
10. Viết fixture test cho header, thứ tự, ký tự đặc biệt, missing/extra columns và các version file.

## 31. Ghi nhớ

Trong Jackson CSV, CsvSchema là hợp đồng mô tả tên cột, thứ tự và một số quy tắc định dạng. CsvMapper sử dụng schema để ghi hoặc đọc các row. withHeader() bật dòng tiêu đề; schema rỗng kết hợp header hữu ích khi tên/vị trí cột đến từ file, còn schema builder phù hợp khi contract cố định và cần kiểm soát thứ tự.

Dùng JsonProperty để ánh xạ header khác tên property Java, JsonPropertyOrder hoặc schema builder để giữ thứ tự ổn định. Với CSV không header, vị trí cột phải được thống nhất tuyệt đối. CSV không tự mô tả kiểu, null hay nested object; hãy quy định delimiter, quote, encoding, null marker, date format và schema version trong contract. Với file lớn, đọc bằng MappingIterator và ghi bằng SequenceWriter; luôn kiểm tra header và dữ liệu trước khi đưa vào nghiệp vụ.
