# Hợp đồng initializer, integrator, combiner và finisher

**Stream Gatherer** là cơ chế mở rộng pipeline Java Stream API để tạo ra một thao tác trung gian có thể giữ trạng thái, xử lý một phần tử thành nhiều kết quả, gom nhiều phần tử thành một kết quả, hoặc dừng xử lý trước khi nguồn kết thúc. Điểm khác biệt quan trọng so với `map` hay `filter` là Gatherer cho phép người lập trình mô tả một phép biến đổi tùy biến qua **bốn hàm có hợp đồng phối hợp chặt chẽ**: `initializer`, `integrator`, `combiner` và `finisher`.

Bài học thuộc chương **Xây dựng Gatherer tùy biến** của module `JAVA_STREAM_API`. Ta sẽ hiểu vai trò từng hàm, vòng đời trạng thái, cách phát phần tử qua `Downstream`, cách xử lý dừng sớm, điều kiện chia việc song song, trường hợp không nên viết `combiner`, cũng như cách thử nghiệm một Gatherer với dữ liệu rỗng, trạng thái biên và nguồn I/O. Chủ đề nối tiếp kiến thức về pipeline lazy, `filter`, `map`, `reduce`, `collect`, `Spliterator` và Stream Gatherers.

> **Phiên bản JDK:** `java.util.stream.Gatherer`, `java.util.stream.Gatherers` và `Stream.gather(...)` là API chính thức từ **Java 24** (JEP 485). Chúng từng xuất hiện dưới dạng preview ở Java 22 và 23. Mã trong bài sử dụng API **Java 24 trở lên**, không chạy nguyên trạng trên Java 8–21. Gatherers không còn yêu cầu `--enable-preview` khi sử dụng Java 24.

## 1. Gatherer không phải Collector

Một `Collector` là đối số của thao tác terminal `collect(...)` và tạo một kết quả tổng hợp cuối cùng. Một `Gatherer` được đưa vào `Stream.gather(...)`, là **intermediate operation**: đầu ra của nó tiếp tục đi qua `filter`, `map`, `limit`, `collect`, `toList` hoặc các thao tác khác.

```text
Nguồn Stream<T>
      |
   filter / map
      |
   gather(Gatherer<T, A, R>)
      |       |
      |       +-- initializer: tạo A
      |       +-- integrator : nhận T, cập nhật A, có thể push R
      |       +-- combiner   : ghép hai A khi cho phép song song
      |       +-- finisher   : xử lý A cuối, có thể push R
      |
    Stream<R>
      |
   filter / map / limit / ...
      |
    toList / collect / reduce      <-- terminal
      |
     Kết quả
```

Ví dụ tạo cửa sổ cố định bằng Gatherer có sẵn:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> totals = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(Gatherers.<Integer>windowFixed(3))
        .map(window -> window.stream()
                .mapToInt(Integer::intValue)
                .sum())
        .toList();

System.out.println(totals); // [6, 15, 7]
```

`windowFixed(3)` biến các phần tử thành những danh sách có tối đa ba phần tử; `map` phía sau đổi từng danh sách thành tổng. Gatherer **không bắt buộc** phải đợi hết nguồn để phát kết quả: nó có thể phát một cửa sổ ngay khi cửa sổ đó hoàn tất.

Bốn thành phần của Gatherer giúp ta tự tạo một phép biến đổi theo đúng nguyên tắc ấy.

## 2. Ba kiểu T, A, R và bốn hợp đồng

Giao diện tổng quát:

```java
public interface Gatherer<T, A, R> {
    // Các phương thức được giải thích ở các phần tiếp theo.
}
```

Ba tham số kiểu:

| Kiểu | Ý nghĩa | Ví dụ khi tạo cửa sổ |
| --- | --- | --- |
| `T` | Phần tử đầu vào | `Integer` |
| `A` | Trạng thái trung gian riêng của Gatherer | Buffer giữ các số chưa đủ cửa sổ |
| `R` | Phần tử đưa ra phía sau `gather` | `List<Integer>` |

Hợp đồng của bốn hàm:

| Hàm | Kiểu hàm cơ bản | Trách nhiệm |
| --- | --- | --- |
| `initializer()` | `Supplier<A>` | Cấp trạng thái khởi đầu cho một lượt/nhánh xử lý |
| `integrator()` | `Gatherer.Integrator<A,T,R>` | Nhận phần tử mới, có thể sửa trạng thái và phát kết quả |
| `combiner()` | `BinaryOperator<A>` | Gộp hai trạng thái đã tích lũy, khi Gatherer cho phép parallel |
| `finisher()` | `BiConsumer<A, Downstream<? super R>>` | Thực hiện bước cuối sau khi tích lũy, thường phát phần tồn dư |

Khung xử lý tuần tự có thể hình dung:

```text
A state = initializer.get()

for mỗi phần tử T từ upstream:
    tiếp tục = integrator.integrate(state, T, downstream)
    nếu tiếp tục == false:
        dừng nhận thêm phần tử

finisher.accept(state, downstream)
```

Đây là **mô hình ý nghĩa**, không phải chương trình tự gọi toàn bộ bốn hàm. Java có quyền tối ưu: có thể không gọi initializer mặc định của Gatherer stateless, không gọi finisher mặc định, và có thể chia nguồn rồi gộp trạng thái nếu combiner cho phép.

Đừng nhầm các đối tượng `A` với kết quả `R`: trạng thái nội bộ không nhất thiết được công khai, và Gatherer có thể phát **0, 1 hoặc nhiều** `R` cho mỗi `T`.

## 3. initializer: bắt đầu từ trạng thái hợp lệ

`initializer()` trả về một `Supplier<A>`. Supplier này tạo trạng thái cho một lần tích lũy; trong xử lý song song, có thể được gọi nhiều lần để cấp trạng thái cho các phân hoạch khác nhau.

Ví dụ trạng thái của cửa sổ:

```java
import java.util.ArrayList;
import java.util.List;

static final class WindowState<T> {
    final List<T> pending = new ArrayList<>();
    boolean stopped;
}
```

Supplier:

```java
WindowState<Integer> initialState = new WindowState<>();
```

Trong Gatherer, nên truyền `WindowState::new` thay vì một đối tượng tạo sẵn. Điều kiện quan trọng là **mỗi lần Supplier được gọi phải có trạng thái độc lập**, không phải trả lại cùng một `ArrayList` hay Map dùng chung.

Sai:

```java
WindowState<Integer> shared = new WindowState<>();

// SAI: Supplier luôn trả lại một instance mutable.
java.util.function.Supplier<WindowState<Integer>> unsafe =
        () -> shared;
```

Đúng:

```java
java.util.function.Supplier<WindowState<Integer>> safe =
        WindowState::new;
```

Một trạng thái ban đầu tốt cần xác định **identity** cho phép ghép: với tổng là 0, với danh sách là rỗng, với bộ đếm là 0. Nếu cần phân biệt “chưa nhận phần tử” và “giá trị khóa đầu tiên là null”, dùng cờ `initialized`/`active` riêng, thay vì lấy `null` làm dấu hiệu chưa bắt đầu.

**Không nên lưu trạng thái của một lượt chạy vào biến static hoặc một object chung giữa những lượt Stream.** Gatherer được thiết kế như một mô tả có thể tái sử dụng; mỗi lần thực thi cần trạng thái riêng theo hợp đồng của nó.

## 4. integrator: nhận một phần tử, có thể phát nhiều kết quả

`integrator()` trả về một `Gatherer.Integrator<A,T,R>`. Phương thức trung tâm có hình thức:

```java
boolean integrate(
        A state,
        T element,
        Gatherer.Downstream<? super R> downstream
);
```

Một lần tích hợp có thể:

1. Đọc/đổi trạng thái `A` dựa trên phần tử `T`.
2. Không phát gì (ví dụ đang chờ đủ ba phần tử của cửa sổ).
3. Phát một hoặc nhiều `R` bằng `downstream.push(...)`.
4. Trả `true` để tiếp tục nhận phần tử, hoặc `false` để **dừng nhận thêm phần tử từ upstream**.

Ví dụ chỉ biến đổi mỗi số thành dạng chữ (minh họa Gatherer stateless):

```java
import java.util.function.Function;
import java.util.Objects;
import java.util.stream.Gatherer;

static <T, R> Gatherer<T, ?, R> project(
        Function<? super T, ? extends R> mapper) {

    Objects.requireNonNull(mapper, "mapper");

    return Gatherer.of(
            (unusedState, element, downstream) ->
                    downstream.push(mapper.apply(element))
    );
}
```

Dùng:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> labels = Stream.of(1, 2, 3)
        .gather(project(n -> "n=" + n))
        .toList();

System.out.println(labels); // [n=1, n=2, n=3]
```

Mã này tương đương về ý tưởng với `map`; trong ứng dụng thực, nên dùng `map` vì ngắn hơn. Điểm học tập là **không phải Gatherer nào cũng cần trạng thái**.

Với Gatherer stateless dạng `Gatherer.of(integrator)`, JDK sử dụng initializer và combiner mặc định thích hợp. Đừng tự tạo một đối tượng state vô ích nếu không có gì cần ghi nhớ giữa các phần tử.

## 5. Downstream.push và tín hiệu dừng sớm

`Gatherer.Downstream<R>` đại diện cho bước tiếp theo trong pipeline. Hai phương thức cần biết:

- `boolean push(R value)`: phát kết quả ra bước sau. Trả `true` nếu downstream vẫn có thể nhận thêm, `false` nếu không.
- `boolean isRejecting()`: kiểm tra tốt nhất khả năng downstream đã từ chối thêm phần tử. `false` **không bảo đảm** rằng lần `push` tiếp theo chắc chắn được nhận; đây là tín hiệu *best effort*.

Ví dụ `limit(2)` làm bước sau Gatherer dừng sau hai kết quả:

```java
List<String> firstTwo = Stream.of(10, 20, 30, 40)
        .gather(project(n -> "value:" + n))
        .limit(2)
        .toList();

System.out.println(firstTwo); // [value:10, value:20]
```

Hàm integrator trong `project` trả **chính giá trị của `push`**; khi downstream không muốn thêm kết quả, Gatherer có thể dừng nhận phần tử nguồn. Khi `push` đã trả `false`, các lần `push` tiếp theo trên cùng downstream sẽ tiếp tục bị từ chối theo hợp đồng.

### Dừng từ bên trong Gatherer

Một Gatherer cũng có thể tự quyết định chỉ phát tối đa `n` phần tử:

```java
import java.util.stream.Gatherer;

static <T> Gatherer<T, ?, T> firstAtMost(int maxElements) {
    if (maxElements < 0) {
        throw new IllegalArgumentException(
                "maxElements must not be negative"
        );
    }

    class State {
        int emitted;
    }

    return Gatherer.<T, State, T>ofSequential(
            State::new,
            (state, element, downstream) -> {
                if (state.emitted >= maxElements) {
                    return false;
                }

                state.emitted++;
                boolean wantsMore = downstream.push(element);

                return wantsMore && state.emitted < maxElements;
            }
    );
}
```

Ví dụ:

```java
System.out.println(
        Stream.of("A", "B", "C", "D")
                .gather(firstAtMost(2))
                .toList()
); // [A, B]
```

Giá trị trả về `false` có ý nghĩa **dừng tích hợp đầu vào**, không phải “phần tử hiện tại có lỗi”. Khi `maxElements == 0`, Gatherer không phát phần tử nào; nếu chỉ cần giới hạn thông thường, `Stream.limit(maxElements)` có sẵn và nên được ưu tiên.

**Quan trọng:** dừng sớm của Stream không tự đóng `Files.lines`, socket hay Reader. Quyền sở hữu tài nguyên của upstream vẫn phải được xử lý riêng bằng `try-with-resources` hoặc một hợp đồng đóng tài nguyên tương đương.

## 6. finisher: xử lý trạng thái còn tồn sau phần tử cuối

`finisher()` có hình thức:

```java
BiConsumer<A, Gatherer.Downstream<? super R>> finisher()
```

`finisher` **khác** finisher của Collector:

- Collector finisher biến `A` thành một **kết quả cuối `R`**.
- Gatherer finisher có thể **phát thêm phần tử** bằng `downstream.push(...)`, chẳng hạn nhóm cuối hoặc cửa sổ chưa đủ kích thước.

Ví dụ nhóm các phần tử thành lô ba phần tử: khi đọc `1,2,3,4,5`, integrator phát `[1,2,3]`; cuối nguồn, finisher phát `[4,5]`.

Không có finisher, lô `[4,5]` sẽ bị mất vì không có phần tử thứ sáu để kích hoạt phát tiếp.

**Hai quy tắc an toàn:**

1. Nếu đã phát một `List` xuống downstream, đừng tiếp tục `clear()` hoặc thay đổi List đó. Nên phát một **snapshot độc lập**.
2. Nếu downstream đã dừng, finisher không được phát thêm kết quả trái yêu cầu. Kiểm tra cờ dừng nội bộ và/hoặc `downstream.isRejecting()`, nhưng nhớ `isRejecting` là kiểm tra best effort.

## 7. Bài tập hoàn chỉnh: Gatherer gom lô tuần tự

Ta xây `fixedBatches(size)` để minh họa **initializer + integrator + finisher**. Nó có thứ tự phụ thuộc encounter order, vì vậy dùng `Gatherer.ofSequential(...)` và **không tự viết combiner giả**.

### 7.1. Mã Gatherer hoàn chỉnh

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;

public final class BatchGatherers {
    private BatchGatherers() {}

    private static final class BatchState<T> {
        final List<T> pending = new ArrayList<>();
        boolean stopped;
    }

    public static <T> Gatherer<T, ?, List<T>> fixedBatches(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException(
                    "size must be positive"
            );
        }

        return Gatherer.<T, BatchState<T>, List<T>>ofSequential(
                BatchState::new,            // initializer

                (state, element, downstream) -> { // integrator
                    state.pending.add(element);

                    if (state.pending.size() < size) {
                        return true;
                    }

                    // Phát bản sao, không phát buffer còn đang thay đổi.
                    List<T> complete =
                            new ArrayList<>(state.pending);
                    state.pending.clear();

                    boolean accepted = downstream.push(complete);
                    if (!accepted) {
                        state.stopped = true;
                    }
                    return accepted;
                },

                (state, downstream) -> {     // finisher
                    if (!state.stopped
                            && !state.pending.isEmpty()
                            && !downstream.isRejecting()) {
                        downstream.push(
                                new ArrayList<>(state.pending));
                    }
                }
        );
    }
}
```

### 7.2. Sử dụng trong pipeline

```java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> batches = Stream.of(
        1, 2, 3, 4, 5, 6, 7, 8
).gather(BatchGatherers.fixedBatches(3))
 .toList();

System.out.println(batches);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Dòng thời gian của `pending`:

```text
Nhận 1: pending = [1]         => chưa phát
Nhận 2: pending = [1,2]       => chưa phát
Nhận 3: pending = [1,2,3]     => push [1,2,3], clear
Nhận 4: pending = [4]         => chưa phát
Nhận 5: pending = [4,5]       => chưa phát
Nhận 6: pending = [4,5,6]     => push [4,5,6], clear
Nhận 7: pending = [7]         => chưa phát
Nhận 8: pending = [7,8]       => chưa phát
Kết thúc: finisher             => push [7,8]
```

Với nguồn rỗng, `pending` rỗng và finisher không phát gì. Với nguồn có đúng một lô đủ kích thước, finisher không phát lô rỗng.

### 7.3. Dừng sớm và xử lý snapshot

```java
List<List<Integer>> onlyOne = Stream.of(
        1, 2, 3, 4, 5, 6, 7
).gather(BatchGatherers.fixedBatches(3))
 .limit(1)
 .toList();

System.out.println(onlyOne); // [[1, 2, 3]]
```

Khi `limit(1)` đã nhận đủ lô đầu tiên, `push` có thể trả `false`. `stopped` ngăn finisher phát phần còn lại.

Nếu thay `new ArrayList<>(state.pending)` bằng `state.pending` rồi gọi `clear()`, các lô đã phát có thể biến thành danh sách rỗng hoặc thay đổi theo những phần tử sau. **Không được để trạng thái nội bộ mutable thoát ra downstream rồi tiếp tục thay đổi nó**.

Đối với lô lớn, buffer giữ tối đa `size` phần tử; bản sao khi phát làm phát sinh chi phí bộ nhớ và cấp phát. Nếu chỉ cần số lượng hoặc tổng từng lô, hãy lưu thống kê thay vì toàn bộ phần tử.

### 7.4. Khi nào không cần tự viết?

Trong Java 24 có `Gatherers.windowFixed(size)`, giải quyết chính bài toán chia thành lô cố định. `fixedBatches` là ví dụ **học hợp đồng**, không phải khuyến nghị tự viết lại API chuẩn cho mọi dự án.

## 8. combiner: ghép hai trạng thái, không phát tùy ý

`combiner()` trả về một `BinaryOperator<A>`:

```java
A combine(A left, A right);
```

Khi Gatherer được phép song song, framework có thể:

1. Chia nguồn thành các phân hoạch.
2. Cấp trạng thái riêng cho từng phân hoạch bằng initializer.
3. Gọi integrator trên phần tử của phân hoạch đó.
4. Đợi tích lũy của các phân hoạch kết thúc rồi gọi combiner để ghép các trạng thái.
5. Gọi finisher trên trạng thái cuối đã được ghép.

Sơ đồ:

```text
              Stream<T> (parallel)
                 /         \
               T...        T...
                |            |
          initializer    initializer
                |            |
           state A1       state A2
                |            |
          integrator     integrator
                |            |
                +-- combiner-+
                      |
                 merged A
                      |
                   finisher
                      |
                Stream<R>
```

**Hợp đồng cốt lõi của combiner:**

- Không đánh mất hoặc đếm trùng phần tử.
- Gộp trạng thái theo ý nghĩa của phép biến đổi.
- Có **phần tử đồng nhất** phù hợp với initializer.
- Đúng với các **cách phân nhóm khác nhau**: ghép `(A+B)+C` phải tương đương về kết quả với `A+(B+C)` khi Gatherer hỗ trợ parallel.
- Không giả định số lần gọi, kích thước phân hoạch hoặc số luồng cố định.
- Không tiếp tục sửa các trạng thái đã giao cho combiner/finisher theo cách vi phạm hợp đồng vòng đời.
- Không phát kết quả ra downstream một cách tùy tiện từ combiner, vì combiner chỉ nhận **hai trạng thái**, không có `Downstream`.

**Hàm combiner không bắt buộc phải tạo một state mới:** có thể gộp `right` vào `left` rồi trả `left`, miễn giữ đúng tính độc lập của các phân hoạch và quy tắc sử dụng trạng thái. Đừng tự truy cập đồng thời cùng state từ bên ngoài Gatherer.

## 9. Bài tập có đủ bốn hàm: cộng số nguyên để phát một tổng

Ta tạo một Gatherer nhận các `Integer` và phát **một `Long` tổng** ở cuối. Bài toán này có thể giải dễ hơn bằng `mapToLong(...).sum()`, nhưng nó cho thấy một Gatherer **có combiner đúng** hoạt động thế nào.

### 9.1. Triển khai Gatherer.of

```java
import java.util.stream.Gatherer;

public final class SumGatherers {
    private SumGatherers() {}

    private static final class SumState {
        long total;
    }

    public static Gatherer<Integer, ?, Long> oneTotal() {
        return Gatherer.<Integer, SumState, Long>of(
                SumState::new, // initializer: tổng khởi đầu 0

                Gatherer.Integrator.ofGreedy(
                        (state, value, downstream) -> {
                            state.total += value.longValue();
                            return true;
                        }
                ),

                (left, right) -> { // combiner: gộp hai tổng
                    left.total += right.total;
                    return left;
                },

                (state, downstream) -> { // finisher
                    if (!downstream.isRejecting()) {
                        downstream.push(state.total);
                    }
                }
        );
    }
}
```

Phân tích bốn hợp đồng:

- **Initializer:** `new SumState()` có `total == 0`, tức identity của phép cộng.
- **Integrator:** mỗi `Integer` được cộng vào tổng. Nó không phát output trước khi kết thúc.
- **Combiner:** hai tổng cục bộ được cộng thành một tổng mới, không bỏ dữ liệu nhánh phải.
- **Finisher:** khi kết thúc, phát tổng cuối cùng như một phần tử `Long`.

`Integrator.ofGreedy(...)` được dùng vì integrator này **luôn trả `true`**, không bao giờ tự yêu cầu dừng sớm. Nó cũng **không gọi `push` trong giai đoạn tích lũy**, nên không bỏ qua một tín hiệu từ downstream.

### 9.2. Cùng ngữ nghĩa khi có nhiều phân hoạch

```java
import java.util.List;
import java.util.stream.IntStream;

List<Long> sequential = IntStream.rangeClosed(1, 100)
        .boxed()
        .gather(SumGatherers.oneTotal())
        .toList();

List<Long> parallel = IntStream.rangeClosed(1, 100)
        .boxed()
        .parallel()
        .gather(SumGatherers.oneTotal())
        .toList();

System.out.println(sequential); // [5050]
System.out.println(parallel);   // [5050]
```

Các nhóm có thể chia thành tổng `1+...+50` và `51+...+100`, rồi combiner cộng hai tổng. Phép cộng nguyên trong phạm vi ví dụ bảo toàn ngữ nghĩa khi thay cách nhóm.

**Không nên dùng ví dụ này để khẳng định Gatherer tự viết nhanh hơn `sum()`.** Nó boxing `int` thành `Integer`, tạo trạng thái và dùng downstream để phát kết quả; `IntStream.sum()` chuyên dụng thường gọn và có thể tối ưu tốt hơn.

Trên miền lớn, phép cộng `long` cũng có thể tràn; chọn số học phù hợp yêu cầu. Và vì Gatherer là intermediate operation, kết quả cuối vẫn cần terminal `toList()` (hoặc phương thức terminal khác).

### 9.3. Vì sao không tự trả left mà bỏ right?

Sai:

```java
// SAI nếu đã tích lũy dữ liệu vào cả hai nhánh.
(left, right) -> left
```

Với một Stream song song, điều này bỏ mất tổng của một phân hoạch. Một lần chạy tuần tự vẫn có thể “trông đúng” nếu combiner không được dùng; do đó **kiểm thử tuần tự chưa đủ** cho Gatherer được tuyên bố có khả năng parallel.

## 10. Không phải mọi Gatherer có trạng thái đều chia được

Thử chuyển `fixedBatches(3)` ở phần 7 thành Gatherer song song bằng cách gộp hai danh sách `pending`:

```text
Dãy đầu vào: 1 2 3 4 5 6 7

Nhánh trái: [1 2 3 4]      phát [1 2 3], giữ [4]
Nhánh phải: [5 6 7]       phát [5 6 7]

Kết quả đúng theo toàn dãy:
  [1 2 3] [4 5 6] [7]

Kết quả sai nếu chỉ nối output của hai nhánh:
  [1 2 3] [5 6 7] [4]      (thứ tự/ranh giới sai)
```

Nhóm hoặc cửa sổ có thể **bắc qua ranh giới phân hoạch**. Không thể chỉ viết `left.pending.addAll(right.pending)` nếu các phần tử ở hai đầu đã phát thành kết quả trước đó.

Những bài toán thường khó ghép trạng thái:

- Nhóm các phần tử **liên tiếp** có cùng khóa;
- Cửa sổ trượt có chồng lặp giữa hai phân hoạch;
- Phát những thay đổi trạng thái so với phần tử trước;
- Dừng sau khi thấy một số lượng kết quả cụ thể;
- Tích lũy phụ thuộc mạnh vào encounter order.

Với những bài toán này, hãy bắt đầu bằng `Gatherer.ofSequential(...)`. Chỉ tự viết combiner khi có thể chứng minh rõ cách giữ **tiền tố, hậu tố và ranh giới** cũng như cách xử lý dừng sớm trên các phân hoạch.

**Cờ `parallel()` của Stream không tự sửa một combiner sai.** Nó chỉ cho phép framework chọn chiến lược song song khi Gatherer cung cấp combiner phù hợp.

## 11. ofSequential, of và các hàm mặc định

Java 24 có các factory quan trọng:

| Cách tạo Gatherer | Đặc điểm | Tình huống |
| --- | --- | --- |
| `Gatherer.ofSequential(initializer, integrator, finisher)` | Trạng thái, không cung cấp combiner song song | Lô/cửa sổ/nhóm kề nhau |
| `Gatherer.ofSequential(initializer, integrator)` | Có trạng thái, không cần finisher đặc biệt | Phát mọi output khi integrator chạy |
| `Gatherer.ofSequential(integrator)` | Stateless, tuần tự | Logic đặc thù không cần trạng thái |
| `Gatherer.of(initializer, integrator, combiner, finisher)` | Có trạng thái, cho phép parallel theo combiner | Tổng hợp gộp được |
| `Gatherer.of(integrator)` | Stateless, có khả năng parallel | Biến đổi độc lập từng phần tử |

Ba hàm mặc định cần phân biệt:

- `Gatherer.defaultInitializer()`: dấu hiệu Gatherer **stateless**; framework có thể bỏ qua việc gọi initializer.
- `Gatherer.defaultCombiner()`: dấu hiệu Gatherer **chỉ được đánh giá tuần tự**. Đây không phải một combiner ghép trạng thái tổng quát.
- `Gatherer.defaultFinisher()`: dấu hiệu **không có công việc cuối nguồn**; framework có thể bỏ qua việc gọi finisher.

Đừng thay `defaultCombiner()` bằng một lambda tưởng như vô hại để “bật song song”. Nếu lambda không mô tả phép ghép đúng, thuật toán vẫn sai khi chia nhánh. `ofSequential` là cách tường minh để báo rằng chưa có phép ghép trạng thái hợp lệ.

### Integrator.Greedy khác integrator thông thường

`Gatherer.Integrator.ofGreedy(...)` tạo một integrator tuyên bố **không tự khởi xướng short-circuit**. Theo hợp đồng Java 24, Greedy integrator phải sẵn sàng nhận toàn bộ đầu vào; nó **có thể chuyển tiếp** việc downstream không muốn nhận thêm phần tử. Framework có quyền không kiểm tra giá trị trả về của một Greedy integrator, vì trạng thái từ chối đã được biểu thị ở downstream.

Do đó:

```java
// HỢP LỆ: tự integrator không bao giờ yêu cầu dừng.
class CounterState {
    long total;
}

Gatherer.Integrator<CounterState, Integer, Long> greedy =
        Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    state.total += element.longValue();
                    return true;
                }
        );
```

Một Greedy integrator cũng có thể chuyển tiếp kết quả của `push` mà không tự đặt giới hạn:

```java
// HỢP LỆ: false chỉ phản ánh downstream đã từ chối thêm output.
Gatherer.Integrator<Void, Integer, Integer> forwardingGreedy =
        Gatherer.Integrator.ofGreedy(
                (unused, element, downstream) ->
                        downstream.push(element)
        );
```

Ngược lại, đoạn dưới **sai về hợp đồng Greedy**, vì nó tự quyết định dừng khi đã thấy đủ số phần tử, kể cả khi downstream vẫn sẵn sàng:

```java
class CutoffState {
    int seen;
}

// SAI: tự short-circuit ở lần thứ 5, không chỉ chuyển tiếp downstream.
Gatherer.Integrator<CutoffState, Integer, Integer> wrongGreedy =
        Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    state.seen++;
                    if (state.seen == 5) {
                        return false;
                    }
                    return downstream.push(element);
                }
        );
```

Muốn tự dừng theo ngưỡng, hãy dùng `Gatherer.Integrator` thông thường hoặc lambda integrator trực tiếp trong `ofSequential`; **đừng** đánh dấu `ofGreedy` cho thuật toán đó.

## 12. Vòng đời trạng thái và quy tắc không giữ tham chiếu

Đây là một phần dễ bị bỏ qua trong hợp đồng Gatherer. Theo API, implementation **không được giữ hoặc truyền ra luồng khác các tham chiếu đến state hoặc Downstream lâu hơn phạm vi invocation mà các đối tượng ấy được chuyển vào**.

Nên làm:

- Giữ state trong các hàm Gatherer đúng cách; Supplier tạo state mới khi framework yêu cầu.
- Phát **giá trị kết quả độc lập** qua `push`.
- Sau khi state đã được đưa cho combiner hoặc finisher, không tiếp tục thao tác với nó trong integrator.
- Không lưu `downstream` vào biến static, task nền hoặc callback chạy sau để gọi `push` bất kỳ lúc nào.
- Không dùng state của một phép gather làm container toàn cục có thể bị sửa đồng thời từ bên ngoài.

Không nên làm:

```java
// SAI về ý tưởng: giữ downstream để sử dụng sau khi callback kết thúc.
// static Gatherer.Downstream<String> savedDownstream;
//
// (state, element, downstream) -> {
//     savedDownstream = downstream;
//     return true;
// };
```

Việc làm này có thể vi phạm vòng đời và an toàn luồng. Nếu muốn xử lý bất đồng bộ, cần thiết kế pipeline theo một cơ chế được hỗ trợ rõ ràng, không dùng `Downstream` như một kênh callback tùy ý.

### Đầu ra mutable có được phép không?

Một `R` có thể là một `List<T>`, nhưng **không nên dùng chính state list đang biến đổi làm kết quả nếu còn sửa nó**. Phát snapshot sẽ giúp kết quả downstream không bị thay đổi bởi những lần integrator tiếp theo.

Nếu việc sao chép danh sách đắt, hãy xem lại yêu cầu: có thể phát `count`, `sum` hoặc một immutable DTO nhỏ thay vì giữ cả nhóm.

## 13. Hành vi dừng sớm khi có combiner

Dừng sớm là một tương tác tinh tế giữa integrator, downstream và phân hoạch song song.

Khi `integrate` trả `false`, framework hiểu như **không còn phần tử nào cần được đưa vào integrator ấy**. Với đánh giá song song, trạng thái từ các phân hoạch ở **phía sau** một phân hoạch đã short-circuit có thể không đóng góp vào kết quả được phép phát.

Vì thế các trường hợp sau cần được kiểm tra kỹ:

1. **Integrator dừng theo số phần tử đầu vào**: với nguồn ordered và chia nhánh, làm sao xác định “n phần tử đầu tiên”?
2. **Downstream dùng `limit`**: hàm `push` có thể báo `false` ngay trong khi tích hợp.
3. **Finisher có dữ liệu tồn dư**: có chắc downstream vẫn nhận thêm không?
4. **Combiner có giữ thứ tự cần thiết không?** Nếu không, việc lấy “đầu tiên” hoặc “cuối cùng” sẽ sai.

Ví dụ `fixedBatches` có cờ `stopped` và dùng `isRejecting` để không phát lô cuối khi downstream đã từ chối. Đó là một cách phối hợp trạng thái với yêu cầu ngừng nhận thêm dữ liệu.

Không nên khẳng định rằng `finisher` luôn được dùng để “cứu” mọi phần tử còn trong state sau khi downstream đã dừng. Khi downstream từ chối, phát thêm chỉ gây output bị bỏ hoặc vi phạm ý nghĩa mà ứng dụng mong muốn.

## 14. Composition: ghép nhiều Gatherer và các thao tác Stream

Một Gatherer có thể được nối với Gatherer khác bằng `andThen(...)`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> values = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(
                Gatherers.<Integer>windowFixed(3)
                        .andThen(
                                Gatherer.<List<Integer>, Integer>of(
                                        (unused, window, downstream) ->
                                                downstream.push(
                                                        window.stream()
                                                                .mapToInt(
                                                                        Integer::intValue)
                                                                .sum()
                                                )
                                )
                        )
        )
        .toList();

System.out.println(values); // [6, 15]
```

Ở đây ta đặt Gatherer tạo cửa sổ trước Gatherer tính tổng từng cửa sổ. Kết quả tương tự:

```java
List<Integer> direct = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(Gatherers.<Integer>windowFixed(3))
        .map(window -> window.stream()
                .mapToInt(Integer::intValue)
                .sum())
        .toList();
```

Mẫu `andThen` hữu ích khi muốn **đóng gói** nhiều bước biến đổi thành một Gatherer tái sử dụng. Nhưng khi chỉ cần `map` hoặc `filter` thông thường, không cần biến mọi bước thành Gatherer tùy chỉnh.

**Chú ý kiểu dữ liệu:** `andThen` ghép theo loại phần tử `R` của Gatherer trước và `T` của Gatherer sau; không ghép hai trạng thái `A`. Kiểm tra kiểu đầu vào/đầu ra sẽ giúp phát hiện các tổ hợp không phù hợp ngay lúc biên dịch.

## 15. Hiệu năng, bộ nhớ, và khi nào nên quay về API chuẩn

Việc viết Gatherer không tự đảm bảo hiệu năng cao hơn các phép Stream chuẩn.

| Cách làm | Ưu điểm | Giới hạn |
| --- | --- | --- |
| `map`, `filter`, `flatMap` | Rõ nghĩa, phổ biến, dễ tối ưu | Không trực tiếp biểu diễn mọi biến đổi stateful |
| `collect`/`reduce` | Tạo kết quả tổng hợp cuối | Không tự tạo một intermediate operation phát nhiều output |
| `Gatherers.windowFixed` | Cửa sổ cố định có sẵn | Không tùy biến toàn bộ logic ranh giới |
| `Gatherers.windowSliding` | Cửa sổ trượt có sẵn | Có chính sách cửa sổ xác định của JDK |
| `Gatherers.scan` | Tích lũy tiền tố có sẵn | Không thay mọi thuật toán trạng thái |
| `Gatherer.ofSequential` | Dễ giữ encounter order cho thuật toán kề nhau | Có thể hạn chế song song tại giai đoạn gather |
| `Gatherer.of` có combiner | Có thể tận dụng các phân hoạch | Phải chứng minh phép ghép an toàn và hiệu quả |

Đánh giá bộ nhớ:

- Trạng thái của `fixedBatches(k)` giữ tối đa khoảng `k` phần tử; đầu ra `toList()` giữ thêm tất cả lô đã phát.
- Trạng thái của `oneTotal()` là `O(1)` mỗi nhánh, nhưng có chi phí tạo và gộp state.
- Dùng `distinct`/`sorted` hoặc lồng các cửa sổ lớn trước hoặc sau Gatherer có thể làm pipeline phải giữ bộ đệm đáng kể.
- Nếu cần kết quả thống kê nhỏ, không nên phát danh sách lớn rồi tính tổng ở downstream nếu có thể thiết kế một phép tích lũy trực tiếp.

Song song chỉ có thể có ích nếu Spliterator của nguồn chia được, integrator đủ nặng, combiner rẻ hơn phần việc được chia và phép biến đổi không phụ thuộc thứ tự theo cách gây phối hợp lớn.

## 16. Quản lý tài nguyên khi upstream là I/O

Gatherer không thay đổi trách nhiệm đóng nguồn Stream:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<List<String>> readBatches(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> !line.isEmpty())
                .gather(BatchGatherers.fixedBatches(100))
                .toList();
    }
}
```

`Files.lines` mở tài nguyên; `gather` là intermediate và `toList` là terminal. **Không thao tác nào tự thay thế `close`**. `try-with-resources` đóng Stream cả khi nguồn rỗng, khi downstream dừng sớm hoặc khi xảy ra lỗi trong lúc đọc.

Với tệp rất lớn, `toList()` sau Gatherer vẫn giữ toàn bộ dữ liệu đã phát. Nếu mục tiêu chỉ là đếm số dòng theo lô hoặc tính thống kê, hãy dùng đầu ra nhỏ hoặc một terminal có bộ nhớ phù hợp.

Nếu upstream là `BufferedReader.lines()`, đối tượng Reader do caller sở hữu phải được đóng ở đúng vòng đời. Không trả một Stream lazy từ Reader đã được đóng trong `try`.

## 17. Bộ kiểm thử tối thiểu cho Gatherer tự viết

Một bộ kiểm thử có ích cần xác minh **kết quả**, **hợp đồng trạng thái**, **dừng sớm** và **song song** khi có combiner.

### 17.1. Lô tuần tự: nguồn rỗng, lô đủ, lô thiếu

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

static void checkEquals(Object expected, Object actual) {
    if (!Objects.equals(expected, actual)) {
        throw new AssertionError(
                "Expected " + expected + ", actual " + actual
        );
    }
}

checkEquals(
        List.of(),
        Stream.<Integer>empty()
                .gather(BatchGatherers.fixedBatches(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3), List.of(4, 5)),
        Stream.of(1, 2, 3, 4, 5)
                .gather(BatchGatherers.fixedBatches(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3)),
        Stream.of(1, 2, 3)
                .gather(BatchGatherers.fixedBatches(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3)),
        Stream.of(1, 2, 3, 4, 5)
                .gather(BatchGatherers.fixedBatches(3))
                .limit(1)
                .toList()
);
```

Cần kiểm tra snapshot: kết quả lô đầu không được thay đổi sau khi lô sau xuất hiện. Đồng thời kiểm tra `size <= 0` ném `IllegalArgumentException` và nguồn chỉ có một phần tử vẫn tạo lô cuối đúng chính sách.

### 17.2. Tổng với combiner: tuần tự và song song

```java
import java.util.List;
import java.util.stream.IntStream;

List<Long> a = IntStream.rangeClosed(1, 1000)
        .boxed()
        .gather(SumGatherers.oneTotal())
        .toList();

List<Long> b = IntStream.rangeClosed(1, 1000)
        .boxed()
        .parallel()
        .gather(SumGatherers.oneTotal())
        .toList();

checkEquals(List.of(500500L), a);
checkEquals(a, b);
```

Không xem việc trùng khớp ở một lần chạy là đủ để chứng minh combiner đúng. Hãy bổ sung các trường hợp dữ liệu rỗng, chỉ một phần tử, nhiều phần tử lặp, giá trị âm, và nhiều lượt chạy parallel với kích thước nguồn khác nhau. Với nguồn bị giới hạn số học, theo dõi điều kiện tràn.

### 17.3. Kiểm thử dữ liệu rỗng và lỗi đầu vào

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Nguồn rỗng, Gatherer gom lô | Không phát lô rỗng |
| Nguồn một phần tử, kích thước lô 3 | Finisher phát lô một phần tử |
| Kích thước lô 0 hoặc âm | Ném `IllegalArgumentException` trước khi duyệt |
| Downstream dùng `limit(1)` | Không có kết quả ngoài giới hạn |
| Nguồn chứa null | Chính sách rõ ràng: cho phép trong `ArrayList` hoặc chủ động từ chối |
| Gatherer công bố combiner song song | Kết quả khớp ngữ nghĩa với tuần tự |
| Nguồn `Files.lines` | Stream được đóng sau khi tiêu thụ |

Một điểm quan trọng: `List.of(null)` không hợp lệ; nếu cần kiểm thử phần tử null, có thể dùng `Arrays.asList((String) null)` làm nguồn.

## 18. Những lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Supplier luôn trả cùng một state mutable | Trạng thái lẫn giữa phân hoạch/lượt chạy | Cấp instance mới cho mỗi lần gọi |
| Lấy `null` làm dấu hiệu trạng thái chưa khởi tạo | Nhầm khi khóa hợp lệ là null | Dùng cờ `active` riêng |
| Integrator sửa biến ngoài Stream | Data race, phụ thuộc thứ tự và tác dụng phụ | Giữ trạng thái qua `A` của Gatherer |
| Bỏ qua giá trị trả về của `downstream.push` | Không tôn trọng yêu cầu dừng sớm | Dùng giá trị push để quyết định tiếp tục |
| Đánh dấu `ofGreedy` cho integrator tự dừng theo ngưỡng | Framework có quyền không kiểm tra giá trị trả về | Chỉ dùng Greedy nếu không **tự** short-circuit; được chuyển tiếp tín hiệu từ downstream |
| Thiếu finisher khi còn buffer | Mất lô/nhóm cuối | Phát tồn dư theo chính sách đã xác định |
| Phát state list rồi xóa hoặc sửa lại | Output trước đó bị thay đổi | Phát snapshot độc lập |
| Finisher phát dữ liệu dù downstream đã từ chối | Phát thừa hoặc bị từ chối | Dùng trạng thái dừng và `isRejecting` |
| Viết combiner chỉ trả `left` | Mất dữ liệu từ nhánh `right` | Gộp trạng thái đúng nghĩa |
| Tự bật parallel cho nhóm kề nhau nhưng không xử lý ranh giới | Mất, lặp hoặc trộn nhóm | Dùng `ofSequential` hoặc chứng minh combiner |
| Tưởng `defaultCombiner` ghép trạng thái được | Gatherer chỉ đánh giá tuần tự | Viết combiner thực sự nếu cần parallel |
| Giữ tham chiếu `Downstream` để push trong thread khác | Vi phạm vòng đời callback | Chỉ sử dụng trong phạm vi invocation |
| Dùng Gatherer cho mọi phép `map`/`filter` | Tăng độ phức tạp không cần thiết | Ưu tiên API chuẩn |
| Giữ mọi cửa sổ trong `toList` cho tệp lớn | Tốn bộ nhớ dù nguồn đọc lazy | Phát kết quả nhỏ hoặc dùng terminal phù hợp |
| Nghĩ `gather`/`toList` đóng nguồn I/O | Rò rỉ tài nguyên | `try-with-resources` |

## 19. Bài tập nâng cao

### Bài tập A: viết Gatherer phát các nhóm ký tự liên tiếp

Nguồn:

```text
A A B B B A C C
```

Đầu ra mong muốn:

```text
(A,2), (B,3), (A,1), (C,2)
```

**Yêu cầu:** initializer giữ khóa/đếm và cờ `active`; integrator phát nhóm cũ khi khóa đổi; finisher phát nhóm cuối; dùng `Objects.equals` nếu khóa có thể null; không viết combiner nếu chưa giải được ranh giới phân hoạch.

### Bài tập B: mỗi cửa sổ phát tổng, không phát List

Thay `fixedBatches(k)` bằng Gatherer giữ `long sum` và `int count`. Khi `count == k`, phát một `Long` rồi reset trạng thái. Khi kết thúc, quy định có phát lô cuối không đủ `k` hay không.

**Tiêu chí:** xử lý nguồn rỗng, `k=1`, `k=3`, dừng sớm, miền số và tràn `long`.

### Bài tập C: chứng minh combiner đúng

Với `oneTotal()`, hãy mô phỏng ba trạng thái chứa các tổng lần lượt `10`, `20`, `30`. So sánh:

```text
combine(combine(A, B), C) => 60
combine(A, combine(B, C)) => 60
```

Giải thích vì sao trạng thái rỗng (tổng 0) là identity. Sau đó thử thay combiner bằng phép trừ và chỉ ra phép ghép không kết hợp như yêu cầu.

### Bài tập D: dừng theo ngưỡng

Viết Gatherer phát dữ liệu đầu vào cho tới khi gặp một giá trị lớn hơn ngưỡng, rồi dừng. Xác định rõ phần tử vượt ngưỡng **có được phát hay không**. Dùng kết quả `push` để tôn trọng downstream `limit`.

**Tiêu chí:** nguồn rỗng, vượt ngưỡng ở phần tử đầu, không vượt ngưỡng, và upstream có tài nguyên cần đóng.

### Bài tập E: đối chiếu API chuẩn

Thử `Gatherers.windowFixed`, `Gatherers.windowSliding` và `Gatherers.scan` để xác định bài toán nào **không cần** Gatherer tùy chỉnh. Chỉ tự viết khi quy tắc ranh giới, output hoặc dừng sớm khác hợp đồng sẵn có.

## 20. Câu hỏi tự kiểm tra

1. `Gatherer` là intermediate hay terminal operation? **Intermediate**; `Stream.gather` cho phép nối các thao tác tiếp theo.
2. Ba kiểu `T`, `A`, `R` là gì? **Đầu vào, trạng thái tích lũy, đầu ra phát xuống downstream**.
3. `initializer` phải tạo trạng thái như thế nào? **Hợp lệ và độc lập mỗi lần Supplier được gọi**.
4. `integrator` có phải luôn phát đúng một output không? **Không**, có thể phát 0, 1 hoặc nhiều.
5. `integrate` trả `false` có nghĩa gì? **Ngừng nhận thêm phần tử từ upstream cho tiến trình tích hợp đó**.
6. `Downstream.push` trả `false` có ý nghĩa gì? **Downstream không muốn nhận thêm phần tử**.
7. `Downstream.isRejecting()` trả `false` có bảo đảm push tiếp theo thành công không? **Không**, đây là kiểm tra best effort.
8. Finisher của Gatherer khác finisher của Collector ở đâu? **Gatherer finisher có thể push thêm output; Collector finisher chuyển trạng thái thành kết quả cuối**.
9. Khi nào finisher quan trọng nhất? **Khi còn nhóm hoặc cửa sổ chưa được phát ở cuối nguồn**.
10. Vì sao phải snapshot buffer trước khi phát? **Để tránh output bị sửa bởi các lần tích lũy tiếp theo**.
11. `combiner` được gọi khi nào? **Khi framework đánh giá Gatherer có khả năng parallel và cần ghép các trạng thái**.
12. Có thể bỏ nhánh `right` trong combiner không? **Không**, nếu như vậy mất kết quả của một phân hoạch.
13. `defaultCombiner()` biểu thị điều gì? **Gatherer chỉ được đánh giá tuần tự**.
14. `defaultInitializer()` biểu thị điều gì? **Gatherer stateless; framework có thể không gọi initializer**.
15. `defaultFinisher()` biểu thị điều gì? **Không cần bước cuối nguồn; framework có thể bỏ qua finisher**.
16. Khi nào `Integrator.ofGreedy` hợp lệ? **Khi integrator không tự khởi xướng short-circuit**; nó vẫn có thể chuyển tiếp việc downstream từ chối thêm output.
17. Vì sao nhóm liên tiếp khó xử lý song song? **Phải xét ranh giới giữa các phân hoạch**.
18. `parallel()` có tự biến Gatherer `ofSequential` thành một phép chia trạng thái đúng không? **Không**.
19. Có được lưu `Downstream` để dùng sau khi callback kết thúc không? **Không**, vì vi phạm hợp đồng vòng đời.
20. `gather` có tự đóng `Files.lines` không? **Không**, người sở hữu nguồn phải đóng bằng `try-with-resources`.
21. Khi chỉ cần tổng số nguyên, có nên luôn dùng Gatherer tùy chỉnh không? **Không**, `sum()` hoặc `reduce()` thường đơn giản hơn.
22. Gatherer chuẩn có từ Java nào? **Java 24**, sau các phiên bản preview ở Java 22 và 23.

## Tài liệu tham khảo

- [Java SE 24 — Gatherer API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): hợp đồng của bốn hàm, các factory và xử lý trạng thái/song song.
- [Java SE 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): `push` và `isRejecting`.
- [Java SE 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): hướng dẫn tạo và sử dụng Gatherer.
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): cột mốc hoàn thiện API trong Java 24.

**Nguyên tắc áp dụng:** Bốn hàm `initializer`, `integrator`, `combiner` và `finisher` không phải bốn callback tùy ý mà là **hợp đồng phối hợp xử lý dữ liệu**. Hãy bắt đầu từ trạng thái khởi tạo độc lập, tích hợp phần tử và phát output đúng thời điểm, tôn trọng tín hiệu dừng của downstream, chỉ tạo combiner khi chứng minh được phép gộp hợp lệ, và dùng finisher cho phần còn tồn ở cuối nguồn. Với thuật toán phụ thuộc phần tử kề nhau, `ofSequential` thường an toàn và dễ hiểu hơn; với phép tổng hợp có thể kết hợp, `of` cho phép parallel nhưng vẫn phải kiểm thử ngữ nghĩa. Sau cùng, quản lý tài nguyên và bộ nhớ độc lập với việc Gatherer là lazy.
