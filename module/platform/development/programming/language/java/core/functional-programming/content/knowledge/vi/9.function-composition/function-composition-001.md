# Function.compose() và Function.andThen() trong Java

## 1. Tư duy kết hợp hàm: đầu ra của hàm trước là đầu vào của hàm sau

Trong lập trình hàm, **kết hợp hàm** (*function composition*) cho phép ghép các phép biến đổi nhỏ thành một phép biến đổi lớn hơn. Thay vì gọi nhiều hàm lồng nhau, Java cung cấp hai phương thức mặc định của `java.util.function.Function<T,R>`:

- `andThen(after)`: thực hiện **hàm hiện tại trước**, rồi thực hiện `after`.
- `compose(before)`: thực hiện **hàm `before` trước**, rồi thực hiện hàm hiện tại.

Ví dụ, đặt `f(x) = x + 3` và `g(x) = 2 * x`. Với đầu vào `5`:

```text
f.andThen(g): 5 -> f -> 8 -> g -> 16
f.compose(g): 5 -> g -> 10 -> f -> 13
```

Hai kết quả **khác nhau**. Nếu chỉ ghi nhớ một điểm, đó là: **thứ tự viết các hàm trong mã không luôn đồng nghĩa với thứ tự thực thi**. `compose` gọi đối số trước, trong khi `andThen` gọi đối tượng nhận phương thức trước.

Trong Java, `Function<T,R>` là functional interface có phương thức trừu tượng `R apply(T value)`. Lambda, tham chiếu phương thức và một đối tượng triển khai `Function` đều có thể được kết hợp theo cách này. Kết quả của phép kết hợp cũng là một `Function`, có thể lưu, truyền tiếp hoặc gọi `apply`.

## 2. Chữ ký API và quy tắc kiểu dữ liệu

Phương thức chính của `Function<T,R>`:

```java
R apply(T value);
```

Hai phương thức kết hợp (chữ ký khái niệm đúng theo generic API Java):

```java
default <V> Function<T, V> andThen(
        Function<? super R, ? extends V> after);

default <V> Function<V, R> compose(
        Function<? super V, ? extends T> before);
```

Đây là **chữ ký trích dẫn để đọc kiểu**, không phải một lớp độc lập để sao chép biên dịch; phần triển khai đã tồn tại trong thư viện chuẩn.

Giả sử `f` có kiểu `Function<T,R>`:

| Lời gọi | Hàm được truyền vào | Hàm kết quả | Thứ tự xử lý |
| --- | --- | --- | --- |
| `f.andThen(g)` | `g: R → V` hoặc kiểu vào rộng hơn, đầu ra phù hợp `V` | `Function<T,V>` | `g(f(x))` |
| `f.compose(g)` | `g: V → T` hoặc kiểu vào rộng hơn, đầu ra phù hợp `T` | `Function<V,R>` | `f(g(x))` |

Dạng wildcard `? super` cho kiểu đầu vào và `? extends` cho kiểu đầu ra giúp API chấp nhận các hàm tương thích theo quan hệ kiểu cha/con. Đây là lý do không nên phát biểu rằng hai kiểu phải giống nhau đến từng tham số generic.

Khi giải bài tập, hãy viết chuỗi kiểu như sau:

```text
String --trim--> String --parse--> Integer --label--> String
```

Mỗi mũi tên tiếp theo chỉ hợp lệ khi **kiểu kết quả hàm trước phù hợp kiểu tham số hàm sau**. Java kiểm tra điều này tại thời điểm biên dịch, không chờ `apply`.

## 3. andThen(): đọc xuôi từ trái sang phải

Giả sử hai hàm:

```java
Function<Integer, Integer> addThree = x -> x + 3;
Function<Integer, Integer> doubleIt = x -> x * 2;
```

Hai lệnh này nằm trong phương thức có `import java.util.function.Function;`. Khi viết:

```java
Function<Integer, Integer> result = addThree.andThen(doubleIt);
System.out.println(result.apply(5)); // 16
```

Thực thi theo thứ tự:

1. `addThree.apply(5)` cho `8`.
2. `doubleIt.apply(8)` cho `16`.
3. `result.apply(5)` trả `16`.

Vì thế `addThree.andThen(doubleIt)` tương đương về phép biến đổi với `x -> doubleIt.apply(addThree.apply(x))`, khi bỏ qua khác biệt về đối tượng hàm và cách xử lý lỗi không liên quan.

Từ khóa `then` trong `andThen` gợi ý “**làm việc hiện tại, sau đó làm việc kế tiếp**”. Điều này đặc biệt thuận tiện với các bước tiền xử lý/kiểm tra/chuyển đổi/định dạng nối liên tiếp.

## 4. compose(): đọc hàm tham số trước

Vẫn dùng hai hàm trên:

```java
Function<Integer, Integer> result = addThree.compose(doubleIt);
System.out.println(result.apply(5)); // 13
```

Thực thi:

1. `doubleIt.apply(5)` cho `10`.
2. `addThree.apply(10)` cho `13`.
3. `result.apply(5)` trả `13`.

`addThree.compose(doubleIt)` tương đương với `x -> addThree.apply(doubleIt.apply(x))`.

Điểm dễ nhầm: cách đọc phương thức thông thường `addThree.compose(...)` khiến người mới tưởng `addThree` chạy trước vì đứng bên trái dấu chấm. Nhưng trong `compose`, **hàm được truyền vào `before` mới chạy trước**.

Với hai hàm `f` và `g` có kiểu tương thích:

```text
f.andThen(g)  = g ∘ f
f.compose(g)  = f ∘ g
f.andThen(g)  = g.compose(f)
```

Dấu `∘` là ký hiệu hợp thành trong toán học. Đẳng thức ở đây mô tả kết quả áp dụng cùng đầu vào với các hàm thuần; trong ứng dụng có tác dụng phụ, cần xem xét cả **thứ tự tác dụng phụ**, không chỉ giá trị cuối.

## 5. Ví dụ Java 17 hoàn chỉnh và đầu ra chính xác

Lưu nội dung sau thành tệp `FunctionCompositionDemo.java`:

```java
import java.util.function.Function;

public class FunctionCompositionDemo {
    public static void main(String[] args) {
        Function<Integer, Integer> addThree = x -> x + 3;
        Function<Integer, Integer> doubleIt = x -> x * 2;

        System.out.println(addThree.andThen(doubleIt).apply(5));
        System.out.println(addThree.compose(doubleIt).apply(5));

        Function<String, String> trim = String::trim;
        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, String> label = n -> "value=" + n;
        Function<String, String> pipeline = trim.andThen(parse).andThen(label);
        System.out.println(pipeline.apply(" 21 "));

        Function<String, Integer> afterParse = addThree.compose(parse);
        Function<String, Integer> afterParseAlternative = parse.andThen(addThree);
        System.out.println(afterParse.apply("21"));
        System.out.println(afterParseAlternative.apply("21"));

        Function<CharSequence, String> asString = CharSequence::toString;
        Function<String, Integer> length = String::length;
        Function<CharSequence, Integer> lengthOfText = length.compose(asString);
        System.out.println(lengthOfText.apply(new StringBuilder("abc")));

        Function<Integer, Integer> identity = Function.identity();
        System.out.println(identity.andThen(addThree).apply(5));

        StringBuilder trace = new StringBuilder();
        Function<Integer, Integer> f = x -> {
            trace.append("f ");
            return x + 1;
        };
        Function<Integer, Integer> g = x -> {
            trace.append("g ");
            return x * 3;
        };
        Function<Integer, Integer> firstF = f.andThen(g);
        System.out.println("before=" + trace);
        System.out.println(firstF.apply(2));
        System.out.println("order=" + trace);
        trace.setLength(0);
        System.out.println(f.compose(g).apply(2));
        System.out.println("order=" + trace);

        Function<Number, Double> scale = n -> n.doubleValue() * 1.5;
        Function<String, Double> parseAndScale = scale.compose(Integer::valueOf);
        System.out.println(parseAndScale.apply("4"));

        Function<Integer, Number> widen = n -> n;
        Function<Integer, String> wideThenLabel = widen.andThen(n -> "n=" + n);
        System.out.println(wideThenLabel.apply(7));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 FunctionCompositionDemo.java
java FunctionCompositionDemo
```

Đầu ra:

```text
16
13
value=21
24
24
3
8
before=
9
order=f g 
7
order=g f 
6.0
n=7
```

**Lưu ý:** trong hai dòng `order=f g ` và `order=g f ` có một dấu cách ở cuối do chương trình dùng `trace.append("f ")`/`trace.append("g ")`. Đây là kết quả được kiểm thử thực tế với `javac --release 17`, không phải giả định.

Các phần chính của chương trình:

- `addThree.andThen(doubleIt)` trả `16`; `addThree.compose(doubleIt)` trả `13`.
- `trim.andThen(parse).andThen(label)` chuyển chuỗi có khoảng trắng thành chuỗi nhãn `value=21`.
- `addThree.compose(parse)` và `parse.andThen(addThree)` cho cùng kết quả `24`: cách viết khác nhưng thứ tự thực thi **đều là parse trước, cộng sau**.
- `length.compose(asString)` thể hiện việc ghép hàm có nhiều loại dữ liệu, nhận `CharSequence` rồi trả `Integer`.
- `Function.identity()` giữ nguyên giá trị đầu vào, nên nối tiếp `addThree` trên đầu vào `5` trả `8`.
- Hai hàm có ghi log `f` và `g` cho thấy **lúc tạo hàm kết hợp chưa chạy phần thân**, còn khi gọi `apply`, thứ tự được xác nhận bởi `StringBuilder`.
- Các phần `scale.compose(Integer::valueOf)` và `widen.andThen(...)` cho thấy việc dùng kiểu cha/con và wildcard trong chữ ký API.

Ví dụ này được viết để chạy độc lập bằng Java 17+, không cần thư viện ngoài.

## 6. Chuỗi xử lý thực tế: trim → parse → label

Một quy trình nhỏ thường gồm ba bước:

```java
Function<String, String> trim = String::trim;
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = n -> "value=" + n;

Function<String, String> pipeline =
        trim.andThen(parse).andThen(label);
```

Các khai báo đặt trong một phương thức đã import `Function`.

Phân tích kiểu:

| Giai đoạn | Kiểu đầu vào | Kiểu đầu ra |
| --- | --- | --- |
| `trim` | `String` | `String` |
| `parse` | `String` | `Integer` (từ `int` được boxing) |
| `label` | `Integer` | `String` |
| `pipeline` | `String` | `String` |

Lời gọi `pipeline.apply(" 21 ")` lần lượt tạo `"21"`, `21`, `"value=21"`.

Đọc chuỗi `andThen` như một pipeline **trái → phải**, thuận tiện khi một đầu vào phải qua nhiều bước.

Viết tương đương bằng `compose`:

```java
Function<String, String> samePipeline =
        label.compose(parse).compose(trim);
```

Lúc thực thi, `trim` vẫn chạy đầu tiên, rồi `parse`, rồi `label`. Cú pháp `compose` nhìn **phải → trái** theo thứ tự thực thi. Cả hai biểu thức tạo hàm nhận `String`, trả `String`.

Không nên hiểu `compose` là phép *đảo ngược* kết quả của một hàm. Nó **đảo thứ tự hai phép biến đổi trong cách ghép**, không tính hàm nghịch đảo.

## 7. Ghép những Function có kiểu khác nhau

Điểm mạnh của composition không nằm ở ví dụ `int → int`, mà ở khả năng chuyển qua nhiều kiểu:

```java
Function<CharSequence, String> asString = CharSequence::toString;
Function<String, Integer> length = String::length;
Function<CharSequence, Integer> lengthOfText =
        length.compose(asString);
```

Đây là ba lệnh minh họa trong một phương thức đã import `Function`. `lengthOfText.apply(new StringBuilder("abc"))` trả `3`: `StringBuilder` triển khai `CharSequence`, `asString` biến nó thành `String`, và `length` trả `int` (boxing thành `Integer`).

Thay vì nói “ghép hai hàm được nếu cùng kiểu”, hãy kiểm tra **điểm nối**:

```text
asString: CharSequence -> String
length:   String       -> Integer

asString.andThen(length): CharSequence -> Integer
length.compose(asString): CharSequence -> Integer
```

Điểm nối là `String`, còn kiểu đầu vào cuối và kiểu đầu ra cuối **không cần giống nhau**.

Nếu ghép theo hướng ngược lại mà đầu vào/đầu ra không tương thích, `javac` sẽ từ chối. Việc ép kiểu thô `(Function)` để “lách” kiểm tra thường chỉ dời lỗi sang lúc chạy và làm mất an toàn kiểu.

## 8. Wildcard và generic: vì sao dùng ? super và ? extends?

Chữ ký `andThen` có `Function<? super R, ? extends V>`. Điều này mang hai ý nghĩa:

1. `? super R` cho phép hàm sau nhận **`R` hoặc một kiểu cha của `R`**. Nếu hàm trước trả `Integer`, hàm sau có thể xử lý `Number` hay `Object`.
2. `? extends V` cho phép hàm sau tạo **`V` hoặc một kiểu con của `V`**. Ví dụ có thể xử lý một hàm trả `Double` trong ngữ cảnh mong đợi `Number`.

Tương tự, `compose` nhận `Function<? super V, ? extends T>`: hàm trước phải tạo ra giá trị tương thích với **đầu vào `T`** của hàm hiện tại.

Ví dụ:

```java
Function<Number, Double> scale = n -> n.doubleValue() * 1.5;
Function<String, Double> parseAndScale =
        scale.compose(Integer::valueOf);
```

`Integer::valueOf` tạo `Integer` từ chuỗi, và `Integer` là con của `Number`; vì thế có thể truyền cho hàm `scale` nhận `Number`. `parseAndScale.apply("4")` cho `6.0`.

Một ví dụ với kiểu kết quả tổng quát:

```java
Function<Integer, Number> widen = n -> n;
Function<Integer, String> wideThenLabel =
        widen.andThen(number -> "n=" + number);
```

Mặc dù hàm `widen` trả kiểu khai báo là `Number`, lambda `number -> ...` vẫn nhận được kiểu đích phù hợp. Đọc chữ ký generic của từng phương thức thay vì cho rằng tất cả phải là `Function<Integer,Integer>`.

**Lưu ý về `Integer` và `int`:** `Function<T,R>` dùng kiểu tham chiếu. Phép biến đổi số nguyên có thể xảy ra boxing/unboxing; nếu dùng trong đường nóng và chỉ xử lý kiểu nguyên thủy, hãy cân nhắc giao diện chuyên biệt (`IntUnaryOperator`, `IntFunction`, `ToIntFunction`) nhưng không mặc định rằng chúng có đủ **cả hai** phương thức `compose` và `andThen` như `Function`.

## 9. Function.identity() và đơn vị của phép ghép

`Function.identity()` trả về một `Function<T,T>` có hành vi `x -> x`:

```java
Function<Integer, Integer> identity = Function.identity();
Function<Integer, Integer> addThree = x -> x + 3;

System.out.println(identity.andThen(addThree).apply(5)); // 8
System.out.println(addThree.compose(identity).apply(5)); // 8
```

Các lệnh nằm trong một phương thức đã import `Function`. Identity giữ nguyên giá trị, vì vậy đối với hàm thuần và kiểu tương thích:

```text
identity.andThen(f) = f
f.andThen(identity) = f
identity.compose(f) = f
f.compose(identity) = f
```

Các đẳng thức ở đây là **tương đương về giá trị khi áp dụng** chứ không khẳng định đối tượng Java tạo ra bởi `andThen`/`compose` có cùng danh tính (`==`) với `f`.

Tính chất này giúp xây chuỗi xử lý tăng dần. Có thể bắt đầu từ identity rồi nối các phép biến đổi phù hợp, miễn là bạn chọn đúng các kiểu generic và xử lý null/exception theo nhu cầu.

## 10. Thời điểm thực thi, tác dụng phụ và thứ tự gọi

Khi viết `Function<Integer,Integer> h = f.andThen(g);`, Java tạo ra một hàm kết hợp. **Phần thân `f` và `g` không tự được gọi khi chỉ tạo `h`**. Chúng được gọi khi `h.apply(x)` chạy. Hành vi này quan trọng nếu lambda ghi log, cập nhật trạng thái hoặc truy cập hệ thống bên ngoài.

Trong chương trình đầy đủ, với:

```java
StringBuilder trace = new StringBuilder();
Function<Integer,Integer> f = x -> {
    trace.append("f ");
    return x + 1;
};
Function<Integer,Integer> g = x -> {
    trace.append("g ");
    return x * 3;
};
```

Đoạn mã thuộc thân phương thức và đã import `Function`. Sau khi tạo `f.andThen(g)`, `trace` vẫn rỗng. Gọi `apply(2)` cho `9`, log thứ tự `f g `. Đổi sang `f.compose(g).apply(2)` cho `7`, log `g f `.

Vì thứ tự **thực sự thay đổi**, hai phép ghép không mặc định giao hoán (*commutative*). Chúng chỉ có cùng kết quả trong những tình huống đặc biệt.

Cũng cần phân biệt `Function.andThen` với `Stream.map`: một `Function` kết hợp có thể được truyền cho stream, nhưng stream có tính **lazy** đối với thao tác trung gian. `stream.map(composed)` không làm việc ngay; một terminal operation thích hợp sẽ kích hoạt việc xử lý theo cơ chế của Stream.

Với dữ liệu nghiệp vụ, nên ưu tiên hàm thuần (*pure functions*): không ghi đè trạng thái dùng chung, không dựa vào thời điểm gọi, trả kết quả nhất quán cho cùng đầu vào. Điều này giúp tái sử dụng và kiểm thử chuỗi biến đổi dễ hơn. Nếu có side effects, thứ tự phải được xét rõ.

## 11. Xử lý lỗi, null và exception

Hai phương thức kết hợp **không tự bắt exception** phát sinh trong `apply`. Ví dụ:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<String, Integer> plusOne = parse.andThen(n -> n + 1);
```

Đây là các lệnh minh họa đặt trong phương thức có import `Function`. `plusOne.apply("7")` cho `8`, nhưng `plusOne.apply("abc")` ném `NumberFormatException`; lỗi từ `parse` lan ra và hàm sau **không được gọi** nếu hàm trước thất bại.

Nguyên tắc xử lý:

- **Validation trước parsing:** khi có thể, đặt bước kiểm tra dữ liệu trước khi chạy hàm chuyển đổi, hoặc thiết kế một hàm chuyển đổi trả kiểu kết quả thể hiện lỗi.
- **Bọc ngoại lệ ở ranh giới phù hợp:** gọi `apply` trong `try/catch` khi cần phản hồi nghiệp vụ; tránh âm thầm bỏ lỗi.
- **Checked exceptions:** phương thức `Function.apply` không khai báo `throws` checked exception, nên lambda của nó không thể trực tiếp ném checked exception chưa được xử lý. Có thể xử lý trong lambda hoặc thiết kế giao diện hàm riêng có `throws`.
- **Null đối số `before` hoặc `after`:** `compose(null)` và `andThen(null)` ném `NullPointerException` theo hợp đồng API. Đừng nhầm với việc hàm nhận **giá trị đầu vào null**: đầu vào null có thể hợp lệ hay không tùy thân hàm.
- **Null do một bước tạo ra:** bước tiếp theo có thể gặp `NullPointerException` nếu không hỗ trợ null; `Function` không tự kiểm tra hoặc biến null thành giá trị mặc định.

Không nên cho rằng `compose()` hoặc `andThen()` có tính năng retry, rollback, bỏ qua lỗi hay xử lý null thay cho code ứng dụng. Chúng chỉ điều phối thứ tự áp dụng hàm.

## 12. Những lỗi biên dịch hoặc lỗi hiểu sai thường gặp

| Nhầm lẫn | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| `f.andThen(g)` thực hiện `g` trước | `andThen` luôn gọi hàm hiện tại trước | Đọc như `g(f(x))` |
| `f.compose(g)` thực hiện `f` trước | `compose` gọi `before` trước | Đọc như `f(g(x))` |
| Hai phép ghép luôn cho cùng kết quả | Thứ tự các hàm có thể không giao hoán | Tính thử với đầu vào như `5`, hoặc kiểm tra bằng unit test |
| Chỉ ghép được khi mọi hàm có cùng `T` và `R` | Chỉ yêu cầu tương thích ở **điểm nối** | Viết chuỗi kiểu `A → B → C` |
| `Function<Integer,Integer> wrong = f.andThen(s -> s.length())` | `s` trong lambda sau là `Integer`, không có `length()` | Dùng hàm xử lý `Integer` hoặc đổi đầu ra trước đó |
| `Function<String,Integer> wrong = parse.compose((Integer n) -> n + 1)` | Hàm `before` tạo `Integer`, nhưng kiểu đầu vào mong đợi là `String` | Dùng `parse.andThen(n -> n + 1)` |
| Tạo hàm kết hợp là chạy tất cả bước | Chưa gọi `apply` thì các thân hàm chưa chạy | Gọi `apply`, hoặc truyền hàm vào API thực thi |
| `compose` giúp đảo ngược hàm | Composition khác với inverse function | Cần một hàm nghịch đảo riêng, nếu tồn tại |
| Dùng `Function` cho tất cả hành vi `void` | `Function<T,R>` có kết quả `R` | Xem `Consumer<T>`, `Runnable` nếu chỉ thực hiện thao tác |
| Mọi functional interface đều có `compose` và `andThen` giống `Function` | API của mỗi giao diện hàm có bộ phương thức riêng | Đọc Javadoc: `Predicate` có `and`/`or`, `Consumer` có `andThen`, `BiFunction` có `andThen` |

Hai đoạn mã “wrong” trong bảng là **phản ví dụ cố ý không biên dịch**; chúng không thuộc chương trình mẫu. `javac --release 17` đã được dùng để xác nhận các trường hợp sai kiểu tương ứng.

## 13. Phân biệt API liên quan

`Function<T,R>` mô tả một bước biến đổi có **một đầu vào và một đầu ra**. Java còn các giao diện khác có tên phương thức dễ gây nhầm:

- `UnaryOperator<T>` kế thừa `Function<T,T>` nên có thể dùng các phương thức ghép của `Function` (kiểu kết quả khai báo của các phương thức ghép vẫn là `Function<...>`).
- `BiFunction<T,U,R>` nhận **hai đầu vào** và có `andThen` để xử lý kết quả, nhưng không có `compose` tương ứng như `Function`.
- `Consumer<T>` mô tả thao tác `void`. `Consumer.andThen` ghép **hai thao tác tiêu thụ** theo thứ tự, không tạo ra một phép biến đổi `T → R`.
- `Predicate<T>` trả `boolean`, có `and`, `or`, `negate` để kết hợp điều kiện logic. Không đồng nhất `Predicate.and` với `Function.andThen`.
- Các giao diện chuyên biệt cho kiểu nguyên thủy như `IntUnaryOperator` có API riêng, ví dụ `IntUnaryOperator.compose` và `IntUnaryOperator.andThen` cho `int → int`; hãy kiểm tra Javadoc của từng giao diện thay vì mặc định các chữ ký generic giống nhau.

Quy tắc chọn API: **muốn biến đổi từ T sang R**, chọn `Function<T,R>`; **muốn hành động không trả kết quả**, chọn `Consumer<T>`; **muốn điều kiện đúng/sai**, chọn `Predicate<T>`. Sau đó mới xem phương thức kết hợp thích hợp.

## 14. Bài tập và lời giải

**Bài 1 — Thứ tự.** Cho `f(x)=x-2`, `g(x)=x*x`, `x=6`. Tính `f.andThen(g)` và `f.compose(g)`.

Đáp án: `f.andThen(g).apply(6)` cho `(6-2)^2=16`. `f.compose(g).apply(6)` cho `6^2-2=34`.

**Bài 2 — Ghép khác kiểu.** Có `trim: Function<String,String>`, `parse: Function<String,Integer>`, `doubleIt: Function<Integer,Integer>`. Tạo hàm nhận `String`, trả `Integer` theo thứ tự trim → parse → double.

```java
Function<String, Integer> pipeline =
        trim.andThen(parse).andThen(doubleIt);
```

Đây là câu lệnh minh họa để dùng trong phương thức đã khai báo ba hàm cùng tên và import `Function`. Cách viết bằng `compose` là `doubleIt.compose(parse).compose(trim)` với cùng hợp đồng kiểu.

**Bài 3 — Đọc kiểu trả về.** `Function<String,Integer> parse` nối `Function<Integer,String> label` bằng `andThen` tạo kiểu gì?

Đáp án: `Function<String,String>`, vì đầu vào vẫn là `String`, còn đầu ra cuối là `String`.

**Bài 4 — Phân biệt side effects.** Cho `f` ghi `F`, `g` ghi `G` vào log. Hai lời gọi `f.andThen(g).apply(x)` và `f.compose(g).apply(x)` ghi thứ tự nào?

Đáp án: thứ nhất ghi `FG`; thứ hai ghi `GF`, giả sử cả hai bước đều hoàn tất bình thường và không có bước khác ghi log. Không tự đảo thứ tự thực thi để “tối ưu”.

**Bài 5 — Nhận diện lỗi.** Cho `Function<String,Integer> parse = Integer::parseInt;`. Tại sao `parse.andThen(s -> s.trim())` không hợp lệ?

Đáp án: đối số `s` của hàm sau có kiểu `Integer` nên không có `trim()`. Nếu muốn trim trước khi parse, viết `parse.compose(String::trim)` hoặc `((Function<String,String>) String::trim).andThen(parse)` trong ngữ cảnh kiểu rõ ràng.

**Bài 6 — Identity.** Với `Function<Integer,Integer> addThree = n -> n + 3;`, giá trị của `addThree.andThen(Function.identity()).apply(10)` là bao nhiêu?

Đáp án: `13`; identity không thay đổi đầu ra của `addThree`.

## 15. Ghi nhớ nhanh

1. **`f.andThen(g)` = `g(f(x))`**: gọi `f` trước, rồi `g`.
2. **`f.compose(g)` = `f(g(x))`**: gọi `g` trước, rồi `f`.
3. Các hàm chỉ cần **tương thích kiểu tại điểm nối**, không cần đầu vào và đầu ra cuối trùng nhau.
4. Cả hai phương thức tạo một **Function mới**; phần thân các hàm được thực hiện khi gọi `apply`.
5. `Function.identity()` là phép biến đổi giữ nguyên giá trị, hữu ích làm đơn vị trong kết hợp.
6. Side effects, null và exceptions vẫn phải được xử lý theo nghiệp vụ; thứ tự có ý nghĩa và có thể quan sát được.
7. Khi gặp lỗi generic, hãy viết chuỗi kiểu đầu vào/đầu ra của từng bước rồi chọn `andThen` hoặc `compose` phù hợp.

Tài liệu chuẩn: [Java 17 `Function` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), gồm `apply`, `compose`, `andThen`, `identity`; và [Java Language Specification §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).