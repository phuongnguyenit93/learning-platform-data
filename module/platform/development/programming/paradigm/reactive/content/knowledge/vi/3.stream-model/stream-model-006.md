# Đọc sơ đồ marble để mô tả dữ liệu, thời gian và kết thúc

Trong lập trình reactive, một pipeline không chỉ biến đổi các giá trị. Nó còn quyết định giá trị nào được phát, chúng xuất hiện theo trình tự và nhịp thời gian nào, và luồng kết thúc ra sao. **Sơ đồ marble (marble diagram)** biểu diễn những điều đó bằng một trục thời gian và các ký hiệu ngắn gọn. Nhờ vậy, ta có thể nhìn thấy tác động của một toán tử trước khi đọc hoặc viết mã.

Đây là kỹ năng nền tảng trong chương **Mô hình luồng** của REACTIVE_PROGRAMMING. Module học cách xử lý các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; sau đó thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi đọc sơ đồ marble, hãy luôn theo dõi đồng thời ba câu hỏi: dữ liệu nào đi qua, thời điểm tương đối của từng lần phát thay đổi thế nào, và tín hiệu kết thúc nào được gửi đến Subscriber.

## Cấu trúc cơ bản của sơ đồ marble

Một sơ đồ marble thường có đường ngang biểu diễn một luồng và các hình tròn hoặc nhãn trên đường đó biểu diễn những phần tử được phát. Thời gian tiến từ trái sang phải. Các ký hiệu kết thúc thường nằm ở cuối đường. Không có một quy ước hình ảnh duy nhất được mọi tài liệu sử dụng; vì vậy, trước khi đọc sơ đồ trong tài liệu hoặc thư viện cụ thể, hãy xem phần chú giải (legend) của nó.

Trong các ví dụ của bài này, ta dùng quy ước sau:

| Ký hiệu | Ý nghĩa |
|---|---|
| `──` | Dòng thời gian; đoạn dài hơn biểu thị khoảng cách tương đối dài hơn trong hình |
| `(A)` | Một phần tử có giá trị `A` được phát (`onNext`) |
| `\|` | Luồng hoàn tất bình thường (`onComplete`) |
| `X` | Luồng kết thúc bằng lỗi (`onError`) |
| `↓ cancel` | Subscriber hủy subscription upstream; đây là chú thích về điều khiển, không phải phần tử dữ liệu |
| `...` | Phần tiếp diễn được lược bỏ hoặc không xác định trong hình |

Ví dụ một luồng phát ba giá trị rồi hoàn tất:

```text
thời gian ───────────────────────────────────────────────►
source    ──(A)────(B)──(C)───────────────────────────────|
```

Ta đọc từ trái sang phải: nguồn phát `A`, sau đó `B`, rồi `C`, cuối cùng gửi tín hiệu hoàn tất. Khoảng cách giữa các phần tử cho thấy nhịp tương đối được minh họa; nó không mặc định là số mili giây chính xác. Nếu sơ đồ không ghi thang thời gian, không thể kết luận `A` cách `B` đúng một giây chỉ dựa vào độ dài đoạn thẳng.

Một sơ đồ có thể vẽ nhiều đường để so sánh nguồn đầu vào với kết quả đầu ra của toán tử:

```text
source    ──(1)────(2)────(3)────────────────────────────|
map(x10)  ──(10)───(20)───(30)───────────────────────────|
```

Hai đường được căn theo trục thời gian. `map(x10)` biến đổi từng giá trị nhưng trong ví dụ này không chủ ý thêm độ trễ, bỏ phần tử hay đổi thứ tự. Khi so sánh hai đường, hãy kiểm tra cả giá trị và vị trí phát, không chỉ nhìn danh sách kết quả.

## Đọc dữ liệu: phần tử được giữ, đổi hoặc loại bỏ

Các toán tử biến đổi dữ liệu thường được mô tả bằng cách đối chiếu đường nguồn và đường kết quả.

### `map`: thay giá trị của từng phần tử

`map` áp dụng một hàm lên từng phần tử. Nếu hàm trả về bình thường, mỗi phần tử đầu vào tạo ra một phần tử đầu ra tương ứng:

```text
source      ──(1)────(2)────(3)──────────────────────────|
map(n * 2)  ──(2)────(4)────(6)──────────────────────────|
```

Số lượng và thứ tự phần tử được giữ nguyên trong ví dụ; giá trị thay đổi theo hàm. `map` không tự tạo một luồng song song. Nếu hàm ánh xạ ném exception, pipeline chuyển sang kết thúc bằng lỗi tại phần tử đó và không tiếp tục phát các phần tử phía sau của subscription.

```java
import reactor.core.publisher.Flux;

Flux<Integer> doubled = Flux.just(1, 2, 3)
    .map(number -> number * 2);
```

### `filter`: chỉ giữ phần tử thỏa điều kiện

`filter` bỏ những phần tử không thỏa predicate. Các phần tử được giữ lại vẫn theo thứ tự nguồn:

```text
source          ──(1)────(2)────(3)────(4)──────────────|
filter(even)    ─────────(2)───────────(4)──────────────|
```

Khoảng trống tại vị trí `1` và `3` cho biết không có phần tử đầu ra tương ứng. Nó không có nghĩa pipeline phát một giá trị rỗng (`null`). Trong Reactive Streams, `null` không phải phần tử hợp lệ của tín hiệu `onNext`.

```java
Flux<Integer> evenNumbers = Flux.range(1, 4)
    .filter(number -> number % 2 == 0);
```

### `take`: giới hạn số phần tử và kết thúc sớm

`take(2)` chỉ chuyển tối đa hai phần tử đầu tiên xuống downstream rồi hoàn tất luồng kết quả:

```text
source       ──(A)────(B)────(C)────(D)───────────────►
take(2)      ──(A)────(B)────| 
                              ↓ cancel upstream
```

Điểm quan trọng là hai sự việc khác nhau diễn ra ở hai phía của toán tử. Downstream nhận `onComplete` sau phần tử thứ hai; toán tử đồng thời hủy subscription upstream để không cần nhận thêm dữ liệu. Một số sơ đồ chỉ vẽ đường kết quả kết thúc mà bỏ qua mũi tên hủy. Vì vậy, không nên suy luận rằng nguồn gốc đã tự phát `onComplete` đúng tại vị trí đó.

```java
Flux<String> firstTwo = Flux.just("A", "B", "C", "D")
    .take(2);
```

## Đọc thời gian: thứ tự, khoảng cách và độ trễ

Trục ngang thể hiện thứ tự và quan hệ thời gian giữa các tín hiệu. Có ba điều cần phân biệt:

1. **Thứ tự:** phần tử nào được phát trước và phần tử nào được phát sau.
2. **Khoảng cách tương đối:** các lần phát cách nhau gần hay xa theo cách vẽ.
3. **Thời lượng thực:** bao nhiêu mili giây hoặc giây đã trôi qua. Chỉ kết luận được điều này nếu sơ đồ có thang thời gian hoặc ghi chú cụ thể.

Ví dụ, hai sơ đồ dưới đây đều phát `A`, `B`, `C` theo cùng thứ tự nhưng minh họa nhịp khác nhau:

```text
nhịp đều       ──(A)──(B)──(C)──────────────────────────|
nhịp không đều ──(A)────────(B)─(C)─────────────────────|
```

Sơ đồ không đều cho thấy khoảng chờ giữa `A` và `B` dài hơn khoảng chờ giữa `B` và `C`. Nếu không có chú giải về thang đo, đây chỉ là so sánh tương đối.

### `delayElements`: dịch thời điểm phát về sau

Toán tử `delayElements` trì hoãn việc phát từng phần tử. Sơ đồ kết quả thể hiện các phần tử xuất hiện muộn hơn so với nguồn:

```text
source                 ──(A)──(B)──(C)──────────────────|
delayElements(200 ms)  ────────(A)──(B)──(C)────────────|
```

Đây là hình minh họa khái niệm: mỗi phần tử đầu ra được phát sau khoảng trễ cấu hình. Độ trễ quan sát thực tế còn chịu ảnh hưởng của scheduler và tải hệ thống; sơ đồ không phải cam kết thời gian thực chính xác.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<String> delayed = Flux.just("A", "B", "C")
    .delayElements(Duration.ofMillis(200));
```

### `interval`: nguồn tự phát theo nhịp thời gian

`Flux.interval` tạo các giá trị đếm theo khoảng thời gian. Đây là ví dụ về nguồn mà thời điểm phát là một phần của hành vi:

```text
thời gian (mỗi nhịp 1 giây) ────────────────────────────►
interval                    ──(0)──(1)──(2)──(3)── ...
```

Nguồn này thường tiếp tục cho đến khi subscription bị hủy hoặc có điều kiện kết thúc khác. Nếu Subscriber xử lý chậm, không nên mặc định rằng hình minh họa đơn giản đã mô tả đầy đủ cách scheduler, hàng đợi và nhu cầu `request(n)` tương tác. Cần đọc cả hợp đồng nguồn và chính sách backpressure của pipeline.

## Đọc tín hiệu kết thúc: hoàn tất, lỗi và hủy

Một luồng Reactive Streams không chỉ phát dữ liệu. Nó còn có tín hiệu kết thúc để Subscriber biết nguồn đã dừng theo cách nào. Hai kết thúc do Publisher gửi là `onComplete` và `onError`; Subscriber có thể chủ động hủy bằng `cancel`.

### Hoàn tất bình thường (`onComplete`)

```text
finite source ──(A)────(B)──────────────────────────────|
```

Ký hiệu `|` biểu thị Publisher đã hoàn tất bình thường. Có thể có nhiều phần tử trước đó hoặc không có phần tử nào. Ví dụ `Flux.empty()` hoàn tất mà không phát `onNext`:

```text
Flux.empty()  ──────────────────────────────────────────|
```

Vì vậy, một đường không có marble dữ liệu nhưng có `|` là luồng rỗng đã hoàn tất, không phải luồng đang chờ mãi.

### Kết thúc do lỗi (`onError`)

```text
source        ──(A)────(B)──────────────────────────────X
```

Ký hiệu `X` biểu thị Publisher gửi `onError`. Các phần tử đã phát trước lỗi vẫn đã được Subscriber quan sát; sau lỗi, subscription đó không nhận thêm `onNext` hoặc `onComplete`. Lỗi là tín hiệu kết thúc, không phải một phần tử dữ liệu nằm trong luồng.

Ví dụ một pipeline có thể lỗi khi hàm `map` không xử lý được đầu vào:

```java
Flux<Integer> values = Flux.just(1, 2, 0, 4)
    .map(number -> 10 / number);
```

Trong ví dụ này, phép chia cho `0` ném `ArithmeticException`. Pipeline phát kết quả của các phần tử trước đó, sau đó kết thúc bằng lỗi tại phép tính gây exception; phần tử `4` phía sau không được xử lý trong subscription đó.

### Hủy subscription (`cancel`)

Hủy là hành động của Subscriber thông qua Subscription để báo rằng nó không muốn nhận thêm dữ liệu. `cancel` không phải một tín hiệu kết thúc mà Publisher gửi xuống như `onComplete` hoặc `onError`. Vì thế, sơ đồ chi tiết có thể biểu diễn nó bằng mũi tên từ downstream hướng về upstream:

```text
Publisher    ──(A)────(B)────(C)────(D)───────────────►
                         │
Subscriber   ── nhận A, B ┘
                         ↑ cancel gửi về upstream
```

Sau khi hủy, Publisher cần ngừng phát thêm cho subscription đó theo hợp đồng. Subscriber không nên chờ `onComplete` như một xác nhận cho thao tác hủy. Trong sơ đồ giản lược, đường có thể chỉ dừng lại mà không có `|` hay `X`; hãy xem chú giải để biết đó là hủy, phần hình bị lược bỏ hay nguồn chưa phát thêm.

## Phân biệt luồng rỗng, luồng chưa phát và luồng chưa kết thúc

Ba trường hợp có thể trông giống nhau nếu chỉ nhìn một đoạn đường ngang, nhưng mang ý nghĩa khác nhau:

| Trường hợp | Sơ đồ khái niệm | Ý nghĩa |
|---|---|---|
| Rỗng và hoàn tất | `────────────────|` | Không có phần tử, kết thúc bình thường |
| Chưa phát tín hiệu | `────────────────` | Trong khoảng được vẽ chưa quan sát thấy dữ liệu hoặc kết thúc; chưa đủ căn cứ kết luận |
| Không bao giờ phát hay kết thúc | `Flux.never()` | Không phát `onNext`, `onComplete` hoặc `onError` |
| Liên tục | `──(0)──(1)──(2)──...` | Còn phát dữ liệu; phần tiếp diễn được biểu diễn bằng dấu ba chấm |

`Flux.never()` hữu ích khi cần biểu diễn hoặc kiểm thử một Publisher không phát tín hiệu nào. Nó khác `Flux.empty()`: nguồn rỗng kết thúc ngay, còn nguồn never không kết thúc. Một đoạn sơ đồ bị cắt ở mép trang cũng không chứng minh nguồn là vô hạn; có thể chỉ là người vẽ không hiển thị phần còn lại.

## Đọc sơ đồ của các toán tử kết hợp nguồn

Khi pipeline có nhiều nguồn, cần xem sơ đồ của từng nguồn và cách toán tử sắp xếp các tín hiệu đầu ra.

### `concat`: tiêu thụ lần lượt

`concat` chờ nguồn trước hoàn tất rồi mới chuyển sang nguồn tiếp theo:

```text
source A  ──(A1)────(A2)──|
source B  ───────────────────(B1)────(B2)──|
concat    ──(A1)────(A2)────(B1)────(B2)──|
```

Các giá trị của nguồn B chỉ xuất hiện sau khi A hoàn tất. Nếu A không bao giờ kết thúc, B có thể không được đăng ký hoặc tiêu thụ. Đây là hệ quả thời gian quan trọng của việc nối tuần tự.

### `merge`: cho phép các nguồn xen kẽ

`merge` kết hợp các tín hiệu theo thời điểm chúng đến từ các nguồn:

```text
source A  ──(A1)────────────(A2)──────────────|
source B  ───────(B1)──(B2)───────────────────|
merge     ──(A1)─(B1)──(B2)──(A2)─────────────|
```

Trong hình minh họa, B phát `B1` và `B2` trong lúc A đang chờ nên các phần tử xen kẽ. Với nguồn bất đồng bộ thực tế, thứ tự xen kẽ phụ thuộc thời điểm phát; không nên giả định một thứ tự cố định nếu không có cơ chế đồng bộ hoặc dữ liệu sequence rõ ràng.

## Cách đọc một sơ đồ marble theo từng bước

Khi gặp sơ đồ mới, hãy đọc theo trình tự sau để tránh bỏ sót ý nghĩa:

1. **Đọc chú giải:** xác định ký hiệu phần tử, lỗi, hoàn tất, hủy, subscription và trục thời gian.
2. **Xác định nguồn:** có bao nhiêu Publisher, mỗi nguồn phát kiểu dữ liệu gì và có hữu hạn hay không.
3. **Theo dõi từng phần tử:** ghi lại giá trị, thứ tự và vị trí tương đối trước khi qua toán tử.
4. **So sánh đầu vào và đầu ra:** xác định phần tử nào được biến đổi, giữ lại, loại bỏ, trì hoãn hoặc xen kẽ.
5. **Tìm tín hiệu kết thúc:** kiểm tra đầu ra hoàn tất, lỗi hay bị hủy; không nhầm hủy upstream với `onComplete` downstream.
6. **Kiểm tra giới hạn của hình:** xem có thang thời gian không, phần nào bị lược bỏ, và hình có biểu diễn `request(n)` hay backpressure không.

Một sơ đồ marble có thể tóm tắt hành vi của toán tử nhưng không nhất thiết thể hiện tất cả chi tiết triển khai. Nếu hình không vẽ luồng yêu cầu, hàng đợi hoặc scheduler, đừng suy diễn rằng nó đã mô tả những khía cạnh đó.

## Từ sơ đồ sang mã Reactor và kiểm thử

Sơ đồ giúp hình thành dự đoán về pipeline; mã và kiểm thử xác nhận dự đoán đó. Ví dụ, từ sơ đồ `filter` rồi `take`, ta dự đoán chỉ các số chẵn đầu tiên được phát và luồng kết thúc sau khi lấy đủ hai số:

```text
source       ──(1)──(2)──(3)──(4)──(5)──(6)──────────►
filter even  ───────(2)──────(4)──────(6)─────────────►
take(2)      ───────(2)──────(4)──|
```

```java
import reactor.core.publisher.Flux;

Flux<Integer> firstTwoEven = Flux.range(1, 6)
    .filter(number -> number % 2 == 0)
    .take(2);
```

Có thể kiểm tra kết quả bằng `StepVerifier` trong dự án có dependency `reactor-test`:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class MarbleBehaviorTest {
    @Test
    void emitsFirstTwoEvenNumbersThenCompletes() {
        Flux<Integer> result = Flux.range(1, 6)
            .filter(number -> number % 2 == 0)
            .take(2);

        StepVerifier.create(result)
            .expectNext(2, 4)
            .verifyComplete();
    }
}
```

`expectNext(2, 4)` xác nhận dữ liệu và thứ tự; `verifyComplete()` xác nhận tín hiệu kết thúc. Nếu sơ đồ dự đoán lỗi, dùng `expectError(...)` hoặc `expectErrorMatches(...)` để xác nhận loại lỗi. Với pipeline dựa trên thời gian, `StepVerifier.withVirtualTime` cho phép kiểm thử các mốc thời gian mà không phải chờ đồng hồ thực chạy hết khoảng trễ; khi đó cần tạo Publisher bên trong supplier được truyền cho verifier để virtual scheduler được áp dụng đúng.

## Những lỗi thường gặp khi đọc sơ đồ

**Coi khoảng cách hình vẽ là thời lượng chính xác.** Trừ khi có thang thời gian hoặc chú giải, độ dài chỉ biểu diễn quan hệ tương đối.

**Coi khoảng trống là giá trị null.** Khoảng trống thường có nghĩa không có phần tử được phát tại vị trí đó, chẳng hạn vì `filter` loại bỏ phần tử.

**Nhầm `|` với `X`.** `|` là hoàn tất bình thường; `X` là kết thúc do lỗi. Hai tín hiệu này loại trừ nhau trong một subscription.

**Nhầm hủy với hoàn tất.** `cancel` là yêu cầu từ Subscriber gửi về upstream. `onComplete` là tín hiệu Publisher gửi đến Subscriber. Một toán tử như `take` có thể hoàn tất downstream đồng thời hủy upstream.

**Cho rằng đường kết thúc đồng nghĩa nguồn đã phát hết dữ liệu.** Đường downstream có thể kết thúc sớm vì `take`, timeout hoặc hủy. Hãy xác định đường nào đang được vẽ và tín hiệu đến từ phía nào.

**Suy ra song song hoặc backpressure từ hình không thể hiện chúng.** Sơ đồ marble cơ bản mô tả phần tử và thời gian. Muốn kết luận về scheduler, số luồng hoặc nhu cầu `request(n)`, cần thêm ký hiệu hay thông tin tương ứng.

## Tự kiểm tra

1. Trên sơ đồ, nguồn phát `(A)`, `(B)`, `(C)` rồi có ký hiệu `|`. Subscriber nhận được những gì và luồng kết thúc thế nào?
2. Một sơ đồ `filter` có khoảng trống tại vị trí phần tử đầu vào bị loại bỏ. Vì sao khoảng trống đó không biểu diễn `null`?
3. Nếu đường nguồn tiếp tục có `(C)` và `(D)` nhưng đường `take(2)` đã có `|`, điều gì xảy ra với subscription upstream?
4. Phân biệt hai sơ đồ kết thúc bằng `|` và `X`. Subscriber có thể mong đợi tín hiệu nào trong mỗi trường hợp?
5. Hai nguồn A và B được kết hợp bằng `merge`. Vì sao thứ tự xen kẽ trong sơ đồ không phải cam kết về thứ tự cố định ở mọi lần chạy?
6. Một đường ngang không có marble và cũng chưa có ký hiệu kết thúc. Có thể kết luận Publisher đã hoàn tất không? Vì sao?

Khi đọc được dữ liệu, trục thời gian và tín hiệu kết thúc trên cùng một sơ đồ, bạn có thể dự đoán hành vi của các toán tử Reactor, nhận ra khác biệt giữa hoàn tất và hủy, rồi chuyển dự đoán đó thành kiểm thử pipeline có ý nghĩa.
