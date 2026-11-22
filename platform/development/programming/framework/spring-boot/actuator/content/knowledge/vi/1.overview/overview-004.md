# Các khái niệm endpoint, health indicator, meter, observation và trace

## 1. Một giao dịch, nhiều câu hỏi khác nhau

Giả sử một lần đặt hàng phải kiểm tra kho rồi ghi nhận đơn. Khi vận hành dịch vụ, bạn có thể muốn biết:

- Khả năng phục vụ của kho hiện đang được đánh giá ra sao?
- Đã có bao nhiêu đơn được chấp nhận?
- Những lần xử lý vừa qua mất bao lâu?
- Một lần đặt hàng cụ thể đi qua những bước nào?
- Công cụ quản trị đọc những thông tin đó từ đâu?

Năm câu hỏi liên quan tới cùng một ứng dụng, nhưng chúng không yêu cầu cùng một loại dữ liệu. Vì vậy, Actuator và hệ sinh thái Micrometer dùng nhiều khái niệm với vai trò riêng.

| Khái niệm | Vai trò cần nhớ | Ví dụ trong dịch vụ đặt hàng |
| --- | --- | --- |
| Điểm truy cập quản trị — endpoint | Công bố một khả năng đọc hoặc quản lý | `health`, `metrics`, endpoint tùy chỉnh |
| Bộ kiểm tra tình trạng — health indicator | Đánh giá một điều kiện cụ thể | Kiểm tra khả năng dùng một tài nguyên |
| Bộ đo — meter | Ghi nhận hoặc lấy số đo | Bộ đếm đơn được chấp nhận, bộ đo thời gian xử lý |
| Hoạt động được quan sát — observation | Mô tả vòng đời của một lần thực hiện để các bộ xử lý ghi nhận tín hiệu | Một lần xử lý đặt hàng bắt đầu, gặp lỗi, kết thúc |
| Dấu vết — trace | Liên kết các đơn vị công việc có quan hệ trong một lần thực hiện | Đặt hàng → kiểm tra kho → lưu đơn |

**Endpoint là cách công bố; health indicator là phép kiểm tra; meter là công cụ đo; observation là điểm tích hợp việc quan sát; trace là dữ liệu mô tả một hành trình thực hiện.** Không nên dùng các từ này thay thế cho nhau.

Bài này giải thích theo Spring Boot **3.3.13**, Micrometer **1.13.x** và Micrometer Tracing **1.3.x** do Boot quản lý. Ví dụ hoàn chỉnh chạy bằng Java **21**.

## 2. Endpoint: công bố khả năng quản trị

### 2.1. Định danh và cách truy cập là hai phần riêng

Trong ngữ cảnh Actuator, một endpoint có định danh và các thao tác. Chẳng hạn, endpoint `health` cung cấp thông tin tình trạng. Khi được công bố qua HTTP với tiền tố thông thường, nó có đường dẫn `/actuator/health`.

Cần tách ba thứ:

~~~text
Định danh:       health
Thao tác:        đọc thông tin tình trạng
Cách công bố:    HTTP tại /actuator/health hoặc cơ chế khác phù hợp
~~~

`@Endpoint` nhận diện một loại endpoint; các annotation như `@ReadOperation` mô tả thao tác. Actuator có thể thích nghi các thao tác này với công nghệ công bố như HTTP hoặc JMX. [Hợp đồng @Endpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

“Endpoint” cũng được dùng rộng rãi để nói về API nghiệp vụ. Trong bài này, khi không ghi rõ khác đi, từ đó chỉ **endpoint quản trị của Actuator**. Một phương thức `@GetMapping("/orders")` không tự trở thành Actuator endpoint.

### 2.2. Endpoint không nhất thiết tự tạo dữ liệu

Một endpoint có thể đọc dữ liệu từ thành phần khác:

~~~text
HealthIndicator ------> health endpoint ------> bên đọc tình trạng
MeterRegistry --------> metrics endpoint -----> bên tra cứu số đo
Dữ liệu tùy chỉnh ----> custom endpoint ------> công cụ quản trị
~~~

Ví dụ, `metrics` là một giao diện tra cứu các số đo đang được quản lý. Việc thêm một tên vào danh sách công bố web không tự tạo ra phép đo nghiệp vụ mang tên đó.

Để đọc được qua web, cần có các thành phần phù hợp, endpoint được bật, được công bố qua HTTP và yêu cầu vượt qua quy tắc truy cập. Trong dòng Boot 3.3, mặc định chỉ `health` được công bố qua HTTP. [Cơ chế endpoint và exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Việc công bố và việc cấp quyền có mục đích khác nhau. Khi áp dụng, hãy xác định ai cần đọc dữ liệu quản trị và thông tin nào phù hợp để họ nhìn thấy.

## 3. Health indicator: một phép đánh giá có phạm vi

### 3.1. Đầu vào là điều kiện kiểm tra, đầu ra là Health

`HealthIndicator` là giao diện đóng góp một kết quả `Health` cho hệ thống tình trạng. Phương thức quan trọng là `health()`. Kết quả chứa trạng thái, và có thể có chi tiết bổ sung. [API HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Một ví dụ về ý nghĩa:

~~~text
“Có sử dụng được tài nguyên X theo phép kiểm tra đã định nghĩa không?”
    -> đánh giá điều kiện
    -> UP hoặc DOWN cùng thông tin phù hợp
~~~

Phạm vi của câu hỏi rất quan trọng. Nếu phép kiểm tra chỉ xác nhận kết nối được tới kho dữ liệu, nó chưa chứng minh được rằng mọi quy tắc đặt hàng đều đúng.

Không nên suy diễn `UP` thành “toàn bộ nghiệp vụ chắc chắn thành công”. Trạng thái có giá trị trong phạm vi các điều kiện thực sự được kiểm tra.

### 3.2. Indicator và health endpoint có quan hệ đóng góp

Trong một ứng dụng Boot, có thể có nhiều thành phần đóng góp tình trạng. Health endpoint tổ chức và công bố bức tranh kết hợp. Việc tổng hợp dựa trên chính sách trạng thái; đó không phải phép bỏ phiếu kiểu “đa số UP thì toàn hệ thống UP”. [StatusAggregator mặc định](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

Cũng cần tách:

- Trạng thái `Health` ở phía mô hình.
- Quy tắc chọn chi tiết được công bố.
- Mã HTTP do lớp công bố health ánh xạ.

Một chuỗi `"DOWN"` nằm trong dữ liệu của endpoint tùy chỉnh không tự tạo ra mọi hành vi của health endpoint. Việc ánh xạ trạng thái sang mã HTTP có thành phần phụ trách riêng. [HttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

### 3.3. Chọn phép kiểm tra có ý nghĩa

Khi viết indicator, hãy phát biểu rõ điều kiện nào được đánh giá. Ví dụ:

- “Ứng dụng còn đủ dung lượng đĩa theo ngưỡng đã chọn.”
- “Có thể thực hiện một kiểm tra kết nối tới nguồn dữ liệu.”
- “Một thành phần nội bộ đang được đánh dấu có khả năng phục vụ.”

Đừng để một phép kiểm tra tình trạng thực hiện một giao dịch phá hủy dữ liệu chỉ để xem hệ thống “còn sống” hay không. Với tài nguyên bên ngoài, cần cân nhắc thời gian chờ và chi phí của phép kiểm tra.

Ví dụ chạy trong bài sẽ dùng một cờ mô phỏng để làm rõ giao diện `HealthIndicator`. Nó không giả làm phép kiểm tra kết nối kho hàng thật.

## 4. Meter: công cụ tạo ra số đo

### 4.1. Meter khác với một giá trị metric

`Meter` là giao diện thu thập một tập các phép đo. Khi nói “metric”, người ta thường đang nói tới số đo hoặc chuỗi số liệu được công bố. Một meter có thể cho nhiều đại lượng; vì vậy không có quy tắc “một meter bằng đúng một con số”. [Khái niệm Meter](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

Ba loại cần nhận diện sớm:

| Loại | Cách dùng | Ví dụ |
| --- | --- | --- |
| `Counter` | Cộng dồn những sự kiện đã xảy ra bằng lượng tăng dương | Số đơn được chấp nhận |
| `Timer` | Ghi nhận thời gian và số lượt được đo | Thời gian xử lý các lần đặt hàng |
| `Gauge` | Đọc giá trị của trạng thái tại thời điểm quan sát | Số công việc đang chờ |

`Counter` không phải nơi đặt số công việc đang chờ, vì đại lượng đó có thể giảm. Muốn tính tốc độ từ bộ đếm, cần xét sự thay đổi trong một khoảng thời gian và xử lý việc tiến trình khởi động lại. [Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

`Timer` đã có số lượt và tổng thời gian. Nếu chỉ muốn đếm chính những lượt đã được timer đo, thường không cần thêm một counter trùng nghĩa. Một counter riêng vẫn có ích khi biểu diễn kết quả nghiệp vụ khác, chẳng hạn “đơn được chấp nhận” trong khi timer đo mọi lần thử. [Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

`Gauge` phản ánh giá trị lúc lấy mẫu; các thay đổi trung gian giữa hai lần lấy mẫu có thể không được giữ lại. Một giá trị hàng đợi hiện tại không cho biết hôm qua hàng đợi từng dài nhất bao nhiêu. [Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

### 4.2. MeterRegistry quản lý bộ đo

`MeterRegistry` quản lý các meter. Tên và các nhãn (tags) phân biệt những nhóm đo.

Ví dụ về mặt ý nghĩa:

~~~text
Tên:      checkout.duration
Nhãn:     channel=web, result=success
Số liệu:  số lượt, tổng thời gian, các thống kê được hỗ trợ
~~~

Một meter được dùng lại cho nhiều lượt thực hiện. Ngược lại, một observation trong ví dụ ở phần sau đại diện cho một lượt thực hiện cụ thể. Đây là điểm khác biệt về vòng đời:

~~~text
1 meter dùng qua nhiều lượt
        ^
        | ghi nhận
        +--- lượt 1
        +--- lượt 2
        +--- lượt 3
~~~

Khi dữ liệu đã được tổng hợp, bạn không thể chỉ từ một tổng số suy ra đầy đủ diễn biến của từng lượt. Đó là lý do metrics và traces hỗ trợ những câu hỏi khác nhau.

## 5. Observation: kết nối vòng đời công việc với bộ xử lý tín hiệu

### 5.1. Observation mô tả một lần hoạt động

`Observation` cho phép mô tả lúc một hoạt động bắt đầu, có lỗi hoặc sự kiện, đi vào phạm vi hiện hành và kết thúc. Các `ObservationHandler` phù hợp phản ứng với vòng đời đó.

Một bộ xử lý có thể ghi timer; bộ xử lý khác có thể tạo span. **Observation không tự đồng nghĩa với timer hoặc span.** Dữ liệu thực sự sinh ra phụ thuộc bộ xử lý và cấu hình đang hoạt động. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

Mô hình đơn giản:

~~~text
Một lần xử lý nghiệp vụ
        |
        v
Observation + Context
        |
        +--> bộ xử lý số đo --> MeterRegistry
        |
        +--> bộ xử lý tracing --> span
~~~

Lợi ích là mã nghiệp vụ có một điểm mô tả hoạt động, còn cách ghi nhận có thể được cấu hình ở lớp tích hợp.

### 5.2. ObservationRegistry khác MeterRegistry

Hai registry có trách nhiệm khác nhau:

| Thành phần | Điều nó quản lý |
| --- | --- |
| `MeterRegistry` | Các meter và cách chúng ghi nhận/công bố số đo |
| `ObservationRegistry` | Cấu hình observation, gồm các handler và chính sách liên quan |
| `Tracer` | Tạo và quản lý span cùng ngữ cảnh tracing |

`Observation.Context` giữ thông tin của một lượt để các bộ xử lý phối hợp. `ObservationConvention` chuẩn hóa tên và dữ liệu mô tả; predicate có thể loại một observation; filter có thể điều chỉnh context. Bạn chưa cần tự viết tất cả các thành phần này để hiểu quan hệ chính. [Các thành phần Observation](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Trong ứng dụng Spring Boot, thường tiêm các registry đã được cấu hình thay vì tự tạo những registry riêng lẻ ở từng service. Tạo một đối tượng registry mới có thể khiến phép đo rơi vào một cấu hình khác với cấu hình mà hệ thống đang công bố.

### 5.3. Scope giúp xác định hoạt động hiện hành

Phạm vi hiện hành (scope) cho phép bộ xử lý biết observation hoặc span nào đang bao quanh công việc. Nhờ đó, một hoạt động con có thể được liên kết với hoạt động cha.

Với cách dùng đồng bộ trong bài, `observe(...)` quản lý việc bắt đầu, mở scope, chạy lambda, ghi nhận lỗi nếu có, đóng scope và kết thúc observation. Nếu tự quản lý thủ công, phải đảm bảo kết thúc và đóng scope ngay cả khi có ngoại lệ.

Không nên dùng cùng một observation làm đối tượng chung cho tất cả yêu cầu. Mỗi lượt cần ngữ cảnh riêng; các số liệu tổng hợp được đưa vào meter dùng chung.

## 6. Nhãn ít và nhiều giá trị: vì sao phải phân biệt?

Số giá trị khác nhau mà một nhãn có thể mang được gọi là độ đa dạng giá trị (cardinality).

- `channel` với vài lựa chọn như `web` hoặc `mobile` có miền giá trị nhỏ.
- `order.id` thường tiếp tục sinh giá trị mới theo từng đơn.
- `traceId` cũng có rất nhiều giá trị khác nhau.

Theo cách tích hợp Observation của Boot, dữ liệu low cardinality được đưa vào metrics và traces; dữ liệu high cardinality dành cho traces, không được tự đưa vào nhãn metrics theo đường xử lý mặc định đó. [Quy tắc key-value trong Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Điều này quan trọng vì tổ hợp nhãn làm tăng số nhóm đo. Chẳng hạn, nếu có 3 kênh và 4 vùng thì có tối đa 12 tổ hợp kênh–vùng. Thêm mã đơn với hàng triệu giá trị có thể làm số tổ hợp tăng rất mạnh khi các giá trị đó được sử dụng.

Đặt `order.id` bằng `highCardinalityKeyValue(...)` giúp mô tả từng lượt cho tracing trong cấu hình phù hợp. Nó không cản bạn tự đăng ký một meter sai thiết kế và gắn mã đơn vào nhãn của meter đó. Người viết mã vẫn phải chọn nhãn có chủ đích.

Dữ liệu đưa vào trace cũng cần được lựa chọn: khả năng gắn nhiều giá trị không phải lý do để ghi tùy tiện thông tin bí mật hoặc dữ liệu người dùng.

## 7. Trace: liên kết các span của một hành trình

### 7.1. Span là đơn vị công việc; trace là bức tranh kết hợp

Một span mô tả một đơn vị công việc, thường có tên, thời điểm bắt đầu/kết thúc, định danh và dữ liệu liên quan. Trace liên kết các span có quan hệ để nhìn lại hành trình thực hiện. Một trace có thể chỉ nằm trong một tiến trình hoặc đi qua nhiều dịch vụ. [OpenTelemetry: Traces và spans](https://opentelemetry.io/docs/concepts/signals/traces/).

Mô hình hai span đơn giản:

~~~text
Trace T
└── Span A: checkout
    └── Span B: stock.check
~~~

Hai span có cùng trace ID. Mỗi span có span ID riêng. Span con tham chiếu span cha; span gốc không có cha trong mô hình này.

Các nhãn `T`, `A` và `B` ở đây chỉ phục vụ giải thích, không phải định danh sinh ra từ chương trình.

Trace không phải danh sách có thứ tự của toàn bộ dòng log. Nó giữ cấu trúc công việc đã được ghi nhận. Khi có các hoạt động chạy đồng thời, không thể chỉ nhìn thứ tự dòng log rồi khẳng định đó là thứ tự cha–con.

### 7.2. Truyền ngữ cảnh nối hành trình qua ranh giới

Khi gọi dịch vụ khác, phía gửi phải truyền ngữ cảnh và phía nhận phải khôi phục ngữ cảnh phù hợp để nối các span. Với HTTP, một cơ chế tiêu chuẩn là header `traceparent` của W3C Trace Context. Khi chuyển luồng hoặc chuyển qua xử lý bất đồng bộ, ngữ cảnh cũng cần được xử lý đúng. [Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

Có hai observation ở hai dịch vụ chưa đủ để kết luận chúng thuộc cùng một trace. Nếu việc truyền ngữ cảnh bị đứt, dữ liệu có thể thành những hành trình rời nhau.

Trong ứng dụng Boot, hãy dùng các thành phần tích hợp đã cấu hình, chẳng hạn builder HTTP client do Boot cung cấp, khi muốn hưởng cơ chế truyền tracing tự động tương ứng. [Tracing trong Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 7.3. Ghi nhận span, gửi dữ liệu và xem trace là các bước khác nhau

Một chuỗi thường gặp:

~~~text
Hoạt động được quan sát
    -> bộ xử lý tracing / tracer
    -> span được kết thúc
    -> cơ chế xuất dữ liệu
    -> hệ thống lưu trữ và truy vấn trace
~~~

Có số đo không đảm bảo bạn đã cấu hình tracing. Có tracer cũng không đảm bảo một hệ thống bên ngoài đã nhận được dữ liệu. Việc lấy mẫu (sampling) còn có thể khiến chỉ một phần hành trình được ghi nhận/xuất để giới hạn chi phí.

Vì thế, không nên mong đợi mặc định có một endpoint `/actuator/trace` để tải toàn bộ dấu vết. Hãy xác minh chuỗi thu thập thực tế của công nghệ tracing đang sử dụng.

## 8. Ghép năm khái niệm mà không trộn trách nhiệm

Xét một yêu cầu đặt hàng:

1. Mã nghiệp vụ kiểm tra điều kiện kho và quyết định có nhận đơn hay không.
2. Observation bao quanh lượt thực hiện để cung cấp vòng đời và ngữ cảnh.
3. Handler số đo cập nhật timer; mã nghiệp vụ có thể tăng counter của kết quả “được chấp nhận”.
4. Handler tracing tạo các span liên quan nếu tracing được cấu hình.
5. Indicator có thể đánh giá điều kiện kho theo hợp đồng riêng khi được gọi.
6. Endpoint quản trị công bố thông tin phù hợp cho bên đọc.

Đây là mô hình tích hợp minh họa, không phải chuỗi bắt buộc mà mọi yêu cầu đều phải đi qua.

Đặc biệt, không có các suy luận tự động sau:

- Một span có lỗi không tự bắt mọi health indicator đổi sang `DOWN`.
- Một health indicator trả `DOWN` không tự tạo ra một trace lỗi.
- Đọc metrics endpoint không đồng nghĩa với việc nó mới bắt đầu đo tất cả hoạt động.
- Mở thêm endpoint không tự cài bộ xuất trace.
- Có timer đếm mọi lần thử không có nghĩa mọi lần thử đều thành công.

Mỗi tín hiệu trả lời câu hỏi của nó. Muốn chúng phản ánh cùng một điều kiện nghiệp vụ, phải thiết kế và kiểm chứng quan hệ đó.

## 9. Ví dụ hoàn chỉnh: hai lượt xử lý, một lượt bị từ chối

Chương trình sau chạy trong console để nhìn rõ quan hệ giữa năm khái niệm. Nó dùng đúng các API Actuator/Micrometer và một tracer Brave, nhưng **không khởi động Spring ApplicationContext hoặc máy chủ HTTP**.

Mục đích của cách tổ chức này là để bạn thấy các đối tượng và bộ xử lý được nối với nhau như thế nào. Trong một ứng dụng Boot thông thường, nhiều phần nối này do tự cấu hình đảm nhiệm.

Điều kiện và giới hạn của ví dụ:

- Dùng JDK 21 và Maven; lần đầu cần tải thư viện.
- Hai lượt được chạy đồng bộ trên một luồng.
- Một cờ mô phỏng khả năng dùng kho; không có dịch vụ kho thật.
- Tất cả span được lấy mẫu và thu vào danh sách trong bộ nhớ; không gửi tới hệ thống bên ngoài.
- `TrainingEndpoint` được gọi trực tiếp bằng Java. Annotation của nó không tự mở một cổng HTTP trong chương trình console.

### 9.1. Cấu trúc và khai báo thư viện

~~~text
signal-concept-demo/
├── pom.xml
└── src/main/java/SignalConceptDemo.java
~~~

Tệp `pom.xml`:

~~~xml
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
    <artifactId>signal-concept-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Parent cố định phiên bản tương thích của các thư viện. `micrometer-core` được khai báo trực tiếp vì chương trình sử dụng API meter; bridge Brave nối Micrometer Tracing với phần hiện thực Brave.

### 9.2. Mã Java

Tệp `src/main/java/SignalConceptDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.ThreadLocalCurrentTraceContext;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.brave.bridge.BraveBaggageManager;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public class SignalConceptDemo {
    record FinishedSpan(String traceId, String spanId, String parentId,
                        String operation, boolean error) {}

    @Endpoint(id = "training")
    public static final class TrainingEndpoint {
        private final HealthIndicator stockHealth;
        private final Counter accepted;

        public TrainingEndpoint(HealthIndicator stockHealth, Counter accepted) {
            this.stockHealth = stockHealth;
            this.accepted = accepted;
        }

        @ReadOperation
        public Map<String, Object> read() {
            return Map.of(
                "stock", stockHealth.health().getStatus().getCode(),
                "accepted", (long) accepted.count()
            );
        }
    }

    public static void main(String[] args) {
        List<FinishedSpan> spans = new ArrayList<>();
        SpanHandler recorder = new SpanHandler() {
            @Override
            public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                spans.add(new FinishedSpan(
                    context.traceIdString(), context.spanIdString(),
                    context.parentIdString(), span.name(), span.error() != null
                ));
                return true;
            }
        };

        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try (Tracing tracing = Tracing.newBuilder()
                 .currentTraceContext(ThreadLocalCurrentTraceContext.create())
                 .sampler(Sampler.ALWAYS_SAMPLE)
                 .addSpanHandler(recorder)
                 .build()) {
            BraveTracer tracer = new BraveTracer(
                tracing.tracer(),
                new BraveCurrentTraceContext(tracing.currentTraceContext()),
                new BraveBaggageManager()
            );
            ObservationRegistry observations = ObservationRegistry.create();
            observations.observationConfig()
                .observationHandler(new DefaultMeterObservationHandler(meters))
                .observationHandler(new DefaultTracingObservationHandler(tracer));

            AtomicBoolean stockReady = new AtomicBoolean(true);
            HealthIndicator stockHealth = () -> stockReady.get()
                ? Health.up().build()
                : Health.down().withDetail("reason", "stock-disabled").build();
            Counter accepted = meters.counter("demo.orders.accepted", "channel", "web");
            TrainingEndpoint endpoint = new TrainingEndpoint(stockHealth, accepted);

            System.out.println("health.before=" + stockHealth.health().getStatus().getCode());
            checkout(observations, stockReady, accepted, "order-101");

            stockReady.set(false);
            boolean rejected = false;
            try {
                checkout(observations, stockReady, accepted, "order-102");
            } catch (IllegalStateException expected) {
                rejected = true;
            }

            long attempts = meters.find("demo.checkout").timers().stream()
                .mapToLong(Timer::count).sum();
            long checks = meters.find("demo.stock.check").timers().stream()
                .mapToLong(Timer::count).sum();
            long traceCount = spans.stream().map(FinishedSpan::traceId).distinct().count();
            long roots = spans.stream().filter(s -> s.parentId() == null).count();
            long children = spans.size() - roots;
            boolean parentsValid = roots == 2 && children == 2
                && spans.stream().filter(s -> s.parentId() != null).allMatch(child ->
                    spans.stream().anyMatch(parent ->
                        parent.spanId().equals(child.parentId())
                            && parent.traceId().equals(child.traceId())));
            boolean orderIdInMetricTags = meters.getMeters().stream()
                .flatMap(meter -> meter.getId().getTags().stream())
                .anyMatch(tag -> tag.getKey().equals("order.id"));

            System.out.println("rejected=" + rejected);
            System.out.println("health.after=" + stockHealth.health().getStatus().getCode());
            System.out.println("accepted=" + (long) accepted.count());
            System.out.println("checkout.timer.count=" + attempts);
            System.out.println("stock.timer.count=" + checks);
            System.out.println("trace.count=" + traceCount);
            System.out.println("span.count=" + spans.size());
            System.out.println("parents.valid=" + parentsValid);
            System.out.println("error.spans=" + spans.stream().filter(FinishedSpan::error).count());
            System.out.println("orderId.in.metric.tags=" + orderIdInMetricTags);
            System.out.println("endpoint.stock=" + endpoint.read().get("stock"));
            System.out.println("endpoint.accepted=" + endpoint.read().get("accepted"));
        } finally {
            meters.close();
        }
    }

    private static void checkout(ObservationRegistry observations,
                                 AtomicBoolean stockReady, Counter accepted,
                                 String orderId) {
        Observation.createNotStarted("demo.checkout", observations)
            .lowCardinalityKeyValue("channel", "web")
            .highCardinalityKeyValue("order.id", orderId)
            .observe(() -> {
                Observation.createNotStarted("demo.stock.check", observations)
                    .observe(() -> {
                        if (!stockReady.get()) {
                            throw new IllegalStateException("Stock is unavailable");
                        }
                    });
                accepted.increment();
            });
    }
}
~~~

### 9.3. Biên dịch và chạy

Tại thư mục chứa `pom.xml`, dùng PowerShell trên Windows:

~~~powershell
mvn -q dependency:copy-dependencies
New-Item -ItemType Directory -Force target/classes | Out-Null
javac --release 21 -encoding UTF-8 -cp "target/dependency/*" -d target/classes src/main/java/SignalConceptDemo.java
java -cp "target/classes;target/dependency/*" SignalConceptDemo
~~~

Maven sao chép các thư viện vào `target/dependency`; `javac` biên dịch tệp nguồn với classpath đó; `java` chạy chương trình đã biên dịch.

Trên Linux hoặc macOS, tạo thư mục bằng `mkdir -p target/classes` và đổi dấu phân cách classpath trong lệnh chạy thành dấu hai chấm:

~~~bash
java -cp "target/classes:target/dependency/*" SignalConceptDemo
~~~

Đầu ra chuẩn của chương trình:

~~~text
health.before=UP
rejected=true
health.after=DOWN
accepted=1
checkout.timer.count=2
stock.timer.count=2
trace.count=2
span.count=4
parents.valid=true
error.spans=2
orderId.in.metric.tags=false
endpoint.stock=DOWN
endpoint.accepted=1
~~~

Các giá trị thời gian và định danh tracing không được in ra vì chúng thay đổi giữa các lần chạy. Chương trình kiểm tra quan hệ giữa định danh thay vì giả định một ID cố định.

## 10. Giải thích từng nhóm bằng chứng

### 10.1. Health đánh giá điều kiện hiện tại

Lúc đầu, `stockReady` là `true` nên indicator trả `UP`. Sau khi cờ đổi thành `false`, indicator trả `DOWN`. Đây là kết quả từ một phép kiểm tra đã được định nghĩa rõ ràng.

Phương thức `checkout` đọc cờ để quyết định nghiệp vụ. Indicator cũng đọc cờ để đánh giá tình trạng. Hai phần dùng chung điều kiện mô phỏng; indicator không phải bộ điều khiển âm thầm quyết định thay mã nghiệp vụ.

Trong hệ thống thật, cần xem hai cách đánh giá có cùng phạm vi và yêu cầu thời điểm hay không. Một phép kiểm tra định kỳ đạt không đảm bảo tài nguyên sẽ tiếp tục đạt ở mọi giao dịch tiếp theo.

### 10.2. Counter thành công và timer lượt thử có ý nghĩa khác nhau

Lượt thứ nhất đi qua kiểm tra kho rồi tăng `demo.orders.accepted`. Lượt thứ hai ném ngoại lệ trước khi tăng counter. Vì vậy:

~~~text
Số đơn được chấp nhận = 1
Số lượt checkout được đo = 2
Số lượt kiểm tra kho được đo = 2
~~~

Timer không chỉ đếm các lượt thành công. `observe(...)` vẫn kết thúc observation khi lambda ném ngoại lệ, nên lượt thất bại cũng được ghi nhận.

Chương trình cộng `count` của các timer có cùng tên vì nhãn lỗi hoặc các nhãn khác có thể chia chúng thành nhiều meter. Đọc một nhóm thành công rồi coi đó là tổng mọi lượt sẽ cho kết luận sai.

### 10.3. Observation tạo tín hiệu thông qua handler

Hai dòng đăng ký handler là phần nối quan trọng:

~~~java
observations.observationConfig()
    .observationHandler(new DefaultMeterObservationHandler(meters))
    .observationHandler(new DefaultTracingObservationHandler(tracer));
~~~

Bộ xử lý meter đưa dữ liệu vòng đời vào các timer. Bộ xử lý tracing dùng tracer để tạo span.

`ObservationRegistry` không phải kho chứa mọi số đo và cũng không phải hệ thống lưu trace lâu dài. Nó quản lý cách các lượt observation được xử lý.

Trong cấu hình mặc định của chương trình, `order.id` là dữ liệu high cardinality. Kết quả `orderId.in.metric.tags=false` xác nhận nhãn đó không đi vào các meter đang có trong ví dụ.

### 10.4. Hai trace, mỗi trace có hai span

Mỗi lần gọi `checkout` bắt đầu khi không có span cha hiện hành. Vì vậy có hai trace riêng:

~~~text
Trace của order-101
└── checkout
    └── stock.check

Trace của order-102
└── checkout
    └── stock.check
~~~

Khi observation kiểm tra kho được mở bên trong scope của checkout, tracing handler liên kết span con với span cha. `parents.valid=true` kiểm tra rằng hai span con tham chiếu đúng ID của span cha và có cùng trace ID với cha.

Lượt thất bại ném ngoại lệ ở hoạt động kiểm tra kho. Ngoại lệ tiếp tục đi qua lambda của checkout, nên cả hai observation của lượt đó đều ghi nhận lỗi. Đó là lý do có `error.spans=2`.

Không nên đọc con số 2 này thành “hai đơn thất bại”. Đây là **hai span có lỗi của cùng một lượt đặt hàng**. Đơn vị đếm luôn phải đi cùng ý nghĩa nghiệp vụ.

### 10.5. Endpoint công bố một góc nhìn

`TrainingEndpoint.read()` đọc kết quả indicator và counter rồi trả một cấu trúc dữ liệu. Nó không tạo thêm đơn, không tự tăng counter và không tự khởi tạo trace cho mọi cuộc gọi Java.

Kết quả cuối là tình trạng kho `DOWN` và số đơn được chấp nhận `1`. Điều này minh họa vai trò của endpoint: công bố dữ liệu từ các nguồn khác.

Muốn đưa loại endpoint này vào ứng dụng Boot qua HTTP, cần đăng ký nó thành bean, có hạ tầng web/Actuator phù hợp và cấu hình công bố cùng quyền truy cập. Chỉ tạo bằng `new TrainingEndpoint(...)` như trong console không đáp ứng các điều kiện đó.

Ngay cả khi được công bố, một trường dữ liệu tùy chỉnh mang giá trị `"DOWN"` cũng không tự biến endpoint này thành health endpoint với toàn bộ quy tắc ánh xạ trạng thái tương ứng.

## 11. Những chỗ dễ nhầm khi áp dụng

| Hiểu nhầm | Cách kiểm tra lại |
| --- | --- |
| “Endpoint là nơi mọi dữ liệu được sinh ra” | Tìm thành phần tạo hoặc cung cấp dữ liệu phía sau endpoint |
| “Health indicator chính là URL health” | Tách hợp đồng phép kiểm tra khỏi lớp công bố |
| “Một timer chỉ chứa thời gian” | Xem cả số lượt, tổng thời gian và các thống kê được hỗ trợ |
| “Observation luôn là một span đã được gửi đi” | Kiểm tra handler, tracer, lấy mẫu và bộ xuất dữ liệu |
| “Một trace tương ứng một span” | Xem các span cha–con thuộc cùng hành trình |
| “Đếm span lỗi là đếm giao dịch lỗi” | Xác định mỗi giao dịch tạo bao nhiêu span và lỗi lan truyền ra sao |
| “Mã đơn và trace ID nên là nhãn metric” | Kiểm tra số lượng giá trị và số tổ hợp nhóm đo có thể sinh ra |
| “Có số đo thì đã có lịch sử lâu dài” | Xác minh nơi thu thập và lưu trữ bên ngoài tiến trình |

Khi chuyển sang bất đồng bộ, còn một câu hỏi về ranh giới đo. Bao quanh lệnh gửi công việc vào executor chỉ có thể đo phần diễn ra trong phạm vi bao quanh đó; không nên mặc nhiên coi thời gian lambda trả về là thời gian toàn bộ công việc nền hoàn tất. Cần nối đúng vòng đời công việc và ngữ cảnh của nó.

Ngoài ra, không cần tự bao một hoạt động đã được framework quan sát bằng một phép đo cùng nghĩa mà không có mục tiêu rõ ràng. Các lớp đo trùng nhau có thể khiến người đọc nhầm số lượt hoặc cộng thời gian lặp.

## 12. Bài tập để tự kiểm tra mô hình

**Bài 1 — Đổi điều kiện kho sau khi có hai lượt thành công.**

Cho cả hai lần checkout chạy khi `stockReady=true`, rồi mới đổi cờ thành `false` trước khi đọc indicator. Dự đoán số đơn được chấp nhận, số lượt timer và tình trạng cuối.

Kết quả cần giải thích: có thể có 2 đơn đã được chấp nhận trong khi tình trạng hiện tại là `DOWN`. Dữ liệu tích lũy về quá khứ và phép đánh giá hiện tại đang nói về những thời điểm khác nhau.

**Bài 2 — Bỏ handler tracing.**

Chỉ giữ handler meter rồi chạy lại. Quan sát các timer và danh sách span. Không có tracing handler nào trong chương trình nối observation với tracer, nên danh sách span do recorder thu không có dữ liệu từ các observation đó. Timer vẫn có thể ghi nhận nhờ handler meter còn hoạt động.

Bài này kiểm tra lý do không được đồng nhất observation với trace. Nó không yêu cầu sửa phần nghiệp vụ.

**Bài 3 — Bỏ handler meter.**

Giữ handler tracing. Counter được mã nghiệp vụ tăng trực tiếp vẫn tồn tại; các timer do `DefaultMeterObservationHandler` tạo sẽ không còn được tạo theo con đường đó. Điều này phân biệt đo trực tiếp qua meter với đo thông qua Observation.

**Bài 4 — Diễn giải một báo cáo lỗi.**

Một giao dịch tạo 5 span, trong đó 3 span mang lỗi. Cần thêm thông tin gì trước khi báo “có 3 giao dịch lỗi”?

Cần xác định cách nhóm span thành trace/giao dịch, quan hệ cha–con và nơi lỗi phát sinh. Số span là số đơn vị công việc đã ghi nhận, không tự là số giao dịch.

Khi đọc một hệ thống có Actuator, hãy lần theo năm câu hỏi: **Dữ liệu được công bố ở đâu? Điều kiện nào được kiểm tra? Đại lượng nào được đo? Vòng đời nào được quan sát? Những span nào được liên kết thành một hành trình?** Trả lời được chúng sẽ giúp bạn chọn đúng cơ chế thay vì chỉ ghi nhớ tên API.
