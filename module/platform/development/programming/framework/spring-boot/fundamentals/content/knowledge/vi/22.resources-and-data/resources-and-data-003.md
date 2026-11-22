# ResourcePatternResolver khi cần tìm nhiều tài nguyên

Một ứng dụng Spring Boot không phải lúc nào cũng biết trước chính xác tên của từng file cần đọc. Có những tình huống ứng dụng cần tìm **toàn bộ** file cấu hình nằm trong một thư mục, các mẫu email theo ngôn ngữ, những file JSON schema ở nhiều module, hoặc những tài nguyên cùng tên được đóng gói trong nhiều JAR khác nhau.

Nếu đã biết một đường dẫn duy nhất, `ResourceLoader.getResource(...)` thường đủ. Nhưng khi yêu cầu là “tìm tất cả tài nguyên phù hợp với mẫu này”, Spring Framework cung cấp **`ResourcePatternResolver`** và implementation quen thuộc **`PathMatchingResourcePatternResolver`**.

Ví dụ:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

Lời gọi trên yêu cầu Spring tìm các tài nguyên JSON trong thư mục `schemas` và những thư mục con, có thể trải rộng qua nhiều vị trí classpath.

Bài học giải thích sự khác nhau giữa `Resource`, `ResourceLoader` và `ResourcePatternResolver`; cú pháp `classpath:`, `classpath*:`, `file:`; wildcard `*`, `?` và `**`; cách đọc resource khi ứng dụng chạy từ executable JAR; giới hạn của việc quét classpath; cách sử dụng trong service, kiểm thử và các lỗi thường gặp.

## 1. Tình huống: một file và nhiều file khác nhau như thế nào?

Giả sử project có:

~~~text
src/main/resources/
└── schemas/
    ├── order.json
    ├── customer.json
    └── versions/
        ├── v1/
        │   └── payment.json
        └── v2/
            └── payment.json
~~~

Nếu chỉ đọc `schemas/order.json`, ta biết tên file từ đầu:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:schemas/order.json"
);
~~~

Nhưng nếu yêu cầu là **tìm tất cả schema JSON** để đăng ký vào một catalog khi khởi động, tự viết bốn đường dẫn sẽ khiến code phải sửa mỗi khi dự án có schema mới.

Một giải pháp có mẫu tìm kiếm:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

Các schema có thể được phát hiện theo quy tắc đặt file thay vì phải thêm từng tên file vào Java source.

Đây là một ví dụ của phương pháp *convention-based discovery*: thư mục và pattern được xem là quy ước, còn các file thỏa quy ước sẽ được tìm thấy khi chương trình thực hiện việc quét.

### 1.1. Các trường hợp sử dụng thực tế

- Tìm những template nằm trong `classpath*:templates/email/**/*.html`.
- Nạp file schema từ một hoặc nhiều module.
- Tìm metadata của nhiều thư viện trong `META-INF`.
- Thu thập tập dữ liệu mẫu cho một bài kiểm thử.
- Nạp file rules, mappings hoặc định nghĩa có định dạng thống nhất.
- Tìm tài nguyên trên filesystem khi một thư mục được mount vào container.

Cơ chế này hữu ích khi nhiều tài nguyên dùng chung một convention và ứng dụng có thể xử lý chúng như một tập hợp.

## 2. Resource: trừu tượng hóa một tài nguyên

Trong Spring Framework, `Resource` là abstraction của một tài nguyên có thể được đọc hoặc mô tả.

~~~java
import org.springframework.core.io.Resource;
~~~

Một số phương thức đáng chú ý:

~~~java
boolean exists();
boolean isReadable();
String getFilename();
String getDescription();
InputStream getInputStream() throws IOException;
URL getURL() throws IOException;
File getFile() throws IOException;
~~~

Về ý nghĩa:

| API | Ý nghĩa |
| --- | --- |
| `exists()` | Resource hiện có tồn tại theo cơ chế của implementation không? |
| `isReadable()` | Resource có thể đọc theo cách implementation hỗ trợ không? |
| `getFilename()` | Lấy tên file cuối đường dẫn nếu xác định được |
| `getDescription()` | Mô tả để ghi log hoặc chẩn đoán |
| `getInputStream()` | Mở luồng đọc nội dung |
| `getURL()` | Lấy URL khi resource hỗ trợ |
| `getFile()` | Chuyển sang `java.io.File` khi có một file thật tương ứng |

Các implementation thông dụng của `Resource` gồm:

- `ClassPathResource` cho tài nguyên trong classpath.
- `FileSystemResource` cho file trên filesystem.
- `UrlResource` cho tài nguyên có URL.
- Các loại resource khác tùy `ResourceLoader` và môi trường thực thi.

**Điểm cần nhớ:** không phải mọi `Resource` là một file vật lý riêng biệt trên đĩa. Tài nguyên bên trong JAR vẫn có thể được đọc bằng `getInputStream()`, nhưng `getFile()` có thể không hoạt động.

## 3. ResourceLoader: giải quyết một resource location

`ResourceLoader` là interface của Spring Framework:

~~~java
import org.springframework.core.io.ResourceLoader;
~~~

Nó cung cấp phương thức:

~~~java
Resource getResource(String location);
~~~

Ví dụ:

~~~java
@Component
public class LogoService {

    private final ResourceLoader resourceLoader;

    public LogoService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource logo() {
        return resourceLoader.getResource(
                "classpath:images/logo.png"
        );
    }
}
~~~

`getResource(...)` trả về một `Resource` biểu diễn location được chỉ định. Nó **không tự tìm một danh sách các file khớp wildcard** và cũng không nhất thiết đọc nội dung ngay tại lúc gọi.

Để đọc resource:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:data/message.txt"
);

try (InputStream input = resource.getInputStream()) {
    String text = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
    System.out.println(text);
}
~~~

Cần import `java.io.InputStream`, `java.nio.charset.StandardCharsets` và xử lý `IOException` ở method bao quanh.

### 3.1. Khi nào ResourceLoader đủ?

Khi ứng dụng đã biết đúng một resource location:

~~~text
classpath:config/payment-defaults.json
file:/opt/myapp/config/feature-flags.yml
~~~

Nếu nhu cầu là tìm tất cả `*.json` hoặc tập tài nguyên có trong nhiều JAR, ta cần API giải quyết **pattern**.

## 4. ResourcePatternResolver: mở rộng để tìm một tập Resource

`ResourcePatternResolver` nằm trong package:

~~~java
import org.springframework.core.io.support.ResourcePatternResolver;
~~~

Interface này kế thừa `ResourceLoader` và bổ sung:

~~~java
Resource[] getResources(String locationPattern) throws IOException;
~~~

Nói cách khác:

- `getResource(String)` xử lý một location.
- `getResources(String)` xử lý một location pattern và trả về một **mảng resource**.

Spring cung cấp implementation thường dùng:

~~~java
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
~~~

Ví dụ:

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

`PathMatchingResourcePatternResolver` sử dụng cơ chế giải quyết resource của Spring kết hợp path matching. Nó không bắt buộc ứng dụng phải dùng Spring Boot; đây là API của Spring Framework. Spring Boot đem lại cách đóng gói, cấu hình và dependency injection thuận tiện để sử dụng nó.

### 4.1. Vì sao kết quả là mảng?

Pattern có thể khớp:

- Không resource nào.
- Một resource.
- Nhiều resource.
- Nhiều resource có cùng tên nhưng nằm trong các classpath root hoặc JAR khác nhau.

Vì vậy kết quả là `Resource[]`, kể cả khi pattern của bạn chỉ tình cờ khớp một file.

Một trường hợp không có kết quả thường trả về mảng rỗng. Nhưng lỗi trong quá trình truy cập hoặc duyệt resource có thể khiến `getResources(...)` ném `IOException`; ứng dụng cần quyết định phải xử lý thế nào.

## 5. So sánh classpath:, classpath*: và file:

Đây là phần dễ nhầm nhất khi mới dùng `ResourcePatternResolver`.

### 5.1. classpath: — một đường dẫn theo classpath

~~~java
resourceLoader.getResource(
        "classpath:schemas/order.json"
);
~~~

Prefix `classpath:` thường giải quyết một resource tương ứng theo classloader/resource loader.

Nếu cùng một tên resource tồn tại trong hai JAR, API đọc một resource không có ý nghĩa là tự tổng hợp nội dung từ cả hai JAR.

Với `ResourcePatternResolver`, một pattern bắt đầu bằng `classpath:` và có wildcard có thể được quét dưới một classpath root được giải quyết. **Đừng dùng nó khi mục tiêu là gom toàn bộ resource từ mọi JAR.**

### 5.2. classpath*: — tìm trên nhiều vị trí classpath

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

Prefix đặc biệt `classpath*:` yêu cầu resolver xét **mọi vị trí classpath phù hợp**, bao gồm nhiều directory và JAR mà classloader có thể truy cập.

Ví dụ có hai thư viện:

~~~text
billing-schema.jar
└── schemas/
    └── billing/
        └── invoice.json

shipping-schema.jar
└── schemas/
    └── shipping/
        └── shipment.json
~~~

Pattern:

~~~java
resolver.getResources("classpath*:schemas/**/*.json");
~~~

có thể tìm thấy cả hai schema khi chúng thực sự nằm trong classpath có thể quét được và cấu trúc JAR cho phép resolver xác định các entry.

Đây là giá trị khác biệt quan trọng nhất của `classpath*:`: **không giới hạn vào một classpath location được chọn đầu tiên**.

### 5.3. file: — đường dẫn trên filesystem

Nếu file nằm ngoài ứng dụng:

~~~text
/opt/myapp/config/rules/
├── tax.yml
├── discount.yml
└── archived/
    └── legacy.yml
~~~

có thể dùng:

~~~java
Resource[] resources = resolver.getResources(
        "file:/opt/myapp/config/rules/**/*.yml"
);
~~~

Pattern này dùng location dạng filesystem. Ví dụ đường dẫn trên áp dụng cho hệ thống có layout tương tự Linux; trên Windows phải dùng URI filesystem phù hợp.

Đừng nhầm `file:` với `classpath:`. File được mount vào container có thể không thuộc classpath dù nó nằm trên cùng máy chạy JVM.

### 5.4. Bảng chọn prefix

| Prefix | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `classpath:` | Một resource hoặc pattern từ classpath location | Biết file hoặc không cần duyệt mọi classpath root |
| `classpath*:` | Mọi location classpath phù hợp mà resolver tìm được | Quét tài nguyên trong nhiều module/JAR |
| `file:` | Resource trong filesystem | Thư mục được mount hoặc file ngoài JAR |
| `https:` và các URL khác | Resource theo URL, tùy implementation | Một resource URL cụ thể; wildcard từ xa không được bảo đảm |

Một URI HTTP không tự biến thành hệ thống thư mục mà Spring có thể liệt kê. Để tìm hàng loạt file trên object storage hoặc dịch vụ bên ngoài, thường cần API listing riêng thay vì dùng wildcard URL theo suy đoán.

## 6. Cú pháp wildcard theo kiểu Ant

`PathMatchingResourcePatternResolver` có thể sử dụng cú pháp pattern theo kiểu Ant.

Các ký hiệu thường dùng:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `*` | Khớp không hoặc nhiều ký tự trong một đoạn đường dẫn |
| `?` | Khớp một ký tự trong một đoạn đường dẫn |
| `**` | Khớp không hoặc nhiều cấp thư mục khi dùng theo cú pháp path matcher phù hợp |

Ví dụ:

~~~text
classpath*:schemas/*.json
classpath*:schemas/**/*.json
classpath*:templates/email/*.html
classpath*:templates/email/**/*.html
classpath*:config/app-?.yml
~~~

Cách hiểu:

- `schemas/*.json`: tìm các file JSON ngay trong thư mục `schemas`.
- `schemas/**/*.json`: tìm file JSON trong `schemas` và những thư mục con ở nhiều độ sâu.
- `app-?.yml`: tên có đúng một ký tự ở vị trí `?`, ví dụ `app-a.yml`.
- `templates/email/**/*.html`: tìm các HTML template trong cây thư mục email.

### 6.1. Ví dụ minh họa kết quả

Cho:

~~~text
schemas/
├── order.json
├── readme.txt
├── v1/
│   ├── invoice.json
│   └── notes.md
└── v2/
    └── archive/
        └── payment.json
~~~

Dự kiến:

| Pattern | Những file thường khớp |
| --- | --- |
| `schemas/*.json` | `order.json` |
| `schemas/**/*.json` | `order.json`, `invoice.json`, `payment.json` |
| `schemas/v1/*.json` | `invoice.json` |
| `schemas/v?/invoice.json` | `invoice.json` nếu đường dẫn phù hợp |
| `schemas/**/*.txt` | Không có file nếu `readme.txt` là file duy nhất nằm ngay root? |

Với pattern cuối, vì `**` có thể khớp không thư mục con nào, `readme.txt` ngay dưới `schemas` **vẫn có thể khớp**. Đây là lý do nên kiểm tra ý nghĩa của `**` thay vì hiểu nó bắt buộc phải có thư mục con.

### 6.2. Không nhầm với regular expression

Pattern `schemas/**/*.json` không phải Java regex. Các ký hiệu và ngữ nghĩa phù hợp với path matcher dạng Ant, không phải `Pattern.compile(...)`.

Đừng dùng syntax regex như `.*` hoặc nhóm capture rồi kỳ vọng resolver diễn giải theo regex.

### 6.3. Càng rõ thư mục gốc càng tốt

Nên dùng:

~~~text
classpath*:schemas/**/*.json
~~~

thay vì quét quá rộng:

~~~text
classpath*:**/*.json
~~~

Pattern rộng có thể tìm nhiều tài nguyên không liên quan và khiến startup chậm, đặc biệt trong ứng dụng có classpath lớn.

## 7. Classpath root, thư mục trong JAR và giới hạn của việc quét

Khác với việc đọc một file đã biết, giải quyết wildcard đòi hỏi resolver tìm được một **root directory** rồi duyệt các entry phù hợp.

Ví dụ:

~~~text
classpath*:schemas/**/*.json
~~~

có root `schemas/` trước phần wildcard. Resolver có thể tìm các classpath root tương ứng rồi tìm những entry bên dưới.

Trong khi:

~~~text
classpath*:*.xml
~~~

yêu cầu quét các file XML ở root của classpath. Việc quét wildcard ngay tại root có thể không tìm đầy đủ entry trong mọi JAR/classloader, vì cơ chế liệt kê root directory của JAR và classloader có những giới hạn.

### 7.1. Quy tắc thực hành cho tài nguyên thư viện

Nếu bạn thiết kế thư viện cần các tài nguyên được auto-discover, hãy đặt chúng trong **một thư mục con có tên rõ ràng**:

~~~text
META-INF/myapp/schemas/
META-INF/myapp/mappings/
META-INF/myapp/rules/
~~~

Ví dụ:

~~~java
Resource[] schemas = resolver.getResources(
        "classpath*:META-INF/myapp/schemas/**/*.json"
);
~~~

Cách này dễ quản lý hơn việc đặt tất cả JSON ở root classpath rồi quét `classpath*:*.json`.

### 7.2. classpath* không phải lời hứa tìm được mọi file trong mọi môi trường

Kết quả còn phụ thuộc:

- ClassLoader và những URL nó công bố.
- Cấu trúc thư mục và entries trong JAR.
- Runtime đóng gói ứng dụng, bao gồm executable JAR.
- Cách URL protocol được xử lý.
- Khả năng resolver mở và duyệt thư mục/JAR tương ứng.

Spring có hỗ trợ rộng cho classpath scanning, nhưng khi một sản phẩm phụ thuộc vào cơ chế tự phát hiện trong các thư viện đóng gói phức tạp, cần có test chạy từ **artifact được đóng gói thật**, không chỉ test trong IDE.

### 7.3. Có resource trùng tên trong nhiều JAR

Giả sử:

~~~text
plugin-a.jar!/META-INF/myapp/rules/default.yml
plugin-b.jar!/META-INF/myapp/rules/default.yml
~~~

`classpath*:META-INF/myapp/rules/default.yml` có thể trả về cả hai location.

Không nên tự quyết định “chỉ lấy file đầu tiên” mà không có quy tắc. Thứ tự trả về có thể phụ thuộc classloader hoặc cơ chế quét và không phải contract ưu tiên nghiệp vụ.

Nếu mỗi rule phải có ID duy nhất, ứng dụng cần đọc ID rồi:

- Phát hiện trùng và fail fast; hoặc
- Cho phép một quy tắc override có độ ưu tiên tường minh; hoặc
- Giữ riêng hai nguồn nếu tên giống nhau nhưng thuộc hai plugin khác nhau.

Việc khớp file vật lý không đồng nghĩa dữ liệu logic bên trong không trùng.

## 8. Đọc tài nguyên bằng InputStream, không phụ thuộc getFile()

Khi chạy ứng dụng trong IDE, một resource có thể nằm dưới `target/classes` hoặc `build/resources/main`. Lúc đó `Resource.getFile()` có thể hoạt động.

Nhưng sau khi đóng gói:

~~~text
app.jar
└── BOOT-INF/classes/
    └── schemas/
        └── order.json
~~~

resource nằm bên trong archive, không nhất thiết có một `java.io.File` tương ứng.

Đoạn sau dễ gặp lỗi khi triển khai:

~~~java
File file = resource.getFile();
String json = Files.readString(file.toPath());
~~~

Với resource nằm trong JAR, `getFile()` có thể ném `FileNotFoundException` hoặc một `IOException` liên quan.

Nên dùng:

~~~java
try (InputStream input = resource.getInputStream()) {
    String json = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

### 8.1. Vì sao phải đóng stream?

`getInputStream()` mở tài nguyên cần đóng khi đọc xong. `try-with-resources` bảo đảm đóng stream ngay cả khi đọc hoặc parse thất bại.

Nếu đọc nhiều resource, quên đóng stream có thể làm cạn file descriptor hoặc giữ kết nối/handle archive lâu không mong muốn.

### 8.2. isReadable() không thay thế xử lý IOException

Có thể lọc:

~~~java
if (!resource.isReadable()) {
    return;
}
~~~

nhưng giữa thời điểm kiểm tra và đọc, tài nguyên có thể thay đổi hoặc xảy ra lỗi I/O. Vì vậy vẫn phải xử lý exception từ `getInputStream()`.

### 8.3. getFilename() không đảm bảo định danh duy nhất

Nếu cả hai location có tên `default.json`, `resource.getFilename()` đều trả `default.json` dù nội dung khác nhau.

Dùng `getDescription()` hoặc `getURL()` khi cần chẩn đoán nguồn; nếu cần định danh nghiệp vụ, hãy định nghĩa một ID trong nội dung/schema hoặc lấy path tương đối theo quy tắc đã thiết kế.

## 9. Dùng ResourcePatternResolver trong bean Spring Boot

`ResourceLoader` được Spring cung cấp như dependency hạ tầng. Ta có thể dùng nó để tạo resolver thực hiện pattern matching:

~~~java
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Service;

@Service
public class SchemaCatalog {

    private final ResourcePatternResolver resolver;

    public SchemaCatalog(ResourceLoader resourceLoader) {
        this.resolver =
                new PathMatchingResourcePatternResolver(resourceLoader);
    }

    public Resource[] findSchemas() throws IOException {
        return resolver.getResources(
                "classpath*:schemas/**/*.json"
        );
    }
}
~~~

Lợi ích:

- `ResourceLoader` đến từ Spring context.
- Resolver sử dụng resource loading infrastructure phù hợp với môi trường ứng dụng.
- Code nghiệp vụ chỉ sử dụng contract `ResourcePatternResolver`.
- Dễ thay đổi pattern thành một giá trị cấu hình có kiểm soát sau này.

### 9.1. ApplicationContext cũng có khả năng giải quyết pattern

`ApplicationContext` của Spring Framework kế thừa `ResourcePatternResolver` và có thể dùng các API này. Ví dụ:

~~~java
Resource[] resources = applicationContext.getResources(
        "classpath*:schemas/**/*.json"
);
~~~

Cách này phù hợp khi code vốn đang thao tác với ApplicationContext. Tuy nhiên, một service chỉ cần đọc tài nguyên không nhất thiết phải phụ thuộc vào toàn bộ ApplicationContext. Inject `ResourceLoader` rồi tạo resolver hoặc khai báo một bean `ResourcePatternResolver` cụ thể có thể làm dependency hẹp và dễ test hơn.

### 9.2. Tạo bean ResourcePatternResolver để chia sẻ

Nếu nhiều service cần chung một resolver, có thể đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
public class ResourceConfiguration {

    @Bean
    public ResourcePatternResolver resourcePatternResolver(
            ResourceLoader resourceLoader) {

        return new PathMatchingResourcePatternResolver(resourceLoader);
    }
}
~~~

Sau đó inject:

~~~java
@Service
public class RuleCatalog {

    private final ResourcePatternResolver resolver;

    public RuleCatalog(ResourcePatternResolver resolver) {
        this.resolver = resolver;
    }
}
~~~

Cách này đặt hạ tầng tìm resource ở một nơi, thay vì mỗi service tự khởi tạo implementation.

## 10. Ví dụ hoàn chỉnh: tìm tất cả schema JSON khi khởi động

Ta xây một Spring Boot application nhỏ để in danh sách schema JSON tìm được. Không cần web server hay database.

### 10.1. Cấu trúc project

~~~text
schema-discovery/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/schemas/
    │   │   ├── SchemaDiscoveryApplication.java
    │   │   └── SchemaListingRunner.java
    │   └── resources/
    │       └── schemas/
    │           ├── order.json
    │           ├── customer.json
    │           └── versions/
    │               └── v2/
    │                   └── invoice.json
    └── test/
        └── java/com/example/schemas/
            └── SchemaListingRunnerTest.java
~~~

### 10.2. Dependency Spring Boot

Ví dụ Maven dùng Java 21, Spring Boot 3.x:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>schema-discovery</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
</project>
~~~

Phiên bản trên mang tính minh họa cho dòng Boot 3.x. Trong dự án thật, nên dùng phiên bản Spring Boot được BOM/project quản lý và bảo đảm tương thích với JDK.

### 10.3. Class khởi động

`SchemaDiscoveryApplication.java`:

~~~java
package com.example.schemas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SchemaDiscoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SchemaDiscoveryApplication.class, args);
    }
}
~~~

### 10.4. Nội dung resource mẫu

`src/main/resources/schemas/order.json`:

~~~json
{
  "type": "object",
  "title": "Order",
  "properties": {
    "id": { "type": "string" }
  }
}
~~~

`src/main/resources/schemas/customer.json`:

~~~json
{
  "type": "object",
  "title": "Customer",
  "properties": {
    "name": { "type": "string" }
  }
}
~~~

`src/main/resources/schemas/versions/v2/invoice.json`:

~~~json
{
  "type": "object",
  "title": "Invoice",
  "properties": {
    "amount": { "type": "number" }
  }
}
~~~

Các JSON ở đây chỉ là dữ liệu mẫu. `ResourcePatternResolver` không tự phân tích hay validate schema; nó chỉ tìm và cung cấp `Resource` tương ứng.

### 10.5. ApplicationRunner để liệt kê resource

`SchemaListingRunner.java`:

~~~java
package com.example.schemas;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Comparator;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Component;

@Component
public class SchemaListingRunner implements ApplicationRunner {

    private static final String PATTERN =
            "classpath*:schemas/**/*.json";

    private final ResourcePatternResolver resolver;

    public SchemaListingRunner(ResourceLoader resourceLoader) {
        this.resolver =
                new PathMatchingResourcePatternResolver(resourceLoader);
    }

    @Override
    public void run(ApplicationArguments args) throws IOException {
        Resource[] schemas = resolver.getResources(PATTERN);

        // Thứ tự quét không phải contract nghiệp vụ.
        Arrays.sort(
                schemas,
                Comparator.comparing(Resource::getDescription)
        );

        System.out.println("Found " + schemas.length + " schema(s)");

        for (Resource resource : schemas) {
            if (!resource.isReadable()) {
                throw new IOException(
                        "Schema is not readable: "
                                + resource.getDescription()
                );
            }

            try (InputStream input = resource.getInputStream()) {
                String json = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                );

                System.out.println(
                        "Schema: " + resource.getDescription()
                );
                System.out.println(
                        "Characters: " + json.length()
                );
            }
        }
    }
}
~~~

Khi ứng dụng chạy, runner gọi resolver, sắp xếp resource theo mô tả cho log dễ đọc, rồi mở stream đọc từng file.

**Sắp xếp bằng `getDescription()` ở đây chỉ nhằm ổn định trình tự ghi log trong ví dụ; không phải quy tắc ưu tiên nghiệp vụ giữa các schema.** Nếu cần precedence, hãy xác định ID/priority trong dữ liệu.

### 10.6. Chạy ở local và từ JAR

Từ thư mục Maven project:

~~~bash
./mvnw spring-boot:run
~~~

nếu repository có Maven Wrapper; hoặc:

~~~bash
mvn spring-boot:run
~~~

Khi đóng gói:

~~~bash
mvn package
java -jar target/schema-discovery-0.0.1-SNAPSHOT.jar
~~~

Code sử dụng `getInputStream()` nên phù hợp với resource đóng trong JAR hơn cách phụ thuộc vào `getFile()`.

### 10.7. Nếu không tìm thấy schema nào

Nếu đây là module mà schema là **bắt buộc**, ứng dụng nên fail fast:

~~~java
Resource[] schemas = resolver.getResources(PATTERN);

if (schemas.length == 0) {
    throw new IllegalStateException(
            "No schemas found for pattern: " + PATTERN
    );
}
~~~

Nếu schema là **tùy chọn**, mảng rỗng có thể là kết quả hợp lệ; service chỉ cần dùng một catalog rỗng hoặc tắt feature tương ứng.

Quyết định này thuộc nghiệp vụ. Resolver không tự biết việc không tìm thấy file là lỗi hay tình huống bình thường.

## 11. Tìm tài nguyên từ nhiều JAR

Một trường hợp nổi bật là hệ thống modular: mỗi module tự đóng gói metadata hoặc cấu hình.

Ví dụ:

~~~text
catalog-core.jar
└── META-INF/myapp/catalog/
    └── core.json

catalog-plugin-tax.jar
└── META-INF/myapp/catalog/
    └── tax.json

catalog-plugin-shipping.jar
└── META-INF/myapp/catalog/
    └── shipping.json
~~~

Ứng dụng có các JAR này trên runtime classpath và thực hiện:

~~~java
Resource[] catalogs = resolver.getResources(
        "classpath*:META-INF/myapp/catalog/**/*.json"
);
~~~

Khi resolver có thể truy cập và quét các classpath roots tương ứng, nó có thể trả resource từ cả ba module.

### 11.1. Pattern là một giao ước giữa các module

Nếu module đóng gói metadata sai thư mục:

~~~text
META-INF/other-place/shipping.json
~~~

thì nó không khớp pattern. Đó không phải lỗi của resolver.

Thư viện nên tài liệu hóa:

- Thư mục resource chuẩn.
- Phần mở rộng file.
- Cấu trúc nội dung.
- Quy tắc đặt ID và version.
- Cách xử lý trùng tên/ID.
- Thời điểm ứng dụng tìm và nạp resource.

### 11.2. Resource có thể nằm trong nested JAR

Spring Boot executable JAR có cơ chế classloader và URL phù hợp với cách đóng gói dependency lồng bên trong. Hãy để `ResourcePatternResolver` sử dụng resource loading infrastructure của Spring thay vì tự xây đường dẫn `java.io.File` tới `BOOT-INF/lib`.

Nếu thư viện dùng URL protocol lạ hoặc custom classloader, khả năng quét pattern cần được kiểm chứng trên runtime thực tế. Không nên tự suy đoán một resource trong JAR chắc chắn có filesystem path.

## 12. Khi nào dùng classpath*: với tên chính xác, không có wildcard?

`classpath*:` còn có ý nghĩa khi cần **mọi resource có cùng tên**.

Ví dụ, hai dependency đều chứa:

~~~text
META-INF/myapp/extensions.properties
~~~

Có thể gọi:

~~~java
Resource[] resources = resolver.getResources(
        "classpath*:META-INF/myapp/extensions.properties"
);
~~~

Trường hợp này không có `*` hay `**` ở phần đường dẫn sau prefix; tuy vậy prefix `classpath*:` cho phép tìm nhiều resource location của cùng tên theo classloader.

Điều đó khác với:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:META-INF/myapp/extensions.properties"
);
~~~

Lời gọi thứ hai chỉ trả một resource location theo cách `ResourceLoader` giải quyết. Khi thiết kế một hệ plugin có nhiều file chung tên, phân biệt này rất quan trọng.

## 13. Không giả định thứ tự kết quả và cách xử lý trùng

Resolver trả `Resource[]`, nhưng thứ tự có thể phụ thuộc vào:

- Thứ tự classpath.
- Classloader.
- Cách duyệt file system.
- Thứ tự entries trong archive.
- Cơ chế URL resolver của môi trường chạy.

Không nên dùng:

~~~java
Resource selected = resolver.getResources(pattern)[0];
~~~

để lựa chọn “resource ưu tiên cao nhất” khi không có quy tắc nào bảo đảm ý nghĩa của phần tử đầu tiên.

### 13.1. Nếu chỉ cần in log

Có thể sắp xếp bằng tên/mô tả:

~~~java
Arrays.sort(
        resources,
        Comparator.comparing(Resource::getDescription)
);
~~~

Cách này chỉ tạo thứ tự dễ đọc hơn, không phải business precedence.

### 13.2. Nếu mỗi file định nghĩa một rule có ID

Một hướng thiết kế tốt:

1. Tìm các resource.
2. Đọc và parse nội dung.
3. Lấy ID được công bố trong nội dung.
4. Phát hiện ID trùng.
5. Áp dụng quy tắc ưu tiên rõ ràng hoặc fail fast.
6. Tạo catalog cuối cùng.

Ví dụ pseudo-code:

~~~java
Map<String, RuleDefinition> rulesById = new HashMap<>();

for (Resource resource : resources) {
    RuleDefinition rule = parseRule(resource);

    RuleDefinition previous = rulesById.putIfAbsent(
            rule.id(),
            rule
    );

    if (previous != null) {
        throw new IllegalStateException(
                "Duplicate rule id: " + rule.id()
        );
    }
}
~~~

`RuleDefinition` và `parseRule` là abstraction minh họa, cần tự định nghĩa khi triển khai. Resolver không tự gộp hoặc validate nội dung.

### 13.3. Hai resource giống nhau có thể xuất hiện qua các đường quét khác nhau

Một ứng dụng với classloader hoặc module setup phức tạp có thể trả nhiều URL trỏ tới cùng nội dung hoặc các bản sao giống nhau. Nếu việc nạp hai lần tạo side effect, hãy xác định chiến lược deduplicate theo ID logic hoặc normalized URL có kiểm soát.

**Không dùng filename làm khóa duy nhất** khi quét nhiều JAR: hai thư viện độc lập hoàn toàn có thể chứa cùng tên `config.json`.

## 14. Dùng pattern từ configuration properties

Nếu ứng dụng cần thay đổi thư mục quét theo deployment, không nhất thiết hard-code pattern vào service.

`application.yml`:

~~~yaml
app:
  schema:
    location-pattern: classpath*:schemas/**/*.json
    required: true
~~~

Configuration properties:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.schema")
public record SchemaProperties(
        String locationPattern,
        boolean required
) {
}
~~~

Đăng ký:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
    // ...
}
~~~

Service:

~~~java
@Service
public class SchemaDiscoveryService {

    private final ResourcePatternResolver resolver;
    private final SchemaProperties properties;

    public SchemaDiscoveryService(
            ResourceLoader resourceLoader,
            SchemaProperties properties) {

        this.resolver =
                new PathMatchingResourcePatternResolver(resourceLoader);
        this.properties = properties;
    }

    public Resource[] find() throws IOException {
        Resource[] found = resolver.getResources(
                properties.locationPattern()
        );

        if (properties.required() && found.length == 0) {
            throw new IllegalStateException(
                    "Required resources not found: "
                            + properties.locationPattern()
            );
        }

        return found;
    }
}
~~~

Trong production, nên validate `locationPattern` không rỗng và prefix phù hợp với mục đích ứng dụng. Nếu pattern đến từ người dùng không đáng tin cậy, không cho phép tùy ý quét toàn bộ filesystem hoặc classpath rồi trả nội dung resource cho caller.

### 14.1. Khi nên cấu hình thay vì hard-code

- Đường dẫn thư mục khác giữa staging và production.
- Một module có thể dùng resource trong JAR hoặc thư mục mount.
- Test cần trỏ đến fixture.
- Có tính năng optional được bật bằng một cấu hình rõ ràng.

### 14.2. Không để pattern thay đổi không kiểm soát

Nếu một API nhận pattern từ request:

~~~text
GET /resources?pattern=file:/**/*
~~~

và server tự đọc tất cả các file khớp, ứng dụng có nguy cơ lộ dữ liệu hoặc tốn tài nguyên.

Nên dùng pattern được quản trị tin cậy, giới hạn prefix/thư mục cho phép và không trả nội dung tùy ý ra ngoài. Với dữ liệu người dùng upload, nên xây kho lưu trữ riêng có phân quyền thay vì biến ResourcePatternResolver thành bộ duyệt filesystem công khai.

## 15. Đọc lượng lớn tài nguyên: tránh nạp tất cả vào RAM

Code ví dụ dùng:

~~~java
String content = new String(
        input.readAllBytes(),
        StandardCharsets.UTF_8
);
~~~

Cách này thuận tiện cho file nhỏ, nhưng `readAllBytes()` đưa toàn bộ nội dung file vào bộ nhớ.

Nếu pattern khớp hàng trăm file lớn, rủi ro gồm:

- Dùng nhiều heap.
- GC tăng.
- Startup bị kéo dài.
- Một file rất lớn gây `OutOfMemoryError`.
- Nhiều parser cùng giữ dữ liệu không cần thiết.

Với file lớn, nên dùng parser hỗ trợ stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Truyền InputStream vào parser có hỗ trợ streaming.
    parseIncrementally(input);
}
~~~

`parseIncrementally` là hàm minh họa của ứng dụng, không phải API có sẵn của Spring.

Có thể đặt giới hạn kích thước file, số resource và timeout khi truy cập filesystem/network. Nếu các resource được nạp vào memory cache, hãy thiết kế giới hạn cache và khả năng reload rõ ràng.

### 15.1. Không quét lại trên mỗi request nếu không cần

Nếu tập resource gần như cố định từ khi ứng dụng khởi động, tránh gọi:

~~~java
resolver.getResources("classpath*:schemas/**/*.json");
~~~

mỗi lần một HTTP request đến. Việc quét JAR/directory lặp lại có chi phí.

Có thể xây catalog một lần sau startup, lưu kết quả đã parse vào một immutable structure và inject catalog vào service.

Nếu filesystem resource cần được cập nhật lúc runtime, cần thiết kế cơ chế reload/versioning riêng. Resolver chỉ tìm tài nguyên khi được gọi; nó **không tự đăng ký file watcher**.

## 16. Kết hợp với @ConditionalOnResource: giống và khác

Spring Boot có `@ConditionalOnResource`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:config/report-template.html"
)
public class ReportAutoConfiguration {
}
~~~

Annotation đó dùng để **điều kiện hóa việc đăng ký cấu hình/bean** dựa trên sự hiện diện của những resource location được khai báo.

`ResourcePatternResolver` là API chủ động **tìm và trả về các resource** để ứng dụng sử dụng.

| Tiêu chí | `@ConditionalOnResource` | `ResourcePatternResolver` |
| --- | --- | --- |
| Vai trò | Condition cho bean/configuration | API tìm tài nguyên |
| Thời điểm thường gặp | Khi xử lý cấu hình context | Khi code gọi resolver |
| Đầu ra | Condition khớp hay không khớp | `Resource[]` |
| Nhu cầu chính | Chỉ bật một cấu hình nếu tài nguyên hiện diện | Lấy nhiều resource phù hợp mẫu |
| Đọc nội dung | Không | Người gọi tự mở `InputStream` |
| Có thay việc parse/validate không | Không | Không |

Ví dụ, module chỉ nên được đăng ký nếu có một file manifest cố định, sau đó khi đã bật thì quét nhiều schema:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:META-INF/myapp/manifest.json"
)
public class SchemaModuleConfiguration {

    @Bean
    SchemaCatalog schemaCatalog(ResourceLoader resourceLoader) {
        return new SchemaCatalog(resourceLoader);
    }
}
~~~

Trong ví dụ này `SchemaCatalog` là class do ứng dụng thiết kế để dùng resolver tìm schema. Việc đăng ký có điều kiện và việc tìm nhiều resource là hai trách nhiệm khác nhau.

## 17. So sánh với ClassLoader.getResources và Files.walk

Cùng là “tìm file”, nhưng mỗi API hoạt động với một abstraction khác nhau.

### 17.1. ClassLoader.getResources

Java ClassLoader có API:

~~~java
Enumeration<URL> urls =
        Thread.currentThread()
                .getContextClassLoader()
                .getResources("META-INF/myapp/extensions.properties");
~~~

Nó hữu ích để tìm nhiều resource **cùng tên chính xác** trên classpath.

Tuy nhiên, API này không trực tiếp giải quyết pattern Ant-style như:

~~~text
schemas/**/*.json
~~~

`PathMatchingResourcePatternResolver` cung cấp lớp logic matching và quét resource cho những trường hợp đó.

### 17.2. Files.walk

Java NIO có thể duyệt thư mục trên filesystem:

~~~java
try (Stream<Path> paths = Files.walk(Path.of("/opt/myapp/rules"))) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.walk` phù hợp khi dữ liệu chắc chắn nằm trong một thư mục thật. Nó không tự đi vào JAR nằm trong classpath theo cú pháp `classpath*:`.

### 17.3. Chọn công cụ

| Bài toán | API phù hợp |
| --- | --- |
| Đọc một file classpath đã biết tên | `ResourceLoader.getResource` hoặc `ClassPathResource` |
| Tìm nhiều resource cùng tên ở nhiều JAR | `ResourcePatternResolver.getResources` với `classpath*:` |
| Tìm theo wildcard trong classpath | `PathMatchingResourcePatternResolver` |
| Duyệt thư mục local với NIO features | `Files.walk` |
| Liệt kê object trong S3/blob storage | SDK/listing API của hệ lưu trữ |
| Đăng ký bean theo sự tồn tại của một resource | `@ConditionalOnResource` |

Nếu hệ lưu trữ có API listing/changelog riêng, sử dụng API đó sẽ rõ ràng và đáng tin hơn cố coi nó là filesystem.

## 18. Kiểm thử ResourcePatternResolver

Kiểm thử nên xác nhận pattern tìm được những resource mong đợi và code đọc được nội dung.

Một cấu trúc test fixtures:

~~~text
src/test/resources/
└── test-schemas/
    ├── one.json
    ├── two.json
    └── nested/
        └── three.json
~~~

### 18.1. Test wildcard với JUnit 5

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

class ResourcePatternResolverTest {

    private final ResourcePatternResolver resolver =
            new PathMatchingResourcePatternResolver();

    @Test
    void findsJsonFilesRecursively() throws IOException {
        Resource[] resources = resolver.getResources(
                "classpath*:test-schemas/**/*.json"
        );

        assertThat(resources).hasSize(3);

        assertThat(
                Arrays.stream(resources)
                        .map(Resource::getFilename)
                        .toList()
        ).containsExactlyInAnyOrder(
                "one.json",
                "two.json",
                "three.json"
        );
    }
}
~~~

Test giả định `src/test/resources` có đúng ba file JSON phù hợp và không có fixture cùng pattern ở dependency khác.

### 18.2. Test mảng rỗng

~~~java
@Test
void returnsEmptyArrayForNoMatches() throws IOException {
    Resource[] resources = resolver.getResources(
            "classpath*:folder-that-does-not-exist-xyz/**/*.json"
    );

    assertThat(resources).isEmpty();
}
~~~

Tình huống không match thường được biểu diễn bằng mảng rỗng. Nhưng nếu có lỗi đọc một root hoặc archive, resolver có thể ném `IOException`; test cũng nên xét hành vi lỗi I/O nếu ứng dụng cần chính sách xử lý cụ thể.

### 18.3. Test đọc nội dung qua stream

~~~java
@Test
void canReadSchemaFromClasspath() throws IOException {
    Resource[] resources = resolver.getResources(
            "classpath*:test-schemas/one.json"
    );

    assertThat(resources).hasSize(1);

    try (InputStream input = resources[0].getInputStream()) {
        String text = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );

        assertThat(text).contains("type");
    }
}
~~~

Nhớ import `java.io.InputStream` và `java.nio.charset.StandardCharsets`.

### 18.4. Test chạy từ executable JAR

Một unit test trong IDE thường dùng classpath là các thư mục đã được build. Để xác nhận khả năng quét resource trong packaged Boot JAR, nên có một bước integration/smoke test chạy chính artifact được đóng gói:

~~~bash
java -jar target/schema-discovery-0.0.1-SNAPSHOT.jar
~~~

Ghi nhận số lượng schema được tìm thấy và so sánh với dữ liệu được đóng gói thực tế. Test ở runtime này đặc biệt quan trọng nếu thư viện được dùng trong môi trường với nested JAR hoặc classloader đặc thù.

## 19. Lỗi thường gặp và cách xử lý

### 19.1. Dùng getResource để tìm wildcard

**Sai kỳ vọng:**

~~~java
resourceLoader.getResource("classpath*:schemas/**/*.json");
~~~

`getResource` không có contract trả về nhiều resource từ wildcard.

**Đúng API:**

~~~java
resolver.getResources("classpath*:schemas/**/*.json");
~~~

### 19.2. Chỉ tìm được file ở module đầu tiên

Có thể code sử dụng `classpath:` thay vì `classpath*:` khi thực sự cần quét mọi JAR.

**Cách xử lý:** dùng `classpath*:` và đặt file trong một thư mục con ổn định được đóng gói vào classpath.

### 19.3. Không tìm được file ở root của JAR

Pattern `classpath*:*.json` có thể không duyệt đủ root entries trong mọi classloader/JAR.

**Cách xử lý:** đặt tài nguyên dưới `META-INF/myapp/...` hoặc thư mục con khác rồi tìm theo prefix cố định.

### 19.4. Chạy trong IDE được nhưng executable JAR lỗi

Nguyên nhân phổ biến là dùng `resource.getFile()` hoặc `File` API cho tài nguyên classpath đã nằm trong archive.

**Cách xử lý:** đọc bằng `getInputStream()`; test từ artifact đã đóng gói.

### 19.5. Đếm số file không đúng vì cùng tên

Hai JAR có thể đóng gói cùng tên resource. Nếu code deduplicate bằng `getFilename()`, một file bị mất.

**Cách xử lý:** dùng ID logic hoặc URL/mô tả nguồn phù hợp, không chỉ dùng tên cuối đường dẫn.

### 19.6. Thứ tự quét thay đổi giữa máy

**Nguyên nhân:** thứ tự classpath và filesystem không phải quy tắc nghiệp vụ.

**Cách xử lý:** sort có chủ đích cho log; nếu cần thứ tự áp dụng rule, đưa priority/ID vào metadata và xử lý rõ ràng.

### 19.7. Mất tài nguyên khi build

File nằm ở `src/test/resources` nhưng ứng dụng production chạy từ `src/main/resources` và dependencies runtime.

**Cách xử lý:** kiểm tra file thuộc artifact nào, build có copy resource không và đường dẫn cuối trong JAR có khớp pattern không.

### 19.8. Quét quá rộng làm startup chậm

Pattern như `classpath*:**/*.xml` có thể yêu cầu duyệt nhiều JAR và match file không liên quan.

**Cách xử lý:** thu hẹp root directory và phần mở rộng, ví dụ `classpath*:META-INF/myapp/mappings/**/*.xml`.

### 19.9. Parser lỗi nhưng tưởng resolver lỗi

Resolver chỉ tìm và mở resource; JSON/XML parser, schema validator hoặc logic domain có thể báo lỗi khác.

**Cách xử lý:** ghi log source description và phân biệt `IOException`, parsing exception, validation exception và duplicate ID.

### 19.10. Quên đóng InputStream

**Nguyên nhân:** code gọi `getInputStream()` nhưng không dùng `try-with-resources`.

**Cách xử lý:** đóng stream ở từng resource sau khi đọc, đặc biệt với file/network resource.

### 19.11. Dùng URL wildcard để liệt kê file từ xa

Một endpoint HTTP không bảo đảm hỗ trợ danh sách file bên trong đường dẫn như filesystem.

**Cách xử lý:** dùng API listing của remote storage; chỉ dùng resolver cho các loại location mà implementation thực sự hỗ trợ.

### 19.12. Cho client cung cấp pattern file: tùy ý

**Nguy cơ:** lộ dữ liệu filesystem hoặc khiến server quét nhiều directory không liên quan.

**Cách xử lý:** hạn chế pattern ở cấu hình tin cậy, kiểm tra prefix/root và không đưa nội dung resource tùy ý ra endpoint công khai.

## 20. Thiết kế quy trình nạp nhiều tài nguyên an toàn

Khi dự án cần discovery nhiều resource lúc startup, có thể theo thứ tự:

1. **Xác định nơi đặt resource:** classpath hay filesystem?
2. **Định nghĩa prefix ổn định:** ví dụ `META-INF/myapp/rules/`.
3. **Chọn pattern phù hợp:** ưu tiên root rõ ràng và `classpath*:` nếu có nhiều JAR.
4. **Giới hạn độ rộng:** không quét toàn bộ classpath khi không cần.
5. **Gọi `getResources(...)` và xử lý `IOException`** một cách minh bạch.
6. **Quyết định zero-match có phải lỗi không:** fail fast với dữ liệu bắt buộc; cho phép rỗng khi optional.
7. **Đọc qua `getInputStream()`** và đóng từng stream.
8. **Parse/validate nội dung** bằng parser phù hợp với loại file.
9. **Phát hiện duplicate ID** và quy định precedence rõ ràng.
10. **Đưa dữ liệu đã xử lý vào catalog** để tránh quét lặp lại trên mỗi request.
11. **Kiểm thử packaged runtime** nếu resource nằm trong JAR/nested JAR.
12. **Quan sát được lỗi:** log resource description, pattern, số lượng match và nguyên nhân thất bại.

Một catalog tốt không chỉ tìm được các file mà còn có quy tắc rõ ràng khi thiếu file, file hỏng, trùng định danh hoặc không thể đọc một phần dữ liệu.

## 21. Bài thực hành

### Bài A: Tìm nhiều template

Tạo:

~~~text
src/main/resources/templates/email/
├── welcome.html
├── goodbye.html
└── vi/
    └── welcome.html
~~~

Dùng:

~~~java
resolver.getResources(
        "classpath*:templates/email/**/*.html"
);
~~~

In số file, `getFilename()` và `getDescription()`. Giải thích vì sao hai file `welcome.html` có thể cùng filename nhưng khác nguồn.

### Bài B: So sánh * và **

Với cùng cấu trúc trên, so sánh:

~~~text
classpath*:templates/email/*.html
classpath*:templates/email/**/*.html
~~~

Ghi lại file nào được tìm trong mỗi trường hợp và giải thích ý nghĩa của thư mục con.

### Bài C: Dùng file: thay cho classpath*:

Tạo thư mục `/tmp/myapp-rules` hoặc một thư mục phù hợp trên máy đang dùng, với hai file `.yml`.

Thử:

~~~java
resolver.getResources(
        "file:/tmp/myapp-rules/**/*.yml"
);
~~~

Quan sát sự khác nhau giữa file ngoài filesystem và resource được đóng gói trong JAR.

### Bài D: Đọc từ executable JAR

Đặt một JSON file vào `src/main/resources/schemas`, dùng resolver tìm file và đọc với `getInputStream()`.

Chạy trong IDE, sau đó đóng gói và chạy `java -jar`. Thử giải thích vì sao chuyển sang `getFile()` có thể làm bản JAR lỗi.

### Bài E: Hai dependency có cùng tên resource

Tạo hai module thư viện, mỗi module có:

~~~text
META-INF/myapp/extensions.properties
~~~

Đóng gói cả hai và thêm vào runtime classpath. Dùng:

~~~java
resolver.getResources(
        "classpath*:META-INF/myapp/extensions.properties"
);
~~~

So sánh với:

~~~java
resourceLoader.getResource(
        "classpath:META-INF/myapp/extensions.properties"
);
~~~

Giải thích khác biệt giữa một resource location và nhiều classpath location cùng tên.

### Bài F: Phát hiện rule ID trùng

Cho hai JSON rule có cùng `id` nhưng khác file. Sau khi resolver tìm resource, parse nội dung và fail fast nếu catalog có ID trùng.

Đừng dùng tên file làm khóa duy nhất.

### Bài G: Pattern từ configuration properties

Tạo:

~~~yaml
app:
  schema:
    location-pattern: classpath*:schemas/**/*.json
    required: true
~~~

Bind vào `SchemaProperties`, inject trong service, rồi thử thay bằng một pattern không khớp. Khi `required=true`, ứng dụng phải báo thiếu resource rõ ràng.

### Bài H: Test tài nguyên của project

Thêm ba fixture JSON dưới `src/test/resources/test-schemas/`. Viết JUnit test cho pattern recursive, assert số lượng và nội dung file.

Sau đó thêm một file trong thư mục con và quan sát test thay đổi mà không sửa tên file trong Java source.

## 22. Câu hỏi tự kiểm tra

**1. `ResourcePatternResolver` dùng để làm gì?**

Để giải quyết một location pattern thành mảng `Resource[]`, phục vụ nhu cầu tìm nhiều tài nguyên.

**2. `ResourceLoader.getResource` và `ResourcePatternResolver.getResources` khác nhau thế nào?**

`getResource` trả về một resource location; `getResources` có thể trả nhiều resource phù hợp mẫu tìm kiếm.

**3. Prefix `classpath*:` có ý nghĩa gì?**

Nó cho phép tìm ở nhiều vị trí classpath phù hợp, bao gồm các resource trong nhiều module/JAR.

**4. `*` và `**` khác nhau thế nào?**

`*` khớp trong một đoạn đường dẫn; `**` có thể khớp qua nhiều cấp thư mục.

**5. Vì sao nên đặt resource dưới `META-INF/myapp/...`?**

Để có một root directory rõ ràng, tránh wildcard ở root JAR và hạn chế quét resource không liên quan.

**6. Có nên dùng `Resource.getFile()` cho classpath resource trong executable JAR không?**

Không nên giả định nó hoạt động. Ưu tiên `getInputStream()` để đọc file trong archive.

**7. Resolver có tự parse JSON hoặc validate nội dung không?**

Không. Nó chỉ tìm resource. Ứng dụng phải dùng parser và validator phù hợp.

**8. Có bảo đảm mảng Resource trả về được sắp theo tên không?**

Không nên dựa vào thứ tự kết quả. Nếu cần thứ tự, hãy sắp xếp theo quy tắc tường minh.

**9. Không tìm thấy resource có phải luôn là exception không?**

Không. Pattern không match thường trả mảng rỗng. Ứng dụng tự quyết định khi nào mảng rỗng là lỗi.

**10. Có thể dùng `classpath*:META-INF/myapp/extensions.properties` dù không có wildcard trong path không?**

Có. Prefix `classpath*:` vẫn giúp tìm nhiều resource cùng tên trên classpath.

**11. Có nên gọi resolver mỗi request để quét nhiều JAR không?**

Thường không nếu resource cố định. Nên nạp catalog khi phù hợp và cache kết quả đã xử lý, trừ khi có yêu cầu refresh rõ ràng.

## 23. Kết luận

`ResourcePatternResolver` là API của Spring Framework dành cho tình huống cần **tìm nhiều tài nguyên theo đường dẫn hoặc wildcard**. Implementation `PathMatchingResourcePatternResolver` giúp sử dụng các pattern như `classpath*:schemas/**/*.json` thay vì phải liệt kê thủ công từng file.

Điểm phân biệt quan trọng nhất là: `classpath:` thường nhắm tới một classpath resource/location, còn `classpath*:` cho phép tìm trên nhiều classpath root và JAR. Các ký hiệu `*`, `?` và `**` hỗ trợ tìm theo tên file hoặc cây thư mục. Khi quét nhiều JAR, hãy dùng root directory rõ ràng, không mặc định thứ tự kết quả và không coi filename là định danh duy nhất.

Khi đọc resource, ưu tiên `getInputStream()` và đóng stream, vì file có thể được đóng gói trong executable JAR chứ không có đường dẫn `java.io.File`. Cuối cùng, hãy nhớ resolver chỉ thực hiện **discovery**: parse, validate, xử lý dữ liệu trùng, chính sách khi thiếu resource và bảo mật đường dẫn đều là trách nhiệm của ứng dụng.

Nếu được dùng cùng một convention thư mục rõ ràng và một catalog có kiểm tra dữ liệu, `ResourcePatternResolver` giúp hệ thống Spring Boot mở rộng thêm template, schema hoặc metadata qua nhiều module mà không phải sửa code để đăng ký từng tài nguyên một.

