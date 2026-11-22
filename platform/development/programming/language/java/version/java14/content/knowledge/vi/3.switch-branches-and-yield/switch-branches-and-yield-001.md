# Nhãn mũi tên `case ... ->` và một kết quả trực tiếp trong `switch` biểu thức (Java 14+)

## 1. Ý nghĩa

Từ Java 14, **`switch` biểu thức** là tính năng chính thức: một cấu trúc `switch` có thể tính toán và **trả về một giá trị** để gán vào biến, truyền cho phương thức hoặc trả về từ phương thức đang chạy. Khi mỗi nhánh chỉ cần tạo ra một kết quả, cách viết ngắn gọn nhất là dùng **nhãn mũi tên**:

```java
String label = switch (status) {
    case 0 -> "Chờ xử lý";
    case 1 -> "Đang thực hiện";
    case 2 -> "Hoàn tất";
    default -> "Không xác định";
};
```

Đây là **đoạn mã minh họa**; biến `status` phải được khai báo với kiểu phù hợp trong ngữ cảnh sử dụng.

Trong cú pháp `case 1 -> "Đang thực hiện";`:

- `case 1` là nhãn so khớp giá trị của biểu thức sau `switch (...)`.
- `->` phân cách **nhãn** và **phần xử lý** của nhánh.
- `"Đang thực hiện"` là **biểu thức kết quả trực tiếp**; giá trị của biểu thức này trở thành giá trị của toàn bộ `switch`.
- `;` kết thúc quy tắc nhánh. Khi `switch` nằm trong phép gán hoặc câu lệnh `return`, dấu `;` sau dấu `}` còn kết thúc câu lệnh bao quanh.

**Điểm cốt lõi:** với nhánh đơn giản, viết `case VALUE -> resultExpression;`. Không cần `yield`, `break` hay `return` bên trong nhánh.

## 2. Cách một nhánh mũi tên hoạt động

Khi đánh giá một `switch` biểu thức dạng nhãn mũi tên, Java thực hiện theo thứ tự:

1. Đánh giá biểu thức chọn (**selector**) sau `switch (...)`.
2. Tìm nhãn `case` khớp với giá trị đó. Nếu không có nhãn nào khớp, `default` được chọn nếu có.
3. Chỉ chạy **phần xử lý của nhánh được chọn**. Với nhánh `case ... -> biểu_thức;`, Java đánh giá biểu thức ở bên phải mũi tên và lấy giá trị của nó làm kết quả.
4. Tiếp tục thực thi ở nơi sử dụng kết quả `switch` (phép gán, `return`, lời gọi phương thức, v.v.).

Ví dụ, với `status = 1`, biểu thức `switch` phía trên cho ra `"Đang thực hiện"`. Nhánh `case 2` không chạy, dù nằm ngay bên dưới nhánh `case 1`.

Nhãn mũi tên **không có fall-through** (không chạy xuyên từ nhánh này sang nhánh tiếp theo). Đây là đặc trưng quan trọng khi nhiều nhánh đứng cạnh nhau: không cần đặt `break` để chặn chúng.

Vế phải mũi tên có thể là bất kỳ biểu thức Java hợp lệ và phù hợp với kiểu kết quả cần dùng, chẳng hạn:

```java
case 1 -> 100;                    // Hằng số nguyên
case 2 -> basePrice + 20_000;     // Biểu thức tính toán
case 3 -> message.toUpperCase();  // Lời gọi phương thức trả về String
```

Ba dòng chỉ minh họa **những cách viết vế phải khác nhau**; chúng chưa tạo thành một `switch` độc lập có cùng kiểu kết quả. Trong một `switch` cụ thể, các kết quả phải tương thích với kiểu được yêu cầu ở ngữ cảnh sử dụng.

## 3. Ví dụ Java hoàn chỉnh, chạy được

Lưu nội dung sau vào **`Main.java`**. Ba phương thức minh họa kết quả trực tiếp với `String`, `int` và `boolean`.

```java
public class Main {
    enum Day {
        MONDAY, TUESDAY, WEDNESDAY, THURSDAY,
        FRIDAY, SATURDAY, SUNDAY
    }

    static String shippingStatus(int status) {
        return switch (status) {
            case 0 -> "Chờ xử lý";
            case 1, 2 -> "Đang vận chuyển";
            case 3 -> "Đã giao";
            default -> "Không xác định";
        };
    }

    static int shippingFee(String method) {
        return switch (method) {
            case "STANDARD" -> 15_000;
            case "EXPRESS" -> 15_000 + 20_000;
            case "SAME_DAY" -> 15_000 + 50_000;
            default -> throw new IllegalArgumentException(
                "Phương thức không hợp lệ: " + method
            );
        };
    }

    static boolean isWeekend(Day day) {
        return switch (day) {
            case SATURDAY, SUNDAY -> true;
            case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY -> false;
        };
    }

    public static void main(String[] args) {
        System.out.println(shippingStatus(2));
        System.out.println(shippingStatus(9));
        System.out.println(shippingFee("EXPRESS"));
        System.out.println(isWeekend(Day.SUNDAY));
    }
}
```

Sử dụng JDK 17 hoặc 21 (cú pháp này đã chính thức từ Java 14):

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Kết quả chính xác:**

```text
Đang vận chuyển
Không xác định
35000
true
```

**Phân tích từng trường hợp:**

- `shippingStatus(2)` khớp `case 1, 2`, trả về chuỗi `"Đang vận chuyển"`. Danh sách giá trị cách nhau bằng dấu phẩy vẫn là **một nhãn** và **một kết quả trực tiếp**.
- `shippingStatus(9)` không khớp nhánh cụ thể nào, nên `default` tạo ra `"Không xác định"`.
- `shippingFee("EXPRESS")` chọn nhánh `15_000 + 20_000`, biểu thức cộng được đánh giá thành số nguyên `35000` rồi trả về.
- `isWeekend(Day.SUNDAY)` chọn nhánh có kết quả `true`. Vì tất cả bảy hằng của `Day` đều được liệt kê, `switch` trên `enum` này đã bao phủ đủ giá trị và không cần `default`.

Trong phương thức `shippingFee`, nhánh `default -> throw ...;` **ném ngoại lệ** khi gặp phương thức không hợp lệ. Ném ngoại lệ không trả về một giá trị bình thường, nhưng là một cách thoát hợp lệ khỏi `switch` biểu thức. Ba nhánh hợp lệ vẫn trả về `int`.

## 4. Biểu thức kết quả trực tiếp được dùng ở đâu?

Một `switch` biểu thức có thể xuất hiện ở các vị trí mà Java chấp nhận một biểu thức:

**Gán cho biến:**

```java
int month = 4;
String quarter = switch (month) {
    case 1, 2, 3 -> "Q1";
    case 4, 5, 6 -> "Q2";
    case 7, 8, 9 -> "Q3";
    case 10, 11, 12 -> "Q4";
    default -> "Không hợp lệ";
};
System.out.println(quarter); // Q2
```

Đây là **đoạn mã đặt trong một phương thức** (ví dụ `main`); nó không phải toàn bộ tệp Java.

**Trả về trực tiếp từ phương thức:**

```java
static String roleName(int roleCode) {
    return switch (roleCode) {
        case 1 -> "Quản trị";
        case 2 -> "Biên tập";
        default -> "Khách";
    };
}
```

Ở đây, câu lệnh `return` nằm **trước `switch`**, trả kết quả của toàn bộ biểu thức. Phần bên phải mỗi `->` chỉ là biểu thức chuỗi, không chứa `return`.

**Làm đối số của phương thức:**

```java
int priority = 2;
System.out.println(switch (priority) {
    case 1 -> "Cao";
    case 2 -> "Trung bình";
    default -> "Thấp";
});
```

Đoạn mã đặt trong một phương thức; lời gọi trên in `Trung bình`. Kết quả `switch` được truyền trực tiếp cho `System.out.println`.

Kiểu của các nhánh phải phù hợp với ngữ cảnh: khi `switch` được gán cho biến `String`, không thể trả một `int` ở một nhánh rồi coi đó là `String`. Khi dùng `var`, trình biên dịch suy luận kiểu kết quả từ các biểu thức nhánh và quy tắc suy luận kiểu Java; khi cần một kiểu API rõ ràng, nên khai báo kiểu đích một cách tường minh.

## 5. Khi nào dùng `yield` thay vì trả kết quả trực tiếp?

Với một kết quả duy nhất, cú pháp gọn nhất là:

```java
static String name(int code) {
    return switch (code) {
        case 1 -> "Một";
        case 2 -> "Hai";
        default -> "Khác";
    };
}
```

Khi cần **nhiều câu lệnh** trước khi cho ra kết quả, dùng **khối lệnh** `{ ... }` sau mũi tên; trong khối này, dùng `yield` để cung cấp giá trị cho `switch` biểu thức:

```java
static String nameWithPrefix(int code) {
    return switch (code) {
        case 1 -> {
            String prefix = "Số ";
            yield prefix + "một";
        }
        case 2 -> "Số hai";
        default -> "Số khác";
    };
}
```

- `case 1 -> { ... yield ...; }` chứa khối nhiều lệnh và dùng `yield` để kết thúc nhánh với một giá trị.
- `case 2 -> "Số hai";` trả kết quả **trực tiếp**, không có khối và không cần `yield`.
- `yield` khác `return`: `yield` chỉ trả giá trị cho biểu thức `switch`, còn `return` kết thúc phương thức bao quanh.
- Không viết `case 1 -> yield "Một";` như một nhánh kết quả trực tiếp; nếu cần `yield`, hãy dùng khối `{ yield "Một"; }`.

Vì thế **`->` là cú pháp nhãn nhánh**, còn **`yield` là lệnh sinh kết quả từ một khối**. Chúng giải quyết hai vai trò khác nhau và có thể đi cùng nhau.

## 6. Mũi tên trong `switch` biểu thức và `switch` câu lệnh

Nhãn `case ... ->` cũng dùng được trong **`switch` câu lệnh**. Sự khác nhau nằm ở việc cấu trúc có tạo ra một **giá trị** hay chỉ thực thi **hành động**.

Ví dụ `switch` câu lệnh:

```java
int choice = 1;
switch (choice) {
    case 1 -> System.out.println("Đã chọn một");
    case 2 -> System.out.println("Đã chọn hai");
    default -> System.out.println("Không hợp lệ");
}
```

Đây là đoạn mã đặt trong phương thức. Nó in `Đã chọn một` nhưng bản thân cấu trúc `switch` **không cung cấp giá trị** để gán. Vì là câu lệnh nên nó không cần dấu `;` sau dấu `}`.

Ví dụ `switch` biểu thức:

```java
int choice = 1;
String message = switch (choice) {
    case 1 -> "Đã chọn một";
    case 2 -> "Đã chọn hai";
    default -> "Không hợp lệ";
};
System.out.println(message);
```

Ở đây toàn bộ `switch` sinh ra một `String` để gán cho `message`. Dấu `;` sau `}` kết thúc câu lệnh khai báo biến.

**Lưu ý:** `System.out.println(...)` trả về kiểu `void`. Vì vậy trong một `switch` biểu thức cần cho ra `String`, không thể dùng `case 1 -> System.out.println("Một");` làm nhánh sinh kết quả. Muốn vừa ghi log vừa tạo giá trị, dùng khối `-> { ...; yield value; }`.

## 7. Độ bao phủ và xử lý trường hợp không hợp lệ

Một `switch` **biểu thức** phải bao phủ các giá trị selector có thể xảy ra, sao cho khi thực thi sẽ **cho ra giá trị hoặc ném ngoại lệ**. Quy tắc cần nhớ:

- Với `int` hoặc `String`, thông thường có nhánh `default` để xử lý các giá trị ngoài danh sách, vì các nhãn cụ thể không bao phủ hết mọi giá trị.
- Với `enum`, có thể bỏ `default` nếu các nhãn bao phủ toàn bộ hằng trong kiểu `enum`. Khi tập hằng thay đổi, phải xem lại tính đầy đủ của nhánh.
- Với nhánh kết quả trực tiếp, giá trị ở bên phải `->` phải có kiểu phù hợp với kết quả toàn biểu thức.
- Nhánh `throw` hợp lệ khi đầu vào cần được từ chối rõ ràng. Nên phân biệt trường hợp cần giá trị mặc định với trường hợp dữ liệu thực sự không hợp lệ.

Lưu ý về `null`: khi biên dịch theo Java 14/17, nếu selector tham chiếu như `String` hoặc `enum` là `null`, `switch` thông thường ném `NullPointerException` trước khi chọn nhánh. Có thể xác thực đầu vào trước khi `switch` (ví dụ `Objects.requireNonNull(...)`). Các mở rộng `switch` ở Java mới hơn có cách xử lý `null` riêng; không nên giả định `default` ở Java 14/17 tự xử lý `null`.

## 8. Các lỗi phổ biến

| Cách viết hoặc tình huống | Kết luận |
| --- | --- |
| `case 1 -> "Một";` | Đúng: một nhánh, một kết quả chuỗi trực tiếp. |
| `case 1, 2 -> "Nhóm A";` | Đúng: nhiều hằng so khớp chung một kết quả. |
| `case 1 -> value + 1;` | Đúng nếu `value + 1` là biểu thức hợp lệ và phù hợp kiểu kết quả. |
| `case 1 -> { yield "Một"; }` | Đúng: khối nhánh cung cấp kết quả bằng `yield`. |
| `case 1 -> return "Một";` | Sai trong `switch` biểu thức: vế phải `->` không nhận lệnh `return` trực tiếp. |
| `case 1 -> yield "Một";` | Sai: `yield` không phải biểu thức đặt trực tiếp ở vị trí kết quả; dùng khối. |
| `case 1 -> { String text = "Một"; }` | Sai nếu đây là nhánh `switch` biểu thức: khối không tạo ra kết quả, cần `yield text;`. |
| `case 1 -> System.out.println("Một");` khi cần `String` | Sai: lời gọi có kiểu `void`, không tạo ra `String`. |
| `case 1 -> "Một"; case 1 -> "Lần nữa";` | Sai: một giá trị `case` bị khai báo trùng. |
| `switch` biểu thức trên `int` không đủ nhánh và thiếu `default` | Sai: không bảo đảm tính đầy đủ của biểu thức. |

Các trường hợp **cố ý sai** sau chỉ để nhận biết lỗi biên dịch:

```java
// Sai: return không được đặt trực tiếp sau nhãn ->
case 1 -> return "Một";

// Sai: yield phải xuất hiện bên trong khối phù hợp
case 2 -> yield "Hai";

// Sai trong switch biểu thức: khối thiếu yield
case 3 -> {
    String text = "Ba";
}
```

Các dòng trên là đoạn trích minh họa lỗi, không phải chương trình độc lập.

## 9. Cách áp dụng trong mã thực tế

Ưu tiên **`case CONSTANT -> expression;`** khi mỗi giá trị đầu vào ánh xạ tới **một kết quả rõ ràng**, ví dụ mã trạng thái thành nhãn hiển thị, tên loại dịch vụ thành phí, hoặc loại ngày thành cờ `boolean`. Mỗi nhánh dễ kiểm tra độc lập và không lo chạy xuyên giữa các nhánh.

Khi nhiều giá trị đầu vào cần cùng kết quả, nhóm chúng trong **một nhãn** bằng dấu phẩy. Khi nhánh cần nhiều bước hoặc phải ghi log trước khi trả kết quả, chuyển **chính nhánh đó** sang khối `-> { ... yield result; }`; các nhánh đơn giản khác vẫn có thể dùng kết quả trực tiếp.

Tự kiểm tra với phương thức dưới đây (đặt trong một lớp Java):

```java
static String severity(int code) {
    return switch (code) {
        case 0 -> "INFO";
        case 1, 2 -> "WARN";
        case 3 -> "ERROR";
        default -> "UNKNOWN";
    };
}
```

Kết quả lần lượt là `severity(0) = "INFO"`, `severity(2) = "WARN"`, `severity(3) = "ERROR"` và `severity(5) = "UNKNOWN"`.

**Ghi nhớ:** `case ... -> một_biểu_thức;` lấy trực tiếp giá trị biểu thức bên phải làm kết quả của `switch` biểu thức. Cú pháp này tránh fall-through, không cần `break`; chỉ cần `yield` khi chuyển sang khối nhiều lệnh. Bảo đảm mọi nhánh hợp lệ trả đúng kiểu, và bảo đảm toàn bộ `switch` được bao phủ đầy đủ.