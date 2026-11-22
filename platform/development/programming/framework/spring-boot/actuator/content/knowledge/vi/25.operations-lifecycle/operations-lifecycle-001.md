# Quan sát thời gian khởi động qua endpoint startup

Ứng dụng mất vài giây để khởi động, nhưng một dòng nhật ký “Started ... in ... seconds” không chỉ ra thời gian đã nằm ở đâu. Có thể Spring đang tạo bean, xử lý cấu hình, chờ một bước khởi tạo của ứng dụng hoặc làm nhiều công việc lồng nhau. Endpoint `startup` của Spring Boot Actuator giúp xem các bước khởi động đã được ghi lại, cùng thời điểm, thời lượng và quan hệ cha–con của chúng.

Mục tiêu của bài là biết cách thu thập dữ liệu đúng từ đầu, lấy bản chụp an toàn, đọc thời lượng đúng đơn vị và tìm đầu mối điều tra việc khởi động chậm. Bài dùng Spring Boot 3.3.x; ví dụ cố định Boot 3.3.13 và JDK 21 để tái lập, không hàm ý đây là phiên bản mới nhất.

## 1. Hiểu đúng vai trò của startup

Trong quá trình khởi động, `SpringApplication` và `ApplicationContext` thực hiện nhiều công việc. Những phần có hỗ trợ đo đạc tạo ra các `StartupStep`: mỗi bước có tên, định danh, thời gian thực hiện và có thể có các thông tin gắn kèm gọi là tag.

Hãy tách ba trách nhiệm:

```text
ApplicationStartup
    -> nhận các mốc bắt đầu/kết thúc StartupStep

BufferingApplicationStartup
    -> lưu các bước đã ghi vào bộ đệm hữu hạn

Actuator startup endpoint
    -> cung cấp dữ liệu trong bộ đệm qua HTTP
```

Endpoint là nơi đọc dữ liệu, không phải công tắc tự động bổ sung dữ liệu cho mọi lần khởi động trước đó. Nếu không bật cách ghi phù hợp trước lúc chạy ứng dụng, thêm `startup` vào danh sách exposure về sau không khôi phục được các bước đã bỏ qua.

Một số bước thường gặp liên quan tới việc tạo bean hoặc khởi tạo ngữ cảnh. Không phải mọi lệnh Java, mọi truy vấn cơ sở dữ liệu hay mọi đoạn mã trong JVM đều tự trở thành một bước riêng. Khi một bước dài, dữ liệu cho biết khoảng đo đó tốn thời gian; để biết chính xác CPU, I/O, tải lớp hay GC đóng góp thế nào, có thể cần thêm công cụ phân tích.

Spring Boot hỗ trợ chọn `ApplicationStartup` khi cấu hình đối tượng `SpringApplication`; `BufferingApplicationStartup` là lựa chọn phục vụ bộ đệm và endpoint JSON. [Theo dõi quá trình khởi động trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.startup-tracking).

### 1.1. Những số đo dễ bị nhầm

| Thông tin | Trả lời câu hỏi gì? |
| --- | --- |
| Dòng nhật ký tổng thời gian khởi động | Lần chạy này đã mất khoảng bao lâu tới mốc nhật ký đó? |
| `startup` timeline | Những bước được ghi nhận đã diễn ra trong các khoảng thời gian nào? |
| `application.started.time` | Số đo thời gian tới mốc ứng dụng đã khởi động |
| `application.ready.time` | Số đo thời gian tới mốc ứng dụng sẵn sàng phục vụ |
| Readiness hoặc startup probe của nền tảng triển khai | Hệ thống có nên đưa lưu lượng tới ứng dụng hoặc tiếp tục chờ nó không? |

Endpoint `startup` không phải `startupProbe` và không thay thế readiness. Hai số đo `application.started.time` và `application.ready.time` cũng không phải danh sách chi tiết các bước. Công việc trong runner hoặc giai đoạn chuẩn bị phục vụ có thể làm các mốc tổng hợp khác nhau. [Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.application-startup).

## 2. Cấu hình ghi dữ liệu trước khi chạy

Điểm quan trọng nằm trong `main`, trước lời gọi `run`:

```java
SpringApplication application = new SpringApplication(StartupDemoApplication.class);
application.setApplicationStartup(new BufferingApplicationStartup(2048));
application.run(args);
```

Đây là đoạn trích cấu hình, chưa phải một tệp Java độc lập. Ví dụ đầy đủ ở phần sau có các import và lớp tương ứng.

`2048` là sức chứa bộ đệm theo số bước, không phải số mili giây và không phải số byte. Sức chứa hữu hạn giúp giới hạn lượng thông tin giữ trong bộ nhớ. Khi đạt giới hạn, các bước mới có thể không được ghi thêm; không được xem đây là bộ đệm vòng tự động giữ 2048 bước mới nhất.

Không đặt `BufferingApplicationStartup` vào một `@Bean` tạo muộn rồi mong nó ghi lại toàn bộ các công việc Spring đã thực hiện trước đó. Cũng không tự gọi `startRecording()` mỗi lần đọc HTTP: constructor đã bắt đầu ghi, còn API đặt lại mốc ghi có điều kiện sử dụng riêng.

Nếu cần lọc bớt dữ liệu, có thể dùng `addFilter` trước `run`. Ví dụ thay thế phần cấu hình trong `main`:

```java
BufferingApplicationStartup startup = new BufferingApplicationStartup(4096);
startup.addFilter(step ->
        step.getName().startsWith("spring.beans.")
                || step.getName().startsWith("demo."));
application.setApplicationStartup(startup);
```

Đoạn trên giả định biến `application` đã tồn tại và chưa gọi `run`; nó không phải chương trình thứ hai. Bộ lọc quyết định bước nào được lưu, không quyết định công việc nào được thực thi. Khi lọc bỏ bước cha, bước con còn lại có thể tham chiếu tới một `parentId` không có trong bản chụp. Điều đó cần được tính tới khi dựng cây.

API phân biệt rõ giới hạn sức chứa, bộ lọc, lấy bản chụp và lấy dữ liệu ra khỏi bộ đệm. [BufferingApplicationStartup của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html).

## 3. Bật endpoint và lựa chọn cách đọc

Ứng dụng cần Actuator, cách ghi `BufferingApplicationStartup` phù hợp và endpoint được cung cấp trên kênh web. Với đường dẫn mặc định, cấu hình liên quan là:

```yaml
management:
  endpoint:
    startup:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,startup
```

Bật endpoint và expose qua HTTP là hai điều kiện khác nhau. Chỉ thêm `enabled: true` không tự đưa nó ra mạng; chỉ thêm vào `include` cũng không thay thế điều kiện có bộ ghi dữ liệu. Cấu hình hiệu lực còn chịu tác động của profile và các nguồn ghi đè. [Điều kiện của endpoint startup và quy tắc exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 3.1. GET giữ nguyên dữ liệu; POST lấy dữ liệu ra

| Yêu cầu | Kết quả thành công | Tác động lên bộ đệm |
| --- | --- | --- |
| `GET /actuator/startup` | `200 OK` và JSON bản chụp | Không loại bỏ các bước đang được trả về |
| `POST /actuator/startup` | `200 OK` và JSON các bước được lấy ra | Loại bỏ các bước đã lấy khỏi bộ đệm |

**POST ở đây không có nghĩa “đo lại từ đầu”.** Nó thực hiện thao tác lấy dữ liệu ra, thường gọi là drain. Nó không khởi động lại ứng dụng, không chạy lại việc tạo bean và không trả về 204 rỗng. Nếu cần so sánh với một lần khởi động mới, phải thu thập dữ liệu của lần chạy mới đó.

Với công cụ quan sát cần giữ dữ liệu cho người khác, ưu tiên `GET`. Nếu dùng `POST` để xuất dữ liệu sang nơi lưu trữ khác, phải quản lý ai là bên lấy dữ liệu và xử lý thất bại khi lưu. Một công cụ đã drain có thể khiến người đọc sau không còn thấy các bước cũ.

Sau drain, một lần `GET` tiếp theo không nhất thiết luôn có mảng rỗng: hệ thống có thể vừa phát sinh thêm bước, chẳng hạn do tạo bean muộn. Điều cần hiểu là những bước đã được drain không còn nằm trong bộ đệm chỉ vì người dùng muốn xem lại. [Hợp đồng GET và POST của startup](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html).

## 4. Ví dụ chạy được: ghi một bước khởi tạo có chủ đích

Ví dụ tạo một bean `warmupData`, bên trong có bước `demo.warmup`. Bước này cố ý chờ khoảng 120 ms để tạo ra một khoảng đo dễ nhận biết. Đây là độ trễ mô phỏng cho bài học, không phải cách tối ưu hoặc yêu cầu thêm thời gian chờ vào ứng dụng thật.

### 4.1. Cấu trúc và phụ thuộc

Tạo dự án Maven mới:

```text
startup-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/StartupDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/StartupEndpointTest.java
```

Dùng JDK 21 và Maven. Tệp kiểm chứng ở phần 8 có thể được thêm sau khi đã xem mã ứng dụng.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>startup-demo</artifactId>
    <version>1.0.0</version>
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

Starter web cung cấp HTTP, Actuator cung cấp endpoint quản trị và starter test chỉ dùng khi kiểm chứng. Với dự án đang tồn tại, giữ cơ chế quản lý phiên bản của chính dự án; không cần sửa cấu trúc toàn bộ dự án để áp dụng ba dòng cấu hình `ApplicationStartup`.

### 4.2. application.yml

```yaml
spring:
  application:
    name: startup-demo

server:
  address: 127.0.0.1
  port: 8099

management:
  endpoint:
    startup:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,startup
```

Ví dụ chỉ lắng nghe trên loopback `127.0.0.1:8099` và không thêm Spring Security để tập trung vào cơ chế thu thập. Đây là cấu hình thực hành cục bộ. Trong ứng dụng có bảo mật, người gọi phải thỏa mãn chính sách hiện có; exposure không tự cấp quyền truy cập.

Nếu dùng management port hoặc đường dẫn cơ sở Actuator khác, thay URL của các lệnh tương ứng. Nếu cổng 8099 đang được dùng, chọn một cổng trống.

### 4.3. StartupDemoApplication.java

```java
package example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;

@SpringBootApplication
public class StartupDemoApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StartupDemoApplication.class);
        application.setApplicationStartup(new BufferingApplicationStartup(2048));
        application.run(args);
    }

    @Bean
    WarmupData warmupData(ApplicationStartup startup) throws InterruptedException {
        StartupStep step = startup.start("demo.warmup");
        step.tag("component", "warmupData");
        try {
            // Simulate a slow initialization step for this local exercise.
            Thread.sleep(120);
            return new WarmupData("ready");
        } finally {
            step.end();
        }
    }

    @Bean
    ApplicationRunner reportWarmup(WarmupData data) {
        return args -> System.out.println("warmup=" + data.status());
    }

    record WarmupData(String status) {
    }
}
```

Có ba chi tiết đáng chú ý:

1. Bộ ghi được gắn vào `SpringApplication` trước khi `run` bắt đầu.
2. Mã khởi tạo dùng `ApplicationStartup.start("demo.warmup")` để đánh dấu khoảng công việc cần quan sát, rồi thêm tag `component=warmupData`.
3. `step.end()` nằm trong `finally`, giúp kết thúc khoảng đo ngay cả khi công việc ném ngoại lệ.

Không quên kết thúc bước rồi mới kỳ vọng nó xuất hiện như một sự kiện hoàn chỉnh trong timeline. Tag nên ngắn, có ý nghĩa và không chứa mật khẩu, token hoặc dữ liệu người dùng.

`reportWarmup` chỉ in trạng thái kết quả, không in một thời lượng cố định. Bộ lập lịch của hệ điều hành và các công việc khác có thể khiến thời gian chờ thực tế khác 120 ms; không được viết kết quả đo như một hằng số do mã nguồn quyết định.

### 4.4. Biên dịch, chạy và lấy bản chụp

Trong thư mục chứa `pom.xml`:

```bash
mvn clean package
java -jar target/startup-demo-1.0.0.jar
```

Maven thiết lập các phụ thuộc và gọi trình biên dịch JDK; không biên dịch ứng dụng Spring bằng một lệnh `javac` không có classpath. Nếu đã thêm tệp kiểm chứng ở phần 8, `package` cũng chạy phép kiểm chứng đó.

Ngoài nhật ký Spring Boot, chương trình tự in:

```text
warmup=ready
```

Giữ ứng dụng chạy, mở terminal khác để lưu dữ liệu:

```bash
curl -i http://127.0.0.1:8099/actuator/startup
curl -fsS http://127.0.0.1:8099/actuator/startup -o startup.json
```

Lệnh đầu giúp xem trạng thái HTTP và headers. Lệnh thứ hai chỉ lưu JSON; không dùng đầu ra có headers của `curl -i` làm một tệp JSON thuần. Trên PowerShell, dùng `curl.exe` nếu cần tránh nhầm với alias.

Nếu cấu hình đúng và người gọi được cấp quyền, phản hồi đọc là `200 OK`. Số sự kiện, định danh, thời điểm và thời lượng thay đổi giữa các lần chạy; chúng không phải các giá trị cần giống hệt tài liệu.

## 5. Đọc timeline và quan hệ cha–con

Một bản chụp có cấu trúc chính như sau:

| Trường | Cách hiểu |
| --- | --- |
| `springBootVersion` | Phiên bản Spring Boot của ứng dụng |
| `timeline.startTime` | Mốc bắt đầu timeline ghi nhận, không phải cam kết bao trùm từ lúc hệ điều hành tạo tiến trình |
| `timeline.events` | Các sự kiện đã ghi được tại thời điểm lấy dữ liệu |
| `event.startTime`, `event.endTime` | Thời điểm bắt đầu và kết thúc khoảng đo |
| `event.duration` | Thời lượng dưới dạng chuỗi ISO-8601 |
| `startupStep.name` | Tên bước đo |
| `startupStep.id` | Định danh bước trong lần ghi nhận đó |
| `startupStep.parentId` | Tham chiếu bước cha khi có |
| `startupStep.tags` | Mảng cặp `key/value` bổ sung ngữ cảnh |

Sau đây là JSON rút gọn từ một lần kiểm chứng ví dụ trên: chỉ giữ bước `demo.warmup` và bước tạo bean bao quanh nó. Các số và thời điểm là dữ liệu của lần đo đó; bước cha ở ngoài đoạn rút gọn không được đưa vào.

```json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2026-11-06T05:08:38.068083100Z",
    "events": [
      {
        "endTime": "2026-11-06T05:08:39.212704100Z",
        "duration": "PT0.1217529S",
        "startTime": "2026-11-06T05:08:39.090951200Z",
        "startupStep": {
          "name": "demo.warmup",
          "id": 44,
          "tags": [
            {
              "key": "component",
              "value": "warmupData"
            }
          ],
          "parentId": 43
        }
      },
      {
        "endTime": "2026-11-06T05:08:39.212704100Z",
        "duration": "PT0.1227533S",
        "startTime": "2026-11-06T05:08:39.089950800Z",
        "startupStep": {
          "name": "spring.beans.instantiate",
          "id": 43,
          "tags": [
            {
              "key": "beanName",
              "value": "warmupData"
            }
          ],
          "parentId": 4
        }
      }
    ]
  }
}
```

Trong đoạn này:

- Bước 44 là `demo.warmup`, có `parentId=43`.
- Bước 43 là `spring.beans.instantiate`, với tag `beanName=warmupData`.
- Vì vậy khoảng chờ mô phỏng nằm bên trong việc tạo bean `warmupData`.
- Bước 43 còn tham chiếu tới bước 4, nhưng bước 4 đã được lược khỏi đoạn JSON minh họa.

Không nhầm `parentId` với “bước chạy ngay trước đó”. Đây là quan hệ lồng nhau, không phải số thứ tự để nối mọi sự kiện thành một đường tuyến tính. Cũng không dùng chỉ số phần tử trong mảng làm định danh: mảng có thể chứa bước con kết thúc trước bước cha.

Nếu dựng cây bằng dữ liệu đã lọc, phải chấp nhận rằng một số bước cha không có mặt. Không vì vậy mà tự gán bước cha khác hoặc coi dữ liệu đã bị hỏng. Định danh cũng không phải khóa ổn định để ghép hai lần khởi động khác nhau.

### 5.1. duration không phải số mili giây viết sẵn

`PT0.1217529S` có nghĩa là 0,1217529 giây, tương đương 121,7529 ms. Không bỏ tiền tố rồi diễn giải phần số như mili giây. Không sắp xếp các chuỗi duration theo thứ tự từ điển để tìm bước dài nhất.

Trong Java, dùng `java.time.Duration`. Tệp độc lập `DurationExample.java`:

```java
import java.time.Duration;

public class DurationExample {
    public static void main(String[] args) {
        Duration duration = Duration.parse("PT0.1217529S");
        System.out.println(duration.toNanos() / 1_000_000.0);
    }
}
```

Chạy với JDK 21:

```bash
javac DurationExample.java
java DurationExample
```

Stdout chính xác:

```text
121.7529
```

Chia số nano giây cho `1_000_000.0` giữ phần thập phân khi biểu diễn mili giây. Nếu chỉ gọi `toMillis()`, phần nhỏ hơn một mili giây sẽ không được giữ trong kết quả số nguyên. [Duration của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html).

### 5.2. Không cộng mọi duration thành tổng thời gian khởi động

Thời lượng bước cha thường đã bao gồm thời gian của các bước con diễn ra bên trong nó. Trong JSON trên, bước tạo bean khoảng 122,7533 ms đã bao quanh bước `demo.warmup` khoảng 121,7529 ms. Cộng chúng thành khoảng 244,5062 ms sẽ đếm phần thời gian chờ gần như hai lần.

Một tình huống số học đơn giản:

```text
Bước cha:  0 -------------------------- 600 ms
Bước con A:      100 ----- 300 ms
Bước con B:                  300 ----- 500 ms

Thời gian của bước cha: 600 ms
Tổng duration cha + A + B: 1000 ms
```

1000 ms không phải khoảng thời gian thực đã trôi qua của đoạn công việc 600 ms này.

Ngay cả phép lấy duration cha trừ tổng duration con cũng phải thận trọng: có thể thiếu bước do lọc hoặc hết bộ đệm, có khoảng chồng lấn và có công việc đồng thời. Một phép tính “thời gian riêng” chỉ đáng tin khi đã xác định đủ các khoảng con và xử lý phần giao nhau phù hợp.

Sắp xếp bước dài giúp tìm đầu mối, không tự chứng minh nguyên nhân gốc hay đường xử lý quyết định tổng thời gian khởi động.

## 6. Xếp hạng các bước dài bằng một công cụ nhỏ

Để đọc tệp JSON đã lưu, có thể dùng Python 3 và thư viện chuẩn. Chương trình sau hỗ trợ các duration không âm dạng `PT...` với giờ, phút và giây như dữ liệu startup đang xét; nó báo lỗi nếu gặp định dạng ngoài phạm vi ấy, thay vì đoán đơn vị.

Lưu thành `rank_startup.py`:

```python
import json
import re
import sys
from decimal import Decimal

PATTERN = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")


def duration_ms(text):
    match = PATTERN.fullmatch(text)
    if match is None or not any(match.groups()):
        raise ValueError(f"Unsupported duration: {text}")
    hours, minutes, seconds = (Decimal(value or "0") for value in match.groups())
    return (hours * 3600 + minutes * 60 + seconds) * 1000


with open(sys.argv[1], encoding="utf-8") as stream:
    document = json.load(stream)

events = document["timeline"]["events"]
ranked = sorted(events, key=lambda event: duration_ms(event["duration"]), reverse=True)
for event in ranked[:10]:
    step = event["startupStep"]
    tags = {tag["key"]: tag["value"] for tag in step.get("tags", [])}
    parent = step.get("parentId", "-")
    print(f"{duration_ms(event['duration']):.3f} ms "
          f"id={step['id']} parent={parent} {step['name']} "
          f"bean={tags.get('beanName', '-')}")
```

Chạy trên dữ liệu thực:

```bash
python rank_startup.py startup.json
```

Chương trình chuyển duration thành giá trị số bằng `Decimal`, sắp giảm dần và in tối đa 10 sự kiện. Dùng `beanName` để nhận biết những bước tạo bean; một bước tùy biến có thể dùng tag khác, nên giá trị `bean=-` không có nghĩa bước đó vô ích.

Nếu lưu đúng đoạn JSON rút gọn ở phần 5 thành `startup-excerpt.json`, lệnh:

```bash
python rank_startup.py startup-excerpt.json
```

in ra:

```text
122.753 ms id=43 parent=4 spring.beans.instantiate bean=warmupData
121.753 ms id=44 parent=43 demo.warmup bean=-
```

Đây là kết quả của dữ liệu mẫu cụ thể, không phải lời hứa thời gian đo trên máy khác. Sau khi tìm thấy hai dòng này, cần nhận ra dòng thứ hai nằm trong dòng thứ nhất; không kết luận có hai nút nghẽn độc lập.

## 7. Thu thập có chủ đích và điều tra bước chậm

Một quy trình quan sát hữu ích gồm:

1. **Chốt điều kiện đo:** cùng phiên bản JDK, bản dựng, profile, cấu hình, tài nguyên và điều kiện mạng; ghi rõ có cache ấm, DevTools hay chế độ debug hay không.
2. **Lưu bản chụp sớm sau mốc cần quan sát:** dùng `GET`, giữ dữ liệu gốc cùng thông tin lần chạy.
3. **Kiểm tra tính đầy đủ:** bộ đệm có đủ lớn không, có bộ lọc không, có công cụ khác đã drain không, bước quan tâm đã kết thúc chưa.
4. **Tìm khoảng dài và đọc quan hệ cha–con:** đối chiếu tag, bean và mã khởi tạo tương ứng.
5. **Bổ sung bằng chứng:** xem log, JFR hoặc thông tin về thao tác chờ bên ngoài nếu timeline chưa giải thích được nguyên nhân.
6. **Thay đổi có kiểm soát và đo lại nhiều lần:** so sánh cùng điều kiện, phân biệt biến động môi trường với tác động của thay đổi.

Không khẳng định một tối ưu đã thành công từ một lần chạy nhanh hơn. Thời gian tải lớp, trạng thái đĩa, DNS, kết nối ngoài và tài nguyên CPU có thể khác giữa các lần đo.

Nếu cần lấy dữ liệu ra khỏi bộ đệm để lưu ở nơi khác, ví dụ cục bộ không có Spring Security có thể dùng:

```bash
curl -fsS -X POST http://127.0.0.1:8099/actuator/startup -o startup-drained.json
```

Lệnh này lưu phản hồi JSON của drain. Nếu phía máy khách không lưu được tệp sau khi máy chủ đã lấy dữ liệu ra, dữ liệu cũ không tự quay lại bộ đệm. Khi có nhiều công cụ giám sát, cần thống nhất bên nào được drain và bên nào chỉ đọc snapshot.

`GET` không xóa bước, nhưng điều đó không có nghĩa hai lần GET luôn trả toàn bộ JSON giống hệt nhau: các bước mới vẫn có thể được ghi do khởi tạo muộn hoặc công việc bổ sung. Một phép kiểm chứng tốt so sánh các định danh cũ còn hiện diện, thay vì buộc số lượng sự kiện phải bất biến.

### 7.1. Không dời chi phí rồi coi như đã loại bỏ

Bật lazy initialization có thể làm giảm thời gian trước một mốc khởi động, nhưng cũng có thể chuyển việc tạo bean và phát hiện lỗi sang lần sử dụng đầu tiên. Khi đánh giá, hãy xem thêm thời gian sẵn sàng phục vụ và độ trễ yêu cầu đầu tiên; không chỉ nhìn một con số startup thấp hơn.

Tương tự, đưa công việc sang tác vụ chạy nền không chứng minh ứng dụng đã sẵn sàng về nghiệp vụ. Cần xác định phần việc nào thật sự là điều kiện để phục vụ và quản lý readiness tương ứng.

Nếu cần tương quan các bước Spring với sự kiện JVM như tải lớp hoặc GC, `FlightRecorderApplicationStartup` là một lựa chọn tích hợp JFR khác. Nó không tự thay thế yêu cầu `BufferingApplicationStartup` của endpoint này. Đổi cách ghi phải đi cùng mục tiêu thu thập phù hợp; không giả định mọi cách ghi đều cung cấp cùng bộ đệm JSON.

## 8. Tự kiểm chứng hợp đồng snapshot và drain

Một chi tiết khi viết kiểm chứng là cấu hình bộ ghi nằm trong `main`. Mặc định `@SpringBootTest` không gọi `main`, nên một phép thử có thể khởi tạo ngữ cảnh khác với ứng dụng thật. Dùng `useMainMethod=ALWAYS` để áp dụng đúng cấu hình đó trong ví dụ này. [Cách gọi main trong kiểm chứng Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.using-main).

Lưu tệp `src/test/java/example/StartupEndpointTest.java`:

```java
package example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
@AutoConfigureMockMvc
class StartupEndpointTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test void snapshotPreservesAndPostDrainsRecordedSteps() throws Exception {
        JsonNode first = snapshot();
        Set<Long> originalIds = ids(first);
        assertThat(originalIds).isNotEmpty();
        assertThat(first.path("springBootVersion").asText()).isEqualTo("3.3.13");
        boolean foundWarmup = false;
        for (JsonNode event : first.path("timeline").path("events")) {
            if (event.path("startupStep").path("name").asText().equals("demo.warmup")) {
                foundWarmup = true;
                assertThat(java.time.Duration.parse(event.path("duration").asText()).toMillis())
                        .isGreaterThanOrEqualTo(100L);
                assertThat(event.path("startupStep").has("parentId")).isTrue();
            }
        }
        assertThat(foundWarmup).isTrue();
        Files.writeString(Path.of("target/startup-snapshot.json"), first.toPrettyString());
        assertThat(ids(snapshot())).containsAll(originalIds);
        String body = mvc.perform(post("/actuator/startup"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertThat(ids(mapper.readTree(body))).containsAll(originalIds);
        Set<Long> after = ids(snapshot());
        assertThat(after).doesNotContainAnyElementsOf(originalIds);
    }

    private JsonNode snapshot() throws Exception {
        return mapper.readTree(mvc.perform(get("/actuator/startup"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
    }

    private Set<Long> ids(JsonNode root) {
        Set<Long> result = new HashSet<>();
        root.path("timeline").path("events").forEach(event ->
                result.add(event.path("startupStep").path("id").asLong()));
        return result;
    }
}
```

Chạy:

```bash
mvn test
```

Phép kiểm chứng dùng MockMvc trong tiến trình, không cần mở một máy chủ HTTP thật. Nó xác minh:

- Có dữ liệu startup và có bước tùy biến `demo.warmup`.
- Bước tùy biến có bước cha và thể hiện độ trễ mô phỏng.
- GET tiếp theo vẫn giữ các định danh đã đọc.
- POST trả về các định danh đó trong JSON.
- GET sau drain không còn các định danh đã lấy ra.

Ngưỡng 100 ms trong phép thử chỉ phục vụ bước mô phỏng chờ 120 ms, không phải tiêu chuẩn hiệu năng cho một ứng dụng thật. Phép thử còn lưu bản chụp tại `target/startup-snapshot.json`; có thể đưa tệp đó vào chương trình xếp hạng để quan sát dữ liệu của chính lần kiểm chứng.

Số lượng và danh sách bước khi chạy trong ngữ cảnh kiểm chứng có thể khác khi chạy JAR với máy chủ thật. Phép kiểm chứng bảo đảm hợp đồng thu thập/đọc/drain trong cấu hình đã kiểm tra; nó không biến thời gian của môi trường kiểm chứng thành thời gian khởi động môi trường vận hành.

## 9. Chẩn đoán dữ liệu thiếu hoặc hiểu nhầm thời gian

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Không gọi được `/actuator/startup` | Đúng cổng và đường dẫn chưa; có Actuator, bộ ghi được cấu hình trước run, endpoint được bật và expose không |
| HTTP 401 hoặc 403 | Xác thực, phân quyền; với POST kiểm tra thêm CSRF trong chính sách bảo mật |
| Kiểm chứng không có endpoint nhưng chạy ứng dụng có | Kiểm tra phép thử có áp dụng tùy chỉnh trong main không |
| Timeline không còn các bước cũ | Có công cụ đã gọi POST hoặc API drain không; có đang xem tiến trình/lần chạy khác không |
| Thiếu các bước cuối | Sức chứa, bộ lọc, thời điểm chụp và việc bước đã kết thúc chưa |
| Có parentId không thấy trong dữ liệu | Bước cha có thể bị lọc, chưa có trong đoạn rút gọn hoặc không được giữ lại; không tự nối sang bước khác |
| Một số duration rất nhỏ hoặc hiển thị 0 ms | Kiểm tra đơn vị và việc làm tròn; số nguyên mili giây có thể mất phần nhỏ |
| Tổng các duration lớn hơn thời gian nhật ký | Các bước lồng nhau hoặc chồng lấn bị đếm nhiều lần |
| Không nhìn thấy một thao tác cần điều tra | Kiểm tra thao tác có được đánh dấu bằng StartupStep hay chưa; endpoint không tự đo mọi câu lệnh |
| Ứng dụng chưa mở HTTP hoặc đã khởi động thất bại | Không trông chờ endpoint như kênh điều tra duy nhất; dùng log hoặc công cụ đã cấu hình từ trước |
| Khởi động có vẻ nhanh hơn sau lazy initialization | Kiểm tra thêm chi phí lần dùng đầu tiên và thời điểm ứng dụng thật sự sẵn sàng |

Không nên tăng bộ đệm vô hạn hoặc thêm mọi giá trị vào tag để sửa vấn đề thiếu thông tin. Trước hết xác định phạm vi cần đo; sức chứa lớn hơn và chi tiết nhiều hơn đều có chi phí bộ nhớ và xử lý.

Dữ liệu khởi động tồn tại trong bộ nhớ của tiến trình đang xét, không phải kho lịch sử các lần triển khai. Khi khởi động lại, cần coi đó là một lần ghi mới và lưu bản chụp ngoài tiến trình nếu muốn so sánh về sau.

## 10. Giữ quyền quan sát phù hợp với môi trường vận hành

Timeline có thể tiết lộ tên bean, lớp ứng dụng, cấu trúc khởi tạo và các tag do bạn tự thêm. Chỉ expose cho người hoặc hệ thống thực sự cần quan sát; bảo vệ cả đường truyền lẫn tệp JSON đã xuất.

Trong ứng dụng có Spring Security, quyền đọc GET và quyền drain POST có thể cần được quản lý riêng. CSRF cũng có thể khiến POST bị từ chối dù GET hoạt động; không tắt CSRF toàn ứng dụng chỉ để lệnh curl chạy được. Hãy áp dụng chính sách phù hợp cho máy khách quản trị.

Dừng ứng dụng thực hành bằng Ctrl+C sau khi dùng xong. Kết quả cần đạt khi sử dụng endpoint này là một chuỗi bằng chứng rõ ràng: bộ ghi được bật đủ sớm, dữ liệu được giữ hoặc lấy ra đúng chủ đích, thời lượng được đọc đúng và khoảng chậm được đối chiếu với đúng công việc trước khi đưa ra kết luận tối ưu.
