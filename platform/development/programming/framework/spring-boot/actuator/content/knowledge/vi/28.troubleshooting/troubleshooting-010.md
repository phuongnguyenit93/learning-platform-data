# Tìm nguyên nhân Prometheus scrape lỗi hoặc registry không xuất được dữ liệu

## 1. Hiểu đúng đường đi của một phép đo

Trong Spring Boot Actuator, một phép đo không đi thẳng từ mã Java tới màn hình biểu đồ. Nó đi qua nhiều lớp:

```text
Mã ứng dụng / bộ đo tự động của Spring Boot
                 |
                 v
MeterRegistry mà ứng dụng thực sự sử dụng
                 |
                 v
PrometheusMeterRegistry và bộ thu thập của nó
                 |
                 v
HTTP endpoint /actuator/prometheus
                 |
                 v
Prometheus kết nối, đọc và phân tích bản xuất
                 |
                 v
Mẫu dữ liệu được chấp nhận, lưu trữ và truy vấn
```

**Registry** là nơi Micrometer quản lý các bộ đo (meter), chẳng hạn bộ đếm, đồng hồ đo thời gian và giá trị tức thời. **Scrape** là việc Prometheus chủ động gửi HTTP request tới ứng dụng rồi đọc bản xuất các phép đo. Trong cơ chế thông thường này, Spring Boot không chủ động đẩy dữ liệu sang Prometheus.

Vì vậy, “không thấy dữ liệu” có thể là những sự cố khác nhau:

- Prometheus không kết nối được tới ứng dụng.
- Kết nối được nhưng sai đường dẫn, không được xác thực hoặc nhận sai định dạng.
- Endpoint hoạt động nhưng bộ đo cần tìm không nằm trong registry được xuất.
- Bản xuất có bộ đo nhưng Prometheus loại bỏ hoặc từ chối mẫu dữ liệu.
- Prometheus đã lưu dữ liệu nhưng truy vấn dùng sai tên, nhãn hoặc khoảng thời gian.

Mục tiêu chẩn đoán là tìm **ranh giới đầu tiên mà bằng chứng không còn đúng**. Chỉ sửa cấu hình ở lớp đó; không bật hàng loạt endpoint hoặc thay mọi dependency cùng lúc.

Các ví dụ cấu hình dưới đây dùng Spring Boot 3.3.x, Java 17+ và Micrometer do Spring Boot quản lý phiên bản. Nếu ứng dụng dùng phiên bản khác, cần đối chiếu tên thuộc tính và loại Prometheus client với phiên bản đang chạy, thay vì chép cấu hình từ một bài viết cũ.

## 2. Thu thập bằng chứng trước khi thay đổi

Ghi lại ít nhất các thông tin sau cho đúng instance đang lỗi:

| Bằng chứng | Câu hỏi cần trả lời |
| --- | --- |
| Phiên bản thực tế | Spring Boot, Micrometer và Prometheus client nào đã được resolve? |
| Địa chỉ quản trị | Scheme, host, port và đường dẫn đầy đủ nào đang được scrape? |
| Nguồn gửi request | Request đến từ máy cá nhân, container Prometheus hay Pod nào? |
| Phản hồi HTTP | Status, Content-Type và nội dung thực tế là gì? |
| Trạng thái target | Last scrape, Last error và nhãn job/instance nào? |
| Bộ đo cần tìm | Tên Micrometer, tên xuất Prometheus và bộ nhãn dự kiến là gì? |
| Cấu hình có hiệu lực | Profile, biến môi trường và tham số dòng lệnh nào đang ghi đè? |
| Thời điểm | Lỗi bắt đầu sau triển khai, đổi dependency, đổi bảo mật hay tăng tải? |

Không dùng việc mở được URL trên trình duyệt máy cá nhân để kết luận Prometheus cũng truy cập được. Hai bên có thể dùng DNS, đường mạng, thông tin xác thực và chứng chỉ khác nhau.

Khi chia sẻ log hoặc kết quả kiểm tra, loại bỏ mật khẩu, token và thông tin xác thực. Chỉ cần giữ lại địa chỉ phù hợp để chẩn đoán, mã lỗi và các phần phản hồi cần thiết.

### Kiểm tra HTTP nguyên trạng

Lệnh sau dùng cú pháp shell kiểu Bash; trên Windows có thể gọi rõ `curl.exe` và điều chỉnh cách đặt biến/đường dẫn cho PowerShell:

```bash
curl -i --max-time 10 http://localhost:8080/actuator/prometheus
```

Đọc cả header lẫn body:

- `200` và văn bản metric: đi tiếp tới bước kiểm tra bộ đo và ingestion.
- `200` nhưng body là HTML: có thể đang nhận trang đăng nhập, trang lỗi hoặc trang của frontend.
- `301`/`302`: kiểm tra `Location`; redirect có thể đưa request sang scheme, host hoặc trang đăng nhập khác.
- `401`/`403`: đi vào nhánh xác thực/phân quyền.
- `404`: kiểm tra dependency, trạng thái endpoint, exposure và đường dẫn.
- `500`: kiểm tra lỗi phía ứng dụng trong lúc thu thập/xuất.
- Không có HTTP response: ưu tiên DNS, TCP, TLS và timeout.

Không thêm `-L` ngay trong lần kiểm tra đầu, vì theo redirect có thể che mất phản hồi gốc. Khi cần mô phỏng Prometheus, kiểm tra hành vi redirect thực tế trong cấu hình scrape của nó.

## 3. Cây quyết định ngắn

```text
Prometheus có một target đúng cho instance này không?
  Không -> kiểm tra discovery, relabel và scrape config
  Có
   |
   +-- Không kết nối/timeout/TLS -> xử lý mạng và địa chỉ
   |
   +-- Có HTTP nhưng 401/403/404/500 -> xử lý endpoint/bảo mật/xuất dữ liệu
   |
   +-- 200 nhưng không đọc được metric -> kiểm tra body, Content-Type, định dạng
   |
   +-- 200 và có metric hợp lệ
          |
          +-- Thiếu metric cần tìm ngay trong body -> kiểm tra MeterRegistry/meter
          |
          +-- Body đã có metric -> kiểm tra ingestion, relabel và truy vấn
```

Thứ tự này giúp tránh một lỗi suy luận phổ biến: sửa câu PromQL khi endpoint còn trả `404`, hoặc sửa registry khi Prometheus đang trỏ tới sai container.

## 4. Nhánh một: Prometheus không tìm thấy hoặc không kết nối được target

### 4.1. Xác nhận target thực tế

Trong trang Targets hoặc API trạng thái target của Prometheus, kiểm tra:

- Target có tồn tại và đang ở trạng thái active hay không.
- Scrape URL sau discovery/relabel có đúng host, port, scheme và path không.
- Các nhãn `job`, `instance` và nhãn từ discovery có chỉ đúng instance không.
- `Last error` nói về DNS, kết nối, TLS, HTTP hay parse dữ liệu.
- Thời điểm lần scrape gần nhất có phù hợp với lần triển khai hiện tại không.

Nếu không có target, ứng dụng chưa chắc đã hỏng. Nguyên nhân có thể nằm ở file scrape chưa được nạp, discovery không trả instance, hoặc `relabel_configs` đã loại bỏ target.

Trong môi trường Kubernetes, phải phân biệt cổng container, cổng Service, `targetPort` và cấu hình discovery. Việc khai báo một annotation không tự có tác dụng nếu hệ thống Prometheus đang dùng không đọc annotation đó.

### 4.2. Lỗi localhost giữa các container

`localhost` luôn chỉ môi trường mạng của tiến trình gửi request. Prometheus trong container gọi `localhost:8080` là đang gọi chính container Prometheus, không phải ứng dụng Spring Boot trong container khác.

Ví dụ hai service cùng mạng Docker Compose:

```yaml
scrape_configs:
  - job_name: boot-actuator
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["app:8080"]
```

Trong ví dụ này, `app` phải là tên service phân giải được trên mạng mà Prometheus tham gia. Nếu management server chạy trên cổng `9091`, target phải dùng `app:9091`. Cổng publish ra host và cổng giao tiếp nội bộ container có thể khác nhau.

### 4.3. Phân loại lỗi kết nối

| Dấu hiệu | Giả thuyết ưu tiên | Cách kiểm chứng |
| --- | --- | --- |
| Không phân giải được tên | DNS hoặc tên service sai | Kiểm tra DNS từ môi trường Prometheus |
| Connection refused | Sai cổng, chưa có listener hoặc ứng dụng đã dừng | Đối chiếu cổng listener và log khởi động |
| Connection timeout | Route, firewall, NetworkPolicy hoặc đích không phản hồi | Thử kết nối từ cùng mạng và kiểm tra chính sách |
| TLS handshake/certificate error | Sai scheme, CA không tin cậy, tên chứng chỉ không khớp hoặc yêu cầu mTLS | Kiểm tra chứng chỉ, hostname và TLS config |
| Timeout sau khi đã kết nối | Endpoint chậm, proxy chậm hoặc tải cao | Đo thời gian phản hồi và xem log/thread dump phù hợp |

`management.server.address=127.0.0.1` trên một management server riêng có thể làm nó chỉ nhận kết nối loopback. Không đổi thành lắng nghe mọi địa chỉ theo phản xạ; xác định mạng nào cần được phép truy cập và cấu hình đúng ranh giới đó.

Với TLS, dùng CA và tên máy chủ đúng trong cấu hình Prometheus. Bỏ kiểm tra chứng chỉ chỉ che lỗi cấu hình; nó không phải bằng chứng rằng tuyến scrape đã được thiết lập đúng.

## 5. Nhánh hai: endpoint không tồn tại hoặc trả sai HTTP status

### 5.1. Bốn điều kiện để có bản xuất Prometheus

Trong trường hợp tự cấu hình thông thường, cần kiểm tra đủ:

1. Có Actuator trên runtime classpath.
2. Có registry Prometheus phù hợp trên runtime classpath và không bị vô hiệu hóa.
3. Endpoint `prometheus` không bị tắt.
4. Endpoint được expose qua HTTP và request đi tới đúng đường dẫn, đúng cổng.

Một cấu hình tham khảo cho Spring Boot 3.3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Đoạn trên là phần `dependencies` của một dự án Gradle đã áp dụng Spring Boot plugin và cơ chế quản lý dependency của Spring Boot. Nó không phải một `build.gradle` độc lập.

Dùng phiên bản Micrometer do BOM của Spring Boot quản lý, trừ khi có lý do tương thích đã được xác minh. Không tự ghép một phiên bản `micrometer-core` với một phiên bản registry/client khác rồi kết luận lỗi do Actuator.

Kiểm tra dependency thực tế bằng task của đúng Gradle project:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

Trong multi-project build, thêm project path thích hợp trước tên task. Trên Windows dùng `gradlew.bat`. Dependency có trong `testRuntimeClasspath` hoặc trong một module khác không chứng minh ứng dụng đang chạy có nó.

### 5.2. Cấu hình endpoint và export

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    prometheus:
      enabled: true
  prometheus:
    metrics:
      export:
        enabled: true
```

Ba nhánh có ý nghĩa khác nhau:

- `management.endpoints.web.exposure.include`: chọn endpoint được công bố qua HTTP.
- `management.endpoint.prometheus.enabled`: trạng thái bật/tắt endpoint theo mô hình cấu hình Spring Boot 3.3.x.
- `management.prometheus.metrics.export.enabled`: bật/tắt auto-configuration export Prometheus của Micrometer trong Boot 3.3.x.

Có registry không đồng nghĩa endpoint đã expose. Expose `prometheus` cũng không tự bổ sung dependency còn thiếu.

Kiểm tra thêm `management.endpoints.web.exposure.exclude`, vì exclude được ưu tiên hơn include. Nếu ứng dụng tắt mặc định toàn bộ endpoint bằng `management.endpoints.enabled-by-default=false`, phải kiểm tra việc bật lại endpoint cụ thể. Với metrics, cũng cần kiểm tra cấu hình tắt exporter mặc định và việc bật riêng exporter Prometheus.

Các cấu hình kiểu `management.metrics.export.prometheus.enabled` từ thế hệ Spring Boot cũ không nên được chép nguyên sang Boot 3.3.x. Một thuộc tính không còn được nhận có thể không tạo lỗi khởi động như người dùng kỳ vọng.

Nếu cấu hình YAML đúng mà hành vi vẫn sai, kiểm tra profile active, biến môi trường, cấu hình bên ngoài và tham số dòng lệnh. Bằng chứng cần là **giá trị có hiệu lực ở tiến trình đang chạy**, không chỉ là nội dung `application.yml` trong source.

Có thể bật báo cáo điều kiện auto-configuration khi khởi động bằng `--debug` trong môi trường chẩn đoán phù hợp. Tìm điều kiện khiến registry hoặc Prometheus endpoint không được tạo. Không cần công khai thêm `env`, `beans` hay `conditions` qua HTTP chỉ để thực hiện bước này.

### 5.3. Đường dẫn và cổng quản trị

Đường dẫn mặc định thường gặp là:

```text
http://host:8080/actuator/prometheus
```

Nhưng URL thực tế có thể đổi bởi:

- `server.port`.
- `management.server.port` cho management server riêng.
- `management.endpoints.web.base-path`.
- `management.endpoints.web.path-mapping.prometheus`.
- Context path của Servlet hoặc base path của ứng dụng reactive khi dùng chung server.
- Base path của management server riêng.
- Proxy hoặc ingress thêm/bỏ một tiền tố đường dẫn.

Ví dụ management server riêng:

```yaml
management:
  server:
    port: 9091
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,prometheus
```

Nếu không có base path hoặc path mapping bổ sung, endpoint là `http://host:9091/manage/prometheus`. Khi tách management server, không tự ghép context path của application server vào URL quản trị.

Prometheus tương ứng:

```yaml
scrape_configs:
  - job_name: boot-actuator
    metrics_path: /manage/prometheus
    static_configs:
      - targets: ["app:9091"]
```

Ứng dụng trả `200` ở `/actuator/health` không chứng minh `/actuator/prometheus` tồn tại, được expose hoặc được cấp quyền. Đây là các endpoint có điều kiện và quyền truy cập khác nhau.

### 5.4. Xử lý 401, 403 và redirect đăng nhập

Nếu có Spring Security, đối chiếu security chain áp dụng cho request quản trị:

- Chain nào khớp với URL/cổng này?
- Danh tính scrape có được xác thực không?
- Danh tính đó có quyền đọc endpoint Prometheus không?
- Reverse proxy có giữ header xác thực và đường dẫn không?
- Có redirect sang trang đăng nhập mà Prometheus nhận thành HTML không?

Khi ứng dụng khai báo security chain riêng, không giả định cơ chế bảo vệ Actuator mặc định vẫn quyết định mọi endpoint. Với nhiều chain, thứ tự và matcher đều ảnh hưởng kết quả.

Cấu hình `basic_auth`, `authorization` hoặc TLS/mTLS trong Prometheus phải tương thích với phía nhận. Sử dụng cơ chế secret của môi trường, không đưa thông tin đăng nhập vào URL mẫu hoặc commit vào source.

Một lần scrape thông thường là HTTP GET; tắt CSRF toàn ứng dụng không phải cách sửa mặc định cho lỗi scrape. Không mở toàn bộ Actuator bằng `include: "*"` hoặc bỏ toàn bộ bảo mật chỉ để che một rule cấp quyền sai.

### 5.5. Xử lý HTTP 500

Nếu request đã vào đúng endpoint nhưng trả `500`, xem stack trace cùng thời điểm scrape. Các nhóm nguyên nhân cần kiểm tra:

- Custom collector hoặc hàm đọc gauge ném exception.
- Bộ đo sinh ra dữ liệu/metadata không hợp lệ cho exporter.
- Xung đột dependency hoặc lỗi liên kết class.
- Bộ thu thập thực hiện I/O chậm, giữ khóa hoặc tạo tải quá lớn.

Không khẳng định mọi gauge lỗi đều làm toàn endpoint trả `500`: cách xử lý phụ thuộc loại meter, collector và phiên bản. Phản hồi HTTP và log thực tế mới quyết định hướng xử lý.

## 6. Nhánh ba: endpoint hoạt động nhưng thiếu bộ đo

### 6.1. Phân biệt ba câu hỏi về registry

Cần phân biệt rõ:

1. Meter đã được đăng ký vào **registry nào**?
2. Registry đó có phải Prometheus registry, hoặc có chuyển tiếp tới Prometheus registry không?
3. Endpoint đang xuất từ **registry nào**?

Ví dụ sai thường gặp:

```java
// Mã minh họa chống mẫu: đây là một registry riêng.
MeterRegistry isolated = new SimpleMeterRegistry();
isolated.counter("learning.scrape.check").increment();
```

Counter ở `isolated` không tự xuất hiện ở `/actuator/prometheus` do Spring Boot quản lý. Có meter trong heap không đồng nghĩa meter nằm trong registry mà endpoint đang xuất.

Cách thông thường là inject `MeterRegistry` được Spring quản lý:

```java
@Component
class ScrapeCheckRecorder {
    private final Counter counter;

    ScrapeCheckRecorder(MeterRegistry registry) {
        this.counter = Counter.builder("learning.scrape.check")
                .description("Number of diagnostic events")
                .tag("result", "ok")
                .register(registry);
    }

    void record() {
        counter.increment();
    }
}
```

Đây là một component trong ứng dụng Spring Boot, không phải chương trình chạy độc lập. Các import cần dùng là `io.micrometer.core.instrument.Counter`, `io.micrometer.core.instrument.MeterRegistry` và `org.springframework.stereotype.Component`.

Nếu có nhiều registry, Spring Boot có thể dùng composite registry. Việc inject `MeterRegistry` không có nghĩa đối tượng nhận được chắc chắn là lớp Prometheus cụ thể. Kiểm tra các registry con và cấu hình bean thực tế.

Với `CompositeMeterRegistry`, sự kiện xảy ra trước khi thêm registry con không được phát lại như một hàng đợi lịch sử. Không thể tạo registry Prometheus sau đó rồi kỳ vọng khôi phục mọi lần increment trước đó.

### 6.2. Không trộn Prometheus client mới và cũ

Spring Boot 3.3 chuyển sang thế hệ Prometheus Java client 1.x qua `micrometer-registry-prometheus`. Lớp registry của nhánh này nằm trong package `io.micrometer.prometheusmetrics`.

Nhánh tương thích client cũ dùng artifact `micrometer-registry-prometheus-simpleclient` và package `io.micrometer.prometheus`. Khi xem hướng dẫn cũ, cần chú ý khác biệt này.

Nếu custom collector được đăng ký vào collector registry của client cũ nhưng endpoint đang xuất client mới, collector đó không tự đi qua nhánh mới. Ngược lại cũng vậy.

Dấu hiệu cần điều tra:

- Cả hai họ client cùng xuất hiện trong dependency tree.
- Có `NoClassDefFoundError`, `NoSuchMethodError` hoặc import không khớp với artifact.
- Tạo collector registry riêng bằng mã Java thay vì dùng registry của ứng dụng.
- Custom collector có dữ liệu nhưng không được nối vào registry mà endpoint sử dụng.

Không thêm cả hai artifact để “chắc chắn có đủ”. Chọn hệ client cần dùng, để Spring Boot quản lý phiên bản, rồi nối custom instrumentation vào đúng registry tương ứng.

### 6.3. Tên Micrometer không nhất thiết là tên Prometheus

Micrometer thường dùng tên dạng dấu chấm, còn Prometheus dùng quy tắc tên và hậu tố của exporter.

Ví dụ counter `learning.scrape.check` thường được xuất thành:

```text
learning_scrape_check_total{result="ok"} 1.0
```

Dòng trên minh họa tên và nhãn; cách biểu diễn số hoặc nhãn bổ sung có thể khác. Không dùng việc thiếu đúng chuỗi `learning.scrape.check` trong bản xuất để kết luận counter không tồn tại.

Với timer `http.server.requests`, các series thường có dạng `http_server_requests_seconds_count`, `http_server_requests_seconds_sum` và những series khác tùy cấu hình phân phối. Không phải mọi timer đều có `_bucket`; histogram cần được cấu hình phù hợp. Cũng không mặc định có sẵn mọi percentile theo ý người truy vấn.

Nếu endpoint `metrics` đã được expose và người chẩn đoán có quyền sử dụng, có thể kiểm tra tên Micrometer ở đó. Nếu endpoint ấy chưa expose, không cần bật nó chỉ để hoàn thành chẩn đoán; có thể kiểm tra registry trong mã chẩn đoán nội bộ hoặc log được kiểm soát.

### 6.4. Meter chưa được tạo hoặc chưa được kích hoạt

Một số meter được tạo khi có hoạt động đầu tiên. Hãy tạo đúng sự kiện nghiệp vụ rồi scrape lại:

- Gọi API cần đo, thay vì chỉ gọi `/actuator/health`.
- Thực thi nhánh code thực sự tăng counter.
- Hoàn tất tác vụ cần đo bởi timer.
- Chờ lần thu thập tiếp theo của bộ đo phụ thuộc lịch riêng, nếu có.

Không hứa rằng chỉ gọi endpoint scrape sẽ tạo mọi metric HTTP hoặc business metric. Cũng không dùng metric ngẫu nhiên từ một instance khác làm bằng chứng cho instance đang điều tra.

Đối với bộ đếm, giá trị không đổi không có nghĩa exporter hỏng. Có thể chưa có sự kiện mới, request đang đi tới replica khác, hoặc điều kiện increment không được thực thi.

### 6.5. Filter, tag và xung đột đăng ký

Kiểm tra:

- `MeterFilter` có từ chối tên meter hoặc giới hạn số lượng nhãn không.
- Cấu hình `management.metrics.enable.<prefix>` có tắt nhóm meter cần tìm không.
- Filter có đổi tên hoặc bỏ tag khiến nhiều meter bị gom về cùng định danh không.
- Các lần đăng ký cùng họ metric có bộ tên tag không nhất quán không.
- Một tên đã được đăng ký với loại meter khác chưa.

Ví dụ hai counter cùng tên `orders.processed`, một cái dùng tag `region`, cái còn lại dùng tag `status`, có thể dẫn tới xung đột quy tắc xuất của Prometheus. Thiết kế thống nhất bộ tên tag cho một họ metric và đọc cảnh báo đăng ký của registry.

Định danh meter phụ thuộc tên và tags; không phải cứ tạo đối tượng mới là có một chuỗi thời gian độc lập. Việc đăng ký lặp với định danh trùng có thể trả về meter đã có, khiến người viết mã tưởng callback hoặc đối tượng mới đang được đo.

Tránh dùng `requestId`, `userId` hoặc URL thô chứa ID làm tag. Số lượng chuỗi thời gian tăng mạnh có thể làm tốn bộ nhớ, kéo dài thời gian scrape và chạm giới hạn ingestion. Một tag có giá trị thay đổi liên tục không giúp khắc phục lỗi xuất dữ liệu.

### 6.6. Gauge mất đối tượng hoặc trả giá trị bất thường

Nhiều gauge của Micrometer giữ tham chiếu yếu tới đối tượng được quan sát. Nếu đối tượng chỉ được tạo trong biến cục bộ rồi không còn tham chiếu mạnh, nó có thể bị thu gom rác. Khi đó gauge có thể trả `NaN` hoặc mất khả năng cung cấp giá trị như mong đợi, tùy loại và đường xuất.

Ví dụ sau dễ có vấn đề vòng đời:

```java
// Mã minh họa: AtomicInteger không được giữ bởi một owner sống đủ lâu.
registry.gauge("queue.depth", new AtomicInteger(0));
```

Giữ đối tượng trạng thái trong một bean hoặc đối tượng có vòng đời phù hợp; hàm đo nên nhanh, không chặn và an toàn khi được gọi đồng thời. `NaN` của một gauge không tự chứng minh mạng scrape hỏng.

## 7. Nhánh bốn: HTTP 200 nhưng Prometheus từ chối bản xuất

### 7.1. Status 200 chưa đủ

Một bản scrape thành công còn cần:

- Body thực sự là định dạng mà Prometheus hỗ trợ.
- `Content-Type` phù hợp với định dạng được thương lượng.
- Các mẫu và metadata tuân thủ quy tắc định dạng.
- Không vi phạm giới hạn ingestion của target.
- Không bị proxy cắt ngắn, đổi nội dung hoặc trả trang lỗi dưới status `200`.

Kiểm tra từ đúng tuyến Prometheus đang dùng. Một request đi thẳng vào Pod có thể thành công trong khi request qua ingress nhận body khác.

Bản xuất kiểu Prometheus text thường chứa:

```text
# HELP learning_scrape_check_total Number of diagnostic events
# TYPE learning_scrape_check_total counter
learning_scrape_check_total{result="ok"} 1.0
```

Đây là một mẫu minh họa, không phải toàn bộ bản xuất của Spring Boot.

Với OpenMetrics, format và các yêu cầu như dấu kết thúc `# EOF` phải phù hợp. Không sửa tay body của endpoint hoặc ép proxy thay Content-Type để che một bản xuất không đúng định dạng.

Có thể đối chiếu phản hồi khi yêu cầu rõ Prometheus text:

```bash
curl -i --max-time 10 -H "Accept: text/plain;version=0.0.4" http://localhost:8080/actuator/prometheus
```

Nếu dùng `promtool check metrics`, hãy chạy trên bản Prometheus text tương thích với công cụ đang có. Ví dụ Bash sau lưu header và body riêng:

```bash
curl --fail --silent --show-error --max-time 10 \
  -H "Accept: text/plain;version=0.0.4" \
  -D scrape.headers -o scrape.txt \
  http://localhost:8080/actuator/prometheus
promtool check metrics < scrape.txt
```

Trước khi chạy lệnh thứ hai, xác nhận lệnh curl thành công và header đúng. Một lỗi lint của `promtool` và lỗi parse làm target DOWN không hoàn toàn đồng nghĩa; đối chiếu thông báo cụ thể. Bản xuất vượt qua kiểm tra định dạng cũng chưa chứng minh đã vượt qua giới hạn ingestion hoặc đã được lưu.

### 7.2. Sample limit, nhãn và relabel

Kiểm tra cấu hình và lỗi của Prometheus:

- `sample_limit` có bị vượt không.
- Các giới hạn về số lượng/độ dài nhãn có bị vượt không.
- Có mẫu trùng tổ hợp tên và nhãn gây lỗi không.
- Có timestamp không hợp lệ, quá cũ hoặc đi ngược thứ tự không.
- `metric_relabel_configs` có drop metric đang tìm không.

Cần phân biệt:

| Cấu hình | Thời điểm tác động | Hệ quả có thể quan sát |
| --- | --- | --- |
| `relabel_configs` | Trước scrape, trên target và nhãn discovery | Target bị đổi địa chỉ/nhãn hoặc bị loại bỏ |
| `metric_relabel_configs` | Sau đọc mẫu, trước lưu | HTTP scrape có dữ liệu nhưng metric cụ thể không được lưu |

Khi vượt một giới hạn, ảnh hưởng có thể là toàn lần scrape bị đánh dấu lỗi chứ không chỉ bỏ một metric. Đọc `Last error` và log thay vì suy luận từ status `200` của ứng dụng.

Nếu custom collector tự gắn timestamp, kiểm tra nguồn timestamp đó. Metrics thông thường thường để Prometheus gán thời điểm scrape; không tự thêm timestamp như cách sửa mặc định.

## 8. Nhánh năm: dữ liệu đã được lưu nhưng truy vấn không thấy

Bắt đầu bằng truy vấn đơn giản, đúng tên metric và đúng target. Ví dụ thay `instance` bằng nhãn thực tế từ Targets:

```promql
up{job="boot-actuator", instance="app:8080"}
```

- `1`: lần scrape gần nhất của chuỗi target đó thành công; không bảo đảm mọi business metric đều tồn tại.
- `0`: target có lần scrape lỗi gần nhất.
- Không có chuỗi: có thể selector sai, target không được phát hiện, hoặc chuỗi không hiện diện trong khoảng đánh giá. “Không có” khác “bằng 0”.

Tiếp theo, tìm counter mà chưa thêm phép tính tốc độ:

```promql
learning_scrape_check_total{job="boot-actuator"}
```

Sau đó mới giới hạn `instance` và các tag khác. Nếu có nhiều replica, request thử nghiệm và target được truy vấn phải cùng instance, hoặc truy vấn cần tổng hợp đúng nhiều instance.

Các lỗi truy vấn thường gặp:

- Dùng tên Micrometer có dấu chấm thay cho tên trong bản xuất Prometheus.
- Dùng tag mà exporter không tạo, hoặc giá trị tag không khớp.
- Cửa sổ thời gian không bao phủ lúc dữ liệu xuất hiện.
- Dùng `rate()` khi chưa có ít nhất hai mẫu phù hợp.
- Dùng cửa sổ `rate()` quá ngắn so với scrape interval.
- Mong counter tiếp tục tăng sau khi tiến trình đã restart; counter của tiến trình có thể reset.
- Lấy `_sum` nhưng quên đơn vị của timer, hoặc dùng `_bucket` khi histogram chưa được bật.
- Xem biểu đồ cũ có selector cố định cho instance đã thay địa chỉ.

Ví dụ tốc độ sự kiện:

```promql
rate(learning_scrape_check_total{job="boot-actuator"}[5m])
```

Cửa sổ `5m` chỉ là ví dụ. Chọn cửa sổ chứa đủ nhiều lần scrape theo cấu hình thực tế. `rate()` có xử lý counter reset, nhưng không thể tạo dữ liệu chưa từng được scrape.

Có thể quan sát thêm `scrape_duration_seconds`, `scrape_samples_scraped` và `scrape_samples_post_metric_relabeling` của target. Các chỉ số này giúp đối chiếu số mẫu đã đọc, số mẫu sau relabel và thời gian scrape; chúng không thay thế việc tìm metric cụ thể.

## 9. Bài thực hành: tạo một tín hiệu chẩn đoán có kiểm soát

Mục tiêu là tách instrumentation khỏi mạng và truy vấn. Dùng một ứng dụng thử nghiệm với `spring-boot-starter-web`, `spring-boot-starter-actuator` và `micrometer-registry-prometheus` như phần dependency ở trên.

Tệp `src/main/java/demo/ScrapeDemoApplication.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ScrapeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScrapeDemoApplication.class, args);
    }
}

@RestController
class DiagnosticController {
    private final Counter checks;

    DiagnosticController(MeterRegistry registry) {
        checks = Counter.builder("learning.scrape.check")
                .description("Number of diagnostic events")
                .tag("result", "ok")
                .register(registry);
    }

    @GetMapping("/demo")
    String record() {
        checks.increment();
        return "recorded";
    }
}
```

Tệp `src/main/resources/application.yml` trong môi trường thử nghiệm:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Chương trình này chạy bên trong dự án Spring Boot, không chạy trực tiếp bằng `javac` vì cần dependency và runtime Spring. Với dự án đã có Gradle wrapper và plugin Boot:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Trong bài thực hành tối giản không thêm Spring Security, không đổi cổng và không gắn proxy; ứng dụng mặc định nhận HTTP trên cổng `8080`.

Từ một terminal khác, gọi đúng một lần trên một tiến trình vừa khởi động:

```bash
curl --fail --silent --show-error http://localhost:8080/demo
```

Body trả về chính xác là:

```text
recorded
```

Lệnh trên không yêu cầu server thêm ký tự xuống dòng; dấu nhắc terminal có thể xuất hiện ngay sau body. Sau đó đọc bản xuất:

```bash
curl --fail --silent --show-error http://localhost:8080/actuator/prometheus
```

Tìm series mang tên `learning_scrape_check_total` và tag `result="ok"`. Nếu đây là lần duy nhất gọi `/demo`, giá trị số của counter là `1`; hình thức biểu diễn số có thể là `1.0` hoặc dạng tương đương tùy exporter. Các lần scrape không làm counter này tăng, vì chỉ handler `/demo` gọi `increment()`.

Sau khi Prometheus đã có đủ lần scrape, kiểm tra lần lượt:

```promql
up{job="boot-actuator"}
learning_scrape_check_total{job="boot-actuator", result="ok"}
```

Nếu chạy thử nhiều instance hoặc có công cụ tự gọi `/demo`, không còn điều kiện “chỉ một lần gọi”; hãy dùng đúng instance và ghi lại số request thực tế.

### Bốn thí nghiệm lỗi để xác định đúng lớp

Chỉ thực hiện trong môi trường thử nghiệm và mỗi lần thay đúng một yếu tố:

| Thay đổi | Hiện tượng cần kiểm chứng | Kết luận |
| --- | --- | --- |
| Bỏ `prometheus` khỏi exposure | Endpoint không còn được công bố qua HTTP | Lỗi công bố endpoint, chưa chứng minh registry mất |
| Đổi target sang cổng không có listener | Prometheus báo lỗi kết nối | Lỗi địa chỉ/kết nối, không phải counter |
| Ghi counter vào `new SimpleMeterRegistry()` riêng | Counter đó không đi vào bản xuất Boot | Sai registry đích |
| Dùng selector có `result="failed"` | Truy vấn không có series dù body chứa `result="ok"` | Sai điều kiện truy vấn |

HTTP status cụ thể khi bỏ exposure còn phụ thuộc security/proxy; đừng coi mọi môi trường đều bắt buộc trả cùng một mã.

Sau mỗi thí nghiệm, khôi phục thay đổi, khởi động lại nếu cấu hình yêu cầu và kiểm chứng bằng HTTP cùng Targets. Không giữ nhiều lỗi cùng lúc vì sẽ khó biết sửa đổi nào tạo ra kết quả.

## 10. Khi scrape chậm hoặc lỗi không ổn định

Một endpoint đôi khi thành công, đôi khi timeout cần được điều tra như một vấn đề hiệu năng, không chỉ một lỗi URL:

1. Đo thời gian phản hồi và kích thước body ở cùng thời điểm Prometheus báo lỗi.
2. So sánh `scrape_duration_seconds` với `scrape_timeout`.
3. Kiểm tra CPU, GC, số chuỗi thời gian và số lượng meter.
4. Tìm gauge/custom collector gọi database, dịch vụ từ xa hoặc duyệt cấu trúc dữ liệu lớn trong lúc scrape.
5. Kiểm tra lock và thread bị chặn; đối chiếu thread dump khi cần.
6. Kiểm tra proxy timeout, giới hạn response và sự khác biệt giữa các replica.

Hàm đọc gauge nên lấy trạng thái đã có sẵn một cách nhanh chóng. Một gauge gọi API ngoài ở mỗi lần scrape có thể biến hệ thống giám sát thành tác nhân tạo tải hoặc gây nghẽn.

Chỉ tăng timeout sau khi đã biết thời gian thực thi bình thường và giới hạn của pipeline. Timeout scrape không được lớn hơn scrape interval trong cấu hình Prometheus hợp lệ. Tăng cả hai mà không giảm nguyên nhân chậm có thể chỉ làm phát hiện sự cố muộn hơn.

Nếu dữ liệu quá lớn, ưu tiên giảm tag có độ đa dạng cao, số histogram bucket không cần thiết và meter đăng ký động không được quản lý vòng đời. Đừng bỏ ngẫu nhiên metric trước khi xác định nhu cầu giám sát.

## 11. Checklist kết thúc chẩn đoán

Chỉ coi sự cố đã được xử lý khi có bằng chứng ở đủ lớp liên quan:

- Target được discovery đúng và URL cuối cùng trỏ đúng instance.
- Kết nối từ môi trường Prometheus thành công với TLS/xác thực phù hợp.
- Endpoint trả HTTP và định dạng metric hợp lệ.
- Bộ đo cần tìm nằm trong đúng registry và xuất hiện trong body sau khi kích hoạt đúng sự kiện.
- Prometheus scrape thành công và không có lỗi ingestion đang liên quan.
- Metric có mặt với đúng tên, nhãn, đơn vị và khoảng thời gian.
- Cách sửa vẫn giữ đúng phạm vi expose và quyền đọc quản trị.
- Nếu lỗi chỉ xuất hiện dưới tải hoặc sau restart, đã kiểm tra lại đúng điều kiện đó.

Điểm mấu chốt là tách ba bằng chứng: **ứng dụng đã đo**, **endpoint đã xuất**, và **Prometheus đã lưu được dữ liệu cần truy vấn**. Mỗi bằng chứng chỉ xác nhận một đoạn của đường đi; nối chúng theo đúng instance và thời điểm mới xác định được nguyên nhân.
