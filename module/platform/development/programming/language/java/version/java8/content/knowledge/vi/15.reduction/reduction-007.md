# Reduction: Tính đúng khi chia nguồn theo nhiều cách (Java 8+)

## 1. Vấn đề: cùng dữ liệu, nhiều cách chia, có phải cùng kết quả?

Khi sử dụng **Stream.reduce(...)**, đặc biệt với **parallelStream()**, Java có thể tách nguồn dữ liệu thành nhiều phần, tính kết quả cục bộ cho từng phần rồi kết hợp các kết quả đó. Số phần, điểm cắt và cách nhóm khi kết hợp là chi tiết thực thi: người lập trình không được giả định chúng cố định.

Với dữ liệu có thứ tự **[1, 2, 3, 4]** và phép cộng, ta muốn thu được **10** trong tất cả các trường hợp sau:

| Cách xử lý | Kết quả các phần | Kết hợp cuối |
| --- | --- | --- |
| Không chia | 1 + 2 + 3 + 4 | 10 |
| [1, 2] / [3, 4] | 3 và 7 | 3 + 7 = 10 |
| [1] / [2, 3] / [4] | 1, 5 và 4 | 1 + 5 + 4 = 10 |
| [] / [1, 2, 3, 4] | 0 và 10 | 0 + 10 = 10 |
| [1, 2, 3, 4] / [] | 10 và 0 | 10 + 0 = 10 |

Trong bảng, các phần giữ **encounter order** (thứ tự phần tử mà nguồn Stream định nghĩa). Phép cộng hoạt động vì có tính **kết hợp** và có phần tử trung hòa **0**.

Câu hỏi cốt lõi của bài: **Làm sao thiết kế reduction sao cho việc chia nguồn theo nhiều cách và nhóm các kết quả trung gian không làm sai kết quả mong muốn?**

Đây là yêu cầu hiện hành của Java Stream, được mô tả trong hợp đồng API từ Java 8 và vẫn có hiệu lực trong Java hiện đại. Không cần phụ thuộc chi tiết thuật toán chia việc của một phiên bản JDK cụ thể.

## 2. Mô hình tính từng phần và kết hợp

Giả sử nguồn có thứ tự **D** được chia thành các đoạn liên tiếp **A**, **B**, **C**. Gọi:

- **R(P)**: kết quả rút gọn (*reduction*) của đoạn **P**.
- **e**: phần tử trung hòa (*identity*) dùng cho đoạn rỗng và khởi tạo từng phép rút gọn cục bộ.
- **⊗**: phép kết hợp hai kết quả cục bộ (*combiner*).
- **A ++ B**: ghép hai đoạn theo thứ tự A trước, B sau.

Điều ta cần là:

~~~text
R([]) = e

R(A ++ B) = R(A) ⊗ R(B)

R(A ++ B ++ C)
    = (R(A) ⊗ R(B)) ⊗ R(C)
    = R(A) ⊗ (R(B) ⊗ R(C))
~~~

Nghĩa là bất kể chia một nguồn thành bao nhiêu đoạn, kể cả có đoạn rỗng, sau khi kết hợp hợp lệ, kết quả phải tương đương với xử lý liên tục trên cả nguồn.

Tính đúng ở đây **không có nghĩa** Java phải gọi lambda theo cùng thứ tự, dùng cùng số luồng hay tạo cùng số đoạn. Nó có nghĩa **kết quả quan sát được phải tuân thủ hợp đồng reduction** trong những điều kiện API đặt ra.

Một cách hiểu thực hành: để được quyền chia và nhóm lại, phép gộp phải có khả năng **đổi dấu ngoặc** mà không đổi ý nghĩa. Đó là tính kết hợp (*associativity*). Đồng thời, đoạn rỗng phải không làm thay đổi kết quả. Đó là vai trò của identity.

## 3. Ba dạng Stream.reduce cần phân biệt

~~~java
// 1. Có identity, đầu vào và kết quả cùng kiểu T
T reduce(T identity, BinaryOperator<T> accumulator);

// 2. Không có identity, kết quả có thể rỗng
Optional<T> reduce(BinaryOperator<T> accumulator);

// 3. Đầu vào T, kết quả có thể là kiểu U khác
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

Các chữ ký trên là cách biểu diễn API để học; hãy xem tài liệu JDK chính thức để tra đầy đủ chi tiết generic.

| Dạng | Khi nào dùng | Điều kiện liên quan đến việc chia |
| --- | --- | --- |
| reduce(identity, accumulator) | Một phép gộp thuần nhất, ví dụ tổng, tích hoặc nối chuỗi | Identity trung hòa; accumulator kết hợp |
| reduce(accumulator) | Có thể không có phần tử, ví dụ tìm min/max | Accumulator kết hợp; nguồn rỗng trả Optional.empty() |
| reduce(identity, accumulator, combiner) | Đầu vào và kết quả khác kiểu; ví dụ String thành tổng độ dài Integer | Combiner kết hợp, identity trung hòa, accumulator tương thích với combiner |

**reduce** là phép toán kết thúc (*terminal operation*): sau khi gọi, Stream đó đã được tiêu thụ và không được tái sử dụng. Với **reduce** thuần và đúng hợp đồng, việc chuyển từ **stream()** sang **parallelStream()** không được làm sai ý nghĩa kết quả.

Lưu ý: dạng **reduce(identity, accumulator)** không nhận combiner riêng; trong quá trình thực hiện song song, chính phép gộp **accumulator** phải có khả năng kết hợp các kết quả một cách hợp lệ.

## 4. Điều kiện thứ nhất: phép kết hợp phải có tính kết hợp

Một phép toán **⊕** có tính kết hợp khi:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

Sự khác biệt nằm ở **cách đặt dấu ngoặc**, không phải đổi chỗ các phần tử.

Ví dụ phép cộng số nguyên:

~~~text
(1 + 2) + 3 = 6
1 + (2 + 3) = 6
~~~

Ví dụ phép trừ:

~~~text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
~~~

**Phép trừ không kết hợp**, nên không phù hợp làm phép reduction dự kiến hoạt động đúng với mọi cách chia/nhóm. Với Java:

~~~java
// Phản ví dụ: không dùng phép trừ làm accumulator của
// một reduction cần kết quả độc lập với cách nhóm.
int unreliable = java.util.stream.Stream.of(10, 5, 2)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

Ngoài tính không kết hợp, **0** còn không là identity hai phía của phép trừ vì **0 - a** khác **a**. Một lần chạy tuần tự cho giá trị có vẻ hợp lý không chứng minh đoạn code đúng khi được chia để xử lý song song.

Các ví dụ hay gặp:

| Phép gộp | Có tính kết hợp? | Identity phù hợp | Ghi chú |
| --- | --- | --- | --- |
| Cộng số nguyên | Có (theo số học của kiểu số đã chọn) | 0 | Cẩn thận overflow nếu muốn tổng toán học chính xác |
| Nhân số nguyên | Có (theo số học của kiểu số đã chọn) | 1 | Cẩn thận overflow nếu yêu cầu kết quả không tràn |
| Min / Max | Có trên miền dữ liệu và quan hệ so sánh nhất quán | Tùy miền, hoặc dùng Optional | Không bịa identity nếu không có giá trị trung hòa hợp lệ |
| Nối chuỗi | Có | Chuỗi rỗng "" | Kết hợp nhưng không giao hoán |
| Trừ / Chia | Không | Không có identity thích hợp cho yêu cầu này | Thay bằng mô hình tổng hợp khác |
| Trung bình trực tiếp giữa hai số | Nói chung không | Không có identity phù hợp | Tích lũy tổng và số lượng rồi mới chia |

Ví dụ phép "lấy trung bình từng cặp" cho kết quả phụ thuộc cách nhóm:

~~~text
(1 ⋄ 3) ⋄ 5 = ((1 + 3)/2 + 5)/2 = 3.5
1 ⋄ (3 ⋄ 5) = (1 + (3 + 5)/2)/2 = 2,5

Trong đó a ⋄ b = (a + b) / 2.
~~~

Vì vậy không tính average bằng **reduce** với hàm lấy trung bình hai giá trị trung gian. Với dữ liệu số, dùng **IntStream.average()**, **DoubleStream.average()**, hoặc một kết quả gồm **sum/count** với combiner hợp lệ.

## 5. Điều kiện thứ hai: identity phải trung hòa trong mọi phân đoạn

Với phép gộp **⊕**, phần tử **e** trung hòa hai phía khi:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

Ví dụ:

- Tổng số nguyên: **e = 0** vì **0 + x = x + 0 = x**.
- Tích: **e = 1** vì **1 × x = x × 1 = x**.
- Nối chuỗi: **e = ""** vì **"" + s = s + "" = s**.

API **Stream.reduce(identity, BinaryOperator)** yêu cầu identity đối với accumulator; với phép gộp đúng được sử dụng trong nhiều cách chia, hai phía trung hòa là cách kiểm tra an toàn và rõ ràng.

Hãy xem ví dụ sai:

~~~java
// SAI: 10 không phải identity của phép cộng.
int wrong = java.util.stream.Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(10, Integer::sum);
~~~

Không thể giả định **10** được cộng đúng một lần. Nếu tính tuần tự, chương trình có thể cho **20 = 10 + (1 + 2 + 3 + 4)**. Nếu nguồn được chia thành hai đoạn **[1, 2]** và **[3, 4]**, mỗi đoạn có thể bắt đầu từ identity 10:

~~~text
Đoạn 1: 10 + 1 + 2 = 13
Đoạn 2: 10 + 3 + 4 = 17
Kết hợp: 13 + 17 = 30  (khác 20)
~~~

Đây là ví dụ minh họa cách chia, không phải dự đoán JVM luôn chia thành đúng hai đoạn hay luôn cho ra 30.

**Đặc biệt:** identity không phải "giá trị cộng thêm một lần ở đầu cả bài toán". Khi xử lý song song, nó có thể được dùng để khởi tạo **từng reduction cục bộ**. Nếu mục tiêu nghiệp vụ là **10 + tổng dữ liệu**, hãy reduction với identity thật sự là **0**, rồi cộng 10 **một lần sau khi reduction hoàn tất**:

~~~java
int total = java.util.stream.Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, Integer::sum);

int withOffset = 10 + total; // 20
~~~

Đoạn rỗng rất hữu ích khi tự kiểm chứng: với nguồn không có phần tử, **reduce(0, Integer::sum)** trả **0**, còn **reduce(1, phép nhân)** trả **1**. Với dạng không identity, **Stream.empty().reduce(...)** trả **Optional.empty()**.

## 6. Điều kiện thứ ba: accumulator phải tương thích với combiner

Dạng reduction ba tham số đặc biệt quan trọng khi **kiểu phần tử nguồn T khác kiểu kết quả U**:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

- **identity**: kết quả mặc định của đoạn rỗng, đồng thời là giá trị khởi tạo các kết quả cục bộ.
- **accumulator(U, T)**: thêm một phần tử kiểu T vào kết quả cục bộ kiểu U.
- **combiner(U, U)**: kết hợp hai kết quả cục bộ kiểu U sau khi chia nguồn.

Ngoài điều kiện combiner kết hợp và identity trung hòa, chúng phải thỏa quan hệ tương thích sau, với mọi kết quả cục bộ **u** và phần tử **t**:

~~~text
combiner(u, accumulator(identity, t))
    = accumulator(u, t)
~~~

Ý nghĩa: "gộp u với kết quả của một đoạn chỉ chứa t" phải tương đương với "thêm trực tiếp t vào u". Nếu không đúng, chia một phần tử thành đoạn riêng có thể làm thay đổi kết quả.

### Ví dụ đúng: tính tổng độ dài từ Stream<String>

~~~java
java.util.List<String> words =
        java.util.Arrays.asList("ab", "c", "def", "a");

int length = words.parallelStream().reduce(
        0,
        (sum, word) -> sum + word.length(),
        Integer::sum
); // 7
~~~

Tại đây:

~~~text
T = String; U = Integer
identity = 0
accumulator(u, t) = u + t.length()
combiner(u, v) = u + v

combiner(u, accumulator(0, t))
    = u + (0 + t.length())
    = u + t.length()
    = accumulator(u, t)
~~~

Đúng cho mọi String không null trong nguồn, vì phép cộng số nguyên có tính kết hợp và identity phù hợp. Chia nguồn thành **["ab", "c"]** và **["def", "a"]** cho kết quả trung gian **3** và **4**, gộp lại được **7**. Chia thành **["ab"]**, **["c", "def"]**, **["a"]** cho **2 + 4 + 1 = 7**.

Có thể viết tương đương, dễ đọc hơn khi mục đích chỉ là ánh xạ rồi tính tổng:

~~~java
int length = words.parallelStream()
        .mapToInt(String::length)
        .sum(); // 7
~~~

**Chọn mapToInt(...).sum() khi phù hợp** vì nó nêu trực tiếp ý định và dùng primitive stream; không phải bài toán nào cũng cần viết thủ công reduction ba tham số.

### Ví dụ sai: combiner làm mất dữ liệu

~~~java
int wrong = words.parallelStream().reduce(
        0,
        (sum, word) -> sum + word.length(),
        (left, right) -> left  // SAI: bỏ hẳn kết quả đoạn right
);
~~~

Với đoạn bên trái có độ dài 3 và bên phải có độ dài 4, combiner trả **3** thay vì **7**. Khi chạy tuần tự, combiner có thể không được gọi và biểu hiện lỗi sẽ bị che khuất. Không có bảo đảm một lần chạy parallel bất kỳ sẽ cho ra giá trị cụ thể nào khi ta vi phạm hợp đồng reduction.

### Ví dụ sai: combiner cũng phải cùng quy tắc tổng hợp

Giả sử accumulator vẫn cộng độ dài, nhưng combiner dùng **Math.max**:

~~~java
int wrong = words.parallelStream().reduce(
        0,
        (sum, word) -> sum + word.length(),
        Math::max
);
~~~

Phép **max** riêng nó có tính kết hợp, nhưng **không tương thích** với accumulator cộng độ dài. Với **u = 2** và phần tử có độ dài 3:

~~~text
combiner(2, accumulator(0, t)) = max(2, 3) = 3
accumulator(2, t)              = 2 + 3 = 5
~~~

**Kết luận:** combiner kết hợp chưa đủ. Với reduction ba tham số, phải có **cả** identity đúng, combiner kết hợp, accumulator tương thích và các lambda thuần/không can thiệp nguồn.

## 7. Ví dụ chạy được: kiểm tra tất cả 15 cách chia thành ba đoạn

Tạo tệp **ReductionPartitionDemo.java**. Ví dụ dùng các API có từ Java 8 và chạy được trên JDK 17+ hiện hành. Hàm **sum** dùng phép cộng với identity 0; vòng lặp tự chia dữ liệu theo mọi cặp vị trí cắt **first <= second**. Do cho phép hai vị trí trùng nhau và các điểm cắt ở đầu/cuối, ta còn kiểm tra được **đoạn rỗng**.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

public class ReductionPartitionDemo {
    static int sum(List<Integer> data) {
        return data.stream().reduce(0, Integer::sum);
    }

    static int wordLength(List<String> data) {
        return data.stream().reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        );
    }

    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(1, 2, 3, 4);

        System.out.println("sum sequential: " + sum(values));
        System.out.println("sum parallel: "
                + values.parallelStream().reduce(0, Integer::sum));

        int checked = 0;
        for (int first = 0; first <= values.size(); first++) {
            for (int second = first; second <= values.size(); second++) {
                int a = sum(values.subList(0, first));
                int b = sum(values.subList(first, second));
                int c = sum(values.subList(second, values.size()));

                if (Integer.sum(Integer.sum(a, b), c) != sum(values)) {
                    throw new AssertionError(
                            "Mismatch at " + first + ", " + second);
                }
                checked++;
            }
        }
        System.out.println("three-way splits checked: " + checked);

        List<String> words = Arrays.asList("ab", "c", "def", "a");

        System.out.println("length sequential: " + wordLength(words));
        System.out.println("length parallel: "
                + words.parallelStream().reduce(
                        0,
                        (total, word) -> total + word.length(),
                        Integer::sum
                ));

        System.out.println("concat ordered: "
                + Stream.of("A", "B", "C")
                        .parallel()
                        .reduce("", String::concat));

        System.out.println("subtraction groups: "
                + ((10 - 5) - 2) + " vs " + (10 - (5 - 2)));

        System.out.println("empty sum: "
                + Stream.<Integer>empty().reduce(0, Integer::sum));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReductionPartitionDemo.java
java ReductionPartitionDemo
~~~

**Stdout chính xác:**

~~~text
sum sequential: 10
sum parallel: 10
three-way splits checked: 15
length sequential: 7
length parallel: 7
concat ordered: ABC
subtraction groups: 3 vs 7
empty sum: 0
~~~

Giải thích phần kiểm tra:

1. Với bốn phần tử, có **15** cặp vị trí cắt thỏa mãn **0 <= first <= second <= 4**. Ví dụ bao gồm ba đoạn không rỗng, một đoạn rỗng và hai đoạn rỗng.
2. **subList** giữ nguyên thứ tự các phần tử trong từng đoạn. Việc gộp **a + b + c** theo đúng thứ tự đoạn chứng minh bất biến chia nguồn cho ví dụ cộng.
3. Giá trị **parallel = 10** là phép kiểm tra thực thi; vòng lặp 15 cách chia là kiểm tra có kiểm soát, không dựa vào lịch chia việc của ForkJoinPool hoặc JDK.
4. Ví dụ **concat ordered** cho kết quả **ABC** vì nguồn **Stream.of** có encounter order và **String::concat** kết hợp. Điều này không nói rằng các lambda đã chạy theo thứ tự A, B, C.
5. Ví dụ phép trừ cho hai giá trị khác nhau chỉ vì thay đổi dấu ngoặc; đó là lý do không dùng phép trừ làm reduction tùy ý nhóm.

Một bài toán thực tế có thể có hàng triệu phần tử, nên kiểm tra một tập nhỏ không phải là chứng minh toán học toàn cục. Hãy kết hợp bài test với việc chứng minh các quy luật identity, associativity và compatibility cho toàn miền dữ liệu hợp lệ.

## 8. Giữ thứ tự khác với giao hoán

Hai khái niệm thường bị nhầm:

- **Kết hợp (associative)**: có thể thay dấu ngoặc, ví dụ **(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)**.
- **Giao hoán (commutative)**: có thể đổi chỗ hai phần tử, ví dụ **a ⊕ b = b ⊕ a**.

Phép nối chuỗi kết hợp nhưng **không** giao hoán:

~~~text
("A" + "B") + "C" = "ABC"
"A" + ("B" + "C") = "ABC"

"A" + "B" = "AB"
"B" + "A" = "BA"
~~~

Với **Stream có encounter order** và một reduction hợp lệ, có thể chia nguồn/đổi nhóm mà vẫn phải bảo toàn thứ tự có ý nghĩa. Không cần phép gộp giao hoán để xử lý nguồn ordered.

Ngược lại, với Stream **unordered**, hoặc sau khi chủ động dùng **unordered()**, không được suy diễn có thứ tự ổn định nếu hợp đồng nguồn không bảo đảm. Khi thứ tự có thể thay đổi, phép nối chuỗi có thể tạo ra kết quả khác nhau. Nếu bài toán yêu cầu cùng kết quả bất kể hoán vị phần tử, cần thêm tính giao hoán hoặc thiết kế một cơ chế gom nhóm/sắp xếp phù hợp.

~~~java
// Có encounter order: kết quả nội dung vẫn là "ABC".
String ordered = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", String::concat);

// Không có yêu cầu giữ encounter order ở pipeline này.
// Đừng dựa vào một thứ tự nối chuỗi ngẫu nhiên khi chạy thử.
String orderNotGuaranteed = Stream.of("A", "B", "C")
        .unordered()
        .parallel()
        .reduce("", String::concat);
~~~

**ordered** không có nghĩa mọi bước đều được xử lý theo thứ tự hoặc trên một thread. Nó ràng buộc kết quả quan sát được của các thao tác có yêu cầu thứ tự. Nếu cần một thứ tự cụ thể, hãy chọn một nguồn ordered hoặc thiết lập thứ tự bằng **sorted(...)** với comparator phù hợp, có cân nhắc chi phí xử lý.

## 9. Các lỗi làm reduction sai khi thay đổi cách chia

### 9.1. Dùng một phép không kết hợp

~~~java
// SAI: phép trừ không kết hợp và identity cũng không phù hợp.
int result = java.util.stream.Stream.of(10, 5, 2)
        .parallel()
        .reduce(0, (left, right) -> left - right);
~~~

Cách xử lý đúng phụ thuộc mục đích. Nếu muốn lấy tổng rồi đổi dấu, hãy tổng hợp bằng phép cộng hợp lệ và đổi dấu **sau** reduction. Nếu phép toán thực sự phụ thuộc trình tự từng bước, đừng giả vờ nó là phép giảm có thể chia tùy ý.

### 9.2. Identity không trung hòa

~~~java
// SAI: 10 được dùng làm seed của mỗi đoạn, có thể bị tính nhiều lần.
int result = java.util.stream.IntStream.of(1, 2, 3, 4)
        .boxed()
        .parallel()
        .reduce(10, Integer::sum);
~~~

Sửa bằng **reduce(0, Integer::sum)** rồi cộng offset sau khi có kết quả cuối.

### 9.3. Accumulator và combiner không đồng nhất về ý nghĩa

~~~java
// SAI: tính tổng độ dài ở từng đoạn nhưng chỉ lấy max khi ghép đoạn.
int result = java.util.stream.Stream.of("aa", "bbb")
        .parallel()
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Math::max
        );
~~~

Cần xác định kết quả đang đại diện cho gì (tổng, max, số đếm, tập hợp, thống kê...), rồi thiết kế **cả accumulator lẫn combiner** theo cùng đại lượng đó.

### 9.4. Dùng trạng thái chia sẻ hoặc thay đổi nguồn

~~~java
// SAI: không xây reduction bằng side effect lên biến dùng chung.
int[] total = {0};
java.util.stream.IntStream.rangeClosed(1, 4)
        .parallel()
        .forEach(n -> total[0] += n); // Data race, không bảo đảm đúng
~~~

**reduce** đúng cách:

~~~java
int total = java.util.stream.IntStream.rangeClosed(1, 4)
        .parallel()
        .sum(); // 10
~~~

Biến chia sẻ được khóa hoặc dùng AtomicInteger cũng không tự động biến một phép gộp không kết hợp thành hợp lệ. Việc thêm đồng bộ có thể làm giảm lợi ích song song; tốt hơn là thiết kế phép tổng hợp từ dữ liệu đầu vào, với hàm không can thiệp nguồn (**non-interfering**) và không phụ thuộc trạng thái thay đổi (**stateless**).

Không thay đổi **ArrayList**, **HashMap** hoặc nguồn không hỗ trợ concurrent modification trong lúc đang chạy pipeline. Phải kiểm soát nguồn dữ liệu và quy tắc đồng thời trước khi đưa vào reduction.

### 9.5. Dùng đối tượng mutable làm identity của reduce

Ví dụ sau là **phản ví dụ**, không sử dụng trong ứng dụng:

~~~java
java.util.List<String> shared = new java.util.ArrayList<>();

java.util.List<String> wrong = java.util.stream.Stream.of("a", "b")
        .parallel()
        .reduce(
                shared,
                (acc, word) -> {
                    acc.add(word); // SAI: mutate identity dùng chung
                    return acc;
                },
                (left, right) -> {
                    left.addAll(right); // Có thể ghép trùng chính cùng object
                    return left;
                }
        );
~~~

Các nhánh reduction có thể nhận **cùng tham chiếu identity**, gây race, ghi trùng hoặc kết quả khó dự đoán. Đây là vi phạm mô hình immutable/functional reduction. Hãy dùng **collect**, vốn cấp container riêng cho từng phần và có cơ chế kết hợp phù hợp:

~~~java
java.util.List<String> list =
        java.util.stream.Stream.of("a", "b")
                .parallel()
                .collect(java.util.stream.Collectors.toCollection(
                        java.util.ArrayList::new));
~~~

Khi kết quả là danh sách, bản đồ, StringBuilder hay đối tượng tổng hợp mutable, **collect(...)** hoặc một **Collector** phù hợp thường là công cụ đúng. Nếu cần nối chuỗi với dấu phân cách, dùng **Collectors.joining(",")** thay vì một reduce tự chế dễ sai identity hoặc tạo quá nhiều chuỗi trung gian.

### 9.6. Kiểu số và giới hạn chính xác

Phép cộng **double** không kết hợp tuyệt đối theo số học dấu phẩy động IEEE 754:

~~~text
(1e16 + (-1e16)) + 1 = 1.0
1e16 + ((-1e16) + 1) = 0.0
~~~

Do làm tròn, thay đổi nhóm có thể tạo khác biệt ở các chữ số cuối hoặc thậm chí rõ rệt trong ví dụ cực đoan. Đây là vấn đề khi yêu cầu **bitwise identical**, mặc dù phép cộng số thực về toán học có tính kết hợp.

- Với tiền hoặc số thập phân cần độ chính xác cố định, cân nhắc **BigDecimal** với cách khởi tạo từ chuỗi và phép cộng chính xác; tránh đặt quy tắc làm tròn từng bước tùy ý nếu muốn giữ kết quả độc lập với nhóm.
- Nếu chấp nhận sai số dấu phẩy động, dùng cách đánh giá dựa trên sai số phù hợp bài toán thay vì luôn so **==** bitwise giữa các lịch thực thi.
- Số nguyên **int/long** có thể tràn nếu vượt phạm vi. Dù phép cộng nguyên theo quy tắc tràn của Java có tính kết hợp, tổng bị tràn có thể sai so với tổng toán học mà nghiệp vụ mong đợi. Có thể dùng **long**, **BigInteger** hoặc kiểm tra giới hạn theo yêu cầu.
- Khi dùng **Math.addExact** để báo tràn, xử lý ngoại lệ và thứ tự gộp có thể ảnh hưởng việc phát hiện tràn ở kết quả cục bộ; cần đặc tả bài toán chính xác.

**Tính đúng với mọi cách chia không thay thế yêu cầu đúng về miền số và độ chính xác.**

### 9.7. Việc kiểm thử tuần tự không làm hợp đồng trở nên tùy chọn

Một combiner sai có thể không được thực thi khi chạy **stream()**. Chương trình có thể vượt qua nhiều test tuần tự nhưng vẫn sai khi chuyển sang **parallelStream()** hoặc chạy trên nguồn lớn. Tính kết hợp/identity/compatibility phải được chứng minh độc lập với lịch thực thi.

## 10. Chia nguồn, xử lý song song và chi phí thực tế

**parallelStream()** cho runtime cơ hội xử lý các đoạn dữ liệu đồng thời. Java có thể dựa vào khả năng chia nguồn (**Spliterator**) và đặc tính pipeline để quyết định chiến lược thực thi. Bạn không nên phụ thuộc số đoạn, kích thước đoạn, thread thực thi hay thứ tự gọi accumulator/combiner trong chương trình ứng dụng.

Tính đúng và hiệu suất là hai câu hỏi riêng:

- **Đúng:** Các hàm thuần, không can thiệp nguồn; identity/combiner/accumulator đáp ứng hợp đồng; encounter order được tôn trọng khi có yêu cầu.
- **Nhanh:** Phụ thuộc kích thước dữ liệu, chi phí thao tác trên từng phần tử, chi phí phân chia/gộp và hạ tầng thực thi; với dữ liệu nhỏ, song song có thể chậm hơn.
- **Dễ hiểu:** Các terminal operation có mục đích rõ như **sum()**, **count()**, **min()**, **max()**, **average()** hoặc **Collectors.joining(...)** thường nên được chọn thay vì tự viết reduction tương đương.
- **Có thứ tự:** Nếu không cần encounter order, chỉ dùng **unordered()** khi điều đó thực sự phù hợp với ý nghĩa kết quả; không bỏ bảo đảm thứ tự chỉ để hy vọng nhanh hơn.

Một thuật toán sai về reduction không trở thành đúng chỉ vì **parallel()** chạy nhanh; ngược lại, một reduction đúng không tự động đáng sử dụng song song ở mọi kích thước bài toán.

## 11. Quy trình tự kiểm tra một reduction mới

Khi thiết kế reduction để chia nguồn, hãy kiểm tra lần lượt:

**Bước 1 — Xác định kết quả mong muốn.** Kết quả là tổng, max, giá trị nối theo thứ tự, thống kê có sum/count hay một cấu trúc có thể cập nhật? Ghi rõ kiểu phần tử **T**, kiểu kết quả **U** và yêu cầu order.

**Bước 2 — Xác định identity và đoạn rỗng.** Nếu không có phần tử, kết quả hợp lý là gì? Thử **combine(identity, u)** và **combine(u, identity)**. Nếu không tìm được identity hợp lệ, cân nhắc dạng trả **Optional** hoặc thuật toán khác.

**Bước 3 — Chứng minh combiner kết hợp.** Với ít nhất ba kết quả cục bộ **a, b, c**, kiểm tra hai cách đặt dấu ngoặc. Thử cả biên như 0, số âm, chuỗi rỗng và các giới hạn kiểu số.

**Bước 4 — Kiểm tra compatibility của reduce ba tham số.** Với nhiều giá trị đại diện **u** và phần tử **t**, kiểm tra **combine(u, accumulate(identity, t)) = accumulate(u, t)**. Đây là điều kiện giúp kết quả không thay đổi khi t được chuyển sang một đoạn riêng.

**Bước 5 — Loại bỏ trạng thái chia sẻ.** Accumulator và combiner không làm thay đổi nguồn, không dùng đồng hồ/thứ tự thread/random state làm cơ sở kết quả, không mutate identity dùng chung.

**Bước 6 — Test nhiều cách chia có kiểm soát.** So sánh reduction trực tiếp với kết quả của:
- Một đoạn duy nhất.
- Hai hoặc ba đoạn liên tiếp với tất cả vị trí cắt hợp lệ.
- Đoạn rỗng và đoạn một phần tử.
- Nhiều cách nhóm combiner, ví dụ **(a ⊗ b) ⊗ c** và **a ⊗ (b ⊗ c)**.
- **stream()** và **parallelStream()** ở nhiều kích thước dữ liệu.

**Bước 7 — Kiểm tra thứ tự và miền số.** Nếu yêu cầu giữ encounter order, test trên nguồn ordered. Nếu cần kết quả không phụ thuộc hoán vị, đánh giá thêm tính giao hoán hoặc thuật toán khác. Nếu tổng có thể tràn hay số thực bị làm tròn, xác định giới hạn chấp nhận được.

Bộ test là bằng chứng thực thi cần thiết, nhưng **không thay thế** lập luận về hợp đồng. Kết quả đúng trong một lần chạy song song không chứng minh mọi cách chia đều đúng.

## 12. Luyện tập có lời giải

### Bài 1 — Identity và tính kết hợp

Với **Stream.of(2, 3, 4)**, chọn identity và phép gộp để tính tích dù nguồn bị chia:

~~~java
int product = java.util.stream.Stream.of(2, 3, 4)
        .parallel()
        .reduce(1, (a, b) -> a * b); // 24
~~~

**Giải thích:** phép nhân số nguyên có tính kết hợp theo quy tắc số học kiểu int, **1** trung hòa hai phía. Với dữ liệu lớn, vẫn phải đánh giá nguy cơ tràn số theo bài toán.

### Bài 2 — Phát hiện lỗi do identity sai

Tại sao không nên viết:

~~~java
int total = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(5, Integer::sum);
~~~

**Lời giải:** 5 không là identity của phép cộng. Kết quả có thể phụ thuộc số phân đoạn vì giá trị seed được dùng nhiều lần. Nếu yêu cầu là **5 + 1 + 2 + 3**, hãy dùng **reduce(0, Integer::sum)** trước, rồi cộng 5 vào kết quả cuối.

### Bài 3 — Kiểm tra compatibility

Cho **T = String**, **U = Integer**, **identity = 0**, **accumulator(u, t) = u + t.length()**, và **combiner(u, v) = u * v**. Có đúng không?

**Lời giải:** Không. **identity = 0** cũng không trung hòa phép nhân, và **u * (0 + len) != u + len** nói chung. Cần combiner là phép cộng **Integer::sum** để khớp ý nghĩa tổng độ dài.

### Bài 4 — Nối chuỗi có dấu phẩy

Vì sao không dùng **reduce("", (a, b) -> a + "," + b)** để nối các từ?

**Lời giải:** Chuỗi rỗng **""** không trung hòa phép đó: **"" + "," + "a" = ",a"**. Khi các đoạn được xử lý riêng, dấu phẩy đầu đoạn/đoạn rỗng càng làm kết quả sai. Dùng:

~~~java
String joined = java.util.stream.Stream.of("a", "b", "c")
        .parallel()
        .collect(java.util.stream.Collectors.joining(","));
// "a,b,c"
~~~

### Bài 5 — Khi nào cần giao hoán?

Nếu muốn kết quả **"abc"** từ các từ **"a", "b", "c"**, nhưng nguồn là unordered, chỉ có tính kết hợp của **String::concat** đã đủ để bảo đảm đúng thứ tự chưa?

**Lời giải:** Chưa. Nối chuỗi không giao hoán, nên khi thứ tự không được bảo đảm, kết quả chuỗi cũng không được bảo đảm. Nếu yêu cầu một thứ tự cụ thể, cần định nghĩa order, ví dụ dùng **sorted()** trước khi ghép, hoặc dùng một nguồn có encounter order ổn định.

## 13. Ghi nhớ

1. **Đúng khi chia nguồn** nghĩa là kết quả không thay đổi khi tách các phần tử thành các đoạn và kết hợp các kết quả cục bộ hợp lệ, với thứ tự đầu vào được bảo toàn nếu pipeline ordered.
2. **Associativity** cho phép đổi cách nhóm; **identity** bảo đảm đoạn rỗng không ảnh hưởng kết quả. Identity có thể được dùng ở nhiều đoạn, không nhất thiết chỉ một lần.
3. Với **reduce(identity, accumulator, combiner)**, phải thêm điều kiện **combiner(u, accumulator(identity, t)) = accumulator(u, t)**. Combiner kết hợp nhưng không tương thích vẫn làm sai kết quả.
4. **Kết hợp khác giao hoán**: phép nối chuỗi có thể xử lý theo các cách nhóm khác nhau, nhưng không được đổi thứ tự phần tử khi kết quả có yêu cầu thứ tự.
5. Tránh phép trừ, average theo từng cặp, identity sai, combiner bỏ dữ liệu, mutable identity và side effect trong reduction.
6. Test tuần tự và song song, nhiều vị trí cắt, đoạn rỗng và miền số; xác minh bằng lý luận theo hợp đồng API, không phụ thuộc số thread hay lịch chia của JDK.

### Tài liệu chính thức đang áp dụng

- **Stream.reduce** và điều kiện identity/associativity/compatibility (Java SE 25): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- **java.util.stream package summary** — reduction, parallelism, encounter order, stateless/non-interfering operations và mutable reduction (Java SE 25): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- **Collectors** và các terminal operation cho kết quả mutable: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
