# Tính ổn định của `sorted()` trên Stream có thứ tự trong Java

## 1. Mục tiêu bài học

Trong Java Stream API, `sorted()` là **intermediate operation** để sắp xếp các phần tử. Nhưng nói “sắp xếp tăng dần” chưa đủ: khi nhiều phần tử được comparator đánh giá **bằng nhau**, thứ tự ban đầu của các phần tử ấy có được giữ lại không?

Đó là câu hỏi về **tính ổn định của phép sắp xếp (stable sorting)**. Javadoc của `Stream.sorted()` và `Stream.sorted(Comparator)` nêu rõ:

> Với **Stream có thứ tự (ordered Stream)**, phép sắp xếp được bảo đảm ổn định. Với **Stream không có thứ tự (unordered Stream)**, không có bảo đảm về tính ổn định.

Bài học tập trung vào ý nghĩa và giới hạn chính xác của bảo đảm này. Sau khi học, bạn có thể:

- Phân biệt **encounter order** của Stream với thứ tự do comparator tạo ra.
- Định nghĩa sự ổn định dựa trên `compare(a,b) == 0`, không nhầm với `equals()`.
- Dự đoán thứ tự các phần tử có khóa sắp xếp bằng nhau trên Stream có thứ tự.
- Hiểu khác biệt giữa `List.stream()`, nguồn không có thứ tự như `HashSet` và lời gọi `unordered()`.
- Giải thích vì sao `parallelStream().sorted(...)` vẫn được bảo đảm ổn định nếu nguồn có encounter order, nhưng `forEach(...)` có thể quan sát thứ tự khác.
- Sử dụng `thenComparing(...)` khi nghiệp vụ cần **thứ tự phụ rõ ràng**, thay vì dựa vào thứ tự gốc.
- Tránh comparator không hợp lệ, phép trừ số nguyên gây overflow, áp dụng `sorted`/`limit` sai thứ tự và sử dụng Stream đã tiêu thụ.
- Chạy chương trình Java 17 minh họa và kiểm tra stdout chính xác.

**Phạm vi:** tính ổn định của `sorted()` trên Stream tham chiếu trong Java, với một số liên hệ về comparator, nguồn và terminal operation để áp dụng đúng.

## 2. Hai khái niệm cần tách riêng

### 2.1. Encounter order là gì?

**Encounter order** là thứ tự phần tử mà một pipeline có thứ tự nhận từ nguồn và duy trì thông qua các thao tác giữ thứ tự. Với một `List`, encounter order thường chính là thứ tự phần tử trong danh sách:

~~~java
List<String> names = List.of("Mai", "An", "Binh");
List<String> original = names.stream().toList();
System.out.println(original); // [Mai, An, Binh]
~~~

Đoạn trên là **mảnh mã trong phương thức** có import `java.util.List`. `List.stream()` cung cấp Stream có thứ tự. Một số nguồn khác như `Stream.of(...)` cũng có encounter order rõ ràng.

Không phải mọi nguồn Stream đều có thứ tự. Một số nguồn như `HashSet` không hứa hẹn encounter order; `unordered()` cũng có thể loại bỏ ràng buộc thứ tự khỏi một pipeline. Không được giả định rằng quan sát một lần chạy có thứ tự cụ thể thì nguồn đã có bảo đảm thứ tự tương ứng.

### 2.2. Thứ tự sắp xếp là gì?

`sorted()` tạo thứ tự theo **natural ordering** (thường là `Comparable`). `sorted(comparator)` tạo thứ tự theo **Comparator** do người gọi cung cấp. Ví dụ:

~~~java
List<Integer> numbers = List.of(5, 2, 4, 1, 3);
List<Integer> sorted = numbers.stream().sorted().toList();
System.out.println(sorted); // [1, 2, 3, 4, 5]
~~~

Phần tử được đưa vào thứ tự theo giá trị; thứ tự này khác encounter order gốc của danh sách.

Nhưng nếu nhiều phần tử được xem là **ngang nhau theo comparator**, thì comparator không đưa ra đủ dữ liệu để phân biệt thứ tự giữa chúng. Với Stream có thứ tự, `sorted` phải giữ **thứ tự gặp ban đầu giữa những phần tử ngang nhau đó**.

### 2.3. Tính ổn định không có nghĩa không đổi vị trí tất cả phần tử

Giả sử các mục có độ ưu tiên `2, 1, 2, 1`. Sau sắp xếp tăng theo độ ưu tiên, các mục ưu tiên `1` chuyển lên trước ưu tiên `2`. Phép sắp xếp ổn định chỉ yêu cầu **hai mục cùng độ ưu tiên** giữ thứ tự tương đối, chứ không đòi giữ nguyên vị trí tuyệt đối của mọi mục.

## 3. Định nghĩa phép sắp xếp ổn định

Cho một dãy đầu vào có encounter order:

~~~text
Phần tử:   A   B   C   D   E
Khóa:      2   1   2   1   2
Vị trí:    0   1   2   3   4
~~~

Sắp xếp tăng theo khóa theo cách **ổn định** cho:

~~~text
B(1)  D(1)  A(2)  C(2)  E(2)
~~~

Các phần tử có khóa bằng nhau giữ thứ tự tương đối:

- Nhóm khóa `1`: `B` xuất hiện trước `D` ở đầu vào, nên vẫn `B, D` sau khi sắp xếp.
- Nhóm khóa `2`: `A` đứng trước `C`, rồi `E` ở đầu vào, nên vẫn `A, C, E` sau sắp xếp.

Định nghĩa chính xác hơn: nếu hai phần tử `x` và `y` xuất hiện trong Stream có thứ tự, `x` đứng trước `y` theo encounter order, và comparator trả `compare(x,y) == 0`, thì phép `sorted(comparator)` ổn định giữ `x` trước `y` trong kết quả.

**Đừng nhầm “bằng nhau” ở đây với `equals()`.** Hai đối tượng có thể khác ID, khác payload, thậm chí `equals()` trả `false`, nhưng comparator chỉ so một khóa và trả `0`. Khi đó chúng được coi là cùng nhóm khóa **cho mục đích sắp xếp** và tính ổn định có ý nghĩa.

## 4. Hai overload của `sorted()`

### 4.1. `sorted()` dùng natural ordering

~~~java
Stream<T> sorted();
~~~

Đây là **chữ ký API khái quát**, không phải đoạn Java độc lập để khai báo trong method. Với Stream các giá trị `String`, `Integer` hoặc các object triển khai `Comparable` phù hợp, có thể viết:

~~~java
List<String> words = List.of("pear", "apple", "banana");
List<String> sorted = words.stream().sorted().toList();

System.out.println(sorted); // [apple, banana, pear]
~~~

Nếu không có thứ tự tự nhiên tương thích, phép sắp xếp có thể thất bại bằng `ClassCastException` khi thực thi. Với đối tượng nghiệp vụ không có `Comparable`, hãy dùng `sorted(Comparator)` để thể hiện khóa và quy tắc sắp xếp thay vì dựa vào cast.

### 4.2. `sorted(Comparator<? super T>)` dùng comparator

~~~java
Stream<T> sorted(Comparator<? super T> comparator);
~~~

Cũng là **chữ ký API**, diễn đạt cách cung cấp một bộ so sánh. Ví dụ:

~~~java
List<String> words = List.of("bb", "a", "cc", "b", "ddd", "ee");
List<String> byLength = words.stream()
        .sorted(Comparator.comparingInt(String::length))
        .toList();

System.out.println(byLength); // [a, b, bb, cc, ee, ddd]
~~~

Đây là mảnh mã trong method với import `java.util.List` và `java.util.Comparator`. Các chuỗi `"a"` và `"b"` có độ dài `1` nên giữ thứ tự `a, b`. Các chuỗi `"bb"`, `"cc"`, `"ee"` đều có độ dài `2`, nên vẫn theo thứ tự `bb, cc, ee`.

Nếu comparator được xây chỉ để so sánh độ dài, nó **không phân biệt nội dung chuỗi cùng độ dài**. Tính ổn định giữ encounter order trong nhóm độ dài bằng nhau, thay vì ngẫu nhiên đảo nhóm.

### 4.3. Sự ổn định là bảo đảm của `sorted`, không phải do bạn chọn một thuật toán cụ thể

Javadoc quy định hành vi, không yêu cầu người dùng phải biết JVM dùng thuật toán sắp xếp nội bộ nào. Tránh gắn điều kiện “ổn định” vào một thuật toán cụ thể hoặc kết luận từ implementation đang thấy trong một phiên bản JDK.

## 5. Ví dụ với record: so khóa, giữ thứ tự khi hòa

Giả sử có các ticket, mỗi ticket có mã và độ ưu tiên:

~~~text
Encounter order:
C(2), B(1), A(2), D(1), F(3), E(2)
~~~

Ta chỉ so sánh theo `priority`. Sau `sorted(comparingInt(Ticket::priority))`, kết quả đúng theo hợp đồng ổn định là:

~~~text
B(1), D(1), C(2), A(2), E(2), F(3)
~~~

Trong nhóm độ ưu tiên `2`, mã `C` vẫn đứng trước `A` và `E`, mặc dù thứ tự bảng chữ cái có thể là `A, C, E`. Đây là trường hợp điển hình để kiểm tra hiểu biết: **không có tie-breaker thì thứ tự nguồn quyết định thứ tự các phần tử có comparator bằng 0** trên ordered Stream.

Một comparator gọn và an toàn:

~~~java
Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority);
~~~

Đây là đoạn code đặt trong class đã có record `Ticket(String code, int priority)` và import `java.util.Comparator`. `Comparator.comparingInt` tránh boxing cần thiết cho khóa số nguyên và tránh tự viết phép trừ rủi ro.

## 6. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`StableSortedDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;

public class StableSortedDemo {

    record Ticket(String code, int priority) {}

    public static void main(String[] args) {
        List<Ticket> input = List.of(
                new Ticket("C", 2),
                new Ticket("B", 1),
                new Ticket("A", 2),
                new Ticket("D", 1),
                new Ticket("F", 3),
                new Ticket("E", 2)
        );

        Comparator<Ticket> byPriority =
                Comparator.comparingInt(Ticket::priority);

        List<String> encounter = input.stream()
                .map(Ticket::code)
                .toList();

        // List.stream() có encounter order.
        List<String> stable = input.stream()
                .sorted(byPriority)
                .map(Ticket::code)
                .toList();

        // Nguồn vẫn ordered dù pipeline chạy parallel.
        List<String> stableParallel = input.parallelStream()
                .sorted(byPriority)
                .map(Ticket::code)
                .toList();

        // Thêm khóa phụ: thứ tự trong nhóm priority có thể đổi.
        List<String> withTieBreak = input.stream()
                .sorted(byPriority.thenComparing(Ticket::code))
                .map(Ticket::code)
                .toList();

        System.out.println("source=" + encounter);
        System.out.println("stable=" + stable);
        System.out.println("parallel=" + stableParallel);
        System.out.println("tie-break=" + withTieBreak);
        System.out.println("same=" + stable.equals(stableParallel));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 StableSortedDemo.java
java StableSortedDemo
~~~

**Stdout chính xác:**

~~~text
source=[C, B, A, D, F, E]
stable=[B, D, C, A, E, F]
parallel=[B, D, C, A, E, F]
tie-break=[B, D, A, C, E, F]
same=true
~~~

### Vì sao có kết quả này?

1. `source` phản ánh encounter order của `List`: `C, B, A, D, F, E`.
2. `stable` sắp xếp tăng theo `priority`. Nhóm `priority = 1` là `B, D`, nhóm `priority = 2` là `C, A, E`, nhóm `priority = 3` chỉ có `F`.
3. `parallel` có cùng kết quả vì **`sorted` trên ordered Stream được bảo đảm ổn định** ngay cả khi pipeline song song. `toList()` thu các phần tử theo encounter order của pipeline có thứ tự.
4. `tie-break` dùng `thenComparing(Ticket::code)`. Trong nhóm cùng `priority`, comparator bây giờ phân biệt bằng `code`; `A` đứng trước `C`. Việc thay đổi là **do quy tắc sắp xếp mới**, không phải sorted mất tính ổn định.
5. `same=true` chứng minh hai kết quả trong chương trình kiểm thử bằng nhau; lý do bảo đảm tổng quát là hợp đồng Javadoc, không phải chỉ một lần chạy may mắn.

## 7. Comparator bằng 0 không có nghĩa hai object `equals`

Xét hai bản ghi:

~~~java
record Person(String id, int age) {}

Person a = new Person("p-1", 20);
Person b = new Person("p-2", 20);

Comparator<Person> byAge = Comparator.comparingInt(Person::age);

System.out.println(byAge.compare(a, b)); // 0
System.out.println(a.equals(b));         // false
~~~

Đây là mảnh mã trong phương thức với import `Comparator` và khai báo record phù hợp. `a` và `b` không bằng nhau theo `equals()`, vì `id` khác nhau, nhưng comparator `byAge` chỉ so tuổi và trả `0`. Vì vậy hai người thuộc một nhóm “hòa” theo phép sắp xếp và sẽ giữ thứ tự gặp ban đầu khi dùng ordered Stream.

**Tính ổn định được xét theo comparator, không theo `equals`.** Đừng cho rằng `sorted` loại bỏ phần tử trùng khóa: `sorted` chỉ sắp xếp, không tự `distinct`. Muốn loại trùng phải xác định đúng định nghĩa trùng và dùng công cụ tương ứng.

Lưu ý thêm: comparator không nhất thiết phải nhất quán với `equals` để dùng `sorted` trên Stream, nhưng khi dùng làm quy tắc sắp xếp của `TreeSet`/`TreeMap`, quan hệ so sánh bằng 0 ảnh hưởng mạnh tới cách phân biệt phần tử/khóa; đó là hợp đồng khác cần xem riêng.

## 8. Ordered Stream: điều kiện để có bảo đảm ổn định

### 8.1. Những nguồn thường có encounter order

| Nguồn | Đặc điểm về encounter order |
| --- | --- |
| `List.stream()` | Theo thứ tự phần tử trong List |
| `Stream.of(a,b,c)` | Theo thứ tự các phần tử cung cấp |
| `Arrays.stream(array)` | Theo thứ tự chỉ số trong mảng |
| `IntStream.range(...)` | Theo thứ tự số nguyên của dải |
| `LinkedHashSet.stream()` | Theo thứ tự duyệt được quy định bởi collection |
| `HashSet.stream()` | Không có encounter order được bảo đảm |
| `unordered()` được gọi trên pipeline | Loại bỏ bảo đảm thứ tự của pipeline, dù nguồn gốc ban đầu có thứ tự |

Bảng này mô tả những **nguồn/phép biến đổi phổ biến**, không có nghĩa mọi thao tác trung gian đều giữ nguyên đặc tính. Với pipeline phức tạp, phải xác định thứ tự từ nguồn và các thao tác trước `sorted`.

### 8.2. Bảo đảm của `sorted` được phát biểu thế nào?

Với Stream có encounter order, `sorted` được bảo đảm ổn định. Nếu đầu vào chưa có encounter order, `sorted` vẫn sắp xếp theo giá trị/Comparator nhưng **không hứa thứ tự tương đối giữa các phần tử được so sánh bằng nhau**.

Một cách mô tả:

~~~text
ORDERED source
     |
     v
sorted(comparator)
     |
     +--> Các phần tử khóa khác nhau theo comparator được sắp đúng thứ tự
     |
     +--> Các phần tử compare == 0 giữ thứ tự tương đối của nguồn

UNORDERED source
     |
     v
sorted(comparator)
     |
     +--> Các phần tử khóa khác nhau vẫn được sắp đúng thứ tự
     |
     +--> Các phần tử compare == 0 KHÔNG có bảo đảm ổn định
~~~

Điểm tinh tế: gọi `sorted(comparator)` với nguồn unordered vẫn có thể tạo một kết quả nhìn như đã ổn định khi chạy trên môi trường hiện tại. **Không được dựa vào kết quả quan sát tình cờ** để suy ra hợp đồng ổn định.

## 9. `unordered()` không phải lệnh trộn ngẫu nhiên

~~~java
List<String> input = List.of("bb", "a", "cc", "b");

List<String> result = input.stream()
        .unordered()
        .sorted(Comparator.comparingInt(String::length))
        .toList();
~~~

Đoạn trên là mảnh mã trong method. `unordered()` chỉ **bỏ yêu cầu bảo toàn encounter order** của pipeline; nó không yêu cầu đảo, trộn hay bốc thăm phần tử. Vì vậy, trong một lần chạy, các chuỗi cùng độ dài có thể vẫn xuất hiện theo thứ tự gốc.

Tuy nhiên, sau `unordered()`, không còn bảo đảm tính ổn định của `sorted` đối với nhóm khóa bằng nhau. Nếu cần bảo đảm, đừng bỏ đặc tính ordered trước sắp xếp, hoặc xác định tie-breaker rõ ràng.

### 9.1. `HashSet` và thứ tự không được bảo đảm

~~~java
Set<String> source = new HashSet<>(List.of("bb", "cc", "a", "b"));

List<String> result = source.stream()
        .sorted(Comparator.comparingInt(String::length))
        .toList();
~~~

Đoạn minh họa cần import `Set`, `HashSet`, `List` và `Comparator`. Sắp xếp theo độ dài vẫn đưa nhóm một ký tự trước nhóm hai ký tự. Nhưng thứ tự giữa `"a"` và `"b"`, hoặc `"bb"` và `"cc"`, **không được bảo đảm** theo một “thứ tự ban đầu” nhất định từ nguồn `HashSet`.

Đừng ghi một stdout cụ thể như `[a,b,bb,cc]` cho đoạn này rồi tuyên bố nó sẽ luôn đúng: code và Javadoc không hứa thứ tự tie như vậy.

### 9.2. Khi muốn đầu ra hoàn toàn xác định

Thay vì trông chờ thứ tự xuất hiện ban đầu của một nguồn unordered, hãy thêm khóa phụ:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());

List<String> result = source.stream()
        .sorted(byLengthThenText)
        .toList();
~~~

Nếu mọi phần tử là chuỗi không `null`, comparator này trước tiên so độ dài và khi hòa thì so chữ. Nhờ đó, kết quả có quy tắc thứ tự rõ ràng bất kể nguồn HashSet duyệt theo thứ tự nào. `thenComparing` không làm sắp xếp “ổn định hơn” theo định nghĩa: nó thay đổi quan hệ so sánh để giảm hoặc loại bỏ các trường hợp `compare == 0` chưa được phân biệt.

## 10. `parallelStream()` và tính ổn định

### 10.1. Parallel không có nghĩa mất encounter order

~~~java
List<Ticket> ordered = List.of(
        new Ticket("x", 2),
        new Ticket("y", 1),
        new Ticket("z", 2)
);

List<Ticket> output = ordered.parallelStream()
        .sorted(Comparator.comparingInt(Ticket::priority))
        .toList();
~~~

Đây là ví dụ mảnh mã trong class có record `Ticket`. `List.parallelStream()` vẫn là **ordered Stream**. Dù việc sắp xếp được thực hiện song song, `sorted` phải giữ thứ tự tương đối của `x` trước `z` khi hai ticket có cùng `priority = 2`.

Bảo đảm ổn định đến từ đặc tính ordered và hợp đồng `sorted`; nó không phụ thuộc việc pipeline được đánh giá trên một hay nhiều thread.

### 10.2. Vì sao `parallel().forEach(...)` có thể khiến bạn tưởng sort không ổn định?

Xét:

~~~java
input.parallelStream()
        .sorted(byPriority)
        .forEach(ticket -> System.out.println(ticket.code()));
~~~

**Đừng dự đoán thứ tự stdout cho đoạn này.** `forEach` trên Stream song song không bảo đảm thực hiện hành động theo encounter order. Dù `sorted` tạo ra thứ tự đúng trong pipeline, các side effect in ra console có thể xuất hiện theo lịch chạy của các thread.

Nếu mục tiêu là kiểm tra thứ tự sắp xếp, dùng terminal giữ encounter order:

~~~java
List<String> codes = input.parallelStream()
        .sorted(byPriority)
        .map(Ticket::code)
        .toList();
System.out.println(codes);
~~~

Hoặc nếu cần thực hiện hành động theo encounter order:

~~~java
input.parallelStream()
        .sorted(byPriority)
        .forEachOrdered(ticket -> System.out.println(ticket.code()));
~~~

`forEachOrdered` áp đặt yêu cầu thứ tự hành động; nó không phải cách bảo đảm tác dụng phụ bất kỳ trở thành thread-safe, và yêu cầu thứ tự có thể hạn chế hiệu suất song song. Với kiểm thử thứ tự dữ liệu, **thu thành List và so sánh** thường đơn giản hơn việc đọc log từ nhiều thread.

### 10.3. `toList()` giữ thứ tự kết quả phù hợp encounter order

`Stream.toList()` trong Java 17 trả một danh sách **unmodifiable** gồm phần tử của Stream theo encounter order nếu có. Vì thế ví dụ chương trình phần 6 có thể so sánh output từ pipeline tuần tự và song song. Đây là phép kiểm tra trực tiếp nội dung và thứ tự, không cần đưa side effect vào pipeline.

## 11. Tie-breaker: khi nào cần thứ tự phụ?

### 11.1. Giữ thứ tự gốc khi hòa là yêu cầu nghiệp vụ hợp lệ

Nếu dữ liệu ticket đã được xếp theo thứ tự tiếp nhận và chỉ muốn gom các mức ưu tiên, phép sắp xếp **ổn định theo priority** rất hữu ích: trong mỗi nhóm priority, ticket đến trước vẫn được giữ trước.

~~~java
Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority);

List<Ticket> sorted = input.stream()
        .sorted(byPriority)
        .toList();
~~~

Dữ liệu `input` ở đây là ordered `List<Ticket>`. Không thêm khóa phụ nếu yêu cầu chính là **bảo toàn thứ tự tiếp nhận** giữa các mục ưu tiên bằng nhau.

### 11.2. Muốn kết quả có thứ tự phụ độc lập nguồn thì thêm `thenComparing`

Nếu yêu cầu là “ưu tiên tăng dần, cùng ưu tiên thì mã ticket tăng dần”:

~~~java
Comparator<Ticket> byPriorityThenCode =
        Comparator.comparingInt(Ticket::priority)
                  .thenComparing(Ticket::code);

List<Ticket> sorted = input.stream()
        .sorted(byPriorityThenCode)
        .toList();
~~~

Giờ comparator không còn trả 0 cho `Ticket("C",2)` và `Ticket("A",2)`, vì `code` khác nhau; `A` đứng trước `C`. Điều này không vi phạm tính ổn định: **khóa sắp xếp đã thay đổi**.

Nếu hai ticket có cùng priority và cùng code nhưng vẫn là các object khác nhau, chúng tiếp tục là một tie theo comparator trên; đối với ordered Stream, thứ tự nguồn vẫn là cơ sở cho cặp ấy. Để sắp xếp hoàn toàn xác định, chỉ thêm những khóa tie-breaker thật sự có ý nghĩa và đủ để phân biệt đối tượng trong phạm vi yêu cầu.

### 11.3. Đừng dùng thứ tự thứ cấp giả tạo

Tạo khóa phụ bằng `System.identityHashCode`, random, thời gian hiện tại hoặc trạng thái mutable có thể tạo thứ tự khó dự đoán và vi phạm ý định nghiệp vụ. Nếu cần ID ổn định, dùng ID miền có hợp đồng rõ ràng. Nếu cần thứ tự nhận dữ liệu, giữ encounter order và dùng stable sort đúng cách.

## 12. Comparator đúng là điều kiện bắt buộc

### 12.1. Tránh phép trừ làm comparator số nguyên

Mã dễ gặp nhưng rủi ro:

~~~java
Comparator<Ticket> risky =
        (a, b) -> a.priority() - b.priority();
~~~

Khi hai giá trị ở gần giới hạn `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, phép trừ có thể overflow, cho dấu so sánh sai và vi phạm hợp đồng comparator. Sửa bằng:

~~~java
Comparator<Ticket> safe =
        Comparator.comparingInt(Ticket::priority);
~~~

Hoặc `(a,b) -> Integer.compare(a.priority(), b.priority())`. Tính ổn định của `sorted` **không sửa được comparator sai**.

### 12.2. Comparator phải thỏa hợp đồng so sánh

Các điều kiện cốt lõi gồm tính phản đối xứng về dấu, tính bắc cầu và sự nhất quán trong việc nhận diện các lớp “so sánh bằng nhau”. Nếu comparator phụ thuộc trạng thái bị mutate trong lúc pipeline chạy, dùng random, hoặc đưa ra quan hệ không bắc cầu, kết quả có thể sai hoặc sắp xếp ném `IllegalArgumentException` trong những trường hợp implementation phát hiện vi phạm hợp đồng.

Ví dụ không nên làm:

~~~java
Comparator<Ticket> inconsistent =
        (a, b) -> new java.util.Random().nextBoolean() ? 1 : -1;
~~~

Đoạn này là **ví dụ anti-pattern**, không phải comparator đúng. Cùng một cặp có thể được so sánh khác nhau ở những lần gọi khác nhau. Không kiểm thử ổn định với comparator như vậy.

### 12.3. `null` và so sánh

`Comparator.comparingInt(Ticket::priority)` yêu cầu đối tượng ticket không `null`; nếu Stream chứa `null` thì lời gọi getter sẽ lỗi. Với dữ liệu có thể `null`, định nghĩa chính sách tường minh:

~~~java
Comparator<Ticket> nullSafe =
        Comparator.nullsLast(
                Comparator.comparingInt(Ticket::priority));
~~~

Nếu bản thân `priority` là một object nullable, cần thêm comparator xử lý null **cho khóa**, không chỉ cho ticket. Với key kiểu `int` của record ở bài này, chỉ cần xem xét trường hợp object Ticket null.

### 12.4. `sorted` không bảo đảm giữ nguyên phần tử “theo equals”

`sorted` không loại trùng, không thay đổi khóa, không làm sạch dữ liệu. Hai phần tử cùng comparator key vẫn đều được giữ. Nếu có nghiệp vụ lọc trùng, phải chọn tiêu chuẩn trùng và thao tác khác; `distinct()` dùng `equals`, không tự đồng nghĩa với comparator bằng 0.

## 13. `sorted()` là intermediate operation có trạng thái

### 13.1. Không nhất thiết chạy khi chỉ tạo pipeline

~~~java
Stream<Ticket> pipeline = input.stream()
        .sorted(byPriority);
~~~

Đây là mảnh mã với `input`/`byPriority` có sẵn. `sorted` là **stateful intermediate operation**. Một pipeline Stream thường lazy: chỉ tạo `pipeline` chưa có nghĩa mọi phần tử đã được duyệt và sắp xếp ngay.

Một terminal operation như `toList()`, `count()` hoặc `forEach(...)` mới kích hoạt đánh giá cần thiết theo ngữ nghĩa API. Lưu ý Stream có thể tối ưu hóa một số pipeline khi không cần thực hiện đầy đủ các bước; vì vậy không nên đưa side effect nghiệp vụ vào comparator và tin rằng nó sẽ được gọi với số lần cụ thể.

### 13.2. Sắp xếp thường phải xét toàn bộ nguồn

Để xuất ra phần tử nhỏ nhất theo comparator tổng quát, `sorted` thường cần kiểm tra và lưu nhiều hoặc tất cả phần tử trước khi phát kết quả. Với nguồn rất lớn, `sorted` có thể cần bộ nhớ và thời gian đáng kể. Một Stream vô hạn mà cần sắp xếp toàn bộ trước khi xuất kết quả có thể không hoàn tất.

Trên ordered parallel Stream, bảo đảm ổn định cũng có thể khiến việc sắp xếp và giữ thứ tự có chi phí cao. Đừng giả định thêm `parallel()` luôn giúp chương trình nhanh hơn; dùng benchmark trên workload thật khi hiệu năng là mục tiêu.

### 13.3. Thứ tự giữa `sorted` và `limit` có ý nghĩa

So sánh:

~~~java
List<Integer> values = List.of(9, 1, 7, 2, 5);

List<Integer> smallestTwo = values.stream()
        .sorted()
        .limit(2)
        .toList();

List<Integer> firstTwoSorted = values.stream()
        .limit(2)
        .sorted()
        .toList();

System.out.println(smallestTwo);     // [1, 2]
System.out.println(firstTwoSorted);  // [1, 9]
~~~

Hai pipeline khác ý nghĩa:

- `sorted().limit(2)` chọn 2 phần tử nhỏ nhất trong toàn nguồn.
- `limit(2).sorted()` chỉ chọn hai phần tử đầu theo encounter order rồi sắp xếp hai phần tử đó.

Sự khác biệt về tập phần tử được xử lý thường quan trọng hơn câu hỏi về ổn định. Khi áp dụng các phép có trạng thái hoặc short-circuit, hãy đặt thứ tự các thao tác theo mục tiêu nghiệp vụ.

### 13.4. Stream đã xử lý không thể tái sử dụng

~~~java
Stream<Integer> s = Stream.of(3, 1, 2);
List<Integer> first = s.sorted().toList();
// s.sorted().toList(); // Không hợp lệ về vòng đời Stream.
~~~

Đoạn trên là ví dụ: sau khi đã tiêu thụ pipeline, không được dùng lại cùng Stream. Tạo Stream mới từ collection hoặc dữ liệu ban đầu nếu cần sắp xếp lại theo comparator khác.

## 14. Phân biệt “ổn định”, “deterministic” và “giữ encounter order”

Ba khái niệm liên quan nhưng không giống nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Stability** | Cặp `compare == 0` có giữ thứ tự tương đối không? | `C(2)` trước `A(2)` sau stable sort |
| **Determinism** | Cùng điều kiện/hợp đồng có đầu ra dự đoán được không? | Có tie-breaker `priority` rồi `code` |
| **Encounter order** | Stream đã có thứ tự phần tử nào trước khi sắp xếp? | `List.stream()` theo thứ tự danh sách |

Trên ordered Stream, `sorted` ổn định, nhưng kết quả hoàn chỉnh còn phụ thuộc encounter order và comparator. Nếu nguồn là một `HashSet` unordered, muốn kết quả theo mã chữ cái trong mỗi nhóm khóa, cần tie-breaker. Nếu dùng `parallel().forEach`, hành động in vẫn có thể không theo thứ tự dù dữ liệu đã được sort.

**Thực hành kiểm thử tốt:** đối chiếu `List` kết quả với `List` mong đợi bằng `assertEquals` (khi dùng thư viện test) hoặc `List.equals`; so sánh từng phần tử theo thứ tự. Không dựa vào vài dòng `println` chạy song song để kết luận sắp xếp bị đảo tie.

## 15. Bài tập thực hành

### Bài 1 — Kiểm tra tie theo độ dài

Cho `List<String> words = List.of("ab", "z", "cd", "x", "efg", "y");`. Sắp xếp theo `String::length` trên ordered Stream. Viết kết quả mong đợi và giải thích vì sao nhóm chuỗi độ dài 1 giữ thứ tự `z, x, y` còn nhóm độ dài 2 giữ `ab, cd`.

**Đáp án định hướng:**

~~~text
[z, x, y, ab, cd, efg]
~~~

### Bài 2 — Kiểu record khác ID, cùng khóa

Định nghĩa `record Order(String id, int priority) {}` với dữ liệu `("C",2),("B",1),("A",2),("D",1)`. Sắp xếp theo priority bằng `Comparator.comparingInt(Order::priority)`; dự đoán `[B, D, C, A]` khi chỉ lấy `id`. So sánh với `thenComparing(Order::id)`.

### Bài 3 — Song song nhưng vẫn ổn định

Dùng cùng ordered `List<Order>`. So sánh:

~~~java
List<Order> sequential = orders.stream()
        .sorted(comparator).toList();
List<Order> parallel = orders.parallelStream()
        .sorted(comparator).toList();

System.out.println(sequential.equals(parallel));
~~~

Mong đợi `true` nếu `comparator` đúng hợp đồng, dữ liệu không đổi, cả hai pipeline cùng ordered và không có side effect ảnh hưởng kết quả. Giải thích vì sao không nên thay kiểm thử List này bằng kiểm tra thứ tự `parallelStream().forEach(System.out::println)`.

### Bài 4 — Bỏ bảo đảm encounter order

Tạo `List<String>`, gọi `stream().unordered().sorted(comparingInt(String::length))`. Giải thích **điều gì vẫn được bảo đảm** (sắp theo độ dài) và **điều gì không được bảo đảm** (thứ tự tie gốc). Vì sao một lần chạy trùng kết quả stable không đủ để kết luận?

### Bài 5 — Comparator có tie-breaker

Tạo `List<Ticket>` với hai ticket cùng `priority` nhưng mã khác nhau. Viết comparator chỉ so priority, sau đó comparator `priority` + `code`. So sánh hai kết quả và chỉ ra việc đổi thứ tự trong nhóm là do **bộ so sánh mới**, không phải do mất stability.

### Bài 6 — Lỗi overflow trong comparator

Thử so sánh `Integer.MIN_VALUE` và `Integer.MAX_VALUE` bằng phép trừ rồi bằng `Integer.compare`. Quan sát kết quả dấu và giải thích tại sao dùng `Comparator.comparingInt` an toàn hơn. Không dùng comparator sai trong phép sort thực tế.

### Bài 7 — `sorted()` kết hợp `limit()`

Với `[9,1,7,2,5]`, tính `sorted().limit(2)` và `limit(2).sorted()`. Giải thích khác biệt lựa chọn phần tử. Thử với danh sách có nhiều phần tử bằng nhau để đánh giá kết quả ổn định khi pipeline giữ encounter order.

### Bài 8 — Source unordered

Dùng `HashSet` chứa các chuỗi dài bằng nhau và một comparator chỉ so độ dài. Đừng viết test đòi một thứ tự tie cụ thể. Sau đó thêm `thenComparing(Comparator.naturalOrder())` để tạo đầu ra xác định theo ký tự, và viết test so sánh đúng List mong đợi.

## 16. Câu hỏi tự kiểm tra

**1. Khi nào `Stream.sorted()` ổn định?** Khi input Stream có encounter order theo hợp đồng của API.

**2. Với unordered Stream thì sao?** Sắp xếp vẫn theo comparator/natural ordering, nhưng không có bảo đảm về thứ tự tương đối của các phần tử comparator đánh giá bằng nhau.

**3. “Bằng nhau” trong tính ổn định là `equals()` hay `compare == 0`?** Là kết quả comparator so sánh bằng 0 (hoặc natural compare cho overload không comparator).

**4. `sorted()` có xóa bản ghi trùng khóa không?** Không, nó sắp xếp, không tự loại phần tử.

**5. `List.parallelStream().sorted(...)` có mất stability?** Không; ordered Stream vẫn được bảo đảm ổn định dù xử lý song song.

**6. Vì sao kết quả `parallelStream().sorted(...).forEach(...)` có thể in lộn thứ tự?** `forEach` không bảo đảm hành động theo encounter order trên parallel Stream.

**7. `unordered()` có trộn ngẫu nhiên phần tử không?** Không; nó bỏ ràng buộc về encounter order, không phải một phép shuffle.

**8. Khi nào dùng `thenComparing`?** Khi nghiệp vụ cần thứ tự phụ rõ ràng, nhất là muốn kết quả deterministic độc lập thứ tự nguồn.

**9. Vì sao không nên dùng `a-b` trong comparator int?** Có thể overflow và làm sai dấu so sánh.

**10. `sorted` là intermediate hay terminal?** Nó là stateful intermediate operation; terminal operation ở cuối kích hoạt việc đánh giá cần thiết.

**11. `sorted().limit(n)` có giống `limit(n).sorted()`?** Không; thứ tự thao tác quyết định tập phần tử nào được chọn.

**12. Có thể dựa vào thứ tự quan sát từ `HashSet` trong một lần chạy để khẳng định ổn định không?** Không, vì nguồn không bảo đảm encounter order.

## 17. Tổng kết

**`sorted()` trong Java bảo đảm stable sort trên Stream có thứ tự.** Điều này nghĩa là các phần tử có kết quả so sánh bằng 0 vẫn giữ thứ tự tương đối theo encounter order ban đầu. Nó không đồng nghĩa giữ vị trí tuyệt đối của mọi phần tử, không yêu cầu `equals()` phải trả true và không tự xóa phần tử trùng khóa.

Đối với unordered Stream, sắp xếp vẫn tuân theo comparator nhưng **không bảo đảm thứ tự tie**. Dùng `thenComparing` khi cần thứ tự phụ xác định; không xem `unordered()` là lệnh shuffle. Trên ordered parallel Stream, stability của `sorted` vẫn có hiệu lực, nhưng `forEach` song song có thể quan sát hành động ngoài encounter order — hãy dùng `toList()` hoặc `forEachOrdered` khi cần kiểm tra hoặc thực thi theo thứ tự.

Comparator phải đúng hợp đồng; ưu tiên `Comparator.comparingInt`/`thenComparing` thay vì phép trừ gây overflow. Nhớ rằng `sorted` là stateful intermediate operation và có thể tốn bộ nhớ khi xử lý nguồn lớn.

**Tài liệu chính thức:** Javadoc Java SE 17 của `java.util.stream.Stream` (các mục `sorted()`, `sorted(Comparator)`, `forEach`, `forEachOrdered`, `unordered`, `toList`), `java.util.Comparator`, `java.util.Spliterator`; phần ordering của Java Stream package documentation.
