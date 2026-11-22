# Phân biệt filter với takeWhile và dropWhile

Trong Java Stream API, `filter`, `takeWhile` và `dropWhile` đều nhận một điều kiện `Predicate`, nhưng **không trả lời cùng một câu hỏi**. `filter` chọn những phần tử thỏa điều kiện trong **toàn bộ nguồn**; `takeWhile` lấy **đoạn đầu liên tiếp** còn thỏa điều kiện; `dropWhile` **bỏ đoạn đầu liên tiếp** còn thỏa điều kiện rồi giữ phần còn lại. Sự khác biệt đặc biệt quan trọng khi dữ liệu có thứ tự, khi gặp một giá trị vượt ngưỡng ở giữa nguồn và khi xử lý Stream song song.

Bài thuộc chương **Thứ tự, loại trùng và cắt lát** của mô-đun **JAVA_STREAM_API**. Qua các ví dụ Java 17+, người học sẽ hiểu *encounter order*, điều kiện để cắt theo mốc, tính lazy và dừng sớm, rủi ro với Stream không có thứ tự, cách phối hợp `sorted`, `limit`, `skip`, cũng như giới hạn về trạng thái, tài nguyên và hiệu năng trong pipeline `filter → map → collect`.

## 1. Một ví dụ, ba kết quả khác nhau

Xét dãy có thứ tự:

```text
[1, 3, 7, 2, 9]
```

Điều kiện là `n < 5`. Số `2` thỏa điều kiện nhưng **nằm sau** phần tử `7` không thỏa.

```java
import java.util.List;

public class WhileVsFilterBasics {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 3, 7, 2, 9);

        System.out.println(values.stream()
            .filter(n -> n < 5)
            .toList()); // [1, 3, 2]

        System.out.println(values.stream()
            .takeWhile(n -> n < 5)
            .toList()); // [1, 3]

        System.out.println(values.stream()
            .dropWhile(n -> n < 5)
            .toList()); // [7, 2, 9]
    }
}
```

Cùng một predicate, ba thao tác tạo ra ba tập kết quả:

| Thao tác | Quy tắc trên Stream có thứ tự | Kết quả ví dụ |
| --- | --- | --- |
| `filter(n -> n < 5)` | Giữ **mọi** phần tử thỏa điều kiện | `[1, 3, 2]` |
| `takeWhile(n -> n < 5)` | Giữ **tiền tố liên tiếp dài nhất** thỏa điều kiện; dừng tại phần tử đầu tiên không thỏa | `[1, 3]` |
| `dropWhile(n -> n < 5)` | Loại **tiền tố liên tiếp dài nhất** thỏa điều kiện; giữ phần tử đầu tiên không thỏa **và tất cả phần tử sau đó** | `[7, 2, 9]` |

Minh họa cách cắt:

```text
Dữ liệu:       [ 1, 3 | 7, 2, 9 ]
                        ^
                    7 không thỏa n < 5
filter:        [ 1, 3,    2    ]   (chọn mọi phần tử thỏa)
takeWhile:     [ 1, 3 ]            (lấy đoạn đầu)
dropWhile:             [ 7, 2, 9 ] (bỏ đoạn đầu)
```

**Ghi nhớ ngay:** `dropWhile` **không phải** `filter(predicate.negate())`. Trong kết quả `dropWhile` ở trên vẫn có số `2` thỏa predicate, bởi nó xuất hiện sau điểm cắt.

## 2. Ý nghĩa chính xác của “tiền tố” và encounter order

*Tiền tố* (*prefix*) là đoạn phần tử liên tiếp bắt đầu ở **đầu thứ tự gặp** (*encounter order*) của nguồn. Một Stream có thứ tự cho phép xác định đâu là phần tử đầu tiên, thứ hai, thứ ba, v.v.

Ví dụ với `List`:

```java
List<String> states = List.of(
    "PENDING", "PENDING", "DONE", "PENDING"
);
```

- `takeWhile("PENDING"::equals)` cho `[PENDING, PENDING]`.
- `dropWhile("PENDING"::equals)` cho `[DONE, PENDING]`.
- `filter("PENDING"::equals)` cho `[PENDING, PENDING, PENDING]`.

Các nguồn thường có encounter order như `List.stream()`, `Arrays.stream(...)` và `IntStream.range(...)`. Ngược lại, nguồn từ một `HashSet` thông thường **không có encounter order được bảo đảm**. Sự khác biệt này ảnh hưởng trực tiếp đến ý nghĩa của `takeWhile` và `dropWhile`.

### 2.1. Ba cách mô tả theo chỉ số

Giả sử nguồn có thứ tự `x0, x1, ..., x(n-1)` và điều kiện `p(x)`.

- `filter(p)` trả về tất cả `xi` mà `p(xi)` đúng, giữ thứ tự tương đối của các phần tử còn lại.
- `takeWhile(p)` tìm vị trí `k` đầu tiên mà `p(xk)` sai, rồi trả `x0, ..., x(k-1)`. Nếu không có vị trí sai, trả toàn bộ nguồn.
- `dropWhile(p)` tìm cùng vị trí `k` và trả `xk, ..., x(n-1)`. Nếu không có vị trí sai, trả Stream rỗng.

Điểm cắt `k` có thể bằng 0 (phần tử đầu tiên đã sai) hoặc bằng `n` (mọi phần tử đều đúng). Với Stream hữu hạn và có thứ tự, hai đoạn tạo bởi `takeWhile(p)` và `dropWhile(p)` là hai phần **không chồng lấn** và ghép lại theo đúng thứ tự sẽ khôi phục nguồn ban đầu.

**Lưu ý:** Hai biểu thức ở trên phải chạy từ **hai Stream mới** vì Stream đã được tiêu thụ bởi terminal operation không dùng lại được. Để chia nguồn thành hai nhánh thật sự chỉ với một lần đọc, cần thiết kế thuật toán khác, chẳng hạn lưu dữ liệu hoặc một cơ chế chia dòng phù hợp.

## 3. `filter`: lọc mọi vị trí trong nguồn

`filter` là thao tác trung gian không trạng thái (*stateless intermediate operation*). Nó giữ phần tử nếu `Predicate.test(element)` trả về `true`, bất kể các phần tử trước đó có thỏa điều kiện hay không.

```java
import java.util.List;

List<Integer> scores = List.of(40, 90, 20, 80, 50);

List<Integer> passed = scores.stream()
    .filter(score -> score >= 50)
    .toList();

System.out.println(passed); // [90, 80, 50]
```

Dữ liệu điểm không cần được sắp xếp. Các điểm qua ngưỡng có thể nằm ở bất kỳ vị trí nào.

### Khi nào `filter` là lựa chọn đúng?

- Tìm **tất cả** đơn hàng đã thanh toán trong danh sách.
- Giữ mọi dòng log có mức `ERROR`, kể cả khi xen giữa các dòng khác.
- Chọn các sản phẩm thuộc một danh mục, không quan tâm chúng xuất hiện ở đâu.
- Xử lý dữ liệu không có thứ tự mà điều kiện có ý nghĩa độc lập trên từng phần tử.

Với một terminal operation cần toàn bộ kết quả như `toList()`, `filter` thường phải xét các phần tử trong phạm vi nguồn để chọn ra tất cả phần tử thỏa; nhưng không được biến điều này thành cam kết rằng predicate có tác dụng phụ được gọi **đúng một lần trong mọi pipeline**. Stream có thể tối ưu các bước khi ngữ nghĩa kết quả không đổi.

### `filter` không phải phép cắt ở mốc đầu tiên

```java
List<Integer> readings = List.of(1, 2, 10, 3, 4);

System.out.println(readings.stream()
    .filter(n -> n < 5)
    .toList()); // [1, 2, 3, 4]
```

Nếu nghiệp vụ yêu cầu **dừng dữ liệu tại lần đầu vượt ngưỡng**, kết quả `[1, 2, 3, 4]` là sai vì đã giữ `3` và `4` sau mốc vi phạm. Khi nguồn có thứ tự, `takeWhile` là thao tác phù hợp hơn.

## 4. `takeWhile`: lấy tiền tố liên tiếp thỏa điều kiện

`takeWhile` được giới thiệu từ **Java 9** cho `Stream` và các Primitive Stream. Trên Stream có thứ tự, nó trả về **tiền tố dài nhất** mà mọi phần tử trong tiền tố đều thỏa predicate.

```java
List<Integer> temperatures = List.of(28, 29, 30, 36, 29, 28);

List<Integer> beforeFirstHotReading = temperatures.stream()
    .takeWhile(temp -> temp < 35)
    .toList();

System.out.println(beforeFirstHotReading); // [28, 29, 30]
```

Sau khi gặp `36`, hai giá trị `29`, `28` ở phía sau **không xuất hiện** trong kết quả, dù chúng cũng nhỏ hơn 35.

### 4.1. Vì sao `takeWhile` có thể dừng sớm?

Trên nguồn có thứ tự, ngay khi tìm được phần tử đầu tiên không thỏa điều kiện, các phần tử sau không thể thuộc tiền tố hợp lệ. Vì vậy `takeWhile` là một thao tác trung gian **có trạng thái** (*stateful*) và **có khả năng dừng sớm** (*short-circuiting*).

```text
Nguồn:      A(true) → B(true) → C(false) → D(true) → E(true)
takeWhile:  A       → B       → STOP
Kết quả:    [A, B]
```

Về ngữ nghĩa, không cần chuyển `D` và `E` sang downstream. Tuy nhiên, trong triển khai song song hoặc một số tối ưu khác, **không được dựa vào số lần hoặc thứ tự gọi predicate** để làm công việc có tác dụng phụ.

### 4.2. Những trường hợp biên

```java
import java.util.List;

List<Integer> numbers = List.of(2, 4, 6);

System.out.println(numbers.stream()
    .takeWhile(n -> n % 2 == 0)
    .toList()); // [2, 4, 6] — mọi phần tử đều thỏa

System.out.println(numbers.stream()
    .takeWhile(n -> n < 0)
    .toList()); // [] — phần tử đầu tiên đã không thỏa

System.out.println(List.<Integer>of().stream()
    .takeWhile(n -> n > 0)
    .toList()); // [] — nguồn rỗng
```

Nếu không có phần tử làm điều kiện sai, `takeWhile` lấy toàn bộ Stream. Nếu phần tử đầu tiên đã sai, kết quả rỗng.

## 5. `dropWhile`: bỏ tiền tố, không phải loại mọi phần tử thỏa điều kiện

`dropWhile` cũng có từ Java 9. Với Stream có thứ tự, nó bỏ qua **tiền tố dài nhất** thỏa điều kiện rồi đưa **toàn bộ phần còn lại** vào downstream.

```java
List<String> lines = List.of(
    "# header", "# source", "name,amount", "# data", "A,100"
);

List<String> afterHeader = lines.stream()
    .dropWhile(line -> line.startsWith("#"))
    .toList();

System.out.println(afterHeader);
// [name,amount, # data, A,100]
```

Ví dụ này bỏ **các dòng chú thích ở đầu tệp**. Dòng `"# data"` nằm sau `"name,amount"` vẫn được giữ. Nếu thay bằng `filter(line -> !line.startsWith("#"))` thì cả `"# header"`, `"# source"` và `"# data"` đều bị loại — nghĩa khác hoàn toàn.

### 5.1. Phần tử đầu tiên không thỏa **được giữ lại**

```java
List<Integer> values = List.of(1, 2, 5, 3, 4);

System.out.println(values.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [5, 3, 4]
```

Giá trị `5` là **phần tử xác định ranh giới**. Nó không thỏa `n < 5`, nhưng `dropWhile` giữ nó lại. Nếu nghiệp vụ yêu cầu **bỏ cả phần tử ranh giới**, cần diễn đạt quy tắc bổ sung và kiểm tra trường hợp biên, thay vì tự cho rằng `dropWhile` đã làm điều đó.

### 5.2. Sau điểm cắt, phần còn lại không bị lọc bởi predicate

```java
List<Integer> values = List.of(1, 2, 7, 3, 9);

System.out.println(values.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [7, 3, 9]
```

Số `3` vẫn được giữ. `dropWhile` không phải một kiểu `filter` dùng điều kiện phủ định; nó chỉ chọn **điểm bắt đầu của phần đuôi** (*suffix*).

### 5.3. Các trường hợp biên

```java
List<Integer> values = List.of(2, 4, 6);

System.out.println(values.stream()
    .dropWhile(n -> n % 2 == 0)
    .toList()); // [] — mọi phần tử đều bị bỏ

System.out.println(values.stream()
    .dropWhile(n -> n < 0)
    .toList()); // [2, 4, 6] — phần tử đầu tiên đã không thỏa

System.out.println(List.<Integer>of().stream()
    .dropWhile(n -> n > 0)
    .toList()); // [] — nguồn rỗng
```

Khác với `takeWhile`, `dropWhile` phải tiếp tục chuyển các phần tử trong phần đuôi cho downstream nếu terminal operation cần chúng. Vì vậy **`dropWhile` không được phân loại là thao tác dừng sớm** như `takeWhile`, dù nó có thể ngừng việc kiểm tra điều kiện ở phần đã xác định xong điểm cắt.

## 6. Bảng đối chiếu cho các tình huống thường gặp

Với nguồn có thứ tự và predicate `p`:

| Dữ liệu đầu vào | `filter(p)` | `takeWhile(p)` | `dropWhile(p)` |
| --- | --- | --- | --- |
| `[]` | `[]` | `[]` | `[]` |
| Mọi phần tử đều thỏa `p` | Toàn bộ | Toàn bộ | `[]` |
| Không phần tử nào thỏa `p` | `[]` | `[]` | Toàn bộ |
| Tiền tố thỏa rồi gặp phần tử không thỏa | Giữ mọi match kể cả phía sau | Chỉ giữ tiền tố | Giữ từ phần tử không thỏa trở đi |
| Phần tử đầu không thỏa, phần sau có match | Giữ các match phía sau | `[]` | Toàn bộ |

Ví dụ trực quan với predicate `n < 5`:

| Nguồn | `filter` | `takeWhile` | `dropWhile` |
| --- | --- | --- | --- |
| `[1, 2, 3]` | `[1, 2, 3]` | `[1, 2, 3]` | `[]` |
| `[5, 1, 2]` | `[1, 2]` | `[]` | `[5, 1, 2]` |
| `[1, 2, 5]` | `[1, 2]` | `[1, 2]` | `[5]` |
| `[1, 5, 2]` | `[1, 2]` | `[1]` | `[5, 2]` |
| `[8, 9]` | `[]` | `[]` | `[8, 9]` |

Hai bảng giúp kiểm tra nhanh những cách dùng sai phổ biến: `takeWhile` **không lấy thêm** phần tử thỏa sau vị trí sai đầu tiên, còn `dropWhile` **không xóa thêm** phần tử thỏa sau vị trí đó.

## 7. Khi nào `takeWhile` giống `filter`? Điều kiện đơn điệu theo thứ tự

Trong một số nguồn, các phần tử được sắp xếp sao cho mọi phần tử thỏa predicate đều nằm **trước** mọi phần tử không thỏa. Khi đó, trên Stream có thứ tự, `filter(p)` và `takeWhile(p)` trả cùng danh sách phần tử.

Ví dụ dãy điểm tăng dần:

```java
List<Integer> sortedScores = List.of(10, 20, 30, 60, 90);

System.out.println(sortedScores.stream()
    .filter(score -> score < 50)
    .toList()); // [10, 20, 30]

System.out.println(sortedScores.stream()
    .takeWhile(score -> score < 50)
    .toList()); // [10, 20, 30]
```

Trong ví dụ này, predicate `score < 50` có **tính tiền tố** trên thứ tự tăng dần: một khi gặp giá trị không nhỏ hơn 50, sẽ không còn giá trị nào phía sau nhỏ hơn 50.

Nhưng chỉ cần đổi thứ tự nguồn, sự tương đương biến mất:

```java
List<Integer> unsorted = List.of(10, 60, 20, 90);

System.out.println(unsorted.stream()
    .filter(score -> score < 50)
    .toList()); // [10, 20]

System.out.println(unsorted.stream()
    .takeWhile(score -> score < 50)
    .toList()); // [10]
```

### 7.1. `sorted` có thể tạo thứ tự thích hợp — nhưng không miễn phí

```java
List<Integer> source = List.of(30, 70, 10, 20, 90);

List<Integer> lowScores = source.stream()
    .sorted()
    .takeWhile(score -> score < 50)
    .toList();

System.out.println(lowScores); // [10, 20, 30]
```

`sorted()` làm thay đổi encounter order theo tiêu chí sắp xếp. Đây là một thao tác trung gian **có trạng thái**: với nguồn hữu hạn không biết sẵn thứ tự, thường phải tổ chức dữ liệu để sắp xếp trước khi có thể xác định phần tử đầu của kết quả. Vì vậy, không được mặc định rằng thêm `sorted` rồi `takeWhile` sẽ nhanh hơn một `filter` đơn giản.

Hãy hỏi: nghiệp vụ yêu cầu **giữ thứ tự gốc** hay **lấy theo ngưỡng sau khi đã sắp xếp**? Đổi thứ tự có thể đổi cả ý nghĩa của báo cáo.

### 7.2. `dropWhile` và điều kiện ngưỡng

Nếu nguồn được sắp tăng và `p(n) = n < 50`, `dropWhile(p)` trả phần tử đầu tiên có giá trị từ 50 trở lên cùng toàn bộ phần sau:

```java
List<Integer> highScores = sortedScores.stream()
    .dropWhile(score -> score < 50)
    .toList();

System.out.println(highScores); // [60, 90]
```

Trong trường hợp **đã bảo đảm** thứ tự tăng và predicate theo ngưỡng, kết quả cũng giống `filter(score -> score >= 50)`. Không áp dụng sự tương đương này cho dữ liệu không sắp xếp hoặc predicate không đơn điệu theo encounter order.

## 8. Stream không có thứ tự: `takeWhile` và `dropWhile` không còn ranh giới xác định

Đây là bẫy quan trọng nhất khi chuyển từ `List` sang `HashSet` hoặc gọi `unordered()` trong pipeline.

Với **unordered Stream**:

- `filter(p)` vẫn có nghĩa “chọn các phần tử thỏa `p`”, chỉ là **không có thứ tự trả về được bảo đảm**.
- `takeWhile(p)` có thể trả về **một tập con bất kỳ của các phần tử thỏa `p`** nếu có phần tử thỏa, không nhất thiết tất cả; nó có thể chọn tập rỗng.
- `dropWhile(p)` có thể **loại một tập con bất kỳ** của các phần tử thỏa `p`; những phần tử không thỏa phải được giữ, nhưng một số phần tử thỏa có thể cũng được giữ lại.

Không còn “tiền tố dài nhất” theo một thứ tự nghiệp vụ, vì nguồn không hứa có thứ tự như vậy.

```java
import java.util.List;

List<Integer> input = List.of(1, 2, 3, 8, 9);

// Cố ý bỏ bảo đảm encounter order của pipeline.
List<Integer> taken = input.parallelStream()
    .unordered()
    .takeWhile(n -> n < 5)
    .toList();

List<Integer> dropped = input.parallelStream()
    .unordered()
    .dropWhile(n -> n < 5)
    .toList();

System.out.println(taken);
System.out.println(dropped);
// Không viết một expected output cố định cho hai kết quả này.
```

Trong đoạn trên, `taken` chỉ gồm các giá trị từ `{1, 2, 3}`, nhưng không có bảo đảm sẽ gồm đủ cả ba. `dropped` phải giữ các phần tử `8`, `9`, nhưng có thể giữ lại một số giá trị trong `{1, 2, 3}`.

### 8.1. `unordered()` không phải `shuffle()`

`unordered()` **loại bỏ ràng buộc thứ tự** để cho phép tối ưu; nó **không yêu cầu xáo trộn** dữ liệu. Có những lần chạy kết quả trông giống xử lý tuần tự, nhưng điều đó không biến kết quả quan sát được thành hợp đồng ổn định.

### 8.2. Cách chọn thao tác theo yêu cầu

Nếu mục tiêu là **tập mọi phần tử thỏa điều kiện**, dùng `filter`. Nếu mục tiêu là **cắt ở điểm đầu tiên theo thứ tự**, phải có encounter order phù hợp rồi dùng `takeWhile` hoặc `dropWhile`. Đừng dùng `unordered()` để tìm cách tăng tốc mà không chấp nhận thay đổi ngữ nghĩa.

Đối với nguồn từ `HashSet`, `takeWhile`/`dropWhile` thường không diễn đạt một điểm cắt nghiệp vụ đáng tin. Nếu thật sự cần điểm cắt, trước tiên phải **định nghĩa thứ tự** bằng nguồn phù hợp hoặc phép sắp xếp có chủ đích.

## 9. Song song: đúng ngữ nghĩa quan trọng hơn tốc độ

`takeWhile` và `dropWhile` có tính **stateful**. Đặc biệt trên **ordered parallel Stream**, xác định ranh giới tiền tố theo encounter order có thể đòi hỏi nhiều phối hợp giữa các tác vụ.

Ví dụ:

```java
import java.util.stream.IntStream;

long count = IntStream.range(0, 1_000_000)
    .parallel()
    .takeWhile(n -> n < 100_000)
    .count();

System.out.println(count); // 100000
```

Đối với `IntStream.range` có thứ tự và predicate theo ngưỡng, kết quả logic vẫn chính xác. Tuy vậy, không được suy từ việc pipeline có `parallel()` rằng nó sẽ xử lý nhanh hơn bản tuần tự.

Một số yếu tố chi phối hiệu năng:

- Kích thước nguồn và chất lượng chia nguồn của `Spliterator.trySplit()`.
- Vị trí điểm cắt và tỷ lệ phần tử đầu phải duyệt.
- Chi phí thực thi predicate, `map` và downstream collector.
- Chi phí phối hợp để giữ encounter order trong xử lý song song.
- Các thao tác có trạng thái khác như `sorted`, `distinct` và việc giữ dữ liệu trung gian.
- Tranh chấp tài nguyên, bộ nhớ và áp lực GC.

Với những yêu cầu không cần ranh giới tiền tố, `filter` thường diễn đạt trực tiếp hơn và có thể chia việc độc lập theo phần tử.

### 9.1. Không phải cứ bỏ thứ tự là tối ưu được mà vẫn đúng

```java
IntStream.range(0, 1_000_000)
    .parallel()
    .unordered()
    .takeWhile(n -> n < 100_000)
    .count();
```

Không thể dự đoán kết quả chắc chắn là 100.000, bởi `takeWhile` trên unordered Stream chỉ hứa trả một tập con được phép của những phần tử thỏa điều kiện.

Nếu kết quả **phải** là 100.000, giữ encounter order hoặc chọn phép toán khác đúng với câu hỏi. Chỉ bỏ ràng buộc thứ tự khi nghiệp vụ thực sự không cần chúng và cách cắt bất định được chấp nhận.

### 9.2. Cách đánh giá hiệu năng

Nếu mục tiêu là cải thiện tốc độ, hãy đo với dữ liệu đại diện và công cụ benchmark như JMH. So sánh tuần tự và song song với **cùng đầu vào, cùng thứ tự bắt buộc và cùng tiêu chí đúng**, không đánh đổi yêu cầu nghiệp vụ để được số đo nhanh hơn.

## 10. Phối hợp với `limit`, `skip` và thứ tự pipeline

`limit(n)` và `skip(n)` cắt theo **số lượng phần tử**, không theo predicate:

- `limit(n)`: chỉ giữ tối đa `n` phần tử đầu.
- `skip(n)`: bỏ `n` phần tử đầu.

`takeWhile` và `dropWhile` thì cắt theo **nội dung cho đến mốc đầu tiên** trên ordered Stream.

```java
import java.util.List;

List<Integer> data = List.of(1, 2, 6, 3, 4);

System.out.println(data.stream()
    .limit(3)
    .toList()); // [1, 2, 6]

System.out.println(data.stream()
    .skip(2)
    .toList()); // [6, 3, 4]

System.out.println(data.stream()
    .takeWhile(n -> n < 5)
    .toList()); // [1, 2]

System.out.println(data.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [6, 3, 4]
```

### 10.1. Đổi thứ tự các thao tác có thể đổi kết quả

Thứ tự `filter` và `takeWhile` không thể hoán đổi tùy tiện. Hãy xem ví dụ có kết quả khác nhau thật sự:

```java
List<Integer> input = List.of(1, 7, 2, 3, 8);

List<Integer> filterThenTake = input.stream()
    .filter(n -> n % 2 == 0) // [2, 8]
    .takeWhile(n -> n < 5)  // lấy [2], dừng tại 8
    .toList();

List<Integer> takeThenFilter = input.stream()
    .takeWhile(n -> n < 5)  // lấy [1], dừng tại 7
    .filter(n -> n % 2 == 0)
    .toList();             // []

System.out.println(filterThenTake); // [2]
System.out.println(takeThenFilter); // []
```

**Bản chất:** `filter` có thể xóa những phần tử vốn sẽ trở thành điểm cắt của `takeWhile`. Vì vậy thứ tự các bước quyết định vị trí ranh giới được quan sát.

### 10.2. `dropWhile` rồi `limit`

Một cách thường dùng là bỏ các bản ghi cũ ở đầu dãy đã sắp theo thời gian, sau đó lấy vài bản ghi mới:

```java
List<Integer> sorted = List.of(10, 20, 30, 40, 50, 60);

System.out.println(sorted.stream()
    .dropWhile(n -> n < 35)
    .limit(2)
    .toList()); // [40, 50]
```

Đây là một phép cắt theo **hai loại ràng buộc**: giá trị ngưỡng quyết định vị trí bắt đầu, số lượng quyết định độ dài kết quả.

### 10.3. `sorted`, `distinct` cũng thay đổi đầu vào quan sát bởi phép cắt

`sorted` thay đổi encounter order. `distinct` loại các phần tử trùng, làm thay đổi số lượng và vị trí tương đối của các phần tử còn lại. Vì vậy pipeline:

```java
stream.distinct().takeWhile(predicate)
```

có thể có kết quả khác với:

```java
stream.takeWhile(predicate).distinct()
```

Không áp dụng các biến đổi đại số giữa các thao tác một cách máy móc; hãy xác định rõ **thứ tự và phạm vi** mà predicate phải quan sát.

## 11. Stream vô hạn: dừng được hay không?

Với một nguồn vô hạn, khả năng dừng sớm là khác biệt rất thực tế.

### 11.1. `takeWhile` có thể biến nguồn vô hạn thành hữu hạn

```java
import java.util.stream.IntStream;

List<Integer> firstFive = IntStream.iterate(1, n -> n + 1)
    .takeWhile(n -> n <= 5)
    .boxed()
    .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
```

Nguồn `IntStream.iterate(1, n -> n + 1)` tạo dãy không giới hạn theo định nghĩa. Nhưng trên nguồn có thứ tự này, `takeWhile(n -> n <= 5)` dừng khi gặp `6`, nên `toList()` có thể kết thúc.

Nếu predicate **không bao giờ sai**, `takeWhile` cũng không tạo được điểm dừng; một terminal operation cần toàn bộ kết quả có thể không kết thúc.

### 11.2. `dropWhile` chỉ loại tiền tố, không làm phần đuôi hữu hạn

```java
List<Integer> afterFive = IntStream.iterate(1, n -> n + 1)
    .dropWhile(n -> n <= 5)
    .limit(3)
    .boxed()
    .toList();

System.out.println(afterFive); // [6, 7, 8]
```

`dropWhile` tìm ra `6`, sau đó **giữ phần đuôi vô hạn**. `limit(3)` là yếu tố buộc kết quả cuối hữu hạn. Nếu gọi `toList()` ngay sau `dropWhile` trên phần đuôi vô hạn, quá trình có thể chạy mãi hoặc cạn tài nguyên.

### 11.3. `filter` không có ý nghĩa “dừng khi lần đầu sai”

```java
List<Integer> firstOdds = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 != 0)
    .limit(3)
    .boxed()
    .toList();

System.out.println(firstOdds); // [1, 3, 5]
```

`filter` tìm các phần tử thỏa ở bất kỳ vị trí nào. Nếu predicate không bao giờ đúng, pipeline `filter(p).findFirst()` trên nguồn vô hạn có thể chờ mãi vì không tìm được phần tử hợp lệ.

**Lưu ý:** Với Stream vô hạn, chỉ thực hiện những terminal operation có đường kết thúc rõ ràng; `sorted()` toàn bộ nguồn vô hạn chẳng hạn thường không phù hợp vì cần xác định thứ tự trên toàn bộ nguồn trước khi trả kết quả.

## 12. Primitive Stream: cùng ý nghĩa trên `IntStream`, `LongStream`, `DoubleStream`

Cả ba phép `filter`, `takeWhile` và `dropWhile` đều có trên:

- `Stream<T>`: nhận `Predicate<? super T>`.
- `IntStream`: nhận `IntPredicate`.
- `LongStream`: nhận `LongPredicate`.
- `DoubleStream`: nhận `DoublePredicate`.

Ví dụ với `IntStream`:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = {2, 4, 7, 8, 10};

int[] even = IntStream.of(values)
    .filter(n -> n % 2 == 0)
    .toArray();

int[] initialEven = IntStream.of(values)
    .takeWhile(n -> n % 2 == 0)
    .toArray();

int[] afterInitialEven = IntStream.of(values)
    .dropWhile(n -> n % 2 == 0)
    .toArray();

System.out.println(Arrays.toString(even));             // [2, 4, 8, 10]
System.out.println(Arrays.toString(initialEven));      // [2, 4]
System.out.println(Arrays.toString(afterInitialEven)); // [7, 8, 10]
```

Ví dụ với `LongStream` và `DoubleStream`:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;
import java.util.stream.LongStream;

long[] recentIds = LongStream.of(10L, 20L, 30L, 5L)
    .takeWhile(id -> id < 25L)
    .toArray();

double[] remaining = DoubleStream.of(0.1, 0.3, 0.9, 0.2)
    .dropWhile(value -> value < 0.5)
    .toArray();

System.out.println(Arrays.toString(recentIds)); // [10, 20]
System.out.println(Arrays.toString(remaining)); // [0.9, 0.2]
```

Primitive Stream giúp tránh boxing trong các bước xử lý số. Tuy nhiên, kiểu primitive **không thay đổi** ngữ nghĩa tiền tố, encounter order hoặc giới hạn của xử lý song song.

## 13. Ví dụ hoàn chỉnh: phân tích sự kiện theo mốc thời gian

Một hệ thống nhận các sự kiện có timestamp. Người dùng muốn các sự kiện **trước** một mốc thời gian và **từ mốc đó trở đi**.

Có hai câu hỏi khác nhau:

1. “Tìm tất cả sự kiện cũ trước mốc, **dù nằm ở vị trí nào**.” → `filter`.
2. “Với các sự kiện đã sắp theo thời gian tăng dần, **cắt danh sách tại mốc**.” → `takeWhile` và `dropWhile`.

Ví dụ Java 17+ tự chứa dưới đây minh họa rõ rủi ro khi đầu vào không được sắp xếp.

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public class TimeBoundaryDemo {

    record Event(String id, Instant occurredAt, long amountVnd) {}

    public static void main(String[] args) {
        Instant cutoff = Instant.parse("2026-11-18T10:02:00Z");

        // Thứ tự nhận: E-03 đến muộn trong nguồn,
        // còn E-02 xảy ra sớm nhưng xuất hiện sau E-03.
        List<Event> events = List.of(
            new Event("E-01", Instant.parse("2026-11-18T10:00:00Z"), 100L),
            new Event("E-03", Instant.parse("2026-11-18T10:03:00Z"), 300L),
            new Event("E-02", Instant.parse("2026-11-18T10:01:00Z"), 200L),
            new Event("E-04", Instant.parse("2026-11-18T10:05:00Z"), 400L)
        );

        List<String> allEarlier = events.stream()
            .filter(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        List<String> wronglyCutUnsorted = events.stream()
            .takeWhile(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        List<Event> sorted = events.stream()
            .sorted(Comparator.comparing(Event::occurredAt))
            .toList();

        List<String> beforeBoundary = sorted.stream()
            .takeWhile(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        List<String> fromBoundary = sorted.stream()
            .dropWhile(e -> e.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        System.out.println(allEarlier);       // [E-01, E-02]
        System.out.println(wronglyCutUnsorted);// [E-01]
        System.out.println(beforeBoundary);   // [E-01, E-02]
        System.out.println(fromBoundary);     // [E-03, E-04]
    }
}
```

### Phân tích kết quả

- Dữ liệu ban đầu có `E-02` xuất hiện sau `E-03`, dù timestamp của `E-02` sớm hơn.
- `filter` tìm **tất cả sự kiện sớm hơn cutoff**, nên có `E-01` và `E-02`.
- `takeWhile` trên nguồn chưa sắp xếp gặp `E-03` (không thỏa) và cắt tại đó; `E-02` bị bỏ qua.
- `sorted(Comparator.comparing(Event::occurredAt))` tạo một thứ tự thích hợp cho phép cắt theo timestamp.
- Trên nguồn đã sắp, `takeWhile` lấy các sự kiện trước cutoff, `dropWhile` giữ các sự kiện **từ cutoff trở đi**.

Việc sắp xếp có chi phí bộ nhớ và thời gian. Nếu nguồn vốn được hệ thống bảo đảm sắp tăng theo timestamp, không nhất thiết phải gọi `sorted`. Ngược lại, nếu timestamp có thể đến không đúng thứ tự và yêu cầu chỉ là “mọi sự kiện trước mốc”, `filter` trực tiếp hơn và không cần thay đổi thứ tự nguồn.

### 13.1. Dữ liệu bằng đúng cutoff thuộc nhóm nào?

`Instant.isBefore(cutoff)` trả `false` khi timestamp **bằng** cutoff, nên sự kiện đúng tại mốc sẽ:

- **Không** nằm trong `takeWhile(isBefore)` trên nguồn đã sắp.
- **Có** trong `dropWhile(isBefore)`, vì nó là phần tử đầu tiên không còn thỏa `isBefore`.

Nếu nghiệp vụ quy định ranh giới “trước hoặc bằng” thì phải đổi predicate một cách tường minh, ví dụ `!event.occurredAt().isAfter(cutoff)`. Cách chọn điều kiện quyết định **bao gồm hay loại trừ ranh giới**, không phải bản thân tên `takeWhile`/`dropWhile`.

## 14. Lazy pipeline, tác dụng phụ và nguồn có tài nguyên

Cả ba phương thức đều là **intermediate operations** và không kích hoạt duyệt ngay lúc xây pipeline:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = List.of(1, 2, 5, 3);

Stream<Integer> pending = values.stream()
    .takeWhile(n -> n < 5)
    .map(n -> n * 10); // Chưa thực thi pipeline.

System.out.println(pending.toList()); // [10, 20]
```

`toList()` là terminal operation kích hoạt xử lý. Sau đó, không được gọi lại `pending.count()`.

### 14.1. Tránh predicate phụ thuộc trạng thái

Một cám dỗ thường gặp là dùng `filter` với biến cờ để giả lập `takeWhile`:

```java
// Không nên làm: stateful predicate và side effect.
boolean[] keep = {true};

List<Integer> result = values.parallelStream()
    .filter(n -> {
        if (n >= 5) {
            keep[0] = false;
        }
        return keep[0];
    })
    .toList();
```

Đoạn này không thread-safe khi chạy song song, và ngay cả ở tuần tự cũng khó diễn đạt/hạn chế khả năng tối ưu. Dùng `takeWhile(n -> n < 5)` với nguồn có thứ tự nếu nghiệp vụ yêu cầu dừng tại phần tử đầu tiên không hợp lệ.

Các behavioral functions nên **stateless** và **non-interfering**: không sửa nguồn đang duyệt và không dùng trạng thái bên ngoài để xác định kết quả theo lịch thực thi.

### 14.2. `peek` không phải bộ đếm chính xác số lần duyệt

`peek` và side effect trong predicate không nên là căn cứ nghiệp vụ để kết luận có bao nhiêu phần tử được đọc. Các thao tác dừng sớm, tối ưu dựa trên kích thước nguồn và xử lý song song có thể thay đổi số lần thực hiện từng giai đoạn. Nếu cần con số, hãy dùng terminal operation như `count()` trên phạm vi dữ liệu đã được chọn.

### 14.3. Stream gắn I/O phải được đóng

Ví dụ `Files.lines(path)` trả Stream gắn tệp cần đóng. `takeWhile` có thể dừng duyệt sớm, nhưng **không tự đóng tài nguyên tệp** khi terminal operation hoàn tất:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public static List<String> firstCommentBlock(Path file)
        throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines
            .takeWhile(line -> line.startsWith("#"))
            .toList();
    }
}
```

Phương thức này đọc **khối chú thích liên tiếp ở đầu tệp**, không phải mọi dòng chú thích. `try-with-resources` bảo đảm đóng nguồn cả khi pipeline dừng sớm hoặc phát sinh lỗi. Nếu caller nhận Stream từ một API khác, trách nhiệm đóng phải được xác định theo hợp đồng sở hữu của API đó.

## 15. Chọn đúng thao tác theo yêu cầu nghiệp vụ

| Yêu cầu | Thao tác nên ưu tiên | Lý do |
| --- | --- | --- |
| Giữ tất cả giao dịch đã thanh toán, dữ liệu có thể xen kẽ | `filter(Order::paid)` | Điều kiện áp dụng độc lập trên mọi phần tử |
| Đọc khối header liên tiếp ở đầu tệp | `takeWhile(isHeader)` | Dừng khi gặp dòng không còn thuộc header |
| Bỏ khối header rồi xử lý phần nội dung còn lại | `dropWhile(isHeader)` | Chỉ loại header ở đầu |
| Trên dãy timestamp đã sắp tăng, lấy phần tử trước mốc | `takeWhile(beforeCutoff)` | Cắt tại mốc thời gian đầu tiên |
| Trên dãy timestamp đã sắp tăng, lấy phần tử từ mốc trở đi | `dropWhile(beforeCutoff)` | Giữ phần đuôi kể từ ranh giới |
| Trên dữ liệu timestamp chưa sắp xếp, tìm mọi bản ghi trước mốc | `filter(beforeCutoff)` | Không bỏ sót bản ghi cũ đến muộn |
| Bỏ đúng 10 phần tử đầu, bất kể giá trị | `skip(10)` | Cắt theo số lượng |
| Lấy tối đa 10 phần tử đầu | `limit(10)` | Cắt theo số lượng |
| Chọn mọi phần tử thỏa trên nguồn unordered | `filter(predicate)` | Không yêu cầu ranh giới theo encounter order |

Một cách tự kiểm tra nhanh: **“Tôi muốn kiểm tra từng phần tử độc lập hay muốn dừng/bắt đầu tại mốc đầu tiên theo thứ tự?”** Câu trả lời thường quyết định chọn `filter` hay các phép `while`.

## 16. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `takeWhile(p)` như `filter(p)` trên dữ liệu xen kẽ | Bỏ sót các phần tử thỏa sau lần đầu sai | Dùng `filter` nếu cần tất cả match |
| Dùng `dropWhile(p)` như `filter(p.negate())` | Giữ cả các phần tử thỏa ở phần đuôi | Dùng `filter(p.negate())` nếu muốn loại **mọi** match |
| Nghĩ `dropWhile` bỏ cả phần tử đầu không thỏa | Mất hiểu biết về ranh giới | Nhớ phần tử đầu không thỏa **được giữ** |
| Dùng `takeWhile` cắt theo timestamp trên dữ liệu chưa sắp | Bỏ sót sự kiện cũ xuất hiện muộn | Dùng `filter` hoặc thiết lập thứ tự đúng |
| Gọi `unordered()` trước `takeWhile` nhưng vẫn đòi đầy đủ tiền tố | Không còn ranh giới xác định, kết quả có thể thiếu | Giữ encounter order khi cần cắt theo vị trí |
| Giả định `HashSet.stream()` có thứ tự đáng tin | Kết quả `while` không được xác định theo thứ tự nghiệp vụ | Đổi sang nguồn có thứ tự hoặc sắp xếp |
| Cho rằng `parallel().takeWhile` luôn nhanh | Ordered parallel có thể phối hợp tốn kém | Đo hiệu năng đúng workload |
| Dùng `takeWhile` trên nguồn vô hạn với predicate luôn đúng rồi `toList()` | Không có điểm kết thúc | Xác định điều kiện dừng hoặc thêm giới hạn |
| Dùng `dropWhile` trên nguồn vô hạn rồi `toList()` | Phần đuôi vẫn vô hạn | Ghép `limit` hoặc dùng cách xử lý hữu hạn khác |
| Nhầm `limit(10)` với `takeWhile(n -> n < 10)` | Một phép dựa số lượng, một phép dựa giá trị | Chọn theo định nghĩa mốc |
| Tự tạo predicate có biến `boolean[]` trong `filter` | Phụ thuộc trạng thái, race khi parallel | Dùng `takeWhile`/`dropWhile` trên ordered Stream |
| Dựa vào số lần gọi `Predicate`/`peek` để quyết định nghiệp vụ | Không đáng tin khi tối ưu hoặc song song | Dùng kết quả chính thức của terminal operation |
| Quên đóng Stream từ `Files.lines` khi dùng `takeWhile` | Rò rỉ tài nguyên | `try-with-resources` |
| Dùng lại Stream sau `toList` hoặc `count` | Stream đã được tiêu thụ | Tạo Stream mới từ nguồn nếu cần phép tính khác |

## 17. Bài tập thực hành

### Bài 1: Dự đoán ba kết quả

Với `List<Integer> values = List.of(2, 4, 7, 6, 8)`, dự đoán kết quả của `filter(n -> n % 2 == 0)`, `takeWhile(n -> n % 2 == 0)` và `dropWhile(n -> n % 2 == 0)`. Giải thích tại sao `6` và `8` chỉ xuất hiện trong một số kết quả.

### Bài 2: Khối header của tệp

Cho các dòng `["# generated", "# owner", "id,value", "# note", "1,100"]`. Dùng `takeWhile` để lấy header, `dropWhile` để bỏ header, rồi dùng `filter` để bỏ **mọi** dòng chú thích. Đối chiếu ba kết quả.

### Bài 3: Cắt theo ngưỡng

Cho `[10, 30, 50, 20, 70]` và predicate `n < 40`. Hãy tính kết quả của hai phép `while` và `filter`; sau đó thêm `sorted()` trước mỗi phép và giải thích điều gì thay đổi. Khi nào sắp xếp là hợp lệ với yêu cầu nghiệp vụ?

### Bài 4: Thứ tự pipeline

Xem `List.of(1, 7, 2, 3, 8)`. So sánh `filter(even).takeWhile(n < 5)` và `takeWhile(n < 5).filter(even)`. Vì sao hoán đổi hai thao tác cho kết quả khác?

### Bài 5: Stream không có thứ tự

Viết `IntStream.range(0, 1000).parallel().unordered().takeWhile(n -> n < 100)`. Có được khẳng định kết quả luôn chứa đủ 100 số từ 0 đến 99 không? Nếu yêu cầu là **mọi số nhỏ hơn 100**, nên dùng thao tác nào?

### Bài 6: Nguồn vô hạn

Dùng `IntStream.iterate(1, n -> n + 1)` để tạo `[1, 2, 3, 4, 5]` bằng `takeWhile`; sau đó tạo `[6, 7, 8]` bằng `dropWhile` và `limit`. Giải thích vì sao `dropWhile` không tự làm phần đuôi hữu hạn.

### Bài 7: Sự kiện không đúng thứ tự thời gian

Một hệ thống nhận log theo thời gian truyền qua mạng; sự kiện tạo lúc 10:01 có thể đến sau sự kiện 10:03. Hãy thiết kế pipeline tìm **mọi sự kiện trước 10:02**. Vì sao `takeWhile` trực tiếp trên thứ tự nhận có thể sai?

### Bài 8: Đánh giá song song

So sánh pipeline tuần tự và song song trên `IntStream.range(0, 1_000_000)` với `takeWhile(n -> n < 100_000)`. Mô tả các yếu tố đo hiệu năng cần xem xét trước khi chọn `parallel()`. Không dùng side effect trong predicate để suy luận số phần tử thực sự được xử lý.

## 18. Tự kiểm tra kiến thức

- `filter` xét toàn bộ nguồn theo điều kiện hay dừng tại phần tử không thỏa đầu tiên?
- “Tiền tố dài nhất” có nghĩa gì với `takeWhile` trên ordered Stream?
- `dropWhile` có giữ phần tử đầu tiên không thỏa predicate không?
- Vì sao `dropWhile(p)` không tương đương `filter(p.negate())`?
- Trường hợp nào `takeWhile(p)` trả cùng kết quả với `filter(p)`?
- Điều gì thay đổi khi dùng `unordered()` hoặc nguồn không có encounter order?
- Tại sao `takeWhile` có thể giúp kết thúc một Stream vô hạn còn `dropWhile` thường không?
- Vì sao `sorted` có thể làm bài toán cắt theo ngưỡng đúng hơn nhưng lại tăng chi phí?
- Phân biệt `limit`, `skip` với các phép `while` theo nội dung như thế nào?
- Có được dựa vào số lần gọi predicate trong parallel Stream để cập nhật bộ đếm nghiệp vụ không?
- Vì sao Stream gắn I/O vẫn phải được đóng ngay cả khi `takeWhile` dừng sớm?

**Ghi nhớ:** Với Stream **có thứ tự**, `filter(p)` chọn **mọi phần tử** thỏa `p`, `takeWhile(p)` chỉ lấy **tiền tố liên tiếp dài nhất** thỏa `p`, còn `dropWhile(p)` **bỏ tiền tố đó và giữ toàn bộ phần đuôi**. Muốn cắt theo mốc, hãy bảo đảm encounter order đúng với ý nghĩa nghiệp vụ. Nếu chỉ cần lọc các phần tử ở bất kỳ vị trí nào — nhất là trên nguồn không có thứ tự — hãy dùng `filter`.
