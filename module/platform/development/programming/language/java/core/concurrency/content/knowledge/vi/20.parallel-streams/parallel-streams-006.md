# Ordering trong Parallel Streams: forEachOrdered(), findFirst(), unordered()

## 1. Vấn đề cốt lõi: xử lý song song có còn thứ tự không?

Một Java Stream có thể chạy **tuần tự** (`sequential()`) hoặc **song song** (`parallel()` / `Collection.parallelStream()`). Parallel stream chia công việc thành nhiều phần và cho phép các phần được tính toán đồng thời. Vì vậy **thời điểm một phần tử được xử lý** không nhất thiết trùng với **vị trí của phần tử trong dữ liệu nguồn**.

Tuy nhiên, không phải cứ gọi `parallel()` thì mất toàn bộ thứ tự. Stream API phân biệt rõ:

- **Encounter order:** thứ tự logic khi các phần tử được “gặp” trong nguồn và qua pipeline, nếu pipeline có định nghĩa thứ tự đó. Ví dụ `List.of("A", "B", "C")` có encounter order `A → B → C`.
- **Execution order:** thời điểm và thread thực thi thao tác trên từng phần tử. Với parallel stream, thao tác trên `C` có thể chạy trước `A`.
- **Result order:** thứ tự trong kết quả cuối cùng, phụ thuộc nguồn, các intermediate operation và terminal operation; không thể suy chỉ từ việc dùng nhiều thread.
- **Ordering constraint:** ràng buộc mà Stream API phải tôn trọng. Ràng buộc này có thể làm một số phép xử lý song song cần phối hợp, chờ, sắp lại kết quả hoặc lưu buffer.

Bài này tập trung vào ba API:

1. `forEachOrdered()`: thực thi hành động cuối theo encounter order **nếu stream có thứ tự xác định**.
2. `findFirst()`: chọn phần tử đầu tiên theo encounter order **nếu có**.
3. `unordered()`: bỏ yêu cầu phải giữ encounter order, từ đó có thể cho phép tối ưu song song trong những pipeline phù hợp.

Các API là thành phần **Java Stream API thuần**; phần trình bày không phụ thuộc framework.

## 2. Encounter order được hình thành từ đâu?

### 2.1. Nguồn có thứ tự và nguồn không có thứ tự

Nguồn **có encounter order** thường gặp:

- `List`: thứ tự vị trí phần tử trong danh sách.
- Mảng thông qua `Arrays.stream(...)`: thứ tự chỉ số.
- `IntStream.range(start, end)`: tăng dần từ `start` đến trước `end`.
- `Stream.of(...)`: theo thứ tự các đối số.
- `LinkedHashSet`: theo thứ tự iteration của tập hợp đó.

Nguồn **không có encounter order được bảo đảm**:

- `HashSet`: không có hợp đồng duy trì thứ tự chèn hoặc một thứ tự cụ thể.
- `Stream.generate(...)`: nguồn stream vô hạn, unordered.
- Một số nguồn/spliterator do thư viện hoặc ứng dụng tự triển khai không khai báo đặc tính `ORDERED`.

Một `HashSet` có thể **in giống cùng một thứ tự** qua nhiều lần chạy thử; quan sát đó không biến thứ tự thành hợp đồng API. Không nên viết test dựa vào thứ tự ngẫu nhiên quan sát được.

### 2.2. Intermediate operation có thể giữ, tạo hoặc bỏ thứ tự

Với một nguồn có thứ tự, những phép `map` và `filter` thông thường giữ **thứ tự logic tương đối** của các phần tử còn lại. Ví dụ lọc số chẵn từ `[5, 2, 4, 1]` có thứ tự `[2, 4]`, ngay cả khi việc kiểm tra predicate trên các phần tử chạy đồng thời.

Một số phép ảnh hưởng trực tiếp đến ordering:

| Phép toán | Ý nghĩa với encounter order |
|---|---|
| `map()` / `filter()` | Thông thường bảo toàn thứ tự tương đối đã được định nghĩa |
| `sorted()` | Đặt thứ tự theo giá trị hoặc comparator; với dữ liệu bằng nhau cần xét tính ổn định |
| `unordered()` | Bỏ ràng buộc encounter order, **không tự sắp xếp hoặc xáo trộn** |
| `distinct()` | Nếu ordered, giữ lần xuất hiện đầu tiên của mỗi giá trị; nếu unordered, không bảo đảm chọn lần xuất hiện nào khi các giá trị bằng nhau |
| `limit(n)` / `skip(n)` | Với ordered stream, “n phần tử đầu” có nghĩa rõ; với unordered stream, phép chọn/bỏ không cần tuân theo một tiền tố cố định |
| `takeWhile()` / `dropWhile()` | Với ordered stream, xử lý một tiền tố liên tiếp; với unordered stream, ngữ nghĩa tập con khác và có thể không xác định |

**Hai chiều cần tách biệt:** `parallel()` điều khiển **chế độ thực thi**; `unordered()` điều khiển **cam kết về thứ tự**. Một stream hoàn toàn có thể vừa `parallel` vừa `ordered`, hoặc `sequential` nhưng `unordered`.

## 3. forEach() và forEachOrdered(): vì sao hai kết quả có thể khác?

Cả hai là **terminal operation**, nghĩa là kết thúc pipeline và tiêu thụ stream. Điểm khác là mức bảo đảm thứ tự của **hành động cuối**:

- `forEach(action)`: với parallel stream, không cam kết tôn trọng encounter order. Thư viện có thể thực thi action trên các thread và thời điểm khác nhau; lần chạy A và B có thể in thứ tự khác nhau.
- `forEachOrdered(action)`: nếu stream có encounter order, action được thực hiện **theo đúng thứ tự đó**, từng phần tử một. API bảo đảm action với phần tử trước **happens-before** action với phần tử sau.
- `forEachOrdered` không nói rằng mọi action phải chạy trên **cùng một thread**; JVM được phép chọn thread khác nhau cho từng phần tử.
- Việc **xử lý ở upstream** (`map`, `filter`, v.v.) vẫn có thể song song. `forEachOrdered` ràng buộc thứ tự **quan sát được của action cuối**, không biến toàn bộ pipeline thành một stream sequential.

### Ví dụ 1: kết quả xác định bằng forEachOrdered

**Tệp `OrderedTerminal.java` (Java 17+):**

```java
import java.util.List;

public class OrderedTerminal {
    public static void main(String[] args) {
        List<String> letters = List.of("D", "B", "A", "C");

        System.out.print("ordered actions: ");
        letters.parallelStream()
                .map(String::toLowerCase)
                .forEachOrdered(letter -> System.out.print(letter + " "));
        System.out.println();

        System.out.println("ordered result: " +
                letters.parallelStream()
                        .map(String::toLowerCase)
                        .toList());
    }
}
```

Lệnh:

```bash
javac OrderedTerminal.java
java OrderedTerminal
```

Stdout chính xác:

```text
ordered actions: d b a c 
ordered result: [d, b, a, c]
```

Dấu cách ở cuối dòng thứ nhất do `System.out.print(letter + " ")` chủ động in ra. `List` có encounter order `D, B, A, C`; `map` chuyển chữ thường mà không đổi thứ tự logic. Với ordered stream, `Stream.toList()` (Java 16+) giữ encounter order trong kết quả.

**Nếu thay `forEachOrdered` bằng `forEach`** thì các chữ vẫn được xử lý, nhưng **thứ tự xuất hiện trên màn hình không được bảo đảm**. Không thể viết một chuỗi stdout cố định cho trường hợp `forEach` song song, kể cả trên máy có nhiều CPU.

### Ví dụ 2: không cố kiểm tra thứ tự bất định

**Tệp `UnorderedPrint.java` (Java 17+):**

```java
import java.util.stream.IntStream;

public class UnorderedPrint {
    public static void main(String[] args) {
        IntStream.rangeClosed(1, 8)
                .parallel()
                .forEach(value -> System.out.print(value + " "));
        System.out.println();
    }
}
```

Chạy:

```bash
javac UnorderedPrint.java
java UnorderedPrint
```

Một lần chạy **có thể** in `6 5 8 7 3 2 1 4`, hoặc một hoán vị khác, thậm chí `1 2 3 4 5 6 7 8`. **Không có stdout cố định được bảo đảm**. `forEach` trên parallel stream chỉ cam kết gọi action cho các phần tử được pipeline tiêu thụ; thứ tự không là một phần của hợp đồng.

### 3.1. Happens-before không có nghĩa toàn pipeline chạy tuần tự

Javadoc bảo đảm: với `forEachOrdered`, việc thực thi action cho một phần tử **happens-before** action cho phần tử tiếp theo. Điều này cung cấp quan hệ thứ tự bộ nhớ giữa **các action cuối**. Nhưng không mở rộng thành giả định rằng mỗi `map` chạy trên cùng thread hay theo thứ tự.

Ví dụ này có action cuối được thực hiện đúng thứ tự, dù `map` có thể tính toán song song:

```java
IntStream.range(0, 5)
        .parallel()
        .map(n -> n * 2)
        .forEachOrdered(System.out::println);
```

Đoạn trên đặt trong một phương thức có `import java.util.stream.IntStream;`, và stdout của terminal action là:

```text
0
2
4
6
8
```

Không nên dùng sự bảo đảm đó để tạo side effect trong `map`. Các thao tác trung gian nên **stateless** và **non-interfering**, không cùng sửa một `ArrayList` hoặc biến dùng chung mà không đồng bộ.

### 3.2. Trường hợp nào dùng forEachOrdered?

Phù hợp khi hành động cuối có thứ tự quan trọng: xuất bản dòng dữ liệu theo thứ tự nguồn, in log theo thứ tự bản ghi, ghi một định dạng tuyến tính hoặc xử lý một hiệu ứng có yêu cầu tuần tự.

Không cần thiết nếu chỉ cộng số, tính thống kê, đếm, kiểm tra điều kiện hoặc gom nhóm không yêu cầu thứ tự. Với các phép aggregate, ưu tiên `reduce` hoặc collector thích hợp thay vì `forEach` sửa biến ngoài.

**Hạn chế:** bảo đảm thứ tự ở terminal action có thể làm giảm khả năng tận dụng parallelism và tạo thêm phối hợp/buffer, nhất là khi chính action chậm. Nếu mọi action phải chạy tuần tự và công việc chủ yếu nằm trong action, hãy đo so với `sequential()`.

## 4. findFirst(): “đầu tiên” là theo encounter order

`findFirst()` là **short-circuiting terminal operation**. Nó trả về `Optional<T>` (hoặc `OptionalInt`, `OptionalLong`, `OptionalDouble` với primitive stream):

- Nếu stream **có encounter order**, chọn **phần tử đầu tiên** trong pipeline (sau các phép filter/map liên quan).
- Nếu stream **không có encounter order**, có thể chọn **bất kỳ phần tử nào**.
- Stream rỗng trả `Optional.empty()`; không gọi `get()` nếu chưa kiểm tra. `orElse(...)` hoặc `orElseThrow()` thường rõ ràng hơn.
- Với reference stream, phần tử được chọn mà là `null` khiến `findFirst()` ném `NullPointerException`; đừng thiết kế pipeline có phần tử null không được xử lý.

“Đầu tiên” không có nghĩa **task xử lý nhanh nhất**. Với ordered parallel stream, engine có thể đã tính phần tử phía sau trước nhưng vẫn phải chọn phần tử đứng đầu theo encounter order.

### Ví dụ 3: findFirst() ổn định khi có order

**Tệp `FirstElement.java` (Java 17+):**

```java
import java.util.List;

public class FirstElement {
    public static void main(String[] args) {
        List<Integer> source = List.of(9, 4, 8, 2, 6);

        int firstEven = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElse(-1);

        int smallestEven = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .sorted()
                .findFirst()
                .orElse(-1);

        int missing = source.parallelStream()
                .filter(n -> n < 0)
                .findFirst()
                .orElse(-1);

        System.out.println("first even: " + firstEven);
        System.out.println("smallest even: " + smallestEven);
        System.out.println("none: " + missing);
    }
}
```

Chạy:

```bash
javac FirstElement.java
java FirstElement
```

Stdout chính xác:

```text
first even: 4
smallest even: 2
none: -1
```

`firstEven == 4` vì phần tử chẵn đầu tiên **trong thứ tự nguồn** là 4, dù 2 nhỏ hơn. Sau `sorted()`, thứ tự mới có phần tử chẵn đầu là 2. Nếu bài toán thực sự tìm **giá trị nhỏ nhất**, có thể biểu đạt trực tiếp bằng `min(Integer::compareTo)` và tránh sắp toàn bộ dữ liệu:

```java
int minimumEven = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .min(Integer::compareTo)
        .orElse(-1);
```

Đây là đoạn minh họa trong cùng phạm vi `main` có biến `source`; kết quả là `2`.

### 4.1. findAny() khác findFirst()

`findAny()` chọn một phần tử phù hợp **không cam kết vị trí**, kể cả khi nguồn có encounter order. Với parallel stream, nó cho engine thêm quyền chọn theo cách thực thi hiệu quả. `findAny()` vẫn có thể vô tình trả phần tử đầu tiên; đó không là bảo đảm.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Bản ghi đầu tiên trong danh sách thỏa điều kiện | `findFirst()` trên ordered stream |
| Bất kỳ bản ghi nào thỏa điều kiện | `findAny()` |
| Giá trị nhỏ nhất/lớn nhất | `min()` / `max()` |
| Muốn tất cả kết quả theo thứ tự | Ordered stream + `toList()` hoặc collector giữ encounter order |
| Muốn một kết quả nhưng input không có order | `findAny()` hoặc `findFirst()` đều không có “đầu tiên” xác định |

**Hiệu năng:** `findFirst()` trong ordered parallel stream có thể cần phối hợp giữa các partition để chứng minh rằng không còn phần tử đứng trước nào thỏa điều kiện. `findAny()` có thể tránh ràng buộc đó. Tuy nhiên, hiệu năng thực tế còn tùy dữ liệu, predicate, partition, số CPU và các operation khác; **không khẳng định luôn nhanh hơn**.

### 4.2. Short-circuit không có nghĩa “chỉ chạy đúng một phần tử”

Parallel stream có thể đã bắt đầu kiểm tra nhiều phần tử trước khi `findFirst()` chọn được kết quả. Các hàm `filter`/`map` nên thuần và không dựa vào việc gọi đúng một lần hoặc đúng số lần. Không tính số tác vụ đã chạy chỉ bằng bộ đếm đặt trong `peek` rồi xem đó là hành vi được bảo đảm.

## 5. unordered(): bỏ ràng buộc, không phải trộn dữ liệu

`BaseStream.unordered()` là **intermediate operation** trả về stream tương đương nhưng không còn yêu cầu encounter order. Nó có thể không phải làm công việc thực tế nào nếu stream vốn unordered.

**Nó không:**

- Tự biến stream thành parallel; muốn chạy song song phải gọi `parallel()` hoặc tạo parallel stream.
- Bảo đảm hoán vị ngẫu nhiên hay đảo ngược dữ liệu; muốn shuffle phải dùng thuật toán riêng.
- Sắp xếp tăng/giảm; muốn sort phải gọi `sorted()`.
- Thay đổi thứ tự hoặc nội dung của `List` gốc.
- Bảo đảm tốc độ nhanh hơn trong mọi pipeline.
- Bảo đảm `findFirst()` sẽ trả phần tử khác phần tử đầu; nó chỉ **loại bỏ nghĩa vụ** phải trả phần tử đầu tiên.

### Ví dụ 4: kiểm tra hợp đồng unordered mà không đoán kết quả

**Tệp `UnorderedContract.java` (Java 17+):**

```java
import java.util.List;

public class UnorderedContract {
    public static void main(String[] args) {
        List<Integer> values = List.of(10, 20, 30, 40);

        int chosen = values.parallelStream()
                .unordered()
                .findFirst()
                .orElseThrow();

        System.out.println("chosen belongs to source: " +
                values.contains(chosen));
        System.out.println("source: " + values);
        System.out.println("sorted again: " +
                values.parallelStream()
                        .unordered()
                        .sorted()
                        .toList());
    }
}
```

Chạy:

```bash
javac UnorderedContract.java
java UnorderedContract
```

Stdout được bảo đảm cho ba dòng:

```text
chosen belongs to source: true
source: [10, 20, 30, 40]
sorted again: [10, 20, 30, 40]
```

Ta cố ý không in giá trị cụ thể của `chosen`: nó có thể là **bất kỳ phần tử nào** trong danh sách. `sorted()` ở pipeline thứ ba **áp đặt lại thứ tự** theo giá trị (cần dữ liệu hỗ trợ so sánh), nên kết quả sau đó có encounter order xác định.

Ngay cả khi đoạn thử nghiệm luôn thấy `chosen == 10` trên một JDK cụ thể, code vẫn **không được dựa** vào kết quả đó. Một version, dữ liệu, cấu hình hoặc lịch chạy khác có thể cho kết quả khác.

### 5.1. Thứ tự gọi các operation có thể đổi ngữ nghĩa

So sánh:

```java
// Phần tử chẵn đầu tiên theo thứ tự List:
source.parallelStream().filter(n -> n % 2 == 0).findFirst();

// Không còn yêu cầu chọn phần tử chẵn đầu tiên:
source.parallelStream().unordered()
        .filter(n -> n % 2 == 0).findFirst();

// Sắp xếp đặt lại thứ tự, rồi lấy phần tử chẵn nhỏ nhất:
source.parallelStream().unordered()
        .filter(n -> n % 2 == 0).sorted().findFirst();

// Bỏ thứ tự sau khi sắp xếp: không còn cam kết lấy nhỏ nhất:
source.parallelStream().sorted()
        .unordered().findFirst();
```

Đoạn trên là các **biểu thức minh họa**, giả sử `source` là `List<Integer>` đã khai báo; mỗi dòng là một pipeline riêng. Đừng nhầm “từng bước tính toán nhanh chậm ra sao” với thứ tự logic do API bảo đảm.

### 5.2. unordered() ảnh hưởng forEachOrdered() thế nào?

Tên `forEachOrdered()` dễ gây ngộ nhận. Nó chỉ bảo đảm đi **theo encounter order nếu có**. Sau khi gọi `unordered()`, stream không còn encounter order để terminal action tuân theo, nên:

```java
values.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);
```

Với `values` là một `List<Integer>`, **không thể đòi** stdout đúng thứ tự danh sách. Trong một lần chạy hoặc implementation cụ thể nó vẫn có thể in theo thứ tự cũ; không có nghĩa chương trình được phép phụ thuộc vào hành vi đó.

**Đừng dùng `unordered().forEachOrdered(...)` như một mẹo vừa bảo đảm thứ tự vừa tối ưu tốc độ**; hai mong muốn trái ngược ngay ở hợp đồng ordering.

## 6. Khi nào bỏ ordering có thể giúp parallel stream?

Theo tài liệu JDK, ràng buộc thứ tự đặc biệt ảnh hưởng tới một số **stateful intermediate operation** và phép chọn tiền tố:

| Operation | Ordered parallel stream cần giữ | Sau `unordered()` có thể |
|---|---|---|
| `distinct()` | Giữ lần xuất hiện đầu trong encounter order; thường cần phối hợp/buffer | Không cần giữ phần tử xuất hiện đầu; có thể giảm phối hợp |
| `limit(n)` | Chọn **n phần tử đầu tiên** | Chọn **bất kỳ n phần tử phù hợp** (nếu có đủ) |
| `skip(n)` | Bỏ đúng **n phần tử đầu** | Không cần xác định một tiền tố cố định |
| `takeWhile(p)` | Lấy tiền tố liên tiếp dài nhất thỏa `p` | Có thể lấy tập con bất kỳ từ các phần tử thỏa `p` theo hợp đồng unordered |
| `dropWhile(p)` | Bỏ tiền tố liên tiếp dài nhất thỏa `p` | Có thể bỏ tập con các phần tử thỏa `p`, không theo tiền tố |
| `findFirst()` | Tìm phần tử thỏa mãn đầu tiên | Có thể trả bất kỳ phần tử nào; xem xét `findAny()` nếu đó là ý định |

**Đổi ordering đồng nghĩa có thể đổi kết quả.** Nếu nghiệp vụ yêu cầu “10 bản ghi đầu tiên theo thứ tự thời gian”, `unordered().limit(10)` là **sai ngữ nghĩa**, dù benchmark nhanh hơn.

Ngược lại, nếu mục tiêu chỉ là “lấy tối đa 10 đối tượng bất kỳ thỏa điều kiện” và không có yêu cầu công bằng, thứ tự hoặc ổn định, việc bỏ ordering có thể hợp lý.

### Ví dụ 5: kết quả tập hợp có thể giữ nguyên dù bỏ ordering

**Tệp `DistinctCount.java` (Java 17+):**

```java
import java.util.stream.IntStream;

public class DistinctCount {
    public static void main(String[] args) {
        long distinct = IntStream.range(0, 100_000)
                .parallel()
                .unordered()
                .map(n -> n % 100)
                .distinct()
                .count();

        System.out.println("distinct count=" + distinct);
    }
}
```

Chạy:

```bash
javac DistinctCount.java
java DistinctCount
```

Stdout:

```text
distinct count=100
```

Vì chỉ cần **số giá trị khác nhau**, thứ tự không có ý nghĩa cho kết quả này. `unordered()` có thể giúp `distinct()` được triển khai hiệu quả hơn trong một số tình huống, nhưng không thể kết luận nhanh hơn chỉ từ ví dụ nhỏ này.

### Ví dụ 6: limit() có nghĩa khác khi unordered

Với:

```java
List<Integer> data = List.of(10, 20, 30, 40, 50, 60);
List<Integer> firstThree =
        data.parallelStream().limit(3).toList();
List<Integer> anyThree =
        data.parallelStream().unordered().limit(3).toList();
```

Đây là các câu lệnh minh họa trong phương thức có `import java.util.List;`.

- `firstThree` **được bảo đảm** là `[10, 20, 30]`.
- `anyThree` được bảo đảm có **ba phần tử từ nguồn** (với ví dụ sáu phần tử này) nhưng **không được bảo đảm là ba phần tử đầu**. Thứ tự trong `anyThree` cũng không có hợp đồng encounter order.
- Không nên hardcode một kết quả cụ thể cho `anyThree`. Một lần chạy có thể vẫn cho `[10, 20, 30]`.

Nếu cần chọn ba phần tử ngẫu nhiên thực sự, `unordered().limit(3)` **không phải thuật toán lấy mẫu ngẫu nhiên**.

## 7. Cách suy luận đúng khi phối hợp ba API

Đọc pipeline từ **nguồn sang terminal** và trả lời theo thứ tự:

1. Nguồn có encounter order hay không?
2. Trung gian có thêm `sorted()` hay bỏ `unordered()` không?
3. Stream đang parallel hay sequential?
4. Terminal operation có tôn trọng order hay bỏ qua order?
5. Kết quả cần bảo đảm **vị trí** hay chỉ cần bảo đảm **giá trị/tập phần tử**?

Ví dụ với `List.of(7, 3, 8, 2)`:

| Pipeline | Kết quả/ý nghĩa được bảo đảm |
|---|---|
| `parallelStream().findFirst()` | `7` |
| `parallelStream().filter(x -> x % 2 == 0).findFirst()` | `8` |
| `parallelStream().unordered().findFirst()` | Một trong `7, 3, 8, 2` |
| `parallelStream().unordered().filter(x -> x % 2 == 0).findFirst()` | `8` hoặc `2` |
| `parallelStream().sorted().findFirst()` | `2` |
| `parallelStream().unordered().sorted().findFirst()` | `2` |
| `parallelStream().sorted().unordered().findFirst()` | Không cam kết `2` |
| `parallelStream().forEachOrdered(...)` | Action theo `7, 3, 8, 2` |
| `parallelStream().forEach(...)` | Không cam kết thứ tự action |

Một thay đổi một dòng như chèn `unordered()` trước `findFirst()` có thể đổi hợp đồng nghiệp vụ từ **“bản ghi đầu tiên”** sang **“bản ghi bất kỳ”**. Vì vậy review code phải hiểu *vì sao* order được yêu cầu.

## 8. Sai lầm phổ biến về ordering và side effect

### Sai lầm 1: “parallelStream() luôn phá thứ tự”

Sai. Ordered stream vẫn có encounter order. `toList()` và `forEachOrdered()` có thể quan sát kết quả theo order đó. Chỉ **thứ tự thực thi nội bộ** không được cam kết.

### Sai lầm 2: “forEachOrdered() ép mọi thứ chạy trên một thread”

Sai. Chỉ bảo đảm action theo order nếu stream có encounter order; một action có thể chạy trên thread khác action trước. Upstream computation vẫn có thể song song.

### Sai lầm 3: “forEach() được bảo đảm là unordered()”

Sai theo nghĩa API: `forEach()` là terminal operation **không bắt buộc** tôn trọng thứ tự khi chạy parallel; `unordered()` là intermediate operation **bỏ ràng buộc encounter order** cho phần pipeline tiếp theo. Mục đích và vị trí của hai phép khác nhau.

### Sai lầm 4: “unordered() xáo trộn dữ liệu”

Sai. Nó chỉ bỏ yêu cầu giữ thứ tự. Không làm ngẫu nhiên hóa và không sửa collection nguồn.

### Sai lầm 5: “findFirst() trong parallel stream trả phần tử chạy xong đầu tiên”

Sai. Nếu ordered, đó là **phần tử đầu theo encounter order** thỏa điều kiện, dù partition phía sau tính xong sớm hơn.

### Sai lầm 6: “Có synchronizedList là append giữ đúng encounter order”

`Collections.synchronizedList(...)` có thể bảo vệ thao tác append khỏi data race, **không bảo đảm thứ tự các thread đến append** tương ứng encounter order. Thay vì:

```java
List<Integer> result = java.util.Collections.synchronizedList(
        new java.util.ArrayList<>());
source.parallelStream().forEach(result::add);
```

hãy ưu tiên phép tạo kết quả trực tiếp:

```java
List<Integer> result = source.parallelStream().toList();
```

Hai đoạn là **mã minh họa**, giả sử `source` là `List<Integer>`. Phương án `toList()` rõ ràng hơn, không dùng side effect ra collection ngoài và giữ order khi nguồn có order. `Stream.toList()` trả một List không chỉnh sửa được; nếu cần mutable result, cân nhắc `collect(Collectors.toCollection(ArrayList::new))` với import phù hợp.

### Sai lầm 7: “unordered() chắc chắn giúp nhanh hơn”

Không. Chi phí đổi order, kích thước dữ liệu, overhead chia việc/ghép kết quả, contention và số CPU quyết định. Với thao tác đơn giản trên dữ liệu nhỏ, parallelism có thể **chậm hơn sequential**; thêm `unordered()` không xóa overhead.

### Sai lầm 8: “Bỏ ordering lúc nào cũng an toàn vì kết quả vẫn đủ phần tử”

`unordered()` có thể thay đổi **phần tử được chọn** ở `limit`, `skip`, `findFirst`, `takeWhile`, `dropWhile`. Với các tình huống như phân trang, ưu tiên, SLA hoặc nghiệp vụ chọn bản ghi đầu tiên, thay đổi là lỗi chức năng, không chỉ vấn đề trình bày.

## 9. Kiểm thử ordering theo hợp đồng thay vì theo may rủi

Một test tốt phải kiểm tra **điều được bảo đảm**, không phụ thuộc một lịch chạy ngẫu nhiên.

**Test nên viết:**

- Với ordered `List` và `findFirst()`: assert đúng phần tử đầu sau filter.
- Với ordered `List` và `forEachOrdered()`: assert action tạo chuỗi đúng thứ tự nguồn.
- Với unordered `findFirst()`: assert phần tử thuộc tập ứng viên, không assert bằng phần tử đầu.
- Với `unordered().limit(n)`: assert kích thước, tính hợp lệ và không trùng phần tử khi nguồn không trùng; không assert một tiền tố cố định.
- Với `unordered().distinct().count()`: assert số lượng phần tử phân biệt.
- Với `sorted()`: assert thứ tự comparator và không giả định tính ổn định của phần tử có khóa bằng nhau trên unordered source.

Ví dụ xác minh một hợp đồng xác định:

**Tệp `OrderingAssertions.java` (Java 17+):**

```java
import java.util.List;
import java.util.stream.Collectors;

public class OrderingAssertions {
    public static void main(String[] args) {
        List<String> values = List.of("A", "C", "B");

        StringBuilder ordered = new StringBuilder();
        values.parallelStream().forEachOrdered(ordered::append);

        if (!"ACB".contentEquals(ordered)) {
            throw new AssertionError("forEachOrdered lost encounter order");
        }

        String first = values.parallelStream().findFirst().orElseThrow();
        if (!"A".equals(first)) {
            throw new AssertionError("findFirst did not respect order");
        }

        String any = values.parallelStream()
                .unordered().findFirst().orElseThrow();
        if (!values.contains(any)) {
            throw new AssertionError("unordered result outside source");
        }

        List<String> collected = values.parallelStream()
                .collect(Collectors.toList());
        if (!collected.equals(values)) {
            throw new AssertionError("ordered collection mismatch");
        }

        System.out.println("Ordering contracts passed");
    }
}
```

Chạy:

```bash
javac OrderingAssertions.java
java OrderingAssertions
```

Stdout xác định:

```text
Ordering contracts passed
```

`StringBuilder` ở đây an toàn theo **hợp đồng action tuần tự của `forEachOrdered`** (các action xử lý lần lượt có happens-before), và object này chỉ được sử dụng sau khi terminal operation hoàn tất. Không áp dụng cách viết đó với `parallelStream().forEach(ordered::append)` vì `StringBuilder` không thread-safe.

## 10. Quyết định đúng cho bài toán thực tế

**Tình huống A — gửi bản ghi theo thứ tự business:** Mỗi bản ghi có vị trí trong danh sách và phía nhận yêu cầu đúng thứ tự. Giữ ordered pipeline; nếu action cuối có side effect có thứ tự, cân nhắc `forEachOrdered()`. Với output lớn, đo bộ nhớ và latency.

**Tình huống B — tìm người đầu tiên đạt tiêu chí ưu tiên:** Dữ liệu đầu vào đã sắp theo mức ưu tiên, cần mục đầu tiên thỏa điều kiện. Dùng `filter(...).findFirst()` và giữ encounter order. Không thêm `unordered()` chỉ vì thấy nhanh hơn.

**Tình huống C — kiểm tra tồn tại hoặc lấy một phần tử bất kỳ:** Nếu thứ tự không quan trọng, `anyMatch(...)` hoặc `findAny()` diễn đạt đúng hơn `findFirst()`. Không nên dùng `findFirst()` để ngầm hứa “đầu tiên” rồi làm mất ordering trong pipeline.

**Tình huống D — đếm phần tử duy nhất trên dữ liệu lớn:** Nếu chỉ cần số lượng distinct, `parallel().unordered().distinct().count()` có thể phù hợp; đo với dữ liệu thật trước khi tối ưu.

**Tình huống E — lấy n phần tử đầu để phân trang:** Giữ nguồn ordered và `limit(n)`, đồng thời xác định rõ nguồn có sắp theo trường nghiệp vụ nào. Nếu nguồn vốn unordered thì ngay từ đầu “trang đầu” đã không có nghĩa ổn định.

**Tình huống F — cần kết quả sorted:** Nếu mục tiêu là danh sách có thứ tự theo comparator, `sorted(comparator)` đưa ra thứ tự cần thiết. Chỉ thêm `unordered()` trước `sorted()` khi có lý do và hiểu rằng stability của các phần tử có khóa bằng nhau trên nguồn unordered không được bảo đảm.

## 11. Checklist review và đo hiệu năng

- [ ] Xác định chính xác thứ tự nguồn (`List`, mảng, `HashSet`, custom spliterator...).
- [ ] Xem pipeline có `sorted()`, `unordered()`, `distinct()`, `limit()`, `skip()`, `takeWhile()` hay `dropWhile()`.
- [ ] Tách yêu cầu **thứ tự kết quả** khỏi nhu cầu **song song hóa phép tính**.
- [ ] Nếu muốn phần tử đầu, dùng `findFirst()` trên nguồn có order; nếu chỉ cần bất kỳ, xét `findAny()`.
- [ ] Nếu muốn side effect theo thứ tự, xét `forEachOrdered()`, đồng thời cân nhắc chi phí.
- [ ] Không dùng `unordered()` như shuffle hoặc như một cam kết tăng tốc.
- [ ] Tránh thay đổi mutable shared state trong `map`/`filter`/`forEach` khi chạy parallel; ưu tiên collector/reduction.
- [ ] Test ordering theo hợp đồng; không hardcode output của hành vi không xác định.
- [ ] Benchmark với cùng đầu vào, cùng ngữ nghĩa kết quả, sau khi JVM warm up; theo dõi thời gian, CPU, allocation và bộ nhớ đệm.
- [ ] Nếu ordered parallel quá chậm và order là bắt buộc, thử `sequential()` trước khi làm code phức tạp hơn.

## 12. Câu hỏi tự kiểm tra

1. Với `List.of(5, 1, 4)`, `parallelStream().map(x -> x * 2).toList()` được bảo đảm trả danh sách nào?
2. `forEachOrdered()` có luôn chạy action trên cùng một worker thread hay không?
3. Vì sao `parallelStream().filter(x -> x > 10).findFirst()` có thể phải chờ kết quả từ partition phía trước, dù partition phía sau tìm thấy phần tử trước?
4. Gọi `unordered()` trước `findFirst()` có bắt buộc chọn phần tử khác phần tử đầu nguồn không?
5. Khi nào `unordered().limit(10)` đúng nghiệp vụ? Khi nào là lỗi?
6. Vì sao `Collections.synchronizedList` không bảo đảm thứ tự append tương ứng encounter order nếu dùng `parallelStream().forEach(...)`?
7. Nếu một `HashSet` luôn lặp ra cùng thứ tự trong thử nghiệm, có thể dựa vào đó cho `findFirst()` không?
8. Dùng `unordered().sorted().findFirst()` và `sorted().unordered().findFirst()` có cùng cam kết tìm giá trị nhỏ nhất không?

**Gợi ý trả lời:** (1) `[10, 2, 8]`; (2) không, chỉ bảo đảm thứ tự và happens-before giữa các action; (3) phải xác minh đúng “đầu tiên”; (4) không; (5) đúng khi bất kỳ 10 phần tử nào đều chấp nhận được, sai khi cần 10 phần tử đầu; (6) synchronized bảo vệ thao tác chứ không quyết định thứ tự đến; (7) không, `HashSet` không có encounter order; (8) không, chỉ pipeline **sort cuối cùng trước findFirst** còn cam kết nhỏ nhất.

## Tài liệu chuẩn

- [Java SE 21 — Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): `forEach`, `forEachOrdered`, `findFirst`, `findAny`, `distinct`, `limit`, `skip` và `sorted`.
- [Java SE 21 — BaseStream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html): `parallel()`, `sequential()`, `unordered()`, `isParallel()`.
- [Java SE 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): encounter order, parallelism, non-interference và quy tắc reduction.
- [dev.java — Stream terminal operations](https://dev.java/learn/api/streams/terminal-operations/): cách sử dụng `findFirst()`, `findAny()` và các terminal operation.

> **Ghi nhớ:** `parallel()` thay đổi **cách thực thi**, `unordered()` thay đổi **ràng buộc về thứ tự**, `findFirst()` cần encounter order để có nghĩa “đầu tiên”, còn `forEachOrdered()` giữ **thứ tự của action cuối khi order được định nghĩa**. Chọn API theo **hợp đồng dữ liệu cần bảo đảm**, sau đó mới tối ưu hiệu năng.