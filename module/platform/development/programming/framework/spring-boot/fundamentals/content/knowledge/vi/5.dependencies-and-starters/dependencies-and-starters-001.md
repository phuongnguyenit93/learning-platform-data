# Starter gom những dependency nào và vì sao cần starter trong Spring Boot?

Khi tạo một dự án Spring Boot từ Spring Initializr, bạn thường chỉ chọn một vài mục như **Spring Web**, **Spring Data JPA**, **Validation** hoặc **Spring Security**. Sau khi tạo dự án, file `pom.xml` hay `build.gradle` lại chỉ có một số dependency với tên `spring-boot-starter-*`. Vì sao thêm một dependency mà ứng dụng có thể sử dụng nhiều thư viện khác nhau?

Câu trả lời nằm ở **starter** và **transitive dependency** (phụ thuộc bắc cầu). Starter là một tập hợp dependency được Spring Boot lựa chọn cho một mục đích sử dụng phổ biến. Nó giúp lập trình viên bắt đầu bằng một nhóm thư viện tương thích, thay vì tự tìm và ghép từng thư viện.

Bài học tập trung vào ba vấn đề: **starter thực tế kéo theo những dependency nào**, **vì sao có lợi khi dùng starter**, và **cách kiểm tra hoặc điều chỉnh các dependency đó trong dự án đầu tiên**.

## 1. Trước hết, dependency là gì?

Trong Java, một ứng dụng thường cần chức năng từ thư viện bên ngoài, chẳng hạn xử lý HTTP, chuyển đổi JSON, kết nối database hoặc viết unit test. Những thư viện đó là **dependency** của ứng dụng.

Với Maven, bạn có thể khai báo dependency trong `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Với Gradle Groovy DSL, khai báo tương đương trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Trong Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Các đoạn trên giả định dự án đã được cấu hình quản lý phiên bản dependency của Spring Boot, ví dụ dùng parent/BOM ở Maven hoặc import BOM trong Gradle. Cách Spring Boot xác định phiên bản được giải thích ở mục 4.

Build tool đọc khai báo, tìm artifact và tải các thư viện cần thiết từ repository (chẳng hạn Maven Central) hoặc cache cục bộ. Những thư viện được tải được đưa vào **classpath** ở các giai đoạn thích hợp như compile, runtime hoặc test.

### 1.1. Direct dependency và transitive dependency

- **Direct dependency**: dependency bạn trực tiếp khai báo trong file build. Ví dụ `spring-boot-starter-web`.
- **Transitive dependency**: dependency mà một dependency khác yêu cầu; build tool tự giải quyết tiếp. Ví dụ starter Web có thể kéo theo module Spring MVC và thư viện xử lý JSON.

Mô hình đơn giản:

```text
Ứng dụng của bạn
    └── spring-boot-starter-web                 ← direct dependency
         ├── các module Spring Web/MVC         ← transitive dependencies
         ├── thư viện xử lý JSON               ← transitive dependencies
         ├── web server nhúng                  ← transitive dependencies
         └── các module Spring Boot nền tảng   ← transitive dependencies
```

Đây là **sơ đồ khái niệm**: artifact cụ thể, số tầng và phiên bản thay đổi giữa các dòng Spring Boot. Muốn biết chính xác dự án hiện tại đã tải những gì, cần xem dependency tree từ Maven hoặc Gradle.

## 2. Starter trong Spring Boot là gì?

Một **Spring Boot starter** là một dependency được đóng gói và đặt tên để biểu diễn **một nhu cầu phát triển thường gặp**. Ví dụ:

- Muốn xây dựng REST API: dùng starter cho Spring Web/MVC.
- Muốn lưu dữ liệu qua JPA: dùng starter Data JPA.
- Muốn xác thực và phân quyền: dùng starter Security.
- Muốn kiểm thử Spring Boot: dùng starter Test.

Starter thường chủ yếu là **artifact khai báo dependency**, chứ không phải một thư viện tự chứa toàn bộ tính năng. Khi khai báo starter, hệ thống build sẽ giải quyết các dependency mà starter liệt kê. Spring Boot có thể tiếp tục dựa vào những thư viện hiện diện trên classpath để kích hoạt **auto-configuration** phù hợp.

Phân biệt ba tầng:

```text
       build.gradle / pom.xml
                 │
                 ▼
     Starter (nhóm dependency)
                 │
                 ▼
   Thư viện có mặt trên classpath
                 │
                 ▼
  Spring Boot xét điều kiện auto-configuration
                 │
                 ▼
  Bean/cấu hình được tạo nếu điều kiện thỏa mãn
```

Ví dụ, thêm starter Web cung cấp các thành phần cần thiết để xử lý HTTP trong một ứng dụng web Spring Boot. Nhưng **starter không tự biến bất kỳ lớp Java nào thành một endpoint**: bạn vẫn phải khai báo controller và mapping, đồng thời ứng dụng phải được khởi động đúng cách.

## 3. Các starter thường gom những thư viện nào?

Tên artifact và danh sách dependency dưới đây mô tả các nhóm chức năng phổ biến. Cấu trúc dependency cụ thể có thể thay đổi theo phiên bản Spring Boot; đặc biệt các phiên bản mới có thể tách, đổi tên hoặc tổ chức lại starter.

| Starter thường gặp | Mục đích | Nhóm thành phần thường được kéo theo |
| --- | --- | --- |
| `spring-boot-starter` | Nền tảng Spring Boot | Spring Core/Context, Spring Boot, auto-configuration, logging mặc định theo phiên bản |
| `spring-boot-starter-web` | Ứng dụng HTTP/REST theo mô hình servlet trong các dòng Spring Boot phổ biến | Spring Web, Spring MVC, JSON, embedded servlet server như Tomcat, nền tảng Boot |
| `spring-boot-starter-webflux` | Web reactive | Spring WebFlux, Project Reactor, HTTP server reactive mặc định theo cấu hình/phiên bản |
| `spring-boot-starter-data-jpa` | Truy cập dữ liệu quan hệ theo JPA | Spring Data JPA, Spring ORM, Hibernate và nền tảng JDBC/transaction |
| `spring-boot-starter-jdbc` | Thao tác SQL qua JDBC | Spring JDBC, transaction, connection pool thông dụng |
| `spring-boot-starter-validation` | Kiểm tra dữ liệu khai báo bằng Jakarta Bean Validation | Jakarta Validation API và implementation như Hibernate Validator |
| `spring-boot-starter-security` | Xác thực, phân quyền và các tích hợp Spring Security | Spring Security Core/Config/Web và thành phần liên quan |
| `spring-boot-starter-actuator` | Theo dõi, kiểm tra tình trạng và quản lý ứng dụng | Spring Boot Actuator và các thành phần endpoint/observability |
| `spring-boot-starter-test` | Kiểm thử | Spring Boot Test, JUnit Jupiter, Spring Test, AssertJ, Mockito cùng các thư viện hỗ trợ khác tùy phiên bản |

**Quan trọng về phiên bản:** bảng dùng các tên starter quen thuộc của Spring Boot, đặc biệt trong dự án Spring Boot 3.x. Các dòng Spring Boot khác có thể sử dụng tên starter cụ thể hơn (ví dụ theo công nghệ MVC) hoặc tổ chức lại các dependency. Hãy lấy file build được tạo cho **đúng phiên bản đang sử dụng** và kết quả dependency tree làm nguồn xác nhận.

### 3.1. Starter Web: vì sao chỉ một khai báo đã đủ làm REST API?

Xét một ứng dụng Spring Boot kiểu servlet. Muốn trả lời HTTP request, cần nhiều phần việc:

1. **Spring Web và Spring MVC**: nhận request, định tuyến URL, gọi phương thức controller và tạo response.
2. **Bộ chuyển đổi nội dung**: ví dụ chuyển object Java thành JSON qua thư viện JSON được cấu hình.
3. **Embedded web server**: ví dụ Tomcat trong nhiều cấu hình mặc định, nhận kết nối HTTP mà không cần triển khai WAR lên server độc lập.
4. **Spring Boot và cấu hình nền tảng**: tạo application context, đăng ký bean và thiết lập những giá trị mặc định hợp lý.

Nếu tự chọn từng dependency, bạn phải hiểu từng module, quan hệ tương thích và cách cấu hình chúng. Starter Web giúp gom chúng thành một lựa chọn phù hợp cho phần lớn REST API cơ bản.

Ví dụ controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/greeting")
    public Greeting greeting() {
        return new Greeting("Xin chào", 200);
    }

    public record Greeting(String message, int code) {}
}
```

Với ứng dụng Spring Boot đã có web starter phù hợp, lớp controller nằm trong vùng component scan và ứng dụng đang chạy ở cổng mặc định, truy cập:

```text
GET http://localhost:8080/greeting
```

Ví dụ response JSON:

```json
{
  "message": "Xin chào",
  "code": 200
}
```

`@RestController` và `@GetMapping` cung cấp metadata cho Spring MVC. Các HTTP message converter xử lý biểu diễn response; khi sử dụng JSON converter thích hợp, object được tuần tự hóa thành JSON. Trong các phiên bản/cấu hình khác nhau, thư viện JSON mặc định và cách tổ chức dependency có thể khác nhau.

### 3.2. Starter Data JPA: gom ORM và tích hợp Spring Data

Để truy cập database quan hệ bằng JPA, ứng dụng thường cần:

- Jakarta Persistence API (chuẩn JPA).
- Một JPA provider/ORM phổ biến như Hibernate.
- Spring Data JPA để khai báo repository và giảm code truy vấn lặp lại.
- Spring ORM và khả năng quản lý transaction.
- Các thành phần JDBC và connection pool phù hợp.

Starter Data JPA tập hợp những thành phần cơ bản để chúng hoạt động cùng Spring Boot. Ví dụ:

```java
package com.example.demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {} // JPA dùng constructor không tham số

    public Product(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

```java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
```

Spring Data JPA có thể tạo implementation của repository và tích hợp với `EntityManager`. Nhưng **starter Data JPA không thay thế JDBC driver của database bạn chọn**. Nếu dùng PostgreSQL, cần thêm driver tương ứng và cấu hình datasource:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Ví dụ `application.properties` cho môi trường học tập:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/demo
spring.datasource.username=demo_user
spring.datasource.password=${DB_PASSWORD}
```

Muốn chạy được, database phải thực sự tồn tại và truy cập được; cần cung cấp biến môi trường `DB_PASSWORD` và cấu hình schema/phương án migration thích hợp. Có starter không có nghĩa ứng dụng tự tạo PostgreSQL server hoặc tự biết thông tin kết nối.

### 3.3. Starter Security: thêm thư viện cũng có thể đổi hành vi mặc định

Trong dự án web, thêm `spring-boot-starter-security` thường đưa những thành phần Spring Security cần thiết vào classpath. Khi auto-configuration mặc định phù hợp và chưa có cấu hình bảo mật do ứng dụng định nghĩa, Spring Boot có thể thiết lập bảo vệ HTTP với hành vi mặc định.

Điều này giải thích vì sao endpoint trước đó truy cập tự do nhưng sau khi thêm starter Security, request có thể cần xác thực hoặc nhận `401 Unauthorized`/trang đăng nhập, tùy kiểu request và cấu hình.

**Bài học:** starter giúp chuẩn bị dependency, còn tính năng được kích hoạt tùy thuộc điều kiện auto-configuration và cấu hình ứng dụng. Khi thêm starter, luôn xem có thay đổi hành vi runtime nào không.

### 3.4. Starter Test: bộ công cụ dành cho phạm vi test

Kiểm thử Spring Boot thường sử dụng nhiều thư viện: framework chạy test (JUnit Jupiter), assertions (AssertJ), mock (Mockito), Spring Test và các tiện ích Spring Boot Test. Starter Test giúp bạn không phải chọn từng thư viện một.

Trong Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Trong Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**Phạm vi `test` / `testImplementation` có ý nghĩa:** thư viện chỉ dùng để viết và chạy test, không cần nằm trong runtime classpath của ứng dụng production. Quản lý đúng scope giúp giảm kích thước artifact và tránh mang theo thư viện không cần thiết.

## 4. Starter, dependency management và auto-configuration khác nhau như thế nào?

Ba khái niệm này thường xuất hiện cùng nhau nên dễ bị hiểu nhầm là một.

| Thành phần | Trả lời câu hỏi | Vai trò |
| --- | --- | --- |
| **Starter** | *Cần những thư viện nào cho tính năng này?* | Gom các dependency liên quan thành một điểm khai báo |
| **Dependency management / BOM** | *Nên dùng phiên bản nào?* | Quản lý tập phiên bản thư viện tương thích với một dòng Spring Boot |
| **Auto-configuration** | *Khi các thư viện và điều kiện đã có, Spring nên cấu hình gì?* | Tạo/configure bean theo classpath, property, bean hiện hữu và điều kiện khác |

Chúng bổ sung cho nhau; không nên đánh đồng.

### 4.1. BOM giải quyết phiên bản, starter giải quyết nhóm dependency

Giả sử một ứng dụng cần Spring MVC, Jackson, Hibernate và thư viện liên quan. Nếu bạn ghi phiên bản riêng cho mọi artifact, việc nâng cấp có thể tạo ra xung đột:

```text
spring-webmvc       phiên bản A
spring-core         phiên bản B
jackson-*           phiên bản C
hibernate-core      phiên bản D
...
```

**BOM** (*Bill of Materials*) là tập quy tắc quản lý phiên bản được kiểm thử để hoạt động cùng nhau. Với Maven, một dự án dùng `spring-boot-starter-parent` có thể thừa hưởng dependency management của Spring Boot:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

`3.3.5` trong đoạn ví dụ chỉ minh họa cách khai báo phiên bản Spring Boot ở parent; hãy dùng phiên bản thực tế mà dự án đã chọn và đang được hỗ trợ. Khi dependency được quản lý bởi parent/BOM, thường không cần ghi `<version>` ở từng starter.

Nếu không dùng Spring Boot parent, Maven có thể import BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Gradle cũng có thể dùng BOM qua `platform(...)` hoặc cơ chế dependency management tương thích:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Các đoạn BOM là **những cách thiết lập thay thế trong dự án minh họa**, không phải những đoạn phải chép cùng lúc vào mọi dự án. Khi khởi tạo từ Spring Initializr, thường chỉ cần giữ cấu hình build được sinh ra và nâng cấp phiên bản theo kế hoạch của dự án.

Không phải **mọi** thư viện bên ngoài đều nằm trong BOM; một dependency không được quản lý vẫn cần phiên bản rõ ràng hoặc nguồn quản lý phiên bản thích hợp.

### 4.2. Auto-configuration hoạt động dựa trên điều kiện

Spring Boot có thể tự đăng ký cấu hình khi nhìn thấy một số class trên classpath và những điều kiện khác được thỏa mãn. Một số kiểu điều kiện quan trọng:

```java
@ConditionalOnClass(SomeLibrary.class)
@ConditionalOnMissingBean(SomeService.class)
@ConditionalOnProperty(name = "feature.enabled", havingValue = "true")
```

Ví dụ mang tính khái niệm: nếu thư viện JDBC và datasource phù hợp có mặt, đồng thời cấu hình connection được cung cấp, Spring Boot có thể cấu hình `DataSource` và những bean liên quan. Nếu ứng dụng tự định nghĩa bean thay thế, một auto-configuration có thể nhường quyền nhờ điều kiện `@ConditionalOnMissingBean`.

Vì vậy, **không phải cứ thêm starter là tất cả bean đều được tạo**. Một số auto-configuration yêu cầu dependency, property, servlet/reactive environment hoặc bean khác. Có những trường hợp muốn tùy biến hoặc vô hiệu hóa một auto-configuration cụ thể thay vì loại bỏ toàn bộ starter.

Để xem vì sao một auto-configuration được chọn hoặc bỏ qua, bạn có thể chạy ứng dụng Spring Boot với báo cáo điều kiện, ví dụ:

```text
--debug
```

Trong ứng dụng đã bật cơ chế startup logging phù hợp, Spring Boot sẽ in **Conditions Evaluation Report** để hỗ trợ chẩn đoán. Không nhầm `--debug` của Spring Boot với việc chạy JVM qua debugger của IDE.

## 5. Tại sao cần starter?

### 5.1. Giảm công việc khai báo và cấu hình lặp lại

Thay vì phải nhớ tên và quan hệ của nhiều dependency, bạn chỉ cần khai báo mục đích: Web, Data JPA, Security hoặc Test. Điều này đặc biệt hữu ích với người mới học Spring Boot, vì có thể tập trung vào controller, service và logic nghiệp vụ.

### 5.2. Giảm rủi ro không tương thích phiên bản

Starter cùng cơ chế dependency management của Spring Boot giúp chọn bộ dependency thường được kiểm thử chung. Khi thay đổi phiên bản Spring Boot, nhiều phiên bản thư viện nền tảng có thể được quản lý tập trung.

Tuy nhiên, đây không phải bảo đảm rằng **mọi** dependency bổ sung, custom override hoặc plugin đều tương thích. Nếu tự ép một thư viện lên phiên bản khác, bạn vẫn có thể gây lỗi classpath.

### 5.3. Tận dụng cấu hình mặc định theo quy ước

Khi một nhóm thư viện phổ biến có mặt, auto-configuration có thể tạo nhiều bean mặc định thích hợp. Ví dụ web starter có thể góp phần giúp embedded server, MVC infrastructure và JSON converter được cấu hình để bạn bắt đầu viết endpoint nhanh hơn.

Vẫn có thể chỉnh cấu hình khi cần: đổi cổng, thêm interceptor, khai báo `SecurityFilterChain`, dùng datasource riêng hoặc thay thành phần mặc định.

### 5.4. Dễ đọc dự án và chia sẻ cho nhóm

Nhìn vào file build:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Một người trong nhóm có thể nhận ra dự án phát triển web, dùng JPA và PostgreSQL, kiểm tra dữ liệu bằng Bean Validation và có hỗ trợ test. Danh sách này thể hiện **ý định kiến trúc** rõ hơn hàng chục khai báo thư viện rời rạc.

### 5.5. Thuận tiện cho môi trường CI và tái lập build

Wrapper của Maven/Gradle kết hợp với cấu hình starter và BOM giúp môi trường khác có thể resolve dependency theo cùng khai báo trong repository. Với build đòi hỏi tính tái lập nghiêm ngặt, còn cần quản lý repository, artifact, lockfile/verification hoặc policy phiên bản tương ứng; starter tự nó không thay thế những yếu tố đó.

## 6. Xem chính xác starter đã kéo theo dependency nào

**Đừng đoán từ tên starter khi cần biết dependency thực tế.** Build tool có thể hiển thị cây phụ thuộc đã được resolve.

### 6.1. Maven: `dependency:tree`

Trong thư mục chứa `pom.xml`, dùng Maven wrapper:

**macOS/Linux**

```bash
./mvnw dependency:tree
```

**Windows PowerShell**

```powershell
.\mvnw.cmd dependency:tree
```

Đầu ra thường thể hiện dạng cây, với các dòng con nằm dưới dependency khai báo trực tiếp. Ví dụ đơn giản hóa:

```text
com.example:demo:jar:0.0.1-SNAPSHOT
\- org.springframework.boot:spring-boot-starter-web:jar:...:compile
   +- org.springframework.boot:spring-boot-starter:jar:...:compile
   +- org.springframework:spring-web:jar:...:compile
   \- org.springframework:spring-webmvc:jar:...:compile
```

Sơ đồ chỉ minh họa cách đọc cây dependency; những thành phần như JSON, embedded server, Spring Core và các dependency cấp sâu hơn đã được lược bớt. Maven sẽ hiển thị phiên bản và scope thực tế đã được resolve.

Để tìm dependency cụ thể, dùng thêm bộ lọc theo cú pháp Maven Dependency Plugin:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-webmvc
```

Nếu chạy PowerShell và việc truyền thuộc tính `-D...` gặp vấn đề về diễn giải đối số, hãy đặt nguyên đối số trong dấu ngoặc kép:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework:spring-webmvc"
```

### 6.2. Gradle: `dependencies` và `dependencyInsight`

Trong thư mục gốc của dự án Gradle:

**macOS/Linux**

```bash
./gradlew dependencies --configuration runtimeClasspath
```

**Windows PowerShell**

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

`runtimeClasspath` biểu diễn các dependency được resolve cho quá trình chạy của source set Java chính. Muốn xem vì sao có một thư viện, ví dụ Spring MVC:

```bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
```

Trong Gradle, các cấu hình dependency khác nhau phục vụ mục đích khác nhau:

| Configuration | Ý nghĩa điển hình |
| --- | --- |
| `implementation` | Khai báo thư viện cần cho mã ứng dụng |
| `runtimeOnly` | Thư viện chỉ cần ở runtime, ví dụ một JDBC driver |
| `compileOnly` | Cần khi biên dịch nhưng không đưa vào runtime classpath từ khai báo này |
| `testImplementation` | Thư viện dành cho việc viết và biên dịch test |
| `testRuntimeOnly` | Thư viện chỉ cần ở runtime của test |

Dependency tree không chỉ hiện tên mà còn thể hiện quan hệ bắc cầu, khả năng chọn phiên bản và các dependency bị thay thế/xung đột theo luật resolve của build tool.

### 6.3. Cách đọc một cây dependency

Ví dụ giả định:

```text
demo
├── starter-web
│   ├── spring-webmvc
│   │   └── spring-web
│   └── embedded-server
└── starter-data-jpa
    ├── spring-data-jpa
    └── hibernate-core
```

Ở đây `starter-web` và `starter-data-jpa` do dự án khai báo trực tiếp. `spring-webmvc`, `spring-data-jpa` và `hibernate-core` được kéo theo. Một thư viện có thể xuất hiện qua nhiều đường phụ thuộc; Maven hoặc Gradle sẽ giải quyết và chọn phiên bản theo quy tắc của công cụ.

Khi gặp lỗi `NoClassDefFoundError`, `NoSuchMethodError` hoặc xung đột giữa các thư viện, xem dependency tree thường hữu ích hơn việc thêm một dependency ngẫu nhiên.

## 7. Khi nào không nên chỉ dùng starter mặc định?

Starter giúp thuận tiện, nhưng không bắt buộc dùng mọi lựa chọn mặc định. Một số trường hợp cần thêm hoặc thay dependency rõ ràng.

### 7.1. Thêm JDBC driver riêng

Như ví dụ JPA, starter chuẩn bị ORM và Spring Data nhưng database cụ thể có thể yêu cầu driver riêng. PostgreSQL, MySQL, MariaDB hoặc Oracle có driver và cấu hình kết nối khác nhau. Chọn driver đúng database và quản lý phiên bản tương thích.

### 7.2. Thay web server mặc định

Trong nhiều dự án servlet dùng `spring-boot-starter-web`, Tomcat được kéo theo mặc định. Nếu cần Jetty trong một phiên bản Spring Boot hỗ trợ, có thể loại trừ Tomcat và thêm starter Jetty tương ứng.

Ví dụ Maven cho cách tổ chức starter thường gặp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

Lựa chọn server và tọa độ starter cần kiểm tra theo **phiên bản Spring Boot thực tế**; sơ đồ này không áp dụng nguyên xi cho mọi dòng phát hành. Sau khi loại trừ một dependency, cần xác nhận lại cây dependency và hành vi khởi động.

Với Gradle, ý tưởng tương tự:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

Loại trừ dependency là công cụ có chủ đích; nếu loại nhầm thư viện cần thiết, ứng dụng có thể không biên dịch hoặc không khởi động.

### 7.3. Dùng module trực tiếp khi không cần toàn bộ starter

Có trường hợp bạn chỉ cần một phần chức năng, chẳng hạn một module Spring cụ thể trong thư viện dùng chung hoặc công cụ command-line không chạy web server. Khi đó, khai báo dependency trực tiếp có thể phù hợp hơn:

```groovy
dependencies {
    implementation 'org.springframework:spring-context'
}
```

Tuy nhiên, nếu đây là ứng dụng Spring Boot hoàn chỉnh, việc dùng starter cho nhu cầu phổ biến thường đơn giản hơn. **Mục tiêu là chọn đủ dependency cần thiết** thay vì thêm càng nhiều starter càng tốt.

### 7.4. Starter do bên thứ ba cung cấp

Không phải tất cả starter đều do nhóm Spring Boot phát hành. Các thư viện bên thứ ba cũng có thể cung cấp starter tích hợp Spring Boot, thường với quy ước đặt tên như `ten-thu-vien-spring-boot-starter`.

Chẳng hạn một starter tích hợp dịch vụ có thể kéo theo client SDK và các module auto-configuration của nhà cung cấp. Vì vậy cần xem:

- Nguồn phát hành, phiên bản và mức độ bảo trì của starter.
- Danh sách dependency bắc cầu, bao gồm cả thư viện runtime.
- Điều kiện cấu hình, biến môi trường và bảo mật cần thiết.
- Khả năng tương thích với phiên bản Spring Boot đang dùng.

Không nên suy ra chất lượng hoặc tính tương thích của một starter chỉ từ việc tên có hậu tố `starter`.

## 8. Những hiểu nhầm thường gặp

| Hiểu nhầm | Giải thích đúng |
| --- | --- |
| “Starter là một thư viện chứa toàn bộ Spring Boot.” | Starter chủ yếu gom những dependency cho một nhu cầu cụ thể; chức năng nằm trong các thư viện được kéo theo. |
| “Cứ thêm starter thì tính năng chạy ngay.” | Có thể còn cần class, annotation, config, connection và điều kiện auto-configuration phù hợp. |
| “Starter tự quyết định tất cả phiên bản dependency.” | BOM/dependency management quyết định các phiên bản được quản lý; starter quyết định nhóm dependency. |
| “Muốn dùng PostgreSQL chỉ cần Data JPA.” | Thường còn cần PostgreSQL JDBC driver, database và datasource configuration. |
| “Starter Web luôn gồm đúng các JAR giống nhau.” | Thành phần, module và tên starter có thể khác theo phiên bản và cách resolve. |
| “Thêm tất cả starter cho tiện.” | Làm tăng dependency, có thể tăng footprint và kích hoạt hành vi không mong muốn như security configuration. |
| “Có dependency trong `pom.xml` nghĩa là nó luôn có mặt trong production JAR.” | Còn tùy scope, packaging, plugin và quá trình tạo artifact. |
| “Starter và wrapper là một.” | Starter gom thư viện; Gradle/Maven wrapper giúp chạy đúng phiên bản build tool. |

### 8.1. Spring Web và WebFlux có nên thêm cả hai?

Hai stack phục vụ mô hình phát triển khác nhau: Spring MVC thường dùng servlet và phong cách lập trình blocking; WebFlux hỗ trợ reactive programming. Cả hai có thể cùng xuất hiện trong classpath của một ứng dụng ở những trường hợp nhất định, nhưng việc thêm cả hai starter chỉ vì “cho đủ thư viện” dễ gây nhầm lẫn về loại ứng dụng, server và cách xử lý request. Nên xác định mô hình web muốn dùng rồi chọn dependency có chủ đích.

### 8.2. Vì sao thêm starter rồi vẫn bị lỗi?

Có thể do một trong các nguyên nhân:

1. Chưa khai báo dependency ở scope/cấu hình thích hợp.
2. Chưa đồng bộ Maven/Gradle hoặc repository không tải được artifact.
3. JDK/build tool không tương thích với phiên bản Spring Boot.
4. Thiếu thành phần bên ngoài như database, driver, broker hoặc thông tin kết nối.
5. Tự override phiên bản dẫn đến conflict.
6. Điều kiện auto-configuration không thỏa mãn hoặc đã bị loại trừ.
7. Component nằm ngoài phạm vi package scan, thiếu annotation hoặc thiếu bean yêu cầu.

Để tìm nguyên nhân, đọc log khởi động, kiểm tra dependency tree và cấu hình tương ứng thay vì mặc định quy lỗi cho starter.

## 9. Thực hành trên dự án Spring Boot đầu tiên

### Bài 1 — Quan sát dependency được kéo theo

Tạo một dự án từ Spring Initializr chỉ chọn **Spring Web** và **Spring Boot Test** theo cấu hình sinh sẵn. Mở `pom.xml` hoặc `build.gradle` để xác định đâu là direct dependency.

Chạy lệnh hiển thị cây dependency:

```bash
# Gradle
./gradlew dependencies --configuration runtimeClasspath

# Maven
./mvnw dependency:tree
```

Chỉ chạy lệnh phù hợp với build tool đã chọn. Với Windows, dùng `gradlew.bat` hoặc `mvnw.cmd` thay cho script Unix. Hãy tìm các module HTTP, MVC, JSON và web server trong cây; ghi lại **tên thực tế** thay vì chỉ dựa vào sơ đồ ở bài này.

### Bài 2 — Bổ sung Validation

Thêm starter Validation tương ứng phiên bản Spring Boot và tạo request DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank String name,
    @Size(min = 3, max = 20) String sku
) {}
```

Khi có `@Valid` trên tham số `@RequestBody` và hạ tầng validation phù hợp, Spring MVC có thể kiểm tra dữ liệu theo constraint:

```java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    @PostMapping("/products")
    public String create(@Valid @RequestBody CreateProductRequest request) {
        return "Created: " + request.name();
    }
}
```

Thử gửi JSON với `"name": ""` để quan sát phản hồi khi validation không đạt. Sau đó xem dependency tree để xác nhận starter Validation kéo theo thư viện triển khai Bean Validation nào trong phiên bản đang dùng.

### Bài 3 — Quan sát tác động của Security

Trong một dự án web thử nghiệm riêng, truy cập endpoint `/greeting` khi **chưa** có starter Security. Sau đó thêm starter Security, khởi động lại và thử truy cập URL lần nữa. So sánh HTTP status và log khởi động.

Giải thích: điều gì đến từ việc **dependency có mặt trên classpath**, và điều gì đến từ **auto-configuration**? Sau khi thử nghiệm, có thể cấu hình security phù hợp mục đích ứng dụng thay vì dựa vào hành vi mặc định.

### Bài 4 — Chọn starter dựa trên nhu cầu

Hãy chọn dependency phù hợp cho các yêu cầu sau và giải thích có cần cấu hình bổ sung hay không:

| Yêu cầu | Gợi ý lựa chọn |
| --- | --- |
| REST API nhận/trả JSON qua Spring MVC | Starter Web/MVC phù hợp với phiên bản |
| Lưu `Product` vào PostgreSQL bằng repository JPA | Data JPA + PostgreSQL driver + datasource |
| Kiểm tra `@NotBlank` trong request body | Validation starter + `@Valid` và constraint |
| Bảo vệ endpoint cần đăng nhập | Security starter + cấu hình xác thực/phân quyền |
| Viết unit test với JUnit, Mockito | Starter Test ở test scope |
| Kiểm tra tình trạng vận hành | Actuator starter + cấu hình exposure/security cho endpoint cần thiết |

## 10. Ghi nhớ

**Starter là một lựa chọn tiện lợi cho nhóm dependency**, còn **transitive dependency** giải thích vì sao khai báo một starter lại tải về nhiều thư viện. **Dependency management/BOM** giúp đồng bộ phiên bản, còn **auto-configuration** dùng các điều kiện ở runtime để cấu hình ứng dụng dựa trên những thư viện và thông tin cấu hình hiện diện.

Khi nhìn thấy một starter mới, hãy đặt ba câu hỏi:

1. **Nó giải quyết nhu cầu gì?** Ví dụ HTTP, JPA, Security hay Test.
2. **Nó kéo theo những thư viện nào trong phiên bản dự án hiện tại?** Hãy xem `dependency:tree` hoặc `dependencies`.
3. **Ứng dụng còn cần cấu hình hoặc dịch vụ bên ngoài nào để hoạt động?** Ví dụ datasource, JDBC driver, controller hay security policy.

Hiểu được ba điều này giúp bạn chọn starter đúng, đọc file build tự tin hơn và giải quyết lỗi dependency có phương pháp khi phát triển các ứng dụng Spring Boot tiếp theo.
