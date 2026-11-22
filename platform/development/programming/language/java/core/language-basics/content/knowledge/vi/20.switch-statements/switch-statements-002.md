# Nhãn `case`, `default` và nhãn trùng lặp trong Java

> **Java core — language-basics / Switch**  
> **Môi trường:** Java 17+, không bật preview, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Chọn đúng nhãn `case`, hiểu `default` và trường hợp không khớp, nhận biết lỗi nhãn trùng; phân biệt cú pháp `case ...:` truyền thống với `case ... ->` hiện đại.

## 1. Nhãn `case` dùng để làm gì?

`switch` đánh giá biểu thức chọn (*selector*) và đối chiếu kết quả với các nhãn. Trong một chuỗi `if/else if`, ta viết điều kiện; với `switch`, ta liệt kê các giá trị được chọn:

~~~java
int code = 2;

switch (code) {
    case 1:
        System.out.println("ONE");
        break;
    case 2:
        System.out.println("TWO");
        break;
    default:
        System.out.println("OTHER");
}
// In: TWO
~~~

Ở đây:

- `case 1:` và `case 2:` là nhãn cho hai giá trị.
- `default:` là điểm bắt đầu khi không nhãn `case` nào khớp.
- `break` thoát `switch` dạng câu lệnh, tránh chạy tiếp từ nhánh đang chọn vào nhánh phía sau.

Một `switch` có thể có nhiều nhãn `case` nhưng **không được có hai nhãn mang cùng giá trị** trong cùng một khối.

## 2. Loại giá trị nào dùng được làm nhãn?

Với `switch` thông thường trong Java 17 (không bật preview), selector hỗ trợ các kiểu nguyên `byte`, `short`, `char`, `int`, các lớp bao tương ứng, `String` và `enum`. Không dùng trực tiếp `long`, `float`, `double` hoặc `boolean` làm selector.

Đối với số nguyên/chuỗi, nhãn `case` thông thường phải là **biểu thức hằng tại thời điểm biên dịch** (*compile-time constant*) với kiểu phù hợp selector; không được là kết quả tính lúc chạy:

~~~java
static final int BASE = 2;

// Hợp lệ trong switch (code):
// case 1:
// case BASE + 1:     // Hằng số 3 vì BASE là constant variable.
// case 'A':          // Ký tự có giá trị số tương ứng; hợp lệ với int.
~~~

Ví dụ không hợp lệ (chỉ minh họa, không đưa vào chương trình chạy):

~~~java
int runtime = 2;
// case runtime:             // Không phải hằng tại compile time.
// case Integer.parseInt("2"): // Lời gọi hàm không là hằng compile time.
~~~

Nếu selector là `byte` thì nhãn nguyên `case 128` không hợp lệ vì ngoài miền giá trị `byte`. Nếu selector là `String` thì dùng nhãn chuỗi hằng như `case "go"`. Với `enum`, nhãn dùng **tên hằng chưa định danh kiểu**, ví dụ `case LOW`, không phải `case Level.LOW` trong switch thông thường của Java 17.

## 3. Nhãn trùng lặp: lỗi ngay khi biên dịch

Nhãn trùng không nhất thiết phải viết giống hệt nhau. Hai biểu thức hằng có **cùng giá trị sau khi tính** cũng trùng:

~~~java
// KHÔNG BIÊN DỊCH — hai nhãn cùng là 2:
// switch (number) {
//     case 2:   System.out.println("first");  break;
//     case 1+1: System.out.println("second"); break;
// }
~~~

Tương tự:

~~~java
// KHÔNG BIÊN DỊCH trong một switch (int):
// case 65:
// case 'A': // Ký tự 'A' có giá trị 65.

// KHÔNG BIÊN DỊCH trong một switch (String):
// case "go":
// case "g" + "o": // Cùng chuỗi hằng "go".
~~~

Các nhãn trùng không trở thành “hai lựa chọn đều đúng” như hai `if` độc lập. Java **từ chối biên dịch** vì hai nhãn trong cùng `switch` không thể phân biệt.

**Cách sửa:** Gộp nhãn nếu nhiều giá trị khác nhau thực sự dùng chung một cách xử lý, hoặc chỉ giữ **một** nhãn cho cùng một giá trị. Không thể chữa hai nhãn trùng bằng cách thêm `break`.

## 4. Gộp nhiều nhãn hợp lệ vào một nhánh

Trong `switch` truyền thống, nhiều `case` liên tiếp có thể dẫn tới cùng thân:

~~~java
switch (code) {
    case 1:
    case 2:
        System.out.println("SMALL");
        break;
    default:
        System.out.println("OTHER");
}
~~~

Trong cú pháp mũi tên Java 17, dùng danh sách nhãn:

~~~java
String group = switch (code) {
    case 1, 2 -> "SMALL";
    case 3 -> "THREE";
    default -> "OTHER";
};
~~~

**`case 1, 2` là hai giá trị khác nhau trong cùng một nhóm** — hoàn toàn hợp lệ. Nhưng `case 1, 1` hoặc đặt thêm `case 2` ở nhánh khác vẫn là nhãn trùng.

Các nhánh `->` **không tự chạy xuyên xuống nhánh sau** (*no fall-through*); có thể dùng `switch` như một biểu thức để trả về giá trị. Đừng trộn dạng `case ...:` và `case ... ->` trong cùng một `switch`.

## 5. Vai trò và vị trí của `default`

`default` được dùng khi **không có nhãn `case` nào khớp**, không phải “nhánh luôn chạy sau mọi case”:

~~~java
int code = 9;
switch (code) {
    case 1:
        System.out.println("ONE");
        break;
    default:
        System.out.println("OTHER"); // code = 9.
}
~~~

Các điều cần nhớ:

- Tối đa **một** nhãn `default` trong một `switch`; khai báo `default` hai lần là lỗi biên dịch.
- Với `switch` **statement**, `default` có thể không có; nếu không nhãn nào khớp và không có `default` thì bỏ qua thân `switch`.
- Với `switch` **expression**, mọi giá trị có thể phải được bao phủ (*exhaustive*); các nhãn `int` hoặc `String` thông thường cần `default`. Riêng switch expression trên `enum` có thể bỏ `default` nếu liệt kê đủ mọi hằng enum.
- Trong `switch` dạng dấu hai chấm `:`, `default` **không bắt buộc nằm cuối**. Nếu thiếu `break`, thực thi có thể tiếp tục từ `default` sang `case` ở sau.
- `default` không xử lý `null` cho `String`/enum/wrapper selector trong Java 17 không bật preview; giá trị selector `null` gây `NullPointerException` trước khi vào nhánh.

Ví dụ cố ý đặt `default` giữa các nhãn để thấy fall-through:

~~~java
static String unusualOrder(int code) {
    StringBuilder result = new StringBuilder();
    switch (code) {
        case 0:
            result.append("ZERO");
            break;
        default:
            result.append("DEFAULT-");
        case 2:
            result.append("TWO");
            break;
    }
    return result.toString();
}
// unusualOrder(0) = "ZERO"
// unusualOrder(2) = "TWO"
// unusualOrder(9) = "DEFAULT-TWO"
~~~

Đây là cú pháp hợp lệ nhưng **không khuyến nghị** khi không chủ ý fall-through. Thực tế nên đặt `default` rõ ràng, dùng `break` với `:` hoặc ưu tiên `->` khi chỉ muốn một nhánh.

## 6. `String`, `enum` và tính tương thích Java 17

`switch` trên `String` đối chiếu **nội dung chuỗi** chứ không phải chỉ so sánh hai tham chiếu bằng `==`; phân biệt chữ hoa/chữ thường:

~~~java
String text = new String("go");

String action = switch (text) {
    case "go" -> "MOVE";
    case "stop" -> "HALT";
    default -> "UNKNOWN";
};
// action = "MOVE".
~~~

Với `enum`:

~~~java
enum Level { LOW, MEDIUM, HIGH }

static String label(Level level) {
    return switch (level) {
        case LOW -> "low";
        case MEDIUM -> "medium";
        case HIGH -> "high";
    };
}
~~~

Biểu thức `switch` trên `Level` đã liệt kê đủ ba hằng, nên không cần `default`. Nếu `level == null`, vẫn ném `NullPointerException`. Hãy kiểm tra `null` **trước switch** nếu dữ liệu có thể thiếu.

Các cú pháp như `case null` hoặc mẫu kiểu (*pattern matching for switch*) không thuộc switch Java 17 tiêu chuẩn khi không bật tính năng preview; không dùng chúng để thay thế `default` trong bài này.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **SwitchCaseLabelsDemo.java**:

~~~java
public final class SwitchCaseLabelsDemo {
    private static final int BASE = 2;

    enum Level { LOW, MEDIUM, HIGH }

    private static String classic(int code) {
        switch (code) {
            case 1:
            case 2:
                return "SMALL";
            case 3:
                return "THREE";
            default:
                return "OTHER";
        }
    }

    private static String arrow(int code) {
        return switch (code) {
            case 1, 2 -> "SMALL";
            case 3 -> "THREE";
            default -> "OTHER";
        };
    }

    private static String constantCase(int code) {
        return switch (code) {
            case BASE + 1 -> "THREE";
            default -> "OTHER";
        };
    }

    private static String byText(String text) {
        return switch (text) {
            case "go" -> "MOVE";
            case "stop" -> "HALT";
            default -> "UNKNOWN";
        };
    }

    private static String byLevel(Level level) {
        return switch (level) {
            case LOW -> "low";
            case MEDIUM -> "medium";
            case HIGH -> "high";
        };
    }

    private static String unusualOrder(int code) {
        StringBuilder result = new StringBuilder();
        switch (code) {
            case 0:
                result.append("ZERO");
                break;
            default:
                result.append("DEFAULT-");
            case 2:
                result.append("TWO");
                break;
        }
        return result.toString();
    }

    public static void main(String[] args) {
        System.out.println("classic1=" + classic(1));
        System.out.println("classic2=" + classic(2));
        System.out.println("classic3=" + classic(3));
        System.out.println("classic9=" + classic(9));
        System.out.println("arrow2=" + arrow(2));
        System.out.println("arrow3=" + arrow(3));
        System.out.println("arrow9=" + arrow(9));
        System.out.println("constant3=" + constantCase(3));

        System.out.println("stringGo=" + byText(new String("go")));
        System.out.println("stringStop=" + byText("stop"));
        System.out.println("stringOther=" + byText("GO"));
        System.out.println("enumLow=" + byLevel(Level.LOW));
        System.out.println("enumHigh=" + byLevel(Level.HIGH));

        System.out.println("default0=" + unusualOrder(0));
        System.out.println("default2=" + unusualOrder(2));
        System.out.println("default9=" + unusualOrder(9));

        try {
            byText(null);
        } catch (NullPointerException ex) {
            System.out.println("nullSelector=NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 SwitchCaseLabelsDemo.java
java SwitchCaseLabelsDemo
~~~

**Expected stdout chính xác:**

~~~text
classic1=SMALL
classic2=SMALL
classic3=THREE
classic9=OTHER
arrow2=SMALL
arrow3=THREE
arrow9=OTHER
constant3=THREE
stringGo=MOVE
stringStop=HALT
stringOther=UNKNOWN
enumLow=low
enumHigh=high
default0=ZERO
default2=TWO
default9=DEFAULT-TWO
nullSelector=NullPointerException
~~~

Ví dụ `default9=DEFAULT-TWO` cố ý cho thấy **fall-through trong switch dạng `:`** khi `default` đứng trước `case 2` mà không có `break`. Đây không phải hành vi của dạng `->`.

## 8. Lỗi thường gặp và bài tập

| Lỗi | Nguyên nhân | Cách tránh |
| --- | --- | --- |
| `case 2` và `case 1 + 1` | Trùng giá trị hằng | Chỉ giữ một giá trị |
| `case value` với biến thường | Giá trị không phải compile-time constant | Dùng hằng hợp lệ hoặc `if` |
| Hai nhãn `default` | `default` phải duy nhất | Chỉ có một nhánh mặc định |
| Quên `break` ở cú pháp `:` | Fall-through ngoài ý muốn | Thêm `break` hoặc dùng `->` |
| Cho rằng `default` bắt `null` | Java 17 không bật preview không làm vậy | Kiểm tra `null` trước |
| Đặt `case Level.LOW` cho enum | Nhãn enum phải viết tên không định danh kiểu | Dùng `case LOW` |
| Bỏ `default` khi switch expression không exhaustive | Không có kết quả cho mọi giá trị | Thêm `default` hoặc bao phủ đủ enum |

**Bài 1.** Viết `switch` để mã 1 và 2 dùng chung kết quả `"SMALL"`, mã 3 là `"THREE"` và mọi mã khác là `"OTHER"`. Thực hiện bằng cả `:` và `->`.

**Bài 2.** Giải thích vì sao trong cùng một switch `int`, hai nhãn `case 3` và `case 1 + 2` bị từ chối dù khác cách viết.

**Bài 3.** Thử thêm nhãn `default` thứ hai vào một `switch` mẫu. Nêu loại lỗi xảy ra và sửa thế nào.

**Bài 4.** Dự đoán `unusualOrder(9)` và `unusualOrder(2)`. Vì sao không giống nhau dù `default` nằm trước `case 2`?

**Bài 5.** Viết `switch` expression trên enum có đủ ba hằng; giải thích khi nào có thể bỏ `default`, và xử lý trước thế nào nếu selector nullable.

### Ghi nhớ

**`case` chọn giá trị hằng hợp lệ, các nhãn trong cùng `switch` không được trùng giá trị.** `default` là nhánh khi không có case khớp, tối đa một nhãn và không tự xử lý `null` trong Java 17 tiêu chuẩn. Dùng nhiều nhãn **khác nhau** để gộp xử lý; nhớ `break` ở cú pháp `:` hoặc dùng `->` để tránh fall-through ngoài ý muốn.
