# Chuyển HTTP status thành lỗi trước khi Circuit Breaker ghi nhận

Khi gọi một dịch vụ HTTP, nhận được phản hồi HTTP không đồng nghĩa với thao tác nghiệp vụ đã thành công. Một phản hồi `503 Service Unavailable` hoặc `504 Gateway Timeout` cho biết phụ thuộc đang gặp vấn đề, nhưng nếu ứng dụng chỉ trả về một đối tượng chứa status code như một kết quả bình thường, Circuit Breaker có thể xem lời gọi đó là thành công. Muốn Circuit Breaker ghi nhận đúng lỗi, cần chuyển những HTTP status được xem là lỗi phụ thuộc thành exception trước khi kết quả đi qua bộ bảo vệ.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, việc phân loại kết quả là một phần của triển khai Circuit Breaker trong Spring Cloud và Resilience4j. Ta cần phân biệt lỗi hạ tầng với kết quả nghiệp vụ như không tìm thấy tài nguyên, sau đó quyết định exception nào được tính vào sliding window, exception nào được bỏ qua và khi nào dùng fallback.

## 1. Vì sao HTTP status cần được chuyển thành exception?

Circuit Breaker quan sát kết quả của lời gọi mà nó bọc. Với API đồng bộ, một lời gọi thường được xem là thành công khi `Supplier<T>` trả về giá trị và thất bại khi nó ném exception. Với API reactive, publisher hoàn tất bình thường là thành công; publisher phát tín hiệu `onError` là thất bại.

Giả sử dịch vụ Đơn hàng gọi dịch vụ Kho:

| Phản hồi từ dịch vụ Kho | Ý nghĩa có thể có | Cách phân loại thường gặp |
| --- | --- | --- |
| `200 OK` | Truy vấn tồn kho thành công | Kết quả thành công |
| `404 Not Found` | SKU không tồn tại hoặc tài nguyên không được tìm thấy | Thường là kết quả nghiệp vụ; không nhất thiết là lỗi phụ thuộc |
| `400 Bad Request` hoặc `422 Unprocessable Entity` | Dữ liệu gửi sang không hợp lệ | Lỗi đầu vào hoặc nghiệp vụ cần xử lý riêng |
| `401 Unauthorized` hoặc `403 Forbidden` | Xác thực hoặc quyền truy cập không hợp lệ | Lỗi cấu hình hoặc bảo mật cần điều tra |
| `429 Too Many Requests` | Phụ thuộc đang giới hạn lưu lượng | Có thể xem là lỗi tạm thời hoặc tình trạng bị giới hạn |
| `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout` | Phụ thuộc hoặc gateway gặp sự cố | Thường được tính là lỗi phụ thuộc |

Nếu client trả về `ResponseEntity<Inventory>` với status 503 nhưng không ném exception, đoạn code bọc quanh Circuit Breaker có thể hoàn tất bình thường. Khi đó, Circuit Breaker không có tín hiệu lỗi để tăng failure rate. Việc kiểm tra status và ném exception phải xảy ra bên trong thao tác được Circuit Breaker bảo vệ.

Luồng xử lý mong muốn:

~~~mermaid
flowchart TD
    A[Lời gọi HTTP đến dịch vụ phụ thuộc] --> B[Đọc HTTP status]
    B --> C{Status cần xem là lỗi?}
    C -->|Không| D[Trả kết quả bình thường]
    C -->|Có| E[Chuyển status thành exception phù hợp]
    D --> F[Circuit Breaker quan sát kết quả]
    E --> F
    F --> G{Exception có bị bỏ qua?}
    G -->|Có| H[Không tính vào tỷ lệ lỗi]
    G -->|Không| I[Ghi nhận lỗi vào sliding window]
~~~

Circuit Breaker chỉ có thể phân loại đúng những gì lời gọi truyền đến nó. Nếu HTTP client đã biến lỗi thành một giá trị bình thường, cần chuẩn hóa giá trị đó thành exception trước khi Circuit Breaker đánh giá.

## 2. Hành vi mặc định của RestTemplate và WebClient

Hai HTTP client phổ biến trong Spring có hành vi xử lý status khác nhau về API, nhưng đều hỗ trợ chuyển status lỗi thành exception.

### RestTemplate

Mặc định, `RestTemplate` sử dụng `DefaultResponseErrorHandler`. Error handler này xem các status 4xx và 5xx là lỗi, sau đó ném exception khi thực hiện lời gọi, thường là `HttpClientErrorException` cho nhóm 4xx và `HttpServerErrorException` cho nhóm 5xx. Các exception này thuộc hệ exception của Spring Web.

Do đó, khi dùng cấu hình mặc định, lời gọi có thể được bọc trực tiếp:

~~~java
public Inventory getInventory(String sku) {
    return circuitBreaker.run(
            () -> restTemplate.getForObject(
                    inventoryUrl + "/items/{sku}",
                    Inventory.class,
                    sku),
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

Nếu dịch vụ Kho trả 503, `RestTemplate` ném exception bên trong `Supplier`. Circuit Breaker nhận được exception đó và áp dụng chính sách ghi nhận lỗi. Hàm fallback nhận nguyên nhân qua biến `failure`.

Nếu ứng dụng đã cài một `ResponseErrorHandler` tùy chỉnh và handler đó không coi một status nhất định là lỗi, `RestTemplate` có thể trả response bình thường cho status đó. Khi ấy, cần kiểm tra status và ném exception ngay trong `Supplier`, trước khi trả kết quả cho Circuit Breaker.

### WebClient

Với `WebClient`, cách dùng `retrieve()` mặc định chuyển status 4xx và 5xx thành `WebClientResponseException`. Có thể tùy chỉnh việc chuyển đổi bằng `onStatus` để tạo exception mang ngữ nghĩa của ứng dụng:

~~~java
Mono<Inventory> primary =
        webClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .onStatus(
                        HttpStatusCode::isError,
                        response -> response.bodyToMono(String.class)
                                .defaultIfEmpty("")
                                .map(body -> mapInventoryError(
                                        response.statusCode().value(),
                                        body))
                )
                .bodyToMono(Inventory.class);
~~~

Hàm `mapInventoryError` trả về một exception dựa trên status. `onStatus` yêu cầu hàm chuyển đổi trả về một publisher chứa exception; khi publisher chính được subscribe, exception sẽ được phát dưới dạng tín hiệu `onError`.

Ví dụ hàm phân loại:

~~~java
private RuntimeException mapInventoryError(int status, String responseBody) {
    if (status == 404) {
        return new InventoryNotFoundException();
    }
    if (status == 400 || status == 422) {
        return new InventoryRequestException();
    }
    if (status == 408 || status == 429 || status >= 500) {
        return new DownstreamUnavailableException(status);
    }
    return new DownstreamHttpException(status);
}
~~~

Các exception như `InventoryNotFoundException`, `InventoryRequestException`, `DownstreamUnavailableException` và `DownstreamHttpException` là lớp nghiệp vụ minh họa do ứng dụng định nghĩa. Có thể giữ thêm status code trong exception để log và giám sát mà không phải phân tích lại nội dung response.

Với Spring Framework 6, predicate thường nhận `HttpStatusCode`; ở các phiên bản cũ hơn có thể cần dùng kiểu `HttpStatus` tương ứng. Hãy điều chỉnh chữ ký theo phiên bản Spring đang dùng.

### Khi dùng exchangeToMono

`retrieve()` có xử lý mặc định cho status 4xx và 5xx. Nếu dùng `exchangeToMono()`, ứng dụng tự quyết định cách xử lý từng response. Vì vậy, cần chủ động tạo tín hiệu lỗi cho status muốn Circuit Breaker ghi nhận:

~~~java
Mono<Inventory> primary =
        webClient.get()
                .uri("/items/{sku}", sku)
                .exchangeToMono(response -> {
                    if (response.statusCode().isError()) {
                        return response.createException()
                                .flatMap(error -> Mono.<Inventory>error(error));
                    }
                    return response.bodyToMono(Inventory.class);
                });
~~~

Nếu bỏ qua nhánh kiểm tra status và chỉ đọc body, một phản hồi lỗi có thể bị xử lý như dữ liệu bình thường tùy cách body được giải mã. Khi dùng `exchangeToMono`, hãy quyết định rõ status nào tạo exception, status nào trở thành kết quả nghiệp vụ và status nào cần được bỏ qua.

## 3. Đặt bước chuyển đổi lỗi bên trong Circuit Breaker

Thứ tự bọc thao tác quyết định Circuit Breaker có nhìn thấy exception hay không. Với reactive, cần tạo publisher HTTP đã có bước chuyển status thành exception, rồi truyền publisher đó vào `ReactiveCircuitBreaker.run`:

~~~java
public Mono<Inventory> getInventory(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            reactiveCircuitBreakerFactory.create("inventory");

    Mono<Inventory> primary = webClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .onStatus(
                    HttpStatusCode::isError,
                    response -> response.bodyToMono(String.class)
                            .defaultIfEmpty("")
                            .map(body -> mapInventoryError(
                                    response.statusCode().value(),
                                    body))
            )
            .bodyToMono(Inventory.class);

    return circuitBreaker.run(
            primary,
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

Trong luồng này:

1. `WebClient` gửi request và nhận response.
2. `onStatus` chuyển status lỗi thành exception.
3. Publisher chính phát `onError` nếu response thuộc nhóm lỗi đã ánh xạ.
4. Circuit Breaker quan sát tín hiệu lỗi và cập nhật số liệu theo cấu hình.
5. Fallback được gọi để tạo phản hồi dự phòng nếu ứng dụng đã cung cấp fallback.

Với lời gọi đồng bộ, nguyên tắc tương tự: việc kiểm tra status và ném exception phải nằm trong `Supplier` truyền cho `circuitBreaker.run`.

Không nên bắt exception rồi trả một giá trị mặc định bên trong thao tác chính nếu muốn Circuit Breaker ghi nhận lỗi. Ví dụ sau làm mất tín hiệu lỗi:

~~~java
// Không phù hợp nếu muốn Circuit Breaker ghi nhận lỗi HTTP.
Mono<Inventory> primary = webClient.get()
        .uri("/items/{sku}", sku)
        .retrieve()
        .bodyToMono(Inventory.class)
        .onErrorReturn(Inventory.unavailable());

return circuitBreaker.run(primary, failure -> fallbackInventory(sku, failure));
~~~

`onErrorReturn` đã chuyển tín hiệu lỗi thành một giá trị phát bình thường trước khi publisher đi vào Circuit Breaker. Circuit Breaker có thể ghi nhận lời gọi là thành công và fallback của nó không được gọi. Hãy để lỗi truyền đến Circuit Breaker, sau đó xử lý bằng fallback được truyền cho Circuit Breaker hoặc ở tầng bên ngoài sau khi lỗi đã được ghi nhận.

## 4. Phân biệt lỗi phụ thuộc và lỗi nghiệp vụ

Không nên chuyển mọi status 4xx thành cùng một loại lỗi hạ tầng. Ví dụ, 404 có thể chỉ có nghĩa SKU không tồn tại. Nếu mỗi lần tìm SKU không tồn tại đều làm tăng failure rate, Circuit Breaker có thể mở dù dịch vụ Kho đang hoạt động bình thường.

Một cách làm là ánh xạ status thành exception riêng:

| HTTP status | Exception ứng dụng | Chính sách Circuit Breaker gợi ý |
| --- | --- | --- |
| 404 | `InventoryNotFoundException` | Bỏ qua trong phép tính lỗi nếu đây là kết quả nghiệp vụ bình thường |
| 400, 422 | `InventoryRequestException` | Xử lý như lỗi dữ liệu đầu vào; thường bỏ qua trong phép tính lỗi phụ thuộc |
| 408 | `DownstreamUnavailableException` | Thường ghi nhận là lỗi tạm thời |
| 429 | `DownstreamUnavailableException` hoặc exception giới hạn lưu lượng riêng | Chọn theo chính sách retry, rate limit và vận hành |
| 500–599 | `DownstreamUnavailableException` | Thường ghi nhận là lỗi phụ thuộc |
| 401, 403 | `DownstreamHttpException` hoặc exception bảo mật riêng | Điều tra credential và quyền; quyết định chính sách riêng |

Ví dụ, cấu hình Resilience4j có thể bỏ qua các exception nghiệp vụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        ignoreExceptions:
          - com.example.InventoryNotFoundException
          - com.example.InventoryRequestException
~~~

Các exception bị liệt kê trong `ignoreExceptions` không được tính là thành công hay thất bại trong sliding window. Chúng không làm tăng failure rate. Những exception khác sẽ tuân theo chính sách ghi nhận mặc định hoặc các thuộc tính `recordExceptions` đã cấu hình.

Nếu khai báo `recordExceptions`, cần chú ý rằng exception không khớp danh sách ghi nhận sẽ không được xem là lỗi theo chính sách đó; hãy liệt kê đầy đủ các exception cần tính. `ignoreExceptions` có độ ưu tiên loại trừ đối với những exception được chỉ định. Không nên thêm `recordExceptions` chỉ để ghi một loại lỗi nếu chưa xem xét tác động với các exception khác.

Việc bỏ qua exception trong Circuit Breaker không có nghĩa là bỏ qua xử lý lỗi ở tầng nghiệp vụ. API vẫn có thể trả 404 hoặc 400 cho client, ghi log phù hợp và hiển thị thông báo đúng nghĩa; chỉ có phép tính tình trạng sức khỏe của phụ thuộc là không tính các kết quả đó như lỗi.

## 5. Fallback nhận exception đã phân loại

Khi status đã được chuyển thành exception, fallback có thể quyết định cách phản hồi theo nguyên nhân:

~~~java
private Mono<Inventory> fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof InventoryNotFoundException) {
        return Mono.error(failure);
    }

    return inventoryCache.findRecent(sku)
            .map(cached -> cached.withStale(true))
            .defaultIfEmpty(Inventory.unavailable());
}
~~~

Trong ví dụ, lỗi không tìm thấy SKU được chuyển tiếp để tầng nghiệp vụ trả đúng kết quả. Với lỗi phụ thuộc hoặc Circuit Breaker từ chối lời gọi, ứng dụng thử lấy dữ liệu cache và đánh dấu dữ liệu cũ. Nếu không có cache, ứng dụng trả trạng thái tồn kho chưa xác định.

Fallback không nên biến mọi lỗi thành số lượng tồn kho bằng 0. Giá trị 0 có thể mang nghĩa đã xác nhận hết hàng, còn trạng thái unavailable có nghĩa không thể xác minh. Hai kết quả này khác nhau và ảnh hưởng trực tiếp đến quyết định đặt hàng.

Với API đồng bộ, có thể áp dụng cùng cách phân loại:

~~~java
private Inventory fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof InventoryNotFoundException) {
        throw (InventoryNotFoundException) failure;
    }
    return inventoryCache.findRecent(sku)
            .orElseGet(Inventory::unavailable);
}
~~~

Nếu fallback tự ném exception, lời gọi tổng thể vẫn có thể thất bại. Cần theo dõi cả số lần fallback được gọi và số lần fallback không tạo được kết quả.

## 6. Kiểm tra việc Circuit Breaker ghi nhận status lỗi

Có thể kiểm tra hành vi theo từng trường hợp bằng test ở tầng tích hợp hoặc kiểm thử thành phần với HTTP server giả:

| Kịch bản | Kết quả mong đợi từ HTTP client | Kết quả mong đợi từ Circuit Breaker |
| --- | --- | --- |
| Dịch vụ trả 200 | Publisher hoàn tất bình thường hoặc trả object | Ghi nhận thành công |
| Dịch vụ trả 503 | Ném exception đã ánh xạ | Ghi nhận lỗi nếu exception không bị ignore |
| Dịch vụ trả 404 và được phân loại là nghiệp vụ | Ném `InventoryNotFoundException` hoặc trả kết quả nghiệp vụ rõ ràng | Không tăng failure rate nếu exception được ignore |
| Mạch đang OPEN | Lời gọi bị Circuit Breaker từ chối trước khi gửi HTTP request | Ghi nhận việc từ chối theo metrics phù hợp; fallback có thể được gọi |
| Lỗi bị `onErrorResume` xử lý trước Circuit Breaker | Publisher hoàn tất bình thường | Có thể bị ghi nhận là thành công; cần tránh nếu muốn đếm lỗi gốc |

Trong kiểm thử, không chỉ xác nhận API cuối cùng trả về giá trị nào. Cần xác nhận loại exception phát ra từ HTTP client, fallback có nhận đúng exception hay không và failure rate của Circuit Breaker có thay đổi như mong đợi hay không.

Nếu cần kiểm tra hành vi của Resilience4j, có thể quan sát trạng thái và metrics của instance sau một số lời gọi thử nghiệm. Đặt cửa sổ và số lời gọi tối thiểu nhỏ trong môi trường kiểm thử để có thể tái hiện chuyển trạng thái; không dùng các giá trị thử nghiệm đó làm cấu hình sản xuất nếu chưa đánh giá lưu lượng thật.

## 7. Quan sát và chẩn đoán

Để biết việc phân loại HTTP status có hiệu quả, nên theo dõi các số liệu sau:

- Số response theo từng status code của từng phụ thuộc.
- Số exception theo lớp, chẳng hạn `DownstreamUnavailableException` và `InventoryNotFoundException`.
- Failure rate và slow call rate của từng Circuit Breaker.
- Số lần Circuit Breaker từ chối lời gọi khi OPEN.
- Số lần fallback được gọi và tỷ lệ fallback thành công.
- Độ trễ của HTTP client trước khi status được chuyển thành exception.

Nếu log cho thấy nhiều HTTP 503 nhưng failure rate của Circuit Breaker không tăng, hãy kiểm tra xem HTTP client có trả response như giá trị bình thường hay không, custom error handler có bỏ qua status đó hay không, và có bước `onErrorResume` hoặc `onErrorReturn` nào đã xử lý lỗi trước Circuit Breaker không.

Nếu failure rate tăng mạnh khi nhiều SKU không tồn tại, hãy xem lại cách ánh xạ 404 và cấu hình `ignoreExceptions`. Nếu mạch mở vì lỗi 401 hoặc 403, cần điều tra cấu hình credential và quyền truy cập thay vì mặc định coi đây là sự cố mạng.

Khi ghi log body của response lỗi, cần giới hạn kích thước và loại bỏ dữ liệu nhạy cảm. Không nên lưu token, thông tin cá nhân hoặc nội dung request riêng tư chỉ để chẩn đoán status code.

## 8. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Trả response chứa status 5xx như một object bình thường | Circuit Breaker có thể ghi nhận thành công | Ném exception bên trong lời gọi được bảo vệ |
| Dùng `onErrorReturn` trước Circuit Breaker | Lỗi bị đổi thành giá trị thành công trước khi Circuit Breaker quan sát | Dùng fallback của Circuit Breaker hoặc xử lý lỗi ở tầng ngoài |
| Coi mọi status 4xx là lỗi hạ tầng | Lỗi nghiệp vụ làm tăng failure rate | Ánh xạ status thành exception có ý nghĩa và bỏ qua loại phù hợp |
| Chỉ kiểm tra status sau khi `circuitBreaker.run` trả về | Circuit Breaker đã quan sát response trước khi status được đổi thành exception | Đưa bước kiểm tra status vào Supplier hoặc publisher chính |
| Dùng `exchangeToMono` nhưng không xử lý nhánh status lỗi | Status có thể không trở thành tín hiệu lỗi theo ý định | Chủ động trả `Mono.error(...)` cho status cần ghi nhận |
| Cấu hình `recordExceptions` quá hẹp | Một số lỗi phụ thuộc không được tính là lỗi | Kiểm tra đầy đủ danh sách exception được ghi nhận |
| Fallback trả dữ liệu giả như tồn kho bằng 0 | Client hiểu nhầm dữ liệu không xác định thành dữ liệu chính xác | Trả trạng thái unavailable hoặc cache có đánh dấu thời điểm |

## 9. Quy trình triển khai

Khi tích hợp một HTTP client với Circuit Breaker, hãy thực hiện theo trình tự:

1. Xác định status nào biểu thị lỗi phụ thuộc, status nào là kết quả nghiệp vụ và status nào cần xử lý riêng.
2. Kiểm tra hành vi mặc định của HTTP client đang dùng: `RestTemplate`, `WebClient.retrieve()` hay `WebClient.exchangeToMono()`.
3. Chuyển status cần ghi nhận thành exception bên trong thao tác được Circuit Breaker bảo vệ.
4. Đặt `ignoreExceptions` cho lỗi nghiệp vụ không nên làm tăng failure rate; nếu dùng `recordExceptions`, xác minh mọi loại lỗi cần tính đều có trong chính sách.
5. Truyền fallback để xử lý lỗi phụ thuộc và lỗi từ chối do mạch OPEN, giữ nguyên lỗi nghiệp vụ cần trả cho client.
6. Kiểm tra status 200, 404, 503 và trạng thái OPEN; xác nhận cả exception, fallback lẫn metrics.
7. Theo dõi status code, failure rate, slow call rate và fallback trong môi trường chạy thật để điều chỉnh chính sách.

Chuyển HTTP status thành exception đúng vị trí giúp Circuit Breaker nhìn thấy sự cố của dịch vụ phụ thuộc và cập nhật sliding window chính xác. Phân loại exception theo ý nghĩa nghiệp vụ giúp cơ chế bảo vệ phản ứng với lỗi hạ tầng mà không nhầm những kết quả như “không tìm thấy” thành dấu hiệu dịch vụ đang hỏng.
