# Viết phép reduce đúng hợp đồng và tìm phản ví dụ sai

> **Chương:** Bài tập nền tảng và trung cấp  
> **Module:** JAVA_STREAM_API  
> **Chủ đề thực hành:** Thiết kế phép `reduce` đúng hợp đồng, tìm bộ dữ liệu nhỏ nhất khiến phép giảm gộp sai, rồi sửa bằng phép toán phù hợp. Các bài tập kết nối `filter`, `map`, `collect`, grouping, xử lý song song và vấn đề trạng thái/độ chính xác trong Java Stream API.

## Mục tiêu học tập

Kết thúc bài này, bạn có thể:

1. Phân biệt ba overload `reduce(BinaryOperator)`, `reduce(identity, accumulator)` và `reduce(identity, accumulator, combiner)`.
2. Kiểm tra **giá trị đơn vị** (*identity*) và **tính kết hợp** (*associativity*) của phép giảm gộp.
3. Kiểm tra **tính tương thích** (*compatibility*) giữa accumulator và combiner trong overload ba tham số.
4. Chứng minh bằng phản ví dụ rằng một `reduce` có thể chạy đúng ở chế độ tuần tự nhưng sai khi chia/gộp các phân vùng.
5. Phân biệt tính **kết hợp** với tính **giao hoán**, và hiểu vai trò của encounter order.
6. Tránh tích lũy vào đối tượng mutable dùng chung hoặc biến bên ngoài lambda.
7. Xác định các lỗi riêng của số học: tràn `int`/`long`, không kết hợp của `double` và làm tròn `BigDecimal` giữa chừng.
8. Chọn `collect` thay `reduce` khi mục tiêu là gom phần tử vào container mutable.
9. Viết kiểm tra tự động cho identity, associativity, compatibility, nguồn rỗng, dữ liệu biên, và kết quả tham chiếu độc lập.
10. Lý giải **vì sao** một cách sửa đúng, không chỉ thay code đến khi một lần chạy song song cho kết quả mong đợi.

**Phiên bản:** Ví dụ dùng Java 17 trở lên, trong đó `record` và `List.of` giúp mã ngắn gọn. Hầu hết các phép `reduce` đã có từ Java 8. Những snippet độc lập có thể đặt trong phương thức Java với `import` phù hợp; các chương trình khai báo lớp đầy đủ có thể chạy riêng.

**Cách học:** Mỗi bài theo trình tự **dự đoán → tìm phản ví dụ → phân tích hợp đồng → sửa → kiểm tra**. Không cần bật parallel để *chứng minh* một phép toán sai; chỉ cần xây một phép gộp trung gian hợp lệ cho thấy kết quả khác đã là phản ví dụ.

---

## 1. Nhìn thấy cách reduce có thể phân chia dữ liệu

`reduce` là một **terminal operation**: nó nhận các phần tử của Stream và kết hợp chúng thành một giá trị kết quả. Với Stream song song, công việc có thể được chia nhỏ và các kết quả trung gian được gộp theo cây.

~~~text
Nguồn có encounter order: [a, b, c, d]

Một cách đánh giá tuần tự:
  (((identity ⊕ a) ⊕ b) ⊕ c) ⊕ d

Một cách đánh giá sau khi phân vùng:
       [a, b]                [c, d]
          |                     |
    identity ⊕ a ⊕ b       identity ⊕ c ⊕ d
          |                     |
        left                  right
          \                     /
           \--- combiner ------/
                     |
                  result
~~~

Dấu `⊕` trong sơ đồ là biểu tượng chung; với overload ba tham số, **accumulator và combiner có thể có kiểu khác nhau**, nhưng phải có ý nghĩa toán học tương thích.

**Không nên dự đoán chính xác Stream sẽ chia thành bao nhiêu phần.** Sơ đồ chỉ minh họa những cách đánh giá mà một phép tổng hợp hợp lệ phải chịu được.

Nếu kết quả phải đúng **chỉ khi** mọi phần tử được đưa vào một accumulator từ trái sang phải, thì thuật toán có thể không phù hợp với `reduce` song song.

### 1.1. Ba dạng API

| Dạng | Kiểu trả về | Khi nên dùng |
|---|---|---|
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Gộp các phần tử bằng một phép toán cùng kiểu, không muốn tạo giá trị mặc định cho nguồn rỗng |
| `reduce(T identity, BinaryOperator<T>)` | `T` | Có một giá trị đơn vị đúng và phép toán có tính kết hợp |
| `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)` | `U` | Kiểu kết quả `U` khác kiểu phần tử `T`, cần accumulator/combiner tương thích |

Ví dụ cơ bản:

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(4, 7, 2);

int sum = values.stream().reduce(0, Integer::sum);

Optional<Integer> max = values.stream()
        .reduce(Integer::max);

long sumAsLong = values.stream()
        .reduce(
                0L,
                (acc, n) -> acc + n.longValue(),
                Long::sum
        );

System.out.println(sum);               // 13
System.out.println(max.orElseThrow()); // 7
System.out.println(sumAsLong);         // 13
~~~

Ở đây mỗi terminal operation dùng một **Stream mới** từ `values`. Không dùng lại đối tượng `Stream` sau khi đã gọi `reduce`.

---

## 2. Hai định luật cốt lõi của reduce có identity

Với overload:

~~~java
T result = stream.reduce(identity, accumulator);
~~~

Hợp đồng đòi hỏi `accumulator` là hàm **kết hợp** (*associative*), **stateless** và **non-interfering**; `identity` là giá trị **đơn vị** của phép toán đó.

### 2.1. Định luật identity

Đặt `e` là identity và `f` là accumulator:

~~~text
f(e, x) = x
f(x, e) = x
~~~

Điều kiện hai phía cần đúng theo phép toán được dùng để gộp các giá trị, vì framework có thể đặt identity vào các phần tích lũy khác nhau. Với một toán tử liên kết không giao hoán, vẫn cần một đơn vị hai phía.

Ví dụ:

| Phép toán | Identity đúng | Kiểm tra |
|---|---|---|
| Cộng số nguyên | `0` | `0 + x = x + 0 = x` |
| Nhân số nguyên | `1` | `1 * x = x * 1 = x` |
| Nối chuỗi | `""` | `"" + x = x + "" = x` |
| Nối danh sách bất biến | Danh sách rỗng | `[] ++ xs = xs ++ [] = xs` |
| Giá trị lớn nhất trên toàn miền `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Giá trị nhỏ nhất trên toàn miền `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

Identity có thể **phụ thuộc miền giá trị**. `0` chỉ là identity cho phép `max` nếu mọi giá trị trong miền đều **không âm**; nó không đúng với tập số nguyên âm.

### 2.2. Định luật associativity

Với mọi `a`, `b`, `c` hợp lệ:

~~~text
f(f(a, b), c) = f(a, f(b, c))
~~~

Phép cộng và nhân số nguyên toán học có tính kết hợp; phép trừ và chia thì không.

~~~java
int a = 10;
int b = 3;
int c = 2;

System.out.println((a - b) - c); // 5
System.out.println(a - (b - c)); // 9
~~~

Đây là **phản ví dụ** cho khẳng định phép trừ có tính kết hợp. Chỉ một bộ ba giá trị khiến hai vế khác nhau đã đủ bác bỏ định luật.

### 2.3. Giao hoán không phải yêu cầu chung

**Associativity** thay đổi dấu ngoặc, không thay thứ tự:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

**Commutativity** thay vị trí các toán hạng:

~~~text
a ⊕ b = b ⊕ a
~~~

Nối chuỗi là ví dụ quan trọng:

~~~java
String a = "A";
String b = "B";
String c = "C";

System.out.println((a + b) + c); // ABC
System.out.println(a + (b + c)); // ABC

System.out.println(a + b); // AB
System.out.println(b + a); // BA
~~~

Nối chuỗi **kết hợp** nhưng **không giao hoán**. Nó có thể dùng với `reduce("", String::concat)` trên một nguồn có encounter order và vẫn giữ thứ tự kết quả theo hợp đồng. Không tự gắn giả định “song song thì mọi phép toán phải giao hoán”.

---

## 3. Bài mẫu A — Tổng số nguyên: phiên bản đúng và kiểm tra nhanh

~~~java
import java.util.List;

List<Integer> values = List.of(2, 5, 7);

int sequential = values.stream()
        .reduce(0, Integer::sum);

int parallel = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sequential); // 14
System.out.println(parallel);   // 14
~~~

Đánh giá theo hợp đồng:

1. `0` là identity của phép cộng.
2. `Integer::sum` thực hiện phép cộng `int`, có tính kết hợp **theo số học modulo** \(2^{32}\).
3. Hàm cộng không ghi biến bên ngoài hay sửa nguồn.
4. Với dữ liệu đủ nhỏ để không tràn, kết quả cũng đúng theo số nguyên toán học.

**Giới hạn:** `reduce(0, Integer::sum)` không bảo đảm tổng toán học đúng nếu số cộng vượt miền `int`. Tính đúng **theo kiểu Java** và tính đúng **theo nghiệp vụ** là hai câu hỏi khác nhau.

Khi tổng có thể lớn hơn `Integer.MAX_VALUE` nhưng vẫn nằm trong `long`:

~~~java
long sum = values.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Khi có thể vượt cả `long`, dùng `BigInteger` hoặc một mô hình số học phù hợp với miền bài toán.

---

## 4. Phản ví dụ 1 — Identity không phải 0 cho phép cộng

Một người viết:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

// SAI hợp đồng:
int total = values.parallelStream()
        .reduce(10, Integer::sum);
~~~

**Hãy dự đoán:** Tại sao `10` không phải identity của phép cộng? Điều gì có thể xảy ra khi có hai phân vùng?

Với một phép gộp tuần tự từ trái qua phải:

~~~text
((10 + 1) + 2) + 3 = 16
~~~

Nếu chia thành `[1]` và `[2,3]`, mỗi phần bắt đầu từ `10`:

~~~text
Phân vùng trái:   10 + 1 = 11
Phân vùng phải:   10 + 2 + 3 = 15
Gộp hai kết quả:  11 + 15 = 26
~~~

`16 != 26`. Đây là phản ví dụ cho phép giảm gộp không đúng identity. Không cần đoán JDK sẽ dùng đúng hai phân vùng ấy; **tồn tại cách phân vùng hợp lý trả kết quả khác** đã đủ cho thấy thuật toán không đáp ứng hợp đồng song song.

Sửa:

~~~java
int correct = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(correct); // 6
~~~

Nếu nghiệp vụ thực sự muốn **cộng thêm phí cố định 10 một lần**:

~~~java
int totalWithFee = Math.addExact(
        10,
        values.parallelStream().reduce(0, Integer::sum)
);

System.out.println(totalWithFee); // 16
~~~

Dù ở ví dụ này `Math.addExact` giúp phát hiện tràn phép cộng cuối, `reduce` bên trong vẫn dùng `int` và có thể đã tràn với dữ liệu lớn. Với tổng có rủi ro tràn, nâng kiểu **trước** khi tích lũy.

**Quy tắc:** Giá trị cố định của nghiệp vụ không nhất thiết là identity. Hãy gộp bằng identity toán học, sau đó áp dụng điều chỉnh **một lần bên ngoài**.

---

## 5. Phản ví dụ 2 — Phép trừ không kết hợp

~~~java
import java.util.List;

List<Integer> numbers = List.of(10, 3, 2);

// SAI nếu kỳ vọng một kết quả giảm gộp không phụ thuộc phân vùng:
int reduced = numbers.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Hai cách đặt ngoặc:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

`5 != 9` nên phép trừ không kết hợp.

Thêm `0` vào như một identity cũng **không đúng hai phía**: `0 - x = -x`, không bằng `x`. Bởi vậy cách viết sai **cả identity lẫn associativity**.

Nếu yêu cầu là **trừ lần lượt khỏi một số ban đầu**, dùng một vòng lặp tuần tự:

~~~java
int balance = 10;
for (int cost : List.of(3, 2)) {
    balance = Math.subtractExact(balance, cost);
}
System.out.println(balance); // 5
~~~

Nếu yêu cầu là “số dư đầu kỳ trừ tổng mọi chi phí”:

~~~java
import java.util.List;

int openingBalance = 10;
List<Integer> costs = List.of(3, 2);

long spent = costs.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

long closingBalance = openingBalance - spent;
System.out.println(closingBalance); // 5
~~~

Cách thứ hai **thay đổi phép tổng hợp trung gian** thành cộng, có identity `0` và tính kết hợp phù hợp. Việc trừ diễn ra **một lần sau tổng hợp**. Nếu phải bảo đảm không tràn `long`, cân nhắc `BigInteger`.

---

## 6. Phản ví dụ 3 — Dùng 0 làm identity cho max với toàn số âm

~~~java
import java.util.List;

List<Integer> scores = List.of(-7, -2, -9);

// Sai nếu muốn tìm max thật của nguồn:
int wrong = scores.parallelStream()
        .reduce(0, Integer::max);

System.out.println(wrong); // 0
~~~

Ở đây không có phần tử nào bằng `0`, nhưng kết quả là `0`. Lý do:

~~~text
max(0, -7) = 0
max(0, -2) = 0
max(0, -9) = 0
~~~

`0` không phải identity cho phép lấy max trên **toàn miền `int`**.

Hai cách sửa:

~~~java
import java.util.Optional;

Optional<Integer> max = scores.parallelStream()
        .reduce(Integer::max);

System.out.println(max.orElseThrow()); // -2
~~~

Hoặc, khi miền giá trị là `int` và muốn một identity hợp lệ:

~~~java
int maxWithIdentity = scores.parallelStream()
        .reduce(Integer.MIN_VALUE, Integer::max);

System.out.println(maxWithIdentity); // -2
~~~

**Cảnh báo về nguồn rỗng:** Với `reduce(Integer.MIN_VALUE, Integer::max)`, Stream rỗng trả về `Integer.MIN_VALUE` dù không có phần tử thật. Nếu cần phân biệt “không có dữ liệu” với “có phần tử bằng MIN_VALUE”, ưu tiên overload trả `Optional<Integer>`.

### 6.1. Bài học về miền dữ liệu

Một identity chỉ đúng nếu nó hoạt động cho **mọi giá trị có thể đi vào phép gộp**. Không lấy điều kiện của dữ liệu mẫu (“lần này tất cả giá trị không âm”) làm định luật tổng quát nếu hệ thống chưa có ràng buộc nhập liệu tương ứng.

---

## 7. Phản ví dụ 4 — Nối chuỗi đúng hợp đồng nhưng combiner đảo thứ tự

Nối chuỗi có identity `""` và phép nối `String::concat` có tính kết hợp:

~~~java
import java.util.List;

List<String> words = List.of("A", "B", "C");

String correct = words.parallelStream()
        .reduce("", String::concat);

System.out.println(correct); // ABC
~~~

Đây là phép giảm gộp hai tham số hợp lệ trên `String` và nguồn có encounter order.

Vấn đề xuất hiện nếu tự thiết kế combiner **ghép theo thứ tự ngược**:

~~~java
List<String> pieces = List.of("A", "B", "C");

String wrong = pieces.parallelStream()
        .reduce(
                "",
                (result, value) -> result + value,
                (left, right) -> right + left // SAI với nguồn ORDERED
        );
~~~

Kiểm tra thủ công:

~~~text
Phân vùng trái:  [A]    -> "A"
Phân vùng phải: [B, C] -> "BC"

Combiner đúng: "A" + "BC" = "ABC"
Combiner sai : "BC" + "A" = "BCA"
~~~

Trong khi phép nối `String` có tính kết hợp, **đảo hai kết quả phân vùng** không giữ encounter order. Đây là lỗi combiner, không phải lỗi của `parallelStream`.

Sửa:

~~~java
String fixed = pieces.parallelStream()
        .reduce(
                "",
                (result, value) -> result + value,
                (left, right) -> left + right
        );
System.out.println(fixed); // ABC
~~~

**Hiệu năng:** Nối chuỗi liên tiếp bằng `String::concat` thường cấp phát nhiều chuỗi trung gian. Khi muốn ghép nhiều chuỗi với dấu phân cách, dùng `Collectors.joining(delimiter)` thường rõ hơn:

~~~java
import java.util.stream.Collectors;

String csv = words.parallelStream()
        .collect(Collectors.joining(","));

System.out.println(csv); // A,B,C
~~~

Hàm gộp đúng hợp đồng không có nghĩa đó là thuật toán tốt nhất về bộ nhớ hoặc hiệu năng.

---

## 8. Overload ba tham số: thêm một định luật compatibility

Cấu trúc:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
);
~~~

Ở đây:

- `T` là kiểu phần tử Stream.
- `U` là kiểu trạng thái/kết quả.
- `identity` thuộc kiểu `U`.
- `accumulator` biến `(U, T)` thành `U`.
- `combiner` gộp hai trạng thái `U`.

Để chạy đúng khi phân vùng, cần:

1. **Identity cho combiner:** `combiner(identity, u) = u` đối với trạng thái hợp lệ; trong thiết kế phép gộp thông thường identity cũng là đơn vị hai phía.
2. **Associativity của combiner:** `combine(combine(a,b),c) = combine(a,combine(b,c))`.
3. **Compatibility của accumulator và combiner:**

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

với `u` là trạng thái tích lũy hợp lệ và `t` là phần tử đầu vào.

Điều kiện thứ ba nói rằng: “ghép trạng thái `u` với phần tạo ra khi xử lý riêng một phần tử” phải có cùng nghĩa với “đưa trực tiếp phần tử đó vào trạng thái `u`”.

### 8.1. Bài mẫu B — Tính tổng độ dài String bằng Long

~~~java
import java.util.List;

List<String> words = List.of("java", "stream", "api");

long sequential = words.stream()
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

long parallel = words.parallelStream()
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

System.out.println(sequential); // 13
System.out.println(parallel);   // 13
~~~

Giải thích với `u=4` và `t="api"`:

~~~text
accumulator(identity, "api") = 0 + 3 = 3
combiner(4, 3) = 4 + 3 = 7
accumulator(4, "api") = 4 + 3 = 7

=> compatibility đúng
~~~

Bên cạnh đó, `Long::sum` có identity `0L` và kết hợp theo số học `long` modulo \(2^{64}\). Đối với độ dài thật có thể vượt `long` trong một ứng dụng lý thuyết cực lớn, phải chọn kiểu đếm lớn hơn. Trong bài tập thông thường với số lượng hữu hạn phù hợp miền `long`, kết quả là chính xác theo số nguyên.

---

## 9. Phản ví dụ 5 — Accumulator cộng, combiner lấy max

~~~java
import java.util.List;

List<String> words = List.of("ab", "cde");

// SAI:
long result = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::max
        );
~~~

Chạy tuần tự trên hai phần tử có thể cho `5` vì phần tích lũy liên tiếp chỉ dùng accumulator:

~~~text
0 + len("ab") = 2
2 + len("cde") = 5
~~~

Nhưng khi chia thành hai phần:

~~~text
Phân vùng trái:  0 + 2 = 2
Phân vùng phải: 0 + 3 = 3
Combiner: max(2, 3) = 3
~~~

`3 != 5`. Định luật compatibility bị vi phạm:

~~~text
u = 2
t = "cde"
identity = 0

combiner(2, accumulator(0, t)) = max(2, 3) = 3
accumulator(2, t)             = 2 + 3    = 5
~~~

Sửa combiner thành phép cộng:

~~~java
long correct = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(correct); // 5
~~~

**Đây là phản ví dụ quan trọng nhất cho overload ba tham số:** `combiner` không chỉ cần “một phép toán hợp lệ trên kiểu U”; nó phải **tương thích với ý nghĩa mà accumulator đang xây dựng**.

---

## 10. Phản ví dụ 6 — Combiner bỏ qua một phân vùng

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4);

// SAI:
int wrong = numbers.parallelStream()
        .reduce(
                0,
                Integer::sum,
                (left, right) -> left
        );
~~~

Xét hai phân vùng:

~~~text
[1,2] -> 3
[3,4] -> 7

combiner(3,7) = 3  (mất phần bên phải)
Kết quả đúng là 10
~~~

Bất kể một lần chạy tình cờ có cho ra 10 hay không, combiner đã sai vì không hợp nhất dữ liệu từ nhánh bên phải.

Sửa bằng:

~~~java
int correct = numbers.parallelStream()
        .reduce(0, Integer::sum, Integer::sum);

System.out.println(correct); // 10
~~~

Với Stream số nguyên, còn cách gọn hơn:

~~~java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

**Tư duy kiểm thử:** Hãy cố ý tạo **hai phân vùng đều không rỗng** và yêu cầu phép gộp trả cùng kết quả như khi xử lý toàn nguồn. Không nên chỉ test danh sách một phần tử hoặc nguồn rỗng, vì chúng có thể không dùng đến combiner.

---

## 11. Phản ví dụ 7 — Dùng reduce để sửa List mutable

`reduce` được thiết kế cho phép **giảm gộp các giá trị theo phép toán kết hợp**, không phải để lắp ráp một container mutable dùng chung.

~~~java
import java.util.ArrayList;
import java.util.List;

// SAI khi dùng chung List identity và sửa nó trong accumulator:
List<Integer> wrong = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(
                new ArrayList<Integer>(),
                (list, n) -> {
                    list.add(n);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Vấn đề:

- Identity là **một object `ArrayList` có thể sửa**, không phải giá trị rỗng bất biến.
- Nhiều nhánh có thể nhận cùng tham chiếu identity, gây chia sẻ trạng thái.
- Accumulator và combiner làm thay đổi object nhận vào, không tuân thủ cách dùng `reduce` đòi hỏi kết quả được kết hợp một cách an toàn.
- Khi một lần gộp thực hiện `left.addAll(right)` mà `left` và `right` là cùng list, dữ liệu có thể bị nhân đôi; khi cập nhật đồng thời, `ArrayList` cũng không thread-safe.

### 11.1. Sửa bằng collect

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );

System.out.println(result); // [1, 2, 3, 4]
~~~

Đây là overload mutable reduction của `Stream.collect(supplier, accumulator, combiner)`. `supplier` tạo **container mới** cho các nhánh khi cần, và `combiner` gộp container có kiểm soát.

Hoặc dùng collector chuẩn:

~~~java
import java.util.stream.Collectors;

List<Integer> collected = List.of(1, 2, 3, 4)
        .parallelStream()
        .collect(Collectors.toList());
~~~

Nếu chỉ muốn một List kết quả không cho sửa cấu trúc trên Java 16+:

~~~java
List<Integer> immutable = List.of(1, 2, 3, 4)
        .parallelStream()
        .toList();
~~~

**Không sửa bằng cách thêm `synchronized` vào một reducer sai hợp đồng.** Đồng bộ có thể làm giảm data race, nhưng không biến identity mutable được chia sẻ thành một phép giảm gộp có ngữ nghĩa đúng.

### 11.2. Có thể giảm gộp danh sách bất biến không?

Về nguyên tắc có thể dùng một phép nối **trả về một danh sách mới**, không sửa đầu vào, và có identity là danh sách rỗng. Tuy nhiên việc sao chép list ở mỗi bước thường rất tốn chi phí. `collect` phù hợp hơn khi mục đích là xây collection.

---

## 12. Phản ví dụ 8 — Biến trạng thái ngoài lambda

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

List<Integer> values = List.of(1, 2, 3, 4);
AtomicInteger calls = new AtomicInteger();

int sum = values.parallelStream()
        .reduce(0, (acc, n) -> {
            calls.incrementAndGet(); // Side effect ngoài phép tổng hợp
            return acc + n;
        });
~~~

`AtomicInteger` làm lần tăng bộ đếm nguyên tử, nhưng **không khiến lambda trở thành stateless**. Nếu chương trình cần số lần gọi accumulator như một dữ liệu nghiệp vụ, thiết kế có vấn đề: Stream có quyền chia công việc và kết hợp theo nhiều cây; những thay đổi pipeline, đặc biệt khi có các thao tác dừng sớm hoặc tối ưu, có thể thay đổi số lần gọi hành vi trung gian hoặc mẫu thực thi.

Trong một phép reduce đơn giản với nguồn hữu hạn, số phần tử cần xử lý được ràng buộc bởi phép tổng hợp, nhưng **không được suy ra số lần gọi hoặc thứ tự của từng lambda từ một phép đếm side effect** như một hợp đồng tổng quát.

Tệ hơn là làm phép tính **phụ thuộc** vào biến chia sẻ:

~~~java
int[] factor = {1};

int broken = values.parallelStream()
        .reduce(0, (acc, n) -> {
            factor[0]++; // Đọc/ghi không đồng bộ
            return acc + n * factor[0];
        });
~~~

Giá trị phụ thuộc thứ tự chạy thread và trạng thái đã thay đổi, nên accumulator không còn là một hàm thuần của hai đối số. Việc mảng `factor` là effectively final **không** làm nội dung mảng bất biến hoặc thread-safe.

Cách đúng nếu yêu cầu tính tổng các số sau khi nhân hằng số 2:

~~~java
int correct = values.parallelStream()
        .mapToInt(n -> n * 2)
        .sum();

System.out.println(correct); // 20
~~~

Khi dữ liệu cần kèm chỉ số/timestamp để có phép biến đổi đặc thù, hãy đưa thông tin ấy vào **phần tử đầu vào hoặc trạng thái tổng hợp có hợp đồng**, không điều khiển bằng biến đếm ngoài pipeline.

---

## 13. Số học là một phần của hợp đồng: overflow và độ chính xác

### 13.1. int cộng theo modulo, nhưng nghiệp vụ có thể cần tổng nguyên chính xác

~~~java
import java.util.List;

List<Integer> amounts = List.of(
        1_500_000_000,
        1_500_000_000
);

int wrapped = amounts.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(wrapped); // -1294967296
~~~

`Integer::sum` vẫn kết hợp theo modulo `2^32`; đây là **lỗi chọn miền số**, không phải một phản ví dụ cho tính kết hợp của phép cộng `int`. Tổng toán học là `3_000_000_000`, không nằm trong `int`.

Sửa bằng `long` trước khi cộng:

~~~java
long exactInLong = amounts.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(exactInLong); // 3000000000
~~~

Nếu tổng có thể vượt `long`:

~~~java
import java.math.BigInteger;

BigInteger exact = amounts.parallelStream()
        .map(n -> BigInteger.valueOf(n.longValue()))
        .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 3000000000
~~~

### 13.2. Math.addExact phát hiện tràn trung gian

~~~java
import java.util.List;

List<Long> values = List.of(Long.MAX_VALUE, 1L, -1L);

// Có thể ném ArithmeticException ở một cách nhóm:
// values.parallelStream().reduce(0L, Math::addExact);
~~~

Tổng **toán học cuối cùng** là `Long.MAX_VALUE`, nằm trong miền `long`. Nhưng nếu một nhánh cộng `Long.MAX_VALUE + 1` trước thì `Math.addExact` ném ngoại lệ. Một cách nhóm khác có thể cộng `1 + (-1) = 0` trước rồi mới cộng `Long.MAX_VALUE` mà không tràn.

Vì thế `Math.addExact` hữu ích khi muốn **từ chối mọi phép cộng trung gian tràn**; nó không là phép toán toàn phần có tính kết hợp trên mọi chuỗi số `long` nếu xét cả khả năng ném ngoại lệ.

Để tính tổng toán học chính xác bất kể cách nhóm rồi mới kiểm tra miền cuối:

~~~java
BigInteger total = values.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

long result = total.longValueExact();
System.out.println(result); // 9223372036854775807
~~~

### 13.3. double không có associativity theo số học nhị phân

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

`1.0` bị mất khi cộng vào `-1.0e16` do làm tròn dấu phẩy động. Vì vậy:

~~~java
import java.util.List;

List<Double> values = List.of(1.0e16, -1.0e16, 1.0);

double sequential = values.stream()
        .reduce(0.0, Double::sum);

double parallel = values.parallelStream()
        .reduce(0.0, Double::sum);

// Không dự đoán một giá trị parallel cố định cho mọi cấu hình/JDK.
System.out.println(sequential);
System.out.println(parallel);
~~~

`DoubleStream.sum()` có thể dùng kỹ thuật tổng có bù sai số và không bảo đảm cùng cách nhóm như `reduce(0.0, Double::sum)`. Không lấy một kết quả đơn lẻ làm chuẩn chính xác tuyệt đối cho mọi pipeline số thực.

Với ứng dụng khoa học/thống kê, hãy xác định sai số tuyệt đối/tương đối được phép và đối chiếu với oracle phù hợp. Với tiền tệ yêu cầu chính xác thập phân, `BigDecimal` hoặc số đơn vị nhỏ nhất là lựa chọn thường thích hợp hơn `double`.

---

## 14. Phản ví dụ 9 — Làm tròn BigDecimal trong combiner

`BigDecimal` cộng **không truyền MathContext** là phép cộng thập phân chính xác. Nhưng nếu làm tròn sau **mỗi bước cộng**, tính kết hợp có thể mất.

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(2, RoundingMode.HALF_UP);

BigDecimal a = new BigDecimal("9.9");
BigDecimal b = new BigDecimal("0.2");
BigDecimal c = new BigDecimal("-9.9");

BigDecimal left  = a.add(b, mc).add(c, mc);
BigDecimal right = a.add(b.add(c, mc), mc);

System.out.println(left);  // 0.1
System.out.println(right); // 0.2
~~~

Hai cách đặt ngoặc cho **kết quả khác nhau**. Do đó:

~~~java
import java.util.List;

List<BigDecimal> amounts = List.of(a, b, c);

// Không phù hợp nếu muốn kết quả độc lập cách nhóm:
// BigDecimal total = amounts.parallelStream()
//         .reduce(BigDecimal.ZERO, (x, y) -> x.add(y, mc));
~~~

Cách sửa nếu nghiệp vụ yêu cầu **cộng chính xác rồi làm tròn một lần cuối**:

~~~java
BigDecimal exactTotal = amounts.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal rounded = exactTotal.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 0.20
~~~

Nếu yêu cầu phải làm tròn **mỗi dòng giao dịch trước khi cộng**, hãy chuẩn hóa từng dòng theo chính sách nghiệp vụ rồi tổng hợp chính xác những kết quả đã chuẩn hóa. Đừng tùy tiện đổi thời điểm làm tròn vì hai bài toán có thể cho tổng khác nhau.

### 14.1. BigDecimal equals và compareTo

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
~~~

`equals` xét cả scale, trong khi `compareTo` xét giá trị số. Khi viết oracle và kiểm thử, xác định mục tiêu là **giá trị** hay **giá trị kèm định dạng/scale**.

---

## 15. Bài mẫu C — Giữ sum và count bất biến, chia một lần cuối

Để tính trung bình cộng, không lấy trung bình của các trung bình phân vùng khi kích thước nhóm khác nhau. Hãy lưu **tổng** và **số lượng** trong trạng thái bất biến, rồi gộp chúng đúng.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.List;

record SumCount(BigInteger sum, long count) {

    SumCount add(Integer n) {
        return new SumCount(
                sum.add(BigInteger.valueOf(n.longValue())),
                Math.addExact(count, 1L)
        );
    }

    SumCount merge(SumCount other) {
        return new SumCount(
                sum.add(other.sum),
                Math.addExact(count, other.count)
        );
    }

    BigDecimal average(int scale) {
        if (count == 0L) {
            throw new IllegalStateException("Nguồn rỗng");
        }
        return new BigDecimal(sum).divide(
                BigDecimal.valueOf(count),
                scale,
                RoundingMode.HALF_UP
        );
    }
}

List<Integer> values = List.of(10, 20, 100);

SumCount stats = values.parallelStream()
        .reduce(
                new SumCount(BigInteger.ZERO, 0L),
                SumCount::add,
                SumCount::merge
        );

System.out.println(stats.sum());       // 130
System.out.println(stats.count());     // 3
System.out.println(stats.average(4));  // 43.3333
~~~

Tại sao dạng ba tham số này phù hợp?

- `identity = SumCount(0,0)`.
- `add(n)` tăng sum thêm `n` và count thêm 1, **trả trạng thái mới**, không sửa trạng thái cũ.
- `merge` cộng tổng với tổng và số lượng với số lượng.
- Cả sum và count đều được gộp theo phép cộng tương ứng; không mất thông tin về kích thước phân vùng.
- Việc chia diễn ra **sau** khi reduce hoàn thành, không xuất hiện trong combiner.

**Điểm giới hạn:** `Math.addExact` của count sẽ ném nếu số phần tử vượt miền `long`. Trong dữ liệu thông thường `count` nằm trong giới hạn, nhưng nếu yêu cầu lý thuyết là không giới hạn số phần tử, thay count bằng `BigInteger`. Kết quả trung bình phải xác định scale/rounding mode trước.

### 15.1. Phản ví dụ: trung bình của hai trung bình

~~~text
Phân vùng A = [10, 20] => average(A) = 15, count(A) = 2
Phân vùng B = [100]    => average(B) = 100, count(B) = 1

Sai:  (15 + 100) / 2 = 57.5
Đúng: (10 + 20 + 100) / 3 = 43.333...
~~~

Khi reducer chỉ lưu một số `average`, combiner không biết mỗi average được tạo từ **bao nhiêu** phần tử. Cần giữ count (hoặc trọng số tương ứng) trong trạng thái.

---

## 16. Cách viết phép kiểm tra định luật bằng Java

Một lần chạy `parallelStream()` cho kết quả đúng **không chứng minh** phép toán có tính kết hợp. Kiểm thử nên chủ động dùng các giá trị khiến luật dễ bị phá.

### 16.1. Kiểm tra identity và associativity của BinaryOperator

Chương trình kiểm tra mẫu dưới đây áp dụng với các **giá trị bất biến** có `equals` phản ánh đúng tính tương đương muốn kiểm chứng:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.BinaryOperator;

public final class ReduceLawChecks {

    static <T> void verifyLaws(
            T identity,
            BinaryOperator<T> op,
            List<T> candidates) {

        for (T a : candidates) {
            if (!Objects.equals(op.apply(identity, a), a)
                    || !Objects.equals(op.apply(a, identity), a)) {
                throw new AssertionError(
                        "Sai identity tại a=" + a
                );
            }

            for (T b : candidates) {
                for (T c : candidates) {
                    T left = op.apply(op.apply(a, b), c);
                    T right = op.apply(a, op.apply(b, c));

                    if (!Objects.equals(left, right)) {
                        throw new AssertionError(
                                "Sai associativity: "
                                + a + ", " + b + ", " + c
                                + " => " + left + " != " + right
                        );
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        verifyLaws(
                0,
                Integer::sum,
                List.of(-3, 0, 2, 7)
        );
        System.out.println("ADD_PASS");

        try {
            verifyLaws(
                    0,
                    (Integer a, Integer b) -> a - b,
                    List.of(2, 3, 7)
            );
            throw new AssertionError("Trừ phải bị phát hiện sai");
        } catch (AssertionError expected) {
            System.out.println("SUBTRACT_FAILED_AS_EXPECTED");
        }

        try {
            verifyLaws(
                    10,
                    Integer::sum,
                    List.of(1, 2, 3)
            );
            throw new AssertionError("Sai identity phải bị phát hiện");
        } catch (AssertionError expected) {
            System.out.println("IDENTITY_FAILED_AS_EXPECTED");
        }
    }
}
~~~

Đây là **kiểm thử trên một tập mẫu**, không phải chứng minh toán học cho mọi giá trị đầu vào. Đặt các ca biên như `Integer.MIN_VALUE`, `Integer.MAX_VALUE` và những số gần ngưỡng nếu lĩnh vực sử dụng cần.

### 16.2. Kiểm tra compatibility của reduce ba tham số

Một phép kiểm tra đủ đơn giản cho các trạng thái kiểu `Long` bất biến:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;

static <T, U> void verifyCompatibility(
        U identity,
        BiFunction<U, T, U> accumulator,
        BinaryOperator<U> combiner,
        List<U> states,
        List<T> elements) {

    for (U u : states) {
        for (T t : elements) {
            U left = combiner.apply(
                    u, accumulator.apply(identity, t)
            );
            U right = accumulator.apply(u, t);

            if (!Objects.equals(left, right)) {
                throw new AssertionError(
                        "Sai compatibility với u=" + u
                        + ", element=" + t
                );
            }
        }
    }
}
~~~

Đặt phương thức static này trong một lớp tiện ích. Sử dụng:

~~~java
import java.util.List;

verifyCompatibility(
        0L,
        (Long sum, String word) -> sum + word.length(),
        Long::sum,
        List.of(0L, 2L, 7L),
        List.of("", "ab", "cde")
); // PASS

// Dùng Long::max sẽ FAIL, ví dụ u=2, t="cde":
// max(2, 3) != 2 + 3.
~~~

Ngoài compatibility, **vẫn cần kiểm tra identity và associativity của combiner**. Một phép kiểm tra compatibility đơn lẻ chưa chứng nhận toàn bộ hợp đồng.

### 16.3. Vì sao không tái sử dụng object mutable trong bộ kiểm tra định luật?

Khi gọi `op.apply(a,b)`, một operator mutable có thể **sửa a hoặc b**. Nếu dùng lại chính hai object đó cho vế còn lại, phép kiểm tra tự phá dữ liệu đầu vào và cho kết quả sai lệch.

Với phép toán mutable, cần:

- Tạo **các container mới** cho từng phép thử, dựa trên cùng dữ liệu bất biến.
- So sánh kết quả **snapshot** trước/sau.
- Kiểm tra cả việc gộp container rỗng và các cách đặt ngoặc khác nhau.
- Xét kỹ xem có nên dùng `collect` thay vì cố dùng `reduce` hay không.

---

## 17. Kiểm chứng kết quả bằng oracle độc lập

Các định luật đại số là điều kiện nền tảng. Ngoài ra, cần một **oracle độc lập** tính kết quả theo đúng bài toán.

Ví dụ tổng nguyên `int` có thể tràn, nên dùng `BigInteger` làm chuẩn để kiểm tra một reducer ứng viên.

~~~java
import java.math.BigInteger;
import java.util.List;

static BigInteger oracleSum(List<Integer> input) {
    BigInteger expected = BigInteger.ZERO;

    for (int n : input) {
        expected = expected.add(BigInteger.valueOf(n));
    }
    return expected;
}

static BigInteger parallelExactSum(List<Integer> input) {
    return input.parallelStream()
            .map(BigInteger::valueOf)
            .reduce(BigInteger.ZERO, BigInteger::add);
}

List<Integer> input = List.of(
        1_500_000_000, 1_500_000_000, -1
);

BigInteger expected = oracleSum(input);
BigInteger actual = parallelExactSum(input);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected " + expected + ", actual " + actual
    );
}

System.out.println(actual); // 2999999999
~~~

Hai phương thức static có thể đặt trong một lớp test. Oracle dùng vòng lặp, không gọi lại chính reducer đang kiểm tra. Với các yêu cầu như tiền tệ và trung bình, oracle phải dùng **kiểu số và quy tắc làm tròn** đúng theo nghiệp vụ.

### 17.1. Ma trận trường hợp phản ví dụ

| Ca kiểm thử | Lỗi dễ lộ |
|---|---|
| Nguồn rỗng | Identity giả, phép max/min thiếu xử lý không có dữ liệu |
| Một phần tử | Identity không đúng, phép toán làm thay đổi giá trị |
| Hai phân vùng đều không rỗng | Combiner bỏ/nhân đôi một phần |
| Ba phần có cách nhóm khác nhau | Associativity bị vi phạm |
| Toàn số âm | `max` với identity 0 |
| Giá trị dương/âm lớn triệt tiêu | `double` và phép `addExact` có thể nhạy cách nhóm |
| Tổng `int` vượt 2.147.483.647 | Tràn kiểu số |
| Nhiều chuỗi với thứ tự | Combiner nối ngược |
| Dữ liệu nhóm có kích thước khác nhau | Trung bình của các trung bình |
| List mutable được dùng làm identity | Chia sẻ container, nhân đôi, data race |
| Nhiều lần chạy parallel | Phát hiện lỗi có tính lịch thực thi |
| Dữ liệu rỗng/null | Thực thi trên nguồn không có dữ liệu hoặc chưa được xác thực |

### 17.2. Chia thủ công để kiểm tra, không cần đoán số thread

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 3, 5, 7);

// Chia [2,3] và [5,7].
List<Integer> leftData = numbers.subList(0, 2);
List<Integer> rightData = numbers.subList(2, 4);

int left = leftData.stream().reduce(0, Integer::sum);
int right = rightData.stream().reduce(0, Integer::sum);

int combined = Integer.sum(left, right);
int full = numbers.stream().reduce(0, Integer::sum);

if (combined != full) {
    throw new AssertionError("Sai phép gộp");
}
~~~

Ví dụ này kiểm tra một phép gộp đúng. Thay `Integer::sum` bằng combiner sai như `Math::max` sẽ tìm được phản ví dụ với dữ liệu phù hợp, dù `parallelStream` trong một lần chạy không nhất thiết chọn đúng ranh giới phân vùng này.

---

## 18. Bộ bài tập nền tảng: tự tìm lỗi trước khi xem đáp án

### Bài 1. Tính tổng đúng

**Đề:** Cho `[4, 8, 3, 5]`. Viết `reduce` hai tham số trả `20` và chứng minh identity, associativity.

**Gợi ý:** Phép cộng và `0`.

**Đáp án:**

~~~java
import java.util.List;

int total = List.of(4, 8, 3, 5).parallelStream()
        .reduce(0, Integer::sum);

System.out.println(total); // 20
~~~

`0 + x = x + 0 = x`. Phép cộng `int` kết hợp theo modulo; tổng mẫu không tràn nên cũng đúng theo số nguyên toán học.

### Bài 2. Tìm identity sai

**Đề:** Với `List.of(2, 3)` và `reduce(5, Integer::sum)`, tính kết quả tuần tự và một cách gộp hai phần.

**Đáp án:**

~~~text
Tuần tự: ((5+2)+3) = 10
Hai phần [2], [3]:
  (5+2) + (5+3) = 7+8 = 15
~~~

Sai vì `5` không phải identity của cộng. Sửa thành `0` rồi cộng giá trị nghiệp vụ `5` một lần sau reduce nếu cần.

### Bài 3. Chứng minh trừ không kết hợp

**Đề:** Tìm ba số nguyên `a,b,c` sao cho `(a-b)-c != a-(b-c)`.

**Đáp án:** `a=10`, `b=3`, `c=2`: hai vế là `5` và `9`. Không dùng phép trừ làm phép giảm gộp kết hợp; có thể tính tổng chi phí trước rồi trừ một lần.

### Bài 4. Lấy max trên toàn số âm

**Đề:** `List.of(-8, -2, -5).stream().reduce(0, Integer::max)` trả gì? Có đúng max dữ liệu không?

**Đáp án:** Trả `0`, sai vì max thật là `-2`. Dùng `reduce(Integer::max)` trả `Optional<Integer>` hoặc identity `Integer.MIN_VALUE` khi chấp nhận giá trị sentinel cho nguồn rỗng.

### Bài 5. Xử lý Stream rỗng

**Đề:** Dự đoán:

~~~java
import java.util.List;

System.out.println(List.<Integer>of().stream()
        .reduce(0, Integer::sum));

System.out.println(List.<Integer>of().stream()
        .reduce(Integer::max));
~~~

**Đáp án:** Dòng đầu in `0`; dòng thứ hai in `Optional.empty`. Hai overload có hợp đồng trả về khác nhau khi không có phần tử.

### Bài 6. Nối chuỗi giữ encounter order

**Đề:** Cho `["J","A","V","A"]`. Viết reduce với identity đúng để nhận `"JAVA"` và cho biết phép toán có cần giao hoán không.

**Đáp án:**

~~~java
String text = List.of("J", "A", "V", "A")
        .parallelStream()
        .reduce("", String::concat);

System.out.println(text); // JAVA
~~~

Nối chuỗi kết hợp, có identity `""`, nhưng không giao hoán. Với List có thứ tự, kết quả giữ encounter order. Trong nghiệp vụ nối nhiều chuỗi, cân nhắc `Collectors.joining()` để giảm chi phí cấp phát.

### Bài 7. Đúng hay sai: accumulator và combiner không cần cùng ý nghĩa

**Đề:**

~~~java
long n = List.of("aa", "bbb").parallelStream()
        .reduce(
                0L,
                (sum, s) -> sum + s.length(),
                Long::max
        );
~~~

**Đáp án:** Sai. Khi hai phần tách ra, kết quả trung gian là `2` và `3`, `max(2,3)=3` khác tổng đúng `5`. Sửa combiner thành `Long::sum`.

---

## 19. Bộ bài tập trung cấp: thiết kế phép gộp và phản ví dụ

### Bài 8. Tính tổng độ dài bằng ba tham số

**Đề:** Cho `List.of("a","bb","ccc")`. Viết overload ba tham số trả `6L` và nêu compatibility.

**Đáp án:**

~~~java
import java.util.List;

long length = List.of("a", "bb", "ccc")
        .parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(length); // 6
~~~

Với mọi trạng thái hợp lệ `u` và chuỗi `s`, `u + (0 + len(s)) = u + len(s)` nên compatibility đúng. `Long::sum` có identity 0 và kết hợp theo số học `long` modulo.

### Bài 9. Chia hai phân vùng để bắt lỗi combiner

**Đề:** Reducer có accumulator cộng nhưng combiner `(a,b) -> a`. Nguồn `[2,3,5,7]`. Tính theo hai phân vùng `[2,3]` và `[5,7]`.

**Đáp án:** Trái = `5`, phải = `12`. Combiner sai trả `5` thay vì `17`. Sửa combiner thành `Integer::sum`.

### Bài 10. Nối chuỗi bị đảo

**Đề:** Vì sao `reduce("", (s,t)->s+t, (left,right)->right+left)` không phù hợp để giữ thứ tự trên `["A","B","C"]`?

**Đáp án:** Hai phần `["A"]` và `["B","C"]` cho `"A"`, `"BC"`. Combiner sai trả `"BCA"` thay vì `"ABC"`. Cần dùng `left + right` theo thứ tự phân vùng.

### Bài 11. Tính trung bình với các phân vùng không đều

**Đề:** Nhóm thứ nhất có `[10,20]`, nhóm thứ hai có `[100]`. Có thể gộp bằng trung bình hai giá trị average không?

**Đáp án:** Không. `(15+100)/2=57.5` sai, trung bình thật `130/3≈43.3333`. Thiết kế trạng thái `(sum,count)`, accumulator thêm vào cả hai trường, combiner cộng từng trường rồi chia trong bước hoàn thiện cuối.

### Bài 12. Tràn số với identity đúng

**Đề:** `reduce(0, Integer::sum)` trên hai số `1_500_000_000` có sai định luật associativity không? Có đúng tổng nghiệp vụ không?

**Đáp án:** Phép cộng `int` kết hợp theo modulo nên không sai định luật dưới cách hiểu đó. Nhưng kết quả `-1294967296` không phải tổng nguyên toán học `3_000_000_000`. Nâng sang `long` trước khi cộng hoặc dùng `BigInteger` nếu miền lớn hơn `long`.

### Bài 13. Chọn collect hay reduce?

**Đề:** Muốn nhận `List<String>` từ nhiều phần tử String, có nên dùng identity `new ArrayList<>()` rồi sửa list trong accumulator của `reduce` không?

**Đáp án:** Không. Đây là mục tiêu gom container mutable; nên dùng `collect(ArrayList::new, List::add, List::addAll)`, `Collectors.toList()` hoặc `Stream.toList()`. Identity mutable trong reduce ba tham số có thể bị chia sẻ và gây sai kết quả.

### Bài 14. BigDecimal và làm tròn

**Đề:** Một `reduce` cộng `BigDecimal` bằng `add(b, new MathContext(2))` tại mọi bước. Có đảm bảo phép gộp kết hợp không?

**Đáp án:** Không. Bộ ba `9.9, 0.2, -9.9` cho `(a+b)+c=0.1` và `a+(b+c)=0.2` với `MathContext(2, HALF_UP)`. Nếu đúng nghiệp vụ, cộng không làm tròn trung gian rồi làm tròn một lần cuối.

### Bài 15. Kiểm tra luật không đủ chứng minh đúng nghiệp vụ

**Đề:** Một reducer `Integer::sum` qua kiểm tra identity/associativity trên một tập giá trị mẫu. Có thể kết luận an toàn cho mọi tổng tiền không?

**Đáp án:** Không. Cần kiểm tra miền số và quy tắc tiền tệ: tràn `int` vẫn có thể xảy ra. Kiểm tra với oracle `BigInteger` hoặc số cent trong kiểu đủ rộng, thêm các ca biên và chính sách làm tròn.

### Bài 16. Phép gộp với hai mục tiêu

**Đề:** Bạn cần biết **tổng số lượng** và **tổng tiền** của tất cả giao dịch. Có nên dùng hai biến mutable bên ngoài lambda của `parallelStream().forEach`?

**Đáp án:** Không. Tạo một trạng thái tổng hợp chứa cả hai trường, với accumulator/combiner trả trạng thái mới (nếu dùng `reduce`) hoặc dùng collector với supplier riêng và combiner đúng (nếu dùng `collect`). Kiểm tra việc gộp hai phân vùng và kết quả oracle độc lập.

Ví dụ minh họa bằng `record`:

~~~java
import java.math.BigInteger;
import java.util.List;

record Sale(long units, long cents) {}
record Totals(BigInteger units, BigInteger cents) {

    Totals add(Sale sale) {
        return new Totals(
                units.add(BigInteger.valueOf(sale.units())),
                cents.add(BigInteger.valueOf(sale.cents()))
        );
    }

    Totals merge(Totals other) {
        return new Totals(
                units.add(other.units()),
                cents.add(other.cents())
        );
    }
}

List<Sale> sales = List.of(
        new Sale(2, 1200),
        new Sale(1, 500),
        new Sale(-1, -500)
);

Totals totals = sales.parallelStream()
        .reduce(
                new Totals(BigInteger.ZERO, BigInteger.ZERO),
                Totals::add,
                Totals::merge
        );

System.out.println(totals.units()); // 2
System.out.println(totals.cents()); // 1200
~~~

Kết quả phù hợp vì identity trung hòa từng trường, phép cộng `BigInteger` kết hợp và không sửa một container dùng chung.

---

## 20. Checklist tự chấm trước khi nộp phép reduce

Đối với mỗi phép giảm gộp do bạn tự viết, trả lời được các câu hỏi:

| Câu hỏi kiểm tra | Bằng chứng cần có |
|---|---|
| **Identity là gì?** | Chỉ ra `f(e,x)=x` và `f(x,e)=x` trên miền dữ liệu |
| **Phép gộp có kết hợp?** | Giải thích đại số, thử `(a⊕b)⊕c` và `a⊕(b⊕c)` |
| **Có cần giao hoán không?** | Không mặc định; xác định có yêu cầu encounter order hay không |
| **Dạng ba tham số có tương thích?** | Thử `combine(u,acc(e,t)) = acc(u,t)` |
| **Lambda có stateless/non-interfering?** | Không sửa nguồn, không phụ thuộc biến thay đổi bên ngoài |
| **Identity hoặc trạng thái có mutable?** | Không chia sẻ một object mutable sai cách qua `reduce` |
| **Nguồn rỗng trả gì?** | Giá trị identity hoặc `Optional.empty` đúng hợp đồng |
| **Kiểu số có đủ miền không?** | Kiểm tra overflow, độ chính xác và rounding mode |
| **Có giữ đúng thứ tự cần thiết?** | Với nối chuỗi/danh sách, không đảo kết quả phân vùng |
| **Đã test phân vùng khác nhau?** | Hai phần không rỗng, ba phần với hai cây gộp |
| **Đã có oracle độc lập?** | Vòng lặp/tính tay/`BigInteger` theo yêu cầu nghiệp vụ |
| **Có cần collect thay reduce?** | Nếu mục tiêu là container mutable, ưu tiên collector đúng hợp đồng |

### 20.1. Sơ đồ chọn giải pháp

~~~text
Muốn tổng hợp Stream?
        |
        v
Có phải gom vào container mutable (List/Map/Set)?
        |--- Có ---> Ưu tiên collect/Collector
        |
        v
Có một phép kết hợp trên kiểu T và identity hợp lệ?
        |--- Có ---> reduce(identity, operator)
        |
        v
Không có identity tổng quát nhưng cần max/min/so sánh?
        |--- Có ---> reduce(BinaryOperator) -> Optional<T>
        |
        v
Kiểu trạng thái U khác kiểu T?
        |--- Có ---> reduce(identity, accumulator, combiner)
        |             với compatibility + associativity
        |
        v
Cần thứ tự xử lý tuần tự đặc biệt hoặc thao tác không kết hợp?
        |--- Có ---> Xem lại thuật toán; không ép vào parallel reduce
        |
        v
Kiểm định định luật + oracle + ca biên
        |
        v
Chỉ khi đúng mới đo hiệu năng parallel
~~~

### 20.2. Những điều không thể suy ra từ một lần chạy

- `sequential == parallel` **không chứng minh** identity và associativity đúng: có thể chưa kích hoạt đường gọi combiner.
- `sequential == parallel` **không chứng minh** tổng tiền đúng: cả hai có thể cùng overflow.
- `parallel` trả một lần đúng **không bảo đảm** mọi lịch chia/gộp khác cũng đúng.
- Bộ test trên ít giá trị **không phải chứng minh toán học** cho mọi dữ liệu.
- Thêm `synchronized`/`AtomicInteger` **không tự sửa** một thuật toán có combiner hoặc identity sai.
- “Có dùng nhiều CPU” **không thay thế** bài toán kiểm tra kết quả số và ngữ nghĩa dữ liệu.

---

## Tổng kết

Một phép `reduce` tốt cần **giá trị đơn vị**, **phép toán kết hợp** và hành vi **stateless/non-interfering**. Với overload ba tham số, accumulator và combiner còn phải **tương thích**. Hãy dùng **phản ví dụ nhỏ** để tìm lỗi: identity 10 cho phép cộng, phép trừ, `max` với 0 trên số âm, combiner lấy max thay vì cộng, ghép chuỗi ngược, hoặc danh sách mutable dùng làm identity. Sau đó kiểm tra kết quả với **oracle độc lập** và dữ liệu biên, đặc biệt khi chuyển sang xử lý song song.

**Ghi nhớ:** `reduce` không phải “vòng lặp bất kỳ được viết bằng lambda”. Nó là một **phép giảm gộp có hợp đồng đại số**, được thiết kế để Stream API có thể chia công việc và ghép lại mà vẫn giữ đúng kết quả. Khi hiểu và tự kiểm chứng hợp đồng đó, bạn có thể dùng `reduce`, `collect` và các pipeline Java Stream API song song một cách có căn cứ.

