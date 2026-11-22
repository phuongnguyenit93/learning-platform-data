# Dùng bộ xử lý đúng định dạng cho JSON, CSV, đường dẫn hoặc URI

## 1. Một String có thể chứa nhiều ngôn ngữ dữ liệu khác nhau

Trong Java, kiểu `String` chỉ lưu một dãy ký tự. Nó **không tự cho biết** dãy đó là JSON, bản ghi CSV, đường dẫn tệp hay URI. Mỗi định dạng có **ngữ pháp và quy tắc escape riêng**. Nếu lấy thao tác chuỗi phổ thông như `split`, `substring`, `replace` hoặc regex để thay thế bộ phân tích định dạng, kết quả thường chỉ đúng với dữ liệu đơn giản.

Ví dụ bốn chuỗi nhìn có vẻ dễ xử lý:

```text
{"message":"Lan said \"Hello\"","count":2}
"Lan, A.","Dòng đầu
Dòng thứ hai"
reports/2026/../summary.csv
https://example.com/search?q=Java%20%26%20Spring#results
```

- JSON có chuỗi được quote, ký tự escape, kiểu số, `null`, array và object.
- CSV có dấu phân cách nằm **bên trong trường được quote**, dấu nháy kép được escape bằng hai dấu nháy liên tiếp, thậm chí một trường có thể chứa newline.
- Đường dẫn có phân đoạn, quy tắc tương đối/tuyệt đối, hệ thống tệp và các ký hiệu `.`, `..`.
- URI có scheme, authority, path, query, fragment, percent-encoding và ký tự dành riêng.

Một API tốt cần nói rõ **đầu vào thuộc định dạng nào**, dùng bộ xử lý phù hợp để tạo ra kiểu dữ liệu có cấu trúc, rồi mới thực hiện logic nghiệp vụ. Không nên biến mọi thứ thành `String.split(...)` chỉ vì mọi đầu vào đều bắt đầu từ chuỗi.

## 2. Bảng chọn API theo loại dữ liệu

| Dữ liệu | Công cụ phù hợp trong Java | Đầu ra mong đợi | Tránh cách làm |
| --- | --- | --- | --- |
| JSON | Jackson `ObjectMapper`, Gson hoặc thư viện JSON tương thích | Object/record, cây JSON, hoặc luồng token | Tự tách theo dấu phẩy, dấu hai chấm hay dấu ngoặc |
| CSV | Apache Commons CSV, OpenCSV hoặc parser có cấu hình đúng dialect | Bản ghi và các trường, kể cả giá trị rỗng | `split(",")` hoặc `split("\n")` mù quáng |
| Đường dẫn tệp | `java.nio.file.Path`, `Files` | Các phân đoạn đường dẫn, đối tượng truy cập file | Tự nối đường dẫn bằng `"/"` hoặc `"\\"` |
| URI | `java.net.URI` và URI builder phù hợp | Scheme, host, path, query, fragment | Cắt chuỗi dựa trên `"://"`, `"/"`, `"?"`, `"&"` |
| Query tham số form | URL/form encoder hoặc URI builder ở đúng ngữ cảnh | Giá trị query được encode đúng | Dùng `URLEncoder` cho mọi thành phần URI |

**Chọn parser là một phần của hợp đồng API**, không chỉ là vấn đề tiện lợi. Nó giúp xử lý đúng dữ liệu hợp lệ phức tạp, phân biệt input sai, và tránh việc mã hóa hai lần hoặc làm mất thông tin.

## 3. JSON: parser hiểu cấu trúc, kiểu dữ liệu và escaping

### 3.1. Vì sao split theo dấu phẩy hoặc dấu hai chấm sẽ sai?

Ví dụ:

```json
{
  "name": "Lan, A.",
  "address": {"city": "Hà Nội"},
  "tags": ["Java", "Spring"],
  "enabled": true,
  "note": null
}
```

Nếu gọi `split(",")`, dấu phẩy trong `"Lan, A."` sẽ bị coi là dấu phân cách trường, trong khi nó chỉ là **nội dung chuỗi**. Dấu phẩy giữa các phần tử của array cũng không nằm ở cùng cấp với dấu phẩy giữa các thuộc tính của object. Tương tự, `split(":")` không phân biệt dấu hai chấm của thuộc tính với ký tự bên trong giá trị chuỗi.

JSON còn có escape `\"`, `\\`, `\n`, `\uXXXX`; phân biệt `42` (number) với `"42"` (string), `true` (boolean), `null` và trường không tồn tại. Việc tự viết một loạt `replace` hiếm khi xử lý đủ các trường hợp.

### 3.2. Parse bằng Jackson

Với ứng dụng có thư viện Jackson Databind trong classpath, có thể ánh xạ JSON vào một kiểu Java:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

record Product(String sku, int quantity) {}

ObjectMapper mapper = new ObjectMapper();
String json = """
        {"sku":"SKU-01","quantity":3}
        """;

Product product = mapper.readValue(json, Product.class);
System.out.println(product.sku());      // SKU-01
System.out.println(product.quantity()); // 3

String serialized = mapper.writeValueAsString(product);
System.out.println(serialized); // {"sku":"SKU-01","quantity":3}
```

**Đây là đoạn minh họa để đặt trong một lớp/phương thức Java**, không phải tệp độc lập. Cần khai báo dependency `com.fasterxml.jackson.core:jackson-databind` với phiên bản phù hợp do dự án quản lý; Java 17 **không có Jackson sẵn trong JDK**. Record cần phiên bản Jackson có hỗ trợ Java records.

Jackson cũng hỗ trợ `JsonNode` để duyệt JSON linh hoạt, hoặc streaming API cho đầu vào lớn. Khi dữ liệu có schema cố định, chuyển thành record/class giúp logic nghiệp vụ có kiểu rõ ràng; khi cấu trúc động, cây JSON thường phù hợp hơn.

Lưu ý: **deserialize thành công chưa thay thế kiểm tra nghiệp vụ**. Ví dụ `quantity` có thể cần lớn hơn 0; định dạng JSON hợp lệ chưa bảo đảm giá trị hợp lệ. Các tùy chọn Jackson về field thiếu, field lạ và ép kiểu (coercion) phải phù hợp hợp đồng API; không nên dựa vào giá trị mặc định của trường primitive rồi im lặng chấp nhận thiếu trường.

### 3.3. Tạo JSON bằng serializer, không tự ghép dấu nháy

Cách ghép chuỗi thủ công:

```java
String json = "{\"message\":\"" + userText + "\"}";
```

sẽ sai khi `userText` có dấu nháy kép, backslash hoặc các ký tự điều khiển. Nếu nguồn dữ liệu không đáng tin cậy, việc ghép JSON sai còn gây lỗi dữ liệu hoặc làm thay đổi cấu trúc.

Thay vào đó, để serializer chịu trách nhiệm escape:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

ObjectMapper mapper = new ObjectMapper();
String result = mapper.writeValueAsString(
        Map.of("message", "Lan said \"Hello\"")
);
// result là JSON hợp lệ với dấu nháy trong giá trị được escape.
```

Đây cũng là đoạn minh họa có dependency Jackson. Khi output bắt buộc hợp lệ theo một schema, hãy kết hợp serializer với schema validation hoặc kiểm tra domain trước khi gửi.

## 4. CSV: tách bản ghi và trường theo đúng dialect

### 4.1. Dấu phẩy chưa chắc là dấu phân cách

CSV thường được mô tả ngắn là “các giá trị cách nhau bằng dấu phẩy”, nhưng trường được đặt trong dấu nháy kép có thể **chứa dấu phẩy, newline hoặc dấu nháy**. Ví dụ CSV sau có một dòng tiêu đề và một dòng dữ liệu:

```csv
name,note
"Lan, A.","Said ""hello"""
```

Bản ghi dữ liệu có **hai trường**:

1. `Lan, A.`
2. `Said "hello"`

`split(",")` sẽ tách sai trường đầu. Một ví dụ khác:

```csv
id,note
1,"First line
Second line"
```

Trường `note` chứa newline, nhưng vẫn thuộc **một bản ghi CSV**. Vì vậy, `split("\n")` để đếm số dòng rồi `split(",")` để lấy trường không phải bộ đọc CSV tổng quát.

Các file mang đuôi `.csv` còn có thể dùng dấu chấm phẩy `;`, tab, escape riêng, encoding và quy tắc header khác nhau. Cần xác định **dialect** (delimiter, quote, escape, header, record separator, chính sách ô rỗng) từ nguồn dữ liệu.

### 4.2. Parse bằng Apache Commons CSV

Khi dự án đã thêm dependency `org.apache.commons:commons-csv`, có thể dùng:

```java
import java.io.StringReader;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

String input = """
        name,note
        "Lan, A.","Said ""hello"""
        """;

try (CSVParser parser =
             CSVFormat.RFC4180.parse(new StringReader(input))) {
    for (CSVRecord record : parser) {
        System.out.println(record.get(0) + " | " + record.get(1));
    }
}
```

Đây là **đoạn minh họa** đặt trong một phương thức có thể xử lý `IOException`, và cần thư viện Commons CSV trên classpath. Nó đọc cả dòng tiêu đề như bản ghi đầu tiên; nếu muốn truy cập cột theo **tên header**, cần cấu hình header theo API của phiên bản Commons CSV đang sử dụng.

Cấu hình đúng phụ thuộc nguồn CSV: không phải mọi tập tin đều tuân thủ RFC 4180, và không nên giả định mọi dấu `;` hoặc tab trong dữ liệu đều là sai.

### 4.3. Ghi CSV bằng printer và giữ đủ trường

Khi xuất CSV, hãy dùng chức năng ghi của thư viện để quote và escape trường. Không tự ghép:

```java
String line = name + "," + note; // Có thể làm hỏng CSV.
```

Các bộ ghi CSV chuyên dụng biết khi nào phải thêm dấu nháy và biến dấu `"` bên trong thành `""`. Nếu số cột là cố định, phải kiểm tra số trường sau khi parser xử lý, kể cả trường rỗng ở cuối.

Ví dụ `A,B,` biểu thị **ba trường** trong mô hình CSV có dấu phân cách literal: `A`, `B` và trường cuối rỗng. Dùng `"A,B,".split(",")` trong Java sẽ bỏ trường rỗng cuối; `split(",", -1)` giữ được trường đó với **CSV cực kỳ đơn giản**, nhưng vẫn **không xử lý** các trường quoted, embedded comma hoặc newline. `-1` không biến `split` thành CSV parser.

Khi xuất CSV cho ứng dụng bảng tính, cần xem xét dữ liệu người dùng bắt đầu bằng `=`, `+`, `-` hoặc `@`: một số phần mềm có thể diễn giải chúng như **công thức** khi mở tệp. Việc CSV được quote đúng cú pháp không đồng nghĩa an toàn khi hiển thị trong spreadsheet; cần chính sách xuất dữ liệu theo ứng dụng đích để giảm nguy cơ công thức được thực thi.

## 5. Đường dẫn: dùng Path thay cho nối chuỗi

### 5.1. Đường dẫn là cấu trúc của hệ thống tệp

Trong Java 17, `java.nio.file.Path` biểu diễn đường dẫn tệp theo **file-system provider** đang dùng. Nó hỗ trợ phân đoạn, resolve, normalize, truy xuất tên tệp và thao tác thông qua `Files`:

```java
import java.nio.file.Path;

Path root = Path.of("reports");
Path target = root.resolve(Path.of("2026", "summary.csv"));

System.out.println(target.getFileName()); // summary.csv
```

Tránh tự nối:

```java
String path = rootText + "/" + fileName;
```

vì dấu phân cách và cách biểu diễn ổ đĩa/thư mục gốc phụ thuộc nền tảng; nhiều dấu `/`, `\\`, đường dẫn tuyệt đối hoặc các phân đoạn `..` còn có thể làm ý nghĩa đường dẫn khác dự định.

Cùng một đường dẫn có thể được biểu diễn bằng nhiều cách text khác nhau. `Path.normalize()` loại các thành phần `.` và xử lý các cặp phân đoạn `name/..` **theo cú pháp**, chưa cần truy cập hệ thống tệp.

### 5.2. Dùng resolve và normalize đúng mục đích

```java
Path root = Path.of("documents").toAbsolutePath().normalize();
Path relative = Path.of("2026", "report.csv");
Path target = root.resolve(relative).normalize();

System.out.println(target.getFileName()); // report.csv
System.out.println(target.startsWith(root)); // true
```

Nếu người dùng cung cấp `../secret.txt` và ứng dụng chỉ cho phép đặt tệp dưới `root`, cần kiểm tra:

```java
Path attempt = root.resolve(Path.of("..", "secret.txt")).normalize();
boolean inside = attempt.startsWith(root);
System.out.println(inside); // false
```

`Path.startsWith(Path)` so sánh **các thành phần đường dẫn**, khác với `String.startsWith`. Ví dụ đường dẫn `/data/reports-other` không nằm trong root `/data/reports` dù chuỗi ký tự có chung tiền tố.

**Lưu ý bảo mật quan trọng:** kiểm tra `normalize()`/`startsWith(root)` chỉ là **kiểm tra cấu trúc đường dẫn theo cú pháp**. Nó không ngăn trường hợp symlink bên trong root trỏ đến một vị trí bên ngoài, và không tự khắc phục race condition giữa kiểm tra với lúc mở tệp. Với yêu cầu giới hạn truy cập nghiêm ngặt, cần thiết kế quy trình filesystem phù hợp: kiểm tra đường dẫn thực bằng `toRealPath` khi có tệp, xử lý symlink và quyền truy cập, cân nhắc thao tác gắn với directory handle/secure directory stream tùy hệ thống tệp. Không dùng một phép kiểm tra text đơn lẻ như bằng chứng “đã chống mọi path traversal”.

### 5.3. File Path không đồng nghĩa URI

`Path.of("data", "report.csv")` là đường dẫn tệp tương đối. `URI.create("https://example.com/report.csv")` là URI HTTPS. Chúng có cú pháp và cơ chế truy cập khác nhau.

`Path.of(uri)` được dùng cho URI chỉ hệ thống tệp được provider hỗ trợ, phổ biến là `file:`, **không dùng để chuyển URL HTTP/HTTPS thành đường dẫn cục bộ**. Nếu cần tải tài nguyên HTTP, dùng HTTP client (`java.net.http.HttpClient`) hoặc thư viện phù hợp, rồi lưu kết quả bằng `Files` dưới một `Path` do ứng dụng kiểm soát.

## 6. URI: phân tách thành phần và mã hóa theo ngữ cảnh

### 6.1. URI có cấu trúc riêng

Ví dụ:

```text
https://example.com/search?q=Java%20%26%20Spring#results
└scheme └authority┘ └path┘ └────query─────┘ └fragment
```

Các thành phần có ý nghĩa khác nhau:

| Thành phần | Mục đích |
| --- | --- |
| Scheme | `https`, `http`, `file`, v.v. |
| Authority | Có thể chứa user info, host và port. |
| Path | Các phân đoạn tài nguyên. |
| Query | Phần sau `?` theo cú pháp của dịch vụ. |
| Fragment | Phần sau `#`; không phải phần request path gửi máy chủ theo nghĩa thông thường. |

Java cung cấp `java.net.URI` để parse và xử lý cú pháp URI:

```java
import java.net.URI;

URI uri = URI.create(
        "https://example.com/search?q=Java%20%26%20Spring#results");

System.out.println(uri.getScheme());    // https
System.out.println(uri.getHost());      // example.com
System.out.println(uri.getPath());      // /search
System.out.println(uri.getRawQuery());  // q=Java%20%26%20Spring
System.out.println(uri.getFragment());  // results
```

`getRawQuery()` giữ percent-encoding; `getQuery()` trả dữ liệu query đã được decode theo quy tắc của `URI`. Nhưng `URI` **không tự biến một query thành map nhiều tham số theo chuẩn riêng của ứng dụng**.

### 6.2. Mã hóa query value không giống mã hóa path segment

Trong chuỗi `?q=Java%20%26%20Spring`, `%26` thể hiện ký tự `&` thuộc **giá trị tham số**, không phải dấu phân tách hai tham số. Nếu ghép `?q=` với text tùy ý chưa encode, một dấu `&` trong dữ liệu có thể bị hiểu thành phần cú pháp query.

Với **giá trị query được mã hóa theo application/x-www-form-urlencoded**, có thể dùng:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String queryValue = "Java & Spring";
String encoded = URLEncoder.encode(queryValue, StandardCharsets.UTF_8);
URI search = URI.create("https://example.com/search?q=" + encoded);

System.out.println(search.getRawQuery());
// q=Java+%26+Spring
```

Dấu cách được form-encode thành `+`, dấu `&` thành `%26`. Đây là cách mã hóa phù hợp cho **form-style query parameter value**; không dùng `URLEncoder` cho toàn bộ URL hoặc toàn bộ path. Trong URI path, ký tự `+` có thể mang nghĩa literal, còn `/` phân tách path segment. Để tạo URI với nhiều path segments và query params tùy ý, dùng URI builder đáng tin cậy, biết encode **từng thành phần đúng ngữ cảnh**.

Nếu dùng `new URI(scheme, authority, path, query, fragment)`, vẫn phải phân biệt các dấu reserved có ý nghĩa bên trong thành phần: constructor mã hóa ký tự bất hợp lệ nhưng không thể đoán rằng dấu `/` trong một path string là dữ liệu thuộc **một segment** hay dấu phân tách segment. Mã hóa đúng theo **ý nghĩa thành phần** vẫn là trách nhiệm của API gọi.

### 6.3. URI.resolve: xây đường dẫn tương đối, nhưng kiểm tra nguồn

```java
URI base = URI.create("https://example.com/api/");
URI userEndpoint = base.resolve("users/42");

System.out.println(userEndpoint.getPath());
// /api/users/42
```

Dấu `/` cuối ở base ảnh hưởng cách resolve đường dẫn tương đối. Nếu base là `https://example.com/api` (không có slash cuối), chuỗi `users/42` có thể thay phân đoạn `api` thay vì được thêm dưới nó.

**Không dùng `base.resolve(userSuppliedUri)` rồi mặc định đích vẫn nằm trên cùng host**. Chuỗi đầu vào bắt đầu bằng `https://...` hoặc `//other-host/...` có thể dẫn đến URI đích khác. Khi xây dựng URL cho request ra ngoài, phải kiểm tra scheme, host, port, path và các chính sách truy cập sau khi resolve; khi theo redirect còn cần xem lại đích mới. Việc parser tạo thành công `URI` không bảo đảm URL an toàn để gọi mạng.

## 7. Ví dụ Java 17 độc lập, không cần thư viện ngoài

Tạo tệp `StructuredFormatDemo.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class StructuredFormatDemo {
    public static void main(String[] args) {
        String userInput = "Java & Spring";
        String encoded =
                URLEncoder.encode(userInput, StandardCharsets.UTF_8);
        URI search = URI.create(
                "https://example.com/search?q=" + encoded);

        URI base = URI.create("https://example.com/api/");
        URI endpoint = base.resolve("users/42");

        Path root = Path.of("documents")
                .toAbsolutePath().normalize();
        Path safe = root.resolve(
                Path.of("2026", "report.csv")).normalize();
        Path escape = root.resolve(
                Path.of("..", "secret.txt")).normalize();

        System.out.println("query: " + search.getRawQuery());
        System.out.println("path: " + endpoint.getPath());
        System.out.println("file name: " + safe.getFileName());
        System.out.println("inside root: " + safe.startsWith(root));
        System.out.println("escape rejected: " +
                !escape.startsWith(root));
        System.out.println("uri absolute: " + search.isAbsolute());

        String tricky = "Lan,\"said \"\"hello\"\"\"";
        System.out.println("naive CSV parts: " +
                tricky.split(",").length);
    }
}
```

Biên dịch và chạy:

```bash
javac StructuredFormatDemo.java
java StructuredFormatDemo
```

Kết quả:

```text
query: q=Java+%26+Spring
path: /api/users/42
file name: report.csv
inside root: true
escape rejected: true
uri absolute: true
naive CSV parts: 2
```

Các dòng đầu xác nhận việc mã hóa giá trị query và sử dụng `URI.resolve`, `Path.resolve`/`normalize` đúng ngữ cảnh. Dòng cuối cố tình cho thấy `split(",")` tạo hai đoạn vì nó gặp một dấu phẩy nằm trong chuỗi quoted; với CSV hợp lệ `Lan,"said ""hello"""`, dấu phẩy là delimiter, nhưng các đoạn thô do `split` để lại **chưa được giải mã quote/escape** và không phải các giá trị trường CSV đúng nghĩa. Với một trường quoted chứa dấu phẩy như `"Lan, A.","hello"`, `split(",")` còn tạo **sai số lượng trường**.

Ví dụ `escape rejected: true` chỉ chứng minh thao tác kiểm tra đường dẫn **về mặt cú pháp**; để kiểm tra đường dẫn thật trên hệ thống tệp vẫn cần xét symlink và các vấn đề truy cập nêu ở mục 5.

## 8. Thiết kế API: nhận dữ liệu có ý nghĩa, trả kiểu có cấu trúc

Hạn chế tối đa việc để các tầng nghiệp vụ phải đoán định dạng của một chuỗi chung chung.

Thay vì API mơ hồ như:

```java
void process(String data);
```

hãy thiết kế đường đi rõ ràng, ví dụ:

```text
HTTP body JSON --JSON parser--> OrderRequest --validation--> domain command
CSV upload ----CSV parser----> CSV records ---mapping-----> domain rows
Path input ----Path/Files-----> normalized/checkable file path
URI input -----URI parser-----> URI components -> validated outbound request
```

Tại ranh giới hệ thống, nên tách thành các bước:

1. **Xác định định dạng** từ hợp đồng, Content-Type hoặc cấu hình đáng tin, không đoán bằng `contains(",")` hay `startsWith("{")`.
2. **Parse bằng bộ xử lý đúng** để tôn trọng quoting, escape, nested structures và cú pháp thành phần.
3. **Kiểm tra tính hợp lệ về cấu trúc và nghiệp vụ**: trường bắt buộc, kiểu, số cột, giới hạn độ dài, phạm vi giá trị, path root hoặc destination host.
4. **Sử dụng kiểu dữ liệu có ý nghĩa** trong phần còn lại của chương trình, thay vì đưa raw string đi khắp nơi.
5. **Serialize/encode khi xuất** bằng đúng công cụ cho định dạng đích; tránh tự ghép lại dữ liệu bằng dấu phân cách.

Ở bước parse, lỗi phải được chuyển thành thông báo rõ ràng cho người gọi, ví dụ “JSON sai cú pháp”, “CSV thiếu cột”, “đường dẫn nằm ngoài thư mục cho phép”, “URI có scheme không được chấp nhận”. Không nuốt mọi ngoại lệ rồi trả một chuỗi rỗng, vì chuỗi rỗng đôi khi lại là dữ liệu hợp lệ.

## 9. Những bẫy thiết kế thường gặp

### 9.1. Dùng một regex cho định dạng có cấu trúc lồng nhau

Regex vẫn hữu ích để kiểm tra **mẫu đơn giản**, tìm token hoặc xác nhận một trường văn bản có pattern hẹp. Nhưng JSON có object/array lồng nhau và escape; CSV có quote/newline và trạng thái parser; URI có nhiều thành phần độc lập. Khi vấn đề là **phân tích toàn bộ định dạng**, chọn parser thay vì liên tục bổ sung regex cho từng phản ví dụ.

### 9.2. Nhầm escaping của định dạng này với định dạng khác

- JSON escape dấu `"` và `\` theo luật JSON.
- CSV escape dấu `"` trong quoted field bằng `""` ở dialect thông dụng.
- URI percent-encode theo vị trí và quy tắc từng thành phần.
- File path dùng quy tắc phân đoạn của file system; một số ký tự hợp lệ trên hệ này lại không hợp lệ trên hệ khác.

`String.replace("\"", "\\\"")` chỉ xử lý một trường hợp của JSON, không tạo serializer JSON hoàn chỉnh; `URLEncoder` không tạo đường dẫn file hợp lệ; `Pattern.quote` chỉ phục vụ regex literal, không tạo CSV hay JSON hợp lệ.

### 9.3. Nhầm parse thành công với dữ liệu đáng tin cậy

Một object JSON parse được vẫn có thể có giá trị bất hợp lệ; một CSV có cấu trúc hợp lệ vẫn có thể chứa công thức khi xuất vào bảng tính; một `Path` parse được vẫn có thể trỏ ngoài vùng được phép; một `URI` hợp lệ vẫn có thể trỏ tới đích mạng bị cấm.

Parser trả lời “**cú pháp có hiểu được không?**”. Việc dữ liệu có được phép xử lý hay không là **quyết định kiểm tra tiếp theo** dựa trên hợp đồng nghiệp vụ và chính sách truy cập.

### 9.4. Không kiểm soát kích thước và tài nguyên

JSON/CSV rất lớn có thể tiêu tốn bộ nhớ, thời gian xử lý và tài nguyên I/O. Đặt giới hạn kích thước input, số trường/cột, độ sâu cấu trúc, thời gian xử lý theo nhu cầu; với luồng lớn ưu tiên parser dạng streaming. Khi mở reader, parser hoặc file, dùng `try-with-resources` nếu đối tượng giữ tài nguyên cần đóng.

### 9.5. Dựa vào phần mở rộng tệp hoặc chuỗi URL để suy đoán

Tên tệp `.json` hoặc `.csv` chưa chứng minh nội dung đúng định dạng. Đuôi file chỉ là gợi ý, không thay thế parser và xác thực. Tương tự, kiểm tra `url.startsWith("https://trusted.example")` bằng text có thể đánh đồng host hợp lệ với `trusted.example.evil.test`. Hãy parse URI, so sánh host/scheme theo cấu trúc và áp dụng chính sách kết nối phù hợp.

## 10. Bài tập vận dụng

**Bài 1 — JSON:** Tạo record `Order(String id, int quantity)`; dùng JSON parser để đọc một JSON hợp lệ, sau đó thử giá trị `quantity` âm, thiếu trường và một chuỗi chứa dấu nháy/Unicode. Phân biệt lỗi parse với lỗi nghiệp vụ.

**Bài 2 — CSV:** Dùng CSV parser đọc bản ghi có `"Lan, A."`, trường `"said ""hello"""` và một trường chứa newline. In **đúng số cột** cùng giá trị đã bỏ quoting. Thử file có header và field rỗng cuối.

**Bài 3 — Path:** Nhận tên tệp tương đối do người dùng nhập, resolve từ một root cố định, kiểm tra cấu trúc phân đoạn, sau đó thảo luận cách symlink ảnh hưởng kiểm tra truy cập thực tế. Thử `summary.csv`, `2026/summary.csv`, `../outside.txt` và một absolute path.

**Bài 4 — URI:** Xây URI tìm kiếm từ từ khóa `"Java & Spring"` và xác nhận `&` nằm trong **giá trị** query. Thử resolve một relative path và một absolute URI; xác nhận scheme/host của kết quả trước khi gửi request.

## 11. Ghi nhớ

- **String chỉ là phương tiện chứa ký tự; định dạng mới quyết định cách parse**.
- JSON cần JSON parser/serializer; CSV cần CSV parser/printer được cấu hình đúng dialect.
- File path dùng `Path`, `resolve`, `normalize`, `Files`; kiểm tra root theo cú pháp chưa loại hết rủi ro symlink.
- URI dùng `URI` và URI builder/encoder phù hợp **từng thành phần**; `URLEncoder` dành cho form-style query value, không dành cho toàn URL.
- `split` và `replace` hữu ích cho chuỗi đơn giản nhưng không thay thế công cụ hiểu quoting, escape, nested structure, encoding hay semantics của định dạng.
- Sau bước parse vẫn cần kiểm tra nghiệp vụ, giới hạn tài nguyên và chính sách truy cập; khi xuất dữ liệu hãy dùng serializer/encoder đúng định dạng đích.
