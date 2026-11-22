# Gắn `BufferingApplicationStartup` vào `SpringApplication` — đo các bước khởi động Spring Boot 3.3

## 1. Mục tiêu

Một ứng dụng Spring Boot có thể mất vài giây hoặc hàng chục giây để bắt đầu phục vụ. Nhìn vào dòng log “Started … in … seconds” chỉ biết **thời gian tổng quát**, chưa chỉ ra chi tiết: bước nào dành thời gian để tạo bean, xử lý dependency, refresh `ApplicationContext`, khởi động web server hoặc thực hiện startup callbacks.

Spring Framework cung cấp hợp đồng **`ApplicationStartup`**. Spring Boot cung cấp implementation **`BufferingApplicationStartup`** để ghi lại các **`StartupStep`** vào một bộ đệm có dung lượng giới hạn, kèm thời điểm bắt đầu, kết thúc, thời lượng, tên bước và các tags liên quan.

**Đề bài trọng tâm:** phải tạo và **gắn `BufferingApplicationStartup` vào đối tượng `SpringApplication` trước khi gọi `run(args)`**. Đây là thời điểm quyết định vì các bước startup đầu tiên diễn ra trước khi application context và các bean ứng dụng được tạo xong.

Sau bài này bạn có thể:

1. Giải thích `ApplicationStartup`, `StartupStep`, `BufferingApplicationStartup` và `StartupTimeline`.
2. Cấu hình đúng `SpringApplication#setApplicationStartup(...)` trong Java 21 / Spring Boot 3.3.13.
3. Hiểu ý nghĩa `capacity`, khi đầy thì bước mới không còn được lưu, và cách dùng `addFilter(...)` để giảm lượng dữ liệu.
4. Đọc timeline bằng `getBufferedTimeline()` hoặc `drainBufferedTimeline()`.
5. Bổ sung Actuator để xem startup timeline qua **`GET /actuator/startup` (snapshot)** và **`POST /actuator/startup` (drain)**.
6. Hiểu quan hệ giữa bản ghi startup chi tiết, `ApplicationStartedEvent`, `ApplicationReadyEvent`, readiness và tổng thời gian khởi động.
7. Chạy một ứng dụng Maven hoàn chỉnh, test bằng JUnit mà không phụ thuộc thời lượng startup cụ thể.
8. Nhận diện lỗi cấu hình sai thời điểm, buffer bị đầy, endpoint bị 404, làm mất dữ liệu vì drain và rủi ro bảo mật.

Bài sử dụng **Java 21, Spring Boot 3.3.13, Maven và Spring Boot Actuator**. Phần ví dụ không yêu cầu database hoặc broker.

## 2. Vì sao cần đo startup theo bước?

Giả sử có hai lần khởi động:

```text
Lần A: Started Demo in 2.1 seconds
Lần B: Started Demo in 8.5 seconds
```

Chỉ nhìn thời gian tổng thì không biết sự khác biệt đến từ classpath scanning, tạo bean, database migration, external call trong `@PostConstruct` hay chờ executor trong `ApplicationRunner`.

Khi thu thập các bước startup, bạn có thể nhìn những tên kỹ thuật như:

```text
spring.boot.application.starting
spring.context.refresh
spring.beans.instantiate
```

Các tên trên là **ví dụ về loại step** trong quá trình startup, không phải cam kết rằng mọi ứng dụng/phiên bản đều sinh đúng tập tên và số lượng như nhau. Boot và Framework có thể thêm/bớt bước đo giữa các phiên bản, theo auto-configuration và loại context.

Một bản ghi trong timeline có thể mang:

| Trường | Ý nghĩa |
| --- | --- |
| `startupStep.name` | Tên hành động được đo, thường có namespace phân tách bằng dấu chấm |
| `startupStep.id` | Mã định danh bước trong lần ghi startup |
| `startupStep.parentId` | Bước cha nếu có, thể hiện nesting |
| `startupStep.tags` | Metadata như tên bean hoặc loại thao tác |
| `startTime` | Thời điểm bước bắt đầu |
| `endTime` | Thời điểm bước kết thúc |
| `duration` | Khoảng thời gian của bước |

**Không cộng tất cả `duration` để suy ra thời gian startup**: các bước có thể lồng nhau hoặc cùng thuộc một giai đoạn lớn. Cộng thời gian bước cha và bước con sẽ đếm trùng, và hoạt động song song có thể làm tổng các duration vượt quá wall-clock time.

## 3. Bốn khái niệm liên quan

### 3.1. `ApplicationStartup`

Interface của Spring Framework:

```java
package org.springframework.core.metrics;

public interface ApplicationStartup {
    StartupStep start(String name);
}
```

Đây là **minh họa phần hợp đồng chính**, không phải một tệp cần tự định nghĩa. Khi Framework hoặc application gọi `start(name)`, nó mở một startup step. Bước ấy được hoàn tất bằng `StartupStep.end()`.

`ApplicationStartup.DEFAULT` là implementation mặc định với overhead rất thấp; nó không có ý nghĩa là dữ liệu timeline sẽ tự động được lưu trong buffer hay đưa ra Actuator.

### 3.2. `StartupStep`

`org.springframework.core.metrics.StartupStep` đại diện cho một đoạn công việc:

```java
StartupStep step = startup.start("demo.bootstrap.check");
try {
    // Thao tác cần đo.
    step.tag("component", "local-config");
}
finally {
    step.end();
}
```

Đây là **đoạn code minh họa trong scope đã có biến `startup`**, không phải chương trình độc lập. Tên step nên có namespace, ổn định và mô tả thao tác; tags nên nhỏ, có số lượng giá trị khác nhau vừa phải. Không đưa access token, mật khẩu, dữ liệu nhạy cảm hoặc dữ liệu theo từng người dùng vào tags.

**Đừng quên `end()`**. Với một bước không kết thúc, buffer không có bản ghi kết thúc/duration chính xác theo cách thông thường; lỗi thiếu `end()` còn gây nhiễu quan hệ parent/child của các bước.

### 3.3. `BufferingApplicationStartup`

Tên đầy đủ:

```java
org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup
```

Implementation này thuộc **Spring Boot**, không phải package `org.springframework.core.metrics` (package đó chứa interface `ApplicationStartup` và `StartupStep`).

Khởi tạo:

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);
```

Tham số `2048` là **sức chứa số bước ghi nhận**, không phải số byte, số mili-giây, số luồng hay một giới hạn thời gian.

Recorder lưu các bước đã kết thúc, kèm timestamps và duration. Khi đã đạt capacity, **các bước mới không tiếp tục được ghi vào buffer** cho tới khi có hành động giải phóng buffer phù hợp. Đây là giới hạn của độ đầy đủ dữ liệu, không phải một lỗi làm ứng dụng dừng khởi động.

### 3.4. `StartupTimeline`

`org.springframework.boot.context.metrics.buffering.StartupTimeline` là đối tượng chứa:

- `getStartTime()` — mốc đầu của timeline;
- `getEvents()` — các `StartupTimeline.TimelineEvent` đã ghi nhận.

Mỗi `TimelineEvent` có `getStartupStep()`, `getStartTime()`, `getEndTime()` và `getDuration()`. `getStartupStep()` cung cấp `getName()`, `getId()`, `getParentId()` và `getTags()`.

Phân biệt **bước đang diễn ra** với **event đã hoàn tất và được buffer**. Không nên kỳ vọng thấy ngay một step vừa gọi `start(...)` nếu chưa gọi `end()`.

## 4. Cách gắn đúng vào SpringApplication

Đây là đoạn code **cốt lõi**:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(2048);

        application.setApplicationStartup(recorder);
        application.run(args);
    }
}
```

Các bước quan trọng:

1. Tạo đối tượng `SpringApplication` với primary source class.
2. Tạo **một** `BufferingApplicationStartup` có capacity phù hợp.
3. Gọi **`application.setApplicationStartup(recorder)` trước `application.run(args)`**.
4. Gọi `run` để Spring Boot dùng recorder cho các startup steps.

### 4.1. Vì sao không dùng chỉ `SpringApplication.run(...)` dạng static?

Cách viết thông thường:

```java
SpringApplication.run(DemoApplication.class, args);
```

rất gọn nhưng không cho bạn **cơ hội cấu hình instance `SpringApplication`** trước khi nó tự chạy. Nếu muốn gắn riêng startup recorder, tạo `new SpringApplication(...)`, gọi setter và mới `run`.

Không có nghĩa static `run` là sai trong mọi ứng dụng. Nó chỉ không đáp ứng trực tiếp nhu cầu đề bài: **đặt một `ApplicationStartup` cụ thể trước startup**.

### 4.2. Vì sao không đặt trong @PostConstruct?

**Sai thời điểm:**

```java
@PostConstruct
void configureStartupLater() {
    // Đến đây Spring đã tạo/khởi tạo bean này.
    // Nhiều bước startup ban đầu đã trôi qua.
}
```

Đoạn này minh họa lỗi về thời điểm, không phải code hoàn chỉnh. Một `@PostConstruct`, `@Bean`, `ApplicationRunner` hoặc `ApplicationReadyEvent` listener chạy **sau khi startup đã bắt đầu**. Nếu mới tạo `BufferingApplicationStartup` lúc đó, nó không thể đo ngược những bước trước.

### 4.3. Không cần tự gọi startRecording() ở mỗi lần run

Constructor `new BufferingApplicationStartup(capacity)` **đã bắt đầu ghi nhận**. API có `startRecording()` nhưng không cần gọi lại theo thói quen. Khi đã có bước được ghi trong buffer, gọi lại có thể ném `IllegalStateException`. Đừng coi nó là nút reset tùy ý trong lúc production đang chạy.

### 4.4. Gắn lên đúng SpringApplication

Trong hệ thống có nhiều `SpringApplication` instances hoặc context hierarchy, việc chỉ gắn recorder vào một instance không có nghĩa nó đã theo dõi tất cả contexts độc lập. Hãy xác định đúng instance đang `run(...)`, và chỉ diễn giải timeline tương ứng với những bước instrumented.

## 5. BufferingApplicationStartup được dùng để đo gì?

Một flow rút gọn:

```text
new BufferingApplicationStartup(2048)
             |
             v
SpringApplication.setApplicationStartup(recorder)
             |
             v
SpringApplication.run(args)
   |
   +-- Environment và bootstrap
   +-- Tạo ApplicationContext
   +-- Nạp bean definitions
   +-- Refresh context
   |     +-- Bean instantiation
   |     +-- Context lifecycle callbacks
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
             |
             v
StartupTimeline (steps đã hoàn tất)
             |
             +-- Java: getBufferedTimeline()
             +-- Java: drainBufferedTimeline()
             +-- Actuator: GET /actuator/startup
             +-- Actuator: POST /actuator/startup
```

**Điểm quan trọng:** sơ đồ startup events ở trên là luồng Spring Boot chuẩn để lấy ngữ cảnh; nó **không phải cam kết từng event đều có một `StartupStep` cùng tên** hoặc mọi đoạn code được tự động đo sâu như nhau.

Nếu code của bạn tự tạo một `Thread` và làm việc 20 giây ngoài lifecycle đang đo, buffer không tự biết mọi hành động bên trong thread đó. Muốn đo logic riêng, cần bổ sung custom startup steps đúng chỗ và completion rõ ràng.

## 6. Ví dụ Maven hoàn chỉnh có Spring Boot Actuator

Dự án sẽ:

1. Khởi tạo `SpringApplication` một cách tường minh.
2. Gắn `BufferingApplicationStartup(4096)` **trước `run()`**.
3. Chạy HTTP server trên port `8080`.
4. Bật Actuator startup endpoint có thể truy vấn từ localhost.
5. Test bằng JUnit trong chế độ non-web để kiểm tra việc ghi và drain buffer mà không mở port.

Lưu ý: demo được thiết kế cho **môi trường phát triển trên máy cá nhân**. Vì startup timeline có thể chứa tên bean, main class và thông tin cấu trúc nội bộ, không công khai endpoint này ra Internet mà không có authentication, authorization và network restriction.

### 6.1. Cấu trúc thư mục

```text
startup-buffer-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/startup/
    │   │   ├── StartupBufferApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/startup/
            └── StartupBufferTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>startup-buffer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` cung cấp servlet HTTP server và Spring MVC. `spring-boot-starter-actuator` cung cấp management endpoints. `spring-boot-starter-test` cung cấp JUnit Jupiter.

### 6.3. StartupBufferApplication.java

Tệp `src/main/java/com/example/startup/StartupBufferApplication.java`:

```java
package com.example.startup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupBufferApplication {

    public static void main(String[] args) {
        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(4096);

        SpringApplication application =
                new SpringApplication(StartupBufferApplication.class);

        application.setApplicationStartup(recorder);
        application.run(args);
    }
}
```

Đây là chương trình đầy đủ. **Không có `recorder.drainBufferedTimeline()` trong `main`** vì ta muốn các bước còn ở buffer để `/actuator/startup` có thể đọc. Nếu `main` drain ngay trước khi người vận hành gọi HTTP endpoint, dữ liệu startup có thể không còn ở đó.

Không dùng `new BufferingApplicationStartup(...)` làm replacement cho Spring application; recorder chỉ là thành phần đo, còn `SpringApplication` vẫn phụ trách bootstrap context.

### 6.4. HelloController.java

Tệp `src/main/java/com/example/startup/HelloController.java`:

```java
package com.example.startup;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
```

Controller này giúp có một ứng dụng web thật và tạo thêm một bean để Spring khởi tạo. Việc đo bean instantiation có thể chứa tag cho `helloController`, nhưng không nên hardcode tên bean đó trong test của phần API startup vì chi tiết instrumentation có thể thay đổi giữa các phiên bản.

### 6.5. application.properties

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=startup-buffer-demo
server.port=8080

management.endpoints.web.exposure.include=health,startup
```

**Phân biệt:**

- Dependency Actuator làm Spring có các endpoint phù hợp trên classpath.
- `setApplicationStartup(recorder)` là điều kiện quan trọng để **thu thập startup steps**.
- `management.endpoints.web.exposure.include=health,startup` là cấu hình **phơi bày endpoint qua HTTP** cho môi trường thử nghiệm.
- Bật exposure **không tự tạo recorder**. Nếu không gắn `BufferingApplicationStartup` trước startup, `/actuator/startup` có thể không xuất hiện dù đã expose tên `startup`.

Với demo này, `spring-boot-starter-security` không được thêm, nên URL được expose có thể truy cập trên HTTP port của ứng dụng. **Chỉ chạy local hoặc trong mạng test được hạn chế; không dùng nguyên cấu hình này ở production public.**

### 6.6. Build và chạy

Cần JDK 21, Maven, mạng có thể tải dependencies và port `8080` còn trống.

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/startup-buffer-demo-0.0.1-SNAPSHOT.jar
```

Trong terminal khác:

```bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/startup
```

Với `HelloController`, response body tại `/hello` là:

```text
hello
```

Với health endpoint của demo không có health dependency bị lỗi, bạn có thể nhận JSON tương tự:

```json
{"status":"UP"}
```

Với `/actuator/startup`, kết quả là **JSON động**, chứa các step thực tế. Không có số lượng steps/duration/ID cố định để copy và giả định giống nhau trên mọi máy.

Ví dụ **hình dạng rút gọn** (không phải stdout chính xác):

```json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "thoi-diem-ISO-8601-thuc-te",
    "events": [
      {
        "startTime": "thoi-diem-thuc-te",
        "endTime": "thoi-diem-thuc-te",
        "duration": "PT0.004S",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 3,
          "tags": [
            {
              "key": "beanName",
              "value": "helloController"
            }
          ]
        }
      }
    ]
  }
}
```

**Giải thích:** các giá trị timestamp, duration, id và tag value ở trên chỉ mô tả **cấu trúc payload**, không phải giá trị được xác minh của lần chạy cụ thể; response thực tế có thể có nhiều bước hơn, `parentId` và nhiều tags khác. Đừng dùng snapshot giả định này làm expected output của automated tests.

## 7. GET snapshot và POST drain là hai thao tác khác nhau

Trong Spring Boot 3.3, Actuator startup endpoint cho phép hai HTTP methods:

| Request | Công dụng | Tác động đến buffer |
| --- | --- | --- |
| `GET /actuator/startup` | Xem startup steps đã thu thập | **Không xóa** dữ liệu |
| `POST /actuator/startup` | Trả các steps và **drain** buffer | **Xóa** các steps được lấy ra |
| `GET` sau `POST` | Xem trạng thái buffer hiện thời | Có thể ít hoặc không còn events |

Ví dụ chạy trên app local:

```bash
curl -sS http://localhost:8080/actuator/startup
curl -sS http://localhost:8080/actuator/startup
curl -sS -X POST http://localhost:8080/actuator/startup
curl -sS http://localhost:8080/actuator/startup
```

Hai lệnh GET đầu đọc snapshot mà không chủ động drain. Lệnh POST lấy và rút các sự kiện đã buffer. GET sau cùng thường trả `events` rỗng nếu không có step nào khác được ghi thêm; **không coi số lượng bằng 0 là invariant khi vẫn có hoạt động ghi đồng thời**.

### 7.1. Vì sao không dùng POST chỉ để kiểm tra?

Một dashboard hoặc thao tác thử API dùng POST có thể **làm mất dữ liệu trong bộ đệm** mà một công cụ khác định lấy. Nếu bạn chỉ muốn quan sát, dùng GET. Chỉ POST khi có chủ ý thu thập và rút dữ liệu, ví dụ một hệ thống diagnostics đã lưu response đi nơi khác.

### 7.2. Mã lỗi không đúng mong đợi

Nếu gọi GET nhưng nhận `404`, các nguyên nhân thường gặp:

- Chưa thêm `spring-boot-starter-actuator`.
- Chưa expose endpoint qua `management.endpoints.web.exposure.include`.
- Chưa gắn `BufferingApplicationStartup` lên đúng `SpringApplication` trước `run`.
- Endpoint bị disable, không sẵn có hoặc nằm sau base path/port khác.
- Ứng dụng không phải một web application; demo có web starter nhưng thực tế hệ thống có thể chọn `WebApplicationType.NONE`.
- Proxy/routing khiến request đi tới instance khác.

Nếu nhận `401`/`403`, kiểm tra security, authentication/authorization và CSRF đối với thao tác POST, không mặc định đó là lỗi recorder.

## 8. Dùng BufferingApplicationStartup trực tiếp trong Java

Không bắt buộc có Actuator nếu chỉ muốn đo và xử lý timeline trong code.

### 8.1. Đọc snapshot

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);

SpringApplication app = new SpringApplication(DemoApplication.class);
app.setApplicationStartup(recorder);

ConfigurableApplicationContext context = app.run(args);
try {
    StartupTimeline snapshot = recorder.getBufferedTimeline();

    System.out.println("recorded steps: "
            + snapshot.getEvents().size());
}
finally {
    context.close();
}
```

Đoạn trên là **ví dụ tích hợp trong một class khác có `DemoApplication`, `args` và imports cần thiết**; không phải một chương trình độc lập. `getBufferedTimeline()` cung cấp snapshot của các events hiện có **mà không xóa chúng**.

Trong một hệ thống nhiều threads vẫn còn ghi steps, snapshot là ảnh chụp tại thời điểm được lấy; không tự trở thành bản ghi tất cả những bước sẽ được tạo trong tương lai.

### 8.2. Đọc timeline và các fields

```java
StartupTimeline timeline = recorder.getBufferedTimeline();

for (StartupTimeline.TimelineEvent event : timeline.getEvents()) {
    System.out.println(
            event.getStartupStep().getName()
            + " duration=" + event.getDuration());
}
```

Đây là **đoạn minh họa dùng biến `recorder`**. `getDuration()` trả `java.time.Duration`. Thứ tự và số lượng dòng phụ thuộc app; không nên assert một số lượng bean steps cố định.

Muốn tìm các bước lâu nhất, có thể tạo list và sort theo `event.getDuration()`, nhưng phải nhớ đây là elapsed time cho từng step, không nhất thiết là root cause CPU hoặc I/O. Phải xem tags, parent-child nesting, thread activity và các phép đo khác trước khi kết luận.

### 8.3. Drain bằng Java

```java
StartupTimeline drained = recorder.drainBufferedTimeline();
int count = drained.getEvents().size();

System.out.println("drained events: " + count);
System.out.println("remaining events: "
        + recorder.getBufferedTimeline().getEvents().size());
```

Các dòng trên là **minh họa**. Nếu không có threads mới ghi step đồng thời, lần snapshot sau drain thường rỗng. `drainBufferedTimeline()` không phải API “lấy snapshot không phá hủy”; hãy tránh gọi nó từ hai consumers độc lập nếu mỗi nơi đều kỳ vọng toàn bộ dữ liệu startup.

### 8.4. Có cần tạo Bean cho recorder không?

Cách chính xác nhất cho mục đích đo **toàn bộ quá trình Spring Boot chạy** là gắn recorder vào `SpringApplication` **trước `run`**, như ví dụ chính. Không nên chỉ làm:

```java
@Bean
BufferingApplicationStartup recorder() {
    return new BufferingApplicationStartup(2048);
}
```

Đây là **ví dụ không đủ để đạt đề bài**, vì bean được tạo trong quá trình context khởi tạo, khi nhiều startup steps đã trôi qua. Thêm `@Bean` không thay thế `setApplicationStartup`. Spring Boot có thể cung cấp startup implementation đã được gắn cho các thành phần thích hợp, nhưng không cần tự tạo một recorder thứ hai để đọc timeline: nếu đọc một recorder khác với instance đã set, bạn có thể thấy buffer rỗng hoặc dữ liệu không đúng.

## 9. Ghi một custom StartupStep

Các startup steps sẵn có của Framework không tự giải thích mọi tác vụ nghiệp vụ. Khi một bước quan trọng của app cần được đo, bạn có thể ghi step riêng trên **cùng recorder**.

Ví dụ một thao tác có sẵn trong phần bootstrap Java:

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);

StartupStep verifyStep =
        recorder.start("demo.bootstrap.verify-local-config");
try {
    verifyLocalConfiguration();
    verifyStep.tag("result", "ok");
}
finally {
    verifyStep.end();
}

SpringApplication application = new SpringApplication(DemoApplication.class);
application.setApplicationStartup(recorder);
application.run(args);
```

Đây là **đoạn minh họa không độc lập**: cần định nghĩa `verifyLocalConfiguration()`, `DemoApplication` và imports. Tác vụ chạy trước `run` vẫn được recorder giữ lại vì nó dùng đúng cùng instance; các step của Spring Boot được ghi tiếp khi `run` bắt đầu.

### 9.1. Nên đặt tên và tag thế nào?

Tên step nên biểu thị thao tác ổn định:

```text
demo.bootstrap.verify-local-config
demo.cache.warmup
demo.schema.validate
```

Tags hữu ích có thể là `component=cache`, `mode=local`, `result=ok`. Tránh dùng order ID, email, token, đường dẫn có secrets hoặc hàng nghìn giá trị biến đổi làm tags, vì chúng có thể lộ qua endpoint và gây bùng nổ cardinality khi bạn phân tích metrics.

### 9.2. Bảo đảm mọi branch đều end()

Một bug rất dễ gặp:

```java
StartupStep step = recorder.start("demo.preflight");
if (!configurationExists()) {
    return; // SAI: step chưa kết thúc.
}
step.end();
```

Đây là anti-pattern minh họa. Nên dùng `try/finally`; không tạo step rồi để luồng exception hoặc return khiến `end()` bị bỏ quên.

### 9.3. Nếu bước là bất đồng bộ?

Nếu method chỉ submit một `CompletableFuture` và return, duration đo quanh submit **không phải thời gian job hoàn tất**. Muốn đo completion thật, phải chọn vị trí end đúng theo hợp đồng completion, phối hợp concurrency và tránh race/cross-thread interpretation. Không mặc định `StartupStep` có thể giữ như một stopwatch được dùng tùy tiện giữa các threads mà không kiểm tra implementation.

Nếu task được chờ trong `ApplicationRunner`, có thể dùng startup step để đo khoảng chờ thật, rồi kiểm tra kết quả. Nhưng nếu task chỉ chạy nền và Boot phát `ApplicationReadyEvent` trước khi task hoàn thành, một step ngắn không chứng minh app đã ready về mặt nghiệp vụ.

## 10. Quản lý capacity và overhead

### 10.1. Capacity là số events, không phải thời gian

`new BufferingApplicationStartup(2048)` có giới hạn số bước được buffer. Nếu ứng dụng có rất nhiều beans, nhiều auto-configuration hoặc custom startup steps, 2048 có thể không đủ để giữ toàn bộ quá trình.

Khi đầy, các bước mới **không được tiếp tục lưu**; ứng dụng vẫn có thể khởi động bình thường nhưng timeline thiếu những phần về sau. Vì vậy:

- Chọn capacity dựa trên số steps đo được trong các runs đại diện.
- Trong một lần profiling, có thể tăng lên 4096 hoặc lớn hơn nếu memory budget cho phép.
- Chỉ lưu những tên steps cần thiết bằng filter khi mục tiêu phân tích rõ.
- Dùng drain ở thời điểm phù hợp nếu có consumer thu nhận dữ liệu liên tục.
- Tránh hiểu “timeline ít steps” thành “ứng dụng có ít việc startup”.

### 10.2. Lọc steps

`BufferingApplicationStartup#addFilter(Predicate<StartupStep>)` cho phép lọc những step sẽ được lưu:

```java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(4096);

recorder.addFilter(step ->
        step.getName().startsWith("spring.beans."));
```

Đây là đoạn minh họa, có thể đặt **trước khi gắn recorder và chạy ứng dụng**. Với filter này, những steps không thuộc nhóm `spring.beans.*` có thể không còn xuất hiện trong timeline; điều đó là **do chọn lọc**, không phải Framework không thực hiện những bước ấy.

Nhiều filters được kết hợp theo điều kiện cần cùng thỏa mãn. Không áp dụng filter sau khi đã ghi xong và kỳ vọng nó tự xóa dữ liệu cũ.

### 10.3. Lọc có thể làm mất bối cảnh

Nếu chỉ giữ steps về bean instantiation, bạn có thể không còn các steps cấp cao biểu diễn vòng đời refresh. Khi đó `parentId` có thể tham chiếu một step đã không được lưu do filter. Đây không nhất thiết là dữ liệu hỏng; đó là kết quả của chính sách lọc.

Tùy mục tiêu, lưu toàn bộ để điều tra lần đầu; các lần tiếp theo mới thu hẹp filter.

### 10.4. Bộ đệm không phải tracing backend

`BufferingApplicationStartup` là in-memory buffer, không phải hệ thống lưu dữ liệu startup lâu dài, không phải distributed trace backend và không tự ship steps tới observability platform. Muốn lưu/so sánh qua lần deploy, phải chủ động thu thập JSON/timeline và lưu ở nơi phù hợp, có bảo mật và retention policy.

### 10.5. Đừng bật quá rộng trong production

Thu thập startup có overhead (thời gian và bộ nhớ) và có thể để lộ topology của ứng dụng. Khi profiling production:

- Đo impact bằng thử nghiệm trên staging/production-like.
- Giới hạn dung lượng, chỉ giữ dữ liệu cần phân tích.
- Kiểm soát ai được gọi endpoint.
- Không công khai endpoint nhạy cảm.
- Tắt profiling hoặc dùng filter nếu không còn nhu cầu.

## 11. GET/POST không giống việc khởi động lại ứng dụng

Một hiểu nhầm phổ biến là `POST /actuator/startup` sẽ “đo lại startup” hoặc “restart app”. **Không đúng.** Trong Spring Boot 3.3, POST trả timeline và drain buffer hiện có. Nó không gọi lại `SpringApplication.run`, không refresh lại context, không khởi động lại beans.

Tương tự, GET chỉ xem snapshot; nó không bắt đầu một phép đo mới. Nếu muốn so sánh cold startup với warm startup, cần **những lần khởi chạy riêng** dưới điều kiện kiểm soát tương đương.

### 11.1. Phân biệt startup timeline và tổng startup time

Có những tín hiệu khác:

- Log `Started ... in ... seconds`: thông tin tổng quan về thời gian startup.
- `ApplicationStartedEvent#getTimeTaken()`: thời gian tới mốc started (sau refresh, trước runners) nếu có.
- `ApplicationReadyEvent#getTimeTaken()`: thời gian tới mốc ready (sau runners) nếu có.
- `ApplicationStartup`/`StartupStep`: các đoạn thao tác được instrumented ở mức chi tiết.

Không dùng duration của một step cuối làm tổng thời gian khởi động nếu step ấy chỉ đo một đoạn. Cũng không so sánh một cách đơn giản tổng duration của toàn bộ events với thời gian JVM thực tế.

### 11.2. Startup snapshot khác readiness và health

Một endpoint startup trả 200 với nhiều steps không có nghĩa instance hiện đang healthy, sẵn sàng xử lý traffic hoặc các dependencies bên ngoài đang hoạt động. Readiness và liveness là một bộ tín hiệu khác. Một ứng dụng có thể đã ghi đủ timeline nhưng sau đó rơi vào lỗi runtime; startup recorder không phải live health monitor.

Nếu mục tiêu là biết khi nào ứng dụng sẵn sàng nhận việc mới, cần `ReadinessState`/Actuator probes và các kiểm tra nghiệp vụ phù hợp; không dùng riêng số lượng startup events.

## 12. JUnit kiểm chứng cách gắn recorder

Test nên chứng minh rằng recorder đã được dùng **trước quá trình startup**, có steps được ghi, snapshot không xóa và drain làm trống phần đã lấy. Tránh assert cứng rằng phải có đúng `179` hoặc `542` events: số lượng phụ thuộc classpath, cấu hình, environment và các version.

Tệp `src/test/java/com/example/startup/StartupBufferTest.java`:

```java
package com.example.startup;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StartupBufferTest {

    @Test
    void recordsStartupStepsAndSupportsSnapshotAndDrain() {
        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(4096);

        SpringApplication app =
                new SpringApplication(StartupBufferApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setApplicationStartup(recorder);

        try (ConfigurableApplicationContext context = app.run(
                "--spring.main.banner-mode=off",
                "--logging.level.root=ERROR")) {

            assertTrue(context.isActive());

            StartupTimeline first = recorder.getBufferedTimeline();
            List<StartupTimeline.TimelineEvent> events = first.getEvents();

            assertFalse(events.isEmpty());

            assertTrue(events.stream()
                    .anyMatch(event -> event.getStartupStep()
                            .getName().startsWith("spring.")));

            StartupTimeline second = recorder.getBufferedTimeline();
            assertEquals(events.size(), second.getEvents().size());

            StartupTimeline drained = recorder.drainBufferedTimeline();
            assertEquals(events.size(), drained.getEvents().size());

            assertTrue(recorder.getBufferedTimeline().getEvents().isEmpty());
        }
    }
}
```

Giải thích:

1. Test tạo **recorder riêng** cho lần khởi động này.
2. `setApplicationStartup(recorder)` được gọi **trước `app.run(...)`**.
3. Test dùng `WebApplicationType.NONE` để không mở HTTP port, dù project có web starter trên classpath.
4. `getBufferedTimeline()` trả snapshot; hai lần đọc không làm mất steps.
5. `drainBufferedTimeline()` trả dữ liệu và lấy nó khỏi buffer; sau drain, khi không có bước khác được ghi thêm, snapshot rỗng.
6. Không phụ thuộc duration/ID cụ thể, nên test ổn định hơn.

Chạy:

```bash
mvn test
```

Kỳ vọng **một JUnit test** thành công với project này khi dependencies tải được và không có cấu hình ngoài dự kiến. Để kiểm thử HTTP Actuator `GET`/`POST` end-to-end, nên có một test web riêng hoặc dùng `curl` như mục 7; test này không mở HTTP endpoint và không kiểm tra HTTP security.

**Lưu ý khi mở rộng test:** context có thể ghi các startup steps từ các callbacks không đồng bộ hoặc component riêng. Khi đó phép kiểm tra “snapshot rỗng ngay sau drain” cần đồng bộ hóa hoặc đưa app về trạng thái không còn ghi steps. Với demo hiện tại, chúng ta không tạo custom background startup steps.

## 13. Cách đọc timeline để tìm vấn đề

Khi nhận timeline JSON từ `/actuator/startup`, hãy phân tích có quy trình:

1. Ghi rõ commit, JDK, phiên bản Boot, profiles, CPU/RAM và môi trường chạy.
2. Lưu snapshot trước khi thay đổi code để có baseline.
3. Tìm những steps có duration lớn; phân nhóm theo tên và tags.
4. Xem `parentId` để nhận diện bước nằm trong giai đoạn nào.
5. Tránh cộng duration của parent và child.
6. Kiểm tra các bước bị thiếu do filter/capacity.
7. Kết hợp CPU profiler, JFR, thread dump, GC logs, DB/network traces nếu chậm do hạ tầng.
8. Chạy nhiều lần, tách cold-start và warm-start, xem phân bố thay vì chỉ một mẫu.
9. So sánh cùng điều kiện; không kết luận tối ưu hiệu quả chỉ vì một lần run nhanh hơn.
10. Đưa thay đổi vào test đo lại performance và kiểm tra chức năng startup bình thường.

### 13.1. Một bean có duration lớn

Nếu thấy `spring.beans.instantiate` cho một bean có duration cao, điều đó chỉ cho biết Spring đo được nhiều elapsed time trong quá trình tạo/khởi tạo bean ấy. Nguyên nhân có thể là constructor, `@PostConstruct`, dependency chain, factory method, external I/O hoặc lớp khác bị gọi gián tiếp.

Đừng kết luận "constructor chậm" chỉ dựa vào tên step mà chưa xem dependency và timestamps.

### 13.2. Một step bao quanh external call

Nếu method init gọi dịch vụ ngoài với timeout 10 giây, duration có thể bao gồm network wait. Startup recorder không tự biết DNS, TCP connect, TLS handshake, DB locks hay CPU work chi tiết. Dùng thêm network trace, client metrics hoặc JFR nếu cần phân rã nguyên nhân.

### 13.3. Cấu hình lazy initialization

Khi bật `spring.main.lazy-initialization=true`, startup có thể nhanh hơn vì một số beans chưa được tạo. Nhưng chi phí có thể chuyển sang **request đầu tiên**, đồng thời lỗi cấu hình xuất hiện muộn hơn. Một timeline ngắn hơn không mặc nhiên có nghĩa user-perceived latency tốt hơn.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `GET /actuator/startup` trả 404 | Actuator chưa thêm, endpoint chưa expose hoặc recorder chưa được gắn | Kiểm tra dependency, property và setter trước `run` |
| `GET` trả nhiều bước, `POST` rồi `GET` gần như rỗng | POST đã drain buffer | Dùng GET để đọc không phá hủy |
| Timeline có rất ít bước | Buffer quá nhỏ, filter quá hẹp hoặc bị drain | Tăng capacity có kiểm soát; kiểm tra filters và ai gọi POST |
| `@Bean BufferingApplicationStartup` không ghi được bước sớm | Bean được tạo trong quá trình startup | Set trực tiếp trên `SpringApplication` trước `run` |
| Tạo recorder sau `SpringApplication.run(...)` | Quá muộn | Tạo trước khi bootstrap |
| Gọi `startRecording()` tùy tiện | Constructor đã bắt đầu recording; gọi lại sau khi ghi có thể lỗi | Không gọi nếu không có lý do và hiểu contract |
| Custom step không xuất hiện | Quên `end()` hoặc dùng recorder khác | `try/finally`, cùng instance |
| Duration khác giữa các lần chạy | JIT, GC, I/O, CPU, classloading, caches | Đo nhiều lần dưới điều kiện tương đương |
| Tổng step duration lớn hơn startup wall time | Nested steps bị cộng trùng | Xem parent/child và intervals, không cộng thô |
| Có dữ liệu nhưng app vẫn không ready | Startup recorder không phải readiness probe | Dùng availability/health riêng |
| `POST` bị 403 | Spring Security/CSRF hoặc policy | Kiểm tra quyền và cấu hình bảo mật, không mở công khai |
| GET không thấy nhiều step business | Framework chỉ tự đo các điểm được instrumented | Tạo custom steps đúng thời điểm |
| Đặt filter sau khi startup xong | Không làm thay đổi dữ liệu cũ | Đặt filter trước `run` |
| Trộn dữ liệu hai instance | Load balancer gửi GET sang pod khác | Thu thập theo instance ID/pod |
| Timeline làm lộ bean/config names | Endpoint exposure quá rộng | Giới hạn mạng, xác thực và quyền truy cập |
| Không phân biệt `ApplicationStartup` với `ApplicationReadyEvent` | Một bên là đo bước, một bên là lifecycle event | Xác định mục tiêu đo và readiness riêng |

### 14.1. Checklist chẩn đoán nhanh

1. Có chắc `SpringApplication` đang `run` chính là instance vừa được `setApplicationStartup`?
2. Đã gọi setter **trước** khi startup bắt đầu?
3. Đã import `BufferingApplicationStartup` từ đúng package `org.springframework.boot.context.metrics.buffering`?
4. Dùng constructor capacity dương và đủ lớn?
5. Có `@Bean` thứ hai gây nhầm recorder?
6. Có ai gọi `drainBufferedTimeline()` hoặc HTTP POST trước đó?
7. Có filter không phù hợp với tên steps muốn đo?
8. Có đủ `spring-boot-starter-actuator` và web starter?
9. Đã expose `startup` qua management properties?
10. Port/base path/authentication/authorization/CSRF đúng?
11. Endpoint có đang đi qua load balancer đến một pod khác?
12. Có người khác vừa đọc bằng POST và rút mất dữ liệu?
13. Custom steps có được end bằng `finally`?
14. Có đang cố coi số event là tổng thời gian sẵn sàng?
15. Có lưu snapshot trước khi restart nếu cần so sánh?
16. Có kiểm tra profiling overhead và tránh tags nhạy cảm?

## 15. Bài tập và câu hỏi tự kiểm tra

1. `ApplicationStartup` thuộc Spring Framework hay Spring Boot? `BufferingApplicationStartup` thuộc package nào?
2. Tại sao `setApplicationStartup` phải được gọi trước `run`?
3. Phân biệt `StartupStep` và `StartupTimeline.TimelineEvent`.
4. Capacity `2048` nghĩa là gì? Nó có giới hạn số mili-giây startup không?
5. Nếu buffer đầy, chuyện gì xảy ra với các bước mới và với việc Boot startup?
6. Vì sao `@PostConstruct` tạo recorder là quá muộn để ghi các bước đầu?
7. Từ source demo, hãy thay capacity 4096 bằng 32 và so sánh số lượng steps được ghi.
8. Viết filter chỉ giữ các steps có tên bắt đầu với `spring.beans.`.
9. Nếu filter bỏ các parent steps, `parentId` có thể còn tham chiếu parent không được lưu không?
10. Phân biệt GET và POST của `/actuator/startup`.
11. Vì sao gọi POST trước khi lưu JSON có thể gây mất dữ liệu cho công cụ khác?
12. `getBufferedTimeline()` khác `drainBufferedTimeline()` ở điểm nào?
13. Trong test, tại sao không assert đúng số bước hoặc duration cứng?
14. Hãy thêm custom step `demo.bootstrap.verify-local-config` và tag `result=ok`, đảm bảo `end()` trong `finally`.
15. Nếu một `ApplicationRunner` chỉ submit async task rồi return, startup duration của step đo submit có chứng minh task đã xong chưa?
16. Vì sao không được cộng durations của tất cả events để suy ra tổng thời gian?
17. Với hai lần khởi động khác nhau, phải kiểm soát những biến môi trường nào để so sánh?
18. Nếu app có `spring.main.lazy-initialization=true`, startup nhanh hơn nhưng điều gì có thể trở nên chậm hơn?
19. Một bean instantiation step dài có chắc constructor của bean chậm không?
20. Nếu endpoint startup trả JSON nhưng `/actuator/health` trả lỗi, điều đó có mâu thuẫn không?
21. Trong Kubernetes nhiều pods, vì sao phải biết instance nào đã trả timeline?
22. Vì sao cần bảo vệ Actuator startup endpoint dù nó không cho sửa business data?
23. Tạo unit test chứng minh GET-like snapshot không xóa, POST-like drain làm rỗng recorder.
24. Khi nào cần JFR hoặc profiler bên cạnh BufferingApplicationStartup?
25. Giải thích khác biệt giữa `ApplicationReadyEvent#getTimeTaken()` và timeline durations.
26. Nếu muốn lưu 10 lần khởi động để phân tích regression, hãy đề xuất một quy trình thu thập an toàn, có version, environment, timestamp và retention.

**Tiêu chí đạt:** chạy được dự án Spring Boot 3.3, hiểu chính xác cách gắn recorder trước startup, truy vấn GET/POST đúng semantics, giải thích tác dụng buffer/filter và biết dùng timeline để điều tra mà không nhầm nó với readiness hay business metrics.

## 16. Nguồn tham khảo chính thức

- Spring Boot 3.3 — SpringApplication / Application Startup Tracking: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `SpringApplication#setApplicationStartup`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `BufferingApplicationStartup`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html
- Spring Boot 3.3.13 — `StartupTimeline`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/StartupTimeline.html
- Spring Boot 3.3 — Actuator Startup Endpoint (GET/POST): https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Actuator Endpoints/Exposure/Security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Framework 6.1 — `ApplicationStartup`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
- Spring Framework 6.1 — `StartupStep`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/StartupStep.html
- Spring Framework 6.1 — Java Flight Recorder startup implementation: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
