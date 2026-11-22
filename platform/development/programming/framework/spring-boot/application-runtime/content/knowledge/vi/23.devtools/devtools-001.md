# Vai trò của spring-boot-devtools trong vòng lặp phát triển

## 1. Devtools giải quyết vấn đề nào?

Trong một ứng dụng Spring Boot, một thay đổi nhỏ ở controller, service, cấu hình hoặc template thường khiến người lập trình phải lặp lại nhiều bước:

```text
Sửa mã -> lưu -> biên dịch -> dừng app -> chạy lại -> chờ startup
    -> gọi API hoặc mở trình duyệt -> xem kết quả -> tiếp tục sửa
```

Các bước dừng/chạy lại ứng dụng thủ công gây lãng phí thời gian, nhất là khi Spring container có nhiều bean và dependency. **`spring-boot-devtools`** là module của Spring Boot nhằm cải thiện vòng phản hồi khi **phát triển cục bộ**. Nó giúp cập nhật chương trình đã chạy nhanh hơn và giảm một số rào cản do cache.

Vòng lặp phát triển với Devtools thường là:

```text
Developer sửa mã Java
      |
      v
IDE/Gradle/Maven biên dịch -> file .class thay đổi trên classpath
      |
      v
Devtools phát hiện thay đổi ở các directory được theo dõi
      |
      v
Đóng ApplicationContext cũ, tạo restart classloader mới
      |
      v
SpringApplication startup lại trong cùng JVM
      |
      v
Gọi API/kiểm tra log/test hành vi mới
      |
      +-------------------> sửa tiếp
```

Với thay đổi tài nguyên như file tĩnh hoặc template, đường phản hồi có thể ngắn hơn: **không cần restart context**; cơ chế cache mặc định cho development và LiveReload (nếu được client hỗ trợ) giúp thấy nội dung mới.

**Điểm then chốt:** Devtools tự restart khi **classpath được cập nhật**, chứ **không tự biên dịch Java source**. Việc lưu `.java` không đương nhiên làm xuất hiện file `.class` mới trong thư mục mà ứng dụng đang chạy quan sát.

Bài này tập trung vào **Spring Boot 3.3.x / Java 17+**, dùng `3.3.13` cho ví dụ Gradle. Devtools không phải thư viện để đưa vào production: nó thay đổi trải nghiệm local development, có hai classloader và những default tối ưu cho phát triển chứ không phải tối ưu cho vận hành.

## 2. Bốn vai trò chính của Devtools

| Vai trò | Hành vi | Lợi ích thực tế | Điều không được hiểu nhầm |
| --- | --- | --- | --- |
| **Automatic restart** | Theo dõi thay đổi trong các thư mục classpath và restart Spring app khi cần | Giảm thao tác dừng/chạy lại app mỗi lần sửa class | Không phải hot swap thay code ngay trong mọi thread đang chạy |
| **Development property defaults** | Áp đặt một số giá trị thuận tiện cho phát triển, nhất là cache/template và chi tiết lỗi | Thấy thay đổi dễ hơn, ít vướng nội dung cache cũ | Không áp dụng nguyên trạng cho production |
| **LiveReload** | Có thể chạy server LiveReload để báo browser refresh khi resource thay đổi | Giảm thao tác bấm tải lại trang thủ công | Không làm Java compiler, không phải JavaScript HMR của frontend bundler |
| **Condition evaluation delta** | Có thể log sự thay đổi của auto-configuration khi app restart | Tìm hiểu vì sao bean/auto-config đổi sau chỉnh property/dependency | Không thay thế toàn bộ stack trace, test hay hiểu biết về điều kiện cấu hình |

Ngoài ra, Devtools hỗ trợ **trigger file**, danh sách exclude/additional paths, điều chỉnh file watcher và classloader, cùng các cơ chế nâng cao như remote development. Phần lớn dự án chỉ cần dependency, automatic restart và property defaults.

### 2.1. Mục tiêu là phản hồi nhanh, không phải vận hành tự động

Devtools giúp một developer thử giả thuyết:

- Đổi giá trị response của controller rồi gọi lại endpoint.
- Thay implementation của service và quan sát bean được tái khởi tạo.
- Sửa property và xem tác động lên auto-configuration.
- Đổi template, CSS, JavaScript tĩnh và thấy thay đổi khi render/tải lại.
- Quan sát startup failure từ thay đổi code mới mà không phải nhập lại lệnh chạy.

Nhưng Devtools **không** bảo đảm:

- Mã mới đúng: vẫn phải chạy unit/integration tests.
- Database schema được migrate hoặc dữ liệu test được reset đúng.
- Dịch vụ remote có thể truy cập.
- Mọi thư viện hỗ trợ restart classloader.
- Client HTTP hiện hữu không bị ngắt khi context restart.
- Prod image không vô tình chứa cơ chế remote devtools nếu team cố tình cấu hình khác mặc định.

## 3. Thêm dependency đúng phạm vi development

### 3.1. Gradle Groovy

Trong `build.gradle` của Spring Boot 3.3:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

Đoạn trên chỉ là **khối dependencies minh họa**, cần Gradle plugin Spring Boot và repository thích hợp. Cấu hình `developmentOnly` làm rõ đây là công cụ của developer; nó không nên bị đưa vào các dependency runtime phát hành như một thư viện nghiệp vụ.

### 3.2. Maven

Trong `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

`optional=true` tránh việc devtools bị kéo transitively vào các module khác phụ thuộc vào project của bạn. Với Maven và Boot packaging bình thường, devtools cũng được xử lý để không bị đưa vào artifact production mặc định.

### 3.3. Devtools có tự chạy khi java -jar không?

**Mặc định không.** Spring Boot coi fully packaged application được chạy bằng `java -jar` là môi trường production-like và tự vô hiệu hóa chức năng Devtools. Các executable JAR/WAR được Spring Boot repackager tạo ra cũng **mặc định không chứa devtools**.

So sánh:

| Cách chạy | Thực tế mong đợi |
| --- | --- |
| `./gradlew bootRun` với `developmentOnly` | Devtools có trên classpath phát triển, có thể bật restart |
| IDE chạy main với classpath dạng thư mục | Devtools có thể theo dõi classpath output khi được cấu hình đúng |
| `mvn spring-boot:run` và dependency optional | Phù hợp vòng lặp phát triển nếu launcher/forking hỗ trợ |
| `java -jar build/libs/app.jar` với Boot packaging mặc định | Không nên dự kiến Devtools restart chạy |
| Docker/Kubernetes production image | Không nên đưa devtools/remote devtools vào; dùng deploy thực |

Không biến sự khác biệt giữa `bootRun` và `java -jar` thành “bug”: đây là ranh giới có chủ ý giữa môi trường phát triển và artifact vận hành.

### 3.4. Cảnh báo về remote devtools

Spring Boot có cơ chế remote development **opt-in**, nhưng tài liệu chính thức cảnh báo rõ **không bao giờ bật remote devtools trong production**, vì có thể tạo rủi ro bảo mật. Không cấu hình `spring.devtools.remote.secret` hay cố đóng gói devtools vào JAR production để “sửa nóng” hệ thống sống.

Với staging/dev environment có yêu cầu đặc biệt, chỉ đánh giá theo hướng dẫn bảo mật và mạng được tin cậy; vòng lặp local thông thường **không cần remote devtools**.

## 4. Automatic restart hoạt động như thế nào?

### 4.1. Devtools không xem trực tiếp mọi file source

Devtools giám sát các **directory entries trên classpath**. Với project Gradle, ví dụ có thể là:

```text
src/main/java/.../GreetingController.java    (mã nguồn)
        |
        +--> Gradle/IDE compileJava
                |
                v
build/classes/java/main/.../GreetingController.class (classpath)
        |
        +--> Devtools watcher nhận diện thay đổi
                |
                v
Restart ApplicationContext
```

Một file `GreetingController.java` được sửa và lưu nhưng IDE **chưa tạo `.class` mới** có thể không làm Devtools restart. Điều này giải thích vì sao trên máy A “cứ Save là restart” nhưng máy B “phải Build Project”:

- Eclipse/STS thường tự cập nhật classpath output khi save nếu incremental build được bật.
- IntelliJ IDEA có thể yêu cầu `Build > Build Project` hoặc cấu hình auto-build hợp lệ.
- Dùng Gradle/Maven, có thể chạy một lệnh compile cập nhật classpath output mà process đang quan sát.

Điểm ổn định để debug là **classpath output có đổi không?**, không phải phỏng đoán IDE đã “nhận Save” hay chưa.

### 4.2. Hai classloader là lý do restart nhanh

Devtools dùng mô hình hai classloader:

```text
JVM process
  |
  +--> Base ClassLoader
  |      +--> thư viện ổn định, JAR của Spring và dependency
  |      +--> không nạp lại toàn bộ qua mỗi restart bình thường
  |
  +--> Restart ClassLoader lần 1
  |      +--> classes của project đang phát triển
  |      +--> tạo ApplicationContext lần 1
  |
  +--> thấy classpath changed
         |
         +--> đóng ApplicationContext lần 1
         +--> bỏ Restart ClassLoader lần 1 khi có thể
         +--> tạo Restart ClassLoader lần 2
                 +--> classes mới của project
                 +--> tạo ApplicationContext lần 2
```

Thư viện từ regular JAR thường ở **base classloader**, còn những project đang mở trên classpath thường ở **restart classloader**. Khi thay đổi code, Devtools có thể tái sử dụng lớp thư viện nặng đã load ở base và chỉ dựng lại phần application. Vì vậy **restart nhanh hơn cold JVM start** trong nhiều project.

**Không đồng nghĩa “không restart Spring context”.** Bean thường được tạo lại; `@PostConstruct` của bean singleton mới chạy lại; `@PreDestroy` hoặc lifecycle stop có thể chạy trên context cũ trong restart. Những connection/client thuộc context phải được đóng và tạo theo đúng lifecycle.

### 4.3. Restart khác hot swap, reload browser và redeploy

| Cơ chế | Điều thay đổi | Context có tạo lại? |
| --- | --- | --- |
| **Devtools restart** | Thay restart classloader, khởi động lại phần Spring app | **Có**, trong một JVM đang sống |
| **JVM cold restart** | Dừng process Java và chạy JVM mới | Có, cùng với việc khởi động JVM lại |
| **Debugger HotSwap** | JVM thay một số bytecode/method trong điều kiện được hỗ trợ | Không nhất thiết |
| **JRebel/dynamic class reloading** | Công nghệ viết lại/reload class riêng | Không nhất thiết theo cơ chế Devtools |
| **LiveReload** | Tín hiệu browser làm mới giao diện/tài nguyên | Không bắt buộc |
| **Frontend HMR** | Bundler cập nhật module JS/CSS trong browser | Không phải chức năng chính của Spring Devtools |
| **Deploy JAR/Container mới** | Bản phát hành được thay trong hạ tầng | Có lifecycle deployment riêng |

Với thay đổi Java bean/controller, Devtools thường **restart context**, không patch class trực tiếp. Do đó in-memory state trong bean có thể được reset; request in-flight có thể bị gián đoạn; test phải kiểm tra hành vi mới sau khi ứng dụng startup lại.

### 4.4. Các giới hạn classloader quan trọng

Một số thư viện tự dùng `Class.forName`, reflection, annotation scanning, proxy, `ObjectInputStream` hay custom serialization theo classloader khác có thể gặp lỗi:

- `ClassCastException` khi cùng tên class được load bởi hai classloader khác nhau.
- `ClassNotFoundException` ở luồng deserialize do dùng sai context classloader.
- Annotations không được nhìn thấy ở loader như ứng dụng kỳ vọng.
- Static singleton hoặc thread do một library giữ từ lần restart cũ gây leak.
- Module multi-project được phân vào base/restart loader không đúng chỗ.

Để điều tra, thử tắt restart. Nếu lỗi biến mất, xem cơ chế classloader và file `META-INF/spring-devtools.properties`, chứ không kết luận domain logic sai. Phần 10 hướng dẫn lựa chọn restart include/exclude.


## 5. Ví dụ chạy được: Spring Boot 3.3.13 / Java 17 / Gradle

Ta tạo một web app nhỏ với endpoint trả chuỗi. Mục tiêu kiểm chứng hai đường:

1. **Sửa Java → compile → Devtools restart** và endpoint trả body mới.
2. **Sửa static resource → processResources → nội dung mới** mà **không cần full restart** theo exclude mặc định.

Dự án không dùng database, frontend bundler hay service ngoài; ví dụ đủ gọn để phân biệt đúng nơi cần nhìn.

### 5.1. Cấu trúc thư mục

```text
devtools-loop-lab/
├── build.gradle
├── settings.gradle
└── src/main/
    ├── java/com/example/devloop/
    │   ├── DevLoopApplication.java
    │   └── GreetingController.java
    └── resources/
        ├── application.properties
        └── static/
            └── notice.txt
```

Tên đường dẫn, package và class phải khớp. Dự án giả định có **Gradle Wrapper tương thích Java 17**. Nếu chưa có wrapper, cần tạo bằng công cụ Gradle có sẵn một lần; ví dụ lệnh dưới đây dùng wrapper.

### 5.2. File build.gradle

```groovy
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
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'devtools-loop-lab'
```

Dependency `developmentOnly` cho Devtools xuất hiện trong classpath của `bootRun` nhưng tránh coi nó là dependency runtime của JAR deploy. Spring Boot Gradle plugin quản lý version của dependency theo dependency management đã khai báo, nên không cần thêm version Devtools thủ công.

### 5.3. File application.properties

Tạo `src/main/resources/application.properties`:

```properties
server.port=8080
demo.greeting=hello

# Dành cho local development:
spring.devtools.restart.enabled=true
spring.devtools.livereload.enabled=true
spring.devtools.restart.log-condition-evaluation-delta=false
```

Chúng ta tắt log condition evaluation delta trong demo để nhìn log đơn giản hơn; nó **không làm Devtools mất chức năng restart**. Nếu muốn xem điều kiện auto-configuration thay đổi sau mỗi restart, bỏ dòng `log-condition-evaluation-delta=false`.

**Không đưa các property devtools ở trên vào mọi production environment** như một chính sách chung. Chúng nằm trong demo local development có dependency `developmentOnly`. Production vẫn phải tách config/secrets và dùng release artifact đúng cách.

### 5.4. File Java main hoàn chỉnh

Tạo `src/main/java/com/example/devloop/DevLoopApplication.java`:

```java
package com.example.devloop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevLoopApplication {
    public static void main(String[] args) {
        SpringApplication.run(DevLoopApplication.class, args);
    }
}
```

Method `main` đơn giản khởi động web application, không tự đóng context sau `run`. Spring Boot starter web cung cấp embedded servlet server.

### 5.5. File Java controller hoàn chỉnh

Tạo `src/main/java/com/example/devloop/GreetingController.java`:

```java
package com.example.devloop;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final String greeting;

    public GreetingController(
            @Value("${demo.greeting:hello}") String greeting) {
        this.greeting = greeting;
    }

    @GetMapping(
            value = "/hello",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return greeting;
    }
}
```

Controller có constructor injection từ property. Khi context được dựng lại sau restart, một bean `GreetingController` mới được tạo và nhận giá trị config hiện tại.

### 5.6. Static resource

Tạo `src/main/resources/static/notice.txt` với nội dung đúng một dòng:

```text
asset-v1
```

Spring MVC static resource mapping mặc định phục vụ file này qua `GET /notice.txt` khi server đang chạy. Ví dụ giả định không có security filter tùy chỉnh.

### 5.7. Khởi động development app

Windows PowerShell (terminal A):

```powershell
.\gradlew.bat bootRun
```

macOS/Linux (terminal A):

```bash
./gradlew bootRun
```

Chờ server startup hoàn tất (không chỉ đến khi Gradle bắt đầu compile). Khi Devtools hoạt động, log có thể cho thấy restart thread, nhưng **không dùng chính xác một tên thread làm assertion tuyệt đối** vì cách log có thể khác theo môi trường.

Mở terminal B:

```bash
curl -sS http://localhost:8080/hello
```

HTTP response body là:

```text
hello
```

Kiểm tra tài nguyên tĩnh:

```bash
curl -sS http://localhost:8080/notice.txt
```

HTTP body là:

```text
asset-v1
```

Lưu ý lệnh `curl -sS` có thể không tự thêm newline sau body; `hello` và `asset-v1` ở đây là **nội dung response**, không khẳng định terminal cursor xuống dòng đẹp. Nếu Windows PowerShell alias `curl` không hoạt động như lệnh curl thật, dùng `curl.exe -sS ...` hoặc `Invoke-RestMethod -Uri ...`.

### 5.8. Thí nghiệm A: sửa mã Java và quan sát restart

Trong `GreetingController.java`, đổi **chỉ body của method**:

Trước:

```java
public String hello() {
    return greeting;
}
```

Sau:

```java
public String hello() {
    return greeting + "-v2";
}
```

Đây là **đoạn sửa trong file Java đã đầy đủ**, không tạo method thứ hai cùng chữ ký.

Sau khi save, **phải bảo đảm file .class trong classpath được cập nhật**. Nếu IDE không tự compile, ở terminal B chạy:

macOS/Linux:

```bash
./gradlew classes
```

Windows PowerShell:

```powershell
.\gradlew.bat classes
```

Lệnh này build Java classes/resources. **Không cần dừng terminal A rồi chạy bootRun lại.** Khi `build/classes/java/main/.../GreetingController.class` thay đổi, Devtools phát hiện và restart context trong cùng JVM. Chờ quá trình startup lại thành công, rồi gọi:

```bash
curl -sS http://localhost:8080/hello
```

HTTP response body mới:

```text
hello-v2
```

Nếu vẫn thấy `hello`, chưa chắc Devtools lỗi: trước hết kiểm tra Gradle/IDE có thật sự compile file mới, terminal A còn sống, ứng dụng đang lấy class từ directory đúng và request có tới đúng port/process không.

### 5.9. Thí nghiệm B: sửa static resource không cần full restart

Đổi file `src/main/resources/static/notice.txt` từ:

```text
asset-v1
```

thành:

```text
asset-v2
```

Nếu IDE tự copy resource vào output directory, Devtools phát hiện thay đổi. Nếu không, chạy ở terminal B:

```bash
./gradlew processResources
```

Chờ `build/resources/main/static/notice.txt` được cập nhật và gọi:

```bash
curl -sS http://localhost:8080/notice.txt
```

HTTP response body mới:

```text
asset-v2
```

**Theo exclude mặc định của Boot 3.3, resource dưới `static/**` không gây full restart**; cơ chế LiveReload có thể gửi thông báo browser refresh nếu người dùng có client/extension và server LiveReload hoạt động. Vì devtools điều chỉnh các default caching trong development, static resource thường có thể phản ánh nội dung mới mà không cần khởi động lại toàn bộ application context.

Điều phải quan sát là thay đổi của **classpath resource output**, không chỉ file source chưa được copy. Nếu không thấy nội dung mới, kiểm tra `build/resources/main/static/notice.txt` thay vì lặp lại lệnh `bootRun`.

### 5.10. Thí nghiệm C: đổi cấu hình

Đổi `demo.greeting=hello` thành `demo.greeting=welcome` trong `application.properties`. Để Gradle copy vào classpath, chạy:

```bash
./gradlew processResources
```

Khi Devtools restart theo thay đổi tài nguyên cấu hình, controller mới nhận property `welcome`. Nếu vẫn giữ method `return greeting + "-v2";` của thí nghiệm A, endpoint trả:

```text
welcome-v2
```

Điều này minh họa **tái tạo bean và lấy lại cấu hình khi restart**. Nếu property được quản lý ở một nguồn ngoài classpath, không tự giả định mọi thay đổi ngoài đó đều được watcher theo dõi; cần thiết kế config refresh khác khi phù hợp.

### 5.11. Thí nghiệm D: build JAR production-like

Dừng `bootRun` local (ví dụ Ctrl+C), rồi build:

```bash
./gradlew bootJar
```

JAR tiêu chuẩn dự kiến ở:

```text
build/libs/devtools-loop-lab-0.0.1-SNAPSHOT.jar
```

Chạy:

```bash
java -jar build/libs/devtools-loop-lab-0.0.1-SNAPSHOT.jar
```

Vì `spring-boot-devtools` dùng `developmentOnly` và Boot packaging mặc định loại Devtools, **không mong JAR này tự restart** khi bạn sửa file `src/main/java` hoặc `src/main/resources`. Artifact JAR đã đóng gói chứa code/resources tại thời điểm build; thay đổi source sau đó **không làm JAR đổi**.

Có thể kiểm tra sơ bộ bằng:

```bash
jar tf build/libs/devtools-loop-lab-0.0.1-SNAPSHOT.jar
```

Khi đọc danh sách JAR, không nên thấy dependency `spring-boot-devtools` trong `BOOT-INF/lib` theo build config này. Nếu đóng gói đặc biệt cố tình include Devtools, kết luận phải kiểm lại build setup; **không bao giờ bật remote Devtools trên production**.


## 6. Property defaults: giảm rào cản cache trong development

Một lý do “tôi đã sửa template nhưng refresh vẫn thấy trang cũ” là browser hoặc framework template/resource cache. Trong production, caching rất hữu ích; trong development, nó có thể che thay đổi.

Khi Devtools có hiệu lực, Spring Boot 3.3 tự áp dụng một số **development-time property defaults**. Các ví dụ trong tài liệu chính thức:

| Property | Giá trị Devtools ưu tiên mặc định | Ý nghĩa |
| --- | --- | --- |
| `spring.thymeleaf.cache` | `false` | Không cache compiled Thymeleaf templates trong vòng phát triển |
| `spring.freemarker.cache` | `false` | Giảm cache của FreeMarker templates |
| `spring.web.resources.cache.period` | `0` | Không cache HTTP static resource theo thời gian trong development |
| `spring.web.resources.chain.cache` | `false` | Không cache resource chain như môi trường tối ưu production |
| `server.error.include-message` | `always` | Có thêm thông tin lỗi phục vụ debug |
| `server.error.include-binding-errors` | `always` | Hiển thị binding errors trong phản hồi lỗi thích hợp |
| `server.error.include-stacktrace` | `always` | Có thể đưa stack trace vào error responses của development setup |

**Cảnh báo bảo mật:** Các tùy chọn lỗi có thể tiết lộ thông tin nội bộ trong response. Đây là lý do **không đưa Devtools property defaults vào production**.

Nếu không muốn Devtools tự thêm các giá trị phát triển, đặt:

```properties
spring.devtools.add-properties=false
```

Điều này **tắt việc bổ sung property defaults**, không tự tắt automatic restart hoặc LiveReload. Nếu bạn ghi đè một property bằng cấu hình explicit với precedence phù hợp, cần xét effective configuration chứ không giả định Devtools luôn thắng mọi nguồn property.

### 6.1. LiveReload khác automatic restart

Devtools có thể chạy server **LiveReload** (cổng thường là `35729`). Nó gửi tín hiệu để browser client/extension hỗ trợ tự refresh trang khi có resource change. Để nhận được refresh, thông thường cần client/extension tương thích đang hoạt động, hoặc một integration tương đương.

Phân biệt:

- **Java class thay đổi:** Devtools có thể restart Spring application, rồi LiveReload báo browser tải lại khi thích hợp.
- **Static/template đổi:** Có thể chỉ cần copy resource và LiveReload/browser refresh, không restart context.
- **Browser không tự reload:** Devtools restart vẫn có thể diễn ra bình thường; kiểm tra LiveReload server và client.
- **LiveReload server chạy:** Không có nghĩa HTTP controller tự đổi; Java vẫn cần compile/restart.
- **JS HMR của Vite/Webpack:** Là một subsystem khác, không phải Devtools tự thay module frontend trong browser.

Chỉ **một LiveReload server** cùng lúc có thể bind cổng mặc định, nên khi chạy nhiều Spring Boot apps từ IDE, app khác có thể không khởi chạy được LiveReload. Muốn tắt riêng:

```properties
spring.devtools.livereload.enabled=false
```

Restart vẫn có thể hoạt động nếu `spring.devtools.restart.enabled` không bị tắt.

### 6.2. Các nhóm file có đường xử lý khác nhau

| File thay đổi | Cần compiler/build copy? | Full restart mặc định? | Kiểm chứng |
| --- | --- | --- | --- |
| `.java` | **Cần compile thành .class** | Có thể có sau classpath update | Gọi endpoint/kiểm log startup lại |
| `application.properties` trên classpath | Cần output resource được cập nhật | Thông thường có restart | Giá trị property ở bean mới |
| `static/**` / `public/**` | Cần file resource mới có sẵn cho runtime | **Không**, theo exclude mặc định | Gọi URL static/refresh browser |
| `templates/**` | Cần template được copy/cập nhật tại runtime | **Không**, theo exclude mặc định | Render lại template với cache dev disabled |
| File nằm ngoài classpath hoàn toàn | Không tự có nếu không watch/copy | Không mặc định | Cấu hình additional paths hoặc cơ chế riêng |
| Thay đổi dependency Gradle/Maven | Phải resolve/build lại classpath | Không phải mọi thay đổi đều hot restart an toàn | Khởi động lại `bootRun`/IDE nếu classpath library thay đổi |

**Không viết quy tắc “mọi thứ cứ Save là app restart”**. IDE, Gradle, resource mapping và classloader đều tác động tới kết quả.

## 7. Những cấu hình hữu ích khi vòng lặp quá nhiễu

### 7.1. Loại trừ tài nguyên không cần restart

Default excludes trong Boot 3.3 gồm các nhóm như `META-INF/maven/**`, `META-INF/resources/**`, `resources/**`, `static/**`, `public/**` và `templates/**`. Nếu thay đổi ở những đường này, Devtools thường không cần restart context nhưng vẫn có thể kích hoạt LiveReload.

**Cần phân biệt hai property:**

```properties
spring.devtools.restart.exclude=static/**,public/**
```

Property `exclude` **thay thế danh sách exclude mặc định** bằng danh sách bạn chỉ định. Nếu chỉ khai báo `static/**,public/**`, những default khác có thể **không còn bị exclude**.

Nếu muốn giữ default và **bổ sung** một pattern cho những file tạo ra thường xuyên, dùng:

```properties
spring.devtools.restart.additional-exclude=generated/**,reports/**
```

Mẫu trên không tự tạo directory hoặc build resource. Chỉ áp dụng khi đường file thực sự được watcher theo dõi trong môi trường local.

### 7.2. Watch thêm đường dẫn ngoài classpath

Với project có source generator, shared templates hoặc frontend assets nằm ngoài classpath, có thể dùng:

```properties
spring.devtools.restart.additional-paths=../shared-config
```

Giá trị chỉ là ví dụ path local. Thực tế phải điều chỉnh theo working directory và layout project; additional paths làm Devtools watch các file thay đổi, nhưng **không tự compile Java, không copy asset vào JAR hoặc giải quyết classpath của dependency**. Có thể kết hợp `exclude` để chọn trigger full restart hay LiveReload.

### 7.3. Dùng trigger file để chủ động chọn thời điểm restart

Khi IDE auto-build liên tục hoặc nhiều file được generate cùng lúc, developer có thể không muốn mỗi đợt file change tự gây restart. Spring Boot có cơ chế trigger file.

Đặt file rỗng trong classpath resource source:

```text
src/main/resources/.reloadtrigger
```

Cấu hình:

```properties
spring.devtools.restart.trigger-file=.reloadtrigger
```

Khi Devtools đã quan sát classpath changes, nó chỉ kiểm tra restart khi trigger file được cập nhật. **File trigger phải xuất hiện trên classpath và thay đổi tới classpath output**, không chỉ là một path ngẫu nhiên ngoài ứng dụng.

Quy trình thực tế:

1. Sửa nhiều file Java hoặc configuration.
2. Chạy compiler/build để classpath output cập nhật.
3. Cập nhật `.reloadtrigger` đã được copy vào classpath khi muốn kiểm tra restart.
4. Devtools đánh giá có thay đổi cần restart rồi thực hiện restart nếu cần.

Một lần sửa trigger file **không bảo đảm có restart** nếu không phát hiện thay đổi cần xử lý; property này dùng để điều tiết vòng lặp, không phải một nút cưỡng bức restart toàn bộ JVM.

### 7.4. Điều chỉnh watcher cho môi trường copy file chậm

Devtools watcher kiểm tra thay đổi theo chu kỳ rồi đợi **quiet period** để tránh restart trên một batch class files mới copy dở. Trên máy yếu, network-mounted project hoặc IDE compile nhiều modules, quiet period quá ngắn có thể khiến restart với classpath chưa đồng bộ.

Cấu hình ví dụ theo tài liệu:

```properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
```

Điều đó khiến watcher poll khoảng 2 giây và đợi khoảng 1 giây không thấy thêm thay đổi trước khi tiến hành restart. Hệ quả: feedback chậm hơn một ít, nhưng giảm nguy cơ restart nhiều lần hoặc đọc class files chưa copy đủ.

Chỉ thay đổi các giá trị này khi có bằng chứng: log restart lặp, `ClassNotFoundException` tạm thời khi build, IDE copy nhiều file. Không tự đặt poll interval cực nhỏ để “nhanh nhất”, vì có thể tăng overhead và khiến classpath không ổn định.

### 7.5. Log điều kiện auto-configuration

Mỗi khi restart, Devtools có thể log **condition evaluation delta**, hữu ích khi thay dependency, profile hoặc configuration property làm các bean tự động bật/tắt.

Nếu log quá nhiễu trong local dev:

```properties
spring.devtools.restart.log-condition-evaluation-delta=false
```

Đây không phải thuộc tính để tắt condition evaluation của Spring; nó chỉ điều khiển việc **log thay đổi của condition report** trên restart.

## 8. Tắt restart đúng cách khi cần

### 8.1. Tắt watcher bằng application.properties

```properties
spring.devtools.restart.enabled=false
```

Cấu hình này thường ngăn file watcher thực hiện automatic restart, nhưng Boot 3.3 lưu ý **restart classloader vẫn có thể được khởi tạo**. Điều đó có nghĩa: nếu đang debug một lỗi classloader, chỉ đặt property này trong config chưa chắc cho phép kiểm chứng app với một classloader bình thường.

### 8.2. Vô hiệu hóa restart classloader hoàn toàn

Đặt **JVM System property** trước khi gọi `SpringApplication.run(...)`:

```java
package com.example.devloop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevLoopApplication {

    public static void main(String[] args) {
        System.setProperty(
                "spring.devtools.restart.enabled", "false");
        SpringApplication.run(DevLoopApplication.class, args);
    }
}
```

Đây là **biến thể hoàn chỉnh thay cho file main mục 5.4**, không đặt cùng lúc hai class `DevLoopApplication`. Vì property được đặt sớm ở cấp System, Devtools có thể tránh khởi tạo restart support; phù hợp để cô lập lỗi classloader.

Tương đương trong launch arguments:

```bash
java -Dspring.devtools.restart.enabled=false -cp ... com.example.devloop.DevLoopApplication
```

Dòng này là **lệnh minh họa classpath**, dấu `...` đại diện classpath thật do IDE/build tool cung cấp; không phải câu lệnh chạy độc lập. Với Gradle `bootRun`, nên cấu hình JVM/system property của Java process nếu cần kiểm tra triệt để restart loader, không chỉ thêm argument ứng dụng `--spring.devtools.restart.enabled=false`.

### 8.3. Không nhầm các công tắc

| Property | Tác dụng |
| --- | --- |
| `spring.devtools.restart.enabled=false` | Tắt automatic restart (nếu đặt như app property, restart loader vẫn có thể tồn tại) |
| `System.setProperty("spring.devtools.restart.enabled","false")` trước `run` | Vô hiệu restart support sớm, hữu ích cho debug loader |
| `spring.devtools.livereload.enabled=false` | Tắt LiveReload server |
| `spring.devtools.add-properties=false` | Tắt development property defaults |
| Loại dependency Devtools khỏi classpath | Loại toàn bộ module/tiện ích của nó |

Khi debug, nên thử thay đổi **một trục mỗi lần** để biết vấn đề thuộc restart, browser reload hay property defaults.

## 9. Restart an toàn với state, threads và tài nguyên

Vì Devtools restart **đóng context cũ rồi tạo mới**, phải xem nó là một vòng đời application mới ở mức Spring. Các resource được bean sở hữu phải được cleanup:

- JDBC connection pools, HTTP clients, sockets, message consumers.
- Scheduled tasks/executors, watchers và background threads.
- Singleton caches và state lưu trong bean fields.
- Các đối tượng gắn với request/session.
- File handles, temp files và subscription tới broker.

Một ví dụ lifecycle:

```java
@Component
class LocalWorker {
    @PostConstruct
    void start() {
        // Chuẩn bị resource khi bean mới được tạo.
    }

    @PreDestroy
    void stop() {
        // Dọn resource thuộc sở hữu của bean trước khi context cũ đóng.
    }
}
```

Đây là **class minh họa**, cần imports `Component`, `PostConstruct` và `PreDestroy`, và không phải project runnable độc lập. Với worker vận hành lâu dài, cân nhắc `SmartLifecycle` để phối hợp start/stop phase, thay vì để thread sống bên ngoài Spring context.

### 9.1. Những thứ thường được reset khi restart

- Bean singleton state thường được tạo lại, không giữ state runtime như lần request trước.
- `static` fields của class ứng dụng có thể được load lại do restart classloader mới.
- Bộ nhớ cache chỉ nằm trong JVM/bean có thể mất hoặc không được khởi tạo như cũ.
- H2 in-memory database có thể được tạo lại tùy URL/lifecycle; **không coi Devtools là cơ chế bảo toàn dữ liệu**.
- Session persistence có thể có default development riêng, nhưng không vì thế mà mọi state ứng dụng được giữ.
- Số PID JVM có thể giữ nguyên trong Devtools restart; đó không phải bằng chứng Spring context chưa restart.

**Đừng dựa vào static field hoặc thread tự tạo để giữ state giữa hai lần restart.** Nếu muốn test mô hình dữ liệu bền vững, dùng database thực/testcontainer hoặc công cụ migration/fixture, không dựa vào cache trong JVM.

### 9.2. In-flight HTTP requests và restart

Khi Devtools đóng context cũ, web server có thể dừng và tạo lại. Một số client HTTP có thể gặp connection refused/reset/503 trong cửa sổ restart. Devtools không đưa ra cam kết zero-downtime rollout như một hệ thống Kubernetes load balancer.

Chỉ dùng nó để tăng tốc developer feedback, không làm cơ chế deploy cho traffic production.

### 9.3. Startup failure và hồi phục

Nếu mã Java mới không compile, IDE/Gradle **không tạo classpath output hợp lệ** để Devtools có thể restart với code mới. Nếu compile thành công nhưng bean initialization lỗi, Devtools có thể thử restart rồi ứng dụng không khởi động lại thành công. Cần đọc root cause, sửa lỗi, compile lần nữa; đừng giả định Devtools tự rollback một bản build lỗi.

Trong một số tình huống, watcher và context có thể ở trạng thái bất thường; restart thủ công `bootRun` là biện pháp phục hồi hợp lệ khi kiểm chứng vấn đề kỹ thuật đã được sửa. Nó không thay thế việc hiểu classloader failure.


## 10. Khi nào cấu hình restart classloader?

Trong multi-module projects, Devtools có thể chia nhầm classpath entries giữa base và restart classloaders. Ví dụ một internal library module đóng thành JAR chứa annotation/custom converter nhưng lại bị loader khác load so với main app.

Hậu quả có thể là:

```text
ClassCastException:
  com.example.api.Type cannot be cast to com.example.api.Type

ClassNotFoundException / NoSuchMethodError / annotation not visible
```

Thông báo “một kiểu class không cast được sang chính tên class ấy” thường liên quan classloader identity; **tên class giống nhau chưa đủ**, classloader cũng là thành phần của identity tại runtime.

Trình tự xử lý:

1. **Xác nhận chỉ lỗi khi Devtools restart đang bật.** Tắt restart hoàn toàn bằng system property trước `run` và so sánh.
2. Xác định class/library được load bởi base hay restart loader, nơi nào giữ reference dài hạn.
3. Kiểm tra dependency graph, cách module được đưa vào classpath (directory hay JAR).
4. Khi thực sự cần, thêm `META-INF/spring-devtools.properties` để chuyển classpath entries giữa hai loaders.
5. Kiểm tra lại bằng full cold start và nhiều lần Devtools restart, không chỉ một lần khởi động.

### 10.1. Cấu trúc file cấu hình

```text
src/main/resources/META-INF/spring-devtools.properties
```

Các key dạng:

```properties
restart.include.myshared=/myshared-[\\w\\d\\-\\.]+\\.jar
restart.exclude.localmodule=/my-local-module/(build|bin|out)/
```

Đây là **pattern minh họa**, cần điều chỉnh theo classpath real của project. `restart.include.*` yêu cầu đưa entry phù hợp vào restart classloader; `restart.exclude.*` yêu cầu đưa entry phù hợp về base loader. Giá trị là **regex áp dụng lên classpath URL/path**, không phải Ant path pattern của `spring.devtools.restart.exclude`.

Những key phải **duy nhất**. Spring Boot đọc các `META-INF/spring-devtools.properties` tìm thấy trên classpath. Không nhầm file này với `application.properties` hoặc cấu hình global devtools.

### 10.2. Vì sao không làm mặc định ở mọi module?

Điều chỉnh classloader sai có thể tăng memory footprint, làm restart chậm và che lỗi thiết kế serialization/circular dependencies. Khi mọi thứ hoạt động đúng, hãy để Boot tự chia hai loader; chỉ sửa sau khi có reproduction và hiểu nguyên nhân.

### 10.3. Deserialization và Thread Context ClassLoader

Java `ObjectInputStream` mặc định hoặc framework dùng reflection có thể không nhìn thấy class mới từ restart loader nếu classloader được chọn không phù hợp. Với trường hợp thực sự cần deserialize dữ liệu trong Spring application, Spring có `ConfigurableObjectInputStream` có thể dùng context classloader tương ứng.

Đây là kỹ thuật chẩn đoán sâu, không phải một bước bắt buộc để bật Devtools. Trước khi can thiệp, hãy xác nhận sự cố biến mất khi restart disabled và kiểm tra thư viện liên quan.

## 11. Production boundary và nguyên tắc bảo mật

### 11.1. Tại sao Devtools không nên được đóng gói lên production?

Devtools có default ưu tiên developer convenience như:

- Cache bị hạn chế/tắt cho template/static resources.
- Error responses có thể hiển thị thông tin nhiều hơn.
- Classpath watcher và cơ chế restart.
- LiveReload server và khả năng remote development nếu cố bật.

Những điều này không phù hợp mặc định cho ứng dụng phục vụ người dùng thật. Ngoài hiệu năng và ổn định, việc hiển thị error details hoặc mở remote devtools endpoint có **nguy cơ lộ thông tin/chức năng điều khiển**.

**Chuẩn phù hợp:** Development chỉ dùng `developmentOnly` hoặc Maven optional; artifact production dùng `bootJar`/`repackage` mặc định loại devtools. Kiểm tra dependency tree và nội dung executable JAR trước release. Không bật `spring.devtools.remote.secret` trên production.

### 11.2. Devtools không phải remote hotfix

Nếu một bug xuất hiện trong production, cần build/test artifact mới, thực hiện rollout theo quy trình và theo dõi health/rollback. Đừng dùng Devtools để “đẩy class mới lên container đang sống” nhằm tránh deploy. Remote Devtools chỉ là tính năng phát triển opt-in và tài liệu Boot khuyến cáo không bật trong production.

### 11.3. Cẩn thận với data thật ngay cả khi chỉ là local dev

Một ứng dụng chạy local với Devtools vẫn có thể đang trỏ tới production database, broker hoặc remote API. Restart nhanh và lặp lại startup runner có thể gửi request hay chạy migration nhiều lần.

- Dùng profile/dev credentials riêng.
- Chặn thao tác ghi tới hệ thống production khi chạy local.
- Thiết kế `ApplicationRunner`, `@PostConstruct`, `SmartLifecycle.start()` idempotent và đúng ownership.
- Có timeout, không mở quá nhiều connection khi restart lặp.
- Đặt dữ liệu test trong môi trường tách biệt.

Devtools giúp lặp nhanh **cả code đúng lẫn bug và side effects**, nên cần giữ ranh giới dữ liệu.

## 12. Checklist chẩn đoán khi Devtools không restart

1. **Đã có dependency chưa?** Trong Gradle cần `developmentOnly 'org.springframework.boot:spring-boot-devtools'`.
2. **App chạy kiểu nào?** IDE/`bootRun` khác `java -jar` packaged; JAR thường không chứa devtools.
3. **Classpath output có thay đổi?** Kiểm `build/classes/java/main` hoặc `target/classes` sau khi compile.
4. **IDE có auto-build không?** Save `.java` không đủ nếu compiler chưa cập nhật `.class`.
5. **Có bật trigger file?** Nếu có, phải cập nhật đúng file trong classpath.
6. **File thuộc exclude không?** `static/**` và `templates/**` thường chỉ cần LiveReload, không full restart.
7. **Property restart.enabled có bị tắt?** Kiểm app config và JVM system properties.
8. **Có JRebel/AspectJ weaving/custom launcher không?** Có những trường hợp Devtools restart không được hỗ trợ hoặc không được dùng.
9. **Context shutdown hook có bị vô hiệu?** Devtools cần close context đúng khi restart.
10. **Watcher có bỏ lỡ batch file copy?** Thử điều chỉnh poll interval/quiet period dựa trên bằng chứng.
11. **Có lỗi từ restart classloader?** Thử tắt restart sớm, kiểm modules và serialization.
12. **Có hai process bind cùng port?** Có thể request đang tới JAR cũ/IDE khác, không phải app vừa compile.
13. **Có proxy/browser caching?** Dùng `curl` trực tiếp hoặc disable client cache để phân biệt.
14. **Server đã startup lại thành công?** Root cause có thể là bean startup fail, không phải watcher.
15. **Resource mới có ở output path?** Source đã sửa nhưng `processResources` chưa copy thì runtime chưa thấy.
16. **Devtools đang kích hoạt quá nhiều restart?** Kiểm generated files, excludes và trigger file.
17. **Livereload browser không chạy?** Kiểm extension/server/port; Java restart có thể vẫn đúng.
18. **Đã cô lập môi trường?** Gradle daemon, IDE output directory và target Java process phải thống nhất.

### 12.1. Bảng tình huống nhanh

| Triệu chứng | Giải thích thường gặp | Việc kiểm tra đầu tiên |
| --- | --- | --- |
| Sửa `.java`, Save nhưng API vẫn trả cũ | Không có classpath class mới | Compile và kiểm `.class` |
| Chạy `java -jar` không restart | Packaged app production-like | Dùng `bootRun` để development |
| CSS đổi nhưng không có log startup mới | Resource bị exclude khỏi full restart | Refresh trình duyệt, kiểm static file |
| Log có restart nhưng HTTP vẫn là giá trị cũ | Request sai process/port, code chưa đúng, cache | `curl` trực tiếp và kiểm URL/PID |
| Restart liên tiếp nhiều lần | IDE copy nhiều batch hoặc generated files | Trigger file, quiet period, exclude |
| Cứ restart thì lộ ClassCastException lạ | Class bị load ở hai loader khác nhau | Tắt restart, xem spring-devtools.properties |
| Đã bật LiveReload nhưng browser không tự refresh | Thiếu client/extension hoặc port xung đột | Kiểm LiveReload server và browser integration |
| Thấy static mới nhưng Java method vẫn cũ | Static file không cần compile Java | Build Java classes, chờ restart |
| Devtools disabled dù dependency có trong POM | Chạy packaged app, thiếu dev classpath, config off | Kiểm launch mode và runtime classpath |
| Tắt `spring.devtools.add-properties` vẫn restart | Property chỉ điều khiển defaults | Dùng `spring.devtools.restart.enabled` khi muốn tắt restart |
| App bị startup failure sau khi compile | Code/config mới lỗi | Đọc root exception, sửa và compile lại |
| Devtools làm task khởi tạo chạy nhiều lần | Restart context tạo bean/runner mới | Thiết kế startup idempotent |
| Template không đổi dù file source mới | Template chưa copy hoặc template cache còn tác dụng | Kiểm output path và effective cache config |
| Devtools tự “dừng” khi debug | Launcher, shutdown hook hoặc classloader issue | Xem logs và cách run, không đổ lỗi ngay cho watcher |

## 13. Thực hành và câu hỏi tự đánh giá

**Câu 1.** `spring-boot-devtools` giúp rút ngắn bước nào trong vòng lặp sửa–kiểm thử?

**Đáp:** Giúp restart Spring application khi classpath output đổi, giảm thao tác stop/start thủ công, đồng thời hỗ trợ property defaults/LiveReload. Compiler và test vẫn là phần việc riêng.

**Câu 2.** Tại sao chỉ Save file Java có thể chưa restart?

**Đáp:** Devtools theo dõi classpath directory chứ không tự compile source. Cần IDE/Gradle/Maven tạo `.class` mới.

**Câu 3.** Restart của Devtools có phải chạy JVM process mới không?

**Đáp:** Không theo cơ chế mặc định. Devtools thay restart classloader và tạo lại context trong cùng JVM, có thể nhanh hơn cold start.

**Câu 4.** Tại sao sửa `static/app.css` có thể không restart context?

**Đáp:** Resource tĩnh thuộc default excludes; nội dung mới có thể được phục vụ/LiveReload mà không cần full restart.

**Câu 5.** `spring.devtools.restart.exclude` khác `additional-exclude` như thế nào?

**Đáp:** `exclude` thay danh sách excludes mặc định; `additional-exclude` bổ sung vào default list.

**Câu 6.** Muốn tắt LiveReload nhưng vẫn dùng auto restart?

**Đáp:** Đặt `spring.devtools.livereload.enabled=false`, giữ restart enabled.

**Câu 7.** Tại sao cần `developmentOnly` trong Gradle?

**Đáp:** Vì Devtools là công cụ development, không phải dependency production. Nó được sử dụng ở `bootRun` nhưng không nên transitive/đóng gói vào JAR phát hành mặc định.

**Câu 8.** Nếu chạy `java -jar` một executable archive đã build với cấu hình chuẩn, sửa `src/main/java` có làm JAR tự cập nhật không?

**Đáp:** Không. JAR là artifact đã đóng gói và Devtools mặc định disabled/excluded ở môi trường packaged.

**Câu 9.** Vì sao hiện tượng “Class X cannot be cast to Class X” có thể xuất hiện?

**Đáp:** Hai bản class cùng tên được load từ classloaders khác nhau nên không cùng runtime type identity. Kiểm tra base/restart loader.

**Câu 10.** Có phải LiveReload là HMR của Vite/Webpack?

**Đáp:** Không. LiveReload báo browser refresh; nó không thay mọi module frontend ngay trong memory theo semantics của HMR.

**Câu 11.** `spring.devtools.add-properties=false` có tắt auto restart không?

**Đáp:** Không. Nó tắt development property defaults, không điều khiển restart watcher.

**Câu 12.** Muốn hoàn toàn loại restart classloader khi debug lỗi thư viện?

**Đáp:** Đặt `System.setProperty("spring.devtools.restart.enabled","false")` trước `SpringApplication.run` hoặc loại dependency Devtools khỏi classpath.

**Câu 13.** Vì sao Devtools có thể làm `@PostConstruct` của bean chạy nhiều lần trong một phiên IDE?

**Đáp:** Mỗi restart tạo ApplicationContext mới nên bean singleton được khởi tạo lại.

**Câu 14.** Có nên bật remote devtools để sửa JAR production mà không cần deploy?

**Đáp:** Không. Tài liệu Spring Boot khuyến cáo không bật remote devtools trong production vì rủi ro bảo mật.

**Câu 15.** Đã có trigger file mà không có classpath changes cần xử lý, liệu chạm trigger có chắc restart?

**Đáp:** Không. Trigger file yêu cầu Devtools kiểm tra lại, chỉ restart nếu đã phát hiện thay đổi thích hợp.

**Câu 16.** Khi startup sau restart thất bại, cần nhìn đâu?

**Đáp:** Root stacktrace/`APPLICATION FAILED TO START`, compile output, thay đổi config/dependencies và tình trạng resources. Devtools không tự sửa hay rollback lỗi nghiệp vụ.

## 14. Tóm tắt và tài liệu tham khảo

### 14.1. Những nguyên tắc cần nhớ

- **Devtools là công cụ của vòng lặp phát triển cục bộ**, không phải thành phần cần chạy trong production.
- **Java source → compile → classpath update → Devtools restart** là chuỗi quan trọng. Save chưa chắc đủ.
- **Restart dùng hai classloaders**, thường nhanh hơn cold start, nhưng vẫn tạo lại Spring ApplicationContext và bean state.
- **Static/template resources** thường được loại khỏi full restart; dev cache defaults và LiveReload giúp feedback nhanh.
- **LiveReload chỉ gợi ý browser refresh**, không compile Java hoặc thay thế JRebel/frontend HMR.
- **`developmentOnly` / Maven optional**, Boot packaging mặc định loại hoặc vô hiệu Devtools trong executable JAR.
- **Chỉ điều chỉnh** `additional-exclude`, `additional-paths`, trigger file, poll/quiet period khi có nhu cầu rõ.
- **Chủ động thử tắt restart** nếu gặp lỗi classloader hoặc serialization bất thường.
- **Không bật remote devtools ở production**, không để error-detail defaults lộ dữ liệu thật.

### 14.2. Tài liệu chính thức cho Spring Boot 3.3

1. [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html): dependency, automatic restart, LiveReload, property defaults và troubleshooting.
2. [Spring Boot 3.3 — Running Your Application](https://docs.spring.io/spring-boot/3.3/reference/using/running-your-application.html): IDE, Gradle/Maven launcher và chế độ development.
3. [Spring Boot 3.3 — Gradle Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reference/htmlsingle/): `bootRun`, `bootJar` và `developmentOnly`.
4. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): các property `spring.devtools.*` và giá trị mặc định.
5. [Spring Boot 3.3 — Packaging for Production](https://docs.spring.io/spring-boot/3.3/reference/using/packaging-for-production.html): ranh giới executable artifact và development runtime.

**Kết luận:** `spring-boot-devtools` làm ngắn vòng lặp **sửa → biên dịch → thấy ứng dụng phản hồi với code mới** bằng restart nhanh, default caching thuận tiện và LiveReload. Giá trị của nó nằm ở **developer feedback**, không phải thay compiler, test suite, release pipeline hay cơ chế vận hành an toàn.
