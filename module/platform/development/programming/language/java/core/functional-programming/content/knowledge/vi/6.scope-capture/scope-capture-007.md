# So sánh phạm vi và `this` giữa lambda với lớp vô danh trong Java

## 1. Bối cảnh: cùng là hành vi, nhưng phạm vi không giống nhau

Một biểu thức **lambda** và một **lớp vô danh (anonymous class)** đều có thể cung cấp phần triển khai cho một functional interface, chẳng hạn `Runnable` hoặc `Comparator<T>`. Tuy nhiên, chúng có cách xác định **phạm vi tên (scope)** và ý nghĩa của `this`, `super` rất khác nhau.

- **Lambda** không tạo ra phạm vi `this` và `super` riêng. `this` trong lambda mang cùng ý nghĩa như `this` tại nơi lambda xuất hiện: thường là đối tượng bao ngoài đang thực thi phương thức.
- **Anonymous class** khai báo và tạo một đối tượng thuộc một lớp mới không có tên. Bên trong phương thức của lớp vô danh, `this` là đối tượng lớp vô danh ấy, còn `super` hướng tới lớp cha của lớp vô danh.
- **Lambda** không cho khai báo lại tên tham số hoặc biến cục bộ đang ở trong phạm vi bao ngoài theo cách tạo một lớp riêng. **Anonymous class** có phạm vi thành viên riêng (các field, method) và có thể che khuất (shadow) tên ở phạm vi ngoài.
- Cả hai đều có thể đọc các biến cục bộ được **capture** từ vùng bao ngoài nếu biến là `final` hoặc *effectively final*. Cả hai đều có thể truy cập và thay đổi field của đối tượng nếu quyền truy cập cho phép.

Những khác biệt này có ý nghĩa khi viết callback, listener, xử lý stream, mã bất đồng bộ và khi chuyển mã từ anonymous class sang lambda.

> **Nguyên tắc nhận diện:** đừng chỉ nhìn thấy `() -> ...` và `new Runnable() { ... }` rồi cho rằng đây là hai cú pháp hoán đổi tự do. Hãy kiểm tra xem thân hàm có dùng `this`, `super`, field trùng tên, `return` hoặc thông tin về lớp thực thi hay không.

## 2. Cùng một hợp đồng `Runnable`, hai cách triển khai

`Runnable` là functional interface trong `java.lang`, có một phương thức trừu tượng `void run()`. Hai cách dưới đây đều tạo giá trị truyền được vào nơi yêu cầu `Runnable`:

```java
Runnable lambda = () -> System.out.println("Run");

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Run");
    }
};

lambda.run();    // Run
anonymous.run(); // Run
```

Đây là đoạn mã **minh họa trong một phương thức**, không phải chương trình độc lập. Với ví dụ chỉ in chuỗi, kết quả giống nhau. Khác biệt xuất hiện khi thân phương thức cần tham chiếu tới đối tượng hoặc tên của phạm vi bao quanh.

Một lambda thường ngắn gọn hơn khi chỉ thực hiện một hành vi nhỏ. Một anonymous class có thể khai báo thêm field, method và khối khởi tạo riêng, hoặc mở rộng một lớp có thể kế thừa (không nhất thiết là functional interface). Lambda chỉ dùng trong ngữ cảnh **functional interface**; không phải cú pháp thay thế chung cho bất kỳ lớp vô danh nào.

## 3. Quy tắc `this`: câu hỏi “đang nói tới đối tượng nào?”

Xét đoạn code nằm bên trong một phương thức instance của `Outer`:

```java
class Outer {
    String label = "OUTER";

    void demonstrate() {
        Runnable lambda = () ->
                System.out.println(this.label);

        Runnable anonymous = new Runnable() {
            String label = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Outer.this.label);
            }
        };

        lambda.run();    // OUTER
        anonymous.run(); // ANONYMOUS, sau đó OUTER
    }
}
```

- Trong lambda, `this.label` là `Outer.this.label` vì lambda có **lexical scoping** đối với `this`; nó không có “lambda this” riêng.
- Trong anonymous class, `this.label` là field của đối tượng anonymous class, nên kết quả là `ANONYMOUS`.
- `Outer.this` là **qualified this**, chỉ rõ đối tượng `Outer` đang bao quanh. Cú pháp này rất hữu ích khi một lớp bên trong che khuất field của lớp bên ngoài.

Nếu bỏ field `label` của anonymous class, cách phân giải `this.label` sẽ khác: đối tượng anonymous class không có field ấy và không tự động có quyền dùng `this` để gọi field của `Outer`. Từ trong anonymous class, hãy viết `Outer.this.label` để tham chiếu tường minh tới field bao ngoài.

### Khi nào `this` trong lambda không dùng được?

`this` chỉ hợp lệ trong ngữ cảnh có một đối tượng hiện hành phù hợp. Nếu lambda được khai báo trực tiếp trong một **phương thức static**, không có instance `this` của lớp bao ngoài:

```java
class Example {
    static Runnable task() {
        // SAI: trong static context không có "this" của Example.
        // return () -> System.out.println(this);
        return () -> System.out.println("static context");
    }
}
```

Một anonymous class được tạo trong static method vẫn là một đối tượng: bên trong `run()` của nó, `this` vẫn trỏ tới **đối tượng lớp vô danh**, không trỏ tới instance của lớp đang chứa static method. Ngữ cảnh static và instance vì thế cần được phân biệt rõ.

## 4. Chương trình Java 17 hoàn chỉnh để kiểm chứng

Chương trình bên dưới chạy toàn bộ bằng Java 17+, dùng `Runnable`, `Consumer<String>`, lambda và anonymous class, đồng thời chủ động in kết quả có thứ tự xác định.

Tạo tệp **`LambdaScopeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class LambdaScopeDemo {
    private final String label = "OUTER";
    private int counter = 0;

    private void demonstrate() {
        String prefix = "captured";

        Runnable lambda = () -> {
            System.out.println("Lambda this.label: " + this.label);
            System.out.println("Lambda this is outer: "
                    + (this == LambdaScopeDemo.this));
            System.out.println("Lambda local: " + prefix);
            counter++;
        };

        Runnable anonymous = new Runnable() {
            private final String label = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println("Anonymous this.label: " + this.label);
                System.out.println("Anonymous outer.label: "
                        + LambdaScopeDemo.this.label);
                System.out.println("Anonymous this is outer: "
                        + ((Object) this == LambdaScopeDemo.this));
                System.out.println("Anonymous local: " + prefix);
                LambdaScopeDemo.this.counter++;
            }
        };

        lambda.run();
        anonymous.run();
        System.out.println("Counter: " + counter);

        List<String> events = new ArrayList<>();
        Consumer<String> lambdaConsumer = text -> {
            events.add("lambda:" + text);
        };

        Consumer<String> anonymousConsumer = new Consumer<>() {
            private final String prefix = "inner";

            @Override
            public void accept(String text) {
                events.add(prefix + ":" + text);
            }
        };

        lambdaConsumer.accept("A");
        anonymousConsumer.accept("B");
        System.out.println("Events: " + events);

        // Cùng capture một biến local: không có phép gán lại prefix.
        Runnable again = () ->
                System.out.println("Again local: " + prefix);
        again.run();
    }

    public static void main(String[] args) {
        new LambdaScopeDemo().demonstrate();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 LambdaScopeDemo.java
java LambdaScopeDemo
```

**Stdout kỳ vọng chính xác**:

```text
Lambda this.label: OUTER
Lambda this is outer: true
Lambda local: captured
Anonymous this.label: ANONYMOUS
Anonymous outer.label: OUTER
Anonymous this is outer: false
Anonymous local: captured
Counter: 2
Events: [lambda:A, inner:B]
Again local: captured
```

Đối chiếu từng phần:

1. `lambda` chạy trong phương thức `demonstrate` của đối tượng `LambdaScopeDemo`. `this.label` trỏ tới field `label` của chính đối tượng bao ngoài, bằng `"OUTER"`.
2. `this == LambdaScopeDemo.this` trong lambda là `true` vì hai cách viết chỉ cùng một instance.
3. Anonymous class có field riêng tên `label` nên `this.label` thành `"ANONYMOUS"`. Viết `LambdaScopeDemo.this.label` mới lấy field bên ngoài.
4. Trong anonymous class, `(Object) this == LambdaScopeDemo.this` cho `false`: hai đối tượng khác nhau. Ép kiểu `(Object)` ở đây làm phép so sánh tham chiếu giữa hai loại object khác nhau trở nên hợp lệ về kiểu.
5. Cả hai đều đọc được `prefix` từ phương thức chứa chúng vì `prefix` không bị gán lại.
6. Hai lần tăng `counter` tác động lên **cùng field của đối tượng bao ngoài**: lambda dùng `counter++`, anonymous class ghi tường minh `LambdaScopeDemo.this.counter++`. Kết quả là 2.
7. Với `Consumer` của lambda, `events.add(...)` thêm chuỗi `"lambda:A"`. Trong anonymous class, field `prefix` riêng có giá trị `"inner"`, nên thêm `"inner:B"`. Các hành động được gọi tuần tự nên thứ tự danh sách được xác định.

> Ví dụ cố ý sử dụng `counter++` và `events.add` để cho thấy **phạm vi và đối tượng sở hữu trạng thái**, không phải khuyến nghị cập nhật trạng thái dùng chung từ nhiều thread. Khi gọi callback đồng thời, cần cơ chế phối hợp hoặc thay thiết kế để tránh data race.

## 5. Phạm vi biến cục bộ và quy tắc *effectively final*

Một lambda có thể **đọc** biến cục bộ trong phạm vi chứa nó khi biến đó là `final` hoặc *effectively final*: giá trị biến chỉ được gán trong quá trình khởi tạo (hoặc theo những quy tắc definite assignment hợp lệ) và không được gán lại sau đó.

```java
String category = "BOOK"; // effectively final
Runnable lambda = () -> System.out.println(category);

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(category);
    }
};
```

Cả hai hợp lệ. Nhưng đoạn sau không hợp lệ đối với **cả lambda và anonymous class**:

```java
// SAI: biến local bị gán lại nên không effectively final.
String category = "BOOK";
Runnable lambda = () -> System.out.println(category);
category = "PEN";
```

Compiler sẽ báo lỗi về biến cục bộ được tham chiếu từ lambda phải là final hoặc effectively final. Nếu đổi `lambda` thành anonymous class, giới hạn capture local tương tự.

**Tại sao có quy tắc này?** Biến cục bộ thuộc stack frame của lời gọi phương thức; lambda hoặc đối tượng anonymous class có thể sống lâu hơn thời gian phương thức ấy chạy. Java cho phép capture giá trị của local phù hợp mà không cung cấp một biến local mutable dùng chung để mọi callback sửa tùy ý. Đây cũng là lý do không thể dùng trực tiếp một biến đếm local để cập nhật trong `forEach`:

```java
// SAI: không được sửa biến local được capture.
int count = 0;
// list.forEach(item -> count++);
```

Thay vì “lách” bằng mảng `int[] count = {0}`, hãy dùng `stream().count()` nếu mục đích là đếm phần tử hoặc `reduce`/`sum` để tổng hợp.

### *Effectively final* không có nghĩa object bất biến

```java
List<String> events = new ArrayList<>();
Consumer<String> store = events::add;
store.accept("A");
System.out.println(events); // [A]
```

Biến `events` không được gán sang list khác nên vẫn effectively final, dù **nội dung** list thay đổi. Lambda và anonymous class đều có thể mutate object được tham chiếu qua local captured; chính vì vậy phải xem xét side effect, quyền sở hữu trạng thái và thread safety riêng.

## 6. Shadowing: lambda không mở một lớp với field riêng

**Shadowing** xảy ra khi khai báo trong phạm vi gần hơn dùng cùng tên với một khai báo ở phạm vi xa hơn và làm tên xa bị che khuất. Quy tắc này khiến lambda khác anonymous class.

Trong phương thức có `String name = "outer";`, lambda **không thể** khai báo tham số hoặc biến cục bộ khác cùng tên trong thân nó:

```java
void example() {
    String name = "outer";

    // SAI: tên tham số lambda trùng biến local đang ở phạm vi bao ngoài.
    // Consumer<String> badParam = name -> System.out.println(name);

    // SAI: biến local khai báo trong block lambda trùng tên đã có.
    // Runnable badLocal = () -> {
    //     String name = "inner";
    //     System.out.println(name);
    // };
}
```

Đây là mã **minh họa lỗi**, các dòng sai đã comment để không ảnh hưởng chương trình.

Ngược lại, anonymous class tạo **phạm vi thành viên** riêng, vì thế có thể khai báo field trùng tên local ở phương thức bao ngoài:

```java
void example() {
    String name = "outer";

    Runnable anonymous = new Runnable() {
        private final String name = "inner";

        @Override
        public void run() {
            System.out.println(this.name); // inner
            System.out.println(name);      // inner: field được ưu tiên
        }
    };

    anonymous.run();
    System.out.println(name); // outer
}
```

Đoạn này cũng là ví dụ phương thức, không phải class độc lập. Field `name` thuộc đối tượng anonymous class; `name` local ở phương thức chứa vẫn tồn tại và không bị đổi giá trị. Điều đó không có nghĩa anonymous class có quyền gán lại biến local captured: nó chỉ khai báo **một field khác** cùng tên.

### Tham số lambda cũng thuộc phạm vi tên của enclosing context

```java
String item = "BOOK";

// Hợp lệ: tên tham số khác tên biến local bao ngoài.
Consumer<String> display = value ->
        System.out.println(item + " -> " + value);
```

Lambda có thể dùng tên tham số khác (`value`) và đọc `item` captured. Khi thiết kế callback, đặt tên tham số rõ ràng sẽ tránh nhầm lẫn giữa tên ở hai phạm vi và giảm nguy cơ lỗi “variable is already defined”.

## 7. `this`, `super` và tham chiếu đến thành viên kế thừa

Sự khác biệt `this` kéo theo khác biệt với `super`:

| Ngữ cảnh | `this` trỏ tới | `super` hướng tới |
| --- | --- | --- |
| Lambda trong instance method của `Child extends Base` | Instance `Child` bao ngoài | `Base`, như `super` tại vị trí lambda được viết |
| Method `run()` của `new Runnable() { ... }` | Instance anonymous class | Lớp cha trực tiếp của anonymous class (trong ví dụ là `Object`) |
| Anonymous class bên trong `Child`, dùng `Child.this` | Instance `Child` bao ngoài | Cần cú pháp qualified `Child.super` để nhắm tới superclass của `Child` |
| Lambda trong static method | Không có outer instance `this` | Không thể dùng `super` của một outer instance |

Ví dụ về `super` với mã riêng:

```java
class Base {
    String source() {
        return "base";
    }
}

class Child extends Base {
    @Override
    String source() {
        return "child";
    }

    void compare() {
        Runnable lambda =
                () -> System.out.println(super.source());

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println(Child.super.source());
            }
        };

        lambda.run();    // base
        anonymous.run(); // base
    }
}
```

`super.source()` trong lambda được hiểu như viết tại chính phương thức `Child.compare()`, tức gọi phương thức `source()` của `Base`. Trong anonymous class, viết `super.source()` **không** thể gọi `Base.source()`, vì superclass của anonymous class triển khai `Runnable` là `Object`; `Object` không định nghĩa phương thức `source()`. Viết `Child.super.source()` nêu rõ superclass của đối tượng bao ngoài.

**Hạn chế:** cú pháp `QualifiedType.this` và `QualifiedType.super` chỉ dùng trong các ngữ cảnh có enclosing instance/class hợp lệ theo quy tắc ngôn ngữ; không thể tùy ý tham chiếu một đối tượng ở ngoài không nằm trong chuỗi bao chứa về mặt từ vựng.

## 8. Anonymous class có đối tượng riêng; lambda không đồng nghĩa “new class mỗi lần”

Anonymous class là một class declaration không tên, được dùng trong một class instance creation expression như `new Runnable() { ... }`. Nó tạo instance riêng, có thể có field và method hỗ trợ. Bên trong anonymous class, `getClass()` và `this.getClass()` nói về lớp anonymous, không phải lớp bao ngoài.

Lambda có biểu diễn runtime do JVM quyết định. Không nên dựa vào `lambda.getClass().getName()`, tên class tổng hợp, số lần phân bổ object, hoặc danh tính tham chiếu `==` để suy luận nghiệp vụ. Với lambda không capture biến, JVM có thể tái sử dụng instance; với lambda capture state, hành vi tạo/tái sử dụng instance không phải hợp đồng để thiết kế logic ứng dụng.

```java
Runnable lambda = () -> {};
Runnable anonymous = new Runnable() {
    @Override public void run() {}
};

System.out.println(lambda instanceof Runnable);    // true
System.out.println(anonymous instanceof Runnable); // true
```

Hai giá trị đều là `Runnable`. Chúng không bắt buộc có cùng class ở runtime và không nên đem so sánh class name hoặc object identity để kiểm tra tính tương đương về hành vi.

## 9. Từ anonymous class sang lambda: kiểm tra những gì?

Một refactor phổ biến:

```java
Runnable oldTask = new Runnable() {
    @Override
    public void run() {
        System.out.println("Ready");
    }
};

Runnable newTask = () -> System.out.println("Ready");
```

Hai phiên bản cùng in `Ready` khi chạy. Nhưng chuyển đổi **cần xem xét lại** nếu anonymous class trước đó tham chiếu đến:

1. **`this`** hoặc `getClass()`: trước đây tham chiếu đối tượng anonymous class, sau chuyển sang lambda có thể tham chiếu outer instance.
2. **`super`**: trước đây superclass của anonymous class; trong lambda là superclass của outer context.
3. **Field/phương thức riêng của anonymous class**: lambda không định nghĩa được field mới như một class; phải chuyển trạng thái vào đối tượng có owner rõ ràng hoặc cấu trúc khác.
4. **Tên biến/field trùng nhau**: lambda không tạo vùng shadowing mới tương đương.
5. **Các hành vi phụ thuộc thời điểm tạo instance hoặc identity**: không bảo đảm giữ nguyên nếu thay mô hình object.
6. **Functional interface**: lambda chỉ áp dụng cho interface có một abstract method, không thay được anonymous subclass của một lớp tùy ý.

Ví dụ thay đổi ý nghĩa:

```java
class Example {
    private String name = "Outer";

    void run() {
        Runnable anonymous = new Runnable() {
            private String name = "Inner";

            @Override public void run() {
                System.out.println(this.name); // Inner
            }
        };

        Runnable lambda = () ->
                System.out.println(this.name); // Outer

        anonymous.run();
        lambda.run();
    }
}
```

Không thể chỉ xóa cú pháp `new Runnable() { ... }` rồi thay bằng `() -> ...` mà kỳ vọng `this.name` giữ nguyên ý nghĩa. Khi làm refactor, phải viết rõ nguồn dữ liệu cần đọc và kiểm tra bằng test cho cùng kịch bản.

## 10. Phân biệt outer object, state và thread safety

Lambda có thể dùng field của outer object trực tiếp:

```java
class Counter {
    private int value;

    Runnable incrementTask() {
        return () -> value++;
    }

    int value() {
        return value;
    }
}
```

Đây là code hợp lệ về phạm vi, nhưng phép tăng `value++` không nguyên tử. Nếu hai thread gọi cùng `incrementTask` hoặc nhiều task cùng capture một `Counter`, có thể xảy ra **lost update**.

Anonymous class cũng không tự giải quyết vấn đề: `Counter.this.value++` có cùng rủi ro. Sự khác nhau về `this` **không quyết định** mã có thread-safe hay không. Cách giải quyết tùy yêu cầu: tránh trạng thái dùng chung, trả về giá trị mới qua `Function`/`reduce`, hoặc dùng `AtomicInteger`, synchronized/lock hay thiết kế chia sẻ trạng thái phù hợp.

Ví dụ lựa chọn không dùng shared accumulator:

```java
List<Integer> values = List.of(1, 2, 3, 4);

int sum = values.stream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 10
```

`mapToInt` chuyển từng `Integer` thành primitive `int`, `sum` thực hiện phép gộp qua API Stream. Không cần để lambda tăng một biến cục bộ/mảng được chia sẻ.

## 11. Câu hỏi thường gặp và lỗi điển hình

**“Lambda có `this` riêng không?”** Không. Trong instance context, `this` bên trong lambda là `this` tại vị trí lambda được khai báo. Một anonymous class có đối tượng riêng nên `this` của nó mang nghĩa khác.

**“Lambda có capture toàn bộ đối tượng ngoài không?”** Không thể suy ra đơn giản như vậy. Nếu thân lambda dùng field/instance method qua `this`, nó có thể giữ tham chiếu tới enclosing instance; nếu chỉ dùng biến cục bộ effectively final, lambda capture những giá trị cần thiết. Chi tiết biểu diễn và tối ưu do JVM quyết định. Không thiết kế logic phụ thuộc vào cấu trúc object nội bộ của lambda.

**“Một biến captured là `final` thì có bất biến không?”** `final`/effectively final chỉ ngăn **gán lại biến local**, không ngăn sửa object bên trong tham chiếu. `List` hoặc `AtomicInteger` có thể vẫn bị thay đổi.

**“Anonymous class có thể đọc local không effectively final không?”** Không. Cả lambda và anonymous class đều bị ràng buộc bởi quy tắc capture biến local thích hợp.

**“Có thể khai báo field trong lambda không?”** Không như trong class body của anonymous class. Lambda body là expression hoặc block thực thi, không phải phần khai báo field. Có thể khai báo biến cục bộ mới trong block khi không trùng tên ở phạm vi bị cấm.

**“Tại sao `this.toString()` khác nhau?”** Trong lambda, nó gọi `toString()` trên outer object; trong anonymous class, nó gọi trên anonymous object, trừ khi viết qualified outer `this`.

**“Bỏ `this` có luôn lấy outer field không?”** Không. Tên không có qualifier phụ thuộc quy tắc phân giải tên và shadowing. Anonymous class có field cùng tên có thể che khuất outer member; dùng `Outer.this.member` để rõ ràng.

**“Dùng anonymous class thì có gì tốt hơn?”** Nó phù hợp nếu cần mở rộng một lớp, khai báo field/method riêng hoặc tổ chức một object với trạng thái riêng. Với callback đơn giản đúng một hành vi, lambda thường ngắn gọn và dễ đọc hơn.

**“Có thể thay mọi anonymous class bằng lambda không?”** Chỉ với trường hợp functional interface và sau khi xem xét scope, `this`/`super`, các member riêng và ngữ nghĩa callback.

## 12. Bài tập tự kiểm tra

1. Trong `LambdaScopeDemo`, đổi field outer `label` thành `"PARENT"`. Dự đoán chính xác những dòng stdout nào đổi và vì sao dòng `Anonymous this.label` giữ nguyên `"ANONYMOUS"`.
2. Bỏ field `label` của anonymous class trong chương trình và sửa các truy cập cho phù hợp. Dùng `LambdaScopeDemo.this.label` để truy cập outer field.
3. Đặt `String prefix = "captured";` rồi thử `prefix = "changed";` sau khi khai báo lambda. Giải thích vì sao cả lambda và anonymous class capture `prefix` không còn compile.
4. Thử khai báo tham số lambda tên `prefix` trong cùng phạm vi với local `prefix` của phương thức. Ghi lại lỗi compiler và đặt lại tên thành `value` để sửa.
5. Trong anonymous `Consumer`, thay `private final String prefix = "inner";` thành `private final String prefix = "ANON";`. Dự đoán chính xác nội dung danh sách `events`, trong khi lambda `lambdaConsumer` không đổi.
6. Trong ví dụ `Child extends Base`, đổi `Child.source()` trả `"child-v2"`. Giải thích vì sao `super.source()` vẫn trả `"base"`.
7. Viết một anonymous class `Runnable` ghi `System.out.println(this.getClass().getName())`, sau đó viết lambda có cùng thân biểu thức. Xác định `this` đang nói tới object nào và không dựa vào tên class runtime để so sánh chức năng.
8. Tạo `Counter` với `incrementTask()` rồi chạy nhiều task đồng thời. Giải thích vì sao kết quả có thể thiếu phép tăng và trình bày cách thay bằng `AtomicInteger` hoặc thiết kế không chia sẻ state.
9. Lấy một callback anonymous class trong dự án và lập bảng những chỗ dùng `this`, `super`, field trùng tên, biến captured. Chỉ chuyển sang lambda khi ý nghĩa các tham chiếu đã được bảo toàn.

**Điểm cốt lõi cần ghi nhớ:** lambda dùng `this`/`super` theo **phạm vi từ vựng bao ngoài**; anonymous class tạo **đối tượng và phạm vi thành viên riêng**. Cả hai cùng chịu quy tắc capture local `final` hoặc effectively final. Khi hiểu rõ các quy tắc này, việc chọn hoặc refactor callback sẽ ít gây thay đổi hành vi ngoài ý muốn.
