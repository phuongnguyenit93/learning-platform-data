# responseTimeout và giới hạn bộ đệm

WebTestClient là công cụ kiểm thử ứng dụng Spring WebFlux theo góc nhìn của một HTTP client. Khi kiểm thử endpoint trả lời chậm, response lớn hoặc dữ liệu streaming, hai cấu hình cần được hiểu riêng: **response timeout** giới hạn thời gian client chờ nhận response theo cấu hình của client; **max in-memory size** giới hạn lượng dữ liệu mà codec được phép giữ trong bộ nhớ khi cần buffer hoặc tổng hợp dữ liệu.

Hai giới hạn này giải quyết hai vấn đề khác nhau. Tăng thời gian chờ không giúp đọc được body vượt giới hạn bộ đệm. Tăng bộ đệm cũng không làm một endpoint phản hồi chậm trở nên nhanh hơn. Cấu hình đúng cần dựa trên đặc điểm của endpoint và cách test tiêu thụ response.

## 1. WebTestClient hoạt động ở đâu trong quá trình kiểm thử?

WebTestClient cung cấp API gần giống WebClient nhưng có các assertion dành cho test. Nó có thể gọi WebFlux handler trong môi trường mock hoặc gửi request qua một HTTP connector tới server đang chạy.

Các cách tạo client phổ biến:

~~~java
// Bind trực tiếp vào controller.
WebTestClient controllerClient =
        WebTestClient.bindToController(new OrderController())
                .build();

// Bind vào WebFlux application context.
WebTestClient contextClient =
        WebTestClient.bindToApplicationContext(context)
                .build();

// Bind vào RouterFunction.
WebTestClient routerClient =
        WebTestClient.bindToRouterFunction(routerFunction)
                .build();

// Gửi request qua HTTP connector tới server thật.
WebTestClient serverClient =
        WebTestClient.bindToServer()
                .baseUrl("http://localhost:8080")
                .build();
~~~

Các kiểu bind đầu tiên phù hợp với kiểm thử WebFlux trong cùng tiến trình, không cần mở cổng mạng. bindToServer() phù hợp khi cần kiểm tra giao tiếp HTTP qua connector và server đang chạy, ví dụ Spring Boot integration test với cổng ngẫu nhiên.

Sau khi tạo client từ controller, context hoặc router function, có thể gọi configureClient() để cấu hình phần client:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .configureClient()
        .baseUrl("/api")
        .build();
~~~

responseTimeout và codec của client thuộc cấu hình client. Khi dùng bindToApplicationContext, ứng dụng còn có cấu hình codec phía server riêng. Cần phân biệt hai phía này khi xử lý lỗi bộ đệm.

## 2. responseTimeout là gì?

responseTimeout(Duration) cấu hình thời gian client chờ response. Với WebTestClient.Builder, mặc định response timeout là 5 giây; có thể đặt thời gian khác theo mục đích test:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(10))
        .build();
~~~

Trong ví dụ, client cho phép thời gian chờ response dài hơn 5 giây. Điều này hữu ích với endpoint có công việc xử lý lâu nhưng thời gian hoàn tất vẫn có giới hạn dự kiến, chẳng hạn tạo báo cáo hoặc truy vấn dữ liệu tích hợp.

Với client bind vào WebFlux application context:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ReportController(reportService))
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

Phương thức này là cấu hình thời gian chờ ở phía test client. Nó không thay đổi thời gian timeout của database, HTTP client mà service sử dụng, scheduler, reverse proxy hoặc server connector. Nếu một dependency bên trong service bị treo, timeout của dependency và timeout của test client là các lớp bảo vệ riêng.

### 2.1. Timeout không phải thời gian xử lý tối đa của controller

Giả sử một endpoint trả về Mono<ReportResponse>:

~~~java
@GetMapping("/api/reports/{id}")
public Mono<ReportResponse> getReport(@PathVariable UUID id) {
    return reportService.generate(id);
}
~~~

Client có thể chờ response trong một khoảng thời gian hữu hạn. Nếu response không đến kịp, test thất bại do timeout. Điều đó không chứng minh controller đã dừng xử lý hoặc service đã tự hủy công việc. Việc hủy subscription, hủy request và dừng công việc downstream phụ thuộc cách publisher, connector và dependency triển khai cancellation.

Không nên xem timeout phía test là cơ chế bảo vệ tài nguyên của production. Nếu nghiệp vụ cần giới hạn thời gian gọi database hoặc service khác, cấu hình timeout tại chính dependency hoặc pipeline tương ứng. Nếu server cần giới hạn thời gian xử lý request, hãy cấu hình chính sách ở server và các tầng hạ tầng liên quan.

### 2.2. Timeout của response và timeout khi tiêu thụ body

Response có thể được gửi theo nhiều dạng:

- Response nhỏ được gửi hoàn chỉnh trong thời gian ngắn.
- Response body lớn cần thời gian để truyền và giải mã.
- Response streaming gửi từng phần trong thời gian dài.

responseTimeout là giới hạn chờ response ở phía client connector. Nó không thay thế mọi giới hạn thời gian của một phép kiểm thử. Khi test chủ động tiêu thụ Flux từ response, cần đặt giới hạn thời gian cho việc xác minh publisher, ví dụ StepVerifier.verify(Duration). Với timeout ở từng operator của Reactor, có thể dùng Mono.timeout(...) hoặc Flux.timeout(...) nếu đó là hành vi ứng dụng cần kiểm tra.

Với response streaming dài hạn như Server-Sent Events, một stream có thể được thiết kế để tiếp tục gửi dữ liệu trong thời gian dài. Không nên áp một response timeout ngắn giống endpoint JSON thông thường rồi kết luận stream bị lỗi. Hãy xác định test cần chờ event đầu tiên, chờ một số event, hay xác minh stream duy trì hoạt động trong một khoảng thời gian; mỗi mục tiêu có giới hạn chờ riêng.

## 3. Chọn response timeout theo mục tiêu test

| Loại endpoint | Cách đặt thời gian chờ |
|---|---|
| API CRUD thông thường | Giữ mặc định hoặc đặt một giới hạn ngắn nhưng đủ dư cho CI |
| Truy vấn tích hợp hoặc tạo báo cáo | Đặt thời gian lớn hơn SLA dự kiến của endpoint |
| Endpoint mô phỏng xử lý chậm | Đặt timeout nhỏ có chủ đích để kiểm tra lỗi timeout |
| Server-Sent Events hoặc stream dài hạn | Không dùng timeout ngắn của request thông thường; giới hạn thời gian kiểm tra event bằng cơ chế phù hợp |
| Test cần giới hạn toàn bộ thời gian chạy | Kết hợp timeout của client với giới hạn của test runner hoặc StepVerifier |

Ví dụ tạo một client dành cho nhóm test endpoint báo cáo:

~~~java
static WebTestClient reportClient(WebApplicationContext context) {
    return WebTestClient
            .bindToApplicationContext(context)
            .configureClient()
            .responseTimeout(Duration.ofSeconds(15))
            .build();
}
~~~

Không nên tăng timeout toàn cục lên vài phút chỉ vì một test thỉnh thoảng bị chậm. Trước hết hãy xác định endpoint nào cần thời gian dài, kiểm tra scheduler và dependency, rồi đặt timeout riêng cho client hoặc nhóm test tương ứng. Timeout quá dài khiến lỗi treo bị phát hiện muộn và làm CI mất nhiều thời gian.

## 4. Giới hạn bộ đệm của codec là gì?

WebFlux sử dụng codec để encode request và decode response. Một số codec cần buffer dữ liệu trước khi tạo object Java, chẳng hạn khi đọc một giá trị JSON đơn, chuỗi hoặc byte array. Để tránh một request hoặc response buộc ứng dụng giữ quá nhiều dữ liệu trong bộ nhớ, Spring giới hạn lượng dữ liệu codec được phép buffer.

Trong Spring WebFlux, giá trị mặc định của maxInMemorySize là 256 KB đối với các codec mặc định. Khi thao tác cần buffer vượt quá giới hạn, có thể phát sinh DataBufferLimitException.

Giới hạn này không đơn giản đồng nghĩa “mọi HTTP body đều phải nhỏ hơn 256 KB”. Nó áp dụng cho hoạt động buffer của codec. Với dữ liệu streaming được giải mã tăng dần, codec có thể xử lý từng phần; nhưng một phần tử đơn lẻ hoặc thao tác tổng hợp cần buffer lớn vẫn có thể vượt giới hạn. Cách tiêu thụ response trong test cũng ảnh hưởng tới lượng dữ liệu được giữ trong bộ nhớ.

Ví dụ, các assertion sau thường yêu cầu WebTestClient đọc và tổng hợp body để kiểm tra:

~~~java
client.get()
        .uri("/api/export")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.items").isArray();
~~~

Hoặc:

~~~java
client.get()
        .uri("/api/export")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(ExportItem.class)
        .hasSize(1000);
~~~

Các thao tác gom body hoặc giải mã một cấu trúc lớn có thể cần nhiều bộ nhớ. Nếu dữ liệu vượt giới hạn codec, test có thể thất bại dù server đã trả status 200.

## 5. Cấu hình giới hạn bộ đệm phía client

Khi response body lớn hơn giới hạn mặc định và test thực sự cần decode body đó ở phía client, cấu hình codec của WebTestClient:

~~~java
int maxBytes = 2 * 1024 * 1024;

WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(10))
        .codecs(configurer ->
                configurer.defaultCodecs().maxInMemorySize(maxBytes))
        .build();
~~~

Ví dụ đặt giới hạn buffer của codec client là 2 MB. Với client bind vào application context, có thể cấu hình tương tự sau configureClient():

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(10))
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

Cấu hình này ảnh hưởng codec phía client dùng để encode/decode request và response trong quá trình kiểm thử. Nó không tự thay đổi giới hạn codec của server.

### 5.1. Cấu hình phía server là một việc khác

Nếu server WebFlux cần nhận hoặc xử lý payload lớn, cấu hình ServerCodecConfigurer ở phía ứng dụng:

~~~java
@Configuration
public class WebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Với Spring Boot, thuộc tính spring.codec.max-in-memory-size có thể dùng để cấu hình giới hạn codec mặc định theo cách Boot hỗ trợ:

~~~yaml
spring:
  codec:
    max-in-memory-size: 2MB
~~~

Khi test bằng bindToApplicationContext, WebTestClient sử dụng server handler và codec được cấu hình từ context đó. Khi test bằng bindToServer, server là một tiến trình hoặc ứng dụng khác; thay đổi codec trên WebTestClient chỉ tác động client, không sửa cấu hình server đang chạy.

Nếu response bị lỗi khi WebTestClient decode, hãy kiểm tra giới hạn codec phía client. Nếu request bị từ chối trong lúc server đọc body, hãy kiểm tra codec phía server. Không tăng cả hai giới hạn một cách tự động vì sẽ che khuất phía thực sự gây lỗi và có thể làm tăng đáng kể lượng bộ nhớ được phép sử dụng.

## 6. maxInMemorySize không phải giới hạn kích thước HTTP tổng quát

Các giới hạn sau thuộc những lớp khác nhau:

| Cấu hình/giới hạn | Phạm vi |
|---|---|
| maxInMemorySize của codec | Lượng dữ liệu codec buffer khi encode/decode |
| Giới hạn body của gateway hoặc reverse proxy | Kích thước request/response được hạ tầng cho phép |
| Giới hạn multipart | Số part, kích thước file hoặc cách lưu file tạm |
| Giới hạn header của HTTP connector | Kích thước header và request line |
| Giới hạn database/client | Kích thước truy vấn, kết quả hoặc payload của dependency |
| Giới hạn heap JVM | Tổng bộ nhớ tiến trình có thể sử dụng |

Tăng maxInMemorySize không làm reverse proxy chấp nhận request lớn hơn và không tăng heap JVM. Tương tự, một request body nhỏ hơn giới hạn proxy vẫn có thể làm codec thất bại nếu quá trình decode cần buffer nhiều hơn giới hạn codec.

Đặc biệt, không nên dùng maxInMemorySize để thay thế chính sách giới hạn upload. Với upload file lớn, cân nhắc multipart, streaming, lưu file tạm hoặc object storage; không đọc toàn bộ file vào một byte array nếu không cần thiết.

## 7. Xử lý DataBufferLimitException

DataBufferLimitException cho biết một thao tác buffer vượt giới hạn được cấu hình. Lỗi có thể xuất hiện trong lúc server đọc request body hoặc trong lúc WebTestClient giải mã response. Vị trí xuất hiện quyết định nên điều chỉnh cấu hình nào.

Một số dấu hiệu:

- Stack trace có codec phía client, decoder hoặc WebTestClient body assertion: kiểm tra giới hạn phía client.
- Stack trace có server request decoder hoặc handler đọc body: kiểm tra giới hạn phía server.
- Lỗi chỉ xuất hiện khi dùng expectBody() hoặc gom nhiều phần tử vào collection: xem test có đang tổng hợp toàn bộ response vào bộ nhớ không.
- Lỗi chỉ xuất hiện với một JSON field hoặc một phần tử cực lớn: kiểm tra kích thước từng phần tử và cấu trúc payload.

Không nên bắt DataBufferLimitException rồi trả response thành công hoặc bỏ qua phần body còn lại. Việc đó làm test không còn xác nhận dữ liệu mà client nhận được. Hãy quyết định rõ API có cho phép payload lớn hay không; nếu có, cấu hình giới hạn hữu hạn phù hợp và kiểm tra cả trường hợp nằm trong giới hạn lẫn vượt giới hạn.

## 8. Test response lớn với WebTestClient

Giả sử endpoint trả về một tài liệu JSON có nhiều mục:

~~~java
@RestController
@RequestMapping("/api/exports")
class ExportController {

    @GetMapping
    Mono<ExportResponse> export() {
        return exportService.createExport();
    }
}
~~~

Test có thể cấu hình codec phía client lớn hơn mặc định:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExportControllerTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(15))
                .codecs(configurer ->
                        configurer.defaultCodecs()
                                .maxInMemorySize(4 * 1024 * 1024))
                .build();
    }

    @Test
    void returnsLargeExport() {
        client.get()
                .uri("/api/exports")
                .exchange()
                .expectStatus().isOk()
                .expectBody(ExportResponse.class)
                .value(response ->
                        assertThat(response.items()).isNotEmpty());
    }
}
~~~

Ví dụ này giả định ứng dụng đã cấu hình server codec đủ để tạo và gửi response. Cấu hình 4 MB trong WebTestClient chỉ điều chỉnh phía client. Nếu server cũng buffer dữ liệu lớn, cấu hình phía server cần được xử lý riêng.

Khi response có kích thước lớn, không nhất thiết phải decode toàn bộ thành một object chỉ để kiểm tra một vài đặc tính. Có thể thiết kế endpoint trả dữ liệu theo trang hoặc stream, rồi kiểm tra một số phần tử và điều kiện kết thúc.

## 9. Kiểm thử dữ liệu streaming mà không gom toàn bộ body

WebFlux phù hợp với dữ liệu được phát theo từng phần. Nếu mục tiêu của test là xác minh stream, hãy lấy publisher từ kết quả thay vì dùng assertion buộc gom toàn bộ body.

Ví dụ endpoint phát các tiến độ xử lý:

~~~java
@GetMapping(value = "/api/progress",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ProgressEvent> progress() {
    return progressService.events();
}
~~~

Test có thể nhận FluxExchangeResult và xác minh một số phần tử:

~~~java
FluxExchangeResult<ProgressEvent> result = client.get()
        .uri("/api/progress")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(ProgressEvent.class);

StepVerifier.create(result.getResponseBody())
        .assertNext(event ->
                assertThat(event.status()).isEqualTo("STARTED"))
        .assertNext(event ->
                assertThat(event.progress()).isGreaterThan(0))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

returnResult(...) cho phép test tiếp tục xác minh response body dưới dạng publisher. StepVerifier đăng ký subscriber và kiểm tra các phần tử được phát ra. thenCancel() kết thúc subscription sau khi đã nhận đủ dữ liệu cần kiểm tra; verify(Duration) giới hạn thời gian test chờ publisher.

Với stream dài hạn, không nên gọi collectList() hoặc chuyển toàn bộ publisher thành một collection chỉ để xác minh vài event. Làm vậy sẽ phá lợi ích streaming và có thể gây tiêu thụ bộ nhớ lớn. Nếu cần xác nhận stream kết thúc, dùng verifyComplete() với timeout phù hợp; nếu stream không có chủ đích kết thúc, dùng một số assertion rồi cancel.

## 10. Phân biệt timeout ở các tầng

Trong một test WebFlux có thể có nhiều timeout cùng tồn tại:

| Timeout | Được áp dụng ở đâu | Mục đích |
|---|---|---|
| WebTestClient.responseTimeout(...) | Client kiểm thử | Giới hạn thời gian chờ response theo cấu hình client |
| StepVerifier.verify(Duration) | Test subscriber | Giới hạn thời gian xác minh publisher |
| Mono.timeout(...) / Flux.timeout(...) | Reactor pipeline | Chuyển pipeline sang lỗi timeout nếu publisher không phát tín hiệu đúng hạn |
| block(Duration) | Đoạn code blocking | Giới hạn thời gian thread chờ kết quả |
| JUnit @Timeout | Toàn bộ test method | Giới hạn thời gian chạy test |
| Timeout của HTTP/database client | Dependency gọi ra ngoài | Giới hạn thời gian chờ dependency |
| Timeout ở server/gateway | Hạ tầng hoặc server | Giới hạn thời gian xử lý/kết nối theo chính sách triển khai |

Không nên đặt tất cả timeout cùng một con số mà không hiểu quan hệ giữa chúng. Ví dụ, nếu JUnit timeout ngắn hơn response timeout, test runner có thể dừng test trước khi WebTestClient báo timeout. Nếu dependency timeout dài hơn timeout của endpoint, client có thể bỏ chờ trong khi công việc phía server vẫn còn chạy.

Hãy chọn thời gian theo một ngân sách có thứ tự: dependency nên có giới hạn phù hợp, pipeline có thể có deadline nghiệp vụ, client test cần đủ thời gian nhận kết quả, còn test runner cần một giới hạn tổng thể lớn hơn để phát hiện test treo.

## 11. Kiểm thử timeout một cách ổn định

Không dùng Thread.sleep(...) để giả lập endpoint chậm. sleep chỉ làm thread test chờ một khoảng cố định, không đồng bộ với tín hiệu reactive và dễ gây flaky khi CI chậm.

Có thể tạo publisher có độ trễ có chủ đích:

~~~java
@RestController
class DelayedController {

    @GetMapping("/api/delayed")
    Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(500))
                .thenReturn("done");
    }
}
~~~

Với test bình thường, đặt timeout đủ lớn để response hoàn tất:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new DelayedController())
        .configureClient()
        .responseTimeout(Duration.ofSeconds(2))
        .build();

client.get()
        .uri("/api/delayed")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("done");
~~~

Để kiểm tra timeout ở tầng HTTP connector, nên dùng một client kết nối tới server thật hoặc test server có connector tương ứng và đặt response timeout ngắn hơn thời gian phản hồi dự kiến. Việc này kiểm tra hành vi timeout của connector mà ứng dụng sử dụng; client bind trực tiếp vào controller không thay thế được mọi khác biệt ở network connector.

Khi kiểm tra timeout, tránh so sánh thời gian chạy chính xác đến từng millisecond. Scheduler, tải CPU và môi trường CI đều ảnh hưởng thời gian. Test nên xác minh kết quả timeout hoặc thành công theo một khoảng đủ rộng, không dựa vào thời gian thực thi chính xác.

## 12. Cấu hình giới hạn bộ đệm có trách nhiệm

Khi response hoặc request lớn hơn mặc định, có thể tăng maxInMemorySize lên một giá trị hữu hạn phù hợp:

~~~java
private static final int TEST_CODEC_LIMIT =
        4 * 1024 * 1024;

WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .configureClient()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(TEST_CODEC_LIMIT))
        .build();
~~~

Không nên mặc định đặt giới hạn thành không giới hạn chỉ để test qua. Một response lớn bất thường có thể là lỗi của endpoint, dữ liệu test hoặc một vòng lặp tạo payload ngoài ý muốn. Giới hạn hữu hạn giúp test phát hiện thay đổi kích thước ngoài dự kiến.

Nếu codec hỗ trợ cấu hình maxInMemorySize(-1) để bỏ giới hạn, chỉ dùng khi có lý do rõ ràng và đã kiểm soát kích thước dữ liệu ở một lớp khác. Cấu hình không giới hạn có thể khiến test hoặc ứng dụng tiêu thụ heap lớn nếu body tăng bất thường.

Hãy chọn giá trị dựa trên kích thước payload hợp lệ lớn nhất mà API cam kết hỗ trợ, cộng thêm khoảng dự phòng hợp lý. Đối với endpoint streaming, ưu tiên thiết kế xử lý tăng dần thay vì nâng bộ đệm để giữ toàn bộ stream.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Test lỗi timeout sau vài giây | Response chậm hơn giới hạn client | Xác định thời gian phản hồi dự kiến rồi đặt responseTimeout phù hợp |
| Test timeout dù service vẫn tiếp tục chạy | Timeout phía client không nhất thiết dừng công việc server/dependency | Kiểm tra cancellation và timeout của dependency riêng |
| DataBufferLimitException khi đọc JSON lớn | Codec cần buffer nhiều hơn giới hạn | Xác định lỗi ở client hay server, tăng giới hạn hữu hạn đúng phía hoặc thay cách đọc |
| Test response nhỏ chạy qua, response lớn thất bại | Kích thước dữ liệu vượt giới hạn buffer hoặc cách test đang aggregate | Kiểm tra payload, codec và dùng streaming khi phù hợp |
| Tăng client codec limit nhưng request vẫn bị từ chối | Giới hạn gây lỗi nằm ở server codec hoặc hạ tầng | Cấu hình đúng phía server/proxy |
| Test SSE không kết thúc | Stream được thiết kế dài hạn | Dùng StepVerifier, kiểm tra số event cần thiết rồi cancel |
| Test dùng collectList() tiêu thụ nhiều bộ nhớ | Toàn bộ stream bị gom thành collection | Xác minh theo phần tử hoặc theo điều kiện kết thúc |
| Tăng timeout làm CI chậm hơn | Timeout quá lớn che giấu endpoint treo | Tách test chậm, đặt deadline phù hợp và kiểm tra dependency |

## 14. Quy trình lựa chọn cấu hình cho một test

Khi viết test với WebTestClient, hãy lần lượt xác định:

1. Test bind trực tiếp vào controller/context hay gửi request qua server thật?
2. Endpoint trả response nhỏ, response lớn hay stream dài hạn?
3. Test cần đợi response trong bao lâu theo SLA hoặc đặc tính xử lý?
4. Test có aggregate body vào object, list, string hoặc byte array không?
5. Lỗi buffer phát sinh ở codec phía client hay phía server?
6. Có thể xác minh dữ liệu tăng dần thay vì gom toàn bộ body không?
7. Timeout của client, publisher, dependency và test runner có quan hệ hợp lý không?
8. Giới hạn bộ đệm được đặt hữu hạn và có căn cứ từ hợp đồng dữ liệu không?

Ví dụ, API trả JSON nhỏ chỉ cần timeout mặc định và codec limit mặc định. API tạo báo cáo lớn có thể cần timeout dài hơn và codec limit lớn hơn ở client, đồng thời cấu hình server phù hợp. API SSE nên được kiểm tra bằng publisher và StepVerifier, tránh gom toàn bộ stream vào bộ nhớ.

responseTimeout giúp test phát hiện response không đến trong khoảng thời gian cho phép. maxInMemorySize giúp codec kiểm soát lượng dữ liệu cần buffer. Chọn đúng lớp cấu hình và đúng cách tiêu thụ body sẽ làm test WebFlux ổn định, đồng thời phát hiện được các vấn đề về độ trễ và kích thước payload của API.
