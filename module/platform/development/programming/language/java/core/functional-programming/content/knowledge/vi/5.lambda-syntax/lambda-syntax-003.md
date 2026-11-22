# Thân biểu thức và thân khối lệnh trong Java lambda

## 1. Mục tiêu bài học

Biểu thức lambda giúp cung cấp cách triển khai **phương thức trừu tượng duy nhất** (SAM) của một functional interface. Phần bên phải mũi tên `->` gọi là **thân lambda**. Java cho phép viết thân theo hai dạng chính:

- **Thân biểu thức (expression body):** một biểu thức duy nhất, viết gọn, không dùng ngoặc nhọn và không đặt `return`.
- **Thân khối lệnh (block body):** một khối `{ ... }` gồm các câu lệnh; có thể khai báo biến, rẽ nhánh, xử lý ngoại lệ và dùng `return` phù hợp với kiểu trả về của SAM.

Đây là hai dạng cú pháp cho cùng khái niệm lambda, **không phải hai loại functional interface khác nhau**. Chọn dạng dựa vào công việc cần thực hiện, khả năng đọc và hợp đồng tham số/giá trị trả về.

Sau bài này, người học cần có thể viết và chuyển đổi hai dạng thân; xác định khi nào cần `return`, dấu `;`, ngoặc nhọn; giải thích khác biệt giữa lambda trả giá trị và lambda `void`; đồng thời nhận diện các lỗi biên dịch thường gặp.

Các ví dụ chạy độc lập sử dụng **JDK 17 trở lên**.

## 2. Cấu trúc chung của một biểu thức lambda

Cú pháp tổng quát:

~~~java
(parameters) -> expression

(parameters) -> {
    statements
}
~~~

Đây là **mẫu cú pháp**, không phải hai câu lệnh Java độc lập. Vế trái `->` là danh sách tham số và vế phải là thân. Kiểu tham số, kiểu trả về hợp lệ và khả năng ném checked exception được xác định từ **functional interface làm kiểu đích** (*target type*), chẳng hạn `Function<Integer,Integer>` hoặc `Consumer<String>`.

Ví dụ với `java.util.function.Function`:

~~~java
Function<Integer, Integer> square = number -> number * number;
~~~

`Function<Integer,Integer>` có SAM là `Integer apply(Integer value)`. Compiler hiểu `number` là một `Integer`; biểu thức `number * number` dùng phép unboxing rồi boxing cần thiết để trả kết quả phù hợp `Integer`.

Viết cùng logic dưới dạng thân khối lệnh:

~~~java
Function<Integer, Integer> square = number -> {
    int result = number * number;
    return result;
};
~~~

Hai ví dụ minh họa được đặt **riêng biệt** trong ngữ cảnh đã import `java.util.function.Function`; không khai báo hai biến `square` cùng phạm vi trong chương trình thực tế.

Các dấu dễ nhầm:

| Thành phần | Ý nghĩa |
| --- | --- |
| `->` | Ngăn tham số và thân lambda |
| `{ ... }` | Bắt đầu/kết thúc block body |
| `return expression;` | Trả giá trị từ block body khi SAM yêu cầu kết quả |
| `return;` | Kết thúc block body tương thích `void` |
| `;` sau toàn bộ lambda | Kết thúc câu lệnh khai báo/gán biến hoặc lời gọi chứa lambda theo cú pháp xung quanh |
| `;` bên trong block | Kết thúc từng câu lệnh Java trong khối |

**Điểm quan trọng:** dấu chấm phẩy sau `}` trong `Function<Integer,Integer> f = x -> { return x + 1; };` kết thúc **khai báo biến**, còn dấu `;` sau `return x + 1` kết thúc **câu lệnh return**.

## 3. Thân biểu thức: ngắn gọn khi một biểu thức là đủ

### 3.1. Viết không có `{ }` và không có `return`

Các ví dụ sau đều là expression body:

~~~java
Function<Integer, Integer> doubleIt = n -> n * 2;
Predicate<String> nonEmpty = text -> !text.isEmpty();
Supplier<String> greeting = () -> "Xin chào";
Comparator<Integer> ascending = (a, b) -> Integer.compare(a, b);
Consumer<String> print = text -> System.out.println(text);
~~~

Đây là **các khai báo trong một phương thức** sau khi import `java.util.function.*` và `java.util.Comparator`. Mỗi vế phải `->` chứa đúng **một biểu thức**:

- `n * 2` là biểu thức toán học; giá trị của nó là kết quả của `Function.apply`.
- `!text.isEmpty()` trả `boolean`, phù hợp SAM `Predicate.test`.
- `"Xin chào"` là biểu thức hằng, phù hợp `Supplier.get`.
- `Integer.compare(a, b)` trả `int`, phù hợp `Comparator.compare`.
- `System.out.println(text)` là lời gọi phương thức `void`, phù hợp `Consumer.accept`.

Trong expression body, **không viết** `return`. Ví dụ `n -> return n * 2;` là lỗi cú pháp. Nếu muốn dùng `return`, phải chuyển sang block body.

### 3.2. Điều kiện ba ngôi và lời gọi phương thức

Expression body không chỉ giới hạn ở phép toán đơn giản; có thể là một biểu thức điều kiện hoặc lời gọi hàm khác:

~~~java
Function<Integer, String> classification =
        n -> n >= 0 ? "không âm" : "âm";

Function<String, Integer> length =
        text -> text == null ? 0 : text.length();
~~~

Các biểu thức điều kiện `?:` vẫn là **một biểu thức**. Nên ưu tiên cách này khi cả hai nhánh ngắn và ý nghĩa rõ. Nếu có nhiều nhánh, nhiều bước xử lý hoặc kiểm tra lỗi, block body thường dễ theo dõi hơn.

### 3.3. Kiểu trả về không thể đoán riêng từ dấu `->`

So sánh:

~~~java
Function<String, Integer> count = text -> text.length();
Consumer<String> log = text -> System.out.println(text);
~~~

Với `Function`, `apply` trả `Integer` nên biểu thức phải tạo được giá trị phù hợp. Với `Consumer`, `accept` trả `void` nên lambda thực hiện một hành động. **Cú pháp gọn không quyết định kiểu trả về; functional interface mới quyết định hợp đồng**.

Một lambda không có kiểu đích rõ ràng thường không thể suy luận, ví dụ:

~~~java
// Không hợp lệ: thiếu target type cho lambda.
var action = x -> x + 1;
~~~

Sửa bằng cách cung cấp kiểu đích:

~~~java
Function<Integer, Integer> action = x -> x + 1;
~~~

Các ví dụ lỗi ở bài này chỉ nhằm phân tích cú pháp và **không được ghép vào chương trình chạy**.

## 4. Thân khối lệnh: nhiều câu lệnh và kiểm soát luồng

### 4.1. Dùng khối `{ ... }` và khai báo biến nội bộ

Khi cần nhiều bước trung gian:

~~~java
Function<String, String> normalize = raw -> {
    String value = raw == null ? "" : raw.trim();
    String upper = value.toUpperCase(java.util.Locale.ROOT);
    return upper;
};
~~~

Thân khối lệnh có thể khai báo biến, gọi phương thức và trả kết quả. Các biến `value`, `upper` sống trong phạm vi block lambda, giúp đặt tên cho các bước nghiệp vụ.

### 4.2. Với SAM trả giá trị: đường đi bình thường phải trả kết quả

Một khối của `Function<T,R>` cần trả giá trị phù hợp `R` trên mọi đường đi có thể hoàn tất; đường đi có thể kết thúc bằng exception thay cho `return`. Ví dụ hợp lệ:

~~~java
Function<Integer, String> sign = n -> {
    if (n < 0) {
        return "âm";
    }
    if (n == 0) {
        return "không";
    }
    return "dương";
};
~~~

Ví dụ **không hợp lệ** vì có nhánh không trả giá trị:

~~~java
Function<Integer, Integer> absolute = n -> {
    if (n < 0) {
        return -n;
    }
    // Thiếu return khi n >= 0
};
~~~

Sửa bằng `return n;` ở cuối khối. Java kiểm tra đường đi trả về trong quá trình biên dịch, không đợi đến lúc chạy với trường hợp gây lỗi.

### 4.3. Với SAM `void`: không trả giá trị

Ví dụ cho `Consumer<String>`:

~~~java
Consumer<String> printIfPresent = text -> {
    if (text == null || text.isBlank()) {
        return; // Thoát sớm khỏi lambda void.
    }
    System.out.println(text.trim());
};
~~~

`return;` không có biểu thức sau nó, phù hợp `void`. Viết `return text;` trong block của `Consumer.accept` là lỗi biên dịch. Có thể bỏ `return;` khi khối tự chạy đến cuối và hoàn tất bình thường.

Với `Runnable` hoặc `Consumer`, block thường chỉ gồm câu lệnh như logging, lưu dữ liệu, gửi sự kiện. Việc không trả kết quả **không có nghĩa tác dụng phụ là an toàn hay nên làm trong mọi trường hợp**.

### 4.4. Block body và câu lệnh `throw`

Nếu gặp lỗi đầu vào, có thể ném exception:

~~~java
Function<Integer, Integer> safeReciprocal = n -> {
    if (n == 0) {
        throw new IllegalArgumentException("n must not be zero");
    }
    return 100 / n;
};
~~~

Câu lệnh `throw` kết thúc đường đi bằng exception, không yêu cầu có một giá trị `return` cho nhánh đó. Các trường hợp khác vẫn phải trả kết quả phù hợp kiểu đích. Nếu lambda có checked exception, nó phải phù hợp khai báo `throws` của SAM hoặc được xử lý, giống các phương thức Java thông thường.

## 5. Phân biệt `void` và biểu thức trả về giá trị

Đây là chi tiết dễ nhầm nhất: **một expression body tương thích với SAM `void` khi biểu thức thuộc nhóm *statement expression*** theo cú pháp Java. Nhóm này gồm lời gọi phương thức, phép gán, tăng/giảm tiền tố hoặc hậu tố, và biểu thức tạo đối tượng bằng `new`. Giá trị do một số biểu thức tạo ra vẫn có thể **bị bỏ qua** trong ngữ cảnh `void`.

Ví dụ hợp lệ:

~~~java
List<String> names = new ArrayList<>();

// List.add trả boolean; Consumer.accept trả void.
// Giá trị boolean của add(...) bị bỏ qua.
Consumer<String> addName = name -> names.add(name);

addName.accept("An");
~~~

Mã trên cần import `java.util.List`, `java.util.ArrayList` và `java.util.function.Consumer`, đặt bên trong phương thức. Nó hợp lệ vì `names.add(name)` là **method invocation expression**, đồng thời là statement expression. Không nên hiểu rằng mọi biểu thức trả giá trị đều dùng được cho `Consumer`.

Ví dụ không hợp lệ:

~~~java
// Không phải statement expression, không thể là thân của lambda void.
Consumer<Integer> wrong = n -> n + 1;
~~~

Sửa tùy **ý định**:

~~~java
// Nếu cần kết quả số mới:
Function<Integer, Integer> plusOne = n -> n + 1;

// Nếu cần thực hiện thao tác in:
Consumer<Integer> printPlusOne = n -> System.out.println(n + 1);
~~~

Dạng block làm ranh giới rõ hơn:

~~~java
Consumer<Integer> printBlock = n -> {
    int result = n + 1;
    System.out.println(result);
};
~~~

### Bảng quy tắc theo kiểu SAM

| Kiểu đích | Expression body | Block body | Lưu ý |
| --- | --- | --- | --- |
| `Function<Integer,Integer>` | `n -> n * 2` | `n -> { return n * 2; }` | Phải cung cấp giá trị `Integer` hợp lệ |
| `Predicate<Integer>` | `n -> n > 0` | `n -> { return n > 0; }` | Trả `boolean` |
| `Supplier<String>` | `() -> "ok"` | `() -> { return "ok"; }` | Không có tham số, có kết quả |
| `Consumer<String>` | `s -> System.out.println(s)` | `s -> { System.out.println(s); }` | Thực hiện hành động, trả `void` |
| `Runnable` | `() -> System.out.println("go")` | `() -> { System.out.println("go"); }` | Không có tham số, trả `void` |

Cần phân biệt **block void-compatible** và **block value-compatible**:

- Với SAM trả `void`, block có thể hoàn tất bình thường hoặc dùng `return;`, nhưng không có `return expression;`.
- Với SAM trả giá trị, block không được có đường đi hoàn tất bình thường mà thiếu giá trị; mọi câu lệnh `return` phải mang biểu thức đúng kiểu.
- Một block chỉ ném exception trên mọi đường đi (không có `return` và không hoàn tất bình thường) có thể tương thích cả hai dạng, nhưng đây là trường hợp đặc biệt. Không nên dùng nó để suy luận rằng `return;` và `return value;` có thể hoán đổi.

## 6. Chương trình Java 17 hoàn chỉnh: cùng một logic ở hai dạng thân

Tạo tệp **`LambdaBodiesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaBodiesDemo {
    public static void main(String[] args) {
        // Expression body: kết quả biểu thức trở thành giá trị trả về.
        Function<Integer, Integer> square = n -> n * n;

        // Block body: phải return vì Function.apply không trả void.
        Function<Integer, Integer> squareBlock = n -> {
            int result = n * n;
            return result;
        };

        // Nhiều đường đi với giá trị trả về rõ ràng.
        Predicate<String> hasText = text -> {
            if (text == null) {
                return false;
            }
            return !text.isBlank();
        };

        // Consumer: expression body gọi phương thức void.
        Consumer<String> greet =
                text -> System.out.println("Hi " + text);

        // Consumer: block body gồm nhiều câu lệnh.
        Consumer<String> greetBlock = text -> {
            String clean = text.trim();
            System.out.println("Hi " + clean);
        };

        // Runnable không nhận tham số, không trả giá trị.
        Runnable announce = () -> System.out.println("Ready");
        Runnable announceBlock = () -> {
            System.out.println("Ready");
        };

        // List.add trả boolean nhưng lời gọi có thể bỏ kết quả
        // khi dùng làm expression body của Consumer.
        List<String> names = new ArrayList<>(List.of("An"));
        Consumer<List<String>> append = list -> list.add("Binh");

        System.out.println(square.apply(5));
        System.out.println(squareBlock.apply(5));
        System.out.println(hasText.test(" "));
        System.out.println(hasText.test(" Java "));
        greet.accept("Mai");
        greetBlock.accept("  Mai  ");
        announce.run();
        announceBlock.run();
        append.accept(names);
        System.out.println(names);
    }
}
~~~

Trong terminal có JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 LambdaBodiesDemo.java
java LambdaBodiesDemo
~~~

**Stdout chính xác:**

~~~text
25
25
false
true
Hi Mai
Hi Mai
Ready
Ready
[An, Binh]
~~~

Giải thích:

1. Hai lambda `square` và `squareBlock` đều nhân `5 * 5`, nên cùng in `25`. Dạng block yêu cầu `return`, còn dạng expression không viết `return`.
2. `hasText.test(" ")` trả `false` vì chuỗi chỉ có khoảng trắng; `hasText.test(" Java ")` trả `true`.
3. Hai `Consumer` tạo lời chào giống nhau; một bản gọi `println` trực tiếp, bản kia chuẩn hóa trước.
4. Hai `Runnable` in `Ready`. Các khối hoàn tất bình thường vì phương thức `run` trả `void`.
5. `append` dùng lời gọi `list.add("Binh")` làm expression body hợp lệ cho `Consumer<List<String>>`; kết quả boolean của `add` bị bỏ qua. Danh sách được sửa nên in `[An, Binh]`.

Ví dụ cố ý có một side effect để minh họa khả năng tương thích `void`; trong thiết kế dữ liệu thực tế, không nên mặc định thay đổi collection bên ngoài pipeline là lựa chọn an toàn, nhất là với xử lý song song.

## 7. Những lỗi cú pháp và biên dịch thường gặp

### 7.1. Thêm `return` vào expression body

~~~java
// Sai: return chỉ là câu lệnh trong block.
Function<Integer, Integer> f = n -> return n * 2;
~~~

Sửa thành `n -> n * 2` hoặc `n -> { return n * 2; }`.

### 7.2. Dùng ngoặc nhọn nhưng quên `return`

~~~java
// Sai: đây là block, Function yêu cầu trả kết quả.
Function<Integer, Integer> f = n -> { n * 2; };
~~~

Ngoài việc thiếu `return`, phép cộng/nhân đơn lẻ `n * 2;` cũng không phải một *statement expression* hợp lệ. Sửa:

~~~java
Function<Integer, Integer> f = n -> {
    return n * 2;
};
~~~

### 7.3. Dùng dấu chấm phẩy sai vị trí

~~~java
// Đúng:
Function<Integer, Integer> a = n -> n + 1;
Function<Integer, Integer> b = n -> { return n + 1; };

// Sai: dấu ; trở thành một phần đặt nhầm trong expression body.
Function<Integer, Integer> c = n -> n + 1;;
~~~

Ở dòng `c`, **dấu `;` thứ hai** là một câu lệnh rỗng riêng nếu đặt tại vị trí cho phép câu lệnh; nó không nhất thiết gây lỗi biên dịch. Tuy nhiên, đó là cú pháp thừa và không phải cách diễn đạt một thân lambda gồm hai lệnh. Khi dùng block, dấu `;` bên trong thuộc về từng câu lệnh. Khi dùng expression, chỉ cần một dấu `;` để kết thúc khai báo biến.

### 7.4. Trả giá trị từ `Consumer`

~~~java
// Sai: Consumer.accept trả void.
Consumer<String> consumer = s -> { return s; };
~~~

Sửa thành `s -> { System.out.println(s); }` nếu mục tiêu là hành động, hoặc `Function<String,String>` nếu muốn biến đổi chuỗi và nhận kết quả.

### 7.5. Không trả về ở mọi nhánh của `Function`

~~~java
// Sai: n = 0 đi đến cuối block mà không return.
Function<Integer, Integer> f = n -> {
    if (n > 0) {
        return n;
    }
};
~~~

Thêm `return 0;` hoặc triển khai điều kiện đầy đủ.

### 7.6. Dùng nhiều câu lệnh mà không có block

~~~java
// Sai: thiếu { } cho hai câu lệnh riêng.
Consumer<String> action = s -> System.out.println(s); System.out.println("done");
~~~

Dòng trên có thể được Java phân tích thành **hai câu lệnh bên ngoài lambda** nếu nằm trong phương thức: `action` chỉ in `s`, còn `println("done")` chạy ngay lúc đi qua câu lệnh kế tiếp. Nó không tạo một Consumer có hai hành động. Sửa ý định:

~~~java
Consumer<String> action = s -> {
    System.out.println(s);
    System.out.println("done");
};
~~~

### 7.7. Đặt nhầm tên biến trong phạm vi

Các biến khai báo trong block lambda là biến cục bộ, không tự tạo vùng tên độc lập cho phép khai báo trùng tên một biến local đã tồn tại trong phạm vi bao ngoài. Ví dụ:

~~~java
int count = 10;
// Sai: không được khai báo local count mới trong block lambda.
Runnable r = () -> {
    int count = 5;
    System.out.println(count);
};
~~~

Đổi tên biến ở trong lambda hoặc tổ chức lại phạm vi. Biến ở ngoài mà lambda sử dụng phải là `final` hoặc **effectively final**; không thể tăng `count++` của một local captured từ trong lambda.

### 7.8. Bỏ qua checked exception

Thân biểu thức và thân khối lệnh đều phải tuân thủ `throws` của SAM. Việc đổi từ expression body sang block body không tự cho phép ném `IOException` qua `Consumer.accept`. Với lời gọi có checked exception, cần xử lý bằng `try/catch` hoặc chọn một functional interface có hợp đồng exception phù hợp. Tránh nuốt lỗi để làm code biên dịch.

## 8. Khi nào nên chọn dạng biểu thức hay khối lệnh?

| Tình huống | Dạng thường phù hợp | Lý do |
| --- | --- | --- |
| Phép toán/biến đổi một bước | Expression | Ngắn, thấy ngay kết quả |
| Predicate điều kiện đơn giản | Expression | Ít nhánh, dễ đối chiếu |
| Gọi một phương thức `void` | Expression | Gọn khi tên phương thức rõ nghĩa |
| Có biến trung gian cần đặt tên | Block | Làm lộ các bước xử lý |
| Có nhiều nhánh `if`/`switch` hoặc kiểm tra lỗi | Block | Kiểm soát luồng và trả kết quả rõ |
| Có `try/catch` hoặc nhiều side effect có chủ đích | Block | Dễ xác định cách xử lý lỗi, thứ tự |
| Lambda quá dài hoặc lồng nhau | Tách thành phương thức riêng | Giảm tải nhận thức, dễ kiểm thử |

Ví dụ chuyển đổi tương đương:

~~~java
Function<String, Integer> lengthA =
        text -> text == null ? 0 : text.trim().length();

Function<String, Integer> lengthB = text -> {
    if (text == null) {
        return 0;
    }
    String trimmed = text.trim();
    return trimmed.length();
};
~~~

Cả hai cho `0` với `null`, `4` với `" Java "`. Bản biểu thức gọn; bản khối dễ thêm kiểm tra, log hoặc điểm dừng debugger. Không nên tự động biến mọi lambda ngắn thành block, cũng không nên ép mọi logic phức tạp vào một biểu thức.

### Mẹo debug

Với block, có thể đặt breakpoint trên dòng khai báo biến hoặc nhánh `return` để quan sát giá trị trung gian. Nếu expression body khó debug, đổi tạm sang block hoặc tách logic thành phương thức có tên. Khi tác dụng phụ xuất hiện, xem xét thứ tự thực thi và ngoại lệ, đặc biệt nếu lambda được truyền vào Stream chạy song song.

## 9. Bài tập tự luyện và đáp án gợi ý

**Bài 1 — Viết hai dạng cùng logic.** Tạo `Function<Integer,Integer>` tăng một số lên 1 bằng expression body và block body. Kiểm tra với `5`, kết quả phải là `6`.

Gợi ý:

~~~java
Function<Integer, Integer> shortForm = n -> n + 1;
Function<Integer, Integer> longForm = n -> {
    return n + 1;
};
~~~

**Bài 2 — Điều kiện nhiều nhánh.** Viết `Function<Integer,String>` phân loại điểm: dưới 5 là `"Fail"`, từ 5 đến dưới 8 là `"Pass"`, còn lại là `"Excellent"`. Dùng block body và bảo đảm mọi nhánh trả kết quả. Kiểm tra với `4`, `6`, `9`.

**Bài 3 — Consumer thoát sớm.** Viết `Consumer<String>` chỉ in khi chuỗi khác `null` và không trống sau khi bỏ khoảng trắng. Dùng `return;` để bỏ qua đầu vào không hợp lệ. Giải thích vì sao `return value;` không hợp lệ.

**Bài 4 — Xác định lỗi.** Mỗi đoạn dưới đây nên thay gì?

~~~java
// A: thiếu return trong block trả giá trị.
Function<Integer, Integer> a = n -> { n + 1; };

// B: void block lại return giá trị.
Consumer<String> b = text -> { return text; };

// C: phép cộng không phải statement expression cho SAM void.
Consumer<Integer> c = n -> n + 1;
~~~

Đáp án định hướng: A dùng `return n + 1;`; B thực hiện hành động như `System.out.println(text);` hoặc thay bằng `Function`; C chuyển thành `Function<Integer,Integer>` nếu cần kết quả, hoặc `Consumer` gọi `println` nếu cần hành động.

**Bài 5 — Phân biệt thời điểm chạy.** Viết `Runnable r = () -> { System.out.println("go"); };` và một dòng `System.out.println("now");` ngay sau khai báo. Dự đoán đầu ra trước và sau `r.run()`. Lời giải: khai báo lambda chưa chạy thân; đầu ra là `now`, rồi sau khi gọi `run` mới có `go`.

**Bài 6 — Chuyển đổi có kiểm chứng.** Tạo `Predicate<String>` kiểm tra tên có ít nhất ba ký tự sau khi `trim`. Viết dưới dạng expression và block, thử `null`, `"  An "`, `"  Hoa  "`. Nếu không xử lý `null`, biểu thức có thể ném `NullPointerException`; yêu cầu hai bản có hợp đồng giống nhau.

## 10. Checklist trước khi hoàn thành một lambda

1. **Kiểu đích là gì?** SAM nhận tham số nào, trả kiểu nào, có khai báo checked exception không?
2. **Một biểu thức đã đủ chưa?** Nếu có, expression body thường gọn nhất.
3. **Có nhiều câu lệnh hoặc rẽ nhánh không?** Nếu có, dùng `{ ... }`.
4. **SAM trả giá trị?** Với block, mọi đường đi hoàn tất bình thường phải có `return expression;` đúng kiểu.
5. **SAM trả `void`?** Không trả giá trị; nếu cần thoát sớm, dùng `return;`.
6. **Thân expression có phải statement expression khi SAM là `void`?** Phép cộng thuần `n + 1` không đủ; lời gọi phương thức như `println` hoặc `list.add` có thể hợp lệ.
7. **Dấu `;` đặt đúng chỗ?** Sau câu lệnh trong block, sau toàn bộ khai báo; không viết `return` bên ngoài block.
8. **Đã xem xét `null`, ngoại lệ, shared mutable state và biến captured?** Cú pháp hợp lệ chưa chắc chương trình an toàn hoặc đúng nghiệp vụ.
9. **Đã thử các trường hợp biên và đối chiếu đầu ra?** Không chỉ thử dữ liệu thuận lợi.

## 11. Tổng kết

**Thân biểu thức** (`x -> expression`) phù hợp khi hành vi thể hiện được bằng một biểu thức. Nếu SAM có kết quả, giá trị biểu thức được dùng làm kết quả; nếu SAM trả `void`, biểu thức phải phù hợp ngữ cảnh *statement expression*. Không viết `return` trong thân biểu thức.

**Thân khối lệnh** (`x -> { statements; }`) cho phép nhiều câu lệnh và kiểm soát luồng rõ ràng. Với SAM trả giá trị, cần bảo đảm các đường đi hợp lệ trả về giá trị hoặc ném exception; với SAM trả `void`, chỉ `return;` không có giá trị mới phù hợp. Cả hai dạng cùng dựa trên hợp đồng functional interface và tuân thủ các quy tắc Java về phạm vi biến, ngoại lệ, kiểu dữ liệu và side effect.

Để tra cứu cú pháp chính xác, xem Java Language Specification **`15.27 Lambda Expressions`**, đặc biệt **`15.27.2 Lambda Body`** và **`15.27.3 Type of a Lambda Expression`**, cùng Javadoc `java.util.function.Function`, `Consumer`, `Predicate` và `Supplier`.
