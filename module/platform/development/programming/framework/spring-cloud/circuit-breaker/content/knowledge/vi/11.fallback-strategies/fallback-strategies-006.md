# Tránh fallback gọi lại chính hệ thống đang lỗi

Fallback chỉ có ích khi nó giúp ứng dụng đưa ra phản hồi an toàn trong lúc lời gọi chính thất bại hoặc Circuit Breaker đang OPEN. Nếu fallback gọi lại chính dịch vụ vừa gặp sự cố, ứng dụng có thể tiếp tục tạo tải lên phụ thuộc, bỏ qua cơ chế ngắt mạch hoặc rơi vào vòng lặp fallback. Vì vậy, fallback cần lấy kết quả từ một nguồn độc lập, dùng dữ liệu dự phòng đã có hoặc trả trạng thái suy giảm được mô tả rõ ràng.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, Circuit Breaker của Spring Cloud và Resilience4j giúp giới hạn tác động khi dịch vụ phụ thuộc chậm hoặc không khả dụng. Fallback là một phần của chiến lược bảo vệ đó; nó cần phối hợp với trạng thái CLOSED, OPEN, HALF_OPEN, timeout, bulkhead và cơ chế theo dõi để tránh biến sự cố của một dịch vụ thành lỗi dây chuyền.

## 1. Vì sao fallback không được gọi lại phụ thuộc đang lỗi?

Giả sử dịch vụ Đơn hàng gọi dịch vụ Kho để lấy số lượng tồn. Khi Kho bị quá tải, Circuit Breaker mở mạch và từ chối các lời gọi mới. Fallback được chạy để trả dữ liệu cache hoặc thông báo chưa thể xác minh tồn kho.

Nếu fallback lại gọi dịch vụ Kho, có hai tình huống nguy hiểm:

- Fallback gọi trực tiếp HTTP client, bỏ qua Circuit Breaker. Dù mạch đã OPEN, request mới vẫn được gửi đến dịch vụ Kho và tiếp tục tăng tải.
- Fallback gọi lại phương thức đã được bảo vệ bởi cùng Circuit Breaker. Lời gọi lồng nhau có thể bị từ chối ngay khi mạch OPEN, kích hoạt fallback lần nữa và tạo đệ quy hoặc vòng lặp.

Sơ đồ của một thiết kế lỗi:

~~~mermaid
flowchart TD
    A[Yêu cầu từ dịch vụ Đơn hàng] --> B[Circuit Breaker]
    B --> C[Lời gọi dịch vụ Kho]
    C -->|Lỗi hoặc bị từ chối| D[Fallback]
    D --> E[Gọi lại dịch vụ Kho]
    E -->|Tiếp tục lỗi| D
    D --> F[Vòng lặp hoặc tải lặp lại]
~~~

Circuit Breaker nhằm ngăn lời gọi mới đến phụ thuộc đang gặp sự cố. Fallback gọi lại phụ thuộc đó sẽ phá vỡ mục tiêu bảo vệ. Một phương thức fallback cũng không nên gọi gián tiếp một service khác nếu service đó lại đi qua cùng đường gọi đang lỗi.

## 2. Nhận diện fallback nguy hiểm

Ví dụ sau minh họa một lỗi thiết kế: phương thức fallback gọi lại chính phương thức `getInventory` đang được bảo vệ.

~~~java
public InventoryResult getInventory(String sku) {
    CircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    return circuitBreaker.run(
            () -> inventoryClient.get(sku),
            failure -> fallbackInventory(sku, failure)
    );
}

private InventoryResult fallbackInventory(String sku, Throwable failure) {
    // Không an toàn: gọi lại chính luồng được bảo vệ.
    return getInventory(sku);
}
~~~

Khi mạch OPEN, lời gọi bên trong fallback có thể bị từ chối ngay và gọi fallback lần nữa. Nếu fallback tiếp tục gọi `getInventory`, luồng xử lý có thể đệ quy cho đến khi cạn stack. Nếu thay vào đó fallback gọi thẳng `inventoryClient.get(sku)`, nó vẫn tạo thêm request đến dịch vụ Kho dù Circuit Breaker đã ngăn lời gọi chính.

Một biến thể khác là fallback gọi một service trung gian, nhưng service đó lại dùng cùng endpoint hoặc cùng cụm dịch vụ Kho. Tên class hoặc URL khác không đảm bảo nguồn dữ liệu độc lập. Cần xem toàn bộ đường đi của request, bao gồm gateway, service discovery, proxy và các client được gọi gián tiếp.

Hãy đặt câu hỏi: khi dịch vụ chính không khả dụng, fallback có thực sự tránh được tài nguyên, endpoint và hạ tầng đang gặp sự cố hay không? Nếu câu trả lời là không, fallback đó chưa tạo ra một đường phục hồi đáng tin cậy.

## 3. Chọn nguồn dữ liệu dự phòng độc lập

Một fallback tốt thường dùng một trong các nguồn sau:

| Nguồn dự phòng | Khi phù hợp | Điều cần thể hiện |
| --- | --- | --- |
| Cache cục bộ | Dữ liệu đã được tải trước và có thể dùng trong thời gian ngắn | Đánh dấu dữ liệu cũ, thời điểm cập nhật và giới hạn tuổi dữ liệu |
| Cache hoặc kho đọc độc lập | Có thể truy vấn mà không phụ thuộc vào cùng hệ thống đang lỗi | Đảm bảo hạ tầng dự phòng không cùng chịu sự cố |
| Replica hoặc nhà cung cấp thay thế | Có nguồn thứ hai với khả năng phục vụ độc lập | Kiểm tra độ nhất quán, quyền truy cập và giới hạn lưu lượng |
| Dữ liệu đã tính trước | Kết quả có thể được tạo trước và không cần gọi dịch vụ chính khi fallback chạy | Ghi rõ thời điểm và phạm vi áp dụng |
| Trạng thái suy giảm | Không có dữ liệu đáng tin cậy để trả | Thể hiện rõ chưa thể xác minh, không giả vờ thành công |

Không phải fallback lúc nào cũng cần trả dữ liệu. Với thao tác thanh toán hoặc cập nhật trạng thái đơn hàng, trả về “chưa thể xác nhận” có thể an toàn hơn việc tạo một kết quả thành công giả. Tầng gọi có thể giữ yêu cầu ở trạng thái chờ xử lý, yêu cầu thử lại sau hoặc hiển thị thông báo phù hợp.

Cache cũng cần được đánh giá độc lập. Nếu cache là một cụm Redis dùng chung mạng, credential hoặc hạ tầng với dịch vụ đang lỗi, cache có thể gặp cùng sự cố. Với dữ liệu có yêu cầu nhất quán cao, dữ liệu cũ có thể không được phép dùng để ra quyết định. Fallback phải tuân theo quy tắc nghiệp vụ về tuổi dữ liệu và mức độ chấp nhận sai lệch.

## 4. Ví dụ đồng bộ: fallback dùng cache thay vì gọi lại dịch vụ Kho

Giả sử `inventoryClient` gọi dịch vụ Kho, còn `inventoryCache` cung cấp dữ liệu gần nhất đã được lưu trước đó. Fallback chỉ đọc cache và trả trạng thái unavailable nếu không có bản ghi:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    public InventoryResult getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.get(sku),
                failure -> fallbackInventory(sku, failure)
        );
    }

    private InventoryResult fallbackInventory(
            String sku,
            Throwable failure) {
        return inventoryCache.findRecent(sku)
                .map(cached -> cached.withStale(true))
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }
}
~~~

Trong ví dụ:

1. Lời gọi chính chỉ truy cập dịch vụ Kho thông qua `inventoryClient`.
2. Khi lời gọi chính thất bại hoặc mạch OPEN, Circuit Breaker chuyển nguyên nhân cho fallback.
3. Fallback đọc dữ liệu đã lưu trong cache; nó không gọi lại `inventoryClient` và không gọi `getInventory`.
4. Nếu cache không có dữ liệu, ứng dụng trả trạng thái chưa xác minh tồn kho.
5. Cờ `stale` giúp tầng gọi biết dữ liệu cache có thể cũ.

`InventoryCache` ở đây là một abstraction minh họa. Nếu triển khai bằng cache từ xa, cần đặt timeout và giới hạn tài nguyên cho thao tác đọc cache, đồng thời đánh giá liệu hạ tầng cache có độc lập với dịch vụ Kho hay không.

## 5. Ví dụ reactive: giữ fallback trong chuỗi Mono

Với WebClient, fallback nên trả về publisher và tiếp tục xử lý bất đồng bộ. Không gọi `block()` hoặc gửi một request mới đến cùng dịch vụ Kho trong fallback:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInventoryGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final WebClient inventoryWebClient;
    private final ReactiveInventoryCache inventoryCache;

    public ReactiveInventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            WebClient inventoryWebClient,
            ReactiveInventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryWebClient = inventoryWebClient;
        this.inventoryCache = inventoryCache;
    }

    public Mono<InventoryResult> getInventory(String sku) {
        ReactiveCircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        Mono<InventoryResult> primary = inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResult.class);

        return circuitBreaker.run(
                primary,
                failure -> inventoryCache.findRecent(sku)
                        .map(cached -> cached.withStale(true))
                        .defaultIfEmpty(InventoryResult.unavailable(sku))
        );
    }
}
~~~

Publisher cache được trả trực tiếp cho fallback. Khi cache không có dữ liệu, `defaultIfEmpty` tạo kết quả unavailable. Cả publisher chính và publisher fallback đều có kiểu `Mono<InventoryResult>`.

Không dùng cách sau:

~~~java
return circuitBreaker.run(
        primary,
        failure -> inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResult.class)
);
~~~

Đoạn mã này gửi lại request đến cùng dịch vụ Kho khi lời gọi chính đã lỗi hoặc bị từ chối. Nếu Kho đang quá tải, fallback tiếp tục tạo tải; nếu mạch OPEN nhưng request fallback không đi qua mạch đó, nó còn bỏ qua cơ chế chặn. Reactive không làm cho lời gọi lặp lại trở nên an toàn hơn; publisher vẫn tạo request khi được subscribe.

## 6. Nếu cần nguồn thay thế từ xa

Đôi khi cache không đủ và ứng dụng có một nhà cung cấp hoặc replica thứ hai. Có thể dùng nguồn thay thế nếu nó độc lập về đường mạng, năng lực phục vụ và miền lỗi. Tuy nhiên, nguồn thay thế cũng là một phụ thuộc và cần được bảo vệ.

Một số nguyên tắc:

- Dùng client và Circuit Breaker riêng cho nguồn thay thế, với timeout ngắn và bulkhead giới hạn số lời gọi đồng thời.
- Không cấu hình fallback của nguồn thay thế quay lại nguồn chính. Chuỗi dự phòng phải kết thúc ở một phản hồi terminal như cache hoặc trạng thái unavailable.
- Giới hạn số lần thử. Không dùng retry vô hạn trong fallback.
- Chỉ gọi nguồn thay thế cho lỗi có thể phục hồi; lỗi đầu vào hoặc lỗi nghiệp vụ cần được chuyển tiếp.
- Theo dõi riêng tỷ lệ gọi nguồn thay thế, thời gian phản hồi và số lần nguồn thay thế thất bại.

Sơ đồ của chuỗi dự phòng có giới hạn:

~~~mermaid
flowchart TD
    A[Yêu cầu] --> B[Circuit Breaker dịch vụ chính]
    B -->|Thành công| C[Kết quả chính]
    B -->|Lỗi hoặc OPEN| D[Fallback]
    D --> E[Cache độc lập]
    E -->|Có dữ liệu hợp lệ| F[Kết quả cache, đánh dấu cũ]
    E -->|Không có dữ liệu| G[Trạng thái unavailable]
    D -. Nguồn thay thế nếu được cho phép .-> H[Circuit Breaker riêng]
    H -->|Thành công| I[Kết quả từ nguồn thay thế]
    H -->|Lỗi hoặc OPEN| G
~~~

Trong mô hình này, nguồn thay thế không gọi ngược lại dịch vụ chính. Nếu nguồn thay thế cũng thất bại, luồng kết thúc bằng cache hoặc trạng thái unavailable. Tránh thiết kế các fallback phụ thuộc lẫn nhau thành vòng A gọi B, B gọi C, rồi C quay lại A.

## 7. Timeout, bulkhead và retry trong fallback

Fallback thường chạy đúng lúc hệ thống đang suy giảm, vì vậy nó cần ít tài nguyên và hoàn tất nhanh. Một fallback gọi dịch vụ từ xa có thể treo lâu hoặc chiếm hết luồng xử lý, khiến ứng dụng vẫn bị nghẽn dù Circuit Breaker đã chặn lời gọi chính.

| Cơ chế | Vai trò trong đường fallback |
| --- | --- |
| Timeout | Giới hạn thời gian chờ cache hoặc nguồn thay thế |
| Bulkhead | Giới hạn số lời gọi fallback đồng thời để tránh cạn tài nguyên |
| Circuit Breaker riêng | Ngăn tiếp tục gọi một nguồn thay thế đang lỗi |
| Retry có giới hạn | Chỉ thử lại lỗi tạm thời khi thao tác an toàn và còn ngân sách thời gian |

Không nên tự động retry cùng dịch vụ chính trong fallback. Khi Circuit Breaker OPEN, mục tiêu là ngừng gửi request đến dịch vụ đó. Nếu cần retry cho một nguồn thay thế, số lần thử phải nhỏ, có backoff và jitter, chỉ áp dụng với thao tác idempotent và phải nằm trong tổng thời gian phản hồi cho phép.

Timeout của fallback nên ngắn hơn hoặc được tính trong ngân sách thời gian tổng thể của request. Nếu API có SLA 1 giây mà fallback chờ nguồn thay thế 5 giây, fallback không giúp cải thiện trải nghiệm. Bulkhead giúp giới hạn mức tiêu thụ tài nguyên nhưng không thay thế timeout.

## 8. Không tạo vòng lặp qua service hoặc proxy

Lỗi gọi lại phụ thuộc đang lỗi không phải lúc nào cũng xuất hiện trực tiếp trong cùng một phương thức. Một số dạng gián tiếp:

- Fallback gọi một service nội bộ, service đó lại gọi gateway đang có fallback.
- Fallback dùng Feign hoặc WebClient có URL trỏ qua API gateway rồi gateway định tuyến ngược về chính service ban đầu.
- Nguồn dự phòng dùng chung một cụm backend hoặc một database đang là nguyên nhân sự cố của nguồn chính.
- Fallback gọi một phương thức được gắn cùng Circuit Breaker và chính phương thức đó kích hoạt fallback lần nữa.
- Retry được đặt bên trong fallback khiến request tiếp tục chạy dù Circuit Breaker chính đã mở.

Khi thiết kế, hãy vẽ đường đi thực tế của request, không chỉ nhìn tên bean hoặc tên client. Tách rõ nguồn dữ liệu chính, nguồn dự phòng, Circuit Breaker tương ứng và điểm kết thúc cuối cùng khi tất cả nguồn đều không khả dụng.

Một quy tắc hữu ích là fallback không gọi lại entry point được bảo vệ của chính nó. Nếu cần dùng nguồn từ xa thay thế, hãy gọi một abstraction khác có timeout và Circuit Breaker riêng; fallback cuối cùng của abstraction đó phải trả lỗi hoặc trạng thái terminal, không quay về nguồn chính.

## 9. Chọn phản hồi fallback đúng ngữ nghĩa

Fallback cần giữ nguyên ý nghĩa nghiệp vụ. Một phản hồi kỹ thuật thành công nhưng chứa dữ liệu giả có thể gây lỗi khó phát hiện hơn một lỗi rõ ràng.

| Tình huống | Phản hồi nên cân nhắc |
| --- | --- |
| Có cache còn trong thời hạn cho phép | Trả dữ liệu cache và đánh dấu thời điểm cập nhật |
| Cache có dữ liệu nhưng đã quá hạn nghiệp vụ | Trả trạng thái unavailable hoặc yêu cầu xác minh lại |
| Không có dữ liệu và không có nguồn thay thế | Trả trạng thái tạm thời không khả dụng |
| Thao tác ghi như thanh toán không xác định kết quả | Trả trạng thái pending/unknown và dùng cơ chế đối soát; không báo thành công giả |
| Lỗi nghiệp vụ như tài nguyên không tồn tại | Chuyển tiếp lỗi nghiệp vụ thay vì thay bằng dữ liệu dự phòng |

Với thao tác ghi, cần đặc biệt cẩn thận. Nếu request thanh toán timeout, không thể kết luận giao dịch đã thất bại; hệ thống thanh toán có thể đã xử lý nhưng phản hồi bị mất. Fallback nên trả trạng thái chưa xác định và dựa vào idempotency key hoặc quy trình đối soát để xác định kết quả. Không gửi lại lệnh ghi một cách mù quáng từ fallback.

## 10. Theo dõi fallback để phát hiện sự cố

Một API vẫn trả HTTP 200 không có nghĩa dịch vụ phụ thuộc đang khỏe. Nếu fallback thường xuyên trả dữ liệu cache, hệ thống có thể che giấu sự cố phía sau.

Nên theo dõi:

- Số lần lời gọi chính thất bại và số lần bị Circuit Breaker từ chối.
- Số lần fallback được gọi theo từng instance và loại nguyên nhân.
- Tỷ lệ cache hit, cache miss và tuổi trung bình của dữ liệu dự phòng.
- Số lần nguồn thay thế được gọi và tỷ lệ thất bại của nguồn đó.
- Độ trễ fallback, số timeout và số lần fallback tự thất bại.
- Tỷ lệ phản hồi degraded/unavailable so với tổng request.

Log nên chứa tên phụ thuộc, tên Circuit Breaker, loại exception và định danh trace. Không ghi token, dữ liệu cá nhân hoặc toàn bộ body lỗi nếu không cần thiết. Metrics cần phân biệt lỗi của nguồn chính với lỗi của nguồn fallback để nhóm vận hành xác định đúng điểm nghẽn.

## 11. Kiểm tra fallback không gọi lại hệ thống chính

Có thể kiểm tra bằng test đơn vị hoặc kiểm thử tích hợp với client giả. Ngoài việc xác nhận kết quả trả về, cần xác nhận số lần gọi đến phụ thuộc chính.

| Kịch bản | Kết quả mong đợi | Điều cần xác minh |
| --- | --- | --- |
| Lời gọi chính thành công | Trả kết quả chính | Fallback không được gọi |
| Lời gọi chính thất bại, cache có dữ liệu | Trả dữ liệu cache được đánh dấu cũ | Client chính chỉ được gọi một lần; cache được đọc |
| Lời gọi chính thất bại, cache trống | Trả unavailable | Không phát sinh request thứ hai đến dịch vụ chính |
| Circuit Breaker OPEN | Fallback được chạy khi lời gọi bị từ chối | Client chính không được gọi trong request đó |
| Nguồn thay thế thất bại | Trả trạng thái terminal hoặc lỗi phù hợp | Không có đường gọi quay lại nguồn chính |
| Fallback tự thất bại | Lỗi fallback được chuyển lên tầng gọi và được ghi nhận | Không lặp fallback vô hạn |

Một kiểm thử quan trọng là cấu hình client chính trả lỗi, sau đó xác minh số lần gọi client vẫn bằng một sau khi fallback hoàn tất. Với trạng thái OPEN, xác minh số lần gọi client chính bằng không cho request bị từ chối.

## 12. Quy trình thiết kế fallback an toàn

Khi thêm fallback cho một phụ thuộc, hãy thực hiện theo trình tự:

1. Xác định nguyên nhân nào kích hoạt fallback: exception HTTP, timeout, lỗi kết nối hay Circuit Breaker OPEN.
2. Liệt kê các nguồn dữ liệu dự phòng và xác minh chúng độc lập với miền lỗi của dịch vụ chính.
3. Chọn phản hồi có ý nghĩa nghiệp vụ: dữ liệu cache có đánh dấu cũ, trạng thái pending hoặc unavailable.
4. Viết fallback sao cho không gọi lại client chính, entry point được bảo vệ hoặc một service định tuyến ngược về chính phụ thuộc đó.
5. Nếu cần nguồn thay thế từ xa, bảo vệ nguồn đó bằng timeout, bulkhead và Circuit Breaker riêng; đặt fallback cuối cùng có điểm dừng.
6. Kiểm tra cả trường hợp cache trống, nguồn thay thế lỗi, Circuit Breaker OPEN và fallback tự phát sinh exception.
7. Theo dõi số lần fallback, độ trễ, cache hit/miss và tỷ lệ phản hồi degraded.

Fallback an toàn tạo ra một đường phục hồi có giới hạn và có điểm kết thúc rõ ràng. Khi nó dùng nguồn độc lập hoặc trả trạng thái suy giảm trung thực, Circuit Breaker mới thực sự giúp giảm tải cho dịch vụ đang lỗi và hạn chế sự cố lan sang các phần khác của hệ thống Spring Cloud.
