# Overload mơ hồ với nhiều functional interface trong Java

## 1. Vấn đề: cùng một lambda, nhiều kiểu đích có vẻ hợp lệ

Java cho phép **overload**: nhiều phương thức cùng tên nhưng danh sách kiểu tham số khác nhau. Java cũng cho phép biểu diễn hành vi bằng **lambda expression** và **method reference**, tương thích với một *functional interface* có đúng một phương thức abstract chức năng (SAM). Hai tính năng này kết hợp rất tiện lợi, nhưng đôi khi trình biên dịch không thể quyết định overload nào được gọi.

Ví dụ có hai hợp đồng khác tên nhưng cùng nhận một `String` và trả về `boolean`:

~~~java
@FunctionalInterface
interface NameRule {
    boolean test(String name);
}

@FunctionalInterface
interface NameCheck {
    boolean check(String name);
}
~~~

Và hai overload:

~~~java
static void evaluate(NameRule rule) { /* ... */ }
static void evaluate(NameCheck check) { /* ... */ }
~~~

Lời gọi dưới đây là **mã cố ý không biên dịch**:

~~~java
evaluate(name -> name.length() >= 4);
// Lỗi: lời gọi evaluate(...) bị mơ hồ giữa hai overload.
~~~

Không phải lambda “không có kiểu”; vấn đề là lambda lấy **kiểu đích (target type)** từ ngữ cảnh. Cả `NameRule` và `NameCheck` đều có descriptor tương thích với `(String) -> boolean`, nên cả hai overload đều là ứng viên hợp lệ. Vì chúng là hai interface không liên quan theo kế thừa, compiler không có đủ căn cứ để chọn một phương thức duy nhất.

**Điểm cốt lõi của bài:** khi nhiều overload nhận nhiều functional interface, hãy phân biệt (1) **tương thích với kiểu đích** của mỗi lambda/method reference, (2) **quy tắc chọn phương thức cụ thể nhất**, và (3) **kỹ thuật làm rõ ý định** của caller. Đừng nghĩ rằng Java “luôn chọn overload khai báo trước” hoặc “chọn tên interface giống nội dung lambda hơn”.

Tính năng overload với lambda/method reference đã có từ Java 8, vẫn áp dụng trong Java 17+ và các phiên bản Java hiện đại.

## 2. Ôn lại cơ chế target typing của lambda

Lambda trong Java thường là một *poly expression*: ngữ cảnh mà lambda xuất hiện quyết định kiểu chức năng đích cần kiểm tra. Ví dụ:

~~~java
java.util.function.Predicate<String> nonBlank =
        text -> text != null && !text.isBlank();

java.util.function.Function<String, Integer> length =
        text -> text.length();
~~~

Với `Predicate<String>`, compiler biết `text` có kiểu `String`, và thân phải phù hợp kiểu kết quả `boolean). Với `Function<String,Integer>`, compiler biết đầu vào là `String` và kết quả phải thích hợp cho `Integer`; `text.length()` trả `int` rồi có thể được boxing thành `Integer`.

`String.isBlank()` có từ Java 11; chương trình dùng API này cần JDK phù hợp. Bản thân nguyên tắc target typing của lambda không hề là tính năng lỗi thời.

### Lambda không phải một object có “kiểu giao diện mặc định”

Không tồn tại một interface duy nhất mặc định cho lambda `x -> x > 0`. Tùy ngữ cảnh, nó có thể hướng tới `Predicate<Integer>`, `IntPredicate`, hoặc một interface riêng có descriptor thích hợp. Trình biên dịch không chọn dựa vào tên biến `valid`, `check` hay `filter`, cũng không dựa vào mục đích nghiệp vụ viết trong comment.

Một lambda phải được đặt vào ngữ cảnh có kiểu đích, ví dụ khai báo biến, đối số gọi phương thức, biểu thức ép kiểu hoặc câu lệnh `return` có kiểu xác định.

### SAM descriptor có ý nghĩa gì?

Đối với `Predicate<String>`, descriptor là `(String) -> boolean`; đối với `Function<String,Integer>`, descriptor là `(String) -> Integer` theo kiểu generic được thay thế. Hai interface riêng `NameRule` và `NameCheck` có tên phương thức khác nhau nhưng đều mô tả hành vi một `String` sang `boolean`.

Một lambda **có thể tương thích với nhiều descriptor**. Chính đặc tính này tạo tiền đề cho overload mơ hồ.

## 3. Ba giai đoạn nên hình dung khi đọc lỗi overload

Không cần ghi nhớ toàn bộ đặc tả Java để xử lý phần lớn trường hợp. Có thể suy luận theo ba câu hỏi:

1. **Những overload nào cùng tên và đúng số lượng đối số?** Xác định tập ứng viên. Có xét các phương thức kế thừa, biến thể generic và varargs khi có.
2. **Lambda/method reference có tương thích với từng tham số functional interface hay không?** Xét số lượng tham số SAM, kiểu tham số suy ra hoặc được viết tường minh, hình dạng thân (trả giá trị hay void), kiểu trả về, checked exception và thông tin kiểu đích.
3. **Có một overload cụ thể nhất theo quy tắc Java không?** Quan hệ subtype và các quy tắc tính cụ thể của biểu thức chức năng có thể phân định. Nếu còn nhiều ứng viên phù hợp nhưng không có ứng viên duy nhất thắng, compilation thất bại vì **ambiguous method call**.

Đây là mô hình học tập, không phải thay thế đặc tả JLS. Không nên kết luận “cùng số tham số và đều nhận lambda tức là mơ hồ” — có nhiều trường hợp compiler chọn được nhờ kiểu tham số, hình dạng thân hoặc quan hệ interface.

### Lỗi mơ hồ là lỗi biên dịch

Một lời gọi như `evaluate(s -> s.isEmpty())` khi cả `NameRule` và `NameCheck` đều tương thích thường bị từ chối **trước khi chương trình chạy**. Nó không phải một nhánh runtime thay đổi theo dữ liệu. Việc chạy cùng binary trên máy khác không làm overload tự chọn khác, bởi binary chỉ tồn tại sau khi biên dịch thành công.

## 4. Ví dụ Java hoàn chỉnh 1: hai SAM cùng chữ ký và ba cách giải mơ hồ

Tạo tệp **AmbiguousSamDemo.java**:

~~~java
public class AmbiguousSamDemo {

    @FunctionalInterface
    interface NameRule {
        boolean test(String name);
    }

    @FunctionalInterface
    interface NameCheck {
        boolean check(String name);
    }

    static String evaluate(NameRule rule) {
        return "rule=" + rule.test("Java");
    }

    static String evaluate(NameCheck check) {
        return "check=" + check.check("Java");
    }

    public static void main(String[] args) {
        // evaluate(s -> s.length() >= 4);
        // Dòng trên cố ý comment vì bị ambiguous.

        NameRule longEnough = s -> s.length() >= 4;
        NameCheck startsWithJ = s -> s.startsWith("J");

        System.out.println(evaluate(longEnough));
        System.out.println(evaluate(startsWithJ));

        System.out.println(evaluate(
                (NameRule) (s -> s.endsWith("a"))
        ));

        System.out.println(evaluate(
                (NameCheck) (s -> s.isBlank())
        ));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac AmbiguousSamDemo.java
java AmbiguousSamDemo
~~~

Kết quả dự kiến chính xác:

~~~text
rule=true
check=true
rule=true
check=false
~~~

Giải thích:

- `evaluate(longEnough)` chọn overload nhận `NameRule` vì **biến đã có kiểu NameRule**.
- `evaluate(startsWithJ)` chọn overload nhận `NameCheck`.
- Ép kiểu `(NameRule) (s -> ...)` cung cấp kiểu đích rõ ràng và loại bỏ nhầm lẫn.
- `"Java".isBlank()` là `false`, nên dòng `check=false`; ở đây API `String.isBlank()` cần Java 11+.

### Những cách sửa hợp lệ

**Cách A — Khai báo biến có kiểu tường minh**:

~~~java
NameRule rule = name -> name.length() >= 4;
evaluate(rule);
~~~

**Cách B — Ép kiểu lambda tại call site**:

~~~java
evaluate((NameRule) (name -> name.length() >= 4));
~~~

**Cách C — Đổi tên API** nếu hai overload thực sự có ý nghĩa nghiệp vụ khác nhau, ví dụ `evaluateRule(...)` và `evaluateCheck(...)`. Đây thường là cách tốt nhất cho public API khi người dùng thường xuyên truyền lambda.

Không nên thêm các cast tùy tiện chỉ để ép compiler chấp nhận mà chưa hiểu overload nào phù hợp hợp đồng.

## 5. Interface `Supplier<T>` và `Callable<T>`: khác checked exception nhưng lambda vẫn mơ hồ

Hai interface chuẩn:

~~~java
java.util.function.Supplier<String> supplier = () -> "hello";
java.util.concurrent.Callable<String> callable = () -> "hello";
~~~

Đều có SAM **không nhận tham số và trả `String`** (sau thay kiểu generic). Khác biệt chính là `Callable.call()` khai báo `throws Exception`, còn `Supplier.get()` không khai báo checked exception.

Giả sử overload:

~~~java
static String fetch(Supplier<String> supplier) { /* ... */ }
static String fetch(Callable<String> callable) throws Exception { /* ... */ }
~~~

Lời gọi sau, khi cả hai overload tồn tại, có thể bị mơ hồ:

~~~java
fetch(() -> "hello"); // Mã cố ý không biên dịch: ambiguous.
~~~

Vì thân lambda không ném checked exception, nó **tương thích với cả hai** functional interfaces. Compiler không tự ưu tiên `Supplier` vì ngắn hơn, cũng không tự ưu tiên `Callable` vì có `throws`.

### Ví dụ Java hoàn chỉnh 2: giải bằng kiểu đích

Tạo tệp **SupplierCallableOverloadDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

public class SupplierCallableOverloadDemo {

    static String fetch(Supplier<String> supplier) {
        return "supplier:" + supplier.get();
    }

    static String fetch(Callable<String> callable) throws Exception {
        return "callable:" + callable.call();
    }

    public static void main(String[] args) throws Exception {
        // fetch(() -> "data"); // ambiguous: không biên dịch.

        Supplier<String> supplier = () -> "data";
        Callable<String> callable = () -> "data";

        System.out.println(fetch(supplier));
        System.out.println(fetch(callable));

        System.out.println(fetch((Supplier<String>) () -> "x"));
        System.out.println(fetch((Callable<String>) () -> "y"));
    }
}
~~~

Lệnh chạy:

~~~bash
javac SupplierCallableOverloadDemo.java
java SupplierCallableOverloadDemo
~~~

Stdout:

~~~text
supplier:data
callable:data
supplier:x
callable:y
~~~

**Phân biệt chính sách ngoại lệ:** việc `main` khai báo `throws Exception` là do overload `Callable`; nó không có tác dụng lựa chọn overload cho lời gọi `fetch(() -> "data")`. Với `Supplier`, lambda không thể để một checked exception chưa xử lý thoát ra từ `get()`. Với `Callable`, lambda có thể khai báo/để lan truyền checked exception phù hợp; đây là một khác biệt hợp đồng cần cân nhắc khi thiết kế API.

**Thiết kế thực tế:** nếu API cho cả hai biến thể `Supplier` và `Callable`, nên dùng hai tên thể hiện có checked exception hay không, hoặc yêu cầu caller cung cấp một biến được định kiểu rõ. Đừng gây áp lực để người dùng phải cast mọi lambda.

## 6. Hình dạng thân lambda có thể loại bớt overload

Không phải mọi overload chứa functional interface đều mơ hồ. Với lambda không nhận tham số, thân được phân loại theo việc **tương thích với hàm trả `void`** hay **trả một giá trị**.

Xét hai overload:

~~~java
static void perform(Runnable runnable) { /* ... */ }
static void perform(java.util.function.Supplier<String> supplier) {
    /* ... */
}
~~~

Lời gọi sau chọn `Runnable`:

~~~java
perform(() -> {
    System.out.println("running");
});
~~~

Thân block này kết thúc bình thường, không trả giá trị; nó phù hợp `void run()`, **không** phù hợp `String get()`.

Lời gọi sau chọn `Supplier<String>`:

~~~java
perform(() -> "result");
~~~

Biểu thức `"result"` là một **String literal**, không phải *statement expression* được dùng làm lệnh Java độc lập. Vì vậy lambda này trả một giá trị thích hợp cho `Supplier<String>` chứ không phù hợp với `Runnable`.

### Nhưng expression body có thể vừa void-compatible vừa value-compatible

Một **method invocation expression** như `doSomething()` được phép đứng một mình thành một statement trong Java, kể cả khi nó trả kết quả. Lambda:

~~~java
() -> computeText()
~~~

có thể tương thích với SAM trả `void` (bỏ qua kết quả) **hoặc** SAM trả `String` (giữ kết quả), nếu `computeText()` trả `String` và các kiểu tham số khác phù hợp. Khi overload có cả `Runnable` và `Supplier<String>`, điều này có thể tạo ra ambiguity.

Để chỉ rõ ý định:

~~~java
perform(() -> {
    computeText(); // Dạng void-compatible: kết quả bị bỏ qua
});
~~~

Hoặc:

~~~java
perform(() -> {
    return computeText(); // Dạng value-compatible: trả String
});
~~~

Hai ví dụ dùng `perform` và `computeText` là **mảnh mã minh họa**; cần định nghĩa method trước khi chạy. Phân biệt này rất quan trọng: **“phương thức gọi bên trong có kiểu trả về” không tự động bảo đảm overload chọn interface trả về giá trị**.

### Quy tắc cho block lambda

- `(x) -> { doWork(x); }` là void-compatible nếu block có thể kết thúc bình thường và không có `return value;`.
- `(x) -> { return transform(x); }` là value-compatible nếu mọi nhánh cần thiết trả kết quả phù hợp.
- Một block dùng `return;` không trả giá trị chỉ tương thích SAM void ở các trường hợp phù hợp.
- Trong biểu thức ngắn, `x -> x.length()` là method invocation expression; nó có thể được điều chỉnh để bỏ qua giá trị khi SAM yêu cầu void, tùy overload cụ thể.

Trình biên dịch kiểm tra cú pháp và tính phù hợp kiểu, không “đoán” mục đích nghiệp vụ của lời gọi.

## 7. Ví dụ Java hoàn chỉnh 3: chọn overload nhờ hình dạng lambda

Tạo tệp **LambdaBodyShapeDemo.java**:

~~~java
import java.util.function.Supplier;

public class LambdaBodyShapeDemo {

    static void perform(Runnable action) {
        System.out.print("runnable:");
        action.run();
    }

    static void perform(Supplier<String> supplier) {
        System.out.println("supplier:" + supplier.get());
    }

    static String compute() {
        return "value";
    }

    public static void main(String[] args) {
        perform(() -> {
            System.out.println("done");
        });

        perform(() -> "literal");

        perform(() -> {
            compute();
        });

        perform(() -> {
            return compute();
        });

        // perform(() -> compute());
        // Dòng trên để comment để tránh overload ambiguous.
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac LambdaBodyShapeDemo.java
java LambdaBodyShapeDemo
~~~

Stdout:

~~~text
runnable:done
supplier:literal
runnable:supplier:value
~~~

**Giải thích cần đọc cẩn thận:** Chương trình thực sự có **bốn** lời gọi `perform`; hai lời gọi `Runnable` và hai lời gọi `Supplier`. Vì `perform(Runnable)` dùng `System.out.print` trước `action.run()`, đoạn `perform(() -> { compute(); })` chỉ in `runnable:` rồi **không xuống dòng**; ngay sau đó, overload `Supplier` của lời gọi thứ tư in `supplier:value` trên cùng dòng. Do đó stdout có ba dòng như trên.

Để dễ theo dõi trong hệ thống sản xuất, nên tránh logging không có newline như ví dụ này; ở đây nó nhấn mạnh rằng stdout phải dựa vào lệnh in thực tế, không dựa vào số lượt gọi.

**Lưu ý về comment mơ hồ:** `() -> compute()` là expression lambda với method invocation, phù hợp để bỏ qua hoặc sử dụng `String` trả về, do đó có thể khiến hai overload không xác định được ứng viên tốt nhất.

## 8. Method reference cũng phụ thuộc target type

Method reference như `String::trim`, `String::length` hoặc `Integer::parseInt` không mang một kiểu functional interface duy nhất từ trước. Khi gán:

~~~java
java.util.function.Function<String, String> trimmed =
        String::trim;
~~~

compiler dùng descriptor `(String) -> String` để hiểu `String` là receiver và `trim()` trả `String`.

Một method reference đôi khi cũng tương thích nhiều functional interfaces. Ví dụ, `String::trim` có thể dùng cho một `Consumer<String>` có SAM trả void (kết quả `trim()` được bỏ qua), cũng có thể dùng cho `Function<String,String>` có SAM trả `String`. Vì vậy overload nhận hai interface không liên quan có thể mơ hồ nếu truyền method reference trực tiếp.

~~~java
// Hai overload giả định:
static void handle(java.util.function.Consumer<String> action) { /*...*/ }
static void handle(java.util.function.Function<String,String> map) { /*...*/ }

// Có thể mơ hồ:
handle(String::trim);
~~~

Đây là mảnh mã minh họa, không phải chương trình standalone.

### Cách làm rõ method reference

~~~java
java.util.function.Consumer<String> sideEffect = String::trim;
java.util.function.Function<String,String> transform = String::trim;

handle(sideEffect);
handle(transform);
~~~

**Chú ý ý nghĩa:** Dùng `String::trim` làm `Consumer<String>` chỉ thực thi phép trim và bỏ đi `String` kết quả; vì `String` là immutable nên nó **không sửa chuỗi gốc**. Phần lớn tác vụ chuẩn hóa thật sự nên chọn `Function<String,String>` và dùng kết quả, không sử dụng `Consumer` như cách “biến đổi tại chỗ”.

### Method reference overload bên trong cũng cần phân giải

Một kiểu có thể khai báo nhiều phương thức cùng tên. Ví dụ `Integer.valueOf` có overload nhận `String` và nhận `int`. Khi gán:

~~~java
java.util.function.Function<String,Integer> fromText =
        Integer::valueOf;
java.util.function.IntFunction<Integer> fromInt =
        Integer::valueOf;
~~~

Kiểu đích dẫn compiler tới overload của `valueOf` phù hợp với tham số. Khi thông tin kiểu đích không đủ, một method reference có thể khiến lời gọi overload ở lớp ngoài bị mơ hồ hoặc không áp dụng được. Đừng kết luận mọi method reference đều được phân giải hoàn toàn trước khi compiler xem xét ngữ cảnh.

## 9. Trường hợp không mơ hồ: một kiểu là subtype của kiểu kia

Ví dụ `UnaryOperator<T>` **extends** `Function<T,T>`; hai interface có quan hệ kế thừa. Với các chữ ký phù hợp:

~~~java
static void process(java.util.function.Function<String,String> f) {
    /* ... */
}

static void process(java.util.function.UnaryOperator<String> f) {
    /* ... */
}
~~~

Do `UnaryOperator<String>` là subtype của `Function<String,String>`, overload nhận `UnaryOperator<String>` có thể được xem là cụ thể hơn khi cả hai cùng áp dụng. Không nên khẳng định “cứ có hai functional interfaces là ambiguous”.

Đây là mảnh mã minh họa, không phải lời khuyên tạo các overload na ná nhau. Hai overload kiểu cha/con vẫn có thể khó đọc, nhất là khi mở rộng API thêm chữ ký hoặc generic về sau.

**Nguyên tắc:** quan hệ subtype có thể cung cấp thứ tự ưu tiên theo quy tắc chọn overload. Khi hai interface không liên quan và đều tương thích, compiler thường thiếu một lựa chọn duy nhất.

### Một lambda chỉ tương thích với một interface

Giả sử có:

~~~java
static void select(java.util.function.Predicate<String> rule) { /*...*/ }
static void select(java.util.function.Function<String,Integer> mapper) {
    /*...*/
}
~~~

Lambda `s -> s.isEmpty()` trả `boolean`, không trả `Integer`, nên không tương thích với `Function<String,Integer>` (trong ngữ cảnh này). Overload `Predicate<String>` là lựa chọn tương thích.

Lambda `s -> s.length()` trả `int` có thể boxing thành `Integer`, nhưng không phù hợp `boolean`; do đó chọn `Function<String,Integer>`.

Ví dụ này chứng tỏ **hai overload nhận functional interfaces không nhất thiết tạo lỗi mơ hồ**. Thứ tự lựa chọn được quyết định bằng chữ ký và khả năng chuyển kiểu, không phải compiler ưu ái `Predicate` hay `Function`.

## 10. Explicit lambda parameter type có giải quyết được không?

Có khi **có**, có khi **không**. Ví dụ overload:

~~~java
@FunctionalInterface
interface TextConsumer {
    void accept(String s);
}

@FunctionalInterface
interface NumberConsumer {
    void accept(Integer n);
}

static void inspect(TextConsumer c) { /*...*/ }
static void inspect(NumberConsumer c) { /*...*/ }
~~~

Khi viết:

~~~java
inspect((String s) -> {
    System.out.println(s.length());
});
~~~

Khai báo `String s` tường minh loại ứng viên có tham số `Integer`. Điều này có thể giải quyết overload. Nhưng đối với `NameRule` và `NameCheck` trong phần 1, **cả hai SAM đều nhận String**, nên viết:

~~~java
evaluate((String s) -> s.length() >= 4);
~~~

vẫn không phân biệt được hai overload. Cần cast tới **interface cụ thể**, gán biến có kiểu rõ hoặc đổi tên API.

### Có nên luôn viết kiểu tham số trong lambda?

Không cần. Java suy luận kiểu tốt khi ngữ cảnh rõ. Kiểu tường minh có lợi khi cần tăng khả năng đọc hoặc phân biệt các overload có parameter types khác nhau. Nó **không thay thế** được việc giải quyết những interface có cùng functional descriptor.

Từ Java 11, cú pháp `var` trong tham số lambda được hỗ trợ, ví dụ `(var s) -> s.length()`, nhưng `var` không tự biến một lời gọi overload ambiguous thành lời gọi rõ ràng nếu cả hai target types vẫn hợp lệ. Trong Java 8, không có cú pháp `var` ở tham số lambda; những ví dụ Java 17 ở đây không dùng `var` để tránh thêm ràng buộc không cần thiết.

## 11. Tránh nhầm “overload mơ hồ” với “trùng erasure”

Không phải mọi chữ ký khác nhau ở generic type argument đều tạo thành hai overload hợp lệ.

Ví dụ **cố ý không biên dịch**:

~~~java
static void filter(java.util.function.Predicate<String> a) { }
static void filter(java.util.function.Predicate<Integer> b) { }
~~~

Hai phương thức có cùng tên và cùng **erasure** của tham số, là `Predicate`. Java không cho khai báo cả hai vì **name clash** sau type erasure. Đây là lỗi khai báo overload, **không phải** lỗi chọn giữa hai overload tại lời gọi lambda.

Muốn phân biệt một predicate cho String và một predicate cho Integer, có thể:

- Đổi tên phương thức như `filterNames`, `filterNumbers`.
- Tạo một phương thức generic duy nhất nếu hợp đồng thực sự thống nhất.
- Thêm tham số định danh kiểu/hợp đồng rõ ràng khi thật sự cần một API chung, nhưng tránh thiết kế rườm rà.

**Đặc biệt:** `Function<String,String>` và `Function<Integer,Integer>` cũng có cùng erased type `Function`. Không dùng kiểu generic arguments khác nhau để “qua mặt” quy tắc overloading của Java.

### Overload theo return type là bất hợp lệ

Hai phương thức chỉ khác **kiểu trả về** nhưng có cùng tên và danh sách tham số không thể cùng tồn tại:

~~~java
// Cố ý KHÔNG biên dịch:
static String parse(String text) { return text; }
static Integer parse(String text) { return text.length(); }
~~~

Return type không phải yếu tố đủ để định nghĩa hai method signatures khác nhau. Đừng cố giải quyết overload ambiguity bằng cách chỉ đổi kiểu trả về của hai overload.

## 12. Return-type preference và những trường hợp cần thận trọng

Quy tắc “cụ thể nhất” của Java bao gồm một số trường hợp đặc biệt đối với kiểu trả về của functional interface, kiểu primitive/reference và lambda hoặc method reference. Vì vậy:

- Không thể suy ra mơ hồ chỉ từ việc hai interface **không có quan hệ subtype**.
- Không thể khẳng định compiler chọn overload chỉ vì một method trả `int` còn method khác trả `Integer`.
- Không thể dự đoán một lời gọi lambda phức tạp bằng cách nhìn riêng tên functional interface.
- Khi có overload generic, biểu thức kết hợp overload, method references overloaded hoặc chuyển đổi boxing/unboxing, cần kiểm tra compiler của JDK mục tiêu với ví dụ tối giản.

Nếu đang phân tích trường hợp rắc rối, hãy dựng một class nhỏ chỉ giữ **hai overload**, đúng lambda/method reference gây lỗi, đúng version Java dự án, rồi biên dịch. Trình biên dịch cung cấp chẩn đoán chính xác hơn việc đoán quy tắc dựa trên trực giác từ vài ví dụ đơn giản.

**Không dùng cast thô để tránh lỗi:** ví dụ `(Predicate) lambda` xóa thông tin generic và có thể gây unchecked warning hoặc rủi ro runtime. Hãy cast tới một **parameterized functional interface** cụ thể khi cần.

## 13. Giải mơ hồ an toàn: chọn đúng kỹ thuật theo ngữ cảnh

| Tình huống | Kỹ thuật ưu tiên | Vì sao |
| --- | --- | --- |
| Hai SAM unrelated cùng descriptor | Gán biến có interface type hoặc cast lambda | Cung cấp target type trực tiếp |
| API do bạn quản lý có hai overload rất gần nhau | Đổi tên các method | Call site dễ đọc, giảm gánh nặng cast |
| Hai SAM khác kiểu tham số | Viết kiểu tham số lambda tường minh nếu giúp chọn | Loại overload không tương thích |
| Một SAM `void`, một SAM có kết quả | Chọn block void hoặc value-return phù hợp | Làm rõ hình dạng callback |
| Cần checked exception | Thiết kế interface nhận checked exception hoặc chọn `Callable` rõ ràng | Hợp đồng lỗi đúng |
| Method reference trùng nhiều target types | Gán typed variable trước khi truyền | Tránh phỏng đoán overload |
| Hai overload chỉ khác generic argument cùng erasure | Đổi tên hoặc thiết kế lại API | Khai báo overload không hợp lệ |
| Nhiều overload mà caller thường xuyên phải cast | Rà soát API thay vì thêm cast | Tối ưu tính dễ dùng dài hạn |

### Khi nào cast có lợi?

Cast là giải pháp cục bộ, minh bạch cho một call site:

~~~java
runTask((java.util.concurrent.Callable<String>) () -> "ok");
~~~

Mảnh mã trên giả định `runTask` có overload nhận `Callable<String>`. Nó nói rõ muốn hợp đồng `Callable`. Tuy nhiên, việc cast không tự làm thân lambda an toàn, không xử lý ngoại lệ giùm caller và không đảm bảo interface đó phù hợp ý nghĩa nghiệp vụ.

### Khi nào typed variable tốt hơn?

Nếu callback dùng nhiều nơi hoặc cần test riêng:

~~~java
java.util.function.Supplier<String> createMessage =
        () -> "hello";
String message = createMessage.get();
~~~

Biến có tên giúp cả người đọc lẫn compiler hiểu lựa chọn. Đối với một lời gọi duy nhất, cast có thể gọn; đối với public API phức tạp, tên phương thức rõ nghĩa thường tốt hơn cả hai.

## 14. Checked exception, `null` và các trường hợp biên

### 14.1. Checked exception không nên bị giấu bởi overload

`Runnable.run()` không khai báo checked exception, `Supplier.get()` cũng không; `Callable.call()` khai báo `throws Exception`. Lambda chứa thao tác I/O có `IOException` có thể yêu cầu hợp đồng cho phép checked exception hoặc phải xử lý lỗi ngay trong lambda.

Không nên chuyển một lambda đang thực hiện thao tác có thể thất bại thành `Supplier` chỉ để “giảm lỗi compiler” rồi nuốt `IOException` và trả giá trị giả. Hãy định nghĩa rõ API làm gì với thất bại: truyền exception, trả kiểu kết quả chứa lỗi, retry theo chính sách, hay dừng thực thi.

### 14.2. `null` đối số cũng có thể gây overload ambiguity

Nếu hai overload đều nhận interface reference không liên quan:

~~~java
static void evaluate(NameRule rule) { /*...*/ }
static void evaluate(NameCheck check) { /*...*/ }
~~~

Thì:

~~~java
evaluate(null); // Mơ hồ: null có thể chuyển sang cả hai kiểu reference.
~~~

Cast `evaluate((NameRule) null)` có thể làm compiler chọn overload, nhưng nếu method gọi `rule.test(...)` thì **vẫn NPE ở runtime**. Cast giải quyết chọn chữ ký, **không** làm `null` trở thành callback hợp lệ.

Nếu API không chấp nhận callback null, kiểm tra `Objects.requireNonNull` ở ranh giới và nêu rõ hợp đồng.

### 14.3. Các method có cùng tên nhưng số tham số khác nhau

Nếu `evaluate(NameRule)` và `evaluate(NameRule,String)`, lời gọi một đối số thường không mơ hồ về số tham số. Phạm vi overload được giới hạn trước khi xét kiểu SAM; đừng gán tất cả lỗi lambda cho “có hai functional interface”.

### 14.4. Constructor method reference

`ArrayList::new` có thể hướng tới `Supplier<ArrayList<T>>` (constructor không tham số) hoặc `IntFunction<ArrayList<T>>` (constructor nhận capacity `int`). Nhưng kiểu SAM có số tham số khác nhau, nên một số overload có thể được phân biệt nhờ số lượng tham số cần cho callback.

Trong trường hợp constructor overload nhiều kiểu đầu vào, method reference resolution vẫn phụ thuộc target type và có thể phức tạp. Khi cần rõ ràng, dùng typed variable hoặc lambda với tham số khai báo tường minh.

## 15. Ví dụ Java hoàn chỉnh 4: thiết kế lại API để caller không phải cast

Đôi khi giải pháp đúng nhất không phải sửa lambda, mà là **đặt tên phương thức theo hợp đồng**.

Tạo tệp **NamedCallbackApiDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

public class NamedCallbackApiDemo {

    static String getUnchecked(Supplier<String> supplier) {
        return "unchecked:" + supplier.get();
    }

    static String getChecked(Callable<String> callable) throws Exception {
        return "checked:" + callable.call();
    }

    @FunctionalInterface
    interface TextValidator {
        boolean valid(String value);
    }

    static boolean validateText(
            String input, TextValidator validator) {
        return validator.valid(input);
    }

    static String transformText(
            String input, java.util.function.Function<String,String> mapper) {
        return mapper.apply(input);
    }

    public static void main(String[] args) throws Exception {
        System.out.println(getUnchecked(() -> "A"));
        System.out.println(getChecked(() -> "B"));

        System.out.println(
                validateText("Java", s -> s.length() >= 4)
        );
        System.out.println(
                transformText(" java ", String::trim)
        );
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NamedCallbackApiDemo.java
java NamedCallbackApiDemo
~~~

Stdout:

~~~text
unchecked:A
checked:B
true
java
~~~

Các tên `getUnchecked` và `getChecked` chỉ là tên minh họa cho **khác biệt checked-exception contract**, không có nghĩa việc chạy `Supplier` không thể gặp unchecked exception. `getUnchecked` vẫn có thể ném `RuntimeException` hoặc `Error` tùy callback.

Việc tách `validateText` và `transformText` phản ánh hai hành vi khác nhau: trả kết quả kiểm tra hay tạo dữ liệu mới. Khi tên method rõ nghĩa, code client ít phải dựa vào mẹo ép kiểu để chọn đúng overload.

## 16. Trình tự debug lỗi “reference to ... is ambiguous”

Khi IDE hoặc `javac` báo ambiguous với lambda/method reference, nên làm tuần tự:

1. **Ghi lại chính xác call site** gây lỗi, bao gồm biểu thức lambda, method reference và tất cả các tham số khác.
2. **Tìm các overload khả dụng** của tên method (trong cùng class, class cha và các nơi liên quan) và đối chiếu arity, generic/varargs.
3. **Xác định target functional descriptor** của từng candidate (số tham số, kiểu tham số, kiểu trả về, checked exception).
4. **Đánh dấu ứng viên tương thích** với biểu thức. Nhớ rằng method invocation expression có thể vừa void-compatible vừa value-compatible.
5. **Kiểm tra quan hệ subtype và độ cụ thể**; không mặc định hai interface khác nhau là mơ hồ.
6. **Gán lambda/method reference vào một biến có kiểu** đúng overload mong muốn, hoặc cast tường minh và kiểm tra compiler.
7. **Chạy test về hành vi**, đặc biệt nếu hai overload có logic hoặc quy tắc ngoại lệ khác nhau.
8. **Rà soát thiết kế API**, nhất là public API yêu cầu người dùng cast quá nhiều lần.
9. **Thử với JDK mục tiêu**, không sử dụng đặc điểm cú pháp/API mới hơn phiên bản dự án mà không ghi rõ.

Ví dụ chẩn đoán thường có nội dung gần như:

~~~text
reference to evaluate is ambiguous
both method evaluate(NameRule) and method evaluate(NameCheck) match
~~~

Đây là **minh họa dạng thông báo**, không cam kết bản văn giống nhau giữa các JDK hoặc IDE.

## 17. Lỗi phổ biến và cách tránh

| Ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Hai functional interface cùng descriptor sẽ được Java tự chọn theo tên.” | Tên SAM không tạo ưu tiên overload | Gán biến/cast hoặc đổi API |
| “Lambda có một kiểu cố định ngay khi viết.” | Lambda phụ thuộc target typing | Xem ngữ cảnh, chữ ký overload |
| “Có hai functional interfaces là chắc chắn ambiguous.” | Compiler còn xét tương thích và most specific | Kiểm tra từng candidate |
| “`Supplier` luôn ưu tiên hơn `Callable` vì không throws.” | Checked-exception declaration không tự tạo thứ tự ưu tiên | Chọn hợp đồng tường minh |
| “`() -> methodReturningString()` chỉ có thể là Supplier.” | Method invocation expression có thể void-compatible | Dùng block/typed variable |
| “`(String s) -> ...` luôn giải quyết mơ hồ.” | Không giúp khi cả hai SAM cùng nhận String | Cast tới interface |
| “`Predicate<String>` và `Predicate<Integer>` là hai overload hợp lệ.” | Trùng erased signature | Đổi tên hoặc generic method |
| “Chỉ sửa kiểu trả về của overload là đủ.” | Không overload chỉ theo return type | Sửa tham số hoặc tên |
| “Cast lambda cũng xử lý null/exception.” | Cast chỉ chọn kiểu đích | Xử lý runtime contract riêng |
| “Method reference không cần target type.” | Method reference cũng là poly expression | Cung cấp functional interface rõ |
| “Compiler chọn overload theo thứ tự viết trong file.” | Thứ tự khai báo không có ưu tiên | Dựa vào quy tắc overload |
| “Các interface khác nhau luôn là các hợp đồng tương đương.” | Tên/exception/ý nghĩa nghiệp vụ có thể khác nhau | Chọn đúng API theo trách nhiệm |

## 18. Bài tập thực hành

**Bài 1 — Hai SAM tương đương.** Tạo interface `PositiveRule` và `PositiveCheck`, đều có SAM `boolean ... (int n)`. Viết hai overload `test(...)` và gọi `test(n -> n > 0)`. Dự đoán lỗi biên dịch, rồi giải bằng typed variable và cast. Giải thích tại sao đổi tên phương thức abstract trong interface **không** giúp chọn overload.

**Bài 2 — Supplier và Callable.** Viết hai overload nhận `Supplier<Integer>` và `Callable<Integer>`. Kiểm tra `() -> 42` và giải bằng biến có kiểu. Tạo một lambda có `IOException` checked và suy nghĩ hợp đồng nào cho phép chuyển lỗi lên caller. Không biến lỗi I/O thành giá trị 0 nếu không được yêu cầu.

**Bài 3 — Shape của thân lambda.** Với overload `perform(Runnable)` và `perform(Supplier<String>)`, thử lần lượt: `() -> "abc"`, `() -> System.out.println("x")`, `() -> compute()` khi `compute()` trả String, `() -> { compute(); }`, `() -> { return compute(); }`. Phân loại tương thích void/value và chỗ nào có thể mơ hồ.

**Bài 4 — Kiểu tham số tường minh.** Tạo hai SAM với tham số `String` và `Integer`. Viết `(String s) -> System.out.println(s)` và giải thích ứng viên nào còn phù hợp. Sau đó đổi cả hai SAM về tham số String và kiểm tra xem kiểu tham số tường minh còn phân biệt được không.

**Bài 5 — Name clash.** Thử khai báo hai `filter(Predicate<String>)` và `filter(Predicate<Integer>)`. Đọc lỗi compiler về erasure, rồi thiết kế một giải pháp bằng method generic duy nhất hoặc tên method khác.

**Bài 6 — API dễ dùng.** Bạn sở hữu thư viện với `onSuccess(Consumer<String>)` và `onSuccess(Function<String,String>)`. Hãy phân tích mục tiêu thực tế, đề xuất tên `observeSuccess` cho callback tác động phụ và `mapSuccess` cho biến đổi; kiểm tra liệu overload ban đầu có làm người dùng phải cast method reference hay không.

**Bài 7 — Most specific.** So sánh `Function<String,String>` với subtype `UnaryOperator<String>`. Giải thích tại sao quan hệ kế thừa khiến đây không giống cặp `Supplier<String>` và `Callable<String>`. Thử viết ví dụ tối giản rồi biên dịch để kiểm tra overload được chọn.

## 19. Checklist khi code review

- Các phương thức cùng tên có **functional interface params** với descriptor trùng hoặc gần trùng không?
- Có khả năng lambda/method reference không chỉ có một target type phù hợp không?
- Các interface này có quan hệ subtype hay hoàn toàn unrelated?
- Thân lambda có phải method invocation có thể tương thích cả `void` và value-return không?
- Có thể dùng typed variable hoặc cast parameterized interface mà không làm mờ ý nghĩa không?
- Có đang nhầm với erasure clash hoặc overload chỉ khác kiểu trả về không?
- Checked exception có ảnh hưởng thiết kế API và xử lý lỗi đúng chỗ chưa?
- Public API có nên đổi tên để caller không cần suy luận phức tạp không?
- Test có bao phủ hành vi của overload đã chọn không?
- JDK mục tiêu đã rõ, và các API/cú pháp đang dùng có còn được hỗ trợ hiện nay không?

## 20. Tóm tắt

- **Overload mơ hồ với nhiều functional interface** xảy ra khi lambda hoặc method reference tương thích với nhiều chữ ký mà compiler không xác định được overload duy nhất cụ thể nhất.
- **Target typing** là chìa khóa: cùng một lambda có thể được phân tích theo những SAM descriptors khác nhau, và tên của interface hay tên của method abstract không phải tiêu chí chọn overload.
- Hai SAM unrelated cùng descriptor dễ gây mơ hồ; `Supplier<T>` và `Callable<T>` là ví dụ thực tế. Nhưng compiler có thể phân biệt khi shape, kiểu tham số/kết quả hoặc quan hệ subtype đủ rõ.
- Giải pháp cục bộ là **typed variable**, **cast đến interface cụ thể**, hoặc **khai báo kiểu tham số lambda** khi nó thực sự loại ứng viên. Giải pháp dài hạn cho API khó dùng là **đặt tên phương thức khác nhau** theo hợp đồng.
- Phải phân biệt lỗi **ambiguous invocation** với lỗi **name clash do type erasure**; không che giấu checked exception, null hoặc mục đích nghiệp vụ chỉ để làm code biên dịch.
