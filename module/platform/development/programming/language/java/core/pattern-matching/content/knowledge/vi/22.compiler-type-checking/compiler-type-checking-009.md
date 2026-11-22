# Lỗi do record component pattern không tương thích trong Java 21+

## 1. Vấn đề: compiler kiểm tra gì khi tách record?

**Record pattern** cho phép kiểm tra một đối tượng có phù hợp với một record class rồi tách dữ liệu của từng *record component* trong một biểu thức `instanceof` hoặc nhãn `case` của `switch`. Ví dụ:

~~~java
record Point(int x, int y) {}

Object value = new Point(2, 3);
if (value instanceof Point(int a, int b)) {
    System.out.println(a + b); // 5
}
~~~

`Point(int a, int b)` có ba phần liên quan đến việc kiểm tra kiểu:

1. **`Point`** là record class được chọn làm kiểu của record pattern.
2. **Hai vị trí component** tương ứng theo thứ tự với `x` và `y` của `record Point(int x, int y)`.
3. **`int a` và `int b`** là hai component patterns, ràng buộc các pattern variable nếu toàn bộ phép so khớp thành công.

Trong Java 21, compiler không chấp nhận mọi chuỗi biểu thức đặt trong `Point(...)`. Nó kiểm tra số component, tính phù hợp của kiểu pattern với kiểu khai báo của từng component và các quy tắc generic. Nếu một component pattern không thể áp dụng hợp lệ cho component tương ứng, **chương trình không biên dịch**.

Điểm mấu chốt là phân biệt hai tình huống:

- **Không tương thích về mặt kiểu tại compile time:** compiler chứng minh pattern không hợp lệ, nên báo lỗi trước khi chạy.
- **Pattern hợp lệ nhưng không khớp dữ liệu tại runtime:** compiler cho phép, song giá trị thực tế của component không đáp ứng một component pattern cụ thể; biểu thức `instanceof` trả về `false` hoặc `switch` tìm case khác.

Tính năng record patterns được chuẩn hóa từ **Java 21 (JEP 440)**, không cần `--enable-preview`. Java 17 hỗ trợ type pattern trong `instanceof` nhưng **chưa** có record pattern chuẩn như những ví dụ dưới đây.

## 2. Nguyên tắc tương thích: vị trí và kiểu khai báo

Xét hai record:

~~~java
record Point(int x, int y) {}
record Person(String name, String city) {}
~~~

Các record component có tên, kiểu và **thứ tự cố định**. Khi viết `Point(int a, int b)`, compiler ghép pattern đầu với component `x` kiểu `int`, pattern thứ hai với `y` kiểu `int`. Tên `a` và `b` là tên biến mới, không phải tên component; có thể khác `x`, `y`.

**Để một record pattern hợp lệ:**

- Kiểu ngoài phải là một **record class type**, và kiểu của giá trị được kiểm tra phải cho phép áp dụng record pattern đó theo quy tắc chuyển kiểu.
- Danh sách component patterns phải có **đúng số vị trí** bằng số component khai báo trong record.
- Mỗi component pattern phải áp dụng được cho **kiểu tĩnh của component** ở vị trí tương ứng. Kiểu pattern không cần luôn giống hệt kiểu khai báo; một phép kiểm tra kiểu tham chiếu hẹp hơn có thể hợp lệ nếu Java cho phép kiểm tra ở runtime.
- Với record generic, tham số kiểu và pattern suy luận từ ngữ cảnh phải thỏa các quy tắc chuyển kiểu được kiểm tra an toàn (*checked cast*); type erasure vẫn có hiệu lực.
- Một pattern lồng nhau phải tương thích với **kiểu của component cha**, không chỉ tương thích với kiểu tổng thể của đầu vào.

Thông thường, compiler có thể xác định các lỗi này từ khai báo record và pattern mà **không cần biết đối tượng thực tế** của chương trình.

## 3. Lỗi số lượng record component pattern không khớp

Đây là lỗi cấu trúc rõ nhất. Record `Point` có **hai** component, nên phải dùng hai component patterns:

~~~java
record Point(int x, int y) {}

Object input = new Point(1, 2);

// KHÔNG BIÊN DỊCH: Point có 2 component nhưng pattern chỉ có 1.
// if (input instanceof Point(int x)) {
//     System.out.println(x);
// }

// ĐÚNG:
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 3
}
~~~

Lỗi compiler điển hình: `incorrect number of nested patterns`, kèm danh sách kiểu component mà compiler mong đợi.

Đưa thêm một pattern thứ ba cũng sai:

~~~java
// KHÔNG BIÊN DỊCH:
// if (input instanceof Point(int x, int y, int z)) { ... }
~~~

Muốn chỉ dùng `x` thì vẫn phải cung cấp pattern cho `y`, ví dụ `Point(int x, var ignored)`. Trong Java 21 dạng ổn định, nên dùng biến có tên như `ignored` cho vị trí không cần sử dụng. Đừng tự ý bỏ vị trí khỏi danh sách.

## 4. Lỗi kiểu của component pattern không phù hợp

Compiler biết kiểu tĩnh của từng component. Nếu component kiểu nguyên thủy `int` nhưng pattern yêu cầu một tham chiếu `String`, mẫu không thể áp dụng:

~~~java
record Point(int x, int y) {}

// KHÔNG BIÊN DỊCH:
// Object input = new Point(2, 3);
// if (input instanceof Point(String x, int y)) { ... }
~~~

Với Java compiler, lỗi thuộc dạng:

~~~text
incompatible types: int cannot be converted to java.lang.String
~~~

Nguyên nhân không phải giá trị `2` “không giống chuỗi”, mà là **kiểu khai báo của component đầu đã là `int`**. Pattern `String x` không có chuyển đổi hợp lệ để kiểm tra một component nguyên thủy như vậy.

Cách sửa:

~~~java
Object input = new Point(2, 3);

if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}

// Hoặc để trình biên dịch suy luận từ record component:
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y); // 5
}
~~~

Với `Point(var x, var y)`, compiler suy luận cả hai pattern variables là `int`. `var` trong component pattern **không có nghĩa là kiểu động**; nó vẫn cho compiler một kiểu tĩnh xác định dựa trên khai báo record.

Để tránh nhầm lẫn, không suy luận rằng mọi kiểu Java có thể chuyển bằng phép gán hay ép kiểu ở nơi khác sẽ dùng được nguyên dạng bên trong một type pattern. Các quy tắc áp dụng type patterns đối với primitive/reference là quy tắc riêng theo phiên bản Java đang biên dịch.

## 5. Lỗi pattern lồng không tương thích với kiểu component cha

Xét:

~~~java
record Point(int x, int y) {}
record Person(String name, String city) {}
record NamedPoint(String name, Point point) {}
~~~

Mẫu sau **sai**:

~~~java
// KHÔNG BIÊN DỊCH:
// Object value = new Person("An", "Hà Nội");
// if (value instanceof Person(String name, Point(var x, var y))) { ... }
~~~

Compiler biết component `city` của `Person` mang kiểu `String`. Nhưng pattern ở vị trí thứ hai là record pattern `Point(...)`: nó đòi một giá trị phù hợp kiểu record `Point`. `String` và `Point` không có chuyển kiểu được phép trong trường hợp này.

Thông báo điển hình:

~~~text
incompatible types: java.lang.String cannot be converted to Point
~~~

Tùy vị trí khai báo và trình biên dịch, tên lớp trong thông báo có thể được viết đầy đủ hoặc có tiền tố class bên ngoài.

Sửa theo **cấu trúc record thực sự**:

~~~java
// Person có String city:
Object p = new Person("An", "Hà Nội");

if (p instanceof Person(var name, var city)) {
    System.out.println(name + ": " + city); // An: Hà Nội
}

// NamedPoint mới có component point thuộc kiểu Point:
Object n = new NamedPoint("A", new Point(4, 7));

if (n instanceof NamedPoint(var name, Point(var x, var y))) {
    System.out.println(name + ": " + x + ", " + y); // A: 4, 7
}
~~~

Khi debug pattern lồng nhiều cấp, hãy đi **từ ngoài vào trong** và kiểm tra kiểu component ở mỗi cấp trước khi đặt một record pattern khác vào vị trí đó. Việc tên biến là `point` hoặc `city` không làm thay đổi kiểu của component: **khai báo record** mới quyết định.

## 6. Kiểu reference hẹp hơn có thể hợp lệ: compile được nhưng runtime không khớp

**Không phải mọi kiểu pattern khác kiểu khai báo đều là lỗi.** Ví dụ:

~~~java
record Amount(Number number) {}

static String classify(Object value) {
    if (value instanceof Amount(Integer n)) {
        return "Integer: " + (n + 1);
    }
    if (value instanceof Amount(Double n)) {
        return "Double: " + n;
    }
    return "Không khớp số";
}
~~~

Component `number` được khai báo là `Number`. `Integer` và `Double` đều là các kiểu con phù hợp với phép kiểm tra kiểu tham chiếu tại runtime. Do đó compiler **chấp nhận** `Amount(Integer n)` và `Amount(Double n)`.

Kết quả:

~~~java
System.out.println(classify(new Amount(12)));   // Integer: 13
System.out.println(classify(new Amount(1.5)));  // Double: 1.5
System.out.println(classify(new Amount(3L)));   // Không khớp số
~~~

`new Amount(3L)` hợp lệ vì `Long` là một `Number`, nhưng không khớp với `Integer` hoặc `Double`. Đây là **không khớp runtime**, khác hẳn lỗi compile time ở mục 4.

Bảng giúp phân biệt:

| Kiểu khai báo component | Component pattern | Compile? | Kết quả |
| --- | --- | --- | --- |
| `int` | `int x` | Có | Ràng buộc giá trị `int` |
| `int` | `var x` | Có | `x` được suy luận là `int` |
| `int` | `String x` | **Không** | Kiểu tham chiếu không tương thích với `int` |
| `Number` | `Integer n` | Có | Chỉ khớp runtime khi component thực sự là `Integer` |
| `Number` | `Double n` | Có | Chỉ khớp runtime khi component thực sự là `Double` |
| `Number` | `var n` | Có | `n` được suy luận theo kiểu khai báo `Number` |
| `String` | `Point(var x, var y)` | **Không** | Nested record pattern không áp dụng được cho `String` |

**Quy tắc thực hành:** khi một reference component có kiểu cha rộng, một type pattern con có thể làm **bộ lọc runtime**. Khi kiểu pattern vốn đã không thể được áp dụng cho component theo luật ngôn ngữ, compiler từ chối trước khi chạy.

## 7. Generic record pattern: lỗi do kiểu không kiểm tra được sau erasure

Record có thể mang tham số kiểu:

~~~java
record Box<T>(T value) {}
~~~

Nếu kiểu tĩnh của đầu vào đã là `Box<String>`, compiler có đủ thông tin để suy luận kiểu component:

~~~java
static String typed(Box<String> box) {
    if (box instanceof Box(var text)) {
        return text == null ? "null" : text.toUpperCase();
    }
    return "Không khớp";
}
~~~

`text` có kiểu tĩnh `String`. Có thể viết `Box<String>(var text)` trong ngữ cảnh phù hợp này; đây là hợp đồng được kiểm tra dựa trên **kiểu tĩnh**, không phải do JVM lưu lại đối số kiểu generic trong từng instance.

Ngược lại, đoạn sau **không biên dịch**:

~~~java
// KHÔNG BIÊN DỊCH:
// static void invalid(Object input) {
//     if (input instanceof Box<String>(var text)) {
//         System.out.println(text);
//     }
// }
~~~

Compiler không thể dùng kiểm tra runtime để chứng minh một `Object` là `Box<String>` thay vì `Box<Integer>`: tham số generic `String` bị **type erasure**. Lỗi thường ở dạng `Object cannot be safely cast to Box<String>`.

Ngay cả với `Box<String>`, việc yêu cầu tham số khác vẫn sai:

~~~java
// KHÔNG BIÊN DỊCH:
// static void invalidTyped(Box<String> box) {
//     if (box instanceof Box<Integer>(var number)) { ... }
// }
~~~

Compiler biết `Box<String>` không thể được dùng như `Box<Integer>` theo luật bất biến (*invariance*) của generic type arguments.

Cách xử lý đầu vào chưa biết là dùng **wildcard** rồi kiểm tra giá trị component khi cần:

~~~java
static String inspect(Object input) {
    if (input instanceof Box<?>(var payload)) {
        if (payload instanceof String text) {
            return "String: " + text.toUpperCase();
        }
        return "Giá trị khác";
    }
    return "Không phải Box";
}
~~~

`Box<?>` có thể so khớp an toàn từ `Object` mà không hứa hẹn `T` là `String`. Phép `payload instanceof String text` kiểm tra **giá trị component đang có** ở runtime, không xác nhận generic argument đã bị erasure.

Cũng có thể dùng `input instanceof Box(var payload)` khi compiler suy luận kiểu pattern đủ an toàn; nếu đầu vào chỉ là `Object`, **không** được mặc nhiên xem `payload` là `String`.

## 8. `null`: phân biệt kiểu pattern không phù hợp với giá trị không khớp

`null` dễ gây hiểu nhầm vì hai cấp kiểm tra khác nhau.

**A. Giá trị của cả record là null.**

~~~java
Object input = null;
if (input instanceof Point(var x, var y)) {
    // Không chạy: record pattern không khớp null.
}
~~~

Đây là kết quả **runtime false**, không phải lỗi biên dịch.

**B. Component chứa record lồng là null.**

~~~java
Object value = new NamedPoint("B", null);

if (value instanceof NamedPoint(var name, Point(var x, var y))) {
    // Không chạy: nested record pattern Point(...) không khớp null.
}
~~~

Mẫu lồng `Point(...)` hợp lệ với component `point` kiểu `Point`, nhưng **giá trị runtime** của component là null.

**C. Component reference là null nhưng component pattern vô điều kiện.**

~~~java
record Contact(String email) {}

Contact contact = new Contact(null);
if (contact instanceof Contact(String email)) {
    System.out.println(email == null); // true
}
~~~

Trong record patterns, một **unconditional type pattern** áp dụng cho component có thể ràng buộc `null`. Ở ví dụ này, component `email` đã được khai báo `String` nên type pattern `String email` phù hợp vô điều kiện; nó nhận giá trị `null`. `var email` cũng có thể nhận null.

Đừng đồng nhất quy tắc component pattern bên trong một record pattern với phép kiểm tra độc lập `null instanceof String` (luôn `false`).

**D. Reference pattern hẹp hơn không khớp null.**

~~~java
record Amount(Number number) {}
Object value = new Amount(null);

if (value instanceof Amount(Integer n)) {
    // Không chạy: Integer là một kiểm tra hẹp hơn Number; null không khớp.
}
~~~

`Amount(Integer n)` vẫn **biên dịch hợp lệ**. Dữ liệu null chỉ làm component pattern này không khớp lúc chạy. Nếu cần chấp nhận null, dùng `Amount(var number)` và kiểm tra `number == null` rõ ràng.

## 9. Quy trình đọc lỗi compiler và sửa pattern

Khi gặp lỗi trong `instanceof RecordType(...)` hoặc `case RecordType(...)`, nên kiểm tra theo đúng thứ tự sau.

1. **Xem khai báo record**: xác định tên kiểu và danh sách component thực tế. Ví dụ `record Point(int x, int y)` có chính xác hai vị trí.
2. **Đếm pattern**: nếu số đối số trong dấu ngoặc khác số component, sửa số vị trí trước. Kể cả component không cần dùng cũng phải có pattern tương ứng.
3. **So từng vị trí với kiểu khai báo**: với `Point`, vị trí 1 là `int`, vị trí 2 là `int`. Không dựa vào tên biến trong pattern để suy ra kiểu.
4. **Kiểm tra pattern lồng**: nếu thấy `SomeRecord(...)` ở vị trí thứ hai, component thứ hai của record ngoài phải có kiểu tương thích với `SomeRecord`.
5. **Kiểm tra generic source type**: nếu biểu thức có kiểu `Object`/raw type, tránh tự viết một type argument cụ thể không kiểm chứng được. Dùng wildcard và kiểm tra component khi cần.
6. **Phân biệt compile error với runtime no-match**: `Number -> Integer` có thể là kiểm tra runtime hợp lệ; `int -> String` là kiểu sai từ đầu.
7. **Xét null và flow scoping**: với nested record pattern, null có thể làm nhánh không khớp; pattern variable chỉ dùng ở vị trí compiler bảo đảm đã khớp.

Không nên “sửa” lỗi type mismatch bằng cách ép kiểu không an toàn hoặc chuyển mọi thứ sang raw generic. Nếu cấu trúc dữ liệu thực sự khác khai báo mà pattern mong đợi, hãy cập nhật pattern theo **hợp đồng dữ liệu đúng**.

## 10. Ví dụ hoàn chỉnh Java 21+, chạy được

Lưu thành **`RecordPatternCompatibilityDemo.java`**:

~~~java
public class RecordPatternCompatibilityDemo {
    record Point(int x, int y) {}
    record NamedPoint(String name, Point point) {}
    record Amount(Number number) {}
    record Box<T>(T value) {}

    static String point(Object input) {
        if (input instanceof Point(int x, int y)) {
            return "Tổng: " + (x + y);
        }
        return "Không phải Point";
    }

    static String nested(Object input) {
        if (input instanceof NamedPoint(var name, Point(var x, var y))) {
            return name + ": " + x + ", " + y;
        }
        return "Nested không khớp";
    }

    static String amount(Object input) {
        if (input instanceof Amount(Integer n)) {
            return "Integer: " + (n + 1);
        }
        if (input instanceof Amount(Double n)) {
            return "Double: " + n;
        }
        return "Không khớp số";
    }

    static String unknownBox(Object input) {
        if (input instanceof Box<?>(var payload)) {
            if (payload instanceof String s) {
                return "String: " + s.toUpperCase();
            }
            return "Khác: " +
                (payload == null ? "null" : payload.getClass().getSimpleName());
        }
        return "Không phải Box";
    }

    static String typedBox(Box<String> box) {
        if (box instanceof Box(var text)) {
            return "Dài: " + (text == null ? "null" : text.length());
        }
        return "Không khớp";
    }

    public static void main(String[] args) {
        System.out.println(point(new Point(2, 3)));
        System.out.println(nested(new NamedPoint("A", new Point(4, 7))));
        System.out.println(nested(new NamedPoint("B", null)));
        System.out.println(amount(new Amount(12)));
        System.out.println(amount(new Amount(1.5)));
        System.out.println(amount(new Amount(3L)));
        System.out.println(unknownBox(new Box<>("java")));
        System.out.println(unknownBox(new Box<>(42)));
        System.out.println(unknownBox(new Box<>(null)));
        System.out.println(typedBox(new Box<>("hello")));
        System.out.println(typedBox(new Box<>(null)));
        System.out.println(point(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac --release 21 RecordPatternCompatibilityDemo.java
java RecordPatternCompatibilityDemo
~~~

Đầu ra:

~~~text
Tổng: 5
A: 4, 7
Nested không khớp
Integer: 13
Double: 1.5
Không khớp số
String: JAVA
Khác: Integer
Khác: null
Dài: 5
Dài: null
Không phải Point
~~~

Điều chương trình chứng minh:

- `Point(int x, int y)` và `NamedPoint(var name, Point(var x, var y))` hợp lệ về số lượng, thứ tự và kiểu component.
- `NamedPoint("B", null)` vẫn tạo được đối tượng, nhưng **nested Point pattern** không khớp khi component là null.
- `Amount(Integer n)` và `Amount(Double n)` là hai phép kiểm tra runtime hợp lệ đối với component `Number`; `Long` không khớp mẫu nào.
- `Box<?>(var payload)` kiểm tra lớp record mà không đòi generic argument cụ thể; `payload instanceof String s` mới kiểm tra String thực tế.
- Với `Box<String>`, `Box(var text)` suy luận `text` là `String`; component reference null được xử lý tường minh.
- Bản thân selector `null` không khớp `Point(...)`.

## 11. Năm lỗi compile time cần tự nhận diện

Các ví dụ sau **cố ý không biên dịch**. Đọc riêng như tình huống chẩn đoán; không đưa vào tệp của mục 10.

~~~java
record Point(int x, int y) {}
record Person(String name, String city) {}
record Box<T>(T value) {}

class InvalidPatterns {
    static void wrongArity(Object v) {
        // ERROR 1: Point yêu cầu 2 component patterns.
        if (v instanceof Point(int x)) {}
    }

    static void wrongComponentType(Object v) {
        // ERROR 2: component x có kiểu int, không thể là String pattern.
        if (v instanceof Point(String x, int y)) {}
    }

    static void wrongNestedType(Object v) {
        // ERROR 3: city là String, không thể áp dụng Point record pattern.
        if (v instanceof Person(String name, Point(var x, var y))) {}
    }

    static void wrongGenericFromObject(Object v) {
        // ERROR 4: Object -> Box<String> cần unchecked conversion.
        if (v instanceof Box<String>(var text)) {}
    }

    static void wrongGenericArgument(Box<String> v) {
        // ERROR 5: Box<String> không chuyển thành Box<Integer>.
        if (v instanceof Box<Integer>(var number)) {}
    }
}
~~~

Bảng phân loại:

| Đoạn | Lỗi | Hướng sửa |
| --- | --- | --- |
| `Point(int x)` | Sai số lượng component patterns | `Point(int x, var ignored)` |
| `Point(String x, int y)` | `int` không tương thích `String` | `Point(int x, int y)` hoặc `Point(var x, var y)` |
| `Person(String name, Point(...))` | Component `city` là `String`, không phải `Point` | `Person(var name, var city)`; hoặc dùng một record thực sự có component `Point` |
| `Object -> Box<String>(var s)` | Type erasure, cần unchecked cast | `Box<?>(var value)`, rồi kiểm tra `value instanceof String s` |
| `Box<String> -> Box<Integer>(var n)` | Generic arguments mâu thuẫn | Dùng `Box(var text)` và kiểu đầu vào đúng |

Các lỗi này đều có thể được xác định bằng **compiler**. Không sửa chúng bằng việc thêm `if (value != null)`: kiểm tra null không thể làm một kiểu component bất tương thích trở nên hợp lệ.

## 12. Bài tập có hướng dẫn đáp án

**Bài 1 — Sai số lượng.** Với `record RGB(int red, int green, int blue) {}`, vì sao `RGB(int r, int g)` lỗi? Nếu chỉ cần `red`, sửa như thế nào?

**Bài 2 — Sai kiểu tĩnh.** Với `record Task(String name, int priority) {}`, sửa pattern `Task(String name, String priority)` để in `name + " / " + priority`.

**Bài 3 — Pattern hợp lệ nhưng không khớp.** Với `record Amount(Number number) {}`, `Amount(Integer n)` có biên dịch không? Đối tượng `new Amount(3.5)` có khớp không? Phân biệt hai câu trả lời.

**Bài 4 — Nested record và null.** Với `record Holder(Point point) {}`, tại sao `Holder(Point(var x, var y))` biên dịch được nhưng lại không khớp `new Holder(null)`?

**Bài 5 — Generic.** Tại sao `Object obj` không thể dùng `obj instanceof Box<String>(var text)`? Viết lại cách kiểm tra an toàn để lấy chuỗi khi component là `String`.

**Gợi ý:**

~~~java
// 1: RGB có 3 component, luôn cần 3 vị trí.
if (obj instanceof RGB(int r, var ignoredG, var ignoredB)) {
    System.out.println(r);
}

// 2: priority là int.
if (obj instanceof Task(String name, int priority)) {
    System.out.println(name + " / " + priority);
}

// 5: giữ kiểu generic ở dạng wildcard và kiểm tra giá trị component.
if (obj instanceof Box<?>(var value)
        && value instanceof String text) {
    System.out.println(text);
}
~~~

Bài 3: pattern `Amount(Integer n)` biên dịch **được** vì `Integer` là subtype phù hợp của `Number`; `new Amount(3.5)` chứa `Double` nên không khớp runtime. Bài 4: kiểu component `Point` hợp lệ cho nested record pattern; giá trị null không được một record pattern tiếp nhận.

## 13. Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns, nested patterns, kiểu của component patterns, suy luận kiểu (Java 21).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): cú pháp và ví dụ.
- [JLS Java 21 — `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, quy tắc áp dụng và ràng buộc.
- [JLS Java 21 — `4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): giới hạn runtime với generic arguments.
