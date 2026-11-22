# Quan hệ giữa Spring Boot Actuator, Micrometer và hệ thống giám sát bên ngoài

Khi muốn biết ứng dụng đã xử lý bao nhiêu công việc, bạn cần một cách ghi nhận trong mã Java. Khi muốn lấy dữ liệu từ ứng dụng đang chạy, bạn cần một đường truy cập hoặc một cơ chế xuất dữ liệu. Khi muốn xem diễn biến trong nhiều giờ và phát cảnh báo, bạn cần nơi thu thập, lưu trữ và truy vấn.

Spring Boot Actuator, Micrometer và hệ thống giám sát bên ngoài tham gia vào những việc đó với trách nhiệm khác nhau. Hiểu quan hệ giữa chúng giúp bạn tránh tình trạng “đã thêm thư viện nhưng biểu đồ vẫn trống” hoặc “thấy số đo trong ứng dụng nhưng không có lịch sử”.

Bài học dùng Spring Boot 3.3 làm mốc cho cấu hình. Hãy đi theo đường dữ liệu: **đo trong ứng dụng → đăng ký và chuyển đổi → thu thập ra ngoài → lưu, truy vấn và cảnh báo**.

## 1. Bản đồ trách nhiệm

| Thành phần | Trách nhiệm chính trong luồng số đo | Ví dụ |
| --- | --- | --- |
| Mã ứng dụng và thư viện tích hợp | Ghi nhận sự kiện, thời lượng hoặc trạng thái cần đo | Một công việc hoàn tất làm bộ đếm tăng |
| Micrometer | Cung cấp API số đo và cơ chế tích hợp với hệ thống đích | `Counter`, `Timer`, `MeterRegistry` |
| Spring Boot Actuator cùng cấu hình tự động | Tích hợp khả năng vận hành vào ứng dụng Spring Boot, cung cấp các điểm truy cập quản trị | `health`, `metrics`, `prometheus` |
| Hệ thống giám sát bên ngoài | Thu thập, lưu và phân tích dữ liệu theo thời gian | Prometheus hoặc dịch vụ giám sát tương ứng |
| Công cụ hiển thị và cảnh báo | Truy vấn, trình bày dữ liệu và thông báo khi điều kiện thỏa mãn | Grafana; quy tắc Prometheus kết hợp Alertmanager |

Các hàng thể hiện trách nhiệm, không bắt buộc mỗi hàng phải là một máy chủ riêng. Một sản phẩm có thể cung cấp nhiều chức năng, còn một hệ thống lớn có thể tách chúng thành nhiều dịch vụ.

Micrometer tự giới thiệu là lớp API đo đạc trung lập với hệ thống đích. Spring Boot Actuator tích hợp Micrometer và hỗ trợ cấu hình tự động cho các registry có trên đường dẫn thư viện. Tham khảo [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 1.1. Một luồng cụ thể với Prometheus

```text
BÊN TRONG TIẾN TRÌNH SPRING BOOT

Mã nghiệp vụ / cơ chế đo có sẵn
             │ ghi nhận
             ▼
       Micrometer meters
             │
             ▼
    PrometheusMeterRegistry
             │ cung cấp dữ liệu đúng định dạng
             ▼
 /actuator/prometheus của Actuator

BÊN NGOÀI TIẾN TRÌNH

Prometheus ── HTTP GET định kỳ ──> /actuator/prometheus
Prometheus <── dữ liệu trả về ─── /actuator/prometheus
     │
     ├─ Lưu các mẫu số đo theo thời gian
     ├─ Truy vấn bằng PromQL
     └─ Đánh giá quy tắc cảnh báo

Grafana ── truy vấn ──> nguồn dữ liệu Prometheus
```

Trong mô hình này, Prometheus chủ động yêu cầu dữ liệu. Ứng dụng chỉ trả lời mỗi lần được đọc; việc thêm registry không tự tạo một máy chủ Prometheus hay một bảng theo dõi.

[Prometheus Overview](https://prometheus.io/docs/introduction/overview/) mô tả việc lưu số đo thành chuỗi thời gian và mô hình thu thập chủ động qua HTTP. Đây là một cách tích hợp cụ thể; không phải mọi hệ thống giám sát đều lấy dữ liệu theo cùng chiều.

## 2. Micrometer cung cấp những gì?

### 2.1. Thiết bị đo, registry và nhãn

Trong ngữ cảnh Micrometer, một **meter** là đối tượng đo một đại lượng. Ba loại thường gặp:

- `Counter`: đếm số lần một sự kiện xảy ra, chẳng hạn số công việc hoàn tất.
- `Timer`: ghi nhận thời lượng và số lần thực hiện một thao tác.
- `Gauge`: đọc một giá trị trạng thái hiện tại, chẳng hạn độ dài hàng đợi.

**Registry (`MeterRegistry`)** quản lý các meter và cung cấp hành vi phù hợp với hệ thống đích. **Nhãn (`tag`)** bổ sung chiều phân loại, ví dụ cùng số đo công việc nhưng tách theo `result=success` và `result=failure`.

Một `Counter` chỉ tăng bằng lượng dương. Khi theo dõi vận hành, tốc độ tăng trong một khoảng thời gian thường hữu ích hơn tổng tích lũy từ lúc khởi động. Nếu đã dùng `Timer` cho thao tác, nó cũng có số lần ghi nhận; cần tránh thêm một bộ đếm tương đương mà không có mục đích. Xem [Micrometer 1.13 — Counters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

### 2.2. Vì sao cần registry dành cho từng hệ thống?

Một API Java chung không có nghĩa mọi hệ thống bên ngoài dùng cùng định dạng. Registry phù hợp giúp chuyển đổi tên, kiểu biểu diễn và cách cung cấp dữ liệu cho hệ thống đích.

Ví dụ, tên trong mã có thể là `learning.tasks.completed`, còn khi xuất cho Prometheus có thể được chuyển thành dạng dùng dấu gạch dưới và hậu tố dành cho bộ đếm. Vì vậy cần phân biệt **tên meter trong ứng dụng** với **tên chuỗi số đo sau khi xuất**. Quy ước chuyển đổi được mô tả trong [Micrometer 1.13 — Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Không tự suy tên chỉ bằng việc thay dấu chấm: đơn vị, loại meter và quy ước của registry cũng có thể ảnh hưởng. Khi viết truy vấn, hãy kiểm tra dữ liệu thực sự đã xuất.

### 2.3. Registry trong bộ nhớ và registry xuất dữ liệu

`SimpleMeterRegistry` giữ giá trị trong bộ nhớ và không tự xuất dữ liệu đi đâu. `PrometheusMeterRegistry` cung cấp dữ liệu phù hợp để Prometheus đọc. Có thể dùng `CompositeMeterRegistry` để kết hợp nhiều registry.

Các registry không phải kho lưu trữ lịch sử dùng chung giữa các tiến trình. Đặc biệt, tạo một registry mới không làm nó kế thừa giá trị của registry cũ. Xem [Micrometer — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

Trong ứng dụng Spring Boot, nên sử dụng `MeterRegistry` do Spring quản lý khi ghi số đo cho hệ thống đã cấu hình. Nếu một thành phần tự tạo `new SimpleMeterRegistry()` rồi chỉ tăng số đo ở đó, số đo ấy không tự xuất hiện trong registry khác mà Actuator hoặc bộ xuất dữ liệu đang dùng.

## 3. Thử nghiệm Java: Micrometer hoạt động độc lập với Actuator

Thử nghiệm này chỉ cần Micrometer, không chạy Spring Boot và không mở máy chủ HTTP. Mục tiêu là tách rõ việc **ghi nhận số đo** với việc **công khai và lưu số đo ở bên ngoài**.

### 3.1. Chuẩn bị dependency

Dùng JDK 17 trở lên và một bản Gradle tương thích với JDK đang chạy. Trong một thư mục thử nghiệm riêng, tạo `settings.gradle`:

```groovy
rootProject.name = 'metric-boundary-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.6'
}

tasks.register('copyMetricLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

Phiên bản được cố định để thử nghiệm dễ tái lập. Đây là dự án Java độc lập; phần tích hợp Spring Boot bên dưới sẽ dùng cơ chế quản lý phiên bản của Spring Boot.

### 3.2. Chương trình đầy đủ

Lưu tệp `MetricBoundaryDemo.java` tại cùng thư mục với hai tệp Gradle:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MetricBoundaryDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry first = new SimpleMeterRegistry();
        Counter completed = first.counter(
                "learning.tasks.completed", "result", "success");
        completed.increment();
        completed.increment(2);

        System.out.println("first=" + completed.count());
        System.out.println("meters=" + first.getMeters().size());
        first.close();

        SimpleMeterRegistry second = new SimpleMeterRegistry();
        Counter fresh = second.counter(
                "learning.tasks.completed", "result", "success");
        System.out.println("new=" + fresh.count());
        second.close();
    }
}
```

Lệnh trên PowerShell, khi `gradle`, `javac` và `java` có trong đường dẫn:

```powershell
gradle copyMetricLibraries
javac -encoding UTF-8 -cp "lib/*" MetricBoundaryDemo.java
java -cp ".;lib/*" MetricBoundaryDemo
```

Trên Linux/macOS, dấu phân cách classpath ở lệnh chạy là `:`:

```bash
java -cp ".:lib/*" MetricBoundaryDemo
```

Lệnh Gradle tải thư viện cần kết nối kho Maven nếu chưa có bộ nhớ đệm. Kết quả chuẩn của riêng chương trình Java:

```text
first=3.0
meters=1
new=0.0
```

### 3.3. Giải thích kết quả

- `first=3.0`: hai lần tăng là 1 và 2, tổng bằng 3 trong registry thứ nhất.
- `meters=1`: chương trình chỉ đăng ký một meter trong registry đó.
- `new=0.0`: registry thứ hai có bộ đếm mới, dù tên và nhãn giống nhau.

Trong phép thử này, việc in ra console do chính `System.out.println` thực hiện. Nó không phải quá trình xuất số đo sang hệ thống giám sát. Không có `/actuator/metrics`, không có lịch sử ở Prometheus và không có cảnh báo.

Kết quả cho thấy Micrometer có thể dùng ngoài Spring Boot. Khi thêm Actuator vào một ứng dụng Spring Boot, bạn có thêm cách tích hợp và truy cập dữ liệu vận hành; khi thêm hệ thống giám sát bên ngoài, bạn có thể thu thập và khai thác dữ liệu qua thời gian.

## 4. Actuator kết nối số đo với ứng dụng Spring Boot như thế nào?

Actuator cung cấp các điểm truy cập phục vụ vận hành. Trong Spring Boot 3.3, một điểm truy cập phải được bật và được công khai qua cơ chế tương ứng mới có thể sử dụng qua cơ chế đó; quyền truy cập HTTP còn chịu lớp bảo mật.

Mặc định chỉ `health` được công khai qua HTTP. Thêm thư viện Actuator không đồng nghĩa tất cả điểm truy cập đều truy cập được từ mạng. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 4.1. Hai điểm truy cập số đo có mục đích khác nhau

| Điểm truy cập | Đối tượng sử dụng và mục đích |
| --- | --- |
| `/actuator/metrics` | Người phát triển hoặc vận hành kiểm tra tên và giá trị meter đang được đăng ký |
| `/actuator/prometheus` | Prometheus thu thập số đo theo định dạng phù hợp |

API `metrics` không được thiết kế làm nguồn để thu thập định kỳ hoặc làm kho số đo trong môi trường vận hành. Nó hữu ích khi kiểm tra ứng dụng đã ghi nhận gì. Cấu trúc và mục đích được nêu rõ trong [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Điểm truy cập `prometheus` cần registry tương ứng cùng cơ chế công khai HTTP. Micrometer có thể cung cấp dữ liệu Prometheus ngay cả khi không dùng Actuator, nhưng khi đó ứng dụng cần tự tích hợp đường HTTP phù hợp. Xem [Micrometer 1.13 — Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

### 4.2. Các điều kiện cần được kiểm tra riêng

Với mô hình Prometheus đọc Actuator, hãy phân biệt:

1. Ứng dụng có thực sự ghi số đo cần dùng không?
2. Số đo được ghi vào registry nào?
3. Có registry Prometheus và điểm truy cập tương ứng không?
4. Điểm truy cập được công khai và cho phép bên thu thập truy cập chưa?
5. Prometheus có cấu hình mục tiêu, địa chỉ và đường dẫn đúng không?
6. Dữ liệu đã được lưu nhưng truy vấn hoặc bộ lọc đang sai không?

Ví dụ, số đo có trong `metrics` là bằng chứng tốt ở phía ứng dụng. Nó chưa chứng minh Prometheus đã từng đọc thành công.

## 5. Thực hành nối một ứng dụng Spring Boot với Prometheus

Phần này là **các mảnh cấu hình cho ứng dụng Spring Boot 3.3 web có sẵn**, không phải dự án Java độc lập ở phần 3. Giả sử ứng dụng đang hoạt động trên cổng 8080, không đổi tiền tố `/actuator` hay đường dẫn gốc của ứng dụng.

### 5.1. Dependency ở phía ứng dụng

Trong khối `dependencies` của một dự án đã dùng plugin/BOM Spring Boot để quản lý phiên bản, cần các dependency liên quan:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Đây là phần bổ sung; ứng dụng web vẫn cần dependency web và mã khởi động vốn có. Không chép nguyên cấu hình của dự án Java độc lập sang để thay thế cấu hình Spring Boot.

### 5.2. Cấu hình cho môi trường học tập

Hợp nhất vào `application.yml` của môi trường thử nghiệm:

```yaml
spring:
  application:
    name: actuator-lab

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  metrics:
    tags:
      application: "actuator-lab"
```

Nhãn `application` ở ví dụ được đặt rõ để nhận diện dữ liệu. Không mặc định rằng tên ứng dụng sẽ tự trở thành nhãn cho mọi hệ thống đích.

Công khai điểm truy cập không thay thế xác thực và phân quyền. Cấu hình ví dụ giả định một mạng thử nghiệm được kiểm soát; nếu ứng dụng dùng Spring Security, cấu hình quyền đọc theo cơ chế bảo mật hiện có.

### 5.3. Kiểm tra ở phía ứng dụng trước

Trên Windows:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
curl.exe -i "http://localhost:8080/actuator/metrics/jvm.memory.used"
curl.exe -i "http://localhost:8080/actuator/prometheus"
```

Lệnh thứ hai chỉ áp dụng khi `jvm.memory.used` có trong danh sách. Với ứng dụng JVM thông thường có cơ chế đo mặc định tương ứng, đây là ví dụ thuận tiện để kiểm tra mà không cần tạo API nghiệp vụ mới.

Dữ liệu thực tế thay đổi theo tiến trình. Hãy xem đơn vị, các nhãn và tên đã xuất; không mong đợi một giá trị bộ nhớ cố định. Hai điểm truy cập cũng trả cấu trúc khác nhau: dữ liệu chẩn đoán dạng JSON và dữ liệu theo định dạng Prometheus/OpenMetrics được hỗ trợ.

Bộ đếm `learning.tasks.completed` ở phần 3 thuộc một chương trình khác, nên **không tự xuất hiện trong ứng dụng Spring Boot này**. Muốn có số đo nghiệp vụ tương tự ở Spring Boot, mã nghiệp vụ phải ghi vào `MeterRegistry` do ứng dụng đang quản lý.

### 5.4. Cấu hình ở phía Prometheus

Nếu Prometheus và ứng dụng chạy trực tiếp trên cùng máy, một `prometheus.yml` tối giản có thể là:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "actuator-lab"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
```

Khởi động Prometheus với tệp này theo cách cài đặt của bạn, ví dụ khi dùng bản nhị phân:

```powershell
.\prometheus.exe --config.file=prometheus.yml
```

`job_name` đặt tên nhóm mục tiêu; `metrics_path` xác định đường đọc; `targets` xác định địa chỉ mà chính tiến trình Prometheus kết nối tới. Tham khảo [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Nếu Prometheus chạy trong container, `localhost` chỉ chính container đó. Khi ấy cần địa chỉ hoặc tên dịch vụ truy cập được từ mạng của Prometheus. Cấu hình cùng máy ở trên không tự áp dụng cho hai container hoặc hai máy riêng.

### 5.5. Kiểm tra đã thu thập và truy vấn được chưa

Trong giao diện truy vấn Prometheus, kiểm tra:

```promql
up{job="actuator-lab"}
```

Với mục tiêu đang được thu thập, giá trị 1 cho biết lần thu thập thành công; 0 cho biết lần thu thập thất bại. Không có chuỗi nào có thể dẫn tới kiểm tra tên job, cấu hình mục tiêu hoặc thời điểm bắt đầu thu thập. Ý nghĩa các nhãn `job`, `instance` và chuỗi `up` được mô tả trong [Prometheus — Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/).

`up=1` nói về việc lấy số đo, không trực tiếp xác nhận mọi chức năng kinh doanh đang đúng. Nó cũng không phải kết quả `UP` của Actuator Health.

Nếu đầu ra đã có tên `jvm_memory_used_bytes` với nhãn `area="heap"`, có thể thử:

```promql
jvm_memory_used_bytes{job="actuator-lab",area="heap"}
```

Chọn chế độ hiển thị theo thời gian để quan sát các mẫu đã được lưu. Đây là dữ liệu bộ nhớ hiện tại ở mỗi lần thu thập, không phải số sự kiện; không áp dụng phép tính tốc độ của bộ đếm cho nó một cách máy móc.

## 6. Hệ thống bên ngoài bổ sung điều gì?

### 6.1. Lịch sử và truy vấn xuyên nhiều phiên bản chạy

Giả sử có hai phiên bản chạy của cùng ứng dụng. Trong một khoảng quan sát giả định, phiên bản chạy A ghi thêm 30 công việc thành công và phiên bản chạy B ghi thêm 20. Muốn trả lời “dịch vụ hoàn tất bao nhiêu công việc trong khoảng đó”, cần:

- Biết mỗi mẫu thuộc phiên bản chạy nào.
- Dùng cùng định nghĩa “hoàn tất”.
- Xác định cùng khoảng thời gian.
- Xử lý việc bộ đếm có thể được tạo lại khi tiến trình khởi động lại.

Không nên lấy hai tổng tích lũy từ những tiến trình có thời gian sống khác nhau rồi gọi đó là số công việc trong 5 phút.

Với dữ liệu bộ đếm phù hợp, Prometheus có các hàm như `rate` để tính tốc độ trung bình mỗi giây và xử lý việc bộ đếm bị đặt lại. Nên tính tốc độ trên từng chuỗi rồi mới tổng hợp. Tham khảo [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

**Ví dụ minh họa, chỉ dùng nếu ứng dụng Spring Boot thực sự đã ghi và xuất bộ đếm này:**

```promql
sum by (result) (
  rate(learning_tasks_completed_total{job="actuator-lab"}[5m])
)
```

Truy vấn hỏi tốc độ hoàn tất theo từng kết quả, đơn vị là công việc/giây. Nó không chạy trên `SimpleMeterRegistry` của chương trình đã kết thúc ở phần 3. Cần kiểm tra tên chuỗi thực tế, có đủ mẫu và đúng nhãn trước khi diễn giải.

### 6.2. Hiển thị dữ liệu

Trong cách triển khai đang minh họa, Grafana kết nối tới Prometheus như một nguồn dữ liệu rồi dùng truy vấn để vẽ bảng theo dõi.

Grafana có thể kết nối nhiều loại nguồn dữ liệu và hỗ trợ quy tắc cảnh báo. Tuy nhiên, riêng việc cài Grafana không làm ứng dụng tự được thu thập số đo. Cần một đường dữ liệu hoạt động từ nguồn tới nơi lưu mà Grafana truy vấn. Xem [Grafana — Data sources](https://grafana.com/docs/grafana/latest/datasources/).

Nếu Prometheus có dữ liệu nhưng một ô biểu đồ trống, hãy kiểm tra nguồn dữ liệu, truy vấn, khoảng thời gian và các biến lọc trước khi sửa mã Java.

### 6.3. Cảnh báo và gửi thông báo

Trong mô hình cảnh báo của Prometheus, máy chủ đánh giá quy tắc; Alertmanager tiếp nhận cảnh báo để xử lý việc gom nhóm, tạm ngưng và chuyển thông báo tới kênh đã cấu hình. Đây là chức năng cần thiết lập riêng. Xem [Prometheus — Alerting overview](https://prometheus.io/docs/alerting/latest/overview/).

Một `Counter` trong Micrometer không tự biết ai cần được báo. Một điểm truy cập Actuator trả số đo cũng không tự tạo người nhận cảnh báo.

Để thiết kế một quy tắc có ích, hãy viết rõ câu hỏi nghiệp vụ, khoảng thời gian đánh giá, lưu lượng tối thiểu và hành động khi nhận cảnh báo. Đây là phần thiết kế vận hành; không nên coi “có một số vượt ngưỡng” là đủ cho mọi trường hợp.

### 6.4. Giới hạn của lịch sử đã thu thập

Hệ thống bên ngoài chỉ lưu được dữ liệu thực sự nhận được và còn trong thời hạn lưu. Nếu chưa từng thu thập hoặc đã xóa dữ liệu cũ, cài thêm bảng theo dõi không khôi phục được lịch sử đó.

Trong ví dụ một tiến trình chạy rất ngắn rồi kết thúc giữa hai lần đọc, Prometheus có thể không kịp đọc bộ đếm của nó. Tương tự, một thay đổi ngắn của giá trị trạng thái có thể không xuất hiện trong những mẫu cách nhau 15 giây. Hãy chọn cách thu thập theo tuổi thọ tiến trình và câu hỏi cần trả lời.

Số đo tổng hợp cũng không thay cho một sổ giao dịch. Nếu nghiệp vụ cần lưu chính xác từng giao dịch để đối soát, dữ liệu nghiệp vụ bền vững phải được thiết kế riêng; bộ đếm giám sát chỉ phục vụ quan sát theo định nghĩa của nó.

## 7. Mô hình đẩy dữ liệu: không phải mọi registry đều cần Prometheus

Với mô hình **đẩy (push)**, phía ứng dụng hoặc bộ thu thập chủ động gửi dữ liệu tới nơi tiếp nhận. Ví dụ, registry OTLP của Micrometer có thể gửi số đo bằng giao thức OpenTelemetry Protocol tới hệ thống tiếp nhận hỗ trợ giao thức đó.

```text
Mã ứng dụng
    ↓ ghi số đo
Micrometer + registry OTLP
    ↓ gửi dữ liệu theo cấu hình
Bộ tiếp nhận / Collector / hệ thống lưu trữ
    ↓
Truy vấn, hiển thị và cảnh báo
```

Trong Micrometer 1.13, registry OTLP được cung cấp bởi `micrometer-registry-otlp`; cấu hình Spring Boot dùng nhóm thuộc tính `management.otlp.metrics.export`. Cần địa chỉ đích và các thiết lập phù hợp. Xem [Micrometer 1.13 — OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html).

Cấu hình công khai HTTP của Actuator điều khiển người khác đọc các điểm truy cập HTTP. Nó không thay thế cấu hình xuất số đo theo đường đẩy. Nếu không công khai `metrics`, một đường xuất OTLP đã cấu hình đúng vẫn có thể hoạt động.

Ngược lại, với ví dụ Prometheus đọc `/actuator/prometheus`, chặn điểm truy cập đó khiến đường đọc trực tiếp này không lấy được số đo. Cần xác định đang dùng mô hình nào trước khi đổi thuộc tính cấu hình.

| Câu hỏi | Mô hình Prometheus đọc trực tiếp | Ví dụ registry OTLP đẩy dữ liệu |
| --- | --- | --- |
| Ai khởi tạo việc truyền số đo? | Prometheus gửi yêu cầu HTTP | Bộ xuất số đo gửi tới đích |
| Mạng cần thông theo chiều nào? | Từ Prometheus tới ứng dụng | Từ phía xuất tới hệ thống tiếp nhận |
| Đường dẫn HTTP Actuator có vai trò gì? | Cung cấp điểm đọc trong ví dụ | Không phải đường gửi OTLP |
| Thiếu dữ liệu thì kiểm tra ở đâu? | Mục tiêu, lần đọc, quyền truy cập, định dạng | Địa chỉ đích, cấu hình xuất, kết nối, quyền và tiếp nhận |

Thay hệ thống đích có thể giữ lại phần mã ghi số đo theo API Micrometer, nhưng cấu hình kết nối, khả năng biểu diễn và truy vấn vẫn cần rà soát. Tính trung lập của API giúp giảm sự phụ thuộc trong mã; không bảo đảm mọi bảng theo dõi được chuyển nguyên trạng.

## 8. Quan hệ với Observation, Tracing và nhật ký

Tên “Micrometer” có thể xuất hiện ở nhiều thành phần. Cần phân biệt mục đích:

| Thành phần | Vai trò |
| --- | --- |
| Micrometer Metrics và `MeterRegistry` | Ghi và quản lý số đo |
| Micrometer Observation và `ObservationRegistry` | Mô tả một thao tác được quan sát; các bộ xử lý đã cấu hình có thể tạo dữ liệu tương ứng |
| Micrometer Tracing | Tích hợp cơ chế tạo dấu vết và truyền ngữ cảnh với thư viện tương ứng |

Spring Boot dùng Micrometer Observation cho các tích hợp số đo và dấu vết. Một observation chỉ tạo được dữ liệu mà các bộ xử lý đã thiết lập hỗ trợ. Không suy ra rằng có `ObservationRegistry` là mọi dấu vết đều đã được gửi và lưu. Xem [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Để xuất dấu vết cần thành phần tích hợp tracer, bộ xuất và nơi tiếp nhận phù hợp. Thêm registry Prometheus dành cho số đo không tự cấu hình nơi lưu dấu vết. Xem [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Nhật ký có thể được ghi ra đầu ra của tiến trình hoặc tệp rồi được thu thập qua đường riêng. Vì vậy, không nên vẽ toàn bộ dữ liệu quan sát như thể đều đi qua `/actuator/prometheus`. Điểm truy cập đó phục vụ số đo, còn dữ liệu nhật ký và dấu vết cần đường tích hợp tương ứng.

## 9. Chọn số đo có ý nghĩa và kiểm soát ngữ cảnh

Một hệ thống thu thập hoạt động đúng vẫn có thể chứa số đo khó sử dụng. Trước khi đặt tên hay thêm nhãn, hãy mô tả đại lượng muốn đo.

Ví dụ, `learning.tasks.completed` nên có định nghĩa rõ: tăng sau khi công việc đã hoàn tất theo điều kiện nào? Nếu một lần thử được lặp lại, đang đếm lần thử hay kết quả công việc? Hai định nghĩa đều có thể hữu ích, nhưng phải thể hiện bằng tên và cách ghi nhận nhất quán.

Nhãn nên phục vụ câu hỏi có ích và có số giá trị kiểm soát được. Ví dụ `result=success|failure` giúp phân loại kết quả. Ngược lại, dùng mã duy nhất của từng công việc làm nhãn có thể tạo lượng chuỗi rất lớn.

Một phép tính giả định: 2 kết quả × 3 loại công việc × 4 phiên bản chạy tạo tối đa 24 tổ hợp cho một chuỗi thành phần, nếu mọi tổ hợp đều xuất hiện. Thêm 100.000 mã công việc có thể làm quy mô tăng rất mạnh. Đây là cách ước lượng để nhận ra chi phí; một meter có thể tạo nhiều chuỗi, nên không xem 24 là tổng bắt buộc của toàn hệ thống.

Trong mã nghiệp vụ, hãy ghi nhận vào registry được quản lý và hạn chế các giá trị nhãn phát sinh tùy ý từ đầu vào. Khi cần tìm một công việc riêng lẻ, nhật ký hoặc dấu vết có ngữ cảnh thường phù hợp hơn việc tạo một chuỗi số đo riêng cho mỗi mã.

## 10. Tìm lỗi theo chặng thay vì sửa mọi cấu hình cùng lúc

| Dấu hiệu | Chặng cần kiểm tra trước | Bằng chứng nên lấy |
| --- | --- | --- |
| Không tìm thấy meter trong ứng dụng | Đo đạc và đăng ký | Tên meter, đoạn xử lý đã chạy, registry được dùng |
| Có meter trong registry tự tạo nhưng Actuator không thấy | Ranh giới registry | Thành phần có dùng đúng bean `MeterRegistry` không? |
| `metrics` hoạt động nhưng `prometheus` không đọc được | Registry và điểm truy cập | Dependency, trạng thái điểm truy cập, công khai và quyền |
| Máy cá nhân đọc được, Prometheus đọc thất bại | Đường mạng của bên thu thập | Địa chỉ từ chính Prometheus, cổng, TLS, xác thực |
| Prometheus có chuỗi, Grafana trống | Truy vấn và hiển thị | Nguồn dữ liệu, tên sau chuyển đổi, nhãn, khoảng thời gian |
| Biểu đồ giảm mạnh sau khởi động lại | Cách diễn giải bộ đếm | Chuỗi theo từng phiên bản chạy, phép tính tốc độ, thời điểm khởi động |
| Có biểu đồ nhưng không có thông báo | Cảnh báo và chuyển thông báo | Quy tắc, trạng thái đánh giá, cấu hình hệ thống gửi |

Một cách điều tra thực tế:

1. Viết tên số đo và câu hỏi cần trả lời.
2. Kiểm tra ứng dụng có ghi nhận đúng sự kiện hay giá trị không.
3. Kiểm tra số đo ở registry và đầu ra xuất dữ liệu.
4. Kiểm tra bên thu thập có nhận thành công không.
5. Kiểm tra dữ liệu đã lưu bằng truy vấn đơn giản.
6. Sau đó mới kiểm tra bảng theo dõi và quy tắc cảnh báo.

Mỗi bước nên tạo một bằng chứng cụ thể. Ví dụ “curl từ máy tôi thành công” chỉ chứng minh đường truy cập từ máy đó; chưa chứng minh đường mạng từ Prometheus thành công.

## 11. Tự kiểm tra quan hệ giữa ba thành phần

### Tình huống A: chỉ có Micrometer

Một chương trình Java dùng `SimpleMeterRegistry`, tăng bộ đếm rồi thoát.

**Phân tích:** đã có phần ghi nhận số đo trong tiến trình. Chưa có HTTP Actuator, hệ thống thu thập hay lịch sử bên ngoài. Đây chính là ranh giới mà thử nghiệm phần 3 làm rõ.

### Tình huống B: có Actuator và registry Prometheus

Ứng dụng đọc được `/actuator/prometheus`, nhưng chưa chạy Prometheus.

**Phân tích:** phía ứng dụng đã có dữ liệu sẵn sàng cho đường đọc. Chưa có máy chủ bên ngoài lưu mẫu theo thời gian. Một lần đọc bằng trình duyệt không tự tạo lịch sử giám sát.

### Tình huống C: Prometheus thu thập thành công nhưng bảng theo dõi trống

**Phân tích:** bắt đầu từ truy vấn trong Prometheus và nguồn dữ liệu của bảng theo dõi. Có thể tên meter trong Java đã được đổi khi xuất, nhãn lọc sai hoặc cửa sổ thời gian chưa chứa dữ liệu. Chưa có cơ sở để thêm một registry mới.

### Tình huống D: bỏ công khai `metrics` nhưng vẫn có số đo ở hệ thống ngoài

**Phân tích:** xác định đường xuất thực tế. Nếu Prometheus đang đọc `prometheus` hoặc registry đang đẩy OTLP, việc đóng API chẩn đoán `metrics` không đồng nghĩa những đường ấy bị đóng.

### Bài tập áp dụng

Vẽ đường đi của một số đo thực tế trong ứng dụng của bạn và điền sáu thông tin:

1. Sự kiện hoặc trạng thái được đo là gì?
2. Thành phần nào ghi nhận nó?
3. Registry nào đang giữ hoặc xuất nó?
4. Ai khởi tạo việc truyền dữ liệu và truyền qua đâu?
5. Nơi nào lưu lịch sử, nơi nào thực hiện truy vấn?
6. Quy tắc và thành phần nào chịu trách nhiệm thông báo?

Nếu chưa thể điền một bước, hãy ghi rõ bằng chứng cần kiểm tra ở bước đó. Cách làm này giúp biến một cấu hình giám sát thành một luồng dữ liệu có thể giải thích và xác minh.
