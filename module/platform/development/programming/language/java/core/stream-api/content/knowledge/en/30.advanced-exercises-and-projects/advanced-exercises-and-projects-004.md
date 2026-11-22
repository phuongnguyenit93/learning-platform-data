# Viết Gatherer xử lý nhóm liên tiếp và cửa sổ dữ liệu

Trong nhiều bài toán xử lý chuỗi sự kiện, kết quả không phụ thuộc riêng từng phần tử mà phụ thuộc **những phần tử kề nhau**: một đợt trạng thái liên tiếp, một phiên hoạt động, một dãy số cùng loại hoặc một cửa sổ các phép đo gần nhất. `filter` và `map` xử lý rất tốt từng phần tử; `groupingBy` thu thập toàn bộ phần tử theo khóa; nhưng chúng không trực tiếp diễn tả quy tắc “gom những phần tử **đứng cạnh nhau** rồi phát một kết quả trung gian để tiếp tục pipeline”.

**Stream Gatherers** cung cấp cơ chế tạo thao tác trung gian có trạng thái và có thể phát **0, 1 hoặc nhiều phần tử** đầu ra. Bài học thuộc chương **Bài tập nâng cao và dự án** của module `JAVA_STREAM_API`: chúng ta sẽ tự viết Gatherer cho **nhóm liên tiếp** và **cửa sổ dữ liệu**, đối chiếu với `Gatherers.windowFixed` và `Gatherers.windowSliding`, triển khai một bài toán giám sát sự kiện, kiểm tra tình huống biên và cân nhắc hiệu năng, tài nguyên, thứ tự, xử lý song song.

> **Yêu cầu phiên bản:** API `java.util.stream.Gatherer`, `Gatherers` và thao tác `Stream.gather(...)` được hoàn thiện chính thức trong **Java 24 (JEP 485)**. Java 22 và 23 từng có phiên bản preview với hợp đồng/cú pháp có thể khác; **Java 8–21 không có API chuẩn này**. Các đoạn mã chính hướng tới Java 24 trở lên, không sử dụng cờ `--enable-preview` trên Java 24. Nếu hệ thống chưa thể nâng JDK, có thể dùng vòng lặp hoặc một phép thu thập có trạng thái phù hợp thay vì sao chép nguyên mã Gatherer.

## 1. Xác định yêu cầu trước khi viết Gatherer

Giả sử có chuỗi trạng thái theo thời gian:

```text
A, A, A, B, B, A, C, C
```

Có hai cách nhóm rất khác nhau:

| Nhu cầu | Kết quả mong muốn | Công cụ phù hợp |
| --- | --- | --- |
| Nhóm tất cả phần tử có cùng khóa, không quan tâm vị trí | A → [A,A,A,A], B → [B,B], C → [C,C] | `Collectors.groupingBy` |
| Nhóm **các đoạn liên tiếp** có cùng khóa | [A,A,A], [B,B], [A], [C,C] | Gatherer giữ trạng thái nhóm hiện hành |
| Cắt thành các khối cố định, không chồng lặp | [A,A,A], [B,B,A], [C,C] | `Gatherers.windowFixed(3)` |
| Tạo cửa sổ trượt kích thước 3 | [A,A,A], [A,A,B], [A,B,B], ... | `Gatherers.windowSliding(3)` |
| Tạo cửa sổ trượt **chỉ khi đủ 3 phần tử** | Các đoạn dài 3, không phát cửa sổ thiếu phần tử | Gatherer tùy chỉnh có quy tắc phát rõ ràng |

Khái niệm **nhóm liên tiếp** cần một encounter order có ý nghĩa. Nếu nguồn là một tập không có thứ tự hoặc các sự kiện chưa sắp theo thời gian, “liên tiếp” sẽ phản ánh thứ tự duyệt tình cờ chứ không nhất thiết là thứ tự nghiệp vụ.

**Câu hỏi thiết kế cốt lõi:** Một kết quả được phát ra khi nào? Khi thấy khóa khác, khi đếm đủ `k` phần tử, hay khi nguồn kết thúc? Chính câu trả lời quyết định cách dùng `integrator` và `finisher`.

## 2. Gatherer nằm ở đâu trong pipeline?

`gather(...)` là **intermediate operation**, không phải terminal operation:

```text
Nguồn Stream<T>
      |
  filter/map
      |
  gather(custom Gatherer<T, A, R>)
      |             ├─ initializer: tạo trạng thái A
      |             ├─ integrator: nhận T, cập nhật A, có thể push R
      |             ├─ combiner: gộp A nếu hỗ trợ parallel
      |             └─ finisher: phát kết quả còn lại khi kết thúc
      |
  map/filter/flatMap
      |
  collect / toList / reduce / count      ← terminal
      |
  Kết quả
```

Khái niệm kiểu dữ liệu:

- `T`: đầu vào Gatherer;
- `A`: trạng thái tích lũy nội bộ;
- `R`: phần tử đầu ra được Gatherer phát sang downstream.

Ví dụ `Gatherer<String, ?, List<String>>` nhận từng chuỗi và phát ra từng **nhóm chuỗi**, chứ không trả một `Map` cuối cùng.

Một Gatherer có những thành phần tương tự collector nhưng vai trò khác:

| Thành phần | Chức năng |
| --- | --- |
| `initializer` | Tạo trạng thái `A` cho quá trình tích lũy |
| `integrator` | Nhận một phần tử `T` và quyết định cập nhật trạng thái, phát `R` hay dừng |
| `combiner` | Phối hợp trạng thái các nhánh khi Gatherer có hợp đồng cho phép |
| `finisher` | Xử lý trạng thái còn lại khi upstream kết thúc |
| `Downstream.push(R)` | Chuyển một phần tử `R` xuống bước tiếp theo |

Đặc biệt, `integrator` có kết quả kiểu `boolean`: trả `true` nếu còn cho phép nhận phần tử, trả `false` nếu không cần tiếp tục. `Downstream.push(value)` cũng trả `boolean` cho biết downstream có còn muốn nhận thêm dữ liệu hay không.

Không được hiểu `push` là thao tác ghi trực tiếp vào `List` cuối cùng. Nó chỉ phát phần tử sang bước kế tiếp; phía sau còn có thể có `filter`, `limit`, `map` hoặc một Gatherer khác.

## 3. ofSequential và lý do chọn Gatherer tuần tự

Với bài toán dựa vào **ranh giới giữa phần tử trước và phần tử sau**, cách đơn giản nhất là dùng `Gatherer.ofSequential(...)`.

Dạng ý tưởng:

```java
Gatherer.ofSequential(
        initializer,
        integrator,
        finisher
);
```

Trong đó:

- `initializer` cấp trạng thái mới;
- `integrator` xử lý từng phần tử theo logic liền kề;
- `finisher` phát phần cuối còn nằm trong bộ đệm.

Không phải Gatherer nào cũng cần finisher; nếu mọi kết quả đã được phát khi nhận phần tử, có thể dùng overload `ofSequential(initializer, integrator)`.

`ofSequential` phù hợp vì trạng thái “nhóm hiện tại” hoặc “cửa sổ các phần tử trước đó” phụ thuộc vào thứ tự. Nếu viết một `combiner` cho phép chia xử lý song song, ta phải giải quyết đúng **nhóm nối qua ranh giới hai nhánh**, không chỉ nối hai danh sách kết quả. Không nên tự tạo combiner ghép kết quả một cách tùy ý rồi cho rằng đã song song hóa đúng bài toán.

Việc gọi `parallel()` ở upstream **không phải** bảo đảm Gatherer tuần tự sẽ chạy nhanh hơn. Phần trước Gatherer có thể có tính chất khác, còn phép biến đổi dựa trên thứ tự vẫn phải duy trì đúng hợp đồng.

## 4. Bài tập 1: gom nhóm các phần tử liên tiếp theo khóa

### Yêu cầu và ví dụ

Từ các mã:

```text
A, A, B, B, B, A, C, C
```

Tạo các nhóm:

```text
[A, A]
[B, B, B]
[A]
[C, C]
```

Nhóm `A` thứ ba **không được nhập** với nhóm `A` đầu tiên vì giữa chúng có ba phần tử `B`. Đây là điểm khác `groupingBy`.

Quy tắc trạng thái:

1. Chưa có nhóm → mở nhóm bằng khóa phần tử đầu tiên.
2. Khóa mới bằng khóa nhóm hiện tại → thêm phần tử.
3. Khóa mới khác khóa hiện tại → **phát bản sao nhóm cũ**, rồi bắt đầu nhóm mới.
4. Nguồn kết thúc → **phát nhóm cuối** trong finisher.
5. Nếu downstream không muốn nhận thêm → dừng và không phát phần tồn dư nữa.

### Triển khai hoàn chỉnh

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Gatherer;

public final class RunGatherers {
    private RunGatherers() {}

    private static final class RunState<T, K> {
        boolean active;
        boolean cancelled;
        K currentKey;
        final List<T> current = new ArrayList<>();
    }

    public static <T, K> Gatherer<T, ?, List<T>> consecutiveBy(
            Function<? super T, ? extends K> classifier) {

        Objects.requireNonNull(classifier, "classifier");

        return Gatherer.ofSequential(
                () -> new RunState<T, K>(),

                (state, element, downstream) -> {
                    K key = classifier.apply(element);

                    // Phần tử đầu tiên của nhóm.
                    if (!state.active) {
                        state.active = true;
                        state.currentKey = key;
                        state.current.add(element);
                        return true;
                    }

                    // Cùng khóa với nhóm hiện tại.
                    if (Objects.equals(state.currentKey, key)) {
                        state.current.add(element);
                        return true;
                    }

                    // Đổi khóa: phát bản sao của nhóm đã hoàn thành.
                    List<T> completed =
                            new ArrayList<>(state.current);

                    if (!downstream.push(completed)) {
                        state.cancelled = true;
                        state.current.clear();
                        return false;
                    }

                    state.current.clear();
                    state.currentKey = key;
                    state.current.add(element);
                    return true;
                },

                (state, downstream) -> {
                    // Nhóm cuối không có phần tử đổi khóa để kích hoạt push.
                    if (!state.cancelled
                            && state.active
                            && !state.current.isEmpty()) {
                        downstream.push(
                                new ArrayList<>(state.current)
                        );
                    }
                }
        );
    }
}
```

**Cách dùng:**

```java
import java.util.List;
import java.util.stream.Stream;

List<List<String>> runs = Stream.of(
        "A", "A", "B", "B", "B", "A", "C", "C"
).gather(RunGatherers.consecutiveBy(s -> s))
 .toList();

System.out.println(runs);
// [[A, A], [B, B, B], [A], [C, C]]
```

Trong lớp trên, kiểu `RunState<T, K>` là dữ liệu **riêng của Gatherer**, không phải kết quả công khai. `current` chỉ giữ một nhóm chưa hoàn tất. `currentKey` lưu khóa của nhóm hiện tại; `active` phân biệt “chưa bắt đầu” với “đang có nhóm có khóa null”.

### Vì sao phải dùng Objects.equals?

Nếu classifier có thể trả `null`, viết `currentKey.equals(key)` sẽ gây `NullPointerException`. Trong ví dụ, `Objects.equals(currentKey, key)` coi hai khóa null là cùng một khóa và không nhầm với trạng thái chưa có nhóm nhờ `active`.

Điều này khác `Collectors.groupingBy`: classifier của `groupingBy` không chấp nhận trả `null` theo hợp đồng. Gatherer tự định nghĩa có thể chọn chính sách khóa null riêng, miễn mã xử lý và kiểu dữ liệu downstream nhất quán.

Nếu **bản thân phần tử đầu vào** có thể là null, mã tổng quát vẫn có thể chứa phần tử đó trong `ArrayList`; classifier phải xử lý null một cách hợp lệ. Không nên mặc định mọi `Function<T,K>` đều hỗ trợ đầu vào null.

## 5. Bước qua ranh giới: integrator và finisher phối hợp ra sao?

Xem chuỗi `A, A, B`:

```text
Đọc A:
    active = true, currentKey = A, current = [A]
    chưa phát

Đọc A:
    current = [A, A]
    chưa phát

Đọc B:
    phát snapshot [A, A]
    currentKey = B, current = [B]

Nguồn kết thúc:
    finisher phát snapshot [B]
```

Nếu quên finisher, nhóm cuối sẽ bị mất. Nếu phát thẳng `state.current` rồi gọi `clear()`, downstream có thể giữ tham chiếu tới **cùng một List đã bị xóa sạch**, khiến kết quả trước đó bị hỏng.

Vì vậy, mỗi lần phát dùng `new ArrayList<>(state.current)`. Đó là một **bản sao tách khỏi bộ đệm mutable**; ta không thay đổi nó nữa sau khi phát.

### Downstream có thể dừng sớm

Ví dụ chỉ cần nhóm đầu:

```java
List<List<String>> firstRun = Stream.of(
        "A", "A", "B", "B", "C"
).gather(RunGatherers.consecutiveBy(s -> s))
 .limit(1)
 .toList();

System.out.println(firstRun); // [[A, A]]
```

Khi Gatherer thấy phần tử `B`, nó phát nhóm `[A, A]`. `limit(1)` đã nhận đủ một đầu ra, nên `downstream.push(...)` có thể trả `false`: Gatherer phải dừng và không phát nhóm `B` trong finisher.

Do đó ví dụ cài đặt ghi `state.cancelled = true` rồi trả `false`. Đừng bỏ qua kết quả của `push` một cách vô điều kiện. **Dừng sớm của downstream không tự đóng nguồn I/O**; nếu upstream là `Files.lines`, vẫn phải dùng `try-with-resources`.

## 6. Những trường hợp biên của nhóm liên tiếp

| Nguồn | Kết quả |
| --- | --- |
| Rỗng | `[]` |
| `[A]` | `[[A]]` |
| `[A,A,A]` | `[[A,A,A]]` |
| `[A,B,A]` | `[[A],[B],[A]]` |
| `[A,A,B]` | `[[A,A],[B]]` |
| `[A,B,B]` | `[[A],[B,B]]` |
| `[null,null,A,null]` khi classifier là identity | `[[null,null],[A],[null]]` |

Với nguồn rỗng, `active` vẫn là `false`; finisher không phát nhóm nào. Với khóa cuối cùng không có phần tử đổi khóa theo sau, finisher hoàn tất nhóm.

Một nhóm có thể rất dài, thậm chí dài bằng toàn bộ nguồn. Bản triển khai trả `List<T>` phải giữ tất cả phần tử của nhóm đó trong bộ nhớ; **không có bảo đảm bộ nhớ `O(1)` theo độ dài nhóm**. Nếu chỉ cần đếm hoặc tính tổng theo từng đoạn, nên lưu trạng thái tổng hợp nhỏ thay vì toàn bộ phần tử.

## 7. Biến thể tiết kiệm bộ nhớ: phát thống kê mỗi nhóm

Dữ liệu log có thể chứa hàng triệu sự kiện cùng loại liên tiếp. Nếu chỉ muốn biết **khóa và số lượng** của mỗi đợt, không cần giữ toàn bộ sự kiện.

Ví dụ có `record` kết quả:

```java
record RunCount<K>(K key, long count) {}
```

Trạng thái chỉ cần `key`, `count`, `active` và `cancelled`. Ý tưởng triển khai:

```java
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Gatherer;

static <T, K> Gatherer<T, ?, RunCount<K>> countRuns(
        Function<? super T, ? extends K> classifier) {

    class State {
        K key;
        long count;
        boolean active;
        boolean cancelled;
    }

    return Gatherer.ofSequential(
            State::new,
            (state, element, downstream) -> {
                K key = classifier.apply(element);

                if (!state.active) {
                    state.active = true;
                    state.key = key;
                    state.count = 1;
                    return true;
                }

                if (Objects.equals(state.key, key)) {
                    state.count++;
                    return true;
                }

                if (!downstream.push(
                        new RunCount<>(state.key, state.count))) {
                    state.cancelled = true;
                    return false;
                }

                state.key = key;
                state.count = 1;
                return true;
            },
            (state, downstream) -> {
                if (state.active && !state.cancelled) {
                    downstream.push(
                            new RunCount<>(state.key, state.count));
                }
            }
    );
}
```

Kết quả:

```java
List<RunCount<String>> counts = Stream.of(
        "A", "A", "B", "A", "A", "A"
).gather(countRuns(s -> s)).toList();

System.out.println(counts);
// [RunCount[key=A, count=2], RunCount[key=B, count=1],
//  RunCount[key=A, count=3]]
```

Bộ nhớ trạng thái nội bộ của biến thể này là `O(1)` mỗi nhóm, không tính danh sách kết quả mà terminal `toList()` tạo. Với bộ đếm `long`, vẫn cần cân nhắc tràn số nếu một nhóm có số lượng vượt `Long.MAX_VALUE`.

> **Điểm thiết kế:** Nếu cần giữ toàn bộ các phần tử trong nhóm, dùng Gatherer phát `List<T>`. Nếu chỉ cần tổng hợp, hãy phát một **DTO thống kê nhỏ**. Việc lựa chọn hình dạng đầu ra quyết định phần lớn chi phí bộ nhớ.

## 8. Bài tập 2: cửa sổ cố định và cửa sổ trượt

“Cửa sổ” (*window*) là một nhóm gồm các phần tử gần nhau trong một dãy có thứ tự. Có hai loại cơ bản.

### Cửa sổ cố định không chồng lặp

Với kích thước `3`:

```text
Nguồn:  1 2 3 4 5 6 7 8

Window 1: [1 2 3]
Window 2:       [4 5 6]
Window 3:             [7 8]   ← phần cuối chưa đủ 3
```

Đây là cách chia thành các lô liên tiếp; các lô **không chồng lặp**.

### Cửa sổ trượt chồng lặp

Với kích thước `3`:

```text
Nguồn:  1 2 3 4 5

Window 1: [1 2 3]
Window 2:   [2 3 4]
Window 3:     [3 4 5]
```

Mỗi cửa sổ đầy đủ dịch một phần tử, nên các phần tử ở giữa xuất hiện trong nhiều cửa sổ. Bài toán điển hình là trung bình trượt, phát hiện xu hướng hoặc kiểm tra ba sự kiện gần nhất.

**Cần ghi rõ chính sách cửa sổ thiếu phần tử:** cửa sổ cố định thường muốn phát lô cuối dù thiếu, còn một thuật toán thống kê có thể chỉ muốn cửa sổ trượt **đủ `k` phần tử**. Các yêu cầu này khác nhau, nên ta sẽ định nghĩa rõ hợp đồng của từng biến thể tự viết.

## 9. Factory có sẵn trong Java 24: Gatherers.windowFixed và windowSliding

Trước khi tự xây, kiểm tra hai Gatherer chuẩn:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> fixed = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
        .gather(Gatherers.windowFixed(3))
        .toList();

System.out.println(fixed);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Với sliding window:

```java
List<List<Integer>> sliding = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(sliding);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Hai factory chuẩn diễn đạt bài toán ngắn gọn và tránh viết lại logic trạng thái. Chúng trả các cửa sổ dưới dạng danh sách; **không nên sửa danh sách đầu ra** nếu không có nhu cầu và hợp đồng mutability rõ ràng.

Các factory yêu cầu kích thước cửa sổ **dương**; `0` hoặc giá trị âm là cấu hình không hợp lệ. Với kích thước lớn, hãy tính đến bộ nhớ giữ phần tử và số lượng bản sao cửa sổ được tạo.

**Chú ý về trường hợp ngắn hơn kích thước:** khi áp dụng `Gatherers.windowSliding` chuẩn, hãy kiểm tra chính sách cửa sổ chưa đủ kích thước theo hợp đồng JDK đang sử dụng. Bản tùy chỉnh `fullSliding` ở phần sau **cố ý không phát** cửa sổ thiếu phần tử, để thuật toán kiểm tra ngưỡng có ý nghĩa thống nhất.

## 10. Tự viết cửa sổ cố định có phát lô cuối

Mục tiêu: phát một cửa sổ mỗi khi có đủ `size` phần tử; khi nguồn kết thúc, phát phần còn lại nếu không rỗng.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;

public final class FixedWindowGatherers {
    private FixedWindowGatherers() {}

    private static final class State<T> {
        final List<T> bucket = new ArrayList<>();
        boolean cancelled;
    }

    public static <T> Gatherer<T, ?, List<T>> fixed(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        return Gatherer.ofSequential(
                () -> new State<T>(),

                (state, element, downstream) -> {
                    state.bucket.add(element);

                    if (state.bucket.size() < size) {
                        return true;
                    }

                    List<T> completed =
                            new ArrayList<>(state.bucket);
                    state.bucket.clear();

                    boolean wantsMore = downstream.push(completed);
                    if (!wantsMore) {
                        state.cancelled = true;
                    }
                    return wantsMore;
                },

                (state, downstream) -> {
                    if (!state.cancelled
                            && !state.bucket.isEmpty()) {
                        downstream.push(
                                new ArrayList<>(state.bucket));
                    }
                }
        );
    }
}
```

Ví dụ:

```java
import java.util.List;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 8)
        .boxed()
        .gather(FixedWindowGatherers.fixed(3))
        .toList();

System.out.println(windows);
// [[1, 2, 3], [4, 5, 6], [7, 8]]
```

Đặc điểm:

- Bộ đệm giữ tối đa `size` phần tử trước khi phát.
- Khi đủ kích thước, tích lũy tạo **snapshot** rồi xóa bộ đệm.
- `finisher` phát lô cuối nếu còn phần tử.
- Nếu downstream đã yêu cầu dừng, `cancelled` ngăn finisher phát thêm.

Với `n > 0` phần tử, số cửa sổ cố định là `ceil(n / size)`; với nguồn rỗng, không phát cửa sổ. Tài nguyên trạng thái đang tích lũy có kích thước `O(size)`, chưa tính các cửa sổ đã được giữ ở downstream.

## 11. Tự viết cửa sổ trượt chỉ phát cửa sổ đầy đủ

Mục tiêu chính xác của `fullSliding(size)`:

- Nếu còn ít hơn `size` phần tử → **chưa phát gì**.
- Khi nhận đủ `size` phần tử → phát cửa sổ đầu tiên.
- Mỗi phần tử mới → bỏ phần tử cũ nhất, thêm phần tử mới, phát cửa sổ mới.
- **Không phát cửa sổ thiếu** ở cuối nguồn.
- Nếu downstream từ chối thêm dữ liệu → trả `false` và dừng.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public final class WindowGatherers {
    private WindowGatherers() {}

    private static final class WindowState<T> {
        final Deque<T> buffer = new ArrayDeque<>();
    }

    public static <T> Gatherer<T, ?, List<T>> fullSliding(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        return Gatherer.ofSequential(
                () -> new WindowState<T>(),

                (state, element, downstream) -> {
                    // ArrayDeque không nhận phần tử null.
                    state.buffer.addLast(
                            Objects.requireNonNull(element, "element")
                    );

                    if (state.buffer.size() > size) {
                        state.buffer.removeFirst();
                    }

                    if (state.buffer.size() == size) {
                        return downstream.push(
                                new ArrayList<>(state.buffer)
                        );
                    }

                    return true;
                }
        );
    }
}
```

Cách dùng:

```java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
        .gather(WindowGatherers.fullSliding(3))
        .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Ở mỗi lần phát, `new ArrayList<>(state.buffer)` tạo bản sao độc lập, tránh việc lần `removeFirst` tiếp theo làm thay đổi cửa sổ đã đưa xuống downstream.

**Giới hạn cụ thể:** `ArrayDeque` không nhận phần tử null. Bản triển khai trên chủ động từ chối null bằng `Objects.requireNonNull`; nếu hệ thống cần một dãy có các giá trị null hợp lệ, hãy chọn một buffer khác hoặc biểu diễn dữ liệu thiếu bằng kiểu dữ liệu rõ nghĩa.

### Tại sao không cần finisher?

Vì chính sách đã nêu chỉ phát **cửa sổ đầy đủ**, không có phần tồn dư cần phát khi kết thúc. Bất kỳ buffer có ít hơn `size` phần tử lúc hết nguồn đều không phải cửa sổ hợp lệ theo hợp đồng của bài tập này.

Đây là khác biệt quan trọng với cửa sổ cố định ở phần 10: **finisher có hay không phụ thuộc ngữ nghĩa mong muốn**, không phải bước bắt buộc cho mọi Gatherer.

## 12. Công thức đếm và độ phức tạp

Giả sử nguồn có `n` phần tử, kích thước cửa sổ `k > 0`.

| Thuật toán | Số phần tử đầu ra | Bộ nhớ trạng thái | Chi phí tạo kết quả |
| --- | --- | --- | --- |
| `consecutiveBy` phát `List<T>` | Số đoạn có khóa liên tiếp | `O(độ dài đoạn lớn nhất)` | Tổng số phần tử được sao chép khoảng `O(n)` |
| `countRuns` phát thống kê | Số đoạn có khóa liên tiếp | `O(1)` | `O(số đoạn)` |
| `fixed(k)` tự viết | `ceil(n/k)` nếu `n > 0`; 0 nếu rỗng | `O(k)` | Tổng số phần tử được chép `O(n)` |
| `fullSliding(k)` tự viết | `max(0, n-k+1)` | `O(k)` | Có thể `O(k · max(0,n-k+1))` vì chép mỗi cửa sổ |

Một sai lầm phổ biến là thấy trạng thái cửa sổ chỉ giữ `k` phần tử rồi suy ra toàn bộ pipeline dùng bộ nhớ `O(k)`. Nếu terminal là `toList()`, toàn bộ các cửa sổ đã phát vẫn được giữ lại; với cửa sổ trượt, lượng phần tử xuất hiện trong output có thể xấp xỉ `k(n-k+1)`.

Ví dụ `100_000` phép đo và cửa sổ `100` sẽ tạo gần `100_000` cửa sổ, mỗi cửa sổ chứa `100` phần tử. Nếu chỉ cần **trung bình trượt**, việc phát cả `List<T>` rồi giữ tất cả trong `toList()` có thể rất tốn bộ nhớ; thay vào đó hãy `map` từng cửa sổ thành thống kê ngay, hoặc viết Gatherer duy trì tổng trượt `O(1)` cập nhật mỗi bước.

Nếu cửa sổ không cần lưu lại tất cả, dùng terminal xử lý tuần tự hoặc ghi ra đích với quản lý I/O rõ ràng để tránh giữ toàn bộ kết quả.

## 13. Mini project: phát hiện biến động theo từng phiên cảm biến

### Yêu cầu

Một dòng sự kiện cảm biến có mã cảm biến và giá trị đo. Dữ liệu đã sắp theo thời gian, nhưng những dòng của một cảm biến có thể xuất hiện thành **nhiều phiên không kề nhau**.

```text
A:10, A:14, A:19, B:20, B:22, B:24, A:5
```

Mục tiêu:

1. Gom các sự kiện **kề nhau có cùng mã cảm biến** thành phiên.
2. Trong mỗi phiên, tạo cửa sổ trượt **đủ ba phần tử**.
3. Phát tổng ba phép đo cho mỗi cửa sổ.
4. Không cho cửa sổ vượt qua ranh giới phiên.
5. Nếu phiên ngắn hơn ba phép đo, không phát kết quả.

Bài này kết hợp hai Gatherer tùy chỉnh mà không cần một Map giữ mọi dữ liệu theo khóa toàn cục.

### Mô hình dữ liệu

```java
record Reading(String sensorId, long tick, int value) {}

record WindowSum(String sensorId, int sum) {}
```

`record` là cú pháp có sẵn trên Java 24. Ví dụ giả định đầu vào đã được sắp theo `tick` tăng dần; nếu chưa, cần xác định và xử lý thứ tự trước khi gom phiên.

### Pipeline thực hành

```java
import java.util.List;

List<Reading> readings = List.of(
        new Reading("A", 1, 10),
        new Reading("A", 2, 14),
        new Reading("A", 3, 19),
        new Reading("B", 4, 20),
        new Reading("B", 5, 22),
        new Reading("B", 6, 24),
        new Reading("A", 7, 5)
);

List<WindowSum> result = readings.stream()
        .gather(RunGatherers.consecutiveBy(Reading::sensorId))
        .flatMap(run -> run.stream()
                .gather(WindowGatherers.fullSliding(3))
                .map(window -> new WindowSum(
                        window.get(0).sensorId(),
                        window.stream()
                                .mapToInt(Reading::value)
                                .sum()
                )))
        .toList();

System.out.println(result);
// [WindowSum[sensorId=A, sum=43],
//  WindowSum[sensorId=B, sum=66]]
```

Vì:

- Phiên A đầu có `10 + 14 + 19 = 43`.
- Phiên B có `20 + 22 + 24 = 66`.
- Phiên A cuối chỉ có `5` nên không đủ cửa sổ ba phần tử.

Nếu thay `consecutiveBy` bằng `groupingBy(Reading::sensorId)`, hai phiên A sẽ bị nhập làm một nhóm. Điều đó có thể tạo một cửa sổ đi qua ranh giới thời gian/phiên và làm kết quả nghiệp vụ sai.

### Nâng cấp đề bài

Để biến ví dụ thành một mini project thực tế, hãy mở rộng từng bước:

1. Bản ghi có thêm `sessionId` hoặc quy tắc bắt đầu phiên mới khi khoảng cách `tick` vượt ngưỡng. Khi đó classifier theo mã cảm biến **chưa đủ**; trạng thái Gatherer phải xét thêm điều kiện ngắt phiên.
2. Thay phép tính tổng bằng `double average`, đồng thời nêu sai số floating point và chính sách làm tròn.
3. Phát cảnh báo chỉ khi trung bình ba phép đo vượt ngưỡng và không cảnh báo lặp liên tục trong cùng một phiên.
4. Nếu dữ liệu đến theo mạng hoặc tệp, xác định ai sở hữu/đóng nguồn; Gatherer không tự quản lý I/O.
5. Khi dữ liệu rất lớn, tránh giữ toàn bộ phiên trong `List`; viết Gatherer trực tiếp theo từng phiên và dùng cửa sổ ring-buffer.

Những bước nâng cấp này là bài tập mở rộng; mã nền tảng ở trên giải quyết chính xác yêu cầu gom phiên theo khóa kề nhau và cửa sổ đủ ba phép đo.

## 14. Bài kiểm tra hành vi quan trọng

Kiểm thử Gatherer không chỉ so khớp kết quả của một dãy “đẹp”. Hãy kiểm tra các tình huống biên theo hợp đồng.

### Kiểm thử nhóm liên tiếp

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

static void checkEquals(Object expected, Object actual) {
    if (!Objects.equals(expected, actual)) {
        throw new AssertionError(
                "Expected " + expected + ", got " + actual
        );
    }
}

checkEquals(
        List.of(),
        Stream.<String>empty()
                .gather(RunGatherers.consecutiveBy(s -> s))
                .toList()
);

checkEquals(
        List.of(List.of("A", "A", "A")),
        Stream.of("A", "A", "A")
                .gather(RunGatherers.consecutiveBy(s -> s))
                .toList()
);

checkEquals(
        List.of(List.of("A"), List.of("B"), List.of("A")),
        Stream.of("A", "B", "A")
                .gather(RunGatherers.consecutiveBy(s -> s))
                .toList()
);
```

Với `null`, `List.of(null)` **không hợp lệ** vì `List.of` không nhận null. Nếu cần kiểm thử khóa null, hãy dùng `Arrays.asList(...)` để tạo nguồn/dữ liệu mong đợi:

```java
import java.util.Arrays;

List<List<String>> nullableRuns =
        Arrays.<String>asList(null, null, "A", null)
              .stream()
              .gather(RunGatherers.consecutiveBy(s -> s))
              .toList();

checkEquals(
        Arrays.asList(
                Arrays.asList(null, null),
                Arrays.asList("A"),
                Arrays.asList((String) null)
        ),
        nullableRuns
);
```

Mục đích là xác minh `active` và `Objects.equals` xử lý đúng trường hợp khóa null, không bị hiểu nhầm null là trạng thái “chưa có nhóm”.

### Kiểm thử fixed và fullSliding

```java
import java.util.List;
import java.util.stream.Stream;

checkEquals(
        List.of(),
        Stream.<Integer>empty()
                .gather(FixedWindowGatherers.fixed(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2)),
        Stream.of(1, 2)
                .gather(FixedWindowGatherers.fixed(3))
                .toList()
);

checkEquals(
        List.of(),
        Stream.of(1, 2)
                .gather(WindowGatherers.fullSliding(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3)),
        Stream.of(1, 2, 3)
                .gather(WindowGatherers.fullSliding(3))
                .toList()
);

checkEquals(
        List.of(List.of(1, 2, 3), List.of(2, 3, 4)),
        Stream.of(1, 2, 3, 4)
                .gather(WindowGatherers.fullSliding(3))
                .toList()
);
```

Vì yêu cầu của hai Gatherer khác nhau, kết quả với nguồn ngắn hơn ba phần tử **cố ý khác nhau**. Bài kiểm thử phải khẳng định sự khác biệt này, thay vì cố ép hai API có cùng chính sách.

### Kiểm thử dừng sớm và snapshot

```java
List<List<Integer>> onlyFirst =
        Stream.of(1, 2, 3, 4, 5)
              .gather(FixedWindowGatherers.fixed(2))
              .limit(1)
              .toList();

checkEquals(List.of(List.of(1, 2)), onlyFirst);

List<List<String>> separateSnapshots =
        Stream.of("X", "X", "Y", "Y")
              .gather(RunGatherers.consecutiveBy(s -> s))
              .toList();

checkEquals(
        List.of(List.of("X", "X"), List.of("Y", "Y")),
        separateSnapshots
);
```

Cần kiểm tra rằng nhóm đầu không biến thành rỗng khi nhóm thứ hai được xây dựng. Đó là cách phát hiện lỗi phát lại cùng một `ArrayList` mutable.

## 15. Các lỗi dễ mắc khi tự viết Gatherer

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Quên `finisher` trong thuật toán nhóm liên tiếp | Mất nhóm cuối | Phát trạng thái còn lại khi upstream kết thúc |
| Phát thẳng buffer rồi `clear()` | Những nhóm/cửa sổ đã phát bị sửa theo | Phát snapshot `new ArrayList<>(buffer)` |
| Không kiểm tra `downstream.push(...)` | Tiếp tục phát sau khi downstream không cần | Trả `false`, ghi nhận hủy khi cần |
| Dùng `currentKey == key` cho String/object | So sánh tham chiếu thay vì giá trị | `Objects.equals` hoặc comparator đúng nghiệp vụ |
| Dùng `key.equals(...)` với khóa nullable | `NullPointerException` | `Objects.equals` và trạng thái `active` |
| Dùng `groupingBy` thay cho nhóm kề nhau | Gộp cả các đoạn không liên tiếp cùng khóa | Gatherer có trạng thái ranh giới |
| Cửa sổ trượt không loại phần tử cũ | Buffer cứ lớn lên, kết quả sai kích thước | Xóa đầu buffer khi vượt `k` |
| Dùng `ArrayDeque` nhưng yêu cầu phần tử null | `NullPointerException` | Chọn buffer phù hợp hoặc chuẩn hóa dữ liệu |
| Không kiểm tra `k > 0` | Quy tắc phát cửa sổ vô nghĩa | `IllegalArgumentException` |
| Nghĩ `windowFixed` và `windowSliding` đều không chồng lặp | Nhầm ý nghĩa dữ liệu | Xác định số bước trượt và điểm phát |
| Cửa sổ đi qua ranh giới phiên | Kết quả thống kê sai ngữ nghĩa | Gom phiên trước, tạo cửa sổ trong từng phiên |
| Tự tạo combiner nối hai nhóm cuối/đầu mà không kiểm tra khóa | Mất/gộp sai nhóm ở ranh giới phân hoạch | Dùng `ofSequential` hoặc thiết kế thuật toán ghép ranh giới đầy đủ |
| Bật `parallel()` và suy ra kết quả nhanh hơn | Overhead có thể lớn, thứ tự phức tạp | Đo trên dữ liệu thật; không đánh đổi tính đúng |
| Đọc dữ liệu từ `Files.lines` mà không đóng nguồn | Rò rỉ tài nguyên | `try-with-resources` |
| Dùng `toList()` cho hàng triệu cửa sổ dài | Bộ nhớ tăng lớn do lưu tất cả output | Phát thống kê nhỏ hoặc xử lý luồng |

## 16. Thứ tự, nguồn I/O và parallel stream

Bài toán nhóm liên tiếp cần một **encounter order có ý nghĩa**. Với nguồn List sự kiện đã sắp theo thời gian, thứ tự gặp là vị trí trong List. Với nguồn không ordered hoặc dữ liệu phân phối từ nhiều nơi, không nên tự khẳng định rằng các phần tử liền nhau trong Stream cũng liền nhau theo nghiệp vụ.

Nếu dùng `sorted(Comparator.comparing(...))` để đưa về thứ tự thời gian, hãy nhớ `sorted` là thao tác stateful và có thể cần bộ đệm lớn trước khi phát dữ liệu. Đối với dữ liệu không đủ để phân biệt thời gian, phải xác định tie-breaker, chẳng hạn sequence number.

Không nên tạo một Gatherer có combiner “chỉ nối các List kết quả” mà không xử lý **ranh giới giữa nhánh trái và nhánh phải**: ví dụ nhánh trái kết thúc bằng `A`, nhánh phải bắt đầu bằng `A` thì nhóm cuối của nhánh trái và nhóm đầu của nhánh phải có thể phải hợp nhất. Với sliding window kích thước `k`, khi chia nhánh còn phải duy trì tối đa `k - 1` phần tử đầu/cuối để tạo cửa sổ bắc qua ranh giới.

Chính vì các điều kiện đó, `ofSequential` là điểm khởi đầu phù hợp cho bài thực hành. Nếu sau này muốn viết Gatherer hỗ trợ parallel, cần đặc tả phép kết hợp có tính kết hợp và bảo toàn thứ tự/ngữ nghĩa trong mọi cách phân hoạch.

### Sở hữu tài nguyên không thay đổi vì Gatherer

Ví dụ xử lý các đợt có cùng mã lỗi từ tệp:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<List<String>> consecutiveErrorLines(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> line.startsWith("ERROR:"))
                .gather(RunGatherers.consecutiveBy(
                        line -> line.substring(
                                0, Math.min(line.length(), 10))
                ))
                .toList();
    }
}
```

Ví dụ trên minh họa **vòng đời tài nguyên**, không phải bộ phân tích log hoàn chỉnh: việc lấy mười ký tự đầu làm khóa chỉ là quy tắc ví dụ và không chắc đúng cho định dạng log thực. Hơn nữa, `filter` có thể làm hai dòng ERROR cách nhau bởi INFO trở thành kề nhau trong pipeline; nếu yêu cầu các nhóm **liên tiếp trong tệp gốc**, phải đưa logic ngắt nhóm vào Gatherer hoặc đặt một bước biến đổi giữ dấu ranh giới thay vì lọc bỏ các dòng ở giữa.

`collect`, `toList`, `limit` và `gather` đều **không tự đóng Stream** do `Files.lines` trả về. `try-with-resources` đóng nguồn ngay cả khi terminal operation kết thúc sớm hoặc xảy ra lỗi. Nếu I/O lỗi khi duyệt lazy, ngoại lệ có thể xuất hiện dưới dạng `UncheckedIOException`.

## 17. Từ bài tập đến triển khai thực tế

Trước khi đưa Gatherer tự viết vào ứng dụng, hãy trả lời:

1. **JDK có hỗ trợ API chưa?** Dùng Java 24+; không mặc định mã chạy trên Java 8–21.
2. **Đầu ra thật sự cần là gì?** `List<T>`, DTO thống kê, hay một cảnh báo? Đừng giữ dữ liệu không cần thiết.
3. **Ranh giới nhóm dựa trên gì?** Khóa đổi, khoảng thời gian, session ID, hay predicate đặc biệt?
4. **Thứ tự đầu vào có được bảo đảm không?** Nếu không, “liên tiếp” và “cửa sổ” có thể không có ý nghĩa ổn định.
5. **Cửa sổ ngắn hơn `k` được xử lý ra sao?** Phát một phần, bỏ qua hay báo lỗi?
6. **Đầu vào có thể null không?** Xác định trách nhiệm classifier, bộ đệm và kiểu kết quả.
7. **Có ngưỡng kích thước bộ đệm không?** Một nhóm rất dài có thể gây áp lực RAM.
8. **Có thể dừng sớm không?** Khi `push` trả `false`, integrator/finisher phải phối hợp để không phát thừa.
9. **Có thật sự cần parallel không?** Hãy chứng minh phép gộp trạng thái ở ranh giới trước.
10. **Nguồn có giữ I/O không?** Phân biệt quyền sở hữu, đóng nguồn bằng `try-with-resources`.
11. **Đã kiểm tra nguồn rỗng, một phần tử, khóa đổi nhiều lần, cửa sổ chồng lặp và cancellation chưa?**
12. **Có thể dùng Gatherer chuẩn thay vì tự viết không?** Nếu chỉ cần window cố định/trượt thông thường, `Gatherers.windowFixed`/`windowSliding` có thể đủ.

### Gợi ý tiêu chí chấm bài dự án

| Tiêu chí | Điều kiện đạt |
| --- | --- |
| Đúng nhóm liên tiếp | `A,A,B,A` tạo ba nhóm, không gộp hai đoạn A |
| Đúng cửa sổ cố định | Nguồn 8 phần tử, `k=3` tạo lô có kích thước 3, 3, 2 |
| Đúng cửa sổ trượt đầy đủ | Nguồn 5 phần tử, `k=3` tạo 3 cửa sổ kích thước 3 |
| Bảo toàn snapshot | Kết quả đã phát không thay đổi khi buffer được dùng lại |
| Kết thúc nguồn | Nhóm cuối và lô cuối được xử lý đúng chính sách |
| Dừng sớm | `limit(1)` không làm xuất hiện output ngoài yêu cầu |
| Biên đầu vào | Nguồn rỗng, `k <= 0`, null được xử lý rõ |
| Quản lý tài nguyên | Stream nguồn I/O được đóng đúng nơi sở hữu |
| Hiệu năng | Đánh giá bộ nhớ và sao chép phần tử thay vì chỉ đo tốc độ |
| Tính phù hợp API | Không dùng Gatherer phức tạp khi API chuẩn đã giải quyết yêu cầu |

## 18. Câu hỏi tự kiểm tra

1. `gather` là intermediate hay terminal operation? **Intermediate**; có thể tiếp tục `map`, `filter`, `flatMap` rồi mới terminal.
2. Khác biệt chính giữa `groupingBy` và nhóm liên tiếp? **groupingBy gom toàn cục theo khóa; nhóm liên tiếp giữ các đoạn kề nhau theo encounter order**.
3. Vì sao nhóm cuối cần finisher? **Không còn phần tử đổi khóa để kích hoạt phát nhóm cuối**.
4. Vì sao phải sao chép buffer trước khi push? **Để tránh downstream nhìn thấy cùng List bị clear/sửa sau đó**.
5. `Downstream.push` trả `false` thì integrator nên làm gì? **Ngừng nhận thêm phần tử và không phát tồn dư ngoài yêu cầu**.
6. `ofSequential` phù hợp khi nào? **Khi trạng thái phụ thuộc thứ tự và không có phép combiner ranh giới được chứng minh đúng**.
7. `Gatherers.windowFixed(3)` trên 8 phần tử phát mấy cửa sổ? **Ba**, với kích thước 3, 3, 2.
8. `Gatherers.windowSliding(3)` trên năm phần tử liên tiếp phát mấy cửa sổ đầy đủ? **Ba**, bắt đầu tại vị trí 1, 2, 3.
9. Bản `fullSliding(3)` tự viết phát gì khi nguồn chỉ có hai phần tử? **Không phát gì**, theo hợp đồng chỉ cửa sổ đầy đủ.
10. Vì sao `ArrayDeque` trong ví dụ không nhận null? **Đây là quy tắc của ArrayDeque**, nên code kiểm tra đầu vào.
11. Với `n` phần tử và cửa sổ đầy đủ `k`, số cửa sổ trượt là gì? **`max(0, n-k+1)`**.
12. Tại sao bộ nhớ của `consecutiveBy` không nhất thiết là `O(1)`? **Vì nó giữ nguyên nhóm chưa kết thúc; độ dài nhóm có thể tăng tới n**.
13. Nối kết quả hai nhánh parallel có luôn đúng cho nhóm liên tiếp không? **Không**, phải xét nhóm bắc qua ranh giới phân hoạch.
14. Nếu chỉ cần số lượng trong từng đợt, cải tiến quan trọng nhất là gì? **Chỉ giữ khóa và bộ đếm, phát DTO thống kê thay vì List**.
15. Khi xử lý `Files.lines` qua Gatherer, terminal operation có tự đóng nguồn không? **Không**, vẫn phải dùng `try-with-resources`.

**Nguyên tắc áp dụng:** Viết Gatherer cho nhóm liên tiếp và cửa sổ dữ liệu bắt đầu bằng **định nghĩa ranh giới, thời điểm phát kết quả và chính sách xử lý phần chưa hoàn tất**. Dùng `ofSequential` khi các kết quả phụ thuộc phần tử kề nhau, giữ trạng thái nhỏ nhất cần thiết, phát snapshot độc lập và tôn trọng tín hiệu dừng của downstream. Ưu tiên `Gatherers.windowFixed`/`windowSliding` nếu hợp đồng chuẩn đã đủ; chỉ tự xây Gatherer khi nghiệp vụ cần quy tắc khác. Cuối cùng, kiểm tra tính đúng đắn, nguồn I/O và chi phí bộ nhớ trước khi cân nhắc tối ưu song song.
