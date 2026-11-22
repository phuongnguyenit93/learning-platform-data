# Chuyển pipeline tuần tự sang song song mà vẫn giữ đúng ngữ nghĩa

Trong chương **Ngữ nghĩa xử lý song song** của **Java Stream API**, đổi từ `stream()` sang `parallelStream()` hoặc thêm `parallel()` là một thao tác cú pháp rất nhỏ. Tuy nhiên, chuyển đổi thành công về mặt kỹ thuật **không đồng nghĩa** pipeline vẫn đúng về mặt nghiệp vụ. Cách chia nguồn, thứ tự thực thi các lambda, số lần gọi một thao tác và thứ tự kết hợp các kết quả trung gian đều có thể thay đổi.

Mục tiêu của bài này là biết **khi nào có thể chuyển pipeline tuần tự sang song song mà vẫn giữ ngữ nghĩa mong muốn**. Ta sẽ kiểm tra hợp đồng nguồn và Spliterator, tính độc lập của hàm xử lý, quy tắc về thứ tự (*encounter order*), phép `reduce`/`collect`, dữ liệu số học và đặc biệt là những side effect không an toàn. Từ đó, ta có thể đánh giá đúng cả **tính chính xác** và **hiệu năng**, thay vì chỉ bật `parallel()` với kỳ vọng chạy nhanh hơn.

Các nguyên tắc này áp dụng cho pipeline gồm `filter`, `map`, `flatMap`, `reduce`, `collect`, các collector nhiều tầng, Spliterator và những thao tác mở rộng như Stream Gatherers: song song hóa chỉ an toàn khi ngữ nghĩa của từng tầng chịu được cách thực thi chia phần và kết hợp.

## 1. Song song hóa thay đổi điều gì?

Ví dụ một pipeline tuần tự:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> squared = values.stream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * n)
        .toList();

System.out.println(squared); // [1, 9, 25]
~~~

Chỉ thay nguồn Stream:

~~~java
List<Integer> squared = values.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * n)
        .toList();

System.out.println(squared); // [1, 9, 25]
~~~

Pipeline dùng các hàm `filter`/`map` không phụ thuộc trạng thái chia sẻ; nguồn `List` có encounter order; `toList()` giữ thứ tự đó. Vì vậy, **giá trị và thứ tự của danh sách kết quả** được bảo toàn trong ví dụ.

Nhưng điều sau **không được bảo đảm**:

~~~text
Phần tử 1 được xử lý trước phần tử 3.
Thread xử lý phần tử 5 phải là thread xử lý phần tử 4.
Mỗi lời gọi map/filter xảy ra đúng theo thứ tự của List.
Mỗi phần tử đều được xử lý bởi một thread riêng.
~~~

Stream API có thể chia nguồn thành các phần, xử lý trên những worker khác nhau và ghép kết quả theo hợp đồng của terminal operation. Thứ tự thực thi bên trong **không phải** encounter order, dù kết quả cuối cùng có encounter order.

> **Nguyên tắc:** Kiểm tra **kết quả được đặc tả**, không kiểm tra thứ tự nội bộ mà implementation tình cờ thực hiện.

## 2. Phân biệt thứ tự encounter, thứ tự xử lý và thứ tự kết quả

Ba khái niệm rất dễ bị đánh đồng:

| Khái niệm | Ý nghĩa | Có được bảo đảm khi parallel? |
| --- | --- | --- |
| *Encounter order* | Thứ tự logic các phần tử của nguồn/pipeline nếu nguồn có thứ tự | Được giữ bởi các thao tác có hợp đồng duy trì encounter order. |
| Thứ tự xử lý (*execution order*) | Lúc nào và bởi thread nào mapper/predicate chạy | Nói chung **không** được bảo đảm. |
| Thứ tự kết quả | Thứ tự quan sát ở đầu ra terminal operation | Phụ thuộc hợp đồng của terminal operation và việc nguồn có thứ tự hay không. |

Với một `List`:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "An", "Minh", "Huy");

List<String> result = names.parallelStream()
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, AN, MINH, HUY]
~~~

`toList()` trả các phần tử theo encounter order của nguồn. Điều này **không có nghĩa** các lời gọi `toUpperCase` được thực thi lần lượt Lan → An → Minh → Huy.

Nếu nguồn không có encounter order được cam kết, ví dụ Stream đến từ một số loại `Set`, hoặc pipeline gọi `unordered()`, không được dựa vào thứ tự đầu ra mặc định. Nếu nghiệp vụ yêu cầu thứ tự theo mã, ngày hoặc mức ưu tiên, hãy xác định rõ tiêu chí và dùng `sorted(...)` ở vị trí thích hợp.

## 3. Checklist trước khi đổi stream() thành parallelStream()

Trước khi sửa mã, hãy trả lời những câu hỏi sau:

1. **Nguồn có thể chia phần an toàn không?** Spliterator có hỗ trợ `trySplit()` hợp lý; không bị thay đổi trái hợp đồng trong lúc duyệt?
2. **Các lambda có không can thiệp nguồn (*non-interfering*) không?** Không thêm/xóa phần tử nguồn trong quá trình duyệt nếu nguồn không hỗ trợ thay đổi đồng thời theo hợp đồng.
3. **Các lambda có tránh trạng thái dùng chung (*stateless*) không?** Kết quả của mỗi `map`/`filter` không dựa vào biến ngoài đang thay đổi bởi những phần tử khác.
4. **Thứ tự có quan trọng không?** Nếu quan trọng, terminal operation và intermediate operation có giữ encounter order cần thiết không?
5. **Phép tổng hợp có hợp lệ khi chia/ghép không?** `identity` đúng, `combiner` có tính kết hợp, accumulator tương thích; collector tuân thủ hợp đồng song song?
6. **Có yêu cầu giá trị số học chính xác tuyệt đối không?** Floating-point và làm tròn giữa các bước có thể thay đổi kết quả theo thứ tự nhóm.
7. **Có side effect, I/O hoặc transaction không?** Song song không tự cung cấp đồng bộ hóa, thứ tự commit hay rollback.
8. **Có đáng song song hóa không?** Dữ liệu, chi phí xử lý và cách chia nguồn có đủ lớn để bù overhead?

Nếu chưa thể trả lời các câu hỏi về **tính đúng đắn**, đừng dùng kết quả benchmark như bằng chứng rằng mã đã an toàn. Một pipeline chạy nhanh nhưng đôi khi thiếu bản ghi vẫn là pipeline sai.

## 4. Stateless và non-interfering: điều kiện nền tảng

Một `map` hoặc `filter` phù hợp để chạy song song thường chỉ phụ thuộc vào **phần tử đang xử lý** và dữ liệu bất biến được dùng để cấu hình phép biến đổi.

~~~java
import java.util.List;

List<String> codes = List.of(" pen ", "book", "pad");

List<String> normalized = codes.parallelStream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();

System.out.println(normalized); // [PEN, BOOK, PAD]
~~~

Mỗi mapper là một phép biến đổi độc lập trên một chuỗi. Không có biến đếm hoặc Map mutable bị nhiều tác vụ cùng cập nhật.

### Lỗi: dùng biến đếm chung để đánh số

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

List<String> names = List.of("A", "B", "C", "D");

AtomicInteger counter = new AtomicInteger();

List<String> numbered = names.parallelStream()
        .map(name -> counter.incrementAndGet() + ":" + name)
        .toList();
~~~

`AtomicInteger` làm phép tăng số an toàn ở mức cập nhật nguyên tử, nhưng **không bảo đảm số thứ tự gắn với encounter order**. Chương trình có thể trả danh sách theo thứ tự tên `A, B, C, D` mà số đánh lên từng tên không theo thứ tự `1, 2, 3, 4`.

Thay một biến `int[]` dùng chung bằng `AtomicInteger` có thể sửa một race condition ở cấp phép tăng, **không tự sửa ngữ nghĩa** của pipeline.

Nếu cần đánh số theo vị trí, hãy lấy chỉ số từ nguồn có thứ tự và kích thước xác định:

~~~java
import java.util.stream.IntStream;

List<String> numbered = IntStream.range(0, names.size())
        .parallel()
        .mapToObj(i -> (i + 1) + ":" + names.get(i))
        .toList();

System.out.println(numbered); // [1:A, 2:B, 3:C, 4:D]
~~~

Ở đây chỉ số `i` là **dữ liệu của phần tử**, không phải thứ tự một tác vụ tình cờ chạy đến. Mẫu này phù hợp khi nguồn hỗ trợ truy cập theo chỉ số ổn định, như `List.of(...)` trong ví dụ, và không bị sửa trong khi duyệt.

## 5. Không sửa nguồn khi đang duyệt

Một pipeline không can thiệp nguồn tránh thay đổi dữ liệu đầu vào theo cách phá hợp đồng Iterator hoặc Spliterator.

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Sai: thay đổi chính nguồn trong khi Stream đang duyệt.
numbers.parallelStream()
        .forEach(n -> {
            if (n % 2 == 0) {
                numbers.remove(n);
            }
        });
~~~

Hành vi có thể bao gồm `ConcurrentModificationException`, bỏ sót dữ liệu hoặc kết quả không được bảo đảm. Điều này không trở thành hợp lệ chỉ vì một lần chạy không phát sinh exception.

Nếu mục tiêu là loại số chẵn, hãy tạo đầu ra mới:

~~~java
List<Integer> oddNumbers = numbers.parallelStream()
        .filter(n -> n % 2 != 0)
        .toList();
~~~

Nếu ứng dụng cần cập nhật collection nguồn sau đó, thực hiện thao tác chỉnh sửa **tách khỏi lượt duyệt** theo cơ chế phù hợp. Nguồn có đặc tính `CONCURRENT` có thể hỗ trợ một số thay đổi đồng thời theo hợp đồng riêng, nhưng không nên mặc định mọi `ArrayList` hay `HashMap` đều cho phép điều đó.

## 6. Side effect trong forEach: đúng ở đâu, sai ở đâu?

`forEach` là terminal operation cho hành động trên từng phần tử; nó không tự xây dựng một collection kết quả và không bảo đảm thứ tự gọi trong pipeline song song.

~~~java
import java.util.List;

List<String> items = List.of("A", "B", "C", "D");

items.parallelStream()
        .forEach(System.out::println);
// Có thể in theo một thứ tự khác A, B, C, D.
~~~

### Sai: ghi vào ArrayList chia sẻ

~~~java
import java.util.ArrayList;

List<String> output = new ArrayList<>();

items.parallelStream()
        .forEach(output::add); // Không an toàn.
~~~

`ArrayList` không bảo đảm cập nhật đồng thời an toàn. Lỗi có thể là mất phần tử, ghi không nhất quán hoặc hành vi khó tái hiện.

### Đúng: dùng terminal operation có hợp đồng thu thập

~~~java
List<String> output = items.parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(output); // [a, b, c, d]
~~~

`toList()` giữ encounter order của Stream có thứ tự và trả danh sách không sửa đổi được (Java 16+). Nếu cần danh sách mutable, dùng collector yêu cầu container mới:

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<String> editable = items.parallelStream()
        .map(String::toLowerCase)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Khi dùng `collect` chuẩn, Stream tự điều phối vùng tích lũy và việc ghép kết quả theo hợp đồng collector; không cần cho nhiều tác vụ cùng sửa một `ArrayList` bên ngoài.

### Thread-safe chưa chắc đúng ngữ nghĩa

Dùng `Collections.synchronizedList(...)` có thể loại bỏ race condition của từng lời gọi `add`, nhưng **thứ tự gọi `add` vẫn không phải encounter order**. Đồng bộ hóa cũng có thể làm mất lợi ích song song.

Nếu yêu cầu là tạo danh sách có thứ tự, `map(...).toList()` hoặc `collect(...)` phù hợp hơn. Nếu yêu cầu là side effect như gửi thông báo, hãy xem xét riêng idempotency, thứ tự và cơ chế retry; Stream không cung cấp hợp đồng giao dịch cho tác vụ ngoài.

## 7. forEachOrdered và giới hạn của bảo đảm thứ tự

Nếu bắt buộc thực hiện một hành động theo encounter order, có thể dùng `forEachOrdered`:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Minh", "An");

names.parallelStream()
        .forEachOrdered(System.out::println);

// Lan
// Minh
// An
~~~

`forEachOrdered` đảm bảo thực hiện action theo encounter order của **Stream có thứ tự**. Nó cũng thiết lập quan hệ *happens-before* giữa các lần action theo thứ tự đó. Tuy nhiên:

- Nó **không** bảo đảm toàn bộ các thao tác `map`/`filter` trước đó chạy tuần tự theo thứ tự nguồn.
- Nó **không** bảo đảm tất cả action chạy trên cùng một thread.
- Việc áp thứ tự có thể làm giảm cơ hội tăng tốc vì những tác vụ cần phối hợp.
- Với Stream không có encounter order, không thể đòi một thứ tự logic mà nguồn chưa công bố.

Nếu chỉ cần một `List` để sử dụng tiếp, việc thu bằng `toList()` thường thể hiện đúng ý định hơn phát side effect bằng `forEachOrdered`.

## 8. findFirst, findAny và các thao tác có khả năng dừng sớm

Chuyển sang song song đặc biệt cần để ý **kết quả có thể được phép thay đổi theo hợp đồng API**.

~~~java
import java.util.List;
import java.util.Optional;

List<String> names = List.of("A", "B", "C");

Optional<String> first = names.parallelStream().findFirst();
Optional<String> any = names.parallelStream().findAny();

System.out.println(first.orElseThrow()); // A
// any có thể là A, B hoặc C.
~~~

`findFirst()` lấy phần tử đầu theo encounter order nếu Stream có thứ tự. `findAny()` chủ động cho phép chọn phần tử bất kỳ để hỗ trợ thực thi song song linh hoạt hơn.

| Terminal operation | Tiêu chí dừng/kết quả | Khi dùng parallel |
| --- | --- | --- |
| `findFirst()` | Phần tử đầu theo encounter order; với unordered thì không có thứ tự đầu xác định | Có thể phải phối hợp để chọn đúng phần tử đầu. |
| `findAny()` | Một phần tử bất kỳ trong kết quả | Có thể trả phần tử khác giữa các lần chạy. |
| `anyMatch(p)` | Có ít nhất một phần tử thỏa `p` | Kết quả boolean vẫn theo logic khi predicate thuần. |
| `allMatch(p)` | Mọi phần tử đều thỏa `p` | Kết quả boolean vẫn theo logic khi predicate thuần. |
| `noneMatch(p)` | Không phần tử nào thỏa `p` | Kết quả boolean vẫn theo logic khi predicate thuần. |

Các phép match có khả năng short-circuit nhưng **không cam kết số lần gọi predicate** hoặc thứ tự các phần tử được kiểm tra. Thậm chí sau khi đã tìm thấy bằng chứng đủ để trả kết quả, một số tác vụ đang chạy có thể còn được hoàn thành hoặc bị hủy theo cơ chế implementation.

Vì vậy, đừng gắn side effect cần được gọi **đúng một lần cho mỗi phần tử** vào predicate của `anyMatch`, `allMatch` hay `findAny`.

## 9. limit, skip, takeWhile, dropWhile: giữ ý nghĩa về tiền tố

Với Stream có encounter order, những thao tác lấy/bỏ tiền tố phải tôn trọng thứ tự logic.

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> firstFive = IntStream.range(0, 100)
        .parallel()
        .limit(5)
        .boxed()
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

`limit(5)` trên Stream có thứ tự trả **năm phần tử đầu theo encounter order**, không phải năm phần tử được thread bất kỳ xử lý nhanh nhất. `skip(5)` tương tự phải bỏ năm phần tử đầu theo thứ tự nguồn. Việc tuân thủ điều này có thể tạo chi phí đồng bộ, đặc biệt trên Stream song song có thứ tự.

~~~java
List<Integer> afterSkip = IntStream.range(0, 10)
        .parallel()
        .skip(5)
        .boxed()
        .toList();

System.out.println(afterSkip); // [5, 6, 7, 8, 9]
~~~

Từ Java 9, `takeWhile` và `dropWhile` cũng có quy tắc về **tiền tố** khi nguồn có thứ tự:

~~~java
List<Integer> prefix = IntStream.range(0, 10)
        .parallel()
        .takeWhile(n -> n < 4)
        .boxed()
        .toList();

System.out.println(prefix); // [0, 1, 2, 3]
~~~

Nếu gọi `unordered()`, các thao tác như `limit`, `takeWhile` hoặc `dropWhile` có thể có hành vi khác do **không còn ràng buộc tiền tố của encounter order**. `unordered()` không phải một “nút tăng tốc vô hại”; nó thay đổi những bảo đảm mà chương trình được dựa vào.

Với nguồn vốn không có thứ tự, nếu chỉ cần **bất kỳ N phần tử** để thử nghiệm hoặc thống kê lấy mẫu mà không cần đúng N phần tử đầu, việc bỏ ràng buộc thứ tự có thể hợp lý. Ngược lại, nếu yêu cầu “100 đơn hàng đầu theo thời gian”, phải có thứ tự thời gian được xác định và không được tự ý bỏ đi.

## 10. reduce: identity, tính kết hợp và combiner

Đối với `reduce`, điều kiện lớn nhất để chạy song song đúng là **phép kết hợp có tính kết hợp (*associative*)** với identity phù hợp.

Ví dụ tổng số nguyên từ một nguồn hữu hạn:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

int sequential = values.stream()
        .reduce(0, Integer::sum);

int parallel = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sequential); // 10
System.out.println(parallel);   // 10
~~~

Với kiểu `int`, phép cộng có quy tắc tràn số nguyên theo Java; nếu tổng có thể vượt giới hạn, cần chọn kiểu dữ liệu phù hợp hoặc kiểm soát tràn theo nghiệp vụ. Dù sao, `Integer::sum` là phép kết hợp phù hợp cho reduction theo ngữ nghĩa phép cộng số nguyên Java.

### Identity sai khiến kết quả bị cộng nhiều lần

~~~java
// Sai: 10 không phải identity của phép cộng.
int bad = values.parallelStream()
        .reduce(10, Integer::sum);
~~~

Ở chế độ tuần tự, đoạn này tính `10 + 1 + 2 + 3 + 4 = 20`. Nhưng khi chia phần, mỗi nhánh có thể bắt đầu từ identity `10`, dẫn đến nhiều lần cộng khoản 10; kết quả không được bảo đảm theo mục đích “cộng 10 một lần”.

Cách đúng:

~~~java
int result = 10 + values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(result); // 20
~~~

Identity phải **trung hòa với combiner**; khoản cộng thêm phục vụ nghiệp vụ nên đặt ngoài reduction nếu đó không phải identity.

### Phép trừ không có tính kết hợp

~~~java
// Không dùng mẫu này để mong kết quả giống tuần tự:
int result = values.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Với phép trừ, `(a - b) - c` khác `a - (b - c)`. Thay đổi cách nhóm phần tử có thể thay đổi kết quả, vì vậy không thỏa hợp đồng của reduction song song.

Nếu yêu cầu là lấy số đối của tổng, hãy diễn đạt bằng phép cộng kết hợp rồi đổi dấu:

~~~java
int negativeSum = -values.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(negativeSum); // -10
~~~

Trường hợp `Integer.MIN_VALUE` và số học tràn cần được thiết kế riêng nếu nghiệp vụ không cho phép tràn; việc đổi phép toán không tự giải quyết mọi giới hạn miền giá trị.

## 11. reduce ba tham số: accumulator phải tương thích combiner

Overload:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

Cho phép chuyển `Stream<T>` thành một kết quả `U` khác kiểu phần tử.

~~~java
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

long countLetters = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(countLetters); // 13
~~~

Ba điều kiện cần ghi nhớ:

~~~text
combine(identity, u) = u

combine(combine(a, b), c) = combine(a, combine(b, c))

combine(u, accumulate(identity, t)) = accumulate(u, t)
~~~

Điều kiện thứ nhất là **identity trung hòa**, thứ hai là **tính kết hợp của combiner**, thứ ba là **tính tương thích giữa accumulator và combiner**. Với tổng độ dài chuỗi, tất cả đều dựa trên phép cộng.

Lỗi dễ xảy ra là dùng accumulator để tính tổng nhưng combiner để nhân, hoặc dùng identity `10` cho phép cộng. Chạy tuần tự có thể trông đúng vì combiner ít được quan sát, nhưng song song có thể ghép ra kết quả khác.

Đối với bài toán chỉ có một chỉ số, một primitive stream như `mapToLong(String::length).sum()` thường ngắn và tránh boxing hơn. Overload ba tham số hữu ích khi muốn xây một **kết quả bất biến gồm nhiều trường** và có hàm ghép hai kết quả trung gian rõ ràng.

## 12. Floating-point và làm tròn: "đúng" phụ thuộc hợp đồng số học

Không phải mọi phép cộng đều có cùng tính chất khi thực hiện trên máy.

### 12.1. Cộng double có thể cho khác biệt nhỏ

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Dù phép cộng số thực toán học có tính kết hợp, cộng `double` chịu làm tròn theo biểu diễn nhị phân nên **không có tính kết hợp tuyệt đối**. Khi Stream thay đổi cách phân chia và gộp các tổng một phần, kết quả có thể khác ở những chữ số cuối.

~~~java
double total = valuesAsDoubles.parallelStream()
        .mapToDouble(Double::doubleValue)
        .sum();
~~~

Ví dụ trên giả định `valuesAsDoubles` là một collection `Double`. `DoubleStream.sum()` có thể sử dụng chiến lược cải thiện độ chính xác, nhưng không nên xem tổng dấu phẩy động là bất biến từng bit giữa mọi thứ tự tính hoặc mọi phương án triển khai. Cần xác định sai số chấp nhận được nếu nghiệp vụ sử dụng floating-point.

### 12.2. Với tiền, dùng BigDecimal và chỉ làm tròn tại ranh giới nghiệp vụ

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

List<BigDecimal> amounts = List.of(
        new BigDecimal("0.005"),
        new BigDecimal("0.005"),
        new BigDecimal("0.005")
);

BigDecimal exact = amounts.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal payable = exact.setScale(2, RoundingMode.HALF_UP);

System.out.println(payable); // 0.02
~~~

`BigDecimal::add` không dùng `MathContext` thực hiện phép cộng thập phân chính xác. Do đó có thể chia nhóm rồi cộng các tổng một phần mà không mất giá trị số học. Làm tròn **sau reduction** phù hợp với chính sách “cộng chính xác, làm tròn tổng một lần”.

Nếu ứng dụng làm tròn từng phần tử trước khi thu, kết quả có thể khác (ba lần `0.005 -> 0.01` cho tổng `0.03`). Hai chính sách đều có thể hợp lệ trong những nghiệp vụ khác nhau, nhưng không được hoán đổi khi tối ưu.

**Tránh làm tròn trong combiner/accumulator** nếu muốn phép cộng có tính kết hợp theo giá trị số học. Mỗi phép làm tròn trung gian có thể làm kết quả phụ thuộc cách nhóm phần tử.

## 13. collect: phân biệt mutable reduction và trạng thái chia sẻ

Một collector được thiết kế để **tích lũy** dữ liệu, có thể dùng container mutable nội bộ. Điều này khác với việc tự tạo một container chung rồi sửa trong `forEach`.

Ví dụ gom sản phẩm theo nhóm:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String sku, String category) {}

List<Product> products = List.of(
        new Product("PEN", "OFFICE"),
        new Product("BOOK", "EDUCATION"),
        new Product("PAD", "OFFICE")
);

Map<String, List<Product>> byCategory = products.parallelStream()
        .collect(Collectors.groupingBy(Product::category));

System.out.println(byCategory.get("OFFICE").size()); // 2
~~~

`groupingBy` là collector chuẩn, có thể kết hợp kết quả trung gian theo hợp đồng. Nhưng dùng `groupingBy` **không có nghĩa** Map kết quả là một Map đồng thời, và cũng không bảo đảm kiểu Map hoặc thread-safety cho các cập nhật mà caller thực hiện về sau.

Khi cần một `List`, chọn:

~~~java
List<String> codes = products.parallelStream()
        .map(Product::sku)
        .toList();
~~~

Hoặc dùng collector yêu cầu danh sách có thể chỉnh sửa:

~~~java
import java.util.ArrayList;

ArrayList<String> editableCodes = products.parallelStream()
        .map(Product::sku)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

### Sai: reduce với cùng một container mutable

~~~java
// Sai với parallel reduction: identity mutable có thể dùng chung.
List<String> wrong = products.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, p) -> {
                    list.add(p.sku());
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

`reduce` ba tham số có hợp đồng accumulator trả về kết quả `U` mới theo phép kết hợp; dùng cùng một identity mutable rồi sửa nó phá điều kiện cần thiết khi các nhánh ghép kết quả. Chọn `collect` cho cấu trúc mutable hoặc một kiểu kết quả immutable phù hợp với `reduce`.

## 14. groupingByConcurrent, toConcurrentMap và đánh đổi về thứ tự

Java cung cấp collector để khai thác tính đồng thời, ví dụ `groupingByConcurrent` và `toConcurrentMap`:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = products.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Product::category,
                Collectors.counting()
        ));

System.out.println(counts.get("OFFICE")); // 2
~~~

`groupingByConcurrent` trả `ConcurrentMap` và có collector với tính chất **concurrent, unordered**. Điều này phù hợp khi kết quả là số đếm theo khóa và **không yêu cầu giữ thứ tự xuất hiện** trong từng nhóm.

Nếu cần duy trì danh sách có thứ tự cụ thể, không được tự thay `groupingBy` bằng `groupingByConcurrent` và giả định kết quả sẽ y hệt về thứ tự các phần tử. Việc chạy nhanh hơn cũng không được bảo đảm vì các tác vụ có thể tranh chấp cùng một khóa.

Với `toConcurrentMap`, khi nhiều phần tử có cùng khóa, hãy cung cấp merge function có tính kết hợp và quy tắc nghiệp vụ rõ:

~~~java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Integer> occurrences = products.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Product::category,
                p -> 1,
                Integer::sum
        ));
~~~

`ConcurrentMap` không có nghĩa là mapper/predicate tự an toàn khi dùng trạng thái mutable bên ngoài. Collector có thể tổ chức cập nhật Map nội bộ đúng hợp đồng, nhưng side effect do ứng dụng tự viết vẫn cần được thiết kế riêng.

## 15. distinct, sorted và các thao tác có trạng thái

Một số intermediate operation lưu trạng thái hoặc cần phối hợp giữa nhiều phần tử:

| Thao tác | Ý nghĩa | Lưu ý khi parallel |
| --- | --- | --- |
| `distinct()` | Giữ phần tử phân biệt | Với Stream có thứ tự, cần giữ lần xuất hiện đầu theo encounter order; có thể phải lưu trạng thái/phối hợp. |
| `sorted()` | Sắp theo comparator hoặc thứ tự tự nhiên | Có thể cần đệm dữ liệu và ghép/sắp xếp các phần. |
| `limit(n)`, `skip(n)` | Lấy/bỏ số phần tử theo thứ tự nếu có encounter order | Có thể tốn phối hợp để tôn trọng tiền tố. |
| `takeWhile`, `dropWhile` | Xử lý tiền tố theo predicate trên Stream có thứ tự | Có thể khó chia nhỏ hiệu quả nếu cần tìm chính xác điểm cắt. |
| `map`, `filter` với lambda thuần | Biến đổi/đánh giá từng phần tử độc lập | Thường thuận lợi hơn cho việc chia phần. |

Những thao tác có trạng thái **không sai chỉ vì chạy song song**. Vấn đề là chúng có thể làm mất lợi thế song song hoặc khiến pipeline giữ nhiều bộ nhớ hơn.

Ví dụ:

~~~java
List<Integer> sortedDistinct = List.of(3, 1, 3, 2)
        .parallelStream()
        .distinct()
        .sorted()
        .toList();

System.out.println(sortedDistinct); // [1, 2, 3]
~~~

Kết quả có ngữ nghĩa rõ ràng, nhưng với tập nhỏ như ví dụ, chạy song song không phải lựa chọn có lợi về hiệu năng.

Nếu bỏ `ORDERED` bằng `unordered()` để tối ưu, hãy chắc rằng việc chọn phần tử đại diện trong `distinct` và các thao tác tiếp theo vẫn đúng yêu cầu. `sorted()` có thể tạo thứ tự kết quả mới, nhưng không vì thế mà mọi hành vi trước nó đều trở thành có thứ tự.

## 16. Nguồn, Spliterator và khả năng chia phần

Stream song song làm việc thông qua `Spliterator` của nguồn. Một Spliterator có `trySplit()` hiệu quả thường giúp chia nhiệm vụ đều hơn.

| Nguồn | Khả năng chia thường gặp | Điều cần nhớ |
| --- | --- | --- |
| `ArrayList` hoặc mảng | Có thể chia theo chỉ số/phạm vi | Thường phù hợp với pipeline tính toán thuần và đủ lớn. |
| `IntStream.range` / `LongStream.range` | Nguồn số theo khoảng, chia được thành các phần | Thuận lợi cho công việc độc lập từng phần tử. |
| `HashSet` | Có thể chia nhưng không có encounter order được cam kết | Không suy ra thứ tự ổn định. |
| `Iterator` được bọc bởi `Spliterators.spliteratorUnknownSize` | Có thể phải đọc trước vào từng lô để chia | Việc đọc Iterator gốc có thể là nút thắt tuần tự. |
| Stream đọc I/O như `Files.lines` | Phụ thuộc nguồn, encoding, khả năng chia và chi phí I/O | Parallel không tự làm tệp đọc nhanh hơn. |

Các characteristic như `SIZED`, `SUBSIZED`, `ORDERED`, `IMMUTABLE`, `CONCURRENT` ảnh hưởng đến những tối ưu mà implementation có thể áp dụng. **Khai báo sai characteristic** ở Spliterator tùy chỉnh là lỗi nguồn, không phải thứ `parallel()` tự sửa được.

Một nguồn chỉ có thể cung cấp phần tử tuần tự từ mạng hoặc database cursor có thể khó tận dụng xử lý song song. Thậm chí khi `map` đủ nặng, chi phí lấy dữ liệu từ Iterator vẫn có thể trở thành nút thắt chung.

## 17. I/O, transaction, tính nguyên tử và hành vi lỗi

Một pipeline có thể trông độc lập về dữ liệu nhưng mapper thực hiện I/O hoặc cập nhật trạng thái bên ngoài:

~~~java
// Chỉ là minh họa: sendNotification là một thao tác có side effect.
orders.parallelStream()
        .forEach(order -> sendNotification(order));
~~~

Với cách này, **thứ tự gửi** không được bảo đảm. Nếu một tác vụ ném exception, không có cơ chế mặc định để rollback những thông báo mà các tác vụ khác đã gửi. Các tác vụ đang chạy cũng có thể đã tạo side effect trước khi caller nhận được lỗi.

Vì vậy, cần cân nhắc thiết kế tách đôi:

1. **Tính toán và xác định dữ liệu cần xử lý** bằng Stream với các hàm thuần, tạo một tập yêu cầu rõ ràng.
2. **Thực hiện side effect** bằng cơ chế phù hợp với transaction, retry, idempotency, concurrency limit và yêu cầu thứ tự của hệ thống.

Đừng xem parallel Stream là một framework điều phối I/O với timeout, backpressure, số lần retry hoặc phân tán công việc. Những tính chất đó phải được thiết kế ở tầng tác vụ nếu bài toán đòi hỏi.

### Stream từ nguồn I/O vẫn cần đóng

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("events.log");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines.parallel()
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

`count()` là terminal operation nhưng không tự thay thế `close()` trên nguồn tài nguyên. `try-with-resources` vẫn cần thiết dù pipeline chạy song song, dừng sớm hoặc gặp lỗi.

## 18. Ví dụ hoàn chỉnh: chuyển báo cáo doanh thu sang song song

Giả sử hệ thống cần tính tổng tiền theo từng khách hàng, từ các dòng bán hàng. Mỗi dòng có mã khách, số lượng và đơn giá. Yêu cầu:

- Kết quả là `Map<String, BigDecimal>`, không phụ thuộc thứ tự xử lý.
- Tính thành tiền bằng số thập phân chính xác.
- Không làm tròn trung gian và không sửa dữ liệu nguồn.
- Khi cần hiển thị, chỉ làm tròn theo chính sách nghiệp vụ **sau** khi tổng hợp.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ParallelRevenueDemo {

    record Sale(String customerId, long quantity, BigDecimal unitPrice) {}

    static Map<String, BigDecimal> revenueByCustomer(
            List<Sale> sales, boolean parallel) {

        var source = parallel
                ? sales.parallelStream()
                : sales.stream();

        return source.collect(Collectors.groupingBy(
                Sale::customerId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        sale -> sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity())),
                        BigDecimal::add
                )
        ));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("C-01", 2, new BigDecimal("10.50")),
                new Sale("C-02", 3, new BigDecimal("2.00")),
                new Sale("C-01", 1, new BigDecimal("9.50"))
        );

        Map<String, BigDecimal> sequential =
                revenueByCustomer(sales, false);

        Map<String, BigDecimal> parallel =
                revenueByCustomer(sales, true);

        System.out.println(sequential.equals(parallel)); // true
        System.out.println(parallel.get("C-01"));          // 30.50
        System.out.println(parallel.get("C-02"));          // 6.00

        BigDecimal payableC01 = parallel.get("C-01")
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println(payableC01); // 30.50
    }
}
~~~

Giải thích vì sao có thể chuyển sang song song:

1. **Nguồn** là một `List` không bị sửa trong lúc xử lý, có Spliterator phù hợp.
2. `sale -> ...` là phép tính độc lập, không ghi vào biến mutable bên ngoài.
3. `groupingBy` dùng collector chuẩn để tích lũy/ghép các kết quả trung gian.
4. `BigDecimal::add` (không truyền `MathContext`) là phép cộng thập phân chính xác, phù hợp để gộp các tổng phần.
5. **Không phụ thuộc thứ tự duyệt Map**. Bài toán chỉ yêu cầu ánh xạ khách hàng → tổng tiền.
6. Thao tác `setScale` được áp dụng **sau** khi tổng hợp xong, tại ranh giới nghiệp vụ.

Nếu yêu cầu dữ liệu lớn, vẫn phải benchmark trên môi trường phù hợp để xác định chế độ song song có thực sự tốt hơn. Ví dụ này chứng minh **khả năng giữ ngữ nghĩa**, không chứng minh có tăng tốc.

> **Ghi chú phiên bản:** `record` và `Stream.toList()` có từ Java 16; `var` có từ Java 10. Java Stream API, `parallelStream`, `Collectors.groupingBy` và `reducing` có từ Java 8. Nếu dùng Java 8, thay `record` bằng class, khai báo kiểu `Stream<Sale>` thay `var` và dùng `collect(Collectors.toList())` thay `toList()` khi cần.

## 19. Chiến lược kiểm thử tính tương đương trước và sau song song

Hãy tách **ngữ nghĩa được bảo đảm** khỏi những chi tiết không nên kiểm tra.

### 19.1. So sánh theo hợp đồng kết quả

Với báo cáo doanh thu:

~~~java
Map<String, BigDecimal> expected = revenueByCustomer(sales, false);
Map<String, BigDecimal> actual = revenueByCustomer(sales, true);

if (!expected.equals(actual)) {
    throw new AssertionError("Parallel result differs");
}
~~~

Giả định `sales` là collection cùng dữ liệu như ví dụ ở phần trước. Để kiểm tra `BigDecimal`, cần phân biệt so sánh giá trị số học (`compareTo`) và so sánh cả scale (`equals`); trong ví dụ, phép cộng chính xác với cùng dữ liệu dẫn tới kết quả phù hợp để so trực tiếp. Nếu chính sách nghiệp vụ yêu cầu scale cố định, chuẩn hóa scale trước khi khẳng định tương đương.

Với `Set`, kiểm tra tập phần tử; với `Map`, kiểm tra ánh xạ khóa–giá trị; với `List` có encounter order, kiểm tra cả thứ tự; với `findAny()`, chỉ kiểm tra phần tử thuộc tập hợp cho phép, không đòi luôn một giá trị cố định.

### 19.2. Kiểm thử các trường hợp dễ hỏng

- **Nguồn rỗng, một phần tử, rất nhiều phần tử**: kiểm tra identity, logic nhóm và giới hạn dữ liệu.
- **Nhiều khóa trùng**: kiểm tra merge function, grouping collector và tổng chính xác.
- **Phần tử bằng nhau, null, số âm, số lớn**: kiểm tra hợp đồng đầu vào; `null` không tự an toàn.
- **Nguồn có/không encounter order**: kiểm tra xem kết quả có vô tình dựa vào thứ tự không được cam kết.
- **Lặp lại nhiều lượt xử lý**: giúp phát hiện race condition, nhưng không đủ để chứng minh không còn lỗi.
- **Có lỗi ở mapper/I/O**: xác định cách báo lỗi và side effect nào có thể đã xảy ra.
- **Không sửa nguồn trong lúc duyệt**: giữ dữ liệu đầu vào ổn định trong toàn bộ phép đo và phép kiểm tra.

Không nên tạo bài kiểm thử chỉ kiểm tra `Thread.currentThread().getName()` hoặc số lượng thread: Stream không cam kết cố định số thread, cách lên lịch hay mức độ song song.

### 19.3. Phân biệt kiểm thử đúng và benchmark

Kiểm thử tính tương đương trả lời: **Kết quả có đúng hợp đồng không?**

Benchmark trả lời: **Trên tập dữ liệu và môi trường này, pipeline có nhanh hơn không?**

Hai câu hỏi cần được giải quyết độc lập; không nên lấy tốc độ làm bằng chứng tính đúng, cũng không suy rằng một pipeline đúng thì mặc nhiên song song sẽ có lợi.

## 20. Khi nào parallelStream() thực sự đáng dùng?

Có cơ hội tăng tốc khi:

- Nguồn **lớn, hữu hạn, dễ chia đều** thành những phần độc lập.
- Mỗi phần tử cần **tính toán CPU đủ đáng kể**.
- Mapper và predicate stateless, không phụ thuộc vào thứ tự gọi.
- Terminal operation có thể ghép kết quả hiệu quả.
- Bộ nhớ và chi phí quản lý tác vụ không trở thành nút thắt.

Không nên kỳ vọng tăng tốc khi:

- Tập dữ liệu rất nhỏ, ví dụ chỉ vài chục phần tử với phép toán nhẹ.
- Nguồn như Iterator/cursor phải được đọc tuần tự mới có dữ liệu.
- Pipeline chứa nhiều thao tác có trạng thái hoặc yêu cầu encounter order nghiêm ngặt.
- Lambda liên tục truy cập synchronized lock, database, network hoặc tài nguyên I/O bị giới hạn.
- Collector có các khóa nóng gây cạnh tranh, hoặc bước ghép các kết quả trung gian quá tốn kém.
- Chương trình đang chạy chung tài nguyên CPU với nhiều tác vụ cần độ trễ ổn định.

### Đo lường như thế nào?

Trong môi trường Java có khả năng chạy benchmark, nên dùng công cụ chuyên dụng như **JMH** để tránh sai lệch do JIT warm-up, dead-code elimination, mức độ tải CPU và GC. Một phép đo đơn lẻ bằng `System.nanoTime()` thường không đủ kết luận.

Cần đo cả **thời gian**, **mức cấp phát/bộ nhớ**, **độ trễ đuôi**, và ảnh hưởng đến tác vụ khác. Với server xử lý nhiều request đồng thời, song song hóa từng request có thể tạo cạnh tranh tài nguyên dù một phép benchmark độc lập có lợi.

`parallelStream()` thường dùng cơ chế fork/join và common pool theo triển khai JDK, nhưng không nên viết logic nghiệp vụ phụ thuộc số thread hay tên pool. Nếu cần kiểm soát chặt concurrency, timeout, backpressure hoặc tài nguyên theo request, cân nhắc kiến trúc tác vụ riêng thay vì mặc định giao toàn bộ cho parallel Stream.

## 21. Bảng lỗi thường gặp và cách sửa

| Triệu chứng | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Thiếu phần tử khi gom vào `ArrayList` | Nhiều thread gọi `add` trên cùng container không an toàn | Dùng `toList` hoặc `collect` chuẩn. |
| Đã dùng `AtomicInteger` nhưng số thứ tự bị lệch | Atomicity không bảo đảm encounter order | Lấy chỉ số từ nguồn ổn định, ví dụ `IntStream.range`. |
| `forEach` in lộn thứ tự | Không cam kết thứ tự thực thi khi parallel | Dùng `forEachOrdered` nếu thật sự cần side effect có thứ tự; dùng `toList` nếu cần danh sách. |
| `findAny` đôi khi trả phần tử khác | Theo hợp đồng, có thể chọn phần tử bất kỳ | Nếu cần phần tử đầu của nguồn có thứ tự, dùng `findFirst`. |
| `limit` trả bộ phần tử không như dự đoán | Nguồn unordered hoặc có `unordered()` | Giữ encounter order hoặc sắp xếp rõ theo yêu cầu. |
| Tổng `double` lệch vài chữ số cuối | Phép cộng floating-point không hoàn toàn kết hợp | Xác định sai số; dùng `BigDecimal` nếu cần số thập phân chính xác. |
| `reduce` song song trả sai | Identity không trung hòa hoặc combiner không tương thích | Dùng phép kết hợp đúng hợp đồng, kiểm tra trên các cách chia nhóm. |
| Có dữ liệu trùng/mất khi reduce mutable | Dùng identity mutable và sửa trực tiếp | Dùng immutable reduction hoặc `collect` cho container mutable. |
| `groupingByConcurrent` làm thay đổi thứ tự danh sách | Collector unordered, không giữ encounter order như yêu cầu | Dùng `groupingBy`/downstream phù hợp nếu thứ tự quan trọng. |
| Xử lý chậm hơn tuần tự | Overhead chia/ghép, thao tác có trạng thái, dữ liệu nhỏ hoặc contention | Benchmark sau khi bảo đảm tính đúng, cân nhắc trở về tuần tự. |
| Truy vấn/ghi bên ngoài chạy sai thứ tự hoặc nửa chừng | Side effect trong mapper/forEach không có giao dịch chung | Tách phép tính thuần và tầng thực thi I/O có điều phối. |
| Tệp bị giữ mở sau terminal operation | `parallel` và `count` không tự đóng nguồn | Dùng `try-with-resources` cho nguồn I/O. |

## 22. Bài tập tự kiểm tra

### Bài 1 — Pipeline nào giữ nguyên thứ tự kết quả?

~~~java
List<Integer> values = List.of(4, 1, 3, 2);

List<Integer> a = values.stream()
        .map(n -> n * 2)
        .toList();

List<Integer> b = values.parallelStream()
        .map(n -> n * 2)
        .toList();
~~~

**Đáp án:** Cả `a` và `b` đều là `[8, 2, 6, 4]`. Nguồn `List` có encounter order; `map` là phép biến đổi độc lập; `toList()` giữ encounter order. Thứ tự mapper thực thi không được suy ra từ thứ tự kết quả.

### Bài 2 — Race condition hay lỗi ngữ nghĩa?

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> ids = names.parallelStream()
        .map(name -> counter.incrementAndGet() + "-" + name)
        .toList();
~~~

**Đáp án:** `AtomicInteger` tránh mất lượt tăng vì race ở biến đếm, nhưng số gắn với từng tên không bảo đảm khớp vị trí encounter order. Đây là lỗi **ngữ nghĩa đánh số**, không chỉ lỗi an toàn cập nhật. Chọn nguồn có chỉ số xác định hoặc tạo thứ tự ở bước riêng.

### Bài 3 — Identity trong reduce

~~~java
int sum = List.of(1, 2, 3).parallelStream()
        .reduce(5, Integer::sum);
~~~

**Đáp án:** `5` không phải identity của phép cộng; reduction này không đúng hợp đồng cho mục tiêu “tổng các phần tử cộng thêm 5 một lần”. Dùng `5 + stream.reduce(0, Integer::sum)`.

### Bài 4 — Chọn findFirst hay findAny

Một hệ thống cần lấy **khách hàng đầu tiên theo danh sách ưu tiên đã sắp xếp**. Có thể đổi `findFirst()` thành `findAny()` để tăng tốc không?

**Đáp án:** Không nếu “đầu tiên” là yêu cầu nghiệp vụ. `findAny` có quyền trả bất kỳ phần tử nào; dùng `findFirst` trên Stream có encounter order phù hợp.

### Bài 5 — Có nên gắn unordered trước limit?

~~~java
List<Integer> first = IntStream.range(0, 10)
        .parallel()
        .unordered()
        .limit(3)
        .boxed()
        .toList();
~~~

**Đáp án:** Không được đòi kết quả luôn là `[0, 1, 2]`. `unordered()` làm mất ràng buộc ba phần tử đầu theo encounter order; phép `limit(3)` có thể chọn ba phần tử khác nhau. Nếu cần ba số đầu của khoảng, bỏ `unordered()`.

### Bài 6 — Có nên dùng synchronizedList?

Một lập trình viên thay `new ArrayList<>()` bằng `Collections.synchronizedList(new ArrayList<>())` rồi dùng `parallelStream().forEach(list::add)`. Điều đó đã bảo đảm kết quả theo encounter order chưa?

**Đáp án:** Chưa. Các lời gọi `add` được đồng bộ ở mức collection nhưng vẫn đến theo thứ tự thực thi không xác định. Nếu cần danh sách theo thứ tự nguồn, dùng `toList()` hoặc collector có hợp đồng phù hợp.

### Bài 7 — Tổng tiền và làm tròn

Ba khoản tiền đều là `0.005`. Pipeline tuần tự làm tròn sau khi cộng cho `0.02`. Có thể chuyển sang parallel stream không?

**Đáp án:** Có thể nếu `reduce` dùng `BigDecimal.ZERO` và `BigDecimal::add` **chính xác**, còn `setScale(2, HALF_UP)` chỉ chạy **sau** reduction. Không đưa làm tròn vào từng accumulator/combiner vì có thể phá tính kết hợp.

### Bài 8 — Bài toán I/O

Một pipeline gọi API thanh toán trong `forEach`, sau đó chuyển từ `stream()` sang `parallelStream()`. Đã đủ để tăng tốc an toàn chưa?

**Đáp án:** Chưa. Phải xem xét idempotency, giới hạn đồng thời, transaction, thứ tự xử lý, timeout, retry và khả năng có side effect xảy ra trước khi một tác vụ khác ném lỗi. Parallel Stream không tự đảm nhiệm những hợp đồng đó.

## 23. Ghi nhớ

- `parallel()` hoặc `parallelStream()` thay đổi **cách thực thi**, không cho phép tự ý thay đổi ngữ nghĩa nghiệp vụ.
- Lambda trong `map`, `filter` và các bước xử lý nên **stateless, non-interfering**, không sửa nguồn và không dựa vào trạng thái mutable bên ngoài.
- Phân biệt **encounter order**, **thứ tự thực thi** và **thứ tự kết quả**. `forEach` không giữ thứ tự; `forEachOrdered` có hợp đồng về thứ tự action; `toList` giữ encounter order của Stream có thứ tự.
- `findFirst` và `findAny` có hợp đồng khác nhau; `unordered()` có thể thay đổi ý nghĩa của `limit`, `takeWhile` và các phép lấy tiền tố.
- `reduce` cần identity trung hòa, phép kết hợp có tính kết hợp và accumulator/combiner tương thích. `collect` phù hợp với mutable reduction; không dùng identity mutable chia sẻ trong `reduce`.
- Cộng `double` có thể lệch do thứ tự nhóm; với số thập phân cần chính xác như tiền, dùng `BigDecimal` phù hợp và áp dụng làm tròn đúng ranh giới nghiệp vụ.
- Spliterator, các thao tác có trạng thái, collector concurrent, side effect và nguồn I/O quyết định tính phù hợp và hiệu năng của pipeline song song.
- **Kiểm thử đúng trước, benchmark sau.** Không suy rằng parallel Stream luôn nhanh hơn, ngay cả khi đã đúng ngữ nghĩa.

**Ý chính:** Chuyển pipeline tuần tự sang song song an toàn khi kết quả **không phụ thuộc vào lịch thực thi hoặc cách chia–ghép công việc** ngoài những khác biệt mà hợp đồng API cho phép. Hãy xác định rõ thứ tự cần giữ, dùng lambda không chia sẻ trạng thái, chọn reduction/collector đúng hợp đồng và đo hiệu năng sau khi đã kiểm chứng tính đúng đắn.
