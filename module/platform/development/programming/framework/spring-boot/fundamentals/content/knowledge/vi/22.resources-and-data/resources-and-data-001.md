# Resource, ResourceLoader và các tiền tố classpath, file, URL

Trong ứng dụng Spring Boot, không phải mọi dữ liệu đều đến từ database hoặc HTTP request. Ứng dụng còn có thể cần đọc một mẫu email, tệp JSON dùng làm dữ liệu khởi tạo, chứng chỉ được mount vào container, file CSV do bên vận hành cung cấp, hoặc một nội dung có địa chỉ URL. Những nguồn đó có vị trí lưu trữ khác nhau, nhưng chương trình thường chỉ cần thao tác cơ bản: **xác định tài nguyên, kiểm tra khả năng đọc và mở luồng dữ liệu**.

Spring Framework cung cấp hai abstraction quan trọng:

- **`Resource`**: đại diện cho một tài nguyên có thể truy cập được, bất kể nó nằm trong classpath, hệ thống file hay ở một URL.
- **`ResourceLoader`**: nhận một chuỗi mô tả vị trí và tạo ra đối tượng `Resource` phù hợp.

Trong **Spring Boot Fundamentals → Tài nguyên và dữ liệu**, điều cần nắm vững không chỉ là cách viết `classpath:`, `file:` hoặc `https:`, mà còn là cách chúng ảnh hưởng đến việc đóng gói JAR, triển khai container, vòng đời của `InputStream` và bảo mật khi đường dẫn đến từ cấu hình.

## 1. Vì sao không nên luôn dùng java.io.File?

Giả sử ta muốn nạp nội dung từ `src/main/resources/templates/welcome.txt`. Khi chạy ứng dụng trong IDE, file đó tồn tại trong cây thư mục dự án nên đoạn code sau có vẻ hợp lý:

~~~java
File file = new File("src/main/resources/templates/welcome.txt");
String text = Files.readString(file.toPath());
~~~

Nhưng khi đóng gói thành executable JAR, đường dẫn `src/main/resources/...` không còn là một đường dẫn runtime đáng tin cậy. Tài nguyên được copy vào output classpath và thường nằm **bên trong file JAR**. File bên trong archive không nhất thiết có một `java.io.File` tương ứng trên hệ thống file.

Vì vậy, đoạn code dựa trên đường dẫn source có thể chạy ở IDE nhưng lỗi sau khi deploy:

~~~text
Môi trường phát triển:
  project/src/main/resources/templates/welcome.txt
       |
       +-- build tool copy vào classpath

Môi trường chạy:
  application.jar
       |
       +-- BOOT-INF/classes/templates/welcome.txt
             (mục bên trong archive, không phải file độc lập)
~~~

Hướng tiếp cận tốt hơn là mô tả **vị trí logic**:

~~~text
classpath:templates/welcome.txt
~~~

Sau đó yêu cầu Spring đọc nó bằng `Resource` hoặc `ResourceLoader`. Ứng dụng không còn phải tự đoán đường dẫn vật lý trong từng môi trường.

### Phân biệt “resource” và “file”

Một resource có thể là:

- File thực sự trên ổ đĩa.
- Entry bên trong JAR.
- Nội dung truy cập qua HTTP/HTTPS.
- Một đối tượng byte array hoặc input stream do ứng dụng tạo.
- Tài nguyên trong một ngữ cảnh ứng dụng đặc biệt.

Trong khi đó, `java.io.File` chỉ mô tả vị trí trong hệ thống file của máy đang chạy. Vì thế, **mọi file có thể được biểu diễn bằng resource, nhưng không phải mọi resource đều là file vật lý**.

## 2. Resource là gì?

Interface `org.springframework.core.io.Resource` biểu diễn tài nguyên và kế thừa các khả năng cơ bản của `InputStreamSource`.

Những phương thức thường dùng:

| Phương thức | Ý nghĩa | Lưu ý |
|---|---|---|
| `getInputStream()` | Mở luồng đọc dữ liệu | Đóng stream sau khi dùng; có thể ném `IOException` |
| `exists()` | Kiểm tra resource có vẻ tồn tại | Không bảo đảm lần đọc sau chắc chắn thành công |
| `isReadable()` | Kiểm tra resource được coi là đọc được | Kết quả có thể phụ thuộc loại resource |
| `getDescription()` | Chuỗi mô tả resource, tiện cho log | Không nhất thiết là đường dẫn filesystem |
| `getFilename()` | Tên file nếu có thể xác định | Có thể `null` |
| `getURL()` / `getURI()` | Biểu diễn dưới dạng URL/URI nếu hỗ trợ | Không có nghĩa đó là file vật lý |
| `getFile()` | Cố lấy `java.io.File` | Không dùng cho resource nằm trong JAR hoặc qua HTTP |
| `contentLength()` | Kích thước nội dung nếu có thể xác định | Có thể tốn I/O hoặc không khả dụng |
| `lastModified()` | Mốc sửa đổi nếu lấy được | Không nên dựa vào như metadata luôn tồn tại |

Mục tiêu của abstraction là dùng chung giao diện, không ép mọi nguồn có cùng khả năng.

Ví dụ một hàm đọc UTF-8:

~~~java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;

public final class ResourceTextReader {

    private ResourceTextReader() {
    }

    public static String readSmallUtf8(Resource resource)
            throws IOException {

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

**Vì sao dùng `getInputStream()` thay vì `getFile()`?** Vì luồng đọc áp dụng được cho nhiều loại nguồn: file, classpath entry trong JAR và URL. Đó là lựa chọn mặc định tốt khi chỉ cần đọc nội dung.

Lưu ý `readAllBytes()` chỉ thích hợp cho nội dung nhỏ hoặc có giới hạn kích thước rõ ràng. Với file lớn, cần xử lý streaming, giới hạn dữ liệu và quản lý bộ nhớ.

## 3. ResourceLoader là gì?

`org.springframework.core.io.ResourceLoader` là giao diện tải tài nguyên theo chuỗi vị trí. Phương thức quan trọng là:

~~~java
Resource getResource(String location);
~~~

Ví dụ:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:templates/welcome.txt"
);
~~~

Tham số `location` có thể là:

- Địa chỉ có tiền tố `classpath:`.
- Đường dẫn có tiền tố `file:`.
- URL có scheme hợp lệ như `https:`.
- Chuỗi không có scheme; cách giải thích phụ thuộc implementation và context.

`ResourceLoader` chỉ **giải quyết vị trí thành Resource**; phần lớn trường hợp lời gọi `getResource(...)` chưa đọc toàn bộ nội dung. Thao tác I/O thực tế thường diễn ra khi gọi `getInputStream()`, `exists()` hoặc những phương thức tương tự.

### ResourceLoader trong Spring Boot

`ApplicationContext` của Spring có khả năng hoạt động như một `ResourceLoader`. Trong ứng dụng Boot, ta có thể inject giao diện này vào một bean:

~~~java
package com.example.resources;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class DocumentLocator {

    private final ResourceLoader resourceLoader;

    public DocumentLocator(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource locate(String location) {
        return resourceLoader.getResource(location);
    }
}
~~~

Service không cần biết ứng dụng đang chạy bằng IDE, executable JAR hay container. Người gọi truyền vào location phù hợp, và service trả về một `Resource`.

Tuy nhiên, **không nên truyền location trực tiếp từ input không đáng tin cậy của người dùng**. Các scheme như `file:` và `https:` có thể khiến service đọc file nhạy cảm hoặc gọi ra mạng ngoài. Phần bảo mật sẽ được trình bày ở mục sau.

## 4. Bảng quy tắc: classpath:, file:, URL

Ba nhóm vị trí phổ biến nhất:

| Ví dụ location | Nơi tìm tài nguyên | Khi nào dùng |
|---|---|---|
| `classpath:templates/welcome.txt` | Classpath của ứng dụng | Tài nguyên đóng gói cùng code/JAR |
| `file:/opt/app/config/rules.json` | Hệ thống file của process | File bên ngoài artifact, thường mount vào container |
| `file:///opt/app/config/rules.json` | Hệ thống file, dùng file URI dạng đầy đủ | Khi đường dẫn tuyệt đối cần biểu diễn rõ |
| `https://example.org/assets/catalog.json` | Tài nguyên qua HTTP(S) | Dữ liệu ở endpoint ngoài, khi đã kiểm soát truy cập và rủi ro |
| `templates/welcome.txt` | Phụ thuộc ResourceLoader/context | Dễ gây hiểu nhầm; nên dùng tiền tố tường minh |

Có thể hình dung:

~~~text
ResourceLoader.getResource(location)
                   |
        +----------+-----------+
        |          |           |
   classpath:     file:       https:
        |          |           |
        v          v           v
 ClassPath      Local FS      Remote URL
 resource       resource      resource
        \          |           /
         \         |          /
          +--------+---------+
                   |
                   v
           Resource abstraction
                   |
                   v
            getInputStream()
                   |
                   v
            Đọc dữ liệu
~~~

Đối với người viết service, điều quan trọng là **code tiêu thụ dữ liệu có thể làm việc với `Resource`**, trong khi nơi lấy dữ liệu được quyết định bởi location và cấu hình.

## 5. Tiền tố classpath:

`classpath:` chỉ định tài nguyên trên classpath của Java application.

Ví dụ:

~~~text
classpath:templates/welcome.txt
classpath:data/countries.json
classpath:config/default-rules.yml
~~~

Trong dự án Maven hoặc Gradle dùng cấu trúc chuẩn, tài nguyên ứng dụng thường đặt ở:

~~~text
src/
  main/
    java/
      com/example/DemoApplication.java
    resources/
      templates/welcome.txt
      data/countries.json
      config/default-rules.yml
~~~

Khi build, các file trong `src/main/resources` được đưa vào runtime classpath. Vì vậy chúng có thể được truy cập bằng `classpath:data/countries.json`, bất kể đường dẫn source nằm ở đâu.

### Ví dụ đọc classpath resource

File `src/main/resources/demo/greeting.txt`:

~~~text
Xin chào từ tài nguyên classpath!
~~~

Code:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource resource = new ClassPathResource("demo/greeting.txt");

try (InputStream input = resource.getInputStream()) {
    String message = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
    System.out.println(message);
}
~~~

`ClassPathResource` là một implementation cụ thể của `Resource`. Nó hữu ích khi nguồn được biết chắc là classpath và không cần thay đổi bằng cấu hình.

Nếu muốn location linh hoạt, dùng:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:demo/greeting.txt"
);
~~~

Cách thứ hai có ưu điểm cho phép sau này đổi nguồn mà không sửa logic tiêu thụ tài nguyên.

### Dấu gạch chéo đầu đường dẫn

Thông thường, đối với location `classpath:`, tài nguyên được hiểu từ **gốc classpath**:

~~~text
classpath:demo/greeting.txt
~~~

Một số API có thể chấp nhận cả dạng `classpath:/demo/greeting.txt`, nhưng sử dụng dạng không có dấu `/` dư sau prefix giúp ví dụ dễ hiểu.

Khác với đường dẫn filesystem, `demo/greeting.txt` ở đây không có nghĩa tương đối với working directory của process Java.

## 6. Runtime classpath và executable JAR

Một khác biệt quan trọng giữa chạy trong IDE và chạy JAR là cách tài nguyên được lưu trữ.

Trong IDE, file `demo/greeting.txt` có thể tồn tại dưới dạng một file bình thường trong thư mục output:

~~~text
build/resources/main/demo/greeting.txt
~~~

Khi đóng gói Spring Boot executable JAR, resource thường được đưa vào:

~~~text
app.jar
  |
  +-- BOOT-INF/classes/
        |
        +-- demo/greeting.txt
~~~

Ở thời điểm chạy:

~~~bash
java -jar app.jar
~~~

`ClassPathResource` có thể đọc resource trong JAR qua `getInputStream()`. Nhưng một lời gọi như sau **không an toàn về tính di động**:

~~~java
Resource resource = new ClassPathResource("demo/greeting.txt");

File file = resource.getFile(); // Có thể lỗi khi file nằm trong JAR
~~~

Vì `getFile()` cần một file thực trên hệ thống file, còn entry bên trong JAR không phải một file độc lập.

Cách đúng khi chỉ đọc:

~~~java
try (InputStream stream = resource.getInputStream()) {
    // Đọc, parse hoặc copy dữ liệu từ stream.
}
~~~

Nếu một thư viện bên thứ ba bắt buộc nhận `Path` hoặc `File`, có thể cần copy nội dung ra một **temporary file** do ứng dụng quản lý. Khi đó cần xử lý việc đóng stream, giới hạn kích thước, phân quyền thư mục tạm và dọn dẹp file sau khi dùng. Không nên mặc định Spring sẽ tự giải nén cả archive chỉ để tạo file tương ứng.

### classpath resource thường nên là nội dung chỉ đọc

Các tài nguyên đóng gói trong JAR thích hợp làm mẫu, dữ liệu mặc định hoặc tài liệu tĩnh. Việc sửa nội dung runtime bên trong executable JAR không phải một chiến lược cấu hình hay lưu trữ dữ liệu hợp lý.

Nếu nội dung cần chỉnh sửa mà không build lại, hãy chuyển sang file bên ngoài với `file:`, một dịch vụ cấu hình hoặc kho lưu trữ phù hợp.

## 7. Tiền tố file:

`file:` mô tả tài nguyên trên hệ thống file mà process Java có quyền truy cập.

Ví dụ trên Linux:

~~~text
file:/opt/app/config/rules.json
file:///opt/app/config/rules.json
~~~

Dạng URI đầy đủ với ba dấu gạch chéo giúp thể hiện rõ đường dẫn tuyệt đối ở một số ngữ cảnh:

~~~text
file:///opt/app/config/rules.json
    ^^^
    scheme + đường dẫn tuyệt đối
~~~

Trên Windows, một file URI có thể có dạng:

~~~text
file:///C:/apps/demo/config/rules.json
~~~

Đường dẫn phải phản ánh filesystem **của máy hoặc container đang chạy Java**, không phải filesystem của máy phát triển nếu hai môi trường khác nhau.

### Ví dụ đọc file ngoài JAR

Giả sử file có nội dung:

~~~json
{
  "mode": "safe",
  "maxItems": 100
}
~~~

Nó được mount tại `/opt/app/config/rules.json`.

Code:

~~~java
Resource resource = resourceLoader.getResource(
        "file:/opt/app/config/rules.json"
);

try (InputStream input = resource.getInputStream()) {
    // Truyền stream vào parser JSON của ứng dụng.
}
~~~

Code chỉ cần quyền đọc file; không yêu cầu file phải nằm trong JAR.

### Cẩn trọng với đường dẫn tương đối

Những location như:

~~~text
file:./config/rules.json
file:config/rules.json
~~~

có thể phụ thuộc vào working directory, cách xử lý URI/URL và implementation. Chúng dễ hoạt động khác giữa IDE, script chạy JAR, container và service manager.

Khi cần cấu hình file bên ngoài trong môi trường triển khai, **ưu tiên đường dẫn tuyệt đối rõ ràng**:

~~~text
file:/opt/app/config/rules.json
~~~

Nếu thật sự cần đường dẫn tương đối, phải chủ động xác định working directory và viết tài liệu triển khai tương ứng.

### FileSystemResource cho đường dẫn đã biết

Khi đã có một `Path` trong Java, không nhất thiết phải chuyển nó thành chuỗi location:

~~~java
import java.nio.file.Path;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Path path = Path.of("/opt/app/config/rules.json");
Resource resource = new FileSystemResource(path);
~~~

`FileSystemResource` làm việc với file/path cụ thể. Cách này thuận tiện khi ứng dụng đã nhận một đường dẫn đã được kiểm tra và xử lý bằng Java NIO.

## 8. Tiền tố URL: http: và https:

Một location có URL scheme hợp lệ như:

~~~text
https://example.org/resources/pricing.json
http://localhost:8081/sample.txt
~~~

có thể được `ResourceLoader` biểu diễn bằng tài nguyên kiểu URL, thường là `UrlResource` hoặc implementation phù hợp với loader.

Ví dụ:

~~~java
Resource resource = resourceLoader.getResource(
        "https://example.org/resources/pricing.json"
);

try (InputStream input = resource.getInputStream()) {
    // Đọc nội dung được lấy qua kết nối tới URL.
}
~~~

Khi gọi `getInputStream()` trên remote resource, thao tác có thể cần kết nối mạng và có thể thất bại do DNS, TLS, timeout, HTTP status hoặc điều kiện mạng.

### Resource URL không phải HTTP client đa năng

`Resource` thích hợp khi ý định chính là **đọc nội dung từ một vị trí trừu tượng**. Nó không thay thế một HTTP client chuyên dụng khi cần:

- Authentication phức tạp và tự động gia hạn token.
- Timeout, retry, circuit breaker và điều khiển connection pool cụ thể.
- API có phương thức POST/PUT/PATCH/DELETE.
- Request headers hoặc response headers nghiệp vụ.
- Xử lý status code, pagination và rate limiting.
- Streaming với giới hạn dung lượng và chống treo kết nối.

Trong các tình huống đó, nên dùng HTTP client tương ứng trong Spring (chẳng hạn `RestClient` hoặc `WebClient` nếu phù hợp), hay thư viện HTTP có khả năng quản lý chính sách mạng rõ ràng.

**Không dùng `ResourceLoader.getResource(userInput)` như một trình đọc URL không giới hạn.** Để người dùng điều khiển tùy ý location có thể tạo rủi ro SSRF hoặc đọc file nội bộ; ứng dụng cần kiểm soát nguồn hợp lệ.

## 9. Khi location không có tiền tố thì sao?

Ví dụ:

~~~java
Resource resource = resourceLoader.getResource(
        "demo/greeting.txt"
);
~~~

Đây không phải một cách chỉ rõ nguồn. Kết quả **phụ thuộc implementation của `ResourceLoader` và loại context**.

Có loader hiểu một đường dẫn không có prefix như đường dẫn trong classpath; có ngữ cảnh web dùng cách giải quyết resource riêng. Không nên xem một chuỗi không có scheme như một chuẩn xuyên mọi implementation.

Để code dễ đọc và nhất quán, hãy chọn một trong các dạng tường minh:

~~~text
classpath:demo/greeting.txt
file:/opt/app/demo/greeting.txt
https://example.org/demo/greeting.txt
~~~

Nếu không muốn lặp lại prefix trong code, có thể giữ location đầy đủ trong cấu hình và truyền vào service, thay vì bỏ scheme.

## 10. Ví dụ Spring Boot hoàn chỉnh: một service đọc tài nguyên

Ta tạo một ứng dụng nhỏ có thể thay đổi nơi lấy văn bản chỉ bằng cấu hình.

### 10.1. Tạo file trong resources

Đặt file tại:

~~~text
src/main/resources/demo/message.txt
~~~

Nội dung:

~~~text
Đây là thông điệp mặc định được đóng gói cùng Spring Boot.
~~~

### 10.2. Cấu hình location

Trong `src/main/resources/application.properties`:

~~~properties
app.message.location=classpath:demo/message.txt
~~~

Tên property do ứng dụng tự quy định; Spring Boot không có sẵn property `app.message.location` với ý nghĩa đặc biệt.

### 10.3. Service đọc Resource

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class MessageResourceService {

    private final ResourceLoader resourceLoader;

    public MessageResourceService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String readMessage(String location) throws IOException {
        Resource resource = resourceLoader.getResource(location);

        try (InputStream stream = resource.getInputStream()) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Phương thức `readMessage(...)`:

1. Nhận location đã được cấu hình.
2. Gọi loader để tạo resource.
3. Mở input stream.
4. Đọc văn bản theo UTF-8.
5. Đóng input stream nhờ try-with-resources.

Đây là ví dụ dành cho file văn bản nhỏ. Khi thao tác với dữ liệu lớn hoặc nguồn bên ngoài không đáng tin cậy, cần stream theo chunk và giới hạn dung lượng.

### 10.4. Chạy ở startup bằng ApplicationRunner

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MessageConfiguration {

    @Bean
    ApplicationRunner showMessage(
            MessageResourceService service,
            @Value("${app.message.location}") String location
    ) {
        return args -> System.out.println(
                service.readMessage(location)
        );
    }
}
~~~

Ở đây `@Value` chỉ đọc một property location để đưa vào service. Vì service nhận chuỗi location có prefix nên nó có thể truy cập nhiều loại resource khác nhau mà không thay đổi logic.

Khi khởi động, ứng dụng đọc nội dung:

~~~text
Đây là thông điệp mặc định được đóng gói cùng Spring Boot.
~~~

### 10.5. Đổi sang file ngoài JAR

Tạo file ngoài JAR, ví dụ `/opt/app/config/message.txt`, rồi chạy:

~~~bash
java -jar app.jar --app.message.location=file:/opt/app/config/message.txt
~~~

Lúc này **cùng một service Java** đọc dữ liệu từ filesystem thay vì từ classpath.

### 10.6. Đổi sang URL

Trong môi trường demo có một endpoint HTTPS tin cậy:

~~~bash
java -jar app.jar --app.message.location=https://example.org/demo/message.txt
~~~

Service cũng có thể đọc qua URL resource nếu endpoint tồn tại và có thể truy cập. Vì đây là nguồn mạng, ứng dụng thực tế phải kiểm soát timeout, nội dung, kích thước và danh sách host được phép.

Ví dụ dùng tên miền minh họa; không mặc định rằng đường dẫn `https://example.org/demo/message.txt` là endpoint có dữ liệu thật.

## 11. Resource injection trực tiếp qua @Value

Nếu location cố định hoặc chỉ có một thuộc tính, Spring có thể inject một đối tượng `Resource` qua `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class WelcomeTemplate {

    private final Resource template;

    public WelcomeTemplate(
            @Value("classpath:demo/message.txt") Resource template
    ) {
        this.template = template;
    }

    public Resource getTemplate() {
        return template;
    }
}
~~~

Ở đây Spring chuyển chuỗi location trong annotation thành `Resource` phù hợp.

Có thể dùng một property placeholder để chọn location:

~~~java
public WelcomeTemplate(
        @Value("${app.message.location:classpath:demo/message.txt}")
        Resource template
) {
    this.template = template;
}
~~~

Điểm đáng chú ý:

- Giá trị trước dấu `:` trong placeholder là tên property `app.message.location`.
- Phần `classpath:demo/message.txt` là fallback nếu property không có.
- Spring đọc location và inject `Resource`.
- Khi bean nhận resource, **không có nghĩa nội dung đã được đọc đầy đủ**; việc đọc thường xảy ra khi gọi `getInputStream()`.

Khi có nhiều nhóm cấu hình, sử dụng `@ConfigurationProperties` để tổ chức property tốt hơn. Tuy nhiên, ý nghĩa của location vẫn không đổi: nó mô tả nơi tài nguyên sẽ được truy cập.

## 12. Tạo Resource không nhất thiết là tải nội dung

Một nhầm lẫn phổ biến là nghĩ:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:missing-file.txt"
);
~~~

sẽ lập tức ném lỗi nếu file không tồn tại. Trên thực tế, **getResource thường chỉ tạo đối tượng mô tả vị trí**, chưa bắt buộc mở stream.

Ví dụ:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:missing-file.txt"
);

System.out.println(resource.exists());
~~~

`exists()` có thể trả về `false`; khi gọi `getInputStream()` có thể xuất hiện `FileNotFoundException` hoặc loại `IOException` phù hợp.

Vì vậy, code tiêu thụ resource cần xử lý lỗi I/O đúng chỗ:

~~~java
try (InputStream stream = resource.getInputStream()) {
    // Xử lý dữ liệu.
} catch (IOException exception) {
    // Log bối cảnh rồi xử lý theo chính sách ứng dụng.
}
~~~

### exists() không thay thế try/catch

Ngay cả khi `exists()` trả về true, file vẫn có thể bị xóa, quyền truy cập bị thay đổi hoặc kết nối mạng bị gián đoạn trước lúc đọc. Đây là một dạng time-of-check/time-of-use.

Nên dùng `exists()` khi muốn đưa ra thông báo thân thiện hoặc quyết định nhánh xử lý, nhưng không dùng nó để bỏ qua xử lý `IOException`.

### isReadable() cũng chỉ là một chỉ báo

`isReadable()` có thể giúp phát hiện một số resource không thể đọc, nhưng không phải cam kết rằng lần mở stream sau sẽ thành công.

Thông báo lỗi tốt nên bổ sung `resource.getDescription()` để biết nguồn được đọc mà không phụ thuộc vào `getFile()`.

## 13. Đọc văn bản, JSON và dữ liệu nhị phân

`Resource` không áp đặt định dạng nội dung.

**Với văn bản UTF-8 nhỏ**, có thể đọc toàn bộ stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    String text = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

**Với JSON**, truyền stream vào parser:

~~~java
try (InputStream input = resource.getInputStream()) {
    JsonNode tree = objectMapper.readTree(input);
}
~~~

Ví dụ thứ hai dùng `JsonNode` và `ObjectMapper` của Jackson, giả định `objectMapper` đã được inject và thư viện Jackson phù hợp đã có trong project.

**Với file lớn**, xử lý tuần tự:

~~~java
try (InputStream input = resource.getInputStream()) {
    byte[] buffer = new byte[8192];

    int count;
    while ((count = input.read(buffer)) != -1) {
        // Xử lý buffer từ vị trí 0 với độ dài count.
    }
}
~~~

Với CSV hoặc log text, có thể dùng `BufferedReader` để đọc từng dòng. Với hình ảnh hoặc file nhị phân, tuyệt đối không tự chuyển byte qua một charset rồi kỳ vọng giữ nguyên nội dung.

Để tránh OutOfMemoryError hoặc chi phí bộ nhớ khó kiểm soát, không nên gọi `readAllBytes()` với tài nguyên có kích thước lớn hoặc không giới hạn, nhất là URL công khai.

## 14. Đóng InputStream đúng cách

Hợp đồng quan trọng của `Resource` là caller phải quản lý resource sử dụng được trả về từ `getInputStream()`.

Cách nên dùng:

~~~java
try (InputStream stream = resource.getInputStream()) {
    // Sử dụng stream trong khối này.
}
~~~

Sau khi kết thúc khối, Java sẽ gọi `close()`, kể cả khi có exception trong lúc đọc.

Tránh những mẫu sau:

~~~java
InputStream stream = resource.getInputStream();
// Đọc xong nhưng không đóng stream.
~~~

Điều này có thể làm rò rỉ file descriptor, socket hoặc tài nguyên mạng.

Đồng thời, **đừng mặc định cùng một Resource luôn cho phép mở lại stream nhiều lần**. Những implementation như `InputStreamResource` có thể đại diện cho một stream chỉ đọc được một lần. Nếu API cần đọc lại nhiều lần, phải kiểm tra tính chất của loại resource hoặc thiết kế cách lưu trữ/buffer phù hợp.

## 15. Các implementation Resource quan trọng

| Implementation | Nguồn thường dùng | Ghi chú |
|---|---|---|
| `ClassPathResource` | File/entry trên classpath | Hỗ trợ đọc dữ liệu đóng gói trong JAR qua stream |
| `FileSystemResource` | File hoặc Path trên filesystem | Phù hợp khi đã có đường dẫn thực |
| `UrlResource` | URL, có thể gồm file/HTTP(S) | Hành vi I/O phụ thuộc scheme và URL handler |
| `ByteArrayResource` | Dữ liệu `byte[]` trong bộ nhớ | Thích hợp test hoặc nội dung tạo sẵn |
| `InputStreamResource` | Một `InputStream` hiện có | Thường không thích hợp để đọc nhiều lần |
| `ServletContextResource` | Resource gắn với servlet context | Có thể xuất hiện trong ứng dụng web truyền thống |

### ClassPathResource

~~~java
Resource resource = new ClassPathResource("data/default.json");
~~~

Chỉ rõ lớp lưu trữ là classpath.

### FileSystemResource

~~~java
Resource resource = new FileSystemResource(
        Path.of("/opt/app/config/default.json")
);
~~~

Tài nguyên là file/path mà OS có thể truy cập.

### UrlResource

~~~java
Resource resource = new UrlResource(
        "https://example.org/data/default.json"
);
~~~

Cần xử lý ngoại lệ khi tạo URL không hợp lệ và khi truy cập nội dung.

### ByteArrayResource trong unit test

~~~java
byte[] content = "Hello".getBytes(StandardCharsets.UTF_8);
Resource resource = new ByteArrayResource(content);

String message = ResourceTextReader.readSmallUtf8(resource);
~~~

Một ưu điểm của việc thiết kế hàm nhận `Resource` là test có thể dùng `ByteArrayResource` mà không cần tạo file thật hoặc gọi network.

## 16. ResourceLoader đọc một vị trí; ResourcePatternResolver tìm nhiều tài nguyên

Một phân biệt rất quan trọng là:

- `ResourceLoader.getResource(location)`: nhận **một location**, trả về **một đối tượng Resource**.
- `ResourcePatternResolver.getResources(pattern)`: tìm **nhiều Resource** theo pattern hoặc quy ước tìm kiếm.

Ví dụ, `ResourceLoader` không phải công cụ để expand glob:

~~~java
resourceLoader.getResource("classpath:config/*.yml");
~~~

Đừng kỳ vọng lời gọi trên tự tìm mọi file có đuôi `.yml`. Dấu `*` ở đây không có ý nghĩa glob với phương thức `getResource(...)` theo cách thông thường.

Nếu cần tìm nhiều tài nguyên, dùng `ResourcePatternResolver`:

~~~java
import java.io.IOException;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver(resourceLoader);

Resource[] resources = resolver.getResources(
        "classpath*:config/*.yml"
);

for (Resource resource : resources) {
    System.out.println(resource.getDescription());
}
~~~

`PathMatchingResourcePatternResolver` hỗ trợ pattern thường gặp theo phong cách Ant và tìm kiếm trên classpath với `classpath*:`.

### classpath: khác classpath*:

| Tiền tố | Ý nghĩa khái quát |
|---|---|
| `classpath:` | Một resource được tìm từ classpath |
| `classpath*:` | Tìm các resource khớp qua các vị trí classpath có thể có |
| `classpath*:config/*.yml` | Kết hợp tìm nhiều vị trí classpath và pattern |

Ví dụ nhiều thư viện JAR đều chứa một file:

~~~text
META-INF/demo/plugin.properties
~~~

Nếu cần lấy **tất cả** bản sao của resource trên nhiều classpath root/JAR, có thể dùng:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:META-INF/demo/plugin.properties"
);
~~~

Ngược lại, `classpath:META-INF/demo/plugin.properties` thường chỉ giải quyết một resource theo cơ chế classloader; không bảo đảm duyệt tất cả bản sao trùng tên.

**Lưu ý:** `classpath*:` là cơ chế dành cho `ResourcePatternResolver`. Không coi nó là một prefix thay thế tự do cho `classpath:` trong mọi API chỉ nhận một `Resource`.

### Giới hạn của việc scan pattern

Việc tìm theo pattern trong nhiều JAR có thể phụ thuộc cấu trúc classpath, URL handler và khả năng liệt kê nội dung archive. Không nên thiết kế một tính năng bắt buộc dựa trên giả định rằng mọi kiểu archive không chuẩn đều có khả năng scan giống nhau.

Nếu ứng dụng cần một danh sách file bắt buộc, đôi khi cấu hình danh sách tường minh ổn định và dễ vận hành hơn một pattern quá rộng.

## 17. Ví dụ dùng ResourcePatternResolver trong service

Giả sử có các file:

~~~text
src/main/resources/
  rules/
    common.yml
    pricing.yml
    security.yml
~~~

Ta muốn tải tất cả file `.yml` trong thư mục `rules`.

~~~java
package com.example.rules;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Service;

@Service
public class RuleResourceService {

    private final ResourcePatternResolver resolver;

    public RuleResourceService(ResourceLoader loader) {
        this.resolver = new PathMatchingResourcePatternResolver(loader);
    }

    public List<Resource> findRuleFiles() throws IOException {
        Resource[] matches = resolver.getResources(
                "classpath*:rules/*.yml"
        );

        List<Resource> result = new ArrayList<>();
        for (Resource resource : matches) {
            if (resource.isReadable()) {
                result.add(resource);
            }
        }
        return result;
    }
}
~~~

Method chỉ **tìm các resource**, chưa parse YAML. Ứng dụng cần quyết định thứ tự xử lý, xử lý trùng tên, phản ứng khi không tìm thấy file và chính sách khi một file bị lỗi.

Đặc biệt, kết quả pattern scan có thể phụ thuộc classpath và classloader; không dựa vào thứ tự liệt kê mặc định để định nghĩa độ ưu tiên cấu hình nghiệp vụ.

## 18. Resource và cấu hình ngoài ứng dụng

Một ứng dụng thường có dữ liệu mặc định trong classpath và muốn cho phép thay bằng file ngoài JAR.

Ví dụ trong `application.properties`:

~~~properties
app.rules.location=classpath:rules/default.json
~~~

Khi deploy:

~~~bash
java -jar app.jar --app.rules.location=file:/opt/app/config/rules.json
~~~

Hoặc dùng biến môi trường:

~~~bash
export APP_RULES_LOCATION=file:/opt/app/config/rules.json
java -jar app.jar
~~~

Tên `APP_RULES_LOCATION` tương ứng property `app.rules.location` trong cơ chế externalized configuration của Spring Boot.

Service đọc resource có thể dùng:

~~~java
@ConfigurationProperties(prefix = "app.rules")
public record RulesProperties(String location) {
}
~~~

Sau khi đăng ký `RulesProperties` với Spring, một service nhận object này và `ResourceLoader`:

~~~java
@Service
public class RulesService {

    private final RulesProperties properties;
    private final ResourceLoader loader;

    public RulesService(RulesProperties properties, ResourceLoader loader) {
        this.properties = properties;
        this.loader = loader;
    }

    public Resource rulesResource() {
        return loader.getResource(properties.location());
    }
}
~~~

Các đoạn Java trên lược bỏ import để tập trung vào cách kết hợp hai abstraction. Khi đưa vào project, cần import `ConfigurationProperties`, `Service`, `ResourceLoader` và `Resource` tương ứng, đồng thời đăng ký configuration properties bean.

### Dữ liệu tài nguyên khác với application config

`application.properties` hoặc `application.yml` là **các nguồn cấu hình** mà Spring Boot đọc theo cơ chế Config Data, có profile, ưu tiên và quy tắc riêng.

Trong khi đó, `ResourceLoader` là abstraction tổng quát để truy cập tài nguyên. Việc đọc một file JSON bằng `ResourceLoader` **không tự làm các key trong JSON trở thành Spring properties**. Tương tự, tự gọi `getResource("file:/.../app.yml")` chưa đồng nghĩa Spring Boot sẽ tự đưa file đó vào các property sources.

Nếu muốn Spring Boot nạp một file cấu hình ngoài theo cơ chế cấu hình chính thức, cần sử dụng những tùy chọn tương ứng như `spring.config.location`, `spring.config.additional-location` hoặc `spring.config.import` trong hoàn cảnh phù hợp. Đó là một mục đích khác với việc đọc file dữ liệu nghiệp vụ bằng `Resource`.

## 19. Những rủi ro bảo mật khi location đến từ input

Giả sử xây dựng endpoint:

~~~java
@GetMapping("/read")
public String read(@RequestParam String path) throws IOException {
    Resource resource = resourceLoader.getResource(path);
    return ResourceTextReader.readSmallUtf8(resource);
}
~~~

**Đây là một ví dụ không an toàn, không nên triển khai.**

Người dùng có thể thử những location như:

~~~text
file:/etc/passwd
file:/opt/app/secrets/private-key.pem
http://127.0.0.1:8080/admin
http://169.254.169.254/
~~~

Nếu endpoint cho phép đọc tùy ý, nó có thể tạo ra:

- **Local File Read / path traversal**: đọc file không dành cho người dùng.
- **SSRF**: khiến server gửi request đến địa chỉ nội bộ hoặc dịch vụ metadata.
- **Resource exhaustion**: đọc file rất lớn, URL chậm hoặc stream không kết thúc.
- **Lộ thông tin**: trả lại nội dung chứa secret hoặc cấu hình nội bộ.

### Thiết kế an toàn hơn

Thay vì nhận location trực tiếp từ request, định nghĩa các tài nguyên hợp lệ bằng mã hoặc cấu hình đáng tin cậy:

~~~java
private static final Map<String, String> ALLOWED_RESOURCES = Map.of(
        "guide", "classpath:docs/guide.txt",
        "terms", "classpath:docs/terms.txt"
);

public Resource findDocument(String id) {
    String location = ALLOWED_RESOURCES.get(id);

    if (location == null) {
        throw new IllegalArgumentException("Tài liệu không hợp lệ");
    }

    return resourceLoader.getResource(location);
}
~~~

Với file ngoài JAR, cần kiểm tra thêm đường dẫn được chuẩn hóa có nằm trong thư mục cho phép, phân quyền OS/container và giới hạn loại file. Với URL, nên dùng allowlist scheme/host và HTTP client có chính sách timeout, redirect, DNS, IP range và kích thước nội dung.

**Không chỉ kiểm tra chuỗi có bắt đầu bằng `classpath:`, `file:` hoặc `https:` rồi coi là an toàn.** Prefix cho biết loại nguồn, không chứng minh nguồn đó đáng tin.

## 20. Xử lý lỗi khi đọc Resource

Một số tình huống điển hình:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Chạy IDE được, JAR lỗi `getFile()` | Resource nằm bên trong archive | Dùng `getInputStream()` |
| Không tìm thấy `classpath:...` | Sai đường dẫn classpath hoặc file chưa được package | Kiểm tra `src/main/resources`, tên phân biệt hoa/thường, artifact |
| File ngoài JAR không đọc được | Sai đường dẫn hoặc process không có quyền | Kiểm tra mount, path tuyệt đối, quyền đọc |
| URL resource đọc rất chậm | DNS, TLS, mạng hoặc server chậm | Dùng client có timeout và chính sách rõ |
| `exists()` trả true nhưng read lỗi | Nguồn thay đổi giữa kiểm tra và đọc | Bắt và xử lý `IOException` |
| Không tìm được các file `*.yml` | Dùng `getResource()` thay vì pattern resolver | Dùng `ResourcePatternResolver.getResources(...)` |
| Đọc lần thứ hai thất bại | Resource có stream chỉ dùng một lần | Thiết kế luồng đọc hoặc buffer phù hợp |
| File lớn gây tăng bộ nhớ mạnh | Dùng `readAllBytes()` không giới hạn | Đọc streaming, giới hạn kích thước |
| URL hoặc file trái phép bị đọc | Location xuất phát từ input tùy ý | Allowlist và kiểm soát truy cập |

### Ghi log có bối cảnh nhưng không lộ thông tin

Ví dụ:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Đọc resource.
} catch (IOException exception) {
    log.error(
            "Không đọc được tài nguyên: {}",
            resource.getDescription(),
            exception
    );
    throw exception;
}
~~~

`resource.getDescription()` hỗ trợ xác định nguồn lỗi. Tuy nhiên, với URL chứa token trong query string hoặc vị trí file nhạy cảm, có thể cần **rút gọn hoặc làm sạch mô tả trước khi log**.

Không nên ghi toàn bộ URL có credential, nội dung file hoặc token vào log.

## 21. Resource trong unit test

Việc phụ thuộc `Resource` giúp code dễ kiểm thử mà không phải có file thật trong nhiều trường hợp.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

class ResourceTextReaderTest {

    @Test
    void readsUtf8() throws Exception {
        byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
        Resource resource = new ByteArrayResource(bytes);

        String actual = ResourceTextReader.readSmallUtf8(resource);

        assertEquals("Xin chào", actual);
    }
}
~~~

Test này không cần:

- Tạo file tạm.
- Đọc `src/main/resources`.
- Khởi động Spring ApplicationContext.
- Gọi HTTP endpoint.

Khi cần kiểm tra cơ chế classpath thật, có thể đưa test fixture vào `src/test/resources`:

~~~text
src/test/resources/
  fixtures/sample.json
~~~

Rồi tạo `ClassPathResource("fixtures/sample.json")` trong test. Hãy nhớ: tài nguyên trong `src/test/resources` thường chỉ thuộc **test classpath**, không tự xuất hiện trong executable JAR production.

## 22. Đường dẫn tương đối với một class trong package

`ClassPathResource` có constructor cho phép tạo resource tương đối với một `Class<?>`. Điều này khác với tên đường dẫn bắt đầu từ gốc classpath.

Ví dụ:

~~~java
package com.example.report;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class ReportRenderer {

    public Resource template() {
        return new ClassPathResource(
                "default-template.txt",
                ReportRenderer.class
        );
    }
}
~~~

Với constructor nhận `Class<?>`, đường dẫn tương đối có thể được giải quyết dựa trên package của class đó. Điều này hữu ích nếu muốn đặt resource cùng package với class Java.

Nếu dùng constructor đơn giản:

~~~java
new ClassPathResource("com/example/report/default-template.txt");
~~~

thì đường dẫn được hiểu từ gốc classpath.

**Nên chọn và ghi rõ một quy ước trong dự án.** Nếu một số tài nguyên được đặt theo package còn số khác ở thư mục cấu hình độc lập, cách viết đường dẫn không tường minh sẽ khiến việc di chuyển class hoặc refactor package làm lỗi resource.

## 23. Dùng ResourceLoader có cần ApplicationContext trực tiếp không?

Không cần. Một service chỉ muốn tải resource nên phụ thuộc vào abstraction hẹp:

~~~java
@Service
public class TemplateService {

    private final ResourceLoader resourceLoader;

    public TemplateService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource template(String name) {
        return resourceLoader.getResource(
                "classpath:templates/" + name
        );
    }
}
~~~

Ví dụ trên chỉ minh họa dependency injection, **không an toàn để nhận `name` không tin cậy** nếu nó có thể chứa path traversal. Một dịch vụ thực tế nên chọn tên từ danh sách cho phép hoặc ánh xạ ID đến location cố định.

Nếu service inject cả `ApplicationContext` chỉ để gọi `getResource(...)`, nó đã phụ thuộc vào một giao diện rộng hơn nhu cầu. Dùng `ResourceLoader` làm dependency thường giúp thiết kế gọn và dễ thay bằng implementation test.

### ResourceLoaderAware

Ngoài constructor injection, Spring còn có `ResourceLoaderAware` cho các bean muốn được cung cấp ResourceLoader qua callback. Tuy nhiên, constructor injection thường dễ hiểu, dễ test và biểu đạt dependency trực tiếp hơn trong ứng dụng hiện đại.

Không cần triển khai `ResourceLoaderAware` nếu constructor đã đáp ứng yêu cầu.

## 24. Không nhầm Resource với tài nguyên HTTP tĩnh do Spring MVC phục vụ

Spring Boot cũng có cơ chế phục vụ static content từ các vị trí classpath như:

~~~text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
~~~

Trong ứng dụng web cấu hình mặc định phù hợp, file trong những vị trí đó có thể được ánh xạ thành HTTP resource thông qua cơ chế phục vụ nội dung tĩnh của Spring MVC.

Ví dụ một file `src/main/resources/static/logo.svg` có thể được phục vụ dưới một URL ứng dụng tùy mapping.

Điều này **khác** với việc một service chủ động gọi:

~~~java
resourceLoader.getResource("classpath:static/logo.svg");
~~~

Hai cơ chế có thể cùng đọc dữ liệu từ classpath nhưng mục đích khác nhau:

- **ResourceLoader**: giúp code Java truy cập một tài nguyên.
- **Static resource handling**: giúp web framework ánh xạ và phục vụ tài nguyên cho HTTP client.

Không nên mặc định bất kỳ file nào trong `src/main/resources` cũng sẽ tự được public qua HTTP. Việc exposure phụ thuộc vào web stack, mapping và cấu hình resource handlers.

## 25. Bài tập thực hành

### Bài tập 1: Đọc classpath resource từ JAR

1. Tạo file `src/main/resources/data/banner.txt`.
2. Viết service nhận `ResourceLoader`.
3. Gọi `getResource("classpath:data/banner.txt")`.
4. Đọc bằng `getInputStream()` trong try-with-resources.
5. Chạy trong IDE, sau đó đóng gói executable JAR và chạy lại.

**Quan sát:** đoạn code không nên cần biết đường dẫn `src/main/resources` tại runtime.

### Bài tập 2: Thay nguồn qua cấu hình

Giữ service đọc resource không đổi. Đặt:

~~~properties
app.banner.location=classpath:data/banner.txt
~~~

Sau đó chạy:

~~~bash
java -jar app.jar --app.banner.location=file:/opt/app/config/banner.txt
~~~

Hãy ghi nhận điểm khác biệt giữa nội dung đóng gói trong JAR và file bên ngoài.

### Bài tập 3: Cố tình dùng getFile()

Tạo `ClassPathResource` cho một file trong JAR rồi gọi `getFile()`. Quan sát hành vi khi chạy từ IDE và executable JAR.

**Bài học cần rút ra:** API có thể hoạt động với file thật lúc phát triển nhưng không đảm bảo hoạt động với entry trong archive.

Thay lời gọi bằng `getInputStream()` để không phụ thuộc layout của JAR.

### Bài tập 4: Đọc nhiều resource

Tạo:

~~~text
src/main/resources/rules/
  a.yml
  b.yml
  c.yml
~~~

Dùng:

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver(resourceLoader);

Resource[] resources = resolver.getResources(
        "classpath*:rules/*.yml"
);
~~~

So sánh kết quả với `resourceLoader.getResource("classpath:rules/*.yml")`.

**Bài học cần rút ra:** một phương thức trả về một resource không tự tìm nhiều file theo glob.

### Bài tập 5: Thiết kế API truy cập tài nguyên an toàn

Giả sử một API chỉ được phép trả về hai mẫu tài liệu `guide` và `terms`. Hãy viết một map ID → location tường minh, thay vì lấy toàn bộ location trực tiếp từ HTTP query parameter.

Sau đó giải thích vì sao việc chỉ kiểm tra `location.startsWith("file:")` hoặc `location.startsWith("https:")` không đủ ngăn Local File Read hoặc SSRF.

## 26. Những hiểu lầm thường gặp

**“Resource luôn là java.io.File.”** Sai. Resource có thể đại diện cho mục trong JAR hoặc URL.

**“Dùng getFile() trên classpath resource luôn được.”** Không. Khi resource đóng gói trong archive, file vật lý có thể không tồn tại.

**“getResource() sẽ tải hết dữ liệu ngay.”** Thông thường không. Nó chủ yếu tạo abstraction cho location; việc đọc xuất hiện khi mở stream.

**“exists() thành công nên không cần bắt IOException.”** Sai. Nguồn có thể thay đổi hoặc thất bại khi mở stream.

**“file: là đường dẫn trên máy developer.”** Sai. Đó là filesystem nhìn thấy bởi process đang chạy, có thể nằm trong container hoặc máy khác.

**“Một location không có prefix luôn là classpath.”** Không nên giả định vì cách xử lý phụ thuộc loader/context.

**“classpath*: luôn dùng như classpath: được.”** Sai. `classpath*:` gắn với cơ chế tìm nhiều resource của `ResourcePatternResolver`.

**“resourceLoader.getResource có thể tìm tất cả *.json.”** Không. Để tìm nhiều tài nguyên theo pattern cần resolver phù hợp.

**“ResourceLoader là một HTTP client đầy đủ.”** Không. Với HTTP nghiệp vụ phức tạp cần client riêng và cơ chế timeout/retry rõ ràng.

**“Chỉ cần nhận location từ user rồi getResource là tiện.”** Rất rủi ro: có thể dẫn tới đọc file nhạy cảm hoặc SSRF.

**“Tài nguyên trong src/test/resources luôn có trong production.”** Không. Nó thường chỉ có mặt trên test classpath.

**“Đọc file dữ liệu bằng ResourceLoader là Spring tự thêm các trường vào Environment.”** Không. Resource abstraction và Config Data là hai cơ chế phục vụ các mục đích khác nhau.

## 27. Nguyên tắc chọn giải pháp

Khi thiết kế chức năng đọc tài nguyên, có thể quyết định theo các câu hỏi:

| Câu hỏi | Hướng lựa chọn |
|---|---|
| Dữ liệu luôn đi kèm ứng dụng và không cần chỉnh sửa sau build? | `classpath:` |
| Dữ liệu được mount hoặc cập nhật từ bên ngoài artifact? | `file:` với path rõ ràng |
| Dữ liệu nằm ở endpoint mạng cần auth, timeout và retry? | HTTP client chuyên dụng; `Resource` chỉ khi nhu cầu đơn giản và kiểm soát được |
| Code chỉ cần đọc nội dung? | `Resource.getInputStream()` |
| Code cần tìm nhiều file theo glob? | `ResourcePatternResolver` |
| Code được cấp một `Path` đã kiểm tra? | `FileSystemResource` |
| Muốn viết test không phụ thuộc file thật? | `ByteArrayResource` |
| Location đến từ người dùng cuối? | Không nạp trực tiếp; kiểm soát danh sách nguồn, path và URL |
| Resource có thể rất lớn? | Streaming, giới hạn kích thước và xử lý lỗi I/O |
| Cần đổi nguồn mà không sửa Java? | Đưa location vào configuration property đáng tin cậy |

Cần nhớ rằng lựa chọn nguồn dữ liệu còn ảnh hưởng đến vận hành: phân quyền container, mount volumes, lịch sử triển khai, tính bất biến của artifact, security boundary và chính sách phục hồi khi nguồn không sẵn sàng.

## Kết luận

**`Resource`** là abstraction để đọc một tài nguyên mà không buộc nó phải tồn tại dưới dạng file vật lý. **`ResourceLoader`** nhận một location và giải quyết nó thành đối tượng Resource phù hợp. Ba nhóm location quan trọng nhất trong Spring Boot là:

- **`classpath:`** cho tài nguyên có trong classpath, bao gồm file đóng gói bên trong executable JAR.
- **`file:`** cho file/path mà process Java nhìn thấy trên hệ thống file.
- **URL scheme như `https:`** cho nguồn có thể truy cập qua mạng, với yêu cầu kiểm soát an toàn và chính sách I/O thích hợp.

Khi đọc, ưu tiên **`getInputStream()` và try-with-resources** thay vì ép resource thành `java.io.File`. Khi cần nhiều file, phân biệt rõ `ResourceLoader` với `ResourcePatternResolver` và tiền tố `classpath*:`. Khi nguồn được chọn từ cấu hình, hãy dùng location tường minh và quản lý quyền truy cập, kích thước dữ liệu cùng lỗi I/O.

Hiểu đúng các abstraction này giúp ứng dụng Spring Boot vận hành nhất quán từ IDE đến JAR/container, dễ thay đổi nguồn dữ liệu khi triển khai và tránh những lỗi thường gặp về đường dẫn cũng như bảo mật.
