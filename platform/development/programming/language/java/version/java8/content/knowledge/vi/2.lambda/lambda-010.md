# Quy tắc tên biến và khác biệt với anonymous class trong Lambda (Java 8)

## Bài học này giải quyết điều gì?

Khi viết hoặc refactor lambda, lỗi phổ biến là tưởng rằng chỉ cần thay `new Runnable() { ... }` bằng `() -> ...` mà không thay đổi ngữ nghĩa. Thực tế, **lambda và anonymous class khác nhau ở phạm vi tên, `this`, `super` và khả năng khai báo thành viên**. Cả hai lại có chung quy tắc đối với **biến cục bộ được capture**: phải là `final` hoặc *effectively final*.

Bài học thuộc chủ đề **Java 8 / Lambda**, tập trung vào những quy tắc Java vẫn áp dụng trong các JDK được duy trì hiện nay. Ví dụ chạy bằng JDK hiện đại, nhưng dùng API/cú pháp có từ Java 8 để có thể kiểm tra với `javac --release 8`. Không cần cài một runtime cũ chỉ để học lambda.

Sau bài học, bạn có thể: đặt tên tham số lambda hợp lệ, nhận diện shadowing, giải thích biến được capture, phân biệt `this` của lambda và anonymous class, viết ví dụ chạy được và refactor mà vẫn giữ hành vi.

## 1. Quy tắc tên tham số lambda

Lambda triển khai hành vi cho một **functional interface** có một phương thức trừu tượng theo quy tắc ngôn ngữ. Kiểu của mỗi tham số lambda được suy ra từ *target type*, chẳng hạn `IntUnaryOperator`, `IntBinaryOperator`, `Predicate<String>` hoặc `Runnable`.

~~~java
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;

// Các câu lệnh đặt bên trong một phương thức.
IntUnaryOperator square = value -> value * value;
IntUnaryOperator next = (int value) -> value + 1;
IntBinaryOperator add = (left, right) -> left + right;
IntBinaryOperator multiply = (int left, int right) -> left * right;
~~~

**Quy tắc cú pháp:**

- Với **một tham số suy luận kiểu**, có thể bỏ dấu ngoặc: `value -> value + 1`. Cách viết `(value) -> value + 1` cũng hợp lệ.
- Với **không tham số**, viết `() -> ...`. Với **từ hai tham số trở lên**, phải có ngoặc: `(left, right) -> ...`.
- Nếu khai báo kiểu rõ ràng, phải khai báo **cho tất cả tham số**: `(int left, int right)`. Không trộn `(int left, right)` hoặc `(left, int right)`.
- Các tham số cùng lambda không thể có tên trùng nhau: `(value, value) -> ...` là lỗi biên dịch.
- Tên phải là identifier hợp lệ; chọn `order`, `item`, `left`, `right` để đọc được vai trò. `x` hay `n` hữu ích trong phép toán rất ngắn, nhưng nên tránh ở nghiệp vụ dài.

~~~java
// MINH HỌA LỖI: bỏ dấu // sẽ không biên dịch được.
// IntBinaryOperator bad1 = (int a, b) -> a + b;
// IntBinaryOperator bad2 = (a, int b) -> a + b;
// IntBinaryOperator bad3 = (x, x) -> x + x;
~~~

**Mốc phiên bản:** `(var a, var b) -> ...` là biến thể suy luận kiểu được thêm sau Java 8 (Java 11), không sử dụng khi target `--release 8`. Ký hiệu `_` dùng như tham số không tên theo quy tắc của các Java mới cũng không phải cú pháp tham số lambda Java 8. Đừng lấy cú pháp của phiên bản mới để giải thích một ví dụ yêu cầu Java 8 compatibility.

## 2. Lambda không tạo một scope kiểu class mới

Lambda có tham số và block riêng, nhưng **không tạo thêm một cấp phạm vi tên như một khai báo lớp**. Vì vậy, nếu một local variable hoặc method parameter đã nằm trong scope tại vị trí lambda, bạn **không thể** dùng lại đúng tên đó để khai báo tham số lambda hay local variable mới bên trong lambda.

~~~java
import java.util.function.IntUnaryOperator;

// Đặt trong một phương thức:
int offset = 10;

// HỢP LỆ: tham số có tên khác; offset ngoài được đọc.
IntUnaryOperator plusOffset = number -> number + offset;

// KHÔNG HỢP LỆ: tên tham số trùng local ở scope bao quanh.
// IntUnaryOperator wrong = offset -> offset + 1;

// KHÔNG HỢP LỆ: tạo local mới trùng tên trong block lambda.
// Runnable alsoWrong = () -> {
//     int offset = 99;
//     System.out.println(offset);
// };
~~~

Thêm ngoặc nhọn `{ ... }` không làm biến bên ngoài biến mất khỏi scope. Với lambda lồng nhau, một tên ở lambda ngoài cũng không thể bị khai báo lại trong lambda trong nếu phạm vi còn chồng lấp.

~~~java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

// Đặt trong một phương thức:
Function<Integer, IntUnaryOperator> good =
    base -> value -> base + value;

// Sai vì lambda trong khai báo lại tên "value" từ lambda ngoài:
// Function<Integer, IntUnaryOperator> bad =
//     value -> value -> value + 1;
~~~

### Trường hợp tên trùng field của đối tượng

**Field không giống local variable.** Tham số lambda có thể có tên trùng field; khi đó tên không kèm qualifier chỉ tham số, còn `this.fieldName` chỉ field của object bao quanh, nếu lambda nằm trong instance context.

~~~java
// Trong instance method của một class có field: private int limit = 10;
IntUnaryOperator adjust = limit -> limit + this.limit;
~~~

Ví dụ là trích đoạn; trong `static` context, không thể dùng `this` vì không có enclosing instance. Hạn chế cố tình dùng tên field làm tên tham số nếu điều đó khiến người đọc nhầm hai giá trị.

## 3. Anonymous class có scope riêng nên shadowing khác

Anonymous class được tạo bằng `new Interface() { ... }` hoặc `new BaseClass(...) { ... }`. Bên trong nó là một khai báo class với thành viên/phương thức riêng. Khi khai báo một parameter của phương thức trong anonymous class, có thể **dùng lại tên local variable của phương thức bên ngoài**: tên bên trong sẽ che tên bên ngoài.

~~~java
import java.util.function.IntUnaryOperator;

// Trong một phương thức:
int offset = 10;

IntUnaryOperator oldStyle = new IntUnaryOperator() {
    @Override
    public int applyAsInt(int offset) {  // HỢP LỆ
        return offset + 1;              // offset là tham số, không phải số 10.
    }
};

// Không thể thay máy móc bằng:
// IntUnaryOperator wrong = offset -> offset + 1;

// Cách thay hợp lệ, giữ biểu thức tính toán cũ:
IntUnaryOperator correct = number -> number + 1;
~~~

`oldStyle.applyAsInt(5)` và `correct.applyAsInt(5)` đều trả **6**. Tham số anonymous class được khai báo trong lớp lồng nên được phép shadow biến local bên ngoài. Khi chuyển sang lambda, tham số đó không được khai báo lại trùng tên local đang tồn tại.

Nếu muốn **dùng cả hai biến**, phải tránh shadowing, ví dụ đặt tham số `number` rồi viết `number + offset`. Chú ý rằng local variable không có cú pháp `this.offset`: `this` dành cho thành viên của instance, không giải quyết được việc truy xuất một outer local đã bị che.

## 4. Biến local được capture: quy tắc áp dụng cho cả hai

Capture nghĩa là lambda hoặc anonymous class đọc local variable/parameter được khai báo ở một phạm vi bên ngoài. Java yêu cầu biến local đó là **`final` hoặc effectively final**:

- `final`: đã khai báo không thể gán lại.
- *Effectively final*: không ghi `final` nhưng cũng không có phép gán lại sau khởi tạo hợp lệ.

~~~java
import java.util.function.IntUnaryOperator;

// Trong một phương thức:
int factor = 3; // effectively final

IntUnaryOperator byLambda = value -> value * factor;

IntUnaryOperator byAnonymous = new IntUnaryOperator() {
    @Override
    public int applyAsInt(int value) {
        return value * factor;
    }
};

// Nếu mở comment dòng dưới, cả hai capture trở thành không hợp lệ:
// factor++;
~~~

**Bẫy 1:** Quy tắc này áp dụng cho **local được capture**, không có nghĩa mọi tham số lambda đều tự động `final`. Tham số bình thường có thể được gán lại trong thân lambda, dù nên tránh lạm dụng vì code khó hiểu.

**Bẫy 2:** Một **tham chiếu local effectively final** có thể trỏ đến object vẫn mutable. `list.add(...)` không gán lại biến `list`, còn `list = new ArrayList<>()` là phép gán lại.

~~~java
import java.util.ArrayList;
import java.util.List;

// Trong một phương thức:
List<String> names = new ArrayList<String>();
Runnable append = () -> names.add("Lan");
append.run(); // Hợp lệ; names trỏ đến cùng object.

// Sai nếu bỏ comment: gán lại tham chiếu local được capture.
// names = new ArrayList<String>();
~~~

Không vì thế mà mặc định sửa một `ArrayList` từ nhiều thread là thread-safe. Với Stream, callback, xử lý bất đồng bộ, tránh side effect lên dữ liệu chung; nếu cần trạng thái chia sẻ, dùng cấu trúc hoặc cơ chế đồng bộ phù hợp.

## 5. `this` và `super`: khác biệt ngữ nghĩa khi refactor

**Lambda:** trong instance method, `this` chỉ **instance của class bao quanh** nơi lambda xuất hiện. `super`, field và lời gọi phương thức không có qualifier được hiểu theo ngữ cảnh từ vựng bao quanh.

**Anonymous class:** `this` chỉ **instance của anonymous class**, vì bạn đang ở trong method của một class khác. `super` nói đến superclass của anonymous class. Muốn chỉ instance của class ngoài, viết `OuterClass.this`.

Ví dụ: nếu class bao quanh có field `label = "outer"` và anonymous class có field `label = "anonymous"`, thì:
- `this.label` trong lambda là `outer`.
- `this.label` trong anonymous class là `anonymous`.
- `OuterClass.this.label` trong anonymous class là `outer`.

Trong static method, lambda không làm xuất hiện enclosing instance để dùng `this`; anonymous instance do `new` tạo vẫn có `this` riêng bên trong phương thức của nó.

**Kết luận khi refactor:** không thay anonymous class thành lambda theo mẫu tìm-kiếm/thay-thế nếu code đang dùng `this`, `super`, field/phương thức chưa qualified hoặc phụ thuộc vào object identity. Cần hiểu từng tham chiếu trước khi quyết định tương đương hành vi.

## 6. Bài thực hành hoàn chỉnh, chạy trên JDK được cập nhật

Tạo tệp **`LambdaNames.java`** với encoding UTF-8:

~~~java
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;

public class LambdaNames {
    private final String label = "outer";

    void demonstrate() {
        int offset = 10;

        // Lambda đọc biến offset bên ngoài.
        IntUnaryOperator lambda = number -> number + offset;

        // Anonymous class có tham số cùng tên với local bên ngoài.
        IntUnaryOperator anonymous = new IntUnaryOperator() {
            @Override
            public int applyAsInt(int offset) {
                return offset + 1;
            }
        };

        System.out.println("lambda result = " + lambda.applyAsInt(5));
        System.out.println("anonymous result = " + anonymous.applyAsInt(5));

        Runnable lambdaThis = () ->
            System.out.println("lambda this = " + this.label);

        Runnable anonymousThis = new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println("anonymous this = " + this.label);
                System.out.println("enclosing this = "
                    + LambdaNames.this.label);
            }
        };

        lambdaThis.run();
        anonymousThis.run();

        IntBinaryOperator add = (left, right) -> left + right;
        System.out.println("sum = " + add.applyAsInt(2, 3));
    }

    public static void main(String[] args) {
        new LambdaNames().demonstrate();
    }
}
~~~

Trên JDK đang được nhà cung cấp duy trì và có hỗ trợ `--release 8`:

~~~text
javac --release 8 -encoding UTF-8 LambdaNames.java
java LambdaNames
~~~

**Stdout chính xác, theo đúng thứ tự:**

~~~text
lambda result = 15
anonymous result = 6
lambda this = outer
anonymous this = anonymous
enclosing this = outer
sum = 5
~~~

**Giải thích số và tên:**

1. Lambda nhận `number=5`, cộng local `offset=10` → 15.
2. Anonymous class nhận tham số tên `offset` với giá trị 5, nên phép `offset + 1` → 6. Nó không dùng biến `offset` của method bao quanh.
3. `this.label` trong lambda truy cập `LambdaNames.label` → `outer`.
4. `this.label` trong anonymous class truy cập field riêng → `anonymous`.
5. `LambdaNames.this.label` trỏ rõ instance ngoài → `outer`.
6. `IntBinaryOperator` nhận 2 và 3 rồi tính `2 + 3 = 5`.

Toàn bộ mã dùng API Java 8 và biên dịch được với `--release 8` trên JDK hỗ trợ tùy chọn đó. Biên dịch mục tiêu Java 8 khác với việc cần chạy ứng dụng production trên một JVM 8 không được cập nhật. Chính sách runtime là quyết định độc lập của dự án.

## 7. Tự nhận diện lỗi và sửa đúng bản chất

### A. Trùng tên parameter với outer local

~~~java
// Trong một phương thức:
int count = 4;
// IntUnaryOperator wrong = count -> count + 1; // lỗi shadowing
IntUnaryOperator correct = value -> value + count;
~~~

### B. Khai báo lại local trong block lambda

~~~java
// Trong một phương thức:
String message = "outer";
// Runnable wrong = () -> { String message = "inner"; }; // lỗi
Runnable correct = () -> {
    String text = message + " value";
    System.out.println(text);
};
~~~

### C. Gán lại biến local đã capture

~~~java
// Trong một phương thức:
int offset = 7;
// IntUnaryOperator wrong = n -> n + offset;
// offset++; // Nếu cả hai dòng mở comment, compilation sẽ thất bại.
final int stableOffset = offset;
IntUnaryOperator correct = n -> n + stableOffset;
~~~

### D. Nhầm kiểu và tên tham số

~~~java
// Sai: IntBinaryOperator wrong = (int first, second) -> first + second;
IntBinaryOperator good1 = (first, second) -> first + second;
IntBinaryOperator good2 = (int first, int second) -> first + second;
~~~

### E. Thay anonymous class bằng lambda làm đổi `this`

~~~java
// Đặt trong instance method:
// Runnable original = new Runnable() {
//     @Override public void run() {
//         System.out.println(this.toString()); // anonymous instance
//     }
// };
// Runnable replaced = () -> System.out.println(this.toString());
// "this" giờ là instance của class bao quanh, không cùng đối tượng.
~~~

Những đoạn mục 7 là **trích đoạn để chèn trong một phương thức**, cần đặt import cho kiểu sử dụng; các dòng có `//` cố ý minh họa **mã không hợp lệ nếu bỏ comment**. Chương trình ở mục 6 mới là file chạy độc lập với output đầy đủ.

## 8. So sánh lambda và anonymous class

| Tiêu chí | Lambda | Anonymous class |
| --- | --- | --- |
| Target type | Functional interface | Có thể triển khai interface hoặc mở rộng class |
| Tên tham số trùng local ngoài | Không được khi scope chồng lấp | Được phép trong method của nested class |
| Capture local ngoài | `final`/effectively final | Cũng `final`/effectively final |
| `this` trong instance context | Instance của enclosing class | Instance anonymous class |
| `super` | Ngữ cảnh enclosing class | Superclass của anonymous class |
| Khai báo field/method bổ sung | Không có class body | Có thể có field/method riêng |
| Bảo đảm object identity | Không nên dựa vào identity/cấp phát mỗi lần | `new` tạo instance của anonymous class |
| Phù hợp | Hành vi ngắn cho SAM | Cần state riêng, mở rộng class, override nhiều phương thức |

Khi callback chỉ biểu diễn một phép chuyển đổi hoặc điều kiện, lambda thường dễ đọc hơn. Nếu chỉ chuyển tham số tới method có sẵn, cân nhắc method reference (`System.out::println`). Nếu cần trạng thái instance riêng hoặc nhiều phương thức, anonymous class hoặc named class có thể hợp lý hơn. **Không lấy độ ngắn cú pháp làm bằng chứng tương đương hành vi.**

## 9. Bài tập tự đánh giá

1. Viết `int base = 7;` và lambda với tham số `base`; giải thích lỗi, đổi tên tham số thành `value`. Đặt thân `value * 2 + base`, thử `value=3`; kết quả phải là **13**.
2. Trong ví dụ chính, đổi tham số method của anonymous class từ `offset` thành `number`, đổi body thành `number + offset`; với input 5, kết quả đổi từ **6** thành **15**. Giải thích nguồn hai giá trị.
3. Thêm `offset++;` trước khi khai báo lambda; phân tích tại sao `offset` không còn effectively final và cả anonymous class nếu capture local đó cũng phải tuân thủ.
4. So sánh kết quả `this.label` và `LambdaNames.this.label`; lý giải vì sao ý nghĩa của `this` đổi khi chuyển từ anonymous class sang lambda.
5. Tạo lambda hai tham số `(int left, int right)` và thử thay bằng `(int left, right)`; dùng quy tắc suy luận kiểu để giải thích compile error.
6. Chạy `javac --release 8` và `java` trên JDK được bảo trì, so sánh stdout với mục 6; phân biệt khả năng tương thích bytecode/API với việc một runtime cũ có còn được cập nhật bảo mật hay không.

**Tiêu chí hoàn thành:** bạn phát hiện được lỗi tên biến và capture ngay ở compile-time, biết `this` trỏ đến đâu, và refactor được một anonymous class thành lambda mà vẫn giữ hành vi và tính dễ đọc.

## Tài liệu đặc tả còn hiệu lực

- Java Language Specification, SE 25, `15.27 Lambda Expressions: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27
- JLS, `6.3 Scope of a Declaration và `6.4 Shadowing and Obscuring: https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.4
- JLS, `15.9.5 Anonymous Class Declarations: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9.5
- Java Compiler `javac`, `--release`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html

Các liên kết dẫn tới đặc tả và tài liệu compiler đang được áp dụng; những tính năng mới hơn Java 8 được ghi rõ để không trộn lẫn cú pháp của các phiên bản.