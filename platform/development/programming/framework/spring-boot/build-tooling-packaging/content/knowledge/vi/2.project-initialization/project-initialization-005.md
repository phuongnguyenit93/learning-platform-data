# Quản lý `src/main`, `src/test` và tài nguyên đi kèm trong dự án Spring Boot

Trong bước **khởi tạo dự án Spring Boot**, cách đặt mã nguồn và tài nguyên quyết định những gì được biên dịch, những gì có trên **classpath** khi chạy, những gì chỉ phục vụ kiểm thử và những gì đi vào gói triển khai. Maven và Gradle có quy ước thư mục gần như giống nhau; tuân thủ các quy ước này giúp IDE, build tool, bài kiểm thử và file JAR hoạt động nhất quán.

Sau bài này, bạn có thể: xác định đúng nơi đặt từng loại file; giải thích sự khác nhau giữa classpath chính và classpath kiểm thử; đọc resource khi ứng dụng đã đóng gói; quản lý cấu hình, dữ liệu kiểm thử và tài nguyên web; kiểm tra kết quả build; và nhận diện những lỗi thường gặp.

## 1. Bốn thư mục nguồn cốt lõi

Một cấu trúc phổ biến của ứng dụng Spring Boot dùng Java:

```text
demo/
├── build.gradle                 # Gradle (hoặc pom.xml nếu dùng Maven)
├── settings.gradle
├── gradlew                      # Gradle Wrapper
├── gradlew.bat                  # Wrapper cho Windows
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/demo/
    │   │       ├── DemoApplication.java
    │   │       └── GreetingService.java
    │   └── resources/
    │       ├── application.yml
    │       ├── greeting.txt
    │       ├── static/
    │       │   └── index.html
    │       └── templates/
    │           └── welcome.html
    └── test/
        ├── java/
        │   └── com/example/demo/
        │       └── GreetingServiceTest.java
        └── resources/
            ├── application-test.yml
            └── fixtures/
                └── sample-order.json
```

Các thư mục có vai trò khác nhau:

| Đường dẫn | Nội dung nên đặt | Được dùng ở đâu? | Có trong JAR ứng dụng thông thường? |
| --- | --- | --- | --- |
| `src/main/java` | Lớp Java chạy thật: lớp `@SpringBootApplication`, controller, service, configuration, model | Biên dịch thành `.class` trên classpath chính | **Có**, dưới dạng class đã biên dịch |
| `src/main/resources` | `application.yml`, file văn bản, template, static assets, metadata cấu hình | Được xử lý/sao chép lên classpath chính | **Có**, trừ khi có cấu hình loại trừ |
| `src/test/java` | Unit test, integration test và mã hỗ trợ test | Biên dịch/chạy trong pha kiểm thử | **Không** nằm trong executable JAR theo quy ước |
| `src/test/resources` | Fixture JSON/CSV, cấu hình và file mẫu chỉ dành cho test | Có trên classpath kiểm thử | **Không** nằm trong executable JAR theo quy ước |

`src/main` và `src/test` là **hai nhóm nguồn** (source sets) của dự án, không phải tên package Java. Ví dụ, lớp ở `src/main/java/com/example/demo/GreetingService.java` khai báo `package com.example.demo;`. Lớp test có thể dùng cùng package, nhưng đặt dưới `src/test/java`.

Khi dùng Maven, file cấu hình là `pom.xml`; với Gradle, thường là `build.gradle` hoặc `build.gradle.kts`. Các tên file build khác nhau nhưng bốn thư mục nguồn mặc định giống nhau.

## 2. Build tool biến các thư mục thành classpath như thế nào?

**Classpath** là tập vị trí mà Java/Spring tra cứu class và tài nguyên khi chạy.

- **Classpath chính (main):** class được biên dịch từ `src/main/java` cùng các resource từ `src/main/resources` và thư viện runtime cần thiết.
- **Classpath kiểm thử (test):** class/test resource từ `src/test`, cộng thêm class/resource chính và các dependency chỉ dành cho test, chẳng hạn JUnit.
- **Classpath khi chạy executable JAR:** class/resource chính và các dependency được đóng gói phù hợp; không mặc định chứa mã hoặc fixture từ `src/test`.

Luồng mặc định:

```text
src/main/java       --compileJava (Gradle)----------> class chính
src/main/resources  --processResources--------------> resource chính
                                                     \
                                                      +--> bootJar / package --> JAR chạy thật
src/test/java       --compileTestJava---------------> class kiểm thử
src/test/resources  --processTestResources----------> resource kiểm thử
                                                     \
                                                      +--> test (dùng thêm class/resource chính)
```

Tên `compileJava`, `processResources`, `compileTestJava`, `processTestResources`, `test` và `bootJar` là task thường gặp của Gradle. Maven thực hiện những việc tương ứng qua các pha `process-resources`, `compile`, `process-test-resources`, `test-compile`, `test` và `package`.

Vị trí đầu ra điển hình:

| Loại kết quả | Gradle | Maven |
| --- | --- | --- |
| Class chính | `build/classes/java/main` | `target/classes` |
| Resource chính | `build/resources/main` | `target/classes` |
| Class test | `build/classes/java/test` | `target/test-classes` |
| Resource test | `build/resources/test` | `target/test-classes` |

**Đừng sửa trực tiếp `build/` hoặc `target/`**: đây là đầu ra được tạo lại khi build. File cần duy trì lâu dài phải nằm trong thư mục nguồn hoặc cấu hình được quản lý phù hợp.

## 3. Đọc resource theo classpath: ví dụ chạy được trong một dự án Spring Boot

Giả sử bạn muốn đặt một câu chào trong file dữ liệu và dùng từ mã Java mà không cố định đường dẫn tới thư mục dự án.

**Bước 1 — Tạo `src/main/resources/greeting.txt`** với nội dung:

```text
Xin chào từ classpath!
```

**Bước 2 — Tạo `src/main/java/com/example/demo/GreetingService.java`:**

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class GreetingService {

    public String loadGreeting() throws IOException {
        try (InputStream input = GreetingService.class
                .getClassLoader()
                .getResourceAsStream("greeting.txt")) {

            if (input == null) {
                throw new IOException("Không tìm thấy greeting.txt trên classpath");
            }

            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }
}
```

`getResourceAsStream("greeting.txt")` tìm file từ **gốc classpath**. File nằm ngay trong `src/main/resources` nên đường dẫn tra cứu là `greeting.txt`, không phải `src/main/resources/greeting.txt`. `try-with-resources` tự đóng stream; `StandardCharsets.UTF_8` tránh phụ thuộc charset mặc định; `strip()` bỏ dấu xuống dòng ở cuối file.

**Bước 3 — Tạo `src/test/java/com/example/demo/GreetingServiceTest.java`:**

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    @Test
    void readsMainResourceFromTestClasspath() throws IOException {
        GreetingService service = new GreetingService();

        assertEquals(
                "Xin chào từ classpath!",
                service.loadGreeting()
        );
    }
}
```

Bài test truy cập được `GreetingService` và `greeting.txt` vì **classpath test bao gồm đầu ra main**. Đây là một lớp được JUnit chạy, không phải chương trình Java có phương thức `main` độc lập. Ví dụ dùng cú pháp tương thích Java 17+ và yêu cầu JUnit Jupiter trên test classpath. Trong dự án Spring Boot tạo từ Initializr, dependency `spring-boot-starter-test` thường đáp ứng phần này; với Gradle cần bảo đảm task `test` được cấu hình dùng JUnit Platform.

**Bước 4 — Chạy kiểm thử từ thư mục gốc dự án:**

```bash
# macOS / Linux, dự án Gradle
./gradlew test

# macOS / Linux, dự án Maven
./mvnw test
```

Trên Windows PowerShell, dùng `.\gradlew.bat test` hoặc `.\mvnw.cmd test`. Nếu dự án chưa có wrapper, chạy `gradle test` hoặc `mvn test` khi công cụ đã được cài đặt. Với Gradle sử dụng JUnit Jupiter, cấu hình thường thấy trong `build.gradle` (Groovy DSL) là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ bổ sung những dòng còn thiếu; không khai báo trùng dependency đã có. Nếu test chạy thành công, JUnit xác nhận chuỗi thực đọc từ resource là `Xin chào từ classpath!`; không cần đoán một dòng stdout cố định của Gradle/Maven vì phần log tùy phiên bản và cấu hình.

**Vì sao không dùng `new File("src/main/resources/greeting.txt")`?** Đường dẫn đó phụ thuộc working directory và file nguồn còn tồn tại trên ổ đĩa. Khi chạy `java -jar` trên máy khác, resource thường nằm **bên trong JAR**, không còn là file độc lập ở đường dẫn nguồn. API classpath như `ClassLoader.getResourceAsStream` hoặc Spring `ClassPathResource` đọc được nội dung đã đóng gói. Nếu cần ghi dữ liệu thay đổi lúc runtime, hãy dùng thư mục bên ngoài JAR, không ghi ngược vào resource đóng gói.

## 4. Phân biệt resource ứng dụng, cấu hình và dữ liệu kiểm thử

### 4.1. Cấu hình Spring Boot

`src/main/resources/application.yml` chứa cấu hình mặc định được đóng gói cùng ứng dụng:

```yaml
app:
  display-name: "Demo"
logging:
  level:
    root: INFO
```

`src/test/resources/application-test.yml` có thể cung cấp giá trị cho profile kiểm thử:

```yaml
app:
  display-name: "Demo Test"
```

Trong một Spring test có khởi tạo application context, dùng `@ActiveProfiles("test")` để kích hoạt profile `test`; khi đó Spring Boot có thể nạp `application-test.yml` và áp dụng các quy tắc ưu tiên cấu hình. Chỉ đặt file `application-test.yml` trong `src/test/resources` **không tự kích hoạt** profile `test`. Đối với bài test Java/JUnit thuần ở mục 3, Spring context và profile cũng không tự được khởi tạo.

Phân biệt:
- `application.yml` ở main có thể đi vào gói triển khai.
- `application-test.yml` ở test chỉ phục vụ kiểm thử của build hiện tại và không đi vào executable JAR theo mặc định.
- `application-dev.yml` hoặc `application-prod.yml` ở main là các cấu hình profile **có thể được đóng gói**; tên profile không tự giữ bí mật nội dung của file.

Không lưu mật khẩu, access token hoặc private key thật trong tài nguyên được commit/đóng gói. Dùng biến môi trường, secret manager hoặc cấu hình bên ngoài theo môi trường triển khai. Cấu hình bên ngoài có thể ghi đè giá trị đóng gói tùy thứ tự ưu tiên của Spring Boot.

### 4.2. Tài nguyên web và template

Các đường dẫn thường gặp dưới `src/main/resources`:

| Thư mục | Vai trò | Cần chú ý |
| --- | --- | --- |
| `static/` | HTML, CSS, JavaScript, hình ảnh tĩnh | Với Spring MVC/WebFlux được cấu hình phù hợp, có thể phục vụ trực tiếp qua HTTP; không đặt dữ liệu bí mật |
| `public/` | Một vị trí mặc định khác cho static assets | Tránh tạo tài nguyên trùng URL khó kiểm soát |
| `templates/` | Mẫu HTML cho template engine, ví dụ Thymeleaf | Cần dependency và cấu hình template engine để render; chỉ đặt file ở đây không tự tạo endpoint |
| `META-INF/` | Metadata theo quy ước Java/thư viện | Đường dẫn và tên file phải đúng quy ước của tính năng dùng nó |

Ví dụ, `src/main/resources/static/index.html` có thể là welcome page của ứng dụng web Spring Boot khi điều kiện xử lý static/welcome page được đáp ứng. Trong khi đó, `templates/welcome.html` không tự trở thành một URL; thường cần controller trả về tên view và template engine tương ứng.

### 4.3. Fixture riêng cho test

Đặt JSON, CSV, script dữ liệu mẫu hay response giả ở `src/test/resources`:

```text
src/test/resources/
└── fixtures/
    └── sample-order.json
```

Trong test, tra cứu bằng đường dẫn classpath `fixtures/sample-order.json`. Điều này giữ dữ liệu mẫu tách khỏi bản triển khai và giúp test chạy nhất quán trên máy lập trình lẫn CI.

Nếu `src/main/resources` và `src/test/resources` có file cùng đường dẫn tương đối, tài nguyên test có thể che khuất tài nguyên main tùy thứ tự classpath. Chỉ dùng cách ghi đè này khi chủ ý và có kiểm thử xác nhận; ưu tiên tên/path rõ ràng để tránh test chạy khác môi trường.

## 5. Đổi đường dẫn resource khi thật sự cần

**Ưu tiên quy ước mặc định.** Chỉ cấu hình thêm thư mục ngoài `src/main/resources` khi có lý do cụ thể, chẳng hạn module có một thư mục tài nguyên chung do build quản lý.

Ví dụ **Gradle Groovy DSL** thêm `shared/config` vào resource main mà vẫn giữ đường dẫn mặc định:

```groovy
sourceSets {
    main {
        resources {
            srcDir 'shared/config'
        }
    }
}
```

Gradle xử lý file trong các thư mục resource main để đưa vào classpath; `srcDir` bổ sung một thư mục nguồn. Nếu hai thư mục chứa cùng đường dẫn đích, cần giải quyết trùng lặp có chủ đích theo cấu hình xử lý resource của dự án.

Ví dụ **Maven** khi khai báo resource bổ sung trong `pom.xml`, liệt kê cả thư mục mặc định vì khối `<resources>` được khai báo có thể thay thế cấu hình resource mặc định:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
        </resource>
        <resource>
            <directory>shared/config</directory>
        </resource>
    </resources>
</build>
```

Các ví dụ chỉ sửa đường dẫn resource main; chúng **không** đưa `src/test/resources` vào gói production. Cũng không cần chuyển file Java vào thư mục resources hoặc tự copy file từ `src/main/resources` sang `build/` hay `target/` bằng tay.

Khi cần biến đổi nội dung resource trong lúc build, có thể dùng `processResources` của Gradle hoặc resource filtering của Maven. Chỉ bật cho file cần thiết: lọc nhầm `application.yml` có placeholder do Spring xử lý, thay thế không mong muốn hoặc đưa giá trị bí mật vào file đóng gói có thể gây lỗi vận hành/bảo mật. Kiểm tra **nội dung file sau xử lý**, không chỉ file nguồn.

## 6. Kiểm tra đầu ra và nội dung JAR

Với một ứng dụng có Spring Boot Gradle plugin và Java plugin được cấu hình để tạo executable JAR:

```bash
./gradlew clean test bootJar
```

Với Maven Wrapper và Spring Boot Maven plugin được cấu hình cho repackage:

```bash
./mvnw clean verify
```

Trên Windows thay bằng `.\gradlew.bat clean test bootJar` hoặc `.\mvnw.cmd clean verify`. Lệnh và file JAR cụ thể tùy tên project, version, plugin và chế độ đóng gói; không giả định mọi dự án đều tạo executable JAR.

Sau khi build, kiểm tra:

1. **Đầu ra main:** `build/classes/java/main` và `build/resources/main` (Gradle), hoặc `target/classes` (Maven) có class/resource như mong đợi.
2. **Đầu ra test:** các thư mục test chứa class và fixture phục vụ `test`, không dùng làm dữ liệu runtime của ứng dụng.
3. **File JAR:** chạy `jar tf <đường-dẫn-file-jar>` với đúng đường dẫn sản phẩm vừa tạo. Với Spring Boot executable JAR kiểu phổ biến, tìm `BOOT-INF/classes/com/example/demo/GreetingService.class` và `BOOT-INF/classes/greeting.txt`; dependency thường nằm dưới `BOOT-INF/lib/`.
4. **Không lẫn test:** `GreetingServiceTest.class` và `fixtures/sample-order.json` không nên xuất hiện trong executable JAR mặc định.

`jar tf` là lệnh của JDK để **liệt kê** nội dung archive; nó không chạy ứng dụng. Nếu dùng plain JAR, WAR hay bố cục packaging khác, đường dẫn nội bộ có thể khác `BOOT-INF/classes`. Kiểm tra theo artifact thực tế, tránh dựa hoàn toàn vào tên file nguồn.

## 7. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chạy trong IDE được nhưng `java -jar` báo không tìm thấy file | Dùng đường dẫn tương đối `src/main/resources/...` như đường dẫn filesystem | Đọc bằng classpath stream/`ClassPathResource`; đối chiếu file trong JAR |
| `getResourceAsStream` trả `null` | Sai đường dẫn hoặc file không được copy vào resource output | Xác nhận file thuộc `src/main/resources`/`src/test/resources` đúng mục đích; tìm bằng đường dẫn tính từ gốc classpath |
| Test compile lỗi `package org.junit.jupiter.api does not exist` | Thiếu dependency test hoặc cấu hình JUnit | Bổ sung `spring-boot-starter-test` đúng scope/configuration và cấu hình test engine phù hợp |
| Test thấy dữ liệu khác runtime | File cùng tên giữa main/test hoặc profile test đang active | Kiểm tra đường dẫn, thứ tự classpath, profile và các nguồn cấu hình |
| File fixture xuất hiện trong ứng dụng triển khai | Đặt nhầm fixture ở main hoặc tự copy từ test sang main | Chuyển sang `src/test/resources` và bỏ rule copy nhầm |
| Sửa file trong `build/` hoặc `target/` nhưng chạy lại mất | Sửa output thay vì nguồn | Sửa ở `src/...`, build lại và kiểm tra artifact |
| Tài nguyên web không truy cập được | Đặt nhầm dưới `templates`, thiếu web stack hoặc cấu hình static | Đặt asset tĩnh dưới `static`/`public`; xác nhận web dependency và routing |
| Giá trị config theo profile không được áp dụng | Profile chưa kích hoạt hoặc cấu hình ngoài ghi đè | Kiểm tra active profiles và thứ tự ưu tiên property sources |

## 8. Checklist khi khởi tạo hoặc mở rộng dự án

- [ ] Mã ứng dụng ở `src/main/java` và package khớp đường dẫn logic; test ở `src/test/java`.
- [ ] Cấu hình/resource cần chạy thật ở `src/main/resources`; fixture và cấu hình chỉ dùng trong test ở `src/test/resources`.
- [ ] Mã dùng resource qua **classpath**, không phụ thuộc working directory hay thư mục source tồn tại sau khi package.
- [ ] Test có dependency và test engine thích hợp; profile test được kích hoạt có chủ đích.
- [ ] Static assets và template được đặt đúng chỗ, có dependency/runtime tương ứng.
- [ ] Không đóng gói nhầm bí mật hoặc dữ liệu test; không sửa đầu ra build thủ công.
- [ ] Chạy test và kiểm tra JAR để xác nhận class/resource cần thiết đã được đóng gói, test resource không bị lẫn.

**Nguyên tắc quyết định:** file phục vụ ứng dụng khi triển khai thuộc `main`; file chỉ phục vụ xác minh hành vi thuộc `test`. Java source được **biên dịch**; resource được **đưa lên classpath**; build tool quyết định phần nào xuất hiện trong artifact cuối cùng.