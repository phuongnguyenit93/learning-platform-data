# Phân biệt `instanceof` chính thức với pattern `switch` preview của Java 17

Java 17 có hai nhóm cú pháp dễ bị nhầm với nhau khi xử lý dữ liệu theo kiểu runtime: **pattern matching cho `instanceof`**, đã là tính năng chính thức, và **pattern matching cho `switch`**, khi đó mới ở trạng thái *preview*. Cả hai đều có thể kiểm tra kiểu và gắn tên biến cho giá trị đã khớp; điểm khác nhau quan trọng là **mức độ ổn định, cách biên dịch/chạy, phạm vi cú pháp và cách xử lý các trường hợp còn thiếu**.

Với dự án cần duy trì trên **Java 17 lâu dài**, hãy dùng pattern `instanceof` ổn định. Nếu thấy các ví dụ `switch` có `case String s -> ...` hoặc `case null -> ...`, cần hiểu rằng đây không phải cú pháp `switch` ổn định của Java 17. Phần thực hành dưới đây trình bày cả hai để người học phân biệt chính xác; phần preview được tách riêng và chỉ dùng để minh họa lịch sử phát triển ngôn ngữ.

## 1. Trạng thái tính năng trong Java 17

| Tính năng | Ví dụ cú pháp | Trạng thái trong JDK 17 | Cần `--enable-preview`? |
| --- | --- | --- | --- |
| `instanceof` kiểm tra kiểu thông thường | `value instanceof String` | Chính thức, đã có từ lâu | Không |
| Pattern matching cho `instanceof` | `value instanceof String text` | **Chính thức**, từ Java 16 (JEP 394) | **Không** |
| `switch` theo hằng `int`, `String`, `enum` | `case "OK" -> ...` | Chính thức; `switch` expression và arrow labels ổn định từ Java 14 | Không |
| Pattern matching cho `switch` | `case String text -> ...` | **Preview lần đầu ở Java 17** (JEP 406) | **Có** |
| `case null` trong pattern `switch` | `case null -> ...` | Thuộc phần mở rộng preview ở Java 17 | **Có** |
| Guarded pattern trong `switch` | `case String s && s.length() > 3 -> ...` | Preview ở Java 17 | **Có** |

Hai từ khóa `instanceof` và `switch` vốn là thành phần lâu đời của Java. Điều cần nhận biết ở đây là **pattern** được tích hợp vào chúng ở phiên bản nào và trạng thái phát hành ra sao.

Các mốc liên quan:

- **Java 16:** Pattern matching cho `instanceof` được chuẩn hóa bằng **JEP 394**.
- **Java 17:** Pattern matching cho `switch` xuất hiện ở **lần preview đầu tiên**, theo **JEP 406**.
- **Java 21:** Pattern matching cho `switch` mới chính thức được chuẩn hóa bằng **JEP 441**, sau những lần preview và thay đổi cú pháp ở các bản Java trung gian.

Do đó, không nên lấy một ví dụ `switch` pattern viết cho Java 21 rồi mặc định nó chạy nguyên vẹn trên Java 17.

## 2. Pattern `instanceof` chính thức giải quyết vấn đề gì?

Trước khi có pattern variable, cách phổ biến là kiểm tra rồi ép kiểu thủ công:

~~~java
static String describe(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "Độ dài: " + text.length();
    }
    return "Không phải chuỗi";
}
~~~

Cùng ý nghĩa trong Java 17:

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Độ dài: " + text.length();
    }
    return "Không phải chuỗi";
}
~~~

Ở biểu thức `value instanceof String text`:

1. `value` là giá trị cần kiểm tra.
2. `String` là kiểu cần khớp.
3. `text` là **pattern variable**, được gán giá trị đã khớp và có kiểu `String`.
4. Nếu điều kiện là `true`, compiler biết `text` dùng an toàn ở những vị trí mà luồng điều khiển bảo đảm mẫu đã khớp.

Không cần gọi lại phép ép kiểu `(String) value`. Cách này giảm trùng lặp và giữ điều kiện kiểm tra gần với chỗ sử dụng dữ liệu.

### 2.1. Ví dụ Java 17 không cần preview

Tạo file **`StableInstanceofDemo.java`**:

~~~java
public final class StableInstanceofDemo {

    private StableInstanceofDemo() {
    }

    static String describe(Object value) {
        if (value == null) {
            return "Không có dữ liệu";
        }

        if (value instanceof String text && !text.isBlank()) {
            return "Chuỗi: " + text.strip();
        }

        if (value instanceof Integer number) {
            return "Số nguyên: " + number;
        }

        if (value instanceof String) {
            return "Chuỗi trống";
        }

        return "Kiểu khác: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Object[] samples = {"  Java 17  ", 42, "   ", 3.14, null};
        for (Object sample : samples) {
            System.out.println(describe(sample));
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17**:

~~~bash
javac --release 17 -encoding UTF-8 StableInstanceofDemo.java
java StableInstanceofDemo
~~~

Đầu ra mong đợi:

~~~text
Chuỗi: Java 17
Số nguyên: 42
Chuỗi trống
Kiểu khác: Double
Không có dữ liệu
~~~

Không có flag preview trong hai lệnh này. Đây là ví dụ thích hợp làm mã thực hành hoặc mã ứng dụng Java 17 ổn định.

## 3. Phạm vi của pattern variable: flow scoping

Biến `text` trong `value instanceof String text` không phải biến có hiệu lực ở mọi nơi sau khi xuất hiện. Java dùng **flow scoping**: pattern variable có thể được tham chiếu ở chỗ mà compiler xác định mẫu đã khớp chắc chắn.

### 3.1. Trong nhánh `if` đúng

~~~java
void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip()); // Hợp lệ: đã khớp String.
    }

    // Không thể mặc định dùng text tại đây:
    // biểu thức instanceof có thể đã trả về false.
}
~~~

### 3.2. Trong biểu thức kết hợp bằng `&&`

~~~java
static boolean isLongText(Object value) {
    return value instanceof String text && text.length() >= 10;
}
~~~

Nếu phần bên trái là `false`, toán tử `&&` sẽ không đánh giá phần bên phải. Nếu phần bên phải được chạy thì `text` đã là một `String` hợp lệ.

Ngược lại, đây là lỗi biên dịch:

~~~java
// Sai: vế phải của || có thể chạy khi mẫu không khớp.
// if (value instanceof String text || text.isBlank()) {
//     ...
// }
~~~

Bởi với `||`, vế phải được xét khi vế trái là `false`; thời điểm đó `text` chưa chắc được gán.

### 3.3. Sau một nhánh thoát sớm

~~~java
static int lengthOfText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần truyền String");
    }

    return text.length(); // Hợp lệ: nhánh không khớp đã ném ngoại lệ.
}
~~~

Đây là mẫu **guard clause** hữu ích trong validation: trả về hoặc ném ngoại lệ ngay khi kiểu không phù hợp, rồi dùng pattern variable trong luồng thành công.

### 3.4. Kiểm tra giá trị `null`

~~~java
Object value = null;

System.out.println(value instanceof String text); // false
~~~

Khi biểu thức đầu vào là `null`, `instanceof` trả về `false`; nó không ném `NullPointerException` chỉ vì đầu vào null. Nếu muốn phân biệt “không có dữ liệu” với “kiểu dữ liệu khác”, hãy xử lý `null` tường minh trước hoặc sau các điều kiện `instanceof`.

### 3.5. Generic type và type erasure

Java không cho kiểm tra một tham số generic không xác định được tại runtime:

~~~java
Object value = java.util.List.of("A", "B");

// Không hợp lệ: List<String> không thể được kiểm tra đầy đủ ở runtime.
// if (value instanceof java.util.List<String> list) {
//     ...
// }
~~~

Cách biểu diễn đúng là kiểm tra dạng có thể xác định ở runtime:

~~~java
if (value instanceof java.util.List<?> list) {
    System.out.println("Số phần tử: " + list.size());
}
~~~

`List<?>` cho biết đối tượng là một danh sách nhưng chưa chứng minh kiểu của từng phần tử. Nếu cần bảo đảm tất cả phần tử là `String`, phải kiểm tra từng phần tử hoặc xác thực ở ranh giới dữ liệu.

## 4. `switch` thông thường vẫn là tính năng chính thức trong Java 17

Một nhầm lẫn phổ biến là nhìn thấy `switch` có mũi tên `->` rồi kết luận đó là preview. Thực tế, **switch expression** và nhãn nhánh có mũi tên đã là tính năng chính thức từ **Java 14**.

Ví dụ `switch` trên `enum`, hoàn toàn ổn định trong Java 17:

~~~java
public final class StableSwitchDemo {

    enum OrderStatus {
        NEW,
        PAID,
        CANCELLED
    }

    static String label(OrderStatus status) {
        return switch (status) {
            case NEW -> "Đơn mới";
            case PAID -> "Đã thanh toán";
            case CANCELLED -> "Đã hủy";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(OrderStatus.PAID));
    }
}
~~~

Biên dịch bình thường:

~~~bash
javac --release 17 -encoding UTF-8 StableSwitchDemo.java
java StableSwitchDemo
~~~

Kết quả:

~~~text
Đã thanh toán
~~~

Đây là `switch` chọn trường hợp dựa trên **hằng enum** và trả về biểu thức. Nó **không** kiểm tra kiểu runtime của một `Object` và không khai báo pattern variable `case String text`.

Có thể dùng nhãn hằng với `String` trong Java 17:

~~~java
String output = switch (statusCode) {
    case "OK" -> "Thành công";
    case "RETRY" -> "Thử lại";
    default -> "Không xác định";
};
~~~

Cú pháp `case "OK" ->` cũng ổn định; **không đồng nghĩa** với `case String text ->`. Điều phân biệt là **constant label** và **type pattern label**, không phải hình dạng mũi tên.

## 5. Pattern matching cho `switch` của Java 17 là preview

JEP 406 mở rộng `switch` để chọn nhánh theo kiểu và ràng buộc mẫu. Trong Java 17, ví dụ dưới đây thuộc tính năng **preview**:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Integer number -> "Số nguyên: " + number;
        case String text -> "Chuỗi: " + text;
        default -> "Kiểu khác";
    };
}
~~~

Hai nhánh `case Integer number` và `case String text` khai báo pattern variable trong từng case, khác với `case` theo hằng.

**Không dùng hai lệnh biên dịch/chạy bình thường ở mục 2 để chạy file này**. Với JDK 17, cần bật preview ở cả hai giai đoạn.

### 5.1. Ví dụ preview độc lập

Tạo file **`PatternSwitchPreviewDemo.java`**:

~~~java
public final class PatternSwitchPreviewDemo {

    private PatternSwitchPreviewDemo() {
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";
            case String text && text.isBlank() -> "Chuỗi trống";
            case String text -> "Chuỗi: " + text.strip();
            case Integer number -> "Số nguyên: " + number;
            default -> "Kiểu khác: " + value.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        Object[] samples = {"  Java 17  ", 42, "   ", 3.14, null};
        for (Object sample : samples) {
            System.out.println(describe(sample));
        }
    }
}
~~~

Với **JDK 17**, biên dịch:

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PatternSwitchPreviewDemo.java
~~~

Và chạy:

~~~bash
java --enable-preview PatternSwitchPreviewDemo
~~~

Đầu ra mong đợi:

~~~text
Chuỗi: Java 17
Số nguyên: 42
Chuỗi trống
Kiểu khác: Double
Không có dữ liệu
~~~

Compiler có thể thông báo rằng mã đang dùng preview features. Đây là cảnh báo có chủ đích: chương trình đang dùng cú pháp chưa được chuẩn hóa trong chính bản Java 17.

**Hai flag có vai trò khác nhau:**

- `--release 17` chọn phiên bản ngôn ngữ và API mục tiêu.
- `--enable-preview` cho phép sử dụng những tính năng preview của phiên bản JDK đang biên dịch/chạy.

Chỉ đặt `--release 17` không đủ để dùng pattern `switch` preview. Chỉ bật preview lúc biên dịch mà quên flag lúc chạy cũng không đủ với class file sử dụng preview.

### 5.2. Guard trong bản preview Java 17

Ở ví dụ trên:

~~~java
case String text && text.isBlank() -> "Chuỗi trống";
~~~

`&& text.isBlank()` là **guard** gắn với type pattern: chỉ chọn nhánh khi giá trị là `String` và điều kiện bổ sung đúng.

Cú pháp guard này là cú pháp của **Java 17 preview**. Trong Java 21, pattern `switch` đã chính thức và guard dùng `when`:

~~~java
// Java 21 trở lên; không phải mã Java 17:
case String text when text.isBlank() -> "Chuỗi trống";
~~~

Không lấy ví dụ `when` của Java 21 dán nguyên vào mã Java 17. Ngược lại, không dùng cú pháp guard `&&` của Java 17 preview làm chuẩn cho mã Java 21.

### 5.3. `case null` cũng thuộc phần mở rộng preview

`switch` truyền thống của Java không xử lý selector `null` bằng nhánh hằng thông thường: một giá trị `null` đi vào `switch` truyền thống thường gây `NullPointerException`.

Với pattern `switch` preview, JEP 406 cho phép:

~~~java
return switch (value) {
    case null -> "Không có giá trị";
    case String text -> text;
    default -> "Giá trị kiểu khác";
};
~~~

Điều này **không có nghĩa rằng mọi `switch` Java 17 đều hỗ trợ `case null`**. Ví dụ trên vẫn là preview.

Trong mã Java 17 không bật preview, xử lý null trước khi vào `switch` hoặc dùng `if`:

~~~java
static String safeText(Object value) {
    if (value == null) {
        return "Không có giá trị";
    }
    if (value instanceof String text) {
        return text;
    }
    return "Giá trị kiểu khác";
}
~~~

Lưu ý: `default` trong pattern `switch` không phải một cách thay thế chắc chắn cho `case null`. Nếu không có nhãn cho null, một giá trị null vẫn có thể dẫn đến `NullPointerException` theo quy tắc của `switch`.

## 6. So sánh cùng một yêu cầu bằng hai cách

Giả sử yêu cầu là chuyển một giá trị kiểu `Object` thành thông điệp:

- `null`: “Không có dữ liệu”.
- `String` rỗng hoặc toàn khoảng trắng: “Chuỗi trống”.
- `String` khác: chuẩn hóa bằng `strip()`.
- `Integer`: hiển thị giá trị số.
- Các kiểu còn lại: hiển thị loại dữ liệu.

**Cách A — Java 17 ổn định, không bật preview:**

~~~java
static String describeStable(Object value) {
    if (value == null) {
        return "Không có dữ liệu";
    }

    if (value instanceof String text) {
        if (text.isBlank()) {
            return "Chuỗi trống";
        }
        return "Chuỗi: " + text.strip();
    }

    if (value instanceof Integer number) {
        return "Số nguyên: " + number;
    }

    return "Kiểu khác: " + value.getClass().getSimpleName();
}
~~~

**Cách B — Java 17 preview:**

~~~java
static String describePreview(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String text && text.isBlank() -> "Chuỗi trống";
        case String text -> "Chuỗi: " + text.strip();
        case Integer number -> "Số nguyên: " + number;
        default -> "Kiểu khác: " + value.getClass().getSimpleName();
    };
}
~~~

Về mặt nghiệp vụ, hai phương thức tương đương với bộ đầu vào đã nêu. Nhưng khi chọn cho **dự án thực tế chạy Java 17**, cách A có lợi thế là dựa trên ngôn ngữ chuẩn của Java 17 và hoạt động với bộ công cụ mặc định. Cách B giúp nhận diện ý tưởng pattern `switch`, song vẫn phụ thuộc cơ chế preview và cú pháp lịch sử.

| Góc nhìn | Pattern `instanceof` ổn định | Pattern `switch` trong Java 17 |
| --- | --- | --- |
| Kiểm tra kiểu runtime | Có | Có |
| Khai báo biến đã khớp | Có | Có |
| Hỗ trợ nhánh theo kiểu | Qua `if` / `else if` | Qua `case Type variable` |
| Guard theo điều kiện bổ sung | Điều kiện `&&` trong `if` | Guarded pattern `&&` trong nhãn `case` |
| Null | `instanceof` cho `false`; cần nhánh xử lý riêng nếu muốn | `case null` có trong phần preview |
| Phân tích trường hợp toàn diện | Chuỗi `if` không tự báo thiếu toàn bộ biến thể | Một số `switch` expression có thể được kiểm tra tính toàn diện theo các kiểu được phép, nhưng cơ chế pattern vẫn preview |
| Flag compiler/runtime | Không | Có |
| Phù hợp mã Java 17 ổn định | Có | Không nên chọn làm nền tảng mặc định |
| Mối liên hệ Java 21 | Vẫn dùng bình thường | Ý tưởng được chuẩn hóa, có thay đổi cú pháp trong quá trình phát triển |

## 7. Pattern `switch` preview có quy tắc sắp xếp nhánh

Một lợi thế của pattern `switch` là các nhãn case có thể thể hiện quan hệ kiểu cụ thể và kiểu tổng quát. Tuy nhiên, chúng cũng tạo ra vấn đề **dominance**: một case đặt trước có thể bao phủ tất cả giá trị của case đặt sau.

Ví dụ minh họa **không hợp lệ** trong pattern `switch` preview:

~~~java
// Sai: Number đã khớp mọi Integer,
// vì Integer là một subtype của Number.
static String bad(Object value) {
    return switch (value) {
        case Number number -> "Number";
        case Integer integer -> "Integer"; // Bị case trước bao phủ.
        default -> "Other";
    };
}
~~~

Cách sắp xếp đúng là đặt mẫu cụ thể trước:

~~~java
static String good(Object value) {
    return switch (value) {
        case Integer integer -> "Integer: " + integer;
        case Number number -> "Number: " + number;
        default -> "Other";
    };
}
~~~

Tương tự, nhánh `case Object anything` có thể bao phủ các type pattern khác dành cho giá trị không null. Trong code Java 17 ổn định, khi viết chuỗi `if`, compiler không tự báo nhánh đứng sau bị che khuất theo cùng cơ chế `switch` pattern; người viết cần tự chú ý thứ tự điều kiện.

Với các guard, ví dụ trước dùng:

~~~java
case String text && text.isBlank() -> "Chuỗi trống";
case String text -> "Chuỗi có nội dung";
~~~

Nhánh có guard phải đứng trước nhánh `String` tổng quát để nhánh chuyên biệt có cơ hội chạy. Nếu đưa nhánh `String` tổng quát lên trước, mọi chuỗi sẽ khớp ở đó và nhánh sau không còn hữu ích.

## 8. `sealed` và tính bao phủ đầy đủ của `switch`

Java 17 đã chính thức hỗ trợ `sealed class` và `sealed interface`: kiểu gốc có thể giới hạn các kiểu con trực tiếp. Điều này thường đi cùng ý tưởng **xử lý tất cả các biến thể hợp lệ**.

Ví dụ mô hình kết quả nghiệp vụ:

~~~java
sealed interface LookupResult permits Found, Missing {
}

record Found(String name) implements LookupResult {
}

record Missing(int requestedId) implements LookupResult {
}
~~~

Với pattern `instanceof` **ổn định** trong Java 17:

~~~java
static String render(LookupResult result) {
    if (result instanceof Found found) {
        return "Đã tìm thấy: " + found.name();
    }

    if (result instanceof Missing missing) {
        return "Không tìm thấy ID " + missing.requestedId();
    }

    throw new IllegalStateException("Biến thể chưa được hỗ trợ");
}
~~~

Mặc dù hệ phân cấp hiện có hai biến thể, các nhánh `if` không tạo thành một lời chứng minh tự động cho compiler rằng phương thức đã xử lý đầy đủ. Nếu tương lai thêm kiểu `InvalidInput` vào `permits`, phương thức vẫn có thể biên dịch mà không cảnh báo thiếu nhánh; nhánh dự phòng sẽ chỉ hoạt động khi chạy đến loại mới.

Với pattern `switch` **preview** ở Java 17, có thể viết:

~~~java
static String renderPreview(LookupResult result) {
    return switch (result) {
        case Found found -> "Đã tìm thấy: " + found.name();
        case Missing missing -> "Không tìm thấy ID " + missing.requestedId();
    };
}
~~~

Ở đây, compiler có thể dựa trên sealed hierarchy để xác định các subtype được phép và kiểm tra các nhánh của `switch` expression. Nhưng bản thân **cú pháp pattern `switch` trong JDK 17 vẫn preview**; không vì có `sealed` chính thức mà mặc định pattern `switch` cũng là ngôn ngữ chính thức.

Khi thêm biến thể trực tiếp vào hierarchy, logic `switch` cần được cập nhật theo hợp đồng mới. Đây là lý do việc liệt kê kiểu hợp lệ rõ ràng hữu ích khi tổ chức API, dù bản Java 17 ổn định thường xử lý bằng `instanceof`.

### 8.1. `switch` expression và yêu cầu tính đầy đủ

Một `switch` **expression** cần tạo ra kết quả cho mọi đường thực thi hợp lệ. Với `enum` thông thường, có thể liệt kê hết các hằng như ví dụ `OrderStatus`. Với các type pattern trong Java 17 preview, compiler cũng phân tích các trường hợp bao phủ trên tập kiểu đầu vào.

Nếu `switch` trả về biểu thức mà không bao phủ đủ trường hợp, sẽ có lỗi biên dịch. Một nhánh `default` thường được dùng với kiểu đầu vào mở như `Object`. Với hierarchy sealed được kiểm soát, có thể dùng các type pattern của các nhánh hợp lệ để thể hiện toàn bộ tập kết quả.

Đừng nhầm tính toàn diện của một **switch expression** với yêu cầu rằng mọi chuỗi `if` phải được compiler kiểm tra: đó là hai cơ chế khác nhau.

## 9. Pattern `instanceof` có thay thế mọi loại cast không?

Không. Pattern `instanceof` hoạt động tốt khi cần xác định **kiểu runtime** của một tham chiếu rồi xử lý theo kiểu đó. Nó không tự kiểm tra mọi quy tắc nghiệp vụ hoặc biến mọi phép chuyển kiểu thành hợp lệ.

### 9.1. Kiểu runtime so với ý nghĩa nghiệp vụ

~~~java
if (value instanceof String text) {
    // Đã biết là String.
    // Chưa biết text có phải email hợp lệ hay không.
}
~~~

Kiểm tra kiểu không tương đương validation nội dung. Vẫn phải kiểm tra dữ liệu theo yêu cầu của miền nghiệp vụ.

### 9.2. Không destructure record bằng `instanceof` của Java 17

Một record có thể có thành phần:

~~~java
record Point(int x, int y) {
}
~~~

Ở Java 17, cú pháp hợp lệ là **type pattern** rồi gọi accessor:

~~~java
if (value instanceof Point point) {
    System.out.println(point.x() + point.y());
}
~~~

Cú pháp **record pattern** dạng bên dưới **không thuộc Java 17 chính thức**:

~~~java
// Không dùng trong Java 17:
// if (value instanceof Point(int x, int y)) {
//     ...
// }
~~~

Record patterns là tính năng xuất hiện sau Java 17 và được chuẩn hóa ở Java 21. Đừng nhầm việc Java 17 hỗ trợ `record` với việc nó đã hỗ trợ destructuring của record trong mọi pattern.

### 9.3. Cast khi kiểu đã được biết bằng hợp đồng

Nếu API đã trả về một kiểu cụ thể, không cần ép kiểu hay `instanceof`:

~~~java
String text = service.loadText();
System.out.println(text.length());
~~~

Nếu một API nhận đa dạng kiểu dữ liệu, pattern matching mới có vai trò rõ ràng. Không nên lạm dụng kiểm tra kiểu thay cho thiết kế interface, polymorphism hoặc generic ở nơi các cơ chế này diễn đạt yêu cầu tốt hơn.

## 10. Khác biệt về build, runtime và phiên bản JDK

Trong Java 17, preview là cơ chế cho phép thử nghiệm một tính năng ngôn ngữ ở phiên bản phát hành cụ thể, trước khi tính năng ấy được chuẩn hóa hoặc điều chỉnh.

### 10.1. Cách biên dịch có ý nghĩa gì?

| Mã nguồn | Lệnh | Kết quả mong đợi |
| --- | --- | --- |
| `if (obj instanceof String s)` | `javac --release 17 File.java` | Hợp lệ |
| `switch` theo hằng/enum dùng `->` | `javac --release 17 File.java` | Hợp lệ |
| `switch` có `case String s ->` | `javac --release 17 File.java` | Không chấp nhận vì preview chưa bật |
| `switch` có `case String s ->` | `javac --enable-preview --release 17 File.java` | Có thể biên dịch với JDK 17 có preview bật |
| Class file dùng preview | `java --enable-preview MainClass` | Chạy trên runtime tương ứng với bản phát hành đã biên dịch preview |

Lệnh chỉ rõ `--release 17` nên dùng khi biên dịch hướng tới Java 17; nó yêu cầu cả ngôn ngữ và API phù hợp với phiên bản đích. Đối với preview, phải bảo đảm **JDK thực tế đang chạy trình biên dịch cũng là JDK 17**.

### 10.2. Vì sao không nên phát hành mã Java 17 preview tùy tiện?

Class file sử dụng preview được đánh dấu đặc biệt theo phiên bản class file; runtime cần hỗ trợ đúng phiên bản preview tương ứng. Không thể mặc định rằng một class được biên dịch từ Java 17 preview sẽ chạy trên Java 18 hoặc Java 21 chỉ vì các bản đó mới hơn.

Khi ứng dụng dùng preview, cần kiểm soát:

- Phiên bản JDK dùng để compile và run.
- Flag `--enable-preview` trong build, test và lệnh khởi động thực tế.
- Cấu hình IDE, CI và môi trường triển khai.
- Kế hoạch điều chỉnh mã nguồn nếu đổi JDK, bởi cú pháp và ngữ nghĩa preview có thể thay đổi giữa các bản.

Vì vậy, trong bài học hoặc ứng dụng được yêu cầu **Java 17 ổn định**, việc giới thiệu cú pháp `switch` preview là để nhận diện sự khác biệt, không phải đề xuất sử dụng nó mặc định.

### 10.3. Cẩn thận khi sao chép ví dụ từ Internet hoặc IDE

Có ba trường hợp thường gặp:

1. **IDE đang dùng JDK mới hơn** và tự đề xuất code `switch` pattern chính thức của Java 21; dán sang dự án Java 17 có thể không biên dịch.
2. **Bài viết cũ dùng Java 17 preview** với guard `&&`; mã đó không nên được coi là cú pháp ổn định dùng xuyên mọi phiên bản.
3. **Ứng dụng dùng Java 17 nhưng build không bật preview**; mọi `case Type variable` sẽ gây lỗi dù `if (value instanceof Type variable)` hoạt động bình thường.

Để xác định ngữ cảnh, nên đọc phiên bản `java -version`/`javac -version`, cấu hình `--release` hoặc Maven/Gradle toolchain, rồi đối chiếu với cú pháp đang sử dụng.

## 11. Khi nào dùng pattern `instanceof`, khi nào dùng đa hình?

Một chuỗi pattern `instanceof` có thể thích hợp cho **adapter**, **chuyển đổi dữ liệu**, **parsing**, **formatter** hoặc các tình huống cần phân loại các kiểu khác nhau:

~~~java
static String format(Object value) {
    if (value instanceof Integer n) {
        return "Số: " + n;
    }
    if (value instanceof String s) {
        return "Văn bản: " + s;
    }
    return "Không hỗ trợ";
}
~~~

Nhưng nếu các lớp đều thuộc một hệ phân cấp và mỗi lớp tự biết cách thực hiện hành vi, interface thông thường có thể phù hợp hơn:

~~~java
interface Message {
    String display();
}

record TextMessage(String text) implements Message {
    @Override
    public String display() {
        return text;
    }
}

record NumberMessage(int number) implements Message {
    @Override
    public String display() {
        return Integer.toString(number);
    }
}
~~~

Người gọi chỉ cần:

~~~java
Message message = new TextMessage("Xin chào");
System.out.println(message.display());
~~~

Cách này tránh buộc mọi nơi tiêu thụ `Message` phải lặp lại danh sách `instanceof`. Việc chọn pattern hay đa hình phụ thuộc **ai sở hữu hành vi** và **ai cần biết các biến thể**: nếu logic định dạng thuộc chính mỗi kiểu, đa hình có thể gọn hơn; nếu đang chuyển nhiều kiểu không cùng interface sang một định dạng ngoài, pattern `instanceof` thường tự nhiên.

Với hệ phân cấp `sealed`, cả hai cách vẫn có chỗ đứng; điều cần tránh trong dự án Java 17 là vô tình đưa cú pháp pattern `switch` preview vào mã được yêu cầu biên dịch bằng ngôn ngữ ổn định.

## 12. Bảng lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách xử lý trên Java 17 |
| --- | --- | --- |
| `case String s ->` báo “preview feature” | Đang dùng pattern `switch` của Java 17 | Viết lại bằng `instanceof` hoặc chủ động bật preview cho bài thử nghiệm |
| `case "OK" ->` bị tưởng là preview | Nhầm arrow `switch` expression với pattern `switch` | Giữ nguyên; đây là cú pháp ổn định |
| `case String s when ...` không biên dịch | Đây là cú pháp guard của phiên bản Java mới hơn | Dùng `if` với `instanceof` trong mã Java 17 ổn định |
| `if (x instanceof String s || s.isEmpty())` báo lỗi | `s` không chắc đã được gán ở vế phải `||` | Dùng điều kiện `&&` khi logic phù hợp hoặc tách nhánh |
| Dùng `s` ngoài phạm vi nhánh `instanceof` | Pattern variable theo flow scoping | Chỉ dùng ở đường đi mà compiler biết mẫu đã khớp |
| `instanceof List<String>` không hợp lệ | Generic type erasure | Dùng `List<?>` và kiểm tra phần tử nếu cần |
| Biên dịch preview thành công nhưng runtime lỗi | Chưa bật preview lúc chạy hoặc sai phiên bản JDK | Dùng runtime tương ứng và `java --enable-preview` |
| `switch` trên null ném lỗi | Không có nhánh xử lý null | Với Java 17 ổn định, kiểm tra null trước khi switch |
| Tưởng `record` tự hỗ trợ record pattern | Nhầm tính năng record với record destructuring | Dùng `instanceof Point p` rồi gọi `p.x()`, `p.y()` |
| Thêm biến thể sealed mà logic `if` bỏ sót | Chuỗi `if` không tự được compiler xem là exhaustive | Cập nhật các nhánh và xử lý mặc định hợp lý |

## 13. Bài tập thực hành

### Bài 1 — Viết lại cast thành pattern `instanceof`

Chuyển đoạn code sau sang Java 17 ổn định:

~~~java
if (value instanceof Number) {
    Number number = (Number) value;
    System.out.println(number.doubleValue());
}
~~~

Yêu cầu: dùng pattern variable, giữ hành vi cũ, không bật preview. Sau đó giải thích vì sao không thể sử dụng biến đã khai báo trong nhánh nếu điều kiện kiểm tra kiểu trả về `false`.

### Bài 2 — Phân biệt `switch` ổn định và preview

Xác định đoạn nào chạy bằng `javac --release 17` bình thường và đoạn nào cần preview:

~~~java
// A
String a = switch (status) {
    case "ACTIVE" -> "Đang hoạt động";
    default -> "Không rõ";
};

// B
String b = switch (value) {
    case Integer i -> "Số " + i;
    default -> "Khác";
};

// C
boolean c = value instanceof String s && s.length() > 3;
~~~

Gợi ý: xem **nhãn của case** có phải hằng kiểu `String` hay là **type pattern**. Đừng chỉ nhìn mũi tên.

### Bài 3 — Sửa lỗi flow scoping

Đoạn sau sai ở chỗ nào?

~~~java
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("Chuỗi");
// }
~~~

Viết lại yêu cầu “giá trị phải là chuỗi không trống” bằng `&&` rồi in nội dung đã `strip()`.

### Bài 4 — Chạy thử preview có kiểm soát

Dùng file `PatternSwitchPreviewDemo.java` ở mục 5:

1. Thử biên dịch bằng `javac --release 17 PatternSwitchPreviewDemo.java` để quan sát thông báo liên quan preview.
2. Biên dịch bằng `javac --enable-preview --release 17 -encoding UTF-8 PatternSwitchPreviewDemo.java`.
3. Chạy bằng `java --enable-preview PatternSwitchPreviewDemo`.
4. Viết lại phương thức `describe` bằng pattern `instanceof`, rồi chạy không có preview.

Mục tiêu là **phân biệt chế độ ngôn ngữ**, không phải đưa preview vào ứng dụng.

### Bài 5 — Phát triển mô hình `sealed`

Tạo `sealed interface Result permits Success, Failure` với hai record `Success(String value)` và `Failure(String message)`. Viết hàm `render(Result value)` bằng pattern `instanceof` ổn định. Sau đó thêm biến thể `Cancelled` vào hierarchy, cập nhật hàm và giải thích vì sao bước cập nhật này phải được xem xét ở mọi nơi tiêu thụ `Result`.

## 14. Ghi nhớ khi làm việc với Java 17

- `instanceof Type variable` là **pattern matching đã chính thức** và được dùng trực tiếp trong Java 17.
- `switch` expression với nhãn hằng và `->` cũng **đã chính thức**; mũi tên không phải dấu hiệu của preview.
- `case Type variable ->`, `case null ->` và guarded pattern trong `switch` là những phần của **pattern switch preview** ở Java 17.
- Khi thử nghiệm preview trên JDK 17 cần bật `--enable-preview` khi biên dịch và chạy; cú pháp có thể khác với pattern `switch` chính thức của Java 21.
- Với mã yêu cầu giữ ổn định trên Java 17, dùng `if`/`else if` với pattern `instanceof`, `switch` theo hằng chính thức, hoặc đa hình theo nhu cầu thiết kế.

Phân biệt đúng **tính năng đã chuẩn hóa** và **tính năng preview ở từng phiên bản** giúp viết được mã Java 17 thực sự chạy trên môi trường mục tiêu, đồng thời hiểu vì sao các ví dụ `switch` pattern trên những phiên bản Java khác nhau có thể trông tương tự nhưng không tương thích cú pháp.
