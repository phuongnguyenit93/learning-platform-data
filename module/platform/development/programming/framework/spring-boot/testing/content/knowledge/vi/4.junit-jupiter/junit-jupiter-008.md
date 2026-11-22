# JUnit Jupiter `@Tag`: phân nhóm test theo mục đích thực thi trong Spring Boot

> **Module:** Spring Boot – testing  
> **Mạch kiến thức:** JUnit Jupiter  
> **Đề bài:** `@Tag` và phân nhóm theo mục đích thực thi  
> **Mục tiêu:** Gắn tag đúng chỗ, hiểu cách JUnit Platform lọc test, chạy từng nhóm bằng Gradle hoặc Maven, và thiết kế lịch CI phù hợp với unit, slice, integration, smoke và end-to-end (E2E).

## 1. `@Tag` giải quyết vấn đề gì?

Một dự án Spring Boot thường có nhiều test với mục đích và chi phí khác nhau:

- **Unit test:** xác nhận logic Java trong một phạm vi nhỏ; thường rất nhanh.
- **Slice test:** xác nhận một lát framework (ví dụ Spring MVC với `@WebMvcTest` hoặc JPA với `@DataJpaTest`).
- **Integration test:** xác nhận nhiều bean/tầng thực hoạt động cùng nhau, có thể cần database hoặc broker.
- **E2E test:** xác nhận luồng từ điểm vào bên ngoài của hệ thống đang chạy tới kết quả quan sát được.
- **Smoke test:** tập rất nhỏ các hành vi cốt lõi phải hoạt động sau build/deploy.
- **Regression test:** xác nhận lỗi từng xảy ra không tái diễn và những contract quan trọng vẫn đúng.

Nếu luôn chạy **mọi test** sau mỗi lần lưu mã, vòng phản hồi có thể lâu. Nếu chỉ chạy vài unit test, ta dễ bỏ sót lỗi wiring, cấu hình hoặc luồng đầu cuối. **`@Tag` giúp gắn nhãn các test và chọn nhóm cần chạy cho một lần thực thi cụ thể.**

Ví dụ:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("unit")
@Tag("fast")
class PriceCalculationTest {
    @Test
    @Tag("smoke")
    void calculatesBasePrice() {
        // Assertion kiểm tra quy tắc giá.
    }
}
```

Test này có **ba tag hiệu lực**: `unit`, `fast`, `smoke`. Ta có thể chạy nó trong nhóm unit, nhóm fast, hoặc nhóm smoke. `@Tag` **không tự viết assertion, không tự chạy test, không tự nạp Spring context, không tự tạo transaction, không tự làm test nhanh hơn**. Nó chỉ cung cấp metadata cho cơ chế discovery/filtering của JUnit Platform và công cụ build.

**Phân biệt hai khái niệm:** `@Tag("integration")` là *nhãn lựa chọn chạy*; `@SpringBootTest` là *cấu hình nạp ứng dụng Spring*. Gắn `integration` vào unit test không biến unit test thành integration test. Ngược lại, `@SpringBootTest` thiếu tag vẫn là một test nạp context và có thể được chọn chạy theo cấu hình mặc định.

## 2. Tag được đặt ở đâu và có hiệu lực ra sao?

JUnit Jupiter cho phép đặt `@Tag` trên **test class** hoặc **test method**, đồng thời cho phép lặp annotation để một test thuộc nhiều nhóm.

### 2.1. Tag trên class áp dụng cho các phương thức test của class đó

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("unit")
@Tag("fast")
class GreetingRulesTest {

    @Test
    void defaultGreeting() {
        assertEquals("Hello", "Hel" + "lo");
    }

    @Test
    @Tag("smoke")
    void essentialGreeting() {
        assertEquals(2, 1 + 1);
    }
}
```

Những tag hiệu lực là:

| Test method | Tag hiệu lực |
| --- | --- |
| `defaultGreeting` | `unit`, `fast` |
| `essentialGreeting` | `unit`, `fast`, `smoke` |

Tag của phương thức **bổ sung** tag của class, không thay thế toàn bộ tag cấp class. Khi lọc chỉ `smoke`, chỉ `essentialGreeting` được chọn trong class trên; khi lọc `fast`, cả hai test được chọn.

`@Tag` có quy tắc kế thừa của JUnit Jupiter: **tag cấp class được kế thừa từ superclass; tag cấp method không được kế thừa theo cách tương tự**. Tránh dựa vào cấu trúc kế thừa phức tạp để phân nhóm; nếu cần hãy ưu tiên cấu trúc rõ ràng và kiểm tra kết quả discovery thực tế.

### 2.2. Một test có thể thuộc nhiều chiều phân loại

Tag không chỉ là “loại test”. Có thể dùng các chiều độc lập:

| Chiều | Ví dụ tag | Câu hỏi nó trả lời |
| --- | --- | --- |
| Mức kiểm thử | `unit`, `slice`, `integration`, `e2e` | Hệ thống nào thực sự đang được kiểm tra? |
| Tốc độ/chi phí | `fast`, `slow` | Nhóm nào phù hợp phản hồi nhanh? |
| Mục đích thực thi | `smoke`, `regression`, `release` | Nên chạy lúc nào trong vòng đời phát triển? |
| Hệ thống phụ thuộc | `db`, `http`, `external` | Test cần loại tài nguyên/hạ tầng nào? |
| Vùng nghiệp vụ | `catalog`, `checkout`, `auth` | Chức năng nào đang được bảo vệ? |

Ví dụ một integration test kiểm tra repository trên PostgreSQL có thể có `integration`, `db`, `catalog`. Một E2E test chỉ xác nhận người dùng đăng nhập thành công có thể có `e2e`, `smoke`, `auth`.

**Không bắt buộc mỗi test có mọi chiều.** Chọn ít tag có ý nghĩa thực tế và có nơi sử dụng. Quy ước team càng nhất quán thì biểu thức lọc càng dễ hiểu.

### 2.3. Quy tắc đặt tên tag hợp lệ

Theo JUnit Platform:

- Tag không được `null` hoặc rỗng.
- Sau khi trim, tag không được chứa khoảng trắng hoặc ký tự điều khiển ISO.
- Không chứa các ký tự dành riêng của cú pháp lọc: `,`, `(`, `)`, `&`, `|`, `!`.
- Các tên gọn như `fast`, `integration`, `db`, `feature-checkout` là ví dụ hợp lệ.
- Tag phân biệt chữ hoa/chữ thường: tránh vừa dùng `Fast` vừa dùng `fast` nếu muốn cùng một nhóm.

```java
@Tag("fast")             // Hợp lệ
@Tag("checkout-flow")    // Hợp lệ
@Tag("slow tests")       // Sai: có khoảng trắng
@Tag("unit,smoke")       // Sai: dấu phẩy là ký tự dành riêng
@Tag("unit")
@Tag("smoke")            // Đúng: hai tag riêng biệt
```

Khối trên **chỉ minh họa cú pháp annotation**, không phải một tệp Java độc lập để biên dịch vì annotation phải được đặt trước class/method thích hợp.

## 3. JUnit Platform chọn test bằng tag expression

JUnit Platform cho phép lọc bằng **tag expression**, gồm các toán tử Boolean:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `!` | Phủ định | `!e2e`: tất cả test không có tag `e2e` |
| `&` | AND/giao | `fast & smoke`: phải có cả hai tag |
| `|` | OR/hợp | `unit | slice`: có ít nhất một tag |
| `( )` | Nhóm điều kiện | `(unit | slice) & !slow` |
| `any()` | Có ít nhất một tag | `any()` |
| `none()` | Không có tag nào | `none()` |

**Độ ưu tiên:** `!` cao nhất, sau đó `&`, rồi `|`. Vì thế `unit | integration & !slow` được hiểu là `unit | (integration & !slow)`. Nên **đặt ngoặc** khi biểu thức có nhiều loại toán tử để người đọc không phải đoán.

Ví dụ dùng cùng một danh sách:

| Test | Tag |
| --- | --- |
| A | `unit`, `fast`, `smoke` |
| B | `unit`, `fast` |
| C | `slice`, `fast` |
| D | `integration`, `db` |
| E | `e2e`, `smoke`, `external` |
| F | không có tag |

Kết quả:

| Biểu thức | Test được chọn | Lý do |
| --- | --- | --- |
| `fast` | A, B, C | Có tag fast |
| `smoke` | A, E | Cả unit và E2E đều có thể là smoke |
| `fast & smoke` | A | Giao hai nhóm |
| `unit | integration` | A, B, D | Hợp hai nhóm |
| `smoke & !e2e` | A | Smoke nhưng loại E2E |
| `!e2e` | A, B, C, D, F | Cả test không gắn tag cũng được chọn |
| `none()` | F | Chỉ test không có tag |
| `any()` | A, B, C, D, E | Có ít nhất một tag |

**Lưu ý:** Biểu thức lọc là điều kiện quyết định *test nào được khám phá/chọn để chạy*. Test không được chọn do filter không đồng nghĩa với test bị đánh dấu `@Disabled`. Khi đánh giá số liệu CI, phân biệt **filtered out**, **skipped by condition** và **failed**.

## 4. Dự án Spring Boot chạy được: unit, slice, integration và external E2E

Phần này là một dự án Gradle Groovy DSL tối giản, dùng **Java 17, Spring Boot 3.5.0 và JUnit Jupiter 5** (phiên bản test dependencies do Spring Boot BOM quản lý). Các test cùng tồn tại trong `src/test/java` nhưng mang tag khác nhau để chạy theo nhu cầu.

### 4.1. Cấu trúc tệp

```text
tagged-tests-demo/
├── settings.gradle
├── build.gradle
├── gradlew                 # Có nếu dự án tạo bằng Spring Initializr/Gradle Wrapper
├── gradlew.bat
└── src/
    ├── main/java/com/example/tags/
    │   ├── TaggedTestsApplication.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/java/com/example/tags/
        ├── GreetingServiceTest.java
        ├── GreetingWebSliceTest.java
        ├── GreetingIntegrationTest.java
        └── GreetingExternalE2eTest.java
```

Các đoạn tệp dưới đây ghép thành một dự án duy nhất. Chỉ dùng **một** file `build.gradle` với cấu hình được đưa ra; các khối `tasks` thuộc chính file này.

### 4.2. Cấu hình Gradle

```groovy
// settings.gradle
rootProject.name = 'tagged-tests-demo'
```

```groovy
// build.gradle
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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

// Chạy test thường: mặc định loại E2E đang cần server ngoài.
// -PtagQuery=... cho phép chọn biểu thức tag vào một lần chạy cụ thể.
tasks.named('test', Test) {
    useJUnitPlatform {
        def tagQuery = project.findProperty('tagQuery')?.toString()
        if (tagQuery) {
            includeTags tagQuery
        } else {
            excludeTags 'e2e'
        }
    }
}

// Task chuyên chạy integration test từ cùng source set 'test'.
tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Run tests tagged integration'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    shouldRunAfter tasks.named('test')
    useJUnitPlatform {
        includeTags 'integration'
    }
}

// Task chuyên chạy E2E bằng HTTP với server đã khởi động riêng.
tasks.register('e2eTest', Test) {
    group = 'verification'
    description = 'Run tests tagged e2e against a running application'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    shouldRunAfter tasks.named('test')
    useJUnitPlatform {
        includeTags 'e2e'
    }
}
```

Giải thích cấu hình:

1. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Mockito, Spring Boot Test và Spring Test; test import những API này ở compile time nên dùng `testImplementation`.
2. `junit-platform-launcher` cần cho JUnit Platform lúc chạy nên dùng `testRuntimeOnly`. Với các phiên bản do BOM quản lý, không phải ghi số phiên bản tại mỗi dependency.
3. `useJUnitPlatform` khiến Gradle dùng JUnit Platform để discovery và thực thi Jupiter tests.
4. `test` mặc định **loại `e2e`**, còn unit/slice/integration được chạy; khi có `-PtagQuery=...`, nó chọn theo biểu thức mới thay cho mặc định.
5. `integrationTest` và `e2eTest` là **Gradle task tự định nghĩa**, sử dụng lại test classes và runtime classpath. Chúng chỉ chọn test theo tag; tự thân chúng không dựng DB, server hoặc Docker.
6. Các task đăng ký thêm không tự trở thành dependency của `check` nếu bạn chưa cấu hình `check.dependsOn(...)`. CI có thể gọi chúng vào đúng stage thay vì mặc định chạy tất cả.

**Ranh giới:** `@Tag` không tạo source set mới. Trong ví dụ này tất cả test vẫn ở source set `test`, khác nhau ở cách chọn khi chạy.

### 4.3. Mã ứng dụng thực

```java
// src/main/java/com/example/tags/TaggedTestsApplication.java
package com.example.tags;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaggedTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaggedTestsApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/tags/GreetingService.java
package com.example.tags;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        return "Hello, " + name.trim() + "!";
    }
}
```

```java
// src/main/java/com/example/tags/GreetingController.java
package com.example.tags;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet/{name}")
    public String greet(@PathVariable String name) {
        return service.greet(name);
    }
}
```

Endpoint `GET /greet/Mai` trả HTTP 200 và body text `Hello, Mai!`. Không có Spring Security hoặc database trong dự án tối giản này, vì vậy việc khởi chạy bằng `bootRun` không cần cấu hình phụ để test endpoint.

### 4.4. Unit test gắn tag `unit`, `fast` và `smoke`

```java
// src/test/java/com/example/tags/GreetingServiceTest.java
package com.example.tags;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
@Tag("fast")
class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    @Tag("smoke")
    void trimsName() {
        assertEquals("Hello, An!", service.greet("  An  "));
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.greet("  "));
        assertEquals("Name is required", error.getMessage());
    }
}
```

Ở đây, **cả hai test** có tag `unit` và `fast`, nhưng chỉ `trimsName` có thêm `smoke`. Không có `@SpringBootTest` hay HTTP request; cả hai test dựng trực tiếp Java class. Đây là unit test, bất kể cách gọi Gradle task.

### 4.5. MVC slice test gắn tag `slice` và `fast`

```java
// src/test/java/com/example/tags/GreetingWebSliceTest.java
package com.example.tags;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Tag("slice")
@Tag("fast")
@WebMvcTest(GreetingController.class)
class GreetingWebSliceTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    GreetingService service;

    @Test
    void routesGetRequestAndRendersBody() throws Exception {
        when(service.greet("Mai")).thenReturn("Hello, Mai!");

        mockMvc.perform(get("/greet/Mai"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Mai!"));
    }
}
```

`@WebMvcTest` nạp Spring MVC slice, MockMvc kiểm tra mapping và response, còn `@MockitoBean` đưa mock service vào Spring context thay cho service thật. `@Tag("fast")` là **quy ước** của team vì test này tương đối nhẹ; một slice test vẫn có thể chậm nếu bạn thêm nhiều bean hoặc thiết lập đắt đỏ.

### 4.6. Integration test gắn tag `integration`

```java
// src/test/java/com/example/tags/GreetingIntegrationTest.java
package com.example.tags;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Tag("integration")
@Tag("http")
@SpringBootTest
@AutoConfigureMockMvc
class GreetingIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void controllerAndRealServiceWorkTogether() throws Exception {
        mockMvc.perform(get("/greet/Mai"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Mai!"));
    }
}
```

Test này nạp ứng dụng với controller và service thật để xác nhận wiring, MVC và phản hồi phối hợp. `MockMvc` **không mở cổng HTTP socket**; tag `http` chỉ mô tả mục đích giao diện request/response, không chứng minh có kết nối network thật. Nếu cần xác nhận HTTP server thực, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và client HTTP.

### 4.7. E2E/API smoke test gắn tag `e2e`, `smoke`

Test dưới đây chạy từ client Java tách khỏi Spring context và gọi một **server đã chạy**. Biến `E2E_BASE_URL` xác định endpoint của môi trường kiểm thử. JUnit condition ngăn test chạy nếu chưa cấu hình URL.

```java
// src/test/java/com/example/tags/GreetingExternalE2eTest.java
package com.example.tags;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("e2e")
@Tag("smoke")
@EnabledIfEnvironmentVariable(
        named = "E2E_BASE_URL", matches = "https?://.+")
class GreetingExternalE2eTest {
    @Test
    void runningApplicationRespondsToExternalHttp() throws Exception {
        String base = System.getenv("E2E_BASE_URL")
                .replaceAll("/+$", "");

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(base + "/greet/Mai"))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Mai!", response.body());
    }
}
```

Đây là **E2E ở biên REST API** của một ứng dụng đang chạy. Nếu hệ thống thật có reverse proxy, database, authentication hoặc nhiều service, test local này **chưa chứng minh** các bộ phận không hiện diện trong môi trường; hãy chạy trên staging có cấu hình tương đương mục tiêu khi cần phạm vi đó. `@EnabledIfEnvironmentVariable` là điều kiện enable/disable, khác với `@Tag`: khi không có URL, test được chọn theo tag vẫn có thể bị báo *skipped* bởi JUnit condition.

## 5. Chạy các nhóm với Gradle

Dùng Gradle Wrapper trong thư mục `tagged-tests-demo`, với JDK 17+ và môi trường có thể tải dependencies:

```bash
# Chạy mặc định: tất cả trừ tag e2e (2 unit + 1 slice + 1 integration).
./gradlew test

# Chạy các test có tag fast (2 unit + 1 slice).
./gradlew test -PtagQuery=fast

# Chạy đúng phần giao của fast và smoke (1 unit method).
./gradlew test '-PtagQuery=fast & smoke'

# Chạy unit hoặc integration, nhưng loại e2e.
./gradlew test '-PtagQuery=(unit | integration) & !e2e'

# Chạy một task integration chuyên biệt (1 integration test).
./gradlew integrationTest

# Chọn e2e; nếu không có E2E_BASE_URL thì JUnit sẽ skip.
./gradlew e2eTest
```

Trên PowerShell/Windows:

```powershell
.\gradlew.bat test
.\gradlew.bat test -PtagQuery=fast
.\gradlew.bat test "-PtagQuery=fast & smoke"
.\gradlew.bat integrationTest
.\gradlew.bat e2eTest
```

**Chạy E2E có server ngoài:** mở terminal thứ nhất trong thư mục project:

```bash
./gradlew bootRun
```

Đợi ứng dụng khởi động, terminal thứ hai (Bash):

```bash
E2E_BASE_URL=http://localhost:8080 ./gradlew e2eTest
```

Hoặc PowerShell:

```powershell
$env:E2E_BASE_URL = "http://localhost:8080"
.\gradlew.bat e2eTest
Remove-Item Env:E2E_BASE_URL
```

Kết quả **được mong đợi** khi dự án mẫu và môi trường hoạt động đúng:

| Lệnh | Các method được chọn và thực thi |
| --- | --- |
| `./gradlew test` | `GreetingServiceTest`: 2; `GreetingWebSliceTest`: 1; `GreetingIntegrationTest`: 1; E2E bị lọc khỏi danh sách |
| `./gradlew test -PtagQuery=fast` | 2 unit + 1 slice = 3 |
| `./gradlew test '-PtagQuery=fast & smoke'` | `GreetingServiceTest.trimsName` = 1 |
| `./gradlew integrationTest` | `GreetingIntegrationTest.controllerAndRealServiceWorkTogether` = 1 |
| `./gradlew e2eTest` với URL hợp lệ và server sẵn sàng | `GreetingExternalE2eTest.runningApplicationRespondsToExternalHttp` = 1 |

Log Gradle, thời gian và task `UP-TO-DATE` thay đổi theo môi trường. Nếu task đã up-to-date khi đang kiểm tra lại selection, thử `./gradlew test -PtagQuery=fast --rerun-tasks`. Với E2E không có URL, có thể thấy một test *skipped* do `@EnabledIfEnvironmentVariable`. **Không đồng nhất “không thấy test trong report” với “test đã pass”**: xem số test thực sự được chọn, chạy và bị skip.

### 5.1. `--tests` có phải cú pháp lọc tag không?

Không. Trong Gradle, `--tests` lọc theo **class/method name pattern**, chẳng hạn:

```bash
./gradlew test --tests 'com.example.tags.GreetingServiceTest'
```

Trong project này, `-PtagQuery=...` chỉ hoạt động vì ta **đã viết logic đọc Gradle property** trong `build.gradle`. Không có nghĩa mọi dự án Gradle mặc định hiểu `-PtagQuery` hay có sẵn option `--include-tags`. Tag filter và `--tests` là hai cơ chế khác nhau; dùng cùng lúc có thể khiến tập test được chọn là **giao** của cả hai bộ lọc. Nếu không còn test phù hợp, hãy kiểm tra cả hai.

### 5.2. Chọn nhóm khi dùng Kotlin DSL

Trong `build.gradle.kts`, cấu hình tương đương:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform {
        val tagQuery = providers.gradleProperty("tagQuery").orNull
        if (tagQuery != null && tagQuery.isNotBlank()) {
            includeTags(tagQuery)
        } else {
            excludeTags("e2e")
        }
    }
}
```

Đây là **đoạn cấu hình thay thế tương ứng** cho build Kotlin DSL, không phải tệp độc lập đủ để chạy. Phần `dependencies`, plugin và source sets vẫn cần có trong `build.gradle.kts`. Không trộn cú pháp Groovy `includeTags 'fast'` vào Kotlin DSL; Kotlin cần `includeTags("fast")`.

## 6. Chạy theo tag bằng Maven Surefire/Failsafe

Khi dự án dùng Maven, **không áp dụng cấu hình `build.gradle`**. Maven Surefire Plugin hỗ trợ lọc JUnit 5/Jupiter tags bằng hai thuộc tính:

- `groups`: chọn tag hoặc tag expression để **bao gồm**.
- `excludedGroups`: chọn tag hoặc tag expression để **loại trừ**.

Ví dụ cấu hình một plugin Surefire trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.1</version>
            <configuration>
                <excludedGroups>e2e</excludedGroups>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Khối XML trên là **một phần `pom.xml`**, giả định project đã có dependencies JUnit Jupiter/Spring Boot Test thích hợp và compiler plugin phù hợp. Khi muốn chọn tag khác bằng CLI:

```bash
# Chỉ các test có tag fast:
mvn -Dgroups=fast test

# Chỉ các test có tag integration:
mvn -Dgroups=integration test

# Tổ hợp logic, đặt cả argument trong dấu nháy của shell:
mvn '-Dgroups=(fast | integration) & !e2e' test

# Loại các test gắn tag e2e:
mvn -DexcludedGroups=e2e test
```

Nếu `pom.xml` đang đặt `excludedGroups=e2e`, lệnh chỉ định `groups=...` **không tự xóa cấu hình loại trừ đó**; effective configuration là kết hợp các điều kiện include và exclude. Ví dụ tag `e2e` vẫn có thể bị loại nếu đã cấu hình excludedGroups. Đối với một số stage CI, hãy tạo Maven profile tường minh hoặc cấu hình lại cả hai phía để tránh filter ngầm.

**Surefire/Failsafe và tên tệp:** Surefire thường chọn các tên `*Test`/`*Tests` theo convention, trong khi Failsafe thường dùng `*IT`/`IT*`. `@Tag("integration")` **không tự đưa class qua Failsafe** hoặc đổi phase Maven. Muốn tách unit/integration giữa Surefire và Failsafe cần cấu hình plugin, include/exclude pattern và lifecycle tương ứng; tag chỉ là **một điều kiện lọc khác**. Failsafe cũng hỗ trợ tag filtering qua provider JUnit Platform khi được cấu hình phù hợp.

## 7. Tạo annotation có ý nghĩa bằng meta-annotation

Khi cả dự án thường xuyên gắn cùng một tag, bạn có thể định nghĩa annotation của riêng team, thay vì lặp chuỗi `"integration"` ở nhiều nơi. JUnit Jupiter hỗ trợ **composed annotation**: annotation do bạn tạo mang meta-annotation `@Tag`.

```java
// src/test/java/com/example/tags/IntegrationTagged.java
package com.example.tags;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.Tag;

@Target({ ElementType.TYPE, ElementType.METHOD })
@Retention(RetentionPolicy.RUNTIME)
@Tag("integration")
public @interface IntegrationTagged {}
```

Sử dụng:

```java
@IntegrationTagged
@SpringBootTest
class PaymentFlowIntegrationTest {
    @Test
    void persistsPayment() {
        // Ví dụ khung: test thật cần assertions + fixtures thích hợp.
    }
}
```

Đoạn `PaymentFlowIntegrationTest` chỉ là **minh họa cách sử dụng annotation**, không phải test chức năng đầy đủ hoặc một file runnable độc lập. `@IntegrationTagged` đóng gói **nhãn**, còn `@SpringBootTest` riêng biệt đóng gói **cách tạo Spring context**. Nếu muốn định nghĩa một stereotype test mang cả hai, có thể tạo custom composed annotation chứa cả `@Tag` và `@SpringBootTest`, nhưng phải quản lý hậu quả về Spring test context, inheritance và test configuration rõ ràng. Tránh giấu những dependency hệ thống quan trọng trong tên annotation mơ hồ.

## 8. Thiết kế nhóm chạy test cho CI/CD

Một cách tổ chức thường có ích là dùng nhiều stage, không cố gán mọi test vào một nhãn duy nhất:

| Trigger | Nhóm được chọn | Mục đích |
| --- | --- | --- |
| Developer chạy local khi sửa logic | `fast` hoặc `unit | slice` | Phát hiện regression nhanh |
| Mỗi pull request | `fast`; bổ sung test integration quan trọng | Feedback đủ nhanh để sửa ngay |
| Trước merge / trên nhánh chính | `integration` và phần liên quan DB/service | Xác nhận wiring và phụ thuộc thật |
| Sau deploy staging | `smoke & e2e` | Xác nhận các đường đi tối thiểu qua môi trường |
| Hàng đêm / lịch định kỳ | `regression`, `slow`, E2E rộng hơn | Phát hiện vấn đề tốn thời gian chạy |
| Trước release | `release` cộng các test rủi ro cao | Bao phủ contract và hành trình quan trọng |

Ví dụ biểu thức mục tiêu:

- **Local nhanh:** `fast & !external`.
- **Nhóm nghiệp vụ catalog:** `catalog & (unit | slice | integration)`.
- **Smoke sau deploy:** `smoke & e2e`.
- **Những test không gắn tag:** `none()`, dùng để phát hiện test chưa được phân nhóm.

Việc áp dụng còn phụ thuộc thời gian chạy, độ ổn định, giá trị bảo vệ và quy mô codebase. Đừng ép mọi test mang `smoke` chỉ để tăng số lượng smoke; smoke nên bảo vệ **những hành vi cốt lõi, đủ nhỏ để có kết quả sớm**.

### 8.1. Nếu test cần dịch vụ bên ngoài thì tag có đủ không?

Không. `@Tag("db")` chỉ là metadata. Muốn test chạy được vẫn cần database/testcontainer, schema, migration, dữ liệu seed, credentials, endpoint, timeout và cơ chế cleanup phù hợp. Nếu chạy CI ở môi trường thiếu database, việc chỉ include tag `db` sẽ gây lỗi chứ không tạo database.

Có thể kết hợp `@Tag` với:

- `@ActiveProfiles("test")` để chọn Spring profile; hai annotation giải quyết **hai việc khác nhau**.
- `@Testcontainers` hoặc container lifecycle để khởi tạo dependency theo nhu cầu.
- `@EnabledIfEnvironmentVariable` để disable có điều kiện khi môi trường không sẵn sàng.
- Cấu hình Gradle/Maven/CI để cấp URL, secret và tài nguyên thích hợp.

Tag là **nhãn chọn test**, không là một cơ chế quản lý môi trường kiểm thử.

## 9. Những lỗi phổ biến

### 9.1. Gắn `@Tag` nhưng mọi test vẫn chạy

Nguyên nhân: chưa cấu hình tag filter ở Gradle/Maven/IDE hoặc đang chạy một task khác không có filter. **Mặc định, JUnit Platform không tự bỏ qua test chỉ vì nó mang tag `slow` hoặc `e2e`.** Kiểm tra đúng task/runner, xem log và report.

### 9.2. Dùng `@Tag("fast,smoke")` để gắn hai tag

Đó là **một chuỗi tag không hợp lệ** vì chứa dấu phẩy. Dùng hai annotation `@Tag("fast")` và `@Tag("smoke")`. Khi lọc nhiều tag, sử dụng biểu thức `fast | smoke` hoặc `fast & smoke` tùy logic cần.

### 9.3. Nhầm `@Disabled` với `@Tag("skip")`

`@Disabled` là annotation JUnit dùng để disable test không điều kiện (trừ cơ chế riêng khác); `@Tag("skip")` không có tác dụng đặc biệt nếu runner không chủ động exclude nó. Không dùng tên tag “skip” với kỳ vọng JUnit tự tắt test.

### 9.4. Tin rằng test có tag `integration` chắc chắn kiểm tra database thật

Tag không xác thực phạm vi thực. Một test có `@MockitoBean` mock repository vẫn có thể chạy dưới `@SpringBootTest` nhưng chưa chứng minh query SQL. Cần kiểm tra các thành phần và boundary thực sự, rồi chọn tag đúng.

### 9.5. Dùng tên tag không nhất quán

`Integration`, `integration`, `int-test` và `IT` có thể bị xem là các tag khác nhau; filter `integration` sẽ không tự nhận các tên còn lại. Xây một bảng tag chuẩn trong dự án, thống nhất lowercase/kiểu nối từ và tránh thay đổi tên bất ngờ.

### 9.6. Dùng tag expression sai ưu tiên

`unit | integration & !slow` khác `(unit | integration) & !slow`. Biểu thức đầu chọn **mọi unit**, kể cả unit chậm; biểu thức sau loại slow ở cả hai nhóm. Sử dụng dấu ngoặc để truyền đạt ý định rõ ràng.

### 9.7. Tin vào tổng số test pass mà bỏ qua filtered/skipped

Nếu bạn chỉ chạy `fast` và thấy tất cả pass, không thể suy ra `integration`/`e2e` cũng pass. Nếu `e2eTest` được chọn nhưng `E2E_BASE_URL` thiếu, test có thể bị skipped; đếm test selected/executed/skipped và có chính sách CI để phát hiện nhóm test vô tình rỗng.

### 9.8. Tạo quá nhiều tag một lần

Một bộ 40 tag không có đường chạy thực tế chỉ tăng gánh nặng bảo trì. Khởi đầu bằng những chiều cần thiết (mức test, chi phí, luồng quan trọng), viết quy ước và bổ sung sau khi có yêu cầu lọc cụ thể.

### 9.9. Lẫn lộn `--tests` và tag filter

`--tests` của Gradle chọn test theo tên class/method; `@Tag` lọc theo metadata. Thay class name hoặc đổi method không nên làm thay đổi tag ý nghĩa, và đổi tag không đổi tên class. Nếu một test “biến mất”, xem cả tag filter và class name filter.

### 9.10. Coi test không được chọn là test bị lỗi

Lọc bỏ một test không làm nó fail. CI báo “0 test” hoặc “successful with only N tests” phải được đánh giá theo kỳ vọng của stage: nhóm smoke không được trống và các nhóm quan trọng phải có ít nhất các case đã cam kết.

## 10. Bài tập thực hành

Sử dụng dự án mẫu:

1. Chạy `./gradlew test -PtagQuery=fast`, ghi lại những class/method được chọn. **Đáp án:** hai method của `GreetingServiceTest` và một của `GreetingWebSliceTest`.
2. Chạy `./gradlew test '-PtagQuery=fast & smoke'`. **Đáp án:** chỉ method `GreetingServiceTest.trimsName`.
3. Chạy `./gradlew integrationTest`. **Đáp án:** một method của `GreetingIntegrationTest`, sử dụng Spring context và MockMvc.
4. Chạy `./gradlew e2eTest` khi thiếu `E2E_BASE_URL`. **Kỳ vọng:** test mang tag e2e được chọn nhưng bị JUnit condition disable/skip; không có yêu cầu gửi HTTP thành công.
5. Khởi động `bootRun`, cấu hình `E2E_BASE_URL` rồi chạy `e2eTest`. **Kỳ vọng:** 1 method thực thi, nhận 200 và `Hello, Mai!`.
6. Gắn `@Tag("regression")` lên method `rejectsBlankName` rồi dùng `-PtagQuery=regression`. **Kỳ vọng:** chỉ method này được chọn (và vẫn có tag class `unit`, `fast`).
7. Gắn `@Tag("slow")` ở class `GreetingServiceTest` rồi chạy `-PtagQuery='(unit | slice) & !slow'`. **Kỳ vọng:** cả hai unit bị loại, chỉ slice test còn trong phạm vi biểu thức.
8. Thử lọc `none()` trên chính dự án mẫu. **Kỳ vọng:** không còn test nào không có tag, nên tập được chọn rỗng; đây là tín hiệu phải kiểm tra theo quy định CI, không phải bằng chứng ứng dụng đúng.

## 11. Checklist tự đánh giá

- [ ] Biết `@Tag` chỉ gắn metadata để JUnit Platform chọn test; không quyết định cách nạp Spring context.
- [ ] Biết đặt tag ở class/method, kết hợp nhiều tag và hiểu class-level tags áp dụng cho các method.
- [ ] Dùng đúng `!`, `&`, `|`, dấu ngoặc và `any()`/`none()`.
- [ ] Tránh tên tag rỗng, khoảng trắng hoặc ký tự `,()&|!`; áp dụng convention thống nhất.
- [ ] Phân biệt test bị lọc với test bị `@Disabled`/conditional skip hoặc failed.
- [ ] Biết cấu hình `useJUnitPlatform { includeTags ...; excludeTags ... }` trong Gradle.
- [ ] Biết `groups`/`excludedGroups` trong Maven Surefire và quan hệ của Surefire/Failsafe với naming conventions.
- [ ] Phân biệt `--tests` (tên class/method) với filtering bằng `@Tag`.
- [ ] Thiết kế được nhóm fast, integration, E2E, smoke phù hợp local/PR/staging/nightly.
- [ ] Kiểm tra môi trường/fixtures và số test thực thi; không coi tag là thay thế cho test infrastructure.

## 12. Nguồn chính thức để đối chiếu

- [JUnit Jupiter – Writing Tests: Tagging and Filtering](https://docs.junit.org/5.14.1/writing-tests/tagging-and-filtering.html): `@Tag`, tag syntax và composed annotations (dòng JUnit 5).
- [JUnit Platform – Tags và Tag Expressions](https://docs.junit.org/5.14.0/user-guide/index.html): Boolean operators, mức ưu tiên và `any()`/`none()`.
- [Gradle – Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, `includeTags`/`excludeTags`, `--tests`.
- [Maven Surefire – Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): lọc JUnit 5 bằng `groups` và `excludedGroups`.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@AutoConfigureMockMvc`.

**Ghi nhớ:** Một test có thể cùng lúc là `unit`, `fast` và `smoke`, vì ba nhãn trả lời ba câu hỏi khác nhau. `@Tag` làm việc với **discovery/filter**; Gradle/Maven quyết định **chạy nhóm nào**; annotation Spring và hạ tầng test quyết định **thực sự kiểm tra điều gì**.