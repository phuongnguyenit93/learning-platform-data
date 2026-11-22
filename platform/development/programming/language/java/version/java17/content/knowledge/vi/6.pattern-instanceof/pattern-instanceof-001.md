# Bài toán kiểm tra kiểu rồi ép kiểu lặp lại: Pattern Matching for `instanceof` trong Java 17

Trong code Java xử lý đối tượng có kiểu tổng quát như `Object`, một interface hoặc một lớp cha, lập trình viên thường phải làm hai việc liên tiếp: **kiểm tra đối tượng thuộc kiểu cụ thể nào** bằng `instanceof`, sau đó **ép kiểu** để gọi các phương thức của kiểu đó. Trước khi có *pattern matching for `instanceof`*, cách viết này dễ tạo ra nhiều dòng lặp lại và có thể gây lỗi khi kiểm tra một kiểu nhưng ép sang kiểu khác.

Từ Java 16, **type pattern cho `instanceof` đã là tính năng chính thức** (JEP 394), vì vậy **Java 17 sử dụng trực tiếp, không cần bật preview**. Thay vì kiểm tra xong rồi tự khai báo một biến đã ép kiểu, ta viết kiểm tra và khai báo biến ngay trong cùng một biểu thức:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Trong câu lệnh đó:

- `value` là biểu thức cần kiểm tra.
- `String` là kiểu muốn kiểm tra.
- `text` là **pattern variable**, chỉ được sử dụng tại những vị trí mà compiler biết pattern đã khớp.
- Khi `value` thực sự là một `String`, biến `text` tham chiếu đến đối tượng đó dưới kiểu tĩnh `String`. Không cần viết `(String) value` một lần nữa.

Bài học đi từ vấn đề *kiểm tra kiểu rồi ép kiểu lặp lại* đến cú pháp Java 17, cách hiểu phạm vi biến theo luồng điều khiển, giới hạn kiểu và cách áp dụng trong code thực tế.

## 1. Vấn đề: `instanceof` rồi cast thủ công

Giả sử một API trả về `Object`, vì kết quả có thể là chuỗi, số hoặc một loại dữ liệu khác. Muốn xử lý riêng từng trường hợp, trước đây ta thường viết:

```java
public class BeforePattern {
    static String describe(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "Chuỗi dài " + text.length() + " ký tự";
        }

        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "Số gấp đôi: " + (number * 2);
        }

        return "Loại dữ liệu khác";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java 17"));
        System.out.println(describe(12));
    }
}
```

Khi đọc từng nhánh, ta thấy ba thao tác luôn đi cùng nhau:

1. Kiểm tra kiểu bằng `value instanceof String`.
2. Lặp lại tên kiểu trong `(String) value`.
3. Gán kết quả cast cho biến địa phương `text`.

Đây là chỗ dễ phát sinh vấn đề:

| Vấn đề của mẫu cũ | Hệ quả |
| --- | --- |
| Viết tên kiểu hai lần. | Code dài hơn và phải chỉnh sửa đồng bộ nếu thay đổi kiểu. |
| Lặp lại biểu thức nguồn. | Dễ vô tình cast một biểu thức khác với biểu thức vừa kiểm tra. |
| Cast thủ công không khớp với điều kiện. | Có thể gặp `ClassCastException` khi chạy. |
| Nhiều nhánh tương tự. | Phần kiểm tra và boilerplate che mất logic nghiệp vụ. |

Chẳng hạn, đây là lỗi lập trình chứ không phải lỗi của `instanceof`:

```java
if (value instanceof String) {
    // Sai: đã kiểm tra String nhưng lại cast sang Integer.
    Integer number = (Integer) value;
}
```

Compiler có thể cho phép cast từ `Object` sang `Integer` về mặt cú pháp, nhưng khi `value` thực tế là `String`, chương trình sẽ gặp `ClassCastException`. Pattern matching giảm cơ hội mắc lỗi này bằng cách ràng buộc **kiểu được kiểm tra và kiểu của biến sử dụng** trong cùng một cấu trúc.

## 2. Cách viết mới: Kiểm tra và gán biến trong một bước

Viết lại đúng chương trình trên bằng Java 17:

```java
public class AfterPattern {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "Chuỗi dài " + text.length() + " ký tự";
        }

        if (value instanceof Integer number) {
            return "Số gấp đôi: " + (number * 2);
        }

        return "Loại dữ liệu khác";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java 17"));
        System.out.println(describe(12));
    }
}
```

Kết quả:

```text
Chuỗi dài 7 ký tự
Số gấp đôi: 24
```

Điểm khác biệt là các biến `text`, `number` có **kiểu cụ thể sẵn**. Compiler kiểm tra biểu thức `instanceof`; nếu pattern khớp, nó cung cấp biến đúng kiểu trong phạm vi có thể sử dụng an toàn.

So sánh trực tiếp:

| Cách truyền thống | Pattern matching trong Java 17 |
| --- | --- |
| `if (obj instanceof String) { String s = (String) obj; ... }` | `if (obj instanceof String s) { ... }` |
| Kiểm tra kiểu rồi tự cast. | Kiểm tra và khai báo biến đúng kiểu cùng lúc. |
| Phải lặp `String` và `obj`. | Không cần lặp phép cast. |
| Biến `s` do lập trình viên tự khai báo trong block. | Biến pattern được compiler cho phép sử dụng ở những vị trí đã khớp. |

**Điều không đổi:** `instanceof` vẫn kiểm tra kiểu của đối tượng tại runtime; pattern matching **không làm mất tính đa hình, không chuyển đổi giá trị sang kiểu khác và không tự sửa thiết kế dữ liệu**. Nó làm cách viết type check + cast rõ ràng và an toàn hơn.

## 3. `instanceof Type variable` hoạt động như thế nào?

Với biểu thức:

```java
Object payload = "hello";

if (payload instanceof String message) {
    System.out.println(message.toUpperCase());
}
```

Ta có thể đọc là: “Nếu `payload` là một đối tượng `String`, đặt tên biến cho đối tượng đó là `message`, rồi chạy nhánh `if`.”

### 3.1. Đây là kiểm tra kiểu, không phải chuyển đổi dữ liệu

Nếu `payload` giữ một `Integer`, phép kiểm tra `payload instanceof String message` trả về `false`; Java không thử chuyển số thành chuỗi:

```java
Object payload = 42;

if (payload instanceof String message) {
    // Không chạy.
    System.out.println(message);
} else {
    System.out.println("Không phải String");
}
```

Để **chuyển đổi dữ liệu** như số sang chuỗi, dùng API thích hợp, chẳng hạn `String.valueOf(payload)`. Để **kiểm tra subtype**, dùng `instanceof`.

### 3.2. Pattern biến không phải đối tượng mới

`message` tham chiếu tới **chính đối tượng** mà `payload` đang giữ. Không có hàm tạo `String` được gọi và không phải một bản sao dữ liệu. Lợi ích chính là **kiểu tĩnh được thu hẹp trong luồng điều khiển**: bên trong nhánh hợp lệ, có thể gọi `String.length()` mà không cần cast.

### 3.3. `null` không khớp type pattern

```java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không khớp kiểu String");
}
```

Đoạn code in “Không khớp kiểu String”. Tương tự `instanceof` thông thường, biểu thức `null instanceof String` cho kết quả `false`. Nhánh khớp pattern không nhận đối tượng `null`, nên không cần thêm `text != null` chỉ để tránh trường hợp đó.

Tuy nhiên, **biểu thức được đánh giá để lấy đối tượng vẫn có thể ném ngoại lệ**: `service.read() instanceof String s` không bảo đảm `service.read()` tự nó không lỗi. Việc kiểm tra `instanceof` chỉ xử lý kết quả nếu biểu thức đã thực thi thành công.

## 4. Phạm vi của pattern variable: Biến chỉ xuất hiện khi chắc chắn khớp

Điểm khác biệt đáng học nhất so với khai báo biến thông thường là **flow scoping**: compiler theo dõi luồng điều khiển để biết khi nào pattern chắc chắn đã khớp. Quy tắc chi tiết được định nghĩa trong Java Language Specification.

### 4.1. Trong nhánh `if` khớp kiểu

```java
static void printIfText(Object value) {
    if (value instanceof String text) {
        System.out.println(text.trim()); // Hợp lệ
    }

    // System.out.println(text); // Không hợp lệ
}
```

Sau toàn bộ `if`, không thể dùng `text`, vì chương trình có thể đã đi qua nhánh không khớp. Biến pattern **không mặc nhiên tồn tại trong toàn bộ phương thức**.

### 4.2. Dùng `else` với phủ định

```java
static void printIfText(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Không phải chuỗi");
    } else {
        System.out.println(text.trim()); // Hợp lệ
    }
}
```

Nhánh `else` ở đây đồng nghĩa với việc điều kiện `!(value instanceof String text)` là `false`, tức pattern đã khớp, nên `text` được sử dụng.

### 4.3. Guard clause: Kiểm tra lỗi rồi xử lý phần còn lại

Trong phương thức có kiểu trả về, nếu nhánh không khớp **thoát khỏi phương thức**, compiler biết mọi đường đi còn lại đều đã khớp:

```java
static int lengthOfText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }

    // Chỉ tới đây khi value đã khớp với String.
    return text.length();
}
```

Có thể sử dụng `return` để kết thúc sớm theo cùng nguyên tắc:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "";
    }
    return text.strip();
}
```

Đây là mẫu viết thuận tiện khi dữ liệu đầu vào phải thuộc một kiểu cụ thể. Nó tránh lồng nhiều tầng `if` và tránh viết cast thủ công.

### 4.4. Không thể dùng biến pattern nếu không chứng minh được đã khớp

```java
static void invalid(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }

    // Sai: value có thể không phải String.
    // System.out.println(text.toUpperCase());
}
```

Quy tắc không chỉ liên quan cặp ngoặc nhọn; nó phụ thuộc **đường đi có thể tới vị trí sử dụng**. Nhìn vào điều kiện và các nhánh `return`, `throw`, `else` thường đủ để giải thích vì sao compiler cho phép hoặc từ chối.

## 5. Kết hợp điều kiện với `&&` và `||`

Pattern matching gọn hơn đặc biệt khi sau khi kiểm tra kiểu, ta cần **kiểm tra thêm điều kiện trên dữ liệu đã thu hẹp kiểu**.

### 5.1. `&&`: Kiểm tra kiểu rồi sử dụng biến

```java
static boolean isValidUserName(Object input) {
    return input instanceof String name
            && !name.isBlank()
            && name.length() <= 30;
}
```

Java đánh giá `&&` từ trái sang phải và **ngừng khi một toán hạng là `false`**. Do đó, nếu tới `!name.isBlank()`, pattern `input instanceof String name` đã khớp. `name` có thể được dùng trong những toán hạng tiếp theo.

Mẫu cũ thường cần nhiều dòng:

```java
static boolean isValidUserNameOld(Object input) {
    if (!(input instanceof String)) {
        return false;
    }
    String name = (String) input;
    return !name.isBlank() && name.length() <= 30;
}
```

Hai cách đều diễn tả quy tắc xác thực, nhưng phiên bản Java 17 không cần dòng cast riêng.

### 5.2. `||`: Không thể dùng biến ở vế phải theo cách tương tự

```java
static boolean invalidCondition(Object input) {
    // Sai: nếu input không phải String, vế phải vẫn có thể được đánh giá.
    // return input instanceof String name || name.isBlank();
    return false;
}
```

Lý do: khi vế phải của `||` được đánh giá, vế trái phải là `false`; đó chính là trường hợp pattern **không khớp**, nên `name` không sẵn dùng.

Thường viết lại bằng `&&`:

```java
static boolean isNonBlankText(Object input) {
    return input instanceof String text && !text.isBlank();
}
```

Hoặc dùng phủ định kèm điều kiện trả về sớm:

```java
static String requireNonBlankText(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected non-blank text");
    }
    return text;
}
```

Ở biểu thức sau, `text.isBlank()` được đánh giá **chỉ khi** `!(input instanceof String text)` là `false`, nghĩa là pattern ban đầu đã khớp. Sự khác nhau giữa hai ví dụ cho thấy cần hiểu cả **phép phủ định** lẫn **short-circuit evaluation**.

### 5.3. Quy tắc nhớ nhanh

| Biểu thức | Có dùng được biến pattern ở phần sau? | Vì sao |
| --- | --- | --- |
| `obj instanceof String s && s.length() > 3` | Có | Vế phải của `&&` chỉ chạy khi pattern khớp. |
| `obj instanceof String s || s.isEmpty()` | Không | Vế phải của `||` chạy khi pattern không khớp. |
| `!(obj instanceof String s) || s.isEmpty()` | Có | Vế phải của `||` chỉ chạy khi phủ định là `false`, tức pattern khớp. |
| `if (!(obj instanceof String s)) return;` rồi dùng `s` | Có | Mọi đường đi tiếp tục đều đã khớp. |
| `if (obj instanceof String s) { ... }` rồi dùng `s` ngoài khối | Không | Có thể điều kiện `if` là `false`. |

## 6. Ứng dụng khi xử lý dữ liệu đa hình

Bài toán kiểm tra rồi ép kiểu thường xuất hiện khi:

- Đọc dữ liệu từ thư viện có API tổng quát trả về `Object`.
- Xử lý một interface có nhiều lớp triển khai, mỗi lớp có dữ liệu riêng.
- Làm việc với hàng đợi thông điệp, sự kiện hoặc kết quả được biểu diễn bởi nhiều subtype.
- Duy trì mã cũ có nhiều nhánh `instanceof` và cast lặp lại.

Ví dụ sau mô tả một bộ định dạng thông báo. Ta có hai biến thể với dữ liệu khác nhau:

```java
interface Notice {}

record EmailNotice(String address, String subject)
        implements Notice {}

record SmsNotice(String phoneNumber, String body)
        implements Notice {}

public class NoticeDemo {
    static String format(Notice notice) {
        if (notice instanceof EmailNotice email) {
            return "Email tới " + email.address()
                    + ": " + email.subject();
        }

        if (notice instanceof SmsNotice sms) {
            return "SMS tới " + sms.phoneNumber()
                    + ": " + sms.body();
        }

        throw new IllegalArgumentException("Unsupported notice: " + notice);
    }

    public static void main(String[] args) {
        Notice first = new EmailNotice("team@example.org", "Java 17");
        Notice second = new SmsNotice("+84123456789", "Đã gửi");

        System.out.println(format(first));
        System.out.println(format(second));
    }
}
```

Lưu vào **`NoticeDemo.java`** rồi thực hiện:

```bash
javac --release 17 NoticeDemo.java
java NoticeDemo
```

Ví dụ có đầu ra:

```text
Email tới team@example.org: Java 17
SMS tới +84123456789: Đã gửi
```

Nếu không có pattern matching, mỗi nhánh phải viết thêm:

```java
if (notice instanceof EmailNotice) {
    EmailNotice email = (EmailNotice) notice;
    // ...
}
```

Với pattern, kiểu được kiểm tra và biến được khai báo cùng chỗ. Khi thêm xử lý cho `PushNotice`, lập trình viên chỉ cần viết một nhánh kiểu mới mà không tạo cặp kiểm tra/cast lặp lại.

**Giới hạn thiết kế:** ví dụ trên dùng interface thông thường; chương trình không thể suy ra rằng mã đã xử lý mọi implementation có thể tồn tại. Nếu việc bổ sung subtype thường xuyên xảy ra và mỗi subtype cần một hành vi riêng, việc đặt hành vi đa hình ngay trên interface hoặc lớp triển khai có thể hợp lý hơn một chuỗi `instanceof` dài. Pattern matching giải quyết tốt **cú pháp** của trường hợp kiểm tra subtype, nhưng không thay thế mọi phương án thiết kế hướng đối tượng.

## 7. Tận dụng mẫu type check + cast an toàn ở đầu phương thức

Khi một phương thức nhận một tham số tổng quát và chỉ xử lý một kiểu, có hai cách thường gặp:

### 7.1. Cast thủ công sau điều kiện

```java
static int wordCountOld(Object input) {
    if (!(input instanceof String)) {
        return 0;
    }

    String text = (String) input;
    if (text.isBlank()) {
        return 0;
    }
    return text.strip().split("\\s+").length;
}
```

### 7.2. Pattern biến với guard clause

```java
static int wordCount(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }

    if (text.isBlank()) {
        return 0;
    }
    return text.strip().split("\\s+").length;
}
```

Trong ví dụ này, logic đếm từ không đổi; chỉ bỏ đoạn ép kiểu thủ công. `String.isBlank()` và `strip()` có sẵn trong Java 17. Phần `split("\\s+")` là biểu thức chính quy cho chuỗi khoảng trắng; nó không phải một phần của pattern matching.

Một lựa chọn ngắn hơn:

```java
static int lengthIfText(Object input) {
    return input instanceof String text ? text.length() : 0;
}
```

Vế đúng của toán tử điều kiện `?:` chỉ được đánh giá khi pattern đã khớp. Tuy nhiên, nếu biểu thức phức tạp hoặc có nhiều nhánh, khối `if` thường dễ đọc hơn.

## 8. Các giới hạn kiểu cần biết

### 8.1. Kiểu kiểm tra phải phù hợp với kiểu tĩnh của biểu thức

Java chỉ chấp nhận phép kiểm tra có ý nghĩa theo các quy tắc chuyển đổi và kiểu của ngôn ngữ. Một điểm riêng với **type pattern**:

```java
Object value = "Hello";
if (value instanceof String text) { // Hợp lệ
    System.out.println(text.length());
}
```

Trong khi đó:

```java
String value = "Hello";

// Không hợp lệ trong Java 17:
// if (value instanceof String text) { ... }
```

Ở ví dụ thứ hai, **kiểu tĩnh của `value` đã là `String`**, tức là một subtype của kiểu pattern `String`. Đây là kiểm tra pattern dư thừa và compiler từ chối. Nếu đang có một biến `String`, dùng trực tiếp biến đó:

```java
String value = "Hello";
System.out.println(value.length());
```

Không thêm pattern matching chỉ vì muốn dùng tính năng mới. Công cụ có ích khi **kiểu tĩnh đang rộng hơn kiểu cần dùng**.

### 8.2. `instanceof` không kiểm tra đầy đủ generic type arguments

Do Java thực hiện type erasure, không thể viết type pattern với tham số kiểu không *reifiable* như `List<String>`:

```java
import java.util.List;

class GenericsExample {
    static void inspect(Object value) {
        // Sai: không thể kiểm tra List<String> theo cách này.
        // if (value instanceof List<String> strings) { ... }

        if (value instanceof List<?> elements) {
            for (Object element : elements) {
                if (element instanceof String text) {
                    System.out.println(text.toUpperCase());
                }
            }
        }
    }
}
```

`List<?>` là kiểu có thể kiểm tra theo cách này; các phần tử vẫn cần kiểm tra riêng nếu phải bảo đảm là `String`. Đừng xem `instanceof List<?>` là bằng chứng mọi phần tử cùng một kiểu cụ thể.

### 8.3. Không có primitive pattern matching ở Java 17

```java
Object value = 10; // auto-box thành Integer

if (value instanceof Integer number) {
    int doubled = number * 2; // unboxing trong phép tính
    System.out.println(doubled);
}
```

Đối tượng `value` giữ một `Integer`, không phải một đối tượng primitive `int`. Với Java 17, type pattern cho `instanceof` dùng **kiểu tham chiếu** phù hợp, chẳng hạn `Integer`, `String` hoặc một interface. Không viết `value instanceof int number`.

### 8.4. Type pattern không phải record pattern

Với một record:

```java
record Point(int x, int y) {}

static int distanceSquared(Object value) {
    if (value instanceof Point point) {
        return point.x() * point.x() + point.y() * point.y();
    }
    return 0;
}
```

Java 17 cho phép `instanceof Point point` nhưng **không hỗ trợ cú pháp record pattern dùng để tách trực tiếp thành `x` và `y`** theo dạng `value instanceof Point(int x, int y)`. Chỉ nên dùng cú pháp thực sự tồn tại trong đặc tả Java 17, không sao chép ví dụ từ phiên bản JDK mới hơn.

### 8.5. Không nhầm với pattern matching trong `switch`

Java 17 hỗ trợ **switch expression** trên các kiểu thông thường và enum, nhưng **pattern matching cho `switch` là preview trong Java 17** (JEP 406):

```java
// Không phải cú pháp ổn định mặc định của Java 17:
// return switch (value) {
//     case String s -> s.length();
//     case Integer i -> i;
//     default -> 0;
// };
```

Để viết code Java 17 ổn định mà không dùng preview, chọn `if (value instanceof String s)` hoặc các kỹ thuật đa hình thích hợp. Pattern matching cho `instanceof` không cần `--enable-preview`.

## 9. Chỉ đánh giá biểu thức phức tạp một lần

Ngoài lặp phép cast, code cũ còn có nguy cơ **gọi lại biểu thức sinh dữ liệu**:

```java
// Tránh cách viết này:
// if (service.fetch() instanceof String) {
//     String text = (String) service.fetch();
// }
```

Hai lần `fetch()` có thể tốn tài nguyên, gây tác dụng phụ hoặc trả về các giá trị khác nhau. Cách rõ nghĩa:

```java
Object result = service.fetch();
if (result instanceof String text) {
    System.out.println(text);
}
```

Có thể viết `if (service.fetch() instanceof String text)` để đánh giá `fetch()` một lần ngay trong điều kiện, nhưng tách ra biến `result` sẽ thuận tiện hơn nếu cần log, kiểm tra ngoại lệ hoặc tái sử dụng kết quả.

**Lưu ý:** pattern matching giúp tránh cast lặp lại; nó không tự làm một API có side effect trở nên an toàn hay chỉ gọi một biểu thức nhiều lần trong toàn bộ phương thức. Lập trình viên vẫn phải quyết định khi nào đánh giá biểu thức.

## 10. Kiểm tra subtype theo thứ tự từ cụ thể đến tổng quát

Một đối tượng có thể đồng thời phù hợp với nhiều kiểu, ví dụ `String` vừa là `String` vừa triển khai `CharSequence`. Nếu kiểm tra kiểu rộng trước, nhánh sau có thể không bao giờ được chọn cho đối tượng đó:

```java
static String describe(Object input) {
    if (input instanceof String text) {
        return "String: " + text;
    }
    if (input instanceof CharSequence sequence) {
        return "CharSequence dài " + sequence.length();
    }
    return "Khác";
}
```

Đây là thứ tự hợp lý khi cần xử lý riêng `String`. Nếu đặt `CharSequence` trước, mọi `String` sẽ được bắt bởi nhánh tổng quát.

Không nên suy ra một thứ tự cho mọi bài toán. Nếu các kiểu kiểm tra không có quan hệ subtype hoặc mục tiêu nghiệp vụ khác nhau, hãy chọn thứ tự phản ánh ý nghĩa của từng nhánh. `instanceof` là kiểm tra **tương thích kiểu ở runtime**, không phải phép so sánh class chính xác tuyệt đối như `getClass() == String.class`.

## 11. Khi nên dùng pattern matching, khi nào nên thiết kế lại API?

Pattern matching cho `instanceof` đặc biệt phù hợp khi **không thể hoặc không nên thay đổi** cấu trúc kiểu đầu vào, chẳng hạn:

- API bên ngoài trả về một supertype và code của bạn chỉ cần xử lý vài subtype cụ thể.
- Cần nâng cấp đoạn mã cũ đang có nhiều cặp `instanceof` + cast.
- Cần kiểm tra trước khi truy cập trường hoặc phương thức chỉ xuất hiện ở một subtype.
- Cần viết điều kiện gác nhanh: `obj instanceof Type typed && typed.isValid()`.

Tuy nhiên, nếu hệ thống có hàng chục nhánh subtype trong nhiều dịch vụ, một chuỗi dài `if (x instanceof A a) ... else if (x instanceof B b) ...` có thể báo hiệu **thiếu hành vi đa hình**.

Ví dụ: nếu tất cả implementation của `Notice` đều phải tự biết cách hiển thị, ta có thể định nghĩa:

```java
interface Notice {
    String format();
}

record Email(String to, String subject) implements Notice {
    public String format() {
        return "Email tới " + to + ": " + subject;
    }
}

record Sms(String phone, String body) implements Notice {
    public String format() {
        return "SMS tới " + phone + ": " + body;
    }
}

class NoticeRenderer {
    static String render(Notice notice) {
        return notice.format();
    }
}
```

Khi có thể thay đổi thiết kế của toàn bộ họ kiểu, đa hình cho phép bỏ hoàn toàn việc kiểm tra/cast cho hành vi chung. Ngược lại, nếu bạn đang xử lý dữ liệu từ một API không kiểm soát hoặc cần chỉ thực hiện một thao tác đặc biệt với vài kiểu, type pattern là công cụ ngắn gọn và đúng mục đích.

Đừng đổi `instanceof` sang reflection (`getClass()` hoặc `Class.cast()`) chỉ để tránh cast thông thường. Reflection phục vụ các nhu cầu runtime khác; nó không đem lại lợi ích rõ ràng trong trường hợp type check + cast đơn giản mà Java 17 đã hỗ trợ trực tiếp.

## 12. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu và xử lý đúng trong Java 17 |
| --- | --- |
| Pattern variable luôn có phạm vi toàn bộ phương thức. | Phạm vi dựa trên **flow scoping**: chỉ sử dụng khi compiler chứng minh pattern đã khớp. |
| Kiểm tra `obj instanceof String s` rồi phải cast lại `(String) obj`. | Dùng luôn `s`; đó chính là mục tiêu của pattern matching. |
| `obj instanceof String s || s.isEmpty()` là hợp lệ. | Không; vế phải của `||` được đánh giá khi pattern không khớp. |
| `null` sẽ khớp type pattern do biến có kiểu tham chiếu. | Không; `null instanceof String s` cho `false`. |
| Pattern matching biến số thành chuỗi hoặc chuỗi thành số. | Không; nó kiểm tra runtime type và đặt tên cho đối tượng đã khớp. |
| Có thể dùng `List<String>` để kiểm tra mọi phần tử là `String`. | Không; các generic type arguments như vậy không kiểm tra được do type erasure. Dùng `List<?>` và kiểm tra phần tử. |
| Java 17 đã có mọi loại pattern mới nhất. | Java 17 có type pattern cho `instanceof`; record pattern và type-pattern `switch` theo các phiên bản đời sau không phải các tính năng ổn định mặc định ở Java 17. |
| `String s` có thể dùng `s instanceof String text` để khai báo lại một biến cùng kiểu. | Tránh pattern dư thừa: compiler Java 17 từ chối type pattern khi kiểu của biểu thức đã là subtype của pattern type. |
| Dùng pattern matching luôn làm ứng dụng nhanh hơn. | Lợi ích chính là tính rõ ràng và giảm lặp cast. Hiệu năng phải đo trong ngữ cảnh cụ thể, không suy ra chỉ từ cú pháp. |

## 13. Bài tập thực hành

### Bài tập 1 — Bỏ cast lặp lại

Chuyển đoạn code này sang Java 17 pattern matching mà vẫn giữ nguyên chức năng:

```java
static String classify(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "text(" + text.length() + ")";
    }

    if (value instanceof Long) {
        Long number = (Long) value;
        return "long(" + (number + 1) + ")";
    }

    return "other";
}
```

Yêu cầu: không dùng cast trong các nhánh sau khi kiểm tra kiểu; xử lý `null` giống code ban đầu.

### Bài tập 2 — Giải thích phạm vi biến

Xác định dòng nào hợp lệ và giải thích theo luồng điều khiển:

```java
static void check(Object input) {
    if (input instanceof String s && s.length() > 5) {
        System.out.println(s);
    }

    // System.out.println(s);

    if (!(input instanceof Integer n)) {
        return;
    }
    System.out.println(n + 10);
}
```

Gợi ý: câu lệnh `return` khiến những đường đi không khớp `Integer` đều kết thúc trước khi tới phép cộng.

### Bài tập 3 — Viết một guard clause

Viết hàm `static String normalizeId(Object input)`. Nếu `input` là một `String` không rỗng sau khi `strip()` thì trả về chuỗi đã loại bỏ khoảng trắng đầu/cuối; các trường hợp khác ném `IllegalArgumentException`. Hãy sử dụng pattern matching trong điều kiện, không dùng cast.

### Bài tập 4 — Xử lý danh sách không biết kiểu phần tử

Viết hàm nhận `Object`. Nếu đối tượng là `List<?>`, duyệt từng phần tử và chỉ in ra các phần tử là `String` theo chữ hoa. Nếu không phải danh sách thì không in gì. Không dùng `instanceof List<String>` và không cast sang `List<String>`.

### Bài tập 5 — Quyết định có cần `instanceof` hay không

Một ứng dụng có interface `Shape`, mỗi hình đều phải tính diện tích. So sánh:

- Viết một phương thức duy nhất với các nhánh `instanceof Circle`, `instanceof Rectangle`;
- Khai báo `double area()` trong `Shape` rồi cho từng implementation thực hiện.

Chọn phương án phù hợp nếu bạn có quyền sửa toàn bộ các kiểu hình và dự kiến thường xuyên thêm loại hình mới. Sau đó nêu tình huống mà `instanceof` pattern vẫn hữu ích.

## 14. Tài liệu chính thức

- **JEP 394 — Pattern Matching for `instanceof`:** <https://openjdk.org/jeps/394>. Giải thích động lực loại bỏ chuỗi kiểm tra rồi cast, flow scoping và trạng thái chính thức từ Java 16.
- **Java Language Specification, Java SE 17, §15.20.2 — The `instanceof` Operator:** <https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2>. Đặc tả cách kiểm tra kiểu và ý nghĩa của `instanceof`.
- **Java Language Specification, Java SE 17, §14.30 — Patterns:** <https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30>. Các khái niệm pattern trong ngôn ngữ.
- **Java Language Specification, Java SE 17, §6.3.1 — Scope of a Pattern Variable Declaration:** <https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1>. Giải thích phạm vi biến dựa trên luồng điều khiển.
- **JEP 406 — Pattern Matching for `switch` (Preview):** <https://openjdk.org/jeps/406>. Tham khảo để phân biệt tính năng preview trong Java 17 với pattern `instanceof` đã chính thức.
- **Java SE 17 API Documentation:** <https://docs.oracle.com/en/java/javase/17/docs/api/index.html>. Tra `String.isBlank()`, `String.strip()`, `List` và các API được dùng trong ví dụ.

Khi bắt gặp các đoạn code dạng **“`if (x instanceof T)` rồi `T value = (T) x`”**, có thể cân nhắc đổi thành **“`if (x instanceof T value)`”** để loại bỏ sự lặp lại. Điều quan trọng cần hiểu sâu hơn chính là **phạm vi sử dụng biến theo kết quả của điều kiện**: Java 17 chỉ cho dùng pattern variable trên những đường đi mà compiler xác định kiểu đã khớp.
