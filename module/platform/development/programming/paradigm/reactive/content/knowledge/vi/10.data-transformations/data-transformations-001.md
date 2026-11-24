# Biến đổi từng phần tử và giữ quan hệ một–một

Trong một pipeline reactive, nhiều bước chỉ cần đổi cách biểu diễn của từng phần tử mà không thay đổi số lượng phần tử. Ví dụ, một luồng Order có thể được chuyển thành luồng OrderSummary, một chuỗi nhiệt độ có thể được chuẩn hóa sang độ Fahrenheit, hoặc một bản ghi database có thể được chuyển thành DTO trước khi trả về API. Với Reactor, toán tử **map** là lựa chọn cơ bản cho kiểu biến đổi một–một này.

Quan hệ một–một có nghĩa là mỗi giá trị được phát từ upstream và đi đến toán tử sẽ tạo ra đúng một giá trị tương ứng ở downstream. map không lọc phần tử, không tạo thêm publisher con và không tự chạy một tác vụ bất đồng bộ. Nó nhận một giá trị, áp dụng hàm biến đổi đồng bộ rồi phát kết quả. Hiểu đúng semantics này giúp chọn map thay vì filter, flatMap hoặc concatMap, đồng thời dự đoán được số lượng, thứ tự và cách lỗi đi qua pipeline.

## 1. Biến đổi một–một là gì?

Giả sử nguồn phát ba số nguyên:

~~~text
1 -> 2 -> 3
~~~

Ta muốn nhân mỗi giá trị với 10:

~~~text
1 -> 10
2 -> 20
3 -> 30
~~~

Mỗi phần tử đầu vào tạo ra đúng một phần tử đầu ra. Số lượng vẫn là ba, thứ tự vẫn theo thứ tự nguồn phát và kiểu dữ liệu có thể thay đổi từ Integer sang một kiểu khác.

Trong Reactor:

~~~java
Flux<Integer> numbers = Flux.just(1, 2, 3);

Flux<Integer> multiplied = numbers
    .map(number -> number * 10);
~~~

map tạo một publisher mới mô tả phép biến đổi. Publisher nguồn không bị thay đổi. Khi có subscriber đăng ký multiplied, từng giá trị từ numbers được chuyển qua hàm mapper và kết quả được phát xuống downstream.

Với Mono, semantics tương tự nhưng publisher chỉ có tối đa một giá trị:

~~~java
Mono<String> normalizedName = Mono.just("  Nguyen An  ")
    .map(String::trim)
    .map(String::toUpperCase);
~~~

Nếu Mono phát một giá trị, mapper tạo một giá trị mới. Nếu Mono rỗng, mapper không được gọi và publisher kết quả vẫn rỗng. Nếu Mono kết thúc bằng lỗi, lỗi được truyền xuống và mapper không được gọi cho giá trị nào.

## 2. Dùng map để chuyển đổi kiểu dữ liệu

Một ứng dụng thường nhận dữ liệu ở dạng phù hợp với tầng lưu trữ hoặc nguồn bên ngoài, sau đó chuyển thành kiểu phù hợp với tầng nghiệp vụ hoặc API. map giúp thực hiện việc chuyển đổi ngay trong pipeline.

Ví dụ, repository phát các đơn hàng và service muốn trả về dữ liệu tóm tắt:

~~~java
record Order(
    String id,
    BigDecimal total,
    OrderStatus status
) {}

record OrderSummary(
    String orderId,
    BigDecimal amount,
    String status
) {}

Flux<OrderSummary> summaries = orderRepository.findByCustomer(customerId)
    .map(order -> new OrderSummary(
        order.id(),
        order.total(),
        order.status().name()
    ));
~~~

Mỗi Order tạo một OrderSummary. Publisher đầu vào là Flux<Order> và publisher đầu ra là Flux<OrderSummary>. Số lượng phần tử không đổi do mapper tạo đúng một summary cho mỗi order được nhận.

Có thể tách phép biến đổi thành một method reference nếu logic đã có tên rõ ràng:

~~~java
private OrderSummary toSummary(Order order) {
    return new OrderSummary(
        order.id(),
        order.total(),
        order.status().name()
    );
}

Flux<OrderSummary> summaries = orderRepository.findByCustomer(customerId)
    .map(this::toSummary);
~~~

Cách này giúp pipeline dễ đọc hơn khi phép biến đổi có nhiều trường hoặc cần tái sử dụng. Hàm toSummary nên tập trung vào việc chuyển đổi một giá trị, tránh thực hiện I/O hoặc thay đổi trạng thái bên ngoài.

## 3. map giữ số lượng và thứ tự mà nó nhận được

Với một upstream phát tuần tự các phần tử A, B, C, toán tử map chuyển chúng thành f(A), f(B), f(C) theo đúng trình tự tín hiệu nhận được. Bản thân map không bỏ phần tử và không đổi thứ tự.

| Đặc điểm | Hành vi của map |
| --- | --- |
| Cardinality | Một giá trị đầu vào tạo một giá trị đầu ra |
| Kiểu dữ liệu | Có thể đổi từ T sang R |
| Thứ tự | Giữ thứ tự tín hiệu upstream đã phát |
| Empty publisher | Vẫn empty; mapper không được gọi |
| Error signal | Được chuyển tiếp; mapper không được gọi sau terminal error |
| Mapper ném exception | Pipeline kết thúc bằng onError |
| Mapper trả null | Không hợp lệ trong Reactive Streams; Reactor chuyển thành lỗi |

Điểm “giữ thứ tự” cần được hiểu tại ranh giới của toán tử: map phát kết quả theo thứ tự mà nó nhận tín hiệu upstream. Nếu upstream trước đó đã kết hợp nhiều nguồn đồng thời và phát kết quả theo thứ tự hoàn tất, map không tự sắp xếp lại theo một khóa nghiệp vụ. Khi cần sắp xếp, phải dùng bước sắp xếp hoặc chiến lược kết hợp có semantics giữ thứ tự phù hợp.

## 4. Kết hợp nhiều map để biểu diễn các bước chuyển đổi

Một giá trị có thể đi qua nhiều phép biến đổi nhỏ. Có thể nối nhiều map để mỗi bước thể hiện một ý nghĩa riêng:

~~~java
Flux<String> displayNames = userRepository.findActiveUsers()
    .map(User::displayName)
    .map(String::trim)
    .map(String::toUpperCase);
~~~

Pipeline lần lượt lấy tên hiển thị, loại bỏ khoảng trắng ở hai đầu và chuyển thành chữ hoa. Mỗi bước vẫn duy trì quan hệ một–một. Việc tách các phép biến đổi nhỏ thường giúp đọc, kiểm thử và tái sử dụng dễ hơn.

Nếu các bước quá đơn giản và chỉ có ý nghĩa khi kết hợp, có thể gộp chúng vào một mapper:

~~~java
Flux<String> displayNames = userRepository.findActiveUsers()
    .map(user -> user.displayName().trim().toUpperCase());
~~~

Hãy chọn cách thể hiện giúp người đọc hiểu nghiệp vụ. Không cần tạo một toán tử map cho mọi biểu thức nhỏ nếu nó làm pipeline dài và khó theo dõi. Ngược lại, một mapper quá lớn có thể che giấu nhiều quy tắc chuyển đổi và khiến test khó xác định nguyên nhân lỗi.

## 5. map chạy hàm biến đổi đồng bộ trên thread phát tín hiệu

map không tự chuyển công việc sang scheduler khác. Mapper được gọi khi phần tử đi qua toán tử, trên thread đang thực thi tín hiệu tại vị trí đó. Nếu upstream phát đồng bộ trong lúc subscribe, mapper có thể chạy ngay trên thread gọi subscribe. Nếu upstream phát trên event-loop hoặc scheduler cụ thể, mapper thường chạy trên thread đó cho đến khi pipeline có ranh giới scheduler khác.

~~~java
Flux<Integer> result = Flux.range(1, 3)
    .map(value -> {
        logThread("map", Thread.currentThread().getName());
        return value * 2;
    });
~~~

Đoạn mã minh họa cách quan sát thread. Không nên dùng map để thực hiện một lời gọi blocking nặng trên event-loop. Nếu phải gọi thư viện blocking, hãy cô lập nguồn blocking bằng Mono.fromCallable hoặc Flux.defer kết hợp subscribeOn(Schedulers.boundedElastic()) theo đúng ranh giới. Nếu mapper chỉ thực hiện tính toán CPU, cần đánh giá chi phí và quyết định có cần chuyển sang scheduler CPU-bound hay không; việc chuyển thread cũng có overhead.

Ví dụ cô lập lời gọi blocking trước khi biến đổi:

~~~java
Mono<User> user = Mono.fromCallable(() -> legacyRepository.findById(userId))
    .subscribeOn(Schedulers.boundedElastic());

Mono<UserView> view = user
    .map(this::toUserView);
~~~

fromCallable trì hoãn lời gọi đến subscription và subscribeOn đặt công việc blocking trên boundedElastic. map sau đó chuyển đổi kết quả trên thread phát tín hiệu. Nếu toUserView cũng thực hiện blocking hoặc tính toán rất nặng, cần đánh giá riêng thay vì cho rằng scheduler của nguồn tự động là lựa chọn tốt cho mọi bước.

## 6. Hàm mapper nên tập trung vào chuyển đổi

Một mapper dễ kiểm thử thường nhận một giá trị và trả về một giá trị mới, không phụ thuộc vào thời điểm thực thi hoặc trạng thái bên ngoài. Ví dụ tốt:

~~~java
OrderSummary toSummary(Order order) {
    return new OrderSummary(
        order.id(),
        order.total(),
        order.status().name()
    );
}
~~~

Ngược lại, tránh dùng mapper như nơi thực hiện side effect:

~~~java
// Không nên: mapper vừa chuyển đổi vừa ghi dữ liệu ra ngoài.
Flux<OrderView> views = orders.map(order -> {
    auditRepository.save(order);
    return toView(order);
});
~~~

Đoạn mã trên khiến việc biến đổi dữ liệu phụ thuộc vào một thao tác ghi. Nếu pipeline được subscribe nhiều lần, thao tác ghi có thể lặp lại. Nếu thao tác ghi blocking, nó có thể chặn thread đang phát tín hiệu. Nếu ghi thất bại, mapper ném exception và pipeline kết thúc bằng lỗi.

Nếu cần thực hiện side effect, hãy thể hiện nó rõ ràng bằng một bước phù hợp và xác định semantics bất đồng bộ. doOnNext chỉ phù hợp cho hành động quan sát nhẹ như logging hoặc metric; nó không phải cơ chế compose một thao tác I/O có kết quả. Với một thao tác bất đồng bộ, thường cần flatMap để kết hợp publisher của thao tác đó.

## 7. Xử lý null và giá trị vắng mặt

Reactive Streams không cho phép publisher phát null qua onNext. Vì vậy, mapper không được trả null để biểu diễn “không có kết quả”. Trong Reactor, nếu mapper trả null, pipeline kết thúc bằng lỗi NullPointerException.

Không nên viết:

~~~java
Mono<String> name = userMono
    .map(user -> user.nickname() == null ? null : user.nickname());
~~~

Nếu nickname có thể vắng mặt, hãy chọn cách biểu diễn rõ ràng:

~~~java
Mono<Optional<String>> nickname = userMono
    .map(user -> Optional.ofNullable(user.nickname()));
~~~

Hoặc nếu yêu cầu nghiệp vụ là không phát kết quả khi nickname vắng mặt:

~~~java
Mono<String> nickname = userMono
    .flatMap(user -> Mono.justOrEmpty(user.nickname()));
~~~

Ví dụ thứ hai dùng flatMap vì hàm chuyển đổi trả về Mono<String> có thể rỗng. Nếu chỉ cần biểu diễn một trường nullable bên trong một DTO và vẫn muốn một DTO cho mỗi user, map cùng Optional có thể giữ quan hệ một–một.

## 8. Exception trong mapper trở thành onError

Mapper có thể ném exception khi dữ liệu không hợp lệ hoặc phép chuyển đổi thất bại. Reactor bắt exception phát sinh từ mapper và chuyển nó thành tín hiệu onError. Tín hiệu lỗi kết thúc pipeline hiện tại; các phần tử upstream tiếp theo không tiếp tục được xử lý qua mapper đó.

~~~java
Flux<Integer> parsed = Flux.just("10", "20", "abc", "40")
    .map(Integer::parseInt);
~~~

Pipeline phát 10 và 20, sau đó Integer.parseInt("abc") ném NumberFormatException. Subscriber nhận onError; giá trị 40 phía sau không được xử lý trong subscription này.

Nếu lỗi chuyển đổi cần được ánh xạ sang lỗi miền nghiệp vụ, có thể dùng onErrorMap:

~~~java
Flux<Integer> parsed = rawValues
    .map(Integer::parseInt)
    .onErrorMap(NumberFormatException.class,
        error -> new InvalidInputException("Giá trị số không hợp lệ", error));
~~~

Nếu mỗi phần tử lỗi cần được thay bằng một kết quả khác và tiếp tục xử lý phần tử sau, cần thiết kế ranh giới phục hồi theo từng phần tử. Không nên giả định map tự bỏ qua phần tử lỗi. Có thể chuyển từng phần tử thành publisher con với flatMap và đặt xử lý lỗi bên trong publisher con, hoặc dùng một hàm chuyển đổi trả về kiểu kết quả thể hiện success/failure. Cách chọn phụ thuộc yêu cầu giữ hay bỏ lỗi của từng phần tử.

## 9. Phân biệt map với filter, flatMap và concatMap

Các toán tử này có hình dạng tương tự nhưng semantics khác nhau. Chọn theo quan hệ giữa một phần tử đầu vào và kết quả mong muốn.

| Toán tử | Quan hệ cardinality | Mục đích |
| --- | --- | --- |
| map | 1 -> 1 | Chuyển một giá trị thành một giá trị khác |
| filter | 1 -> 0 hoặc 1 | Giữ hoặc loại bỏ phần tử theo điều kiện |
| flatMap | 1 -> 0, 1 hoặc nhiều phần tử | Chuyển mỗi giá trị thành publisher con và hợp nhất kết quả; có thể chạy đồng thời |
| concatMap | 1 -> 0, 1 hoặc nhiều phần tử | Chuyển mỗi giá trị thành publisher con và xử lý tuần tự theo thứ tự nguồn |
| handle | 1 -> 0 hoặc 1 | Kết hợp kiểm tra và phát kết quả có điều kiện trong một callback |

Ví dụ dùng map khi mỗi đơn hàng tạo đúng một nhãn:

~~~java
Flux<String> labels = orders
    .map(order -> order.id() + ":" + order.status());
~~~

Dùng filter khi chỉ muốn giữ đơn hàng đã thanh toán:

~~~java
Flux<Order> paidOrders = orders
    .filter(order -> order.status() == OrderStatus.PAID);
~~~

Dùng flatMap khi mỗi đơn hàng cần gọi một publisher khác để lấy thông tin giao hàng:

~~~java
Flux<Delivery> deliveries = orders
    .flatMap(order -> deliveryClient.findByOrderId(order.id()));
~~~

Dùng concatMap nếu các publisher con phải được xử lý lần lượt và kết quả phải giữ thứ tự nguồn:

~~~java
Flux<Delivery> deliveriesInOrder = orders
    .concatMap(order -> deliveryClient.findByOrderId(order.id()));
~~~

Đừng dùng map khi mapper trả về một Mono hoặc Flux mà bạn muốn hợp nhất. Nếu viết orders.map(order -> deliveryClient.findByOrderId(...)), kết quả sẽ là Flux<Mono<Delivery>>: một luồng chứa các publisher con chưa được flatten. flatMap hoặc concatMap thể hiện rõ việc đăng ký và kết hợp các publisher con.

## 10. Biến đổi lồng nhau và cấu trúc dữ liệu

map phù hợp để chuyển đổi cấu trúc một phần tử mà không thay đổi số lượng phần tử của luồng. Ví dụ, một Customer có thể chứa địa chỉ và danh sách thông tin liên hệ; mapper có thể tạo DTO phẳng cho API:

~~~java
Flux<CustomerView> views = customers
    .map(customer -> new CustomerView(
        customer.id(),
        customer.profile().fullName(),
        customer.address().city(),
        customer.contacts().size()
    ));
~~~

Mỗi customer tạo một view. Số liên hệ được tính thành một trường số, không phát thành nhiều phần tử. Nếu yêu cầu là phát riêng từng contact, quan hệ không còn một–một; khi đó cần flatMap hoặc một toán tử biến đổi luồng phù hợp.

Khi dữ liệu lồng nhau có thể null, cần xác định hợp đồng miền trước khi truy cập. Có thể dùng Optional, kiểu dữ liệu biểu diễn sự vắng mặt hoặc một hàm chuyển đổi có kiểm soát. Đừng để một chuỗi truy cập có thể null tạo lỗi bất ngờ mà không có test cho trường hợp đó.

## 11. Kiểm thử phép biến đổi một–một

Reactor Test cung cấp StepVerifier để kiểm tra các phần tử và terminal signal mà publisher phát ra. Một test cơ bản xác minh cả giá trị lẫn số lượng:

~~~java
Flux<Integer> transformed = Flux.just(1, 2, 3)
    .map(number -> number * 10);

StepVerifier.create(transformed)
    .expectNext(10, 20, 30)
    .verifyComplete();
~~~

expectNext(10, 20, 30) xác minh đúng ba giá trị theo đúng thứ tự; verifyComplete() xác minh nguồn kết thúc bình thường. Nếu mapper vô tình lọc phần tử hoặc phát sai giá trị, test sẽ thất bại.

Có thể kiểm tra trường hợp Mono rỗng:

~~~java
StepVerifier.create(Mono.<String>empty().map(String::toUpperCase))
    .verifyComplete();
~~~

Mapper không được gọi vì không có giá trị. Có thể dùng một counter trong test để xác nhận điều đó, nhưng tránh đưa side effect vào mapper của code production chỉ để dễ test.

Kiểm tra lỗi từ mapper:

~~~java
StepVerifier.create(
        Flux.just("12", "x", "30").map(Integer::parseInt))
    .expectNext(12)
    .expectError(NumberFormatException.class)
    .verify();
~~~

Test xác minh phần tử hợp lệ đầu tiên được phát, sau đó lỗi chuyển đổi kết thúc pipeline. Phần tử "30" không được phát sau lỗi. Với logic chuyển đổi nghiệp vụ, nên bổ sung unit test trực tiếp cho hàm mapper để kiểm tra biên dữ liệu, định dạng và các trường hợp không hợp lệ.

## 12. Những lỗi thường gặp

- **Dùng map để gọi một API bất đồng bộ:** mapper tạo Mono/Flux lồng nhau; dùng flatMap hoặc concatMap để compose publisher con.
- **Nghĩ map thay đổi số lượng phần tử:** map giữ quan hệ một–một; dùng filter để loại bỏ hoặc flatMap để phát nhiều/không phần tử.
- **Trả về null từ mapper:** Reactive Streams không cho phép null qua onNext; dùng Optional, publisher rỗng hoặc kiểu kết quả tường minh.
- **Thực hiện I/O blocking trong mapper:** mapper chạy trên thread phát tín hiệu và có thể chặn event-loop; cô lập nguồn blocking bằng scheduler phù hợp.
- **Đặt side effect vào mapper:** mỗi subscription có thể chạy lại nguồn và mapper; side effect có thể lặp ngoài dự kiến.
- **Cho rằng mapper ném exception chỉ làm hỏng một phần tử:** exception thường kết thúc subscription bằng onError; muốn phục hồi từng phần tử phải đặt ranh giới xử lý lỗi theo từng phần tử.
- **Dùng map để sắp xếp dữ liệu:** map chỉ biến đổi; nó giữ thứ tự nhận được chứ không sắp xếp theo khóa.
- **Gộp quá nhiều logic vào một mapper:** hàm dài làm khó kiểm thử và khó xác định quy tắc nào gây lỗi; tách method khi cần.
- **Cho rằng map tạo thread mới:** map không đổi scheduler; dùng publishOn/subscribeOn khi có yêu cầu thực thi cụ thể.

## 13. Quy trình chọn toán tử cho một phép biến đổi

Trước khi viết một bước xử lý, hãy xác định quan hệ giữa một phần tử đầu vào và kết quả:

1. Nếu mỗi giá trị tạo đúng một giá trị mới, dùng map.
2. Nếu giá trị có thể bị loại bỏ theo điều kiện, dùng filter hoặc handle.
3. Nếu một giá trị dẫn đến một publisher khác, dùng flatMap hoặc concatMap tùy yêu cầu concurrency và thứ tự.
4. Nếu mapper có thể không tạo kết quả, biểu diễn rõ bằng Mono.empty, Optional hoặc một kiểu kết quả phù hợp; không trả null.
5. Nếu mapper có thể lỗi, xác định lỗi có nên kết thúc toàn pipeline hay được phục hồi riêng cho phần tử đó.
6. Nếu mapper thực hiện blocking hoặc tính toán nặng, xác định scheduler và giới hạn tài nguyên trước khi triển khai.
7. Viết test cho số lượng, thứ tự, giá trị, empty và lỗi.

map là toán tử cốt lõi để chuyển đổi từng phần tử trong Mono và Flux mà giữ quan hệ một–một. Nó làm pipeline thể hiện rõ việc đổi kiểu hoặc tạo một biểu diễn mới, đồng thời giữ nguyên số lượng và thứ tự tín hiệu mà nó nhận được. Khi cần lọc, phát nhiều kết quả, gọi publisher bất đồng bộ hoặc phục hồi lỗi theo từng phần tử, hãy chọn toán tử có semantics tương ứng. Mapper nên tập trung vào chuyển đổi giá trị, không trả null, không chặn thread và không che giấu side effect. Với những nguyên tắc này, các bước biến đổi dữ liệu trong Reactor sẽ dễ đọc, kiểm thử và kết hợp thành pipeline lớn hơn.
