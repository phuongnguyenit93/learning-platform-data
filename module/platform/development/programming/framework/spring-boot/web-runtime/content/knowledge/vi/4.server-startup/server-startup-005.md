# WebServerInitializedEvent và lấy cổng thực tế sau khởi động

## 1. Vấn đề: cổng cấu hình có thể khác cổng đang lắng nghe

Khi ứng dụng Spring Boot web khởi động, embedded HTTP server (chẳng hạn Tomcat trong Spring MVC hoặc Reactor Netty trong Spring WebFlux) phải bind vào một địa chỉ/cổng để nhận kết nối.

Phân biệt ba giá trị:

- **Cổng cấu hình:** giá trị `server.port` trong `application.properties`/`application.yml`, environment hoặc tham số chạy. Khi không tùy chỉnh, cổng HTTP ứng dụng Spring Boot thường là **8080**.
- **Cổng thực tế:** số cổng mà embedded web server thực sự bind thành công trên máy chạy ứng dụng.
- **Cổng công khai:** cổng mà client bên ngoài truy cập qua Docker port mapping, reverse proxy, load balancer, Kubernetes Service/Ingress hoặc NAT. Giá trị này có thể khác cổng nội bộ.

Ví dụ `server.port=8080` thường dẫn đến cổng thực tế 8080 nếu ứng dụng khởi động thành công. Nhưng `server.port=0` có nghĩa **yêu cầu hệ điều hành chọn một cổng khả dụng**: cổng thực tế sẽ là một số dương do hệ điều hành cấp, thay đổi tùy lần chạy.

Đọc `server.port` từ cấu hình trong trường hợp này chỉ thu được **0**, không biết được client cần gọi cổng nào. Spring Boot giải quyết bằng sự kiện **`WebServerInitializedEvent`**, phát ra khi embedded web server đã sẵn sàng. Từ event, ta đọc trực tiếp cổng đang được server sử dụng.

## 2. `WebServerInitializedEvent` là gì?

Trong Spring Boot 3.3.x, `org.springframework.boot.web.context.WebServerInitializedEvent` là lớp sự kiện chung được phát khi một `WebServer` sẵn sàng. Mục đích tiêu biểu là cho phép code nhận biết cổng local thực tế của server sau khi khởi tạo.

Các API quan trọng:

| API | Ý nghĩa |
|---|---|
| `WebServerInitializedEvent` | Event vòng đời khi embedded web server đã khởi tạo |
| `event.getWebServer()` | Lấy `WebServer` phát sinh event |
| `event.getWebServer().getPort()` | Lấy cổng thực tế của server ấy |
| `event.getApplicationContext()` | Lấy `WebServerApplicationContext` tạo ra server |
| `event.getApplicationContext().getServerNamespace()` | Xác định namespace, giúp phân biệt server chính và server quản trị |
| `ApplicationListener<WebServerInitializedEvent>` | Cách đăng ký listener bằng một Spring bean |
| `@EventListener` | Cách viết callback nhận event bằng annotation |

Các subclass thường gặp:

- **`ServletWebServerInitializedEvent`** với Servlet stack / Spring MVC.
- **`ReactiveWebServerInitializedEvent`** với reactive stack / Spring WebFlux.

Cả hai là `WebServerInitializedEvent`, nên listener chỉ dùng `getWebServer().getPort()` thường không cần phụ thuộc trực tiếp vào Tomcat, Netty hoặc Servlet/Reactive subclass.

**Đây không phải sự kiện HTTP request.** Nó được phát trong quá trình startup, không cần có người dùng gọi endpoint.

## 3. Sự kiện xảy ra ở đâu trong startup?

```text
main() → SpringApplication.run(...)
       │
       ├── Tạo và refresh ApplicationContext
       ├── Tạo/cấu hình các bean và web infrastructure
       ├── Chuẩn bị embedded web server
       │
       ├── Embedded web server bắt đầu lắng nghe
       │       │
       │       └── Publish WebServerInitializedEvent
       │                   │
       │                   └── Listener đọc event.getWebServer().getPort()
       │
       ├── Hoàn thành phần startup còn lại
       ├── ApplicationStartedEvent / ApplicationRunner / CommandLineRunner
       ├── ApplicationReadyEvent
       └── SpringApplication.run(...) trả về
```

Sơ đồ là đường đi khái niệm của startup Spring Boot thông thường. `WebServerInitializedEvent` cho biết web server đã khởi tạo để có thể đọc cổng; **không khẳng định toàn bộ ứng dụng và phụ thuộc ngoài đã sẵn sàng phục vụ nghiệp vụ**. Chẳng hạn runner vẫn có thể đang thực thi, database có thể chưa đáp ứng, hoặc health/readiness check có thể chưa đạt.

`ApplicationReadyEvent` mang ý nghĩa SpringApplication đã đi qua startup và các application/command-line runners, nhưng cũng không thay thế được kiểm tra readiness thực tế.

Nếu bind cổng thất bại (ví dụ cổng cố định bị ứng dụng khác chiếm), server không khởi tạo thành công, do đó không nên kỳ vọng event thành công để lấy được cổng. Nếu cấu hình `spring.main.web-application-type=none`, không có embedded HTTP server của web application để phát event này.

## 4. Ví dụ hoàn chỉnh: ứng dụng tự chọn cổng rồi in cổng thật

Ví dụ sử dụng Java 17, Spring Boot 3.3.13 và Spring MVC (`spring-boot-starter-web`). Ứng dụng dùng `server.port=0` và cung cấp endpoint `GET /ping`. Không cần database hay Actuator để chạy ví dụ cơ bản.

Cấu trúc:

```text
web-port-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/webport/WebPortApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/webport/WebPortApplicationTests.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
# Hệ điều hành sẽ chọn một cổng khả dụng.
server.port=0
```

**`src/main/java/com/example/webport/WebPortApplication.java`:**

```java
package com.example.webport;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebPortApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebPortApplication.class, args);
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> logApplicationPort() {
        return event -> {
            // Trong cấu hình thông thường, null là namespace của app server.
            // Management server riêng thường có namespace "management".
            if (event.getApplicationContext().getServerNamespace() != null) {
                return;
            }

            int port = event.getWebServer().getPort();
            System.out.println("APP_PORT=" + port);
        };
    }
}

@RestController
class PingController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
```

Đây là **một file Java hợp lệ**: chỉ `WebPortApplication` là top-level public class, còn `PingController` là top-level package-private class thuộc cùng package. `@SpringBootApplication` bật auto-configuration và component scanning; `@RestController` đăng ký endpoint và method `@Bean` đăng ký listener.

Dòng quan trọng là:

```java
int port = event.getWebServer().getPort();
```

`getPort()` lấy cổng từ server thực sự phát event. Kiểm tra namespace giúp ví dụ chỉ ghi cổng server chính trong ứng dụng Boot thông thường; ý nghĩa các server phụ được giải thích tại mục 8.

**Chạy ứng dụng:**

```bash
gradle bootRun
```

Dùng Gradle tương thích Boot 3.3 và JDK 17+, hoặc Gradle Wrapper nếu project có: `./gradlew bootRun` (macOS/Linux), `.\gradlew.bat bootRun` (Windows PowerShell).

Log có thể chứa dòng như sau:

```text
... Tomcat started on port 53147 (http) ...
APP_PORT=53147
... Started WebPortApplication ...
```

**53147 chỉ là số minh họa; không được coi là kết quả cố định.** Nội dung và thứ tự log của Spring/Tomcat cũng có thể khác theo cấu hình. Điều quan trọng là listener in `APP_PORT=...` với cổng vừa được cấp sau khi web server khởi tạo.

Với cổng đã in (giả sử là 53147), gọi:

```bash
curl -i http://localhost:53147/ping
```

Phản hồi mong đợi: **HTTP 200** và body JSON:

```json
{"message":"pong"}
```

Nếu cổng in ra là số khác, hãy thay số đó trong URL. Ví dụ không tự mở cổng public qua firewall/container; nó chỉ cho thấy web server nội bộ đang lắng nghe.

## 5. Viết listener bằng `@EventListener`

Một Spring bean có thể lắng nghe event bằng annotation, không cần viết `@Bean ApplicationListener`:

```java
package com.example.webport;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class PortObserver {

    @EventListener
    void onWebServerInitialized(WebServerInitializedEvent event) {
        if (event.getApplicationContext().getServerNamespace() == null) {
            int actualPort = event.getWebServer().getPort();
            System.out.println("OBSERVED_PORT=" + actualPort);
        }
    }
}
```

Đây là **phương án thay thế**, không cần đồng thời dùng cả hai listener trong ứng dụng ví dụ trừ khi muốn in hai dòng. Để chạy riêng phương án này, lưu file `PortObserver.java` cùng package và bỏ method `logApplicationPort()` khỏi `WebPortApplication`.

Trong cấu hình event multicaster mặc định của Spring, callback thường chạy đồng bộ trên thread phát sự kiện. Không thực hiện network call kéo dài, vòng lặp chờ hoặc tác vụ blocking nặng trong listener vì có thể làm chậm startup. Cơ chế asynchronous listener/multicaster có thể đổi hành vi thread nhưng cần được cấu hình có chủ đích.

## 6. Ba cách đọc port và thời điểm tương ứng

### 6.1. Đọc từ property `server.port`

Ví dụ một bean dùng:

```java
@Value("${server.port:8080}")
private int configuredPort;
```

Với `server.port=0`, biến này bằng **0**, không phải cổng thực tế. Với giá trị cố định 8080, bean biết giá trị mong muốn nhưng không chứng minh việc bind thành công. Đọc property phù hợp khi cần biết cấu hình, không phù hợp để khám phá cổng ngẫu nhiên sau khởi động.

### 6.2. Đọc từ `WebServerApplicationContext` sau `SpringApplication.run`

Sau khi gọi `SpringApplication.run`, code sở hữu context cũng có thể truy vấn server:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

// Thay cho nội dung main() của ví dụ:
ConfigurableApplicationContext context =
        SpringApplication.run(WebPortApplication.class, args);

if (context instanceof WebServerApplicationContext webContext) {
    int port = webContext.getWebServer().getPort();
    System.out.println("PORT_AFTER_RUN=" + port);
}
```

Đây là **mảnh code minh họa đặt bên trong `main`**, không phải file Java độc lập. Nó dùng được vì `run` đã trả về khi quá trình khởi động hoàn tất. Nếu muốn một callback ở thời điểm web server vừa sẵn sàng, listener `WebServerInitializedEvent` thể hiện đúng ý đồ hơn. Không gọi `getWebServer().getPort()` khi bean mới được tạo mà chưa biết server đã tồn tại, vì `getWebServer()` có thể chưa trả về một server.

### 6.3. Trong integration test: dùng `@LocalServerPort`

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot cung cấp annotation chuyên dụng để inject cổng thực tế vào **bài test**:

```java
package com.example.webport;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebPortApplicationTests {

    @LocalServerPort
    int port;

    @Test
    void serverUsesAnAssignedPort() {
        assertTrue(port > 0);
    }
}
```

Lưu file ở `src/test/java/com/example/webport/WebPortApplicationTests.java`. Chạy `gradle test` hoặc lệnh tương ứng qua Gradle Wrapper. Test khởi động server HTTP thật trên cổng được hệ điều hành cấp và xác nhận cổng dương.

**Lưu ý:** import của Boot 3.3 là `org.springframework.boot.test.web.server.LocalServerPort`. Annotation này liên quan property `local.server.port`, chỉ sẵn sàng **sau** khi server được khởi tạo. Không tiêm `@LocalServerPort` hoặc `@Value("${local.server.port}")` vào bean ứng dụng thông thường lúc khởi tạo bean; thời điểm đó property có thể chưa tồn tại. Dùng event listener cho code runtime, dùng `@LocalServerPort` cho test có server thật.

`@SpringBootTest(webEnvironment = MOCK)` không khởi động server network và do đó không có cổng thật để inject.

## 7. Dùng port thực tế: việc gì hợp lý và việc gì dễ gây nhầm?

Một số ứng dụng thực tế:

1. **Ghi log/debug:** hiển thị cổng đang nghe của instance ở môi trường local/dev khi dùng `server.port=0`.
2. **Integration test:** xây dựng base URL nội bộ từ cổng runtime của từng lần test; tránh hardcode 8080 và xung đột cổng.
3. **Service discovery nội bộ có kiểm soát:** đăng ký endpoint server đang nghe sau khi nó khởi tạo, đồng thời bảo đảm unregister/health/lifecycle được thiết kế đúng.
4. **Nhiều web server/context:** phân biệt cổng chính với cổng Actuator management để gửi request tới đúng endpoint.

Những giới hạn:

- **Cổng web server ≠ địa chỉ công khai.** Ví dụ trong Docker, app lắng nghe cổng 8080 bên trong container nhưng host ánh xạ `9090:8080`; `getPort()` vẫn nói 8080. Trong Kubernetes, Service/Ingress có thể công bố địa chỉ/cổng hoàn toàn khác.
- **Có port ≠ sẵn sàng nghiệp vụ.** Nếu mục tiêu là nhận traffic sau khi tất cả bước startup hoàn tất, cần dùng readiness/health checks và lifecycle phù hợp, có thể kết hợp `ApplicationReadyEvent`.
- **`server.port=-1` khác `server.port=0`.** Số 0 yêu cầu chọn cổng để chạy server; -1 là cách vô hiệu HTTP endpoints dù vẫn có web application context. Không suy diễn có cổng HTTP có thể truy cập ở cấu hình -1.
- **Server có thể bind vào interface cụ thể:** `server.address` hoặc chính sách network quyết định từ đâu kết nối được; chỉ biết cổng là chưa đủ để kết luận remote client truy cập thành công.
- **Nếu server fail bind**, không có cổng hoạt động để event cung cấp; cần giải quyết lỗi startup trước.

## 8. Khi có Actuator management server ở cổng riêng

Nếu thêm `spring-boot-starter-actuator` và cấu hình management server tách khỏi app server, có thể có **nhiều `WebServerInitializedEvent`** tương ứng với các context/server khác nhau. Ví dụ:

```properties
server.port=0
management.server.port=0
```

Khi chạy trong môi trường hỗ trợ hai server riêng, hệ điều hành có thể cấp **hai cổng khác nhau**. Nếu listener chỉ ghi biến `lastPort` sau mỗi event, biến có thể chứa nhầm cổng management thay vì cổng nghiệp vụ.

Spring Boot có `getServerNamespace()` để phân biệt. Theo convention thường gặp của Boot, namespace của app server chính là `null`, còn management server riêng là `management`. Có thể quan sát:

```java
@EventListener
void observe(WebServerInitializedEvent event) {
    String namespace = event.getApplicationContext().getServerNamespace();
    int port = event.getWebServer().getPort();

    if (namespace == null) {
        System.out.println("APP_PORT=" + port);
    } else if ("management".equals(namespace)) {
        System.out.println("MANAGEMENT_PORT=" + port);
    } else {
        System.out.println("OTHER_PORT[" + namespace + "]=" + port);
    }
}
```

Đây là **method rút gọn**, cần đặt trong Spring bean (ví dụ `@Component`), không phải chương trình độc lập. Nếu chỉ cần app port trong một ứng dụng Boot thông thường, điều kiện namespace `null` của ví dụ chạy được là đủ. Nếu tự tạo các context/server có namespace tùy biến, hãy đối chiếu `event.getApplicationContext()` với context mong muốn thay vì giả định mọi event không phải management đều là app server.

Không phải ứng dụng dùng Actuator nào cũng tạo server riêng. Khi `management.server.port` không tách khỏi `server.port`, Actuator thường dùng chung cổng với endpoint ứng dụng.

## 9. Với WebFlux có dùng event này được không?

Có. `WebServerInitializedEvent` là base class chung, WebFlux có thể phát `ReactiveWebServerInitializedEvent` từ embedded reactive web server (phổ biến là Reactor Netty). Listener dùng `WebServerInitializedEvent` và `getWebServer().getPort()` vẫn phù hợp. Không cần cast sang `ServletWebServerInitializedEvent` nếu code cần áp dụng cho cả MVC lẫn WebFlux.

Dù cả hai stack có thể dùng annotation `@RestController`, chúng khác pipeline HTTP và execution model; sự khác biệt này không làm thay đổi ý nghĩa **lấy cổng đã bind từ web server trong event**. Lưu ý nếu classpath có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường ưu tiên web application kiểu Servlet theo mặc định.

## 10. Các lỗi hay gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân/cách kiểm tra |
|---|---|
| `server.port=0` nhưng code đọc được 0 | Đang đọc cấu hình, không đọc `event.getWebServer().getPort()` |
| Listener không được gọi | Chưa đăng ký `@Bean`/`@Component` đúng package scan, không chạy web server, hoặc startup thất bại |
| Log port xuất hiện hai lần | Có hai listener cùng mục đích hoặc nhiều web server/context; kiểm tra namespace |
| Test `@LocalServerPort` không nhận cổng | Có dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và đúng import không? Test có thực sự mở web server không? |
| Inject port vào constructor/`@PostConstruct` lỗi | Thời điểm bean khởi tạo có thể trước server bind; chuyển sang `WebServerInitializedEvent` |
| Có cổng nhưng `curl` thất bại | Kiểm tra HTTP/HTTPS, host/interface, port được in, container port mapping, proxy, firewall và thời điểm startup |
| Cố định port 8080 bị báo đã dùng | Có process khác đang lắng nghe; chọn cổng khác, giải phóng port hoặc dùng `server.port=0` cho test/dev |

## 11. Tự kiểm tra kiến thức

**Câu 1:** `server.port=0` thì số 0 có phải cổng HTTP cuối cùng không?  
**Đáp án:** Không. Số 0 là yêu cầu chọn cổng khả dụng; số cổng cuối cùng đọc từ `WebServerInitializedEvent.getWebServer().getPort()`.

**Câu 2:** Event này có đồng nghĩa với `ApplicationReadyEvent` không?  
**Đáp án:** Không. Một sự kiện báo web server đã khởi tạo, sự kiện còn lại báo SpringApplication hoàn thành các bước startup/runners theo vòng đời bình thường. Cả hai không thay thế health/readiness checks.

**Câu 3:** Khi có management server riêng, vì sao cần xét `getServerNamespace()`?  
**Đáp án:** Để không nhầm cổng server chính với cổng quản trị của Actuator hoặc server thuộc context khác.

**Câu 4:** Đọc `server.port` trong bean có thay thế event được không?  
**Đáp án:** Không khi cần cổng thực tế, nhất là `server.port=0`; property chỉ thể hiện cấu hình.

**Câu 5:** `@LocalServerPort` phù hợp nhất ở đâu?  
**Đáp án:** Trong integration test Spring Boot mở web server thật, chẳng hạn `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

## 12. Đọc thêm tài liệu chính thức

- Spring Boot 3.3.13, *Embedded Web Servers*, mục *Use a Random Unassigned HTTP Port* và *Discover the HTTP Port at Runtime*: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 API, `WebServerApplicationContext` và `getServerNamespace()`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html
- Spring Boot API, `WebServerInitializedEvent`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html

**Ghi nhớ:** cấu hình `server.port` cho biết **port muốn dùng**; `WebServerInitializedEvent` cho phép biết **port đã bind thật** ở thời điểm web server sẵn sàng. Khi có nhiều server hoặc proxy, phải phân biệt đúng context và cổng nội bộ/công khai.