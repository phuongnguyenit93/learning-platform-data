# Kết hợp `instanceof` pattern với `&&` hoặc guard clause trong Java 17

> **Java core — language-basics / Mẫu kiểm tra kiểu**  
> **Môi trường:** Java 17+, một file tự chứa, chỉ cần JDK; không bật preview.  
> **Mục tiêu:** Kết hợp phép kiểm tra kiểu với điều kiện phụ bằng `&&`; dùng guard clause thoát sớm để sử dụng biến mẫu phía sau; hiểu *flow scoping*, short-circuit và các lỗi về phạm vi biến.

## 1. Tình huống thực tế: kiểm tra rồi xử lý dữ liệu nhập

Giả sử một hàm nhận `Object` từ API và chỉ chấp nhận chuỗi có nội dung. Type pattern `input instanceof String text` vừa kiểm tra kiểu runtime vừa ràng buộc biến `text`; nếu là `null` hoặc kiểu khác, mẫu không khớp.

~~~java
static boolean hasUsableName(Object input) {
    return input instanceof String name
            && !name.isBlank()
            && name.strip().length() <= 20;
}
~~~

Hàm trả `false` với `null`, số nguyên, chuỗi toàn khoảng trắng hoặc chuỗi sau `strip()` dài hơn 20 ký tự. Với tên hợp lệ, các điều kiện sau mới được đánh giá. Chính thứ tự ấy giúp không cần ép kiểu hoặc kiểm tra null riêng.

## 2. Chọn `&&` hay guard clause theo nhiệm vụ

Nếu chỉ cần một câu trả lời boolean như `hasUsableName`, nối điều kiện bằng `&&` giúp tránh nhánh lồng nhau. Khi cần giải thích **vì sao** từ chối (sai kiểu, chuỗi rỗng, dữ liệu quá dài) hoặc dùng đối tượng đã kiểm tra qua nhiều bước, guard clause thường dễ đọc hơn. Mục 4 so sánh các đường trả về; chương trình hoàn chỉnh ở mục 7 đếm số lần một điều kiện phụ thực sự được gọi.

| Mục tiêu | Cách viết |
| --- | --- |
| Quy tắc kiểm tra ngắn, không cần lý do từ chối | Type pattern kết hợp `&&` |
| Trả mã lỗi khác nhau và xử lý nhiều bước | Guard `if (!(x instanceof T t)) return ...;` |
| Trả cùng một lỗi nếu sai kiểu **hoặc** không đạt điều kiện phụ | Guard phủ định kết hợp `||` |

Đối với cả hai cách, biến mẫu chỉ được dùng khi luồng đã bảo đảm khớp kiểu.

## 3. Khi thay `&&` bằng `&` hoặc `||`

`&&` ngắn mạch: không kiểm tra điều kiện phụ nếu mẫu sai. Toán tử `&` trên `boolean` đánh giá cả hai vế nên `input instanceof String s & !s.isBlank()` không biên dịch: compiler không thể bảo đảm `s` đã được ràng buộc ở vế phải.

~~~java
Object input = " Java ";
// Hợp lệ: điều kiện phụ chỉ chạy sau khi String đã khớp.
boolean ok = input instanceof String s && !s.isBlank();

// Không hợp lệ: OR dương xét vế phải khi mẫu thất bại.
// boolean bad = input instanceof String s || s.isBlank();
~~~

Với yêu cầu “sai kiểu **hoặc** chuỗi blank”, đảo điều kiện mẫu sẽ làm `||` phù hợp: `!(input instanceof String text) || text.isBlank()`. Trong trường hợp đó vế phải chỉ chạy khi mẫu String thật sự khớp. Chương trình ở mục 7 đặt ba cách cạnh nhau để thấy khác biệt về kết quả và số lần gọi hàm.

## 4. Guard clause: trả về sớm khi không đúng kiểu

Khi phải xử lý nhiều bước sau kiểm tra kiểu, dùng guard clause thường dễ đọc hơn nhiều tầng lồng nhau:

~~~java
static String normalize(Object input) {
    if (!(input instanceof String text)) {
        return "NOT_STRING";
    }

    if (text.isBlank()) {
        return "BLANK";
    }

    return text.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

Nếu không phải String hoặc là null, nhánh đầu **return** ngay. Để đến được dòng `text.isBlank()`, Java biết pattern phải đã khớp, nên biến mẫu `text` có thể sử dụng ở phần còn lại.

Nếu thay `return` trong guard đầu bằng lệnh chỉ in log rồi cho chương trình chạy tiếp, Java **không thể đảm bảo** `text` đã được ràng buộc ở các dòng sau.

| Cần làm | Cách phù hợp |
| --- | --- |
| Một điều kiện kiểu và một điều kiện phụ ngắn | `if (x instanceof String s && !s.isBlank())` |
| Phân biệt lỗi sai kiểu và chuỗi trống | Guard phủ định, rồi kiểm tra blank |
| Nhiều thao tác liên tiếp trên đối tượng đã kiểm tra | Guard clause để giảm lồng nhánh |
| Không cần sử dụng biến mẫu | `x instanceof String` là đủ |

## 5. Guard phủ định kết hợp OR và early return

Có thể kết hợp cả hai bước từ chối:

~~~java
static String accept(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "REJECTED";
    }
    return "ACCEPTED:" + text.trim();
}
~~~

Ở vế phải của OR, `text` hợp lệ vì khi vế đó được xét, pattern đã khớp. Nếu toàn bộ điều kiện true thì phương thức return. Nếu luồng đi tiếp, Java biết `input` là String và `text` không blank.

Dù viết gọn, cách này có thể khó đọc khi nhiều điều kiện; khi cần trả thông báo lỗi riêng từng nguyên nhân, tách thành hai guard như mục 4.

Ví dụ với interface:

~~~java
static String longSequence(Object input) {
    if (input instanceof CharSequence seq && seq.length() >= 3) {
        return "LEN:" + seq.length();
    }
    return "SHORT_OR_OTHER";
}
~~~

Cả `String` lẫn `StringBuilder` đều triển khai `CharSequence`. Pattern có thể dùng với lớp hoặc interface, không cần chỉ kiểm tra `String`.

## 6. Lỗi thường gặp và giới hạn Java 17

- **Tham chiếu `null`:** Với `Object missing = null;`, phép `missing instanceof String s` trả `false`; biến mẫu `s` không được dùng trên đường đi đó. **Literal `null instanceof String s` không biên dịch ở Java 17**, vì pattern này vô điều kiện theo kiểu tĩnh của literal. Dùng một biến tham chiếu có giá trị null như trong ví dụ thay vì viết literal trực tiếp.
- **Dùng biến mẫu ở sai chỗ:** Sau `if (x instanceof String s)` thông thường, đừng tự giả định `s` có thể dùng ở ngoài nhánh; hãy để một guard có `return` hoặc `throw` loại hết đường không khớp.
- **Pattern thừa:** `String alreadyString = "x";` rồi `alreadyString instanceof String s` có thể bị từ chối trong Java 17 vì kiểu tĩnh đã là subtype của kiểu mẫu. Không cần kiểm tra kiểu đã biết.
- **Generic bị xóa:** Không thể kiểm tra trực tiếp `instanceof java.util.List<String>`; dùng kiểu kiểm tra được tại runtime như `List<?>` và kiểm tra các phần tử riêng nếu cần.
- **Điều kiện có tác dụng phụ:** Vế phải của `&&` không được gọi khi vế trái false. Nếu vế phải cập nhật biến, ghi log hoặc ném ngoại lệ, chuyển sang toán tử khác có thể thay đổi hành vi.
- **Không thay kiểm tra nghiệp vụ:** Khớp String không có nghĩa chuỗi không rỗng, đúng định dạng hoặc không vượt giới hạn.

Nguyên tắc: giữ biểu thức ngắn, ưu tiên tên biến rõ nghĩa, và dùng guard clause cho nhiều điều kiện từ chối hoặc nhiều bước xử lý.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **InstanceofAndGuardDemo.java**:

~~~java
import java.util.Locale;

public final class InstanceofAndGuardDemo {
    private static int checkCalls;

    private static boolean nonBlank(String text) {
        checkCalls++;
        return !text.isBlank();
    }

    private static String withAnd(Object input) {
        if (input instanceof String text && nonBlank(text)) {
            return "TEXT:" + text.trim().toUpperCase(Locale.ROOT);
        }
        return "NO_TEXT";
    }

    private static String withGuard(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_STRING";
        }
        if (text.isBlank()) {
            return "BLANK";
        }
        return "TEXT:" + text.trim().toUpperCase(Locale.ROOT);
    }

    private static String withOrGuard(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "REJECTED";
        }
        return "ACCEPTED:" + text.trim();
    }

    private static String sequenceLabel(Object input) {
        if (input instanceof CharSequence seq && seq.length() >= 3) {
            return "LEN:" + seq.length();
        }
        return "SHORT_OR_OTHER";
    }

    private static String display(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String text) {
            return "\"" + text + "\"";
        }
        return value.getClass().getSimpleName() + ":" + value;
    }

    public static void main(String[] args) {
        Object[] inputs = {null, Integer.valueOf(7), "  ", " java ", "Hi"};

        for (Object value : inputs) {
            checkCalls = 0;
            String andResult = withAnd(value);
            int checks = checkCalls;
            String guardResult = withGuard(value);
            String orResult = withOrGuard(value);

            System.out.println("input=" + display(value)
                    + ";and=" + andResult
                    + ";checks=" + checks
                    + ";guard=" + guardResult
                    + ";or=" + orResult);
        }

        System.out.println("sequenceBuilder="
                + sequenceLabel(new StringBuilder("abc")));
        System.out.println("sequenceShort=" + sequenceLabel("Hi"));
        System.out.println("sequenceNull=" + sequenceLabel(null));
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 InstanceofAndGuardDemo.java
java InstanceofAndGuardDemo
~~~

**Expected stdout chính xác:**

~~~text
input=null;and=NO_TEXT;checks=0;guard=NOT_STRING;or=REJECTED
input=Integer:7;and=NO_TEXT;checks=0;guard=NOT_STRING;or=REJECTED
input="  ";and=NO_TEXT;checks=1;guard=BLANK;or=REJECTED
input=" java ";and=TEXT:JAVA;checks=1;guard=TEXT:JAVA;or=ACCEPTED:java
input="Hi";and=TEXT:HI;checks=1;guard=TEXT:HI;or=ACCEPTED:Hi
sequenceBuilder=LEN:3
sequenceShort=SHORT_OR_OTHER
sequenceNull=SHORT_OR_OTHER
~~~

`checks=0` khi null hoặc Integer cho thấy hàm `nonBlank` **không chạy** khi pattern thất bại. Với chuỗi blank, pattern khớp nên `nonBlank` chạy đúng một lần rồi trả false. Guard clause cho nhãn từ chối cụ thể; guard dùng OR cho một nhãn từ chối chung.

## 8. Bài tập tự luyện

**Bài 1.** Dự đoán điều kiện `x instanceof String s && s.length() >= 5` với `null`, `Integer`, chuỗi 2 ký tự và chuỗi 6 ký tự; vế phải chạy khi nào?

**Bài 2.** Viết lại bài 1 bằng guard clause, sau đó dùng `s` ngoài nhánh guard khi bảo đảm đã khớp kiểu.

**Bài 3.** Giải thích vì sao kiểm tra kiểu rồi nối với OR trực tiếp không thể dùng biến mẫu ở vế phải, nhưng phủ định kiểm tra kiểu rồi OR với `s.isBlank()` lại hợp lệ.

**Bài 4.** Viết một bộ đếm trong hàm điều kiện phụ; thử input null, sai kiểu, String rỗng và String hợp lệ để quan sát số lần gọi.

**Bài 5.** Dùng pattern `CharSequence seq` với `StringBuilder("abcd")` và `String("xy")`; xác định đầu ra khi yêu cầu độ dài ít nhất 3.

### Ghi nhớ

**`x instanceof T name && predicate(name)`** an toàn vì vế phải chỉ chạy sau khi pattern khớp. **`if (!(x instanceof T name)) return ...;`** là guard clause giúp sử dụng `name` ở phần còn lại của phương thức. Phạm vi biến mẫu được kiểm tra theo luồng thực thi, không chỉ theo dấu ngoặc.
