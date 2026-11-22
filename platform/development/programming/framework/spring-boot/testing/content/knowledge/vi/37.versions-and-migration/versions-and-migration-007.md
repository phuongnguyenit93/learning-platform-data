# MockMvcTester, RestTestClient và API chỉ có ở phiên bản hỗ trợ

## 1. Vì sao một đoạn test đúng trên Spring mới có thể không biên dịch trên dự án cũ?

Trong Spring Boot testing, tên API đôi khi giống nhau nhưng **nằm ở các phiên bản, mô-đun, package và tầng kiểm thử khác nhau**. Một ví dụ từ tài liệu Spring Framework mới có thể dùng `MockMvcTester` hoặc `RestTestClient`. Khi sao chép nguyên xi sang project Spring Boot 3.3.5, Java compiler có thể báo `cannot find symbol` hoặc `package ... does not exist` dù project vẫn có `spring-boot-starter-test`. Không phải vì Mockito/MockMvc không hoạt động; nguyên nhân là class **chưa được phát hành trong phiên bản Spring Framework được Boot 3.3 quản lý**.

Những câu hỏi cần phân biệt:

- `MockMvc` (Spring MVC Test) có sẵn trong nhiều thế hệ Spring Framework, trong đó có **6.1**.
- `MockMvcTester` cung cấp cách viết AssertJ fluent trên `MockMvc`, được giới thiệu trong **Spring Framework 6.2**.
- `RestClient` là HTTP client cho ứng dụng, đã có từ **Spring Framework 6.1**.
- `RestTestClient` là HTTP client **dành cho test server**, dựa trên `RestClient`, được giới thiệu trong **Spring Framework 7.0**.
- `WebTestClient` là test client đã tồn tại trước đó trong Spring WebFlux; không phải tên cũ của `RestTestClient`.
- `TestRestTemplate` là tiện ích test HTTP khác của Spring Boot, có sẵn trong Boot 3.3, nhưng module và package thay đổi trong Boot 4.
- `@MockBean` của Boot 3.3 và `@MockitoBean` của Spring Framework 6.2+ cũng liên quan version; không trộn imports theo bài mẫu mới.

Bài này thuộc nhóm **Phiên bản và chuyển đổi**, chủ đề **“MockMvcTester, RestTestClient và API chỉ có ở phiên bản hỗ trợ”**, trong module **Spring Boot - testing**. Mục tiêu là biết **API thuộc artifact nào, version tối thiểu nào, dùng đúng dependency/annotation nào và migrate thế nào** mà không làm hỏng test suite hiện hữu.

Ví dụ chính dùng **Java 17+**. Ta xây cùng một Greeting Controller rồi trình bày **ba cấu hình/build tách biệt**:

1. **Spring Boot 3.3.5** với Spring Framework 6.1: `MockMvc`, `@MockBean` và `TestRestTemplate`.
2. **Spring Boot 3.5.x** với Spring Framework 6.2: `MockMvcTester` và `@MockitoBean`.
3. **Spring Boot 4.0.x** với Spring Framework 7.0: `RestTestClient`, `@AutoConfigureRestTestClient` và các package/module Boot 4 tương ứng.

**Không ghép tất cả test classes của ba nhánh vào cùng một project classpath.** Mỗi test file có phiên bản hỗ trợ được ghi rõ. Mọi con số và code report bên dưới là **hướng dẫn**, không phải kết quả Gradle đã chạy trong lúc viết bài.

## 2. Bảng tương thích phải đọc trước tiên

| Hệ Spring Boot | Spring Framework do Boot quản lý | MockMvc | MockMvcTester | RestTestClient | Đặc điểm |
| --- | --- | --- | --- | --- | --- |
| **3.3.x** (ví dụ 3.3.5) | **6.1.x** | Có | **Chưa có** | **Chưa có** | `@MockBean` của Boot; `RestClient` đã có |
| **3.4.x** | **6.2.x** | Có | Có | **Chưa có** | Framework `@MockitoBean`; Boot `@MockBean` được deprecate |
| **3.5.x** | **6.2.x** | Có | Có | **Chưa có** | `@WebMvcTest` thường auto-configure MockMvcTester nếu AssertJ trên classpath |
| **4.0.x** | **7.0.x** | Có | Có | Có | `@AutoConfigureRestTestClient`, Boot test modules và packages mới |

Các hàng thể hiện **nhánh phiên bản tương thích**, không bảo đảm mọi patch release có cùng số minor cuối cùng. Khi dùng Spring Boot BOM, nó quản lý đúng Spring Framework patch version; xem dependency tree thực trước khi debug.

### Bốn kết luận quan trọng

1. **Không thể dùng RestTestClient trên Boot 3.3 hoặc 3.5 chỉ vì đã có RestClient.** Hai class có nhiệm vụ khác nhau và `RestTestClient` chưa tồn tại trong Spring Framework 6.x.
2. **Không thể dùng MockMvcTester trực tiếp trên Boot 3.3.5** với Spring Framework 6.1. Cách an toàn là tiếp tục `MockMvc` hoặc nâng cấp đồng bộ sang Boot 3.4/3.5.
3. **Không cần nâng lên Boot 4 chỉ để sử dụng MockMvcTester.** API này đã có ở Framework 6.2 / Boot 3.4+.
4. **Không nên nâng riêng mỗi `spring-test` lên 7.x trong Boot 3.3.** Các module Spring Core/Web/Context/Test và Servlet stack phải tương thích; chỉ ép version của một JAR rất dễ gây `NoSuchMethodError`/`ClassNotFoundException` lúc chạy.

### Về phiên bản tài liệu

Đừng chỉ nhìn URL `docs.spring.io/spring-framework/reference/...` không có segment phiên bản rồi đoán đó là API dành cho Boot 3.3. Documentation “current” được cập nhật theo nhánh Spring Framework mới. Luôn chọn trang **6.1**, **6.2** hoặc **7.0** tương ứng với project. Ở cuối bài có các link versioned chính thức.

## 3. Hai tầng khác nhau: kiểm thử client outbound và server inbound

Sơ đồ:

```text
Application A                  Application B (REST server)
   |
   |  Production HTTP client
   |  RestClient / WebClient / RestTemplate
   +------------------------------------------> API B
                                                   |
              Testing server application B         |
              MockMvc / MockMvcTester /             |
              RestTestClient / WebTestClient         |
                                                   v
                                            Controller, MVC,
                                            Filters, Advice

              Testing outbound client A:
              MockRestServiceServer / MockWebServer
```

- `RestClient` thực thi HTTP request **do application chủ động gửi**.
- `MockRestServiceServer` mô phỏng **remote HTTP server cho outbound RestClient/RestTemplate** bằng một mock request factory.
- `MockMvc` và `MockMvcTester` kiểm tra **Spring MVC controller** mà không cần mở HTTP listening port.
- `RestTestClient` kiểm thử **server endpoints** với API fluent; có thể bind vào **MockMvc** (không real port) hoặc bind vào **live HTTP server**.
- `WebTestClient` phục vụ WebFlux hoặc có thể bind đến MVC/real server khi dependency/setup phù hợp; nó tồn tại từ các phiên bản trước RestTestClient.

**Sai mục đích:** Một test code sử dụng `RestClient.builder()` rồi cố gọi `expectStatus().isOk()` như `RestTestClient`; các API assertion không tồn tại trên production RestClient. Với `RestClient`, bạn nhận response hay exception và tự assert. Với `RestTestClient`, bạn có `exchange().expectStatus()` và `expectBody(...)`.

## 4. Các imports cần nhớ theo thế hệ

| API | Boot 3.3 / Framework 6.1 | Boot 3.5 / Framework 6.2 | Boot 4 / Framework 7 |
| --- | --- | --- | --- |
| MockMvc | `org.springframework.test.web.servlet.MockMvc` | Không đổi | Không đổi |
| MockMvcTester | Chưa tồn tại | `org.springframework.test.web.servlet.assertj.MockMvcTester` | Cùng class |
| RestTestClient | Chưa tồn tại | Chưa tồn tại | `org.springframework.test.web.servlet.client.RestTestClient` |
| @WebMvcTest | `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` | Package cũ còn dùng | `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest` |
| @AutoConfigureMockMvc | `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` | Package cũ còn dùng | `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc` |
| @MockBean | `org.springframework.boot.test.mock.mockito.MockBean` | Legacy Boot annotation đã deprecate | Không dùng legacy Boot annotation |
| @MockitoBean | Chưa có trong Framework 6.1 | `org.springframework.test.context.bean.override.mockito.MockitoBean` | Cùng Spring Test annotation |
| @AutoConfigureRestTestClient | Chưa tồn tại | Chưa tồn tại | `org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient` |
| @SpringBootTest | `org.springframework.boot.test.context.SpringBootTest` | Như cũ | Như cũ |
| TestRestTemplate | `org.springframework.boot.test.web.client.TestRestTemplate` | Như cũ | `org.springframework.boot.resttestclient.TestRestTemplate` |

**Chú ý:** Đây là bảng chọn imports khi migrate; không được tạo một file Java chứa đồng thời hai `WebMvcTest` imports. Spring Boot 4 chia module/auto-configuration package theo feature, nên một import đúng ở Boot 3.5 có thể cần thay khi chuyển 4.0.

## 5. Kỹ thuật tìm đúng dependency đang quản lý API

Trong Gradle (chạy ở module chứa test):

```bash
./gradlew dependencyInsight \
  --dependency spring-test \
  --configuration testRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration testRuntimeClasspath

./gradlew dependencies \
  --configuration testRuntimeClasspath
```

Lệnh trên giúp nhìn **version thực được resolve**, nguyên nhân version được chọn và dependency constraints, thay vì đoán từ `build.gradle` của một module khác. Trong multi-module, dùng `:module-name:dependencyInsight` và đúng test task/source set.

Maven tương đương:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
```

Nếu test compile fail, kiểm tra **testCompileClasspath** nữa. Một JAR có trên test runtime chưa chắc xuất hiện trên compile classpath hoặc ngược lại.

### Những dấu hiệu trong Java compiler

```text
error: cannot find symbol
  symbol: class MockMvcTester

error: package org.springframework.test.web.servlet.client
  does not exist

error: cannot find symbol
  symbol: class MockitoBean
```

Đây là **dạng thông báo minh họa**, không phải stdout của một build vừa chạy. Kiểm tra class/package tồn tại trong Spring Test artifact của branch đang dùng. Nếu Gradle cache cũ, làm mới resolution theo quy trình build của team; **không** chỉ thêm import mới rồi tắt test.

## 6. Nguyên tắc triển khai ví dụ: ba project riêng hoặc ba Git branches

Để một README không đưa mã không tương thích vào cùng một source set, có thể:

- Tạo **ba thư mục standalone**: `boot33-mockmvc/`, `boot35-mockmvctester/`, `boot40-resttestclient/`. Mỗi thư mục có một `settings.gradle` và `build.gradle` riêng.
- Hoặc dùng **ba Git branches** với cùng package ứng dụng, mỗi branch chọn một phiên bản Boot/Gradle/dependency và các test files riêng.
- Hoặc dùng Gradle multi-project với subprojects độc lập; **không** ép tất cả subprojects cùng một Spring BOM nếu muốn chạy cả 3 versions.

Trong bài này, production Java files giống nhau giữa ba nhánh và được liệt kê **một lần** ở mục 8–11. Mỗi nhánh có **build.gradle và test classes riêng**, nên khi thực hành phải copy mã dùng chung vào **project của nhánh đang thử**.

```text
boot33-mockmvc/
  settings.gradle
  build.gradle
  src/main/java/com/example/compat/
    GreetingApplication.java
    GreetingMessage.java
    GreetingService.java
    GreetingController.java
  src/test/java/com/example/compat/
    GreetingController33SliceTest.java
    GreetingController33HttpTest.java

boot35-mockmvctester/
  settings.gradle
  build.gradle
  src/main/java/com/example/compat/
    (bốn file ứng dụng giống nhánh 3.3)
  src/test/java/com/example/compat/
    GreetingController35SliceTest.java

boot40-resttestclient/
  settings.gradle
  build.gradle
  src/main/java/com/example/compat/
    (bốn file ứng dụng giống nhánh 3.3)
  src/test/java/com/example/compat/
    GreetingController40SliceTest.java
    GreetingController40HttpTest.java
    GreetingController40StandaloneTest.java
```

Đây là mô tả cấu trúc, **không** yêu cầu tạo các files này trong repo hiện tại. Bài Knowledge lưu mã để người đọc tự thực hành; worker không sửa repository hay chạy Gradle trong môi trường ứng dụng thật.

## 7. Cấu hình chung settings.gradle và quy tắc Java 17

Mỗi nhánh có một `settings.gradle` với tên khác nhau:

**boot33-mockmvc/settings.gradle**:

```groovy
rootProject.name = 'boot33-mockmvc'
```

**boot35-mockmvctester/settings.gradle**:

```groovy
rootProject.name = 'boot35-mockmvctester'
```

**boot40-resttestclient/settings.gradle**:

```groovy
rootProject.name = 'boot40-resttestclient'
```

Cả ba dùng Java toolchain 17. Boot 4.0 vẫn có baseline Java 17; cần **Gradle 8.14+ hoặc 9.x** theo yêu cầu Boot 4.0. Không dùng Gradle 8.5/8.8 đã cài trong dự án Boot 3.3 để mặc nhiên chạy Gradle plugin 4.0.

### Gradle Wrapper

Nếu `gradlew`/`gradlew.bat` chưa có, `./gradlew test` không chạy. Có thể dùng `gradle test` khi cài Gradle tương thích hoặc tạo Wrapper đúng version. Khi nâng Boot major, cập nhật `gradle/wrapper/gradle-wrapper.properties` và kiểm tra plugins/Java toolchain trước khi kết luận thiếu class test.

## 8. Java file chung: GreetingApplication.java

`src/main/java/com/example/compat/GreetingApplication.java`:

```java
package com.example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }
}
```

Class này là entry point, có package cha bao phủ các Spring components khác. `@WebMvcTest` sẽ giới hạn slice vào MVC, còn `@SpringBootTest` nạp application context rộng hơn. Cả hai có thể tìm được `@SpringBootApplication` theo package hierarchy.

## 9. Java record chung: GreetingMessage.java

`src/main/java/com/example/compat/GreetingMessage.java`:

```java
package com.example.compat;

public record GreetingMessage(String message) {
}
```

Java 17 records hỗ trợ JSON serialization khi Jackson message converter hiện diện. Test JSON sẽ kiểm tra trường `message` thay vì phụ thuộc thứ tự key, whitespace hoặc serialization formatting.

Không dùng một `record` JSON giả để chứng minh một MVC controller đã được test: phải thực sự gọi endpoint bằng MockMvc, MockMvcTester hoặc RestTestClient tương ứng.

## 10. Java service chung: GreetingService.java

`src/main/java/com/example/compat/GreetingService.java`:

```java
package com.example.compat;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public GreetingMessage greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        return new GreetingMessage("Hello " + name);
    }
}
```

Vì service không gọi DB/HTTP ngoài, full HTTP tests có thể dùng bean thật. Còn MVC slice tests dùng `@MockBean`/`@MockitoBean` để chỉ tập trung vào controller request mapping, status, response body.

**Lưu ý:** Không có `@RestControllerAdvice` nào map `IllegalArgumentException` thành HTTP 400 trong project này. Đừng thêm test kỳ vọng 400 cho request rỗng rồi cho rằng Spring Boot tự chuyển mọi IllegalArgumentException thành Bad Request. Đó là một hợp đồng khác cần thiết kế riêng.

## 11. Controller chung: GreetingController.java

`src/main/java/com/example/compat/GreetingController.java`:

```java
package com.example.compat;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(
            path = "/api/hello/{name}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello(@PathVariable String name) {
        return greetingService.greeting(name).message();
    }

    @GetMapping(
            path = "/api/greetings/{name}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingMessage json(@PathVariable String name) {
        return greetingService.greeting(name);
    }

    @GetMapping(
            path = "/api/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
```

Dùng constructor injection để mock service dễ dàng. Controller có ba endpoints:
- `GET /api/hello/Ada` trả text `Hello Ada`;
- `GET /api/greetings/Ada` trả JSON object có `message="Hello Ada"`;
- `GET /api/ping` trả text `pong`.

Với JSON, test không nên so sánh raw body format nếu không có yêu cầu byte-level; có thể dùng JsonPath hoặc DTO decoding.

## 12. Nhánh A — Spring Boot 3.3.5: build.gradle

**Chỉ cho boot33-mockmvc**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Lý do:
- `spring-boot-starter-web` đưa Spring MVC, embedded Servlet server và JSON converters.
- `spring-boot-starter-test` đưa Spring Test, JUnit Jupiter, AssertJ, Mockito, JsonPath/Hamcrest.
- `spring-boot-test-autoconfigure` đã có qua starter-test để dùng `@WebMvcTest` và `@AutoConfigureMockMvc`.
- `MockMvc` dùng được với Spring Framework 6.1 trong Boot 3.3.
- **Không có `MockMvcTester` hoặc `RestTestClient`** trong Spring Test 6.1, nên không import các class ấy.

## 13. Boot 3.3: MVC slice test bằng MockMvc và @MockBean

`boot33-mockmvc/src/test/java/com/example/compat/GreetingController33SliceTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingController33SliceTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    GreetingService service;

    @Test
    void textResponseUsesExpectedMapping() throws Exception {
        when(service.greeting("Ada"))
                .thenReturn(new GreetingMessage("Hello Ada"));

        mvc.perform(get("/api/hello/Ada")
                        .accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Ada"));

        verify(service).greeting("Ada");
    }

    @Test
    void jsonResponseHasMessageField() throws Exception {
        when(service.greeting("Lin"))
                .thenReturn(new GreetingMessage("Hello Lin"));

        mvc.perform(get("/api/greetings/Lin")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message")
                        .value("Hello Lin"));

        verify(service).greeting("Lin");
    }

    @Test
    void missingPathReturnsNotFound() throws Exception {
        mvc.perform(get("/api/not-defined"))
                .andExpect(status().isNotFound());
    }
}
```

Đây là **3 phương thức `@Test`** của nhánh 3.3 slice.

### Giải thích

`@WebMvcTest(GreetingController.class)` chỉ load MVC slice. `GreetingService` là `@Service` và thường **không tự được scan** trong slice; nếu không cấp mock/bean, context có thể fail vì constructor dependency thiếu. `@MockBean` của Boot 3.3 tạo hoặc thay bean cùng type/name trong `ApplicationContext`.

`@Autowired MockMvc` là mô phỏng server-side request handling bằng mock Servlet request/response. **Không có HTTP listening port**; vì vậy test không kiểm tra TCP/TLS/proxy/real embedded server. Nó kiểm tra request mapping, content negotiation, serialization, controller and filters nếu được đưa vào slice.

### Assert hành vi, không chỉ compile

- Status 200 là một assertion.
- Text body và JSON `$.message` là hai contract khác.
- `verify(service).greeting("Ada")` cho biết controller gọi đúng collaborator được mock.
- HTTP 404 route không tồn tại không cần service stub; nếu cố tạo stub trong test này, strict stubbing/unused behavior có thể phụ thuộc Mockito session policy, và nó không giúp kiểm tra route.

**Không copy code dùng `MockMvcTester` vào file này.** Một import không có trong classpath làm cả `compileTestJava` fail trước khi JUnit chạy.

## 14. Boot 3.3: kiểm thử HTTP server thật bằng TestRestTemplate

`boot33-mockmvc/src/test/java/com/example/compat/GreetingController33HttpTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingController33HttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void realHttpTextResponseIsOk() {
        ResponseEntity<String> response =
                http.getForEntity(
                        "/api/hello/Ada", String.class);

        assertEquals(HttpStatus.OK,
                response.getStatusCode());
        assertEquals("Hello Ada",
                response.getBody());
    }

    @Test
    void realHttpJsonResponseIsDecoded() {
        ResponseEntity<GreetingMessage> response =
                http.getForEntity(
                        "/api/greetings/Lin",
                        GreetingMessage.class);

        assertEquals(HttpStatus.OK,
                response.getStatusCode());
        assertEquals(
                new GreetingMessage("Hello Lin"),
                response.getBody());
    }
}
```

Đây là **2 phương thức `@Test`** bổ sung ở Boot 3.3. `RANDOM_PORT` mở embedded Servlet HTTP server ở port do hệ điều hành cấp; `TestRestTemplate` do Boot test auto-configure dùng relative URL trỏ đúng server.

### TestRestTemplate không phải RestTestClient

`TestRestTemplate` wrap `RestTemplate` theo hướng tiện cho test; một đặc điểm là nó **không tự throw** cho HTTP 4xx/5xx như nhiều production API call patterns, mà cho phép assert `ResponseEntity.getStatusCode()`.

`RestTestClient` không tồn tại trong Boot 3.3. Nếu bạn muốn API fluent `exchange().expectStatus()` trên Boot 3.3, có thể cân nhắc `WebTestClient` khi đủ dependencies/config (hoặc tiếp tục MockMvc/TestRestTemplate). Nhưng **đừng đổi import tên class giống nhau** để compiler tự tìm phiên bản mới.

### Random port và transactions

Khi test gửi HTTP thật, client và server chạy ở threads/transactions khác nhau. Một `@Transactional` trên test method **không tự rollback** commit phía server nếu controller/service ghi database. Đây là sự khác biệt quan trọng giữa MockMvc tests và live server tests khi thiết kế cleanup.

## 15. Lệnh chạy và kết quả có thể xác minh của Boot 3.3

Vào thư mục `boot33-mockmvc`:

```bash
./gradlew clean test
./gradlew test --tests 'com.example.compat.GreetingController33SliceTest'
./gradlew test --tests 'com.example.compat.GreetingController33HttpTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

Nếu thư mục chưa có Wrapper, dùng `gradle clean test` với Gradle tương thích đã cài hoặc tạo Wrapper theo tiêu chuẩn build team.

**Nhánh A định nghĩa 5 `@Test` methods** (3 slice + 2 live HTTP). Không có số PASS thật vì bài viết chưa chạy Gradle. Xem report tại `build/reports/tests/test/index.html` và `build/test-results/test/` sau khi chạy.

## 16. Nhánh B — Spring Boot 3.5.x: tại sao có MockMvcTester?

Spring Framework **6.2** giới thiệu `org.springframework.test.web.servlet.assertj.MockMvcTester`. Nó dùng cơ sở hạ tầng `MockMvc`, nhưng cung cấp API để gửi request/đọc result/AssertJ assertions như:

```java
assertThat(mvc.get().uri("/api/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

So với `MockMvc.perform(...).andExpect(...)` truyền thống, cách này:
- Dễ phối hợp với các assertions AssertJ khác trong cùng test.
- Có `bodyJson()` để so sánh JSON/JsonPath.
- Có các assertions cho request/response/exception.
- Có behavior xử lý kết quả async khác với MockMvc raw; vẫn cần nắm contract và timeout.
- **Không có real HTTP port chỉ vì gọi MockMvcTester** — vẫn là server simulation trên mock Servlet objects.

**Tại sao chọn Boot 3.5 ở ví dụ?** Đây là nhánh đã quản lý Framework 6.2. Boot 3.4 cũng có API, nhưng 3.5 docs có ví dụ `@WebMvcTest` + `@MockitoBean` + `MockMvcTester` rõ ràng; nên dùng nó cho mẫu chuyển đổi.

## 17. Boot 3.5: build.gradle và dependency choices

**Chỉ cho boot35-mockmvctester**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Phiên bản 3.5.16 là một ví dụ patch thuộc nhánh 3.5**; không có nghĩa nó là patch mới nhất trong mọi môi trường tương lai. Khi dùng một patch khác, giữ Spring Framework version do Boot BOM quản lý.

Không thêm một `org.springframework:spring-test:7.0.0` thủ công để “mở khóa RestTestClient” trong project 3.5. Spring Framework 7 là một bước nâng major khác, đòi xem Servlet/Jakarta stack và Spring Boot 4.

### Điều kiện để auto-configure MockMvcTester

- Có `spring-test` với class `MockMvcTester` (Framework 6.2+).
- Có AssertJ từ `spring-boot-starter-test` trên test classpath.
- Test nạp MVC slice với `@WebMvcTest`, hoặc `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`.
- Test inject đúng `MockMvcTester`, không tự tạo một bean khác làm mất MVC filters/converters.

Nếu chỉ tạo một project Java thuần với `spring-test` mà không có Boot test autoconfigure, có thể dùng `MockMvcTester.of(controller)` hoặc `MockMvcTester.from(WebApplicationContext)` thủ công; **không mặc định @Autowired có bean** ngoài Spring Boot test setup phù hợp.

## 18. Boot 3.5: MockMvcTester cùng @MockitoBean

`boot35-mockmvctester/src/test/java/com/example/compat/GreetingController35SliceTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(GreetingController.class)
class GreetingController35SliceTest {

    @Autowired
    MockMvcTester mvc;

    @MockitoBean
    GreetingService service;

    @Test
    void plainTextWithAssertJFluentApi() {
        when(service.greeting("Ada"))
                .thenReturn(new GreetingMessage("Hello Ada"));

        assertThat(mvc.get().uri("/api/hello/Ada")
                        .accept(MediaType.TEXT_PLAIN))
                .hasStatusOk()
                .hasBodyTextEqualTo("Hello Ada");

        verify(service).greeting("Ada");
    }

    @Test
    void jsonPathFromResponseBody() {
        when(service.greeting("Lin"))
                .thenReturn(new GreetingMessage("Hello Lin"));

        assertThat(mvc.get().uri("/api/greetings/Lin")
                        .accept(MediaType.APPLICATION_JSON))
                .hasStatusOk()
                .hasContentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .bodyJson()
                .extractingPath("$.message")
                .asString()
                .isEqualTo("Hello Lin");

        verify(service).greeting("Lin");
    }

    @Test
    void unknownRouteIsNotFound() {
        assertThat(mvc.get().uri("/api/not-defined"))
                .hasStatus(HttpStatus.NOT_FOUND);
    }
}
```

Có **3 phương thức `@Test`** trong nhánh B. Tên `MockMvcTester` nằm ở `org.springframework.test.web.servlet.assertj`. Với Boot 3.5, `@WebMvcTest` vẫn dùng package `org.springframework.boot.test.autoconfigure.web.servlet`; sang Boot 4, package của Boot slice đổi.

### Tại sao cần .asString() sau JSONPath?

`bodyJson().extractingPath("$.message")` tạo một assertion đại diện cho JSON value; `asString()` chọn assertion type cho string. Nếu dùng `assertThat(...).bodyJson().isLenientlyEqualTo(...)`, có thể so sánh JSON với fixture; không dùng `hasBodyTextEqualTo` trên JSON chỉ để test một field vì raw JSON spacing có thể thay đổi.

### Lưu ý về @MockitoBean

Spring Framework 6.2 cung cấp `@MockitoBean` qua Spring Test bean override infrastructure. Nó giúp replace collaborator của controller trong context slice. Legacy `@MockBean` của Boot được deprecate trong 3.4+, nên khi dự án chuyển sang 3.5, có thể migrate dần sang `@MockitoBean`. Không thay annotation rồi bỏ qua những khác biệt trong bean naming/qualifier/context cache/override strategy.

## 19. MockMvcTester.of và MockMvcTester.from: test standalone hay full context?

Cùng Framework 6.2, ngoài Spring Boot auto-injection có thể tạo thủ công:

```java
GreetingController controller =
        new GreetingController(new GreetingService());

MockMvcTester tester =
        MockMvcTester.of(controller);

assertThat(tester.get().uri("/api/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

**Đây là snippet**, không phải test file bổ sung trong project B. Nó cần imports `MockMvcTester` và `assertThat` của AssertJ và controller/service classes. `of(controller)` dùng standalone MockMvc setup, rất thích hợp cho quick tests nhưng **không tự load** toàn bộ controller advice, security filters, custom converters của ứng dụng production.

Khi cần infrastructure/config từ Spring `WebApplicationContext`:

```java
MockMvcTester tester =
        MockMvcTester.from(webApplicationContext);
```

Snippet này cần `WebApplicationContext webApplicationContext` đã được tạo trong Spring TestContext. Nó sử dụng MVC application context, gần cấu hình thật hơn standalone, nhưng vẫn không mở TCP port.

## 20. MockMvcTester và xử lý exception bất thường

Với `MockMvc.perform(...)`, một exception không được controller/advice xử lý có thể truyền ra từ `perform`; với `MockMvcTester`, API AssertJ giữ result để bạn assert failure. Theo Spring 6.2 docs, các assertions như `hasFailed()`/`failure()` giúp kiểm tra exception, còn `hasStatus(...)` dùng cho response đã hoàn tất.

Không kết luận rằng một `RuntimeException` do controller ném sẽ tự biến thành HTTP 500 với JSON ProblemDetail. Để nhận response có status/body ổn định cần `@ExceptionHandler`/`@RestControllerAdvice` hoặc framework error handling được cấu hình đúng. **Khác biệt giữa unresolved exception và HTTP 500 response là một phần contract test**.

### Async requests

`MockMvcTester.exchange()` có behavior đợi async processing hoàn tất theo timeout của API, khác cách thao tác `MockMvc` raw thường cần `asyncDispatch(...)`. Tuy nhiên “đợi” ở đây không có nghĩa mọi @Async job/event mà controller fire-and-forget đều xong. Luôn test đúng completion boundary của operation; không dùng sleep cố định trong CI.

## 21. Nhánh C — Spring Boot 4.0.x: RestTestClient thuộc Framework 7.0

Spring Framework **7.0** đưa `org.springframework.test.web.servlet.client.RestTestClient` vào Spring Test. Khác `MockMvcTester` vốn wrap MockMvc/AssertJ, `RestTestClient` xây API giống blocking `RestClient` trước `exchange()` rồi mở đường cho `expectStatus()`, `expectHeader()`, `expectBody(...)`.

Các setup modes quan trọng:

| Factory | Có server TCP không? | Phạm vi kiểm thử |
| --- | --- | --- |
| `RestTestClient.bindToController(controller)` | Không | Standalone MVC controller |
| `RestTestClient.bindToApplicationContext(context)` | Không | MVC context qua MockMvc |
| `RestTestClient.bindToRouterFunction(router)` | Không | Spring MVC functional routes |
| `RestTestClient.bindToServer().baseUrl(url)` | Có | HTTP server đang chạy |
| Boot `@AutoConfigureRestTestClient` + `@WebMvcTest` | Không | MVC slice bound to MockMvc |
| Boot `@AutoConfigureRestTestClient` + `@SpringBootTest(RANDOM_PORT)` | Có | Live embedded server |

**Một API, hai chế độ kết nối**. Khi đọc test, phải xem nó bind đến controller/context hay server thật. Assertion `expectStatus().isOk()` không nói một mình rằng TCP đã hoạt động.

### RestTestClient không phải RestClient

`RestClient` là HTTP client dành cho ứng dụng, có `retrieve().body(...)` và `exchange(...)` callbacks. `RestTestClient` là một wrapper/facade kiểm thử server và sau `exchange()` cung cấp expectations. Không đổi tên biến rồi gọi các method test-only trên RestClient.

## 22. Boot 4: build.gradle và các module tách theo feature

**Chỉ cho boot40-resttestclient**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.9'
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
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-resttestclient'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

### Vì sao khác Boot 3.3/3.5?

Spring Boot 4 chia nhiều auto-configuration/test modules theo feature:

- `spring-boot-starter-webmvc` là starter web MVC được khuyến nghị thay cho legacy `spring-boot-starter-web`.
- `spring-boot-starter-webmvc-test` hỗ trợ Spring MVC tests và `@WebMvcTest` trong Boot 4.
- `spring-boot-starter-test` chứa general test libraries.
- `spring-boot-resttestclient` được khai báo rõ trong ví dụ để có Boot `@AutoConfigureRestTestClient` và các customizers; project có cả `spring-test`/RestTestClient từ Framework 7 qua các dependencies liên quan.
- Không thêm `spring-boot-starter-webflux` chỉ vì API test tên tương tự `WebTestClient`. Chúng là các stacks khác nhau.

**Điều kiện build:** Java 17+, Gradle **8.14+ hoặc 9.x**, Jakarta Servlet API tương thích với Boot 4/Spring 7. Nếu build đang dùng Gradle 8.7, hãy nâng Wrapper trước. Mọi patch upgrades phải theo Boot BOM và release notes.

### Vì sao không copy nguyên boot33 build.gradle rồi chỉ đổi version?

Boot 4 có nhiều module names/annotation packages thay đổi. Một artifact legacy có thể còn như alias/deprecated trong một patch, nhưng không nên dựa vào điều đó khi viết test mới. Migration nên cập nhật **plugin, starters, testing modules và imports** theo nhánh 4.0 đồng bộ.

## 23. Boot 4: @WebMvcTest + @AutoConfigureRestTestClient

`boot40-resttestclient/src/test/java/com/example/compat/GreetingController40SliceTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.client.RestTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(GreetingController.class)
@AutoConfigureRestTestClient
class GreetingController40SliceTest {

    @Autowired
    RestTestClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void mvcSliceTextWithoutListeningPort() {
        when(service.greeting("Ada"))
                .thenReturn(new GreetingMessage("Hello Ada"));

        client.get()
                .uri("/api/hello/Ada")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello Ada");

        verify(service).greeting("Ada");
    }

    @Test
    void mvcSliceJsonPath() {
        when(service.greeting("Lin"))
                .thenReturn(new GreetingMessage("Hello Lin"));

        client.get()
                .uri("/api/greetings/Lin")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello Lin");

        verify(service).greeting("Lin");
    }

    @Test
    void mvcSliceUnknownRoute() {
        client.get()
                .uri("/api/not-defined")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody();
    }
}
```

**Có 3 phương thức `@Test`** trong Boot 4 slice.

### Không có real network port

`@WebMvcTest` cấu hình MVC slice và `MockMvc` infrastructure. `@AutoConfigureRestTestClient` đưa `RestTestClient` có thể autowire, bind vào MockMvc của context. Mặc dù code dùng REST-client-like syntax, request không đi qua TCP socket. Nó vẫn là controller test, không phải end-to-end live HTTP test.

### Tại sao cần @MockitoBean thay vì @MockBean?

`GreetingService` không được MVC slice tự tạo. Spring Framework 7 hỗ trợ `@MockitoBean` qua Spring Test. Trong Boot 4, đừng copy `org.springframework.boot.test.mock.mockito.MockBean` của Boot 3.3 vào test mới; đó là legacy Boot test package và không phải đường đi supported cho Boot 4.

### Body JSON với expectBody().jsonPath

`expectBody().jsonPath("$.message").isEqualTo("Hello Lin")` assert một JSON field. Nó không phụ thuộc whitespace hay key order. `expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)` kiểm tra MIME type nhưng không nhất thiết yêu cầu exact charset parameter; thích hợp với JSON response.

## 24. Boot 4: full HTTP server bằng @SpringBootTest(RANDOM_PORT)

`boot40-resttestclient/src/test/java/com/example/compat/GreetingController40HttpTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class GreetingController40HttpTest {

    @Autowired
    RestTestClient client;

    @Test
    void liveHttpTextEndpoint() {
        client.get()
                .uri("/api/hello/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello Ada");
    }

    @Test
    void liveHttpJsonEndpoint() {
        client.get()
                .uri("/api/greetings/Lin")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello Lin");
    }
}
```

**Có 2 phương thức `@Test`** trong Boot 4 live HTTP class.

`@SpringBootTest(RANDOM_PORT)` khởi động server thật; Boot 4 `@AutoConfigureRestTestClient` tự cấu hình client trỏ relative URLs về embedded server đang chạy trên port ngẫu nhiên. Không hardcode `localhost:8080` và không dùng URL production để test.

### HTTP thật khác MockMvc

Full HTTP test đi qua socket, embedded server connector, request serialization và application runtime configuration. Nó có thể phát hiện nhiều lỗi network/filter/container configuration mà mock MVC tests không thấy. Đổi lại, startup chậm hơn và transaction boundary khác.

**Không suy từ assert status/body rằng đã test TLS production, proxy thực hay distributed deployment.** Embedded localhost server là một level integration, không phải E2E trên production infrastructure.

## 25. Boot 4: dùng RestTestClient trực tiếp, không cần Spring Boot context

`boot40-resttestclient/src/test/java/com/example/compat/GreetingController40StandaloneTest.java`:

```java
package com.example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

class GreetingController40StandaloneTest {

    private RestTestClient newClient() {
        GreetingController controller =
                new GreetingController(new GreetingService());

        return RestTestClient.bindToController(controller)
                .build();
    }

    @Test
    void standaloneControllerText() {
        newClient().get()
                .uri("/api/hello/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello Ada");
    }

    @Test
    void standaloneControllerJson() {
        newClient().get()
                .uri("/api/greetings/Lin")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello Lin");
    }
}
```

**Có 2 phương thức `@Test`** ở standalone class. `RestTestClient.bindToController` là Spring Framework API: không cần annotation `@AutoConfigureRestTestClient` vì client được tạo trực tiếp. Vẫn cần Spring MVC mock infrastructure trên test classpath, nhưng không tạo full Boot ApplicationContext hoặc open live port.

### Giới hạn của standalone

Bạn tạo `GreetingService` thật và truyền vào controller bằng constructor. Việc này hữu ích cho focused controller test nhưng không tự load:
- `@ControllerAdvice` của app,
- security filter chain,
- global JSON customization,
- interceptors,
- context-specific conversion/validation,
- custom Servlet filters,
- Spring AOP proxies quanh service.

Để kiểm tra configuration đó, dùng `bindToApplicationContext(...)` hoặc Boot `@WebMvcTest`/`@SpringBootTest` tùy mục tiêu. Đừng gọi standalone controller test là full application integration test.

## 26. RestTestClient.bindToServer(): một live server được quản lý bên ngoài

Nếu integration environment đã có HTTP server trên URL tin cậy, có thể dùng:

```java
RestTestClient client =
        RestTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:8080")
                .build();

client.get().uri("/api/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("pong");
```

**Snippet độc lập về ý tưởng**, yêu cầu một local server đúng API đang chạy ở cổng 8080 và class RestTestClient trên Framework 7.0+. Không đưa đoạn này vào test CI mặc định với fixed port; thay bằng local server được quản lý bởi `@SpringBootTest(RANDOM_PORT)` hoặc Testcontainers port mapping/URI.

### Không nhầm test client với HTTP client production

`RestTestClient` dùng một facade tương tự RestClient để mô phỏng hành vi **người dùng gọi server**. Production code không nên inject `RestTestClient` làm adapter HTTP bình thường. Nó thuộc test scope; dùng `RestClient` hoặc `WebClient` trong ứng dụng production.

## 27. RestTestClient assertion: built-in và AssertJ

Theo Spring Framework 7.0, built-in fluent expectations:

```java
client.get()
        .uri("/api/greetings/Lin")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello Lin");
```

Với typed body:

```java
client.get().uri("/api/hello/Ada")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello Ada");
```

Đây là snippets dùng `client` đã bind tới controller/server; không phải test methods bổ sung.

### AssertJ response API

Spring Framework 7 cung cấp `RestTestClientResponse` qua package `org.springframework.test.web.servlet.client.assertj`. Có thể dùng (snippet):

```java
RestTestClient.ResponseSpec spec =
        client.get().uri("/api/hello/Ada")
                .exchange();

RestTestClientResponse response =
        RestTestClientResponse.from(spec);

assertThat(response)
        .hasStatusOk()
        .bodyText()
        .isEqualTo("Hello Ada");
```

Cần imports `RestTestClient`, `RestTestClientResponse` và `org.assertj.core.api.Assertions.assertThat`. Nó là cách kiểm tra **AssertJ** trên result; không thay thế built-in expectations. Với typed body và JSONPath đơn giản, built-in `expectBody` thường đủ rõ.

### expectAll không phải retry

`expectAll(...)` dùng khi muốn thực hiện nhiều assertions dù một assertion thất bại, tương tự soft assertions. Nó **không** gửi HTTP request lại và không phải cơ chế resilience retry. Một test có nhiều assertions vẫn thường chỉ có một HTTP exchange.

### Consume response body khi cần

Khi dùng pooled HTTP buffers/leak detection, Spring documentation khuyến nghị **consume response body**, ví dụ qua `expectBody()` hoặc `expectBody(Void.class)` theo ngữ cảnh. Đừng bỏ resource management chỉ vì bạn chỉ cần status. Với mock environment, khác biệt buffer lifecycle có thể ít nổi bật hơn nhưng pattern đúng vẫn có ích.

## 28. Cái gì vẫn dùng được trên Boot 4?

**MockMvc không biến mất.** Spring Framework 7 vẫn hỗ trợ `MockMvc`. `MockMvcTester` cũng tiếp tục tồn tại. `RestTestClient` là một **lựa chọn mới**, không phải lệnh bắt buộc thay mọi test cũ.

Ví dụ Boot 4 có thể vẫn dùng:

```java
assertThat(mvc.get().uri("/api/ping"))
        .hasStatusOk()
        .hasBodyTextEqualTo("pong");
```

Nếu `mvc` là `MockMvcTester` auto-configured bởi Boot 4 `@WebMvcTest` khi AssertJ có sẵn. Với raw `MockMvc` bạn vẫn dùng `mvc.perform(get(...)).andExpect(...)`. Việc migrate toàn bộ vào RestTestClient có thể làm diff rất lớn mà chưa tạo thêm giá trị nếu team đang được bảo vệ tốt bằng MockMvc/MockMvcTester.

### Khi nào nên chuyển?

- Cần **cùng API test** cho MockMvc bound tests và real HTTP tests.
- Muốn fluent expectations và typed body trên MVC tests.
- Đã lên Boot 4 và team muốn chuẩn hóa HTTP server tests.
- Có yêu cầu giảm khác biệt giữa một số local controller tests và embedded HTTP tests.

### Khi nào không nên chuyển?

- Đang ở Boot 3.3 hoặc 3.5 và chưa có ngân sách nâng cấp.
- Chỉ cần kiểm tra service logic thuần Java, không cần MVC machinery.
- Test hiện tại dùng MockMvc-specific extensions/custom handlers quan trọng; việc chuyển chưa được đánh giá.
- Team cần giữ compatibility nhiều nhánh Spring Boot trong cùng codebase.
- Đang dùng `WebTestClient` cho reactive/WebFlux tests và API đó phù hợp.
- Muốn test HTTP outbound client: nên dùng MockRestServiceServer/MockWebServer, không phải RestTestClient server-side.

## 29. @MockitoBean là lỗi phiên bản khác thường đi kèm

Một StackOverflow snippet cho Boot mới:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Trên Boot 3.3.5 (Spring Framework 6.1), package bean override Mockito của Framework 6.2 **chưa có**. Cách đúng trên Boot 3.3:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

Khi sang 3.4/3.5, Framework 6.2 có `@MockitoBean` và Boot legacy `@MockBean` được deprecate; sang Boot 4 dùng Spring Test override. Nhưng không thay import **mà quên bean matching semantics**, đặc biệt nếu có:
- Nhiều beans cùng type.
- Bean name/qualifier.
- Spring context cache reuse.
- Scoped proxies.
- FactoryBean.
- Stubbing cần có trước khi một @PostConstruct code gọi collaborator.

### Vấn đề chuẩn bị mock lúc startup

Nếu service bị gọi trong `@PostConstruct` hoặc application runner, stubbing viết **trong @Test method** quá muộn — Spring context đã refresh. Cần test-specific configuration/injection trước startup hoặc refactor startup side effects. Không nhầm lỗi này với thiếu MockMvcTester API.

## 30. @WebMvcTest Boot 4 đổi package: lỗi thường bị bỏ sót

Một test dùng:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
```

đúng với Boot 3.3/3.5. Nhưng khi chuyển Boot 4, theo module mới hãy dùng:

```java
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
```

Tương tự `@AutoConfigureMockMvc` của Boot 4 nằm trong `org.springframework.boot.webmvc.test.autoconfigure`. Nếu chỉ nâng plugin mà giữ import cũ, lỗi `package does not exist` có thể xuất hiện trước khi test được discover.

### Checklist imports từng nhánh

**Boot 3.3**: Boot `@WebMvcTest` cũ, Boot `@MockBean` cũ, Spring `MockMvc`.

**Boot 3.5**: Boot `@WebMvcTest` cũ, Framework `@MockitoBean` mới, Spring `MockMvcTester` mới.

**Boot 4.0**: Boot `@WebMvcTest` mới, Framework `@MockitoBean`, Spring `RestTestClient`, Boot `@AutoConfigureRestTestClient`.

**Không có một import set duy nhất biên dịch trên cả ba nhánh** nếu source trực tiếp tham chiếu RestTestClient.

## 31. Vì sao không ép spring-test 7 vào Boot 3.3?

Ví dụ build patch sai:

```groovy
dependencies {
    // Sai: cố ép một mình Spring Test 7 vào Boot 3.3.
    testImplementation 'org.springframework:spring-test:7.0.0'
}
```

Đây là **snippet phản ví dụ**, không nằm trong runnable project. Spring Test 7 được xây để làm việc với Spring Framework 7 và runtime/container dependencies tương ứng. Boot 3.3 quản lý Spring Framework 6.1. Việc trộn major có thể làm test compile nhưng runtime fail, hoặc build fail vì API signature khác.

Những lỗi có thể phát sinh:
- `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`.
- `BeanCreationException` do Spring context methods không tương thích.
- Một controller test pass nhưng auto-configuration class khác fail.
- Incompatible Servlet/Jakarta types.
- Maven/Gradle resolution kéo nhiều Spring versions khác nhau.
- Test dependencies conflict với JUnit/Jackson/Mockito.

**Sửa đúng:** chọn Spring Boot release line tương thích với Framework version muốn dùng; kiểm tra BOM/Dependency Insight; nâng toàn bộ stack theo migration notes; chạy tests đầy đủ. Không tự “lắp” Spring Framework 7 vào Boot 3.3 bằng một số dependency overrides.

## 32. MockMvcTester, WebTestClient và RestTestClient khác nhau ở đâu?

| Tiêu chí | MockMvcTester | WebTestClient | RestTestClient |
| --- | --- | --- | --- |
| Bắt đầu có từ | Framework 6.2 | Có trước Framework 6.2 | Framework 7.0 |
| Backend | MockMvc, mock Servlet | WebFlux mock hoặc bind MVC/real HTTP | RestClient + MockMvc bridge hoặc real HTTP |
| Tập trung | MVC AssertJ assertions | Reactive style API | Blocking HTTP test style API |
| Server port | Không | Tùy setup | Tùy bindTo... |
| Ngữ cảnh lý tưởng | Spring MVC controller/slice | WebFlux, hoặc team đã dùng nó | Boot 4 MVC tests hoặc live HTTP với một API |
| Test dependency | spring-test + AssertJ + MVC test | spring-test/webflux test dependencies | Spring 7 spring-test + Boot test wiring khi autowire |
| App HTTP client production? | Không | Không | Không |

Cả ba là **test APIs**. Không vì chúng có fluent syntax mà coi chúng có cùng backpressure, threading, connection pooling hoặc message decoding. Với WebFlux, `WebTestClient` là lựa chọn tự nhiên; với Spring MVC Boot 3.5, `MockMvcTester` tiện và đủ mạnh; với Spring MVC Boot 4, `RestTestClient` bổ sung lựa chọn thống nhất mock/live tests.

### RestTestClient không phải một alias của WebTestClient

Tên method có thể giống như `exchange().expectStatus().isOk()`, nhưng package, implementation, dependencies và supported server setup khác. Không dùng import `org.springframework.test.web.reactive.server.WebTestClient` rồi gọi code ví dụ `RestTestClient.bindToController(...)`; đó là class khác.

## 33. Các lỗi compile và runtime thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `cannot find symbol MockMvcTester` trong Boot 3.3 | Spring Test 6.1 chưa có | Dùng MockMvc hoặc nâng Boot 3.4/3.5 |
| `cannot find symbol RestTestClient` trong Boot 3.5 | Spring Test 6.2 chưa có | Dùng MockMvcTester/WebTestClient hoặc nâng Boot 4 |
| `package ...web.servlet.assertj does not exist` | Spring Test quá cũ hoặc dependency thiếu | Kiểm tra `spring-test` testCompileClasspath |
| `package ...web.servlet.client does not exist` | Không ở Framework 7 | Kiểm tra Boot4 BOM |
| `package ...bean.override.mockito... does not exist` | Framework 6.1 | @MockBean ở Boot3.3 hoặc nâng release line |
| `@WebMvcTest import cũ lỗi ở Boot 4` | Boot test package được tách | Đổi Boot4 package và test starter |
| `No qualifying bean of type MockMvcTester` | MVC test bean không được auto-configured | @WebMvcTest/@AutoConfigureMockMvc, AssertJ & classpath |
| `No qualifying bean of type RestTestClient` | Không có @AutoConfigureRestTestClient hoặc module | Add Boot4 test config/dependency, bind manually |
| `NoSuchMethodError sau nâng JAR` | Spring artifacts khác major/minor | Re-align Boot BOM/Framework dependencies |
| `NoClassDefFoundError Servlet...` | Jakarta Servlet API/container không tương thích | Sửa stack/Servlet dependency version |
| `Failed to load ApplicationContext` | Missing mock collaborator hoặc bad slice | @MockitoBean/@MockBean đúng branch |
| Test status 200 nhưng body null | Service mock chưa stub | Stub đúng argument, assert payload |
| Test 404 trên path không tồn tại lúc mock | Request mapping khác | Đối chiếu annotation/URI |
| `RestClient` không có expectStatus | Nhầm production client với test client | Dùng RestTestClient/WebTestClient/MockMvc |
| Live HTTP test không kết nối được | Hardcoded port 8080 hoặc server chưa start | RANDOM_PORT + auto-configured RestTestClient |
| Test pass với MockMvc nhưng fail live | Filters/session/encoding/network/transaction khác | Thêm real HTTP contract tests |
| Boot 4 build Gradle plugin fail | Gradle dưới 8.14 hoặc Java/toolchain lệch | Nâng wrapper và kiểm tra JDK |
| JSON assertion fail sau migration | Jackson/codec/property naming thay đổi | Check content type, mapper/schema, fixtures |
| @MockitoBean không thay bean mong muốn | Ambiguous type/qualifier | Named override hoặc qualifier rõ |
| Tests khác thất bại sau adding new test modules | Classpath/auto-config changes | Phân tích dependency graph và startup logs |

## 34. Đừng chữa compile error bằng reflection fallback trong production test

Một kỹ thuật có thể kiểm tra `Class.forName("...MockMvcTester")` ở runtime. Nhưng nếu Java source import một class chưa tồn tại, **compiler đã fail trước runtime**. Vì vậy reflection-based “if present” không làm cho file test compile được với Boot 3.3.

Nếu một thư viện muốn hỗ trợ nhiều Spring versions, các lựa chọn đúng hơn:
- Chỉ dựa vào API tồn tại trong version tối thiểu (ví dụ MockMvc).
- Tách adapters/test sources theo `sourceSets`/modules và release-specific classpaths.
- Multi-release testing matrix trong CI nhưng test class tương ứng được compile riêng.
- Có integration tests thực trên từng supported version, không chỉ dynamic detection.
- Cố định Java toolchain, Gradle/Maven plugins và BOM per variant.
- Nếu thật sự cần reflection để bridge optional API, phải thiết kế đầy đủ linkage/catch/compatibility tests; không dùng làm workaround bừa.

**Version gate là compile-time contract**, không chỉ là runtime `assumeTrue(...)`.

## 35. Một ma trận CI nên kiểm gì?

Một project có nhiều supported Boot lines có thể dùng CI matrix:

```text
Variant A: Java 17 | Boot 3.3.5 | Framework 6.1
  -> compile MockMvc tests
  -> run MVC slice + TestRestTemplate HTTP tests

Variant B: Java 17 | Boot 3.5.x | Framework 6.2
  -> compile MockMvcTester tests
  -> run slice with @MockitoBean

Variant C: Java 17 | Boot 4.0.x | Framework 7.0
  -> Gradle 8.14+
  -> compile RestTestClient tests
  -> run MockMvc-bound slice + RANDOM_PORT HTTP tests
```

Đừng đặt các files test mới nhất vào source set chạy trên mọi Boot line rồi đánh dấu `@Disabled` hoặc JUnit condition. `@Disabled`/`@EnabledIf...` chỉ điều khiển execution **sau khi compile**; class không tồn tại vẫn làm `compileTestJava` fail. Nếu test C dùng RestTestClient, chỉ compile C với Boot 4 classpath.

### CI artifact/report

Theo dõi riêng:
- compile status;
- JUnit case count/skipped count;
- Java/Gradle/Boot/Framework versions;
- HTML/JUnit XML reports;
- TestContext startup errors;
- dependency insight khi failure là classpath conflict.

Nếu một matrix variant fail ở compile, sẽ không có JUnit testcase cho nó. Đừng viết báo cáo “0 test failures” mà quên build failure.

## 36. Kiểm tra kỹ năng đặt tên và lựa chọn API

Một bảng quyết định ngắn:

| Bối cảnh | Khuyến nghị |
| --- | --- |
| Boot 3.3, MVC slice | `MockMvc` |
| Boot 3.3, live HTTP server | `TestRestTemplate` hoặc `WebTestClient` khi cấu hình |
| Boot 3.4/3.5, MVC slice | `MockMvc` hoặc `MockMvcTester` |
| Boot 3.4/3.5, live HTTP | `TestRestTemplate`/`WebTestClient` |
| Boot 4, MVC slice | `MockMvc`/`MockMvcTester`/`RestTestClient` |
| Boot 4, live HTTP | `RestTestClient` bind server hoặc auto-config |
| Test client outbound RestClient | `MockRestServiceServer`, MockWebServer, WireMock |
| Test WebFlux/reactive endpoint | `WebTestClient` |
| Unit test service không liên quan HTTP | JUnit + Mockito, không cần MVC |
| Test business DB commit | JDBC/JPA/Testcontainers integration, không suy từ HTTP mock |

**Nguyên tắc chọn thấp nhất đủ dùng:** nếu một MockMvc test hiện tại thể hiện rõ contract và ổn định, bạn không cần đổi sang RestTestClient chỉ vì release mới. Nếu cần loại lỗi real HTTP/serialization khác mock servlet, thêm một số ít RANDOM_PORT tests thay vì chuyển mọi test sang live server nặng hơn.

## 37. Những sai lầm khi migrate @WebMvcTest slice

1. **Quên thay dependency mock:** `@WebMvcTest` không quét mọi `@Service`, nên controller constructor injection fail.
2. **Dùng @Mock trong unit style thay vì @MockitoBean trong Boot 4 Spring context:** mock field không tự thay Spring bean.
3. **Chuyển import @WebMvcTest nhưng không thêm test starter Boot4:** annotation/package có thể thiếu.
4. **Test path string sai:** Swagger URL, controller class path hoặc media type khác sau nâng.
5. **MockMvcTester thiếu AssertJ:** bean/assertion class không sẵn đúng như ví dụ.
6. **Security filter mặc định khác:** một `401/403` có thể là security configuration, không phải API response bug.
7. **Thay Spring Framework BOM đơn lẻ:** class linkage fail.
8. **Mix Spring WebMVC/WebFlux không rõ:** Boot ưu tiên MVC khi cả hai trên classpath; test configuration phải explicit.
9. **Không cập nhật test report paths/source sets:** CI mất tests dù local build chạy.
10. **Chỉ kiểm status:** schema/Content-Type/body bị hỏng không được phát hiện.
11. **Test @Transactional với RANDOM_PORT:** server transaction khác client test thread.
12. **Nhìn compile success và kết luận integration pass:** compile chỉ xác nhận API/linkage một phần.

## 38. Vì sao auto-configuration có thể khác giữa @WebMvcTest và @SpringBootTest?

`@WebMvcTest` là test slice, chỉ nạp một phần application context liên quan Spring MVC. Các bean nằm ngoài scan scope (business services/repositories) cần `@MockBean` hoặc `@MockitoBean` đúng version, hoặc `@Import`/test configuration nếu muốn bean thật.

`@SpringBootTest` có thể nạp toàn bộ application context; khi kết hợp `@AutoConfigureMockMvc` bạn vẫn dùng mock Servlet server, không mở port mặc định. `@SpringBootTest(RANDOM_PORT)` mở HTTP server thật. Với Boot4 `@AutoConfigureRestTestClient`, client target phụ thuộc vào test environment — mock MVC bound hoặc server bound. Một test chỉ có `@SpringBootTest` **không** tự đảm bảo có `@Autowired RestTestClient` nếu thiếu test auto-configuration/module.

### Khi nào cần @AutoConfigureMockMvc?

Với Boot3.3/3.5:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullContextMvcTests {
    @Autowired MockMvc mvc;
}
```

Đây là **snippet test class chưa có @Test**, cần imports Boot-version-correct. `@SpringBootTest` không nhất thiết auto-create MockMvc bean nếu không có `@AutoConfigureMockMvc`; `@WebMvcTest` thường đã cung cấp. Với Boot4, package import của `@AutoConfigureMockMvc` chuyển sang `org.springframework.boot.webmvc.test.autoconfigure`.

### Mock MVC không phải live HTTP

`@AutoConfigureMockMvc` vẫn làm request handling bằng mock servlet objects. Dù bạn có controller security filters, test sẽ không chứng minh TCP connection management/real deployed proxy headers. Chọn test level theo contract chứ không theo “cảm giác integration”.

## 39. Phân biệt lỗi classpath với lỗi nghiệp vụ khi điều tra

Thứ tự debug:

1. Đọc task thất bại: `compileTestJava` hay `test`?
2. Nếu compile error, đọc import/package và dependency tree trước khi xem business code.
3. Nếu `NoClassDefFoundError`/`NoSuchMethodError`, xem resolved versions của tất cả Spring artifacts, không chỉ `spring-test`.
4. Nếu context fail, xác định đúng `@WebMvcTest` Boot package và collaborator bean override.
5. Nếu chỉ một JUnit assertion fail, xem request URI, Accept/Content-Type, body, stubbing và MVC advice.
6. Nếu MockMvc pass nhưng HTTP fail, xem embedded server port, serialization, filters, cookies/headers, transactions và networking.
7. Nếu chỉ CI fail, xem JDK/Gradle Wrapper/test source sets/cache/JUnit versions.
8. Nếu còn lỗi, tạo minimal reproduction với một controller và một test của đúng nhánh, thay vì trộn code 6.1/6.2/7.0.

Một ví dụ dễ mắc: IDE cache nhận diện `MockMvcTester` từ project A Boot3.5 nhưng Gradle project B Boot3.3 compile báo missing class. Luôn tin **build resolved classpath của module đang chạy**, không dựa vào autocomplete từ một module khác.

## 40. MockMvcTester có thể giúp test gọn, nhưng không phải replacement bắt buộc

`MockMvc`:

```java
mvc.perform(get("/api/hello/Ada"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello Ada"));
```

`MockMvcTester`:

```java
assertThat(mvc.get().uri("/api/hello/Ada"))
        .hasStatusOk()
        .hasBodyTextEqualTo("Hello Ada");
```

`RestTestClient`:

```java
client.get().uri("/api/hello/Ada")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello Ada");
```

Ba snippets minh họa sự khác biệt về API surface; biến `mvc` có type khác nhau trong hai đoạn đầu. Không đặt cả ba vào một class Boot 3.3. Spring Boot mới vẫn hỗ trợ cách đầu; chọn API dựa vào dependency support và nhu cầu assertions.

## 41. Khi nào nên dùng typed body thay cho raw JSON?

Với RestTestClient, `expectBody(GreetingMessage.class)` có thể decode JSON thành Java record. Khi test cần kiểm tra schema fields theo API contract, JSONPath thường trực quan hơn. Khi test cần business object equality, typed body hữu ích.

Ví dụ trong Boot4 standalone/live:

```java
client.get().uri("/api/greetings/Lin")
        .exchange()
        .expectStatus().isOk()
        .expectBody(GreetingMessage.class)
        .isEqualTo(new GreetingMessage("Hello Lin"));
```

Đây là **snippet không thuộc @Test method mới**. Nếu app dùng Jackson customization, polymorphism, dates/timezone hoặc JSON modules, test decode bằng client có thể khác test JSON bytes; chọn assertion phù hợp và kiểm tra JSON response thật khi cần.

`MockMvcTester` thiên về AssertJ over MockMvc result, có `bodyJson().extractingPath(...)`; nó không dùng chính API `expectBody(Class)` của RestTestClient. Tương tự, `MockMvc` truyền thống dùng `jsonPath(...)` result matcher. Những API khác nhau này lý giải nhiều lỗi “cannot resolve method” khi copy code giữa clients.

## 42. Các giới hạn và thay đổi liên quan Servlet 6.1, Jakarta và Boot 4

Boot4/Spring7 đổi nhiều phần web stack, bao gồm Servlet API baseline. Một third-party filter/Servlet container cũ có thể không tương thích dù REST controller code vẫn biên dịch. Nếu test `@WebMvcTest` pass mà live HTTP test fail, kiểm tra:
- Servlet version và embedded Tomcat/Jetty tương thích;
- Jakarta imports thay vì javax cũ;
- custom servlet filter implementations;
- MVC request path matching;
- HTTP message converter/Jackson upgrades;
- Spring Security version/config;
- bean/auto-configuration changes;
- test modules và JUnit Platform versions;
- logging/observation filters.

Không kết luận “RestTestClient gây fail” chỉ từ thời điểm đổi API. Nâng Boot4 là một migration framework rộng; tách lỗi compile test code khỏi lỗi runtime application configuration.

### Một thủ thuật thực tế

Trước khi migrate tests sang RestTestClient, cho **cùng endpoint** chạy qua MockMvc trên Boot4. Nếu MockMvc pass nhưng RestTestClient mock-bound fail, kiểm tra test wiring/assertion semantics. Nếu cả hai pass mock-bound nhưng live HTTP fail, điều tra networking/container/real server behavior. Kết quả so sánh giúp cô lập boundary.

## 43. Bảo trì codebase nhiều branches: đặt test adapter theo version

Một thư viện nội bộ cần hỗ trợ Boot3.3 và Boot4 có thể:
- Viết **core contract tests** không phụ thuộc test facade mới, ví dụ plain MockMvc dùng ở cả hai versions.
- Viết **version-specific module tests** ở source sets hoặc subprojects chỉ compile với relevant BOM.
- Khi nâng min supported version lên Boot3.5, có thể bổ sung MockMvcTester.
- Khi min supported lên Boot4, có thể bổ sung RestTestClient.
- Dùng dependency compatibility test suite, không dựa vào reflection fallback để che thiếu class.
- Không copy/paste ba test classes vào mọi module rồi @Disabled những classes thiếu dependency — compiler vẫn fail.
- Dùng CI version matrix với build reports riêng theo module/JDK/Boot line.
- Chạy tests ở ít nhất min and max supported versions; một API tồn tại ở latest chưa đủ chứng minh oldest support.

### Quy định về support

Nếu team công bố “tương thích Spring Boot 3.3–4.0”, phải có **một bộ code có thể compile phù hợp từng version** hoặc modules tách biệt; nếu thư viện public API dùng thẳng `RestTestClient` trong signatures, consumers Boot3.3 không thể compile với cùng artifact trừ khi có adapter/layer phù hợp.

## 44. Cách đọc Release Notes và Javadoc 'Since'

Khi gặp class lạ trong đoạn test:

1. Xác định **fully qualified class name**.
2. Mở API Javadoc versioned của Spring Framework/Boot.
3. Tìm field **Since** nếu có; phân biệt introduction version với version được deprecate/removal.
4. Đọc package/artifact nơi class sống.
5. Đọc dependency BOM mapping của Spring Boot release line.
6. Đọc Spring Boot testing reference của **đúng version**, không dùng trang "current" mặc định.
7. Xác định annotated auto-config module có nằm trên test runtime classpath không.
8. Xác định method call examples trong đúng Javadoc version, vì signatures có thể thay qua milestones.
9. Chạy Gradle dependencyInsight và compile một test tối giản.
10. Sau đó mới refactor nhiều tests, luôn giữ regression reports.

**Milestone/RC/SNAPSHOT API** có thể thay trước GA; không lấy ví dụ milestone rồi áp cho GA khác release mà không kiểm tra. Với `MockMvcTester`, Javadoc của Framework6.2.0 milestone và GA đều có entrypoint; với `RestTestClient`, verify GA 7.0/API hiện tại.

## 45. Checklist QA cho pull request chuyển đổi

- [ ] Ghi rõ Boot branch/patch, Framework branch và Java/Gradle version?
- [ ] Xác nhận MockMvcTester chỉ dùng ở Framework 6.2+?
- [ ] Xác nhận RestTestClient chỉ dùng ở Framework 7.0+?
- [ ] Không nhầm RestClient production với RestTestClient testing?
- [ ] Không nhầm WebTestClient với RestTestClient?
- [ ] Không nâng riêng spring-test major vượt Boot BOM?
- [ ] Không để unsupported test sources trong project Boot3.3/3.5?
- [ ] Boot3.3 dùng @MockBean đúng package?
- [ ] Boot3.5+ dùng @MockitoBean khi migrate và test bean override?
- [ ] Boot4 @WebMvcTest và @AutoConfigureMockMvc đúng package mới?
- [ ] Boot4 có test starter/module và @AutoConfigureRestTestClient đúng?
- [ ] Boot4 dùng Gradle8.14+ và JDK17+?
- [ ] @WebMvcTest đủ mock collaborators, không load DB ngoài ý định?
- [ ] Test MockMvcTester đủ AssertJ dependency?
- [ ] Phân biệt mock-bound tests với real HTTP tests?
- [ ] Tests assert status, Content-Type và body thay vì chỉ assert no exception?
- [ ] JSONPath/typed body assertions không phụ thuộc formatting ngoài hợp đồng?
- [ ] Có test 404/negative branch mà không che context failure?
- [ ] @SpringBootTest(RANDOM_PORT) tránh hardcoded listening port?
- [ ] Cảnh giác transactions khác thread khi live HTTP tests ghi DB?
- [ ] Có report/CI matrix cho mỗi supported version?
- [ ] Đọc dependencyInsight khi compile/linkage fail?
- [ ] Không khẳng định các test đã PASS nếu chưa chạy Gradle?
- [ ] Không tạo false green bằng skip toàn bộ tests không compile?
- [ ] Tài liệu code examples được gắn đúng version/module?

## 46. Bài tập thực hành

1. Tạo `boot33-mockmvc` từ project A; chạy `GreetingController33SliceTest`.
2. Chạy `GreetingController33HttpTest` và so sánh real port với mock servlet.
3. Cố import MockMvcTester vào Boot3.3 sandbox, đọc compile error; bỏ import để khôi phục.
4. Dùng `dependencyInsight --dependency spring-test` để xem Framework6.1.
5. Nâng sandbox sang Boot3.5, bỏ các test files không đúng version và thêm class `GreetingController35SliceTest`.
6. Thử `MockMvcTester.of(new GreetingController(new GreetingService()))` trong một test độc lập, so sánh with @WebMvcTest.
7. Thêm JSON field vào GreetingMessage và so sánh `bodyJson().extractingPath` với raw body equality.
8. Dùng `@MockitoBean` trong Boot3.5 và so sánh với legacy @MockBean behavior.
9. Thử import RestTestClient trên Boot3.5 sandbox, phân tích vì sao chưa có.
10. Nâng thử một project riêng lên Boot4.0 với Gradle8.14+, đổi test starter và @WebMvcTest imports.
11. Chạy Boot4 slice test qua @AutoConfigureRestTestClient và assert response JSONPath.
12. Chạy Boot4 live HTTP test qua RANDOM_PORT + RestTestClient.
13. Chạy standalone RestTestClient.bindToController và kiểm tra nó không mở port.
14. Dùng RestTestClient.bindToServer với local test server chủ động, không gọi production URL.
15. Tạo một REST client outbound, kiểm thử bằng MockRestServiceServer; giải thích khác với server test.
16. Viết WebFlux endpoint và dùng WebTestClient; so sánh không nhầm tên RestTestClient.
17. Kiểm tra nếu thiếu AssertJ trên classpath thì MockMvcTester assertions/bean injection bị ảnh hưởng như thế nào.
18. Trộn cố ý spring-test7 vào Boot3.3 sandbox, đọc dependency tree và khôi phục BOM đúng.
19. Thêm Spring Security vào app ở một nhánh, quan sát 401/403 khi chưa có test auth.
20. Tạo CI matrix 3 variants, giữ JUnit XML/HTML reports riêng.
21. Cố đặt @Disabled trên một test source import unsupported class và xác nhận compiler vẫn fail.
22. Với MockMvcTester async API, thử exchange()/asyncExchange() với endpoint async đúng setup.
23. Đọc Javadoc Since và reference của Framework6.1/6.2/7.0, lập bảng imports riêng cho team.
24. Sau khi migrate, chạy cả full suite/CI và so sánh count pass/fail/skip trước và sau.

## 47. Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — Spring MVC Test / MockMvc](https://docs.spring.io/spring-framework/reference/6.1/testing/spring-mvc-test-framework.html): MockMvc và test MVC trước MockMvcTester.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @WebMvcTest, @AutoConfigureMockMvc, @MockBean, TestRestTemplate.
- [Spring Framework 6.2 — MockMvc AssertJ Integration](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/assertj.html): MockMvcTester, AssertJ assertions và JSON support.
- [Spring Framework 6.2 — MockMvcTester Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/web/servlet/assertj/MockMvcTester.html): factories of/from và fluent API.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvcTester bean injection, @MockitoBean và MVC testing.
- [Spring Framework 7.0 — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html): bindToController, bindToApplicationContext, bindToServer, built-in expectations.
- [Spring Boot 4.0 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): @AutoConfigureRestTestClient, mock-bound và RANDOM_PORT.
- [Spring Boot 4.0 — Test Modules](https://docs.spring.io/spring-boot/4.0/reference/testing/test-modules.html): module phân tách theo feature.
- [Spring Boot 4.0 — Build Systems](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html): webmvc/test starter coordinates.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Java 17, Gradle 8.14+.
- [Spring Framework 7 — RestTestClient Builder Javadoc](https://docs.spring.io/spring-framework/docs/7.0.0-M8/javadoc-api/org/springframework/test/web/servlet/client/RestTestClient.Builder.html): Since 7.0, builder semantics.
- [Spring Blog — The state of HTTP clients in Spring](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/): lý do có RestTestClient và sự khác biệt với WebTestClient.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): @Test, context lifecycle/runner.
- [Gradle — Dependency Management & Dependency Insight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencyInsight, versions và conflicts.

## 48. Kết luận

**API chỉ dùng được khi version và module hỗ trợ nó.** Trên Spring Boot 3.3.5 / Framework6.1, dùng `MockMvc` và `TestRestTemplate` đúng dependency; `MockMvcTester` và `RestTestClient` chưa tồn tại. Khi nâng lên Boot3.4/3.5 / Framework6.2, có `MockMvcTester` cùng `@MockitoBean` để viết AssertJ MVC tests. Khi nâng lên Boot4.0 / Framework7.0, `RestTestClient` cho phép một test facade với hai chế độ: MockMvc-bound không real server và bindToServer/RANDOM_PORT có real HTTP, đi kèm các test modules/annotation package Boot4 mới.

Không ép `spring-test` của một major khác vào Boot BOM cũ, không @Disabled một file test không compile, không nhầm RestClient outbound với RestTestClient inbound. Thay vì nâng toàn bộ suite chỉ vì cú pháp fluent, hãy chọn test API đúng với release line, khẳng định behavior bằng status/body assertions và mở rộng từ mock MVC đến real HTTP khi cần. **Việc thấy 15 phương thức @Test trong các ba nhánh ví dụ không phải bằng chứng 15 tests đã PASS; phải chạy Gradle/JUnit riêng từng branch rồi kiểm tra reports thực tế.**
