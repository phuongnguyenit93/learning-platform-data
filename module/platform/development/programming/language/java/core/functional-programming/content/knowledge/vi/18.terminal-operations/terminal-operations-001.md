# `forEach()` và `forEachOrdered()` — thao tác kết thúc của Java Stream

## 1. Bản chất: tiêu thụ phần tử để thực hiện hành động

`Stream.forEach(...)` và `Stream.forEachOrdered(...)` đều là **terminal operation** (thao tác kết thúc) của Stream API. Chúng nhận một `Consumer<? super T>`, tức một hành động nhận phần tử kiểu `T` và **không trả giá trị**:

```java
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

Hai chữ ký là cách trình bày giản lược. Sau khi gọi một terminal operation, stream đã được tiêu thụ và không nên sử dụng lại. Chúng thường phù hợp khi cần thực hiện **tác dụng phụ có chủ đích** như in kết quả, ghi log hoặc chuyển từng phần tử tới một API bên ngoài.

Điểm phân biệt quan trọng nhất là **thứ tự hành động**:

- **`forEach`:** không cam kết thực hiện action theo *encounter order* (thứ tự gặp phần tử). Đặc biệt trong stream song song, action có thể chạy ở các thread khác nhau và theo thứ tự không dự đoán được.
- **`forEachOrdered`:** nếu stream có *encounter order*, action phải được thực hiện theo thứ tự đó, kể cả khi stream được đánh dấu `parallel()`. Đối với một phần tử, việc thực hiện action có quan hệ *happens-before* với action của phần tử kế tiếp theo thứ tự này.

**Không hiểu nhầm:** `forEachOrdered` giữ thứ tự *action*, chứ không có nghĩa tất cả phép toán trung gian như `map`, `filter` đều bắt buộc chạy nối tiếp trên đúng một thread. Việc buộc action đầu ra có thứ tự có thể làm giảm hiệu quả song song.

## 2. Encounter order là gì?

**Encounter order** là thứ tự phần tử mà nguồn Stream định nghĩa, hoặc thứ tự được thiết lập bởi các phép toán như `sorted`.

Ví dụ:

```java
List<String> names = List.of("Lan", "Minh", "An");
names.stream().forEachOrdered(System.out::println);
```

Output:

```text
Lan
Minh
An
```

`List` có thứ tự duyệt rõ ràng, nên stream tạo từ `List` có encounter order `Lan → Minh → An`. Ngược lại, những nguồn như `HashSet` **không bảo đảm thứ tự phần tử theo cách ứng dụng nên dựa vào**; gọi `forEachOrdered` không tạo ra một thứ tự nghiệp vụ mới khi nguồn vốn không có encounter order.

Một số nguồn/hoạt động đáng nhớ:

| Nguồn hoặc thao tác | Encounter order |
| --- | --- |
| `List.stream()` | Theo thứ tự duyệt của `List` |
| `Arrays.stream(array)` | Theo thứ tự chỉ số |
| `IntStream.range(1, 5)` | `1, 2, 3, 4` |
| `Stream.of("A","B","C")` | `A, B, C` |
| `HashSet.stream()` | Không có thứ tự được bảo đảm |
| `LinkedHashSet.stream()` | Theo thứ tự iteration do collection duy trì |
| `stream.sorted()` | Tạo thứ tự theo comparator hoặc thứ tự tự nhiên |
| `stream.unordered()` | Cho phép pipeline bỏ ràng buộc encounter order |

`forEachOrdered` bảo toàn encounter order **khi nó tồn tại**. Nếu cần in kết quả theo một thứ tự được xác định bởi nghiệp vụ như mã đơn hàng tăng dần, hãy tạo thứ tự bằng `sorted(...)` trước `forEachOrdered(...)`.

## 3. `forEach`: mỗi phần tử là một lời gọi `Consumer`

Ví dụ:

```java
List<Integer> numbers = List.of(1, 2, 3);

numbers.stream().forEach(n -> System.out.println(n));
```

Với stream tuần tự từ `List` này, kết quả thực tế theo trình tự duyệt là:

```text
1
2
3
```

Tuy nhiên, **hợp đồng của `forEach` không cam kết encounter order**. Khi chuyển sang parallel stream:

```java
numbers.parallelStream().forEach(System.out::println);
```

Bạn **không được giả định** sẽ nhìn thấy `1`, `2`, `3` theo đúng thứ tự đó. Những lần chạy khác nhau hoặc các môi trường khác nhau có thể in theo nhiều thứ tự. Vì không có một stdout duy nhất được bảo đảm, đừng dùng ví dụ parallel `forEach` này để viết kiểm thử so sánh chuỗi in cố định.

### `forEach` có phải phép biến đổi?

Không. `forEach` là terminal operation trả `void`. Nó không tạo `Stream<R>` mới và không dùng để trả danh sách đã biến đổi:

```java
// Sai về mục đích nếu cần lấy List<String>:
numbers.stream().forEach(n -> "N=" + n); // Không hợp lệ: biểu thức không là statement expression.
```

Đoạn trên là **ví dụ lỗi biên dịch** và không thuộc chương trình chạy. Muốn có một danh sách mới, dùng `map` và `toList`:

```java
List<String> labels = numbers.stream()
        .map(n -> "N=" + n)
        .toList();

System.out.println(labels); // [N=1, N=2, N=3]
```

Nếu mục tiêu là **in** các nhãn, terminal `forEach` hợp lý:

```java
numbers.stream()
        .map(n -> "N=" + n)
        .forEach(System.out::println);
```

Lựa chọn không nằm ở cách viết lambda ngắn hay dài, mà ở việc bạn muốn **dữ liệu đầu ra** hay muốn **thực hiện hành động**.

## 4. `forEachOrdered`: hành động theo encounter order

Với dữ liệu có thứ tự:

```java
List<String> codes = List.of("C", "A", "B");

codes.parallelStream()
        .forEachOrdered(System.out::println);
```

Output được bảo đảm về thứ tự hành động:

```text
C
A
B
```

`forEachOrdered` tuân theo encounter order ban đầu của danh sách, **không tự sắp xếp** theo bảng chữ cái. Muốn có A, B, C:

```java
codes.parallelStream()
        .sorted()
        .forEachOrdered(System.out::println);
```

Output:

```text
A
B
C
```

Ở đây, `sorted` thiết lập thứ tự mới, còn `forEachOrdered` yêu cầu các action diễn ra theo thứ tự ấy.

### Thứ tự action không phải thứ tự tất cả bước trung gian

```java
codes.parallelStream()
        .map(value -> value.toLowerCase(java.util.Locale.ROOT))
        .forEachOrdered(System.out::println);
```

Output là:

```text
c
a
b
```

Điều được bảo đảm ở cuối là **thứ tự gọi action của `forEachOrdered`**. Không suy ra các phép gọi `map` đã chạy lần lượt C, A, B trên cùng một thread. Trong xử lý song song, các phép toán trung gian có thể thực hiện trên các thread khác nhau.

Nếu `map` có tác dụng phụ như ghi log hoặc cập nhật một biến dùng chung, không dùng `forEachOrdered` để hợp thức hóa những side effect đó. Quy tắc thiết kế an toàn hơn là giữ mapper không can thiệp vào trạng thái chia sẻ.

## 5. Chương trình Java 17 hoàn chỉnh

Ví dụ sử dụng danh sách đơn hàng có encounter order rõ ràng. Chương trình chủ động **không in thứ tự thực thi không xác định** của parallel `forEach`; thay vào đó, nó thu thập dữ liệu song song qua collection thread-safe rồi sắp xếp ở một bước riêng để có stdout xác định.

Tạo tệp **`ForEachOrderingDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

public class ForEachOrderingDemo {
    record Order(String id, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A03", 100),
                new Order("A01", 300),
                new Order("A02", 200)
        );

        System.out.println("Sequential forEach:");
        orders.stream()
                .forEach(order ->
                        System.out.println(order.id()
                                + "=" + order.amount()));

        System.out.println("Parallel forEachOrdered:");
        orders.parallelStream()
                .forEachOrdered(order ->
                        System.out.println(order.id()));

        System.out.println("Sorted and ordered:");
        orders.parallelStream()
                .sorted(Comparator.comparing(Order::id))
                .forEachOrdered(order ->
                        System.out.println(order.id()));

        // forEach song song không bảo đảm thứ tự, nên không in
        // thứ tự queue; chỉ kiểm tra tập phần tử sau khi hoàn tất.
        ConcurrentLinkedQueue<String> received =
                new ConcurrentLinkedQueue<>();
        orders.parallelStream()
                .forEach(order -> received.add(order.id()));

        System.out.println("Parallel forEach count: "
                + received.size());
        System.out.println("Parallel values sorted: "
                + received.stream().sorted().toList());

        // LongAdder xử lý các lần cộng đồng thời an toàn.
        LongAdder accumulator = new LongAdder();
        orders.parallelStream()
                .forEach(order -> accumulator.add(order.amount()));
        System.out.println("Parallel LongAdder total: "
                + accumulator.sum());

        // Khi chỉ cần tổng số tiền, reduction rõ ý định hơn.
        int total = orders.parallelStream()
                .mapToInt(Order::amount)
                .sum();
        System.out.println("Reduction total: " + total);

        // map + toList tạo danh sách kết quả theo encounter order.
        List<String> ids = orders.parallelStream()
                .map(Order::id)
                .toList();
        System.out.println("Mapped ids: " + ids);

        System.out.println("Range ordered:");
        IntStream.rangeClosed(1, 4)
                .parallel()
                .forEachOrdered(n ->
                        System.out.print(n == 1 ? "1" : " " + n));
        System.out.println();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 ForEachOrderingDemo.java
java ForEachOrderingDemo
```

**Stdout xác định trong ví dụ:**

```text
Sequential forEach:
A03=100
A01=300
A02=200
Parallel forEachOrdered:
A03
A01
A02
Sorted and ordered:
A01
A02
A03
Parallel forEach count: 3
Parallel values sorted: [A01, A02, A03]
Parallel LongAdder total: 600
Reduction total: 600
Mapped ids: [A03, A01, A02]
Range ordered:
1 2 3 4
```

### Tại sao kết quả như vậy?

1. `orders.stream()` là stream tuần tự có thứ tự duyệt theo danh sách A03, A01, A02. Chương trình mẫu in theo thứ tự tuần tự đó.
2. `orders.parallelStream().forEachOrdered(...)` **giữ encounter order A03, A01, A02**, dù pipeline là parallel.
3. `sorted(Comparator.comparing(Order::id))` tạo thứ tự mã đơn A01, A02, A03; `forEachOrdered` đảm bảo hành động in theo thứ tự ấy.
4. `ConcurrentLinkedQueue` an toàn khi nhiều thread gọi `add`. Thứ tự thực tế mà các thread thêm phần tử vào queue **không được in hoặc giả định**. Sau khi `forEach` kết thúc, queue có đủ ba mã. Gọi `sorted().toList()` trên queue cho danh sách mã có thứ tự xác định.
5. `LongAdder` phù hợp để cộng từ nhiều thread trong ví dụ, nên tổng tiền là `100+300+200 = 600`. Tuy nhiên cách dùng này có **side effect**; `mapToInt(...).sum()` thường diễn đạt nhiệm vụ tổng hợp rõ hơn và tránh tự quản lý accumulator dùng chung.
6. `Stream.toList()` giữ encounter order nếu stream có thứ tự, dù pipeline có thể tính toán song song. Vì vậy `Mapped ids` vẫn là `[A03, A01, A02]`.
7. `IntStream.rangeClosed(1, 4)` có thứ tự số tự nhiên 1, 2, 3, 4; `forEachOrdered` in thành một dòng có dấu cách giữa các số.

**Lưu ý:** Đoạn in với `System.out.print` trên `forEachOrdered` phù hợp cho minh họa thứ tự. Trong ứng dụng nhiều request, những output khác cũng có thể cùng ghi ra `System.out`; kiểm soát sự xen kẽ giữa các phần độc lập cần cơ chế log/output phù hợp.

## 6. Bảng so sánh nhanh

| Tiêu chí | `forEach(action)` | `forEachOrdered(action)` |
| --- | --- | --- |
| Loại Stream operation | Terminal | Terminal |
| Kiểu trả về | `void` | `void` |
| Nhận | `Consumer<? super T>` | `Consumer<? super T>` |
| Đảm bảo encounter order | **Không** | **Có, nếu stream có encounter order** |
| Trên stream tuần tự từ `List` | Thường quan sát đúng thứ tự duyệt | Bảo đảm đúng thứ tự hành động |
| Trên parallel stream | Hành động có thể bất kỳ thứ tự nào | Hành động theo encounter order |
| Thread thực thi | Không cố định theo hợp đồng parallel `forEach` | Không buộc toàn bộ action cùng một thread |
| Happens-before giữa các action liên tiếp | Không có bảo đảm tương đương `forEachOrdered` | Có theo thứ tự hành động được chỉ định |
| Chi phí tiềm năng | Có thể thuận lợi cho parallel | Có thể phải phối hợp/đồng bộ thứ tự |
| Thích hợp khi | Không cần thứ tự action | Bắt buộc thứ tự action |

Hai phương thức đều không tự biến stream thành collection và đều không bảo đảm side effect có thể rollback. Nếu mục đích là xây kết quả, thường nên sử dụng terminal reduction hoặc collector thay vì `forEach`/`forEachOrdered` với một danh sách mutable bên ngoài.

## 7. Nguồn không có encounter order: `forEachOrdered` không thể đoán thứ tự bạn muốn

Ví dụ:

```java
java.util.Set<String> set =
        new java.util.HashSet<>(List.of("A", "B", "C"));

set.parallelStream().forEachOrdered(System.out::println);
```

`HashSet` không cung cấp thứ tự duyệt theo nghĩa API bảo đảm phục vụ nghiệp vụ. Bởi vậy không được khẳng định output luôn là A, B, C, hoặc thứ tự mà các phần tử được thêm vào Set. `forEachOrdered` chỉ ràng buộc action theo encounter order **nếu có**.

Nếu bạn cần thứ tự rõ ràng, hãy thiết lập:

```java
set.stream()
        .sorted()
        .forEachOrdered(System.out::println);
```

Lúc này output theo thứ tự tự nhiên:

```text
A
B
C
```

Nếu mục tiêu là **giữ thứ tự thêm vào**, một cấu trúc như `LinkedHashSet` phù hợp hơn `HashSet`. Nếu mục tiêu là thứ tự theo số tiền/mã đơn, dùng comparator rõ ràng, không dựa vào “thứ tự mặc định” của một collection thiếu ràng buộc.

### `unordered()` thay đổi điều gì?

`stream.unordered()` là intermediate operation có thể **bỏ ràng buộc encounter order**. Nó không bắt buộc hoán đổi phần tử, nhưng cho phép những tối ưu có thể không giữ thứ tự. Sau `unordered()`, không nên kỳ vọng `forEachOrdered` tái tạo lại thứ tự cũ:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

// Không được dùng thứ tự in ở đây làm hợp đồng nghiệp vụ.
numbers.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);
```

Nếu cần thứ tự xác định, đừng vô tình gọi `unordered()` trong pipeline, hoặc chủ động tái lập thứ tự bằng `sorted` khi đáp ứng yêu cầu nghiệp vụ.

## 8. Điều gì xảy ra với `map`, `filter`, `sorted` trước terminal?

`forEachOrdered` bảo đảm thứ tự **thực hiện action**, không buộc mọi phép toán phía trước có thời điểm thực thi theo thứ tự.

```java
List<Integer> values = List.of(5, 2, 4, 1, 3);

values.parallelStream()
        .filter(n -> n % 2 == 1)
        .sorted()
        .forEachOrdered(System.out::println);
```

Output:

```text
1
3
5
```

`filter` chọn các số lẻ 5, 1, 3; `sorted` sắp 1, 3, 5; `forEachOrdered` in 1, 3, 5. Không được suy luận thứ tự **thread chạy predicate** hay **thứ tự gọi comparator** chỉ từ thứ tự output.

### `peek` không phải công cụ đảm bảo side effect

`peek` là intermediate operation, thường được dùng khi debug. Nó không phải cam kết rằng một hành động sẽ được thực hiện cho **mọi** phần tử bất kể downstream. Trên các pipeline có short-circuit, tối ưu hoặc nguồn đặc biệt, số lần `peek` được gọi có thể không như trực giác.

```java
List<Integer> firstTwo = List.of(1, 2, 3, 4)
        .stream()
        .peek(n -> System.out.println("seen " + n))
        .limit(2)
        .toList();
```

Đây chỉ là cách quan sát khi debug; không nên đặt việc ghi database hay audit bắt buộc trong `peek`. Nếu mục đích là thực hiện hành động cho toàn bộ các phần tử thực sự được duyệt, dùng terminal thích hợp; nếu mục đích là dữ liệu mới, hãy dùng `map`/`collect`. Đặc biệt, `forEachOrdered` ở cuối không bảo đảm `peek` được gọi tuần tự theo encounter order trong parallel pipeline.

## 9. Rủi ro khi dùng `forEach` để tự thu thập kết quả

Một phản ví dụ điển hình:

```java
List<String> output = new java.util.ArrayList<>();

// KHÔNG AN TOÀN khi chạy song song.
List.of("A", "B", "C")
        .parallelStream()
        .forEach(output::add);
```

`ArrayList` không thread-safe. Nhiều worker có thể gọi `add` cùng lúc, gây race, thiếu phần tử, thứ tự bất định hoặc tình trạng nội bộ không hợp lệ. **Việc dùng lambda/method reference không tự tạo tính an toàn đồng thời.**

Một sửa sai khác là đổi `forEach` thành `forEachOrdered` rồi cho rằng mọi thao tác sẽ trở thành “giải pháp thu thập kết quả tốt nhất”:

```java
List<String> output = new java.util.ArrayList<>();

List.of("A", "B", "C")
        .parallelStream()
        .forEachOrdered(output::add);
```

Với nguồn có thứ tự, cách này thực hiện action theo thứ tự và có ràng buộc happens-before, nhưng vẫn dùng side effect và một collection ngoại vi để làm công việc mà Stream API đã có terminal operation phù hợp. **Đừng dùng thay cho collector chỉ vì thấy stdout đúng.**

Cách rõ ràng hơn:

```java
List<String> output = List.of("A", "B", "C")
        .parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(output); // [a, b, c]
```

`toList()` trả kết quả theo encounter order khi nguồn ordered và không cho sửa danh sách qua `add`/`remove`. Nếu cần danh sách mutable, có thể tạo `new ArrayList<>(output)` sau khi pipeline hoàn tất.

### Tại sao `LongAdder` trong ví dụ vẫn được dùng?

`LongAdder` là công cụ có chủ đích dành cho các phép cộng đồng thời. Nó làm một minh họa an toàn hơn `int[] total = {0}` hoặc `AtomicInteger` khi nhiều worker cộng. Nhưng nếu bạn chỉ cần tổng số tiền của stream, `mapToInt(Order::amount).sum()` thường ngắn hơn, thuần chức năng hơn và hợp với reduction mà thư viện tối ưu.

**Nguyên tắc:** an toàn đồng thời chưa đủ để kết luận một thiết kế tốt; còn phải xét mục đích, tính kiểm thử, tính tái sử dụng và có cần side effect hay không.

## 10. `forEachOrdered` và happens-before: phạm vi chính xác

Javadoc của `forEachOrdered` nói rằng thực hiện action cho một phần tử **happens-before** thực hiện action cho phần tử tiếp theo trong encounter order. Điều này giúp đảm bảo các action của một lời gọi terminal được quan sát theo thứ tự mong muốn.

Tuy vậy:

- Nó **không làm cho toàn bộ pipeline trở thành tuần tự**. Các bước upstream có thể tính trên nhiều thread.
- Nó **không tự đồng bộ hóa các side effect độc lập** bên ngoài pipeline với mọi task khác trong ứng dụng.
- Nó **không phải transaction manager**: nếu action thứ ba ném exception, hai action trước có thể đã tạo thay đổi và không tự hoàn tác.
- Nó **không tạo encounter order** cho nguồn vốn không có thứ tự.
- Nó **không bảo đảm performance** tương đương `forEach`; việc giữ thứ tự có thể yêu cầu phối hợp và chờ đợi.

Khi thật sự phải ghi một chuỗi sự kiện theo thứ tự, có thể chọn `forEachOrdered`, hoặc thu thập thành danh sách đã sắp xếp rồi điều phối việc ghi ở một tầng chuyên trách. Với I/O quan trọng, nên xác định rõ xử lý lỗi, idempotency, retry và cơ chế ghi trước/sau.

## 11. Ngoại lệ trong action

`Consumer.accept` không khai báo checked exception. Vì vậy hai terminal operation cũng không tự xử lý checked exception thay cho bạn. Một lambda muốn gọi I/O khai báo `throws IOException` phải bắt lỗi hoặc dùng adapter đã được thiết kế.

Ví dụ unchecked exception:

```java
List<String> values = List.of("A", "STOP", "B");

try {
    values.stream().forEachOrdered(value -> {
        if (value.equals("STOP")) {
            throw new IllegalStateException("cannot continue");
        }
        System.out.println("Processed: " + value);
    });
} catch (IllegalStateException ex) {
    System.out.println("Caught: " + ex.getMessage());
}
```

Output của ví dụ tuần tự này:

```text
Processed: A
Caught: cannot continue
```

Khi action gặp `STOP`, nó ném lỗi; `B` không được in. Các side effect đã xảy ra trước lỗi, như in `Processed: A`, không được tự hoàn tác. Trong **parallel pipeline**, khi có lỗi, những action đã chạy trên worker khác có thể để lại side effect; không viết logic đòi “không một action nào xảy ra sau khi có lỗi ở một phần tử khác” nếu chưa có cơ chế điều phối mạnh hơn.

Nếu cần **xử lý lỗi của từng phần tử và tiếp tục**, có thể bắt lỗi bên trong action rồi ghi nhận kết quả thất bại, nhưng phải đảm bảo cách làm đó phù hợp nghiệp vụ (đặc biệt với ghi tiền, thanh toán hoặc thao tác không thể rollback).

## 12. Khi nào nên chọn phương thức nào?

### Chọn `forEach` khi không yêu cầu thứ tự

Ví dụ cập nhật một thống kê thread-safe trên nhiều bản ghi:

```java
java.util.concurrent.atomic.LongAdder counter =
        new java.util.concurrent.atomic.LongAdder();

List.of("A", "B", "C").parallelStream()
        .forEach(value -> counter.increment());

System.out.println(counter.sum()); // 3
```

Tuy nhiên nếu đơn giản chỉ cần **số phần tử**, `stream().count()` trực tiếp hơn. Ví dụ `counter` chủ yếu minh họa rằng tính thread-safe của action và việc bỏ qua thứ tự là hai lựa chọn thiết kế độc lập.

### Chọn `forEachOrdered` khi bắt buộc có thứ tự hành động

Ví dụ in kết quả báo cáo theo mã đơn đã sắp xếp:

```java
orders.parallelStream()
        .sorted(java.util.Comparator.comparing(Order::id))
        .forEachOrdered(order ->
                System.out.println(order.id()));
```

Đoạn này dùng `orders`/`Order` như chương trình hoàn chỉnh. Nếu yêu cầu chỉ là dữ liệu đã sắp xếp để trả về API, `sorted(...).toList()` có thể phù hợp hơn việc in trực tiếp.

### Không chọn cả hai khi cần tính toán kết quả

| Mục tiêu | API thường phù hợp hơn |
| --- | --- |
| Biến đổi phần tử | `map`, `flatMap` |
| Lấy danh sách | `toList`, `collect(Collectors.toList())` |
| Tính tổng | `mapToInt(...).sum()`, `reduce` |
| Đếm phần tử | `count()` |
| Kiểm tra có phần tử phù hợp | `anyMatch` |
| Lấy phần tử đầu tiên theo encounter order | `findFirst` |
| Nhóm phần tử theo khóa | `collect(Collectors.groupingBy(...))` |

Hãy phân biệt **thao tác kết thúc có side effect** với **thao tác kết thúc tạo một kết quả**. Việc Stream hỗ trợ `forEach` không có nghĩa mọi bài toán đều nên dùng nó.

## 13. So sánh `forEach`, `forEachOrdered` và `Iterable.forEach`

Một sự nhầm lẫn phổ biến là coi tất cả những lời gọi `forEach` là cùng API.

```java
List<String> names = List.of("Lan", "Minh", "An");

names.forEach(System.out::println);          // Iterable.forEach
names.stream().forEach(System.out::println); // Stream.forEach
names.stream().forEachOrdered(System.out::println);
```

`Iterable.forEach` là default method trên `Iterable` và sử dụng thứ tự iteration của iterable nếu thứ tự đó được chỉ định. `Stream.forEach` có contract riêng là không bảo đảm encounter order của terminal action, nhất là trong parallel pipeline. `Stream.forEachOrdered` mới là lựa chọn tường minh khi cần giữ encounter order.

`Collection.parallelStream()` tạo parallel stream từ collection; **nó không khiến phương thức `collection.forEach(...)` trên chính collection trở thành parallel**. Đừng suy ra môi trường thực thi chỉ từ chữ `forEach` mà không biết đối tượng nhận lời gọi là `Iterable` hay `Stream`.

## 14. Câu hỏi thường gặp

**1. “Stream tuần tự với `forEach` có luôn in theo thứ tự không?”** Trong ví dụ tuần tự từ `List`, hành động diễn ra khi duyệt theo thứ tự phần tử. Nhưng contract của `Stream.forEach` không đưa ra lời hứa encounter order giống `forEachOrdered`, nên mã cần thứ tự như một bất biến nên dùng `forEachOrdered` hoặc thu thập đầu ra có thứ tự.

**2. “`forEachOrdered` có biến một parallel stream thành sequential stream không?”** Không. Nó bắt action cuối tuân thủ encounter order, nhưng các phần khác của pipeline vẫn có thể thực thi song song.

**3. “Nếu dùng `HashSet` thì `forEachOrdered` có in đúng thứ tự thêm vào không?”** Không. `HashSet` không bảo đảm thứ tự thêm; nếu cần thứ tự thêm, dùng cấu trúc được thiết kế để giữ nó, hoặc chủ động `sorted`.

**4. “`forEachOrdered` có tự sort không?”** Không. Nó theo encounter order hiện có. Sắp xếp là công việc của `sorted` hoặc nguồn đã có thứ tự mong muốn.

**5. “`forEach` có trả lại stream để gọi `map` tiếp không?”** Không. Nó là terminal operation trả `void` và tiêu thụ stream.

**6. “Một thread trong parallel `forEachOrdered` xử lý toàn bộ action à?”** Không có bảo đảm như vậy. Action được thực hiện theo thứ tự encounter order nhưng không nhất thiết cùng một thread.

**7. “`forEachOrdered` có giúp `ArrayList.add` an toàn cho mọi parallel workload không?”** Không được suy luận như vậy cho các cập nhật đồng thời độc lập. Thực hiện terminal action có thứ tự là một thuộc tính của lời gọi đó; không bảo vệ collection khỏi các thread hoặc tác vụ ngoài khác cùng truy cập. Nếu cần collection kết quả, ưu tiên `toList`/`collect`.

**8. “Có thể dựa vào thứ tự log trong `map` khi cuối chuỗi dùng `forEachOrdered` không?”** Không. Thứ tự của action `forEachOrdered` không áp đặt thứ tự thực thi của mapper trung gian.

**9. “`parallelStream().forEach` có luôn nhanh hơn `forEachOrdered` không?”** Không thể khẳng định cho mọi bài toán. Tốc độ phụ thuộc workload, chi phí action, kích thước dữ liệu, mức độ cạnh tranh tài nguyên và khả năng chia pipeline. Cần benchmark trong điều kiện thực tế.

**10. “Muốn kiểm thử logic stream thì test stdout như thế nào?”** Với yêu cầu thứ tự, dùng nguồn ordered + `forEachOrdered`, hoặc tốt hơn kiểm thử dữ liệu bằng `toList`. Với `parallel forEach`, hãy kiểm thử thuộc tính như tập phần tử, tổng, số lượng, không so sánh thứ tự log ngẫu nhiên.

## 15. Bài tập thực hành

1. Dùng `List.of("C","A","B")`, gọi `parallelStream().forEachOrdered(System.out::println)`. Dự đoán thứ tự in và giải thích tại sao không tự thành A,B,C.
2. Thêm `sorted()` trước `forEachOrdered` của bài 1, dự đoán lại stdout.
3. Với `IntStream.rangeClosed(1,5).parallel()`, thử `forEach` nhiều lần và ghi nhận thứ tự thay đổi có thể quan sát. **Không** viết assert rằng bắt buộc có thay đổi thứ tự ở mọi lần chạy.
4. Tạo `ConcurrentLinkedQueue<Integer>`, dùng `parallel().forEach(queue::add)` rồi kiểm tra kích thước bằng 5 và tập phần tử sau khi sắp xếp là [1,2,3,4,5]. Không dựa vào thứ tự thêm.
5. Thay queue của bài 4 bằng `ArrayList` dùng chung. Phân tích nguy cơ race, rồi đổi cách thu thập sang `toList()`.
6. Dùng `orders` trong chương trình mẫu, tạo danh sách mã đơn bằng `map(Order::id).toList()`. Vì sao danh sách theo encounter order ngay cả khi dùng `parallelStream()`?
7. Viết pipeline `filter` chỉ lấy đơn có tiền trên 150, `sorted` theo mã rồi `forEachOrdered` in mã. Với dữ liệu mẫu, kết quả phải là A01 rồi A02.
8. Từ một `HashSet<String>`, viết code in kết quả theo thứ tự alphabet. Giải thích vai trò của `sorted()` và `forEachOrdered()`.
9. Viết một action ném `IllegalStateException` khi gặp mã A01; thử `forEachOrdered` trên stream tuần tự và xác định những thao tác trước đó đã diễn ra.
10. Giải thích tại sao `forEachOrdered` không thích hợp thay thế `mapToInt(...).sum()` chỉ để tính tổng tiền, ngay cả khi dùng `LongAdder` thread-safe.
11. Viết hai phép toán khác nhau: một phép tạo `List<String>` nhãn đơn hàng bằng `map(...).toList()`, một phép in các nhãn đó bằng `forEachOrdered`. Phân biệt giá trị trả về của từng terminal operation.
12. Dùng `List.of(3,1,2)` rồi gọi `unordered().parallel().forEachOrdered(...)`. Vì sao không nên ghi một expected stdout có thứ tự dựa trên nguồn ban đầu?

## 16. Checklist ứng dụng

- Mục tiêu có phải **hành động trả `void`** hay cần **trả kết quả dữ liệu**?
- Nguồn có encounter order không? Nếu không, có cần `sorted` hoặc cấu trúc dữ liệu khác không?
- Thứ tự **thực hiện action** có phải yêu cầu nghiệp vụ hay chỉ cần đủ phần tử?
- Nếu chạy `parallel`, action có chạm vào shared mutable state không? Đã có phương án thread-safe chưa?
- Có side effect trong `map`/`filter`/`peek` mà đang hiểu nhầm `forEachOrdered` sẽ sắp thứ tự chúng không?
- Có dùng `LongAdder`/collection ngoài chỉ để thay cho `sum`/`toList`/`collect` không?
- Nếu action lỗi giữa chừng, side effect đã xảy ra có cần xử lý phục hồi/idempotency không?
- Test có đang vô tình giả định một thứ tự cố định của `parallel forEach` hay `HashSet` không?
- Đã đánh giá chi phí giữ thứ tự nếu data lớn và workload song song chưa?

**Kết luận:** `forEach()` và `forEachOrdered()` đều là terminal operation nhận `Consumer` để thực hiện một hành động trên từng phần tử. `forEach` không bảo đảm encounter order; `forEachOrdered` giữ thứ tự action khi stream có encounter order, kể cả ở parallel stream, nhưng không làm cả pipeline chạy tuần tự. Khi cần **tính hoặc thu thập kết quả**, ưu tiên `map`/`reduce`/`toList`/`collect`; khi thực hiện side effect, hãy chủ động chọn chính sách thứ tự và bảo vệ trạng thái dùng chung.
