# Thứ tự gặp phần tử khác thứ tự thực thi lambda trong Java Stream song song

## 1. Câu hỏi trung tâm

Khi gọi `parallelStream()` hoặc `stream().parallel()`, nhiều phần tử của Stream có thể được xử lý bằng các tác vụ chạy đồng thời. Điều này làm nảy sinh một nhầm lẫn quan trọng:

> **Thứ tự gặp phần tử (encounter order)** là thứ tự logic mà nguồn và các stage của Stream quy định; **thứ tự thực thi lambda** là thứ tự thực tế mà mapper, predicate hoặc action được gọi trên các phần tử trong quá trình chạy. Hai thứ tự này **không đồng nhất** khi chạy song song.

Ví dụ một danh sách có thứ tự:

```text
Nguồn List:       [1, 2, 3, 4, 5]
Encounter order:   1 → 2 → 3 → 4 → 5

Một lịch chạy lambda có thể là:
                  map(3) → map(5) → map(1) → map(2) → map(4)

Kết quả toList() trên ordered stream vẫn có thể là:
                  [10, 20, 30, 40, 50]
```

Dòng “một lịch chạy” là **minh họa một khả năng**, không phải lịch chạy được Java cam kết. JVM có thể chọn lịch khác, hoặc thậm chí xử lý ít luồng tùy tải và môi trường. Điều được API cam kết ở đây là **ý nghĩa thứ tự dữ liệu kết quả**, không phải thứ tự từng lời gọi `map`.

Mục tiêu của bài:

- Phân biệt encounter order, execution order, output order và thứ tự side effect.
- Biết operation nào **giữ thứ tự kết quả**, operation nào **không bảo đảm thứ tự callback**.
- Phân biệt `forEach` với `forEachOrdered` và giới hạn của `forEachOrdered`.
- Hiểu `findFirst` khác `findAny`, tác động của `unordered()`, `sorted()` và các thao tác ngắn mạch.
- Viết lambda **stateless**, **non-interfering** và tránh lỗi mutable shared state.
- Kiểm thử giá trị cuối cùng thay vì coi thứ tự log như một phần của hợp đồng.

## 2. Bốn khái niệm “thứ tự” cần tách biệt

| Khái niệm | Câu hỏi nó trả lời | Điều API bảo đảm |
| --- | --- | --- |
| **Encounter order** | Theo thứ tự logic nào các phần tử được xem là đi qua Stream? | Tùy nguồn và các stage, chẳng hạn List có thứ tự, sorted thiết lập thứ tự |
| **Execution order** | Lambda được gọi vào thời điểm nào, trên thread nào, theo thứ tự nào? | Với parallel stream thường **không có cam kết** thứ tự đó theo encounter order |
| **Result order** | Kết quả terminal operation được thu/hiển thị theo thứ tự nào? | Phụ thuộc terminal operation và tính ordered của pipeline |
| **Side-effect order** | Log, cập nhật biến, ghi file xảy ra theo thứ tự nào? | Không nên dựa vào thứ tự callback; chỉ một số API, như `forEachOrdered`, có hợp đồng riêng |

Một ví dụ: `list.parallelStream().map(f).toList()`. Nếu `list` có encounter order, `toList()` trả danh sách theo encounter order của kết quả ánh xạ; nhưng các lần gọi `f.apply(...)` có thể đan xen trên nhiều thread.

Chẳng hạn:

```java
List<Integer> squares = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * n)
        .toList();
```

Kết quả của đoạn code trong một phương thức Java 17 có import `List` là `[1, 4, 9, 16]`. Không cần biết mapper chạy với 4 trước hay 1 trước để suy ra điều đó.

**Một pipeline có thứ tự không có nghĩa mỗi lambda sẽ chạy tuần tự.** Framework có thể lưu kết quả ở những vị trí tương ứng rồi tạo danh sách cuối cùng đúng thứ tự.

## 3. Nguồn nào có encounter order?

Không phải mọi Stream đều bắt đầu với một trật tự encounter xác định.

| Nguồn / stage | Thứ tự logic |
| --- | --- |
| `List.of("A","B","C").stream()` | Có encounter order theo thứ tự phần tử của List |
| `Arrays.stream(array)` | Có thứ tự theo index của mảng |
| `IntStream.range(0, 5)` | Có thứ tự 0, 1, 2, 3, 4 |
| `Stream.of("A","B","C")` | Có thứ tự theo thứ tự đối số |
| Stream từ `HashSet` | Không nên dựa vào một encounter order xác định |
| `stream.sorted(comparator)` | Thiết lập thứ tự của các phần tử theo comparator |
| `stream.unordered()` | Gỡ ràng buộc ordered nếu có; **không có nghĩa là xáo trộn ngẫu nhiên** |

Đặt `parallel()` **không tự xóa encounter order**. Một ordered stream vẫn ordered khi chuyển sang parallel. Điểm thay đổi chủ yếu là **cách lập lịch xử lý**, không phải việc tự động đổi nghĩa dữ liệu thành unordered.

Ngược lại, khi nguồn đã unordered, một terminal operation yêu cầu “phần tử đầu tiên” sẽ không có ý nghĩa theo thứ tự List ban đầu vốn không tồn tại. Với nguồn List có thứ tự, `findFirst()` có nghĩa rõ ràng hơn.

Không dùng thứ tự duyệt ngẫu nhiên quan sát được từ `HashSet` làm một cam kết. Nếu yêu cầu là kết quả sắp tăng dần, hãy dùng `sorted()` với comparator phù hợp, thay vì trông chờ cấu trúc hash tình cờ cho cùng thứ tự ở lần chạy hiện tại.

## 4. Ví dụ Java 17: nguồn ordered, kết quả ordered dù pipeline parallel

Lưu file `ParallelResultOrderDemo.java`:

```java
import java.util.List;

public class ParallelResultOrderDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(6, 2, 4, 1, 5, 3);

        List<Integer> tenTimes = source.parallelStream()
                .map(n -> n * 10)
                .toList();

        List<Integer> oddValues = source.parallelStream()
                .filter(n -> n % 2 != 0)
                .toList();

        List<Integer> ascending = source.parallelStream()
                .sorted()
                .toList();

        System.out.println("source=" + source);
        System.out.println("mapped=" + tenTimes);
        System.out.println("odds=" + oddValues);
        System.out.println("sorted=" + ascending);
    }
}
```

Biên dịch/chạy:

```bash
javac ParallelResultOrderDemo.java
java ParallelResultOrderDemo
```

Kết quả chính xác:

```text
source=[6, 2, 4, 1, 5, 3]
mapped=[60, 20, 40, 10, 50, 30]
odds=[1, 5, 3]
sorted=[1, 2, 3, 4, 5, 6]
```

Giải thích:

1. `source` là List có encounter order 6, 2, 4, 1, 5, 3.
2. `map(n -> n * 10)` tạo các giá trị mới và giữ thứ tự tương ứng theo nguồn trong kết quả `toList()`. Không có yêu cầu mapper phải chạy theo thứ tự đó.
3. `filter(n -> n % 2 != 0)` loại các số chẵn, giữ **thứ tự tương đối** của những phần tử còn lại trong ordered stream: 1, 5, 3.
4. `sorted()` thiết lập thứ tự số tăng dần, nên kết quả cuối là 1, 2, 3, 4, 5, 6.
5. `toList()` trên ordered stream trả danh sách theo encounter order kết quả, kể cả khi các phần tính toán được xử lý song song.
6. Mọi lời gọi ở trên tạo Stream mới từ nguồn; không sử dụng lại cùng một instance Stream sau terminal operation.

Đừng kết luận rằng `parallelStream()` “vô dụng” chỉ vì kết quả vẫn có thứ tự. Lợi ích có thể đến từ công việc tính toán trên nhiều phần tử được phân chia, trong khi hệ thống vẫn phải hợp nhất kết quả theo hợp đồng.

## 5. Quan sát execution order: log có thể không đi theo thứ tự nguồn

Ví dụ sau cố ý đưa log vào mapper để giúp **quan sát khi học**, không phải mẫu sản xuất nên dùng log làm kết quả nghiệp vụ.

Tạo file `ParallelExecutionLogDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelExecutionLogDemo {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 8)
                .boxed()
                .toList();

        System.out.println("source=" + source);

        List<Integer> result = source.parallelStream()
                .map(n -> {
                    System.out.println("map " + n + " on " +
                            Thread.currentThread().getName());
                    return n * 10;
                })
                .toList();

        System.out.println("result=" + result);
    }
}
```

Chạy:

```bash
javac ParallelExecutionLogDemo.java
java ParallelExecutionLogDemo
```

**Hai dòng đầu/cuối xác định** (giữa chúng là các dòng log tùy lịch chạy):

```text
source=[1, 2, 3, 4, 5, 6, 7, 8]
... các dòng map 1..8, có thể xen kẽ trên nhiều thread ...
result=[10, 20, 30, 40, 50, 60, 70, 80]
```

Phần ở giữa **không phải stdout cố định**; thứ tự và tên thread khác nhau theo mỗi lần chạy. Java có thể thực thi các lambda trên worker thread của ForkJoinPool hoặc thread đang gọi, và không bắt buộc phân phối đồng thời cho mọi môi trường.

Điều có thể kiểm chứng đáng tin là dữ liệu `result` theo đúng thứ tự logic khi source ordered. Vì thế, không viết test so sánh nguyên văn toàn bộ log của một parallel pipeline. Test nên so kết quả cuối cùng và những bất biến có cam kết.

Ngay cả ở một Stream tuần tự, không nên mở rộng suy luận “đúng một lần mỗi callback mỗi phần tử” thành quy tắc cho mọi pipeline: short-circuit và tối ưu bỏ qua stage vẫn có thể xảy ra.

## 6. `forEach()` không bảo đảm thứ tự action

Tài liệu `Stream.forEach` mô tả đây là terminal operation **explicitly nondeterministic** về thứ tự gọi action đối với stream parallel: framework tự do thực thi action trên thread được chọn và theo thứ tự phù hợp lịch chạy.

Đoạn sau minh họa:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEach(n -> System.out.print(n + " "));
```

Giả sử đoạn nằm trong phương thức có import `java.util.stream.IntStream`. Một lần chạy có thể in:

```text
3 5 4 2 1
```

**Đây chỉ là ví dụ output có thể xảy ra**, không phải giá trị phải thu được. Một lần chạy khác có thể in thứ tự 1, 2, 3, 4, 5 hoặc thứ tự khác. Nếu nhiều action ghi ra cùng một output stream, cách chúng xen nhau còn phụ thuộc việc các lời gọi ghi được đồng bộ ra sao; không nên dựa vào log để suy ra lịch chính xác.

Mục đích của `forEach` là yêu cầu action áp dụng trên các phần tử được tiêu thụ, **không phải** đưa ra một bản ghi có thứ tự theo encounter order. Nếu quy tắc nghiệp vụ đòi trình tự xuất, cần một API có hợp đồng phù hợp.

## 7. `forEachOrdered()` bảo đảm thứ tự của action, nhưng không ép mapper trước đó chạy tuần tự

Với một Stream có encounter order, `forEachOrdered(action)` bảo đảm action được thực hiện **theo encounter order**. Đặc tả còn bảo đảm action trên phần tử đứng trước *happens-before* action trên phần tử tiếp theo; điều này là ràng buộc về thứ tự action, không phải giấy phép chia sẻ mutable state tùy tiện trong upstream stages.

Tạo file `ForEachOrderedDemo.java`:

```java
import java.util.stream.IntStream;

public class ForEachOrderedDemo {
    public static void main(String[] args) {
        StringBuilder output = new StringBuilder();

        IntStream.rangeClosed(1, 5)
                .parallel()
                .forEachOrdered(n -> output.append(n).append(" "));

        System.out.println("ordered=" + output.toString().trim());

        System.out.println("mapped=" +
                IntStream.rangeClosed(1, 5)
                        .parallel()
                        .map(n -> n * n)
                        .boxed()
                        .toList());
    }
}
```

Biên dịch/chạy:

```bash
javac ForEachOrderedDemo.java
java ForEachOrderedDemo
```

Output xác định:

```text
ordered=1 2 3 4 5
mapped=[1, 4, 9, 16, 25]
```

Trong ví dụ này, `StringBuilder` chỉ được thay đổi trong các action `forEachOrdered` có quan hệ *happens-before* giữa những phần tử theo thứ tự, nên action không bị chạy đồng thời tùy tiện như `forEach`. Tuy nhiên, với code sản xuất nên ưu tiên thu kết quả và format ở bước rõ ràng, thay vì mặc định mọi side effect trong parallel stream đều an toàn.

**Giới hạn:** nếu thêm `map` hoặc `peek` **trước** `forEachOrdered`, không có cam kết rằng các callback upstream ấy sẽ chạy theo thứ tự encounter. `forEachOrdered` áp dụng cam kết thứ tự cho **action được truyền vào chính nó**, không phải toàn bộ pipeline.

Ví dụ minh họa:

```java
IntStream.rangeClosed(1, 5).parallel()
        .map(n -> {
            System.out.println("map " + n); // thứ tự không cam kết
            return n * 10;
        })
        .forEachOrdered(n -> System.out.println("out " + n));
```

Dòng `out ...` giữ thứ tự 10, 20, 30, 40, 50 trên ordered stream, còn các dòng `map ...` có thể xuất hiện đan xen trước hoặc giữa chúng. Đoạn này nằm trong phương thức có import `IntStream`; stdout đầy đủ không cố định và **không nên** được dùng làm assertion chính xác.

## 8. Bảng so sánh các terminal operation thường gặp

| Terminal | Ordered source + parallel | Lưu ý |
| --- | --- | --- |
| `toList()` | Danh sách theo encounter order | Không bảo đảm thứ tự mapper/peek thực thi |
| `collect(Collectors.toList())` | Kết quả giữ encounter order theo hợp đồng collector thích hợp | Không bảo đảm collection mutable/immutable cụ thể theo API này |
| `forEach(action)` | Không cam kết thứ tự action | Thường cho phép thực thi theo lịch parallel |
| `forEachOrdered(action)` | Action theo encounter order | Không ép toàn bộ upstream callbacks chạy theo thứ tự |
| `findFirst()` | Phần tử đầu tiên theo encounter order | Có thể làm parallel kém linh hoạt hơn |
| `findAny()` | Một phần tử thỏa bất kỳ | Chọn phần tử không cam kết, kể cả khi nguồn ordered |
| `anyMatch()`, `allMatch()`, `noneMatch()` | Trả boolean theo điều kiện | Có thể dừng sớm; không cam kết trình tự/đầy đủ callback |
| `count()` | Đếm số phần tử | Có thể tối ưu bỏ qua một số stage không ảnh hưởng kích thước |
| `min()`/`max()` | Tìm giá trị cực trị theo comparator | Kết quả giá trị không yêu cầu log theo thứ tự |

Không đánh đồng **“terminal có kết quả xác định”** với **“mọi callback được gọi theo thứ tự xác định”**. Một phép gộp có thể dùng các kết quả trung gian và hợp nhất đúng, dù các nhóm được xử lý theo các nhánh công việc khác nhau.

## 9. `findFirst()` và `findAny()`: rõ thứ tự và không rõ thứ tự

Với ordered stream:

- `findFirst()` theo hợp đồng cố gắng lấy **phần tử đầu tiên trong encounter order**.
- `findAny()` được phép lấy **một phần tử bất kỳ**, không yêu cầu trả phần tử đầu tiên. Đây là lựa chọn thuận tiện khi chỉ cần “có một kết quả nào đó”, đặc biệt ở parallel stream.

Tạo tệp `FindFirstAnyDemo.java`:

```java
import java.util.List;

public class FindFirstAnyDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(10, 20, 30, 40);

        int first = numbers.parallelStream()
                .findFirst()
                .orElse(-1);

        int any = numbers.parallelStream()
                .findAny()
                .orElse(-1);

        System.out.println("first=" + first);
        System.out.println("any-is-member=" + numbers.contains(any));
    }
}
```

Chạy:

```bash
javac FindFirstAnyDemo.java
java FindFirstAnyDemo
```

Output xác định:

```text
first=10
any-is-member=true
```

Giá trị chính xác của biến `any` **không được Java cam kết** trong ví dụ này; nó là một phần tử bất kỳ của danh sách không rỗng. Nếu in `any` thay vì in điều kiện membership, stdout có thể khác nhau giữa các lần chạy.

Nếu nguồn unordered (hoặc đã gọi `unordered()`), `findFirst()` không còn một “đầu tiên theo nguồn List” được bảo đảm, nên có thể trả một phần tử bất kỳ. Không thiết kế nghiệp vụ dựa vào kết quả tình cờ ổn định của `findAny` trong một môi trường cụ thể.

## 10. Thứ tự `map`, `filter` và `sorted` trong parallel pipeline

**Với ordered stream**, `map` và `filter` giữ được ý nghĩa encounter order tương ứng:

```java
List<Integer> source = List.of(5, 2, 7, 4);

List<Integer> values = source.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 10)
        .toList();
```

Kết quả là `[50, 70]`, vì các số lẻ 5 và 7 xuất hiện theo thứ tự đó trong nguồn. Nhưng `Predicate.test` trên phần tử 7 vẫn có thể chạy trước phần tử 5 ở một số lịch song song.

`sorted()` là **stateful intermediate operation** và thiết lập thứ tự logic mới theo comparator. Một pipeline:

```java
List<Integer> sorted = source.parallelStream()
        .sorted()
        .toList();
```

trả `[2, 4, 5, 7]`, không cần callback so sánh hay mapper chạy theo thứ tự nguồn. Nếu comparator có side effect (ghi log, thay đổi trạng thái), thứ tự và số lần gọi comparator thường không phải hợp đồng để dựa vào.

Với source có encounter order, `sorted` là stable theo hợp đồng: các phần tử so sánh bằng nhau giữ thứ tự tương đối. Với source unordered, không có cam kết stability cho các phần tử bằng khóa. Muốn thứ tự kết quả xác định khi có nhiều phần tử trùng khóa, hãy đặt comparator phụ như `thenComparing(...)`.

## 11. `unordered()` không đồng nghĩa với `shuffle()`

Một nhầm lẫn phổ biến là:

```java
List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .unordered()
        .toList();
```

Sau `unordered()`, Stream **không còn ràng buộc phải bảo toàn encounter order**, nhưng điều đó không bắt buộc Java hoán vị các phần tử. Kết quả có thể vẫn là `[1, 2, 3, 4]` trong nhiều lần chạy; không được dựa vào điều đó để nói `unordered()` “không làm gì” hoặc “xáo trộn ngẫu nhiên”.

Khi bỏ ràng buộc thứ tự, một số operation stateful hoặc short-circuit có thể có thêm cơ hội tối ưu. Ví dụ `distinct` trên ordered parallel stream phải giữ logic phần tử đầu trong encounter order, trong khi trên unordered stream có thể linh hoạt hơn. Hay `limit(n)` trên ordered parallel stream cần lấy n phần tử đầu theo thứ tự; với unordered, lựa chọn n phần tử có thể khác miễn tuân thủ hợp đồng tương ứng.

Nếu cần thứ tự ngẫu nhiên, hãy dùng cơ chế shuffle/sampling rõ ràng trên dữ liệu thích hợp. `unordered()` không phải hàm randomize.

## 12. `limit()`, `skip()` và short-circuit khi chạy song song

Khi source ordered:

```java
List<Integer> firstThree = IntStream.rangeClosed(1, 10)
        .parallel()
        .limit(3)
        .boxed()
        .toList();
```

Kết quả là `[1, 2, 3]`. Điều đó **không** nói rằng framework nhất thiết chỉ bắt đầu xử lý ba phần tử đầu trong mọi pipeline. Parallel tasks có thể được phân chia hoặc xử lý một phần khác trước khi toàn bộ quá trình ngừng; hợp đồng terminal chủ yếu quan tâm đến giá trị kết quả, không phải một lịch thăm phần tử cụ thể.

Với `skip(3)` trên ordered stream của 1..10, phần tử còn lại bắt đầu từ 4 theo encounter order; với unordered stream, hành vi về việc chọn phần tử cụ thể không cần gắn vào “ba phần tử đầu ban đầu”.

Một tối ưu thường được xem xét là cho phép unordered khi ứng dụng **không quan tâm phần tử nào** được chọn. Nhưng việc đó **làm thay đổi ràng buộc nghiệp vụ**. Không thêm `unordered()` chỉ để tăng tốc nếu người dùng cần top-N, pagination, hoặc lựa chọn phần tử đầu tiên theo thứ tự ổn định.

## 13. Side effect trong lambda: nguy hiểm hơn sự khác thứ tự log

Sự khác nhau giữa encounter order và execution order không chỉ là chuyện log trông lộn xộn. Nếu lambda **ghi vào một biến hoặc collection mutable dùng chung**, kết quả có thể sai thật sự.

### Mẫu sai: sửa `ArrayList` dùng chung từ `forEach` song song

```java
List<Integer> result = new ArrayList<>();
IntStream.rangeClosed(1, 10_000)
        .parallel()
        .forEach(result::add); // KHÔNG AN TOÀN
```

Đây là **đoạn phản ví dụ**, cần import `List`, `ArrayList`, `IntStream`. `ArrayList` không thread-safe; các action concurrent có thể làm hỏng trạng thái, thiếu phần tử hoặc gây lỗi. Đôi khi chạy “đúng” trong thử nghiệm nhỏ không chứng minh code an toàn.

**Cách đúng khi mục tiêu là thu kết quả:**

```java
List<Integer> result = IntStream.rangeClosed(1, 10_000)
        .parallel()
        .boxed()
        .toList();
```

Bằng cách này framework chịu trách nhiệm phối hợp tích lũy kết quả theo hợp đồng terminal. Với ordered stream, list theo encounter order. Không cần side effect vào container ngoài.

### Mẫu sai về mặt ý nghĩa: đánh số theo thời điểm callback chạy

```java
AtomicInteger sequence = new AtomicInteger();

List<String> labels = IntStream.rangeClosed(1, 5)
        .parallel()
        .mapToObj(n -> n + ":" + sequence.incrementAndGet())
        .toList();
```

Đây là **đoạn minh họa điều cần tránh khi muốn đánh số theo encounter order**, cần import `AtomicInteger`, `List`, `IntStream`. `AtomicInteger` tránh race trên biến đếm, nhưng số thứ tự vẫn phản ánh **thứ tự callback lấy lượt**, không phải thứ tự nguồn. List kết quả có thể theo thứ tự n tăng dần nhưng nhãn số đếm không tăng dần theo n.

Nếu mục tiêu là đánh chỉ số theo vị trí nguồn, dùng nguồn có index rõ, ví dụ `IntStream.range(0, list.size()).mapToObj(i -> (i + 1) + ":" + list.get(i))`, rồi thu bằng `toList()`. Cách này dựa vào **chỉ số**, không dựa vào lịch gọi lambda.

## 14. Ví dụ Java 17 đầy đủ: đánh số theo index và tránh shared state

Tạo file `StableIndexDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class StableIndexDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "An", "Minh", "Hoa");

        List<String> labels = IntStream.range(0, names.size())
                .parallel()
                .mapToObj(i -> (i + 1) + ":" + names.get(i))
                .toList();

        System.out.println(labels);
    }
}
```

Chạy:

```bash
javac StableIndexDemo.java
java StableIndexDemo
```

Output:

```text
[1:Lan, 2:An, 3:Minh, 4:Hoa]
```

Phần tử đầu tiên có index 0 nhưng được gắn nhãn 1; nhãn dựa vào index **bất biến đối với lịch xử lý**. `IntStream.range(0, n)` có encounter order theo dãy chỉ số. `List.of(...)` cung cấp danh sách không thay đổi, thuận tiện cho ví dụ read-only. Với nguồn mutable được sửa đồng thời, cách đánh chỉ số cũng cần đồng bộ/snapshot thích hợp.

Mẫu này phù hợp cho nhiều tác vụ xử lý theo vị trí. Tuy nhiên không phải Stream nào cũng có index; để tạo số thứ tự cho stream phức tạp, cần thiết kế thao tác indexing phù hợp hoặc đưa dữ liệu vào collection có thứ tự rõ trước.

## 15. `forEachOrdered` không bảo đảm mọi side effect upstream an toàn

Xét:

```java
List<String> names = List.of("A", "B", "C");
List<String> mutable = new ArrayList<>();

names.parallelStream()
        .map(s -> {
            mutable.add(s);  // vẫn sai: mapper có thể chạy đồng thời
            return s;
        })
        .forEachOrdered(System.out::println);
```

Đây là **đoạn phản ví dụ về an toàn đồng thời**, yêu cầu import `List`, `ArrayList`. Dù `forEachOrdered` in các phần tử A, B, C theo đúng encounter order, hành vi `mutable.add(s)` ở **mapper upstream** không trở thành thread-safe. `forEachOrdered` chỉ cam kết thứ tự action được truyền vào nó.

Vì thế:

- Đừng sửa mutable collection dùng chung trong `map`/`filter`/`peek` của pipeline parallel.
- Tránh lambda phụ thuộc số lần gọi, thread ID hoặc thời điểm callback chạy.
- Nếu cần gộp dữ liệu, sử dụng `collect`/`reduce` với accumulator, combiner đúng hợp đồng và không dùng mutable accumulator chung ngoài framework.
- Nếu cần side effect bắt buộc theo thứ tự, cân nhắc pipeline tuần tự hoặc API có hợp đồng ordering phù hợp; không đặt side effect ngẫu nhiên trong intermediate stage.
- Nếu cần kiểm tra thứ tự, hãy kiểm thử **kết quả được materialize**, không kiểm tra thứ tự in log của mapper.

Đối với `peek()`, tài liệu API nhấn mạnh nó chủ yếu hữu ích cho debugging. Framework còn có thể **bỏ qua một số operation** khi không ảnh hưởng kết quả cuối theo hợp đồng; ví dụ `count()` trên nguồn sized có thể tính nhanh mà không gọi `peek`. Dùng `peek` để làm audit bắt buộc là sai cả khi chạy tuần tự, không riêng parallel.

## 16. Kiểm thử song song: tập trung vào dữ liệu xác định

Một test tốt phải kiểm tra điều Java bảo đảm:

```java
List<Integer> input = List.of(4, 1, 3, 2);

List<Integer> actual = input.parallelStream()
        .map(n -> n * 2)
        .toList();

if (!actual.equals(List.of(8, 2, 6, 4))) {
    throw new AssertionError(actual);
}
```

Đây là đoạn code trong phương thức có import `List`. Test dựa trên encounter order và semantics của `map`/`toList`, không quan tâm mapper chạy trên thread nào.

Để kiểm thử những kết quả không cần thứ tự, so sánh tập hợp/multiset khi thích hợp (đặc biệt chú ý số lần xuất hiện của giá trị trùng, tránh chuyển thành Set nếu cần giữ duplicates). Nếu yêu cầu thứ tự rõ ràng, đừng “sửa” test bằng cách biến expected và actual thành Set; hãy xây pipeline hoặc comparator thỏa yêu cầu.

Với code có side effect, test ngẫu nhiên chạy qua vài lần thường không chứng minh thread safety. Thiết kế tránh state dùng chung vẫn quan trọng hơn việc thử chạy nhiều lần thấy không lỗi.

## 17. Parallel không luôn nhanh hơn sequential

Một hiểu lầm khác: đã có nhiều thread thì công việc chắc chắn nhanh hơn. Trong thực tế, parallel stream có thêm chi phí phân chia nguồn, lập lịch, hợp nhất kết quả, áp lực bộ nhớ và đồng bộ. Nếu callback quá nhẹ (ví dụ `n -> n + 1` trên vài phần tử), phần chi phí này có thể lớn hơn lợi ích.

Một số stage phụ thuộc encounter order như `findFirst()`, `limit()`, `skip()` hoặc xử lý sắp xếp toàn cục có thể làm parallel phức tạp hơn. Nếu nghiệp vụ không cần thứ tự, bỏ ràng buộc ordered đôi khi mở thêm cơ hội tối ưu, nhưng chỉ nên làm khi **không đổi yêu cầu dữ liệu**.

Hãy chọn theo thứ tự ưu tiên:

1. **Đúng semantics**: đầu vào, kết quả, thứ tự bắt buộc và xử lý lỗi.
2. **An toàn đồng thời**: lambda non-interfering, stateless hoặc có đồng bộ đúng.
3. **Tính xác định**: có cần output theo thứ tự hay chỉ cần giá trị tương đương?
4. **Hiệu năng thực tế**: benchmark trên dữ liệu, máy và tải đại diện.

Không suy tốc độ từ thứ tự log hoặc số thread nhìn thấy trên console.

## 18. Lỗi thường gặp

1. **Tưởng `parallelStream()` xóa thứ tự của List.** Sai: nguồn List vẫn ordered; nhiều terminal giữ encounter order kết quả.
2. **Tưởng mapper chạy theo thứ tự List vì `toList()` trả đúng thứ tự.** Sai: output order và execution order là hai hợp đồng khác nhau.
3. **Dùng `forEach` rồi so log chính xác.** Thứ tự action của `forEach` trên parallel stream không được bảo đảm.
4. **Tưởng `forEachOrdered` ép `map`/`peek` upstream chạy tuần tự.** Không; nó bảo đảm thứ tự của action trong chính terminal.
5. **Coi `findAny()` là `findFirst()` trên parallel stream.** Có thể khác; `findAny` không cam kết phần tử đầu tiên.
6. **Dùng `unordered()` như shuffle.** Nó gỡ ràng buộc thứ tự chứ không xáo ngẫu nhiên.
7. **Bỏ ordered mà không xem yêu cầu top-N/pagination.** Có thể thay đổi phần tử được chọn qua `limit/skip/findFirst`.
8. **Thêm side effect vào mapper để gán số thứ tự.** Thứ tự AtomicInteger increment là thứ tự lịch chạy, không phải encounter order.
9. **Thu kết quả vào ArrayList bên ngoài bằng `parallel().forEach(add)`.** Không thread-safe; dùng collector/toList.
10. **Lấy log của `peek` làm bằng chứng đầy đủ.** Callback có thể bị bỏ qua do short-circuit/tối ưu.
11. **Sắp mà không có tie-breaker trong source unordered.** Thứ tự phần tử có khóa bằng nhau có thể không xác định.
12. **Dùng mutable state thay đổi trong comparator/Predictate.** Dễ gây kết quả khó dự đoán và vi phạm hợp đồng.
13. **Cho rằng luôn có nhiều thread chạy song song.** Runtime có quyền phân chia tùy môi trường; không dựa vào số luồng cụ thể.
14. **Xem một lần chạy đúng là chứng minh concurrency đúng.** Race condition có thể không xuất hiện trong lần kiểm thử đó.
15. **Cho rằng mọi terminal luôn duyệt đủ và gọi callback đúng một lần.** Short-circuit, nguồn rỗng và tối ưu có thể thay đổi hành vi.
16. **Mất track nguồn ordered/unordered.** Kiểm tra stage nào thiết lập/gỡ encounter order trước khi đưa ra kết luận về đầu ra.

## 19. Bài tập tự kiểm tra

### Bài 1: Dự đoán output xác định

```java
List<Integer> values = List.of(5, 1, 4, 2, 3);

List<Integer> a = values.parallelStream()
        .map(n -> n + 10)
        .toList();

List<Integer> b = values.parallelStream()
        .filter(n -> n % 2 != 0)
        .toList();

List<Integer> c = values.parallelStream()
        .sorted()
        .limit(3)
        .toList();
```

Đây là code trong phương thức có import `List`. Hãy xác định `a`, `b`, `c` và trả lời: liệu mapper chắc chắn chạy theo thứ tự 5, 1, 4, 2, 3 không?

**Đáp án:** `a = [15, 11, 14, 12, 13]`, `b = [5, 1, 3]` và `c = [1, 2, 3]`. Không có cam kết mapper chạy theo thứ tự nguồn; `toList()` trên ordered stream giữ thứ tự kết quả.

### Bài 2: Chọn `forEach` hay `forEachOrdered`

Yêu cầu in số 1 đến 5 theo đúng thứ tự trong một stream parallel:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::println);
```

Với import `IntStream`, từng dòng sẽ là 1, 2, 3, 4, 5 theo thứ tự. Thay bằng `forEach` không bảo đảm thứ tự in đó.

### Bài 3: Có thể tin `findAny` trả 10?

```java
int x = List.of(10, 20, 30)
        .parallelStream()
        .findAny()
        .orElse(-1);
```

**Đáp án:** Không. Vì nguồn không rỗng, `x` là một phần tử trong danh sách, nhưng không có cam kết nó là 10. Nếu nghiệp vụ cần phần tử đầu theo encounter order, dùng `findFirst()` trên ordered stream.

### Bài 4: Vì sao dùng AtomicInteger vẫn sai để đánh số?

Một mapper parallel gán nhãn `sequence.incrementAndGet()` theo thời điểm callback chạy. Tại sao List kết quả vẫn có thể là ordered, nhưng nhãn số lại lộn xộn?

**Đáp án:** vì kết quả được xếp theo encounter order, còn counter tăng theo **execution order**. AtomicInteger chỉ bảo đảm tăng nguyên tử, không biến execution order thành encounter order. Dùng index của dữ liệu nếu cần đánh số vị trí.

### Bài 5: Nguy cơ trong upstream

```java
Stream.of("A", "B", "C")
        .parallel()
        .peek(System.out::println)
        .forEachOrdered(s -> save(s));
```

Đây là minh họa giả định đã có hàm `save(String)` với hợp đồng cụ thể. Có chắc `peek` in A, B, C theo thứ tự không? Còn `save`?

**Đáp án:** không có cam kết về thứ tự callback của `peek`. Nếu pipeline có encounter order, action của `forEachOrdered` gọi `save` theo thứ tự A, B, C. Vẫn cần xử lý lỗi, idempotency và tài nguyên của `save` theo nghiệp vụ; thứ tự action không thay thế các điều kiện đó.

## 20. Checklist thiết kế Stream song song

Trước khi chuyển từ `stream()` sang `parallelStream()`, tự hỏi:

- Nguồn có encounter order không? Nó đến từ List, mảng, SortedSet hay cấu trúc unordered?
- Kết quả có cần thứ tự không? Nếu có, terminal nào giữ trật tự đó?
- Callback có thuần túy, không phụ thuộc mutable state và không sửa nguồn không?
- Có side effect nào đang được đặt trong `map/filter/peek` chỉ để log, đếm hoặc cập nhật biến bên ngoài không?
- Có `findAny/findFirst/limit/skip` và điều kiện “đầu tiên” liên quan không?
- Có `sorted/distinct` và yếu tố comparator ổn định/tie-breaker không?
- Nếu dùng `forEachOrdered`, có ai đang hiểu nhầm rằng mọi upstream operation cũng chạy tuần tự không?
- Có tests chỉ so sánh log hoặc kiểm tra thread ID thay vì kết quả data không?
- Runtime có thực sự hưởng lợi khi chia nguồn và hợp nhất kết quả không?
- Nếu bỏ encounter order bằng `unordered()`, điều đó đã được nghiệp vụ cho phép chưa?

**Kết luận:** **Encounter order mô tả trật tự logic của dữ liệu; execution order mô tả lịch chạy callback.** Trong parallel stream, hai điều đó có thể rất khác nhau. Hãy viết lambda độc lập, không side effect bắt buộc; dùng `toList` để thu kết quả theo encounter order khi nguồn ordered, `forEachOrdered` khi chính action phải có thứ tự, và `findFirst` khi cần phần tử đầu tiên theo thứ tự nguồn. Với các hoạt động còn lại, đừng suy lịch gọi lambda từ thứ tự dữ liệu kết quả.

**Tài liệu tham khảo:** Java SE API `java.util.stream.Stream` (`parallel`, `unordered`, `map`, `filter`, `sorted`, `forEach`, `forEachOrdered`, `findFirst`, `findAny`, `toList`); package specification `java.util.stream` về encounter order, non-interference và stateless behaviors; `java.util.stream.IntStream`.