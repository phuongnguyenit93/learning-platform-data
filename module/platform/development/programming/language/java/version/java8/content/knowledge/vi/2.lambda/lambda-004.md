# Lambda trong Java: phần thân biểu thức và khối lệnh

Khi viết lambda, phần nằm **sau dấu `->`** là *lambda body*: đoạn công việc chạy mỗi khi phương thức trừu tượng của functional interface được gọi. Java hỗ trợ hai hình thức thân lambda từ Java 8 đến các phiên bản Java hiện đại:

1. **Expression body (thân biểu thức):** một biểu thức đơn, viết ngắn gọn và thường phù hợp với phép chuyển đổi, so sánh, kiểm tra hoặc lời gọi phương thức.
2. **Block body (thân khối lệnh):** một khối trong cặp dấu `{ }`, chứa câu lệnh, khai báo biến cục bộ, điều kiện, xử lý ngoại lệ và `return` tường minh.

Hai dạng phục vụ cùng mô hình lambda. Việc chọn dạng nào phụ thuộc vào **hợp đồng trả về của functional interface** và độ phức tạp của hành vi, không phải quy định rằng mọi lambda chỉ được viết một dòng.

## 1. Nhìn vào vị trí và vai trò của body

Cú pháp khái quát:

```java
(parameters) -> expression
(parameters) -> {
    statements;
}
```

Đây là **mẫu cú pháp minh họa**, không phải mã chạy độc lập. Phía trái `->` khai báo tham số; phía phải định nghĩa hành vi. Lambda cần một *target type* là functional interface, chẳng hạn `Function<T,R>`, `Predicate<T>`, `Consumer<T>`, `Supplier<T>` hoặc `Runnable`.

```java
Function<Integer, Integer> square = n -> n * n;
Function<Integer, Integer> squareBlock = n -> {
    int result = n * n;
    return result;
};
```

Đây là **đoạn minh họa**, cần `import java.util.function.Function;` và đặt trong phương thức hoặc vị trí khai báo thích hợp. Cả hai đều có kiểu `Function<Integer,Integer>`: nhận một số nguyên, trả về bình phương. Thân lambda không chạy ngay khi gán cho biến; nó chạy khi gọi `square.apply(4)` hoặc `squareBlock.apply(4)`.

Một số chi tiết cú pháp dễ nhầm:

- `n -> n * n`: không có dấu `;` **bên trong** phần thân biểu thức; dấu `;` cuối dòng là dấu kết thúc câu lệnh khai báo/gán lambda.
- `n -> { return n * n; }`: dấu `;` nằm **sau** `return` vì `return` là câu lệnh Java.
- Một tham số suy luận kiểu có thể viết `n -> ...` hoặc `(n) -> ...`; nhiều tham số dùng ngoặc `(a, b) -> ...`; không có tham số dùng `() -> ...`.
- Dấu ngoặc đơn bao quanh biểu thức như `n -> (n * n)` không biến biểu thức thành khối lệnh; chỉ cặp `{ }` mới tạo block body.

## 2. Expression body: một biểu thức, kết quả có thể được trả về ngầm định

Expression body gồm **đúng một biểu thức** sau `->`. Khi functional interface yêu cầu trả về giá trị, kết quả biểu thức được dùng làm kết quả gọi lambda, vì vậy không viết từ khóa `return`.

```java
Function<String, Integer> length = text -> text.length();
Predicate<Integer> positive = number -> number > 0;
Supplier<String> greeting = () -> "Xin chào";
BinaryOperator<Integer> sum = (left, right) -> left + right;
```

Đây là **đoạn minh họa**; cần `import java.util.function.*;`. `length.apply("Java")` trả `4`; `positive.test(5)` là `true`; `greeting.get()` trả chuỗi; `sum.apply(3, 4)` trả `7`. Target type cho biết giá trị biểu thức phải tương thích với kiểu kết quả nào.

Expression body cũng có thể gọi phương thức trả về `void` trong một functional interface trả `void`:

```java
Consumer<String> print = text -> System.out.println(text);
Runnable task = () -> System.out.println("Đã chạy");
```

Đây là **đoạn minh họa**; cần `import java.util.function.Consumer;`. Một điểm tinh tế: với target trả `void`, thân biểu thức còn có thể là *statement expression* có kết quả, như lời gọi phương thức trả `boolean`; giá trị đó sẽ bị bỏ qua. Ví dụ `Consumer<String> append = text -> list.add(text);` có thể hợp lệ nếu `list` là danh sách phù hợp. Khả năng này bắt nguồn từ quy tắc tương thích của lambda; **không** có nghĩa mọi biểu thức sinh giá trị đều dùng được cho `Consumer`.

Expression body nên được ưu tiên khi hành vi đơn giản và tên hàm/biểu thức diễn đạt rõ mục đích. Nếu cần khai báo biến trung gian, nhiều bước hoặc nhánh `if` chứa các câu lệnh, đổi sang block body.

## 3. Block body: nhiều câu lệnh, phạm vi cục bộ và return tường minh

Một block body cho phép dùng câu lệnh Java thông thường:

```java
Predicate<String> nonBlank = value -> {
    if (value == null) {
        return false;
    }
    String cleaned = value.trim();
    return !cleaned.isEmpty();
};
```

Đây là **đoạn minh họa**, cần `import java.util.function.Predicate;`. Khối này kiểm tra `null` trước, tạo biến trung gian `cleaned` rồi trả về kết quả. Biến khai báo trong khối có phạm vi bên trong khối; không thể truy cập biến đó từ ngoài lambda.

Một block chỉ cần một câu lệnh cũng hoàn toàn hợp lệ:

```java
Function<Integer, Integer> plusOne = n -> {
    return n + 1;
};
```

**Quy tắc quan trọng:** Trong block body trả về giá trị, phải viết `return expression;` trên mọi đường thực thi có thể hoàn tất bình thường. Dấu ngoặc nhọn **không** biến biểu thức cuối thành giá trị trả về ngầm định. Vì thế, `n -> { n + 1; }` sai cả về việc dùng phép cộng như một statement độc lập lẫn thiếu `return`.

Block body hữu ích khi:

- Cần nhiều câu lệnh để kiểm tra dữ liệu, chuẩn hóa rồi tính kết quả.
- Có nhánh `if`/`else` hoặc `switch` để đưa ra các đường trả về khác nhau.
- Cần `try`/`catch` để chuyển lỗi thành quy tắc xử lý có chủ đích.
- Cần ghi log hay đo thời gian trước khi trả kết quả; tuy nhiên tác dụng phụ phải được kiểm soát.

Không nên chuyển mọi lambda sang block chỉ để thêm dòng: thân dài bất thường có thể là dấu hiệu cần tách một phương thức đặt tên rõ ràng rồi truyền bằng method reference.

## 4. Phân biệt lambda trả giá trị và lambda trả void

**Target type**, không phải chỉ hình dáng code, quyết định lambda phải trả `void` hay một giá trị. Đây là bảng quy tắc thực hành:

| Loại body | Functional interface trả giá trị | Functional interface trả `void` |
| --- | --- | --- |
| Biểu thức | Biểu thức phải tạo giá trị phù hợp, như `n -> n + 1` | Chỉ hợp lệ nếu là *statement expression* phù hợp, như `x -> System.out.println(x)` |
| Khối lệnh | Mọi đường đi hoàn tất cần trả bằng `return value;` | Có thể kết thúc tự nhiên hoặc dùng `return;`, không dùng `return value;` |
| Khối chỉ `throw` | Có thể tương thích khi các đường đi không hoàn tất bình thường | Cũng có thể tương thích |

Các ví dụ độc lập về mặt cú pháp (chỉ minh họa, cần import và ngữ cảnh khai báo):

```java
// Trả về giá trị: đúng
Function<Integer, Integer> f1 = n -> n + 1;
Function<Integer, Integer> f2 = n -> { return n + 1; };

// Trả về void: đúng
Consumer<String> c1 = s -> System.out.println(s);
Consumer<String> c2 = s -> {
    System.out.println(s);
    return; // hợp lệ, nhưng không bắt buộc
};
```

Với block body trả giá trị, một `if` không có `else` chỉ hợp lệ nếu có đường trả giá trị cuối cùng:

```java
Function<Integer, String> classify = score -> {
    if (score >= 80) {
        return "Giỏi";
    }
    return "Cần luyện tập";
};
```

Ví dụ trên là **đoạn minh họa**, cần `import java.util.function.Function;`. Nếu bỏ `return "Cần luyện tập";`, đường đi khi `score < 80` sẽ không trả giá trị. Trình biên dịch báo lỗi.

Theo Java Language Specification, một **void-compatible block** chỉ có các `return;` không kèm giá trị (nếu có); một **value-compatible block** phải không thể hoàn tất bình thường và mọi `return` phải kèm biểu thức. Một khối chỉ luôn ném ngoại lệ có thể tương thích cả hai kiểu; quy tắc này đặc biệt hữu ích khi giải thích lỗi biên dịch hoặc overload, nhưng không nên lạm dụng khối cố ý ném lỗi để thiết kế API.

## 5. Những lỗi biên dịch thường gặp và cách sửa

Các đoạn đánh dấu **SAI** dưới đây chỉ để nhận diện lỗi, **không** đưa chung vào chương trình đang biên dịch.

### Lỗi 1: Thêm return vào expression body

```java
// SAI: return là statement, không phải expression ở vị trí này
Function<Integer, Integer> f = n -> return n + 1;

// ĐÚNG: biểu thức
Function<Integer, Integer> a = n -> n + 1;

// ĐÚNG: khối có return
Function<Integer, Integer> b = n -> { return n + 1; };
```

### Lỗi 2: Có ngoặc khối nhưng không return giá trị

```java
// SAI: biểu thức cộng không được đứng độc lập như statement;
// đồng thời không trả được Integer
Function<Integer, Integer> f = n -> { n + 1; };

// ĐÚNG
Function<Integer, Integer> g = n -> {
    int result = n + 1;
    return result;
};
```

### Lỗi 3: Trả giá trị cho một target void

```java
// SAI: Consumer.accept trả void
Consumer<String> c = s -> { return s.length(); };

// ĐÚNG: thực hiện hành động mà không trả giá trị
Consumer<String> a = s -> { System.out.println(s.length()); };

// ĐÚNG: đổi target để có kết quả
Function<String, Integer> f = s -> s.length();
```

### Lỗi 4: Mọi biểu thức đều hợp lệ cho Consumer?

```java
// SAI: phép cộng không phải một statement expression
Consumer<Integer> c = n -> n + 1;

// ĐÚNG: dùng Function khi cần kết quả
Function<Integer, Integer> f = n -> n + 1;

// ĐÚNG: dùng một phương thức/hành động dưới Consumer
Consumer<Integer> print = n -> System.out.println(n + 1);
```

Một *statement expression* là biểu thức Java có thể đứng thành câu lệnh, ví dụ lời gọi phương thức, phép gán, tăng/giảm hay tạo đối tượng. `n + 1` là biểu thức tính toán nhưng **không** phải statement expression, nên không thể dùng trực tiếp cho thân expression của target `void`.

### Lỗi 5: Thiếu return trên một nhánh

```java
// SAI: n <= 0 thì block kết thúc mà không trả giá trị
Function<Integer, Integer> f = n -> {
    if (n > 0) {
        return n;
    }
};

// ĐÚNG: mọi đường đi có kết quả
Function<Integer, Integer> g = n -> {
    if (n > 0) {
        return n;
    }
    return 0;
};
```

Ngoài ra, không trộn `return;` và `return value;` tùy tiện trong cùng block: chúng biểu thị hai loại hợp đồng trả về khác nhau.

## 6. Phạm vi biến, return và tác dụng phụ trong lambda body

Block body có cú pháp gần giống thân phương thức, nhưng cần hiểu **đang trở về từ đâu**:

- `return` bên trong lambda trả về từ lần gọi lambda, **không** trả về từ phương thức bao ngoài đang tạo lambda.
- `this` trong lambda chỉ cùng đối tượng như ở phạm vi bao ngoài; lambda không tạo một `this` mới như anonymous class.
- Biến cục bộ ở phạm vi ngoài mà lambda sử dụng phải là `final` hoặc *effectively final*: được gán xong rồi không bị gán lại.
- Có thể gọi phương thức trên object được tham chiếu từ biến effectively final, nhưng thao tác sửa trạng thái chia sẻ cần được đánh giá cẩn thận, đặc biệt khi callback chạy bất đồng bộ hoặc Stream song song.
- Trong body có thể `throw` exception, nhưng checked exception phải được khai báo trong hợp đồng phương thức trừu tượng hoặc được bắt/chuyển xử lý phù hợp.

Ví dụ về capture (đoạn minh họa):

```java
int threshold = 10;
Predicate<Integer> isLarge = n -> n > threshold;
// threshold = 20; // nếu bỏ comment, biến không còn effectively final
```

Ví dụ về biến nội bộ của block:

```java
Function<String, String> normalize = input -> {
    String trimmed = input.trim();
    return trimmed.toLowerCase(java.util.Locale.ROOT);
};
// trimmed chỉ tồn tại bên trong lambda, không tồn tại ở đây
```

Cần phân biệt lambda trong ứng dụng với đoạn callback nặng tác động phụ. Khi một block vừa ghi dữ liệu, vừa thay đổi state, vừa tính kết quả, khó kiểm thử hơn là tách các trách nhiệm thành phương thức chuyên biệt.

## 7. Ví dụ chạy hoàn chỉnh: đặt hai body cạnh nhau

Chương trình dùng một expression body tính gấp đôi, block body tính gấp đôi có biến trung gian, block kiểm tra điều kiện và hai Consumer thực hiện tác động. Đồng thời nó minh họa một method invocation trả `boolean` được dùng hợp lệ trong `Consumer` với kết quả bị bỏ qua.

Lưu thành tệp **LambdaBodyDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.IntUnaryOperator;
import java.util.function.Predicate;

public class LambdaBodyDemo {
    public static void main(String[] args) {
        IntUnaryOperator doubleExpression = n -> n * 2;

        IntUnaryOperator doubleBlock = n -> {
            int result = n * 2;
            return result;
        };

        Predicate<String> hasText = value -> {
            if (value == null) {
                return false;
            }
            String trimmed = value.trim();
            return !trimmed.isEmpty();
        };

        Consumer<String> showExpression =
                text -> System.out.println("expr: " + text);

        Consumer<String> showBlock = text -> {
            String cleaned = text.trim();
            System.out.println("block: " + cleaned);
        };

        List<String> tags = new ArrayList<>();
        Consumer<String> saveTag = tag -> tags.add(tag);

        System.out.println(doubleExpression.applyAsInt(5));
        System.out.println(doubleBlock.applyAsInt(6));
        System.out.println(hasText.test("  Java  "));
        System.out.println(hasText.test("   "));
        showExpression.accept("hello");
        showBlock.accept("  world  ");
        saveTag.accept("Lambda");
        System.out.println(tags);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac LambdaBodyDemo.java
java LambdaBodyDemo
```

**Standard output:**

```text
10
12
true
false
expr: hello
block: world
[Lambda]
```

Giải thích:

1. `IntUnaryOperator` có phương thức `applyAsInt(int)` trả `int` nên expression body lấy kết quả `n * 2` và block body trả tường minh `result`.
2. `Predicate<String>` có `test(String)` trả `boolean`; mỗi đường đi trong block `hasText` trả `true` hoặc `false`. Kiểm tra `null` ngăn lỗi gọi `trim()` trên giá trị vắng mặt.
3. Cả hai `Consumer<String>` trả `void`; expression body gọi `println` còn block body có biến trung gian và câu lệnh in.
4. `List.add` trả `boolean`, nhưng `tag -> tags.add(tag)` vẫn phù hợp cho `Consumer` vì lời gọi phương thức là *statement expression*; giá trị `boolean` bị bỏ qua. `tags` không bị gán lại, nên được lambda capture; danh sách bên trong có thể được sửa. Trong tình huống này chạy tuần tự, không có tranh chấp luồng.

Có thể thay `showExpression` bằng method reference `System.out::println` nếu không cần tiền tố `expr: `. Chọn cách diễn đạt khiến ý định dễ hiểu nhất.

## 8. Cách quyết định trong code thật

| Cần làm | Nên chọn | Vì sao |
| --- | --- | --- |
| Một phép toán hoặc một lời gọi rõ ý nghĩa | Expression body | Ngắn, ít thành phần cú pháp |
| Kiểm tra `null` rồi tính toán với biến trung gian | Block body | Điều kiện và đường `return` tường minh |
| Chỉ log/ghi một kết quả | Expression body với lời gọi phương thức, hoặc method reference | Phù hợp target `void` |
| Có nhiều nhánh kết quả | Block body hoặc tách hàm | Giúp nhìn đủ các đường trả về |
| Thân lambda dài, nhiều mức lồng, có nhiều trách nhiệm | Tách phương thức đặt tên rồi gọi/đưa method reference | Dễ đọc, tái sử dụng và kiểm thử |
| Nhiều tác động phụ lên trạng thái dùng chung | Xem lại cấu trúc xử lý và đồng bộ | Tránh lỗi và khó dự đoán khi thực thi song song |

**Checklist khi review một lambda body:**

- Functional interface cần `void` hay một kiểu kết quả? Body có tương thích không?
- Nếu là expression body, có đúng một biểu thức và không có `return` không?
- Nếu là block trả giá trị, mọi đường thực thi hợp lệ có `return expression;` không?
- Nếu là block trả `void`, có tránh `return value;` không?
- Những biến bao ngoài có effectively final? Body có thay đổi state chia sẻ ngoài dự kiến không?
- Body có thực sự đơn giản, hay nên chuyển phần thân thành một phương thức có tên?

### Thực hành ngắn

1. Chuyển `Function<Integer,Integer> increment = x -> x + 1;` sang block body, giữ nguyên hành vi.
2. Viết `Predicate<String>` dùng block để trả `false` khi chuỗi là `null` và `true` khi chuỗi bắt đầu bằng `"J"`.
3. Giải thích tại sao `Consumer<Integer> a = n -> n * 2;` không biên dịch, còn `Consumer<Integer> b = n -> System.out.println(n * 2);` lại hợp lệ.
4. Giải thích khác biệt giữa `return` trong lambda và `return` của phương thức bao ngoài.

Lời giải gợi ý cho bài 1: `x -> { return x + 1; }`. Bài 2: `s -> { if (s == null) return false; return s.startsWith("J"); }`. Bài 3: phép nhân thuần túy không phải statement expression; lời gọi phương thức `println` là statement expression. Bài 4: `return` chỉ kết thúc lần thực thi của chính lambda.

### Tài liệu chính thức

- [Java Language Specification, `15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27)
- [Java Language Specification, `15.27.2 Lambda Body](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.2)
- [Java Language Specification, `15.27.3 Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27.3)
- [Java SE 25, java.util.function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html)
