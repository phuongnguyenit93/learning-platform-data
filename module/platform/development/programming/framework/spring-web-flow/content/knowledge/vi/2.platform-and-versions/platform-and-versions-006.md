# Khai báo dependency bằng Maven hoặc Gradle

> **Chương:** Nền tảng và phiên bản  
> **Mục tiêu:** Biết cách thêm Spring Web Flow vào dự án Java bằng Maven hoặc Gradle; chọn artifact và phiên bản phù hợp với Spring Framework, Spring Security, JDK và servlet container; quản lý dependency trực tiếp/gián tiếp, scope đóng gói, dependency test và xác minh classpath thực tế.

## 1. Vì sao phải khai báo dependency có chủ đích?

Spring Web Flow (SWF) mô hình hóa hành trình web nhiều bước bằng **flow definition**, **state**, **event** và **transition**. Một flow có thể đi qua nhiều HTTP request, giữ dữ liệu trong scope, bind form, gọi action và tích hợp Spring MVC.

Để biên dịch và chạy ứng dụng dùng Web Flow, dự án cần các thư viện tương ứng với những phần thực sự sử dụng:

- **Spring Web Flow:** engine thực thi flow, state, transition, execution và binding.
- **Spring Framework:** container, context, MVC và các abstraction mà ứng dụng dùng.
- **Servlet API:** hợp đồng servlet của container triển khai web app.
- **Spring Security:** nếu ứng dụng có xác thực/phân quyền hoặc listener tích hợp bảo mật.
- **Thư viện kiểm thử:** kiểm thử service, Spring context, MVC và hành trình flow.

Khai báo dependency sai có thể gây:

- Compile thành công nhưng runtime thiếu class.
- Nhiều phiên bản Spring Framework cùng xuất hiện trên classpath.
- `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi khởi tạo bean.
- Xung đột giữa `javax.servlet` và `jakarta.servlet`.
- Dependency test bị đóng gói nhầm vào WAR/JAR.
- Flow definition tồn tại nhưng ứng dụng chưa có cấu hình registry/executor để chạy flow.

**Thêm dependency là bước đưa thư viện vào classpath.** Nó chưa tự tạo `FlowRegistry`, `FlowExecutor`, `FlowHandlerMapping`, `FlowHandlerAdapter`, view resolver hay đăng ký flow definition.

## 2. Xác định các thành phần trước khi thêm thư viện

Trước khi sửa `pom.xml` hoặc file Gradle, xác định kiến trúc dự án:

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Dự án dùng Maven hay Gradle? | Chọn đúng file build và cách quản lý dependency |
| Ứng dụng là WAR chạy servlet container hay ứng dụng khác? | Quyết định servlet API và packaging |
| Spring Framework/Spring Boot đang ở phiên bản nào? | Quyết định baseline và khả năng tương thích |
| Spring Security có được sử dụng không? | Chọn module security và phiên bản đồng bộ |
| JDK mục tiêu là gì? | Các thư viện có yêu cầu Java tối thiểu khác nhau |
| Container cung cấp Servlet API nào? | Phải khớp `javax` hoặc `jakarta` |
| Flow cần tích hợp với Spring MVC hay môi trường khác? | Quyết định các module bổ sung và cấu hình |

Đừng chọn version bằng cách lấy phiên bản mới nhất của từng dependency một cách độc lập. Các thư viện Spring được phát triển theo một ma trận tương thích; phiên bản mới hơn của một module không nhất thiết tương thích với toàn bộ stack hiện có.

### 2.1. Phân biệt dependency với cấu hình runtime

~~~text
Build configuration
  -> dependency artifacts
  -> compile/test/runtime classpath

Spring application configuration
  -> ApplicationContext
  -> FlowRegistry
  -> FlowBuilderServices
  -> FlowExecutor
  -> Spring MVC integration
  -> flow definitions and views
~~~

Nếu dependency đã có nhưng request `/booking` không chạy flow, nguyên nhân có thể nằm ở lớp cấu hình runtime, mapping URL, registry hoặc view chứ không phải Maven/Gradle.

## 3. Artifact Spring Web Flow

Artifact chính thường dùng trong Maven Central có tọa độ:

~~~text
groupId:    org.springframework.webflow
artifactId: spring-webflow
~~~

Một version thường gặp trong các dự án Web Flow 2.x là `2.5.1.RELEASE`. Đây là **version minh họa để đọc cú pháp dependency**, không phải khuyến nghị mặc định cho một dự án mới hoặc khẳng định đó là bản mới nhất.

Không nên chọn version chỉ vì ví dụ trên. Hãy xác định bản SWF tương thích với:

- Spring Framework đang dùng.
- Spring Security đang dùng nếu có.
- Java/JDK mục tiêu.
- Servlet API và container.
- Cấu hình XML/Java và các extension cần thiết.

### 3.1. Những artifact liên quan

| Thành phần | Khi nào cần khai báo trực tiếp? |
| --- | --- |
| `org.springframework.webflow:spring-webflow` | Ứng dụng thực sự sử dụng Spring Web Flow |
| `org.springframework:spring-webmvc` | Ứng dụng dùng Spring MVC và import API MVC trực tiếp |
| `org.springframework:spring-context` | Code/config dùng API này và quy tắc dự án yêu cầu khai báo trực tiếp |
| `org.springframework.security:*` | Khi ứng dụng sử dụng Spring Security; chọn đúng module theo chức năng |
| Servlet API (`javax.servlet` hoặc `jakarta.servlet`) | Khi code cần compile với Servlet API do container cung cấp |
| `org.springframework:spring-test` | Khi viết test dùng Spring TestContext/MVC test |

Spring Web Flow có thể kéo theo một số dependency thông qua quan hệ transitive. Trước khi thêm tất cả các artifact bằng tay, hãy kiểm tra dependency tree. Khai báo trực tiếp những thư viện mà mã nguồn dự án phụ thuộc vào giúp build rõ ràng hơn; tránh khai báo trùng chỉ để “chắc chắn”.

### 3.2. Không nhầm artifact với Spring Boot starter

`spring-webflow` là artifact của Spring Web Flow. Không tự giả định rằng mọi phiên bản Spring Boot đều có starter chính thức, tương thích và tự động cấu hình đầy đủ Web Flow.

Nếu dự án dùng Boot, cần xác minh:

- Starter đang dùng do ai phát hành và hỗ trợ phiên bản nào.
- Nó có thực sự cấu hình FlowRegistry/FlowExecutor và Spring MVC integration không.
- Có xung đột dependency hoặc auto-configuration nào không.
- Những bean nào vẫn phải khai báo thủ công.

Không thêm một starter bên thứ ba chỉ vì tên có chữ `webflow` mà chưa xem metadata, tài liệu và dependency tree.

## 4. Quản lý phiên bản và tính tương thích

~~~text
Spring Web Flow
  ├─ Spring Binding / Web Flow internals
  ├─ Spring Framework
  │    ├─ spring-core
  │    ├─ spring-context
  │    ├─ spring-beans
  │    └─ spring-web / spring-webmvc
  ├─ Spring Security (nếu dùng)
  └─ Servlet API do môi trường triển khai cung cấp
~~~

Các dependency này phải tương thích ở cả **API** lẫn **runtime baseline**.

### 4.1. Không trộn version Spring tùy tiện

Ví dụ nguy hiểm:

~~~text
spring-core       version A
spring-context    version B
spring-webmvc     version C
spring-webflow    version D
spring-security   version E
~~~

Nếu các version không nằm trong một tổ hợp được hỗ trợ, ứng dụng có thể biên dịch nhưng lỗi lúc khởi động hoặc khi gọi method.

Nên:

1. Chọn baseline Spring Framework thống nhất.
2. Dùng Spring Framework BOM hoặc dependency management để căn chỉnh các module cùng dòng.
3. Chọn Spring Web Flow version tương thích với baseline đó.
4. Nếu dùng Spring Security, quản lý các module Security theo BOM/version đồng bộ.
5. Chốt JDK và Servlet API theo môi trường thực tế.
6. Chạy dependency tree và integration test.

### 4.2. BOM là gì?

**Bill of Materials (BOM)** là POM dạng `pom` được import để quản lý phiên bản cho một nhóm artifact. Thay vì gắn version riêng vào từng module Spring Framework, BOM cung cấp version thống nhất qua `dependencyManagement`.

Một BOM không tự thêm dependency vào dự án. Nó chỉ quản lý phiên bản khi dependency tương ứng được khai báo.

### 4.3. Spring Framework BOM không tự quản lý version Spring Web Flow

Spring Framework BOM quản lý các artifact thuộc phạm vi BOM. Không mặc định rằng nó sẽ chọn version cho `org.springframework.webflow:spring-webflow`.

Hãy quản lý version Web Flow riêng, đồng thời xác minh version đó tương thích với các module Spring Framework được BOM quản lý.

### 4.4. Chú ý ranh giới javax và jakarta

Các thế hệ Spring/Servlet khác nhau có thể dùng namespace:

~~~text
javax.servlet.*
jakarta.servlet.*
~~~

Đây là hai package namespace khác nhau. Một thư viện biên dịch với `javax.servlet` không tự tương thích với container chỉ cung cấp `jakarta.servlet`, và ngược lại.

Trước khi chọn SWF version, hãy kiểm tra namespace mà artifact thực tế sử dụng và baseline của Spring/container. Đừng giải quyết bằng cách thêm đồng thời cả hai Servlet API vào WAR; điều đó không chuyển đổi bytecode hoặc API của thư viện.

## 5. Khai báo dependency bằng Maven

Maven quản lý dependency trong `pom.xml`. Một dependency cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
    <version>2.5.1.RELEASE</version>
</dependency>
~~~

Version trong ví dụ chỉ minh họa cú pháp và một version Web Flow 2.x cụ thể. Trong dự án thực tế, nên đặt version thành property để dễ kiểm soát:

~~~xml
<properties>
    <spring-webflow.version>2.5.1.RELEASE</spring-webflow.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.webflow</groupId>
        <artifactId>spring-webflow</artifactId>
        <version>${spring-webflow.version}</version>
    </dependency>
</dependencies>
~~~

### 5.1. Dùng dependencyManagement cho Spring Framework

Ví dụ dưới đây minh họa cách import Spring Framework BOM. Hãy thay giá trị placeholder bằng version đã được dự án xác minh tương thích với Spring Web Flow và JDK:

~~~xml
<properties>
    <spring-framework.version>REPLACE_WITH_COMPATIBLE_VERSION</spring-framework.version>
    <spring-webflow.version>2.5.1.RELEASE</spring-webflow.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.webflow</groupId>
        <artifactId>spring-webflow</artifactId>
        <version>${spring-webflow.version}</version>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

`REPLACE_WITH_COMPATIBLE_VERSION` là placeholder, không phải version Maven hợp lệ. Cần thay trước khi build. Nếu dự án đã dùng Spring Boot dependency management hoặc một BOM nội bộ, không import thêm một BOM khác mà chưa kiểm tra xung đột.

### 5.2. Vì sao khai báo spring-webmvc riêng?

Nếu ứng dụng trực tiếp dùng Spring MVC, khai báo `spring-webmvc` làm dependency trực tiếp giúp mô tả đúng dependency của mã nguồn. Dù artifact khác có thể kéo nó theo dạng transitive, không nên dựa vào một dependency gián tiếp nếu dự án thực sự phụ thuộc vào API đó.

Tuy nhiên, hãy xem dependency tree trước khi thêm. Nếu module web không dùng Spring MVC hoặc framework được tích hợp theo cách khác, không cần thêm chỉ vì một ví dụ có nó.

### 5.3. Servlet API trong Maven WAR

Ứng dụng WAR chạy trên servlet container thường cần Servlet API để compile. Container đã cung cấp implementation khi chạy, vì vậy scope thường là `provided`.

Ví dụ minh họa cho một dự án thuộc thế hệ `javax.servlet`:

~~~xml
<dependency>
    <groupId>javax.servlet</groupId>
    <artifactId>javax.servlet-api</artifactId>
    <version>REPLACE_WITH_CONTAINER_COMPATIBLE_VERSION</version>
    <scope>provided</scope>
</dependency>
~~~

Nếu stack thuộc thế hệ Jakarta, artifact và namespace sẽ là `jakarta.servlet:jakarta.servlet-api`. Không dùng hai dòng này cùng lúc để “hỗ trợ cả hai”; chọn một theo Spring/Web Flow và container đã chốt.

Placeholder version cần được thay bằng version tương ứng container. Scope `provided` giúp Maven đưa API vào compile/test classpath theo quy tắc scope nhưng không đóng gói như thư viện runtime thông thường trong WAR.

### 5.4. Dependency kiểm thử

Một cấu hình test thường có:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu test tích hợp Spring Security, có thể cần module test tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các dependency này chỉ cần khi test thực sự dùng API của chúng. Version Spring Security phải tương thích với Spring Framework và các module Security còn lại; quản lý bằng BOM hoặc dependency management đã được dự án chọn.

## 6. Khai báo dependency bằng Gradle

Gradle khai báo dependency trong `build.gradle` hoặc `build.gradle.kts`. Với Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'war'
}

repositories {
    mavenCentral()
}

ext {
    springWebFlowVersion = '2.5.1.RELEASE' // Version minh họa, cần xác minh tương thích.
}

dependencies {
    implementation "org.springframework.webflow:spring-webflow:" + springWebFlowVersion
    implementation "org.springframework:spring-webmvc"

    // Chỉ dùng cho stack javax.servlet và WAR chạy trên container cung cấp API.
    providedCompile "javax.servlet:javax.servlet-api:REPLACE_WITH_CONTAINER_COMPATIBLE_VERSION"

    testImplementation "org.springframework:spring-test"
    testImplementation "org.springframework.security:spring-security-test"
}
~~~

Đoạn trên là **mẫu minh họa**. `providedCompile` thuộc cấu hình plugin `war`; với các kiểu project/Gradle khác có thể cần configuration khác. Placeholder version phải được thay và module Security test chỉ giữ nếu dự án có Spring Security.

### 6.1. Quản lý version bằng platform/BOM

Với Gradle, có thể import BOM để quản lý version các module Spring Framework:

~~~groovy
ext {
    springFrameworkVersion = 'REPLACE_WITH_COMPATIBLE_VERSION'
    springWebFlowVersion = '2.5.1.RELEASE'
}

dependencies {
    implementation platform(
        "org.springframework:spring-framework-bom:" + springFrameworkVersion
    )

    implementation "org.springframework.webflow:spring-webflow:" + springWebFlowVersion
    implementation "org.springframework:spring-webmvc"
}
~~~

Gradle `platform(...)` đưa dependency constraints từ BOM vào resolution. Nó không tự chọn phiên bản Spring Web Flow nếu BOM không quản lý artifact đó.

Nếu cần quản lý Spring Security, hãy import BOM phù hợp với phiên bản Spring Security mà dự án dùng hoặc cấu hình version đồng bộ theo chính sách build. Không trộn BOM mới và cũ tùy tiện.

### 6.2. Kotlin DSL

Với `build.gradle.kts`, cú pháp tương đương:

~~~kotlin
plugins {
    java
    war
}

repositories {
    mavenCentral()
}

val springWebFlowVersion = "2.5.1.RELEASE"

dependencies {
    implementation(
        "org.springframework.webflow:spring-webflow:$springWebFlowVersion"
    )
    implementation("org.springframework:spring-webmvc")

    // Version phải khớp servlet namespace/container của dự án.
    compileOnly("javax.servlet:javax.servlet-api:REPLACE_WITH_COMPATIBLE_VERSION")

    testImplementation("org.springframework:spring-test")
}
~~~

Đây là ví dụ cho một cấu hình Kotlin DSL. `compileOnly` không đóng gói Servlet API; với plugin WAR và mục tiêu chạy trên container, kiểm tra thêm cấu hình packaging/test để scope đúng với cách dự án triển khai.

## 7. Chọn scope/configuration phù hợp

Dependency không chỉ có tên và version; **scope** quyết định thư viện xuất hiện ở giai đoạn nào và có được đóng gói hay không.

| Nhu cầu | Maven | Gradle thường dùng | Ý nghĩa |
| --- | --- | --- | --- |
| Code ứng dụng cần thư viện khi compile và runtime | `compile` (mặc định) | `implementation` | Có trong classpath ứng dụng |
| API do container cung cấp | `provided` | `providedCompile`/`compileOnly` tùy plugin và mục tiêu | Không đóng gói như dependency runtime thông thường |
| Chỉ cần cho test | `test` | `testImplementation` | Không thuộc runtime artifact production |
| Thư viện chỉ cần khi compile, không runtime | `provided` hoặc cấu hình phù hợp | `compileOnly` | Chỉ dùng khi runtime có nguồn cung cấp |
| Thư viện cần runtime nhưng không compile trực tiếp | `runtime` | `runtimeOnly` | Có trên runtime classpath |

Tên configuration và semantics chi tiết có thể phụ thuộc plugin/version. Hãy xác minh WAR/JAR được tạo ra và classpath test/runtime thay vì chỉ nhìn tên cấu hình.

### 7.1. Không đặt Spring Web Flow vào test scope

Nếu mã ứng dụng có:

~~~java
import org.springframework.webflow.execution.RequestContext;
~~~

thì `spring-webflow` là dependency compile/runtime của ứng dụng, không phải chỉ `test`. Nếu chỉ một test utility dùng một thư viện phụ trợ, thư viện phụ trợ đó mới thuộc test scope.

### 7.2. Không đóng gói Servlet API của container vào WAR

Nếu container cung cấp Servlet API, đóng gói thêm một bản khác vào `WEB-INF/lib` có thể tạo classloading conflict. Dùng scope/configuration phù hợp với servlet container đã chọn.

### 7.3. Phân biệt compileOnly và runtimeOnly

- `compileOnly`: compiler nhìn thấy API nhưng ứng dụng không mang thư viện đó như runtime dependency.
- `runtimeOnly`: code không compile trực tiếp với API nhưng runtime cần implementation.

Đừng dùng `runtimeOnly` cho Spring Web Flow nếu ứng dụng import các class Web Flow trong source code.

## 8. Dependency transitive và xung đột phiên bản

Khi khai báo `spring-webflow`, build tool có thể tải các dependency mà artifact này cần. Chúng được gọi là **transitive dependencies**.

~~~mermaid
flowchart TD
    A["Ứng dụng"] --> B["spring-webflow"]
    B --> C["Các module Spring liên quan"]
    B --> D["Spring Binding / các dependency khác"]
    A --> E["spring-webmvc khai báo trực tiếp"]
    A --> F["spring-security nếu dùng"]
    A --> G["Servlet API do container cung cấp"]
~~~

Đây là sơ đồ khái niệm, không phải danh sách dependency cố định của mọi version. Dependency thực tế được khai báo trong POM của artifact và thay đổi theo version.

### 8.1. Khi nào cần exclusion?

Maven:

~~~xml
<dependency>
    <groupId>some.vendor</groupId>
    <artifactId>some-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>example.group</groupId>
            <artifactId>conflicting-module</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Gradle:

~~~groovy
implementation("some.vendor:some-library:1.0.0") {
    exclude group: "example.group", module: "conflicting-module"
}
~~~

Chỉ exclusion khi đã xác định dependency nào gây xung đột và dự án chủ động cung cấp phiên bản thay thế tương thích. Loại bỏ tùy tiện có thể làm thiếu class ở runtime.

### 8.2. Tránh ép version bằng cách loại bỏ mọi dependency cũ

Nếu dependency tree chứa hai version `spring-core`, hãy tìm lý do:

- Module trực tiếp nào kéo version cũ?
- BOM nào đang quản lý version?
- Có dependency từ một thư viện legacy không?
- Có nhiều Spring Framework line cùng tồn tại?

Sau đó căn chỉnh bằng dependency management/constraints. Đừng exclusion hàng loạt chỉ để build không còn cảnh báo.

### 8.3. Dependency convergence

Một dự án nên kiểm soát việc nhiều đường dependency đưa vào các version khác nhau của cùng một artifact. Maven có thể dùng Enforcer/plugin kiểm tra dependency convergence; Gradle có thể dùng dependency constraints, resolution rules hoặc plugin kiểm tra dependency.

Nếu buộc phải dùng resolution rule, hãy ghi lại lý do và test runtime. Ép tất cả artifact Spring về một version không được hỗ trợ vẫn có thể làm hỏng API.

## 9. Maven: kiểm tra dependency đã được resolve

Các lệnh hữu ích:

~~~bash
# Hiển thị dependency tree của dự án
mvn dependency:tree

# Lọc các module Spring/Web Flow (cú pháp plugin có thể khác theo version)
mvn dependency:tree -Dincludes=org.springframework:*,org.springframework.webflow:*

# Build và chạy test
mvn -U clean test
~~~

Tùy phiên bản Maven Dependency Plugin, cú pháp `-Dincludes` và cách lọc có thể khác. Có thể chạy dependency:tree đầy đủ rồi tìm thủ công `spring-webflow`, `spring-core`, `spring-context`, `spring-webmvc` và `spring-security`.

### 9.1. Đọc dependency tree

Ví dụ minh họa:

~~~text
com.example:appointment-app:war:1.0
+- org.springframework.webflow:spring-webflow:jar:2.5.1.RELEASE:compile
|  +- org.springframework:spring-context:jar:<resolved-version>:compile
|  \- ...
+- org.springframework:spring-webmvc:jar:<resolved-version>:compile
\- org.springframework:spring-test:jar:<resolved-version>:test
~~~

Các giá trị `<resolved-version>` là placeholder. Hãy kiểm tra version thực tế của dự án; không sao chép chúng vào file build.

Kiểm tra:

- Chỉ có một version phù hợp cho mỗi module Spring quan trọng.
- Spring Security modules được căn chỉnh.
- Servlet API không bị đóng gói sai.
- Dependency test không rò vào production artifact.
- Không có artifact cũ được kéo vào từ thư viện legacy.

### 9.2. Dependency:tree không chứng minh flow chạy đúng

Lệnh trên chứng minh Maven resolve được dependency graph. Nó không chứng minh:

- Flow XML được tìm thấy.
- Flow ID được đăng ký.
- FlowExecutor được tạo.
- MVC mapping nhận request.
- View resolver tìm thấy template.
- Listener/validator/converter đã được cấu hình.

Các điều này cần Spring context test và integration test.

## 10. Gradle: kiểm tra dependency đã được resolve

Các lệnh hữu ích:

~~~bash
# Liệt kê dependency runtime
./gradlew dependencies --configuration runtimeClasspath

# Liệt kê dependency compile
./gradlew dependencies --configuration compileClasspath

# Giải thích tại sao một module được chọn
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath

# Kiểm tra Web Flow
./gradlew dependencyInsight --dependency spring-webflow --configuration runtimeClasspath

# Chạy kiểm thử
./gradlew clean test
~~~

Trên Windows, có thể dùng `gradlew.bat` thay cho `./gradlew`.

### 10.1. Đọc kết quả resolution

Gradle có thể chọn một version theo conflict resolution hoặc constraints. `dependencyInsight` cho biết:

- Dependency được yêu cầu từ những module nào.
- Vì sao version được chọn.
- Có constraint/platform nào áp dụng không.
- Có version nào bị thay thế hay không.

Nếu version được chọn không tương thích với Web Flow, cần chỉnh lại constraints/BOM hoặc dependency source; đừng chỉ dựa vào việc Gradle đã chọn một version để kết luận ứng dụng an toàn.

### 10.2. Kiểm tra artifact WAR

Nếu ứng dụng đóng gói WAR:

~~~bash
./gradlew war
~~~

Sau đó kiểm tra nội dung `WEB-INF/lib` để xác minh:

- Spring Web Flow và runtime dependencies cần thiết có mặt.
- Servlet API do container cung cấp không bị đóng gói nhầm.
- Dependency test không nằm trong WAR.
- Không có hai phiên bản module Spring cùng bị đóng gói.

Tên file và vị trí output WAR phụ thuộc cấu hình project.

## 11. Spring Web Flow trong dự án Spring MVC

Ứng dụng dùng Spring MVC thường cần các thành phần runtime:

~~~text
DispatcherServlet
  -> FlowHandlerMapping
  -> FlowHandlerAdapter
  -> FlowExecutor
  -> FlowRegistry
  -> FlowDefinition
~~~

Các class/cấu hình namespace cụ thể phụ thuộc phiên bản. Mục tiêu là:

1. Đăng ký flow definition trong registry.
2. Cấu hình flow builder services cần thiết.
3. Tạo FlowExecutor để start/resume execution.
4. Đưa FlowHandlerMapping và FlowHandlerAdapter vào MVC context phù hợp.
5. Cấu hình view resolver và các view tương ứng.
6. Tích hợp Spring Security nếu cần.

**Maven/Gradle chỉ đưa class vào classpath.** Nếu thiếu các bean và mapping trên, request vẫn có thể đi vào controller thông thường hoặc trả 404/500.

### 11.1. Không giả định dependency tự tạo flow

Khai báo dependency `org.springframework.webflow:spring-webflow` không tự động tìm mọi file `*-flow.xml` trong dự án rồi công khai URL cho chúng. Ứng dụng cần cấu hình registry, executor và MVC integration theo tài liệu Web Flow.

### 11.2. Cấu trúc tài nguyên không quyết định dependency

Một flow có thể được đặt ở:

~~~text
src/main/resources/flows/booking/booking-flow.xml
~~~

nhưng việc file nằm trong classpath không có nghĩa flow đã được đăng ký. Registry cần được cấu hình đúng location và flow ID.

## 12. Dự án dùng Spring Boot

Spring Boot có cơ chế dependency management và auto-configuration cho nhiều module. Tuy nhiên, với Spring Web Flow, cần xác minh cụ thể cách tích hợp đang sử dụng.

Checklist:

- Boot version có tương thích với Spring Framework line mà SWF yêu cầu không?
- Artifact Web Flow version có được hỗ trợ với JDK và servlet namespace không?
- Có starter tương thích thật sự không, và do ai phát hành?
- FlowRegistry/FlowExecutor được auto-configure hay phải tạo bean thủ công?
- FlowHandlerMapping/Adapter đã đăng ký đúng thứ tự với MVC chưa?
- Flow XML và view resources có được đóng gói vào artifact không?

Không thêm một starter không rõ nguồn chỉ để tránh cấu hình thủ công. Một starter bên thứ ba có thể quản lý version hoặc cấu hình theo giả định riêng.

### 12.1. Không trộn Spring Boot BOM với BOM tùy ý

Nếu Boot đã quản lý version Spring Framework/Security, hãy ưu tiên dependency management mà dự án đang dùng. Thêm một BOM Spring Framework khác có thể ghi đè version do Boot chọn và tạo stack không được hỗ trợ.

Nếu cần override, phải có lý do, kiểm tra compatibility và integration test toàn bộ ứng dụng.

## 13. Spring Security là dependency tùy theo nhu cầu

Không phải mọi flow đều cần Spring Security. Nếu ứng dụng cần authentication/authorization, hãy khai báo các module Security thực sự dùng, ví dụ web/security config và test support.

Mẫu dependency chỉ để minh họa cấu trúc:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-config</artifactId>
</dependency>
~~~

Version phải được quản lý đồng bộ theo baseline Spring Security đã chọn. Một ứng dụng có thể cần thêm module khác tùy authentication provider, OAuth2 hoặc test; không khai báo toàn bộ Spring Security chỉ vì một flow có thẻ secured.

### 13.1. Dependency không bật bảo mật

Thêm `spring-security-web` và `spring-security-config` không tự tạo:

- Security filter chain.
- Authentication provider.
- Login page.
- CSRF policy.
- Method security.
- `SecurityFlowExecutionListener`.

Các thành phần này cần được cấu hình. Listener Web Flow nếu dùng cũng phải được đăng ký vào FlowExecutor theo cơ chế tương thích.

## 14. Dependency cho test và integration test

Một dự án Web Flow cần nhiều lớp test:

| Loại test | Dependency thường cần |
| --- | --- |
| Unit test service/action | JUnit hoặc test framework dự án chọn |
| Spring context test | `spring-test` |
| Spring MVC test | `spring-test` và test framework phù hợp |
| Security test | `spring-security-test` nếu dùng Spring Security |
| Database integration test | Driver/database test environment theo dự án |
| Test view/template | Thư viện view engine và test support tương ứng nếu cần |

Không nên đặt toàn bộ dependency test vào runtime. Maven dùng scope `test`; Gradle dùng `testImplementation` hoặc cấu hình test phù hợp.

### 14.1. Test dependency không thay thế kiểm thử runtime

Test có thể khởi động Spring context nhưng không đóng gói WAR giống production. Cần có kiểm tra artifact:

- Build WAR/JAR.
- Kiểm tra runtime dependency.
- Khởi động ứng dụng trong container/môi trường tương đương.
- Mở một flow mẫu.
- Gửi event qua nhiều request.
- Xác minh session, view, binding và service.

## 15. Chẩn đoán lỗi dependency phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | Thiếu artifact runtime hoặc scope sai | Dependency tree và nội dung WAR |
| `NoClassDefFoundError` | Class có lúc compile nhưng thiếu lúc chạy | Runtime classpath, packaging |
| `NoSuchMethodError` | Version API không tương thích | Căn chỉnh Spring Framework/SWF/Security |
| `NoSuchBeanDefinitionException` | Thiếu bean cấu hình, không nhất thiết thiếu dependency | ApplicationContext và bean registration |
| `No flow found with id ...` | FlowRegistry không nạp flow hoặc ID sai | Registry location/flow ID |
| HTTP 404 cho flow | MVC mapping/handler chưa đúng | FlowHandlerMapping/Adapter |
| `javax.servlet`/`jakarta.servlet` lỗi | Namespace/container không tương thích | JDK/framework/container baseline |
| Test pass nhưng WAR lỗi | Scope hoặc packaging khác test classpath | Inspect WAR, chạy integration |
| Version bị downgrade | BOM/constraint/transitive conflict | `dependency:tree` hoặc `dependencyInsight` |

### 15.1. NoSuchBeanDefinitionException không nhất thiết là lỗi Maven

Ví dụ bean `flowExecutor` không tồn tại. Có thể dependency đã có nhưng cấu hình chưa khai báo executor hoặc context không load file cấu hình. Đừng thêm lại `spring-webflow` nhiều lần để chữa lỗi thiếu bean.

### 15.2. No flow found không phải thiếu class

Nếu engine đã chạy nhưng không tìm thấy flow ID, kiểm tra:

- Flow ID trong registry.
- Location của flow definition.
- Pattern resource loader.
- Cấu hình registry.
- Flow ID được URL/handler yêu cầu.

Dependency tree không thể xác minh các thông tin này.

## 16. Thực hành kiểm tra dependency từ đầu đến cuối

Với một ứng dụng Maven:

1. Thêm `spring-webflow` version đã chọn.
2. Căn chỉnh Spring Framework bằng BOM/dependency management phù hợp.
3. Thêm `spring-webmvc` nếu ứng dụng dùng MVC.
4. Thêm Servlet API với scope phù hợp nếu cần compile trên WAR.
5. Thêm dependency test.
6. Chạy dependency tree và kiểm tra version.
7. Build test.
8. Đóng gói WAR và kiểm tra `WEB-INF/lib`.
9. Khởi động trong servlet container tương thích.
10. Kiểm tra một flow từ start đến end qua nhiều request.

Với Gradle, các bước tương tự:

1. Thêm dependency trong `dependencies`.
2. Import platform/BOM nếu cần.
3. Chọn configuration `implementation`, `compileOnly`/`providedCompile`, `testImplementation` đúng mục đích.
4. Chạy `dependencies` và `dependencyInsight`.
5. Chạy test.
6. Build WAR và kiểm tra nội dung.
7. Chạy integration test qua FlowExecutor/MVC.

### 16.1. Một ví dụ flow tối thiểu để kiểm tra runtime

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="start">

    <view-state id="start" view="demo/start">
        <transition on="next" to="finish"/>
    </view-state>

    <end-state id="finish" view="demo/finish"/>
</flow>
~~~

Đây là ví dụ định nghĩa flow tối thiểu. Để chạy được, vẫn cần registry, executor, MVC handler, view `demo/start` và `demo/finish`, cùng servlet environment phù hợp.

### 16.2. Kiểm tra hành vi chứ không chỉ khởi động

Một integration test nên chứng minh:

- Flow ID được resolve.
- Request đầu tiên khởi tạo execution.
- Event `next` tiếp tục đúng execution.
- Transition đến end-state.
- View được resolve.
- Không có class/method incompatibility khi thực thi.

Điều đó xác minh dependency và cấu hình runtime phối hợp đúng trong kịch bản thực.

## 17. Quản lý dependency theo môi trường và triển khai

Không nên dùng một tập dependency khác nhau tùy máy developer mà không kiểm soát. Dùng dependency management rõ ràng, lockfile/verification phù hợp với build tool và CI.

Các nguyên tắc:

- Version dependency production được pin hoặc quản lý tập trung.
- Không dùng version động như `2.+` cho dependency quan trọng trong build production.
- CI phải chạy cùng JDK baseline đã công bố.
- Artifact build được kiểm tra dependency và packaging.
- Thay version Web Flow phải chạy integration test toàn bộ flow.
- Security updates được đánh giá cùng compatibility thay vì nâng riêng một module.
- Repository/proxy nội bộ cần mirror đúng artifact và metadata.

### 17.1. Maven Enforcer và Gradle dependency locking

Maven có thể dùng Enforcer để kiểm tra Java/Maven version, dependency convergence và rule nội bộ. Gradle có thể dùng dependency locking để ghi nhận version đã resolve.

Các cơ chế này giúp build có thể tái lập hơn, nhưng không tự chứng minh version tương thích về mặt API. Vẫn cần test runtime.

### 17.2. Không đưa thông tin nhạy cảm vào build file

Dependency repository có thể cần credentials. Không commit mật khẩu/token vào `pom.xml`, `settings.gradle` hoặc `gradle.properties` trong repository. Dùng secret manager, biến môi trường hoặc cấu hình CI phù hợp.

## 18. Bài thực hành: thêm Spring Web Flow vào ứng dụng đặt lịch

Một dự án hiện có Spring MVC, chạy dưới dạng WAR. Nhóm muốn thêm flow đặt lịch nhiều bước và hỗ trợ kiểm thử.

**Yêu cầu:**

1. Xác định JDK, Spring Framework, Spring Security (nếu có), Servlet API và container hiện tại.
2. Chọn một version Spring Web Flow tương thích; ghi rõ lý do và nguồn version.
3. Thêm dependency `org.springframework.webflow:spring-webflow` vào Maven hoặc Gradle.
4. Quản lý Spring Framework version thống nhất bằng BOM/platform hoặc cơ chế hiện có của dự án.
5. Khai báo `spring-webmvc` trực tiếp nếu code dùng MVC API.
6. Chọn Servlet API đúng namespace và scope cho WAR; không đóng gói bản API của container vào WAR.
7. Thêm `spring-test` và Security test support nếu ứng dụng dùng Security.
8. Chạy dependency tree/dependencyInsight và giải thích từng dependency quan trọng.
9. Kiểm tra artifact WAR để phát hiện duplicate Spring modules hoặc test dependencies.
10. Cấu hình FlowRegistry, FlowExecutor và Spring MVC integration.
11. Tạo flow tối thiểu `start → finish`, kiểm tra qua hai request.
12. Viết integration test chứng minh dependency, wiring và view đều hoạt động.

**Bảng ghi nhận kết quả:**

| Hạng mục | Giá trị dự án |
| --- | --- |
| Build tool | Maven / Gradle |
| JDK | Version đã chọn |
| Spring Framework | Version/BOM |
| Spring Web Flow | Artifact + version |
| Spring Security | Version hoặc không sử dụng |
| Servlet namespace | `javax` / `jakarta` |
| Container | Tên và version |
| WAR/JAR | Kiểu artifact |
| Dependency conflict | Kết quả tree/insight |
| Flow integration test | Pass/Fail |

**Tiêu chí đạt:** dependency resolve nhất quán, không có module Spring bị lệch version ngoài chủ đích, Servlet API phù hợp container, WAR không chứa thư viện test hoặc Servlet API sai scope, FlowExecutor khởi động và flow mẫu đi qua được các state.

## 19. Tổng kết và câu hỏi tự kiểm tra

Để dùng Spring Web Flow, dự án thường khai báo artifact `org.springframework.webflow:spring-webflow` bằng Maven hoặc Gradle. Việc chọn version phải dựa trên **tổ hợp tương thích** của Spring Framework, Spring Security, JDK, Servlet API và container. Dùng BOM/platform để căn chỉnh các module có cùng phạm vi quản lý; quản lý version Web Flow riêng nếu BOM không bao gồm artifact đó.

Scope phải đúng: dependency ứng dụng ở runtime, Servlet API do container cung cấp thường không đóng gói vào WAR, dependency test chỉ dùng ở test classpath. Dependency tree và dependencyInsight giúp xem version đã resolve, nhưng **không chứng minh flow đã được cấu hình runtime**. Muốn flow chạy cần FlowRegistry, FlowExecutor, MVC integration, view và các bean tương ứng.

**Câu hỏi tự kiểm tra:**

1. Tọa độ Maven của Spring Web Flow gồm groupId và artifactId nào?
2. Vì sao version `2.5.1.RELEASE` trong ví dụ không nên được hiểu là version mặc định cho mọi dự án?
3. BOM quản lý version khác gì với việc tự thêm dependency?
4. Vì sao Spring Framework BOM không mặc nhiên quản lý Spring Web Flow?
5. Khi nào cần khai báo `spring-webmvc` trực tiếp?
6. Vì sao Servlet API trong WAR thường có scope `provided` hoặc cấu hình tương đương?
7. Sự khác biệt giữa `javax.servlet` và `jakarta.servlet` ảnh hưởng dependency ra sao?
8. `dependency:tree` và `dependencyInsight` giúp chẩn đoán những vấn đề nào?
9. Vì sao có `spring-webflow` trên classpath vẫn có thể nhận HTTP 404 hoặc lỗi không tìm thấy flow?
10. Cần những integration test nào để chứng minh dependency, FlowExecutor và Spring MVC đã hoạt động cùng nhau?
