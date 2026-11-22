# Nhận diện trace bị đứt, span trùng và cấu hình quan sát bị chồng lặp

Một yêu cầu đi từ dịch vụ A sang B nhưng giao diện truy vết lại hiển thị hai cây rời nhau. Sau khi thêm một thư viện quan sát, cùng một lời gọi HTTP xuất hiện thành nhiều span gần như giống nhau. Cả hai tình huống đều làm dữ liệu khó đọc, nhưng nguyên nhân có thể nằm ở những tầng khác nhau.

Muốn sửa đúng, cần phân biệt ba câu hỏi: ngữ cảnh có được truyền liên tục không, một công việc có bị đo nhiều lần không, và một bản ghi có bị gửi hoặc tiếp nhận nhiều lần không. Bài này xây dựng cách chẩn đoán cho Spring Boot 3.3.x với Micrometer Observation/Tracing, đồng thời chỉ ra những điểm cần kiểm tra nếu có OpenTelemetry Java agent hoặc bộ thu thập dữ liệu ở giữa.

## 1. Nhìn hệ thống quan sát theo đường đi của dữ liệu

```text
Công việc cần quan sát
  → mã tích hợp tạo observation hoặc span
  → tracer quản lý trace/span hiện hành
  → propagator truyền ngữ cảnh qua mạng hoặc cơ chế chuyển luồng
  → exporter gửi span đã hoàn tất
  → bộ thu thập xử lý và chuyển tiếp
  → hệ thống lưu trữ và giao diện truy vấn
```

Mã tích hợp quan sát (instrumentation) xác định **đo công việc nào**. Tracer xác định **công việc đó thuộc trace nào**. Bộ truyền ngữ cảnh (propagator) đưa thông tin liên kết qua ranh giới xử lý. Exporter và bộ thu thập đưa dữ liệu đến nơi lưu.

Một observation có thể được nhiều handler xử lý cho các mục đích khác nhau, chẳng hạn đo thời gian và tạo span. Vì vậy, thấy nhiều handler không đồng nghĩa cấu hình bị trùng. Cần xem chúng xử lý cùng ngữ cảnh để tạo những loại dữ liệu gì. Tham khảo [vòng đời Observation và ObservationHandler trong Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

| Hiện tượng | Điều đã quan sát được | Điều chưa được phép kết luận ngay |
| --- | --- | --- |
| A và B dùng hai trace ID cho cùng một lời gọi đã xác minh | Có dấu hiệu mất liên tục ngữ cảnh | Chưa biết mất lúc tạo client, truyền header, nhận header hay chuyển luồng |
| B có cùng trace ID với A nhưng không thấy span cha | Dữ liệu đang xem thiếu liên kết cha | Chưa chứng minh ngữ cảnh truyền bị mất |
| Hai span gần giống nhau có ID khác nhau | Có hai span được tạo | Chưa chứng minh công việc bị đo thừa |
| Một span ID xuất hiện ở nhiều bản ghi | Có nhiều bản ghi liên quan cùng định danh | Chưa chứng minh có nhiều lần thực hiện nghiệp vụ |
| Có nhiều thư viện quan sát trong runtime | Có nhiều thành phần có khả năng hoạt động | Chưa chứng minh tất cả đều đã được kích hoạt |
| Hai dòng log giống nhau | Có hiện tượng lặp ở log | Chưa chứng minh có hai span |

Thông tin log là bằng chứng hỗ trợ. MDC có thể thiếu hoặc bị ghi đè; không dùng riêng chuỗi `traceId` trong log làm bằng chứng cuối cùng về ngữ cảnh thật của tracer.

## 2. Định nghĩa một đường đi hợp lệ trước khi tìm lỗi

Giả sử đã xác minh: một yêu cầu HTTP vào A tạo đúng một lần gọi HTTP từ A đến B, không có retry, không qua một quy trình tách biệt có chủ đích. Với mô hình client/server dùng các span riêng, cây mong đợi có dạng:

```text
Trace T
└── A: SERVER, span S1
    └── A: CLIENT, span S2, parent S1
        └── B: SERVER, span S3, parent S2
```

Ba span giữ cùng `traceId=T`. Span nhận ở B nối vào span gửi của client A, nên `parentId` của S3 là S2, không phải S1.

Hai span CLIENT và SERVER là hai góc nhìn khác nhau của một lời gọi qua mạng. Khoảng thời gian của chúng có thể gần bằng nhau; điều đó không làm chúng thành span trùng. Các bước nghiệp vụ bên trong B có thể có thêm span INTERNAL hợp lệ.

Đây là giả định cho phần thực hành của bài. Một số hệ thống Brave/B3 hỗ trợ client và server cùng đóng góp vào một span dùng chung. Spring Boot có cấu hình `management.tracing.brave.span-joining-supported`, mặc định là `false`; việc bật nó cần B3 và hệ thống nhận tương thích. Khi gặp dữ liệu kiểu này, xem thêm `kind`, endpoint và cờ `shared` trước khi kết luận lặp. Xem [thuộc tính tracing của Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) và [mô hình span của Zipkin](https://github.com/openzipkin/zipkin-api/blob/master/zipkin2-api.yaml).

Cũng không áp đặt “một mã nghiệp vụ phải có đúng một trace” cho mọi kiến trúc. Công việc được lên lịch về sau, xử lý lô hoặc xử lý có nhiều nguồn có thể dùng trace riêng và span link theo thiết kế. Chỉ gọi là trace bị đứt sau khi xác định ranh giới ấy phải tiếp tục cùng ngữ cảnh.

## 3. Nhận diện trace bị đứt

### 3.1. Dấu hiệu mạnh: mất liên tục tại một ranh giới đã xác minh

Dữ liệu mong đợi:

```text
A gửi: trace=T1, span=S2
B nhận: trace=T1, span=S3, parent=S2
```

Dữ liệu nghi ngờ:

```text
A gửi: trace=T1, span=S2
B nhận: trace=T2, span=S8, parent=không có
```

Nếu đó thực sự là cùng một lần gọi và không có chủ đích bắt đầu trace mới, cần tìm vị trí B không nhận được hoặc không dùng được ngữ cảnh T1.

Với W3C Trace Context, `traceparent` mang trace ID, parent ID và các cờ liên quan. Phía nhận dùng parent ID để nối span mới vào đường đi đã có; không được sao chép parent ID thành ID của span nhận trong mô hình span riêng. Header sai định dạng có thể bị từ chối. Xem [đặc tả xử lý Trace Context](https://www.w3.org/TR/trace-context/).

Theo dõi bằng chứng theo từng điểm:

1. **Ngay trước khi A gửi:** span hiện hành nào đang hoạt động? Client có tạo span gửi không?
2. **Trên yêu cầu đi ra:** header truyền ngữ cảnh thực tế chứa gì?
3. **Sau proxy/gateway, tại đầu vào B:** header còn nguyên không?
4. **Trong B khi xử lý:** tracer nhận trace ID và parent ID nào?
5. **Tại nơi thu thập:** span của A và B có cùng thông tin liên kết đó không?

Nếu header đã thiếu khi rời A, sửa cấu hình nhận ở B sẽ không giải quyết tận gốc. Nếu header còn đúng khi đến B nhưng B tạo trace mới, tập trung vào việc trích xuất và các tracer đang hoạt động trong B.

### 3.2. Các nguyên nhân thường gặp và cách phân biệt

| Ranh giới | Khả năng cần kiểm tra | Bằng chứng có giá trị |
| --- | --- | --- |
| Tạo HTTP client | Client được tạo ngoài builder có tích hợp quan sát của Boot | Kiểm tra cách tạo client thực tế và header của chính lời gọi đó |
| Truyền qua mạng | Proxy hoặc mã tùy chỉnh xóa/ghi đè header | Đối chiếu trước và sau từng điểm trung gian |
| Nhận ngữ cảnh | B chỉ nhận một định dạng khác với định dạng A gửi | So sánh cấu hình produce/consume đang có hiệu lực |
| Gửi việc sang executor | Công việc chạy khi ngữ cảnh nguồn không được khôi phục trên luồng đích | So sánh tracer tại điểm gửi và điểm bắt đầu công việc |
| Chuỗi Reactor | Dựa vào ThreadLocal tại thời điểm lắp ráp, rồi mất ngữ cảnh lúc thực thi | Kiểm tra tại toán tử thực sự chạy và sau điểm đổi luồng |
| Mã tạo span riêng | Span được bắt đầu nhưng không được đặt trong scope phù hợp | Kiểm tra vòng đời span và scope bao quanh công việc |
| Nhiều SDK/tracer độc lập | Một thành phần ghi vào ngữ cảnh khác với thành phần dùng để gửi HTTP | Đối chiếu đối tượng tracer/SDK, đường cấu hình và dữ liệu xuất |

Với Spring Boot, các builder `RestTemplateBuilder`, `RestClient.Builder` và `WebClient.Builder` được tự động cấu hình là đường tích hợp quan trọng để truyền trace qua HTTP. Tự tạo client ngoài các builder đó có thể làm mất tích hợp tự động. Tham khảo [phần truyền trace của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Đối với executor, dùng cơ chế truyền ngữ cảnh phù hợp, ví dụ `ContextPropagatingTaskDecorator` trong Spring Framework 6.1, và bảo đảm công việc chạy qua đúng executor đã cấu hình. Với Reactor, kiểm tra chế độ `spring.reactor.context-propagation` và ngữ cảnh tại lúc thực thi. Chỉ sao chép MDC giúp mang chuỗi phục vụ log; nó không thay thế việc truyền ngữ cảnh của tracer.

### 3.3. “Thiếu span cha” không luôn là mất ngữ cảnh

Có thể thấy `traceId=T1` và `parentId=S2` ở B nhưng không tìm được S2. Những khả năng khác gồm:

- Span cha chưa hoàn tất nên chưa được xuất, hoặc dữ liệu tới hệ thống nhận chậm.
- Quyết định chọn mẫu hay bộ lọc ở các tầng không giữ đầy đủ phần dữ liệu đang tìm.
- Hàng đợi exporter đầy, mạng lỗi, tiến trình kết thúc trước khi gửi xong.
- Truy vấn đang giới hạn thời gian, dịch vụ, môi trường hoặc vùng dữ liệu.
- Span cha nằm ngoài phạm vi hệ thống đang thu thập, như một client bên ngoài.
- Bản ghi có dữ liệu nhưng giao diện chỉ đang hiển thị một phần.

Trong trường hợp này, liên kết trong ngữ cảnh có thể vẫn đúng. Hãy kiểm tra exporter, bộ thu thập và truy vấn trước khi thay đổi propagator.

Một ví dụ: chủ động gửi một `traceparent` từ curl với parent ID tự chọn sẽ làm span server có cha bên ngoài. Nếu curl không xuất span cha ấy, việc không thấy nó trong hệ thống lưu trữ là điều có thể giải thích được.

## 4. Phân biệt các dạng “span trùng”

### 4.1. Hai span khác ID nhưng đo cùng một ranh giới

Một cây đáng kiểm tra:

```text
A: SERVER
└── A: CLIENT do tích hợp HTTP của framework tạo
    └── A: CLIENT do bộ bọc tùy chỉnh tạo
        └── B: SERVER
```

Nếu đã xác minh chỉ có một lần gửi HTTP, hai span CLIENT cùng mô tả một lần gửi, cùng đích và cùng khoảng công việc có thể là đo chồng lặp.

Cần đối chiếu đồng thời:

- Dịch vụ và instance tạo span.
- `kind`: CLIENT, SERVER, INTERNAL, PRODUCER hoặc CONSUMER.
- Thao tác, phương thức HTTP, tuyến và đích gọi.
- Thời điểm bắt đầu/kết thúc, quan hệ cha–con.
- Tên và phiên bản instrumentation scope nếu định dạng dữ liệu có cung cấp.
- Số lần thực hiện thực tế, retry, redirect, cơ chế dự phòng và các bước nghiệp vụ.

Tên giống nhau chỉ là một dấu hiệu. Hai lần gọi hợp lệ đến cùng API có thể cùng tên span. Ngược lại, hai tích hợp đo trùng có thể đặt hai tên khác nhau.

### 4.2. Cùng định danh nhưng có nhiều bản ghi

Với dữ liệu đã loại trừ mô hình shared span, nếu cùng cặp `traceId + spanId`, cùng nguồn và cùng nội dung xuất hiện nhiều lần tại một đích nhận, hãy kiểm tra đường chuyển dữ liệu:

```text
Một span hoàn tất
  ├── exporter thứ nhất ──→ cùng hệ thống nhận
  └── exporter thứ hai ──→ cùng hệ thống nhận
```

Hoặc:

```text
SDK → Collector A → hệ thống nhận
  └→ Collector B → cùng hệ thống nhận
```

Cũng cần xem việc gửi lại khi có lỗi hoặc xác nhận không rõ ràng. Một số hệ thống nhận có thể gộp các bản ghi cùng ID, nên việc gửi lặp không nhất thiết xuất hiện thành hai dòng trên giao diện.

So sánh **dữ liệu ở từng chặng**, không chỉ đếm dòng trong giao diện. Hai lần xuất cùng một span sang hai hệ thống khác nhau có thể là thiết kế có chủ đích; vấn đề của tình huống trên là nhiều đường cùng đổ về một đích ngoài dự kiến.

### 4.3. Những trường hợp cần giữ lại

| Nhìn thấy | Có thể là hành vi hợp lệ vì |
| --- | --- |
| Một span CLIENT ở A và một span SERVER ở B | Chúng đo hai phía của lời gọi |
| SERVER chứa INTERNAL mang tên nghiệp vụ | Đó là bước con có ý nghĩa riêng |
| Nhiều span CLIENT cùng tuyến | Có thể có nhiều lần gọi hoặc retry thật |
| Span ở proxy/service mesh và span trong ứng dụng | Chúng có thể đo các ranh giới mạng khác nhau |
| Một span có nhiều sự kiện | Sự kiện không phải các span mới |
| Nhiều handler trên một observation | Có thể mỗi handler xử lý một tín hiệu khác nhau |
| Một trace có nhiều span cùng tên | Tên không phải định danh duy nhất |

Mục tiêu là loại bỏ việc đo lặp một trách nhiệm, không phải ép mọi yêu cầu về một số lượng span cố định.

## 5. Tìm cấu hình quan sát bị chồng lặp

### 5.1. Lập bản đồ ai đang đo việc gì

Trong ứng dụng cần chẩn đoán, liệt kê những thành phần thực sự hoạt động:

| Công việc hoặc tầng | Thành phần có thể đang sở hữu | Dấu hiệu chồng lặp cần xác minh |
| --- | --- | --- |
| HTTP server | Instrumentation của Spring MVC/WebFlux hoặc Java agent | Filter tự tạo thêm SERVER span cho toàn bộ cùng yêu cầu |
| HTTP client | Client được Boot tích hợp hoặc Java agent | Interceptor/bộ bọc tạo thêm CLIENT span quanh cùng lần gửi |
| Hàm nghiệp vụ | Observation thủ công hoặc aspect cho annotation | Cả hai cùng bọc đúng một thao tác với cùng mục đích |
| Cầu nối tracing | Bridge của Micrometer đến Brave hoặc OpenTelemetry | Nhiều bridge/SDK cấu hình độc lập mà không có thiết kế tích hợp rõ |
| Vòng đời observation | Handler đo metric và handler tracing | Đăng ký lặp handler cùng vai trò hoặc nhiều đường tạo span cho cùng context |
| Xuất span | Exporter hoặc span processor | Nhiều đường gửi cùng dữ liệu về một nơi |
| Thu thập | Các pipeline/Collector | Dữ liệu cùng nguồn đi vòng hoặc nhập lại vào cùng đích |

Việc có `micrometer-tracing-bridge-otel` cùng thư viện OpenTelemetry là quan hệ cầu nối bình thường, không tự nó chứng minh có hai hệ thống tạo span. Tương tự, Actuator còn phục vụ nhiều chức năng khác ngoài tracing. Không gỡ toàn bộ chỉ vì phát hiện ứng dụng có Java agent.

### 5.2. Annotation và mã thủ công bao quanh cùng việc

Một tình huống điển hình là controller đã được HTTP instrumentation quan sát nhưng lại được thêm observation cho chính toàn bộ cùng ranh giới HTTP. Khi aspect cho `@Observed` đã được kích hoạt, annotation bổ sung có thể tạo observation nữa.

Một tình huống khác là một phương thức vừa có `@Observed`, vừa gọi `Observation.createNotStarted(...).observe(...)` để bọc nguyên cùng thân phương thức.

Cách xử lý phụ thuộc ý nghĩa đo lường:

- Nếu hai lớp cùng đo một trách nhiệm, giữ một lớp phù hợp.
- Nếu muốn đo riêng một bước nghiệp vụ, đặt observation ở bước ấy với tên và phạm vi phản ánh đúng công việc.
- Nếu chỉ muốn đổi tên hoặc bổ sung thông tin cho observation có sẵn, xem xét convention/cơ chế tùy chỉnh tương ứng trước khi tạo thêm một vòng đo.
- Không thêm annotation theo thói quen rồi suy ra rằng càng nhiều span càng quan sát tốt.

Spring Boot có lưu ý rõ về observation lặp khi thêm annotation trên các thành phần đã được instrument. Xem [phần annotation trong tài liệu Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html). Cần xác minh aspect thực sự có hoạt động; một annotation chưa được xử lý không phải nguyên nhân tạo observation thêm.

### 5.3. Java agent, starter và cấu hình riêng

Agent có thể được gắn bằng tham số `-javaagent`, cấu hình chạy của container/IDE hoặc biến môi trường dùng khi khởi động JVM. Nó không nhất thiết xuất hiện trong cây phụ thuộc Gradle của ứng dụng.

Nếu thấy agent và cấu hình quan sát trong ứng dụng:

1. Ghi nhận phiên bản agent và cấu hình thực sự có hiệu lực.
2. Xác định instrumentation nào tạo các span bị nghi ngờ.
3. Kiểm tra các cơ chế tích hợp hoặc loại bỏ span lồng trùng của đúng phiên bản.
4. Trong môi trường thực hành, tắt đúng một nguồn đo nghi ngờ và chạy lại cùng ca.
5. Chỉ giữ thay đổi khi dữ liệu chứng minh đã loại bỏ phần dư mà vẫn giữ liên kết cần thiết.

OpenTelemetry Java agent có cơ chế hạn chế các span lồng nhau trùng dữ liệu và cho phép tắt từng instrumentation. Cơ chế đó không có nghĩa mọi cấu hình tự tạo bên ngoài agent đều tự được xử lý đúng. Tham khảo [tài liệu kiểm soát instrumentation của agent](https://opentelemetry.io/docs/zero-code/java/agent/disable/).

Không sử dụng một công tắc tắt tracing toàn ứng dụng như kết luận chẩn đoán. Nếu mọi span cùng biến mất, ta chỉ mới làm mất dữ liệu, chưa xác định được nguồn tạo phần trùng.

### 5.4. Kiểm tra cấu hình đang chạy

Trong dự án Gradle độc lập dùng để thực hành, có thể đọc các phụ thuộc runtime bằng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-tracing --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opentelemetry --configuration runtimeClasspath
```

Trên PowerShell, dùng `.\gradlew.bat` thay cho `./gradlew`. Với dự án nhiều module, chạy task trên đúng project sở hữu ứng dụng cần kiểm tra.

Cây phụ thuộc cho biết thư viện đến từ đâu; nó chưa chứng minh auto-configuration nào đang hoạt động. Đối chiếu thêm báo cáo điều kiện khởi động của Boot khi dùng `--debug`, các bean registry/tracer/provider/exporter do ứng dụng tạo, cấu hình agent và các profile đang bật.

Thuộc tính đặt trong YAML có thể bị nguồn cấu hình ưu tiên cao hơn thay thế. Hãy ghi nhận giá trị có hiệu lực của định dạng truyền ngữ cảnh, tỷ lệ chọn mẫu, endpoint xuất và cấu hình bật/tắt, thay vì chỉ nhìn một tệp `application.yml`.


## 6. Quy trình tái hiện lỗi có kiểm soát

### 6.1. Thu nhỏ đường đi nhưng giữ đúng ranh giới cần kiểm tra

Chọn một đường xử lý A → B đã biết. Trong lượt đầu, dùng một yêu cầu, không retry và không có lưu lượng nền gây nhiễu. Ghi rõ phiên bản ứng dụng, profile, agent, đích xuất và ý nghĩa của các span dự kiến.

Trong môi trường thực hành dùng tracing do Boot quản lý, có thể cấu hình tạm:

```yaml
management:
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
```

Cấu hình này giúp thử nghiệm cùng một định dạng truyền ngữ cảnh và giảm ảnh hưởng của việc chọn mẫu trong SDK do Boot quản lý. Nó không tự điều khiển sampler của agent hoặc chính sách lấy mẫu/lọc tại Collector. Cũng không khắc phục mất gói, hàng đợi đầy hay exporter sai endpoint.

Thuộc tính `management.tracing.propagation.type` áp dụng cho cả nhận và gửi, đồng thời ghi đè các thuộc tính `consume`/`produce` chi tiết. Nếu hệ thống đang cần nhận nhiều định dạng khi chuyển đổi, phải giữ yêu cầu tương thích đó trong thiết kế sửa; đừng thay toàn hệ thống sang một định dạng chỉ vì ca thử đơn giản đã chạy.

### 6.2. Gửi một ngữ cảnh biết trước

Giả sử hai ứng dụng thực hành đã có `GET /checkout` ở cổng 8080 và `GET /stock` ở cổng 8081; xử lý checkout gọi stock qua HTTP client đã tích hợp truy vết. Đây là điều kiện của kịch bản kiểm tra, không phải hai endpoint do chương trình Java ở phần 7 tạo ra.

Gửi đúng một yêu cầu:

```bash
curl -H "traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-1111111111111111-01" http://localhost:8080/checkout
```

Trên Windows có thể dùng `curl.exe`. Trace ID trong header có 32 ký tự hệ mười sáu, parent ID có 16 ký tự; cả hai đều khác giá trị toàn số không. Cờ cuối `01` thể hiện yêu cầu lấy mẫu trong ngữ cảnh truyền đến.

Khi các ứng dụng chấp nhận ngữ cảnh này theo cấu hình thử nghiệm, cần đối chiếu:

- Span SERVER của A thuộc trace `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, có cha bên ngoài là `1111111111111111`.
- Span CLIENT thực sự gửi đến B có ID riêng và giữ trace đó.
- Header đi từ A sang B có parent ID của span CLIENT này.
- Span SERVER của B giữ trace đó và nối vào span gửi, theo mô hình span riêng đang kiểm tra.

Dùng trace ID mới cho mỗi lượt thử. Gửi nhiều yêu cầu với cùng trace ID cố định sẽ chủ động gom chúng vào một trace, làm việc đếm span dễ bị hiểu sai. Không mong thấy span cha của curl trong hệ thống nhận nếu chưa hề xuất span đó.

Nếu hệ thống có chính sách bắt đầu trace mới ở ranh giới tin cậy, cần đối chiếu chính sách ấy; không kết luận ứng dụng sai chỉ vì nó không tiếp nhận ngữ cảnh bên ngoài trong ca thử.

### 6.3. Thay đổi một giả thuyết trong mỗi lượt

Ví dụ, nếu nghi một interceptor tùy chỉnh tạo CLIENT span thừa:

1. Lưu bằng chứng của lượt có interceptor: ID, kind, quan hệ cha–con, số lần gửi HTTP.
2. Chỉ bỏ phần tạo span của interceptor trong môi trường thử; giữ nguyên hành vi gửi yêu cầu.
3. Gửi một yêu cầu mới với ngữ cảnh mới.
4. Xác nhận span dư biến mất, số lần thực hiện nghiệp vụ không đổi và B vẫn nối đúng vào trace.
5. Chạy lại cả đường thành công và đường có lỗi.

Nếu đồng thời đổi bridge, tắt agent, đổi sampler và đổi exporter, dù giao diện đẹp hơn ta cũng không biết yếu tố nào đã sửa lỗi.

### 6.4. Quan sát tại bộ thu thập

Khi cần phân biệt “ứng dụng tạo lặp” với “pipeline chuyển tiếp lặp”, kiểm tra dữ liệu trước và sau từng chặng. Với OpenTelemetry Collector có các thành phần tương ứng, một cấu hình thực hành cục bộ để nhận OTLP và in dữ liệu có thể là:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
```

Đây là Collector thực hành chỉ in dữ liệu, chưa chuyển tiếp sang hệ thống lưu trace. Ứng dụng gửi vào nó phải dùng đúng giao thức và endpoint tương ứng; thay địa chỉ nhận không có nghĩa đổi được định dạng giao thức.

Đối chiếu trace ID, span ID, parent ID, resource dịch vụ, kind, instrumentation scope và thời điểm. Nếu dữ liệu đã có hai span khác ID trước khi vào Collector, hãy quay lại nguồn tạo span. Nếu nguồn có một bản ghi nhưng đường chuyển tiếp tạo nhiều bản sao cùng ID, tập trung vào pipeline/exporter.

Tên và trường dữ liệu hiển thị phụ thuộc phiên bản. Cách dùng `debug` exporter và kiểm tra từng tầng được hướng dẫn trong [tài liệu chẩn đoán Collector](https://opentelemetry.io/docs/collector/troubleshooting/).

## 7. Thí nghiệm chạy được: một lần làm việc bị bao bởi hai observation

Thí nghiệm này dùng Micrometer Observation trực tiếp để cô lập hiện tượng đo chồng lặp. Nó không chạy HTTP server, không cài agent, không đăng ký handler tạo span và không gửi dữ liệu ra ngoài. Do đó, đầu ra chứng minh số observation được tạo, không phải một bản trace hoàn chỉnh.

Chuẩn bị tệp `ObservationOverlapDemo.java` và thư mục `lib/` chứa `micrometer-observation` cùng `micrometer-commons` ở phiên bản tương thích. Một bộ tái lập thí nghiệm là cả hai ở phiên bản `1.13.0`, thuộc dòng Micrometer dùng với Boot 3.3. Khi tích hợp vào dự án thật, theo bộ phiên bản do dự án quản lý.

Chương trình tạo ba ca, mỗi ca có registry riêng:

- `single`: một observation bao quanh một lần thực hiện công việc.
- `overlap`: hai observation cùng tên bao quanh đúng một lần thực hiện công việc.
- `business-child`: observation bên ngoài và một observation riêng cho bước nghiệp vụ bên trong.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationOverlapDemo {
    private static final class Probe
            implements ObservationHandler<Observation.Context> {
        private final List<String> started = new ArrayList<>();
        private int stopped;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            started.add(context.getName());
        }

        @Override
        public void onStop(Observation.Context context) {
            stopped++;
        }
    }

    public static void main(String[] args) {
        run("single", null);
        run("overlap", "http.server.requests");
        run("business-child", "order.reserve");
    }

    private static void run(String label, String innerName) {
        ObservationRegistry registry = ObservationRegistry.create();
        Probe probe = new Probe();
        registry.observationConfig().observationHandler(probe);
        AtomicInteger work = new AtomicInteger();

        Observation.createNotStarted("http.server.requests", registry)
                .observe(() -> {
                    if (innerName == null) {
                        work.incrementAndGet();
                    } else {
                        Observation.createNotStarted(innerName, registry)
                                .observe(() -> {
                                    work.incrementAndGet();
                                });
                    }
                });

        System.out.printf("%s work=%d started=%s stopped=%d%n",
                label, work.get(), probe.started, probe.stopped);
    }
}
```

Biên dịch và chạy trên PowerShell/Windows, từ thư mục chứa tệp:

```powershell
javac --release 17 -encoding UTF-8 -cp "lib/*" ObservationOverlapDemo.java
java -cp ".;lib/*" ObservationOverlapDemo
```

Trên Linux/macOS, dùng cùng lệnh biên dịch; lệnh chạy đổi dấu phân cách classpath:

```bash
java -cp ".:lib/*" ObservationOverlapDemo
```

Đầu ra chính xác:

```text
single work=1 started=[http.server.requests] stopped=1
overlap work=1 started=[http.server.requests, http.server.requests] stopped=2
business-child work=1 started=[http.server.requests, order.reserve] stopped=2
```

`work=1` trong cả ba ca xác nhận công việc chỉ thực hiện một lần. Số lần đo khác nhau là do cách bọc quanh công việc, không phải do nghiệp vụ bị chạy lại.

Ở ca `overlap`, hai lớp cùng tên `http.server.requests` mô phỏng hai nguồn cùng nhận trách nhiệm đo một ranh giới. Trong ví dụ này ta biết ý nghĩa của hai lớp vì đã viết chúng; ngoài hệ thống thật vẫn phải xác minh bằng dữ liệu và cấu hình.

Ca `business-child` cũng có hai observation, nhưng `order.reserve` biểu diễn một bước riêng. Chỉ nhìn số lượng bằng hai không thể phân biệt hai thiết kế. `stopped` cho thấy các observation ở đây đã được kết thúc; nó cũng chưa chứng minh thiết kế đo lường là hợp lý.

Tên `http.server.requests` được đặt trực tiếp trong thí nghiệm. Đặt tên đó không biến observation thành instrumentation HTTP thật. Khi có handler tracing phù hợp trong ứng dụng, các observation có thể dẫn đến span; còn handler `Probe` ở đây chỉ ghi lại vòng đời để ta quan sát rõ cơ chế.

## 8. Chọn cách sửa theo tầng gây lỗi

### Mất ngữ cảnh qua một lời gọi

Giữ cách tạo và truyền ngữ cảnh thống nhất: dùng client có tích hợp đúng, bảo toàn header cần thiết, đồng bộ định dạng giữa bên gửi/nhận, và truyền ngữ cảnh qua ranh giới luồng. Với span thủ công, quản lý cả lúc bắt đầu, scope và lúc kết thúc.

Không sửa bằng cách chép cùng một chuỗi vào `MDC.traceId` của hai dịch vụ. Cách ấy có thể làm log trông liên quan trong khi dữ liệu span vẫn là hai cây khác nhau.

### Hai nguồn cùng đo một trách nhiệm

Giữ một nguồn sở hữu ranh giới đó. Gỡ phần bọc thủ công dư, bỏ annotation không cần thiết hoặc điều chỉnh instrumentation của đúng thành phần. Giữ lại observation nghiệp vụ có ý nghĩa khác.

Nếu cần đổi metadata của observation có sẵn, dùng cơ chế tùy chỉnh tương ứng. Đổi tên một span dư chỉ làm nó bớt giống span kia trên giao diện, chưa loại bỏ phép đo dư.

### Cùng bản ghi đi qua nhiều đường xuất

Sửa topology exporter/processor/Collector để mỗi bản ghi đi theo các đường có chủ đích. Kiểm tra đích đến thực tế, không chỉ tên cấu hình: hai hostname có thể trỏ về cùng hệ thống tiếp nhận.

Không đổi propagator để xử lý bản ghi xuất lặp. Việc truyền ngữ cảnh và số đường gửi một span hoàn tất thuộc hai vấn đề khác nhau.

### Chỉ thiếu dữ liệu khi truy vấn

Sửa phạm vi truy vấn, bộ lọc, chính sách chọn mẫu hoặc khả năng chuyển dữ liệu ở đúng tầng. Một span đã có đúng `traceId` và `parentId` không cần được tái tạo chỉ để làm giao diện đủ cây.

Không đặt lấy mẫu 100% vĩnh viễn như một cách chữa mọi trace thiếu. Cấu hình thực hành giúp loại trừ một biến; chọn mẫu trong vận hành phải phù hợp tải và mục tiêu quan sát.

## 9. Xác nhận kết quả sửa và thực hành suy luận

Một kết quả sửa có bằng chứng nên đáp ứng các điểm sau:

1. **Liên tục:** tại ranh giới dự kiến tiếp tục trace, bên nhận dùng đúng trace ID và quan hệ cha cần thiết.
2. **Đúng ý nghĩa:** một lần thực hiện không có hai lớp đo cùng một trách nhiệm ngoài thiết kế; các bước khác vai trò vẫn được giữ.
3. **Đúng đường dữ liệu:** không có đường xuất lặp ngoài dự kiến vào cùng đích.
4. **Đúng phạm vi:** sau khi đóng scope hoặc dùng lại luồng, yêu cầu mới không nhận ngữ cảnh của yêu cầu trước.
5. **Giữ hành vi:** số lần thực hiện nghiệp vụ, retry và xử lý lỗi vẫn đúng; việc giảm span không che giấu lỗi thật.
6. **Có thể giải thích:** ghi lại giả thuyết, bằng chứng trước–sau, thay đổi cụ thể và giới hạn của lượt thử.

Sau ca một yêu cầu, thử các yêu cầu độc lập chạy đồng thời và một đường có ngoại lệ. Kiểm tra mỗi yêu cầu giữ ngữ cảnh riêng, scope được đóng và các span dự kiến hoàn tất. Nếu có retry thật, đối chiếu số lần thử với số span thuộc từng lần thử thay vì coi mọi lần thêm là trùng.

### Tình huống A: B đổi trace ID sau một điểm chuyển luồng

A gửi header hợp lệ; B ban đầu đọc cùng trace ID. Sau khi B gửi việc vào executor riêng, lời gọi tiếp theo tạo trace mới. Điểm mất liên tục cần kiểm tra nằm ở đâu?

**Hướng giải thích:** dữ liệu cho thấy ranh giới nhận HTTP ban đầu vẫn đúng. Hãy kiểm tra việc chụp/khôi phục ngữ cảnh và executor thực tế ở điểm gửi việc, rồi đối chiếu tracer trong công việc đích. Chưa có căn cứ đổi định dạng truyền ngữ cảnh trên toàn mạng.

### Tình huống B: hai span giống nhau nhưng hai lần gọi thật

Hai CLIENT span cùng tên gọi kho xuất hiện cách nhau một khoảng ngắn. Nhật ký phía nhận xác nhận lần đầu lỗi, lần sau thành công; mỗi span tương ứng một lần gửi.

**Hướng giải thích:** đây có thể là retry hợp lệ. Cần kiểm tra chính sách retry và quan hệ giữa các lần thử. Xóa một span chỉ vì cùng tên sẽ làm mất thông tin về lỗi và chi phí thực hiện lại.

### Tình huống C: một span ở nguồn, hai bản ghi tại đích

Điểm xuất từ SDK ghi nhận một cặp trace/span ID. Hai pipeline cùng chuyển bản ghi này về một nơi; hệ thống nhận ghi nhận hai lần nhập.

**Hướng giải thích:** ưu tiên kiểm tra đường chuyển tiếp và cơ chế tiếp nhận/gộp dữ liệu. Không có bằng chứng ở đây rằng mã nghiệp vụ hoặc instrumentation đã tạo hai span khác nhau.

### Tình huống D: thiếu cha sau lần thử bằng curl

A có trace ID từ header thử nghiệm và parent ID do người thử chọn, nhưng không thấy span cha trong hệ thống nhận.

**Hướng giải thích:** header truyền quan hệ, không tạo hoặc xuất bản ghi span cha. Nếu curl không hề gửi span cha, sự vắng mặt ấy chưa chứng minh trace bị đứt. Hãy kiểm tra riêng quan hệ A → B mà ca thử thực sự có dữ liệu để chứng minh.
