# Vai trò của CsvMapper và CsvSchema

Jackson không chỉ dùng JSON để trao đổi dữ liệu. Với module jackson-dataformat-csv, ứng dụng có thể dùng cùng hệ sinh thái data binding để đọc và ghi dữ liệu CSV thành POJO, Map hoặc các kiểu Java khác. Hai thành phần quan trọng nhất là **CsvMapper** và **CsvSchema**.

CsvMapper là mapper chuyên xử lý định dạng CSV. Nó cung cấp cơ chế chọn serializer/deserializer, chuyển đổi giữa dòng CSV và kiểu Java, đồng thời tạo reader/writer cho việc đọc ghi tuần tự. CsvSchema mô tả cấu trúc của bảng CSV: tên và thứ tự cột, kiểu cột, header, dấu phân cách, dấu quote, cách biểu diễn null và một số quy tắc định dạng khác.

Có thể nhớ vai trò của chúng như sau:

- **CsvMapper** trả lời: dùng Jackson để đọc hoặc ghi dữ liệu CSV như thế nào, ánh xạ vào kiểu Java nào?
- **CsvSchema** trả lời: CSV có những cột nào, theo thứ tự nào và được phân tách/định dạng ra sao?

Hai thành phần phối hợp với nhau. Mapper xử lý chuyển đổi dữ liệu; schema cung cấp hợp đồng cấu trúc của file CSV.

## 1. CSV khác JSON và YAML ở điểm nào?

JSON và YAML biểu diễn dữ liệu lồng nhau. Một object có thể chứa object khác, array có thể chứa nhiều object và các nhánh có thể có độ sâu khác nhau.

CSV thường biểu diễn dữ liệu dạng bảng: mỗi dòng là một record, mỗi cột là một thuộc tính. Ví dụ:

~~~csv
id,name,age
1,An,28
2,Binh,31
~~~

Có thể xem CSV như một bảng:

| id | name | age |
|---:|---|---:|
| 1 | An | 28 |
| 2 | Binh | 31 |

Cấu trúc này có một số đặc điểm:

- Các dòng dữ liệu thường có cùng số cột.
- Header có thể có hoặc không.
- Giá trị trong CSV về bản chất được truyền dưới dạng text; schema và kiểu Java đích hỗ trợ diễn giải chúng.
- CSV không có cấu trúc object/array lồng nhau tổng quát như JSON.
- Dấu phẩy, dấu quote, xuống dòng và null cần quy ước rõ.

Vì vậy, khi chuyển một object Java phức tạp thành CSV, ứng dụng thường cần một mô hình phẳng (flat row DTO). Không nên kỳ vọng CsvMapper tự biến mọi object graph lồng nhau thành nhiều bảng quan hệ.

## 2. CsvMapper là gì?

CsvMapper thuộc module jackson-dataformat-csv. Nó kế thừa mô hình data binding của Jackson và được cấu hình với CSV factory để đọc/ghi CSV.

Nó cung cấp các khả năng chính:

1. Tạo schema từ một class Java.
2. Tạo ObjectReader và ObjectWriter gắn với schema.
3. Deserialize các dòng CSV thành POJO hoặc Map.
4. Serialize POJO/Map thành các dòng CSV.
5. Đọc nhiều record theo kiểu streaming bằng MappingIterator.
6. Tích hợp serializer, deserializer và module của Jackson khi cần chuyển đổi riêng.

Ví dụ tạo mapper:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;

CsvMapper csvMapper = new CsvMapper();
~~~

CsvMapper là điểm vào chính khi làm việc với CSV. Nếu chỉ có CsvSchema mà không có mapper, ứng dụng mới mô tả được cấu trúc bảng nhưng chưa có cơ chế data binding để chuyển từng record thành object Java.

### 2.1. CsvMapper vẫn dùng các khái niệm Jackson quen thuộc

Các khái niệm như ObjectReader, ObjectWriter, MappingIterator, module và custom serializer/deserializer vẫn có vai trò tương tự khi xử lý JSON. Điểm khác biệt là reader/writer được cấu hình với CsvSchema và parser/generator làm việc theo quy tắc CSV.

Ví dụ:

~~~java
ObjectReader reader = csvMapper
        .readerFor(Person.class)
        .with(schema);

ObjectWriter writer = csvMapper.writer(schema);
~~~

Reader biết kiểu Java đích là Person và biết cấu trúc CSV qua schema. Writer biết cách serialize object theo các cột được mô tả trong schema.

### 2.2. CsvMapper không tự quyết định hợp đồng bảng

Một class Java có thể có nhiều property, nhưng không phải mọi property đều nên xuất hiện trong CSV. Ứng dụng cần quyết định:
- Cột nào được xuất.
- Thứ tự cột.
- Tên header.
- Kiểu và format của từng cột.
- Field nào được phép đọc từ file bên ngoài.
- Field nào phải tính lại hoặc lấy từ hệ thống.

CsvMapper thực hiện mapping theo cấu hình và schema đã chọn. Nó không thay thế việc thiết kế contract dữ liệu.

## 3. CsvSchema là gì?

CsvSchema là mô tả cấu trúc của một CSV document hoặc một tập record. Schema có thể bao gồm:

- Danh sách tên cột.
- Thứ tự các cột.
- ColumnType của từng cột.
- Có header hay không.
- Ký tự phân tách cột.
- Ký tự quote và escape.
- Line separator.
- Null value representation.
- Array element separator trong những trường hợp dùng array column.
- Một số chính sách về header và comment tùy phiên bản/module.

Ví dụ schema đơn giản:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvSchema;

CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name", CsvSchema.ColumnType.STRING)
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();
~~~

Schema trên mô tả ba cột theo thứ tự id, name, age và yêu cầu dòng đầu là header.

Dữ liệu:

~~~csv
id,name,age
1,An,28
2,Binh,31
~~~

Schema không chứa các object Person. Nó mô tả cách record được trình bày trên CSV; CsvMapper dùng schema cùng kiểu Java đích để thực hiện chuyển đổi.

## 4. Tạo CsvSchema từ class Java

Khi CSV có cấu trúc gần với một POJO, CsvMapper có thể suy ra schema từ class:

~~~java
public class Person {
    private Long id;
    private String name;
    private Integer age;

    public Person() {
    }

    public Person(Long id, String name, Integer age) {
        this.id = id;
        this.name = name;
        this.age = age;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Tạo schema:

~~~java
CsvMapper mapper = new CsvMapper();

CsvSchema schema = mapper
        .schemaFor(Person.class)
        .withHeader();
~~~

schemaFor(Person.class) introspect các property mà Jackson nhận diện cho class. Kết quả thường là một schema có các cột tương ứng với property có thể serialize.

Cách này tiện khi:
- POJO và CSV có cùng tên field.
- CSV là export nội bộ có cấu trúc đơn giản.
- Muốn tránh khai báo lặp lại danh sách cột.

Tuy nhiên, không nên phụ thuộc vào thứ tự property suy ra nếu thứ tự cột là một phần quan trọng của hợp đồng bên ngoài. Với CSV được trao đổi giữa nhiều hệ thống, schema tường minh thường dễ kiểm soát và review hơn.

### 4.1. Schema tự sinh không phải hợp đồng API bất biến

Nếu class Java thay đổi, schema suy ra từ class cũng có thể thay đổi:
- Thêm property có thể thêm cột.
- Đổi tên property có thể đổi tên cột.
- Thay annotation hoặc visibility có thể làm thay đổi tập property.
- Thay đổi cấu hình mapper có thể làm thay đổi cách introspection.

Nếu file CSV được dùng bởi hệ thống bên ngoài hoặc được lưu trữ lâu dài, hãy coi schema là contract versioned. Cân nhắc khai báo schema riêng hoặc dùng DTO export riêng để thay đổi class nội bộ không làm thay đổi format file ngoài ý muốn.

## 5. Tạo CsvSchema tường minh bằng builder

Builder phù hợp khi cần kiểm soát chính xác cột và định dạng.

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("employeeId", CsvSchema.ColumnType.NUMBER)
        .addColumn("fullName", CsvSchema.ColumnType.STRING)
        .addColumn("department", CsvSchema.ColumnType.STRING)
        .addColumn("salary", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();
~~~

Tên cột trong schema là tên wire format. Nó không bắt buộc phải giống tên property Java nếu có annotation hoặc mapping phù hợp.

Schema tường minh hữu ích khi:
- Chỉ xuất một phần property của model.
- Cần thứ tự cột cố định.
- Tên header phải tuân theo quy ước của đối tác.
- Muốn phân biệt export schema và import schema.
- Muốn tránh việc thêm field Java vô tình làm thay đổi CSV.

### 5.1. Thứ tự cột có ý nghĩa

Trong CSV không có tên field gắn trực tiếp với từng value nếu file không có header. Vì vậy, thứ tự cột là một phần quan trọng của contract.

Ví dụ schema:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("name")
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build();
~~~

Dòng dữ liệu không header phải tuân theo đúng thứ tự:

~~~csv
An,1,28
Binh,2,31
~~~

Nếu producer ghi id trước name trong khi consumer hiểu name trước id, dữ liệu có thể bị ánh xạ sai mà file vẫn là CSV hợp lệ về cú pháp.

Với file không header, nên dùng schema tường minh và quản lý version cẩn thận.

## 6. Header và headerless CSV

### 6.1. CSV có header

CSV thường dùng dòng đầu tiên làm tên cột:

~~~csv
id,name,age
1,An,28
2,Binh,31
~~~

Có thể tạo schema có header:

~~~java
CsvSchema schema = mapper
        .schemaFor(Person.class)
        .withHeader();
~~~

Khi đọc, header giúp parser nhận diện tên cột. Khi ghi, mapper có thể ghi dòng tên cột trước dữ liệu.

~~~java
String csv = mapper
        .writer(schema)
        .writeValueAsString(people);
~~~

Kết quả có dạng:

~~~csv
id,name,age
1,An,28
2,Binh,31
~~~

Header làm file dễ đọc và giảm phụ thuộc vào thứ tự cột ở phía consumer, nhưng header cũng phải được kiểm soát. Tên cột sai, thiếu hoặc trùng vẫn có thể gây lỗi hoặc mapping không như mong đợi.

### 6.2. CSV không có header

Một số hệ thống yêu cầu file chỉ có record:

~~~csv
1,An,28
2,Binh,31
~~~

Dùng schema không header:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build()
        .withoutHeader();
~~~

Trong trường hợp này, consumer cần biết chính xác thứ tự cột. Không nên đọc file headerless bằng schema có thứ tự khác.

### 6.3. Đọc header động thành Map

Nếu file có header và cột có thể thay đổi, có thể đọc từng record thành Map:

~~~java
CsvSchema schema = CsvSchema.emptySchema().withHeader();

MappingIterator<Map<String, String>> iterator = mapper
        .readerFor(Map.class)
        .with(schema)
        .readValues(csvInput);

List<Map<String, String>> rows = iterator.readAll();
~~~

Mỗi Map dùng tên header làm key. Cách này linh hoạt cho dữ liệu tabular không có POJO cố định.

Tuy nhiên, Map không tự xác thực schema nghiệp vụ. Ứng dụng vẫn phải kiểm tra key bắt buộc, kiểu value, cột lạ và giới hạn dữ liệu trước khi sử dụng.

## 7. ColumnType mô tả điều gì?

CsvSchema có thể gán kiểu cho cột. Các kiểu thường dùng gồm:

- STRING: dữ liệu dạng chuỗi.
- NUMBER: dữ liệu số.
- ARRAY: cột biểu diễn một tập giá trị theo quy ước array separator của CSV module.

Ví dụ:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("code", CsvSchema.ColumnType.STRING)
        .addColumn("quantity", CsvSchema.ColumnType.NUMBER)
        .addColumn("unitPrice", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();
~~~

ColumnType giúp CSV generator/parser áp dụng cách xử lý phù hợp cho cột, chẳng hạn quy tắc quote và representation. Tuy nhiên, CSV không có hệ kiểu dữ liệu phong phú như Java. ColumnType không thay thế việc kiểm tra kiểu Java đích hoặc validation nghiệp vụ.

Ví dụ, cột quantity được đánh dấu NUMBER không có nghĩa mọi giá trị trong cột tự động thỏa điều kiện quantity phải lớn hơn 0. Ứng dụng vẫn cần kiểm tra:
- Giá trị có parse được thành số nguyên không.
- Có nằm trong phạm vi kiểu Java không.
- Có lớn hơn 0 không.
- Có đáp ứng giới hạn nghiệp vụ không.

Không nên dùng ColumnType như một lớp xác thực duy nhất.

## 8. Dấu phân cách cột

CSV thường dùng dấu phẩy, nhưng nhiều hệ thống dùng dấu chấm phẩy hoặc ký tự khác do quy ước địa phương.

Ví dụ dùng semicolon:

~~~csv
id;name;age
1;An;28
2;Binh;31
~~~

Tạo schema:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .setColumnSeparator(';')
        .build()
        .withHeader();
~~~

Dấu phân cách phải giống nhau giữa producer và consumer. Nếu producer dùng dấu chấm phẩy còn consumer hiểu dấu phẩy, mỗi dòng có thể bị đọc thành một cột duy nhất hoặc sai số cột.

Không nên chọn delimiter dựa trên locale một cách ngầm định. Hãy quy định rõ trong contract hoặc metadata của file.

## 9. Quote và escape

CSV cần xử lý những giá trị chứa delimiter, dấu quote hoặc xuống dòng.

Ví dụ:

~~~csv
id,name,note
1,"An, Nguyen","Works in ""Platform"""
2,Binh,"First line
Second line"
~~~

Một field có dấu phẩy thường được bao bởi dấu quote. Dấu quote bên trong field được escape theo quy tắc CSV, thường bằng cách lặp lại dấu quote.

Schema có thể cấu hình quote char và escape char:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .addColumn("note")
        .setColumnSeparator(',')
        .setQuoteChar('"')
        .setEscapeChar('"')
        .build()
        .withHeader();
~~~

Không tự nối chuỗi CSV bằng dấu phẩy. Hãy để CsvGenerator xử lý quote/escape vì việc này dễ sai với dấu phẩy, dấu quote, newline và Unicode.

Nếu producer và consumer dùng quy tắc quote khác nhau, cùng một file có thể được hiểu khác nhau. Hãy kiểm thử các trường hợp chứa delimiter, quote, CR/LF và chuỗi rỗng.

## 10. Null, chuỗi rỗng và giá trị thiếu

CSV không có một token null chuẩn giống JSON. Các file khác nhau có thể dùng:
- Ô trống.
- Chuỗi rỗng.
- Một sentinel như \N hoặc NULL.
- Không có cột hoặc thiếu cell ở cuối dòng.

Những biểu diễn này không nhất thiết có cùng ý nghĩa.

CsvSchema có thể cấu hình null representation, ví dụ:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .setNullValue("\\N")
        .build()
        .withHeader();
~~~

Nếu dùng sentinel \N, producer và consumer phải thống nhất chuỗi này có nghĩa null. Cần xem xét trường hợp người dùng thật sự nhập đúng chuỗi \N; nếu không có quy tắc escape riêng, dữ liệu hợp lệ có thể bị diễn giải thành null.

Không nên tự coi mọi ô trống là null hoặc mọi chuỗi "NULL" là null. Hãy quy định riêng cho từng cột nếu cần phân biệt:
- Missing cell.
- Empty field.
- Null sentinel.
- Chuỗi có độ dài bằng 0.
- Giá trị mặc định.

Sau khi deserialize, validation cần xác nhận các cột bắt buộc đã có dữ liệu.

## 11. Array column trong CSV

CSV là bảng phẳng, nhưng đôi khi một cột cần biểu diễn một danh sách đơn giản. Jackson CSV hỗ trợ array column với một dấu phân cách phần tử riêng trong cell.

Ví dụ ý tưởng:

~~~csv
id,tags
1,java|jackson|csv
2,security|validation
~~~

Schema có thể khai báo array column và separator:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addArrayColumn("tags")
        .setArrayElementSeparator("|")
        .build()
        .withHeader();
~~~

Cách này chỉ phù hợp với danh sách giá trị đơn giản và có quy tắc separator rõ. Nếu một phần tử có thể chứa chính separator, cần kiểm tra khả năng escape/encoding của module và thiết kế contract tương ứng.

Đối với cấu trúc lồng nhau phức tạp, nên dùng JSON/YAML hoặc tách thành nhiều bảng có khóa liên kết. Không nên nhồi object graph vào một cell CSV bằng cách tự nối chuỗi.

## 12. Đọc CSV thành POJO với CsvMapper

Ví dụ đầy đủ:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;
import com.fasterxml.jackson.databind.MappingIterator;

import java.util.List;

public class CsvReadExample {

    public static void main(String[] args) throws Exception {
        String csv = """
                id,name,age
                1,An,28
                2,Binh,31
                """;

        CsvMapper mapper = new CsvMapper();

        CsvSchema schema = mapper
                .schemaFor(Person.class)
                .withHeader();

        try (MappingIterator<Person> iterator = mapper
                .readerFor(Person.class)
                .with(schema)
                .readValues(csv)) {

            List<Person> people = iterator.readAll();

            for (Person person : people) {
                System.out.println(
                        person.getId() + " - "
                                + person.getName() + " - "
                                + person.getAge()
                );
            }
        }
    }
}
~~~

Luồng xử lý:
1. Tạo CsvMapper.
2. Tạo schema phù hợp với Person và header.
3. Tạo ObjectReader cho kiểu Person.
4. Gắn schema vào reader.
5. Gọi readValues() để nhận MappingIterator.
6. Duyệt hoặc đọc toàn bộ record.

MappingIterator có thể được dùng theo kiểu streaming, nên không bắt buộc phải nạp toàn bộ file vào List. Với file lớn, nên xử lý từng record rồi giải phóng dữ liệu đã dùng.

### 12.1. Đọc với schema tường minh

Nếu thứ tự và tên cột phải cố định:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();

List<Person> people = mapper
        .readerFor(Person.class)
        .with(schema)
        .readValues(csv)
        .readAll();
~~~

Schema tường minh làm rõ contract và tránh phụ thuộc vào introspection của class.

## 13. Ghi POJO thành CSV

Dùng ObjectWriter gắn schema:

~~~java
List<Person> people = List.of(
        new Person(1L, "An", 28),
        new Person(2L, "Binh", 31)
);

CsvMapper mapper = new CsvMapper();

CsvSchema schema = mapper
        .schemaFor(Person.class)
        .withHeader();

String csv = mapper
        .writer(schema)
        .writeValueAsString(people);

System.out.println(csv);
~~~

Hoặc dùng schema builder:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name", CsvSchema.ColumnType.STRING)
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();

String csv = mapper.writer(schema).writeValueAsString(people);
~~~

CsvMapper sẽ ghi header và các row theo schema. Không cần tự ghép tên cột hoặc value bằng StringBuilder.

### 13.1. Export một phần property

Nếu không muốn export toàn bộ class, tạo DTO dành riêng cho file:

~~~java
public record PersonExportRow(
        Long id,
        String displayName,
        Integer age
) {
}
~~~

Tạo schema theo đúng thứ tự:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("displayName")
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();
~~~

DTO export giúp kiểm soát field nào được gửi ra ngoài và tránh vô tình xuất property nội bộ khi class domain được bổ sung.

## 14. Đọc file lớn bằng MappingIterator

Đối với file CSV lớn, readAll() có thể nạp toàn bộ record vào bộ nhớ. Nếu chỉ cần xử lý từng dòng, hãy duyệt MappingIterator:

~~~java
try (MappingIterator<Person> iterator = mapper
        .readerFor(Person.class)
        .with(schema)
        .readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        Person person = iterator.nextValue();

        validate(person);
        importOne(person);
    }
}
~~~

Ưu điểm:
- Không cần giữ toàn bộ file trong một List.
- Có thể validate và ghi database từng batch.
- Giảm áp lực heap với file lớn.
- Có thể dừng sớm khi gặp lỗi theo chính sách import.

Nếu ghi database, nên gom nhiều record thành batch thay vì commit từng dòng. Cần quyết định rõ import có tính atomic toàn file hay cho phép một phần thành công.

MappingIterator quản lý việc đọc tuần tự. Ứng dụng vẫn cần giới hạn kích thước file, số dòng, độ dài cell và thời gian xử lý.

## 15. Ghi nhiều record theo kiểu streaming

Với output lớn, có thể ghi tuần tự thay vì tạo một String chứa toàn bộ CSV:

~~~java
try (SequenceWriter writer = mapper
        .writer(schema)
        .writeValues(outputStream)) {

    for (Person person : people) {
        writer.write(person);
    }
}
~~~

SequenceWriter ghi từng object theo schema. Cách này hữu ích khi export dữ liệu lớn hoặc stream response.

Cần đóng writer/stream đúng cách để flush dữ liệu và giải phóng tài nguyên. Nếu stream thuộc về framework HTTP và framework quản lý vòng đời, hãy tuân theo quy ước của framework để tránh đóng nhầm stream do container sở hữu.

## 16. Kiểm soát header và schema drift

Header giúp xác định cột bằng tên, nhưng không tự bảo đảm file tuân theo contract.

Các tình huống cần kiểm tra:
- Thiếu cột bắt buộc.
- Thừa cột ngoài hợp đồng.
- Tên cột sai chính tả.
- Hai cột có cùng tên.
- Thứ tự cột thay đổi.
- Header rỗng.
- File không có header dù consumer mong đợi header.

CsvSchema có các tùy chọn liên quan đến strict header và thứ tự cột trong các phiên bản Jackson CSV. Khi dùng những tùy chọn này, hãy kiểm tra API của đúng phiên bản jackson-dataformat-csv trong dự án và test với file có header thiếu, thừa hoặc đổi thứ tự.

Không nên dựa vào một hành vi mặc định chưa được kiểm thử. Hãy quyết định contract:
- Header có bắt buộc không?
- Cột có thể được đổi thứ tự không?
- Có cho phép cột mở rộng không?
- Cột nào là bắt buộc?
- Tên cột có phân biệt hoa thường không?

Nếu cần schema version, có thể thêm metadata bên ngoài file, tên file versioned hoặc một cột schemaVersion theo quy ước của hệ thống. Không nên tự suy đoán phiên bản chỉ từ số cột.

## 17. CsvMapper và YAMLMapper không thay thế nhau

Chương YAML và CSV nằm trong cùng hệ sinh thái Jackson, nhưng hai định dạng có cấu trúc khác nhau.

- CSV: dùng CsvMapper và CsvSchema; phù hợp với dữ liệu dạng bảng.
- YAML: dùng YAMLFactory hoặc YAMLMapper từ module jackson-dataformat-yaml; phù hợp với cấu trúc mapping/sequence lồng nhau.
- JSON: dùng ObjectMapper với JsonFactory mặc định; phù hợp với object/array tree và streaming token.

Ví dụ YAML mapper:

~~~java
ObjectMapper yamlMapper = new ObjectMapper(new YAMLFactory());
~~~

YAML không dùng CsvSchema. Ngược lại, CsvMapper không biến CSV thành cấu trúc YAML hoặc JSON lồng nhau. Chọn mapper theo định dạng nguồn/đích và thiết kế DTO theo cấu trúc phù hợp.

## 18. Giới hạn của CSV và cách mô hình hóa object lồng nhau

Giả sử class:

~~~java
public class Order {
    private Long id;
    private Customer customer;
    private List<OrderItem> items;
}
~~~

Đây là object có nested object và collection. CSV không có cách biểu diễn lồng nhau tổng quát tương đương JSON:

~~~json
{
  "id": 100,
  "customer": {
    "id": 5,
    "name": "An"
  },
  "items": [
    {"sku": "A", "quantity": 2},
    {"sku": "B", "quantity": 1}
  ]
}
~~~

Có một số cách mô hình hóa:

**Cách 1: Flatten thành một dòng**

~~~csv
orderId,customerId,customerName,itemCount
100,5,An,2
~~~

Phù hợp khi chỉ cần summary.

**Cách 2: Một dòng cho mỗi order item**

~~~csv
orderId,customerId,customerName,sku,quantity
100,5,An,A,2
100,5,An,B,1
~~~

Phù hợp khi cần phân tích từng item, nhưng thông tin order/customer bị lặp lại.

**Cách 3: Tách thành nhiều file/bảng liên kết bằng ID**

orders.csv:

~~~csv
orderId,customerId
100,5
~~~

order-items.csv:

~~~csv
orderId,sku,quantity
100,A,2
100,B,1
~~~

Phù hợp với dữ liệu quan hệ hoặc import/export nhiều bảng. Ứng dụng cần join lại bằng khóa.

Chọn mô hình theo mục đích tiêu thụ dữ liệu. Nếu cấu trúc lồng nhau là quan trọng, JSON hoặc YAML thường tự nhiên hơn CSV.

## 19. Xử lý encoding và line ending

CSV thường được trao đổi dưới dạng file text. Ngoài schema, ứng dụng cần thống nhất:
- Charset, thường là UTF-8.
- Có BOM hay không.
- Line ending LF hay CRLF.
- Delimiter.
- Quote/escape.
- Null representation.

Không nên đọc file bằng charset mặc định của máy vì môi trường Windows/Linux có thể khác nhau. Dùng Reader/Writer hoặc InputStream/OutputStream với charset được quy định rõ.

Ví dụ đọc UTF-8:

~~~java
try (Reader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
)) {
    MappingIterator<Person> iterator = mapper
            .readerFor(Person.class)
            .with(schema)
            .readValues(reader);

    // Xử lý iterator theo contract tài nguyên của ứng dụng.
}
~~~

Khi dùng stream, cần đảm bảo parser/iterator được đóng đúng cách và ownership của Reader không bị đóng hai lần theo cách gây lỗi.

## 20. Kiểm tra dữ liệu CSV trước khi đưa vào nghiệp vụ

CsvMapper có thể deserialize thành công một dòng nhưng điều đó không chứng minh dữ liệu an toàn hoặc hợp lệ.

Ví dụ:
- age parse thành Integer nhưng âm.
- quantity rất lớn gây vượt giới hạn nghiệp vụ.
- email có format sai.
- mã khách hàng không tồn tại.
- một cột quyền hạn được đưa vào DTO ngoài ý muốn.
- file chứa số dòng hoặc cell dài bất thường.

Một pipeline import nên có các bước:

~~~mermaid
flowchart TD
    A[Nhận file CSV] --> B[Kiểm tra kích thước và encoding]
    B --> C[CsvMapper + CsvSchema đọc record]
    C --> D[Kiểm tra cột và kiểu dữ liệu]
    D --> E[Bean Validation]
    E --> F[Kiểm tra nghiệp vụ và quyền]
    F --> G[Import theo batch]
    D -->|Lỗi| H[Ghi nhận row/column và mã lỗi]
    E -->|Lỗi| H
    F -->|Lỗi| H
~~~

Với file do người dùng tải lên, không nên tin header, tên file, content type hoặc dữ liệu cell. Giới hạn dung lượng, số dòng, độ dài cột và xử lý lỗi theo chính sách rõ ràng.

## 21. Lưu ý bảo mật khi export CSV cho spreadsheet

CSV thường được mở bằng Excel hoặc các ứng dụng bảng tính. Một số cell bắt đầu bằng ký tự như =, +, - hoặc @ có thể được diễn giải thành công thức thay vì text.

Đây là rủi ro CSV formula injection. Quote/escape do CsvMapper thực hiện nhằm tạo CSV hợp lệ, nhưng không nhất thiết ngăn spreadsheet thực thi công thức.

Nếu export dữ liệu do người dùng kiểm soát sang spreadsheet:
- Xác định các cột có thể chứa text không tin cậy.
- Áp dụng chính sách trung hòa formula prefix phù hợp với spreadsheet mục tiêu.
- Không thay đổi dữ liệu gốc trong database chỉ để phục vụ export.
- Kiểm thử với các giá trị bắt đầu bằng =, +, - và @.
- Cân nhắc tạo XLSX với cell type text nếu cần kiểm soát kiểu cell chặt hơn.

Việc thêm dấu nháy đơn hoặc prefix an toàn có thể ảnh hưởng dữ liệu khi một hệ thống khác import lại. Hãy coi đây là chính sách export dành cho người dùng spreadsheet, không phải quy tắc chung cho mọi CSV machine-to-machine.

## 22. Tái sử dụng mapper và schema

CsvMapper và schema thường được cấu hình một lần rồi tái sử dụng. Sau khi hoàn tất cấu hình mapper, không nên thay đổi module hoặc feature tùy tiện trong lúc nhiều thread đang dùng.

CsvSchema được thiết kế như một mô tả cấu trúc có thể tái sử dụng. Khi cần biến thể có header, delimiter hoặc null representation khác, tạo schema mới từ builder hoặc dùng các phương thức with... tương ứng thay vì chia sẻ một schema rồi sửa trạng thái giữa các request.

Ví dụ tách schema import/export:

~~~java
CsvSchema importSchema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("name")
        .addColumn("age", CsvSchema.ColumnType.NUMBER)
        .build()
        .withHeader();

CsvSchema exportSchema = CsvSchema.builder()
        .addColumn("id", CsvSchema.ColumnType.NUMBER)
        .addColumn("displayName")
        .build()
        .withHeader();
~~~

Schema import và export có thể khác nhau vì input và output có mục đích, field allowlist và version contract khác nhau.

## 23. Dependency cần có

Để dùng CsvMapper, dự án cần module jackson-dataformat-csv bên cạnh các dependency Jackson tương ứng.

Với Maven, nếu Jackson BOM đã quản lý phiên bản, dependency có thể khai báo:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-csv</artifactId>
</dependency>
~~~

Nếu không dùng BOM, khai báo version của jackson-dataformat-csv đồng bộ với jackson-core và jackson-databind đang dùng. Tránh trộn các phiên bản khác dòng vì có thể gây lỗi linkage hoặc API không tương thích.

Các import thường gặp:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;
import com.fasterxml.jackson.databind.MappingIterator;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
~~~

## 24. Kiểm thử CsvMapper và CsvSchema

Test nên xác nhận cả cấu trúc output và cách đọc input. Một số test cơ bản:

### 24.1. Ghi CSV có header

~~~java
@Test
void writesPeopleWithHeader() throws Exception {
    CsvMapper mapper = new CsvMapper();

    CsvSchema schema = CsvSchema.builder()
            .addColumn("id", CsvSchema.ColumnType.NUMBER)
            .addColumn("name")
            .addColumn("age", CsvSchema.ColumnType.NUMBER)
            .build()
            .withHeader();

    List<Person> people = List.of(
            new Person(1L, "An", 28),
            new Person(2L, "Binh", 31)
    );

    String csv = mapper.writer(schema).writeValueAsString(people);

    assertTrue(csv.startsWith("id,name,age"));
    assertTrue(csv.contains("1,An,28"));
}
~~~

### 24.2. Đọc CSV thành POJO

~~~java
@Test
void readsPeopleFromCsv() throws Exception {
    String csv = """
            id,name,age
            1,An,28
            2,Binh,31
            """;

    CsvMapper mapper = new CsvMapper();

    CsvSchema schema = CsvSchema.builder()
            .addColumn("id", CsvSchema.ColumnType.NUMBER)
            .addColumn("name")
            .addColumn("age", CsvSchema.ColumnType.NUMBER)
            .build()
            .withHeader();

    try (MappingIterator<Person> iterator = mapper
            .readerFor(Person.class)
            .with(schema)
            .readValues(csv)) {

        List<Person> people = iterator.readAll();

        assertEquals(2, people.size());
        assertEquals("An", people.get(0).getName());
        assertEquals(31, people.get(1).getAge());
    }
}
~~~

### 24.3. Đọc header động thành Map

~~~java
@Test
void readsHeaderDrivenRowsAsMaps() throws Exception {
    String csv = """
            code,label
            A,Alpha
            B,Beta
            """;

    CsvMapper mapper = new CsvMapper();
    CsvSchema schema = CsvSchema.emptySchema().withHeader();

    try (MappingIterator<Map<String, String>> iterator = mapper
            .readerFor(Map.class)
            .with(schema)
            .readValues(csv)) {

        List<Map<String, String>> rows = iterator.readAll();

        assertEquals("Alpha", rows.get(0).get("label"));
        assertEquals("B", rows.get(1).get("code"));
    }
}
~~~

### 24.4. Test các giá trị đặc biệt

Ngoài happy path, hãy kiểm thử:
- Tên hoặc ghi chú có delimiter.
- Cell chứa quote.
- Cell chứa newline.
- Unicode có dấu.
- Null sentinel và chuỗi rỗng.
- Header thiếu hoặc sai tên.
- Dòng có số cột không đúng.
- Number sai format hoặc vượt range.
- File rỗng.
- File có BOM hoặc line ending khác.
- Cột không được phép import.

Không nên chỉ so sánh chuỗi CSV bằng một snapshot nếu format có thể thay đổi theo line separator. Có thể parse output lại bằng cùng schema và kiểm tra giá trị Java, đồng thời vẫn có test riêng cho header/delimiter quan trọng.

## 25. Những điểm cần nhớ

- CsvMapper là mapper chuyên xử lý CSV trong hệ sinh thái Jackson.
- CsvSchema mô tả tên, thứ tự và kiểu cột cùng các quy tắc format của bảng.
- Mapper chịu trách nhiệm data binding; schema chịu trách nhiệm cấu trúc CSV.
- Có thể tạo schema từ POJO bằng schemaFor() hoặc khai báo tường minh bằng builder.
- Header và thứ tự cột là một phần của contract.
- ColumnType hỗ trợ cách xử lý cột nhưng không thay thế validation nghiệp vụ.
- Delimiter, quote, escape, null representation và line ending phải thống nhất giữa producer và consumer.
- CSV phù hợp với record phẳng; object graph lồng nhau thường cần DTO flatten hoặc nhiều bảng liên kết.
- MappingIterator hỗ trợ đọc nhiều dòng theo kiểu streaming; readAll() sẽ giữ toàn bộ kết quả trong bộ nhớ.
- SequenceWriter hỗ trợ ghi nhiều record tuần tự.
- Unknown column, sai kiểu, thiếu cột và giá trị ngoài miền hợp lệ cần chính sách riêng.
- Bỏ qua field lạ không thay thế kiểm tra schema, Bean Validation hoặc authorization.
- Với file lớn, giới hạn kích thước, số dòng, độ dài cell và xử lý theo batch.
- Khi export cho spreadsheet, xem xét CSV formula injection; quote CSV không tự trung hòa công thức.
- CsvMapper/CsvSchema dành cho CSV; YAML dùng YAMLFactory/YAMLMapper và không dùng CsvSchema.

CsvMapper và CsvSchema bổ sung cho nhau: mapper cung cấp cơ chế chuyển đổi giữa CSV và Java, còn schema định nghĩa cách dữ liệu được tổ chức thành cột và dòng. Khi schema được thiết kế rõ ràng, ứng dụng có thể đọc/ghi CSV nhất quán, kiểm soát header và định dạng, xử lý file lớn theo streaming và giữ ranh giới giữa mapping, validation và nghiệp vụ.

