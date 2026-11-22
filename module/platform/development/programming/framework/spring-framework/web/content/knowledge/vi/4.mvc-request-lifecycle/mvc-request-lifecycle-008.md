# Vòng đời controller singleton và nguy cơ dùng trạng thái chia sẻ trong Spring Web MVC

## 1. Mục tiêu học tập

Trong Spring Web MVC, một `@RestController` thông thường **là Spring bean có scope `singleton`**. Nhiều HTTP request có thể gọi **cùng một instance controller** đồng thời. Đây là một đặc điểm quan trọng của luồng xử lý MVC: Spring không tạo một controller Java mới cho mỗi request chỉ vì nhiều client đang truy cập endpoint.

Sau bài này, bạn có thể:

- Mô tả controller được tạo, khởi tạo, sử dụng và hủy trong vòng đời Spring `ApplicationContext`.
- Phân biệt `singleton` của Spring với singleton GoF, đối tượng "một instance trên toàn JVM" và khái niệm "mỗi request một controller".
- Chỉ ra vì sao biến local trong handler khác về tính chia sẻ so với mutable instance field, static field hoặc mutable dependency.
- Tái hiện một race condition khiến dữ liệu request A xuất hiện trong response của request B.
- Thiết kế controller stateless và chuyển trạng thái đúng nơi: request, session, database hay thành phần đồng bộ phù hợp.
- Phân biệt `@RequestScope`, `@SessionScope`, `prototype`, scoped proxy, `ThreadLocal` và primitive thread-safe.
- Kiểm thử hành vi singleton, request independence và rủi ro concurrency bằng Java 17+ và Spring MVC.

**Thông điệp chính:** `singleton` chỉ xác định **số lượng và phạm vi tồn tại của instance**. Nó **không tự bảo đảm thread safety**. Cách an toàn mặc định là viết controller ít trạng thái, giữ dữ liệu từng request trong tham số/biến local và sử dụng collaborator có hợp đồng concurrency phù hợp.

## 2. Controller trong Spring MVC được tạo như thế nào?

Một lớp được đánh dấu `@Controller` hoặc `@RestController` là ứng viên Spring component. Khi component scanning hoặc cấu hình explicit đăng ký bean definition, Spring container tạo và quản lý instance theo scope của bean.

Ví dụ:

```java
package com.example.lifecycle.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

Lớp này mặc định dùng **`singleton` scope**, tương tự việc khai báo `@Scope("singleton")` một cách tường minh. Trong một Spring `ApplicationContext`, Spring giữ lại một instance cho **bean definition** của controller và tái sử dụng nó. Cùng một class vẫn có thể xuất hiện trong nhiều bean definitions/contexts khác nhau; "singleton" của Spring có nghĩa **theo container và theo bean**, không phải một object duy nhất trên toàn JVM.

### Vòng đời thông thường

```text
Ứng dụng khởi động
    |
    v
Tạo ApplicationContext và đăng ký bean definitions
    |
    v
Tạo singleton controller (eager theo mặc định, trừ lazy/điều kiện riêng)
    |
    v
Resolve và inject dependencies (constructor, ...)
    |
    v
Bean lifecycle: post-processors, @PostConstruct và callbacks liên quan
    |
    v
Context sẵn sàng nhận request
    |
    +-- HTTP request A --> HandlerMapping/HandlerAdapter --> controller INSTANCE X
    |
    +-- HTTP request B --> HandlerMapping/HandlerAdapter --> controller INSTANCE X
    |
    +-- HTTP request C --> HandlerMapping/HandlerAdapter --> controller INSTANCE X
    |
    v
ApplicationContext đóng
    |
    v
Destroy callbacks của singleton (nếu có), giải phóng tài nguyên quản lý
```

Chi tiết startup có thể thay đổi do lazy initialization, proxy, bean post-processor hoặc context hierarchy. **Không** diễn giải sơ đồ thành "mọi bean đều có `@PostConstruct`" hoặc "mọi bean được tạo tại đúng một thời điểm tuyệt đối". Với controller singleton chuẩn, điều cốt lõi là instance sống qua nhiều request và thường lâu ngang vòng đời context.

`@PostConstruct` chạy ở thời điểm bean initialization, **không chạy cho mỗi HTTP request**. `@PreDestroy` hoặc destruction callback của bean singleton thường liên quan context shutdown, **không chạy khi controller xử lý xong một request**.

### Vì sao Spring MVC dùng chung controller?

Trong Spring MVC, Servlet container điều phối request đến `DispatcherServlet`. `HandlerMapping` chọn handler đã đăng ký; `HandlerAdapter` gọi phương thức tương ứng trên controller bean hiện hữu. Spring container không "new" controller mỗi lần khi handler method được chọn. Nhiều request đồng thời có thể được các servlet threads khác nhau xử lý và gọi cùng một method trên một object:

```text
Request A (thread T1):  controllerInstance.getUser("A")
                                 |
                                 +--> cùng một object
                                 |
Request B (thread T2):  controllerInstance.getUser("B")
```

Thread ở đây chỉ là mô hình trực quan. Với async processing, request có thể đi qua nhiều dispatch hoặc executor khác nhau. Điều quan trọng là **nhiều luồng thực thi có thể truy cập cùng field của object controller**.

## 3. Phân biệt dữ liệu local, field và dữ liệu dùng chung

```java
@RestController
class ExampleController {

    private final GreetingService service;        // một reference của bean
    private String lastName;                       // mutable instance field
    private static long globalCounter;             // static mutable field

    ExampleController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/api/example")
    String example(@RequestParam String name) {
        String normalized = name.trim();          // local variable
        lastName = normalized;                     // shared state!
        globalCounter++;                           // shared state + race!
        return service.greet(normalized);
    }
}
```

Đây là **đoạn minh họa**: cần imports tương ứng và bean `GreetingService` mới biên dịch trong project Spring. Không nên copy ví dụ này làm production controller.

| Loại dữ liệu | Nơi tồn tại | Nguy cơ khi nhiều request cùng truy cập |
|---|---|---|
| Tham số handler, ví dụ `name` | Mỗi lần phương thức được gọi | Không phải field dùng chung; vẫn có thể trỏ đến mutable object khác. |
| Biến local, ví dụ `normalized` | Mỗi lần gọi phương thức | Không chia sẻ riêng biến local giữa các lần gọi; chỉ trở nên nguy hiểm nếu reference của nó thoát ra môi trường dùng chung. |
| `final` instance field trỏ đến service | Cùng controller singleton | Reference không thể gán lại; bản thân service/object được trỏ đến vẫn có thể mutable và cần thread-safe. |
| Mutable instance field, ví dụ `lastName` | Cùng instance controller | Request khác có thể ghi đè, đọc thấy dữ liệu của nhau hoặc gây data race. |
| `static` field, ví dụ `globalCounter` | Gắn với class/ClassLoader trong JVM | Có thể dùng chung xuyên các controller instances; không trở thành an toàn chỉ vì đổi scope controller. |
| Mutable state trong injected singleton service | Trong service singleton | Rủi ro tương tự, chỉ được chuyển từ controller sang service. |
| Request-scoped bean | Một HTTP request scope hợp lệ | Cách ly giữa các request khác nhau; **không** mặc nhiên bảo vệ nếu nhiều thread bên trong cùng request cùng truy cập object đó. |
| Session-scoped bean | Một HTTP session scope | Nhiều request của **cùng một session** vẫn có thể chạy đồng thời và đụng state. |

Khi controller chỉ gọi các pure/stateless methods và dùng dữ liệu local, việc nhiều thread sử dụng cùng instance **thường an toàn**, vì object không lưu trạng thái riêng của request. Nhưng controller stateless vẫn có thể gọi service, cache hoặc database mà giao thức cập nhật dữ liệu không an toàn; luôn đánh giá toàn bộ chuỗi phụ thuộc.

## 4. Race condition điển hình: một request ghi đè tên của request khác

Xét controller sai:

```java
package com.example.lifecycle.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnsafeGreetingController {

    private String currentName;

    @GetMapping("/api/unsafe")
    public String greet(@RequestParam(name = "name") String name) {
        currentName = name;
        // Một request khác có thể ghi đè currentName tại đây.
        return "Xin chào, " + currentName;
    }
}
```

Với hai request gần nhau, interleaving **có thể** là:

```text
Thread A                             Thread B
----------------------------------   ----------------------------------
GET /api/unsafe?name=An              GET /api/unsafe?name=Bình
currentName = "An"
                                     currentName = "Bình"
return "Xin chào, " + currentName
-> có thể trả "Xin chào, Bình"!
                                     return "Xin chào, Bình"
```

Đây là một lịch chạy có thể xảy ra, không phải kết quả bắt buộc của mọi lần thử HTTP. Lỗi có thể chỉ xuất hiện khi tải cao và rất khó tái hiện bằng gọi URL lần lượt. Ngoài interleaving, field không có cơ chế đồng bộ còn có vấn đề memory visibility theo Java Memory Model: các thread có thể không thấy thay đổi của nhau theo thời điểm mà lập trình viên tưởng tượng.

**Hệ quả nghiệp vụ có thể nghiêm trọng**: nếu lưu `currentUserId`, `tenantId`, `cart`, `accessToken`, `searchCriteria` hay dữ liệu trả về theo user trong field singleton, request của người này có thể dùng nhầm dữ liệu của người khác. Đây là vấn đề data isolation, không chỉ là số đếm bị sai.

### Vì sao `volatile` không phải cách sửa chung?

Đổi thành:

```java
private volatile String currentName;
```

chỉ thêm một số bảo đảm visibility và ordering cho các thao tác read/write trên field. Nó **không** gắn một giá trị với request đã sinh ra giá trị đó. Request A vẫn có thể đọc giá trị B vừa ghi. Ngược lại, `counter++` là chuỗi read–modify–write, nên thêm `volatile` vào counter **không** khiến increment trở thành atomic.

Vấn đề đúng cần giải là: **không đặt dữ liệu riêng của request vào object shared**.

## 5. Thí nghiệm Java 17+: tái hiện lỗi một cách có kiểm soát

Bạn không cần khởi động server để chứng minh bản chất lỗi. File Java độc lập sau dùng hai thread, một instance service chung và `CyclicBarrier` để buộc hai lời gọi cùng ghi state trước khi đọc. Dùng `volatile` ở đây để kết quả hiển thị nhất quán về visibility; `volatile` vẫn không sửa lỗi trộn request.

Tệp `SharedStateRace.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedStateRace {

    static final class UnsafeGreeter {
        private volatile String currentName;
        private final CyclicBarrier bothWritten = new CyclicBarrier(2);

        String greet(String name)
                throws InterruptedException, BrokenBarrierException {
            currentName = name;
            bothWritten.await();
            return currentName;
        }
    }

    public static void main(String[] args) throws Exception {
        UnsafeGreeter greeter = new UnsafeGreeter();

        try (ExecutorService pool = Executors.newFixedThreadPool(2)) {
            Future<String> first = pool.submit(() -> greeter.greet("An"));
            Future<String> second = pool.submit(() -> greeter.greet("Bình"));

            String a = first.get();
            String b = second.get();

            System.out.println("Same response: " + a.equals(b));
            System.out.println("Exactly one correct: "
                    + (a.equals("An") != b.equals("Bình")));
        }
    }
}
```

**Chú ý:** `ExecutorService` triển khai `AutoCloseable` từ Java 19; đoạn `try (ExecutorService ...)` cần **Java 19+**, nên để chạy chính xác trên Java 17 như mục tiêu bài, hãy dùng phiên bản bên dưới, gọi `shutdown()` trong `finally`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedStateRace {

    static final class UnsafeGreeter {
        private volatile String currentName;
        private final CyclicBarrier bothWritten = new CyclicBarrier(2);

        String greet(String name)
                throws InterruptedException, BrokenBarrierException {
            currentName = name;
            bothWritten.await();
            return currentName;
        }
    }

    public static void main(String[] args) throws Exception {
        UnsafeGreeter greeter = new UnsafeGreeter();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<String> first = pool.submit(() -> greeter.greet("An"));
            Future<String> second = pool.submit(() -> greeter.greet("Bình"));

            String a = first.get();
            String b = second.get();

            System.out.println("Same response: " + a.equals(b));
            System.out.println("Exactly one correct: "
                    + (a.equals("An") != b.equals("Bình")));
        } finally {
            pool.shutdown();
        }
    }
}
```

Tạo file chỉ với **khối mã thứ hai** (bản tương thích Java 17), lưu UTF-8. Chạy:

```bash
javac -encoding UTF-8 SharedStateRace.java
java SharedStateRace
```

Stdout:

```text
Same response: true
Exactly one correct: true
```

Giải thích: mỗi thread ghi tên riêng rồi chờ cả hai thread tới barrier. Sau barrier, cả hai đọc **cùng một field đã bị lần ghi cuối cùng quyết định**. Giá trị cuối có thể là `An` hoặc `Bình`, nhưng hai response giống nhau nên chính xác một trong hai request bị gắn sai tên. Barrier trong thí nghiệm có mục đích tạo interleaving xác định; **đừng đưa barrier vào controller production** để "đồng bộ request".

Sửa logic bằng cách bỏ mutable shared field:

```java
static final class SafeGreeter {
    String greet(String name) {
        String normalized = name.trim();
        return normalized;
    }
}
```

Mỗi lần gọi có `name`/`normalized` riêng. Không cần `volatile`, `synchronized` hay lock để bảo vệ state không tồn tại.

## 6. Spring Web MVC chạy được: thiết kế controller stateless

Phần này tạo ứng dụng Spring Boot 3.5.x + Spring MVC, dùng Java 17, Gradle 8.5. Ví dụ chọn phiên bản cụ thể **Spring Boot 3.5.16**; trong sản phẩm đang triển khai, tuân thủ BOM và đường nâng cấp phiên bản được hỗ trợ. Với Spring Boot 3.5, starter web theo Servlet stack vẫn là `spring-boot-starter-web`.

### 6.1. Cấu trúc project

```text
controller-lifecycle-demo/
├── settings.gradle
├── build.gradle
├── gradlew                      # nếu tạo với Gradle Wrapper/Initializr
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/lifecycle/
    │   │   ├── LifecycleApplication.java
    │   │   ├── service/GreetingService.java
    │   │   └── web/GreetingController.java
    │   └── resources/application.properties
    └── test/java/com/example/lifecycle/
        └── GreetingControllerTest.java
```

Bạn có thể tạo project qua https://start.spring.io với Gradle/Groovy, Java 17 và dependency **Spring Web**, hoặc tạo tệp thủ công rồi generate Gradle Wrapper. Những file `gradlew` và `gradle/wrapper/*` phải do wrapper hoặc Initializr tạo; đừng tạo file `gradle-wrapper.jar` giả.

`settings.gradle`:

```groovy
rootProject.name = 'controller-lifecycle-demo'
```

`build.gradle`:

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý phiên bản Spring Framework, Jackson và phần lớn dependency liên quan; đừng tự chọn version `spring-webmvc` khác một cách tùy tiện. `spring-boot-starter-test` mang thư viện JUnit và Spring Test thường dùng để kiểm chứng handler.

### 6.2. Khởi động ứng dụng

`src/main/java/com/example/lifecycle/LifecycleApplication.java`:

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
```

Đặt `@SpringBootApplication` tại package cha `com.example.lifecycle` để component scan phát hiện service/controller bên dưới. Spring Boot tự cấu hình embedded Servlet container và `DispatcherServlet` khi starter web phù hợp có mặt.

`src/main/resources/application.properties`:

```properties
spring.application.name=controller-lifecycle-demo
server.port=8080
```

### 6.3. Stateless service

`src/main/java/com/example/lifecycle/service/GreetingService.java`:

```java
package com.example.lifecycle.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        String normalized = name.trim();
        return "Xin chào, " + normalized + "!";
    }
}
```

`@Service` mặc định cũng là singleton bean. Service này **an toàn cho concurrent calls theo logic đang trình bày** vì không ghi hay đọc mutable state dùng chung. Các local variables của mỗi lời gọi phương thức không dùng chung với lời gọi khác.

Nếu một ngày thêm `private String lastName;` vào service để "lưu tạm", bạn chỉ đang **dời race condition từ controller sang service**. Stateless cần được kiểm tra cả chuỗi collaborator.

### 6.4. Controller singleton đúng cách

`src/main/java/com/example/lifecycle/web/GreetingController.java`:

```java
package com.example.lifecycle.web;

import java.util.Map;
import com.example.lifecycle.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/api/greeting")
    public Map<String, String> greeting(
            @RequestParam(name = "name", defaultValue = "bạn") String name) {

        String message = greetingService.greet(name);
        return Map.of("message", message);
    }
}
```

Trong ví dụ này:

- Spring tạo một `GreetingController` singleton thông thường.
- Constructor injection gắn collaborator cần thiết; `private final` ngăn gán lại reference sau construction.
- `name`, `message` và `Map.of(...)` đều được tạo/sử dụng trong lần gọi handler hiện tại. `Map.of` trả immutable map nên không gây thêm mutable state bị chia sẻ từ phần controller.
- Không có `lastName` hoặc `currentUser` làm instance field. Hai request đồng thời gọi cùng bean nhưng mỗi request tính response từ input riêng.
- `GreetingService` cũng singleton, vẫn ổn vì không lưu dữ liệu request vào field.

**Lưu ý:** `final GreetingService greetingService` bảo vệ reference, **không tự làm cho service thread-safe**. Nếu service chứa mutable `HashMap`, list, cache không đồng bộ hoặc object thay đổi dưới nhiều thread thì vẫn cần thiết kế lại.

### 6.5. Chạy và quan sát response

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat bootRun
```

Trên Linux/macOS:

```bash
./gradlew clean test
./gradlew bootRun
```

Ở terminal thứ hai, gửi request:

```bash
curl -i "http://localhost:8080/api/greeting?name=An"
curl -i "http://localhost:8080/api/greeting?name=Binh"
curl -i "http://localhost:8080/api/greeting"
```

Các body JSON tương ứng:

```json
{"message":"Xin chào, An!"}
```

```json
{"message":"Xin chào, Binh!"}
```

```json
{"message":"Xin chào, bạn!"}
```

Status mong đợi là HTTP 200, cùng JSON `Content-Type` do message converter tạo. Header đầy đủ, thứ tự header và log startup phụ thuộc môi trường; ví dụ chỉ cam kết nội dung được code tạo ra.

## 7. Kiểm thử singleton identity và request independence

File `src/test/java/com/example/lifecycle/GreetingControllerTest.java`:

```java
package com.example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.lifecycle.web.GreetingController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    MockMvc mvc;

    @Test
    void controllerIsSameSingletonBeanInThisContext() {
        GreetingController first = context.getBean(GreetingController.class);
        GreetingController second = context.getBean(GreetingController.class);
        assertSame(first, second);
    }

    @Test
    void independentRequestsProduceIndependentResponses() throws Exception {
        mvc.perform(get("/api/greeting").param("name", "An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, An!"));

        mvc.perform(get("/api/greeting").param("name", "Binh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, Binh!"));

        mvc.perform(get("/api/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, bạn!"));
    }
}
```

Điểm kiểm chứng:
- `assertSame` chứng minh hai lần lấy **cùng bean definition trong cùng context** trả cùng một reference. Nó không chứng minh trong toàn JVM chỉ có một instance.
- MockMvc kiểm chứng mapping, binding và JSON theo ứng dụng Spring MVC.
- Các MockMvc request ở đây chạy **tuần tự**, nên **chưa chứng minh** một controller không bao giờ có bug concurrency. Phần mã nguồn stateless và thí nghiệm `SharedStateRace` mới giải thích bản chất việc không dùng shared request state.
- Một integration test chạy HTTP concurrent trên server thật có thể phát hiện một số race, nhưng không thể chứng minh tuyệt đối mọi lịch xen kẽ đều an toàn. Đánh giá thiết kế/ownership của mutable state vẫn là quan trọng.

## 8. Quy tắc thiết kế an toàn: state thuộc đâu?

Khi cần lưu dữ liệu, trước tiên xác định **lifecycle và owner** của dữ liệu, rồi chọn nơi lưu phù hợp:

| Loại dữ liệu | Nơi nên để | Ví dụ |
|---|---|---|
| Chỉ dùng trong một lời gọi handler | Tham số/biến local, DTO | `name`, `orderId`, `validatedInput` |
| Gắn với một HTTP request | Request attribute hoặc `@RequestScope` | Request correlation context, dữ liệu tính toán tạm |
| Dành cho một phiên truy cập | Session store / `@SessionScope` có kiểm soát | Wizard form state, tùy chọn giao diện |
| Dữ liệu nghiệp vụ bền vững | Database hoặc nguồn lưu trữ có transaction/consistency | Giỏ hàng bền vững, đơn hàng, số dư |
| Cache dùng chung | Cache API và chính sách đồng bộ/TTL thích hợp | Dữ liệu tham khảo có thể cache |
| Bộ đếm metrics cục bộ của một process | Metrics registry hoặc atomic/adder phù hợp | Số request xử lý trên một instance |
| Cấu hình bất biến | Immutable configuration object hoặc constructor-injected collaborator | Endpoint base URL, quy tắc định dạng |
| Dữ liệu gắn với người dùng đang xác thực | Request/security context được framework quản lý | Principal/authorities cho request hiện tại |

Bảo mật dữ liệu yêu cầu **xác định quyền trên từng request/operation**, không lưu user hiện tại trong `static` hoặc singleton field. Một instance ứng dụng có thể phục vụ nhiều users/tenants đồng thời.

### `@RequestScope` khi thật sự cần đối tượng theo request

Có lúc nhiều thành phần trong cùng một request cần chung một object tạm. Khi đó dùng `@RequestScope`:

```java
package com.example.lifecycle.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMarker {

    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

Controller singleton có thể inject bean này:

```java
package com.example.lifecycle.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RequestMarkerController {

    private final RequestMarker marker;

    public RequestMarkerController(RequestMarker marker) {
        this.marker = marker;
    }

    @GetMapping("/api/marker")
    public Map<String, String> marker() {
        return Map.of("requestId", marker.id());
    }
}
```

Hai file Java trên là **phần mở rộng độc lập**, đặt cùng source tree của project ở mục 6; không cần thêm thư viện ngoài starter web. `@RequestScope` là shortcut cho request scope và **mặc định sử dụng class-based scoped proxy**. Singleton `RequestMarkerController` giữ một proxy ổn định; tại mỗi request, lời gọi `marker.id()` được chuyển tới **target `RequestMarker` của request hiện tại**. Như vậy constructor injection của singleton không phải tạo request object tại startup.

Khi gọi `/api/marker` hai lần, giá trị UUID trong response **thường khác** do mỗi request có instance marker riêng. UUID là dữ liệu ngẫu nhiên nên không thể ghi stdout chính xác cố định; test tốt có thể kiểm tra id hợp lệ và khác nhau giữa hai request, nếu muốn. Một request có thể gọi `marker.id()` nhiều lần và nhận cùng id vì nó dùng cùng target bean.

**Không cần tự tạo request-scoped controller** cho endpoint CRUD thông thường: request-local variables đủ cho nhiều trường hợp, ít overhead và đơn giản hơn. `@RequestScope` hữu ích khi thật sự cần một collaborator có identity/state theo request.

### `@SessionScope` không tự làm state thread-safe

`@SessionScope` có một instance cho mỗi HTTP session, nhưng **hai request của cùng người dùng** (hai tab trình duyệt, AJAX calls song song) vẫn có thể dùng cùng session bean đồng thời.

Ví dụ:

```java
@Component
@SessionScope
public class WizardState {

    private int step;

    public int advance() {
        return ++step;
    }
}
```

Đây là snippet để phân tích, không phải khuyến nghị dùng cho sản phẩm. `++step` không atomic. Nếu hai request trong cùng session cùng gọi `advance()`, có thể mất một lần tăng. Cần thiết kế cập nhật có đồng bộ hoặc mô hình lưu trữ/trạng thái phù hợp; với hệ thống multi-instance, phải cân nhắc session replication, serialization và lưu trữ tập trung. Hơn nữa, session bean không mặc định là cache toàn cục cho tất cả người dùng.

### `prototype` có phải giải pháp cho controller?

`@Scope("prototype")` yêu cầu Spring tạo object mới mỗi lần container **được yêu cầu lấy bean prototype**, không có nghĩa tự động có một instance mới cho **mỗi HTTP request** trong cơ chế MVC thông thường. Nếu inject prototype vào singleton tại thời điểm khởi tạo, singleton có thể giữ cùng một prototype instance suốt vòng đời của nó. Vì vậy **đừng biến controller sang prototype chỉ để chữa shared request data**. Hãy thiết kế stateless hoặc sử dụng request scope đúng mục đích.

Nếu một singleton cần tạo các object stateful mới cho từng thao tác, có thể dùng `ObjectProvider<T>.getObject()` hoặc factory rõ ràng để cấp một prototype mới **mỗi lần gọi**. Đây là cơ chế lookup bean, không là cơ chế tự động biến prototype thành request-scoped.

## 9. Các biện pháp đồng bộ: biết đúng giới hạn

Có trường hợp state **thực sự thuộc process** và cần shared, ví dụ một metrics counter. Khi đó concurrency primitive có ích, nhưng không nên dùng chúng để vá nhầm đời sống của dữ liệu user.

### `AtomicInteger` và phép tăng số đếm

Sai:

```java
private int count;

public int next() {
    return ++count;
}
```

Hai thread có thể đọc cùng giá trị cũ và mất update. Nếu đây là số đếm **cục bộ cho một instance JVM**:

```java
import java.util.concurrent.atomic.AtomicInteger;

private final AtomicInteger count = new AtomicInteger();

public int next() {
    return count.incrementAndGet();
}
```

`incrementAndGet()` thực hiện tăng atomic trên một `AtomicInteger`. Nhưng counter vẫn chỉ thuộc process; khi chạy 3 replicas hoặc restart, các process có state riêng, không tạo ra chuỗi số ID toàn hệ thống bền vững. Với business IDs hay tiền/tồn kho, dùng database sequence, atomic update, transaction hoặc cơ chế consistency được thiết kế phù hợp.

### `synchronized` / lock

`synchronized` có thể đảm bảo mutual exclusion của một critical section trong **cùng JVM/monitor**. Nhưng:

- Đồng bộ toàn bộ method handler làm nhiều request bị tuần tự hóa, giảm throughput.
- Nếu trả kết quả dựa trên field user global, việc tạo lock không tự làm lifecycle/semantics đúng.
- Lock trong một process không bảo vệ cùng business record khi ứng dụng chạy nhiều instances.
- Lock và state sharing phức tạp dễ gây deadlock, contention và lỗi khó kiểm thử.

**Ưu tiên loại bỏ request-specific state khỏi singleton**, thay vì dùng global lock.

### Concurrent collections và compound operations

`ConcurrentHashMap` giúp nhiều thao tác collection có contract thread-safe. Tuy nhiên chuỗi `containsKey` → `put` vẫn có thể có race ở cấp **nghiệp vụ**. Dùng atomic methods thích hợp như `computeIfAbsent` hoặc `merge` khi semantics yêu cầu; đánh giá function callback và side effects. Một collection thread-safe không tự đảm bảo "kiểm tra rồi cập nhật" trên nhiều resources/database transactions có tính atomic.

### Immutable objects

Một class có `final` fields trỏ tới immutable values (ví dụ `String`, `record` chứa immutable components) thường giúp tránh mutation ngoài ý muốn. Tuy nhiên:
- `final List<T>` chỉ khóa reference, **không** biến `ArrayList` thành immutable.
- Một `record` có field tham chiếu tới mutable object cũng không deep-immutable.
- Stateless controller có thể giữ immutable cấu hình và references đến services, repositories, clients miễn các collaborator được dùng phù hợp với concurrency contract.

## 10. Sai lầm liên quan request context và ThreadLocal

`ThreadLocal` có thể lưu context gắn với một thread, ví dụ correlation information trong logging. Nhưng servlet containers **tái sử dụng worker threads**; không cleanup sẽ để context request cũ rò sang request sau. Với async execution, xử lý có thể chuyển sang thread khác và `ThreadLocal` không tự đi theo request.

Một ví dụ chỉ mang tính minh họa:

```java
private static final ThreadLocal<String> CURRENT_ID = new ThreadLocal<>();

void process(String id) {
    CURRENT_ID.set(id);
    try {
        // xử lý đồng bộ trên thread hiện tại
    } finally {
        CURRENT_ID.remove();
    }
}
```

Đoạn này **không** tạo request-scope thực thụ, không thay thế `SecurityContext`/request attributes và không tự truyền state sang `@Async`, `CompletableFuture` hoặc asynchronous MVC dispatch. Nếu cần context cross-thread, hãy dùng cơ chế propagation được framework/thư viện quan sát/bảo mật cung cấp, với chính sách rõ ràng.

### HttpServletRequest, @RequestParam và Principal

Trong controller, nhận request data qua method parameters là cách trực tiếp:

```java
@GetMapping("/api/me")
public Map<String, String> whoAmI(java.security.Principal principal) {
    return Map.of("name", principal.getName());
}
```

Đây là snippet phụ thuộc việc security principal có mặt. Nếu không cấu hình authentication, `principal` có thể là `null` và ví dụ trên cần xử lý trường hợp đó. Ý ở đây là **đừng lưu principal của request vào field singleton**. Đối tượng được truyền vào handler hoặc lấy qua API security đúng thời điểm thuộc ngữ cảnh request; nó không nên được cache như "người dùng hiện tại" toàn ứng dụng.

## 11. Async controller và virtual threads có làm thay đổi kết luận không?

Không. Dù Servlet container sử dụng platform worker threads, async MVC executor, hoặc mô hình virtual threads trong một số cấu hình, singleton controller vẫn là một object **được nhiều luồng thực thi sử dụng**. Việc đổi loại thread không đổi scope bean.

Ví dụ controller trả `Callable<String>`:

```java
@GetMapping("/api/async-greeting")
public java.util.concurrent.Callable<String> asyncGreeting(
        @RequestParam(name = "name") String name) {

    return () -> "Xin chào, " + name + "!";
}
```

Đây là đoạn controller đặt bên trong `@RestController` hiện hữu. `name` là local/parameter đã được capture theo từng lời gọi, nên không cần field chung. Spring MVC có thể thực thi `Callable` qua configured async executor và thực hiện async dispatch hoàn tất response. Nếu lambda đọc/ghi một mutable field singleton thay vì capture input request, race vẫn tồn tại.

Với request-scoped beans và security/request contexts, async execution có quy tắc propagation/lifecycle riêng; không dựa vào `ThreadLocal` thủ công để suy luận bean luôn hiện diện trên mọi thread. Lập trình theo thread-safe state ownership vẫn là nền tảng.

## 12. Bảng kiểm tra nhanh trong code review

| Dấu hiệu trong controller/service | Câu hỏi cần đặt | Hướng xử lý thường phù hợp |
|---|---|---|
| `private String currentUser;` | Đây có phải giá trị thay đổi theo request/user? | Bỏ field; nhận làm tham số hoặc lấy từ request/security context. |
| `private Map<String, Cart> carts = new HashMap<>();` | Map có được nhiều request truy cập đồng thời, có cần bền vững/multi-node? | Thiết kế repository/store/cache với concurrency và ownership rõ. |
| `private final List<...> cache = new ArrayList<>();` | `final` chỉ khóa reference, list có đang bị mutate? | Dùng immutable snapshot hoặc cache thread-safe phù hợp. |
| `private int requestCount;` và `++requestCount` | Cần số đếm process hay hệ thống? | Metrics registry, atomic primitive hoặc backend counter đúng phạm vi. |
| `@Scope("prototype")` trên controller | Có kỳ vọng một instance mỗi request? | Xem lại semantics; ưu tiên controller stateless. |
| `@SessionScope` có nhiều field mutable | Cùng session có nhiều request song song? | Bảo vệ cập nhật/thiết kế session state rõ. |
| `ThreadLocal` nhưng không có `remove()` | Container có reuse thread? | Cleanup ở `finally` và xác định async propagation. |
| `synchronized` trên handler | Đang dùng lock để vá state đặt sai chỗ? | Di chuyển state đúng owner; nếu cần shared data, chọn atomic operation/transaction. |
| Inject singleton service có mutable field | Controller stateless nhưng service có an toàn không? | Rà soát toàn bộ dependency chain. |
| `static` mutable field | Dữ liệu có bị chia sẻ ngoài dự kiến qua class? | Tránh cho request/user state; cô lập hoặc quản lý rõ process-global state. |

## 13. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1: chỉ ra biến nguy hiểm

```java
@RestController
class CartController {

    private String cartId;
    private final CartService service;

    CartController(CartService service) {
        this.service = service;
    }

    @GetMapping("/api/cart")
    CartDto getCart(@RequestParam String id) {
        cartId = id;
        return service.load(cartId);
    }
}
```

Hãy xác định vì sao response có thể nhầm giỏ hàng khi có request A, B đồng thời. Viết lại handler thành `return service.load(id);` và xóa field `cartId`. Nếu `CartService` lưu `lastLoadedCart` làm mutable singleton field, bài toán vẫn chưa được giải quyết.

### Bài tập 2: thử scope

Thêm `RequestMarker` và `RequestMarkerController` ở mục 8 vào ứng dụng chạy. Gửi hai request `/api/marker`, quan sát UUID khác nhau giữa các request. Trong **một** handler, gọi `marker.id()` hai lần rồi so sánh; chúng dùng cùng request-scoped target khi cùng request còn hiệu lực.

### Bài tập 3: mô hình nhiều instances

Giả sử load balancer gửi requests tới hai ứng dụng độc lập A và B. Mỗi ứng dụng có singleton bean giữ `AtomicInteger counter`. Nếu client gọi `/counter` nhiều lần, counter có bảo đảm tăng toàn cục không? **Không**: A/B có object và giá trị khác nhau. Hãy nêu khi nào nên dùng shared database/metrics backend.

### Câu hỏi thường gặp

**1. Spring có tạo controller mới cho mỗi HTTP request không?**  
Mặc định không. `@RestController` là Spring bean singleton theo mỗi bean definition và context. Request mapping thường gọi cùng instance.

**2. Singleton bean có nghĩa controller không thread-safe?**  
Không mặc nhiên. Singleton stateless hoặc có shared state được quản lý đúng vẫn có thể thread-safe. Rủi ro xảy ra khi nhiều luồng truy cập mutable state mà không có ownership/đồng bộ phù hợp.

**3. Biến local `String name` trong handler có bị request khác ghi đè không?**  
Không theo cách một instance field bị ghi đè; mỗi invocation có local variables riêng. Nhưng một local reference trỏ tới object mutable được chia sẻ vẫn có thể gây race.

**4. Dùng `volatile` cho `currentUser` có an toàn không?**  
Không. Nó không tạo sự cách ly theo request; user A vẫn có thể đọc tên của user B.

**5. Dùng `@RequestScope` cho tất cả controllers có tốt hơn không?**  
Thường không cần. Controller stateless singleton là cấu trúc đơn giản và phù hợp. Chỉ dùng request scope khi thật sự cần object có vòng đời gắn với request.

**6. Inject `prototype` vào singleton có tạo object mới ở mỗi request không?**  
Không. Dependency thường được resolve lúc xây dựng singleton; cần factory/provider nếu muốn tạo prototype mỗi lần gọi.

**7. `@SessionScope` có tránh race giữa các requests cùng user không?**  
Không mặc nhiên. Hai request cùng session có thể đồng thời mutate một bean session-scoped.

**8. Có thể để mọi business state trong singleton service rồi chỉ làm controller stateless?**  
Không nên nếu business state riêng user/request vẫn bị chia sẻ. Hãy dùng local values, request/session scope khi phù hợp, persistence hoặc hệ thống state có thiết kế concurrency đúng.

## 14. Nguồn đọc thêm

- Spring Framework Reference — Bean Scopes, singleton/prototype/request/session, scoped proxies: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework Reference — Classpath Scanning and Managed Components, `@RequestScope` và `@SessionScope`: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework Reference — Spring MVC annotated controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html
- Spring Framework Reference — MVC asynchronous requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.5 — Web applications: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Java SE 17 — `java.util.concurrent`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
