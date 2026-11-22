# Phân biệt hàm không giữ trạng thái với thao tác Stream có giữ trạng thái

## 1. Vấn đề cốt lõi: có hai cấp độ “trạng thái”

Khi học Java Stream và functional programming, cụm từ **không giữ trạng thái (stateless)** có thể được dùng ở **hai cấp độ khác nhau**:

1. **Hành vi truyền vào Stream** (*behavioral parameter*) — ví dụ lambda của `map`, `filter`, `peek` hoặc một `Comparator`. Một hành vi được coi là stateless khi kết quả không phụ thuộc vào trạng thái mutable có thể thay đổi trong quá trình xử lý; lý tưởng nhất, cùng đầu vào và cùng điều kiện cố định thì cho cùng kết quả, không cập nhật trạng thái chia sẻ.
2. **Thao tác của pipeline Stream** (*intermediate operation*) — một số thao tác bản thân cần nhớ, đệm hoặc phối hợp thông tin từ nhiều phần tử để quyết định đầu ra. Những thao tác ấy được phân loại **stateful**, ngay cả khi các lambda mà ta truyền vào chúng đều thuần và không có side effect.

Hai cấp độ này **không đồng nhất**. Một pipeline dùng các lambda stateless vẫn có thể chứa `sorted()` hay `distinct()` — đó là những **stateful intermediate operations** hợp lệ và được Java thiết kế sẵn. Ngược lại, `filter()` được phân loại là stateless intermediate operation nhưng **predicate do lập trình viên viết có thể lén giữ trạng thái**, khiến kết quả khó dự đoán, đặc biệt khi chạy song song.

Ví dụ:

~~~java
// Lambda stateless: kết quả chỉ phụ thuộc vào n.
IntStream.rangeClosed(1, 5)
        .filter(n -> n % 2 == 0);

// Stream operation stateful: phải xét phần tử để loại trùng.
IntStream.of(3, 1, 3, 2)
        .distinct();
~~~

Đây là các **đoạn minh họa**, cần import `java.util.stream.IntStream`. Chưa có terminal operation nên chưa tiêu thụ stream.

**Kết luận quan trọng:** “Stream có stateful operation” **không có nghĩa** pipeline vi phạm functional programming. Vấn đề thường nằm ở **stateful lambda, side effect và việc can thiệp nguồn dữ liệu** mà người viết tự đưa vào các behavioral parameters.

## 2. Hàm stateless là gì?

Xét một lambda chuyển số sang bình phương:

~~~java
IntUnaryOperator square = x -> x * x;
~~~

Đây là đoạn minh họa cần import `java.util.function.IntUnaryOperator`.

Với một đầu vào `x` cố định trong miền `int`, lambda không tham chiếu đến bộ đếm đang thay đổi, biến ngoài mutable, thời gian hiện tại hay kết quả lần gọi trước. Ví dụ `square.applyAsInt(4)` luôn trả `16`. Nó được xem là **stateless** đối với dữ liệu đang xử lý.

Một predicate đơn giản:

~~~java
Predicate<String> nonBlank = s -> s != null && !s.isBlank();
~~~

Đây là đoạn minh họa cần import `Predicate`. Nó đưa ra cùng quyết định cho cùng chuỗi đầu vào và không thay đổi dữ liệu ngoài.

### 2.1. Stateless không nhất thiết nghĩa là không dùng bất kỳ dữ liệu ngoài nào

Lambda có thể đóng trên một cấu hình **bất biến**:

~~~java
final int minimum = 10;
IntPredicate allowed = n -> n >= minimum;
~~~

Đoạn minh họa cần import `IntPredicate`. Việc dùng `minimum` là hợp lệ và ổn định: local variable bị capture phải **final hoặc effectively final**. Nó không tự biến lambda thành stateful.

Với một cấu hình object:

~~~java
final Set<String> allowedCodes = Set.of("A", "B");
Predicate<String> allowed = allowedCodes::contains;
~~~

Đây là đoạn minh họa cần import `Set`, `Predicate`. Nếu tập mã không bị thay đổi trong lúc pipeline hoạt động và phép contains không có tác động phụ, hành vi phù hợp với stateless. **Điểm cốt lõi là trạng thái được quan sát có ổn định hay không**, không phải lambda có bao nhiêu biến capture.

### 2.2. Những hành vi dễ làm lambda trở thành stateful

Lambda sau **phụ thuộc vào thứ tự và số lần được gọi**:

~~~java
AtomicInteger index = new AtomicInteger();

Predicate<String> everySecond = word ->
        index.incrementAndGet() % 2 == 0;
~~~

Đây là đoạn minh họa cần import `AtomicInteger`, `Predicate`.

Với cùng đầu vào `"java"`, predicate có thể trả false ở lần gọi thứ nhất và true ở lần gọi thứ hai vì counter đã đổi. **AtomicInteger chỉ làm phép tăng nguyên tử; nó không biến logic phụ thuộc thứ tự thành stateless**. Trong parallel stream, phần tử nào là “thứ hai” phụ thuộc vào cách lập lịch thực thi.

Những dạng phụ thuộc trạng thái thường gặp:

- Dùng `counter++`, `AtomicInteger.incrementAndGet()`, hoặc `List.add(...)` trong `map`/`filter`.
- Đọc một trường `current` mutable bị thread khác thay đổi trong lúc pipeline chạy.
- Quyết định dựa trên `System.currentTimeMillis()` hoặc dữ liệu từ nguồn ngoài luôn biến động.
- Thay đổi chính Collection nguồn khi Stream đang duyệt nguồn đó.
- Ghi log, gửi request, cập nhật database trong một callback và cho rằng nó sẽ luôn chạy đúng một lần cho mỗi phần tử.

Không phải tất cả ví dụ trên đều dẫn tới lỗi biên dịch: **phần lớn vẫn compile được**. Rủi ro nằm ở **tính đúng đắn, tính lặp lại và khả năng song song hóa**.

## 3. Java phân loại thao tác trung gian như thế nào?

Một **intermediate operation** tạo Stream mới từ Stream trước đó, thường không thực thi ngay do Stream **lazy**. Ở mức hợp đồng Stream, các thao tác thường được phân thành:

| Thao tác | Phân loại | Cơ chế tiêu biểu |
| --- | --- | --- |
| `map(f)` | **Stateless** | Chuyển từng phần tử bằng `f` |
| `mapToInt(f)` / `flatMap(f)` | **Stateless** | Biến đổi/làm phẳng phần tử, không cần nhớ tập phần tử trước |
| `filter(p)` | **Stateless** | Quyết định giữ một phần tử dựa trên predicate |
| `peek(action)` | **Stateless** | Quan sát phần tử đi qua bước, không tự cần lưu tập đã thấy |
| `distinct()` | **Stateful** | Nhận biết những phần tử đã gặp để bỏ trùng |
| `sorted()` | **Stateful** | Cần xét nhiều phần tử để xác định thứ tự toàn cục |
| `limit(n)` | **Stateful** | Cần theo dõi số phần tử được phát, có tính short-circuit |
| `skip(n)` | **Stateful** | Cần biết đã bỏ bao nhiêu phần tử |
| `takeWhile(p)` / `dropWhile(p)` | **Stateful** | Quyết định ranh giới prefix theo thứ tự và kết quả predicate |

**Lưu ý:** Phân loại ở bảng là **đặc tính của thao tác Stream**, không phải sự đảm bảo lambda mà lập trình viên truyền vào là stateless. `map(n -> counter.incrementAndGet())` vẫn là gọi một **stateless intermediate operation map**, nhưng lambda bên trong lại **phụ thuộc mutable state** — một thiết kế có nguy cơ sai.

Một số thao tác có thể giữ thông tin rất nhỏ thay vì đệm toàn bộ nguồn. Ví dụ `limit(n)` theo dõi số lượng cần lấy; nó không buộc phải lưu mọi phần tử. Vì thế **stateful không đồng nghĩa với “tải toàn bộ dữ liệu vào RAM”**.

## 4. Ví dụ Java 17: cùng một dữ liệu, hai loại operation

Tạo tệp **StreamStateKindsDemo.java**:

~~~java
import java.util.List;

public class StreamStateKindsDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(5, 2, 5, 1, 2, 3);

        List<Integer> stateless = source.stream()
                .map(n -> n * 2)
                .filter(n -> n >= 4)
                .toList();

        List<Integer> stateful = source.stream()
                .distinct()
                .sorted()
                .limit(3)
                .toList();

        System.out.println("Stateless stages: " + stateless);
        System.out.println("Stateful stages: " + stateful);
        System.out.println("Source: " + source);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac StreamStateKindsDemo.java
java StreamStateKindsDemo
~~~

Stdout:

~~~text
Stateless stages: [10, 4, 10, 4, 6]
Stateful stages: [1, 2, 3]
Source: [5, 2, 5, 1, 2, 3]
~~~

Giải thích:

1. Ở pipeline thứ nhất, `map(n -> n * 2)` biến dữ liệu thành `[10,4,10,2,4,6]`. `filter(n >= 4)` bỏ giá trị `2`, không cần biết các phần tử khác. Hai bước là **stateless intermediate operations**.
2. Pipeline thứ hai dùng `distinct()` để loại trùng: các giá trị duy nhất theo encounter order là `[5,2,1,3]`. `sorted()` xếp thành `[1,2,3,5]`. `limit(3)` chọn ba giá trị đầu và trả `[1,2,3]`.
3. Cả ba thao tác ở pipeline thứ hai được **phân loại stateful** theo Stream API nhưng hoàn toàn hợp lệ và không cần tự viết counter hay sửa nguồn.
4. `source` giữ nguyên, vì các thao tác ở đây không can thiệp collection nguồn.

**Một nuance:** `distinct()` trên một stream có thứ tự giữ phần tử đại diện đầu tiên theo thứ tự gặp. Với nguồn unordered, lựa chọn phần tử đại diện và thứ tự duyệt có thể khác; không nên dùng một kết quả cụ thể của HashSet làm bằng chứng về encounter order.

## 5. Tại sao map/filter là stateless operation?

Về mặt mô hình, `map(f)` có thể áp dụng `f` lên phần tử hiện tại mà không cần chờ toàn bộ luồng:

~~~text
n = 3  -> map(n * 2) -> 6
n = 5  -> map(n * 2) -> 10
n = 2  -> map(n * 2) -> 4
~~~

Tương tự, `filter(p)` chỉ cần biết p(x) của phần tử x hiện tại để quyết định có phát x hay không. Khi các behavioral parameters cũng stateless/non-interfering, Stream có thể **fuse** các bước liên tiếp trong pipeline tuần tự:

~~~text
source element 1 -> map -> filter -> downstream
source element 2 -> map -> filter -> downstream
source element 3 -> map -> filter -> downstream
~~~

Đây là sơ đồ khái niệm, không phải cam kết về mọi chi tiết triển khai. Pipeline có stateful operation hoặc chạy song song có thể tổ chức dữ liệu khác.

### 5.1. flatMap cũng được phân loại stateless

`flatMap` có thể tạo một Stream con từ **mỗi phần tử nguồn** rồi phát các phần tử con. Ví dụ:

~~~java
List<String> tokens = List.of("a,b", "c").stream()
        .flatMap(s -> java.util.Arrays.stream(s.split(",")))
        .toList();
~~~

Đây là đoạn minh họa cần import List. Kết quả là `[a, b, c]`. `flatMap` không cần nhớ tất cả token từ các phần tử trước để quyết định token của phần tử hiện tại.

Tuy nhiên, mapper `s -> ...` **vẫn có thể được viết sai** nếu nó dùng cùng một Stream con bị tiêu thụ nhiều lần hoặc ghi shared mutable state. Việc operation được phân loại stateless **không chứng nhận** mọi mapper là an toàn.

### 5.2. peek là stateless operation nhưng action có side effect

`peek(action)` thường được dùng để quan sát lúc gỡ lỗi:

~~~java
List<Integer> values = List.of(1, 2, 3).stream()
        .peek(n -> System.out.println("seen: " + n))
        .map(n -> n * 2)
        .toList();
~~~

Đây là đoạn minh họa. `peek` **không được xếp stateful** chỉ vì action in log; bản thân thao tác không cần nhớ các phần tử đã qua.

Nhưng action có **side effect** và Java Stream có quyền tối ưu hóa một số pipeline hoặc dừng sớm, nên **không dùng peek cho công việc bắt buộc** như ghi audit hay cập nhật trạng thái. `peek(...).count()` trên nguồn có kích thước xác định có thể không gọi action vì count được tính trực tiếp; log không phải bằng chứng đáng tin về số phần tử đã xử lý.

**Phân biệt rõ ba câu hỏi:**
- Operation có giữ trạng thái nội bộ? Với peek: **không**.
- Callback có side effect? `System.out.println`: **có**.
- Side effect ấy có được cam kết thực hiện cho mỗi phần tử? **Không nên giả định** trong Stream pipeline.

## 6. distinct(): cần thông tin về phần tử đã thấy

`distinct()` loại các phần tử trùng theo `Object.equals` trên object stream, hoặc theo semantics giá trị của primitive stream. Để quyết định phần tử đang xét có mới không, thao tác cần thông tin về những phần tử trước hoặc một cấu trúc tương đương.

Ví dụ:

~~~java
List<String> unique = List.of("A", "B", "A", "C", "B")
        .stream()
        .distinct()
        .toList();
~~~

Đây là đoạn minh họa cần import List. Với nguồn List có thứ tự, kết quả là **[A, B, C]**.

**Stateful là đặc tính hợp lệ của distinct:** Java quản lý cấu trúc nhận diện trùng trong framework; lập trình viên **không nên** thay bằng:

~~~java
Set<String> seen = new HashSet<>();
List<String> unique = source.stream()
        .filter(seen::add)
        .toList();
~~~

Đây là **phản mẫu minh họa** cần import Set, HashSet, List và có biến source. Dù với một số pipeline tuần tự nó có thể tạo kết quả tương tự, `seen::add` **sửa một Set bên ngoài** trong predicate. Trong parallel stream, HashSet không thread-safe, có thể có race và kết quả sai. Dùng synchronized set chỉ khắc phục một phần an toàn dữ liệu, không thay thế semantics có thứ tự và tối ưu của distinct.

Dùng thẳng:

~~~java
List<String> unique = source.stream().distinct().toList();
~~~

Đây là cách diễn đạt ý định đúng khi muốn loại phần tử trùng.

### 6.1. Equality và object mutable

Nếu `distinct()` xử lý các object mutable mà `equals/hashCode` phụ thuộc trường thay đổi trong lúc xử lý, kết quả có thể không đáng tin. Dữ liệu dùng để so trùng nên có **định danh và quy tắc equality ổn định** trong pipeline. Statefulness do distinct tự quản lý không bảo đảm mọi object đầu vào đều bất biến.

## 7. sorted(): thường cần nhìn nhiều phần tử trước khi phát kết quả

`sorted()` hoặc `sorted(comparator)` phải xác định thứ tự các phần tử. Với một stream hữu hạn thông thường, điều này thường dẫn đến việc **đệm và sắp xếp** dữ liệu trước khi phát theo thứ tự mong muốn.

Ví dụ:

~~~java
List<Integer> ordered = List.of(4, 1, 3, 2)
        .stream()
        .sorted()
        .toList();
~~~

Kết quả: **[1, 2, 3, 4]**.

Không thể áp dụng `sorted()` đơn giản kiểu “nhìn một phần tử là biết ngay phần tử đầu tiên nhỏ nhất” khi nguồn chưa kết thúc. Đây là điểm trực quan giúp hiểu vì sao sorted **stateful** còn map/filter **stateless**.

### 7.1. Quan sát buffering bằng peek

Tạo tệp **SortedBoundaryDemo.java**:

~~~java
import java.util.List;

public class SortedBoundaryDemo {
    public static void main(String[] args) {
        List<Integer> output = List.of(4, 1, 3, 2)
                .stream()
                .peek(n -> System.out.println("before=" + n))
                .sorted()
                .peek(n -> System.out.println("after=" + n))
                .toList();

        System.out.println("result=" + output);
    }
}
~~~

Chạy:

~~~bash
javac SortedBoundaryDemo.java
java SortedBoundaryDemo
~~~

Stdout trong pipeline tuần tự của ví dụ:

~~~text
before=4
before=1
before=3
before=2
after=1
after=2
after=3
after=4
result=[1, 2, 3, 4]
~~~

**Diễn giải:** Các giá trị được quan sát trước sorted theo thứ tự nguồn, sau sorted theo thứ tự tăng dần. Đây là minh họa hữu ích cho ranh giới stateful.

**Không coi thứ tự dòng log peek là hợp đồng tổng quát** khi chuyển sang parallel stream hoặc khi JVM có tối ưu khác. Hãy kiểm tra dữ liệu kết quả và yêu cầu encounter order thay vì kiểm tra một thứ tự side effect không được API cam kết trong mọi trường hợp.

### 7.2. Comparator nên stateless và nhất quán

`sorted(comparator)` dùng comparator để so sánh nhiều cặp phần tử. Comparator không nên dựa vào biến counter, random hay field mutable thay đổi trong khi sort. Nếu cùng một cặp giá trị bị so sánh nhiều lần nhưng cho kết quả mâu thuẫn, quá trình sort có thể tạo thứ tự sai hoặc ném ngoại lệ vi phạm hợp đồng so sánh.

Ví dụ phù hợp:

~~~java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());
~~~

Đoạn minh họa cần import Comparator. Comparator ổn định trên các String immutable và trả thứ tự xác định: trước theo độ dài, sau theo thứ tự tự nhiên.

## 8. limit(), skip(), takeWhile(), dropWhile(): stateful theo vị trí/ranh giới

Không phải stateful operation nào cũng phải đệm toàn bộ nguồn. Một số cần nhớ **vị trí tương đối** hay **trạng thái đã vượt qua ranh giới**.

### 8.1. limit(n)

`limit(n)` phát tối đa n phần tử (khi n không âm). Nó là stateful **short-circuiting intermediate operation**: nếu đã đủ n phần tử đầu ra, phần còn lại không cần được yêu cầu trong nhiều pipeline.

~~~java
List<Integer> firstThree = IntStream.rangeClosed(1, 10)
        .limit(3)
        .boxed()
        .toList();
~~~

Kết quả là **[1, 2, 3]**. Đây là đoạn minh họa với import IntStream, List.

### 8.2. skip(n)

`skip(n)` bỏ qua n phần tử đầu của stream có encounter order. Nó cần xác định đã bỏ qua bao nhiêu phần tử, nên là stateful.

~~~java
List<Integer> remaining = IntStream.rangeClosed(1, 6)
        .skip(2)
        .boxed()
        .toList();
~~~

Kết quả là **[3, 4, 5, 6]**.

### 8.3. takeWhile / dropWhile (Java 9+)

Với **ordered stream**, `takeWhile(p)` giữ prefix dài nhất gồm các phần tử liên tiếp thỏa p, còn `dropWhile(p)` bỏ prefix dài nhất ấy rồi phát phần còn lại.

~~~java
List<Integer> take = IntStream.of(1, 2, 3, 0, 4, 5)
        .takeWhile(n -> n > 0)
        .boxed()
        .toList();

List<Integer> drop = IntStream.of(1, 2, 3, 0, 4, 5)
        .dropWhile(n -> n > 0)
        .boxed()
        .toList();
~~~

Với ví dụ này, `take = [1, 2, 3]` và `drop = [0, 4, 5]`. **Khác với filter**, takeWhile **dừng lấy khi gặp phần tử đầu tiên không thỏa**, không tiếp tục chọn các số dương phía sau.

### 8.4. Hệ quả của encounter order

Với stream có encounter order, `limit/skip/takeWhile/dropWhile` mang nghĩa prefix/vị trí được chỉ định; khi nguồn **unordered** hoặc pipeline đã dùng `unordered()`, khả năng chọn phần tử có thể khác, tùy hợp đồng từng thao tác.

Đặc biệt, `limit` và `skip` trên **ordered parallel stream** có thể đắt hơn vì phải giữ đúng thứ tự tương đối. Chỉ chuyển sang `unordered()` nếu **nghiệp vụ thực sự không quan tâm phần tử cụ thể nào được giữ/bỏ**, không phải chỉ để tối ưu hiệu năng.

## 9. Ví dụ Java 17: slice và short-circuit với dữ liệu vô hạn

Tạo tệp **SliceAndWhileDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class SliceAndWhileDemo {
    public static void main(String[] args) {
        List<Integer> firstEven = IntStream.iterate(1, n -> n + 1)
                .filter(n -> n % 2 == 0)
                .limit(3)
                .boxed()
                .toList();

        List<Integer> take = IntStream.of(1, 2, 3, 0, 4, 5)
                .takeWhile(n -> n > 0)
                .boxed()
                .toList();

        List<Integer> drop = IntStream.of(1, 2, 3, 0, 4, 5)
                .dropWhile(n -> n > 0)
                .boxed()
                .toList();

        System.out.println("Even: " + firstEven);
        System.out.println("Take: " + take);
        System.out.println("Drop: " + drop);
    }
}
~~~

Chạy:

~~~bash
javac SliceAndWhileDemo.java
java SliceAndWhileDemo
~~~

Stdout:

~~~text
Even: [2, 4, 6]
Take: [1, 2, 3]
Drop: [0, 4, 5]
~~~

**Phân tích:**

1. `IntStream.iterate(1, n -> n + 1)` tạo một luồng không có điểm kết thúc xác định. Predicate của filter chỉ chọn số chẵn.
2. `limit(3)` là thao tác có khả năng short-circuit và chỉ cần ba số chẵn đầu tiên. Vì vậy, pipeline có thể kết thúc dù nguồn iterate về mặt khái niệm là vô hạn.
3. `takeWhile(n > 0)` trên luồng hữu hạn có thứ tự dừng khi gặp 0; nó không chọn 4 và 5 dù chúng vẫn dương.
4. `dropWhile(n > 0)` bỏ 1, 2, 3 rồi phát 0, 4, 5.
5. Predicate `n -> n > 0` **stateless**; thao tác `takeWhile/dropWhile` **stateful** do cần nhớ trạng thái đã gặp ranh giới.

**Điểm hiệu năng:** Đặt `sorted()` trên **stream vô hạn** rồi chờ `limit(3)` thông thường không thể lấy được ba giá trị đầu vì sorted cần hoàn tất sắp xếp trước khi biết thứ tự toàn cục. Ngược lại, `limit(3).sorted()` chỉ phải sắp xếp một tập hữu hạn ba phần tử. **Thứ tự các stage không chỉ ảnh hưởng kết quả mà còn ảnh hưởng tính kết thúc và bộ nhớ.**

## 10. Một lambda stateful có thể làm filter sai thế nào?

Tạo tệp **StatefulPredicateDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;

public class StatefulPredicateDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "bb", "ccc");
        AtomicInteger calls = new AtomicInteger(0);

        Predicate<String> everySecondCall = text ->
                calls.incrementAndGet() % 2 == 0;

        System.out.println("First: " + words.stream()
                .filter(everySecondCall).toList());

        System.out.println("Second: " + words.stream()
                .filter(everySecondCall).toList());

        Predicate<String> lengthAtLeastTwo =
                text -> text.length() >= 2;

        System.out.println("Stateless: " + words.stream()
                .filter(lengthAtLeastTwo).toList());

        System.out.println("Again: " + words.stream()
                .filter(lengthAtLeastTwo).toList());
    }
}
~~~

Chạy:

~~~bash
javac StatefulPredicateDemo.java
java StatefulPredicateDemo
~~~

Stdout của chương trình **tuần tự**:

~~~text
First: [bb]
Second: [a, ccc]
Stateless: [bb, ccc]
Again: [bb, ccc]
~~~

Giải thích:

1. Lượt thứ nhất gọi predicate ba lần: đếm 1 (loại "a"), 2 (giữ "bb"), 3 (loại "ccc").
2. Lượt thứ hai **dùng lại chính Predicate với AtomicInteger chưa reset**: đếm 4 (giữ "a"), 5 (loại "bb"), 6 (giữ "ccc").
3. Cùng danh sách đầu vào nhưng kết quả filter khác nhau, vì predicate phụ thuộc **lịch sử số lần gọi**, không chỉ giá trị phần tử.
4. `lengthAtLeastTwo` chỉ đọc độ dài String, nên hai lần cho cùng `[bb, ccc]`.

**Ví dụ stateful predicate này dùng để minh họa lỗi thiết kế**, không phải một pattern nên áp dụng. Nếu chuyển sang parallel stream, số lần gọi có thể vẫn tương ứng số phần tử được xét trong trường hợp cụ thể này nhưng **phần tử nào nhận số đếm nào là không đáng dựa vào**. AtomicInteger bảo vệ cập nhật counter khỏi race ở mức phép tăng, không bảo vệ ý nghĩa “phần tử thứ hai theo encounter order”.

### 10.1. Vì sao external mutable state nguy hiểm hơn dùng distinct?

Với `distinct()`, Java biết đây là một stateful intermediate operation, chịu trách nhiệm tổ chức việc nhận diện trùng và kết hợp kết quả theo hợp đồng. Với `filter(seen::add)`, Java chỉ thấy một filter mà theo contract behavioral parameters cần **non-interfering** và nhìn chung **stateless**. Trạng thái `seen` nằm ngoài cơ chế collector/operation được quản lý; Stream không có cách diễn giải nó là phép loại trùng với thứ tự ổn định khi tối ưu hoặc song song.

Vì vậy, **ưu tiên `distinct()`**, không viết `filter` tự duy trì Set đã thấy. Tương tự, ưu tiên **`limit(n)`** thay vì `filter` phụ thuộc counter để lấy n phần tử.

## 11. Stateless không hoàn toàn giống pure; side effect cũng là vấn đề riêng

Một hàm **pure (thuần)** thường có các tính chất: cùng đầu vào cho cùng kết quả và **không có side effect có thể quan sát**. Một lambda **stateless** trong nghĩa Stream thường không phụ thuộc mutable state qua các lần gọi; nhưng một callback vẫn có thể gây side effect dù không cần nhớ kết quả lần trước.

Ví dụ:

~~~java
Consumer<String> logger = text -> System.out.println(text);
~~~

Nó không cần bộ nhớ để quyết định giá trị trả về, nhưng **in console là side effect**. Vì `Consumer` không trả giá trị, khái niệm purity của nó cần xét theo nghĩa hành động thay vì hàm ánh xạ; nó không phải phép biến đổi thuần.

Một phép biến đổi có side effect:

~~~java
Function<String, String> withLog = text -> {
    System.out.println("processing " + text);
    return text.strip();
};
~~~

Đây là đoạn minh họa cần import Function. Giá trị trả về được tính từ text, nhưng callback ghi log, và Stream không cam kết mỗi callback đều được gọi trong mọi tối ưu.

**Tách biệt ba câu hỏi:**

| Câu hỏi | Ví dụ | Hệ quả |
| --- | --- | --- |
| Operation có stateful? | `sorted()` | Cần phối hợp giữa các phần tử |
| Behavioral parameter có dùng mutable state? | `filter(x -> ++count % 2 == 0)` | Dễ phụ thuộc lịch sử gọi, không an toàn |
| Callback có side effect? | `peek(System.out::println)` | Không dùng làm logic nghiệp vụ bắt buộc |

Có thể có một **stateful Stream operation** hoàn toàn hợp lệ dùng một **comparator thuần**. Cũng có thể có một **stateless Stream operation** sử dụng **callback side-effectful**. Không nên suy luận tất cả tính chất chỉ từ một nhãn “stateful”.

## 12. Non-interference: không sửa nguồn đang được duyệt

Stream API yêu cầu behavioral parameters nhìn chung **không can thiệp vào nguồn dữ liệu** (*non-interfering*). Điều này có nghĩa không sửa collection nguồn trong khi stream đang duyệt, trừ những nguồn được thiết kế hỗ trợ concurrent modification theo hợp đồng riêng.

Phản mẫu:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

numbers.stream()
        .peek(n -> numbers.add(n + 10))
        .toList();
~~~

Đây là **đoạn phản mẫu minh họa** cần import ArrayList, List; không nên chạy trong ứng dụng thật. Hành động `numbers.add(...)` thay đổi chính ArrayList đang làm nguồn. Nó có thể gây `ConcurrentModificationException`, hành vi khó dự đoán hoặc khiến pipeline bị tối ưu theo cách bỏ qua side effect.

Cách rõ nghĩa hơn nếu muốn tạo một danh sách mới:

~~~java
List<Integer> result = numbers.stream()
        .map(n -> n + 10)
        .toList();
~~~

Đây là đoạn minh họa. `map` tạo giá trị đầu ra mới mà không thay đổi nguồn.

Nếu mục tiêu thật sự là cập nhật dữ liệu mutable (ví dụ thanh toán, thay đổi trạng thái hồ sơ), nên dùng **quy trình tường minh có ranh giới lỗi, thứ tự và transaction rõ**, không giấu việc cập nhật trong `peek` hay `map`.

## 13. Stateful operation và tính lazy của Stream

Stream là **lazy**: các intermediate operations chỉ mô tả pipeline; công việc thường diễn ra khi terminal operation yêu cầu kết quả.

Ví dụ:

~~~java
Stream<Integer> pipeline = Stream.of(3, 1, 2).sorted();
~~~

Ở dòng này, ta mới tạo một pipeline với stateful `sorted()`; **chưa bắt buộc có việc sắp xếp thực tế** cho tới khi terminal operation tiêu thụ nó.

~~~java
List<Integer> sorted = pipeline.toList();
~~~

Lúc đó, Stream phải tạo kết quả theo thứ tự đã sắp xếp.

Nhưng **terminal operation không đảm bảo mọi callback trung gian luôn chạy**. Ví dụ:

~~~java
long count = List.of(1, 2, 3).stream()
        .map(n -> {
            System.out.println("map " + n);
            return n * 2;
        })
        .count();
~~~

Đây là đoạn minh họa. Với nguồn kích thước đã biết và pipeline không thay đổi số lượng phần tử, `count()` có thể tính **3** mà không duyệt qua `map`, nên không có bảo đảm sẽ in ba dòng log.

**Ý nghĩa:** Không nên dùng side effect trong behavioral parameters làm bằng chứng đã xử lý từng phần tử. Tính lazy và khả năng tối ưu là đặc tính API, không phải lỗi.

### 13.1. Stateful operation có luôn buộc duyệt hết không?

**Không.** `sorted()` với đầu vào hữu hạn không có thông tin thứ tự sẵn thường cần toàn bộ dữ liệu để sắp xếp. Nhưng `limit(3)` có thể kết thúc sớm; `distinct().limit(3)` có thể dừng sau khi tìm được ba phần tử phân biệt mà không cần đọc hết nguồn, tùy cấu trúc pipeline và tính thứ tự.

Chính vì thế, **stateful** không đồng nghĩa với **blocking toàn luồng**. Cần phân tích **cơ chế cụ thể** của từng operation.

## 14. Ordered, unordered và parallel: khi statefulness trở nên đắt đỏ

Một số stateful operations chịu thêm chi phí khi giữ **encounter order** trong pipeline song song:

- **distinct()** trên ordered parallel stream cần giữ sự ổn định theo thứ tự gặp đối với phần tử đại diện, có thể cần buffering/phối hợp.
- **limit(n)** và **skip(n)** trên ordered parallel stream phải tôn trọng đúng prefix/offset; điều này có thể khiến việc phối hợp tốn chi phí.
- **sorted()** phải xác lập thứ tự tổng thể cho kết quả, nên không thể xử lý như map độc lập trên từng phần tử.
- **takeWhile/dropWhile** trên ordered parallel stream cần nhận diện ranh giới prefix; API cảnh báo có thể tốn chi phí hơn so với sequential.

Đôi khi có thể dùng `unordered()` nếu đầu ra **không cần giữ vị trí hay thứ tự gặp**:

~~~java
Set<Integer> selected = IntStream.rangeClosed(1, 1000)
        .parallel()
        .unordered()
        .limit(10)
        .boxed()
        .collect(Collectors.toSet());
~~~

Đây là đoạn minh họa cần import Set, IntStream, Collectors. Chỉ có thể khẳng định **tối đa 10 phần tử phân biệt** từ nguồn đã cho; **không được hứa chính xác là 1..10** khi pipeline unordered. Trong ví dụ với các số phân biệt, có thể thu được 10 phần tử, nhưng tập cụ thể không nên là hợp đồng.

**Không chuyển sang unordered() nếu nghiệp vụ cần “10 bản ghi đầu tiên theo ngày”**. Để tối ưu an toàn, trước hết xác nhận tính thứ tự có quan trọng hay không.

### 14.1. Một kết quả đúng nhưng log khác thứ tự

Parallel stream có thể xử lý từng phần tử trên nhiều thread, nên log từ `peek` hoặc `map` có thể xen kẽ dù kết quả `toList()` của nguồn có encounter order được trả về theo thứ tự.

Ví dụ:

~~~java
List<Integer> result = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * 10)
        .boxed()
        .toList();
~~~

Đây là đoạn minh họa. Kết quả vẫn là **[10, 20, 30, 40, 50]** theo encounter order. Nếu thêm log ở từng mapper, thứ tự log **không** cần giống thứ tự kết quả.

Đây là lý do một counter trong mapper không phù hợp để định nghĩa “số thứ tự của phần tử trong danh sách cuối”.

## 15. Collectors có accumulator mutable nhưng không đồng nghĩa lambda stateful sai

Đôi khi người học nghĩ: “Nếu functional programming nên stateless, tại sao `collect` lại dùng ArrayList/HashMap mutable để tích lũy?”

Đó là **một cơ chế khác**. `collect` là terminal **mutable reduction**, trong đó Supplier tạo container, accumulator thêm phần tử, và combiner kết hợp các container khi cần. Trạng thái được **quản lý theo hợp đồng của Collector**, không phải một biến shared tùy tiện bị ghi trong `filter`.

Ví dụ:

~~~java
ArrayList<String> result = Stream.of("a", "b", "c")
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa cần import ArrayList, Stream, Collectors. `ArrayList` là mutable container đích; việc collect vào nó là hoàn toàn bình thường.

Phản mẫu:

~~~java
List<String> outside = new ArrayList<>();

source.parallelStream()
        .forEach(outside::add);
~~~

Đây là đoạn minh họa, giả định source là collection phù hợp. ArrayList không thread-safe cho nhiều thread cùng `add`. Ngay cả khi thêm synchronized, thứ tự các phần tử trong outside có thể không tương ứng encounter order. Nếu mục tiêu là **thu gom kết quả**, chọn Collector phù hợp thay vì chia sẻ một List bên ngoài.

**Phân biệt thuật ngữ:**

- `sorted`, `distinct`, `limit`, `skip`: **stateful intermediate operations**.
- `map`, `filter`, `peek`: **stateless intermediate operations** về thiết kế Stream.
- `collect`: **terminal mutable reduction**, được quản lý bởi Collector.
- `filter(x -> sharedCounter.incrementAndGet() ...)`: **stateful behavioral parameter**, thường nguy hiểm cho ý nghĩa pipeline.

## 16. Có cần tránh mọi stateful operation không?

**Không.** Stateful operations là thành phần chuẩn của Stream API để biểu đạt những yêu cầu thực tế:

- `distinct()` khi cần loại bản sao.
- `sorted()` khi cần thứ tự toàn cục.
- `limit(n)` và `skip(n)` khi cần lấy một đoạn theo vị trí.
- `takeWhile` và `dropWhile` khi cần xử lý prefix trên ordered stream.

Điều nên tránh là **đưa mutable state ngoài vào behavioral parameters một cách không kiểm soát** hoặc dùng side effect trong Stream như phần bắt buộc của quy trình nghiệp vụ.

Chọn Stream với stateful operation hay vòng lặp dựa trên **độ rõ nghĩa, bộ nhớ, khả năng kết thúc, thứ tự và hiệu năng**. Nếu cần một thuật toán phức tạp có trạng thái (máy trạng thái, cập nhật sổ cái, retry có thứ tự, so sánh cặp phần tử liên tiếp), vòng lặp tường minh hoặc abstraction chuyên biệt đôi khi dễ hiểu và an toàn hơn việc ép vào các lambda sử dụng counter ngoài.

## 17. Những lỗi phổ biến

| Ngộ nhận/lỗi | Điều sai | Cách xử lý |
| --- | --- | --- |
| “Stream có sorted là lập trình hàm sai vì dùng trạng thái” | Sorted tự quản lý trạng thái theo API | Dùng sorted khi cần sắp xếp, đánh giá chi phí |
| “filter là stateless nên mọi predicate đều stateless” | Predicate có thể dùng counter/shared Set | Viết predicate dựa trên input và cấu hình ổn định |
| “AtomicInteger giúp lambda trở nên stateless” | Atomic chỉ giúp cập nhật nguyên tử | Không dùng counter để quyết định thứ tự phần tử |
| “distinct giống filter(seen::add)” | seen là external mutable state, có race | Dùng distinct |
| “takeWhile giống filter” | takeWhile chỉ giữ prefix liên tiếp | Phân biệt ranh giới và bộ lọc toàn bộ nguồn |
| “Mọi stateful operation đều đọc hết nguồn” | limit có thể short-circuit | Xét cơ chế từng operation |
| “limit sau sorted trên nguồn vô hạn sẽ lấy được kết quả” | Sorted có thể không kết thúc | Giới hạn nguồn trước khi sorted nếu đúng yêu cầu |
| “parallel log sẽ theo thứ tự kết quả” | Task chạy đồng thời | Dựa vào dữ liệu kết quả/encounter order |
| “peek là stateful operation vì có print” | Operation stateless, action có side effect | Tách khái niệm operation và callback |
| “collect dùng List mutable là sai” | Mutable reduction là hợp đồng chuẩn | Dùng Collector, tránh shared external list |
| “map luôn chạy đúng một lần cho mỗi phần tử nguồn” | Lazy/optimization/short-circuit | Không dựa vào side effect trong map |
| “unordered() luôn tăng tốc và không thay đổi nghiệp vụ” | Có thể thay đổi phần tử được chọn/giữ | Chỉ unordered khi thứ tự không quan trọng |
| “Comparator có thể đọc random” | Quy tắc so sánh không nhất quán | Dùng comparator ổn định, đúng hợp đồng |
| “Stateful lambda tự gán index sẽ giống vị trí List” | Thứ tự gọi không nhất thiết là encounter order | Sử dụng nguồn có index hoặc cấu trúc dữ liệu phù hợp |

## 18. Checklist khi viết pipeline Stream

1. **Tôi đang nói về trạng thái của operation hay lambda?** Tách rõ hai cấp độ.
2. **Các mapper/predicate có chỉ phụ thuộc vào input và cấu hình ổn định không?**
3. **Có `counter++`, `seen.add`, `List.add` hoặc cập nhật trường dùng chung không?** Cân nhắc thiết kế lại.
4. **Có sửa nguồn trong lúc duyệt không?** Tránh vi phạm non-interference.
5. **Operation nào cần nhiều phần tử để quyết định?** Phân tích distinct/sorted/limit/skip/takeWhile/dropWhile.
6. **Có short-circuit không?** Một số phần tử không được xử lý là điều hợp lệ.
7. **Nguồn hữu hạn hay vô hạn?** Sorted trước limit có thể khiến pipeline không kết thúc.
8. **Encounter order có quan trọng không?** Quyết định có thể dùng unordered/parallel không.
9. **Có dùng log trong peek/map để suy luận số lượt xử lý không?** Đừng biến log thành dữ liệu nghiệp vụ.
10. **Có cần tích lũy dữ liệu không?** Dùng collect/reduce/count/sum thích hợp thay vì List ngoài.
11. **Lambda có chạy trong parallel stream không?** Tránh shared mutable state, comparator bất ổn, tác động phụ có thứ tự.
12. **Đã kiểm thử đầu vào rỗng, trùng, thứ tự, short-circuit và trường hợp nhiều lần chạy chưa?**

## 19. Bài tập tự luyện

### Bài 1: Phân loại operation và callback

Cho pipeline:

~~~java
words.stream()
        .map(String::strip)
        .distinct()
        .sorted()
        .filter(s -> s.length() > 2)
        .limit(5)
        .toList();
~~~

Đây là đoạn minh họa, giả định words là List<String> không có null.

Hãy xác định thao tác trung gian nào **stateless**, thao tác nào **stateful**, và giải thích vì sao `String::strip` là hành vi stateless. Đáp án: map và filter là stateless; distinct, sorted, limit là stateful.

### Bài 2: Phản mẫu đếm phần tử

Viết một `Predicate<Integer>` dựa trên AtomicInteger để giữ “mỗi phần tử thứ hai”. Chạy hai lần trên cùng List với hai Stream mới nhưng dùng lại Predicate. Giải thích vì sao kết quả có thể khác nhau và tại sao chuyển sang parallel làm ngữ nghĩa tệ hơn.

### Bài 3: Chọn API thay vì shared Set

Từ List `[1,2,1,3,2]`, thử `distinct().toList()` và đối chiếu với `filter(seen::add)` khi chạy tuần tự. Vì sao cách thứ hai không nên được dùng trong parallel stream? Điều gì xảy ra khi dùng lại Set seen từ lượt trước?

### Bài 4: Stateful operation trên nguồn vô hạn

Tạo một `IntStream.iterate(1,n -> n+1)`. So sánh ý nghĩa và tính kết thúc của `limit(5).sorted().toList()` với `sorted().limit(5).toList()`. Phân tích mà không cố chạy biến thể có thể không dừng.

### Bài 5: takeWhile vs filter

Dùng nguồn `[1,2,0,3,4]`. So sánh `filter(n -> n > 0)`, `takeWhile(n -> n > 0)` và `dropWhile(n -> n > 0)`. Dự đoán ba kết quả: `[1,2,3,4]`, `[1,2]` và `[0,3,4]`.

### Bài 6: Ordered parallel và limit

Thử một `IntStream.rangeClosed(1,1000).parallel().limit(10)`; giải thích vì sao hợp đồng của ordered stream vẫn nhắm tới 10 phần tử đầu theo encounter order. Sau đó thêm `unordered()` và nêu vì sao không nên cam kết cùng 10 phần tử theo vị trí nguồn.

### Bài 7: Distinct và comparator

Tại sao `distinct()` trên object stream dựa vào `equals` trong khi `sorted(comparator)` dựa vào comparator? Điều gì có thể xảy ra nếu comparator phụ thuộc vào trường mutable bị thay đổi trong khi sort?

### Bài 8: Thu gom song song

Thay `parallelStream().forEach(sharedList::add)` bằng `parallelStream().collect(Collectors.toList())` hoặc `toCollection(ArrayList::new)`. Vì sao collector có thể tạo container trung gian để kết hợp mà không cần chia sẻ một ArrayList cho mọi task?

## 20. Ghi nhớ

**Có hai ý nghĩa khác nhau của “stateful”:**

- **Stateful behavioral parameter**: lambda hay method reference phụ thuộc mutable state/lịch sử gọi. Đây thường là nguồn bug khi dùng trong `map`, `filter`, `peek`, đặc biệt ở parallel stream.
- **Stateful intermediate operation**: một thao tác chuẩn như **distinct, sorted, limit, skip, takeWhile, dropWhile** tự cần trạng thái để quản lý phần tử đã thấy, thứ tự hoặc ranh giới. Những thao tác này **hợp lệ** và là một phần quan trọng của Stream API.

**Map, filter, flatMap và peek là stateless intermediate operations**, nhưng callback do người viết truyền vào vẫn có thể gây side effect hoặc phụ thuộc trạng thái. **collect** là terminal reduction có thể dùng accumulator mutable theo hợp đồng riêng; nó không đồng nghĩa với một lambda tùy tiện ghi chung vào List bên ngoài.

Khi chọn pipeline, hãy cân nhắc **lazy evaluation, encounter order, short-circuit, yêu cầu bộ nhớ, nguồn vô hạn và chi phí của parallelism**. Câu hỏi cốt lõi trước khi viết lambda: **“Hàm này có đưa ra cùng quyết định cho cùng input bất kể được gọi lần thứ mấy, ở thread nào và trong thứ tự nào không?”** Nếu không, hãy đánh giá lại cách tổ chức trạng thái thay vì chỉ dựa vào việc phép toán Stream bên ngoài mang tên map hay filter.