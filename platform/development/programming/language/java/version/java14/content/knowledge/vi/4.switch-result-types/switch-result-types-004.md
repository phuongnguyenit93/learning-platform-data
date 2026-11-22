# Boxing, unboxing và kết quả tham chiếu của `switch expression`

## Mục tiêu

Khi một `switch` được dùng như **biểu thức trả về giá trị**, Java phải xác định **kiểu của toàn bộ biểu thức** và chuyển đổi kết quả của nhánh được chọn sang kiểu đó. Nếu các nhánh dùng `int`, `Integer`, `double`, `Double`, `String` hay `null`, kết quả có thể chịu ảnh hưởng của **boxing**, **unboxing**, **numeric promotion** và **target typing**.

Sau bài này, bạn có thể:

- Phân biệt **kiểu của selector** (`switch (x)`) với **kiểu kết quả** (`switch (x) { ... }`).
- Giải thích khi nào giá trị nguyên thủy được **boxing** thành wrapper và khi nào wrapper được **unboxing** về primitive.
- Hiểu sự khác nhau giữa **poly switch expression** (có kiểu đích khi gán/truyền tham số) và **standalone switch expression** (Java suy ra kiểu từ các nhánh).
- Xác định tác động của kết quả `null` đến các kiểu tham chiếu và nguy cơ `NullPointerException` khi unboxing.
- Thiết kế API trả `Integer`, `Number`, `Object` hoặc kiểu domain cụ thể mà không tạo chuyển đổi khó hiểu.
- Chạy ví dụ Java 17+ và kiểm tra chính xác kết quả.

**Phạm vi phiên bản:** `switch expression` là tính năng **chính thức từ Java 14** ([JEP 361](https://openjdk.org/jeps/361)). Các quy tắc typing, boxing, unboxing và kết quả tham chiếu trình bày dưới đây vẫn thuộc Java hiện đại. Mã chạy dùng cú pháp chuẩn trên **JDK 17 trở lên**, không cần `--enable-preview`.

## 1. Kiểu selector và kiểu kết quả là hai vấn đề khác nhau

Trong biểu thức:

~~~java
String label = switch (code) {
    case 1 -> "Mới";
    case 2 -> "Đang xử lý";
    default -> "Khác";
};
~~~

- `code` là **selector**: giá trị dùng để chọn nhánh.
- `"Mới"`, `"Đang xử lý"` và `"Khác"` là các **result expressions**.
- `String label` chỉ rõ **kiểu đích** của biểu thức `switch` khi gán.
- Toàn bộ `switch (...) { ... }` sinh **một giá trị**; việc chọn nhánh không nhất thiết làm kiểu kết quả giống kiểu selector.

Ví dụ, selector kiểu `int` vẫn có thể dẫn đến kết quả kiểu `double`, `Integer`, `String` hoặc `Object`. Đừng suy ra kiểu kết quả chỉ từ `switch (code)`.

Một nhánh dùng khối `{ ... }` thì biểu thức nằm trong câu lệnh `yield` chính là **result expression** của nhánh đó:

~~~java
Number quantity = switch (code) {
    case 1 -> 10;                   // result expression: 10
    default -> {
        double value = 2.5;
        yield value;                 // result expression: value
    }
};
~~~

Đoạn trên là **mã minh họa** trong một phương thức, giả sử `code` kiểu `int`. Kiểu đích `Number` cho phép `10` được boxing thành `Integer` và `value` được boxing thành `Double`, sau đó cả hai có thể được tham chiếu qua `Number`.

## 2. Boxing và unboxing trong kết quả `switch`

### 2.1. Boxing: primitive → wrapper

**Boxing** chuyển một giá trị nguyên thủy sang wrapper tương ứng, chẳng hạn:

| Primitive | Wrapper |
|---|---|
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Ví dụ, khi kiểu đích là `Integer`, kết quả `int` trong nhánh có thể được boxing tự động:

~~~java
// Mã minh họa trong phương thức; code có kiểu int.
Integer count = switch (code) {
    case 0 -> 10;                    // int -> Integer
    case 1 -> Integer.valueOf(20);   // đã là Integer
    default -> null;                 // hợp lệ với kiểu tham chiếu Integer
};
~~~

Ở đây `count` là **tham chiếu kiểu `Integer`**, có thể giữ giá trị wrapper hoặc `null`. Việc có thể trả `null` là thuộc tính của **kiểu tham chiếu**, không phải tính năng đặc biệt của `switch`.

Wrapper là đối tượng bất biến, nhưng **boxing không bảo đảm tạo một đối tượng mới cho mỗi lần chuyển đổi**. Không dùng `==` để suy ra hai wrapper có giá trị số bằng nhau; khi so sánh giá trị, ưu tiên `equals`/`Objects.equals` hoặc unbox sau khi chắc chắn khác `null`.

### 2.2. Unboxing: wrapper → primitive

**Unboxing** lấy giá trị primitive từ wrapper:

~~~java
// Mã minh họa: code có kiểu int.
int count = switch (code) {
    case 0 -> Integer.valueOf(10);   // Integer -> int
    default -> 20;                   // đã là int
};
~~~

Ở đây biến `count` yêu cầu `int`, nên nhánh `Integer.valueOf(10)` phải chuyển về `int`.

**Nguy cơ cốt lõi:** Nếu kết quả wrapper được unbox đang là `null`, Java ném `NullPointerException`.

~~~java
// Mã minh họa: chạy vào default sẽ ném NullPointerException.
int count = switch (code) {
    case 0 -> 10;
    default -> (Integer) null;       // null Integer phải unbox thành int
};
~~~

`(Integer) null` là một biểu thức có kiểu `Integer` nhưng mang giá trị `null`. Nó **khác** với nhánh `default -> null` khi kiểu đích là `int`: bản thân `null` không tương thích với `int`, nên trường hợp sau là **lỗi biên dịch**, không phải một cách hợp lệ để trả số nguyên.

### 2.3. Phân biệt biến primitive và reference sau `switch`

~~~java
// Mã minh họa: k có kiểu int.
Integer optional = switch (k) {
    case 0 -> null;
    default -> 100;
};

int required = switch (k) {
    case 0 -> Integer.valueOf(100);
    default -> 200;
};
~~~

- `optional` là `Integer`, nên nhánh `null` hợp lệ; nhánh `100` được boxing.
- `required` là `int`, nên nhánh `Integer.valueOf(100)` được unboxing.
- Việc chọn `Integer` hay `int` là **hợp đồng dữ liệu**: `Integer` biểu đạt khả năng thiếu giá trị (`null`) nhưng đòi hỏi kiểm soát unboxing; `int` luôn chứa một số nguyên sau khi biểu thức hoàn tất bình thường.

**Khuyến nghị:** Nếu `null` có ý nghĩa nghiệp vụ, đặt tên rõ ràng và kiểm tra trước khi tính toán. Nếu không cho phép thiếu dữ liệu, ưu tiên kết quả primitive hoặc ném ngoại lệ có thông điệp rõ thay vì âm thầm dùng `null`.

## 3. Poly expression và standalone expression quyết định cách suy kiểu

Đây là phần quan trọng nhất khi nhánh `switch` có nhiều kiểu kết quả.

### 3.1. Poly `switch expression`: kiểu đích truyền xuống các nhánh

Theo Java Language Specification, `switch expression` là **poly expression** khi xuất hiện trong **ngữ cảnh gán** (assignment context) hoặc **ngữ cảnh truyền tham số** (invocation context). Các result expressions phải tương thích với **cùng kiểu đích `T`**; kiểu của toàn bộ poly `switch` chính là `T`.

Ví dụ có kiểu đích tường minh:

~~~java
// Mã minh họa: k có kiểu int.
Number value = switch (k) {
    case 0 -> 10;                    // boxing int -> Integer -> Number
    case 1 -> 2.5d;                  // boxing double -> Double -> Number
    default -> Long.valueOf(99);    // Long là một Number
};
~~~

Với `Number` làm kiểu đích, mỗi nhánh được kiểm tra khả năng gán vào `Number`. Kết quả thực tế của nhánh `case 0` thường là một `Integer`, nhánh `case 1` là một `Double`, nhưng biến `value` có **kiểu tĩnh `Number`**.

Tương tự:

~~~java
Object payload = switch (k) {
    case 0 -> 42;                    // boxing thành Integer
    case 1 -> "ready";               // String là Object
    default -> null;                 // null hợp lệ với Object
};
~~~

Kết quả có **kiểu tĩnh `Object`**; khi chạy, đối tượng tham chiếu thực tế phụ thuộc nhánh. Ví dụ `case 0` dẫn tới một `Integer`. Nếu cần dùng phương thức riêng của `Integer`, phải kiểm tra/ép kiểu phù hợp; không thể gọi phương thức chỉ có ở `Integer` trực tiếp trên biến `Object`.

### 3.2. Standalone `switch expression`: kiểu được suy ra từ các nhánh

Nếu không có ngữ cảnh gán hoặc truyền tham số cung cấp kiểu đích cho chính `switch`, nó là **standalone expression**. Trường hợp dễ thấy là dùng `var`:

~~~java
// Mã minh họa: k có kiểu int.
var amount = switch (k) {
    case 0 -> 5;     // int
    default -> 8L;   // long
};
~~~

Ở đây kết quả có kiểu **`long`** theo quy tắc **numeric promotion**; `var` suy ra `long`, chứ không thể tùy chọn giữa `int` và `long` ở thời điểm chạy.

Quy tắc kiểu standalone `switch`, theo thứ tự:

1. **Tất cả nhánh cùng kiểu:** kiểu của `switch` là kiểu chung đó.
2. **Các nhánh chỉ gồm `boolean`/`Boolean` nhưng không cùng kiểu:** wrapper `Boolean` được unbox, và `switch` có kiểu `boolean`.
3. **Các nhánh đều có kiểu chuyển đổi được sang số:** áp dụng **general numeric promotion** (có thể unbox wrapper), chẳng hạn `int` và `long` dẫn đến `long`.
4. **Các trường hợp còn lại:** boxing những kết quả primitive, rồi tìm **least upper bound (LUB)** của các kiểu tham chiếu và áp dụng capture conversion theo quy tắc ngôn ngữ.

Điểm thứ tư cho phép các nhánh tạo những đối tượng khác lớp cùng xuất hiện trong một `switch`. **Đừng mặc định rằng `var` với các nhánh khác kiểu luôn suy ra `Object`**: LUB có thể là một kiểu chung hoặc kiểu giao phức tạp. Khi hợp đồng mong muốn là `Number`, `Object` hoặc một interface, khai báo kiểu đích đó tường minh thường giúp mã dễ đọc hơn.

> **Lưu ý về `return switch (...)`:** Ngữ cảnh `return` không phải một trong hai ngữ cảnh làm `switch` trở thành poly expression theo quy tắc ở trên. Java xác định kiểu standalone của `switch` trước, rồi kiểm tra việc trả về có tương thích kiểu khai báo của phương thức hay không. Để tác động rõ tới cách typing của từng nhánh, dùng biến có kiểu đích tường minh hoặc đưa biểu thức vào ngữ cảnh gán thích hợp.

### 3.3. Khi nào numeric promotion sẽ tự unbox?

~~~java
// Mã minh họa: k có kiểu int.
var amount = switch (k) {
    case 0 -> Integer.valueOf(5);  // Integer
    default -> 8L;                 // long
};
~~~

Cả `Integer` và `long` là các kiểu kết quả có thể dùng trong ngữ cảnh số, nên `switch` standalone áp dụng **numeric promotion**. `Integer` được **unbox thành `int`** và mở rộng sang `long`; `amount` có kiểu `long`.

Vì có unboxing ở đường tính kiểu số, nhánh `Integer` mang giá trị `null` có thể gây `NullPointerException` ngay khi chọn nhánh, **dù lập trình viên không viết `.intValue()` một cách tường minh**.

### 3.4. Kiểu Boolean cũng có chuyển đổi đáng chú ý

~~~java
// Mã minh họa: k có kiểu int.
var enabled = switch (k) {
    case 0 -> Boolean.TRUE;  // Boolean
    default -> false;        // boolean
};
~~~

Đây là standalone `switch` với nhánh `Boolean` và `boolean`; kiểu kết quả là **`boolean`**, nên nhánh `Boolean` được unbox. Nếu nhánh wrapper trả `null`, việc unbox sẽ ném `NullPointerException`.

Đừng suy ra “hễ thấy Boolean là luôn unbox”: nếu **mọi nhánh đều có cùng kiểu `Boolean`**, trường hợp cùng kiểu được xét trước, và `switch` standalone có kiểu `Boolean`. Kết quả `null` có thể được giữ nguyên cho tới khi nơi sử dụng yêu cầu primitive.

## 4. Kết quả tham chiếu và `null`: lỗi hay hợp lệ phụ thuộc ngữ cảnh

### 4.1. `null` là một kết quả tham chiếu hợp lệ

~~~java
// Mã minh họa: status là int.
String description = switch (status) {
    case 1 -> "Đang xử lý";
    case 2 -> "Hoàn tất";
    default -> null;
};
~~~

`null` trong một **nhánh kết quả** hợp lệ khi kiểu đích là tham chiếu `String`. Tuy nhiên, việc dùng `description.length()` khi nhánh `default` được chọn sẽ ném `NullPointerException`. Bài toán nghiệp vụ có thể chọn giá trị như `"Không xác định"` hoặc dùng `Optional<String>` nếu muốn biểu đạt trường hợp không có dữ liệu; đó là quyết định thiết kế API, không phải yêu cầu của cú pháp `switch`.

### 4.2. Cùng các nhánh, khác ngữ cảnh có thể khác kết quả

Đây là ví dụ đặc biệt quan trọng:

~~~java
// Mã minh họa: k có kiểu int và missing là Integer có giá trị null.
Integer missing = null;

Number referenceResult = switch (k) {
    case 0 -> missing;   // giữ kiểu tham chiếu Integer khi đích là Number
    default -> 2.5d;     // boxing double -> Double -> Number
};

var numericResult = switch (k) {
    case 0 -> missing;   // phải unbox nếu nhánh này được chọn
    default -> 2.5d;     // double
};
~~~

Ở biểu thức thứ nhất, **`Number` là kiểu đích**. Nhánh `missing` có kiểu tham chiếu `Integer` tương thích với `Number`; nếu `k == 0` thì `referenceResult` nhận `null` **mà không bị unbox**.

Ở biểu thức thứ hai, `var` khiến Java tự suy kiểu của `switch` standalone. Hai nhánh có kiểu `Integer` và `double`, nên áp dụng numeric promotion và kết quả có kiểu **`double`**. Nếu `k == 0`, Java unbox `missing == null` và ném **`NullPointerException`**.

Nói cách khác, **khác biệt không nằm ở nhãn `case`**, mà ở **kiểu đích và quy tắc chuyển đổi kết quả**.

### 4.3. Đừng nhầm `null` ở selector với `null` ở result

- **Selector `null`:** Java 17 `switch (nullableReference)` với giá trị selector `null` ném `NullPointerException`; nhánh `default` không tự giải quyết `null` selector.
- **Result `null`:** một nhánh như `default -> null` có thể hợp lệ nếu kiểu đích chấp nhận tham chiếu null.
- **Unboxing result `null`:** nếu kết quả cần primitive, hoặc standalone numeric/Boolean promotion yêu cầu unboxing, `null` lại gây `NullPointerException`.

Pattern matching cho `switch` đã trở thành tính năng chuẩn ở Java 21 và có thể xử lý `case null` cho selector trong ngữ cảnh hỗ trợ. **Không mang cú pháp `case null` của Java 21 vào ví dụ cần biên dịch ở Java 17.** Bài học hiện tại tập trung vào quy tắc kết quả vốn đã chuẩn từ Java 14.

## 5. Ví dụ Java 17+ chạy hoàn chỉnh

Lưu mã sau vào **`SwitchResultTypes.java`**:

~~~java
public final class SwitchResultTypes {

    enum Mode {
        PRIMITIVE, BOXED, ABSENT
    }

    // Kiểu đích Integer: boxing int, giữ Integer và cho phép null.
    static Integer optionalCount(Mode mode) {
        Integer result = switch (mode) {
            case PRIMITIVE -> 12;
            case BOXED -> Integer.valueOf(24);
            case ABSENT -> null;
        };
        return result;
    }

    // Kiểu đích int: unboxing Integer.
    static int requiredCount(int code) {
        int value = switch (code) {
            case 1 -> Integer.valueOf(7);
            default -> 9;
        };
        return value;
    }

    // Kiểu đích Number: mỗi nhánh trả một subtype phù hợp.
    static Number magnitude(int code) {
        Number result = switch (code) {
            case 0 -> 7;
            case 1 -> 2.5d;
            default -> Long.valueOf(99);
        };
        return result;
    }

    // Kiểu đích Object: boxing và tham chiếu cùng tồn tại.
    static Object mixedResult(int code) {
        Object result = switch (code) {
            case 0 -> 100;
            case 1 -> "ready";
            default -> null;
        };
        return result;
    }

    // var: standalone numeric promotion (Integer + long -> long).
    static long promotedAmount(int code) {
        var value = switch (code) {
            case 0 -> Integer.valueOf(5);
            default -> 8L;
        };
        return value;
    }

    public static void main(String[] args) {
        System.out.println("nullable=" + (optionalCount(Mode.ABSENT) == null));
        System.out.println("boxed=" + optionalCount(Mode.PRIMITIVE));
        System.out.println("unboxed=" + requiredCount(1));

        Number number = magnitude(1);
        System.out.println(
                "number=" + number + ", type=" + number.getClass().getSimpleName());

        Object item = mixedResult(0);
        System.out.println("objectType=" + item.getClass().getSimpleName());
        System.out.println("promoted=" + promotedAmount(0));

        Integer missing = null;

        // Poly switch: kiểu đích Number cho phép giữ null reference.
        Number retained = switch (0) {
            case 0 -> missing;
            default -> 2.5d;
        };
        System.out.println("referenceNull=" + (retained == null));

        // Standalone switch: Integer + double -> double, phải unbox.
        try {
            var promoted = switch (0) {
                case 0 -> missing;
                default -> 2.5d;
            };
            System.out.println("unexpected=" + promoted);
        } catch (NullPointerException ex) {
            System.out.println("standaloneNull=NullPointerException");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 SwitchResultTypes.java
java SwitchResultTypes
~~~

**Đầu ra chính xác:**

~~~text
nullable=true
boxed=12
unboxed=7
number=2.5, type=Double
objectType=Integer
promoted=5
referenceNull=true
standaloneNull=NullPointerException
~~~

Giải thích theo thứ tự:

1. `Mode.ABSENT` chọn `null`; `optionalCount` trả `Integer` nên có thể mang `null`.
2. `Mode.PRIMITIVE` trả `12` từ nhánh kiểu `int`, được boxing khi gán vào `Integer`.
3. `requiredCount(1)` nhận `Integer.valueOf(7)`, unbox sang `int`.
4. `magnitude(1)` trả `2.5d`, boxing thành `Double`; biến khai báo kiểu `Number` vẫn tham chiếu đối tượng `Double`.
5. `mixedResult(0)` boxing `100` thành `Integer`, có thể gán cho biến `Object`.
6. `promotedAmount(0)` suy ra `long` cho `Integer` và `long`; giá trị in ra là `5`.
7. `retained` giữ `null` dưới kiểu đích `Number`.
8. `promoted` trong `try` bị numeric promotion sang `double`; nhánh `Integer missing == null` phải unbox, gây `NullPointerException` và vào `catch`.

Chương trình không phụ thuộc vào trạng thái preview hay hành vi riêng của một JDK cũ. Các hành vi mà nó minh họa nằm trong đặc tả ngôn ngữ hiện hành.

## 6. Những trường hợp dễ nhầm và cách sửa

### 6.1. Primitive không tự “biến thành mọi wrapper khác”

~~~java
// HỢP LỆ: đích Number có thể nhận Integer qua boxing rồi widening reference.
Number n = switch (k) {
    case 0 -> 1;        // int -> Integer -> Number
    default -> 2L;      // long -> Long -> Number
};
~~~

Đoạn là mã minh họa, giả định `k` có kiểu `int`.

Đừng suy diễn rằng Java sẽ tự ghép bất kỳ chuỗi chuyển đổi nào. Ví dụ, **`Long boxed = 1;` không hợp lệ**: trình biên dịch không tự thực hiện “widening `int` → `long`, rồi boxing thành `Long`” trong ngữ cảnh gán này. Nếu muốn `Long`, dùng `1L` hoặc `Long.valueOf(1L)`. Khi thiết kế nhánh `switch` đích `Long`, các giá trị từng nhánh cũng phải tương thích với kiểu đích `Long`.

### 6.2. `var` không có nghĩa là “giữ nguyên kiểu của từng nhánh”

~~~java
var number = switch (k) {
    case 0 -> 1;       // int
    default -> 2.5d;   // double
};
~~~

Kiểu tĩnh của `number` là **`double`**, do numeric promotion, không phải kiểu thay đổi động theo nhánh. Khi cần giữ các wrapper khác nhau, khai báo **`Number`** hoặc một interface phù hợp làm kiểu đích.

### 6.3. Có thể trả `null` ở kết quả tham chiếu nhưng không thể coi `null` là số

~~~java
Integer a = switch (k) {
    case 0 -> null;
    default -> 10;
};

// Không hợp lệ nếu viết int b với case 0 -> null:
// int b = switch (k) { case 0 -> null; default -> 10; };
~~~

Biến `a` có kiểu tham chiếu, được phép mang `null`. Nếu đổi thành kiểu primitive `int` mà vẫn có nhánh trả `null` trực tiếp, chương trình không biên dịch. Dùng `(Integer) null` để làm biểu thức hợp kiểu wrapper **không giải quyết lỗi logic**: khi unboxing sang `int`, nó sẽ ném `NullPointerException` ở runtime.

### 6.4. Không nên dựa vào kiểu được suy ra quá phức tạp

Nếu các nhánh trả về các lớp tham chiếu khác nhau:

~~~java
// Đoạn minh họa: k kiểu int.
Object result = switch (k) {
    case 0 -> "text";
    case 1 -> 12;       // boxing thành Integer
    default -> null;
};
~~~

Khai báo `Object` làm hợp đồng rõ ràng. Nếu thay bằng `var`, trình biên dịch sẽ suy kiểu theo quy tắc standalone và **least upper bound**, không nhất thiết đơn giản là `Object`. Tốt hơn nữa, nếu kết quả có một ý nghĩa nghiệp vụ thống nhất, thiết kế một kiểu/interface cụ thể thay vì dựa vào `Object` và ép kiểu ở mọi nơi sử dụng.

### 6.5. Wrapper làm thay đổi hành vi khi dùng kết quả về sau

~~~java
// Đoạn minh họa: optional có kiểu Integer.
Integer optional = null;

// Hợp lệ, so sánh tham chiếu với null.
boolean missing = (optional == null);

// Có thể NPE vì phép cộng cần unbox Integer.
// int total = optional + 1;
~~~

Khi `Integer`/`Boolean` được trả từ `switch`, không chỉ riêng dòng `switch` mới có khả năng unbox. Các phép toán số học, logic, điều kiện hoặc lời gọi cần primitive sau đó cũng có thể gây unboxing. Hãy kiểm tra `null` ở **ranh giới API**, đừng để ngoại lệ xuất hiện xa nơi tạo dữ liệu.

## 7. Cách chọn kiểu kết quả của `switch`

| Nhu cầu nghiệp vụ | Kiểu đích đề xuất | Tác động chuyển đổi cần chú ý |
|---|---|---|
| Luôn có số nguyên hợp lệ | `int` | Wrapper ở nhánh sẽ unbox; wrapper null gây NPE. |
| Có thể thiếu số nguyên | `Integer` | Primitive ở nhánh sẽ boxing; kiểm tra null khi dùng. |
| Cùng một nghĩa số nhưng mỗi nhánh có kiểu wrapper khác nhau | `Number` | Primitive được boxing; giữ kiểu runtime `Integer`/`Double`/`Long` tùy nhánh. |
| Chỉ muốn một nhãn văn bản | `String` | Mọi nhánh nên trả `String` hoặc null có chủ đích; tránh ép các kiểu không liên quan. |
| Các nhánh trả cùng một interface/domain type | Interface hoặc kiểu domain cụ thể | Thể hiện hợp đồng nghiệp vụ rõ hơn `Object`. |
| Kết quả không đồng nhất vì lý do kỹ thuật | `Object` (có cân nhắc) | Có thể cần kiểm tra kiểu tại nơi dùng; dễ làm API khó bảo trì. |
| Muốn Java tự suy ra kiểu trong một khai báo cục bộ | `var` | Kiểm tra numeric/Boolean promotion, LUB và null unboxing trước khi dùng. |

**Nguyên tắc:** Hãy quyết định ý nghĩa và kiểu kết quả **trước** khi viết từng nhánh. Nếu nhiều nhánh trả các loại dữ liệu không liên quan, có thể phép phân loại đang cần một cấu trúc dữ liệu kết quả rõ ràng hơn (ví dụ một `record` hoặc interface chung) thay vì một `Object`.

## 8. Bài tự kiểm tra

**Câu 1.** Kết quả của đoạn sau có kiểu tĩnh nào?

~~~java
// Mã minh họa: k là int.
var x = switch (k) {
    case 0 -> Integer.valueOf(4);
    default -> 6L;
};
~~~

**Đáp án:** `long`; `Integer` được unbox rồi áp dụng numeric promotion với `long`. Nếu nhánh `Integer` thực tế là null, có nguy cơ NPE.

**Câu 2.** Đoạn sau có hợp lệ không, và `x` có thể là null không?

~~~java
// Mã minh họa: k là int.
Number x = switch (k) {
    case 0 -> 3;
    default -> null;
};
~~~

**Đáp án:** Hợp lệ. Nhánh `3` boxing thành `Integer`, là `Number`; nhánh null có thể gán cho tham chiếu `Number`.

**Câu 3.** Vì sao hai phép gán dưới đây có thể khác nhau khi `maybe` là null?

~~~java
// Mã minh họa: k là int.
Integer maybe = null;
Number a = switch (k) { case 0 -> maybe; default -> 1.0d; };
var b = switch (k) { case 0 -> maybe; default -> 1.0d; };
~~~

**Đáp án:** `a` có kiểu đích tham chiếu `Number`, nên nhánh `maybe` có thể giữ null. `b` có kiểu `double` theo numeric promotion của standalone `switch`; khi `k == 0`, nó phải unbox `maybe` và ném NPE.

**Câu 4.** Có thể dùng `Long total = switch (k) { case 0 -> 1; default -> 2L; };` không?

**Đáp án:** Không nên viết như vậy: `1` là literal `int`, không thể tự chuyển theo chuỗi `int → long → Long` qua assignment conversion. Hãy dùng `1L` cho nhánh đầu nếu đích yêu cầu `Long`.

**Câu 5.** `default -> null` có bắt được selector `null` không?

**Đáp án:** Không. `default -> null` mô tả **giá trị kết quả sau khi chọn nhánh**, còn selector null là một vấn đề khác. Với Java 17, phải xử lý selector null trước `switch`; với các dạng `switch` hỗ trợ `case null` ở Java 21+, có thể xử lý riêng theo cú pháp phù hợp.

## 9. Tài liệu đối chiếu

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): xác nhận `switch expression` trở thành tính năng chính thức ở Java 14.
- [Java Language Specification SE 17 — `15.28: switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): phân biệt poly/standalone, thứ tự suy kiểu kết quả và quy tắc xử lý result expressions.
- [JLS — `5.1.7 Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7): primitive → wrapper.
- [JLS — `5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): wrapper → primitive và trường hợp null.
- [JLS — `5.2 Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): kiểu đích, tính tương thích và các phép chuyển đổi trong gán.
- [JLS — `5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): numeric promotion.
- [JLS — `4.10.4 Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4): tính kiểu chung khi các nhánh trả kiểu tham chiếu khác nhau.

**Ghi nhớ:** Một `switch expression` không chỉ “chọn một nhánh”; nó còn có **kiểu tĩnh**. Khi nhánh trả cả primitive, wrapper và tham chiếu, hãy quan sát **kiểu đích**, **quy tắc suy kiểu** và **đường unboxing có thể gặp null** để tránh lỗi biên dịch hoặc `NullPointerException` không mong muốn.