# Phân biệt bộ đệm HTTP, cache nghiệp vụ và dữ liệu fallback

## Mục tiêu của bài học

Khi bảo vệ lời gọi đến dịch vụ phụ thuộc bằng Spring Cloud CircuitBreaker, ứng dụng có thể phải xử lý payload HTTP, lưu dữ liệu để dùng lại và trả kết quả suy giảm khi lời gọi thất bại. Ba việc này thường cùng xuất hiện trong một gateway, nhưng có mục đích và vòng đời khác nhau:

- **Bộ đệm HTTP** giữ tạm byte hoặc phần dữ liệu đang được truyền/giải mã trong một lần trao đổi mạng.
- **Cache nghiệp vụ** lưu một giá trị có ý nghĩa với domain để nhiều request có thể đọc lại theo khóa và chính sách freshness.
- **Dữ liệu fallback** là kết quả thay thế được trả khi thao tác chính không thể cung cấp kết quả hợp lệ.

Nhầm lẫn ba khái niệm có thể gây lãng phí bộ nhớ, trả dữ liệu cũ mà không biết, hoặc khiến fallback bị lưu như dữ liệu thật. Sau bài học, bạn có thể:

- Phân biệt buffer ở tầng HTTP với cache có khóa, TTL và quy tắc nghiệp vụ.
- Hiểu buffering body trong WebClient và giới hạn bộ nhớ khi giải mã response.
- Thiết kế cache nghiệp vụ có metadata freshness và chính sách dùng dữ liệu cũ khi phụ thuộc lỗi.
- Chọn dữ liệu fallback phù hợp và biểu diễn rõ trạng thái suy giảm.
- Đặt fallback sau ranh giới circuit breaker để breaker vẫn ghi nhận lỗi.
- Tránh ghi dữ liệu fallback vào cache như thể đó là kết quả xác thực từ dịch vụ phụ thuộc.

## 1. Ba khái niệm, ba vòng đời

Giả sử order-service gọi catalog-service để lấy thông tin sản phẩm. Trong lúc xử lý, ứng dụng có thể nhận các byte HTTP, giải mã thành Product, lưu Product vào cache và trả một kết quả dự phòng nếu catalog-service không phản hồi.

| Khái niệm | Mục đích | Vòng đời | Ví dụ |
| --- | --- | --- | --- |
| Bộ đệm HTTP | Giữ tạm dữ liệu truyền qua mạng hoặc gom body để giải mã. | Thường gắn với một request/response và được giải phóng sau khi xử lý. | Buffer của socket, Netty DataBuffer, body được codec gom để decode. |
| Cache nghiệp vụ | Tái sử dụng dữ liệu domain qua nhiều request. | Có khóa, thời hạn, chính sách cập nhật và eviction. | Product theo SKU trong Caffeine hoặc Redis. |
| Dữ liệu fallback | Cung cấp phản hồi thay thế khi lời gọi chính lỗi hoặc bị circuit breaker từ chối. | Được chọn cho một lần xử lý; có thể lấy từ cache hoặc tạo theo quy tắc. | ProductView ở trạng thái STALE hoặc UNKNOWN. |

Bộ đệm HTTP không tự trở thành cache. Việc một response đã được đọc vào bộ nhớ không có nghĩa request tiếp theo có thể lấy lại response đó. Cache nghiệp vụ có thể dùng lại dữ liệu sau khi request ban đầu kết thúc. Fallback cũng không mặc nhiên được lưu lại; nó chỉ là cách ứng dụng phản hồi khi không có kết quả chính đáng tin cậy.

## 2. Bộ đệm HTTP hoạt động ở tầng truyền tải

HTTP client và runtime mạng có thể dùng buffer để nhận, gửi hoặc chuyển tiếp byte. Trong ứng dụng Spring WebFlux, Reactor Netty sử dụng các vùng nhớ dạng DataBuffer/ByteBuf để xử lý dữ liệu mạng. Codec có thể gom response body vào bộ nhớ khi cần giải mã thành một đối tượng.

Ví dụ:

    Mono<ProductDto> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class);

bodyToMono yêu cầu decoder tạo một ProductDto. Với response body có kích thước hữu hạn, codec có thể cần tích lũy dữ liệu trước khi hoàn tất việc giải mã. Đây là buffering phục vụ quá trình truyền tải và decode. Sau khi publisher hoàn tất, buffer tạm thời được quản lý và giải phóng theo vòng đời của client/codec.

Một số điểm cần nhớ:

- Buffer giữ byte hoặc chunk, không hiểu ý nghĩa của Product, giá hay tồn kho.
- Buffer không có khóa nghiệp vụ như SKU hoặc customerId.
- Buffer không tự có TTL, quy tắc invalidation hoặc chính sách dữ liệu cũ.
- Giới hạn buffer giúp tránh một response quá lớn chiếm nhiều heap hoặc vùng nhớ direct.
- Với dữ liệu lớn hoặc stream, nên xử lý theo từng phần thay vì luôn gom toàn bộ body.

Có thể giới hạn lượng dữ liệu codec được phép gom trong bộ nhớ khi cấu hình WebClient:

    ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs(codecs ->
            codecs.defaultCodecs().maxInMemorySize(2 * 1024 * 1024)
        )
        .build();

    WebClient client = WebClient.builder()
        .exchangeStrategies(strategies)
        .build();

Giá trị 2 MiB chỉ là ví dụ. Hãy chọn theo kích thước payload hợp lệ của API và ngân sách bộ nhớ của ứng dụng. Khi body vượt giới hạn, codec có thể phát sinh DataBufferLimitException. Đây là tín hiệu payload vượt giới hạn decode; không nên tự động coi mọi trường hợp này là dịch vụ phụ thuộc mất khả dụng. Cần phân loại theo hợp đồng API và chính sách ghi nhận lỗi của circuit breaker.

### Xử lý response lớn hoặc streaming

Nếu API trả dữ liệu lớn, hãy cân nhắc Flux để xử lý từng phần tử:

    Flux<ProductDto> products = webClient.get()
        .uri("/products/export")
        .retrieve()
        .bodyToFlux(ProductDto.class);

Flux cho phép xử lý theo dòng và tận dụng backpressure thay vì luôn giữ toàn bộ danh sách trong bộ nhớ. Nếu ứng dụng thao tác trực tiếp với DataBuffer, cần tuân thủ vòng đời của buffer và giải phóng đúng cách khi giữ hoặc loại bỏ buffer thủ công. Việc giữ tham chiếu DataBuffer quá lâu có thể làm tăng áp lực bộ nhớ hoặc gây rò rỉ vùng nhớ direct.

Buffering là vấn đề về cách vận chuyển và giải mã payload. Nếu muốn tái sử dụng kết quả đã giải mã qua nhiều request, hãy thiết kế cache riêng ở tầng domain.

## 3. HTTP cache cũng khác bộ đệm truyền tải

Ngoài buffer, HTTP còn có cơ chế caching theo semantics của giao thức. Các header như Cache-Control, ETag, Last-Modified, Age và Vary có thể cho phép browser, proxy hoặc cache HTTP lưu response và tái xác thực response sau đó.

HTTP cache khác buffer ở chỗ nó có thể tái sử dụng response giữa nhiều request theo quy tắc HTTP. Tuy vậy, nó vẫn khác cache nghiệp vụ:

- HTTP cache chủ yếu lưu representation của resource và tuân theo header/cache key của giao thức.
- Cache nghiệp vụ lưu đối tượng domain hoặc dữ liệu đã xử lý theo khóa và quy tắc của ứng dụng.
- Buffer truyền tải chỉ giữ dữ liệu tạm thời trong quá trình gửi/nhận hoặc decode.

Nếu catalog-service trả Cache-Control hoặc ETag, client/proxy có thể dùng cơ chế HTTP cache hoặc conditional request khi được hỗ trợ. Nhưng không nên giả định WebClient tự cung cấp một cache HTTP đầy đủ chỉ vì response có header Cache-Control. Cần một cache layer hoặc HTTP caching client phù hợp và phải xác minh chính sách thực tế.

Với dữ liệu riêng tư hoặc phụ thuộc người dùng, cần xem xét Cache-Control: private/no-store, Vary và danh tính người dùng trước khi cho phép cache ở proxy hoặc thiết bị dùng chung. Cache sai phạm vi có thể làm lộ dữ liệu giữa người dùng.

## 4. Cache nghiệp vụ lưu dữ liệu domain để dùng lại

Cache nghiệp vụ lưu giá trị đã giải mã và có ý nghĩa trong domain. Ví dụ, catalog cache lưu Product theo SKU:

    product-cache
      key: product:{tenant}:{locale}:{currency}:{sku}
      value:
        name: "Bàn phím cơ"
        price: 1250000
        version: 18
        fetchedAt: 2026-11-24T10:00:00Z
        expiresAt: 2026-11-24T10:05:00Z

Khác với buffer HTTP, cache nghiệp vụ cần quyết định:

- **Key:** dữ liệu được tra cứu theo SKU, tenant, locale hoặc tổ hợp nào?
- **TTL:** dữ liệu được xem là mới trong bao lâu?
- **Freshness:** dữ liệu hết TTL có được dùng tạm khi dịch vụ lỗi không?
- **Invalidation:** khi giá hoặc sản phẩm thay đổi, cache được cập nhật hoặc xóa như thế nào?
- **Eviction:** giới hạn số entry hoặc dung lượng bộ nhớ ra sao?
- **Consistency:** chấp nhận dữ liệu trễ bao lâu so với nguồn chính?
- **Phạm vi:** dữ liệu có phụ thuộc người dùng, tenant hoặc quyền truy cập không?

Cache có thể đặt trong bộ nhớ tiến trình như Caffeine hoặc dùng kho phân tán như Redis. Cache cục bộ có độ trễ thấp nhưng mỗi instance có thể giữ giá trị khác nhau. Cache phân tán chia sẻ dữ liệu giữa nhiều instance nhưng bổ sung một phụ thuộc vận hành khác. Dù chọn loại nào, hãy đặt giới hạn dung lượng, TTL và chính sách cập nhật rõ ràng.

Không cache dữ liệu chỉ vì đã nhận được một response. Chỉ lưu kết quả đã được xác nhận hợp lệ theo hợp đồng domain. Nếu response lỗi, response không đầy đủ hoặc dữ liệu không vượt qua validation, không ghi nó vào cache như một giá trị chính xác.

## 5. Fresh cache, stale cache và chính sách dùng khi lỗi

Cache thường có trạng thái mới hoặc cũ theo thời gian:

| Trạng thái | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| Fresh | Nằm trong thời hạn freshness bình thường. | Có thể trả trực tiếp nếu nghiệp vụ cho phép. |
| Stale but usable | Đã quá TTL bình thường nhưng vẫn nằm trong khoảng cho phép dùng khi lỗi. | Chỉ dùng khi chính sách stale-if-error cho phép và phải biểu diễn dữ liệu cũ. |
| Expired/unusable | Quá giới hạn sử dụng hoặc bị invalidation. | Không dùng làm fallback; trả lỗi hoặc trạng thái không xác định. |

Ví dụ, thông tin mô tả sản phẩm có thể chấp nhận cũ vài phút, nhưng giá bán hoặc tồn kho có thể cần dữ liệu mới hơn. Một cache policy nên thể hiện rõ hai mốc: TTL bình thường và stale window tối đa khi nguồn chính không khả dụng.

Không áp dụng một stale window chung cho mọi loại dữ liệu. Giá, tồn kho, quyền truy cập, hạn mức tín dụng và trạng thái thanh toán thường có rủi ro khác nhau. Với dữ liệu ảnh hưởng đến giao dịch hoặc bảo mật, stale fallback có thể không được phép.

Khi trả stale data, response nên chứa metadata để tầng gọi hoặc client biết đó là dữ liệu cũ, ví dụ:

    {
      "sku": "SKU-42",
      "name": "Bàn phím cơ",
      "availability": "STALE",
      "dataAsOf": "2026-11-24T10:00:00Z",
      "source": "CACHE"
    }

Đây là cấu trúc minh họa do ứng dụng định nghĩa. Không dùng trường availability chung nếu domain đã có một khái niệm khác; hãy chọn tên phản ánh rõ trạng thái dữ liệu. Thời điểm dataAsOf cần là thời điểm dữ liệu được lấy từ nguồn xác thực, không phải thời điểm fallback được trả.

## 6. Fallback là quyết định phản hồi, không phải một loại cache

Fallback là nhánh xử lý thay thế khi thao tác chính không thể cung cấp kết quả bình thường. Có thể có nhiều kiểu fallback:

- Đọc cache fresh hoặc stale nếu nghiệp vụ cho phép.
- Trả trạng thái UNKNOWN khi không thể xác định dữ liệu.
- Trả kết quả mặc định cho một phần thông tin tùy chọn.
- Gọi một nguồn dự phòng khác nếu có hợp đồng và giới hạn phù hợp.
- Truyền lỗi lên tầng gọi nếu không có phản hồi thay thế an toàn.

Fallback không bắt buộc phải đọc cache. Một fallback có thể trả trạng thái không khả dụng, hoặc yêu cầu client thử lại. Ngược lại, cache có thể phục vụ request bình thường ngay cả khi không có lỗi nào xảy ra.

Phân biệt ba trường hợp:

1. Cache hit: nguồn chính không cần được gọi vì cache đang có dữ liệu dùng được.
2. Fallback from cache: nguồn chính được gọi nhưng lỗi hoặc breaker từ chối, nên ứng dụng dùng cache theo chính sách stale-if-error.
3. Static/degraded fallback: không có dữ liệu cache phù hợp, ứng dụng trả trạng thái thay thế hoặc truyền lỗi.

Không biến fallback thành một giá trị giả trông giống dữ liệu xác thực. Ví dụ, nếu không lấy được giá, trả price = 0 có thể khiến hệ thống tính đơn hàng miễn phí. Nếu không lấy được tồn kho, trả quantity = 0 có thể khiến ứng dụng khẳng định sản phẩm đã hết hàng. Hãy biểu diễn UNKNOWN, UNAVAILABLE hoặc trạng thái domain tương đương.

## 7. Đặt fallback sau circuit breaker để không che lỗi

Với Resilience4j Reactor operator, circuit breaker cần quan sát lỗi của lời gọi chính trước khi lỗi được chuyển thành fallback. Ví dụ:

    Mono<ProductView> primary = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .map(ProductView::from)
        .doOnNext(productCache::putAuthoritative);

    Mono<ProductView> result = primary
        .transformDeferred(CircuitBreakerOperator.of(catalogCircuitBreaker))
        .onErrorResume(error -> {
            if (!isDependencyAvailabilityFailure(error)) {
                return Mono.error(error);
            }

            return productCache.findUsable(id)
                .map(CachedProduct::toFallbackView)
                .switchIfEmpty(Mono.error(error));
        });

Trong ví dụ:

- primary gọi catalog-service và chuyển DTO thành domain view.
- putAuthoritative chỉ lưu kết quả chính đã nhận và chuyển đổi thành công.
- CircuitBreakerOperator quan sát kết quả lời gọi chính.
- onErrorResume chạy sau operator, chỉ dùng cache cho nhóm lỗi được phép.
- Nếu cache không có dữ liệu dùng được, lỗi ban đầu được truyền tiếp.

Nếu đặt onErrorResume trước CircuitBreakerOperator và chuyển mọi lỗi thành Mono.just(...), breaker có thể chỉ nhìn thấy một kết quả thành công. Failure rate và slow-call statistics sẽ không còn phản ánh đúng phụ thuộc.

Với API Spring Cloud ReactiveCircuitBreakerFactory, fallback được truyền vào run:

    return circuitBreakerFactory.create("catalog-read").run(
        primary,
        error -> {
            if (!isDependencyAvailabilityFailure(error)) {
                return Mono.error(error);
            }

            return productCache.findUsable(id)
                .map(CachedProduct::toFallbackView)
                .switchIfEmpty(Mono.error(error));
        }
    );

API factory quản lý việc gọi fallback khi publisher thất bại hoặc breaker không cho phép lời gọi. Hàm isDependencyAvailabilityFailure là chính sách do ứng dụng định nghĩa; không nên dùng một điều kiện quá rộng để biến lỗi lập trình, validation hoặc lỗi giải mã thành dữ liệu fallback.

Với lời gọi đồng bộ, nguyên tắc tương tự áp dụng cho hàm fallback của CircuitBreaker.run: chỉ dùng dữ liệu thay thế khi lỗi thuộc nhóm mà nghiệp vụ cho phép phục hồi.

## 8. Không ghi fallback vào cache như dữ liệu xác thực

Một lỗi phổ biến là đặt thao tác cache write sau nhánh đã hợp nhất kết quả chính và fallback:

    Mono<ProductView> result = protectedCall
        .onErrorResume(error -> Mono.just(ProductView.unknown(id)))
        .doOnNext(productCache::putAuthoritative);

Đoạn code này có thể ghi ProductView.unknown vào cache như thể nó là dữ liệu lấy từ catalog-service. Request sau đó có thể đọc lại trạng thái UNKNOWN dù dịch vụ đã phục hồi.

Hãy chỉ cập nhật cache ở nhánh thành công của nguồn chính, trước fallback:

    Mono<ProductView> primary = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .map(ProductView::from)
        .doOnNext(productCache::putAuthoritative);

    return circuitBreakerFactory.create("catalog-read").run(
        primary,
        error -> productCache.findUsable(id)
            .map(CachedProduct::toFallbackView)
            .switchIfEmpty(Mono.error(error))
    );

Nếu nghiệp vụ có chủ đích muốn lưu một trạng thái degraded, hãy lưu ở namespace hoặc loại record riêng, có nguồn và thời điểm rõ ràng. Không ghi đè cache chính bằng dữ liệu fallback. Khi dịch vụ phục hồi, dữ liệu authoritative mới phải thay thế giá trị cũ theo quy tắc cập nhật đã định nghĩa.

Cũng cần tránh cập nhật cache từ một response đến muộn nếu nó cũ hơn dữ liệu hiện tại. Với các luồng cập nhật đồng thời, có thể cần version, timestamp từ nguồn hoặc compare-and-set để không ghi đè dữ liệu mới bằng response cũ.

## 9. Phân loại lỗi để chọn đúng fallback

Không phải lỗi nào cũng nên kích hoạt cùng một fallback:

| Loại lỗi | Cách xử lý thường phù hợp |
| --- | --- |
| Connection timeout hoặc dịch vụ không kết nối được | Có thể dùng stale cache nếu domain cho phép. |
| Circuit breaker OPEN / CallNotPermittedException | Không gọi nguồn chính; cân nhắc cache usable hoặc trạng thái unavailable. |
| HTTP 5xx | Có thể dùng cache theo chính sách lỗi máy chủ. |
| HTTP 404 | Có thể là kết quả domain hợp lệ; xử lý theo hợp đồng, không mặc định dùng dữ liệu cũ. |
| HTTP 401/403 | Truyền lỗi xác thực/ủy quyền; không trả cache thuộc phạm vi người dùng khác. |
| Validation hoặc lỗi lập trình | Truyền lỗi để phát hiện vấn đề; không che bằng fallback chung. |
| Payload vượt giới hạn decode | Kiểm tra hợp đồng kích thước và codec; không tự động coi là lỗi tạm thời của dịch vụ. |
| Bulkhead từ chối | Có thể trả busy hoặc dùng cache nếu cho phép; tránh retry ngay gây tăng tải. |

Hàm phân loại lỗi cần dựa trên exception thực tế của HTTP client, status code và hợp đồng API. Một số mã 4xx có ý nghĩa đặc biệt như 429 Too Many Requests; không nên gom toàn bộ 4xx vào nhóm lỗi nghiệp vụ hoặc nhóm lỗi cần bỏ qua.

Fallback không thay thế xử lý bảo mật. Nếu cache có dữ liệu theo tenant hoặc user, phải kiểm tra quyền truy cập trước khi trả cache. Không dùng fallback để bỏ qua kiểm tra authorization chỉ vì dịch vụ xác thực đang lỗi.

## 10. Cache key, freshness và quyền truy cập

Một cache key chỉ dựa trên productId có thể không đủ nếu kết quả thay đổi theo tenant, ngôn ngữ, currency hoặc quyền của người dùng. Hãy xác định đầy đủ các yếu tố ảnh hưởng đến representation:

    product:{tenant}:{locale}:{currency}:{sku}

Đây là ví dụ key; chỉ đưa vào các chiều thực sự ảnh hưởng đến dữ liệu. Key càng rộng thì số entry càng tăng, vì vậy cần cân bằng giữa tính chính xác và dung lượng.

Đối với dữ liệu có phân quyền:

- Không trả cache của tenant A cho tenant B.
- Không bỏ qua kiểm tra authorization khi nguồn chính lỗi.
- Không cache response chứa token, cookie hoặc dữ liệu cá nhân không cần thiết.
- Xác định rõ cache có chia sẻ giữa các user hay không.
- Khi quyền truy cập bị thu hồi, cân nhắc invalidation hoặc kiểm tra quyền lại trước khi dùng cache.

Freshness cũng cần có nguồn thời gian đáng tin cậy. Dùng timestamp của dữ liệu gốc nếu có, hoặc ghi fetchedAt khi nhận kết quả xác thực. Không cập nhật fetchedAt mỗi lần đọc cache, vì điều đó khiến dữ liệu cũ trông như mới.

## 11. Quan sát buffer, cache và fallback riêng biệt

Để tìm đúng nguyên nhân khi hệ thống suy giảm, hãy theo dõi từng lớp:

| Lớp | Chỉ số hoặc sự kiện nên quan sát |
| --- | --- |
| HTTP buffer/codec | Kích thước body, số lần vượt maxInMemorySize, lỗi decode, áp lực heap/direct memory. |
| Cache nghiệp vụ | Hit/miss, eviction, TTL expiration, tuổi dữ liệu khi đọc, stale hit và lỗi cache. |
| Fallback | Số lần fallback theo nguyên nhân, loại fallback, tỷ lệ UNKNOWN/STALE/UNAVAILABLE. |
| Circuit breaker | Trạng thái CLOSED/OPEN/HALF_OPEN, failure rate, slow call rate, số lần bị từ chối. |
| HTTP client | Connect/response timeout, số kết nối đang dùng, lỗi mạng và latency. |

Nếu cache hit tăng nhưng dữ liệu stale tăng, cần xem lại TTL hoặc invalidation. Nếu fallback tăng cùng lúc breaker mở, phụ thuộc có thể đang gặp sự cố. Nếu DataBufferLimitException tăng, có thể response body vượt giới hạn codec hoặc ứng dụng đang cố gom dữ liệu stream quá lớn. Không tăng giới hạn buffer một cách tự động nếu chưa hiểu kích thước payload và tác động bộ nhớ.

Metric nên dùng tag có cardinality kiểm soát. Không gắn SKU, userId hoặc requestId làm tag metric nếu số giá trị có thể tăng rất lớn. Những giá trị chi tiết nên nằm trong log có kiểm soát và tuân thủ chính sách dữ liệu.

## 12. Bài thực hành: dùng cache làm fallback có kiểm soát

Xây dựng catalog gateway để lấy thông tin sản phẩm và bảo vệ lời gọi bằng circuit breaker:

1. Tạo WebClient gọi catalog-service và trả về Mono<ProductDto>.
2. Cấu hình giới hạn buffer cho codec theo kích thước response hợp lệ.
3. Tạo ProductCache có key theo tenant và SKU, TTL bình thường cùng stale window tối đa.
4. Chỉ ghi cache khi response chính được giải mã và validation thành công.
5. Bọc publisher chính bằng circuit breaker có id catalog-read.
6. Đặt fallback phía sau breaker; chỉ dùng cache khi lỗi thuộc nhóm availability được phép.
7. Trả metadata cho biết kết quả là LIVE, STALE hoặc UNKNOWN cùng dataAsOf.
8. Làm catalog-service timeout và xác nhận breaker ghi nhận lỗi trước khi fallback trả stale cache.
9. Làm cache hết stale window và xác nhận ứng dụng truyền lỗi hoặc trả trạng thái unavailable theo hợp đồng.
10. Khôi phục catalog-service và xác nhận kết quả mới cập nhật cache chính, thay thế dữ liệu cũ.
11. Thử response body lớn hơn giới hạn codec và phân biệt lỗi buffer/decode với lỗi availability.
12. Kiểm tra cache key không làm lộ dữ liệu giữa tenant hoặc người dùng.

Khi hoàn thành, bạn cần chỉ ra được buffer HTTP tồn tại ở đâu và được giải phóng khi nào, cache nghiệp vụ lưu dữ liệu nào và dựa trên freshness nào, fallback được kích hoạt trong điều kiện nào và vì sao không được ghi fallback vào cache authoritative. Phân tách ba lớp này giúp ứng dụng kiểm soát bộ nhớ, tính đúng đắn của dữ liệu và hành vi khi dịch vụ phụ thuộc không khả dụng.

