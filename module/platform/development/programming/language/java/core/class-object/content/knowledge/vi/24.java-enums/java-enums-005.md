# Phần thân riêng cho từng hằng và hành vi khác nhau trong Java `enum`

## 1. Mục tiêu và bức tranh tổng thể

Một `enum` trong Java mô hình hóa **tập các hằng có tên được xác định trước**. Khi các hằng không chỉ khác tên hoặc dữ liệu, mà còn **khác hành vi**, Java cho phép viết **phần thân riêng cho từng hằng** (*constant-specific class body*).

Ví dụ căn bản:

```java
enum Operation {
    PLUS {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MINUS {
        @Override
        int apply(int a, int b) {
            return a - b;
        }
    };

    abstract int apply(int a, int b);
}
```

Trong ví dụ:

- `PLUS` và `MINUS` vẫn là **hai hằng của cùng kiểu enum `Operation`**.
- Khối `{ ... }` sau mỗi tên hằng là **phần thân riêng**, nơi override cách hoạt động của method `apply`.
- Method `apply` được khai báo `abstract` trong enum, buộc các hằng cung cấp implementation phù hợp.
- Caller chỉ giữ biến kiểu `Operation` rồi gọi `operation.apply(a,b)`; JVM chọn implementation theo constant object đang nhận lời gọi.
- Code không cần phân nhánh `if (operation == PLUS) ...` ở mọi nơi thực hiện phép tính.

**Ý chính:** Enum cho ta một **tập các lựa chọn đóng**, còn phần thân riêng giúp mỗi lựa chọn chứa **hành vi phù hợp với chính nó**. Đây là đa hình được áp dụng vào các hằng của enum, không phải khả năng cho plugin bên ngoài tự đăng ký thêm hằng.

### Sau bài học, bạn cần làm được

1. Viết đúng cú pháp constant body kèm hoặc không kèm constructor arguments.
2. Khai báo abstract method chung và override tại từng constant.
3. Có một implementation mặc định trong enum, rồi **chỉ override** ở những constant đặc biệt.
4. Kết hợp metadata bất biến, constructor và phần thân riêng.
5. Phân biệt **enum type**, **constant instance** và **lớp con ngầm được tạo cho phần thân riêng**.
6. So sánh thiết kế đa hình enum với `switch`, `if/else` và strategy classes.
7. Nhận diện lỗi thường gặp về method signatures, visibility, constructor, state mutable, test và bảo trì.

Các ví dụ sau ưu tiên Java 17+, chỉ rõ tên tệp và output. Những đoạn chỉ minh họa cú pháp hoặc lỗi được đánh dấu riêng.

## 2. Ví dụ chạy được: mỗi hằng thực hiện một phép toán

Tạo tệp **`EnumOperationDemo.java`**:

```java
enum Operation {
    ADD {
        @Override
        int apply(int left, int right) {
            return left + right;
        }
    },
    SUBTRACT {
        @Override
        int apply(int left, int right) {
            return left - right;
        }
    },
    MULTIPLY {
        @Override
        int apply(int left, int right) {
            return left * right;
        }
    };

    abstract int apply(int left, int right);
}

public class EnumOperationDemo {
    public static void main(String[] args) {
        for (Operation operation : Operation.values()) {
            System.out.println(operation.name() + "="
                    + operation.apply(8, 3));
        }
    }
}
```

Biên dịch, chạy:

```bash
javac EnumOperationDemo.java
java EnumOperationDemo
```

**Standard output:**

```text
ADD=11
SUBTRACT=5
MULTIPLY=24
```

**Đọc từng phần:**

- `ADD { ... }` không khai báo một biến cục bộ; đó là một enum constant có class body riêng.
- `@Override` yêu cầu method trong phần thân khớp với một method của superclass/interface phù hợp, nên giúp compiler phát hiện sai chính tả hoặc sai chữ ký.
- `abstract int apply(...)` khai báo hành vi chung ở mức enum type.
- `Operation.values()` trả các hằng theo thứ tự khai báo.
- Khi vòng lặp gọi `operation.apply(8,3)`, cơ chế **dynamic dispatch** gọi override thích hợp với hằng thực tế.

Ba constants khác hành vi nhưng tất cả vẫn dùng chung **API `Operation.apply(int,int)`**.

## 3. Cú pháp chuẩn của phần thân riêng

Mẫu khái niệm:

```java
enum Example {
    FIRST {
        @Override
        String describe() {
            return "first";
        }
    },
    SECOND {
        @Override
        String describe() {
            return "second";
        }
    };

    abstract String describe();
}
```

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `enum Example` | Khai báo enum type |
| `FIRST`, `SECOND` | Named enum constants |
| `{ ... }` sau mỗi constant | Constant-specific class body |
| `@Override` | Kiểm tra override tại compile time |
| `abstract String describe()` | Hợp đồng method chung của enum |
| Dấu phẩy giữa constants | Phân tách constant declarations |
| Dấu `;` sau danh sách constants | Ngăn cách constant list với member declarations theo sau |
| Dấu `}` cuối | Đóng enum declaration |

Khi enum **không có fields/methods khai báo phía sau constants**, dấu `;` có thể được bỏ. Khi phía sau danh sách có `abstract method`, constructor hoặc fields, hãy đặt dấu `;` đúng vị trí như ví dụ.

### Phần thân riêng có tên class không?

Không có một **source-level class name** độc lập để client dùng như `new Example.FIRST()` hoặc `extends Example.FIRST`. Java compiler tổ chức constant-specific class body thành một dạng **lớp con ngầm/anonymous subclass** của enum type cho constant tương ứng.

Điểm quan trọng khi thiết kế API: client làm việc bằng kiểu `Example` và hằng `Example.FIRST`, **không cần và không nên phụ thuộc tên lớp phát sinh ở mức bytecode**.

## 4. Phần thân riêng khác các khối lệnh thực thi ra sao?

Ba cách viết này khác nhau:

```java
enum Mode {
    FAST {
        @Override
        int weight() {
            return 2;
        }
    },
    SLOW {
        @Override
        int weight() {
            return 1;
        }
    };

    abstract int weight();
}
```

Khối sau `FAST` và `SLOW` khai báo **members cho constant-specific subclasses**. Nó không phải một block statement chỉ chạy một lần rồi kết thúc.

Trong phần thân, bạn thường viết:

- Method overrides.
- Instance methods hỗ trợ.
- Fields riêng nếu thật sự cần.
- Instance initializer nếu thật sự cần (thận trọng về lifecycle).

Bạn **không** viết những câu lệnh tự do như `System.out.println("x");` trực tiếp ở class body; nếu cần logic chạy khi tạo instance thì phải thuộc initializer/field initializer/constructor theo rules Java.

### Phần thân riêng không tạo thêm enum constant

`FAST { ... }` vẫn là đúng một hằng `Mode.FAST`. Việc có nhiều methods trong body **không** làm `Mode.values()` có thêm phần tử.

## 5. Vì sao `abstract method` là một contract mạnh?

Với enum có nhiều chiến lược riêng, một cách là khai báo abstract method ở enum type:

```java
enum Choice {
    A {
        @Override
        String text() {
            return "a";
        }
    },
    B {
        @Override
        String text() {
            return "b";
        }
    };

    abstract String text();
}
```

Compiler đòi mỗi constant cung cấp implementation concrete cho abstract method, bởi mọi constant phải là đối tượng có thể khởi tạo.

### Khi thêm một hằng mới

Nếu bạn viết:

```java
enum BrokenChoice {
    A {
        @Override
        String text() {
            return "a";
        }
    },
    B;

    abstract String text();
}
```

đây là **đoạn minh họa lỗi biên dịch**, không phải ví dụ chạy. `B` không có implementation cho `text()`, và bản thân enum không cung cấp implementation mặc định. Compiler báo thiếu abstract method implementation cho B.

**Lợi ích:** Khi thêm một phần tử vào tập hằng mà quên định nghĩa hành vi bắt buộc, lỗi được phát hiện **ngay khi biên dịch**, thay vì âm thầm trả null hoặc chạy sai trong một nhánh chưa được kiểm.

### Chọn abstract hay default method?

- Nếu **mọi hằng** phải tự quyết định hành vi, khai báo abstract.
- Nếu nhiều hằng có **cùng hành vi mặc định** và chỉ vài hằng khác, khai báo concrete method ở enum rồi override nơi cần.
- Nếu method chỉ trả metadata không khác logic, một final field và getter thường đơn giản hơn override cho từng hằng.

## 6. Implementation mặc định: không phải hằng nào cũng cần class body

Một enum có thể định nghĩa method concrete để mọi constant kế thừa, rồi chỉ override ở constant ngoại lệ.

Tạo **`EnumDefaultBehaviorDemo.java`**:

```java
enum Delivery {
    STANDARD,
    ECONOMY,
    EXPRESS {
        @Override
        int days() {
            return 1;
        }
    };

    int days() {
        return 5;
    }
}

public class EnumDefaultBehaviorDemo {
    public static void main(String[] args) {
        for (Delivery method : Delivery.values()) {
            System.out.println(method.name() + "="
                    + method.days());
        }
    }
}
```

```bash
javac EnumDefaultBehaviorDemo.java
java EnumDefaultBehaviorDemo
```

```text
STANDARD=5
ECONOMY=5
EXPRESS=1
```

- STANDARD và ECONOMY **không có body riêng**: sử dụng `Delivery.days()` có sẵn.
- EXPRESS **có body** và override days() thành 1.
- Tất cả có static type `Delivery` ở caller, nên chỉ cần gọi `method.days()`.

**Thiết kế đáng cân nhắc:** Giá trị mặc định phải thực sự là quy tắc đúng cho các hằng không override. Nếu 5 ngày không phải mặc định của nghiệp vụ, đưa mặc định vào enum có thể che các case quên triển khai. Khi đó dùng abstract method buộc mọi hằng xác định rõ.

## 7. Gọi `super` để tái sử dụng hành vi chung

Constant-specific subclass có thể override concrete method rồi **gọi implementation của enum type qua `super`** để mở rộng thay vì thay hoàn toàn.

Tạo **`EnumSuperMethodDemo.java`**:

```java
enum OutputMode {
    PLAIN,
    DECORATED {
        @Override
        String render(String text) {
            return "[" + super.render(text) + "]";
        }
    };

    String render(String text) {
        return text.trim();
    }
}

public class EnumSuperMethodDemo {
    public static void main(String[] args) {
        System.out.println(OutputMode.PLAIN.render(" Java "));
        System.out.println(OutputMode.DECORATED.render(" Java "));
    }
}
```

```bash
javac EnumSuperMethodDemo.java
java EnumSuperMethodDemo
```

```text
Java
[Java]
```

`super.render(text)` ở DECORATED gọi implementation `OutputMode.render`; nó **không** có nghĩa gọi hằng PLAIN.

**Nhận diện receiver:**

- `this` trong phần thân riêng chỉ object constant hiện tại.
- `super` dùng superclass implementation tương ứng.
- `OutputMode.PLAIN` là một enum constant **khác object**.
- Không dùng `super` để chọn một constant khác; gọi constant theo tên nếu đó thực sự là nghiệp vụ.

## 8. `this` trong phần thân riêng là chính hằng enum

Enum constants là objects. Trong method của constant-specific body, `this` tham chiếu constant đó.

Tạo **`EnumThisDemo.java`**:

```java
enum Action {
    START {
        @Override
        String describe() {
            return "start:" + this.name();
        }
    },
    STOP {
        @Override
        String describe() {
            return "stop:" + this.name();
        }
    };

    abstract String describe();
}

public class EnumThisDemo {
    public static void main(String[] args) {
        System.out.println(Action.START.describe());
        System.out.println(Action.STOP.describe());
        System.out.println(Action.START == Action.valueOf("START"));
    }
}
```

```bash
javac EnumThisDemo.java
java EnumThisDemo
```

```text
start:START
stop:STOP
true
```

`this.name()` gọi method được kế thừa từ `java.lang.Enum`, trả tên constant khai báo, không phải binary name của constant-specific class.

**Không nhầm:** Có body riêng không biến enum constant thành một value được phép tạo bằng `new Action(...)`. `START` và `STOP` vẫn là named constant instances duy nhất cho từng tên trong enum type.

## 9. Hành vi có tham số thay vì hard-code toàn bộ dữ liệu trong body

Một constant-specific method có thể nhận tham số và tính kết quả dựa trên đầu vào, không phải chỉ trả một chuỗi cố định.

Tạo **`EnumDiscountDemo.java`**:

```java
enum Discount {
    NONE {
        @Override
        int finalPrice(int original) {
            return original;
        }
    },
    TEN_PERCENT {
        @Override
        int finalPrice(int original) {
            return original - original / 10;
        }
    },
    FIXED_20 {
        @Override
        int finalPrice(int original) {
            return Math.max(0, original - 20);
        }
    };

    abstract int finalPrice(int original);
}

public class EnumDiscountDemo {
    public static void main(String[] args) {
        int price = 150;

        for (Discount discount : Discount.values()) {
            System.out.println(discount.name() + "="
                    + discount.finalPrice(price));
        }
    }
}
```

```bash
javac EnumDiscountDemo.java
java EnumDiscountDemo
```

```text
NONE=150
TEN_PERCENT=135
FIXED_20=130
```

Ví dụ áp dụng integer arithmetic: `original / 10` được làm tròn về 0, nên kết quả có rounding behavior của `int`. Đây là bài minh họa dispatch, **không phải** cách chuẩn chung để tính tiền thật. Với money/thuế/phân số cần dùng kiểu và rounding policy phù hợp (ví dụ BigDecimal với scale/rounding được định nghĩa).

**Tiêu chí đúng:** Nếu mỗi lựa chọn thật sự là một **quy tắc tính khác nhau**, constant-specific method body diễn đạt điều đó tự nhiên. Nếu chỉ khác hệ số, một field có thể đơn giản hơn.

## 10. Khi chỉ khác dữ liệu: ưu tiên field và constructor

Thay vì override getter ba lần:

```java
enum Priority {
    LOW {
        @Override
        int weight() {
            return 1;
        }
    },
    MEDIUM {
        @Override
        int weight() {
            return 2;
        }
    },
    HIGH {
        @Override
        int weight() {
            return 3;
        }
    };

    abstract int weight();
}
```

bạn có thể dùng metadata:

```java
enum Priority {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
```

Hai đoạn là **khai báo enum minh họa thay thế nhau**, không đặt cùng một tệp với cùng tên type.

**Vì sao field/constructor đơn giản hơn ở trường hợp này?** Hành vi của `weight()` giống nhau cho cả ba constants: chỉ trả stored value. Dùng ba overrides dễ bị lặp và tăng code không cần thiết.

### Quy tắc lựa chọn

| Dấu hiệu | Hướng thiết kế |
| --- | --- |
| Chỉ khác mã, nhãn, trọng số, hạn mức | Constructor + final metadata fields |
| Mỗi constant có thuật toán thực sự khác | Constant-specific method bodies |
| Đa số dùng mặc định, vài constant đặc biệt | Concrete method + selective override |
| Mọi constant phải tự cung cấp chính sách | Abstract method + override mỗi constant |
| Behavior phụ thuộc config/runtime services phức tạp | Cân nhắc strategy/service bên ngoài enum |

## 11. Phối hợp constructor chung và body riêng

Các constants có thể nhận constructor arguments để lưu metadata dùng bởi logic riêng.

Tạo **`EnumMetadataAndBehaviorDemo.java`**:

```java
enum Shipping {
    NORMAL("N", 5) {
        @Override
        int fee(int items) {
            return 10 + items;
        }
    },
    EXPRESS("E", 1) {
        @Override
        int fee(int items) {
            return 20 + 3 * items;
        }
    },
    PICKUP("P", 0) {
        @Override
        int fee(int items) {
            return 0;
        }
    };

    private final String code;
    private final int promisedDays;

    Shipping(String code, int promisedDays) {
        this.code = code;
        this.promisedDays = promisedDays;
    }

    String code() {
        return code;
    }

    int promisedDays() {
        return promisedDays;
    }

    abstract int fee(int items);
}

public class EnumMetadataAndBehaviorDemo {
    public static void main(String[] args) {
        for (Shipping shipping : Shipping.values()) {
            System.out.println(
                    shipping.code() + ":"
                    + shipping.promisedDays() + ":"
                    + shipping.fee(2));
        }
    }
}
```

```bash
javac EnumMetadataAndBehaviorDemo.java
java EnumMetadataAndBehaviorDemo
```

```text
N:5:12
E:1:26
P:0:0
```

Cú pháp có ý nghĩa:

```java
NORMAL("N", 5) { ... }
```

- `("N", 5)` là arguments cho constructor enum `Shipping(String,int)`.
- `{ ... }` là phần thân riêng của hằng NORMAL.
- Fields `code` và `promisedDays` nằm trong **enum type chung**; mọi constant có data tương ứng.
- Method `fee` thực sự khác logic ở từng hằng, nên abstract polymorphism có giá trị.

**Không viết constructor trong constant-specific body để nhận `"N",5`**. Constructor dùng chung được định nghĩa ở enum declaration và được gọi khi tạo constant theo quy tắc Java.

## 12. Constructor restrictions với enum

Dù enum có constructor, client **không** được gọi `new Shipping("X", 9)`. Tập constant instances do declaration xác định.

Quy tắc cần nhớ:

1. Constructor trong enum là **private hoặc package-private theo cú pháp hợp lệ**, nhưng truy cập tạo enum instances bị ngôn ngữ giới hạn; constructor không thể là `public`/`protected`.
2. Nếu bỏ access modifier, constructor enum được xử lý với quyền truy cập private theo rules enum.
3. Những arguments trong constant declaration sẽ khởi tạo metadata chung.
4. Constructor được thực thi trong quá trình khởi tạo các constants.
5. Body riêng không phải một constructor thứ hai mà client có thể gọi.
6. Tránh dựa vào mutable static state trong constructors khi enum đang trong giai đoạn initialization.

Đoạn sau **cố ý sai**, không chạy:

```java
enum Invalid {
    ONE;

    // public Invalid() { } // Enum constructor không được public.
}
```

**Vì sao?** Nếu constructor public có thể được caller sử dụng, đặc tính “tập hằng cố định” sẽ bị phá. Java chặn việc đó ngay từ ngôn ngữ.

## 13. Method của enum có thể implement interface chung

Enum type có thể `implements` một interface để callers dùng cùng contract mà không cần biết enum cụ thể.

Tạo **`EnumInterfaceBehaviorDemo.java`**:

```java
interface Formatter {
    String format(String value);
}

enum FormatStyle implements Formatter {
    PLAIN {
        @Override
        public String format(String value) {
            return value;
        }
    },
    BRACKETED {
        @Override
        public String format(String value) {
            return "[" + value + "]";
        }
    },
    UPPERCASE {
        @Override
        public String format(String value) {
            return value.toUpperCase(
                    java.util.Locale.ROOT);
        }
    };
}

public class EnumInterfaceBehaviorDemo {
    static void show(Formatter formatter, String input) {
        System.out.println(formatter.format(input));
    }

    public static void main(String[] args) {
        show(FormatStyle.PLAIN, "Java");
        show(FormatStyle.BRACKETED, "Java");
        show(FormatStyle.UPPERCASE, "Java");
    }
}
```

```bash
javac EnumInterfaceBehaviorDemo.java
java EnumInterfaceBehaviorDemo
```

```text
Java
[Java]
JAVA
```

- `Formatter` là interface được implement bởi `FormatStyle`.
- Mỗi constant body có public override `format` theo interface method visibility.
- Caller có thể nhận `Formatter` hoặc `FormatStyle`.
- Không cần ba top-level classes riêng chỉ để mô tả ba chiến lược đóng của một domain nhỏ.

**Cảnh báo:** Interface cho phép nhiều implementations khác; việc `FormatStyle` implement nó không làm `FormatStyle` tự nhận thêm enum constants từ classes bên ngoài.

## 14. Lỗi visibility khi override method interface

Methods của interface (không tính private/static special cases) thường có public contract. Một override tại constant body **không được giảm quyền truy cập**.

Đoạn **sai**, đặt trong một enum phù hợp sẽ không biên dịch:

```java
interface Step {
    String execute();
}

enum InvalidStep implements Step {
    FIRST {
        @Override
        String execute() { // Sai: cần public.
            return "first";
        }
    };
}
```

Điểm sai là `String execute()` trong enum constant body có package-private access, hẹp hơn `public` của interface method.

Sửa thành:

```java
@Override
public String execute() {
    return "first";
}
```

Đây là **mảnh override method** cho ví dụ lỗi trên, không phải chương trình độc lập.

**Cẩn thận dấu `@Override`:** Annotation giúp kiểm method signature khớp; nó **không tự sửa** visibility, checked exceptions hoặc type compatibility.

## 15. Có thể đặt hành vi chung vào enum type và chỉ phân nhánh ở một số hằng

Một enum có thể khai báo helper method chung, dùng trong overridden methods để tránh lặp.

Tạo **`EnumSharedHelperDemo.java`**:

```java
enum MessageStyle {
    PLAIN,
    PREFIXED {
        @Override
        String decorate(String input) {
            return "msg:" + normalize(input);
        }
    },
    SUFFIXED {
        @Override
        String decorate(String input) {
            return normalize(input) + ":end";
        }
    };

    static String normalize(String input) {
        return input.trim();
    }

    String decorate(String input) {
        return normalize(input);
    }
}

public class EnumSharedHelperDemo {
    public static void main(String[] args) {
        for (MessageStyle style : MessageStyle.values()) {
            System.out.println(style.decorate(" hi "));
        }
    }
}
```

```bash
javac EnumSharedHelperDemo.java
java EnumSharedHelperDemo
```

```text
hi
msg:hi
hi:end
```

`normalize` là common static helper của enum, không phụ thuộc constant identity. `decorate` là instance method mà một vài constants override.

**Thiết kế tốt:** Các constants được chia sẻ logic chuẩn hóa ở một nơi. Nếu helper chung quá phức tạp hoặc cần nhiều dependencies, tách sang một utility/service có tên rõ thay vì biến enum thành khối code lớn.

## 16. Phần thân riêng có thể gọi methods/fields của enum chung

Các constants với body riêng vẫn là các đối tượng thuộc enum type; methods override có thể gọi members của enum type theo access rules.

Tạo **`EnumCommonFieldDemo.java`**:

```java
enum Level {
    BASIC(2) {
        @Override
        int adjusted(int input) {
            return input + base();
        }
    },
    PREMIUM(5) {
        @Override
        int adjusted(int input) {
            return input * base();
        }
    };

    private final int value;

    Level(int value) {
        this.value = value;
    }

    final int base() {
        return value;
    }

    abstract int adjusted(int input);
}

public class EnumCommonFieldDemo {
    public static void main(String[] args) {
        System.out.println(Level.BASIC.adjusted(3));
        System.out.println(Level.PREMIUM.adjusted(3));
    }
}
```

```bash
javac EnumCommonFieldDemo.java
java EnumCommonFieldDemo
```

```text
5
15
```

Ở đây `base()` là `final` method của enum, mọi constants gọi chung; nó không cần override và cũng không thể bị override. `adjusted` mới là behavior đặc thù.

**Phân biệt quan trọng:**
- `final` method: không thể override ở constant body.
- `abstract` method: cần implementation ở constant cụ thể.
- Concrete non-final method: constant body có thể override tùy nhu cầu.

## 17. Lỗi khi cố override `final` method

Đây là **mã minh họa lỗi**, không phải chương trình để chạy:

```java
enum Bad {
    A {
        @Override
        int code() {
            return 2;
        }
    };

    final int code() {
        return 1;
    }
}
```

Compiler từ chối override `final int code()`.

**Cách giải quyết**: Nếu method cần đa hình, đừng khai báo final. Nếu nó đại diện một invariant/giá trị chung không thể thay đổi, giữ final và tạo **method khác** cho behavior riêng.

Đừng xóa `final` chỉ để cho code biên dịch nếu business contract của method thật sự cần bất biến.

## 18. Dùng `switch` hay constant-specific behavior?

Cùng bài toán chuyển đổi một hằng thành thông điệp có thể viết theo hai cách.

### Cách A: xử lý bằng `switch` bên ngoài

```java
String label(Phase phase) {
    return switch (phase) {
        case CREATED -> "new";
        case RUNNING -> "working";
        case FINISHED -> "done";
    };
}
```

Đây là **mảnh method minh họa**, giả định đã có `enum Phase { CREATED, RUNNING, FINISHED }`.

### Cách B: method nằm trong enum

```java
enum Phase {
    CREATED {
        @Override
        String label() {
            return "new";
        }
    },
    RUNNING {
        @Override
        String label() {
            return "working";
        }
    },
    FINISHED {
        @Override
        String label() {
            return "done";
        }
    };

    abstract String label();
}
```

Đây là **enum declaration minh họa**, chưa có main.

**Không có người thắng tuyệt đối:**

| Tiêu chí | `switch` | Constant-specific method |
| --- | --- | --- |
| Đặt logic ở đâu | Trong consumer/operation | Gắn trực tiếp với mỗi constant |
| Khi thêm constant | Exhaustive switch có thể báo thiếu nhánh khi rebuild | Abstract method có thể buộc constant mới implement |
| Hành vi chỉ là mapping nhỏ | Thường gọn | Có thể tạo nhiều overrides dài dòng |
| Nhiều consumers cần cùng behavior | Dễ lặp switch | Dễ tái sử dụng method enum |
| Logic thay đổi theo external dependency/context | Consumer/service có thể phù hợp | Dễ làm enum cồng kềnh |
| Hành vi có cùng domain ownership với enum | Có thể đặt switch tại domain service | Method enum thường tự nhiên |
| Dữ liệu chỉ khác giá trị cố định | Mapping table có thể gọn | Final fields/constructor có thể tốt hơn |

**Khuyến nghị:** Đặt behavior ở enum khi nó nhỏ, thuần, gắn chặt với chính sự lựa chọn và được dùng ở nhiều nơi. Dùng switch khi đây là **một góc nhìn của consumer** không nên nhúng vào domain type.

## 19. Ví dụ so sánh dispatch đa hình và `switch` trong cùng chương trình

Tạo **`EnumSwitchVersusOverrideDemo.java`**:

```java
enum Light {
    RED {
        @Override
        String action() {
            return "STOP";
        }
    },
    YELLOW {
        @Override
        String action() {
            return "WAIT";
        }
    },
    GREEN {
        @Override
        String action() {
            return "GO";
        }
    };

    abstract String action();
}

public class EnumSwitchVersusOverrideDemo {
    static String fromSwitch(Light light) {
        return switch (light) {
            case RED -> "STOP";
            case YELLOW -> "WAIT";
            case GREEN -> "GO";
        };
    }

    public static void main(String[] args) {
        for (Light light : Light.values()) {
            System.out.println(light.name() + ":"
                    + light.action().equals(fromSwitch(light)));
        }
    }
}
```

```bash
javac EnumSwitchVersusOverrideDemo.java
java EnumSwitchVersusOverrideDemo
```

```text
RED:true
YELLOW:true
GREEN:true
```

Ví dụ kiểm cả hai implementation trả cùng kết quả trên tập hiện tại. Nhưng production code **không nên giữ hai bộ quy tắc trùng nhau** nếu không có mục đích kiểm tương đương; điều đó làm tăng rủi ro lệch logic khi thêm constant.

## 20. Một workflow có quy tắc trạng thái khác nhau

Khi mỗi trạng thái có quy tắc chuyển tiếp khác nhau, enum behavior có thể chứa phần kiểm *transition* nhỏ.

Tạo **`EnumTransitionBehaviorDemo.java`**:

```java
enum OrderStage {
    NEW {
        @Override
        boolean canMoveTo(OrderStage next) {
            return next == PAID || next == CANCELLED;
        }
    },
    PAID {
        @Override
        boolean canMoveTo(OrderStage next) {
            return next == SENT || next == CANCELLED;
        }
    },
    SENT {
        @Override
        boolean canMoveTo(OrderStage next) {
            return next == DELIVERED;
        }
    },
    DELIVERED {
        @Override
        boolean canMoveTo(OrderStage next) {
            return false;
        }
    },
    CANCELLED {
        @Override
        boolean canMoveTo(OrderStage next) {
            return false;
        }
    };

    abstract boolean canMoveTo(OrderStage next);
}

public class EnumTransitionBehaviorDemo {
    public static void main(String[] args) {
        System.out.println(
                OrderStage.NEW.canMoveTo(OrderStage.PAID));
        System.out.println(
                OrderStage.NEW.canMoveTo(OrderStage.SENT));
        System.out.println(
                OrderStage.PAID.canMoveTo(OrderStage.SENT));
        System.out.println(
                OrderStage.CANCELLED.canMoveTo(OrderStage.PAID));
    }
}
```

```bash
javac EnumTransitionBehaviorDemo.java
java EnumTransitionBehaviorDemo
```

```text
true
false
true
false
```

### Ranh giới quan trọng

- Enum cho ta **tập trạng thái** và rules nhỏ về lựa chọn chuyển trạng thái.
- Việc thực sự chuyển state trên một Order instance cần thêm validation, atomicity, kiểm payment/inventory, persist và authorization theo nghiệp vụ.
- Method `canMoveTo` chỉ tính boolean, không sửa global state.
- Không tự động cho rằng mọi transitions được định nghĩa bằng enum đều hợp lệ cho mọi đơn hàng.

Một thiết kế lý tưởng có thể giữ **pure transition rules** ở enum, còn **side effects** trong service/aggregate riêng.

## 21. `switch` có thể phù hợp hơn với hành vi phụ thuộc nguồn bên ngoài

Ví dụ mỗi OrderStage đòi kiểm một service hoặc database khác. Nếu đặt thẳng database client/network logic vào constant body, enum có nguy cơ trở thành singleton objects nắm dependencies và vòng đời phức tạp.

Tình huống:

- `PAID` cần gọi payment service.
- `SENT` cần shipment service.
- `CANCELLED` cần refund service.

Chúng là operations với dependencies có thể cấu hình/test/mock. Khi ấy một **interface Strategy**, ứng dụng service hoặc dispatch table quản lý bằng dependency injection có thể phù hợp hơn.

**Mẫu định hướng:**

```java
interface Handler {
    void handle(OrderContext context);
}
```

Đây là **mảnh interface minh họa**, không phải mã của một framework cụ thể. `OrderContext` là kiểu ví dụ cần khai báo trong ứng dụng thực.

Enum vẫn có thể giữ **identifier** của loại xử lý, còn factory/map từ identifier sang Handler lưu ở service. Điều này bảo vệ enum khỏi phụ thuộc vào hệ thống bên ngoài và cho phép unit tests độc lập.

## 22. Lớp con ngầm và `getClass()`: một chi tiết quan trọng

Một enum constant có phần thân riêng được thực hiện bằng một class con ngầm của enum. Do đó **runtime class** của constant có body riêng không nhất thiết là trực tiếp `Mode.class`.

Cách kiểm đúng **enum type khai báo** là `getDeclaringClass()`.

Tạo **`EnumRuntimeClassDemo.java`**:

```java
enum Mode {
    NORMAL,
    SPECIAL {
        @Override
        String label() {
            return "special";
        }
    };

    String label() {
        return "normal";
    }
}

public class EnumRuntimeClassDemo {
    public static void main(String[] args) {
        System.out.println(
                Mode.NORMAL.getClass() == Mode.class);
        System.out.println(
                Mode.SPECIAL.getClass() == Mode.class);

        System.out.println(
                Mode.NORMAL.getDeclaringClass() == Mode.class);
        System.out.println(
                Mode.SPECIAL.getDeclaringClass() == Mode.class);

        System.out.println(Mode.SPECIAL.label());
    }
}
```

```bash
javac EnumRuntimeClassDemo.java
java EnumRuntimeClassDemo
```

```text
true
false
true
true
special
```

**Giải thích:**

- NORMAL không có constant-specific body, nên runtime class trực tiếp là Mode.
- SPECIAL có body, nên runtime class là một lớp con ngầm của Mode.
- `getDeclaringClass()` trả `Mode.class` cho cả hai constants.
- Hành vi `label` được dispatch theo actual constant.

**Sai lầm phổ biến:** `constant.getClass() == Mode.class` không phải điều kiện đúng cho mọi constant. Khi cần xác định enum type một cách có ý nghĩa, dùng `getDeclaringClass()`.

**Không in hardcoded compiler-generated class names** bằng `getClass().getName()` rồi đưa chúng thành hợp đồng. Chúng là chi tiết implementation và có thể thay đổi theo compiler/cấu trúc source.

## 23. Tên và identity hằng không đổi khi có body riêng

Dù constant có subclass ngầm, `name()`, `ordinal()` và `values()` vẫn gắn với declaration của enum.

Tạo **`EnumConstantIdentityDemo.java`**:

```java
enum Operation {
    FIRST {
        @Override
        String answer() {
            return "A";
        }
    },
    SECOND {
        @Override
        String answer() {
            return "B";
        }
    };

    abstract String answer();
}

public class EnumConstantIdentityDemo {
    public static void main(String[] args) {
        for (Operation item : Operation.values()) {
            System.out.println(item.name() + ":"
                    + item.ordinal() + ":"
                    + item.answer());
        }

        System.out.println(
                Operation.valueOf("FIRST") == Operation.FIRST);
    }
}
```

```bash
javac EnumConstantIdentityDemo.java
java EnumConstantIdentityDemo
```

```text
FIRST:0:A
SECOND:1:B
true
```

`name()` là tên khai báo, `ordinal()` là vị trí bắt đầu từ 0, `valueOf` tìm theo tên. Phần thân riêng **không làm `FIRST` trở thành một enum type mới cho client**.

**Không dùng `ordinal()` làm business ID/persisted code:** Thêm hoặc đổi thứ tự constants có thể thay số ấy. Dùng field `code` cố định nếu external compatibility quan trọng.

## 24. `toString()` cũng có thể khác nhau theo constant

`toString()` là một method có thể override. Nó hữu ích cho display, nhưng cần phân biệt với `name()` và `valueOf`.

Tạo **`EnumToStringOverrideDemo.java`**:

```java
enum Outcome {
    OK {
        @Override
        public String toString() {
            return "Thanh cong";
        }
    },
    ERROR {
        @Override
        public String toString() {
            return "That bai";
        }
    };
}

public class EnumToStringOverrideDemo {
    public static void main(String[] args) {
        System.out.println(Outcome.OK.name());
        System.out.println(Outcome.OK.toString());
        System.out.println(Outcome.valueOf("ERROR"));
    }
}
```

```bash
javac EnumToStringOverrideDemo.java
java EnumToStringOverrideDemo
```

```text
OK
Thanh cong
That bai
```

Dòng thứ ba `valueOf("ERROR")` tìm constant theo **`name`**, nhưng `println` gọi override `toString()` của ERROR nên in “That bai”.

**Giới hạn hiển thị:** Khi cần localization, labels thường nên lấy từ resource bundles/message keys thay vì hardcode ngôn ngữ trong enum. Không dùng `toString()` làm mã API/database ổn định nếu output có thể thay theo yêu cầu UI.

## 25. Không thể thêm constants bằng kế thừa hoặc `new` từ bên ngoài

Constant-specific class bodies là cách Java cho phép định nghĩa behavior khác nhau trong **tập hằng có sẵn**. Chúng **không** mở enum để subclass từ code client.

Các ý định sau là **sai**:

```java
// class NewOperation extends Operation { ... }
// Operation extra = new Operation();
// Operation plugin = registerAtRuntime(...);
```

Ngoài việc enum không cho user-defined subclasses như class thường, `Operation` không phải plugin registry có thể tự thêm constants ngoài source.

**Khi nào đây là lợi thế?** Khi tập lựa chọn đóng và phải xử lý tất cả hằng theo contract. Compiler có thể hỗ trợ bắt thiếu behavior.

**Khi nào đây là hạn chế?** Khi bên thứ ba cần tự đăng ký hành vi không biết trước vào runtime: hãy dùng interface, concrete strategy implementations và registry/configuration riêng.

## 26. Thêm một hằng mới: lợi ích và trách nhiệm

Giả sử enum `Operation` ban đầu có ADD/SUBTRACT, sau này thêm DIVIDE:

```java
DIVIDE {
    @Override
    int apply(int a, int b) {
        if (b == 0) {
            throw new ArithmeticException("division by zero");
        }
        return a / b;
    }
}
```

Đây là **mảnh constant declaration minh họa**, chỉ đúng khi được đưa vào danh sách constants của một enum có abstract method `apply(int,int)`.

Khi thêm DIVIDE:

- Compiler đòi override abstract apply nếu không có implementation chung.
- Phải xác định rõ xử lý `b == 0`.
- Phải định nghĩa integer division hay floating-point division.
- Các consumers dùng `switch` có thể cần cập nhật.
- UI, serializers, persisted values và tests có thể cần hỗ trợ tên mới.
- `values()` bây giờ có thêm một constant và `ordinal()` có thể bị ảnh hưởng tùy vị trí chèn.

**Đừng chỉ xem việc “compile PASS” là bằng chứng hành vi nghiệp vụ đúng**. Compiler đảm bảo có method implementation về cú pháp/type, không chứng minh thuật toán chính xác.

## 27. Giữ enum constants immutable khi có thể

Enum constants có **identity ổn định** nhưng instance fields **không tự immutable**.

Ví dụ:

```java
enum Counter {
    A;

    private int hits;

    void hit() {
        hits++;
    }

    int hits() {
        return hits;
    }
}
```

Đây là khai báo hợp lệ, nhưng `Counter.A` là một **shared singleton-like enum constant**. Nếu nhiều requests gọi `hit()`, cùng một field `hits` thay đổi; không còn là state riêng từng request.

### Rủi ro còn lớn hơn với constant-specific state

```java
enum BadCache {
    ONE {
        private final java.util.ArrayList<String> items =
                new java.util.ArrayList<>();

        @Override
        int size() {
            items.add("x");
            return items.size();
        }
    };

    abstract int size();
}
```

Đây là **khai báo hợp lệ** nhưng cố ý minh họa thiết kế không tốt: mỗi lần gọi `BadCache.ONE.size()` lại mutate shared list, khiến kết quả phụ thuộc thứ tự/số lần gọi và không thread-safe.

**Khuyến nghị:**

- Ưu tiên final fields chứa primitive/immutable metadata.
- Ưu tiên pure methods phụ thuộc inputs, không side effects.
- Đặt request/session data trong class instance riêng.
- Nếu thật sự cần mutable shared state, phải định nghĩa synchronization, lifecycle, reset policy và testing; enum không tự làm điều ấy an toàn.

## 28. Không dùng enum constant body để lưu per-user/per-request state

Một nhầm lẫn thiết kế phổ biến:

> “Mỗi enum constant có class body riêng, vậy tôi lưu user counter trong class body ấy để tạo state theo mỗi request được không?”

Không. Enum constant object không được tạo lại cho mỗi request. Nếu field mutable nằm trong constant-specific body, state ấy gắn với **constant instance**, có thể được mọi callers chia sẻ.

Một thiết kế thích hợp:

- Enum `PlanType` mô tả BASIC/PRO.
- Class `Subscription` mô tả **một thuê bao cụ thể**, có userId, startDate, status, limits…
- Method `PlanType.allowedSeats()` có thể trả metadata chung.
- Method `Subscription.useSeat()` mutate state của **một thuê bao**, không mutate enum constant toàn hệ thống.

**Phân biệt type/domain category với domain entity instance.** Constant-specific behavior phù hợp cho category-level rules; mutable entity state thuộc objects khác.

## 29. Thứ tự thực thi: constants được khởi tạo như objects, không phải chạy mỗi lần gọi

Mỗi hằng enum được tạo trong quá trình enum class initialization theo quy tắc Java. Phần thân riêng định nghĩa implementation của methods, nhưng **không có nghĩa mọi statements khai báo trong initializer chạy lại mỗi lần dùng constant**.

Tạo **`EnumInitializationDemo.java`**:

```java
enum Feature {
    ALPHA {
        @Override
        int score() {
            return base() + 1;
        }
    },
    BETA {
        @Override
        int score() {
            return base() + 2;
        }
    };

    private final int base = 10;

    int base() {
        return base;
    }

    abstract int score();
}

public class EnumInitializationDemo {
    public static void main(String[] args) {
        System.out.println(Feature.ALPHA.score());
        System.out.println(Feature.ALPHA.score());
        System.out.println(Feature.BETA.score());
    }
}
```

```bash
javac EnumInitializationDemo.java
java EnumInitializationDemo
```

```text
11
11
12
```

`Feature.ALPHA` không được tạo lại giữa hai lần gọi. Method `score` được gọi hai lần trên **cùng enum constant object**.

**Tránh code có side effects trong constructor/initializer** nếu chỉ muốn compute khi gọi method. Ngược lại, nếu method cần cache, phải thiết kế cache với thread safety/lifecycle rõ ràng thay vì ngầm trông chờ vào enum initialization.

## 30. Method call bên trong body có thể dùng member chung và helper ngoài

Một method override có thể delegate sang pure helper:

```java
@Override
int fee(int items) {
    return FeeRules.express(items);
}
```

Đây là **mảnh override minh họa**; `FeeRules` là một helper class giả định phải được định nghĩa trong ứng dụng.

Không bắt buộc mỗi dòng business logic nằm trong enum. Nếu thuật toán lớn nhưng tập lựa chọn vẫn đóng, enum có thể giữ:

- Code/label/metadata.
- Một method ngắn điều phối.
- Delegation sang pure helper hoặc strategy đã có API test riêng.

Điều này giữ **hành vi enum rõ**, không biến source file enum thành một khối quá dài.

## 31. Constant-specific fields và method visibility

Một constant-specific body có thể có field hoặc method hỗ trợ riêng, nhưng code bên ngoài thường chỉ biết static type của enum, nên **không gọi được members đặc thù chưa được khai báo trong enum/interface**.

Ví dụ:

```java
enum Detail {
    SPECIAL {
        private String helper() {
            return "SPECIAL";
        }

        @Override
        String describe() {
            return helper();
        }
    };

    abstract String describe();
}
```

Đây là **khai báo hợp lệ**, không có main.

Caller hợp lệ:

```java
String text = Detail.SPECIAL.describe();
```

Nhưng caller **không có API trực tiếp `Detail.SPECIAL.helper()`**, vì static type `Detail` không khai báo helper method. Helper là chi tiết implementation private trong body.

**Bài học về encapsulation:** Không phải cứ đặt method trong constant body là tự expose method đó như public API. Hãy đặt contract chung ở enum/interface, và giữ helpers bên trong bodies nếu chúng chỉ phục vụ một constant.

## 32. `getDeclaringClass()` tốt hơn dùng `getClass()` để nhận diện enum type

Trong hệ thống generic xử lý enums, bạn có thể cần biết hằng thuộc **enum declaration nào**.

`constant.getDeclaringClass()` trả enum type mà constant được khai báo. Trong khi đó `constant.getClass()` có thể là subclass ngầm nếu constant có body riêng.

Sơ đồ:

```text
Operation (enum type)
  |
  +-- ADD constant: runtime class có body riêng
  |
  +-- SUBTRACT constant: runtime class có body riêng

ADD.getDeclaringClass() == Operation.class
SUBTRACT.getDeclaringClass() == Operation.class
```

**Không dùng binary-name string parsing** để lấy tên constant hay enum type. Dùng public API:

- `name()` để lấy constant name.
- `getDeclaringClass()` để lấy enum type.
- `values()` để duyệt constants của enum cụ thể.
- `Enum.valueOf(EnumClass.class, name)` khi xử lý enum class ở generic code.

## 33. Giới hạn riêng về `equals`, `hashCode` và `clone`

Enum constants kế thừa những quy tắc identity nhất quán từ `java.lang.Enum`. Không nên và về cơ bản cũng không thể override những phương thức final này để biến từng constant thành value object tùy ý.

- `equals` của enum có identity semantics.
- `hashCode` không phải business ID ổn định.
- `clone()` của Enum là final và chặn sao chép constants theo API.
- Mỗi constant có identity riêng, có thể so `==`.
- `name()` và `ordinal()` là metadata do Enum cung cấp; không override thành dữ liệu khác.
- `compareTo` dựa trên thứ tự khai báo, không phải business ranking tự định nghĩa.

**Lý do:** Enum là các named constant instances. Nếu cho client clone hoặc tái định nghĩa identity, mô hình “một hằng có tên” sẽ mất tính nhất quán.

**Nếu cần nhiều objects có cùng category nhưng state khác nhau:** tạo class/record riêng có field trỏ tới enum constant, không cố clone enum object.

## 34. Một số lỗi compile-time thường gặp

| Ý định / lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Quên `;` trước member declarations sau constants | Sai cú pháp enum body | Thêm `;` sau constant list |
| Enum có abstract method nhưng một constant không implement | Thiếu concrete behavior | Override hoặc dùng default method |
| Sai tên tham số/method signature ở override | Không khớp method cần override | Giữ `@Override` để compiler báo |
| Override interface method bằng package-private method | Giảm visibility so với public | Dùng `public` |
| Override method đã `final` ở enum | Java cấm override final | Đổi thiết kế hoặc tạo method khác |
| Cố gọi `new EnumName()` | Enum instances chỉ do declaration xác định | Dùng tên constant |
| Cố viết constructor trong constant body bằng tên constant | Constant body không là một enum declaration độc lập | Định nghĩa constructor ở enum |
| Cố `extends AnotherEnum` | Enum có superclass đặc biệt Enum | Interface hoặc composition |
| Cố subclass enum từ class bên ngoài | Enum không mở để subclass tùy ý | Strategy/registry nếu cần mở rộng |
| Dùng `getClass()==EnumType.class` cho mọi constant | Constant có body có runtime subclass | Dùng `getDeclaringClass()` |
| Cố gọi helper chỉ nằm trong body qua type enum | Member không thuộc API enum type | Định nghĩa contract chung |
| Dùng `ordinal()` làm persisted ID | Thay thứ tự constant có thể đổi số | Stable code field |
| Dùng `toString()` để parse constant name | toString có thể override | `name()/valueOf` hoặc external code parser |
| Đặt mutable list/counter trong constant body | Shared singleton-like mutable state | Per-instance state tách riêng |
| Giả định mọi constant body có constructor riêng | Constructor thuộc enum chung | Truyền arguments ở constant declaration |
| Method abstract trả kết quả business sai nhưng compiler PASS | Type checking không chứng minh thuật toán đúng | Tests cho từng constant |
| Copy y nguyên logic vào nhiều overrides | Duplicated behavior | Common helper/default implementation |
| Đưa I/O/DB/HTTP vào enum constant | Coupling/lifecycle khó test | Service/strategy bên ngoài |

## 35. Self-test: kiểm đầy đủ hành vi của mọi constant

Một bài thực hành tốt là viết tests duyệt `values()` và xác nhận **mọi hằng** có behavior đúng, không chỉ test một hằng yêu thích.

Tạo **`EnumBehaviorSelfTest.java`**:

```java
enum MathAction {
    ADD {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    SUBTRACT {
        @Override
        int apply(int a, int b) {
            return a - b;
        }
    },
    MAX {
        @Override
        int apply(int a, int b) {
            return Math.max(a, b);
        }
    };

    abstract int apply(int a, int b);
}

public class EnumBehaviorSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(MathAction.values().length == 3, "count");
        check(MathAction.ADD.apply(8, 3) == 11, "ADD");
        check(MathAction.SUBTRACT.apply(8, 3) == 5,
                "SUBTRACT");
        check(MathAction.MAX.apply(8, 3) == 8, "MAX");

        for (MathAction action : MathAction.values()) {
            check(action.getDeclaringClass() ==
                    MathAction.class, "declaring class");
            check(action.apply(2, 2) >= 0,
                    "nonnegative sample");
        }

        check(MathAction.valueOf("ADD") == MathAction.ADD,
                "valueOf");
        System.out.println("enum behavior PASS");
    }
}
```

```bash
javac EnumBehaviorSelfTest.java
java EnumBehaviorSelfTest
```

```text
enum behavior PASS
```

`check` ném `AssertionError` trực tiếp khi false, nên không phụ thuộc flag JVM `-ea`.

**Phạm vi kiểm:** Đây là self-test đơn giản cho ba phép toán trên inputs cụ thể. Trong production, hãy bổ sung edge cases như overflow, âm/dương, bằng nhau, hoặc property tests nếu contract có bất biến rộng hơn.

## 36. Kiểm thử trường hợp method mặc định và override riêng

Ví dụ có một concrete default và một override. Test nên xác minh **cả default path lẫn override path**.

Tạo **`EnumDefaultOverrideTest.java`**:

```java
enum Channel {
    EMAIL,
    SMS {
        @Override
        String label() {
            return "short message";
        }
    },
    PUSH;

    String label() {
        return "notification";
    }
}

public class EnumDefaultOverrideTest {
    static void check(boolean ok, String name) {
        if (!ok) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        check(Channel.EMAIL.label().equals("notification"),
                "EMAIL default");
        check(Channel.PUSH.label().equals("notification"),
                "PUSH default");
        check(Channel.SMS.label().equals("short message"),
                "SMS override");

        System.out.println("default and override PASS");
    }
}
```

```bash
javac EnumDefaultOverrideTest.java
java EnumDefaultOverrideTest
```

```text
default and override PASS
```

Nếu sau này một developer đổi default label, tests phải phản ánh policy mới. Nếu vô tình bỏ override của SMS, test bắt sai ngay, dù compiler có thể không báo vì method mặc định đã tồn tại.

**So với abstract method:** Abstract declaration giúp bắt thiếu implementation; default implementation không bắt thiếu override, nên test business behavior càng quan trọng.

## 37. Bài tập: viết enum cho hình học đơn giản

Hãy xây enum `ShapeType` có hai hằng `SQUARE` và `RECTANGLE`. Mỗi hằng override method tính diện tích theo hai tham số nguyên dương. Mục tiêu:

- `SQUARE.area(side, ignored)` trả `side * side`.
- `RECTANGLE.area(width, height)` trả `width * height`.
- Kiểm inputs dương.
- Không thêm hằng runtime ngoài declaration.
- Unit tests từng hằng, bao gồm invalid values.

### Một lời giải tham khảo chạy được

Tệp **`ShapeTypeExercise.java`**:

```java
enum ShapeType {
    SQUARE {
        @Override
        int area(int first, int second) {
            requirePositive(first);
            return Math.multiplyExact(first, first);
        }
    },
    RECTANGLE {
        @Override
        int area(int first, int second) {
            requirePositive(first);
            requirePositive(second);
            return Math.multiplyExact(first, second);
        }
    };

    static void requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "positive dimensions required");
        }
    }

    abstract int area(int first, int second);
}

public class ShapeTypeExercise {
    public static void main(String[] args) {
        System.out.println(ShapeType.SQUARE.area(4, 0));
        System.out.println(ShapeType.RECTANGLE.area(4, 5));

        try {
            ShapeType.RECTANGLE.area(0, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid size");
        }
    }
}
```

```bash
javac ShapeTypeExercise.java
java ShapeTypeExercise
```

```text
16
20
invalid size
```

**Nhận xét thiết kế:** Để biểu diễn hình vuông, tham số thứ hai bị bỏ qua là dấu hiệu method signature `area(int,int)` chưa phải tối ưu. Có thể thiết kế interface/value object riêng cho từng shape nếu API cần biểu diễn kích thước chặt chẽ. Ví dụ tập trung vào **hành vi khác nhau ở từng enum constant**, không đề xuất một hình học library thực tế.

## 38. Bài tập: metadata kết hợp behavior riêng

Hãy triển khai một enum `Transport` có:

- `WALK("W", 0)`
- `BIKE("B", 1)`
- `CAR("C", 2)`

Mỗi hằng có `String code` và `int speedTier`, cùng method `estimateMinutes(int kilometers)` với cách tính riêng. Hãy quy định đơn giản: 1 km WALK = 12 phút, BIKE = 4 phút, CAR = 2 phút.

### Lời giải chạy được

Tạo **`TransportExercise.java`**:

```java
enum Transport {
    WALK("W", 0) {
        @Override
        int estimateMinutes(int kilometers) {
            return Math.multiplyExact(kilometers, 12);
        }
    },
    BIKE("B", 1) {
        @Override
        int estimateMinutes(int kilometers) {
            return Math.multiplyExact(kilometers, 4);
        }
    },
    CAR("C", 2) {
        @Override
        int estimateMinutes(int kilometers) {
            return Math.multiplyExact(kilometers, 2);
        }
    };

    private final String code;
    private final int speedTier;

    Transport(String code, int speedTier) {
        this.code = code;
        this.speedTier = speedTier;
    }

    String code() {
        return code;
    }

    int speedTier() {
        return speedTier;
    }

    abstract int estimateMinutes(int kilometers);
}

public class TransportExercise {
    public static void main(String[] args) {
        for (Transport mode : Transport.values()) {
            System.out.println(mode.code() + ":"
                    + mode.speedTier() + ":"
                    + mode.estimateMinutes(3));
        }
    }
}
```

```bash
javac TransportExercise.java
java TransportExercise
```

```text
W:0:36
B:1:12
C:2:6
```

**Phạm vi:** Đây là phép tính giả định để luyện thiết kế enum, không phải thời gian đi lại thực tế; không xét giao thông, địa hình, tốc độ, quãng nghỉ. Khi dùng trong thực tế phải validate kilometers không âm và xác định rounding/units.

## 39. Khi nào cách này làm code tốt hơn?

Một phần thân riêng cho hằng có giá trị khi thỏa các dấu hiệu:

- Tập các loại được **biết trước và đóng theo phiên bản code**.
- Mỗi loại có **hành vi khác nhau nhưng chung một API**.
- Method behavior là rule nhỏ, ổn định, gắn mạnh với danh tính constant.
- Các callers lặp lại `switch/if` dựa trên chính enum constant chỉ để làm cùng một thao tác.
- Abstract method contract giúp **khó quên** implementation khi thêm hằng.
- Logic vẫn đủ ngắn để đọc hiểu khi xem enum declaration.

Ví dụ tốt: các toán tử số học đơn giản, formatter modes, mức policy, trạng thái có quy tắc chuyển tiếp thuần, cách tính phí cố định.

### Khi nào nên tránh?

- Chỉ khác số liệu/nhãn: dùng constructor fields.
- Nhiều thuật toán lớn, thay đổi độc lập: dùng Strategy/service.
- Tập loại do người dùng/plugin bổ sung runtime: dùng interface/registry, không đóng trong enum.
- Behavior có side effects/lifecycle/DI: tách orchestration khỏi enum.
- Mutable state per request: dùng class instances riêng.
- Nhiều consumers muốn quan điểm khác nhau về enum, ví dụ UI và persistence: tránh nhét mọi behavior vào cùng enum.

**Nguyên tắc bảo trì:** Enum là nơi diễn tả một loại domain có tên. Đừng biến nó thành trung tâm của mọi nghiệp vụ chỉ vì method dispatch thuận tiện.

## 40. Checklist đọc và review constant-specific body

- [ ] Enum có **tập hằng đóng** đúng nghiệp vụ?
- [ ] Những hằng nào thực sự khác behavior, chứ không chỉ khác metadata?
- [ ] Dấu `{ ... }` sau mỗi hằng được đặt đúng cú pháp?
- [ ] Có dấu `;` sau constant list nếu enum còn khai báo members?
- [ ] Abstract methods được mọi constants cần thiết implement?
- [ ] Nếu method có default, các hằng không override có thực sự chấp nhận default?
- [ ] `@Override` có được dùng để bắt sai signatures?
- [ ] Nếu implement interface, override methods có `public` phù hợp?
- [ ] Không override `final` methods?
- [ ] Tên constant, constructor arguments và phần thân riêng có vai trò rõ?
- [ ] Constructor chỉ được khai báo trong enum type, không tưởng tượng body riêng là constructor mới?
- [ ] Methods pure, không có mutable shared per-user state?
- [ ] Nếu có fields, ưu tiên immutable metadata và copy defensive khi cần?
- [ ] `getDeclaringClass()` được dùng khi cần enum type, không suy từ `getClass()`?
- [ ] Không phụ thuộc compiler-generated names của constant-specific subclasses?
- [ ] `name()`, `ordinal()`, `toString()` được dùng đúng mục đích?
- [ ] Không lưu `ordinal()` thành external ID?
- [ ] Đã test từng constant, cả default và overridden paths?
- [ ] Thêm hằng mới có kích hoạt review/tests cho behavior, switch, mapping?
- [ ] Có dùng interface/strategy/service khi behavior quá phức tạp hoặc cần mở rộng runtime?
- [ ] Không gắn database/network resource trực tiếp vào shared enum constants nếu không có chính sách rõ?
- [ ] Tên file/public class và stdout của ví dụ đã khớp Java 17+?

## 41. Câu hỏi tự luyện có đáp án

**Câu 1.** `ADD { ... }` trong một enum có tạo thêm enum constant ngoài ADD không?

*Đáp án:* Không. Đó là phần thân riêng của constant ADD, vẫn đúng một hằng có tên ADD.

**Câu 2.** Có phải mọi hằng enum đều bắt buộc có body riêng?

*Đáp án:* Không. Chỉ cần body khi hằng có implementation riêng; các hằng khác có thể dùng behavior concrete mặc định.

**Câu 3.** Nếu enum có `abstract int apply(...)`, mỗi constant phải làm gì?

*Đáp án:* Cung cấp concrete implementation phù hợp, thường bằng override trong constant-specific class body.

**Câu 4.** Nếu method enum là concrete và không final thì một constant có override được không?

*Đáp án:* Có, trong constant-specific body theo override rules.

**Câu 5.** Nếu method enum là `final` thì sao?

*Đáp án:* Constant-specific subclass không được override.

**Câu 6.** `this` trong method của body riêng chỉ đến đâu?

*Đáp án:* Chính constant object đang nhận lời gọi.

**Câu 7.** `super.method()` trong body riêng có gọi method của hằng khác không?

*Đáp án:* Không. Nó gọi superclass implementation, nếu method phù hợp.

**Câu 8.** Tại sao `getClass() == EnumType.class` có thể false?

*Đáp án:* Constant có body riêng có runtime subclass ngầm; dùng `getDeclaringClass()` để nhận enum declaration type.

**Câu 9.** `name()` của constant có body riêng vẫn trả gì?

*Đáp án:* Tên enum constant khai báo, ví dụ `ADD`.

**Câu 10.** Constructor parameters `ADD("A",1) { ... }` được nhận ở đâu?

*Đáp án:* Trong constructor của enum type, không phải constructor do constant body tự khai báo.

**Câu 11.** Một enum constant implement method của interface cần quyền truy cập gì?

*Đáp án:* Override phải đáp ứng visibility của interface, thường `public`.

**Câu 12.** Chỉ khác weight giữa LOW/MEDIUM/HIGH, nên override weight ba lần hay dùng fields?

*Đáp án:* Thường final metadata field/constructor đơn giản hơn.

**Câu 13.** Khi nào constant body tốt hơn `switch`?

*Đáp án:* Khi behavior nhỏ và gắn chặt với constant, được dùng lại ở nhiều consumers và đặt ở enum giúp tránh lặp switches.

**Câu 14.** Khi nào `switch`/service tốt hơn?

*Đáp án:* Khi behavior thuộc một consumer perspective, thay đổi độc lập, hoặc cần external dependencies/resources.

**Câu 15.** Enum với body riêng có thể được plugin thêm hằng runtime không?

*Đáp án:* Không. Tập constants vẫn đóng theo enum declaration.

**Câu 16.** Có nên giữ counter của từng user trong enum constant không?

*Đáp án:* Không. Constant instance được chia sẻ; state phải ở per-user object.

**Câu 17.** `valueOf("ADD")` có phụ thuộc constant-specific runtime class name không?

*Đáp án:* Không, tra cứu bằng enum constant name khai báo.

**Câu 18.** `toString()` có thể trả nhãn khác `name()` không?

*Đáp án:* Có, toString có thể override; name vẫn đại diện tên constant.

**Câu 19.** Khi thêm constant mới vào enum có abstract method, compiler giúp thế nào?

*Đáp án:* Có thể báo thiếu implementation nếu constant mới không override và không có concrete inherited implementation.

**Câu 20.** Lợi ích cốt lõi của constant-specific class body là gì?

*Đáp án:* Cho từng named constant **hành vi đa hình riêng** dưới một API enum type chung, trong khi tập constants vẫn được khai báo hữu hạn.

---

**Ghi nhớ cuối bài:** Với Java `enum`, **`CONSTANT { ... }`** là **phần thân lớp riêng của hằng** (*constant-specific class body*), cho phép override methods và áp dụng **đa hình** trên một tập lựa chọn đóng. Khi **mọi hằng** phải tự xử lý, khai báo `abstract method` chung để compiler buộc triển khai; khi chỉ vài hằng là ngoại lệ, dùng concrete default method và override có chọn lọc. Kết hợp constructor/final fields cho metadata, còn body riêng cho **thuật toán thực sự khác**. Những constants này vẫn thuộc cùng enum type qua `getDeclaringClass()` dù `getClass()` có thể khác ở hằng có body, và **không thể được mở rộng động** từ client. Ưu tiên behavior nhỏ, thuần, có tests theo từng constant; với quy tắc phức tạp, mutable per-request state hoặc dependencies bên ngoài, hãy cân nhắc strategy/service tách riêng.