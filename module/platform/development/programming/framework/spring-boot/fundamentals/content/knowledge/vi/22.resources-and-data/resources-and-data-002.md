# Đọc tài nguyên bằng InputStream và giới hạn của Resource.getFile trong JAR

Một ứng dụng Spring Boot thường đi kèm những tài nguyên không phải mã Java: template email, file JSON mẫu, SQL script, chứng chỉ công khai, ảnh, font, tài liệu PDF, bảng tra cứu CSV hoặc dữ liệu khởi tạo. Khi chạy bằng IDE, các tài nguyên trong `src/main/resources` thường được copy ra một thư mục trên đĩa nên bạn có thể đọc chúng bằng `File` hoặc `Path`. Nhưng sau khi đóng gói thành **executable JAR**, tài nguyên có thể nằm **bên trong một archive**, không còn tồn tại dưới dạng một file độc lập trong filesystem của hệ điều hành.

Đây là nguyên nhân của một lỗi Spring Boot rất phổ biến:

~~~text
java.io.FileNotFoundException:
class path resource [data/catalog.json] cannot be resolved to absolute
file path because it does not reside in the file system
~~~

Lỗi thường xuất hiện khi code gọi `Resource.getFile()` hoặc lấy `Path` từ URL của một resource nằm trong JAR. Nó không có nghĩa tài nguyên không tồn tại. Nó có thể vẫn được đọc bình thường bằng `Resource.getInputStream()`.

**Nguyên tắc trọng tâm:** với tài nguyên đóng gói theo classpath, hãy suy nghĩ theo **luồng byte hoặc resource abstraction**, không mặc định rằng resource có đường dẫn file vật lý. Chỉ sử dụng `File` hoặc `Path` khi đối tượng thực sự nằm trên filesystem, hoặc khi bạn chủ động copy nội dung sang một file tạm cho API bắt buộc cần file.

Bài học trình bày mô hình tài nguyên Spring, lý do `getFile()` hoạt động trong IDE nhưng thất bại khi chạy JAR, cách đọc text/binary bằng `InputStream`, cách tích hợp `@Value` và `ResourceLoader`, cách dùng tài nguyên ngoài JAR, cùng các ví dụ kiểm thử và xử lý sự cố.

## 1. Tài nguyên trong ứng dụng Spring Boot là gì?

Một project Maven hoặc Gradle thông thường có cấu trúc:

~~~text
my-spring-boot-app/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       ├── DemoApplication.java
│   │   │       └── CatalogService.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── data/
│   │       │   ├── catalog.json
│   │       │   └── cities.csv
│   │       ├── templates/
│   │       │   └── welcome.txt
│   │       └── images/
│   │           └── logo.png
│   └── test/
│       └── resources/
│           └── data/
│               └── catalog-test.json
└── build.gradle
~~~

Trong quá trình build, nội dung `src/main/resources` được đưa vào **runtime classpath**. Các tài nguyên sẽ được truy cập theo đường dẫn **tương đối với gốc classpath**, không kèm tiền tố `src/main/resources`.

Ví dụ:

| File trong project | Resource location khi chạy |
| --- | --- |
| `src/main/resources/data/catalog.json` | `classpath:data/catalog.json` |
| `src/main/resources/data/cities.csv` | `classpath:data/cities.csv` |
| `src/main/resources/templates/welcome.txt` | `classpath:templates/welcome.txt` |
| `src/main/resources/images/logo.png` | `classpath:images/logo.png` |

Nếu viết `classpath:src/main/resources/data/catalog.json`, ứng dụng thường không tìm thấy tài nguyên vì `src/main/resources` không phải một phần của tên resource trong classpath.

### 1.1. Classpath và filesystem không giống nhau

Một đường dẫn filesystem, ví dụ:

~~~text
/opt/app/config/catalog.json
C:\applications\demo\catalog.json
~~~

trỏ tới một file vật lý trên hệ điều hành. Java có thể mở nó bằng `Path`, `Files.newInputStream(...)` hoặc `FileInputStream` nếu có quyền truy cập.

Ngược lại, `classpath:data/catalog.json` là một **tên tài nguyên logic** được class loader tìm kiếm. Tài nguyên đó có thể nằm:

- Trong thư mục output của project khi chạy từ IDE.
- Trong một JAR thông thường.
- Trong `BOOT-INF/classes` của executable JAR Spring Boot.
- Trong một dependency JAR, có thể là nested JAR.
- Trong một class loader hoặc môi trường đóng gói khác mà Spring hỗ trợ.

Vì vậy, một tên resource logic không đồng nghĩa với một đường dẫn vật lý ổn định.

### 1.2. Đọc tài nguyên khác với đọc cấu hình động

Một template mặc định đi kèm ứng dụng phù hợp để đặt trong `src/main/resources`. Nhưng file mà người vận hành cần thay đổi sau khi deploy thường nên nằm bên ngoài JAR và được trỏ tới qua property hoặc đường dẫn filesystem.

Nếu bạn sửa file bên trong thư mục `src/main/resources` trên máy phát triển rồi deploy lại ứng dụng, nội dung mới được đóng gói vào artifact. Trong production, không nên giả định có thể sửa trực tiếp resource bên trong executable JAR như một file độc lập.

## 2. Spring Resource abstraction

Spring định nghĩa interface `org.springframework.core.io.Resource`. Nó cung cấp một cách truy cập thống nhất tới nhiều loại tài nguyên mà không bắt buộc caller biết nơi lưu trữ cụ thể.

Các method thường dùng:

| Method | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `getInputStream()` | Mở luồng để đọc byte của resource | Phù hợp với classpath/JAR; caller phải đóng stream |
| `exists()` | Kiểm tra resource có tồn tại theo implementation | Không có nghĩa resource là file vật lý |
| `isReadable()` | Kiểm tra khả năng đọc theo resource implementation | Không thay thế việc xử lý `IOException` |
| `getFilename()` | Lấy tên phần cuối của resource | Có thể null, không phải đường dẫn vật lý |
| `getDescription()` | Mô tả resource phục vụ log/lỗi | Không chứa nội dung file |
| `getURL()` | Trả về URL biểu diễn vị trí resource | URL có thể dùng protocol `jar:` hoặc dạng khác |
| `getURI()` | Trả về URI của resource | Không bảo đảm chuyển được thành `Path` |
| `getFile()` | Yêu cầu resource cung cấp `java.io.File` | Có thể thất bại nếu resource nằm trong archive |
| `contentLength()` | Xác định độ dài nội dung | Một số implementation có thể cần đọc stream để tính |
| `lastModified()` | Lấy thời gian sửa đổi nếu có thể | Không phải implementation nào cũng cung cấp thông tin có ý nghĩa |

`Resource` là abstraction cho nhiều vị trí khác nhau. Bạn nên chọn API theo **điều cần làm**: muốn đọc byte thì dùng stream; muốn sửa file trên đĩa thì làm việc với một filesystem path thực; không ép mọi Resource thành File.

### 2.1. Những implementation quan trọng

| Implementation | Tình huống sử dụng | `getFile()` |
| --- | --- | --- |
| `ClassPathResource` | Tài nguyên trên classpath | Có thể thành công khi nằm ở thư mục; thường thất bại khi nằm trong JAR |
| `FileSystemResource` | File trên filesystem | Phù hợp với `File`/`Path` thực |
| `PathResource` | Tài nguyên được biểu diễn bằng NIO `Path` | Phù hợp với filesystem path |
| `UrlResource` | Resource có URL như `file:`, `jar:`, `https:` | Phụ thuộc protocol; `jar:` không tự là file |
| `ByteArrayResource` | Nội dung byte có sẵn trong memory | Không phải file vật lý |
| `InputStreamResource` | Bọc một stream đã mở | Thường chỉ đọc một lần; không dùng như resource có thể mở lặp |

Một `ClassPathResource` có thể hỗ trợ `getFile()` trong môi trường chạy bằng thư mục, nhưng đó là **khả năng tùy vị trí hiện tại**, không phải một hợp đồng bảo đảm tài nguyên classpath luôn có file vật lý.

## 3. Vì sao Resource.getFile() thường lỗi khi chạy executable JAR?

Xét code sau:

~~~java
import java.io.File;
import java.io.IOException;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class CatalogLoader {

    public String loadCatalogPath() throws IOException {
        Resource resource = new ClassPathResource("data/catalog.json");
        File file = resource.getFile(); // Có thể lỗi trong packaged JAR.
        return file.getAbsolutePath();
    }
}
~~~

Khi chạy từ IDE, resource có thể được copy tới một thư mục tương tự:

~~~text
build/resources/main/data/catalog.json
~~~

Ở đây class loader tìm được tài nguyên dưới một URL có ý nghĩa filesystem, nên `getFile()` có thể trả về `File`.

Khi đóng gói ứng dụng Spring Boot thành executable JAR:

~~~text
app.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   └── data/
    │       └── catalog.json
    └── lib/
        ├── spring-boot-....jar
        └── some-library.jar
~~~

Tài nguyên `catalog.json` là **một entry trong archive**. Hệ điều hành không cung cấp một file độc lập ở đường dẫn `/somewhere/catalog.json` chỉ vì entry tồn tại trong JAR.

Spring Boot còn có cơ chế class loading riêng cho executable JAR và nested dependency JAR. URL dùng để định vị entry có thể thể hiện một vị trí trong archive, không phải `file:` URL đến một file thông thường.

~~~mermaid
flowchart TD
    A["ClassPathResource: data/catalog.json"] --> B{"Vị trí runtime"}
    B -->|IDE / exploded classes| C["Thư mục trên filesystem"]
    B -->|Executable JAR| D["Entry trong BOOT-INF/classes"]
    B -->|Dependency JAR| E["Entry trong một JAR thư viện"]
    C --> F["getFile() có thể thành công"]
    D --> G["getFile() không có file vật lý tương ứng"]
    E --> G
    C --> H["getInputStream()"]
    D --> H
    E --> H
    H --> I["Đọc byte qua luồng"]
~~~

Vì thế cùng một dòng code có thể chạy tốt trong IDE rồi hỏng khi deploy bằng `java -jar app.jar`.

### 3.1. Resource tồn tại không có nghĩa getFile() thành công

Ví dụ:

~~~java
Resource resource = new ClassPathResource("data/catalog.json");

boolean exists = resource.exists(); // Có thể true trong executable JAR.

// Không được suy ra:
File file = resource.getFile();      // Vẫn có thể ném IOException.
~~~

`exists()` trả lời “resource có được tìm thấy không?”. `getFile()` trả lời “có thể biểu diễn resource này như một file của filesystem không?”. Hai câu hỏi khác nhau.

### 3.2. Lỗi thường được biểu hiện ra sao?

Bạn có thể thấy exception dạng:

~~~text
java.io.FileNotFoundException:
class path resource [data/catalog.json] cannot be resolved to absolute
file path because it does not reside in the file system
~~~

Đôi khi code không gọi `getFile()` trực tiếp mà thất bại tại:

~~~java
Path path = resource.getFile().toPath();

String content = Files.readString(resource.getFile().toPath());

FileInputStream stream = new FileInputStream(resource.getFile());
~~~

Cách sửa không phải là thay `getFile().toPath()` bằng một biến thể chuyển đổi URI; cần xem thao tác cuối cùng có thực sự đòi file vật lý hay chỉ muốn đọc nội dung.

## 4. Cách đúng: đọc tài nguyên bằng Resource.getInputStream()

Với resource đóng gói, `Resource.getInputStream()` là API phổ biến và đáng tin cậy để đọc nội dung.

Ví dụ đơn giản:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class CatalogReader {

    public String readCatalog() throws IOException {
        Resource resource = new ClassPathResource("data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            byte[] bytes = input.readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }
}
~~~

Code không cần một đường dẫn filesystem. Stream được class loader và implementation `Resource` mở từ vị trí thực tế, dù là thư mục hay JAR entry.

### 4.1. Vì sao try-with-resources quan trọng?

`getInputStream()` trả về một luồng cần được đóng. `try-with-resources` bảo đảm `close()` được gọi kể cả khi đọc gặp lỗi:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Đọc nội dung.
}
~~~

Nếu bỏ qua việc đóng stream, ứng dụng có thể giữ tài nguyên native, file descriptor, kết nối hoặc handle tùy implementation. Với những request lặp lại liên tục, rò rỉ stream có thể dẫn tới lỗi tài nguyên và khó chẩn đoán.

Không giữ một `InputStream` đã mở trong field singleton để sử dụng xuyên suốt vòng đời ứng dụng nếu không có lý do và lifecycle quản lý rõ ràng. Thông thường, hãy giữ `Resource` rồi mở stream trong phạm vi một thao tác.

### 4.2. Ví dụ với Resource được inject

Thay vì tự khởi tạo `ClassPathResource` trong từng method, có thể inject resource bằng Spring:

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class WelcomeTemplateService {

    private final Resource template;

    public WelcomeTemplateService(
            @Value("classpath:templates/welcome.txt") Resource template) {
        this.template = template;
    }

    public String loadTemplate() throws IOException {
        try (InputStream input = template.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

File:

~~~text
src/main/resources/templates/welcome.txt
~~~

Nội dung ví dụ:

~~~text
Xin chào, đây là ứng dụng Spring Boot!
~~~

`@Value` ở constructor parameter cho Spring biết resource location. Service chỉ giữ `Resource`, không giữ stream đã mở.

Khi gọi `loadTemplate()`, method mở một stream mới. Cách này phù hợp với `ClassPathResource` và nhiều resource có thể mở lại; không nên mặc định mọi implementation `Resource` đều hỗ trợ mở lại, đặc biệt `InputStreamResource`.

## 5. Đọc text: chỉ định charset rõ ràng

`InputStream` là luồng **byte**, không biết văn bản thuộc UTF-8, UTF-16 hay encoding khác. Khi đọc text, phải chọn charset.

### 5.1. Đọc hết nội dung text nhỏ

Với template nhỏ hoặc file JSON cấu hình ít dữ liệu:

~~~java
public String readUtf8(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
    }
}
~~~

`readAllBytes()` có sẵn trong Java 9 trở lên; Spring Boot 3.3 chạy trên các phiên bản Java đáp ứng yêu cầu tối thiểu của nó, nên API này khả dụng.

Lưu ý: `readAllBytes()` đưa toàn bộ nội dung vào RAM. Phù hợp cho resource nhỏ được đóng gói và có kích thước kiểm soát. Không dùng cho file rất lớn hoặc dữ liệu do người dùng cung cấp mà chưa giới hạn dung lượng.

### 5.2. Dùng InputStreamReader và BufferedReader

Nếu muốn xử lý từng dòng:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public void printLines(Resource resource) throws IOException {
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8
            )
    )) {
        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println(line);
        }
    }
}
~~~

`BufferedReader` tạo lớp đọc văn bản có buffer và `readLine()` tách dòng theo semantics của reader. Phù hợp cho CSV line-oriented, file cấu hình text hoặc danh sách dữ liệu.

Lưu ý: mã trên chỉ minh họa đọc từng dòng. Với CSV thực tế có trường đặt trong dấu nháy, dấu phẩy hoặc newline bên trong field, không nên tự parse bằng `String.split(",")`; hãy dùng thư viện CSV có parser tương thích định dạng.

### 5.3. Giữ byte gốc hay chuyển thành String?

| Loại dữ liệu | Cách đọc nên dùng |
| --- | --- |
| Text UTF-8 nhỏ | `readAllBytes()` rồi `new String(..., UTF_8)` |
| Text lớn xử lý theo dòng | `InputStreamReader` + `BufferedReader` |
| JSON | Đưa `InputStream` cho Jackson/ObjectMapper |
| XML | Đưa stream cho parser XML được cấu hình an toàn |
| CSV | Đưa reader cho thư viện CSV |
| PNG/JPEG/PDF | Xử lý byte hoặc stream; không chuyển bừa sang String |
| ZIP hoặc archive | Dùng API stream/archive phù hợp |

Đừng giả định mọi byte có thể chuyển sang String UTF-8 mà không mất thông tin. Với file nhị phân, dùng stream hoặc byte buffer.

## 6. Ví dụ JSON: truyền InputStream trực tiếp cho Jackson

Một ứng dụng có dữ liệu mẫu trong `src/main/resources/data/catalog.json`:

~~~json
{
  "catalogName": "spring-fundamentals",
  "items": [
    { "id": "book-1", "title": "Introduction" },
    { "id": "book-2", "title": "Resources" }
  ]
}
~~~

Java record:

~~~java
public record Catalog(
        String catalogName,
        List<Item> items
) {
    public record Item(String id, String title) {}
}
~~~

Service dùng Jackson `ObjectMapper`:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final ObjectMapper objectMapper;

    public CatalogService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Catalog readBundledCatalog() throws IOException {
        Resource resource = new ClassPathResource("data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            return objectMapper.readValue(input, Catalog.class);
        }
    }
}
~~~

`ObjectMapper` có thể đọc trực tiếp từ stream nên không cần trung gian `String`, `File` hoặc `Path`. Trong ứng dụng có Spring Boot JSON auto-configuration phù hợp, `ObjectMapper` thường được đăng ký dưới dạng bean có thể inject; nếu không, hãy khai báo bean cụ thể.

### 6.1. Parser có thể đóng stream không?

Một số thư viện có tùy chọn tự quản lý nguồn vào. Dù parser có thể đóng stream trong một số chế độ, hãy để phạm vi `try-with-resources` biểu diễn quyền sở hữu resource rõ ràng. Khi method sở hữu stream do chính nó mở, nó phải đóng stream khi xong.

Nếu truyền stream vào một API bất đồng bộ đọc sau khi method trả về, `try-with-resources` đóng sớm có thể gây lỗi. Trong trường hợp đó, owner của thao tác bất đồng bộ phải quản lý thời gian sống của stream theo hợp đồng API.

## 7. Đọc dữ liệu nhị phân bằng InputStream

Đối với PDF, ảnh hoặc file nhị phân, tránh giải mã thành text. Có thể copy nội dung tới `OutputStream`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public void copyResource(Resource resource, OutputStream output)
        throws IOException {

    try (InputStream input = resource.getInputStream()) {
        input.transferTo(output);
    }
}
~~~

`InputStream.transferTo(...)` có từ Java 9, chuyển các byte từ input sang output. Method trên **chỉ đóng InputStream do nó mở**, không đóng `OutputStream` do caller cung cấp. Caller sở hữu output stream và quyết định khi nào đóng nó.

Đây là mô hình phù hợp khi ứng dụng cần gửi một tài liệu đóng gói sang storage, xuất dữ liệu ra HTTP response hoặc truyền file qua một API nhận stream.

### 7.1. Khi nào dùng streaming thay vì readAllBytes?

Giả sử một file PDF có kích thước 200 MB. Nếu gọi `readAllBytes()`, ứng dụng cần giữ toàn bộ 200 MB (và có thể thêm bản sao trung gian) trong bộ nhớ trước khi xử lý.

Nếu dùng stream và copy theo buffer, ứng dụng có thể xử lý dần dữ liệu. `transferTo` giúp giảm nhu cầu tự viết vòng lặp và tránh giữ toàn bộ resource trong RAM.

Với các API cần byte array, hãy giới hạn kích thước resource trước khi đọc toàn bộ. Đừng xem `contentLength()` là điều kiện bảo mật duy nhất; một resource động có thể có độ dài không được biết hoặc thay đổi.

### 7.2. Dùng buffer thủ công nếu cần

~~~java
public void copyBuffered(Resource resource, OutputStream output)
        throws IOException {

    try (InputStream input = resource.getInputStream()) {
        byte[] buffer = new byte[8192];
        int count;

        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
        }
    }
}
~~~

Đoạn này có cùng ý nghĩa streaming, đồng thời cho phép bạn chèn logic giới hạn số byte, tính checksum hoặc đo tiến trình chuyển dữ liệu.

Không nên tự flush `output` sau mỗi khối nhỏ nếu không có nhu cầu đặc biệt vì có thể ảnh hưởng hiệu năng.

## 8. @Value và ResourceLoader: hai cách nhận resource

`ClassPathResource` là lựa chọn trực tiếp khi tên resource cố định. Khi location cần đến từ cấu hình hoặc nhiều loại resource, `ResourceLoader` và injection có thể phù hợp hơn.

### 8.1. Inject Resource trực tiếp bằng @Value

~~~java
@Component
public class ReportTemplateRepository {

    private final Resource template;

    public ReportTemplateRepository(
            @Value("classpath:templates/report.html") Resource template) {
        this.template = template;
    }

    public String readTemplate() throws IOException {
        try (InputStream input = template.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Spring hỗ trợ chuyển resource location thành `Resource` tại injection point.

Nếu cần cho phép người vận hành override đường dẫn, đưa location vào property thay vì hard-code:

~~~properties
app.report.template-location=classpath:templates/report.html
~~~

~~~java
@Component
public class ConfigurableTemplateRepository {

    private final Resource resource;

    public ConfigurableTemplateRepository(
            @Value("${app.report.template-location}") Resource resource) {
        this.resource = resource;
    }

    public String read() throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Khi property được đặt thành `file:/opt/app/config/report.html`, Spring có thể đưa vào một resource filesystem thay vì classpath.

### 8.2. Dùng ResourceLoader

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class ResourceReadingService {

    private final ResourceLoader resourceLoader;

    public ResourceReadingService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public byte[] readClasspathFile(String path) throws IOException {
        Resource resource =
                resourceLoader.getResource("classpath:" + path);

        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

Ví dụ này minh họa API. Với dữ liệu đầu vào từ người dùng, **không nối đường dẫn tùy ý trực tiếp** mà không kiểm tra. Người dùng có thể cố chọn các resource không được phép đọc. Hãy cho phép chỉ những tên resource đã được định nghĩa hoặc chuẩn hóa/kiểm soát path cẩn thận.

### 8.3. Khi location không có prefix thì sao?

`ResourceLoader.getResource(location)` hỗ trợ các prefix như `classpath:` và URL protocol như `file:`. Cách diễn giải location không có prefix tùy implementation cụ thể của resource loader và context.

Để code dễ hiểu và ít phụ thuộc môi trường, hãy dùng prefix rõ ràng:

- `classpath:data/catalog.json` cho resource đóng gói.
- `file:/opt/app/data/catalog.json` cho file ngoài JAR.
- Không tùy tiện cho phép URL từ bên ngoài nếu không có chính sách bảo mật và timeout phù hợp.

## 9. ClassPathResource và ClassLoader.getResourceAsStream()

Ngoài Spring Resource abstraction, Java có sẵn cơ chế đọc resource qua class loader.

### 9.1. ClassPathResource

~~~java
Resource resource = new ClassPathResource("data/catalog.json");

try (InputStream input = resource.getInputStream()) {
    // Đọc dữ liệu.
}
~~~

Đường dẫn trong ví dụ tính từ gốc classpath.

### 9.2. ClassLoader.getResourceAsStream

~~~java
ClassLoader classLoader = Thread.currentThread()
        .getContextClassLoader();

try (InputStream input =
             classLoader.getResourceAsStream("data/catalog.json")) {
    if (input == null) {
        throw new IOException("Resource not found: data/catalog.json");
    }

    // Đọc dữ liệu từ input.
}
~~~

`ClassLoader.getResourceAsStream(...)` trả về `null` nếu không tìm thấy resource. Không nên gọi `input.read()` ngay mà quên xử lý trường hợp null.

### 9.3. Class.getResourceAsStream và dấu gạch chéo đầu

~~~java
try (InputStream rootResource =
             DemoApplication.class.getResourceAsStream(
                     "/data/catalog.json"
             )) {
    // Dấu / đầu: tìm từ gốc classpath.
}
~~~

Với `Class.getResourceAsStream`:

- `"/data/catalog.json"` bắt đầu từ gốc classpath.
- `"data/catalog.json"` không có dấu slash đầu được giải thích tương đối theo package của class.

Với `ClassLoader.getResourceAsStream`, path thường là tên resource từ gốc classpath, **không đặt dấu slash đầu**.

| API | Ví dụ từ gốc classpath |
| --- | --- |
| `new ClassPathResource(...)` | `"data/catalog.json"` |
| `ClassLoader.getResourceAsStream(...)` | `"data/catalog.json"` |
| `DemoApplication.class.getResourceAsStream(...)` | `"/data/catalog.json"` |

Dấu slash có thể là nguồn lỗi khó nhận thấy khi chuyển giữa các API. Nếu đã dùng Spring, `ClassPathResource` hoặc `ResourceLoader` thường thể hiện ý định rõ hơn.

## 10. getURL() và getURI() không thay thế getInputStream()

Một số người sửa lỗi `getFile()` bằng cách gọi `resource.getURL()`, rồi chuyển URL sang `Path`:

~~~java
URL url = resource.getURL();

// Không an toàn cho resource trong JAR:
Path path = Paths.get(url.toURI());
~~~

Khi URL trỏ tới file thường, cách chuyển có thể hoạt động. Nhưng khi resource nằm trong JAR, URL có thể có scheme đặc biệt biểu diễn một entry trong archive, và `Path.of(uri)` hoặc `Paths.get(uri)` không biết cách xử lý nó như file thông thường.

Ví dụ dạng location khái niệm:

~~~text
file:/opt/app/classes/data/catalog.json
jar:file:/opt/app/lib/config.jar!/data/catalog.json
jar:nested:/opt/app/app.jar/!BOOT-INF/lib/library.jar!/data/catalog.json
~~~

Các URL trong thực tế phụ thuộc version, loader và nơi đóng gói. Không nên parse chuỗi URL như trên bằng cách tách dấu `!` hoặc cố nối thành đường dẫn filesystem.

### 10.1. URL là locator, không phải File

`URL` và `URI` mô tả cách định vị một tài nguyên; `File` và `Path` biểu diễn một đối tượng trong filesystem. Hai nhóm có thể giao nhau với `file:` URL, nhưng không phải mọi URL đều chuyển thành file.

Với nhiệm vụ đọc nội dung, hãy mở stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Đọc byte.
}
~~~

Nếu một thư viện nhận `URL` và hỗ trợ đọc `jar:` URL đúng cách, bạn có thể truyền URL trực tiếp. Nhưng cần kiểm tra contract của thư viện. Không mặc định nó xử lý được nested JAR do Spring Boot loader cung cấp.

### 10.2. Không dùng ZipFile chỉ để truy cập resource

Một hướng khác là cố mở executable JAR bằng `ZipFile` hoặc `JarFile` rồi tìm entry. Điều này làm code phụ thuộc cấu trúc đóng gói, vị trí `BOOT-INF/classes` và cơ chế nested JAR.

Nếu class loader đã biết cách đọc resource, hãy để `ClassPathResource.getInputStream()` hoặc API class loader thực hiện. Chỉ dùng API archive khi yêu cầu nghiệp vụ thật sự là thao tác với nội dung của archive như một file ZIP/JAR.

## 11. Khi thư viện bên ngoài chỉ chấp nhận File hoặc Path

Không phải API nào cũng nhận `InputStream`. Một thư viện cũ có thể yêu cầu:

~~~java
legacyParser.parse(File file);
~~~

Nếu tài nguyên nằm trong JAR, không thể chuyển trực tiếp `ClassPathResource` thành `File`. Lúc này có hai hướng:

1. Ưu tiên tìm overload nhận `InputStream`, `Reader`, `byte[]` hoặc `URL` được thư viện hỗ trợ.
2. Nếu không thể thay đổi API, **copy resource ra một file tạm thật**, sau đó truyền `File` hoặc `Path` cho thư viện.

### 11.1. Copy sang temp file bằng Files.copy

~~~java
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.core.io.Resource;

public class LegacyParserAdapter {

    private final LegacyParser legacyParser;

    public LegacyParserAdapter(LegacyParser legacyParser) {
        this.legacyParser = legacyParser;
    }

    public void parseBundledResource(Resource resource) throws IOException {
        Path temporaryFile =
                Files.createTempFile("spring-resource-", ".bin");

        try {
            try (InputStream input = resource.getInputStream()) {
                Files.copy(
                        input,
                        temporaryFile,
                        StandardCopyOption.REPLACE_EXISTING
                );
            }

            File file = temporaryFile.toFile();
            legacyParser.parse(file);
        } finally {
            Files.deleteIfExists(temporaryFile);
        }
    }
}
~~~

Trong ví dụ, `LegacyParser` là abstraction của một thư viện giả định. Thay nó bằng API thực tế của bạn. Điểm chính là resource được copy thành **file vật lý** trước khi đưa vào API.

### 11.2. Khi nào mới được xóa file tạm?

Ví dụ trên xóa file trong `finally` **sau khi lời gọi `parse(file)` kết thúc**. Cách này chỉ đúng nếu thư viện đọc xong file đồng bộ trong method.

Nếu thư viện lưu đường dẫn rồi xử lý bất đồng bộ, xóa ngay sẽ khiến công việc nền không tìm thấy file. Khi đó phải quản lý file tạm theo lifecycle công việc: chỉ xóa sau khi tác vụ thật sự hoàn tất, thất bại hoặc bị hủy.

### 11.3. File tạm cần suffix và quyền truy cập phù hợp

Một số thư viện chọn parser theo extension, chẳng hạn `.json`, `.pdf` hoặc `.ttf`. Hãy tạo file tạm có suffix phù hợp thay vì luôn dùng `.bin`.

Cần cân nhắc:

- Dung lượng ổ đĩa tạm và quyền ghi trong container.
- Thông tin nhạy cảm có thể nằm trong file tạm.
- Xóa file khi thành công, thất bại và ứng dụng bị gián đoạn.
- Không dùng tên file cố định dễ va chạm giữa request.
- Không để client điều khiển trực tiếp đường dẫn file tạm.
- Một số hệ điều hành không cho xóa file còn bị process giữ mở.

Nếu một API có thể nhận stream, cách đó thường đơn giản và tránh thêm rủi ro của file tạm.

### 11.4. Có cần copy để cache resource luôn không?

Không nhất thiết. Nếu cần đọc một file nhỏ nhiều lần, bạn có thể parse một lần khi bean khởi tạo rồi giữ kết quả **bất biến** trong bộ nhớ. Nếu cần stream dữ liệu lớn, mở stream theo mỗi thao tác. Chỉ tạo file tạm khi API hoặc use case thực sự đòi đường dẫn filesystem.

## 12. Resource ngoài JAR: khi nào getFile() phù hợp?

`getFile()` không phải một API luôn sai. Nó đúng khi resource thực sự là một file trên đĩa.

Ví dụ:

~~~java
import java.io.File;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource external =
        new FileSystemResource("/opt/app/config/catalog.json");

File file = external.getFile();
~~~

Ở đây source là file filesystem, nên gọi `getFile()` phù hợp với contract. Bạn cũng có thể dùng `Path` trực tiếp:

~~~java
Path path = Path.of("/opt/app/config/catalog.json");

try (InputStream input = Files.newInputStream(path)) {
    // Đọc file bên ngoài JAR.
}
~~~

Dùng file ngoài JAR khi dữ liệu cần:

- Được cập nhật sau deployment mà không rebuild artifact.
- Được mount dưới dạng ConfigMap, Secret hoặc volume trong container.
- Được quản trị bởi operator.
- Có quyền ghi và tồn tại độc lập với vòng đời artifact.
- Được truyền cho API yêu cầu filesystem path thật.

### 12.1. Resource location lấy từ cấu hình

Trong `application.yml`:

~~~yaml
app:
  catalog:
    location: file:/opt/app/config/catalog.json
~~~

Consumer:

~~~java
@Service
public class CatalogLocationService {

    private final Resource resource;

    public CatalogLocationService(
            @Value("${app.catalog.location}") Resource resource) {
        this.resource = resource;
    }

    public String read() throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Dù location trỏ tới external file, việc dùng `getInputStream()` vẫn hợp lệ và giúp service không phụ thuộc vào loại tài nguyên. Chỉ khi một API thật sự yêu cầu `File` mới cần `getFile()`.

### 12.2. Fallback từ external file sang classpath default

Một thiết kế thường gặp là ứng dụng có template mặc định trong JAR nhưng cho phép override bằng file ngoài:

~~~properties
app.template.location=classpath:templates/default.txt
~~~

Khi deploy, operator có thể đổi thành:

~~~properties
app.template.location=file:/opt/app/templates/custom.txt
~~~

Service chỉ đọc `Resource` được inject và không cần biết nguồn đến từ JAR hay filesystem.

Điều này giảm nhu cầu đọc đường dẫn tương đối theo working directory, vốn có thể thay đổi khi chạy bằng IDE, systemd, Docker hoặc Kubernetes.

### 12.3. Tài nguyên classpath nên được xem là read-only

Với resource nằm trong executable JAR, không được mong sửa trực tiếp bằng `Files.write(...)` hay `FileOutputStream`. Nếu ứng dụng cần cập nhật dữ liệu, hãy dùng file external, database, object storage hoặc cơ chế ghi phù hợp.

Kể cả khi IDE đang chạy từ một exploded directory và bạn có thể ghi resource trong `build/resources/main`, sửa file output này không đồng nghĩa thay đổi source `src/main/resources` và cũng không phải hành vi bền vững khi deploy.

## 13. Đọc nhiều tài nguyên bằng ResourcePatternResolver

Một số ứng dụng cần đọc nhiều file từ một thư mục logic trên classpath, chẳng hạn các file migration tự định nghĩa hoặc nhiều template được đóng gói trong các module.

`ResourcePatternResolver` hỗ trợ tìm resource theo pattern:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

public class BundledCsvReader {

    private final ResourcePatternResolver resolver =
            new PathMatchingResourcePatternResolver();

    public List<String> filenames() throws IOException {
        Resource[] resources =
                resolver.getResources("classpath*:data/*.csv");

        List<String> names = new ArrayList<>();

        for (Resource resource : resources) {
            names.add(resource.getFilename());
        }

        return names;
    }
}
~~~

Ở đây `classpath*:` cho phép tìm resource qua nhiều vị trí classpath, không chỉ một resource đầu tiên. Pattern có wildcard được xử lý theo cơ chế resource pattern resolution của Spring.

### 13.1. classpath: và classpath*: khác nhau

| Prefix | Ý nghĩa điển hình |
| --- | --- |
| `classpath:` | Tìm một resource trên classpath |
| `classpath*:` | Tìm tất cả resource khớp qua các vị trí classpath được hỗ trợ |

Ví dụ nhiều JAR có cùng tên resource:

~~~text
module-a.jar!/config/features.yml
module-b.jar!/config/features.yml
~~~

`classpath:config/features.yml` thường chỉ tìm một resource theo class loader resolution. `classpath*:config/features.yml` nhằm tìm nhiều tài nguyên khớp và trả về một mảng.

### 13.2. Không dựa vào thứ tự trả về

Khi đọc nhiều resource, thứ tự có thể phụ thuộc classpath, class loader và cách scan archive. Nếu thứ tự xử lý có ý nghĩa nghiệp vụ, hãy sắp xếp theo một khóa ổn định, chẳng hạn `getFilename()` hoặc metadata bên trong file, trước khi xử lý.

Không mặc định `Resource[]` được trả về theo thứ tự alphabet hay module dependency.

### 13.3. Wildcard và executable JAR

Spring có hỗ trợ pattern resolution cho classpath và JAR resources, nhưng chi tiết quét wildcard ở root và các loại archive/class loader có những giới hạn theo môi trường. Với bài toán cần bảo đảm thứ tự và danh sách file chính xác, một **manifest** liệt kê các tài nguyên đôi khi đáng tin cậy hơn wildcard scanning.

Ví dụ:

~~~text
data/files.txt
-----------
catalogs/electronics.csv
catalogs/books.csv
catalogs/games.csv
~~~

Bạn đọc manifest bằng stream, sau đó resolve từng tên tài nguyên rõ ràng. Cách này không phụ thuộc vào thứ tự scan tự nhiên và giúp phát hiện file thiếu.

Trong mọi trường hợp, đừng chuyển các `Resource` tìm được thành `File` nếu chúng nằm trong JAR; vẫn dùng `getInputStream()`.

## 14. Phân biệt ClassPathResource và InputStreamResource

Một điểm dễ nhầm là nghĩ mọi implementation của `Resource` đều có thể gọi `getInputStream()` nhiều lần.

`ClassPathResource` thông thường có khả năng mở một stream mới cho mỗi lần truy cập resource. Nhưng `InputStreamResource` bọc một stream **đã mở sẵn**, thường chỉ đọc được một lần.

Ví dụ:

~~~java
InputStream originalInput = new ByteArrayInputStream(
        "hello".getBytes(StandardCharsets.UTF_8)
);

Resource resource = new InputStreamResource(originalInput);
~~~

`InputStreamResource` không phải lựa chọn tốt để lưu trong singleton rồi đọc nhiều lần theo các request. Việc mở lại hoặc tính `contentLength()` có thể tiêu thụ stream và làm lần đọc sau thất bại.

Nếu dữ liệu đã nằm trong byte array và cần đọc lại nhiều lần, có thể dùng `ByteArrayResource`:

~~~java
byte[] data = "hello".getBytes(StandardCharsets.UTF_8);

Resource reusable = new ByteArrayResource(data);

try (InputStream first = reusable.getInputStream();
     InputStream second = reusable.getInputStream()) {
    // Hai stream riêng có thể đọc từ dữ liệu trong bộ nhớ.
}
~~~

Tuy nhiên, `ByteArrayResource` giữ toàn bộ byte array trong bộ nhớ. Với tài nguyên lớn, đọc lại từ resource gốc qua streaming thường tiết kiệm RAM hơn.

### 14.1. contentLength() có thể không vô hại

Với một số `Resource`, đặc biệt resource bao quanh stream chỉ đọc một lần, việc yêu cầu `contentLength()` có thể buộc implementation đọc stream để tính độ dài.

Do đó, tránh gọi `contentLength()` như thao tác kiểm tra “vô hại” với mọi Resource. Nếu biết kích thước từ metadata riêng, dùng metadata đó; nếu không, hãy xử lý stream và áp giới hạn dữ liệu thực tế theo từng byte đọc.

## 15. Dùng Resource trong HTTP response

Một controller đôi khi cần cho người dùng tải một file được đóng gói trong JAR. Thay vì tự gọi `getFile()`, Spring MVC có thể ghi nội dung từ `Resource` vào response.

Ví dụ endpoint tải một tài liệu cố định:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ManualController {

    @GetMapping("/manual")
    public ResponseEntity<Resource> download() {
        Resource manual =
                new ClassPathResource("documents/user-manual.pdf");

        if (!manual.exists()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename("user-manual.pdf")
                                .build()
                                .toString()
                )
                .body(manual);
    }
}
~~~

Ví dụ giả định file `src/main/resources/documents/user-manual.pdf` có trong artifact. Với Spring MVC auto-configuration thông thường, `ResourceHttpMessageConverter` có thể đọc resource và gửi nội dung.

Bạn không cần gọi `manual.getFile()` để trả response. Đặc biệt, nếu cần streaming tài nguyên lớn, hãy kiểm tra cách framework ghi response, cách đặt Content-Length, range request và cache header theo use case.

### 15.1. Tài nguyên tĩnh có thể không cần controller

Spring Boot MVC thường phục vụ tài nguyên tĩnh từ các vị trí classpath như:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
~~~

Ví dụ `src/main/resources/static/images/logo.png` thường có thể được truy cập qua `/images/logo.png` khi cấu hình static resource handling mặc định đang hoạt động.

Nếu bạn chỉ muốn phục vụ CSS, JavaScript hoặc ảnh tĩnh, hãy cân nhắc cơ chế static resource của Spring Boot trước khi viết controller đọc stream thủ công.

Không tự expose mọi path classpath theo tham số người dùng vì có thể làm lộ cấu hình hoặc tài nguyên nội bộ.

## 16. Test tài nguyên: vì sao unit test có thể bỏ sót lỗi getFile?

Các test thường chạy classpath dạng thư mục:

~~~text
build/classes/java/main/
build/resources/main/
build/classes/java/test/
build/resources/test/
~~~

Do vậy một test dùng:

~~~java
Resource resource = new ClassPathResource("data/catalog.json");
assertThat(resource.getFile()).exists();
~~~

có thể vượt qua trong IDE hoặc Gradle test, dù `getFile()` sẽ lỗi khi ứng dụng chạy từ executable JAR.

**Không dùng thành công của `getFile()` trong test classpath dạng thư mục để khẳng định resource trong JAR có đường dẫn file hợp lệ.** Đây là hai môi trường class loader khác nhau.

### 16.1. Unit test đọc resource theo InputStream

Một test JUnit 5 đơn giản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

class ClasspathResourceTest {

    @Test
    void readsTextFromClasspath() throws Exception {
        Resource resource =
                new ClassPathResource("templates/welcome.txt");

        try (InputStream input = resource.getInputStream()) {
            String text = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            assertThat(text).contains("Xin chào");
        }
    }
}
~~~

Test này không đòi `File` nên phù hợp hơn với thiết kế cần chạy cả trong IDE và JAR.

### 16.2. Test qua Spring context

Nếu service dùng `@Value` để inject `Resource`:

~~~java
@SpringBootTest
class WelcomeTemplateServiceTest {

    @Autowired
    private WelcomeTemplateService service;

    @Test
    void loadsBundledTemplate() throws Exception {
        String text = service.loadTemplate();
        assertThat(text).isNotBlank();
    }
}
~~~

Test dùng đúng dependency injection mechanism của ứng dụng. Nhưng test vẫn có thể chạy từ exploded classpath, nên nó chủ yếu kiểm tra việc resolve tên resource và đọc stream, không thay thế hoàn toàn kiểm tra packaged artifact.

### 16.3. Kiểm thử artifact đã đóng gói

Với một ứng dụng được phát hành dưới dạng executable JAR, có thể chạy artifact trong một môi trường kiểm thử gần production:

~~~bash
# Ví dụ sau khi artifact đã được build theo pipeline của dự án:
java -jar build/libs/demo-app.jar
~~~

Sau đó gọi endpoint hoặc workflow sử dụng resource. Nếu ứng dụng là CLI, tạo một `ApplicationRunner` hoặc command cụ thể để đọc resource theo luồng.

Điều cần xác nhận là resource thực sự được đóng gói trong JAR và việc đọc không phụ thuộc vào đường dẫn `src/main/resources` hoặc thư mục build trên máy phát triển.

Đừng viết test với một đường dẫn cố định `build/resources/main/...` chỉ vì nó tồn tại khi chạy IDE; đó không phải classpath resource location ổn định của artifact được deploy.

## 17. Kiểm tra tài nguyên có được đóng gói hay không

Nếu `getInputStream()` cũng thất bại, nguyên nhân có thể là tài nguyên không có trong classpath hoặc đường dẫn sai.

Kiểm tra cấu trúc project:

~~~text
src/main/resources/data/catalog.json
~~~

Kiểm tra code:

~~~java
Resource resource = new ClassPathResource("data/catalog.json");

if (!resource.exists()) {
    throw new IllegalStateException(
            "Missing resource: " + resource.getDescription()
    );
}
~~~

Trong pipeline build, có thể xem nội dung artifact sau khi đã build để xác nhận resource nằm trong JAR:

~~~bash
jar tf build/libs/demo-app.jar
~~~

Bạn có thể tìm:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Các lệnh trên là cách chẩn đoán thủ công khi phát triển/deploy. Không nên xây logic runtime dựa trên việc mở executable JAR và tự dò entry bằng path hard-coded.

### 17.1. Những lý do resource bị thiếu

- File đặt nhầm vào `src/test/resources` nên không có trong artifact production.
- Đường dẫn phân biệt hoa/thường khác nhau, đặc biệt khi chuyển từ Windows sang Linux.
- File bị loại bởi resource filtering hoặc cấu hình build.
- Resource nằm trong một module/JAR chưa được đưa vào runtime classpath.
- Code đang ghép sai prefix `classpath:` hoặc thêm thừa `src/main/resources`.
- Sử dụng `Class.getResourceAsStream` nhưng quên dấu slash đầu khi cần path từ root.
- Trong Docker, mount volume ghi đè một thư mục chứa external resource và làm mất file mong đợi.

Nếu classpath resource tồn tại trong JAR nhưng `getFile()` lỗi, đó không phải lỗi đóng gói. Đó là lỗi **chọn API không phù hợp**.

## 18. Ngoại lệ và cách xử lý lỗi hợp lý

Method `Resource.getInputStream()` có thể ném `IOException` khi resource không tồn tại hoặc không đọc được.

Tùy vai trò file, ứng dụng cần quyết định hành vi khi lỗi.

### 18.1. Resource bắt buộc

Với template cần có để ứng dụng hoạt động, có thể fail fast:

~~~java
@Component
public class RequiredTemplate {

    private final Resource resource =
            new ClassPathResource("templates/required.txt");

    @PostConstruct
    public void verify() throws IOException {
        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Required template is missing: "
                            + resource.getDescription()
            );
        }

        try (InputStream input = resource.getInputStream()) {
            // Có thể kiểm tra header hoặc parse dữ liệu thiết yếu.
            input.read();
        }
    }
}
~~~

Ví dụ này yêu cầu imports tương ứng của `Component`, `PostConstruct`, `Resource` và `InputStream`. Trong ứng dụng thật, nếu cần parse toàn bộ dữ liệu khi khởi động, hãy cân nhắc cache kết quả đã parse thay vì chỉ đọc một byte ở bước verify rồi đọc lại nhiều lần.

### 18.2. Resource tùy chọn

Với file tùy chọn, có thể có fallback:

~~~java
public String loadOptionalText(Resource resource) throws IOException {
    if (!resource.exists()) {
        return "";
    }

    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Chỉ dùng default rỗng nếu điều đó có ý nghĩa nghiệp vụ. Đừng im lặng bỏ qua lỗi đọc một file bắt buộc hoặc file chứa cấu hình bảo mật.

### 18.3. Không che IOException bằng null vô điều kiện

Sai:

~~~java
try {
    return new String(resource.getInputStream().readAllBytes(), UTF_8);
} catch (Exception exception) {
    return null;
}
~~~

Đoạn này vừa không đóng stream, vừa che mọi lỗi thành null. Consumer sau đó có thể gặp `NullPointerException` ở nơi xa nguyên nhân thật.

Tốt hơn là để `IOException` đi lên hoặc chuyển nó thành exception domain có thông tin resource location mà không làm lộ dữ liệu nhạy cảm:

~~~java
public String requireText(Resource resource) {
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException exception) {
        throw new IllegalStateException(
                "Cannot read required resource: "
                        + resource.getDescription(),
                exception
        );
    }
}
~~~

## 19. Bảo mật khi đọc tài nguyên

Classpath resource thường là dữ liệu do chính developer đóng gói và ít thay đổi. Nhưng location có thể đến từ property, HTTP parameter hoặc message. Khi đó cần xem nó là đầu vào có thể gây hại nếu không kiểm soát.

### 19.1. Không dùng path do người dùng nhập để đọc bất kỳ file nào

Ví dụ nguy hiểm:

~~~java
@GetMapping("/read")
public String read(@RequestParam String path) throws IOException {
    Resource resource = resourceLoader.getResource(path);
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Nếu người dùng tự chọn được location như `file:` hoặc URL khác, endpoint có thể cho phép truy cập dữ liệu ngoài phạm vi mong muốn, bao gồm file hệ thống hoặc truy cập mạng theo quyền của server.

Thay vào đó, giới hạn một tập resource được phép:

~~~java
private static final Map<String, String> ALLOWED_TEMPLATES = Map.of(
        "welcome", "classpath:templates/welcome.txt",
        "receipt", "classpath:templates/receipt.txt"
);
~~~

Chỉ dùng location lấy từ map đã định nghĩa. Với external paths, cần validate và chuẩn hóa path, ngăn traversal/symlink escape theo yêu cầu bảo mật.

### 19.2. Không đọc vô hạn vào RAM

Một resource do người dùng kiểm soát có thể rất lớn. Nếu gọi `readAllBytes()` hoặc `ByteArrayOutputStream` không có giới hạn, request có thể tiêu tốn bộ nhớ và làm ứng dụng mất ổn định.

Với dữ liệu không tin cậy hoặc lớn, ưu tiên stream kèm giới hạn số byte, timeout nếu đọc mạng và backpressure/cancellation theo framework đang dùng.

### 19.3. Không log nội dung bí mật

`getDescription()` có thể hữu ích cho thông báo lỗi, nhưng một số resource location có thể chứa query parameter hoặc thông tin nhạy cảm. Hãy lọc và giảm log thông tin trước khi đưa vào hệ thống quan sát tập trung.

Không log toàn bộ byte hoặc nội dung các file cấu hình chứa secret chỉ để chẩn đoán lỗi `getFile()`.

## 20. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân chính | Cách khắc phục |
| --- | --- | --- |
| Chạy IDE được, `java -jar` lỗi `getFile()` | Classpath resource giờ là JAR entry | Đọc bằng `getInputStream()` |
| `FileNotFoundException` nói không nằm trong file system | Resource tồn tại nhưng không có file path vật lý | Không gọi `getFile()`; dùng stream |
| `resource.exists()` true nhưng `getFile()` thất bại | Tồn tại logic khác biểu diễn dưới dạng `File` | Xác định vị trí resource và API cần dùng |
| `ClassLoader.getResourceAsStream` trả null | Sai path hoặc file không có trong runtime classpath | Kiểm tra root path, resource packaging và case |
| `new ClassPathResource("src/main/resources/...")` không tìm thấy | Dùng path source thay vì classpath path | Bỏ phần `src/main/resources/` |
| `Path.of(resource.getURI())` lỗi với `jar:` URI | URI không phải filesystem path | Dùng resource stream |
| Không parse được JSON/CSV | Charset hoặc parser không đúng | Dùng UTF-8 và thư viện parser phù hợp |
| File nhị phân hỏng sau khi đọc | Đã chuyển byte thành text | Giữ byte/stream, không giải mã thành String |
| Resource read lại bị lỗi | Dùng `InputStreamResource` một lần hoặc stream đã đóng | Dùng resource có thể mở lại hoặc quản lý stream đúng vòng đời |
| `contentLength()` làm stream không còn đọc được | Resource một lần có thể bị consume | Không gọi method này tùy tiện với one-shot stream |
| Parser chỉ nhận `File` | API thư viện không hỗ trợ InputStream | Copy sang temp file, quản lý lifecycle và xóa sau khi dùng |
| Không tìm thấy file trong production | File chỉ có trong test resources hoặc không nằm trong artifact | Kiểm tra build resource packaging |
| Sai tên trên Linux nhưng đúng Windows | Khác chữ hoa/thường | Dùng path đúng case |
| Đọc file ngoài JAR không được | Sai quyền filesystem hoặc volume mount | Kiểm tra quyền, mount và đường dẫn |
| File classpath bị sửa nhưng deploy không thay đổi | Resource đã được đóng gói trong artifact cũ | Rebuild/redeploy hoặc dùng external config |
| Quét classpath wildcard thiếu file | Class loader/pattern/archive scanning khác nhau | Test packaged artifact hoặc dùng manifest tường minh |

### 20.1. Quy trình chẩn đoán nhanh

Khi gặp lỗi tài nguyên trong ứng dụng Spring Boot:

1. Xác nhận file được lưu trong `src/main/resources` hoặc dependency JAR tương ứng.
2. Kiểm tra tên resource **tương đối với classpath root**, không dùng đường dẫn project.
3. Xem code có gọi `getFile()`, `getURI()` để tạo `Path` hoặc `FileInputStream` không.
4. Nếu chỉ cần đọc, chuyển sang `Resource.getInputStream()`.
5. Nếu thư viện cần `File` thật, kiểm tra overload nhận stream trước; nếu không có, copy sang file tạm và cleanup.
6. Kiểm tra encoding/format và bảo đảm stream được đóng.
7. Chạy trong môi trường đóng gói gần production để phát hiện khác biệt giữa exploded classes và JAR.
8. Nếu vẫn lỗi, kiểm tra artifact có đóng gói resource, runtime classpath, quyền đọc và case của đường dẫn.

## 21. Chọn API phù hợp với nhu cầu

| Nhu cầu | Giải pháp nên chọn | Có cần getFile()? |
| --- | --- | --- |
| Đọc text nhỏ từ JAR | `Resource.getInputStream()` + UTF-8 | Không |
| Parse JSON đóng gói | `ObjectMapper.readValue(InputStream, ...)` | Không |
| Đọc CSV theo dòng | `InputStreamReader` + CSV parser | Không |
| Stream PDF/ảnh | `InputStream.transferTo(OutputStream)` | Không |
| Trả resource qua Spring MVC | `ResponseEntity<Resource>` hoặc static resource handling | Không |
| Tải resource từ nhiều location | `ResourceLoader` | Không |
| Scan nhiều classpath resources | `ResourcePatternResolver` | Không |
| Đọc/ghi external file có path thật | `Files` / `FileSystemResource` | Có thể dùng |
| Thư viện cũ chỉ nhận File | Copy resource sang temporary file | Chỉ trên file tạm |
| Cấu hình runtime có thể thay đổi | File external/database/object storage | Không dựa vào JAR |
| Lưu cache nội dung nhỏ đã parse | Parse một lần rồi giữ immutable object | Không |

Một câu hỏi hữu ích trước khi chọn API: **mình cần dữ liệu bên trong resource hay thực sự cần một file path của hệ điều hành?** Nếu chỉ cần dữ liệu, `InputStream` là abstraction phù hợp hơn.

## 22. Bài tập thực hành

### Bài tập 1 — Đọc text trong IDE và JAR

Tạo `src/main/resources/templates/welcome.txt`. Viết một service đọc file bằng `ClassPathResource.getInputStream()` và `UTF_8`. Gọi service khi chạy bằng IDE và khi chạy packaged JAR. So sánh kết quả.

### Bài tập 2 — Tái hiện lỗi getFile

Viết một method dùng `new ClassPathResource("templates/welcome.txt").getFile()`. Quan sát hành vi khi chạy từ exploded classpath. Sau đó chạy từ executable JAR và giải thích vì sao `getFile()` không thể cung cấp đường dẫn vật lý.

### Bài tập 3 — JSON bằng Jackson

Thêm `data/catalog.json` và một record Java tương ứng. Dùng `ObjectMapper.readValue(InputStream, Catalog.class)`. Viết test kiểm tra số lượng phần tử sau khi parse.

### Bài tập 4 — Streaming dữ liệu nhị phân

Thêm một ảnh nhỏ dưới `images/logo.png`. Viết method nhận `OutputStream`, dùng `InputStream.transferTo` để copy byte. Tính checksum hoặc so sánh dữ liệu byte trước/sau, không chuyển thành String.

### Bài tập 5 — External override

Cấu hình một property resource location mặc định là `classpath:templates/welcome.txt`. Thay property bằng `file:/opt/app/templates/custom.txt` trong môi trường test có file tương ứng. Xác nhận service không cần sửa code để chuyển nguồn.

### Bài tập 6 — SDK nhận File

Giả lập một parser chỉ nhận `File`. Viết adapter copy classpath resource ra `Files.createTempFile`, truyền vào parser, rồi xóa trong `finally`. Giải thích cách xử lý nếu parser chạy bất đồng bộ.

### Bài tập 7 — Đọc nhiều CSV

Tạo hai file `data/one.csv` và `data/two.csv`. Dùng `ResourcePatternResolver.getResources("classpath*:data/*.csv")` để tìm chúng. Xử lý từng resource qua `getInputStream()` và sắp xếp theo filename trước khi dùng.

### Bài tập 8 — Xác nhận lifecycle của stream

Tạo một method đọc resource bằng `try-with-resources` và một method cố lưu stream vào field singleton. So sánh cách quản lý close/reopen và giải thích vì sao giữ `Resource` thường an toàn hơn giữ stream đã mở.

### Bài tập 9 — Kiểm thử packaged artifact

Thêm test đọc resource bằng stream. Sau đó trong pipeline kiểm thử đóng gói, chạy ứng dụng từ executable JAR và gọi workflow sử dụng resource. Xác nhận không còn phụ thuộc vào `build/resources/main` hoặc `src/main/resources`.

## 23. Ghi nhớ

`Resource` là abstraction của Spring cho nhiều loại vị trí dữ liệu. `ClassPathResource` giúp tìm tài nguyên bằng tên trên classpath nhưng **không cam kết có file vật lý**. Khi chạy trong IDE, resource có thể nằm trong thư mục và `getFile()` tình cờ hoạt động. Sau khi đóng gói thành executable JAR, cùng resource thường là một JAR entry nên `getFile()` có thể ném `FileNotFoundException` dù `exists()` vẫn true.

Nếu chỉ muốn đọc nội dung, dùng **`Resource.getInputStream()`**, đóng stream bằng `try-with-resources` và chọn cách xử lý dữ liệu thích hợp: `UTF-8` cho text, parser nhận stream cho JSON/CSV, byte stream cho PDF và ảnh. Đừng tự chuyển `jar:` URL/URI thành filesystem path, và không dùng `readAllBytes()` cho dữ liệu lớn không kiểm soát.

Khi một thư viện thật sự yêu cầu `File` hoặc `Path`, hãy ưu tiên overload nhận stream hoặc copy resource sang temporary file và quản lý việc xóa theo đúng lifecycle. Với file cần chỉnh sửa ở runtime, dùng external filesystem/config location thay vì resource bên trong JAR.

Thiết kế dựa trên stream không chỉ sửa lỗi deployment: nó còn làm code ít phụ thuộc cách đóng gói, dễ kiểm thử và tương thích hơn với class loader, dependency JAR và môi trường container.
