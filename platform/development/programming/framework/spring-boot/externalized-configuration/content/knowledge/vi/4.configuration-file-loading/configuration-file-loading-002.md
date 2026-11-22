# Phân biệt classpath, thư mục làm việc và đường dẫn file

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Tìm và nạp tệp

## 1. Vì sao cần phân biệt ba khái niệm?

Một ứng dụng Spring Boot thường cần đọc hai nhóm dữ liệu: **tài nguyên đóng gói cùng ứng dụng** (mẫu email, tệp JSON mặc định, chứng chỉ công khai, dữ liệu mẫu) và **tệp nằm ngoài ứng dụng** (cấu hình triển khai, dữ liệu nhập/xuất, tệp người dùng tải lên). Hai nhóm này có thể được truy cập bằng những cách hoàn toàn khác nhau.

Ba khái niệm hay bị nhầm lẫn là:

- **Classpath**: tập hợp các vị trí mà Java ClassLoader dùng để tìm lớp và tài nguyên khi chạy. Tài nguyên có thể nằm trong thư mục hoặc bên trong JAR.
- **Thư mục làm việc (working directory)**: thư mục hiện hành của tiến trình Java, thường được biểu diễn bằng `user.dir`. Một đường dẫn tương đối như `data/input.csv` thường được giải quyết theo thư mục này khi dùng API `Path`/`File`.
- **Đường dẫn file (filesystem path)**: địa chỉ của một mục trong hệ thống tệp, có thể là đường dẫn tuyệt đối (`/opt/app/data/a.csv`) hoặc tương đối (`./data/a.csv`).

**Ý chính:** `classpath:...` và `file:...` chỉ tới hai loại nguồn khác nhau trong cơ chế `Resource` của Spring. Một tài nguyên có thể tìm thấy bằng classpath nhưng hoàn toàn **không tồn tại như một file độc lập** trên hệ thống tệp khi ứng dụng đã được đóng gói thành executable JAR.

## 2. Một cấu trúc dự án để minh họa

Giả sử dự án có cấu trúc:

~~~text
catalog-service/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/catalog/
│       │   └── CatalogApplication.java
│       └── resources/
│           ├── application.yml
│           └── templates/
│               └── welcome.txt
├── config/
│   └── overrides.yml
└── data/
    └── incoming.csv
~~~

Khi phát triển trong IDE, ba file sau có thể đều xuất hiện trên ổ đĩa:

1. `src/main/resources/templates/welcome.txt`: tài nguyên nguồn sẽ được đưa vào **classpath** sau khi build; trong JAR thường không còn giữ tiền tố `src/main/resources`.
2. `config/overrides.yml`: file bên ngoài phần `src/main/resources`, chỉ được đọc khi ứng dụng được chỉ đúng filesystem path hoặc cấu hình nạp phù hợp.
3. `data/incoming.csv`: file dữ liệu ngoài ứng dụng; `Path.of("data/incoming.csv")` sẽ truy cập dựa trên working directory của tiến trình.

Sau khi đóng gói, có thể triển khai:

~~~text
/opt/catalog/
├── catalog-service.jar
├── config/
│   └── application.yml
└── data/
    └── incoming.csv
~~~

Trong JAR, `templates/welcome.txt` vẫn là classpath resource. Trong khi đó, `/opt/catalog/config/application.yml` và `/opt/catalog/data/incoming.csv` là các file trên hệ thống tệp bên ngoài JAR.

## 3. Classpath: tài nguyên được ClassLoader tìm thấy

### 3.1. `src/main/resources` là thư mục nguồn khi phát triển

Với Maven hoặc Gradle, nội dung `src/main/resources` thường được sao chép vào output resources của build, rồi được đóng gói vào JAR.

Ví dụ tệp:

~~~text
src/main/resources/templates/welcome.txt
~~~

thường được truy cập khi chạy bằng đường dẫn classpath:

~~~text
classpath:templates/welcome.txt
~~~

Không dùng `classpath:src/main/resources/templates/welcome.txt`. Sau khi build, đường dẫn classpath phải tính từ **gốc classpath**, không tính từ gốc repository.

Classpath không đồng nghĩa với một thư mục duy nhất. Nó có thể bao gồm nhiều thư mục, nhiều dependency JAR, các vị trí do class loader quản lý; Spring Boot executable JAR cũng có bố cục đóng gói riêng (thông thường có `BOOT-INF/classes` và `BOOT-INF/lib`).

### 3.2. Đọc classpath resource bằng Spring `Resource`

Ví dụ dùng `ResourceLoader` của Spring:

~~~java
package com.example.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class WelcomeTemplateService {

    private final ResourceLoader resourceLoader;

    public WelcomeTemplateService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String loadTemplate() throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:templates/welcome.txt");

        try (InputStream stream = resource.getInputStream()) {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Có thể inject trực tiếp một resource:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class TemplateResourceHolder {
    private final Resource template;

    public TemplateResourceHolder(
            @Value("classpath:templates/welcome.txt") Resource template) {
        this.template = template;
    }

    public Resource template() {
        return template;
    }
}
~~~

Khi cần lấy nội dung, gọi `template.getInputStream()` và đóng stream sau khi sử dụng. Cách đọc này thường hoạt động trong IDE lẫn executable JAR.

### 3.3. Vì sao `getFile()` có thể chạy ở IDE nhưng lỗi khi chạy JAR?

Ví dụ dễ mắc lỗi:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:templates/welcome.txt");

// Không nên giả định classpath resource luôn có một File trên ổ đĩa.
File file = resource.getFile();
~~~

Trong IDE, resource có thể nằm dưới một thư mục như `target/classes` hoặc `build/resources/main`, nên lời gọi này đôi khi thành công. Khi đóng gói trong JAR, resource nằm **bên trong archive**, không còn tương ứng với một `java.io.File` độc lập. Lúc đó `getFile()` có thể ném `FileNotFoundException` hoặc lỗi tương đương.

Muốn **đọc** resource đóng gói, ưu tiên `getInputStream()`. Chỉ dùng `getFile()` nếu yêu cầu nghiệp vụ và cách triển khai bảo đảm resource thực sự là một file ngoài archive.

### 3.4. ClassLoader API trong Java thuần

Không cần Spring, Java cũng có thể đọc tài nguyên:

~~~java
try (InputStream in = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("templates/welcome.txt")) {

    if (in == null) {
        throw new IllegalStateException("Không tìm thấy welcome.txt");
    }

    String content = new String(
            in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

`ClassLoader.getResourceAsStream(...)` dùng tên resource không có tiền tố `classpath:` và thường không bắt đầu bằng `/`. `Class.getResourceAsStream(...)` có quy tắc khác: tên không bắt đầu `/` là tương đối với package của class; tên bắt đầu `/` tính từ classpath root. Nên chọn một cách đặt tên rõ ràng để tránh nhầm đường dẫn.

Spring còn hỗ trợ `classpath*:` trong các API tìm **nhiều** tài nguyên, ví dụ `ResourcePatternResolver`; đây không phải một filesystem path và không có nghĩa sẽ trả về đúng một resource duy nhất.

## 4. Working directory: thư mục hiện hành của tiến trình Java

### 4.1. `user.dir` không mặc định là thư mục chứa JAR

Thư mục làm việc thường phụ thuộc vào **nơi và cách khởi động tiến trình**: terminal đang đứng ở đâu, cấu hình Run/Debug của IDE, `WORKDIR` trong Docker, `workingDir` trong Kubernetes hoặc working directory của service manager.

Ví dụ cùng một JAR nhưng cách chạy khác nhau:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar
~~~

Khi đó đường dẫn tương đối `./data/incoming.csv` thường được giải quyết thành `/opt/catalog/data/incoming.csv`.

Nếu chạy:

~~~bash
cd /tmp
java -jar /opt/catalog/catalog-service.jar
~~~

thì `./data/incoming.csv` thường trỏ tới `/tmp/data/incoming.csv`, **không phải** `/opt/catalog/data/incoming.csv`. Vị trí của file JAR không tự quyết định working directory.

Trong Java:

~~~java
import java.nio.file.Path;

Path workingDirectory = Path.of("")
        .toAbsolutePath()
        .normalize();

System.out.println("user.dir = " + System.getProperty("user.dir"));
System.out.println("Working directory = " + workingDirectory);
~~~

Hai giá trị trên thường phản ánh working directory của tiến trình tại lúc khởi động. Chúng hữu ích cho chẩn đoán, nhưng không nên dùng như một giả định cố định về cách triển khai.

### 4.2. Đọc một đường dẫn tương đối bằng `java.nio.file`

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExternalFileReader {

    public String loadIncomingCsv() throws IOException {
        Path path = Path.of("data", "incoming.csv");

        // Địa chỉ thực tế mà ứng dụng đang cố mở.
        Path resolved = path.toAbsolutePath().normalize();

        System.out.println("Reading from: " + resolved);
        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
~~~

`Path.of("data", "incoming.csv")` không dùng ClassLoader. Nó mô tả một file trên filesystem theo quy tắc của hệ điều hành và working directory. Nếu file không tồn tại tại vị trí được giải quyết, thao tác đọc sẽ thất bại dù một resource cùng tên có thể tồn tại trong classpath.

Để giảm rủi ro lỗi do working directory thay đổi, nên lấy thư mục dữ liệu từ cấu hình rõ ràng và kết hợp với tên file:

~~~properties
catalog.storage-dir=/var/lib/catalog
~~~

~~~java
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogPaths {

    private final Path storageDir;

    public CatalogPaths(@Value("${catalog.storage-dir}") String value) {
        this.storageDir = Path.of(value).toAbsolutePath().normalize();
    }

    public Path incoming() {
        return storageDir.resolve("incoming.csv");
    }
}
~~~

Đường dẫn `/var/lib/catalog` chỉ là ví dụ Unix/Linux; trên Windows hoặc các môi trường khác cần dùng đường dẫn phù hợp. `toAbsolutePath().normalize()` chuẩn hóa cú pháp, nhưng không kiểm tra file có tồn tại hoặc loại bỏ mọi rủi ro bảo mật khi ghép đường dẫn từ đầu vào không tin cậy.

## 5. File path: tuyệt đối và tương đối

| Dạng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tương đối | `data/input.csv` | Được giải quyết so với working directory khi dùng `Path`/`File` |
| Tương đối có `./` | `./config/application.yml` | Cùng nguyên tắc trên; `./` nhấn mạnh bắt đầu ở thư mục hiện hành |
| Tuyệt đối trên Linux | `/etc/catalog/application.yml` | Vị trí đầy đủ trên filesystem Linux; không phụ thuộc working directory |
| Tuyệt đối trên Windows | `C:\apps\catalog\config\application.yml` | Vị trí filesystem Windows; không phải đường dẫn dùng chung cho mọi OS |
| URI trong Spring | `file:./config/application.yml` | Spring `Resource` đọc một file tương đối với working directory |
| URI trong Spring | `file:/opt/catalog/config/application.yml` | Spring `Resource` đọc file ở vị trí tuyệt đối tương ứng |
| URI trong Spring | `classpath:application.yml` | Spring tìm resource trên classpath; không phải đường dẫn filesystem |

Trong một string Java, dấu `\` của đường dẫn Windows phải được escape, ví dụ `"C:\\apps\\catalog\\config\\application.yml"`. API `Path.of(...)` giúp làm việc với đường dẫn theo hệ điều hành; khi lấy đường dẫn từ biến môi trường hoặc cấu hình, không nên tự lắp dấu `/` hay `\` bằng string nếu có thể dùng `resolve(...)`.

### 5.1. `file:` là cách chỉ định nguồn cho Spring Resource

Trong Spring:

~~~java
Resource external = resourceLoader.getResource(
        "file:./config/overrides.yml");

try (InputStream in = external.getInputStream()) {
    // Đọc từ file bên ngoài JAR.
}
~~~

Ở đây `file:./config/overrides.yml` mô tả file trong filesystem, tính từ working directory khi đường dẫn còn tương đối. Nó không được tự động đóng gói vào JAR.

Nếu đã có `Path`, có thể đọc trực tiếp bằng `Files` hoặc dùng `FileSystemResource`:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Path path = Path.of("/opt/catalog/config/overrides.yml");
Resource resource = new FileSystemResource(path);
~~~

Lựa chọn API dựa vào nhu cầu: `Resource` thuận tiện khi cần làm việc với nhiều loại vị trí trong Spring; `Path`/`Files` phù hợp khi đối tượng luôn là file trên filesystem và cần thao tác như kiểm tra thuộc tính, ghi hoặc di chuyển.

### 5.2. Không thể viết lại file đóng gói trong JAR như file dữ liệu thông thường

Resource trong `src/main/resources` là dữ liệu **bên trong artifact** sau khi build. Nó phù hợp để phát hành nội dung mặc định, không phù hợp để làm nơi ghi dữ liệu runtime. Với tệp người dùng tải lên, export, cache hoặc cấu hình có thể thay đổi, dùng filesystem bên ngoài JAR, volume/container mount hoặc một dịch vụ lưu trữ phù hợp.

Cách triển khai này còn giúp cập nhật dữ liệu mà không phải rebuild và phát hành lại ứng dụng.

## 6. Liên hệ trực tiếp với Spring Boot Externalized Configuration

Spring Boot có **cơ chế tìm config data** riêng (`application.properties`, `application.yml`, biến thể theo profile, `spring.config.import`, v.v.). Cơ chế này dùng cả classpath lẫn filesystem; không nên nhầm nó với lệnh đọc một resource bất kỳ bằng `ResourceLoader`.

### 6.1. Spring Boot mặc định tìm `application.*` ở đâu?

Với cách khởi động thông thường, Spring Boot tìm config data tại các vị trí mặc định, bao gồm:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

Dấu `./` ở các vị trí `file:` dựa vào working directory. Mẫu `config/*/` hỗ trợ các thư mục con trực tiếp phù hợp trong thư mục `config` bên ngoài. Thứ tự địa điểm và các quy tắc merge/override cấu hình được Spring Boot xử lý theo cơ chế config data, bao gồm tài liệu theo profile.

Ví dụ:

~~~text
catalog-service.jar
config/
  application.yml
~~~

Nếu chạy JAR với working directory ở cùng cấp với `config/`, Spring Boot có thể tìm thấy `./config/application.yml` theo cơ chế mặc định. Nếu chạy ở một thư mục khác, đường dẫn `./config` cũng thay đổi.

Trong các nguồn config data mặc định, các vị trí bên ngoài JAR thường được ưu tiên hơn bản `application.yml` đóng gói bên trong JAR. Tuy nhiên, **giá trị cấu hình cuối cùng** còn phụ thuộc profile, import, environment variable, system property và tham số dòng lệnh; không thể suy ra giá trị chỉ bằng nhìn vị trí file.

### 6.2. Dùng `spring.config.location` và `spring.config.additional-location`

Nếu cần đặt cấu hình tại một vị trí rõ ràng, có thể truyền khi khởi động:

~~~bash
java -jar catalog-service.jar \
  --spring.config.additional-location=optional:file:/etc/catalog/
~~~

Ở ví dụ này:

- `spring.config.additional-location` **bổ sung** vị trí vào tập tìm kiếm mặc định.
- `optional:` cho phép bỏ qua vị trí không tồn tại.
- Đường dẫn thư mục được kết thúc bằng `/` để Spring Boot ghép tên như `application.yml`.
- Vị trí bên ngoài đặt sau trong cơ chế thêm vị trí có thể ghi đè cấu hình mặc định theo quy tắc config data.

Nếu dùng:

~~~bash
java -jar catalog-service.jar \
  --spring.config.location=optional:file:/etc/catalog/
~~~

thì `spring.config.location` **thay thế** các vị trí mặc định dùng để tìm config data, thay vì chỉ bổ sung. Khi cần nhiều vị trí, phải khai báo tường minh theo cú pháp được Spring Boot hỗ trợ.

Các thuộc tính quyết định **nơi tìm cấu hình** như `spring.config.location`, `spring.config.additional-location` và `spring.config.name` cần có ở giai đoạn khởi động rất sớm (chẳng hạn environment variable, system property hoặc CLI), vì Boot dùng chúng trước khi nạp các file config data tương ứng. Không nên trông đợi khai báo `spring.config.location` trong chính file đang cần được tìm thấy sẽ giúp Boot tìm file đó.

### 6.3. Dùng `spring.config.import` khi file cấu hình đã được tìm thấy

Ví dụ trong một `application.yml` đã được Spring Boot nạp:

~~~yaml
spring:
  config:
    import: "optional:file:./config/overrides.yml"

catalog:
  greeting: "Welcome"
~~~

`spring.config.import` khai báo thêm một nguồn config data. Nếu file tồn tại trong working directory thích hợp, các thuộc tính nhập từ file tham gia cơ chế ưu tiên của Spring Boot. Nếu không tồn tại, `optional:` tránh lỗi thiếu file. Với cấu hình quan trọng bắt buộc phải có, hãy cân nhắc bỏ `optional:` để quá trình khởi động báo lỗi rõ ràng khi không tìm thấy.

Phân biệt:

- `ResourceLoader.getResource("file:...")` chỉ tạo một đối tượng để **đọc tài nguyên** theo yêu cầu của code.
- `spring.config.import=...` yêu cầu Spring Boot **nạp file như config data**, tham gia quá trình giải quyết cấu hình qua `Environment`.
- `@Value("${catalog.greeting}")` hoặc `@ConfigurationProperties` đọc **giá trị đã được giải quyết** từ `Environment`, không trực tiếp mở một filesystem path.

### 6.4. Nếu tên file không phải `application.yml`?

File `config/overrides.yml` không tự động được Boot nạp chỉ vì nằm trong `./config/`. Tìm kiếm mặc định chủ yếu dựa trên tên `application` và các biến thể profile. Để dùng một tên riêng như `overrides.yml`, có thể khai báo `spring.config.import` hoặc chỉ định vị trí file thích hợp. Tương tự, file `templates/welcome.txt` trong classpath không tự trở thành property source.

## 7. Ví dụ so sánh cùng một tên tài nguyên

Giả sử có hai file đều tên `banner.txt`:

~~~text
src/main/resources/templates/banner.txt     (Nội dung A: packaged)
./templates/banner.txt                      (Nội dung B: external)
~~~

Đoạn 1:

~~~java
Resource packaged = resourceLoader.getResource(
        "classpath:templates/banner.txt");
~~~

Đoạn 2:

~~~java
Resource external = resourceLoader.getResource(
        "file:./templates/banner.txt");
~~~

Nếu cả hai có mặt, đoạn 1 đọc **A** còn đoạn 2 đọc **B**. Việc hai file trùng tên không khiến Spring tự ưu tiên một file cho mọi API; chính **cơ chế định vị** quyết định nội dung được mở.

Đoạn 3:

~~~java
Path path = Path.of("templates", "banner.txt");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đoạn 3 cũng đọc file **B** nếu working directory chứa thư mục `templates` phù hợp. Nếu đổi working directory mà không đổi file JAR, đoạn 1 thường vẫn đọc A, trong khi đoạn 2 và 3 có thể không tìm thấy B.

Tình huống thường gặp: một developer chạy từ IDE với working directory là project root, nên `Path.of("src/main/resources/templates/banner.txt")` đọc thành công. Sau khi đóng gói và chỉ mang JAR lên server, thư mục `src/main/resources` không còn ở nơi đó. Code thất bại dù classpath resource vẫn được đóng gói đúng. Hãy dùng `classpath:templates/banner.txt` cùng `getInputStream()` để đọc nội dung này.

## 8. Chọn cách nạp file theo nhu cầu

| Nhu cầu | Lựa chọn nên dùng | Lưu ý |
| --- | --- | --- |
| Mẫu email, dữ liệu mẫu, resource bất biến đóng gói trong ứng dụng | `classpath:...` và `Resource.getInputStream()` | Hoạt động cả khi resource nằm trong JAR |
| Đọc một file dữ liệu người dùng đặt ở máy/container | `Path`/`Files` hoặc `file:...` | Nên đưa thư mục gốc vào cấu hình triển khai |
| Đọc file dựa vào thư mục hiện hành | `Path.of("relative/path")` hoặc `file:./...` | Working directory phải được khai báo/hiểu rõ |
| Đọc một file có vị trí tuyệt đối | `Path.of("/path/...")` hoặc `file:/path/...` | Phụ thuộc OS và quyền truy cập |
| Nạp thêm cấu hình cho Spring Boot `Environment` | `spring.config.import` hoặc các thuộc tính `spring.config.*` | Chịu quy tắc tìm kiếm, profile và precedence của Boot |
| Ghi file lúc runtime | Filesystem/volume/object storage bên ngoài JAR | Không viết ngược vào classpath resource trong JAR |
| Tra cứu nhiều tài nguyên classpath theo pattern | `ResourcePatternResolver` và khi phù hợp `classpath*:` | Cần xử lý nhiều kết quả và khả năng trùng tên |

Trong production, một đường dẫn tuyệt đối do deployment cung cấp qua biến môi trường hoặc config thường dễ kiểm soát hơn việc giả định working directory. Có thể dùng đường dẫn tương đối, nhưng cần xác định rõ thư mục khởi động của service/container.

## 9. Chẩn đoán lỗi không tìm thấy file

Khi nhận `FileNotFoundException`, `NoSuchFileException` hoặc lỗi resource tương tự, kiểm tra theo thứ tự:

1. **Code đang dùng API nào?** `ResourceLoader("classpath:...")`, `ResourceLoader("file:...")`, `Path.of(...)` hay `ClassLoader.getResourceAsStream(...)`. Mỗi API có cách giải quyết path riêng.
2. **Tên resource đã tính đúng từ classpath root chưa?** Với `src/main/resources/templates/welcome.txt`, thông thường dùng `classpath:templates/welcome.txt`.
3. **Tiến trình có working directory nào?** Kiểm tra `user.dir` và `Path.of("").toAbsolutePath().normalize()` ở đúng môi trường đang lỗi.
4. **File có được đóng gói hoặc mount đúng nơi không?** Với classpath kiểm tra artifact; với filesystem kiểm tra file ngoài JAR và đường dẫn triển khai.
5. **Đang cố lấy `File` từ một resource nằm trong JAR?** Nếu chỉ cần đọc, đổi sang `getInputStream()`.
6. **Có nhầm giữa resource và config data không?** Có file `custom.yml` không đồng nghĩa Boot tự nạp các thuộc tính của nó.
7. **Quyền truy cập và chữ hoa/chữ thường có khác nhau không?** Linux thường phân biệt hoa/thường trong tên file; kiểm tra permissions và mount của container.

Ví dụ kiểm tra đúng vị trí của một file ngoài JAR:

~~~java
Path relativePath = Path.of("data", "incoming.csv");
Path absolutePath = relativePath.toAbsolutePath().normalize();

System.out.println("Working directory: "
        + Path.of("").toAbsolutePath().normalize());
System.out.println("Expected data path: " + absolutePath);
System.out.println("Exists: " + Files.exists(absolutePath));
System.out.println("Readable: " + Files.isReadable(absolutePath));
~~~

Chỉ in các đường dẫn không nhạy cảm phục vụ chẩn đoán; tránh log nội dung file bí mật hoặc token. `Files.exists` và `Files.isReadable` hữu ích để quan sát nhưng không thay thế việc xử lý ngoại lệ của thao tác đọc thật, vì filesystem có thể thay đổi giữa lúc kiểm tra và lúc sử dụng.

### Những nhầm lẫn phổ biến

**“File ở `src/main/resources` thì có thể lấy bằng `new File("src/main/resources/...")` khi deploy.”** Không đáng tin cậy. Đây là đường dẫn mã nguồn của dự án, không phải vị trí runtime của resource đã đóng gói.

**“`classpath:config/app.yml` giống `./config/app.yml`.”** Sai. Cái đầu tìm trong classpath, cái sau tìm trên filesystem theo working directory.

**“Chạy `java -jar /opt/app/app.jar` thì working directory là `/opt/app`.”** Không đúng theo mặc định. Working directory là của tiến trình gọi lệnh; có thể khác thư mục chứa JAR.

**“Có `custom.yml` trong `./config/` là Boot tự nạp.”** Không mặc định. Cơ chế tìm file `application.*` và các khai báo `spring.config.*` mới quyết định nạp những file cấu hình cụ thể nào.

**“`Resource.getFile()` là API đọc resource chung.”** Không phải. Khi resource ở bên trong JAR, cách đọc phù hợp thường là `getInputStream()`.

## 10. Bài tập thực hành

### Bài tập A: resource bên trong JAR

Tạo `src/main/resources/templates/hello.txt` với nội dung `Hello from classpath`. Viết một service đọc bằng `classpath:templates/hello.txt` và `getInputStream()`. Chạy từ IDE, sau đó package thành executable JAR và chạy lại. Quan sát rằng nội dung vẫn đọc được khi không có thư mục `src` của dự án ở nơi chạy.

### Bài tập B: cùng JAR, hai working directory

Đặt file ngoài JAR tại `/opt/catalog/data/demo.txt`. Chạy ứng dụng ở `/opt/catalog` rồi chạy lại từ `/tmp`, dùng `Path.of("data/demo.txt")` để đọc. So sánh `user.dir`, absolute path đã giải quyết và kết quả đọc. Cuối cùng đổi sang một absolute path được cấu hình tường minh để không phụ thuộc thư mục hiện hành.

### Bài tập C: config data của Boot

Đặt `catalog.mode=internal` trong `src/main/resources/application.properties` và `catalog.mode=external` trong `./config/application.properties`. Chạy JAR với working directory chứa thư mục `config` đó. Đọc giá trị `catalog.mode` qua `Environment` hoặc `@Value`. Sau đó đổi working directory và quan sát thay đổi. Thử dùng `--spring.config.additional-location=optional:file:/duong-dan-ngoai/` trỏ đến thư mục ngoài phù hợp.

### Bài tập D: phân biệt file thường và nguồn cấu hình

Tạo `./config/extra.yml` chứa một khóa chưa có ở `application.yml`. Thử đọc file bằng `ResourceLoader("file:./config/extra.yml")`, rồi đọc khóa bằng `Environment.getProperty(...)`. Sau đó khai báo `spring.config.import=optional:file:./config/extra.yml` trong `application.yml` và so sánh kết quả. Từ đó phân biệt thao tác **đọc một file** với thao tác **đưa dữ liệu file vào cấu hình Spring**.

## 11. Ghi nhớ

- **Classpath** dùng để định vị tài nguyên qua ClassLoader; resource bên trong JAR cần được đọc bằng stream.
- **Working directory** là ngữ cảnh của tiến trình; đường dẫn filesystem tương đối dựa vào ngữ cảnh này, không mặc định theo vị trí JAR.
- **File path** mô tả vị trí trên filesystem; `Path`/`Files` làm việc với file thật, còn Spring `Resource` hỗ trợ cả `classpath:` và `file:`.
- **Spring Boot config data** có quy tắc tìm kiếm và ưu tiên riêng: `classpath:/...` và `file:./...` là những vị trí khác nhau, còn `spring.config.location`/`spring.config.additional-location`/`spring.config.import` dùng để điều khiển quá trình nạp cấu hình.
- Thiết kế bền vững: resource mặc định đi cùng ứng dụng; dữ liệu hoặc cấu hình cần thay đổi được lưu bên ngoài và có đường dẫn triển khai rõ ràng.

## Tài liệu tham khảo

- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ResourceLoader`, classpath resource và filesystem resource.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): config data, vị trí tìm `application.*` và `spring.config.*`.
- [Java SE — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): tra cứu tài nguyên trên classpath.
- [Java SE — Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): đường dẫn tương đối/tuyệt đối và API filesystem.
