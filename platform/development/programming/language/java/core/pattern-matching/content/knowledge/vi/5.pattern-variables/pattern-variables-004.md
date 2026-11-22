# Pattern variable: Không được shadow biến đang có hiệu lực

> **Phạm vi:** Java Core Pattern Matching → Pattern variable. Bài dùng **Java 17+**, tập trung vào `instanceof` với type pattern (`instanceof String text`). Các đoạn chú thích **ERROR** cố ý không biên dịch và chỉ dùng để phân tích; chương trình chạy đầy đủ nằm ở phần 8.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích **trùng tên (name collision)**, **shadowing** và phạm vi hiệu lực (*scope*) của pattern variable.
- Dự đoán vì sao khai báo `instanceof String name` có thể bị compiler từ chối khi `name` đã là biến cục bộ, tham số hoặc pattern variable còn trong scope.
- Nhận ra **flow scoping**: phạm vi pattern variable phụ thuộc đường đi điều khiển; nó có thể kết thúc sau nhánh `if` hoặc tiếp tục sau một guard clause.
- Phân biệt trường hợp **không được phép trùng tên với biến cục bộ** và trường hợp **được phép che tên field**.
- Viết lại code bằng tên biến rõ nghĩa, tái sử dụng tên an toàn ở các nhánh không chồng scope, và xử lý lỗi biên dịch liên quan.

## 1. Quy tắc cốt lõi: pattern variable là một biến cục bộ có phạm vi theo luồng

Ví dụ Java 17:

~~~java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length()); // text là String, đã được khởi tạo.
}
~~~

`String text` khai báo **pattern variable** có tên `text`. Khi `input` khớp `String`, biến này được khởi tạo và sử dụng ở nơi compiler chứng minh kết quả match là `true`.

**Quy tắc quan trọng:** Java **không cho một pattern variable khai báo cùng tên với biến cục bộ đang ở trong phạm vi áp dụng**, bao gồm một pattern variable khác. Các quy tắc đối với tham số phương thức, tham số lambda và tham số `catch` cũng ngăn khai báo biến trùng tên ở những phạm vi tương ứng. Đây là **lỗi biên dịch**; không phụ thuộc giá trị runtime và không thể chữa bằng phép ép kiểu.

Ví dụ sau **cố ý không biên dịch**:

~~~java
static void broken(Object input) {
    String text = "đã tồn tại";

    if (input instanceof String text) { // ERROR: text đã được khai báo.
        System.out.println(text);
    }
}
~~~

`text` ở dòng đầu là một biến cục bộ; scope của nó còn hiệu lực tại câu lệnh `if`. Nếu cho pattern khai báo thêm `text`, hai biến không thể được phân biệt bằng một tên đơn giản. Compiler từ chối.

**Cách sửa:** đặt tên khác cho pattern variable hoặc thay đổi thiết kế để dùng biến đã có:

~~~java
static void fixed(Object input) {
    String fallbackText = "mặc định";

    if (input instanceof String matchedText) {
        System.out.println(matchedText);
    } else {
        System.out.println(fallbackText);
    }
}
~~~

Tên `matchedText` diễn tả rõ biến được tạo **khi match thành công**. Không cần cast lại `input` sang `String`.

## 2. Những kiểu tên đang có hiệu lực không được khai báo lại

### 2.1. Trùng tên với biến cục bộ của khối ngoài

~~~java
static void brokenLocal(Object value) {
    String name = "outer";

    {
        if (value instanceof String name) { // ERROR: name đã ở trong scope.
            System.out.println(name);
        }
    }
}
~~~

**Lưu ý:** Tạo thêm khối `{ ... }` **không** cho phép khai báo lại tên của biến cục bộ ở khối bao ngoài. Quy tắc khác với một số ngôn ngữ cho phép shadow local tùy ý trong nested block.

Cách sửa: `if (value instanceof String matchedName) { ... }`.

### 2.2. Trùng tên với tham số phương thức

~~~java
static void brokenParameter(Object value) {
    if (value instanceof String value) { // ERROR: value là tham số phương thức.
        System.out.println(value);
    }
}
~~~

Tham số `value` đã mang tên đó trong thân phương thức. Việc đối tượng có thực sự là `String` không làm thay đổi lỗi. Viết:

~~~java
static void fixedParameter(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
}
~~~

Đây cũng là lý do không nên mặc định đặt pattern variable **cùng tên với biểu thức target**. Chẳng hạn `input instanceof String input` gây trùng tên nếu `input` là tham số hoặc biến cục bộ đang trong scope.

### 2.3. Trùng tên với tham số `catch` hoặc biến trong lambda

Các đoạn dưới **cố ý không biên dịch**:

~~~java
static void brokenCatch(Object input) {
    try {
        throw new IllegalStateException("demo");
    } catch (IllegalStateException error) {
        if (input instanceof String error) { // ERROR: error là catch parameter.
            System.out.println(error);
        }
    }
}
~~~

~~~java
static void brokenLambda(Object input) {
    String name = "outer";

    Runnable task = () -> {
        if (input instanceof String name) { // ERROR: name của khối ngoài.
            System.out.println(name);
        }
    };
}
~~~

Lambda không tạo một “vùng tên hoàn toàn mới” để khai báo lại biến cục bộ đang sống ở khối bao ngoài. Hãy dùng `matchedName` hoặc một tên khác chưa bị chiếm. Với tham số lambda cũng tương tự: không khai báo lại tên tham số ở bên trong thân lambda.

### 2.4. Trùng tên với một pattern variable đang hiệu lực

~~~java
static void brokenNested(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println(text);

        if (second instanceof String text) { // ERROR: text của if ngoài vẫn trong scope.
            System.out.println(text);
        }
    }
}
~~~

Trong khối `if` ngoài, `text` đã là tên pattern variable hợp lệ. Một pattern lồng ở trong khối ấy không thể khai báo **một `text` khác**.

Cách sửa: giữ biến `text` cho đối tượng đầu và dùng `secondText` cho đối tượng thứ hai:

~~~java
static void fixedNested(Object first, Object second) {
    if (first instanceof String firstText) {
        if (second instanceof String secondText) {
            System.out.println(firstText + " / " + secondText);
        }
    }
}
~~~

## 3. Scope không đơn thuần là vị trí của dấu ngoặc nhọn

Pattern variable có **flow scoping**: compiler suy ra những điểm thực thi mà pattern chắc chắn đã match. Việc xác định **biến có đang trong scope không** phải dựa trên luồng, không chỉ nhìn khoảng cách văn bản hay một cặp `{ }`.

### 3.1. Phạm vi thông thường của `if`

~~~java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Hợp lệ.
    }

    String text = "new local"; // Hợp lệ: pattern text của if đã hết scope.
    System.out.println(text);
}
~~~

Với `if` này, pattern `text` nằm trong nhánh true; sau `if`, compiler không thể chắc rằng `input` đã khớp. Do đó tên `text` có thể được dùng cho một khai báo cục bộ mới tại vị trí đó.

### 3.2. Guard clause: scope tiếp tục sau `if`

~~~java
static int readLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }

    return text.length(); // Hợp lệ: mọi đường đi tới đây đã match.
}
~~~

Đây là cách Java tránh phải cast lại `input`. Tuy nhiên cũng vì `text` **vẫn còn trong scope**, đoạn sau **cố ý không biên dịch**:

~~~java
static int brokenGuard(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }

    String text = "other"; // ERROR: pattern text vẫn đang hiệu lực.
    return text.length();
}
~~~

Vì nhánh thất bại kết thúc bằng `return`, những câu lệnh phía dưới chỉ có thể chạy khi pattern thành công. Nếu nhánh thất bại `throw` ngoại lệ, lập luận tương tự.

### 3.3. Toán tử `&&` cho phép dùng biến, không cho khai báo trùng

~~~java
static boolean longText(Object input) {
    return input instanceof String text && text.length() >= 4;
}
~~~

Khi Java đánh giá vế phải của `&&`, vế trái đã trả `true`, nên `text` có thể được sử dụng. Nhưng không được lợi dụng vế phải để tạo thêm biến **cùng tên**:

~~~java
static boolean brokenAnd(Object first, Object second) {
    return first instanceof String text
        && second instanceof String text; // ERROR: tên text bị khai báo lại.
}
~~~

Cách sửa: `first instanceof String firstText && second instanceof String secondText`. Từ đó có thể dùng đồng thời `firstText` và `secondText` trong các biểu thức tiếp theo của nhánh true.

### 3.4. Trùng tên trong hai vế `||` vẫn có thể bị từ chối

Đoạn sau **cố ý không biên dịch**:

~~~java
static boolean brokenOr(Object first, Object second) {
    return (first instanceof String text)
        || (second instanceof String text); // ERROR: hai binding cùng tên.
}
~~~

Dù `||` có thể ngắn mạch và một trong hai phép match thành công, việc cố tạo hai pattern variable **cùng tên** trong biểu thức `||` gây xung đột khi xác định binding. Không nên suy luận rằng “chỉ một vế chạy” thì được dùng lại tên.

Nếu mục tiêu chỉ là kiểm tra có ít nhất một chuỗi, không cần pattern variable:

~~~java
static boolean anyString(Object first, Object second) {
    return first instanceof String || second instanceof String;
}
~~~

Nếu muốn truy cập chuỗi match thành công, hãy xử lý hai nhánh độc lập với tên riêng hoặc cấu trúc `if / else if` phù hợp.

## 4. Khi nào được dùng lại một tên pattern variable?

**Không phải cứ hai pattern cùng tên trong một phương thức là lỗi.** Điều quyết định là phạm vi của chúng có chồng nhau hoặc quy tắc ghép biểu thức có cấm binding cùng tên hay không.

### 4.1. Hai `if` độc lập: hợp lệ

~~~java
static void printTwo(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println("first=" + text);
    }

    if (second instanceof String text) {
        System.out.println("second=" + text);
    }
}
~~~

`text` của `if` đầu chỉ có hiệu lực ở nhánh match đầu tiên; nó **không** còn trong scope tại `if` thứ hai. Mỗi lần khai báo là một pattern variable riêng. Điều này được JLS minh họa bằng nhiều pattern có cùng tên ở những nhánh không chồng phạm vi.

### 4.2. Hai nhánh loại trừ nhau: hợp lệ

~~~java
static void printEither(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println("first=" + text);
    } else if (second instanceof String text) {
        System.out.println("second=" + text);
    }
}
~~~

Trong nhánh `else if`, pattern `text` của nhánh đầu không còn hiệu lực. Hai khai báo cùng tên vì vậy hợp lệ.

### 4.3. Sau khi scope kết thúc: hợp lệ

~~~java
static void printAfter(Object value) {
    if (value instanceof String name) {
        System.out.println(name);
    }

    String name = "fallback"; // Hợp lệ trong trường hợp if thông thường này.
    System.out.println(name);
}
~~~

So sánh với guard clause ở mục 3.2: khi `return` làm pattern tiếp tục sống sau `if`, khai báo `String name` tại cùng vị trí sẽ không còn hợp lệ.

**Quy tắc thực hành:** Nếu cần dùng hai giá trị cùng lúc, hãy đặt hai tên khác nhau (`firstText`, `secondText`). Nếu các nhánh độc lập và không giao scope, dùng lại tên ngắn (`text`) có thể hợp lệ và dễ đọc.

## 5. Ngoại lệ quan trọng: pattern variable được che tên field

Tên bài học cần hiểu chính xác theo quy tắc Java: **cấm shadow biến cục bộ đang sống** không đồng nghĩa cấm một pattern variable **cùng tên với field** của lớp.

~~~java
class FieldExample {
    private String label = "FIELD";

    void print(Object input) {
        if (input instanceof String label) {
            System.out.println(label);      // Pattern variable.
            System.out.println(this.label); // Field của đối tượng.
        }
    }
}
~~~

Đây là code **hợp lệ**. Bên trong nhánh match, tên đơn giản `label` trỏ đến pattern variable; `this.label` vẫn truy cập được field. Với field `static`, có thể dùng tên lớp: `ClassName.fieldName`.

Phân biệt hai trường hợp:

| Biến đã có tên `label` | Pattern mới `instanceof String label` | Giải thích |
| --- | --- | --- |
| Tham số phương thức trong cùng thân hàm | **Lỗi biên dịch** | Tên tham số bị trùng trong vùng hiệu lực |
| Biến cục bộ ở khối bao ngoài | **Lỗi biên dịch** | Không được shadow local còn scope |
| Pattern variable khác đang hiệu lực | **Lỗi biên dịch** | Trùng binding trong vùng hoạt động |
| Field của lớp, không có local/parameter cùng tên | **Hợp lệ** | Pattern variable che tên field tại nhánh của nó; dùng `this.label` để truy cập field |
| Pattern variable thuộc một `if` độc lập đã hết scope | **Hợp lệ** | Hai scope tách biệt |

**Về thiết kế:** Dù shadow field được cho phép, đặt tên pattern dễ phân biệt (`matchedLabel`) thường dễ bảo trì hơn. Khi cố ý trùng tên, phải hiểu rõ `label` và `this.label` là **hai biến khác nhau**.

## 6. Vì sao compiler từ chối ở compile time?

Compiler cần gắn mỗi tên đơn giản trong biểu thức với **một khai báo hợp lệ và xác định**, đồng thời bảo đảm pattern variable chỉ được sử dụng khi match thành công. Java áp dụng:

1. **Quy tắc khai báo tên:** tham số/biến cục bộ/pattern variable đang ở trong scope không được bị khai báo đè tên theo các quy định của JLS `6.4.
2. **Quy tắc giới thiệu pattern variable theo luồng:** `instanceof String text` đưa biến vào scope tại các điểm mà điều kiện match được chứng minh là `true` (JLS `6.3).
3. **Quy tắc biểu thức logic và nhánh:** `&&`, `||`, `!`, `if` và guard clause quyết định nơi một binding được sử dụng và nơi việc khai báo trùng trở thành lỗi.

Vì lỗi nằm ở **mã nguồn và phạm vi**, đổi giá trị của `input` từ `String` sang `Integer`, hay thay `null` bằng chuỗi, không sửa được tên đã trùng. Đừng nhầm với `ClassCastException`, vốn là ngoại lệ runtime do cast không hợp lệ.

Thông báo từ `javac` thường có dạng *variable ... is already defined* hoặc thông báo về binding bị định nghĩa lại. Cách diễn đạt cụ thể có thể khác nhau giữa các phiên bản JDK; hãy xem cả vị trí compiler gạch chân và danh sách khai báo trong scope.

## 7. Cách sửa lỗi có hệ thống

Khi thấy lỗi với tên pattern variable, làm theo trình tự:

1. **Tìm khai báo cùng tên** của tham số, local, pattern variable, catch/lambda trong phương thức và các khối bao ngoài. Ví dụ `String text = ...` xuất hiện trước `instanceof String text`.
2. **Phân tích scope theo luồng:** pattern đến từ một `if` thông thường chỉ sống ở nhánh true? Hay guard `if (!(o instanceof String text)) return;` làm nó sống ở phần sau? Có `&&` / `||` hoặc nested `if` không?
3. **Đổi tên binding đang xung đột** sao cho phản ánh nguồn dữ liệu: `matchedText`, `outerText`, `innerText`, `leftValue`, `rightValue`. Đổi đồng thời mọi chỗ sử dụng tên thuộc binding ấy.
4. **Giữ pattern thay cho cast thừa:** sau `if (o instanceof String matchedText)`, dùng `matchedText` trực tiếp. Không cần `(String) o`.
5. **Nếu xung đột là field**, xác định có thực sự cần trùng tên không. Dùng `this.field` hoặc đặt tên pattern rõ hơn.
6. **Biên dịch lại** và chạy thử với các giá trị match, không match, `null` để xác nhận luồng xử lý.

Ví dụ sửa nested pattern:

~~~java
// Sai: cả hai pattern cùng tên text trong scope chồng lấn.
if (left instanceof String text) {
    if (right instanceof String text) { // ERROR
        System.out.println(text);
    }
}

// Đúng: đặt tên theo đối tượng nguồn.
if (left instanceof String leftText) {
    if (right instanceof String rightText) {
        System.out.println(leftText + ", " + rightText);
    }
}
~~~

Đây là mã **minh họa đặt bên trong một phương thức** có tham số `Object left, Object right`; không phải tệp Java độc lập. Không copy cả hai đoạn “Sai” và “Đúng” vào cùng một phương thức rồi mong compiler chấp nhận.

## 8. Chương trình hoàn chỉnh chạy trên Java 17+

Lưu nguyên đoạn sau vào tệp **`PatternScopeDemo.java`**:

~~~java
public class PatternScopeDemo {
    private final String label = "FIELD";

    void print(Object first, Object second) {
        // Hợp lệ: pattern variable che tên field label.
        if (first instanceof String label) {
            System.out.println("local=" + label + ", field=" + this.label);
        }

        // Hợp lệ: tên label ở if trước đã hết scope.
        if (second instanceof String label) {
            System.out.println("second=" + label);
        }

        // Hợp lệ: text có scope ở vế phải của && khi match thành công.
        if (first instanceof String text && !text.isBlank()) {
            System.out.println("length=" + text.length());
        }

        // Hợp lệ: matched tiếp tục trong scope sau guard clause.
        if (!(second instanceof String matched)) {
            System.out.println("not string");
            return;
        }

        System.out.println("after guard=" + matched.toUpperCase());
    }

    public static void main(String[] args) {
        new PatternScopeDemo().print("hello", "world");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 PatternScopeDemo.java
java PatternScopeDemo
~~~

**Kết quả stdout chính xác:**

~~~text
local=hello, field=FIELD
second=world
length=5
after guard=WORLD
~~~

Diễn giải:

- `local=hello, field=FIELD`: pattern `label` nhận `"hello"`, còn `this.label` vẫn là field `"FIELD"`.
- `second=world`: khai báo `label` ở `if` kế tiếp hợp lệ vì pattern `label` trước đã hết scope.
- `length=5`: `text` chỉ được dùng khi `instanceof String` trả `true`, nên `text.isBlank()` và `text.length()` an toàn.
- `after guard=WORLD`: nhánh không match của `second` đã `return`; ở phần tiếp theo, `matched` chắc chắn là `String`.

Nếu truyền `new PatternScopeDemo().print("hello", 42)` thì nhánh `second instanceof String label` không chạy và guard in thêm `not string` rồi `return`. **Không cần cast**, cũng không gặp lỗi “biến trùng tên” vì tên được sử dụng theo những scope hợp lệ.

## 9. Những nhầm lẫn thường gặp

- **“Mọi khai báo pattern trùng tên trong cùng phương thức đều lỗi.”** Sai: hai `if` độc lập hoặc hai nhánh loại trừ nhau có thể dùng lại tên.
- **“Chỉ cần đặt trong một cặp `{ }` mới là có thể khai báo trùng tên.”** Sai: một local/parameter của khối bao ngoài vẫn có scope trong khối con.
- **“Pattern variable chỉ sống ở đúng nhánh `if` ban đầu.”** Sai: sau guard clause với `return`/`throw` phù hợp, biến có thể còn trong scope.
- **“Hai vế `||` không chạy đồng thời nên được khai báo cùng tên.”** Sai: JLS cấm những trường hợp tạo binding trùng tên giữa các vế.
- **“Cấm shadow mọi loại biến, kể cả field.”** Sai: có thể che field bằng local/pattern variable và truy cập field có định danh `this.field` hoặc `ClassName.field`.
- **“Lỗi trùng tên là do dữ liệu không match `instanceof`.”** Sai: lỗi trùng tên xảy ra ở compile time, ngay cả khi không chạy chương trình.
- **“Đổi kiểu của pattern nhưng giữ nguyên tên thì hết xung đột.”** Sai: tên `text` trùng trong scope vẫn là vấn đề dù pattern đổi từ `String` sang `CharSequence`.
- **“Có thể sửa bằng cách cast thủ công mọi chỗ.”** Cast không giải quyết tên trùng; nên đổi tên pattern hoặc sắp xếp lại scope hợp lệ.

## 10. Bài tập kiểm tra

**Câu 1:** Đoạn sau biên dịch không? Vì sao?

~~~java
static void test(Object input) {
    String result = "old";
    if (input instanceof String result) {
        System.out.println(result);
    }
}
~~~

**Câu 2:** Vì sao hai khai báo `name` ở đây hợp lệ?

~~~java
static void test(Object a, Object b) {
    if (a instanceof String name) {
        System.out.println(name);
    }
    if (b instanceof String name) {
        System.out.println(name);
    }
}
~~~

**Câu 3:** Đoạn sau có thể khai báo thêm `String s = "new";` ở sau `if` không?

~~~java
static void test(Object obj) {
    if (!(obj instanceof String s)) {
        throw new IllegalArgumentException();
    }
    // Khai báo String s = "new"; tại đây?
}
~~~

**Câu 4:** Trong `class Box { String value = "FIELD"; ... }`, nếu viết `if (obj instanceof String value)` trong một phương thức không có biến local/parameter `value`, compiler có chấp nhận không? `value` và `this.value` trỏ tới đâu?

**Câu 5:** Xét `if (a instanceof String s && b instanceof String s)`. Lỗi gì? Chỉnh lại để dùng được cả hai chuỗi.

**Câu 6:** Phân biệt `if (a instanceof String s) ... else if (b instanceof String s) ...` và `(a instanceof String s) || (b instanceof String s)` về khả năng trùng tên.

### Đáp án

1. **Không**: biến cục bộ `result` đã nằm trong scope khi pattern cũng khai báo `result`. Đổi pattern thành `matchedResult`.
2. **Hợp lệ**: scope của `name` trong `if` đầu kết thúc trước `if` thứ hai. Đây là hai pattern variable khác nhau.
3. **Không**: nhánh thất bại ném ngoại lệ nên `s` tiếp tục có scope ở phần sau. Hãy dùng tên mới nếu cần thêm biến.
4. **Có**: pattern variable được phép che tên field; `value` là chuỗi match, `this.value` là field của đối tượng.
5. **Lỗi tên pattern trùng** trong `&&`. Sửa thành `a instanceof String firstText && b instanceof String secondText` rồi dùng các biến ở nhánh `true`.
6. **`else if` có thể hợp lệ** vì hai nhánh không chồng scope; còn biểu thức `||` khai báo hai binding tên `s` bị JLS từ chối.

## Nguồn tham khảo chính thức

- [Java Language Specification 17 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): flow scoping của pattern variable, `instanceof`, `&&`, `||`, `if` và guard clause.
- [Java Language Specification 17 — `6.4 Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): cấm khai báo trùng tên local đang trong scope; ví dụ `Test4`/`Test5` về pattern names.
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): phạm vi pattern variable và các ví dụ `if`/`&&`/`!`.
- [Java Language Specification 17 — `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): ý nghĩa pattern, khai báo và gán giá trị cho pattern variable.
