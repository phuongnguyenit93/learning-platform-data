# Kiểm soát lỗi kết nối, mất dữ liệu và chi phí khi hệ thống giám sát gián đoạn

## 1. Hiểu đúng sự cố: ứng dụng vẫn chạy nhưng ta có thể mất khả năng quan sát

Trong Spring Boot Actuator, ghi nhận một phép đo vào Micrometer và đưa phép đo đó đến nơi lưu trữ là hai việc khác nhau. Một yêu cầu nghiệp vụ có thể xử lý thành công, bộ đếm trong JVM vẫn tăng, nhưng biểu đồ trung tâm lại trống vì đường truyền thu thập metrics bị hỏng.

Ví dụ: dịch vụ bán hàng vẫn nhận đơn lúc 10:00–10:05, trong khi Prometheus không truy cập được endpoint metrics. Không thể kết luận doanh số bằng 0 chỉ vì biểu đồ không có điểm đo. Cũng không thể hứa rằng sau 10:05 mọi chi tiết của năm phút đó sẽ tự xuất hiện trở lại.

Bài này tập trung vào ba câu hỏi:

- Lỗi nằm ở đoạn nào của đường đi metrics, và có ảnh hưởng đến xử lý nghiệp vụ không?
- Phép đo nào còn có thể suy ra sau khi kết nối phục hồi, phép đo nào đã mất?
- Giới hạn nào giúp việc chờ, thử lại và gửi bù không làm cạn tài nguyên hoặc tăng chi phí ngoài dự kiến?

**Metrics là dữ liệu quan sát đã được tổng hợp hoặc lấy mẫu.** Nếu cần đối soát từng giao dịch, phải dựa vào dữ liệu nghiệp vụ được lưu bền vững hoặc cơ chế nhật ký sự kiện phù hợp. Không dùng bộ đếm trong bộ nhớ làm sổ cái thanh toán.

### Những thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| Registry | Nơi Micrometer quản lý các meter và số liệu đang được ghi nhận trong ứng dụng |
| Scrape | Hệ thống giám sát chủ động đọc endpoint metrics của từng ứng dụng |
| Exporter | Thành phần chuyển/gửi metrics sang hệ thống nhận |
| Backend | Hệ thống nhận, lưu và phục vụ truy vấn metrics |
| Khoảng chờ tối đa (timeout) | Giới hạn chờ cho một thao tác; không đồng nghĩa với giới hạn thời gian của toàn bộ quá trình thử lại |
| Thử lại (retry) | Gửi lại sau một lỗi có khả năng tạm thời |
| Hàng đợi có giới hạn | Bộ đệm có dung lượng tối đa và quy tắc rõ ràng khi đầy |
| WAL | Nhật ký ghi trước trên đĩa; khả năng phục hồi còn phụ thuộc dung lượng, thời hạn và cơ chế của thành phần sở hữu nó |
| Độ mới dữ liệu | Thời gian từ phép đo mới nhất đã nhận được đến thời điểm hiện tại |
| Cardinality | Số tổ hợp tên metric và giá trị nhãn tạo thành các chuỗi thời gian riêng biệt |

## 2. Vẽ đường đi trước khi sửa cấu hình

Có hai mô hình thường gặp trong phạm vi Actuator.

### 2.1. Pull: Prometheus đọc từ ứng dụng

```text
Nghiệp vụ → Micrometer trong JVM
                       ↑
                HTTP scrape
                       |
              Prometheus cục bộ → remote_write → Backend từ xa
                       |
                    Truy vấn → Dashboard
```

Spring Boot cung cấp endpoint `/actuator/prometheus` khi có registry Prometheus phù hợp và endpoint được expose. Endpoint `/actuator/metrics` phục vụ kiểm tra chẩn đoán; không thay thế định dạng scrape Prometheus. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Ba sự cố trong sơ đồ có hậu quả khác nhau:

1. **Prometheus không đọc được ứng dụng:** thiếu mẫu ngay ở đầu thu thập.
2. **Prometheus vẫn scrape được nhưng backend từ xa hỏng:** có thể còn dữ liệu ở Prometheus cục bộ; khả năng chuyển tiếp phụ thuộc remote write.
3. **Dashboard hoặc tầng truy vấn hỏng:** dữ liệu có thể vẫn được thu thập đầy đủ; cần kiểm tra nơi lưu trước khi kết luận mất dữ liệu.

Trong mô hình pull thông thường, ứng dụng không tự gửi một HTTP request đến Prometheus sau mỗi nghiệp vụ. Việc Prometheus ngừng hoạt động không có nghĩa các luồng xử lý nghiệp vụ đang chờ một lời gọi đến Prometheus. Tuy vậy, đăng ký quá nhiều meter hoặc tính gauge bằng một phép toán nặng vẫn có thể gây tốn tài nguyên tại ứng dụng.

### 2.2. Push: registry gửi theo chu kỳ

```text
Nghiệp vụ → Micrometer → Bộ xuất theo chu kỳ → Collector/Backend
                                                  |
                                  Bộ đệm và retry nếu được cấu hình
```

Trong mô hình này, phải kiểm tra chính registry đang dùng: kiểu tổng hợp, giao thức, giới hạn chờ, cơ chế gửi và hành vi khi lỗi. Không suy ra tính năng retry hay lưu bền vững của registry này từ registry khác.

Nếu ứng dụng gửi đến một OpenTelemetry Collector gần nó, Collector có thể làm nhiệm vụ chuyển tiếp đến backend. Nhưng các bảo đảm ở Collector chỉ có tác dụng với dữ liệu đã đến Collector; không phục hồi được dữ liệu chưa rời JVM.

**Quyền sở hữu cấu hình phải đi cùng thành phần:** thời gian scrape thuộc Prometheus; thời gian xuất của registry thuộc Spring Boot/Micrometer; hàng đợi chuyển tiếp thuộc Collector hoặc Prometheus. Không đặt một khóa `queue-size` tự nghĩ ra trong `application.yml` rồi cho rằng ứng dụng đã có bộ đệm bền vững.

## 3. Mất điểm đo, mất tổng số và mất dữ liệu nghiệp vụ là ba mức khác nhau

### 3.1. Bộ đếm tích lũy có thể giữ tổng mức tăng, nhưng mất phân bố theo thời gian

Giả sử cùng một tiến trình JVM, cùng một chuỗi thời gian và không có lần đặt lại bộ đếm:

| Thời điểm | Counter trong JVM | Kết quả scrape |
| --- | ---: | --- |
| 10:00 | 100 | Nhận 100 |
| 10:01 | 120 | Thất bại |
| 10:02 | 155 | Thất bại |
| 10:03 | 190 | Thất bại |
| 10:04 | 230 | Nhận 230 |

Hai giá trị đọc được cho biết bộ đếm đã tăng **130** giữa hai lần quan sát. Chúng không cho biết chính xác trong từng phút đã tăng bao nhiêu. Không thể vẽ lại các điểm 120, 155, 190 chỉ từ 100 và 230.

Với hệ thống dùng số tích lũy để tính tốc độ ở phía máy chủ, chênh lệch giữa các lần đọc có thể giữ lại thông tin tổng quát qua một khoảng gián đoạn. Với hệ thống tổng hợp theo từng chu kỳ ở phía ứng dụng, số liệu được chuyển giữa khoảng hiện tại và khoảng trước; đó không phải kho lưu mọi khoảng quá khứ để gửi lại vô hạn. Xem [Micrometer — Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

Điều kiện “cùng tiến trình, cùng chuỗi” rất quan trọng. Nếu ứng dụng khởi động lại trong lúc mất kết nối, phần tăng chưa được quan sát trước lần khởi động lại có thể mất. Một lần triển khai thay đổi nhãn cũng có thể tạo chuỗi khác; không được tự lấy hai giá trị thuộc hai chuỗi khác nhau để trừ.

Prometheus có các hàm `rate()` và `increase()` xử lý những lần reset nhìn thấy được trong mẫu và có phép ngoại suy theo cửa sổ truy vấn. `increase()` có thể trả số không nguyên. Các hàm này không khôi phục một đoạn hoạt động hoàn toàn không được quan sát; cửa sổ thiếu đủ mẫu cũng không cho một tốc độ đáng tin. Xem [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

### 3.2. Gauge không giữ lịch sử giá trị trung gian

Giả sử số yêu cầu đang xử lý lần lượt là 4, 80, 6 trong một phút. Nếu chỉ lấy mẫu lúc đầu và cuối phút thì thấy 4 và 6; đỉnh 80 có thể biến mất khỏi dữ liệu thu được.

Gauge biểu diễn giá trị tại lúc quan sát. Ghi nhận giá trị liên tục trong ứng dụng không đồng nghĩa mọi giá trị trung gian đều được gửi và lưu. Xem [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Hệ quả khi vận hành:

- Gauge bộ nhớ thấp sau phục hồi không chứng minh trong thời gian mất giám sát chưa từng có đỉnh bộ nhớ.
- Cần quan sát đỉnh theo cửa sổ thì phải chọn loại thống kê và cấu hình phù hợp; tăng retry không biến gauge thành lịch sử.
- Với sự kiện cần đếm, hãy chọn counter hoặc count của timer thay vì dùng gauge để mô phỏng số sự kiện.

### 3.3. Timer và histogram phụ thuộc dữ liệu nào đã được giữ

Một timer có thể có count, tổng thời gian, cực đại hoặc phân bố theo cấu hình và registry. Không được coi tất cả các phần đó có cùng tuổi thọ và cùng khả năng phục hồi.

Ví dụ, nếu count và tổng thời gian tích lũy của cùng tiến trình còn đọc được ở hai đầu khoảng gián đoạn, có thể suy ra trung bình chung của các phép đo trong khoảng bằng chênh lệch tổng thời gian chia chênh lệch count. Điều đó vẫn không cho biết độ trễ của từng phút hoặc từng yêu cầu. Cực đại theo cửa sổ và phân vị đã tổng hợp có thể không còn đại diện cho phần thời gian bị bỏ lỡ.

Khi phân tích sự cố, hãy ghi rõ thứ còn thiếu là **mẫu theo thời gian**, **thống kê của một chu kỳ**, hay **toàn bộ phần tích lũy trước khi JVM chết**. Cụm từ “mất metrics” riêng lẻ chưa đủ để chọn giải pháp.

## 4. Phân loại lỗi kết nối để xử lý đúng

| Dấu hiệu | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không phân giải được tên | DNS, sai tên dịch vụ, cấu hình resolver | Kiểm tra từ môi trường của thành phần gửi/scrape |
| Connection refused | Không có tiến trình lắng nghe hoặc sai cổng | Kiểm tra địa chỉ bind, cổng và tiến trình nhận |
| Connect timeout | Đường mạng, tường lửa, quá tải kết nối | Xác định đường truyền và giới hạn chờ kết nối |
| Read timeout | Đã kết nối nhưng phía nhận chậm hoặc xử lý bị nghẽn | Kiểm tra tải, kích thước lô và thời gian phản hồi |
| TLS handshake/certificate error | Sai hostname, chuỗi tin cậy, chứng chỉ hết hạn | Sửa cấu hình TLS; không dùng tắt xác minh làm cách khắc phục lâu dài |
| HTTP 401/403 | Sai thông tin xác thực hoặc thiếu quyền | Sửa quyền/cấu hình; retry liên tục không chữa được |
| HTTP 404 | Sai đường dẫn, endpoint chưa expose, định tuyến sai | Kiểm tra endpoint thật và cấu hình đường dẫn |
| HTTP 413 | Lô dữ liệu vượt giới hạn phía nhận | Giảm kích thước lô hoặc sửa giới hạn phù hợp |
| HTTP 429 | Bị hạn chế lưu lượng hoặc vượt hạn mức | Giảm tốc độ và tuân theo chính sách retry của giao thức/backend |
| HTTP 5xx | Dịch vụ nhận/proxy gặp lỗi | Retry có giới hạn nếu lỗi được xác định là tạm thời |
| HTTP 2xx nhưng thiếu dữ liệu | Sai nhãn truy vấn, sai khoảng thời gian hoặc phía nhận chỉ chấp nhận một phần | Đối chiếu nội dung phản hồi và số điểm thực nhận |

Bảng là cách chẩn đoán, không phải cam kết rằng mọi exporter tự retry mọi lỗi trong bảng. Giao thức có thể quy định khác nhau về lỗi được thử lại và phản hồi chấp nhận một phần.

Hai thao tác cần làm trước khi thay tham số:

1. Kiểm tra kết nối từ **chính nơi phát sinh yêu cầu mạng**. Laptop truy cập được endpoint không chứng minh container Prometheus truy cập được.
2. Đối chiếu đồng hồ và múi giờ khi so thời điểm lỗi, phép đo và truy vấn. Dữ liệu đến chậm hoặc sai thời gian có thể bị hiểu nhầm là mất.

## 5. Giữ sự cố xuất metrics trong giới hạn tài nguyên

### 5.1. Tách việc quan sát khỏi đường xử lý nghiệp vụ

Trong xử lý đơn hàng, nên ghi nhận counter/timer qua registry đã được cấu hình. Không tự chèn một HTTP call đồng bộ đến backend metrics sau mỗi đơn hàng rồi đợi vô hạn.

Mục tiêu thiết kế là khi backend metrics hỏng:

- Lỗi nghiệp vụ vẫn phản ánh đúng kết quả nghiệp vụ.
- Không tạo thêm vô hạn luồng gửi, tác vụ retry hoặc đối tượng trong bộ nhớ.
- Giao diện giám sát thể hiện dữ liệu thiếu/chậm rõ ràng.
- Có cơ chế nhìn thấy lỗi xuất dữ liệu mà không tạo vòng lặp log vô hạn.

Một exporter chạy nền vẫn dùng CPU, RAM, kết nối và đĩa. Vì thế “chạy nền” không có nghĩa “không ảnh hưởng”. Cần thử khi backend thật sự không sẵn sàng, thay vì chỉ thử đường truyền thành công.

Thông thường, không đưa backend giám sát thành điều kiện bắt buộc của readiness/liveness cho dịch vụ nghiệp vụ. Nếu mọi instance bị loại khỏi cân bằng tải chỉ vì cùng một backend metrics hỏng, sự cố quan sát sẽ lan thành sự cố phục vụ. Trường hợp nghiệp vụ có yêu cầu kiểm soát đặc biệt phải có quyết định riêng và bằng chứng phù hợp; không suy ra yêu cầu ấy từ việc dùng Actuator.

### 5.2. Timeout là nhiều ngân sách khác nhau

Cần phân biệt:

- Thời gian chờ thiết lập kết nối.
- Thời gian chờ phản hồi/đọc dữ liệu.
- Hạn chót cho một lần gửi, nếu thư viện hỗ trợ.
- Tổng thời gian một lô được giữ và thử lại.
- Thời gian chờ đóng ứng dụng.

Không giả định `connect-timeout + read-timeout` bao trùm chính xác mọi giai đoạn như DNS, TLS, ghi request và các lần retry. Phải đọc hợp đồng của HTTP client/exporter cụ thể.

Nếu chu kỳ xuất là 30 giây nhưng một lần gửi có thể kéo dài gần 2 phút, phải kiểm tra hành vi thực tế khi lần gửi chưa kết thúc: bị chậm lịch, bỏ chu kỳ hay có tác vụ chồng lấn? Không tự giải quyết bằng cách tăng số luồng vô hạn.

### 5.3. Retry cần có giới hạn, giãn cách và chênh lệch ngẫu nhiên

Chính sách thiết kế thường gồm:

1. Chỉ retry lỗi có khả năng tạm thời.
2. Tăng khoảng chờ dần, có trần.
3. Thêm độ lệch ngẫu nhiên (jitter) để nhiều instance không gửi lại cùng thời điểm.
4. Giới hạn số lần hoặc tổng thời gian retry.
5. Giới hạn số lô đang xử lý và dung lượng đệm.
6. Đếm/ghi nhận số dữ liệu bị loại khi hết ngân sách.

Đây là yêu cầu đánh giá thành phần gửi, không phải tập property chung mà Micrometer nào cũng hỗ trợ. Nếu exporter hiện có không có chính sách cần thiết, cân nhắc chuyển việc chuyển tiếp sang thành phần chuyên trách thay vì bọc thêm một vòng retry không kiểm soát.

Sau lỗi timeout, có thể phía nhận đã ghi dữ liệu nhưng phản hồi chưa về. Gửi lại khi đó có nguy cơ trùng. Cách xử lý phụ thuộc định danh chuỗi, timestamp, kiểu dữ liệu và giao thức; không tuyên bố “exactly once” chỉ vì đã bật retry.

### 5.4. Hàng đợi đầy cần một quyết định rõ ràng

| Lựa chọn | Đánh đổi |
| --- | --- |
| Loại dữ liệu mới | Bảo vệ bộ nhớ nhưng mất thông tin mới nhất |
| Loại dữ liệu cũ | Ưu tiên độ mới nhưng mất lịch sử chờ gửi |
| Chặn phía gửi | Giảm tốc độ vào; nguy hiểm nếu chặn lan đến luồng nghiệp vụ |
| Ghi ra đĩa | Có cơ hội phục hồi qua restart nhưng cần ngân sách đĩa và cơ chế đọc lại |
| Giảm số liệu thu thập có chủ đích | Giảm tải nhưng giảm chi tiết; phải ghi nhận thay đổi chính sách |

Không phải mọi sản phẩm đều cho chọn tất cả phương án. Phải xác định hành vi đang có, phần nào bị loại và số bị loại có quan sát được hay không.

## 6. Cấu hình minh họa cho Spring Boot 3.3

Các đoạn dưới đây là ví dụ học tập cho một ứng dụng riêng có Spring Boot 3.3; không phải yêu cầu thay đổi build của repository. Phiên bản Micrometer đi theo dependency management của Spring Boot. Khi dùng phiên bản khác, đối chiếu tài liệu tương ứng trước khi sao chép property.

### 6.1. Phương án pull: giới hạn thời gian scrape ở Prometheus

Ứng dụng cần Actuator và registry Prometheus. Ví dụ phần dependencies trong Gradle khi dự án đã có Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Cấu hình ứng dụng cho phòng thực hành trên cùng máy:

```yaml
spring:
  application:
    name: orders-demo

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: orders-demo
```

Đoạn này giả định các đường dẫn Actuator mặc định, ứng dụng có HTTP server và không có cấu hình bảo mật bổ sung chặn yêu cầu thực hành. Bind loopback chỉ cho phép truy cập cục bộ. Nếu Prometheus chạy trong container/máy khác, phải cấu hình địa chỉ và quyền truy cập phù hợp; `127.0.0.1` bên trong container không trỏ đến máy host.

File `prometheus.yml` cho Prometheus chạy trực tiếp trên cùng máy:

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 3s

scrape_configs:
  - job_name: orders-demo
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - 127.0.0.1:9091
```

Ở đây, `scrape_timeout` giới hạn một lần thu thập; phải không lớn hơn khoảng scrape áp dụng. Nó không thiết lập timeout cho các yêu cầu HTTP nghiệp vụ đến ứng dụng. Chọn 3 giây và 15 giây là quyết định minh họa, cần điều chỉnh theo độ trễ đo được và nhu cầu phát hiện sự cố. Cú pháp cấu hình tham khảo [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Khi đường mạng tới endpoint hỏng, Prometheus có thể ghi nhận lần scrape thất bại; ứng dụng vẫn có thể tiếp tục ghi số liệu vào registry. Tuy nhiên, các mẫu không được scrape sẽ không tự được xếp hàng ở endpoint để gửi bù.

### 6.2. Phương án push: đặt ngân sách cho OTLP metrics

Nếu chọn Micrometer OTLP thay cho registry Prometheus trong ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
```

Một cấu hình Spring Boot 3.3 minh họa:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://127.0.0.1:4318/v1/metrics
        connect-timeout: 1s
        read-timeout: 3s
        step: 30s
        batch-size: 1000
```

- Địa chỉ trên dành cho Collector hỗ trợ OTLP HTTP metrics ở cùng máy.
- `step` là chu kỳ xuất; nó không phải thời gian được lưu bù.
- `batch-size` giới hạn số measurement trong một request; không phải dung lượng hàng đợi, số byte tối đa hay giới hạn tổng số meter trong JVM.
- Timeout giúp giới hạn chờ cho thao tác mạng tương ứng; cấu hình này không thêm một WAL.
- Không nhầm `management.otlp.metrics.export.*` với cấu hình OTLP tracing.

Tên và ý nghĩa property được đối chiếu với [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html). Các giá trị 1 giây, 3 giây, 30 giây và 1000 là giá trị được chọn cho ví dụ, không phải lời khuyên mặc định cho mọi môi trường.

Một ứng dụng có nhiều registry trên classpath có thể xuất đến nhiều đích. Chỉ giữ/bật các registry cần thiết để tránh chi phí và lưu lượng gửi trùng ngoài dự kiến. Nếu tạm tắt OTLP, property của ví dụ là `management.otlp.metrics.export.enabled=false`; thay file cấu hình thông thường cần áp dụng lại cấu hình/khởi động lại theo cơ chế triển khai, không tự có hiệu lực động.

## 7. Bộ đệm bền vững giúp gì và không giúp gì?

Có thể thiết kế đường truyền theo hai hướng:

```text
Ứng dụng → Prometheus gần ứng dụng → remote_write → Backend xa

Ứng dụng → Collector gần ứng dụng → hàng đợi chuyển tiếp → Backend xa
```

### 7.1. Với Prometheus remote write

Remote write đọc dữ liệu từ WAL và gửi qua các hàng đợi theo đích nhận. Việc tăng dung lượng hàng đợi hoặc số luồng gửi có thể làm tăng RAM/CPU/mạng. Cần xem mẫu đang chờ, tốc độ vào, tốc độ gửi và giới hạn lưu giữ.

Tài liệu vận hành Prometheus mô tả nguy cơ mất phần chưa gửi khi backend gián đoạn vượt cửa sổ WAL, với mốc hơn hai giờ trong cơ chế được tài liệu đó mô tả. Không dùng mốc này như một cam kết lưu bền vững phổ quát cho mọi phiên bản, chế độ và cấu hình. Đặc biệt, thời gian lưu của cơ sở dữ liệu cục bộ không tự trở thành thời hạn retry của remote write. Xem [Prometheus — Remote write tuning](https://prometheus.io/docs/practices/remote_write/).

WAL ở Prometheus chỉ bảo vệ phần đã được Prometheus thu nhận. Nếu Prometheus không scrape được ứng dụng suốt năm phút, không có mẫu tương ứng trong WAL để gửi bù.

### 7.2. Với OpenTelemetry Collector

Collector có thể dùng hàng đợi gửi, retry với thời gian chờ tăng dần và jitter. Thành phần phù hợp có thể gắn hàng đợi với `file_storage` để giữ dữ liệu qua lần khởi động lại. Nhưng vẫn có thể mất dữ liệu khi đầy hàng đợi, quá thời hạn retry, đầy/hỏng đĩa hoặc mất nơi lưu. Xem [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/).

Khi chọn cách này, cần xác minh:

- Bản phân phối Collector có exporter và extension lưu trữ đang cần.
- Extension thực sự được khai báo, kích hoạt và gắn vào hàng đợi của exporter.
- Thư mục lưu được gắn volume bền vững và có quyền ghi phù hợp.
- Giới hạn hàng đợi đang tính bằng request, batch, item hay byte theo phiên bản/cấu hình cụ thể.
- Quy tắc retry và loại lỗi không retry được hiểu đúng.
- Cơ chế dọn dữ liệu, giới hạn đĩa và phục hồi đã được thử.

Không chỉ nhìn một khóa cấu hình chứa chữ “storage” rồi kết luận mọi dữ liệu đã an toàn. Khả năng phục hồi phải được chứng minh bằng thử nghiệm restart khi có dữ liệu đang chờ.

## 8. Tính dung lượng chịu gián đoạn và tốc độ phục hồi

Các công thức dưới đây là mô hình lập kế hoạch đơn giản do ta xây dựng, không thay thế phép đo tài nguyên thực tế.

Gọi:

- `λ`: tốc độ dữ liệu đi vào bộ đệm, tính bằng điểm đo/giây.
- `T`: thời gian dự kiến phía nhận ngừng hoạt động, tính bằng giây.
- `Q`: dung lượng đệm còn dùng được, quy đổi sang điểm đo.
- `μ`: tốc độ gửi thành công sau phục hồi, tính bằng điểm đo/giây.

Khi phía nhận hoàn toàn ngừng nhận và tốc độ vào ổn định:

```text
Dung lượng cần cho khoảng gián đoạn ≈ λ × T
Thời gian đệm còn chịu được         ≈ Q / λ
```

Ví dụ: hệ thống đưa vào 400 điểm/giây, cần chịu gián đoạn 10 phút:

```text
400 × 600 = 240.000 điểm
```

Nếu đo thực tế thấy bình quân 200 byte cho mỗi điểm trong kiểu lưu đang dùng, riêng phần dữ liệu ước tính là:

```text
240.000 × 200 = 48.000.000 byte ≈ 45,8 MiB
```

200 byte là **giả định minh họa**, không phải kích thước cố định của Prometheus hay OTLP. Bộ nhớ/đĩa thực tế còn có nhãn, chỉ mục, đối tượng, hàng đợi, metadata và chi phí định dạng. Cần dự phòng cho biến động lưu lượng và đo bằng thử tải.

Sau phục hồi, dữ liệu mới vẫn tiếp tục đến. Nếu backlog là 240.000 điểm và gửi thành công 1000 điểm/giây:

```text
Tốc độ giảm backlog = μ − λ = 1000 − 400 = 600 điểm/giây
Thời gian bắt kịp    ≈ 240.000 / 600 = 400 giây
```

Nếu `μ ≤ λ`, hệ thống không thể bắt kịp chỉ bằng chờ đợi. Phải tăng năng lực phía nhận, giảm lượng dữ liệu vào hoặc chấp nhận loại một phần theo chính sách. Tăng hàng đợi chỉ trì hoãn lúc đầy.

Thời gian chịu gián đoạn thực tế còn bị chặn bởi thời hạn retry/tuổi dữ liệu và nơi lưu. Có đủ đĩa cho một giờ không giúp được nếu thành phần gửi loại dữ liệu sau năm phút.

Để tránh đợt gửi bù làm backend quá tải, giới hạn tốc độ và mức song song trong giai đoạn phục hồi, rồi theo dõi cả tuổi dữ liệu cũ nhất đang chờ. Hàng đợi nhỏ về số lượng vẫn có thể chứa dữ liệu quá cũ.

## 9. Kiểm soát chi phí ngay cả khi đường truyền bình thường

Chi phí metrics không chỉ là hóa đơn lưu trữ. Cần tính RAM trong JVM, CPU tổng hợp/serialize, mạng, đĩa bộ đệm, tài nguyên truy vấn và công sức vận hành khi dữ liệu chậm hoặc thiếu.

### 9.1. Kiểm soát số chuỗi trước khi giảm chất lượng đo

Một metric gắn nhãn `route`, `status`, `instance` có thể tạo nhiều chuỗi theo các tổ hợp thực tế. Ước lượng trần đơn giản với 20 route, 5 trạng thái và 10 instance:

```text
20 × 5 × 10 = 1000 tổ hợp
```

Không phải mọi tổ hợp đều xuất hiện, và một meter có thể sinh nhiều chuỗi đầu ra. Vì vậy con số này là điểm xuất phát cho kế hoạch, không phải tổng cuối cùng.

Nếu thêm `userId` có 100.000 giá trị vào các tổ hợp đó, trần lý thuyết thành 100 triệu tổ hợp. Đây là vấn đề thiết kế nhãn; kéo dài timeout không giải quyết được.

Nên dùng route mẫu như `/orders/{id}` thay cho từng đường dẫn chứa mã đơn. Không đưa request ID hoặc thông điệp lỗi tùy ý vào nhãn metrics. Nếu cần tìm một yêu cầu cụ thể, dùng dữ liệu log/trace phù hợp. Hướng dẫn chính thức cũng nhấn mạnh chi phí của số lượng nhãn và chuỗi: [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/).

Micrometer có `MeterFilter` để từ chối meter hoặc giới hạn số giá trị nhãn, chẳng hạn `maximumAllowableTags`. Đây là hàng rào bảo vệ, không thay thế thiết kế nhãn có giới hạn. Từ chối meter đồng nghĩa phép đo đó không được ghi nhận qua meter bị từ chối; phải đưa việc loại bỏ có chủ đích này vào chính sách quan sát. Xem [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

### 9.2. Cân đối độ phân giải, histogram và số bản sao

Với số chuỗi ổn định và chu kỳ scrape đều:

```text
Số mẫu/ngày ≈ số chuỗi × 86.400 / scrape_interval_tính_bằng_giây
```

Ví dụ 10.000 chuỗi:

- Scrape 15 giây: khoảng 57.600.000 mẫu/ngày.
- Scrape 60 giây: khoảng 14.400.000 mẫu/ngày.

Đây là ước lượng số mẫu, không phải công thức hóa đơn. Giá thực tế còn phụ thuộc cách tính phí theo chuỗi hoạt động, điểm nhận, dung lượng, truy vấn, retention và bản sao.

Kéo dài chu kỳ làm giảm độ phân giải và tăng thời gian phát hiện một số sự cố. Không áp dụng đồng loạt cho cả metric quan trọng và metric ít dùng.

Với histogram kiểu cổ điển, mỗi nhóm nhãn thường tạo thêm các chuỗi bucket, count và sum. Cần kiểm tra đầu ra thực tế vì loại registry và cấu hình có thể bổ sung chuỗi khác. Chỉ bật độ chi tiết cần để trả lời câu hỏi vận hành/SLO, tránh bật mọi phân vị/histogram cho mọi meter mà không đo chi phí.

Nếu dùng nhiều Prometheus, nhiều Collector hoặc nhiều registry gửi cùng số liệu, phải hiểu cơ chế phân biệt/deduplicate ở nơi nhận. Nhiều bản sao giúp tăng sẵn sàng trong thiết kế phù hợp nhưng cũng có thể tăng lượng nhận và chi phí.

### 9.3. Khi lỗi, chi phí còn đến từ retry và log

Một gián đoạn 10 phút có thể gây tải ở ba thời điểm:

1. Trước gián đoạn: lưu lượng metrics bình thường.
2. Trong gián đoạn: kết nối thất bại, retry, log, bộ đệm và đĩa tăng.
3. Sau gián đoạn: vừa gửi mới vừa gửi bù, gây đỉnh lưu lượng.

Cần giới hạn log lặp lại bằng cơ chế phù hợp của thành phần vận hành, đồng thời giữ bộ đếm lỗi và mốc thời gian để điều tra. Không ghi toàn bộ payload hoặc thông tin xác thực chỉ để chẩn đoán một lỗi kết nối.

## 10. Theo dõi chính đường truyền metrics

Không chỉ cảnh báo giá trị nghiệp vụ cao/thấp; phải cảnh báo khi không còn biết giá trị đó.

Trong ví dụ Prometheus, hai biểu thức sau trả lời hai câu hỏi riêng:

```promql
up{job="orders-demo"} == 0
```

Biểu thức này phát hiện target vẫn được Prometheus theo dõi nhưng lần scrape không thành công.

```promql
absent_over_time(up{job="orders-demo"}[5m])
```

Biểu thức này phát hiện toàn bộ tập chuỗi khớp job không có mẫu trong năm phút. Nó không phát hiện từng instance bị biến mất nếu instance khác của job vẫn có mẫu. Muốn phát hiện thiếu từng instance cần biết danh sách instance kỳ vọng hoặc một nguồn đối chiếu phù hợp. Các biểu thức ở đây là điều kiện minh họa, chưa phải cấu hình cảnh báo hoàn chỉnh; xem [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Cần quan sát thêm:

- Thời gian scrape, kích thước phản hồi và số chuỗi/mẫu.
- Số lần xuất thất bại, bị từ chối hoặc bị loại ở thành phần thực sự xuất dữ liệu.
- Dung lượng, độ đầy và tuổi dữ liệu trong hàng đợi.
- Thời điểm gửi thành công gần nhất và độ trễ từ thu thập đến nơi truy vấn.
- RAM, CPU, đĩa, số kết nối khi backend hỏng và khi phục hồi.

Tên metric nội bộ phụ thuộc sản phẩm/phiên bản; kiểm tra endpoint và tài liệu của chính Prometheus/Collector đang triển khai, không tự tạo một tên rồi cho rằng hệ thống đã xuất nó.

Nếu toàn bộ Prometheus và hệ thống gửi cảnh báo cùng ngừng chạy, chính Prometheus đó không thể gửi cảnh báo về sự ngừng chạy của mình. Cần một đường kiểm tra độc lập, chẳng hạn hệ thống khác theo dõi sự hiện diện của tín hiệu định kỳ. Trên dashboard, hiển thị khoảng trống và độ mới; không thay mọi giá trị thiếu bằng 0 để làm biểu đồ liền mạch.

## 11. Thực hành: chứng minh điều còn giữ được sau gián đoạn

Đây là kịch bản kiểm chứng cho môi trường thử nghiệm, không phải kết quả đã chạy trên một hệ thống cụ thể.

### 11.1. Kiểm tra đường pull bình thường

Khởi động ứng dụng và Prometheus theo mục 6.1. Trên Windows có curl:

```powershell
curl.exe --fail --silent --show-error http://127.0.0.1:9091/actuator/health
curl.exe --fail --silent --show-error http://127.0.0.1:9091/actuator/prometheus
```

Trên Linux/macOS dùng `curl` thay cho `curl.exe`. Nếu đã bật bảo mật, bổ sung cách xác thực của môi trường; không tắt bảo mật chỉ để ép lệnh chạy.

Kỳ vọng: endpoint health trả phản hồi hợp lệ; endpoint Prometheus trả nội dung exposition thay vì JSON danh sách meter. Danh sách metric và giá trị cụ thể phụ thuộc ứng dụng, dependency và tải tại thời điểm đọc.

Trong Prometheus, xác nhận target ở trạng thái UP và có mẫu. Tạo tải có kiểm soát vào một nghiệp vụ có sẵn; chọn một counter tích lũy thực sự có trong dữ liệu và ghi lại **đầy đủ nhãn** cùng giá trị ban đầu.

### 11.2. Mô phỏng không scrape được trong khi nghiệp vụ vẫn chạy

Trong môi trường thử nghiệm, tạm chặn **đúng kết nối từ Prometheus đến cổng quản trị 9091**, giữ đường nghiệp vụ hoạt động. Không chặn toàn bộ mạng ứng dụng vì như vậy đang kiểm tra thêm một sự cố khác.

Giữ gián đoạn qua vài chu kỳ scrape, tiếp tục tạo tải rồi khôi phục kết nối.

Quan sát kỳ vọng:

- Target có lần scrape lỗi; biểu đồ có khoảng thiếu mẫu.
- Nếu cùng JVM và cùng chuỗi counter tiếp tục tồn tại, giá trị sau phục hồi có thể bao gồm phần tăng trong khoảng gián đoạn.
- Không có các điểm thời gian bị bỏ lỡ được tái tạo một cách kỳ diệu.
- Gauge có thể bỏ lỡ đỉnh chỉ xuất hiện khi không thu thập được.
- Thời gian đáp ứng nghiệp vụ và mức sử dụng tài nguyên phải được đối chiếu với mức nền.

Nếu không thể chặn riêng đường scrape, có thể dừng Prometheus để quan sát mất thu thập. Nhưng khi Prometheus dừng, không mong chính nó ghi liên tục `up=0`; khi đó đã thay đổi loại thí nghiệm và cần ghi rõ.

### 11.3. Lặp lại với một lần restart ứng dụng

Thực hiện lại gián đoạn và chủ động restart ứng dụng thử nghiệm sau khi đã phát sinh thêm tải. Đối chiếu các mẫu trước/sau cùng thời điểm restart.

Kỳ vọng: bộ đếm trong JVM mới bắt đầu lại; phần tăng của JVM cũ chưa được scrape không thể phục hồi chỉ từ JVM mới. Lưu lại kết luận này riêng với trường hợp không restart.

### 11.4. Thử gián đoạn backend phía sau bộ đệm

Giữ Prometheus/Collector gần ứng dụng hoạt động, chỉ làm backend từ xa không nhận dữ liệu.

Kiểm tra lần lượt:

1. Dữ liệu đầu vào vẫn được thu nhận.
2. Hàng đợi tăng theo tốc độ dự kiến.
3. Tài nguyên vẫn nằm trong ngân sách.
4. Khi hết giới hạn/thời hạn, xác định dữ liệu nào bị loại.
5. Sau phục hồi, tốc độ gửi vượt tốc độ vào đủ để giảm backlog.
6. Nếu có lưu bền vững, restart thành phần đệm và xác minh dữ liệu đang chờ còn được phục hồi.

Đánh giá bằng số liệu nhận được tại backend và độ mới sau khi bắt kịp, không chỉ bằng việc log ngừng báo lỗi. Nếu giao thức cho phép nhận một phần hoặc retry gây trùng, phải tính cả phần bị từ chối/trùng khi đối chiếu.

## 12. Những kết luận sai thường gặp

| Kết luận sai | Cách hiểu cần thay thế |
| --- | --- |
| Không có điểm trên biểu đồ nghĩa là lưu lượng bằng 0 | Phân biệt giá trị 0 với không có mẫu |
| Tăng timeout sẽ chống mất dữ liệu | Timeout chỉ điều khiển chờ; còn cần hiểu bộ đệm và loại số liệu |
| Counter còn nguyên nên khôi phục được mọi giây đã mất | Có thể giữ tổng mức tăng trong điều kiện phù hợp, nhưng mất phân bố thời gian |
| Retry càng nhiều càng an toàn | Retry không giới hạn có thể làm đầy RAM/đĩa hoặc kéo dài tải lên backend |
| Có WAL thì không bao giờ mất | WAL vẫn có giới hạn, lỗi đĩa, thời hạn và phạm vi bảo vệ |
| Đổi `step` là tăng thời gian lưu bù | Chu kỳ xuất và thời hạn lưu bù là hai cơ chế khác nhau |
| Đổi `batch-size` là giới hạn tổng bộ nhớ | Kích thước một request không giới hạn mọi dữ liệu đang chờ |
| Đẩy qua Pushgateway là có một hàng đợi lịch sử | Không suy ra bảo đảm lưu/gửi lại lịch sử từ sự hiện diện của một gateway |
| Backend metrics hỏng thì phải đánh dấu mọi ứng dụng không sẵn sàng | Đánh giá độc lập khả năng phục vụ nghiệp vụ và khả năng quan sát |
| Backend hết lỗi thì sự cố đã xong | Còn phải xác minh backlog, độ mới, phần mất và đỉnh chi phí khi gửi bù |

## 13. Tự kiểm tra bằng ba tình huống

**Tình huống 1:** Counter được scrape là 500. Trong ba phút tiếp theo ứng dụng xử lý thêm 90 yêu cầu, không restart, rồi scrape lại được 590. Ta biết gì?

Ta biết mức tăng giữa hai lần quan sát là 90 nếu đó vẫn là cùng chuỗi tích lũy. Không biết số yêu cầu chính xác trong từng phút. Kết quả của một truy vấn `increase()` cụ thể còn chịu quy tắc cửa sổ và ngoại suy; không đồng nhất số chênh lệch thô với mọi kết quả truy vấn.

**Tình huống 2:** Bộ đệm còn 120.000 điểm, đầu vào 400 điểm/giây, backend ngừng nhận. Chịu được bao lâu?

Theo mô hình đơn giản: `120.000 / 400 = 300 giây`, tức năm phút. Nếu timeout retry sớm hơn, hàng đợi không thực sự còn đủ chỗ hoặc lưu lượng tăng, thời gian hữu ích sẽ thấp hơn.

**Tình huống 3:** Backend nhận lại được 350 điểm/giây trong khi đầu vào vẫn 400 điểm/giây. Vì sao backlog không giảm dù tăng kích thước hàng đợi?

Tốc độ thoát nhỏ hơn tốc độ vào nên backlog còn tăng 50 điểm/giây. Cần thay đổi năng lực hoặc lượng vào/chính sách loại bỏ; dung lượng lớn hơn chỉ kéo dài thời gian trước khi chạm giới hạn.

Khi thiết kế xuất metrics cho Actuator, kết quả cần đạt là một đường truyền có phạm vi mất dữ liệu được hiểu rõ, tài nguyên được chặn trong ngân sách và khả năng phục hồi đã được kiểm chứng. Quyết định chấp nhận mất phần nào phải xuất phát từ câu hỏi quan sát cần trả lời và yêu cầu nghiệp vụ thực tế.
