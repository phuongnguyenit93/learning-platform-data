# Kết hợp Gatherer bằng andThen

> **Chương:** Stream Gatherer  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Hiểu và dùng `Gatherer.andThen(...)` để ghép nhiều phép biến đổi Stream tùy chỉnh thành một Gatherer có thể tái sử dụng. Bài kết nối kiến thức pipeline lazy, `filter`/`map`, collector, Spliterator và xử lý song song; đặc biệt chú ý kiểu đầu vào/đầu ra, thứ tự ghép, trạng thái, `finisher`, short-circuit và hiệu năng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mục đích của `Gatherer`, `Stream.gather(...)` và phương thức `Gatherer.andThen(...)`.
2. Đọc đúng chữ ký generic, hiểu luồng kiểu `T → R → RR` và vai trò riêng của trạng thái `A`.
3. Chứng minh bằng ví dụ rằng `stream.gather(a.andThen(b))` tương đương về **ngữ nghĩa** với `stream.gather(a).gather(b)`.
4. Phân biệt phép **ghép tuần tự** (*composition*) với ghép kết quả (*concat*), ghép hai nhánh (*zip*) và terminal collector.
5. Tạo pipeline từ các Gatherer chuẩn: `windowFixed`, `windowSliding`, `scan`, `fold`, `mapConcurrent`.
6. Viết Gatherer đơn giản bằng `Gatherer.of(...)` hoặc `Gatherer.ofSequential(...)` rồi kết hợp với Gatherer chuẩn.
7. Giải thích cách một Gatherer có thể phát 0, 1 hoặc nhiều phần tử, phát kết quả cuối trong `finisher` và báo dừng khi downstream không nhận thêm.
8. Xử lý nguồn rỗng, cửa sổ cuối thiếu phần tử, thứ tự dữ liệu, lỗi null và giới hạn bộ nhớ.
9. Hiểu vì sao ghép Gatherer **không tự tạo combiner đúng**, không tự bảo đảm tăng tốc khi song song và không thay thế quản lý tài nguyên.
10. Kiểm thử chain bằng một pipeline tham chiếu độc lập, dữ liệu biên và các bất biến về thứ tự/kết quả.

**Yêu cầu phiên bản:** Ví dụ chính sử dụng **Java 24 trở lên**, khi Stream Gatherers đã là API chuẩn theo **JEP 485**. Gatherers từng được giới thiệu dưới dạng *preview* ở **JDK 22 (JEP 461)** và **JDK 23 (JEP 473)**. Mã Java 24 trong bài không cần `--enable-preview` chỉ để dùng `Gatherer`. Java 8, 11, 17 và 21 **không** có `Stream.gather`/`Gatherer.andThen` như API chuẩn.

Đây là một bài kiến thức tự chứa của module `JAVA_STREAM_API`, không phải hướng dẫn bật preview trên JDK cũ. Mọi ví dụ có `import java.util.stream.Gatherer` hoặc `Gatherers` đều nhắm tới API Java 24+.

---

## 1. Vì sao Stream cần Gatherer và phép ghép andThen?

Stream truyền thống cung cấp `filter`, `map`, `flatMap`, `distinct`, `sorted`, `reduce` và `collect`. Chúng xử lý được rất nhiều bài toán, nhưng có những phép biến đổi trung gian khó diễn đạt gọn:

- **Đóng gói theo cửa sổ:** cứ ba phần tử phát một `List`.
- **Tổng tích lũy:** sau mỗi phần tử phát tổng đã thấy đến thời điểm đó.
- **Giữ trạng thái riêng:** phát bản ghi khi khác bản ghi ngay trước nó.
- **Chỉ phát kết quả khi hết nguồn:** ghép toàn bộ chuỗi thành một phần tử.
- **Giới hạn công việc đồng thời:** thực thi mapper có giới hạn concurrency.

`Gatherer<T,A,R>` cho phép định nghĩa những phép biến đổi trung gian như vậy. Khi có hai bước cần thực hiện liên tiếp, `andThen` nối chúng thành **một Gatherer mới**:

~~~text
Stream<T>
    |
    v
Gatherer A: T -> R
    |
    | các phần tử R do A phát ra
    v
Gatherer B: R -> RR
    |
    v
Stream<RR>
    |
    v
terminal operation: toList / count / findFirst / collect...
~~~

Ví dụ quy trình:

~~~text
Số đơn hàng:          [10, 20, 30, 40, 50]
                              |
                    windowFixed(2)
                              |
                       [[10,20],
                        [30,40],
                        [50]]
                              |
                     map từng cửa sổ
                              |
                        [30, 70, 50]
                              |
                      scan tổng dồn
                              |
                        [30,100,150]
~~~

Ở đây `windowFixed` thay đổi “một phần tử” từ `Integer` thành `List<Integer>`. Gatherer tiếp theo có thể tính tổng từng list, rồi một Gatherer khác tính tổng tích lũy.

**Điểm cốt lõi:** `andThen` nối **đầu ra của bước trước** với **đầu vào của bước sau**. Nó không nối hai danh sách kết quả độc lập, không chạy hai nhánh cạnh nhau và không tự thay thế terminal operation.

---

## 2. Bản đồ API: Gatherer, Gatherers và Stream.gather

Các thành phần liên quan trong `java.util.stream`:

| API | Vai trò | Mức sử dụng |
|---|---|---|
| `Gatherer<T,A,R>` | Hợp đồng của phép biến đổi trung gian có thể có trạng thái | Định nghĩa hoặc tham chiếu một Gatherer |
| `Gatherer.andThen(that)` | Ghép kết quả của Gatherer hiện tại vào Gatherer sau | **Trọng tâm bài học** |
| `Stream.gather(gatherer)` | Gắn một Gatherer vào pipeline Stream | Khi thực thi pipeline |
| `Gatherers.windowFixed(n)` | Chia nguồn thành các nhóm liên tiếp kích thước n | Gatherer chuẩn |
| `Gatherers.windowSliding(n)` | Phát các cửa sổ trượt | Gatherer chuẩn |
| `Gatherers.scan(initial, scanner)` | Phát giá trị tích lũy sau mỗi input | Gatherer chuẩn |
| `Gatherers.fold(initial, folder)` | Phát một giá trị tổng hợp khi kết thúc | Gatherer chuẩn |
| `Gatherers.mapConcurrent(k, mapper)` | Biến đổi từng phần tử với giới hạn concurrency | Gatherer chuẩn |
| `Gatherer.of(...)` | Tạo Gatherer có thể có combiner | Gatherer tự định nghĩa |
| `Gatherer.ofSequential(...)` | Tạo Gatherer có đặc tính xử lý tuần tự | Gatherer tự định nghĩa |

Phân biệt tên:

- `Gatherer` (số ít): **interface** của một thao tác trung gian.
- `Gatherers` (số nhiều): lớp tiện ích cung cấp **Gatherer có sẵn**.
- `Collector`: thu thập ở **cuối** pipeline; `Gatherer` biến đổi **ở giữa** pipeline.
- `Gatherer.andThen`: ghép **hai Gatherer**, không phải `Consumer.andThen` hoặc `Function.andThen`.

### 2.1. Cấu trúc đầy đủ của Gatherer

Một Gatherer có thể định nghĩa:

1. `initializer()` — tạo trạng thái riêng `A`.
2. `integrator()` — nhận phần tử `T`, cập nhật trạng thái và có thể phát các phần tử `R`.
3. `combiner()` — gộp trạng thái trung gian khi phép gather hỗ trợ song song.
4. `finisher()` — thực hiện thao tác cuối khi phần tích lũy kết thúc, có thể phát thêm phần tử.

~~~text
                     +------------------------+
Input T ------------>| integrator(state, T)   |
                     |       |                |
                     |       +---- push(R) ---+----> Downstream
                     +------------------------+
                               |
                       state A thay đổi
                               |
                      sau khi kết thúc
                               |
                               v
                       finisher(state)
                               |
                          push(R) nếu cần
~~~

**Không phải Gatherer nào cũng sử dụng cả bốn phần.** Một Gatherer stateless đơn giản có thể chỉ cần `integrator`. Một Gatherer theo cửa sổ hoặc tổng dồn cần trạng thái; một Gatherer kiểu `fold` có thể đợi đến `finisher` mới phát kết quả.

---

## 3. Chữ ký chính xác của andThen

Chữ ký khái niệm trong Java 24:

~~~java
default <RR> Gatherer<T, ?, RR> andThen(
        Gatherer<? super R, ?, ? extends RR> that
);
~~~

Giả sử Gatherer ban đầu có kiểu:

~~~java
Gatherer<T, A, R> first;
~~~

thì `that` phải nhận được phần tử kiểu `R` mà `first` phát ra. Kết quả là một Gatherer mới:

~~~java
Gatherer<T, ?, RR> combined = first.andThen(that);
~~~

Bảng đọc kiểu:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `T` | Đầu vào **toàn chain** | `Integer` |
| `A` | Trạng thái riêng của Gatherer đầu | Ví dụ state dùng gom cửa sổ |
| `R` | Đầu ra bước đầu, **đầu vào bước sau** | `List<Integer>` |
| `RR` | Đầu ra **toàn chain** | `Integer` |
| `?` | Chi tiết trạng thái nội bộ đã được ẩn khỏi API của chain | Trạng thái ghép của hai Gatherer |

### 3.1. Vì sao có ? super R và ? extends RR?

- `? super R`: Gatherer sau có thể chấp nhận chính `R` hoặc một **kiểu cha** phù hợp.
- `? extends RR`: Gatherer sau có thể phát kiểu `RR` hoặc một **kiểu con** có thể dùng như `RR`.

Ví dụ một Gatherer phát `Integer` có thể được nối vào một Gatherer nhận `Number`, vì mọi `Integer` đều là `Number`.

~~~java
import java.util.stream.Gatherer;

Gatherer<Integer, ?, Integer> increment =
        Gatherer.<Integer, Integer>of(
                (ignored, n, downstream) ->
                        downstream.push(n + 1)
        );

Gatherer<Number, ?, String> formatNumber =
        Gatherer.<Number, String>of(
                (ignored, n, downstream) ->
                        downstream.push("n=" + n)
        );

Gatherer<Integer, ?, String> chain =
        increment.andThen(formatNumber);
~~~

Chain nhận `Integer` và phát `String`. Kiểu trạng thái của từng Gatherer không cần bị lộ trong biến `chain`.

### 3.2. Ghép sai kiểu không biên dịch

~~~java
Gatherer<Integer, ?, Integer> numbers = ...;
Gatherer<String, ?, String> trimTexts = ...;

// KHÔNG biên dịch: bước sau cần String,
// nhưng bước trước chỉ phát Integer.
// numbers.andThen(trimTexts);
~~~

Muốn nối đúng, cần một bước `Integer → String` hoặc thay đổi kiểu đầu ra của Gatherer trước. Không ép kiểu một cách tùy ý để che giấu thiết kế sai.

### 3.3. Truyền null là lỗi

~~~java
// Ném NullPointerException:
// chain.andThen(null);
~~~

Một Gatherer `null` không phải “bước rỗng” hợp lệ. Nếu không có công đoạn tùy chọn, xây chain có điều kiện trong mã ứng dụng, hoặc dùng một Gatherer pass-through đã được định nghĩa rõ.

---

## 4. Định luật cơ bản: hai lần gather tương đương andThen

Javadoc của `Gatherer.andThen` cam kết kết quả có ngữ nghĩa tương đương với việc nối hai thao tác gather liên tiếp.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> scan =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, String> asText =
        Gatherer.<Integer, String>of(
                (ignored, sum, downstream) ->
                        downstream.push("sum=" + sum)
        );

List<String> composed = Stream.of(1, 2, 3, 4)
        .gather(scan.andThen(asText))
        .toList();

List<String> separate = Stream.of(1, 2, 3, 4)
        .gather(scan)
        .gather(asText)
        .toList();

System.out.println(composed);
// [sum=1, sum=3, sum=6, sum=10]

System.out.println(composed.equals(separate)); // true
~~~

~~~text
Cách 1: gather(scan.andThen(asText))
          Integer --> Integer --> String

Cách 2: gather(scan).gather(asText)
          Integer --> Integer --> String
~~~

**Tương đương ngữ nghĩa** không có nghĩa framework phải tạo cùng số lượng object, dùng cùng lịch thread hoặc gọi hàm người dùng theo một lịch trình quan sát được qua side effect. Mục tiêu so sánh là **kết quả theo hợp đồng**, không phải thứ tự in debug của những lambda chạy song song.

### 4.1. andThen tạo một Gatherer, không chạy ngay

~~~java
Gatherer<Integer, ?, String> reusable =
        scan.andThen(asText); // Chưa có nguồn, chưa phát phần tử.

List<String> result = Stream.of(5, 6)
        .gather(reusable)
        .toList();             // Terminal operation tiêu thụ nguồn.
~~~

Trong pipeline lazy, khai báo `Gatherer` hoặc gọi `andThen` **không tự đánh giá** các phần tử của Stream. `toList()`, `collect()`, `count()`, `findFirst()` hoặc terminal khác mới kích hoạt xử lý.

### 4.2. Không dùng lại chính một Stream đã bị tiêu thụ

~~~java
// Sai mô hình:
// Stream<Integer> source = Stream.of(1, 2, 3);
// source.gather(scan).toList();
// source.gather(scan.andThen(asText)).toList();
~~~

Hãy tạo **hai Stream mới từ cùng nguồn có thể duyệt lại** hoặc dùng `Supplier<Stream<T>>` để so sánh. Có thể tái sử dụng **định nghĩa Gatherer không giữ state ngoài không hợp lệ**; trạng thái của Gatherer chuẩn được tạo cho từng lần chạy, không phải do biến `Gatherer` lưu sẵn kết quả.

---

## 5. Ví dụ nền tảng: windowFixed rồi tính tổng từng cửa sổ

`Gatherers.windowFixed(n)` nhận `Stream<T>` và phát `Stream<List<T>>`. Ta nối nó với một Gatherer nhận `List<Integer>`, tính tổng và phát `Integer`.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, List<Integer>> windows =
        Gatherers.windowFixed(3);

Gatherer<List<Integer>, ?, Integer> sumWindow =
        Gatherer.<List<Integer>, Integer>of(
                (ignored, window, downstream) ->
                        downstream.push(
                                window.stream()
                                      .mapToInt(Integer::intValue)
                                      .sum()
                        )
        );

Gatherer<Integer, ?, Integer> windowSums =
        windows.andThen(sumWindow);

List<Integer> result = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(windowSums)
        .toList();

System.out.println(result); // [6, 15, 7]
~~~

Diễn giải:

~~~text
Input Integer:        1 2 3 4 5 6 7
                         |
                  windowFixed(3)
                         |
Output List<Integer>: [1,2,3] [4,5,6] [7]
                         |
                     sumWindow
                         |
Output Integer:         6      15     7
~~~

Cửa sổ cuối có thể **ít hơn n phần tử**. `windowFixed(3)` không tự bỏ `[7]`. `sumWindow` phải tính đúng với cả list nhỏ hơn kích thước chuẩn.

### 5.1. So với gather liên tiếp

~~~java
List<Integer> sameResult = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(windows)
        .gather(sumWindow)
        .toList();

System.out.println(result.equals(sameResult)); // true
~~~

Hai cách diễn đạt cùng logic; `andThen` có lợi khi muốn đặt tên và tái sử dụng phép biến đổi **“gom 3 rồi tính tổng”**.

### 5.2. Khi nào không cần andThen?

~~~java
List<Integer> alsoValid = Stream.of(1, 2, 3, 4, 5, 6, 7)
        .gather(Gatherers.windowFixed(3))
        .map(window -> window.stream()
                             .mapToInt(Integer::intValue)
                             .sum())
        .toList();
~~~

Một `map` thông thường là đủ nếu giai đoạn sau chỉ biến đổi **một-một** và không cần đóng gói thành Gatherer riêng. `andThen` không thay thế `map` trong mọi bài toán; nó là công cụ để **tổ hợp những Gatherer** có thể xử lý nhiều kiểu trạng thái và số lượng đầu ra.

---

## 6. Ví dụ nâng cao: tổng cửa sổ rồi tính tổng tích lũy

Có ba giai đoạn:

1. `windowFixed(2)`: `Integer → List<Integer>`.
2. `sumWindow`: `List<Integer> → Integer`.
3. `scan`: `Integer → Integer`, phát tổng tích lũy sau mỗi cửa sổ.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, List<Integer>> window2 =
        Gatherers.windowFixed(2);

Gatherer<List<Integer>, ?, Integer> sumEach =
        Gatherer.<List<Integer>, Integer>of(
                (ignored, xs, downstream) ->
                        downstream.push(
                                xs.stream()
                                  .mapToInt(Integer::intValue)
                                  .sum()
                        )
        );

Gatherer<Integer, ?, Integer> running =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, Integer> pipeline =
        window2.andThen(sumEach).andThen(running);

List<Integer> totals = Stream.of(1, 2, 3, 4, 5)
        .gather(pipeline)
        .toList();

System.out.println(totals); // [3, 10, 15]
~~~

Vì:

~~~text
Input:             [1, 2, 3, 4, 5]
windowFixed(2):    [[1,2], [3,4], [5]]
sumEach:           [3, 7, 5]
scan(sum):         [3, 10, 15]
~~~

Với `scan`, giá trị do `initial` trả về là **trạng thái xuất phát**, không được phát như một phần tử đứng đầu. Vì vậy kết quả có ba số ứng với ba cửa sổ, không phải bốn số bắt đầu từ `0`.

### 6.1. Tương đương ba lần gather riêng

~~~java
List<Integer> separateStages = Stream.of(1, 2, 3, 4, 5)
        .gather(window2)
        .gather(sumEach)
        .gather(running)
        .toList();

System.out.println(totals.equals(separateStages)); // true
~~~

### 6.2. Tạo thành một công cụ tái sử dụng

~~~java
static Gatherer<Integer, ?, Integer>
runningWindowSums(int windowSize) {
    Gatherer<Integer, ?, List<Integer>> windows =
            Gatherers.windowFixed(windowSize);

    Gatherer<List<Integer>, ?, Integer> sumWindow =
            Gatherer.<List<Integer>, Integer>of(
                    (ignored, xs, downstream) ->
                            downstream.push(
                                    xs.stream()
                                      .mapToInt(Integer::intValue)
                                      .sum()
                            )
            );

    Gatherer<Integer, ?, Integer> running =
            Gatherers.scan(() -> 0, Integer::sum);

    return windows.andThen(sumWindow).andThen(running);
}
~~~

Đặt phương thức trong một lớp Java. Chúng ta có thể dùng:

~~~java
List<Integer> a = Stream.of(1, 2, 3, 4, 5)
        .gather(runningWindowSums(2))
        .toList();

List<Integer> b = Stream.of(10, 20, 30)
        .gather(runningWindowSums(2))
        .toList();

System.out.println(a); // [3, 10, 15]
System.out.println(b); // [30, 60]
~~~

Hàm tạo một Gatherer **mới theo cấu hình cửa sổ**. Nó không giữ một tổng `int` bên ngoài dùng chung giữa các luồng đánh giá.

**Lưu ý độ chính xác:** Ví dụ dùng `int` để đơn giản. Với dữ liệu có thể làm tổng `int` tràn, cần chọn `long`/`BigInteger` thích hợp thay vì hy vọng `andThen` tự khắc phục overflow.

---

## 7. Thứ tự ghép quan trọng: andThen không giao hoán

Nói chung:

~~~text
A.andThen(B) != B.andThen(A)
~~~

Thậm chí nhiều cặp Gatherer không thể đảo vì **không khớp kiểu dữ liệu**. Với các Gatherer cùng kiểu, hai thứ tự vẫn có thể cho kết quả khác.

### 7.1. Ví dụ scan rồi fold

`scan` phát **từng tổng tích lũy**; `fold` thu toàn bộ những tổng ấy thành một kết quả cuối.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> running =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, Integer> foldSum =
        Gatherers.fold(() -> 0, Integer::sum);

List<Integer> scanThenFold = Stream.of(1, 2, 3, 4)
        .gather(running.andThen(foldSum))
        .toList();

System.out.println(scanThenFold); // [20]
~~~

Giải thích:

~~~text
Input:     [1, 2, 3, 4]
scan:      [1, 3, 6, 10]
fold:      [1 + 3 + 6 + 10]
Output:    [20]
~~~

### 7.2. Ví dụ fold rồi scan

~~~java
List<Integer> foldThenScan = Stream.of(1, 2, 3, 4)
        .gather(foldSum.andThen(running))
        .toList();

System.out.println(foldThenScan); // [10]
~~~

Giải thích:

~~~text
Input:     [1, 2, 3, 4]
fold:      [10]     (một phần tử phát cuối nguồn)
scan:      [10]     (chỉ xử lý một phần tử)
Output:    [10]
~~~

Hai pipeline có **cùng kiểu đầu/cuối** nhưng kết quả **khác nhau**. Đây là phản ví dụ đơn giản nhất cho suy luận sai rằng `andThen` có tính giao hoán.

### 7.3. Associativity ở mức kết quả

Với ba Gatherer `A: T→U`, `B: U→V`, `C: V→W`, hai biểu thức sau có cùng dòng biến đổi theo hợp đồng:

~~~java
Gatherer<T, ?, W> leftGrouped =
        A.andThen(B).andThen(C);

Gatherer<T, ?, W> rightGrouped =
        A.andThen(B.andThen(C));
~~~

Đây là **mã minh họa kiểu**, không phải đoạn Java biên dịch độc lập vì các biến `A`/`B`/`C` và type parameters `T`/`U`/`V`/`W` cần được khai báo. Ý nghĩa là cả hai nhóm ngoặc đều truyền dữ liệu theo thứ tự `A → B → C`.

**Không** suy ra hai cách có cùng chi phí cấp phát, cùng thread, cùng số lần gọi lambda quan sát qua side effect. Tính tương đương được xét trên **hành vi đầu ra theo hợp đồng**.

---

## 8. windowSliding và hậu xử lý theo chuỗi cửa sổ

`Gatherers.windowSliding(n)` tạo cửa sổ trượt. Với n = 3 và đầu vào 1..5:

~~~text
[1,2,3]
  [2,3,4]
    [3,4,5]
~~~

Ta có thể ghép một Gatherer lấy trung bình từng cửa sổ:

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, List<Integer>> sliding =
        Gatherers.windowSliding(3);

Gatherer<List<Integer>, ?, Double> averageWindow =
        Gatherer.<List<Integer>, Double>of(
                (ignored, window, downstream) ->
                        downstream.push(
                                window.stream()
                                      .mapToInt(Integer::intValue)
                                      .average()
                                      .orElseThrow()
                        )
        );

List<Double> averages = Stream.of(1, 2, 3, 4, 5)
        .gather(sliding.andThen(averageWindow))
        .toList();

System.out.println(averages); // [2.0, 3.0, 4.0]
~~~

`average().orElseThrow()` an toàn **trong ví dụ** vì cửa sổ trượt được phát có ít nhất một phần tử khi `windowSize >= 1`. Nếu bạn viết một Gatherer phát các list có thể rỗng, phải chọn chính sách xử lý rỗng rõ ràng.

### 8.1. Nguồn ngắn hơn kích thước window

Nếu input có ít phần tử hơn `windowSliding(3)`, Gatherer có thể phát **một cửa sổ chứa mọi phần tử hiện có**.

~~~java
List<List<Integer>> windows = Stream.of(1, 2)
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(windows); // [[1, 2]]
~~~

Với nguồn rỗng, không có cửa sổ. Với `windowFixed`, cửa sổ cuối cũng có thể ngắn hơn n. Không nên viết downstream mặc định mọi list đều có đúng n phần tử mà không kiểm tra hợp đồng cụ thể của loại cửa sổ.

### 8.2. Chi phí

Cửa sổ trượt có nhiều phần tử **chồng lấp**; tổng lượng phần tử xuất hiện qua các cửa sổ có thể lớn hơn kích thước input. Ghép thêm một Gatherer tính thống kê cho từng cửa sổ có thể làm lại một số phép tính.

Nếu cần tối ưu sâu, cân nhắc thuật toán cập nhật thống kê trượt theo state chuyên dụng. `andThen` giúp mô tả **cấu trúc pipeline**, không tự biến thuật toán O(n·windowSize) thành O(n).

---

## 9. Finisher: phần tử phát ở cuối vẫn đi qua Gatherer sau

Một số Gatherer chỉ phát output trong `finisher` sau khi upstream hoàn tất. `Gatherers.fold` là ví dụ quan trọng.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> foldSum =
        Gatherers.fold(() -> 0, Integer::sum);

Gatherer<Integer, ?, String> format =
        Gatherer.<Integer, String>of(
                (ignored, n, downstream) ->
                        downstream.push("TOTAL=" + n)
        );

List<String> result = Stream.of(3, 5, 7)
        .gather(foldSum.andThen(format))
        .toList();

System.out.println(result); // [TOTAL=15]
~~~

~~~text
Stream.of(3,5,7)
   |
   v
foldSum:
  integrator nhận 3,5,7;
  không phát từng tổng trung gian;
  finisher phát 15
   |
   v
format:
  integrator nhận 15
  và phát "TOTAL=15"
   |
   v
["TOTAL=15"]
~~~

Vì output của `fold` được phát **cuối nguồn**, Gatherer đứng sau vẫn cần nhận và xử lý nó. Việc ghép không có nghĩa “bỏ qua finisher của bước trước”.

### 9.1. Trường hợp nguồn rỗng

Theo hợp đồng `Gatherers.fold`, khi không có input và xử lý hoàn tất bình thường, nó phát **giá trị initial**.

~~~java
List<Integer> foldedEmpty = Stream.<Integer>empty()
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(foldedEmpty); // [0]
~~~

Ngược lại, `windowFixed(3)` trên Stream rỗng không phát cửa sổ:

~~~java
List<List<Integer>> emptyWindows = Stream.<Integer>empty()
        .gather(Gatherers.windowFixed(3))
        .toList();

System.out.println(emptyWindows); // []
~~~

Khi ghép hai bước:

~~~java
Gatherer<Integer, ?, List<Integer>> windows =
        Gatherers.windowFixed(3);

Gatherer<List<Integer>, ?, Integer> countWindows =
        Gatherers.fold(() -> 0,
                (count, window) -> count + 1);

List<Integer> counts = Stream.<Integer>empty()
        .gather(windows.andThen(countWindows))
        .toList();

System.out.println(counts); // [0]
~~~

**Điểm dễ nhầm:** “Gatherer A không phát output” không đồng nghĩa “toàn chain không có output”, vì Gatherer B có thể phát giá trị trong `finisher` ngay cả khi không nhận input.

### 9.2. Finisher khác terminal Collector.finisher

- `Gatherer.finisher` có thể **phát thêm các phần tử vào downstream**, vẫn là một phần của phép biến đổi Stream.
- `Collector.finisher` chuyển trạng thái thu thập `A` thành **kết quả terminal** `R` của `collect`.
- `Gatherer.andThen` ghép các thao tác **trung gian**; `Collectors.collectingAndThen` hoàn thiện một **kết quả collector**. Hai API không thể thay thế cho nhau.

---

## 10. Tự tạo Gatherer stateless rồi ghép

Ta muốn chuẩn hóa chuỗi và bỏ những chuỗi trống, sau đó chia các chuỗi còn lại thành từng cặp.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<String, ?, String> nonBlankTrimmed =
        Gatherer.<String, String>of(
                (ignored, text, downstream) -> {
                    if (downstream.isRejecting()) {
                        return false;
                    }

                    String trimmed = text.trim();
                    if (trimmed.isEmpty()) {
                        return true; // Không phát phần tử.
                    }

                    return downstream.push(trimmed);
                }
        );

Gatherer<String, ?, List<String>> pairs =
        nonBlankTrimmed.andThen(
                Gatherers.windowFixed(2)
        );

List<List<String>> result = Stream
        .of(" An ", " ", "Binh", "", " Chi ")
        .gather(pairs)
        .toList();

System.out.println(result); // [[An, Binh], [Chi]]
~~~

Hợp đồng:

- Một input `String` có thể tạo **0 hoặc 1** output từ `nonBlankTrimmed`.
- `windowFixed(2)` chỉ nhìn thấy **những String thực sự được phát**; các chuỗi trống đã biến mất trước bước gom.
- Nếu dùng `windowFixed(2).andThen(...)` với một bước xử lý list, bạn đang nhóm **dữ liệu gốc trước**; đó là quy trình khác.

### 10.1. Khi nào dùng filter + map thông thường?

Cùng bài toán có thể viết:

~~~java
List<List<String>> alsoValid = Stream
        .of(" An ", " ", "Binh", "", " Chi ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .gather(Gatherers.windowFixed(2))
        .toList();
~~~

`map` và `filter` thường rõ hơn nếu không cần đóng gói phép biến đổi thành một Gatherer tái sử dụng. Chỉ tự viết Gatherer khi có yêu cầu về phát số lượng phần tử, state, short-circuit, finisher hoặc thành phần compose cụ thể.

---

## 11. Gatherer stateful tự định nghĩa: dừng sau mốc nhưng giữ mốc

Yêu cầu: Stream số nguyên có encounter order, lấy phần tử từ đầu **cho đến khi gặp số đầu tiên >= threshold**, bao gồm cả số chạm ngưỡng.

Một Gatherer kiểu này có thể dừng nguồn sớm:

~~~java
import java.util.stream.Gatherer;

static Gatherer<Integer, ?, Integer>
takeUntilInclusive(int threshold) {
    return Gatherer.<Integer, Integer>ofSequential(
            (ignored, value, downstream) -> {
                // Phát phần tử, nếu downstream còn nhận.
                boolean wantsMore = downstream.push(value);

                // Dừng sau phần tử đầu tiên >= threshold.
                return wantsMore && value < threshold;
            }
    );
}
~~~

Dù không lưu state riêng, `ofSequential` được chọn để nhấn mạnh ngữ nghĩa **tiền tố theo thứ tự đầu vào**. Không tự công bố một combiner khiến dữ liệu bị chia mà không thể xác định mốc đầu tiên toàn cục.

### 11.1. Ghép với scan

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<Integer, ?, Integer> stopAtThree =
        takeUntilInclusive(3);

Gatherer<Integer, ?, Integer> running =
        Gatherers.scan(() -> 0, Integer::sum);

List<Integer> result = Stream.of(1, 2, 3, 4, 5)
        .gather(stopAtThree.andThen(running))
        .toList();

System.out.println(result); // [1, 3, 6]
~~~

Sau khi phát `3`, Gatherer trước trả `false` để không nhận thêm input. `running` chỉ nhìn thấy `[1,2,3]`.

### 11.2. Đảo thứ tự có thể đổi điểm dừng

~~~java
List<Integer> other = Stream.of(1, 2, 3, 4, 5)
        .gather(running.andThen(stopAtThree))
        .toList();

System.out.println(other); // [1, 3]
~~~

Vì `running` phát `[1,3,6,10,15]`, Gatherer dừng ở **tổng tích lũy 3** (phần tử thứ hai), nên kết quả là `[1,3]`. Đây là một ví dụ nữa cho thấy `andThen` **có thứ tự**.

### 11.3. Không nuốt tín hiệu từ downstream.push

~~~java
// Kém an toàn nếu downstream dừng sớm:
// (ignored, value, downstream) -> {
//     downstream.push(value);
//     return true; // Cố yêu cầu upstream tiếp tục.
// }
~~~

`downstream.push(value)` trả `boolean` cho biết downstream còn muốn nhận thêm hay không. Nếu trả `false`, không tiếp tục phát vào downstream. `downstream.isRejecting()` có thể hỗ trợ kiểm tra sớm, nhưng là *best-effort*; không được dùng nó để thay quy tắc xử lý giá trị trả về từ `push`.

Ví dụ `takeUntilInclusive` trả `wantsMore && ...`, vì vậy tôn trọng cả điều kiện dừng của chính Gatherer và yêu cầu dừng từ terminal operation phía sau.

---

## 12. Custom finisher: phát kết quả sau khi hết nguồn

Ví dụ một Gatherer giữ số phần tử đã nhận, chỉ phát `"count=N"` khi upstream kết thúc.

~~~java
import java.util.stream.Gatherer;

static Gatherer<Integer, ?, String> countAsText() {
    class CountState {
        long count;
    }

    return Gatherer.<Integer, CountState, String>ofSequential(
            CountState::new,
            (state, item, downstream) -> {
                state.count++;
                return true;
            },
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push("count=" + state.count);
                }
            }
    );
}
~~~

Trong phần code này:

- `initializer` tạo một `CountState` cho mỗi lần đánh giá thích hợp.
- `integrator` tăng count nhưng **không phát output**.
- `finisher` phát một String khi kết thúc.
- Không lưu state hay đối tượng `downstream` vào field static để dùng về sau.

### 12.1. Ghép custom finisher với Gatherer khác

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

Gatherer<String, ?, Integer> textLength =
        Gatherer.<String, Integer>of(
                (ignored, text, downstream) ->
                        downstream.push(text.length())
        );

List<Integer> result = Stream.of(3, 7, 11)
        .gather(countAsText().andThen(textLength))
        .toList();

System.out.println(result); // [7]
~~~

`"count=3"` có độ dài `7`. Output của finisher bước trước được chuyển tiếp qua integrator của bước sau, dù bước trước không phát gì trong khi đọc từng phần tử.

### 12.2. Short-circuit và finisher

Không dựa vào việc finisher của từng Gatherer luôn phát thành công mọi giá trị:

- Terminal `limit`/`findFirst` có thể khiến downstream **không nhận thêm**.
- Nếu một integrator dừng sớm, xử lý phần input còn lại có thể bị bỏ.
- Nếu downstream đã từ chối, finisher không nên cố gửi thêm phần tử bằng mọi giá.
- Đừng đặt side effect bắt buộc như commit transaction, gửi email hoặc đóng file handle chỉ trong một finisher rồi giả định mọi đường lỗi/hủy đều sẽ gọi nó đúng một lần.

Đối với tài nguyên, dùng `try-with-resources` và các cơ chế đảm bảo cleanup chuyên biệt của ứng dụng.

---

## 13. Việc compose ảnh hưởng ra sao đến state của hai Gatherer?

Giả sử:

~~~text
A: windowFixed(3)     state A gom số vào cửa sổ
B: scan(sum)           state B giữ tổng tích lũy
C: fold(...)           state C giữ một giá trị tổng hợp cuối
~~~

Khi ghép `A.andThen(B).andThen(C)`, mỗi stage vẫn có **ngữ nghĩa state riêng**. Trạng thái của B không phải trạng thái của A; tổng tích lũy của B được tính từ **những output A đã phát**, chứ không trực tiếp từ mọi input T.

Một sơ đồ:

~~~text
Stream<T>
  |
  v
A.initializer / A.integrator / A.finisher
  |          |
  |          +-- có thể phát trong finisher
  v
R
  |
  v
B.initializer / B.integrator / B.finisher
  |
  v
RR
  |
  v
C.initializer / C.integrator / C.finisher
  |
  v
Final Output
~~~

`andThen` trả một Gatherer **bao gói sự kết hợp**. Kiểu trạng thái nội bộ được ẩn bằng wildcard `?`, vì mã gọi không cần biết hai Gatherer lưu những gì bên trong.

### 13.1. Không đưa state mutable ra ngoài pipeline

~~~java
// Không nên:
// List<Integer> shared = new ArrayList<>();
// Gatherer<Integer, ?, Integer> g = Gatherer.of(
//     (unused, n, downstream) -> {
//         shared.add(n);       // Cùng list chia sẻ giữa các lần evaluate.
//         return downstream.push(n);
//     }
// );
~~~

State dùng để theo dõi tiến trình phải thuộc về **lần đánh giá** (qua initializer hoặc cơ chế state tương ứng), không phải một biến mutable dùng chung cho nhiều pipeline.

**Ràng buộc API:** Một Gatherer tự định nghĩa không được giữ tham chiếu tới state được truyền vào hoặc `Gatherer.Downstream` vượt quá thời gian gọi hàm nhận các tham chiếu đó, và không được chuyển chúng sang thread khác để dùng tùy tiện.

---

## 14. Parallel stream: andThen không tự làm Gatherer song song hóa

Một Gatherer chỉ có thể được đánh giá song song nếu mô hình và **combiner** của nó cho phép. `Gatherer.ofSequential(...)` chỉ mô tả một Gatherer **tuần tự**; có thể xuất hiện trong pipeline có `parallel()`, nhưng không vì thế nó tự được chia và gộp an toàn.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

Gatherer<Integer, ?, Integer> scan =
        Gatherers.scan(() -> 0, Integer::sum);

Gatherer<Integer, ?, Integer> fold =
        Gatherers.fold(() -> 0, Integer::sum);

List<Integer> result = IntStream.rangeClosed(1, 4)
        .boxed()
        .parallel()
        .gather(scan.andThen(fold))
        .toList();

System.out.println(result); // [20]
~~~

Kết quả vẫn phải tuân thủ hợp đồng biến đổi đã ghép, nhưng **đừng suy ra** hai stage thực sự xử lý trên nhiều thread. Những phép tính phụ thuộc thứ tự như prefix scan/fold có thể giới hạn khả năng song song.

### 14.1. Các điều kiện của một combiner đúng

Nếu tự viết Gatherer có combiner, phải bảo đảm:

1. **Mỗi phân vùng được khởi tạo trạng thái riêng**, không sửa một object dùng chung không an toàn.
2. **Combiner gộp hai trạng thái theo đúng ý nghĩa của phép biến đổi**, có tính kết hợp khi cần chia/gộp nhiều tầng.
3. Kết quả không phụ thuộc một lịch phân vùng cụ thể nếu API cho phép đánh giá theo những cách khác nhau.
4. **Ngữ nghĩa encounter order** vẫn được giữ ở những bước cần bảo đảm thứ tự.
5. Việc dừng sớm và hủy các phần thừa không được dẫn tới output sai.

Không thể lấy combiner cộng số của một Gatherer rồi áp vào Gatherer gom cửa sổ mà không chứng minh **ranh giới cửa sổ giữa hai phân vùng** được xử lý đúng.

### 14.2. Nếu một stage chỉ có thể chạy tuần tự?

Một chain gồm một Gatherer tuần tự và một Gatherer có thể song song vẫn phải giữ **ngữ nghĩa của toàn chain**. Bước tuần tự có thể tạo nút nghẽn; việc có một stage có combiner không tự làm các stage còn lại song song hóa.

`andThen` là phép **tổ hợp ngữ nghĩa**, không phải lời hứa toàn bộ pipeline được triển khai như một thuật toán song song tối ưu.

### 14.3. mapConcurrent có nghĩa gì?

`Gatherers.mapConcurrent(maxConcurrency, mapper)` có thể thực thi mapper với **mức đồng thời tối đa** được cấu hình, sử dụng virtual threads, đồng thời giữ thứ tự đầu ra theo nguồn. Nó khác với việc bật `parallelStream()` toàn pipeline.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Gatherer<String, ?, String> enrich =
        Gatherers.mapConcurrent(
                3,
                (String code) -> "enriched:" + code
        );

Gatherer<String, ?, List<String>> batch =
        Gatherers.windowFixed(2);

List<List<String>> output = Stream.of("A", "B", "C")
        .gather(enrich.andThen(batch))
        .toList();

System.out.println(output);
// [[enriched:A, enriched:B], [enriched:C]]
~~~

Ví dụ mapper chỉ ghép chuỗi cho dễ kiểm chứng; trong thực tế `mapConcurrent` thích hợp hơn với công việc độc lập có chi phí chờ như gọi I/O, và phải giới hạn concurrency theo tài nguyên. Đừng gọi mapper trên dữ liệu mutable dùng chung mà không có kiểm soát thread.

---

## 15. andThen không phải collect, collectingAndThen hay Function.andThen

Bốn cách có chữ “Then” hoặc mô hình ghép dễ gây nhầm:

| API | Nằm ở đâu? | Đầu ra |
|---|---|---|
| `Function.andThen` | Ghép hai hàm biến đổi một-một | Một hàm mới |
| `Consumer.andThen` | Ghép hai hành động `void` | Một consumer mới |
| `Collector`/`Collectors.collectingAndThen` | Hoàn thiện kết quả thu thập ở terminal | Kết quả cuối `R` của `collect` |
| `Gatherer.andThen` | Ghép **hai thao tác trung gian có thể có state** | Một Gatherer mới |

### 15.1. Function.andThen không có cơ chế phát nhiều output hoặc finisher

~~~java
import java.util.function.Function;

Function<Integer, Integer> plusOne = n -> n + 1;
Function<Integer, String> toText = n -> "n=" + n;

Function<Integer, String> f = plusOne.andThen(toText);

System.out.println(f.apply(4)); // n=5
~~~

Hàm truyền thống không có `integrator`, `downstream.push`, `finisher` hoặc combiner như Gatherer. Dùng `Function.andThen` khi chỉ cần chuỗi biến đổi 1→1 thuần.

### 15.2. collectingAndThen chạy khi thu thập xong

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> list = Stream.of(1, 2, 3)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
        ));
~~~

Đây là **terminal operation**. `List::copyOf` được áp dụng lên **toàn kết quả thu thập**; nó không nhận từng phần tử như một Gatherer trung gian.

### 15.3. Gatherer.andThen vẫn cho pipeline tiếp tục

~~~java
long howMany = Stream.of(1, 2, 3, 4)
        .gather(
                Gatherers.<Integer>windowFixed(2)
                        .andThen(
                                Gatherer.<List<Integer>, Integer>of(
                                        (ignored, window, downstream) ->
                                                downstream.push(window.size())
                                )
                        )
        )
        .filter(size -> size >= 2)
        .count();

System.out.println(howMany); // 2
~~~

Sau `gather`, Stream vẫn có thể tiếp tục qua `filter`, `map`, `sorted`, `collect` hoặc terminal khác. `andThen` không kết thúc Stream.

---

## 16. Kết hợp Gatherer và Stream operations thông thường

Không nhất thiết mọi giai đoạn đều phải là Gatherer.

~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> result = Stream.of(-1, 1, 2, 3, 4, 5)
        .filter(n -> n > 0)
        .gather(Gatherers.windowFixed(2))
        .map(window -> window.stream()
                             .mapToInt(Integer::intValue)
                             .sum())
        .filter(sum -> sum > 3)
        .toList();

System.out.println(result); // [7, 5]
~~~

Sau `filter(n > 0)`, input là `[1,2,3,4,5]`. Các cửa sổ: `[1,2]`, `[3,4]`, `[5]`. Tổng: `3,7,5`. Sau điều kiện `sum > 3`: `[7,5]`.

Nếu một bước sau nhiều lần dùng lại ở các pipeline khác nhau, ta có thể đưa nó vào Gatherer riêng rồi `andThen`. Nếu chỉ cần một phép `map` đơn giản tại đúng một nơi, pipeline hỗn hợp thường dễ đọc hơn.

### 16.1. Chỉ đưa filter lên trước window khi không đổi nghiệp vụ

~~~text
Input: [A, X, B, C]
X: bản ghi không hợp lệ
windowFixed(2) trước filter: [[A,X], [B,C]]
filter trước windowFixed(2): [[A,B], [C]]
~~~

Hai quy trình chia nhóm khác nhau. Khi dùng `andThen` để đóng gói một chain, hãy ghi rõ **thời điểm lọc** so với **thời điểm gom cửa sổ**.

### 16.2. Không lạm dụng custom Gatherer

Một phép biến đổi `x -> x * 2` thường nên viết `map(x -> x * 2)`. Một phép loại trùng theo `equals` thường dùng `distinct`. Gatherer có ích khi cần state hoặc cơ chế phát phần tử mà operations có sẵn không diễn đạt rõ, hoặc khi muốn đóng gói **một tổ hợp Gatherer nhiều stage**.

---

## 17. Tái sử dụng chain và khái niệm cấu hình

Một cách tổ chức code thực tế:

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;

static Gatherer<Integer, ?, Integer>
windowAveragesRoundedDown(int size) {

    Gatherer<Integer, ?, List<Integer>> windows =
            Gatherers.windowFixed(size);

    Gatherer<List<Integer>, ?, Integer> averageFloor =
            Gatherer.<List<Integer>, Integer>of(
                    (ignored, xs, downstream) -> {
                        long sum = xs.stream()
                                .mapToLong(Integer::longValue)
                                .sum();

                        int average = Math.toIntExact(
                                Math.floorDiv(sum, xs.size())
                        );

                        return downstream.push(average);
                    }
            );

    return windows.andThen(averageFloor);
}
~~~

Tạo chain từ tham số cấu hình `size` giúp bài toán được đặt tên và có thể kiểm thử riêng. `Gatherers.windowFixed` sẽ từ chối `size < 1`; ta không nên âm thầm đổi thành size=1 nếu nghiệp vụ không yêu cầu.

**Giới hạn số học:** Ví dụ dùng `long` cho sum và `Math.toIntExact` để phát hiện kết quả vượt `int`. Với tổng cực lớn có thể vượt `long`, cần nâng sang `BigInteger` nếu nghiệp vụ yêu cầu tổng tuyệt đối chính xác.

### 17.1. Không dùng biến đếm mutable ở cấp ứng dụng

~~~java
// Không nên:
// AtomicInteger running = new AtomicInteger();
// Gatherer<Integer, ?, Integer> g = Gatherer.of(
//       (unused, n, downstream) ->
//               downstream.push(running.addAndGet(n))
// );
~~~

Dùng `Gatherers.scan(() -> 0, Integer::sum)` để mỗi lần đánh giá có state phù hợp theo hợp đồng. Tái sử dụng một **định nghĩa Gatherer an toàn** khác với chia sẻ một **container mutable mang dữ liệu của các lần chạy trước**.

---

## 18. Sự khác biệt giữa windowFixed và windowSliding khi ghép

| Điều kiện | `windowFixed(3)` | `windowSliding(3)` |
|---|---|---|
| Đầu vào `[1,2,3,4,5]` | `[[1,2,3],[4,5]]` | `[[1,2,3],[2,3,4],[3,4,5]]` |
| Số phần tử mỗi cửa sổ | Cuối có thể ít hơn 3 | Thường 3 khi nguồn đủ dài; nguồn ngắn hơn 3 có thể phát một cửa sổ ngắn |
| Chồng lấp | Không | Có |
| Dùng phổ biến | Chia batch để gửi/gom | Trung bình trượt, so sánh lân cận |
| Khi ghép với `scan` | Scan chạy theo **mỗi batch** | Scan chạy theo **mỗi cửa sổ trượt** |

### 18.1. Phản ví dụ: tưởng hai loại cửa sổ cho cùng số output

~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> fixed = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowFixed(3))
        .toList();

List<List<Integer>> sliding = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(fixed);   // [[1, 2, 3], [4, 5]]
System.out.println(sliding); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
~~~

Một Gatherer theo sau sẽ thấy **2 phần tử List** trong trường hợp fixed và **3 phần tử List** trong trường hợp sliding. Hãy chọn đúng ý nghĩa cửa sổ trước khi nối tiếp với `fold` hoặc `scan`.

---

## 19. Xử lý null, nguồn rỗng và dữ liệu có vấn đề

### 19.1. Nguồn rỗng

| Chain | Kết quả khi không có input và xử lý hoàn tất bình thường |
|---|---|
| `windowFixed(3)` | Không phát cửa sổ |
| `windowSliding(3)` | Không phát cửa sổ |
| `scan(() -> 0, sum)` | Không phát tổng dồn |
| `fold(() -> 0, sum)` | Phát giá trị khởi tạo `0` |
| `windowFixed(3).andThen(fold(count))` | Có thể phát `0` vì downstream fold không nhận cửa sổ nào |

Đây là lý do bộ test không được áp một quy tắc “Stream rỗng luôn trả List rỗng” cho **mọi Gatherer**. Một Gatherer với `finisher` có thể phát giá trị **dù không có input**.

### 19.2. Null

`Stream.of((String) null)` có thể tạo một phần tử null. Nhưng `String::trim` trên null ném `NullPointerException`.

~~~java
import java.util.Objects;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<String>> safe = Stream.of(" An ", null, " Binh ")
        .filter(Objects::nonNull)
        .map(String::trim)
        .gather(Gatherers.windowFixed(2))
        .toList();

System.out.println(safe); // [[An, Binh]]
~~~

Lọc null **trước** khi vào Gatherer nếu Gatherer chưa định nghĩa cách xử lý null. Điều này cũng thay đổi kích thước và ranh giới cửa sổ so với việc giữ một vị trí null, nên cần thống nhất chính sách.

### 19.3. Ngoại lệ trong mapper và finisher

Khi hàm mapper/gatherer phát sinh exception, pipeline có thể kết thúc bằng exception; các side effect đã thực hiện ở những phần trước không có cơ chế rollback tự động.

Với `mapConcurrent`, khi công việc mapper thất bại, ngoại lệ có thể được chuyển tiếp dưới dạng `RuntimeException` và các task còn lại có thể bị hủy theo best effort. Không giả định mọi task đã khởi chạy đều hoàn tất hoặc các thao tác ngoài hệ thống được hoàn tác tự động.

---

## 20. Hiệu năng: composition có thể tối ưu nhưng không có bảo đảm

Một ví dụ:

~~~java
Stream<Integer> source = ...;

List<Integer> result = source
        .gather(g1.andThen(g2))
        .toList();
~~~

Không thể khẳng định chỉ từ cú pháp rằng cách viết này luôn:

- Duyệt nguồn ít lần hơn cách `gather(g1).gather(g2)`.
- Tạo ít object hơn trong mọi JDK.
- Xử lý song song tốt hơn.
- Không dùng bộ nhớ tạm.
- Hủy mọi công việc ngay lập tức khi downstream dừng.

`andThen` cung cấp **hợp đồng ghép**, còn runtime có thể chọn cách triển khai bảo toàn ngữ nghĩa, tùy phiên bản JDK, đặc tính Gatherer và pipeline.

### 20.1. Các nguồn chi phí quan trọng

| Chi phí | Khi nào đáng kể? |
|---|---|
| Giữ state | `scan`, `fold`, Gatherer tùy chỉnh |
| Cấp phát cửa sổ | `windowFixed`/`windowSliding`, nhất là cửa sổ lớn |
| Tính lại trên cửa sổ trượt | Khi mỗi cửa sổ được xử lý riêng bằng một phép reduce |
| Gộp state song song | Gatherer có combiner; cần kiểm tra hợp đồng |
| Bảo toàn encounter order | Khi phép biến đổi có trạng thái phụ thuộc thứ tự |
| Đồng thời I/O | `mapConcurrent` có nhiều virtual threads nhưng tài nguyên ngoài vẫn giới hạn |
| Kết quả cuối | `toList` có thể giữ toàn bộ output vào bộ nhớ |

### 20.2. Đo hiệu năng đúng

Nếu hiệu năng là yêu cầu, nên dùng JMH hoặc cách đo có warm-up và kiểm soát rõ:

- Cùng nguồn dữ liệu và cùng hợp đồng kết quả.
- Các kích thước dữ liệu và window size khác nhau.
- So pipeline truyền thống, `gather` nối tiếp và `andThen`.
- Đo throughput, allocation, GC, latency và peak memory.
- Tách chi phí I/O thật khỏi phép biến đổi CPU nếu muốn biết nút nghẽn.
- Không so hai pipeline **khác ngữ nghĩa** như `windowFixed` và `windowSliding` rồi kết luận nhanh/chậm thuần túy.

---

## 21. Chương trình Java 24 hoàn chỉnh: kiểm thử andThen

Đây là ví dụ độc lập, có thể đặt trong tệp `GathererAndThenDemo.java` và biên dịch bằng JDK 24 trở lên.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererAndThenDemo {

    static Gatherer<Integer, ?, Integer> pairSums() {
        Gatherer<Integer, ?, List<Integer>> pairs =
                Gatherers.windowFixed(2);

        Gatherer<List<Integer>, ?, Integer> sumPair =
                Gatherer.<List<Integer>, Integer>of(
                        (ignored, pair, downstream) ->
                                downstream.push(
                                        pair.stream()
                                            .mapToInt(Integer::intValue)
                                            .sum()
                                )
                );

        return pairs.andThen(sumPair);
    }

    static Gatherer<Integer, ?, Integer> runningPairSums() {
        Gatherer<Integer, ?, Integer> pairSums = pairSums();
        Gatherer<Integer, ?, Integer> running =
                Gatherers.scan(() -> 0, Integer::sum);

        return pairSums.andThen(running);
    }

    static void checkEquals(
            String name, Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual
            );
        }
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(1, 2, 3, 4, 5);

        List<Integer> composed = input.stream()
                .gather(runningPairSums())
                .toList();

        List<Integer> separate = input.stream()
                .gather(Gatherers.windowFixed(2))
                .map(pair -> pair.stream()
                                 .mapToInt(Integer::intValue)
                                 .sum())
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        checkEquals("composed", List.of(3, 10, 15), composed);
        checkEquals("equivalence", separate, composed);

        // Nguồn rỗng: windowFixed không tạo cửa sổ.
        List<Integer> empty = Stream.<Integer>empty()
                .gather(runningPairSums())
                .toList();
        checkEquals("empty", List.of(), empty);

        // Cửa sổ cuối thiếu phần tử.
        List<Integer> one = Stream.of(7)
                .gather(runningPairSums())
                .toList();
        checkEquals("one", List.of(7), one);

        // Hai cách gọi gather có cùng ngữ nghĩa.
        Gatherer<Integer, ?, Integer> pairs = pairSums();
        Gatherer<Integer, ?, Integer> running =
                Gatherers.scan(() -> 0, Integer::sum);

        List<Integer> joined = input.stream()
                .gather(pairs.andThen(running))
                .toList();

        List<Integer> chained = input.stream()
                .gather(pairs)
                .gather(running)
                .toList();

        checkEquals("andThen vs gather-gather", chained, joined);

        // Sử dụng nhiều lần nhưng luôn tạo Stream mới.
        List<Integer> again = input.stream()
                .gather(runningPairSums())
                .toList();
        checkEquals("reusable definition", composed, again);

        System.out.println("AND_THEN_OK");
        System.out.println(composed);
    }
}
~~~

Kết quả kỳ vọng:

~~~text
AND_THEN_OK
[3, 10, 15]
~~~

### 21.1. Chạy với JDK 24+

~~~text
javac GathererAndThenDemo.java
java GathererAndThenDemo
~~~

Nếu `javac` báo không tìm thấy `Gatherer` hoặc `Stream.gather`, hãy kiểm tra phiên bản thực tế của JDK đang dùng:

~~~text
java -version
javac -version
~~~

JDK 22/23 có các bản **preview** của Stream Gatherers; bài này nhắm vào **API final trên JDK 24+**, không khuyến nghị sao chép nguyên ví dụ sang những JDK cũ mà không kiểm tra tương thích.

---

## 22. Kiểm thử chain theo oracle và bất biến

Các ca nên có:

| Ca | Mong đợi |
|---|---|
| Nguồn rỗng | Tùy chain: không cửa sổ, nhưng `fold` có thể phát initial |
| Một phần tử | `windowFixed` phát cửa sổ ngắn; downstream xử lý được |
| Kích thước chia hết cho n | Không tạo cửa sổ rỗng thừa |
| Kích thước không chia hết cho n | Cửa sổ cuối có phần tử còn lại |
| Chạy `gather(A).gather(B)` | Kết quả bằng `gather(A.andThen(B))` theo hợp đồng |
| Đảo `A/B` khi cùng kiểu | Không tự suy ra tương đương; có thể khác |
| Type A output không khớp B input | Lỗi biên dịch; không ép kiểu giả |
| Downstream terminal `limit` | Tôn trọng ngừng nhận thêm; không dựa số lần gọi lambda |
| Gatherer stateful | Không rò state giữa hai lần đánh giá |
| Gatherer có finisher | Output phát cuối vẫn đi qua bước sau |
| Parallel | Đúng kết quả theo hợp đồng; không đòi dùng nhiều thread |
| Null/ngoại lệ | Xử lý đầu vào và cleanup theo chính sách |
| Window size không hợp lệ | `windowFixed`/`windowSliding` từ chối size < 1 |
| Kết quả cần số học chính xác | Kiểm tra overflow và rounding |
| I/O | Nguồn tệp được đóng, không chỉ trông chờ finisher |

### 22.1. Xây một oracle từ List và vòng lặp

Ví dụ kiểm chứng `windowFixed(2)` rồi cộng mỗi cặp, rồi tổng dồn:

~~~java
import java.util.ArrayList;
import java.util.List;

static List<Integer> oracleRunningPairs(List<Integer> input) {
    List<Integer> result = new ArrayList<>();
    int total = 0;

    for (int i = 0; i < input.size(); i += 2) {
        int pairSum = input.get(i);

        if (i + 1 < input.size()) {
            pairSum += input.get(i + 1);
        }

        total += pairSum;
        result.add(total);
    }

    return result;
}
~~~

Phương thức này đặt trong lớp Java và phù hợp với dữ liệu mẫu không tràn `int`. Oracle **không gọi lại chính Gatherer** cần kiểm tra, nên có thể phát hiện một lỗi cấu trúc chain.

### 22.2. Kiểm tra nhiều kích thước đầu vào

~~~java
for (int size = 0; size <= 20; size++) {
    List<Integer> input = new java.util.ArrayList<>();

    for (int n = 1; n <= size; n++) {
        input.add(n);
    }

    List<Integer> expected = oracleRunningPairs(input);

    List<Integer> actual = input.stream()
            .gather(runningPairSums())
            .toList();

    if (!expected.equals(actual)) {
        throw new AssertionError(
                "size=" + size
                + ", expected=" + expected
                + ", actual=" + actual
        );
    }
}
~~~

Kiểm tra đủ size 0..20 giúp bao phủ cả cửa sổ cuối đủ/thiếu phần tử; tuy nhiên chưa chứng minh mọi dữ liệu và mọi cách chia. Bổ sung giá trị âm, số lớn, các ca null và kiểu xử lý song song theo yêu cầu.

### 22.3. Không kiểm thử bằng số lần gọi side effect

~~~java
// Không nên lấy số lần println trong integrator làm oracle,
// vì short-circuit/parallel/lazy optimizations có thể ảnh hưởng
// lịch gọi và thứ tự quan sát được.
//
// Hãy so KẾT QUẢ DỮ LIỆU và các bất biến thuộc hợp đồng.
~~~

---

## 23. Những lỗi thường gặp khi ghép Gatherer

| Lỗi | Hậu quả | Sửa |
|---|---|---|
| Nhầm `andThen` là concat hai luồng | Sai mô hình xử lý | Hiểu đầu ra A trở thành đầu vào B |
| Đảo thứ tự `A.andThen(B)` | Có thể sai kiểu hoặc sai kết quả | Vẽ sơ đồ `T → R → RR` trước |
| Quên terminal operation | Pipeline không tiêu thụ nguồn | Gọi `toList`, `collect`, `findFirst`... khi cần |
| Dùng lại Stream đã tiêu thụ | Lỗi vòng đời Stream | Tạo Stream mới |
| Giả định window cuối luôn đủ n | Lỗi indexing/thiếu dữ liệu | Xử lý list ngắn |
| Nghĩ fold phát từng giá trị | Sai số lượng output | `fold` phát một kết quả khi kết thúc; `scan` phát mỗi bước |
| Nghĩ Stream rỗng luôn cho output rỗng | Sai với `fold(initial)` | Kiểm tra finisher của từng stage |
| Bỏ qua `downstream.push` trả false | Không tôn trọng yêu cầu dừng | Trả false khi downstream từ chối |
| Lưu `Downstream` hoặc state để dùng ngoài lời gọi | Vi phạm hợp đồng Gatherer | Chỉ dùng trong thời gian invocation |
| Cho state mutable chung vào lambda | Rò state/race giữa nhiều lần xử lý | Tạo state qua initializer |
| Tưởng `andThen` tự tạo combiner song song | Có thể sai kết quả hoặc mất hiệu năng | Thiết kế combiner đúng hoặc giữ sequential |
| Gắn `CONCURRENT` theo suy đoán | Nhầm với Collector, không đúng hợp đồng | Phân biệt Gatherer và Collector |
| Mặc định `windowSliding` giống `windowFixed` | Số cửa sổ và chi phí khác nhau | Chọn đúng loại cửa sổ |
| Thay `takeUntilInclusive` bằng `filter` | Mất ngữ nghĩa dừng ở mốc đầu | Dùng Gatherer có short-circuit |
| Không kiểm tra phiên bản JDK | Không biên dịch trên Java 17/21 | Dùng JDK 24+ cho API final |
| Xem hai pipeline khác nghĩa như cùng benchmark | Tối ưu sai mục tiêu | So cùng oracle/ngữ nghĩa trước |

---

## 24. Khi nào dùng andThen, khi nào dùng gather liên tiếp?

Dùng `andThen` khi:

- Có **hai hoặc nhiều Gatherer** muốn đặt tên như một phép xử lý tái sử dụng.
- Muốn công bố một API nhỏ kiểu `Gatherer<Input, ?, Output>` thay vì yêu cầu mã gọi tự lắp các stage.
- Muốn cô lập việc cấu hình window, scan, fold hoặc custom gatherer trong một helper.
- Cần kiểm thử một tổ hợp như **một đơn vị nghiệp vụ**.
- Muốn mô tả rõ các chuyển kiểu trung gian.

Dùng `gather(A).gather(B)` khi:

- Chỉ xây một pipeline ở một vị trí và các bước riêng rẽ dễ đọc hơn.
- Muốn debug hoặc thêm các thao tác `filter`/`map` giữa A và B.
- Không cần đóng gói tổ hợp thành đối tượng Gatherer tái sử dụng.

Dùng `map`/`filter`/`flatMap` khi:

- Thao tác là một biến đổi đơn giản đã được Stream hỗ trợ sẵn.
- Không cần state, finisher hay cơ chế short-circuit tùy chỉnh.

Dùng `collect` khi:

- Muốn **thu kết quả cuối** thành List/Map/Set, thống kê hoặc DTO.
- Không cần tiếp tục truyền các phần tử qua một Stream sau phép tổng hợp.

### 24.1. Checklist thiết kế chain

1. Đặt tên **đầu vào, đầu ra của từng bước**, ví dụ `Integer → List<Integer> → Long`.
2. Xác minh kiểu generic của `andThen` biên dịch hợp lệ.
3. Xác định mỗi bước phát **0, 1 hay nhiều** phần tử trên mỗi input.
4. Xác định có bước nào **chỉ phát trong finisher** không.
5. Xác định **nguồn rỗng** cho output nào.
6. Xác định encounter order, trạng thái và điều kiện dừng sớm.
7. Kiểm soát state mutable: không đưa trạng thái riêng ra ngoài invocation.
8. Nếu dùng parallel, bảo đảm combiner hợp lệ hoặc chấp nhận stage tuần tự.
9. Không để hàm phát ra kiểu số vượt miền tính toán mà không có chính sách.
10. So `gather(A.andThen(B))` và `gather(A).gather(B)` trên cùng dữ liệu.
11. Dùng oracle độc lập để phát hiện **cả hai cách cùng sai nghiệp vụ**.
12. Benchmark sau khi đã xác nhận kết quả và ràng buộc tài nguyên.

---

## 25. Bài tập nền tảng (có đáp án)

### Bài 1. andThen nhận loại đối tượng nào?

**Đề:** `Gatherer.andThen(...)` nhận một `Collector`, một `Function` hay một `Gatherer`?

**Đáp án:** Nhận một **`Gatherer`** khác. Chữ ký có dạng `Gatherer<T,?,RR> andThen(Gatherer<? super R,?,? extends RR> that)`. Đầu ra bước trước phải dùng được làm đầu vào bước sau.

### Bài 2. Hai cách gọi tương đương

**Đề:** Hãy viết cách tương đương với `stream.gather(a.andThen(b))`.

**Đáp án:** `stream.gather(a).gather(b)`. Sự tương đương xét **ngữ nghĩa đầu ra** theo hợp đồng, không phải số thread, số lần gọi log hoặc chi tiết tối ưu.

### Bài 3. Kiểu dữ liệu trung gian

**Đề:** `Gatherers.windowFixed(3)` nhận số `Integer` và phát gì? Một Gatherer tiếp theo nên nhận kiểu gì để tính tổng cửa sổ?

**Đáp án:** Nó phát `List<Integer>`. Gatherer sau có đầu vào `List<Integer>`, có thể phát `Integer` là tổng của list.

### Bài 4. Cửa sổ cuối

**Đề:** `Stream.of(1,2,3,4,5).gather(Gatherers.windowFixed(2)).toList()` trả gì?

**Đáp án:** `[[1,2],[3,4],[5]]`. Cửa sổ cuối có thể ngắn hơn kích thước yêu cầu.

### Bài 5. Scan sau window sum

**Đề:** Input `[1,2,3,4,5]`, `windowFixed(2)` rồi tính tổng từng cửa sổ, sau đó `scan(() -> 0, Integer::sum)`. Kết quả?

**Đáp án:** Cửa sổ `[[1,2],[3,4],[5]]`, tổng cửa sổ `[3,7,5]`, scan phát `[3,10,15]`.

### Bài 6. fold khác scan

**Đề:** `scan` và `fold` cùng có initial 0, cùng cộng các số `[1,2,3]`. Kết quả khác nhau thế nào?

**Đáp án:** `scan` phát `[1,3,6]` sau từng input; `fold` phát một giá trị cuối `[6]` khi upstream kết thúc.

### Bài 7. Nguồn rỗng

**Đề:** `Stream.<Integer>empty().gather(Gatherers.fold(() -> 0, Integer::sum)).toList()` trả gì?

**Đáp án:** `[0]` vì `fold` phát initial tại finisher ngay cả khi không có phần tử đầu vào. `windowFixed(3)` riêng lẻ trên nguồn rỗng trả `[]`.

### Bài 8. Đảo thứ tự

**Đề:** Với `[1,2,3,4]`, `scan(sum).andThen(fold(sum))` và `fold(sum).andThen(scan(sum))` có bằng nhau không?

**Đáp án:** Không. Cách đầu phát `[20]` vì tổng các prefix sums 1+3+6+10. Cách sau phát `[10]` vì fold tính tổng 10 rồi scan nhận đúng một số 10.

---

## 26. Bài tập trung cấp (có đáp án)

### Bài 9. Viết Gatherer biến mỗi cửa sổ thành tổng

**Đề:** Viết `Gatherer<List<Integer>, ?, Integer>` dùng `Gatherer.of` để chuyển một list số thành một số tổng.

**Đáp án:**

~~~java
Gatherer<List<Integer>, ?, Integer> sumWindow =
        Gatherer.<List<Integer>, Integer>of(
                (ignored, xs, downstream) ->
                        downstream.push(
                                xs.stream().mapToInt(Integer::intValue).sum()
                        )
        );
~~~

Đây là Gatherer stateless, biến một input List thành một output Integer. Sau đó có thể nối `Gatherers.<Integer>windowFixed(2).andThen(sumWindow)`.

### Bài 10. Chuỗi trống ảnh hưởng đến cửa sổ

**Đề:** Nguồn `["A", "", "B", "C"]`. Nếu loại chuỗi rỗng trước khi `windowFixed(2)` thì nhận gì? Nếu gom trước rồi mới loại rỗng trong từng cửa sổ?

**Đáp án:** Lọc trước cho `[["A","B"],["C"]]`. Gom trước tạo `[["A",""],["B","C"]]`, rồi loại rỗng theo từng cửa sổ cho `[["A"],["B","C"]]`. Thứ tự xử lý thay đổi ranh giới nhóm, không hoán đổi tùy ý.

### Bài 11. Dừng bao gồm phần tử mốc

**Đề:** Viết Gatherer nhận Integer, phát các số từ đầu và dừng ngay sau số đầu tiên `>= 5`. Input `[1,3,6,2,8]` cho kết quả nào?

**Đáp án:** `[1,3,6]`. Integrator cần phát `6` rồi trả `false`; dùng `ofSequential` khi xử lý ranh giới tiền tố phụ thuộc encounter order. `filter(n -> n < 5)` sẽ trả `[1,3,2]`, khác yêu cầu.

### Bài 12. Tại sao downstream.push trả boolean?

**Đề:** Nếu downstream đã nhận đủ phần tử, một Gatherer còn phát thêm và luôn trả true có đúng cách không?

**Đáp án:** Không. `push` trả false khi downstream không muốn nhận thêm. Integrator cần tôn trọng tín hiệu này và tránh phát các phần tử tiếp theo. `isRejecting()` chỉ giúp kiểm tra thêm theo best effort.

### Bài 13. andThen có tự tối ưu parallel không?

**Đề:** Có `A` dùng `ofSequential` và `B` có combiner hợp lệ. `A.andThen(B)` có tự bảo đảm cả hai stage chạy song song không?

**Đáp án:** Không. Mỗi Gatherer có hợp đồng xử lý riêng; một stage tuần tự có thể giới hạn toàn chain. Muốn song song hóa phải có cơ chế chia/gộp đúng, không thể chỉ thêm `parallel()` hay `andThen`.

### Bài 14. Finisher và đầu ra sau cùng

**Đề:** Gatherer `A` không phát gì trong integrator nhưng finisher phát String `"count=4"`. Gatherer `B` biến String thành độ dài. `A.andThen(B)` trả gì?

**Đáp án:** Phát một phần tử `[7]`, vì `"count=4"` dài 7 ký tự. Đầu ra phát trong finisher A vẫn đi qua Gatherer B.

### Bài 15. Sliding và fixed

**Đề:** Với `[1,2,3,4,5]` và window size 3, mỗi loại cửa sổ phát bao nhiêu list?

**Đáp án:** `windowFixed(3)` phát hai list `[[1,2,3],[4,5]]`; `windowSliding(3)` phát ba list `[[1,2,3],[2,3,4],[3,4,5]]`.

### Bài 16. Nguồn Java 21

**Đề:** Dự án chạy Java 21 và cần viết `stream.gather(g1.andThen(g2))`. Có thể copy trực tiếp code Java 24 không?

**Đáp án:** Không. Stream Gatherers chỉ được chuẩn hóa ở Java 24, đã là preview ở 22/23; Java 21 không có API này. Nếu không thể nâng JDK, cần diễn đạt bằng `map`/`flatMap`/`collect`/`Spliterator` hoặc vòng lặp, tùy đúng nghiệp vụ.

### Bài 17. Kiểm tra tương đương

**Đề:** Chỉ so kết quả của `gather(a.andThen(b))` và `gather(a).gather(b)` có chứng minh đúng yêu cầu nghiệp vụ không?

**Đáp án:** Chưa đủ. Hai cách có thể cùng áp dụng sai comparator, sai kích thước cửa sổ hoặc sai công thức. Cần thêm một oracle độc lập và các trường hợp biên.

### Bài 18. Kiểu dữ liệu không khớp

**Đề:** Gatherer A phát `List<Integer>`, Gatherer B nhận `String`. Có thể dùng `A.andThen(B)` không?

**Đáp án:** Không thể nối trực tiếp với kiểu dữ liệu không tương thích. Cần một Gatherer `List<Integer> → String` trung gian, hoặc đổi contract đầu ra của A/đầu vào của B.

---

## 27. Checklist cuối bài

Một chain `A.andThen(B)` được thiết kế tốt khi:

- **Kiểu đúng:** `output(A)` có thể đưa vào `input(B)`.
- **Thứ tự đúng:** Đã xác định rõ A chạy trước B, không đảo dựa vào cảm giác.
- **Số phần tử đúng:** Đã tính đến A/B có thể phát 0, 1 hoặc nhiều phần tử.
- **Nguồn rỗng đúng:** Đã hiểu hành vi của từng finisher.
- **Cửa sổ cuối đúng:** Không giả định mọi batch đủ kích thước.
- **Short-circuit đúng:** Tôn trọng tín hiệu từ `downstream.push`.
- **Trạng thái đúng:** Không giữ state/Downstream bên ngoài lời gọi hợp lệ hoặc dùng object mutable chung.
- **Song song đúng:** Không tự gắn combiner sai; không hứa tăng tốc khi có stage tuần tự.
- **Tài nguyên đúng:** Đóng nguồn I/O ở tầng phù hợp, không dựa vào finisher thay cleanup.
- **Kết quả đúng:** So với oracle và các bất biến, không chỉ so hai cách viết của cùng chain.
- **Phiên bản đúng:** Biên dịch và chạy trên JDK 24+ khi dùng API Gatherer chuẩn.
- **Hiệu năng được đo:** Không khẳng định `andThen` tự fusion/tự tiết kiệm bộ nhớ.

### Tài liệu tra cứu

- Javadoc chính thức Java 24 — [Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- Javadoc chính thức Java 24 — [Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- Đặc tả chuẩn hóa — [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)

---

## Tổng kết

`Gatherer.andThen(...)` là cơ chế **ghép các phép biến đổi Stream trung gian**: đầu ra `R` của Gatherer thứ nhất trở thành đầu vào của Gatherer thứ hai, tạo một Gatherer mới có kiểu `T → RR`. Theo hợp đồng, `stream.gather(a.andThen(b))` tương đương về ngữ nghĩa với `stream.gather(a).gather(b)`.

Trong thực hành, `andThen` đặc biệt hữu ích để đóng gói các quy trình như **chia cửa sổ → tính tổng từng cửa sổ → tính tổng tích lũy**, hoặc **lọc/chuẩn hóa → gom nhóm**, hoặc **fold → định dạng kết quả**. Phải hiểu các trường hợp **finisher phát phần tử cuối**, **short-circuit**, **trạng thái riêng từng lần chạy**, **kiểu trung gian** và **giới hạn xử lý song song** trước khi biến một chain thành thư viện tái sử dụng.

**Ghi nhớ:** `andThen` là phép **nối theo thứ tự**, không phải phép cộng hai kết quả hay phép bảo đảm tăng tốc. Để viết Java Stream API đúng, hãy xác định rõ đầu vào/đầu ra của từng Gatherer, kiểm tra bằng oracle độc lập, và chạy trên JDK hỗ trợ API final (Java 24+).

