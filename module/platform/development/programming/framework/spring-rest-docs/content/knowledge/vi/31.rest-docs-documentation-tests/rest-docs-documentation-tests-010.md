# Test tài liệu reactive và bất đồng bộ

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, endpoint có thể xử lý request theo mô hình reactive của Spring WebFlux hoặc trả kết quả bất đồng bộ trong Spring MVC. Documentation test cần đợi response thực sự hoàn tất, xác minh status/header/body, rồi mới chuyển exchange cho Spring REST Docs sinh snippet.

Hai mô hình thường gặp:

- **Reactive WebFlux:** controller trả Mono, Flux hoặc kiểu reactive khác; dùng WebTestClient để gửi request và kiểm tra kết quả.
- **Servlet MVC async:** controller trả Callable, DeferredResult hoặc WebAsyncTask; với MockMvc, test khởi tạo async request, chờ kết quả và dispatch lần hai bằng asyncDispatch.

Spring MVC cũng hỗ trợ reactive return types trong một số trường hợp. Hãy xác định application stack và cách endpoint thực sự được thực thi để chọn test client phù hợp.

Sau bài này, bạn có thể:

- Phân biệt reactive WebFlux và async request trong Spring MVC.
- Dùng WebTestClient để kiểm thử và document endpoint reactive.
- Dùng MockMvc với asyncDispatch cho MVC async endpoint.
- Kiểm soát timeout, completion và dữ liệu test để tránh test chập chờn.
- Tài liệu hóa response hữu hạn và hiểu giới hạn với streaming response.

## 1. Phân biệt reactive và Servlet MVC async

| Đặc điểm | Spring WebFlux | Spring MVC async |
| --- | --- | --- |
| Runtime phổ biến | Reactive stack, thường dựa trên Reactor Netty | Servlet container |
| Return type thường gặp | Mono, Flux | Callable, DeferredResult, WebAsyncTask; cũng hỗ trợ reactive types |
| Test client | WebTestClient | MockMvc hoặc client tích hợp phù hợp |
| Cách chờ response | Consume publisher qua exchange | Async dispatch sau khi request chuyển sang trạng thái async |
| Điểm cần chú ý | Publisher phải complete hoặc được giới hạn | Phải chờ async result rồi mới dispatch |

WebTestClient có thể kiểm thử WebFlux trực tiếp hoặc kết nối tới server chạy thật. Nó cũng có thể được cấu hình để kiểm thử Spring MVC. Tên test client không tự xác định application stack.

## 2. Test WebFlux endpoint với WebTestClient

Giả sử controller trả về một sản phẩm bằng Mono:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    @GetMapping("/{id}")
    Mono<ProductResponse> getById(@PathVariable long id) {
        return this.productService.findById(id);
    }
}
```

Test WebTestClient:

```java
this.webTestClient.get()
    .uri("/api/products/{id}", 501)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(501)
    .jsonPath("$.name").isEqualTo("Keyboard")
    .consumeWith(document("products-get",
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm."),
            fieldWithPath("name").description("Tên sản phẩm.")
        )));
```

WebTestClient thực hiện exchange, đợi response body theo cách kiểm thử đã chọn, chạy expectation rồi chuyển kết quả cho REST Docs qua consumeWith(document(...)).

### 2.1. Kiểm tra response body thành object

Có thể deserialize body thành DTO:

```java
this.webTestClient.get()
    .uri("/api/products/{id}", 501)
    .exchange()
    .expectStatus().isOk()
    .expectBody(ProductResponse.class)
    .value(product -> {
        assertThat(product.id()).isEqualTo(501);
        assertThat(product.name()).isEqualTo("Keyboard");
    });
```

Khi cần document cùng exchange, dùng consumeWith(document(...)) trên body spec thay vì tạo request thứ hai chỉ để sinh snippet. Không gửi hai request độc lập nếu endpoint có side effect hoặc dữ liệu thay đổi giữa hai lần.

### 2.2. Test với publisher có độ trễ

Một service có thể trả Mono hoàn tất sau một khoảng thời gian:

```java
Mono<ProductResponse> findById(long id) {
    return Mono.delay(Duration.ofMillis(20))
            .map(ignored -> repository.findResponse(id));
}
```

WebTestClient chờ exchange hoàn tất theo timeout cấu hình. Nên đặt timeout hữu hạn và đủ lớn cho CI:

```java
this.webTestClient = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
```

Không dùng Thread.sleep để đoán khi nào publisher hoàn tất. Chờ completion qua reactive test client hoặc Reactor StepVerifier cho test ở tầng publisher.

## 3. Kiểm thử Flux hữu hạn

Endpoint có thể trả danh sách bằng Flux:

```java
@GetMapping
Flux<ProductResponse> list() {
    return this.productService.findAll();
}
```

Nếu publisher hoàn tất sau một số phần tử hữu hạn, có thể kiểm tra JSON array:

```java
this.webTestClient.get()
    .uri("/api/products")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("""
            [
              {"id": 501, "name": "Keyboard"},
              {"id": 502, "name": "Mouse"}
            ]
            """)
    .consumeWith(document("products-list",
        responseFields(
            fieldWithPath("[].id").description("Mã sản phẩm."),
            fieldWithPath("[].name").description("Tên sản phẩm.")
        )));
```

Đây là ví dụ response serialize thành JSON array hữu hạn. Cấu trúc JSON và field path phải khớp output thật của ứng dụng và REST Docs version đang dùng.

Với dữ liệu danh sách, fixture nên cố định và thứ tự chỉ được assert nếu API cam kết thứ tự. Nếu API không cam kết, kiểm tra nội dung theo tập giá trị hoặc sắp xếp dữ liệu ở tầng test theo quy tắc rõ ràng.

## 4. Test stream liên tục và SSE

Không phải Flux nào cũng complete. Ví dụ server-sent events:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<Notification>> events() {
    return notificationService.stream();
}
```

Stream vô hạn không thể được xử lý như JSON array hoàn chỉnh. Nếu test chờ body complete, nó có thể timeout vì publisher không kết thúc.

Các lựa chọn:

- Dùng publisher hữu hạn trong test fixture, ví dụ phát hai event rồi complete.
- Dùng take(n) ở nguồn test hoặc cấu hình mock service để giới hạn số event.
- Kiểm tra media type, event format và một số event đầu bằng cơ chế streaming phù hợp.
- Tài liệu hóa định dạng event, tên event, data schema và chính sách reconnect bằng ví dụ có chủ đích.

Không dùng stream vô hạn thật làm nguồn sinh snippet trong documentation test. Test cần điểm kết thúc xác định để hoàn tất assertion và ghi artifact.

Ví dụ publisher hữu hạn:

```java
when(notificationService.stream())
    .thenReturn(Flux.just(
            new Notification("created", 501),
            new Notification("updated", 501)
    ));
```

Publisher complete sau hai event, giúp test có thể kiểm tra dữ liệu và kết thúc. Cách assert/document body của SSE phụ thuộc adapter và cách WebTestClient consume streaming response; không áp dụng JSON payload snippet cho event stream nếu representation thực tế là text/event-stream.

## 5. Spring MVC async với MockMvc

Spring MVC có thể trả kết quả bất đồng bộ bằng Callable:

```java
@GetMapping("/report")
Callable<ReportResponse> report() {
    return reportService::generate;
}
```

MockMvc xử lý kiểu request này theo hai pha:

1. Thực hiện request ban đầu và nhận trạng thái async started.
2. Chờ async result, sau đó dispatch request lần hai để kiểm tra response cuối.

Ví dụ:

```java
MvcResult mvcResult = this.mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvcResult.getAsyncResult(3_000);

this.mockMvc.perform(asyncDispatch(mvcResult))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.status").value("READY"))
    .andDo(document("report-get",
        responseFields(
            fieldWithPath("status").description("Trạng thái báo cáo."),
            fieldWithPath("downloadUrl").description("Đường dẫn tải báo cáo.")
        )));
```

asyncDispatch(mvcResult) là bước quan trọng: nó dispatch kết quả async đã hoàn tất qua MVC pipeline để assertion và REST Docs nhìn thấy response cuối cùng.

Không gọi document(...) ngay sau request ban đầu nếu response chưa được hoàn tất. Khi đó exchange có thể chưa có status/body cuối cùng mà tài liệu cần ghi.

### 5.1. Đặt timeout cho async request

MockMvc có thể cấu hình async request timeout. Test nên dùng giới hạn phù hợp và kiểm tra timeout behavior nếu đó là hợp đồng:

```java
MvcResult mvcResult = this.mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

mvcResult.getAsyncResult(3_000);

this.mockMvc.perform(asyncDispatch(mvcResult))
    .andExpect(status().isOk())
    .andDo(document("report-get"));
```

getAsyncResult chờ tối đa số milliseconds được truyền vào và ném lỗi nếu không có kết quả trong thời gian đó. Không tăng timeout quá lớn để che giấu deadlock hoặc publisher không hoàn tất.

### 5.2. DeferredResult và WebAsyncTask

Controller dùng DeferredResult hoặc WebAsyncTask cũng có thể kiểm thử theo mô hình async dispatch nếu request được xử lý bất đồng bộ bởi Spring MVC:

```java
MvcResult result = this.mockMvc.perform(get("/api/summary"))
    .andExpect(request().asyncStarted())
    .andReturn();

this.mockMvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andDo(document("summary-get"));
```

Với DeferredResult, test cần kích hoạt callback hoàn tất hoặc dùng service giả lập hoàn tất có kiểm soát. Nếu không, request sẽ tiếp tục pending đến timeout.

## 6. Phân biệt timeout với response lỗi

Timeout của tác vụ bất đồng bộ không nhất thiết tương đương một status cụ thể trong mọi ứng dụng. Kết quả phụ thuộc timeout cấu hình, exception handler và cách framework chuyển lỗi thành HTTP response.

Nếu timeout là hành vi API cần công bố:

- Cố định timeout trong test.
- Làm cho tác vụ test không hoàn tất trong giới hạn đã chọn.
- Assert status và error body theo exception handling thực tế.
- Dùng operation ID riêng, ví dụ report-get-timeout.
- Không để timeout test phụ thuộc tải máy hoặc sleep ngẫu nhiên.

Nếu timeout chỉ là lỗi hạ tầng test, hãy xử lý nguyên nhân publisher/task không complete thay vì tài liệu hóa nó như một response hợp lệ.

## 7. Kết hợp assertion và REST Docs

Dù endpoint reactive hay async, nguyên tắc vẫn là:

1. Gửi request bằng client phù hợp.
2. Chờ response hoàn tất theo đúng lifecycle.
3. Assert status, headers và body.
4. Chuyển exchange hoàn chỉnh cho REST Docs.
5. Dùng descriptor mô tả request/response.

Ví dụ WebTestClient:

```java
this.webTestClient.get()
    .uri("/api/products/{id}", 501)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo(501)
    .consumeWith(document("products-get",
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm."),
            fieldWithPath("name").description("Tên sản phẩm.")
        )));
```

Ví dụ MockMvc async:

```java
MvcResult result = this.mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

this.mockMvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.status").value("READY"))
    .andDo(document("report-get"));
```

Không tạo snippet từ request ban đầu chưa có response cuối, và không dùng assertion chỉ xác nhận async started như bằng chứng endpoint đã hoàn tất thành công.

## 8. Kiểm thử lỗi trong reactive/async endpoint

Reactive publisher có thể phát lỗi bằng Mono.error hoặc Flux.error. Spring WebFlux xử lý lỗi qua exception handler tương ứng.

Ví dụ:

```java
when(productService.findById(9999))
    .thenReturn(Mono.error(new ProductNotFoundException(9999)));

this.webTestClient.get()
    .uri("/api/products/{id}", 9999)
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
    .consumeWith(document("products-get-not-found",
        responseFields(
            fieldWithPath("code").description("Mã lỗi."),
            fieldWithPath("message").description("Thông điệp lỗi.")
        )));
```

Đây là ví dụ minh họa; kiểu exception và error response phải khớp ứng dụng. Với MVC async, exception từ Callable/DeferredResult cũng cần được kiểm tra sau async dispatch và qua exception handling thực tế.

## 9. Test xác định và độc lập

Bất đồng bộ làm tăng nguy cơ test chập chờn nếu phụ thuộc vào thời gian hoặc thứ tự thực thi.

Nên:

- Dùng publisher hữu hạn trong documentation tests.
- Dùng scheduler/test executor có thể kiểm soát khi cần.
- Tránh Thread.sleep để đợi tác vụ hoàn tất.
- Đặt timeout hữu hạn, hợp lý cho môi trường CI.
- Dùng fixture cố định và mock dependency ở đúng ranh giới.
- Không dùng cùng operation ID cho response success và timeout/error.
- Reset state giữa các test và không phụ thuộc thứ tự chạy.
- Chỉ include snippet sau khi response cuối đã được assert.

Với Reactor, StepVerifier phù hợp để kiểm tra publisher ở tầng service. Tuy nhiên, StepVerifier không thay thế HTTP-level documentation test: REST Docs cần exchange HTTP thực tế qua test client/REST Docs integration.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| MockMvc test chỉ thấy async started | Chưa gọi asyncDispatch | Chờ kết quả rồi dispatch lần hai |
| asyncDispatch timeout | Callable/DeferredResult chưa complete hoặc timeout quá ngắn | Kiểm tra executor/callback và timeout |
| WebTestClient test treo | Mono/Flux không complete hoặc response là stream liên tục | Dùng fixture hữu hạn hoặc kiểm tra streaming có giới hạn |
| Snippet body rỗng | Document trước khi response hoàn tất hoặc endpoint không có body | Đặt document sau expectation/async dispatch |
| Test chập chờn trên CI | Dùng sleep, scheduler hoặc thời gian phụ thuộc máy | Đồng bộ bằng completion và timeout hợp lý |
| SSE bị parse như JSON | Content-Type/representation không phải application/json | Assert text/event-stream và kiểm tra event theo giao thức |
| Timeout bị nhầm là status 504 | Framework/application chưa được cấu hình trả 504 | Assert response thực tế theo exception handling |
| Test reactive pass nhưng endpoint production lỗi | Chỉ test publisher/service, chưa test HTTP layer | Thêm WebTestClient documentation test |
| Operation snippet bị ghi đè | Success và error dùng chung operation ID | Tách operation ID |

## 11. Bài thực hành

1. Tạo WebFlux endpoint GET /api/products/{id} trả Mono<ProductResponse>.
2. Viết WebTestClient test, assert status, Content-Type và JSON body; tạo operation products-get.
3. Tạo endpoint list trả Flux<ProductResponse> hữu hạn; kiểm tra JSON array và document field.
4. Tạo test reactive error bằng Mono.error; assert 404 và document error body bằng operation ID riêng.
5. Tạo Spring MVC endpoint trả Callable<ReportResponse>.
6. Viết MockMvc test xác nhận async started, chờ async result và dùng asyncDispatch trước khi document.
7. Tạo test timeout có kiểm soát nếu timeout thuộc hợp đồng; assert status/error response thực tế.
8. Thử một SSE stream hữu hạn; xác định representation và cách kiểm tra event phù hợp thay vì dùng JSON array snippet.

**Câu hỏi tự đánh giá**

1. WebFlux reactive khác Spring MVC async ở điểm nào?
2. Vì sao MockMvc cần asyncDispatch với request async?
3. WebTestClient chờ Mono/Flux hoàn tất như thế nào trong response test thông thường?
4. Vì sao publisher vô hạn không phù hợp để sinh một body snippet hoàn chỉnh?
5. Khi nào StepVerifier hữu ích và vì sao nó không thay thế HTTP documentation test?
6. Timeout test khác response timeout mà API công bố như thế nào?
7. Vì sao cần operation ID riêng cho reactive success và error?
8. Làm sao giữ documentation test async ổn định trên CI?

## Tài liệu tham khảo chính thức

- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử WebFlux và HTTP exchange.
- [Spring Framework — WebFlux Testing](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): kiểm thử controller và reactive web layer.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): kiểm tra async request và async dispatch.
- [Spring REST Docs — WebTestClient](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation-snippets.html): tích hợp REST Docs với WebTestClient.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier và kiểm thử publisher.
- [Spring Framework — MVC Async](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): Callable, DeferredResult và xử lý request bất đồng bộ.

**Kết luận thực hành:** Với WebFlux, dùng WebTestClient để chờ và kiểm tra exchange reactive; với Spring MVC async, chờ async result và gọi asyncDispatch trước khi document. Dùng publisher hữu hạn, timeout xác định và operation ID riêng cho các nhánh response khác nhau. Với stream liên tục như SSE, tài liệu hóa giao thức và event mẫu theo cách phù hợp thay vì chờ một body vô hạn hoàn tất như JSON thông thường.
