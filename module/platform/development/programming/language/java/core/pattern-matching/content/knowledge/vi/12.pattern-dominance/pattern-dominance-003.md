# Type pattern cha chi phối type pattern con trong Java

## 1. Vấn đề: tại sao một case hợp lệ về kiểu vẫn không được biên dịch?

Kể từ **Java 21**, pattern matching for `switch` là tính năng chính thức. Bạn có thể viết các nhánh dựa trên kiểu thực tế của đối tượng:

~~~java
return switch (value) {
    case String s -> "Chuỗi: " + s;
    case CharSequence chars -> "Dãy ký tự";
    default -> "Khác";
};
~~~

Giả sử `value` có kiểu tĩnh `Object`. Mã này **hợp lệ** vì nhánh `String` đứng **trước** nhánh rộng hơn `CharSequence`.

Nếu đảo thứ tự, compiler từ chối:

~~~java
return switch (value) {
    case CharSequence chars -> "Dãy ký tự";
    case String s -> "Chuỗi: " + s; // COMPILE ERROR: dominated case label
    default -> "Khác";
};
~~~

Lý do: mọi đối tượng `String` đều triển khai `CharSequence`. Khi gặp một `String`, case `CharSequence` **đã nhận nó trước**, nên case `String` phía sau **không thể được chọn**. Java gọi trường hợp đó là **dominance** (một nhãn case *chi phối* hoặc *che* một nhãn case phía sau).

> **Quy tắc nhớ nhanh:** Trong một `switch` có type patterns, **pattern tổng quát không có guard thực sự** đặt trước có thể chi phối pattern cụ thể hơn phía sau. Muốn phân loại theo kiểu con, hãy ưu tiên **case con trước, case cha sau**.

Lưu ý: kiểm tra dominance diễn ra **khi biên dịch**, không phải khi chương trình chạy. Đây không chỉ là cảnh báo mã chết hoặc vấn đề thứ tự tùy ý: chương trình sai sẽ **không biên dịch**.

## 2. Hiểu đúng “cha”, “con” và quan hệ kiểu

Trong bài này:

- **Kiểu cha / kiểu rộng hơn:** kiểu bao phủ các đối tượng thuộc một hoặc nhiều kiểu con, như `CharSequence` so với `String`, `Number` so với `Integer`, `List<?>` so với `ArrayList<?>`.
- **Kiểu con / kiểu hẹp hơn:** kiểu mà các instance của nó cũng là instance của kiểu cha, như `String` là một `CharSequence`.
- **Type pattern:** một nhãn `case T variable` kiểm tra selector có khớp kiểu `T` và đặt tên biến mẫu nếu khớp.

Mối quan hệ không nhất thiết là `extends` trực tiếp giữa hai **class**. **Interface** và **kế thừa gián tiếp** cũng rất quan trọng:

~~~text
Object
├── CharSequence (interface)
│   ├── String
│   └── StringBuilder
├── Number
│   ├── Integer
│   └── Double
└── List (interface)
    └── ArrayList
~~~

Sơ đồ chỉ minh họa các quan hệ liên quan, **không** phải cây kế thừa Java đầy đủ: interface và class có thể nằm trong nhiều quan hệ cùng lúc. Ví dụ, `String` còn triển khai `Serializable` và các interface khác.

Với kiểu rộng `T` và hẹp `U`, nếu mọi giá trị khớp `U` cũng khớp `T` thì nhãn `case T t` **không guard** đứng trước thường **dominate** nhãn `case U u` đứng sau. Java Language Specification định nghĩa quy tắc chính xác, bao gồm các trường hợp parameterized types, pattern guards và những dạng nhãn khác; đừng thay thế toàn bộ đặc tả bằng quy tắc “chỉ xét superclass trực tiếp”.

### Bảng các quan hệ quen thuộc

| Case trước (rộng hơn) | Case sau (hẹp hơn) | Kết quả nếu cả hai không guard |
| --- | --- | --- |
| `case CharSequence cs` | `case String s` | Case String bị dominate |
| `case Number n` | `case Integer i` | Case Integer bị dominate |
| `case Object o` | `case String s` | Case String bị dominate |
| `case java.io.Serializable obj` | `case String s` | Case String bị dominate |
| `case java.util.List<?> list` | `case java.util.ArrayList<?> arrayList` | Case ArrayList bị dominate |

Một interface cha cũng có thể che một **class con**. Với `Serializable` trước `String`, Java không cần một quan hệ `extends` theo tên lớp để phát hiện dominance, bởi mọi `String` đều là `Serializable`.

## 3. Dominance có nghĩa gì về luồng chọn case?

Hãy xét:

~~~java
Object value = "Java";

String result = switch (value) {
    case CharSequence cs -> "SEQUENCE";
    case String s -> "STRING"; // Không biên dịch
    default -> "OTHER";
};
~~~

Nếu thứ tự này được cho phép, case đầu sẽ nhận `"Java"` vì `String` là một `CharSequence`. Case sau cũng mô tả một String nhưng **không bao giờ có cơ hội** xử lý giá trị như vậy.

Đặc tính quan trọng:

1. **Dominance phụ thuộc thứ tự nhãn.** Khi đảo thành `String` trước `CharSequence`, mỗi case vẫn có thể được chọn.
2. **Dominance dựa vào quan hệ kiểu và đặc tính nhãn**, không phải vào tập dữ liệu mà bạn dự đoán ở runtime. Dù hiện tại chỉ truyền `Integer` vào switch, lỗi `CharSequence` trước `String` vẫn là lỗi biên dịch.
3. **Dominance khác pattern matching.** Pattern matching xảy ra khi switch chạy; dominance xác định từ trước liệu thứ tự case có hợp lệ.
4. **Dominance áp dụng với cả switch statement và switch expression** sử dụng pattern, không chỉ khi switch tạo ra giá trị.

Hai nhãn có thể cùng applicable tại kiểu selector `Object` nhưng **không được phép** đặt theo thứ tự khiến một nhãn chi phối nhãn còn lại. Vì vậy “compiler chấp nhận `case String` riêng lẻ” không bảo đảm bạn có thể đặt case đó ở bất kỳ vị trí nào.

## 4. Chương trình Java 21: thứ tự đúng với class, interface và generic

Lưu thành tệp **`DominanceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DominanceDemo {

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";

            case String s -> "STRING:" + s;
            case CharSequence cs -> "CHARS:" + cs.length();

            case Integer n -> "INTEGER:" + n;
            case Number n -> "NUMBER:" + n;

            case ArrayList<?> items -> "ARRAYLIST:" + items.size();
            case List<?> items -> "LIST:" + items.size();

            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(new StringBuilder("xy")));
        System.out.println(describe(7));
        System.out.println(describe(2.5));
        System.out.println(describe(
                new ArrayList<>(List.of(1, 2))));
        System.out.println(describe(List.of("x")));
        System.out.println(describe(null));
        System.out.println(describe(new Object()));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên**:

~~~bash
javac DominanceDemo.java
java DominanceDemo
~~~

Đầu ra chính xác:

~~~text
STRING:Java
CHARS:2
INTEGER:7
NUMBER:2.5
ARRAYLIST:2
LIST:1
NULL
OTHER
~~~

Giải thích:

- `"Java"` là `String` và cũng là `CharSequence`. Vì case `String` đứng trước, kết quả là `STRING:Java`.
- `StringBuilder("xy")` triển khai `CharSequence` nhưng không phải `String`, nên case thứ hai nhận và cho `CHARS:2`.
- `Integer(7)` là một `Number`, nhưng case `Integer` cụ thể hơn được ưu tiên.
- `Double(2.5)` không phải Integer nhưng là Number, nên kết quả `NUMBER:2.5`.
- `new ArrayList<>(...)` vừa là `ArrayList<?>` vừa là `List<?>`. Đặt `ArrayList<?>` trước để nó được xử lý riêng.
- `List.of("x")` trả một List nhưng không phải ArrayList, nên case `List<?>` nhận.
- `null` được xử lý bằng `case null`; đối tượng `new Object()` rơi vào `default`.

Chương trình cho thấy cùng một nguyên tắc áp dụng với **class**, **interface**, **kiểu số** và **collection generic wildcard**: **hẹp trước, rộng sau** khi những case đó không guard.

## 5. Các đoạn mã cố ý không biên dịch

Các ví dụ dưới đây chỉ để xem lỗi; **không ghép vào `DominanceDemo.java`**.

### 5.1. Number trước Integer

~~~java
static String badNumber(Object value) {
    return switch (value) {
        case Number n -> "NUMBER";
        case Integer i -> "INTEGER"; // COMPILE ERROR: dominated
        default -> "OTHER";
    };
}
~~~

Mọi `Integer` đều là `Number`. Trình biên dịch không cho phép đặt case `Integer` sau case `Number` không guard. Sửa bằng cách đảo hai nhãn:

~~~java
static String goodNumber(Object value) {
    return switch (value) {
        case Integer i -> "INTEGER";
        case Number n -> "NUMBER";
        default -> "OTHER";
    };
}
~~~

Đây là các **phương thức minh họa**; đặt trong class và dùng JDK 21 khi muốn kiểm tra. Nhánh Integer không cần phải “không phải Number” để tồn tại: nó chỉ cần được xét trước.

### 5.2. Interface cũng có thể chi phối String

~~~java
static String badInterface(Object value) {
    return switch (value) {
        case java.io.Serializable ser -> "SERIALIZABLE";
        case String text -> "STRING"; // COMPILE ERROR: dominated
        default -> "OTHER";
    };
}
~~~

`String` triển khai `Serializable`; case String phía sau không thể nhận một String nào mà case Serializable phía trước đã bỏ qua. Thứ tự đúng là case String trước case Serializable (nếu bạn thật sự cần phân biệt hai loại này).

**Đừng nhầm “cha” chỉ là lớp cơ sở.** Với type patterns, các interface thích hợp cũng có thể tạo quan hệ dominance.

### 5.3. List<?> trước ArrayList<?>

~~~java
static String badList(Object value) {
    return switch (value) {
        case java.util.List<?> list -> "LIST";
        case java.util.ArrayList<?> arr -> "ARRAYLIST"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

`ArrayList<?>` luôn là `List<?>`. Khi case List đứng trước và không guard, case ArrayList bị che. Đây là ví dụ giúp nhận ra rằng **generics không làm biến mất quan hệ subtype** giữa List và ArrayList.

Một điểm khác cần lưu ý: `case List<String> l` với selector kiểu `Object` thường không hợp lệ do kiểm tra generic bị xóa (*unchecked cast*). **Applicability** của một pattern generic là vấn đề khác với **dominance** giữa hai pattern đã hợp lệ. Dùng `List<?>` trong ví dụ tổng quát vì đây là pattern phù hợp để kiểm tra sự tồn tại của List tại runtime.

## 6. Guard when có thể thay đổi dominance như thế nào?

Với Java 21, **guard** `when` chỉ cho phép chọn case khi pattern khớp **và** biểu thức guard true. Nếu guard thực sự có thể false, một case kiểu cha ở phía trước **không chắc chắn** nhận mọi giá trị kiểu con.

Ví dụ hợp lệ:

~~~java
static String classify(Object value) {
    return switch (value) {
        case CharSequence cs when cs.length() >= 4 -> "LONG";
        case String s -> "STRING";
        case CharSequence cs -> "SHORT_SEQUENCE";
        default -> "OTHER";
    };
}
~~~

Giải thích theo các giá trị:

- `"abcdef"`: khớp `CharSequence` và guard true, chọn `LONG`.
- `"abc"`: khớp `CharSequence` nhưng guard false; switch **tiếp tục xét** `case String s` và chọn `STRING`.
- `new StringBuilder("xy")`: guard false, không phải `String`, rồi khớp case `CharSequence` không guard.
- `new StringBuilder("abcdef")`: guard true ngay case đầu, chọn `LONG`.

Do guard `cs.length() >= 4` **không luôn true**, case String phía sau vẫn có thể được chọn, do đó không bị che hoàn toàn. Quy tắc không phải “cứ cha trước là luôn lỗi”, mà là **nhãn trước có thực sự chi phối nhãn sau theo điều kiện ngôn ngữ không**.

### Chương trình chạy được: kiểm chứng guard

Lưu thành **`GuardDominanceDemo.java`**:

~~~java
public class GuardDominanceDemo {

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case CharSequence cs when cs.length() >= 4
                    -> "LONG:" + cs.length();
            case String s -> "STRING:" + s;
            case CharSequence cs
                    -> "SHORT_SEQUENCE:" + cs.length();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("abc"));
        System.out.println(classify("abcdef"));
        System.out.println(classify(new StringBuilder("xy")));
        System.out.println(classify(new StringBuilder("abcdef")));
        System.out.println(classify(42));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac GuardDominanceDemo.java
java GuardDominanceDemo
~~~

Kết quả:

~~~text
STRING:abc
LONG:6
SHORT_SEQUENCE:2
LONG:6
OTHER
NULL
~~~

Điều gì xảy ra với `"abc"`? Case cha `CharSequence` đầu tiên **khớp pattern**, nhưng guard false, nên case String con còn có cơ hội được thử. Lưu ý biến `cs` của case đầu và biến `cs` của case thứ ba thuộc **hai nhãn khác nhau**; không nên coi đây là một biến mẫu chia sẻ giữa các case.

### Trường hợp đặc biệt: when true vẫn có thể gây dominance

Không phải cứ thêm chữ `when` là compiler sẽ bỏ kiểm tra dominance:

~~~java
static String badGuard(Object value) {
    return switch (value) {
        case CharSequence cs when true -> "PARENT";
        case String s -> "CHILD"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

Trong Java 21, guard hằng `true` **không loại bỏ khả năng chi phối**: case CharSequence phía trước vẫn nhận mọi String, do đó case String phía sau bị dominated.

**Quy tắc sử dụng:** dùng `when` khi thực sự có điều kiện nghiệp vụ cần kiểm tra, không phải để lách lỗi compiler. Nếu không có điều kiện thực chất, hãy đổi thứ tự case.

## 7. Type pattern Object, default và null

`Object` là kiểu rộng nhất trong hệ tham chiếu Java. Trên selector kiểu `Object`, case sau có thể bị che nếu bạn đặt `case Object o` trước:

~~~java
// CỐ Ý SAI
return switch (value) {
    case Object o -> "ANY_OBJECT";
    case String s -> "STRING"; // COMPILE ERROR: dominated
};
~~~

Nhưng có **hai điều cần phân biệt**:

1. `case Object o` là *unconditional type pattern* tại selector `Object` đối với các giá trị tham chiếu phù hợp. Nó đã bao phủ mọi **đối tượng không null**, khiến các type pattern cụ thể hơn phía sau không còn hữu ích.
2. `case Object o` **không tự khớp selector null** trong Java 21. Muốn xử lý null, viết `case null`. Khi chỉ có `case Object o` mà đầu vào là null, switch có thể ném `NullPointerException`.

Ví dụ hợp lệ:

~~~java
static String classifyAll(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "STRING";
        case Object o -> "OTHER_NON_NULL";
    };
}
~~~

Ở đây `case String` đứng trước `case Object` để không bị che; `case null` tách riêng selector null. Không cần `default`: tại selector `Object`, pattern `Object o` là unconditional đối với các giá trị còn lại.

Trong thực tế, compiler còn có thể từ chối **sự kết hợp** `case Object o` và `default` trong cùng switch vì có cả một unconditional pattern lẫn nhãn default. Vì vậy, nếu muốn bao phủ “mọi kiểu còn lại”, hãy chọn cấu trúc nhãn phù hợp thay vì tự động thêm default sau `case Object`.

Đừng suy luận rằng “`Object` là cha của mọi reference type nên `case Object` xử lý null” — **null không phải một đối tượng `Object`**.

## 8. Dominance và interface: không phải lúc nào cũng có thứ tự toàn phần

Hai kiểu có thể **giao nhau** mà không cái nào là subtype của cái kia. Ví dụ, `CharSequence` và `Serializable` đều có thể áp dụng cho `String`, nhưng không phải mọi CharSequence đều Serializable và cũng không phải mọi Serializable đều CharSequence.

Giả sử hai nhãn:

~~~java
return switch (value) {
    case CharSequence cs -> "CHAR_SEQUENCE";
    case java.io.Serializable ser -> "SERIALIZABLE";
    default -> "OTHER";
};
~~~

Với selector `Object`, thứ tự này có thể hợp lệ: case thứ hai vẫn có cơ hội nhận những đối tượng Serializable nhưng **không** phải CharSequence. Với một `String`, hai điều kiện kiểu đều đúng, nên case **đầu** sẽ được chọn.

Ngược lại, nếu case Serializable ở trước rồi ngay sau là `case String s`, thì String **bị dominate**, vì **mọi String** đều Serializable. Khác biệt then chốt là **quan hệ bao hàm toàn bộ tập giá trị của pattern sau**, chứ không chỉ có một vài đối tượng chung giữa hai kiểu.

Vì vậy, đừng áp dụng “sắp xếp mọi interface theo alphabet” hoặc “interface luôn trước class”. Phải xét quan hệ kiểu thực tế và mục đích phân loại.

## 9. Sealed hierarchy: exhaustiveness không miễn kiểm tra dominance

Trong Java 17+, `sealed interface` cho phép giới hạn các kiểu con trực tiếp. Trong Java 21, switch expression có thể dùng các type patterns của từng kiểu con để bao phủ hierarchy.

Ví dụ tự chứa **Java 21**, lưu thành `SealedDominanceDemo.java`:

~~~java
public class SealedDominanceDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c -> "CIRCLE:" + c.radius();
            case Rectangle r -> "RECT:"
                    + (r.width() * r.height());
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(3)));
        System.out.println(describe(new Rectangle(2, 4)));
    }
}
~~~

~~~bash
javac SealedDominanceDemo.java
java SealedDominanceDemo
~~~

Kết quả:

~~~text
CIRCLE:3
RECT:8
~~~

`Circle` và `Rectangle` là hai kiểu con được khai báo trong danh sách `permits`. Hai nhãn trên có thể tạo thành một **switch expression exhaustive** (cho các giá trị thuộc hierarchy hợp lệ), không cần `default`.

Nhưng viết kiểu cha trước vẫn sai:

~~~java
static String badShape(Shape shape) {
    return switch (shape) {
        case Shape s -> "SHAPE";
        case Circle c -> "CIRCLE"; // COMPILE ERROR: dominated
    };
}
~~~

Đây là **mảnh mã cố ý lỗi** trong ngữ cảnh có `Shape`, `Circle` đã khai báo. Case `Shape` bao phủ mọi Circle, nên `case Circle` phía sau bị che.

**Hai phép kiểm tra khác nhau:**

- **Dominance:** có nhãn sau nào không thể được chọn vì nhãn trước đã bao phủ nó không?
- **Exhaustiveness:** toàn bộ switch expression có bao phủ mọi giá trị selector cần xử lý không?

Một switch **exhaustive** vẫn có thể bị từ chối vì dominance; một switch không bị dominance vẫn có thể thiếu case và không exhaustive.

Ngoài ra, nếu `shape == null` và không có `case null`, switch trên tham chiếu vẫn có thể ném `NullPointerException`. “Exhaustive đối với các subtype” không có nghĩa là mặc nhiên xử lý null.

## 10. Type pattern cha-con khác với biến thể điều kiện instanceof độc lập

Nhiều người thấy điều kiện này hợp lệ:

~~~java
Object value = "Java";

if (value instanceof CharSequence cs) {
    System.out.println("A");
}
if (value instanceof String s) {
    System.out.println("B");
}
~~~

Hai câu lệnh `if` **độc lập**, nên cả hai có thể chạy đối với String. Đây không phải switch với hai nhãn loại trừ lẫn nhau; Java không áp đặt cùng một quy tắc dominance lên những lệnh `if` độc lập.

Ngay cả một chuỗi `if / else if` có điều kiện rộng trước cũng có thể biên dịch:

~~~java
if (value instanceof CharSequence cs) {
    System.out.println("sequence");
} else if (value instanceof String s) {
    System.out.println("string");
}
~~~

Nhánh `else if` phía sau sẽ không được thực thi khi value là String trong luồng ví dụ này, nhưng đây là **phân tích logic chương trình**, không phải cùng cơ chế compile-time rejection như pattern `case` của switch.

Chính vì switch pattern được thiết kế để chọn **một nhãn case áp dụng**, compiler có quy tắc dominance riêng giúp phát hiện các nhãn bị che một cách tường minh.

## 11. Dominance không phải applicability, matching hoặc lỗi null

Trước khi sửa một lỗi biên dịch, cần xác định đúng loại lỗi.

| Kiểm tra | Hỏi điều gì? | Ví dụ |
| --- | --- | --- |
| **Applicability** | Pattern có hợp lệ với **kiểu tĩnh** của selector không? | Selector `String` nhưng `case Integer n`: không tương thích kiểu |
| **Dominance** | Một case trước có chi phối case sau không? | Selector `Object`, `case Number` trước `case Integer` |
| **Exhaustiveness** | Switch expression có đủ case để tạo giá trị cho mọi đầu vào phù hợp không? | Switch trên `int` chỉ có `case 1`, thiếu `default` |
| **Runtime matching** | Đối tượng thực tế có khớp pattern và guard không? | `"Java"` khớp `case String s` |
| **Null handling** | Selector null có nhãn xử lý phù hợp không? | `case null` tách riêng null |

Khi compiler báo “**this case label is dominated by a preceding case label**”, việc thêm một guard tùy tiện, cast selector sang kiểu khác hoặc xóa default không nhất thiết sửa được vấn đề. Cần xem nhãn nào phía trước đã bao phủ mọi giá trị mà nhãn lỗi muốn bắt.

Một phương pháp debug nhanh:

1. Xác định kiểu tĩnh của selector để loại lỗi applicability.
2. Liệt kê các case theo đúng **thứ tự**.
3. Với case bị báo lỗi, hỏi: “mọi giá trị khớp nhãn này có chắc chắn đã khớp một nhãn **trước** hay không?”
4. Nếu có, chuyển case cụ thể hơn lên trước hoặc thiết kế lại guard để các nhánh có ý nghĩa khác nhau.
5. Sau khi sửa dominance, kiểm tra lại exhaustiveness và null handling.
6. Chỉ sau khi biên dịch thành công mới xét dữ liệu runtime, thứ tự chọn case và kết quả mong muốn.

## 12. Những lỗi phổ biến trong thực tế

| Sai lầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Đặt `case Object` đầu tiên | Bao phủ mọi object không null | Đặt các case cụ thể trước; Object ở cuối nếu cần |
| Đặt `case Number` trước `case Integer` | Integer luôn là Number | Đảo thứ tự |
| Đặt `case CharSequence` trước `case String` | String triển khai CharSequence | Đảo thứ tự hoặc dùng guard thực sự cần thiết |
| Đặt `case Serializable` trước `case String` | String triển khai Serializable | Ưu tiên String trước Serializable |
| Đặt `case List<?>` trước `case ArrayList<?>` | ArrayList luôn là List | Ưu tiên ArrayList trước List |
| Dùng `when true` để né dominance | Guard luôn đúng, vẫn chi phối case con | Không dùng guard giả; đổi thứ tự |
| Tin rằng kiểu cha chỉ là một class `extends` trực tiếp | Interface cũng có thể tạo dominance | Kiểm tra toàn bộ quan hệ kiểu |
| Tưởng hai pattern có một vài instance chung là dominance | Cần quan hệ bao phủ, không chỉ giao nhau | Xét liệu case sau **còn giá trị nào được chọn** hay không |
| Tưởng một sealed switch exhaustive không thể bị dominance | Exhaustiveness và dominance độc lập | Sắp case con đúng trước cha |
| Tưởng `case Object` bắt cả null | Null không là Object instance | Dùng `case null` |
| Dùng `default` sau unconditional `case Object` | Có thể vi phạm quy tắc nhãn switch | Dùng một cấu trúc bao phủ hợp lệ |
| Bị dominance nhưng sửa thành `if` mà không xem logic | Có thể giữ nhánh không bao giờ đạt tới | Thiết kế lại thứ tự phân loại |

### Checklist khi code review switch patterns

- Có nhãn kiểu cha/interface rộng **đứng trước** nhãn kiểu con không?
- Mỗi case rộng có guard thực sự giới hạn tập giá trị, hay chỉ có `when true`?
- Các nhãn cùng kiểu nhưng có `when` đã đặt nhánh có điều kiện cụ thể trước nhánh tổng quát chưa?
- Generic wildcard/collection hierarchy có bị nhầm thứ tự List/ArrayList/Collection không?
- Có cần `case null` riêng không?
- Switch expression đã exhaustive chưa?
- Các nhánh thực sự biểu thị những tình huống nghiệp vụ khác nhau hay chỉ trùng lặp?

## 13. Bài tập tự kiểm tra

**Bài 1 — Dự đoán lỗi.** Cho selector kiểu `Object`:

~~~java
return switch (value) {
    case Number n -> "N";
    case Double d -> "D";
    default -> "O";
};
~~~

**Đáp án:** Không biên dịch. `Double` là `Number`; case Double sau bị dominate. Sửa bằng `case Double d` đứng trước `case Number n`.

**Bài 2 — Interface và class.**

~~~java
return switch (value) {
    case java.io.Serializable s -> "SER";
    case String text -> "TEXT";
    default -> "OTHER";
};
~~~

**Đáp án:** Case String bị dominate vì mọi String đều Serializable. Đưa case String lên trước.

**Bài 3 — Guard có cứu được case con?**

~~~java
return switch (value) {
    case CharSequence cs when cs.length() > 5 -> "LONG";
    case String s -> "STRING";
    case CharSequence cs -> "OTHER_SEQ";
    default -> "OTHER";
};
~~~

**Đáp án:** Hợp lệ với selector kiểu `Object` trong Java 21. Guard đầu có thể false đối với String ngắn, nên case String phía sau vẫn có giá trị có thể nhận. Nhánh CharSequence không guard cuối nhận các CharSequence còn lại mà chưa được xử lý.

**Bài 4 — `when true` có tác dụng gì?**

~~~java
return switch (value) {
    case CharSequence cs when true -> "SEQ";
    case String s -> "STR";
    default -> "OTHER";
};
~~~

**Đáp án:** Vẫn lỗi dominated case label. Guard hằng true không khiến case String nhận được giá trị nào khác.

**Bài 5 — Object và null.** Với selector kiểu `Object`, cấu trúc:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s -> "STRING";
    case Object o -> "OBJECT";
};
~~~

**Đáp án:** Hợp lệ, bao phủ null, String và tất cả object không null còn lại. Không cần `default`. Nếu hoán đổi case Object lên trước String thì String bị dominate.

**Bài 6 — Phân biệt hai loại lỗi.** `switch` gồm `case String` rồi `case CharSequence` nhưng không có default khi selector kiểu `Object`.

**Đáp án:** Thứ tự hai case này **không gây dominance**, vì nhãn String hẹp đứng trước nhãn CharSequence rộng. Tuy nhiên switch expression **chưa exhaustive** cho mọi Object khác như Integer; cần case/default bao phủ phần còn lại.

## 14. Tài liệu chính thức

Các quy tắc trong bài sử dụng Java Language Specification của **Java SE 21**:

- [JLS 21 — mục 14.11.1, Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): quy định case labels, dominance và yêu cầu liên quan tới switch.
- [JLS 21 — mục 14.30.3, Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): đặc tính của pattern, bao gồm applicability và dominance.
- [JLS 21 — mục 15.28, Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression và exhaustiveness.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): pattern labels, `when` guards, dominance và null case.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng được hoàn thiện trong Java 21.

**Ghi nhớ:** Một **type pattern cha** không guard có thể **dominate** type pattern con đứng phía sau vì nó đã nhận mọi đối tượng thuộc kiểu con. Hãy đặt **case con trước case cha**; nếu dùng `when`, bảo đảm guard có điều kiện thực sự và được đặt đúng thứ tự. Kiểm tra dominance riêng với applicability, exhaustiveness và xử lý null.
