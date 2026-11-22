# ApplicationStartup và các StartupStep — đo, phân tích chuỗi khởi động Spring Boot

## 1. Bài toán: “Ứng dụng khởi động chậm” chậm ở bước nào?

Khi khởi chạy một ứng dụng Spring Boot, dòng log `Started ... in ... seconds` cho biết một khoảng thời gian khởi động tổng hợp, nhưng nó **không tự chỉ ra** thời gian được tiêu tốn vào component scan, phân tích `@Configuration`, tạo bean, thực thi `BeanFactoryPostProcessor` hay một thao tác initialization tùy biến.

Spring Framework cung cấp **`ApplicationStartup`** và **`StartupStep`** để mô tả **các bước công việc có tên, tag và thời điểm bắt đầu/kết thúc** trong quá trình khởi tạo `ApplicationContext`. Spring Boot bổ sung `BufferingApplicationStartup`, liên kết với Actuator `/actuator/startup`; Spring Framework cũng có `FlightRecorderApplicationStartup` để xem các bước cùng sự kiện JVM qua Java Flight Recorder (JFR).

Một điều cần hiểu ngay:

> `ApplicationStartup` **không phải một loại application event** và `StartupStep` **không phải một Spring bean bắt buộc**. Chúng là API ghi nhận các bước thực thi có thể dùng để chẩn đoán startup.

Các câu hỏi mà bài này giúp giải đáp:

- `ApplicationStartup.DEFAULT` làm gì, khi nào phải bật recording?
- `start("step.name")`, `tag(...)` và `end()` có thứ tự thế nào?
- Khi nào dùng `BufferingApplicationStartup`, khi nào dùng `FlightRecorderApplicationStartup`?
- Đọc JSON từ `GET /actuator/startup` khác `POST /actuator/startup` ra sao?
- `id` và `parentId` của step giúp phân tích quan hệ như thế nào?
- Làm sao chèn step tùy biến vào việc tạo một bean, và tránh quên `end()` khi lỗi?
- Vì sao không thể cộng thời gian mọi step để thành thời gian JVM startup?
- Những lưu ý về dung lượng buffer, monitoring overhead, bí mật trong tags và quyền truy cập endpoint?

## 2. Cơ chế và luồng dữ liệu

SpringApplication và Spring Framework container đã có sẵn các điểm instrumentation nội bộ. Khi cấu hình một `ApplicationStartup` implementation ở **đầu quá trình khởi chạy**, các phần khung được instrumented sẽ tạo `StartupStep` tương ứng.

~~~mermaid
flowchart TD
    MAIN["main(String[] args)"] --> CONFIG["SpringApplication.setApplicationStartup(...)"]
    CONFIG --> RUN["SpringApplication.run(args)"]
    RUN --> TRACKER["ApplicationStartup.start(name)"]
    TRACKER --> STEP["StartupStep: id, name, parentId, tags"]
    STEP --> END["StartupStep.end()"]
    END --> BUF["BufferingApplicationStartup: timeline in memory"]
    END --> JFR["FlightRecorderApplicationStartup: JFR events"]
    BUF --> HTTP["Actuator GET/POST /actuator/startup"]
    BUF --> CODE["getBufferedTimeline() / drainBufferedTimeline()"]
    JFR --> VIEW["JFR / JDK Mission Control / jfr CLI"]
~~~

Đây là sơ đồ hai **lựa chọn implementation**. Trong ví dụ chuẩn, bạn cấu hình **một** implementation cho một `SpringApplication`. Nó không có nghĩa một step được tự ghi đồng thời vào hai nơi trong mọi ứng dụng.

### Từ bước có tên đến thời gian đo

Giả sử framework cần xử lý một cấu hình:

~~~java
StartupStep step = applicationStartup.start("demo.catalog.prepare");
try {
    prepareCatalog();
} finally {
    step.end();
}
~~~

Snippet này cần biến `applicationStartup` kiểu `ApplicationStartup` và method `prepareCatalog()` đã định nghĩa. Khi dùng implementation có ghi nhận, khoảng từ `start` đến `end` trở thành một bước có thể quan sát trong timeline/JFR.

Nếu code không gọi `end()`, step có thể không được đưa vào bản ghi hoàn chỉnh hoặc làm sai cấu trúc quan sát. **Luôn dùng `try/finally`**, đặc biệt với constructor, bean factory, I/O hoặc các bước có thể ném exception.

### Step là khoảng thời gian công việc, không phải chỉ một dòng log

Một step có thể bao gồm:
- thời gian CPU;
- chờ I/O;
- chờ lock;
- class loading;
- các step con được tạo trong khi step cha đang mở.

Vì vậy duration của một step là **elapsed processing time của đoạn đã được bao quanh**, không phải CPU time riêng của đoạn đó, cũng không tự chứng minh toàn bộ thời gian thuộc về một bean cụ thể.

## 3. ApplicationStartup: API nền tảng của Spring Framework

Interface ở package:

~~~java
org.springframework.core.metrics.ApplicationStartup
~~~

Có hai thành phần cơ bản:

| Thành phần | Chữ ký/giá trị | Ý nghĩa |
| --- | --- | --- |
| `ApplicationStartup.start(String name)` | Trả `StartupStep` | Bắt đầu theo dõi một bước có tên kỹ thuật |
| `ApplicationStartup.DEFAULT` | No-op implementation | Ít overhead; **không thu thập** timeline startup thực tế |

Đường mặc định được thiết kế tối giản: chỉ bật Spring Boot Actuator không có nghĩa mọi startup step đã được ghi vào buffer. Để sử dụng endpoint startup cho mục đích chẩn đoán, phải cấu hình tracker phù hợp trước khi các bước quan trọng diễn ra.

### Vì sao phải cấu hình sớm?

Nếu ứng dụng chỉ tạo `new BufferingApplicationStartup(2048)` sau khi context đã refresh, những công việc xảy ra trước đó **không được ghi lại hồi tố**. Do vậy cách chuẩn là:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setApplicationStartup(
        new BufferingApplicationStartup(2048));
application.run(args);
~~~

Đây là snippet, cần các import/class phù hợp. Điều quan trọng là `setApplicationStartup(...)` được gọi **trước** `run(args)`.

Tạo một `@Bean BufferingApplicationStartup` sau đó nhưng không cấu hình lên `SpringApplication` **không phải thao tác tương đương**; nó có thể tạo tracker thứ hai không dùng cho framework steps. Trong Boot hiện đại, tracker cấu hình cho application cũng có thể được inject qua infrastructure; không nên đăng ký thêm một bean trùng type vô cớ.

### Startup tracking thuộc framework hay Boot?

- Spring Framework 5.3+ định nghĩa `ApplicationStartup` và `StartupStep` trong `spring-core`.
- Spring Framework cung cấp `FlightRecorderApplicationStartup` ở `org.springframework.core.metrics.jfr`.
- Spring Boot 2.4+ có `BufferingApplicationStartup` ở `org.springframework.boot.context.metrics.buffering`.
- Spring Boot Actuator cung cấp `startup` endpoint cho **buffer implementation**.
- Các bước cụ thể được ghi bởi Spring/Boot là chi tiết triển khai, có thể thay đổi tên/tag trong các bản cập nhật.

## 4. StartupStep: vòng đời, thông tin và tags

`org.springframework.core.metrics.StartupStep` có các API đáng nhớ:

| API | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `getName()` | `String` | Tên kỹ thuật của bước |
| `getId()` | `long` | ID riêng cho step trong quá trình startup |
| `getParentId()` | `Long` (có thể null) | ID của bước cha nếu có |
| `tag(String key, String value)` | `StartupStep` | Gắn metadata key/value |
| `tag(String key, Supplier<String> value)` | `StartupStep` | Gắn metadata được cung cấp bởi một supplier |
| `getTags()` | `StartupStep.Tags` | Các tag của step |
| `end()` | `void` | Đánh dấu step đã xong, để implementation chốt thông tin |

### Vòng đời đúng

~~~mermaid
flowchart LR
    CREATE["applicationStartup.start(name)"] --> TAG["step.tag(key, value)"]
    TAG --> EXECUTE["Thực thi công việc thực tế"]
    EXECUTE --> FINALLY["finally: step.end()"]
    FINALLY --> OBSERVE["Timeline/JFR ghi nhận"]
~~~

Một step có thể có không có tag. Có thể thêm nhiều tag **trước khi `end()`**. Đừng sửa state của step sau `end()`: Javadoc yêu cầu bước đã kết thúc không còn được chỉnh sửa.

### Tên step nên như thế nào?

Spring Framework khuyến nghị tên kỹ thuật có namespace phân tách bằng dấu chấm, có thể được tái sử dụng cho nhiều instance của cùng loại công việc:

~~~text
demo.catalog.prepare
demo.cache.warmup
company.connector.initialize
~~~

**Không đặt tên custom bắt đầu bằng `spring.`**, vì namespace này được dành cho framework nội bộ. Không đặt step name là một ID ngẫu nhiên theo mỗi lần chạy; tên nên mô tả **loại thao tác**, còn thông tin phân loại thuộc tags.

### Tags: dùng để hiểu “bước nào”

~~~java
StartupStep step =
        applicationStartup.start("demo.connector.prepare");

step.tag("component", "pricing-client");
step.tag("mode", "initial-load");

try {
    initializeConnector();
} finally {
    step.end();
}
~~~

Đây là snippet cần biến và method tương ứng. Nó diễn tả:
- name = `demo.connector.prepare`;
- tag `component` = `pricing-client`;
- tag `mode` = `initial-load`.

Tags là **chuỗi metadata**, không phải Java objects hay metrics labels vô hạn. Không gắn password, access token, connection string, dữ liệu người dùng hoặc bản dump của toàn `Environment` vào tags. Những nội dung này có thể hiện trong Actuator JSON/JFR hoặc log chẩn đoán.

### Supplier tag

~~~java
step.tag("configCount", () -> Integer.toString(configs.size()));
~~~

Snippet cần biến `configs` phù hợp. Supplier cho phép implementation lấy biểu diễn của tag khi thích hợp, có thể tránh tính chuỗi tốn công trong một số tình huống. Nhưng **không dùng Supplier để thực hiện side effects** hoặc truy cập đối tượng đã bị giải phóng sau khi step kết thúc; ưu tiên dữ liệu mô tả ngắn, ổn định.

### ID và parentId không phải khóa trong database

`id` giúp nhận diện một step trong một timeline; `parentId` giúp chỉ ra quan hệ cha-con khi framework/implementation ghi nhận được. Đừng dùng `id` như business identifier bền vững qua các lần deploy: một startup khác có thể đánh số từ đầu hoặc tạo thứ tự bước khác.

**Không khẳng định parentId luôn hiện diện**: top-level steps có thể không có parent và dữ liệu serialize có thể lược bỏ field này. Trong code, `getParentId()` có thể `null`; đừng unbox trực tiếp sang `long` khi chưa kiểm tra.

## 5. Những bước mặc định của Spring nên nhận diện

Spring Framework đã instrument nhiều đường xử lý. Các tên dưới đây là **ví dụ theo tài liệu Spring Framework 6.2**, không phải hợp đồng API bất biến:

| Tên `StartupStep` | Công việc thường được đo | Tag ví dụ |
| --- | --- | --- |
| `spring.context.refresh` | Refresh application context | Tùy implementation |
| `spring.context.base-packages.scan` | Component scan các base packages | `packages` |
| `spring.context.config-classes.parse` | Parse configuration classes | `classCount` |
| `spring.context.config-classes.enhance` | Enhance configuration classes | `classCount` |
| `spring.context.bean-factory.post-process` | Chạy `BeanFactoryPostProcessor` | `postProcessor` |
| `spring.context.beandef-registry.post-process` | Chạy registry post-processor | `postProcessor` |
| `spring.context.beans.post-process` | Phase bean post-processing | Tùy step |
| `spring.beans.instantiate` | Tạo một bean cùng những dependency liên quan | `beanName`, `beanType` |
| `spring.beans.smart-initialize` | `SmartInitializingSingleton` callback | `beanName` |
| `spring.context.annotated-bean-reader.create` | Tạo annotated bean definition reader | Tùy step |

Spring Boot có thể thêm những bước `spring.boot.*` liên quan bootstrap/lifecycle. Một số step cụ thể chỉ xuất hiện khi feature tương ứng được sử dụng.

### Ví dụ diễn giải

Nếu JSON chứa:

~~~json
{
  "name": "spring.beans.instantiate",
  "tags": [
    {"key": "beanName", "value": "pricingClient"}
  ]
}
~~~

đây là một phần mô tả **một step**, không phải toàn bộ response của Actuator. Nó gợi ý quá trình instantiation bean `pricingClient` đã được ghi nhận.

Nhưng đừng kết luận “duration của step này là thời gian **constructor riêng**” nếu nó còn bao gồm dependency resolution, factory calls, proxy creation hoặc các startup steps con. Để biết đoạn nào tốn thời gian thật, xem stack/JFR, các bước con và mã khởi tạo.

### Cảnh báo về thứ tự trong timeline

- `id` là identifier, **không phải số milliseconds**.
- Một step có thể bắt đầu trước nhưng kết thúc sau step khác.
- `timeline.events` không nên được hiểu mặc nhiên là một trace tuyến tính “step 1 làm xong mới chạy step 2”.
- Tổng duration của các steps có thể **lớn hơn** tổng thời gian startup vì các bước lồng nhau/đồng thời.
- Một bước được ghi nhận không bảo đảm rằng tất cả logic khởi tạo cùng tên được đo ở mọi nhánh runtime.

## 6. So sánh ba cách dùng ApplicationStartup

| Lựa chọn | Ở đâu | Dữ liệu thu được | Dùng khi |
| --- | --- | --- | --- |
| `ApplicationStartup.DEFAULT` | Spring Framework | Không có recording thực; no-op | Đa số ứng dụng bình thường, ưu tiên overhead thấp |
| `BufferingApplicationStartup(capacity)` | Spring Boot | Timeline steps, timestamps và durations trong memory buffer | Chẩn đoán nhanh, dùng `/actuator/startup` JSON |
| `FlightRecorderApplicationStartup` | Spring Framework | StartupStep trở thành JFR events | Điều tra sâu, tương quan class loading, allocations, GC và JVM events |

Không nên nói `BufferingApplicationStartup` là “metrics library thay thế Micrometer”, hoặc JFR là “endpoint Actuator mặc định”. Chúng có **đường lưu trữ/quan sát** khác nhau.

### DEFAULT: tại sao gần như không thấy gì?

~~~java
ApplicationStartup tracker = ApplicationStartup.DEFAULT;
StartupStep step = tracker.start("demo.noop");

step.tag("component", "example");
step.end();
~~~

Snippet Java 17 cần import hai interface. Logic chạy được nhưng **không có timeline được thu thập** bởi no-op implementation. Đây là hành vi có chủ đích để giảm overhead startup.

### Buffering: giới hạn capacity là quan trọng

~~~java
BufferingApplicationStartup tracker =
        new BufferingApplicationStartup(2048);
~~~

Constructor này khởi động việc ghi nhận. Theo Javadoc Spring Boot 3.5:

- Buffer có sức chứa hữu hạn.
- **Khi đầy, step mới không được record.**
- Đây **không phải ring buffer** tự xóa step cũ để giữ step mới.
- Có thể dùng `addFilter(Predicate<StartupStep>)` để chỉ giữ loại steps cần.
- Có thể dùng `getBufferedTimeline()` để lấy snapshot.
- Có thể dùng `drainBufferedTimeline()` để **lấy và rút steps khỏi buffer**.
- `startRecording()` không cần gọi ngay sau constructor; constructor đã gọi nội bộ. Gọi nó sau khi đã có steps có thể ném `IllegalStateException`.

`2048` là **ví dụ dung lượng**, không phải giá trị mặc định của mọi application. Ứng dụng có nhiều beans/configuration classes có thể tạo hơn số này. Nếu thấy timeline không có những bước cuối startup, kiểm tra capacity trước khi kết luận framework không instrument.

### FlightRecorder: khi cần biết cả JVM đang làm gì

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

Đây là snippet cần import `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup`, `SpringApplication` và class `MyApplication`. Muốn lấy recording, cần **bật Java Flight Recorder trong JVM** (ví dụ `-XX:StartFlightRecording=...`) và chạy workload phù hợp.

Khi dùng implementation này, endpoint `/actuator/startup` không tự cung cấp timeline buffer, vì endpoint của Boot yêu cầu `BufferingApplicationStartup`. Đó là khác biệt về architecture, không phải một sự cố Actuator.

## 7. Ví dụ Spring Boot hoàn chỉnh: custom StartupStep trong bean factory

Ví dụ sử dụng Spring Boot **3.5.16**, Java **17+**, Maven, Spring Web và Actuator. Chương trình có một bean `DataCatalog` khởi tạo với một khoảng trễ ngắn **chỉ để minh họa**, một controller cho phép xác minh bean, và cấu hình tracker từ `main`.

Cấu trúc thư mục:

~~~text
startup-steps-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/startupsteps/
    │   │   ├── StartupStepsApplication.java
    │   │   └── CatalogController.java
    │   └── resources/application.yaml
    └── test/java/com/example/startupsteps/
        └── BufferingApplicationStartupTest.java
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>startup-steps-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
~~~

### File src/main/resources/application.yaml

~~~yaml
spring:
  application:
    name: startup-steps-demo
  main:
    banner-mode: "off"

server:
  port: 18083

management:
  endpoints:
    web:
      exposure:
        include: health,startup
~~~

`management.endpoints.web.exposure.include` cho phép xem endpoint startup qua HTTP **trong môi trường lab**. Trong môi trường sản xuất cần giới hạn quyền truy cập nghiêm ngặt: tên beans, đường khởi tạo hoặc tags có thể tiết lộ cấu trúc nội bộ. Không expose endpoint startup công khai theo mặc định.

### File src/main/java/com/example/startupsteps/StartupStepsApplication.java

~~~java
package com.example.startupsteps;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

@SpringBootApplication
public class StartupStepsApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupStepsApplication.class);

        // Thay implementation trước app.run(...).
        if (Boolean.getBoolean("demo.startup.jfr")) {
            app.setApplicationStartup(
                    new FlightRecorderApplicationStartup());
        } else {
            app.setApplicationStartup(
                    new BufferingApplicationStartup(4096));
        }

        app.run(args);
    }

    @Bean
    DataCatalog dataCatalog(ApplicationStartup applicationStartup) {
        StartupStep step =
                applicationStartup.start("demo.catalog.prepare");

        step.tag("component", "dataCatalog");
        step.tag("strategy", "sample-bootstrap");

        try {
            // Chỉ phục vụ lab: tạo thời gian có thể quan sát.
            Thread.sleep(150);

            return new DataCatalog(List.of(
                    "alpha", "beta", "gamma"));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog setup interrupted", e);
        } finally {
            step.end();
        }
    }

    @Bean
    ApplicationRunner printCatalog(DataCatalog catalog) {
        return args -> System.out.println(
                "CATALOG_SIZE=" + catalog.items().size());
    }

    public record DataCatalog(List<String> items) {
    }
}
~~~

**Tại sao cách này có ý nghĩa?**

1. `main` cấu hình `ApplicationStartup` trước khi Boot tạo/phân tích context, để framework ghi nhận càng nhiều bước startup càng tốt.
2. System property `-Ddemo.startup.jfr=true`, nếu có, chọn JFR implementation. Không có property, ứng dụng sử dụng buffer và Actuator startup endpoint.
3. `@Bean dataCatalog(ApplicationStartup applicationStartup)` lấy tracker được Spring cung cấp, không tự tạo recorder mới trong bean.
4. Tên custom `demo.catalog.prepare` không đè lên namespace `spring.*`.
5. Hai tags có giá trị cố định, không chứa secret/high-cardinality data.
6. `Thread.sleep(150)` làm khoảng thời gian khởi tạo dễ nhìn trong lab. Không để sleep nhân tạo trong production.
7. Dùng `try/finally` để bảo đảm `step.end()` ngay cả khi initialization ném lỗi.
8. `ApplicationRunner` cần `DataCatalog` nên bean sẽ được tạo trước khi runner thực thi; nếu app bật lazy global, dependency này cũng có thể kéo bean tạo sớm. Đừng kết luận một custom step đã record vào trước-ready chỉ vì tên method, phải xem timeline.
9. Nested record `DataCatalog` là một Java 17 record bình thường, được trả về bởi `@Bean`.

### File src/main/java/com/example/startupsteps/CatalogController.java

~~~java
package com.example.startupsteps;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {
    private final StartupStepsApplication.DataCatalog catalog;

    public CatalogController(
            StartupStepsApplication.DataCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/catalog")
    public List<String> catalog() {
        return catalog.items();
    }
}
~~~

Controller giúp xác nhận bean đã được tạo. Request `/catalog` **không bắt buộc** sinh một startup step mới sau khi ứng dụng ready: `ApplicationStartup` dành cho startup instrumentation, không phải request tracing chung.

### Build và chạy

~~~bash
mvn -q test
mvn -q -DskipTests package
java -jar target/startup-steps-demo-0.0.1-SNAPSHOT.jar
~~~

Khi startup thành công, dòng do runner chủ động in là:

~~~text
CATALOG_SIZE=3
~~~

Boot có thể in log framework trước/sau dòng này; không coi nó là toàn bộ stdout.

Gọi API:

~~~bash
curl -fsS http://127.0.0.1:18083/catalog
~~~

JSON response dự kiến:

~~~json
["alpha","beta","gamma"]
~~~

Đây là response body của controller, không phải dữ liệu `/actuator/startup`. Startup duration/timestamp phụ thuộc phần cứng và JVM nên không gắn một số milliseconds cố định cho ví dụ.

## 8. Endpoint /actuator/startup: GET snapshot và POST drain

Khi có **Spring Boot Actuator**, web exposure phù hợp và `BufferingApplicationStartup`:

~~~bash
curl -fsS http://127.0.0.1:18083/actuator/startup
~~~

GET trả một JSON timeline, trong đó có thể tìm step tùy biến `demo.catalog.prepare`.

Một **mẫu cấu trúc rút gọn**:

~~~json
{
  "springBootVersion": "3.5.16",
  "timeline": {
    "startTime": "2026-01-01T00:00:00Z",
    "events": [
      {
        "startTime": "2026-01-01T00:00:01Z",
        "endTime": "2026-01-01T00:00:01.150Z",
        "duration": "PT0.150S",
        "startupStep": {
          "id": 21,
          "parentId": 12,
          "name": "demo.catalog.prepare",
          "tags": [
            {"key": "component", "value": "dataCatalog"},
            {"key": "strategy", "value": "sample-bootstrap"}
          ]
        }
      }
    ]
  }
}
~~~

**Đây không phải output chính xác của một lần chạy**: mọi timestamps, `id`, `parentId`, duration và số events trên là dữ liệu minh họa. Một startup thực có thể có hàng trăm bước và `parentId` có thể không hiện diện cho top-level step.

### Những trường cần hiểu

| Trường JSON | Kiểu/ý nghĩa |
| --- | --- |
| `springBootVersion` | Phiên bản Boot của ứng dụng |
| `timeline.startTime` | Mốc bắt đầu timeline |
| `timeline.events[]` | Các steps đã được record |
| `startTime`, `endTime` | Thời gian bắt đầu/kết thúc step |
| `duration` | Duration theo định dạng thời lượng ISO-8601, ví dụ `PT0.150S` |
| `startupStep.name` | Tên kỹ thuật của step |
| `startupStep.id` | ID trong timeline |
| `startupStep.parentId` | ID bước cha nếu có |
| `startupStep.tags[]` | Các key/value metadata |

`duration` không phải số giây dạng JSON number; nếu cần phân tích trong Java, dùng `java.time.Duration.parse(...)` hoặc parser tương đương.

### GET không rút dữ liệu khỏi buffer

~~~bash
curl -fsS -X GET \
  http://127.0.0.1:18083/actuator/startup \
  -o startup-before.json
~~~

GET là **snapshot**. Nó đọc timeline đã ghi và không chủ đích xóa các bước trong buffer.

### POST rút dữ liệu khỏi buffer

~~~bash
curl -fsS -X POST \
  http://127.0.0.1:18083/actuator/startup \
  -o startup-drained.json
~~~

POST trả timeline chứa steps đã record và **drain** chúng khỏi buffer. Sau POST, một GET kế tiếp có thể trả rất ít hoặc không có steps nếu không có step mới được ghi.

Điều này là **khác biệt về ngữ nghĩa**, không chỉ khác HTTP verb:
- GET phù hợp quan sát/đối chiếu nhiều lần;
- POST phù hợp thu gom dữ liệu rồi giải phóng buffer;
- Khi POST xong, không thể dựa vào một GET sau đó để tái lập toàn bộ dữ liệu đã drain, trừ khi bạn đã lưu response POST hoặc thực hiện startup lại.

Trong môi trường có nhiều công cụ quan sát, cần xác định **ai sở hữu việc drain**: hai consumer cùng POST có thể khiến consumer sau nhận dữ liệu trống. Đừng dùng POST chỉ để “xem thử” rồi bỏ response.

### Có thể phân tích bằng jq

Nếu đã cài `jq`:

~~~bash
# Đếm events trong snapshot
jq '.timeline.events | length' startup-before.json

# Tìm step custom và lấy duration + tags
jq '[.timeline.events[]
     | select(.startupStep.name == "demo.catalog.prepare")
     | {duration, startupStep}]' startup-before.json

# Liệt kê một số steps khởi tạo bean
jq '[.timeline.events[]
     | select(.startupStep.name == "spring.beans.instantiate")
     | {duration, startupStep}]' startup-before.json
~~~

Output phụ thuộc số events thực. Không nhất thiết một bean chỉ xuất hiện đúng một lần trong mọi thiết kế context/mode startup. Không nên dùng thứ tự JSON events làm mô hình nhân quả duy nhất.

## 9. Unit test cho BufferingApplicationStartup (không cần Spring context)

Có thể kiểm tra contract một cách độc lập bằng JUnit 5. File kiểm thử của project trên:

**`src/test/java/com/example/startupsteps/BufferingApplicationStartupTest.java`**

~~~java
package com.example.startupsteps;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;
import org.springframework.core.metrics.StartupStep;

import static org.junit.jupiter.api.Assertions.*;

class BufferingApplicationStartupTest {

    @Test
    void recordsACompletedStepAndKeepsSnapshot() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(8);

        StartupStep step = tracker.start("demo.test.prepare");
        step.tag("component", "test");
        step.end();

        StartupTimeline snapshot = tracker.getBufferedTimeline();
        assertEquals(1, snapshot.getEvents().size());
        assertEquals("demo.test.prepare",
                snapshot.getEvents().get(0)
                        .getStartupStep().getName());

        // Snapshot không làm mất nội dung buffer.
        assertEquals(1,
                tracker.getBufferedTimeline().getEvents().size());

        StartupTimeline drained = tracker.drainBufferedTimeline();
        assertEquals(1, drained.getEvents().size());

        assertTrue(tracker.getBufferedTimeline()
                .getEvents().isEmpty());
    }

    @Test
    void filtersStepsByName() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(8);

        tracker.addFilter(step ->
                step.getName().startsWith("demo."));

        tracker.start("internal.unwanted").end();

        StartupStep wanted = tracker.start("demo.useful");
        wanted.tag("category", "demo");
        wanted.end();

        StartupTimeline snapshot = tracker.getBufferedTimeline();
        assertEquals(1, snapshot.getEvents().size());
        assertEquals("demo.useful",
                snapshot.getEvents().get(0)
                        .getStartupStep().getName());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Hai tests minh họa:
- Step hoàn tất được ghi vào buffer và snapshot đọc không làm mất dữ liệu.
- Drain lấy và xóa các steps đã buffered.
- Filter theo tên loại bỏ steps không quan tâm.

Đây là **unit test implementation**, không khởi tạo `SpringApplication` thật. Nó không chứng minh các steps nội bộ như `spring.context.refresh` sẽ có mặt trong mọi dự án; muốn kiểm tra framework instrumentation, dùng integration test hoặc chạy JAR có config tracker.

**Lưu ý nhỏ:** nếu thêm filter, step không khớp các filters sẽ không được record; điều đó có thể làm timeline thiếu các bước cha cần để hiển thị một cây đầy đủ. Trong production, đừng tự động filter mạnh trước khi hiểu phụ thuộc parent-child của dữ liệu.

## 10. Phân tích đúng thời gian startup từ timeline

### Tại sao không cộng duration của mọi event?

Giả sử:
- `spring.context.refresh` dài 700 ms;
- trong đó `spring.beans.instantiate` của A dài 350 ms;
- trong A có một bước custom `demo.catalog.prepare` dài 150 ms.

Nếu cộng 700 + 350 + 150 = 1.200 ms, bạn **đếm lặp** thời gian lồng nhau. Các durations thường là inclusive elapsed time của từng khoảng, có thể chồng lấp. Tổng duration của events **không phải thời gian khởi động toàn process**.

~~~mermaid
gantt
  title Ví dụ minh họa các bước lồng nhau (không phải số đo thật)
  dateFormat X
  axisFormat %s
  section Context
  refresh : 0, 700
  section Bean
  instantiate A : 150, 500
  section Custom
  catalog.prepare : 200, 350
~~~

Lược đồ trên chỉ minh họa các khoảng thời gian chồng nhau. Khi xử lý dữ liệu thật, dùng start/end và parentId (khi có) để xây timeline hoặc flamegraph, tránh cộng thẳng duration các bước.

### Bốn con số không nên trộn

| Chỉ số | Mốc đo | Nơi thu |
| --- | --- | --- |
| `T_process_ready` | Spawn JVM → readiness probe trả khỏe | Script/monitor từ bên ngoài process |
| `T_main_ready` | Đầu `main` → `ApplicationReadyEvent` | Đồng hồ monotonic như `System.nanoTime()` |
| `T_context_refresh` | Khoảng context refresh được instrumented | `spring.context.refresh` step |
| `T_bean_creation` | Khoảng tạo bean theo step | `spring.beans.instantiate` hoặc custom step |

Một ứng dụng có thể tối ưu rất tốt context refresh nhưng vẫn mất thời gian ở:
- JVM startup trước khi `main` chạy;
- config/environment preparation;
- `ApplicationRunner`/`CommandLineRunner` sau context refresh;
- readiness propagation từ platform;
- request hoặc connection warm-up sau khi ready.

Do đó `ApplicationStartup` **không thay thế** đo end-to-end startup hoặc health readiness. Nó là công cụ lý giải **các bước đã được instrumented**.

### Top-N chậm nhất có ý nghĩa gì?

Có thể sort events theo duration để tìm những khoảng lớn. Nhưng một bước cha dài và nhiều bước con cùng dài không chứng minh nhiều bottleneck độc lập. Đọc từ parent xuống child:
1. Tìm phase có thời gian lớn.
2. Xem những con của phase đó.
3. So sánh các events cùng type ở các bean khác nhau.
4. Xác định phần thời gian không được chia thành step con.
5. Nếu cần, bật JFR CPU/allocation/I/O profiling để nhìn sâu hơn.

Nên lưu cả `startTime`/`endTime` và `parentId`, không chỉ duration.

### Khi nào dùng @Lazy hoặc chỉnh dependency graph?

Nếu `spring.beans.instantiate` chỉ ra một bean đắt đỏ, bước tiếp theo là tìm vì sao nó đắt: I/O trong constructor, khởi tạo connection pool, nạp cache, quét file, compile template, reflection/class loading hay một dependency chain sâu.

Bật `spring.main.lazy-initialization=true` có thể giảm một số steps trước ready bằng cách **dời chi phí sang lần sử dụng đầu tiên**. Không gọi đó là cải thiện tổng chi phí khi chưa đo first-hit latency, RSS/heap và tính đúng của startup validation. Nếu bean thiết yếu bị lỗi, lazy có thể chuyển exception từ startup sang runtime.

## 11. Khi cần JFR thay cho buffering endpoint

`FlightRecorderApplicationStartup` tạo Spring-specific startup events để JFR có thể tương quan với:
- CPU samples;
- class loading;
- Java allocations;
- garbage collection;
- thread scheduling và những sự kiện JVM khác.

Trong project ở mục 7, đặt JVM property **trước `-jar`** để chọn implementation JFR:

~~~bash
java -Ddemo.startup.jfr=true \
  -XX:StartFlightRecording=filename=boot-startup.jfr,settings=profile,dumponexit=true \
  -jar target/startup-steps-demo-0.0.1-SNAPSHOT.jar
~~~

Đây là chương trình web chạy dài; khi đã gọi `/catalog`, dừng bằng Ctrl+C hoặc tín hiệu shutdown có kiểm soát để JVM ghi file nếu recording được cấu hình `dumponexit=true`. Đừng dùng `kill -9` rồi kỳ vọng recording được flush bình thường.

Kiểm tra recording bằng JDK 17+:

~~~bash
jfr summary boot-startup.jfr
jfr metadata boot-startup.jfr
~~~

Để in các Spring StartupStep events, event name ở các bản Spring Framework 6.x có thể là:

~~~bash
jfr print \
  --events org.springframework.core.metrics.jfr.FlightRecorderStartupEvent \
  boot-startup.jfr
~~~

Nếu không thấy event, xác minh JFR được bật đúng, ứng dụng dùng `FlightRecorderApplicationStartup` và JFR file chứa startup window. Tên event cần đối chiếu với metadata của **đúng phiên bản Spring Framework**; không tự dựa vào một tên sự kiện ở phiên bản khác.

**Không trông đợi `GET /actuator/startup` hoạt động ở chế độ JFR**: endpoint đó cần buffer tracker chứ không trực tiếp đọc JFR recording.

### JFR hay Buffering tốt hơn?

- Muốn **JSON nhanh** để hiểu phase/bean names: buffer + actuator.
- Muốn tìm **allocation/GC/class loading** tương ứng với một startup step: JFR + Mission Control.
- Muốn đo **long-term latency, throughput, errors**: Micrometer/tracing/load test, không cố dùng startup tracker như một metrics backend chung.
- Muốn so sánh performance A/B: tránh bật JFR chỉ ở một nhánh nếu overhead của recording có thể gây lệch.

## 12. Theo dõi custom steps ngoài thời điểm startup

Mặc dù API tên là `ApplicationStartup`, code vẫn có thể gọi `start(...)` sau khi app ready nếu implementation còn tồn tại. Tuy nhiên:
- Semantics và công cụ của nó được thiết kế cho **startup và core-container initialization**.
- Buffer có giới hạn, không phải event store dài hạn.
- Actuator startup timeline không phải một kho mọi request/job bất kỳ.
- Các steps tạo sau ready có thể gây nhiễu khi phân tích hiệu năng khởi động.

Với request tracing, sử dụng Observation API/Micrometer tracing/OpenTelemetry. Với metrics latency lặp lại theo thời gian, dùng `Timer`/distribution metrics phù hợp, không biến `StartupStep` thành giải pháp chung cho mọi phần mềm runtime.

## 13. Capacity, filter, drain và các tác động vận hành

### Capacity quá thấp

Giả sử recorder có capacity 100 nhưng framework tạo 500 steps. Theo Javadoc, sau khi buffer đầy, **new steps không được record**. Timeline được thấy chỉ là tập đã kịp giữ lại trong hạn mức (cộng tác động filters), không được diễn giải là toàn bộ startup.

Cách xử lý:
1. Tăng capacity có kiểm soát, ví dụ từ 512 lên 4096.
2. Đọc các loại step gây nhiều bản ghi nhất.
3. Dùng filter theo tên khi biết rõ mục tiêu điều tra.
4. Drain dữ liệu sang kho phù hợp trước khi buffer đầy nếu có cơ chế thu gom đáng tin.
5. Đo memory/overhead khi tăng capacity, không dùng một số vô hạn.

### Đừng gọi startRecording() sai lúc

`BufferingApplicationStartup` constructor đã tự bắt đầu recording. Gọi `startRecording()` lại sau khi steps đã ghi có thể ném `IllegalStateException`. API này không phải “nút reset bất kỳ lúc nào” để đo lại từ đầu cùng application instance.

### GET và POST có rủi ro cạnh tranh

Nếu một monitoring agent `POST /actuator/startup` để drain, một developer GET sau đó có thể tưởng startup không có steps. Không có quyền sở hữu dữ liệu cố định cho mỗi HTTP client. Hãy thiết kế một đường thu thập chủ đạo, lưu response, và dùng GET để quan sát khi chưa cần drain.

### Khi app startup lỗi trước khi endpoint mở

Nếu context fail trong refresh hoặc web server chưa listen, `/actuator/startup` có thể **không bao giờ khả dụng**. Đây là một giới hạn quan trọng: buffer được giữ trong process có thể biến mất khi process kết thúc.

Để điều tra failure rất sớm:
- đọc stack trace, `Caused by` và `FailureAnalyzer`;
- dùng JFR recording được bật từ lúc JVM khởi chạy, nếu JVM đi qua đường dump recording thích hợp;
- quan sát logs/events/exit code, không trông đợi một endpoint HTTP từ app chưa startup xong.

### Lưu dữ liệu có trách nhiệm

Startup tags có thể chứa tên bean, package, class, tham số hoặc các giá trị do chính bạn thêm. Hạn chế:
- public exposure của Actuator startup;
- log raw tags chứa secrets/PII;
- retention quá dài ở hệ thống chẩn đoán;
- tự động gửi full startup graph ra hệ thống không được phê duyệt.

Chỉ thêm metadata đủ để đối chiếu lý do chậm; không cần dump toàn bộ configuration properties.

## 14. Các tình huống debug thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xác minh |
| --- | --- | --- |
| `/actuator/startup` trả 404 | Chưa có Actuator, chưa expose, endpoint bị hạn chế access, không dùng buffer | Kiểm tra dependency, startup tracker, exposure và security |
| JSON không có events hữu ích | Mặc định no-op hoặc đã POST drain | Bật `BufferingApplicationStartup` trước run, xem GET trước POST |
| Không có bước cuối startup | Buffer capacity đầy | Tăng capacity hoặc filter có chủ đích |
| POST đầu trả events, POST sau rỗng | Drain đã lấy ra và xóa buffer | Lưu response từ lần POST đầu |
| Bean tên X có duration dài | Có thể bao gồm dependency init | Xem parent-child, child steps và JFR |
| Không thấy custom step | Chưa gọi code, gọi `end()` thiếu, buffer đầy, filter loại bỏ | Kiểm tra control flow và test |
| Filter làm mất nhiều bước | Predicate quá chặt | Đo lại không filter hoặc filter bớt chặt |
| JFR file không có Spring events | Tracker chưa là JFR, recording không bao phủ startup | Đặt `setApplicationStartup` trước run, bật JFR trước main |
| Bật JFR nhưng actuator startup 404 | Actuator endpoint cần Buffering tracker | Dùng JFR viewer hoặc chuyển sang buffer trong lượt đo khác |
| Lấy tổng duration quá lớn | Các events lồng nhau/chồng nhau | Phân tích timeline và parentId |
| Startup step rất nhanh nhưng ready chậm | Runner, JVM bootstrap, readiness propagation, code chưa instrumented | Đo thêm process→ready và main→ready |
| Thấy ID đổi giữa deploy | IDs chỉ có ý nghĩa trong từng timeline | So theo name/tags, không so raw ID |
| Tăng buffer làm startup chậm thêm | Tracking overhead/GC hoặc môi trường nhiễu | Benchmark có đối chứng, giữ cùng cấu hình |
| API có `spring.*` names khác tài liệu | Bản Spring Framework khác | Đối chiếu appendix của đúng version |
| Dùng startup tracker để đo mọi request | Sai công cụ/semantics | Dùng Micrometer Observation/Timer/traces |

### Vì sao startup event không giống application event?

`ApplicationStartedEvent` / `ApplicationReadyEvent` là **SpringApplication events** trong startup lifecycle. `StartupStep` là bản ghi một khoảng đo. Một step có thể bao quanh việc xử lý event, nhưng không phải chính đối tượng event. Không cố `@EventListener(StartupStep.class)` rồi kỳ vọng Spring publish từng step như application event.

### Vì sao /actuator/startup không phải readiness?

`/actuator/health/readiness` phản ánh trạng thái phục vụ. `/actuator/startup` trả các bước đã ghi. Một app có thể có đầy đủ `StartupStep` mà đang REFUSING_TRAFFIC, hoặc đã ready nhưng buffer không bật. Hai endpoint có nhiệm vụ khác nhau.

## 15. Quy trình đánh giá thời gian khởi động thực tế

1. **Chốt mục tiêu:** cần rút process→ready, main→ready, context refresh hay first request?
2. **Ghi môi trường:** JDK vendor/version, Spring Boot/Framework version, JAR digest, JVM flags, profiles, CPU/memory limits, storage/DB endpoints.
3. **Bật tracker sớm:** `setApplicationStartup(new BufferingApplicationStartup(capacity))` **trước** `run(args)`.
4. **Chạy ứng dụng sạch:** cùng artifact, cùng profiles, cùng external services; không so IDE hot restart với clean process.
5. **Thu timeline GET:** lưu JSON ngay sau khi ready, tránh POST trước khi lưu data.
6. **Phân nhóm steps:** framework phases, bean instantiation, custom startup steps, parent/child.
7. **Tìm vùng thời gian lớn:** sort duration có chú ý lồng nhau, đối chiếu source code/config.
8. **Nếu chưa rõ:** ghi JFR trong một lượt chẩn đoán riêng để xem allocations/GC/class loading.
9. **Sửa một biến có chủ đích:** ví dụ bỏ I/O từ constructor, sửa eager dependency, giảm scan scope, cải tiến cache warm-up.
10. **Chạy lại nhiều process:** xen kẽ baseline/variant, so median/p95, không dùng một lần khởi động.
11. **Đo cả phía bên ngoài JVM:** readiness probe, first-hit latency và resource footprint.
12. **Kiểm tra correctness:** bean fail-fast, datasource, scheduler, message listener, config validation phải vẫn đúng.
13. **Báo cáo tên bước, before/after duration, môi trường và trade-off**, không chỉ một con số “nhanh hơn 30%” thiếu căn cứ.

### Mẫu kết luận benchmark (chưa có số liệu thật)

~~~text
Artifact / image digest: <ghi từ môi trường>
JDK / Spring Boot / Spring Framework: <version thật>
Tracking implementation: BufferingApplicationStartup(4096)
Recorded steps: <số từ timeline>
Missing due capacity/filter: <đánh giá>
Main-to-ready median: <đo>
External process-to-readiness median: <đo>
Top slow parent steps: <name + measured duration>
Relevant child steps: <name + measured duration>
Change tested: <cấu hình hoặc code cụ thể>
Cold first-hit / warm p95 / error rate: <đo>
RSS / heap / CPU: <đo>
Conclusion and rollback plan: <dựa trên số liệu>
~~~

Các cụm trong dấu góc là **nhãn chờ số đo**, không phải kết quả giả định. Cần lưu số thực khi thực nghiệm.

## 16. Câu hỏi tự kiểm tra

**1. `ApplicationStartup` có phải là một Spring event không?**  
Không. Đây là SPI instrumentation cho các startup steps.

**2. `ApplicationStartup.DEFAULT` có thu timeline mặc định không?**  
Không, nó là no-op.

**3. `StartupStep.start(...)` được gọi trên interface nào?**  
`ApplicationStartup.start(String name)` trả về một `StartupStep`.

**4. Vì sao phải gọi `step.end()` trong finally?**  
Để hoàn tất recording ngay cả khi logic khởi tạo ném exception.

**5. ID và parentId có dùng làm khóa bền vững giữa hai lần startup không?**  
Không. Chúng phục vụ timeline của lần ghi nhận cụ thể.

**6. Vì sao không tạo step custom tên `spring.my-feature`?**  
Namespace `spring.*` dành cho framework nội bộ; nên dùng namespace riêng như `demo.*`.

**7. Tại sao ApplicationStartup cần được cấu hình trước run()?**  
Để ghi nhận các bước xảy ra trong quá trình SpringApplication/context startup, không chỉ các bước sau khi app đã ready.

**8. BufferingApplicationStartup đầy có tự xóa step cũ không?**  
Không. Khi đạt capacity, các step mới không được record.

**9. GET /actuator/startup và POST khác nhau như thế nào?**  
GET đọc snapshot; POST trả dữ liệu và drain buffer.

**10. Gọi POST hai lần liên tiếp có chắc cả hai trả cùng events không?**  
Không. Lần sau có thể chỉ còn những events phát sinh sau lần drain trước.

**11. Chỉ có Actuator dependency là đủ để có startup timeline không?**  
Không. Cần tracker phù hợp, web exposure và access hợp lệ.

**12. FlightRecorderApplicationStartup có dùng /actuator/startup thay cho JFR không?**  
Không. Nó ghi events vào JFR recording; endpoint startup dùng buffer tracker.

**13. Vì sao duration của các steps không được cộng thẳng?**  
Vì các khoảng có thể lồng nhau, chồng nhau và còn phần việc không được instrumented.

**14. Khi context khởi động lỗi trước khi mở HTTP, endpoint startup có đọc được không?**  
Có thể không. Dùng logs/FailureAnalyzer và JFR/diagnostics chạy từ đầu process.

**15. Có nên gắn access token vào tag để nhận diện bước?**  
Không. Startup data có thể hiện ra qua HTTP/JFR/logs.

**16. Khi thấy bean init chậm, có nên bật lazy cho toàn hệ thống ngay không?**  
Không. Lazy có thể dời chi phí và lỗi sang first request; đo thêm readiness/cold-hit/heap và kiểm tra đúng nghiệp vụ.

## 17. Tài liệu chính thức

- [Spring Boot 3.5 — SpringApplication: Application Startup Tracking](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): cách cấu hình buffering và JFR trackers.
- [Spring Boot 3.5 — Actuator Startup REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html): GET snapshot, POST drain, response fields.
- [Spring Boot 3.5 — BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html): capacity, filters, getBufferedTimeline, drainBufferedTimeline.
- [Spring Boot 3.5 — StartupTimeline API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/StartupTimeline.html): TimelineEvent, getEvents, getStartTime.
- [Spring Boot 3.5 — Actuator Endpoint Exposure](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): startup endpoint yêu cầu Buffering tracker và chính sách exposure.
- [Spring Framework 6.2 — ApplicationStartup Reference](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): instrumentation của context và nguyên tắc namespace custom.
- [Spring Framework 6.2 — StartupStep API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/metrics/StartupStep.html): getId, parentId, tags, end.
- [Spring Framework 6.2 — Application Startup Steps Appendix](https://docs.spring.io/spring-framework/reference/6.2/core/appendix/application-startup-steps.html): các step nội bộ, tên/tag không phải contract bất biến.
- [Spring Framework 6.2 — FlightRecorderApplicationStartup API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html): Spring startup data trong JFR.
- [Oracle JDK 17 — jfr Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): summary, print, metadata và đọc recording.

**Kết luận:** `ApplicationStartup` và `StartupStep` giúp trả lời chính xác hơn câu hỏi **“Spring khởi động chậm ở bước nào?”**. Chọn `BufferingApplicationStartup` để lấy JSON nhanh từ Actuator, `FlightRecorderApplicationStartup` để phân tích chi tiết cùng sự kiện JVM; đặt tracker trước `run`, gọi `end` đúng thời điểm, hiểu parent-child và giới hạn buffer. Chỉ coi đó là một phần của phép đo: **end-to-end readiness, first-hit latency, lỗi và resource usage** vẫn cần được đánh giá riêng.