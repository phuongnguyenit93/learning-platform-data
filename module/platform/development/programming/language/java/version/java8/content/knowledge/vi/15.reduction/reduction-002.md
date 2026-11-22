# Identity và giá trị trung hòa trong Java Stream Reduction

Khi dùng `Stream.reduce(...)`, tham số `identity` (phần tử đơn vị, hay **giá trị trung hòa**) là giá trị **không làm thay đổi kết quả của phép kết hợp**. Nó cũng là kết quả khi stream rỗng đối với các overload nhận `identity`. Chọn đúng `identity` quyết định kết quả đúng, nhất là khi cùng một phép reduction được chạy với `parallelStream()`.

Bài học thuộc **Reduction trong Java 8**, sử dụng các API Stream vẫn hiện hành trong các phiên bản Java mới. Mọi ví dụ chạy được trên JDK 17+ và không dùng API lỗi thời.

## 1. Identity khác gì với một giá trị khởi tạo tùy ý?

Giả sử ta gộp hai giá trị bằng phép toán `⊕`. Một giá trị `e` là identity nếu:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

với **mọi giá trị x hợp lệ trong miền dữ liệu**. Hai đẳng thức cho thấy thêm `e` ở đầu hoặc cuối phép gộp đều không đổi kết quả.

Ví dụ:

~~~text
0 + 7 = 7           7 + 0 = 7       → identity của phép cộng là 0
1 × 7 = 7           7 × 1 = 7       → identity của phép nhân là 1
"" + "Java" = "Java"                 → identity của nối chuỗi là ""
true && false = false              → identity của phép AND là true
false || true = true                → identity của phép OR là false
~~~

**`identity` gắn với phép kết hợp, không gắn với kiểu dữ liệu.** Cùng kiểu `Integer`, cộng dùng `0`, nhân dùng `1`, min/max cần xét miền giá trị. Số `10` có thể là *giá trị cộng thêm của nghiệp vụ* nhưng không phải identity của phép cộng.

Cũng cần phân biệt identity với **phần tử đầu tiên**: `reduce(BinaryOperator)` không nhận identity, nên chỉ có thể trả `Optional` khi không chắc stream có dữ liệu.

## 2. Vì sao identity phải đi cùng tính kết hợp (*associativity*)?

Với phép kết hợp `⊕`, ngoài identity còn cần:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

Đây là **tính kết hợp**. Khi stream chạy song song, Java có thể chia phần tử thành nhiều nhóm, gộp từng nhóm và kết hợp các kết quả trung gian. Cách nhóm không được làm thay đổi ý nghĩa kết quả.

Ví dụ tổng của `[2, 3, 4, 5]`:

~~~text
Tuần tự: 0 + 2 + 3 + 4 + 5 = 14
Chia nhóm (minh họa):
    nhóm 1: 0 + 2 + 3 = 5
    nhóm 2: 0 + 4 + 5 = 9
    gộp:   5 + 9     = 14
~~~

Nếu nhầm `10` là identity:

~~~text
Tuần tự: 10 + 2 + 3 + 4 + 5 = 24
Chia nhóm (minh họa):
    nhóm 1: 10 + 2 + 3 = 15
    nhóm 2: 10 + 4 + 5 = 19
    gộp:   15 + 19      = 34  (sai)
~~~

Đây là **một cách chia nhóm minh họa**, không phải lời khẳng định Java luôn chia thành đúng hai nhóm. Kết quả sai có thể phụ thuộc cách phân hoạch thực tế; vì vậy lỗi identity đôi khi bị che giấu trong stream tuần tự nhưng xuất hiện khi chạy song song.

Phép trừ không có tính kết hợp: `(10 - 4) - 2 = 4`, còn `10 - (4 - 2) = 8`. Vì vậy `reduce(0, (a, b) -> a - b)` vừa vi phạm quy tắc identity bên trái (`0 - x != x` với `x != 0`), vừa dùng phép toán không kết hợp. Đừng sử dụng reduction như vậy rồi dựa vào thứ tự thực thi tình cờ.

## 3. Những identity phổ biến và các giới hạn cần nhớ

| Phép toán gộp | Identity | Lưu ý |
| --- | --- | --- |
| Tổng số nguyên, `Integer::sum` | `0` | Khi tổng có thể vượt phạm vi `int`, chọn kiểu/chiến lược số thích hợp. |
| Tích số nguyên, `(a,b) -> a * b` | `1` | Tương tự, cần xem nguy cơ tràn số. |
| Nối chuỗi `String::concat` | `""` | Đúng về kết quả, nhưng nối quá nhiều chuỗi có thể tốn chi phí sao chép. |
| Boolean AND | `true` | Tương ứng chân trị của “mọi phần tử đều thỏa” trên tập rỗng. |
| Boolean OR | `false` | Tương ứng “có ít nhất một phần tử thỏa” trên tập rỗng. |
| Min trên toàn bộ miền `int` | `Integer.MAX_VALUE` | Nếu stream rỗng thì nhận `MAX_VALUE`; dễ bị hiểu là dữ liệu thực. |
| Max trên toàn bộ miền `int` | `Integer.MIN_VALUE` | Nếu stream rỗng thì nhận `MIN_VALUE`; dễ bị hiểu là dữ liệu thực. |

Các giá trị lớn nhất/nhỏ nhất chỉ là identity đúng khi **miền dữ liệu và comparator** cho phép. Với kiểu đối tượng, miền giá trị khác, hoặc `null`, không tự áp dụng sentinel. Nếu cần phân biệt “không có phần tử” và “kết quả đúng bằng sentinel”, dùng `reduce(BinaryOperator)` hoặc `min`/`max` trả `Optional`/`OptionalInt`.

Ví dụ sai thường gặp:

~~~java
int wrongMax = Stream.of(-8, -3, -5).reduce(0, Integer::max);
// wrongMax = 0, dù 0 không xuất hiện trong dữ liệu.
~~~

Vì `0` không trung hòa đối với max của các số âm. Cách tự nhiên hơn:

~~~java
Optional<Integer> max = Stream.of(-8, -3, -5).reduce(Integer::max);
// max = Optional[-3].
~~~

## 4. Ba overload `Stream.reduce` và hợp đồng sử dụng

### 4.1. `Optional<T> reduce(BinaryOperator<T> accumulator)`

Không truyền identity. Với stream rỗng, kết quả là `Optional.empty()`; với stream có phần tử, kết quả là `Optional` chứa giá trị gộp. Hàm kết hợp vẫn phải associative, stateless và không can thiệp vào nguồn stream.

~~~java
Optional<Integer> max = Stream.of(-8, -3, -5).reduce(Integer::max);
Optional<Integer> missing = Stream.<Integer>empty().reduce(Integer::max);
~~~

Với thao tác min/max, mẫu này tránh nhầm sentinel với dữ liệu thực. Không gọi `get()` nếu chưa biết `Optional` có giá trị; dùng `orElse`, `orElseThrow`, hoặc xử lý điều kiện phù hợp nghiệp vụ.

### 4.2. `T reduce(T identity, BinaryOperator<T> accumulator)`

Kiểu phần tử đầu vào và kết quả cùng là `T`. Hàm gộp có tính kết hợp, còn `identity` phải là phần tử trung hòa của hàm gộp.

~~~java
int sum = Stream.of(2, 3, 4, 5).reduce(0, Integer::sum);
int product = Stream.of(2, 3, 4, 5)
                    .reduce(1, (a, b) -> a * b);
~~~

Với stream rỗng, hai phép trên lần lượt trả `0` và `1`. Điều đó đúng theo đại số của phép gộp, nhưng không nhất thiết có nghĩa “đã tìm thấy dữ liệu”.

Về mặt tuần tự có thể hình dung:

~~~java
T result = identity;
for (T element : source) {
    result = accumulator.apply(result, element);
}
~~~

Đây là **mô hình để hiểu ý nghĩa**, không phải bảo đảm Java luôn thực thi đúng một vòng lặp như vậy. Với parallel stream, các nhóm có thể được gộp độc lập.

### 4.3. `U reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)`

Overload ba tham số dùng khi **kiểu phần tử `T` khác kiểu kết quả `U`**, hoặc phép tích lũy cần bước chuyển đổi. Ví dụ: stream các chuỗi `String` → tổng độ dài kiểu `Integer`.

~~~java
List<String> words = Arrays.asList("Java", "8", "Stream");

int length = words.stream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
// length = 11
~~~

Vai trò của từng tham số:

- `identity = 0`: giá trị trung hòa để gộp các tổng độ dài.
- `accumulator(total, word)`: tích lũy **một phần tử đầu vào** vào kết quả trung gian kiểu `Integer`.
- `combiner(leftTotal, rightTotal)`: gộp **hai kết quả trung gian cùng kiểu `Integer`**, nhất là khi chia nhóm xử lý song song.

Để đúng, `combiner` phải associative, có identity, và tương thích `accumulator`. Với mọi kết quả trung gian `u` và phần tử `t`, cần:

~~~text
combiner(identity, u) = u
combiner(u, accumulator(identity, t)) = accumulator(u, t)
~~~

Cách hiểu công thức thứ hai: tích lũy `t` vào một nhóm rỗng rồi gộp vào `u` phải bằng tích lũy `t` trực tiếp vào `u`. Với ví dụ độ dài, hai vế đều bằng `u + t.length()`. `combiner` cũng cần thỏa `combiner(combiner(a,b),c) = combiner(a,combiner(b,c))`.

Trong nhiều trường hợp, viết tường minh `mapToInt(String::length).sum()` dễ đọc hơn. Không cần ép sử dụng overload ba tham số nếu API chuyên dụng diễn tả yêu cầu rõ hơn.

## 5. Ví dụ Java hoàn chỉnh, có thể chạy

Lưu mã vào tệp `IdentityReductionExample.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class IdentityReductionExample {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(2, 3, 4, 5);

        int sum = numbers.stream().reduce(0, Integer::sum);
        int parallelSum = numbers.parallelStream()
                                 .reduce(0, Integer::sum);
        int product = numbers.stream().reduce(1, (a, b) -> a * b);

        int emptySum = Stream.<Integer>empty()
                             .reduce(0, Integer::sum);
        int emptyProduct = Stream.<Integer>empty()
                                 .reduce(1, (a, b) -> a * b);

        Optional<Integer> max = Stream.of(-8, -3, -5)
                                      .reduce(Integer::max);
        Optional<Integer> emptyMax = Stream.<Integer>empty()
                                           .reduce(Integer::max);
        int wrongMax = Stream.of(-8, -3, -5)
                             .reduce(0, Integer::max);

        List<String> words = Arrays.asList("Java", "8", "Stream");
        int totalLength = words.stream().reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum);
        int parallelLength = words.parallelStream().reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum);

        String joined = words.stream().reduce("", String::concat);
        String collected = words.stream().collect(
                StringBuilder::new,
                (builder, word) -> builder.append(word),
                (left, right) -> left.append(right))
                .toString();

        System.out.println("sum = " + sum);
        System.out.println("parallelSum = " + parallelSum);
        System.out.println("product = " + product);
        System.out.println("emptySum = " + emptySum);
        System.out.println("emptyProduct = " + emptyProduct);
        System.out.println("max = " + max);
        System.out.println("emptyMax = " + emptyMax);
        System.out.println("wrongMax = " + wrongMax);
        System.out.println("totalLength = " + totalLength);
        System.out.println("parallelLength = " + parallelLength);
        System.out.println("joined = " + joined);
        System.out.println("collected = " + collected);
    }
}
~~~

Biên dịch và chạy (JDK 17+; các API dùng trong ví dụ đã có từ Java 8):

~~~bash
javac -encoding UTF-8 IdentityReductionExample.java
java IdentityReductionExample
~~~

Kết quả:

~~~text
sum = 14
parallelSum = 14
product = 120
emptySum = 0
emptyProduct = 1
max = Optional[-3]
emptyMax = Optional.empty
wrongMax = 0
totalLength = 11
parallelLength = 11
joined = Java8Stream
collected = Java8Stream
~~~

Các điểm cần quan sát:

1. Hai cách cộng tuần tự/song song đều bằng `14` vì `0` thực sự trung hòa và phép cộng các giá trị này có tính kết hợp.
2. Stream rỗng trả lại identity với `reduce(identity, ...)`, nhưng dạng không identity trả `Optional.empty()`.
3. `wrongMax` thể hiện lỗi **sai identity**, dù chương trình vẫn biên dịch và chạy.
4. Overload ba tham số xử lý `String → Integer`; `combiner = Integer::sum` khớp với cách `accumulator` tính độ dài.
5. `String::concat` đúng về ngữ nghĩa cho các ví dụ nhỏ; `collect` với `StringBuilder` minh họa cách gom nhiều chuỗi vào vùng chứa có thể thay đổi.

## 6. Phân biệt identity với giá trị ban đầu của nghiệp vụ

Giả sử đã có tổng `10` từ một nguồn khác, và cần cộng thêm các số `[2,3,4,5]` đúng **một lần**. Không nên đưa `10` vào identity của phép cộng:

~~~java
// Sai về hợp đồng reduce: 10 không phải identity của phép cộng
int wrongDesign = numbers.stream().reduce(10, Integer::sum);

// Đúng: giảm với identity thực sự, rồi cộng lượng có sẵn một lần
int existingTotal = 10;
int finalTotal = existingTotal
        + numbers.stream().mapToInt(Integer::intValue).sum();
// finalTotal = 24
~~~

Ở pipeline tuần tự, `wrongDesign` có thể cũng cho `24`; sự trùng khớp đó không biến `10` thành identity hợp lệ. Nếu mỗi nhóm của parallel stream bắt đầu với `10`, giá trị này có thể bị tính nhiều lần.

Nếu cần biết “danh sách có dữ liệu hay không”, đừng suy diễn từ kết quả bằng identity (tổng bằng `0` cũng có thể đến từ phần tử hợp lệ). Hãy biểu diễn riêng điều kiện tồn tại dữ liệu hoặc dùng `Optional` tùy yêu cầu.

## 7. Lỗi phổ biến và lựa chọn API đúng

### Lỗi 1 — Dùng mutable identity với `reduce`

~~~java
// KHÔNG dùng: cùng đối tượng ArrayList có thể được sửa ở nhiều nhánh.
List<String> broken = words.parallelStream().reduce(
    new java.util.ArrayList<String>(),
    (list, word) -> { list.add(word); return list; },
    (left, right) -> { left.addAll(right); return left; }
);
~~~

Đoạn trên là **phản ví dụ**: `identity` là một đối tượng có thể thay đổi; accumulator/combiner sửa chính các đối tượng được truyền vào. Nó vi phạm hợp đồng reduction, dễ tạo kết quả sai hoặc hành vi bất định khi parallel. Không chạy và dựa vào kết quả ngẫu nhiên của đoạn này.

Muốn gom vào danh sách, dùng mutable reduction:

~~~java
List<String> safe = words.parallelStream()
                         .collect(java.util.stream.Collectors.toList());
~~~

Hoặc dùng `collect(supplier, accumulator, combiner)` để tạo vùng chứa riêng và gộp đúng cách. Chọn `reduce` cho phép kết hợp trả **giá trị mới**, chọn `collect` khi mục đích là **tích lũy vào vùng chứa mutable**.

### Lỗi 2 — Nhầm neutral với “giá trị mặc định có vẻ hợp lý”

`reduce(0, Integer::max)` sai khi dữ liệu có số âm; `reduce(1, Integer::sum)` sai khi cộng; `reduce("", String::concat)` hợp lệ nhưng `reduce("prefix", String::concat)` không còn có identity trung hòa. Nếu muốn thêm tiền tố vào kết quả, hãy thêm vào **sau phép reduce** hoặc dùng cấu trúc kết quả có hợp đồng chính xác.

### Lỗi 3 — Cho rằng cứ có identity là có thể chạy song song đúng

Identity đúng **chưa đủ**: phép gộp phải associative, stateless và non-interfering; overload ba tham số còn cần accumulator/combiner tương thích. Với số thực `double`, phép cộng có thể cho sai khác làm tròn tùy thứ tự nhóm, vì phép cộng dấu phẩy động không hoàn toàn associative theo nghĩa tính toán bitwise. Nếu độ chính xác yêu cầu cao, cân nhắc miền số, thuật toán và cách thực thi phù hợp.

### Lỗi 4 — Dùng `reduce` thay các terminal operation đã diễn đạt rõ ý định

Với số nguyên từ `IntStream`, `sum()` thường dễ đọc hơn `reduce(0, Integer::sum)`, `min()`/`max()` trả `OptionalInt` nên thể hiện tập rỗng rõ hơn. Dùng `anyMatch` và `allMatch` cho điều kiện tồn tại/toàn bộ, vì các API này còn có thể dừng sớm. `reduce` không thay thế mọi terminal operation về hành vi ngắn mạch hoặc hiệu năng.

### Lỗi 5 — Bỏ qua tràn số và giới hạn phạm vi

`int` có giới hạn; tổng/tích có thể tràn và cho giá trị không đúng kỳ vọng nghiệp vụ. Kiểm tra miền dữ liệu, chọn `long`/`BigInteger` hoặc xử lý tràn bằng `Math.addExact` khi phù hợp. Việc toán tử cộng `int` có tính kết hợp theo số học tràn kiểu Java **không có nghĩa** kết quả là tổng toán học chính xác.

### Lỗi 6 — Quên domain và tính duy nhất của identity

Với phép max trên toàn bộ `int`, `Integer.MIN_VALUE` là phần tử trung hòa nhưng cũng **có thể chính là giá trị dữ liệu**. Kết quả `Integer.MIN_VALUE` không đủ để phân biệt “stream rỗng” với “stream chứa đúng `Integer.MIN_VALUE`”. Khi sự khác nhau quan trọng, dùng `Optional`/`OptionalInt`.

## 8. Checklist trước khi chọn identity cho một reduction

1. **Xác định phép gộp thực tế.** Phép cộng, phép nhân, min, max, nối chuỗi, hợp tập hợp… có identity khác nhau.
2. **Xác định miền dữ liệu.** Tìm giá trị `e` sao cho `combine(e, x) = combine(x, e) = x` với mọi `x` hợp lệ.
3. **Kiểm tra tính kết hợp.** Thử so sánh `combine(combine(a,b),c)` với `combine(a,combine(b,c))`; đặc biệt cẩn thận với subtraction, rounding và side effect.
4. **Với overload ba tham số, kiểm tra hai hợp đồng.** `combiner(identity,u)=u` và `combiner(u,accumulator(identity,t))=accumulator(u,t)`.
5. **Tự hỏi stream rỗng có ý nghĩa gì.** Nếu identity không diễn tả được “không có dữ liệu”, dùng `Optional` hoặc thiết kế kiểu kết quả rõ ràng.
6. **Kiểm tra tính an toàn khi chia nhóm.** Không đếm identity nhiều lần, không chia sẻ đối tượng mutable, không phụ thuộc thứ tự kết hợp tình cờ.
7. **Ưu tiên API chuyên dụng khi phù hợp.** `sum`, `min`, `max`, `count`, `collect`, `anyMatch`, `allMatch` thường rõ nghĩa và tránh nhiều lỗi.

**Ghi nhớ:** Identity là giá trị trung hòa của **phép kết hợp**, còn associativity và hợp đồng accumulator/combiner giúp reduction giữ đúng ý nghĩa khi Java thay đổi cách phân nhóm thực thi. Khi không tồn tại identity phù hợp hoặc cần nhận biết stream rỗng, hãy dùng overload trả `Optional` hay một API tổng hợp chuyên dụng.

## Tài liệu chuẩn

- [Oracle Java SE 25 — Stream.reduce, overload và hợp đồng identity/combiner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — java.util.stream: Reduction, Associativity, Mutable reduction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
