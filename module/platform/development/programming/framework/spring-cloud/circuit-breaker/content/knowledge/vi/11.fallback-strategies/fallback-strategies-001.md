# Fallback là gì và những tình huống phù hợp

## Fallback trong hệ thống dùng Circuit Breaker

Fallback là cách ứng dụng tạo ra một kết quả thay thế khi lời gọi đến dịch vụ phụ thuộc không thể hoàn tất như mong đợi. Trong Spring Cloud Circuit Breaker, một lời gọi có thể thất bại vì lỗi kết nối, timeout, phản hồi lỗi từ server hoặc vì Circuit Breaker đang `OPEN` và từ chối lời gọi mới. Thay vì để mọi lỗi đó làm hỏng toàn bộ luồng nghiệp vụ, ứng dụng có thể trả về dữ liệu dự phòng hoặc một trạng thái suy giảm đã được thiết kế trước.

Fallback không làm cho dịch vụ phụ thuộc hoạt động trở lại. Nó chỉ quyết định ứng dụng phản hồi thế nào trong lúc kết quả chính không có sẵn. Vì vậy, fallback cần giữ đúng ý nghĩa nghiệp vụ: nếu dữ liệu chỉ là ước lượng hoặc đã cũ, caller phải nhận biết được điều đó; nếu thao tác chưa được thực hiện, ứng dụng không được báo thành công như thể dữ liệu đã được ghi.

Trong Spring Cloud Circuit Breaker, API `run` cho phép truyền một supplier thực hiện lời gọi chính và một hàm fallback nhận nguyên nhân lỗi:

```java
return circuitBreakerFactory.create("catalog").run(
    () -> catalogClient.find(productId),
    error -> fallbackCatalog(productId, error)
);
```

Supplier là đường xử lý chính. Fallback được gọi khi supplier kết thúc bằng lỗi mà integration chuyển đến fallback handler, bao gồm trường hợp Circuit Breaker từ chối lời gọi khi đang mở. Hành vi cụ thể và kiểu lỗi truyền vào cần được xác nhận theo provider và phiên bản Spring Cloud Circuit Breaker đang sử dụng.

## Fallback phù hợp khi nào?

Fallback hữu ích khi nghiệp vụ có thể tiếp tục với một kết quả thay thế an toàn và có ý nghĩa. Một số tình huống thường gặp:

| Tình huống | Fallback phù hợp | Điều kiện cần giữ |
| --- | --- | --- |
| Trang sản phẩm không lấy được dữ liệu tồn kho trực tiếp | Hiển thị trạng thái tồn kho chưa xác định hoặc dữ liệu cache còn trong giới hạn tuổi cho phép. | Không biến dữ liệu cũ thành cam kết tồn kho hiện tại. |
| Dịch vụ gợi ý sản phẩm tạm thời không khả dụng | Trả danh sách gợi ý phổ biến đã chuẩn bị trước hoặc bỏ qua khu vực gợi ý. | Phần gợi ý là tùy chọn, không ảnh hưởng giá hoặc quyền mua. |
| Dịch vụ hồ sơ phụ trợ bị lỗi | Dùng một phần dữ liệu hồ sơ đã cache hoặc ẩn phần thông tin phụ. | Không hiển thị dữ liệu thuộc người dùng khác hoặc dữ liệu quá hạn. |
| Dịch vụ tính năng không bắt buộc bị chậm | Tắt tạm tính năng phụ và tiếp tục luồng chính. | Người dùng được thông báo nếu trải nghiệm bị giới hạn đáng kể. |
| Dịch vụ ghi nhận sự kiện không thiết yếu gặp sự cố | Đưa sự kiện vào hàng đợi bền vững để gửi lại sau. | Chỉ xác nhận đã nhận nếu sự kiện thực sự được lưu bền vững và có cơ chế chống trùng lặp. |

Một phép thử hữu ích là hỏi: “Nếu kết quả chính không có, có một kết quả thay thế nào vẫn đúng và không khiến người dùng đưa ra quyết định sai không?” Nếu câu trả lời là có, fallback có thể phù hợp. Nếu mọi kết quả thay thế đều gây hiểu nhầm hoặc làm sai dữ liệu, nên trả lỗi rõ ràng để caller xử lý.

## Các chiến lược fallback phổ biến

### Dữ liệu cache hoặc dữ liệu gần nhất

Cache phù hợp với dữ liệu ít thay đổi hoặc chấp nhận được độ trễ cập nhật. Khi dịch vụ chính không phản hồi, ứng dụng đọc bản sao gần nhất và kèm thông tin thời điểm cập nhật. Nên đặt giới hạn tuổi tối đa (*maximum staleness*). Nếu cache quá cũ, fallback phải chuyển sang trạng thái không xác định hoặc trả lỗi thay vì tiếp tục dùng dữ liệu không còn đáng tin.

Ví dụ, trang thông tin sản phẩm có thể hiển thị mô tả và ảnh từ cache, nhưng không nên dùng tồn kho cũ để khẳng định sản phẩm chắc chắn còn hàng. Dữ liệu quan trọng cho giao dịch như giá cuối cùng, số dư hoặc quyền truy cập thường cần nguồn xác thực và chính sách chặt hơn.

### Giá trị mặc định có ý nghĩa

Một giá trị mặc định chỉ phù hợp khi nó là một trạng thái hợp lệ theo nghiệp vụ. Ví dụ, nếu dịch vụ gợi ý không khả dụng, trả danh sách rỗng có thể chấp nhận được vì gợi ý là tùy chọn. Nhưng trả số dư tài khoản bằng 0 khi dịch vụ số dư gặp lỗi là nguy hiểm: người dùng có thể hiểu đó là số dư thật.

Nên dùng kiểu kết quả thể hiện trạng thái thay thế, ví dụ `AVAILABLE`, `STALE`, `UNKNOWN` hoặc `DEGRADED`, thay vì lạm dụng `null`, chuỗi rỗng hoặc số 0. Kiểu kết quả rõ nghĩa giúp tầng giao diện và tầng nghiệp vụ quyết định cách hiển thị phù hợp.

### Giảm cấp chức năng

Ứng dụng có thể bỏ qua một chức năng không thiết yếu để giữ phần cốt lõi hoạt động. Ví dụ, trang thanh toán vẫn hiển thị giỏ hàng và phương thức thanh toán khi dịch vụ phân tích hành vi không khả dụng. Không nên để dịch vụ phân tích tùy chọn làm hỏng giao dịch chính.

Giảm cấp cần có ranh giới rõ: xác định tính năng nào có thể tắt, dữ liệu nào không còn được cung cấp và thao tác nào vẫn phải bị từ chối. Không được bỏ qua kiểm tra bảo mật, quyền truy cập, hạn mức hoặc quy tắc bắt buộc chỉ để tạo cảm giác hệ thống vẫn hoạt động.

### Chuyển sang nguồn dữ liệu thay thế

Một nguồn dự phòng có thể phục vụ cùng thông tin, chẳng hạn đọc bản sao chỉ đọc hoặc gọi một nhà cung cấp thứ hai. Chiến lược này chỉ có ích nếu nguồn thay thế độc lập đủ mức cần thiết. Nếu cả hai nguồn dùng chung database, DNS, gateway hoặc vùng lỗi, fallback có thể thất bại cùng lúc với đường chính.

Giới hạn timeout và số lần thử của nguồn dự phòng. Nếu fallback gọi lại đúng dịch vụ đang lỗi hoặc gọi qua một chuỗi phụ thuộc dài, nó có thể làm tăng tải và tạo vòng lặp lỗi. Nguồn dự phòng cũng cần có quy tắc xác định độ mới, tính nhất quán và nguồn dữ liệu được ưu tiên khi cả hai cùng có kết quả.

### Lưu yêu cầu để xử lý sau

Với một số thao tác ghi không cần hoàn tất tức thời, ứng dụng có thể lưu yêu cầu vào hàng đợi bền vững rồi xử lý sau. Ví dụ, gửi thông báo hoặc đồng bộ một sự kiện có thể được trì hoãn. Khi dùng cách này, phản hồi nên nói rõ yêu cầu đã được tiếp nhận để xử lý sau, không khẳng định thao tác cuối cùng đã hoàn tất.

Hàng đợi cần có xác nhận lưu bền vững, mã định danh, khả năng chống xử lý trùng, chính sách retry có giới hạn và nơi theo dõi thông điệp thất bại. Nếu không ghi được vào hàng đợi, fallback cũng thất bại và ứng dụng phải trả lỗi phù hợp.

## Ví dụ: cache fallback cho dịch vụ danh mục

Giả sử trang sản phẩm cần thông tin mô tả từ dịch vụ danh mục. Ứng dụng có cache bản mô tả gần nhất và chấp nhận dữ liệu cũ tối đa 15 phút. Khi dịch vụ chính lỗi, ứng dụng dùng cache nếu bản ghi còn trong giới hạn đó; nếu không, trả trạng thái chưa xác định.

```java
@Service
public class ProductViewService {
    private final CatalogClient catalogClient;
    private final ProductCache productCache;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductViewService(
            CatalogClient catalogClient,
            ProductCache productCache,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductView find(String productId) {
        return circuitBreakerFactory.create("catalog").run(
            () -> {
                ProductDetails details = catalogClient.find(productId);
                productCache.put(productId, details, Instant.now());
                return ProductView.current(details);
            },
            error -> productCache.find(productId)
                .filter(entry -> entry.cachedAt().isAfter(
                    Instant.now().minus(Duration.ofMinutes(15))))
                .map(entry -> ProductView.stale(entry.details(), entry.cachedAt()))
                .orElseGet(() -> ProductView.unavailable(productId))
        );
    }
}
```

`ProductCache`, `ProductDetails` và `ProductView` là các kiểu do ứng dụng định nghĩa. `ProductView.stale` cần giúp tầng hiển thị biết dữ liệu lấy từ cache và thời điểm cập nhật; `ProductView.unavailable` biểu thị chưa có thông tin. Ví dụ tập trung vào lựa chọn fallback, nên cache cần được thiết kế thread-safe và có giới hạn dung lượng, chính sách hết hạn riêng.

Trong một hệ thống thực tế, cần cân nhắc việc ghi cache chỉ sau khi xác nhận response hợp lệ, tránh lưu kết quả lỗi hoặc dữ liệu không đầy đủ. Không nên cache các trường nhạy cảm nếu chưa có chính sách bảo vệ và phân vùng dữ liệu phù hợp.

## Fallback với Resilience4j annotation

Nếu ứng dụng dùng annotation của Resilience4j, có thể khai báo tên phương thức fallback trên `@CircuitBreaker`:

```java
@Service
public class RecommendationService {

    @CircuitBreaker(name = "recommendations", fallbackMethod = "fallback")
    public List<Product> recommend(String customerId) {
        return recommendationClient.fetch(customerId);
    }

    private List<Product> fallback(String customerId, Throwable cause) {
        log.warn("Recommendations unavailable for customerId={}", customerId, cause);
        return popularProducts.forDisplay();
    }
}
```

Phương thức fallback phải có kiểu trả về tương thích với phương thức gốc, nhận cùng các tham số nghiệp vụ và có thể nhận thêm một tham số ngoại lệ ở cuối. Có thể dùng kiểu ngoại lệ cụ thể thay cho `Throwable` nếu muốn xử lý riêng từng nhóm lỗi. Khi có nhiều fallback overload, hãy bảo đảm chữ ký không mơ hồ và tương thích với phiên bản Resilience4j.

Annotation hoạt động qua Spring AOP. Lời gọi cần đi qua Spring proxy; gọi nội bộ `this.recommend(...)` trong cùng bean có thể bỏ qua interceptor. Nếu fallback không được gọi, hãy kiểm tra cách bean được tạo, đường gọi qua proxy và chữ ký phương thức fallback.

## Fallback cho lời gọi reactive

Với Reactor, fallback cần trả về một publisher thay vì chặn luồng để lấy giá trị. Ví dụ:

```java
public Mono<ProductView> find(String productId) {
    Mono<ProductDetails> primary = catalogClient.findReactive(productId);

    return reactiveCircuitBreakerFactory.create("catalog")
        .run(
            primary.map(ProductView::current),
            error -> productCache.findReactive(productId)
                .map(entry -> ProductView.stale(entry.details(), entry.cachedAt()))
                .defaultIfEmpty(ProductView.unavailable(productId))
        );
}
```

`reactiveCircuitBreakerFactory` là `ReactiveCircuitBreakerFactory` được Spring inject; các phương thức `findReactive` của client và cache là API giả định trả về `Mono`. Fallback cũng trả `Mono<ProductView>`, nên toàn bộ pipeline tiếp tục non-blocking. Tránh gọi `block()` bên trong fallback hoặc dùng một lời gọi đồng bộ có thể chặn event-loop.

## Khi nào không nên dùng fallback?

Fallback không phù hợp nếu kết quả thay thế có thể làm sai quyết định của người dùng hoặc vi phạm quy tắc bắt buộc. Một số ví dụ:

- Không trả số dư mặc định bằng 0 khi không truy vấn được tài khoản.
- Không bỏ qua xác thực hoặc phân quyền khi dịch vụ kiểm tra quyền không khả dụng.
- Không xác nhận thanh toán, đặt hàng hoặc cập nhật dữ liệu đã thành công nếu dịch vụ đích chưa xác nhận.
- Không trả dữ liệu cache quá hạn cho thông tin có yêu cầu nhất quán chặt như giá giao dịch hoặc trạng thái quyền truy cập.
- Không chuyển mọi ngoại lệ lập trình, lỗi null hoặc lỗi cấu hình thành một kết quả mặc định chung. Những lỗi đó cần được phát hiện và sửa.

Với thao tác ghi, nếu có thể lưu yêu cầu để xử lý sau, hãy trả trạng thái tiếp nhận rõ ràng và cung cấp mã theo dõi. Nếu không có cơ chế lưu bền vững, trả lỗi để caller biết thao tác chưa được xác nhận.

## Thiết kế fallback để không tạo lỗi dây chuyền

Fallback cũng tiêu thụ tài nguyên và có thể thất bại. Một số nguyên tắc giúp tránh biến fallback thành nguồn lỗi mới:

1. **Không gọi lại cùng dịch vụ đang lỗi:** fallback nên dùng cache, dữ liệu tĩnh, một nguồn độc lập hoặc trả trạng thái suy giảm.
2. **Đặt timeout cho nguồn dự phòng:** không để fallback chờ vô hạn và giữ thread của request chính.
3. **Giới hạn chi phí:** tránh truy vấn nặng, tạo thread pool mới hoặc gọi nhiều dịch vụ khác trong fallback.
4. **Giữ ngữ nghĩa kết quả:** đánh dấu dữ liệu cũ, chưa xác định hoặc đang chờ xử lý.
5. **Giới hạn retry:** nếu fallback gửi vào queue hoặc gọi nguồn thay thế, phải có retry/backoff và cơ chế chống trùng.
6. **Ghi nhận nguyên nhân:** lưu loại lỗi và ID dịch vụ phụ thuộc để vận hành có thể phân biệt Circuit Breaker mở, timeout, lỗi server và lỗi fallback.

Fallback thường không nên mở thêm một chuỗi Circuit Breaker lồng nhau nếu không có thiết kế rõ ràng. Nhiều lớp fallback có thể che mất nguyên nhân đầu tiên và làm khó việc xác định đường đi của request. Nếu phải gọi nguồn thay thế, hãy đặt chính sách riêng và theo dõi nó như một dependency độc lập.

## Quan sát và kiểm thử fallback

Không chỉ kiểm tra rằng người dùng nhận được response. Cần biết fallback xảy ra bao nhiêu lần, vì nguyên nhân gì, dữ liệu thay thế cũ đến mức nào và fallback có tự thất bại hay không.

Các metric hữu ích gồm:

- Số lần fallback theo tên Circuit Breaker và loại lỗi.
- Tỷ lệ lời gọi chính thành công, thất bại, chậm và bị từ chối.
- Tỷ lệ fallback lấy được cache hợp lệ so với không có dữ liệu.
- Tuổi trung bình và tuổi lớn nhất của dữ liệu cache được sử dụng.
- Số yêu cầu được đưa vào hàng đợi chờ xử lý và số yêu cầu xử lý thất bại.
- Latency tổng của request khi đi qua fallback.

Nên kiểm thử ít nhất các tình huống sau:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Dịch vụ chính thành công | Trả kết quả chính và cập nhật cache nếu phù hợp. |
| Dịch vụ chính timeout, cache còn mới | Trả dữ liệu cache với dấu hiệu dữ liệu cũ và thời điểm cập nhật. |
| Dịch vụ chính lỗi, cache quá hạn | Trả trạng thái unavailable hoặc lỗi rõ nghĩa. |
| Circuit Breaker đang `OPEN` | Lời gọi chính bị từ chối nhanh và fallback xử lý theo chính sách. |
| Fallback cũng lỗi | Lỗi được truyền hoặc ánh xạ rõ ràng; không tạo vòng gọi vô hạn. |
| Request không hợp lệ | Validation từ chối request; không dùng fallback để che lỗi đầu vào. |
| Dịch vụ phục hồi | Lời gọi chính thành công trở lại và dữ liệu cache được cập nhật. |

Trong kiểm thử, nên quan sát cả response cuối cùng và metrics của Circuit Breaker. Một fallback trả HTTP 200 không có nghĩa lời gọi phụ thuộc đã thành công; nếu chỉ theo dõi status cuối cùng, hệ thống có thể che giấu một dependency đang liên tục lỗi.

## Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| Fallback sửa lỗi của dịch vụ phụ thuộc. | Fallback chỉ cung cấp phản hồi thay thế trong lúc đường chính lỗi. |
| Có thể dùng một giá trị mặc định cho mọi lỗi. | Giá trị thay thế phải đúng ngữ nghĩa và mức độ nhất quán của nghiệp vụ. |
| Fallback luôn được gọi cho mọi exception trong ứng dụng. | Nó chỉ áp dụng cho lời gọi được bọc và các lỗi được integration chuyển đến fallback handler. |
| Bỏ qua exception trong thống kê đồng nghĩa không cần fallback. | Phân loại thống kê và xử lý lỗi cho caller là hai quyết định riêng. |
| Cache nào cũng có thể dùng làm fallback. | Cache phải đúng phạm vi dữ liệu, được bảo vệ và chưa quá giới hạn tuổi cho phép. |
| Fallback trả HTTP 200 nghĩa là dependency khỏe. | Cần theo dõi riêng kết quả đường chính và số lần fallback. |

Fallback phù hợp khi ứng dụng có một cách phản hồi thay thế an toàn, có giới hạn và có thể giải thích được. Kết hợp fallback với Circuit Breaker giúp phần chức năng còn hoạt động tiếp tục phục vụ trong lúc dependency suy giảm, đồng thời giữ cho người dùng và hệ thống phía sau hiểu đúng trạng thái dữ liệu hoặc thao tác.
