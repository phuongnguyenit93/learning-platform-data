# Mono và Flux: số lượng phần tử, kết quả rỗng và lỗi

Trong Reactor, **Mono** và **Flux** biểu diễn các chuỗi tín hiệu bất đồng bộ. Chọn đúng kiểu trả về giúp người gọi biết một thao tác có thể tạo ra bao nhiêu phần tử, khi nào thao tác kết thúc và lỗi được truyền đi như thế nào. Đây là nền tảng quan trọng khi xây dựng các tương tác RSocket như request-response, request-stream, fire-and-forget và request-channel.

Sau bài học này, bạn có thể:

- Phân biệt cardinality của Mono và Flux.
- Nhận biết một publisher hoàn tất rỗng và một publisher kết thúc bằng lỗi.
- Chọn toán tử phù hợp để xử lý giá trị vắng mặt hoặc lỗi.
- Thiết kế kiểu trả về cho handler RSocket và kiểm tra hành vi bằng StepVerifier.

## 1. Chuỗi reactive được tạo từ các tín hiệu

Một publisher Reactive Streams gửi tín hiệu đến subscriber. Sau tín hiệu đăng ký, publisher có thể phát không hoặc nhiều giá trị, rồi kết thúc bằng đúng một tín hiệu terminal:

1. **onSubscribe**: thiết lập subscription và cơ chế yêu cầu dữ liệu.
2. **onNext**: phát một phần tử.
3. **onComplete**: kết thúc bình thường.
4. **onError**: kết thúc do lỗi.

Publisher có thể hoàn tất ngay mà không phát onNext. Đây là một kết quả hợp lệ, thường được gọi là **empty completion**. onComplete và onError loại trừ nhau; sau một trong hai tín hiệu này, publisher không được phát thêm dữ liệu.

~~~mermaid
flowchart TD
    A[Publisher] --> B[onSubscribe]
    B --> C{Có phần tử?}
    C -->|Có| D[onNext]
    D --> C
    C -->|Không còn phần tử| E[onComplete]
    C -->|Có lỗi| F[onError]
~~~

Với Flux, publisher có thể phát một số phần tử rồi mới gặp lỗi. Các phần tử đã phát vẫn đã đến subscriber; lỗi kết thúc phần còn lại của chuỗi. Với Mono, chuỗi chỉ có thể phát tối đa một phần tử: hoặc phát một phần tử rồi hoàn tất, hoặc kết thúc bằng lỗi mà không phát phần tử.

## 2. Mono và Flux khác nhau ở số lượng phần tử

**Mono<T>** biểu diễn một kết quả bất đồng bộ có từ không đến một phần tử. **Flux<T>** biểu diễn một chuỗi bất đồng bộ có từ không đến nhiều phần tử.

| Kiểu | Cardinality | Các kết quả bình thường |
|---|---:|---|
| **Mono<T>** | 0..1 | Một giá trị rồi hoàn tất, hoặc hoàn tất rỗng |
| **Flux<T>** | 0..N | Không có giá trị, một giá trị hoặc nhiều giá trị rồi hoàn tất |

Ví dụ:

~~~java
Mono<String> oneName = Mono.just("An");
Mono<String> noName = Mono.empty();

Flux<String> names = Flux.just("An", "Bình", "Chi");
Flux<String> noNames = Flux.empty();
~~~

Tên kiểu không đảm bảo publisher chắc chắn có dữ liệu. Một phương thức trả về Mono<Customer> vẫn có thể không tìm thấy customer và trả về Mono.empty(). Một phương thức trả về Flux<Event> vẫn có thể không có event nào để phát.

### Mono<Void> là kết quả chỉ báo hoàn tất

Mono<Void> thường được dùng cho thao tác mà người gọi chỉ cần biết chuỗi đã hoàn tất hay gặp lỗi, không cần nhận một giá trị nghiệp vụ. Ví dụ: ghi audit, gửi lệnh hoặc xóa dữ liệu.

~~~java
Mono<Void> deleteProduct(String id) {
    return repository.deleteById(id);
}
~~~

Nếu một thao tác ban đầu trả về giá trị nhưng tầng gọi không cần giá trị đó, có thể dùng then() để chuyển thành Mono<Void>:

~~~java
Mono<Void> saveAudit(AuditEvent event) {
    return auditRepository.save(event).then();
}
~~~

Mono<Void> hoàn tất bình thường mà không phát onNext. Vì vậy, không nên kiểm tra nó bằng cách chờ một giá trị; hãy quan sát việc hoàn tất hoặc lỗi.

### Reactive Streams không dùng null làm phần tử

Một tín hiệu onNext không được mang null. Vì thế, Mono.just(null) là không hợp lệ và Reactor sẽ báo lỗi. Khi nguồn dữ liệu có thể trả về null hoặc Optional rỗng, hãy chuyển trạng thái đó thành empty publisher:

~~~java
Mono<Product> findLegacyProduct(String id) {
    Product product = legacyLookup(id);
    return Mono.justOrEmpty(product);
}

Mono<Product> findOptionalProduct(String id) {
    Optional<Product> product = legacyOptionalLookup(id);
    return Mono.justOrEmpty(product);
}
~~~

Cách biểu diễn này giúp chuỗi giữ đúng hợp đồng reactive: có giá trị thì phát giá trị, không có giá trị thì hoàn tất rỗng.

## 3. Hiểu đúng empty completion

Một publisher rỗng không phải là publisher bị lỗi. Nó đã thực hiện xong công việc theo cách bình thường, nhưng không có phần tử nào để phát.

Những tình huống thường tạo ra kết quả rỗng:

- Truy vấn không tìm thấy bản ghi.
- filter loại bỏ tất cả phần tử.
- Một hàm flatMap trả về Mono.empty().
- Nguồn dữ liệu là danh sách hoặc luồng không có phần tử.
- Một API được thiết kế để biểu diễn kết quả không bắt buộc.

~~~java
Mono<Product> product = repository.findById(id)
    .filter(Product::isPublished);

Flux<Product> availableProducts = repository.findAll()
    .filter(Product::isAvailable);
~~~

Trong ví dụ đầu, sản phẩm không tồn tại hoặc chưa được xuất bản đều có thể dẫn đến Mono.empty(). Trong ví dụ sau, nếu không sản phẩm nào khả dụng thì Flux hoàn tất mà không phát phần tử.

### Dùng defaultIfEmpty và switchIfEmpty

defaultIfEmpty(value) phát một giá trị mặc định nếu nguồn hoàn tất rỗng. Toán tử này phù hợp khi có một giá trị mặc định hợp lệ về mặt nghiệp vụ:

~~~java
Mono<String> displayName = repository.findName(userId)
    .defaultIfEmpty("Khách");
~~~

switchIfEmpty(publisher) chuyển sang một publisher khác nếu nguồn hoàn tất rỗng. Cách này phù hợp khi cần tra cứu dự phòng hoặc áp dụng một nhánh xử lý khác:

~~~java
Mono<Product> findProduct(String id) {
    return primaryRepository.findById(id)
        .switchIfEmpty(
            Mono.defer(() -> archiveRepository.findById(id))
        );
}
~~~

Mono.defer trì hoãn việc tạo publisher dự phòng cho đến khi nhánh dự phòng thực sự được chọn. Điều này hữu ích khi việc tạo nguồn có chi phí hoặc có tác dụng phụ.

Hai toán tử trên chỉ xử lý empty completion. Chúng không xử lý onError.

### Chuyển empty thành thông tin rõ ràng

Đôi khi tầng nghiệp vụ không muốn để kết quả vắng mặt đi tiếp. Có thể chuyển empty thành lỗi miền hoặc một đối tượng kết quả có trạng thái rõ ràng:

~~~java
Mono<Product> getRequiredProduct(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
~~~

Lựa chọn giữa empty, lỗi và đối tượng kết quả phụ thuộc hợp đồng API:

- Dùng empty khi “không có kết quả” là một kết quả bình thường mà bên gọi có thể xử lý.
- Dùng lỗi miền khi yêu cầu không thể được đáp ứng theo quy tắc nghiệp vụ.
- Dùng đối tượng kết quả khi bên gọi cần phân biệt nhiều trạng thái, chẳng hạn FOUND, NOT_FOUND hoặc NOT_VISIBLE.

Đừng biến mọi trường hợp không tìm thấy thành lỗi một cách máy móc. Ngược lại, đừng để empty đi qua nhiều tầng nếu bên gọi cần một kết quả bắt buộc.

### Một số toán tử thay đổi cardinality

| Toán tử | Đầu vào | Đầu ra | Khi nguồn rỗng |
|---|---|---|---|
| next() | Flux<T> | Mono<T> | Mono.empty() |
| singleOrEmpty() | Flux<T> | Mono<T> | Mono.empty(); lỗi nếu có hơn một phần tử |
| collectList() | Flux<T> | Mono<List<T>> | Phát một danh sách rỗng |
| count() | Flux<T> | Mono<Long> | Phát 0 |
| hasElements() | Flux<T> | Mono<Boolean> | Phát false |

Ví dụ, collectList() biến một Flux rỗng thành Mono chứa danh sách rỗng. Nó không tạo ra một Mono rỗng. Sự khác biệt này rất quan trọng khi thiết kế kiểu trả về cho API.

~~~java
Mono<List<Product>> allProducts = repository.findAll()
    .collectList();

Mono<Long> productCount = repository.findAll()
    .count();

Mono<Boolean> hasProducts = repository.findAll()
    .hasElements();
~~~

Không dùng singleOrEmpty() nếu nguồn có thể có nhiều phần tử và bạn muốn lấy phần tử đầu tiên. Trong trường hợp đó, dùng next() hoặc một toán tử giới hạn phù hợp.

## 4. Lỗi là tín hiệu kết thúc riêng biệt

onError biểu thị chuỗi không thể tiếp tục theo cách bình thường. Nó khác với empty completion:

| Tình huống | Tín hiệu kết thúc | Ý nghĩa |
|---|---|---|
| Không tìm thấy dữ liệu và đây là kết quả hợp lệ | onComplete mà không có onNext | Không có giá trị |
| Đọc cơ sở dữ liệu thất bại | onError | Không hoàn thành thành công |
| Flux đã phát vài phần tử rồi nguồn gặp lỗi | onError sau các onNext | Dữ liệu trước lỗi đã được phát; phần còn lại bị kết thúc |

Có thể tạo publisher lỗi bằng Mono.error hoặc Flux.error:

~~~java
Mono<Product> failedLookup =
    Mono.error(new IllegalStateException("Catalog unavailable"));

Flux<Event> failedStream =
    Flux.error(new IllegalStateException("Stream unavailable"));
~~~

Lỗi cũng có thể phát sinh trong quá trình thực thi toán tử, chẳng hạn trong hàm truyền cho map, flatMap hoặc khi gọi nguồn dữ liệu.

### Các cách xử lý lỗi thường dùng

| Toán tử | Tác dụng |
|---|---|
| doOnError(...) | Quan sát lỗi để ghi log hoặc đo lường; lỗi vẫn được truyền tiếp |
| onErrorReturn(value) | Thay lỗi bằng một giá trị cố định rồi hoàn tất |
| onErrorResume(error -> publisher) | Chuyển sang publisher dự phòng khi có lỗi |
| onErrorMap(error -> newError) | Chuyển lỗi hiện tại thành lỗi khác |
| onErrorComplete() | Biến lỗi thành hoàn tất bình thường, không có giá trị thay thế |
| retryWhen(...) | Đăng ký lại nguồn theo chính sách retry |

Ví dụ dùng giá trị dự phòng:

~~~java
Mono<Price> getPrice(String productId) {
    return priceClient.fetch(productId)
        .onErrorReturn(Price.unavailable());
}
~~~

Ví dụ dùng nguồn dự phòng:

~~~java
Mono<Product> getProduct(String id) {
    return primaryRepository.findById(id)
        .onErrorResume(
            PrimaryStoreException.class,
            error -> cacheRepository.findById(id)
        );
}
~~~

Ví dụ chuyển lỗi hạ tầng thành lỗi miền:

~~~java
Mono<Product> getProduct(String id) {
    return repository.findById(id)
        .onErrorMap(
            DataAccessException.class,
            error -> new CatalogUnavailableException(error)
        );
}
~~~

doOnError thích hợp cho tác dụng phụ như ghi log. Không dùng nó để thay thế giá trị hoặc khôi phục luồng, vì nó không tiêu thụ lỗi.

onErrorComplete có thể hữu ích khi lỗi được phép bỏ qua theo hợp đồng, nhưng cần thận trọng: nó làm bên gọi nhìn thấy một kết quả hoàn tất bình thường. Nếu lỗi bị che đi, hệ thống có thể báo thành công dù dữ liệu chưa được xử lý.

### Retry cần có giới hạn và điều kiện

Retry phù hợp với lỗi tạm thời, chẳng hạn một lần gọi dịch vụ bị gián đoạn ngắn. Không nên retry tất cả lỗi, cũng không nên retry thao tác có tác dụng phụ nếu thao tác đó không an toàn khi thực hiện nhiều lần.

~~~java
Mono<Response> callRemoteService() {
    return remoteClient.call()
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientFailure)
        );
}
~~~

Đoạn mã trên thử lại tối đa ba lần sau lần gọi đầu tiên, với khoảng chờ tăng dần. Cần chọn điều kiện retry, số lần thử và thời gian chờ dựa trên hợp đồng của dịch vụ. Với lệnh ghi hoặc thanh toán, hãy bảo đảm cơ chế idempotency trước khi retry.

## 5. Empty và error cần được xử lý bằng đúng toán tử

switchIfEmpty và onErrorResume giải quyết hai tín hiệu khác nhau. Kết hợp chúng khi nghiệp vụ có cả nhánh “không có dữ liệu” và nhánh “nguồn dữ liệu bị lỗi”:

~~~java
Mono<Product> getProduct(String id) {
    return primaryRepository.findById(id)
        .switchIfEmpty(
            Mono.defer(() -> archiveRepository.findById(id))
        )
        .onErrorResume(
            CatalogUnavailableException.class,
            error -> cacheRepository.findById(id)
        );
}
~~~

Trong ví dụ này:

- Nếu kho chính hoàn tất rỗng, hệ thống tìm trong kho lưu trữ.
- Nếu chuỗi phát ra CatalogUnavailableException, hệ thống chuyển sang cache.
- Nếu nguồn dự phòng cũng rỗng, kết quả cuối cùng vẫn có thể là empty.
- Nếu nguồn dự phòng phát lỗi, lỗi đó tiếp tục được truyền xuống bên gọi, trừ khi có xử lý bổ sung.

Thứ tự toán tử ảnh hưởng đến lỗi nào được bắt. Một onErrorResume chỉ xử lý lỗi phát sinh ở phía upstream của nó. Nếu chính publisher dự phòng phát lỗi, toán tử đó không tự động bắt lại lỗi của nhánh dự phòng.

Cần tránh các nhầm lẫn sau:

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Dùng onErrorResume để xử lý không tìm thấy dữ liệu | Empty không phải lỗi; dùng switchIfEmpty hoặc defaultIfEmpty |
| Dùng switchIfEmpty để khôi phục khi database lỗi | Lỗi đi qua onError; dùng onErrorResume nếu có thể phục hồi |
| Cho rằng Mono<T> luôn có một giá trị | Mono có thể hoàn tất rỗng |
| Cho rằng Mono<Void> phát một giá trị null | Mono<Void> hoàn tất mà không phát onNext |
| Dùng onErrorComplete cho mọi lỗi | Có thể che mất lỗi cần được báo cáo |
| Gọi block() trong chuỗi xử lý reactive | Có thể chặn thread và phá vỡ mô hình bất đồng bộ |

## 6. Áp dụng cardinality vào các tương tác RSocket

RSocket có nhiều mô hình tương tác. Kiểu publisher ở phía Java nên phản ánh số lượng thông điệp mà handler dự kiến xử lý hoặc trả về.

| Mô hình RSocket | Dạng dữ liệu thường dùng trong Reactor | Ý nghĩa |
|---|---|---|
| Request-response | Mono<Response> | Một request và tối đa một giá trị response ở tầng ứng dụng |
| Request-stream | Flux<Response> | Một request mở đầu và một chuỗi response |
| Fire-and-forget | Mono<Void> ở handler | Xử lý không tạo response payload |
| Request-channel | Flux<Request> → Flux<Response> | Chuỗi request và chuỗi response hai chiều |

Với request-response, hãy định nghĩa rõ trường hợp không tìm thấy dữ liệu. Nếu API cần trả lời cho mọi request, có thể trả một DTO chứa trạng thái hoặc phát lỗi miền:

~~~java
@MessageMapping("catalog.product.get")
public Mono<ProductResponse> getProduct(ProductRequest request) {
    return productService.findById(request.id())
        .map(ProductResponse::found)
        .switchIfEmpty(Mono.just(ProductResponse.notFound()));
}
~~~

Với request-stream, một Flux rỗng có nghĩa là luồng kết thúc bình thường mà không phát response nào. Điều này có thể phù hợp khi không có sự kiện mới, nhưng nếu bên gọi cần phân biệt “không có dữ liệu” với “đăng ký sai”, hợp đồng ứng dụng phải biểu diễn hai trạng thái riêng:

~~~java
@MessageMapping("quotes.watch")
public Flux<Quote> watchQuotes(QuoteRequest request) {
    return quoteService.watch(request.symbol());
}
~~~

Với fire-and-forget, handler có thể trả Mono<Void> để biểu diễn việc xử lý bất đồng bộ ở phía nhận đã hoàn tất hoặc gặp lỗi trong pipeline của handler:

~~~java
@MessageMapping("audit.record")
public Mono<Void> recordAudit(AuditRequest request) {
    return auditService.record(request);
}
~~~

Ở phía gửi, API fireAndForget(...) cũng trả về Mono<Void>. Việc publisher này hoàn tất biểu thị thao tác gửi theo API client đã hoàn tất; nó không phải response xác nhận rằng nghiệp vụ phía server đã xử lý xong. Nếu cần xác nhận xử lý từ server, hãy chọn mô hình tương tác có response phù hợp.

Với request-channel, Flux đầu vào và Flux đầu ra đều có thể rỗng hoặc phát nhiều phần tử. Handler cần xử lý việc kết thúc luồng đầu vào, lỗi và nhu cầu điều tiết luồng theo đúng hợp đồng của channel:

~~~java
@MessageMapping("telemetry.ingest")
public Flux<IngestResult> ingest(Flux<TelemetryEvent> events) {
    return events
        .filter(TelemetryEvent::isValid)
        .flatMap(telemetryService::process);
}
~~~

Chọn Mono hay Flux là quyết định về cardinality ở tầng ứng dụng. Các quy tắc giao thức RSocket và cách Spring ánh xạ handler vẫn cần được tuân thủ; đừng dựa vào kiểu trả về để suy đoán rằng mọi trạng thái nghiệp vụ đã được truyền tải đầy đủ.

## 7. Kiểm tra empty và error bằng StepVerifier

StepVerifier cho phép mô tả các tín hiệu mà publisher phải phát. Các kiểm tra sau giúp xác nhận cả giá trị lẫn tín hiệu kết thúc:

~~~java
@Test
void monoEmitsOneValueAndCompletes() {
    StepVerifier.create(Mono.just("RSocket"))
        .expectNext("RSocket")
        .verifyComplete();
}

@Test
void monoCanCompleteEmpty() {
    StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
}

@Test
void monoCanFail() {
    StepVerifier.create(
            Mono.<String>error(
                new IllegalStateException("unavailable")
            )
        )
        .expectError(IllegalStateException.class)
        .verify();
}

@Test
void fluxCanEmitValuesBeforeFailing() {
    StepVerifier.create(
            Flux.concat(
                Flux.just("event-1", "event-2"),
                Flux.error(new IllegalStateException("stream failed"))
            )
        )
        .expectNext("event-1", "event-2")
        .expectErrorMessage("stream failed")
        .verify();
}
~~~

Khi kiểm tra logic dự phòng, hãy kiểm tra riêng từng nhánh: nguồn có giá trị, nguồn rỗng, nguồn lỗi, và chính nguồn dự phòng cũng lỗi. Nhờ vậy, bài kiểm tra phản ánh hợp đồng của chuỗi thay vì chỉ xác nhận một trường hợp thành công.

## 8. Quy trình chọn kiểu trả về và xử lý kết quả

Khi thiết kế một service hoặc RSocket handler, hãy lần lượt trả lời các câu hỏi sau:

1. Một lần gọi có thể tạo ra bao nhiêu phần tử? Chọn Mono cho 0..1 và Flux cho 0..N.
2. Không có dữ liệu có phải là kết quả bình thường không? Nếu có, giữ empty và để tầng gọi quyết định; nếu không, chuyển thành lỗi miền hoặc DTO trạng thái.
3. Lỗi nào có thể phục hồi? Chỉ dùng fallback hoặc retry cho những lỗi có chính sách rõ ràng.
4. Bên gọi cần biết điều gì khi kết thúc? Một giá trị, một danh sách rỗng, trạng thái hoàn tất hay một lỗi?
5. Kiểu trả về có khớp mô hình tương tác RSocket không? Đặc biệt phân biệt response payload với Mono<Void> chỉ biểu diễn hoàn tất.

Hãy giữ hợp đồng nhất quán giữa repository, service và handler. Nếu repository dùng empty để biểu diễn không tìm thấy, service cần quyết định rõ có giữ nguyên trạng thái đó hay chuyển thành kết quả nghiệp vụ khác. Handler RSocket sau đó phải truyền đạt đúng trạng thái mà client cần biết.

## 9. Ghi nhớ

- Mono<T> phát tối đa một phần tử; Flux<T> phát không hoặc nhiều phần tử.
- Empty completion là kết thúc bình thường không có onNext.
- Error là tín hiệu terminal riêng; Flux có thể đã phát dữ liệu trước khi gặp lỗi.
- defaultIfEmpty và switchIfEmpty xử lý empty; onErrorReturn và onErrorResume xử lý error.
- Mono<Void> biểu diễn hoàn tất mà không có response value.
- Với RSocket, kiểu trả về phải phù hợp mô hình tương tác và hợp đồng nghiệp vụ phải định nghĩa rõ empty có nghĩa gì.

