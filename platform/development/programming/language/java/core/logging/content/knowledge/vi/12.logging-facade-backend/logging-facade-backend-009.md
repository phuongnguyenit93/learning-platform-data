# Xung đột dependency trong Java Logging: SLF4J, Logback, Log4j2 và JUL

Một ứng dụng Java có thể chạy bình thường trên IDE nhưng khi đóng gói hoặc triển khai lại xuất hiện cảnh báo `multiple SLF4J providers`, mất log, in trùng log, không đọc `logback.xml`, hoặc gặp `NoClassDefFoundError`. Nguyên nhân thường nằm ở **dependency graph và runtime classpath**: nhiều thư viện cùng mang một logging implementation, phiên bản API không tương thích với provider, bridge chuyển log sai hướng hoặc cấu hình được viết cho backend không thực sự hoạt động.

**Xung đột dependency trong logging** không chỉ là “có hai phiên bản của một JAR”. Nó có thể là **nhiều provider cạnh tranh**, **thiếu provider**, **API và implementation lệch thế hệ**, **vòng lặp bridge** hoặc **hai pipeline độc lập cùng ghi**. Để sửa đúng, phải nhận diện đường đi của sự kiện log và chọn **một đích logging chính** theo thiết kế, thay vì thêm JAR cho đến khi cảnh báo biến mất.

Trong bài, `SLF4J` là một facade thường dùng, `Logback` và `Log4j2 Core` là backend, còn `java.util.logging` (**JUL**) là hệ thống logging trong JDK. Phiên bản và thông báo lúc chạy có thể thay đổi giữa các release; luôn xác minh bằng dependency tree và runtime thực tế.

## 1. Nắm rõ ba lớp: API, backend, bridge

```text
Code ứng dụng hoặc thư viện
  |
  +-- SLF4J API ------------> SLF4J provider ------> Backend
  |                                |                     |
  |                                +-- Logback Classic   +--> Console/File
  |                                +-- Log4j2 provider   +--> Console/File
  |                                +-- slf4j-simple      +--> Simple output
  |
  +-- Log4j2 API -----------> Log4j2 Core hoặc adapter
  |
  +-- JUL API --------------> JUL Handler hoặc bridge
```

**API/facade** là nơi code gọi `info/debug/error`. **Provider/backend** là nơi quyết định cấu hình và xuất bản ghi. **Bridge/adapter** chuyển lời gọi từ API này sang API khác để thống nhất pipeline. Một bridge thường có **chiều cụ thể**; lắp cả hai chiều tạo vòng lặp.

| Artifact | Vai trò thường gặp | Ghi nhớ |
| --- | --- | --- |
| `org.slf4j:slf4j-api` | Facade API SLF4J. | Bản thân nó không ghi file/console thay cho provider. |
| `ch.qos.logback:logback-classic` | SLF4J provider với backend Logback. | Kéo theo `logback-core` và các dependency cần thiết. |
| `org.slf4j:slf4j-simple` | Provider ghi log đơn giản. | Dùng tốt cho bài nhỏ, nhưng cạnh tranh với Logback nếu cùng có mặt. |
| `org.slf4j:slf4j-nop` | Provider cố tình bỏ log. | Không phù hợp nếu ứng dụng phải có log vận hành. |
| `org.apache.logging.log4j:log4j-api` | API của Log4j2. | Không đồng nghĩa với Log4j2 Core. |
| `org.apache.logging.log4j:log4j-core` | Backend và appender của Log4j2. | Cần phiên bản phù hợp với `log4j-api`. |
| `org.apache.logging.log4j:log4j-slf4j2-impl` | Hướng **SLF4J 2.x → Log4j2**. | Chọn khi Log4j2 là backend cho SLF4J 2.x. |
| `org.apache.logging.log4j:log4j-slf4j-impl` | Hướng **SLF4J 1.7.x → Log4j2** ở nhánh tương thích. | Không dùng thay cho provider SLF4J 2.x. |
| `org.apache.logging.log4j:log4j-to-slf4j` | Hướng **Log4j2 API → SLF4J**. | Không lắp cùng adapter SLF4J → Log4j2. |
| `org.slf4j:jul-to-slf4j` | Bridge **JUL → SLF4J**. | Cần cài handler/thiết lập bridge tương ứng, không chỉ thêm dependency. |
| `org.slf4j:slf4j-jdk14` | Provider **SLF4J → JUL**. | Không dùng đồng thời với bridge JUL → SLF4J nếu tạo vòng lặp. |

Mục đích cuối cùng có thể là Logback, Log4j2 hoặc JUL. **Đừng chọn backend chỉ bằng cách nhìn import của một class**: một dependency bên ngoài có thể dùng Log4j API trong khi ứng dụng dùng SLF4J và dùng bridge một chiều để kết hợp.

## 2. Lỗi phổ biến nhất: nhiều SLF4J provider trên classpath

Giả sử dự án vừa thêm `logback-classic` vừa thêm `slf4j-simple`. Cả hai cung cấp implementation cho facade SLF4J. Khi khởi động, SLF4J có thể phát cảnh báo rằng có **nhiều provider** và chọn một provider đang thấy theo cơ chế khám phá runtime. **Không dựa vào thứ tự ngẫu nhiên của classpath để quyết định backend**.

Một dependency tree sai điển hình:

```text
application
+-- ch.qos.logback:logback-classic
|   +-- ch.qos.logback:logback-core
|   \-- org.slf4j:slf4j-api
\-- org.slf4j:slf4j-simple          <-- thêm provider cạnh tranh
```

Kết quả có thể là cấu hình `logback.xml` không có tác dụng vì provider khác được chọn; định dạng log bất ngờ, mức log khác và thông báo runtime khó hiểu.

### Cách sửa

1. **Chọn backend chủ đạo** của ứng dụng, ví dụ Logback.
2. **Giữ đúng một provider SLF4J phù hợp** ở runtime, ví dụ `logback-classic`.
3. Loại `slf4j-simple`, `slf4j-nop`, `slf4j-reload4j` hoặc provider Log4j2 khác nếu chúng không nằm trong thiết kế.
4. Kiểm tra cả **dependency trực tiếp lẫn transitive**, đặc biệt artifact do starter/framework và SDK kéo vào.
5. Chạy lại trên **classpath cuối cùng sau đóng gói**, không chỉ classpath unit test.

**Phân biệt API và provider:** nhiều dependency cùng tham chiếu `slf4j-api` không có nghĩa có nhiều provider. Maven/Gradle thường giải quyết về một phiên bản artifact trên classpath; vấn đề thật nằm ở provider hoặc phiên bản được chọn không phù hợp.

## 3. SLF4J 1.7 và 2.x: không trộn binding với provider

Hai thế hệ SLF4J dùng cơ chế khám phá implementation khác nhau:

| Thế hệ API | Cơ chế tìm backend | Artifact cần phù hợp |
| --- | --- | --- |
| SLF4J 1.7.x trở về trước | Tìm **`StaticLoggerBinder`** (binding). | Binding nhắm đến SLF4J 1.7.x. |
| SLF4J 2.0.x | Dùng `ServiceLoader` để tìm **`SLF4JServiceProvider`**. | Provider tương thích SLF4J 2.0.x. |

Vì vậy, nếu runtime dùng `slf4j-api:2.0.x` nhưng chỉ có binding cũ dành cho 1.7, SLF4J 2 có thể **bỏ qua binding cũ**, báo thiếu provider và dùng implementation không ghi log (`NOP`) cho các lời gọi SLF4J. Ngược lại, API 1.7 không tự hiểu cơ chế provider của API 2.x.

Các trường hợp cần phân biệt:

- **API 2.0.x + provider 2.0.x tương thích:** kiến trúc hợp lệ, còn phải đảm bảo không có provider cạnh tranh.
- **API 2.0.x + chỉ binding 1.7.x:** không giải quyết được provider SLF4J 2.x.
- **API 1.7.x + chỉ provider 2.0.x:** không đáp ứng cơ chế binding của SLF4J 1.7.
- **API 2.0.x + một số thư viện compile với SLF4J API cũ:** không tự động xem là lỗi; API phía client được duy trì tương thích rộng, nhưng provider/runtime vẫn phải phù hợp.
- **Nhiều phiên bản của cùng `slf4j-api` được khai báo:** công cụ build sẽ chọn một theo quy tắc resolution; phải xem **phiên bản hiệu lực lúc chạy** thay vì đoán từ `pom.xml`.

Thông báo có thể chứa các ý như “No SLF4J providers were found”, “Class path contains multiple SLF4J providers”, hoặc cảnh báo về binding nhắm vào bản 1.7. **Câu chữ chính xác có thể khác theo phiên bản**; dùng nội dung cảnh báo làm manh mối, rồi đối chiếu dependency tree.

### Nguyên tắc về phiên bản

Các artifact `org.slf4j` như `slf4j-api` và `slf4j-simple` cần tương thích theo nhánh phiên bản; với SLF4J 2.0.x, provider phải nhắm đến 2.0.x, không phải binding 1.7.x. Provider Logback và Log4j2 có hệ thống phiên bản riêng, nên **không so sánh số 1.5 của Logback với số 2.0 của SLF4J theo kiểu phải bằng nhau**; hãy xem ma trận tương thích của backend.

Trong dự án nhiều module, áp dụng dependency management hoặc version catalog/BOM khi phù hợp để giữ phiên bản thống nhất. Không hạ `slf4j-api` chỉ để “giấu” một cảnh báo nếu phần còn lại của ứng dụng dùng tính năng của SLF4J 2.x.

## 4. Vòng lặp nguy hiểm: bridge hai chiều

Một lỗi khác nghiêm trọng hơn cảnh báo nhiều provider là tạo **vòng chuyển log**:

```text
SLF4J API
  | log4j-slf4j2-impl
  v
Log4j2 API
  | log4j-to-slf4j
  v
SLF4J API
  | ...
  +----> vòng lặp
```

**Không triển khai đồng thời** `log4j-slf4j2-impl` với `log4j-to-slf4j`. Tương tự, `log4j-slf4j-impl` không được kết hợp với bridge chiều ngược này. Log4j2 có thể phát hiện cấu hình không hợp lệ và báo lỗi thay vì thực sự lặp vô hạn; dù biểu hiện cụ thể thế nào, thiết kế vòng hai chiều vẫn phải bị loại.

### Chọn một trong hai đích

| Backend mong muốn | Hướng chuyển hợp lý | Điều cần loại |
| --- | --- | --- |
| **Logback** xử lý log gọi bằng Log4j2 API | `Log4j2 API → log4j-to-slf4j → SLF4J → Logback` | Không thêm `log4j-slf4j2-impl`. |
| **Log4j2 Core** xử lý log gọi qua SLF4J 2.x | `SLF4J → log4j-slf4j2-impl → Log4j2 Core` | Không thêm `log4j-to-slf4j`; không thêm Logback provider cạnh tranh. |
| **JUL** là backend | `SLF4J → slf4j-jdk14 → JUL` | Không đồng thời gắn JUL → SLF4J tạo vòng lặp. |
| **Logback** là backend và có thư viện gọi JUL | `JUL → jul-to-slf4j → SLF4J → Logback` | Không thêm `slf4j-jdk14` cùng chiều ngược; cần kích hoạt bridge JUL thích hợp. |

Bridge không phải plugin “nâng cấp log” tổng quát. Nó chuyển API theo **chiều xác định** và có thể thay đổi chi phí format, level mapping hoặc thông tin ngữ cảnh. Tích hợp JUL bằng `jul-to-slf4j` cần cài đặt `SLF4JBridgeHandler` hay tích hợp tương đương; **dependency đơn thuần không tự thay handler của JUL**.

Các cặp bridge khác cũng cần xem chiều: `jcl-over-slf4j` hướng Commons Logging → SLF4J, còn `slf4j-jcl` hướng SLF4J → Commons Logging. Không đặt đồng thời hai chiều theo cách biến một lời gọi thành vòng lặp.

## 5. Phân biệt xung đột backend với log trùng do cấu hình

Không phải mọi lần xuất hai dòng giống nhau đều là “multiple provider”.

**Kịch bản A – Hai provider cạnh tranh:** Logback và `slf4j-simple` cùng nằm ở runtime. SLF4J có thể cảnh báo chọn provider. Cách xử lý là sửa dependencies.

**Kịch bản B – Chỉ một Logback provider nhưng log bị in hai lần:** cùng một appender được gắn ở logger con và root trong khi `additivity=true`. Cách xử lý là sửa cấu hình appender/additivity, không cần đổi backend.

**Kịch bản C – Thư viện gọi JUL, ứng dụng dùng Logback:** event của JUL vẫn có thể ra `ConsoleHandler` và event SLF4J ra Logback, tạo hai luồng output trông khác nhau. Cần quyết định có muốn dùng bridge JUL → SLF4J hay giữ pipeline JUL độc lập; chỉ thêm dependency Logback không chuyển mọi lời gọi JUL sang nó.

**Kịch bản D – Có cả Log4j API và SLF4J API ở runtime:** điều này không tự là xung đột. Có thể hợp lệ nếu chỉ một bridge một chiều đưa hai API về backend thống nhất. Cần xem provider và adapter nào đang hoạt động.

Tóm lại, **đếm số JAR có chữ “logging” không đủ để kết luận lỗi**. Phải kiểm tra vai trò của từng artifact và đường đi của event từ API đến sink.

## 6. Những triệu chứng cần nhận diện

| Triệu chứng lúc chạy/build | Nguyên nhân đáng nghi | Điều nên kiểm tra |
| --- | --- | --- |
| Cảnh báo **multiple SLF4J providers** | Có hai hoặc nhiều provider SLF4J 2.x. | `logback-classic`, `slf4j-simple`, `slf4j-reload4j`, `log4j-slf4j2-impl`. |
| Cảnh báo **multiple SLF4J bindings** ở ứng dụng cũ | Có nhiều binding `StaticLoggerBinder` thuộc hệ 1.7. | Phiên bản `slf4j-api`, các binding cũ. |
| Cảnh báo **no SLF4J providers** | Thiếu provider, chỉ có API hoặc có binding cũ bị bỏ qua. | Runtime artifacts, scope, việc đóng gói service descriptor. |
| Log mất hoặc không xuất ra dù có lời gọi | NOP provider, level/filter sai hoặc cấu hình backend khác. | Provider thực tế, config loaded, effective level. |
| `logback.xml` không có tác dụng | Runtime chọn backend khác hoặc framework nạp cấu hình khác. | Provider + file config trên classpath. |
| `log4j2.xml` không có tác dụng | Log4j Core không được chọn, thiếu artifact hoặc config không được nạp. | API/Core, adapter, provider, resource. |
| `NoClassDefFoundError` / `NoSuchMethodError` | Runtime classpath lệch so với lúc compile, API/implementation sai phiên bản, JAR thiếu. | Class đến từ JAR nào, dependency graph, packaging. |
| `ClassCastException` khi ép kiểu backend | Code giả định SLF4J logger factory thuộc Logback nhưng runtime là backend khác. | Tách facade khỏi backend-specific API. |
| Lỗi về bridge/loop giữa Log4j2 và SLF4J | Đưa cả hai adapter ngược chiều vào. | `log4j-slf4j2-impl` và `log4j-to-slf4j`. |
| Một event xuất nhiều lần | Appender additivity, nhiều pipeline/handler hoặc cấu hình thu thập trùng. | Logger/appender/collector, không chỉ dependencies. |
| Chạy được trong IDE nhưng lỗi khi đóng gói | Test scope, provided/runtime scope, assembly/shading hoặc Spring Boot repackaging khác. | Classpath cuối cùng của JAR/container. |

**Chẩn đoán từ lỗi thực tế, không đoán theo thông báo duy nhất.** `NoClassDefFoundError` cũng có thể xuất hiện vì thư viện khác ngoài logging; cần đọc đầy đủ class name và stack trace.

## 7. Kiểm tra dependency tree bằng Maven

Giả sử chạy dự án Maven trong thư mục chứa `pom.xml`:

```bash
mvn dependency:tree
```

Tìm các tọa độ bắt đầu bằng:

```text
org.slf4j:slf4j-api
org.slf4j:slf4j-simple
org.slf4j:slf4j-nop
org.slf4j:slf4j-jdk14
ch.qos.logback:logback-classic
ch.qos.logback:logback-core
org.apache.logging.log4j:log4j-api
org.apache.logging.log4j:log4j-core
org.apache.logging.log4j:log4j-slf4j2-impl
org.apache.logging.log4j:log4j-slf4j-impl
org.apache.logging.log4j:log4j-to-slf4j
org.slf4j:jul-to-slf4j
```

Ở cây phụ thuộc, hãy kiểm tra **đường dẫn bắc cầu nào đã kéo** một provider hoặc bridge vào. Maven sẽ giải quyết xung đột phiên bản theo cơ chế dependency mediation (thường xét đường đi gần hơn và thứ tự khai báo khi độ sâu bằng nhau), nên không thể chỉ đọc phiên bản trong dependency con rồi coi đó là phiên bản runtime.

### Đọc dependency từ góc độ runtime

Phân biệt:

- `compile`: dependency thường có trên compile và runtime classpath.
- `runtime`: thường cần ở runtime nhưng không nhất thiết phải có để compile mã nghiệp vụ.
- `test`: chỉ cho test classpath; unit test chạy được không chứng minh ứng dụng được đóng gói đúng.
- `provided`: phụ thuộc vào runtime/container cung cấp thư viện; nếu giả định sai, JAR triển khai sẽ thiếu lớp cần thiết.
- `optional` và dependency exclusions: có thể ảnh hưởng những artifact transitive nào tới dự án tiêu thụ.

Có thể xem `mvn help:effective-pom` để biết phiên bản do parent/BOM/dependencyManagement áp dụng. Kiểm tra cả `mvn dependency:tree` sau khi đổi cấu hình, không chỉ đọc vài dòng `pom.xml`. Khi chạy fat JAR, container hoặc launcher có classpath khác với Maven, cần kiểm tra runtime cuối cùng.

### Sửa bằng exclusions đúng vị trí

Nếu một dependency transitive kéo vào provider không mong muốn, hãy loại **artifact provider ở cạnh mang nó vào** và giữ API phù hợp. Cú pháp Maven:

```xml
<!-- Ví dụ bên trong một dự án Spring Boot đã quản lý versions. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đây là **đoạn cấu hình minh họa trong một POM Spring Boot**, không phải `pom.xml` chạy độc lập. Cách loại starter logging thường được dùng khi chuyển một ứng dụng Spring Boot sang starter backend khác **và đã bổ sung backend thay thế phù hợp**. Không sao chép exclusion này vào dự án chỉ dùng Logback mặc định, vì có thể làm mất provider.

**Không loại `slf4j-api` chỉ vì thấy nhiều dòng tham chiếu API**. Lỗi thường ở provider/bridge, không phải bản thân việc nhiều thư viện dùng facade. Exclusion Maven có hiệu lực theo nhánh dependency, nên nếu cùng artifact được kéo từ nhánh khác, phải kiểm tra cây cuối cùng.

## 8. Kiểm tra runtimeClasspath bằng Gradle

Với dự án Gradle, các lệnh điển hình:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency logback-classic --configuration runtimeClasspath
```

Với Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat` nếu dự án có Gradle Wrapper cho Windows. Các lệnh là **hướng dẫn cho dự án Gradle đã có build script**, không phải phần của Maven demo bên dưới.

`dependencyInsight` giúp biết vì sao một phiên bản được chọn; khác Maven, Gradle thường có cơ chế giải quyết xung đột mặc định ưu tiên phiên bản cao hơn, trừ khi có constraint/platform/forced rule hoặc cấu hình riêng. Vì vậy hai dự án cùng khai báo dependency có thể có **kết quả runtime khác nhau** nếu công cụ build hoặc quy tắc version khác nhau.

Ví dụ loại transitive provider trong Gradle Kotlin DSL, khi dependency cha thực sự kéo vào artifact đó:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") {
        exclude(
            group = "org.springframework.boot",
            module = "spring-boot-starter-logging"
        )
    }
    // Cần một dependency backend thay thế phù hợp do dự án quản lý.
}
```

Đoạn trên là **minh họa** trong dự án có version management cho Spring Boot; thiếu version/BOM/build plugin thì không thể chép vào project rỗng và tự chạy. Tránh dùng `configurations.all { exclude(...) }` toàn cục khi chưa hiểu hệ quả: dễ loại cả dependency mà tính năng khác còn cần.

## 9. Thực hành Java 17: một SLF4J API, một Logback provider

Bài thực hành dưới đây thể hiện cấu hình **không xung đột**. Mã chỉ dùng SLF4J API, runtime có **một provider là Logback Classic**. Chương trình in ra tên implementation của `ILoggerFactory` để chứng minh provider được chọn, đồng thời ghi event với định dạng cố định.

Ví dụ dùng **JDK 17 + Maven**. Các phiên bản `slf4j-api 2.0.17` và `logback-classic 1.5.18` là **phiên bản cố định cho bài học**, không có nghĩa đây là bản mới nhất. Dự án thật cần cập nhật phiên bản còn được hỗ trợ và đã vá bảo mật, đồng thời kiểm tra ma trận tương thích.

### 9.1. Cấu trúc dự án

```text
logging-dependency-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LoggingDependencyDemo.java
        └── resources/
            └── logback.xml
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logging-dependency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.LoggingDependencyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` kéo theo `logback-core`; có khai báo `slf4j-api` trực tiếp để bài thể hiện rõ API được sử dụng. Trong ứng dụng quản lý dependency theo BOM, không nhất thiết phải đặt version riêng ở mỗi dependency, nhưng **runtime chỉ nên có đúng một provider SLF4J** nếu muốn hành vi nhất quán.

### 9.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Pattern không có timestamp, thread, MDC hay màu ANSI để output ổn định. Trong production cần thêm các trường phục vụ điều tra và kiểm soát dữ liệu nhạy cảm.

### 9.4. src/main/java/demo/LoggingDependencyDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingDependencyDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingDependencyDemo.class);

    public static void main(String[] args) {
        System.out.println(
                "factory=" +
                LoggerFactory.getILoggerFactory().getClass().getName()
        );

        LOG.debug("event=diagnostic.hidden");
        LOG.info("event=service.ready requestId={}", "req-17");
        LOG.warn("event=dependency.check outcome={}", "clean");
    }
}
```

### 9.5. Biên dịch và chạy

Mở terminal tại thư mục chứa `pom.xml`; Maven có thể cần mạng để tải dependency lần đầu:

```bash
mvn -q compile exec:java
```

**Đầu ra chuẩn từ chương trình**, không tính output riêng do Maven hay môi trường có thể in thêm:

```text
factory=ch.qos.logback.classic.LoggerContext
INFO | demo.LoggingDependencyDemo | event=service.ready requestId=req-17
WARN | demo.LoggingDependencyDemo | event=dependency.check outcome=clean
```

Giải thích:

1. `LoggerFactory.getILoggerFactory()` trả về implementation của provider Logback Classic: `ch.qos.logback.classic.LoggerContext`.
2. `LOG` thuộc namespace `demo.LoggingDependencyDemo`, kế thừa mức INFO từ root.
3. DEBUG bị loại tại ngưỡng INFO; hai event INFO/WARN được appender STDOUT chấp nhận.
4. `{}` là cú pháp tham số của SLF4J, khác `{0}` của JUL; Logback định dạng message qua facade.
5. File `logback.xml` ở `src/main/resources` được đưa vào classpath khi chạy Maven; chỉ có một provider thì cấu hình backend được chọn nhất quán.

### 9.6. Mô phỏng sai: thêm provider thứ hai

Nếu **thêm** dependency sau vào `pom.xml` của demo (chỉ thực hiện trong môi trường thử nghiệm, không dùng cấu hình này để triển khai):

```xml
<!-- CHỈ ĐỂ MINH HỌA XUNG ĐỘT PROVIDER, KHÔNG PHẢI CẤU HÌNH ĐÚNG. -->
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.17</version>
</dependency>
```

Runtime lúc này có `logback-classic` và `slf4j-simple`. SLF4J có thể báo **multiple providers**, và việc backend nào được chọn không nên bị dựa vào thứ tự classpath. Khi hoàn tất kiểm tra, **bỏ dependency `slf4j-simple`** để quay về một provider. Không ép dùng `slf4j.provider` như một cách che giấu dependency graph chưa được dọn dẹp.

## 10. Runtime classpath, fat JAR và framework

### Một project có nhiều module

Dự án thư viện nên **phụ thuộc API**, thường không ép người sử dụng dùng một backend cụ thể. Nếu một thư viện tự kéo `slf4j-simple` hoặc Logback vào runtime của sản phẩm, ứng dụng chính có thể nhận thêm provider không mong muốn. Với thư viện dùng SLF4J, thường khai báo `slf4j-api` theo scope thích hợp và để **ứng dụng cuối cùng** quyết định backend.

Tuy nhiên, một số framework application starter cố tình mang backend mặc định vì đó là ứng dụng, không phải thư viện độc lập. Khi đổi backend, dùng cơ chế exclusion/starter được framework hỗ trợ, không xóa mọi dependency có chữ “logging”.

### Spring Boot

Trong nhiều cấu hình Spring Boot truyền thống, `spring-boot-starter-logging` cung cấp Logback mặc định. Khi muốn dùng Log4j2 làm backend, ứng dụng thường chuyển sang `spring-boot-starter-log4j2` và loại starter logging mặc định ở các nhánh cần thiết. Phiên bản Boot cụ thể có thể đổi chi tiết dependency; **kiểm tra tài liệu và dependency tree của phiên bản đang sử dụng**.

Không để cả Logback provider và Log4j2 SLF4J provider cùng chiếm runtime chỉ vì hai starter được kéo từ những module khác nhau. Ngoài ra, `logback-spring.xml` là cơ chế cấu hình trong hệ sinh thái Spring Boot; ứng dụng Java thuần không tự hiểu tất cả extension này.

### Fat JAR, shaded JAR và class loader

Một dependency tree “sạch” ở Maven không bảo đảm artifact triển khai sạch:

- Quá trình shading có thể **gộp/loại nhầm** tệp `META-INF/services/org.slf4j.spi.SLF4JServiceProvider`, khiến provider không được tìm thấy.
- Assembly hoặc đóng gói thủ công có thể chứa **nhiều phiên bản JAR** hoặc provider không xuất hiện trong cây phụ thuộc build dự kiến.
- App server có thể cung cấp logging library ở class loader cha, gây khác biệt giữa local và runtime.
- `provided`/`test` scope có thể khiến runtime cuối cùng thiếu implementation.
- Plugin/agent hoặc SDK có thể dùng logging độc lập; phải hiểu class loader isolation trước khi kết luận “nhiều JAR” có nghĩa xung đột.

Hãy kiểm tra **classpath và nội dung JAR của đúng artifact đã triển khai**, không chỉ file khai báo dependency. Nếu dùng container, kiểm tra cả image và lớp library do platform cung cấp.

## 11. Quy trình xử lý một sự cố logging dependency

Làm theo thứ tự từ nguyên nhân đến giải pháp:

1. **Thu thập triệu chứng:** lưu trọn cảnh báo SLF4J/Log4j, exception stack trace, môi trường và cách chạy. Không chỉ chụp một dòng cuối.
2. **Xác định API của mã phát log:** SLF4J, Log4j2 API, JUL, Apache Commons Logging hay API khác.
3. **Chọn một backend chủ đạo:** Logback, Log4j2 Core hoặc JUL. Vẽ một đường đi một chiều cho mỗi API khác.
4. **Liệt kê provider và bridge thực tế:** xem dependency tree và runtime JAR; phân biệt API với implementation.
5. **Kiểm tra phiên bản:** SLF4J 1.7 binding hay 2.0 provider, Log4j API/Core, Logback compatibility và Java baseline.
6. **Tìm nhánh transitive gây xung đột:** Maven/Gradle dependency report hoặc dependency insight; xác nhận artifact nào kéo provider thừa.
7. **Dùng exclusion có mục tiêu:** bỏ provider/adapter không mong muốn tại nhánh đưa vào, giữ API cần thiết. Dùng BOM/dependencyManagement để thống nhất version.
8. **Loại bridge ngược chiều:** đặc biệt `log4j-slf4j2-impl` với `log4j-to-slf4j`, `slf4j-jdk14` với `jul-to-slf4j` khi chúng tạo vòng.
9. **Kiểm tra cấu hình đang nạp:** `logback.xml`, `log4j2.xml`, `logging.properties` và cơ chế đặc thù framework; đừng đổi file config khi backend còn sai.
10. **Chạy lại trên runtime cuối:** unit test, integration test, fat JAR/container; kiểm tra startup, INFO, DEBUG và exception có cause/stack trace.
11. **Xác nhận không bị log trùng/khuyết:** theo dõi stdout/file/collector và appender additivity, không chỉ xem cảnh báo đã biến mất.
12. **Khóa chất lượng dependency:** thêm kiểm tra CI/dependency management phù hợp để không tái xuất hiện provider/bridge xung đột sau update.

### Ví dụ quyết định trước–sau

**Trước:** project dùng Logback, một thư viện mới kéo `slf4j-simple`; startup cảnh báo multiple providers, file `logback.xml` bị bỏ qua trong một số môi trường.

**Sau:** giữ `slf4j-api` và `logback-classic`, loại `slf4j-simple` theo nhánh transitive, đọc lại dependency tree, chạy trên JAR cuối và xác nhận Logback factory được chọn; kiểm tra các level/log output. Không đổi toàn bộ code sang JUL để né một xung đột classpath.

## 12. Những cách sửa sai và vì sao nguy hiểm

| Cách sửa vội | Hệ quả | Cách phù hợp |
| --- | --- | --- |
| Thêm `slf4j-simple` khi đã có Logback | Có hai provider, runtime selection không nhất quán. | Giữ đúng provider ứng dụng chủ động chọn. |
| Nâng `slf4j-api` lên 2.x nhưng giữ binding 1.7 | Thiếu provider tương thích; có thể dùng NOP. | Nâng/chọn provider 2.x tương ứng và kiểm tra release notes. |
| Lắp `log4j-to-slf4j` cùng `log4j-slf4j2-impl` | Vòng lặp bridge. | Chọn một chiều API → backend. |
| Xóa toàn bộ dependency SLF4J | Code/library còn gọi SLF4J sẽ thiếu class, thay vì hết xung đột. | Giữ facade API, sửa provider/bridge. |
| Thay đổi level thành ERROR để ép log xuất hiện | Che triệu chứng, mất INFO/DEBUG phục vụ điều tra. | Xác định backend và config đang hoạt động. |
| Để SLF4J NOP cho production nhằm tránh cảnh báo | Mất log vận hành quan trọng. | Cấu hình một provider thực phù hợp yêu cầu. |
| Không kiểm tra runtime artifact | Local đúng, CI/container lại lỗi. | Kiểm tra fat JAR/image/classpath và startup thật. |
| Loại provider bằng exclusion toàn cục không hiểu nhánh | Có thể làm một ứng dụng khác trong multi-module thiếu backend. | Exclude tại cạnh transitive cụ thể, kiểm tra từng module. |
| Chỉ đổi `logback.xml` khi runtime dùng Log4j2 | Cấu hình tiếp tục không có tác dụng. | Chọn backend rồi dùng config đúng backend. |
| Coi log in trùng = chắc chắn có nhiều provider | Bỏ sót additivity hoặc thu thập lặp. | Kiểm tra sink, handler/appender và collector. |
| Bỏ qua cảnh báo vì “ứng dụng vẫn chạy” | Có thể đang dùng NOP hoặc backend bất ngờ. | Xác minh logger factory và output sau triển khai. |

## 13. Checklist trước khi merge dependency logging

- [ ] Mỗi API logging được định tuyến đến **backend đã chọn** bằng đường đi rõ ràng, không có vòng hai chiều.
- [ ] Trên runtime có **một provider SLF4J 2.x tương thích** (nếu dùng SLF4J 2.x), hoặc binding tương ứng cho hệ cũ.
- [ ] Phiên bản `slf4j-api`, backend, bridge và Java baseline tương thích; không lẫn binding 1.7 với provider 2.x.
- [ ] Maven/Gradle dependency graph không còn provider thừa do transitive dependency, starter hoặc test scope.
- [ ] Logback/JUL/Log4j2 đang đọc đúng file cấu hình; không còn cảnh báo provider/binding không mong muốn.
- [ ] Runtime cuối cùng (fat JAR, container, app server) chứa đúng implementation và service descriptor.
- [ ] Các event DEBUG/INFO/WARN/ERROR có level phù hợp, không bị mất hoặc in trùng ngoài dự kiến.
- [ ] Exception được truyền dưới dạng `Throwable`, stack trace/cause không bị pipeline bỏ ngoài ý muốn.
- [ ] Log không chứa token, mật khẩu, cookie phiên, payload cá nhân không cần thiết; có chính sách retention và phân quyền.
- [ ] CI có bước kiểm tra phiên bản/cây dependency và thử startup để phát hiện xung đột tái xuất hiện.

## 14. Tài liệu chính thức nên tra cứu khi nâng cấp

- [SLF4J FAQ – provider, phiên bản và tương thích](https://slf4j.org/faq.html).
- [SLF4J Manual – mô hình facade/provider](https://slf4j.org/manual.html).
- [SLF4J Error Codes – cảnh báo thiếu hoặc nhiều provider](https://www.slf4j.org/codes.html).
- [Apache Log4j 2 Components – bridge hai chiều và các artifact](https://logging.apache.org/log4j/2.x/components.html).

**Kết luận:** Khi thấy xung đột logging, đừng bắt đầu bằng việc sửa message hay tăng level. Hãy **vẽ tuyến API → provider/bridge → backend → appender/handler**, kiểm tra dependency tree và runtime classpath, giữ đúng một provider cho SLF4J, loại adapter ngược chiều và xác nhận đầu ra thực tế. Cách đó giúp tránh mất log, vòng lặp, log trùng và sự cố khó tái hiện khi triển khai.