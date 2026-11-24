# Đánh số phần tử và kết hợp dữ liệu với thông tin vị trí

Trong một luồng reactive, đôi khi giá trị chưa đủ để xử lý nghiệp vụ. Bạn có thể cần biết phần tử đang đứng ở vị trí nào trong luồng, ghép phần tử thứ nhất của nguồn này với phần tử thứ nhất của nguồn khác, hoặc giữ lại vị trí ban đầu khi lọc và xử lý bất đồng bộ. Reactor cung cấp `index()` để gắn số thứ tự cho từng phần tử và `zip`/`zipWith` để kết hợp các nguồn theo thứ tự phát.

Bài học thuộc chương **Biến đổi dữ liệu** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là cách bổ sung thông tin vị trí và kết hợp dữ liệu theo vị trí mà vẫn giữ đúng semantics của từng luồng.

Sau bài học, bạn có thể:

- Đánh số phần tử của `Flux` bằng `index()` và sử dụng chỉ số zero-based.
- Chọn vị trí đặt `index()` để giữ số thứ tự gốc hoặc đánh số lại sau khi lọc.
- Kết hợp các luồng cùng thứ tự bằng `zip` hoặc `zipWith`.
- Hiểu hành vi khi một nguồn ngắn hơn, chậm hơn hoặc không phát dữ liệu.
- Phân biệt vị trí trong một lần subscribe với định danh bền vững của dữ liệu.
- Kiểm thử thứ tự, số thứ tự và việc ghép cặp bằng `StepVerifier`.

## 1. Vì sao cần thông tin vị trí?

Giả sử một luồng chứa các đơn hàng. Ứng dụng có thể cần đánh số dòng khi xuất báo cáo, gắn số thứ tự cho kết quả hiển thị, hoặc ghép từng đơn hàng với một luồng thông tin bổ sung đã được chuẩn bị theo đúng thứ tự. Trong các trường hợp đó, vị trí là metadata của phần tử.

Tuy nhiên, vị trí không giống định danh nghiệp vụ. Chỉ số `0` có thể chỉ phần tử đầu tiên của một lần subscribe, nhưng không chứng minh đó là cùng một đơn hàng ở lần chạy sau. Nếu nguồn thay đổi thứ tự hoặc thêm phần tử, vị trí cũng thay đổi.

Hai thao tác chính trong bài này là:

| Thao tác | Mục đích | Toán tử Reactor |
|---|---|---|
| Gắn vị trí cho từng phần tử | Biến một giá trị `T` thành cặp gồm chỉ số và giá trị | `index()` |
| Ghép các nguồn theo vị trí phát | Kết hợp phần tử thứ n của nguồn này với phần tử thứ n của nguồn khác | `zip`, `zipWith` |

## 2. Đánh số phần tử bằng `index()`

`Flux.index()` phát một `Tuple2<Long, T>` cho mỗi phần tử upstream. Thành phần thứ nhất là chỉ số bắt đầu từ `0`; thành phần thứ hai là giá trị ban đầu.

```java
Flux<String> names = Flux.just("An", "Bình", "Chi");

Flux<Tuple2<Long, String>> numbered = names.index();
```

Luồng kết quả tương đương về mặt dữ liệu với:

| Chỉ số | Giá trị |
|---:|---|
| 0 | An |
| 1 | Bình |
| 2 | Chi |

Bạn có thể đọc hai thành phần bằng `getT1()` và `getT2()`:

```java
numbered.subscribe(tuple -> {
    long position = tuple.getT1();
    String name = tuple.getT2();

    System.out.println(position + ": " + name);
});
```

`index()` đánh số theo thứ tự mà toán tử nhận được các phần tử. Nó không cần thu thập toàn bộ `Flux` vào một danh sách trước khi phát kết quả. Khi một phần tử đi qua toán tử, chỉ số tương ứng được gắn vào phần tử đó.

### Chuyển tuple thành kiểu dữ liệu có tên rõ ràng

Trong code nghiệp vụ, tuple với `getT1()` và `getT2()` đôi khi khó đọc. Bạn có thể chuyển sang một record mô tả ý nghĩa của hai trường:

```java
record Numbered<T>(long position, T value) {}

Flux<Numbered<String>> numberedNames = Flux.just("An", "Bình", "Chi")
    .index()
    .map(tuple -> new Numbered<>(tuple.getT1(), tuple.getT2()));
```

Record giúp tên trường thể hiện ý nghĩa rõ ràng hơn và làm cho các bước sau của pipeline dễ đọc:

```java
numberedNames
    .doOnNext(item -> log.info(
        "Dòng {}: {}", item.position() + 1, item.value()
    ))
    .subscribe();
```

Ở ví dụ này, giá trị `position()` vẫn bắt đầu từ `0`; chỉ khi hiển thị cho người dùng mới cộng thêm `1`. Cách này giữ quy ước zero-based nhất quán trong xử lý dữ liệu và tránh trộn lẫn chỉ số kỹ thuật với số thứ tự hiển thị.

## 3. Đánh số trước hay sau khi lọc?

Vị trí của `index()` trong pipeline quyết định chỉ số biểu diễn điều gì. Nếu đặt `index()` trước `filter`, chỉ số giữ vị trí trong nguồn ban đầu. Nếu đặt sau `filter`, các phần tử còn lại được đánh số lại từ `0`.

```java
Flux<String> source = Flux.just("A", "B", "C", "D");

// Giữ vị trí gốc trong nguồn.
Flux<Tuple2<Long, String>> originalPositions = source
    .index()
    .filter(tuple -> !tuple.getT2().equals("B"));

// Đánh số lại sau khi loại bỏ B.
Flux<Tuple2<Long, String>> compactPositions = source
    .filter(value -> !value.equals("B"))
    .index();
```

Hai kết quả khác nhau:

| Giá trị | `index()` trước `filter` | `index()` sau `filter` |
|---|---:|---:|
| A | 0 | 0 |
| C | 2 | 1 |
| D | 3 | 2 |

Hãy chọn theo ý nghĩa nghiệp vụ:

- **Giữ vị trí gốc:** dùng khi cần truy vết phần tử về vị trí trong dữ liệu đầu vào, ví dụ báo lỗi ở dòng nào của file import.
- **Đánh số lại:** dùng khi cần đánh số danh sách kết quả sau khi lọc, ví dụ hiển thị thứ tự các mục đang được chọn.

Nguyên tắc này cũng áp dụng với các toán tử biến đổi số lượng phần tử. Nếu `flatMap` tạo nhiều kết quả từ một phần tử, đặt `index()` trước `flatMap` sẽ gắn vị trí cho phần tử nguồn; đặt sau `flatMap` sẽ đánh số từng kết quả đã bung ra.

## 4. Kết hợp dữ liệu theo vị trí bằng `zipWith`

`zipWith` kết hợp hai Publisher bằng cách ghép các phần tử theo thứ tự phát: phần tử thứ nhất của nguồn A với phần tử thứ nhất của nguồn B, phần tử thứ hai với phần tử thứ hai, và tiếp tục như vậy.

```java
record Order(String id, long amount) {}
record DeliveryWindow(String slot) {}
record PlannedDelivery(Order order, DeliveryWindow window) {}

Flux<Order> orders = Flux.just(
    new Order("O-101", 120_000),
    new Order("O-102", 250_000)
);

Flux<DeliveryWindow> windows = Flux.just(
    new DeliveryWindow("09:00-11:00"),
    new DeliveryWindow("13:00-15:00")
);

Flux<PlannedDelivery> plan = orders.zipWith(
    windows,
    PlannedDelivery::new
);
```

Kết quả ghép theo vị trí:

| Vị trí | Đơn hàng | Khung giao hàng |
|---:|---|---|
| 0 | O-101 | 09:00-11:00 |
| 1 | O-102 | 13:00-15:00 |

`zipWith` không tìm khóa chung giữa hai phần tử. Nó chỉ ghép theo thứ tự phát. Vì vậy, ví dụ trên đúng khi hai nguồn đã được chuẩn bị sao cho vị trí tương ứng mang cùng ý nghĩa nghiệp vụ.

### Kết hợp chỉ số với một luồng khác

Bạn cũng có thể gắn số thứ tự cho nguồn chính rồi kết hợp với metadata ở cùng vị trí:

```java
record IndexedOrder(long position, Order order) {}
record ExportRow(long position, Order order, String region) {}

Flux<ExportRow> rows = orders
    .index()
    .zipWith(regions, (indexed, region) -> new ExportRow(
        indexed.getT1(),
        indexed.getT2(),
        region
    ));
```

Ở đây, `regions` phải phát vùng tương ứng theo đúng thứ tự với `orders`. Nếu dữ liệu cần ghép theo `orderId`, hãy dùng khóa đó để tra cứu hoặc join ở tầng phù hợp thay vì dựa vào vị trí.

### Dùng `zip` cho nhiều nguồn

`Flux.zip` kết hợp nhiều Publisher cùng lúc. Kết quả thường là tuple chứa một phần tử từ mỗi nguồn:

```java
Flux<Tuple3<Order, Customer, DeliveryWindow>> fullPlan = Flux.zip(
    orders,
    customers,
    windows
);
```

Nếu muốn một kiểu dữ liệu nghiệp vụ, có thể ánh xạ tuple:

```java
record DeliveryPlan(Order order, Customer customer, DeliveryWindow window) {}

Flux<DeliveryPlan> plans = Flux.zip(orders, customers, windows)
    .map(tuple -> new DeliveryPlan(
        tuple.getT1(),
        tuple.getT2(),
        tuple.getT3()
    ));
```

`Mono.zip` cũng có thể kết hợp các kết quả đơn lẻ, chẳng hạn lấy hồ sơ khách hàng và hạn mức tài khoản rồi tạo một DTO. Với `Mono`, nếu một nguồn hoàn tất empty, tổ hợp không thể tạo đủ bộ giá trị nên cũng hoàn tất empty; nếu một nguồn báo lỗi, lỗi được truyền xuống. Với `Flux.zip`, việc ghép tiếp tục cho đến khi không thể tạo thêm một bộ đầy đủ, thường là khi một nguồn hoàn tất và không còn phần tử đã đệm để ghép.

## 5. Điều gì xảy ra khi các nguồn không cùng độ dài?

`zip` chỉ phát một kết quả khi có đủ một phần tử từ mỗi nguồn. Khi một nguồn hoàn tất, không thể tạo thêm bộ ghép sau khi phần tử đã đệm của nguồn đó được dùng hết. Vì vậy, kết quả thường có số phần tử bằng độ dài của nguồn ngắn nhất.

```java
Flux<String> products = Flux.just("Book", "Pen", "Bag");
Flux<Integer> quantities = Flux.just(2, 5);

Flux<String> lines = products.zipWith(
    quantities,
    (product, quantity) -> product + " x " + quantity
);
```

Kết quả chỉ có hai dòng:

```text
Book x 2
Pen x 5
```

`Bag` không có quantity tương ứng nên không tạo được cặp. Nếu nghiệp vụ cần giữ tất cả sản phẩm, hãy xác định rõ giá trị mặc định cho phần thiếu hoặc chuẩn hóa dữ liệu trước khi zip. Không nên giả định `zip` tự điền giá trị mặc định.

Một số trường hợp cần phân biệt:

| Tình huống | Hành vi cần nhớ |
|---|---|
| Một nguồn empty | Không có bộ giá trị đầy đủ; kết quả zip hoàn tất mà không tạo phần tử. |
| Một nguồn error | Kết quả zip kết thúc bằng lỗi. |
| Một nguồn never | Không thể ghép nếu nguồn đó không phát phần tử; pipeline có thể chờ vô hạn nếu không có timeout hoặc cancellation. |
| Một nguồn chậm | Nguồn nhanh có thể phải chờ phần tử tương ứng; zip có thể giữ phần tử đã đến trong hàng đợi nội bộ. |
| Một nguồn ngắn hơn | Sau khi không còn phần tử để ghép, zip kết thúc và hủy các nguồn còn lại theo semantics của operator. |

Khi các nguồn có tốc độ phát rất khác nhau hoặc một nguồn có thể im lặng lâu, hãy cân nhắc timeout, giới hạn prefetch và chính sách lưu dữ liệu. `zip` phù hợp khi cần bộ giá trị đồng bộ theo vị trí; nó không phải công cụ ghép sự kiện theo thời gian hoặc theo khóa nghiệp vụ.

## 6. Thứ tự phát và các toán tử bất đồng bộ

`index()` đánh số theo thứ tự phần tử đi qua vị trí đặt toán tử. Nếu phía sau có xử lý bất đồng bộ và cho phép hoàn tất không theo thứ tự, thứ tự quan sát đầu ra có thể khác thứ tự chỉ số.

Ví dụ:

```java
Flux<IndexedResult> results = source
    .index()
    .flatMap(tuple -> asyncLookup(tuple.getT2())
        .map(value -> new IndexedResult(tuple.getT1(), value)));
```

`flatMap` cho phép các inner Publisher chạy đồng thời. Một phần tử có chỉ số `5` có thể hoàn tất trước phần tử có chỉ số `4`. Chỉ số vẫn cho biết vị trí nguồn, nhưng thứ tự phát kết quả có thể khác thứ tự nguồn.

Nếu cần chạy đồng thời nhưng giữ thứ tự đầu ra theo nguồn, cân nhắc `flatMapSequential`:

```java
Flux<IndexedResult> orderedResults = source
    .index()
    .flatMapSequential(tuple -> asyncLookup(tuple.getT2())
        .map(value -> new IndexedResult(tuple.getT1(), value)), 8);
```

`flatMapSequential` có thể subscribe và thực thi nhiều inner Publisher đồng thời, nhưng phát kết quả theo thứ tự các inner Publisher trong nguồn. Nếu cần thực thi tuần tự từng tác vụ, `concatMap` là lựa chọn khác, đổi lại không có concurrency giữa các inner Publisher.

Không nên dùng chỉ số để che giấu việc mất thứ tự. Nếu nghiệp vụ yêu cầu sắp xếp theo timestamp, sequence number từ hệ thống nguồn hoặc một khóa cụ thể, hãy dùng trường dữ liệu đó và xác định quy tắc xử lý khi dữ liệu đến trễ.

## 7. Vị trí là metadata theo subscription, không phải ID bền vững

`index()` tạo chỉ số cho mỗi lần subscribe. Khi pipeline được subscribe lại, quá trình đánh số bắt đầu lại từ đầu. Nếu nguồn là cold và phát lại cùng dữ liệu, các vị trí có thể giống nhau; nếu nguồn thay đổi, vị trí cũng thay đổi.

Ví dụ:

```java
Flux<Tuple2<Long, String>> indexed = Flux.just("A", "B").index();

indexed.subscribe(System.out::println);
indexed.subscribe(System.out::println);
```

Mỗi subscriber nhận một lần đánh số riêng bắt đầu từ `0`. Điều này hữu ích cho xử lý theo từng lần chạy, nhưng không đủ để tạo ID giao dịch, ID message hoặc khóa lưu trữ lâu dài.

Hãy dùng:

- `index()` cho vị trí tương đối trong một lần phát hoặc một lần xử lý.
- ID nghiệp vụ như `orderId`, `customerId` cho định danh bản ghi.
- Sequence number do nguồn phát cấp khi cần thứ tự ổn định xuyên qua retry, phân vùng hoặc nhiều lần chạy.
- Timestamp cùng quy tắc tie-break khi cần sắp xếp sự kiện theo thời gian.

Nếu cần báo lỗi ở dòng nào trong file import, chỉ số có thể là thông tin phù hợp cho lần import đó. Nếu cần cập nhật lại chính đơn hàng ấy vào ngày mai, hãy dùng ID đơn hàng, không dùng vị trí `17`.

## 8. Backpressure và chi phí của việc kết hợp nguồn

`index()` là phép biến đổi một-một: mỗi phần tử được nhận sẽ tạo một phần tử có thêm chỉ số. Nó không cần gom toàn bộ luồng vào bộ nhớ. Demand downstream tiếp tục được truyền qua toán tử theo cơ chế backpressure của Reactor.

`zip` phải chờ đủ phần tử ở các nguồn để tạo bộ ghép. Vì vậy, nếu một nguồn nhanh hơn nguồn khác, phần tử từ nguồn nhanh có thể được giữ lại trong hàng đợi nội bộ cho đến khi có phần tử tương ứng. Với nguồn có tốc độ chênh lệch lớn, cần để ý prefetch và dung lượng bộ đệm.

Một số nguyên tắc vận hành:

- Không ghép theo vị trí hai nguồn nếu chúng không có cùng quy tắc sắp xếp và cùng ý nghĩa thứ tự.
- Tránh ghép một nguồn nhanh, không giới hạn với một nguồn có thể ngừng phát vô thời hạn mà không có timeout hoặc chính sách hủy.
- Giữ giới hạn concurrency và prefetch phù hợp khi các nhánh có xử lý bất đồng bộ.
- Đo độ trễ, số phần tử đang chờ và số lần timeout khi pipeline phụ thuộc nhiều nguồn.
- Nếu dữ liệu có thể được ghép theo khóa, ưu tiên khóa rõ ràng thay vì đồng bộ hóa ngầm bằng vị trí.

## 9. Kiểm thử đánh số và kết hợp dữ liệu

`StepVerifier` giúp xác nhận chỉ số, thứ tự và hành vi khi một nguồn ngắn hơn.

### Kiểm thử `index()`

```java
StepVerifier.create(Flux.just("A", "B", "C").index())
    .assertNext(tuple -> {
        assertThat(tuple.getT1()).isEqualTo(0L);
        assertThat(tuple.getT2()).isEqualTo("A");
    })
    .assertNext(tuple -> {
        assertThat(tuple.getT1()).isEqualTo(1L);
        assertThat(tuple.getT2()).isEqualTo("B");
    })
    .assertNext(tuple -> {
        assertThat(tuple.getT1()).isEqualTo(2L);
        assertThat(tuple.getT2()).isEqualTo("C");
    })
    .verifyComplete();
```

Các assertion bên trong `assertNext` có thể dùng AssertJ hoặc thư viện assertion mà dự án đang sử dụng. Nếu không dùng AssertJ, thay bằng kiểm tra điều kiện tương đương của framework kiểm thử.

### Kiểm thử `zipWith` khi một nguồn ngắn hơn

```java
StepVerifier.create(
        Flux.just("Book", "Pen", "Bag")
            .zipWith(Flux.just(2, 5), (name, quantity) -> name + quantity)
    )
    .expectNext("Book2", "Pen5")
    .verifyComplete();
```

Kiểm thử xác nhận chỉ có hai cặp được tạo vì nguồn quantity chỉ có hai phần tử.

### Kiểm thử vị trí sau filter

```java
StepVerifier.create(
        Flux.just("A", "B", "C")
            .filter(value -> !value.equals("B"))
            .index()
    )
    .expectNextMatches(tuple -> tuple.getT1() == 0L && tuple.getT2().equals("A"))
    .expectNextMatches(tuple -> tuple.getT1() == 1L && tuple.getT2().equals("C"))
    .verifyComplete();
```

Hãy bổ sung kiểm thử cho trường hợp `index()` đứng trước `filter` nếu ứng dụng cần bảo toàn vị trí gốc. Với pipeline bất đồng bộ, cũng nên kiểm tra rõ liệu đầu ra phải giữ thứ tự hay chỉ cần mang theo chỉ số nguồn.

## 10. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ chỉ số bắt đầu từ `1` | Dùng sai vị trí khi truy cập mảng hoặc đối chiếu dữ liệu. | `index()` bắt đầu từ `0`; chỉ cộng `1` ở tầng hiển thị nếu cần. |
| Đặt `index()` sau `filter` nhưng mong giữ vị trí gốc | Phần tử còn lại được đánh số lại. | Đặt `index()` trước `filter` để giữ chỉ số nguồn. |
| Dùng `zipWith` để join theo ID | Hai phần tử cùng vị trí có thể thuộc hai thực thể khác nhau. | Join theo khóa nghiệp vụ hoặc tra cứu bằng ID. |
| Cho rằng `zip` chờ nguồn dài nhất | Nguồn ngắn hơn khiến không thể tạo thêm bộ ghép. | Chuẩn hóa độ dài hoặc định nghĩa chính sách cho phần thiếu. |
| Dùng `flatMap` rồi giả định đầu ra giữ thứ tự | Inner Publisher có thể hoàn tất không theo thứ tự. | Dùng `flatMapSequential` hoặc `concatMap` khi cần giữ thứ tự. |
| Dùng chỉ số làm định danh lâu dài | Vị trí có thể thay đổi giữa các lần subscribe hoặc khi nguồn thay đổi. | Dùng ID ổn định do nghiệp vụ hoặc nguồn dữ liệu cung cấp. |

## 11. Checklist lựa chọn toán tử

Trước khi đưa thông tin vị trí hoặc kết hợp nhiều nguồn vào pipeline, hãy kiểm tra:

- Chỉ số cần biểu diễn vị trí ban đầu hay vị trí sau khi lọc?
- Vị trí bắt đầu từ `0` hay cần chuyển sang số thứ tự hiển thị từ `1`?
- Hai nguồn có cùng thứ tự và cùng số phần tử không?
- Nếu một nguồn empty, error, never hoặc ngắn hơn, kết quả mong muốn là gì?
- Việc xử lý bất đồng bộ có làm thay đổi thứ tự đầu ra không?
- Vị trí chỉ dùng trong một lần subscribe hay cần định danh bền vững?
- Bộ đệm và prefetch có phù hợp khi tốc độ các nguồn khác nhau không?
- Đã kiểm thử các trường hợp lọc, ghép cặp, nguồn ngắn và thứ tự chưa?

Khi hiểu đúng `index()` và `zipWith`, bạn có thể bổ sung vị trí cho từng phần tử, kết hợp dữ liệu theo thứ tự có chủ đích và giữ được khả năng truy vết trong pipeline `Flux`. Điều quan trọng là luôn gắn ý nghĩa nghiệp vụ rõ ràng cho vị trí, đồng thời kiểm soát độ dài, tốc độ và thứ tự của các nguồn tham gia kết hợp.
