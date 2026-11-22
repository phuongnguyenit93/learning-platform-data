# returnResult để truy cập ExchangeResult

**Ngữ cảnh:** Spring Framework Testing → Xác nhận HTTP phản ứng.

Khi kiểm thử HTTP bằng **WebTestClient**, các phương thức như **expectStatus()**, **expectHeader()** và **expectBody()** giúp xác nhận response ngay trong một chuỗi fluent. Tuy nhiên, có những tình huống cần giữ lại toàn bộ kết quả để đọc nhiều thuộc tính, truyền dữ liệu sang bước kiểm tra tiếp theo, dùng AssertJ hoặc kiểm thử một luồng reactive.

Phương thức **returnResult(...)** kết thúc phần khai báo expectation và trả về một đối tượng kết quả. Tùy cách đọc body, kết quả có thể là:

- **EntityExchangeResult<T>:** giữ response body đã được đọc thành một giá trị Java, cùng metadata của HTTP exchange.
- **FluxExchangeResult<T>:** giữ response body dưới dạng Flux để kiểm tra từng phần tử của luồng, phù hợp với dữ liệu streaming.
- **ExchangeResult:** lớp cơ sở cung cấp thông tin request và response như URL, method, headers, status, cookies và dữ liệu body đã được capture.

Hiểu đúng các kiểu kết quả này giúp chọn cách đọc body phù hợp, kiểm tra metadata mà không phải gửi request lần thứ hai và xử lý đúng những endpoint trả dữ liệu liên tục.

## 1. Vị trí của returnResult trong WebTestClient

WebTestClient gửi request qua một client test và cung cấp response để kiểm tra. Client có thể được bind với controller, application context, router function hoặc một server thật. Dù dùng kiểu binding nào, phần xác nhận HTTP vẫn có thể sử dụng các API expectation tương tự.

Luồng xử lý cơ bản:

~~~text
WebTestClient request
        |
        v
exchange()
        |
        v
HTTP response / ExchangeResult
        |
        +--> expectStatus()
        |
        +--> expectHeader()
        |
        +--> expectBody(...)
        |       |
        |       +--> consumeWith(...)
        |       +--> returnResult() -> EntityExchangeResult<T>
        |
        +--> returnResult(Type) -> FluxExchangeResult<T>
~~~

**returnResult** cho phép rời khỏi chuỗi expectation và lấy kết quả để kiểm tra bằng code Java thông thường. Nó đặc biệt hữu ích khi cần:

- Đọc nhiều response header hoặc cookie.
- Lấy body thành DTO, list hoặc byte array.
- Truyền body cho assertion AssertJ.
- Dùng **assertWithDiagnostics** để bổ sung request/response khi assertion thất bại.
- Đọc một luồng reactive và xác nhận các phần tử bằng **StepVerifier**.
- Viết helper trả về kiểu kết quả cụ thể cho nhiều test.

Không phải request nào cũng cần returnResult. Nếu chỉ cần xác nhận status, content type và một vài trường JSON, các expectation trực tiếp thường ngắn gọn và dễ đọc hơn.

## 2. Các kiểu ExchangeResult

### 2.1. ExchangeResult

**ExchangeResult** là lớp cơ sở đại diện cho thông tin của một HTTP exchange. Nó lưu thông tin về request và response mà WebTestClient quan sát được.

Các phương thức thường dùng:

| Phương thức | Thông tin |
|---|---|
| getUrl() | URI của request |
| getMethod() | HTTP method |
| getRequestHeaders() | Header của request |
| getResponseHeaders() | Header của response |
| getStatus() | HTTP status |
| getResponseCookies() | Cookie trong response |
| getRequestBodyContent() | Request body bytes nếu có thể capture |
| getResponseBodyContent() | Response body bytes nếu có thể capture |
| getLogPrefix() | Prefix dùng cho thông tin log |
| assertWithDiagnostics(...) | Chạy assertion và bổ sung thông tin exchange khi assertion thất bại |

ExchangeResult tập trung vào dữ liệu ở ranh giới HTTP. Nó không phải một đối tượng chứa toàn bộ trạng thái nội bộ của server. Chẳng hạn, nó không thay thế ServerWebExchange, không cung cấp trực tiếp bean/controller đã xử lý request và không tự phơi bày mọi exception nội bộ của ứng dụng.

### 2.2. EntityExchangeResult<T>

**EntityExchangeResult<T>** kế thừa ExchangeResult và bổ sung response body đã được giải mã thành một giá trị Java kiểu T.

Ví dụ:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .returnResult();

OrderResponse order = result.getResponseBody();
~~~

Ở đây, OrderResponse.class chỉ định kiểu mà WebTestClient dùng để đọc body. Nếu JSON không thể giải mã thành kiểu đó, lỗi xảy ra trong bước đọc body và test thất bại trước khi có một kết quả entity hoàn chỉnh.

**getResponseBody()** trả về đối tượng đã giải mã. Có thể dùng nó trong AssertJ, truyền cho helper hoặc kiểm tra nhiều thuộc tính mà không cần parse JSON thủ công.

### 2.3. FluxExchangeResult<T>

**FluxExchangeResult<T>** cũng kế thừa ExchangeResult nhưng response body được biểu diễn dưới dạng **Flux<T>**.

Ví dụ:

~~~java
FluxExchangeResult<OrderEvent> result = webTestClient.get()
        .uri("/orders/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(OrderEvent.class);

Flux<OrderEvent> events = result.getResponseBody();
~~~

Kiểu kết quả này phù hợp với endpoint trả dữ liệu reactive hoặc streaming. Test có thể dùng StepVerifier để kiểm tra phần tử, thứ tự, số lượng, lỗi hoặc thời điểm hoàn tất của luồng.

Không nên thu thập một luồng không giới hạn thành List chỉ để dùng assertion đơn giản. Với SSE hoặc stream dài hạn, hãy kiểm tra một số phần tử cần thiết rồi hủy subscription có chủ đích.

### 2.4. Chọn kiểu kết quả nào?

| Nhu cầu | Cách dùng | Kiểu kết quả |
|---|---|---|
| Đọc một JSON object thành DTO | expectBody(OrderResponse.class).returnResult() | EntityExchangeResult<OrderResponse> |
| Đọc JSON array hữu hạn thành List | expectBodyList(OrderResponse.class).returnResult() | EntityExchangeResult<List<OrderResponse>> |
| Đọc body thô dạng bytes | expectBody().returnResult() | EntityExchangeResult<byte[]> |
| Kiểm tra stream reactive | returnResult(OrderEvent.class) | FluxExchangeResult<OrderEvent> |
| Kiểm tra Server-Sent Events | returnResult(ParameterizedTypeReference<ServerSentEvent<T>>) | FluxExchangeResult<ServerSentEvent<T>> |

Quy tắc chính là phân biệt body đã được gom và giải mã thành một giá trị với body vẫn được cung cấp như một publisher. Endpoint trả một JSON object thường phù hợp với EntityExchangeResult. Endpoint streaming thường phù hợp với FluxExchangeResult.

## 3. Lấy EntityExchangeResult cho response DTO

### 3.1. Đọc một đối tượng JSON

Giả sử endpoint trả về:

~~~java
record OrderResponse(long id, String status) {}
~~~

Test có thể lấy kết quả:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .returnResult();
~~~

Sau đó xác nhận body và metadata:

~~~java
assertThat(result.getResponseBody())
        .isEqualTo(new OrderResponse(42L, "PAID"));

assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
assertThat(result.getResponseHeaders().getContentType())
        .isCompatibleWith(MediaType.APPLICATION_JSON);
~~~

Lợi ích là request chỉ được gửi một lần. Test lấy được cả body đã giải mã và metadata của response trong cùng một kết quả.

### 3.2. Đọc JSON với generic type

Khi response có kiểu generic, ví dụ một envelope chứa dữ liệu, cần cung cấp đầy đủ kiểu bằng **ParameterizedTypeReference** để tránh mất thông tin do type erasure.

~~~java
record ApiEnvelope<T>(T data, String requestId) {}

EntityExchangeResult<ApiEnvelope<OrderResponse>> result =
        webTestClient.get()
                .uri("/orders/42/envelope")
                .exchange()
                .expectStatus().isOk()
                .expectBody(
                        new ParameterizedTypeReference<
                                ApiEnvelope<OrderResponse>>() {})
                .returnResult();

ApiEnvelope<OrderResponse> envelope = result.getResponseBody();

assertThat(envelope.data().id()).isEqualTo(42L);
assertThat(envelope.requestId()).isNotBlank();
~~~

Nếu chỉ truyền ApiEnvelope.class, kiểu tham số T có thể không được giữ đầy đủ cho quá trình deserialize. Dùng ParameterizedTypeReference khi kiểu response lồng generic như ApiEnvelope<OrderResponse>, Map<String, List<OrderResponse>> hoặc cấu trúc tương tự.

### 3.3. Đọc danh sách hữu hạn

Với JSON array, có thể dùng **expectBodyList**:

~~~java
EntityExchangeResult<List<OrderResponse>> result =
        webTestClient.get()
                .uri("/orders")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(OrderResponse.class)
                .returnResult();

List<OrderResponse> orders = result.getResponseBody();

assertThat(orders)
        .extracting(OrderResponse::id)
        .containsExactly(41L, 42L, 43L);
~~~

Body được đọc thành một List khi response hoàn tất. Cách này phù hợp với endpoint trả collection hữu hạn. Nếu endpoint trả Flux không kết thúc hoặc stream liên tục, việc chờ body thành List có thể khiến test không hoàn tất.

### 3.4. Đọc body thô

Nếu cần kiểm tra bytes, encoding hoặc một định dạng chưa có decoder thành DTO, dùng body không chỉ định kiểu:

~~~java
EntityExchangeResult<byte[]> result = webTestClient.get()
        .uri("/reports/export")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .returnResult();

byte[] bytes = result.getResponseBody();

assertThat(bytes).isNotEmpty();
assertThat(result.getResponseHeaders().getContentType())
        .isEqualTo(MediaType.APPLICATION_PDF);
~~~

Có thể chuyển bytes thành String khi body thực sự là text và biết encoding:

~~~java
String body = new String(
        result.getResponseBody(),
        StandardCharsets.UTF_8
);
~~~

Với file binary, không nên chuyển thành String để kiểm tra. Hãy kiểm tra byte content, content length, content type, checksum hoặc cấu trúc file bằng thư viện phù hợp.

## 4. Truy cập metadata của HTTP exchange

Một lý do quan trọng để lấy ExchangeResult là kiểm tra nhiều metadata mà không cần gửi request lần nữa.

### 4.1. Kiểm tra URL, method và request headers

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .header("X-Request-Source", "integration-test")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

assertThat(result.getMethod()).isEqualTo(HttpMethod.GET);
assertThat(result.getUrl().getPath()).isEqualTo("/orders/42");
assertThat(result.getRequestHeaders().getFirst("X-Request-Source"))
        .isEqualTo("integration-test");
~~~

Thông tin này hữu ích khi test dùng URI builder, base URL, default header hoặc nhiều biến thể request. Có thể xác nhận request được tạo với method và header đúng như mong đợi.

### 4.2. Kiểm tra response headers

~~~java
HttpHeaders headers = result.getResponseHeaders();

assertThat(headers.getContentType())
        .isCompatibleWith(MediaType.APPLICATION_JSON);

assertThat(headers.getFirst(HttpHeaders.CACHE_CONTROL))
        .contains("no-store");
~~~

Có thể kiểm tra các header như:

- Content-Type và Content-Length.
- Cache-Control, ETag và Last-Modified.
- Location cho response redirect.
- Header correlation hoặc request id.
- Header bảo mật theo hợp đồng của API.

Không nên khẳng định một header luôn tồn tại nếu nó chỉ xuất hiện trong một profile hoặc một cấu hình server cụ thể. Test cần phản ánh contract mà endpoint thực sự cam kết.

### 4.3. Kiểm tra response cookies

ExchangeResult cung cấp response cookies dưới dạng MultiValueMap:

~~~java
MultiValueMap<String, ResponseCookie> cookies =
        result.getResponseCookies();

ResponseCookie sessionCookie = cookies.getFirst("SESSION");

assertThat(sessionCookie).isNotNull();
assertThat(sessionCookie.isHttpOnly()).isTrue();
assertThat(sessionCookie.isSecure()).isTrue();
~~~

Ví dụ trên phù hợp khi ứng dụng phát hành cookie session hoặc cookie bảo mật. Với môi trường test HTTP thuần, thuộc tính Secure có thể phụ thuộc cấu hình HTTPS hoặc profile; hãy cấu hình test đúng với contract đang xác nhận.

Cookie có thể chứa thông tin nhạy cảm. Không in giá trị cookie thật vào log chia sẻ. Khi cần chẩn đoán, chỉ ghi tên cookie và các thuộc tính an toàn cần kiểm tra.

### 4.4. Phân biệt request body và response body content

ExchangeResult có thể cung cấp byte content của request/response khi nội dung đã được capture trong exchange tương ứng:

~~~java
byte[] requestBytes = result.getRequestBodyContent();
byte[] responseBytes = result.getResponseBodyContent();
~~~

Các phương thức này hữu ích cho chẩn đoán ở mức wire content hoặc khi cần xem bytes. Nếu body đã được giải mã thành DTO, nên ưu tiên EntityExchangeResult.getResponseBody() cho assertion nghiệp vụ. Không cần parse lại bytes chỉ để xác nhận một thuộc tính đã có trong DTO.

Đối với response streaming, không nên giả định toàn bộ luồng đã được gom thành một mảng byte hoàn chỉnh. Dùng FluxExchangeResult và kiểm tra publisher khi nội dung được phát theo từng phần.

## 5. Dùng assertWithDiagnostics khi assertion thất bại

### 5.1. Vấn đề khi assert sau returnResult

Sau khi lấy kết quả, có thể viết assertion AssertJ:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

assertThat(result.getResponseBody().status()).isEqualTo("PAID");
~~~

Nếu assertion thất bại, thông báo thường cho biết giá trị mong đợi và thực tế. Tuy nhiên, khi chỉ nhìn vào assertion, có thể thiếu request URI, method, status hoặc response headers để hiểu vì sao kết quả sai.

### 5.2. Bao assertion bằng assertWithDiagnostics

**assertWithDiagnostics(...)** cho phép chạy assertion và bổ sung thông tin HTTP exchange vào thông báo khi assertion ném AssertionError.

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

result.assertWithDiagnostics(() ->
        assertThat(result.getResponseBody())
                .isEqualTo(new OrderResponse(42L, "PAID"))
);
~~~

Nếu assertion thất bại, chẩn đoán có thể bao gồm request và response liên quan đến ExchangeResult. Điều này giúp biết assertion đang thất bại trên request nào và response thực tế ra sao.

Có thể nhóm nhiều assertion liên quan trong một Runnable:

~~~java
result.assertWithDiagnostics(() -> {
    assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
    assertThat(result.getResponseHeaders().getContentType())
            .isCompatibleWith(MediaType.APPLICATION_JSON);

    assertThat(result.getResponseBody().status())
            .isEqualTo("PAID");
});
~~~

Dùng một khối diagnostics cho các assertion thuộc cùng một HTTP exchange. Không đưa assertion của nhiều request không liên quan vào cùng một khối vì khi thất bại sẽ khó xác định request nào gây lỗi.

### 5.3. Kết hợp với AssertJ và helper

Có thể viết helper nhận ExchangeResult để tái sử dụng kiểm tra:

~~~java
void assertJsonResponseHeaders(ExchangeResult result) {
    result.assertWithDiagnostics(() -> {
        assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
        assertThat(result.getResponseHeaders().getContentType())
                .isCompatibleWith(MediaType.APPLICATION_JSON);
    });
}
~~~

Helper nên nhận kết quả đã được tạo, không tự gửi request bên trong. Nhờ vậy request chỉ thực hiện một lần và mọi assertion cùng tham chiếu một response.

Nếu cần kiểm tra một body typed, có thể viết helper nhận EntityExchangeResult<OrderResponse> thay vì chỉ ExchangeResult. Kiểu tham số cụ thể giúp compiler hỗ trợ truy cập body và tránh ép kiểu không cần thiết.

## 6. returnResult cho reactive stream

### 6.1. Vì sao stream cần cách kiểm tra khác?

Một endpoint có thể trả về Flux thay vì một object hoặc List. Ví dụ:

~~~java
@GetMapping(value = "/orders/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<OrderEvent> events() {
    return eventService.events();
}
~~~

Flux có thể phát nhiều phần tử theo thời gian và có thể không hoàn tất. Nếu test dùng expectBodyList để gom toàn bộ nội dung, nó sẽ chờ stream kết thúc. Với SSE hoặc event stream liên tục, điều đó không xảy ra theo thiết kế.

Trong trường hợp này, lấy **FluxExchangeResult** để truy cập publisher và dùng **StepVerifier** để kiểm tra hành vi của luồng.

### 6.2. Lấy FluxExchangeResult

Với kiểu dữ liệu đơn giản:

~~~java
FluxExchangeResult<OrderEvent> result = webTestClient.get()
        .uri("/orders/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(OrderEvent.class);
~~~

Sau đó xác nhận stream:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                event.type().equals("ORDER_CREATED"))
        .expectNextMatches(event ->
                event.type().equals("ORDER_PAID"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

returnResult(OrderEvent.class) yêu cầu WebTestClient giải mã các phần tử response thành OrderEvent và cung cấp chúng qua Flux. StepVerifier subscribe vào Flux, kiểm tra thứ tự phần tử và chủ động hủy sau các sự kiện cần thiết.

Nếu stream là hữu hạn, có thể xác nhận hoàn tất:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(3)
        .verifyComplete();
~~~

Chỉ dùng verifyComplete() khi endpoint được kỳ vọng kết thúc. Với stream dài hạn, dùng thenCancel() sau khi đã xác nhận các phần tử cần thiết.

### 6.3. Kiểm tra Server-Sent Events

Nếu endpoint trả SSE, body có thể được giải mã thành ServerSentEvent<T>:

~~~java
FluxExchangeResult<ServerSentEvent<OrderEvent>> result =
        webTestClient.get()
                .uri("/orders/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                        new ParameterizedTypeReference<
                                ServerSentEvent<OrderEvent>>() {}
                );
~~~

Kiểm tra event name và data:

~~~java
StepVerifier.create(result.getResponseBody())
        .assertNext(event -> {
            assertThat(event.event()).isEqualTo("order-created");
            assertThat(event.data()).isNotNull();
            assertThat(event.data().orderId()).isEqualTo(42L);
        })
        .thenCancel()
        .verify();
~~~

Dùng ParameterizedTypeReference để giữ kiểu generic của ServerSentEvent<OrderEvent>. Nếu chỉ dùng raw ServerSentEvent.class, kiểu data lồng bên trong có thể không được giải mã thành OrderEvent như mong muốn.

### 6.4. Giới hạn thời gian khi xác nhận stream

Một test reactive nên có timeout phù hợp để không chờ vô hạn khi server không phát dữ liệu hoặc stream không hoàn tất như dự kiến.

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Timeout cần đủ lớn cho môi trường CI nhưng vẫn đủ ngắn để phát hiện lỗi treo. Không đặt timeout quá thấp khiến test chập chờn khi CI tải cao.

Với stream có nhịp phát sự kiện theo thời gian, có thể dùng các bước kiểm tra thời gian của StepVerifier khi thời điểm phát là một phần của contract. Tránh kiểm tra thời gian chính xác quá chặt nếu scheduler hoặc môi trường thực thi không bảo đảm độ chính xác đó.

## 7. Phân biệt returnResult với consumeWith

WebTestClient cung cấp cả **consumeWith(...)** và **returnResult()** sau bước đọc body. Hai cách đều cho phép truy cập kết quả, nhưng phù hợp với cách tổ chức khác nhau.

### 7.1. consumeWith

Ví dụ:

~~~java
webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .consumeWith(result -> {
            assertThat(result.getResponseBody().id()).isEqualTo(42L);
            assertThat(result.getStatus()).isEqualTo(HttpStatus.OK);
        });
~~~

**consumeWith** nhận kết quả trong callback. Cách này phù hợp khi mọi assertion có thể thực hiện ngay tại vị trí request và không cần dùng kết quả ở nơi khác.

### 7.2. returnResult

Ví dụ:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();

assertOrderResponse(result);
~~~

**returnResult** trả kết quả ra ngoài callback. Cách này phù hợp khi:

- Cần gọi nhiều helper trên cùng kết quả.
- Cần kiểm tra metadata ở nhiều vị trí.
- Cần kết hợp với một assertion framework khác.
- Muốn trả kết quả từ một helper hoặc factory.
- Cần đưa ExchangeResult vào bước xử lý sau đó.

Không nên lấy returnResult rồi chỉ dùng một assertion đơn giản nếu expectation trực tiếp đã diễn đạt rõ hơn. Chọn cách nào làm test dễ đọc nhất.

## 8. Tổ chức helper trả về ExchangeResult

Khi nhiều test cần cùng một request setup, có thể tạo helper trả về kiểu kết quả cụ thể.

Ví dụ:

~~~java
EntityExchangeResult<OrderResponse> getOrder(long id) {
    return webTestClient.get()
            .uri("/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody(OrderResponse.class)
            .returnResult();
}
~~~

Test:

~~~java
@Test
void returnsPaidOrder() {
    EntityExchangeResult<OrderResponse> result = getOrder(42L);

    result.assertWithDiagnostics(() ->
            assertThat(result.getResponseBody().status())
                    .isEqualTo("PAID")
    );
}
~~~

Helper giữ request setup và expectation chung ở một nơi. Tuy nhiên, không nên đặt quá nhiều assertion nghiệp vụ vào helper nếu từng test cần xác nhận những điều khác nhau. Helper nên làm rõ điều kiện HTTP cơ bản, còn test nên giữ các kỳ vọng riêng của kịch bản.

### 8.1. Trả về kiểu tổng quát

Nếu helper cần hỗ trợ nhiều body type, có thể nhận Class<T>:

~~~java
<T> EntityExchangeResult<T> getEntity(
        String uri,
        Class<T> bodyType) {

    return webTestClient.get()
            .uri(uri)
            .exchange()
            .expectStatus().isOk()
            .expectBody(bodyType)
            .returnResult();
}
~~~

Với kiểu generic phức tạp, tạo overload nhận ParameterizedTypeReference<T>:

~~~java
<T> EntityExchangeResult<T> getEntity(
        String uri,
        ParameterizedTypeReference<T> bodyType) {

    return webTestClient.get()
            .uri(uri)
            .exchange()
            .expectStatus().isOk()
            .expectBody(bodyType)
            .returnResult();
}
~~~

Không cần tạo abstraction tổng quát nếu chỉ có một hoặc hai test dùng. Một helper có quá nhiều tham số hoặc overload khó hiểu sẽ làm test khó đọc hơn request builder trực tiếp.

## 9. Những giới hạn cần hiểu khi đọc ExchangeResult

### 9.1. ExchangeResult không phải MvcResult

MockMvc trả về MvcResult với các thông tin liên quan đến Servlet MVC như handler, ModelAndView, flash map và resolved exception.

WebTestClient trả về ExchangeResult với góc nhìn HTTP client: URL, method, headers, status, cookies và body content. Hai loại kết quả phục vụ các môi trường test khác nhau.

Vì vậy, không nên tìm một API tương đương getHandler() hoặc getModelAndView() trong ExchangeResult. Nếu cần xác nhận hành vi nội bộ server, hãy dùng log, instrumentation, test ở tầng phù hợp hoặc API quan sát của ứng dụng.

### 9.2. Không thể suy ra exception nội bộ chỉ từ HTTP response

Nếu server xử lý exception bằng exception handler và trả HTTP 404 hoặc 500, ExchangeResult cho biết response client nhận được. Nó không nhất thiết cung cấp exception gốc đã xảy ra bên trong server.

Để điều tra exception nội bộ:

- Xem log server hoặc test output.
- Kiểm tra error response contract.
- Nếu dùng mock application context, kiểm tra cấu hình exception handling trong context.
- Viết test riêng cho service hoặc component phát sinh exception nếu cần.

Một response 500 không tự nói rõ lỗi nằm ở controller, service, serialization hay infrastructure. ExchangeResult cung cấp dấu vết HTTP, còn chẩn đoán server-side cần nguồn quan sát tương ứng.

### 9.3. Body streaming không phải một object đã hoàn tất

Với FluxExchangeResult, body là publisher. Việc lấy ExchangeResult không có nghĩa tất cả phần tử đã được tiêu thụ hoặc stream đã hoàn tất.

Test cần subscribe bằng StepVerifier hoặc cơ chế reactive phù hợp. Không gọi block() tùy tiện trong test WebFlux nếu mục tiêu là kiểm tra hành vi publisher; StepVerifier cho phép kiểm tra tín hiệu reactive theo đúng trình tự.

### 9.4. Không gửi request hai lần để lấy metadata

Một lỗi thiết kế thường gặp là gửi một request để kiểm tra status, sau đó gửi request khác để lấy body hoặc header. Hai lần gửi có thể nhận dữ liệu khác nhau do trạng thái thay đổi, thời gian, random id hoặc dữ liệu cập nhật.

Lấy ExchangeResult từ chính request đã kiểm tra:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .returnResult();
~~~

Sau đó dùng cùng result cho tất cả assertion liên quan. Điều này giữ các bằng chứng thuộc cùng một HTTP exchange.

## 10. Những lỗi thường gặp khi dùng returnResult

### Không giải mã được response body

Kiểm tra:

- Content-Type của response.
- Decoder có hỗ trợ media type không?
- Kiểu DTO có tương thích với JSON thực tế không?
- Generic type có được mô tả bằng ParameterizedTypeReference không?
- Codec hoặc ObjectMapper có cấu hình module cần thiết không?

Nếu lỗi xảy ra ở bước decode, không có EntityExchangeResult typed hoàn chỉnh để tiếp tục assertion. Xem exception và response body content nếu có thể capture.

### Dùng expectBodyList cho stream không kết thúc

expectBodyList cần đọc body thành collection hữu hạn. Với SSE hoặc stream liên tục, test có thể chờ mãi hoặc hết timeout. Dùng returnResult(Type) để lấy FluxExchangeResult và kiểm tra publisher bằng StepVerifier.

### Gọi assertion sau returnResult trên cùng ResponseSpec

returnResult là thao tác kết thúc chuỗi expectation và trả về kết quả. Sau đó, tiếp tục kiểm tra bằng API của ExchangeResult hoặc body object. Không gọi thêm expectStatus hoặc expectHeader trên ResponseSpec đã được kết thúc.

### Body đã được đọc nhưng test lại muốn đọc từ cùng response

Response body thường được tiêu thụ trong quá trình decode hoặc stream subscription. Không giả định có thể đọc lại cùng một publisher như một collection độc lập. Nếu cần nhiều assertion, lưu object đã giải mã hoặc dùng các operator phù hợp trên Flux; tránh subscribe nhiều lần vào một nguồn one-shot.

### Generic body bị giải mã thành Map hoặc kiểu không mong muốn

Khi kiểu response có generic lồng nhau, dùng ParameterizedTypeReference. Raw Class không giữ được đầy đủ tham số generic do type erasure.

### Assertion thất bại nhưng thiếu request/response context

Dùng assertWithDiagnostics cho assertion chạy sau returnResult. Với các expectation trực tiếp, WebTestClient thường cung cấp thông báo theo bước thất bại; có thể dùng callback consumeWith hoặc lưu ExchangeResult để bổ sung thông tin.

### Kiểm tra bytes của response streaming như một body hoàn chỉnh

Streaming response được phát theo từng phần tử hoặc event. Dùng FluxExchangeResult và StepVerifier để xác nhận nội dung theo tín hiệu, không giả định một mảng bytes đầy đủ đã sẵn sàng trước khi stream kết thúc.

### In dữ liệu nhạy cảm

ExchangeResult có thể cung cấp request headers, cookies và body content. Không ghi token, session cookie, thông tin cá nhân hoặc dữ liệu bí mật vào log CI dùng chung. Dùng dữ liệu giả và chỉ ghi các trường cần chẩn đoán.

## 11. Ví dụ tổng hợp: DTO, metadata và stream

Một bộ test có thể kiểm tra response object và stream bằng hai kiểu result khác nhau.

### 11.1. DTO và metadata

~~~java
@Test
void capturesOrderResponseAndMetadata() {
    EntityExchangeResult<OrderResponse> result =
            webTestClient.get()
                    .uri("/orders/42")
                    .accept(MediaType.APPLICATION_JSON)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.APPLICATION_JSON)
                    .expectBody(OrderResponse.class)
                    .returnResult();

    result.assertWithDiagnostics(() -> {
        assertThat(result.getMethod()).isEqualTo(HttpMethod.GET);
        assertThat(result.getResponseBody().id()).isEqualTo(42L);
        assertThat(result.getResponseBody().status()).isEqualTo("PAID");
    });
}
~~~

Ở đây, expectBody(OrderResponse.class).returnResult() tạo **EntityExchangeResult<OrderResponse>**: body được đọc và giải mã thành một DTO trước khi test kiểm tra metadata và thuộc tính nghiệp vụ.

### 11.2. Stream sự kiện

~~~java
@Test
void emitsOrderEvents() {
    FluxExchangeResult<OrderEvent> result =
            webTestClient.get()
                    .uri("/orders/events")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .exchange()
                    .expectStatus().isOk()
                    .returnResult(OrderEvent.class);

    StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                    event.type().equals("ORDER_CREATED"))
            .expectNextMatches(event ->
                    event.type().equals("ORDER_PAID"))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
}
~~~

Ví dụ này cho thấy sự khác nhau giữa lấy một entity đã giải mã và lấy publisher. Cùng một phương thức returnResult có thể tạo kiểu kết quả khác nhau tùy vị trí gọi: từ BodySpec sau expectBody để nhận EntityExchangeResult, hoặc từ ResponseSpec với element type để nhận FluxExchangeResult.

## 12. Nguyên tắc thực hành

1. Dùng returnResult khi cần giữ response để kiểm tra nhiều thuộc tính hoặc truyền sang helper.
2. Dùng expectBody(Type).returnResult() cho một body đã giải mã thành giá trị Java.
3. Dùng expectBodyList(Type).returnResult() cho collection hữu hạn.
4. Dùng expectBody().returnResult() khi cần raw bytes của body.
5. Dùng returnResult(Type) trên ResponseSpec để nhận FluxExchangeResult cho reactive stream.
6. Dùng ParameterizedTypeReference cho generic type và ServerSentEvent có data generic.
7. Dùng assertWithDiagnostics để bổ sung request/response khi assertion trên ExchangeResult thất bại.
8. Dùng StepVerifier cho Flux và phân biệt stream hữu hạn với stream dài hạn.
9. Không gửi lại request chỉ để lấy thêm metadata; giữ một ExchangeResult cho cùng exchange.
10. Không xem ExchangeResult như MvcResult hoặc nguồn truy cập trạng thái nội bộ server.
11. Không gom stream vô hạn thành List và không subscribe lặp lại tùy tiện.
12. Giữ log chẩn đoán an toàn, tránh ghi token, cookie hoặc dữ liệu nhạy cảm.

returnResult giúp chuyển từ chuỗi expectation sang một đối tượng kết quả có kiểu rõ ràng. EntityExchangeResult phù hợp với body đã được giải mã, FluxExchangeResult phù hợp với publisher streaming, còn ExchangeResult cung cấp metadata HTTP chung. Chọn đúng kiểu theo dạng response sẽ giúp test xác nhận cả dữ liệu lẫn giao thức, đồng thời giữ được bằng chứng cần thiết để điều tra khi một assertion thất bại.

