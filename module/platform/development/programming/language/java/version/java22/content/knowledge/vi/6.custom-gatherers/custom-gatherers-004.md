# Tín hiệu dừng từ integrator và xử lý downstream từ chối nhận thêm dữ liệu

## Gatherer tùy biến trong Java hiện đại

Stream Gatherers cho phép xây dựng các phép toán trung gian tùy biến trong Stream API. Tính năng được hoàn thiện trong JDK 24 theo JEP 485; các ví dụ trong bài dùng API chính thức từ JDK 24 trở lên, không cần bật preview.

Khi một Gatherer gửi kết quả sang bước kế tiếp, nó cần biết downstream còn nhận dữ liệu hay không. Đồng thời, bản thân Gatherer có thể quyết định đã xử lý đủ dữ liệu đầu vào và không muốn nhận phần tử tiếp theo. Hai tình huống này có liên quan nhưng được biểu diễn bằng hai giá trị `boolean` ở hai phương thức khác nhau:

- `Downstream.push(R)` thực hiện thao tác gửi một phần tử đầu ra xuống bước kế tiếp và trả về liệu downstream còn có thể nhận thêm phần tử hay không.
- `Integrator.integrate(A, T, Downstream)` cho biết integrator có muốn tiếp tục nhận phần tử đầu vào hay không.

Phân biệt hai tín hiệu giúp Gatherer dừng đúng lúc, tránh xử lý thừa và không gửi dữ liệu sau khi bước kế tiếp đã từ chối.

## 1. Hai tín hiệu boolean có ý nghĩa khác nhau

| API | Giá trị `true` | Giá trị `false` |
| --- | --- | --- |
| `downstream.push(result)` | Downstream còn có thể nhận thêm phần tử. | Downstream không nhận thêm phần tử nào nữa; những lần gọi `push` tiếp theo cũng trả về `false`. |
| `integrate(state, element, downstream)` | Gatherer muốn tiếp tục nhận phần tử đầu vào kế tiếp. | Gatherer dừng tích hợp; runtime xem như không còn phần tử đầu vào nào cần chuyển cho integrator đó. |

`push` mô tả trạng thái tiếp nhận của bước phía sau. `integrate` mô tả quyết định tiếp tục hay dừng của Gatherer hiện tại. Không nên dùng hai giá trị này như thể chúng là cùng một tín hiệu.

Lưu ý: `push` trả về `false` không nhất thiết có nghĩa phần tử của lần gọi hiện tại chưa được chuyển tiếp. Giá trị này cho biết downstream không nhận thêm phần tử nào sau lần gọi đó; vì vậy, hãy hiểu nó là tín hiệu về khả năng gửi tiếp.

Một cách hình dung:

```text
Phần tử đầu vào T
       |
       v
Integrator.integrate(state, T, downstream)
       |
       +---- có thể gọi downstream.push(R)
       |              |
       |              +-- true  -> downstream còn nhận được dữ liệu
       |              +-- false -> downstream từ chối dữ liệu tiếp theo
       |
       +---- trả true  -> integrator muốn nhận T kế tiếp
       +---- trả false -> integrator kết thúc việc nhận đầu vào
```

Nếu một Gatherer chỉ chuyển đổi hoặc chuyển tiếp phần tử, kết quả của `push` thường được trả trực tiếp từ integrator. Nếu Gatherer có điều kiện dừng riêng, nó phải kết hợp điều kiện đó với kết quả của `push`.

## 2. Dừng do chính integrator quyết định

Integrator có thể chủ động dừng khi đã đạt mục tiêu của phép biến đổi. Ví dụ, một Gatherer có thể phát phần tử thỏa điều kiện rồi dừng ngay sau phần tử đó. Đây là short-circuit do logic của Gatherer khởi tạo, không phụ thuộc việc downstream có còn nhận dữ liệu hay không.

Ví dụ sau tạo Gatherer phát các phần tử cho đến hết phần tử đầu tiên thỏa `stopAfter`. Phần tử thỏa điều kiện vẫn được gửi xuống downstream:

```java
import java.util.List;
import java.util.Optional;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

static <T> Gatherer<T, Void, T> takeThrough(
        Predicate<? super T> stopAfter) {

    Gatherer.Integrator<Void, T, T> integrator =
        Gatherer.Integrator.of((state, element, downstream) -> {
            // Thử gửi phần tử hiện tại để giữ phần tử dừng trong kết quả.
            if (!downstream.push(element)) {
                return false;
            }

            // Nếu phần tử hiện tại đạt điều kiện, không nhận đầu vào tiếp theo.
            return !stopAfter.test(element);
        });

    return Gatherer.of(integrator);
}

List<Integer> result = Stream.of(2, 4, 6, 7, 8, 10)
    .gather(takeThrough(value -> value >= 7))
    .toList();

// [2, 4, 6, 7]
```

Có hai đường dẫn trả về `false` trong ví dụ:

1. `downstream.push(element)` trả về `false`: bước tiếp theo đã từ chối nhận thêm kết quả, nên Gatherer dừng.
2. `stopAfter.test(element)` trả về `true`: Gatherer đã gửi phần tử dừng và chủ động kết thúc việc nhận đầu vào.

Nếu muốn loại bỏ phần tử làm điều kiện dừng khỏi kết quả, kiểm tra predicate trước khi gọi `push`:

```java
static <T> Gatherer<T, Void, T> takeWhile(
        Predicate<? super T> keep) {

    return Gatherer.of(
        Gatherer.Integrator.of((state, element, downstream) ->
            keep.test(element) && downstream.push(element)
        )
    );
}
```

Với `takeWhile(value -> value < 7)`, phần tử `7` không được gửi xuống downstream và integrator trả về `false` tại phần tử đó. Trong thực tế, hãy ưu tiên `Stream.takeWhile` khi ngữ nghĩa của thao tác chuẩn đã đáp ứng yêu cầu; ví dụ custom Gatherer ở đây minh họa cách điều khiển hai tín hiệu dừng.

Khi integrator có thể tự dừng theo trạng thái hoặc giá trị đầu vào, hãy tạo nó bằng `Gatherer.Integrator.of(...)`. Kiểu này cho runtime biết integrator có thể short-circuit và kết quả boolean của `integrate` cần được xem xét.

## 3. Downstream từ chối nhận thêm kết quả

Downstream là bước tiếp theo trong pipeline. Bước này có thể không cần thêm dữ liệu vì một phép toán phía sau đã đủ kết quả. Những ví dụ thường gặp là:

- `findFirst()` hoặc `findAny()` đã tìm được phần tử cần trả về.
- `anyMatch()` đã tìm thấy phần tử thỏa điều kiện.
- `allMatch()` đã tìm thấy phần tử không thỏa điều kiện.
- `limit(n)` đã nhận đủ số phần tử được yêu cầu.
- Một Gatherer khác ở phía sau đã kết thúc việc nhận đầu vào.

Khi downstream không nhận thêm kết quả, `push` trả về `false`. Nếu Gatherer hiện tại không còn việc gì cần làm sau khi downstream báo không nhận thêm dữ liệu, hãy truyền tín hiệu đó về integrator bằng cách trả về `false`:

```java
static <T> Gatherer<T, Void, T> forward() {
    return Gatherer.of(
        Gatherer.Integrator.of((state, element, downstream) ->
            downstream.push(element)
        )
    );
}

Optional<Integer> first = Stream.of(10, 20, 30, 40)
    .gather(forward())
    .findFirst();

// Optional[10]
```

`findFirst()` chỉ cần phần tử đầu tiên. Khi downstream đã có kết quả, nó có thể từ chối nhận thêm dữ liệu. `forward()` trả lại chính kết quả của `push`, vì vậy Gatherer có thể dừng việc tích hợp đầu vào khi không còn kết quả nào cần chuyển tiếp.

Nếu integrator bỏ qua kết quả `push` và luôn trả `true`, nó đang yêu cầu tiếp tục xử lý đầu vào dù downstream không còn nhận kết quả. Điều này có thể tạo thêm công việc không cần thiết, đặc biệt khi mỗi phần tử phải thực hiện phép biến đổi tốn kém.

## 4. Kiểm tra trạng thái bằng Downstream.isRejecting()

`Downstream.isRejecting()` cho biết theo cách best-effort rằng downstream đã được biết là không muốn nhận thêm phần tử. Phương thức này hữu ích khi Gatherer có thể tránh một phép tính tốn kém trước khi gọi `push`.

```java
static <T, R> Gatherer<T, Void, R> mapGatherer(
        Function<? super T, ? extends R> mapper) {

    return Gatherer.of(
        Gatherer.Integrator.ofGreedy((state, element, downstream) -> {
            // Bỏ qua phép biến đổi nếu đã biết downstream từ chối dữ liệu.
            if (downstream.isRejecting()) {
                return false;
            }

            // Nếu trạng thái từ chối chưa được biết, thử gửi và dùng kết quả thật.
            return downstream.push(mapper.apply(element));
        })
    );
}
```

Có ba điểm cần nhớ về `isRejecting()`:

1. Đây là thông tin best-effort. `true` cho biết downstream đã được biết là từ chối; `false` chỉ có nghĩa là chưa biết downstream đang từ chối.
2. Cài đặt mặc định của phương thức trả về `false`. Vì vậy, không được hiểu `false` là cam kết rằng lần gọi `push` tiếp theo chắc chắn thành công.
3. Với cùng một đối tượng downstream, khi phương thức đã trả về `true` thì không nên kỳ vọng nó quay lại `false`.

`push` vẫn là kết quả xác định của lần gửi cụ thể. Nếu `isRejecting()` trả về `false`, hãy thực hiện `push` khi có kết quả cần gửi và kiểm tra giá trị trả về của nó.

Trong ví dụ trên, mapper được thực hiện sau bước kiểm tra để tránh tính toán khi downstream đã từ chối. `Integrator.ofGreedy` phù hợp vì integrator không tự dừng theo giá trị đầu vào hay trạng thái; nó chỉ phản ánh việc downstream không còn nhận dữ liệu.

## 5. Khi nào dùng Integrator.ofGreedy()

API có hai cách tạo integrator với ý nghĩa khác nhau:

| Factory | Cam kết | Trường hợp phù hợp |
| --- | --- | --- |
| `Integrator.of(...)` | Integrator có thể chủ động trả `false` để short-circuit. Runtime cần xét kết quả `integrate`. | `takeWhile`, `takeThrough`, tìm phần tử đầu tiên theo logic riêng, hoặc Gatherer có giới hạn đầu vào do chính nó quản lý. |
| `Integrator.ofGreedy(...)` | Integrator không tự khởi tạo short-circuit; nó tiêu thụ đầu vào và chỉ có thể phản ánh việc downstream không muốn thêm dữ liệu. | Chuyển tiếp, ánh xạ hoặc xử lý từng phần tử mà không có điều kiện dừng riêng. |

`Integrator.Greedy` là một cam kết ngữ nghĩa để runtime tối ưu. Khi integrator thuộc kiểu này, implementation có thể giả định nó không chủ động short-circuit và không cần kiểm tra giá trị trả về của `integrate`. Vì thế, không dùng `ofGreedy` cho thuật toán có thể dừng khi gặp một giá trị, đạt bộ đếm hoặc hoàn thành một điều kiện nội bộ.

Ví dụ một integrator chuyển tiếp mọi phần tử và chỉ phản ánh trạng thái downstream:

```java
static <T> Gatherer<T, Void, T> relayAll() {
    Gatherer.Integrator.Greedy<Void, T, T> integrator =
        Gatherer.Integrator.ofGreedy(
            (state, element, downstream) -> downstream.push(element)
        );

    return Gatherer.of(integrator);
}
```

Khi cần dừng theo một điều kiện riêng, chuyển sang `Integrator.of`:

```java
Gatherer.Integrator<Void, Integer, Integer> stopAtTen =
    Gatherer.Integrator.of((state, value, downstream) -> {
        if (!downstream.push(value)) {
            return false;
        }

        return value < 10;
    });
```

Ở đây, `10` vẫn được gửi xuống downstream, sau đó integrator trả về `false` để kết thúc. Không được khai báo integrator này là `Greedy`, vì chính nó khởi tạo short-circuit dựa trên giá trị đầu vào.

## 6. Kết hợp hai tín hiệu mà không làm mất dữ liệu

Khi một lần tích hợp vừa có thể phát kết quả vừa có điều kiện dừng, hãy xác định thứ tự xử lý rõ ràng:

1. Quyết định phần tử hiện tại có cần được phát xuống downstream hay không.
2. Nếu cần phát, gọi `push` và kiểm tra kết quả.
3. Nếu `push` trả về `false`, dừng xử lý đầu vào vì downstream không nhận thêm kết quả.
4. Nếu downstream còn nhận dữ liệu, kiểm tra điều kiện dừng của Gatherer.
5. Chỉ trả `true` khi cả downstream còn có thể nhận kết quả và Gatherer vẫn muốn xử lý phần tử tiếp theo.

Với Gatherer phát một kết quả cho mỗi phần tử, biểu thức sau thể hiện quy tắc trên khi phần tử thỏa `stopAfter` vẫn được giữ lại:

```java
return downstream.push(element) && !stopAfter.test(element);
```

Toán tử `&&` đánh giá từ trái sang phải và dừng sớm. Nếu `push` trả về `false`, predicate không cần được gọi nữa. Nếu `push` trả về `true`, kết quả predicate quyết định Gatherer có tiếp tục nhận đầu vào hay không.

Khi một phần tử có thể phát ra nhiều kết quả, phải kiểm tra từng lần `push`:

```java
static <T> Gatherer<T, Void, T> duplicate() {
    return Gatherer.of(
        Gatherer.Integrator.ofGreedy((state, element, downstream) -> {
            if (!downstream.push(element)) {
                return false;
            }

            return downstream.push(element);
        })
    );
}
```

Nếu lần `push` đầu tiên trả về `false`, lần gửi thứ hai không được thực hiện. Nếu lần thứ hai trả về `false`, integrator phản ánh việc downstream từ chối nhận thêm. Đây vẫn là một integrator greedy vì nó không tự dừng theo nội dung phần tử; mọi tín hiệu dừng đều đến từ downstream.

## 7. Finisher và short-circuit

`finisher()` là callback cuối của Gatherer, được dùng để xử lý trạng thái khi kết thúc đầu vào hoặc phát kết quả cuối cùng. Tuy nhiên, không nên dựa vào finisher để phát thêm dữ liệu sau khi integrator đã trả về `false`.

Khi integrator short-circuit, downstream đã dừng nhận thêm kết quả. Tài liệu Core Libraries của Java ghi rõ giá trị mà finisher cố gửi sẽ không được chuyển tiếp nếu integrator đã trả về `false`. Nếu finisher có ý định gửi dữ liệu, cần kiểm tra `downstream.isRejecting()` trước khi thực hiện công việc không cần thiết và vẫn phải kiểm tra kết quả của `push`.

Nếu mục tiêu là phát một kết quả tổng hợp sau khi đã đọc hết đầu vào, hãy để integrator tiếp tục trả `true` cho đến khi upstream kết thúc, rồi phát kết quả trong finisher. Không dùng `return false` để biểu thị rằng đã tính xong một giá trị mà vẫn mong finisher gửi thêm kết quả sau đó.

## 8. Short-circuit trong pipeline song song

Với Gatherer chạy song song, đầu vào có thể được chia thành nhiều phân vùng. Một phân vùng có thể phát hiện điều kiện dừng trong khi phân vùng khác đã bắt đầu hoặc đã xử lý các phần tử của nó.

Kết quả và trạng thái thuộc phần sau của encounter order có thể bị loại bỏ khi một phân vùng trước đó short-circuit. Vì vậy:

- Không dựa vào side effect trong integrator để khẳng định chính xác chỉ những phần tử trước điểm dừng được xử lý.
- Không dùng số lần gọi integrator như một phần của kết quả nghiệp vụ.
- Nếu logic yêu cầu thứ tự dừng dễ dự đoán hoặc có trạng thái phụ thuộc chặt vào thứ tự, cân nhắc Gatherer tuần tự bằng `Gatherer.ofSequential(...)`.
- Nếu dùng song song, bảo đảm combiner và trạng thái từng phân vùng vẫn đúng ngay cả khi một phân vùng dừng sớm.

Short-circuit là cơ chế điều khiển luồng dữ liệu, không phải cam kết rằng mọi công việc đã bắt đầu ở các phân vùng khác sẽ bị hủy tức thì.

## 9. Những lỗi thường gặp

- **Nhầm `push(false)` với `integrate(false)`:** một giá trị mô tả downstream không nhận thêm đầu ra, giá trị còn lại mô tả Gatherer ngừng nhận đầu vào.
- **Bỏ qua kết quả `push`:** Gatherer tiếp tục xử lý hoặc tính toán dù downstream không còn nhận kết quả.
- **Xem `isRejecting() == false` là bảo đảm:** đây chỉ là thông tin best-effort; vẫn phải kiểm tra `push`.
- **Dùng `ofGreedy` cho integrator có điều kiện dừng riêng:** runtime được phép giả định integrator không short-circuit và bỏ qua kết quả `integrate`.
- **Gửi nhiều kết quả mà không kiểm tra từng lần `push`:** sau lần đầu trả về `false`, những lần gửi tiếp theo cũng sẽ thất bại.
- **Cố phát kết quả trong finisher sau khi đã short-circuit:** downstream có thể đã từ chối nhận thêm dữ liệu.
- **Dùng side effect để quan sát chính xác điểm dừng khi chạy song song:** các phân vùng khác có thể đã xử lý thêm dữ liệu.

## Kết luận

Hãy dùng kết quả của `Downstream.push` để biết downstream còn nhận dữ liệu hay không, và dùng kết quả của `Integrator.integrate` để quyết định Gatherer có nhận phần tử đầu vào tiếp theo hay không. `isRejecting()` là gợi ý best-effort để tránh công việc thừa; `Integrator.ofGreedy` là cam kết rằng integrator không tự short-circuit. Khi nắm rõ ba API này, Gatherer có thể phối hợp đúng với các phép toán ngắn mạch trong Stream pipeline và dừng xử lý ở đúng tầng.

## Tài liệu tham khảo

- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)
- [Gatherer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.html)
- [Gatherer.Integrator — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.Integrator.html)
- [Gatherer.Integrator.Greedy — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.Integrator.Greedy.html)
- [Gatherer.Downstream — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [Stream Gatherers — Java SE 26 Core Libraries Guide](https://docs.oracle.com/en/java/javase/26/core/stream-gatherers.html)
