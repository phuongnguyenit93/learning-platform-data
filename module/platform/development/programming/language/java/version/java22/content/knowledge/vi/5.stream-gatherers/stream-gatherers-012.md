# Chuyển ví dụ preview Java 22 sang API Gatherers chính thức trên JDK mới

Stream Gatherers mở rộng Stream API bằng các intermediate operation do lập trình viên định nghĩa. Một Gatherer có thể giữ trạng thái giữa các phần tử, gom nhiều phần tử thành một kết quả, phát ra nhiều kết quả cho mỗi đầu vào, dừng xử lý sớm hoặc phối hợp xử lý song song. Đây là công cụ phù hợp khi `map`, `filter`, `flatMap` và các phép toán Stream có sẵn không diễn đạt được một bước xử lý trạng thái cần thiết.

Tính năng này xuất hiện dưới dạng preview trong JDK 22 qua JEP 461, được preview lần thứ hai trong JDK 23 qua JEP 473 và trở thành API chính thức trong JDK 24 qua JEP 485. Từ JDK 24 trở lên, `Gatherer`, `Gatherers` và `Stream.gather` là API chuẩn; mã chỉ sử dụng Gatherers không cần bật preview. Các ví dụ trong bài dùng API ổn định có từ JDK 24 và vẫn áp dụng trên JDK mới hơn.

## 1. Xác định phần cần chuyển khi nâng cấp

| Phiên bản | Trạng thái Stream Gatherers | Điều cần lưu ý |
| --- | --- | --- |
| JDK 22 — JEP 461 | Preview lần đầu | Khi biên dịch và chạy mã dùng Gatherers phải bật preview của JDK 22. |
| JDK 23 — JEP 473 | Preview lần thứ hai | API được giữ nguyên so với preview JDK 22. |
| JDK 24 — JEP 485 | Chính thức | Có thể dùng API mà không bật preview. |
| JDK 25 trở lên | API chuẩn | Dùng trực tiếp trong ứng dụng và thư viện Java hiện đại. |

Với mã nguồn chỉ sử dụng Stream Gatherers, thay đổi quan trọng nhất khi chuyển sang JDK 24+ là cấu hình biên dịch và chạy. Những kiểu API chính như `Gatherer`, `Gatherers`, `Gatherer.Integrator` và `Stream.gather` vẫn là mô hình lập trình cần dùng. Tuy nhiên, hãy biên dịch lại từ mã nguồn trên JDK mới; class file được tạo cho preview của một phiên bản JDK không phải artifact có thể mang sang phiên bản khác để chạy như class file thông thường.

Ví dụ cấu hình cho mã preview JDK 22:

```bash
# Biên dịch mã preview của JDK 22
javac --release 22 --enable-preview StreamExample.java

# Chạy trên JDK 22 với preview được bật
java --enable-preview StreamExample
```

Sau khi chuyển sang API chính thức trên JDK 24 trở lên:

```bash
# Biên dịch bằng JDK 24 trở lên, không cần --enable-preview
javac --release 24 StreamExample.java

# Chạy như ứng dụng Java thông thường
java StreamExample
```

Nếu dự án còn dùng tính năng preview khác, chỉ có thể bỏ `--enable-preview` sau khi các tính năng đó cũng đã được chuyển sang API chính thức hoặc được loại bỏ. Khi nâng cấp thư viện, hãy kiểm tra cả cấu hình compiler, test runner, plugin build, IDE và JVM ở môi trường triển khai.

## 2. Giữ cách gọi Stream.gather và dùng Gatherers chuẩn

Gatherer là intermediate operation: nó nhận phần tử từ upstream, có thể giữ trạng thái và gửi kết quả xuống downstream. `Stream.gather(gatherer)` tạo ra một stream mới, vì vậy có thể nối Gatherer với các thao tác Stream khác và kết thúc bằng terminal operation như `toList()`.

Ví dụ gom phần tử thành các cửa sổ cố định:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FixedWindowExample {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
                .gather(Gatherers.windowFixed(3))
                .toList();

        System.out.println(windows);
        // [[1, 2, 3], [4, 5, 6], [7, 8]]
    }
}
```

`windowFixed(3)` chia phần tử theo encounter order thành từng nhóm ba phần tử. Nhóm cuối có thể ít hơn ba phần tử. Các danh sách cửa sổ được trả về là unmodifiable; nếu cần thay đổi nội dung, hãy tạo bản sao như `new ArrayList<>(window)`.

Nếu mỗi cửa sổ kế tiếp phải dịch đi một phần tử, dùng `windowSliding`:

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Với stream ngắn hơn kích thước cửa sổ, `windowSliding` tạo một cửa sổ chứa toàn bộ phần tử hiện có. Cả `windowFixed` và `windowSliding` yêu cầu `windowSize` lớn hơn hoặc bằng 1.

## 3. Chọn đúng Gatherer dựng sẵn

JDK cung cấp lớp tiện ích `Gatherers` với các phép biến đổi phổ biến. Nên ưu tiên các implementation dựng sẵn khi ngữ nghĩa của chúng đã đáp ứng yêu cầu:

| API | Hành vi | Trường hợp sử dụng |
| --- | --- | --- |
| `Gatherers.windowFixed(size)` | Chia stream thành các cửa sổ liên tiếp, không chồng lấp. | Xử lý dữ liệu theo lô cố định. |
| `Gatherers.windowSliding(size)` | Tạo cửa sổ trượt, mỗi cửa sổ kế tiếp bỏ phần tử cũ nhất và nhận phần tử mới. | Tính toán trên các khoảng dữ liệu liên tiếp. |
| `Gatherers.scan(initial, scanner)` | Phát ra từng giá trị tích lũy sau mỗi đầu vào. | Tổng lũy kế, trạng thái tích lũy, prefix transformation. |
| `Gatherers.fold(initial, folder)` | Tích lũy theo thứ tự và phát ra kết quả cuối cùng. | Một phép biến đổi reduction-like phụ thuộc thứ tự. |
| `Gatherers.mapConcurrent(maxConcurrency, mapper)` | Áp dụng mapper đồng thời bằng virtual threads, giữ encounter order của kết quả. | Các thao tác độc lập có thời gian chờ, chẳng hạn gọi dịch vụ I/O. |

### Scan: phát ra kết quả tích lũy sau từng phần tử

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class RunningTotalExample {
    public static void main(String[] args) {
        List<Integer> totals = Stream.of(3, 5, 2, 4)
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        System.out.println(totals); // [3, 8, 10, 14]
    }
}
```

`scan` khác `reduce`: nó phát ra từng trạng thái tích lũy, thay vì chỉ trả về một kết quả terminal. Supplier tạo giá trị ban đầu cho mỗi lần thực thi Gatherer; không dùng một mutable accumulator dùng chung giữa nhiều pipeline.

### Fold: chỉ cần kết quả tích lũy cuối

```java
import java.util.Optional;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FoldExample {
    public static void main(String[] args) {
        Optional<String> result = Stream.of("Java", " ", "Gatherers")
                .gather(Gatherers.fold(StringBuilder::new,
                        StringBuilder::append))
                .map(StringBuilder::toString)
                .findFirst();

        System.out.println(result.orElse("")); // Java Gatherers
    }
}
```

`fold` phù hợp với phép tích lũy có thứ tự và không có combiner thích hợp. Nếu chỉ cần gom kết quả terminal theo quy tắc reduction thông thường, hãy cân nhắc `reduce` hoặc `collect`; không nên dùng Gatherer chỉ để thay thế một terminal operation đơn giản.

### MapConcurrent: giới hạn số tác vụ đồng thời

```java
import java.util.List;
import java.util.stream.Gatherers;

public class ConcurrentMappingExample {
    public static void main(String[] args) {
        List<String> customerIds = List.of("C-01", "C-02", "C-03");

        List<Customer> customers = customerIds.stream()
                .gather(Gatherers.mapConcurrent(8,
                        ConcurrentMappingExample::loadCustomer))
                .toList();

        System.out.println(customers);
    }

    private static Customer loadCustomer(String id) {
        // Thay bằng thao tác I/O độc lập, ví dụ gọi dịch vụ khách hàng.
        return new Customer(id);
    }

    record Customer(String id) {}
}
```

`mapConcurrent` chạy mapper bằng virtual threads với giới hạn đồng thời do `maxConcurrency` quy định và giữ thứ tự kết quả theo encounter order. Giá trị này phải lớn hơn hoặc bằng 1. API cố gắng hủy các tác vụ đang chạy khi downstream không còn cần kết quả, nhưng việc hủy là best-effort. Vì vậy, mapper vẫn nên có timeout và xử lý hủy phù hợp với dịch vụ được gọi. Đây là công cụ hữu ích cho công việc có thời gian chờ; không nên mặc định dùng nó cho mọi phép tính CPU-bound.

## 4. Chuyển Gatherer tự định nghĩa sang API ổn định

Một Gatherer có ba kiểu tham số:

- `T`: kiểu phần tử đầu vào.
- `A`: kiểu trạng thái trung gian, có thể mutable.
- `R`: kiểu phần tử được phát ra downstream.

Một Gatherer có thể được mô tả bằng bốn hàm:

| Hàm | Vai trò |
| --- | --- |
| `initializer()` | Tạo trạng thái mới cho một lần xử lý hoặc một partition. |
| `integrator()` | Nhận trạng thái, phần tử đầu vào và `Downstream`; cập nhật state và có thể phát kết quả. |
| `combiner()` | Gộp hai trạng thái khi Gatherer hỗ trợ thực thi song song. |
| `finisher()` | Thực hiện hành động cuối khi upstream đã hết phần tử, ví dụ phát phần tử còn đệm. |

Nếu Gatherer có trạng thái phụ thuộc thứ tự và không có cách gộp hai trạng thái chính xác, hãy dùng `Gatherer.ofSequential`. Nếu muốn Gatherer có thể được thực thi song song, hãy cung cấp combiner hợp lệ bằng `Gatherer.of`; mỗi partition phải có state riêng và combiner phải bảo toàn ngữ nghĩa kết quả theo encounter order.

### Ví dụ: loại bỏ phần tử trùng liên tiếp

Stream `distinct()` loại bỏ mọi phần tử trùng nhau trong toàn bộ stream. Một yêu cầu khác là chỉ loại bỏ các phần tử bằng phần tử ngay trước đó; ví dụ `A, A, B, A, A` trở thành `A, B, A`. Đây là phép biến đổi có trạng thái và phụ thuộc encounter order:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class ConsecutiveDistinctExample {
    static <T> Gatherer<T, ?, T> distinctConsecutive() {
        class State {
            boolean hasPrevious;
            T previous;
        }

        return Gatherer.ofSequential(
                State::new,
                Gatherer.Integrator.ofGreedy((state, element, downstream) -> {
                    if (!state.hasPrevious
                            || !Objects.equals(state.previous, element)) {
                        state.hasPrevious = true;
                        state.previous = element;
                        return downstream.push(element);
                    }
                    return true;
                })
        );
    }

    public static void main(String[] args) {
        List<String> values = Stream.of("A", "A", "B", "A", "A", "C")
                .gather(distinctConsecutive())
                .toList();

        System.out.println(values); // [A, B, A, C]
    }
}
```

`State` giữ phần tử gần nhất. Integrator chỉ đẩy phần tử xuống downstream khi nó khác phần tử trước. `ofGreedy` diễn đạt rằng integrator không tự quyết định dừng đọc đầu vào; nó chỉ truyền tiếp tín hiệu dừng khi `downstream.push` trả về `false`. `ofSequential` phù hợp vì state phụ thuộc thứ tự và ví dụ không cung cấp combiner.

### Khi nào dùng of, ofSequential và ofGreedy?

- `Gatherer.of(initializer, integrator, combiner, finisher)`: dùng khi có state và đã định nghĩa được cách gộp hai state độc lập để hỗ trợ parallel stream.
- `Gatherer.of(integrator)` hoặc overload có finisher: dùng cho Gatherer không có state riêng và có thể thực thi song song.
- `Gatherer.ofSequential(...)`: dùng khi state phụ thuộc encounter order hoặc không có combiner đúng.
- `Gatherer.Integrator.of(...)`: dùng khi integrator có thể tự kết thúc xử lý đầu vào bằng cách trả về `false`.
- `Gatherer.Integrator.ofGreedy(...)`: dùng khi integrator sẽ tiếp tục tiêu thụ đầu vào cho đến hết, trừ khi downstream từ chối nhận thêm phần tử.

`Downstream.push(value)` trả về `true` nếu downstream sẵn sàng nhận thêm dữ liệu và `false` nếu pipeline không cần thêm kết quả. Với integrator không greedy, trả về `false` cũng là cách short-circuit upstream. Không bỏ qua giá trị trả về này khi logic của Gatherer cần dừng sớm.

Không giữ tham chiếu tới state hoặc `Downstream` lâu hơn thời gian gọi hàm mà API truyền chúng vào. Đặc biệt, không đưa state mutable dùng nội bộ của một Gatherer ra ngoài hoặc chia sẻ nó giữa các thread.

## 5. Kết hợp nhiều Gatherer bằng andThen

`andThen` nối output của Gatherer trước vào input của Gatherer sau. Điều này cho phép đóng gói một chuỗi intermediate operation thành một Gatherer có thể tái sử dụng:

```java
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererCompositionExample {
    public static void main(String[] args) {
        Gatherer<Integer, ?, java.util.List<Integer>> windows =
                Gatherers.windowFixed(3);

        Gatherer<java.util.List<Integer>, ?, Integer> windowSizes =
                Gatherer.of((unused, window, downstream) ->
                        downstream.push(window.size()));

        var result = Stream.of(1, 2, 3, 4, 5, 6, 7)
                .gather(windows.andThen(windowSizes))
                .toList();

        System.out.println(result); // [3, 3, 1]
    }
}
```

Ở ví dụ này, Gatherer đầu tiên tạo các cửa sổ cố định; Gatherer thứ hai chuyển mỗi cửa sổ thành kích thước của nó. `andThen` giữ cả hai bước trong cùng một intermediate operation. Với pipeline thông thường, cũng có thể viết hai lời gọi `gather` liên tiếp; dùng `andThen` hữu ích khi muốn đặt tên, tái sử dụng hoặc đóng gói logic thành một Gatherer.

## 6. Quyết định có nên tự viết Gatherer hay không

Gatherer là extension point mạnh, nhưng không phải lựa chọn mặc định cho mọi phép biến đổi. Hãy cân nhắc theo nhu cầu:

| Nhu cầu | API nên cân nhắc |
| --- | --- |
| Biến đổi từng phần tử độc lập | `map` |
| Giữ hoặc loại phần tử theo điều kiện | `filter` |
| Một đầu vào tạo ra nhiều phần tử | `flatMap` hoặc `mapMulti` |
| Gom kết quả thành một collection hoặc giá trị cuối | `collect`, `reduce` |
| Cần gom cửa sổ, scan, fold hoặc map đồng thời | `Gatherers` |
| Cần intermediate operation có state, buffer, phát nhiều kết quả hoặc short-circuit tùy biến | Tự định nghĩa `Gatherer` |

Khi chạy parallel stream, chỉ cung cấp combiner nếu có thể gộp state từ hai partition mà vẫn giữ đúng ngữ nghĩa. Một combiner sai có thể cho kết quả khác với stream tuần tự. Nếu không có phép gộp đúng, chọn `ofSequential` hoặc chạy pipeline tuần tự; không thêm combiner giả chỉ để cố tận dụng parallel stream.

Với cửa sổ lớn, cần cân nhắc bộ nhớ vì implementation có thể cấp phát vùng lưu cửa sổ theo cách eager và liền kề. Với `mapConcurrent`, cần giới hạn số tác vụ đồng thời, đặt timeout và hiểu rằng việc hủy tác vụ đang chạy chỉ là best-effort. Những quyết định này quan trọng hơn việc chỉ thay tên API preview.

## 7. Quy trình migration thực tế

1. **Xác định phiên bản đích.** Chọn JDK 24 trở lên nếu cần dùng Gatherers chính thức.
2. **Tìm mã phụ thuộc preview.** Tìm các chỗ dùng `Gatherer`, `Gatherers`, `Stream.gather` và cấu hình `--enable-preview`.
3. **Đối chiếu chữ ký API.** Kiểm tra method handle, generic type, integrator, combiner và finisher của Gatherer tự định nghĩa.
4. **Chuyển sang API chính thức.** Giữ logic phù hợp, dùng các built-in Gatherers khi có sẵn và bỏ phụ thuộc preview.
5. **Cập nhật build và runtime.** Dùng JDK mới, đặt release tương ứng và bỏ preview flags nếu dự án không còn tính năng preview nào khác.
6. **Biên dịch lại và xác minh kết quả.** Không tái sử dụng class file được biên dịch cho preview JDK 22; kiểm tra cả pipeline tuần tự, song song, stream rỗng và các trường hợp short-circuit.

Stream Gatherers đã trở thành API chuẩn từ JDK 24. Khi chuyển dự án từ JDK 22, trọng tâm là biên dịch lại với JDK mới, bỏ yêu cầu preview và rà soát ngữ nghĩa của các Gatherer tự định nghĩa, đặc biệt là state, short-circuit và combiner. Các ứng dụng mới nên dùng API chính thức thay vì cấu hình preview của JDK 22.

## Tài liệu tham khảo

- [JEP 461: Stream Gatherers (Preview)](https://openjdk.org/jeps/461) — lần preview đầu tiên trong JDK 22.
- [JEP 473: Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473) — lần preview thứ hai trong JDK 23.
- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — hoàn thiện API trong JDK 24.
- [Gatherer, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.html) — factory methods, state, integrator, combiner, finisher và composition.
- [Gatherers, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherers.html) — các Gatherer dựng sẵn.
- [Stream, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html) — `Stream.gather(Gatherer)`.
- [Stream Gatherers, Java SE 22 Core Libraries Guide](https://docs.oracle.com/en/java/javase/22/core/stream-gatherers.html) — tài liệu lịch sử cho API preview JDK 22.
