# Classpath resource khi chạy từ thư mục lớp hoặc từ JAR

Trong quá trình phát triển ứng dụng Spring Boot, một file nằm ở `src/main/resources` thường có thể được đọc dễ dàng. Nhưng sau khi đóng gói thành executable JAR và chạy bằng `java -jar`, một số đoạn code bất ngờ thất bại với `FileNotFoundException` hoặc `FileSystemNotFoundException`. Nguyên nhân phổ biến là code đã nhầm **tài nguyên trên classpath** với **file vật lý trên filesystem**.

Sự khác biệt này quan trọng trong chương **Chạy và đóng gói**. Khi chạy từ IDE hoặc Maven/Gradle development task, class và resource thường nằm trong các **thư mục output** như `target/classes` hoặc `build/resources/main`. Khi đóng gói bằng công cụ của Spring Boot, các resource được đưa **vào bên trong JAR**, thường ở `BOOT-INF/classes`. Resource vẫn đọc được thông qua classloader hoặc API `Resource` của Spring, nhưng không còn nhất thiết ánh xạ thành một `java.io.File` riêng lẻ.

**Quy tắc thực hành:** nếu dữ liệu chỉ cần đọc, hãy mở nó bằng `InputStream` thông qua `ClassPathResource`, `ResourceLoader` hoặc `ClassLoader.getResourceAsStream(...)`. Không xây đường dẫn trực tiếp đến `src/main/resources` và không mặc định gọi `resource.getFile()` cho resource nằm trong JAR.

Bài học đi từ cơ chế classpath, sự khác nhau giữa chạy từ thư mục lớp và executable JAR, các API đọc resource, tình huống cần file vật lý, ví dụ Spring Boot hoàn chỉnh, kiểm thử sau đóng gói, đến những lỗi dễ gặp khi triển khai.

## 1. Classpath resource là gì?

Trong Java, **classpath** là tập những vị trí mà classloader dùng để tìm class và tài nguyên. Các vị trí đó có thể là thư mục, JAR hoặc những location do classloader chuyên biệt quản lý.

Giả sử project có:

~~~text
catalog-app/
└── src/
    └── main/
        ├── java/
        │   └── com/example/catalog/
        │       ├── CatalogApplication.java
        │       └── CatalogReader.java
        └── resources/
            ├── application.yml
            └── data/
                ├── catalog.json
                └── messages.txt
~~~

Khi build, công cụ Maven hoặc Gradle thường đưa những file trong `src/main/resources` vào output resources mà runtime classpath có thể nhìn thấy.

Đường dẫn logic của resource là:

~~~text
data/catalog.json
~~~

Khi dùng prefix của Spring:

~~~text
classpath:data/catalog.json
~~~

Cụm `classpath:` không có nghĩa resource phải nằm ở một thư mục vật lý tên `classpath`. Nó có nghĩa **hãy tìm đường dẫn tương đối này trong những vị trí mà classloader đang quản lý**.

### 1.1. Source directory không phải runtime location

`src/main/resources` là nơi đặt resource trong **source tree**. Nó không phải đường dẫn bắt buộc tồn tại sau khi ứng dụng được build.

Nếu code viết:

~~~java
Path path = Path.of("src/main/resources/data/catalog.json");
String json = Files.readString(path);
~~~

đoạn này đang truy cập **đường dẫn filesystem tương đối với thư mục làm việc của tiến trình**. Nó không sử dụng classpath.

Trong lúc lập trình ở project root, đoạn code có thể hoạt động vì thư mục `src/main/resources` thực sự tồn tại. Khi triển khai bằng JAR sang một máy khác, source tree thường không còn nên đường dẫn đó có thể thất bại.

### 1.2. Resource khác class

Một file `.class` là bytecode được JVM nạp như class. Những file như `catalog.json`, `logo.png`, `schema.sql`, `messages.txt` cũng có thể nằm trên classpath nhưng không phải class Java.

Classloader có thể giúp tìm hoặc mở những tài nguyên này mà không cần biết chi tiết chúng nằm trong một directory hay archive.

### 1.3. “Classpath resource” không đồng nghĩa “bất kỳ file nào trên máy”

Nếu operator mount file dưới:

~~~text
/opt/catalog/config/custom-rules.yml
~~~

thì file đó không mặc nhiên nằm trên classpath. Có thể đọc bằng filesystem API hoặc Spring `file:` resource, nhưng không nên truy vấn bằng `classpath:` trừ khi launch configuration thực sự thêm vị trí ấy vào classpath.

## 2. Khi chạy từ thư mục lớp: resource nằm ở đâu?

Khi chạy bằng IDE hoặc development task, classpath thường bao gồm các output directory thay vì một executable JAR duy nhất.

### 2.1. Với Maven

Cấu trúc output thông dụng:

~~~text
target/
├── classes/
│   ├── com/
│   │   └── example/catalog/
│   │       ├── CatalogApplication.class
│   │       └── CatalogReader.class
│   ├── application.yml
│   └── data/
│       ├── catalog.json
│       └── messages.txt
└── test-classes/
    └── ...
~~~

Khi `target/classes` là một classpath root, việc tìm `data/catalog.json` tương ứng với:

~~~text
target/classes/data/catalog.json
~~~

Trong trường hợp này, resource có thể là file vật lý riêng trên disk, nên một số API như `getFile()` có thể trả về `File` hợp lệ.

### 2.2. Với Gradle

Output điển hình:

~~~text
build/
├── classes/
│   └── java/main/
│       └── com/example/catalog/
│           ├── CatalogApplication.class
│           └── CatalogReader.class
└── resources/
    └── main/
        ├── application.yml
        └── data/
            ├── catalog.json
            └── messages.txt
~~~

Classpath development có thể kết hợp `build/classes/java/main` với `build/resources/main` cùng các dependency JAR khác.

Vì thế **class và resource không bắt buộc nằm chung một thư mục**, miễn các classpath root tương ứng đã được thêm vào runtime.

### 2.3. Với IDE

IntelliJ IDEA, Eclipse, VS Code hoặc các extension Java có thể sử dụng layout output riêng, hoặc ủy quyền việc build/run cho Maven/Gradle.

Không nên mã hóa cứng `target/classes` hay `build/resources/main` trong Java source. Đường dẫn output là một chi tiết của build tool và run configuration.

Sử dụng classpath abstraction để cùng một đoạn code hoạt động dù IDE thay output root.

### 2.4. Mẫu đường đi

~~~text
src/main/resources/data/catalog.json
                |
                | processResources / copy resources
                v
        runtime classpath directory
                |
                +-- Maven: target/classes/data/catalog.json
                |
                +-- Gradle: build/resources/main/data/catalog.json
                |
                v
      classpath:data/catalog.json
                |
                v
         InputStream để đọc
~~~

Để file xuất hiện trong runtime, nó phải được copy hoặc đưa vào một classpath root đúng cách. Chỉ có file trong source tree không bảo đảm runtime đã nhìn thấy bản mới nhất.

## 3. Khi đóng gói Spring Boot executable JAR

Spring Boot Maven Plugin và Gradle Plugin có khả năng đóng gói executable JAR, thường còn gọi là “fat JAR” hoặc “Boot JAR”, để chạy bằng:

~~~bash
java -jar catalog-app.jar
~~~

Một layout JAR phổ biến:

~~~text
catalog-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   ├── com/example/catalog/
    │   │   ├── CatalogApplication.class
    │   │   └── CatalogReader.class
    │   └── data/
    │       ├── catalog.json
    │       └── messages.txt
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   └── other-dependency.jar
    └── classpath.idx
~~~

Đây là layout minh họa: tên dependency, launcher classes và một số file bổ trợ phụ thuộc phiên bản Spring Boot, plugin và cấu hình build. File `classpath.idx` là metadata có thể có, không phải yêu cầu của mọi JAR.

### 3.1. Tại sao có BOOT-INF/classes?

`BOOT-INF/classes` chứa class và resource của ứng dụng. Khi executable JAR được chạy bằng launcher của Boot, nội dung ở đây được expose như những classpath resources tương ứng.

Ví dụ resource vẫn có **tên classpath logic**:

~~~text
data/catalog.json
~~~

Dù vị trí trong archive là:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Vì vậy code:

~~~java
new ClassPathResource("data/catalog.json")
~~~

không cần đổi thành:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Prefix `BOOT-INF/classes` là chi tiết layout của archive do launcher xử lý, không phải một phần đường dẫn nên hard-code trong source code tiêu thụ resource.

### 3.2. JAR dependency được xử lý thế nào?

Các dependency JAR thường nằm ở `BOOT-INF/lib`. Spring Boot launcher có cơ chế nạp class và resource từ cấu trúc archive đó.

Một resource có thể đến từ:

- Class và resources của ứng dụng trong `BOOT-INF/classes`.
- Một dependency JAR trong `BOOT-INF/lib`.
- Những vị trí classpath khác mà launcher hoặc classloader thực sự expose.

Điều này giải thích vì sao hai resource có cùng tên có thể tồn tại ở nhiều dependency khác nhau và vì sao `ClassLoader.getResource(...)` không nhất thiết trả “tất cả bản sao”.

### 3.3. Khi chạy JAR, không còn thư mục src/main/resources

Giả sử bạn copy duy nhất file:

~~~text
catalog-app.jar
~~~

sang server và chạy:

~~~bash
java -jar catalog-app.jar
~~~

Không cần copy thư mục `src/main/resources` cạnh file JAR để những **packaged resources** đã được bundle vào archive hoạt động.

Nếu code vẫn phụ thuộc:

~~~text
src/main/resources/data/catalog.json
~~~

thì nó phụ thuộc một đường dẫn trong source tree, chứ không dựa vào classpath đúng cách.

### 3.4. Không nên tự xử lý nested JAR path

Một URL resource trong executable JAR có thể mang dạng URL/protocol do launcher cung cấp, thay vì `file:/...` thuần túy. Cấu trúc URL chính xác có thể khác qua phiên bản Boot.

Đừng tự tách chuỗi URL bằng `split("!")` để tạo filesystem path cho nested JAR. Hãy để classloader hoặc `Resource.getInputStream()` xử lý.

## 4. So sánh thư mục lớp và JAR

| Tiêu chí | Chạy từ output directory | Chạy từ Boot executable JAR |
| --- | --- | --- |
| Class ứng dụng | File `.class` riêng | Bên trong `BOOT-INF/classes` |
| Resource ứng dụng | File nằm dưới output resources | Entry trong `BOOT-INF/classes` |
| Dependency | JAR trên runtime classpath | Thường nằm trong `BOOT-INF/lib` |
| `getResourceAsStream` | Có thể đọc | Có thể đọc |
| `ClassPathResource.getInputStream` | Có thể đọc | Có thể đọc |
| `ClassPathResource.getFile` | Có thể hoạt động | Không nên kỳ vọng hoạt động |
| `Paths.get("src/main/resources/...")` | Có thể tình cờ hoạt động tại project root | Thường thất bại sau deploy |
| Viết ngược resource | Có thể sửa file output nhưng không nên | Không thể coi entry JAR là file ghi sửa thông thường |
| Nơi phụ thuộc vào | Output folders | Launcher, JAR layout và classloader |
| Đường dẫn logic trong code | `classpath:data/catalog.json` | **Vẫn vậy** |

Tính bền vững của code đến từ cách truy cập dựa trên **classpath abstraction**, không phải biết resource nằm trong cấu trúc file vật lý nào.

## 5. Cách 1: đọc bằng ClassLoader.getResourceAsStream

Java có API chuẩn để mở resource trên classpath:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class CatalogTextLoader {

    public String loadCatalog() throws IOException {
        ClassLoader classLoader =
                Thread.currentThread().getContextClassLoader();

        try (InputStream input =
                     classLoader.getResourceAsStream(
                             "data/catalog.json")) {

            if (input == null) {
                throw new IOException(
                        "Classpath resource not found: data/catalog.json"
                );
            }

            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Điểm chính:

1. Tên resource không có prefix `classpath:` vì đây là API của Java `ClassLoader`.
2. Với `ClassLoader.getResourceAsStream`, đường dẫn được hiểu tương đối với **classpath root**.
3. Nếu không tìm thấy resource, phương thức có thể trả `null`; cần kiểm tra.
4. Đóng stream bằng `try-with-resources`.
5. Dùng encoding tường minh, ví dụ UTF-8.

### 5.1. Không thêm dấu / ở đầu với ClassLoader API

Nên dùng:

~~~java
classLoader.getResourceAsStream("data/catalog.json");
~~~

Không dùng một dấu `/` đầu đường dẫn theo thói quen của `Class.getResourceAsStream`:

~~~java
classLoader.getResourceAsStream("/data/catalog.json");
~~~

Đối với API của `ClassLoader`, tên resource thông thường không bắt đầu bằng dấu gạch chéo.

### 5.2. Context classloader không phải luôn bắt buộc

Có thể dùng classloader của chính class:

~~~java
InputStream input =
        CatalogTextLoader.class.getClassLoader()
                .getResourceAsStream("data/catalog.json");
~~~

Context classloader thường hữu ích trong các framework dùng classloader đặc biệt để tải module. Trong một ứng dụng đơn giản, classloader của class đang chạy cũng có thể đủ.

Tuy nhiên, không nên trộn nhiều classloader tùy ý nếu đang làm việc với plugin architecture hoặc executable JAR; việc lựa chọn classloader có thể ảnh hưởng resource nào được tìm thấy.

## 6. Cách 2: Class.getResourceAsStream và dấu / đầu đường dẫn

Java còn có:

~~~java
InputStream getResourceAsStream(String name);
~~~

trên đối tượng `Class<?>`.

Ví dụ:

~~~java
try (InputStream input =
             CatalogTextLoader.class.getResourceAsStream(
                     "/data/catalog.json")) {

    if (input == null) {
        throw new IOException("Resource is missing");
    }

    // Đọc stream...
}
~~~

Với `Class.getResourceAsStream`:

- Tên bắt đầu bằng `/` là đường dẫn tuyệt đối **theo classpath root**.
- Tên không bắt đầu bằng `/` là đường dẫn **tương đối với package của class**.

Giả sử `CatalogTextLoader` thuộc package:

~~~text
com.example.catalog
~~~

Khi gọi:

~~~java
CatalogTextLoader.class.getResourceAsStream(
        "data/catalog.json"
);
~~~

Java sẽ tìm resource tương đối theo package, tương ứng với:

~~~text
com/example/catalog/data/catalog.json
~~~

Còn khi gọi:

~~~java
CatalogTextLoader.class.getResourceAsStream(
        "/data/catalog.json"
);
~~~

Java tìm resource từ classpath root:

~~~text
data/catalog.json
~~~

### 6.1. Bảng phân biệt ba đường dẫn

| API | Đường dẫn | Nơi bắt đầu tìm |
| --- | --- | --- |
| `ClassLoader.getResourceAsStream` | `data/catalog.json` | Classpath root |
| `SomeClass.class.getResourceAsStream` | `/data/catalog.json` | Classpath root |
| `SomeClass.class.getResourceAsStream` | `data/catalog.json` | Package chứa `SomeClass` |

Đây là một nguyên nhân phổ biến khiến code trả `null` dù file có trong artifact. Trước khi nghi ngờ packaging, hãy kiểm tra bạn đang dùng API nào và đường dẫn là tuyệt đối hay tương đối.

### 6.2. Không đưa chuỗi classpath: vào Java ClassLoader API

Đoạn sau thường không có ý nghĩa theo cách người mới kỳ vọng:

~~~java
classLoader.getResourceAsStream(
        "classpath:data/catalog.json"
);
~~~

`classpath:` là prefix được Spring `ResourceLoader` hiểu; `ClassLoader.getResourceAsStream` của Java không tự xử lý prefix đó.

## 7. Cách 3: ClassPathResource của Spring

Spring Framework cung cấp `Resource` abstraction. Với resource trên classpath, implementation quen thuộc là `ClassPathResource`:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
~~~

Ví dụ:

~~~java
public String loadCatalog() throws IOException {
    Resource resource =
            new ClassPathResource("data/catalog.json");

    try (InputStream input = resource.getInputStream()) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
    }
}
~~~

`ClassPathResource` giúp code không cần tự xử lý `null` từ `ClassLoader.getResourceAsStream` như trong ví dụ Java thuần; khi resource không thể mở, thao tác có thể ném `IOException` phù hợp.

### 7.1. Resource mô tả location, không phải luôn là File

`Resource` có nhiều phương thức:

~~~java
resource.exists();
resource.isReadable();
resource.getFilename();
resource.getDescription();
resource.getInputStream();
resource.getURL();
resource.getURI();
resource.getFile();
~~~

Nhưng không có nghĩa **mọi implementation hỗ trợ mọi phương thức với cùng ý nghĩa**.

Ví dụ `getInputStream()` phù hợp để đọc resource nằm trong JAR. `getFile()` chỉ thích hợp nếu resource thực sự có thể biểu diễn dưới dạng file vật lý.

### 7.2. Cần kiểm tra source của ClassPathResource?

Ví dụ:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

System.out.println(resource.getDescription());
~~~

`getDescription()` hữu ích khi chẩn đoán vì nó mô tả vị trí resource. Tuy nhiên, không nên dựa vào chuỗi description để xác định filesystem path hay định danh nghiệp vụ.

### 7.3. ClassPathResource có dùng được ở cả hai chế độ?

Có, khi resource thực sự có trên runtime classpath và classloader tìm thấy nó. Cùng đoạn code có thể đọc được:

~~~text
target/classes/data/catalog.json
~~~

hoặc:

~~~text
catalog-app.jar!/BOOT-INF/classes/data/catalog.json
~~~

Dạng `jar!/...` ở đây chỉ là ký hiệu minh họa vị trí bên trong archive, không phải một đường dẫn `File` có thể mở trực tiếp.

## 8. Cách 4: ResourceLoader trong Spring Boot bean

Trong ứng dụng Spring Boot, `ResourceLoader` có thể được inject như một dependency hạ tầng:

~~~java
package com.example.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CatalogReader {

    private final ResourceLoader resourceLoader;

    public CatalogReader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String read() throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:data/catalog.json"
        );

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Ở đây prefix `classpath:` là cú pháp dành cho Spring `ResourceLoader`. Spring chọn implementation thích hợp, thường là `ClassPathResource` đối với prefix này.

### 8.1. Vì sao inject ResourceLoader?

- Không cần tạo `ClassPathResource` lặp lại khắp code.
- Dễ chọn location từ cấu hình của ứng dụng.
- Có thể đọc resource ở classpath hoặc filesystem bằng cùng abstraction.
- Giảm sự phụ thuộc vào details của classloader trong service.
- Thuận tiện khi tích hợp vào bean lifecycle của Spring.

### 8.2. Không phải mọi location nên do người dùng tự quyết định

Ví dụ service đọc:

~~~java
resourceLoader.getResource(location);
~~~

Nếu `location` được lấy trực tiếp từ request HTTP của người dùng, ứng dụng có thể bị dẫn đến đọc `file:` resource nhạy cảm.

Hãy chỉ dùng resource location đã được cấu hình từ nguồn đáng tin cậy hoặc áp dụng allowlist prefix/thư mục rõ ràng. `ResourceLoader` là công cụ truy cập resource, không phải cơ chế phân quyền.

## 9. Cách 5: inject Resource bằng @Value

Spring cũng hỗ trợ bind trực tiếp một resource location vào dependency:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class BannerReader {

    private final Resource banner;

    public BannerReader(
            @Value("classpath:data/messages.txt") Resource banner) {
        this.banner = banner;
    }
}
~~~

Sau đó:

~~~java
public String readBanner() throws IOException {
    try (InputStream input = banner.getInputStream()) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
    }
}
~~~

Cách này phù hợp khi resource location là cố định.

Nếu location thay đổi theo môi trường, có thể kết hợp `@ConfigurationProperties` hoặc một property chỉ định resource location, rồi inject qua `ResourceLoader`. Tránh rải cùng một chuỗi đường dẫn trong nhiều service.

### 9.1. Resource khác chuỗi nội dung

`@Value("classpath:data/messages.txt") Resource banner` cho bạn một **đối tượng resource**, không phải tự động đọc toàn bộ file thành string.

Bạn vẫn cần mở stream hoặc sử dụng parser phù hợp.

## 10. Vì sao Resource.getFile() hay thất bại sau khi đóng gói?

Đây là lỗi kinh điển:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

File file = resource.getFile();
String content = Files.readString(file.toPath());
~~~

Trong development, `resource.getFile()` có thể trả về:

~~~text
.../target/classes/data/catalog.json
~~~

Sau khi đóng gói, resource chỉ còn là một entry trong executable JAR:

~~~text
catalog-app.jar
└── BOOT-INF/classes/data/catalog.json
~~~

Một entry trong JAR không phải là file vật lý riêng mà `java.io.File` có thể trỏ tới trực tiếp. Do đó `getFile()` có thể ném lỗi như:

~~~text
java.io.FileNotFoundException:
class path resource [data/catalog.json]
cannot be resolved to absolute file path
because it does not reside in the file system
~~~

Thông điệp chính xác tùy phiên bản Spring và loại resource.

### 10.1. Cách sửa phù hợp: InputStream

Thay vì:

~~~java
File file = resource.getFile();
String json = Files.readString(file.toPath());
~~~

hãy dùng:

~~~java
try (InputStream input = resource.getInputStream()) {
    String json = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

Với file JSON, nếu parser hỗ trợ `InputStream`, nên truyền stream trực tiếp thay vì buộc phải đọc ra `String`.

### 10.2. getURL() không đồng nghĩa getFile()

Một resource có thể cung cấp `URL` hợp lệ:

~~~java
URL url = resource.getURL();
~~~

nhưng URL có thể trỏ đến resource trong archive với protocol đặc biệt. Không nên lập tức làm:

~~~java
Path path = Paths.get(url.toURI());
~~~

và mặc định có một filesystem provider hiểu được URI đó. `Paths.get(...)` có thể thất bại với các URI không thuộc filesystem mặc định hoặc archive chưa được mount theo provider thích hợp.

Nếu mục tiêu chỉ là đọc nội dung, `InputStream` đơn giản và ít phụ thuộc vào môi trường hơn.

### 10.3. File#getPath và URL#getFile là hai khái niệm khác

Tên method `URL.getFile()` có thể gây hiểu nhầm. Nó trả về phần đường dẫn của URL theo semantics của `URL`, **không** trả một `java.io.File` đã được hệ điều hành xác nhận tồn tại.

Đừng dùng `new File(url.getFile())` như công thức đọc classpath resource đóng trong JAR. Cách đó còn dễ lỗi khi đường dẫn có khoảng trắng, ký tự Unicode hoặc URL encoding.

## 11. Nếu thư viện bắt buộc nhận File hoặc Path thì làm gì?

Một số API cũ chỉ chấp nhận `File` hoặc `Path`, không nhận `InputStream`. Khi đó có thể cần **copy resource ra một file tạm**, rồi đưa file đó cho thư viện.

Ví dụ:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public final class LegacyFileAdapter {

    public void process() throws IOException {
        Resource source =
                new ClassPathResource("data/catalog.json");

        Path temporary = Files.createTempFile(
                "catalog-",
                ".json"
        );

        try {
            try (InputStream input = source.getInputStream()) {
                Files.copy(
                        input,
                        temporary,
                        StandardCopyOption.REPLACE_EXISTING
                );
            }

            LegacyParser.parse(temporary.toFile());
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

`LegacyParser` là class giả định chỉ nhận file. Trong code thực tế, thay bằng API tương ứng của thư viện đang dùng.

### 11.1. Đừng xóa file khi thư viện còn sử dụng

Ví dụ trên giả định `LegacyParser.parse(...)` xử lý file **đồng bộ** và hoàn tất trước khi method trả về.

Nếu thư viện giữ `Path` và xử lý bất đồng bộ, không được xóa file ngay trong `finally`. Cần quản lý vòng đời file tạm theo thời gian sử dụng thực sự, có chiến lược cleanup và kiểm soát quyền truy cập.

### 11.2. Tên file, permission và dung lượng

Khi copy resource ra file tạm:

- Dùng API tạo file an toàn như `Files.createTempFile`.
- Không ghép tên file từ input không tin cậy mà không kiểm tra.
- Kiểm soát quyền truy cập nếu nội dung nhạy cảm.
- Chú ý dung lượng và chính sách cleanup.
- Không mặc định file tạm sẽ tồn tại qua lần restart/container recreation.

### 11.3. Khi nào nên đổi thư viện?

Nếu một thư viện hỗ trợ cả `File` và `InputStream`, hãy chọn `InputStream` cho resource đóng trong JAR. Đừng copy ra disk chỉ vì ví dụ cũ sử dụng `File`.

## 12. Không thể xem packaged resource là nơi ghi dữ liệu runtime

Một file `src/main/resources/data/catalog.json` thường được đóng gói vào artifact như **dữ liệu đi kèm ứng dụng**. Trong executable JAR, entry đó không phải một file có thể ghi đè như file cấu hình bên ngoài.

Đoạn code như:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

Files.writeString(
        resource.getFile().toPath(),
        "updated"
);
~~~

có thể hoạt động tình cờ trong development nếu resource nằm trên disk. Nhưng sau deploy, việc truy cập file có thể thất bại; và kể cả khi sửa được một file trong output directory, thay đổi đó không trở thành phần của source artifact được quản lý.

### 12.1. Phân biệt packaged defaults với dữ liệu biến đổi

Một thiết kế thường gặp:

- **Classpath resource:** mẫu mặc định, schema, template, dữ liệu seed nhỏ, file cấu hình đóng gói cùng release.
- **External file:** dữ liệu có thể thay đổi theo môi trường hoặc theo người dùng.
- **Database/object storage:** dữ liệu nghiệp vụ hoặc dữ liệu cần lưu lâu dài, đồng bộ qua nhiều instance.

Nếu ứng dụng cần lưu kết quả xử lý hoặc cho operator sửa file mà không rebuild, hãy dùng thư mục ngoài artifact.

### 12.2. Ví dụ ghi vào external directory

~~~java
Path outputDirectory = Path.of("/var/lib/catalog/export");

Files.createDirectories(outputDirectory);

Path destination = outputDirectory.resolve("catalog-export.json");

Files.writeString(
        destination,
        "{ \"status\": \"exported\" }",
        StandardCharsets.UTF_8
);
~~~

Đường dẫn trên chỉ minh họa môi trường Linux/container. Trong ứng dụng thật, dùng configuration properties để chọn directory, kiểm tra quyền ghi, xử lý lỗi I/O và tránh ghi đè ngoài ý muốn.

### 12.3. Image container và filesystem

Khi ứng dụng chạy trong Docker/Kubernetes, resource đã đóng gói ở trong JAR hoặc image vẫn có thể được đọc qua classpath, nhưng dữ liệu cần lưu nên nằm ở volume hoặc dịch vụ lưu trữ thích hợp.

Không kỳ vọng sửa một classpath resource trong image sẽ tồn tại sau khi Pod được thay thế.

## 13. Ví dụ hoàn chỉnh: đọc JSON bằng InputStream

Giả sử có file:

~~~text
src/main/resources/data/catalog.json
~~~

Nội dung:

~~~json
{
  "version": 1,
  "items": [
    { "id": "A100", "name": "Notebook" },
    { "id": "B200", "name": "Pen" }
  ]
}
~~~

Có hai cách đọc: đọc thành chuỗi hoặc nhờ Jackson parse trực tiếp từ stream.

### 13.1. Đọc thành chuỗi UTF-8

~~~java
@Service
public class CatalogTextService {

    private final ResourceLoader loader;

    public CatalogTextService(ResourceLoader loader) {
        this.loader = loader;
    }

    public String getJson() throws IOException {
        Resource resource =
                loader.getResource("classpath:data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Với file nhỏ, cách này đủ đơn giản. Với file lớn, `readAllBytes()` có thể dùng nhiều heap vì đưa toàn bộ nội dung vào memory.

### 13.2. Parse trực tiếp bằng Jackson

Nếu project có Jackson Databind:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CatalogJsonService {

    private final ResourceLoader loader;
    private final ObjectMapper objectMapper;

    public CatalogJsonService(
            ResourceLoader loader,
            ObjectMapper objectMapper) {
        this.loader = loader;
        this.objectMapper = objectMapper;
    }

    public JsonNode load() throws IOException {
        Resource resource =
                loader.getResource("classpath:data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            return objectMapper.readTree(input);
        }
    }
}
~~~

`ObjectMapper` có thể được Spring Boot auto-configure khi Jackson có mặt và cấu hình phù hợp. Nếu project chỉ dùng `spring-boot-starter` cơ bản mà không có Jackson, cần khai báo dependency JSON tương ứng hoặc tự đăng ký parser.

### 13.3. Tại sao truyền InputStream tốt hơn Path?

Jackson có API đọc `InputStream`, nên cùng logic chạy được khi resource ở `target/classes`, `build/resources/main`, trong executable JAR hoặc trong một JAR dependency.

Không cần biết loại URL, mount filesystem hay đường dẫn tạm.

### 13.4. Nếu file không có trên classpath

`resource.getInputStream()` có thể ném `IOException`. Đây là tín hiệu cần xử lý rõ:

- Nếu catalog bắt buộc: fail fast khi startup hoặc báo lỗi có ý nghĩa.
- Nếu catalog tùy chọn: cung cấp fallback được định nghĩa trước.
- Nếu tên file do cấu hình cung cấp: log location đã được chuẩn hóa, không làm lộ secret.

Đừng im lặng nuốt exception và trả dữ liệu rỗng khi dữ liệu bắt buộc để ứng dụng hoạt động đúng.

## 14. Ví dụ Spring Boot: ApplicationRunner đọc resource lúc khởi động

Đây là một ứng dụng minh họa tự chứa.

### 14.1. Cấu trúc project

~~~text
catalog-app/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/catalog/
    │   │   ├── CatalogApplication.java
    │   │   └── CatalogStartupReader.java
    │   └── resources/
    │       └── data/
    │           └── catalog.json
    └── test/
        └── java/com/example/catalog/
            └── CatalogResourceTest.java
~~~

### 14.2. Maven dependencies và plugin

Giả sử project đã sử dụng Spring Boot parent hoặc dependency management phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Đoạn này là phần cần thêm vào `pom.xml` đã có phần project/parent hợp lệ, không phải một POM độc lập.

### 14.3. Class khởi động

`CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 14.4. Reader chạy khi context đã sẵn sàng cho runner

`CatalogStartupReader.java`:

~~~java
package com.example.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;

@Component
public class CatalogStartupReader implements ApplicationRunner {

    private final ResourceLoader resourceLoader;

    public CatalogStartupReader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    @Override
    public void run(ApplicationArguments args) throws IOException {
        Resource resource =
                resourceLoader.getResource(
                        "classpath:data/catalog.json"
                );

        try (InputStream input = resource.getInputStream()) {
            String json = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            System.out.println("Source: " + resource.getDescription());
            System.out.println("Catalog JSON: " + json);
        }
    }
}
~~~

Nếu resource thiếu, runner báo lỗi thay vì cho ứng dụng giả vờ startup thành công với dữ liệu rỗng.

### 14.5. Chạy khi đang phát triển

Với Maven:

~~~bash
mvn spring-boot:run
~~~

Hoặc chạy main class từ IDE.

Trong chế độ development điển hình, `catalog.json` nằm ở output resources. Reader mở stream và in nội dung.

### 14.6. Đóng gói và chạy JAR

~~~bash
mvn package
java -jar target/catalog-app-0.0.1-SNAPSHOT.jar
~~~

Tên file JAR là ví dụ: thay bằng artifact thực tế mà build tạo ra.

Khi chạy từ JAR, code không cần sửa:

~~~java
resourceLoader.getResource(
        "classpath:data/catalog.json"
);
~~~

vẫn là đường dẫn logic đúng nếu build đã đưa resource vào archive.

### 14.7. Quan sát bằng jar tf

Sau khi build, dùng:

~~~bash
jar tf target/catalog-app-0.0.1-SNAPSHOT.jar
~~~

Một dòng output mong đợi:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Nếu không tìm thấy, vấn đề có thể nằm ở quá trình đóng gói resource, không phải riêng Spring `ResourceLoader`.

### 14.8. Tại sao ví dụ không dùng getFile?

Vì mục tiêu là **cùng một đoạn code chạy đúng trong hai môi trường**. `getInputStream()` đáp ứng mục tiêu đó, còn `getFile()` buộc resource phải biểu diễn được dưới dạng file vật lý.

## 15. Đóng gói với Gradle: processResources và bootJar

Trong project có Spring Boot Gradle plugin và Java plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
~~~

Phiên bản plugin và dependency management được xác định ở build script/settings của project thực tế; đoạn trên chỉ minh họa plugin IDs.

Đối với resource mặc định:

~~~text
src/main/resources/data/catalog.json
~~~

Gradle Java plugin thường copy resource vào:

~~~text
build/resources/main/data/catalog.json
~~~

thông qua task `processResources`; Spring Boot `bootJar` có thể đóng gói nó vào:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Các lệnh thường dùng:

~~~bash
./gradlew bootRun
./gradlew bootJar
java -jar build/libs/catalog-app-0.0.1-SNAPSHOT.jar
~~~

Tên JAR và nội dung task phụ thuộc configuration hiện tại.

### 15.1. Phân biệt jar và bootJar

Gradle task `jar` thông thường có thể tạo một plain JAR không bao gồm dependency runtime theo cùng cách với executable Boot JAR. `bootJar` được plugin Spring Boot thiết kế cho việc đóng gói executable archive.

Vì vậy, nếu resource được đọc đúng nhưng `java -jar` báo thiếu main class hoặc dependency, hãy kiểm tra mình đang chạy **đúng artifact** và đúng packaging task, không chỉ kiểm tra đường dẫn resource.

### 15.2. Custom resource filtering

Nếu build dùng resource filtering hoặc chỉnh `sourceSets`/`processResources`, có thể có những file bị bỏ qua hoặc bị biến đổi nội dung trước khi đóng gói.

Khi chẩn đoán, kiểm tra cả:

~~~text
src/main/resources/data/catalog.json
build/resources/main/data/catalog.json
BOOT-INF/classes/data/catalog.json
~~~

Không mặc định file nguồn là byte-for-byte giống bản đã đưa vào JAR nếu build có bước biến đổi.

## 16. Đọc resource trong thư viện dependency

Không phải resource nào cũng do ứng dụng sở hữu. Một thư viện có thể đóng gói template hoặc metadata riêng.

Ví dụ dependency:

~~~text
reporting-support.jar
└── templates/
    └── default-report.html
~~~

Code ứng dụng có thể đọc:

~~~java
Resource template =
        new ClassPathResource(
                "templates/default-report.html"
        );

try (InputStream input = template.getInputStream()) {
    // Đọc nội dung template...
}
~~~

Điều kiện là dependency đó có mặt trong runtime classpath và resource thật sự tồn tại đúng tên.

### 16.1. Trùng tên resource giữa nhiều dependency

Nếu hai JAR đều chứa:

~~~text
templates/default-report.html
~~~

thì `ClassLoader.getResource(...)` hoặc `ClassPathResource` thường giải quyết một resource theo thứ tự tìm kiếm classloader. Không nên xem đó là cơ chế chọn resource ưu tiên có tính chất nghiệp vụ ổn định.

Nếu cần tất cả các bản cùng tên, có thể dùng `ClassLoader.getResources(...)` hoặc Spring `ResourcePatternResolver` với `classpath*:`.

### 16.2. Tránh đặt tên quá chung trong thư viện

Với thư viện phát triển để dùng lại, nên tổ chức resource dưới một namespace ổn định:

~~~text
META-INF/com-example-reporting/
└── templates/
    └── default-report.html
~~~

Cách này giảm khả năng xung đột với thư viện khác và giúp pattern scanning rõ ràng hơn.

### 16.3. Không hard-code BOOT-INF/lib

Thư viện có thể được chạy như JAR trong development, như nested JAR trong Boot executable archive, hoặc theo một cơ chế classpath khác.

Đường dẫn để đọc nên là đường dẫn classpath logic được thư viện công bố, không phải `BOOT-INF/lib/<dependency>.jar!/....` do ứng dụng tự tạo.

## 17. Tìm nhiều resource và khác biệt với đọc một resource

Khi biết chính xác tên file:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");
~~~

là cách đơn giản.

Khi muốn tìm nhiều file JSON:

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
        "classpath*:data/**/*.json"
);
~~~

Import:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
~~~

### 17.1. classpath: và classpath*:

- `classpath:` thường giải quyết một classpath location hoặc pattern từ root được chọn.
- `classpath*:` cho phép tìm nhiều location phù hợp trên runtime classpath, kể cả trong các dependency JAR mà resolver truy cập được.

Nhưng việc quét wildcard phụ thuộc cách classloader và archive expose các directory/entry. Khi xây thư viện cần discovery, nên đặt resource trong thư mục con cố định như `META-INF/myapp/schemas/`, tránh quét wildcard ở root JAR.

### 17.2. Một resource vẫn được đọc bằng stream

Dù resolver trả nhiều `Resource`, cách đọc nên giữ nguyên:

~~~java
for (Resource resource : resources) {
    try (InputStream input = resource.getInputStream()) {
        // Parse từng tài nguyên...
    }
}
~~~

Không chuyển chúng thành `File` chỉ vì cần vòng lặp trên nhiều tài nguyên.

### 17.3. Không dựa vào thứ tự trả về

Khi quét nhiều classpath roots, thứ tự resource có thể phụ thuộc classloader và archive. Nếu thứ tự áp dụng rule quan trọng, ứng dụng cần một chính sách priority tường minh.

## 18. Phân biệt classpath resource với external configuration

Spring Boot còn có cơ chế **externalized configuration**. Những file như `application.yml` có thể được nạp từ nhiều location theo quy tắc config data và property sources.

Đây là chuyện **cấu hình ứng dụng**; nó không đồng nghĩa mọi resource đọc bằng `ClassPathResource` tự động áp dụng quy tắc ưu tiên của `application.yml`.

Ví dụ:

~~~java
new ClassPathResource("data/catalog.json");
~~~

chỉ đọc resource có đường dẫn logic `data/catalog.json`. Nó không tự tìm file thay thế trong `/etc/catalog` chỉ vì cùng tên.

### 18.1. Chọn classpath khi nào?

Dùng classpath cho những dữ liệu nên gắn với version artifact:

- JSON schema mặc định.
- Template đi kèm release.
- Mapping cấu trúc không cần operator thay đổi thường xuyên.
- Seed dữ liệu dùng trong quá trình phát triển/test hoặc khi khởi tạo.
- Tài nguyên tĩnh được publish cùng ứng dụng.

### 18.2. Chọn external file khi nào?

Dùng external file khi giá trị cần thay đổi mà không rebuild:

- File cấu hình riêng của môi trường.
- Certificate/key được mount từ secret store.
- Dataset do operator cập nhật.
- Nội dung do ứng dụng xuất ra.
- File đầu vào do hệ thống khác cung cấp.

Ví dụ Spring `ResourceLoader`:

~~~java
Resource resource =
        resourceLoader.getResource(
                "file:/opt/catalog/config/custom-rules.yml"
        );
~~~

Hoặc Java NIO:

~~~java
Path path = Path.of("/opt/catalog/config/custom-rules.yml");
try (InputStream input = Files.newInputStream(path)) {
    // ...
}
~~~

Trong hệ thống thật, kiểm tra quyền đọc, đường dẫn, encoding, kích thước file và cách cấu hình location.

### 18.3. Không nên kết hợp “fallback” ngầm không có quy tắc

Nếu ứng dụng ưu tiên external file rồi fallback về classpath default, hãy diễn đạt rõ:

~~~java
Resource external =
        resourceLoader.getResource(
                "file:/opt/catalog/config/catalog.json"
        );

Resource selected = external.exists()
        ? external
        : resourceLoader.getResource(
                "classpath:data/catalog-default.json"
        );
~~~

Ví dụ này chỉ chọn nguồn; lúc đọc vẫn cần xử lý lỗi I/O. Đối với file quan trọng, có thể fail fast nếu external file được chỉ định nhưng không đọc được, thay vì tự động fallback âm thầm.

## 19. Resource của ứng dụng web: static và templates

Spring Boot web applications thường có resource dưới:

~~~text
src/main/resources/
├── static/
│   ├── css/site.css
│   └── images/logo.png
└── templates/
    └── invoice.html
~~~

Khi đóng gói executable JAR, các file cũng được đưa vào `BOOT-INF/classes` theo resource layout tương ứng.

### 19.1. Static resources

Một static resource có thể được Spring MVC phục vụ thông qua static resource handling khi cấu hình phù hợp, ví dụ:

~~~text
GET /css/site.css
GET /images/logo.png
~~~

Điều đó **không yêu cầu file nằm dưới một thư mục filesystem public cạnh JAR**. Framework có thể đọc resource qua classpath abstraction.

### 19.2. Templates

Thymeleaf và một số template engine thường tìm template dưới `classpath:/templates/` theo cấu hình mặc định hoặc theo resolver riêng.

Không cần gọi `new File("src/main/resources/templates/invoice.html")` để engine render template. Hãy để template resolver xử lý resource location.

### 19.3. URL HTTP không giống classpath URL

Một static file có thể được truy cập qua HTTP như:

~~~text
https://example.test/images/logo.png
~~~

nhưng URL HTTP là public route do web framework phục vụ. Resource classpath bên dưới có thể là:

~~~text
classpath:/static/images/logo.png
~~~

Chúng là hai lớp định danh khác nhau: một bên là URL của client, một bên là resource location của server.

## 20. Kiểm thử resource trong môi trường phát triển

Một test nhỏ có thể xác nhận resource được build vào test/runtime classpath.

Ví dụ JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

class CatalogResourceTest {

    @Test
    void catalogIsAvailableOnClasspath() throws IOException {
        Resource resource =
                new ClassPathResource("data/catalog.json");

        assertThat(resource.exists()).isTrue();

        try (InputStream input = resource.getInputStream()) {
            String json = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            assertThat(json).contains("\"items\"");
        }
    }
}
~~~

Test này dùng `ClassPathResource` và đọc stream; nó không yêu cầu `getFile()`. Do đó logic của nó phù hợp với cả resource ở thư mục output và resource trong JAR.

### 20.1. src/test/resources có nằm trong production JAR không?

Thông thường, resource trong:

~~~text
src/test/resources/
~~~

được đưa vào **test classpath**, không phải production executable JAR.

Nếu test tìm thấy resource nhưng sau deploy không tìm thấy, kiểm tra có phải file chỉ được đặt trong `src/test/resources` hay không.

Resource cần dùng khi chạy production phải nằm trong một runtime source set/dependency được đóng gói phù hợp, thường là `src/main/resources`.

### 20.2. Test thuần classpath chưa chứng minh packaged runtime đúng

Một unit test hoặc `@SpringBootTest` chạy trong IDE thường dùng output directories. Test pass chưa chứng minh mọi code đều hoạt động khi resource nằm trong executable JAR.

Đặc biệt, code gọi `getFile()` có thể pass test trong IDE nhưng fail sau đóng gói.

Vì vậy cần ít nhất một phép kiểm tra **sau đóng gói** khi ứng dụng có yêu cầu quan trọng về resource loading.

## 21. Kiểm thử sau khi đóng gói JAR

Quy trình smoke test có thể gồm:

1. Build artifact.
2. Kiểm tra file resource đã nằm trong JAR.
3. Chạy `java -jar` từ một thư mục không phải project root.
4. Quan sát ứng dụng đọc resource thành công.
5. Xác nhận không có code phụ thuộc `src/main/resources`.

Với Maven:

~~~bash
mvn package
jar tf target/catalog-app-0.0.1-SNAPSHOT.jar
java -jar target/catalog-app-0.0.1-SNAPSHOT.jar
~~~

Với Gradle:

~~~bash
./gradlew bootJar
jar tf build/libs/catalog-app-0.0.1-SNAPSHOT.jar
java -jar build/libs/catalog-app-0.0.1-SNAPSHOT.jar
~~~

Đường dẫn file JAR chỉ minh họa. Thay bằng artifact thực tế.

### 21.1. Vì sao chạy từ thư mục khác hữu ích?

Nếu code có:

~~~java
Path.of("src/main/resources/data/catalog.json");
~~~

nó có thể tình cờ hoạt động khi working directory là project root.

Khi bạn chạy JAR từ một thư mục sạch chỉ chứa artifact, relative path đó không còn tồn tại. Đây là cách thực tế để phát hiện việc code đã nhầm classpath location với filesystem path.

### 21.2. Kiểm tra content của JAR

Dùng:

~~~bash
jar tf catalog-app.jar
~~~

và tìm entry:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

Lệnh `jar tf` liệt kê các entry của archive; nó không tự xác nhận rằng parser nghiệp vụ đọc nội dung đúng. Cần kết hợp với test chạy thực tế.

### 21.3. Đừng chỉ kiểm tra manifest

Manifest/launcher cho biết cách artifact khởi động. Một JAR có manifest hợp lệ vẫn có thể thiếu resource do build configuration bỏ qua source resource directory.

## 22. java -cp và java -jar khác nhau thế nào?

Hai cách khởi động này sử dụng classpath theo cơ chế khác nhau.

### 22.1. Khi chạy class trực tiếp

Ví dụ, nếu `target/classes` có class chính và các dependency đã được cấu hình ngoài:

~~~bash
java -cp target/classes com.example.catalog.CatalogApplication
~~~

Lệnh trên chỉ minh họa cấu trúc; một ứng dụng Spring Boot thực tế cần các dependency JAR trên classpath. Nếu chỉ có `target/classes` mà thiếu Spring Boot dependencies, app không thể khởi động đầy đủ.

Với classpath development đầy đủ, resource nằm trực tiếp dưới output root thường được giải quyết dưới dạng file URL.

### 22.2. Khi chạy executable JAR

~~~bash
java -jar catalog-app.jar
~~~

JVM chạy launcher được ghi trong manifest; launcher Spring Boot tổ chức classpath nội bộ để nhìn thấy `BOOT-INF/classes` và nested dependencies.

Vì vậy chỉ lấy file executable JAR rồi chạy bằng một lệnh `java -cp catalog-app.jar com.example.catalog.CatalogApplication` không nhất thiết tương đương `java -jar`. Đường dẫn class trong `BOOT-INF/classes` không phải root của một plain JAR classpath theo cách đó.

### 22.3. Không cần thay tên classpath resource theo launcher

Dù cách khởi động khác nhau, khi classloader đã được setup đúng:

~~~java
new ClassPathResource("data/catalog.json");
~~~

vẫn mô tả cùng một tên resource logic.

## 23. Docker và Kubernetes: resource vẫn ở trong artifact

Trong container image, ứng dụng có thể được chạy bằng:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY catalog-app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu `catalog.json` đã nằm trong JAR, không cần copy thêm `src/main/resources` vào image.

Resource được mở bằng:

~~~java
new ClassPathResource("data/catalog.json")
        .getInputStream();
~~~

### 23.1. WORKDIR không thay classpath resource logic

`WORKDIR /app` quyết định thư mục làm việc mặc định của tiến trình, không biến `data/catalog.json` thành `/app/data/catalog.json` khi bạn dùng `ClassPathResource`.

Ngược lại, `Path.of("data/catalog.json")` là đường dẫn filesystem tương đối và sẽ được giải quyết theo working directory, có thể là `/app/data/catalog.json`.

### 23.2. Mount configuration ngoài ứng dụng

Nếu một môi trường Kubernetes mount config dưới:

~~~text
/etc/catalog/config.yml
~~~

đó là external file, không tự trở thành một classpath resource.

Dùng `file:/etc/catalog/config.yml` hoặc Java NIO, hoặc cấu hình Spring Boot config data loading theo cơ chế tương ứng nếu file là ứng dụng configuration.

### 23.3. Kiểm tra resource theo cùng artifact

Để loại bỏ khác biệt giữa test và production, chạy smoke test trên đúng executable JAR hoặc container image được triển khai. Đừng chỉ test một tập class/resources được build riêng trong IDE.

## 24. Tránh những lỗi encoding và đường dẫn

Ngay cả khi đã dùng classpath đúng cách, việc đọc resource vẫn có các rủi ro:

### 24.1. Không dựa vào default charset

Không nên viết:

~~~java
new String(input.readAllBytes());
~~~

nếu tài liệu yêu cầu UTF-8 ổn định ở mọi môi trường. Dùng:

~~~java
new String(
        input.readAllBytes(),
        StandardCharsets.UTF_8
);
~~~

hoặc parser được cấu hình encoding phù hợp.

### 24.2. Không tự decode resource URL để tạo file path

URL có thể có percent-encoding, khoảng trắng, Unicode hoặc JAR-specific protocol. Việc cắt chuỗi URL bằng tay rồi xây `new File(...)` dễ hỏng.

Nếu không cần đường dẫn vật lý, đừng chuyển URL thành File.

### 24.3. Tên resource phân biệt chữ hoa/chữ thường

Một số filesystem development không phân biệt hoa/thường, nhưng archive entry và môi trường chạy có thể phân biệt. Hãy dùng đúng tên:

~~~text
data/catalog.json
~~~

thay vì:

~~~text
data/Catalog.json
~~~

Chính tả tên file và đường dẫn nên nhất quán giữa source, test và deployment.

### 24.4. Dấu gạch chéo

Trong tên classpath resource, dùng dấu `/` theo quy ước URL/path của Java, kể cả khi phát triển trên Windows:

~~~text
data/catalog.json
~~~

Không mã hóa path bằng `\\` như một đường dẫn Windows filesystem.

### 24.5. Resource lớn

`input.readAllBytes()` phù hợp cho file nhỏ. Với CSV/JSON lớn, cân nhắc parser streaming hoặc đọc thành từng phần, tránh tăng heap và thời gian startup không cần thiết.

## 25. Những lỗi thường gặp và cách xử lý

### 25.1. FileNotFoundException sau khi chạy java -jar

**Triệu chứng:** chạy từ IDE được, JAR báo không thể resolve resource thành absolute file path.

**Nguyên nhân thường gặp:** code gọi `ClassPathResource.getFile()`.

**Cách xử lý:** dùng `getInputStream()`; nếu thư viện bắt buộc nhận `File`, copy ra file tạm có quản lý lifecycle.

### 25.2. NoSuchFileException với src/main/resources

**Triệu chứng:** chương trình báo không tìm thấy `src/main/resources/data/catalog.json` trên server.

**Nguyên nhân:** code dùng relative filesystem path của source tree.

**Cách xử lý:** đọc `classpath:data/catalog.json` nếu dữ liệu đóng gói, hoặc chuyển hẳn sang external file được cấu hình rõ ràng.

### 25.3. Resource có trong JAR nhưng ClassLoader trả null

**Nguyên nhân có thể:**

- Sai tên hoặc sai chữ hoa/chữ thường.
- Dùng dấu `/` đầu đường dẫn với `ClassLoader.getResourceAsStream`.
- Thêm prefix `classpath:` vào Java ClassLoader API.
- Resource nằm ở một path khác trong archive.
- Classloader đang dùng không nhìn thấy resource.

**Cách xử lý:** dùng `jar tf` kiểm tra entry, chuẩn hóa tên và thử `ClassPathResource` trong đúng runtime.

### 25.4. Resource có trong test nhưng không có trong production

**Nguyên nhân:** file chỉ nằm trong `src/test/resources`.

**Cách xử lý:** chuyển file cần cho runtime sang `src/main/resources` hoặc cung cấp qua runtime dependency.

### 25.5. Đọc trong IDE được nhưng trong Docker lỗi

**Nguyên nhân có thể:** code dùng working-directory path, file nằm ngoài JAR chưa được copy/mount, quyền truy cập khác hoặc case-sensitive path.

**Cách xử lý:** phân biệt resource packaged và external file; kiểm tra image/volume và dùng API đúng loại nguồn.

### 25.6. java -jar báo không tìm thấy class hoặc dependency

**Nguyên nhân:** đang chạy plain JAR thay vì executable Spring Boot JAR, hoặc plugin đóng gói chưa được cấu hình đúng.

**Cách xử lý:** kiểm tra plugin `repackage`/`bootJar`, manifest và artifact thực tế. Đây là vấn đề packaging, không nhất thiết do đường dẫn resource.

### 25.7. Đọc được URL nhưng Paths.get(url.toURI()) lỗi

**Nguyên nhân:** URI trỏ tới archive/protocol không được filesystem mặc định hiểu hoặc chưa có file system provider tương ứng.

**Cách xử lý:** dùng `InputStream`; chỉ chuyển thành `Path` khi thật sự có filesystem path hợp lệ.

### 25.8. Resource được đóng gói nhưng nội dung không đúng bản mới

**Nguyên nhân:** build không copy resource mới, cache build, custom filtering hoặc artifact chạy không phải bản vừa build.

**Cách xử lý:** kiểm tra output resources, nội dung entry trong JAR và tên artifact đang chạy.

### 25.9. Hai dependency cùng có resource tên giống nhau

**Nguyên nhân:** classloader chọn một resource theo thứ tự tìm kiếm; code kỳ vọng nhầm rằng tự gộp tất cả.

**Cách xử lý:** đặt resource trong namespace thư viện; nếu cần toàn bộ, dùng `getResources`/`ResourcePatternResolver` và quy tắc xử lý trùng.

### 25.10. Ứng dụng cố ghi ngược classpath resource

**Nguyên nhân:** nhầm packaged resource với file dữ liệu runtime.

**Cách xử lý:** dùng filesystem directory, volume hoặc storage được thiết kế cho ghi; giữ classpath resource làm dữ liệu đóng gói theo version artifact.

### 25.11. Chuyển getResource URL thành new File

**Nguyên nhân:** mã giả định mọi URL đều là `file:` URL.

**Cách xử lý:** đọc stream trực tiếp và không phụ thuộc scheme/protocol của URL.

### 25.12. Resource không tìm thấy khi đổi môi trường chạy

**Nguyên nhân:** sourceSets khác, artifact packaging khác, dependency scope khác hoặc classloader chuyên biệt.

**Cách xử lý:** kiểm tra runtime classpath thực tế và đóng gói artifact, thay vì suy luận từ cây thư mục IDE.

## 26. Quy trình thiết kế truy cập resource bền vững

Khi thêm một resource cho một tính năng Spring Boot:

1. **Chọn loại nguồn:** dữ liệu bất biến theo release hay file bên ngoài có thể đổi?
2. **Với dữ liệu đi kèm release, đặt trong `src/main/resources`** hoặc runtime dependency có cấu trúc rõ.
3. **Đặt tên classpath logic ổn định:** ví dụ `data/catalog.json` hoặc `META-INF/myapp/defaults.yml`.
4. **Dùng `ResourceLoader`, `ClassPathResource` hoặc ClassLoader API** để mở resource.
5. **Đọc bằng `InputStream`**, không phụ thuộc `getFile()`.
6. **Đóng stream** và xử lý `IOException`/parser errors rõ ràng.
7. **Dùng encoding cụ thể** cho dữ liệu văn bản.
8. **Không ghi ngược packaged resource**; chọn storage riêng cho dữ liệu biến đổi.
9. **Xác nhận resource có trong runtime output/JAR** nếu build có sourceSets hoặc resource filtering tùy chỉnh.
10. **Kiểm thử từ IDE và executable JAR** để phát hiện code phụ thuộc đường dẫn filesystem tình cờ.
11. **Tránh name collision** khi resource nằm trong nhiều thư viện.
12. **Giới hạn input và nội dung được phép truy cập** nếu resource location đến từ cấu hình bên ngoài hoặc người dùng.

Nếu một đoạn code chỉ hoạt động khi project được mở ở đúng thư mục source, đó là dấu hiệu cần xem lại ranh giới giữa **source tree**, **runtime classpath** và **external filesystem**.

## 27. Bài thực hành

### Bài A: Chạy từ thư mục lớp

Tạo `src/main/resources/data/hello.txt` với nội dung:

~~~text
Xin chào từ classpath!
~~~

Viết `ApplicationRunner` dùng `ClassPathResource("data/hello.txt")` và `getInputStream()` để đọc. Chạy bằng IDE hoặc `mvn spring-boot:run`.

Quan sát resource được tìm thấy dù code không nhắc đến `src/main/resources`.

### Bài B: Chạy từ executable JAR

Đóng gói ứng dụng bằng `mvn package` hoặc `./gradlew bootJar`. Kiểm tra entry `BOOT-INF/classes/data/hello.txt` bằng `jar tf`.

Chạy `java -jar` và xác nhận runner đọc cùng một nội dung mà không cần đổi code.

### Bài C: Tái hiện lỗi getFile

Trong môi trường thử nghiệm, đổi:

~~~java
resource.getInputStream();
~~~

thành:

~~~java
resource.getFile();
~~~

Quan sát sự khác nhau giữa chạy từ output directory và executable JAR. Giải thích vì sao `File` không đại diện cho một entry trong archive.

Khôi phục cách đọc bằng stream sau khi quan sát.

### Bài D: Phân biệt ClassLoader và Class path

Với class trong package `com.example.catalog`, so sánh:

~~~java
SomeClass.class.getResourceAsStream(
        "/data/hello.txt"
);
~~~

~~~java
SomeClass.class.getResourceAsStream(
        "data/hello.txt"
);
~~~

~~~java
SomeClass.class.getClassLoader()
        .getResourceAsStream(
                "data/hello.txt"
        );
~~~

Ghi lại đường dẫn mà mỗi lời gọi tìm kiếm và giải thích dấu `/` đầu đường dẫn.

### Bài E: Đổi thư mục làm việc

Chạy JAR từ một thư mục khác project root. So sánh kết quả của:

~~~java
Path.of("src/main/resources/data/hello.txt");
~~~

và:

~~~java
new ClassPathResource("data/hello.txt");
~~~

Chỉ cách thứ hai mô tả đúng packaged classpath resource.

### Bài F: Resource từ dependency JAR

Tạo module library chứa:

~~~text
META-INF/myapp/messages/default.txt
~~~

Đóng gói và thêm vào runtime dependency của ứng dụng. Dùng `ClassPathResource` để đọc file đó từ ứng dụng.

Quan sát không cần biết đường dẫn `BOOT-INF/lib` của thư viện.

### Bài G: Trường hợp cần external file

Giữ một file default trong classpath và một file tùy chỉnh trong thư mục ngoài ứng dụng.

Thiết kế quy tắc: nếu external file tồn tại và đọc được thì dùng; nếu không và fallback được cho phép thì dùng classpath default. Viết rõ khi nào phải fail thay vì im lặng bỏ qua lỗi.

### Bài H: Truyền resource cho thư viện nhận File

Tạo một API giả định `LegacyParser.parse(File)`. Dùng `getInputStream()` copy resource ra temp file, gọi parser và cleanup an toàn.

Giải thích vì sao không nên xóa temp file sớm nếu API xử lý bất đồng bộ.

### Bài I: Phân biệt main và test resources

Đặt một file chỉ ở `src/test/resources`. Viết unit test đọc nó thành công, sau đó chạy production JAR và quan sát nó không có mặt theo packaging mặc định.

Chuyển file cần cho production sang `src/main/resources` và thử lại.

## 28. Câu hỏi tự kiểm tra

**1. Resource nằm trong `src/main/resources` sẽ được sử dụng ở runtime như thế nào?**

Build thường copy hoặc đóng gói nó vào runtime classpath, nơi classloader/`ResourceLoader` có thể tìm theo tên logic.

**2. Với Maven, classpath output development thường là gì?**

Thường có `target/classes` cho class và main resources, cùng dependency JAR khác.

**3. Với Gradle, main classes và resources thường nằm ở đâu?**

Thường ở `build/classes/java/main` và `build/resources/main`, nhưng layout thực tế có thể khác theo build configuration.

**4. Trong executable Spring Boot JAR, class/resource của ứng dụng thường nằm ở đâu?**

Trong `BOOT-INF/classes` theo layout Boot JAR thông dụng.

**5. Đường dẫn Java để đọc resource có cần thêm `BOOT-INF/classes` khi đóng gói không?**

Không. Vẫn dùng tên classpath logic như `data/catalog.json`.

**6. Vì sao `Resource.getFile()` có thể hoạt động trong IDE nhưng thất bại từ JAR?**

Vì khi chạy từ output directory resource có thể là file thật, còn trong JAR nó là archive entry không có `File` riêng tương ứng.

**7. API nào nên dùng để đọc resource ở cả hai chế độ?**

`InputStream` từ `ClassPathResource`/`ResourceLoader` hoặc `ClassLoader.getResourceAsStream`.

**8. `ClassLoader.getResourceAsStream` có dùng prefix `classpath:` không?**

Không. Nó nhận tên resource trên classpath, ví dụ `data/catalog.json`.

**9. `SomeClass.class.getResourceAsStream("data/x.txt")` tìm từ đâu?**

Tương đối với package của `SomeClass`; thêm dấu `/` đầu đường dẫn để tìm từ classpath root.

**10. `URL.getFile()` có trả một `java.io.File` hợp lệ không?**

Không. Nó trả phần đường dẫn của URL, không bảo đảm là một file vật lý có thể truy cập.

**11. Nếu thư viện chỉ nhận `File`, phải làm gì với resource trong JAR?**

Có thể copy nội dung qua `InputStream` ra file tạm, quản lý vòng đời file và truyền file đó cho thư viện.

**12. Có thể ghi ngược file nằm trong executable JAR bằng `Files.writeString` không?**

Không nên coi packaged resource là nơi ghi. Dùng external file, volume hoặc storage phù hợp.

**13. Tại sao unit test đọc resource thành công chưa đủ chứng minh deployment đúng?**

Test thường chạy từ output directory; packaged JAR có layout và classloader khác. Cần smoke test artifact thực tế.

**14. File trong `src/test/resources` có tự nằm trong production executable JAR không?**

Thông thường không. Nó chỉ thuộc test classpath.

**15. `java -cp app.jar MainClass` có luôn tương đương `java -jar app.jar` đối với Spring Boot executable JAR không?**

Không. Boot executable JAR có launcher và internal layout; cần chạy đúng cách theo packaging của Boot.

## 29. Kết luận

**Classpath resource là tài nguyên được classloader tìm thấy theo một đường dẫn logic, không nhất thiết là file vật lý nằm cạnh ứng dụng.** Khi chạy từ IDE, Maven hoặc Gradle, resource thường nằm trong output directory; khi đóng gói Spring Boot executable JAR, resource thường nằm trong `BOOT-INF/classes` hoặc trong dependency JAR. Cách đóng gói thay đổi, nhưng tên classpath logic như `data/catalog.json` có thể giữ nguyên.

Vì vậy, khi chỉ cần đọc dữ liệu, hãy dùng `ClassPathResource`, `ResourceLoader` hoặc Java `ClassLoader.getResourceAsStream` và xử lý nội dung qua `InputStream`. Đừng giả định `getFile()` luôn được hỗ trợ, đừng hard-code `src/main/resources` và đừng biến resource URL thành filesystem path nếu không thật sự có một file vật lý.

Hãy phân biệt rõ resource đi kèm artifact với external file cần thay đổi hoặc ghi dữ liệu runtime. Cuối cùng, kiểm tra cả output development lẫn executable JAR được đóng gói thật để phát hiện sớm những lỗi chỉ xuất hiện sau khi triển khai. Thiết kế theo classpath abstraction giúp cùng một ứng dụng Spring Boot đọc tài nguyên ổn định dù chạy từ thư mục lớp, JAR, container hay một môi trường deployment khác.

