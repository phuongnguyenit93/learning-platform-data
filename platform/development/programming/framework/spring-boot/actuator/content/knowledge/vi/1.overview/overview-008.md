# Lộ trình từ kiểm tra sức khỏe đến quan sát ứng dụng đang vận hành

Bạn đã gọi được `/actuator/health` và thấy ứng dụng trả về `UP`. Đây là một điểm bắt đầu hữu ích: ứng dụng đã cung cấp một tín hiệu sức khỏe mà công cụ bên ngoài có thể đọc. Bước tiếp theo là biết tín hiệu ấy phản ánh điều gì, rồi bổ sung dữ liệu để theo dõi chất lượng phục vụ và điều tra khi có vấn đề.

Mục tiêu của lộ trình này là giúp bạn tiến từ **đọc trạng thái tại một thời điểm** tới **hiểu điều đang diễn ra với ứng dụng trong môi trường vận hành**. Mỗi chặng có một câu hỏi, một việc thực hành và một bằng chứng cho thấy bạn đã hiểu. Các ví dụ cấu hình lấy Spring Boot 3.3 làm mốc.

## 1. Hình dung đích đến trước khi chọn công cụ

**Khả năng quan sát (observability)** là năng lực tìm hiểu trạng thái và hành vi của hệ thống thông qua dữ liệu nó phát ra. Nó có ích khi bạn cần đặt thêm câu hỏi sau một dấu hiệu bất thường, thay vì chỉ xem những biểu đồ đã chuẩn bị sẵn. Xem [OpenTelemetry — Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/).

Một cách tổ chức việc học:

```text
Đọc đúng sức khỏe
        ↓
Hiểu khả năng tiếp nhận công việc
        ↓
Đo tải, lỗi, thời gian và tài nguyên
        ↓
Lưu lịch sử và kiểm tra đường thu thập
        ↓
Đo kết quả nghiệp vụ, nối sự kiện với đường xử lý
        ↓
Phát hiện ảnh hưởng và thực hành ứng phó
        ↓
Rút kinh nghiệm, cải thiện dữ liệu và quy tắc
```

Đây là trình tự xây dựng hiểu biết. Trong thực tế, nhiều việc được triển khai song song; bảo vệ dữ liệu và quyền truy cập cần được làm ngay từ đầu.

| Khi có câu hỏi này | Bạn cần tiến tới năng lực nào? |
| --- | --- |
| Ứng dụng đang báo trạng thái gì? | Đọc và diễn giải health |
| Phiên bản chạy này có nên nhận thêm việc không? | Hiểu liveness/readiness và cách nền tảng sử dụng chúng |
| Dịch vụ đang chậm hoặc lỗi đến mức nào? | Đọc số đo có đơn vị, khoảng thời gian và phạm vi |
| Vấn đề bắt đầu trước hay sau thay đổi nào? | Có lịch sử, danh tính phiên bản và mốc triển khai |
| Công việc nào bị ảnh hưởng, chậm ở bước nào? | Có số đo nghiệp vụ, nhật ký và dấu vết liên kết được |
| Khi nào cần hành động, hành động ra sao? | Có mục tiêu, cảnh báo, hướng dẫn ứng phó và kiểm chứng sau xử lý |

Để xuyên suốt bài học, hãy tưởng tượng một dịch vụ nhận tệp để xử lý ở phía sau. Người dùng quan tâm tệp hợp lệ có được xử lý đúng và đúng hạn hay không. Máy chủ còn chạy mới trả lời một phần nhỏ của câu hỏi đó.

## 2. Chuẩn bị một ứng dụng và một phạm vi quan sát rõ ràng

Dùng ứng dụng web Spring Boot có sẵn và dependency `spring-boot-starter-actuator`. Không cần tạo thêm API nghiệp vụ chỉ để bắt đầu đọc dữ liệu vận hành.

Trước khi gọi lệnh, ghi rõ:

- Đang quan sát môi trường học tập hay môi trường dùng thật?
- Tên dịch vụ, phiên bản phần mềm và phiên bản chạy cụ thể là gì?
- Thời điểm ghi nhận dùng múi giờ nào?
- Ai được phép đọc dữ liệu quản trị?
- Đường dẫn và cổng quản trị hiện tại là gì?

Trong các lệnh bên dưới, giả sử ứng dụng ở `localhost:8080`, đường dẫn gốc không thay đổi và Actuator dùng tiền tố mặc định `/actuator`. Nếu cấu hình khác, phải dùng địa chỉ thật. Spring Boot cho phép đổi đường dẫn và cổng quản trị; tham khảo [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Các mảnh YAML là cấu hình cho từng chặng. Khi áp dụng cùng nhau, hợp nhất vào một cây `management` hợp lệ trong cấu hình của môi trường học tập, không tạo nhiều khóa cùng tên ở cùng cấp. Nếu ứng dụng dùng Spring Security, thực hiện theo cơ chế xác thực và phân quyền đang có.

## 3. Chặng 1 — Đọc đúng kết quả kiểm tra sức khỏe

**Câu hỏi:** ứng dụng báo trạng thái sức khỏe gì, dựa trên những phép kiểm tra nào?

Thử gọi trên Windows:

```powershell
curl.exe -i "http://localhost:8080/actuator/health"
```

Trên Linux/macOS, dùng chương trình `curl` tương ứng. Ghi lại cả mã HTTP và nội dung phản hồi thật.

Một phản hồi minh họa tối giản:

```json
{
  "status": "UP"
}
```

Đây là ví dụ cấu trúc, không phải kết quả bắt buộc trong mọi lần gọi. Phản hồi có thể có các thành phần và chi tiết tùy cấu hình, quyền truy cập và trạng thái thật. Xem [Actuator Health REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 3.1. Giải thích đúng phạm vi của health

Health tổng hợp các phép kiểm tra được cấu hình. Bạn cần biết phép kiểm tra nào đang tham gia và điều kiện nào làm chúng thay đổi.

Với dịch vụ xử lý tệp, một phép kiểm tra kết nối cơ sở dữ liệu có thể thành công trong khi hàng đợi công việc tăng rất nhanh. Hoặc tiến trình vẫn báo khỏe nhưng một lỗi nghiệp vụ làm dữ liệu đầu ra sai. Đừng mở rộng kết luận của một phép kiểm tra vượt khỏi điều nó thực sự kiểm tra.

Trong Spring Boot 3.3, mặc định chỉ điểm truy cập `health` được công khai qua HTTP. Việc bật điểm truy cập, công khai qua HTTP và cho phép người dùng truy cập cần được xét riêng. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 3.2. Thực hành và bằng chứng đạt chặng

Trong môi trường thử nghiệm, xác định một thành phần kiểm tra có thật của ứng dụng. Đọc cấu hình hoặc tài liệu của phép kiểm tra đó, rồi ghi:

```text
Phép kiểm tra giả định: thử kết nối tới kho dữ liệu.
Khỏe: phép thử kết nối theo thiết kế thành công.
Không khỏe: phép thử kết nối thất bại.
Chưa bao phủ: độ đúng của đầu ra và thời hạn xử lý từng tệp.
```

Đây là mẫu ghi chép đã điền bằng một phép kiểm tra giả định. Hãy thay bằng phép kiểm tra có thật và điều kiện chính xác của ứng dụng; mẫu này không phải cấu hình.

**Đạt chặng khi:** bạn giải thích được vì sao kết quả hiện tại xuất hiện và nêu được ít nhất một tình huống người dùng gặp vấn đề dù health vẫn tốt.

## 4. Chặng 2 — Phân biệt sức sống với khả năng nhận việc

**Câu hỏi:** tiến trình cần được khởi động lại, hay chỉ nên tạm ngừng nhận thêm công việc?

Spring Boot có hai trạng thái sẵn sàng vận hành quan trọng:

- **Trạng thái còn hoạt động đúng (liveness):** phản ánh khả năng hoạt động hoặc tự phục hồi từ trạng thái nội tại. Khi trạng thái bị hỏng, nền tảng có thể cần khởi động lại.
- **Trạng thái sẵn sàng nhận lưu lượng (readiness):** phản ánh khả năng tiếp nhận công việc ở thời điểm hiện tại.

Các trạng thái này và vòng đời ứng dụng được mô tả trong [Spring Boot 3.3 — Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### 4.1. Không dùng cùng một tín hiệu cho mọi quyết định

Với dịch vụ xử lý tệp, hãy tự hỏi: nếu kho lưu trữ bên ngoài tạm gián đoạn, khởi động lại mọi tiến trình có giúp ích không? Nếu mọi tiến trình cùng dùng một dịch vụ ngoài đang hỏng, việc khởi động lại hàng loạt có thể làm tình hình khó phục hồi hơn.

Với bộ xử lý lấy việc từ hàng đợi, cần kiểm tra cả cơ chế tạm dừng nhận việc của chính bộ xử lý; không suy ra hành vi đó chỉ từ trạng thái readiness HTTP.

Readiness cũng cần thiết kế theo khả năng phục vụ thật: một thành phần ngoài có thể bắt buộc cho mọi công việc, chỉ cần cho một loại công việc, hoặc có phương án dự phòng. Vì vậy, không tự đưa mọi kiểm tra phụ thuộc vào cùng một nhóm mà không xét tác động.

### 4.2. Quan sát các nhóm probe trong môi trường học tập

Để bật các nhóm probe ngoài môi trường Kubernetes:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Sau khi áp dụng cấu hình và chạy lại ứng dụng:

```powershell
curl.exe -i "http://localhost:8080/actuator/health/liveness"
curl.exe -i "http://localhost:8080/actuator/health/readiness"
```

Spring Boot tự bật các nhóm này khi nhận diện môi trường Kubernetes. Mặc định các nhóm không tự chứa mọi kiểm tra phụ thuộc bên ngoài; việc bổ sung cần được quyết định rõ. Xem [Spring Boot 3.3 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Việc đọc URL không tự cấu hình nền tảng điều phối. Kubernetes cần cấu hình probe để thực hiện hành động tương ứng; probe khởi động (startup probe) còn giúp bảo vệ ứng dụng khởi động chậm khỏi bị xử lý quá sớm. Tham khảo [Kubernetes — Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Nếu cổng quản trị tách khỏi cổng phục vụ chính, cần kiểm tra tín hiệu có đại diện cho đường phục vụ thật hay không. Một cổng còn đáp ứng không tự chứng minh cổng khác vẫn tiếp nhận kết nối tốt.

**Đạt chặng khi:** bạn giải thích được sự khác nhau giữa khởi động lại và tạm dừng nhận lưu lượng, cùng hậu quả nếu chọn sai tín hiệu.

## 5. Chặng 3 — Đo chất lượng phục vụ thay vì chỉ nhìn trạng thái

**Câu hỏi:** khi ứng dụng còn chạy, người dùng và tài nguyên đang trải qua điều gì?

Bắt đầu với bốn nhóm câu hỏi: có bao nhiêu công việc đến, mất bao lâu, thất bại bao nhiêu và tài nguyên nào đang gần giới hạn. Đây là hướng tiếp cận tương ứng với các tín hiệu lưu lượng, độ trễ, lỗi và mức bão hòa được trình bày trong [Google SRE — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/).

| Nhóm câu hỏi | Ví dụ cho dịch vụ xử lý tệp | Cần nêu rõ |
| --- | --- | --- |
| Lưu lượng | Số tệp được nhận mỗi phút | Đếm yêu cầu, lần thử hay công việc duy nhất? |
| Thời gian | Thời gian nhận yêu cầu; thời gian từ nhận tới hoàn tất | Đơn vị và hai mốc bắt đầu/kết thúc |
| Lỗi | Công việc thất bại; đầu ra không đạt yêu cầu | Định nghĩa thất bại và tập công việc được tính |
| Bão hòa | Công việc chờ, kết nối đang dùng, bộ nhớ | Giới hạn hoặc mức bình thường để so sánh |

### 5.1. Khám phá số đo có sẵn

Trong cấu hình môi trường thử nghiệm:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
```

Đọc danh sách và chỉ truy vấn tên có thật:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
curl.exe -i "http://localhost:8080/actuator/metrics/jvm.memory.used"
```

Lệnh thứ hai là ví dụ nếu danh sách có `jvm.memory.used`. Đọc đơn vị và các nhãn phân loại, không chỉ lấy một con số ra khỏi phản hồi. API `metrics` phục vụ kiểm tra các số đo đang đăng ký; nó không được thiết kế làm kho giám sát hoặc nguồn thu thập định kỳ trong môi trường vận hành. Xem [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Spring Boot tích hợp Micrometer để ghi và cung cấp số đo cho nhiều hệ thống đích. Các số đo tự động phụ thuộc thành phần và cấu hình hiện có; chúng không tự hiểu toàn bộ quy trình xử lý tệp của bạn. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 5.2. Đọc số đo cùng ngữ cảnh

Ba lỗi cần tránh:

- Lấy tổng tích lũy từ lúc tiến trình khởi động rồi gọi đó là lưu lượng trong một phút.
- Xem HTTP trả lời nhanh là bằng chứng công việc chạy nền đã hoàn tất nhanh.
- Xem thời gian trung bình là bằng chứng mọi người dùng đều có trải nghiệm tương tự.

Khi dùng p95/p99, cần biết cửa sổ thời gian, số quan sát và cách tính. Các phân vị tính riêng ở từng phiên bản chạy không thể được gộp bằng cách lấy trung bình để ra phân vị toàn dịch vụ. Việc tổng hợp qua nhiều chiều cần phương pháp phù hợp, chẳng hạn biểu đồ phân bố với các khoảng đếm (histogram). Xem [Micrometer 1.13 — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

**Đạt chặng khi:** với một số đo, bạn nêu được đại lượng, đơn vị, phạm vi, khoảng thời gian và câu hỏi nó chưa trả lời được.

## 6. Chặng 4 — Tạo lịch sử và xác nhận đường thu thập

**Câu hỏi:** dữ liệu có được lấy ra ngoài ứng dụng và còn truy vấn được sau thời điểm xảy ra vấn đề không?

Một lần gọi Actuator chỉ cho bạn một lần quan sát. Muốn so sánh trước/sau triển khai hoặc xem lại một khoảng thời gian, cần đường thu thập và nơi lưu.

Ví dụ với mô hình Prometheus:

```text
Ứng dụng ghi số đo qua Micrometer
              ↓
Registry cung cấp dữ liệu cho hệ thống đích
              ↓
Prometheus đọc /actuator/prometheus định kỳ
              ↓
Các mẫu được lưu theo thời gian
              ↓
Truy vấn, biểu đồ và đánh giá điều kiện
```

Prometheus sử dụng mô hình đọc chủ động qua HTTP và lưu dữ liệu dạng chuỗi thời gian. Đây là một lựa chọn minh họa, không phải điều kiện bắt buộc để mọi ứng dụng có khả năng quan sát. Xem [Prometheus — Overview](https://prometheus.io/docs/introduction/overview/).

### 6.1. Thiết lập một đường học tập tối thiểu

Với ứng dụng đã quản lý phiên bản bằng plugin/BOM Spring Boot, bổ sung registry Prometheus vào khối dependency:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Hợp nhất danh sách công khai cho môi trường học tập thành `health,metrics,prometheus`. Kiểm tra đường `/actuator/prometheus` ở phía ứng dụng trước.

Ví dụ cấu hình của một Prometheus chạy trực tiếp trên cùng máy:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "file-service-lab"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
```

Đây là tệp cấu hình cho Prometheus, không đặt khối `scrape_configs` vào `application.yml` của Spring Boot. Địa chỉ phải truy cập được từ chính nơi Prometheus chạy; `localhost` trong container là container đó. Tham khảo [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Đối với dịch vụ giám sát dùng đường đẩy dữ liệu, cấu hình registry và nơi tiếp nhận theo giao thức tương ứng. Khi ấy danh sách công khai HTTP của Actuator không thay thế cấu hình xuất dữ liệu.

### 6.2. Kiểm tra cả nguồn và bên thu thập

Với job ở ví dụ:

```promql
up{job="file-service-lab"}
```

Giá trị 1 thể hiện lần thu thập thành công, 0 thể hiện thất bại. Không có chuỗi cần được phân biệt với giá trị 0: có thể mục tiêu chưa được cấu hình, chưa có dữ liệu hoặc bộ lọc đang không khớp. Xem [Prometheus — Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/).

Đừng đồng nhất `up=1` với health báo `UP` hoặc với công việc nghiệp vụ thành công. Ba tín hiệu trả lời ba câu hỏi khác nhau.

Gắn được dữ liệu với dịch vụ, phiên bản chạy và mốc triển khai sẽ giúp so sánh có ý nghĩa. Đồng thời cần biết thời hạn lưu: một biểu đồ đẹp không tạo lại dữ liệu đã mất hoặc chưa từng được thu thập.

**Đạt chặng khi:** bạn chỉ ra được nguồn, đường truyền, nơi lưu và một truy vấn xem lại dữ liệu của khoảng thời gian đã qua; đồng thời phát hiện được khi đường thu thập ngừng hoạt động.

## 7. Chặng 5 — Đo điều người dùng thực sự cần và nối các bằng chứng

**Câu hỏi:** ứng dụng có hoàn thành công việc đúng kỳ vọng, và có thể truy tìm một trường hợp bị ảnh hưởng không?

Ở dịch vụ xử lý tệp, một phản hồi HTTP chấp nhận yêu cầu chưa phải kết quả cuối cùng. Cần nhìn cả giai đoạn chờ, xử lý và tạo đầu ra.

### 7.1. Viết định nghĩa trước khi thêm số đo

Một định nghĩa minh họa:

```text
Đối tượng: công việc xử lý tệp hợp lệ đã được nhận.
Kết quả tốt: có đầu ra đúng trong vòng 2 phút kể từ lúc nhận.
Cửa sổ đánh giá: 30 ngày.
Chỉ số: số công việc có kết quả tốt / tổng công việc đủ điều kiện.
Mục tiêu minh họa: tối thiểu 99%.
```

Cần xác định rõ công việc nào đủ điều kiện, thời điểm bắt đầu, cách xác nhận đầu ra đúng và khi nào đã đủ thời gian để kết luận. Không loại công việc thất bại hoặc quá hạn ra khỏi mẫu số chỉ để chỉ số tốt hơn.

**Chỉ số mức dịch vụ (SLI)** là đại lượng đo chất lượng phục vụ; **mục tiêu mức dịch vụ (SLO)** đặt mức đích cho chỉ số trong một khoảng đánh giá. Khái niệm và cách lựa chọn được trình bày trong [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/).

Ví dụ giả định cho một tập đã đủ thời gian đánh giá: có 1.000 công việc đủ điều kiện, 920 có đầu ra đúng trong thời hạn. Tỷ lệ tốt của tập đó là:

```text
920 / 1000 × 100% = 92%
```

Đây là phép tính cho tập minh họa. Muốn đánh giá SLO 30 ngày, phải dùng dữ liệu đúng cửa sổ 30 ngày và đúng định nghĩa; không dùng một đợt thử ngắn để kết luận thay cho cả cửa sổ.

### 7.2. Bổ sung dữ liệu còn thiếu trong quy trình

Xác định tại đâu ứng dụng biết chắc:

- Công việc đã được nhận bền vững.
- Công việc bắt đầu được xử lý.
- Đầu ra đã được xác nhận thành công hoặc thất bại.
- Công việc đã chờ quá hạn.

Từ đó chọn số đo và vị trí ghi nhận phù hợp. Với cách xử lý có thử lại, cần phân biệt số lần thử với số công việc duy nhất để tránh đếm hai lần.

Trong ứng dụng Spring Boot, dùng cơ chế đo được quản lý và tích hợp đúng với đường xuất hiện có. Spring Boot hỗ trợ Micrometer Observation để mô tả thao tác được quan sát, cùng các bộ xử lý tương ứng cho số đo và dấu vết. Xem [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Không đưa nội dung tệp, token hoặc mã duy nhất của từng công việc vào nhãn số đo một cách tùy ý. Hãy giữ số giá trị nhãn có kiểm soát; dùng dữ liệu sự kiện có quyền truy cập phù hợp khi cần tra một trường hợp cụ thể.

### 7.3. Nhật ký giúp tìm sự kiện

**Nhật ký (log)** ghi nhận sự kiện với thời điểm và ngữ cảnh. Các trường có cấu trúc giúp tìm các sự kiện liên quan; khả năng nối với dấu vết còn phụ thuộc ngữ cảnh được thu và truyền. Xem [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

Ví dụ sau là dữ liệu giả định do bài học đặt ra, không phải định dạng nhật ký mặc định của Spring Boot:

```json
{
  "timestamp": "2026-02-12T10:15:30Z",
  "service": "file-service",
  "version": "v3",
  "event": "file_processing_delayed",
  "jobId": "lab-job-42",
  "stage": "waiting",
  "waitingMs": 125000,
  "traceId": "11112222333344445555666677778888"
}
```

Bản ghi giúp tìm công việc đang chờ quá lâu theo ngữ cảnh đã ghi. Nó chưa tự chứng minh thành phần nào là nguyên nhân. Tên sự kiện và trường dữ liệu cần được thiết kế theo ý nghĩa thật của ứng dụng.

### 7.4. Dấu vết giúp hiểu đường xử lý

**Dấu vết (trace)** liên kết các thao tác; mỗi **span** mô tả một đơn vị công việc đã được gắn cơ chế thu thập. Nhờ đó có thể xem thời gian tập trung ở bước nào hoặc lời gọi nào. Tham khảo [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Với công việc chạy nền, ngữ cảnh cần được truyền qua hàng đợi và ranh giới xử lý theo cơ chế đã chọn. Không mặc định một mã dấu vết trong lúc nhận HTTP sẽ tự xuất hiện ở mọi bộ xử lý phía sau.

Spring Boot hỗ trợ Micrometer Tracing; cần tích hợp tracer, bộ xuất dữ liệu và nơi tiếp nhận phù hợp. Các máy khách HTTP cũng cần được tạo theo cơ chế tích hợp để tự truyền ngữ cảnh như mong đợi. Xem [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Cơ chế lấy mẫu có thể chỉ lưu một phần dấu vết. Vì vậy, không tìm thấy dấu vết không đủ để kết luận công việc không xảy ra. Xem [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/).

**Đạt chặng khi:** từ một chỉ số bất thường, bạn tìm được một trường hợp đại diện, xác định các sự kiện và bước xử lý liên quan, đồng thời nêu được khoảng trống dữ liệu còn lại.

## 8. Chặng 6 — Biến tín hiệu thành phát hiện và hành động

**Câu hỏi:** dấu hiệu nào cần được chú ý, ai xử lý và bằng cách nào?

Cảnh báo nên gắn với ảnh hưởng hoặc nguy cơ cụ thể đối với mục tiêu phục vụ. Một biến tài nguyên vượt ngưỡng có thể giúp điều tra, nhưng chưa chắc đáng đánh thức người trực nếu chưa có nguy cơ hoặc hành động hữu ích. Cách liên hệ cảnh báo với SLO được trình bày trong [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/).

### 8.1. Thiết kế một cảnh báo có thể xử lý

Với dịch vụ xử lý tệp, hãy mô tả cảnh báo theo các câu hỏi:

| Thành phần | Ví dụ nội dung cần quyết định |
| --- | --- |
| Hiện tượng | Tỷ lệ công việc quá hạn đang tăng ở nhóm nào? |
| Cửa sổ và lượng dữ liệu | Đánh giá bao lâu, cần tối thiểu bao nhiêu công việc? |
| Mức ảnh hưởng | Người dùng không nhận được kết quả, hay chỉ có nguy cơ trễ? |
| Người chịu trách nhiệm | Nhóm nào có thể xác minh và hành động? |
| Liên kết điều tra | Truy vấn, khoảng thời gian, phiên bản và dữ liệu liên quan |
| Cách kết thúc | Bằng chứng nào xác nhận dịch vụ đã phục hồi? |

Ngưỡng trong một ví dụ học tập không phải mặc định áp dụng cho mọi dịch vụ. Với lưu lượng thấp, tỷ lệ phần trăm cần được đọc cùng số lượng tuyệt đối. Với lỗi chập chờn, cần xét cả độ nhạy phát hiện và số cảnh báo gây nhiễu.

Việc tạo quy tắc và việc chuyển thông báo là hai chặng cần kiểm tra. Hãy thử một tình huống có kiểm soát để biết thông báo đến đúng người, có đủ ngữ cảnh và có thể đánh dấu đã xử lý.

### 8.2. Viết hướng dẫn ứng phó ngắn

Một hướng dẫn xử lý sự cố (runbook) nên giúp người khác bắt đầu mà không phải đoán:

1. Xác nhận phạm vi ảnh hưởng và thời điểm bắt đầu.
2. Kiểm tra dữ liệu có đang được thu đầy đủ không.
3. So sánh tải, thời gian chờ, lỗi, phiên bản và mốc thay đổi.
4. Chọn một giả thuyết và tìm bằng chứng xác nhận hoặc bác bỏ.
5. Giảm ảnh hưởng bằng hành động phù hợp với quyền và quy trình.
6. Kiểm tra lại chất lượng phục vụ sau hành động.

Dùng cách suy luận dựa trên giả thuyết và bằng chứng thay vì sửa nhiều biến cùng lúc. Tham khảo [Google SRE — Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/).

**Đạt chặng khi:** một người khác có thể dùng cảnh báo và hướng dẫn của bạn để xác minh vấn đề, biết bước kiểm tra tiếp theo và xác nhận kết quả sau xử lý.

## 9. Chặng 7 — Kiểm chứng năng lực qua một tình huống vận hành

**Toàn bộ sự kiện và số liệu trong tình huống dưới đây là giả định để thực hành.**

Dịch vụ xử lý tệp vừa triển khai `v3`. Người dùng báo chậm nhận kết quả. Health vẫn báo tốt và tỷ lệ HTTP nhận yêu cầu thành công vẫn cao.

### 9.1. Dùng từng lớp bằng chứng để thu hẹp vấn đề

| Bằng chứng giả định | Điều biết thêm | Điều chưa được kết luận |
| --- | --- | --- |
| Health vẫn tốt | Những kiểm tra hiện có chưa báo bất thường | Mọi tệp đều được xử lý đúng hạn |
| Thời gian trả lời HTTP gần như cũ | Bước nhận yêu cầu chưa chậm rõ | Toàn quy trình không bị chậm |
| Số công việc chờ và tuổi công việc tăng | Tắc nghẽn xuất hiện sau bước tiếp nhận | Thành phần cụ thể nào gây ra |
| Lỗi đầu ra không tăng, tỷ lệ đúng hạn giảm | Vấn đề nổi bật là thời hạn | Chỉ cần tăng tài nguyên là đủ |
| Nhật ký cho thấy công việc chờ lâu trước khi chạy | Có thể tập trung vào giai đoạn chờ | Mọi công việc đều có cùng nguyên nhân |
| Mốc tăng thời gian chờ gần lần triển khai `v3` | Có một thay đổi cần xem xét | `v3` chắc chắn là nguyên nhân duy nhất |

Sau đó, nhóm điều tra đặt giả thuyết: cấu hình số công việc xử lý đồng thời đã thay đổi. Bằng chứng cần tìm gồm cấu hình thực tế, số bộ xử lý đang hoạt động và phép thử dưới tải tương đương.

Giả sử thử nghiệm có kiểm soát cho thấy quay về cấu hình đã xác minh làm thời gian chờ giảm. Đây là bằng chứng ủng hộ giả thuyết. Vẫn cần ghi rõ điều kiện thử, những thay đổi xảy ra cùng lúc và giới hạn của kết luận.

### 9.2. Xác nhận phục hồi bằng kết quả người dùng

Sau hành động, hãy quan sát:

- Công việc cũ trong hàng đợi có được xử lý hết không?
- Công việc mới có đầu ra đúng trong thời hạn không?
- Có phát sinh lỗi hoặc xử lý trùng không?
- Đường thu thập dữ liệu có còn hoạt động trong lúc xử lý sự cố không?

Chỉ thấy tiến trình khởi động lại thành công chưa đủ để xác nhận hàng đợi đã trở về trạng thái bình thường.

### 9.3. Biến bài học thành cải thiện

Ghi lại phần dữ liệu đã hữu ích, phần bị thiếu và hành động nào cần được làm rõ. Nếu không đo được tuổi công việc chờ, hãy xác định cách bổ sung. Nếu cảnh báo chỉ theo HTTP, hãy xem xét bổ sung tín hiệu cho kết quả chạy nền.

Không cần bổ sung mọi công cụ sau mỗi sự cố. Ưu tiên thay đổi giúp trả lời một câu hỏi cụ thể, rồi kiểm chứng nó trong lần diễn tập sau.

**Đạt chặng khi:** bạn tái hiện được chuỗi “phát hiện → khoanh vùng → kiểm chứng → xử lý → xác nhận → cải thiện”, với bằng chứng và giới hạn rõ ràng.

## 10. Những điều cần giữ xuyên suốt lộ trình

### 10.1. Quyền truy cập phù hợp với mục đích

Chỉ công khai các điểm truy cập cần dùng, bảo vệ đường quản trị và giới hạn người có quyền đọc. Một số dữ liệu như cấu hình, bản chụp bộ nhớ hoặc nhật ký có thể chứa thông tin nhạy cảm.

Không chọn công khai toàn bộ Actuator làm cách mặc định để xử lý lỗi thiếu dữ liệu. Hãy xác định điểm truy cập, registry, quyền và đường thu thập đang thiếu ở đâu.

### 10.2. Dữ liệu đủ dùng và chi phí có kiểm soát

Lựa chọn nhãn số đo, mức ghi nhật ký, tỷ lệ lấy mẫu và thời hạn lưu theo nhu cầu điều tra. Thu nhiều dữ liệu hơn có thể làm tăng chi phí và ảnh hưởng tới ứng dụng.

Giữ các trường nhận diện dịch vụ, phiên bản và thời điểm nhất quán. Phân biệt dữ liệu không tồn tại với dữ liệu chưa tìm thấy vì sai bộ lọc, múi giờ hoặc quyền truy cập.

### 10.3. Kênh quan sát cũng có thể bị lỗi

Một biểu đồ ngừng thay đổi có thể do ứng dụng ít hoạt động, đường thu thập bị đứt hoặc truy vấn không còn khớp. Cần có bằng chứng về độ mới của dữ liệu và tình trạng bên thu thập.

Khi dùng cổng quản trị riêng, kiểm tra cả đường phục vụ người dùng. Khi tách nhiều tiến trình, không gộp số liệu mà làm mất danh tính cần cho điều tra.

### 10.4. Mỗi kết luận cần có phạm vi

Ghi rõ đang nói về một yêu cầu, một tiến trình, một nhóm công việc hay toàn dịch vụ; về một thời điểm hay một cửa sổ dài. Đây là cách tránh biến một phản hồi health, một dấu vết hoặc một đợt thử ngắn thành kết luận quá rộng.

## 11. Chọn điểm bắt đầu phù hợp với ứng dụng của bạn

| Bạn đang có | Việc thực hành kế tiếp có giá trị |
| --- | --- |
| Chưa đọc được health | Xác minh dependency, địa chỉ, điểm truy cập và quyền |
| Đọc được health nhưng chưa biết nó kiểm tra gì | Giải thích các thành phần và giới hạn của kết quả |
| Chỉ biết ứng dụng còn chạy | Phân biệt liveness/readiness và đo chất lượng phục vụ |
| Đã có số đo trong ứng dụng | Xác minh đường thu thập, lịch sử và độ mới |
| Có biểu đồ tài nguyên | Bổ sung câu hỏi và tín hiệu về kết quả nghiệp vụ |
| Thấy chỉ số xấu nhưng khó điều tra | Liên kết số đo với sự kiện, dấu vết và phiên bản |
| Có cảnh báo nhưng khó xử lý | Bổ sung người phụ trách, hướng dẫn và diễn tập |

Bảng này giúp chọn việc học dựa trên khoảng trống hiện tại. Bạn không cần chờ hoàn thiện mọi số đo mới viết nhật ký có ích, cũng không cần hệ thống phân tán mới bắt đầu đặt mục tiêu phục vụ.

### Bài tập kết thúc

Chọn một thao tác có thật của ứng dụng và viết một trang ghi chép:

1. Người dùng mong đợi kết quả nào, trong thời gian nào?
2. Health hiện tại kiểm tra điều gì liên quan tới thao tác ấy?
3. Một tín hiệu nào giúp nhận ra kết quả không đạt?
4. Dữ liệu đó được thu và lưu ở đâu, giữ được bao lâu?
5. Làm sao tìm một trường hợp bị ảnh hưởng và các bước xử lý của nó?
6. Ai hành động, hành động theo hướng dẫn nào và xác nhận phục hồi bằng gì?

Bạn đã đi xa hơn việc kiểm tra sức khỏe khi có thể dùng dữ liệu để trả lời các câu hỏi trên, rồi thử lại câu trả lời trong một tình huống có kiểm soát.
