# Kiểu trả về, `return` và tương thích `void` trong Java Lambda

Lambda là một cách cài đặt hành vi cho **functional interface** (giao diện có một phương thức trừu tượng). Khi viết lambda, ta không khai báo kiểu trả về như một phương thức thông thường: **kiểu trả về được xác định bởi phương thức trừu tượng của functional interface đích**, còn phần thân lambda phải tương thích với kiểu đó. Vì vậy cùng một lời gọi phương thức trả về giá trị có thể dùng trong lambda của `Function` để **giữ** kết quả hoặc trong lambda của `Consumer` để **bỏ** kết quả, tùy cách viết.

Bài này đi sâu vào ba điểm có quan hệ trực tiếp: (1) Java xác định kiểu trả về của lambda theo *target typing*; (2) dùng `return` trong phần thân biểu thức và phần thân khối thế nào; (3) thế nào là *void-compatible* và *value-compatible*, đặc biệt với các biểu thức vẫn trả về giá trị nhưng kết quả bị bỏ qua. Đây là những quy tắc của Java Language Specification (JLS) vẫn áp dụng cho các bản Java hiện đại.

## 1. Lambda không tự mang một kiểu trả về độc lập

Định dạng tổng quát:

~~~java
(parameters) -> expression
(parameters) -> { statements; }
~~~

`parameters` mô tả tham số, còn phần sau dấu `->` là một biểu thức (*expression body*) hoặc một khối lệnh (*block body*). Lambda được gán hoặc truyền vào một **target type** là functional interface; chữ ký của phương thức trừu tượng trong giao diện đó quy định số tham số, kiểu tham số và kiểu kết quả mà lambda phải tương thích.

Ví dụ các interface chuẩn còn được dùng rất phổ biến:

| Target type | Phương thức chức năng | Kết quả mà lambda phải tương thích | Ví dụ sử dụng |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `void` | Thực thi công việc không trả kết quả |
| `Consumer<T>` | `void accept(T value)` | `void` | Ghi log, gửi thông báo, cập nhật bộ gom |
| `BiConsumer<T,U>` | `void accept(T t, U u)` | `void` | Nhận hai giá trị để thực hiện thao tác |
| `Supplier<T>` | `T get()` | Giá trị `T` | Tạo/lấy một giá trị khi được gọi |
| `Function<T,R>` | `R apply(T t)` | Giá trị `R` | Ánh xạ dữ liệu |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | Giá trị `R` | Tính kết quả từ hai tham số |
| `Predicate<T>` | `boolean test(T t)` | `boolean` | Điều kiện lọc |
| `UnaryOperator<T>` | `T apply(T t)` | Giá trị cùng kiểu `T` | Biến đổi giá trị cùng kiểu |
| `IntConsumer` | `void accept(int value)` | `void` | Nhận `int`, tránh boxing khi phù hợp |
| `IntUnaryOperator` | `int applyAsInt(int value)` | `int` | Biến đổi `int` không cần boxing |

Các kiểu này chỉ là ví dụ; với functional interface tự định nghĩa, Java vẫn áp dụng cùng quy tắc. `@FunctionalInterface` là annotation giúp trình biên dịch kiểm tra giao diện thực sự đáp ứng hợp đồng, nhưng lambda tương thích với một giao diện chức năng hợp lệ dù annotation đó không được ghi.

~~~java
Function<Integer, Integer> doubleValue = n -> n * 2;
Consumer<Integer> printValue = n -> System.out.println(n);
Supplier<String> status = () -> "READY";
Predicate<Integer> positive = n -> n > 0;
~~~

Đây là **đoạn code minh họa đặt bên trong phương thức**; cần import `java.util.function.*`. Ở dòng đầu, vì `Function<Integer,Integer>` có `apply` trả `Integer`, phép tính `n * 2` được quy đổi kết quả về `Integer` bằng boxing khi cần. Dòng thứ hai phải tương thích với `Consumer.accept` trả `void`; dòng thứ ba trả `String`; dòng cuối trả `boolean`.

**Không có cú pháp khai báo kiểu trả về trên lambda** như `(int n) -> int { ... }`. Nếu muốn giao diện chức năng trả kiểu nào, hãy chọn/định nghĩa target type tương ứng. Tương tự, không thể viết `var f = n -> n * 2;` khi lambda đứng một mình vì `var` không cung cấp target functional interface để suy diễn.

## 2. Hai dạng thân lambda và cách dùng `return`

### 2.1. Expression body: kết quả là giá trị của biểu thức

~~~java
Function<Integer, Integer> square = n -> n * n;
Predicate<String> notEmpty = s -> !s.isEmpty();
Supplier<String> message = () -> "OK";
~~~

Với target trả giá trị, biểu thức bên phải `->` chính là kết quả; **không viết `return` trong expression body**. Trong lambda `n -> n * n`, Java tự dùng giá trị tính được để đáp ứng phương thức `apply`.

Muốn dùng `return`, phải chuyển sang block body:

~~~java
Function<Integer, Integer> square = n -> {
    return n * n;
};
~~~

Hai cách có cùng ý nghĩa ở ví dụ này. Dấu `;` sau dấu `}` đóng vai trò kết thúc câu lệnh gán biến, không phải dấu kết thúc một câu lệnh `return` ở ngoài lambda.

### 2.2. Block body: phải trả về đúng cách theo target type

Với target trả **giá trị**, block có thể có nhiều câu lệnh và nhánh điều kiện, nhưng các đường đi có thể hoàn thành bình thường không được “rơi” ra cuối block mà không có kết quả. Nhánh có thể kết thúc bằng `return expression;` hoặc ném ngoại lệ theo nghiệp vụ.

~~~java
Function<Integer, String> grade = score -> {
    if (score >= 60) {
        return "PASS";
    }
    return "RETRY";
};
~~~

Với target trả **void**, có thể để block kết thúc tự nhiên hoặc dùng `return;` nhằm thoát sớm khỏi lambda:

~~~java
Consumer<String> printIfPresent = input -> {
    if (input == null || input.isBlank()) {
        return;
    }
    System.out.println(input.trim());
};
~~~

Ở đây `return;` không trả dữ liệu. `isBlank()` là API Java 11+, nên đoạn minh họa này thích hợp với ứng dụng JDK 17+ hiện nay; nếu dự án bị ràng buộc Java 8 thì cần chọn cách kiểm tra chuỗi tương thích phiên bản. Quy tắc về `return;` và `return expression;` tự thân là quy tắc lambda của Java 8 và vẫn hiện hành.

**Quan trọng:** `return` bên trong lambda **chỉ kết thúc lần gọi lambda đó**, không thoát phương thức bao ngoài. Ví dụ trong `list.forEach(x -> { if (skip(x)) return; process(x); })`, `return;` bỏ qua phần xử lý còn lại của *một lần gọi lambda*; nó không thoát phương thức chứa `forEach`. Không dùng `return` của lambda để mô phỏng một `return` từ phương thức bao ngoài, và không thể dùng `break`/`continue` trong lambda để điều khiển vòng lặp ở ngoài thân lambda.

## 3. Quy tắc cốt lõi: `void-compatible` và `value-compatible`

JLS `15.27.2` phân loại **thân lambda** theo hình dạng, rồi `15.27.3` kiểm tra khả năng khớp với kiểu trả về của phương thức đích.

### 3.1. Lambda dạng biểu thức (expression body)

Nếu target trả **giá trị** `R`, thân biểu thức phải tạo được giá trị có thể chuyển đổi phù hợp với `R`. Ví dụ `n -> n + 1` phù hợp `Function<Integer,Integer>`, còn `() -> System.out.println("x")` không phù hợp `Supplier<String>` vì `println` trả `void`.

Nếu target trả **void**, thân biểu thức phải thuộc nhóm **statement expression** được Java cho phép đứng thành câu lệnh; khi một biểu thức trong nhóm này có kết quả, **giá trị kết quả bị bỏ đi**. Những dạng statement expression quan trọng gồm:

- Gọi phương thức: `service.save(item)`, `list.add(item)`, `calculate(n)`.
- Gán giá trị: `holder.value = n`.
- Tăng/giảm: `counter.incrementAndGet()` là lời gọi phương thức; với biến phù hợp có thể dùng `n++` hoặc `--n`.
- Tạo đối tượng bằng `new Type(...)`.

**Không phải mọi biểu thức trả ra giá trị đều là statement expression.** Ví dụ số literal `42`, phép cộng `n + 1`, phép so sánh `n > 0` không thuộc nhóm statement expression chỉ vì chúng sinh ra kết quả.

~~~java
Consumer<String> consumeA = s -> System.out.println(s); // Hợp lệ: method invocation, trả void
Consumer<String> consumeB = s -> s.trim();              // Hợp lệ: method invocation, kết quả String bị bỏ
Consumer<String> consumeC = s -> s.isEmpty();           // Hợp lệ: method invocation, kết quả boolean bị bỏ
Function<String, String> mapA = s -> s.trim();           // Hợp lệ: giữ String
Predicate<String> check = s -> s.isEmpty();             // Hợp lệ: giữ boolean
~~~

Đây là các khai báo minh họa trong phương thức (import `java.util.function.*`). Điểm dễ nhầm ở `consumeB` và `consumeC`: **trình biên dịch chấp nhận**, nhưng logic nghiệp vụ có thể không có tác dụng vì kết quả bị bỏ. Muốn dùng chuỗi đã trim, chọn `Function<String,String>` hoặc thực hiện hành động tường minh.

Ví dụ sai, **không phải code chạy độc lập**:

~~~java
Consumer<Integer> wrong = n -> n + 1;      // SAI: phép cộng không là statement expression
Runnable wrong2 = () -> 42;                // SAI: literal không là statement expression
Supplier<String> wrong3 = () -> System.out.println("x"); // SAI: biểu thức trả void
~~~

Nếu muốn tính và giữ `n + 1`, dùng `Function<Integer,Integer> f = n -> n + 1;`. Nếu thực sự cần một hành động, viết lời gọi phương thức có tác dụng phù hợp, ví dụ `Consumer<Integer> c = n -> System.out.println(n + 1);`. Đừng tạo thao tác vô nghĩa chỉ để hợp thức hóa chữ ký `void`.

### 3.2. Lambda dạng khối (block body)

Phân loại theo JLS:

| Loại thân khối | Điều kiện chính xác | Ví dụ |
| --- | --- | --- |
| **Void-compatible** | Mọi câu lệnh `return` trong block đều có dạng `return;` (cũng có thể không có `return` nào). | `() -> { System.out.println("done"); }`, `() -> { return; }` |
| **Value-compatible** | Block **không thể hoàn thành bình thường** (*cannot complete normally*) và mọi câu lệnh `return` bên trong đều có dạng `return expression;`. | `() -> { return 42; }`, `x -> { if (x > 0) return 1; return 0; }` |
| **Cả hai** | Có thể thỏa đồng thời hai quy tắc, thường vì block luôn ném ngoại lệ hoặc không thể kết thúc. | `() -> { throw new IllegalStateException(); }` |
| **Không thuộc loại nào** | Vừa có đường đi hoàn thành bình thường vừa có `return expression;`, hoặc trộn các kiểu `return` không hợp lệ. | `x -> { if (x > 0) return 1; System.out.println(x); }` |

Giải thích chi tiết:

- Một block `void` có thể kết thúc tự nhiên. Không có `return` nào cũng đáp ứng điều kiện “mọi return đều là `return;`”.
- Block giá trị phải bảo đảm không đi hết thân khối mà thiếu kết quả. Một đường đi kết thúc bằng `throw` là được phép; không nhất thiết *mọi nhánh* phải có câu lệnh `return` nếu nhánh còn lại ném ngoại lệ hoặc không kết thúc.
- Ví dụ `() -> { throw new IllegalStateException(); }` vừa void-compatible vừa value-compatible: nó không bao giờ hoàn thành bình thường và không có câu `return` sai dạng. **Điều này không có nghĩa lambda đã tạo được một giá trị ở runtime**; khi gọi nó, ngoại lệ được ném.
- Với target trả giá trị, Java còn kiểm tra **kiểu của từng biểu thức `return`** có tương thích với kiểu trả về yêu cầu hay không. Chỉ đúng “hình dạng” block vẫn chưa đủ: `Supplier<Integer> f = () -> { return "text"; };` là lỗi kiểu dữ liệu.

Nhớ phân biệt **khả năng tương thích hình dạng block** với **kết quả cuối cùng có thể biên dịch**. Chữ ký tham số, kiểu kết quả, checked exception và ngữ cảnh gọi vẫn phải hợp lệ.

## 4. Chọn giao diện theo ý nghĩa nghiệp vụ, không theo việc có dùng `return` hay không

Giả sử phương thức trả về số:

~~~java
static int twice(int n) {
    return n * 2;
}
~~~

Hai lambda sau đều hợp lệ về cú pháp và kiểu, nhưng có hợp đồng khác nhau:

~~~java
Function<Integer, Integer> useResult = n -> twice(n);
Consumer<Integer> ignoreResult = n -> twice(n);
~~~

Với `useResult.apply(5)`, kết quả nhận được là `10`. Với `ignoreResult.accept(5)`, `twice(5)` vẫn được gọi nhưng kết quả `10` bị bỏ. Điều này bắt nguồn từ **statement expression** (lời gọi phương thức), không phải vì phương thức `twice` tự trở thành một phương thức `void`.

Nếu chuyển `ignoreResult` sang dạng block, phải phân biệt rõ:

~~~java
Consumer<Integer> valid = n -> {
    twice(n);     // Kết quả bị bỏ dưới dạng expression statement
    return;       // Hợp lệ cho void
};
~~~

Ví dụ **sai**:

~~~java
Consumer<Integer> invalid = n -> {
    return twice(n); // SAI: target void không nhận return có biểu thức
};
~~~

Nếu bỏ phần thân khối và viết `n -> twice(n)` thì lại hợp lệ vì nó là **expression body** thuộc nhóm statement expression. Hai hình dạng có quy tắc tương thích khác nhau; không thể chép máy móc `return` vào thân khối.

Ngược lại, `Function<Integer,Integer>` cần kết quả:

~~~java
Function<Integer, Integer> valid = n -> {
    return twice(n);
};
~~~

Ví dụ **sai**:

~~~java
Function<Integer, Integer> invalid = n -> {
    twice(n); // SAI: tính xong bỏ kết quả; khối hoàn thành mà không trả giá trị
};
~~~

Khi viết API hoặc xử lý Stream, chọn `Consumer` nếu ý nghĩa là “nhận và thực hiện hành động”, chọn `Function`/`UnaryOperator` khi thực sự biến đổi dữ liệu, và `Predicate` khi yêu cầu một điều kiện boolean. Đừng dùng `Consumer` cho một phép tính có giá trị trả về cần giữ.

## 5. Chương trình đầy đủ có thể biên dịch/chạy: các kiểu `return` và `void`

Chương trình dưới đây chạy với **Java 17+**, đồng thời chỉ dùng các API lambda/function cơ bản đã có từ Java 8. Kết quả đã được kiểm tra bằng cách biên dịch và thực thi.

Lưu tệp **ReturnAndVoidDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;

public class ReturnAndVoidDemo {
    static int twice(int n) { return n * 2; }

    static void printMessage(String message) {
        System.out.println(message);
    }

    public static void main(String[] args) {
        // Expression body trả về giá trị: Function.apply trả Integer
        Function<Integer, Integer> calculate = n -> twice(n);

        // Cùng lời gọi twice, nhưng Consumer.accept trả void
        // nên kết quả từ twice(n) không được giữ lại.
        Consumer<Integer> discardResult = n -> twice(n);

        // Block body void-compatible với return; để thoát sớm
        Consumer<Integer> log = n -> {
            if (n > 0) {
                System.out.println("received=" + n);
                return;
            }
            System.out.println("not-positive");
        };

        // Block body value-compatible: mọi nhánh đều có kết quả
        Function<Integer, String> grade = n -> {
            if (n >= 60) {
                return "PASS";
            }
            return "RETRY";
        };

        Supplier<String> state = () -> "READY";
        Runnable task = () -> printMessage("task-run");

        List<String> names = new ArrayList<>();
        // List.add(String) trả boolean, Consumer<String> bỏ kết quả đó.
        Consumer<String> addName = names::add;

        log.accept(10);
        discardResult.accept(10);
        System.out.println("twice=" + calculate.apply(10));
        System.out.println("grade=" + grade.apply(40));
        System.out.println("state=" + state.get());
        task.run();
        addName.accept("Lan");
        System.out.println("names=" + names);
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ReturnAndVoidDemo.java
java ReturnAndVoidDemo
~~~

Stdout chính xác:

~~~text
received=10
twice=20
grade=RETRY
state=READY
task-run
names=[Lan]
~~~

**Vì sao các dòng đó xuất hiện?**

1. `log.accept(10)` chạy nhánh dương, in `received=10` rồi `return;` kết thúc chính lambda `log`.
2. `discardResult.accept(10)` vẫn tính `twice(10)` nhưng không in gì và không trả `Integer` cho caller.
3. `calculate.apply(10)` nhận lại `20` qua `Function`.
4. `grade.apply(40)` chọn nhánh `"RETRY"`, cả hai nhánh của block đều trả `String`.
5. `state.get()` trả `"READY"` và `task.run()` gọi hàm in thông báo.
6. `names::add` là method reference có phương thức đích `List.add` trả `boolean`, nhưng được dùng qua `Consumer<String>` với return `void`; thao tác thêm `"Lan"` vẫn xảy ra, còn boolean bị bỏ. Đây là ví dụ thực tế cho **tương thích void có loại bỏ giá trị trả về**, không phải vì `add` trả void.

**Hành vi phụ:** `Consumer` thường có mục đích tạo side effect như in log hoặc thêm phần tử vào collection; hãy giới hạn side effect ở các chỗ có chủ đích. Với phép biến đổi dữ liệu cần test và tái sử dụng, `Function` thường thể hiện ý nghĩa rõ hơn.

## 6. `return`, điều kiện nhánh và ngoại lệ: những đường đi dễ mắc lỗi

### 6.1. Lỗi thiếu `return` trong hàm trả giá trị

Đoạn dưới **không biên dịch**:

~~~java
Function<Integer, String> text = n -> {
    if (n > 0) {
        return "positive";
    }
    // n <= 0: không trả gì, block có thể hoàn thành bình thường
};
~~~

Sửa bằng cách bao phủ nhánh còn lại:

~~~java
Function<Integer, String> text = n -> {
    if (n > 0) return "positive";
    return "zero-or-negative";
};
~~~

Hoặc nếu thực sự xem giá trị ngoài miền hợp lệ là lỗi:

~~~java
Function<Integer, String> text = n -> {
    if (n > 0) return "positive";
    throw new IllegalArgumentException("n must be positive");
};
~~~

Cả hai đoạn sửa là **minh họa trong phương thức**, cần import `java.util.function.Function`. Nhánh thứ hai có thể ném exception thay vì return, vì block không hoàn thành bình thường trên đường đi đó.

### 6.2. Phân biệt `return;` với `return expression;`

| Đoạn thân lambda | Target trả void | Target trả giá trị | Lý do |
| --- | --- | --- | --- |
| `() -> { }` | Có | Không | Block có thể kết thúc bình thường |
| `() -> { return; }` | Có | Không | Return rỗng |
| `() -> { return 7; }` | Không | Có nếu kiểu phù hợp | Return có biểu thức |
| `() -> { throw new IllegalStateException(); }` | Có | Có về mặt hình dạng | Luôn ném ngoại lệ |
| `n -> n + 1` | Không | Có nếu kiểu phù hợp | Phép cộng không phải statement expression |
| `n -> Math.abs(n)` | Có | Có nếu kiểu phù hợp | Lời gọi phương thức là statement expression, có kết quả |
| `() -> System.out.println("hi")` | Có | Không | Lời gọi trả void, không tạo giá trị |
| `n -> { if (n > 0) return 1; }` | Không | Không | Có return giá trị nhưng khối có thể kết thúc bình thường |

“Có” trong cột giá trị còn phụ thuộc kiểu trả về của phép tính và các điều kiện gõ kiểu khác. Chẳng hạn `n -> n + 1` cần target có tham số số học tương thích; không thể vì bảng nói “có” mà gán vào một hàm trả `String`.

### 6.3. Ngoại lệ kiểm tra (checked exception) vẫn phải theo hợp đồng

Lambda không được tự ý phát sinh checked exception vượt quá khai báo `throws` của phương thức chức năng. Ví dụ `Runnable.run()` không khai báo `IOException`, nên không thể trực tiếp dùng lambda `() -> Files.readString(path)` trong `Runnable` nếu không bắt hoặc chuyển ngoại lệ. Các lựa chọn hiện hành là bắt lỗi ở ranh giới phù hợp, dùng `UncheckedIOException` khi chuyển `IOException` có ngữ cảnh, hoặc định nghĩa functional interface có `throws` phù hợp. Điều này là vấn đề hợp đồng ngoại lệ, không phải chỉ là `void` hay kiểu giá trị.

## 7. Tương thích kiểu kết quả, generic và boxing/unboxing

Ngay cả khi thân lambda **value-compatible**, kiểu thực tế của biểu thức `return` còn phải phù hợp với kiểu trả về của functional interface:

~~~java
Supplier<String> a = () -> "READY";
Supplier<Object> b = () -> "READY";    // String có thể gán cho Object
IntSupplier c = () -> 42;              // Trả int nguyên thủy
Function<Integer, Long> d = x -> x.longValue();
~~~

Ví dụ `Supplier<Integer> s = () -> 42;` hợp lệ nhờ boxing từ `int` thành `Integer`. Nhưng `Supplier<String> s = () -> 42;` không hợp lệ vì không có chuyển đổi gán kiểu thích hợp từ `int` sang `String`. Một block với `return null;` có thể khớp kiểu tham chiếu nhưng không thể khớp target trả `int`; nếu cần mô tả một kết quả *có thể thiếu*, cân nhắc hợp đồng API rõ ràng như `Optional<T>` hoặc loại kết quả nghiệp vụ, thay vì dùng null tùy tiện.

**Kiểu trả về không quyết định kiểu đối số.** Hai yếu tố được xét chung: arity (số tham số), kiểu tham số và kiểu trả về của phương thức chức năng. Ví dụ `Predicate<String>` nhận `String`, trả `boolean`; `Function<String,Boolean>` nhận `String`, trả `Boolean`. Cả hai có thể viết `s -> s.isEmpty()`, nhưng chúng là những target type khác nhau; chọn theo vai trò mong muốn (kiểm tra điều kiện hay ánh xạ thành đối tượng Boolean).

Đối với method reference, nguyên tắc tương tự: `Consumer<String> c = System.out::println;` thích hợp với lời gọi trả void; `Consumer<String> c = names::add;` có thể bỏ boolean do `add` trả. Trong các overload phức tạp, việc chọn target type có thể ảnh hưởng phương thức được chọn; viết rõ kiểu ở biến/đối số khi cần.

## 8. Lambda khi truyền vào phương thức overload: nên làm cho kiểu đích rõ ràng

Lambda có thể tham gia *overload resolution* (chọn phương thức cùng tên theo tham số), nên chỉ nhìn số tham số lambda chưa đủ kết luận nó phải trả giá trị hay void. Ví dụ có hai overload:

~~~java
static void execute(Runnable action) {
    action.run();
}

static void execute(Supplier<String> source) {
    System.out.println(source.get());
}
~~~

Những lời gọi minh họa trong một phương thức khác của cùng lớp:

~~~java
execute(() -> { System.out.println("run"); }); // Block void-compatible
execute(() -> { return "result"; });            // Block value-compatible
~~~

Các thân block trên giúp phân biệt mục đích trả void và trả `String`. Khi body của lambda là một *method invocation* trả kết quả, hình dạng expression body có thể khớp cả target void và target giá trị, nên chọn overload có thể không rõ hoặc phụ thuộc quy tắc so sánh “most specific” của Java. Không nên dựa vào phỏng đoán kiểu trả về chỉ từ biểu thức; để API dễ gọi và bảo trì, có thể đặt tên phương thức khác nhau, khai báo biến trung gian có target type tường minh, hoặc dùng cast đến functional interface mong muốn ở đúng vị trí.

~~~java
Runnable sideEffect = () -> System.out.println("run");
Supplier<String> valueSource = () -> "result";
execute(sideEffect);
execute(valueSource);
~~~

Một lambda có block `() -> { throw new IllegalStateException(); }` là ví dụ thân khối **vừa void-compatible vừa value-compatible**. Với những overload không được phân biệt đủ bằng các ràng buộc khác, code có thể thành không rõ nghĩa; nếu muốn chọn overload, biểu thị target type tường minh. Đừng hiểu “cả hai” là Java sẽ tự ý quyết định void hay trả một giá trị rỗng.

## 9. Gặp trực tiếp trong Stream và callback

Trong Stream API, target type của các operation đã rõ từ chữ ký phương thức:

| Thao tác | Functional interface được nhận | Điều gì cần trả? |
| --- | --- | --- |
| `stream.filter(predicate)` | `Predicate<T>` | `boolean` để giữ/bỏ phần tử |
| `stream.map(mapper)` | `Function<T,R>` | `R` là phần tử sau biến đổi |
| `stream.flatMap(mapper)` | `Function<T,Stream<R>>` | Một `Stream<R>`; phải quản lý trường hợp rỗng đúng cách |
| `stream.forEach(action)` | `Consumer<T>` | `void`; hành động, không có Stream kết quả |
| `stream.peek(action)` | `Consumer<T>` | `void`; chủ yếu dùng để quan sát/debug có giới hạn |
| `stream.sorted(comparator)` | `Comparator<T>` | `int` diễn tả thứ tự so sánh |

~~~java
List<String> normalized = Arrays.asList(" Lan ", " ", " An ")
    .stream()
    .map(String::trim)       // Function: GIỮ String đã trim
    .filter(s -> !s.isEmpty()) // Predicate: TRẢ boolean
    .toList();               // Java 16+, List không sửa được
~~~

Đây là đoạn dùng bên trong một phương thức, cần import `java.util.*`. Kết quả là danh sách `["Lan", "An"]`. Nếu dùng `forEach(s -> s.trim())` thay cho `map(String::trim)`, thân lambda có thể **biên dịch** vì phương thức `trim` là statement expression, nhưng mọi kết quả chuỗi mới đều bị bỏ, và pipeline không tạo danh sách đã chuẩn hóa. Đây là lỗi **đúng cú pháp nhưng sai ý nghĩa**, đặc biệt phổ biến khi người học nhầm `Consumer` với `Function`.

Với callback trả `void`, hãy diễn tả hành động có chủ đích. Với phép chuyển đổi dữ liệu, hãy chọn API nhận `Function` và dùng giá trị trả về. `forEach` không có ý nghĩa “map và trả danh sách”; terminal operation có thể thực hiện hành động nhưng không tạo Stream mới để tiếp tục.

## 10. Lỗi thường gặp khi viết lambda và cách sửa

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `Consumer<Integer> c = n -> n * 2;` không biên dịch | Toán tử nhân không là statement expression | Dùng `Function<Integer,Integer>` để trả kết quả, hoặc hành động thực sự |
| `Supplier<String> s = () -> System.out.println("x");` không biên dịch | `println` trả void, còn `Supplier.get` cần `String` | Chọn `Runnable`/`Consumer` cho hành động, hoặc trả chuỗi hợp lệ |
| `Consumer<T> c = x -> { return f(x); };` không biên dịch | Block void không cho `return expression;` | Dùng `f(x); return;` nếu cố ý bỏ kết quả; hoặc đổi sang `Function` |
| `Function<T,R> f = x -> { doWork(x); };` không biên dịch | Block có thể kết thúc mà không trả `R` | Trả `R` ở mọi đường hoàn thành, hoặc đổi sang target void |
| `Function` có nhánh `if` trả, nhánh kia bỏ trống | Block không value-compatible | Thêm `return` nhánh còn lại hoặc xử lý bằng `throw` hợp lý |
| `forEach(x -> transform(x))` chạy mà dữ liệu không đổi | Giá trị transform bị bỏ | Dùng `map` và terminal operation thích hợp |
| Thấy phương thức trả `boolean` rồi nghĩ không dùng được với `Consumer` | Nhầm kiểu trả về của phương thức được gọi với kiểu trả về của functional interface | Gọi phương thức trong expression body/statement và bỏ giá trị nếu đúng ý định |
| Dùng `return;` trong `Function` | Không cung cấp kết quả cho target trả giá trị | Dùng `return expression;` hoặc ném lỗi có chủ đích |
| Dùng `return x;` trong `Runnable` | Target void không nhận giá trị | Bỏ biểu thức trả về, hoặc dùng `Supplier<T>` |
| Một lambda khớp nhiều overload | Target type chưa rõ; đặc biệt với method invocation/throw-only body | Tách tên API hoặc khai báo/cast functional interface rõ ràng |
| Nhầm `return` của lambda thành `return` của phương thức bao ngoài | Lambda là một invocation độc lập | Đưa logic cần thoát phương thức vào flow ngoài callback |

Các điều kiện trên là ngữ nghĩa ngôn ngữ hiện hành, không dựa vào một cú pháp cũ đã bị loại bỏ. Khác biệt Java 8 so với các JDK mới hơn thường đến từ **API được dùng trong thân lambda** (ví dụ `String.isBlank()` từ Java 11, `Stream.toList()` từ Java 16), không phải do quy tắc void-compatible/value-compatible bị thay thế.

## 11. Câu hỏi tự luyện

1. Vì sao `Consumer<String> c = s -> s.trim();` hợp lệ về cú pháp nhưng có thể là lỗi logic? Hãy viết phiên bản trả về chuỗi đã trim.
2. Đổi `Function<Integer,Integer> f = x -> x + 2;` thành block body tương đương, không đổi hành vi.
3. Vì sao `Runnable r = () -> 10;` bị từ chối, trong khi `Runnable r = () -> Integer.valueOf(10);` lại phù hợp hình dạng lambda? Phân tích giá trị bị bỏ.
4. Cho một `Function<Integer,String>` phân loại số âm, 0, dương bằng block, đảm bảo không thiếu `return` ở bất kỳ nhánh nào.
5. So sánh `() -> { return; }`, `() -> { return 5; }` và `() -> { throw new RuntimeException(); }` theo hai khái niệm void-compatible/value-compatible.
6. Vì sao `return;` bên trong `list.forEach` không thoát phương thức bên ngoài? Đưa ra cách viết hợp lý nếu thực sự cần dừng xử lý toàn bộ danh sách.
7. Khi `list.add(item)` trả boolean nhưng được truyền qua `Consumer<T>`, điều gì xảy ra với giá trị boolean? Vì sao side effect thêm phần tử vẫn xảy ra?
8. `Supplier<Integer>` có thể trả `"42"` hay `null` không? Giải thích theo tương thích kiểu và boxing.

## Tham khảo chuẩn chính thức

- **Java Language Specification `15.27.2 – Lambda Body**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.2
- **Java Language Specification `15.27.3 – Type of a Lambda Expression**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.3
- **Java Language Specification `14.8 – Expression Statements**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.8
- **Java SE 17 `java.util.function`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html

Cần nhớ nhất: **target functional interface** quyết định phải nhận `void` hay một giá trị; **expression body** có thể bỏ kết quả khi nó là một statement expression; **block body** phải dùng đúng dạng `return;` hoặc `return expression;` và thỏa quy tắc về các đường hoàn thành. Hiểu ba điều này sẽ tránh được cả lỗi biên dịch lẫn những callback biên dịch được nhưng âm thầm bỏ kết quả cần dùng.