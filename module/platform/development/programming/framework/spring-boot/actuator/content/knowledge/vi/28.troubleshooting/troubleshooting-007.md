# Chẩn đoán metrics chưa xuất hiện do chưa phát sinh phép đo hoặc thiếu binder

## 1. Metric không có và metric bằng 0 là hai tình huống khác nhau

Khi tìm một metric trong Actuator mà không thấy, đừng bắt đầu bằng việc gửi thêm thật nhiều request hoặc thêm một dependency bất kỳ. Trước hết cần xác định: meter đã được đăng ký chưa, đoạn mã đo lường đã chạy chưa, và thành phần đăng ký phép đo có tồn tại trong ứng dụng không?

Trong Micrometer, meter là đối tượng đo, chẳng hạn `Counter`, `Timer` hoặc `Gauge`; metric là dữ liệu đo được công bố từ meter đó. Một meter được nhận diện bằng tên và tập nhãn (tags). Cùng một tên có thể có nhiều bộ nhãn và tương ứng nhiều chuỗi dữ liệu. [Khái niệm meter trong Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

| Quan sát | Có thể kết luận gì? | Chưa thể kết luận gì? |
| --- | --- | --- |
| Tên có trong `/actuator/metrics`, COUNT=0 | Có meter tương ứng và giá trị đang là 0 | Không thể nói meter chưa được đăng ký |
| Tên không có, truy vấn riêng trả 404 | Chưa tìm thấy meter khớp trong registry được endpoint quan sát, nếu URL endpoint đã đúng | Chưa xác định được do chưa có hoạt động, thiếu binder hay bị lọc |
| Tên có nhưng truy vấn kèm tag trả 404 | Có tên đó nhưng có thể không có bộ nhãn đang yêu cầu | Không chứng minh toàn bộ metric đã biến mất |
| Actuator có dữ liệu nhưng hệ thống giám sát ngoài chưa có | Phần tạo và đăng ký dữ liệu đã hoạt động ít nhất trong registry đang xem | Không chứng minh đường xuất, thu thập và truy vấn bên ngoài đã đúng |

Mục tiêu của bài là tạo bằng chứng để phân biệt việc đăng ký trễ theo hoạt động với việc thiếu bộ gắn phép đo (binder), rồi kiểm tra các nguyên nhân dễ bị nhầm với hai trường hợp đó. Ví dụ chạy với Spring Boot 3.3.13 và Java 21.

## 2. Theo dõi đường đi của một phép đo

```text
Nguồn cần quan sát: request, pool kết nối, hàng đợi, JVM...
  -> instrumentation / MeterBinder / observation handler
  -> đăng ký meter qua MeterFilter: chấp nhận, chặn hoặc đổi tên/tags
  -> ghi nhận hoặc lấy giá trị của meter trong MeterRegistry
  -> Actuator metrics cho xem dữ liệu đang có
  -> registry xuất dữ liệu ra hệ thống giám sát nếu được cấu hình
```

Đây là mô hình trách nhiệm để khoanh vùng, không phải mọi phép đo đều phải đi qua một lớp có tên MeterBinder. Có phép đo đăng ký trực tiếp trong mã, có phép đo do tích hợp framework tạo ra khi hoạt động hoàn tất, có bộ meter được binder gắn lúc khởi tạo.

`MeterRegistry` giữ các meter. `MeterBinder` có nhiệm vụ đăng ký một hoặc nhiều meter vào registry qua `bindTo`. Với cấu hình Spring Boot thông thường, các bean `MeterBinder` được gắn tự động vào registry do Spring quản lý. Chỉ có class binder trên classpath, hoặc tự `new` một binder mà không gắn nó, chưa bảo đảm có meter. [Đăng ký phép đo và MeterBinder trong Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.registering-custom).

Việc expose endpoint metrics chỉ mở đường quan sát qua HTTP. Nó không tự tạo phép đo nghiệp vụ, không gọi mọi phương thức trong ứng dụng, không tạo một pool kết nối đang thiếu và không tự kích hoạt mọi binder tùy chọn.

## 3. Trường hợp thứ nhất: meter chỉ được tạo khi đường xử lý chạy

### 3.1. Đăng ký trước khác với đăng ký khi cần

Hai đoạn sau minh họa hai thời điểm đăng ký khác nhau. Chúng giả định biến `registry` là `MeterRegistry` được Spring inject; đây là các đoạn mã minh họa, không phải hai chương trình độc lập.

Đăng ký ngay khi khởi tạo thành phần:

```java
Counter counter = Counter.builder("lab.registered").register(registry);
```

Counter đã tồn tại dù chưa gọi `increment`; giá trị ban đầu có thể là 0. Không cần tạo một sự kiện giả chỉ để tên meter xuất hiện.

Đăng ký bên trong đường xử lý:

```java
Timer timer = registry.timer("lab.work.duration", "operation", "compute");
int result = timer.record(() -> 42);
```

Nếu đoạn này chỉ nằm trong handler `/work`, trước lần gọi đầu tiên chưa có chỗ nào yêu cầu đăng ký `lab.work.duration`. Lần gọi đầu vừa đăng ký timer vừa ghi nhận một lượt chạy. `Timer` đo số sự kiện và tổng thời gian; giá trị thời gian thực tế phụ thuộc lần chạy, không nên cố định một con số thời gian trong kiểm thử. [Timer trong Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 3.2. Hoạt động phải đi qua đúng chỗ được gắn phép đo

Không phải mọi request đều làm mọi metric xuất hiện:

- Metric gọi HTTP ra ngoài cần client thực sự thực hiện lời gọi qua tích hợp quan sát phù hợp; gọi HTTP vào ứng dụng không thay thế việc đó.
- Metric của một phương thức cần phương thức được gọi qua cơ chế đo đang có hiệu lực.
- Metric theo một bộ nhãn chỉ xuất hiện khi nhánh xử lý tương ứng tạo bộ nhãn đó.
- Phép đo dựa trên kết thúc hoạt động có thể chưa ghi nhận khi request hoặc công việc vẫn đang chạy.

Ví dụ, nếu chờ `http.server.requests`, hãy gửi một request vào ứng dụng, đợi request hoàn tất rồi đọc lại. Chính việc gọi endpoint Actuator cũng có thể tạo phép đo HTTP, nên danh sách thu trước và sau một lần GET metrics có thể khác nhau. Khi muốn kiểm chứng nguyên nhân một cách rõ ràng, dùng một tên metric riêng cho hành động thử nghiệm thay vì suy từ mọi thay đổi trong danh sách.

Không coi việc thêm `@Timed` lên một phương thức bất kỳ là đủ trong mọi ứng dụng. Cần xác minh cơ chế xử lý annotation, aspect/proxy và đường gọi thực tế. Ví dụ thực hành dưới đây dùng `Timer.record` trực tiếp để thấy rõ thời điểm đăng ký và ghi nhận.

### 3.3. Phép thử có kiểm soát

1. Ghi lại danh sách tên và kết quả truy vấn metric trước hoạt động.
2. Thực hiện đúng một hành động có thể đi tới đoạn mã được đo.
3. Đợi hành động hoàn tất, đọc lại cùng instance và cùng bộ nhãn.
4. Lặp lại một lần để kiểm tra COUNT tăng đúng kỳ vọng.

Nếu tên xuất hiện và COUNT tăng theo hành động, đã có bằng chứng về đăng ký theo hoạt động. Nếu vẫn không có, cần kiểm tra đoạn mã có được đi qua không, rồi mới chuyển sang binder, filter và registry.

Không dùng `registry.timer(name)` để chỉ 'kiểm tra xem timer có tồn tại chưa': phương thức đó có thể tạo timer và làm thay đổi điều đang điều tra. Dùng API tìm kiếm như `registry.find(name).timer()` hoặc endpoint metrics; với API tìm kiếm, kết quả null có nghĩa chưa tìm thấy timer khớp.

## 4. Trường hợp thứ hai: thành phần tạo meter chưa được gắn

Một binder thường đăng ký nhóm phép đo của một nguồn cụ thể. Nếu binder chưa tồn tại hoặc nguồn mà nó cần chưa có, tăng lưu lượng vào endpoint không liên quan sẽ không khắc phục được.

Kiểm tra theo các lớp sau:

| Lớp | Câu hỏi cần xác minh | Bằng chứng phù hợp |
| --- | --- | --- |
| Thư viện lúc chạy | Artifact cung cấp tích hợp có thật trong runtime không? | Dependency graph và gói ứng dụng thực tế |
| Đối tượng nguồn | Pool, cache, client hoặc đối tượng cần quan sát đã được tạo chưa? | Bean/đối tượng đang chạy, không chỉ khai báo trong file cấu hình |
| Điều kiện tự cấu hình | Class, bean, property và profile có đáp ứng điều kiện không? | Báo cáo điều kiện tự cấu hình, log khởi động hoặc kiểm tra context |
| Binder | Có bean binder thích hợp hoặc tích hợp tương đương không? | Bean thực tế và cấu hình tạo bean |
| Gắn vào registry | Binder có được gắn đúng registry không? | Điểm gọi bindTo hoặc quy trình auto-configuration của registry |
| Meter được chấp nhận | Filter có cho đăng ký tên đó không? | Cấu hình enable và các MeterFilter có hiệu lực |

Không phải thư viện nào cũng cung cấp phép đo theo cùng một kiểu bean MeterBinder; một số tích hợp dùng listener, observation hoặc bộ tùy biến client. Hãy tìm cơ chế tương ứng với chính thư viện và phiên bản đang dùng.

Những ví dụ điều kiện thực tế trong Spring Boot 3.3:

- Phép đo Tomcat phụ thuộc MBean registry của Tomcat được bật; không suy rằng có embedded Tomcat thì mọi tên `tomcat.*` chắc chắn tồn tại.
- Cache được tạo sau giai đoạn gắn phép đo có thể cần đăng ký riêng; cấu hình thống kê của thư viện cache cũng có thể là điều kiện.
- Phép đo client HTTP cần dùng client/builder có tích hợp quan sát phù hợp; một client tự tạo ngoài quy trình đó có thể không được đo.

Chỉ thêm dependency sau khi đã xác định thiếu artifact nào và vì sao nó cần có ở runtime. Không tự ghép nhiều phiên bản Micrometer để thử vận may; giữ quản lý phiên bản tương thích với Spring Boot của dự án.

## 5. Những nguyên nhân có biểu hiện giống thiếu binder

### 5.1. Meter bị bộ lọc từ chối

`MeterFilter` có thể từ chối đăng ký, đổi tên hoặc thay tags. Khi bị từ chối, lời gọi đăng ký có thể nhận một meter không ghi dữ liệu (NOOP); mã nghiệp vụ vẫn chạy nên việc handler trả 200 không chứng minh phép đo đã được lưu. [Meter filters của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Ví dụ cấu hình Spring Boot chặn meter có tên bắt đầu bằng tiền tố này:

```properties
management.metrics.enable.lab.queue.depth=false
```

Kiểm tra cả các cấu hình rộng hơn như `management.metrics.enable.all=false`, cấu hình theo tiền tố và các bean `MeterFilter` tự viết. Dùng giá trị có hiệu lực ở profile/instance đang chạy. Nếu vừa thay cấu hình lúc chẩn đoán, cần xác nhận ứng dụng đã áp dụng nó; đừng mặc định mọi filter thay đổi động hoặc dữ liệu lịch sử được phát lại.

Binder có thể tồn tại và đã gọi đăng ký, nhưng meter vẫn không được giữ lại vì filter. Đây là một nguyên nhân khác với thiếu binder.

### 5.2. Đo vào một registry khác

Ưu tiên inject registry do Spring quản lý. Nếu một thành phần tự tạo `new SimpleMeterRegistry()` và chỉ ghi vào đó, endpoint Actuator của ứng dụng không tự tìm tới registry riêng ấy.

Tương tự, nếu dùng API static trên `Metrics`, cần hiểu quan hệ giữa global registry và registry của ứng dụng, nhất là khi đã đổi `management.metrics.use-global-registry`. Không kết luận từ tên class registry giống nhau rằng hai thành phần đang dùng cùng một instance.

Trong điều tra, kiểm tra registry được inject vào nơi ghi và registry mà endpoint/exporter đang dùng. Với composite registry, kiểm tra thêm các registry con; thiếu registry nhận dữ liệu cũng khác với thiếu binder.

### 5.3. Sai tên hoặc sai bộ nhãn

Đọc `/actuator/metrics` để lấy tên thực tế rồi truy vấn tên đó. Endpoint Actuator dùng tên meter trong mã, không dùng tên đã được exporter chuẩn hóa cho hệ thống khác.

Tên xuất sang Prometheus có thể đổi dấu chấm, thêm hậu tố đơn vị hoặc thống kê. Đừng chép nguyên tên chuỗi dữ liệu ở Prometheus vào selector của Actuator rồi kết luận metric mất.

Truy vấn trước khi lọc tags, sau đó thêm từng tag theo `availableTags`. Ví dụ:

```shell
curl -i http://127.0.0.1:8080/actuator/metrics/lab.work.duration
curl -i "http://127.0.0.1:8080/actuator/metrics/lab.work.duration?tag=operation:compute"
```

Trong phiên bản 3.3.13, endpoint trả không có kết quả khi không có meter khớp tên và tags; các phép đo cùng tên có thể được tổng hợp từ nhiều bộ nhãn. COUNT tăng hơn dự kiến có thể do đang xem nhiều series, không nhất thiết do handler chạy lặp. [Cách tìm và tổng hợp trong MetricsEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java).

### 5.4. Gauge chưa có giá trị hợp lệ hoặc đối tượng nguồn đã bị thu gom

Gauge lấy giá trị hiện tại khi được quan sát, không cần một request nghiệp vụ để tăng bộ đếm. Đối tượng trạng thái mà gauge quan sát cần được giữ tham chiếu mạnh ở nơi thích hợp. Nếu đối tượng bị bộ thu gom rác thu hồi, tùy registry có thể thấy NaN hoặc thiếu dữ liệu. Trường hợp đó không nên sửa bằng cách gửi thêm request. [Vòng đời gauge trong Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

Giá trị gauge bằng 0 cũng có thể là kết quả hợp lệ, chẳng hạn hàng đợi đang trống. Cần đối chiếu ý nghĩa của phép đo thay vì xem mọi số 0 là lỗi.

### 5.5. Dữ liệu đã có trong ứng dụng nhưng chưa tới hệ thống giám sát

Nếu Actuator đã cho thấy meter và giá trị đúng, chuyển sang kiểm tra registry xuất dữ liệu, cấu hình exporter, đường thu thập, khoảng thời gian xuất/thu thập, nhãn mục tiêu và khoảng thời gian truy vấn của hệ thống giám sát.

Đừng chờ một chu kỳ xuất dữ liệu để giải thích mãi việc một meter chưa có trong registry cục bộ. Cũng đừng thêm binder chỉ vì dashboard chưa có dữ liệu trong khi Actuator đã xác nhận nó tồn tại.

## 6. Thí nghiệm độc lập với ba kiểu đăng ký

Thí nghiệm có ba tên riêng để tránh lẫn với metric HTTP do chính các lệnh kiểm tra tạo ra:

| Tên | Nơi đăng ký | Trước khi gọi /work |
| --- | --- | --- |
| `lab.registered` | Bean Counter đăng ký lúc khởi tạo | Có, COUNT=0 |
| `lab.work.duration` | Trong handler /work | Chưa có |
| `lab.queue.depth` | MeterBinder có điều kiện | Chỉ có khi binder được bật và meter không bị lọc |

Binder dùng gauge với giá trị mô phỏng 7; đây không phải hàng đợi thật. Handler /work trả 42 và được dùng để kiểm chứng timer. Nó dùng GET vì chỉ là phép tính minh họa, không thực hiện thay đổi nghiệp vụ.

### 6.1. Tạo dự án

Dùng JDK 21, Maven 3.6.3 trở lên và Python 3. Cần kết nối kho Maven nếu dependency chưa có trong bộ nhớ đệm.

```text
metrics-diagnosis-lab/
├── pom.xml
├── verify.py
└── src/main/
    ├── java/example/metrics/MetricsDiagnosisLab.java
    └── resources/application.properties
```

Tệp pom.xml:

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
    <groupId>example</groupId>
    <artifactId>metrics-diagnosis-lab</artifactId>
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

Tệp src/main/resources/application.properties:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,metrics
lab.binder-enabled=false
```

Ví dụ chỉ lắng nghe loopback để thực hành tại máy cá nhân, không thêm dependency Spring Security. Khi áp dụng trong dịch vụ thực, giữ chính sách xác thực/phân quyền của dịch vụ; không công khai metrics chỉ để thuận tiện chẩn đoán.

Tệp src/main/java/example/metrics/MetricsDiagnosisLab.java:

```java
package example.metrics;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MetricsDiagnosisLab {
    public static void main(String[] args) {
        SpringApplication.run(MetricsDiagnosisLab.class, args);
    }

    @Bean
    Counter registeredCounter(MeterRegistry registry) {
        return Counter.builder("lab.registered")
            .description("Registered without increments")
            .register(registry);
    }

    @Bean
    @ConditionalOnProperty(name = "lab.binder-enabled", havingValue = "true")
    MeterBinder queueDepthBinder() {
        return new QueueDepthBinder();
    }

    static final class QueueDepthBinder implements MeterBinder {
        private final AtomicInteger depth = new AtomicInteger(7);

        @Override
        public void bindTo(MeterRegistry registry) {
            Gauge.builder("lab.queue.depth", depth, AtomicInteger::get)
                .description("Simulated queue depth")
                .register(registry);
        }
    }

    @RestController
    static class WorkController {
        private final MeterRegistry registry;

        WorkController(MeterRegistry registry) {
            this.registry = registry;
        }

        @GetMapping("/work")
        public Map<String, Integer> work() {
            Timer timer = registry.timer("lab.work.duration", "operation", "compute");
            int result = timer.record(() -> 42);
            return Map.of("result", result);
        }
    }
}
```

`QueueDepthBinder` giữ `depth` trong một trường của bean, nên đối tượng nguồn có tham chiếu mạnh khi binder còn tồn tại. Spring Boot gọi bindTo theo quy trình gắn binder; handler /work không tự gọi binder và không tạo gauge thay cho binder.

### 6.2. Build và khởi động

Chạy tại thư mục gốc của dự án:

```shell
mvn package
java -jar target/metrics-diagnosis-lab-1.0.0.jar
```

Đây là dự án có dependency Spring Boot; chỉ gọi `javac` trên một tệp sẽ không cung cấp đầy đủ classpath. Giữ ứng dụng chạy và mở terminal thứ hai tại cùng thư mục. Kiểm tra cổng 8080 đang thuộc ứng dụng này.

### 6.3. Kiểm chứng bằng thư viện chuẩn Python

Tệp verify.py nhận hai lựa chọn để kiểm tra gauge và timer có được công bố hay không. Mỗi lần chạy script cần một tiến trình ứng dụng mới, chưa được gọi /work, vì script cố ý kiểm tra trạng thái trước lần ghi đầu tiên.

```python
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8080"


def read_json(path):
    request = Request(BASE + path, headers={"Accept": "application/json"})
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        return response.code, json.loads(raw) if raw else None


def metric(name):
    return read_json("/actuator/metrics/" + name)


def statistic(body, name):
    matches = [item["value"] for item in body["measurements"]
               if item["statistic"] == name]
    assert len(matches) == 1, body
    return matches[0]


def gauge(stage, present):
    code, body = metric("lab.queue.depth")
    if present:
        assert code == 200 and statistic(body, "VALUE") == 7, (code, body)
        print(f"gauge {stage}: VALUE=7")
    else:
        assert code == 404, (code, body)
        print(f"gauge {stage}: HTTP=404")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gauge", choices=["present", "absent"], default="absent")
    parser.add_argument("--timer", choices=["present", "absent"], default="present")
    args = parser.parse_args()
    gauge_present = args.gauge == "present"
    timer_present = args.timer == "present"

    code, body = metric("lab.registered")
    assert code == 200 and statistic(body, "COUNT") == 0, (code, body)
    print("registered counter: COUNT=0")

    code, body = metric("lab.work.duration")
    assert code == 404, (code, body)
    print("timer before work: HTTP=404")
    gauge("before work", gauge_present)

    for _ in range(2):
        code, body = read_json("/work")
        assert code == 200 and body == {"result": 42}, (code, body)
    print("work: result=42, calls=2")

    code, body = metric("lab.work.duration")
    if timer_present:
        assert code == 200 and statistic(body, "COUNT") == 2, (code, body)
        assert statistic(body, "TOTAL_TIME") >= 0, body
        code, filtered = read_json(
            "/actuator/metrics/lab.work.duration?tag=operation:compute")
        assert code == 200 and statistic(filtered, "COUNT") == 2, (code, filtered)
        print("timer after work: COUNT=2")
    else:
        assert code == 404, (code, body)
        print("timer after work: HTTP=404")

    code, body = read_json(
        "/actuator/metrics/lab.work.duration?tag=operation:other")
    assert code == 404, (code, body)
    print("unmatched tag: HTTP=404")
    gauge("after work", gauge_present)

    code, body = read_json("/actuator/metrics")
    assert code == 200, (code, body)
    names = set(body["names"])
    assert "lab.registered" in names, names
    assert ("lab.work.duration" in names) == timer_present, names
    assert ("lab.queue.depth" in names) == gauge_present, names


if __name__ == "__main__":
    main()
```

Với cấu hình ban đầu, chạy:

```shell
python verify.py
```

Stdout chính xác:

```text
registered counter: COUNT=0
timer before work: HTTP=404
gauge before work: HTTP=404
work: result=42, calls=2
timer after work: COUNT=2
unmatched tag: HTTP=404
gauge after work: HTTP=404
```

Kết quả cho thấy ba tình huống khác nhau: counter đã đăng ký nhưng chưa ghi sự kiện; timer xuất hiện sau khi đường xử lý được gọi; gauge vẫn thiếu vì binder đang tắt. Hai request /work không tạo được gauge mà binder chưa đăng ký.

Script không cố định TOTAL_TIME hay MAX vì chúng phụ thuộc thời gian chạy và cách triển khai registry. Nó kiểm tra COUNT, kết quả nghiệp vụ, trạng thái HTTP và danh sách tên để xác nhận đúng điều cần học.

### 6.4. Bật binder rồi quan sát trước khi phát sinh hoạt động

Dừng ứng dụng bằng Ctrl+C, khởi động một tiến trình mới:

```shell
java -jar target/metrics-diagnosis-lab-1.0.0.jar --lab.binder-enabled=true
```

Ở terminal thứ hai:

```shell
python verify.py --gauge present
```

Stdout:

```text
registered counter: COUNT=0
timer before work: HTTP=404
gauge before work: VALUE=7
work: result=42, calls=2
timer after work: COUNT=2
unmatched tag: HTTP=404
gauge after work: VALUE=7
```

Gauge đã có trước khi gọi /work vì binder đã được tạo và gắn khi khởi tạo. Điều kiện cần ở đây là binder, không phải lưu lượng vào /work.

### 6.5. Binder có mặt nhưng gauge bị lọc

Dừng tiến trình trước, rồi chạy:

```shell
java -jar target/metrics-diagnosis-lab-1.0.0.jar --lab.binder-enabled=true --management.metrics.enable.lab.queue.depth=false
```

Kiểm chứng:

```shell
python verify.py --gauge absent
```

Gauge lại không có dù điều kiện tạo binder đang bật. Timer vẫn xuất hiện và COUNT tăng sau /work. Không nên tiếp tục thêm một binder thứ hai để sửa trường hợp này; cần kiểm tra filter đang chặn đúng tên gauge.

### 6.6. Handler chạy tốt nhưng timer không ghi dữ liệu

Dừng tiến trình trước, rồi chạy:

```shell
java -jar target/metrics-diagnosis-lab-1.0.0.jar --lab.binder-enabled=true --management.metrics.enable.lab.work.duration=false
```

Kiểm chứng:

```shell
python verify.py --gauge present --timer absent
```

Handler vẫn trả 42 cho cả hai lần gọi, gauge vẫn có VALUE=7, nhưng timer không xuất hiện sau hoạt động. Bộ lọc chặn phép đo không có nghĩa nó chặn việc thực hiện callback của `Timer.record`.

Trong môi trường đang có bộ lọc, đây là lý do phải kiểm chứng cả kết quả nghiệp vụ và dữ liệu đo thay vì suy luận 'request thành công thì timer chắc đã tăng'.

## 7. Quy trình áp dụng vào sự cố thực tế

### Bước 1: Xác nhận endpoint trước khi điều tra một tên metric

Kiểm tra `/actuator/metrics` có hoạt động ở đúng management port/base path và người gọi có quyền đọc không. 401/403 là vấn đề truy cập cần xử lý trước; một 404 của cả endpoint không đồng nghĩa một metric riêng chưa được tạo.

Giữ phạm vi expose nhỏ theo chính sách của dịch vụ. Không cần expose `*` chỉ để đọc metrics. Endpoint metrics dành cho chẩn đoán, không phải nơi lưu lịch sử hoặc endpoint để hệ thống giám sát scrape thay cho backend chuyên dụng. [Hợp đồng endpoint metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### Bước 2: Xác nhận đúng tên, instance và tập nhãn

Lưu danh sách names, đọc metric không lọc trước rồi thêm tags. Nếu request đi qua cân bằng tải, cần bảo đảm hành động thử và lần đọc metric thuộc cùng instance hoặc hiểu rõ cách tổng hợp của hệ thống phía trước.

Dữ liệu cục bộ trong bộ nhớ có thể mất khi tiến trình khởi động lại. Tên từng xuất hiện ở instance cũ không chứng minh instance mới đã tạo cùng meter.

### Bước 3: Xác định ai chịu trách nhiệm đăng ký

Tìm chỗ gọi builder/register, `registry.counter`, `registry.timer`, binder, listener hoặc observation handler tương ứng. Xác định chỗ đó chạy khi khởi động hay khi phát sinh hoạt động.

Nếu không có cơ chế nào đăng ký metric nghiệp vụ đang mong đợi, việc chờ thêm thời gian sẽ không tạo ra nó. Cần bổ sung phép đo có mục đích và tên/tags ổn định, không giả định Actuator tự hiểu mọi thao tác nghiệp vụ.

### Bước 4: Tạo đúng một hoạt động đại diện

Chọn một hành động có tác động phù hợp với môi trường điều tra. Trên hệ thống thực, không tạo đơn hàng, gửi email hoặc ghi dữ liệu thật chỉ để thấy một counter. Dùng môi trường thử nghiệm hoặc thao tác đã được cho phép.

Xác nhận handler/phương thức/client cần đo thực sự chạy và hoạt động đã kết thúc. Đọc lại metric, kiểm tra COUNT hoặc VALUE phù hợp với loại meter; không áp kỳ vọng tăng COUNT cho một gauge.

### Bước 5: Kiểm tra binder và điều kiện

Nếu chưa có, kiểm tra dependency runtime, nguồn cần quan sát, bean binder/tích hợp, property và profile. Có thể dùng báo cáo điều kiện tự cấu hình hoặc kiểm tra context trong môi trường phát triển. Không mở công khai beans/conditions của hệ thống chỉ để thuận tiện.

Nếu nguồn được tạo động sau khi ứng dụng khởi động, kiểm tra tích hợp có tự theo dõi nguồn mới không hay cần gắn phép đo rõ ràng. Tránh đăng ký lặp gây cảnh báo hoặc giữ tham chiếu tới nguồn đã hết vòng đời.

### Bước 6: Loại trừ filter và registry

Kiểm tra cấu hình enable, các bean MeterFilter và registry thực sự nhận dữ liệu. Khi đặt breakpoint hoặc log chẩn đoán, dùng API tìm kiếm thay vì API có tác dụng đăng ký mới.

Cũng kiểm tra cảnh báo trùng ID, khác loại meter hoặc thay đổi tags sau filter. Giữ bộ nhãn hữu hạn; không dùng requestId, userId hay URL chứa ID thô làm tags chỉ để 'dễ tìm', vì sẽ tạo quá nhiều chuỗi dữ liệu.

### Bước 7: Chỉ sau đó mới kiểm tra đường xuất ra ngoài

Nếu registry/Actuator đã có dữ liệu đúng, kiểm tra exporter, lịch xuất/thu thập và truy vấn backend. Nếu chưa có dữ liệu cục bộ, quay về điểm tạo phép đo; thay cấu hình dashboard không giải quyết được việc chưa đăng ký meter.

## 8. Các kết luận cần tránh

| Kết luận vội | Vì sao chưa đủ | Phép kiểm chứng tốt hơn |
| --- | --- | --- |
| Chưa có request nên mọi metric đều vắng | Nhiều meter đăng ký ngay lúc khởi tạo | Kiểm tra meter được đăng ký ở đâu và giá trị 0 có hợp lệ không |
| Gửi nhiều request chắc sẽ tạo metric | Có thể đang thiếu binder hoặc request không đi qua nguồn được đo | Tạo đúng một hoạt động và xác nhận đường xử lý |
| Có dependency là có binder hoạt động | Còn điều kiện bean/property/runtime và việc gắn registry | Xác nhận tích hợp có hiệu lực trong ứng dụng đang chạy |
| Binder tồn tại nên metric chắc tồn tại | Filter có thể từ chối; binder có thể gắn sai registry | Kiểm tra filter và registry thực tế |
| COUNT=0 nghĩa là metric mất | Meter đã có, chỉ chưa ghi sự kiện hoặc giá trị đang hợp lệ | Phân biệt sự tồn tại với giá trị |
| Gauge NaN chắc do chưa gọi API | Đối tượng nguồn có thể bị thu gom hoặc giá trị không hợp lệ | Kiểm tra vòng đời nguồn và hàm lấy giá trị |
| Dashboard trống nghĩa là Actuator chưa tạo metric | Có thể đứt ở đường xuất hoặc truy vấn | Đối chiếu registry, Actuator rồi backend theo từng tầng |

## 9. Bài tập tự kiểm tra

1. Counter đã được register lúc khởi tạo, chưa increment lần nào. Có bắt buộc phải vắng khỏi danh sách metrics không?
2. Timer nằm trong handler /work, chưa gọi handler. Cần kiểm tra điều gì trước khi thêm dependency?
3. Gauge chỉ có trong một binder đang bị điều kiện property tắt. Gọi /work thêm 100 lần có giải quyết được không?
4. Binder bật, handler chạy, nhưng tên meter vẫn không có. Hai tầng nào cần kiểm tra ngay sau đó?
5. Truy vấn không tags có dữ liệu, thêm tag operation:other thì 404. Có thể kết luận binder đã biến mất không?
6. Dùng registry.timer(name) trong debugger để tìm meter có thể làm sai lệch điều tra thế nào?

Hướng đối chiếu: câu 1 counter có thể tồn tại với COUNT=0; câu 2 kiểm tra đường xử lý và thời điểm đăng ký; câu 3 không, phải đáp ứng điều kiện tạo/gắn binder; câu 4 filter và registry, đồng thời xác nhận binder thực sự đã gắn; câu 5 không, có thể chỉ sai bộ nhãn; câu 6 thao tác tìm tưởng là đọc có thể đăng ký một timer mới.

Kết quả chẩn đoán nên nêu được ai tạo meter, thời điểm tạo, hoạt động nào ghi dữ liệu, registry nào nhận nó, filter nào áp dụng và phép thử nào xác nhận nguyên nhân. Những bằng chứng đó giúp sửa đúng điều kiện đang thiếu thay vì làm metric xuất hiện bằng một thay đổi ngẫu nhiên.
