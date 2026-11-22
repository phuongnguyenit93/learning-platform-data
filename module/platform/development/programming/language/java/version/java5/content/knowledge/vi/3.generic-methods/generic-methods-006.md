# Giới hạn trên bằng extends cho tham số kiểu

## 1. Từ “một kiểu bất kỳ” đến “một kiểu có khả năng cần thiết”

Một phương thức generic không giới hạn như `<T> T echo(T value)` có thể nhận nhiều kiểu tham chiếu. Tuy nhiên, bên trong phương thức, trình biên dịch chỉ biết những khả năng mà khai báo `T` bảo đảm. Nếu chưa có giới hạn riêng, giới hạn trên mặc định là `Object`; phương thức không được tự gọi một thao tác chỉ có ở số hoặc chuỗi.

Giả sử cần cộng các giá trị số theo biểu diễn `double`. Mỗi giá trị phải cung cấp được phương thức `doubleValue()`. Có thể diễn đạt yêu cầu ấy bằng:

```java
static <N extends Number> double sumAsDouble(List<N> values) {
    double sum = 0.0;
    for (N value : values) {
        sum += value.doubleValue();
    }
    return sum;
}
```

Đây là đoạn phương thức minh họa, cần `import java.util.List;` và một lớp bao ngoài. Chương trình đầy đủ có kiểm tra `null` nằm ở mục 5.

`<N extends Number>` khai báo một **tham số kiểu có giới hạn trên** (upper bounded type parameter). Đối số kiểu được chọn cho `N` phải là `Number` hoặc một kiểu con của `Number`. Nhờ giới hạn đó, thân phương thức được phép gọi các phương thức phù hợp của `Number`, như `doubleValue()`.

Giới hạn trên đồng thời phục vụ hai phía: người gọi không được chọn một kiểu không đáp ứng yêu cầu, còn người viết phương thức có một hợp đồng rõ ràng về những thao tác được phép dùng.

Cú pháp này vẫn dùng trong Java hiện hành. Các ví dụ chạy bằng JDK 17 trở lên.

## 2. Đọc chính xác ý nghĩa của `extends`

| Khai báo | Ý nghĩa của giới hạn | Ví dụ đối số kiểu phù hợp |
| --- | --- | --- |
| `<T>` | Mặc định có giới hạn trên `Object` | `String`, `Integer`, `StringBuilder` |
| `<N extends Number>` | `N` là `Number` hoặc kiểu con của nó | `Number`, `Integer`, `Double` |
| `<S extends CharSequence>` | `S` đáp ứng interface `CharSequence` | `CharSequence`, `String`, `StringBuilder` |

`extends` ở đây bao hàm quan hệ kiểu con nói chung, không chỉ trường hợp một lớp dùng từ khóa `extends` để kế thừa lớp khác. Khi giới hạn là interface, vẫn dùng `extends` trong danh sách tham số kiểu:

```java
static <S extends CharSequence> S longer(S left, S right) {
    return left.length() >= right.length() ? left : right;
}
```

Không viết `<S implements CharSequence>`. `String` và `StringBuilder` đều đáp ứng `CharSequence`, nên có thể chọn chúng làm `S`.

“Giới hạn trên” cũng không có nghĩa chỉ chấp nhận các lớp con **khác** giới hạn. Chọn chính `Number` hoặc chính `CharSequence` cũng hợp lệ. Ví dụ một biến `List<Number>` có thể được truyền vào `sumAsDouble`; nó có thể chứa nhiều kiểu con của `Number` theo hợp đồng danh sách đó.

Giới hạn không yêu cầu giới hạn phải tạo đối tượng được. `Number` là lớp trừu tượng và `CharSequence` là interface, nhưng chúng vẫn có thể làm giới hạn hoặc làm đối số kiểu của những khai báo phù hợp. Generic không tự gọi hàm tạo của chúng.

Quy tắc về biến kiểu và giới hạn được mô tả tại [JLS §4.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4).

## 3. Giới hạn cho phép thao tác nào trong thân phương thức?

### 3.1. Chỉ dùng những khả năng được khai báo bảo đảm

Trong `<N extends Number>`, một biến `N` có thể được dùng với `intValue()`, `longValue()` hoặc `doubleValue()` theo hợp đồng và quyền truy cập của các phương thức đó. Không thể gọi một phương thức chỉ có ở một lớp con cụ thể như thể mọi `N` đều thuộc lớp đó.

Trong `<S extends CharSequence>`, có thể gọi `length()` hoặc `charAt(...)`. Không thể gọi `append(...)` chỉ vì một nơi sử dụng truyền vào `StringBuilder`: một nơi khác có thể chọn `String`, mà `String` không cung cấp thao tác nối sửa đổi như `StringBuilder`.

Thân phương thức generic được kiểm tra theo khai báo của nó, không được viết riêng lại cho từng kiểu được truyền vào. Nếu thuật toán cần thêm một khả năng, hãy thể hiện khả năng đó trong giới hạn hoặc trong đối số hành vi riêng.

### 3.2. `Number` không tạo ra phép cộng tổng quát cho `N`

Đoạn sau cố ý không biên dịch:

```java
static <N extends Number> N add(N left, N right) {
    return left + right; // Lỗi: không có phép + tổng quát trên N
}
```

`N extends Number` không làm `N` trở thành một kiểu số nguyên thủy cố định, và `Number` không định nghĩa một phương thức cộng trả về cùng `N`. Vì vậy Java không thể suy ra phải dùng phép cộng của `Integer`, `Double` hay một kiểu số khác.

`sumAsDouble` chọn chiến lược rõ ràng: đổi mỗi giá trị sang `double`, rồi cộng các giá trị nguyên thủy đó và trả `double`. Kết quả không được hứa là `N`, và không giữ nguyên mọi đặc tính số học của kiểu đầu vào.

Theo hợp đồng của [Number](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Number.html), việc đổi sang kiểu nguyên thủy có thể mất độ chính xác hoặc thông tin. Vì vậy ví dụ phù hợp để học khả năng mà giới hạn cung cấp; khi cần số học chính xác cho tiền hoặc số nguyên rất lớn, cần chọn mô hình và thuật toán số học riêng.

### 3.3. Giới hạn không tạo được `new N()`

Một tham số kiểu có giới hạn trên vẫn không cung cấp một hàm tạo cụ thể để gọi. Không thể dùng `new N()` để tạo phần tử chỉ vì `N extends Number`. Nếu thuật toán cần tạo giá trị mới, có thể thiết kế nhận một hàm cung cấp dữ liệu hoặc một phép toán phù hợp; đó là yêu cầu bổ sung ngoài quan hệ kiểu con.

## 4. Giữ quan hệ kiểu giữa đầu vào và kết quả

Xét lại phương thức:

```java
static <S extends CharSequence> S longer(S left, S right) {
    return left.length() >= right.length() ? left : right;
}
```

Nó có hai đặc điểm: giới hạn `CharSequence` cho phép đo độ dài; việc dùng cùng `S` cho đầu vào và đầu ra giữ quan hệ giữa kiểu được chọn ở nơi gọi với kiểu kết quả.

```java
String name = longer("An", "Binh");
StringBuilder builder = longer(
        new StringBuilder("abc"), new StringBuilder("x"));
```

Lần gọi đầu có thể chọn `S = String`; kết quả gán thẳng cho `String`. Lần gọi thứ hai có thể chọn `S = StringBuilder`; kết quả gán thẳng cho `StringBuilder`. Phương thức trả lại một trong hai tham chiếu đầu vào, không sao chép đối tượng hoặc chuyển `StringBuilder` thành `String`.

Nếu chỉ khai báo phương thức nhận và trả `CharSequence`, mã vẫn có thể so độ dài nhưng người gọi chỉ được bảo đảm kết quả là `CharSequence`. Generic có giá trị ở đây vì nó diễn đạt thêm quan hệ kiểu, không chỉ vì có cú pháp `<...>`.

### Không bắt buộc mọi đối số có cùng lớp lúc chạy

Có thể viết:

```java
CharSequence text = longer("A", new StringBuilder("BC"));
```

`S` có thể được chọn là một kiểu chung phù hợp với hai đối số và kiểu đích, chẳng hạn `CharSequence`. Giới hạn không yêu cầu hai đối tượng có cùng `getClass()`. Nhưng người gọi không thể vì thế hứa kết quả luôn là `String` khi một trong hai giá trị có thể là `StringBuilder`.

Kiểu được suy luận phải đáp ứng đồng thời giới hạn, các đối số và ngữ cảnh đích. Nếu các điều kiện không thể thỏa mãn, trình biên dịch từ chối lời gọi.

Trong ví dụ này, `length()` được hiểu theo hợp đồng [CharSequence](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/CharSequence.html); với văn bản Unicode, không nên mặc định số đơn vị `char` luôn bằng số ký tự người đọc nhìn thấy.

## 5. Chương trình chạy đầy đủ

Lưu vào `UpperBoundsDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class UpperBoundsDemo {
    static <N extends Number> double sumAsDouble(List<N> values) {
        Objects.requireNonNull(values, "values");
        double sum = 0.0;
        for (N value : values) {
            sum += Objects.requireNonNull(value, "element").doubleValue();
        }
        return sum;
    }

    static <S extends CharSequence> S longer(S left, S right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        return left.length() >= right.length() ? left : right;
    }

    public static void main(String[] args) {
        List<Integer> counts = List.of(1, 2, 3);
        List<Double> measurements = List.of(1.5, 2.0);
        List<Number> mixedNumbers = List.of(1, 2.5);

        System.out.println("counts=" + sumAsDouble(counts));
        System.out.println("measurements=" + sumAsDouble(measurements));
        System.out.println("mixed numbers=" + sumAsDouble(mixedNumbers));

        String name = longer("An", "Binh");
        StringBuilder builder = longer(
                new StringBuilder("abc"), new StringBuilder("x"));
        CharSequence mixedText = longer("A", new StringBuilder("BC"));

        System.out.println("name=" + name);
        System.out.println("builder=" + builder);
        System.out.println("mixed text=" + mixedText);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror UpperBoundsDemo.java
java UpperBoundsDemo
```

Stdout:

```text
counts=6.0
measurements=3.5
mixed numbers=3.5
name=Binh
builder=abc
mixed text=BC
```

`counts` dùng `N = Integer`; `measurements` dùng `N = Double`; `mixedNumbers` dùng `N = Number`. Cả ba đều đáp ứng giới hạn, dù kiểu phần tử không giống nhau giữa các lần gọi.

`longer` có thể giữ kiểu `String`, giữ kiểu `StringBuilder`, hoặc trả về theo hợp đồng chung `CharSequence`. Quy tắc hòa trong ví dụ là chọn đối số bên trái khi hai độ dài bằng nhau.

`Objects.requireNonNull` là kiểm tra giá trị lúc chạy được viết riêng: một giới hạn trên không tự bảo đảm đối số hoặc phần tử khác `null`. Nếu bỏ các kiểm tra này, lời gọi phương thức trên `null` vẫn có thể ném `NullPointerException`.

## 6. Lỗi biên dịch cần nhận ra

### 6.1. Kiểu đầu vào không thỏa mãn giới hạn

Có thể thêm các dòng sau vào `main` để thử từng lỗi; bỏ dấu chú thích từng dòng rồi biên dịch lại:

```java
// double invalid = sumAsDouble(List.of("1", "2"));
// StringBuilder invalidText = longer("A", new StringBuilder("BC"));
// double forced = UpperBoundsDemo.<String>sumAsDouble(List.of("1"));
```

Dòng thứ nhất không tìm được đối số kiểu vừa phù hợp với chuỗi vừa thỏa mãn `Number`. Dòng thứ hai yêu cầu kết quả là `StringBuilder` nhưng đối số đầu là `String`; không thể thỏa mãn đồng thời hợp đồng đó. Dòng thứ ba ghi rõ `String` làm đối số kiểu, trực tiếp vi phạm giới hạn `N extends Number`.

Thêm đối số kiểu tường minh không bỏ qua giới hạn; nó chỉ làm lựa chọn kiểu rõ hơn để trình biên dịch kiểm tra.

### 6.2. Nhầm kiểu nguyên thủy với đối số kiểu

Không dùng `int` làm đối số kiểu, chẳng hạn không viết `<int>`. `Integer` là kiểu tham chiếu phù hợp với giới hạn `Number`; các số nguyên trong `List.of(1, 2, 3)` được đóng hộp vào đối tượng thích hợp.

Việc đóng hộp không khiến một chuỗi `"3"` trở thành `Integer`. Chuyển đổi nội dung chuỗi thành số là một thao tác dữ liệu riêng, có thể thất bại theo định dạng.

### 6.3. Không dùng `super` để khai báo giới hạn dưới cho biến kiểu

Danh sách tham số kiểu không chấp nhận cú pháp `<T super Number>`. Đừng nhầm nó với wildcard `? super Number` trong một kiểu sử dụng. Tham số kiểu có tên và wildcard là hai công cụ khác nhau, có vị trí cú pháp và vai trò khác nhau.

### 6.4. Giới hạn không loại bỏ tính bất biến

`List<Integer>` không tự trở thành `List<Number>`. `sumAsDouble(List<N>)` nhận được `List<Integer>` bằng cách chọn `N = Integer`, không phải bằng phép đổi `List<Integer>` thành `List<Number>`.

Vì vậy cần đọc cả danh sách tham số kiểu và kiểu của đối số phương thức. Chỉ nhìn thấy từ `Number` ở một nơi không đủ để suy ra mọi phép gán giữa các danh sách số đều hợp lệ.

## 7. Khi nào nên dùng tham số có giới hạn?

Dùng tham số kiểu có giới hạn khi cần vừa yêu cầu một khả năng chung, vừa giữ một quan hệ kiểu có tên trong chữ ký: giữa nhiều đối số, giữa đối số và kết quả, hoặc giữa các thành phần dữ liệu của thuật toán.

Nếu một phương thức chỉ nhận một `CharSequence` và trả về số độ dài, nhận `CharSequence` trực tiếp có thể đã đủ. Nếu một phương thức chỉ đọc các `Number` trong danh sách và trả `double`, chữ ký `List<? extends Number>` cũng là lựa chọn có thể phù hợp khi không cần dùng tên `N` ở nơi khác. Ví dụ `sumAsDouble` trong bài chủ yếu làm rõ tác dụng của giới hạn trên trong thân phương thức.

Giới hạn cũng có thể tham chiếu một biến kiểu khác đã khai báo, như `<T, U extends T>`, hoặc kết hợp những khả năng bằng `&`. Với một giới hạn chứa nhiều thành phần như `<T extends Base & Capability>`, nếu có lớp thì lớp phải đứng đầu; các thành phần thêm sau là interface. Chỉ thêm ràng buộc mà thuật toán thực sự cần, vì ràng buộc thừa sẽ loại người gọi không cần thiết.

Cùng nguyên tắc giới hạn trên có thể áp dụng cho tham số kiểu của lớp hoặc hàm tạo generic. Trong bài này, trọng tâm là hợp đồng của phương thức: kiểu nào được phép truyền vào, thao tác nào được gọi, và kiểu kết quả liên hệ với đầu vào ra sao.

## 8. Tự kiểm tra

1. Trong `<N extends Number>`, có được chọn chính `Number` làm `N` không?
2. Vì sao `<S extends CharSequence>` dùng `extends` dù `CharSequence` là interface?
3. Vì sao có thể gọi `doubleValue()` trên `N` nhưng không thể viết một phép cộng tổng quát trả về `N`?
4. Phương thức `<S extends CharSequence> S longer(S a, S b)` có bắt buộc hai đối tượng cùng lớp lúc chạy không?
5. Giới hạn trên có tự ngăn giá trị `null` không?

Đáp án:

1. Có. Kiểu giới hạn và các kiểu con phù hợp đều được chấp nhận.
2. Vì `extends` trong giới hạn tham số kiểu diễn đạt quan hệ kiểu con, gồm cả việc đáp ứng interface.
3. `Number` bảo đảm phương thức chuyển đổi, nhưng không định nghĩa phép `+` tổng quát cho mọi kiểu con hay cách tạo kết quả đúng cùng `N`.
4. Không. Một kiểu chung thỏa mãn giới hạn có thể được chọn nếu phù hợp toàn bộ lời gọi; kiểu kết quả lúc đó cũng phải được dùng theo hợp đồng đã chọn.
5. Không. Cần kiểm tra hoặc chính sách `null` riêng theo yêu cầu API.

Hãy chọn giới hạn dựa trên khả năng thuật toán cần dùng, rồi xem tên tham số kiểu có giữ được quan hệ hữu ích nào cho người gọi không. Đây là cơ sở để viết phương thức generic vừa đủ chặt mà vẫn dễ sử dụng.
