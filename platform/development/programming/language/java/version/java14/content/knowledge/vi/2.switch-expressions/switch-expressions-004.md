# Nhãn `case` có nhiều hằng phân tách bằng dấu phẩy trong `switch` biểu thức (Java 14+)

## 1. Ý nghĩa và cú pháp

Trong `switch` biểu thức, một nhãn `case` có thể chứa **nhiều hằng số, ngăn cách bằng dấu phẩy**. Chỉ cần giá trị đang xét khớp **một** trong các hằng đó thì cùng một nhánh được chọn. Cú pháp này đã là tính năng chính thức từ Java 14 và vẫn dùng được trong các phiên bản Java hiện đại.

```java
String result = switch (code) {
    case 1, 2, 3 -> "Nhóm A";
    case 4, 5    -> "Nhóm B";
    default      -> "Nhóm khác";
};
```

Ở đây, `code` bằng `1`, `2` **hoặc** `3` đều trả về `"Nhóm A"`. Dấu phẩy là phần của **một nhãn `case`**, không phải phép toán OR (||), không phải khoảng số, và không tạo ra nhiều lượt thực thi. Mỗi nhánh dạng `->` cho ra một kết quả; không cần `break` và không xảy ra hiện tượng chạy xuyên sang nhánh kế tiếp (*fall-through*).

Mô hình tổng quát: `case HANG_1, HANG_2, ... -> gia_tri;`. Các hằng trong cùng nhóm phải tương thích với kiểu biểu thức sau `switch (...)` và cùng được xử lý một cách.

## 2. Ví dụ hoàn chỉnh: gom ngày và tháng

Lưu mã sau vào **`Main.java`**:

```java
public class Main {
    enum Day {
        MONDAY, TUESDAY, WEDNESDAY, THURSDAY,
        FRIDAY, SATURDAY, SUNDAY
    }

    static String dayType(Day day) {
        return switch (day) {
            case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY
                -> "Ngày làm việc";
            case SATURDAY, SUNDAY
                -> "Cuối tuần";
        };
    }

    static int quarter(int month) {
        return switch (month) {
            case 1, 2, 3   -> 1;
            case 4, 5, 6   -> 2;
            case 7, 8, 9   -> 3;
            case 10, 11, 12 -> 4;
            default -> throw new IllegalArgumentException(
                "Tháng không hợp lệ: " + month
            );
        };
    }

    public static void main(String[] args) {
        System.out.println(dayType(Day.MONDAY));
        System.out.println(dayType(Day.SUNDAY));
        System.out.println(quarter(3));
        System.out.println(quarter(11));
    }
}
```

Biên dịch và chạy bằng JDK 14 trở lên (ví dụ JDK 17 hoặc 21):

```bash
javac Main.java
java Main
```

Kết quả chính xác:

```text
Ngày làm việc
Cuối tuần
1
4
```

**Phân tích:**

- Với `Day.MONDAY`, hằng `MONDAY` nằm trong danh sách của nhãn đầu tiên nên `switch` trả về `"Ngày làm việc"`. Với `SUNDAY`, nhánh thứ hai trả về `"Cuối tuần"`.
- Hai nhãn `case` của `dayType` đã liệt kê đủ cả bảy giá trị `Day`, vì vậy biểu thức `switch` trên `enum` này không cần `default`. Nếu thêm một hằng `Day` mới, cần xem lại độ bao phủ của các nhánh khi biên dịch.
- Với `quarter`, mỗi nhóm ba số nguyên dẫn tới một giá trị quý. Vì `int` còn vô số giá trị khác ngoài 1–12, nhánh `default` xử lý đầu vào không hợp lệ. `throw` ở nhánh này kết thúc bằng ngoại lệ thay vì trả về số quý.
- `return switch (...) { ... };` là một **biểu thức có giá trị**, nên có dấu chấm phẩy sau dấu `}` cuối cùng. Mỗi nhánh cần tạo ra giá trị phù hợp với kiểu kết quả của phương thức.

## 3. Nhiều hằng dùng được với những giá trị nào?

Ví dụ trên dùng hằng số `int` và hằng `enum`. Với `String`, có thể nhóm nhiều chuỗi cố định:

```java
static String handleCommand(String command) {
    return switch (command) {
        case "start", "run"  -> "Bắt đầu";
        case "stop", "quit"  -> "Kết thúc";
        default              -> "Lệnh không xác định";
    };
}
```

Đây là **đoạn phương thức** để thêm vào một lớp Java, không phải chương trình độc lập. `handleCommand("run")` trả về `"Bắt đầu"`; `handleCommand("RUN")` trả về `"Lệnh không xác định"` vì việc so khớp chuỗi phân biệt chữ hoa/chữ thường.

Các phần tử trong danh sách phải là **hằng hợp lệ tại thời điểm biên dịch** đối với kiểu selector. Có thể dùng literal hoặc biến hằng `static final` được khởi tạo bằng biểu thức hằng:

```java
static final int CODE_OK = 200;
static final int CODE_CREATED = 201;

static String statusName(int status) {
    return switch (status) {
        case CODE_OK, CODE_CREATED -> "Thành công";
        default -> "Trạng thái khác";
    };
}
```

`CODE_OK` và `CODE_CREATED` được xác định ngay khi biên dịch. Một biến thông thường được gán giá trị lúc chạy không thể thay cho một hằng trong danh sách `case`. Với `enum`, dùng tên hằng trực tiếp theo ngữ cảnh `switch`, như `case SATURDAY, SUNDAY`.

## 4. Cách thực thi và sự khác nhau với cú pháp cũ

Hai cách sau cho cùng kết quả khi `code` là `1` hoặc `2`:

```java
// Gom các hằng vào một nhãn
case 1, 2 -> "Cơ bản";

// Cách viết tương đương khi nằm ở hai nhánh riêng
case 1 -> "Cơ bản";
case 2 -> "Cơ bản";
```

Đây là **hai phương án thay thế**, không được đặt cả hai vào cùng một `switch` vì sẽ lặp hằng `1` và `2`. Việc gom hằng giúp tránh lặp nội dung nhánh và giảm khả năng sửa một nhánh mà quên nhánh còn lại.

Có thể dùng danh sách hằng với nhãn kiểu dấu hai chấm trong `switch` biểu thức:

```java
static String category(int code) {
    return switch (code) {
        case 1, 2:
            yield "Nhóm A";
        case 3, 4:
            yield "Nhóm B";
        default:
            yield "Khác";
    };
}
```

Đây là một phương thức hoàn chỉnh khi đặt trong lớp Java. Với cú pháp `case ...:`, `yield` chuyển **giá trị** ra khỏi `switch` biểu thức. Cú pháp dấu hai chấm có quy tắc điều khiển luồng phức tạp hơn; nếu các trường hợp chỉ có cùng một kết quả, dạng `case A, B -> value` dễ đọc hơn và tránh fall-through.

Với nhánh cần thực hiện vài bước trước khi cho ra giá trị, dùng khối lệnh và `yield`, vẫn có thể nhóm nhiều hằng:

```java
static String levelText(int level) {
    return switch (level) {
        case 1, 2 -> {
            String prefix = "Mức ";
            yield prefix + "cơ bản";
        }
        case 3, 4 -> "Mức trung cấp";
        default -> "Mức khác";
    };
}
```

Nhánh `case 1, 2` trả về `"Mức cơ bản"` nhờ `yield`. `yield` được dùng để cho kết quả của **khối trong `switch` biểu thức**; đừng dùng `break` để thay thế `yield`.

## 5. Các quy tắc và lỗi dễ gặp

| Tình huống | Điều đúng cần nhớ |
| --- | --- |
| `case 1, 2, 3 -> ...` | Một nhãn khớp một trong ba giá trị, không phải khoảng 1 đến 3. |
| `case "a", "b" -> ...` | So khớp chính xác từng chuỗi, có phân biệt hoa/thường. |
| `case 1, 1 -> ...` | Không hợp lệ: lặp giá trị hằng trong cùng `switch`. |
| Một hằng xuất hiện ở hai nhánh khác nhau | Không hợp lệ: nhãn trùng giá trị, dù viết thành hai nhánh. |
| `case 1 || 2 -> ...` | Sai: `||` là toán tử logic cho boolean, không phải cách liệt kê nhãn `case`. |
| `case 1, threshold -> ...` khi `threshold` là biến runtime | Sai: nhãn giá trị cần hằng hợp lệ lúc biên dịch. |
| `switch` biểu thức trên `int` chỉ có vài nhánh `case` | Cần bao phủ các giá trị còn lại, thường bằng `default`. |
| Cú pháp `->` | Không fall-through; không cần `break` giữa các nhánh. |

Các ví dụ dưới đây **cố ý sai** để minh họa lỗi biên dịch; không chép chúng vào một chương trình cần chạy:

```java
// Sai: giá trị 2 xuất hiện hai lần
return switch (number) {
    case 1, 2 -> "A";
    case 2, 3 -> "B";
    default -> "C";
};

// Sai: biến thường không phải hằng compile-time
int threshold = calculateThreshold();
return switch (number) {
    case 1, threshold -> "Nhóm A";
    default -> "Khác";
};
```

Với đoạn thứ hai, giả định `calculateThreshold()` là một phương thức tính lúc chạy. Lỗi nằm ở việc `threshold` không phải hằng tại thời điểm biên dịch, chứ không phải ở dấu phẩy.

Đối với `switch` trên giá trị tham chiếu (như `String` hoặc `enum`), việc nhóm nhiều hằng **không tự động xử lý `null`**. Khi cần chạy tương thích với Java 14/17, có thể kiểm tra hoặc chuẩn hóa đầu vào trước `switch`. Những mở rộng xử lý `null` ở các phiên bản Java mới là một chủ đề riêng.

## 6. Khi nào nên dùng?

Nên dùng `case A, B, C -> result` khi **nhiều giá trị rời rạc có cùng nghiệp vụ và cùng kết quả**, chẳng hạn hai ngày cuối tuần, các mã trạng thái cùng cách xử lý, hoặc các lệnh đồng nghĩa. Nếu các giá trị cần xử lý khác nhau thì nên tách thành nhánh riêng. Nếu yêu cầu là kiểm tra một **khoảng** liên tục hoặc điều kiện phức tạp, dấu phẩy không thay thế phép so sánh: hãy dùng cấu trúc điều kiện thích hợp trước khi chọn cách viết `switch`.

Ví dụ ngắn để tự kiểm tra:

```java
static String grade(int score) {
    return switch (score) {
        case 0, 1, 2 -> "Thấp";
        case 3, 4    -> "Trung bình";
        case 5       -> "Cao";
        default     -> "Ngoài thang";
    };
}
```

`grade(2)` là `"Thấp"`, `grade(4)` là `"Trung bình"`, còn `grade(6)` là `"Ngoài thang"`. Bài học cốt lõi: **dấu phẩy gộp các hằng có cùng hành vi vào đúng một nhãn `case`; mỗi giá trị chỉ được khai báo một lần, và toàn bộ `switch` biểu thức vẫn phải cho ra kết quả hoặc ném ngoại lệ trên mọi đường đi**.