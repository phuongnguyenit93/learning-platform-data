# Phân biệt lỗi biên dịch, lỗi dependency và lỗi khởi động

Khi làm **dự án Spring Boot đầu tiên**, ba câu “project không build được”, “thiếu thư viện” và “ứng dụng không chạy được” thường bị gọi chung là *lỗi Spring Boot*. Thực tế, chúng có thể xảy ra ở các giai đoạn khác nhau, do những thành phần khác nhau gây ra và cần cách xử lý khác nhau.

Bài học này giúp bạn nhìn vào **lệnh đang chạy**, **giai đoạn thất bại** và **dòng lỗi đầu tiên có ý nghĩa**, từ đó phân biệt:

1. **Lỗi biên dịch** (*compile error*): mã nguồn không thể được chuyển thành bytecode hợp lệ.
2. **Lỗi dependency** (*dependency problem*): thư viện cần dùng không được tìm thấy, tải xuống, chọn đúng phiên bản hoặc đưa vào classpath thích hợp.
3. **Lỗi khởi động** (*startup error*): mã đã được biên dịch đủ để bắt đầu chạy, nhưng JVM hoặc Spring Boot không thể hoàn tất quá trình khởi tạo ứng dụng.

Ba nhóm có liên hệ với nhau. Một dependency thiếu có thể biểu hiện thành lỗi biên dịch; dependency sai phiên bản có thể chỉ gây lỗi lúc khởi động. Vì vậy, ngoài *giai đoạn* cần xác định cả *nguyên nhân gốc*.

## 1. Ứng dụng Spring Boot đi qua những bước nào?

Xét một dự án Gradle có Spring Boot plugin, Java và các thư viện Spring Boot. Quá trình làm việc có thể hình dung như sau:

```text
Mã nguồn Java + build.gradle / pom.xml
                  │
                  ▼
        Đọc cấu hình build
                  │
                  ▼
       Giải quyết dependencies
       (chọn, tải, kiểm tra JAR)
                  │
                  ▼
            Biên dịch Java
          (.java → .class)
                  │
                  ▼
          Đóng gói / chạy JVM
                  │
                  ▼
       Nạp lớp và khởi động
        SpringApplication.run()
                  │
                  ▼
      Tạo ApplicationContext
       Bean, cấu hình, kết nối
                  │
                  ▼
     Web server lắng nghe cổng
       ỨNG DỤNG SẴN SÀNG
```

Sơ đồ thể hiện luồng chính, không phải tất cả task của mọi dự án. Chẳng hạn, task `bootRun` của Gradle có thể kích hoạt quá trình biên dịch trước khi khởi chạy JVM; task đóng gói có thể cần thêm xử lý resources và dependencies. Thất bại ở một lệnh `bootRun` chưa đủ để kết luận là lỗi khởi động: ứng dụng có thể chưa đến giai đoạn chạy.

| Nhóm lỗi | Thất bại ở đâu? | Dấu hiệu phổ biến | Bắt đầu điều tra từ |
|---|---|---|---|
| **Biên dịch** | Trình biên dịch Java kiểm tra cú pháp, tên và kiểu dữ liệu | `error: ';' expected`, `cannot find symbol`, `incompatible types`; Gradle có thể báo `:compileJava FAILED` | Tệp `.java`, dòng báo lỗi và chữ ký phương thức/kiểu |
| **Dependency** | Giải quyết, tải hoặc lựa chọn thư viện; đôi khi bộc lộ khi liên kết/nạp lớp ở runtime | `Could not resolve`, `Could not find`, `Could not GET`, `NoClassDefFoundError`, `NoSuchMethodError` | `build.gradle`/`pom.xml`, repositories, phiên bản, compile/runtime classpath |
| **Khởi động** | JVM đã bắt đầu chạy nhưng Spring không hoàn tất việc khởi tạo | `APPLICATION FAILED TO START`, `BeanCreationException`, `Port ... was already in use` | Stack trace, mục `Caused by`, cấu hình bean, cổng, môi trường |

**Cách nhớ:** *Biên dịch* trả lời “Java có hiểu và tạo được mã chạy không?”; *dependency* trả lời “những lớp/thư viện cần thiết có đúng và có sẵn không?”; *khởi động* trả lời “ứng dụng có thiết lập được môi trường chạy thực tế không?”.

## 2. Lỗi biên dịch: Java chưa tạo được bytecode

Lỗi biên dịch xuất hiện khi `javac` (trực tiếp hoặc qua Maven/Gradle) không thể chuyển mã Java thành tệp `.class` hợp lệ. Trình biên dịch kiểm tra cú pháp, khả năng tìm tên lớp/phương thức/biến, tương thích kiểu và nhiều quy tắc của Java.

### 2.1. Ví dụ lỗi cú pháp

Một controller đơn giản:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot"
    }
}
```

Lỗi nằm ở dấu `;` bị thiếu sau câu lệnh `return`. Khi biên dịch, thông báo có thể trông như sau:

```text
HelloController.java:11: error: ';' expected
        return "Hello Spring Boot"
                                  ^
```

Cách sửa:

```java
return "Hello Spring Boot";
```

Ở thời điểm này Spring Boot chưa cần tạo controller, chưa mở cổng và chưa tạo web server. Thay đổi `server.port` hoặc thêm cấu hình database sẽ không giải quyết lỗi dấu chấm phẩy.

### 2.2. Ví dụ lỗi không tìm thấy symbol

```java
public String hello() {
    return greetingService.message();
}
```

Nếu `greetingService` chưa được khai báo, compiler có thể báo:

```text
error: cannot find symbol
    return greetingService.message();
           ^
  symbol:   variable greetingService
```

Đây là một lỗi biên dịch về **tên biến trong mã nguồn**. Ngược lại, nếu bạn đã khai báo trường có kiểu `GreetingService` và biên dịch thành công nhưng Spring không tìm được bean thuộc kiểu đó, lỗi sẽ xuất hiện ở giai đoạn **khởi động ApplicationContext**. Hai vấn đề khác nhau mặc dù cùng nhắc đến tên service.

Các trường hợp biên dịch phổ biến khác:

- Đóng/mở ngoặc, dấu chấm phẩy hoặc dấu nháy không hợp lệ.
- Dùng sai kiểu dữ liệu, chẳng hạn trả `String` khi phương thức khai báo trả `int`.
- Gọi phương thức không tồn tại hoặc sai tham số.
- Trùng tên lớp hoặc trùng chữ ký phương thức không hợp lệ.
- Tên package/import không đúng, hoặc trình biên dịch không nhìn thấy lớp cần dùng.
- Cấu hình phiên bản Java không phù hợp, chẳng hạn công cụ biên dịch quá cũ để hiểu tính năng ngôn ngữ được sử dụng.

### 2.3. Lệnh quan sát lỗi biên dịch

Với dự án có Gradle Wrapper:

```bash
# Linux / macOS
./gradlew compileJava
```

```powershell
# Windows PowerShell
.\gradlew.bat compileJava
```

Với dự án dùng Maven Wrapper:

```bash
# Linux / macOS
./mvnw compile
```

```powershell
# Windows PowerShell
.\mvnw.cmd compile
```

Wrapper chỉ tồn tại nếu dự án có các tệp tương ứng. Nếu không có wrapper, dùng lệnh `gradle` hoặc `mvn` đã được cài đặt. Trong một dự án nhiều module, có thể cần chỉ định task/module cụ thể.

Hãy ưu tiên thông báo compiler có dạng `<TenFile>.java:<dong>: error: ...`; dòng `BUILD FAILED` chỉ là kết quả cuối cùng. Đừng sửa theo suy đoán dựa riêng vào dòng tổng kết đó.

## 3. Lỗi dependency: thiếu, không tải được hoặc không tương thích thư viện

**Dependency** là một thư viện hoặc module mà ứng dụng cần để biên dịch hay chạy. Với Spring Boot, bạn thường khai báo dependency trong `build.gradle` / `build.gradle.kts` hoặc `pom.xml`. Gradle/Maven sẽ tìm các artifact cùng những phụ thuộc bắc cầu (*transitive dependencies*).

Ví dụ Gradle Groovy DSL, giả sử project đã cấu hình Spring Boot plugin và repository:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Ví dụ trên chủ yếu mô tả các dependency, không phải toàn bộ tệp build. Trong dự án Spring Boot cấu hình dependency management phù hợp, phiên bản của các starter có thể được quản lý tập trung. Không nên tự gắn nhiều phiên bản rời rạc khi project đã có cơ chế quản lý phiên bản nhất quán.

### 3.1. Không tìm thấy hoặc không tải được artifact

Ví dụ log minh họa từ Gradle:

```text
Execution failed for task ':compileJava'.
> Could not resolve all files for configuration ':compileClasspath'.
   > Could not find com.example:missing-library:1.0.0.
     Searched in the following locations: ...
```

Đây là lỗi giải quyết dependency, dù task thất bại được báo là `compileJava`. Java compiler chưa có đầy đủ thư viện để thực hiện phần việc của nó.

Các nguyên nhân thường gặp:

| Dấu hiệu trong log | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| `Could not find group:artifact:version` | Sai tọa độ thư viện hoặc phiên bản không được công bố trong repository đã khai báo | Tên `group/artifact/version` và danh sách repositories |
| `Could not resolve ...` | Gradle/Maven không giải quyết được một dependency hoặc xung đột/chính sách liên quan | Phần lỗi chi tiết đi kèm, dependency tree |
| `Could not GET ...`, `Read timed out` | Không truy cập được nơi tải artifact | Mạng, proxy, DNS, repository URL |
| `401 Unauthorized`, `403 Forbidden` | Repository riêng yêu cầu quyền truy cập hoặc tài khoản không đủ quyền | Cấu hình xác thực đúng môi trường |
| `PKIX path building failed` | Kết nối HTTPS không xác thực được chuỗi chứng chỉ | Chuỗi chứng chỉ, proxy doanh nghiệp, truststore |
| `No cached version ... available for offline mode` | Chế độ offline nhưng artifact chưa nằm trong cache | Tắt offline hoặc chuẩn bị dependency trong cache |

Không nên xem mọi lỗi `Could not resolve` là do mạng. Nếu viết sai phiên bản hoặc repository không chứa artifact đó, thử tải lại nhiều lần không sửa được nguyên nhân.

### 3.2. Thư viện có nhưng compile vẫn báo thiếu package

Giả sử tệp Java có:

```java
import org.springframework.web.bind.annotation.RestController;
```

Và compiler báo:

```text
error: package org.springframework.web.bind.annotation does not exist
```

**Biểu hiện** là lỗi biên dịch, nhưng **nguyên nhân gốc có thể là dependency**: project chưa khai báo starter hoặc thư viện chứa annotation tương ứng trên compile classpath. Cũng có thể tên package bị viết sai.

Cách phân tích đúng:

1. Kiểm tra tên import có chính xác không.
2. Kiểm tra dependency có được khai báo trong đúng module không.
3. Kiểm tra thư viện đã có trên `compileClasspath` chưa.
4. Sau khi classpath đúng, chạy lại biên dịch để xác nhận symptom đã hết.

Không nên khắc phục bằng cách sao chép thủ công các tệp `.class` vào source tree.

### 3.3. Compile thành công nhưng runtime thiếu lớp

Có dependency chỉ phục vụ biên dịch và không được đưa vào runtime, hoặc một transitive dependency bị loại trừ sai. Khi ứng dụng thực thi đến một lớp cần nó, JVM có thể báo:

```text
java.lang.NoClassDefFoundError: com/example/library/Parser
Caused by: java.lang.ClassNotFoundException:
    com.example.library.Parser
```

Đây là lỗi tại **runtime**, có nguyên nhân thuộc nhóm **dependency/classpath**. Nó có thể xảy ra trong lúc Spring Boot khởi động hoặc chỉ khi xử lý request đầu tiên.

Với Gradle Java plugin, một số cấu hình phổ biến là:

| Cấu hình | Ý nghĩa thường gặp |
|---|---|
| `implementation` | Thư viện cho mã ứng dụng, thường tham gia cả compile và runtime classpath của module |
| `compileOnly` | Cần khi biên dịch nhưng thường không đóng vai trò dependency runtime |
| `runtimeOnly` | Cần khi chạy; mã chính không trực tiếp biên dịch dựa trên các kiểu của thư viện này |
| `testImplementation` | Thư viện cho việc biên dịch/chạy test, không tự trở thành dependency runtime của ứng dụng chính |

Ví dụ thường gặp: driver JDBC có thể khai báo `runtimeOnly` nếu mã ứng dụng không trực tiếp tham chiếu các lớp driver khi biên dịch; còn annotation như `@RestController` phải được tìm thấy lúc compile.

Với Maven, cách phân chia scope có tên và semantics riêng (`compile`, `runtime`, `provided`, `test`). Không sao chép máy móc tên scope từ Gradle sang Maven.

### 3.4. Thư viện sai phiên bản hoặc có xung đột

Một ứng dụng có thể tải được dependency và biên dịch được nhưng tại runtime xuất hiện:

```text
java.lang.NoSuchMethodError: '...'
```

Điều này thường cho thấy mã bytecode đang gọi một phương thức mà phiên bản lớp thực sự được nạp **không có**. Một nguyên nhân điển hình là compiler từng nhìn thấy phiên bản thư viện khác với phiên bản được dùng lúc chạy.

Một lỗi liên quan là `UnsupportedClassVersionError`: class file được biên dịch với phiên bản Java mới hơn phiên bản JVM hiện tại hỗ trợ. Đây là vấn đề tương thích bytecode/runtime; có thể nằm ở mã ứng dụng hoặc trong thư viện.

Hướng xử lý:

- Xem dependency tree thay vì đoán phiên bản đang được dùng.
- Đọc đầy đủ tên lớp/phương thức trong stack trace.
- Kiểm tra phiên bản JDK ở giai đoạn build và chạy.
- Ưu tiên cơ chế quản lý phiên bản của Spring Boot và BOM phù hợp.
- Hạn chế ép phiên bản hoặc loại bỏ transitive dependency mà chưa hiểu hệ quả.

### 3.5. Công cụ xem đồ thị dependency

Với Gradle:

```bash
# Linux / macOS
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

```powershell
# Windows PowerShell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree
```

```powershell
.\mvnw.cmd dependency:tree
```

Các lệnh dùng tên project/module đang được chạy. Với Gradle nhiều module, cần chọn đúng đường dẫn project; với Maven nhiều module có thể chọn module bằng `-pl`. Khi kiểm tra lỗi biên dịch liên quan dependency, xem `compileClasspath` thay cho hoặc cùng với `runtimeClasspath`.

Tùy tình huống, `--refresh-dependencies` của Gradle có thể buộc kiểm tra lại dependency metadata/cache, nhưng nó không sửa được tọa độ artifact sai hoặc cấu hình repository thiếu. Đừng dùng xóa toàn bộ cache làm bước đầu tiên.

## 4. Lỗi khởi động: ứng dụng chạy nhưng Spring Boot chưa sẵn sàng

Khi mã đã được biên dịch, JVM có thể thực thi phương thức `main`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`SpringApplication.run(...)` bắt đầu thiết lập ứng dụng: đọc cấu hình, tạo `ApplicationContext`, đăng ký và khởi tạo bean, áp dụng auto-configuration, thiết lập kết nối hoặc web server tùy các dependency và cấu hình.

Khi một bước bắt buộc thất bại, quá trình startup có thể dừng và trả về exit code khác 0, dù các tệp `.class` đã được tạo thành công.

### 4.1. Spring Boot báo lỗi nhưng cần đọc nguyên nhân cụ thể

Log minh họa:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Web server failed to start. Port 8080 was already in use.

Action:

Identify and stop the process that's listening on port 8080
or configure this application to listen on another port.
```

Đây là lỗi khởi động do **cổng bị chiếm**, không phải thiếu dấu `;` và cũng không tự động là thiếu dependency. Một cách xử lý khi dùng cổng khác là đặt:

```yaml
# src/main/resources/application.yml
server:
  port: 8081
```

Hoặc truyền tham số khi chạy artifact:

```bash
java -jar build/libs/demo.jar --server.port=8081
```

Tệp `demo.jar` ở lệnh trên là ví dụ: thay bằng tên JAR thực tế. Nếu đổi cổng, các URL gọi thử cũng phải dùng cổng mới.

### 4.2. Không tạo được bean

Xét:

```java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet() {
        return service.greet();
    }
}
```

Nếu `GreetingService` là một interface có khai báo hợp lệ nhưng không có bean triển khai được đăng ký, mã có thể **biên dịch thành công**. Khi Spring tạo `GreetingController`, quá trình khởi động mới thất bại với thông báo tương tự:

```text
Parameter 0 of constructor in com.example.demo.web.GreetingController
required a bean of type 'com.example.demo.service.GreetingService'
that could not be found.
```

Cách xử lý có thể là đăng ký implementation đúng:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet() {
        return "Xin chào!";
    }
}
```

Đồng thời phải bảo đảm lớp nằm trong phạm vi component scan hoặc được đăng ký qua cấu hình phù hợp. `@SpringBootApplication` thường quét package chứa lớp main và các package con. Việc thêm `@Service` chỉ giải quyết tình huống bean thiếu khi lớp được quét và không có vấn đề cấu hình khác.

**Phân biệt quan trọng:**

- `cannot find symbol: GreetingService` khi compile: trình biên dịch không nhận diện kiểu.
- `required a bean of type GreetingService that could not be found` khi startup: JVM đã biết kiểu, nhưng Spring không có bean phù hợp để inject.

### 4.3. Lỗi cấu hình và môi trường

Một số trường hợp quen thuộc của dự án đầu tiên:

| Tình huống | Gợi ý trong log | Nhóm nguyên nhân |
|---|---|---|
| Cổng web đã có process dùng | `Port 8080 was already in use` | Tài nguyên môi trường |
| Không có bean bắt buộc | `No qualifying bean`, `UnsatisfiedDependencyException` | Spring context, component scan, conditional configuration |
| Bean khởi tạo thất bại | `BeanCreationException`; xem tiếp `Caused by` | Bean, phụ thuộc bean hoặc code khởi tạo |
| Không kết nối được database | `Connection refused`, `Access denied`, timeout; có thể kèm lỗi DataSource/JPA | Cấu hình hoặc dịch vụ database |
| Thiếu property cần thiết | `Could not resolve placeholder` | Thiếu environment variable, property hoặc profile |
| Giá trị cấu hình không chuyển được sang kiểu Java | `BindException` hoặc `ConversionFailedException` | Sai giá trị hoặc kiểu cấu hình |
| Không nhận diện được cấu hình profile | `No active profile set` là thông báo thông tin thông thường, **không mặc nhiên là lỗi** | Chỉ điều tra khi có thông báo thất bại liên quan |

Ví dụ, nếu bạn dùng profile `dev` mà chưa cung cấp biến môi trường cho cấu hình datasource, ứng dụng có thể thất bại dù compile và giải quyết dependency đã thành công. Cần xác định application đang đọc `application.yml` nào, profile nào đang active và dữ liệu cấu hình đến từ đâu.

### 4.4. Web server đã lên khác với request thành công

Khi log hiển thị đại ý:

```text
Started DemoApplication in ... seconds
```

ứng dụng thường đã hoàn tất giai đoạn startup. Nếu gọi `GET /hello` rồi nhận `404 Not Found`, đó thường là vấn đề URL mapping hoặc route. Nếu request nhận `500 Internal Server Error` do exception bên trong controller, đó là **lỗi xử lý request**, dù stack trace có nhắc đến Spring.

Tách giai đoạn rõ ràng giúp tránh tìm lỗi bean startup cho một request sai URL, hoặc tìm lỗi route khi web server thực tế chưa mở cổng.

## 5. Cùng một lệnh chạy có thể thất bại ở ba giai đoạn

Giả sử bạn chạy:

```bash
./gradlew bootRun
```

hoặc trên Windows:

```powershell
.\gradlew.bat bootRun
```

Tên lệnh là `bootRun`, nhưng Gradle thường phải chuẩn bị dependencies và compile mã nguồn trước khi thực sự chạy Spring Boot. Vì vậy, ba ví dụ sau đều có thể khiến lệnh này kết thúc thất bại:

**Trường hợp A — Mã nguồn sai cú pháp**

```text
> Task :compileJava FAILED
DemoApplication.java:...: error: ';' expected
```

Nguyên nhân trực tiếp: source code. Hành động: sửa đúng dòng Java bị báo lỗi rồi biên dịch lại.

**Trường hợp B — Không tải được thư viện**

```text
> Could not resolve all files for configuration ':compileClasspath'
> Could not find org.example:sample-library:9.9.9
```

Nguyên nhân trực tiếp: giải quyết dependency thất bại. Hành động: kiểm tra khai báo artifact, repository và kết nối. Đừng tìm trong controller để sửa dấu ngoặc khi compiler chưa được cấp dependencies.

**Trường hợp C — Ứng dụng bắt đầu chạy nhưng Spring startup thất bại**

```text
APPLICATION FAILED TO START
...
Port 8080 was already in use.
```

Nguyên nhân trực tiếp: môi trường khởi động. Hành động: giải phóng cổng phù hợp hoặc thay cấu hình port.

Một dòng tổng kết như `Execution failed for task ':bootRun'` hoặc `BUILD FAILED` không phân biệt được ba trường hợp. Bằng chứng nằm ở log **phía trên** và chuỗi nguyên nhân cụ thể.

## 6. Đọc log để tìm lỗi gốc

Khi chạy Spring Boot lần đầu, terminal có thể in rất nhiều dòng INFO, WARN và ERROR. Không phải mọi dòng WARN đều là lỗi nghiêm trọng. Hãy bắt đầu từ điểm thất bại và lần theo nguyên nhân.

### 6.1. Ví dụ đọc stack trace

Log minh họa rút gọn:

```text
org.springframework.beans.factory.BeanCreationException:
  Error creating bean with name 'dataSource'
Caused by: org.springframework.jdbc.CannotGetJdbcConnectionException:
  Failed to obtain JDBC Connection
Caused by: java.sql.SQLException:
  Access denied for user 'demo_user'
```

Đọc theo thứ tự:

- Spring không tạo được bean `dataSource`.
- Nguyên nhân trung gian là không lấy được JDBC connection.
- Nguyên nhân cụ thể ở đây là thông tin đăng nhập database bị từ chối.

Nếu chỉ thấy `BeanCreationException` rồi đi thêm `@Component` cho lớp đang có, khả năng cao bạn đang sửa sai chỗ. Cần xem credentials, host/database và quyền truy cập phù hợp với thông báo thực tế. Trong môi trường làm việc, tránh dán mật khẩu, token hoặc connection string chứa bí mật vào nơi công khai.

### 6.2. Mốc tìm kiếm hữu ích trong terminal

| Chuỗi cần tìm | Hướng đọc |
|---|---|
| `.java:...: error:` | Lỗi cụ thể mà compiler gắn với vị trí mã nguồn |
| `> Task :compileJava FAILED` | Gradle task biên dịch thất bại; đọc tiếp nguyên nhân, vì có thể do dependency |
| `Could not resolve`, `Could not find` | Kiểm tra phần dependency/repository đi kèm |
| `Caused by:` | Đi dọc chuỗi nguyên nhân, thường nguyên nhân gần cuối chứa thông tin cụ thể nhất |
| `APPLICATION FAILED TO START` | Spring Boot cung cấp thông tin phân tích thất bại khởi động |
| `Description:` và `Action:` | Một số failure analyzer của Spring Boot ghi thêm hướng dẫn |
| `Started ... in ... seconds` | Dấu hiệu startup hoàn tất; lỗi về sau có thể thuộc request/runtime |

Không phải mọi lỗi đều có `APPLICATION FAILED TO START`. Chẳng hạn JVM không tìm được lớp main sẽ thất bại trước khi Spring chạy, hoặc một lỗi nạp lớp có thể xảy ra ngay lúc gọi main.

### 6.3. Thu thêm thông tin khi cần

Gradle:

```bash
./gradlew bootRun --stacktrace
./gradlew bootRun --info
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --stacktrace
.\gradlew.bat bootRun --info
```

Maven:

```bash
./mvnw spring-boot:run -e
```

`--stacktrace` và `-e` cung cấp nhiều chi tiết về lỗi của build tool. Nếu sự cố nằm trong ứng dụng, phải xem **log Spring Boot** và các `Caused by` của application nữa.

Khi muốn hiểu các quyết định auto-configuration của Spring Boot, có thể chạy với tham số `--debug` dành cho Spring Boot, ví dụ:

```bash
java -jar build/libs/demo.jar --debug
```

Cờ này có thể in báo cáo điều kiện auto-configuration rất dài; nó chỉ hữu ích khi nghi ngờ cấu hình tự động hoặc bean có điều kiện. Đừng bật mọi chế độ debug rồi chỉ xem dòng cuối.

## 7. Quy trình xử lý lỗi từng bước

Bạn có thể áp dụng quy trình này mỗi khi “dự án đầu tiên không chạy”.

### Bước 1 — Ghi lại hành động thất bại

Bạn đã chạy lệnh nào: `compileJava`, `test`, `bootJar`, `bootRun`, `java -jar` hay gọi HTTP? Những lệnh đó kích hoạt các giai đoạn khác nhau.

Cùng với lệnh, ghi lại thay đổi vừa làm: sửa Java, thêm starter, đổi Java version, thay application properties hay chạy database.

### Bước 2 — Tìm điểm thất bại sớm nhất có ý nghĩa

Đọc các dòng cụ thể *trước* `BUILD FAILED` hoặc `Application run failed`. Hỏi:

- Có thông báo compiler kèm tệp `.java` và số dòng không?
- Có thông báo repository hoặc dependency resolution không?
- JVM đã gọi main và Spring đã bắt đầu tạo ApplicationContext chưa?
- Web server đã báo started chưa, hay lỗi xảy ra khi gọi một endpoint về sau?

### Bước 3 — Phân loại cả biểu hiện và nguyên nhân

Một số kết hợp hay gặp:

| Biểu hiện | Giai đoạn quan sát | Nguyên nhân gốc cần xét |
|---|---|---|
| `';' expected` | Biên dịch | Cú pháp Java |
| `package ... does not exist` | Biên dịch | Sai import **hoặc** thiếu compile dependency |
| `Could not find ...:...:...` | Giải quyết dependency | Artifact/repository/version |
| `NoClassDefFoundError` | Nạp lớp ở runtime | Thiếu lớp, sai runtime classpath hoặc lỗi liên kết/khởi tạo lớp |
| `NoSuchMethodError` | Runtime | Không tương thích phiên bản binary |
| `required a bean ... could not be found` | Spring startup | Bean chưa đăng ký, không được scan, điều kiện cấu hình không thỏa |
| `Port ... was already in use` | Web server startup | Cổng đang có tiến trình chiếm |
| HTTP `404` hoặc `500` sau khi startup thành công | Xử lý request | Mapping hoặc lỗi xử lý nghiệp vụ/runtime |

Hàng thứ hai là lý do không nên gắn nhãn cứng theo vài từ khóa. Câu `package ... does not exist` được compiler phát ra, nhưng cách khắc phục có thể nằm ở file build.

### Bước 4 — Sửa thay đổi nhỏ nhất giải quyết đúng nguyên nhân

Nếu compiler chỉ ra dấu chấm phẩy thiếu, sửa mã nguồn. Nếu artifact không tồn tại, sửa dependency coordinate/repository. Nếu server port đã dùng, xác định tiến trình hoặc dùng cổng khác. Nếu thiếu bean, kiểm tra wiring và component scanning.

Không thay đồng thời JDK, toàn bộ thư viện, cấu hình database và source code để “thử xem có chạy không”. Thay đổi quá nhiều biến làm mất bằng chứng về nguyên nhân.

### Bước 5 — Chạy lại đúng giai đoạn

- Sửa cú pháp/kiểu dữ liệu: chạy `compileJava` hoặc `mvn compile`.
- Sửa dependency: chạy lại task từng thất bại; xem compile/runtime classpath tương ứng.
- Sửa startup: chạy lại `bootRun` hoặc `java -jar` rồi quan sát log khởi động.
- Nếu ứng dụng đã started: gửi request tới endpoint cụ thể để xác định hành vi.

Điều kiện để kết luận đã sửa lỗi là **bước trước đó thất bại nay hoàn tất được**. Với dự án có test, test có thể là một giai đoạn riêng báo lỗi tiếp theo; không nên gom test failure thành compile/startup failure.

## 8. Bài thực hành: ba lỗi có chủ đích trong project Spring Boot đầu tiên

Dùng project Spring Boot có `@SpringBootApplication` và `spring-boot-starter-web` đã chạy được. Giữ một bản thay đổi có thể hoàn tác trước khi thử. Mỗi bài thử chỉ làm một thay đổi, quan sát log, sửa lại rồi mới chuyển sang bài tiếp theo.

### Thử nghiệm 1 — Tạo lỗi biên dịch

Tạo controller với câu lệnh thiếu dấu `;`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/demo")
    public String demo() {
        return "demo"
    }
}
```

Chạy:

```bash
./gradlew compileJava
```

Kỳ vọng một thông báo compiler tại dòng `return`. Sửa thành `return "demo";` rồi biên dịch lại. Điều bạn vừa quan sát là lỗi xảy ra trước giai đoạn JVM chạy ứng dụng.

### Thử nghiệm 2 — Tạo lỗi giải quyết dependency

Trong một project Gradle Groovy DSL có khai báo `repositories { mavenCentral() }`, thêm tạm dependency giả vào block `dependencies`:

```groovy
implementation 'com.example.nonexistent:training-artifact:9999.0'
```

Chạy:

```bash
./gradlew compileJava
```

Nếu không có dependency này trong repository đã cấu hình và cache, Gradle sẽ báo không thể giải quyết artifact. Không có dòng Java nào cần sửa trong tình huống này. Sau khi đọc lỗi, **xóa dòng dependency giả** rồi chạy lại.

Đây là bài thực hành dựa trên tọa độ cố ý không có thật; thông báo cụ thể phụ thuộc cấu hình repository và phiên bản Gradle.

### Thử nghiệm 3 — Tạo lỗi startup về cổng

Chạy một bản ứng dụng web đã build thành công trên cổng mặc định, sau đó cố chạy thêm một instance khác cũng dùng cùng cổng. Nếu cả hai cùng bind vào một địa chỉ/cổng, instance sau không thể mở listener và Spring Boot thường báo port đã được sử dụng.

Có thể thử đặt cổng khác tại dòng lệnh cho instance thứ hai:

```bash
./gradlew bootRun --args='--server.port=8081'
```

Cú pháp trên là ví dụ với Gradle `bootRun` hỗ trợ `--args`. Với executable JAR, có thể chạy `java -jar <duong-dan-jar> --server.port=8081`. Nếu một tiến trình khác đã dùng cổng 8081, cần chọn cổng còn trống.

Ở thử nghiệm này, compiler và các dependencies của ứng dụng vẫn có thể hoàn toàn hợp lệ. Lỗi là điều kiện runtime của web server.

### Bài luyện phân tích log

Hãy tự xác định *giai đoạn* và *nguyên nhân khả dĩ* của mỗi thông báo sau trước khi nhìn đáp án:

| Log ngắn | Giai đoạn | Nguyên nhân khả dĩ |
|---|---|---|
| `error: incompatible types: String cannot be converted to int` | Biên dịch | Sai kiểu dữ liệu trong mã Java |
| `Could not GET 'https://.../artifact.pom'` | Giải quyết dependency | Truy cập repository thất bại; xem lý do HTTP/TLS/network đi kèm |
| `NoClassDefFoundError: org/example/LibraryClass` khi gọi `java -jar` | Runtime | Thiếu lớp hoặc không thể nạp/liên kết lớp phụ thuộc |
| `UnsatisfiedDependencyException` khi `ApplicationContext` đang refresh | Spring startup | Một dependency bean không thỏa mãn, xem các `Caused by` |
| `Started DemoApplication...` rồi `GET /missing` trả `404` | Request | Ứng dụng đã chạy; URL không có route phù hợp |

## 9. Các hiểu lầm dễ gặp

**“Lệnh `bootRun` thất bại, vậy chắc là lỗi Spring startup.”** Không chắc. `bootRun` có thể dừng ở dependency resolution hoặc Java compile. Phải đọc task và nguyên nhân trong log.

**“Có lỗi `ClassNotFoundException` thì thêm `@Component`.”** `@Component` chỉ tham gia đăng ký bean khi lớp đã có thể được nạp và được quét. Nó không tự bổ sung JAR thiếu vào classpath.

**“Build thành công thì startup chắc chắn thành công.”** Build kiểm tra một số điều kiện của mã nguồn, dependencies và đóng gói. Nó không bảo đảm database sẵn sàng, port còn trống, cấu hình môi trường hợp lệ hoặc bean được tạo thành công trong mọi profile.

**“Dòng ERROR đầu tiên hoặc WARN cuối là nguyên nhân gốc.”** Một lỗi có thể tạo nhiều thông báo nối tiếp. Cần xem ngữ cảnh, chuỗi `Caused by` và failure analysis. WARN thông thường chưa chắc làm ứng dụng thất bại.

**“Thêm cùng một thư viện với phiên bản mới nhất sẽ sửa mọi lỗi.”** Một bản mới có thể không tương thích với Spring Boot hoặc phần khác của ứng dụng. Nên đọc dependency tree và chọn tập phiên bản nhất quán.

**“Ứng dụng trả 404 tức là không khởi động được.”** Không đúng trong trường hợp web server đã sẵn sàng. 404 có thể đơn giản do gửi request tới đường dẫn chưa được định nghĩa.

## 10. Tư duy chẩn đoán cần mang sang các bài Spring Boot tiếp theo

Khi gặp lỗi, hãy kể lại sự cố bằng một câu chính xác:

- “`javac` không biên dịch được `HelloController.java` vì thiếu dấu `;`.”
- “Gradle không giải quyết được `group:artifact:version` từ các repository đã cấu hình.”
- “JVM không nạp được lớp của thư viện khi chạy artifact.”
- “Spring không tạo được `GreetingController` vì không có bean `GreetingService` phù hợp.”
- “Spring tạo ứng dụng web nhưng không mở được cổng do bị chiếm.”
- “Ứng dụng đã started, nhưng request `/hello` nhận 404 vì endpoint không được ánh xạ như mong đợi.”

Những câu trên chỉ rõ **thành phần nào thất bại**, **khi nào thất bại** và **chứng cứ nào cần kiểm tra**. Đó là nền tảng để tiếp tục học Dependency Injection, auto-configuration, profiles, database và xử lý HTTP trong Spring Boot mà không nhầm lẫn giữa lỗi mã nguồn, thư viện và môi trường chạy.
