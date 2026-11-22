# Charset, đóng stream và vòng đời tài nguyên tự mở

Trong một ứng dụng Spring Boot, việc đọc file cấu hình phụ trợ, CSV, JSON, template, dữ liệu mẫu hoặc file do người dùng tải lên thường chỉ cần vài dòng Java. Nhưng những dòng code đó lại nằm ở giao điểm của ba vấn đề dễ bị bỏ qua:

- **Charset**: chuyển đổi giữa byte và ký tự như thế nào để không lỗi dấu tiếng Việt hoặc sai nội dung dữ liệu?
- **Đóng stream**: ai phải gọi close(), gọi ở thời điểm nào, và làm sao bảo đảm đóng cả khi xảy ra exception?
- **Vòng đời tài nguyên**: resource nào do ứng dụng tự mở phải tự đóng, resource nào do Spring/container quản lý, và khi nào không được đóng thay cho chủ sở hữu?

Ba vấn đề này thường xuất hiện cùng nhau. Một file UTF-8 có thể bị đọc bằng charset mặc định khiến chữ **“Tiếng Việt”** thành ký tự lỗi. Một InputStream không được đóng có thể giữ file descriptor hoặc network connection. Một stream được đóng quá sớm có thể làm bước xử lý bất đồng bộ hoặc HTTP response thất bại giữa chừng.

Bài học giải thích cách xử lý ba trách nhiệm trên khi làm việc với **Spring Resource abstraction**, file trong classpath/executable JAR, file hệ thống, HTTP upload/download và các tài nguyên có vòng đời dài trong ApplicationContext.

## 1. Phân biệt byte, character, stream và resource

Đầu tiên cần tách rõ các khái niệm:

| Khái niệm | Trách nhiệm |
|---|---|
| **Byte** | Đơn vị dữ liệu nhị phân. File, socket và nhiều giao thức lưu/truyền byte. |
| **Character/String** | Biểu diễn văn bản ở tầng Java. |
| **Charset** | Quy tắc mã hóa ký tự thành byte và giải mã byte thành ký tự. |
| **InputStream** | Đọc một chuỗi byte từ một nguồn. |
| **OutputStream** | Ghi một chuỗi byte tới một đích. |
| **Reader** | Đọc dữ liệu văn bản dưới dạng ký tự. |
| **Writer** | Ghi dữ liệu văn bản dưới dạng ký tự. |
| **Resource** | Abstraction của Spring mô tả một tài nguyên và cung cấp cách mở stream để đọc, không đồng nghĩa bản thân luôn là stream đã mở. |

Luồng đọc một file văn bản:

~~~text
Classpath file / file trên ổ đĩa / network response
                       │
                       ▼
                Các byte nguồn
                       │
                       ▼
                 InputStream
                       │
                 Charset decoder
                       ▼
               InputStreamReader
                       │
                       ▼
                BufferedReader
                       │
                       ▼
                  String / text
~~~

Luồng ghi đảo chiều:

~~~text
String / text
      │
      ▼
    Writer
      │
  Charset encoder
      ▼
 OutputStream
      │
      ▼
File / response body / network destination
~~~

Một InputStream không biết file đang chứa UTF-8, UTF-16, ISO-8859-1 hay dữ liệu nhị phân. Chỉ khi code giải mã byte thành ký tự, charset mới trở thành quyết định bắt buộc.

## 2. Charset là gì?

**Charset** định nghĩa cách mã hóa hoặc giải mã văn bản. Ví dụ UTF-8 là một encoding của Unicode được dùng rất phổ biến trong ứng dụng hiện đại.

Java cung cấp các charset chuẩn trong:

~~~java
import java.nio.charset.StandardCharsets;
~~~

Ví dụ:

~~~java
String message = "Xin chào, Hà Nội!";

byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Nếu quá trình encode và decode dùng cùng charset phù hợp, chuỗi có thể được khôi phục chính xác.

### 2.1. Khi nào charset thật sự được dùng?

Khi đọc **byte thuần**, không có thao tác giải mã:

~~~java
byte[] data = inputStream.readAllBytes();
~~~

Nhưng khi tạo String từ byte:

~~~java
String text = new String(data, StandardCharsets.UTF_8);
~~~

thì charset đã được chọn. Tương tự, tạo InputStreamReader là quyết định cách giải mã:

~~~java
Reader reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8);
~~~

Đối với file ảnh, PDF, ZIP hoặc dữ liệu binary, không nên mặc định đọc thành String rồi ghi lại. Hãy xử lý dưới dạng byte bằng InputStream/OutputStream, hoặc dùng parser đúng định dạng.

### 2.2. Vì sao cần chỉ định charset tường minh?

Hai đoạn code có thể trông tương tự nhưng khác về ý nghĩa:

~~~java
String text = new String(bytes);
~~~

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Đoạn đầu sử dụng **default charset** của runtime. Charset mặc định có thể thay đổi theo phiên bản Java, cấu hình JVM hoặc môi trường triển khai. Java hiện đại thường mặc định UTF-8 nhưng việc phụ thuộc vào default vẫn khiến hợp đồng dữ liệu thiếu rõ ràng.

Đoạn sau khẳng định dữ liệu nguồn được mã hóa UTF-8. Nó ít phụ thuộc vào thiết lập máy chạy và dễ kiểm thử hơn.

Nguyên tắc nên áp dụng: **mọi ranh giới chuyển đổi byte ↔ text nên dùng charset được chỉ định rõ ràng**, nếu định dạng hoặc giao thức cho phép.

### 2.3. Charset sai làm hỏng dữ liệu như thế nào?

Một file được lưu theo UTF-8 nhưng đọc bằng charset khác có thể cho kết quả:

~~~text
Dữ liệu gốc:    Nguyễn Văn Bình
Giải mã sai:    Nguyá»…n VÄƒn BÃ¬nh
~~~

Đây là hiện tượng thường gọi là **mojibake**: cùng một chuỗi byte được hiểu theo bảng mã không đúng.

Một số lỗi khác:

- Ký tự lạ hoặc ký tự thay thế xuất hiện trong chuỗi.
- So sánh String, tìm kiếm hoặc xác thực chữ ký dữ liệu thất bại.
- Header CSV có ký tự bất thường khiến không tìm được tên cột.
- Dữ liệu được ghi lại với encoding sai, làm lỗi lan sang các hệ thống khác.

Không phải mọi lỗi có dấu tiếng Việt đều là bug của Spring Boot. Cần xác minh file nguồn thực sự được lưu bằng encoding nào và các bước đọc/ghi đang chọn charset nào.

## 3. Đọc văn bản UTF-8 từ file hệ thống

Với file trên filesystem, Java NIO cung cấp các API rõ ràng về charset.

### 3.1. File nhỏ: Files.readString

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileReader {

    public String load(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
~~~

Cách này ngắn gọn và phù hợp nếu toàn bộ nội dung file có thể nằm trong bộ nhớ.

Nếu file chứa hàng trăm MB hoặc nhiều GB, Files.readString có thể làm tăng memory usage mạnh vì phải tạo toàn bộ String.

### 3.2. File lớn: Files.newBufferedReader

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextLineCounter {

    public long countNonEmptyLines(Path path) throws IOException {
        long count = 0;

        try (BufferedReader reader =
                     Files.newBufferedReader(
                             path, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    count++;
                }
            }
        }

        return count;
    }
}
~~~

Đoạn code đọc lần lượt từng dòng, không giữ toàn bộ file trong RAM. Khi thoát khỏi try-with-resources, BufferedReader được đóng tự động.

### 3.3. Viết văn bản với charset rõ ràng

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextReportWriter {

    public void writeReport(Path target) throws IOException {
        try (BufferedWriter writer =
                     Files.newBufferedWriter(
                             target, StandardCharsets.UTF_8)) {

            writer.write("Báo cáo doanh thu");
            writer.newLine();
            writer.write("Chi nhánh: Hà Nội");
            writer.newLine();
        }
    }
}
~~~

Khi writer được đóng, dữ liệu buffer còn lại được flush và tài nguyên bên dưới được giải phóng. Lưu ý: **close/flush không bảo đảm mọi byte đã được đồng bộ bền vững xuống thiết bị lưu trữ trước khi mất điện**. Các yêu cầu durability cao cần chính sách file I/O riêng, có thể bao gồm fsync, giao dịch và atomic move.

### 3.4. Không dùng String.getBytes() không charset ở ranh giới lưu/truyền

Ví dụ không nên:

~~~java
byte[] body = report.getBytes();
~~~

Nên:

~~~java
byte[] body = report.getBytes(StandardCharsets.UTF_8);
~~~

Tương tự, tránh dựa vào default charset khi tạo InputStreamReader hoặc OutputStreamWriter nếu dữ liệu bên ngoài có quy ước encoding cụ thể.

## 4. InputStreamReader và BufferedReader đóng vai trò gì?

Một InputStream trả byte. Để đọc từng dòng văn bản, thường bọc nó bằng:

~~~java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                inputStream, StandardCharsets.UTF_8));
~~~

- **InputStreamReader**: giải mã byte thành ký tự theo UTF-8.
- **BufferedReader**: giảm các thao tác đọc nhỏ và hỗ trợ readLine().

Đừng coi readLine() là parser CSV đầy đủ. Một trường CSV có thể chứa dấu phẩy, dấu ngoặc kép hoặc xuống dòng bên trong dữ liệu theo quy tắc CSV. Nếu cần parse CSV đúng chuẩn, dùng thư viện hoặc parser phù hợp.

### 4.1. BufferedReader phải được đóng

Ví dụ:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                inputStream, StandardCharsets.UTF_8))) {

    String firstLine = reader.readLine();
    System.out.println(firstLine);
}
~~~

**Khi đóng BufferedReader, nó đóng InputStreamReader bên trong và InputStream mà reader đang bao bọc.**

Như vậy, nếu bạn là chủ sở hữu InputStream gốc, chỉ cần đưa wrapper ngoài cùng vào try-with-resources là đủ. Không bắt buộc phải liệt kê cả ba lớp bọc trong ba biến resource nếu hợp đồng ownership rõ ràng.

Điểm quan trọng: nếu InputStream gốc **thuộc về bên gọi** và bạn chỉ được mượn để đọc, việc tự đóng BufferedReader cũng sẽ đóng luôn stream mà bạn không sở hữu. Hãy xác định ownership trước khi đóng; phần sau sẽ giải thích chi tiết.

## 5. Byte Order Mark (BOM) và dấu hiệu khó thấy ở đầu file

Một số file UTF-8 có ba byte BOM ở đầu:

~~~text
EF BB BF
~~~

BOM có thể được dùng như dấu hiệu nhận diện encoding. UTF-8 không cần BOM, nhưng các công cụ xuất file đôi khi vẫn thêm.

Khi đọc file UTF-8 qua các API thông thường, BOM có thể xuất hiện trong text như ký tự **U+FEFF** ở đầu dữ liệu.

Ví dụ:

~~~text
File nhìn thấy:    id,name
Chuỗi thực tế:    U+FEFF + id,name
~~~

Nếu parser so sánh chính xác header **id**, kết quả có thể không match.

### 5.1. Bỏ BOM khi định dạng cho phép

Ví dụ xử lý riêng dòng đầu của một file văn bản có quy ước BOM tùy chọn:

~~~java
String firstLine = reader.readLine();

if (firstLine != null
        && !firstLine.isEmpty()
        && firstLine.charAt(0) == '\uFEFF') {
    firstLine = firstLine.substring(1);
}
~~~

Hãy chỉ xử lý BOM theo hợp đồng của định dạng nguồn. Không nên tự động xóa mọi ký tự đặc biệt đầu chuỗi vì dữ liệu có thể cần giữ nguyên. Nếu thư viện parse JSON/XML/CSV đã tự xử lý BOM theo đặc tả, hãy dùng đúng parser thay vì xử lý chồng chéo.

### 5.2. Đừng đoán charset chỉ từ tên file

Phần mở rộng **.txt**, **.csv**, **.properties** không tự chứng minh dữ liệu dùng UTF-8. Nếu nguồn là một hệ thống cũ có encoding khác, cần xác nhận từ tài liệu hoặc metadata đáng tin cậy.

Với dữ liệu nhập vào không rõ charset, xây quy tắc nhận diện/validation rõ ràng và ghi nhận lỗi, thay vì giải mã bằng default charset rồi tiếp tục sử dụng dữ liệu hỏng.

## 6. Spring Resource abstraction trong Spring Boot

Spring cung cấp interface:

~~~java
org.springframework.core.io.Resource
~~~

Resource biểu diễn một nguồn dữ liệu có thể đọc, cùng metadata như tên file, URL, khả năng tồn tại và khả năng đọc.

Một số implementation thường gặp:

| Loại | Trường hợp sử dụng |
|---|---|
| **ClassPathResource** | File đóng gói trong classpath của ứng dụng hoặc dependency JAR. |
| **FileSystemResource** | File thực trên filesystem. |
| **UrlResource** | Tài nguyên được xác định bằng URL thích hợp. |
| **ByteArrayResource** | Dữ liệu byte đã nằm trong RAM, có thể mở stream lại. |
| **InputStreamResource** | Bọc một InputStream đã có, thường chỉ thích hợp đọc một lần. |

Ví dụ:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.csv");
~~~

Trong một dự án Spring Boot:

~~~text
src/
└── main/
    └── resources/
        └── data/
            └── catalog.csv
~~~

Đường dẫn classpath là **data/catalog.csv**, không phải **src/main/resources/data/catalog.csv** khi ứng dụng đã được đóng gói.

### 6.1. Resource không đồng nghĩa InputStream đang mở

Với một ClassPathResource hoặc FileSystemResource thông thường, đối tượng Resource chủ yếu là mô tả **nơi tìm dữ liệu**. Gọi:

~~~java
InputStream in = resource.getInputStream();
~~~

sẽ mở stream để đọc nội dung.

Thường bạn có thể gọi getInputStream() nhiều lần để mở những stream độc lập từ cùng một ClassPathResource hoặc FileSystemResource, miễn tài nguyên còn tồn tại và được hỗ trợ.

Ngoại lệ cần chú ý: **InputStreamResource** bọc một stream đã mở và thường không có khả năng đọc lại. Không nên giả định mọi Resource là repeatable.

### 6.2. Có cần close(Resource) không?

Interface Resource không phải một tài nguyên cần đóng bằng AutoCloseable theo nghĩa thông thường. Đối với Resource descriptor như ClassPathResource, bạn không gọi resource.close().

Thứ bạn cần đóng là:

~~~java
InputStream in = resource.getInputStream();
~~~

và các Reader/Writer/stream khác mà code đã mở hoặc sở hữu.

Đừng nhầm vòng đời của **Resource bean** với vòng đời của **InputStream** được mở từ Resource.

## 7. Đọc file trong classpath bằng ClassPathResource

Ví dụ một file mẫu:

~~~text
src/main/resources/data/regions.txt
~~~

Nội dung UTF-8:

~~~text
Hà Nội
Đà Nẵng
Thành phố Hồ Chí Minh
~~~

Code đọc:

~~~java
package com.example.demo.resources;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class RegionLoader {

    public List<String> loadRegions() throws IOException {
        Resource resource =
                new ClassPathResource("data/regions.txt");

        List<String> regions = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        resource.getInputStream(),
                        StandardCharsets.UTF_8))) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    regions.add(line);
                }
            }
        }

        return regions;
    }
}
~~~

Điểm cần lưu ý:

1. Đường dẫn được xác định theo classpath của runtime.
2. **getInputStream()** mở dữ liệu; có thể ném IOException.
3. **InputStreamReader** giải mã UTF-8.
4. **BufferedReader** cho phép đọc từng dòng.
5. **try-with-resources** đóng stream kể cả khi vòng lặp hoặc parsing gặp lỗi.

Đối với file dữ liệu lớn, trả toàn bộ List vẫn tiêu tốn RAM theo số dòng. Ví dụ trên dùng file danh mục nhỏ. Với file lớn, nên xử lý tuần tự trong khi stream còn mở.

### 7.1. Vì sao không dùng new File("src/main/resources/...")?

Trong IDE, đường dẫn:

~~~java
new File("src/main/resources/data/regions.txt")
~~~

có thể tình cờ tồn tại vì process được chạy tại thư mục gốc của dự án.

Nhưng sau khi build executable JAR:

~~~text
app.jar
└── BOOT-INF
    └── classes
        └── data
            └── regions.txt
~~~

file classpath là một entry nằm bên trong artifact. Nó không nhất thiết tương ứng với một file độc lập trên filesystem.

Vì vậy, code phụ thuộc working directory của source tree sẽ thất bại khi triển khai. **ClassPathResource.getInputStream()** là API phù hợp để đọc resource nằm trong JAR.

### 7.2. Tránh Resource.getFile() với classpath trong JAR

Ví dụ có rủi ro:

~~~java
File file = new ClassPathResource(
        "data/regions.txt").getFile();
~~~

Khi chạy từ thư mục classes trong IDE, getFile() có thể hoạt động. Khi chạy từ executable JAR, resource không còn là một file riêng lẻ và getFile() có thể ném FileNotFoundException/IOException hoặc lỗi liên quan.

Hãy ưu tiên:

~~~java
try (InputStream in = new ClassPathResource(
        "data/regions.txt").getInputStream()) {
    // Đọc byte hoặc bọc bằng Reader với charset phù hợp.
}
~~~

Chỉ dùng Resource.getFile() khi hợp đồng của ứng dụng thật sự yêu cầu một file filesystem và bạn đã bảo đảm resource nằm trên filesystem, không nằm trong JAR.

## 8. ResourceLoader và đường dẫn cấu hình

Nếu nguồn có thể thay đổi giữa classpath và filesystem, dùng **ResourceLoader**:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

Resource resource = resourceLoader.getResource(
        "classpath:data/catalog.csv");
~~~

Một số location dạng minh họa:

~~~text
classpath:data/catalog.csv
file:/opt/app/input/catalog.csv
https://example.invalid/catalog.csv
~~~

ResourceLoader có thể tạo Resource tương ứng theo protocol/prefix và môi trường. Không phải mọi loại Resource đều được xử lý như nhau: classpath, file và network có quy tắc về khả năng đọc, performance và security khác nhau.

### 8.1. Service nhận ResourceLoader qua constructor

~~~java
package com.example.demo.resources;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final ResourceLoader resourceLoader;

    public CatalogService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public long countLines(String location)
            throws IOException {

        Resource resource =
                resourceLoader.getResource(location);

        long count = 0;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        resource.getInputStream(),
                        StandardCharsets.UTF_8))) {

            while (reader.readLine() != null) {
                count++;
            }
        }
        return count;
    }
}
~~~

Service mở stream **trong phạm vi của từng lần đọc**, đóng sau khi xong và giữ ResourceLoader là dependency được Spring quản lý.

Không cần và không nên cố đóng ResourceLoader sau mỗi lần gọi: nó là thành phần cung cấp cơ chế tìm resource, không phải InputStream của từng request.

### 8.2. Location có nguồn không tin cậy

Ví dụ countLines(String location) trên là minh họa API, **không nên cho phép client HTTP cung cấp tùy ý** những chuỗi như file:/... hoặc https://... để hệ thống server tự đọc.

Nếu ứng dụng đọc location từ request không tin cậy, có thể dẫn tới:

- Đọc file nội bộ ngoài vùng cho phép.
- Truy cập network không mong muốn (SSRF).
- Tài nguyên rất lớn khiến mất RAM/băng thông.
- Kết nối chậm làm treo worker thread.

Trong ứng dụng thật, hãy cấu hình location từ nguồn quản trị được tin cậy hoặc dùng allowlist/sandbox cụ thể. Không coi ResourceLoader là cơ chế kiểm tra quyền truy cập.

## 9. Resource.exists(), isReadable() và xử lý lỗi I/O

Bạn có thể kiểm tra:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.csv");

boolean exists = resource.exists();
boolean readable = resource.isReadable();
~~~

Nhưng kiểm tra exists/isReadable chỉ là quan sát tại một thời điểm. File có thể biến mất hoặc quyền truy cập thay đổi trước khi getInputStream() chạy. Một resource từ network còn có thể gặp timeout sau khi metadata trông hợp lệ.

Vì vậy, code vẫn cần xử lý IOException ở thao tác mở/đọc:

~~~java
public String firstLine(Resource resource)
        throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8))) {

        return reader.readLine();
    }
}
~~~

Không nên chỉ dùng:

~~~java
if (resource.exists()) {
    // Giả định mọi read phía sau chắc chắn thành công.
}
~~~

Nếu nội dung là bắt buộc khi startup, hãy quyết định rõ: startup thất bại khi không đọc được, hay ứng dụng có fallback an toàn? Không nên nuốt IOException và trả dữ liệu rỗng rồi coi đó là thành công nếu dữ liệu quan trọng.

## 10. try-with-resources và trách nhiệm đóng stream

Java hỗ trợ **try-with-resources** cho đối tượng triển khai AutoCloseable, bao gồm InputStream, Reader, Writer và nhiều loại tài nguyên khác.

Cú pháp:

~~~java
try (InputStream in = resource.getInputStream()) {
    // Đọc dữ liệu.
}
~~~

Khi thoát khối try, Java sẽ gọi close() ngay cả khi:

- Đọc hết file bình thường.
- Return sớm.
- Ném exception khi đọc.
- Ném exception trong logic parsing.

Ví dụ:

~~~java
public byte[] read(Resource resource) throws IOException {
    try (InputStream in = resource.getInputStream()) {
        return in.readAllBytes();
    }
}
~~~

**readAllBytes() không tự đóng InputStream.** Trong ví dụ, try-with-resources mới bảo đảm đóng stream.

### 10.1. Đóng wrapper ngoài cùng thường đóng stream bên trong

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                resource.getInputStream(),
                StandardCharsets.UTF_8))) {
    return reader.readLine();
}
~~~

Khi đóng BufferedReader, InputStreamReader và InputStream bên dưới cũng được đóng.

Không cần:

~~~java
InputStream in = resource.getInputStream();
BufferedReader reader = new BufferedReader(
        new InputStreamReader(in, StandardCharsets.UTF_8));
// Xử lý mà không đóng reader hoặc in.
~~~

Đoạn code không quản lý closing này có nguy cơ leak nếu quá trình đọc hoàn tất hoặc gặp lỗi.

### 10.2. Đóng theo thứ tự ngược nếu có nhiều resource

~~~java
try (InputStream in = resource.getInputStream();
     Reader reader = new InputStreamReader(
             in, StandardCharsets.UTF_8);
     BufferedReader buffered = new BufferedReader(reader)) {

    System.out.println(buffered.readLine());
}
~~~

Java đóng các biến resource theo thứ tự ngược: buffered, reader, in. Trong ví dụ, đóng wrapper ngoài thường đã đóng các lớp dưới; những lời gọi close() bổ sung trên cùng luồng thường là dư thừa nhưng nhiều implementation chịu được.

Thường chỉ khai báo wrapper ngoài cùng trong try-with-resources cho gọn và rõ ownership. Với nhiều resource độc lập, khai báo từng đối tượng riêng.

### 10.3. Exception trong close() xử lý thế nào?

Nếu code trong try ném exception và close() cũng ném exception, Java giữ exception gốc và gắn lỗi close dưới dạng **suppressed exception**.

Ví dụ:

~~~java
try (InputStream in = resource.getInputStream()) {
    parse(in);  // Có thể lỗi.
}
~~~

Khi chẩn đoán, đừng chỉ đọc một dòng đầu tiên của stack trace; suppressed exceptions có thể giúp giải thích vấn đề khi giải phóng tài nguyên.

Không nên tự viết finally đóng stream mà vô tình che mất exception chính. try-with-resources giúp xử lý tình huống này an toàn hơn.

## 11. Ai sở hữu stream và ai phải đóng?

Quy tắc quan trọng nhất của tài nguyên là **ownership**: bên nào sở hữu trách nhiệm quản lý vòng đời?

Có ba mẫu thường gặp:

1. **Mở và sử dụng tại chỗ**: code gọi getInputStream()/Files.newBufferedReader() thường phải đóng trong cùng phạm vi.
2. **Nhận tài nguyên từ bên gọi (borrowed)**: code không mặc nhiên được phép đóng; phải tuân theo hợp đồng của API.
3. **Chuyển giao cho framework/container (transferred)**: framework tiếp quản việc sử dụng và đóng tài nguyên; code không được đóng quá sớm.

### 11.1. Mở ở đâu, đóng ở đó

Đây là trường hợp đơn giản nhất:

~~~java
public long countBytes(Resource resource) throws IOException {
    try (InputStream in = resource.getInputStream()) {
        long count = 0;
        byte[] buffer = new byte[8192];

        int read;
        while ((read = in.read(buffer)) != -1) {
            count += read;
        }
        return count;
    }
}
~~~

Method **tự gọi getInputStream** nên tự đóng InputStream trước khi trả kết quả.

### 11.2. API nhận InputStream của bên gọi

Ví dụ một helper chỉ xử lý dữ liệu:

~~~java
public long countBytesBorrowed(InputStream in)
        throws IOException {

    long count = 0;
    byte[] buffer = new byte[8192];

    int read;
    while ((read = in.read(buffer)) != -1) {
        count += read;
    }
    return count;
}
~~~

Helper này **không đóng** InputStream. Vì người gọi đưa stream vào, người gọi có thể còn cần tiếp tục sử dụng sau method này.

Vòng đời phía caller:

~~~java
try (InputStream in = resource.getInputStream()) {
    long size = countBytesBorrowed(in);
    System.out.println(size);
}
~~~

Đừng suy luận rằng mọi API nhận InputStream đều phải để mở. Một số thư viện quy định API sẽ **take ownership** và đóng sau khi sử dụng. Hãy đọc hợp đồng cụ thể; trong API tự thiết kế, nên ghi rõ:

- Method có đóng stream được truyền vào không?
- Method có đọc hết stream không?
- Method có giữ lại stream cho xử lý sau khi trả về không?
- Caller có được tiếp tục sử dụng stream không?

### 11.3. Tránh đóng nhầm borrowed stream qua Reader wrapper

Một lỗi tinh vi:

~~~java
public String readFirstLine(InputStream borrowed)
        throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    borrowed, StandardCharsets.UTF_8))) {

        return reader.readLine();
    }
}
~~~

Method trên **đóng borrowed InputStream** khi đóng BufferedReader. Nếu người gọi còn cần stream sau đó, kết quả sẽ là lỗi “stream closed”.

Giải pháp không chỉ là bỏ try-with-resources một cách tùy tiện. Cần **thiết kế lại hợp đồng ownership**:

- Nếu helper được quyền sở hữu stream, đổi tên/tham số tài liệu thành ownership transfer và dùng try-with-resources.
- Nếu chỉ mượn, cần tránh đóng wrapper mà việc close lan xuống stream gốc, hoặc để caller quản lý chính wrapper/Reader khi phù hợp.
- Tốt hơn, ở những API đọc resource ứng dụng, **truyền Resource/Path** cho helper để helper tự mở và đóng stream của riêng nó.

Ví dụ API rõ ownership:

~~~java
public String readFirstLine(Resource resource)
        throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8))) {

        return reader.readLine();
    }
}
~~~

Resource là descriptor được caller truyền vào; method sở hữu stream mà nó vừa mở.

### 11.4. Không return stream đã đóng

Ví dụ sai:

~~~java
public InputStream openData(Resource resource)
        throws IOException {

    try (InputStream in = resource.getInputStream()) {
        return in;
    }
}
~~~

Sau khi return, Java vẫn kết thúc khối try và gọi close(). Caller nhận một stream đã đóng.

Nếu chủ đích API là **chuyển quyền sở hữu stream** cho caller, phải mở rồi trả về **không đóng trong method này**:

~~~java
public InputStream openData(Resource resource)
        throws IOException {
    return resource.getInputStream();
}
~~~

Caller chịu trách nhiệm:

~~~java
try (InputStream in = openData(resource)) {
    // Đọc dữ liệu.
}
~~~

Cách này vẫn có thể khó quản lý nếu nhiều tầng truyền InputStream qua lại; ưu tiên API trả kết quả đã xử lý hoặc nhận Resource và quản lý stream ở phạm vi rõ ràng.

## 12. Bảng quyền sở hữu tài nguyên thường gặp trong Spring Boot

| Tài nguyên/API | Ai thường quản lý close? | Ghi chú |
|---|---|---|
| Resource.getInputStream() | Code gọi mở stream | Dùng try-with-resources trong phạm vi đọc. |
| Files.newBufferedReader(path, charset) | Code gọi mở reader | Đóng BufferedReader. |
| Files.lines(path, charset) | Code tạo Stream dòng | Stream phải được đóng, thường bằng try-with-resources. |
| BufferedReader.lines() | Code sở hữu BufferedReader | Terminal operation không tự đóng reader. |
| MultipartFile.getInputStream() | Code gọi mở stream | Đọc/đóng trước khi request và temporary upload data hết vòng đời. |
| InputStream nhận từ caller | Tùy hợp đồng | Không tự đóng nếu chỉ được mượn. |
| HttpServletResponse.getOutputStream() | Servlet container/framework | Không tự ý đóng trong controller/service thông thường. |
| Resource trả về qua ResponseEntity | Spring MVC message converter | Framework đọc/ghi và xử lý stream theo response lifecycle. |
| JDBC Connection lấy từ DataSource | Code mượn connection | Gọi close() sau thao tác; với pool thường là trả lại pool. |
| DataSource bean do Spring quản lý | ApplicationContext | Không đóng pool sau từng request; đóng khi context hủy. |
| Client có @Bean(destroyMethod="close") | Spring ApplicationContext | Được đóng khi bean bị hủy theo lifecycle. |
| ResourceLoader bean | ApplicationContext | Không đóng sau từng lần getResource(). |

Đây là **quy tắc thông thường**, không thay thế hợp đồng của từng thư viện. Đặc biệt, một wrapper hoặc adapter có thể chuyển giao ownership khác với API mà nó bọc.

## 13. Đọc file người dùng upload bằng MultipartFile

Trong ứng dụng Spring MVC, controller có thể nhận file upload qua **MultipartFile**:

~~~java
package com.example.demo.upload;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ImportController {

    @PostMapping("/imports/count-lines")
    public ResponseEntity<Long> countLines(
            @RequestParam("file") MultipartFile file)
            throws IOException {

        long count = 0;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        file.getInputStream(),
                        StandardCharsets.UTF_8))) {

            while (reader.readLine() != null) {
                count++;
            }
        }

        return ResponseEntity.ok(count);
    }
}
~~~

Trong ví dụ:

- MultipartFile biểu diễn upload được framework xử lý.
- Code mở InputStream qua getInputStream().
- Code tự đóng reader/stream do mình mở.
- Không giữ tham chiếu tới stream để dùng sau khi request đã hoàn tất.

### 13.1. Không tin tưởng charset hoặc filename từ phía client

Upload có thể chứa:

- File không phải UTF-8.
- File binary giả dạng CSV.
- Nội dung vượt giới hạn dung lượng.
- Filename có path hoặc ký tự không an toàn.
- Dữ liệu sai định dạng hoặc chứa payload độc hại khi được mở bằng phần mềm khác.

Controller trên là minh họa xử lý file UTF-8 theo **hợp đồng API**. Ứng dụng production cần:

1. Giới hạn kích thước upload.
2. Xác thực media type, định dạng và cấu trúc dữ liệu.
3. Kiểm soát charset được hỗ trợ.
4. Không dùng trực tiếp originalFilename làm đường dẫn ghi file.
5. Hạn chế các giá trị kích thước hoặc số dòng quá lớn.
6. Xử lý lỗi bằng phản hồi API phù hợp, không tiết lộ đường dẫn hệ thống.

### 13.2. MultipartFile.getBytes() khác getInputStream()

~~~java
byte[] content = file.getBytes();
~~~

getBytes() đưa toàn bộ nội dung vào byte array; thuận tiện cho file nhỏ nhưng có thể tốn bộ nhớ với upload lớn.

~~~java
try (InputStream in = file.getInputStream()) {
    // Đọc tuần tự.
}
~~~

getInputStream() cho phép xử lý theo luồng. Dù vậy, việc upload có sử dụng RAM hay file tạm trong quá trình tiếp nhận còn phụ thuộc cấu hình multipart resolver/container, không chỉ vào cách đọc trong controller.

### 13.3. Không đưa stream upload vào công việc nền mà không quản lý lifecycle

Ví dụ sai về vòng đời:

~~~java
public void scheduleImport(MultipartFile file) {
    executor.execute(() -> {
        try (InputStream in = file.getInputStream()) {
            // Xử lý sau khi request đã kết thúc.
        } catch (IOException ex) {
            // ...
        }
    });
}
~~~

File tạm backing MultipartFile có thể bị framework/container dọn sau request. Tác vụ nền không nên giả định nó vẫn tồn tại.

Nếu cần xử lý async, hãy chủ động **lưu upload vào vùng lưu trữ do ứng dụng quản lý** theo chính sách bảo mật, rồi truyền identifier hoặc Path hợp lệ cho worker nền. Worker tự mở và đóng tài nguyên khi xử lý.

## 14. Trả file download bằng ResponseEntity<Resource>

Một controller có thể trả một Resource để Spring MVC tự đọc vào response:

~~~java
package com.example.demo.download;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TemplateDownloadController {

    @GetMapping("/downloads/import-template")
    public ResponseEntity<Resource> download() {
        Resource source =
                new ClassPathResource("templates/import.csv");

        return ResponseEntity.ok()
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"import.csv\"")
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .body(source);
    }
}
~~~

Trong trường hợp này:

- Controller không tự mở InputStream.
- Controller trả Resource descriptor.
- Spring MVC/message converter mở và đọc dữ liệu trong giai đoạn ghi HTTP response.
- Vòng đời stream khi ghi response do framework quản lý theo converter tương ứng.

Đây là một ví dụ **chuyển giao trách nhiệm đọc** cho framework; không mở stream trong try-with-resources rồi đóng trước khi response được gửi.

### 14.1. Không trả về InputStreamResource dùng chung như singleton

Ví dụ có rủi ro:

~~~java
@Bean
Resource exportResource() throws IOException {
    return new InputStreamResource(
            new FileInputStream("/tmp/export.csv"));
}
~~~

**InputStreamResource** bọc một InputStream đã mở, thường chỉ có thể tiêu thụ một lần. Nếu bean singleton được dùng cho nhiều request download:

- Request đầu có thể đọc hết stream.
- Request sau có thể nhận EOF hoặc stream đã đóng.
- Stream có thể bị mở quá sớm trong vòng đời ApplicationContext.
- Một số thao tác lấy metadata như content length có thể làm tiêu thụ stream ở implementation không hỗ trợ đọc lại.

Với file có trên filesystem, nên dùng FileSystemResource/PathResource có thể mở stream mới cho mỗi request. Với dữ liệu nhỏ trong RAM, ByteArrayResource có thể phù hợp vì có thể tạo stream mới từ byte array. Với file đóng gói, dùng ClassPathResource.

### 14.2. InputStreamResource là single-use

Ví dụ:

~~~java
InputStream in = resource.getInputStream();
InputStreamResource oneShot = new InputStreamResource(in);
~~~

oneShot thường biểu diễn chính stream vừa mở, không phải một file có thể đọc lại nhiều lần. Không nên để nó sống lâu hơn stream gốc, không dùng lại sau khi đã được response converter tiêu thụ và không giả định metadata access luôn an toàn.

Trong những trường hợp framework hỗ trợ streaming một lần, InputStreamResource vẫn có thể hữu ích, nhưng cần hiểu rõ contract **single-use** và ai chịu trách nhiệm cuối cùng về close.

## 15. StreamingResponseBody và servlet output stream

Khi download được tạo động hoặc dữ liệu lớn, Spring MVC cung cấp **StreamingResponseBody**. Nó cho phép ghi dữ liệu theo luồng mà không buộc phải xây toàn bộ byte[] trong RAM.

Ví dụ copy một file classpath tới response:

~~~java
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class ExportController {

    @GetMapping("/exports/data")
    public ResponseEntity<StreamingResponseBody> export() {
        Resource resource =
                new ClassPathResource("data/export.csv");

        StreamingResponseBody body = output -> {
            try (InputStream in = resource.getInputStream()) {
                in.transferTo(output);
            }
            output.flush();
        };

        return ResponseEntity.ok()
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"export.csv\"")
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .body(body);
    }
}
~~~

Phân tích ownership:

- **InputStream in** được mở bên trong callback: ứng dụng phải đóng, đã dùng try-with-resources.
- **OutputStream output** do Spring MVC/servlet container truyền vào: code ghi và flush khi cần, **không tự ý close()** vì vòng đời HTTP response do framework/container điều phối.
- **Resource resource** là descriptor, được capture để callback mở stream khi thật sự bắt đầu ghi.

Trong ứng dụng thật, cần kiểm tra cấu hình executor cho MVC async processing, giới hạn concurrency, timeout và chính sách xử lý client ngắt kết nối. Truyền khối lượng lớn data qua streaming không miễn trừ việc quản lý số worker và tài nguyên phía server.

### 15.1. Vì sao không bọc servlet output bằng try-with-resources?

Ví dụ cần tránh trong controller/service thông thường:

~~~java
try (OutputStream out = response.getOutputStream()) {
    // ...
}
~~~

Container quản lý stream và vòng đời response. Đóng stream ở tầng ứng dụng có thể làm kết thúc response sớm, khiến các filter/handler khác không còn cơ hội xử lý phù hợp hoặc tạo hành vi phụ thuộc container.

Không phải mọi lần gọi close() đều chắc chắn gây lỗi; quy tắc là **để đúng owner quyết định đóng**.

## 16. Files.lines và Java Stream cũng cần close

API Java Stream thường gợi cảm giác chỉ là một pipeline xử lý collection. Nhưng một số Stream đến từ file I/O có **tài nguyên hệ thống bên dưới**.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public long countLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

**Files.lines()** mở tài nguyên để đọc file. Terminal operation như count(), toList() hoặc forEach() **không tự động thay thế Stream.close()** đối với các tài nguyên I/O đó.

### 16.1. Trường hợp sai

~~~java
Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8);
long count = lines.count();
// Không close stream.
~~~

Nếu chạy lặp lại trên nhiều file, điều này có thể khiến file handles không được giải phóng kịp thời.

### 16.2. BufferedReader.lines() cũng cần ownership rõ

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(
                     path, StandardCharsets.UTF_8)) {

    long count = reader.lines().count();
    return count;
}
~~~

Trong ví dụ, try-with-resources đóng **reader**, là tài nguyên sở hữu nguồn file. Terminal operation của stream không tự đóng reader.

### 16.3. Files.walk và Files.find

Một số API duyệt filesystem trả về Stream có tài nguyên I/O nội bộ:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

Hãy đọc hợp đồng của API trả Stream. Một Stream tạo từ collection thuần không mang nghĩa vụ đóng file handle; một Stream gắn với I/O thì có thể cần đóng.

## 17. Đừng tạo stream “sống lâu” hơn phạm vi tài nguyên

Ví dụ sai:

~~~java
public Stream<String> readLines(Path path)
        throws IOException {

    try (BufferedReader reader =
                 Files.newBufferedReader(
                         path, StandardCharsets.UTF_8)) {
        return reader.lines();
    }
}
~~~

Method trả về một **lazy Stream** dựa trên reader đã bị đóng khi kết thúc try. Khi caller gọi count(), forEach() hoặc toList(), việc đọc file có thể thất bại.

Một thiết kế tốt hơn:

**Phương án A — Đọc/xử lý hoàn toàn trong method**:

~~~java
public long countLines(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(
                         path, StandardCharsets.UTF_8)) {
        return reader.lines().count();
    }
}
~~~

**Phương án B — Trả về Stream mà caller sở hữu**:

~~~java
public Stream<String> openLines(Path path)
        throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}
~~~

Caller phải đóng:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.forEach(System.out::println);
}
~~~

Phương án B cần tài liệu API rõ ràng vì caller có thể quên close. Với API nghiệp vụ, phương án A hoặc callback xử lý trong phạm vi stream thường giảm nguy cơ leak.

## 18. Xử lý bất đồng bộ: đừng đóng stream trước khi worker đọc

Giả sử một tác vụ cần chạy nền:

~~~java
public CompletableFuture<Long> countAsync(Resource resource) {
    // ...
}
~~~

Một lỗi thường gặp là mở stream trong thread gọi, lên lịch công việc nền rồi đóng stream ngay:

~~~java
public CompletableFuture<Long> broken(Resource resource)
        throws IOException {

    try (InputStream in = resource.getInputStream()) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return (long) in.readAllBytes().length;
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
    }
}
~~~

Thread gọi có thể thoát khỏi try và đóng stream **trước khi** worker nền bắt đầu đọc. Kết quả là lỗi stream closed hoặc dữ liệu thiếu.

### 18.1. Mở và đóng trong chính worker

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.core.io.Resource;

public CompletableFuture<Long> countAsync(
        Resource resource, Executor ioExecutor) {

    return CompletableFuture.supplyAsync(() -> {
        try (InputStream in = resource.getInputStream()) {
            long total = 0;
            byte[] buffer = new byte[8192];
            int n;

            while ((n = in.read(buffer)) != -1) {
                total += n;
            }
            return total;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }, ioExecutor);
}
~~~

Ở đây worker mở stream khi bắt đầu xử lý và đóng ngay sau khi hoàn tất. Resource descriptor có thể được truyền sang worker nếu resource vẫn tồn tại và hỗ trợ mở stream mới.

Không dùng pattern này nguyên xi với InputStreamResource đã bọc một stream single-use hoặc MultipartFile mà dữ liệu tạm có thể bị dọn sau request. Hãy bảo đảm nguồn còn hiệu lực trong suốt thời gian worker đọc.

### 18.2. Chọn executor cho blocking I/O

Đọc file bằng InputStream thông thường là **blocking I/O**. Khi chạy bất đồng bộ, cần kiểm soát số task/connections để không tạo quá nhiều luồng hoặc làm cạn file handles.

Nếu ứng dụng dùng Spring WebFlux/reactive stack, không nên đưa blocking file I/O trực tiếp lên event loop. Hãy dùng API/reactive resource handling thích hợp hoặc chuyển việc chặn sang scheduler/executor được quản lý.

## 19. Resource bean và vòng đời ApplicationContext

Spring Boot quản lý vòng đời của những bean trong ApplicationContext. Nhưng **không phải mọi tài nguyên dùng trong ứng dụng đều tự động do Spring đóng**.

Phân biệt ba trường hợp:

| Trường hợp | Ai chịu trách nhiệm |
|---|---|
| Bean được Spring tạo và có lifecycle/destroy callback được cấu hình | Spring hủy bean khi context đóng. |
| InputStream được service mở từ Resource trong mỗi lần gọi | Service tự đóng stream sau khi dùng. |
| Stream hoặc client tạo bằng new ở ngoài sự quản lý của Spring | Code sở hữu phải tự tổ chức vòng đời. |

Ví dụ:

~~~java
@Component
public class ConfigReader {

    private final Resource resource =
            new ClassPathResource("data/config.txt");

    public String read() throws IOException {
        try (InputStream in = resource.getInputStream()) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

**ConfigReader** là Spring bean, Resource là descriptor được giữ trong bean. Nhưng mỗi lần read() mở một InputStream mới, method vẫn phải đóng nó; việc Spring quản lý bean ConfigReader **không tự đóng các InputStream phát sinh ở từng lần gọi**.

### 19.1. Không nên giữ một InputStream dùng chung trong singleton bean

Ví dụ có rủi ro:

~~~java
@Component
public class BrokenConfigReader {

    private final InputStream stream;

    public BrokenConfigReader() throws IOException {
        this.stream = new ClassPathResource(
                "data/config.txt").getInputStream();
    }

    public String readAgain() throws IOException {
        return new String(
                stream.readAllBytes(),
                StandardCharsets.UTF_8);
    }
}
~~~

Vấn đề:

- Stream được mở sớm khi singleton bean khởi tạo.
- Lần đọc đầu tiên có thể tiêu thụ hết nội dung; lần sau gặp EOF.
- Nếu nhiều request dùng chung, chúng cạnh tranh trên cùng vị trí đọc của stream.
- Nếu không có callback hủy phù hợp, stream có thể bị giữ quá lâu.
- Nếu chỉ cần đọc một lần, việc giữ stream sau khi đọc là dư thừa.

Thiết kế tốt hơn: singleton giữ **Resource descriptor** hoặc dữ liệu đã nạp hợp lý, không giữ một stream mở lâu dài trừ khi có lý do và lifecycle rất rõ ràng.

### 19.2. Bean có tài nguyên dài hạn dùng destroy callback

Một số đối tượng cần sống cùng ApplicationContext, ví dụ client có connection pool, worker executor hoặc watcher.

Ví dụ một lớp tự quản lý executor:

~~~java
package com.example.demo.lifecycle;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ManagedReportWorker implements AutoCloseable {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @Override
    public void close() {
        executor.shutdown();
    }
}
~~~

Đăng ký dưới dạng Spring bean với destroy callback:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {

    @Bean(destroyMethod = "close")
    ManagedReportWorker reportWorker() {
        return new ManagedReportWorker();
    }
}
~~~

Khi ApplicationContext hủy bean, Spring gọi close() theo lifecycle đã cấu hình. Việc executor.shutdown() không tự bảo đảm mọi task đã hoàn tất; nếu cần graceful shutdown chờ công việc, ManagedReportWorker phải có thêm chính sách await termination, timeout và xử lý task còn dang dở.

Spring có cơ chế suy luận destroy method như close/shutdown cho nhiều bean @Bean trong các tình huống phù hợp, nhưng khai báo tường minh như trên làm ownership rõ hơn.

### 19.3. @PreDestroy cho tài nguyên thuộc component

Với một component tự mở tài nguyên dài hạn, có thể dùng callback:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class LongRunningClientHolder {

    private final ManagedClient client = new ManagedClient();

    @PreDestroy
    public void shutdown() {
        client.close();
    }
}
~~~

ManagedClient là một kiểu minh họa có phương thức close(). Ví dụ chỉ diễn giải lifecycle: khi Spring quản lý bean và context được đóng bình thường, callback có thể được gọi để giải phóng tài nguyên.

Nếu JVM crash hoặc bị kill cưỡng bức, không có bảo đảm @PreDestroy sẽ chạy. Các hệ thống production vẫn cần cơ chế giới hạn tài nguyên, timeout và phục hồi.

### 19.4. Không đóng bean dùng chung sau từng request

Nếu Spring quản lý DataSource, HTTP client hoặc managed executor dùng chung, một request không nên:

~~~java
sharedClient.close();
~~~

sau mỗi thao tác, trừ khi hợp đồng của client đó quy định đây là một **session/handle riêng** do request sở hữu.

Phải phân biệt **client/pool** sống cùng application với **connection/stream/response handle** được mở cho từng lần sử dụng.

## 20. Ví dụ so sánh JDBC Connection và DataSource

JDBC minh họa rất rõ nguyên tắc ownership trong Spring Boot.

**DataSource** thường là bean được framework hoặc ứng dụng cấu hình, có thể là connection pool dùng chung. Nhưng khi code gọi getConnection(), nó nhận một Connection cần được đóng sau khi thực hiện SQL.

Ví dụ:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class ProductRepository {

    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int countProducts() throws SQLException {
        String sql = "select count(*) from products";

        try (Connection connection =
                     dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql);
             ResultSet result = statement.executeQuery()) {

            result.next();
            return result.getInt(1);
        }
    }
}
~~~

Ở đây:

- **DataSource**: dependency dùng chung; không đóng trong method.
- **Connection**: handle được method lấy ra, cần close() sau khi dùng; với pooled DataSource, close thường trả kết nối về pool.
- **PreparedStatement** và **ResultSet**: tài nguyên JDBC phát sinh trong thao tác, được đóng qua try-with-resources.

Trong ứng dụng có Spring transaction management, cách lấy và quản lý connection có thể do JdbcTemplate hoặc framework thực hiện. Nếu dùng JdbcTemplate, thường không cần tự mở/đóng Connection. Hãy theo hợp đồng của API và transaction manager đang dùng, tránh trộn nhiều cách quản lý connection.

**Bài học chung:** framework quản lý bean không có nghĩa mọi handle mượn từ bean đó đều không cần close.

## 21. InputStreamResource, ByteArrayResource và FileSystemResource

Chọn đúng loại Resource giúp tránh lỗi về vòng đời và khả năng đọc lại.

### 21.1. ByteArrayResource: đọc lại được, nhưng giữ byte[] trong RAM

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

byte[] bytes =
        "Xin chào\n".getBytes(StandardCharsets.UTF_8);

Resource resource = new ByteArrayResource(bytes);
~~~

Thông thường mỗi lần getInputStream() trên ByteArrayResource cung cấp một stream mới đọc từ byte array có sẵn.

Ưu điểm:

- Dễ dùng với test nhỏ.
- Có thể đọc lại nhiều lần.
- Không phụ thuộc file filesystem còn tồn tại.

Nhược điểm:

- Toàn bộ dữ liệu đã nằm trong RAM.
- Nếu tạo Resource từ dữ liệu rất lớn, tiêu thụ bộ nhớ đáng kể.
- Không phù hợp để biến mọi upload/download lớn thành byte[].

### 21.2. InputStreamResource: gắn với stream đã mở

~~~java
InputStream in = fileResource.getInputStream();
Resource oneShot = new InputStreamResource(in);
~~~

Ưu điểm là có thể chuyển tiếp một InputStream hiện có tới API nhận Resource. Nhưng cần lưu ý:

- Thường chỉ được đọc một lần.
- Không giả định có thể mở lại sau khi EOF.
- Không giữ stream lâu hơn nguồn backing còn hiệu lực.
- Cẩn thận khi framework cần tính content length hoặc đọc metadata trước lúc thực sự consume.
- Phải xác định rõ bên nào tiếp quản trách nhiệm đóng.

Không dùng InputStreamResource như một singleton “file dùng mãi” nếu nguồn chỉ là một InputStream duy nhất.

### 21.3. FileSystemResource: mở file theo từng lần đọc

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Path path = Path.of("/opt/app/data/catalog.csv");
Resource resource = new FileSystemResource(path);
~~~

Với file còn tồn tại, Resource có thể mở stream mới khi đọc. Đây là mẫu phù hợp nếu dữ liệu nằm trên filesystem và cần được đọc theo nhiều request/lần chạy.

Không đồng nghĩa file sẽ mãi tồn tại: file có thể bị xóa, đổi quyền hoặc thay đổi trong khi đọc. Code vẫn phải xử lý IOException và nhất quán dữ liệu theo nghiệp vụ.

### 21.4. ClassPathResource: phù hợp với file đi kèm ứng dụng

~~~java
Resource resource =
        new ClassPathResource("templates/invoice.txt");
~~~

Đây là cách phù hợp với dữ liệu tham khảo, template hoặc static content đóng gói cùng artifact. Nếu tài liệu cần sửa mà không build lại, một file bên ngoài hoặc storage có cơ chế cập nhật sẽ phù hợp hơn.

## 22. Charset ở biên HTTP và khi xuất CSV

Trong HTTP, dữ liệu có thể là JSON, text/plain, CSV hoặc binary. **Content-Type** giúp mô tả media type và có thể bao gồm thông tin charset cho những định dạng văn bản cần nó.

Ví dụ response CSV:

~~~java
return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(
                "text/csv;charset=UTF-8"))
        .body(resource);
~~~

Header này báo cho client rằng response CSV là văn bản UTF-8. Nhưng header không tự sửa những byte đã được mã hóa sai. Nếu bạn ghi String qua OutputStreamWriter với charset khác, hoặc file nguồn thật là encoding khác, dữ liệu vẫn có thể lỗi.

### 22.1. Chọn một hợp đồng encoding ở hai đầu

Với một hệ thống xuất dữ liệu CSV, hãy xác định:

1. Nguồn String trong Java được chuyển thành byte bằng encoding nào?
2. Content-Type/charset của HTTP response nói điều gì?
3. Client nhận file kỳ vọng charset nào?
4. File có cần BOM theo yêu cầu tương thích của một consumer cụ thể không?
5. Có cần xử lý escaping/quoting của CSV đúng chuẩn không?

Nếu hệ thống đích yêu cầu UTF-8 có BOM, có thể thêm BOM theo hợp đồng đó. Nhưng không nên mặc định mọi CSV UTF-8 phải có BOM; nhiều consumer không cần và một số parser sẽ coi nó là ký tự đầu header.

### 22.2. Dùng framework converter cho JSON khi phù hợp

Trong Spring MVC, trả một object từ @RestController thường để Jackson và message converter chịu trách nhiệm serialize JSON. Không cần tự tạo String rồi getBytes() cho mọi response.

Ví dụ:

~~~java
@RestController
public class GreetingController {

    @GetMapping("/greeting")
    public Map<String, String> greeting() {
        return Map.of("message", "Xin chào");
    }
}
~~~

Spring MVC dùng HTTP message converters phù hợp để ghi response. Đừng tự mở và đóng servlet output stream khi không cần thiết; để framework đảm nhận việc encode và vòng đời response.

Nếu sử dụng WebFlux, có thêm các quy tắc của reactive HTTP body/data buffers. Không nên tự trộn logic blocking InputStream với pipeline reactive mà không quản lý scheduler và cleanup.

## 23. Không gom toàn bộ dữ liệu vào bộ nhớ nếu không cần

Một số API rất thuận tiện nhưng có đặc tính khác nhau:

| Cách đọc | Đặc tính |
|---|---|
| Files.readString(path, UTF_8) | Đọc toàn bộ text thành String. |
| Files.readAllBytes(path) | Đọc toàn bộ binary thành byte[]. |
| InputStream.readAllBytes() | Đọc toàn bộ phần còn lại của stream. Không tự close. |
| BufferedReader.readLine() | Đọc lần lượt từng dòng, có thể xử lý streaming. |
| Files.lines(path, UTF_8) | Trả lazy Stream dòng, cần close. |
| InputStream.transferTo(output) | Copy tuần tự, không có nghĩa tự close hai stream. |

Ví dụ copy một resource lớn vào file đích:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.Resource;

public void copyResource(Resource source, Path destination)
        throws IOException {

    try (InputStream in = source.getInputStream();
         OutputStream out = Files.newOutputStream(destination)) {

        in.transferTo(out);
    }
}
~~~

Đoạn này copy byte nguyên bản: **không có charset conversion**. Đúng cho file binary hoặc thao tác copy mà bạn không muốn biến đổi encoding.

### 23.1. transferTo không tự đóng stream

**InputStream.transferTo(OutputStream)** chuyển byte từ nguồn sang đích đến khi EOF, nhưng không thay thế trách nhiệm đóng nguồn và đích. Trong ví dụ, cả hai stream do method mở nên đều được đóng bằng try-with-resources.

Nếu đích là output stream của servlet container, method không được tự đóng đích như trong ví dụ copy file; cần tuân theo ownership của response.

### 23.2. Ghi file cần cân nhắc partial output

Nếu copy vào đích cuối và thất bại giữa chừng, file đích có thể chỉ chứa một phần dữ liệu. Với dữ liệu quan trọng, có thể:

1. Ghi vào một file tạm trong cùng vùng filesystem thích hợp.
2. Đóng/flush hoàn tất stream và xác nhận kết quả.
3. Chuyển file tạm sang đường dẫn chính bằng move phù hợp với mức bảo đảm atomicity của filesystem.
4. Dọn file tạm nếu thao tác thất bại.

Chính sách này là yêu cầu về consistency của file, **khác với việc đóng stream**. Đóng stream chỉ giải phóng tài nguyên và hoàn tất các buffer tương ứng; nó không tự biến một thao tác ghi dang dở thành giao dịch.

### 23.3. Giới hạn dữ liệu khi nguồn không tin cậy

Streaming giảm nguy cơ đọc toàn bộ file vào RAM, nhưng chưa giải quyết mọi nguy cơ. Một nguồn rất lớn hoặc không bao giờ kết thúc vẫn có thể giữ worker và disk lâu.

Với upload hoặc network resource, cần thêm:

- Giới hạn dung lượng tối đa.
- Timeout hợp lý.
- Giới hạn concurrency.
- Kiểm tra định dạng.
- Bảo vệ đường dẫn ghi file.
- Hủy tác vụ khi client ngắt kết nối hoặc vượt giới hạn.

Đừng coi “dùng InputStream” đồng nghĩa “an toàn với mọi kích thước file”.

## 24. Kiểm thử charset và closing bằng unit test

Nội dung liên quan encoding và ownership rất phù hợp để kiểm thử bằng byte dữ liệu được kiểm soát. Test không cần khởi động toàn bộ Spring Boot web application.

### 24.1. Tạo một reader làm đơn vị kiểm thử

~~~java
package com.example.demo.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public class Utf8ResourceReader {

    public String readAll(Resource resource) throws IOException {
        try (InputStream in = resource.getInputStream()) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Với file nhỏ, cách này phù hợp cho test. Nếu production cần đọc một file rất lớn, nên thay bằng Reader/buffered streaming.

### 24.2. Xác nhận UTF-8 không làm lỗi dấu

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

class Utf8ResourceReaderTests {

    private final Utf8ResourceReader reader =
            new Utf8ResourceReader();

    @Test
    void preservesVietnameseCharacters() throws Exception {
        String expected = "Cà phê, Hà Nội, Đà Nẵng";
        Resource resource = new ByteArrayResource(
                expected.getBytes(StandardCharsets.UTF_8));

        assertThat(reader.readAll(resource))
                .isEqualTo(expected);
    }
}
~~~

Test này chứng minh reader đã giải mã đúng bộ byte UTF-8 được cung cấp. Nó không kiểm tra BOM, file filesystem hay API upload; mỗi trường hợp cần test riêng theo hợp đồng.

### 24.3. Xác nhận stream do method mở đã được đóng

Có thể tạo InputStream theo dõi close():

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;

final class CloseTrackingInputStream
        extends ByteArrayInputStream {

    private boolean closed;

    CloseTrackingInputStream(byte[] data) {
        super(data);
    }

    @Override
    public void close() throws IOException {
        closed = true;
        super.close();
    }

    boolean wasClosed() {
        return closed;
    }
}
~~~

Test:

~~~java
@Test
void closesResourceStreamAfterReading() throws Exception {
    byte[] bytes = "Hà Nội".getBytes(StandardCharsets.UTF_8);
    CloseTrackingInputStream in =
            new CloseTrackingInputStream(bytes);

    Resource resource = new InputStreamResource(in);

    assertThat(reader.readAll(resource))
            .isEqualTo("Hà Nội");
    assertThat(in.wasClosed()).isTrue();
}
~~~

Ở đây InputStreamResource là one-shot nhưng test chỉ đọc đúng một lần. Mục tiêu là xác nhận **Utf8ResourceReader** đã đóng stream do Resource cung cấp.

### 24.4. Kiểm thử file filesystem bằng @TempDir

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.FileSystemResource;

class FileResourceTests {

    @TempDir
    Path tempDir;

    @Test
    void readsUtf8FileThroughSpringResource()
            throws Exception {

        Path path = tempDir.resolve("sample.txt");
        Files.writeString(path, "Tiếng Việt",
                StandardCharsets.UTF_8);

        Utf8ResourceReader reader =
                new Utf8ResourceReader();

        assertThat(reader.readAll(
                new FileSystemResource(path)))
                .isEqualTo("Tiếng Việt");
    }
}
~~~

@TempDir giúp test không phụ thuộc thư mục làm việc cố định và dễ dọn file sau test.

### 24.5. Kiểm thử khi Resource không tồn tại

~~~java
@Test
void missingResourceReportsIOException() {
    Resource missing = new ClassPathResource(
            "data/does-not-exist.txt");

    assertThatThrownBy(() -> reader.readAll(missing))
            .isInstanceOf(IOException.class);
}
~~~

Ví dụ cần static import assertThatThrownBy từ AssertJ, cùng các import của Resource, ClassPathResource và IOException.

Nếu ứng dụng có fallback khi file không tồn tại, test nên xác minh hành vi fallback **theo yêu cầu nghiệp vụ** chứ không đơn giản nuốt mọi IOException.

## 25. Cách chẩn đoán lỗi charset và rò rỉ tài nguyên

Khi xử lý một file bị lỗi hoặc một service chậm dần, hãy phân biệt hai nhóm nguyên nhân.

### 25.1. Nhóm lỗi charset

Triệu chứng:

- Chữ tiếng Việt bị biến thành chuỗi ký tự lạ.
- Ký tự U+FFFD xuất hiện trong dữ liệu.
- Header CSV không khớp tên cột do BOM.
- JSON/XML parser báo dữ liệu văn bản không hợp lệ.
- Kết quả trên máy developer khác server/container.

Hướng kiểm tra:

1. Nguồn file được tạo bằng charset nào?
2. Code dùng InputStreamReader/FIles.readString với charset nào?
3. Có encoding conversion ở một tầng trung gian không?
4. Có BOM hoặc newline convention đặc biệt không?
5. HTTP Content-Type có mô tả đúng dữ liệu thực không?
6. Có framework parser nào đã xử lý encoding sẵn và code lại giải mã lần hai không?

Không nên sửa bằng cách đổi bừa charset cho tới khi “trông đúng”. Xác định **byte nguồn** và quy tắc decode là điều cơ bản nhất.

### 25.2. Nhóm lỗi vòng đời stream

Triệu chứng:

- **Too many open files** hoặc cạn file descriptor.
- File không xóa/rename được trong một số môi trường do handle còn mở.
- Kết nối tới nguồn dữ liệu bị giữ lâu hơn cần thiết.
- **Stream closed** trong tác vụ async.
- Download request đầu thành công, request sau không còn dữ liệu.
- Bộ nhớ tăng vì giữ nhiều byte arrays hoặc resources lâu dài.

Hướng kiểm tra:

1. Code gọi getInputStream(), Files.lines() hoặc Files.newBufferedReader ở đâu?
2. Có try-with-resources bao quanh phạm vi sử dụng không?
3. Có lazy Stream/Reader trả về khỏi scope đã đóng không?
4. InputStreamResource có bị tái sử dụng không?
5. Có InputStream được giữ trong singleton bean không?
6. Có đóng nhầm servlet output stream hoặc shared client không?
7. Có task nền dùng nguồn tạm sau khi request kết thúc không?
8. Có giới hạn concurrency và timeout với nguồn I/O không?

Không phải mọi vấn đề bộ nhớ hay file handle đều do thiếu close; cũng có thể do task bị block dài, resource single-use hoặc giữ byte[] không cần thiết. Quan sát thread dump, metrics và logs giúp khoanh vùng nguyên nhân.

## 26. Các lỗi thường gặp và cách xử lý

### 26.1. Đọc tiếng Việt bằng charset mặc định

**Dấu hiệu:** văn bản đúng trên một máy nhưng bị lỗi dấu khi chạy ở máy khác.

**Nguyên nhân:** code dùng new InputStreamReader(in), new String(bytes) hoặc getBytes() mà không chỉ định charset.

**Cách xử lý:** xác nhận encoding của dữ liệu nguồn, dùng StandardCharsets.UTF_8 hoặc charset thực tế được quy định trong hợp đồng dữ liệu.

### 26.2. Tạo File từ classpath resource

**Dấu hiệu:** chạy trong IDE được, chạy executable JAR thì báo không tìm thấy file.

**Nguyên nhân:** code dùng đường dẫn src/main/resources/... hoặc ClassPathResource.getFile(), giả định resource luôn là một file filesystem.

**Cách xử lý:** dùng ClassPathResource.getInputStream() hoặc ResourceLoader để đọc classpath content. Chỉ dùng File/Path khi nguồn thực sự nằm trên filesystem.

### 26.3. Quên đóng getInputStream()

**Dấu hiệu:** nhiều lần đọc file hoặc tải resource khiến file handles và connections tăng.

**Nguyên nhân:** stream được mở nhưng không nằm trong try-with-resources hoặc không được đóng trên mọi nhánh exception.

**Cách xử lý:** mở và đóng stream trong cùng method hoặc chuyển ownership rõ ràng cho caller/framework.

### 26.4. Nghĩ readAllBytes() tự đóng stream

**Dấu hiệu:** code ngắn nhưng leak stream sau khi đã có byte[].

**Nguyên nhân:** nhầm việc đọc đến EOF với close().

**Cách xử lý:**

~~~java
try (InputStream in = resource.getInputStream()) {
    return in.readAllBytes();
}
~~~

Với file lớn, tránh đọc hết vào RAM; dùng buffer hoặc streaming.

### 26.5. Đóng stream trước khi trả về

**Dấu hiệu:** caller nhận InputStream nhưng lần đọc đầu tiên báo stream closed.

**Nguyên nhân:** return stream từ bên trong try-with-resources.

**Cách xử lý:** hoặc trả kết quả đã xử lý, hoặc trả stream còn mở và ghi rõ caller phải close.

### 26.6. Đóng borrowed InputStream qua BufferedReader

**Dấu hiệu:** code gọi helper đọc một dòng rồi không thể dùng tiếp stream.

**Nguyên nhân:** helper bọc stream bằng reader và đóng reader, kéo theo đóng stream của caller.

**Cách xử lý:** thống nhất API có take ownership không; ưu tiên truyền Resource/Path để helper tự mở và đóng.

### 26.7. Dùng InputStreamResource cho nhiều response

**Dấu hiệu:** lần tải đầu thành công, lần hai trả file rỗng hoặc exception.

**Nguyên nhân:** tái sử dụng một stream single-use.

**Cách xử lý:** dùng ClassPathResource, FileSystemResource hoặc ByteArrayResource phù hợp để mỗi request có nguồn đọc hợp lệ.

### 26.8. Đóng servlet response output

**Dấu hiệu:** response bị kết thúc sớm hoặc framework gặp lỗi khi xử lý response body/filter.

**Nguyên nhân:** controller/service tự đóng stream thuộc container.

**Cách xử lý:** khi framework đưa OutputStream cho StreamingResponseBody, code chỉ ghi/flush khi cần và để framework quản lý close.

### 26.9. Đọc MultipartFile trong background thread quá muộn

**Dấu hiệu:** worker nền không tìm thấy file upload tạm hoặc stream đã mất hiệu lực.

**Nguyên nhân:** dữ liệu upload thuộc request lifecycle và có thể được dọn sau request.

**Cách xử lý:** sao chép upload vào nguồn lưu trữ do ứng dụng sở hữu trước khi lên lịch xử lý async; worker mở và đóng stream của nguồn mới.

### 26.10. Quên đóng Files.lines()

**Dấu hiệu:** chương trình duyệt nhiều file rồi gặp lỗi tài nguyên hệ thống.

**Nguyên nhân:** nghĩ Stream terminal operation như count() đã giải phóng file.

**Cách xử lý:** bao Files.lines(), Files.walk() và các I/O-backed streams trong try-with-resources.

### 26.11. Trả lazy Stream từ Reader đã đóng

**Dấu hiệu:** method trả Stream thành công nhưng caller không thể iterate.

**Nguyên nhân:** reader được đóng khi method return, còn stream chỉ đọc dữ liệu lúc terminal operation thực thi sau đó.

**Cách xử lý:** thực hiện terminal operation trong scope reader, hoặc trả Stream với quyền sở hữu/close rõ ràng.

### 26.12. Giữ một InputStream trong singleton bean

**Dấu hiệu:** lần sử dụng đầu đọc được dữ liệu, lần tiếp theo EOF hoặc các request cạnh tranh vị trí đọc.

**Nguyên nhân:** một InputStream có trạng thái được dùng chung cho nhiều request.

**Cách xử lý:** giữ Resource descriptor; mở stream mới cho từng lần đọc. Nếu cần cache dữ liệu nhỏ, đọc một lần rồi lưu đối tượng dữ liệu phù hợp thay vì giữ stream.

### 26.13. Quên đóng JDBC Connection lấy từ pool

**Dấu hiệu:** pool cạn và request chờ connection dù database vẫn hoạt động.

**Nguyên nhân:** code getConnection() nhưng không close hoặc tự quản lý JDBC không đúng transaction contract.

**Cách xử lý:** dùng JdbcTemplate/Spring JDBC khi phù hợp, hoặc try-with-resources cho connection/statement/resultset thuộc phạm vi method.

### 26.14. Đóng DataSource sau mỗi truy vấn

**Dấu hiệu:** truy vấn tiếp theo thất bại vì pool đã bị shutdown.

**Nguyên nhân:** nhầm Connection per-operation với DataSource singleton.

**Cách xử lý:** close connection mượn; để ApplicationContext quản lý pool bean.

### 26.15. Dùng stream cho file lớn nhưng không giới hạn tác vụ

**Dấu hiệu:** tuy không hết heap do readAllBytes, ứng dụng vẫn bị treo vì quá nhiều I/O tasks hoặc nguồn cực lớn.

**Nguyên nhân:** bỏ qua timeout, data limit và concurrency controls.

**Cách xử lý:** bổ sung quota, timeout, queue, executor size và xử lý cancel phù hợp.

### 26.16. Có BOM trong file CSV khiến sai header

**Dấu hiệu:** header nhìn như **id** nhưng map không tìm được cột id.

**Nguyên nhân:** U+FEFF xuất hiện ở đầu dòng đầu hoặc parser xử lý BOM khác kỳ vọng.

**Cách xử lý:** xác nhận byte nguồn, chọn parser hỗ trợ BOM hoặc bỏ BOM theo hợp đồng định dạng.

### 26.17. Bỏ qua IOException khiến dữ liệu im lặng bị thiếu

**Dấu hiệu:** kết quả trả về empty list dù thực tế file đọc bị lỗi.

**Nguyên nhân:** catch IOException rồi trả mặc định không phân biệt file trống với file hỏng.

**Cách xử lý:** truyền lỗi lên tầng thích hợp, log nguyên nhân không nhạy cảm và chỉ fallback khi nghiệp vụ cho phép.

## 27. Những hiểu nhầm cần tránh

**“InputStream biết file của tôi đang ở UTF-8.”**  
Không. InputStream chỉ đọc byte; charset được chọn khi giải mã thành ký tự.

**“Java mặc định UTF-8 nên không cần chỉ định charset.”**  
Không nên phụ thuộc điều này ở biên dữ liệu. Hợp đồng encoding rõ ràng giúp code ổn định giữa JVM, thư viện và môi trường.

**“Charset sai chỉ ảnh hưởng hiển thị, không ảnh hưởng dữ liệu.”**  
Không. Nó có thể làm hỏng key, chữ ký, so sánh, parser và những giá trị được ghi lại.

**“ClassPathResource luôn có thể chuyển thành File.”**  
Không. Resource trong executable JAR có thể không có file filesystem độc lập.

**“Resource object phải gọi close() sau mỗi lần dùng.”**  
Không. Với những Resource descriptor thông thường, bạn phải đóng InputStream/Reader đã mở từ Resource.

**“resource.exists() là bảo đảm đọc được.”**  
Không. Tài nguyên có thể thay đổi sau khi kiểm tra và việc đọc vẫn có thể ném IOException.

**“Đọc hết byte là stream tự đóng.”**  
Không. EOF, readAllBytes() hoặc transferTo() không thay thế close().

**“Đóng BufferedReader không liên quan InputStream gốc.”**  
Không. Đóng wrapper thông thường đóng những stream/reader bên dưới.

**“API nhận InputStream thì luôn phải tự đóng nó.”**  
Không. Cần hợp đồng ownership: stream có thể chỉ được mượn từ caller.

**“Stream trả về từ Files.lines() là collection thuần.”**  
Không. Nó có tài nguyên I/O bên dưới và phải đóng.

**“Chỉ cần trả Resource là mọi HTTP download đều có thể đọc nhiều lần.”**  
Không. InputStreamResource thường single-use; khả năng đọc lại phụ thuộc loại Resource.

**“Spring quản lý bean nên tự động đóng mọi stream mở trong method của bean.”**  
Không. Bean lifecycle và vòng đời InputStream mỗi lần đọc là hai phạm vi khác nhau.

**“Response output stream do controller mở và đóng.”**  
Không đúng trong mô hình Servlet thông thường. Framework/container thường sở hữu lifecycle của HTTP response stream.

**“Một MultipartFile có thể được giữ lại vô hạn sau request.”**  
Không. Nó có thể dựa trên temporary storage theo request lifecycle.

**“@PreDestroy luôn chạy khi process kết thúc.”**  
Không. Crash, kill cưỡng bức hoặc mất điện có thể bỏ qua callback.

**“Đóng Connection và đóng DataSource là một việc.”**  
Không. Connection từ pool thường được trả về pool khi close; DataSource/pool là tài nguyên dùng chung do context quản lý.

**“Streaming bảo đảm chương trình không bao giờ cạn tài nguyên.”**  
Không. Nó giảm nhu cầu giữ toàn bộ payload trong RAM nhưng vẫn cần giới hạn concurrent streams, network timeouts và file handles.

## 28. Quy trình chọn API và xác định nơi close

Khi cần đọc hoặc ghi một tài nguyên trong Spring Boot, có thể đi theo thứ tự:

### Bước 1: Xác định nguồn

Nguồn là file classpath, file hệ thống, upload multipart, network URL hay dữ liệu byte trong RAM?

- Classpath → ClassPathResource hoặc ResourceLoader với classpath:.
- Filesystem → Path/Files API hoặc FileSystemResource.
- Upload → MultipartFile trong request lifecycle.
- Byte nhỏ trong RAM → ByteArrayResource.
- Stream có sẵn → xác định hợp đồng ownership và khả năng đọc một lần.

### Bước 2: Xác định dữ liệu là text hay binary

- Binary → InputStream/OutputStream hoặc API nhị phân phù hợp.
- Text → Reader/Writer hoặc Files.readString/writeString với charset được quy định rõ.
- Định dạng có parser chuyên dụng như JSON, XML hoặc CSV → ưu tiên parser đúng định dạng và cấu hình encoding của parser.

### Bước 3: Xác định kích thước và cách xử lý

- Dữ liệu nhỏ, giới hạn rõ → có thể đọc vào String hoặc byte[].
- Dữ liệu lớn → buffered streaming, xử lý theo chunk/dòng và giới hạn tài nguyên.
- Lazy Stream → phải giữ nguồn mở đến khi terminal operation kết thúc.

### Bước 4: Xác định ownership

~~~text
Bạn có tự mở tài nguyên không?
             │
       ┌─────┴──────┐
       │            │
      Có           Không
       │            │
       ▼            ▼
Tự đóng sau dùng   Ai sở hữu?
       │            │
       │     ┌──────┴─────────┐
       │     │                │
       │   Caller         Framework
       │     │                │
       ▼     ▼                ▼
try-with-resources     Tuân theo lifecycle/API contract
~~~

Nếu method tự mở stream từ Resource, nó nên tự đóng. Nếu method trả stream còn mở, phải ghi rõ caller cần đóng. Nếu stream thuộc HTTP response/container, không đóng thay framework khi API không trao quyền sở hữu.

### Bước 5: Kiểm tra thời điểm đóng

- Đã hoàn tất việc đọc/ghi chưa?
- Có return sớm hoặc exception không?
- Có callback bất đồng bộ đang dùng stream không?
- Có lazy Stream sẽ được consume sau khi method return không?
- Nguồn có hết vòng đời khi request kết thúc không?

### Bước 6: Xử lý lỗi và quan sát

- Không nuốt IOException không có lý do.
- Giữ thông tin cause chain để chẩn đoán.
- Không log file nhạy cảm hoặc toàn bộ payload ngoài ý muốn.
- Kiểm soát timeout, file size, concurrency và cleanup.
- Kiểm thử cả charset có dấu tiếng Việt và tình huống resource không tồn tại.

## Ghi nhớ cốt lõi

**Charset** trả lời câu hỏi “byte được chuyển thành ký tự bằng quy tắc nào?”. Với văn bản có hợp đồng UTF-8, hãy dùng **StandardCharsets.UTF_8** tường minh khi đọc và ghi. Nếu dữ liệu thực tế mang encoding khác, phải xác định encoding đúng thay vì giải mã theo mặc định.

**try-with-resources** là cách chuẩn để đóng InputStream, Reader, Writer và những I/O-backed streams mà code sở hữu, kể cả khi xảy ra exception. Một stream đọc hết chưa chắc đã đóng; wrapper như BufferedReader có thể đóng stream bên dưới; Files.lines() cần close; lazy Stream không được sống lâu hơn nguồn dữ liệu của nó.

**Vòng đời tài nguyên** phải đi theo ownership. Đọc file trong executable JAR bằng **Resource.getInputStream()**, không giả định có một File vật lý. Code tự mở stream từ Resource thì tự đóng; Spring MVC/servlet container thường quản lý response output; ApplicationContext quản lý tài nguyên dài hạn của các bean theo destroy callback, nhưng không đóng thay mọi stream ngắn hạn do service mở. Hiểu đúng ba nguyên tắc này giúp tránh lỗi charset, file handle leak, stream closed và các sự cố khó phát hiện khi ứng dụng chuyển từ IDE sang môi trường triển khai thật.
