# Tiêu thụ hoặc giải phóng body và tài nguyên liên quan

## Vì sao response body phải có người tiếp nhận?

Trong kiểm thử HTTP phản ứng với WebTestClient, việc nhận được status 200 OK hoặc header mong đợi chưa có nghĩa là response đã được xử lý hoàn tất. Body có thể vẫn chứa dữ liệu chưa được đọc, một luồng dữ liệu đang mở hoặc các buffer cần được giải phóng.

Spring WebFlux xử lý dữ liệu theo mô hình reactive. Body thường được biểu diễn bằng Publisher, Mono, Flux hoặc các DataBuffer. Khi dữ liệu đến từ network hoặc được quản lý bởi một implementation có reference counting, việc đọc và hủy luồng ảnh hưởng trực tiếp đến vòng đời tài nguyên.

Trong test, cần xác định rõ một trong các mục tiêu:

- Đọc và xác nhận toàn bộ body.
- Xác nhận response không có body.
- Nhận kết quả đã decode để kiểm tra bằng assertion khác.
- Tiêu thụ một response stream có nhiều phần tử.
- Chủ động bỏ qua body khi nội dung không cần thiết, nhưng vẫn giải phóng tài nguyên.
- Đọc dữ liệu ở mức DataBuffer và tự chịu trách nhiệm về vòng đời buffer.

Nguyên tắc chung là mỗi response body phải có một đường xử lý rõ ràng. Nếu test chỉ kiểm tra status/header, hãy thêm bước tiêu thụ hoặc giải phóng body khi API yêu cầu. Nếu test cần quan sát dữ liệu, hãy đọc body đúng một lần và dùng kết quả đã thu được cho các assertion.

## Tiêu thụ body trong WebTestClient

WebTestClient cung cấp các API expectBody, expectBodyList và returnResult để đọc response body trong test. Những API này thực hiện việc tiêu thụ và chuyển đổi body theo kiểu mong muốn.

### Đọc body thành kiểu cụ thể

Khi response là một object JSON, có thể decode trực tiếp thành DTO:

~~~java
EntityExchangeResult<OrderResponse> result = webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .returnResult();

OrderResponse body = result.getResponseBody();

assertThat(body).isNotNull();
assertThat(body.id()).isEqualTo(42L);
assertThat(body.status()).isEqualTo("PAID");
~~~

expectBody(OrderResponse.class) đọc body và dùng message codec để chuyển đổi thành OrderResponse. returnResult() trả về EntityExchangeResult<OrderResponse> chứa thông tin response cùng body đã decode. Test có thể lưu kết quả rồi thực hiện nhiều assertion trên object mà không cần đọc lại HTTP body.

Nếu chỉ cần xác nhận JSON mà không cần DTO, có thể dùng matcher JSON:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 42,
                  "status": "PAID"
                }
                """);
~~~

Matcher json(...) cũng tiêu thụ body để so sánh nội dung. Có thể kết hợp các assertion body trong cùng một BodyContentSpec, nhưng không nên gọi nhiều lần các API đọc body như thể response có thể được đọc lại từ đầu.

### Đọc danh sách hoặc collection

Với JSON array, expectBodyList(...) decode body thành danh sách:

~~~java
EntityExchangeResult<List<OrderResponse>> result = webTestClient.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(OrderResponse.class)
        .returnResult();

List<OrderResponse> orders = result.getResponseBody();

assertThat(orders)
        .extracting(OrderResponse::id)
        .containsExactly(101L, 102L);
~~~

Ở đây test kiểm tra cả dữ liệu đã decode và thứ tự phần tử. Nếu API không cam kết thứ tự, dùng assertion collection không phụ thuộc thứ tự phù hợp với hợp đồng đó. Dù chọn kiểu assertion nào, body đã được đọc trong bước expectBodyList.

### Nhận kết quả đã tiêu thụ bằng returnResult

returnResult() hữu ích khi muốn lấy metadata và body sau khi WebTestClient đã thực hiện bước đọc:

~~~java
EntityExchangeResult<byte[]> result = webTestClient.get()
        .uri("/api/export")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .returnResult();

byte[] bytes = result.getResponseBody();

assertThat(bytes).isNotEmpty();
assertThat(result.getResponseHeaders())
        .containsKey(HttpHeaders.CONTENT_DISPOSITION);
~~~

Trong ví dụ này, expectBody() đọc response thành byte[]; returnResult() trả dữ liệu đã đọc để test kiểm tra kích thước hoặc nội dung file. Cách này phù hợp với response nhị phân có kích thước vừa phải. Nếu response rất lớn hoặc không có giới hạn, nên cân nhắc kiểm tra theo luồng thay vì gom toàn bộ nội dung vào bộ nhớ.

## Response không có body

Một số endpoint trả 204 No Content, HEAD hoặc response chỉ có header. Test nên xác nhận body thực sự rỗng:

~~~java
webTestClient.delete()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody()
        .isEmpty();
~~~

expectBody().isEmpty() tiêu thụ body và xác nhận không có nội dung. Điều này vừa kiểm tra hợp đồng HTTP, vừa làm rõ rằng test đã xử lý body của response.

Nếu test chỉ kiểm tra status hoặc header mà không cần body, đừng dừng ngay sau expectStatus() hoặc expectHeader() nếu body vẫn cần được tiêu thụ. Hãy thêm bước body phù hợp, ví dụ expectBody().isEmpty() cho response được kỳ vọng rỗng. Nếu response được kỳ vọng có nội dung, hãy đọc và xác nhận nội dung đó.

## Tiêu thụ hoặc bỏ qua body khi dùng WebClient

WebTestClient là API kiểm thử; WebClient là reactive HTTP client thường dùng trong ứng dụng. Cả hai cùng dựa trên hạ tầng client reactive, nhưng các API xử lý response khác nhau.

Với WebClient, retrieve() phù hợp khi muốn decode body theo kiểu cụ thể:

~~~java
Mono<OrderResponse> order = webClient.get()
        .uri("/api/orders/42")
        .retrieve()
        .bodyToMono(OrderResponse.class);
~~~

Khi subscribe vào publisher, body được đọc và decode thành OrderResponse. Với response không cần nội dung, có thể dùng toBodilessEntity():

~~~java
Mono<ResponseEntity<Void>> deleted = webClient.delete()
        .uri("/api/orders/42")
        .retrieve()
        .toBodilessEntity();
~~~

Nếu cần kiểm soát status và cách xử lý response, dùng exchangeToMono(...) hoặc exchangeToFlux(...):

~~~java
Mono<OrderResponse> order = webClient.get()
        .uri("/api/orders/42")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(OrderResponse.class);
            }
            return response.createError();
        });
~~~

Callback của exchangeToMono trả về một publisher đại diện cho công việc xử lý response. Sau khi publisher đó hoàn tất, WebClient kiểm tra body đã được tiêu thụ hay chưa và giải phóng phần body còn lại nếu callback không đọc hết. exchangeToFlux có nguyên tắc tương tự cho luồng dữ liệu.

Điều này giúp tránh rò rỉ tài nguyên khi nhánh xử lý chỉ quan tâm status/header hoặc chỉ đọc một phần response. Tuy vậy, nếu callback cần dữ liệu body, hãy decode hoặc tiêu thụ body ngay trong callback và trả về publisher đó; không giữ ClientResponse rồi cố đọc body sau khi callback đã hoàn tất.

### Chủ động giải phóng body không cần dùng

Trong callback của exchangeToMono, nếu đã xác định không cần nội dung response, có thể gọi releaseBody():

~~~java
Mono<Void> deleteOrder = webClient.delete()
        .uri("/api/orders/42")
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.releaseBody();
            }
            return response.createError().then();
        });
~~~

releaseBody() trả về Mono<Void> và phải được đưa vào chuỗi reactive để việc giải phóng thực sự được thực thi. Chỉ gọi phương thức mà không subscribe hoặc không compose publisher của nó thì không bảo đảm thao tác đã chạy.

Không cần gọi releaseBody() sau khi body đã được đọc đầy đủ bằng bodyToMono(...) hoặc bodyToFlux(...). Hãy chọn một đường xử lý rõ ràng: decode body, chuyển thành bodiless result, hoặc release body không dùng.

## Streaming response: phải subscribe và tiêu thụ luồng

Với response streaming, body không được gom thành một object duy nhất. Ví dụ server có thể phát nhiều event hoặc nhiều phần tử JSON theo thời gian. Trong WebTestClient, returnResult(...) có thể trả FluxExchangeResult<T> để test nhận publisher của response body:

~~~java
FluxExchangeResult<ServerSentEvent<Notification>> result =
        webTestClient.get()
                .uri("/api/notifications/stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(new ParameterizedTypeReference<
                        ServerSentEvent<Notification>>() {});

StepVerifier.create(result.getResponseBody())
        .assertNext(event -> {
            assertThat(event.data()).isNotNull();
            assertThat(event.data().message()).isEqualTo("created");
        })
        .assertNext(event ->
                assertThat(event.data().message()).isEqualTo("updated"))
        .thenCancel()
        .verify();
~~~

Trong ví dụ, returnResult(...) cung cấp Flux chưa được test tiêu thụ hết. StepVerifier subscribe vào getResponseBody() và kiểm tra các event. thenCancel() hủy subscription sau các event cần xác nhận; đây là hành động có chủ đích cho stream có thể tiếp tục phát vô hạn.

Với stream hữu hạn, nên kiểm tra hoàn tất:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextMatches(item -> item.id() == 1L)
        .expectNextMatches(item -> item.id() == 2L)
        .verifyComplete();
~~~

verifyComplete() chứng minh publisher kết thúc bình thường sau các phần tử mong đợi. Nếu test chỉ kiểm tra một vài phần tử của stream vô hạn, hãy hủy subscription một cách rõ ràng. Không nên gọi subscribe() rời rạc rồi bỏ mặc subscription vì test có thể kết thúc trong khi luồng vẫn hoạt động.

Nếu cần giới hạn thời gian chờ, cấu hình timeout cho StepVerifier hoặc dùng verify(Duration) để test không treo vô hạn khi server không phát dữ liệu hoặc không hoàn tất.

## Body dạng DataBuffer và quyền sở hữu bộ nhớ

Ở tầng thấp của WebFlux, dữ liệu có thể được biểu diễn bằng DataBuffer. Một số implementation, đặc biệt buffer dựa trên Netty, sử dụng reference counting. Khi một buffer được giữ lại hoặc bị bỏ qua, việc quản lý reference count quyết định lúc bộ nhớ nền được thu hồi.

Nếu có thể, hãy decode body thành DTO, String, byte[] hoặc kiểu dữ liệu ứng dụng. Message codec và framework sẽ xử lý việc chuyển đổi ở tầng cao hơn. Chỉ làm việc trực tiếp với DataBuffer khi cần kiểm soát byte stream, truyền dữ liệu hoặc viết codec/handler ở mức thấp.

Khi code tự nhận quyền sở hữu một DataBuffer và không chuyển nó cho thành phần khác, cần giải phóng sau khi sử dụng:

~~~java
DataBuffer buffer = ...;
try {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);
    process(bytes);
} finally {
    DataBufferUtils.release(buffer);
}
~~~

DataBufferUtils.release(buffer) giải phóng buffer theo cơ chế của implementation. Dùng finally bảo đảm buffer được release cả khi xử lý dữ liệu phát sinh exception.

Nếu chỉ muốn bỏ qua các buffer trong một publisher, có thể dùng consumer do Spring cung cấp:

~~~java
Flux<DataBuffer> body = ...;

Mono<Void> discard = body
        .doOnNext(DataBufferUtils.releaseConsumer())
        .then();
~~~

Đoạn code tạo một Mono<Void> để caller compose vào pipeline hoặc subscribe tại ranh giới thực thi phù hợp. doOnNext(...) release từng buffer khi nó được phát ra; then() chuyển kết quả thành tín hiệu hoàn tất không mang dữ liệu. Không nên tạo subscription phụ tách khỏi luồng điều khiển chính. Hãy compose thao tác tiêu thụ vào pipeline do caller quản lý, hoặc dùng API response cấp cao có cơ chế release phù hợp. Một publisher chỉ được subscribe theo cách có kiểm soát; subscription rời rạc có thể làm khó việc quản lý lỗi, cancellation và vòng đời request.

### Không release hai lần và không dùng buffer sau khi release

Quyền sở hữu buffer cần rõ ràng:

- Thành phần nhận buffer để xử lý phải biết nó có quyền giữ buffer hay chỉ được đọc tạm thời.
- Nếu chuyển buffer cho downstream để downstream tiếp tục sử dụng, không release buffer trước khi downstream hoàn tất.
- Nếu đã release, không tiếp tục đọc hoặc ghi buffer đó.
- Nếu gọi retain() để giữ buffer vượt quá vòng đời hiện tại, phải có một nơi chịu trách nhiệm release phần reference đã retain.

Không nên gọi DataBufferUtils.release(...) một cách máy móc cho mọi buffer xuất hiện trong pipeline. Framework hoặc operator có thể đang quản lý ownership. Chỉ release khi code của bạn thực sự chịu trách nhiệm giải phóng buffer đó.

### Gom nhiều buffer bằng DataBufferUtils.join

DataBufferUtils.join(...) gom các buffer đầu vào thành một buffer tổng hợp:

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(dataBufferPublisher);
~~~

API join quản lý các buffer thành phần theo hợp đồng của nó; caller nhận buffer tổng hợp và phải xử lý vòng đời của buffer kết quả. Nếu caller giữ hoặc đọc buffer kết quả, cần release khi hoàn tất:

~~~java
Mono<byte[]> bytes = DataBufferUtils.join(dataBufferPublisher)
        .map(buffer -> {
            try {
                byte[] content = new byte[buffer.readableByteCount()];
                buffer.read(content);
                return content;
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

Không nên tự release từng buffer nguồn sau khi đã chuyển chúng vào DataBufferUtils.join(...) trừ khi hợp đồng của API tại phiên bản đang dùng yêu cầu rõ ràng. Hãy để operator quản lý buffer đầu vào và quản lý buffer tổng hợp mà caller nhận được.

## Cancellation, lỗi và timeout cũng là một phần của vòng đời

Một response stream có thể kết thúc theo nhiều cách:

- Publisher phát hết dữ liệu và complete.
- Publisher phát lỗi.
- Consumer chủ động cancel.
- Test hết thời gian chờ.

Các đường kết thúc này cần được xem xét khi xử lý tài nguyên. Nếu test dừng đọc stream sau một phần tử, hãy cancel subscription. Nếu callback trong exchangeToMono hoặc exchangeToFlux kết thúc mà body chưa được tiêu thụ, cơ chế của WebClient sẽ release phần body còn lại. Nếu code tự quản lý DataBuffer, cần đảm bảo nhánh complete, error và cancel đều không để sót reference do code giữ.

Một test streaming có thể kiểm tra cancellation bằng StepVerifier:

~~~java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Test này xác nhận consumer đã nhận hai phần tử rồi hủy subscription trong thời gian giới hạn. Nếu ứng dụng có side effect khi client hủy kết nối, có thể bổ sung assertion riêng để xác nhận tác vụ nền dừng hoặc tài nguyên upstream được đóng. Việc cancel phía client không tự động chứng minh mọi công việc bên ngoài đã dừng; điều đó phụ thuộc cách publisher và ứng dụng truyền tín hiệu cancellation.

## Các lỗi thường gặp

### Chỉ assert status mà bỏ quên body

expectStatus() và expectHeader() kiểm tra metadata response. Nếu response có body, test vẫn cần đọc body hoặc sử dụng cách xử lý phù hợp để giải phóng tài nguyên. Với response không nội dung, dùng expectBody().isEmpty().

### Đọc body nhiều lần

HTTP response body là stream một lần. Sau khi expectBody(...), expectBodyList(...) hoặc một decoder đã tiêu thụ body, không thể giả định một matcher khác có thể đọc lại từ đầu. Hãy decode một lần, gọi returnResult() và dùng object/byte array thu được cho nhiều assertion.

### Gọi releaseBody rồi tiếp tục decode

releaseBody() dành cho body không cần sử dụng. Sau khi release, không thể tiếp tục gọi bodyToMono(...) để lấy nội dung đó. Chọn decode hoặc release theo nhánh xử lý.

### Quên subscribe vào publisher trả về từ exchangeToMono

WebClient là reactive. Các publisher như Mono và Flux là lazy; nếu không được subscribe hoặc compose vào chuỗi đang chạy, request và thao tác release có thể chưa được thực thi.

### Nhận FluxExchangeResult nhưng không tiêu thụ response body

returnResult(...) cho streaming trả về publisher. Hãy dùng StepVerifier hoặc subscriber được quản lý để đọc stream đến complete hoặc cancel rõ ràng. Chỉ lấy FluxExchangeResult không đồng nghĩa dữ liệu đã được tiêu thụ.

### Release DataBuffer do framework đang quản lý

Release buffer không đúng ownership có thể làm downstream đọc phải buffer đã giải phóng. Xác định nơi nhận quyền sở hữu và nơi kết thúc quyền sở hữu trước khi thêm thao tác release.

### Gom toàn bộ response lớn vào bộ nhớ

expectBody() và các API decode thành collection phù hợp với payload có kích thước kiểm soát được. Với file lớn hoặc stream dài, dùng cách đọc theo luồng để tránh tăng bộ nhớ theo tổng kích thước response.

## Chọn API theo mục tiêu

| Mục tiêu | Cách xử lý phù hợp |
| --- | --- |
| Kiểm tra JSON hoặc text trong WebTestClient | expectBody() rồi assert nội dung |
| Decode một DTO | expectBody(MyDto.class).returnResult() |
| Decode một JSON array | expectBodyList(MyDto.class).returnResult() |
| Kiểm tra response nhị phân nhỏ | expectBody().returnResult() để lấy byte[] |
| Xác nhận response không có body | expectBody().isEmpty() |
| Đọc SSE hoặc response streaming | returnResult(...) rồi tiêu thụ getResponseBody() bằng StepVerifier |
| WebClient cần decode response | retrieve().bodyToMono(...) hoặc bodyToFlux(...) |
| WebClient cần rẽ nhánh theo status/header | exchangeToMono(...) hoặc exchangeToFlux(...) |
| WebClient không cần response body | toBodilessEntity() hoặc releaseBody() trong callback phù hợp |
| Xử lý byte stream ở tầng thấp | DataBuffer cùng quy tắc ownership và DataBufferUtils.release(...) |

## Quy trình kiểm thử và quản lý body

1. Xác định response có body đơn, body rỗng hay stream nhiều phần tử.
2. Chọn API tiêu thụ phù hợp với kích thước và kiểu dữ liệu: expectBody, expectBodyList, returnResult hoặc streaming result.
3. Đọc body một lần và tái sử dụng kết quả đã decode cho các assertion.
4. Nếu không cần body, xác nhận body rỗng hoặc release body theo API của client.
5. Nếu nhận Flux hoặc DataBuffer, quản lý subscription, cancellation và ownership một cách tường minh.
6. Với buffer tự quản lý, release đúng một lần sau khi không còn consumer nào cần nó.
7. Kiểm tra các nhánh complete, error và cancel để bảo đảm tài nguyên không bị giữ lại ngoài vòng đời request.

Tiêu thụ response body là một phần của kiểm thử HTTP reactive, không chỉ là thao tác lấy dữ liệu để assertion. Khi test đọc, decode, bỏ qua hoặc hủy body theo đúng API và quyền sở hữu, nó vừa xác nhận hợp đồng HTTP vừa giữ vòng đời buffer và tài nguyên liên quan trong giới hạn rõ ràng.
