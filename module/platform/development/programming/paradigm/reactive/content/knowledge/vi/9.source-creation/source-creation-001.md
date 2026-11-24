# Tạo luồng từ một giá trị, mảng, bộ sưu tập và khoảng số

Trong chương **Tạo nguồn**, bài học này trình bày cách tạo các publisher hữu hạn bằng Reactor từ dữ liệu đã có trong ứng dụng: một giá trị đơn, một mảng, một bộ sưu tập hoặc một dãy số. Đây là những cách tạo nguồn thường gặp khi chuyển dữ liệu Java thông thường thành pipeline reactive.

Bài học thuộc module **REACTIVE_PROGRAMMING**. Module hướng dẫn: “Học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.” Khi tạo nguồn, ta cần chọn đúng kiểu publisher, hiểu thời điểm dữ liệu được lấy và biết mỗi lần subscribe sẽ nhận chuỗi tín hiệu nào.

## 1. Từ dữ liệu Java đến Publisher

Trong Reactor, hai kiểu nguồn cơ bản là:

- `Mono<T>`: biểu diễn tối đa một phần tử kiểu `T`, sau đó kết thúc bằng `onComplete`; hoặc kết thúc ngay mà không phát phần tử nào.
- `Flux<T>`: biểu diễn từ không đến nhiều phần tử kiểu `T`, sau đó kết thúc bằng `onComplete`, hoặc kết thúc bằng `onError` nếu có lỗi.

Cả hai đều tuân theo hợp đồng Reactive Streams. Subscriber đăng ký và nhận `Subscription`; subscriber yêu cầu dữ liệu bằng `request(n)`, rồi publisher phát tối đa số phần tử đã được yêu cầu. Với nguồn hữu hạn, sau phần tử cuối cùng publisher gửi tín hiệu hoàn tất.

Một vài ví dụ đầu vào và kiểu nguồn thường dùng:

| Dữ liệu đầu vào | Cách tạo nguồn | Kiểu kết quả |
|---|---|---|
| Một đối tượng | `Mono.just(value)` | `Mono<T>` |
| Một hoặc nhiều giá trị viết trực tiếp | `Flux.just(a, b, c)` | `Flux<T>` |
| Mảng | `Flux.fromArray(array)` | `Flux<T>` |
| `Iterable` như `List` hoặc `Set` | `Flux.fromIterable(items)` | `Flux<T>` |
| Khoảng số nguyên liên tiếp | `Flux.range(start, count)` | `Flux<Integer>` |

Hãy chọn publisher theo số phần tử mà pipeline cần biểu diễn. Một đối tượng đơn lẻ thường phù hợp với `Mono`; một tập hợp các phần tử phù hợp với `Flux`.

## 2. Tạo nguồn từ một giá trị với `just`

`Mono.just(value)` tạo một publisher phát đúng một giá trị rồi hoàn tất. `Flux.just(a, b, c)` tạo một publisher phát các giá trị theo thứ tự đã truyền vào.

```java
Mono<String> greeting = Mono.just("Xin chào");

Flux<String> colors = Flux.just("đỏ", "xanh", "vàng");
```

Khi có subscriber, `greeting` phát một giá trị `"Xin chào"` rồi hoàn tất. `colors` phát ba giá trị theo thứ tự `đỏ`, `xanh`, `vàng` rồi hoàn tất.

Có thể dùng `Mono.just` khi một thao tác đã có sẵn kết quả và muốn đưa kết quả đó vào pipeline:

```java
Order order = orderRepository.findCachedOrder(orderId);

Mono<Order> orderPublisher = Mono.just(order);

orderPublisher
    .map(Order::getId)
    .subscribe(System.out::println);
```

Cần chú ý rằng biểu thức tạo đối số được Java đánh giá ngay khi gọi `Mono.just`. Trong ví dụ trên, `findCachedOrder(orderId)` chạy trước khi publisher được subscribe; ví dụ giả định phương thức trả về một đối tượng khác `null`. Nếu kết quả có thể vắng mặt, dùng `Mono.justOrEmpty`. `just` giữ giá trị đã truyền vào; nó không tự gọi lại phương thức lấy dữ liệu cho từng subscriber.

Nếu muốn trì hoãn việc tạo giá trị cho đến lúc subscribe, có thể dùng `Mono.fromSupplier` hoặc `Mono.defer`:

```java
Mono<Order> lazyOrder =
    Mono.fromSupplier(() -> orderRepository.findCachedOrder(orderId));
```

Supplier được gọi khi có subscription. Nếu supplier trả về `null`, `Mono.fromSupplier` hoàn tất mà không phát phần tử. Cách này phù hợp với một phép tính đồng bộ có thể trả về giá trị hoặc không có kết quả.

Nếu muốn trì hoãn việc tạo cả publisher, dùng `defer`:

```java
Mono<Order> deferredOrder =
    Mono.defer(() -> Mono.just(loadOrder(orderId)));
```

Hàm bên trong `defer` được gọi cho từng subscriber để tạo publisher tương ứng. Đây là lựa chọn hữu ích khi mỗi subscription cần lấy trạng thái mới hoặc cần tạo nguồn theo ngữ cảnh tại thời điểm đăng ký.

### Không phát `null`

Reactive Streams không cho phép publisher phát `null` như một phần tử. Vì vậy, `Mono.just(null)` và `Flux.just(..., null, ...)` không phải cách biểu diễn dữ liệu vắng mặt hợp lệ.

Nếu có thể không có giá trị, hãy biểu diễn trường hợp đó bằng publisher rỗng:

```java
Mono<String> present = Mono.justOrEmpty("reactive");
Mono<String> absent = Mono.justOrEmpty((String) null);

Mono<String> fromOptional =
    Mono.justOrEmpty(Optional.of("publisher"));
```

`Mono.justOrEmpty` phát một giá trị nếu đối số có giá trị; nếu đối số là `null` hoặc `Optional.empty()`, publisher hoàn tất mà không phát phần tử. Cách biểu diễn này giúp phân biệt rõ “không có dữ liệu” với một giá trị thực tế.

## 3. Tạo luồng từ mảng với `fromArray`

Khi dữ liệu đang nằm trong mảng Java, dùng `Flux.fromArray(array)` để phát từng phần tử của mảng theo thứ tự chỉ số.

```java
String[] roles = {"ADMIN", "EDITOR", "VIEWER"};

Flux<String> rolePublisher = Flux.fromArray(roles);

rolePublisher
    .map(String::toLowerCase)
    .subscribe(System.out::println);
```

Kết quả là ba phần tử `admin`, `editor`, `viewer`. Publisher phát các phần tử của mảng, không phát bản thân mảng như một phần tử duy nhất.

Phân biệt hai ý nghĩa sau:

```java
String[] roles = {"ADMIN", "EDITOR"};

Flux<String> eachRole = Flux.fromArray(roles);
Mono<String[]> wholeArray = Mono.just(roles);
```

- `Flux.fromArray(roles)` phát lần lượt từng chuỗi.
- `Mono.just(roles)` phát một phần tử duy nhất có kiểu `String[]`, chính là cả mảng.

Sự khác biệt tương tự xuất hiện với bộ sưu tập: `Flux.fromIterable(items)` phát từng phần tử, còn `Mono.just(items)` phát cả đối tượng collection như một giá trị.

Mảng là cấu trúc có thể thay đổi. Nếu ứng dụng sửa phần tử của mảng trong lúc publisher đang được tiêu thụ, kết quả có thể khó dự đoán. Nên coi mảng đầu vào là dữ liệu bất biến trong suốt vòng đời xử lý, hoặc tạo một bản sao nếu cần cô lập dữ liệu.

## 4. Tạo luồng từ bộ sưu tập với `fromIterable`

`Flux.fromIterable(iterable)` chuyển một đối tượng triển khai `Iterable` thành luồng. Đây là cách thường dùng với `List`, `Set` hoặc các kiểu collection khác.

```java
List<String> productCodes =
    List.of("P-100", "P-200", "P-300");

Flux<String> products = Flux.fromIterable(productCodes);

products
    .filter(code -> code.startsWith("P-"))
    .map(String::toLowerCase)
    .subscribe(System.out::println);
```

Publisher phát từng mã sản phẩm theo thứ tự iterator cung cấp. Với `List`, thứ tự phần tử được giữ theo vị trí trong danh sách. Với một số kiểu `Set`, thứ tự duyệt có thể không được bảo đảm; nếu nghiệp vụ phụ thuộc thứ tự, hãy chọn collection có quy tắc thứ tự rõ ràng.

Một collection rỗng tạo ra một `Flux` rỗng:

```java
Flux<String> noProducts =
    Flux.fromIterable(Collections.emptyList());
```

Khi subscribe, publisher không phát `onNext`; nó gửi `onComplete`. Đây là luồng rỗng hợp lệ, không phải lỗi.

`Iterable` cung cấp iterator để duyệt dữ liệu. Reactor lấy dữ liệu khi publisher được subscribe và tiêu thụ theo nhu cầu downstream. Với collection có thể duyệt lại như `List`, mỗi subscription thường tạo một lượt duyệt riêng:

```java
Flux<String> names =
    Flux.fromIterable(List.of("An", "Bình", "Chi"));

names.subscribe(name -> System.out.println("A: " + name));
names.subscribe(name -> System.out.println("B: " + name));
```

Hai subscriber nhận hai lượt phát độc lập từ cùng dữ liệu đầu vào. Đây vẫn là publisher lạnh: việc subscribe lần nữa không tự chia sẻ kết quả của lần trước.

Không nên sửa collection trong lúc pipeline đang duyệt nó. Với collection có cơ chế phát hiện sửa đổi đồng thời, việc thay đổi cấu trúc trong lúc lặp có thể dẫn đến `ConcurrentModificationException`. Nếu dữ liệu cần thay đổi theo thời gian, hãy thiết kế nguồn sự kiện riêng thay vì dùng một collection đang bị nhiều luồng cập nhật.

### Khi đầu vào là Stream

Java `Stream` khác với `Iterable`: một stream chỉ được tiêu thụ một lần. Nếu chuyển trực tiếp một stream đã tạo bằng `Flux.fromStream(stream)`, subscription tiếp theo có thể thất bại vì stream đã được dùng hoặc đóng.

Nếu cần nhiều subscription, truyền một supplier tạo stream mới cho mỗi lần đăng ký:

```java
List<String> names = List.of("An", "Bình", "Chi");

Flux<String> namePublisher =
    Flux.fromStream(names::stream);
```

Reactor đóng stream sau khi luồng kết thúc hoặc bị hủy. Supplier cần tạo một stream mới trong mỗi lần gọi và không trả lại một stream đã tiêu thụ.

## 5. Tạo dãy số với `range`

`Flux.range(start, count)` tạo một luồng gồm `count` số nguyên liên tiếp, bắt đầu từ `start`.

```java
Flux<Integer> sequence = Flux.range(10, 4);

sequence.subscribe(System.out::println);
```

Luồng phát:

```text
10
11
12
13
```

Tham số thứ hai là số lượng phần tử, không phải giá trị kết thúc. Do đó:

```java
Flux.range(1, 5)
```

phát năm số `1, 2, 3, 4, 5`. Nếu muốn tạo dãy từ 1 đến 100, có thể viết `Flux.range(1, 100)`.

Một số trường hợp biên cần nhớ:

- `Flux.range(5, 0)` tạo luồng rỗng và hoàn tất.
- `count` âm không hợp lệ.
- `range` tạo số nguyên kiểu `Integer`; nếu cần kiểu số khác hoặc quy tắc sinh dữ liệu phức tạp, hãy chọn nguồn và phép biến đổi phù hợp.

Nguồn từ `range` đặc biệt hữu ích để tạo dữ liệu mẫu, sinh số thứ tự, phân trang theo chỉ số hoặc thử nghiệm toán tử:

```java
Flux<String> pageLabels =
    Flux.range(0, 5)
        .map(index -> "Trang " + (index + 1));
```

Kết quả là năm nhãn trang. Không cần tạo sẵn một danh sách số nguyên chỉ để chuyển danh sách đó thành `Flux`.

## 6. Kết hợp nguồn với toán tử

Các publisher được tạo từ giá trị, mảng, collection hoặc khoảng số đều có thể nối vào cùng một pipeline. Những toán tử như `map`, `filter`, `flatMap` và `collectList` biến đổi hoặc tổng hợp dữ liệu mà không cần thay đổi nguồn ban đầu.

Ví dụ, tạo luồng mã sản phẩm từ collection, lọc mã hợp lệ rồi ánh xạ sang đối tượng:

```java
record Product(String code, String displayName) {}

List<String> codes =
    List.of("P-100", "X-404", "P-200");

Flux<Product> products =
    Flux.fromIterable(codes)
        .filter(code -> code.startsWith("P-"))
        .map(code -> new Product(code, "Sản phẩm " + code));
```

Có thể tạo chỉ số bằng `range` và kết hợp với một nguồn khác. Chẳng hạn, mỗi phần tử trong danh sách được gắn một vị trí:

```java
List<String> tasks = List.of("validate", "persist", "notify");

Flux<String> indexedTasks =
    Flux.range(0, tasks.size())
        .map(index -> (index + 1) + ". " + tasks.get(index));
```

Kết quả là `1. validate`, `2. persist`, `3. notify`. Trong ví dụ này, `range` tạo các chỉ số, còn `map` tra cứu phần tử tương ứng trong danh sách.

Nếu chỉ cần thu thập các phần tử của `Flux` thành một danh sách ở cuối pipeline, dùng `collectList()`:

```java
Mono<List<Integer>> collected =
    Flux.range(1, 4)
        .map(number -> number * 10)
        .collectList();
```

Kết quả là một `Mono<List<Integer>>` phát danh sách `[10, 20, 30, 40]`. Việc thu thập này cần giữ các phần tử cho đến khi nguồn hoàn tất; với luồng lớn hoặc không giới hạn, không nên gom toàn bộ vào bộ nhớ.

## 7. Thời điểm tạo dữ liệu và mỗi lần subscribe

Khi làm việc với nguồn, cần phân biệt ba thời điểm:

1. **Assembly:** ứng dụng gọi các phương thức như `Mono.just`, `Flux.fromIterable` hoặc `Flux.range` để tạo mô tả pipeline.
2. **Subscription:** subscriber đăng ký; publisher thiết lập quá trình phát và tạo subscription.
3. **Demand và signal:** subscriber yêu cầu dữ liệu; publisher phát `onNext` theo nhu cầu, sau đó gửi `onComplete` hoặc `onError`.

Không phải mọi giá trị đều được tạo ở cùng một thời điểm. Với `Mono.just(load())`, phương thức `load()` chạy ở assembly. Với `Mono.fromSupplier(this::load)`, supplier chạy khi subscribe. Sự khác biệt này quan trọng nếu thao tác lấy dữ liệu tốn thời gian, phụ thuộc trạng thái hiện tại hoặc cần thực hiện lại cho từng subscriber.

Các nguồn từ giá trị, mảng, collection và range thường là nguồn lạnh. Mỗi lần subscribe tạo một lượt tiêu thụ mới theo cách publisher định nghĩa. Nếu cần nhiều subscriber cùng quan sát một lần phát, hãy dùng cơ chế chia sẻ nguồn phù hợp; việc gọi `subscribe()` nhiều lần lên một publisher lạnh không tự tạo multicast.

Backpressure vẫn có ý nghĩa với các nguồn hữu hạn. Subscriber có thể yêu cầu từng phần dữ liệu; publisher không được phát nhiều phần tử hơn demand đã nhận. Ví dụ, khi downstream chỉ yêu cầu hai phần tử từ `Flux.range(1, 5)`, publisher có thể phát hai phần tử đầu và chờ yêu cầu tiếp theo.

## 8. Kiểm thử các nguồn vừa tạo

Có thể dùng `StepVerifier` trong Reactor Test để kiểm tra chuỗi giá trị và tín hiệu kết thúc. Ví dụ dưới đây kiểm tra nguồn tạo từ một giá trị, mảng, collection và range:

```java
StepVerifier.create(Mono.just("ready"))
    .expectNext("ready")
    .verifyComplete();

StepVerifier.create(Flux.fromArray(new Integer[] {2, 4, 6}))
    .expectNext(2, 4, 6)
    .verifyComplete();

StepVerifier.create(Flux.fromIterable(List.of("A", "B")))
    .expectNext("A", "B")
    .verifyComplete();

StepVerifier.create(Flux.range(3, 3))
    .expectNext(3, 4, 5)
    .verifyComplete();
```

Mỗi kiểm thử xác nhận cả giá trị và tín hiệu hoàn tất. Với publisher rỗng, có thể kiểm tra rằng không có phần tử nào được phát:

```java
StepVerifier.create(Flux.range(10, 0))
    .verifyComplete();
```

Khi kiểm thử nguồn tạo từ supplier hoặc `defer`, nên kiểm tra cả số lần supplier được gọi để xác nhận dữ liệu chỉ được tạo tại thời điểm mong đợi và được tạo lại đúng số lần subscription.

## 9. Chọn toán tử và tránh lỗi thường gặp

| Nhu cầu | Nên dùng | Lưu ý |
|---|---|---|
| Một kết quả đã có sẵn | `Mono.just(value)` | Giá trị được lấy tại assembly |
| Một phép tính đồng bộ cần chạy khi subscribe | `Mono.fromSupplier(...)` | Giá trị `null` tạo publisher rỗng |
| Có thể không có giá trị | `Mono.justOrEmpty(...)` | Biểu diễn trường hợp vắng mặt bằng completion |
| Phát từng phần tử của mảng | `Flux.fromArray(array)` | Không phát cả mảng như một phần tử |
| Phát từng phần tử của collection | `Flux.fromIterable(items)` | Mỗi subscription thực hiện lượt duyệt |
| Phát từng phần tử của Stream | `Flux.fromStream(supplier)` | Supplier phải tạo stream mới cho mỗi subscription |
| Tạo dãy số nguyên liên tiếp | `Flux.range(start, count)` | Tham số thứ hai là số lượng phần tử |

Một số lỗi dễ gặp khi mới tạo nguồn:

- **Dùng `Mono.just` cho dữ liệu có thể vắng mặt.** Nếu đầu vào có thể là `null`, dùng `justOrEmpty` hoặc một publisher phù hợp thay vì để lỗi phát sinh.
- **Nhầm collection với các phần tử của collection.** `Mono.just(list)` phát một đối tượng List; `Flux.fromIterable(list)` phát từng phần tử.
- **Cho rằng `just` trì hoãn việc gọi hàm.** Đối số của `just` được tính trước khi gọi phương thức; dùng `fromSupplier` hoặc `defer` nếu cần trì hoãn.
- **Subscribe lại một Stream đã dùng.** Hãy dùng `Flux.fromStream(() -> source.stream())` để tạo stream mới mỗi lần.
- **Hiểu nhầm tham số của `range`.** Tham số thứ hai là số lượng phần tử, không phải giá trị cuối của dãy; hãy tính số phần tử cần phát.
- **Gom một luồng lớn vào List.** `collectList()` giữ toàn bộ phần tử trong bộ nhớ; chỉ dùng khi kích thước dữ liệu phù hợp.

## 10. Bài tập vận dụng

Một dịch vụ cần tạo pipeline để xử lý danh sách mã giao dịch. Dữ liệu đầu vào có thể đến từ một mảng, một `List` được tải từ repository, hoặc một dãy số thứ tự do chương trình sinh ra.

Hãy viết các publisher tương ứng và giải thích lựa chọn:

1. Tạo `Mono` phát một mã giao dịch duy nhất.
2. Tạo `Flux` phát từng mã trong mảng `{"TX-01", "TX-02", "TX-03"}`.
3. Tạo `Flux` phát từng phần tử từ `List.of("TX-04", "TX-05")`.
4. Tạo `Flux` gồm mười số thứ tự bắt đầu từ 100.
5. Tạo một publisher từ supplier để thao tác đọc dữ liệu chỉ chạy khi có subscription.
6. Dùng `StepVerifier` kiểm tra thứ tự các phần tử và tín hiệu hoàn tất.

Sau khi thực hành, hãy tự trả lời: trường hợp nào cần `Mono`, trường hợp nào cần `Flux`; tại sao `Mono.just(list)` khác `Flux.fromIterable(list)`; điều gì xảy ra khi subscribe nhiều lần; và vì sao một `Stream` không thể được dùng lại như một `List`?

Một nguồn được chọn đúng giúp pipeline thể hiện chính xác số lượng phần tử, thời điểm lấy dữ liệu và vòng đời của mỗi subscription.
