# Liên hệ dữ liệu đo khởi động với Actuator startup khi cấu hình phù hợp

## 1. Đo startup: không chỉ hỏi ứng dụng khởi động mất mấy giây

Trong một ứng dụng Spring Boot, thời gian khởi động có thể dành cho nhiều việc khác nhau: chuẩn bị `Environment`, tải bean definitions, chạy `BeanFactoryPostProcessor`, tạo singleton, khởi tạo embedded web server, khởi động kết nối đến hệ thống ngoài, chạy `ApplicationRunner` và công bố trạng thái sẵn sàng nhận traffic.

Một dòng log như:

```text
Started MyApplication in 4.572 seconds (process running for 5.221)
```

cho biết **một phép đo tổng quan của Spring Boot** (các số chỉ minh họa). Nó không tự chỉ ra bean nào tốn thời gian, bước nào chạy lồng nhau hoặc vì sao thời gian đến trạng thái ready dài hơn. Khi cần chẩn đoán chi tiết, Spring Framework cung cấp `ApplicationStartup` và các `StartupStep`; Spring Boot 3.3 có `BufferingApplicationStartup` và Actuator endpoint `/actuator/startup` để truy xuất những bước được ghi vào bộ đệm **nếu đã cấu hình phù hợp trước khi chạy ứng dụng**.

Cần tách ba lớp:

1. **Thời gian tổng thể**: log “Started ... in ...”, `ApplicationStartedEvent` và `ApplicationReadyEvent`, cũng như các metric tổng thể `application.started.time`/`application.ready.time` khi có Actuator/Micrometer.
2. **Dữ liệu bước khởi động**: `ApplicationStartup` tạo `StartupStep` có tên, id, parent id, tags và khoảng thời gian xử lý.
3. **Kênh lấy dữ liệu**: `/actuator/startup` hiển thị timeline JSON khi dùng `BufferingApplicationStartup`, thêm dependency Actuator và expose endpoint phù hợp.

Bài học áp dụng cho **Spring Boot 3.3.x, Spring Framework 6.1.x và Java 17+**. Mục tiêu không chỉ là bật một URL mà còn **liên hệ đúng dữ liệu**: biết mỗi bước được đo trong giai đoạn nào, không cộng sai durations lồng nhau, phân biệt startup steps với metrics tổng hợp, và không biến endpoint chẩn đoán thành lỗ hổng bảo mật.

## 2. Startup time, started time và ready time khác nhau thế nào?

Trong một lần chạy tiêu chuẩn, Spring Boot có các mốc chính:

```text
main()
    |
SpringApplication.run(args)
    |
Chuẩn bị Environment và ApplicationContext
    |
ApplicationContext.refresh()
    |
ApplicationStartedEvent
    |
LivenessState.CORRECT
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
    |
SpringApplication.run() trả về context
    |
Instance tiếp tục phục vụ traffic
```

**Started** và **ready** không phải một mốc:

- `ApplicationStartedEvent` được phát sau context refresh, **trước** các `ApplicationRunner`/`CommandLineRunner`.
- `ApplicationReadyEvent` được phát sau các runner và trước khi Boot công bố readiness accepting trong trình tự availability mặc định.
- Thời gian đến ready có thể bao gồm các bước trong runner mà log “Started ...” không đại diện cho toàn bộ.
- Một runner chạy công việc bắt buộc trong 10 giây có thể làm ready chậm, dù phần context refresh không thay đổi nhiều.

### 2.1. Hai metric tổng thể trong Actuator

Spring Boot Actuator 3.3 có **application startup time metrics**:

| Metric | Ý nghĩa |
| --- | --- |
| `application.started.time` | Thời gian đến mốc ứng dụng đã started |
| `application.ready.time` | Thời gian đến mốc ứng dụng sẵn sàng phục vụ request theo lifecycle của Boot |

Các metric được gắn tag bằng tên đầy đủ của application class. Khi metrics endpoint được bật/expose, có thể xem:

```text
GET /actuator/metrics/application.started.time
GET /actuator/metrics/application.ready.time
```

Đây **không phải** hai URL con của `/actuator/startup`. Chúng dùng hệ thống metric Micrometer, có thể được xuất sang registry như Prometheus tùy dependency/config. `/actuator/startup` thì cung cấp **timeline bước** để chẩn đoán thành phần gây trễ.

### 2.2. Dòng log “process running for” còn có phạm vi khác

Cụm “process running for ...” trong log tính thêm phần runtime của JVM/process trước thời điểm Boot ghi log, do đó có thể khác con số “Started ... in ...”. Không lấy hiệu hai số bất kỳ trong log để khẳng định khoảng chênh lệch là thời gian khởi tạo bean.

Khi so sánh các phiên bản, cần chọn **cùng một loại metric**, cùng cách launch, môi trường và điều kiện tải. Một log tổng, một startup step và một Java Flight Recorder event có thể đo những khoảng thời gian khác nhau.

## 3. ApplicationStartup là gì?

`org.springframework.core.metrics.ApplicationStartup` là abstraction của Spring Framework để ghi nhận **các giai đoạn/thao tác** trong quá trình startup. Mỗi lời gọi `start(String name)` tạo một `StartupStep`. Step có thể thêm metadata dạng tags rồi được đánh dấu kết thúc bằng `end()`.

Mô hình:

```text
ApplicationStartup
    |
    +-- StartupStep: spring.boot.application.starting
    |       id=...
    |       start -> end
    |
    +-- StartupStep: spring.context.refresh
    |       id=...
    |       +-- StartupStep: spring.beans.instantiate
    |       |       tags: beanName=...
    |       +-- ...
    |
    +-- StartupStep: app.demo.warmup
            tags: phase=runner
            start -> end
```

Tên thực tế và quan hệ step tùy implementation, framework version và đoạn code nào đã được instrument. Sơ đồ này nhằm giải thích dạng dữ liệu, **không phải cam kết mọi step có tên và cấu trúc đúng như sơ đồ**.

### 3.1. Các thành phần của StartupStep

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên thao tác, ví dụ `spring.beans.instantiate` |
| `id` | Mã nhận diện một step trong lần ghi hiện tại |
| `parentId` | Mã step cha khi có quan hệ lồng nhau; có thể vắng mặt |
| `tags` | Key/value metadata, ví dụ `beanName=homeController` |
| `startTime` | Thời điểm bắt đầu step trong timeline |
| `endTime` | Thời điểm kết thúc step |
| `duration` | Khoảng kéo dài của step, thường biểu diễn ISO-8601 Duration |

Ba trường cuối thuộc bản ghi **timeline event** mà implementation buffering thu thập, không phải tất cả đều là method trực tiếp trên interface `StartupStep`.

### 3.2. Default ApplicationStartup không có trace hữu ích

Spring Framework định nghĩa `ApplicationStartup.DEFAULT` là một implementation **no-op**, nhằm giảm overhead khi không cần phân tích startup. Không nên giả định Spring Boot tự giữ một timeline chi tiết cho mọi phiên chạy.

Muốn truy xuất JSON với endpoint `startup`, phải đăng ký `BufferingApplicationStartup` từ lúc xây dựng `SpringApplication`, trước khi gọi `run(...)`. Bật Actuator sau khi startup xong không thể tạo lại các bước chưa từng được ghi.

### 3.3. ApplicationStartup khác @Timed và profiler

`StartupStep` mô tả những điểm đo mà framework hoặc code đã chủ động đánh dấu. Nó **không phải profiler toàn CPU/heap/thời gian I/O**. Nếu một đoạn code không được instrument thành step riêng, timeline không thể tự suy đoán chính xác chi phí của đoạn đó.

Đối với CPU, allocation, GC, classloading, lock contention và stack traces, Java Flight Recorder (JFR) hoặc profiler riêng có thể phù hợp hơn. Dữ liệu startup steps và JFR bổ trợ nhau, không thay thế hoàn toàn nhau.

## 4. Vì sao chọn BufferingApplicationStartup cho Actuator startup?

Spring Boot cung cấp `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`. Implementation này giữ lại các bước startup trong **bộ đệm có sức chứa hữu hạn** để có thể xuất ra một timeline.

Bật bằng Java **trước `run`**:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.setApplicationStartup(
        new BufferingApplicationStartup(2048));

app.run(args);
```

Đoạn này là snippet bên trong `main`, cần class `MyApplication` và imports `SpringApplication`, `BufferingApplicationStartup`. `2048` là **sức chứa số bước** cho buffer, không phải thời gian tính bằng millisecond và không phải memory size tính bằng byte.

### 4.1. Buffer có giới hạn

Theo JavaDoc Boot 3.3:

- Buffer ghi các bước đến khi đạt **capacity**.
- Khi capacity đầy, những step mới có thể **không được ghi**.
- Có thể thêm filter `addFilter(...)` để chỉ thu thập bước cần thiết.
- Có thể lấy snapshot bằng `getBufferedTimeline()`.
- Có thể rút các events ra bằng `drainBufferedTimeline()`.

**Hệ quả quan trọng:** nếu bạn thấy thiếu một step của bean hoặc runner, không nên kết luận “step đó không tồn tại” khi buffer có thể đã đầy trước lúc step được tạo. Tăng capacity có chủ đích, lọc phù hợp hoặc thay đổi chiến lược thu thập.

### 4.2. Không đổi applicationStartup sau khi startup xong để tìm lại lịch sử

Nếu bạn tạo `BufferingApplicationStartup` sau `SpringApplication.run(...)` và chỉ gán vào một bean tùy ý, những bước đã đi qua **không được ghi hồi tố**. Tương tự, chỉ cài Actuator nhưng không gọi `setApplicationStartup(...)` trước `run(...)` sẽ không làm endpoint có đầy đủ các bước.

**Bắt đầu đo trước điều bạn cần đo** là nguyên tắc bất di bất dịch với startup tracing.

## 5. Điều kiện để /actuator/startup tồn tại và có dữ liệu

Với **Spring Boot 3.3**, một ứng dụng HTTP muốn dùng `/actuator/startup` cần đáp ứng những điều kiện sau:

1. Ứng dụng có dependency **`spring-boot-starter-actuator`**.
2. `SpringApplication` đã được cấu hình bằng **`BufferingApplicationStartup`** trước `run`.
3. Endpoint `startup` **được enable** theo Spring Boot Actuator configuration.
4. Endpoint `startup` **được expose qua HTTP** nếu muốn gọi bằng `curl`.
5. HTTP server, management port, base path và Spring Security/network policy cho phép request thực sự truy cập endpoint.

Trong Boot 3.3, đa số endpoints được **enable** mặc định trừ `shutdown`, nhưng mặc định chỉ **`health` được expose qua HTTP**. Vì vậy **enabled và exposed là hai khái niệm khác nhau**.

### 5.1. Cấu hình exposure tối thiểu

```properties
# Có Actuator dependency và BufferingApplicationStartup ở main.
management.endpoints.web.exposure.include=health,startup,metrics
```

Khi muốn explicit rằng startup endpoint enabled:

```properties
management.endpoint.startup.enabled=true
```

Dòng thứ hai thường không cần khi giữ enablement mặc định, nhưng hữu ích nếu ứng dụng đã cấu hình enablement theo kiểu opt-in.

**Không dùng**:

```properties
management.endpoints.web.exposure.include=*
```

một cách tùy tiện cho môi trường production. `*` sẽ expose nhiều endpoints mang thông tin nội bộ; một số còn có write operations. Ưu tiên danh sách nhỏ, firewall và authentication/authorization.

### 5.2. Nếu dùng management port riêng

Nếu bạn đặt:

```properties
management.server.port=9090
management.endpoints.web.base-path=/actuator
```

thì endpoint thường ở `http://host:9090/actuator/startup`, không phải port 8080. Nếu đổi base path hoặc thêm context path, đường URL cần được tính theo cấu hình thực tế. Không suy luận 404 trên `localhost:8080` nghĩa buffer bị hỏng nếu management server đang ở port khác.

### 5.3. Bảo mật phải được thiết kế trước khi expose

`startup` có thể đưa ra:

- Tên các beans và loại subsystem.
- Tên application class.
- Cấu trúc bước startup.
- Tags do framework hoặc app gắn.
- Dấu thời gian, duration và quan hệ giữa các bước.

Những thông tin đó có thể hữu ích cho một người tấn công trong việc hiểu cấu trúc ứng dụng. Nếu custom step vô tình gắn API key hoặc user identifier vào tag, rủi ro càng lớn.

**Chỉ expose endpoint cho người vận hành được phép**, ưu tiên môi trường nội bộ và giới hạn network. Nếu có Spring Security nhưng bạn tự định nghĩa `SecurityFilterChain`, phải chủ động bảo vệ Actuator; đừng mặc định auto-security vẫn giúp khi đã override cấu hình.

## 6. GET và POST của Actuator startup: khác nhau về tác dụng phụ

Theo Spring Boot 3.3 Actuator REST API, `/actuator/startup` hỗ trợ:

| Phương thức | Tác dụng | Có thay đổi buffer không? |
| --- | --- | --- |
| `GET /actuator/startup` | Lấy **snapshot** các steps đang được giữ trong buffer | **Không rút** dữ liệu ra |
| `POST /actuator/startup` | **Drain**: lấy các steps đang có và đồng thời bỏ chúng khỏi buffer | **Có**, làm dữ liệu không còn trong buffer hiện tại |

Ví dụ:

```bash
curl -i http://127.0.0.1:8080/actuator/startup
```

Lệnh trên là **GET** mặc định. Muốn drain:

```bash
curl -i -X POST http://127.0.0.1:8080/actuator/startup
```

**Cảnh báo:** `POST` không phải một cách “đọc tương đương GET”. Nếu một collector đã POST và drain, một GET tiếp theo có thể trả ít events hoặc trống. Không tự gọi POST nhiều lần trên một instance rồi khẳng định dữ liệu startup bị mất bí ẩn.

### 6.1. Quy trình an toàn khi cần giữ dữ liệu

1. Dùng `GET` để quan sát/kiểm tra đầu tiên.
2. Lưu snapshot vào một nơi có quyền truy cập thích hợp nếu cần phân tích.
3. Chỉ dùng `POST` khi muốn **bàn giao rồi xóa buffer**, đã xác định collector/owner và chiến lược lưu trữ.
4. Nếu automation thu thập nhiều lần, kiểm soát duplicate events và drain ordering.
5. Nếu GET sau POST cho thấy không có events, kiểm tra lịch sử POST trước khi tăng capacity.

Với ứng dụng có Spring Security, `POST` còn có thể bị chặn bởi **authorization hoặc CSRF policy**. Không tắt CSRF cho tất cả endpoints chỉ để tiện dùng một lệnh `curl`; thiết kế policy theo API và deployment.

### 6.2. POST không đồng nghĩa tắt instrumentation

Drain loại events đã có khỏi buffer, không phải sửa toàn bộ cấu hình `ApplicationStartup`. Những steps mới có thể tiếp tục được ghi nếu hệ thống còn thu thập theo implementation/capacity. Tuy nhiên mục tiêu của endpoint là **startup sequence**, không phải stream vô hạn mọi HTTP request; đừng dùng nó để thay thế metrics/traces runtime.

## 7. Đọc cấu trúc JSON của /actuator/startup

Actuator REST API 3.3 mô tả response có `springBootVersion` và `timeline`. Trong timeline:

```json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2025-06-19T07:16:19.477Z",
    "events": [
      {
        "startTime": "2025-06-19T07:16:19.875Z",
        "endTime": "2025-06-19T07:16:19.878Z",
        "duration": "PT0.003S",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 3,
          "parentId": 2,
          "tags": [
            { "key": "beanName", "value": "catalogService" }
          ]
        }
      }
    ]
  }
}
```

**Đây là JSON minh họa cấu trúc, không phải kết quả chính xác của một ứng dụng cụ thể.** Các timestamps, durations, step ids và tags trong lần chạy thực sẽ khác. Không phải mọi step đều có `parentId` hoặc tags.

### 7.1. Ý nghĩa từng trường

| JSON path | Cách hiểu |
| --- | --- |
| `springBootVersion` | Phiên bản Spring Boot của instance trả dữ liệu |
| `timeline.startTime` | Điểm bắt đầu của timeline |
| `timeline.events` | Danh sách các bước đã ghi trong buffer |
| `events[].startTime` | Thời điểm bước bắt đầu |
| `events[].endTime` | Thời điểm bước kết thúc |
| `events[].duration` | Thời lượng step theo cú pháp Duration, ví dụ `PT0.003S` |
| `events[].startupStep.name` | Tên step |
| `events[].startupStep.id` | ID step trong timeline |
| `events[].startupStep.parentId` | ID step cha, khi tồn tại |
| `events[].startupStep.tags` | Dữ liệu key/value bổ sung |

Ví dụ `PT0.003S` nghĩa **3 milliseconds** theo ISO-8601 Duration. `PT1.25S` nghĩa 1,25 giây. Không coi đây là Unix timestamp hoặc nanosecond count. Với Java có thể dùng `java.time.Duration.parse(...)` để parse dạng chuỗi này.

### 7.2. Dùng ID để dựng cây, không dùng thứ tự mảng làm hierarchy

Nếu một step có `parentId=2`, nó thuộc phạm vi step có `id=2`. Từ đó có thể dựng graph/cây, tìm parent-child relationships và hiểu khoảng thời gian nào nằm trong một phase lớn.

Thứ tự phần tử trong `timeline.events` **không phải hợp đồng đảm bảo rằng phần tử trước luôn là parent**. Hãy nối bằng `id` và `parentId`. Một số steps không có parent, và buffer đầy/filter có thể khiến không có đủ mọi bước để dựng cây đầy đủ.

### 7.3. Tags giúp khoanh vùng bean nhưng không đo toàn bộ nghiệp vụ

Ví dụ `spring.beans.instantiate` với `beanName=priceCalculator` có thể giúp tìm bean được tạo trong quá trình startup và duration của bước tương ứng.

Nhưng cần xét:

- Bean đó có callback `@PostConstruct`, constructor hoặc dependency graph bên dưới?
- Nó có thật sự là nguyên nhân chính hay chỉ bao trùm các child steps?
- Một phần việc có thể đã chạy trong auto-configuration trước đó.
- Các dependencies ngoài DB/API có thể chậm nhưng không có step riêng.
- Nếu một bean `@Lazy` chưa được tạo lúc startup, nó có thể không xuất hiện trong timeline.

Tags là gợi ý để điều tra, **không phải một profiler đầy đủ**.

## 8. Sai lầm lớn: cộng tất cả duration của events

Nhiều `StartupStep` có thể **lồng nhau hoặc chồng lắp thời gian**:

```text
Context refresh                     [---------------------- 500 ms]
  BeanFactory setup                  [---- 120 ms]
  Instantiate Bean A                      [------ 200 ms]
    Instantiate dependency B              [--- 80 ms]
  Instantiate Bean C                              [-- 40 ms]
```

Nếu cộng `500 + 120 + 200 + 80 + 40 = 940 ms` rồi nói context refresh mất 940 ms, bạn đã **đếm nhiều lần thời gian bên trong các parent steps**. Một nested step thường là thành phần thời gian của step cha.

Quy tắc phân tích:

1. Sử dụng `startTime`/`endTime` để tính khoảng thực tế của phase.
2. Dùng `parentId` xây quan hệ.
3. Phân biệt **inclusive duration** của parent với khoảng riêng của child.
4. Nếu muốn exclusive time, cần tính union khoảng thời gian child trực tiếp một cách chính xác, xử lý overlap; không đơn giản trừ tổng duration khi có concurrency.
5. So sánh những lần chạy có **cùng version/config/environment**.

**Không có một hàm cộng durations đơn giản** nào cho ra chính xác end-to-end startup time của mọi ứng dụng.

### 8.1. “Top 10 slow steps” hữu ích nhưng không đủ

Sắp các steps theo duration có thể giúp phát hiện:

- Một bean tốn nhiều thời gian tạo.
- Context refresh bị chậm.
- Một custom warm-up step dài bất thường.

Nhưng một top-level step dài có thể là **parent bao trùm** nhiều child steps. Cần mở rộng descendants trước khi thay đổi cấu hình. Hãy kiểm tra critical path và tổng thời gian đến ready; không chỉ tối ưu một step mà không ảnh hưởng mốc ready.

### 8.2. Step không xuất hiện không đồng nghĩa công việc không chạy

Có thể vì:

- `ApplicationStartup` đang là no-op.
- `BufferingApplicationStartup` được đăng ký quá muộn.
- Buffer đã đầy trước khi step phát sinh.
- Filter loại step.
- Một collector đã POST/drain.
- Công việc không được instrument.
- Bean lazy chỉ được tạo khi nhận request sau startup.
- Bạn truy vấn nhầm instance/pod/management port.

Dùng checklist này trước khi kết luận một phần lifecycle đã bị bỏ qua.

## 9. Ví dụ Java 17+ hoàn chỉnh: Actuator startup và một bước đo riêng

Ví dụ chạy **Spring Boot 3.3.13 + Java 17**, có server HTTP ở localhost, Actuator và `BufferingApplicationStartup` được cấu hình **trước `run`**. Một `ApplicationRunner` tạo custom `StartupStep` tên `app.demo.warmup`; một controller có `GET /demo/ping`.

**Hành vi cần quan sát:**

- Boot tự ghi các framework startup steps.
- Runner ghi thêm một step có tag `phase=runner`.
- `GET /actuator/startup` trả timeline JSON chứa những steps còn trong buffer.
- `GET /actuator/metrics/application.started.time` và `...ready.time` trả các phép đo tổng thể riêng.
- `POST /actuator/startup` drain buffer, có thể khiến GET kế tiếp không còn dữ liệu cũ.

### 9.1. Cấu trúc project

```text
startup-timeline-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/startup/
    StartupTimelineApplication.java
    PingController.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'startup-timeline-demo'
```

### 9.3. build.gradle (Groovy DSL)

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Script ví dụ dùng BOM của Spring Boot để quản lý versions của starters. Các lệnh `./gradlew` bên dưới giả định project đã có **Gradle Wrapper**; nếu chưa có, tạo Wrapper bằng Gradle phù hợp hoặc dùng Spring Initializr.

### 9.4. application.properties

```properties
# Chỉ cho phép truy cập từ máy local trong bài thực hành.
server.address=127.0.0.1
server.port=8080

# Chỉ expose những endpoints cần cho bài học.
management.endpoints.web.exposure.include=health,startup,metrics

# Thông thường mặc định enabled; ghi rõ để tránh nhầm.
management.endpoint.startup.enabled=true
```

**Lưu ý về bảo mật:** file này **chỉ an toàn như một demo cục bộ** khi chạy ở localhost. Không copy exposure của startup/metrics sang production mà không có chính sách access control, firewall hoặc authentication/authorization phù hợp.

### 9.5. StartupTimelineApplication.java

```java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.StartupStep;

@SpringBootApplication
public class StartupTimelineApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupTimelineApplication.class);

        // Phải đặt TRƯỚC run() mới ghi được startup steps.
        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }

    @Bean
    ApplicationRunner recordDemoWarmup(
            ConfigurableApplicationContext context) {

        return args -> {
            StartupStep step = context.getApplicationStartup()
                    .start("app.demo.warmup");

            try {
                step.tag("phase", "runner");

                int checksum = 0;
                for (int i = 0; i < 1000; i++) {
                    checksum += i;
                }

                System.out.println("WARMUP_CHECKSUM=" + checksum);
            } finally {
                // Quan trọng: kết thúc step ngay cả khi code lỗi.
                step.end();
            }
        };
    }
}
```

Đây là **file Java hoàn chỉnh**. Nó dùng `ConfigurableApplicationContext.getApplicationStartup()` để lấy recorder đã cấu hình; Spring Framework cũng có thể cho injection theo `ApplicationStartup` trong những thành phần phù hợp.

**Vì sao dùng `try/finally`?** `StartupStep.end()` cần được gọi dù công việc ném exception để bước đo được hoàn tất. Nếu quên end, một step đang mở có thể không có duration cuối, ảnh hưởng khả năng xem hoặc giải thích timeline.

Tên `app.demo.warmup` **không dùng prefix `spring.*`** vì namespace đó dành cho các bước nội bộ của Spring. Tag `phase=runner` là metadata cố định, không chứa secrets hoặc dữ liệu cá nhân.

Bài tập `checksum` chỉ minh họa mã chạy có thể quan sát. Với các số nguyên từ 0 tới 999, tổng đúng là **499500**, không phụ thuộc máy chạy. Đừng kết luận thời gian của vòng lặp nhỏ này đại diện cold-start của database hay network.

### 9.6. PingController.java

```java
package com.example.startup;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/demo/ping")
    public String ping() {
        return "pong";
    }
}
```

Đây là file Java hoàn chỉnh. Nó không dùng database, không cố làm nóng tất cả services và không thay thế readiness probe. Mục tiêu duy nhất là có endpoint nghiệp vụ đơn giản để chứng minh server đã nhận request.

### 9.7. Chạy ứng dụng

Từ project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Khi Boot chạy thành công, chương trình in:

```text
WARMUP_CHECKSUM=499500
```

Dòng log framework như “Started StartupTimelineApplication in ...” cũng xuất hiện với số đo phụ thuộc máy. **Không cam kết** chính xác số giây, số `StartupStep` hay thứ tự toàn bộ log framework.

Mở terminal thứ hai:

```bash
curl -i http://127.0.0.1:8080/demo/ping
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/startup
```

Body của endpoint demo `/demo/ping` là:

```text
pong
```

`/actuator/health` là endpoint health, còn `/actuator/startup` trả **timeline JSON**. Không tự động dùng `/actuator/health` như một công cụ giải thích các steps tốn thời gian.

### 9.8. Xem riêng application started/ready metrics

```bash
curl -i http://127.0.0.1:8080/actuator/metrics/application.started.time
curl -i http://127.0.0.1:8080/actuator/metrics/application.ready.time
```

Khi metric được ghi nhận và endpoint đã expose, response thường có các trường tương tự:

```json
{
  "name": "application.ready.time",
  "description": "Time taken for the application to be ready to service requests",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 1.234
    }
  ],
  "availableTags": [
    {
      "tag": "main.application.class",
      "values": ["com.example.startup.StartupTimelineApplication"]
    }
  ]
}
```

**JSON trên chỉ minh họa về mặt nội dung và cấu trúc**, không phải output bảo đảm, và `1.234` không phải số liệu đo của bài. Tên/kiểu statistic và tags cụ thể do Spring Boot/Micrometer version cùng runtime quyết định; hãy dựa vào JSON thực sự trả về.

**Không** lấy metric này từ `/actuator/startup`. Chúng đến từ hệ thống Micrometer metrics của Actuator, dù cùng dùng để chẩn đoán startup.

### 9.9. Lấy snapshot mà không drain

```bash
curl -fsS http://127.0.0.1:8080/actuator/startup \
  -o startup-snapshot.json
```

Đây là lệnh cho shell POSIX; trên Windows PowerShell có thể sử dụng `curl.exe` với cú pháp tương thích hoặc `Invoke-RestMethod`. Dùng `GET` để tránh xóa dữ liệu buffer. Sau khi lưu, bạn có thể đọc `startup-snapshot.json` trong editor hoặc bằng chương trình JSON parser tùy ý.

### 9.10. Draining chỉ khi thực sự chủ đích

```bash
curl -fsS -X POST http://127.0.0.1:8080/actuator/startup \
  -o startup-drained.json
```

**Chỉ thử khi bạn chấp nhận buffer bị tiêu thụ**. Nếu gọi lại GET, bạn có thể thấy rất ít hoặc không còn events. Đối với app có security/CSRF, POST có thể cần credentials/token phù hợp; demo cục bộ không có starter-security.

Không dùng POST chỉ để “refresh lại báo cáo”. Endpoint startup không có chức năng tái dựng lịch sử sau khi events đã bị drain.

## 10. Liên hệ 3 nguồn dữ liệu trong một báo cáo startup

Để chẩn đoán một lần khởi động, thu thập:

| Nguồn | Giá trị | Chuyên trả lời câu hỏi |
| --- | --- | --- |
| Log Spring Boot | “Started ... in X seconds” | Tổng quan lần boot mất bao lâu |
| `application.started.time` | Metric tổng thể | Tới mốc started mất bao lâu |
| `application.ready.time` | Metric tổng thể | Tới mốc ready nhận traffic mất bao lâu |
| `/actuator/startup` | Danh sách steps, durations, tags | Những đoạn có instrumentation đã làm gì và mất bao lâu |
| Log riêng của runner/warmup | Start/end, outcome, trace id nội bộ | Bước nghiệp vụ startup có thành công không |
| JFR/profile | CPU/GC/allocations/threads | Vì sao một phase có chi phí ở mức JVM |
| Readiness probe | Sẵn sàng nhận traffic hiện tại | Instance có nên được route request mới vào không |

### 10.1. Cách ghép dữ liệu có ý nghĩa

Giả sử trước tối ưu, bạn đo:

```text
application.started.time = 3.2 s
application.ready.time   = 8.4 s
```

Đây chỉ là số liệu **giả định**. Khoảng chênh **5.2 s** có thể gợi ý công việc sau started và trước ready, đặc biệt runners. Nhưng đừng coi đó là “thời gian của một bean” hoặc phép đo chính xác mọi bước không được instrument.

Tiếp theo:

1. Tìm custom step `app.demo.warmup` hoặc các step liên quan runner trong `/actuator/startup`.
2. Kiểm tra duration của những bước và quan hệ parent-child.
3. Tìm logs runner và dependency load để xác nhận công việc thực sự hoàn tất.
4. Nếu không có step tương ứng, xem code đã instrument chưa, buffer có đầy/drain không.
5. Đo lại với cùng workload và machine limits để xác nhận thay đổi.

### 10.2. Bản báo cáo nên ghi cả cấu hình thu thập

Một báo cáo startup tối thiểu nên có:

- Application/version/commit.
- Spring Boot version và Java version.
- JVM flags, heap, CPU/memory limits.
- Phương thức chạy: IDE, `bootRun`, `java -jar`, container hay native image.
- Active profiles và những feature flags ảnh hưởng startup (không ghi secrets).
- `BufferingApplicationStartup` capacity/filter.
- Thời điểm và loại truy xuất endpoint: GET hay POST.
- Started/ready metrics nếu có.
- Top steps kèm id, parentId, tags, durations.
- Thông tin readiness, first-request latency nếu đang tối ưu chất lượng rollout.
- Cỡ mẫu các lần chạy, median và p95/p99 thay vì một sample đơn lẻ.

Không so sánh “ngày A” và “ngày B” chỉ từ hai timeline khi JVM cold/warm, classpath và CPU limits khác nhau.

## 11. Phân tích timing JSON bằng một script nhỏ

Nếu muốn phân tích không phụ thuộc vào công cụ UI, có thể dùng Python chuẩn để đọc file `startup-snapshot.json` từ demo. Đoạn sau **đọc dữ liệu đã lưu**, không gửi request ra mạng.

**File:** `inspect_startup.py`

```python
import json
from pathlib import Path

file = Path("startup-snapshot.json")
data = json.loads(file.read_text(encoding="utf-8"))

events = data.get("timeline", {}).get("events", [])

def as_seconds(text):
    # Cho các duration dạng PT0.003S phổ biến của ví dụ.
    if text.startswith("PT") and text.endswith("S"):
        return float(text[2:-1])
    return None

rows = []
for event in events:
    step = event.get("startupStep", {})
    name = step.get("name", "unknown")
    seconds = as_seconds(event.get("duration", ""))
    if seconds is not None:
        rows.append((seconds, name, step.get("id")))

rows.sort(reverse=True)
for duration, name, step_id in rows[:10]:
    print(f"{duration * 1000:9.3f} ms  {name}  id={step_id}")
```

Lệnh chạy, giả định có Python 3:

```bash
python inspect_startup.py
```

Đây là **script độc lập** có thể chạy nếu file JSON chứa data của Actuator. Hàm parser chỉ xử lý **mẫu ISO-8601 Duration dạng `PT...S`**, chưa phải parser tổng quát cho mọi duration như phút/giờ; muốn dùng production, dùng thư viện parser ISO-8601 đáng tin hoặc Java `Duration.parse(...)`.

**Cảnh báo quan trọng:** script xếp các steps theo **inclusive duration**. Nó **không** tính tổng startup time, **không** loại trừ overlap, **không** ghép nested steps và **không** thay thế việc dựng hierarchy từ `parentId`. Dùng để tìm bước cần điều tra đầu tiên, không để công bố “tổng time của 10 beans”.

### 11.1. Vì sao cần xử lý data thiếu?

Khi filter/capacity/drain ảnh hưởng buffer, `events` có thể trống hoặc không đầy đủ. Script trên không yêu cầu `parentId` vì field này là tùy chọn. Việc kiểm tra `duration` trước khi convert tránh ném lỗi khi schema khác hoặc dữ liệu chưa có.

Đối với một pipeline nghiêm túc, nên xác minh `springBootVersion`, schema response và xử lý trường thiếu hợp lệ trước khi so sánh qua nhiều versions.

## 12. Tự thêm StartupStep cho các pha nghiệp vụ trong startup

Spring Framework cho phép code ứng dụng tạo step custom. Ví dụ trong một `ApplicationRunner`:

```java
StartupStep step = context.getApplicationStartup()
        .start("app.cache.preload");

try {
    step.tag("cache", "catalog");
    catalogCache.loadRequiredData();
} finally {
    step.end();
}
```

Đây là **snippet**, cần biến `context`, `catalogCache`, import `StartupStep`, và một cache API do ứng dụng định nghĩa. Nó không phải file Java độc lập. Chỉ áp dụng khi tải cache là việc **có chủ đích trong startup**; không tự nạp dữ liệu production chỉ để tạo số đo.

### 12.1. Đặt tên custom step đúng quy ước

- Nên dùng namespaced name, ví dụ `app.cache.preload` hoặc `company.module.init`.
- **Tránh prefix `spring.*`** cho custom steps vì namespace này thuộc framework.
- Tên nên ổn định giữa các lần release để dễ so sánh.
- Tags có giá trị low-cardinality và không lộ dữ liệu nhạy cảm.
- Không đưa token, raw SQL chứa thông tin người dùng, mật khẩu, connection string có credentials hoặc tên khách hàng vào tags.
- Luôn gọi `end()`, ưu tiên trong `finally`.

### 12.2. Custom step không biến một tác vụ asynchronous thành mốc ready

Nếu runner tạo một `CompletableFuture` và return ngay, Spring Boot có thể ready trước khi task bất đồng bộ xong. Một custom step chạy trong background có thể kết thúc sau ready, nhưng đó **không** chứng minh readiness đã chờ công việc đó.

Nếu warm-up **bắt buộc** trước khi nhận traffic, runner nên chờ kết quả hữu hạn hoặc ứng dụng phải có readiness gating rõ ràng. `ApplicationStartup` chỉ là công cụ đo; nó **không điều phối readiness** thay bạn.

## 13. Buffer capacity, filter và rủi ro dữ liệu không đầy đủ

`BufferingApplicationStartup(2048)` không nghĩa mọi ứng dụng chắc chắn cần hoặc đủ 2048 steps. Một app lớn với nhiều autoconfigurations và bean definitions có thể tạo nhiều hơn.

### 13.1. Capacity hữu hạn là mục tiêu có chủ ý

Buffer giới hạn memory footprint và overhead. Khi đầy, những steps mới có thể bị bỏ qua. Vì vậy tăng capacity quá thấp dẫn tới thiếu evidence; tăng quá lớn có thể tăng chi phí ghi/giữ dữ liệu.

Chọn capacity bằng thử nghiệm:

1. Bật trên staging hoặc local với cấu hình đại diện.
2. Thu thập snapshot một lần khởi động bình thường.
3. Ước tính số lượng events.
4. Kiểm tra những steps quan trọng ở cuối runner có được ghi không.
5. Chọn capacity có khoảng dự phòng phù hợp.
6. Rà overhead CPU/heap và thông tin tags trước production.

### 13.2. Filter giúp giảm sự nhiễu

Implementation hỗ trợ `addFilter(Predicate<StartupStep>)`. Có thể chọn steps theo namespace/tags để giữ các bước cần thiết. Nhưng filter có thể làm mất parent/child relationships quan trọng, khiến khó giải thích một step dài nếu parent đã bị loại.

Trước khi áp dụng filter, cần biết câu hỏi nghiên cứu: tìm bean creation bottleneck, listener duration hay custom warm-up. Đừng dùng filter quá mạnh rồi tuyên bố những thứ không ghi là không xảy ra.

### 13.3. Buffer không phải distributed tracing

Mỗi instance có timeline riêng. Không có cơ chế mặc định gộp dữ liệu của tất cả pods vào một timeline chung. Khi so sánh:

- Lấy đúng instance/pod và version.
- Gắn run/instance id vào metadata của hệ thống thu thập **bên ngoài response** nếu cần.
- Tránh đẩy raw tags nhạy cảm lên bảng điều khiển công khai.
- Tính chênh lệch của từng instance rồi so sánh phân phối.

## 14. FlightRecorderApplicationStartup là lựa chọn khác, không phải JSON startup endpoint

Spring Framework có `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup` dành cho Java Flight Recorder. Nó phát Spring startup-related JFR events, giúp liên hệ với:

- JVM class loading.
- Allocation và GC.
- Thread scheduling.
- Blocking I/O.
- CPU hotspots.

Ví dụ **phương án thay thế** trong `main`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
```

Đây là snippet, cần class `MyApplication` và imports `FlightRecorderApplicationStartup`. Nếu chọn JFR, chạy với lệnh mẫu:

```bash
java -XX:StartFlightRecording:filename=recording.jfr,duration=15s \
  -jar build/libs/myapp.jar
```

Lệnh chỉ minh họa việc bật JFR; file JAR phải tồn tại và JDK hỗ trợ Flight Recorder.

**Điểm phải nhớ:** `/actuator/startup` của Spring Boot 3.3 **yêu cầu BufferingApplicationStartup**. Chỉ cấu hình `FlightRecorderApplicationStartup` rồi expose HTTP endpoint **không tương đương** với buffer JSON. Đây là **hai backend khác nhau** của cùng abstraction `ApplicationStartup`, phục vụ các cách điều tra khác nhau.

Không giả định có thể dùng hai implementations đồng thời chỉ bằng gọi `setApplicationStartup` hai lần; lần thiết lập sau sẽ thay lần trước trừ khi bạn tự xây cơ chế composite hợp lệ.

## 15. Liên hệ với lazy initialization và first-request latency

Nếu `spring.main.lazy-initialization=true`, nhiều beans có thể **chưa được tạo trong startup** mà chỉ xuất hiện khi HTTP request đầu tiên đến. Spring Boot cảnh báo lazy có thể chuyển chi phí sang request đầu và phát hiện lỗi cấu hình muộn.

Hệ quả khi đọc `/actuator/startup`:

- Timeline startup có thể ít bean-instantiation steps hơn.
- `application.ready.time` có thể thấp hơn.
- **Không** có nghĩa các routes đã ấm hoặc mọi dependency đã được kiểm thử.
- Bean lazy không được tạo lúc startup có thể chỉ tiêu tốn thời gian khi traffic đến.
- Buffer dùng cho startup không thay thế HTTP latency metrics.

Muốn đánh giá bật lazy có lợi hay không, đo cùng lúc:

1. Process-to-ready.
2. Các startup steps đã ghi.
3. Latency request đầu của **critical paths**.
4. Error rate ngay sau rollout.
5. Memory và GC khi lazy beans bắt đầu xuất hiện.
6. Tác động đến network/database lúc nhiều pods scale up.

**Tối ưu startup không được đánh đổi thành lỗi cho người dùng đầu tiên mà không có chủ đích.**

## 16. Liên hệ với health, liveness và readiness

`/actuator/startup`, `/actuator/health` và `/actuator/metrics` là ba nhóm endpoint với hợp đồng khác nhau.

| Endpoint | Trả lời câu hỏi |
| --- | --- |
| `/actuator/startup` | Những steps startup đã được ghi vào timeline, mất bao lâu? |
| `/actuator/metrics/application.ready.time` | Mốc ready của lần khởi động vừa qua mất bao lâu? |
| `/actuator/health/readiness` | Instance **hiện tại** có nên nhận traffic không? |
| `/actuator/health/liveness` | Instance **hiện tại** có sống/đúng trạng thái nội bộ không? |
| `/actuator/health` | Tổng hợp health status theo configured indicators |

Nếu `readiness` trả UP, điều đó không đồng nghĩa timeline đã được thu thập hoặc endpoint startup được expose. Ngược lại, một timeline có nhiều steps hoàn tất không phải bảo đảm application **hiện tại** còn khỏe.

### 16.1. Startup-step instrumentation không phải startupProbe của Kubernetes

`startupProbe` trong Kubernetes là cơ chế kiểm tra xem container đã khởi động đủ để tiếp tục liveness/readiness probes hay chưa. Nó **khác** `/actuator/startup` vốn là endpoint chẩn đoán timeline.

Không cấu hình kubelet `startupProbe` gọi `/actuator/startup` chỉ vì URL chứa chữ startup. Kubernetes probe cần endpoint trả lời **tình trạng có thể dùng** thích hợp (`/livez` hoặc endpoint do ứng dụng thiết kế), không phải một API diagnostic có thể bị disable, 404 hoặc drain.

### 16.2. Khi nào nên quan sát cả startup, metrics và readiness?

Một Kubernetes deployment rollout lâu:

- `/actuator/startup` giúp tìm các bước Boot/container nào chậm.
- `application.ready.time` cho phép so sánh **độ dài tổng thể** giữa các versions.
- Readiness probe cho biết load balancer có nên gửi traffic chưa.
- Container logs và CPU/GC/JFR giúp biết yếu tố môi trường.

Dùng dữ liệu phối hợp để tránh tối ưu sai tầng. Nếu startup timeline ổn nhưng pod chưa ready do external dependency, cần điều tra readiness policy, network và deployment, không chỉ bean instantiation.

## 17. Troubleshooting khi /actuator/startup không trả dữ liệu như mong đợi

### 17.1. HTTP 404

Kiểm tra có thứ tự:

1. Đã thêm `spring-boot-starter-actuator` chưa?
2. `application.setApplicationStartup(new BufferingApplicationStartup(...))` có chạy **trước `run`** không?
3. `management.endpoint.startup.enabled` có bị tắt không?
4. `management.endpoints.enabled-by-default=false` có vô hiệu hóa endpoint mà chưa bật lại không?
5. `management.endpoints.web.exposure.include` có chứa `startup` không?
6. Có property `management.endpoints.web.exposure.exclude` ưu tiên loại startup không?
7. Đang gọi đúng port và base path không?
8. Ứng dụng có HTTP server thực sự running không?

Với Spring Boot 3.3, `startup` được auto-configure theo điều kiện, trong đó có recorder phù hợp. Chỉ thêm exposure không làm xuất hiện endpoint khi đang dùng default no-op startup recorder.

### 17.2. HTTP 401 hoặc 403

Đây thường là chuyện **access control**, không phải timeline thiếu. Nếu Spring Security được cài và có custom security filter chain, kiểm tra endpoint matcher/authorization và CSRF policy cho POST.

**Không** mở toàn bộ actuator publicly để “sửa nhanh” lỗi 403. Thay bằng quyền đọc đúng người, allowlist, token/session hoặc management interface phù hợp.

### 17.3. GET có events nhưng không có step mong đợi

Có thể do step chưa được instrument, bị filter, bị bỏ vì buffer đầy, hoặc runner chạy sau mốc bạn tưởng. Kiểm tra custom step có `end()` không và bạn có thật sự dùng đúng recorder trong `SpringApplication`.

### 17.4. GET trả events trống sau POST

Đây có thể là hành vi bình thường vì `POST` đã drain. Để so sánh startup từ đầu, cần **một lần khởi động mới** hoặc dữ liệu mà collector đã lưu. Không có nút “đọc lại lịch sử đã drain”.

### 17.5. application.ready.time không có

Kiểm tra Actuator/Micrometer metrics có được kích hoạt, metric name đúng, endpoint `metrics` có expose, application đã tới mốc ready, và đã gọi đúng URL. Nếu startup thất bại trước ready thì metric ready có thể không được ghi.

### 17.6. Duration quá nhỏ hoặc kết quả không ổn định

Đừng suy luận lỗi recorder khi step chỉ mất vài microseconds. JVM JIT, GC, OS scheduler, disk cache và mạng ảnh hưởng mạnh các lần chạy. Thay vì tăng độ phức tạp bằng một phép đo đơn lẻ, thu nhiều samples và phân tích median/p95.

### 17.7. Management port xanh nhưng app vẫn lỗi

Nếu management server chạy trên port riêng, endpoint Actuator có thể hoạt động trong khi web server chính gặp lỗi. Timeline chỉ giải thích startup recorded, **không thay thế health của request path chính**.

## 18. Quy trình phân tích một startup regression

Giả sử bản release mới mất **8.9 s** đến ready thay vì **4.1 s** (số liệu minh họa). Một quy trình có thể kiểm chứng:

1. Xác định Git commit, Spring Boot/Java version, profiles và resource limits.
2. Đảm bảo cả hai phiên đều cấu hình `BufferingApplicationStartup` giống nhau, đủ capacity.
3. Bật `startup`/`metrics` trên management interface được bảo vệ.
4. Thu nhiều lần restart ở mỗi version, sau đó lưu GET snapshot và started/ready metrics.
5. So sánh phân phối `application.started.time` và `application.ready.time`.
6. Nếu ready tăng nhưng started ổn, điều tra runners/warm-up sau refresh.
7. Nếu started tăng, điều tra context refresh, bean instantiation, framework initialization và web server.
8. Dùng `parentId` để tránh cộng sai durations.
9. Kiểm tra tags để truy tìm bean hoặc component; đối chiếu logs của tác vụ.
10. Nếu chênh lệch chỉ xuất hiện dưới CPU contention, thu JFR và OS resource metrics.
11. Thử tối ưu một điểm có giả thuyết rõ: giảm remote call, lazy chọn lọc, tối ưu query, giới hạn cache preload.
12. Đo lại cả time-to-ready, first-request latency, errors và memory sau thay đổi.
13. Xác nhận thay đổi không làm readiness công bố sớm hơn khi app còn thiếu dependency bắt buộc.
14. Ghi kết luận dựa trên nhiều samples và các steps thực tế, không dùng suy luận từ duy nhất một timeline.

### 18.1. Cách tránh kết luận nhân quả sai

Một step tạo Bean A xuất hiện trong top slow steps không có nghĩa code constructor A chắc chắn là nguyên nhân duy nhất. Bean A có thể tạo nhiều dependencies con, gọi API ngoài hoặc chờ thread. Muốn xác định bottleneck cần kết hợp:

- Nested step hierarchy.
- Stack trace/JFR.
- Database/client timing.
- Logs có correlation.
- Một thí nghiệm thay đổi có kiểm soát.

Số đo giúp chọn nơi điều tra; **bằng chứng thay đổi trước/sau** mới xác nhận cải thiện.

## 19. Những anti-pattern cần tránh

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| Chỉ thêm starter Actuator rồi chờ full startup JSON | Mặc định không có buffer recorder | Cấu hình `BufferingApplicationStartup` trước `run` |
| Chỉ expose startup mà không enable endpoint | Endpoint có thể bị disable | Kiểm tra enablement và exposure riêng |
| Cấu hình recorder sau khi app ready | Không thể ghi hồi tố các bước đã qua | Đặt trong `main` trước `run` |
| Gọi POST như GET | POST drain buffer | Dùng GET để snapshot, POST khi chủ đích bàn giao |
| GET trống nên nghĩ Boot không làm gì | Buffer đầy/filter/drain/no-op | Kiểm tra recorder, capacity, filters, POST history |
| Cộng durations của tất cả steps | Đếm lặp nested/overlapping time | Phân tích id/parentId và interval |
| Lấy startup timeline như toàn bộ CPU profile | Chỉ có các điểm instrument | Dùng JFR/profiler cho JVM hotspots |
| Coi steps là application ready metric | Khác hệ dữ liệu, khác mục đích | Lấy `application.ready.time` riêng |
| Nhầm Actuator startup với startupProbe | Diagnostic vs sức khỏe container | Dùng health/live endpoints cho probes |
| Đưa API keys vào custom tags | Lộ secrets qua endpoint/collector | Tags metadata không nhạy cảm |
| Expose `*` trên public interface | Mở nhiều endpoints có thể nhạy cảm | Endpoint allowlist và auth |
| Chỉ quan sát một pod một lần | Không có phân phối/variance | Nhiều instances và lần restart |
| So sánh IDE launch với production jar | Startup mode/JVM khác | Cùng cách launch/config |
| Tối ưu started.time nhưng để runner chậm | Ready có thể vẫn chậm | Đo cả ready và runners |
| Bật lazy và kết luận app đã nhanh | Chi phí có thể chuyển tới first request | Đo first-hit latency và errors |
| Filter quá mạnh khiến mất parent steps | Hierarchy khó dựng | Giữ steps đủ để phân tích |
| Capacity thấp nhưng tuyên bố trace đầy đủ | Step mới có thể bị bỏ | Tăng capacity kiểm soát và đối chiếu |
| Tự ghi step nhưng quên `end()` | Không hoàn tất duration | `try/finally` |
| Trùng tên custom `spring.*` | Đụng namespace framework | `app.*` hoặc namespace riêng |
| Đặt startup endpoint thành readiness check | Không đo khả năng nhận traffic | `/actuator/health/readiness` |
| Có metrics nhưng không ghi context lần đo | Không so sánh được kết quả | Lưu version/profiles/JVM/resources |
| Giả định GET sau POST lặp lại dữ liệu cũ | Drain đã tiêu thụ buffer | Lưu snapshot hoặc lấy từ collector |

## 20. Checklist cấu hình và đo

**Trước khởi động**

1. Chọn Spring Boot/Java version và ghi vào hồ sơ thí nghiệm.
2. Thêm `spring-boot-starter-actuator`.
3. Tạo `SpringApplication` instance trong `main`.
4. Đặt `setApplicationStartup(new BufferingApplicationStartup(capacity))` **trước `run`**.
5. Chọn capacity hợp lý với số bước app sinh ra.
6. Xác định có filter hay không.
7. Bật `startup` và `metrics` theo nhu cầu.
8. Expose đúng endpoint HTTP cần dùng.
9. Bảo vệ management endpoints; không expose công khai vô điều kiện.
10. Kiểm tra port/base path và instance cụ thể.

**Sau khi app ready**

11. Dùng `GET /actuator/startup` để snapshot.
12. Ghi `springBootVersion` và `timeline.startTime`.
13. Lưu nguyên JSON bằng quyền truy cập phù hợp.
14. Dùng `GET /actuator/metrics/application.started.time`.
15. Dùng `GET /actuator/metrics/application.ready.time`.
16. Nếu dùng `POST`, biết rõ nó drain dữ liệu.
17. Không suy luận hierarchy từ array order; dùng id/parentId.
18. Không cộng tất cả durations để ra tổng thời gian.
19. Kiểm tra những custom startup steps đã `end()`.
20. Đối chiếu ready/startup metrics với logs và trạng thái readiness.

**Phân tích và vận hành**

21. Điều tra steps kéo dài nhưng có xét nested children.
22. Đối chiếu JFR, CPU, GC, I/O khi cần.
23. Đo nhiều lần và nhiều instances.
24. Nếu dùng lazy, đo first-request latency.
25. Kiểm tra buffer có đầy hoặc collector đã drain.
26. Không đưa bí mật vào tags hay báo cáo raw.
27. Không dùng `/actuator/startup` làm Kubernetes startupProbe.
28. Chỉ giữ endpoint chẩn đoán trong phạm vi cần thiết.
29. Kiểm tra việc tối ưu không làm mất correctness/readiness.
30. Ghi lại thí nghiệm để so sánh release sau.

## 21. Câu hỏi tự kiểm tra

**1. Vì sao thêm Actuator chưa chắc có /actuator/startup?**

Vì Spring Boot 3.3 cần `BufferingApplicationStartup` đã được đặt cho `SpringApplication`, đồng thời endpoint phải enabled/exposed và server/security cho truy cập.

**2. Nên gọi setApplicationStartup lúc nào?**

Trước `SpringApplication.run(...)`; đặt muộn không ghi lại được các bước trước đó.

**3. BufferingApplicationStartup(2048) có nghĩa 2048 ms không?**

Không. `2048` là capacity bước ghi vào buffer, không phải timeout hay duration.

**4. GET và POST /actuator/startup khác nhau gì?**

GET trả snapshot **không drain**; POST trả và **tiêu thụ** các steps đang buffer.

**5. application.ready.time có nằm trong /actuator/startup JSON không?**

Đây là metric tổng thể của Micrometer/Actuator; truy cập qua metrics endpoint nếu được bật/exposed. Startup JSON chứa các bước riêng.

**6. Tại sao không cộng mọi duration?**

Vì steps có thể lồng nhau hoặc chồng lắp thời gian, làm đếm cùng một khoảng nhiều lần.

**7. Nếu không thấy bean A trong timeline, có chắc nó chưa được tạo không?**

Không. Có thể buffer đầy, filter loại, đã drain, thiếu instrumentation hoặc bean được tạo ngoài pha đo; phải điều tra.

**8. JFR startup events có đồng nghĩa BufferingApplicationStartup không?**

Không. `FlightRecorderApplicationStartup` dùng JFR; endpoint `startup` Boot 3.3 yêu cầu buffered implementation.

**9. Có nên dùng /actuator/startup làm Kubernetes startupProbe?**

Không. Nó là diagnostic API, không phải availability probe.

**10. Dấu hiệu nào chỉ ra runner có thể làm ready chậm?**

`application.ready.time` cao hơn đáng kể `application.started.time` trong cùng lần chạy, cộng các custom runner steps và logs tương ứng.

**11. Custom step cần làm gì sau khi bắt đầu?**

Gắn tags cần thiết rồi gọi `end()`, ưu tiên `finally` để hoàn tất cả khi lỗi.

**12. Khi nào không nên expose startup endpoint công khai?**

Trong đa số ứng dụng production, timeline/bean names có thể lộ cấu trúc nội bộ. Chỉ expose qua interface/quyền nội bộ được kiểm soát.

## 22. Tóm tắt

```text
        1. CẤU HÌNH TRƯỚC RUN
SpringApplication.setApplicationStartup(
    new BufferingApplicationStartup(...))
                     |
                     v
        2. BOOT GHI STARTUP STEPS
      StartupStep name/id/tags/parentId
                     |
                     v
        3. ACTUATOR STARTUP ENDPOINT
        GET = snapshot / POST = drain
                     |
                     v
        4. DIỄN GIẢI TIMELINE ĐÚNG
  Không cộng durations lồng nhau;
  biết buffer capacity và missing steps
                     |
                     +------------+
                     |            |
   application.started.time   application.ready.time
        (metrics riêng)         (metrics riêng)
                     |            |
                     +------------+
                          |
             5. SO SÁNH CÙNG MÔI TRƯỜNG
        + log + readiness + JFR nếu cần
```

**Ghi nhớ:** `/actuator/startup` chỉ có dữ liệu đầy đủ khi ứng dụng **được cấu hình thu thập ngay từ đầu** bằng `BufferingApplicationStartup`, đồng thời endpoint được enable, expose và bảo vệ phù hợp. `GET` là snapshot, `POST` là drain. Các durations của `StartupStep` giúp khoanh vùng nút thắt nhưng không được cộng bừa vì nested intervals. Hãy đối chiếu `application.started.time` và `application.ready.time`, logs, readiness và đôi khi JFR để có câu chuyện startup chính xác, đo được và có thể kiểm chứng.

## Tài liệu chính thức

- [Spring Boot 3.3.13 — SpringApplication: Application Startup Tracking](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3.13 — Actuator Endpoints: startup conditions, exposure and security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3.13 — Actuator startup REST API (GET và POST)](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
- [Spring Boot 3.3.13 — BufferingApplicationStartup JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html)
- [Spring Boot 3.3.13 — Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Framework 6.1 — ApplicationStartup và StartupStep](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html)
- [Spring Framework 6.1 — StartupStep API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/metrics/StartupStep.html)
