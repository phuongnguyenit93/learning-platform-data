# Đọc các bước, thẻ và quan hệ cha con trong dữ liệu khởi động Spring Boot

**Module:** Spring Boot Application Runtime → **Đo khởi động**. Bài học giải thích cách đọc dữ liệu của `ApplicationStartup` và `StartupStep`: **tên bước**, **ID**, **tags key/value**, **parentId**, thời điểm bắt đầu/kết thúc và `duration`. Trọng tâm là dựng đúng cây cha–con từ dữ liệu Actuator `/actuator/startup`, tránh nhầm thứ tự mảng với thứ tự thực thi, tránh cộng trùng thời gian các bước lồng nhau và biết khi nào timeline chưa đủ để kết luận nguyên nhân khởi động chậm.

**Ví dụ:** Java **17+**, Spring Boot **3.5.x**, Spring Web, Spring Boot Actuator, Maven; có code Java tạo một step cha và hai step con trong `ApplicationRunner` cùng script Python 3 chỉ dùng thư viện chuẩn để phân tích file JSON. Các timestamp, ID và thời lượng trong sơ đồ minh họa **không phải stdout cố định** của ứng dụng.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Mô tả vòng đời `ApplicationStartup.start(name)` → `StartupStep.tag(...)` → `StartupStep.end()`.
2. Cấu hình `BufferingApplicationStartup` **trước** `SpringApplication.run(...)` để thu thập toàn bộ các bước được instrument trong startup.
3. Dùng `GET /actuator/startup` để lấy **snapshot** và `POST /actuator/startup` để **drain** buffer.
4. Đọc đúng cấu trúc `timeline.events[]`, `startupStep.name/id/parentId/tags`, `startTime/endTime/duration`.
5. Hiểu `parentId` có thể vắng mặt và tham chiếu một step không tồn tại trong bản trích; biết dựng cây bằng ID thay vì sort ID.
6. Phân biệt tên `spring.beans.instantiate` xuất hiện nhiều lần theo tags `beanName`.
7. Đổi chuỗi ISO-8601 duration `PT0.012S` thành **12 milliseconds**.
8. Phân biệt **inclusive elapsed** của cha với exclusive elapsed, biết tính union intervals khi các con chồng thời gian.
9. Tạo step cha `lab.warmup` và hai con `lab.warmup.load`, `lab.warmup.index`; đối chiếu dấu mốc Java và JSON.
10. Dùng `jq`/script để in cây, in tags và xếp hạng duration **theo số**.
11. Hiểu giới hạn buffer capacity, filters, nhiều contexts/replicas và ảnh hưởng của GET/POST.
12. Biết dữ liệu bước khởi động **không tự là biểu đồ bean dependencies, CPU profile hay critical path**.
13. Kết hợp timeline với JFR, logs và đo nhiều lần nếu cần xác định startup bottleneck.
14. Triển khai quan sát có kiểm soát quyền truy cập, không rò PII/secrets từ tags.

**Thông điệp chính:** `id` nhận diện một bước trong một lần thu thập, `parentId` nối cấu trúc đo đạc, `name + tags` giải thích việc gì đã được đo, và `start/end/duration` mô tả thời gian. Đừng chỉ dựa vào một trong các trường đó để suy diễn toàn bộ startup.

## 2. ApplicationStartup và StartupStep là gì?

Spring Framework có interface `org.springframework.core.metrics.ApplicationStartup`. Khi muốn ghi một đoạn công việc, gọi:

~~~java
StartupStep step = startup.start("lab.cache.warmup");
try {
    step.tag("component", "catalog");
    step.tag("entries", "500");
    // Thực hiện công việc ở đây.
} finally {
    step.end();
}
~~~

Đây là **snippet** cần một biến `ApplicationStartup startup` hợp lệ và import `org.springframework.core.metrics.StartupStep`; không phải file Java độc lập.

Một `StartupStep` có:

| API | Vai trò |
|---|---|
| `getName()` | Tên kỹ thuật của bước, thường dạng `namespace.action` |
| `getId()` | ID riêng của bước trong lần startup/recorder |
| `getParentId()` | ID của bước cha nếu có, có thể `null` |
| `getTags()` | Collection các tag key/value của bước |
| `tag(String,String)` | Gắn thêm một tag |
| `tag(String,Supplier<String>)` | Gắn tag với value do supplier cung cấp |
| `end()` | Đánh dấu kết thúc bước, cho recorder tính thời gian |

Gọi `start(...)` **trước** công việc cần đo, thêm tag trước khi kết thúc, rồi `end()` trong `finally`. Nếu quên `end()`, recorder có thể không có một event hoàn chỉnh để cung cấp thời lượng; đừng chỉ ghi tag rồi giả định hệ thống tự đóng span. Không cố gọi `tag(...)` sau khi end; hợp đồng API yêu cầu step kết thúc thì không tiếp tục sửa state.

Tên step nên có namespace rõ như `lab.catalog.load`. Nhiều steps **được phép cùng tên** vì tên chỉ định **loại công việc**, không phải instance duy nhất. Để biết instance cụ thể, đọc ID và tags.

### 2.1. Các recorder

| Implementation | Ghi nhận gì? | Đọc ở đâu? |
|---|---|---|
| `ApplicationStartup.DEFAULT` | Chế độ mặc định tối giản/ít overhead | Không kỳ vọng timeline Actuator chi tiết |
| `BufferingApplicationStartup` (Spring Boot) | Các steps, tags, thời gian trong buffer hữu hạn | `/actuator/startup` hoặc `StartupTimeline` API |
| `FlightRecorderApplicationStartup` (Spring Framework) | Startup events cho Java Flight Recorder | File JFR/JDK Mission Control |

`BufferingApplicationStartup` là lựa chọn hợp lý khi học cách đọc **JSON, tags và parentId**. `FlightRecorderApplicationStartup` phù hợp khi cần liên hệ với CPU, GC, classloading và JVM events; không phải biến thể JSON buffer có thể dùng thay thế mà không thay đổi cách thu thập.

### 2.2. Cấu hình recorder ở đâu?

Cần cấu hình trên `SpringApplication` trước khi chạy:

~~~java
SpringApplication app =
        new SpringApplication(StartupLabApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(4096));
app.run(args);
~~~

`4096` là **số bước tối đa được lưu trong buffer**, không phải kích thước byte hay thời gian milliseconds. Khi capacity đầy, recorder không tiếp tục ghi bước mới; không được coi đây là ring buffer giữ 4096 steps cuối cùng. Với app lớn, số bước thật có thể vượt mốc này.

Chỉ tạo `BufferingApplicationStartup` trong một bean sau startup sẽ quá muộn để ghi các phases ban đầu. Và chỉ khai báo Actuator `startup` exposure khi app vẫn dùng default recorder **không đủ**.

## 3. JSON từ Actuator /actuator/startup

Spring Boot 3.5 dùng dữ liệu tương đương mẫu sau (đã lược bỏ rất nhiều bước):

~~~json
{
  "springBootVersion": "3.5.16",
  "timeline": {
    "startTime": "2026-11-09T08:00:00Z",
    "events": [
      {
        "startTime": "2026-11-09T08:00:00.100Z",
        "endTime": "2026-11-09T08:00:00.240Z",
        "duration": "PT0.140S",
        "startupStep": {
          "id": 100,
          "name": "lab.warmup",
          "parentId": 10,
          "tags": [
            {"key": "component", "value": "catalog"},
            {"key": "environment", "value": "local"}
          ]
        }
      },
      {
        "startTime": "2026-11-09T08:00:00.110Z",
        "endTime": "2026-11-09T08:00:00.155Z",
        "duration": "PT0.045S",
        "startupStep": {
          "id": 101,
          "name": "lab.warmup.load",
          "parentId": 100,
          "tags": [
            {"key": "dataSet", "value": "sample"}
          ]
        }
      },
      {
        "startTime": "2026-11-09T08:00:00.160Z",
        "endTime": "2026-11-09T08:00:00.225Z",
        "duration": "PT0.065S",
        "startupStep": {
          "id": 102,
          "name": "lab.warmup.index",
          "parentId": 100,
          "tags": [
            {"key": "index", "value": "prefix"}
          ]
        }
      }
    ]
  }
}
~~~

Mẫu JSON trên **chỉ minh họa API**. Thời gian, IDs và duration do JVM/runtime đo sẽ thay đổi. `parentId=10` của `lab.warmup` là một step framework đã bị lược khỏi ví dụ. Không coi việc thiếu id 10 trong **đoạn trích này** là lỗi hệ thống.

### 3.1. Các trường cốt lõi

| Path | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `springBootVersion` | String | Phiên bản Spring Boot xuất timeline |
| `timeline.startTime` | String timestamp ISO-8601 | Mốc bắt đầu recording |
| `timeline.events` | Array | Danh sách các events đã được buffer |
| `events[].startTime` | ISO instant | Step bắt đầu lúc nào |
| `events[].endTime` | ISO instant | Step kết thúc lúc nào |
| `events[].duration` | ISO-8601 Duration | Thời gian elapsed của riêng step |
| `events[].startupStep.name` | String | Loại bước được đo |
| `events[].startupStep.id` | Number | ID riêng dùng để nối các bước |
| `events[].startupStep.parentId` | Number, optional | ID step cha nếu có |
| `events[].startupStep.tags` | Array | Danh sách các cặp key/value |
| `tags[].key` | String | Tên nhãn, ví dụ `beanName` |
| `tags[].value` | String | Giá trị nhãn, ví dụ `myService` |

**Không được mặc định parentId bằng 0.** `StartupStep.getParentId()` trả `Long` nullable. Serializer có thể **bỏ trường parentId** khi không có cha, trong khi `id=0` (nếu có) vẫn là một ID bước hợp lệ. Parser nên dùng `step.get("parentId")` và phân biệt `null/missing` với số 0.

### 3.2. Duration là giây ISO, không phải milliseconds

Một số ví dụ:

| Chuỗi duration | Giây | Mili-giây |
|---|---:|---:|
| `PT0.0005S` | 0,0005 | 0,5 |
| `PT0.012S` | 0,012 | 12 |
| `PT0.045S` | 0,045 | 45 |
| `PT0.125S` | 0,125 | 125 |
| `PT1S` | 1 | 1.000 |
| `PT1M3S` | 63 | 63.000 |

Trên Java 17:

~~~java
long millis = java.time.Duration.parse("PT0.125S").toMillis();
System.out.println(millis);  // 125
~~~

Đây là đoạn Java **đặt trong method**, muốn biên dịch độc lập cần bao nó vào class với `public static void main`. Tránh lỗi đọc `PT0.012S` thành “0,012 ms”; hậu tố `S` biểu thị **seconds**.

### 3.3. Thứ tự mảng events không phải thứ tự cha–con

Một child có thể **xuất hiện trước parent trong mảng JSON** vì nó `end()` trước parent; tài liệu REST chính thức cũng minh họa thứ tự đó. Nên:

- Không dựa vào vị trí phần tử trước để chọn parent.
- Không giả định `id=100` phải có trước `id=101` trong mảng.
- Không giả định ID lớn hơn đồng nghĩa bước chạy sau khi bước ID nhỏ **kết thúc**.
- Không suy quan hệ chỉ từ hai timestamps nằm trong nhau.
- Dựng index `id → step` và nối bằng `child.parentId`; sau đó sort siblings theo `startTime` nếu muốn hiển thị.

Đây là khác biệt giữa **biểu diễn danh sách các events** và **cây steps**. Tree layout phải được dựng bởi phép nối quan hệ, không phải bởi cách serializer sắp phần tử.

## 4. Hiểu đúng quan hệ parentId

### 4.1. Quan hệ lồng được ghi bởi instrumentation

Javadoc `StartupStep.getParentId()` mô tả parent là bước đã bắt đầu gần nhất khi bước hiện tại được tạo, theo semantics recorder. Trong đoạn Java:

~~~java
StartupStep parent = startup.start("lab.warmup");
try {
    StartupStep child = startup.start("lab.warmup.load");
    try {
        // Đo công việc con.
    } finally {
        child.end();
    }
} finally {
    parent.end();
}
~~~

Kỳ vọng trong cùng luồng/một recorder đang hoạt động:

~~~text
lab.warmup        id=100
  lab.warmup.load id=101 parentId=100
~~~

Đoạn này là snippet minh họa, cần biến `startup` hợp lệ. Child được tạo khi parent chưa end. Cấu trúc này có nghĩa **đo đạc lồng nhau**, không có nghĩa một bean đã khai báo dependency theo `@DependsOn`, không phải Spring bean graph, và cũng không phải distributed trace sang các service khác.

### 4.2. ID, name, parentId phục vụ vai trò khác nhau

- `id` chỉ định **instance của step** trong một recording.
- `name` chỉ định **loại** step; cùng name có thể xuất hiện hàng trăm lần.
- `parentId` chỉ định **step cha** bằng ID trong recorder.
- `tags` chỉ ra instance/đối tượng cụ thể, ví dụ `beanName`.
- `startTime/endTime` cho biết time interval.
- `duration` cho biết elapsed time, chưa phải CPU cost.

Khi so giữa hai lần startup, đừng nối bằng id vì IDs có thể khác. So theo **name + tags + môi trường đo** rồi kiểm duration distribution; tránh dùng mỗi tên nếu có nhiều instances.

### 4.3. Root và cha không được ghi

Các trường hợp gặp `parentId`:

| Dữ liệu | Diễn giải | Xử lý |
|---|---|---|
| `parentId` vắng mặt/null | Step không có parent do recorder biết | Hiển thị top-level |
| `parentId=100` và id 100 có trong JSON | Có liên kết rõ | Gắn làm child của 100 |
| `parentId=100` nhưng id 100 vắng mặt | Snapshot/filters/capacity/trích một phần | Gắn nhãn **missing parent** |
| `parentId=0` | Parent là step ID 0 nếu nó tồn tại | Không đổi thành null |
| `parentId` trỏ lại chính ID | Dữ liệu bất thường | Báo lỗi, không dựng vòng lặp |
| Hai IDs trùng trong cùng file | Dữ liệu bất thường hoặc đã ghép files sai | Không ghi đè thầm trong dictionary |

Nếu bạn lọc chỉ các steps có name bắt đầu bằng `lab.`, parent của `lab.warmup` có thể là một framework step bị **lọc khỏi phần hiển thị** nhưng vẫn nằm trong JSON; nó không phải “thiếu dữ liệu thô”. Cần phân biệt **missing from data** và **not selected**.

### 4.4. Concurrent steps

Nếu steps được tạo bởi nhiều threads, có thể có intervals chồng nhau. Một khoảng thời gian nằm trong khoảng của parent **không tự chứng minh** parentId phải trỏ vào parent. Chỉ dựa parentId do instrumentation thực ghi nhận. Trong các hệ thống có async bootstrap và context propagation, không được giả định parent context tự truyền qua mọi thread pool.

Một cây chỉ ra **quan hệ ghi theo instrumentation**, không phải tổng đồ thị CPU, locking, futures, service calls. Khi muốn xác định critical path hoặc cross-thread causality, cần bổ sung JFR, profiler, tracing hoặc logs có correlation.

## 5. Đọc tags để phân biệt các bước giống tên

Ví dụ hai events:

~~~json
{
  "id": 21,
  "name": "spring.beans.instantiate",
  "parentId": 4,
  "tags": [{"key": "beanName", "value": "orderService"}]
}
~~~

~~~json
{
  "id": 22,
  "name": "spring.beans.instantiate",
  "parentId": 4,
  "tags": [{"key": "beanName", "value": "dataSource"}]
}
~~~

Hai steps **cùng name** nhưng `beanName` khác nên phản ánh các bean khác nhau. Muốn xác định bean lâu, cần xem duration trong event bao quanh step, rồi nhìn tag `beanName`.

**Tags là array**, không phải map:

~~~json
"tags": [
  {"key": "component", "value": "catalog"},
  {"key": "stage", "value": "preload"}
]
~~~

Nên đọc từng item theo `key`, `value`. Nếu chuyển sang dictionary, có thể mất dữ liệu khi có nhiều tags trùng key; giữ list khi cần kiểm chứng nguyên bản. Không đưa mật khẩu/token/full SQL/request body/PII vào tag values vì startup endpoint có thể lộ metadata này. Dùng tên kỹ thuật và nhãn có độ biến thiên thấp.

### 5.1. Custom tag có làm startup chậm không?

Gắn tag string ngắn có overhead nhỏ, nhưng nếu tính value bằng query DB, đọc file lớn hoặc gọi remote API, chính bước lấy metadata có thể làm phép đo chậm và sai. `StartupStep.tag(String,Supplier<String>)` cho phép cung cấp lazy value phù hợp một số recorder, nhưng không nên biến supplier thành một tác vụ nặng.

Hãy đặt measurement sát vùng code bạn muốn tìm hiểu và dùng metadata rẻ tiền. Nếu không cần một tag cụ thể để phân biệt steps, đừng thêm tag chỉ để “cho đủ cột”.

## 6. Inclusive duration, exclusive duration và nút nghẽn

Một step cha bắt đầu trước các step con và end sau chúng. **Duration của cha là inclusive elapsed**, nên nó đã bao trùm các con.

~~~text
Parent: [================================]  150 ms
Child A:    [==========]                    45 ms
Child B:                  [=============]   65 ms
~~~

Với các con không overlap, phép tính ví dụ:

- Parent inclusive = 150ms.
- Child A = 45ms, child B = 65ms.
- Khoảng của parent ngoài hai con, nếu không còn span được đo khác = `150 - 45 - 65 = 40ms`.
- **Sai:** Tổng startup của đoạn là 150 + 45 + 65 = 260ms, vì thời gian của con bị cộng hai lần.

### 6.1. Khi con overlap, không thể trừ tổng durations

Ví dụ:

~~~text
P: [0ms ................................... 100ms]
A:     [10ms ................. 70ms]        60ms
B:                [40ms ................ 95ms] 55ms
~~~

A và B overlap **30ms**; union của các child intervals có độ dài `60 + 55 - 30 = 85ms`. Phần exclusive elapsed của parent `100 - 85 = 15ms`. Trừ ngây thơ `100 - 60 - 55 = -15ms` là sai.

Để tính đúng: lấy các child intervals, cắt trong khoảng parent, sort theo start, merge các intervals overlap, tính union; sau đó trừ union khỏi parent inclusive duration. Vẫn phải giải thích rằng **exclusive elapsed** không phải **CPU time**: parent có thể chờ I/O mà không tiêu tốn CPU.

### 6.2. Đừng cộng durations của mọi steps thành “thời gian khởi động”

Bảng so sánh:

| Chỉ số | Ý nghĩa | Có thể cộng đơn giản? |
|---|---|---|
| Inclusive step duration | Elapsed time từ `start` đến `end` | Không nếu nested/overlap |
| Parent exclusive elapsed | Phần interval không bị children trực tiếp bao phủ | Cần union intervals |
| CPU time | Thời gian CPU thực thi | Không suy trực tiếp từ event duration |
| Critical path | Chuỗi công việc quyết định end-to-end latency | Cần dependency/concurrency analysis |
| Startup-to-ready | Từ process/Boot start tới ready | Không mặc định bằng bất kỳ step duration nào |
| Tổng số steps | Quy mô dữ liệu recorder thu được | Không chứng minh app nhanh/chậm |

Một top duration có thể là parent wrapper. Luôn drill down vào children và tags. Một step 600ms có thể là 580ms chờ database, không phải một đoạn Java dùng CPU 600ms.

## 7. Demo runnable: Java 17, Spring Boot 3.5, Web + Actuator

### 7.1. Cấu trúc project

Tạo project Spring Initializr hoặc Maven:

- Group `com.example`, artifact `startup-steps-lab`.
- Package `com.example.startupsteps`.
- Java 17, Spring Boot 3.5.x.
- Dependencies: Spring Web, Spring Boot Actuator.
- Packaging JAR.

~~~text
startup-steps-lab/
  pom.xml
  mvnw                  (nếu dùng Maven Wrapper)
  mvnw.cmd
  src/main/java/com/example/startupsteps/
    StartupStepsLabApplication.java
    WarmupRunner.java
  src/main/resources/application.properties
~~~

`pom.xml` dưới đây dùng Spring Boot **3.5.16** làm một bản 3.5.x cụ thể. Nếu repository doanh nghiệp có version đã phê duyệt khác, chỉnh parent version tương ứng và kiểm lại API.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>startup-steps-lab</artifactId>
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

Dùng Maven để quản lý classpath Spring, không chạy `javac` một file mà thiếu thư viện. Nếu Initializr đã tạo Maven Wrapper, giữ file và dùng `./mvnw`; nếu không, dùng `mvn` cài sẵn.

### 7.3. Main: gắn recorder trước run

File `StartupStepsLabApplication.java`:

~~~java
package com.example.startupsteps;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupStepsLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupStepsLabApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(4096));

        application.run(args);
    }
}
~~~

**Không** dùng bản `SpringApplication.run(StartupStepsLabApplication.class, args)` rút gọn nếu cần set recorder bằng Java trước run. Một lần run bình thường đủ; đừng tự refresh context lần hai chỉ để phát steps.

### 7.4. Runner: một cha và hai con

File `WarmupRunner.java`:

~~~java
package com.example.startupsteps;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.stereotype.Component;

@Component
public final class WarmupRunner implements ApplicationRunner {

    private final ApplicationContext applicationContext;

    public WarmupRunner(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        ConfigurableApplicationContext context =
                (ConfigurableApplicationContext) applicationContext;
        ApplicationStartup startup = context.getApplicationStartup();

        StartupStep parent = startup.start("lab.warmup");
        parent.tag("component", "catalog");
        parent.tag("environment", "local");

        System.out.println("LAB_PARENT id=" + parent.getId()
                + " parentId=" + parent.getParentId());

        try {
            measureChild(
                    startup, "lab.warmup.load",
                    "dataSet", "sample", 40);
            measureChild(
                    startup, "lab.warmup.index",
                    "index", "prefix", 80);
        } finally {
            parent.end();
            System.out.println("LAB_PARENT_END id=" + parent.getId());
        }
    }

    private static void measureChild(
            ApplicationStartup startup, String name,
            String tagKey, String tagValue, long millis)
            throws InterruptedException {

        StartupStep child = startup.start(name);
        child.tag(tagKey, tagValue);

        System.out.println("LAB_CHILD id=" + child.getId()
                + " name=" + child.getName()
                + " parentId=" + child.getParentId());

        try {
            Thread.sleep(millis);
        } finally {
            child.end();
            System.out.println("LAB_CHILD_END id=" + child.getId());
        }
    }
}
~~~

**Đọc code theo vòng đời:**

1. `ApplicationRunner` chạy sau `ApplicationContext.refresh()` và trước `ApplicationReadyEvent` của startup thành công.
2. Inject `ApplicationContext` là việc bình thường; Spring Boot context trong demo cũng implement `ConfigurableApplicationContext` để lấy `getApplicationStartup()`.
3. Parent `lab.warmup` được tạo rồi giữ **mở** khi tạo hai children.
4. Child `lab.warmup.load` và `lab.warmup.index` cùng được tạo trong một thread khi parent chưa end; `child.getParentId()` tương ứng ID parent.
5. Parent có hai tags; mỗi child có một tag phân biệt công việc.
6. `Thread.sleep(40)`/`Thread.sleep(80)` là delay giả lập để duration dễ nhìn, **không cam kết duration chính xác**; JVM scheduling/logging/GC có thể tăng thời gian.
7. `end()` trong `finally` để đảm bảo step kết thúc ngay cả khi bị `InterruptedException`.
8. `parent.getParentId()` có thể trỏ đến bước framework đang mở hoặc null tùy recorder. Không hardcode giá trị.
9. Console marker giúp đối chiếu JSON `id/parentId` mà không cần đoán từ tên hoặc mảng.
10. Demo không gọi DB/network thật, nên không quy kết kết quả delay cho bottleneck external.

### 7.5. Cấu hình Actuator

File `application.properties`:

~~~properties
spring.application.name=startup-steps-lab
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,startup
management.endpoint.startup.access=unrestricted
~~~

`management.endpoints.web.exposure.include` đưa endpoint `startup` ra HTTP. `management.endpoint.startup.access=unrestricted` cho phép cả GET snapshot và POST drain trong lab Spring Boot 3.5, trừ khi policy chung hoặc Spring Security/CSRF thu hẹp quyền. Mặc định không expose mọi Actuator endpoints trên web; **không** đặt `include=*` chỉ để xem startup.

`server.address=127.0.0.1` giới hạn lab local, tránh phơi metadata bean ra mạng. Khi chạy Kubernetes/container, phải điều chỉnh bind/interface và security theo thực tế; không copy localhost config nếu kubelet/ingress cần kết nối từ network khác.

## 8. Chạy lab và lấy dữ liệu thực tế

### 8.1. Linux/macOS

~~~bash
java -version
./mvnw -version
./mvnw clean package
java -jar target/startup-steps-lab-0.0.1-SNAPSHOT.jar
~~~

### 8.2. Windows PowerShell

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
java -jar target/startup-steps-lab-0.0.1-SNAPSHOT.jar
~~~

Nếu không có Maven Wrapper, dùng `mvn clean package`. Đảm bảo JDK 17+ trong `JAVA_HOME`/PATH. Dừng app khác trên port 8080 hoặc đổi port. Không chạy hai tiến trình trên cùng port rồi thu JSON nhầm process.

### 8.3. Marker trên console

Kỳ vọng tương tự:

~~~text
LAB_PARENT id=<parent-id> parentId=<framework-id-or-null>
LAB_CHILD id=<child1-id> name=lab.warmup.load parentId=<parent-id>
LAB_CHILD_END id=<child1-id>
LAB_CHILD id=<child2-id> name=lab.warmup.index parentId=<parent-id>
LAB_CHILD_END id=<child2-id>
LAB_PARENT_END id=<parent-id>
~~~

Các giá trị trong dấu góc chỉ là **ký hiệu biến số khi mô tả**, không phải stdout literal. Khi đọc log thật:

- Parent ID là một số nguyên được sinh tự động.
- Hai child `parentId` phải bằng **ID của LAB_PARENT** trong một recorder đáp ứng nested steps.
- `LAB_PARENT_END` đến sau cả hai `LAB_CHILD_END`.
- Không đòi mọi Java/system log phải liền nhau hoặc IDs liên tục.

### 8.4. GET snapshot

Trong terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/actuator/startup
curl -s http://127.0.0.1:8080/actuator/startup -o startup.json
~~~

Trên Windows:

~~~powershell
curl.exe -i http://127.0.0.1:8080/actuator/startup
curl.exe -s http://127.0.0.1:8080/actuator/startup -o startup.json
~~~

Khi chạy lab đúng, GET thường trả HTTP 200 với JSON có `springBootVersion`, `timeline.startTime`, `timeline.events`. Gọi GET nhiều lần trả **snapshot** và **không xóa** steps đang có. Vì recorder có thể ghi thêm steps trong quá trình ứng dụng hoạt động nếu code instrument, snapshot sau có thể khác snapshot trước.

**Không dùng POST trước GET lần đầu** nếu muốn lưu toàn bộ startup steps hiện tại.

### 8.5. Trích custom steps bằng jq

Nếu có công cụ `jq`:

~~~bash
jq '.timeline.events | length' startup.json

jq -r '
  .timeline.events[]
  | select(.startupStep.name | startswith("lab."))
  | [
      .startupStep.id,
      (.startupStep.parentId // "none"),
      .startupStep.name,
      .duration
    ]
  | @tsv
' startup.json
~~~

Với buffer còn đủ chỗ, ba tên custom là `lab.warmup`, `lab.warmup.load` và `lab.warmup.index`. `jq` chỉ trích record; phép nối cha/con phải dựa vào hai cột id/parentId, không chỉ vị trí dòng.

Đọc tags:

~~~bash
jq -r '
  .timeline.events[]
  | select(.startupStep.name == "lab.warmup")
  | .startupStep.tags[]
  | "\(.key)=\(.value)"
' startup.json
~~~

Kỳ vọng:

~~~text
component=catalog
environment=local
~~~

Nếu tag array rỗng, dùng `.tags[]?` cho query tổng quát. Với framework steps, key phổ biến như `beanName` giúp phân biệt các instances có cùng `name`.

### 8.6. GET khác POST drain

~~~bash
curl -s -X POST http://127.0.0.1:8080/actuator/startup -o drained.json
curl -s http://127.0.0.1:8080/actuator/startup -o after-drain.json
~~~

Theo REST API của Spring Boot 3.5:

- `GET` lấy **snapshot**, không xóa buffer.
- `POST` **drain** steps đã ghi và trả chúng về response; các steps đó được rút khỏi buffer.
- GET tiếp theo thường không còn các steps cũ; có thể còn steps mới nếu được ghi sau lúc drain.
- `POST` **không** restart JVM, không clear bean definitions và không tắt ứng dụng.
- Vì POST thay đổi dữ liệu quan sát, phải phối hợp với những người dùng cùng endpoint; một người drain có thể khiến người khác bỏ lỡ dữ liệu.

Nếu POST trả 403/405, kiểm quyền Actuator, access level và CSRF/security; không quy kết ngay lỗi `BufferingApplicationStartup`.

## 9. Dựng cây cha–con: không dựa thứ tự mảng

Quy trình xử lý chuẩn:

1. Đọc tất cả `timeline.events`.
2. Với mỗi event, lấy `startupStep.id` và thêm vào dictionary/index.
3. Kiểm IDs trùng; nếu trùng trong cùng file, dữ liệu/ghép records không đúng.
4. Với mỗi step có `parentId`, tìm parent bằng index.
5. Nếu parent tồn tại, gắn child vào parent.
6. Nếu parentId null, đánh dấu root.
7. Nếu parentId có nhưng parent không tồn tại, đánh dấu **missing parent**; không đổi sang 0.
8. Sort siblings theo `startTime` rồi `id` để dễ đọc.
9. In `name` và tags, kèm duration chuyển sang milliseconds.
10. Guard cycles/độ sâu khi xử lý JSON có lỗi, không đệ quy vô hạn.

Dạng kết quả:

~~~text
id=100 lab.warmup duration=140ms tags=[component=catalog]
  id=101 lab.warmup.load duration=45ms tags=[dataSet=sample]
  id=102 lab.warmup.index duration=65ms tags=[index=prefix]
~~~

**Đặc biệt:** Bước cha có thể nằm sau con trong mảng vì cha kết thúc sau; ví dụ tài liệu REST chính thức thể hiện rõ. Không duyệt tuần tự rồi gán phần tử trước làm cha của phần tử sau.

## 10. Script Python 3 đọc JSON và xếp hạng theo duration

Script `analyze_startup.py` dưới đây dùng **standard library**. Nó lập ID index, xây cây các bước tên bắt đầu bằng prefix (mặc định `lab.`), in tags và duration bằng milliseconds, đồng thời cảnh báo reference đến parent không có trong JSON. Nó không thay đổi file.

~~~python
#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

def iso_seconds(value):
    """Parse PT...H...M...S, the common Boot duration form."""
    m = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        value,
    )
    if not m:
        raise ValueError(f"Unsupported duration: {value!r}")
    h = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = float(m.group(3) or 0)
    return h * 3600 + minutes * 60 + seconds

def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python3 analyze_startup.py startup.json [prefix]")
        return 2

    document = json.loads(
        Path(sys.argv[1]).read_text(encoding="utf-8")
    )
    events = document.get("timeline", {}).get("events", [])
    prefix = sys.argv[2] if len(sys.argv) == 3 else "lab."

    by_id = {}
    for event in events:
        key = event["startupStep"]["id"]
        if key in by_id:
            raise ValueError(f"Duplicate startup step id: {key}")
        by_id[key] = event

    selected = {
        key: event for key, event in by_id.items()
        if event["startupStep"]["name"].startswith(prefix)
    }
    children = {key: [] for key in selected}
    roots = []
    missing = []

    for key, event in selected.items():
        parent = event["startupStep"].get("parentId")
        if parent in selected:
            children[parent].append(key)
        else:
            roots.append(key)
            if parent is not None and parent not in by_id:
                missing.append((key, parent))

    def order(key):
        event = selected[key]
        return event.get("startTime", ""), key

    roots.sort(key=order)
    for siblings in children.values():
        siblings.sort(key=order)

    def visit(key, level, path):
        if key in path:
            print("  " * level + f"[CYCLE at id={key}]")
            return
        event = selected[key]
        step = event["startupStep"]
        tags = ", ".join(
            f"{tag.get('key')}={tag.get('value')}"
            for tag in step.get("tags", [])
        )
        ms = iso_seconds(event["duration"]) * 1000
        print(
            "  " * level
            + f"id={key} parent={step.get('parentId')} "
            + f"{step['name']} {ms:.2f}ms"
            + (f" tags=[{tags}]" if tags else "")
        )
        for child in children[key]:
            visit(child, level + 1, path | {key})

    print("Spring Boot version:", document.get("springBootVersion"))
    print("All events:", len(events))
    print("Selected:", len(selected), "prefix:", repr(prefix))
    for root in roots:
        visit(root, 0, set())

    for child, parent in missing:
        print(f"WARNING missing parent: child={child}, parent={parent}")

    ranked = sorted(
        selected.values(),
        key=lambda e: iso_seconds(e["duration"]),
        reverse=True,
    )
    print("Top selected durations:")
    for e in ranked[:10]:
        step = e["startupStep"]
        ms = iso_seconds(e["duration"]) * 1000
        print(f"  {ms:9.2f}ms  id={step['id']} {step['name']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
~~~

Chạy trên Linux/macOS:

~~~bash
python3 analyze_startup.py startup.json
python3 analyze_startup.py startup.json spring.beans.instantiate
~~~

Windows:

~~~powershell
py -3 analyze_startup.py startup.json
py -3 analyze_startup.py startup.json spring.beans.instantiate
~~~

**Lưu ý về parser:**

- Mặc định chỉ in bước `lab.`. Nếu parent là step framework trong JSON nhưng bị filter khỏi prefix, nó được in như một **root của chế độ hiển thị đã lọc**, không phải root tuyệt đối của timeline.
- Chỉ in `WARNING missing parent` nếu ID parent thực sự **không có trong JSON gốc**; filter prefix không tự được xem là thiếu dữ liệu.
- Script sort children bằng `startTime`, không sửa `parentId`.
- Duration parser xử lý dạng `PT...H...M...S` thường gặp trong Startup REST API, không phải parser tổng quát mọi dạng ISO-8601 với ngày/tháng/âm; Java `Duration.parse` có thể dùng khi cần chuẩn JDK.
- Để in nhiều bước hơn, truyền prefix phù hợp; prefix rỗng sẽ in toàn bộ tree và có thể rất dài.
- Với dữ liệu sai có vòng parentId hoàn toàn kín không có root, script không in nhánh kín đó; một analyzer production nên kiểm tra toàn bộ nodes và cycles.
- Chỉ số top là **inclusive elapsed**; hãy xem hierarchy trước khi kết luận bottleneck.
- File JSON từ nhiều replicas/lần JVM restart **không được** ghép thành một map `id` duy nhất vì IDs chỉ độc nhất trong một recording.

### 10.1. Đối chiếu lab

Khi chạy script trên `startup.json` được lấy bằng GET **trước POST**, bạn thường thấy:

~~~text
id=<P> parent=<framework-id-or-None> lab.warmup ...ms tags=[component=catalog, environment=local]
  id=<C1> parent=<P> lab.warmup.load ...ms tags=[dataSet=sample]
  id=<C2> parent=<P> lab.warmup.index ...ms tags=[index=prefix]
~~~

Dấu `<P>`/`<C1>`/`<C2>` ở đây là ký hiệu giá trị thay đổi trong phần mô tả, không phải output byte-for-byte. Các bước con được lồng đúng nếu parent ID khớp và durations nằm trong khoảng outer. Đừng hardcode con số ID từ tài liệu.

## 11. Phân tích một bean chậm từ name và tags

Ví dụ giả định:

| name | tags | inclusive duration |
|---|---|---:|
| `spring.beans.instantiate` | `beanName=reportService` | 650ms |
| `spring.beans.instantiate` | `beanName=dataSource` | 580ms |
| `spring.beans.instantiate` | `beanName=cacheService` | 400ms |

Nếu record `dataSource` là child của `reportService` và intervals được bao hàm, 580ms **đã nằm trong** 650ms parent; không cộng chúng để ra 1230ms. Việc phải làm:

1. Kiểm IDs và `parentId` để chắc hai steps có quan hệ thực.
2. Kiểm `startTime`/`endTime` xác nhận khoảng con nằm trong cha.
3. Xem việc khởi tạo dataSource có chờ DNS/DB connection/driver init hay không.
4. Chạy nhiều lần trong cùng profile/environment và đo p50/p95 để tránh kết luận từ một spike.
5. Với bước chậm không có children, thử bổ sung custom `ApplicationStartup.start(...)` ở code bên trong hoặc dùng JFR/tracing.
6. Tối ưu root cause rồi đo **end-to-end time-to-ready**, không chỉ giảm vài steps.

### 11.1. Lazy initialization không luôn làm app “nhanh hơn” thực sự

`spring.main.lazy-initialization=true` có thể làm nhiều bean không được khởi tạo tại startup, giảm recorded steps và rút ngắn thời gian khởi động. Nhưng công việc chỉ **dời** sang request hoặc operation đầu tiên, có thể làm tăng latency và trì hoãn phát hiện lỗi cấu hình.

Đo startup và first-request latency, readiness thực tế, JDBC warmup, external dependency và error behavior trước/sau khi tối ưu. Số steps giảm chỉ có thể do filter, capacity, lazy init hoặc recorder khác, chưa phải bằng chứng performance cải thiện.

## 12. Buffer capacity và điều kiện thiếu steps

`BufferingApplicationStartup(4096)` ghi tối đa 4096 events theo capacity; theo Javadoc, khi buffer đạt capacity, **những step mới không được ghi tiếp**. Đây không phải ring buffer tự loại bước đầu để giữ bước cuối. Cần cân nhắc:

- App có nhiều beans/auto-configurations có thể vượt capacity.
- Custom `ApplicationRunner` chạy muộn nên step của runner có thể không được ghi dù log console vẫn có.
- Filters có thể cố ý loại một số tên steps.
- Một lệnh POST drain đã lấy dữ liệu và khiến GET sau đó không còn records cũ.
- Một file JSON trích một phần có thể thiếu parent được tham chiếu.
- Application có nhiều contexts/replicas có thể bị curl nhầm instance.

Đừng kết luận `lab.warmup.index` không được thực thi chỉ vì không thấy trong timeline; kiểm logs, recorder configuration, capacity, filter và việc POST đã được gọi chưa.

### 12.1. Filter có tác động tới cây

Ví dụ thay `main` bằng đoạn (snippet, không chạy hai lần):

~~~java
BufferingApplicationStartup startup =
        new BufferingApplicationStartup(4096);
startup.addFilter(step ->
        step.getName().startsWith("lab.")
        || step.getName().startsWith("spring.beans."));

SpringApplication app =
        new SpringApplication(StartupStepsLabApplication.class);
app.setApplicationStartup(startup);
app.run(args);
~~~

Có thể giảm lượng events cần phân tích, nhưng những bước cha `spring.boot.*` hoặc `spring.context.*` bị loại sẽ khiến tree thiếu một số ancestors. Vì vậy filter chỉ phù hợp khi bạn hiểu mình đã mất bối cảnh nào.

Nếu thêm **nhiều** predicates qua `addFilter`, Javadoc mô tả step phải thỏa những filters để được ghi; không nghĩ chúng tự OR với nhau. Đoạn trên chủ động dùng `||` **trong một predicate**.

### 12.2. GET snapshot và POST drain khác buffer overflow

- **Buffer overflow:** bước chưa từng được ghi vào buffer sau khi hết capacity.
- **Filter:** bước bị loại do predicate trước khi được ghi.
- **POST drain:** bước đã ghi nhưng bị rút khỏi buffer khi được trả về.
- **Chưa end step:** bước vẫn đang mở, có thể chưa có completed timeline event.
- **Nhầm process:** lấy đúng endpoint nhưng từ một JVM khác.

Các nguyên nhân này đều làm “thiếu step” nhưng cách xử lý rất khác. Cần ghi nhận cơ chế và thời điểm thu dữ liệu.

## 13. FlightRecorderApplicationStartup và JFR

Khi cần biết bước chậm do classloading/GC/CPU/locks hay I/O, có thể chuyển sang `FlightRecorderApplicationStartup` của Spring Framework và ghi JFR. Ví dụ **thay thế main setup**:

~~~java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

SpringApplication app =
        new SpringApplication(StartupStepsLabApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

Đây là snippet, không đặt dòng `import` giữa method Java khi copy vào file thật. Dùng recorder này thay cho Buffering trong **một lượt chạy khác**; nó **không** tạo JSON buffer `/actuator/startup` tương tự.

Chạy từ JDK có hỗ trợ JFR:

~~~bash
java -XX:StartFlightRecording:filename=startup.jfr,duration=30s \
     -jar target/startup-steps-lab-0.0.1-SNAPSHOT.jar
~~~

Trên Windows PowerShell đặt toàn lệnh một dòng hoặc dùng continuation hợp lệ của PowerShell. Phân tích bằng `jfr print` hoặc JDK Mission Control. Timeline JSON giúp xác định step/tags/parent; JFR cung cấp góc nhìn JVM về allocations, thread scheduling, GC, classloading và CPU samples. Dùng chúng bổ sung nhau chứ không coi duration bằng CPU time.

## 14. Nhiều contexts, threads và replicas

Trong một app có nhiều ApplicationContext hoặc worker threads, không thể mặc định một cây duy nhất miêu tả mọi hoạt động. `parentId` theo semantics recorder, không tự là distributed trace across services hoặc context propagation giữa threads. Hai steps có intervals overlap không tự là cha/con.

Trong Kubernetes nhiều Pods, mỗi JVM có các step IDs của **riêng recording đó**. `id=50` ở Pod A không phải `id=50` ở Pod B. Khi so sánh startup runs, ghi thông tin process/pod ID, version, profile, Java version, cold/warm cache và tải máy; match theo `name + tags` và bối cảnh, không dùng `id` làm khóa toàn cụm.

Với framework instrumentation, các steps có thể được ghi ở nhiều phase như bean creation, context refresh, runners, nhưng không phải mọi phần của JVM launch/OS/container pull image đều được ghi trong `ApplicationStartup`. Muốn đo end-to-end từ platform, kết hợp timestamps từ process supervisor/container, Spring Boot startup logs và ứng dụng ready state.

## 15. Bảo mật, hiệu năng và quy trình điều tra

### 15.1. Bảo mật startup endpoint

`/actuator/startup` có thể lộ bean/package names và tags. Trong production:

- Chỉ expose trên management interface được bảo vệ; không cho public internet.
- Có authentication/authorization, mạng hạn chế và access/audit nếu cần.
- Không gắn token, credentials, request body hoặc PII vào tags.
- Xác định ai có quyền POST drain vì nó làm mất các records đang được giữ.
- Chọn capacity phù hợp với heap và retention.
- Không liên tục GET payload lớn nếu chưa đánh giá serialization/network overhead.
- Nếu bật Spring Security, kiểm CSRF với POST, đừng tự tắt toàn bộ security chỉ để lấy endpoint.

### 15.2. Quy trình tìm bottleneck

1. Ghi đúng JDK, Spring Boot version, profile, classpath, container image và môi trường test.
2. Bật `BufferingApplicationStartup` trước run; capacity đủ để giữ những steps muốn quan sát.
3. Khởi động mới, không dùng file đã drain hoặc dữ liệu từ JVM khác.
4. GET snapshot và lưu JSON với timestamp/run identifier.
5. Kiểm `timeline.events` có đủ các groups quan trọng; đánh dấu missing parents.
6. Dựng cây `id → parentId`, xem `name + tags`.
7. Xếp hạng durations bằng **số milliseconds**, không sort text ISO duration bằng từ điển.
8. Drill down các step cha lớn để tránh double-count.
9. Xem những steps không đo được, I/O/GC/JIT và dependency waits bằng JFR/log/metrics.
10. Thử tối ưu một biến có kiểm soát; đo lại nhiều runs và time-to-ready/first-request.
11. Ghi kết luận theo evidence, không coi một duration đơn lẻ là proof CPU bottleneck.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xét | Cách xác minh |
|---|---|---|
| GET startup 404 | Chưa Actuator, chưa exposure/access hoặc recorder không phù hợp | Kiểm Maven dependencies, properties, `setApplicationStartup` |
| GET 401/403 | Authentication/authorization | Kiểm Spring Security và access policy |
| POST 403/405 | Read-only access hoặc CSRF/security | Kiểm endpoint access, chain và request method |
| Không có steps `lab.warmup.*` | Buffer đầy, filter, đã drain hoặc runner chưa chạy | So LAB markers, capacity, request timeline |
| ParentId trống | Top-level/no parent reported | Giữ null, không ép thành 0 |
| ParentId tham chiếu ID không thấy | Parent filtered, buffer/partial snapshot | Đánh dấu missing parent, không bịa |
| Mảng events có child trước parent | Steps được lưu theo timing/completion | Index theo ID, không dựa vị trí |
| Duration `PT0.3S` bị đọc 0,3ms | Sai đơn vị | Đổi ra 300ms |
| Sort duration bằng `sort_by(.duration)` sai | ISO duration là chuỗi, không phải số | Parse ISO duration trước khi sort |
| Nhiều `spring.beans.instantiate` | Mỗi bean là một step có cùng type/name | Dùng tag beanName và ID |
| Cộng duration được lớn hơn tổng startup | Nested/overlapping spans | Không cộng inclusive durations |
| Exclusive parent bị âm | Trừ tổng child có overlap | Merge union intervals |
| Step lớn nhưng CPU thấp | Chờ I/O, GC, lock hoặc child | JFR/metrics và cây steps |
| Số step giảm sau bật lazy | Dời bean creation sang request đầu | Đo time-to-ready và first-request latency |
| Different runs IDs không khớp | IDs không ổn định qua runs | Match name + tags + environment |
| JSON từ nhầm Pod | Route qua load balancer/management | Chọn instance cụ thể khi lấy snapshot |
| Tags làm lộ dữ liệu | Gắn secrets/PII | Sửa tagging, bảo vệ endpoint |
| Filter làm mất ancestors | Predicate chỉ giữ một số steps | Ghi rõ filter, thử full buffer |
| JFR dùng rồi startup JSON trống | Flight Recorder khác buffering recorder | Dùng JFR tooling hoặc Buffering để lấy JSON |

## 17. Bài tập có thể tự kiểm chứng

**Bài tập A — Tìm ba steps.** Chạy lab, GET snapshot trước khi drain, tìm `lab.warmup`, `lab.warmup.load` và `lab.warmup.index`. Ghi từng `id`, `parentId`, `duration`, `tags`. Xác nhận hai child trỏ tới ID parent thực tế.

**Bài tập B — Đọc tags.** Với `lab.warmup`, liệt kê `component=catalog` và `environment=local`. Với hai children, đọc `dataSet=sample` và `index=prefix`. Giải thích tại sao tên step một mình chưa nói hết thông tin.

**Bài tập C — Thứ tự mảng.** So thứ tự `LAB_PARENT`/`LAB_CHILD` trong console với thứ tự records JSON; giải thích vì sao parent có thể nằm sau child trong danh sách events.

**Bài tập D — Parent bị thiếu.** Copy file JSON, bỏ record parent nhưng giữ child.parentId, chạy script. Kiểm script cảnh báo missing parent và không tự đổi nó thành 0.

**Bài tập E — Duration.** Đổi `PT0.040S`, `PT0.080S` và `PT0.125S` thành ms. Dùng `Duration.parse` hoặc parser Python để kiểm và nêu vì sao `Thread.sleep` không tạo duration tuyệt đối.

**Bài tập F — Inclusive/exclusive.** Parent 100ms, child A từ 10–70ms và B 40–95ms. Tính union 85ms, exclusive 15ms, và giải thích vì sao phép trừ tổng durations có thể âm.

**Bài tập G — GET/POST.** Trong một process mới, lần lượt GET → GET → POST → GET; so số events và mô tả tác động drain.

**Bài tập H — Buffer/filter.** Trong bản copy lab, đặt capacity nhỏ hoặc filter chỉ `lab.`, so dữ liệu với cấu hình 4096 không filter. Quan sát vì sao bước cha framework mất nhưng parentId child vẫn có thể trỏ ID cũ.

**Bài tập I — Tối ưu thật.** Tìm một `spring.beans.instantiate` có duration lớn trong app thử nghiệm, đọc `beanName`, parent/children, kiểm root cause bằng JFR hoặc dependency timing; sau tối ưu đo nhiều lần startup-to-ready và first request thay vì chỉ một giá trị duration.

### Checklist nghiệm thu

- [ ] Cấu hình `BufferingApplicationStartup` trước `SpringApplication.run`.
- [ ] Chạy được Maven project Java 17+ Spring Boot 3.5 Web + Actuator.
- [ ] GET `/actuator/startup` trả JSON có `timeline.events`.
- [ ] Đọc được `name/id/parentId/tags/startTime/endTime/duration`.
- [ ] Biết `parentId` optional; không mặc định 0.
- [ ] Dựng cây theo ID, không dựa vào thứ tự mảng events.
- [ ] Phân biệt nhiều steps trùng name nhờ tags.
- [ ] Đổi `PT0.012S` thành 12ms.
- [ ] Nhìn thấy hai child có parentId bằng ID parent trong lab.
- [ ] Biết duration cha inclusive và không cộng chồng children.
- [ ] Biết merge union intervals khi steps overlap.
- [ ] GET snapshot không xóa, POST drain có xóa buffer.
- [ ] Hiểu capacity/filter có thể khiến steps bị thiếu.
- [ ] Không đồng nhất `parentId` với bean dependency graph.
- [ ] Không đồng nhất elapsed duration với CPU time.
- [ ] Biết bảo vệ Actuator endpoint và tránh secrets trong tags.
- [ ] Có quy trình đối chiếu nhiều runs và JFR khi điều tra bottleneck.

## 18. Tài liệu chính thức

1. **Spring Boot 3.5 — Application Startup tracking**, Buffering và Flight Recorder: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. **Spring Boot 3.5 — Actuator Startup REST API**, GET snapshot, POST drain và JSON schema: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html
3. **Spring Boot 3.5 — Actuator Endpoints**, HTTP exposure/access/security: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
4. **Spring Framework 6.2 — ApplicationStartup API**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
5. **Spring Framework 6.2 — StartupStep API** (ID, parentId, tags, end): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/metrics/StartupStep.html
6. **Spring Boot 3.5 — BufferingApplicationStartup API** (capacity/filters/timeline): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html
7. **Spring Framework 6.2 — FlightRecorderApplicationStartup API**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
8. **Java SE 17 — Duration.parse / toMillis**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html

**Kết luận:** Muốn đọc startup timeline chính xác, hãy nối **`id → parentId`** để có hierarchy, dùng **`name + tags`** để biết mỗi bước đang làm gì, sau đó xem **`startTime/endTime/duration`** để phân tích thời gian. Không coi thứ tự mảng là cây, không gộp IDs giữa các lần chạy, không cộng mọi inclusive durations để ra startup total. Khi có missing parent hoặc buffers bị drain/filter, phải ghi nhận giới hạn quan sát. Muốn tìm bottleneck thực sự, kết hợp timeline với JFR/metrics và xác minh trên nhiều lần khởi động.