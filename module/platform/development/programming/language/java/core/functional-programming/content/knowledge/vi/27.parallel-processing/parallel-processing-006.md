# findAny(), forEach() và các kết quả không quyết định thứ tự trong Java Stream

## Mục tiêu bài học

Trong Java Stream, **thứ tự gặp phần tử**, **thứ tự callback được thực thi** và **thứ tự quan sát kết quả** là ba khái niệm khác nhau. Khi xử lý song song, một phần tử được xử lý trước không nhất thiết là phần tử đầu tiên trong nguồn. Hai terminal operation thể hiện điều này rất rõ:

- `findAny()` trả `Optional<T>` chứa **một phần tử bất kỳ** nếu nguồn không rỗng. Phương thức cố ý không hứa chọn phần tử nào.
- `forEach(action)` áp dụng một `Consumer<T>` cho các phần tử nhưng **không bảo đảm thứ tự action**, ngay cả khi nguồn có encounter order.

Để xử lý các yêu cầu có thứ tự, cần hiểu `findFirst()` và `forEachOrdered()`. Bài cũng so sánh `unordered()`, `parallelStream()`, `toList()`, các phép reduction và quản lý side effect chia sẻ giữa các thread.

Sau bài này bạn có thể chọn đúng API, viết kiểm thử không phụ thuộc lịch chạy thread, phân biệt kết quả nondeterministic hợp lệ với data race, và dùng ví dụ Java 17 để chứng minh các bảo đảm thật sự của Stream.

## 1. Encounter order, execution order và result order

### Encounter order: thứ tự logic

`List.of(1,2,3,4)`, `Stream.of(1,2,3,4)` và `IntStream.rangeClosed(1,4)` đều tạo nguồn có encounter order tương ứng 1,2,3,4. Encounter order là thuộc tính của nguồn/pipeline; nó không tự biến mất chỉ vì ta gọi `parallel()`.

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

Stream<Integer> sequential = numbers.stream();
Stream<Integer> parallel = numbers.parallelStream();
```

Cả hai nguồn đều có encounter order. Biến `parallel` biểu thị chế độ thực thi song song, **không có nghĩa bản thân các phần tử bị đảo ngẫu nhiên**.

### Execution order: thứ tự thực hiện

Khi pipeline xử lý song song, runtime có thể chia nguồn thành nhiều mảnh, chạy mapper/filter/action trên nhiều thread và ghép những phần kết quả. Không có bảo đảm chung rằng callback cho phần tử 1 sẽ chạy xong trước callback cho phần tử 2. Dù chương trình thử nghiệm luôn in theo thứ tự, đó vẫn có thể chỉ là tình cờ.

### Result order: thứ tự đầu ra

Một terminal operation có thể bảo toàn encounter order trong **kết quả** mặc dù các callback trung gian chạy song song. Ví dụ `numbers.parallelStream().map(n -> n * 2).toList()` giữ thứ tự `[2,4,6,8]` cho nguồn List có thứ tự. Điều này không cho phép suy ra `map` đã thực thi theo thứ tự 1,2,3,4.

| Phương thức | Bảo đảm quan trọng trên nguồn ordered | Không được giả định |
| --- | --- | --- |
| `findFirst()` | Chọn phần tử đầu theo encounter order | Luôn nhanh hơn `findAny` |
| `findAny()` | Chọn một phần tử hiện có, nếu có | Phần tử đầu hoặc được chọn ngẫu nhiên đều |
| `forEach()` | Áp dụng action cho phần tử, không có bảo đảm ordering | Log theo encounter order |
| `forEachOrdered()` | Action theo encounter order | Tất cả stage chỉ chạy trên một thread |
| `toList()` | List kết quả giữ encounter order | Mọi callback chạy theo encounter order |
| `unordered()` | Bỏ ràng buộc encounter order | Xáo trộn giá trị theo xác suất ngẫu nhiên |

## 2. findAny(): một phần tử bất kỳ

Chữ ký:

```java
Optional<T> findAny()
```

Đây là **short-circuiting terminal operation**. Khi Stream có phần tử, `findAny()` được phép chọn một phần tử không nhất thiết ở vị trí đầu. Nếu Stream rỗng, trả `Optional.empty()`.

```java
List<Integer> numbers = List.of(10, 20, 30);

Optional<Integer> any = numbers.parallelStream().findAny();
System.out.println(any.isPresent()); // true
```

Không có stdout đáng tin cho **giá trị cụ thể** `any`: các kết quả `Optional[10]`, `Optional[20]` và `Optional[30]` đều hợp lệ theo hợp đồng.

### Vì sao có tính không quyết định?

Một phép tìm cần bảo toàn phần tử đầu theo encounter order có thể phải phối hợp kết quả từ nhiều nhánh song song. `findAny` được phép chọn kết quả từ một nhánh đủ điều kiện mà không cần khẳng định đó là phần tử đầu. Nó tạo khả năng tối ưu hóa, **không hứa hiệu năng luôn tốt hơn**.

Ngay cả ở Stream tuần tự, `findAny` **không có hợp đồng trả phần tử đầu**. Một số implementation thường chọn phần tử đầu, nhưng mã ứng dụng không nên phụ thuộc hành vi quan sát này.

### Kiểm thử đúng

Với nguồn có dữ liệu, kiểm tra tính hợp lệ của kết quả:

```java
List<Integer> numbers = List.of(10, 20, 30);
int selected = numbers.parallelStream()
        .findAny().orElseThrow();

boolean valid = numbers.contains(selected); // true
```

Nếu pipeline còn `filter(n -> n % 2 == 0)`, test phải kiểm tra phần tử đã chọn thỏa predicate. Nếu nguồn rỗng, test `findAny().isEmpty()` là true. **Đừng assert một giá trị cụ thể** như 20 chỉ vì lần chạy trên máy hiện tại ra 20.

Không có hợp đồng phân phối ngẫu nhiên đều: `findAny` **không phải thuật toán random sampling**. Việc chạy 100 lần đều ra một ID không chứng minh Java chọn sai, bởi API không hứa fairness hay entropy.

### Null trong nguồn

`Optional` không thể chứa phần tử `null`. Nếu một terminal `findAny` chọn một phần tử null, `NullPointerException` có thể xảy ra. Tốt nhất xác định chính sách xử lý null ở nguồn và không biến null thành dữ liệu hợp lệ một cách ngầm định. Nếu nghiệp vụ được phép bỏ null, có thể áp dụng `filter(Objects::nonNull)`.

## 3. findFirst(): phần tử đầu chỉ khi có encounter order

Chữ ký:

```java
Optional<T> findFirst()
```

Trên nguồn có encounter order, nó chọn phần tử **đầu tiên sau các intermediate operations**.

```java
int first = List.of(1, 3, 4, 6, 8)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(first); // 4
```

Dù xử lý song song, `findFirst` phải trả 4 vì đó là phần tử chẵn đầu tiên theo encounter order.

Nếu gọi `unordered()` trước `findFirst`, ràng buộc này không còn:

```java
Optional<Integer> selected = List.of(1, 2, 3, 4)
        .parallelStream()
        .unordered()
        .findFirst();
```

Khi pipeline đã unordered, bất kỳ phần tử hiện có nào cũng có thể là kết quả. `unordered()` không có nghĩa xáo trộn: nó chỉ bỏ ràng buộc encounter order. Vì vậy giá trị 1 vẫn có thể được trả về trong nhiều lần chạy.

**Dùng `findFirst` khi nghiệp vụ cần phần tử đầu theo thứ tự đã chọn**; dùng `findAny` khi phần tử phù hợp nào cũng được. Với yêu cầu chọn phần tử ưu tiên cao nhất, hãy xác định comparator hoặc quy tắc min/max, không phụ thuộc nhánh CPU tìm thấy trước.

## 4. forEach(): action không được bảo đảm thứ tự

Chữ ký:

```java
void forEach(Consumer<? super T> action)
```

`forEach` là terminal operation dùng khi cần thực hiện action cho các phần tử. Với parallel stream:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);
numbers.parallelStream().forEach(System.out::println);
```

**Không có stdout theo thứ tự cố định** cho đoạn này. Những thứ tự khác nhau đều có thể xảy ra. Với pipeline tuần tự, nhiều implementation thực tế xử lý từ trái sang phải, nhưng API `forEach` vẫn không hứa bảo toàn encounter order; nếu thứ tự thuộc hợp đồng nghiệp vụ, dùng `forEachOrdered`.

### Data race khi sửa một ArrayList

Đây là mẫu không an toàn:

```java
List<Integer> results = new ArrayList<>();
numbers.parallelStream().forEach(results::add);
```

`ArrayList.add` không hỗ trợ nhiều thread cùng cập nhật không đồng bộ. Có thể mất phần tử hoặc gây lỗi. Đây là **lỗi đồng thời thật sự**, khác với việc log in ra không theo thứ tự hợp lệ.

Nếu cần một container concurrent để kiểm tra tác vụ đã thực hiện, có thể dùng:

```java
ConcurrentLinkedQueue<Integer> results =
        new ConcurrentLinkedQueue<>();

numbers.parallelStream().forEach(results::add);
```

Queue nhận các lệnh thêm đồng thời nhưng **thứ tự queue** có thể khác encounter order. Nếu mục đích chỉ là **thu các giá trị thành List**, dùng phép thu thập thay vì shared mutable container:

```java
List<Integer> values = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();
```

`toList` bảo toàn encounter order trên nguồn có thứ tự; kết quả List không cho chỉnh sửa cấu trúc.

### Bộ đếm chia sẻ

`int[] count = {0}; numbers.parallelStream().forEach(n -> count[0]++);` không an toàn: phép tăng không nguyên tử. `AtomicInteger` hoặc `LongAdder` xử lý một số yêu cầu concurrent, nhưng khi chỉ cần đếm phần tử thì `count()` là lựa chọn rõ hơn. Khi cần tổng, dùng `mapToLong(...).sum()` hoặc `reduce` có phép kết hợp phù hợp.

### Side effect không phải transaction

Nếu action ghi log, gọi API hoặc gửi email rồi một nhánh ném exception, Stream không tự rollback các side effect đã xảy ra. Lịch chạy các action không cố định, và các thao tác bên ngoài có thể đã diễn ra ở thread khác. Đừng đặt logic giao dịch quan trọng trong `forEach` nếu chưa thiết kế chính sách lỗi, idempotency và đồng bộ.

## 5. forEachOrdered(): thứ tự của action

Chữ ký:

```java
void forEachOrdered(Consumer<? super T> action)
```

Trên Stream có encounter order, `forEachOrdered` **thực thi các action theo đúng thứ tự đó**:

```java
List.of(1, 2, 3, 4)
        .parallelStream()
        .forEachOrdered(System.out::println);
```

Stdout có thứ tự 1, 2, 3, 4. Hợp đồng còn nêu rằng action cho một phần tử **happens-before** action cho phần tử kế tiếp theo encounter order. Tuy nhiên, không hứa mọi action chạy trên cùng thread; các stage trước terminal vẫn có thể được xử lý song song.

Bảo toàn thứ tự thường cần phối hợp và có thể giảm lợi ích của parallel. Không kết luận `forEachOrdered` luôn chậm hơn trong mọi trường hợp mà không đo; điều quan trọng là chọn đúng theo yêu cầu nghiệp vụ.

Khi Stream **unordered**, `forEachOrdered` không tự tạo thứ tự mong muốn. Nếu cần in theo tên tăng dần từ nguồn unordered, hãy `sorted()` trước:

```java
Set<String> names = Set.of("Lan", "An", "Mai");

names.parallelStream()
        .sorted()
        .forEachOrdered(System.out::println);
```

Đoạn này in An, Lan, Mai theo thứ tự tự nhiên của String; cần import `Set`.

## 6. Ví dụ Java 17 hoàn chỉnh, stdout ổn định

Một demo song song tốt không được tự bịa **giá trị findAny trả về** hoặc **thứ tự forEach thực hiện**. Ví dụ dưới đây thay thế những thông tin không được bảo đảm bằng kiểm tra thuộc tính: phần tử thuộc nguồn, đủ số phần tử và thứ tự được bảo đảm chỉ ở các API thích hợp.

Tạo file **`ParallelOrderDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 8)
                .boxed().toList();

        int first = numbers.parallelStream()
                .findFirst().orElseThrow();
        int any = numbers.parallelStream()
                .findAny().orElseThrow();
        boolean anyValid = numbers.contains(any);

        System.out.println("findFirst: " + first);
        System.out.println("findAny valid member: " + anyValid);
        System.out.println("Empty findAny: "
                + Stream.<Integer>empty().findAny().isEmpty());

        ConcurrentLinkedQueue<Integer> visited =
                new ConcurrentLinkedQueue<>();
        numbers.parallelStream().forEach(visited::add);
        boolean complete = visited.size() == numbers.size()
                && visited.stream().sorted().toList().equals(numbers);
        System.out.println("forEach visited all: " + complete);
        System.out.println("forEach count: " + visited.size());

        ConcurrentLinkedQueue<Integer> inOrder =
                new ConcurrentLinkedQueue<>();
        numbers.parallelStream().forEachOrdered(inOrder::add);
        System.out.println("forEachOrdered: " + List.copyOf(inOrder));

        List<Integer> doubled = numbers.parallelStream()
                .map(n -> n * 2).toList();
        System.out.println("parallel toList: " + doubled);

        boolean unorderedValid = numbers.parallelStream()
                .unordered().findFirst()
                .filter(numbers::contains).isPresent();
        System.out.println("unordered findFirst valid member: "
                + unorderedValid);

        boolean repeatedValid = IntStream.range(0, 100).allMatch(i ->
                numbers.contains(numbers.parallelStream()
                        .findAny().orElseThrow()));
        System.out.println("100 findAny checks valid: " + repeatedValid);
    }
}
```

Biên dịch, chạy với JDK 17 trở lên:

```bash
javac ParallelOrderDemo.java
java ParallelOrderDemo
```

**Stdout chính xác:**

```text
findFirst: 1
findAny valid member: true
Empty findAny: true
forEach visited all: true
forEach count: 8
forEachOrdered: [1, 2, 3, 4, 5, 6, 7, 8]
parallel toList: [2, 4, 6, 8, 10, 12, 14, 16]
unordered findFirst valid member: true
100 findAny checks valid: true
```

### Phân tích từng phần

1. `IntStream.rangeClosed(1,8).boxed().toList()` tạo List từ 1 đến 8 có thứ tự rõ.
2. `findFirst` trên ordered parallel stream trả 1. `findAny` chỉ phải trả **một số thuộc List**; test kiểm tra thuộc tính thay vì số cụ thể.
3. `Stream.empty().findAny()` cho Optional rỗng.
4. `forEach` thêm vào `ConcurrentLinkedQueue` an toàn với nhiều thread. Bài kiểm tra **đếm 8 phần tử** và **sắp xếp kết quả quan sát được để so với nguồn**, không giả định thứ tự mà các lệnh add đã xảy ra.
5. `forEachOrdered` bảo toàn encounter order; List copy từ queue là dãy 1 đến 8.
6. `map(...).toList()` trên ordered source giữ thứ tự output dù pipeline có thể xử lý phần tử đồng thời.
7. `unordered().findFirst()` không còn nghĩa vụ chọn số 1; kiểm tra membership mới là yêu cầu hợp lệ.
8. 100 lượt `findAny` đều chọn giá trị trong nguồn. Điều đó **không đòi** các lượt trả ra nhiều giá trị khác nhau.

Chương trình dùng giá trị cố định, không đọc mạng, không in tên thread và không dựa vào lịch chạy. Ví dụ đã được biên dịch bằng `javac --release 17` và chạy với stdout trên.

## 7. Short-circuit và các side effect trong pipeline

`findAny`, `findFirst` là terminal operation **short-circuit**: không cần xử lý hết các phần tử để có một kết quả. Trong parallel pipeline, một số nhánh khác có thể vẫn đã thực hiện các callback trước khi kết quả được chọn. Vì vậy không được đưa một side effect nghiệp vụ bắt buộc vào `filter` hoặc `map` rồi kỳ vọng nó luôn chạy đúng một lần cho mọi phần tử.

Ví dụ minh họa anti-pattern:

```java
Optional<Integer> found = IntStream.rangeClosed(1, 1000)
        .parallel()
        .filter(n -> {
            audit(n); // Đây là tác dụng phụ không nên dựa vào.
            return n % 7 == 0;
        })
        .boxed()
        .findAny();
```

Đây không phải chương trình độc lập; `audit` cần được định nghĩa. Nếu bắt buộc audit **tất cả** các phần tử, `findAny` sai yêu cầu vì nó được phép dừng sớm. Cần tách công việc audit khỏi phép chọn phần tử hoặc dùng cơ chế xử lý riêng có bảo đảm phù hợp.

Tương tự, `peek` không nên được dùng để thực hiện thanh toán, cập nhật dữ liệu bắt buộc hay gửi sự kiện mà bạn cho rằng phải chạy trên mọi phần tử: các tối ưu hóa và short-circuit có thể thay đổi số lượt callback thực tế được quan sát.

## 8. Chọn API và kiểm thử theo hợp đồng

| Nhu cầu | API phù hợp | Bất biến để kiểm tra |
| --- | --- | --- |
| Tìm bất kỳ bản ghi nào thỏa điều kiện | `filter(...).findAny()` | Phần tử thuộc nguồn và thỏa predicate |
| Tìm bản ghi đầu sau khi áp dụng thứ tự | `findFirst()` | Là phần tử đầu theo encounter order |
| Tìm min/max theo thuộc tính | `min/max(comparator)` | Thỏa quy tắc so sánh |
| Chạy action không phụ thuộc thứ tự | `forEach()` | Từng phần tử cần xử lý, action thread-safe |
| Chạy action theo thứ tự nguồn | `forEachOrdered()` | Action đúng encounter order |
| Thu một List có thứ tự | `toList()` trên ordered source | Kết quả bằng sequence mong muốn |
| Đếm, cộng hoặc gom nhóm | `count/sum/collect` | Kết quả reduction chính xác |
| Bỏ ordering vì không cần thiết | `unordered()` | Nội dung đúng, không assert thứ tự |

### Những tình huống cần đặc biệt cẩn thận

- Nguồn `Set` không luôn có encounter order; `findFirst` không tự chọn bản ghi “đầu tiên theo tên”.
- `findAny` không phải bộ tạo số ngẫu nhiên; đừng dùng để chọn ngẫu nhiên công bằng.
- `forEachOrdered` bảo đảm thứ tự action khi nguồn ordered, nhưng không tự đồng bộ toàn bộ công việc khác ở bên ngoài.
- Một `Stream` chỉ được terminal operation tiêu thụ một lần; không gọi `findAny` rồi tiếp tục `forEach` trên cùng object Stream.
- `Optional.empty()` cần được xử lý: `orElse`, `orElseThrow` hoặc kiểm tra `isPresent` theo chính sách.
- Nếu callback ném ngoại lệ, không giả định các side effect ở thread khác được rollback.
- Để tối ưu hiệu năng, đo benchmark đúng trên nguồn/khối lượng thực. `parallel()` không tự động nhanh hơn, còn `forEachOrdered` có thể tăng chi phí phối hợp.

## 9. Những lỗi phổ biến

1. Kiểm thử `findAny()` bằng một giá trị cố định.
2. Tưởng `findAny` luôn trả phần tử đầu khi tuần tự.
3. Tưởng `findAny` phân phối kết quả ngẫu nhiên đều.
4. Đồng nhất `parallel` với `unordered`.
5. Dùng thứ tự log của `forEach` làm encounter order.
6. Cho nhiều thread ghi vào cùng `ArrayList` từ `forEach`.
7. Dùng biến đếm chia sẻ không đồng bộ trong callback.
8. Nghĩ `forEachOrdered` buộc toàn pipeline chạy trên một thread.
9. Dùng `forEachOrdered` trên unordered source rồi yêu cầu thứ tự tự nhiên.
10. Dùng `findAny` khi hợp đồng cần bản ghi đầu hoặc ưu tiên cao nhất.
11. Quên xử lý nguồn rỗng và `Optional.empty()`.
12. Không xử lý phần tử null khi `findAny/findFirst` có thể chọn nó.
13. Đưa logging bắt buộc vào `filter` rồi kết thúc bằng `findAny`.
14. Nghĩ `toList` trên ordered parallel stream có output vô thứ tự.
15. Dùng một Stream cho hai terminal operations.
16. Cho rằng chạy thử 100 lần đều ra cùng phần tử là bảo đảm API.

## 10. Bài tập tự luyện

**Bài 1.** Với `List.of("A","B","C").parallelStream().findAny()`, viết assert đúng mà không dự đoán phần tử được chọn.

**Bài 2.** Với `List.of(1,3,4,6,8)`, tìm số chẵn đầu tiên bằng parallel stream. Giá trị được bảo đảm là gì?

**Bài 3.** Với `IntStream.rangeClosed(1,100)`, tìm số chia hết cho 7 bất kỳ. Kiểm tra những thuộc tính nào?

**Bài 4.** Vì sao `parallelStream().forEach(System.out::println)` không có một thứ tự stdout cố định?

**Bài 5.** Thay cách dùng `parallelStream().forEach(sharedArrayList::add)` bằng thao tác thu thập an toàn hơn.

**Bài 6.** Khi một nguồn Set không có thứ tự, cần thêm thao tác gì để in chuỗi theo alphabet với `forEachOrdered`?

**Bài 7.** Sau `unordered()`, `findFirst()` có buộc trả phần tử đầu của List ban đầu không?

**Bài 8.** Vì sao `forEachOrdered` vẫn có thể có upstream parallel và action chạy ở nhiều thread khác nhau?

**Bài 9.** Một pipeline `filter` ghi sự kiện trong callback rồi gọi `findAny`. Vì sao không thể bảo đảm mọi phần tử đều được ghi sự kiện?

**Bài 10.** Nếu chỉ cần đếm số phần tử thỏa điều kiện, tại sao `filter(predicate).count()` rõ hơn một shared counter?

**Bài 11.** `findAny` trên Stream rỗng trả gì? Điều gì xảy ra nếu gọi `orElseThrow()` ngay?

**Bài 12.** `parallelStream().map(...).toList()` có giữ encounter order từ List không? Thứ tự callback có được bảo đảm không?

### Đáp án gợi ý

1. Kiểm tra Optional có giá trị và phần tử nằm trong List.
2. `4`, vì nguồn ordered và `findFirst` chọn chẵn đầu tiên theo encounter order.
3. Kết quả thuộc 1..100 và `n % 7 == 0`.
4. Thứ tự action và lịch thread không được bảo đảm.
5. `numbers.parallelStream().toList()` hoặc `collect(...)` phù hợp yêu cầu.
6. `sorted()` trước `forEachOrdered`.
7. Không; ordering constraint đã được gỡ.
8. Bảo đảm áp dụng cho thứ tự action, không bắt buộc toàn pipeline một thread.
9. `findAny` short-circuit, có thể không duyệt mọi phần tử.
10. `count` là terminal reduction, không có race trên biến chia sẻ.
11. `Optional.empty()`; `orElseThrow()` ném `NoSuchElementException`.
12. Giữ output order nếu nguồn ordered; thứ tự callback trung gian không được bảo đảm.

## Kết luận

`findAny()` và `forEach()` được thiết kế để **không ràng buộc lựa chọn phần tử hay thứ tự hành động** theo cách mà nhiều người vô tình giả định. Đây là quyền tự do hợp lệ trong Java Stream, đặc biệt hữu ích cho tính toán song song. Nếu nghiệp vụ cần thứ tự, dùng `findFirst()`, `forEachOrdered()` hoặc kết quả `toList()` trên ordered stream.

Kiểm thử không quyết định thứ tự phải dựa vào **bất biến**, như phần tử thuộc nguồn, thỏa predicate, đủ số lượng hoặc nội dung Map/List đúng, thay vì dự đoán lịch chạy. Đồng thời, tránh shared mutable state và side effect không được bảo đảm: một thứ tự log khác mong đợi có thể hợp lệ, nhưng mất dữ liệu do data race thì không.
