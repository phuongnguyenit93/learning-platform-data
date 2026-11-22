# Thư viện do môi trường chạy cung cấp và phụ thuộc không đóng gói kèm

Một ứng dụng Java có thể sử dụng những thư viện mà chính ứng dụng không mang theo trong artifact phát hành. Ví dụ, ứng dụng web có thể gọi Servlet API vì servlet container cung cấp API và phần triển khai lúc chạy. Một ứng dụng cũng có thể được triển khai cùng một thư mục `lib/` bên ngoài, hoặc chạy trong một môi trường đã cài sẵn các thư viện dùng chung.

Khi build, ta vẫn cần khai báo những thư viện đó để compiler hiểu kiểu dữ liệu và để kiểm thử có thể chạy. Tuy nhiên, ta cần chỉ rõ dependency nào được cung cấp bởi môi trường triển khai, dependency nào phải được đóng gói hoặc phân phối cùng ứng dụng. Nếu cấu hình sai, ứng dụng có thể compile thành công nhưng lỗi khi khởi chạy do thiếu lớp, hoặc gặp xung đột phiên bản với thư viện do server cung cấp.

Bài này giải thích cách khai báo dependency do runtime cung cấp trong Maven và Gradle, sự khác nhau giữa compile classpath, runtime classpath và artifact đóng gói, cùng cách kiểm tra môi trường triển khai.

## 1. Dependency do môi trường chạy cung cấp là gì?

Một dependency do môi trường chạy cung cấp là thư viện mà ứng dụng cần sử dụng nhưng không chịu trách nhiệm phân phối bản sao của thư viện đó trong gói phát hành. Thay vào đó, môi trường triển khai phải cung cấp thư viện tương thích khi ứng dụng chạy.

Ví dụ phổ biến:

- Servlet API được cung cấp bởi servlet container như Tomcat hoặc Jetty.
- Một số API nền tảng được cung cấp bởi JDK/JVM.
- API và thư viện nền tảng do application server cung cấp.
- Các thư viện dùng chung được cài đặt trong môi trường runtime theo quy ước vận hành của tổ chức.
- Một số thư viện native hoặc driver được cài riêng trên máy/container và được runtime nạp từ bên ngoài.

Ứng dụng có thể cần dependency ở thời điểm biên dịch để gọi interface, class hoặc annotation. Nhưng khi triển khai, runtime đã có bản triển khai phù hợp nên không cần đóng gói thêm bản sao.

Ví dụ một ứng dụng web có thể biên dịch lớp sau:

```java
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        response.setContentType("text/plain");
        response.getWriter().println("OK");
    }
}
```

Compiler cần tìm thấy Servlet API để hiểu `HttpServlet`, `HttpServletRequest` và `HttpServletResponse`. Khi ứng dụng được triển khai vào một servlet container tương thích, container cung cấp API và phần triển khai cần thiết. Gói WAR thông thường không nên chứa một bản Servlet API cạnh tranh với bản do container quản lý.

## 2. Ba khái niệm cần tách biệt

Khi nói một dependency “không đóng gói”, cần phân biệt ba câu hỏi:

1. **Compiler có cần dependency không?** Nếu mã nguồn tham chiếu kiểu trong thư viện, dependency cần có trên compile classpath.
2. **Ứng dụng có cần dependency khi chạy không?** Nếu bytecode cần nạp lớp hoặc gọi API đó, runtime phải cung cấp lớp tương ứng trên classpath/module path hoặc qua classloader của container.
3. **Artifact phát hành có chứa dependency không?** Điều này phụ thuộc cấu hình dependency và cách đóng gói của build tool/plugin.

Ba câu hỏi này liên quan nhưng không đồng nghĩa. Một dependency có thể cần lúc compile và runtime nhưng được cung cấp bởi server, nên không được đóng gói vào WAR. Ngược lại, một thư viện có thể được dùng lúc compile và được đóng gói vào một fat JAR. Cũng có trường hợp dependency chỉ cần ở compile time, chẳng hạn một số annotation processor hoặc thư viện sinh mã, và không cần khi ứng dụng chạy.

| Loại nhu cầu | Compile classpath | Runtime classpath của ứng dụng | Đóng gói cùng artifact |
|---|---:|---:|---:|
| Thư viện ứng dụng tự phân phối | Có nếu mã nguồn cần | Có | Thường có trong fat JAR/WAR hoặc được phân phối riêng |
| API do container cung cấp | Có | Container phải cung cấp | Thường không đưa vào WAR |
| Dependency chỉ dùng khi compile | Có | Không | Không |
| Dependency chỉ dùng khi chạy, không được mã nguồn tham chiếu trực tiếp | Không nhất thiết | Có | Tùy cách đóng gói/phân phối |
| Dependency kiểm thử | Có trong test compile nếu test cần | Có trong test runtime | Không nằm trong artifact ứng dụng thông thường |

Lưu ý: “runtime classpath” ở bảng là classpath mà ứng dụng cần trong môi trường chạy. Với ứng dụng server, một số lớp có thể được cung cấp qua classloader hoặc module của container thay vì nằm trong classpath do ứng dụng tự thiết lập.

## 3. Maven: scope `provided`

Maven có scope `provided` dành cho dependency cần trong quá trình biên dịch và kiểm thử, nhưng được kỳ vọng sẽ có sẵn ở môi trường chạy. Dependency scope `provided` không được đưa vào runtime classpath thông thường của project và không được truyền như dependency bắc cầu theo cách của scope `compile`.

Ví dụ khai báo Servlet API:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>6.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Với khai báo này:

- Mã nguồn chính có thể import và compile với các kiểu Servlet API.
- Mã kiểm thử có thể sử dụng dependency này trên test classpath.
- Dependency không được đưa vào runtime classpath thông thường của project như một dependency `compile` hoặc `runtime`.
- Với Maven WAR Plugin theo cấu hình thông thường, dependency `provided` không được đóng gói vào `WEB-INF/lib`; servlet container phải cung cấp API tương thích.

`provided` phù hợp khi môi trường triển khai có trách nhiệm cung cấp dependency. Không nên dùng nó chỉ để giảm kích thước JAR nếu ứng dụng không có cơ chế nào khác bảo đảm thư viện sẽ tồn tại lúc chạy.

### 3.1. So sánh các Maven scope thường gặp

| Scope | Compile | Runtime | Test | Truyền bắc cầu | Ý nghĩa thường dùng |
|---|---:|---:|---:|---:|---|
| `compile` | Có | Có | Có | Có | Dependency mặc định, cần cho ứng dụng và người dùng dependency |
| `provided` | Có | Không trong runtime classpath thông thường | Có | Không | API do JDK/container/môi trường triển khai cung cấp |
| `runtime` | Không cho compile main thông thường | Có | Có | Có | Thư viện cần lúc chạy nhưng mã nguồn không cần tham chiếu trực tiếp |
| `test` | Không cho compile main | Không cho runtime ứng dụng | Có | Không | Framework và tiện ích chỉ dùng khi kiểm thử |
| `system` | Có | Có theo cách cấu hình | Có | Không | JAR cục bộ chỉ định qua `systemPath`; nên tránh trong dự án thông thường |
| `import` | Không phải scope dependency thường | Không | Không | Không | Import BOM trong `dependencyManagement` |

Bảng mô tả hành vi scope Maven ở mức khái quát. Plugin đóng gói cụ thể có thể có quy tắc riêng, và một số loại packaging như WAR xử lý dependency theo quy ước của plugin tương ứng.

### 3.2. Vì sao `provided` không truyền bắc cầu?

Giả sử thư viện `web-module` khai báo Servlet API với scope `provided`. Một ứng dụng khác phụ thuộc vào `web-module` không nên mặc định nhận Servlet API như một dependency runtime bắc cầu, vì thư viện web được thiết kế để chạy trong môi trường đã cung cấp API đó.

Điều này buộc ứng dụng triển khai phải hiểu môi trường mục tiêu và khai báo dependency cần thiết cho compile/test của chính nó nếu cần. Đây là hành vi có chủ đích: dependency do container cung cấp không nên bị kéo vào mọi consumer như một thư viện ứng dụng thông thường.

Nếu một thư viện công khai API có chữ ký phương thức sử dụng kiểu từ một dependency, cần cân nhắc kỹ cách khai báo và tài liệu hóa yêu cầu runtime/compile của consumer. Scope và metadata dependency phải phản ánh hợp đồng thực tế của thư viện.

### 3.3. `provided` trong WAR

Với web application, Maven WAR Plugin đóng gói các dependency theo quy tắc WAR. Dependency scope `provided` thường không được đưa vào `WEB-INF/lib`, bởi container đã cung cấp các API như Servlet.

Một WAR thông thường có cấu trúc gần như:

```text
order-web.war
├── WEB-INF/
│   ├── classes/
│   │   └── vn/acme/web/HealthServlet.class
│   ├── lib/
│   │   ├── application-library.jar
│   │   └── logging-library.jar
│   └── web.xml                 # nếu dự án dùng deployment descriptor
└── ...
```

Servlet API không nằm trong `WEB-INF/lib` khi được khai báo `provided`; container cung cấp các lớp API và runtime tương ứng. Các dependency ứng dụng thông thường vẫn được đóng gói theo cấu hình WAR.

Đừng nhầm `provided` với việc dependency không tồn tại ở bất kỳ đâu. Nó phải có mặt trong môi trường triển khai, thường thông qua container/server. Nếu triển khai WAR vào môi trường không cung cấp API tương ứng, ứng dụng có thể lỗi khi nạp lớp hoặc khi khởi tạo servlet.

## 4. Gradle: `compileOnly` và cấu hình dành cho runtime do container cung cấp

Với Gradle Java plugin, `compileOnly` khai báo dependency cần cho compile nhưng không được đưa vào runtime classpath của ứng dụng. Đây là cấu hình thường dùng cho API được môi trường runtime cung cấp hoặc thư viện chỉ cần lúc biên dịch.

Ví dụ Kotlin DSL:

```kotlin
plugins {
    java
    war
}

repositories {
    mavenCentral()
}

dependencies {
    compileOnly("jakarta.servlet:jakarta.servlet-api:6.0.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
}

tasks.test {
    useJUnitPlatform()
}
```

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'war'
}

repositories {
    mavenCentral()
}

dependencies {
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}

test {
    useJUnitPlatform()
}
```

Ở đây Servlet API có mặt khi compile mã nguồn. Jackson được khai báo `implementation` vì ứng dụng cần thư viện này khi chạy. Tuy nhiên, cần nhớ Java plugin tạo JAR thông thường không tự nhúng mọi dependency `implementation` vào JAR; dependency runtime vẫn cần được phân phối theo cách phù hợp. Nếu dùng WAR plugin, các dependency runtime thông thường được đưa vào `WEB-INF/lib`, còn `compileOnly` không được đóng gói.

### 4.1. So sánh các Gradle configuration

| Configuration | Compile main | Runtime ứng dụng | Mục đích |
|---|---:|---:|---|
| `implementation` | Có | Có trên runtime classpath | Dependency nội bộ của implementation và runtime |
| `api` (Java Library plugin) | Có và được công bố cho compile consumer | Có theo dependency graph runtime | Dependency là một phần API công khai của thư viện |
| `compileOnly` | Có | Không | API/thư viện chỉ cần compile hoặc được runtime cung cấp |
| `compileOnlyApi` (Java Library plugin) | Có; được công bố cho compile consumer | Không được đưa vào runtime graph chỉ vì cấu hình này | Dependency compile-only xuất hiện trong public API cần consumer biết khi compile |
| `runtimeOnly` | Không cho compile main thông thường | Có | Driver, provider hoặc thư viện chỉ cần lúc chạy |
| `testImplementation` | Không cho compile main | Không cho runtime ứng dụng | Dependency cho mã kiểm thử |
| `testRuntimeOnly` | Không cho compile test | Có cho test runtime | Dependency chỉ cần khi chạy test |

Tên và quan hệ configuration có thể mở rộng theo plugin. Bảng này mô tả các configuration tiêu biểu của Gradle Java/Java Library plugin.

### 4.2. `compileOnly` không thay thế `runtimeOnly`

Hai cấu hình này giải quyết hai nhu cầu khác nhau:

- `compileOnly`: mã nguồn cần thư viện để biên dịch, nhưng ứng dụng không yêu cầu dependency đó từ runtime classpath do Gradle tạo.
- `runtimeOnly`: mã nguồn không cần dependency đó để biên dịch, nhưng runtime cần nó.

Ví dụ JDBC driver:

```kotlin
dependencies {
    implementation("org.springframework:spring-jdbc:6.1.14")
    runtimeOnly("org.postgresql:postgresql:42.7.4")
}
```

Driver PostgreSQL có thể được nạp qua cơ chế JDBC service provider lúc chạy, nên mã nguồn không nhất thiết tham chiếu trực tiếp class của driver. Tuy nhiên, driver phải có trên runtime classpath hoặc được cung cấp bởi môi trường. Đây là trường hợp khác với Servlet API do container cung cấp.

### 4.3. `providedCompile` và `providedRuntime` của Gradle WAR plugin

Khi dùng Gradle WAR plugin, có thể gặp các configuration `providedCompile` và `providedRuntime`:

- `providedCompile`: dependency cần để biên dịch web application nhưng được container cung cấp, nên không đóng gói vào WAR.
- `providedRuntime`: dependency cần trong runtime của ứng dụng web nhưng được môi trường triển khai cung cấp, nên cũng không đóng gói vào WAR.

Ví dụ:

```kotlin
dependencies {
    providedCompile("jakarta.servlet:jakarta.servlet-api:6.0.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
    providedRuntime("org.example:container-integration-api:1.0.0")
}
```

Tên configuration và hành vi cụ thể cần được đối chiếu với phiên bản Gradle WAR plugin của dự án. Với dự án Java không tạo WAR, `compileOnly` thường là cấu hình phù hợp để mô tả dependency chỉ cần compile.

## 5. Dependency không đóng gói không đồng nghĩa với JAR thường tự chứa dependency

Một nhầm lẫn quan trọng là nghĩ rằng chỉ dependency `provided` hoặc `compileOnly` mới không được nhúng vào JAR. Trên thực tế, JAR tiêu chuẩn được tạo bởi Java plugin hoặc Maven JAR Plugin thường chỉ chứa lớp và resource của chính project; các dependency thường không được nhúng vào trong JAR đó.

Ví dụ một project khai báo:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.1-jre")
}
```

Gradle đưa Guava vào runtime classpath của project. Nhưng task `jar` tiêu chuẩn không tự chép toàn bộ Guava vào trong JAR. Khi triển khai, cần phân phối Guava bằng một trong các cách:

- Đặt dependency JAR trong thư mục `lib/` và cấu hình runtime classpath.
- Dùng script/launcher hoặc cơ chế triển khai để dựng classpath.
- Đóng gói ứng dụng thành fat JAR/uber JAR bằng plugin phù hợp.
- Dùng framework packaging tạo executable archive có cơ chế nạp dependency riêng.
- Triển khai lên môi trường có quy ước cung cấp dependency.

Điểm khác nhau là:

- **Dependency không được đưa vào runtime classpath của project**: ví dụ Maven `provided`, Gradle `compileOnly`.
- **Dependency có trong runtime classpath nhưng không nằm bên trong JAR tiêu chuẩn**: ví dụ Gradle `implementation` hoặc Maven `compile` khi tạo plain JAR.
- **Dependency được nhúng/đóng gói cùng ứng dụng**: ví dụ fat JAR, Spring Boot executable JAR hoặc WAR có dependency trong `WEB-INF/lib`.

Do đó, khi kiểm tra artifact, phải xem cả dependency configuration và packaging plugin/task được sử dụng.

## 6. Những cách phân phối dependency bên ngoài artifact

Nếu dependency không nằm trong artifact chính, hệ thống triển khai cần có kế hoạch cung cấp nó.

### 6.1. Thư mục `lib/` và classpath

Một cách truyền thống là phân phối ứng dụng cùng các JAR phụ thuộc:

```text
distribution/
├── app.jar
├── lib/
│   ├── commons-lang3.jar
│   ├── jackson-core.jar
│   └── jackson-databind.jar
└── bin/
    └── run.sh
```

Launcher có thể thiết lập classpath:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Trên Windows, ký tự phân tách classpath là dấu chấm phẩy:

```bat
java -cp "app.jar;lib/*" com.example.Main
```

JVM tìm lớp trong các vị trí được khai báo. Nếu thiếu một dependency hoặc có version không tương thích, ứng dụng có thể gặp `ClassNotFoundException`, `NoClassDefFoundError` hoặc lỗi liên kết như `NoSuchMethodError`.

### 6.2. Manifest `Class-Path`

JAR có thể khai báo `Class-Path` trong manifest để tham chiếu đến các JAR bên ngoài. Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/commons-lang3.jar lib/jackson-databind.jar
```

Các đường dẫn trong `Class-Path` được diễn giải tương đối với vị trí JAR chứa manifest. Những dependency được tham chiếu vẫn phải được phân phối ở vị trí tương ứng. Manifest không nhúng các thư viện đó vào JAR.

### 6.3. Fat JAR hoặc executable archive

Fat JAR (còn gọi là uber JAR trong một số công cụ) gom ứng dụng và các dependency runtime vào một artifact hoặc tổ chức chúng trong một cấu trúc archive đặc biệt.

Một số cách tạo:

- Maven Shade Plugin hoặc Maven Assembly Plugin.
- Gradle Shadow Plugin.
- Spring Boot `bootJar`.

Ví dụ với Spring Boot, executable JAR thường chứa dependency runtime trong cấu trúc archive riêng và dùng launcher của Spring Boot để nạp chúng. Nó không giống một JAR Java thuần chỉ có các `.class` ở root.

Fat JAR thuận tiện khi triển khai vì giảm số file cần phân phối. Tuy nhiên, việc gom thư viện có thể tạo vấn đề về duplicate resource, service descriptor, chữ ký JAR, license, classloader hoặc thư viện native. Cần dùng plugin và cấu hình phù hợp, đồng thời kiểm tra artifact cuối cùng.

### 6.4. Runtime do nền tảng cung cấp

Trong môi trường server/container, nền tảng có thể cung cấp API hoặc thư viện dùng chung. Ứng dụng chỉ đóng gói dependency riêng của nó và dựa vào container cho phần API đã được cung cấp.

Ví dụ:

```text
Servlet container
├── Servlet API / container implementation
├── Container classloader
└── Application deployment
    └── order-web.war
        ├── WEB-INF/classes/
        └── WEB-INF/lib/
            ├── application-library.jar
            └── logging-library.jar
```

Trong trường hợp này, Servlet API không cần được copy vào `WEB-INF/lib`. Nhưng container phải thực sự tương thích với API mà ứng dụng đã compile.

## 7. Chọn đúng scope theo môi trường triển khai

Quyết định dùng `provided` hoặc `compileOnly` phải dựa trên hợp đồng runtime:

1. Xác định ai chịu trách nhiệm cung cấp dependency: ứng dụng, container, JDK hay một thành phần hạ tầng khác.
2. Xác định dependency cần ở compile, test và runtime nào.
3. Xác định packaging plugin có đưa dependency vào artifact hay không.
4. Xác nhận môi trường triển khai có phiên bản tương thích.
5. Kiểm tra ứng dụng khi chạy trong môi trường thực tế hoặc môi trường mô phỏng tương đương.

Ví dụ servlet API:

| Thành phần | Trách nhiệm |
|---|---|
| Build | Có Servlet API trên compile classpath |
| Unit/integration test | Cần test runtime phù hợp nếu test khởi tạo servlet/container API |
| WAR | Không đóng gói Servlet API nếu container cung cấp |
| Servlet container | Cung cấp API và implementation tương thích |
| Deployment | Đảm bảo container hỗ trợ đúng phiên bản Jakarta Servlet mà ứng dụng yêu cầu |

Đừng chỉ nhìn version dependency trong POM/build file. Hãy kiểm tra phiên bản nền tảng thực tế. Ví dụ, một ứng dụng compile với Jakarta Servlet API 6 cần một container hỗ trợ phiên bản Servlet tương ứng. Nếu server cũ chỉ cung cấp Servlet API đời trước, việc khai báo `provided` không làm server tự nâng cấp.

## 8. Phân biệt API do JDK cung cấp và thư viện ngoài

Các module nền tảng Java được cung cấp bởi JDK/runtime phù hợp không cần khai báo như thư viện Maven thông thường trong mọi dự án. Ví dụ `java.base`, `java.logging` và nhiều API chuẩn thuộc Java Platform.

Tuy nhiên, không phải mọi package từng xuất hiện trong JDK đều còn thuộc JDK ở mọi phiên bản. Một số module Java EE/CORBA đã bị loại khỏi JDK từ các phiên bản Java hiện đại; ứng dụng có thể cần khai báo dependency riêng cho các API đó.

Ví dụ, trước đây một số dự án dựa vào `javax.xml.bind` từ JDK cũ. Với JDK mới, JAXB không còn được cung cấp theo cách cũ và project cần khai báo API/runtime implementation tương ứng nếu sử dụng.

Vì vậy:

- Kiểm tra API thuộc Java SE/JDK của phiên bản mục tiêu hay không.
- Kiểm tra module system nếu dự án dùng `module-info.java`.
- Không giả định một package có sẵn chỉ vì nó từng có trên JDK của máy lập trình viên.
- Với API ngoài JDK, khai báo dependency và xác định rõ ai cung cấp runtime implementation.

## 9. Rủi ro khi runtime cung cấp sai hoặc thiếu dependency

Compile thành công chỉ chứng minh compiler tìm thấy các kiểu cần thiết trong compile classpath. Nó không chứng minh môi trường triển khai có thư viện phù hợp.

Các lỗi thường gặp:

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassNotFoundException` | Classloader không tìm thấy lớp được yêu cầu | Kiểm tra classpath, thư mục `lib/`, container và packaging |
| `NoClassDefFoundError` | Lớp cần thiết không có lúc runtime hoặc không khởi tạo được do lỗi trước đó | Xem nguyên nhân gốc trong stack trace, kiểm tra dependency runtime |
| `NoSuchMethodError` | Runtime nạp phiên bản class không có method mà code đã compile dựa vào | Đồng bộ version compile/runtime, kiểm tra classloader và dependency conflict |
| `NoSuchFieldError` | Runtime class khác version so với compile time | Kiểm tra artifact thực tế được nạp |
| `AbstractMethodError` | Implementation runtime không khớp interface/abstract class mà code kỳ vọng | Kiểm tra phiên bản API và implementation |
| `LinkageError` | Xung đột hoặc không tương thích khi liên kết class | Xem classloader, duplicate class và version |
| `UnsupportedClassVersionError` | Runtime Java cũ hơn bytecode | Dùng runtime phù hợp hoặc compile với Java target thấp hơn |

Một nguyên nhân phổ biến là container cung cấp một phiên bản API khác với phiên bản đã dùng khi biên dịch. Một nguyên nhân khác là ứng dụng vô tình đóng gói bản API riêng, khiến classloader nạp lớp từ nguồn không mong muốn.

## 10. Kiểm tra dependency có được đóng gói hay không

Không nên chỉ dựa vào tên scope. Hãy kiểm tra artifact cuối cùng và runtime classpath.

### 10.1. Kiểm tra Maven

Xem dependency tree:

```bash
./mvnw dependency:tree
```

Xem classpath runtime mà Maven phân giải:

```bash
./mvnw dependency:build-classpath -Dmdep.outputFile=runtime-classpath.txt
```

Lệnh trên cần Maven Dependency Plugin phù hợp và có thể cần cấu hình classpath scope nếu muốn lấy phạm vi khác. Để kiểm tra WAR, mở archive như ZIP và xem `WEB-INF/lib/`:

```bash
jar --list --file target/order-web.war
```

Nếu Servlet API được đánh dấu `provided`, thông thường không nên thấy `jakarta.servlet-api-*.jar` trong `WEB-INF/lib` của WAR được tạo theo cấu hình chuẩn.

### 10.2. Kiểm tra Gradle

Xem dependency của compile/runtime configuration:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Tìm lý do một dependency xuất hiện trong runtime graph:

```bash
./gradlew dependencyInsight \
    --dependency jakarta.servlet-api \
    --configuration runtimeClasspath
```

Kiểm tra nội dung WAR:

```bash
jar --list --file build/libs/order-web.war
```

Với Gradle Java plugin và WAR plugin, hãy đối chiếu cấu hình `compileOnly`, `providedCompile` hoặc `providedRuntime` với cấu trúc artifact thực tế. Với JAR thường, task `jar` không tự đóng gói mọi dependency runtime; hãy kiểm tra launcher hoặc packaging plugin nếu cần phân phối dependency ngoài JAR.

### 10.3. Kiểm tra class thực sự được nạp

Khi nghi ngờ runtime nạp nhầm bản thư viện, có thể xem nguồn nạp class. Với Java hiện đại, tùy chọn sau giúp ghi log class loading:

```bash
java -Xlog:class+load=info -jar app.jar
```

Log có thể cho biết lớp được nạp từ đâu. Trong môi trường container, cách thu log có thể cần cấu hình qua startup options của server. Đây là bằng chứng hữu ích khi có nhiều bản cùng tên trong classpath hoặc nhiều classloader.

## 11. Kiểm thử khi dependency được cung cấp bên ngoài

Một unit test có thể chạy thành công trên máy lập trình viên vì IDE hoặc test runner vô tình đưa dependency vào classpath, nhưng artifact triển khai lại thiếu runtime provider. Cần kiểm tra test và deployment theo đúng môi trường mục tiêu.

Một số cách tiếp cận:

- Dùng test dependency riêng cho test runtime nếu test cần framework hoặc implementation không nằm trong production artifact.
- Dùng embedded container hoặc integration test để xác nhận API/behavior trong môi trường gần production.
- Chạy kiểm thử smoke test sau khi triển khai WAR lên đúng loại container.
- Xác nhận phiên bản container và API tương thích với compile dependency.
- Kiểm tra artifact đã đóng gói, tránh dựa vào classpath của IDE.

Ví dụ, Servlet API `provided` cho compile không tự tạo một servlet container để unit test. Nếu test cần khởi chạy servlet lifecycle, project phải cung cấp test runtime phù hợp hoặc dùng container test. Phần test runtime đó không nhất thiết được đưa vào WAR production.

## 12. Tránh đóng gói trùng thư viện nền tảng

Đưa một dependency do container cung cấp vào WAR có thể tạo xung đột classloader. Ví dụ, container đã có Servlet API nhưng WAR lại mang thêm một bản API khác. Hệ quả phụ thuộc classloader policy của server: có thể dùng lớp của container, dùng lớp của ứng dụng hoặc phát sinh lỗi kiểu dữ liệu không tương thích giữa các classloader.

Các quy tắc thực hành:

- Đọc tài liệu của container để biết API nào do nó cung cấp.
- Đánh dấu API container cung cấp bằng scope/configuration tương ứng.
- Không đóng gói implementation nội bộ của server trừ khi tài liệu triển khai yêu cầu rõ ràng.
- Giữ các thư viện ứng dụng riêng trong WAR/JAR hoặc phân phối theo cơ chế đã chọn.
- Kiểm tra dependency tree và nội dung archive sau khi build.
- Không dùng `provided` để che giấu một dependency runtime mà môi trường thực tế không cung cấp.

## 13. Các cấu hình dễ nhầm với dependency do runtime cung cấp

### `optional` trong Maven

`optional` điều khiển việc dependency có được truyền tiếp đến consumer như dependency bắc cầu hay không. Nó không có nghĩa dependency được container cung cấp và cũng không tự động loại dependency khỏi mọi artifact.

Ví dụ:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>metrics-adapter</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Consumer không tự động nhận dependency optional như dependency bắc cầu. Nếu ứng dụng cần adapter đó, nó phải khai báo rõ. `optional` là thông tin về dependency propagation, còn `provided` là scope thể hiện môi trường runtime chịu trách nhiệm cung cấp.

### `exclusions` trong Maven

`exclusions` loại bỏ một dependency bắc cầu khỏi dependency graph của một dependency cụ thể. Nó không cung cấp thư viện thay thế. Nếu loại bỏ một thư viện mà ứng dụng vẫn cần, phải bảo đảm một dependency khác hoặc runtime environment cung cấp lớp tương ứng.

### `runtimeOnly` trong Gradle và scope `runtime` trong Maven

Hai cấu hình này mô tả dependency cần lúc chạy nhưng không cần trên compile classpath chính. Chúng không có nghĩa môi trường ngoài đã cung cấp dependency. Nếu dùng chúng, ứng dụng hoặc gói phân phối phải có trách nhiệm đưa dependency vào runtime classpath.

### `system` scope trong Maven

`system` yêu cầu một JAR ở đường dẫn cục bộ được chỉ định bằng `systemPath`. Nó thường làm build khó tái tạo giữa các máy và không được khuyến nghị cho dependency thông thường. Nên dùng repository Maven hoặc cơ chế phân phối artifact rõ ràng thay vì phụ thuộc đường dẫn cục bộ.

## 14. Ví dụ hoàn chỉnh: WAR dựa vào Servlet container

Giả sử nhóm phát triển `order-web` và triển khai vào một servlet container tương thích Jakarta Servlet 6. POM có thể khai báo:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.acme.order</groupId>
    <artifactId>order-web</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <dependencies>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>
</project>
```

Trong ví dụ này:

1. Servlet API có mặt để compile và test.
2. WAR plugin loại Servlet API khỏi `WEB-INF/lib` theo quy tắc provided.
3. Jackson là thư viện ứng dụng, nên được đưa vào WAR theo cấu hình dependency/packaging thông thường.
4. Container triển khai phải cung cấp Servlet API tương thích.
5. Khi chạy, container nạp ứng dụng và cung cấp các lớp Servlet cần thiết.

Nếu nhóm chuyển ứng dụng sang một runtime không cung cấp Servlet API, cần thay đổi kiến trúc hoặc packaging để runtime đó có đủ API/implementation. Chỉ đổi scope trong POM mà không chuẩn bị runtime tương ứng sẽ không giải quyết được vấn đề.

## 15. Quy trình quyết định scope và packaging

Khi thêm một dependency mới, có thể đi theo các bước sau:

1. Mã nguồn chính có import hoặc tham chiếu kiểu của dependency không? Nếu có, cần dependency trên compile classpath.
2. Ứng dụng có cần lớp đó khi chạy không? Nếu không, có thể là compile-only hoặc annotation processor; nếu có, xác định ai cung cấp.
3. Môi trường server/container có cam kết cung cấp đúng API và version không? Nếu có, cân nhắc `provided`/`compileOnly` hoặc configuration tương ứng.
4. Nếu ứng dụng tự chịu trách nhiệm, chọn scope runtime phù hợp và bảo đảm dependency được phân phối cùng ứng dụng.
5. Kiểm tra packaging plugin: plain JAR, WAR, fat JAR và executable archive có quy tắc khác nhau.
6. Kiểm tra artifact và chạy smoke/integration test trong môi trường gần production.

Sơ đồ quyết định rút gọn:

```text
Ứng dụng có cần dependency lúc chạy?
          |
      +---+---+
      |       |
     Không    Có
      |       |
 compile-only | Runtime có cung cấp dependency?
              |
          +---+---+
          |       |
         Có      Không
          |       |
      provided   Ứng dụng phải phân phối dependency
      /compileOnly  qua runtime classpath hoặc packaging
```

Đây là hướng dẫn lựa chọn ban đầu. Với thư viện được consumer sử dụng, API công khai, annotation processor, native library và container plugin, cần xem thêm quy tắc riêng của build tool và runtime.

## 16. Những điều cần ghi nhớ

- Dependency do runtime cung cấp vẫn có thể cần trên compile classpath để compiler hiểu API.
- Maven `provided` dùng cho dependency có trên compile/test nhưng được môi trường runtime cung cấp; scope này không truyền bắc cầu như `compile`.
- Gradle `compileOnly` đưa dependency vào compile classpath nhưng không đưa vào runtime classpath của ứng dụng.
- Gradle WAR plugin có các configuration `providedCompile` và `providedRuntime` cho dependency do container cung cấp.
- `implementation` hoặc Maven `compile` không có nghĩa dependency tự được nhúng vào plain JAR; packaging plugin quyết định nội dung archive.
- `runtimeOnly`/Maven `runtime` mô tả dependency cần khi chạy, nhưng ứng dụng vẫn phải phân phối nó nếu môi trường không cung cấp.
- `optional` và `exclusions` điều khiển dependency propagation/graph, không đồng nghĩa với `provided`.
- Kiểm tra dependency tree, runtime classpath và nội dung JAR/WAR để xác nhận dependency có được đóng gói hay không.
- Môi trường triển khai phải cung cấp đúng API/version; compile thành công không bảo đảm runtime tương thích.

Khi chọn scope cho thư viện, hãy bắt đầu từ trách nhiệm cung cấp dependency ở môi trường chạy. Nếu container chịu trách nhiệm, khai báo rõ dependency compile-only/provided và xác nhận container có phiên bản tương thích. Nếu ứng dụng chịu trách nhiệm, hãy bảo đảm dependency có mặt trong runtime classpath hoặc gói phát hành. Sau cùng, kiểm tra archive thực tế và chạy thử trong môi trường triển khai dự kiến để tránh lỗi thiếu lớp hoặc xung đột phiên bản.
