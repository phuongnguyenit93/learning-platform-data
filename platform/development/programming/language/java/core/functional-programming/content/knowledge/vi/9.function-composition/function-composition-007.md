# Currying và áp dụng trước một phần đối số bằng lambda trong Java

## 1. Vấn đề và mục tiêu

Một hàm nhận hai hoặc nhiều đối số có thể được tổ chức theo nhiều cách. Với Java, người học quen viết:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
int result = add.apply(2, 3); // 5
~~~

Nếu ta thường xuyên phải cộng một số cố định, hoặc tạo trước một phép tính rồi dùng nhiều lần với dữ liệu đến sau, việc truyền lại tất cả đối số ở mỗi lần gọi không phải lúc nào cũng thuận tiện. Hai kỹ thuật liên quan là:

- **Currying:** biến hàm nhận nhiều đối số thành **chuỗi các hàm**, mỗi hàm nhận một đối số rồi trả về hàm tiếp theo, cho đến khi nhận đủ dữ liệu để tính kết quả.
- **Partial application (áp dụng trước một phần đối số):** **cố định một hoặc vài đối số** của một phép tính có nhiều đối số, tạo ra một hàm mới chỉ chờ các đối số còn lại.

Hai kỹ thuật gần nhau nhưng **không đồng nghĩa**. Currying là một phép biến đổi cấu trúc chữ ký của hàm, còn partial application là thao tác tạo hàm chuyên biệt bằng cách cố định tham số. Currying có thể giúp thực hiện partial application, nhưng hoàn toàn có thể làm partial application trực tiếp từ `BiFunction` mà không curry.

Trong module Java core – functional programming, ta sẽ dùng **lambda**, các functional interface trong `java.util.function` và generic để xây dựng hai kỹ thuật này mà không cần thư viện ngoài.

Sau bài học, bạn cần:

1. Giải thích sự khác biệt `(A, B) -> R` và `A -> (B -> R)`.
2. Viết lambda lồng nhau, gọi theo từng giai đoạn và lưu một hàm trung gian.
3. Cố định đối số bên trái hoặc bên phải của `BiFunction<A,B,R>`.
4. Biến `BiFunction` sang dạng curried và chuyển trở lại khi cần.
5. Dùng `Function.compose`/`andThen` cùng một hàm đã được áp dụng trước.
6. Nhận diện capture, `final`/effectively final, generic, side effect, `null`, exception và vấn đề hiệu năng.
7. Chạy và kiểm thử ví dụ Java 17 độc lập.

## 2. Mô hình kiểu dữ liệu: từ nhiều đầu vào đến chuỗi hàm

### 2.1. Hàm hai đối số thông thường

Trong Java, `BiFunction<A,B,R>` mô tả một phép biến đổi nhận hai đối số và trả về một kết quả:

~~~java
BiFunction<Integer, Integer, Integer> multiply =
        (price, quantity) -> price * quantity;

int total = multiply.apply(120, 3); // 360
~~~

Hình dung chữ ký:

~~~text
BiFunction<A, B, R> : (A, B) -> R
                             |
                             v
                           kết quả
~~~

`multiply` không phải là hàm currying: nó yêu cầu cả hai đối số trong **một** lời gọi `apply`. Các đoạn ở mục này là ví dụ khai báo trong phương thức với import `java.util.function.*`.

### 2.2. Hàm đã currying

Một hàm hai đối số sau khi curry có hình thức:

~~~java
Function<Integer, Function<Integer, Integer>> curriedMultiply =
        price -> quantity -> price * quantity;
~~~

Cú pháp `price -> quantity -> price * quantity` được hiểu là:

~~~java
price -> (quantity -> price * quantity)
~~~

Không phải phép toán trừ; mũi tên `->` ở trong trả về **một lambda thứ hai**. Kiểu đầy đủ:

~~~text
Function<A, Function<B, R>>
    A ----> Function<B, R>
                 B ----> R
~~~

Cách gọi:

~~~java
int total = curriedMultiply.apply(120).apply(3); // 360
~~~

- `curriedMultiply.apply(120)` trả về một đối tượng hàm kiểu `Function<Integer,Integer>`. Tại bước này chưa cần `quantity`.
- Hàm được trả về **ghi nhớ** giá trị `price` thông qua lambda capture.
- Gọi `apply(3)` trên hàm còn lại mới chạy phép nhân và trả `360`.

Viết thành nhiều dòng thường giúp dễ đọc:

~~~java
Function<Integer, Integer> price120 =
        curriedMultiply.apply(120);

int threeItems = price120.apply(3); // 360
int fiveItems = price120.apply(5);  // 600
~~~

Đây là ví dụ **currying kết hợp partial application**: cấu trúc curried cho phép áp dụng trước `price = 120` rồi tái sử dụng với nhiều `quantity`.

### 2.3. Ba đối số được curry

Ví dụ phép cộng ba số:

~~~java
Function<Integer,
        Function<Integer,
                Function<Integer, Integer>>> addThree =
        a -> b -> c -> a + b + c;

int sum = addThree.apply(2).apply(3).apply(4); // 9
~~~

Có thể từng bước cố định `a` hoặc cả `a` và `b`:

~~~java
Function<Integer, Function<Integer, Integer>> add2 =
        addThree.apply(2);
Function<Integer, Integer> add2And3 = add2.apply(3);
int result = add2And3.apply(4); // 9
~~~

Dạng này chứng minh nguyên lý, nhưng trong Java kiểu lồng nhau dài dễ làm code khó đọc. Với API nghiệp vụ, dùng class, record, tên phương thức rõ nghĩa, hoặc `BiFunction` có thể hợp lý hơn.

## 3. Currying và partial application: khác nhau ở đâu?

| Tiêu chí | Currying | Partial application |
| --- | --- | --- |
| Mục tiêu trực tiếp | Biến hàm nhiều đầu vào thành chuỗi hàm một đầu vào | Tạo hàm mới bằng cách cố định một số đầu vào |
| Đầu vào điển hình | Hàm `(A,B) -> R` | Một hàm nhiều tham số và một số giá trị đã biết |
| Đầu ra điển hình | `A -> (B -> R)` | Hàm còn chờ các tham số chưa cố định |
| Có bắt buộc thay cấu trúc sang hàm lồng nhau? | Có, theo định nghĩa currying | Không |
| Có thể cố định tham số thứ hai trước không? | Với dạng `A -> (B -> R)`, thứ tự tự nhiên là `A` trước; cần biến đổi thêm để cố định `B` trước | Có, nếu tạo hàm thích hợp |
| Công cụ Java phù hợp | Lambda lồng nhau, `Function<A,Function<B,R>>` | Closure lambda, `BiFunction`, các hàm `bindFirst`/`bindSecond` |

Một ví dụ **partial application trực tiếp không cần curry**:

~~~java
BiFunction<Integer, Integer, Integer> subtract =
        (a, b) -> a - b;

// Cố định a = 10, còn chờ b.
Function<Integer, Integer> fromTen =
        b -> subtract.apply(10, b);

System.out.println(fromTen.apply(3)); // 7
~~~

Một ví dụ cố định **đối số thứ hai**:

~~~java
// Cố định b = 10, còn chờ a.
Function<Integer, Integer> minusTen =
        a -> subtract.apply(a, 10);

System.out.println(minusTen.apply(3)); // -7
~~~

Vì phép trừ không giao hoán, hai cách cố định cho kết quả khác nhau. Thứ tự tham số là một phần của hợp đồng nghiệp vụ; khi đặt tên hàm, nên làm rõ **đã cố định tham số nào**.

**Kết luận phần này:** mọi bước gọi một hàm đã curry với ít đối số hơn ban đầu có thể xem như tạo ra một dạng hàm đã áp dụng trước một phần; nhưng partial application có thể thực hiện từ bất kỳ hàm thích hợp nào bằng closure, không cần chuyển sang dạng curried.

## 4. Xây dựng `bindFirst` và `bindSecond` với generic

Ta có thể viết hai helper tái sử dụng cho bất kỳ `BiFunction<A,B,R>`.

### 4.1. Cố định tham số đầu tiên

~~~java
static <A, B, R> Function<B, R> bindFirst(
        BiFunction<A, B, R> function, A fixedA) {
    Objects.requireNonNull(function, "function");
    return b -> function.apply(fixedA, b);
}
~~~

Đây là **phương thức cần đặt trong class** có import `java.util.function.BiFunction`, `Function` và `java.util.Objects`.

Ý nghĩa kiểu:

~~~text
Trước: (A, B) -> R
bindFirst(function, fixedA)
Sau:       B  -> R
~~~

Ví dụ:

~~~java
BiFunction<Integer, Integer, Integer> multiply =
        (a, b) -> a * b;

Function<Integer, Integer> triple =
        bindFirst(multiply, 3);

int result = triple.apply(7); // 21
~~~

Giá trị `3` được giữ trong closure. Lambda mới chỉ cần nhận `b` rồi gọi lại phép tính gốc.

### 4.2. Cố định tham số thứ hai

~~~java
static <A, B, R> Function<A, R> bindSecond(
        BiFunction<A, B, R> function, B fixedB) {
    Objects.requireNonNull(function, "function");
    return a -> function.apply(a, fixedB);
}
~~~

Ý nghĩa kiểu:

~~~text
Trước: (A, B) -> R
bindSecond(function, fixedB)
Sau:   A     -> R
~~~

Ví dụ:

~~~java
BiFunction<String, String, String> join =
        (prefix, value) -> prefix + value;

Function<String, String> addSuffix =
        bindSecond(join, "-done");

String result = addSuffix.apply("task"); // task-done
~~~

**Vì sao dùng generic?** Nếu định nghĩa helper chỉ cho `Integer`, bạn sẽ phải viết lại cho `String` hoặc object khác. Ba tham số kiểu `A`, `B`, `R` giúp compiler kiểm tra các cách kết hợp mà không cần raw type và cast không an toàn.

Các helper này sử dụng `Objects.requireNonNull` để từ chối một `function` bằng `null` ngay khi tạo hàm. Chúng **không tự từ chối** `fixedA` hoặc `fixedB` bằng `null`; điều đó tùy hợp đồng của phép tính gốc. Nếu lambda gốc không xử lý `null`, lỗi có thể chỉ xảy ra khi gọi `apply` trên hàm trả về.

### 4.3. Hướng dẫn đọc một kiểu generic lồng nhau

Đọc từ trong ra ngoài:

- `BiFunction<A,B,R>`: biết cả `A`, `B` thì cho `R`.
- `Function<B,R>`: chỉ cần `B` để cho `R`.
- `Function<A,Function<B,R>>`: cần `A` để tạo một hàm mới, rồi cần `B` để cho `R`.

Cố gắng hiểu nghĩa bằng số lượng đầu vào còn thiếu, thay vì nhìn các dấu `<`/`>` như một chuỗi ký tự khó đọc.

## 5. Viết helper `curry` và `uncurry`

Khi cần chuyển đổi hình thức hàm, có thể tự định nghĩa:

~~~java
static <A, B, R> Function<A, Function<B, R>> curry(
        BiFunction<A, B, R> function) {
    Objects.requireNonNull(function, "function");
    return a -> b -> function.apply(a, b);
}

static <A, B, R> BiFunction<A, B, R> uncurry(
        Function<A, Function<B, R>> function) {
    Objects.requireNonNull(function, "function");
    return (a, b) -> function.apply(a).apply(b);
}
~~~

Hai phương thức trên là **mã minh họa nằm trong class** có các import phù hợp. Công dụng:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;

Function<Integer, Function<Integer, Integer>> curried =
        curry(add);

Function<Integer, Integer> addTen = curried.apply(10);
System.out.println(addTen.apply(5)); // 15

BiFunction<Integer, Integer, Integer> originalShape =
        uncurry(curried);
System.out.println(originalShape.apply(10, 5)); // 15
~~~

### Điểm cần hiểu về bảo toàn hành vi

Với **hàm thuần (pure function)** – cùng đầu vào, cùng kết quả, không quan sát side effect – `uncurry(curry(f))` có kết quả tương đương `f` trên các đầu vào phù hợp. Tuy nhiên, với hàm tạo side effect, `null`, exception hoặc các bước trả về hàm có tác dụng phụ, thời điểm/tần suất chạy các bước có thể làm sự tương đương quan sát được phức tạp hơn.

Ví dụ `curry(function)` ở trên **chỉ tạo wrapper**; việc gọi `function.apply(a,b)` xảy ra khi đã nhận cả `a` và `b`. Với một implementation curried tự viết, logic trong hàm ngoài `a -> { ... }` có thể chạy ngay từ lần `apply(a)` đầu, trước khi có `b`. Điều này tác động tới log, thời gian, tính toán tốn kém và exception.

Cần hiểu rằng **hàm lồng nhau không mặc nhiên lazy hoàn toàn**. Bước tạo hàm có thể làm việc; trong đoạn lambda chỉ có biểu thức trả về lambda, bước đầu thường chưa thực hiện phép tính cuối cùng.

## 6. Closure và quy tắc bắt giữ biến

### 6.1. Vì sao hàm mới "nhớ" đối số?

~~~java
int fee = 5;

Function<Integer, Integer> addFee =
        price -> price + fee;
~~~

`fee` là local được lambda bắt giữ; nó phải là `final` hoặc **effectively final**. Sau đó `addFee.apply(100)` trả `105`. Nếu thêm `fee = 7;` ở cùng phạm vi, code dùng `fee` trong lambda sẽ không biên dịch.

Với partial application:

~~~java
static Function<Integer, Integer> plus(int fixed) {
    return value -> fixed + value;
}
~~~

Tham số `fixed` cũng được capture. Nếu không gán lại `fixed`, lambda được trả về hợp lệ và có thể tiếp tục sử dụng giá trị sau khi phương thức `plus` kết thúc.

### 6.2. Capture tham chiếu không đóng băng đối tượng

~~~java
StringBuilder prefix = new StringBuilder("old-");
Function<String, String> label =
        value -> prefix + value;

prefix.replace(0, prefix.length(), "new-");
System.out.println(label.apply("item")); // new-item
~~~

Ví dụ cần được đặt trong phương thức. `prefix` không bị gán lại nên effectively final, nhưng đối tượng `StringBuilder` là mutable. Hàm đọc **trạng thái hiện tại** của builder. Ngữ nghĩa này khác với việc cố định một chuỗi immutable:

~~~java
String fixedPrefix = prefix.toString();
Function<String, String> stableLabel =
        value -> fixedPrefix + value;
~~~

Đây là cách tạo snapshot của **chuỗi** tại thời điểm tạo `stableLabel`, miễn `fixedPrefix` không bị gán lại. Khi dùng helper `bindFirst` với một đối số là object mutable, giá trị được giữ là **tham chiếu**, không phải deep copy object.

### 6.3. Field và shared mutable state

Quy tắc effectively final áp dụng cho local/parameter được capture, không biến các field hoặc object được capture thành immutable. Lambda có thể cập nhật trạng thái của object bên ngoài nếu API cho phép; nếu hàm được chia sẻ giữa thread, cần xem xét race condition và memory visibility độc lập với quy tắc capture.

Để có hàm dễ dự đoán, nên ưu tiên capture dữ liệu immutable hoặc snapshot phù hợp, tránh thay đổi đối tượng đã đóng trong closure nếu không thật sự cần.

## 7. Ví dụ Java 17 hoàn chỉnh: bảng giá, cộng phí và nhãn

Chương trình sau kết hợp hai cách cố định đối số, một hàm đã curry và phép `andThen`. Nó được viết **độc lập, không cần thư viện ngoài**.

Tạo tệp **`CurryingDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.Function;

public class CurryingDemo {

    static <A, B, R> Function<B, R> bindFirst(
            BiFunction<A, B, R> fn, A a) {
        Objects.requireNonNull(fn, "fn");
        return b -> fn.apply(a, b);
    }

    static <A, B, R> Function<A, R> bindSecond(
            BiFunction<A, B, R> fn, B b) {
        Objects.requireNonNull(fn, "fn");
        return a -> fn.apply(a, b);
    }

    public static void main(String[] args) {
        // price * quantity
        BiFunction<Integer, Integer, Integer> multiply =
                (price, quantity) -> price * quantity;

        // Cố định price=120, còn chờ quantity.
        Function<Integer, Integer> fixedPrice =
                bindFirst(multiply, 120);

        // Cố định quantity=3, còn chờ price.
        Function<Integer, Integer> quantityThree =
                bindSecond(multiply, 3);

        // Currying: a -> (b -> a + b).
        Function<Integer, Function<Integer, Integer>> curriedAdd =
                a -> b -> a + b;

        Function<Integer, Integer> addFive =
                curriedAdd.apply(5);

        System.out.println(fixedPrice.apply(3));
        System.out.println(quantityThree.apply(90));
        System.out.println(addFive.apply(7));

        // Trước hết nhân số lượng 3, sau đó cộng phí cố định 5.
        Function<Integer, Integer> pricedAndFee =
                quantityThree.andThen(addFive);
        System.out.println(pricedAndFee.apply(120));

        // Một hàm currying có kiểu đầu vào khác nhau.
        Function<String, Function<Integer, String>> label =
                prefix -> value -> prefix + value;
        System.out.println(label.apply("ID-").apply(42));

        // Mutable capture: tham chiếu ổn định, object thay đổi.
        StringBuilder mutablePrefix = new StringBuilder("old-");
        Function<String, String> tag = text -> mutablePrefix + text;
        mutablePrefix.replace(
                0, mutablePrefix.length(), "new-");
        System.out.println(tag.apply("value"));
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 CurryingDemo.java
java CurryingDemo
~~~

**Stdout chính xác:**

~~~text
360
270
12
365
ID-42
new-value
~~~

Giải thích từng dòng:

1. `fixedPrice.apply(3)` dùng `120 * 3` nên ra `360`.
2. `quantityThree.apply(90)` dùng `90 * 3` nên ra `270`.
3. `addFive.apply(7)` dùng `5 + 7` nên ra `12`.
4. `quantityThree.andThen(addFive)` lấy đầu vào `120` → nhân `3` thành `360` → cộng `5` thành `365`.
5. `label.apply("ID-")` tạo hàm ghi nhớ prefix, sau đó `apply(42)` sinh `ID-42`.
6. `mutablePrefix` được capture dưới dạng tham chiếu tới `StringBuilder`. Sau `replace`, `tag.apply("value")` đọc trạng thái mới, in `new-value`.

**Đơn vị tiền tệ:** ví dụ dùng `int` chỉ để dạy cách tổ chức hàm và thứ tự composition. Trong sản phẩm thanh toán thật, cần mô hình số tiền, đơn vị, thuế/phí, quy tắc làm tròn, kiểm soát overflow và validation rõ ràng; không mặc định phép nhân `int` hay cộng phí như ví dụ là thiết kế tài chính đầy đủ.

## 8. Kết hợp với `compose` và `andThen`

Một `Function<T,R>` trong Java có thể được kết hợp với `compose` hoặc `andThen`:

- `f.andThen(g)`: nhận `x`, tính `f(x)` trước rồi truyền kết quả cho `g`.
- `f.compose(g)`: nhận `x`, tính `g(x)` trước rồi truyền kết quả cho `f`.

Đây là **function composition**, khác về bản chất với currying. Nhưng sau khi áp dụng trước đối số để có `Function` một đầu vào, chúng kết hợp rất thuận tiện:

~~~java
Function<Integer, Integer> timesThree = n -> n * 3;
Function<Integer, Integer> plusFive = n -> n + 5;

Function<Integer, Integer> firstMultiply =
        timesThree.andThen(plusFive);
Function<Integer, Integer> firstAdd =
        timesThree.compose(plusFive);

System.out.println(firstMultiply.apply(10)); // 35
System.out.println(firstAdd.apply(10));      // 45
~~~

Vì `andThen`/`compose` truyền **kết quả bước trước** vào bước sau, chúng khác với partial application, vốn cố định **một đối số có sẵn**. Một workflow có thể cần cả hai: đầu tiên cố định cấu hình, rồi phối hợp các phép biến đổi.

### Kết hợp không làm mất side effect

Nếu hàm gốc ghi log hoặc thay đổi trạng thái, một composed function có thể gây nhiều side effect; bước sau ném exception cũng không hoàn tác thay đổi của bước trước. Nếu thứ tự và transaction là quan trọng, đừng coi function composition là cơ chế rollback.

Nếu nhận nhiều hàm từ cấu hình, cân nhắc gọi `Objects.requireNonNull` cho những đối tượng hàm không được phép là `null`. `Function.andThen(null)` và `Function.compose(null)` sẽ ném `NullPointerException` theo hợp đồng Javadoc.

## 9. Khi nào thực sự nên sử dụng?

### 9.1. Tạo hàm chuyên biệt từ cấu hình

Giả sử ứng dụng cần kiểm tra cùng quy tắc với nhiều ngưỡng:

~~~java
BiFunction<Integer, Integer, Boolean> isAtLeast =
        (minimum, value) -> value >= minimum;

Function<Integer, Boolean> atLeast18 =
        value -> isAtLeast.apply(18, value);
~~~

Sau đó `atLeast18.apply(20)` là `true`. Dữ liệu cấu hình `minimum=18` được cố định, các giá trị kiểm tra thay đổi. Có thể sử dụng `Predicate<Integer>` cho kết quả boolean khi thiết kế API phù hợp, không bắt buộc dùng `Function<Integer,Boolean>`.

### 9.2. Tái sử dụng phép biến đổi qua callback

Một hàm `Function<String,String>` đã cố định prefix có thể truyền vào `stream.map(...)`:

~~~java
String prefix = "USER-";
Function<String, String> withPrefix =
        value -> prefix + value;

List<String> names = List.of("A", "B");
List<String> labels = names.stream()
        .map(withPrefix)
        .toList();

System.out.println(labels); // [USER-A, USER-B]
~~~

Đây là mảnh mã trong phương thức có import `java.util.List`, `Function`. Nó minh họa partial application trực tiếp bằng lambda capture. Nếu chỉ có một bước đơn giản như trên, không cần ép thiết kế phải có một helper `curry`.

### 9.3. Dùng currying khi logic ghép từ nhiều bước

Khi một hàm được cấu hình theo tầng (ví dụ tenant → locale → value), currying có thể tạo API dạng:

~~~java
Function<String, Function<String, Function<Integer, String>>> format =
        tenant -> locale -> value ->
                tenant + "/" + locale + ":" + value;

Function<Integer, String> forVietnam =
        format.apply("acme").apply("vi-VN");

System.out.println(forVietnam.apply(5)); // acme/vi-VN:5
~~~

Chuỗi này dễ đọc nếu thứ tự áp dụng phản ánh đúng quy trình cấu hình. Nếu có quá nhiều tầng hoặc tham số dễ bị đảo, đối tượng cấu hình kiểu record hoặc class có tên trường có thể rõ hơn.

### 9.4. Không cần cưỡng ép mọi API thành curried

Với phép toán ít dùng, `BiFunction.apply(a,b)` có thể đơn giản hơn `curried.apply(a).apply(b)`. Nếu tính toán liên quan nhiều trường nghiệp vụ có tên, record `PricingContext`, `RequestOptions` hoặc phương thức có tên mô tả rõ ràng thường dễ bảo trì hơn một chuỗi hàm lồng sâu.

Hãy chọn công cụ theo **mục đích tái sử dụng và khả năng hiểu mã**, không chỉ vì cú pháp trông "functional".

## 10. Lỗi phổ biến và giới hạn của kỹ thuật

| Lỗi/nhầm lẫn | Vì sao không đúng | Cách khắc phục |
| --- | --- | --- |
| Gọi `curried.apply(a,b)` | `Function` chỉ có `apply` một đầu vào | Gọi `curried.apply(a).apply(b)` |
| Gọi `BiFunction.apply(a).apply(b)` | `BiFunction` nhận hai đầu vào trong một lời gọi | Dùng `apply(a,b)` hoặc curry trước |
| Tưởng currying và partial application là một | Một bên biến dạng hàm; bên kia cố định đối số | Phân biệt chữ ký trước/sau |
| Cố định nhầm tham số của phép trừ | Thứ tự tham số quan trọng | Chọn `bindFirst`/`bindSecond` rõ nghĩa |
| Trả nhầm `R` khi hợp đồng cần `Function<B,R>` | Sai kiểu trả về của tầng ngoài | Tầng ngoài phải trả lambda/hàm |
| Gán lại biến local được capture | Vi phạm `final`/effectively final | Tạo biến cấu hình mới, truyền tham số |
| Giả định object đã capture là immutable | Closure có thể giữ tham chiếu mutable | Chụp snapshot/thiết kế immutable khi cần |
| Sử dụng `null` không có hợp đồng | Helper và phép tính gốc có thể ném lỗi ở thời điểm khác nhau | Kiểm tra và nêu rõ chính sách `null` |
| Dùng raw `Function` hoặc cast tùy tiện | Mất type safety, lỗi chuyển kiểu | Giữ generic đầy đủ |
| Mong `andThen` rollback khi bước sau lỗi | Composition không có transaction | Thiết kế xử lý lỗi và transaction riêng |
| Dùng lambda dài, lồng quá nhiều tầng | Khó đọc và debug | Tách phương thức, đặt tên, dùng record/config |
| Dùng kiểu nguyên thủy qua generic quá nhiều | `Integer`/`Long` có boxing/unboxing | Cân nhắc `IntUnaryOperator`/`IntBinaryOperator` và đo khi có yêu cầu hiệu năng |
| Tạo hàm trong vòng lặp mà lẫn biến đếm | Local capture phải effectively final | Tạo biến local mới cho từng lượt lặp |
| Giả định currying luôn lazy | Hàm của tầng đầu có thể thực thi ngay khi được gọi | Xem logic ở từng tầng và thời điểm side effect |

### 10.1. Kiểu đầu vào, suy luận generic và boxing

`Function<Integer,Integer>` dùng đối tượng `Integer`, có thể gây boxing/unboxing khi làm nhiều phép toán nguyên thủy. Nếu yêu cầu hiệu năng cao và chỉ dùng `int`, cân nhắc `IntUnaryOperator` hoặc `IntBinaryOperator`. Tuy nhiên, các interface nguyên thủy không mang tính tổng quát generic như `Function<A,Function<B,R>>`, nên API có thể cần các helper chuyên biệt.

Trình biên dịch thường suy luận `A`, `B`, `R` cho `bindFirst`. Nếu gặp mơ hồ do overload hoặc ràng buộc generic, hãy tách `BiFunction` ra biến có kiểu rõ rồi gọi helper; không chữa bằng raw type hay ép kiểu không an toàn.

### 10.2. Thời điểm xử lý lỗi

Với:

~~~java
Function<Integer, Integer> divideByTen =
        n -> 10 / n;

Function<Integer, Integer> fixed =
        bindFirst((Integer a, Integer b) -> a / b, 10);
~~~

Hai hàm trên đều có thể được tạo thành công. Nếu gọi `apply(0)` thì phép chia sẽ ném `ArithmeticException`. Việc bind trước một đối số không tự kiểm tra hết các đầu vào sẽ dùng trong tương lai. Nếu cần fail-fast đối với cấu hình, hãy validate giá trị ngay ở phương thức factory/helper.

### 10.3. Side effect làm khác biệt giữa các cách tổ chức

Với logic thuần, chuyển `(a,b)->r` thành `a->b->r` giữ kết quả tương ứng. Nhưng nếu một tầng lambda có log, gọi database, tạo timestamp, phát sự kiện hoặc thay đổi object, quá trình gọi từng tầng **có thể thực hiện side effect ở những thời điểm khác nhau**. Phải xác định yêu cầu nghiệp vụ và kiểm thử số lần gọi, không mặc định mọi cách viết hoán đổi được.

### 10.4. Không dùng để tự động cache

`Function<Integer,Integer> plusFive = curriedAdd.apply(5)` giữ `5`, nhưng **không tự ghi nhớ kết quả** cho từng đầu vào tiếp theo. Gọi `plusFive.apply(10)` nhiều lần thường vẫn thực hiện phép tính tương ứng nhiều lần. Currying và partial application **không phải memoization**; caching là một kỹ thuật khác cần thiết kế key, vòng đời, memory và concurrency riêng.

## 11. Kiểm thử kết quả và đặc tính hàm

### 11.1. So sánh dạng gốc với dạng curried

Với một `BiFunction` thuần như cộng hai số, có thể viết:

~~~java
BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;
Function<Integer, Function<Integer, Integer>> c =
        a -> b -> add.apply(a, b);

int a = 2;
int b = 3;
boolean same = add.apply(a, b).equals(c.apply(a).apply(b));
System.out.println(same); // true
~~~

Đây là mã đặt trong phương thức với import phù hợp. So sánh trên một cặp đầu vào chưa chứng minh đúng mọi cặp; cần kiểm thử giá trị âm, `0`, giới hạn `int`, overflow nếu bài toán có yêu cầu, cùng các ràng buộc thực tế.

### 11.2. Kiểm thử thứ tự đối số

Với `subtract(a,b) = a-b`, kiểm tra:

~~~java
BiFunction<Integer, Integer, Integer> subtract =
        (a, b) -> a - b;

Function<Integer, Integer> fromTen =
        b -> subtract.apply(10, b);
Function<Integer, Integer> minusTen =
        a -> subtract.apply(a, 10);

System.out.println(fromTen.apply(3));  // 7
System.out.println(minusTen.apply(3)); // -7
~~~

Nếu helper generic có lỗi đảo `a`/`b`, phép trừ sẽ lộ lỗi dễ hơn phép cộng hoặc nhân. Trong test, chọn **phép toán không giao hoán** là một cách hữu ích để xác minh đúng thứ tự binding.

### 11.3. Kiểm thử side effect

Nếu lambda gốc có counter hoặc log, viết test khẳng định hành động xảy ra **khi gọi đúng tầng**. Việc tạo hàm (factory), áp dụng tham số đầu tiên và gọi hàm cuối có thể là ba thời điểm quan sát khác nhau. Với implementation `curry` ở phần 5, `function.apply(a,b)` chỉ chạy tại tầng cuối; nếu tự thêm logic ở tầng ngoài, hành vi sẽ thay đổi.

## 12. Bài tập thực hành

**Bài 1 — Curry phép nhân.** Tạo `Function<Integer,Function<Integer,Integer>>` tính tích, tạo hàm nhân `7`, rồi gọi với `8`. Kết quả mong đợi `56`. Viết lại bằng `BiFunction<Integer,Integer,Integer>` để so sánh.

**Bài 2 — Partial application không curry.** Cho `BiFunction<Integer,Integer,Integer> subtract = (a,b)->a-b;`. Viết hai hàm `minusTwoFromTen` và `minusTenFrom` bằng cách cố định các vị trí tham số khác nhau. Kiểm tra đầu ra và đặt tên phản ánh đúng thứ tự.

**Bài 3 — Generic helper.** Tự viết `bindFirst` và `bindSecond`, thử với `BiFunction<String,String,String>` nối chuỗi và `BiFunction<Integer,Integer,Integer>` nhân hai số. Giải thích ý nghĩa `Function<B,R>` trong chữ ký của `bindFirst`.

**Bài 4 — Chuyển đổi `curry`/`uncurry`.** Viết generic helper theo phần 5. Chọn một hàm thuần như phép cộng và kiểm tra kết quả của `original.apply(a,b)`, `curry(original).apply(a).apply(b)` và `uncurry(curry(original)).apply(a,b)` trên vài cặp số.

**Bài 5 — Function composition.** Dùng `bindSecond(multiply,3)` để tạo hàm nhân ba, sau đó dùng `andThen(n -> n+5)`. Với `input=10`, kết quả phải là `35`. Đổi sang `compose` để tính `3*(10+5)` và giải thích vì sao thành `45`.

**Bài 6 — Capture đối tượng mutable.** Dùng `StringBuilder` làm prefix cho một lambda; sửa builder sau khi tạo lambda rồi gọi lại. Chuyển sang capture một `String` bất biến để so sánh. Nêu rõ cái gì được capture và tại sao kết quả có thể khác nhau.

**Bài 7 — Tạo API nghiệp vụ.** Viết factory `Function<Integer,Integer> priceWithTax(int taxPercent)` để tính giá cộng thuế theo quy tắc minh họa của riêng bạn. Kiểm tra dữ liệu âm, overflow và quy tắc làm tròn trước khi dùng trong sản phẩm thật. Giải thích vì sao đầu vào `taxPercent` cần được kiểm tra sớm.

**Bài 8 — Nhận diện kỹ thuật.** Với `Function<String,String> prefix = s -> "ID-" + s;`, đây là một hàm chuyên biệt có prefix cố định, nhưng **không bắt buộc** phải được tạo từ currying. Hãy chuyển nó thành dạng `prefix -> value -> prefix + value` và chỉ ra khi nào thực hiện bước partial application.

## 13. Câu hỏi tự kiểm tra

1. **Currying là gì?** Biến hàm nhiều đầu vào thành chuỗi hàm nhận từng đầu vào.
2. **Partial application là gì?** Cố định một phần đối số để tạo hàm còn chờ các đối số khác.
3. **Hai kỹ thuật có giống nhau hoàn toàn không?** Không. Có thể partial-apply trực tiếp một `BiFunction` mà không curry.
4. **`Function<A,Function<B,R>>` được gọi thế nào?** `apply(a).apply(b)`.
5. **`BiFunction<A,B,R>` được gọi thế nào?** `apply(a,b)`.
6. **`bindFirst` trả về kiểu nào?** `Function<B,R>` khi cố định đối số loại `A`.
7. **`bindSecond` trả về kiểu nào?** `Function<A,R>` khi cố định đối số loại `B`.
8. **Hàm đã bind có tự động cache mọi kết quả không?** Không, không có memoization mặc định.
9. **Nếu capture một `ArrayList`/`StringBuilder` mutable thì sao?** Lambda giữ tham chiếu; object có thể tiếp tục thay đổi, và kết quả có thể phụ thuộc thời điểm gọi.
10. **`andThen` có phải currying không?** Không; nó là composition, truyền kết quả giữa hai phép biến đổi.
11. **Có thể bind trước đối số thứ hai của phép trừ không?** Có, bằng lambda hoặc `bindSecond`; không được đảo thứ tự tùy ý.
12. **Tại sao nên kiểm thử hàm không giao hoán?** Để phát hiện sai vị trí tham số đã cố định.

## 14. Tổng kết và tài liệu tham khảo

**Currying** mô tả cấu trúc `(A,B)->R` thành `A -> (B -> R)`. **Partial application** chọn một hoặc nhiều đối số cố định để trả về hàm chuyên biệt. Trong Java, ta có thể sử dụng lambda lồng nhau, `Function<A,Function<B,R>>`, `BiFunction<A,B,R>` cùng helper `bindFirst`/`bindSecond`. Khi nhận được một `Function` một đầu vào, có thể phối hợp với `compose`/`andThen` để xây pipeline.

Để viết code đáng tin cậy, hãy kiểm soát thứ tự tham số, ràng buộc generic, quy tắc capture, `null`, exception, overflow và side effect. Với bài toán đơn giản, lambda rõ nghĩa hoặc phương thức bình thường thường tốt hơn một chuỗi curry dài. Hãy dùng các kỹ thuật này khi chúng thực sự **giúp tái sử dụng hành vi hoặc tách cấu hình khỏi dữ liệu chạy**.

Tài liệu tra cứu chính thức: Javadoc Java SE 17 của `java.util.function.Function`, `BiFunction`, `IntUnaryOperator`, `IntBinaryOperator`; Java Language Specification `15.27 Lambda Expressions` và `4.12.4 final Variables`.
