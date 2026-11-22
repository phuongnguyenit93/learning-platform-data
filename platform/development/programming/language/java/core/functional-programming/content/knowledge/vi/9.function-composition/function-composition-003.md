# `Function.identity()` và vai trò hàm đồng nhất trong Java

## 1. Hàm đồng nhất là gì?

Trong toán học và lập trình hàm, **hàm đồng nhất** (*identity function*) là hàm trả lại đúng giá trị mà nó nhận được, không biến đổi giá trị ấy:

\[
\operatorname{id}(x)=x.
\]

Trong Java, giao diện `java.util.function.Function<T, R>` mô tả một phép ánh xạ từ kiểu `T` sang kiểu `R` bằng phương thức trừu tượng duy nhất `R apply(T value)`. Khi kiểu vào và kiểu ra đều là `T`, Java cung cấp phương thức tiện ích:

~~~java
static <T> Function<T, T> identity()
~~~

Ta gọi phương thức này qua `Function.identity()`. Nó trả một `Function<T,T>` mà `apply(x)` trả lại chính `x`. Cách viết rõ tương đương về hành vi là:

~~~java
Function<String, String> identityA = Function.identity();
Function<String, String> identityB = s -> s;
~~~

Ví dụ, cả `identityA.apply("Java")` và `identityB.apply("Java")` trả `"Java"`. Đây **không phải một phép biến đổi chuỗi** như `trim()` hoặc `toUpperCase()`, cũng không phải hàm so sánh hoặc tạo đối tượng mới: đầu ra là chính đầu vào.

Điều quan trọng của hàm đồng nhất không nằm ở việc “làm một thao tác vô ích” mà ở vai trò **phần tử trung hòa** khi ghép các hàm. Nó giúp biểu đạt ý định giữ nguyên dữ liệu trong các pipeline có yêu cầu truyền vào một `Function`.

## 2. Cú pháp, kiểu tổng quát và suy luận generic

Chữ ký API là:

~~~java
public static <T> Function<T, T> identity()
~~~

- `<T>` là tham số kiểu generic của *phương thức static*.
- `Function<T,T>` có kiểu đầu vào và đầu ra giống nhau.
- `identity()` không nhận đối số; dữ liệu chỉ đi vào khi sau đó gọi `apply(value)`.
- Compiler có thể suy ra `T` từ ngữ cảnh gán biến hoặc ngữ cảnh truyền tham số.

~~~java
Function<String, String> stringId = Function.identity();
Function<Integer, Integer> integerId = Function.identity();
Function<List<String>, List<String>> listId = Function.identity();

String text = stringId.apply("Java");
Integer number = integerId.apply(42);
~~~

Khi muốn chỉ định kiểu một cách tường minh, sử dụng *type witness*:

~~~java
Function<String, String> id = Function.<String>identity();
~~~

Trong đoạn code trên, hai cách gán `Function.identity()` và `Function.<String>identity()` đều hợp lệ. Type witness hữu ích khi ngữ cảnh suy luận kiểu khó hiểu hoặc khi muốn cho người đọc thấy rõ kiểu trung gian.

Đừng lẫn `Function.identity()` với `Function<String, String>`: thứ nhất là **phương thức trả về một hàm**; thứ hai là **kiểu của hàm**. Cũng không nên gán nó cho một kiểu đầu ra khác kiểu đầu vào:

~~~java
Function<String, String> ok = Function.identity();
// Function<String, Integer> wrong = Function.identity(); // Không tương thích.
~~~

Hàm đồng nhất có thể dùng với tham chiếu đối tượng hoặc các wrapper như `Integer`; Java generics không trực tiếp nhận kiểu nguyên thủy `int` làm tham số `T`.

## 3. Vai trò phần tử trung hòa trong kết hợp hàm

Giả sử có hàm `f: A -> B` và hai hàm đồng nhất `idA: A -> A`, `idB: B -> B`. Khi kết hợp hàm:

\[
f \circ id_A = f,\qquad id_B \circ f = f.
\]

Nghĩa là đưa hàm đồng nhất **trước** hay **sau** `f` đều cho cùng kết quả đầu vào/đầu ra như `f`. Trong Java:

- `f.compose(before)` tạo một hàm thực hiện `before` **trước**, rồi mới thực hiện `f`: `f(before(x))`.
- `f.andThen(after)` tạo một hàm thực hiện `f` **trước**, rồi mới thực hiện `after`: `after(f(x))`.
- `f.compose(Function.identity())` tương đương về phép ánh xạ với `f` khi generic và ngữ cảnh phù hợp.
- `f.andThen(Function.identity())` cũng tương đương về phép ánh xạ với `f`.

Đặt `Function<String, Integer> length = String::length;`. Các dạng sau đều tính độ dài của chuỗi:

~~~java
Function<String, Integer> length = String::length;

Function<String, Integer> first =
        length.compose(Function.<String>identity());
Function<String, Integer> second =
        length.andThen(Function.<Integer>identity());

System.out.println(length.apply("Java")); // 4
System.out.println(first.apply("Java"));  // 4
System.out.println(second.apply("Java")); // 4
~~~

Chú ý **hai kiểu khác nhau** trong ví dụ: `identity` đứng trước `length` nhận/trả `String`, còn `identity` đứng sau `length` nhận/trả `Integer`. Với `Function<String,String>` như `String::trim`, cả hai phía đều là `Function<String,String>`.

Sơ đồ thực thi:

~~~text
compose:
x ──> identity<A> ──> f ──> y

andThen:
x ──> f ──> identity<B> ──> y
~~~

Cần hiểu “trung hòa” là **tương đương về phép ánh xạ/hành vi mà người gọi quan sát khi áp dụng hàm**, chứ không bảo đảm rằng `f.compose(identity) == f` theo toán tử tham chiếu `==`. `compose` và `andThen` trả về một đối tượng triển khai `Function`; API không hứa rằng object đó trùng object `f` ban đầu.

### 3.1. Vì sao tên “identity” hợp lý?

Một phép ghép hàm có tính kết hợp: với các hàm thích hợp `(h ∘ g) ∘ f = h ∘ (g ∘ f)`. Hàm đồng nhất đóng vai trò giống số `0` trong phép cộng hoặc số `1` trong phép nhân: ghép thêm nó không làm thay đổi giá trị cuối cùng. Tính chất đó giúp ta suy luận về các pipeline bất kể khối xử lý có số lượng bước biến đổi khác nhau.

Trong Java, `Function.compose` và `Function.andThen` thực hiện các phép ghép hai hàm đơn giản. Với logic có side effect, khi suy luận quy tắc đại số rộng hơn cần cân nhắc số lần và thứ tự thực thi, lỗi ngoại lệ và trạng thái mutable; đừng mặc định tất cả hàm đều thuần khiết.

## 4. Dùng `Function.identity()` trong Stream

`Stream.map` yêu cầu một hàm ánh xạ từng phần tử đầu vào sang phần tử đầu ra. Khi muốn giữ nguyên từng phần tử, có thể truyền `Function.identity()`:

~~~java
List<String> words = List.of("Java", "Lambda");

List<String> sameValues = words.stream()
        .map(Function.identity())
        .toList();
System.out.println(sameValues); // [Java, Lambda]
~~~

`map(Function.identity())` không biến đổi các phần tử. Với Stream thuần túy, bước này có thể dư thừa; ví dụ `words.stream().toList()` cũng thu được cùng các giá trị trong cùng thứ tự encounter order. Tuy nhiên, `identity()` rất hữu ích khi API yêu cầu đối tượng `Function` hoặc khi xây dựng pipeline động mà một nhánh cần để nguyên giá trị.

**Không nhầm “các phần tử giữ nguyên” với “danh sách giữ nguyên”.** `toList()` tạo một danh sách kết quả (không chỉnh sửa được theo hợp đồng của `Stream.toList()`), còn các phần tử có thể vẫn là chính những đối tượng trong nguồn. Nếu phần tử mutable, thay đổi trạng thái đối tượng qua một tham chiếu sẽ được nhìn thấy qua các tham chiếu khác cùng trỏ đến nó.

Trong những trường hợp như:

~~~java
List<String> upper = words.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Ta cần một phép biến đổi thực; khi đó `Function.identity()` không thay thế được `String::toUpperCase`.

## 5. Ứng dụng rất thường gặp: `Collectors.toMap`

`Collectors.toMap(keyMapper, valueMapper)` cần **hai hàm**: một hàm tạo khóa, một hàm tạo giá trị. Khi muốn map giữ **chính phần tử ban đầu** làm value, `Function.identity()` là lựa chọn rõ nghĩa:

~~~java
record User(String id, String name) {}

List<User> users = List.of(
        new User("u01", "An"),
        new User("u02", "Binh"));

Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(
                User::id,
                Function.identity()));

System.out.println(byId.get("u02").name()); // Binh
~~~

Cách đọc `Collectors.toMap(User::id, Function.identity())`:

1. Với mỗi `User u`, lấy `u.id()` làm key.
2. Dùng chính `u` làm value (không đổi sang `u.name()` hay tạo `User` khác).
3. Thêm cặp key/value đó vào Map kết quả.

Lambda tương đương về ánh xạ giá trị là `u -> u`:

~~~java
Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(User::id, u -> u));
~~~

Không có lý do học thuật hay hiệu năng nào buộc phải dùng một trong hai. `Function.identity()` thường thể hiện rõ ý “giữ nguyên đối tượng” và giảm việc lặp tên biến.

**Giới hạn cần nhớ:** overload hai tham số của `Collectors.toMap` ném `IllegalStateException` nếu các phần tử tạo key trùng nhau; `Function.identity()` không giải quyết va chạm key. Hãy chọn chính sách merge hợp lý, ví dụ giữ bản ghi xuất hiện trước:

~~~java
Map<String, User> firstById = users.stream()
        .collect(Collectors.toMap(
                User::id,
                Function.identity(),
                (first, later) -> first));
~~~

Ví dụ trên giả định `User` đã được định nghĩa và `users` có sẵn như phía trên. Với parallel stream hoặc khi không có encounter order bảo đảm, không tự giả định thứ tự cụ thể để quyết định bản ghi nào “đầu tiên”.

Trong `toMap`, value mapper không được trả `null` cho các đường thu thập thông thường của `Collectors.toMap`; vì vậy `Function.identity()` không biến việc thu thập những phần tử `null` thành an toàn. Với những collection có thể chứa null, hãy định nghĩa quy tắc lọc/xử lý rõ ràng trước khi thu thập.

## 6. Ví dụ Java 17+ chạy độc lập

Tạo tệp `IdentityFunctionDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class IdentityFunctionDemo {
    record User(String id, String name) {}

    public static void main(String[] args) {
        String original = new String("  Java  ");
        Function<String, String> identity = Function.identity();

        String retained = identity.apply(original);
        System.out.println("same reference=" + (retained == original));
        System.out.println("null stays null=" + (identity.apply(null) == null));

        Function<String, String> trim = String::trim;
        Function<String, String> before =
                trim.compose(Function.identity());
        Function<String, String> after =
                trim.andThen(Function.identity());

        System.out.println("compose=" + before.apply(original));
        System.out.println("andThen=" + after.apply(original));

        Function<String, Integer> length = String::length;
        Function<String, Integer> lengthBefore =
                length.compose(Function.<String>identity());
        Function<String, Integer> lengthAfter =
                length.andThen(Function.<Integer>identity());
        System.out.println("length before=" + lengthBefore.apply("Java"));
        System.out.println("length after=" + lengthAfter.apply("Java"));

        List<String> labels = List.of("Java", "Stream");
        System.out.println("map=" + labels.stream()
                .map(Function.identity()).toList());

        List<User> users = List.of(
                new User("u01", "An"),
                new User("u02", "Binh"));
        Map<String, User> byId = users.stream()
                .collect(Collectors.toMap(
                        User::id,
                        Function.identity()));
        System.out.println("user=" + byId.get("u02").name());
        System.out.println("same user=" + (byId.get("u01") == users.get(0)));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac IdentityFunctionDemo.java
java IdentityFunctionDemo
~~~

Stdout kỳ vọng:

~~~text
same reference=true
null stays null=true
compose=Java
andThen=Java
length before=4
length after=4
map=[Java, Stream]
user=Binh
same user=true
~~~

Giải thích:

- `original` là một `String` object; `identity.apply(original)` trả đúng object ấy, nên `retained == original` là `true`.
- Identity function không tự kiểm tra null; khi đầu vào `null`, đầu ra cũng là `null`.
- Ghép `identity` trước hoặc sau phép `trim` không đổi kết quả `"Java"`.
- Kiểu `String` và `Integer` của identity được phân biệt rõ trong hai hướng kết hợp với `length`.
- `map(Function.identity())` giữ nguyên các phần tử `"Java"` và `"Stream"`.
- `toMap(User::id, Function.identity())` dùng ID làm khóa và chính `User` làm value; `byId.get("u01") == users.get(0)` là `true`.

## 7. Identity function không đồng nghĩa với sao chép

Đây là điểm quan trọng khi dùng với đối tượng mutable. Cùng một đối tượng có thể được tham chiếu bởi nhiều biến:

~~~java
List<String> mutable = new java.util.ArrayList<>();
mutable.add("first");

Function<List<String>, List<String>> id = Function.identity();
List<String> alias = id.apply(mutable);
alias.add("second");

System.out.println(mutable);        // [first, second]
System.out.println(alias == mutable); // true
~~~

`identity()` **không tạo bản sao nông hoặc bản sao sâu**; nó trả về đúng đối tượng. Nếu cần một danh sách mới, phải tạo rõ ràng:

~~~java
Function<List<String>, List<String>> copy =
        source -> new java.util.ArrayList<>(source);
~~~

Phép sao chép trên chỉ tạo danh sách mới và sao chép các **tham chiếu phần tử**; với phần tử là đối tượng mutable, đó vẫn chỉ là shallow copy.

Cũng không nên hiểu `Function.identity()` là kiểm tra **đồng nhất đối tượng** hay kiểm tra bằng nhau: `identity` ở đây là tên của *phép ánh xạ x → x*. Đối với kiểm tra tham chiếu, dùng `==`; đối với so sánh giá trị theo hợp đồng `equals`, dùng `equals`/`Objects.equals`. Ba khái niệm đó có vai trò khác nhau.

## 8. Những điểm kỹ thuật dễ hiểu sai

### 8.1. `identity()` không thực thi xử lý khi tạo

~~~java
Function<String, String> id = Function.identity(); // Tạo/lấy một Function.
String result = id.apply("x");                      // Áp dụng Function: trả "x".
~~~

Lời gọi `Function.identity()` chỉ lấy một hàm. Nó không nhận một chuỗi hay xử lý một chuỗi ngay tại thời điểm ấy.

### 8.2. Đừng dựa vào identity object của chính các hàm trả về

~~~java
Function<String, String> a = Function.identity();
Function<String, String> b = Function.identity();
~~~

API bảo đảm hành vi áp dụng `a.apply(x)` và `b.apply(x)` đều trả `x`; nó **không cam kết** `a == b` là `true` hoặc `false` trên mọi JDK. Các implementation có thể tái sử dụng đối tượng lambda hoặc tạo đối tượng khác, và đó không phải điều kiện để lập trình đúng.

### 8.3. Xử lý `null` không tự xuất hiện

`Function.identity()` nhận `null` và trả `null`. Nó không ném `NullPointerException` chỉ vì `apply(null)`, nhưng hàm phía trước hoặc phía sau có thể ném lỗi:

~~~java
Function<String, String> id = Function.identity();
Function<String, String> trim = String::trim;

// id.apply(null) trả null.
// trim.compose(id).apply(null) ném NullPointerException tại trim.
~~~

Tương tự, collection/collector hoặc API nhận hàm có thể áp dụng ràng buộc null riêng; không lấy hành vi của identity làm bảo đảm cho cả pipeline.

### 8.4. `Function.identity()` khác với `UnaryOperator.identity()`

`UnaryOperator<T>` là một functional interface chuyên biệt kế thừa `Function<T,T>` và cung cấp phương thức static `UnaryOperator.identity()`. Nếu API yêu cầu `UnaryOperator<T>`, dùng:

~~~java
import java.util.function.UnaryOperator;

UnaryOperator<String> id = UnaryOperator.identity();
System.out.println(id.apply("Java")); // Java
~~~

`Function.identity()` có kiểu trả về được khai báo là `Function<T,T>`; không thể tùy tiện gán nó vào biến `UnaryOperator<T>` vì `Function<T,T>` không phải subtype của `UnaryOperator<T>`, dù chức năng hai hàm đồng nhất về hành vi.

### 8.5. Identity có thể dư thừa hoặc gây khó đọc khi lạm dụng

~~~java
List<String> items = List.of("a", "b");

List<String> a = items.stream().toList();
List<String> b = items.stream().map(Function.identity()).toList();
~~~

Trong tình huống này, viết thêm `map(identity())` không làm rõ thêm mục đích xử lý. Nhưng trong `Collectors.toMap(KeyExtractor, Function.identity())`, nó là cách diễn đạt cần thiết vì collector thực sự đòi hỏi một **value mapper**.

Đừng tự thêm identity chỉ để làm code trông “functional” hơn; chọn nó khi muốn thể hiện hoặc cung cấp phép ánh xạ giữ nguyên dữ liệu.

### 8.6. Method reference, lambda và identity

- `x -> x` là một lambda biểu đạt hàm đồng nhất.
- `Function.identity()` là phương thức static trả về một hàm đồng nhất.
- Method reference dạng `SomeType::someMethod` biểu đạt việc chuyển tiếp đến phương thức được chỉ định. Nó chỉ đóng vai trò identity nếu phương thức đó thực sự trả nguyên đầu vào theo nghĩa liên quan.
- `Objects::toString` hoặc `String::toString` không thể thay thế tổng quát cho `Function.identity()`: kiểu nhận/trả, hành vi khi null và khả năng áp dụng với các kiểu khác nhau có thể khác biệt.

## 9. Bài tập kiểm tra hiểu biết

**Bài 1 — Ghép hàm.** Với `Function<Integer, Integer> square = x -> x * x;`, kết quả của `square.compose(Function.identity()).apply(5)` và `square.andThen(Function.identity()).apply(5)` là gì?

Đáp án: cả hai bằng `25`. Identity là phần tử trung hòa khi ghép hai hàm, nên thứ tự ghép trước/sau không thay đổi giá trị.

**Bài 2 — Giữ object hay copy?** Sau khi tạo `Function<List<String>,List<String>> f = Function.identity();`, gọi `f.apply(list) == list` cho kết quả gì nếu `list` khác null?

Đáp án: `true`; đây là cùng tham chiếu, không phải danh sách mới.

**Bài 3 — Giá trị trong Map.** Với `users.stream().collect(Collectors.toMap(User::id, Function.identity()))`, kiểu value của Map là gì và khi ID trùng nhau thì sao?

Đáp án: value là `User` gốc. Dạng collector hai tham số ném `IllegalStateException` khi hai phần tử cùng khóa; cần chính sách merge hoặc loại bỏ trùng từ trước.

**Bài 4 — Null.** `Function.<String>identity().apply(null)` cho gì?

Đáp án: trả `null`; identity không tự xác thực null. Nhưng `String::trim` trên receiver null sẽ ném `NullPointerException`.

**Bài 5 — Kiểu generic.** Với `Function<String, Integer> length = String::length;`, identity đứng phía trước và phía sau cần ánh xạ kiểu nào?

Đáp án: trước `length` là `String -> String`; sau `length` là `Integer -> Integer`. Có thể ghi rõ bằng `Function.<String>identity()` và `Function.<Integer>identity()`.

## 10. Ghi nhớ

`Function.identity()` biểu diễn **phép ánh xạ giữ nguyên đầu vào** với kiểu `Function<T,T>`. Nó đóng vai trò phần tử trung hòa của phép kết hợp hàm: `f.compose(id)` và `f.andThen(id)` cho cùng phép ánh xạ như `f` khi kiểu đích tương ứng. Trong Java thực tế, nó đặc biệt hữu ích khi `Stream` hoặc `Collector` yêu cầu một mapper nhưng dữ liệu cần giữ nguyên, nổi bật là `Collectors.toMap(keyMapper, Function.identity())`.

Hãy luôn phân biệt **giữ nguyên đối tượng** với **tạo bản sao**, **hành vi ánh xạ đồng nhất** với **đồng nhất tham chiếu của đối tượng Function**, và nhớ rằng null, key trùng, side effect hay ràng buộc của API bên ngoài vẫn cần được xử lý theo hợp đồng cụ thể.
