# Kiểu tĩnh, kiểu động và kiểm tra kiểu trong Java

> **Chủ đề:** OOP → Cơ chế ngôn ngữ → Kiểu tĩnh, kiểu động và kiểm tra kiểu.  
> **Mục tiêu:** Phân biệt *statically typed* và *dynamically typed*, hiểu **kiểu tại thời điểm biên dịch** với **kiểu thực tế của đối tượng lúc chạy**, giải thích Java vừa kiểm tra kiểu tĩnh vừa có đa hình động, biết vị trí cần kiểm tra runtime và xử lý đúng những giới hạn của generic type.

## 1. “Kiểu” đang nói về điều gì?

**Kiểu dữ liệu (type)** mô tả những giá trị một biểu thức có thể biểu diễn và những thao tác được phép thực hiện với biểu thức đó. Java có kiểu nguyên thủy như `int`, `boolean`, `double` và kiểu tham chiếu như `String`, `List<String>`, `User` hoặc interface `PaymentService`.

Trong một hệ thống kiểu, cần phân biệt ít nhất ba câu hỏi:

1. **Biểu thức/biến có kiểu gì tại thời điểm biên dịch?** Java dùng thông tin kiểu này để kiểm tra phép gán, lời gọi phương thức, toán tử và phần lớn ràng buộc generic.
2. **Giá trị đang trỏ tới đối tượng thuộc lớp thực tế nào khi chạy?** Một biến có kiểu tĩnh là interface có thể tham chiếu tới các implementation khác nhau.
3. **Những kiểm tra nào vẫn cần tại runtime?** Ép kiểu xuống lớp con, ghi vào mảng, kiểm tra input, phản chiếu (*reflection*) và nhiều điều kiện nghiệp vụ chỉ có thể xác nhận khi chạy.

Hai chữ “tĩnh/động” có thể chỉ **hệ thống kiểm tra kiểu** hoặc **cơ chế phân giải lời gọi phương thức**, là hai khái niệm không đồng nhất. Java là ngôn ngữ **kiểm tra kiểu tĩnh**, nhưng có **dynamic dispatch** cho phương thức instance được override.

## 2. Statically typed và dynamically typed

Trong ngôn ngữ **statically typed**, kiểu của biểu thức được phân tích và phần lớn quan hệ kiểu được kiểm tra **trước khi chương trình chạy**. Java thuộc nhóm này: những lời gọi phương thức hoặc phép gán không phù hợp sẽ bị từ chối khi biên dịch, nếu chúng xuất hiện trong mã nguồn được trình biên dịch kiểm tra bình thường.

Trong ngôn ngữ **dynamically typed**, các biến/tên thường không bị ràng buộc vào một kiểu khai báo cố định theo cách của Java; thao tác trên giá trị được kiểm tra nhiều hơn **trong khi chương trình chạy**. Python và JavaScript là ví dụ quen thuộc. Điều này không có nghĩa ngôn ngữ động “không có kiểu”: giá trị/đối tượng vẫn có kiểu và thao tác không hợp lệ vẫn có thể gây lỗi runtime.

| Tiêu chí | Java (kiểu tĩnh) | Python/JavaScript (kiểu động, mô tả tổng quát) |
|---|---|---|
| Kiểm tra trước khi chạy | Trình biên dịch kiểm tra kiểu của nhiều biểu thức, phép gán và lời gọi | Nhiều lỗi do dùng kiểu không phù hợp chỉ lộ ra khi nhánh mã được thực thi |
| Gán lại biến | Biến local có kiểu xác định; giá trị mới phải tương thích với kiểu đó | Một tên biến có thể được gán lần lượt các giá trị khác kiểu |
| Đa hình | Có, ví dụ biến interface tham chiếu implementation khác nhau | Có thể đạt đa hình bằng nhiều cơ chế của từng ngôn ngữ |
| Lỗi runtime | Vẫn có: `ClassCastException`, `ArrayStoreException`, input không hợp lệ... | Vẫn có lỗi khi thao tác với giá trị không được hỗ trợ |
| Ví dụ công cụ | `javac` kiểm tra kiểu khi biên dịch | Có thể dùng type checker/linter bổ sung, nhưng chính sách tùy hệ sinh thái |

So sánh cú pháp ngắn:

~~~java
// Java: kiểu của biến được xác định tại compile time.
Object value = "hello";
value = 123; // Hợp lệ vì cả String và Integer đều là Object.

// String name = "hello";
// name = 123; // LỖI BIÊN DỊCH: không gán int cho String.
~~~

~~~python
# Python: tên value lần lượt trỏ tới các giá trị khác kiểu.
value = "hello"
value = 123
# Một thao tác không được đối tượng hỗ trợ có thể báo lỗi khi chạy.
~~~

Việc Java cho phép `Object value` lần lượt chứa `String` rồi `Integer` **không biến Java thành ngôn ngữ kiểu động**. Kiểu **của biến** vẫn là `Object`; các phép toán trên biến vẫn bị giới hạn theo API của `Object` cho tới khi có một bước kiểm tra hoặc chuyển kiểu hợp lệ.

**Cần tránh kết luận quá mức:** “Kiểu tĩnh” không đồng nghĩa tuyệt đối “mọi lỗi kiểu đều phát hiện ở compile time”; “kiểu động” cũng không đồng nghĩa “mọi lỗi chỉ phát hiện ở runtime”. Công cụ phân tích, annotation, hệ thống kiểu tùy chọn và kiểm tra runtime có thể kết hợp theo nhiều cách.

## 3. Luồng từ nguồn Java đến runtime

~~~mermaid
flowchart TD
    A["Mã nguồn .java"] --> B["javac: phân tích cú pháp, tên và kiểu"]
    B --> C{"Ràng buộc kiểu tĩnh hợp lệ?"}
    C -->|Không| D["Lỗi biên dịch: không sinh chương trình hợp lệ"]
    C -->|Có| E["Bytecode .class"]
    E --> F["JVM tải và xác minh bytecode"]
    F --> G["Chạy chương trình"]
    G --> H["Runtime checks: cast, array store, input..."]
    G --> I["Dynamic dispatch: chọn implementation override"]
    H --> J["Kết quả hoặc lỗi runtime"]
    I --> J
~~~

Java compiler không chỉ “xem có method trùng tên hay không”; nó còn dùng kiểu biểu thức, khả năng truy cập, overload resolution, subtype, generic constraints và những quy tắc khác để quyết định chương trình hợp lệ.

JVM có quá trình **bytecode verification** nhằm kiểm tra các ràng buộc an toàn của bytecode đã nạp. Cơ chế này không thay thế việc xác thực dữ liệu nghiệp vụ, quyền truy cập hay logic của ứng dụng. Runtime vẫn cần giải quyết kiểu thực tế của object và kiểm tra các phép cast phù hợp.

## 4. Kiểu tĩnh của biến và kiểu động của đối tượng

Xét hai class cùng triển khai một interface:

~~~java
interface Message {
    String render();
}

final class EmailMessage implements Message {
    @Override
    public String render() {
        return "[EMAIL] Thông báo đơn hàng";
    }

    public String addressDomain() {
        return "example.com";
    }
}

final class SmsMessage implements Message {
    @Override
    public String render() {
        return "[SMS] Thông báo đơn hàng";
    }
}
~~~

Đoạn này khai báo:

~~~java
Message msg = new EmailMessage();
~~~

- **Kiểu tĩnh của biểu thức biến `msg`**: `Message`. Compiler cho phép gọi `msg.render()` vì `Message` có phương thức đó.
- **Lớp thực tế của đối tượng được tham chiếu lúc này**: `EmailMessage`. JVM sẽ chạy implementation `EmailMessage.render()`.
- `msg.addressDomain()` **không hợp lệ khi biên dịch**, vì interface `Message` không công bố phương thức `addressDomain()`, dù đối tượng thực tế có phương thức ấy.
- Khi gán `msg = new SmsMessage()`, **kiểu tĩnh của biến vẫn là `Message`**, còn đối tượng thực tế trở thành `SmsMessage`.

Các khái niệm liên quan:

| Khái niệm | Thời điểm xác định | Ví dụ |
|---|---|---|
| **Declared/static type của biến** | Compile time | `Message msg` |
| **Actual/runtime class của đối tượng** | Runtime | `new EmailMessage()` |
| **Subtype/polymorphism** | Quan hệ type được compiler kiểm tra, hành vi được thực thi khi chạy | `EmailMessage implements Message` |
| **Dynamic dispatch** | Runtime đối với lời gọi phương thức instance được override | `msg.render()` chạy `EmailMessage.render()` |
| **Downcast** | Phải được compiler chấp nhận về khả năng cast; cast tham chiếu được kiểm tra khi chạy | `(EmailMessage) msg` |

**Quan trọng:** Trong Java, đối tượng `new EmailMessage()` không “đổi class” thành `SmsMessage`. Chỉ là biến `msg` trỏ tới **đối tượng khác** sau phép gán. Với primitive như `int`, cũng không có đối tượng tham chiếu có runtime class theo mô hình trên.

## 5. Chương trình Java 17: compile-time checking, dynamic dispatch, cast và overload

Lưu đoạn dưới đây thành tệp **`TypeCheckingDemo.java`**. Có thể chạy trực tiếp với JDK 17 trở lên mà không cần thư viện ngoài.

~~~java
import java.util.ArrayList;
import java.util.List;

interface Notification {
    String format();
}

final class EmailNotification implements Notification {
    @Override
    public String format() {
        return "EMAIL: đơn hàng đã được xác nhận";
    }

    public String channelSpecificInfo() {
        return "SMTP";
    }
}

final class SmsNotification implements Notification {
    @Override
    public String format() {
        return "SMS: đơn hàng đã được xác nhận";
    }
}

public class TypeCheckingDemo {
    static String describe(Object input) {
        return "overload(Object)";
    }

    static String describe(String input) {
        return "overload(String)";
    }

    static void deliver(Notification notification) {
        // Instance method được dispatch theo object thực tế.
        System.out.println(notification.format());
    }

    public static void main(String[] args) {
        Notification notification = new EmailNotification();

        deliver(notification);
        System.out.println(
                "Runtime class: " + notification.getClass().getSimpleName());

        // Biên dịch sai vì declared type Notification không có method này:
        // notification.channelSpecificInfo();

        // Java 17: instanceof pattern matching vừa kiểm tra vừa bind biến.
        if (notification instanceof EmailNotification email) {
            System.out.println("Kênh đặc thù: "
                    + email.channelSpecificInfo());
        }

        notification = new SmsNotification();
        deliver(notification); // Cùng dòng gọi, implementation khác.

        Object value = "Java";
        System.out.println(describe(value));
        System.out.println(describe((String) value));

        Object untrusted = 42;
        if (untrusted instanceof String str) {
            System.out.println("Text: " + str);
        } else {
            System.out.println("Giá trị không phải String");
        }

        try {
            String bad = (String) untrusted; // Cast hợp lệ về cú pháp.
            System.out.println(bad);
        } catch (ClassCastException ex) {
            System.out.println("Cast sai ở runtime");
        }

        var count = 10; // Compiler suy luận int, không phải kiểu động.
        count = 11;
        // count = "mười"; // LỖI BIÊN DỊCH.

        List<String> codes = new ArrayList<>();
        codes.add("ORD-1");
        // codes.add(123); // LỖI BIÊN DỊCH do generic type.

        System.out.println("Code: " + codes.get(0));
    }
}
~~~

Chạy:

~~~bash
javac TypeCheckingDemo.java
java TypeCheckingDemo
~~~

Kết quả:

~~~text
EMAIL: đơn hàng đã được xác nhận
Runtime class: EmailNotification
Kênh đặc thù: SMTP
SMS: đơn hàng đã được xác nhận
overload(Object)
overload(String)
Giá trị không phải String
Cast sai ở runtime
Code: ORD-1
~~~

### 5.1. Vì sao `deliver(notification)` gọi đúng implementation?

Compiler xác nhận `notification` có static type `Notification` và interface ấy khai báo `format()`. Runtime chọn implementation đã override ứng với lớp thực tế: `EmailNotification.format()` hoặc `SmsNotification.format()`.

Đây là **đa hình động (runtime polymorphism)**. Nó tồn tại **bên trong Java statically typed**, nên không nên lấy dynamic dispatch làm bằng chứng “Java là ngôn ngữ kiểu động”.

### 5.2. Vì sao hai lời gọi `describe(...)` khác nhau?

Trong ví dụ:

~~~java
Object value = "Java";
System.out.println(describe(value));          // overload(Object)
System.out.println(describe((String) value)); // overload(String)
~~~

**Overloading** được giải quyết **theo kiểu biểu thức tại compile time**. Lời gọi `describe(value)` được chọn là `describe(Object)` vì kiểu tĩnh của `value` là `Object`; compiler không tự nhìn runtime object để chọn overload `String`.

Lời gọi `describe((String) value)` có một **biểu thức sau cast** mang kiểu tĩnh `String`, nên compiler chọn `describe(String)`. Bản thân cast tham chiếu vẫn được kiểm tra ở runtime.

**Overriding** thì khác: khi đã chọn chữ ký một phương thức instance thích hợp, JVM có thể chọn implementation override theo class thực tế lúc chạy. Phân biệt hai giai đoạn này để tránh kết quả “lạ” khi gặp overload kết hợp inheritance.

### 5.3. Kiểu của `var` có “động” không?

Không. Java `var` (từ Java 10) cho phép **suy luận kiểu cục bộ** (*local variable type inference*); nó không cho biến đổi sang kiểu không tương thích:

~~~java
var score = 100;       // int
score = 120;           // Đúng
// score = "cao";      // Sai compile time

var label = "READY";   // String
// label = false;      // Sai compile time
~~~

Hơn nữa, `var` không thay thế kiểu khai báo cho mọi vị trí:

~~~java
// int calculate(var value) { ... } // Không hợp lệ: var
// không dùng làm kiểu formal parameter của method thông thường.

// var field = 1; // Không hợp lệ cho field thông thường.
~~~

Một ngoại lệ về cú pháp là `var` có thể xuất hiện ở formal parameter của **lambda** trong một số trường hợp theo quy tắc ngôn ngữ; không nên nhầm với tham số của phương thức khai báo bình thường.

## 6. Kiểm tra kiểu tại compile time: phát hiện gì, bỏ sót gì?

Một số lỗi `javac` thường chặn được:

~~~java
String label = "READY";
// label = 42;        // Không thể gán int cho String.
// label.toUpperCase(1); // Sai danh sách tham số của method.

List<Integer> scores = new java.util.ArrayList<>();
scores.add(90);
// scores.add("A");   // Sai generic element type.

interface Printer { void print(); }
class ConsolePrinter implements Printer {
    public void print() { System.out.println("ok"); }
}
~~~

Nhiều ràng buộc Java được kiểm tra từ **khai báo, chữ ký, cách dùng generic, khả năng truy cập và subtype**. Tuy vậy, compiler không biết trước dữ liệu thực tế từ mạng, file, database, phản hồi HTTP hoặc user nhập vào.

| Trường hợp | Có thể chặn ở compile time? | Runtime cần làm gì? |
|---|---|---|
| Gán `String` vào `int` trực tiếp | Có | Không chạy được nếu vẫn còn lỗi |
| Gọi method không tồn tại trên static type | Có | Không chạy được nếu vẫn còn lỗi |
| Thêm `String` vào `List<Integer>` đúng kiểu khai báo | Có | Không chạy được nếu vẫn còn lỗi |
| Ép `Object` chứa `Integer` xuống `String` | Không thể biết chắc đối tượng thực tế | Cast bị kiểm tra, có thể ném `ClassCastException` |
| Ghi `Double` vào mảng thực tế là `Integer[]` qua tham chiếu `Number[]` | Compiler cho phép do array covariance | Có thể ném `ArrayStoreException` |
| Dữ liệu người dùng có định dạng email đúng | Không | Cần validation nghiệp vụ |
| `100 / divisor` khi `divisor` do runtime cung cấp | Không thể xác nhận mọi trường hợp | Có thể ném `ArithmeticException` nếu phép chia nguyên cho 0 |
| Class được nạp/khởi tạo qua reflection | Không chứng minh đầy đủ từ tên class runtime | Có thể cần kiểm tra `Class<?>` và xử lý reflection exceptions |

**Loại lỗi không phải một khái niệm duy nhất:** `NullPointerException`, `IndexOutOfBoundsException`, lỗi validation hoặc logic sai đều có thể xảy ra trong chương trình có kiểu tĩnh đúng. Không nên coi “biên dịch thành công” đồng nghĩa “chương trình chạy đúng”.

## 7. `instanceof`, pattern matching và cast an toàn

Khi nhận một giá trị có static type rộng như `Object`, hãy **kiểm tra kiểu thực tế** trước khi truy cập hành vi của subtype:

~~~java
static String describeValue(Object value) {
    if (value instanceof String text) {
        return "String: " + text.toUpperCase();
    }
    if (value instanceof Integer number) {
        return "Integer: " + number;
    }
    return "Other or null";
}
~~~

Đoạn trên dùng **pattern matching for `instanceof`** (có ở Java 17). Biến `text` chỉ được phép sử dụng tại những vị trí mà trình biên dịch xác định pattern đã match; đây là quy tắc **flow scoping**. `null instanceof String` trả `false`, nên nhánh cuối xử lý luôn `null`.

Đôi khi một downcast đã được xác thực bằng hợp đồng nghiệp vụ và có thể được viết tường minh, nhưng đừng “đoán” class để cast:

~~~java
Object incoming = Integer.valueOf(42);

// String text = (String) incoming;
// Compiler cho phép cast từ Object, nhưng runtime ném ClassCastException.

if (incoming instanceof Integer number) {
    System.out.println(number + 1);
}
~~~

Trong Java, toán tử cast có **nhiều mục đích khác nhau**. `(String) someObject` là cast kiểu tham chiếu và có thể bị kiểm tra runtime; `(int) 3.9` là chuyển đổi số nguyên thủy, cho kết quả `3` do quy tắc narrowing conversion, **không phải** `ClassCastException`. Không đánh đồng mọi phép cast.

### 7.1. Tránh lạm dụng `instanceof`

Nếu code liên tục làm:

~~~java
if (notification instanceof EmailNotification) {
    // xử lý email
} else if (notification instanceof SmsNotification) {
    // xử lý sms
}
~~~

trong khi interface đã có thao tác chung phù hợp, hãy để các class **override method** và gọi qua interface. `instanceof` nên được dùng khi thật sự cần **phân loại dữ liệu**, kiểm tra input không biết kiểu hoặc xử lý khả năng đặc biệt mà abstraction không thể biểu diễn hợp lý.

**Nguyên tắc thực tế:** Dùng interface và đa hình cho **hành vi chung**; dùng pattern matching/cast có kiểm soát ở **ranh giới dữ liệu không đồng nhất** hoặc nơi cần xử lý từng trường hợp riêng biệt.

## 8. Generics: compile time biết type argument, runtime cần xác thực dữ liệu ngoài

```java
List<String> codes = new ArrayList<>();
codes.add("ORD-1");
// codes.add(123); // Sai ngay khi biên dịch.
System.out.println(codes.get(0)); // ORD-1
```

Nhưng `ArrayList<String>` và `ArrayList<Integer>` dùng cùng runtime class; Java không cho kiểm tra `instanceof List<String>`, chỉ kiểm tra được `List<?>` và sau đó xác nhận phần tử nếu cần. Raw type hoặc unchecked cast có thể làm **heap pollution** và gây `ClassCastException` khi đọc.

Khi dữ liệu được nhận từ JSON/plugin/legacy API, đừng ép `(List<String>)` chỉ để compiler hết báo lỗi. Kiểm tra từng giá trị rồi tạo collection typed mới:

~~~java
static List<String> requireStrings(List<?> source) {
    Objects.requireNonNull(source);
    List<String> result = new ArrayList<>();
    for (Object item : source) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Expected String");
        }
        result.add(text);
    }
    return List.copyOf(result);
}
~~~

`null` cũng bị từ chối vì không match `String`. Danh sách mới không sửa được nhưng đó là **quyết định API**, không phải đặc tính của wildcard. Chi tiết variance/capture và erasure trong bài **Quan hệ kiểu của các cấu trúc tổng quát**; phần này nhấn mạnh **ranh giới từ kiểm tra kiểu tĩnh sang dữ liệu runtime không đáng tin**.

## 9. Reflection, JSON và dữ liệu không tin cậy: kiểm tra kiểu đến đâu?

Khi nhận `Object` từ một plugin, kết quả JSON được ánh xạ thành giá trị hoặc object được tạo qua reflection, kiểm tra kiểu ở compile time không thể xác nhận hết những gì runtime sẽ mang đến.

Ví dụ dùng `Class<T>` để kiểm tra class thực tế trước khi ép kiểu:

~~~java
final class TypedReaders {
    private TypedReaders() {}

    static <T> T requireType(Object input, Class<T> expected) {
        if (!expected.isInstance(input)) {
            throw new IllegalArgumentException(
                    "Expected " + expected.getSimpleName());
        }
        return expected.cast(input);
    }
}

// Ví dụ gọi:
String name = TypedReaders.requireType("Lan", String.class);
// TypedReaders.requireType(42, String.class) -> IllegalArgumentException.
~~~

`Class<T>.isInstance` và `Class<T>.cast` là API runtime type checking hữu ích. Tuy nhiên, `Class<List<String>>` không biểu diễn trực tiếp được bằng `List<String>.class`. Những framework JSON sử dụng *type token* / `Type` / `ParameterizedType` để biểu diễn cấu trúc generic có tham số và ánh xạ dữ liệu sâu hơn. **Không** giả định rằng `List.class` kiểm chứng được kiểu từng phần tử của `List<String>`.

Kiểm tra đúng class vẫn **chưa đủ để bảo đảm dữ liệu hợp lệ**. Chẳng hạn `String email` có type `String` nhưng có thể là `""`; `BigDecimal amount` có đúng type nhưng có thể âm; một object request được deserialize hợp lệ vẫn có thể vi phạm giới hạn nghiệp vụ. Cần phân biệt:

1. **Type checking**: giá trị có thuộc kiểu mong đợi hoặc thỏa quan hệ subtype?
2. **Validation**: giá trị có đúng ý nghĩa nghiệp vụ, format, khoảng giá trị và quyền truy cập?
3. **Business rules**: hành động có được phép ở trạng thái hiện tại hay không?

Không nên dùng cast để thay validation và cũng không cần tự kiểm tra `instanceof` tại mọi dòng nếu static type đã diễn đạt đúng hợp đồng.

## 10. Khái niệm thường bị đánh đồng

| Cặp khái niệm | Phân biệt đúng | Ví dụ |
|---|---|---|
| **Static typing vs dynamic typing** | Hệ thống xác định/kiểm tra kiểu biểu thức trước hay trong runtime, theo đặc trưng ngôn ngữ | Java vs Python |
| **Static type vs runtime class** | Kiểu biểu thức mà compiler biết vs class của object thực tế | `Notification n = new EmailNotification()` |
| **Type inference vs dynamic typing** | Compiler **suy luận một kiểu tĩnh** vs binding linh hoạt hơn khi chạy | `var x = 1` vẫn là `int` |
| **Overloading vs overriding** | Chọn chữ ký overload chủ yếu ở compile time vs chọn implementation của instance override ở runtime | `describe(Object)` / `describe(String)` vs `format()` |
| **Subtype vs cast** | Quan hệ kiểu bảo đảm một số phép gán vs phép chuyển kiểu tham chiếu cần kiểm tra | `EmailNotification` là `Notification`; `(EmailNotification) n` |
| **Type safety vs logic correctness** | Hạn chế thao tác sai kiểu vs bảo đảm kết quả nghiệp vụ đúng | `List<String>` không ngăn gửi email trống |
| **Generic type vs runtime generic check** | Compiler có thể bảo đảm quan hệ kiểu; runtime erasure không giữ mọi type argument | `List<String>`, `instanceof List<?>` |
| **Static method vs dynamically dispatched instance method** | Phương thức static được ẩn (hiding), không override đa hình | `Parent.print()` vs `child.render()` |

### Static member hiding không phải dynamic dispatch

Đây là một ví dụ nhỏ chạy được trong method bất kỳ có hai class sau:

~~~java
class Parent {
    static String category() { return "Parent"; }
    String name() { return "Parent"; }
}

class Child extends Parent {
    static String category() { return "Child"; } // method hiding
    @Override
    String name() { return "Child"; }             // overriding
}

Parent item = new Child();

System.out.println(item.category()); // Parent: theo static type Parent.
System.out.println(item.name());     // Child: dispatch theo object.
~~~

Java cho phép cú pháp gọi static method qua biến, nhưng **nên** gọi rõ `Parent.category()` hoặc `Child.category()` để tránh hiểu nhầm đó là polymorphism. Field cùng tên giữa cha và con cũng **bị ẩn**, không override như instance method.

## 11. Trường hợp Java biên dịch được nhưng vẫn sai runtime

Bảng này giúp chọn cách phòng ngừa đúng thay vì chỉ thêm cast:

| Hiện tượng | Ví dụ nguyên nhân | Biện pháp |
|---|---|---|
| `ClassCastException` | Downcast `Object` sai subtype | Dùng interface chung hoặc `instanceof`/`Class.cast` có kiểm tra |
| `ArrayStoreException` | Ghi sai runtime component type của array covariant | Ưu tiên generic collection khi phù hợp; tránh gán mảng subtype cho biến supertype rồi ghi |
| `NullPointerException` | Dùng tham chiếu null như object hợp lệ | Thiết kế null policy, `Objects.requireNonNull` ở boundary, mô hình hóa optional nếu thích hợp |
| `ArithmeticException` | Chia nguyên cho 0 hoặc phép toán số học không hợp lệ | Kiểm tra điều kiện toán học trước phép tính |
| `IndexOutOfBoundsException` | Chỉ số vượt kích thước mảng/list | Xác thực chỉ số hoặc dùng iteration an toàn |
| `IllegalArgumentException` | Đầu vào đúng Java type nhưng sai quy tắc nghiệp vụ | Validation ở boundary và test trường hợp biên |
| `NoSuchMethodException` / lỗi reflection khác | Tên member runtime không tồn tại hoặc không phù hợp | Hạn chế reflection tùy tiện; kiểm tra API và xử lý lỗi nạp động |

Static typing góp phần giảm những lỗi liên quan kiểu, nhưng không thay thế unit test, integration test, xử lý ngoại lệ và thiết kế hợp đồng rõ ràng.

## 12. Kiểm thử những ranh giới kiểu quan trọng

Các quy tắc compile-time nên được chứng minh bằng **ví dụ không biên dịch** (comment trong demo), tài liệu API hoặc compile-testing tools nếu cần xây dựng thư viện. JUnit thông thường không chạy được một chương trình mà `javac` đã từ chối.

Test runtime, ngược lại, có thể xác nhận kiểu đối tượng khác nhau vẫn đáp ứng cùng interface và kiểm tra đầu vào không biết kiểu. Ví dụ JUnit Jupiter 5, giả sử dùng các class từ `TypeCheckingDemo.java`, đặt test cùng package:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RuntimeTypingTest {
    @Test
    void interfaceReferenceCanHoldDifferentImplementations() {
        Notification notification = new EmailNotification();
        assertTrue(notification.format().startsWith("EMAIL:"));

        notification = new SmsNotification();
        assertTrue(notification.format().startsWith("SMS:"));
    }

    @Test
    void downcastIsCheckedByRuntime() {
        Object number = Integer.valueOf(42);

        assertFalse(number instanceof String);
        assertThrows(ClassCastException.class, () -> {
            String text = (String) number;
            System.out.println(text);
        });
    }

    @Test
    void checkedConversionRejectsOtherTypes() {
        assertEquals("Lan",
                TypedReaders.requireType("Lan", String.class));
        assertThrows(IllegalArgumentException.class,
                () -> TypedReaders.requireType(42, String.class));
    }
}
~~~

`TypedReaders` nằm ở ví dụ riêng trong phần reflection; để chạy test cuối, cần đưa class ấy vào cùng package của test. Các class khác đến từ demo. Thêm dependency `org.junit.jupiter:junit-jupiter` và cấu hình JUnit runner đúng dự án.

Một test `ClassCastException` chứng minh JVM kiểm tra cast tại runtime, **không** có nghĩa viết downcast sai là một cách thiết kế tốt. Trên đường xử lý chính, hãy giữ API theo interface/generic type đủ rõ để ít cần cast.

## 13. So sánh Java với TypeScript và Python

Java dùng hệ thống kiểu tĩnh với dynamic dispatch cho override. **TypeScript** kiểm tra shape/annotation khi biên dịch nhưng phần lớn kiểu bị xóa khi chạy JavaScript; `JSON.parse(...) as User` **không** xác minh object có đúng shape. **Python** mặc định kiểm tra nhiều thao tác khi chạy, dù công cụ như mypy/Pyright có thể dùng type hints để phát hiện sớm một số lỗi.

~~~typescript
type User = { id: number; name: string };
function displayUser(user: User) {
    console.log(user.name.toUpperCase());
}
// Giá trị từ JSON vẫn cần runtime validation trước khi gọi.
~~~

~~~python
value = 42
value = "forty-two"  # Một tên có thể lần lượt giữ giá trị khác kiểu.
print(value.upper())
~~~

So sánh này nhấn mạnh **thời điểm kiểm tra và hợp đồng runtime**, không xếp hạng ngôn ngữ nào luôn an toàn hơn. Bài **Khác biệt ngôn ngữ khi hiện thực cùng một thiết kế OOP** sẽ dùng một mô hình ShippingPolicy chạy qua Java/Kotlin/Python/TypeScript/C# để đối chiếu chi tiết.

## 14. Bài tập thực hành: xử lý thông báo hỗn hợp

Một API nhận dữ liệu đã được hệ thống khác chuyển thành `List<?>`; một số phần tử là `String`, một số là `Integer`, một số có thể là `null`. Bạn cần dựng các nhãn hiển thị.

**Yêu cầu:**

1. Viết `static List<String> labels(List<?> input)`.
2. Với `String` khác rỗng sau `trim()`, thêm `"TEXT: " + value`.
3. Với `Integer` không âm, thêm `"NUMBER: " + value`.
4. Với các phần tử khác hoặc null, ném `IllegalArgumentException` nêu vị trí phần tử.
5. Trả một danh sách không sửa đổi được; xử lý input `null` có chủ đích.
6. Viết test cho dữ liệu hợp lệ, số âm, chuỗi rỗng, phần tử null và kiểu bất ngờ.
7. Giải thích tại sao kiểu khai báo `List<?>` không thể bảo đảm tất cả phần tử đã là `String`, và vì sao ở đây `instanceof` là hợp lý hơn việc ép `(List<String>) input`.

Khung gợi ý:

~~~java
static java.util.List<String> labels(java.util.List<?> input) {
    java.util.Objects.requireNonNull(input, "input");

    java.util.List<String> result = new java.util.ArrayList<>();
    for (int i = 0; i < input.size(); i++) {
        Object value = input.get(i);

        if (value instanceof String text && !text.trim().isEmpty()) {
            result.add("TEXT: " + text.trim());
        } else if (value instanceof Integer number && number >= 0) {
            result.add("NUMBER: " + number);
        } else {
            throw new IllegalArgumentException(
                    "Invalid item at index " + i);
        }
    }
    return java.util.List.copyOf(result);
}
~~~

Khung trên cũng là một lời giải tham khảo. Hãy viết lại mà không dựa vào `instanceof` rải rác nhiều tầng: thực hiện phân loại tại boundary, chuyển về model có kiểu rõ ràng (ví dụ một `sealed interface` với hai record subtype) rồi xử lý model thống nhất ở lớp nghiệp vụ.

### Câu hỏi tự kiểm tra

1. Với `Message msg = new EmailMessage()`, kiểu của **biến** và class thực tế của **đối tượng** là gì?
2. Vì sao `var x = 10; x = "ten";` không biên dịch?
3. Vì sao `print(Object)` được chọn khi gọi `print(value)` dù runtime object là `String`?
4. Khác biệt giữa **overloading** và **overriding** về thời điểm quyết định là gì?
5. Vì sao `List<String>` và `List<Integer>` có thể dùng cùng runtime class mà compiler vẫn kiểm tra kiểu phần tử?
6. Khi nào `instanceof` là phương án kiểm tra boundary hợp lý, khi nào nó là dấu hiệu thiếu polymorphism?
7. Làm sao phân biệt lỗi **không đúng Java type**, lỗi **không đúng format dữ liệu**, và lỗi **vi phạm quy tắc nghiệp vụ**?

**Ghi nhớ:** Java kiểm tra kiểu **tĩnh** cho nhiều phép toán và lời gọi, nhưng tham chiếu interface có thể trỏ tới những object có **runtime class khác nhau**; overriding được phân giải động. `var` chỉ suy luận kiểu tĩnh. Những dữ liệu ngoài chương trình, cast, reflection, array covariance và ranh giới generics vẫn cần kiểm tra hoặc validation runtime. Thiết kế tốt là để compiler bảo vệ tối đa các quan hệ kiểu, còn runtime kiểm tra đúng những gì compiler không thể biết trước.