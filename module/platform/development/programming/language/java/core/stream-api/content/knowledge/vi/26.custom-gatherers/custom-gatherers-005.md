# Tạo Gatherer tuần tự bằng Gatherer.ofSequential

Với Java Stream API, các thao tác `filter`, `map` và `flatMap` giải quyết nhiều bài toán chuyển đổi phần tử độc lập. Tuy nhiên, có những tác vụ cần **ghi nhớ trạng thái giữa các phần tử**: tính tổng lũy kế, đánh số thứ tự, gộp từng nhóm liên tiếp, phát ra một báo cáo khi kết thúc dữ liệu hoặc dừng sau một điều kiện. Thay vì đặt biến mutable bên ngoài pipeline rồi sử dụng `peek` hoặc `forEach`, từ **Java 24** có thể tự xây một *Stream Gatherer* bằng `Gatherer.ofSequential`.

`Gatherer.ofSequential` phù hợp khi thuật toán cần tiến hành bước tích hợp (*integration*) theo trình tự, với **trạng thái riêng của mỗi lần thực thi pipeline**. Gatherer không chỉ đổi từng `T` thành đúng một `R`: với mỗi phần tử đầu vào, nó có thể **không phát đầu ra, phát một đầu ra hoặc nhiều đầu ra**, và có thể phát thêm dữ liệu ở bước hoàn tất. Đây là công cụ mở rộng pipeline cho những xử lý liên tiếp khó diễn đạt bằng `map` hay `filter` đơn thuần.

Bài thuộc chương **Xây dựng Gatherer tùy biến** của module **JAVA_STREAM_API**. Ta sẽ học cách thiết kế initializer, integrator, downstream và finisher; kiểm tra hợp đồng dừng sớm; hiểu giới hạn khi nguồn song song; sau đó viết ví dụ Java 24 tự chạy được. Kiến thức liên quan tới pipeline lazy, `reduce`, `collect`, grouping, `Spliterator`, trạng thái và hiệu năng, nhưng trọng tâm là **tạo Gatherer tuần tự đúng ngữ nghĩa**.

## 1. Phiên bản JDK và mục đích của Gatherer

Các kiểu chính nằm trong package:

```java
import java.util.stream.Gatherer;
import java.util.stream.Stream;
```

Phương thức trung gian trên Stream có dạng:

```java
Stream<R> output = input.gather(gatherer);
```

Stream Gatherers được đưa vào Java trong các phiên bản preview trước đó và **trở thành API chính thức từ JDK 24**. Vì vậy, các ví dụ của bài dùng **JDK 24 trở lên**; không thể biên dịch trực tiếp với JDK 8, 11, 17 hoặc 21. Với môi trường sử dụng phiên bản preview, quy tắc bật preview có thể khác và không nên xem những ví dụ JDK 24 này là mã tương thích ngược.

Ví dụ đơn giản về hình dạng pipeline:

```java
List<String> output = Stream.of("A", "B", "C")
        .gather(myGatherer)
        .toList();
```

`myGatherer` ở đây là một Gatherer đã được định nghĩa. `gather(...)` vẫn là **intermediate operation**: nó tạo pipeline, chưa nhất thiết duyệt nguồn. `toList()` là terminal operation kích hoạt xử lý.

### 1.1. Khi nào cần Gatherer thay vì API có sẵn?

| Bài toán | Công cụ thường phù hợp |
|---|---|
| Lọc từng phần tử độc lập | `filter` |
| Biến đổi mỗi phần tử thành một giá trị | `map` |
| Mỗi phần tử tạo ra Stream con | `flatMap` |
| Cộng/đếm/tổng hợp thành một kết quả cuối | `reduce`, `collect` |
| Nhóm theo khóa không phụ thuộc vị trí liên tiếp | `groupingBy` |
| Tính **tổng lũy kế sau từng phần tử** | Gatherer có trạng thái hoặc thuật toán riêng |
| Chia dãy thành **các khối liên tiếp** rồi phát từng khối | Gatherer, hoặc `Gatherers.windowFixed` có sẵn nếu phù hợp |
| Phát một bản ghi tổng kết khi kết thúc | Gatherer có finisher |
| Điều phối phép biến đổi mới với trạng thái và quy tắc phát đầu ra | Gatherer tùy biến |

Đừng chọn Gatherer chỉ vì cú pháp mới: nếu `filter`, `map`, `limit` hay một collector có sẵn đã diễn đạt bài toán rõ ràng, ưu tiên công cụ đơn giản hơn.

## 2. Mô hình Gatherer<T, A, R>

Giao diện tổng quát là `Gatherer<T, A, R>`:

- **`T`**: kiểu phần tử đầu vào.
- **`A`**: kiểu trạng thái trung gian của Gatherer; có thể là một đối tượng mutable hoặc `Void` nếu không cần trạng thái.
- **`R`**: kiểu phần tử đầu ra mà downstream nhận.

Mô hình khái niệm:

```text
Stream<T>
    |
    v
initializer -> trạng thái A mới
    |
    +----> integrator(A, T, downstream)
                 |
          cập nhật trạng thái
                 |
          push(0..n phần tử R)
                 |
       có tiếp tục tích hợp không?
                 |
             [lặp với T]
                 |
       finisher(A, downstream)
                 |
           push phần còn lại
                 |
              Stream<R>
```

Các thành phần cần hiểu:

| Thành phần | Nhiệm vụ | Đặc điểm của `ofSequential` |
|---|---|---|
| **Initializer** | Khởi tạo `A` cho quá trình tích hợp | Có thể cung cấp `Supplier<A>` hoặc dùng overload không cần trạng thái |
| **Integrator** | Nhận trạng thái, phần tử `T` và downstream; có thể phát `R` | Được thực thi theo mô hình tích hợp tuần tự |
| **Downstream** | Nơi nhận các phần tử `R` từ `push` | Có thể từ chối thêm đầu ra khi pipeline dừng sớm |
| **Finisher** | Hoàn tất trạng thái và có thể phát thêm `R` | Tùy chọn; có thể dùng để đẩy nhóm chưa đủ kích thước |
| **Combiner** | Kết hợp hai trạng thái khi tích hợp song song | `ofSequential` không yêu cầu bạn tự xây phép gộp song song |

Điểm đặc biệt của một Gatherer là **`integrator` trả về `boolean`** để cho biết liệu có nên tiếp tục nhận phần tử đầu vào hay không. Điều này khác với `Consumer<T>` trong `forEach`, vốn không trả tín hiệu dừng.

## 3. Các overload ofSequential thường dùng

Ba biến thể thực hành phổ biến:

### 3.1. Không cần trạng thái và finisher

```java
Gatherer<T, Void, R> gatherer =
        Gatherer.ofSequential(integrator);
```

Trong trường hợp không cần giữ trạng thái, `A` là `Void` và integrator có thể bỏ qua giá trị state. Dùng cho những phép ánh xạ/lọc đơn giản cần thử API, dù `map`/`filter` thường ngắn gọn hơn.

### 3.2. Có trạng thái, không cần finisher

```java
Gatherer<T, A, R> gatherer =
        Gatherer.ofSequential(
                initializer,
                integrator);
```

Đây là lựa chọn cho tổng lũy kế hoặc đánh số thứ tự: mỗi phần tử được tích hợp, kết quả phát ra ngay, và không có phần dữ liệu tồn đọng cần phát khi nguồn kết thúc.

### 3.3. Có trạng thái và finisher

```java
Gatherer<T, A, R> gatherer =
        Gatherer.ofSequential(
                initializer,
                integrator,
                finisher);
```

Dùng khi phải tích lũy một **khối chưa hoàn chỉnh** và chỉ biết cần phát khối ấy khi đầu vào kết thúc. Finisher không phải cách thay thế terminal operation: nó là giai đoạn hoàn tất của Gatherer trong pipeline.

**Lưu ý về cách đọc cú pháp:** `initializer` thường là `Supplier<A>`; `integrator` là `Gatherer.Integrator<A,T,R>`; `finisher` có thể nhận `(state, downstream)` và thực hiện các lệnh đẩy phần tử còn lại. Ví dụ đầy đủ ở phần 5 và 6 cho thấy cách các kiểu được suy ra từ khai báo `Gatherer<T,A,R>`.

## 4. Downstream.push và tín hiệu dừng sớm

Trong integrator, `downstream.push(value)` cố phát một phần tử đầu ra và trả về `boolean`:

- `true`: downstream còn có thể chấp nhận đầu ra; integrator có thể tiếp tục.
- `false`: downstream đã từ chối nhận thêm đầu ra; integrator nên truyền tín hiệu dừng khi thích hợp.

Ví dụ, một Gatherer biến đổi một số `n` thành `n * 2` có thể viết:

```java
import java.util.stream.Gatherer;

Gatherer<Integer, Void, Integer> doublePositive =
        Gatherer.ofSequential((state, value, downstream) -> {
            if (value <= 0) {
                return true; // Bỏ phần tử đầu vào này, tiếp tục đọc.
            }
            return downstream.push(value * 2);
        });
```

Đoạn này **không giữ trạng thái** và chỉ phát số dương nhân đôi. Dữ liệu đầu vào có thể dùng:

```java
List<Integer> values = Stream.of(-1, 2, 0, 3)
        .gather(doublePositive)
        .toList();

System.out.println(values); // [4, 6]
```

Khi downstream từ chối vì có `limit` hoặc một thao tác ngắn mạch, việc trả kết quả của `push` giúp Gatherer không tiếp tục tích hợp không cần thiết. Không nên luôn trả `true` sau khi `push` báo không nhận thêm, bởi điều đó có thể làm nguồn tiếp tục bị duyệt dù kết quả đã đủ.

### 4.1. false không phải “bỏ qua phần tử”

Đây là khác biệt quan trọng:

```java
if (!isValid(value)) {
    return true;   // Không push nhưng cho phép xét phần tử sau.
}
```

Trả `false` nói rằng Gatherer **không muốn tích hợp thêm phần tử đầu vào**; nó không chỉ có nghĩa “lọc bỏ phần tử hiện tại”. Nếu logic lọc bỏ một giá trị mà lại trả `false`, pipeline sẽ kết thúc sớm ngoài ý muốn.

### 4.2. Không coi short-circuit là một chu kỳ đầy đủ

Nếu downstream kết thúc sớm, ví dụ `limit(2)`, quá trình tích hợp có thể không nhìn thấy tất cả phần tử nguồn. Vì vậy, **trạng thái của Gatherer chỉ phản ánh phần dữ liệu thực sự đã tích hợp**, không nhất thiết là toàn bộ dữ liệu ban đầu. Không dùng finisher hoặc biến đếm bên trong Gatherer để khẳng định đã xử lý mọi phần tử nếu terminal operation có thể dừng sớm.

## 5. Ví dụ Java 24 hoàn chỉnh: tổng tiền lũy kế

Giả sử một hệ thống thanh toán cần in **tổng tiền đã xử lý sau mỗi giao dịch**. `reduce` hay `sum` chỉ cho kết quả cuối cùng, trong khi ta cần một đầu ra cho **mỗi** giao dịch, phụ thuộc tổng các giao dịch trước đó.

Ta thiết kế Gatherer:

- Nhận `Long` là số tiền của giao dịch; giá trị âm có thể biểu diễn điều chỉnh/hoàn tiền trong ví dụ.
- `RunningState` có `count` và `sumCents`.
- Mỗi lần tích hợp, cộng tiền và tăng count, rồi phát `RunningTotal(index, sumCents)`.
- Kiểm soát tràn `long` bằng `Math.addExact`.
- Không cần finisher vì sau mỗi phần tử đã phát kết quả tương ứng.

Lưu đoạn sau thành `SequentialGathererDemo.java` và chạy với **JDK 24+**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class SequentialGathererDemo {

    static final class RunningState {
        long count;
        long sumCents;
    }

    static final class RunningTotal {
        final long index;
        final long totalCents;

        RunningTotal(long index, long totalCents) {
            this.index = index;
            this.totalCents = totalCents;
        }

        @Override
        public String toString() {
            return "#" + index + "=" + totalCents;
        }
    }

    static Gatherer<Long, RunningState, RunningTotal>
            runningTotals() {
        return Gatherer.ofSequential(
                RunningState::new, // initializer
                (state, amount, downstream) -> {
                    state.count = Math.addExact(state.count, 1L);
                    state.sumCents = Math.addExact(
                            state.sumCents, amount);

                    // Trả boolean của push để lan truyền tín hiệu dừng.
                    return downstream.push(new RunningTotal(
                            state.count, state.sumCents));
                });
    }

    public static void main(String[] args) {
        List<Long> transactions = Arrays.asList(
                5_000L, 3_000L, -2_000L, 7_000L);

        List<RunningTotal> totals = transactions.stream()
                .gather(runningTotals())
                .toList();

        System.out.println(totals);
        // [#1=5000, #2=8000, #3=6000, #4=13000]

        // Mỗi lần collect là một lần tích hợp với state riêng.
        List<RunningTotal> again = transactions.stream()
                .gather(runningTotals())
                .toList();
        System.out.println(again);
        // [#1=5000, #2=8000, #3=6000, #4=13000]

        // Nguồn rỗng: không có trạng thái nào được push.
        List<RunningTotal> empty = Stream.<Long>empty()
                .gather(runningTotals())
                .toList();
        System.out.println(empty); // []

        // Giữ thứ tự từ List trong xử lý tuần tự.
        transactions.stream()
                .gather(runningTotals())
                .forEachOrdered(System.out::println);
        // #1=5000
        // #2=8000
        // #3=6000
        // #4=13000
    }
}
```

### 5.1. Giải thích cách chạy

| Giao dịch | `state.count` sau khi nhận | `state.sumCents` sau khi nhận | Đầu ra |
|---:|---:|---:|---|
| `5000` | 1 | 5000 | `#1=5000` |
| `3000` | 2 | 8000 | `#2=8000` |
| `-2000` | 3 | 6000 | `#3=6000` |
| `7000` | 4 | 13000 | `#4=13000` |

Tổng lũy kế khác với tổng cuối ở chỗ nó **phát nhiều kết quả**, mỗi kết quả là một ảnh chụp trạng thái sau bước tích hợp. Nếu chỉ cần `13000`, `mapToLong(...).sum()` sẽ đơn giản hơn.

### 5.2. Vì sao initializer phải tạo state mới?

`RunningState::new` tạo một `RunningState` mới cho mỗi lượt dùng Gatherer cần một trạng thái riêng. Không nên tạo một `static RunningState shared` để mọi pipeline dùng chung; làm vậy khiến lần chạy thứ hai tiếp tục số đếm của lần đầu và có thể gây data race nếu chạy song song.

### 5.3. Vì sao không giữ RunningState trong kết quả?

`RunningTotal` giữ **hai giá trị `long` đã chụp**, không giữ tham chiếu tới đối tượng `RunningState` mutable. Nếu đẩy chính một đối tượng state ra ngoài rồi tiếp tục sửa nó, mọi phần tử đầu ra có thể trỏ tới cùng một trạng thái đang thay đổi, khiến danh sách kết quả không thể hiện các mốc lũy kế chính xác.

## 6. Ví dụ Java 24 hoàn chỉnh: chia các phần tử thành khối cố định

Một ứng dụng gửi thông điệp theo lô cần chia danh sách thành các khối liên tiếp, mỗi khối có tối đa `batchSize` phần tử. Khi khối đủ kích thước, integrator phát một `List<String>`. Nếu nguồn kết thúc mà còn khối chưa đủ kích thước, **finisher** phải phát nốt khối cuối.

Ví dụ có 5 phần tử, cỡ khối 2:

```text
Đầu vào: A B C D E
Khối 1:  [A, B]
Khối 2:  [C, D]
Khối 3:  [E]    <- finisher phát
```

Mã sau chạy độc lập bằng JDK 24+:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class SequentialBatchGathererDemo {

    static Gatherer<String, List<String>, List<String>>
            batchesOf(int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize phải lớn hơn 0");
        }

        return Gatherer.ofSequential(
                ArrayList::new,
                (state, value, downstream) -> {
                    Objects.requireNonNull(value, "value");
                    state.add(value);

                    if (state.size() == batchSize) {
                        // Snapshot độc lập: không đẩy state mutable ra ngoài.
                        List<String> batch =
                                Collections.unmodifiableList(
                                        new ArrayList<>(state));
                        state.clear();
                        return downstream.push(batch);
                    }
                    return true; // Chưa đủ khối, tiếp tục nhận input.
                },
                (state, downstream) -> {
                    if (!state.isEmpty()) {
                        downstream.push(Collections.unmodifiableList(
                                new ArrayList<>(state)));
                    }
                });
    }

    public static void main(String[] args) {
        List<List<String>> groups = Stream.of("A", "B", "C", "D", "E")
                .gather(batchesOf(2))
                .toList();

        System.out.println(groups);
        // [[A, B], [C, D], [E]]

        List<List<String>> exact = Stream.of("A", "B", "C", "D")
                .gather(batchesOf(2))
                .toList();
        System.out.println(exact); // [[A, B], [C, D]]

        List<List<String>> none = Stream.<String>empty()
                .gather(batchesOf(2))
                .toList();
        System.out.println(none); // []

        try {
            batchesOf(0);
            throw new AssertionError("Phải từ chối batchSize=0");
        } catch (IllegalArgumentException expected) {
            System.out.println("Đã từ chối batchSize=0");
        }
    }
}
```

### 6.1. Vai trò của ba thành phần

**Initializer:** tạo danh sách rỗng riêng cho quá trình tích hợp. **Integrator:** thêm phần tử vào danh sách; khi đủ kích thước, chụp danh sách, xóa bộ đệm để bắt đầu khối mới, và `push` khối ra downstream. **Finisher:** phát khối cuối nếu bộ đệm còn phần tử.

Khối đã phát được bọc không sửa được và được sao chép từ state. Nếu chỉ `downstream.push(state)` rồi `state.clear()`, kết quả ở các khối có thể cùng tham chiếu một List bị sửa sau khi push, gây lỗi rất khó phát hiện.

### 6.2. Vì sao dùng ofSequential ở đây?

Khái niệm “khối đầu tiên gồm hai phần tử đầu của dãy”, “khối tiếp theo gồm hai phần tử kế” phụ thuộc vào **vị trí liên tiếp và thứ tự đầu vào**. Khi chia nguồn thành các phần chạy độc lập, một combiner tùy tiện không thể chỉ ghép hai danh sách batch mà luôn giữ được ranh giới khối đúng.

`Gatherer.ofSequential` giúp mô tả một cơ chế tích hợp theo trình tự mà **không phải thiết kế phép kết hợp trạng thái song song**. Nếu chỉ cần chia khối cố định theo API có sẵn, Java 24 cũng có `Gatherers.windowFixed(batchSize)`; hãy ưu tiên API chuẩn khi đúng yêu cầu, và dùng custom gatherer để học cách bổ sung quy tắc nghiệp vụ riêng.

### 6.3. Finisher và short-circuit

Finisher có thể được dùng khi nguồn đã hoàn tất hoặc giai đoạn Gatherer đang hoàn tất. Nếu downstream **không còn nhận đầu ra**, việc `push` tiếp cũng không tạo thêm phần tử được chấp nhận. Không thiết kế finisher như một bước side effect bắt buộc để “đảm bảo gửi hết mọi batch” nếu terminal operation có thể dừng sớm, ví dụ `limit(1)`. Muốn đảm bảo phát hết dữ liệu, cần thiết kế toàn bộ pipeline và terminal operation phù hợp với yêu cầu.

## 7. Ví dụ dừng sớm bằng chính integrator

Ngoài việc bị downstream yêu cầu dừng, Gatherer cũng có thể **chủ động dừng** sau một điều kiện. Ví dụ chỉ phát ba số dương đầu tiên, bỏ qua số không dương:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

class Counter {
    int emitted;
}

Gatherer<Integer, Counter, Integer> firstThreePositive =
        Gatherer.ofSequential(
                Counter::new,
                (state, value, downstream) -> {
                    if (value <= 0) {
                        return true; // Bỏ qua, vẫn tiếp tục.
                    }

                    state.emitted++;
                    boolean accepted = downstream.push(value);
                    return accepted && state.emitted < 3;
                });

List<Integer> result = Stream.of(-2, 4, 0, 5, 6, 7)
        .gather(firstThreePositive)
        .toList();

System.out.println(result); // [4, 5, 6]
```

Đoạn trên minh họa trong một lớp/phương thức có chỗ định nghĩa `Counter` và các biến; nó không phải chương trình độc lập như phần 5 và 6. Khi đã phát số dương thứ ba, integrator trả `false` để báo không tiếp tục tích hợp các phần tử sau đó.

**Đừng nhầm:** `false` trong giá trị trả về của integrator là **tín hiệu dừng**, không phải giá trị trả về của predicate như `filter`. Nếu bạn muốn bỏ một phần tử nhưng vẫn tìm phần tử tiếp theo, trả `true` sau khi không push phần tử ấy.

## 8. Gatherer.ofSequential và parallel Stream

Tên “Sequential” mang ý nghĩa **quy tắc tích hợp của Gatherer**: các phần tử không thể được tùy tiện chia ra, tích hợp trạng thái ở nhiều nhánh rồi gộp như một Gatherer có combiner song song hợp lệ.

Ví dụ:

```java
List<Long> input = List.of(5L, 3L, -2L, 7L);

List<SequentialGathererDemo.RunningTotal> totals = input
        .parallelStream()
        .gather(SequentialGathererDemo.runningTotals())
        .toList();
```

Với nguồn List **có encounter order**, kết quả theo ngữ nghĩa tổng lũy kế phải xét phần tử theo thứ tự logic của nguồn. `ofSequential` không tự biến thuật toán lũy kế thành một phép cộng song song được. Framework phải tôn trọng những ràng buộc của Gatherer để không dùng một phép kết hợp trạng thái không tồn tại.

Đừng suy ra rằng **mọi bước trong pipeline** bắt buộc chạy trên một thread duy nhất chỉ vì có `ofSequential`. Các giai đoạn khác có thể được triển khai theo cách thích hợp với Stream, nhưng **khả năng tăng tốc của bước trạng thái tuần tự là có giới hạn**. Đặc biệt, tên thread hoặc lịch gọi lambda không phải hợp đồng cho ứng dụng.

### 8.1. Vì sao không công bố combiner song song tùy tiện?

Giả sử nhánh A xử lý `[5, 3]` và tạo các tổng lũy kế `[5, 8]`; nhánh B xử lý `[-2, 7]` và tạo `[-2, 5]`. Để ghép thành kết quả `[5, 8, 6, 13]`, cần hiệu chỉnh toàn bộ kết quả nhánh B bằng tổng của nhánh A.

Chỉ gọi `left.addAll(right)` không đáp ứng ngữ nghĩa. Việc thiết kế một Gatherer tích hợp song song đúng nghĩa có thể cần trạng thái và phép kết hợp phức tạp, hoặc một thuật toán scan song song riêng. Với bài toán này, `ofSequential` giúp giữ đúng quy tắc mà không tự chế phép combiner sai.

### 8.2. Thứ tự của nguồn vẫn quan trọng

Nếu nguồn đến từ collection **không có encounter order**, “phần tử đầu tiên” hoặc “tổng sau phần tử thứ ba” có thể không có cùng ý nghĩa nghiệp vụ giữa các lần chạy. `ofSequential` không tự sắp xếp dữ liệu. Nếu yêu cầu thứ tự thời gian hay thứ tự mã giao dịch, cần:

- Chọn nguồn có encounter order phù hợp.
- Hoặc sắp xếp rõ bằng `sorted(comparator)` trước khi gọi `gather`, với comparator thể hiện đúng thứ tự nghiệp vụ.
- Không dùng `unordered()` khi kết quả phụ thuộc vị trí hoặc lũy kế.

Tính tuần tự của integrator **không thay thế việc xác định thứ tự đầu vào**.

## 9. So sánh ofSequential với Collector và các phép toán khác

| Đặc tính | `map` / `filter` | `reduce` / `collect` | `Gatherer.ofSequential` |
|---|---|---|---|
| Có thể giữ trạng thái cục bộ giữa các phần tử? | Không nên dựa vào trạng thái mutable ngoài lambda | Có trạng thái tích lũy để tạo kết quả cuối | Có trạng thái `A` riêng cho các bước tích hợp |
| Số đầu ra | 0 hoặc 1 đầu ra cho mỗi phần tử theo phép toán | Thường một kết quả cuối | 0, 1 hoặc nhiều đầu ra trên từng bước, có thể phát thêm khi hoàn tất |
| Hỗ trợ dừng sớm | `limit`, `takeWhile`, v.v. | Một số terminal operation short-circuit | Integrator có thể trả `false`; downstream có thể từ chối |
| Có kết hợp trạng thái song song? | Không phải mô hình stateful riêng | Có combiner đúng hợp đồng | Không yêu cầu combiner song song ở `ofSequential` |
| Trường hợp phù hợp | Ánh xạ/lọc độc lập | Tổng hợp số liệu cuối | Tổng lũy kế, chia khối, biến đổi có trạng thái |

### 9.1. Không thay reduce bằng Gatherer nếu chỉ cần tổng cuối

```java
long total = Stream.of(5L, 3L, -2L, 7L)
        .mapToLong(Long::longValue)
        .sum();
System.out.println(total); // 13
```

Viết Gatherer lũy kế rồi gọi `reduce((a, b) -> b)` để lấy tổng cuối là đường vòng khó hiểu hơn. Dùng Gatherer khi cần **các kết quả trung gian** hoặc quy tắc điều phối phần tử không có API trực tiếp phù hợp.

### 9.2. Khi cần tính theo khóa thay vì theo vị trí

Nếu chỉ muốn tổng tiền theo mã sản phẩm, `groupingBy(..., summingLong(...))` hoặc `toMap(..., Long::sum)` thể hiện rõ hơn một Gatherer tuần tự duyệt và sửa `HashMap`. Gatherer thuận lợi hơn cho xử lý **theo chuỗi phần tử liên tiếp**, chẳng hạn phát báo cáo mỗi khi gặp dấu mốc kết thúc.

### 9.3. API Gatherers có sẵn

Java 24 cung cấp một số gatherer chuẩn như `Gatherers.windowFixed`, `windowSliding`, `scan` và `fold`. Trước khi tự viết, hãy xem chúng có đúng bài toán không. Ví dụ, tổng lũy kế có thể biểu diễn bằng `Gatherers.scan`; việc tự xây qua `ofSequential` vẫn có giá trị học tập khi muốn gắn thêm đếm, kiểm tra tràn hoặc phát đối tượng mang nhiều trường.

## 10. Ràng buộc trạng thái và an toàn dữ liệu

### 10.1. Không dùng state chia sẻ giữa nhiều pipeline

Sai về nguyên tắc:

```java
// Tránh một biến mutable static được chia sẻ cho mọi lần gather:
// static final RunningState SHARED = new RunningState();
// Gatherer.ofSequential(() -> SHARED, integrator);
```

Một initializer trả lại cùng đối tượng khiến:

- Lần gọi sau có thể nối tiếp tổng của lần trước.
- Hai pipeline đang hoạt động có thể tác động lẫn nhau.
- Nếu nhiều thread truy cập, có thể tạo data race.

Hãy tạo trạng thái mới bằng constructor hoặc supplier có ý nghĩa rõ ràng, và xem Gatherer là **đặc tả phép xử lý**, không phải nơi lưu trạng thái nghiệp vụ dùng chung.

### 10.2. Không sửa nguồn khi đang duyệt

Integrator nên thực hiện phép xử lý trên phần tử đã nhận và state riêng, không xóa/thêm phần tử vào chính `List` nguồn trong lúc duyệt. Nguyên tắc *non-interference* của Stream vẫn áp dụng; việc Gatherer có trạng thái không cho phép sửa tùy tiện dữ liệu nguồn.

### 10.3. Phát snapshot thay vì tham chiếu mutable

Với output dạng danh sách hoặc bản tổng kết, nếu trạng thái bên trong có thể tiếp tục thay đổi thì cần sao chép hoặc tạo đối tượng kết quả mới:

```java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(state));
downstream.push(snapshot);
```

Việc phát chính `state` mutable rồi `clear()` trong bước kế tiếp có thể làm mọi output trong List kết quả cùng đổi nội dung.

### 10.4. Xử lý null có chủ đích

Nếu `null` là dữ liệu không hợp lệ, dùng `Objects.requireNonNull(value)` trong integrator hoặc `filter(Objects::nonNull)` trước Gatherer; nếu `null` đại diện một dấu phân cách hợp lệ, phải mô hình hóa quy tắc riêng.

Không dựa vào `toList()` hoặc `collect` để tự loại null. Một phép biến đổi có thể phát null nếu không được bảo vệ, và downstream hoặc phép toán tiếp theo có thể phản ứng khác nhau.

### 10.5. Kiểm soát số học

Tổng lũy kế với `long` có thể tràn. Ví dụ dùng `Math.addExact` để ném `ArithmeticException` khi tổng vượt miền `long`. Nếu dữ liệu là tiền tệ nhạy tính chính xác, cân nhắc đơn vị tiền nhỏ nhất, `BigDecimal` hoặc `BigInteger` theo yêu cầu; đừng mặc định `double` là chính xác tuyệt đối.

## 11. Chi phí bộ nhớ, ngắn mạch và nguồn I/O

Một Gatherer tuần tự **không bắt buộc lưu toàn bộ đầu vào**. Ví dụ lũy kế chỉ giữ hai số `long`, có chi phí trạng thái `O(1)`. Ví dụ chia khối giữ tối đa `batchSize` phần tử, chi phí trạng thái `O(batchSize)`; nếu downstream `toList()` giữ mọi khối thì bộ nhớ đầu ra vẫn tăng theo số phần tử được giữ.

| Thiết kế | Bộ nhớ trạng thái Gathering | Khả năng phát kết quả |
|---|---|---|
| Tổng lũy kế | `O(1)` | Phát một kết quả mỗi phần tử |
| Đếm thứ tự | `O(1)` | Phát một kết quả mỗi phần tử |
| Chia khối kích thước `k` | `O(k)` | Phát một danh sách mỗi `k` phần tử và khối cuối |
| Tích lũy toàn bộ để phát một lần | `O(n)` | Có thể phát ở finisher, tốn bộ nhớ |

### 11.1. Lazy không có nghĩa không có trạng thái

Gọi `stream.gather(gatherer)` chưa cần duyệt phần tử; khi terminal operation chạy, initializer/integrator mới tham gia xử lý theo nhu cầu. Tuy nhiên, khi đã bắt đầu tiêu thụ, Gatherer có thể giữ state qua nhiều phần tử cho tới khi hoàn tất. Nếu tạo nhiều pipeline dùng chung một biến state ngoài, tính lazy còn khiến thời điểm cập nhật trở nên khó dự đoán.

### 11.2. Short-circuit và việc không đọc hết nguồn

`limit`, `findFirst`, `anyMatch` và các terminal operation ngắn mạch có thể ngừng pipeline trước khi toàn bộ đầu vào được tích hợp. Vì thế, không dùng số lần gọi integrator hay finisher làm thước đo chắc chắn “đã xử lý mọi dữ liệu nguồn”. Khi thiết kế một Gatherer phát dữ liệu ở finisher, phải kiểm tra sự tương tác với downstream từ chối nhận thêm.

### 11.3. Stream gắn I/O vẫn cần đóng

`Gatherer.ofSequential` không đóng thay một nguồn mở bằng `Files.lines`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

// Bên trong phương thức có path và gatherer đã được định nghĩa:
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> result = lines
            .gather(gatherer)
            .toList();
}
```

Đoạn này minh họa scope tài nguyên; `path` và `gatherer` cần được khai báo trong code thực tế. `toList()` kích hoạt xử lý nhưng không thay `try-with-resources`. Nếu integrator ném ngoại lệ, việc đóng nguồn vẫn được thực hiện khi rời khối `try`.

## 12. Kiểm thử một Gatherer.ofSequential

Không chỉ test với một danh sách có kích thước chẵn. Hãy tạo một **ma trận trường hợp biên** phù hợp ngữ nghĩa:

| Ca kiểm thử | Tổng lũy kế | Chia khối |
|---|---|---|
| Nguồn rỗng | Danh sách output rỗng | Danh sách khối rỗng |
| Một phần tử | Một tổng bằng phần tử đó | Một khối chứa một phần tử |
| Số phần tử bằng kích thước khối | Không liên quan | Không phát thêm khối rỗng ở finisher |
| Số phần tử không chia hết cho kích thước khối | Không liên quan | Khối cuối có số phần tử còn lại |
| Có số âm/0 | Cộng chính xác theo hợp đồng nghiệp vụ | Nếu hợp lệ, vẫn tạo khối |
| Dữ liệu null | Lọc/báo lỗi theo chính sách | Lọc/báo lỗi theo chính sách |
| Tổng vượt `long` | Ném `ArithmeticException` | Không liên quan |
| Chạy hai pipeline liên tiếp | State không bị giữ từ lần trước | Bộ đệm khối mới, không lẫn phần tử |
| Nguồn có thứ tự vs unordered | Đảm bảo thứ tự nghiệp vụ trước | Không kỳ vọng ranh giới khối theo thứ tự không có bảo đảm |
| Terminal operation dừng sớm | Không khẳng định đã đọc toàn nguồn | Không giả định tất cả khối đều được phát |

### 12.1. Kiểm thử giản lược cho tổng lũy kế

Trong lớp `SequentialGathererDemo` ở phần 5, có thể thêm:

```java
List<RunningTotal> result = Stream.of(2L, -2L, 5L)
        .gather(runningTotals())
        .toList();

if (result.size() != 3
        || result.get(0).totalCents != 2L
        || result.get(1).totalCents != 0L
        || result.get(2).totalCents != 5L) {
    throw new AssertionError("Tổng lũy kế sai");
}
```

Với kiểm thử tự động, có thể dùng JUnit để kiểm tra các trường hợp trong bảng, đặc biệt là nguồn rỗng và nhiều lần gọi Gatherer. Tính đúng của thuật toán có trạng thái không được xác nhận chỉ bằng một lần chạy không lỗi.

## 13. Các lỗi thường gặp khi dùng ofSequential

| Cách làm sai | Hậu quả | Cách sửa |
|---|---|---|
| Trả `false` khi chỉ muốn bỏ một phần tử | Ngừng tích hợp các phần tử còn lại | Bỏ `push` nhưng trả `true` |
| Luôn trả `true` sau khi `downstream.push` từ chối | Có thể duyệt nguồn thừa khi đã đủ đầu ra | Truyền tín hiệu dừng khi thích hợp |
| Initializer trả cùng đối tượng static | State giữa các lần chạy bị lẫn; có thể race | Tạo đối tượng state mới |
| `push(state)` rồi tiếp tục sửa chính state | Các output có thể trỏ tới một đối tượng bị đổi | Phát snapshot hoặc DTO mới |
| Quên finisher trong Gatherer chia khối | Mất khối cuối không đủ kích thước | Dùng overload có finisher |
| Finisher phát khối rỗng khi dữ liệu vừa đủ | Thừa một khối rỗng | Kiểm tra `!state.isEmpty()` |
| Suy `ofSequential` tự sắp xếp dữ liệu | Lũy kế theo thứ tự sai | Bảo đảm encounter order của nguồn |
| Mong `parallel()` tăng tốc bước trạng thái tuần tự | Tốc độ không tăng như kỳ vọng | Benchmark và chọn thuật toán phù hợp |
| Dùng Gatherer để thay `sum()` mà chỉ cần tổng | Code phức tạp hơn cần thiết | Dùng primitive `sum` / `reduce` |
| Gọi `gather` trên JDK 21 | Lỗi API không tồn tại | Dùng JDK 24+ hoặc chiến lược tương thích |
| Quên đóng `Files.lines` | Rò rỉ file handle | `try-with-resources` |
| Dùng biến đếm ngoài `peek` thay state Gatherer | Side effect, race, tối ưu hóa có thể bỏ qua | Giữ state cục bộ trong Gatherer |

## 14. Bài tập thực hành có hướng dẫn và đáp án

### Bài 1. Đánh số thứ tự từng phần tử

**Đề bài:** Viết Gatherer nhận `String`, phát `"1:A"`, `"2:B"`, `"3:C"` từ Stream `["A", "B", "C"]`. Không dùng biến đếm bên ngoài pipeline.

**Đáp án tham khảo:**

```java
class State {
    long index;
}

Gatherer<String, State, String> numbered = Gatherer.ofSequential(
        State::new,
        (state, value, downstream) -> {
            state.index++;
            return downstream.push(state.index + ":" + value);
        });

List<String> out = Stream.of("A", "B", "C")
        .gather(numbered)
        .toList();
// [1:A, 2:B, 3:C]
```

Các khai báo này minh họa trong một scope có import `Gatherer`, `List` và `Stream`.

### Bài 2. Dự đoán kết quả tổng lũy kế

**Đề bài:** Đầu vào `[10, -3, 5, 0]`, Gatherer tổng lũy kế ở phần 5 phát những giá trị tổng nào?

**Đáp án:** `[10, 7, 12, 12]` theo đúng thứ tự đầu vào. Nếu chỉ cần tổng cuối là `12`, `mapToLong(...).sum()` là lựa chọn đơn giản hơn.

### Bài 3. Vì sao không được trả false khi gặp số âm?

**Đề bài:** Gatherer chỉ phát số dương từ `[-1, 2, 3]`. Nếu nhánh xử lý số âm `return false` thì kết quả là gì?

**Đáp án:** Gatherer dừng ngay tại `-1` và không xét `2` hoặc `3`, dẫn tới output rỗng. Để **lọc** số âm, bỏ `push` nhưng trả `true`.

### Bài 4. Chia khối khi số phần tử không chia hết

**Đề bài:** `batchesOf(3)` xử lý `["A", "B", "C", "D", "E"]`. Kết quả là gì?

**Đáp án:** `[[A, B, C], [D, E]]`. Khối thứ hai do finisher phát; nếu không có finisher, hai phần tử cuối có thể bị mất.

### Bài 5. Kiểm tra state dùng chung

**Đề bài:** Một Gatherer được tạo bằng `Gatherer.ofSequential(() -> SHARED_STATE, integrator)`, trong đó `SHARED_STATE` là biến static mutable. Có thể chạy hai pipeline độc lập an toàn không?

**Đáp án:** Không có bảo đảm độc lập. Cả hai lần chạy có thể sử dụng cùng state và lẫn số đếm; nếu chạy đồng thời còn có thể tạo race. Hãy dùng `State::new` để tạo state mới.

### Bài 6. Phát snapshot

**Đề bài:** Trong Gatherer chia khối, integrator viết `downstream.push(state); state.clear();`. Tại sao List kết quả có thể sai?

**Đáp án:** `state` là cùng một List mutable; downstream có thể giữ tham chiếu đó. Gọi `clear` sau `push` làm mất nội dung của khối đã phát. Hãy tạo `new ArrayList<>(state)` rồi mới `clear`.

### Bài 7. Dừng sau N phần tử phù hợp

**Đề bài:** Dùng Gatherer để chỉ phát hai chuỗi đầu tiên có độ dài từ ba ký tự trở lên. Phải làm gì sau khi phát chuỗi thứ hai?

**Đáp án định hướng:** Dùng state đếm **số chuỗi đã phát**, bỏ qua chuỗi ngắn bằng cách trả `true`, còn sau khi phát chuỗi thứ hai thì trả `false` (hoặc kết hợp kết quả `downstream.push` với điều kiện còn được phát). Không được đếm cả chuỗi bị bỏ.

### Bài 8. ofSequential và unordered source

**Đề bài:** Muốn đánh số thứ tự giao dịch theo thời gian, có nên dùng `HashSet.stream().gather(numbered)` không?

**Đáp án:** Không nếu chưa có thứ tự nghiệp vụ. `HashSet` không bảo đảm encounter order, nên thứ tự đánh số có thể không xác định theo timestamp. Chọn List đã sắp xếp hoặc dùng `sorted(Comparator.comparing(Transaction::getTime))` trước Gatherer.

### Bài 9. Chọn API đơn giản nhất

**Đề bài:** Chỉ cần nhóm các số thành danh sách có khối cỡ 4 trên JDK 24. Có cần tự viết `ofSequential` không?

**Đáp án:** Không bắt buộc. `Gatherers.windowFixed(4)` là gatherer chuẩn cho bài toán cửa sổ cố định. Tự viết `ofSequential` có giá trị khi học API hoặc khi cần quy tắc phát khối riêng mà API chuẩn không đáp ứng.

## 15. Checklist khi tự xây Gatherer tuần tự

Trước khi đưa Gatherer tùy biến vào ứng dụng:

1. **Mức JDK đã phù hợp chưa?** `Gatherer` và `Stream.gather` dùng trực tiếp từ Java 24+.
2. **Đã xác định `T`, `A`, `R` chưa?** Phần tử đầu vào, trạng thái và phần tử đầu ra không nhất thiết cùng kiểu.
3. **Initializer có tạo trạng thái mới không?** Không dùng state mutable chia sẻ giữa các lần chạy.
4. **Integrator có xử lý được 0/1/n đầu ra không?** Phân biệt bỏ phần tử với dừng pipeline.
5. **Đã kiểm tra giá trị boolean từ `downstream.push` chưa?** Không tiếp tục tiêu thụ nguồn không cần thiết khi downstream từ chối.
6. **Có cần finisher không?** Nếu còn dữ liệu đệm khi kết thúc, phải có cách phát nốt.
7. **Có phát snapshot của mutable state không?** Tránh để đầu ra thay đổi sau khi đã push.
8. **Nguồn có encounter order đúng nghiệp vụ không?** `ofSequential` không tự sắp xếp.
9. **Có trường hợp trống, null, tràn số, dừng sớm hoặc chạy nhiều lần không?** Test đầy đủ.
10. **Có thực sự cần Gatherer tùy biến không?** Ưu tiên `map`, `filter`, `reduce`, `collect` hoặc `Gatherers` chuẩn nếu đơn giản hơn.
11. **Có giới hạn hiệu năng/tài nguyên không?** Bước stateful tuần tự có thể hạn chế khả năng tăng tốc từ parallel stream.
12. **Có nguồn I/O cần đóng không?** `gather` và terminal operation không thay `try-with-resources`.

**Kết luận:** `Gatherer.ofSequential` là lựa chọn cho phép **chuyển đổi có trạng thái theo trình tự** trên Java Stream mà không phải tự thiết kế một combiner song song. Để viết đúng, hãy tách rõ **initializer tạo state mới**, **integrator cập nhật state và đẩy đầu ra**, **boolean quyết định tiếp tục/dừng**, và **finisher phát phần còn lại khi cần**. Khi giữ được thứ tự nguồn, không chia sẻ mutable state, phát snapshot an toàn và kiểm thử các tình huống rỗng/ngắn mạch, Gatherer tùy biến trở thành công cụ hữu ích cho các pipeline Java Stream nâng cao mà vẫn có ngữ nghĩa rõ ràng.
