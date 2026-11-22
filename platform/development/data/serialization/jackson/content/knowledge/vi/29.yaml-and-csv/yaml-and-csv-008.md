# Xử lý dấu phân cách, trích dẫn và trường nhiều dòng

Dấu phân cách và dấu trích dẫn quyết định parser hiểu ranh giới dữ liệu văn bản như thế nào. Trong CSV, dấu phẩy, dấu chấm phẩy hoặc tab thường tách cột; dấu ngoặc kép cho phép một giá trị chứa chính dấu phân cách, dấu quote hoặc newline mà không bị hiểu nhầm thành cột hay record mới. Trong YAML, cấu trúc dựa trên thụt lề và các indicator như dấu hai chấm, dấu gạch ngang, dấu phẩy trong flow collection; scalar có thể ở dạng plain, quoted hoặc block để biểu diễn nội dung nhiều dòng.

Với Jackson, không nên tự tách CSV bằng `split(",")` hoặc chia từng dòng bằng `split("\\n")`. Cách đó không hiểu trạng thái quote và làm hỏng dữ liệu hợp lệ có dấu phẩy, dấu nháy hoặc newline bên trong field. Hãy dùng `CsvMapper` và `CsvSchema` cho CSV, `YAMLMapper` cho YAML, đồng thời xác định dialect và quy tắc biểu diễn mà producer/consumer cùng tuân thủ.

## 1. Dấu phân cách và dấu trích dẫn có vai trò gì?

Một file CSV thường biểu diễn bảng dưới dạng các record, mỗi record gồm nhiều field:

~~~csv
id,name,city
1,Linh,Hanoi
2,Minh,Da Nang
~~~

Dấu phẩy phân cách các field; newline kết thúc record. Nhưng dữ liệu thực tế có thể chứa delimiter:

~~~csv
id,name,comment
1,Linh,"Hello, team"
~~~

Dấu phẩy trong `"Hello, team"` thuộc nội dung field vì toàn bộ field được quote.

Nếu giá trị chứa dấu quote:

~~~csv
id,comment
1,"She said ""Hello"""
~~~

Hai dấu quote liên tiếp biểu diễn một dấu quote nằm trong giá trị. Nếu field chứa newline, quote bao quanh toàn bộ field:

~~~csv
id,comment
1,"First line
Second line"
~~~

Newline ở giữa field không kết thúc record. Parser phải biết nó đang ở bên trong một field được quote.

Trong YAML, cấu trúc không được chia thành cột bằng delimiter như CSV. Dấu hai chấm tạo mapping entry, dấu gạch ngang mở đầu sequence item, còn dấu phẩy phân cách phần tử trong flow collection. Quoting và block scalar giúp YAML phân biệt cú pháp với nội dung text.

## 2. CSV không có một dialect duy nhất

CSV thường được hiểu là Comma-Separated Values, nhưng thực tế có nhiều biến thể. Một file xuất theo locale có thể dùng dấu chấm phẩy; hệ thống khác dùng tab hoặc dấu pipe.

Một dialect CSV cần xác định:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Column separator | `,`, `;`, tab, `|` | Phân cách field trong record |
| Quote character | `"` | Bao field có delimiter, quote hoặc newline |
| Quote escaping | `""` hoặc escape char riêng | Biểu diễn quote bên trong field |
| Record separator | CRLF hoặc LF | Kết thúc record |
| Header | Có hoặc không | Dòng đầu chứa tên cột hay dữ liệu |
| Null marker | Rỗng, `\N`, sentinel khác | Phân biệt null với chuỗi rỗng nếu contract cần |
| Character encoding | UTF-8, UTF-8 BOM, encoding khác | Giải mã byte thành ký tự |

Không nên đoán dialect từ phần mở rộng `.csv`. Hãy xác nhận với producer hoặc tài liệu tích hợp. Nếu delimiter, quote hoặc null marker khác nhau giữa hai phía, cùng chuỗi byte có thể được diễn giải thành các giá trị khác nhau.

## 3. Quy tắc trích dẫn thường gặp trong CSV

Theo quy tắc CSV phổ biến kiểu RFC 4180, field cần quote khi chứa delimiter, dấu quote hoặc ký tự xuống dòng. Khi field được quote bằng dấu `"`, một dấu quote bên trong được escape bằng cách lặp đôi:

~~~csv
id,description
1,"A value, with comma"
2,"He said ""ready"""
3,"Line one
Line two"
~~~

Giá trị sau khi parse:

| id | description |
|---|---|
| 1 | `A value, with comma` |
| 2 | `He said "ready"` |
| 3 | Hai dòng text: `Line one` và `Line two` |

Quote là cú pháp của file, không phải ký tự thuộc giá trị sau khi parse. Writer có thể quote tất cả field hoặc chỉ quote field cần thiết; hai output khác byte nhưng vẫn biểu diễn cùng dữ liệu.

Không nên tự bỏ dấu quote bằng replace. Chỉ parser CSV mới biết quote nào là cú pháp và quote nào đã được escape thành dữ liệu.

## 4. Phân biệt record với dòng vật lý

Trong CSV, một record không nhất thiết chiếm đúng một dòng vật lý. Nếu field được quote và chứa CR hoặc LF, parser phải tiếp tục đọc cho đến dấu quote đóng.

~~~csv
ticket_id,subject,details
T-01,Login issue,"User cannot sign in.
Error appears after password submission."
T-02,Export,"CSV output contains ""unexpected"" columns."
~~~

File trên có ba record dữ liệu nhưng record T-01 trải qua hai dòng vật lý. Nếu code dùng `BufferedReader.readLine()` rồi parse từng dòng độc lập, record đầu tiên sẽ bị chia đôi.

Không nên đếm số dòng file để suy ra số record. Hãy để CSV parser quản lý trạng thái quote và ranh giới record.

## 5. Vì sao không nên tự split CSV?

Cách làm sau không an toàn:

~~~java
String[] rows = csv.split("\\n");

for (String row : rows) {
    String[] columns = row.split(",");
}
~~~

Nó thất bại với:
- Field có dấu phẩy bên trong quote.
- Field có newline bên trong quote.
- Quote được escape bằng cách lặp đôi.
- Delimiter là semicolon hoặc tab.
- Record kết thúc bằng CRLF.
- Field rỗng ở cuối record.
- Dữ liệu có khoảng trắng hoặc ký tự Unicode.
- Quy tắc dòng trống hoặc comment riêng của dialect.

Ví dụ:

~~~csv
id,name,notes
1,Linh,"likes tea, coffee"
2,Minh,"first line
second line"
~~~

`split(",")` tạo sai số cột ở record 1; `split("\\n")` chia record 2 thành hai phần. Hãy dùng parser hiểu CSV thay vì tự viết logic tách chuỗi.

## 6. Dùng CsvMapper và CsvSchema của Jackson

Jackson có module `jackson-dataformat-csv`. `CsvMapper` cung cấp databinding cho CSV; `CsvSchema` mô tả cột, thứ tự, header và dialect.

Maven:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-csv</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-csv")
}
~~~

Nên quản lý phiên bản module cùng phiên bản Jackson Core và Databind bằng BOM hoặc dependency management.

Ví dụ DTO:

~~~java
public record ContactRow(
    String id,
    String name,
    String notes
) {}
~~~

Tạo schema có header:

~~~java
CsvMapper csvMapper = new CsvMapper();

CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("name")
    .addColumn("notes")
    .build()
    .withHeader();
~~~

Đọc:

~~~java
List<ContactRow> contacts = csvMapper
    .readerFor(ContactRow.class)
    .with(schema)
    .<ContactRow>readValues(csv)
    .readAll();
~~~

Schema xác định tên cột và header. Hãy kiểm tra tên cột và chính sách strict header phù hợp contract. Nếu cần đọc theo vị trí cố định mà không có header, dùng schema không bật `withHeader()` và khai báo thứ tự cột rõ ràng.

`readAll()` tạo toàn bộ danh sách trong bộ nhớ. Với file lớn, dùng `MappingIterator` và xử lý từng record để tránh giữ tất cả dữ liệu cùng lúc.

## 7. Cấu hình delimiter khác dấu phẩy

Nếu file dùng dấu chấm phẩy:

~~~csv
id;name;notes
1;Linh;"Hello; team"
~~~

Khai báo delimiter trong schema:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("name")
    .addColumn("notes")
    .setColumnSeparator(';')
    .build()
    .withHeader();
~~~

Nếu producer dùng tab:

~~~java
.setColumnSeparator('\t')
~~~

Với dấu pipe:

~~~java
.setColumnSeparator('|')
~~~

Cùng một schema phải được dùng nhất quán khi đọc và ghi. Đừng để parser đọc bằng semicolon nhưng writer xuất comma nếu contract không cho phép thay đổi dialect.

## 8. Cấu hình quote và escape

Quote character phổ biến là dấu nháy kép. Có thể khai báo rõ:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("comment")
    .setColumnSeparator(',')
    .setQuoteChar('"')
    .build()
    .withHeader();
~~~

Theo quy ước CSV phổ biến, quote nằm bên trong field được quote sẽ được biểu diễn bằng hai quote liên tiếp:

~~~csv
id,comment
1,"He said ""OK"""
~~~

Một số hệ thống dùng escape character riêng, ví dụ backslash. Jackson CSV cho phép cấu hình escape char trong những phiên bản hỗ trợ API tương ứng:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("comment")
    .setQuoteChar('"')
    .setEscapeChar('\\')
    .build()
    .withHeader();
~~~

Chỉ đặt escape char riêng khi producer thực sự dùng dialect đó. Backslash escaping không tự động tương đương quy tắc quote doubling. Hai phía phải thống nhất cách ghi và đọc quote bên trong field.

Không nên bật một escape convention tùy ý chỉ để sửa một file mẫu. Trước hết hãy xác định file được tạo bởi Excel, database export, hệ thống đối tác hay một thư viện CSV cụ thể.

## 9. Định dạng record separator

CSV thường gặp CRLF (`\r\n`) hoặc LF (`\n`) làm record separator. Hãy xác định quy ước của hệ thống đích, đặc biệt khi file được import bởi công cụ cũ hoặc chạy trên nhiều hệ điều hành.

Jackson CSV cho phép cấu hình line separator trong schema ở các phiên bản có API tương ứng:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("name")
    .setLineSeparator("\r\n")
    .build()
    .withHeader();
~~~

Record separator không làm thay đổi cách diễn giải newline nằm bên trong quoted field. Parser phải phân biệt newline kết thúc record với newline thuộc giá trị field.

Khi đọc, nên dùng parser hỗ trợ dialect của producer thay vì tự chuẩn hóa CRLF/LF trước khi parse. Việc thay thế newline trong raw text có thể làm thay đổi nội dung multiline field.

## 10. Đọc field nhiều dòng bằng CsvMapper

File ví dụ:

~~~csv
id,title,description
1,Welcome,"First line
Second line
Third line"
2,Notice,"A short description"
~~~

DTO:

~~~java
public record ArticleRow(
    int id,
    String title,
    String description
) {}
~~~

Đọc bằng MappingIterator:

~~~java
try (MappingIterator<ArticleRow> iterator = csvMapper
        .readerFor(ArticleRow.class)
        .with(schema)
        .readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        ArticleRow row = iterator.nextValue();
        process(row);
    }
}
~~~

CsvMapper quản lý trạng thái quote khi đọc. Newline trong description không kết thúc record vì field vẫn đang ở trạng thái quoted.

Đóng MappingIterator sau khi đọc xong để giải phóng parser và tài nguyên nguồn theo lifecycle của Jackson. Nếu input là stream do caller sở hữu, hãy xác định rõ ai chịu trách nhiệm đóng stream.

## 11. Ghi CSV có delimiter và newline bên trong field

Khi ghi CSV, không nên tự nối field bằng dấu phẩy. Hãy để CsvMapper quote và escape theo schema:

~~~java
List<ContactRow> rows = List.of(
    new ContactRow("1", "Linh", "Hello, team"),
    new ContactRow("2", "Minh", "First line\nSecond line"),
    new ContactRow("3", "An", "He said \"ready\"")
);

String csv = csvMapper.writer(schema)
    .writeValueAsString(rows);
~~~

Với quote char là `"`, một kết quả tương đương có thể là:

~~~csv
id,name,notes
1,Linh,"Hello, team"
2,Minh,"First line
Second line"
3,An,"He said ""ready"""
~~~

Writer xử lý field có delimiter, quote hoặc newline theo cấu hình schema. Cách quote chính xác có thể khác giữa writer và thư viện, nhưng sau khi parse bằng cùng dialect, giá trị field phải được khôi phục đúng. Nếu consumer yêu cầu quote tất cả field hoặc có quy tắc riêng, hãy kiểm thử output với chính consumer đó.

## 12. Header và thứ tự cột

CSV có thể có header:

~~~csv
id,name,email
1,Linh,linh@example.test
~~~

Hoặc không có header:

~~~csv
1,Linh,linh@example.test
~~~

Khi có header, schema và parser cần thống nhất cách nhận diện header. Với header-driven import, kiểm tra tên cột và cột bắt buộc. Nếu không có header, thứ tự cột là một phần quan trọng của contract.

Schema không header:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("id")
    .addColumn("name")
    .addColumn("email")
    .build();
~~~

Khi producer đổi thứ tự cột nhưng vẫn giữ header, parser có thể cần cấu hình reorder theo tên header nếu contract cho phép. Nếu consumer phụ thuộc vị trí cột, hãy từ chối header sai thứ tự thay vì âm thầm ánh xạ nhầm dữ liệu.

Header cũng cần được kiểm tra duplicate name. Hai cột cùng tên `email` có thể tạo binding mơ hồ. Không nên dựa vào parser tự chọn cột đầu hay cuối.

## 13. Field rỗng, null và khoảng trắng

CSV không có một biểu diễn null thống nhất giữa mọi dialect. Các trường hợp sau có thể có ý nghĩa khác nhau:

~~~csv
id,name,note
1,Linh,
2,Minh,""
3,An," "
~~~

Tùy parser và contract:
- Field rỗng không quote có thể được ánh xạ thành empty string hoặc null.
- `""` là chuỗi rỗng được quote.
- `" "` là chuỗi có một dấu cách.
- Một sentinel như `\N` có thể được quy ước là null.

Không nên tự trim mọi field. Khoảng trắng đầu/cuối có thể là dữ liệu hợp lệ. Nếu cần trim, hãy thực hiện theo chính sách của từng property sau khi parse.

Nếu phải phân biệt null với empty string, hãy định nghĩa null marker rõ ràng trong dialect và cấu hình schema tương ứng, chẳng hạn `setNullValue("\\N")` nếu API/version đang dùng hỗ trợ. Kiểm tra cả chiều ghi và đọc để sentinel không bị nhầm với giá trị văn bản thật.

## 14. Ký tự Unicode và UTF-8 BOM

CSV thường được trao đổi dưới dạng byte. Cần biết file dùng UTF-8 hay encoding khác. Nếu đọc byte bằng charset mặc định của máy, cùng file có thể hiển thị khác nhau giữa môi trường.

Ưu tiên xác định charset rõ:

~~~java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Đưa Reader vào CsvMapper theo API phù hợp.
}
~~~

Một số file UTF-8 được xuất kèm BOM ở đầu. BOM có thể làm tên cột đầu tiên bị đọc thành chuỗi có ký tự BOM đứng trước, khiến header không khớp. Hãy xử lý BOM tại ranh giới byte/character theo contract, rồi mới parse CSV. Không xóa ký tự U+FEFF ở mọi vị trí dữ liệu vì nó có thể là nội dung thật ở nơi khác.

Test với tên tiếng Việt, emoji và ký tự ngoài ASCII để bảo đảm encoding được xử lý đúng từ đầu đến cuối.

## 15. CSV không phải định dạng biểu diễn object lồng nhau

CSV là định dạng bảng. Nó không có object hoặc array lồng nhau như JSON/YAML. Nếu DTO có address object hoặc List item, cần quyết định cách chuyển sang cột.

Ví dụ flatten:

~~~csv
order_id,customer_id,customer_name,item_count
ORD-100,CUS-17,Linh,2
~~~

Hoặc một cột chứa JSON string theo contract riêng:

~~~csv
order_id,metadata
ORD-100,"{""source"":""mobile"",""priority"":true}"
~~~

Trong trường hợp thứ hai, parser CSV chỉ giải quyết lớp quote bên ngoài. Ứng dụng phải parse nội dung metadata như JSON ở bước tiếp theo. Quote CSV và escape JSON là hai lớp cú pháp khác nhau.

Không nên nhét collection vào chuỗi phân cách bằng dấu phẩy nếu giá trị phần tử cũng có thể chứa dấu phẩy và không có escaping convention rõ ràng. Hãy flatten thành nhiều cột/hàng hoặc dùng định dạng có cấu trúc như JSON/YAML nếu dữ liệu lồng nhau là yêu cầu cốt lõi.

## 16. YAML dùng indicator và indentation thay cho delimiter cột

YAML không phải CSV. Mapping thường dùng dấu hai chấm sau key; sequence dùng dấu gạch ngang; flow collection dùng dấu ngoặc vuông/nhọn và dấu phẩy.

Block style:

~~~yaml
name: Linh
active: true
tags:
  - java
  - jackson
address:
  city: Hanoi
  country: VN
~~~

Flow style:

~~~yaml
user: {name: Linh, active: true}
tags: [java, jackson]
~~~

Trong YAML, dấu hai chấm phân cách key và value trong mapping block khi ở vị trí indicator hợp lệ. Dấu phẩy phân cách phần tử trong flow collection. Dấu thăng mở đầu comment khi xuất hiện ở vị trí phù hợp. Cấu trúc còn phụ thuộc indentation.

Không nên tách YAML bằng dấu phẩy, dấu hai chấm hoặc newline. Một dấu hai chấm có thể nằm trong quoted scalar; newline có thể thuộc block scalar; indentation xác định quan hệ cha/con. Dùng YAML parser để hiểu cấu trúc.

## 17. Khi nào cần quote scalar trong YAML?

YAML có plain scalar, single-quoted scalar và double-quoted scalar. Nếu nội dung có ký tự dễ bị hiểu là indicator hoặc có giá trị giống boolean/number/null, quote giúp thể hiện rõ đó là text.

~~~yaml
message: "Status: ready"
label: "yes"
code: "00123"
literal_hash: "name # internal"
single_quote: 'It''s valid'
escaped_text: "Line one\nLine two"
~~~

Trong single-quoted scalar, dấu nháy đơn bên trong được viết thành hai dấu nháy đơn. Trong double-quoted scalar, backslash escape có ý nghĩa như `\n`, `\t` hoặc escape Unicode.

Plain scalar tiện cho giá trị đơn giản, nhưng các chuỗi như `true`, `null`, `00123`, hoặc nội dung chứa `: ` và ` #` có thể bị parser diễn giải theo quy tắc YAML thay vì là string thuần. Quy tắc implicit typing có thể khác theo YAML version và parser backend; nếu cần bảo đảm kiểu string, hãy quote rõ ràng.

## 18. Trường nhiều dòng trong YAML: literal block scalar

Dùng dấu `|` để giữ các line break của nội dung:

~~~yaml
description: |
  First line
  Second line
  Third line
~~~

Giá trị scalar chứa các dòng text với line break được giữ. Đây là lựa chọn phù hợp cho mô tả nhiều đoạn, template email, script, ghi chú có cấu trúc dòng hoặc nội dung cần giữ line break khi parse.

YAML loại bỏ phần indentation dùng để thụt lề block khỏi giá trị. Các dòng nội dung phải được thụt vào sâu hơn vị trí key. Nếu indentation không nhất quán, parser có thể báo lỗi hoặc diễn giải sai cấu trúc.

Dấu `|` mặc định dùng clip chomping: giữ một newline kết thúc scalar. Nếu cần kiểm soát newline cuối, dùng chomping indicator.

## 19. Chomping indicator: `|-`, `|` và `|+`

Chomping quyết định cách xử lý newline và các dòng trống ở cuối block scalar.

| Cú pháp | Ý nghĩa |
|---|---|
| `|-` | Strip: bỏ newline cuối và các dòng trống cuối |
| `|` với clip mặc định | Giữ một newline cuối |
| `|+` | Keep: giữ newline cuối và các dòng trống cuối |

Ví dụ strip:

~~~yaml
script: |-
  echo one
  echo two
~~~

Giá trị kết thúc ngay sau `echo two`, không có newline cuối.

Ví dụ clip:

~~~yaml
script: |
  echo one
  echo two
~~~

Giá trị có một newline kết thúc.

Ví dụ keep:

~~~yaml
notes: |+
  first paragraph

  second paragraph


~~~

Các dòng trống cuối được giữ theo quy tắc keep. Chomping quan trọng khi scalar là script, file fragment hoặc nội dung được so sánh byte-by-byte.

Nếu consumer chỉ cần text hiển thị, khác biệt newline cuối có thể không quan trọng. Nếu scalar được ghi thành file hoặc gửi cho công cụ thực thi, hãy xác định chính xác quy tắc newline.

## 20. Folded block scalar dùng `>` khi muốn gộp dòng

Dấu `>` tạo folded scalar. Các line break thông thường giữa những dòng liên tiếp được chuyển thành dấu cách, trong khi dòng trống thường giữ ranh giới đoạn.

~~~yaml
description: >
  This is a long description
  that is written across several
  source lines but becomes one
  folded paragraph.
~~~

Giá trị sau khi parse gần tương đương một đoạn văn trên một dòng với khoảng trắng giữa các phần. Đây là lựa chọn tốt cho prose dài muốn xuống dòng trong file YAML để dễ đọc nhưng không muốn line break trở thành nội dung.

Có thể kết hợp folded style với chomping:

~~~yaml
summary: >-
  A paragraph that is folded
  and has no final newline.
~~~

Dùng `>-` nếu không muốn newline cuối. Dùng `>+` nếu cần giữ các dòng trống cuối. Không dùng folded style cho nội dung mà mỗi line break có ý nghĩa, chẳng hạn script hoặc danh sách cần giữ nguyên dòng; hãy dùng literal style `|`.

## 21. Chỉ định indentation cho block scalar

YAML thường tự xác định indentation của block scalar từ dòng nội dung đầu tiên. Có thể chỉ định indentation indicator khi nội dung bắt đầu bằng dòng trống hoặc cần kiểm soát rõ:

~~~yaml
snippet: |2-
    first line
    second line
~~~

Chữ số `2` chỉ mức thụt lề nội dung so với indentation của key; dấu `-` là strip chomping. Cú pháp chính xác cần theo YAML indentation rules và vị trí key.

Không nên dùng tab để thụt lề cấu trúc YAML. YAML yêu cầu indentation bằng space. Tab có thể xuất hiện bên trong quoted/block content theo quy tắc phù hợp, nhưng không nên dùng làm indentation của mapping hoặc sequence.

## 22. Dùng YAMLMapper để đọc và ghi YAML

Jackson cung cấp module `jackson-dataformat-yaml` với `YAMLMapper`:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-yaml</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
~~~

Ví dụ DTO:

~~~java
public record AppConfig(
    String name,
    String description,
    List<String> tags
) {}
~~~

Đọc YAML:

~~~java
YAMLMapper yamlMapper = new YAMLMapper();

AppConfig config = yamlMapper.readValue(yaml, AppConfig.class);
~~~

Ghi YAML:

~~~java
String output = yamlMapper.writeValueAsString(config);
~~~

YAML module dùng parser backend của nó để đọc indicator, quoting, indentation và block scalar. Không cần tự loại dấu quote hoặc gộp các dòng trước khi gọi mapper.

YAMLMapper vẫn dùng cơ chế Databind của Jackson, nên annotation như `@JsonProperty`, `@JsonAlias`, `@JsonIgnore` và custom module có thể áp dụng theo cấu hình. Tuy nhiên, việc ghi YAML không nhất thiết giữ nguyên style quote hoặc block style của tài liệu gốc; Jackson chuyển dữ liệu theo mô hình, không phải trình chỉnh sửa bảo toàn nguyên văn source.

## 23. Dùng block scalar trong DTO

Giả sử YAML:

~~~yaml
name: deployment-guide
description: |
  Step one: prepare the environment.
  Step two: deploy the service.
  Step three: verify the result.
tags:
  - release
  - operations
~~~

DTO:

~~~java
public record GuideConfig(
    String name,
    String description,
    List<String> tags
) {}
~~~

Đọc:

~~~java
GuideConfig config =
    yamlMapper.readValue(yaml, GuideConfig.class);
~~~

Property description nhận một String có line break. Ứng dụng không cần biết source dùng `|` hay một dạng scalar khác nếu giá trị semantic sau parse giống nhau.

Nếu ghi object trở lại YAML, writer có thể chọn style scalar khác. Nếu contract yêu cầu block literal để con người dễ sửa, cần cấu hình generator phù hợp với phiên bản hoặc dùng một bước format YAML riêng; đừng giả định round-trip Databind giữ nguyên dấu `|`, `>` và chomping indicator.

## 24. Dấu phân cách đặc biệt trong YAML

Một số ký tự có ý nghĩa cú pháp phụ thuộc vị trí:

- `:` phân cách key/value trong mapping block khi theo sau bởi khoảng trắng phù hợp.
- `-` mở đầu sequence item trong block style.
- `,` phân cách item trong flow sequence hoặc flow mapping.
- `[` và `]` bao flow sequence.
- `{` và `}` bao flow mapping.
- `#` mở comment ở vị trí cú pháp phù hợp.
- `&`, `*` và `!` liên quan đến anchor, alias và tag.
- `|` và `>` mở block scalar.
- `---` và `...` là document markers.

Ví dụ giá trị có dấu hai chấm hoặc dấu thăng:

~~~yaml
url: "https://example.test/path"
message: "Result: ready # not a comment"
plain_message: Result is ready
~~~

Nếu plain scalar chứa chuỗi `: ` hoặc ` #` ở vị trí parser xem là indicator, hãy quote để tránh mơ hồ. Với dữ liệu đến từ người dùng, serializer/parser YAML nên xử lý escaping; không tự thêm/bớt quote bằng thao tác chuỗi.

## 25. CSV và YAML xử lý multiline khác nhau

| Nhu cầu | CSV | YAML |
|---|---|---|
| Phân cách field | Delimiter như comma/semicolon/tab | Mapping key/value và collection syntax |
| Giá trị chứa delimiter | Quote toàn field | Quote scalar nếu ký tự gây mơ hồ |
| Quote bên trong giá trị | Thường lặp đôi quote hoặc escape theo dialect | Single quote doubled; double quote dùng backslash escape |
| Field nhiều dòng | Quote field; newline bên trong là dữ liệu | Block scalar `|` hoặc `>` |
| Cấu trúc lồng nhau | Không có native object/array | Hỗ trợ mapping/sequence lồng nhau |
| Header | Có thể có dòng header | Không có khái niệm header bảng chung |
| Record boundary | Newline ngoài quoted field | Indentation và document structure |

Không áp dụng quy tắc CSV cho YAML. Dấu phẩy trong YAML flow sequence có vai trò phân cách phần tử, nhưng dấu phẩy trong plain scalar ở block context có thể là nội dung. Newline trong CSV quoted field không kết thúc record, còn newline trong YAML block scalar là một phần của giá trị theo chomping/folding rules.

## 26. Null và empty trong CSV/YAML

CSV thường cần quy ước riêng để phân biệt null và empty string. YAML có giá trị null rõ ràng:

~~~yaml
nickname: null
note: ""
description: |
~~~

Các trường hợp này không giống nhau:
- `nickname: null` là explicit null.
- `note: ""` là chuỗi rỗng.
- `description: |` với block rỗng có thể tạo scalar rỗng hoặc nội dung newline tùy chomping và cấu trúc cụ thể.
- Property không xuất hiện là missing.

Trong CSV, một field rỗng có thể được hiểu là null hoặc empty string tùy parser/schema. Nếu phải bảo toàn cả hai, hãy định nghĩa null marker rõ ràng như `\N` và test với dữ liệu thật.

Không nên dùng chuỗi `"null"` như null marker nếu người dùng có thể nhập chính từ "null" như giá trị hợp lệ, trừ khi contract quy định cách phân biệt.

## 27. Xử lý lỗi và validation theo dialect

Một file có thể sai vì cú pháp hoặc vì không đúng contract:
- CSV sai quote: quote mở nhưng không đóng.
- CSV sai số cột: record có nhiều hoặc ít field hơn schema.
- CSV header thiếu hoặc duplicate.
- CSV multiline field không được quote đúng.
- YAML indentation sai.
- YAML scalar bị parser suy luận thành boolean/number/null ngoài ý muốn.
- YAML block scalar dùng sai indentation hoặc chomping.
- Dữ liệu parse được nhưng vi phạm kiểu hoặc ràng buộc nghiệp vụ.

Hãy tách ba mức:
1. Parse: file có đúng cú pháp CSV/YAML theo parser và dialect không?
2. Binding: các cột/key có ánh xạ được vào kiểu Java không?
3. Validation: giá trị có đáp ứng quy tắc nghiệp vụ không?

Thông báo lỗi nên chỉ ra record/field hoặc YAML path khi có thể. Không nên trả nguyên stack trace hoặc nội dung nhạy cảm của file cho người gửi.

## 28. Kiểm thử các trường hợp biên của CSV

Một bộ test CSV nên bao gồm delimiter, quote, newline và dữ liệu rỗng:

~~~csv
id,comment
1,"Contains, comma"
2,"Contains ""quoted"" text"
3,"First line
Second line"
4,
5,""
6," leading and trailing "
~~~

Các giá trị cần xác nhận sau khi parse:
- Field 1 giữ dấu phẩy bên trong.
- Field 2 có quote đơn bên trong giá trị.
- Field 3 giữ newline.
- Field 4 tuân theo null/empty policy.
- Field 5 là empty string nếu dialect quy định như vậy.
- Field 6 giữ khoảng trắng nếu không có bước trim.

Bổ sung test với semicolon/tab delimiter, CRLF/LF record separator, UTF-8 có/không BOM, header đổi thứ tự, duplicate header, field cuối rỗng, quote mở không đóng, record sai số cột và dữ liệu Unicode.

## 29. Kiểm thử YAML quoted và multiline scalar

Fixture:

~~~yaml
title: "Status: ready"
plain_code: "00123"
single_quote: 'It''s a valid scalar'
double_quote: "line one\nline two"
literal: |-
  first line
  second line
folded: >-
  a long paragraph
  continued on the next source line
~~~

Test nên xác nhận giá trị Java sau parse:
- title giữ nguyên dấu hai chấm.
- plain_code vẫn là String, không bị chuyển thành number.
- single_quote chứa một dấu nháy đơn.
- double_quote có newline được giải mã từ escape.
- literal giữ line break và không có newline cuối do `|-`.
- folded có dấu cách giữa các dòng thường và không có newline cuối do `>-`.

Khi so sánh output YAML, ưu tiên kiểm tra giá trị semantic bằng DTO/JsonNode thay vì yêu cầu writer giữ nguyên quote style hoặc indentation của file gốc, trừ khi formatting là yêu cầu riêng.

## 30. Chọn parser và cách đọc phù hợp

| Tình huống | Cách xử lý |
|---|---|
| CSV nhỏ, schema cố định | CsvMapper với CsvSchema rõ ràng |
| CSV có quoted multiline field | CsvMapper hoặc parser CSV chuẩn, không split dòng thủ công |
| CSV rất lớn | MappingIterator hoặc streaming để xử lý từng record |
| CSV delimiter/header thay đổi theo nguồn | Xác định dialect trước, tạo schema tương ứng |
| YAML cấu hình có nested object | YAMLMapper binding vào DTO |
| YAML có multiline prose/script | Dùng block scalar `|` hoặc `>` |
| YAML có nhiều dạng scalar đặc biệt | Quote rõ và kiểm tra kiểu sau parse |
| JSON/YAML có payload động | Giữ subtree bằng mô hình tree phù hợp |
| Cần bảo toàn nguyên văn formatting | Dùng công cụ xử lý text/format chuyên dụng thay vì chỉ databind |

## 31. Quy trình tích hợp an toàn

Khi nhận file CSV hoặc YAML từ một hệ thống khác:
1. Xác nhận encoding và giới hạn byte file/request.
2. Xác định đúng định dạng và dialect.
3. Với CSV, thống nhất delimiter, quote, escape, line separator, header và null marker.
4. Với YAML, xác nhận indentation, scalar style, document markers và parser version.
5. Dùng CsvMapper/CsvSchema hoặc YAMLMapper thay vì tự split chuỗi.
6. Đọc quoted multiline field như một phần của record/scalar.
7. Ánh xạ vào DTO có kiểu dữ liệu rõ ràng.
8. Phân biệt missing, null, empty string và whitespace.
9. Validate số cột, tên header, field bắt buộc và giới hạn collection.
10. Kiểm thử delimiter, quote, newline, Unicode, BOM và dữ liệu rỗng.
11. Với file lớn, dùng streaming và giới hạn số record.
12. Ghi output bằng writer cùng dialect mà consumer mong đợi.

## Kết luận

Dấu phân cách, trích dẫn và newline là một phần của wire format. Trong CSV, delimiter tách field, quote bảo vệ delimiter/quote/newline nằm trong giá trị, và một record có thể trải qua nhiều dòng vật lý. Trong YAML, cấu trúc dựa trên indicator và indentation; quoted scalar giúp tránh mơ hồ, còn block scalar `|` giữ line break và `>` gộp các dòng thành prose.

Hãy dùng `CsvMapper` với `CsvSchema` để xác định dialect CSV và `YAMLMapper` để đọc/ghi YAML. Không tự tách CSV theo dấu phẩy hoặc newline, không tự xử lý quote bằng replace và không giả định YAML block style được giữ nguyên sau round-trip. Xác định rõ encoding, null semantics, header, delimiter và multiline rules; sau đó kiểm thử bằng fixture có dấu phẩy, quote, newline, khoảng trắng và Unicode để bảo đảm dữ liệu được khôi phục đúng.

