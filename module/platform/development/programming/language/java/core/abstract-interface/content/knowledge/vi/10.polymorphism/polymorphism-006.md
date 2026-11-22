# `instanceof`, pattern matching và kiểm tra trước khi ép kiểu trong Java

## 1. Bối cảnh: đa hình và nhu cầu kiểm tra kiểu

Trong Java, biến tham chiếu có thể mang kiểu cha (lớp hoặc interface), trong khi đối tượng thực tế thuộc một lớp con hoặc một lớp triển khai cụ thể. Đó là một cơ sở của **đa hình**:

~~~java
interface Animal {
    void makeSound();
}

final class Dog implements Animal {
    @Override
    public void makeSound() {
        System.out.println("Gâu");
    }

    public void fetch() {
        System.out.println("Nhặt bóng");
    }
}

// Trong một phương thức đang chạy:
Animal animal = new Dog();
animal.makeSound(); // Hợp lệ: phương thức thuộc hợp đồng Animal.
// animal.fetch();  // Không biên dịch: kiểu tham chiếu Animal không khai báo fetch().
~~~

`animal` có **kiểu tĩnh** `Animal` nhưng đối tượng thực tế là `Dog`. Để gọi `fetch()`, trình biên dịch cần biết biểu thức có kiểu `Dog`; lập trình viên có thể ép kiểu tham chiếu (downcast). Vấn đề là biến kiểu `Animal` cũng có thể tham chiếu đến một lớp triển khai khác, và ép kiểu sai sẽ ném `ClassCastException`.

Từ khóa **`instanceof`** cho phép kiểm tra đối tượng có tương thích với một kiểu tham chiếu tại thời điểm chạy hay không. Từ Java 16, **pattern matching for `instanceof`** là tính năng chính thức: có thể kiểm tra kiểu và khai báo biến đã thu hẹp kiểu trong cùng một biểu thức. Java 17 hỗ trợ ổn định cú pháp này.

Bài này tập trung vào kiểm tra kiểu runtime, cách ép kiểu an toàn, phạm vi biến pattern và các lỗi thường gặp. Những ví dụ có `main` được ghi rõ tên tệp để có thể biên dịch/chạy với Java 17+.

## 2. `instanceof` truyền thống

### 2.1. Cú pháp và ý nghĩa

~~~java
referenceExpression instanceof ReferenceType
~~~

Kết quả là `boolean`:

- `true` khi giá trị tham chiếu **khác `null`** và đối tượng tương thích với kiểu ở bên phải. Tương thích bao gồm chính lớp đó, lớp con của nó, hoặc lớp thực hiện interface được kiểm tra.
- `false` khi giá trị tham chiếu là `null`, hoặc đối tượng không thuộc kiểu cần kiểm tra.
- Trình biên dịch kiểm tra tính hợp lệ của phép thử: không phải mọi cặp kiểu tĩnh đều có khả năng chuyển đổi để kiểm tra. Các kiểu hoàn toàn không liên quan trong một trường hợp cụ thể có thể gây lỗi biên dịch ngay từ đầu.

Ví dụ độc lập:

~~~java
Object a = "Java";
Object b = Integer.valueOf(17);
Object c = null;

System.out.println(a instanceof String);       // true
System.out.println(a instanceof CharSequence); // true
System.out.println(a instanceof Integer);      // false
System.out.println(b instanceof Number);       // true
System.out.println(c instanceof Object);       // false
~~~

Với `a` là đối tượng `String`, phép thử `CharSequence` cũng đúng vì `String` thực hiện interface `CharSequence`. Với `c` bằng `null`, ngay cả `instanceof Object` cũng trả về `false`.

`instanceof` không kiểm tra “tên lớp có bằng nhau tuyệt đối không”. Chẳng hạn, `new java.util.ArrayList<String>() instanceof java.util.List` trả về `true` vì đối tượng thực hiện `List`.

### 2.2. Phép thử và phép ép kiểu là hai bước khác nhau

`instanceof` **chỉ kiểm tra**, không tự biến kiểu tĩnh của biến trong cú pháp cũ:

~~~java
Object value = "Xin chào";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

`(String) value` là **ép kiểu tường minh**. Việc kiểm tra trước đảm bảo đối tượng đang được tham chiếu có thể chuyển sang `String` tại nhánh đó. Nếu bỏ bước kiểm tra:

~~~java
Object value = Integer.valueOf(42);
String text = (String) value; // Biên dịch được; runtime ném ClassCastException.
~~~

Với downcast hợp lệ về mặt cú pháp nhưng đối tượng thực không tương thích, lỗi xảy ra **khi chạy**, không phải khi Java biên dịch.

Cần phân biệt thêm:

- **Upcast** từ lớp con lên lớp cha/interface thường là chuyển đổi mở rộng an toàn và không cần `instanceof`: `Animal a = new Dog();`.
- **Downcast** từ kiểu cha/interface về lớp con cần kiểm tra khi kiểu thực tế không được bảo đảm: `Dog d = (Dog) a;`.
- Ép kiểu tham chiếu `(Dog) null` cho kết quả `null`, bản thân phép cast này không ném `ClassCastException`; gọi phương thức trên kết quả `null` mới có thể ném `NullPointerException`.
- Nên kiểm tra và ép kiểu trên **cùng tham chiếu/giá trị đã ổn định**; nếu giữa hai thao tác bạn thay giá trị tham chiếu bằng một đối tượng khác, kết quả kiểm tra trước không còn bảo đảm phép ép kiểu sau.

## 3. Pattern matching for `instanceof` (Java 16+, dùng trên Java 17)

### 3.1. Cú pháp rút gọn

Cú pháp truyền thống:

~~~java
Object data = "Java 17";

if (data instanceof String) {
    String text = (String) data;
    System.out.println(text.toUpperCase());
}
~~~

Cú pháp pattern matching tương đương:

~~~java
Object data = "Java 17";

if (data instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Điểm mới là **`String text`**: `String` là kiểu cần so khớp, `text` là **pattern variable** chỉ được đưa vào phạm vi sử dụng khi phép thử bảo đảm phù hợp. Trong nhánh `if` thành công, `text` đã có kiểu `String`, nên không cần viết `(String) data`.

Pattern này là một **type pattern**, không phải cách tự động chuyển đổi mọi kiểu. Nó không tạo đối tượng mới; `text` tham chiếu chính đối tượng đang được kiểm tra.

**Không được nhầm với `switch` pattern matching**: ở Java 17, pattern matching cho `instanceof` là tính năng chính thức, còn pattern matching cho `switch` vẫn là tính năng preview và có cú pháp/quy tắc khác. Ví dụ bài này không cần bật `--enable-preview`.

### 3.2. Điều kiện kết hợp với `&&` (short-circuit)

Đây là tình huống thường gặp nhất:

~~~java
Object input = "OpenJDK";

if (input instanceof String text && text.length() >= 5) {
    System.out.println("Chuỗi dài: " + text);
}
~~~

Stdout:

~~~text
Chuỗi dài: OpenJDK
~~~

Toán tử `&&` chỉ đánh giá vế phải nếu vế trái là `true`. Vì vậy, khi chương trình chạy `text.length()` thì `text` chắc chắn đã được gán nhờ pattern ở vế trái. Đây là **flow scoping** (phạm vi biến phụ thuộc luồng điều khiển).

Sai:

~~~java
// if (input instanceof String text || text.isBlank()) {
//     // Không biên dịch: vế phải của || có thể chạy khi pattern không khớp.
// }
~~~

Với `||`, vế phải chỉ được xét khi vế trái **sai**, nên không thể bảo đảm `text` đã được gán. Có thể thay bằng hai nhánh riêng hoặc tổ chức lại điều kiện theo ý định. Không phải `||` tự thân bị cấm; lỗi ở đây là **dùng biến pattern ở nhánh không được bảo đảm**.

## 4. Phạm vi biến pattern: điều kiện và luồng thực thi

### 4.1. Trong nhánh `if`

~~~java
static void show(Object candidate) {
    if (candidate instanceof String text) {
        System.out.println(text.trim());
    } else {
        System.out.println("Không phải chuỗi");
    }

    // text không ở trong phạm vi dùng tại đây.
}
~~~

Biến `text` có thể dùng ở phần mà trình biên dịch chứng minh pattern đã khớp. Trong `else` và sau `if` thông thường, kiểm tra có thể đã thất bại nên không được dùng `text`.

### 4.2. Phủ định và early return

Nhờ phân tích luồng, Java có thể cho phép dùng biến pattern **sau** một `if` phủ định nếu nhánh không khớp luôn kết thúc:

~~~java
static void printUppercase(Object candidate) {
    if (!(candidate instanceof String text)) {
        System.out.println("Bỏ qua: không phải chuỗi");
        return;
    }

    System.out.println(text.toUpperCase());
}
~~~

Điểm mấu chốt: khi chương trình đi đến dòng cuối, nhánh pattern không khớp đã `return`, nên `text` chắc chắn tồn tại với kiểu `String`. Nếu nhánh đó không kết thúc luồng phù hợp, không thể suy luận tương tự.

### 4.3. Kết hợp phủ định, điều kiện và các biến khác

~~~java
static boolean hasValidName(Object candidate) {
    return candidate instanceof String name
            && !name.isBlank()
            && name.length() <= 30;
}
~~~

Các phép kiểm tra ở bên phải `&&` chỉ chạy khi pattern đã thành công; `null` trả về `false` ngay tại phép thử đầu tiên. Cách viết này giúp giảm ép kiểu lặp và tránh truy cập kiểu không phù hợp.

### 4.4. Pattern được khai báo ở đâu, không nên khai báo lại khi không cần

Một biến được giới thiệu bằng pattern có phạm vi do Java tính theo những nhánh mà pattern “chắc chắn khớp”. Không nên giả định biến pattern có phạm vi giống biến địa phương khai báo đầu khối. Nếu trình biên dịch báo biến chưa tồn tại hoặc có tên trùng với biến đang trong phạm vi, hãy đặt tên riêng cho pattern hoặc đổi cấu trúc điều kiện.

Ví dụ **cố tình sai**:

~~~java
// Object candidate = "Java";
// if (candidate instanceof String text) {
//     System.out.println(text);
// }
// System.out.println(text); // Lỗi: text không còn trong phạm vi được bảo đảm.
~~~

Một giới hạn riêng của type pattern: với trường hợp kiểu tĩnh đã là subtype của kiểu thử, khai báo pattern có thể bị trình biên dịch từ chối vì phép thử trở nên không cần thiết:

~~~java
// String value = "Java";
// if (value instanceof String text) { // Lỗi biên dịch: expression đã có kiểu String.
//     System.out.println(text);
// }
~~~

Khi biến đã có đúng kiểu, dùng trực tiếp biến đó. Quy tắc này áp dụng cho dạng khai báo **pattern variable**; đừng áp dụng máy móc cho mọi cú pháp `instanceof` truyền thống.

## 5. Ví dụ hoàn chỉnh với abstract class, interface và đa hình

Ví dụ sau dùng một lớp trừu tượng `Device`, hai lớp con `Phone`/`Printer` và interface `Rechargeable` để minh họa:

- Một biến kiểu cha có thể giữ nhiều loại đối tượng cụ thể.
- `instanceof` kiểm tra lớp con **hoặc** interface.
- Biến pattern giúp truy cập phương thức chuyên biệt của kiểu đã khớp.
- `&&` cho phép kiểm tra bổ sung sau khi kiểu đã được xác nhận.
- Kiểm tra `null` là nhánh riêng hữu ích khi muốn thông báo rõ ràng.
- Ép kiểu truyền thống vẫn hợp lệ khi được bảo vệ bởi `instanceof`.

Lưu toàn bộ mã vào tệp **`Main.java`**:

~~~java
interface Rechargeable {
    int batteryPercent();
}

abstract class Device {
    abstract String description();
}

final class Phone extends Device implements Rechargeable {
    private final int battery;

    Phone(int battery) {
        this.battery = battery;
    }

    @Override
    String description() {
        return "Điện thoại";
    }

    @Override
    public int batteryPercent() {
        return battery;
    }
}

final class Printer extends Device {
    private final int ink;

    Printer(int ink) {
        this.ink = ink;
    }

    @Override
    String description() {
        return "Máy in";
    }

    int inkLevel() {
        return ink;
    }
}

public class Main {
    static void printInfo(Device device) {
        if (device == null) {
            System.out.println("Không có thiết bị");
            return;
        }

        System.out.println(device.description());

        if (device instanceof Phone phone
                && phone.batteryPercent() >= 50) {
            System.out.println("Điện thoại đủ pin: "
                    + phone.batteryPercent() + "%");
        }

        if (device instanceof Rechargeable rechargeable) {
            System.out.println("Sạc được: "
                    + rechargeable.batteryPercent() + "%");
        }

        if (device instanceof Printer printer) {
            System.out.println("Mực: " + printer.inkLevel() + "%");
        }
    }

    public static void main(String[] args) {
        Device[] devices = {
                new Phone(70),
                new Printer(30),
                null
        };

        for (Device device : devices) {
            printInfo(device);
        }

        Device candidate = new Phone(70);

        // Cách truyền thống: kiểm tra rồi ép kiểu.
        if (candidate instanceof Phone) {
            Phone phone = (Phone) candidate;
            System.out.println("Ép kiểu truyền thống: "
                    + phone.batteryPercent() + "%");
        }
    }
}
~~~

Chạy trong thư mục chứa `Main.java` với JDK 17 trở lên:

~~~bash
javac Main.java
java Main
~~~

**Stdout chính xác:**

~~~text
Điện thoại
Điện thoại đủ pin: 70%
Sạc được: 70%
Máy in
Mực: 30%
Không có thiết bị
Ép kiểu truyền thống: 70%
~~~

Diễn giải cụ thể:

1. `Device[]` chứa `Phone`, `Printer` và `null`. Kiểu tĩnh của biến lặp `device` là `Device`.
2. `device.description()` là lời gọi đa hình: với `Phone` in “Điện thoại”, với `Printer` in “Máy in”.
3. `device instanceof Phone phone` khớp chỉ đối tượng `Phone` ở đây. `&&` bảo đảm `phone.batteryPercent()` được gọi an toàn; pin 70 đạt điều kiện từ 50 trở lên.
4. `device instanceof Rechargeable rechargeable` khớp `Phone` vì lớp này thực hiện `Rechargeable`, dù biểu thức đang có kiểu tĩnh `Device`.
5. `device instanceof Printer printer` khớp với `Printer` và cho phép gọi `inkLevel()` mà không cần cast tường minh.
6. `null` được xử lý bằng nhánh đầu của `printInfo` và không thực hiện các phép truy cập sau.
7. `candidate instanceof Phone` là cú pháp kiểm tra truyền thống; `(Phone) candidate` là cast sau khi kiểm tra. Với chính đối tượng này, phép cast thành công.

**Lưu ý thiết kế:** nếu toàn bộ client liên tục phải hỏi “đây là Phone hay Printer?” để quyết định hành vi chính của thiết bị, nên cân nhắc đưa hành vi chung vào lớp cha hoặc interface và dùng dispatch đa hình. `instanceof` hữu ích khi cần truy cập **khả năng tùy chọn** (`Rechargeable`), xử lý dữ liệu đầu vào chưa biết kiểu, hoặc tương tác với API không thể sửa.

## 6. Các tình huống đặc biệt khi dùng `instanceof`

### 6.1. `null` luôn không khớp

~~~java
Object object = null;
System.out.println(object instanceof String);
~~~

Kết quả là `false`. Vì vậy, dạng kiểm tra `if (obj instanceof String s)` đã bao gồm việc loại `null` cho nhánh thành công. Chỉ dùng `obj != null` riêng khi muốn xử lý `null` bằng thông báo hoặc nhánh độc lập.

### 6.2. Tính đến lớp con và interface

~~~java
Object value = new java.util.ArrayList<String>();

System.out.println(value instanceof java.util.ArrayList);
System.out.println(value instanceof java.util.List);
System.out.println(value instanceof java.util.Collection);
~~~

Cả ba dòng đều in `true`. `instanceof` không yêu cầu kiểu runtime bằng **đúng** kiểu bên phải; quan hệ kế thừa và thực hiện interface được tính đến. Trái lại, `obj.getClass() == SomeClass.class` so sánh lớp runtime chính xác; `getClass()` còn ném `NullPointerException` nếu `obj` là `null`. Hai cách kiểm tra phục vụ hai mục đích khác nhau.

### 6.3. Kiểu nguyên thủy

`instanceof` kiểm tra **kiểu tham chiếu**, không thể áp dụng trực tiếp lên biểu thức nguyên thủy:

~~~java
// int number = 7;
// boolean ok = number instanceof Integer; // Lỗi biên dịch.
~~~

Muốn kiểm tra kiểu của dữ liệu nhận qua `Object`, giá trị nguyên thủy phải được boxing thành đối tượng. Trong trường hợp đã biết chính xác kiểu nguyên thủy, phép kiểm tra kiểu runtime thường không có ý nghĩa.

### 6.4. Mảng

Mảng là đối tượng tham chiếu. Có thể kiểm tra chúng bằng `instanceof`:

~~~java
Object value = new String[] {"Java", "JVM"};

if (value instanceof String[] words) {
    System.out.println(words.length);
}
~~~

Output: `2`. Dạng pattern cho mảng giới thiệu biến `words` có kiểu `String[]`, nên có thể truy cập `length` hoặc phần tử mảng trong nhánh thành công.

### 6.5. Generic và type erasure

Không thể kiểm tra trực tiếp kiểu tham số cụ thể của một generic collection tại runtime vì **type erasure**:

~~~java
// Object value = java.util.List.of("Java");
// if (value instanceof java.util.List<String> names) { // Lỗi biên dịch.
//     System.out.println(names);
// }
~~~

Có thể kiểm tra kiểu **reifiable** như `List<?>`:

~~~java
Object value = java.util.List.of("Java", "JVM");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
~~~

Stdout: `2`. Phép thử cho biết đối tượng là `List`, **không xác nhận tất cả phần tử đều là `String`**. Nếu chương trình cần kiểm tra kiểu phần tử, phải xem xét từng phần tử và xử lý dữ liệu sai kiểu.

### 6.6. Phân biệt lỗi biên dịch với `ClassCastException`

Hai loại lỗi rất khác nhau:

- **Biên dịch từ chối:** phép so khớp/cast vô nghĩa theo quan hệ kiểu tĩnh mà Java có thể xác định; dùng pattern khi kiểu tĩnh đã là subtype của kiểu pattern; hoặc gọi biến pattern ở nhánh không được bảo đảm.
- **Runtime `ClassCastException`:** cú pháp cast được chấp nhận vì có thể tồn tại đối tượng tương thích, nhưng **đối tượng thực** không thuộc kiểu đích. Ví dụ ép một `Object` đang giữ `Integer` thành `String`.
- **Runtime `NullPointerException`:** nếu cast ra `null` rồi gọi phương thức instance trên đó. Bản thân `instanceof` đối với `null` chỉ cho `false`.

Đừng dùng `try/catch (ClassCastException)` như cách thay thế thường xuyên cho kiểm tra kiểu khi luồng chương trình có thể dự đoán trước. Kiểm tra bằng `instanceof` hoặc thiết kế đa hình rõ ràng dễ hiểu hơn trong các trường hợp thông thường.

## 7. Những lỗi và hiểu nhầm hay gặp

| Lỗi/hiểu nhầm | Vì sao chưa đúng | Cách làm đúng |
|---|---|---|
| Ép kiểu con ngay khi chỉ biết biến kiểu cha | Đối tượng thực tế có thể thuộc lớp con khác. | Kiểm tra `instanceof` trước, hoặc dùng phương thức đa hình từ kiểu cha. |
| Nghĩ `instanceof` thay đổi kiểu tĩnh của biến trong toàn phương thức | Phép thử cũ chỉ trả `boolean`; pattern variable có phạm vi theo luồng. | Dùng `if (x instanceof Type t)` và sử dụng `t` ở vùng hợp lệ. |
| Dùng biến pattern sau một `if` không bảo đảm đã khớp | Trình biên dịch không thể khẳng định biến tồn tại. | Dùng trong nhánh thành công hoặc theo nhánh early return đã chứng minh. |
| `if (x instanceof String s \|\| s.isBlank())` | Khi vế trái false, `s` chưa được gán. | Dùng `&&` khi điều kiện bổ sung cần `s`; nếu ý định khác, tách điều kiện. |
| Chỉ so sánh `getClass()` để tìm subtype/interface | `getClass()` xét lớp runtime chính xác, không tự bao hàm subtype. | Dùng `instanceof` nếu muốn chấp nhận lớp con/triển khai. |
| Giả định `null instanceof Object` trả `true` | `null` không phải một đối tượng cụ thể. | Xử lý `null` riêng nếu cần. |
| Viết `obj instanceof List<String> list` | Generic element type không được kiểm tra bằng `instanceof` sau type erasure. | Thử `List<?>`, sau đó kiểm tra phần tử nếu cần. |
| `int n = 3; n instanceof Integer` | Toán hạng trái là giá trị nguyên thủy. | Kiểm tra kiểu tham chiếu khi cần; không thử kiểu primitive theo cách này. |
| Dùng pattern matching của `switch` như tính năng Java 17 tiêu chuẩn | Trong Java 17, pattern `switch` vẫn preview. | Dùng `instanceof Type name` chính thức, không cần preview. |
| Dùng `instanceof` ở mọi nhánh xử lý đối tượng | Làm code phụ thuộc nhiều lớp con cụ thể và khó mở rộng. | Ưu tiên đa hình cho hành vi chung; dùng `instanceof` khi thật sự cần kiểm tra khả năng/kiểu cụ thể. |

## 8. Mẫu sử dụng thường gặp

### 8.1. Dữ liệu đầu vào chỉ có kiểu `Object`

~~~java
static String toDisplayText(Object value) {
    if (value instanceof String text) {
        return text.trim();
    }
    if (value instanceof Number number) {
        return "Số: " + number;
    }
    return value == null ? "(null)" : "(không hỗ trợ)";
}
~~~

Đây là **phương thức minh họa**, chưa phải chương trình độc lập. Chương trình có thể dùng `toDisplayText("  abc  ")` → `"abc"`, `toDisplayText(17)` → `"Số: 17"`, và `toDisplayText(null)` → `"(null)"`. Mỗi nhánh có tên biến pattern rõ ràng.

### 8.2. Kiểm tra khả năng thông qua interface

~~~java
interface CloseableResource {
    void close();
}

static void closeIfSupported(Object value) {
    if (value instanceof CloseableResource resource) {
        resource.close();
    }
}
~~~

Ở đây kiểm tra **khả năng** (`CloseableResource`) thay vì ép đối tượng thành một lớp triển khai cụ thể. Cách này bền vững hơn nếu về sau xuất hiện nhiều kiểu đối tượng cùng thực hiện interface.

### 8.3. Thoát sớm khi đầu vào sai kiểu

~~~java
static int textLengthOrZero(Object value) {
    if (!(value instanceof CharSequence text)) {
        return 0;
    }
    return text.length();
}
~~~

Phần sau `if` chỉ có thể thực thi khi đầu vào đã khớp `CharSequence`. Java cho phép sử dụng `text` ở lệnh `return` cuối. Kiểu `CharSequence` linh hoạt hơn `String` nếu logic chỉ cần `length()`.

## 9. Chọn giải pháp phù hợp

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Chỉ gọi hành vi chung mà lớp cha/interface đã khai báo | Gọi trực tiếp phương thức đa hình; không cần `instanceof`. |
| Cần kiểm tra một lớp con cụ thể trước khi dùng API riêng | `if (x instanceof Subtype sub) { ... }`. |
| Cần kiểm tra một khả năng tùy chọn | Pattern `instanceof SomeInterface capability`. |
| Cần kiểm tra kiểu và thêm điều kiện dựa trên đối tượng | `if (x instanceof Type value && value.isValid())`. |
| Muốn loại trường hợp không khớp ngay từ đầu | `if (!(x instanceof Type value)) return;`. |
| Đang bảo trì mã Java trước Java 16 | `if (x instanceof Type) { Type value = (Type) x; }`. |
| Cần phân biệt `null` với đối tượng không đúng kiểu | Xử lý `null` riêng trước khi kiểm tra pattern. |

### Câu hỏi tự kiểm tra

1. `instanceof` có trả về `true` đối với `null` không? — **Không, luôn `false`.**
2. `Object o = "abc"; if (o instanceof String s)` có cần viết thêm `(String) o` trong nhánh đúng không? — **Không; `s` đã có kiểu `String`.**
3. Vì sao `s.length()` dùng được sau `instanceof String s &&`? — Vì **`&&` chỉ đánh giá vế phải khi pattern đã khớp**.
4. Lớp con của `Animal` có làm `animal instanceof Animal` thành `true` không? — **Có**, nếu `animal` khác `null` và đối tượng thuộc hệ kiểu tương thích.
5. `instanceof List<String>` có kiểm tra toàn bộ generic argument không? — **Không; cú pháp này không hợp lệ trong phép thử như ví dụ**, dùng `List<?>` và kiểm tra phần tử nếu cần.
6. Có nên ép một tham chiếu kiểu cha xuống lớp con chỉ vì trước đó nó đã được khởi tạo từ lớp con hay không? — Chỉ khi **chắc chắn đối tượng được tham chiếu tại thời điểm ép kiểu** có kiểu tương thích; nếu chưa chắc, kiểm tra `instanceof`.

**Ghi nhớ:** `instanceof` trả lời “đối tượng hiện tại có tương thích với kiểu này không?”. Pattern matching `instanceof Type variable` vừa kiểm tra vừa tạo một biến đã thu hẹp kiểu tại những vị trí được bảo đảm bởi luồng điều khiển. Dùng nó để tránh cast lặp và `ClassCastException` khi cần xử lý kiểu cụ thể; dùng **đa hình** khi hành vi đã có trong hợp đồng chung.
