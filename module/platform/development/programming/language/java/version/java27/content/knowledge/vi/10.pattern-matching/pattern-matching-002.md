# Pattern matching trong switch

Trong Java 27, **pattern matching trong switch** cho phép chọn nhánh xử lý dựa trên **kiểu và cấu trúc thực tế của một giá trị**. Thay vì kiểm tra hàng loạt điều kiện bằng **instanceof**, ép kiểu rồi truy cập dữ liệu, chương trình có thể đặt các **pattern** trực tiếp trong nhãn **case**. Khi một pattern khớp, Java tạo biến đã được kiểm tra kiểu để dùng ngay trong nhánh tương ứng.

Tính năng **Pattern Matching for switch** được chuẩn hóa qua **JEP 441** từ Java 21 và vẫn là một phần chính thức của Java 27. **Record patterns** được chuẩn hóa qua **JEP 440** cũng có thể kết hợp trong **switch** để lấy dữ liệu từ record. Các ví dụ chính trong bài sử dụng tính năng đã chính thức, không cần bật preview.

> **Phạm vi Java 27:** Tính năng mở rộng pattern matching sang các kiểu nguyên thủy ở vị trí mới, chẳng hạn dùng **long**, **float**, **double**, **boolean** làm selector và dùng top-level primitive patterns, vẫn thuộc **JEP 532 — Fifth Preview** trong Java 27. Bài này tập trung vào ngữ nghĩa và cú pháp chính thức; không sử dụng các phần mở rộng preview làm ví dụ mặc định.

## 1. Vì sao cần pattern matching trong switch?

Giả sử một API nhận giá trị có thể là chuỗi, số nguyên hoặc một loại đối tượng khác.

Trước khi sử dụng pattern switch, ta có thể viết các nhánh **if** với **instanceof**:

~~~java
static String describe(Object value) {
    if (value == null) {
        return "Không có giá trị";
    }

    if (value instanceof String s) {
        return "Chuỗi: " + s;
    }

    if (value instanceof Integer n) {
        return "Số nguyên: " + n;
    }

    return "Đối tượng khác";
}
~~~

Cách viết này vẫn hợp lệ và phù hợp khi chỉ có một hoặc hai điều kiện. Khi nhiều kiểu dữ liệu cần được xử lý, **switch** thường trình bày rõ từng trường hợp hơn:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null       -> "Không có giá trị";
        case String s   -> "Chuỗi: " + s;
        case Integer n  -> "Số nguyên: " + n;
        default         -> "Đối tượng khác";
    };
}
~~~

Chương trình lần lượt xét các nhãn **case** để tìm nhánh khớp với giá trị của **value**. Trong nhánh **case String s**, biến **s** có kiểu **String**. Trong nhánh **case Integer n**, biến **n** có kiểu **Integer**. Bạn không cần thực hiện thêm một phép ép kiểu tường minh.

Ví dụ kết quả:

| Giá trị truyền vào | Kết quả |
|---|---|
| **"Java 27"** | Chuỗi: Java 27 |
| **42** | Số nguyên: 42 |
| **null** | Không có giá trị |
| **true** | Đối tượng khác |

Pattern switch đặc biệt hữu ích khi chương trình có một tập kiểu dữ liệu rõ ràng, chẳng hạn thông điệp, sự kiện, kết quả xử lý hoặc các biến thể của một **sealed hierarchy**.

## 2. Phân biệt switch statement và switch expression

Pattern matching hoạt động với cả **switch statement** lẫn **switch expression**. Hai dạng có mục đích khác nhau.

### 2.1. Switch statement: thực hiện hành động

Một **switch statement** dùng để chọn nhóm câu lệnh cần thực thi:

~~~java
static void printValue(Object value) {
    switch (value) {
        case null ->
            System.out.println("Không có dữ liệu");

        case String text ->
            System.out.println("Văn bản: " + text);

        case Integer count ->
            System.out.println("Số lượng: " + count);

        default ->
            System.out.println("Kiểu khác");
    }
}
~~~

Với cú pháp mũi tên **->**, chỉ nhánh được chọn thực thi, không tự rơi sang nhánh kế tiếp (*fall-through*). Khi cần nhiều câu lệnh, dùng một khối:

~~~java
static void inspect(Object value) {
    switch (value) {
        case String text -> {
            System.out.println("Độ dài: " + text.length());
            System.out.println("Nội dung: " + text);
        }

        case null ->
            System.out.println("Không có dữ liệu");

        default ->
            System.out.println("Không phải String");
    }
}
~~~

Phần bên phải **->** của switch statement phải là một biểu thức được phép dùng làm câu lệnh, một khối lệnh hoặc một lệnh **throw**. Ví dụ gọi method in kết quả là hợp lệ.

### 2.2. Switch expression: trả về một giá trị

Một **switch expression** tính toán một kết quả. Mỗi nhánh phải cung cấp giá trị hoặc kết thúc bằng cách ném ngoại lệ:

~~~java
static int textLength(Object value) {
    return switch (value) {
        case null        -> 0;
        case String text -> text.length();
        case char[] chars -> chars.length;
        default          -> -1;
    };
}
~~~

Điểm cần nhớ:

- **return switch (...) { ... };** là một biểu thức trả về giá trị; dấu chấm phẩy sau dấu ngoặc nhọn đóng kết thúc câu lệnh **return**.
- Các nhánh có thể trả về các kiểu tương thích để tạo kiểu kết quả chung của biểu thức.
- Dạng mũi tên không tạo fall-through.

Nếu một nhánh cần thực hiện nhiều bước trước khi tạo ra giá trị, dùng **yield** trong khối của switch expression:

~~~java
static String summarize(Object value) {
    return switch (value) {
        case String text -> {
            String normalized = text.strip();
            yield normalized.isEmpty()
                ? "Chuỗi rỗng"
                : "Chuỗi: " + normalized;
        }

        case Integer number -> "Số: " + number;
        case null -> "Không có giá trị";
        default -> "Không hỗ trợ";
    };
}
~~~

**yield** trả giá trị cho **switch expression** hiện tại. Không dùng **break** để trả giá trị từ một switch expression.

### 2.3. So sánh nhanh

| Tiêu chí | Switch statement | Switch expression |
|---|---|---|
| Mục đích | Thực hiện hành động | Tạo một giá trị |
| Kết quả | Không có giá trị biểu thức | Có giá trị và kiểu kết quả |
| Nhánh nhiều câu lệnh | Dùng khối **{ ... }** | Dùng khối và **yield** |
| Tính đầy đủ | Bắt buộc khi là *enhanced switch statement*, chẳng hạn có pattern label hoặc **case null** | Luôn phải đầy đủ |
| Trường hợp thường dùng | Ghi log, cập nhật trạng thái, gọi xử lý | Phân loại, tính phí, tạo thông báo, ánh xạ dữ liệu |

## 3. Type patterns trong case

Dạng cơ bản nhất là **type pattern**:

~~~java
case String text -> ...
~~~

Nhãn này có hai vai trò:

1. Kiểm tra giá trị thực tế có khớp với kiểu **String** hay không.
2. Nếu khớp, khai báo và khởi tạo biến **text** đã có kiểu **String**.

Ví dụ phân loại nhiều loại đối tượng:

~~~java
static String classify(Object data) {
    return switch (data) {
        case null -> "Giá trị null";
        case String text -> "Văn bản dài " + text.length() + " ký tự";
        case Integer count -> "Số nguyên: " + count;
        case Boolean flag -> "Boolean: " + flag;
        case Number number -> "Số khác: " + number;
        default -> "Đối tượng khác";
    };
}
~~~

Cần đặt **case Integer count** trước **case Number number**, vì **Integer** là lớp con của **Number**. Quy tắc thứ tự sẽ được giải thích ở phần dominance.

**Lưu ý về selector:** Giá trị trong **switch (data)** được tính một lần trước khi xét các nhãn. Với pattern matching chính thức, selector có thể là kiểu tham chiếu như **Object**, **Number**, một interface, một record hoặc một sealed interface. Các mở rộng **switch** trên một số kiểu nguyên thủy khác vẫn là preview trong Java 27.

### 3.1. Phạm vi biến được khai báo bởi pattern

Biến của type pattern chỉ có hiệu lực ở nơi Java bảo đảm pattern đã khớp. Trong dạng mũi tên, đó là phần thân nhánh **case** (và guard **when**, nếu có).

~~~java
static void show(Object input) {
    switch (input) {
        case String text -> {
            System.out.println(text.toUpperCase());
        }

        case Integer count -> {
            System.out.println(count + 1);
            // Không dùng được biến text trong nhánh này.
        }

        default -> {
            System.out.println("Khác");
            // Không dùng được biến count của nhánh trước.
        }
    }
}
~~~

Nhờ giới hạn phạm vi, Java ngăn chương trình dùng một biến khi việc kiểm tra kiểu chưa thành công.

### 3.2. Kiểu selector phải tương thích với pattern

Không phải mọi pattern đều hợp lệ cho mọi selector. Trình biên dịch kiểm tra pattern có thể áp dụng cho **kiểu tĩnh** của biểu thức selector hay không.

Ví dụ, khi selector đã có kiểu **String**, kiểm tra nó bằng một type pattern **Integer** không hợp lệ:

~~~java
// Minh họa lỗi: nhãn Integer không áp dụng được cho String.
static String invalid(String text) {
    return switch (text) {
        case Integer n -> "Số: " + n; // Lỗi biên dịch
        default -> "Chuỗi";
    };
}
~~~

Khi chương trình thật sự cần phân loại nhiều kiểu không liên quan, hãy dùng selector có kiểu chung phù hợp, chẳng hạn **Object** hoặc một interface chung.

## 4. Guard khi điều kiện kiểu chưa đủ: when

Một type pattern chỉ kiểm tra kiểu. Trong thực tế, bạn có thể cần xét thêm độ dài chuỗi, dấu của số, trạng thái hoặc quy tắc nghiệp vụ.

Java cho phép đặt **when** sau pattern:

~~~java
static String describeText(Object input) {
    return switch (input) {
        case null -> "Thiếu dữ liệu";
        case String text when text.isBlank() ->
            "Chuỗi trống hoặc chỉ gồm khoảng trắng";

        case String text when text.length() <= 8 ->
            "Chuỗi ngắn: " + text;

        case String text ->
            "Chuỗi dài: " + text;

        default ->
            "Không phải chuỗi";
    };
}
~~~

Quy trình xử lý một nhãn có guard:

1. Kiểm tra giá trị có khớp với pattern hay không.
2. Chỉ khi pattern khớp, khởi tạo các biến pattern rồi đánh giá biểu thức sau **when**.
3. Nếu guard trả về **true**, chọn nhánh.
4. Nếu guard trả về **false**, tiếp tục xét nhãn **case** phù hợp tiếp theo.

Biến **text** có thể được dùng trong guard và phần thân nhánh vì Java đã xác nhận giá trị có kiểu **String**.

~~~mermaid
flowchart TD
    A["Tính selector của switch"] --> B{"Pattern của case có khớp?"}
    B -->|Không| F["Xét case tiếp theo"]
    B -->|Có| C{"Có when?"}
    C -->|Không| E["Chạy nhánh case"]
    C -->|Có| D{"Guard trả true?"}
    D -->|Có| E
    D -->|Không| F
~~~

Guard phải có kiểu **boolean** hoặc **Boolean**. Nếu giá trị **Boolean** cần unboxing là **null**, quá trình đánh giá có thể ném **NullPointerException**. Ngoại lệ phát sinh khi đánh giá guard cũng lan ra từ **switch**.

Nên viết guard ngắn gọn, dễ đọc và hạn chế tác dụng phụ. Với logic phức tạp, hãy tách điều kiện thành method có tên rõ ràng:

~~~java
static boolean isValidCode(String text) {
    return !text.isBlank() && text.length() <= 12;
}

static String verify(Object input) {
    return switch (input) {
        case String code when isValidCode(code) -> "Mã hợp lệ";
        case String code -> "Mã không hợp lệ";
        case null -> "Thiếu mã";
        default -> "Sai kiểu dữ liệu";
    };
}
~~~

Nếu nhiều nhãn **case** cùng khớp với một kiểu, thứ tự đặt nhãn ảnh hưởng đến kết quả. Hãy đặt trường hợp cụ thể trước trường hợp tổng quát.

## 5. Dominance: thứ tự case và các nhánh không thể tới

Các nhãn có pattern được xét theo thứ tự. Java kiểm tra trường hợp một nhãn xuất hiện sau bị nhãn trước bao phủ hoàn toàn, khiến nhãn sau không bao giờ được chọn. Đây là quy tắc **dominance**.

Ví dụ sai:

~~~java
static String wrongOrder(Object input) {
    return switch (input) {
        case CharSequence sequence ->
            "Chuỗi ký tự dài " + sequence.length();

        case String text ->
            "String: " + text; // Lỗi biên dịch: case bị chi phối

        default -> "Khác";
    };
}
~~~

Mọi đối tượng **String** cũng là **CharSequence**. Vì vậy **case CharSequence** ở trước đã nhận tất cả giá trị mà **case String** ở sau có thể xử lý.

Đổi thứ tự để trường hợp cụ thể được xử lý trước:

~~~java
static String correctOrder(Object input) {
    return switch (input) {
        case String text ->
            "String: " + text;

        case CharSequence sequence ->
            "Chuỗi ký tự dài " + sequence.length();

        case null -> "Không có dữ liệu";
        default -> "Khác";
    };
}
~~~

Tương tự, một type pattern không guard có thể chi phối các constant label liên quan nếu đứng trước:

~~~java
static String describeInteger(Integer value) {
    return switch (value) {
        case 0 -> "Số không";
        case 1 -> "Số một";
        case Integer number when number > 1 -> "Lớn hơn một";
        case Integer number -> "Số khác";
    };
}
~~~

Ở đây **case Integer number** đặt cuối, sau các trường hợp cụ thể. Trình biên dịch có các quy tắc dominance riêng cho guard; không nên giả định rằng mọi guard đều được phân tích để xác định một nhãn không thể tới. Hãy chọn thứ tự dễ hiểu: **hằng cụ thể → pattern có guard → pattern tổng quát**.

Một pattern không guard và bao phủ toàn bộ kiểu selector còn có thể hoạt động như nhánh cuối tương đương với **default**. Không khai báo thêm **default** sau một pattern đã bao phủ toàn bộ kiểu selector, vì sẽ tạo nhãn không thể tới.

## 6. Xử lý null trong pattern switch

**null** cần được xử lý riêng. Một type pattern như **case String text** hoặc **case Object object** không khớp với **null**.

Nếu selector có giá trị **null** và switch không có nhãn **case null**, chương trình ném **NullPointerException**. Nhãn **default** đứng riêng cũng không tự xử lý **null**.

Ví dụ xử lý tường minh:

~~~java
static String stringify(Object input) {
    return switch (input) {
        case null -> "(không có dữ liệu)";
        case String text -> text;
        default -> input.toString();
    };
}
~~~

Giá trị **null** được xử lý ở nhánh đầu; các giá trị không phải **String** đi tới **default**.

Có thể gộp **null** với **default** khi cả hai cần cùng một cách xử lý:

~~~java
static String onlyStrings(Object input) {
    return switch (input) {
        case String text -> "Văn bản: " + text;
        case null, default -> "Không phải văn bản";
    };
}
~~~

Đây là một trường hợp ghép nhãn hợp lệ. **case null** không được ghép tùy ý với một pattern có biến, chẳng hạn **case null, String text**, vì cách ghép đó không hợp lệ.

### 6.1. Null trong record pattern

Một record có thể chứa component tham chiếu bằng **null**. Khi một record pattern con yêu cầu kiểu **String**, component **null** không khớp với pattern con đó. Chương trình có thể dùng một nhánh khác để xử lý record còn lại:

~~~java
record User(String name) {}

static String greeting(Object input) {
    return switch (input) {
        case User(String name) -> "Xin chào, " + name;
        case User user -> "Người dùng chưa có tên";
        case null -> "Không có người dùng";
        default -> "Không phải User";
    };
}
~~~

Nếu có **new User(null)**, nhánh **case User(String name)** không khớp và nhánh **case User user** nhận giá trị đó. Điều này khác với **null** ở cấp selector, vốn cần **case null** riêng.

## 7. Tính đầy đủ của switch: exhaustiveness

Một **switch expression** phải *exhaustive*: trình biên dịch cần chứng minh mọi giá trị selector hợp lệ đều có nhánh xử lý (ngoại trừ cách Java xử lý đặc biệt giá trị **null** như đã nói).

Các **enhanced switch statement** cũng phải exhaustive; ví dụ, switch statement có type pattern hoặc **case null** phải bao phủ đủ các trường hợp. Điều này khác với một số switch statement chỉ dùng nhãn hằng truyền thống, vốn có thể không có nhánh **default**.

Ví dụ thiếu nhánh trong switch expression:

~~~java
static String missingCase(Object input) {
    return switch (input) {
        case String text -> "Chuỗi: " + text;
        case Integer number -> "Số: " + number;
        // Lỗi biên dịch: chưa bao phủ các kiểu Object khác.
    };
}
~~~

Khi không thể liệt kê hết các loại giá trị, hãy thêm **default**:

~~~java
static String completeCase(Object input) {
    return switch (input) {
        case String text -> "Chuỗi: " + text;
        case Integer number -> "Số: " + number;
        case null -> "Không có giá trị";
        default -> "Kiểu khác";
    };
}
~~~

Trong những mô hình dữ liệu được giới hạn bởi **sealed types**, có thể đạt tính đầy đủ mà không cần **default**.

### 7.1. Sealed interface và kiểm tra tính đầy đủ tại thời điểm biên dịch

Một **sealed interface** quy định những kiểu cụ thể được phép triển khai nó. Trình biên dịch có thể sử dụng danh sách này để kiểm tra các nhánh:

~~~java
sealed interface Message permits TextMessage, ErrorMessage {}

record TextMessage(String content) implements Message {}
record ErrorMessage(int code) implements Message {}

public class MessageDemo {
    static String render(Message message) {
        return switch (message) {
            case TextMessage text ->
                "Nội dung: " + text.content();

            case ErrorMessage error ->
                "Lỗi #" + error.code();
        };
    }

    public static void main(String[] args) {
        System.out.println(render(new TextMessage("Java 27")));
        System.out.println(render(new ErrorMessage(404)));
    }
}
~~~

Nhánh **default** không bắt buộc vì chỉ có hai kiểu được phép triển khai **Message**, và cả hai đã có **case** tương ứng. Ví dụ cho thấy sự kết hợp giữa **sealed interface**, **record** và **pattern switch** để xử lý các biến thể dữ liệu.

Nếu thêm một subtype được phép mới vào sealed interface rồi biên dịch lại toàn bộ mã, trình biên dịch có thể yêu cầu bổ sung case mới. Đây là lợi ích của việc không dùng **default** để che khuất những kiểu mà chương trình muốn xử lý tường minh.

Tính exhaustive không đồng nghĩa với việc **null** được xử lý. Với **render(null)**, ví dụ trên vẫn ném **NullPointerException**, vì không có **case null**.

### 7.2. Switch trên enum

Một switch expression bao phủ đủ các hằng của **enum** cũng có thể bỏ **default**:

~~~java
enum Status {
    NEW, PROCESSING, DONE
}

static String label(Status status) {
    return switch (status) {
        case NEW -> "Mới";
        case PROCESSING -> "Đang xử lý";
        case DONE -> "Hoàn thành";
    };
}
~~~

Khi bổ sung một hằng enum và biên dịch lại mã, compiler yêu cầu xem xét những switch expression chưa bao phủ hằng mới.

### 7.3. Khi nào MatchException xuất hiện?

Trong một số tình huống hiếm liên quan đến biên dịch riêng biệt hoặc mã nhị phân không đồng bộ, một **switch** đã được xác minh exhaustive khi biên dịch có thể gặp một kiểu mới lúc chạy mà không có nhánh khớp. Khi đó JVM có thể ném **MatchException**.

Ví dụ, ứng dụng được biên dịch với hai subtype của sealed interface nhưng sau đó chạy với phiên bản thư viện mới có cấu trúc subtype đã thay đổi, trong khi ứng dụng chưa được biên dịch lại. Đây là lý do cần biên dịch và kiểm tra lại các thành phần liên quan khi mô hình sealed/enum thay đổi.

Không nên sử dụng **default** chỉ để che lỗi mất đồng bộ mô hình dữ liệu. Khi một tập biến thể là cố định trong thiết kế, nhánh tường minh thường giúp phát hiện thay đổi sớm hơn.

## 8. Record patterns trong switch

**Record pattern** cho phép kiểm tra một record và lấy trực tiếp các component trong cùng một nhãn **case**. Tính năng này đã được chuẩn hóa trong Java 21 và dùng bình thường trên Java 27.

Xét record:

~~~java
record Point(int x, int y) {}
~~~

Thay vì nhận cả record rồi gọi từng accessor:

~~~java
static String pointText(Object input) {
    return switch (input) {
        case Point point ->
            "x=" + point.x() + ", y=" + point.y();

        case null -> "Không có tọa độ";
        default -> "Không phải Point";
    };
}
~~~

Ta có thể trích xuất component trực tiếp:

~~~java
static String pointText(Object input) {
    return switch (input) {
        case Point(int x, int y) ->
            "x=" + x + ", y=" + y;

        case null -> "Không có tọa độ";
        default -> "Không phải Point";
    };
}
~~~

Ở đây **Point(int x, int y)** vừa kiểm tra kiểu record **Point**, vừa khớp và lấy hai component **int** của nó. Các biến **x** và **y** được sử dụng trong nhánh sau mũi tên.

**Chú ý:** Việc dùng **int** làm pattern cho *record component* có kiểu **int** là chức năng chính thức của record patterns. Điều này không đồng nghĩa với việc các *top-level primitive patterns* hoặc mọi selector nguyên thủy đã trở thành tính năng chính thức; phần mở rộng đó vẫn preview trong Java 27.

### 8.1. Record patterns lồng nhau

Nếu một record chứa record khác, pattern có thể lồng nhau:

~~~java
record Point(int x, int y) {}
record Address(String street, Point location) {}

static String showAddress(Object input) {
    return switch (input) {
        case Address(String street, Point(int x, int y))
                when x >= 0 && y >= 0 ->
            street + " tại (" + x + ", " + y + ")";

        case Address address ->
            "Địa chỉ chưa đủ tọa độ";

        case null ->
            "Không có địa chỉ";

        default ->
            "Không phải Address";
    };
}
~~~

Nhánh đầu chỉ khớp với **Address** có **street** là **String** khác null và **location** là **Point** với các component thỏa guard. Nếu record chứa component null khiến pattern con không khớp, nhánh **case Address address** có thể xử lý.

Record pattern phù hợp để đọc dữ liệu bất biến và lồng nhau. Nếu cần thực hiện nhiều bước nghiệp vụ, hãy tách chúng thành method thay vì lồng quá nhiều tầng pattern trong một nhãn.

## 9. Giới hạn với generic types và những kiểu khác

Pattern switch sử dụng hệ thống kiểu Java và tuân theo những giới hạn của generic types, type erasure và tính phù hợp của pattern.

### 9.1. Kiểm tra List bằng wildcard

Với một giá trị có kiểu tĩnh **Object**, có thể nhận diện **List** bằng wildcard:

~~~java
static int sizeOf(Object input) {
    return switch (input) {
        case null -> 0;
        case List<?> items -> items.size();
        case String text -> text.length();
        default -> 1;
    };
}
~~~

Không viết **case List<String> items** để kiểm tra một **Object** có phải danh sách String hay không: Java không thể kiểm tra tham số kiểu **String** tại runtime theo cách đó do type erasure.

Nếu cần xác thực từng phần tử có phải String, hãy dùng **List<?>** rồi kiểm tra từng phần tử:

~~~java
static boolean isStringList(Object input) {
    if (!(input instanceof List<?> items)) {
        return false;
    }

    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }

    return true;
}
~~~

Đây là cách xử lý rõ ràng khi dữ liệu đến từ nguồn không xác định kiểu phần tử.

### 9.2. Primitive pattern trong Java 27 là preview

Ở Java 27, **JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)** vẫn thuộc diện preview.

| Trường hợp | Trạng thái trên Java 27 |
|---|---|
| **case String s**, **case Integer n** trong switch của **Object** | Chính thức |
| **case Point(int x, int y)** khi **Point** là record có component **int** | Chính thức |
| **case null**, guard **when**, kiểm tra exhaustive trên sealed types | Chính thức |
| Mở rộng switch cho selector **long**, **float**, **double**, **boolean** nguyên thủy | Preview — JEP 532 |
| Top-level primitive patterns theo JEP 532 | Preview — JEP 532 |

Preview feature có thể thay đổi ở bản Java sau và yêu cầu tùy chọn biên dịch/chạy riêng. Trong chương trình thông thường cần mã nguồn ổn định, ưu tiên các ví dụ chính thức đã được dùng trong bài.

## 10. Cú pháp case có dấu hai chấm và nguy cơ fall-through

Java vẫn hỗ trợ các nhóm câu lệnh sau nhãn **case ... :**. Với pattern variables, kiểu viết này cần cẩn thận vì một nhánh không thể được phép rơi xuống nhánh khác rồi sử dụng biến pattern chưa được khởi tạo.

Ví dụ có **break** rõ ràng:

~~~java
static void print(Object input) {
    switch (input) {
        case String text:
            System.out.println(text);
            break;

        case Integer number:
            System.out.println(number);
            break;

        case null:
            System.out.println("Không có dữ liệu");
            break;

        default:
            System.out.println("Khác");
    }
}
~~~

Nếu bỏ **break** giữa các nhánh có biến pattern, mã có thể bị từ chối khi biên dịch vì luồng điều khiển có thể đi vào nhánh chứa biến chưa được khởi tạo. Đối với mã mới, nên dùng nhãn mũi tên **->** để biểu đạt rõ mỗi nhánh là một phương án xử lý độc lập.

### 10.1. Không nhầm break, return và yield

| Từ khóa | Vai trò |
|---|---|
| **break** | Thoát khỏi switch statement hoặc vòng lặp bao quanh thích hợp |
| **return** | Thoát khỏi method hiện tại |
| **yield** | Cung cấp giá trị từ một nhánh khối của switch expression |
| **throw** | Ném ngoại lệ, có thể dùng trong nhánh của cả statement và expression |

Ví dụ nhánh ném ngoại lệ trong switch expression:

~~~java
static int requirePositive(Object input) {
    return switch (input) {
        case Integer number when number > 0 -> number;
        case Integer number ->
            throw new IllegalArgumentException("Giá trị phải dương: " + number);
        case null ->
            throw new IllegalArgumentException("Thiếu giá trị");
        default ->
            throw new IllegalArgumentException("Không phải Integer");
    };
}
~~~

## 11. Ví dụ thực tế: định tuyến yêu cầu xử lý đơn hàng

Một hệ thống nhận các yêu cầu tạo đơn hoặc hủy đơn. Mỗi yêu cầu được mô tả bằng **record** và cùng triển khai một **sealed interface**. Pattern switch sẽ phân loại yêu cầu, trích xuất dữ liệu cần dùng và kiểm tra điều kiện hợp lệ.

Ví dụ đầy đủ, lưu trong tệp **OrderRouter.java**:

~~~java
public class OrderRouter {

    sealed interface OrderRequest permits Create, Cancel {}

    record Create(String product, int quantity) implements OrderRequest {}

    record Cancel(long orderId) implements OrderRequest {}

    static String handle(OrderRequest request) {
        return switch (request) {
            case null ->
                "Thiếu yêu cầu";

            case Create(String product, int quantity)
                    when product != null && !product.isBlank() && quantity > 0 ->
                "Tạo đơn: " + quantity + " x " + product;

            case Create create ->
                "Yêu cầu tạo đơn không hợp lệ";

            case Cancel(long orderId) when orderId > 0 ->
                "Hủy đơn #" + orderId;

            case Cancel cancel ->
                "Mã đơn cần hủy không hợp lệ";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(new Create("Sách Java", 2)));
        System.out.println(handle(new Create("", 0)));
        System.out.println(handle(new Cancel(101)));
        System.out.println(handle(new Cancel(-1)));
        System.out.println(handle(null));
    }
}
~~~

Chạy bằng JDK 27:

~~~bash
javac OrderRouter.java
java OrderRouter
~~~

Kết quả:

~~~text
Tạo đơn: 2 x Sách Java
Yêu cầu tạo đơn không hợp lệ
Hủy đơn #101
Mã đơn cần hủy không hợp lệ
Thiếu yêu cầu
~~~

Bài toán kết hợp các cơ chế:

- **sealed interface OrderRequest** giới hạn tập biến thể dữ liệu ở **Create** và **Cancel**.
- **record Create** và **record Cancel** cung cấp dữ liệu có cấu trúc rõ ràng.
- **case Create(String product, int quantity)** và **case Cancel(long orderId)** dùng record patterns để lấy component.
- **when** kiểm tra điều kiện nghiệp vụ sau khi pattern khớp.
- Nhánh **case Create create** và **case Cancel cancel** xử lý trường hợp dữ liệu không đạt guard.
- **case null** giúp phân biệt yêu cầu vắng mặt.
- Không cần **default** vì toàn bộ các subtype được phép đã có nhánh bao phủ.

Đây là ví dụ về điều phối dựa trên dạng dữ liệu. Nếu hệ thống có thêm subtype mới, ví dụ **Update**, phải cập nhật sealed hierarchy và xem xét thêm nhánh xử lý khi biên dịch lại.

### 11.1. Khi nào nên chọn polymorphism thay cho switch?

Pattern switch phù hợp khi một thao tác cần xử lý nhiều biến thể của **mô hình dữ liệu chung**, đặc biệt khi ứng dụng sở hữu tập biến thể sealed.

Nếu mỗi đối tượng tự chịu trách nhiệm về hành vi của nó và các subtype thường xuyên được bổ sung độc lập, method đa hình thông thường trên interface/lớp có thể phù hợp hơn. Không nên tạo những switch dài lặp lại ở khắp hệ thống. Có thể đặt thao tác phân loại trong một method để dễ kiểm tra và bảo trì.

## 12. Những lỗi và hiểu nhầm thường gặp

| Lỗi hoặc hiểu nhầm | Hậu quả hoặc cách xử lý |
|---|---|
| Đặt **case CharSequence** trước **case String** | **String** bị chi phối, gây lỗi biên dịch; đặt case cụ thể trước. |
| Đặt **case Integer number** trước **case 0** trên selector phù hợp | Hằng **0** có thể bị pattern bao phủ; đặt hằng trước type pattern. |
| Cho rằng **default** tự bắt **null** | **null** vẫn dẫn đến **NullPointerException** nếu không có **case null**. |
| Ghép **case null, String s** | Không hợp lệ; xử lý null riêng hoặc ghép **case null, default**. |
| Quên nhánh cho kiểu khác trên switch expression | Biên dịch thất bại vì switch không exhaustive. |
| Dùng **case List<String>** cho một **Object** | Không kiểm tra được tham số generic tại runtime; dùng **List<?>** và xác thực phần tử nếu cần. |
| Dùng biến pattern trong một case khác | Biến nằm ngoài phạm vi; chỉ dùng biến ở guard và nhánh khớp. |
| Đặt **case String s** trước **case String s when ...** | Nhánh guard phía sau bị bao phủ; đưa nhánh guard lên trước. |
| Cho rằng một record pattern luôn khớp khi record có component null | Pattern con có thể không khớp; bổ sung nhánh fallback nếu dữ liệu có thể chứa null. |
| Dùng dấu **:** và để luồng rơi vào nhánh pattern khác | Có thể gây lỗi vì biến pattern chưa được khởi tạo; ưu tiên **->**. |
| Dùng **break** để trả giá trị của switch expression | Trong khối switch expression hãy dùng **yield**. |
| Dùng selector **long/double/boolean** như tính năng đã ổn định | Các mở rộng tương ứng vẫn preview trong Java 27 (JEP 532). |
| Thêm **default** vào mọi sealed switch | Có thể che việc bổ sung subtype khi cần compiler nhắc cập nhật các nhánh; chỉ thêm khi có chủ đích. |

## 13. Ghi nhớ

- Pattern matching trong **switch** là tính năng chính thức từ Java 21 (JEP 441), vẫn áp dụng trên Java 27.
- **Type patterns** cho phép kiểm tra kiểu và khai báo biến đã đúng kiểu trực tiếp trong nhánh **case**.
- **when** bổ sung điều kiện; guard chỉ được đánh giá khi pattern đã khớp.
- Các case được xét theo thứ tự; nhãn tổng quát ở trước có thể **dominate** nhãn cụ thể ở sau và gây lỗi biên dịch.
- **case null** xử lý giá trị null; **default** riêng lẻ không thay thế nó.
- Switch expression luôn phải **exhaustive**; enhanced switch statement có pattern cũng phải exhaustive.
- **Sealed types** và **enum** cho phép compiler chứng minh tính đầy đủ mà không cần default trong nhiều trường hợp.
- **Record patterns** (JEP 440) có thể trích xuất các component trực tiếp, kể cả khi record lồng nhau.
- **yield** tạo giá trị từ một khối của switch expression; nhãn **->** tránh fall-through.
- Mở rộng primitive patterns và switch với một số selector nguyên thủy vẫn là **JEP 532 Fifth Preview** trong Java 27; không nhầm với các phần đã chính thức.

## Tài liệu tham khảo

- [Oracle Java SE 27 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/27/language/pattern-matching-switch.html)
- [Oracle Java SE 27 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/27/language/switch-expressions-statements.html)
- [Oracle Java SE 27 — Record Patterns](https://docs.oracle.com/en/java/javase/27/language/record-patterns.html)
- [Java Language Specification, Java SE 27 — §14.11 switch Statements, §14.30 Patterns](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html)
- [Java Language Specification, Java SE 27 — §15.28 switch Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java SE 27 — Java Language Changes by Release (JEP 532 preview status)](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
