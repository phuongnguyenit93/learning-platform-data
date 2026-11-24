# Kết hợp một nguồn chính với dữ liệu từ nguồn phụ

## Bổ sung dữ liệu mà vẫn giữ vai trò của nguồn chính

Trong một ứng dụng reactive, nguồn chính thường mang đối tượng hoặc sự kiện mà nghiệp vụ đang xử lý. Nguồn phụ cung cấp thông tin bổ sung để hoàn thiện kết quả: đơn hàng cần thông tin khách hàng, giao dịch cần tỷ giá, sự kiện cần cấu hình hiện tại, hoặc bài viết cần thông tin tác giả.

Khi kết hợp hai nguồn, cần xác định rõ vai trò của từng nguồn:

- **Nguồn chính (primary source)** quyết định đối tượng nào đang được xử lý, số lượng kết quả dự kiến và thường quyết định thứ tự nghiệp vụ.
- **Nguồn phụ (secondary source)** cung cấp dữ liệu để làm giàu (enrich) đối tượng chính, bổ sung thuộc tính hoặc hỗ trợ quyết định xử lý.
- **Toán tử kết hợp** xác định cách ghép dữ liệu, thời điểm đăng ký nguồn phụ, hành vi khi nguồn phụ rỗng hoặc lỗi, và mức độ xử lý đồng thời.

Trong Project Reactor, `Mono<T>` biểu diễn một kết quả có thể rỗng hoặc có tối đa một phần tử; `Flux<T>` biểu diễn một luồng có thể phát không, một hoặc nhiều phần tử. Có thể kết hợp chúng bằng `zip`, `zipWhen`, `flatMap`, `concatMap`, `flatMapSequential` hoặc `combineLatest`, tùy quan hệ giữa hai nguồn.

Các đoạn mã dùng `record` để rút gọn mô hình dữ liệu; `record` có từ Java 16. Trong dự án dùng phiên bản Java cũ hơn, có thể thay bằng các lớp thông thường có constructor và accessor tương ứng.

Ví dụ, một luồng đơn hàng là nguồn chính, còn dịch vụ khách hàng cung cấp tên và hạng thành viên để bổ sung vào từng đơn hàng. Mục tiêu là tạo ra `EnrichedOrder` mà vẫn xử lý được trường hợp khách hàng không tồn tại, dịch vụ phụ gặp lỗi hoặc nhiều đơn hàng được xử lý đồng thời.

## Chọn toán tử theo quan hệ giữa hai nguồn

Không có một toán tử kết hợp phù hợp cho mọi tình huống. Hãy bắt đầu bằng câu hỏi: nguồn phụ có phụ thuộc vào giá trị nguồn chính không, có một giá trị dùng chung hay một giá trị riêng cho từng phần tử, và có cần giữ thứ tự không?

| Quan hệ dữ liệu | Toán tử thường phù hợp | Hành vi chính |
|---|---|---|
| Một `Mono` chính và một `Mono` phụ độc lập | `Mono.zip` | Chờ cả hai có giá trị rồi ghép thành một kết quả |
| Một `Mono` chính quyết định tham số truy vấn phụ | `zipWhen` hoặc `flatMap` | Nhận giá trị chính rồi tạo publisher phụ thuộc vào giá trị đó |
| Nhiều phần tử chính, mỗi phần tử cần một truy vấn phụ riêng | `flatMap` | Thực hiện nhiều truy vấn phụ đồng thời và hợp nhất kết quả |
| Nhiều phần tử chính, cần giữ thứ tự đầu vào | `flatMapSequential` hoặc `concatMap` | Kết hợp publisher phụ nhưng giữ thứ tự phát kết quả |
| Nhiều phần tử chính dùng chung một dữ liệu phụ | `Mono.cache()` kết hợp `flatMap` | Chia sẻ kết quả phụ giữa các phần tử trong phạm vi cache |
| Nguồn phụ liên tục cập nhật và cần kết hợp giá trị mới nhất | `combineLatest` | Tạo tổ hợp mới khi một trong các nguồn phát sau khi tất cả đã có giá trị |

`merge` có mục đích khác: nó trộn các tín hiệu của nhiều nguồn thành một luồng, không ghép từng phần tử chính với dữ liệu phụ. `zip` ghép theo vị trí phát, không tự tìm bản ghi có cùng khóa nghiệp vụ. Cần chọn đúng ngữ nghĩa trước khi viết pipeline.

## Ghép hai kết quả đơn bằng Mono.zip

Khi hai nguồn độc lập đều trả về một kết quả đơn, `Mono.zip` là lựa chọn trực tiếp. Publisher chỉ phát kết quả kết hợp khi cả hai nguồn đã phát giá trị:

```java
import reactor.core.publisher.Mono;

record Product(String id, String name) {}
record Inventory(String productId, int available) {}
record ProductView(Product product, int available) {}

Mono<ProductView> loadProductView(String productId) {
    Mono<Product> product = productClient.findById(productId);
    Mono<Inventory> inventory = inventoryClient.findByProductId(productId);

    return Mono.zip(product, inventory,
        (p, stock) -> new ProductView(p, stock.available()));
}
```

Hai lời gọi được đăng ký khi `loadProductView` được subscribe. Khi cả hai `Mono` phát giá trị, hàm kết hợp tạo `ProductView`. Lỗi từ một nguồn truyền xuống và kết thúc phép ghép; Reactor sẽ hủy nguồn còn lại khi không còn cần kết quả của nó.

Điểm cần chú ý là `Mono.zip` cần mỗi nguồn phát ít nhất một giá trị. Nếu một nguồn hoàn tất rỗng, phép zip cũng có thể hoàn tất rỗng mà không tạo `ProductView`. Điều này có thể đúng nếu cả hai dữ liệu đều bắt buộc, nhưng không phù hợp nếu tồn kho hoặc thông tin phụ là tùy chọn.

Với dữ liệu phụ tùy chọn, chuyển trạng thái rỗng thành một giá trị mặc định hoặc một kiểu biểu diễn rõ ràng:

```java
import reactor.core.publisher.Mono;

Mono<Inventory> inventory = inventoryClient.findByProductId(productId)
    .defaultIfEmpty(new Inventory(productId, 0));

return Mono.zip(productClient.findById(productId), inventory,
    (product, stock) -> new ProductView(product, stock.available()));
```

Giá trị mặc định phải phù hợp với ý nghĩa nghiệp vụ. Nếu “không tìm thấy dữ liệu tồn kho” khác với “tồn kho bằng không”, hãy giữ sự khác biệt bằng `Optional`, một kiểu kết quả riêng hoặc nhánh xử lý `switchIfEmpty`, thay vì gán một con số có thể gây hiểu nhầm.

## Tạo nguồn phụ từ kết quả chính bằng zipWhen

Khi nguồn phụ cần giá trị từ nguồn chính để thực hiện truy vấn, `zipWhen` thể hiện rõ quan hệ phụ thuộc. Nó nhận một giá trị từ `Mono` chính, dùng giá trị đó tạo `Mono` phụ, rồi ghép hai kết quả:

```java
import reactor.core.publisher.Mono;

record Order(String id, String customerId, long total) {}
record Customer(String id, String displayName) {}
record OrderSummary(Order order, Customer customer) {}

Mono<OrderSummary> loadSummary(String orderId) {
    return orderClient.findById(orderId)
        .zipWhen(order -> customerClient.findById(order.customerId()),
            (order, customer) -> new OrderSummary(order, customer));
}
```

Trình tự ở đây là: tải đơn hàng trước, lấy `customerId` từ đơn hàng, rồi mới gọi dịch vụ khách hàng. Hai nguồn không cần được khởi chạy độc lập từ đầu vì nguồn phụ phụ thuộc dữ liệu của nguồn chính.

`zipWhen` phù hợp khi mỗi nguồn chỉ tạo tối đa một giá trị và cần giữ cả giá trị ban đầu lẫn kết quả phụ. Nếu publisher phụ hoàn tất rỗng, kết quả `zipWhen` cũng có thể rỗng. Có thể đặt `defaultIfEmpty` hoặc `switchIfEmpty` bên trong hàm tạo nguồn phụ nếu nghiệp vụ cho phép thiếu dữ liệu khách hàng.

Một cách viết tương đương về ý tưởng là `flatMap` rồi ánh xạ kết quả phụ về cùng đối tượng chính:

```java
Mono<OrderSummary> summary = orderClient.findById(orderId)
    .flatMap(order -> customerClient.findById(order.customerId())
        .map(customer -> new OrderSummary(order, customer)));
```

`flatMap` linh hoạt hơn khi cần xử lý nhiều nhánh, nhưng `zipWhen` diễn đạt trực tiếp ý định “lấy kết quả chính rồi ghép với một nguồn phụ được tạo từ kết quả đó”.

## Làm giàu từng phần tử của Flux bằng flatMap

Với một luồng nhiều phần tử chính, mỗi phần tử có thể cần một truy vấn phụ riêng. `flatMap` là lựa chọn phổ biến vì nó đăng ký publisher phụ cho từng phần tử và cho phép nhiều publisher phụ chạy đồng thời:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record OrderLine(String orderId, String customerId, long amount) {}
record CustomerInfo(String customerId, String name, String tier) {}
record EnrichedOrder(OrderLine order, CustomerInfo customer) {}

Flux<EnrichedOrder> enrichOrders(Flux<OrderLine> orders) {
    return orders.flatMap(order ->
        customerClient.findById(order.customerId())
            .map(customer -> new EnrichedOrder(order, customer))
    );
}
```

Mỗi `OrderLine` tạo một lời gọi phụ đến `customerClient`. Nếu đơn hàng A được phát trước đơn hàng B nhưng truy vấn khách hàng của B hoàn tất sớm hơn, kết quả của B có thể được phát trước A. `flatMap` ưu tiên khả năng xử lý đồng thời và thông lượng; nó không bảo đảm thứ tự kết quả giống thứ tự nguồn.

Điều này thường chấp nhận được khi các đơn hàng độc lập và bên tiêu thụ không yêu cầu thứ tự. Nếu cần giữ thứ tự, có thể dùng `flatMapSequential` hoặc `concatMap`.

### Giữ thứ tự với flatMapSequential

`flatMapSequential` cho phép đăng ký nhiều publisher phụ đồng thời nhưng phát kết quả theo thứ tự các phần tử nguồn. Nếu publisher phụ của phần tử sau hoàn tất trước, kết quả có thể được giữ tạm trong bộ đệm cho đến khi các publisher phụ đứng trước phát xong:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<EnrichedOrder> ordered = orders.flatMapSequential(
    order -> customerClient.findById(order.customerId())
        .map(customer -> new EnrichedOrder(order, customer)),
    8,
    1
);
```

Tham số thứ hai giới hạn số publisher phụ được đăng ký đồng thời; tham số thứ ba là prefetch cho mỗi publisher phụ. Cần lưu ý rằng giữ thứ tự có thể làm tăng bộ nhớ đệm và độ trễ: một publisher phụ chậm ở đầu luồng có thể giữ các kết quả đã hoàn tất của những phần tử phía sau.

### Xử lý tuần tự với concatMap

Nếu nghiệp vụ yêu cầu mỗi truy vấn phụ phải hoàn tất trước khi bắt đầu truy vấn tiếp theo, dùng `concatMap`:

```java
import reactor.core.publisher.Flux;

Flux<EnrichedOrder> orderedSequentially = orders.concatMap(
    order -> customerClient.findById(order.customerId())
        .map(customer -> new EnrichedOrder(order, customer))
);
```

`concatMap` giữ thứ tự và chỉ đăng ký publisher phụ tiếp theo sau khi publisher phụ hiện tại kết thúc. Cách này đơn giản và dễ dự đoán, nhưng giảm concurrency. Hãy chọn nó khi các thao tác phụ phụ thuộc thứ tự hoặc hệ thống đích có giới hạn nghiêm ngặt về số request đồng thời.

| Toán tử | Đăng ký publisher phụ | Thứ tự đầu ra | Đánh đổi chính |
|---|---|---|---|
| `flatMap` | Có thể đồng thời | Theo thời điểm hoàn tất | Thông lượng cao, thứ tự không đảm bảo |
| `flatMapSequential` | Có thể đồng thời | Theo thứ tự nguồn | Có thể phải đệm kết quả phía sau |
| `concatMap` | Tuần tự | Theo thứ tự nguồn | Dễ kiểm soát nhưng ít concurrency |

## Dùng chung một nguồn phụ cho nhiều phần tử chính

Một tình huống thường gặp là mọi phần tử chính đều cần cùng một dữ liệu phụ, ví dụ cấu hình, tỷ giá hoặc chính sách đang áp dụng cho toàn bộ lô dữ liệu. Nếu tạo một subscription đến publisher cold cho mỗi phần tử, dịch vụ phụ có thể bị gọi lặp lại.

```java
import reactor.core.publisher.Mono;

Mono<PricingPolicy> policy = policyClient.loadCurrentPolicy()
    .cache();

Flux<PriceView> prices = products.flatMap(product ->
    policy.map(currentPolicy ->
        new PriceView(product, calculatePrice(product, currentPolicy)))
);
```

`cache()` chia sẻ tín hiệu của `Mono` cho các subscriber của publisher đó. Khi nhiều phần tử sản phẩm cùng subscribe vào `policy`, nguồn phụ được khởi chạy một lần trong vòng đời cache và kết quả được dùng chung. Đây là cách tránh gọi dịch vụ chính sách cho từng sản phẩm.

Cache không nên được đặt tùy tiện ở một publisher sống lâu hơn dữ liệu mà nó đại diện. `Mono.cache()` không TTL giữ lại tín hiệu đã kết thúc, kể cả lỗi hoặc kết quả rỗng. Nếu chính sách thay đổi theo thời gian, hãy đặt TTL phù hợp hoặc tạo publisher cache trong phạm vi một request/lô xử lý:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<PricingPolicy> policy = policyClient.loadCurrentPolicy()
    .cache(Duration.ofSeconds(30));
```

Nếu dữ liệu phụ phụ thuộc tenant, người dùng hoặc quyền truy cập, cache cần được phân vùng theo khóa phù hợp. Không chia sẻ một publisher cache toàn cục nếu các subscriber có thể cần những dữ liệu phụ khác nhau.

Một lựa chọn khác là tải dữ liệu phụ một lần rồi kết hợp cả lô trong `Mono.zip`:

```java
import java.util.List;
import reactor.core.publisher.Mono;

Mono<List<PriceView>> loadPriceViews() {
    Mono<List<Product>> productList = productClient.findAll().collectList();
    Mono<PricingPolicy> policy = policyClient.loadCurrentPolicy();

    return Mono.zip(productList, policy,
        (items, currentPolicy) -> items.stream()
            .map(product -> new PriceView(
                product,
                calculatePrice(product, currentPolicy)))
            .toList());
}
```

Cách này dễ hiểu khi lô sản phẩm hữu hạn và có kích thước vừa phải. Nó thu toàn bộ sản phẩm vào bộ nhớ trước khi tạo kết quả; với luồng lớn hoặc không giới hạn, nên xử lý từng phần tử bằng `flatMap` kết hợp publisher phụ đã cache.

## Nguồn phụ rỗng: giữ hay loại bỏ phần tử chính?

Một `Mono` phụ có thể hoàn tất mà không phát giá trị. Khi dùng `flatMap`, nếu publisher phụ rỗng thì phần tử chính tương ứng thường không tạo ra kết quả downstream. Đây có thể là hành vi đúng nếu dữ liệu phụ bắt buộc, nhưng có thể làm mất bản ghi chính nếu dữ liệu phụ chỉ mang tính tùy chọn.

Ví dụ, nếu không tìm thấy thông tin khách hàng thì vẫn muốn trả về đơn hàng với tên khách hàng mặc định:

```java
Flux<EnrichedOrder> enriched = orders.flatMap(order ->
    customerClient.findById(order.customerId())
        .map(customer -> new EnrichedOrder(order, customer))
        .switchIfEmpty(Mono.just(
            new EnrichedOrder(order, CustomerInfo.unknown(order.customerId()))))
);
```

`switchIfEmpty` ở bên trong nhánh xử lý từng đơn hàng bảo đảm mỗi đơn hàng vẫn tạo một kết quả. Nếu đặt `switchIfEmpty` bên ngoài toàn bộ `Flux`, ý nghĩa sẽ khác: nó chỉ thay thế khi cả publisher ngoài không phát phần tử nào, không phải thay thế riêng từng truy vấn khách hàng rỗng.

Nếu thiếu dữ liệu phụ là lỗi nghiệp vụ, có thể chuyển trạng thái rỗng thành lỗi rõ ràng:

```java
import reactor.core.publisher.Mono;

Mono<CustomerInfo> requiredCustomer(String customerId) {
    return customerClient.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Không tìm thấy khách hàng: " + customerId)));
}
```

Việc lựa chọn giá trị mặc định, bỏ phần tử hay phát lỗi cần xuất phát từ quy tắc nghiệp vụ, không chỉ từ sự tiện lợi của toán tử.

## Nguồn phụ lỗi: cô lập lỗi theo từng phần tử

Nếu một truy vấn phụ lỗi trong `flatMap`, lỗi đó thường kết thúc toàn bộ pipeline và hủy các nhánh còn lại. Khi muốn tiếp tục xử lý các phần tử chính khác, hãy đặt xử lý lỗi trong nhánh của từng phần tử:

```java
Flux<EnrichedOrder> resilient = orders.flatMap(order ->
    customerClient.findById(order.customerId())
        .map(customer -> new EnrichedOrder(order, customer))
        .onErrorResume(CustomerServiceException.class, error -> {
            logCustomerLookupFailure(order.customerId(), error);
            return Mono.just(EnrichedOrder.withUnknownCustomer(order));
        })
);
```

Ở đây, lỗi thuộc loại `CustomerServiceException` được chuyển thành kết quả thay thế cho đơn hàng hiện tại. Các đơn hàng khác vẫn tiếp tục. Lỗi không thuộc loại được xử lý sẽ truyền ra ngoài và có thể kết thúc toàn pipeline.

Vị trí đặt `onErrorResume` rất quan trọng. Nếu đặt sau `flatMap`, một lỗi phụ có thể khiến toàn bộ luồng đơn hàng được thay bằng một publisher dự phòng. Nếu đặt trong nhánh `flatMap`, chỉ nhánh của phần tử tương ứng được phục hồi. Không nên biến mọi lỗi thành dữ liệu mặc định nếu lỗi đó có thể chỉ ra vi phạm hợp đồng, lỗi xác thực hoặc trạng thái hệ thống cần được xử lý ở cấp cao hơn.

## Kết hợp với dữ liệu phụ thay đổi theo thời gian

Đôi khi nguồn phụ không phải một kết quả cố định mà là luồng cập nhật liên tục, chẳng hạn tỷ giá, trạng thái tồn kho hoặc cấu hình thay đổi. `combineLatest` tạo tổ hợp từ giá trị mới nhất của các nguồn sau khi mỗi nguồn đã phát ít nhất một giá trị:

```java
import reactor.core.publisher.Flux;

Flux<DashboardView> dashboard = Flux.combineLatest(
    orderEvents,
    inventoryUpdates,
    (order, inventory) -> new DashboardView(order, inventory)
);
```

Sau khi cả hai nguồn có giá trị đầu tiên, mỗi lần `orderEvents` hoặc `inventoryUpdates` phát phần tử mới, `combineLatest` có thể tạo một `DashboardView` từ giá trị mới và giá trị gần nhất của nguồn còn lại. Vì thế, một cập nhật tồn kho có thể tạo ra kết quả dashboard mới bằng cách kết hợp với đơn hàng gần nhất đã phát.

Đây là ngữ nghĩa phù hợp cho trạng thái tổng hợp hoặc giao diện cần phản ánh giá trị mới nhất từ nhiều luồng. Nó khác với làm giàu từng sự kiện chính bằng một lần tra cứu phụ: `combineLatest` có thể phát thêm kết quả khi nguồn phụ thay đổi, kể cả khi nguồn chính không phát sự kiện mới.

Nếu một nguồn chưa phát giá trị đầu tiên, chưa thể tạo tổ hợp. Nếu một nguồn hoàn tất sau khi đã phát giá trị, giá trị cuối cùng của nó có thể tiếp tục được dùng để kết hợp với các cập nhật từ nguồn còn lại; nếu một nguồn kết thúc mà chưa từng phát giá trị, không có tổ hợp nào để tạo. Cần cân nhắc vòng đời và chính sách hoàn tất của từng nguồn.

## Phân biệt zip, combineLatest và merge

Ba toán tử thường bị nhầm vì đều nhận nhiều nguồn, nhưng ngữ nghĩa khác nhau:

| Toán tử | Cách kết hợp | Khi nào phát kết quả | Trường hợp sử dụng |
|---|---|---|---|
| `zip` | Ghép phần tử theo vị trí: phần tử thứ nhất với thứ nhất, thứ hai với thứ hai | Khi mỗi nguồn có một phần tử tương ứng | Hai luồng có quan hệ vị trí hoặc chỉ số rõ ràng |
| `combineLatest` | Ghép giá trị mới nhất của từng nguồn | Sau khi tất cả nguồn có giá trị đầu tiên, rồi mỗi khi một nguồn cập nhật | Tổng hợp trạng thái mới nhất từ nhiều luồng |
| `merge` | Trộn các tín hiệu từ các nguồn | Khi bất kỳ nguồn nào phát phần tử | Hợp nhất nhiều luồng cùng kiểu dữ liệu, không cần ghép cặp |

Ví dụ `zip` trên hai `Flux` ghép theo thứ tự phát và thường kết thúc khi một nguồn không còn phần tử để tạo cặp. Nó không tự đối chiếu `productId` hay `customerId`. Nếu cần ghép theo khóa, hãy xây dựng logic tra cứu hoặc join phù hợp, không dùng `zip` như thể nó là phép join cơ sở dữ liệu.

`merge` cũng không phải cách làm giàu dữ liệu. Nếu `Flux<Order>` và `Flux<Customer>` được merge, kết quả là một luồng tín hiệu xen kẽ từ hai nguồn (thường cần cùng kiểu phần tử hoặc chuyển về kiểu chung), chứ không phải `Order` được gắn với `Customer` tương ứng.

## Demand, concurrency và cancellation khi kết hợp

Khi subscriber cuối yêu cầu dữ liệu, các toán tử kết hợp phối hợp demand với từng nguồn. `zip` cần dữ liệu từ tất cả nguồn để tạo một cặp; `combineLatest` cần giữ giá trị mới nhất; `flatMap` cần quản lý publisher chính cùng nhiều publisher phụ. Do đó, lượng dữ liệu được yêu cầu upstream có thể khác số kết quả mà subscriber cuối đang chờ.

Với `flatMap`, tham số `concurrency` giới hạn số publisher phụ được đăng ký đồng thời; `prefetch` ảnh hưởng đến lượng dữ liệu được yêu cầu trước từ mỗi publisher phụ. Tăng concurrency có thể cải thiện thông lượng khi nguồn phụ là I/O bất đồng bộ, nhưng cũng làm tăng số request đang hoạt động, tải lên dịch vụ phụ và lượng dữ liệu cần giữ. Hãy bắt đầu bằng giới hạn vừa phải, đo độ trễ và tải, rồi điều chỉnh theo khả năng thực tế của dịch vụ phụ.

Cancellation từ subscriber cuối được truyền ngược qua đồ thị. Khi một pipeline kết thúc hoặc bị hủy, các toán tử kết hợp có thể hủy các subscription nguồn phụ còn hoạt động. Điều này giúp dừng request không còn cần thiết, nhưng hiệu quả cuối cùng phụ thuộc client và adapter có liên kết cancellation với thao tác I/O thực tế hay không.

Không nên gọi `subscribe()` bên trong `flatMap` để khởi động nguồn phụ. Hãy trả publisher phụ trực tiếp từ hàm ánh xạ để Reactor quản lý demand, lỗi và cancellation:

```java
// Nên: publisher phụ là một phần của cùng pipeline.
Flux<Result> results = requests.flatMap(request -> client.fetch(request));

// Tránh: subscription tách rời khỏi pipeline bên ngoài.
// requests.doOnNext(request -> client.fetch(request).subscribe());
```

Khi giữ các nguồn trong cùng một đồ thị, caller có thể quan sát một kết quả thống nhất, xử lý lỗi tại đúng nhánh và hủy toàn bộ công việc khi không còn nhu cầu.

## Quy trình thiết kế phép làm giàu dữ liệu

Khi kết hợp một nguồn chính với dữ liệu phụ, hãy lần lượt xác định:

1. Nguồn chính là `Mono` hay `Flux`, và mỗi phần tử chính cần bao nhiêu dữ liệu phụ.
2. Nguồn phụ độc lập hay được tạo từ giá trị của nguồn chính; nếu độc lập, cân nhắc `zip`, còn nếu phụ thuộc, cân nhắc `zipWhen` hoặc `flatMap`.
3. Dữ liệu phụ được dùng một lần cho cả luồng hay được truy vấn riêng cho từng phần tử; nếu dùng chung, xác định phạm vi và TTL của cache.
4. Nguồn phụ có thể rỗng hoặc lỗi không; quyết định giữ phần tử chính, dùng giá trị thay thế hay kết thúc bằng lỗi.
5. Có cần giữ thứ tự không; chọn `flatMap`, `flatMapSequential` hoặc `concatMap` theo yêu cầu concurrency và thứ tự.
6. Nguồn phụ có cập nhật liên tục không; dùng `combineLatest` khi cần trạng thái mới nhất và chấp nhận kết quả mới khi bất kỳ nguồn nào thay đổi.
7. Đặt giới hạn concurrency, prefetch và timeout phù hợp; kiểm tra cancellation có truyền đến các request phụ.

Trong ứng dụng reactive Java, kết hợp nguồn chính với dữ liệu phụ là một phép ghép có chủ đích về cardinality, thời điểm và vòng đời. Chọn toán tử theo quan hệ dữ liệu giúp giữ đúng ý nghĩa của từng phần tử, tránh gọi dịch vụ phụ lặp lại, xử lý được dữ liệu thiếu hoặc lỗi, và kiểm soát tải khi nhiều phần tử được làm giàu đồng thời.
