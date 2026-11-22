# Vai trò của log, chỉ số đo lường (metrics) và dấu vết phân tán (traces)

## 1. Bắt đầu từ một yêu cầu bị chậm

Một ứng dụng bán hàng trả kết quả chậm. Người vận hành cần trả lời ba nhóm câu hỏi khác nhau:

- **Mức độ ảnh hưởng:** có bao nhiêu yêu cầu bị chậm, tỷ lệ lỗi tăng từ khi nào, hiện tượng xảy ra ở một máy hay nhiều máy?
- **Đường đi của một yêu cầu:** thời gian nằm ở ứng dụng nhận yêu cầu, lời gọi thanh toán hay bước truy vấn dữ liệu?
- **Sự kiện cụ thể:** bước xử lý nào thất bại, gặp lỗi gì, ứng dụng đã chọn nhánh xử lý nào?

**Chỉ số đo lường (metrics)** giúp nhìn xu hướng và phạm vi ảnh hưởng. **Dấu vết phân tán (traces)** giúp lần theo các công đoạn của một lần xử lý. **Nhật ký (logs)** cung cấp các sự kiện và chi tiết được ghi lại trong quá trình đó.

Khả năng dùng dữ liệu bên ngoài để hiểu trạng thái bên trong hệ thống được gọi là **khả năng quan sát (observability)**. Ba loại dữ liệu trên bổ sung cho nhau; chỉ thu thập thật nhiều dữ liệu chưa bảo đảm trả lời được câu hỏi vận hành. Trong Spring Boot, Micrometer Observation là nền tảng kết nối việc quan sát với metrics và tracing. Xem [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Bài này thuộc phần tổng quan Actuator: mục tiêu là biết mỗi nguồn dữ liệu giúp ích ở đâu, cách liên kết chúng và vai trò của Actuator. Việc triển khai đầy đủ hệ thống lưu trữ và giao diện giám sát là bước riêng.

## 2. Log: ghi lại sự kiện và ngữ cảnh

### 2.1. Một bản ghi log trả lời điều gì?

Log là bản ghi về một sự kiện. Một bản ghi hữu ích thường có thời điểm, mức độ, ứng dụng phát sinh, tên sự kiện và thông tin giúp giải thích sự kiện đó.

Ví dụ dưới đây là **dữ liệu minh họa tự đặt**, không phải định dạng đầu ra mặc định của Spring Boot:

~~~text
time=2026-11-04T10:00:01Z level=WARN service=checkout
event=payment.timeout provider=sandbox
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
~~~

Bản ghi cho biết ứng dụng checkout quan sát thấy hết thời gian chờ thanh toán với một nhà cung cấp thử nghiệm. Muốn biết có bao nhiêu người gặp hiện tượng này trong năm phút, vẫn cần đếm trên tập dữ liệu đầy đủ hoặc đối chiếu metrics. Một dòng log đơn lẻ chưa thể hiện quy mô sự cố.

Log có cấu trúc sử dụng các trường ổn định để công cụ tìm kiếm có thể lọc theo `event`, `service` hoặc mã truy vết. JSON là một cách biểu diễn; tính có cấu trúc còn phụ thuộc vào tên trường, kiểu dữ liệu và ý nghĩa nhất quán. Tham khảo [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

### 2.2. Mức độ log và chi tiết cần ghi

Một cách chọn mức độ trong ứng dụng:

| Mức độ | Ý nghĩa sử dụng trong ví dụ |
| --- | --- |
| `DEBUG` | Chi tiết phục vụ điều tra, chẳng hạn nhánh lựa chọn một phương án xử lý |
| `INFO` | Sự kiện thông thường có giá trị theo dõi, chẳng hạn hoàn tất một tác vụ |
| `WARN` | Bất thường cần chú ý nhưng hệ thống vẫn có thể tiếp tục hoặc khôi phục |
| `ERROR` | Thao tác thất bại cần được điều tra |

Đội phát triển cần thống nhất cách dùng mức độ. Số dòng `ERROR` không tự động bằng số yêu cầu HTTP thất bại: một yêu cầu có thể ghi nhiều lỗi, hoặc lỗi đã được xử lý thành một kết quả nghiệp vụ.

Với Spring Boot dùng starter mặc định, Logback là hệ thống ghi log thông dụng được cấu hình sẵn. Có thể dùng SLF4J trong mã ứng dụng:

~~~java
logger.info("event=checkout.accepted channel={}", channel);
~~~

Đây là câu lệnh nằm trong một phương thức, cần biến `logger` và `channel` đã được khai báo. Tham số `{}` giúp truyền giá trị theo cơ chế của thư viện ghi log. Khi cần ghi ngoại lệ, truyền cả đối tượng ngoại lệ để giữ thông tin ngăn xếp lời gọi:

~~~java
logger.error("event=checkout.failed", exception);
~~~

Cấu hình mức độ log ảnh hưởng tới những bản ghi thực sự được phát ra. Xem [Spring Boot 3.3 — Logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html).

### 2.3. Giá trị và giới hạn

Log phù hợp khi cần biết **đã xảy ra sự kiện gì** và **ngữ cảnh cụ thể là gì**. Tuy nhiên, điều chưa được ghi lại thường không thể khôi phục chỉ bằng việc tăng mức độ log sau sự cố.

Hãy ưu tiên sự kiện có ý nghĩa và các trường cần thiết. Không ghi mật khẩu, access token hoặc toàn bộ dữ liệu thanh toán. Mã đơn hàng hay thông tin người dùng cũng cần được xem xét theo mục đích, quyền truy cập và thời gian lưu giữ; chúng không mặc nhiên an toàn chỉ vì được gọi là “ngữ cảnh”.

## 3. Metrics: đo mức độ và xu hướng

### 3.1. Từ nhiều lần xử lý đến số liệu tổng hợp

Metrics biểu diễn các phép đo trong quá trình chạy, thường được tổng hợp và lưu theo thời gian. Ví dụ: số yêu cầu, số lỗi, lượng bộ nhớ đang sử dụng, thời gian xử lý.

Thông tin định danh một chuỗi số liệu thường gồm tên phép đo và các nhãn mô tả. Chẳng hạn cùng đo số yêu cầu nhưng tách theo phương thức HTTP hoặc trạng thái phản hồi. Khi xem số liệu, luôn xác định **đơn vị, khoảng thời gian và tập yêu cầu được tính**. Xem [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/).

Ba kiểu thường gặp trong Micrometer:

| Kiểu | Dùng để biết | Ví dụ |
| --- | --- | --- |
| `Counter` | Số lần một sự kiện được ghi nhận | Số lần chấp nhận một tác vụ |
| `Gauge` | Giá trị tại thời điểm quan sát | Số phần tử đang chờ trong hàng đợi |
| `Timer` | Số lần và tổng thời gian của các thao tác được đo | Số lần gọi và thời gian xử lý yêu cầu |

`Counter` nhận mức tăng dương; khi phân tích cần chú ý vòng đời tiến trình và việc khởi động lại. Tốc độ tăng trong một khoảng thời gian thường hữu ích hơn một tổng số tích lũy đứng riêng lẻ. Tham khảo [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

`Timer` đã cung cấp số lần đo và tổng thời gian, nên không cần thêm một counter chỉ để đếm lại đúng các sự kiện mà timer đã đo. Khả năng cung cấp phân vị hay histogram còn tùy cấu hình và hệ thống nhận dữ liệu. Tham khảo [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 3.2. Đọc số liệu đúng câu hỏi

Giả sử **trong cùng một cửa sổ năm phút**, một tuyến API có 1.000 yêu cầu đã hoàn tất, trong đó 20 phản hồi 5xx:

~~~text
Tỷ lệ 5xx = 20 / 1.000 = 2%
~~~

Mẫu số ở đây là tổng số yêu cầu trong cửa sổ đang xét, không phải tổng từ lúc ứng dụng khởi động. Cũng không nên tự đồng nhất tỷ lệ 5xx với mọi thất bại nghiệp vụ: một giao dịch bị từ chối có thể được biểu diễn bằng trạng thái khác tùy hợp đồng API.

Một ví dụ khác có mười thời gian xử lý, đơn vị mili giây:

~~~text
10, 10, 10, 10, 10, 10, 10, 10, 10, 910
Trung bình = 100 ms
~~~

Con số trung bình che khuất việc có một yêu cầu mất 910 ms. Khi quan tâm người dùng bị chậm, cần xem phân bố và các phân vị thích hợp. Chẳng hạn p95 mô tả ngưỡng bao phủ xấp xỉ 95% quan sát trong tập/cửa sổ được tính; nó không phải “95% của giá trị trung bình”. Cách ước lượng phụ thuộc công cụ và cấu hình.

Khi tổng hợp nhiều máy, hãy giữ đúng trọng số. Máy A có 100 yêu cầu, trung bình 10 ms; máy B có 900 yêu cầu, trung bình 110 ms. Trung bình toàn bộ là:

~~~text
(100 × 10 + 900 × 110) / 1.000 = 100 ms
~~~

Lấy trung bình đơn giản của 10 và 110 sẽ cho 60 ms và làm sai kết luận. Tương tự, không lấy trung bình p95 của các máy để gọi đó là p95 toàn hệ thống.

### 3.3. Giới hạn của metrics

Metrics giúp phát hiện tỷ lệ lỗi hoặc độ trễ đang tăng, nhưng một chuỗi đã tổng hợp thường không giữ toàn bộ câu chuyện của từng yêu cầu. Từ biểu đồ “2% lỗi” chưa thể kết luận lỗi do một câu SQL, một nhà cung cấp thanh toán hay một thay đổi cấu hình.

Đó là lúc chuyển sang trace hoặc log trong đúng khoảng thời gian có bất thường.

## 4. Trace: theo dõi một lần xử lý qua các công đoạn

### 4.1. Trace, span và mối quan hệ cha–con

Một **trace** mô tả một lần thực thi được theo dõi. Một **span** biểu diễn một công đoạn có thời điểm bắt đầu, kết thúc và ngữ cảnh liên quan.

`traceId` liên kết các span thuộc cùng trace; `spanId` định danh từng span. Quan hệ cha–con cho biết công đoạn nào được thực hiện trong ngữ cảnh của công đoạn khác. Trace vẫn hữu ích trong một ứng dụng đơn khối khi cần nhìn các bước nội bộ, không chỉ trong hệ thống nhiều dịch vụ. Xem [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Ví dụ cây trace giả định:

~~~text
checkout: xử lý HTTP                  800 ms
├── kiểm tra yêu cầu                  10 ms
├── gọi dịch vụ thanh toán           730 ms
│   └── payment: xử lý yêu cầu       700 ms
└── lưu kết quả                       40 ms
~~~

Các span cần được đo thực tế mới xuất hiện; cây trên minh họa cách đọc, không khẳng định Actuator tự tạo tất cả các bước đó.

Trong ví dụ, nên điều tra nhánh thanh toán trước vì chiếm phần lớn khoảng thời gian của yêu cầu. Chưa thể kết luận mã trong dịch vụ payment là nguyên nhân gốc: cần xem các span con, thông tin phụ thuộc và log tương ứng.

Không cộng mọi thời lượng trên cây. Span con nằm trong khoảng thời gian của span cha; các công đoạn cũng có thể chồng lấn khi chạy song song. Dòng “gọi dịch vụ thanh toán” và “payment: xử lý yêu cầu” không phải hai khoảng độc lập để cộng lại.

### 4.2. Vì sao cần truyền ngữ cảnh?

Dịch vụ nhận yêu cầu cần biết ngữ cảnh truy vết từ dịch vụ gọi nó. Việc **truyền ngữ cảnh (context propagation)** giúp nối các công đoạn thành cùng trace; với W3C Trace Context, ngữ cảnh được truyền qua header `traceparent`.

Khi một lời gọi không truyền hoặc không khôi phục đúng ngữ cảnh, bên nhận có thể bắt đầu một trace khác. Lúc đó dữ liệu vẫn tồn tại nhưng đường đi trông như bị tách đôi. Chuyển sang luồng khác hoặc xử lý bất đồng bộ cũng cần cơ chế truyền ngữ cảnh phù hợp. Xem [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

### 4.3. Trace có thể không chứa mọi yêu cầu

Lấy mẫu (sampling) lựa chọn một phần các trace để lưu/xuất, giúp kiểm soát chi phí. Không tìm thấy một trace chưa chứng minh yêu cầu đó chưa xảy ra: có thể không được chọn mẫu, thiếu đo đạc, xuất dữ liệu thất bại hoặc truy vấn sai khoảng thời gian.

Dấu vết phân tán cũng khác **stack trace của ngoại lệ**. Stack trace mô tả ngăn xếp lời gọi của một ngoại lệ; distributed trace mô tả các công đoạn của một lần thực thi và có thể tồn tại dù không có ngoại lệ.

## 5. Liên kết ba nguồn dữ liệu

### 5.1. Chọn nguồn theo câu hỏi

| Câu hỏi | Bắt đầu từ | Bổ sung tiếp |
| --- | --- | --- |
| Tỷ lệ lỗi tăng từ lúc nào, ảnh hưởng bao nhiêu yêu cầu? | Metrics | Trace/log trong cửa sổ bất thường |
| Một yêu cầu chậm ở công đoạn nào? | Trace | Log của công đoạn đáng nghi |
| Vì sao ứng dụng chọn nhánh từ chối thanh toán? | Log có ngữ cảnh nghiệp vụ | Trace và metrics để kiểm tra ảnh hưởng |
| Sau khi sửa, tình trạng toàn hệ thống đã cải thiện chưa? | Metrics | Kiểm tra thêm trace và log đại diện |

Đây là cách bắt đầu hợp lý theo câu hỏi, không phải thứ tự cố định cho mọi cuộc điều tra. Nếu người dùng đã cung cấp một mã truy vết, có thể mở trace đó trước.

### 5.2. Một tình huống điều tra hoàn chỉnh

Giả sử biểu đồ checkout báo tỷ lệ 5xx tăng từ 0,2% lên 2% sau 10:00. Quy trình điều tra có thể là:

1. **Khoanh phạm vi bằng metrics:** kiểm tra tuyến API, phiên bản ứng dụng, thời điểm và máy bị ảnh hưởng. So sánh trên cùng cửa sổ và cùng tập yêu cầu.
2. **Xem các trace chậm/lỗi:** trong những trace được lưu, nhiều trace có nhánh thanh toán kéo dài gần thời hạn chờ. Đây là manh mối để kiểm tra nhánh này.
3. **Tìm log theo traceId:** các log liên quan ghi nhận hết thời gian chờ khi gọi cùng nhà cung cấp thử nghiệm.
4. **Kiểm chứng giả thuyết:** đối chiếu cấu hình, log bên nhận, tình trạng mạng và thay đổi triển khai. Chỉ sự trùng thời điểm chưa đủ chứng minh quan hệ nhân quả.
5. **Đánh giá sau xử lý:** theo dõi tỷ lệ lỗi và phân bố độ trễ, rồi kiểm tra thêm các yêu cầu đại diện.

Một log timeout chỉ cho biết phía ghi log quan sát thấy hết thời gian chờ. Nó chưa xác định chắc chắn bên nhận đã xử lý hay chưa; cũng chưa đủ để quyết định thử lại một giao dịch có thể tạo tác dụng phụ.

### 5.3. Liên kết không có nghĩa đưa traceId vào mọi nhãn

Nếu log được ghi khi một span đang hoạt động, thư viện tracing có thể đặt `traceId` và `spanId` vào MDC — vùng ngữ cảnh dùng cho log. Spring Boot 3.3 hỗ trợ hiển thị mã liên kết này khi sử dụng Micrometer Tracing. Ngoài ngữ cảnh đang hoạt động, các mã có thể không xuất hiện. Mối liên hệ giữa log và trace được giải thích trong [Spring — Observability with Spring Boot 3](https://spring.io/blog/2022/10/12/observability-with-spring-boot-3/).

Để tự động truyền trace qua HTTP trong Spring Boot, nên tạo client từ các builder được tự cấu hình như `RestClient.Builder`, `RestTemplateBuilder` hoặc `WebClient.Builder`. Một client tự tạo bằng cách khác không mặc nhiên có cùng cơ chế đo đạc. Xem [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Spring Boot 3.3 mặc định lấy mẫu tracing với xác suất 0,1. Thuộc tính `management.tracing.sampling.probability` nhận giá trị từ 0 đến 1; cấu hình thử nghiệm dưới đây dùng 1,0. Xem [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

## 6. Actuator và Micrometer đứng ở đâu?

### 6.1. Tách vai trò của các thành phần

Trong một ứng dụng Spring Boot, có thể hình dung luồng dữ liệu như sau:

~~~text
Mã ứng dụng / thư viện được gắn cơ chế quan sát
├── Logger → console hoặc tệp → hệ thống thu thập log
└── ObservationRegistry
    ├── bộ xử lý metrics → MeterRegistry → hệ thống metrics
    └── bộ xử lý tracing → tracer/exporter → hệ thống traces
~~~

**Gắn cơ chế đo đạc (instrumentation)** là tạo điểm ghi nhận sự kiện, phép đo hoặc công đoạn trong mã/thư viện. **Exporter** chuyển dữ liệu sang nơi nhận; hệ thống lưu trữ giữ dữ liệu để tìm kiếm và phân tích.

Với Micrometer Observation, các bộ xử lý nhận thông báo theo vòng đời observation. Một điểm quan sát có thể phục vụ cả đo thời gian lẫn tạo span khi các bộ xử lý tương ứng được cấu hình. Việc tạo observation không tự viết thay mọi log nghiệp vụ. Xem [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

Actuator cung cấp các khả năng vận hành và hỗ trợ tự cấu hình tích hợp. Nó không thay thế toàn bộ hệ thống lưu trữ, tìm kiếm hoặc giao diện giám sát:

| Khả năng | Ý nghĩa |
| --- | --- |
| `/actuator/metrics` | Khám phá và xem phép đo đang được ứng dụng ghi nhận |
| `/actuator/prometheus` | Cung cấp metrics ở định dạng Prometheus khi có registry và đã mở endpoint |
| Tích hợp Micrometer Tracing | Hỗ trợ tạo/xuất trace khi có thư viện và cấu hình tương ứng |
| Logger của ứng dụng | Phát các sự kiện mà mã ứng dụng/thư viện thực sự ghi |

Spring Boot có thể đo các yêu cầu HTTP thành `http.server.requests`. Không nên coi `/actuator/metrics` là kho lịch sử của toàn bộ hệ thống. Hệ thống metrics bên ngoài mới đảm nhiệm lưu chuỗi theo thời gian khi được triển khai tương ứng. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 6.2. Chọn nhãn để dữ liệu vẫn sử dụng được

**Số lượng tổ hợp giá trị nhãn (cardinality)** ảnh hưởng tới số chuỗi số liệu cần theo dõi. Ví dụ cùng một phép đo có 2 phương thức, 3 kết quả và 4 tuyến đường có thể tạo tới 24 tổ hợp, trước khi xét thêm máy hay môi trường.

Nếu mỗi yêu cầu thêm một `traceId` khác nhau vào nhãn metrics, số tổ hợp sẽ tiếp tục tăng theo số yêu cầu. Với bài toán phát hiện lỗi theo tuyến API, hãy dùng nhãn ổn định như mẫu đường dẫn `/orders/{id}` thay vì từng đường dẫn `/orders/78421`.

Trong Micrometer Observation:

- **Low-cardinality key values** dành cho tập giá trị được kiểm soát, có thể đi vào metrics và traces.
- **High-cardinality key values** dành cho giá trị biến thiên lớn, đi vào traces thay vì trở thành nhãn metrics theo cơ chế observation thông thường.

Ví dụ, `channel=web/mobile` là ứng viên nhãn ít giá trị; mã từng đơn hàng không phù hợp làm nhãn metrics. Dù chỉ lưu vào trace hoặc log, dữ liệu vẫn cần được xem xét về chi phí và quyền riêng tư. Tham khảo [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 7. Minh họa trong Spring Boot 3.3.x

Ví dụ tạo một điểm quan sát nghiệp vụ, ghi log bên trong điểm quan sát và xem phép đo của nó. Ví dụ chạy **trong một dự án Spring Boot 3.3.x có cấu hình Gradle, quản lý phiên bản dependency và tác vụ bootRun sẵn có**, dùng JDK 17 trở lên. Đoạn dependencies dưới đây là phần ghép vào dự án, không phải toàn bộ build.gradle.

### 7.1. Dependency và cấu hình tối thiểu để xem log/metrics

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Trong `src/main/resources/application.yml` của dự án thử nghiệm:

~~~yaml
spring:
  application:
    name: checkout-demo

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Ví dụ giả định chạy cục bộ ở cổng 8080, không có Spring Security, không đổi context path hoặc management port. Chỉ mở những endpoint cần dùng trong môi trường thử nghiệm; việc mở endpoint qua HTTP và việc cấp quyền truy cập là hai vấn đề riêng. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 7.2. Một tệp Java đầy đủ

Đặt tệp tại `src/main/java/example/observation/ObservabilityDemoApplication.java`:

~~~java
package example.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ObservabilityDemoApplication {
    private static final Logger logger =
            LoggerFactory.getLogger(ObservabilityDemoApplication.class);

    private final ObservationRegistry registry;

    public ObservabilityDemoApplication(ObservationRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/demo/checkout")
    public String checkout() {
        return Observation.createNotStarted("shop.checkout", registry)
                .lowCardinalityKeyValue("channel", "web")
                .observe(() -> {
                    logger.info("event=checkout.accepted channel=web");
                    return "ACCEPTED";
                });
    }

    public static void main(String[] args) {
        SpringApplication.run(ObservabilityDemoApplication.class, args);
    }
}
~~~

Phương thức chỉ mô phỏng việc chấp nhận một thao tác, không gọi ngân hàng hoặc tạo giao dịch thật.

Lệnh `observe` bao quanh phần công việc được đo. Tên `shop.checkout` là tên phép quan sát ổn định, `channel=web` là thông tin ít giá trị. Log được ghi ngay trong phạm vi quan sát. HTTP request bao ngoài và thao tác nghiệp vụ bên trong là hai phạm vi khác nhau; không cộng số lần của chúng thành một tổng số giao dịch.

### 7.3. Chạy và đọc bằng chứng

Trong thư mục dự án thử nghiệm, chạy bằng Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Ở một cửa sổ khác:

~~~powershell
curl.exe --silent http://localhost:8080/demo/checkout
~~~

Body phản hồi dự kiến chính xác là:

~~~text
ACCEPTED
~~~

Console có một thông điệp chứa `event=checkout.accepted channel=web`. Toàn bộ dòng log còn phụ thuộc thời gian, luồng và định dạng nên không cố định.

Sau khi gọi API hoàn tất, xem phép đo:

~~~powershell
curl.exe --silent http://localhost:8080/actuator/metrics/shop.checkout
~~~

Kết quả JSON dự kiến có tên `shop.checkout` và các phép đo thời gian/số lần. Giá trị thời gian thay đổi theo lần chạy; số lần cũng tăng nếu gọi lại. Có thể đối chiếu phép đo HTTP bao ngoài bằng:

~~~powershell
curl.exe --silent "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/demo/checkout"
~~~

Dùng `curl.exe` giúp tránh nhầm với alias `curl` trong một số phiên bản Windows PowerShell. Các lệnh trên là hướng dẫn chạy trong dự án đáp ứng điều kiện đã nêu; một tệp Java riêng lẻ không thể chạy bằng `javac` nếu thiếu classpath Spring/Micrometer.

### 7.4. Bổ sung tracing để thấy công đoạn nghiệp vụ

Để nối ví dụ với một hệ thống trace, thêm một cặp bridge/exporter tương thích. Ví dụ dùng OpenTelemetry và Zipkin:

~~~groovy
dependencies {
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

Bổ sung vào khóa `management` **đã có**, giữ nguyên cấu hình endpoints:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

Địa chỉ nhận Zipkin và thuộc tính sampling được liệt kê trong [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Đoạn YAML này mô tả phần cần ghép, không được tạo hai khóa `management` trùng nhau trong cùng một tài liệu. Cần chạy Zipkin tại địa chỉ trên để nhận dữ liệu, rồi khởi động lại ứng dụng và gọi lại API. Đây là cấu hình thử nghiệm nhỏ với sampling 100%.

Khi dữ liệu được xuất thành công, có thể tìm trace chứa công đoạn nghiệp vụ tương ứng `shop.checkout` trong ngữ cảnh HTTP của lời gọi. Tên hiển thị của span có thể được chuẩn hóa theo thư viện. Không cần tạo endpoint `/actuator/traces` để xem chúng; hãy dùng hệ thống nhận trace đã cấu hình. Cách kết hợp dependency/exporter này được mô tả trong [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Nếu chỉ thêm Actuator và chạy phần log/metrics ở trên, chưa có đủ cấu hình để lưu và xem distributed traces trong Zipkin. Nếu cần trace chi tiết tới SQL, lời gọi bên ngoài hoặc một tác vụ nền, từng đường đi đó phải được thư viện hỗ trợ hoặc được gắn điểm quan sát phù hợp.

## 8. Lỗi hiểu sai và cách tự kiểm tra

| Cách hiểu dễ sai | Cách kiểm tra lại |
| --- | --- |
| Có nhiều log thì chắc chắn hiểu toàn hệ thống | Xác định log có đủ ngữ cảnh và có số liệu về phạm vi ảnh hưởng hay chưa |
| Không có ERROR nghĩa là không có lỗi | Kiểm tra quy ước ghi log, mức lọc, kết quả API và metrics |
| Trung bình thấp nghĩa là mọi yêu cầu đều nhanh | Xem phân bố, các yêu cầu chậm và cửa sổ tính |
| Trace dài nhất chỉ ngay nguyên nhân gốc | Đối chiếu nhánh con, log và phụ thuộc; thời gian là manh mối |
| Có traceId trong log thì chắc chắn tìm được trace đã lưu | Kiểm tra sampling, xuất dữ liệu, thời gian truy vấn và thời gian lưu |
| Bật Actuator là tự có toàn bộ traces, log tập trung và giao diện | Kiểm tra riêng cơ chế đo đạc, thư viện tích hợp và nơi nhận từng nguồn |
| Đưa mã từng yêu cầu vào nhãn metrics để tìm cho tiện | Dùng mã ở log/trace khi phù hợp; giữ nhãn metrics có số tổ hợp được kiểm soát |

### Tự thực hành

1. Chỉ có dữ kiện “20 lỗi trong năm phút”. Hãy nêu thông tin còn thiếu để tính tỷ lệ lỗi.
2. Một API chậm nhưng không phát sinh ngoại lệ. Chọn dữ liệu để phát hiện và dữ liệu để tìm công đoạn chậm.
3. Log có traceId nhưng không tìm thấy trace. Nêu ít nhất hai giả thuyết và cách kiểm chứng.
4. Trong ví dụ Spring Boot, gọi endpoint nghiệp vụ ba lần. Đọc phép đo `shop.checkout`, tìm các log tương ứng và, nếu đã cấu hình tracing, đối chiếu trong hệ thống trace.
5. Giải thích vì sao `channel` có tập giá trị nhỏ phù hợp làm nhãn metrics hơn `orderId`.

**Gợi ý đối chiếu:** câu 1 cần tổng yêu cầu trong cùng cửa sổ và định nghĩa lỗi; câu 2 có thể bắt đầu từ metrics độ trễ rồi xem trace; câu 3 kiểm tra sampling, đường xuất và truy vấn; câu 4 phân biệt số lần nghiệp vụ với các HTTP request khác; câu 5 xét số tổ hợp nhãn thay vì chỉ xét tên trường.
