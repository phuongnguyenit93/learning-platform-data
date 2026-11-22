# Phạm vi từ vựng, `this` và `super` trong Java Lambda

## 1. Mục tiêu

Lambda được bổ sung từ Java 8 để diễn đạt hành vi ngắn gọn dưới dạng một **functional interface**. Điểm rất quan trọng khi đọc hoặc refactor lambda: tên biến, `this` và `super` trong thân lambda được hiểu theo **ngữ cảnh từ vựng bao quanh (lexical context)**, khác với anonymous inner class.

Sau bài này, bạn sẽ có thể:

- Giải thích lexical scope và cách lambda tìm tên của local variable, parameter, field, `this`, `super`.
- Phân biệt `this` của lambda với `this` của anonymous class.
- Hiểu điều kiện **final hoặc effectively final** khi lambda truy cập biến local bên ngoài.
- Truy cập superclass bằng `super` ngay trong lambda khi ngữ cảnh bao quanh cho phép.
- Nhận diện lỗi shadowing, static context, trạng thái dùng chung và những giả định sai về identity của lambda.
- Áp dụng đúng các quy tắc này trong Java hiện đại; đây vẫn là ngữ nghĩa của lambda, không phải tính năng đã lỗi thời.

## 2. Lexical scope là gì?

**Lexical scope (phạm vi từ vựng)** là cách compiler xác định một tên được khai báo ở đâu dựa trên cấu trúc mã nguồn đang bao quanh nơi tên đó xuất hiện. Nó không phụ thuộc vào object nào gọi lambda về sau.

Xem một lambda được khai báo trong instance method:

- Lambda có **tham số riêng**, có thể có block body và biến local riêng khai báo trong block đó.
- Lambda được phép truy cập các tên có thể nhìn thấy trong phạm vi bao quanh: tham số method, local variable đã khai báo và được gán chắc chắn, field và method có thể truy cập.
- Với từ khóa **`this` và `super`**, thân lambda dùng cùng ý nghĩa như ở vị trí khai báo lambda bên ngoài; lambda **không tạo một `this` mới**.
- Lambda có thể được truyền đi và chạy sau khi method tạo nó đã kết thúc; các biến local đủ điều kiện được capture, còn các field thuộc về object và có thể thay đổi.

Cần phân biệt hai thời điểm: **tạo lambda** trả về một giá trị có kiểu functional interface; **gọi abstract method của functional interface** mới thực thi thân lambda. Do đó tên `this` bên trong không chuyển sang object đang gọi functional interface.

Đừng hiểu "lexically scoped" là lambda không có scope: parameter và local khai báo *trong block lambda* vẫn có phạm vi riêng. Điểm khác biệt cốt lõi so với anonymous class là cách diễn giải `this`, `super` và các tên bên ngoài.

## 3. Quy tắc của `this` trong lambda

`this` trong lambda được hiểu là **instance của class bao quanh gần nhất phù hợp về mặt từ vựng** tại vị trí lambda được khai báo. Trong một instance method của `OrderService`, biểu thức `() -> this.orderId` truy cập `orderId` của chính `OrderService` đó.

Điều này có các hệ quả:

- `this.field` truy cập field của object bao quanh; `this.method()` gọi method của object đó.
- Lambda **không có `this` riêng** trỏ đến object triển khai functional interface. Không dùng `this` để đoán danh tính hay class runtime của lambda.
- Khi lambda được khai báo trong **static context**, `this` của instance không hợp lệ; dùng dữ liệu đã truyền vào hoặc tạo instance rõ ràng.
- Khi ở trong một inner class, `this` có thể là inner-class instance. Nếu cần outer instance, dùng biểu thức được phép như `Outer.this`.
- Lambda có thể giữ tham chiếu đến enclosing instance lâu hơn mong đợi. Với callback/listener sống lâu, cân nhắc vòng đời và trách nhiệm tháo đăng ký để tránh giữ object không cần thiết.

### So sánh với anonymous inner class

Đối với:

```java
Supplier<String> a = () -> this.toString();
Supplier<String> b = new Supplier<String>() {
    @Override public String get() {
        return this.toString();
    }
};
```

Đây là **đoạn minh họa phải đặt trong instance context** và cần `import java.util.function.Supplier;`.

Ở `a`, `this` là enclosing instance. Ở `b`, `this` là instance của anonymous class vừa tạo. Nếu code bên trong anonymous class muốn truy cập enclosing instance, trong ngữ cảnh hợp lệ nó có thể dùng `Outer.this`. Hai biểu thức `this.toString()` vì vậy không đồng nghĩa.

Bảng đối chiếu:

| Vấn đề | Lambda | Anonymous class |
| --- | --- | --- |
| Có instance `this` riêng? | Không; dùng `this` của lexical context. | Có; `this` là object anonymous class. |
| `super` tham chiếu theo class nào? | Superclass của enclosing class tại vị trí khai báo hợp lệ. | Superclass của chính anonymous class. |
| Tên field bên ngoài | Phân giải theo ngữ cảnh từ vựng. | Anonymous class có thể khai báo field trùng tên và che field bên ngoài. |
| Local biến bên ngoài | Phải final/effectively final. | Cũng phải final/effectively final. |
| Đích dùng phổ biến | Một hành vi cho functional interface. | Cần định nghĩa class body, field/method riêng hoặc anonymous subtype. |
| Identity của object được tạo | Không có lời hứa một object mới cho mỗi lần đánh giá; tránh dựa vào identity. | `new` tạo một instance anonymous class. |

**Lưu ý:** nếu lambda được viết **bên trong method của anonymous class**, enclosing class gần nhất tại vị trí khai báo lại chính là anonymous class đó. Lexical scoping luôn xét cấu trúc mã nguồn thực tế, không tự động tìm "outer class cao nhất".

## 4. Quy tắc của `super` trong lambda

Trong instance context của subclass, `super.method()` dùng implementation có thể truy cập từ superclass theo luật Java. Đặt lời gọi đó vào lambda **không thay đổi superclass được tham chiếu**:

```java
class Parent {
    String title() { return "Parent"; }
}
class Child extends Parent {
    String title() { return "Child"; }

    java.util.function.Supplier<String> fromParent() {
        return () -> super.title(); // "Parent"
    }
}
```

Đây là ví dụ minh họa với các class; muốn chạy riêng cần có class chứa `main` hoặc gọi `new Child().fromParent().get()`. `super.title()` dùng member superclass của **Child**, vì lambda được khai báo trong instance method của Child.

Trong anonymous class, `super` lại được giải theo superclass của **anonymous class đó**, không mặc nhiên là superclass của outer Child. Vì vậy thay anonymous class bằng lambda mà không xem lại `this`/`super` có thể làm đổi hành vi.

Các giới hạn cần nhớ:

- `super` chỉ hợp lệ khi Java cho phép dùng nó tại lexical context tương ứng; không dùng `super` như instance expression bên trong static method.
- Java có cú pháp qualified `TypeName.super.member` ở những ngữ cảnh được quy định, và `InterfaceName.super.defaultMethod()` với luật riêng của default method; không được suy diễn rằng có thể gọi mọi member của mọi lớp/interface như vậy.
- Đừng nhầm `super` với dynamic dispatch thông thường qua `this`: `super.method()` yêu cầu cơ chế chọn implementation của superclass; trong khi `this.method()` vẫn có thể gọi overriding method qua dispatch của object.

## 5. Ví dụ hoàn chỉnh: cùng object bao quanh, hai cách biểu diễn hành vi

Ví dụ được thiết kế để thấy đồng thời `this`, `super`, local capture, field mutable và khác biệt của anonymous class. Tạo tệp **`LambdaScopeDemo.java`**:

```java
import java.util.function.Supplier;

public class LambdaScopeDemo {
    static class Parent {
        String name() { return "Parent"; }
    }

    static class Child extends Parent {
        String name = "Child";
        int calls = 0;

        Supplier<String> lambda(String action) {
            String prefix = "lambda";
            return () -> {
                calls++;
                return prefix + " | action=" + action
                        + " | this.name=" + this.name
                        + " | super.name()=" + super.name()
                        + " | calls=" + calls;
            };
        }

        Supplier<String> anonymous() {
            return new Supplier<String>() {
                String name = "Anonymous";

                @Override
                public String get() {
                    return "anonymous | this.name=" + this.name
                            + " | Child.this.name=" + Child.this.name;
                }
            };
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Supplier<String> f = child.lambda("read");

        System.out.println(f.get());
        System.out.println(f.get());
        System.out.println(child.anonymous().get());
    }
}
```

Chạy với JDK 17+ (toàn bộ cú pháp trên đã dùng được từ Java 8):

```bash
javac LambdaScopeDemo.java
java LambdaScopeDemo
```

Kết quả chuẩn:

```text
lambda | action=read | this.name=Child | super.name()=Parent | calls=1
lambda | action=read | this.name=Child | super.name()=Parent | calls=2
anonymous | this.name=Anonymous | Child.this.name=Child
```

**Giải thích từng điểm:**

1. `child.lambda("read")` trả về một `Supplier<String>`. Thân lambda chưa chạy tại thời điểm tạo `f`; nó được thực thi khi gọi `f.get()`.
2. `this.name` trong lambda là `Child.name`, nên in `Child`. Lambda không có instance `this` riêng.
3. `super.name()` trong lambda gọi `Parent.name()`, nên in `Parent`, không gọi phần ghi đè hay field của `Child`.
4. `prefix` và `action` là local/parameter được capture; chúng không bị gán lại sau khi khởi tạo nên **effectively final**.
5. `calls` là **field của Child**, có thể tăng khi lambda thực thi. Cùng một `child` được sử dụng ở cả hai lần `get()`, nên in 1 rồi 2. Đây là ví dụ tuần tự; không thể từ đó suy ra tăng field là an toàn khi nhiều thread cùng gọi.
6. Trong anonymous class, `this.name` là field `Anonymous`; `Child.this.name` chỉ rõ enclosing Child, nên cho hai kết quả khác nhau.

Bài học quan trọng: lambda được tạo tại một lexical context và giữ liên hệ với context đó, chứ không mang theo một scope `this` độc lập kiểu anonymous class.

## 6. Capture biến local: `final` và `effectively final`

Một local variable hoặc method parameter được lambda dùng từ phạm vi ngoài phải **final** hoặc **effectively final**. "Effectively final" nghĩa là dù không viết từ khóa `final`, biến không bị gán lại sau lần gán hợp lệ theo quy tắc của Java và được definite assignment trước khi sử dụng.

Ví dụ hợp lệ (đặt trong method hoặc class phù hợp):

```java
String prefix = "Hello";
java.util.function.Function<String, String> greet =
        name -> prefix + ", " + name;
// prefix không bị gán lại: effectively final.
```

Ví dụ **cố ý không biên dịch**:

```java
int next = 1;
java.util.function.Supplier<Integer> supplier = () -> next;
next++; // Lỗi: next không còn effectively final.
```

Không chỉ `next++` bên ngoài mà cố gắng `next++` **trong** lambda cũng vi phạm luật capture local. Quy tắc này liên quan đến **biến local**, không áp dụng y hệt cho field.

**Điều hay bị nhầm:** biến tham chiếu có thể effectively final nhưng **object nó trỏ đến vẫn mutable**:

```java
java.util.List<String> items = new java.util.ArrayList<>();
Runnable addItem = () -> items.add("x");  // Hợp lệ.
addItem.run();                             // items chứa "x".
// items = new java.util.ArrayList<>();   // Nếu gán lại sẽ không hợp lệ.
```

Đây là code minh họa trong cùng một block method. Java hạn chế việc gán lại *biến tham chiếu* `items`, không biến toàn bộ `ArrayList` thành immutable. Thay đổi nội dung object qua tham chiếu có thể phát sinh side effect; khi chia sẻ giữa thread cần bảo đảm đồng bộ hoặc thiết kế immutable phù hợp.

Cùng ý tưởng đó, `this.calls++` trong ví dụ chính hợp lệ vì `calls` là field. Khi callback chạy đồng thời, thao tác tăng không atomic và có thể race; cân nhắc loại bỏ shared mutable state, dùng `AtomicInteger` hay cơ chế đồng bộ khi mô hình thật đòi hỏi.

### Capture và vòng lặp

Biến đếm của vòng `for` thông thường thường bị cập nhật, nên không thể capture trực tiếp nếu nó không effectively final:

```java
java.util.List<java.util.function.Supplier<Integer>> tasks =
        new java.util.ArrayList<>();
for (int i = 0; i < 3; i++) {
    int index = i;                // Biến mới cho mỗi lượt lặp.
    tasks.add(() -> index);      // Hợp lệ: index effectively final.
}
// Khi gọi từng Supplier: lần lượt trả 0, 1, 2.
```

Dòng `tasks.add(() -> i)` trong vòng `for` trên sẽ không biên dịch vì `i` được tăng sau mỗi lượt. Đối với enhanced `for` (for-each), biến phần tử là biến riêng cho mỗi iteration và có thể capture nếu không bị gán lại.

## 7. Shadowing: trùng tên biến và field

Lambda được ràng buộc theo lexical scope, nên không được tùy ý khai báo lại tên của một local/parameter đang còn hiệu lực trong phạm vi bao quanh.

Ví dụ **cố ý không biên dịch**:

```java
String label = "outer";
java.util.function.Supplier<String> invalid = () -> {
    String label = "inner"; // Lỗi: trùng local name của scope ngoài.
    return label;
};
```

Đối với lambda parameter cũng có vấn đề tương tự: một `Function<String, String>` khai báo parameter cùng tên với local variable đang trong scope sẽ gây lỗi biên dịch.

Ngược lại, field của class có thể bị **che (shadow)** bởi local/parameter. Dùng `this.field` để ghi rõ muốn field nào:

```java
class NamePrinter {
    String label = "field";

    java.util.function.Function<String, String> format() {
        return label -> this.label + ":" + label;
        // this.label là field; label là lambda parameter.
    }
}
```

Đoạn code này là class hợp lệ nhưng không có `main`; nếu dùng `new NamePrinter().format().apply("input")`, kết quả là `field:input`.

Hãy ưu tiên tên biến dễ hiểu, và khi có field bị shadow nên viết `this.field` rõ ràng. Đừng đổi anonymous class thành lambda chỉ để ngắn hơn nếu thay đổi đó kéo theo ý nghĩa khác của các tên chưa qualifier.

## 8. Static context và scope lồng nhau

Ở static method không có enclosing instance của class:

```java
class StaticExample {
    String title = "instance";

    static java.util.function.Supplier<String> legal() {
        String value = "local";
        return () -> value; // Hợp lệ: capture local effectively final.
    }

    // static java.util.function.Supplier<String> invalid() {
    //     return () -> this.title; // Lỗi: this không có trong static context.
    // }
}
```

Trong instance context, lambda lồng trong lambda vẫn dùng `this` của class bao quanh, trừ khi lexical context nằm bên trong một class khác (chẳng hạn anonymous/local/inner class). Khi class lồng nhau hợp lệ, `Outer.this` cho phép yêu cầu rõ instance outer.

`super` cũng phụ thuộc lexical context: lambda trong một instance method của subclass có thể dùng `super.method()`; đưa đoạn đó vào static method không khiến `super` tự xuất hiện.

## 9. Lambda, method reference và thiết kế callback

Trong instance context, khi mục đích là chuyển lời gọi một instance method thành callback, bạn có thể dùng:

```java
Runnable a = () -> this.refresh();
Runnable b = this::refresh;
```

Đây là **minh họa** bên trong một class có instance method `void refresh()`. Hai cách biểu đạt cùng việc gọi `refresh` trên enclosing instance cho tình huống này. Method reference thường gọn khi chỉ muốn ủy quyền một method có sẵn; lambda hữu ích khi cần nhiều câu lệnh hoặc logic trung gian.

Khi thiết kế callback:

- Đừng dựa vào `lambda.getClass().getName()` để nhận diện nghiệp vụ; lớp/identity runtime của lambda không phải hợp đồng đáng phụ thuộc.
- Đừng dùng reference equality hay khóa đồng bộ trên object lambda để biểu diễn danh tính công việc, vì runtime có thể tái sử dụng instance.
- Nếu callback giữ `this`, hãy nghĩ tới vòng đời: callback đăng ký vào đối tượng sống lâu có thể khiến enclosing object khó được GC cho tới khi callback được gỡ.
- Nếu callback sửa field/object được capture, cần xem có gọi đồng thời hay không. **Effectively final không có nghĩa là thread-safe**.
- Với code dễ đọc, ưu tiên giữ explicit `this` khi có nguy cơ trùng tên; không ép mọi anonymous class thành lambda nếu class body riêng là chủ ý.

## 10. Những lỗi hiểu nhầm phổ biến

| Khẳng định sai | Cách hiểu đúng |
| --- | --- |
| "Mỗi lambda tạo ra một object mới nên `this` là object đó." | `this` trong thân lambda là lexical enclosing instance; không được dựa vào identity của object functional-interface lúc chạy. |
| "Lambda là anonymous class viết tắt, nên mọi `this`/`super` giống nhau." | Ngữ nghĩa `this`/`super` khác, cần kiểm tra khi refactor. |
| "Effectively final nghĩa là object immutable." | Chỉ hạn chế gán lại biến local/parameter được capture; state của object có thể thay đổi. |
| "Có thể capture `i` trong `for (int i=...; i++)` trực tiếp." | Biến `i` bị tăng, không effectively final; tạo biến riêng mỗi lượt. |
| "Lambda được gọi ở đâu thì `this` là object gọi nó." | `this` cố định theo lexical context lúc khai báo, không theo caller lúc thực thi. |
| "Có thể dùng `this` và `super` trong lambda ở static method." | Static context không có enclosing instance để dùng các biểu thức instance đó. |
| "Field tăng được trong lambda tức là an toàn đa luồng." | Mutable field vẫn có thể có race condition. |

## 11. Tình huống áp dụng và tự kiểm tra

**Tình huống 1:** Trong `UserService`, bạn dùng `users.forEach(user -> this.audit(user))`. `this` là instance `UserService` chứa lambda, không phải `user`. Nếu bạn muốn hành vi trên từng `user`, phải gọi qua chính đối tượng `user` hoặc method phù hợp.

**Tình huống 2:** Bạn thay một anonymous `Runnable` đang dùng `this.toString()` bằng `() -> this.toString()`. Trước đây `this` là anonymous `Runnable`; sau đó là instance của enclosing class. Cần rà soát tác dụng quan sát được trước khi đổi.

**Tình huống 3:** Trong `Child extends Parent`, lambda gọi `super.validate()`. Đây là lời gọi theo ngữ cảnh của Child tới superclass thích hợp, không phải một superclass của functional interface.

**Tình huống 4:** Một method trả callback capture local `message`; method kết thúc rồi callback mới chạy. Việc này hợp lệ nếu `message` definite assigned và effectively final. Callback có thể tiếp tục dùng giá trị capture; không tự động làm biến local trở thành biến có thể gán lại.

**Tình huống 5:** Đối tượng `this` bị giữ bởi một listener đã đăng ký vào dịch vụ sống lâu. Hãy xác định ai sở hữu listener, khi nào đăng ký/hủy đăng ký, và liệu có thể dùng callback chỉ giữ dữ liệu cần thiết thay vì toàn bộ object.

## 12. Kết luận và tài liệu tham khảo

Trong lambda Java 8, **`this` và `super` mang ý nghĩa của lexical context bao quanh**, còn các local được capture phải là `final` hoặc `effectively final`. Đây là nền tảng vẫn áp dụng với Java hiện đại khi dùng Stream, event handler, async callback, dependency injection hoặc functional interface.

Nhớ ba câu hỏi trước khi refactor: **(1)** `this`/`super` thực sự trỏ tới class/instance nào? **(2)** biến được capture có hợp lệ và có state thay đổi không? **(3)** callback được gọi ở đâu, khi nào và có chia sẻ state giữa các thread không?

Nguồn đặc tả: [Java Language Specification, §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27), đặc biệt §15.27.2 về lexical context và capture; [JLS §4.12.4: final variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.4). Các quy tắc được trình bày là ngữ nghĩa ổn định của Java, không sử dụng API đã bị loại bỏ.
