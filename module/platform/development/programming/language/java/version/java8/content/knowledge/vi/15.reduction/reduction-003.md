# Stream.reduce(): tổng hợp phần tử với hoặc không có identity

`Stream.reduce()` là một **terminal operation** của Java Stream, dùng để kết hợp nhiều phần tử thành **một giá trị tổng hợp** (*reduction* hoặc *fold*). Ví dụ: cộng các số, nhân các số, tìm giá trị lớn nhất, ghép các chuỗi, hoặc tính một kết quả từ các phần tử. API `reduce` được giới thiệu từ Java 8 và **vẫn được sử dụng trong các phiên bản Java hiện hành**.

Hai cách cần phân biệt trong bài này:

- **Có identity:** `reduce(identity, accumulator)` trả trực tiếp một giá trị kiểu `T`; Stream rỗng trả `identity`.
- **Không có identity:** `reduce(accumulator)` trả `Optional<T>`; Stream rỗng trả `Optional.empty()` vì không có phần tử nào để làm kết quả.

Bài cũng giới thiệu ngắn gọn overload ba tham số `reduce(identity, accumulator, combiner)` để hiểu trường hợp kiểu kết quả khác kiểu phần tử và quy tắc xử lý song song.

## 1. Reduction hoạt động như thế nào?

Giả sử nguồn là `[4, 7, 2]` và phép gộp là cộng:

~~~text
Có identity = 0:
  bắt đầu 0
  0 + 4  = 4
  4 + 7  = 11
  11 + 2 = 13
  kết quả: 13

Không có identity:
  lấy phần tử đầu 4 làm kết quả tạm
  4 + 7  = 11
  11 + 2 = 13
  kết quả: Optional[13]
~~~

Đây là **mô hình tuần tự để dễ hiểu**, không phải lời cam kết JVM luôn thực thi từng bước theo đúng hình thức ấy: Stream có thể chia dữ liệu thành nhiều phần để reduction chạy song song. Tính đúng đắn phụ thuộc vào phép gộp có các tính chất cần thiết.

Tham số `accumulator` thường là một hàm nhận hai giá trị và trả lại một giá trị đã gộp, ví dụ `Integer::sum` tương đương `(a, b) -> a + b`. Khi dùng overload hai tham số, hai giá trị này cùng kiểu `T`. Hàm gộp **không nên thay đổi dữ liệu nguồn hay trạng thái dùng chung**; phải đáp ứng yêu cầu *associative*, *stateless* và *non-interfering*.

Cả hai overload đều kết thúc và tiêu thụ Stream. Sau khi đã gọi `reduce` trên một Stream, không sử dụng lại chính Stream ấy cho terminal operation khác; tạo Stream mới từ collection nếu cần tính lại.

## 2. Hai overload chính và ý nghĩa của identity

Chữ ký API:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);

Optional<T> reduce(BinaryOperator<T> accumulator);
~~~

Ở overload thứ nhất, `identity` là **phần tử trung hòa** đối với phép gộp. Nghĩa là gộp nó với một giá trị hợp lệ phải giữ nguyên giá trị đó. Ký hiệu `⊕` là phép gộp, ta muốn:

~~~text
identity ⊕ x = x
x ⊕ identity = x
~~~

Ví dụ hiện hành:

| Phép gộp | Accumulator | Identity phù hợp | Lý do |
|---|---|---|---|
| Tổng số nguyên | `Integer::sum` | `0` | `0 + x = x` |
| Tích số nguyên | `(a, b) -> a * b` | `1` | `1 * x = x` |
| Nối chuỗi | `String::concat` | `""` | Nối chuỗi rỗng không đổi nội dung |
| AND boolean | `(a, b) -> a && b` | `true` | `true && x = x` |
| OR boolean | `(a, b) -> a \|\| b` | `false` | `false \|\| x = x` |

**Identity không phải giá trị tùy ý dùng để “khởi tạo”.** Ví dụ muốn tính tổng rồi cộng thêm 10, đừng dùng `reduce(10, Integer::sum)` và mong hành vi tương đương trong parallel Stream. `10` không trung hòa với phép cộng: mỗi nhánh song song có thể dùng identity, khiến số 10 bị tính nhiều lần. Cách rõ nghĩa là:

~~~java
int sumPlusTen = numbers.stream().reduce(0, Integer::sum) + 10;
~~~

Đoạn trên minh họa một biểu thức khi `numbers` đã là `List<Integer>`; không phải chương trình độc lập.

## 3. Ví dụ Java chạy được: có và không có identity

Tạo file `ReduceIdentityDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class ReduceIdentityDemo {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(4, 7, 2);

        int sumWithIdentity = numbers.stream()
                .reduce(0, Integer::sum);

        Optional<Integer> sumWithoutIdentity = numbers.stream()
                .reduce(Integer::sum);

        int emptyWithIdentity = Stream.<Integer>empty()
                .reduce(0, Integer::sum);

        Optional<Integer> emptyWithoutIdentity = Stream.<Integer>empty()
                .reduce(Integer::sum);

        int product = numbers.stream()
                .reduce(1, (a, b) -> a * b);

        Optional<Integer> largest = numbers.stream()
                .reduce(Integer::max);

        System.out.println("Tổng có identity: " + sumWithIdentity);
        System.out.println("Tổng không identity: " + sumWithoutIdentity);
        System.out.println("Rỗng có identity: " + emptyWithIdentity);
        System.out.println("Rỗng không identity: " + emptyWithoutIdentity);
        System.out.println("Tích: " + product);
        System.out.println("Lớn nhất: " + largest);
    }
}
~~~

Lệnh chạy với JDK 17 trở lên (đoạn code này cũng chỉ dùng API đã có trong Java 8):

~~~bash
javac -encoding UTF-8 ReduceIdentityDemo.java
java ReduceIdentityDemo
~~~

Stdout của chương trình:

~~~text
Tổng có identity: 13
Tổng không identity: Optional[13]
Rỗng có identity: 0
Rỗng không identity: Optional.empty
Tích: 56
Lớn nhất: Optional[7]
~~~

Diễn giải:

1. `reduce(0, Integer::sum)` bắt đầu bằng số trung hòa `0` và trả về `int` sau khi tự động unbox từ `Integer`.
2. `reduce(Integer::sum)` **không nhận identity**, vì vậy giá trị trả về là `Optional<Integer>`; với dữ liệu này nó chứa `13`.
3. Trên Stream rỗng, phiên bản có identity trả `0`, còn phiên bản không có identity trả `Optional.empty()`.
4. Tích dùng identity `1`: `4 × 7 × 2 = 56`.
5. Tìm giá trị lớn nhất không cần đặt một giá trị “khởi tạo” có thể lấn át dữ liệu thật; overload không identity trả `Optional[7]`.

**Chú ý về ví dụ:** cần tạo Stream mới từ `numbers.stream()` cho mỗi phép tính. Nếu lưu một Stream vào biến rồi gọi `reduce`, biến Stream đó đã được tiêu thụ.

## 4. Khi nào nên không truyền identity?

Chọn `reduce(BinaryOperator<T>)` khi **không có identity tự nhiên**, hoặc khi muốn phân biệt rõ **“không có dữ liệu”** với **“có dữ liệu và kết quả bằng một giá trị nào đó”**.

### 4.1. Xử lý kết quả rỗng bằng Optional

~~~java
Optional<Integer> max = java.util.stream.Stream.of(5, 9, 3)
        .reduce(Integer::max);

max.ifPresent(value -> System.out.println("Max = " + value));

int fallback = java.util.stream.Stream.<Integer>empty()
        .reduce(Integer::max)
        .orElse(-1);

System.out.println("Fallback = " + fallback);
~~~

Đây là đoạn mã chạy được **khi đặt trong `main`**, sử dụng tên lớp `Optional` đã import. Kết quả là:

~~~text
Max = 9
Fallback = -1
~~~

`orElse(-1)` thể hiện **quy ước của ứng dụng** khi không có kết quả; `-1` không phải identity của phép tìm max và có thể là giá trị hợp lệ trong dữ liệu thực. Nếu không thể chọn một fallback an toàn, hãy giữ `Optional` và buộc phía gọi xử lý trường hợp rỗng bằng `ifPresent`, `isPresent`/`isEmpty` hoặc `orElseThrow(...)`. Riêng `Optional.isEmpty()` được thêm từ Java 11; với Java 8 có thể dùng `!isPresent()`. Với Java 17+, cả hai cách đều dùng được.

### 4.2. Tránh identity làm sai max/min

Ví dụ:

~~~java
int wrongMax = java.util.stream.Stream.of(-8, -3)
        .reduce(0, Integer::max); // Kết quả 0: sai ý định!
~~~

Vì `0` lớn hơn mọi phần tử nguồn, phép gộp cho `0` dù nguồn chỉ có `-8` và `-3`. Nếu mục tiêu là “giá trị lớn nhất của dữ liệu”, lựa chọn rõ nghĩa hơn là:

~~~java
Optional<Integer> correctMax = java.util.stream.Stream.of(-8, -3)
        .reduce(Integer::max); // Optional[-3]
~~~

Hoặc dùng API chuyên biệt `max(Comparator.naturalOrder())` cho `Stream<Integer>`. Khi không có phần tử, cả hai cách không identity đều thể hiện sự vắng mặt bằng `Optional.empty()`, thay vì tự ý thêm một giá trị nằm ngoài dữ liệu.

### 4.3. So sánh trường hợp rỗng và một phần tử

| Stream | `reduce(0, Integer::sum)` | `reduce(Integer::sum)` |
|---|---|---|
| `[]` | `0` | `Optional.empty()` |
| `[7]` | `7` | `Optional[7]` |
| `[4, 7, 2]` | `13` | `Optional[13]` |

Trong trường hợp **một phần tử** và không có identity, kết quả chính là phần tử đó; không cần gọi hàm gộp để kết hợp với phần tử khác. Với stream rỗng, không thể tổng hợp một phần tử vốn không tồn tại, nên `Optional.empty()` là cách biểu đạt nhất quán.

**Không để accumulator trả `null`** trong phiên bản không identity: hợp đồng `reduce(BinaryOperator)` có thể ném `NullPointerException` khi kết quả reduction là `null`. Hãy thiết kế phép gộp trả giá trị không null và xử lý dữ liệu null từ nguồn trước khi reduction.

## 5. Associative và identity quyết định tính đúng đắn

### 5.1. Phép gộp phải associative (kết hợp được)

Với ba giá trị `a`, `b`, `c`, phép gộp hợp lệ cho reduction cần đáp ứng:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

Cộng số nguyên là ví dụ trực quan. Phép trừ **không** associative:

~~~text
(10 - 3) - 1 = 6
10 - (3 - 1) = 8
~~~

Bởi vậy:

~~~java
int unreliable = java.util.stream.Stream.of(10, 3, 1)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

Đây là **mẫu phản ví dụ**, không nên dùng để tính toán. Kết quả không có bảo đảm theo phép trừ tuần tự vì cách chia/gộp phần có thể khác. Chỉ dùng phép gộp thỏa hợp đồng của API.

**Associative không có nghĩa là commutative (giao hoán).** Nối chuỗi `String::concat` có tính kết hợp nhưng `"ab" + "cd"` khác `"cd" + "ab"`. Với Stream có encounter order, reduction có thể gộp theo nhóm mà vẫn bảo toàn kết quả theo thứ tự logic của dữ liệu; không được suy ra thứ tự các callback hay thời điểm các nhánh chạy.

### 5.2. Identity phải thật sự trung hòa trong parallel Stream

Ý nghĩa identity lộ rõ khi chia nhánh:

~~~text
Dữ liệu: [4, 7, 2], identity = 0, phép cộng

Nhánh 1: 0 + 4     = 4
Nhánh 2: 0 + 7 + 2 = 9
Gộp:     4 + 9     = 13
~~~

Đây là **minh họa một cách chia**, không dự đoán JVM sẽ chia chính xác như vậy. Nếu thay `0` bằng `10`, mỗi nhánh có thể cộng thêm `10` và đáp án phụ thuộc vào cách chia. Vì vậy “identity đúng” là yêu cầu về toán học, không đơn thuần là thói quen chọn số 0.

### 5.3. Không dùng side effect để tích lũy

**Sai:**

~~~java
// Phản ví dụ: biến dùng chung thay đổi trong accumulator.
java.util.concurrent.atomic.AtomicInteger total =
        new java.util.concurrent.atomic.AtomicInteger();

int result = java.util.stream.Stream.of(4, 7, 2)
        .parallel()
        .reduce(0, (a, b) -> {
            total.addAndGet(b);
            return a + b;
        });
~~~

Dù `AtomicInteger` có thao tác nguyên tử, callback của `reduce` vẫn không còn stateless. Lần gọi, cách chia và thứ tự thực thi không phải một giao thức để cập nhật biến bên ngoài. **Đừng dùng `peek` hoặc side effect bên trong `reduce` để duy trì bộ đếm nghiệp vụ**; hãy dùng kết quả reduction làm nguồn sự thật:

~~~java
int total = java.util.stream.Stream.of(4, 7, 2)
        .parallel()
        .reduce(0, Integer::sum); // 13
~~~

Để giữ đúng hợp đồng, accumulator cần **stateless**, **non-interfering**, có tính kết hợp, và không sửa nguồn Stream trong khi duyệt.

### 5.4. Chú ý kiểu số và độ chính xác

`Integer::sum` sử dụng số nguyên `int`; nếu vượt giới hạn `int`, kết quả tràn số theo quy tắc Java. Khi tổng có thể lớn, chuyển sang `long` hoặc dùng kiểu số phù hợp. Với `double`/`float`, phép cộng dấu phẩy động không hoàn toàn associative do làm tròn, nên parallel reduction có thể cho sai khác nhỏ ở chữ số cuối so với xử lý tuần tự. Nếu bài toán đòi hỏi tiền tệ/độ chính xác thập phân, cân nhắc `BigDecimal` với cách làm tròn phù hợp; không mặc định cộng `double` luôn có kết quả bit-for-bit như nhau ở mọi cách nhóm.

## 6. Overload ba tham số: khi kiểu đầu ra khác kiểu phần tử

Ngoài hai cách trên, Stream hiện hành có:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

Ở đây:

- `T` là kiểu phần tử nguồn; `U` là kiểu kết quả tổng hợp, có thể **khác `T`**.
- `identity` thuộc kiểu `U` và trung hòa đối với `combiner`.
- `accumulator` gộp một kết quả tạm `U` với phần tử `T` để tạo `U` mới.
- `combiner` kết hợp hai kết quả tạm `U`; đặc biệt cần cho việc gộp các nhánh khi chạy song song.
- `combiner` phải associative và tương thích với `accumulator`: gộp `u` với kết quả của một phần tử đi từ identity phải tương đương với tích lũy phần tử ấy trực tiếp vào `u`.

Ví dụ tính **tổng độ dài** của các chuỗi; nguồn có kiểu `String` nhưng kết quả là `Integer`. Tạo file `ReduceThreeArgsDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;

public class ReduceThreeArgsDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("Java", "Stream", "API");

        int totalLength = words.parallelStream().reduce(
                0,
                (subtotal, word) -> subtotal + word.length(),
                Integer::sum
        );

        System.out.println("Tổng độ dài: " + totalLength);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReduceThreeArgsDemo.java
java ReduceThreeArgsDemo
~~~

Stdout:

~~~text
Tổng độ dài: 13
~~~

Tính toán: `"Java".length() = 4`, `"Stream".length() = 6`, `"API".length() = 3`, cộng được `13`. `0` là identity của phép cộng kết quả từng nhánh; `Integer::sum` vừa associative vừa tương thích với accumulator.

Nếu không cần tích hợp map và reduce vào cùng một hàm, cách sau thường **dễ đọc hơn**:

~~~java
int totalLength = words.stream()
        .mapToInt(String::length)
        .sum(); // 13
~~~

`words` đã được khai báo trong ví dụ trước. `mapToInt(...).sum()` là API chuyên biệt cho kiểu nguyên thủy, tránh phần boxing không cần thiết. Nếu đang dùng `Stream<String>` tổng quát, có thể tách rõ hai bước với `map(String::length).reduce(0, Integer::sum)`.

## 7. Phân biệt reduce và collect: tránh mutable identity

`reduce` biểu đạt cách **tạo ra một giá trị tổng hợp mới sau mỗi lần gộp**. Khi kết quả cần thay đổi trạng thái một container, như `ArrayList`, `HashMap` hoặc `StringBuilder`, **`collect` là lựa chọn phù hợp hơn**.

Phản ví dụ nguy hiểm:

~~~java
// KHÔNG dùng: cùng một StringBuilder mutable làm identity cho parallel reduce.
StringBuilder broken = java.util.stream.Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                StringBuilder::append,
                StringBuilder::append
        );
~~~

`StringBuilder::append` **thay đổi object nhận vào**. Một identity mutable có thể bị dùng ở nhiều nhánh, làm accumulator và combiner cùng thay đổi state; code vi phạm các kỳ vọng của reduction và có thể cho dữ liệu sai hoặc hành vi tranh chấp. Không sửa bằng cách chuyển từ `parallel()` sang tuần tự rồi coi đó là một thiết kế reduction đúng.

Cách nên dùng cho việc ghép chuỗi:

~~~java
String joined = java.util.stream.Stream.of("A", "B", "C")
        .parallel()
        .collect(java.util.stream.Collectors.joining(", "));

System.out.println(joined); // A, B, C
~~~

`Collectors.joining` có từ Java 8 và diễn đạt trực tiếp mục tiêu ghép chuỗi. Ví dụ trên có encounter order nên chuỗi đầu ra theo thứ tự `A, B, C`. Khi cần đưa phần tử vào một collection, dùng `collect(Collectors.toList())` hoặc `collect(Collectors.toCollection(ArrayList::new))` tùy yêu cầu. Việc `Stream.reduce("", String::concat)` vẫn hợp lệ về mặt kết quả nhưng tạo nhiều đối tượng `String` khi dữ liệu lớn; `Collectors.joining` thường phù hợp hơn cho tác vụ này.

## 8. Lựa chọn API theo bài toán

| Nhu cầu | Cách phù hợp | Lý do |
|---|---|---|
| Tổng số nguyên và rỗng có nghĩa là 0 | `reduce(0, Integer::sum)` hoặc `mapToInt(...).sum()` | Identity 0 tự nhiên |
| Tích các số và rỗng có nghĩa là 1 | `reduce(1, (a, b) -> a * b)` | Identity 1 tự nhiên |
| Gộp phần tử nhưng rỗng phải được phân biệt | `reduce(BinaryOperator)` | Trả `Optional<T>` |
| Tìm max/min | `max(...)` / `min(...)` hoặc `reduce(Integer::max)` | Không cần sentinel làm sai dữ liệu |
| Đầu ra khác kiểu đầu vào | `reduce(identity, accumulator, combiner)` hoặc `map` rồi reduce | Biểu đạt rõ quá trình chuyển kiểu và gộp |
| Tổng `int` từ `String.length()` | `mapToInt(String::length).sum()` | API chuyên biệt, dễ đọc |
| Ghép nhiều chuỗi | `collect(Collectors.joining(...))` | Mutable reduction hiệu quả |
| Gom vào `List`, `Set`, `Map` hoặc phân nhóm | `collect(...)` | Container tích lũy là mục tiêu |
| Đếm phần tử | `count()` | API chuyên biệt, không tự cài reduction |

`reduce` là công cụ tổng quát; dùng API chuyên biệt khi nó diễn tả ý định rõ ràng hơn và có lợi về hiệu năng.

## 9. Lỗi thường gặp

**Lỗi 1: nhầm kiểu trả về.** `reduce(0, Integer::sum)` trả `Integer` (hoặc `int` khi unbox), còn `reduce(Integer::sum)` trả `Optional<Integer>`. Không dùng `Optional.get()` vô điều kiện nếu Stream có thể rỗng.

**Lỗi 2: identity không trung hòa.** Dùng `0` cho phép nhân làm kết quả luôn bằng 0; dùng `1` cho phép cộng làm tổng sai và đặc biệt dễ sai khi chạy parallel. Identity phải phù hợp **phép gộp**, không chỉ kiểu dữ liệu.

**Lỗi 3: dùng max với identity 0.** Nếu tất cả phần tử âm, `reduce(0, Integer::max)` trả 0 ngoài tập dữ liệu. Dùng `reduce(Integer::max)` hoặc `max(...)` để có `Optional` thể hiện không có dữ liệu.

**Lỗi 4: phép gộp không associative.** Phép trừ, phép chia và nhiều phép toán phụ thuộc thứ tự đánh giá không đáp ứng hợp đồng. Việc chạy đúng trên một bộ dữ liệu tuần tự không chứng minh thuật toán an toàn cho parallel reduction.

**Lỗi 5: mutation trong accumulator.** Ghi vào biến toàn cục, sửa nguồn hay dùng mutable identity (ví dụ `StringBuilder`) có thể khiến kết quả sai hoặc khó dự đoán. Chuyển sang `collect` nếu cần tích lũy bằng container mutable.

**Lỗi 6: quên Stream là single-use.** Mỗi lần gọi terminal `reduce` tiêu thụ pipeline; tạo lại Stream khi cần tính tổng và max riêng biệt.

**Lỗi 7: dùng reduce bằng mọi giá.** Tính tổng primitive, đếm phần tử, tìm min/max và ghép chuỗi đều có API chuyên biệt. Khi API đó thể hiện mục tiêu đơn giản và chính xác hơn, ưu tiên nó.

## 10. Câu hỏi tự luyện

1. Với `Stream.<Integer>empty()`, `reduce(0, Integer::sum)` và `reduce(Integer::sum)` trả gì? Tại sao hai kiểu trả về khác nhau?
2. Vì sao `Stream.of(2, 3).parallel().reduce(10, Integer::sum)` không phải cách đáng tin để tính `10 + 2 + 3`?
3. Phép gộp nào phù hợp cho `reduce` trong cả tuần tự và song song: cộng, trừ, hay nối chuỗi? Nối chuỗi có cần giao hoán không?
4. Với tất cả giá trị âm, vì sao `reduce(0, Integer::max)` có thể sai mục đích?
5. Bài toán ghép hàng triệu chuỗi nên dùng `reduce("", String::concat)` hay `Collectors.joining`?

**Đáp án gợi ý:** (1) `0` và `Optional.empty()`; overload có identity luôn có giá trị mặc định, overload không identity thể hiện sự vắng mặt. (2) `10` không trung hòa với phép cộng; các nhánh parallel có thể khởi đầu bằng identity. (3) Cộng số nguyên và nối chuỗi có tính kết hợp, phép trừ không; nối chuỗi không cần giao hoán để hợp lệ với reduction có thứ tự. (4) Giá trị 0 có thể lớn hơn mọi phần tử thực. (5) `Collectors.joining` vì dùng mutable reduction phù hợp với tác vụ ghép chuỗi.

## Ghi nhớ

- **Có identity:** `reduce(identity, accumulator) → T`, Stream rỗng trả identity. Identity phải là phần tử trung hòa đúng với phép gộp.
- **Không có identity:** `reduce(accumulator) → Optional<T>`, Stream rỗng trả `Optional.empty()`. Thích hợp khi sự vắng mặt của dữ liệu phải được nhận biết.
- **Song song:** phép gộp phải associative; accumulator không phụ thuộc state bên ngoài hoặc làm thay đổi nguồn; không sử dụng identity tùy ý.
- **Khác kiểu kết quả:** có overload ba tham số; khi chỉ cần map rồi sum/max thì ưu tiên API chuyên biệt.
- **Container mutable:** chọn `collect` và collector thích hợp thay vì mutate object trong `reduce`.

### Tham khảo API Java còn được hỗ trợ

- [Oracle Java SE 25 — `Stream.reduce`, cả ba overload](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — `java.util.stream`: reduction, associativity và mutable reduction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 25 — `Collectors.joining`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
