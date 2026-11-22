# Thiết kế luồng tổng hợp dữ liệu từ nhiều dịch vụ HTTP

Một API tổng hợp thường phải gọi nhiều dịch vụ phía sau để tạo một response duy nhất. Ví dụ màn hình dashboard cần thông tin khách hàng từ Customer Service, số liệu đơn hàng từ Order Service và danh sách gợi ý từ Recommendation Service. Nếu gọi lần lượt từng dịch vụ, tổng thời gian chờ có thể gần bằng tổng latency của tất cả downstream. Với Spring WebFlux và WebClient, ta có thể khởi chạy các request độc lập theo kiểu reactive, chờ kết quả và ghép chúng thành một response bằng mô hình fan-out/fan-in.

Bài này tập trung vào cách chọn operator đúng cho từng quan hệ phụ thuộc: Mono.zip khi cần ghép nhiều kết quả đơn, flatMap khi request sau phụ thuộc kết quả trước, Flux.merge khi nhận nhiều stream theo thứ tự hoàn tất, và concat khi phải giữ thứ tự tuần tự. Phần triển khai còn xử lý timeout, lỗi dịch vụ bắt buộc/tuỳ chọn, retry có giới hạn, cancellation, backpressure và kiểm thử bằng HTTP mock server.

Mục tiêu không phải biến mọi downstream call thành một pipeline phức tạp. Điều quan trọng là mô tả đúng quan hệ giữa các nguồn dữ liệu, xác định nguồn nào bắt buộc, nguồn nào có thể suy giảm chức năng, rồi đặt giới hạn thời gian và tài nguyên rõ ràng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả mô hình fan-out/fan-in trong một API aggregation.
2. Phân biệt gọi tuần tự và gọi đồng thời các dịch vụ độc lập.
3. Dùng Mono.zip để kết hợp nhiều kết quả đơn.
4. Dùng flatMap khi lời gọi tiếp theo phụ thuộc dữ liệu trước đó.
5. Chọn Flux.merge, concat và flatMapSequential theo yêu cầu thứ tự.
6. Hiểu vì sao Mono<Void> không thể đóng vai trò một nguồn dữ liệu thông thường trong zip.
7. Phân loại downstream thành required và optional.
8. Xử lý 4xx/5xx, timeout, network error và empty response có chủ đích.
9. Retry lỗi tạm thời với backoff, số lần thử giới hạn và deadline tổng.
10. Để cancellation và backpressure lan truyền qua pipeline.
11. Thiết kế response một phần mà không che giấu lỗi quan trọng.
12. Dùng WebClient.Builder do Spring Boot cấu hình và tách client theo base URL.
13. Viết ứng dụng Java 17 có thể chạy cùng ba downstream HTTP service.
14. Kiểm thử luồng tổng hợp bằng WebTestClient và MockWebServer.

## 2. Bài toán aggregation: fan-out và fan-in

Giả sử endpoint:

~~~http
GET /api/dashboard/42
~~~

Cần gọi ba dịch vụ:

| Dịch vụ | Endpoint | Vai trò | Chính sách |
| --- | --- | --- | --- |
| Customer | GET /customers/42 | Tên và định danh khách hàng | Required |
| Orders | GET /orders/summary/42 | Số đơn và tổng chi tiêu | Optional |
| Recommendations | GET /recommendations/42 | Danh sách gợi ý | Optional |

Response tổng hợp:

~~~json
{
  "customerId": "42",
  "customerName": "An",
  "orderCount": 3,
  "totalSpend": 125.50,
  "recommendations": ["book", "keyboard"]
}
~~~

Customer là dữ liệu bắt buộc. Nếu không xác định được khách hàng, dashboard không có ý nghĩa và nên trả lỗi. Orders và recommendations là dữ liệu bổ sung; nếu một trong hai dịch vụ gặp lỗi tạm thời, API có thể trả response suy giảm với giá trị mặc định và ghi nhận lỗi trong log/metric.

### 2.1. Gọi tuần tự

~~~java
return loadCustomer(id)
    .flatMap(customer ->
        loadOrders(id)
            .flatMap(orders ->
                loadRecommendations(id)
                    .map(recommendations ->
                        combine(customer, orders, recommendations)
                    )
            )
    );
~~~

Nếu ba request độc lập có latency lần lượt 200 ms, 300 ms và 250 ms, thời gian chờ gần tổng 750 ms (chưa tính overhead). Gọi tuần tự phù hợp khi request sau cần kết quả request trước, nhưng không tối ưu cho các nguồn độc lập.

### 2.2. Fan-out/fan-in

~~~text
                 API /dashboard/42
                         |
                         v
                    Fan-out
                  /     |      \
                 v      v       v
           Customer   Orders  Recommendations
              |         |          |
              +---------+----------+
                         |
                         v
                    Fan-in / zip
                         |
                         v
                 Dashboard response
~~~

Nếu các request độc lập được khởi chạy gần như cùng lúc, latency của nhóm có thể tiến gần request chậm nhất thay vì tổng latency. Ví dụ lý tưởng với 200/300/250 ms là khoảng 300 ms cộng overhead. Đây chỉ là mô hình ước lượng; DNS, connection pool, network, server queue và CPU vẫn ảnh hưởng thời gian thực tế.

### 2.3. Khi nào không nên fan-out đồng thời?

Không khởi chạy đồng thời nếu:

- Dữ liệu đầu vào của request sau chỉ có sau response trước.
- Downstream có quota thấp và không cho phép mức concurrency đó.
- Các request phụ thuộc thứ tự hoặc có side effect.
- Việc đọc đồng thời tạo snapshot không nhất quán mà nghiệp vụ không chấp nhận.
- Một request có thể fan-out hàng nghìn lần mà không có giới hạn.

Song song là một quyết định về dependency và capacity, không phải mục tiêu tự thân.

## 3. Chọn operator theo quan hệ dữ liệu

| Operator | Dùng khi | Đặc điểm |
| --- | --- | --- |
| Mono.zip | Ghép một giá trị từ nhiều nguồn | Chỉ tạo kết quả khi mỗi nguồn phát một item |
| flatMap | Tạo publisher mới dựa trên item trước | Các nhánh có thể chạy bất đồng bộ |
| Flux.merge | Ghép nhiều stream độc lập | Item được phát theo thứ tự đến |
| Flux.concat | Ghép stream theo thứ tự | Chờ stream trước hoàn tất rồi mới subscribe stream sau |
| flatMapSequential | Chạy nhiều nhánh đồng thời nhưng giữ thứ tự nguồn | Có thể buffer kết quả đến sớm |
| Mono.when | Chờ nhiều tác vụ chỉ cần completion | Không ghép các giá trị kết quả |

### 3.1. Mono.zip cho nhiều kết quả đơn

~~~java
Mono<Customer> customer = loadCustomer(id);
Mono<OrderSummary> orders = loadOrders(id);
Mono<Recommendations> recommendations = loadRecommendations(id);

return Mono.zip(customer, orders, recommendations)
    .map(tuple -> combine(
        tuple.getT1(),
        tuple.getT2(),
        tuple.getT3()
    ));
~~~

Mono.zip subscribe các nguồn và ghép giá trị của chúng thành tuple khi mỗi nguồn phát một item. Với WebClient, mỗi nguồn là một HTTP request bất đồng bộ, nên các request độc lập có thể cùng đang chờ network.

Nếu một nguồn phát error, kết quả zip thường error và các nguồn còn lại bị cancel. Nếu một nguồn complete mà không phát item, zip có thể complete rỗng và không gọi hàm combine. Vì vậy phải quyết định rõ cách xử lý response body rỗng trước khi ghép.

### 3.2. Mono.zip và empty publisher

Đây là một lỗi phổ biến:

~~~java
Mono<Void> saveAudit = saveAuditEvent(event);
Mono<Customer> customer = loadCustomer(id);

return Mono.zip(saveAudit, customer, (ignored, value) -> value);
~~~

Mono<Void> biểu diễn completion không có item. zip cần một item từ mỗi nguồn nên hàm combine không được gọi như mong đợi.

Nếu chỉ cần chờ một nhóm side effect hoàn tất, dùng:

~~~java
return Mono.when(saveAudit, publishEvent);
~~~

Nếu vừa cần kết quả dữ liệu vừa cần side effect, ghép dữ liệu trước rồi dùng then/thenReturn cho side effect theo đúng thứ tự nghiệp vụ; đừng biến Mono<Void> thành nguồn zip giả.

### 3.3. zipDelayError

Mono.zipDelayError có thể chờ các nguồn khác hoàn tất trước khi phát lỗi tổng hợp. Dùng khi cần thu thập nhiều lỗi hoặc cho phép các thao tác độc lập hoàn tất trước khi báo lỗi. Nó không tự biến lỗi thành partial response và không thay thế fallback policy.

### 3.4. flatMap cho dependency có điều kiện

Ví dụ cần lấy profile trước để biết tenant rồi mới gọi dịch vụ giá:

~~~java
return customerClient.get()
    .uri("/customers/{id}", id)
    .retrieve()
    .bodyToMono(CustomerProfile.class)
    .flatMap(customer ->
        priceClient.get()
            .uri("/prices/{tenant}/{sku}",
                customer.tenantId(), sku)
            .retrieve()
            .bodyToMono(PriceView.class)
            .map(price -> combine(customer, price))
    );
~~~

Request giá phụ thuộc tenant trong customer profile, nên đây là chuỗi phụ thuộc thật. Dùng zip ở đây không có ích vì chưa biết URL/đầu vào cho request thứ hai.

### 3.5. Flux.merge khi thứ tự đến quyết định

~~~java
Flux<Event> events = Flux.merge(
    customerEvents(),
    orderEvents(),
    inventoryEvents()
);
~~~

Các event được phát khi từng nguồn có item. Một event từ inventory có thể đến trước event customer dù nguồn customer được khai báo trước.

### 3.6. concat khi phải giữ thứ tự

~~~java
Flux<Event> events = Flux.concat(
    initialSnapshot(),
    liveUpdates()
);
~~~

concat subscribe nguồn đầu tiên, chờ complete, sau đó mới chuyển sang nguồn kế tiếp. Nó giữ thứ tự nhưng không có fan-out đồng thời giữa các nguồn.

### 3.7. flatMap và giới hạn concurrency

~~~java
Flux<ProductView> products = Flux.fromIterable(productIds)
    .flatMap(this::loadProduct, 8);
~~~

Tham số 8 giới hạn số inner publisher được subscribe đồng thời. Không dùng flatMap(this::loadProduct) không giới hạn cho danh sách có thể chứa hàng triệu ID. Nếu cần phát kết quả theo thứ tự ID ban đầu nhưng vẫn gọi song song, cân nhắc flatMapSequential và đánh giá chi phí buffer.

## 4. Thiết kế required và optional downstream

Không phải mọi dịch vụ phía sau đều có cùng mức độ quan trọng.

### 4.1. Required dependency

Dữ liệu required là điều kiện để tạo response hợp lệ. Ví dụ Customer Service phải trả profile. Nếu service không tồn tại, timeout hoặc trả lỗi không thể khôi phục, API nên trả lỗi có ý nghĩa, thường là 502/503 tùy semantics.

Không tự thay customer bằng một đối tượng rỗng chỉ để response luôn 200. Điều đó che giấu lỗi nghiệp vụ và có thể khiến client hiển thị nhầm dữ liệu.

### 4.2. Optional dependency

Optional dependency có thể dùng fallback nếu lỗi thuộc nhóm được phép suy giảm:

- Network/connect error.
- Timeout.
- Downstream 5xx tạm thời.
- Empty response nếu contract cho phép coi là không có dữ liệu.

Không tự động fallback cho mọi 4xx. 400 có thể là request lỗi; 401/403 có thể là vấn đề cấu hình credential; 404 có thể mang nghĩa nghiệp vụ riêng. Hãy định nghĩa policy theo từng service.

Ví dụ:

~~~java
Mono<OrderSummary> orders = loadOrders(id)
    .onErrorResume(
        WebClientRequestException.class,
        error -> Mono.just(OrderSummary.empty())
    );
~~~

Đây chỉ là minh họa một loại lỗi. Production nên có log/metric ghi nhận fallback và giới hạn các exception được phép xử lý.

### 4.3. Partial response phải có contract rõ

Nếu optional service không khả dụng, response có thể thêm trạng thái:

~~~json
{
  "orderCount": 0,
  "totalSpend": 0,
  "degraded": ["orders"]
}
~~~

Danh sách degraded giúp client biết dữ liệu đang thiếu do downstream lỗi, khác với trường hợp thật sự không có đơn hàng. Nếu API không thể thay đổi schema, ít nhất phải ghi metric/log và tài liệu hóa semantics của fallback.

### 4.4. Empty Mono khác error

- Mono.just(value): có một kết quả.
- Mono.empty(): complete mà không có kết quả.
- Mono.error(error): kết thúc bằng lỗi.
- Mono<Void>: biểu diễn completion không có data item.

Với nguồn required, có thể chuyển empty thành lỗi:

~~~java
bodyToMono(CustomerProfile.class)
    .switchIfEmpty(Mono.error(
        new RequiredDependencyFailure("customer")
    ));
~~~

Với nguồn optional, có thể chuyển empty thành giá trị mặc định nếu contract cho phép:

~~~java
bodyToMono(RecommendationResponse.class)
    .defaultIfEmpty(RecommendationResponse.empty());
~~~

## 5. WebClient: gọi dịch vụ HTTP theo kiểu reactive

WebClient là HTTP client reactive của Spring WebFlux. Nó hỗ trợ request/response bất đồng bộ, streaming response body và tích hợp Reactor.

Ví dụ:

~~~java
Mono<CustomerProfile> customer = webClient.get()
    .uri("/customers/{id}", customerId)
    .retrieve()
    .bodyToMono(CustomerProfile.class);
~~~

### 5.1. retrieve và exchangeToMono

retrieve() là lựa chọn đơn giản cho response thông thường. Mặc định, response 4xx/5xx tạo WebClientResponseException. Có thể tùy chỉnh bằng onStatus:

~~~java
Mono<CustomerProfile> customer = webClient.get()
    .uri("/customers/{id}", customerId)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.error(
            new CustomerNotFoundException(customerId)
        )
    )
    .bodyToMono(CustomerProfile.class);
~~~

Dùng exchangeToMono khi cần quyết định cách decode dựa trên status/header/body phức tạp hơn. Khi dùng API exchange, phải tiêu thụ hoặc release response body theo contract để connection được giải phóng đúng cách.

### 5.2. Tạo client riêng theo base URL

Có thể dùng một Boot-managed builder và clone để cấu hình nhiều dịch vụ:

~~~java
WebClient customerClient = builder.clone()
    .baseUrl(customerBaseUrl)
    .build();

WebClient orderClient = builder.clone()
    .baseUrl(orderBaseUrl)
    .build();

WebClient recommendationClient = builder.clone()
    .baseUrl(recommendationBaseUrl)
    .build();
~~~

Dùng builder do Spring Boot cung cấp giúp giữ các customizer, codec và observation configuration đã auto-configure. Không tự tạo WebClient riêng rồi giả định nó có toàn bộ cấu hình của Boot.

### 5.3. URI template và encoding

Dùng:

~~~java
.uri("/customers/{id}", customerId)
~~~

thay vì tự nối chuỗi URL từ input. URI template giúp encoding nhất quán và giúp observability nhận biết pattern endpoint ổn định. Vẫn cần validate ID theo quy tắc nghiệp vụ.

## 6. Timeout, deadline và latency budget

Mỗi downstream có thể treo hoặc phản hồi quá chậm. Cần có timeout cho từng request và một deadline cho toàn bộ aggregation.

Ví dụ:

~~~java
private static final Duration DEPENDENCY_TIMEOUT =
    Duration.ofSeconds(2);

private static final Duration TOTAL_TIMEOUT =
    Duration.ofSeconds(4);
~~~

Từng call:

~~~java
Mono<CustomerProfile> customer = loadCustomer(id)
    .timeout(DEPENDENCY_TIMEOUT);
~~~

Toàn bộ fan-in:

~~~java
return Mono.zip(customer, orders, recommendations)
    .map(this::combine)
    .timeout(TOTAL_TIMEOUT);
~~~

Nếu ba nguồn chạy đồng thời, tổng thời gian không phải tổng ba timeout. Nhưng deadline tổng vẫn cần để bảo vệ caller và tài nguyên. Hãy đặt timeout tổng phù hợp với latency budget của API gateway/frontend.

### 6.1. Timeout không đồng nghĩa server đã dừng xử lý

Khi client timeout, Reactor phát lỗi và cancellation được gửi upstream. WebClient/transport có thể hủy request nếu còn khả năng. Tuy nhiên, downstream có thể đã nhận và tiếp tục xử lý request, đặc biệt với thao tác có side effect. Timeout phía aggregator không bảo đảm transaction phía service kia đã rollback.

### 6.2. Không đặt timeout quá thấp

Timeout phải dựa trên số liệu p95/p99, network và SLA của downstream. Giá trị quá thấp gây false timeout và retry storm; giá trị quá cao giữ connection/request context quá lâu.

### 6.3. Deadline tổng và từng dependency

Một policy mẫu:

| Thành phần | Budget minh họa |
| --- | ---: |
| Customer required | 1.5 s |
| Orders optional | 1.2 s |
| Recommendations optional | 1.0 s |
| Tổng API | 2.5 s |

Các nhánh chạy đồng thời nên deadline tổng ngắn hơn tổng thời gian tuần tự. Những con số này chỉ minh họa; hãy đo production rồi đặt theo SLA thực tế.

## 7. Retry có giới hạn và lỗi tạm thời

Retry chỉ có ích khi lỗi có khả năng tự phục hồi. Một số nguyên tắc:

- Chỉ retry nhóm lỗi tạm thời như connect failure, timeout hoặc 5xx đã xác định.
- Giới hạn số lần thử.
- Dùng exponential backoff và jitter để tránh nhiều instance retry đồng loạt.
- Đặt deadline tổng bao trùm cả retry.
- Chỉ retry request idempotent hoặc có idempotency key.
- Không retry 400/401/403 như thể đó là lỗi mạng.

Reactor hỗ trợ:

~~~java
.retryWhen(
    Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientFailure)
)
~~~

Retry.backoff(2, ...) cho phép tối đa hai lần retry sau lần gọi đầu tiên. Nếu cả ba lần đều lỗi, lỗi cuối cùng được phát ra theo policy của Retry. Thứ tự operator quan trọng: timeout cho từng attempt có thể đặt trước retry; timeout tổng đặt sau fan-in.

### 7.1. Retry và fallback

Một nhánh optional có thể:

1. Gọi downstream.
2. Retry một số lỗi tạm thời trong giới hạn.
3. Nếu vẫn thất bại, fallback.
4. Ghi nhận dependency đang degraded.

Không đặt fallback trước retry vì khi lỗi đầu tiên đã bị chuyển thành giá trị mặc định, retry không còn nhận được error signal.

### 7.2. Tránh retry side effect không an toàn

GET đọc dữ liệu thường idempotent, nhưng POST tạo đơn hàng hoặc thanh toán không tự động an toàn để retry. Nếu client không biết request trước đã được xử lý hay chưa, retry có thể tạo bản ghi trùng. Dùng idempotency key hoặc cơ chế deduplication.

### 7.3. Circuit breaker và bulkhead

Với hệ thống có tải lớn, cân nhắc Resilience4j hoặc cơ chế tương đương:

- Circuit breaker: tạm ngừng gọi downstream đang lỗi liên tục.
- Bulkhead: giới hạn số request đồng thời đến một dependency.
- Rate limiter: giới hạn tốc độ gọi.
- Retry: thử lại lỗi tạm thời trong budget.

Không cấu hình retry vô hạn hoặc circuit breaker cho mọi dịch vụ bằng cùng một ngưỡng không đánh giá. Mỗi downstream có SLA, quota và failure mode riêng.

## 8. Error handling trong luồng tổng hợp

### 8.1. WebClientResponseException

Mặc định retrieve() phát WebClientResponseException cho response 4xx/5xx. Có thể phân loại theo status:

~~~java
private boolean isTransientFailure(Throwable error) {
    if (error instanceof WebClientRequestException) {
        return true;
    }

    if (error instanceof TimeoutException) {
        return true;
    }

    return error instanceof WebClientResponseException response
        && response.getStatusCode().is5xxServerError();
}
~~~

Đây là policy mẫu. Tùy service, một số 429 có thể retry sau khi tôn trọng Retry-After; 404 thường không retry.

### 8.2. Required dependency failure

Nếu customer service là required, map lỗi downstream thành lỗi gateway có ngữ nghĩa rõ:

~~~java
.onErrorMap(error ->
    new RequiredDependencyFailure("customer", error)
)
~~~

Controller advice có thể trả HTTP 502 và mã lỗi ứng dụng. Không gửi raw stack trace hoặc thông tin nội bộ của downstream cho client.

### 8.3. Optional dependency failure

~~~java
.onErrorResume(error -> {
    if (isTransientFailure(error)) {
        return Mono.just(OrderSummary.empty());
    }
    return Mono.error(error);
});
~~~

Không dùng onErrorResume(error -> Mono.just(defaultValue)) cho mọi loại exception nếu chưa định nghĩa rõ. Một lỗi decode do schema sai hoặc 401 do credential sai có thể cần fail rõ thay vì giả lập dữ liệu rỗng.

### 8.4. Zip fail-fast và zipDelayError

Mặc định zip có thể fail khi một nhánh lỗi và cancel các nhánh khác. Đây là hành vi hữu ích để tránh tiếp tục công việc không cần thiết. Nếu cần đợi tất cả nhánh hoàn tất để thu thập nhiều lỗi, xem zipDelayError; đổi lại request có thể phải chờ lâu hơn.

### 8.5. Không bắt và nuốt cancellation

Cancellation không phải business error. Không dùng doOnError hoặc onErrorResume như cách giả định mọi request đều kết thúc thành công. Đảm bảo cleanup ở doFinally/resource operator phù hợp và không tiếp tục công việc nền sau khi caller đã rời đi nếu không có yêu cầu rõ.

## 9. Backpressure, concurrency và giới hạn tài nguyên

Reactive không đồng nghĩa với không giới hạn.

### 9.1. Giới hạn fan-out

Nếu một dashboard gọi ba service cố định, concurrency tương đối nhỏ. Nhưng nếu endpoint nhận danh sách 10.000 ID và gọi service cho từng ID, cần giới hạn:

~~~java
Flux<ProductView> products = Flux.fromIterable(ids)
    .flatMap(this::loadProduct, 16);
~~~

Tham số 16 là ví dụ. Chọn giá trị theo downstream capacity, connection pool và latency.

### 9.2. Connection pool

WebClient thường dùng connector có connection pool. Nếu concurrency vượt số connection khả dụng, request phải chờ acquire. Cần theo dõi pending acquire, pool saturation và timeout. Không tăng pool vô hạn để che việc fan-out quá lớn.

### 9.3. Backpressure trong Flux

Flux truyền demand ngược về upstream. Các operator có thể prefetch/buffer, nên cần xem semantics của từng operator và giới hạn queue. flatMap có concurrency và prefetch; merge cũng có buffering. Với dữ liệu lớn, stream từng phần thay vì gom hết vào list.

### 9.4. Cancellation khi caller disconnect

Nếu frontend đóng kết nối trước khi dashboard hoàn tất, cancellation nên lan tới các WebClient request đang chạy. Đừng tự subscribe() bên trong service rồi trả một Mono khác, vì làm vậy tách lifecycle khỏi HTTP request và có thể khiến downstream tiếp tục chạy vô ích.

### 9.5. CPU-bound transform

JSON mapping nhẹ thường phù hợp với pipeline hiện tại. Công việc CPU nặng có thể chiếm event loop; cân nhắc scheduler phù hợp và giới hạn concurrency. Không chuyển mọi operator sang boundedElastic theo thói quen.

## 10. Consistency và dữ liệu snapshot

Gọi nhiều service đồng thời không bảo đảm các response phản ánh cùng một thời điểm.

Ví dụ:

- Customer profile được đọc lúc 10:00:00.100.
- Order summary được đọc lúc 10:00:00.250.
- Recommendation được tính từ snapshot lúc 09:59:59.800.

Dashboard có thể hiển thị các trạng thái hơi lệch nhau. Đây thường là eventual consistency chấp nhận được, nhưng cần quyết định theo nghiệp vụ.

Các cách xử lý:

- Trả timestamp/version của từng nguồn nếu cần minh bạch.
- Dùng một snapshot token hoặc version chung nếu các service hỗ trợ.
- Đưa aggregation vào một service/query model chuyên biệt khi consistency là yêu cầu mạnh.
- Cache dữ liệu ít thay đổi và ghi rõ freshness.
- Không giả định Mono.zip tạo distributed transaction hoặc snapshot nhất quán.

## 11. Tracing và quan sát downstream

Một API aggregation cần theo dõi từng dependency riêng:

- Latency của customer/order/recommendation.
- Tỷ lệ timeout, 4xx, 5xx và network error.
- Số lần retry.
- Số response được fallback/degraded.
- Tổng latency của endpoint aggregation.
- Connection pool usage và pending acquire.
- Cancellation và request còn chạy sau deadline.

Dùng Micrometer Observation/Tracing với WebClient được cấu hình đúng để tạo client observation/span. Không ghi token hoặc dữ liệu cá nhân vào URL, log hay metric tag. Tag metric nên có cardinality thấp; tên dependency như customer/orders/recommendations là hợp lý, còn customerId/orderId không nên là tag metric.

## 12. Ví dụ Java 17 hoàn chỉnh với Spring Boot WebFlux

Ví dụ dùng Java 17 và Spring Boot 3.5.16. Ứng dụng có một endpoint dashboard gọi ba HTTP service:

- Customer là required.
- Orders và recommendations là optional.
- Mỗi downstream có timeout riêng.
- Toàn bộ aggregation có deadline tổng.
- Lỗi tạm thời ở optional service được chuyển thành fallback.
- Lỗi ở required service trả HTTP 502.
- Test dùng ba MockWebServer độc lập, không gọi dịch vụ bên ngoài.

### 12.1. Cấu trúc dự án

~~~text
http-aggregation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/AggregationApplication.java
    │   ├── java/demo/ServiceUrls.java
    │   ├── java/demo/DashboardModels.java
    │   ├── java/demo/DashboardService.java
    │   ├── java/demo/DashboardController.java
    │   └── java/demo/DownstreamErrorHandler.java
    └── test/java/demo/DashboardIntegrationTest.java
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 12.3. application.properties

~~~properties
spring.application.name=http-aggregation-demo

services.customer-base-url=http://localhost:8081
services.order-base-url=http://localhost:8082
services.recommendation-base-url=http://localhost:8083
~~~

Các URL localhost là cấu hình demo. Trong production, lấy địa chỉ từ service discovery, environment variables hoặc cấu hình triển khai; không hard-code endpoint nội bộ trong source.

### 12.4. AggregationApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ServiceUrls.class)
public class AggregationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AggregationApplication.class, args);
    }
}
~~~

### 12.5. ServiceUrls.java

~~~java
package demo;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "services")
public record ServiceUrls(
    URI customerBaseUrl,
    URI orderBaseUrl,
    URI recommendationBaseUrl
) {}
~~~

Spring Boot bind các property services.customer-base-url, services.order-base-url và services.recommendation-base-url vào record.

### 12.6. DashboardModels.java

~~~java
package demo;

import java.math.BigDecimal;
import java.util.List;

record CustomerProfile(
    String id,
    String name
) {}

record OrderSummary(
    int orderCount,
    BigDecimal totalSpend
) {
    static OrderSummary empty() {
        return new OrderSummary(0, BigDecimal.ZERO);
    }
}

record RecommendationResponse(
    List<String> items
) {
    static RecommendationResponse empty() {
        return new RecommendationResponse(List.of());
    }
}

record DashboardView(
    String customerId,
    String customerName,
    int orderCount,
    BigDecimal totalSpend,
    List<String> recommendations
) {}

record ApiError(
    String code,
    String dependency
) {}
~~~

Các record package-private nằm cùng package demo để ví dụ gọn. Trong dự án thật, có thể tách mỗi DTO thành file riêng.

### 12.7. DashboardService.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

@Service
class DashboardService {

    private static final Logger log =
        LoggerFactory.getLogger(DashboardService.class);

    private static final Duration DEPENDENCY_TIMEOUT =
        Duration.ofSeconds(2);

    private static final Duration TOTAL_TIMEOUT =
        Duration.ofSeconds(4);

    private final WebClient customerClient;
    private final WebClient orderClient;
    private final WebClient recommendationClient;

    DashboardService(
            WebClient.Builder builder,
            ServiceUrls urls) {

        this.customerClient = builder.clone()
            .baseUrl(urls.customerBaseUrl().toString())
            .build();

        this.orderClient = builder.clone()
            .baseUrl(urls.orderBaseUrl().toString())
            .build();

        this.recommendationClient = builder.clone()
            .baseUrl(urls.recommendationBaseUrl().toString())
            .build();
    }

    Mono<DashboardView> getDashboard(String customerId) {

        Mono<CustomerProfile> customer =
            customerClient.get()
                .uri("/customers/{id}", customerId)
                .retrieve()
                .bodyToMono(CustomerProfile.class)
                .timeout(DEPENDENCY_TIMEOUT)
                .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                        "Customer service returned an empty body"
                    )
                ))
                .onErrorMap(error ->
                    new RequiredDependencyFailure("customer", error)
                );

        Mono<OrderSummary> orders = optional(
            orderClient.get()
                .uri("/orders/summary/{id}", customerId)
                .retrieve()
                .bodyToMono(OrderSummary.class),
            OrderSummary::empty,
            "orders"
        );

        Mono<RecommendationResponse> recommendations = optional(
            recommendationClient.get()
                .uri("/recommendations/{id}", customerId)
                .retrieve()
                .bodyToMono(RecommendationResponse.class),
            RecommendationResponse::empty,
            "recommendations"
        );

        return Mono.zip(customer, orders, recommendations)
            .map(tuple -> new DashboardView(
                tuple.getT1().id(),
                tuple.getT1().name(),
                tuple.getT2().orderCount(),
                tuple.getT2().totalSpend(),
                tuple.getT3().items()
            ))
            .timeout(TOTAL_TIMEOUT);
    }

    private <T> Mono<T> optional(
            Mono<T> source,
            Supplier<T> fallback,
            String dependency) {

        return source
            .timeout(DEPENDENCY_TIMEOUT)
            .switchIfEmpty(Mono.fromSupplier(fallback))
            .onErrorResume(
                this::isRecoverable,
                error -> {
                    log.warn(
                        "Optional dependency {} failed; using fallback",
                        dependency,
                        error
                    );
                    return Mono.fromSupplier(fallback);
                }
            );
    }

    private boolean isRecoverable(Throwable error) {
        if (error instanceof TimeoutException
                || error instanceof WebClientRequestException) {
            return true;
        }

        return error instanceof WebClientResponseException response
            && response.getStatusCode().is5xxServerError();
    }
}
~~~

Điểm quan trọng:

1. Ba WebClient được cấu hình từ cùng Boot-managed builder nhưng có base URL riêng.
2. Ba request được tạo thành ba Mono độc lập trước khi gọi zip.
3. Customer không có fallback vì là required dependency.
4. Orders và recommendations dùng helper optional để xử lý timeout, network error và 5xx.
5. 4xx không nằm trong danh sách recoverable nên được phát lỗi.
6. Response body rỗng của optional service được thay bằng giá trị mặc định.
7. Response body rỗng của customer được chuyển thành lỗi.
8. Timeout tổng bảo vệ API ngay cả khi từng nhánh có retry/fallback trong tương lai.

Trong ví dụ này không bật retry tự động để giữ hành vi kiểm thử đơn giản. Phần 7 trình bày cách thêm retry có giới hạn khi downstream và nghiệp vụ cho phép.

### 12.8. RequiredDependencyFailure.java

~~~java
package demo;

final class RequiredDependencyFailure extends RuntimeException {

    private final String dependency;

    RequiredDependencyFailure(
            String dependency,
            Throwable cause) {
        super("Required dependency failed: " + dependency, cause);
        this.dependency = dependency;
    }

    String dependency() {
        return dependency;
    }
}
~~~

### 12.9. DashboardController.java

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/dashboard")
class DashboardController {

    private final DashboardService service;

    DashboardController(DashboardService service) {
        this.service = service;
    }

    @GetMapping("/{customerId}")
    Mono<DashboardView> getDashboard(
            @PathVariable String customerId) {

        return service.getDashboard(customerId);
    }
}
~~~

Controller trả thẳng Mono cho WebFlux. Không gọi block() hoặc subscribe() trong controller/service; framework quản lý subscription theo lifecycle HTTP request.

### 12.10. DownstreamErrorHandler.java

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class DownstreamErrorHandler {

    @ExceptionHandler(RequiredDependencyFailure.class)
    ResponseEntity<ApiError> handleRequiredDependency(
            RequiredDependencyFailure error) {

        ApiError body = new ApiError(
            "REQUIRED_DEPENDENCY_UNAVAILABLE",
            error.dependency()
        );

        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(body);
    }
}
~~~

API trả 502 khi nguồn dữ liệu bắt buộc thất bại. Không trả raw exception message hoặc stack trace ra client.

### 12.11. DashboardIntegrationTest.java

~~~java
package demo;

import java.io.IOException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DashboardIntegrationTest {

    private static final MockWebServer CUSTOMER = startServer();
    private static final MockWebServer ORDERS = startServer();
    private static final MockWebServer RECOMMENDATIONS = startServer();

    @Autowired
    WebTestClient client;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void registerServiceUrls(DynamicPropertyRegistry registry) {
        registry.add(
            "services.customer-base-url",
            () -> CUSTOMER.url("/").toString()
        );
        registry.add(
            "services.order-base-url",
            () -> ORDERS.url("/").toString()
        );
        registry.add(
            "services.recommendation-base-url",
            () -> RECOMMENDATIONS.url("/").toString()
        );
    }

    @AfterAll
    static void stopServers() throws IOException {
        CUSTOMER.shutdown();
        ORDERS.shutdown();
        RECOMMENDATIONS.shutdown();
    }

    private MockResponse json(String body) {
        return new MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody(body);
    }

    @Test
    void combinesAllThreeServices() throws Exception {
        CUSTOMER.enqueue(json(
            "{\"id\":\"42\",\"name\":\"An\"}"
        ));
        ORDERS.enqueue(json(
            "{\"orderCount\":3,\"totalSpend\":125.50}"
        ));
        RECOMMENDATIONS.enqueue(json(
            "{\"items\":[\"book\",\"keyboard\"]}"
        ));

        client.get()
            .uri("/api/dashboard/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.customerId").isEqualTo("42")
            .jsonPath("$.customerName").isEqualTo("An")
            .jsonPath("$.orderCount").isEqualTo(3)
            .jsonPath("$.recommendations[0]").isEqualTo("book")
            .jsonPath("$.recommendations[1]").isEqualTo("keyboard");

        assertEquals(
            "/customers/42",
            CUSTOMER.takeRequest().getPath()
        );
        assertEquals(
            "/orders/summary/42",
            ORDERS.takeRequest().getPath()
        );
        assertEquals(
            "/recommendations/42",
            RECOMMENDATIONS.takeRequest().getPath()
        );
    }

    @Test
    void optionalOrdersFailureReturnsDegradedDashboard()
            throws Exception {

        CUSTOMER.enqueue(json(
            "{\"id\":\"42\",\"name\":\"An\"}"
        ));
        ORDERS.enqueue(
            new MockResponse().setResponseCode(503)
        );
        RECOMMENDATIONS.enqueue(json(
            "{\"items\":[\"book\"]}"
        ));

        client.get()
            .uri("/api/dashboard/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.customerName").isEqualTo("An")
            .jsonPath("$.orderCount").isEqualTo(0)
            .jsonPath("$.recommendations[0]").isEqualTo("book");

        assertEquals(
            "/customers/42",
            CUSTOMER.takeRequest().getPath()
        );
        assertEquals(
            "/orders/summary/42",
            ORDERS.takeRequest().getPath()
        );
        assertEquals(
            "/recommendations/42",
            RECOMMENDATIONS.takeRequest().getPath()
        );
    }

    @Test
    void requiredCustomerFailureReturnsBadGateway()
            throws Exception {

        CUSTOMER.enqueue(
            new MockResponse().setResponseCode(503)
        );
        ORDERS.enqueue(json(
            "{\"orderCount\":3,\"totalSpend\":125.50}"
        ));
        RECOMMENDATIONS.enqueue(json(
            "{\"items\":[\"book\"]}"
        ));

        client.get()
            .uri("/api/dashboard/42")
            .exchange()
            .expectStatus().isBadGateway()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("REQUIRED_DEPENDENCY_UNAVAILABLE")
            .jsonPath("$.dependency")
            .isEqualTo("customer");
    }
}
~~~

Các test dùng ba MockWebServer riêng nên mỗi dependency có response queue độc lập. Chúng kiểm tra:

- Cả ba dịch vụ trả dữ liệu: API ghép thành dashboard hoàn chỉnh.
- Orders trả 503: API dùng fallback cho nhánh optional, vẫn trả customer và recommendations.
- Customer trả 503: API trả 502 vì nhánh required thất bại.

WebTestClient gọi server WebFlux thật trên port ngẫu nhiên; MockWebServer chỉ đóng vai downstream. Không cần Internet hoặc cài ba service nghiệp vụ riêng.

### 12.12. Chạy test và ứng dụng

Chạy test bằng Gradle wrapper:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle test
~~~

Chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Endpoint chính:

~~~http
GET http://localhost:8080/api/dashboard/42
~~~

Các downstream URL được cấu hình trong application.properties. Để chạy demo thủ công, cần khởi động ba HTTP service tương thích trên các port 8081, 8082 và 8083, hoặc đổi base URL sang môi trường mock/staging của bạn.

## 13. Các biến thể thiết kế

### 13.1. Tất cả downstream đều required

Nếu mọi nguồn đều bắt buộc, không fallback:

~~~java
return Mono.zip(
    loadCustomer(id),
    loadOrders(id),
    loadRecommendations(id)
).map(this::combine);
~~~

Một lỗi ở bất kỳ nguồn nào sẽ làm aggregation thất bại. Hãy map lỗi thành status và mã lỗi API nhất quán.

### 13.2. Tất cả downstream đều optional

Nếu response có thể tồn tại với dữ liệu rỗng, mỗi nguồn nên có default rõ ràng:

~~~java
Mono<OrderSummary> orders =
    loadOrders(id).defaultIfEmpty(OrderSummary.empty());

Mono<RecommendationResponse> recommendations =
    loadRecommendations(id)
        .defaultIfEmpty(RecommendationResponse.empty());
~~~

defaultIfEmpty chỉ xử lý complete rỗng; nó không xử lý error. Muốn fallback khi lỗi, thêm onErrorResume với policy cụ thể.

### 13.3. Trả partial result có trạng thái degraded

Một model có thể chứa:

~~~java
record DashboardView(
    String customerName,
    OrderSummary orders,
    RecommendationResponse recommendations,
    List<String> degradedDependencies
) {}
~~~

Mỗi optional branch có thể trả wrapper chứa dữ liệu và trạng thái nguồn. Cách này giúp client phân biệt "không có đơn hàng" với "Order Service không phản hồi".

### 13.4. Một nguồn trả Flux

Nếu một dịch vụ trả stream event, không ép thành Mono bằng cách lấy tùy tiện phần tử đầu. Chọn:

- collectList nếu danh sách nhỏ và có giới hạn.
- take(n) nếu chỉ cần n phần tử đầu.
- Stream response trực tiếp nếu client cũng tiêu thụ streaming.
- Window/buffer có giới hạn nếu cần nhóm dữ liệu.

### 13.5. Fan-out động theo danh sách

~~~java
Flux<ProductView> result = Flux.fromIterable(productIds)
    .flatMap(this::loadProduct, 12);
~~~

Giới hạn 12 là ví dụ. Nếu list đến từ client, validate số phần tử tối đa trước khi fan-out. Không để một request duy nhất mở hàng nghìn connection downstream.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi độc lập theo chuỗi flatMap | Latency gần tổng thời gian downstream | Dùng Mono.zip khi không có dependency |
| Dùng zip cho Mono<Void> | Hàm combine không chạy vì không có item | Dùng Mono.when cho completion |
| Không xử lý Mono.empty | Zip complete rỗng, không có dashboard | switchIfEmpty/defaultIfEmpty theo contract |
| Fallback cho mọi exception | Che lỗi schema, auth hoặc bug | Chỉ fallback nhóm lỗi đã phân loại |
| Coi tất cả downstream là optional | API có thể trả dữ liệu sai/ngụy tạo | Phân loại required và optional |
| Không đặt timeout | Request có thể giữ tài nguyên quá lâu | Timeout từng dependency và deadline tổng |
| Retry không giới hạn | Retry storm và quá tải downstream | Backoff, jitter, attempt limit, deadline |
| Retry POST không idempotent | Tạo side effect trùng | Idempotency key hoặc không retry |
| Dùng flatMap không giới hạn | Fan-out quá lớn, cạn pool | Giới hạn concurrency |
| Dùng concat cho nguồn độc lập | Không tận dụng thời gian chờ song song | Merge/zip theo contract |
| Dùng merge nhưng giả định thứ tự | Response/event order không ổn định | Dùng concat hoặc flatMapSequential khi cần |
| Tự subscribe trong service | Mất lifecycle và cancellation của request | Trả Mono/Flux cho caller |
| block trong controller | Chặn event loop | Giữ pipeline reactive |
| Không propagate cancellation | Downstream tiếp tục chạy sau khi caller rời đi | Không tách subscription; cleanup theo lifecycle |
| Tăng connection pool vô hạn | Tăng socket/memory và áp lực downstream | Capacity plan và giới hạn concurrency |
| Gộp nhiều snapshot mà không đánh giá | Response có dữ liệu lệch thời điểm | Snapshot/version hoặc eventual consistency rõ |
| Không quan sát từng dependency | Khó biết service nào làm chậm aggregation | Metric/span riêng theo downstream |
| Ghi ID/token vào metric tag | Cardinality cao và rò dữ liệu | Dùng tag ổn định, mask dữ liệu nhạy cảm |

## 15. Checklist review aggregation flow

1. **Dependency graph:** các downstream nào độc lập, nhánh nào phụ thuộc kết quả trước?
2. **Required/optional:** service nào bắt buộc để tạo response hợp lệ?
3. **Operator:** dùng zip, flatMap, merge, concat hay when đúng semantics?
4. **Empty:** mỗi Mono có thể empty không và policy là gì?
5. **Error:** phân loại 4xx, 5xx, network error, decode error?
6. **Fallback:** có chỉ áp dụng cho nhánh optional và nhóm lỗi cho phép?
7. **Timeout:** có timeout per dependency và deadline tổng?
8. **Retry:** số lần, backoff, filter và idempotency đã rõ?
9. **Concurrency:** có giới hạn fan-out động?
10. **Backpressure:** stream/buffer/prefetch có giới hạn?
11. **Cancellation:** caller disconnect có dừng request không cần thiết?
12. **Consistency:** các nguồn có cần snapshot chung không?
13. **Observability:** có latency/error/fallback metric theo dependency?
14. **Security:** outbound credential, TLS và secret được quản lý đúng?
15. **Tests:** có success, optional failure, required failure, timeout và empty response?
16. **Contract:** partial response có biểu diễn degraded state rõ cho client?

**Ghi nhớ:** Dùng Mono.zip cho nhiều nguồn trả một giá trị và không phụ thuộc nhau; dùng flatMap khi request sau cần kết quả trước; dùng merge khi ghép stream theo thứ tự đến và concat khi phải giữ thứ tự tuần tự. Phân loại required/optional trước khi viết fallback. Đặt timeout riêng và deadline tổng, retry chỉ lỗi tạm thời có thể thử lại, giới hạn fan-out và để cancellation/backpressure đi xuyên suốt. Một API aggregation tốt phải vừa nhanh khi các nguồn khỏe mạnh, vừa trả lỗi hoặc partial response có chủ đích khi một downstream gặp sự cố.

## Tài liệu tham khảo

- Spring Framework — WebClient retrieve(), bodyToMono(), bodyToFlux() and onStatus: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — WebClient configuration and builder: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Reactor Core — Mono.zip and zipDelayError API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core — Reference Guide, error handling, timeout and retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Core — Reference Guide, flatMap, merge, concat and backpressure: https://projectreactor.io/docs/core/release/reference/
- Spring Boot 3.5 — WebFlux and WebClient configuration: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- OkHttp MockWebServer — API and usage: https://github.com/square/okhttp/tree/master/mockwebserver
