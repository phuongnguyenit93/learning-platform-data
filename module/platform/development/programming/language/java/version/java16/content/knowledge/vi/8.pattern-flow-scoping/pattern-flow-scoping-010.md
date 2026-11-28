# Pattern variable có thể gán lại và điều kiện effectively final khi capture

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Khi viết `value instanceof String text`, Java vừa kiểm tra kiểu runtime vừa tạo biến pattern `text` có kiểu tĩnh `String`. Theo JEP 394, pattern variable **không implicitly final**: sau khi pattern khớp, có thể gán lại biến này như một biến cục bộ thông thường.

Điều này liên quan trực tiếp đến việc capture biến trong lambda expression hoặc lớp lồng nhau. Java chỉ cho phép capture biến cục bộ nếu biến đó được khai báo `final` hoặc *effectively final*. Vì pattern variable có thể gán lại, nó chỉ capture được khi không bị gán lại sau khi được khớp và do đó vẫn effectively final. Flow scoping quyết định biến có nằm trong phạm vi tại vị trí lambda hay không; effectively final quyết định biến có đáp ứng điều kiện capture hay không.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này phân biệt việc gán lại pattern variable, điều kiện effectively final và cách capture an toàn trong lambda hoặc lớp lồng nhau. Các ví dụ sử dụng cú pháp đã được chuẩn hóa, không dựa vào tính năng thử nghiệm hoặc đã lỗi thời.

## 1. Pattern variable có thể gán lại

Khi pattern khớp, biến pattern được khởi tạo bằng giá trị đã kiểm tra. Sau đó, có thể gán một giá trị khác cùng kiểu cho biến:

```java
static void normalize(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip());

        text = "default"; // Hợp lệ: pattern variable có thể gán lại.
    }
}
```

`text` là biến cục bộ được khai báo bởi pattern. Từ thời điểm pattern khớp, biến có thể được gán lại như local variable thông thường. Việc gán `text` không thay đổi `value` ban đầu; nó chỉ thay đổi giá trị mà tên cục bộ `text` tham chiếu đến trong phần mã còn lại của phạm vi.

Nếu cần tạo một giá trị đã xử lý, hãy khai báo biến cục bộ khác:

```java
static String normalize(Object value) {
    if (value instanceof String text) {
        String normalized = text.strip();
        return normalized;
    }

    return "(empty)";
}
```

Ở đây `text` giữ giá trị đã khớp, còn `normalized` lưu kết quả xử lý riêng. Tạo biến mới thường giúp mã thể hiện rõ sự khác nhau giữa dữ liệu đầu vào và giá trị đã biến đổi; nếu không cần giữ giá trị gốc, có thể gán lại `text`.

## 2. Gán lại biến khác với thay đổi đối tượng

Khả năng gán lại biến và khả năng thay đổi đối tượng là hai việc khác nhau. Với một pattern variable tham chiếu đến đối tượng mutable, có thể gọi phương thức làm thay đổi đối tượng, đồng thời cũng có thể gán một tham chiếu mới cho biến:

```java
static void appendMarker(Object value) {
    if (value instanceof StringBuilder builder) {
        builder.append("!"); // Hợp lệ: thay đổi trạng thái của đối tượng.

        builder = new StringBuilder("new content"); // Cũng hợp lệ: gán lại biến pattern.
    }
}
```

`builder.append("!")` thay đổi trạng thái của đối tượng hiện tại. Câu lệnh `builder = new StringBuilder("new content")` thay tham chiếu mà biến cục bộ giữ. Cả hai đều hợp lệ vì pattern variable không implicitly final. Nếu biến được capture trong lambda, việc gán lại này sẽ làm nó không còn effectively final.

Vì vậy, cần phân biệt hai thao tác:

- **Gán lại biến:** thay tham chiếu mà biến trỏ đến. Pattern variable cho phép thao tác này.
- **Thay đổi đối tượng:** gọi phương thức làm thay đổi trạng thái nội bộ của đối tượng. Điều này phụ thuộc vào API và tính mutable của kiểu đối tượng.

## 3. Effectively final là gì?

Với biến cục bộ thông thường, Java cho phép capture trong lambda nếu biến được khai báo `final` hoặc là *effectively final*. Một biến effectively final không có modifier `final`, nhưng sau khi được khởi tạo hoặc được gán giá trị theo luồng xác định, nó không bị gán lại.

Ví dụ:

```java
static void printGreeting() {
    String greeting = "Xin chào";

    Runnable task = () -> System.out.println(greeting);
    task.run();
}
```

`greeting` không có từ khóa `final`, nhưng không bị gán lại sau khi khởi tạo. Vì vậy, nó effectively final và được phép capture trong lambda.

Một biến không nhất thiết phải được khởi tạo ngay tại dòng khai báo mới có thể effectively final. Nếu mọi nhánh đều gán giá trị đúng một lần trước khi sử dụng và không có phép gán lại sau đó, biến vẫn có thể được capture:

```java
static Runnable greetingTask(boolean morning) {
    String greeting;

    if (morning) {
        greeting = "Chào buổi sáng";
    } else {
        greeting = "Chào buổi chiều";
    }

    return () -> System.out.println(greeting);
}
```

Ở mỗi đường đi, `greeting` được gán một giá trị trước khi lambda được tạo và không bị thay đổi sau đó. Compiler có thể xác định biến effectively final.

## 4. Gán lại khiến biến thường không còn effectively final

Nếu biến cục bộ được gán lại sau khi khởi tạo, nó không còn effectively final và không thể capture trong lambda:

```java
static void printGreeting() {
    String greeting = "Xin chào";
    greeting = "Chào bạn";

    Runnable task = () -> System.out.println(greeting);
    // Lỗi biên dịch: greeting không còn effectively final.
}
```

Nếu cần tạo lambda dùng một giá trị ổn định, hãy chốt giá trị trước khi tạo lambda:

```java
static void printGreeting() {
    String greeting = "Xin chào";
    greeting = "Chào bạn";

    String capturedGreeting = greeting;
    Runnable task = () -> System.out.println(capturedGreeting);
    task.run();
}
```

`capturedGreeting` không bị gán lại sau khi khởi tạo nên effectively final. Lambda capture biến này thay vì capture biến `greeting` có thể thay đổi. Tính effectively final được xác định cho toàn bộ phạm vi liên quan: dù phép gán lại xuất hiện trước hay sau dòng tạo lambda, biến vẫn không đủ điều kiện capture.

## 5. Capture pattern variable trong lambda

Pattern variable có thể được capture trực tiếp trong lambda nếu nó đang nằm trong phạm vi và không bị gán lại:

```java
import java.util.function.Function;

static void format(Object value) {
    if (value instanceof String text) {
        Function<String, String> addSuffix = suffix -> text + suffix;

        System.out.println(addSuffix.apply("!"));
    }
}
```

Khi điều kiện `instanceof` đúng, `text` được tạo và nằm trong phạm vi thân `if`. Trong ví dụ này `text` không bị gán lại, nên effectively final và lambda `addSuffix` có thể capture trực tiếp. Không cần khai báo biến `final` trung gian chỉ để đáp ứng yêu cầu capture.

Nếu gán lại pattern variable trước khi tạo lambda, biến không còn effectively final:

```java
import java.util.function.Supplier;

static Supplier<String> invalidSupplier(Object value) {
    if (value instanceof String text) {
        text = text.strip();
        return () -> text; // Lỗi biên dịch: text đã bị gán lại.
    }

    return () -> "";
}
```

Để vừa chuẩn hóa vừa capture, hãy tạo biến dẫn xuất không bị gán lại:

```java
import java.util.function.Supplier;

static Supplier<String> normalizedSupplierAfterReassignment(Object value) {
    if (value instanceof String text) {
        text = text.strip();
        String capturedText = text;
        return () -> capturedText;
    }

    return () -> "";
}
```

`text` được phép gán lại, còn `capturedText` không bị gán lại nên effectively final và có thể capture.

Lambda cũng có thể được trả về để thực thi sau khi phương thức tạo nó đã kết thúc:

```java
import java.util.function.Supplier;

static Supplier<String> supplierFor(Object value) {
    if (value instanceof String text) {
        return () -> text.strip();
    }

    return () -> "(not a string)";
}
```

Lambda trong nhánh đầu capture `text` đã được xác nhận. Vì không có phép gán lại, biến effectively final và việc capture hợp lệ. Việc gọi `get()` sau đó vẫn sử dụng được giá trị được capture, dù thân `if` đã kết thúc.

## 6. Capture pattern variable sau guard clause

Flow scoping có thể đưa pattern variable ra sau câu lệnh `if` nếu nhánh không khớp kết thúc bằng `return` hoặc `throw`. Vì biến vẫn nằm trong phạm vi sau guard, có thể capture nó ở phần tiếp theo nếu không gán lại biến:

```java
import java.util.function.Supplier;

static Supplier<String> requireSupplier(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("value phải là String");
    }

    return () -> text.strip();
}
```

Nếu pattern không khớp, phương thức ném ngoại lệ và không tạo lambda. Nếu phương thức đi đến câu lệnh `return`, pattern chắc chắn đã khớp; `text` nằm trong phạm vi và có thể được capture.

Điều kiện capture có hai phần cần thỏa mãn:

1. **Phạm vi:** biến phải được phép sử dụng tại vị trí lambda được khai báo. Flow scoping xác định điều này với pattern variable.
2. **Tính effectively final:** biến phải là `final` hoặc không bị gán lại sau khi được khởi tạo. Pattern variable không implicitly final, vì vậy cần kiểm tra xem có phép gán lại nào trước hoặc sau vị trí capture hay không.

## 7. Capture trong anonymous class

Quy tắc capture cũng áp dụng cho lớp lồng cục bộ hoặc anonymous class. Ví dụ dùng `Runnable`:

```java
static Runnable createTask(Object value) {
    if (value instanceof String text) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(text.strip());
            }
        };
    }

    return () -> System.out.println("Không phải chuỗi");
}
```

Anonymous class sử dụng `text` từ phạm vi bên ngoài. Vì `text` vẫn nằm trong phạm vi tại vị trí khai báo anonymous class và không bị gán lại, biến effectively final nên việc capture là hợp lệ.

Khi dùng lớp lồng cục bộ hoặc anonymous class, cũng cần tránh khai báo một biến cục bộ cùng tên với biến đang được capture trong phạm vi chồng lấn. Hãy dùng tên khác cho biến nội bộ để mã dễ hiểu và không vi phạm quy tắc tên cục bộ.

## 8. Pattern variable và biến dẫn xuất được capture

Đôi khi lambda nên sử dụng giá trị đã chuẩn hóa hoặc chuyển đổi thay vì giá trị đầu vào. Khi đó, hãy tạo một biến dẫn xuất effectively final:

```java
import java.util.function.Supplier;

static Supplier<String> normalizedValueSupplier(Object value) {
    if (value instanceof String text) {
        String normalized = text.strip();
        return () -> normalized;
    }

    return () -> "";
}
```

Ở đây:

- `text` là pattern variable; nó có thể gán lại nếu cần.
- `normalized` là biến cục bộ thông thường, không có `final` nhưng effectively final vì không bị gán lại.
- Lambda capture `normalized`, nên giá trị được trả về là nội dung đã chuẩn hóa.

Nếu muốn thay đổi giá trị trước khi tạo lambda, có thể hoàn tất các phép gán trước rồi tạo một biến snapshot mới không bị gán lại, như ví dụ `capturedGreeting` ở phần trước.

## 9. Không nhầm capture với khả năng thay đổi trạng thái

Khi một pattern variable được capture, nó phải effectively final. Nếu gán lại biến ở bất kỳ vị trí nào trong phạm vi liên quan, lambda không còn được phép capture biến đó:

```java
static Runnable invalidTask(Object value) {
    if (value instanceof String text) {
        return () -> {
            // text = "changed"; // Nếu bỏ comment, capture không còn hợp lệ vì text bị gán lại.
            System.out.println(text);
        };
    }

    return () -> System.out.println("Không phải chuỗi");
}
```

Lambda có thể đọc `text` trong ví dụ vì biến không bị gán lại. Nếu bỏ comment phép gán trong lambda, `text` sẽ không còn effectively final và compiler báo lỗi tại vị trí capture. Nếu cần một trạng thái có thể thay đổi giữa các lần gọi lambda, hãy thiết kế một đối tượng trạng thái riêng có API mutable phù hợp. Không nên dùng mảng một phần tử hoặc holder chỉ để né quy tắc effectively final nếu có thể biểu diễn trạng thái bằng một lớp có ý nghĩa.

Ngoài ra, final/effectively final ràng buộc việc gán lại biến. Với biến tham chiếu, điều đó không tự làm cho đối tượng được tham chiếu trở thành immutable hoặc thread-safe. Nếu nhiều luồng cùng truy cập và thay đổi một đối tượng mutable, cần dùng cơ chế đồng bộ hoặc kiểu dữ liệu thread-safe phù hợp.

## 10. Bảng so sánh nhanh

| Loại biến | Có thể gán lại? | Có thể capture? | Điều kiện |
|---|---|---|---|
| Pattern variable | Có | Có điều kiện | Đang trong flow scope hợp lệ và effectively final tại vị trí capture. |
| Local variable khai báo `final` | Không | Có | Biến phải được khởi tạo hợp lệ trước khi capture. |
| Local variable effectively final | Không được gán lại sau khi đã xác định giá trị | Có | Không có phép gán lại làm mất tính effectively final. |
| Local variable bị gán lại | Có | Không | Không còn effectively final. |
| Tham chiếu `final` đến đối tượng mutable | Không thể đổi tham chiếu | Có | Trạng thái đối tượng vẫn có thể thay đổi tùy API. |

## 11. Ví dụ hoàn chỉnh

```java
import java.util.function.Function;
import java.util.function.Supplier;

public class PatternCaptureDemo {

    static Supplier<String> createSupplier(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("value phải là String");
        }

        String normalized = text.strip();
        return () -> normalized;
    }

    static String addSuffix(Object value, String suffix) {
        if (value instanceof String text) {
            Function<String, String> formatter = extra -> text + extra;
            return formatter.apply(suffix);
        }

        return "(not a string)";
    }

    public static void main(String[] args) {
        Supplier<String> supplier = createSupplier("  Java 16  ");
        System.out.println(supplier.get());

        System.out.println(addSuffix("Pattern", " matching"));
        System.out.println(addSuffix(16, " matching"));
    }
}
```

Có thể biên dịch bằng JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra mã theo mức ngôn ngữ Java 16:

```bash
javac --release 16 PatternCaptureDemo.java
java PatternCaptureDemo
```

## 12. Cách áp dụng trong mã Java hiện đại

- Có thể gán lại pattern variable khi cần; nếu định capture, không gán lại biến sau khi pattern khớp và tạo biến dẫn xuất như `normalized` nếu cần giá trị đã chuyển đổi.
- Capture pattern variable trực tiếp trong lambda hoặc anonymous class khi biến đang nằm trong flow scope hợp lệ.
- Pattern variable không implicitly final; chỉ capture được khi nó effectively final. Không cần tạo biến `final` trung gian nếu bản thân pattern variable không bị gán lại.
- Với local variable thông thường, chỉ capture khi biến được khai báo `final` hoặc effectively final.
- Hoàn tất các phép gán cần thiết trước khi tạo lambda; nếu cần một snapshot ổn định, tạo biến mới và không gán lại biến đó.
- Phân biệt tính final của tham chiếu với tính immutable hoặc thread-safe của đối tượng được tham chiếu.

Pattern variable có thể gán lại như biến cục bộ thông thường. Khi capture trong lambda hoặc lớp lồng nhau, biến phải đang nằm trong flow scope hợp lệ và phải effectively final, nghĩa là không bị gán lại. Nếu cần biến đổi giá trị rồi capture, hãy tạo một biến dẫn xuất riêng và không gán lại biến đó. Hiểu đúng hai điều kiện này giúp sử dụng lambda và lớp lồng nhau an toàn, đồng thời giữ được lợi ích flow scoping trong Java 16 và các phiên bản Java hiện đại.
