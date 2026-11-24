# collect: gom vào cấu trúc dữ liệu và giới hạn bộ nhớ

## collect chuyển một luồng thành một kết quả tổng hợp

Trong Project Reactor, `Flux<T>` biểu diễn một chuỗi có thể phát nhiều phần tử theo thời gian. Các toán tử `collect...` tiêu thụ những phần tử đó, đưa chúng vào một cấu trúc dữ liệu hoặc bộ tích lũy, rồi phát kết quả tổng hợp dưới dạng `Mono`. Ví dụ, `collectList()` biến `Flux<Order>` thành `Mono<List<Order>>`; `collectMap()` tạo một `Map`; `collectMultimap()` nhóm nhiều giá trị theo khóa.

Đây là cách thuận tiện khi cần một kết quả hoàn chỉnh để trả về API, tạo báo cáo, lập chỉ mục hoặc thực hiện phép tính trên một tập dữ liệu hữu hạn. Tuy nhiên, collect có một đặc điểm quan trọng: toán tử phải tích lũy dữ liệu cho đến khi nguồn hoàn tất mới phát cấu trúc kết quả. Nếu nguồn lớn hoặc không bao giờ kết thúc, bộ sưu tập có thể tăng liên tục và chiếm hết bộ nhớ.

Trong module `REACTIVE_PROGRAMMING`, việc dùng `Mono` và `Flux` không chỉ là nối các toán tử. Cần xem xét cả vòng đời nguồn, demand, backpressure và lượng dữ liệu đang được giữ trong bộ nhớ. Vì vậy, khi chọn `collect`, hãy xác định rõ dữ liệu có hữu hạn không, số phần tử tối đa là bao nhiêu, mỗi phần tử có kích thước thế nào và kết quả có cần được giữ toàn bộ hay không.

Các ví dụ dùng `record` để rút gọn mô hình dữ liệu; `record` có từ Java 16. `List.copyOf` có từ Java 10. Nếu dự án dùng Java cũ hơn, thay bằng lớp dữ liệu và cách tạo bản sao danh sách tương ứng.

## Những toán tử collect thường dùng

| Toán tử | Kiểu kết quả | Cách tích lũy | Lưu ý về bộ nhớ |
|---|---|---|---|
| `collectList()` | `Mono<List<T>>` | Giữ tất cả phần tử theo thứ tự phát | Tăng theo tổng số phần tử |
| `collectSortedList()` | `Mono<List<T>>` | Giữ tất cả phần tử rồi sắp xếp | Cần giữ toàn bộ dữ liệu trước khi phát kết quả |
| `collectMap(keyExtractor)` | `Mono<Map<K,T>>` | Lưu một giá trị cho mỗi khóa | Tăng theo số khóa khác nhau; khóa trùng được cập nhật |
| `collectMultimap(keyExtractor)` | `Mono<Map<K, Collection<T>>>` | Lưu nhiều giá trị cho mỗi khóa | Tổng số giá trị vẫn tăng theo số phần tử nguồn |
| `collect(supplier, accumulator)` | `Mono<C>` | Dùng cấu trúc và hàm tích lũy do ứng dụng cung cấp | Giới hạn bộ nhớ phụ thuộc logic accumulator |

Các toán tử trên chỉ phát một kết quả khi nguồn hoàn tất bình thường. Nếu nguồn phát lỗi trước khi hoàn tất, lỗi được truyền xuống và không có collection hoàn chỉnh được phát ra. Với nguồn rỗng, `collectList()` phát một `List` rỗng; nó không hoàn tất bằng `Mono.empty()`.

## Gom toàn bộ phần tử bằng collectList

`collectList()` là lựa chọn đơn giản khi cần giữ tất cả phần tử của một nguồn hữu hạn:

```java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<List<String>> allNames = Flux.just("An", "Bình", "Chi")
    .map(String::toUpperCase)
    .collectList();
```

Khi subscriber đăng ký, `Flux` phát từng tên; `collectList()` thêm mỗi tên vào danh sách nội bộ. Chỉ sau khi nguồn phát `onComplete`, toán tử mới phát `List<String>` cho subscriber của `Mono`. Danh sách giữ thứ tự các phần tử đã được phát.

Đối với nguồn hữu hạn, kích thước đã biết và được kiểm soát, cách này dễ đọc. Ví dụ, tải một trang dữ liệu đã giới hạn từ repository rồi chuyển thành danh sách có thể phù hợp. Ngược lại, không nên áp dụng trực tiếp `collectList()` lên luồng sự kiện dài hạn, message consumer không có điểm kết thúc hoặc `Flux.interval` không giới hạn.

```java
// Nguy hiểm nếu orders là nguồn không giới hạn hoặc có thể rất lớn:
Mono<List<Order>> everyOrder = orderEvents.collectList();
```

Trong trường hợp này, danh sách không được phát cho đến khi nguồn hoàn tất. Nếu nguồn chạy vô hạn, nó không bao giờ hoàn tất và danh sách tiếp tục tích lũy. Backpressure không giải quyết được vấn đề này: dù nguồn tôn trọng demand, `collectList()` vẫn yêu cầu và giữ các phần tử cần thiết để tạo danh sách cuối cùng.

## Gom thành Map bằng collectMap

`collectMap` tạo một ánh xạ từ khóa đến giá trị. Ứng dụng cung cấp hàm lấy khóa và có thể cung cấp thêm hàm chuyển phần tử thành giá trị:

```java
import java.util.Map;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record User(String id, String name) {}

Mono<Map<String, User>> usersById = userSource
    .collectMap(User::id);
```

Nếu muốn giữ một phần dữ liệu làm giá trị, có thể truyền cả hai hàm:

```java
Mono<Map<String, String>> namesById = userSource
    .collectMap(User::id, User::name);
```

Nếu nhiều phần tử có cùng khóa, giá trị được phát sau cùng cho khóa đó thay thế giá trị trước. Vì vậy, `collectMap` phù hợp khi mỗi khóa chỉ cần một giá trị đại diện, chẳng hạn bản ghi mới nhất trong một lô. Nó không phù hợp nếu cần giữ mọi bản ghi trùng khóa.

`collectMap` làm giảm số lượng đối tượng được giữ so với `collectList` khi nhiều phần tử trùng khóa, nhưng nó không tự đặt giới hạn số khóa. Nếu nguồn có hàng triệu khóa khác nhau, `Map` vẫn có thể tăng đến kích thước rất lớn. Hãy xác định giới hạn số khóa, phân trang nguồn hoặc xử lý từng lô nếu dữ liệu không được bảo đảm nhỏ.

## Gom nhiều giá trị theo khóa bằng collectMultimap

`collectMultimap` lưu nhiều giá trị cho một khóa. Ví dụ, gom các dòng đơn hàng theo mã đơn:

```java
import java.util.Collection;
import java.util.Map;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record OrderLine(String orderId, String sku, int quantity) {}

Mono<Map<String, Collection<OrderLine>>> linesByOrder = orderLines
    .collectMultimap(OrderLine::orderId);
```

Khác với `collectMap`, các dòng cùng `orderId` đều được giữ lại trong collection tương ứng. Điều này tiện cho báo cáo hoặc xử lý theo nhóm, nhưng tổng số phần tử vẫn bằng số phần tử nguồn được giữ. Nếu nguồn rất lớn, `collectMultimap` có thể tiêu tốn nhiều bộ nhớ hơn `collectMap` vì không loại bỏ các giá trị trùng khóa.

Chỉ nên gom toàn bộ bằng `collectMultimap` khi nguồn hữu hạn và kích thước nhóm được kiểm soát. Nếu cần xử lý từng nhóm khi dữ liệu tiếp tục đến, cân nhắc `groupBy` hoặc `window` kết hợp xử lý nhóm có giới hạn; không nên đợi toàn bộ nguồn kết thúc mới tạo map nếu nghiệp vụ có thể xử lý theo từng phần.

## Gom rồi sắp xếp bằng collectSortedList

`collectSortedList()` tích lũy toàn bộ phần tử rồi sắp xếp trước khi phát danh sách. Có thể dùng thứ tự tự nhiên hoặc truyền comparator:

```java
import java.util.Comparator;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<List<OrderLine>> sortedLines = orderLines
    .collectSortedList(Comparator.comparing(OrderLine::sku));
```

Toán tử này không phải phép sắp xếp streaming có thể phát phần tử ngay khi thấy một giá trị nhỏ hơn. Muốn bảo đảm thứ tự toàn cục, nó phải biết toàn bộ dữ liệu trước khi phát danh sách. Do đó, bộ nhớ tăng theo số phần tử và thời gian sắp xếp cũng tăng theo kích thước tập dữ liệu.

Nếu dữ liệu quá lớn để giữ trong bộ nhớ, hãy phân trang và sắp xếp ở tầng cơ sở dữ liệu, dùng thuật toán external sort hoặc xử lý theo từng cửa sổ có thứ tự cục bộ nếu nghiệp vụ cho phép. Sắp xếp từng batch không đồng nghĩa với sắp xếp toàn cục toàn bộ nguồn.

## Tùy chỉnh cấu trúc tích lũy bằng collect

Khi các toán tử dựng sẵn không đáp ứng định dạng kết quả, `collect(containerSupplier, accumulator)` cho phép tạo cấu trúc dữ liệu và định nghĩa cách thêm từng phần tử. Supplier tạo container cho subscription; accumulator cập nhật container khi phần tử đến:

```java
import java.util.ArrayList;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<List<String>> normalizedNames = Flux.just("An", "Bình", "Chi")
    .collect(
        ArrayList::new,
        (List<String> result, String name) -> result.add(name.trim().toUpperCase())
    );
```

Container được tạo riêng cho mỗi subscription. Không dùng một `ArrayList` static hoặc một collection dùng chung trong supplier, vì nhiều subscription có thể ghi vào cùng cấu trúc và làm lẫn dữ liệu. Accumulator cũng nên là phép cập nhật đồng bộ, ngắn gọn và không thực hiện I/O chặn.

`collect` không tự giới hạn dung lượng. Nếu accumulator cứ thêm phần tử, collection vẫn tăng không giới hạn. Muốn đặt giới hạn, cần kiểm tra trước khi thêm và định nghĩa rõ điều gì xảy ra khi vượt ngưỡng: phát lỗi, bỏ phần tử, thay thế dữ liệu cũ hoặc ghi ra nơi lưu trữ ngoài bộ nhớ. Không nên âm thầm bỏ dữ liệu nếu nghiệp vụ yêu cầu đầy đủ.

## Đặt giới hạn số phần tử trước khi collect

Một cách đơn giản để bảo vệ `collectList()` là giới hạn số phần tử trước khi gom. Nếu nghiệp vụ yêu cầu tối đa `maxItems` phần tử và phải báo lỗi khi nguồn vượt giới hạn, có thể lấy tối đa `maxItems + 1` để phát hiện trường hợp quá ngưỡng:

```java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<List<Event>> collectAtMost(Flux<Event> source, int maxItems) {
    if (maxItems < 0) {
        return Mono.error(new IllegalArgumentException("maxItems phải không âm"));
    }

    return source
        .take((long) maxItems + 1L)
        .collectList()
        .flatMap(items -> items.size() > maxItems
            ? Mono.error(new IllegalStateException("Số phần tử vượt giới hạn"))
            : Mono.just(List.copyOf(items)));
}
```

Nếu nguồn có không quá `maxItems` phần tử, danh sách được trả về. Nếu có thêm phần tử, toán tử đọc đến phần tử thứ `maxItems + 1`, sau đó `take` hủy upstream và hàm phát lỗi thay vì trả một danh sách bị cắt cụt mà không thông báo. Với `maxItems = 0`, nguồn rỗng trả danh sách rỗng; nguồn có phần tử sẽ bị báo vượt giới hạn.

Giới hạn này bảo vệ số lượng phần tử, không bảo vệ chính xác số byte. Nếu một `Event` có thể chứa payload rất lớn, ngay cả vài trăm phần tử cũng có thể chiếm nhiều bộ nhớ. Khi cần giới hạn theo byte, ứng dụng phải ước lượng kích thước payload, kiểm tra tổng kích thước trong accumulator hoặc giới hạn kích thước từng payload ở tầng nhận dữ liệu.

Nếu yêu cầu nghiệp vụ là chỉ lấy tối đa `maxItems` và chấp nhận bỏ phần còn lại, có thể dùng `source.take(maxItems).collectList()`. Cần thể hiện rõ chính sách này vì `take` hủy upstream sau ngưỡng và danh sách trả về là một phần dữ liệu, không phải toàn bộ nguồn.

## Xử lý theo lô bằng buffer thay vì gom toàn bộ

Khi nguồn có thể lớn hoặc kéo dài, thường nên xử lý từng nhóm có kích thước giới hạn. `buffer(batchSize)` gom tối đa `batchSize` phần tử thành một `List`, phát danh sách đó xuống dưới rồi tiếp tục gom nhóm kế tiếp:

```java
import reactor.core.publisher.Flux;

Flux<Integer> savedBatchSizes = events
    .buffer(500)
    .concatMap(batch -> repository.saveAll(batch)
        .thenReturn(batch.size()), 1);
```

Mỗi batch chứa tối đa 500 phần tử. `concatMap` chỉ xử lý một batch tại một thời điểm, chờ thao tác lưu hoàn tất rồi mới xử lý batch kế tiếp. Nhờ đó, ứng dụng tránh tạo hàng loạt thao tác lưu đồng thời và có thể giải phóng tham chiếu đến batch đã xử lý trước khi tiếp tục. `saveAll` trong ví dụ được giả định trả về `Mono<Void>`; `thenReturn` phát số phần tử đã lưu sau khi thao tác hoàn tất.

Nếu tốc độ nguồn thấp, chờ đủ 500 phần tử có thể làm batch đầu tiên phải đợi lâu. `bufferTimeout(maxSize, maxTime)` phát batch khi đạt kích thước tối đa hoặc khi hết thời gian:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<Integer> savedCounts = events
    .bufferTimeout(500, Duration.ofSeconds(1))
    .concatMap(batch -> repository.saveAll(batch)
        .thenReturn(batch.size()), 1);
```

Với ví dụ này, batch có tối đa 500 phần tử và batch chưa đầy được phát khi cửa sổ thời gian đến hạn. Cách này cân bằng giữa kích thước lô và độ trễ. Nó vẫn không bảo đảm giới hạn byte nếu từng phần tử có kích thước không đồng đều. Khi nguồn hoàn tất, `buffer(500)` và `bufferTimeout(...)` cũng có thể phát batch cuối chưa đủ 500 phần tử trước tín hiệu hoàn tất; các phần tử trong batch cuối không bị loại bỏ chỉ vì nhóm chưa đầy.

Không đặt `collectList()` sau pipeline batch nếu mục tiêu là giải phóng dữ liệu theo từng lô:

```java
// Gom lại mọi batch thành một danh sách lớn, làm mất lợi ích giới hạn bộ nhớ:
Mono<List<List<Event>>> allBatches = events.buffer(500).collectList();
```

Hãy lưu, gửi hoặc tổng hợp từng batch rồi chỉ phát kết quả nhỏ như số bản ghi thành công, mã lô hoặc thống kê. Nếu cần trả về tất cả kết quả chi tiết, hãy cân nhắc phân trang hoặc lưu kết quả vào kho dữ liệu thay vì giữ toàn bộ trong RAM.

## Dùng window để xử lý từng luồng con

`window(maxSize)` chia nguồn thành các `Flux` con, mỗi window chứa tối đa số phần tử được chỉ định. Khác với `buffer`, window phát một publisher con thay vì một `List` đã gom sẵn. Điều này cho phép xử lý các phần tử trong cửa sổ bằng pipeline riêng mà không cần tạo một collection trước:

```java
import reactor.core.publisher.Flux;

Flux<Integer> processedCounts = events
    .window(500)
    .concatMap(window -> window
        .collectList()
        .flatMap(batch -> repository.saveAll(batch)
            .thenReturn(batch.size())), 1);
```

Ở đây, mỗi window có tối đa 500 phần tử; chỉ window hiện tại được thu thành danh sách rồi gửi lưu. `concatMap` tuần tự hóa việc xử lý các window. Tuy nhiên, `collectList()` bên trong window vẫn giữ tối đa một window; nếu tăng kích thước window, bộ nhớ cần thiết cũng tăng.

Window hữu ích khi cần áp dụng các toán tử reactive lên từng nhóm con, ví dụ đếm, lọc hoặc kết hợp sự kiện trong một khoảng. `buffer` thường đơn giản hơn khi chỉ cần một collection để gửi đến API bulk. Cả hai đều cần kích thước cửa sổ hữu hạn nếu muốn kiểm soát lượng dữ liệu tích lũy.

## Reduce: chỉ giữ kết quả tổng hợp thay vì mọi phần tử

Nếu mục tiêu là tính tổng, đếm, tìm giá trị lớn nhất hoặc tạo một thống kê nhỏ, không cần gom mọi phần tử vào danh sách. `reduce` giữ một giá trị tích lũy và cập nhật nó khi phần tử mới đến:

```java
import java.math.BigDecimal;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record PaymentStats(long count, BigDecimal total) {}

Mono<PaymentStats> stats = payments.reduce(
    new PaymentStats(0, BigDecimal.ZERO),
    (current, payment) -> new PaymentStats(
        current.count() + 1,
        current.total().add(payment.amount()))
);
```

Ở đây, bộ tích lũy chỉ giữ số lượng và tổng tiền, nên bộ nhớ phụ thuộc kích thước đối tượng thống kê chứ không phụ thuộc số lượng thanh toán. `reduce` chỉ phát một kết quả sau khi nguồn hoàn tất. Với nguồn rỗng, overload có giá trị khởi tạo phát chính giá trị khởi tạo đó.

Nếu cần phát trạng thái tích lũy sau mỗi phần tử, `scan` có thể phát các giá trị trung gian. Hãy dùng accumulator bất biến hoặc quản lý rõ việc sao chép nếu trạng thái có thể bị quan sát ở nhiều thời điểm. Tránh phát cùng một collection mutable rồi tiếp tục thay đổi nó, vì subscriber có thể nhìn thấy nội dung đã thay đổi sau khi tín hiệu được phát.

## Backpressure không tự giới hạn kích thước collection

Một nhầm lẫn phổ biến là cho rằng Reactive Streams có backpressure nên `collectList()` sẽ tự giữ bộ nhớ ở mức thấp. Backpressure điều tiết số phần tử được phép phát qua subscription; nó không đặt giới hạn tổng số phần tử mà một toán tử tích lũy phải giữ. `collectList()` tiếp tục yêu cầu và lưu dữ liệu cho đến khi nguồn hoàn tất.

Tương tự, `limitRate(100)` điều chỉnh các đợt `request` upstream, nhưng không làm cho `collectList()` chỉ giữ 100 phần tử. Nếu nguồn phát 100.000 phần tử và downstream yêu cầu kết quả cuối, collection vẫn có thể chứa cả 100.000 phần tử.

Để đánh giá bộ nhớ thực tế, cần tính cả:

- Số phần tử trong collection do `collect` giữ.
- Kích thước trung bình và kích thước cực đại của từng phần tử.
- Buffer hoặc prefetch của các toán tử nằm trước và sau điểm gom.
- Số batch hoặc publisher con có thể đang chờ xử lý do concurrency.
- Hàng đợi của client, driver hoặc nguồn sự kiện bên ngoài.

`buffer(500)` giới hạn kích thước từng danh sách ở 500 phần tử, nhưng nếu downstream chậm và có nhiều batch đang xếp hàng, tổng bộ nhớ vẫn có thể tăng. Dùng `concatMap` với prefetch được kiểm soát, giới hạn concurrency và nguồn tôn trọng backpressure để giữ số batch đang hoạt động ở mức dự kiến. Nếu nguồn là hot hoặc adapter không thể tạm dừng phát, cần thêm chính sách overflow rõ ràng như drop, latest, error hoặc một hàng đợi có giới hạn.

## Chọn cách gom theo đặc điểm dữ liệu

| Bài toán | Cách tiếp cận | Giới hạn cần xác định |
|---|---|---|
| Tập hữu hạn nhỏ, cần trả toàn bộ phần tử | `collectList()` | Số phần tử và tổng kích thước dữ liệu |
| Cần một giá trị cho mỗi khóa | `collectMap()` | Số khóa khác nhau và quy tắc xử lý khóa trùng |
| Cần giữ mọi giá trị theo khóa | `collectMultimap()` | Số khóa và tổng số giá trị trong các nhóm |
| Cần sắp xếp toàn bộ tập hữu hạn | `collectSortedList()` | Kích thước tập dữ liệu có thể giữ trong RAM |
| Cần cấu trúc tích lũy riêng | `collect(supplier, accumulator)` | Quy tắc giới hạn và overflow trong accumulator |
| Cần xử lý dữ liệu lớn theo lô | `buffer(size)` hoặc `bufferTimeout(size, time)` | Kích thước batch, thời gian chờ và số batch chờ |
| Cần xử lý từng nhóm như một publisher | `window(size)` | Kích thước window và concurrency xử lý window |
| Chỉ cần số liệu tổng hợp | `reduce()` hoặc `count()` | Kích thước trạng thái tích lũy |

## Quy trình kiểm tra trước khi dùng collect

Trước khi gom một `Flux` thành collection, hãy trả lời các câu hỏi sau:

1. Nguồn có chắc chắn hoàn tất không? Nếu là luồng sự kiện dài hạn, `collect` toàn bộ sẽ không phát kết quả.
2. Số phần tử tối đa là bao nhiêu? Nếu không có giới hạn, hãy đặt cap, phân trang hoặc xử lý theo lô.
3. Mỗi phần tử có thể lớn đến đâu? Giới hạn số lượng không đồng nghĩa giới hạn byte.
4. Có thật sự cần giữ mọi phần tử không? Nếu chỉ cần tổng, số lượng hoặc thống kê, dùng `reduce`/`count`.
5. Dữ liệu có cần xử lý theo nhóm không? Dùng `buffer` hoặc `window` với kích thước hữu hạn.
6. Có bao nhiêu batch hoặc publisher phụ có thể hoạt động đồng thời? Giới hạn concurrency và prefetch để kiểm soát hàng đợi.
7. Khi vượt giới hạn sẽ xảy ra điều gì? Chọn phát lỗi, bỏ dữ liệu theo chính sách, thay thế dữ liệu cũ hoặc ghi ra kho lưu trữ ngoài bộ nhớ.

`collect` là công cụ hữu ích khi kết quả tổng hợp có kích thước dự đoán được. Khi dữ liệu có thể lớn hoặc tiếp tục đến, hãy chọn cách tích lũy có giới hạn, chia batch để xử lý và giải phóng từng phần, hoặc chỉ giữ một trạng thái tổng hợp nhỏ. Quản lý collection cùng demand, buffer và concurrency giúp pipeline Reactor tránh tăng bộ nhớ không kiểm soát mà vẫn giữ được ý nghĩa dữ liệu của nghiệp vụ.
