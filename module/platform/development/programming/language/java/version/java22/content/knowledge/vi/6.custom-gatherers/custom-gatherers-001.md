# Các tham số kiểu đầu vào, trạng thái và đầu ra của Gatherer

## Gatherer tùy biến

Trong module `JAVA_VERSION_JAVA22` — học các tính năng được giới thiệu trong Java 22 còn hữu ích ở Java hiện đại — Gatherer là phần mở rộng của Stream API đáng tiếp tục sử dụng. Stream Gatherers xuất hiện dưới dạng preview ở JDK 22, có vòng preview tiếp theo ở JDK 23 và được hoàn thiện thành API chính thức ở JDK 24 theo JEP 485. Vì vậy, các ví dụ trong bài dùng API ổn định từ JDK 24 trở lên; không cần bật preview khi chạy trên các JDK này.

`Gatherer<T, A, R>` mô tả một phép toán trung gian có thể nhận các phần tử từ stream, giữ trạng thái khi cần, rồi phát ra các phần tử cho bước tiếp theo. Một phần tử đầu vào có thể tạo ra không phần tử đầu ra, một phần tử đầu ra hoặc nhiều phần tử đầu ra. Gatherer cũng có thể giữ dữ liệu lại và chỉ phát kết quả khi đã đọc hết đầu vào.

Ba tham số kiểu của `Gatherer` xác định ba vai trò riêng:

```java
public interface Gatherer<T, A, R> {
    // T: kiểu phần tử đầu vào
    // A: kiểu trạng thái trung gian
    // R: kiểu phần tử đầu ra
}
```

| Tham số | Ý nghĩa | Câu hỏi cần trả lời khi thiết kế |
| --- | --- | --- |
| `T` | Kiểu của từng phần tử mà Gatherer nhận từ stream nguồn | Mỗi lần xử lý, tôi nhận loại dữ liệu nào? |
| `A` | Kiểu của trạng thái trung gian mà Gatherer dùng để ghi nhớ thông tin giữa các lần xử lý | Tôi cần lưu lại điều gì để xử lý phần tử tiếp theo? |
| `R` | Kiểu của từng phần tử mà Gatherer gửi xuống bước tiếp theo | Stream kết quả sẽ chứa loại dữ liệu nào? |

`T` và `R` có thể giống hoặc khác nhau. `A` thường là chi tiết triển khai nội bộ; nó không nhất thiết xuất hiện trong stream kết quả.

## 1. T — kiểu phần tử đầu vào

`T` là kiểu phần tử được truyền vào hàm tích hợp (`integrator`). Nếu stream nguồn là `Stream<Employee>`, một Gatherer xử lý trực tiếp các phần tử đó thường có `T` là `Employee`.

Ví dụ, Gatherer nhận chuỗi và phát ra độ dài của chuỗi có thể được khai báo với `T` là `String` và `R` là `Integer`:

```java
static Gatherer<String, Void, Integer> textLength() {
    return Gatherer.of((state, text, downstream) ->
        downstream.push(text.length())
    );
}

List<Integer> lengths = Stream.of("Java", "Gatherer", "Stream")
    .gather(textLength())
    .toList();

// [4, 8, 6]
```

Ở đây, `text` có kiểu `String`, còn giá trị được gửi xuống downstream có kiểu `Integer`. Gatherer không cần giữ dữ liệu giữa các phần tử nên tham số trạng thái là `Void`.

Khi gọi `Stream.gather`, kiểu đầu vào của Gatherer phải có thể nhận các phần tử của stream. Chữ ký API cho phép Gatherer nhận `T` hoặc một kiểu cha của `T` thông qua `Gatherer<? super T, ?, R>`.

## 2. A — kiểu trạng thái trung gian

`A` là kiểu của đối tượng trạng thái mà Gatherer dùng để ghi nhớ thông tin giữa các lần gọi `integrator`. Trạng thái có thể chứa bộ đếm, phần tử trước đó, tập hợp đã gặp, bộ đệm hoặc dữ liệu tích lũy.

Trạng thái được tạo bởi `initializer()`. Mỗi phần tử đầu vào sau đó được xử lý cùng trạng thái hiện tại. Khi Gatherer chạy song song và có combiner phù hợp, mỗi phân vùng đầu vào có thể có trạng thái riêng; các trạng thái đó được kết hợp sau khi xử lý xong phân vùng.

Ví dụ sau tạo một Gatherer tính tổng lũy kế. `A` là `long[]`, dùng một phần tử mảng để lưu tổng hiện tại; `R` là `Long`, kiểu giá trị được phát ra sau mỗi lần cộng:

```java
static Gatherer<Integer, long[], Long> runningTotal() {
    return Gatherer.ofSequential(
        () -> new long[1],
        (state, value, downstream) -> {
            state[0] += value;
            return downstream.push(state[0]);
        }
    );
}

List<Long> totals = Stream.of(2, 3, 4)
    .gather(runningTotal())
    .toList();

// [2, 5, 9]
```

Mỗi lần tích hợp, `state[0]` được cập nhật rồi giá trị mới được gửi xuống downstream. Thứ tự tích lũy ảnh hưởng đến kết quả, vì vậy ví dụ dùng `ofSequential` và không cung cấp hàm kết hợp.

### Khi không cần trạng thái

Nếu phép biến đổi không cần ghi nhớ thông tin giữa các phần tử, dùng `Void` cho `A` và overload `Gatherer.of` nhận trực tiếp một integrator. Ví dụ `textLength()` ở trên là một Gatherer không trạng thái.

Khi khai báo kiểu trả về của một factory, có thể dùng dấu `?` để ẩn kiểu trạng thái khỏi mã gọi:

```java
static <T, R> Gatherer<T, ?, R> mapGatherer(
        Function<? super T, ? extends R> mapper) {
    return Gatherer.of((state, element, downstream) ->
        downstream.push(mapper.apply(element))
    );
}
```

`Void` diễn tả Gatherer không dùng trạng thái; `?` diễn tả mã gọi không cần biết kiểu trạng thái cụ thể. Hai cách viết phục vụ hai mục đích khác nhau.

## 3. R — kiểu phần tử đầu ra

`R` là kiểu phần tử được chuyển đến downstream thông qua `Gatherer.Downstream<? super R>`. Stream trả về từ `gather` có phần tử kiểu `R`.

Một Gatherer có thể phát ra nhiều giá trị `R` trong một lần tích hợp, không phát giá trị nào trong lần đó, hoặc đợi đến `finisher()` mới phát kết quả. Vì thế, không nên hiểu `R` là kiểu trả về của một phép gọi `integrator`; `integrator` điều khiển việc phát ra không, một hay nhiều phần tử `R`.

Ví dụ `textLength()` có `T = String`, `A = Void`, `R = Integer`. Ví dụ `runningTotal()` có `T = Integer`, `A = long[]`, `R = Long`. Hai ví dụ cho thấy kiểu đầu vào, kiểu trạng thái và kiểu đầu ra độc lập với nhau.

Một Gatherer dựng sẵn cũng thể hiện rõ vai trò của `R`. `Gatherers.windowFixed(3)` nhận từng phần tử `Integer` và phát ra các cửa sổ kiểu `List<Integer>`:

```java
Gatherer<Integer, ?, List<Integer>> windows = Gatherers.windowFixed(3);

List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5)
    .gather(windows)
    .toList();

// [[1, 2, 3], [4, 5]]
```

Kiểu trạng thái nội bộ của Gatherer dựng sẵn được ẩn bằng `?`; kiểu đầu ra vẫn được thể hiện rõ là `List<Integer>`.

## 4. Ba tham số kiểu kết nối với bốn hàm của Gatherer

Gatherer được mô tả bởi bốn hàm. Chúng phối hợp để quản lý trạng thái và luồng dữ liệu:

| Hàm | Kiểu hàm | Vai trò |
| --- | --- | --- |
| `initializer()` | `Supplier<A>` | Tạo trạng thái ban đầu. |
| `integrator()` | `Integrator<A, T, R>` | Nhận trạng thái `A`, một phần tử `T` và downstream; cập nhật trạng thái hoặc phát các phần tử `R`. |
| `combiner()` | `BinaryOperator<A>` | Kết hợp hai trạng thái `A` thành một trạng thái `A` khi xử lý song song. |
| `finisher()` | `BiConsumer<A, Downstream<? super R>>` | Thực hiện hành động cuối cùng, có thể phát thêm phần tử `R` sau khi hết đầu vào. |

Luồng xử lý tuần tự có thể hình dung như sau:

1. `initializer()` tạo một trạng thái `A`.
2. Với mỗi phần tử `T`, `integrator()` nhận trạng thái và phần tử đó. Nó có thể cập nhật `A`, gửi một hoặc nhiều `R` xuống downstream, hoặc không gửi gì.
3. Khi upstream kết thúc, `finisher()` có thể sử dụng trạng thái cuối cùng để phát thêm `R`.

`combiner()` được dùng khi Gatherer hỗ trợ xử lý song song. Runtime có thể chia đầu vào thành các phân vùng, tạo trạng thái riêng cho từng phân vùng, tích hợp dữ liệu rồi kết hợp các trạng thái trước khi hoàn tất. Vì vậy, combiner phải thực sự hợp nhất được kết quả trung gian theo đúng ý nghĩa của phép biến đổi. Nếu không thể định nghĩa phép kết hợp đúng, hãy dùng Gatherer tuần tự.

### Ví dụ có combiner và finisher

Gatherer sau tìm giá trị lớn nhất và chỉ phát ra một phần tử khi đã xử lý xong đầu vào. Trạng thái `MaxState` lưu giá trị lớn nhất đã gặp. Combiner hợp nhất hai trạng thái bằng cách lấy giá trị lớn hơn; finisher phát kết quả cuối cùng.

```java
static final class MaxState {
    boolean hasValue;
    int value;

    void accept(int candidate) {
        if (!hasValue || candidate > value) {
            hasValue = true;
            value = candidate;
        }
    }
}

static Gatherer<Integer, MaxState, Integer> maximumOnce() {
    return Gatherer.of(
        MaxState::new,
        (state, value, downstream) -> {
            state.accept(value);
            return true;
        },
        (left, right) -> {
            if (right.hasValue) {
                left.accept(right.value);
            }
            return left;
        },
        (state, downstream) -> {
            if (state.hasValue) {
                downstream.push(state.value);
            }
        }
    );
}

List<Integer> maximum = Stream.of(3, 8, 2, 7)
    .parallel()
    .gather(maximumOnce())
    .toList();

// [8]
```

Ở ví dụ này, `T` và `R` đều là `Integer`, nhưng `A` là `MaxState`. Integrator chỉ cập nhật trạng thái, không phát kết quả ngay. Combiner có thể gộp hai trạng thái vì phép lấy giá trị lớn nhất có thể được thực hiện theo nhiều cách chia nhóm mà vẫn cho cùng kết quả. Finisher phát một giá trị sau khi các trạng thái đã được hợp nhất. Nếu chỉ cần tìm giá trị lớn nhất của stream trong ứng dụng thực tế, `Stream.max` thường là lựa chọn đơn giản hơn; ví dụ này nhằm minh họa vai trò của `A`, `combiner()` và `finisher()`.

## 5. Phân biệt hai giá trị boolean

`Integrator.integrate` và `Downstream.push` đều trả về `boolean`, nhưng chúng trả lời hai câu hỏi khác nhau:

- `downstream.push(result)` trả về `true` nếu downstream còn nhận phần tử; trả về `false` nếu downstream không nhận thêm phần tử nào nữa.
- `integrate(state, element, downstream)` trả về `true` nếu Gatherer muốn tiếp tục nhận phần tử đầu vào; trả về `false` nếu Gatherer muốn dừng tích hợp.

Với Gatherer có thể dừng khi downstream đã đủ dữ liệu, thường nên trả trực tiếp kết quả của `push`, như trong ví dụ chuyển đổi chuỗi hoặc tính tổng lũy kế. Khi integrator trả về `false`, runtime xem như không còn phần tử đầu vào nào cần chuyển cho integrator đó. `Downstream.isRejecting()` cho biết theo cách best-effort rằng bước kế tiếp đã biết là không muốn nhận thêm dữ liệu.

## 6. Chọn cách tạo Gatherer

Các factory method giúp thể hiện rõ Gatherer có trạng thái hay không và có hỗ trợ kết hợp song song hay không:

| Factory | Trường hợp sử dụng |
| --- | --- |
| `Gatherer.of(integrator)` | Gatherer không trạng thái, không cần finisher riêng; có thể chạy song song. |
| `Gatherer.of(integrator, finisher)` | Gatherer không trạng thái nhưng cần hành động cuối; có thể chạy song song. |
| `Gatherer.of(initializer, integrator, combiner, finisher)` | Gatherer có trạng thái và có thể định nghĩa cách kết hợp trạng thái để hỗ trợ song song. |
| `Gatherer.ofSequential(initializer, integrator)` | Gatherer có trạng thái, xử lý tuần tự và không cần finisher riêng. |
| `Gatherer.ofSequential(initializer, integrator, finisher)` | Gatherer có trạng thái, xử lý tuần tự và cần hành động cuối. |

Các overload không nhận finisher dùng finisher mặc định, tức không thực hiện hành động bổ sung ở cuối luồng. Các overload tuần tự dùng combiner mặc định, biểu thị rằng Gatherer chỉ được đánh giá tuần tự.

## 7. Những lỗi thiết kế thường gặp

- **Dùng `R` làm kiểu trạng thái:** `R` là kiểu phần tử được phát xuống downstream; dữ liệu ghi nhớ giữa các lần tích hợp thuộc `A`.
- **Cho rằng một `T` luôn tạo đúng một `R`:** integrator có thể phát không, một hoặc nhiều kết quả, và finisher cũng có thể phát kết quả.
- **Chia sẻ trạng thái giữa các lần chạy:** tạo trạng thái qua `initializer()` thay vì đặt dữ liệu thay đổi trong biến `static` hoặc dùng chung giữa các pipeline. Khi chạy song song, mỗi phân vùng cần trạng thái riêng.
- **Cung cấp combiner không đúng:** combiner phải hợp nhất được hai trạng thái trung gian mà không làm sai kết quả. Không nên thêm combiner chỉ để bật song song nếu phép biến đổi phụ thuộc thứ tự.
- **Giữ lại `state` hoặc `downstream`:** không lưu các tham chiếu này để sử dụng ngoài thời gian gọi callback tương ứng. Gatherer không được giữ hoặc chia sẻ chúng sang thread khác.
- **Nhầm ý nghĩa của `boolean`:** kết quả của `push` nói downstream còn nhận dữ liệu hay không; kết quả của `integrate` nói Gatherer còn muốn nhận đầu vào hay không.

Khi nối các Gatherer bằng `andThen`, kiểu đầu ra `R` của Gatherer trước trở thành kiểu đầu vào mà Gatherer sau phải nhận. Kiểu trạng thái của mỗi Gatherer vẫn độc lập và có thể được ẩn bằng `?`.

## Kết luận

Khi đọc `Gatherer<T, A, R>`, hãy lần lượt xác định dữ liệu đi vào (`T`), thông tin cần giữ giữa các lần xử lý (`A`) và dữ liệu đi ra (`R`). Sau đó chọn cách tạo trạng thái, tích hợp phần tử, kết hợp trạng thái và hoàn tất sao cho đúng với thứ tự và khả năng chạy song song của phép biến đổi. Cách phân biệt này giúp thiết kế Gatherer có kiểu rõ ràng và tránh nhầm lẫn giữa trạng thái nội bộ với dữ liệu của stream kết quả.

## Tài liệu tham khảo

- [Gatherer — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- [Gatherer.Integrator — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html)
- [Gatherer.Downstream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [Gatherers — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)
