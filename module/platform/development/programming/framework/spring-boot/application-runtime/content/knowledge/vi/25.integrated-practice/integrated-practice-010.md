# Thực hành: đo BufferingApplicationStartup rồi xác định giai đoạn khởi động chậm

## 1. Đặt bài toán và tiêu chí thành công

Khi ứng dụng Spring Boot khởi động chậm, log tổng quát như `Started Application in 4.2 seconds` chưa trả lời được **giai đoạn nào** đã tiêu tốn thời gian: đọc cấu hình, quét component, phân tích `@Configuration`, tạo bean, kết nối database, warm-up cache hay xử lý các runners.

Bài thực hành này dùng **`BufferingApplicationStartup`** để ghi timeline gồm những `StartupStep` do Spring Framework và code ứng dụng phát ra. Ta chủ động cài một khâu khởi tạo chậm, đo nó, đọc quan hệ cha-con rồi loại bỏ khoảng chờ để đo lại. Mục tiêu không phải tạo một con số benchmark đẹp mà là xây một quy trình **tìm bottleneck có bằng chứng**.

Công nghệ:
- **Java 17+**, Maven, **Spring Boot 3.5.16**, Spring Framework 6.2.x.
- `spring-boot-starter-web` và `spring-boot-starter-actuator`.
- `BufferingApplicationStartup` khởi tạo **trước `SpringApplication.run`**.
- `GET /actuator/startup` lưu snapshot JSON; `POST` chỉ dùng khi thực sự muốn drain.
- `jq` hoặc một script **Python 3 standard library** để phân tích hai JSON.
- JUnit 5 / AssertJ để kiểm tra custom instrumentation.

Bài sẽ thực hiện hai cấu hình trên **cùng một JAR**:
1. `--demo.catalog.delay-ms=800`: cố tình chờ khoảng 800 ms trong bean factory method.
2. `--demo.catalog.delay-ms=0`: không chờ, vẫn tạo bean và trả cùng response.

Một kết quả thực hành đạt yêu cầu phải chỉ ra **`demo.catalog.initialize` bị chậm ở chế độ 800 ms**, giải thích nó có thể nằm bên trong `spring.beans.instantiate` và `spring.context.refresh`, rồi xác nhận phần chờ đã biến mất ở lần chạy đối chứng. Các duration thực tế phải **lấy từ JSON**, không tự bịa số.

## 2. BufferingApplicationStartup hoạt động ở đâu trong startup lifecycle?

Spring Framework định nghĩa:
- `org.springframework.core.metrics.ApplicationStartup` — giao diện phát sinh các bước đo.
- `org.springframework.core.metrics.StartupStep` — một đơn vị công việc có name, ID, parent ID, tags và `end()`.
- `ApplicationStartup.DEFAULT` — implementation **no-op**, không có recording timeline hữu ích.

Spring Boot định nghĩa:
- `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup` — bộ đệm hữu hạn chứa steps đã ghi, có timestamps và duration.
- `StartupTimeline` và `StartupTimeline.TimelineEvent` — đối tượng dữ liệu snapshot.
- Actuator `startup` endpoint — expose timeline dưới dạng JSON khi có Buffering tracker phù hợp.

~~~mermaid
flowchart TD
  MAIN["main(args)"] --> TRACKER["SpringApplication.setApplicationStartup(BufferingApplicationStartup)"]
  TRACKER --> RUN["SpringApplication.run(args)"]
  RUN --> FRAMEWORK["Framework: spring.boot.*, spring.context.*, spring.beans.*"]
  FRAMEWORK --> CUSTOM["App: demo.catalog.initialize"]
  CUSTOM --> END["StartupStep.end()"]
  END --> BUFFER["In-memory bounded timeline"]
  BUFFER --> GET["GET /actuator/startup: snapshot"]
  BUFFER --> POST["POST /actuator/startup: drain"]
  GET --> ANALYZE["So duration, tags, id, parentId và timestamps"]
~~~

**Quan trọng:** đây là mô tả luồng dữ liệu. Các steps có thể **lồng nhau**, không phải chạy tuần tự từ trên xuống theo mọi nhánh của sơ đồ. `spring.beans.instantiate` thường bao gồm cả thời gian khởi tạo dependency/bean, do đó thời gian của custom child có thể đã nằm trong khoảng của parent.

### Tại sao phải cấu hình trước run()?

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(4096));
app.run(args);
~~~

Snippet trên cần một `MyApplication` và các imports tương ứng. Nếu tạo `BufferingApplicationStartup` **sau** khi context đã refresh, bạn **không có dữ liệu hồi tố** của những steps trước đó. Đừng tạo một recorder mới trong `@PostConstruct` rồi mong thấy bước parse configuration diễn ra trước nó.

### Các trường của StartupStep và timeline

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `startupStep.name` | Tên loại công việc, ví dụ `spring.beans.instantiate` | Tên nội bộ không phải API bất biến |
| `startupStep.id` | Identifier của step trong lần startup | Không phải thời gian hay business ID |
| `startupStep.parentId` | ID step cha nếu có | Top-level có thể không có field này |
| `startupStep.tags[]` | Metadata key/value, ví dụ `beanName=catalog` | Không chứa secret/PII |
| `startTime`, `endTime` | Thời điểm bắt đầu/kết thúc khoảng đo | Cần đối chiếu với clock/recording |
| `duration` | ISO-8601 Duration như `PT0.812S` | Là string, không phải numeric ms |

Không lấy `id` của step giữa hai lần chạy để ghép tương ứng: ID được cấp cho từng recording. So theo **name + tags + ngữ cảnh**, không theo số ID trần.

## 3. Điều kiện một phép đo có thể tái hiện

Trước khi code:
- Chạy `java -version` và xác nhận JDK **17+**.
- Chạy `mvn -version` để xác nhận Maven và Java mà Maven dùng.
- Giữ nguyên artifact, JVM flags, profiles, CPU quota, RAM/heap, tài nguyên downstream cho hai lần chạy.
- Không bật Devtools restart giữa lượt đo; dùng **JVM process mới** cho slow và fast.
- Xác nhận port `18096` chưa bị process khác sử dụng.
- Chờ readiness trước khi lấy snapshot Actuator; app chưa startup hoàn tất có thể chưa phục vụ HTTP.
- Không gọi `POST /actuator/startup` trước khi lưu bản GET.
- Không coi một lần startup đủ làm performance conclusion production.
- Nếu gặp failure ngay trong bootstrap, endpoint HTTP có thể không mở; cần stack trace/FailureAnalyzer hoặc JFR chạy từ đầu.

Phép đo **toàn bộ** từ process spawn đến readiness không đồng nghĩa timeline. Buffering tracker chỉ đo những **đoạn được instrumented** và có thể chưa bao phủ JVM bootstrap trước `main`, external routing/readiness propagation hay các công việc sau context refresh.

## 4. Tạo dự án Maven Spring Boot

Cấu trúc:

~~~text
startup-buffer-lab/
├── pom.xml
├── measure.sh
├── analyze_startup.py
└── src/
    ├── main/
    │   ├── java/com/example/startupbuffer/
    │   │   ├── StartupBufferApplication.java
    │   │   ├── CatalogConfiguration.java
    │   │   └── CatalogController.java
    │   └── resources/application.yaml
    └── test/java/com/example/startupbuffer/
        └── CatalogConfigurationTest.java
~~~

`measure.sh` và `analyze_startup.py` là tiện ích phân tích trên **máy phát triển**. Ứng dụng Java không phụ thuộc Python khi chạy trong production.

### 4.1. pom.xml

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
    <artifactId>startup-buffer-lab</artifactId>
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

**Maven parent 3.5.16** quản lý dependencies cho Boot/Framework và JUnit. Project không cần Spring Security chỉ để làm lab, nhưng ứng dụng thật cần bảo vệ endpoint `startup`.

### 4.2. src/main/resources/application.yaml

~~~yaml
spring:
  application:
    name: startup-buffer-lab
  main:
    banner-mode: "off"

server:
  port: 18096

demo:
  catalog:
    delay-ms: 800

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,startup
~~~

- `demo.catalog.delay-ms` là tham số thực nghiệm, không phải cấu hình chuẩn của Spring Boot.
- `management.endpoints.web.exposure.include` cho phép endpoint `startup` qua HTTP **trong lab**.
- Các endpoint readiness/health giúp quan sát khi application đã ready.
- Đừng expose thông tin tên bean/class/tags cho public Internet; cấu hình security/network/access theo chính sách hệ thống thực.

### 4.3. src/main/java/com/example/startupbuffer/StartupBufferApplication.java

~~~java
package com.example.startupbuffer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupBufferApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupBufferApplication.class);

        // Tracker PHẢI gắn trước run() để có các framework steps.
        application.setApplicationStartup(
                new BufferingApplicationStartup(4096));

        application.run(args);
    }
}
~~~

`4096` là capacity ví dụ. Bộ đệm chỉ lưu **tối đa capacity steps**; khi đầy, new steps không được ghi. Nó **không** là ring buffer tự đè lên steps cũ.

Spring Boot có thể cung cấp recorder đã được cấu hình vào bean factory để application components inject; đừng tự khai báo một `@Bean BufferingApplicationStartup` khác rồi vô tình có hai instance không thống nhất với tracker trong `SpringApplication`.

### 4.4. src/main/java/com/example/startupbuffer/CatalogConfiguration.java

~~~java
package com.example.startupbuffer;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;

@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    CatalogData catalog(
            ApplicationStartup applicationStartup,
            Environment environment) {

        long delayMillis = environment.getProperty(
                "demo.catalog.delay-ms", Long.class, 800L);

        StartupStep step =
                applicationStartup.start("demo.catalog.initialize");

        step.tag("component", "catalog");
        step.tag("delayMode",
                delayMillis == 0 ? "fast" : "slow");

        try {
            if (delayMillis < 0 || delayMillis > 10000) {
                throw new IllegalArgumentException(
                        "delay-ms must be between 0 and 10000");
            }

            if (delayMillis > 0) {
                Thread.sleep(delayMillis);
            }

            System.out.println(
                    "CATALOG_INITIALIZED items=3 delay_ms="
                            + delayMillis);

            return new CatalogData(
                    List.of("alpha", "beta", "gamma"));

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog initialization interrupted", e);
        } finally {
            step.end();
        }
    }

    public record CatalogData(List<String> items) {
    }
}
~~~

**Phân tích:**

1. Bean `catalog` được tạo như singleton trong bootstrap.
2. Factory method nhận `ApplicationStartup` và `Environment` do Spring quản lý; không cần tạo recorder riêng trong method.
3. Custom step `demo.catalog.initialize` đo khoảng từ trước validation/sleep tới lúc kết thúc factory method.
4. `step.tag` ghi metadata ổn định, không lộ secrets.
5. `try/finally` giúp step hoàn tất ngay cả khi validation ném exception.
6. Khi `delayMillis=800`, `Thread.sleep(800)` chỉ mô phỏng một đoạn initialization chậm; khi bằng 0, không sleep.
7. `CatalogData` là Java record, trả danh sách cố định. Hai nhánh thực nghiệm có **cùng dữ liệu đầu ra**.

Không nên dùng `Thread.sleep` trong startup production để “đợi database sẵn sàng”. Trong ứng dụng thật cần connection timeout, validation/retry policy rõ ràng, migrate/schema checks và readiness semantics đúng.

### 4.5. src/main/java/com/example/startupbuffer/CatalogController.java

~~~java
package com.example.startupbuffer;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final CatalogConfiguration.CatalogData catalog;

    public CatalogController(
            CatalogConfiguration.CatalogData catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/catalog")
    public List<String> catalog() {
        return catalog.items();
    }
}
~~~

Controller ép Spring xử lý dependency vào `CatalogData` và giúp kiểm tra chức năng không đổi giữa slow/fast. Một “tối ưu” không có ý nghĩa nếu chỉ bỏ công việc cần thiết rồi API trả dữ liệu sai.

### 4.6. Build

~~~bash
mvn -q -DskipTests package
~~~

Sau khi tạo file JUnit ở mục 12:

~~~bash
mvn -q test
~~~

Project có hai phần: **application + recorder**, và **test parser/performance observation**. Chỉ khi JAR thực sự build thành công mới chạy các lệnh `java -jar` tiếp theo.

## 5. Chạy và lưu timeline slow

Ở Terminal A:

~~~bash
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar \
  --demo.catalog.delay-ms=800
~~~

Đối với Windows PowerShell, sử dụng lệnh một dòng:

~~~powershell
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar --demo.catalog.delay-ms=800
~~~

Dòng do ứng dụng tự in khi bean được tạo:

~~~text
CATALOG_INITIALIZED items=3 delay_ms=800
~~~

Boot còn có các log startup riêng, không thể dùng một chuỗi stdout cứng cho mọi bản JVM/logging config.

Ở Terminal B, đợi server ready rồi kiểm tra:

~~~bash
curl -fsS http://127.0.0.1:18096/catalog
curl -fsS http://127.0.0.1:18096/actuator/health/readiness
~~~

Body `/catalog` dự kiến:

~~~json
["alpha","beta","gamma"]
~~~

Khi ứng dụng sẵn sàng, readiness health thường trả JSON có `"status":"UP"` dưới cấu hình mặc định. Nếu không, hãy đọc startup log; không lấy một lỗi kết nối HTTP làm bằng chứng duration.

### Lưu dữ liệu trước khi drain

~~~bash
curl -fsS http://127.0.0.1:18096/actuator/startup \
  -o slow-startup.json
~~~

Lệnh này dùng **GET**, chỉ đọc snapshot và **không xóa buffer**. Khi lưu thành công, file `slow-startup.json` chứa timeline có những `StartupStep` đã record.

Nếu đã cài `jq`:

~~~bash
jq '.springBootVersion' slow-startup.json
jq '.timeline.events | length' slow-startup.json
~~~

**Nếu events rỗng:** có thể app đang dùng no-op tracker, đã bị drain trước đó hoặc bạn gọi nhầm process/port. Đừng kết luận “app không có bước khởi động”.

### Tìm custom step

~~~bash
jq '.timeline.events[]
    | select(.startupStep.name == "demo.catalog.initialize")' \
  slow-startup.json
~~~

Mẫu **minh họa cấu trúc**, không phải số đo cố định:

~~~json
{
  "startTime": "2026-01-01T10:00:00Z",
  "endTime": "2026-01-01T10:00:00.801Z",
  "duration": "PT0.801S",
  "startupStep": {
    "name": "demo.catalog.initialize",
    "id": 101,
    "parentId": 100,
    "tags": [
      {"key": "component", "value": "catalog"},
      {"key": "delayMode", "value": "slow"}
    ]
  }
}
~~~

**Không** dùng `101` hay `801 ms` làm expected output cho JUnit. ID/timestamps/duration do môi trường quyết định. Giá trị delay là một *input* 800 ms, không phải cam kết thời gian đo sẽ đúng chính xác 800 ms.

### Tìm spring.beans.instantiate của catalog

~~~bash
jq '.timeline.events[]
    | select(.startupStep.name == "spring.beans.instantiate")
    | select(any(.startupStep.tags[]?;
        .key == "beanName" and .value == "catalog"))' \
  slow-startup.json
~~~

Nếu thấy bean `catalog` mất nhiều thời gian và custom `demo.catalog.initialize` nằm bên dưới nó (theo ID/parent/timestamps), đây là bằng chứng phần việc chậm nằm ở factory method. Nếu bean có tên khác do wiring, hãy xem tags thực tế thay vì áp đặt một ID.

**Không cộng duration của parent và child**: thời gian custom thường **đã nằm trong** khoảng tạo bean.

## 6. Chạy và lưu timeline fast

Dừng JVM slow bằng Ctrl+C hoặc gửi TERM cho đúng PID. Chỉ khi port `18096` không còn bị process cũ dùng, chạy một JVM mới:

~~~bash
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar \
  --demo.catalog.delay-ms=0
~~~

Dòng do code tự in:

~~~text
CATALOG_INITIALIZED items=3 delay_ms=0
~~~

Thu snapshot:

~~~bash
curl -fsS http://127.0.0.1:18096/catalog
curl -fsS http://127.0.0.1:18096/actuator/startup \
  -o fast-startup.json
~~~

Body `/catalog` vẫn là:

~~~json
["alpha","beta","gamma"]
~~~

Tại chế độ fast, custom step vẫn tồn tại nhưng không còn `Thread.sleep(800)`. Do đó khi so sánh **chính custom step**, slow thường dài hơn fast rõ rệt. Số chênh lệch thực được script đọc từ hai file, không phải từ lời mô tả của bài.

### Xem nhanh với jq

~~~bash
jq -r '.timeline.events[]
    | select(.startupStep.name == "demo.catalog.initialize")
    | [.duration, .startupStep.id, .startupStep.parentId]
    | @tsv' slow-startup.json

jq -r '.timeline.events[]
    | select(.startupStep.name == "demo.catalog.initialize")
    | [.duration, .startupStep.id, .startupStep.parentId]
    | @tsv' fast-startup.json
~~~

Lưu ý `duration` là **chuỗi ISO-8601** như `PT0.800S`. Muốn sort/trừ phải parse thành numeric milliseconds, không sort chuỗi nguyên văn.

## 7. Đọc response JSON và quy tắc GET/POST

Spring Boot Actuator 3.5 mô tả response (mẫu rút gọn):

~~~json
{
  "springBootVersion": "3.5.16",
  "timeline": {
    "startTime": "2026-01-01T10:00:00Z",
    "events": [
      {
        "startTime": "2026-01-01T10:00:00.100Z",
        "endTime": "2026-01-01T10:00:00.120Z",
        "duration": "PT0.020S",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 3,
          "parentId": 2,
          "tags": [
            {"key": "beanName", "value": "someBean"}
          ]
        }
      }
    ]
  }
}
~~~

`duration` là dạng `java.time.Duration.toString()`, thường có biểu diễn `PT...S`; khi parsing có thể dùng `Duration.parse()` trên Java hoặc parser ISO phù hợp trên công cụ khác.

### GET — xem snapshot

~~~bash
curl -fsS -X GET \
  http://127.0.0.1:18096/actuator/startup \
  -o snapshot.json
~~~

Không chủ động xóa data trong buffer; phù hợp thăm dò.

### POST — drain

~~~bash
curl -fsS -X POST \
  http://127.0.0.1:18096/actuator/startup \
  -o drained.json
~~~

Trả dữ liệu và **loại** các steps đã được buffered. Một lần GET tiếp theo có thể chỉ còn rất ít events hoặc rỗng. Không dùng POST để “xem thử” rồi bỏ response nếu còn muốn đo lần đó.

Nếu có hai monitoring clients cùng POST, client sau có thể không còn bản ghi mà client trước đã lấy. Cần chỉ định **một consumer chịu trách nhiệm drain** nếu đưa dữ liệu sang analytics pipeline.

### Capacity và filter

Theo Spring Boot 3.5 Javadoc:
- `new BufferingApplicationStartup(4096)` tự bắt đầu recording.
- Khi bộ đệm đầy, **new steps không được record**; không phải ring buffer ghi đè.
- `addFilter(Predicate<StartupStep>)` chỉ giữ những bước thỏa mọi filters.
- `getBufferedTimeline()` đọc snapshot.
- `drainBufferedTimeline()` lấy và xóa các buffered steps.
- `startRecording()` không cần gọi lại; gọi khi đã có steps có thể ném `IllegalStateException`.

Nếu filter bỏ mất parent steps, chuỗi `parentId` có thể không còn dựng được dù custom step vẫn tồn tại. Trong lượt điều tra đầu nên ưu tiên đủ capacity và ít lọc.

## 8. Phân tích JSON tự động bằng Python 3 standard library

Để so sánh hai snapshots mà không phải đếm bằng mắt, tạo **`analyze_startup.py`** ở project root.

Script:
- đọc cả hai file JSON;
- parse Duration ISO-8601 thành milliseconds bằng `Decimal`;
- tìm custom step `demo.catalog.initialize`;
- sort Top 8 steps theo **numeric duration**;
- tìm parent chain theo `id`/`parentId` nếu các events liên quan đã được giữ;
- in duration slow, fast và delta **từ dữ liệu thực**.

~~~python
#!/usr/bin/env python3
import json
import re
import sys
from decimal import Decimal

DURATION = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?$"
)
TARGET = "demo.catalog.initialize"


def milliseconds(text):
    match = DURATION.fullmatch(text)
    if match is None:
        raise ValueError("Unsupported ISO duration: " + text)

    hours, minutes, seconds = match.groups()
    total = (
        Decimal(hours or "0") * 3600
        + Decimal(minutes or "0") * 60
        + Decimal(seconds or "0")
    )
    return total * 1000


def tags(event):
    return {
        tag["key"]: tag["value"]
        for tag in event["startupStep"].get("tags", [])
    }


def describe(event):
    step = event["startupStep"]
    bean = tags(event).get("beanName")
    label = step["name"] + ((" bean=" + bean) if bean else "")
    return label + " ms=" + f"{milliseconds(event['duration']):.3f}"


def print_parents(event, by_id):
    parent = event["startupStep"].get("parentId")
    visited = set()
    found = False

    while parent is not None and parent in by_id:
        if parent in visited:
            print("  cycle-detected")
            return

        visited.add(parent)
        current = by_id[parent]
        print("  PARENT " + describe(current))
        found = True
        parent = current["startupStep"].get("parentId")

    if not found:
        print("  PARENT not available in snapshot")


def analyze(path):
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)

    events = payload["timeline"]["events"]
    by_id = {
        event["startupStep"]["id"]: event
        for event in events
    }
    matches = [
        event
        for event in events
        if event["startupStep"]["name"] == TARGET
    ]

    print("FILE=" + path)
    print("BOOT=" + payload["springBootVersion"])
    print("EVENTS=" + str(len(events)))

    if len(matches) != 1:
        raise ValueError(
            "Expected one custom startup step, found "
            + str(len(matches))
            + ". Check buffer capacity, filters, mode and bean."
        )

    selected = matches[0]
    duration = milliseconds(selected["duration"])

    print("CUSTOM " + describe(selected))
    print("TAGS " + str(tags(selected)))
    print_parents(selected, by_id)

    print("TOP_INCLUSIVE_STEPS:")
    top = sorted(
        events,
        key=lambda event: milliseconds(event["duration"]),
        reverse=True
    )
    for event in top[:8]:
        print("  " + describe(event))

    return duration


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python3 analyze_startup.py "
            "slow-startup.json fast-startup.json"
        )

    slow = analyze(sys.argv[1])
    print()
    fast = analyze(sys.argv[2])
    delta = slow - fast

    print()
    print(f"SLOW_CUSTOM_MS={slow:.3f}")
    print(f"FAST_CUSTOM_MS={fast:.3f}")
    print(f"CUSTOM_DELTA_MS={delta:.3f}")
    print("Delta is for the custom step, not total app startup.")


if __name__ == "__main__":
    main()
~~~

Chạy sau khi đã có hai JSON:

~~~bash
python3 analyze_startup.py \
  slow-startup.json fast-startup.json
~~~

Không thể viết một output số cố định cho script vì hai file JSON lấy từ **hai lần chạy thật**. Nó tự in `CUSTOM_DELTA_MS`, duration của từng step và danh sách lớn nhất.

### Tại sao dùng Decimal?

Vì `PT0.12S` và `PT0.9S` không thể sort trực tiếp theo text như số milliseconds; `Decimal` giúp không phát sinh lỗi so sánh do cách parse string. Regex có chủ ý hỗ trợ dạng duration không âm `PT[H]H[M]M[S]S` thường gặp. Nếu response chứa một biến thể ISO khác, script báo lỗi rõ ràng để mở rộng parser thay vì âm thầm kết luận sai.

### Không tự suy root cause từ Top 8

Nếu top có `spring.context.refresh`, `spring.beans.instantiate` và `demo.catalog.initialize`, ba event có thể phản ánh **cùng thời gian bị lồng nhau**. Top list là nơi bắt đầu điều tra, **không phải bảng cộng tổng chi phí**. Sự cải thiện của custom step được xác nhận bởi thay đổi input delay và source code; với một hệ thống thật cần thêm JFR/CPU/DB metrics để tìm lý do.

## 9. Tự động chạy 2 mode với Bash

Tạo file **`measure.sh`**. Script chạy **hai JVM nối tiếp**, lấy JSON bằng GET, không drain, không dùng PID cũ. Dành cho Linux/macOS có Bash/curl và Python 3.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

jar="target/startup-buffer-lab-0.0.1-SNAPSHOT.jar"
base="http://127.0.0.1:18096"
pid=""

cleanup() {
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

run_mode() {
  local mode="$1"
  local delay="$2"
  local ready="no"

  java -jar "$jar" "--demo.catalog.delay-ms=$delay" \
    >"$mode.log" 2>&1 &
  pid=$!

  for ((i=0; i<180; i++)); do
    if curl -fsS --max-time 1 \
        "$base/actuator/health/readiness" \
        >/dev/null 2>&1; then
      ready="yes"
      break
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "App exited early: $mode" >&2
      return 1
    fi
    sleep 0.2
  done

  if [[ "$ready" != "yes" ]]; then
    echo "Readiness timeout: $mode" >&2
    return 1
  fi

  curl -fsS "$base/catalog" >"$mode-catalog.json"
  curl -fsS "$base/actuator/startup" \
    >"$mode-startup.json"

  echo "Saved $mode-startup.json"

  kill -TERM "$pid"
  wait "$pid" || true
  pid=""
}

run_mode slow 800
run_mode fast 0
python3 analyze_startup.py \
  slow-startup.json fast-startup.json
~~~

Chạy:

~~~bash
mvn -q -DskipTests package
bash measure.sh
~~~

**Cảnh báo về port ownership:** trước khi chạy bảo đảm không có ứng dụng khác đang listen trên `18096`. Readiness của một process khác có thể đánh lừa một script quá đơn giản. Xem cả `slow.log`/`fast.log`, log `CATALOG_INITIALIZED` và ứng dụng đúng URL trước khi tin dữ liệu.

Nếu app không ready, script thoát khác 0 và gửi TERM cho JVM đang chạy thông qua trap. `wait` có thể vẫn kéo dài nếu shutdown hook/worker của ứng dụng bị treo; trong CI cần deadline/watchdog ngoài. Đây là lab đơn giản, không thay cho harness benchmark production.

### Windows PowerShell

Có thể chạy hai lệnh `java -jar` lần lượt ở terminal và lưu HTTP JSON bằng:

~~~powershell
curl.exe -fsS -o slow-startup.json http://127.0.0.1:18096/actuator/startup
~~~

Sau khi dừng lần slow và khởi động fast, đổi output name thành `fast-startup.json`. Dùng `curl.exe` để tránh alias `curl` trong PowerShell cũ và giữ raw HTTP body. Script Python vẫn dùng được nếu máy đã cài Python 3.

## 10. Phân tích parent-child, inclusive time và self time

Một trong những lỗi lớn nhất khi phân tích startup timeline là **cộng thời gian của các steps đang chồng nhau**.

Mô hình:

~~~mermaid
flowchart TD
  ROOT["spring.context.refresh: inclusive time"] --> BEAN["spring.beans.instantiate(catalog)"]
  BEAN --> CUSTOM["demo.catalog.initialize"]
  ROOT --> OTHER["Các bean/post-processors khác"]
~~~

Ví dụ **số liệu hoàn toàn minh họa**:
- `spring.context.refresh`: 1.100 ms;
- `spring.beans.instantiate(catalog)`: 830 ms;
- `demo.catalog.initialize`: 802 ms.

**Sai:** kết luận refresh mất 1.100 + 830 + 802 = 2.732 ms.

**Đúng:** khoảng 802 ms có thể nằm trong 830 ms và cả hai nằm trong 1.100 ms. Cần dùng `parentId`, timestamps và source code để xác định mối quan hệ. Nếu có nhiều child intervals đồng thời, muốn tính **exclusive self time** phải trừ union các khoảng con sau khi xử lý overlap, không chỉ lấy parent trừ tổng các child durations.

Một step bao gồm thời gian chờ I/O, lock, GC hay scheduling. `StartupStep.duration` là **elapsed time**, không phải profiler CPU samples. Nó xác định “**đoạn nào lâu**”, nhưng không đủ để kết luận “**tại sao lâu**” nếu chưa xem code/các metrics khác.

### Nhận diện vị trí cần kiểm tra trong ứng dụng thật

| Nhóm step | Nơi xem tiếp | Khả năng chậm |
| --- | --- | --- |
| `spring.context.refresh` | Toàn bộ refresh phase | Bao gồm nhiều bước con, không tự là nguyên nhân cụ thể |
| `spring.context.base-packages.scan` | Base package/component scan | Quét phạm vi quá rộng |
| `spring.context.config-classes.parse` | Configuration class graph | Imports/conditions nhiều, metadata parsing |
| `spring.context.bean-factory.post-process` | BeanFactoryPostProcessor | Custom processors chậm |
| `spring.context.beandef-registry.post-process` | BeanDefinitionRegistryPostProcessor | Scan và bean definitions |
| `spring.context.beans.post-process` | BeanPostProcessor/proxies | Reflection/proxy/init logic |
| `spring.beans.instantiate` | Bean factory/constructor/dependencies | I/O synchronous, cache preload, connection |
| `spring.beans.smart-initialize` | SmartInitializingSingleton | Warmup việc dài |
| `demo.catalog.initialize` | Method do lab định nghĩa | Sleep 800 ms có thể loại bỏ trong mode fast |

Các tên `spring.*` là **implementation details của Spring Framework**, có thể đổi giữa versions; đừng viết một CI assertion đòi mọi bước xuất hiện với số lượng và ID cố định.

### Một checklist phân tích root cause

1. Lọc các events có duration lớn bằng **numeric Duration**, không phải sort string.
2. Bỏ qua bước cha trùng lặp khi đang tìm nguồn chậm sâu hơn.
3. Lần theo `parentId` từ custom/bean step để biết bối cảnh.
4. Tìm `beanName` và tags khác; xác định class/factory method trong source.
5. Đặt custom step quanh đoạn nghi vấn nếu framework instrumentation chưa đủ chi tiết.
6. Đối chiếu CPU/GC/JFR/I/O/DB traces nếu duration không thể giải thích bằng code.
7. Tạo biến thể **một thay đổi**, đo lại, và xác nhận response/behavior không sai.
8. Đừng dùng một số duration từ warm startup rồi tuyên bố cold process startup sẽ giảm tương đương.

## 11. Đo ứng dụng khởi động “xong” ở mốc nào?

Có ít nhất bốn khái niệm:

| Chỉ số | Mốc bắt đầu/kết thúc | Công cụ |
| --- | --- | --- |
| `T_process_ready` | Spawn JVM → readiness endpoint healthy | Harness ngoài process |
| `T_main_ready` | Bắt đầu `main` → `ApplicationReadyEvent` | Monotonic clock/log |
| `T_context_refresh` | Thực thi context refresh | `spring.context.refresh` |
| `T_custom_catalog` | Đầu và cuối method tạo catalog | `demo.catalog.initialize` |

**Không đồng nhất các mốc này.** `ApplicationStartedEvent` được phát sau context refresh nhưng **trước** `ApplicationRunner`/`CommandLineRunner`. `ApplicationReadyEvent` được phát **sau** runners, rồi Spring Boot có thể chuyển readiness sang ACCEPTING_TRAFFIC. Kubernetes routing/endpoint propagation tiếp tục có thể tạo thêm độ trễ bên ngoài JVM.

Nếu tối ưu chỉ số ở custom step nhưng readiness không cải thiện nhiều, hãy xem phần thời gian khác như JVM bootstrap, class loading, GC, server init, runners, remote config hoặc external readiness polling.

### Ví dụ đo từ bên ngoài (snippet Linux)

~~~bash
start_ns=$(date +%s%N)
java -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar \
  --demo.catalog.delay-ms=800 &
pid=$!

# Thực hiện readiness polling có timeout như trong measure.sh.
# Đo ngay khi readiness trả kết quả thành công.
end_ns=$(date +%s%N)
ready_ms=$(( (end_ns - start_ns) / 1000000 ))
echo "$ready_ms"
~~~

Đây là **snippet phương pháp**, không phải script tự chạy hoàn chỉnh: nếu copy nguyên mà không thêm readiness loop, `end_ns` sẽ bị lấy quá sớm. Với mã có thể chạy end-to-end, dùng cấu trúc `measure.sh` rồi thêm hai mốc tương ứng.

Trên macOS mặc định, `date +%s%N` không hoạt động giống GNU date; có thể dùng Python `time.perf_counter_ns()` trong harness hoặc công cụ monitor khác. Đừng trộn timestamps của nhiều máy không đồng bộ clock khi tính duration.

## 12. JUnit 5 kiểm thử custom StartupStep

Tạo file **`src/test/java/com/example/startupbuffer/CatalogConfigurationTest.java`**:

~~~java
package com.example.startupbuffer;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CatalogConfigurationTest {

    @Test
    void customStepIsRecorded() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(16);

        MockEnvironment environment = new MockEnvironment()
                .withProperty("demo.catalog.delay-ms", "0");

        CatalogConfiguration configuration =
                new CatalogConfiguration();

        CatalogConfiguration.CatalogData data =
                configuration.catalog(tracker, environment);

        assertThat(data.items())
                .containsExactly("alpha", "beta", "gamma");

        List<StartupTimeline.TimelineEvent> events =
                tracker.getBufferedTimeline().getEvents();

        assertThat(events).hasSize(1);
        assertThat(events.get(0).getStartupStep().getName())
                .isEqualTo("demo.catalog.initialize");

        assertThat(events.get(0).getDuration())
                .isGreaterThanOrEqualTo(Duration.ZERO);
    }

    @Test
    void failureAlsoEndsTheStep() {
        BufferingApplicationStartup tracker =
                new BufferingApplicationStartup(16);

        MockEnvironment environment = new MockEnvironment()
                .withProperty("demo.catalog.delay-ms", "-1");

        assertThatThrownBy(() ->
                new CatalogConfiguration().catalog(
                        tracker, environment))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("between 0 and 10000");

        List<StartupTimeline.TimelineEvent> events =
                tracker.getBufferedTimeline().getEvents();

        assertThat(events).hasSize(1);
        assertThat(events.get(0).getStartupStep().getName())
                .isEqualTo("demo.catalog.initialize");
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Hai tests kiểm tra:
- Factory method trả dữ liệu đúng và hoàn tất custom `StartupStep`.
- Nhánh lỗi vẫn gọi `step.end()` do có `finally`.
- Test không dùng sleep làm assertions về thời gian, nên ít flaky hơn benchmark dựa vào ngưỡng milliseconds chính xác.

**Giới hạn:** đây là unit test của method custom, **không** chứng minh rằng toàn bộ Spring container luôn phát các `spring.*` steps với thứ tự/ID nhất định. Để kiểm tra instrumentation của startup đầy đủ, phải chạy JAR và đọc endpoint qua integration run.

## 13. Đọc BufferingApplicationStartup trực tiếp bằng Java

Không bắt buộc phải dùng Actuator để đọc một buffer instance. Java API có:

~~~java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(16);

StartupStep step = recorder.start("demo.short.task");
try {
    // Mã cần đo.
} finally {
    step.end();
}

StartupTimeline snapshot = recorder.getBufferedTimeline();
for (StartupTimeline.TimelineEvent event :
        snapshot.getEvents()) {
    System.out.println(event.getStartupStep().getName()
            + " " + event.getDuration());
}
~~~

Đây là **snippet**, cần imports:
- `BufferingApplicationStartup`,
- `StartupTimeline`,
- `StartupStep`.

Snapshot không làm mất dữ liệu. Nếu gọi:

~~~java
StartupTimeline drained = recorder.drainBufferedTimeline();
~~~

thì các buffered steps được lấy ra khỏi buffer. Trong ứng dụng Boot thật, chỉ đọc **instance đã gắn vào SpringApplication**; một recorder mới tạo sau startup không chứa các steps cũ.

`BufferingApplicationStartup` có thể được inject vào một bean quản lý bởi Spring Boot khi đã cấu hình tracker đó. Nhưng nếu bạn tự drain trong `ApplicationRunner`, dữ liệu của Actuator sau đó có thể thiếu — chúng có thể chia sẻ một buffer.

## 14. Thực hiện A/B một cách khoa học hơn

Thí nghiệm 800 ms là để học cơ chế. Với workload thật:
1. Chốt artifact checksum, Spring Boot/JDK versions, profiles và JVM flags.
2. Cố định CPU/RAM/quota, external services, data size và network.
3. Chạy slow/fast theo thứ tự xen kẽ ở nhiều JVM mới: A→B→B→A.
4. Lưu JSON mỗi lần ngay sau readiness.
5. Ghi `T_process_ready` và `T_custom`, không thay thế một cái bằng cái kia.
6. Tách cold-start/first-run với warm OS cache nếu cần.
7. Tính median, p95, error rate và độ biến thiên, không chỉ so hai số đơn lẻ.
8. Kiểm tra hiệu năng endpoint cold request sau tối ưu.
9. Giữ đúng dữ liệu/transactions/ready semantics.
10. Chỉ tuyên bố cải thiện khi kết quả vượt nhiễu đo và không tạo regression.

**Một biến mỗi lượt** là nền tảng để phân tích nhân quả: nếu vừa đổi Spring version, thêm cache, đổi datasource pool và bỏ sleep thì không thể phân bổ chênh lệch startup cho một nguyên nhân riêng.

### Lazy initialization có thể chuyển chi phí sang first request

`spring.main.lazy-initialization=true` đôi khi giảm thời gian khởi tạo eagerly, nhưng có thể làm bean lỗi/chậm **sau readiness**. Trước khi dùng:
- có được phép báo ready khi bean chưa khả dụng không?
- cold first request có đáp ứng SLO không?
- có cần fail-fast để phát hiện credential/schema lỗi sớm không?
- heap và thread capacity có chịu được concurrent lazy initialization không?

Không thay hoạt động đúng của hệ thống bằng một startup metric thấp hơn.

## 15. Khi buffer không giải thích được lý do chậm

`BufferingApplicationStartup` giúp thấy các **bước instrumented**, không thu mọi stack trace/cpu sample. Nếu một bước lớn nhưng source chưa giải thích được, có thể dùng **`FlightRecorderApplicationStartup`** trong một **lượt chạy riêng**.

~~~java
SpringApplication app = new SpringApplication(MyApp.class);
app.setApplicationStartup(
        new FlightRecorderApplicationStartup());
app.run(args);
~~~

Đây là snippet, cần import `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup` và class `MyApp` phù hợp. Khi chạy JAR cần bật JFR:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,dumponexit=true,settings=profile \
  -jar target/startup-buffer-lab-0.0.1-SNAPSHOT.jar
~~~

Đối với project hiện tại, phải **sửa tracker trong main** thành FlightRecorder trước khi build lại để lệnh trên thực sự ghi Spring-specific startup events. Chỉ bật JFR flag mà giữ Buffering tracker không tự chuyển các buffered steps thành JFR events.

JFR có thể giúp liên kết startup với allocations, classloading, GC và CPU behavior, nhưng endpoint `/actuator/startup` của Boot dành cho Buffering tracker; ở chế độ JFR không nên trông chờ cùng timeline JSON từ endpoint đó.

## 16. Troubleshooting khi chạy lab

| Triệu chứng | Kiểm tra đầu tiên | Cách sửa |
| --- | --- | --- |
| `/actuator/startup` trả 404 | Actuator dependency, web exposure/access và tracker | Expose `startup` đúng, kiểm tra Boot config |
| `/actuator/startup` trả 401/403 | Endpoint bị Spring Security bảo vệ | Dùng quyền truy cập hợp lệ, không mở public |
| Events rỗng | No-op tracker hoặc đã drain | `setApplicationStartup` trước `run`, dùng GET |
| Chỉ có rất ít events | Capacity nhỏ/filter hoặc gọi POST trước | Tăng capacity, bỏ filter chẩn đoán, chạy mới |
| Custom step không có | Bean không tạo, filter/buffer loại, nhầm instance | Kiểm tra log `CATALOG_INITIALIZED` và mode |
| `parentId` không có | Step top-level hoặc parent không record | Dùng timestamps/source, không tự tạo parent |
| Thời gian kiểu `PT0.5S` không sort đúng | Sort như string | Parse numeric Duration |
| Slow/fast JSON trông giống nhau | Chạy cùng PID hoặc delay CLI không áp dụng | Kiểm tra log, URL và `delayMode` |
| App không start | Port `18096` bị chiếm hoặc cấu hình lỗi | Xem startup failure logs, PID, port |
| Fast custom step đã ngắn nhưng ready vẫn chậm | Giai đoạn khác gây chậm | Phân tích Top steps và external readiness |
| Bean tag không có như ví dụ | Framework version/instrumentation khác | Xem raw tags, code và timestamps |
| JUnit pass nhưng HTTP fails | Unit test không khởi tạo Boot web context | Chạy JAR và test Actuator |
| Python parser báo unsupported Duration | ISO format khác regex | Xem JSON và mở rộng parser đúng chuẩn |
| JSON mất sau POST | Drain là thao tác có chủ đích | Lưu GET snapshot trước |
| Process không thoát sau Ctrl+C | Shutdown hooks/non-daemon threads còn sống | Dùng PID/thread dump, kiểm tra resources |
| Timeline nhanh nhưng first request chậm | Lazy init hoặc warm-up bị dời | Đo cold first hit và error rate |
| API startup lộ dữ liệu nội bộ | Endpoint bị expose công khai | Khóa security/network, dùng recording ngắn |
| Monitoring agent đã POST | Shared buffer bị drain | Phối hợp quyền sở hữu việc thu thập |

### Không thấy parent chain không có nghĩa không có nesting

Buffer có thể đã đầy, step cha bị filter, hoặc một custom step không được tạo trong phạm vi đo mà bạn tưởng. Hãy xem full events và timestamps. `parentId` giúp nhiều nhưng không phải bảo đảm hoàn chỉnh về mọi causal dependency.

### Step.duration có phải thời gian CPU?

Không. `duration` đo elapsed processing time, có thể gồm I/O, lock waiting, sleep, GC và scheduler delay. Với CPU bottleneck, cần profiler/JFR CPU samples; với database, cần SQL timings và connection pool metrics.

### Đừng gửi secrets qua tag

Ví dụ `step.tag("password", value)` hoặc URL chứa token là rủi ro. Startup JSON/JFR/logs có thể rời khỏi process và được lưu dài hạn. Dùng tên thành phần/loại thao tác ổn định và kiểm soát quyền endpoint.

## 17. Mẫu báo cáo kết quả cho một ứng dụng thực

Sau các lần đo, ghi một bảng có dữ liệu **đã được thu thực**:

| Trường báo cáo | Cách điền |
| --- | --- |
| Artifact / JAR digest | Hash/version của bản build |
| JDK / Boot / Framework | Từ runtime thực tế |
| Deployment / CPU quota / heap | Từ môi trường đo |
| Recorder | `BufferingApplicationStartup(capacity)` |
| Số events slow/fast | `timeline.events.length` của từng JSON |
| Custom step name | Ví dụ `demo.catalog.initialize` |
| Custom duration slow/fast | Chuyển ISO Duration → ms |
| Parent steps | Theo parentId và tags, khi có |
| Top inclusive steps | Xếp hạng numeric duration |
| Process→ready slow/fast | External stopwatch |
| Cold first request / correctness | Response + latency + errors |
| Số lần lặp, median, p95 | Từ nhiều process |
| Thay đổi đã thử | Một yếu tố xác định |
| Quyết định/rollback | Căn cứ theo SLO và độ tin cậy |

**Không ghi “tiết kiệm 800 ms” khi chưa đo.** Giá trị `delay-ms=800` là input cho thí nghiệm; kết quả là các duration được thực tế thu thập và phân tích.

## 18. Những anti-pattern cần tránh

**1. Chỉ thêm Actuator mà không gắn recorder.**  
`ApplicationStartup.DEFAULT` là no-op, không có timeline mà bạn mong muốn.

**2. Khởi tạo recorder sau context refresh.**  
Không thể lấy lại steps diễn ra trước đó.

**3. Gọi POST khi vẫn cần so sánh dữ liệu.**  
POST drain buffer; GET mới là snapshot không destructive.

**4. Cộng durations của parent và child.**  
Tạo kết quả lớn hơn thời gian startup vì double-count.

**5. Sort `duration` dưới dạng text.**  
Chuỗi ISO Duration không có thứ tự numeric như số ms.

**6. Từ một step chậm suy ra nguyên nhân khi chưa xem source.**  
Elapsed duration chỉ định vị, chưa nói DB, CPU, I/O hay lock.

**7. Tối ưu chỉ bằng cách bật lazy cho toàn app.**  
Có thể đẩy chi phí/lỗi ra runtime và phá cold request SLO.

**8. Dùng data chỉ từ một lần chạy.**  
Nhiễu OS/JIT/cache/CPU làm kết luận thiếu chắc chắn.

**9. Gắn secret vào tag.**  
Metadata có thể bị lộ qua endpoint/logs/recordings.

**10. So `StartupStep.id` giữa hai JVM.**  
ID không phải khóa tương ứng xuyên các recordings.

**11. Tăng capacity vô hạn.**  
Memory/overhead tăng; lựa chọn capacity cần có mục đích.

**12. Dùng Buffering tracker làm request tracing chung.**  
Nó được thiết kế cho startup; request tracing nên dùng Observation/Micrometer/OpenTelemetry.

**13. Quên `step.end()` khi exception.**  
Để recorder giữ incomplete steps hoặc mất bản ghi cần thiết.

**14. Chỉ đo context.refresh mà không đo readiness.**  
Runners và platform routing có thể còn chi phí đáng kể.

## 19. Checklist thực hành

- [ ] Project Java 17+, Spring Boot 3.5.16 đã build.
- [ ] `BufferingApplicationStartup(4096)` được gắn trước `run(args)`.
- [ ] Actuator endpoint `startup` chỉ expose trong môi trường lab an toàn.
- [ ] Code có `demo.catalog.initialize` và `step.end()` trong `finally`.
- [ ] Chạy slow/fast trên hai JVM riêng từ **cùng JAR**.
- [ ] Slow log `CATALOG_INITIALIZED items=3 delay_ms=800`.
- [ ] Fast log `CATALOG_INITIALIZED items=3 delay_ms=0`.
- [ ] `/catalog` trả cùng JSON trong cả hai chế độ.
- [ ] Lưu `slow-startup.json` và `fast-startup.json` bằng GET.
- [ ] Không dùng POST trước khi lưu dữ liệu.
- [ ] Phân tích số events, custom step và tags.
- [ ] Parse `duration` thành numeric milliseconds.
- [ ] Xác định parent-child nếu parentId có sẵn.
- [ ] Không cộng duration của các steps lồng nhau.
- [ ] Đo readiness từ bên ngoài nếu cần kết luận startup end-to-end.
- [ ] Chạy JUnit để test custom instrumentation/cause failure.
- [ ] Ghi version/config/resources và nhiều lượt đo khi muốn so performance.
- [ ] Kiểm tra lazy/init failure/first-hit latency trước khi quyết định tối ưu.
- [ ] Chỉ tuyên bố bottleneck sau khi có source code + data + đối chứng.

## 20. Câu hỏi tự kiểm tra

**1. `BufferingApplicationStartup` cần được cấu hình lúc nào?**  
Trước `SpringApplication.run(...)` để nhận các bước startup sớm.

**2. Chỉ thêm spring-boot-starter-actuator có đủ không?**  
Không. `ApplicationStartup.DEFAULT` là no-op; cần tracker phù hợp.

**3. `StartupStep.end()` vì sao phải nằm trong finally?**  
Để recorder biết bước đã hoàn tất dù có exception.

**4. Buffer đầy có tự ghi đè các bước cũ không?**  
Không; những bước mới không được record khi đạt capacity.

**5. GET và POST /actuator/startup khác nhau thế nào?**  
GET snapshot; POST drain.

**6. `duration` trong JSON có phải numeric ms không?**  
Không, là chuỗi ISO Duration như `PT0.8S`.

**7. ID của step có dùng để match hai lần chạy không?**  
Không, dùng name/tags/ngữ cảnh và dữ liệu tương ứng.

**8. Tại sao không cộng `spring.beans.instantiate` và custom child duration?**  
Có thể đã bao gồm nhau, cộng là double-count.

**9. Một step mất 900 ms có chắc tiêu thụ CPU 900 ms không?**  
Không, duration bao gồm wait/I/O/sleep và những tác động scheduler.

**10. Slow input 800 ms có bảo đảm total startup giảm đúng 800 ms khi tắt không?**  
Không. Đo JSON và readiness thực tế để kết luận.

**11. Vì sao cần A/B trên cùng JAR và JVM độc lập?**  
Để so đúng một biến và tránh lẫn phiên bản hoặc instance khác.

**12. Nếu custom step không xuất hiện, cần kiểm tra gì?**  
Bean đã tạo chưa, tracker đúng chưa, capacity/filter/drain, URL/PID.

**13. ApplicationReadyEvent trước hay sau runners?**  
Sau `ApplicationRunner`/`CommandLineRunner`.

**14. Nếu config refresh nhanh nhưng readiness chậm, cần làm gì?**  
Đo process→ready, runners, bootstrap JVM, probe/routing và bước chưa instrumented.

**15. Có nên dùng FlightRecorderApplicationStartup khi cần CPU/GC correlation không?**  
Có thể, trong lượt đo riêng có JFR recording; Actuator buffer JSON không tự thay thế JFR.

**16. Đưa password vào StartupStep tag có an toàn không?**  
Không; metadata có thể lộ ra ngoài.

## 21. Nguồn tài liệu chính thức

- [Spring Boot 3.5 — SpringApplication và Application Startup Tracking](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): cách gắn tracker trước run, lifecycle events, JFR.
- [Spring Boot 3.5 — Actuator Startup REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html): GET snapshot, POST drain, response JSON fields.
- [Spring Boot 3.5 — BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html): capacity, filter, getBufferedTimeline và drainBufferedTimeline.
- [Spring Boot 3.5 — StartupTimeline API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/StartupTimeline.html): `TimelineEvent`, `getDuration()`, `getStartupStep()`.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): endpoint exposure/access/security/readiness.
- [Spring Framework — Application Startup Steps](https://docs.spring.io/spring-framework/reference/core/appendix/application-startup-steps.html): tên và ngữ nghĩa các steps nội bộ.
- [Spring Framework 6.2 — ApplicationStartup API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html): DEFAULT no-op, start(name).
- [Spring Framework 6.2 — StartupStep API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/StartupStep.html): id, parentId, tags, end().
- [Oracle Java 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): ISO Duration parsing.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): unit testing.

**Kết luận:** Muốn xác định đúng giai đoạn startup chậm, **ghi StartupSteps ngay từ trước `run`, đọc JSON snapshot, phân tích duration và parent-child, truy đến code có tác động, rồi chạy đối chứng trên cùng artifact**. `BufferingApplicationStartup` giúp định vị nơi chậm; nguyên nhân thật phải được chứng minh bằng source/log/JFR/metrics và kiểm tra lại cả readiness, first-hit latency lẫn tính đúng nghiệp vụ.