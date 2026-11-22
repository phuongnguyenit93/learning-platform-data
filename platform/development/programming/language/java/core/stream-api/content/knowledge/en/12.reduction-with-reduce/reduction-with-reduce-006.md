# Tính tương thích giữa accumulator và combiner

Trong Java Stream API, `reduce` biến nhiều phần tử thành một giá trị kết quả. Với dạng ba tham số, chương trình có thể **tích lũy từng phần tử** bằng `accumulator`, rồi **gộp các kết quả từng phần** bằng `combiner`. Hai hàm này phải phối hợp đúng: nếu không, pipeline tuần tự có thể cho kết quả hợp lý nhưng `parallelStream()` lại trả về giá trị sai.

Bài học thuộc chương **Phép rút gọn với reduce** của module **JAVA_STREAM_API**. Đây là điểm nối giữa xử lý dữ liệu khai báo (`map`, `filter`, `reduce`, `collect`) với tính lười của pipeline, khả năng chia dữ liệu qua `Spliterator`, xử lý song song và các giới hạn về trạng thái cũng như hiệu năng. Trọng tâm là **hợp đồng tương thích giữa `accumulator` và `combiner`**, chứ không chỉ là biết cú pháp gọi `reduce`.

## 1. Vì sao reduce cần combiner?

Hãy tưởng tượng cần tính tổng độ dài của các chuỗi:

```java
List<String> words = Arrays.asList("Java", "Stream", "API");
```

Nếu xử lý tuần tự, ta có thể lần lượt cộng:

```text
0 -- + length("Java") = 4 --> 4
4 -- + length("Stream") = 6 --> 10
10 -- + length("API") = 3 --> 13
```

Khi xử lý song song, Java có thể chia nguồn thành những phần độc lập:

```text
              ["Java", "Stream", "API"]
                     /           \
             ["Java", "Stream"]   ["API"]
                   |                 |
             accumulator          accumulator
                   |                 |
                  10                 3
                     \             /
                         combiner
                            |
                           13
```

Sơ đồ chỉ minh họa một cách chia dữ liệu. Java không hứa số nhánh, kích thước từng nhánh hoặc thứ tự luồng thực thi cố định. Tuy nhiên, **bất kể chia ra sao**, kết quả logic cần nhất quán với hợp đồng của phép rút gọn.

`accumulator` xử lý từng phần tử **bên trong một kết quả từng phần**. `combiner` gộp **hai kết quả từng phần**. Vì vậy, cùng một quy tắc toán học phải được giữ nguyên dù tính tất cả trong một nhánh hay phân thành nhiều nhánh.

## 2. Cú pháp reduce ba tham số

Phương thức trên `Stream<T>` có dạng:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Ý nghĩa từng tham số:

| Thành phần | Vai trò | Đầu vào và đầu ra |
| --- | --- | --- |
| `identity` | Giá trị trung lập để khởi đầu kết quả từng phần | Kiểu `U` |
| `accumulator` | Nhận kết quả đang có và một phần tử nguồn, tạo kết quả mới | `(U, T) -> U` |
| `combiner` | Nhận hai kết quả từng phần, tạo kết quả đã gộp | `(U, U) -> U` |

Kiểu phần tử nguồn `T` **có thể khác** kiểu kết quả `U`. Ví dụ, nguồn là `String` nhưng kết quả là `Integer`:

```java
int totalLength = words.stream().reduce(
    0,
    (subtotal, word) -> subtotal + word.length(),
    Integer::sum
);
// totalLength = 13
```

Ở đây, `identity = 0`; `accumulator` chuyển từng `String` thành đóng góp độ dài và cộng vào `Integer`; `combiner` cộng hai `Integer`.

Đừng nhầm hai hàm vì tên gọi: `accumulator` **không nhận hai phần tử của Stream**, mà nhận **một kết quả từng phần kiểu U** và **một phần tử kiểu T**. `combiner` không nhận phần tử nguồn, mà chỉ nhận **hai giá trị kết quả kiểu U**.

## 3. Ba yêu cầu để phép rút gọn hoạt động đúng

Hợp đồng `reduce(identity, accumulator, combiner)` đòi hỏi các hàm dùng để rút gọn có tính **không can thiệp vào nguồn** (*non-interfering*) và **không phụ thuộc trạng thái thay đổi bên ngoài** (*stateless*). Về toán học, cần đặc biệt chú ý ba quan hệ dưới đây.

### 3.1. Identity là phần tử trung lập với combiner

Với mọi kết quả từng phần `u`, hợp đồng yêu cầu:

\[
\operatorname{combiner}(\operatorname{identity},u)=u
\]

Ví dụ với phép cộng:

```java
Integer identity = 0;
int u = 7;
int combined = Integer.sum(identity, u); // 7
```

`0` là giá trị trung lập cho phép cộng. Với phép nhân, giá trị trung lập là `1`; với nối chuỗi, là `""`. Trong những phép gộp thường gặp, identity trung lập ở **cả hai phía**, giúp việc phân nhóm độc lập không làm thay đổi kết quả.

Đưa một giá trị khởi đầu **không trung lập** vào `reduce` có thể khiến nó bị tính nhiều lần khi nguồn được chia thành nhiều phần.

### 3.2. Combiner phải có tính kết hợp

Với các kết quả từng phần `a`, `b`, `c`, cần có:

\[
\operatorname{combiner}(\operatorname{combiner}(a,b),c)
=\operatorname{combiner}(a,\operatorname{combiner}(b,c))
\]

Kết hợp (*associative*) **khác với giao hoán** (*commutative*). Phép nối chuỗi có tính kết hợp:

```text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
```

Nhưng nói chung không có tính giao hoán: `"A" + "B"` khác `"B" + "A"`. Với nguồn có encounter order, một phép reduce được viết đúng vẫn có thể bảo toàn thứ tự khi gộp các phần kết quả. Không được tự ý dùng `unordered()` khi thứ tự là một phần ý nghĩa của kết quả.

Phép trừ không có tính kết hợp: `(10 - 5) - 2 = 3`, còn `10 - (5 - 2) = 7`. Vì vậy, không nên dùng phép trừ làm `combiner` cho một phép rút gọn song song theo nghĩa trừ lần lượt.

### 3.3. Accumulator và combiner phải tương thích

Đây là ràng buộc trung tâm của bài. Với mọi giá trị kết quả từng phần `u` và phần tử nguồn `t`, hợp đồng yêu cầu:

\[
\boxed{
\operatorname{combiner}
\big(u,\operatorname{accumulator}(\operatorname{identity},t)\big)
=\operatorname{accumulator}(u,t)
}
\]

Diễn đạt bằng lời:

> **Tích lũy trực tiếp phần tử `t` vào `u` phải tương đương với việc tích lũy `t` từ identity để tạo một kết quả riêng, rồi dùng combiner gộp kết quả đó vào `u`.**

Điều kiện này bảo đảm phép tính không thay đổi ý nghĩa khi Java **tách một phần tử (hoặc một nhóm phần tử) sang nhánh khác** rồi gộp trở lại. Chỉ kiểm tra `combiner` có tính kết hợp là **chưa đủ**.

Với bài toán tổng độ dài chuỗi, đặt:

```text
identity                 = 0
accumulator(u, t)        = u + length(t)
combiner(left, right)    = left + right
```

Lấy `u = 4`, `t = "Stream"` (độ dài 6):

```text
combiner(4, accumulator(0, "Stream"))
= combiner(4, 6)
= 10

accumulator(4, "Stream")
= 4 + 6
= 10
```

Hai vế bằng nhau; quy tắc cũng đúng cho mọi `u` và chuỗi `t` trong miền giá trị mà phép cộng được định nghĩa theo ý định của bài toán.

## 4. Ví dụ đúng: tổng độ dài chuỗi ở cả hai chế độ

Chương trình hoàn chỉnh dưới đây dùng Java 8 trở lên:

```java
import java.util.Arrays;
import java.util.List;

public class CompatibleReductionDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("Java", "Stream", "API");

        int sequential = words.stream().reduce(
            0,
            (sum, word) -> sum + word.length(),
            Integer::sum
        );

        int parallel = words.parallelStream().reduce(
            0,
            (sum, word) -> sum + word.length(),
            Integer::sum
        );

        System.out.println(sequential); // 13
        System.out.println(parallel);   // 13
    }
}
```

Với dữ liệu nhỏ này, `parallelStream()` có thể chậm hơn do chi phí chia và gộp việc. Mục đích của ví dụ là **tính đúng đắn**, không phải chứng minh tăng tốc. Các lambda đều không sửa trạng thái bên ngoài; phép gộp dùng cộng số nguyên, có identity `0` và tương thích với việc cộng độ dài từng chuỗi.

Nếu chỉ cần tổng độ dài, biểu thức sau thường ngắn gọn và rõ ràng hơn:

```java
int totalLength = words.stream()
    .mapToInt(String::length)
    .sum(); // 13
```

`reduce` ba tham số đặc biệt đáng học khi `T` và `U` khác nhau hoặc cách tích lũy khác cách gộp. Nó không bắt buộc là công cụ tốt nhất cho mọi phép tính tổng.

## 5. Lỗi khó thấy: combiner có tính kết hợp nhưng không tương thích

Giả sử người viết muốn cộng độ dài chuỗi nhưng chọn `Math.max` để gộp các kết quả từng phần:

```java
List<String> words = Arrays.asList("Java", "Stream", "API");

int wrong = words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Math::max                         // SAI: gộp bằng max, không phải cộng
);
```

`Math.max` có tính kết hợp và `0` là giá trị trung lập với `max` trên miền các độ dài **không âm**. Nhưng nó **không tương thích** với accumulator dùng phép cộng:

```text
u = 4, t = "Stream"

combiner(4, accumulator(0, "Stream"))
= max(4, 6)
= 6

accumulator(4, "Stream")
= 4 + 6
= 10
```

Hai vế không bằng nhau. Với một nhánh duy nhất, kết quả có thể vẫn là `13` vì chỉ cần accumulator. Nếu dữ liệu được chia thành các nhánh, combiner `max` chỉ giữ kết quả từng phần lớn nhất thay vì cộng chúng. **Đừng dự đoán một kết quả sai cố định**: mức độ và cách chia dữ liệu khi song song có thể thay đổi theo môi trường.

Sửa bằng phép gộp đúng:

```java
int correct = words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::sum
); // 13
```

Bài học: **associativity và identity không thay thế compatibility**. Cần kiểm tra cả ba điều kiện, đặc biệt khi `accumulator` và `combiner` khác nhau về kiểu tham số và mục đích.

## 6. Lỗi identity: cùng một giá trị bị cộng nhiều lần

Một lỗi khác là dùng số khởi đầu `5` trong khi phép gộp là cộng:

```java
int wrongIdentity = words.parallelStream().reduce(
    5,
    (sum, word) -> sum + word.length(),
    Integer::sum
);
```

`5` không phải giá trị trung lập với phép cộng. Nếu nguồn được xử lý trong một nhánh, kết quả tích lũy sẽ là `5 + 13 = 18`. Nếu chia thành hai nhánh và mỗi nhánh bắt đầu bằng `5`, việc gộp có thể tính **hai lần** số `5`, cho `23`. Cách phân nhánh cụ thể không được bảo đảm.

Điều kiện identity đã sai:

```text
combiner(identity, u) = 5 + u != u
```

Muốn có giá trị bù thêm `5` theo yêu cầu nghiệp vụ, hãy giữ identity đúng rồi cộng `5` **sau khi reduce hoàn tất**:

```java
int totalPlusFive = 5 + words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::sum
); // 18
```

Cách viết này làm rõ ý nghĩa: `5` là giá trị cộng thêm ở cuối, không phải identity dùng cho từng phép gộp.

## 7. Không dùng reduce ba tham số để sửa một container dùng chung

`reduce` được thiết kế cho **phép rút gọn không có trạng thái chia sẻ và không can thiệp**. Dùng một đối tượng mutable làm identity rồi thay đổi trực tiếp nó từ accumulator/combiner dễ vi phạm hợp đồng và gây race condition khi chạy song song.

Ví dụ **sai**, chỉ để nhận diện lỗi:

```java
List<String> unsafe = words.parallelStream().reduce(
    new ArrayList<String>(),
    (list, word) -> {
        list.add(word);      // SAI: thay đổi đối tượng kết quả từng phần
        return list;
    },
    (left, right) -> {
        left.addAll(right);  // SAI: mutate trong reduce
        return left;
    }
);
```

Vấn đề không chỉ là `ArrayList` thiếu đồng bộ. `identity` ở đây là **một tham chiếu đến một đối tượng thay đổi được**; thao tác trên đối tượng đó có thể ảnh hưởng nhiều nhánh xử lý. Ngay cả khi thay `ArrayList` bằng cấu trúc đồng bộ, việc sửa các đối tượng trong `reduce` vẫn không diễn đạt hợp đồng rút gọn thuần túy và có thể sinh dữ liệu trùng hoặc sai.

### Dùng collect khi mục tiêu là tích lũy có thể thay đổi

`collect` cung cấp mô hình riêng cho việc tạo kết quả mutable bằng supplier, accumulator và combiner:

```java
ArrayList<String> safe = words.parallelStream().collect(
    ArrayList::new,
    ArrayList::add,
    ArrayList::addAll
);

System.out.println(safe); // [Java, Stream, API]
```

Ba tham số của `collect` có vai trò:

| Thành phần của collect | Vai trò |
| --- | --- |
| `supplier` | Tạo **container mới** cho từng phần tích lũy |
| `accumulator` | Thêm một phần tử vào container của phần đang xử lý |
| `combiner` | Gộp dữ liệu từ container của nhánh khác vào container hiện tại |

Đây là **mutable reduction** được API hỗ trợ. Combiner của `collect` dạng này trả `void`, còn combiner của `reduce` ba tham số trả lại giá trị `U`. Với việc thu một danh sách đơn giản, cũng có thể viết:

```java
List<String> safeList = words.parallelStream()
    .collect(Collectors.toList());
```

Khi cần grouping hoặc collector tùy chỉnh, hãy ưu tiên `collect` và thiết kế theo hợp đồng Collector. Đây là bước tiếp theo tự nhiên trong lộ trình học JAVA_STREAM_API.

## 8. Khác biệt giữa ba overload của reduce

`reduce` có ba dạng thường gặp:

| Dạng | Ý nghĩa | Khi nào dùng? |
| --- | --- | --- |
| `Optional<T> reduce(BinaryOperator<T> accumulator)` | Không cần identity; kết quả rỗng khi nguồn rỗng | Tìm giá trị gộp không có phần tử trung lập hợp lý, ví dụ giá trị lớn nhất |
| `T reduce(T identity, BinaryOperator<T> accumulator)` | Kiểu kết quả giống kiểu phần tử; toán tử cũng dùng để gộp khi song song | Tính tổng, tích, hợp nhất các phần tử cùng kiểu |
| `U reduce(U identity, BiFunction<U,? super T,U> accumulator, BinaryOperator<U> combiner)` | Kiểu kết quả có thể khác kiểu phần tử; tách cách tích lũy và cách gộp | Tổng độ dài chuỗi, cấu trúc kết quả bất biến, phép biến đổi và rút gọn tùy biến |

Ví dụ:

```java
Optional<Integer> largest = Stream.of(7, 3, 9)
    .reduce(Integer::max); // Optional[9]

int sum = Stream.of(7, 3, 9)
    .reduce(0, Integer::sum); // 19

int lengthSum = Stream.of("Hi", "Java")
    .reduce(0, (length, text) -> length + text.length(), Integer::sum);
// 6
```

Với Stream rỗng:

```java
int zero = Stream.<Integer>empty()
    .reduce(0, Integer::sum); // 0

Optional<Integer> none = Stream.<Integer>empty()
    .reduce(Integer::sum); // Optional.empty()

int total = Stream.<String>empty()
    .reduce(0, (n, text) -> n + text.length(), Integer::sum); // 0
```

Không có phần tử để tích lũy thì hai dạng có identity trả về identity, còn dạng không có identity trả về `Optional.empty()`.

## 9. Trường hợp combiner không giao hoán nhưng vẫn hợp lệ

Không phải mọi bài toán rút gọn đều là cộng số. Có thể nối chuỗi bằng các phép toán **kết hợp nhưng không giao hoán**:

```java
String joined = Stream.of("A", "B", "C")
    .parallel()
    .reduce(
        "",
        (prefix, text) -> prefix + text,
        String::concat
    );

System.out.println(joined); // ABC
```

Ở đây:

- Identity `""` là phần tử trung lập cho nối chuỗi.
- `String::concat` có tính kết hợp theo giá trị chuỗi.
- `concat(u, concat("", t))` bằng `concat(u, t)`, nên tương thích với accumulator.
- Nguồn `Stream.of("A", "B", "C")` có encounter order; reduction hợp lệ giữ nghĩa nối theo thứ tự ấy dù có thể chia phần để thực hiện song song.

**Nối chuỗi liên tục bằng `+` có thể tạo nhiều đối tượng trung gian** và tốn chi phí lớn. Nếu mục tiêu là nối chuỗi thực tế, `Collectors.joining()` thường phù hợp hơn:

```java
String joinedEfficiently = Stream.of("A", "B", "C")
    .parallel()
    .collect(Collectors.joining()); // "ABC"
```

Đừng thay `String::concat` bằng một combiner đảo vị trí `(a, b) -> b + a`: nó sẽ vi phạm compatibility với accumulator nối vào cuối, dù đôi khi quan sát một kết quả tuần tự có vẻ hợp lý.

## 10. Số thực, tràn số và khả năng tái lập kết quả

Tính kết hợp trong hợp đồng reduce là yêu cầu **theo ngữ nghĩa của phép toán**. Với `double`, phép cộng dấu phẩy động chịu sai số làm tròn; trong số học máy, `(a + b) + c` có thể khác `a + (b + c)`:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Vì vậy, tổng số thực khi chạy tuần tự và song song có thể khác nhau ở các bit cuối. Với mục tiêu tính tổng kiểu `double`, `mapToDouble(...).sum()` thường rõ ràng hơn và có thể dùng kỹ thuật cải thiện độ chính xác, nhưng không hứa kết quả thập phân tuyệt đối hay bit giống nhau trong mọi cách chia nhánh.

Nếu ứng dụng yêu cầu chính xác thập phân cho tiền tệ, cân nhắc `BigDecimal` và quy tắc làm tròn cụ thể. Nếu cần tính toán số nguyên nhưng không chấp nhận tràn, có thể sử dụng `Math.addExact` để phát hiện lỗi; với `int`/`long`, phép cộng thông thường có thể tràn theo biểu diễn máy. Việc chọn kiểu dữ liệu đúng là một phần của tính đúng đắn khi reduce.

## 11. Bảng kiểm tra khi thiết kế reduce song song

| Câu hỏi cần kiểm tra | Cách thử hoặc bằng chứng |
| --- | --- |
| `identity` thực sự trung lập không? | Thử `combiner(identity, u) == u` trên nhiều `u` đại diện |
| `combiner` kết hợp được không? | So sánh kết quả của `combine(combine(a,b),c)` và `combine(a,combine(b,c))` |
| `accumulator` và `combiner` tương thích không? | Kiểm tra `combine(u, accumulate(identity,t)) == accumulate(u,t)` |
| Hàm có sửa nguồn hoặc trạng thái chia sẻ không? | Loại bỏ mutation ngoài pipeline; tránh identity mutable bị tái sử dụng |
| Kết quả có phụ thuộc thứ tự không? | Kiểm tra encounter order; không tự ý dùng `unordered()` |
| Cần cấu trúc mutable hay giá trị bất biến? | Mutable: ưu tiên `collect`; giá trị rút gọn: cân nhắc `reduce` |
| Có nguy cơ tràn số hoặc sai số dấu phẩy động không? | Chọn kiểu dữ liệu và tiêu chí kiểm tra phù hợp |
| Đã thử nhiều cách chia dữ liệu chưa? | So sánh kết quả logic của `stream()` và `parallelStream()`, gồm nguồn rỗng và nguồn một phần tử |

Khi kiểm tra kết quả, đừng chỉ chạy một lần trên danh sách ba phần tử: môi trường có thể chọn cách thực thi khiến `combiner` ít hoặc không được gọi. Trước hết hãy **chứng minh ba quan hệ trong hợp đồng**, sau đó mới dùng kiểm thử nhiều đầu vào để phát hiện lỗi triển khai.

## 12. Bài tập tự kiểm tra

**Bài 1 — Xác định compatibility.** Cho:

```java
int value = words.parallelStream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::max
);
```

**Đáp án:** Sai về hợp đồng. Với `u = 4`, `t = "Stream"`, vế `max(4, 6)` bằng `6`, trong khi `4 + 6` bằng `10`. `max` có tính kết hợp nhưng không tương thích với accumulator cộng độ dài.

**Bài 2 — Tìm identity đúng.** Hãy điền identity và combiner để tính tích các số nguyên dương:

```java
int product = Stream.of(2, 3, 4).parallel().reduce(
    1,
    (acc, n) -> acc * n,
    (left, right) -> left * right
); // 24
```

**Đáp án:** Identity là `1` và combiner là phép nhân. `1` trung lập với nhân; nhân có tính kết hợp theo số học nguyên không tràn và tương thích với accumulator. Với `int`, cần xét tràn số nếu miền giá trị lớn.

**Bài 3 — Chọn reduce hay collect.** Muốn lấy toàn bộ chuỗi của một Stream vào `ArrayList`, nên dùng reduce với identity `new ArrayList<>()` rồi `add`, hay `collect`?

```java
ArrayList<String> result = words.parallelStream()
    .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

**Đáp án:** Dùng `collect`; API cung cấp container riêng cho việc tích lũy mutable và cơ chế kết hợp thích hợp. Mutable identity trong reduce có thể làm nhiều nhánh chia sẻ một đối tượng.

**Bài 4 — Có cần giao hoán không?** `String::concat` có phải combiner hợp lệ cho accumulator nối chuỗi vào cuối trên Stream có encounter order?

**Đáp án:** Có, khi identity là `""` và accumulator nối vào cuối. Phép nối có tính kết hợp và tương thích, mặc dù không giao hoán. Nếu bỏ yêu cầu thứ tự, kết quả ghép chuỗi có thể không còn đáp ứng ý định ban đầu.

**Bài 5 — Stream rỗng.** Kết quả của phép reduce ba tham số sau là gì?

```java
int result = Stream.<String>empty().reduce(
    0,
    (sum, s) -> sum + s.length(),
    Integer::sum
); // 0
```

**Đáp án:** `0`. Không có phần tử nào để đưa vào accumulator, nên identity là kết quả.

## Ghi nhớ

Khi dùng `reduce(identity, accumulator, combiner)` trong **JAVA_STREAM_API**, hãy xem `accumulator` là cách đưa **một phần tử T** vào kết quả **U**, còn `combiner` là cách gộp **hai kết quả U**. Bộ ba phải thỏa **identity trung lập, combiner kết hợp được và compatibility giữa accumulator/combiner**. Một hàm kết hợp đúng riêng lẻ vẫn có thể là combiner sai nếu nó không tái tạo đúng ý nghĩa của accumulator. Để tích lũy vào container mutable, dùng `collect`; khi chạy song song, tránh trạng thái chia sẻ và chú ý thứ tự, độ chính xác số học, chi phí gộp dữ liệu. Đó là nền tảng để viết phép rút gọn đúng và có thể mở rộng từ tuần tự sang song song.
