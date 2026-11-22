# Quy tắc lựa chọn lớp, tài nguyên và phụ thuộc được đưa vào sản phẩm Spring Boot

## 1. Tại sao tùy biến đóng gói không chỉ là đổi tên JAR?

Một ứng dụng Spring Boot có thể biên dịch thành công nhưng **sản phẩm cuối cùng** vẫn thiếu class, thiếu file cấu hình, chứa dependency không cần thiết hoặc vô tình mang theo thông tin nội bộ. Ngược lại, build có thể đóng gói tất cả và “xanh” nhưng khi chạy `java -jar` lại gặp `ClassNotFoundException`, `NoClassDefFoundError`, thiếu resource hoặc xung đột thư viện.

Vì vậy, trước khi chỉnh `pom.xml` hay `build.gradle`, hãy xác định **quy tắc lựa chọn nội dung của sản phẩm**:

1. **Class nào thuộc mã production?** Class biên dịch từ main source set phải đi vào ứng dụng; test classes/fixtures không thuộc executable runtime.
2. **Resource nào cần trên classpath?** Ví dụ `application.properties`, templates và static assets; những file chỉ phục vụ local hoặc bí mật không được đưa vào artifact.
3. **Dependency nào cần để chạy?** Phân biệt compile, runtime, test, provided, development-only và các ngoại lệ riêng của Spring Boot packaging.
4. **Đóng gói loại sản phẩm nào?** Executable Boot JAR, plain library JAR, executable WAR, container image hoặc native image có quy tắc khác nhau.
5. **Lấy bằng chứng bằng gì?** Không chỉ nhìn `BUILD SUCCESS`; phải đọc archive, manifest, resolved dependency graph và chạy đúng binary cuối.

Trong executable Spring Boot **JAR** thường gặp, cấu trúc khái niệm:

~~~text
packaging-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...             # Boot Loader
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/packaging/PackagingApplication.class
    │   ├── application.properties
    │   └── public/package-marker.txt
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── spring-web-<version>.jar
    │   └── ...                                      # runtime JARs thực tế
    ├── classpath.idx                                # có thể có
    └── layers.idx                                   # có thể có
~~~

`BOOT-INF/classes` nhận **đầu ra main** đã build; `BOOT-INF/lib` nhận **các thư viện được lựa chọn để chạy**. Boot Loader ở root JAR dựng classpath và gọi `Start-Class`. Class/test dependency thường **không** được đưa vào Boot executable JAR mặc định.

> **Phạm vi phiên bản:** các cấu hình minh họa dùng Java 17 và Spring Boot 3.3.13 cho Maven/Gradle để dễ đối chiếu, không phải lời khuyên dùng một phiên bản mới nhất. Các plugin hoặc phiên bản mới có thể đổi hành vi/tham số; đối chiếu tài liệu theo đúng version của dự án. Các ví dụ là hướng dẫn thực hành; kết quả kỳ vọng cần được người học chạy kiểm chứng.

## 2. Phân loại nội dung: nguồn, đầu ra build và artifact

Điểm khởi đầu tốt nhất là **theo dõi một file từ source đến nơi nó được đóng gói**.

| Loại đầu vào | Maven thông thường | Gradle thông thường | Vị trí trong executable Boot JAR |
| --- | --- | --- | --- |
| Java production source | `src/main/java` → `target/classes` | `sourceSets.main.java` → `build/classes/java/main` | `BOOT-INF/classes/<package>/...class` |
| Main resource | `src/main/resources` → `target/classes` qua Resources Plugin | `sourceSets.main.resources` → `build/resources/main` qua `processResources` | `BOOT-INF/classes/<resource-path>` |
| Test source | `src/test/java` → `target/test-classes` | `sourceSets.test.java` → `build/classes/java/test` | **Không**, trừ khi build tùy biến đưa vào sai/chủ ý |
| Test resources | `src/test/resources` → `target/test-classes` | `sourceSets.test.resources` → `build/resources/test` | **Không** theo cấu hình thông thường |
| Dependency runtime | Maven dependency resolution và Boot repackage | Gradle `runtimeClasspath`, Boot `bootJar.classpath` | `BOOT-INF/lib/*.jar` |
| Annotation processor | Compiler/processor path | `annotationProcessor` configuration | Bản thân processor **không** mặc định ở runtime; generated main classes/resources có thể được đóng |
| Development tools | `spring-boot-devtools`, `spring-boot-docker-compose` | `developmentOnly` | **Thường loại theo mặc định Boot plugin** |
| File ngoài project (secrets, config ops) | Ngoài resources/build output | Ngoài source set/output | **Không đưa vào JAR**; inject từ môi trường triển khai |

**“Đã có trong project” không đồng nghĩa “đã vào artifact”.** Source code trong `src/test` vẫn có thể compile/test nhưng không vào `BOOT-INF/classes`; một tài liệu dưới `src/main/resources` có thể bị filter/exclude; một runtime dependency có thể bị loại trong repackage. Quy tắc thực tế phải được đọc trên **output cuối cùng**, không chỉ dựa vào folder ở repository.

### 2.1. Những lớp nội dung cần kiểm soát khác nhau

- **Main class output:** code mà app cần tại runtime; nên quyết định membership bằng source set/module boundary. Nếu xóa class hậu biên dịch khi class khác tham chiếu tới nó, sẽ tạo lỗi runtime.
- **Main resource output:** dữ liệu classpath (message bundles, templates, static files, application config, SQL migrations, mapping JSON...). Có thể lọc theo đường dẫn, nhưng việc loại nhầm một resource chỉ được phát hiện khi tính năng sử dụng nó được chạy.
- **Nested dependencies:** những JAR cần thiết để nạp class và chạy ứng dụng; quản lý bằng dependency declaration/scope/configuration, constraints/BOM, sau đó xác nhận packaging.
- **Boot Loader + manifest:** do Spring Boot build plugin tạo theo layout; không tự ý xóa vì “không phải code nghiệp vụ”.
- **Layers và chỉ mục:** `BOOT-INF/layers.idx`/`classpath.idx` ảnh hưởng cách chia layer/classpath order trong điều kiện phù hợp, **không thay thế quy tắc chọn resource/dependency**.

### 2.2. Một quyết định bảo mật quan trọng

File `src/main/resources/secret.json` nếu đã commit chứa token thật thì **loại nó khỏi JAR không làm token biến mất khỏi Git history, build cache, artifact cũ hoặc log**. Phải thu hồi/rotate credential và xử lý repository theo quy trình bảo mật. Đừng dùng `exclude` như cách thay thế secret manager. Tốt nhất không đưa bí mật vào source tree ngay từ đầu; sản phẩm chỉ chứa cấu hình an toàn và nhận secrets qua environment variables/secret store ở runtime.

## 3. Maven: hiểu scope trước khi tùy biến `repackage`

Đối với Maven, một dependency có `scope` và các thuộc tính như `optional`, `exclusions`. Những giá trị đó quyết định nó xuất hiện ở classpath nào, nhưng **Spring Boot repackage có các quy tắc đóng executable JAR riêng**. Cần phân biệt dependency tree với danh sách `BOOT-INF/lib`.

| Maven khai báo | Vai trò Maven | Khi Spring Boot Maven Plugin `repackage` tạo executable JAR theo mặc định |
| --- | --- | --- |
| `compile` (mặc định) | Dùng lúc biên dịch và chạy. | Được xét để đóng như dependency runtime. |
| `runtime` | Cần lúc chạy, không cần compile trực tiếp. | Được xét để đóng. |
| `provided` | Compile có, Maven classpath runtime thông thường coi container/JDK cung cấp. | **Vẫn được Boot repackage bao gồm** đối với executable JAR theo tài liệu Boot; không được mặc định coi là “loại khỏi JAR”. |
| `test` | Dùng để compile/run tests. | **Không** đưa vào executable runtime JAR mặc định. |
| `system` | Thư viện trỏ path hệ thống, kém tái lập. | Không được bao gồm theo mặc định; `includeSystemScope` mặc định `false`, không khuyến khích dùng. |
| `optional=true` trên dependency trực tiếp | Giới hạn transitive propagation tới downstream Maven consumers. | **Không phải lệnh “exclude khỏi executable JAR”**; Boot `repackage` có thể bao gồm optional dependency (ngoại lệ devtools/docker-compose theo mặc định). |

**Điểm dễ sai nhất:** với Boot **executable JAR**, `<scope>provided</scope>` **không bảo đảm thiếu thư viện đó trong `BOOT-INF/lib`**. Spring Boot Maven Plugin bao gồm cả provided dependencies; nếu một artifact cụ thể không nên được phân phối, cần xét rõ dependency cần ở đâu và dùng cấu hình exclude phù hợp. Với **WAR**, provided/container dependencies có quy tắc thư mục riêng; không áp trực tiếp kết luận JAR cho WAR.

### 3.1. Ba vị trí điều khiển dependency khác nhau

1. **Khai báo dependency Maven:** `<dependency>` với scope và exclusions thay đổi các dependency được resolve cho build.
2. **Dependency management/BOM:** quản lý versions/constraints; một entry trong `<dependencyManagement>` **không tự thêm dependency**.
3. **Spring Boot Maven Plugin `repackage`:** nhận artifact JAR/WAR đã được Maven tạo rồi đóng lại, có các tùy chọn như `excludes`, `excludeGroupIds`, `includes`, `excludeDevtools`, `excludeDockerCompose`, `includeSystemScope`. Các tùy chọn này tác động tới lựa chọn dependency trong quá trình repackaging, **không phải lệnh xóa dependency từ compile classpath hoặc xóa source**.

Khi thay đổi tầng 3, bạn có thể làm artifact thiếu một dependency **trong khi compile và test vẫn pass**. Luôn chạy smoke test trên `java -jar` sau mỗi thay đổi.

## 4. Gradle: phân biệt configuration và classpath dùng để đóng JAR

Khi dùng Gradle Java plugin, các dependency thường được khai báo theo configuration:

| Gradle configuration | Compile main? | Runtime main/`runtimeClasspath`? | Có được cân nhắc khi `bootJar` đóng dependency? |
| --- | --- | --- | --- |
| `implementation` | Có. | Có. | Có. |
| `runtimeOnly` | Không cần compile. | Có. | Có. |
| `compileOnly` | Có. | **Không**. | **Không**, nếu không được đưa vào một configuration khác. |
| `annotationProcessor` | Processor path, không phải normal compile/runtime dependency. | Không mặc định. | Không mặc định; output generated main classes có thể vào JAR. |
| `testImplementation` | Test compile, không main. | Không trong main runtime. | Không mặc định. |
| `testRuntimeOnly` | Test runtime. | Không trong main runtime. | Không mặc định. |
| `developmentOnly` (Spring Boot plugin) | Dành cho development. | Không thuộc `bootJar` mặc định. | **Bị loại theo mặc định**, trừ khi cố ý bổ sung vào `bootJar.classpath`. |

Spring Boot Gradle Plugin tạo task `bootJar` (khi kết hợp với Java plugin). Task này là một dạng `Jar` đặc biệt, **gói main source set output cùng các dependency runtime được chọn**. `bootJar` có `classpath` riêng có thể được tùy biến; ở cấu hình chuẩn nó lấy runtime classpath phù hợp và mặc định loại `developmentOnly`.

**Cẩn thận:** `compileOnly` là configuration **không đi theo runtimeClasspath**; nó không phải một cách nói khác của Maven `provided` khi Boot repackage. Không nên áp bảng scope của Maven sang Gradle một-một. Với executable WAR, Gradle có `providedRuntime` dành cho thư viện servlet container và layout `WEB-INF/lib-provided`.

### 4.1. Tập dependency do BOM quản lý khác tập dependency được đóng

Một Maven BOM/Gradle platform có thể nêu hàng trăm phiên bản, nhưng không có nghĩa mọi JAR trong BOM đều được tải/đóng. Chỉ những dependency **được khai báo hoặc kéo vào đồ thị** và thuộc runtime archive classpath mới đi vào sản phẩm. Vì vậy:

- **BOM = thông tin quản lý version**, không phải danh sách “hãy đóng tất cả”.
- **Runtime dependency graph = đầu vào quan trọng** để biết vì sao dependency xuất hiện.
- **Executable archive = đầu ra cuối cần kiểm tra** vì còn có lựa chọn/exclusions của plugin.

Dùng Maven `dependency:tree` hoặc Gradle `dependencies --configuration runtimeClasspath` và so sánh với `BOOT-INF/lib` để tìm khác biệt có lý do, không coi mọi khác biệt là lỗi ngay.

## 5. Quy tắc chọn lớp: main source set trước, exclude bytecode sau cùng

Điều kiện thiết kế đầu tiên nên là **chọn đúng module và source set**:

- Class ở `src/main/java` là ứng viên cho production artifact.
- Class ở `src/test/java` là test, cần cho test runner nhưng không đưa vào runtime JAR.
- Generated class do annotation processors tạo cho **main** có thể vào artifact nếu compiler output được đóng bình thường.
- Build-time plugin code hoặc Gradle `build-logic` không phải production class của app.
- Một library module được app tham chiếu có thể được đóng như một **nested dependency JAR** trong `BOOT-INF/lib`, thay vì flatten mọi class của library vào `BOOT-INF/classes`.

### 5.1. Nếu phải bỏ một class khỏi sản phẩm thì sao?

Có thể cấu hình Maven Jar Plugin/Gradle CopySpec để loại entry, nhưng cần đánh giá:

1. Class đó có bị business code, dependency injection, reflection, Spring component scanning hoặc `ServiceLoader` sử dụng không?
2. Nó có tham gia public API hoặc serialization/JPA mapping không?
3. Có resource/META-INF descriptor nào còn trỏ tới class bị loại không?
4. Bỏ class có khiến main entrypoint, Spring auto-configuration hay một profile nào đó bị lỗi không?
5. Có nên chuyển class sang **test sources**, **separate module** hoặc **dev-only source set** trước khi nghĩ đến exclude hậu biên dịch?

**Khuyến nghị:** nếu class thật sự không thuộc production, đặt nó vào đúng source set/module ngay từ đầu. Loại `.class` bằng path pattern ở cuối build dễ tạo artifact chạy được trong happy path nhưng fail khi một tính năng ít dùng gọi tới class.

### 5.2. Vì sao `mainClass` không phải bộ lọc class?

Cấu hình `Start-Class`/`mainClass` chỉ quyết định **điểm khởi động**. Nó **không** có nghĩa Spring Boot chỉ đóng class reachable từ main theo phân tích chương trình. Boot JAR không tự loại bỏ mọi class chưa được gọi như một tree shaker. Class được đóng dựa vào **main output và archive copy rules**, không dựa vào call graph của `main()`.

Nếu muốn giảm kích thước đáng kể, hãy tối ưu dependencies/modules và cân nhắc AOT/native image theo đúng yêu cầu, đừng kỳ vọng đổi `mainClass` xóa “class không dùng”.

## 6. Quy tắc chọn tài nguyên: đường dẫn, filtering và tính bí mật

Resource khác Java code ở chỗ nó có thể không được compiler kiểm tra. File thiếu hoặc bị thay đổi trong `processResources` vẫn có thể khiến app start rồi thất bại khi sử dụng tính năng tương ứng.

Ví dụ những main resources có thể cần trong sản phẩm:

- `application.properties`, `application.yml` và những profile-specific variants không chứa bí mật.
- `static/` (CSS/JS/images) nếu app phục vụ static content.
- `templates/` nếu app render Thymeleaf/Mustache/Freemarker.
- `messages*.properties` cho localization.
- `db/migration/` cho Flyway, hoặc migration paths tương ứng.
- `META-INF/services/**`, `META-INF/spring/**` và các metadata của framework nếu được dùng.
- File mapping/rules/schema/CSV thật sự được ứng dụng nạp bằng classpath resource.

Những thứ **không nên** đưa vào main resources: private keys/passwords, ghi chú developer, database dump, test fixtures, tool output, backup config. Một file nằm dưới `src/main/resources` thường là ứng viên được copy **trừ khi có rule exclude**; vậy hãy tổ chức folder rõ ràng và kiểm tra archive thực.

### 6.1. Resource filtering có thể làm thay đổi hành vi

Trong Maven, resource filtering là một giai đoạn thay token trước khi file vào output; trong Gradle có thể dùng `expand`/`filter` trong `processResources`. **Không bật filtering trên mọi file một cách thiếu kiểm soát**:

- Spring Boot dùng placeholders runtime như `${SERVER_PORT:8080}` (hoặc `${some.property}`). Bộ lọc build-time không được thay nhầm những placeholder cần giữ tới runtime.
- Các file binary có thể bị hỏng khi áp filtering text.
- Secret không được “lọc” vào final archive chỉ vì Maven/Gradle có access vào environment variables khi build.
- Khi build cho nhiều môi trường, nên giữ artifact giống nhau và chuyển cấu hình qua environment/secret store ở runtime, thay vì tạo một JAR chứa credentials riêng cho mỗi môi trường.

Có thể dùng `@project.version@` với cấu hình Maven starter parent phù hợp cho metadata build, nhưng phải kiểm tra nội dung **sau processing**. Trong ví dụ dưới đây, ta cố ý **không filter** resources, để tách việc lựa chọn file khỏi vấn đề thay token.

## 7. Dự án thực hành chung: phân biệt included, excluded và test-only

Ta dùng **một Spring Boot Web app** với hai endpoint để xác nhận:

- `GET /ping` trả `pong`: Java production class và Web runtime dependencies hoạt động.
- `GET /marker` đọc một resource trên classpath và trả `included-v1`: resource được đưa vào `BOOT-INF/classes` đúng.
- `internal/debug-notes.txt` nằm trong source resources nhưng phải **không có trong executable artifact** theo quy tắc package.
- `src/test/resources/only-for-tests.txt` và `PackagingApplicationTest.class` chỉ thuộc test phase, phải **không có trong runtime JAR**.

Cấu trúc:

~~~text
packaging-demo/
├── pom.xml                         # CHỌN Maven nếu dùng Maven
├── settings.gradle                 # CHỌN Gradle nếu dùng Gradle
├── build.gradle                    # Không cần đồng thời cấu hình hai tool
├── src/
│   ├── main/
│   │   ├── java/com/example/packaging/PackagingApplication.java
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── public/package-marker.txt
│   │       └── internal/debug-notes.txt
│   └── test/
│       ├── java/com/example/packaging/PackagingApplicationTest.java
│       └── resources/only-for-tests.txt
└── (Maven Wrapper HOẶC Gradle Wrapper, do project tạo)
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=packaging-demo
server.port=8080
~~~

File `src/main/resources/public/package-marker.txt`:

~~~text
included-v1
~~~

File `src/main/resources/internal/debug-notes.txt`:

~~~text
This local diagnostic resource must not be packaged.
~~~

File `src/test/resources/only-for-tests.txt`:

~~~text
test-fixture-only
~~~

Đây đều là nội dung **giả lập vô hại**, không phải credential thật. Mục tiêu là quan sát rõ inclusion/exclusion.

### 7.1. Java 17 main class

`src/main/java/com/example/packaging/PackagingApplication.java`:

~~~java
package com.example.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PackagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/marker")
    public String marker() throws IOException {
        ClassLoader loader = Thread.currentThread().getContextClassLoader();
        try (InputStream in = loader.getResourceAsStream("public/package-marker.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing public/package-marker.txt");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }
}
~~~

Lưu ý:

- `@SpringBootApplication` và `main()` tạo Spring Boot context, `@RestController` công bố HTTP endpoints.
- `marker()` dùng **InputStream classpath resource**, không tạo `new File("BOOT-INF/classes/...")`. Resource trong executable JAR không phải file thường trên filesystem.
- `readAllBytes()` và `StandardCharsets.UTF_8` có trong Java 17. Kết quả `trim()` giúp không phụ thuộc newline cuối file resource.
- Nếu resource bị loại nhầm, endpoint `/marker` sẽ fail với `IllegalStateException`; đây là kiểm chứng rất thực tế.
- Class này chạy được **trong project Maven/Gradle Spring Boot có dependency**, không phải chương trình Java thuần biên dịch bằng `javac PackagingApplication.java` không có classpath.

### 7.2. JUnit + MockMvc test

`src/test/java/com/example/packaging/PackagingApplicationTest.java`:

~~~java
package com.example.packaging;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PackagingApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void mainClassAndMarkerResourceWork() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));

        mvc.perform(get("/marker"))
           .andExpect(status().isOk())
           .andExpect(content().string("included-v1"));
    }
}
~~~

Đây là **test source**: nó tồn tại để kiểm tra, không phải thành phần runtime. MockMvc kiểm tra request mapping qua Spring test context, chưa phải `java -jar`. Test pass xác nhận resource có trên **test runtime classpath**, nhưng bạn vẫn cần đọc **archive cuối cùng** và chạy binary thật để xác nhận được package đúng.

## 8. Maven hoàn chỉnh: loại main resource theo path, giữ runtime deps cần thiết

Ví dụ `pom.xml` bên dưới dùng Spring Boot starter parent và khai báo **resource copy rule** rõ ràng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <!-- Ví dụ tắt filtering có chủ đích để không thay đổi nội dung resource -->
                <filtering>false</filtering>
                <excludes>
                    <exclude>internal/**</exclude>
                    <exclude>**/*.pem</exclude>
                </excludes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Diễn giải:**

1. `maven-resources-plugin` xử lý `src/main/resources` trước packaging. Khối `<resources>` yêu cầu copy resource từ nguồn, **trừ `internal/**` và `**/*.pem`**. `public/package-marker.txt` và `application.properties` vẫn được copy.
2. `<filtering>false</filtering>` có chủ đích; không vô tình làm sai Spring `${...}` placeholders. Nếu dự án cần resource filtering, cấu hình lại **đúng các resources/filtering semantics** thay vì sao chép cấu hình trên mà không xem xét.
3. Parent Boot quản lý dependency versions và mặc định plugin. Khai báo `spring-boot-maven-plugin` để goal `repackage` được áp trong lifecycle phù hợp.
4. `spring-boot-starter-test` có `test` scope nên không trở thành nested runtime JAR của ứng dụng.
5. Các exclusions ở **`<build><resources>`** là **path/file rules**. Chúng **không** tương đương với `<exclusions>` của dependency Maven hay `<excludes>` của Spring Boot Maven Plugin.

**Quan trọng:** khi tự viết `<build><resources>`, bạn có thể **thay đổi các mặc định resource processing/filtering** được kế thừa từ starter parent. Bài này chọn không filtering để làm ví dụ minh bạch; một hệ thống đang dùng `@project.version@` hoặc sinh config ở build time cần giữ/reproduce các rule cần thiết trước khi áp dụng.

### 8.1. Lệnh build và các bước quan sát của Maven

~~~bash
# Trong root Maven project có Wrapper (macOS/Linux)
./mvnw -version
./mvnw clean verify

# Xem main resources sau processing và lớp main sau compile
# (dùng ls/cat hoặc file explorer trên hệ điều hành tương ứng)
ls -l target/classes/
ls -l target/classes/public/

# Đọc executable JAR
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Kỳ vọng (nếu build thành công và các file như bài):

~~~text
BOOT-INF/classes/com/example/packaging/PackagingApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/public/package-marker.txt
BOOT-INF/lib/<các-thư-viện-runtime-thực-tế>.jar
~~~

**Không** được có:

~~~text
BOOT-INF/classes/internal/debug-notes.txt
BOOT-INF/classes/com/example/packaging/PackagingApplicationTest.class
BOOT-INF/classes/only-for-tests.txt
~~~

`PackagingApplicationTest.class` thường nằm ở `target/test-classes` trong build output, **nhưng không nằm trong executable JAR**. Vì đường dẫn `BOOT-INF/classes/only-for-tests.txt` không tồn tại mặc định, nếu một resource test cố tình được đưa vào JAR, nó cũng cần bị phát hiện bằng grep/tìm tên file toàn archive, không chỉ so một path duy nhất.

### 8.2. Maven: exclude một dependency khỏi repackaged archive

Đây là **mảnh cấu hình minh họa** trong `spring-boot-maven-plugin`; các tọa độ `com.example:unused-agent` là ví dụ giả định để giải thích cú pháp, **không phải dependency thực trong POM chạy được ở mục 8**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludes>
            <exclude>
                <groupId>com.example</groupId>
                <artifactId>unused-agent</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
~~~

Tùy chọn này bảo Spring Boot Plugin **không đem artifact được chỉ định** vào executable archive, và các goal có cùng dependency filtering như `run` có thể bị ảnh hưởng. Nó **không xóa** dependency khỏi `pom.xml` hoặc khỏi compile classpath Maven. Phải xác nhận ứng dụng **không cần class/resource từ artifact đó tại runtime**; nếu cần, việc exclude có thể biến một build xanh thành lỗi `NoClassDefFoundError`.

Tùy chọn `excludeGroupIds` có phạm vi rộng hơn (loại cả groupId) và nguy hiểm nếu vô tình loại nhiều runtime dependencies. `includes` là danh sách chọn artifact của plugin, **không phải cách whitelist file resource**. Đừng dùng `<includes>` ở Boot Plugin để lọc `src/main/resources`.

### 8.3. Maven: khác nhau giữa dependency exclusions và plugin exclusions

Mảnh khai báo transitive dependency exclusion:

~~~xml
<!-- Chỉ minh họa cú pháp; các tọa độ phải được thay bằng dependency thật -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>business-sdk</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>unneeded-transport</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

`<exclusions>` ở dependency là thay đổi **đồ thị resolve transitive dependencies** cho dependency này; còn Boot Plugin `<excludes>` là quyết định **đưa gì vào sản phẩm đã được build**. Hai điểm khác nhau và không thay thế nhau. Nếu dependency không dùng ở cả compile/test/runtime, cách sạch nhất là **xóa khai báo hoặc chỉnh dependency graph từ đầu**.

## 9. Gradle hoàn chỉnh: filter resource output, chọn đúng runtimeClasspath

Dùng cùng Java source/resources/test ở mục 7, nhưng thay POM bằng file Gradle. Đây là **lựa chọn build độc lập**, không nhất thiết giữ hai build system cùng lúc.

`settings.gradle`:

~~~groovy
rootProject.name = 'packaging-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('processResources') {
    // Chỉ tác động tới main resources được copy, không chạm test resources.
    exclude 'internal/**'
    exclude '**/*.pem'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Giải thích:**

- `java` tạo `main`/`test` source sets, `processResources`, `compileJava`, `test` và JAR task. `org.springframework.boot` thêm `bootJar`.
- `io.spring.dependency-management` cùng Spring Boot Plugin quản lý versions cho starters/test library. Một cách khác là Gradle native `platform("org.springframework.boot:spring-boot-dependencies:...")`; chọn một mô hình quản lý dependency nhất quán.
- `processResources` là **Copy task** tạo main resource output. Hai `exclude` lọc path trước khi tài nguyên đến `build/resources/main`, rồi `bootJar` lấy đầu ra đó để đưa vào `BOOT-INF/classes`.
- `testImplementation` và `testRuntimeOnly` phục vụ test, không được xem là production runtime deps chỉ vì JUnit test pass.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` cung cấp launcher JUnit Platform cho Gradle test runtime phù hợp ví dụ.
- Không khai báo `spring-boot-devtools` nên ví dụ không có development-only dependency; nếu có thì Boot Gradle Plugin mặc định không đưa `developmentOnly` vào executable archive.

Có thể dùng `sourceSets.main.resources.exclude` nếu muốn quy tắc loại resource áp **ngay ở nguồn main resource set** trên nhiều task. Ví dụ ở trên chọn `processResources` để chỉ rõ giai đoạn nào quyết định nội dung resource output; khi dự án có task tùy biến đọc thẳng source resources hoặc `bootRun.sourceResources`, hãy kiểm tra lại vì những đường đi đó có thể không qua cùng filtering.

### 9.1. Build và xác nhận Gradle

~~~bash
./gradlew --version
./gradlew clean build

# Xem source set runtime graph
./gradlew dependencies --configuration runtimeClasspath

# Xem nội dung executable JAR và các file thư viện build
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Theo cấu hình thông thường, `bootJar` tạo file không có classifier, còn task `jar` có thể tạo `packaging-demo-0.0.1-SNAPSHOT-plain.jar`. Không dùng wildcard chọn nhầm `*-plain.jar` cho runtime smoke test. Nếu đã tùy biến `archiveFileName`/classifier, lấy tên thật từ task output hoặc `build/libs`.

### 9.2. Gradle: scope selection và dependency exclusion

Một ví dụ **khai báo transitive exclusion** (mảnh, tọa độ giả định):

~~~groovy
dependencies {
    implementation('com.example:business-sdk:1.0.0') {
        exclude group: 'com.example', module: 'unneeded-transport'
    }
}
~~~

`exclude group/module` áp cho đường dependency được khai báo và ảnh hưởng resolution graph; artifact có thể vẫn tới classpath theo đường dependency **khác**. Dùng `dependencyInsight` khi cần biết tại sao artifact vẫn xuất hiện. Không coi đó là một chỉ thị “xóa file khỏi ZIP sau khi đóng”.

Khi cần đổi thành phần mà `bootJar` đóng, bạn có thể cấu hình **task `bootJar.classpath`** với FileCollection/resolvable configuration có chủ đích. Tuy nhiên thay `classpath` một cách tùy tiện có thể xóa luôn Spring Framework, starter hoặc project dependencies: đây là cấu hình **nâng cao**, phải dựa trên runtimeClasspath đã phân tích và kiểm tra executable JAR sau thay đổi. Đừng sao chép một `bootJar { classpath = files() }` rỗng chỉ để làm JAR nhỏ.

### 9.3. `bootJar`, `jar` và copy/exclude rules

- `bootJar` tạo Spring Boot executable JAR chứa loader, `BOOT-INF/classes` và `BOOT-INF/lib`.
- `jar` tạo plain/library JAR. Nếu không tùy biến, Boot Gradle Plugin thường đặt classifier `plain` để tách output.
- `tasks.named('processResources') { exclude ... }` ảnh hưởng những resource đi vào main output, do đó có thể ảnh hưởng **cả plain JAR và bootJar**.
- `tasks.named('bootJar') { ... }` có thể nhận một số tùy chọn đóng gói chuẩn từ Gradle Jar/CopySpec, nhưng với path layout do BootJar dựng nên không được suy rằng glob giống source path sẽ luôn trúng entry cuối. Luôn đối chiếu `jar tf` thực tế.

Muốn loại một resource khỏi **chỉ một artifact** mà vẫn giữ trên development classpath, hãy cân nhắc một task staging/copy có input/output rõ ràng và test artifact, thay vì áp exclude toàn main output một cách khó dự đoán.

## 10. Spring Boot special cases: devtools, Docker Compose, optional/provided

### 10.1. Maven `spring-boot-devtools`

Ví dụ nếu thêm trong Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Đừng suy “`optional=true` làm nó bị loại khỏi executable JAR” theo quy tắc Maven chung. **Spring Boot Maven Plugin** chủ động loại `spring-boot-devtools` theo mặc định thông qua `excludeDevtools=true`; `spring-boot-docker-compose` cũng được loại mặc định qua `excludeDockerCompose=true` ở dòng có hỗ trợ. Nếu vô tình đặt `excludeDevtools=false`, bạn thay đổi package contents. Kiểm tra mục đích và rủi ro trước khi làm.

### 10.2. Gradle `developmentOnly`

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Boot Gradle Plugin **không đóng** các dependency trong `developmentOnly` vào executable JAR/WAR theo mặc định. Nếu một nhóm cố ý thêm chúng qua `bootJar.classpath`, package contents sẽ khác mặc định và cần được rà soát kỹ. Không để DevTools hoặc tooling development vô tình chạy trong production.

### 10.3. Maven `provided` khác Gradle `compileOnly`

Giả sử một dependency chỉ cần compile theo ý người viết:

- Maven `provided` trong một **Boot executable JAR** vẫn có thể được plugin đóng theo mặc định.
- Gradle `compileOnly` nằm ngoài `runtimeClasspath` thông thường nên không được `bootJar` đóng mặc định.
- Với **executable WAR**, Spring Boot có layout khác: `WEB-INF/classes`, `WEB-INF/lib` và với dependency servlet container phù hợp còn có `WEB-INF/lib-provided`. Gradle `providedRuntime` là lựa chọn phù hợp hơn `compileOnly` khi đóng executable/deployable WAR.

Đây là lý do không dùng một bảng “scope mapping” hời hợt để chuyển Maven sang Gradle. Cần hiểu **loại artifact + task/goal + classpath thực**.

### 10.4. Dependency đóng theo runtime có thể khác dependency “dùng ở startup”

Một library có thể chỉ được nạp khi người dùng kích hoạt một endpoint hiếm, gọi một job định kỳ, đọc một file Excel hoặc bật một Spring profile. Nếu bạn loại nó vì smoke test `/ping` vẫn pass, lỗi có thể chỉ xuất hiện sau deploy. Vì vậy trước khi loại dependency, phân tích code path, optional features, Spring auto-configuration, `ServiceLoader`, reflection và report coverage/integration test thích hợp.

## 11. Resource filtering và config theo môi trường: tránh đóng nhầm bí mật

Giả sử file Spring Boot chứa:

~~~properties
server.port=${SERVER_PORT:8080}
spring.application.name=packaging-demo
~~~

Spring Boot xử lý placeholder khi **chạy**; không cần build lại JAR chỉ để đổi `SERVER_PORT`. Nhưng nếu dùng filtering Maven/Gradle bất cẩn, chuỗi `${SERVER_PORT:8080}` có thể bị coi là template build-time và biến đổi ngoài ý muốn.

### 11.1. Nếu thực sự cần build metadata

Ví dụ muốn app biết version của artifact, có thể đặt token `@project.version@` trong một resource chuyên biệt rồi cấu hình filtering đúng delimiter. Trong Maven starter parent, một số mặc định filtering được cấu hình để giảm xung đột với Spring placeholders. Nếu bạn ghi đè toàn bộ `<resources>` như ví dụ mục 8, các mặc định ấy có thể không còn hoạt động: cần nêu và kiểm tra lại.

Trong Gradle, một ví dụ mảnh riêng cho template:

~~~groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(projectVersion: project.version.toString())
    }
}
~~~

Chỉ dùng mảnh này nếu `src/main/resources/build-info.properties` là template có biến `${projectVersion}` để build; nó **không được** coi là yêu cầu áp expand cho toàn bộ resources. Với Spring placeholders, hãy hạn chế filtering theo file đích và kiểm tra nội dung trong `BOOT-INF/classes` sau đóng gói.

### 11.2. Môi trường prod/test/dev có nhất thiết tạo ba JAR không?

**Không.** Trong nhiều kiến trúc, nên đóng **một executable artifact bất biến** rồi truyền profile, endpoint, credentials và feature flags qua runtime environment. Ví dụ:

~~~bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

Điều này chỉ là ví dụ cách chọn profile, **không** có nghĩa trong archive phải chứa bí mật production. File `application-prod.yml` có thể nằm trong JAR nếu chỉ chứa cấu hình không nhạy cảm, còn secrets được inject từ ngoài.

Nếu cần các distribution thật sự khác nhau theo khách hàng hoặc license, hãy định nghĩa package variant có tên rõ ràng, source sets/task inputs riêng, test từng variant; không trộn nhiều rule exclude dựa vào environment của máy build mà không trace được.

## 12. Phân biệt resource exclusion, dependency exclusion và class exclusion

Một lỗi phổ biến là dùng một loại `exclude` để giải quyết sai lớp vấn đề.

| Muốn thay đổi gì? | Maven: vị trí chính | Gradle: vị trí chính | Không nên làm |
| --- | --- | --- | --- |
| Bỏ file `internal/debug-notes.txt` khỏi product | `<build><resources><resource><excludes>` / Resources Plugin | `processResources.exclude` hoặc source set resource rules | Dùng Boot Plugin dependency excludes để lọc path. |
| Bỏ transitive dependency không cần | `<dependency><exclusions>` | `dependency { exclude group/module }` | Chỉ xóa nested JAR thủ công sau build. |
| Bỏ một dependency khỏi Boot repackaging (có chủ đích) | `spring-boot-maven-plugin<configuration><excludes>` | Chỉnh dependency graph hoặc `bootJar.classpath` có kiểm chứng | Thay source set class exclusions nếu đây là library JAR. |
| Bỏ devtools khỏi executable archive | Mặc định Boot Plugin `excludeDevtools=true` | `developmentOnly` mặc định không đóng | Đặt DevTools production cùng runtime library nếu không thật sự cần. |
| Chặn test class vào product | Đặt class ở `src/test/java` | Dùng `sourceSets.test` | Cho test vào main rồi loại bằng glob khó bảo trì. |
| Bỏ class production không dùng | Tách module/source set hoặc chỉnh source design | Tách module/source set hoặc chỉnh source design | Xóa `.class` hậu biên dịch trong khi class khác còn tham chiếu. |
| Chỉ đổi main entrypoint | Boot Maven Plugin `mainClass` | `bootJar.mainClass` hoặc `springBoot.mainClass` | Nhầm với include/exclude class tree. |
| Chọn executable WAR thay JAR | Maven `packaging=war` + Boot plugin + servlet dep scope | Gradle `war` + Boot `bootWar` + `providedRuntime` | Áp `BOOT-INF` layout của JAR cho WAR. |

**Cách đặt câu hỏi đúng trước khi sửa:** “Tôi cần thay đổi **đồ thị dependency**, **main output**, hay **chỉ archive copy selection**?” Sau đó chọn chính xác build phase và kiểm chứng đầu ra sau phase đó.

## 13. Quy trình QA: từ source đến runtime có bằng chứng

Dùng đúng file Java và resource ở mục 7, chọn Maven hoặc Gradle, rồi làm lần lượt:

### 13.1. Bước 1 — build và test phải chạy thật

Maven:

~~~bash
./mvnw clean verify
~~~

Gradle:

~~~bash
./gradlew clean build
~~~

Kiểm tra report:

- Maven: `target/surefire-reports/` phải cho thấy test `mainClassAndMarkerResourceWork` đã chạy và pass.
- Gradle: `build/test-results/test/` và `build/reports/tests/test/` ghi kết quả JUnit.
- Nếu `0 tests` hoặc `NO-SOURCE`, đừng kết luận test pass chỉ vì build thành công.

### 13.2. Bước 2 — chọn đúng artifact và xem entry

Maven:

~~~bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Gradle:

~~~bash
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Kỳ vọng có `META-INF/MANIFEST.MF`, Boot Loader, `BOOT-INF/classes/com/example/packaging/PackagingApplication.class`, `BOOT-INF/classes/public/package-marker.txt`, `BOOT-INF/classes/application.properties` và nhiều `BOOT-INF/lib/*.jar` được runtime sử dụng.

**Kiểm tra các entry không được có:**

~~~text
BOOT-INF/classes/internal/debug-notes.txt
BOOT-INF/classes/only-for-tests.txt
BOOT-INF/classes/com/example/packaging/PackagingApplicationTest.class
BOOT-INF/lib/junit-jupiter-<version>.jar
BOOT-INF/lib/spring-boot-devtools-<version>.jar
~~~

Đối với JUnit/DevTools, đừng chỉ kiểm tra đúng các filename có version giả định; cần rà tên artifact thực tế bằng filter hoặc duyệt entries. Các tệp test chỉ có trong test output nếu project thật dùng default source sets.

### 13.3. Bước 3 — lọc tích cực và phủ định bằng CLI

Ví dụ macOS/Linux với Maven JAR:

~~~bash
JAR=target/packaging-demo-0.0.1-SNAPSHOT.jar

# Các entry bắt buộc
jar tf "$JAR" | grep '^BOOT-INF/classes/com/example/packaging/PackagingApplication.class$'
jar tf "$JAR" | grep '^BOOT-INF/classes/public/package-marker.txt$'
jar tf "$JAR" | grep '^BOOT-INF/lib/'

# Những entry phải bị loại
jar tf "$JAR" | grep -E '(^BOOT-INF/classes/internal/|PackagingApplicationTest.class|only-for-tests.txt|/junit-jupiter-|spring-boot-devtools-)'
~~~

Ở lệnh cuối, **không có dòng được in ra** (và `grep` thường trả exit code 1) là **kỳ vọng** cho ví dụ, không phải lỗi của Java application. Đối với pipeline CI, phải viết assertion có exit code rõ thay vì chỉ đọc output bằng mắt.

Một script nhỏ kiểm tra có/không (macOS/Linux, cần `grep`):

~~~bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/packaging-demo-0.0.1-SNAPSHOT.jar"
LIST="$(jar tf "$JAR")"

# Có class và resource sản phẩm
printf '%s\n' "$LIST" | grep -q '^BOOT-INF/classes/com/example/packaging/PackagingApplication.class$'
printf '%s\n' "$LIST" | grep -q '^BOOT-INF/classes/public/package-marker.txt$'

# Không có resource nội bộ, test class/fixture hoặc DevTools
if printf '%s\n' "$LIST" | grep -Eq '(^BOOT-INF/classes/internal/|PackagingApplicationTest.class|only-for-tests.txt|spring-boot-devtools-)'; then
    echo "FAIL: unwanted file found in executable JAR" >&2
    exit 1
fi

echo "PASS: required entries included, forbidden entries excluded"
~~~

**Stdout kỳ vọng khi script đạt điều kiện:**

~~~text
PASS: required entries included, forbidden entries excluded
~~~

Nếu có file không mong muốn, script in một dòng lỗi ra **stderr** và exit code 1. Script trên chỉ kiểm tra vài điều kiện đại diện, không chứng minh toàn bộ dependency graph an toàn hoặc không còn bí mật trong archive.

Với Gradle, đổi biến `JAR` thành `build/libs/packaging-demo-0.0.1-SNAPSHOT.jar`. Trên Windows PowerShell, thay `grep` bằng `Select-String` hoặc dùng test Java riêng; không chạy nguyên Bash script trong PowerShell rồi suy ra project lỗi.

### 13.4. Bước 4 — đọc resource đã vào archive

Với `unzip`:

~~~bash
unzip -p "$JAR" BOOT-INF/classes/public/package-marker.txt
unzip -p "$JAR" BOOT-INF/classes/application.properties
~~~

`unzip -p` trích một entry ra stdout mà không cần giải nén cả archive. Đường dẫn là **classpath location trong executable JAR**, không phải filesystem path nằm cạnh JAR. Nếu không có `unzip`, dùng `jar xf` trong một **thư mục kiểm tra riêng** và đọc file sau khi extract; không trích toàn bộ archive đè lên source.

Kết quả kỳ vọng của marker file:

~~~text
included-v1
~~~

### 13.5. Bước 5 — chạy chính binary đã đóng

Dừng `spring-boot:run`/`bootRun` đang sử dụng cùng port. Maven:

~~~bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

Hoặc Gradle:

~~~bash
java -jar build/libs/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

Ở terminal khác, sau khi app ready:

~~~bash
curl -i http://localhost:18085/ping
curl -i http://localhost:18085/marker
~~~

Kỳ vọng HTTP 200 với body tương ứng `pong` và `included-v1`. Thông điệp startup/HTTP headers/latency có thể khác theo JDK/web server/OS; **không** coi output mô tả là log đã chạy. Đây mới là phép thử **artifact contents + classloading + HTTP runtime** cùng lúc.

## 14. Trường hợp multi-module: đừng đóng sai module hoặc bỏ dependency nội bộ

Một repository có module `core`, `api`, `app` thường cần:

- `core`/`api` là **library module**, tạo plain JAR và khai báo public/internal APIs phù hợp.
- `app` là **Spring Boot application module**, có `main()`, `bootJar` hoặc `repackage`.
- Dependency từ app tới core thường trở thành một **nested JAR trong `BOOT-INF/lib`**, không tự bị flatten vào `BOOT-INF/classes`, trừ khi có cấu hình đặc biệt.
- Đừng áp cùng Boot plugin hoặc `repackage` vào mọi library module không có main class.

Maven có thể dùng `<modules>` để aggregate, child module `<parent>` để inherit, và `dependencyManagement` để đồng bộ version. Gradle có `include('core','app')` trong settings rồi `implementation project(':core')` ở app. Dù cách nào, hãy **kiểm tra resolved project dependency** sau khi build.

### 14.1. Exclusion nguy hiểm trong multi-module

Một cấu hình Boot Maven Plugin `<excludeGroupIds>com.example</excludeGroupIds>` có thể vô tình loại luôn các **internal application library modules** thuộc groupId đó. Tương tự trong Gradle, loại toàn bộ internal project dependencies khỏi `bootJar.classpath` có thể khiến app start được nếu chưa đụng class hiếm, nhưng fail khi gọi tính năng cần core.

Hãy dùng tiêu chí cụ thể (artifact/module cần bỏ, vì sao, ai chịu trách nhiệm kiểm chứng) hơn là group/path glob quá rộng.

### 14.2. Fat JAR không đồng nghĩa gom toàn bộ class vào root

Spring Boot executable JAR sử dụng nested dependencies ở `BOOT-INF/lib`. Một shadow/shaded JAR thường gộp nhiều dependency classes thành entries ở root; hai cách có rules về resource merging/classloader khác nhau. Không kết luận mọi class của internal dependency nhất thiết phải nằm ở `BOOT-INF/classes`. Với Boot JAR, một class trong `core.jar` có thể được classloader nạp từ **nested core.jar**.

## 15. Tùy biến mạnh hơn: khi nào nên và không nên dùng?

Một số nhu cầu nâng cao thực tế:

### 15.1. Chỉ đóng artifact theo một feature set

Nếu một feature cần dependency nặng (PDF engine, native bindings, cloud client) và không phải mọi instance đều cần, có thể tách feature thành **module riêng** hoặc distribution/variant có tên rõ. Đừng loại một vài nested JAR bằng pattern không có test; phải chứng minh ứng dụng không còn tham chiếu chúng. Feature toggles runtime không làm JVM tự ngừng cần classes khi feature thực sự được bật.

### 15.2. Tài nguyên license/notice/SBOM

Để đảm bảo compliance, cần kiểm tra license notices, dependency metadata, SBOM và provenance theo chuẩn tổ chức. Không tự loại license file hoặc `META-INF/services` để giảm vài KB: đó có thể là nghĩa vụ pháp lý hoặc điều kiện để `ServiceLoader` hoạt động.

### 15.3. Layered JAR và container cache

`BOOT-INF/layers.idx` có thể được dùng để phân chia dependencies, snapshot dependencies, loader và app resources theo layer. **Đổi layer assignment không đồng nghĩa loại nội dung khỏi JAR**; mục đích chính là phân bố nội dung để tối ưu Docker/buildpacks caching. Nếu muốn giảm footprint, phải thay đúng content selection/runtimes, không chỉ chuyển library sang layer khác.

### 15.4. WAR và `providedRuntime`

Nếu sản phẩm là executable/deployable WAR thay vì JAR:

- Maven có `packaging=war` và scope/container semantics riêng.
- Gradle `war` + Spring Boot `bootWar`; `providedRuntime` phù hợp cho servlet container dependency để chúng vào `WEB-INF/lib-provided` khi cần tương thích external container.
- WAR dùng `WEB-INF/classes`, `WEB-INF/lib` và có thể `WEB-INF/lib-provided`, **không** dùng mọi đường dẫn `BOOT-INF` trong các assertion của bài JAR.

Luôn viết các assertion archive **theo artifact type**; không coi một WAR thiếu `BOOT-INF/classes` là lỗi.

### 15.5. Native executable, OCI image và AOT không phải bản sao Boot JAR

GraalVM native image, Spring Boot `bootBuildImage`/`build-image` và các cơ chế AOT có đầu vào/đầu ra khác. Đừng áp kiểm chứng `jar tf` cho file native executable; thay vào đó dùng binary/image inspection, SBOM, test behavior, runtime dependencies và policy phù hợp. Bài này đánh giá **Spring Boot executable JAR**.

## 16. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách tìm nguồn gốc và khắc phục |
| --- | --- | --- |
| `/marker` fail khi chạy JAR nhưng test pass. | Marker có ở test classpath/dev output nhưng bị loại khỏi packaged main resources hoặc task copy khác. | So `target/classes`/`build/resources/main` với `BOOT-INF/classes`; xem filtering/excludes của build. |
| `BOOT-INF/classes/internal/debug-notes.txt` vẫn có. | Rule exclude không trúng folder, source từ nơi khác/copy task tùy biến. | Kiểm tra path tương đối trong resource root; Gradle `processResources` hoặc Maven `<resources>` áp đúng module chưa. |
| Java class ở `src/test/java` xuất hiện trong artifact. | Source sets/output packaging tùy biến, task copy cả test output. | Khôi phục source set boundary; kiểm tra task input của `jar`/`bootJar` hoặc Jar Plugin. |
| Dependency test (JUnit/Mockito) có trong `BOOT-INF/lib`. | Được khai báo như production dependency hoặc bị đưa vào bootJar classpath bằng tay. | Xem Maven scope/Gradle configuration và archive classpath. |
| Maven dependency `provided` vẫn nằm trong Boot JAR. | Spring Boot Maven Plugin repackage mặc định bao gồm provided. | Đây có thể là hành vi đúng; nếu không cần, cấu hình exclusion có test thay vì đoán theo scope. |
| Maven `optional=true` dependency vẫn được đóng. | Optional ảnh hưởng transitiveness, không phải exclude packaging; Boot có thể include. | Dùng Boot Plugin `excludes` cho artifact cần bỏ; DevTools có loại riêng. |
| Gradle `compileOnly` library thiếu ở runtime. | Không thuộc `runtimeClasspath`. | Nếu thật sự cần khi chạy, chuyển sang `implementation` hoặc `runtimeOnly` đúng hợp đồng. |
| Gradle `developmentOnly` lib không thấy trong `BOOT-INF/lib`. | Boot Gradle Plugin mặc định loại developmentOnly. | Đây thường là đúng; không đưa DevTools vào production nếu không cần. |
| Build pass nhưng `NoClassDefFoundError` khi bật một profile. | Dependency bị loại hoặc chỉ kiểm thử happy path. | Đọc stack trace, dependency graph, artifact `BOOT-INF/lib` và test profile đó. |
| `ClassNotFoundException` cho main class. | Sai `mainClass`/`Start-Class`, không có class tại `BOOT-INF/classes`. | Xem manifest, task repackage/bootJar, source path/compile output. |
| Resource trong classpath không thể dùng `new File(...)`. | Entry ở bên trong archive, không phải file trên filesystem. | Dùng `getResourceAsStream`/Spring `Resource`; extract riêng nếu library buộc cần file vật lý. |
| Đóng nhầm `*-plain.jar`. | Chọn artifact bằng wildcard/tên cũ. | Kiểm tra manifest + `BOOT-INF` và chạy `java -jar` đúng executable archive. |
| `spring-boot:run`/`bootRun` pass nhưng JAR fail. | Development classpath không giống packaged output. | So main output, runtimeClasspath, filtering, plugin excludes và packaged smoke. |
| `application.yml` bị thay placeholder. | Build-time resource filtering đụng Spring runtime placeholder. | Scope filtering theo file/delimiter đúng, kiểm tra content sau packaging. |
| Exclude quá rộng làm thiếu metadata. | Xóa `META-INF/spring/**` hoặc `META-INF/services/**`. | Không tự loại framework resources; xác định usage, restore và integration test. |
| File bí mật không có trong JAR nhưng vẫn lộ. | Đã commit hoặc nằm trong cache/log/artifact cũ. | Thu hồi credential, rà hệ thống phát tán, xử lý theo security process. |
| Lấy BOM là nghĩ tất cả thư viện đã được đóng. | BOM chỉ quản lý versions, không tự tạo dependency. | Kiểm tra actual dependency declarations + resolved runtime graph. |
| Runtime trên máy khác fail. | JDK, profile, external config/secret/port hoặc runtime environment khác. | Lưu version/JAR hash, kiểm chứng trên môi trường gần production. |

### Quy tắc chẩn đoán theo lớp

1. **Source:** file nằm ở main hay test? Được generate từ đâu?
2. **Build output:** compiler và resource processing đã sinh/copied file như kỳ vọng?
3. **Resolved graph:** dependency có đúng scope/configuration và version?
4. **Packaging selection:** Boot plugin/task chọn class/resources/deps gì?
5. **Archive:** `jar tf` và manifest cho thấy gì?
6. **Runtime:** `java -jar` nạp class/resource và thực hiện hành vi thật có đạt?

Đừng sửa manifest hoặc thêm mọi dependency vào `implementation` ngay khi gặp một lỗi runtime; điều đó có thể che giấu lỗi scope mà còn làm artifact phình to.

## 17. Bài thực hành cuối và tiêu chí hoàn thành

### Bài A — chứng minh resource included/excluded

1. Tạo source tree với `PackagingApplication.java`, `PackagingApplicationTest.java`, hai main resource và một test resource như mục 7.
2. Build bằng Maven hoặc Gradle tương ứng mục 8/9, đảm bảo `clean verify` hoặc `clean build` chạy test thật.
3. Kiểm tra `BOOT-INF/classes/public/package-marker.txt` tồn tại.
4. Kiểm tra `BOOT-INF/classes/internal/debug-notes.txt` không tồn tại.
5. Kiểm tra `PackagingApplicationTest.class` và `only-for-tests.txt` không xuất hiện ở bất kỳ entry nào của executable runtime JAR.
6. Chạy binary thật và gọi `GET /marker`; body phải là `included-v1`.

### Bài B — chứng minh dependency selection

1. Chạy Maven `dependency:tree` hoặc Gradle `dependencies --configuration runtimeClasspath`.
2. Liệt kê nested entries dưới `BOOT-INF/lib`.
3. Chọn một dependency runtime hiện diện thật, giải thích vì sao nó tới từ starter hay dependency trực tiếp.
4. Xác nhận JUnit/Mockito test-only không bị đóng; DevTools không bị đóng theo default nếu bài thêm DevTools đúng configuration.
5. Với Maven, giải thích vì sao `provided`/`optional` không đồng nghĩa loại khỏi repackage; với Gradle, giải thích `compileOnly`/`developmentOnly`.
6. Nêu trường hợp cần exclude transitive dependency ở dependency declaration khác với exclude khi repackaging.

### Bài C — thử một thay đổi có kiểm soát

Thay `public/package-marker.txt` thành một tên path khác nhưng **không sửa code Java**, rồi chạy build/test. Dự kiến test `mainClassAndMarkerResourceWork` hoặc packaged `/marker` fail vì resource path trong code không khớp. Khôi phục resource path, build sạch và chứng minh test + executable runtime cùng pass.

Bài này chỉ nhằm minh họa **kiểm chứng tài nguyên**; không khuyến khích tạo lỗi trong branch phát hành. Với dependency exclusions, chỉ thử trên một branch học tập, có test bao phủ tính năng sử dụng dependency đó và rollback rõ ràng.

### Checklist đánh giá

- [ ] Giải thích được ba nguồn nội dung của executable JAR: main output, runtime deps, Spring Boot Loader/manifest.
- [ ] Phân biệt `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources`.
- [ ] Dùng đúng Maven `<build><resources>` hoặc Gradle `processResources` để lọc một resource theo path.
- [ ] Không lẫn resource exclude với Maven/Gradle dependency exclusion.
- [ ] Hiểu BOM quản lý version chứ không tự đưa JAR vào runtime graph.
- [ ] Nêu đúng hành vi Spring Boot Maven `provided`/`optional` và Boot Maven `excludeDevtools`/`excludeDockerCompose`.
- [ ] Nêu đúng Gradle `implementation`, `runtimeOnly`, `compileOnly`, `testImplementation`, `developmentOnly`.
- [ ] Không vô tình loại `META-INF/spring/**`, `META-INF/services/**` hay dependency dùng qua reflection.
- [ ] Không coi `mainClass` là cơ chế tree-shake/exclude lớp.
- [ ] Kiểm tra đúng executable Boot JAR, không dùng `*-plain.jar` hay `*.jar.original`.
- [ ] Có test report, positive và negative archive entry assertions.
- [ ] Có `java -jar` smoke test chứng minh code và resource của artifact hoạt động.
- [ ] Không gửi secrets vào archive; biết rằng exclude không xóa secrets đã có trong Git history.
- [ ] Biết viết assertions riêng cho JAR/WAR/container/native artifact.

**Tiêu chí đạt bài:** người học trình bày được quyết định **chọn class/resource/dependency** ở đúng tầng build, tạo một executable JAR có kiểm soát, chứng minh bằng entry list rằng marker được **đóng vào**, debug/test-only files **bị loại**, giải thích vì sao dependency runtime có mặt hoặc không có mặt, và chạy được **chính binary đã được đóng**. Mọi kết luận phải kèm bằng chứng từ build/report/archive/runtime thật, không chỉ đoán dựa trên `pom.xml` hay `build.gradle`.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)
- [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Resources Plugin — Filtering and Inclusion/Exclusion](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html)
- [Gradle — Building Java and JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)

**Ghi nhớ:** **source set + resource processing + resolved runtime dependencies + packaging plugin selection** cùng quyết định thành phần cuối của sản phẩm. Tránh dùng exclude hậu đóng gói làm cách sửa nhanh; thiết kế đúng scope/module và kiểm tra **file JAR thực tế** là cách bền vững hơn.