# Tạo cửa sổ trượt bằng `Gatherers.windowSliding`

## 1. Mục tiêu và bối cảnh

Trong module **`JAVA_STREAM_API`**, người học đã quen các pipeline xử lý dữ liệu khai báo với `filter`, `map`, `flatMap`, `reduce` và `collect`. Tuy nhiên, nhiều bài toán cần xử lý **mối liên hệ giữa các phần tử liên tiếp**: trung bình ba giá trị gần nhất, so sánh sự thay đổi giữa hai mẫu đo, nhận diện ba từ liền nhau hay phát hiện tín hiệu bất thường trong chuỗi thời gian.

Các phép `map` thông thường chỉ nhận một phần tử tại một thời điểm. Có thể viết vòng lặp thủ công hoặc một collector có trạng thái, nhưng **Stream Gatherers** cung cấp cách diễn đạt trực tiếp hơn cho các thao tác trung gian có trạng thái. Một gatherer dựng sẵn là **`Gatherers.windowSliding(windowSize)`**, dùng để tạo các **cửa sổ trượt có chồng lấn**.

Trong chương **Stream Gatherer**, bài học này tập trung vào cách đọc, viết và kiểm thử pipeline cửa sổ trượt, đồng thời phân biệt yêu cầu nghiệp vụ với khả năng song song hóa, chi phí bộ nhớ và vòng đời tài nguyên.

Kết thúc bài, bạn có thể:

1. Giải thích ý nghĩa cửa sổ trượt và sự khác nhau với chia lô cố định.
2. Sử dụng `Stream.gather(Gatherers.windowSliding(k))` trong **Java 24+**.
3. Dự đoán chính xác kết quả cho nguồn rỗng, nguồn ngắn hơn cửa sổ, `k = 1` và `k > 1`.
4. Tính trung bình trượt, độ biến thiên, n-gram và phát hiện mẫu bằng `map`, `filter`, `anyMatch`.
5. Nhận diện cửa sổ là list **không cho phép sửa**, nhưng không tự biến phần tử mutable thành bất biến.
6. Kiểm tra kích thước, thứ tự, độ chồng lấn và tính đúng trên dữ liệu biên.
7. Hiểu giới hạn về kích thước cửa sổ, phần tử nguồn, stream vô hạn, xử lý song song và nguồn I/O.

## 2. Điều kiện phiên bản JDK

Stream Gatherers đã trải qua các giai đoạn:

| Phiên bản | Trạng thái | Lưu ý |
| --- | --- | --- |
| Java 8–21 | Chưa có API Stream Gatherers chuẩn | Dùng vòng lặp, cấu trúc dữ liệu có trạng thái hoặc thuật toán khác. |
| Java 22 | Preview lần đầu (JEP 461) | Cần bật preview khi biên dịch/chạy; không coi API là ổn định. |
| Java 23 | Preview lần hai (JEP 473) | Vẫn cần bật preview; có thể thay đổi chi tiết so với preview trước. |
| **Java 24 trở lên** | **Chính thức (JEP 485)** | Có `Stream.gather` và `java.util.stream.Gatherers` mà không cần `--enable-preview`. |

Mọi đoạn mã có `Gatherers.windowSliding` trong bài, trừ khi ghi rõ khác, sử dụng **Java 24+**.

Đặt tên file `SlidingWindowDemo.java` rồi dùng JDK 24:

```text
javac SlidingWindowDemo.java
java SlidingWindowDemo
```

Nếu môi trường có nhiều JDK, kiểm tra `java -version` và `javac -version` để chắc chắn compiler/runtime đều hỗ trợ API. Một dự án đặt `--release 17` hoặc `--release 21` **không được** gọi API Java 24, ngay cả khi chạy compiler từ JDK mới.

**Không nhầm Java 16 với Java 24:** `Stream.toList()` và `mapMulti` có từ Java 16, nhưng `Stream.gather` cùng các gatherer dựng sẵn được chuẩn hóa ở Java 24.

## 3. Khái niệm cửa sổ trượt

Giả sử có dữ liệu theo encounter order:

```text
[10, 20, 30, 40, 50]
```

Với kích thước cửa sổ `k = 3`:

```text
Nguồn:         10   20   30   40   50
Cửa sổ 1:     [10   20   30]
Cửa sổ 2:          [20   30   40]
Cửa sổ 3:               [30   40   50]
```

Kết quả:

```text
[
  [10, 20, 30],
  [20, 30, 40],
  [30, 40, 50]
]
```

Mỗi cửa sổ sau:

- Bỏ **phần tử xuất hiện sớm nhất** của cửa sổ trước.
- Giữ `k - 1` phần tử còn lại.
- Thêm **phần tử kế tiếp** từ nguồn.

Vì vậy, **bước trượt của gatherer dựng sẵn là 1 phần tử**. Đừng nhầm `windowSize = 3` với việc nhảy ba phần tử mỗi lần.

### 3.1. Độ chồng lấn

Hai cửa sổ kề nhau có kích thước đủ `k` sẽ **chung `k - 1` phần tử**:

```text
[10, 20, 30]
     [20, 30, 40]
       └─────┘
       Chung: 20, 30
```

Trong ví dụ, một giá trị như `30` xuất hiện trong ba cửa sổ. Điều này **đúng với bài toán cửa sổ trượt**, không phải lỗi lặp dữ liệu của Stream.

### 3.2. Kích thước và số cửa sổ

Gọi:

- `n` là số phần tử nguồn hữu hạn.
- `k` là `windowSize`, bắt buộc `k >= 1`.

Số cửa sổ được tạo:

\[
W(n,k)=
\begin{cases}
0, & n=0\\
1, & 0<n<k\\
n-k+1, & n\ge k
\end{cases}
\]

Các tình huống:

| Nguồn | `k` | Kết quả cửa sổ | Số cửa sổ |
| --- | ---: | --- | ---: |
| `[]` | 3 | `[]` | 0 |
| `[1]` | 3 | `[[1]]` | 1 |
| `[1,2]` | 3 | `[[1,2]]` | 1 |
| `[1,2,3]` | 3 | `[[1,2,3]]` | 1 |
| `[1,2,3,4]` | 3 | `[[1,2,3],[2,3,4]]` | 2 |
| `[1,2,3]` | 1 | `[[1],[2],[3]]` | 3 |

**Điểm đặc biệt:** nếu `0 < n < k`, API phát **đúng một cửa sổ ngắn** gồm toàn bộ phần tử đã có, thay vì phát 0 cửa sổ. Nếu `n >= k`, nó chỉ phát các cửa sổ đầy đủ kích thước `k`, **không phát thêm các cửa sổ ngắn ở cuối**.

Đây là khác biệt quan trọng khi tính thống kê: một cửa sổ ngắn có thể không đạt yêu cầu tối thiểu về số mẫu. Khi nghiệp vụ chỉ chấp nhận cửa sổ đủ độ dài, hãy lọc theo `window.size() == k`.

## 4. Ví dụ đầu tiên: `gather` rồi `toList`

Lời gọi trung tâm:

```java
Stream<T> source = ...;

Stream<List<T>> windows =
    source.gather(Gatherers.windowSliding(k));
```

`Gatherers.windowSliding(k)` là một `Gatherer<T, ?, List<T>>`. Khi áp dụng bằng `gather`, mỗi phần tử của **stream đầu ra** là một **`List<T>` chứa một cửa sổ**.

Ví dụ Java 24+ đầy đủ:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class SlidingWindowDemo {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(
                10, 20, 30, 40, 50)
            .gather(Gatherers.windowSliding(3))
            .toList();

        windows.forEach(System.out::println);
    }
}
```

Kết quả:

```text
[10, 20, 30]
[20, 30, 40]
[30, 40, 50]
```

Phân tích pipeline:

1. `Stream.of(...)` cung cấp nguồn có thứ tự gặp.
2. `Gatherers.windowSliding(3)` tạo gatherer có kích thước ba.
3. `gather(...)` phát các cửa sổ theo thứ tự gặp.
4. `toList()` tiêu thụ các cửa sổ, tạo `List<List<Integer>>`.

Cả `gather` và các biến đổi trung gian tiếp theo đều có thể kết hợp với `filter`, `map`, `limit` và các terminal operation. `toList` không phải phần bắt buộc của `windowSliding`; đây chỉ là cách quan sát rõ các cửa sổ.

### 4.1. Đặt `map` sau `gather`

`gather` làm thay đổi kiểu từ `Stream<Integer>` sang `Stream<List<Integer>>`. Vì vậy, `map` phía sau nhận **một danh sách của cửa sổ**, không còn nhận từng số nguồn:

```java
List<Integer> sums = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream()
        .mapToInt(Integer::intValue)
        .sum())
    .toList();

System.out.println(sums); // [6, 9, 12]
```

Các tổng lần lượt tương ứng `[1,2,3]`, `[2,3,4]` và `[3,4,5]`.

### 4.2. Đặt `map` trước `gather`

```java
List<List<Integer>> squares = Stream.of(1, 2, 3, 4)
    .map(n -> n * n)
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(squares);
// [[1, 4], [4, 9], [9, 16]]
```

Đây là **cửa sổ trên giá trị đã biến đổi**. Nếu biến đổi dữ liệu từng phần tử là bước độc lập, đặt trước gatherer có thể phù hợp hơn việc lặp lại phép biến đổi với cùng phần tử ở nhiều cửa sổ.

## 5. Điều kiện đầu vào: `windowSize`

API yêu cầu `windowSize >= 1`.

```java
import java.util.stream.Gatherers;

var gatherer = Gatherers.windowSliding(3); // Hợp lệ.

// Gatherers.windowSliding(0);  // IllegalArgumentException.
// Gatherers.windowSliding(-2); // IllegalArgumentException.
```

`windowSize = 1` là hợp lệ: mỗi phần tử trở thành một cửa sổ một phần tử.

```java
List<List<String>> windows = Stream.of("A", "B", "C")
    .gather(Gatherers.windowSliding(1))
    .toList();

System.out.println(windows); // [[A], [B], [C]]
```

Nếu nhận kích thước cửa sổ từ người dùng, một API ứng dụng nên kiểm tra thêm **giới hạn trên hợp lý**, không chỉ điều kiện dương:

```java
static int validateWindowSize(int size) {
    if (size < 1 || size > 10_000) {
        throw new IllegalArgumentException(
            "windowSize phai nam trong [1, 10000]");
    }
    return size;
}
```

Giới hạn 10.000 là **ví dụ chính sách của ứng dụng**, không phải giới hạn bắt buộc của JDK. Số hợp lý phụ thuộc bản ghi, bộ nhớ, tài nguyên và thời gian xử lý.

### 5.1. Nguồn rỗng và nguồn thiếu mẫu

```java
System.out.println(
    Stream.<Integer>empty()
        .gather(Gatherers.windowSliding(3))
        .toList()
); // []

System.out.println(
    Stream.of(5, 10)
        .gather(Gatherers.windowSliding(3))
        .toList()
); // [[5, 10]]
```

Nếu ứng dụng xử lý trung bình động chỉ khi có ít nhất ba mẫu, không nên lấy trung bình `[5,10]` rồi trình bày như trung bình ba mẫu. Có hai cách:

- Trả cửa sổ ngắn kèm thông tin số mẫu thực tế.
- Lọc bỏ cửa sổ chưa đủ `k`.

```java
int k = 3;

List<List<Integer>> full = Stream.of(5, 10)
    .gather(Gatherers.windowSliding(k))
    .filter(window -> window.size() == k)
    .toList();

System.out.println(full); // []
```

Trên nguồn có `n >= k`, những cửa sổ phát ra đều đủ kích thước; phép lọc này chủ yếu diễn đạt **yêu cầu nghiệp vụ** khi nguồn quá ngắn.

## 6. Cửa sổ là `List` không cho phép sửa

Theo hợp đồng của `Gatherers.windowSliding`, **mỗi cửa sổ là một list unmodifiable**. Không được thay đổi nội dung bằng `add`, `remove` hoặc `set`:

```java
List<Integer> window = Stream.of(1, 2, 3)
    .gather(Gatherers.windowSliding(2))
    .findFirst()
    .orElseThrow();

System.out.println(window); // [1, 2]

try {
    window.add(99);
} catch (UnsupportedOperationException expected) {
    System.out.println("Window khong cho phep sua");
}
```

Không cam kết loại implementation hoặc serializability cụ thể của những list này. Đừng ép kiểu `ArrayList` hay phụ thuộc tên class được in bởi JVM.

### 6.1. Nếu thật sự muốn bản sao có thể sửa

```java
import java.util.ArrayList;

List<List<Integer>> mutableWindows = Stream.of(1, 2, 3, 4)
    .gather(Gatherers.windowSliding(2))
    .map(ArrayList::new)
    .toList();

mutableWindows.get(0).add(99);
System.out.println(mutableWindows.get(0)); // [1, 2, 99]
```

Chú ý: **`toList()` bên ngoài cũng trả một list unmodifiable**. Ở ví dụ, bạn có thể sửa **các `ArrayList` bên trong**, nhưng không thể `mutableWindows.add(...)`. Nếu cần sửa cả list ngoài, thu bằng `collect(Collectors.toCollection(ArrayList::new))`.

### 6.2. Unmodifiable không đồng nghĩa deep immutable

Nếu cửa sổ chứa những object có thuộc tính mutable, việc thay đổi **object được tham chiếu** vẫn có thể được thấy từ cửa sổ:

```java
class Box {
    int value;
    Box(int value) { this.value = value; }
}

Box a = new Box(1);
Box b = new Box(2);

List<Box> window = Stream.of(a, b)
    .gather(Gatherers.windowSliding(2))
    .findFirst()
    .orElseThrow();

a.value = 42;
System.out.println(window.get(0).value); // 42
```

Cửa sổ unmodifiable là **bất biến về cấu trúc list**, không tự sao chép sâu phần tử. Với dữ liệu kế toán, đo lường hoặc audit, hãy cân nhắc phần tử kiểu immutable hoặc snapshot sâu theo chính sách hệ thống.

## 7. So sánh `windowSliding` với `windowFixed`

Java 24 có hai gatherer cửa sổ dựng sẵn:

| Tiêu chí | `windowSliding(k)` | `windowFixed(k)` |
| --- | --- | --- |
| Cách chia | Cửa sổ chồng lấn, bước trượt 1 | Chia các nhóm liên tiếp, không chồng lấn |
| Kích thước cửa sổ | `k` nếu đủ dữ liệu | `k`, cửa sổ cuối có thể ngắn |
| Nguồn ngắn hơn `k`, không rỗng | **Một cửa sổ ngắn** | **Một cửa sổ ngắn** |
| Nguồn rỗng | Không có cửa sổ | Không có cửa sổ |
| Ví dụ `[1..7], k=3` | `[1,2,3]`, `[2,3,4]`, `[3,4,5]`, `[4,5,6]`, `[5,6,7]` | `[1,2,3]`, `[4,5,6]`, `[7]` |
| Ý nghĩa | Quan sát sự biến thiên qua các điểm liền nhau | Xử lý dữ liệu theo batch độc lập |

Chương trình đối chiếu:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class CompareWindows {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 7)
            .boxed()
            .toList();

        System.out.println(source.stream()
            .gather(Gatherers.windowSliding(3))
            .toList());
        // [[1, 2, 3], [2, 3, 4], [3, 4, 5],
        //  [4, 5, 6], [5, 6, 7]]

        System.out.println(source.stream()
            .gather(Gatherers.windowFixed(3))
            .toList());
        // [[1, 2, 3], [4, 5, 6], [7]]
    }
}
```

**Sai lầm thường gặp:** dùng `windowFixed` để tính trung bình trượt, khiến các cửa sổ không chồng lấn và bỏ qua nhiều tổ hợp phần tử liền kề.

## 8. Công thức tổng quát cho số cửa sổ và độ phủ

Khi nguồn hữu hạn có `n >= k >= 1`, các cửa sổ đầy đủ bắt đầu lần lượt tại chỉ số:

```text
0, 1, 2, ..., n - k
```

Cửa sổ thứ `i` theo cách đánh số 0-based là đoạn chỉ số:

```text
[i, i + 1, ..., i + k - 1]
```

Số cửa sổ đầy đủ:

```text
n - k + 1
```

Khi `n = 0`, không có cửa sổ; khi `0 < n < k`, có một cửa sổ ngắn. Công thức này rất hữu ích để viết **test trên nhiều giá trị k**, nhất là k = 1, k = n và k > n.

Ví dụ `n = 5` và `k = 3`:

```text
Cửa sổ thứ 0: phần tử 0, 1, 2
Cửa sổ thứ 1: phần tử 1, 2, 3
Cửa sổ thứ 2: phần tử 2, 3, 4
Tổng: 5 - 3 + 1 = 3 cửa sổ.
```

Nếu một pipeline phía sau chỉ lấy hai cửa sổ bằng `limit(2)`, kết quả vẫn là **hai cửa sổ đầu theo encounter order**, không phải hai phần tử đầu của nguồn.

## 9. Bài toán thực tế 1: tính trung bình trượt

Cho dãy số đo:

```text
[10, 12, 14, 16, 18, 20]
```

Với `k = 3`:

```text
[10,12,14] -> 12.0
[12,14,16] -> 14.0
[14,16,18] -> 16.0
[16,18,20] -> 18.0
```

Ví dụ Java 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class MovingAverage {
    public static void main(String[] args) {
        int windowSize = 3;

        List<Double> averages = Stream.of(
                10, 12, 14, 16, 18, 20)
            .gather(Gatherers.windowSliding(windowSize))
            .filter(window -> window.size() == windowSize)
            .map(window -> window.stream()
                .mapToDouble(Integer::doubleValue)
                .average()
                .orElseThrow())
            .toList();

        System.out.println(averages);
        // [12.0, 14.0, 16.0, 18.0]
    }
}
```

Ở đây:

1. `gather` tạo các cửa sổ liền nhau.
2. `filter` bảo đảm luôn đủ ba mẫu khi tính.
3. `mapToDouble` tránh tạo thêm `Double` boxed trong phép tổng hợp.
4. `average` là terminal operation **trên stream của từng cửa sổ**, trả `OptionalDouble`.
5. `orElseThrow` hợp lệ vì mọi cửa sổ được giữ có ít nhất ba phần tử.

Phương pháp này đơn giản và dễ đọc, nhưng mỗi cửa sổ lại duyệt `k` phần tử để tính tổng. Với `n` lớn và `k` lớn, tổng công việc có thể xấp xỉ **O(n × k)** thay vì O(n). Khi cần tối ưu chặt chẽ, có thể dùng thuật toán **rolling sum** có trạng thái được kiểm soát; không mặc định sử dụng cửa sổ là cách nhanh nhất.

### 9.1. Cửa sổ ngắn có được tính trung bình không?

```java
List<Double> averages = Stream.of(10, 20)
    .gather(Gatherers.windowSliding(3))
    .map(w -> w.stream()
        .mapToDouble(Integer::doubleValue)
        .average()
        .orElseThrow())
    .toList();

System.out.println(averages); // [15.0]
```

Đây là trung bình **của hai mẫu có sẵn**, không phải trung bình trượt ba mẫu. Nếu hệ thống chỉ công bố kết quả khi đủ ba mẫu, thêm `filter(w -> w.size() == 3)` để trả list rỗng cho nguồn này.

### 9.2. Sai số số thực và miền giá trị

`DoubleStream.average()` trả giá trị số thực; khi dùng dữ liệu tiền tệ, độ chính xác số thực có thể không đáp ứng yêu cầu. Cân nhắc `BigDecimal` và quy tắc làm tròn rõ ràng. Nếu chuyển số nguyên sang `double`, có thể mất độ chính xác đối với số nguyên lớn hơn khoảng biểu diễn chính xác.

Với chuỗi dữ liệu dài, việc tính trung bình độc lập cho từng cửa sổ có thể phù hợp để học và kiểm thử; còn yêu cầu hiệu năng cao cần đo trên workload thực và so sánh với một thuật toán cập nhật tổng theo từng bước.


## 10. Bài toán thực tế 2: chênh lệch giữa hai mẫu liên tiếp

Cửa sổ kích thước 2 là cách tự nhiên để so sánh phần tử hiện tại và phần tử ngay trước nó.

Nguồn:

```text
[100, 105, 103, 110]
```

Các cặp và chênh lệch:

```text
[100,105] -> +5
[105,103] -> -2
[103,110] -> +7
```

Ví dụ:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class ConsecutiveDeltas {
    public static void main(String[] args) {
        List<Integer> delta = Stream.of(100, 105, 103, 110)
            .gather(Gatherers.windowSliding(2))
            .filter(window -> window.size() == 2)
            .map(window -> window.get(1) - window.get(0))
            .toList();

        System.out.println(delta); // [5, -2, 7]
    }
}
```

Phép trừ `window.get(1) - window.get(0)` thể hiện thay đổi từ **phần tử trước tới phần tử sau**. Nếu chỉ có một mẫu, gatherer có thể tạo cửa sổ `[100]`; `filter(window -> window.size() == 2)` ngăn lỗi `IndexOutOfBoundsException`.

### 10.1. Phát hiện tăng đột biến

```java
boolean hasJump = Stream.of(100, 105, 103, 140)
    .gather(Gatherers.windowSliding(2))
    .filter(window -> window.size() == 2)
    .anyMatch(window ->
        window.get(1) - window.get(0) > 20);

System.out.println(hasJump); // true
```

`anyMatch` là terminal operation short-circuiting: nó có thể kết thúc khi phát hiện cặp phù hợp. Khi gắn I/O hoặc tác dụng phụ vào pipeline, không được giả định tất cả phần tử nguồn đã được duyệt hoặc callback đã được gọi đúng số lần.

### 10.2. Nếu muốn trả cả vị trí và độ chênh lệch

`gather` tạo cửa sổ nhưng **không tự gắn chỉ số đầu cửa sổ**. Có thể đánh chỉ số đầu vào trước:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

record Sample(int index, int value) {}

record Change(int fromIndex, int toIndex, int delta) {}

List<Change> changes = IntStream.range(0, 4)
    .mapToObj(i -> new Sample(
        i, new int[] {100, 105, 103, 110}[i]))
    .gather(Gatherers.windowSliding(2))
    .filter(window -> window.size() == 2)
    .map(window -> new Change(
        window.get(0).index(),
        window.get(1).index(),
        window.get(1).value() - window.get(0).value()))
    .toList();

System.out.println(changes);
// [Change[fromIndex=0, toIndex=1, delta=5],
//  Change[fromIndex=1, toIndex=2, delta=-2],
//  Change[fromIndex=2, toIndex=3, delta=7]]
```

Đây là đoạn mã minh họa đặt trong một lớp hoặc file nguồn phù hợp của **Java 24+**; `record` có từ Java 16. Để dễ tái sử dụng và tránh cấp phát mảng nhiều lần, chương trình thực tế nên khai báo nguồn một lần rồi lấy phần tử theo chỉ số.

Phiên bản đơn giản hơn nếu chỉ cần biết đoạn nào biến thiên là lưu các cửa sổ hoặc giá trị chênh lệch, không nhất thiết tạo record mới cho từng cặp.

## 11. Bài toán thực tế 3: tạo n-gram trong xử lý văn bản

Một **n-gram** là chuỗi gồm `n` token liền nhau. Với các từ:

```text
["hoc", "java", "stream", "api"]
```

Bigram (`n = 2`) là:

```text
["hoc java", "java stream", "stream api"]
```

Trigram (`n = 3`):

```text
["hoc java stream", "java stream api"]
```

Sử dụng `windowSliding`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class NgramDemo {
    public static void main(String[] args) {
        List<String> tokens = List.of(
            "hoc", "java", "stream", "api"
        );

        List<String> bigrams = tokens.stream()
            .gather(Gatherers.windowSliding(2))
            .map(window -> String.join(" ", window))
            .toList();

        List<String> trigrams = tokens.stream()
            .gather(Gatherers.windowSliding(3))
            .map(window -> String.join(" ", window))
            .toList();

        System.out.println(bigrams);
        System.out.println(trigrams);
    }
}
```

Kết quả:

```text
[hoc java, java stream, stream api]
[hoc java stream, java stream api]
```

### 11.1. Nếu ít token hơn kích thước n-gram

```java
List<String> shortInput = List.of("hoc", "java");

System.out.println(
    shortInput.stream()
        .gather(Gatherers.windowSliding(3))
        .map(window -> String.join(" ", window))
        .toList()
); // [hoc java]
```

Kết quả ở đây chứa **một chuỗi biểu diễn cửa sổ ngắn**, không phải một trigram hợp lệ ba token.

Khi nghiệp vụ chỉ chấp nhận n-gram đầy đủ:

```java
int n = 3;

List<String> valid = shortInput.stream()
    .gather(Gatherers.windowSliding(n))
    .filter(window -> window.size() == n)
    .map(window -> String.join(" ", window))
    .toList();

System.out.println(valid); // []
```

### 11.2. Đếm tần suất n-gram

```java
import java.util.Map;
import java.util.stream.Collectors;

List<String> tokens = List.of(
    "java", "stream", "api", "java", "stream", "api"
);

Map<String, Long> counts = tokens.stream()
    .gather(Gatherers.windowSliding(2))
    .map(window -> String.join(" ", window))
    .collect(Collectors.groupingBy(
        text -> text,
        Collectors.counting()
    ));

System.out.println(counts.get("java stream")); // 2
```

`groupingBy` tổng hợp các n-gram đã được phát. `windowSliding` chỉ tạo các cửa sổ, **không phải collector**.

Thứ tự duyệt các entry của `Map` kết quả không được bảo đảm theo thứ tự token trừ khi bạn chọn loại map phù hợp và tuân thủ hợp đồng collector. Nếu cần báo cáo có thứ tự theo số đếm hoặc theo từ khóa, sắp xếp rõ ràng ở bước tiếp theo.

## 12. Bài toán thực tế 4: phát hiện cửa sổ thỏa điều kiện

Giả sử dữ liệu nhiệt độ (°C) theo thứ tự thời gian đã được chuẩn hóa, và yêu cầu cảnh báo khi **ba mẫu liên tiếp đều lớn hơn 38**.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class TemperatureAlert {
    public static void main(String[] args) {
        List<Double> readings = List.of(
            37.5, 38.2, 39.1, 39.3, 37.8
        );

        boolean alert = readings.stream()
            .gather(Gatherers.windowSliding(3))
            .filter(window -> window.size() == 3)
            .anyMatch(window -> window.stream()
                .allMatch(value -> value > 38.0));

        System.out.println(alert); // true
    }
}
```

Cửa sổ `[38.2,39.1,39.3]` đáp ứng điều kiện. Lọc đủ ba mẫu trước `anyMatch` giúp tránh xem một chuỗi thiếu dữ liệu là ba mẫu liên tiếp.

Khi các mẫu có thời gian thực không đều nhau, cửa sổ ba **phần tử** không có nghĩa ba phút hoặc ba giây. `windowSliding(3)` đếm **số phần tử**, không kiểm tra khoảng cách thời gian.

### 12.1. Phân biệt cửa sổ theo số lượng và cửa sổ theo thời gian

| Loại | Ví dụ yêu cầu | `windowSliding` có đáp ứng trực tiếp? |
| --- | --- | --- |
| Theo số lượng | Ba giá trị gần nhất | Có, dùng `windowSliding(3)`. |
| Theo cặp kề nhau | Chênh lệch mẫu trước/sau | Có, dùng `windowSliding(2)`. |
| Theo thời gian | Mọi mẫu trong 5 phút gần nhất | **Không tự động**; cần xét timestamp và quy tắc biên. |
| Theo bước nhảy | Cửa sổ dài 5, tiến mỗi lần 2 | **Không trực tiếp**; gatherer dựng sẵn trượt từng phần tử. |
| Theo phiên hoạt động | Gom khi khoảng cách giữa sự kiện vượt ngưỡng | Cần state/logic nghiệp vụ riêng. |

Nếu mẫu có timestamp, hãy sắp xếp theo khóa thời gian **và khóa phụ khi trùng thời điểm** trước khi dùng cửa sổ theo số lượng. Tuy nhiên, `sorted` có thể cần giữ dữ liệu đầu vào, gây chi phí lớn hoặc không phù hợp với stream vô hạn tổng quát.

## 13. Thứ tự thao tác quyết định ý nghĩa cửa sổ

Cửa sổ được tạo trên **dòng phần tử tại vị trí gatherer xuất hiện trong pipeline**. Đổi thứ tự các phép toán có thể làm dữ liệu nguồn liền kề trở thành **không còn liền kề** trong kết quả.

### 13.1. Lọc trước khi tạo cửa sổ

```java
List<List<Integer>> result = Stream.of(1, 2, 3, 4, 5)
    .filter(n -> n % 2 == 1)
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(result);
// [[1, 3], [3, 5]]
```

Do `filter` loại số chẵn trước, các phần tử `1` và `3` được xem là kề nhau **trong stream đã lọc**, dù chúng không kề nhau trong nguồn gốc.

### 13.2. Tạo cửa sổ trước khi lọc

```java
List<List<Integer>> result = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(2))
    .filter(window -> window.get(0) % 2 == 1)
    .toList();

System.out.println(result);
// [[1, 2], [3, 4]]
```

Đây là các cặp liền kề của **dữ liệu gốc**, sau đó chỉ giữ những cặp có phần tử đầu lẻ. Hai pipeline **không tương đương**.

Quy tắc chọn:

- Muốn cửa sổ trên **những phần tử đã được chọn**: `filter(...).gather(...)`.
- Muốn giữ khái niệm kề nhau **trong dãy gốc** rồi đánh giá cửa sổ: `gather(...).filter(...)`.

### 13.3. Sắp xếp trước `gather`

```java
List<List<Integer>> byValue = Stream.of(9, 1, 7, 2)
    .sorted()
    .gather(Gatherers.windowSliding(2))
    .toList();

System.out.println(byValue);
// [[1, 2], [2, 7], [7, 9]]
```

Pipeline tạo cửa sổ theo **giá trị tăng dần**, không phải thứ tự xuất hiện ban đầu `9,1,7,2`. Với sự kiện theo thời gian, nếu nguồn đã đúng thứ tự thời gian, sắp xếp thêm theo giá trị đo có thể phá vỡ quan hệ thời gian.

### 13.4. `limit` trước và sau gatherer

```java
List<List<Integer>> firstFourSource = Stream.of(
        1, 2, 3, 4, 5, 6)
    .limit(4)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(firstFourSource);
// [[1, 2, 3], [2, 3, 4]]
```

`limit(4)` giới hạn nguồn còn bốn phần tử, rồi mới tạo các cửa sổ.

```java
List<List<Integer>> firstTwoWindows = Stream.of(
        1, 2, 3, 4, 5, 6)
    .gather(Gatherers.windowSliding(3))
    .limit(2)
    .toList();

System.out.println(firstTwoWindows);
// [[1, 2, 3], [2, 3, 4]]
```

Hai ví dụ tình cờ có kết quả giống nhau với dữ liệu này, nhưng **ý nghĩa khác nhau**. Nếu thay `limit(4)` trước gather bằng `limit(3)`, chỉ còn một cửa sổ đầy đủ. Nếu thay `limit(2)` sau gather bằng `limit(3)`, có ba cửa sổ.

Không suy ra `limit(2)` sau gather luôn khiến nguồn chỉ được đọc bốn phần tử: runtime có thể có buffering hoặc trạng thái trung gian; hợp đồng quan trọng là **số cửa sổ kết quả**.

## 14. Cửa sổ trượt trên stream vô hạn

Một ứng dụng có thể xử lý chuỗi giá trị sinh liên tục. `Stream.iterate` tạo nguồn có thể vô hạn:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(4)
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6]]
```

`limit(4)` **sau gatherer** giúp terminal operation có kết quả hữu hạn. Nếu bỏ cả `limit` lẫn điều kiện dừng nguồn, `toList` cố thu vô hạn cửa sổ, không thể hoàn thành với bộ nhớ hữu hạn.

### 14.1. Cần đủ phần tử trước khi có cửa sổ đầu

Với `windowSize = 3`, gatherer phải có ba phần tử trước khi phát cửa sổ đầy đủ đầu tiên. Trong trường hợp nguồn hữu hạn kết thúc trước đó, nó có thể phát một cửa sổ ngắn khi kết thúc nguồn.

Vì thế:

- Với một nguồn không bao giờ phát đủ `k` phần tử **và không kết thúc**, bạn không thể giả định sẽ sớm nhận một cửa sổ.
- Với một nguồn hữu hạn có ít hơn `k` phần tử, khi traversal kết thúc, có một cửa sổ ngắn.
- `findFirst` trên pipeline gatherer có thể phải đọc đủ dữ liệu để hình thành cửa sổ đầu.

Đây là khác biệt giữa **độ trễ có được cửa sổ đầu** và **chi phí thu toàn bộ kết quả**.

### 14.2. Không tạo cửa sổ trượt vô hạn rồi sắp xếp tất cả

```java
// KHÔNG NÊN với nguồn vô hạn:
// Stream.iterate(1, n -> n + 1)
//     .gather(Gatherers.windowSliding(3))
//     .sorted(comparator)
//     .limit(1)
//     .toList();
```

`sorted` là thao tác stateful có thể cần biết toàn bộ dữ liệu trước khi phát giá trị. Đặt `limit` phía sau không biến bài toán vô hạn thành hữu hạn. Khi phải sắp xếp, xác định rõ giới hạn đầu vào và tài nguyên.

## 15. Khi dữ liệu có nhóm, tránh cửa sổ vượt qua ranh giới nhóm

Giả sử hệ thống có hai thiết bị cảm biến, mỗi thiết bị có chuỗi thời gian riêng:

```text
Thiết bị A: [10, 11, 12]
Thiết bị B: [50, 51, 52]
```

Nếu nối thành `[10,11,12,50,51,52]` rồi tạo `windowSliding(3)`, sẽ có những cửa sổ `[11,12,50]` và `[12,50,51]` **trộn số liệu từ hai thiết bị**.

Một cách đúng là áp dụng gatherer **riêng trong từng nhóm**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Gatherers;

Map<String, List<Integer>> readings = new LinkedHashMap<>();
readings.put("A", List.of(10, 11, 12));
readings.put("B", List.of(50, 51, 52));

readings.forEach((device, values) -> {
    List<List<Integer>> windows = values.stream()
        .gather(Gatherers.windowSliding(3))
        .toList();

    System.out.println(device + ": " + windows);
});
```

Kết quả:

```text
A: [[10, 11, 12]]
B: [[50, 51, 52]]
```

Ví dụ dùng `LinkedHashMap` để thứ tự in nhóm dễ đối chiếu. Với `HashMap`, thứ tự duyệt các thiết bị không được đảm bảo. Nếu dữ liệu có timestamp riêng, cần sắp xếp các phần tử **bên trong từng nhóm** theo thứ tự nghiệp vụ trước khi tạo cửa sổ.

Trong pipeline lớn, bạn có thể dùng `Collectors.groupingBy` trước rồi xử lý các nhóm, nhưng phải nhận biết chi phí **giữ danh sách của từng nhóm trong bộ nhớ**. Gatherer chỉ nhận stream nguồn; nó không tự hiểu ranh giới thiết bị, người dùng hay phiên hoạt động.

### 15.1. Khi bộ dữ liệu thay đổi trong lúc duyệt

Hàm xử lý trong Stream nên **non-interfering**: không sửa collection nguồn khi traversal đang diễn ra. Nếu những thread khác có thể cập nhật list cảm biến, dùng snapshot, cơ chế đồng bộ hoặc loại nguồn hỗ trợ concurrency theo hợp đồng.

`windowSliding` cần duy trì quan hệ liền kề theo encounter order, nên việc thay đổi nguồn trong lúc duyệt có thể khiến các cửa sổ không còn mang ý nghĩa dữ liệu ổn định. Bản thân gatherer không tạo snapshot bất biến của toàn hệ thống.


## 16. Song song hóa: đúng kết quả không đồng nghĩa chạy nhanh hơn

Có thể đặt `parallel()` trên một nguồn ordered:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 6)
    .boxed()
    .parallel()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6]]
```

Mặc dù đầu vào có thể được xử lý theo chế độ song song, cửa sổ trượt phụ thuộc **ranh giới giữa những phần tử liền nhau**. Một cách chia nguồn thành các đoạn độc lập cần xử lý cả các phần tử chồng lấn ở ranh giới; không phải mọi gatherer đều có combiner cho phép ghép trạng thái một cách song song hiệu quả.

Điều được yêu cầu là **kết quả logic đúng theo encounter order** của nguồn ordered. Không có cam kết:

- Mỗi cửa sổ được tạo bởi một thread riêng.
- Mỗi đoạn nguồn có thể được xử lý hoàn toàn độc lập không cần phối hợp.
- Càng nhiều lõi CPU thì `windowSliding` càng nhanh.
- `parallel()` luôn được triển khai bằng cùng một chiến lược ở mọi JDK.

Với gatherer cửa sổ có trạng thái, xử lý song song có thể gặp chi phí **điều phối và giữ thứ tự**, nên đôi khi pipeline tuần tự nhanh hơn. Đừng suy luận hiệu năng từ chữ `parallel()`.

### 16.1. So sánh ngữ nghĩa tuần tự và song song

```java
List<Integer> source = IntStream.range(0, 100)
    .boxed()
    .toList();

List<List<Integer>> sequential = source.stream()
    .gather(Gatherers.windowSliding(5))
    .toList();

List<List<Integer>> parallel = source.parallelStream()
    .gather(Gatherers.windowSliding(5))
    .toList();

System.out.println(sequential.equals(parallel)); // true
```

Kiểm tra bằng `List.equals` giúp so sánh **toàn bộ nội dung và thứ tự cửa sổ**. Không kiểm thử bằng thread id, thứ tự log hoặc thời gian hoàn thành từng callback.

### 16.2. `unordered()` làm mất ngữ nghĩa kề nhau ổn định

```java
List<List<Integer>> windows = IntStream.rangeClosed(1, 6)
    .parallel()
    .unordered()
    .boxed()
    .gather(Gatherers.windowSliding(3))
    .toList();
```

Ở đây pipeline đã **bỏ yêu cầu encounter order**. Không nên mặc định các cửa sổ phản ánh đúng chuỗi `[1,2,3,4,5,6]` theo thứ tự nghiệp vụ. Việc một lần chạy tình cờ cho kết quả mong muốn không tạo thành bảo đảm API.

Đối với dữ liệu theo thời gian, chuỗi giao dịch, log hoặc các bản ghi có vị trí xác định, hãy **giữ thứ tự nguồn** hoặc sắp xếp theo khóa rõ ràng trước khi tạo cửa sổ.

## 17. Bộ nhớ, độ phức tạp và tài nguyên

Cửa sổ trượt có sự chồng lấn lớn: với `n >= k`, có `n - k + 1` cửa sổ và mỗi cửa sổ có `k` tham chiếu phần tử về mặt logic.

Nếu thu **tất cả cửa sổ** vào một `List<List<T>>`, số lượng phần tử được biểu diễn bên trong các cửa sổ có quy mô:

```text
k * (n - k + 1)
```

Ví dụ `n = 100_000` và `k = 1_000`: số cửa sổ khoảng 99.001, tổng số vị trí phần tử xét trên các cửa sổ gần 99 triệu. **Không nên** xem mỗi cửa sổ là dữ liệu độc lập miễn phí.

Triển khai JDK có thể dùng chiến lược lưu trữ hoặc chia sẻ vùng nhớ khác nhau, nên đừng suy từ công thức này rằng lượng cấp phát thực tế luôn chính xác bằng từng ấy object. Nhưng về mặt nghiệp vụ, việc **giữ tất cả cửa sổ** tạo áp lực bộ nhớ cao so với việc **tính một thống kê rồi bỏ cửa sổ**.

### 17.1. Đừng thu cửa sổ nếu chỉ cần thống kê

Thay vì:

```java
List<List<Integer>> windows = source.stream()
    .gather(Gatherers.windowSliding(100))
    .toList();

// Sau đó mới tính thống kê ở một vòng lặp khác.
```

Có thể xử lý trực tiếp:

```java
List<Double> averages = source.stream()
    .gather(Gatherers.windowSliding(100))
    .filter(window -> window.size() == 100)
    .map(window -> window.stream()
        .mapToDouble(Integer::doubleValue)
        .average()
        .orElseThrow())
    .toList();
```

Pipeline thứ hai chỉ giữ **các giá trị trung bình đầu ra**, không giữ toàn bộ danh sách cửa sổ trong kết quả. Tuy nhiên, việc tính lại trung bình của từng cửa sổ vẫn lặp qua tới 100 phần tử; khi cần tối ưu thật sự, có thể tính **rolling sum** với trạng thái được quản lý phù hợp.

### 17.2. Kích thước cửa sổ rất lớn trên nguồn ngắn

Tài liệu API lưu ý rằng để tối ưu hiệu quả, các cửa sổ **có thể được cấp phát liên tiếp hoặc sớm hơn nhu cầu**. Do đó yêu cầu `windowSliding(1_000_000)` trên một stream chỉ có vài phần tử vẫn **có nguy cơ tiêu tốn bộ nhớ lớn** trong thời gian đánh giá.

Hãy đặt giới hạn trên cho `windowSize` theo cấu hình hệ thống và kích thước bản ghi thực tế. Không coi `limit(1)` ở phía sau là bảo đảm tổng bộ nhớ sử dụng nhỏ.

### 17.3. Nguồn gắn với I/O phải được đóng

Nếu dữ liệu đến từ `Files.lines`, `Files.walk` hoặc tài nguyên I/O khác, bản thân terminal operation `toList` **không thay thế thao tác đóng nguồn**. Ví dụ Java 24+:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

static List<List<String>> adjacentLines(Path file)
        throws IOException {

    try (Stream<String> lines = Files.lines(
            file, StandardCharsets.UTF_8)) {

        return lines
            .gather(Gatherers.windowSliding(2))
            .toList();
    }
}
```

`try-with-resources` đóng `lines` khi hoàn thành hoặc gặp lỗi. Kết quả là những list chứa chuỗi đã đọc, không phụ thuộc stream I/O còn mở.

Đừng đọc cả tệp rất lớn rồi giữ toàn bộ các cặp dòng nếu chỉ cần kiểm tra điều kiện trên chúng. Hãy đặt terminal operation phù hợp hoặc chuyển thành kết quả nhỏ hơn trong lúc stream còn mở.

### 17.4. Thay đổi nguồn khi đang duyệt

Nếu một thread khác thay đổi cấu trúc nguồn như `ArrayList` trong lúc stream đang duyệt, kết quả không được bảo đảm. `windowSliding` không tạo ra snapshot của toàn bộ collection trước khi đọc.

Với yêu cầu tái hiện báo cáo, dùng nguồn ổn định hoặc snapshot theo phiên dữ liệu. Nếu phần tử là object mutable, cần xác định có sao chép sâu hay không; list cửa sổ unmodifiable không tự bảo vệ trạng thái của những object đó.

## 18. Chương trình kiểm chứng đầy đủ (Java 24+)

Để xác minh ngữ nghĩa, ta tạo một **thuật toán tham chiếu** dùng `List.subList` trên nguồn hữu hạn, rồi đối chiếu với `windowSliding` cho nhiều giá trị `n` và `k`.

Phương pháp này tránh kiểm tra theo một vài chuỗi ví dụ rồi kết luận vội. Nó kiểm tra:

- Nguồn rỗng.
- Nguồn ít phần tử hơn kích thước cửa sổ.
- `k = 1`, `k = n`, `k > n`.
- Số lượng cửa sổ và nội dung từng cửa sổ.
- Tính tương đương giữa stream tuần tự và song song.
- Khả năng từ chối kích thước cửa sổ không hợp lệ.
- Các cửa sổ không cho phép sửa.
- Dữ liệu lặp vẫn được giữ đúng số lần.

Tạo file `SlidingWindowCheck.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class SlidingWindowCheck {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static <T> List<List<T>> expected(
            List<T> source, int k) {

        if (k < 1) {
            throw new IllegalArgumentException("k phai >= 1");
        }

        List<List<T>> result = new ArrayList<>();

        if (source.isEmpty()) {
            return result;
        }

        if (source.size() < k) {
            result.add(new ArrayList<>(source));
            return result;
        }

        for (int i = 0; i <= source.size() - k; i++) {
            result.add(new ArrayList<>(
                source.subList(i, i + k)));
        }

        return result;
    }

    static <T> void verify(List<T> source, int k) {
        List<List<T>> reference = expected(source, k);

        List<List<T>> sequential = source.stream()
            .gather(Gatherers.windowSliding(k))
            .toList();

        List<List<T>> parallel = source.parallelStream()
            .gather(Gatherers.windowSliding(k))
            .toList();

        check(sequential.equals(reference),
            "Khac tham chieu: source=" + source + ", k=" + k);

        check(parallel.equals(reference),
            "Khac khi song song: source=" + source + ", k=" + k);

        int n = source.size();
        int expectedCount = n == 0 ? 0
            : n < k ? 1
            : n - k + 1;

        check(sequential.size() == expectedCount,
            "Sai so cua so");

        for (List<T> window : sequential) {
            check(!window.isEmpty(), "Cua so rong bat thuong");
            check(window.size() <= k, "Vuot kich thuoc k");
        }
    }

    public static void main(String[] args) {
        for (int n = 0; n <= 10; n++) {
            List<Integer> source = IntStream.range(0, n)
                .boxed()
                .toList();

            for (int k = 1; k <= 12; k++) {
                verify(source, k);
            }
        }

        verify(Arrays.asList(1, 1, 2, 2, 1, 1), 3);
        verify(Arrays.asList(7, 7), 5);

        boolean rejectedZero = false;
        try {
            Gatherers.windowSliding(0);
        } catch (IllegalArgumentException expected) {
            rejectedZero = true;
        }
        check(rejectedZero, "Phai tu choi windowSize=0");

        boolean rejectedNegative = false;
        try {
            Gatherers.windowSliding(-1);
        } catch (IllegalArgumentException expected) {
            rejectedNegative = true;
        }
        check(rejectedNegative,
            "Phai tu choi windowSize am");

        List<Integer> first = List.of(1, 2, 3).stream()
            .gather(Gatherers.windowSliding(2))
            .findFirst()
            .orElseThrow();

        boolean rejectedModification = false;
        try {
            first.add(99);
        } catch (UnsupportedOperationException expected) {
            rejectedModification = true;
        }
        check(rejectedModification,
            "Cua so phai unmodifiable");

        System.out.println("PASS: windowSliding");
    }
}
```

Kết quả dự kiến khi mọi kiểm tra qua:

```text
PASS: windowSliding
```

Chương trình này là **mẫu kiểm thử ngữ nghĩa**, không phải benchmark hiệu năng hay chứng minh hệ thống chịu được mọi quy mô. Đặc biệt, kiểm thử trên nguồn có giá trị trùng ngăn lỗi chỉ so sánh `Set` và bỏ qua số lần xuất hiện.

### 18.1. Vì sao cần thuật toán tham chiếu độc lập?

Nếu cả code sản phẩm và code test đều gọi `windowSliding`, hai đoạn có thể cùng hiểu sai một ca biên mà không phát hiện. Hàm `expected` ở trên dùng:

- Vòng lặp chỉ số.
- `subList(i, i + k)`.
- Một điều kiện riêng cho nguồn rỗng và nguồn ngắn hơn cửa sổ.

Nhờ cách viết khác, nó giúp kiểm tra đúng vị trí, độ dài và số cửa sổ theo quy tắc đã xác định. Với các ca đầu vào lớn hơn, có thể thêm kiểm thử thuộc tính (*property-based testing*) nhưng không nên tạo hàng triệu cửa sổ chỉ để kiểm tra với `toList`.

## 19. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `windowSliding(3)` lấy ba phần tử rồi nhảy ba phần tử | Tạo sai kiểu cửa sổ | Mỗi cửa sổ trượt **một phần tử** và chồng lấn `k - 1`. |
| Dùng `windowFixed` để tính trung bình trượt | Các đoạn không chồng lấn | Dùng `windowSliding` nếu cần mọi đoạn liên tiếp. |
| Cho rằng nguồn ngắn hơn `k` không có cửa sổ | Bỏ sót một cửa sổ ngắn | Kiểm tra `0 < n < k`. |
| Cho rằng luôn phát các cửa sổ ngắn ở cuối | Đếm sai số cửa sổ | Khi `n >= k`, chỉ phát cửa sổ **đủ k**. |
| Truy cập `window.get(k - 1)` với nguồn ngắn | `IndexOutOfBoundsException` | Lọc `window.size() == k` nếu cần đủ mẫu. |
| Gọi `windowSliding(0)` | `IllegalArgumentException` | Yêu cầu `k >= 1` và giới hạn trên phù hợp. |
| Gọi `window.add` hoặc `window.set` | `UnsupportedOperationException` | Dùng `new ArrayList<>(window)` nếu thật sự cần sửa. |
| Nghĩ list unmodifiable làm mọi phần tử bất biến | Dữ liệu mutable vẫn thay đổi | Dùng phần tử immutable/snapshot sâu. |
| Sắp xếp theo giá trị trước khi phân tích thời gian | Mất quan hệ liền kề theo thời gian | Sắp xếp theo timestamp/khóa phụ hoặc giữ nguồn đúng thứ tự. |
| Gọi `filter` trước gather nhưng muốn cặp kề nhau của nguồn gốc | Phần tử không kề nhau bị ghép cặp | Đặt gather trước filter cửa sổ khi cần. |
| Ghép dữ liệu hai thiết bị rồi gather một lượt | Cửa sổ trộn các nhóm | Gather riêng cho mỗi chuỗi/nhóm. |
| Xem k phần tử là k phút | Sai với sampling không đều | Dùng thuật toán cửa sổ theo thời gian nếu cần. |
| Thu tất cả cửa sổ của dữ liệu lớn vào RAM | Áp lực bộ nhớ cao | Tính thống kê trong pipeline, không giữ mọi list. |
| `windowSize` quá lớn trên stream nhỏ | Có thể cấp phát quá nhiều | Áp giới hạn theo nguồn và tài nguyên. |
| Mặc định `parallel()` tăng tốc | Chi phí phối hợp và trạng thái | Đo hiệu năng, không suy từ số thread. |
| Dùng `unordered()` với dữ liệu theo thứ tự nghiệp vụ | Cặp/cửa sổ không còn ý nghĩa ổn định | Duy trì encounter order hoặc sắp xếp. |
| Dùng `toList` trên nguồn vô hạn không giới hạn | Không hoàn thành, tốn vô hạn tài nguyên | `limit` kết quả hoặc ràng buộc đầu vào. |
| Nguồn là `Files.lines` nhưng không đóng | Rò rỉ tài nguyên I/O | `try-with-resources`. |
| Mã không biên dịch ở JDK 21 | Stream Gatherers chưa có trong JDK 21 | Dùng JDK 24+ hoặc giải pháp tương thích cũ. |

## 20. Bài tập thực hành

### Bài 1 — Tự tính cửa sổ

Cho nguồn `[2,4,6,8,10]` và `k = 3`. Hãy liệt kê mọi cửa sổ và số cửa sổ. Đối chiếu với `windowFixed(3)`.

### Bài 2 — Các ca biên

Dự đoán kết quả với `windowSliding(4)` trên `[]`, `[1]`, `[1,2,3]`, `[1,2,3,4]` và `[1,2,3,4,5]`.

### Bài 3 — Tổng từng cửa sổ

Dùng `windowSliding(2)` trên `[3,5,7,9]` rồi chuyển thành list tổng các cặp liên tiếp.

### Bài 4 — Chênh lệch giữa mẫu liền kề

Dùng `windowSliding(2)` để lấy chênh lệch từ `[100,98,103,99]`, với quy ước giá trị sau trừ giá trị trước. Nếu nguồn chỉ có một phần tử, danh sách chênh lệch hợp lệ là gì?

### Bài 5 — N-gram văn bản

Từ `["java","stream","api","java","stream"]`, tạo bigram rồi đếm tần suất từng bigram bằng `groupingBy` và `counting`.

### Bài 6 — Thứ tự thao tác

Cho `[1,2,3,4,5]`. So sánh `filter(n -> n % 2 == 1).gather(windowSliding(2))` với `gather(windowSliding(2)).filter(window -> window.get(0) % 2 == 1)`.

### Bài 7 — Dữ liệu nguồn ngắn hơn k

Một hệ thống cảnh báo chỉ được phép phát tín hiệu nếu có **ba mẫu liên tiếp** vượt 50. Nếu nguồn chỉ có `[60,70]`, liệu `windowSliding(3)` có tạo kết quả không? Làm sao ngăn cảnh báo sai?

### Bài 8 — Giới hạn tài nguyên

Một hệ thống có 100.000 mẫu, `k = 1.000`. Vì sao không nên mặc định thu tất cả cửa sổ thành `List<List<T>>` nếu chỉ cần giá trị trung bình? Nêu thêm lý do cần giới hạn trên cho `k`.

### Bài 9 — Chọn loại cửa sổ

Nghiệp vụ A cần mỗi 100 bản ghi tạo một batch không chồng lấn để xuất file; nghiệp vụ B cần phân tích 100 bản ghi gần nhất sau mỗi bản ghi mới. Chọn gatherer nào cho từng nhu cầu?

### Bài 10 — Bảo đảm thứ tự

Tại sao `source.parallelStream().unordered().gather(Gatherers.windowSliding(3))` không phù hợp khi nguồn là các sự kiện theo thời gian? Cần bổ sung tiêu chí gì nếu hai sự kiện có cùng timestamp?

## 21. Đáp án tham khảo

**Bài 1.** Các cửa sổ trượt là `[2,4,6]`, `[4,6,8]`, `[6,8,10]`, tổng `5 - 3 + 1 = 3`. `windowFixed(3)` tạo `[2,4,6]` và `[8,10]`; batch cuối ngắn vì không đủ ba phần tử.

**Bài 2.** Kết quả lần lượt: `[]`; `[[1]]`; `[[1,2,3]]`; `[[1,2,3,4]]`; `[[1,2,3,4],[2,3,4,5]]`. Nguồn rỗng không có cửa sổ; nguồn chưa đủ k chỉ có một cửa sổ ngắn.

**Bài 3.**

```java
List<Integer> sums = Stream.of(3, 5, 7, 9)
    .gather(Gatherers.windowSliding(2))
    .map(w -> w.get(0) + w.get(1))
    .toList();

System.out.println(sums); // [8, 12, 16]
```

**Bài 4.** Chênh lệch là `[-2,5,-4]`. Nguồn một phần tử có một cửa sổ ngắn, nhưng không có **cặp đủ hai phần tử**. Lọc `window.size() == 2` để kết quả chênh lệch là list rỗng.

```java
List<Integer> deltas = Stream.of(100, 98, 103, 99)
    .gather(Gatherers.windowSliding(2))
    .filter(w -> w.size() == 2)
    .map(w -> w.get(1) - w.get(0))
    .toList();
```

**Bài 5.**

```java
List<String> words = List.of(
    "java", "stream", "api", "java", "stream");

Map<String, Long> counts = words.stream()
    .gather(Gatherers.windowSliding(2))
    .map(w -> String.join(" ", w))
    .collect(java.util.stream.Collectors.groupingBy(
        text -> text,
        java.util.stream.Collectors.counting()));

System.out.println(counts.get("java stream")); // 2
```

Các bigram khác là `stream api` và `api java`, mỗi loại xuất hiện một lần.

**Bài 6.** Lọc số lẻ trước tạo nguồn `[1,3,5]`, cho `[[1,3],[3,5]]`. Gather trước tạo cặp của dãy gốc, sau đó giữ cặp có phần tử đầu lẻ: `[[1,2],[3,4]]`. Chọn cách đặt theo định nghĩa "kề nhau" của nghiệp vụ.

**Bài 7.** `windowSliding(3)` tạo **một cửa sổ ngắn `[60,70]`**. Muốn yêu cầu đủ ba mẫu, thêm `filter(w -> w.size() == 3)` trước khi kiểm tra `allMatch(v -> v > 50)`.

**Bài 8.** Với 100.000 mẫu và k = 1.000 có 99.001 cửa sổ đầy đủ; tổng số vị trí phần tử biểu diễn trên các cửa sổ khoảng 99 triệu. Thu mọi cửa sổ có thể tốn nhiều bộ nhớ, trong khi tính trung bình trực tiếp có thể chỉ giữ các số tổng hợp. API cho phép cửa sổ được cấp phát sớm, nên `k` rất lớn ngay trên nguồn nhỏ cũng có rủi ro bộ nhớ.

**Bài 9.** Nghiệp vụ A dùng `Gatherers.windowFixed(100)`, vì cần batch không chồng lấn. Nghiệp vụ B dùng `Gatherers.windowSliding(100)`, vì sau mỗi mẫu mới cần cửa sổ dịch một vị trí.

**Bài 10.** Cửa sổ trượt dựa trên quan hệ liền kề theo encounter order; `unordered()` bỏ ràng buộc đó, dẫn tới không có ý nghĩa về mẫu "trước/sau" nhất quán. Với sự kiện trùng timestamp, thêm khóa phụ xác định như ID tăng hoặc thứ tự nhập hợp lệ để tạo tổng thứ tự ổn định trước khi gather.

## 22. Checklist sử dụng `windowSliding` trong hệ thống thực tế

- [ ] JDK và toolchain hỗ trợ **Java 24+** nếu không muốn dùng preview.
- [ ] `windowSize >= 1` và có giới hạn trên theo bộ nhớ/tài nguyên.
- [ ] Phân biệt rõ **windowSliding (trượt 1)** và **windowFixed (batch không chồng lấn)**.
- [ ] Hiểu nguồn rỗng **không có cửa sổ**, nguồn `0 < n < k` có **một cửa sổ ngắn**.
- [ ] Có quyết định rõ nếu nghiệp vụ chỉ chấp nhận cửa sổ đủ `k`.
- [ ] Thứ tự gặp của dữ liệu phù hợp: timestamp, khóa phụ, thứ tự nguồn.
- [ ] Không bỏ encounter order với `unordered()` khi cần quan hệ liền kề.
- [ ] `filter` và `sorted` được đặt đúng vị trí so với `gather`.
- [ ] Nếu có nhiều thiết bị/phiên/người dùng, không để cửa sổ vượt ranh giới nhóm.
- [ ] Không sửa các list cửa sổ; các object mutable bên trong có chính sách riêng.
- [ ] Không thu toàn bộ `List<List<T>>` nếu chỉ cần số liệu tổng hợp.
- [ ] Đã đo chi phí tính lại thống kê O(n × k) khi `k` lớn.
- [ ] Nếu nguồn vô hạn, có terminal operation dừng hoặc giới hạn đầu vào hợp lý.
- [ ] Nếu nguồn từ tệp/I/O, có `try-with-resources` và xử lý lỗi.
- [ ] Không kỳ vọng `parallel()` tự động làm cửa sổ có trạng thái nhanh hơn.
- [ ] Đã kiểm thử k = 1, k = n, k > n, nguồn rỗng, dữ liệu trùng và thứ tự.
- [ ] Đã xác minh kết quả tuần tự/song song và dùng thuật toán tham chiếu độc lập.

## 23. Tổng kết và tài liệu tham khảo

`Gatherers.windowSliding(k)` giúp biểu đạt ngắn gọn yêu cầu "xét `k` phần tử liền nhau, dịch một phần tử để xét cửa sổ kế tiếp":

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Các nguyên tắc cốt lõi:

1. **Ngữ nghĩa:** cửa sổ có chồng lấn, mỗi lần trượt một phần tử. Với nguồn hữu hạn đủ dài, có `n-k+1` cửa sổ.
2. **Ca biên:** nguồn rỗng không phát cửa sổ; nguồn ngắn hơn `k` nhưng không rỗng phát **một cửa sổ ngắn**.
3. **Tính bất biến:** mỗi cửa sổ là list unmodifiable, không đồng nghĩa phần tử object bên trong cũng immutable.
4. **Pipeline:** có thể dùng `map`, `filter`, `reduce`, `collect` sau gatherer; thứ tự đặt `filter`, `sorted`, `limit` so với gatherer quyết định ý nghĩa nghiệp vụ.
5. **Hiệu năng:** kích thước cửa sổ, số lượng kết quả, độ chồng lấn và chi phí tính thống kê ảnh hưởng bộ nhớ/tốc độ; cần đo thực tế.
6. **Tài nguyên và thứ tự:** giữ encounter order cho dữ liệu tuần tự, đóng nguồn I/O, không giả định song song hóa luôn hiệu quả.
7. **Phiên bản:** Stream Gatherers chính thức từ Java 24 (JEP 485); Java 22/23 chỉ có bản preview.

Nguồn tham khảo chính thức:

- [Javadoc Java 24: Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) — hợp đồng của `windowSliding`, `windowFixed`, yêu cầu kích thước và list kết quả.
- [Oracle Java 24: Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html) — các ví dụ sử dụng gatherer trong pipeline.
- [OpenJDK JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — tiến trình chuẩn hóa tính năng.

Hiểu rõ `Gatherers.windowSliding` giúp bạn chuyển nhiều vòng lặp thủ công thành pipeline Java Stream API dễ đọc và kiểm thử, đồng thời kiểm soát đúng các trường hợp thiếu dữ liệu, thứ tự, bộ nhớ và tài nguyên khi đưa xử lý cửa sổ trượt vào ứng dụng thực tế.
