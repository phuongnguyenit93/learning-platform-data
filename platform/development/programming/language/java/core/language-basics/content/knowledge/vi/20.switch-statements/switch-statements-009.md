# Xử lý `null` trong `switch` và phân biệt với `default` — Java 17+

**`default` không phải nhánh xử lý `null`.** Trong `switch` Java 17 sử dụng tính năng chuẩn, nếu biểu thức chọn (*selector*) có giá trị `null`, chương trình ném `NullPointerException` **trước khi đi vào bất kỳ nhãn `case` hoặc `default` nào**.

~~~java
String status = null;

// Đoạn này sẽ ném NullPointerException tại runtime:
// switch (status) {
//     case "ON" -> System.out.println("enabled");
//     default -> System.out.println("unknown");
// }
~~~

Ngược lại, `default` chạy khi selector **không null**, nhưng không trùng với bất cứ nhãn `case` nào:

~~~java
String status = "PAUSE";
switch (status) {
    case "ON" -> System.out.println("enabled");
    case "OFF" -> System.out.println("disabled");
    default -> System.out.println("unknown"); // Chạy nhánh này.
}
~~~

## 1. Phân biệt trường hợp không khớp và `null`

| Giá trị selector `String` | Có khớp `case "ON"`? | `default` chạy? | Hành vi |
| --- | --- | --- | --- |
| `"ON"` | Có | Không | Chạy `case "ON"` |
| `"OFF"` | Không, nhưng khớp case khác | Không | Chạy `case "OFF"` |
| `"PAUSE"` | Không | Có | Chạy `default` |
| `""` (chuỗi rỗng) | Không | Có | Chạy `default` |
| `null` | Không xét case | **Không** | Ném `NullPointerException` |

Chuỗi rỗng `""` là **một đối tượng `String` không null**, nên hoàn toàn có thể được xử lý bởi `default`. `null` thì không trỏ tới đối tượng `String` nào.

Điều này áp dụng cho cả **switch statement** và **switch expression** trong Java 17 tiêu chuẩn, kể cả khi đã khai báo `default` đầy đủ.

## 2. Cách an toàn: kiểm tra `null` trước `switch`

### Trả kết quả riêng cho dữ liệu thiếu

~~~java
static String describe(String status) {
    if (status == null) {
        return "missing";
    }
    return switch (status) {
        case "ON" -> "enabled";
        case "OFF" -> "disabled";
        default -> "unknown";
    };
}
~~~

- `"missing"`: đầu vào **không tồn tại**.
- `"unknown"`: đầu vào **có tồn tại**, nhưng không phải `"ON"` hay `"OFF"`.
- Các nhánh `case`: những giá trị hợp lệ được nhận diện.

Đây là hai trạng thái nghiệp vụ khác nhau. Không tự động gộp `null` với `default` nếu ứng dụng cần phân biệt “chưa nhập” và “đã nhập nhưng không hợp lệ”.

### Báo lỗi thay vì tạo giá trị thay thế

Nếu `null` vi phạm hợp đồng phương thức, có thể từ chối rõ ràng:

~~~java
static String requireStatus(String status) {
    if (status == null) {
        throw new IllegalArgumentException("status required");
    }
    return switch (status) {
        case "ON" -> "enabled";
        default -> "unknown";
    };
}
~~~

`IllegalArgumentException` ở đây thể hiện chính sách **do chương trình lựa chọn**. Còn `NullPointerException` tự phát sinh từ `switch(null)` thường khiến nơi gặp lỗi khó giải thích ý nghĩa nghiệp vụ hơn.

## 3. Ví dụ Java 17+ độc lập, runnable CLI

Tạo file UTF-8 **`SwitchNullDemo.java`**:

~~~java
public class SwitchNullDemo {
    enum Mode { START, STOP }

    static String statement(String code) {
        if (code == null) {
            return "missing";
        }
        String result;
        switch (code) {
            case "ON":
                result = "enabled";
                break;
            case "OFF":
                result = "disabled";
                break;
            default:
                result = "unknown";
        }
        return result;
    }

    static String expression(String code) {
        if (code == null) {
            return "missing";
        }
        return switch (code) {
            case "ON" -> "enabled";
            case "OFF" -> "disabled";
            default -> "unknown";
        };
    }

    static String number(Integer n) {
        if (n == null) {
            return "missing";
        }
        return switch (n) {
            case 0 -> "zero";
            case 1 -> "one";
            default -> "other";
        };
    }

    static String mode(Mode m) {
        if (m == null) {
            return "missing";
        }
        return switch (m) {
            case START -> "start";
            case STOP -> "stop";
        };
    }

    static String rawString(String code) {
        return switch (code) {
            case "ON" -> "enabled";
            default -> "default";
        };
    }

    static String rawNumber(Integer n) {
        return switch (n) {
            case 0 -> "zero";
            default -> "default";
        };
    }

    static String rawMode(Mode m) {
        return switch (m) {
            case START -> "start";
            case STOP -> "stop";
        };
    }

    static String requireCode(String code) {
        if (code == null) {
            throw new IllegalArgumentException("code required");
        }
        return rawString(code);
    }

    public static void main(String[] args) {
        System.out.println("== String guard ==");
        for (String s : new String[] {null, "ON", "OFF", "PAUSE", ""}) {
            System.out.println("input=" + String.valueOf(s)
                    + ",statement=" + statement(s)
                    + ",expression=" + expression(s));
        }

        System.out.println("== wrapper and enum ==");
        System.out.println("numberNull=" + number(null));
        System.out.println("number0=" + number(0));
        System.out.println("number9=" + number(9));
        System.out.println("modeNull=" + mode(null));
        System.out.println("modeStart=" + mode(Mode.START));
        System.out.println("modeStop=" + mode(Mode.STOP));

        System.out.println("== default versus null ==");
        System.out.println("unmatched=" + rawString("PAUSE"));
        System.out.println("empty=" + rawString(""));
        System.out.println("unmatchedNumber=" + rawNumber(7));

        try {
            System.out.println("unexpected=" + rawString(null));
        } catch (NullPointerException ex) {
            System.out.println("nullString=NullPointerException");
        }
        try {
            System.out.println("unexpected=" + rawNumber(null));
        } catch (NullPointerException ex) {
            System.out.println("nullNumber=NullPointerException");
        }
        try {
            System.out.println("unexpected=" + rawMode(null));
        } catch (NullPointerException ex) {
            System.out.println("nullMode=NullPointerException");
        }

        System.out.println("== explicit contract ==");
        try {
            requireCode(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
        System.out.println("required=" + requireCode("ON"));

        String maybeNull = null;
        String safe = maybeNull == null
                ? "missing"
                : rawString(maybeNull);
        System.out.println("ternary=" + safe);
    }
}
~~~

Dùng **JDK 17 trở lên**, mở PowerShell hoặc Bash tại thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SwitchNullDemo.java
java SwitchNullDemo
~~~

**Exact expected stdout** từ riêng lệnh `java SwitchNullDemo`:

~~~text
== String guard ==
input=null,statement=missing,expression=missing
input=ON,statement=enabled,expression=enabled
input=OFF,statement=disabled,expression=disabled
input=PAUSE,statement=unknown,expression=unknown
input=,statement=unknown,expression=unknown
== wrapper and enum ==
numberNull=missing
number0=zero
number9=other
modeNull=missing
modeStart=start
modeStop=stop
== default versus null ==
unmatched=default
empty=default
unmatchedNumber=default
nullString=NullPointerException
nullNumber=NullPointerException
nullMode=NullPointerException
== explicit contract ==
invalid=code required
required=enabled
ternary=missing
~~~

Đầu ra của hai lệnh `-version` phụ thuộc bản JDK trên máy; chúng không thuộc khối stdout cố định.

## 4. `String`, wrapper và `enum` đều cần chú ý `null`

| Kiểu selector trong Java 17 | Selector không null | Selector null |
| --- | --- | --- |
| `String` | Khớp theo **nội dung** với nhãn chuỗi | Ném `NullPointerException` |
| `Integer`, `Byte`, `Short`, `Character` | Giá trị wrapper được xử lý theo quy tắc `switch` số nguyên | Ném `NullPointerException` |
| `enum` | Khớp tên hằng enum | Ném `NullPointerException` |
| `int`, `byte`, `short`, `char` | Dùng giá trị nguyên thủy | **Không thể** là null |

Trong demo, `rawNumber(null)` gây lỗi do selector wrapper không có giá trị để dùng; `rawMode(null)` cũng không được `default` “bắt hộ”.

**Không nhầm `default` với `case null`.** Trong Java 17 biên dịch thông thường (không bật preview), không viết `case null -> ...` cho switch theo cú pháp chuẩn. Các ví dụ về `case null` trong tài liệu Java mới hơn thường thuộc **pattern matching for switch**, được chuẩn hóa từ Java 21; Java 17 chỉ có tính năng liên quan ở dạng preview với yêu cầu cấu hình riêng, **không áp dụng vào bài chạy CLI tiêu chuẩn này**.

## 5. Khi nào cần `default`?

`default` dành cho **giá trị hợp lệ về kiểu nhưng không khớp case**:

~~~java
String code = "MAYBE";
String result = switch (code) {
    case "YES" -> "accepted";
    case "NO" -> "rejected";
    default -> "unrecognized";
};
~~~

Với `"MAYBE"`, kết quả là `"unrecognized"`.

Với **switch expression**, trình biên dịch yêu cầu các trường hợp được bao phủ đầy đủ (*exhaustive*). Với `String` hay `int`, điều này thường đòi hỏi `default`. Với một `enum`, liệt kê đủ hằng số có thể không cần `default`, ví dụ `switch(Mode)` trong chương trình.

Tính đầy đủ đó **không đồng nghĩa chấp nhận null**. Biểu thức switch trên enum liệt kê đủ hằng vẫn gây lỗi nếu selector là `null`.

## 6. Chọn chính sách xử lý rõ ràng

Ba chính sách phổ biến:

| Chính sách | Khi `null` | Khi không khớp case |
| --- | --- | --- |
| Trả kết quả riêng | `"missing"` | `"unknown"` |
| Từ chối dữ liệu | `throw IllegalArgumentException` | `throw` hoặc `default` báo lỗi khác |
| Chuyển sang giá trị thay thế | Chỉ khi có quy ước nghiệp vụ rõ ràng | `default` theo quy ước |

Có thể viết kiểm tra ngắn bằng toán tử `?:`:

~~~java
String result = code == null
        ? "missing"
        : switch (code) {
            case "ON" -> "enabled";
            default -> "unknown";
        };
~~~

Do `?:` chỉ đánh giá nhánh được chọn, nếu `code == null` thì `switch` **không được đánh giá**. Nhưng nếu kiểm tra nhiều điều kiện hoặc cần nhiều lệnh, phương thức có guard `if (code == null)` thường dễ đọc hơn.

Không dùng một “giá trị giả” như `""` để thay null mà không cân nhắc va chạm với dữ liệu hợp lệ: chuỗi rỗng có thể mang ý nghĩa riêng.

## 7. Những lỗi thường gặp

| Hiểu nhầm | Cách đúng |
| --- | --- |
| “`default` chạy khi selector null.” | Sai với switch Java 17 tiêu chuẩn; ném NPE |
| “`case "ON"` so sánh bằng tham chiếu `==`.” | Switch `String` khớp theo nội dung chuỗi |
| “Một wrapper null sẽ tự đổi thành số 0.” | Null không có giá trị để unbox |
| “`enum` đã liệt kê đủ case thì null tự được xử lý.” | Không; vẫn cần guard nếu có thể null |
| “`""` chính là null.” | Chuỗi rỗng là `String` không null |
| “Java 17 chuẩn có thể dùng `case null` như Java 21.” | Không nếu biên dịch bình thường không bật preview |
| “Dùng `default` là đã xác thực đầu vào.” | Chỉ bao phủ nhãn không khớp, không thay thế kiểm tra hợp lệ nghiệp vụ |

## 8. Bài tập tự kiểm tra

1. `switch("UNKNOWN")` có `default` thì sao?  
   *Đáp án:* Chạy `default` nếu không case nào khác khớp.
2. `switch((String) null)` có `default` thì sao trong Java 17 tiêu chuẩn?  
   *Đáp án:* `NullPointerException` trước khi chạy default.
3. `String s = "";` có được default xử lý không?  
   *Đáp án:* Có, nếu không có nhãn khớp chuỗi rỗng.
4. `Integer n = null; switch(n) {...}` có tự hiểu n bằng 0 không?  
   *Đáp án:* Không; ném NPE.
5. Switch expression liệt kê đủ mọi hằng enum nhưng không có default có xử lý null không?  
   *Đáp án:* Không.
6. Khi dữ liệu thiếu và dữ liệu không nhận diện là hai trạng thái khác nhau, nên làm gì?  
   *Đáp án:* Kiểm tra null trước switch, trả kết quả riêng cho hai tình huống.

## Checklist

- [ ] `default` xử lý **không khớp case**, không tự xử lý `null`.
- [ ] Kiểm tra `null` trước switch Java 17 đối với `String`, wrapper và enum có thể thiếu.
- [ ] Phân biệt switch statement và switch expression nhưng nhớ cả hai đều cần kiểm soát selector null.
- [ ] Chọn chính sách trả kết quả hoặc ném ngoại lệ rõ ràng.
- [ ] Không dùng `case null` trong ví dụ Java 17 tiêu chuẩn không có preview.
- [ ] Dùng `default` để bao phủ trường hợp còn lại, không xem đó là kiểm tra toàn bộ tính hợp lệ của đầu vào.

**Kết luận:** Trong Java 17 tiêu chuẩn, `default` có nghĩa **“không case nào khớp với một selector hợp lệ, không null”**, chứ không có nghĩa **“mọi trường hợp còn lại kể cả null”**. Kiểm tra `null` trước, rồi dùng `case` và `default` để xử lý giá trị có mặt.
