# Phân biệt khả năng quan sát, giám sát và chẩn đoán sự cố

Một ứng dụng Spring Boot vẫn chạy, `/actuator/health` trả về `UP`, nhưng người dùng phải chờ rất lâu để thanh toán. Khi đó cần trả lời ba nhóm câu hỏi khác nhau: dịch vụ có đang đáp ứng yêu cầu không; có đủ dữ liệu để tìm hiểu điều đang diễn ra không; và bằng chứng nào giải thích được sự chậm trễ?

Bài này giúp bạn phân biệt **khả năng quan sát (observability)**, **giám sát (monitoring)** và **chẩn đoán sự cố (diagnosis/troubleshooting)**, rồi đặt Spring Boot Actuator vào đúng vai trò. Hãy học theo thứ tự: hiểu ba khái niệm → nhận diện dữ liệu → theo dõi một tình huống → thực hành đọc tín hiệu.

## 1. Ba khái niệm nhìn vào cùng một hệ thống

### 1.1. Khả năng quan sát: có thể hiểu điều gì từ dữ liệu bên ngoài?

Khả năng quan sát là khả năng suy luận về trạng thái và hành vi bên trong hệ thống thông qua dữ liệu mà hệ thống phát ra. Giá trị thực tế nằm ở việc đặt được câu hỏi mới khi có vấn đề, kể cả câu hỏi chưa có sẵn trên bảng theo dõi.

Ví dụ: “Vì sao chỉ các yêu cầu thanh toán qua đối tác A trên phiên bản mới bị chậm, trong khi đối tác B vẫn bình thường?” Muốn trả lời, dữ liệu phải có đủ ngữ cảnh để phân biệt thao tác, phiên bản, đối tác và đường đi của yêu cầu. Khái niệm này được giải thích trong [OpenTelemetry Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/).

Khả năng quan sát là một **năng lực của hệ thống cùng cách khai thác dữ liệu**. Cài một thư viện hoặc thu thật nhiều dữ liệu chưa đủ để chứng minh năng lực ấy. Nếu không nối được các sự kiện liên quan hoặc không truy vấn được thời điểm xảy ra lỗi, người vận hành vẫn khó trả lời câu hỏi.

### 1.2. Giám sát: theo dõi dịch vụ theo mục tiêu và quy tắc

Giám sát là hoạt động thu thập, theo dõi và đánh giá dữ liệu để biết hệ thống đang vận hành như thế nào. Bảng theo dõi, kiểm tra định kỳ và cảnh báo là những cách triển khai thường gặp.

Một quy tắc ví dụ: “Cảnh báo khi tỷ lệ yêu cầu thanh toán thất bại vượt 2% trong 5 phút, với ít nhất 100 yêu cầu.” Đây là quy tắc minh họa; ngưỡng thực tế phụ thuộc mục tiêu dịch vụ và lưu lượng.

Giám sát có thể dùng số đo, nhật ký, dấu vết hoặc kiểm tra từ bên ngoài. Nó cũng hỗ trợ phân tích xu hướng và lập kế hoạch, không chỉ phát cảnh báo. [Google SRE mô tả giám sát](https://sre.google/sre-book/monitoring-distributed-systems/) qua việc thu thập, xử lý, tổng hợp và hiển thị dữ liệu; đồng thời phân biệt triệu chứng người dùng gặp với nguyên nhân bên trong.

### 1.3. Chẩn đoán sự cố: giải thích vấn đề bằng giả thuyết và bằng chứng

Chẩn đoán sự cố là quá trình xác định vấn đề, thu hẹp phạm vi, đặt giả thuyết và kiểm chứng để tìm lời giải thích có cơ sở. Quá trình này có thể bắt đầu từ cảnh báo tự động, phản ánh của người dùng hoặc một dấu hiệu bất thường khi thử tải.

Ví dụ: “Có phải thời gian chờ lấy kết nối cơ sở dữ liệu làm thanh toán chậm?” Cần tìm dữ liệu xác nhận hoặc bác bỏ giả thuyết ấy. Một biểu đồ tăng cùng thời điểm chưa đủ để kết luận nguyên nhân.

Chẩn đoán là **hoạt động suy luận và điều tra**. Dữ liệu tốt giúp làm việc đó hiệu quả hơn, nhưng công cụ không tự bảo đảm kết luận đúng. Cách tiếp cận đặt giả thuyết rồi kiểm chứng được trình bày trong [Google SRE — Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/).

### 1.4. Bảng phân biệt

| Góc nhìn | Khả năng quan sát | Giám sát | Chẩn đoán sự cố |
| --- | --- | --- | --- |
| Bản chất | Năng lực hiểu hệ thống qua dữ liệu | Hoạt động theo dõi và đánh giá vận hành | Quá trình điều tra và giải thích vấn đề |
| Câu hỏi tiêu biểu | Có thể truy tìm điều gì đã xảy ra và trong ngữ cảnh nào? | Điều gì đang bất thường so với mục tiêu? | Giả thuyết nào được bằng chứng ủng hộ? |
| Ví dụ trong bài | Nối được phiên bản, đối tác và đường đi của yêu cầu | Phát hiện tỷ lệ lỗi vượt ngưỡng | Kiểm chứng việc chờ kết nối gây chậm |
| Kết quả hữu ích | Dữ liệu đủ ngữ cảnh và có thể truy vấn | Xu hướng, trạng thái, cảnh báo | Phạm vi ảnh hưởng, lời giải thích, hành động và kiểm tra lại |

Ba khái niệm bổ trợ nhau. Một hệ thống có thể phát cảnh báo tốt nhưng thiếu dữ liệu để điều tra. Ngược lại, dữ liệu có thể rất phong phú nhưng chưa có quy tắc phát hiện kịp thời. Chẩn đoán vẫn cần người hoặc cơ chế phân tích sử dụng dữ liệu một cách có phương pháp.

## 2. Dữ liệu nào giúp trả lời câu hỏi nào?

Dữ liệu vận hành thường được gọi chung là **dữ liệu đo đạc và sự kiện (telemetry)**. Trong bài này, ta tập trung vào số đo, nhật ký và dấu vết.

### 2.1. Số đo: nhìn quy mô và xu hướng

**Số đo (metric)** biểu diễn các đại lượng như số yêu cầu, thời gian xử lý hoặc mức sử dụng bộ nhớ. Cần đọc chúng cùng đơn vị, khoảng thời gian và các chiều phân loại.

Các câu hỏi minh họa:

- Có bao nhiêu yêu cầu thanh toán mỗi giây?
- Tỷ lệ thất bại trong 5 phút gần nhất là bao nhiêu?
- Độ trễ p95 của từng thao tác thay đổi ra sao sau khi triển khai?

p95 là phân vị 95 của phân bố độ trễ: xấp xỉ 95% quan sát nằm ở hoặc dưới giá trị đó, tùy phương pháp ước lượng. Nó không phải giá trị trung bình. Cần biết số mẫu và cửa sổ thời gian để diễn giải. Đọc thêm [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/).

**Ví dụ tính toán do bài học đặt ra:** trong một cửa sổ có 200 yêu cầu đủ điều kiện, 10 yêu cầu thất bại:

```text
Tỷ lệ thất bại = 10 / 200 × 100% = 5%
```

Con số này nói về tập yêu cầu đã xác định. Nó chưa cho biết yêu cầu nào thất bại, nguyên nhân là gì hoặc toàn bộ người dùng có bị ảnh hưởng như nhau không.

### 2.2. Nhật ký: nhìn một sự kiện cụ thể

**Nhật ký (log)** ghi lại sự kiện với thời điểm và ngữ cảnh. Một bản ghi có cấu trúc giúp tìm kiếm theo trường dữ liệu thay vì phụ thuộc hoàn toàn vào việc đọc chuỗi văn bản.

Bản ghi sau là **dữ liệu giả định**, tên trường do ứng dụng tự chọn:

```json
{
  "timestamp": "2026-01-10T09:02:15Z",
  "level": "WARN",
  "service": "checkout",
  "version": "v2",
  "event": "payment_timeout",
  "provider": "A",
  "traceId": "0123456789abcdef0123456789abcdef",
  "spanId": "0123456789abcdef",
  "timeoutMs": 2000
}
```

Nó cho biết ứng dụng đã ghi nhận sự kiện hết thời gian chờ với đối tác A trong ngữ cảnh đó. Nó chưa chứng minh máy chủ của đối tác A bị lỗi: thời gian có thể bị tiêu tốn ở nhiều vị trí trên đường đi.

Nhật ký có thể gắn với dấu vết qua mã định danh. Tuy nhiên, không phải mọi bản ghi đều có ngữ cảnh yêu cầu; việc thu thập và liên kết cần được thiết lập. Xem [OpenTelemetry — Logs](https://opentelemetry.io/docs/concepts/signals/logs/).

### 2.3. Dấu vết: nhìn đường đi của một yêu cầu

**Dấu vết phân tán (distributed trace)** mô tả đường đi của một yêu cầu qua các thao tác đã được gắn cơ chế thu thập. Mỗi **span** biểu diễn một đơn vị công việc có thời gian và quan hệ với các span khác.

Ví dụ có thể theo từ yêu cầu thanh toán đến bước kiểm tra giỏ hàng rồi lời gọi đối tác. Cần đọc cả quan hệ lồng nhau và phần chạy song song; không cộng tùy ý mọi thời lượng span để suy ra tổng thời gian. Xem [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Nếu một bước chưa được gắn cơ chế thu thập, dấu vết có thể không thể hiện chi tiết bước đó. Thấy một lời gọi phía máy khách kéo dài chỉ xác định được khu vực cần điều tra thêm; muốn biết điều gì xảy ra trong hệ thống đích, cần bằng chứng tương ứng ở phía đó.

### 2.4. Kết hợp tín hiệu theo câu hỏi

| Câu hỏi trong tình huống thanh toán | Dữ liệu bắt đầu phù hợp | Cần bổ sung để đi sâu |
| --- | --- | --- |
| Có bao nhiêu yêu cầu chậm? | Số đo theo thao tác và cửa sổ thời gian | Phân bố, lưu lượng, phiên bản |
| Sự kiện nào xảy ra với một yêu cầu? | Nhật ký có ngữ cảnh | Mã dấu vết, thông tin bước xử lý |
| Thời gian nằm ở bước nào? | Dấu vết của yêu cầu được lưu | Chi tiết của bước nghi vấn |
| Các luồng JVM đang chờ ở đâu? | Bản chụp trạng thái luồng | Nhiều thời điểm và ngữ cảnh tải |
| Cách sửa có cải thiện dịch vụ không? | So sánh chỉ số trước và sau | Lưu lượng và điều kiện tương đương |

Một trường định danh riêng cho từng yêu cầu rất hữu ích khi tìm nhật ký hoặc dấu vết, nhưng thường không phù hợp làm nhãn cho số đo vì có quá nhiều giá trị khác nhau. Trong mô hình Observation của Spring Boot, thuộc tính có ít giá trị được đưa vào số đo và dấu vết, còn thuộc tính có nhiều giá trị chỉ được đưa vào dấu vết. Xem [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Ngoài khả năng truy vấn, cần quan tâm dữ liệu có được giữ đủ lâu và có còn đầy đủ hay không. Cơ chế lấy mẫu có thể chỉ giữ một phần dấu vết. Vì vậy, không tìm thấy dấu vết của một yêu cầu không đồng nghĩa yêu cầu chưa từng xảy ra. Xem [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/).

## 3. Actuator đứng ở đâu?

Trong Spring Boot, Actuator cung cấp các điểm truy cập phục vụ vận hành và hỗ trợ tích hợp thu thập dữ liệu. Với số đo, Spring Boot tích hợp Micrometer; các hệ thống bên ngoài đảm nhiệm việc thu thập, lưu trữ và khai thác theo cấu hình đã chọn. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Một cách hình dung luồng dữ liệu:

```text
Ứng dụng Spring Boot đang chạy
  ├─ Trạng thái và điểm truy cập Actuator
  ├─ Số đo qua Micrometer
  ├─ Nhật ký từ ứng dụng
  └─ Dấu vết khi có tích hợp tương ứng
                ↓
       Thu thập / xuất dữ liệu
                ↓
       Lưu trữ và truy vấn
                ↓
       Giám sát / điều tra
```

Các nhánh có thể đi qua những đường thu thập khác nhau. Ví dụ, nhật ký có thể được lấy từ đầu ra của tiến trình, trong khi số đo được hệ thống giám sát định kỳ đọc.

### 3.1. Vai trò của một số điểm truy cập

| Điểm truy cập mặc định | Giá trị chính |
| --- | --- |
| `/actuator/health` | Đọc trạng thái sức khỏe từ các thành phần kiểm tra đã cấu hình |
| `/actuator/metrics` | Khám phá và kiểm tra các số đo đang được đăng ký trong ứng dụng |
| `/actuator/prometheus` | Cung cấp số đo theo định dạng để Prometheus thu thập; cần thư viện registry tương ứng |
| `/actuator/threaddump` | Lấy trạng thái các luồng để hỗ trợ điều tra |
| `/actuator/loggers` | Đọc và thay đổi cấu hình mức ghi nhật ký |

Trong Spring Boot 3.3, mặc định chỉ `health` được công khai qua HTTP. Việc một điểm truy cập tồn tại, được bật, được công khai và được phép truy cập là những điều cần kiểm tra riêng. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html). Đường dẫn và cổng còn phụ thuộc cấu hình ứng dụng, được mô tả trong [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 3.2. Đọc đúng giới hạn của từng công cụ

**Health trả `UP`:** kết quả này phản ánh các phép kiểm tra sức khỏe đã được cấu hình tại thời điểm kiểm tra. Nó không trực tiếp đo việc người dùng hoàn thành thanh toán đúng, nhanh hay chậm. Với ví dụ đầu bài, phép kiểm tra kết nối đơn giản có thể thành công trong khi truy vấn nghiệp vụ vẫn chậm. Có thể xem cấu trúc kết quả ở [Health REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

**Metrics có dữ liệu:** có thể kiểm tra ứng dụng đã đăng ký gì và giá trị hiện tại ra sao. API `metrics` phục vụ kiểm tra số đo, không được thiết kế làm kho dữ liệu giám sát trong môi trường vận hành. Lưu lịch sử và truy vấn dài hạn cần hệ thống phù hợp ở ngoài ứng dụng. Xem [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

**Có Actuator:** chưa có nghĩa mọi yêu cầu đều có dấu vết được xuất và lưu. Cần cấu hình bộ tạo dấu vết (tracer), đường xuất dữ liệu và hệ thống tiếp nhận. Spring Boot cung cấp tích hợp Micrometer Tracing cho mục đích này. Xem [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Như vậy, Actuator hỗ trợ tạo và truy cập bằng chứng ở phía ứng dụng. Việc đánh giá tình trạng dịch vụ và tìm nguyên nhân còn phụ thuộc dữ liệu đã thu thập, cách liên kết và quá trình điều tra.

## 4. Đi qua một tình huống hoàn chỉnh

**Toàn bộ tên dịch vụ, thời điểm, số liệu và bằng chứng trong mục này là giả định để học cách suy luận.**

### 4.1. Bước phát hiện: nhận ra ảnh hưởng tới người dùng

Dịch vụ `checkout` vừa triển khai phiên bản `v2`. Nhóm vận hành thấy dữ liệu cho cùng một cửa sổ 5 phút:

| Quan sát giả định | Trước triển khai | Sau triển khai |
| --- | --- | --- |
| Số yêu cầu đủ điều kiện | 200 | 200 |
| Số yêu cầu thất bại | 0 | 10 |
| Tỷ lệ thất bại | 0% | 5% |
| Độ trễ p95 | 300 ms | 2.000 ms |
| Health của các phiên bản đang chạy | `UP` | `UP` |

Quy tắc tỷ lệ lỗi đã nêu ở phần 1 sẽ thỏa điều kiện trên dữ liệu sau triển khai. Đây là ví dụ về **giám sát phát hiện triệu chứng**.

Chưa được kết luận rằng `v2` là nguyên nhân chỉ vì hai việc xảy ra gần nhau. Cần xem hệ thống ngoài, tải và các thay đổi khác trong cùng thời điểm.

### 4.2. Bước truy vấn: dùng năng lực quan sát để tách nhóm

Giả sử dữ liệu có đủ các trường `version`, `provider` và tên thao tác, ta phân nhóm được 200 yêu cầu sau triển khai:

| Nhóm giả định | Tổng yêu cầu | Thất bại | Tỷ lệ thất bại |
| --- | --- | --- | --- |
| `v2`, đối tác A | 50 | 10 | 20% |
| `v2`, đối tác B | 150 | 0 | 0% |

Thông tin mới thu hẹp ảnh hưởng tới nhóm dùng A. Đó là giá trị của **khả năng quan sát**: không chỉ thấy một chỉ số tổng, mà có thể đặt thêm câu hỏi với ngữ cảnh sẵn có.

Nếu dữ liệu chỉ có “toàn hệ thống lỗi 5%”, nhóm vận hành không thể tự suy ra bảng phân nhóm này. Một câu hỏi chưa thể trả lời là dấu hiệu cần cải thiện cơ chế thu thập cho lần sau.

### 4.3. Bước chẩn đoán: tránh nhảy từ dấu hiệu sang nguyên nhân

Nhóm điều tra đưa ra ba giả thuyết:

| Giả thuyết | Bằng chứng cần tìm |
| --- | --- |
| Đối tác A xử lý chậm | Thời gian phía máy khách và dữ liệu tương ứng của đối tác |
| Ứng dụng chờ lấy kết nối HTTP tới A | Thời gian chờ kết nối, số kết nối đang dùng/chờ và trạng thái luồng |
| Công đoạn nội bộ trước khi gọi A bị chậm | Thời lượng từng bước hoặc phép đo bổ sung ở công đoạn đó |

Giả sử một dấu vết được giữ lại cho thấy thời gian tập trung ở lời gọi tới A. Nhật ký ghi `payment_timeout`. Hai dữ kiện ấy chưa phân biệt được “A xử lý chậm” với “ứng dụng chờ tài nguyên trước khi gửi”.

Tiếp tục điều tra, nhóm tìm thấy **bằng chứng giả định bổ sung**:

1. Phép đo riêng của máy khách cho thấy phần lớn thời gian nằm ở bước chờ lấy kết nối.
2. Số kết nối đang dùng chạm giới hạn, đồng thời xuất hiện nhiều yêu cầu chờ.
3. Cấu hình của `v2` giảm giới hạn kết nối dành riêng cho A.
4. Trong thử nghiệm có kiểm soát, giữ tải tương đương và khôi phục cấu hình cũ làm thời gian chờ giảm.

Lúc này, giả thuyết về giới hạn kết nối được ủng hộ rõ hơn. Kết luận phải ghi phạm vi bằng chứng và những điều còn chưa biết; không biến một phép thử thành khẳng định tuyệt đối cho mọi trường hợp.

### 4.4. Bước xử lý và kiểm tra lại

Một hành động giảm ảnh hưởng có thể là quay về cấu hình đã hoạt động ổn định, theo quy trình triển khai của nhóm. Sau đó cần kiểm tra:

- Tỷ lệ thành công và độ trễ của nhóm dùng A có trở lại mức mong đợi không?
- Có lỗi mới hoặc ảnh hưởng sang nhóm dùng B không?
- Điều kiện tải có đủ tương đương để so sánh không?
- Cần thêm cảnh báo hoặc dữ liệu nào để phát hiện và điều tra sớm hơn?

**Giảm ảnh hưởng** và **xác nhận nguyên nhân** là hai kết quả cần ghi rõ. Khởi động lại làm hệ thống tạm ổn có thể hữu ích, nhưng riêng kết quả đó chưa giải thích được vì sao vấn đề xảy ra.

## 5. Thực hành đọc Actuator trên ứng dụng có sẵn

Mục này dùng một ứng dụng web Spring Boot 3.3 có sẵn `spring-boot-starter-actuator`, chạy trên máy học tập với JDK phù hợp. Không cần tạo thêm API nghiệp vụ để học ba khái niệm.

### 5.1. Chuẩn bị phạm vi thử nghiệm

Giả sử ứng dụng chạy tại `localhost:8080`, không đổi đường dẫn quản trị và bạn có quyền đọc các điểm truy cập. Nếu dùng Spring Security, cần thực hiện theo cơ chế xác thực của ứng dụng.

Trong cấu hình dành riêng cho máy học tập, có thể công khai hai điểm truy cập cần dùng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
```

Đây là cấu hình để quan sát, không tự cấp quyền qua lớp bảo mật. Khi hợp nhất vào cấu hình có sẵn, giữ một cây `management` hợp lệ thay vì tạo hai khóa trùng nhau. Với môi trường công khai, giới hạn người có quyền truy cập; không mở toàn bộ điểm truy cập chỉ để làm bài.

### 5.2. Đặt câu hỏi trước khi gọi lệnh

Các lệnh dưới đây dùng PowerShell với `curl.exe`; trên môi trường khác có thể dùng chương trình `curl` tương ứng.

Đọc trạng thái sức khỏe:

```powershell
curl.exe -i "http://localhost:8080/actuator/health"
```

**Câu hỏi trả lời được:** ứng dụng báo trạng thái sức khỏe gì ở thời điểm gọi? Ghi lại mã HTTP và nội dung thật. Không mặc định kết quả luôn là `UP`, cũng không xem một lần gọi thành công là bằng chứng mọi thao tác nghiệp vụ đều đúng.

Khám phá tên số đo:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
```

Sau đó chỉ đọc tên thực sự có trong danh sách. Ví dụ, nếu có `jvm.memory.used`:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics/jvm.memory.used"
```

**Câu hỏi trả lời được:** số đo đó đang có giá trị và các chiều phân loại nào? Đọc cả `measurements`, `availableTags` và đơn vị nếu được cung cấp. Giá trị bộ nhớ thay đổi theo tiến trình; bài học không ấn định một kết quả JSON cố định.

Nếu danh sách đã có `http.server.requests`, có thể kiểm tra nó:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics/http.server.requests"
```

Tên này được Spring Boot sử dụng mặc định cho số đo yêu cầu máy chủ của Spring MVC/WebFlux, nhưng có thể được tùy chỉnh. Số đo cũng phụ thuộc các thao tác đã phát sinh. Đừng suy ra API kinh doanh chưa có lưu lượng chỉ từ việc chưa thấy tên trong một lần đọc. Tham khảo [Spring Boot 3.3 — HTTP server metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

### 5.3. Từ một lần đọc tới giám sát và chẩn đoán

Gọi `health` một lần là kiểm tra tại một thời điểm. Muốn theo dõi dài hạn cần thu thập theo thời gian và xác định điều kiện đánh giá. Muốn điều tra một yêu cầu chậm cần thêm dữ liệu của đúng thời điểm và ngữ cảnh đó.

Thử lập một phiếu quan sát nhỏ:

| Trường cần ghi | Câu hỏi |
| --- | --- |
| Thời điểm và múi giờ | Lần đọc này tương ứng thời gian nào? |
| Phiên bản và phiên bản chạy cụ thể | Dữ liệu thuộc tiến trình nào? |
| Tên số đo, đơn vị, bộ lọc | Đang so sánh đúng đại lượng chưa? |
| Thao tác đã thực hiện | Điều gì có thể làm giá trị thay đổi? |
| Kết luận và giới hạn | Quan sát này chứng minh được gì, chưa chứng minh được gì? |

Không lấy vài lần gọi thủ công để suy ra p95 chính xác của toàn bộ dịch vụ. Bài thực hành này giúp nhận diện dữ liệu; đánh giá phân bố độ trễ cần tập quan sát và cách tổng hợp thích hợp.

Nếu gặp lỗi truy cập, ghi nhận riêng vấn đề lấy dữ liệu: `401/403` thường dẫn tới kiểm tra xác thực/quyền; `404` dẫn tới kiểm tra đường dẫn, cấu hình công khai, khả năng tồn tại của điểm truy cập hoặc số đo. Đây là hướng điều tra, không phải ánh xạ tuyệt đối cho mọi hệ thống có proxy và quy tắc bảo mật riêng.

## 6. Những cách hiểu dễ gây kết luận sai

### “Có biểu đồ CPU là có khả năng quan sát đầy đủ”

Biểu đồ CPU trả lời một nhóm câu hỏi. Trong tình huống thanh toán, CPU bình thường vẫn có thể đi cùng thời gian chờ dài. Hãy bắt đầu từ câu hỏi cần giải đáp rồi xem có đủ dữ liệu tương ứng hay chưa.

### “Không có bản ghi ERROR thì không có sự cố”

Ứng dụng có thể xử lý sai kết quả nghiệp vụ hoặc quá chậm mà không phát sinh ngoại lệ. Cần kiểm tra hành trình người dùng và kết quả mong đợi, thay vì chỉ đếm mức ghi nhật ký.

### “Cảnh báo đã chỉ ra nguyên nhân”

Một cảnh báo thường chỉ xác nhận điều kiện của nó thỏa mãn. “Tỷ lệ lỗi cao” là triệu chứng. Ngay cả cảnh báo “kết nối đang dùng chạm giới hạn” cũng còn cần tìm vì sao tài nguyên bị giữ lâu hoặc vì sao giới hạn không phù hợp.

### “Tăng mức ghi nhật ký sẽ luôn giải quyết được thiếu dữ liệu”

Tăng mức ghi có thể bổ sung ngữ cảnh cho lần phát sinh tiếp theo, nhưng không khôi phục dữ liệu chưa từng được lưu. Cần cân nhắc khối lượng, thông tin nhạy cảm và ảnh hưởng vận hành; chỉ thu điều cần thiết cho câu hỏi điều tra.

### “Không có cảnh báo nghĩa là hệ thống tốt”

Có thể quy tắc chưa bao phủ đúng hành vi, dữ liệu chưa được thu hoặc đường cảnh báo gặp lỗi. Hãy phân biệt “không phát hiện vấn đề” với “đã đo và xác nhận yêu cầu dịch vụ được đáp ứng”.

### “Quay về phiên bản cũ thành công là đã chứng minh toàn bộ nguyên nhân”

Đây là bằng chứng có ích về một thay đổi liên quan. Muốn giải thích cơ chế, cần xác định thay đổi cụ thể và kiểm tra các yếu tố khác đã thay đổi cùng lúc.

## 7. Tự kiểm tra bằng tình huống

### Tình huống A

Một hệ thống mỗi phút kiểm tra khả năng hoàn thành thanh toán bằng giao dịch thử và phát cảnh báo khi liên tiếp thất bại.

**Đáp án:** đây là giám sát từ góc nhìn bên ngoài. Kết quả giúp phát hiện hành trình có vấn đề; muốn biết lỗi nằm ở đâu cần dữ liệu điều tra bổ sung.

### Tình huống B

Nhóm vận hành có thể chọn một yêu cầu chậm, nối nhật ký với dấu vết, xác định phiên bản và bước xử lý liên quan.

**Đáp án:** tình huống thể hiện năng lực quan sát hữu ích. Nếu nhóm dùng các dữ liệu đó để kiểm chứng giả thuyết, họ đang thực hiện chẩn đoán.

### Tình huống C

Health báo `UP`, cảnh báo không phát, nhưng phản ánh của người dùng cho thấy kết quả thanh toán bị tính sai.

**Đáp án:** chưa thể xem dịch vụ là đúng chỉ dựa trên health. Cần xác định phạm vi sai, thu bằng chứng của giao dịch liên quan và bổ sung phép đánh giá kết quả nghiệp vụ phù hợp.

### Bài tập áp dụng

Với một thao tác có sẵn trong ứng dụng của bạn:

1. Viết một câu mô tả kết quả người dùng mong đợi.
2. Chọn một dấu hiệu có thể theo dõi để nhận ra kết quả không đạt.
3. Nêu một câu hỏi điều tra mà dấu hiệu đó chưa trả lời được.
4. Chỉ ra dữ liệu cần thêm và cách nối dữ liệu với đúng thao tác.
5. Viết một giả thuyết, một phép kiểm chứng và một kết quả có thể bác bỏ giả thuyết ấy.

Bạn hiểu đúng ba khái niệm khi có thể giải thích riêng: **đang theo dõi điều gì, có thể biết thêm điều gì từ dữ liệu và cần kiểm chứng điều gì để kết luận**.
