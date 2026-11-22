# Nhiều hằng trong một nhãn `case` của `switch expression` — Java 17

## 1. Mục tiêu của bài học

Khi nhiều giá trị đầu vào cần tạo ra **cùng một kết quả**, viết riêng một nhánh `case` cho từng giá trị khiến mã bị lặp và khó theo dõi. Trong Java 17, một nhãn `case` có thể **liệt kê nhiều hằng, ngăn cách bằng dấu phẩy**. Tất cả hằng trong cùng nhãn đều dẫn đến **một biểu thức hoặc một khối xử lý chung**.

Ví dụ:

```java
int numberOfDays = switch (month) {
    case 4, 6, 9, 11 -> 30;
    case 2 -> 28;
    default -> 31;
};
```

Ở đây, nếu `month` là `4`, `6`, `9` hoặc `11`, biểu thức `switch` trả về `30`. Người viết chỉ mô tả quy tắc “bốn tháng này có cùng số ngày” một lần, không phải sao chép bốn nhánh giống nhau.

Ví dụ trên chỉ minh họa **cú pháp nhóm nhiều hằng**; bài toán lịch thực tế phải xử lý tháng 2 theo năm nhuận và kiểm tra tháng nằm trong khoảng `1..12`. Khi cần nghiệp vụ ngày tháng, API `java.time` như `Month` hoặc `YearMonth` thường phù hợp hơn một bảng hằng tự quản lý.

Sau bài này, người học cần:

1. Viết được `case A, B, C -> value` trong `switch expression`.
2. Giải thích vì sao các giá trị được liệt kê dùng chung một nhánh mà không có *fall-through*.
3. Phân biệt cách nhóm hằng trong `switch expression` với cách viết nhiều nhãn `case` của `switch statement`.
4. Dùng nhóm hằng với `int`, `String`, `enum` và những kiểu selector được Java 17 hỗ trợ.
5. Kết hợp nhãn nhiều hằng với biểu thức, khối `yield`, `throw`, `default`, đồng thời nhận ra lỗi trùng nhãn và hằng không hợp lệ.

**Phạm vi phiên bản:** `switch expression` là tính năng ổn định từ Java 14 (JEP 361). Cú pháp nhiều hằng trong một nhãn `case` được sử dụng trực tiếp trong Java 17, không cần bật tính năng preview.

## 2. Cú pháp cốt lõi: `case A, B, C -> ...`

Cấu trúc thường dùng:

```java
ResultType result = switch (selector) {
    case CONSTANT_1, CONSTANT_2, CONSTANT_3 -> resultExpression;
    case CONSTANT_4 -> anotherExpression;
    default -> fallbackExpression;
};
```

Các thành phần có ý nghĩa:

| Thành phần | Vai trò |
|---|---|
| `selector` | Giá trị được kiểm tra để chọn nhánh của `switch`. |
| `case CONSTANT_1, CONSTANT_2, CONSTANT_3` | Một nhãn chứa nhiều **hằng thay thế nhau**; khớp bất kỳ hằng nào thì chọn cùng nhánh. |
| Dấu phẩy `,` | Ngăn cách các hằng trong một nhãn, mang nghĩa lựa chọn **hoặc** giữa các giá trị. |
| `->` | Giới thiệu quy tắc của nhánh; không tự động chảy sang nhánh khác. |
| `resultExpression` | Giá trị mà nhánh này cung cấp cho `switch expression`. |
| `default` | Nhánh dự phòng khi không nhãn hằng nào khớp; thường cần thiết với `int` hoặc `String`. |
| `;` sau dấu `}` | Kết thúc câu lệnh gán hoặc khai báo đang sử dụng `switch expression`. |

Dấu phẩy chỉ nhóm **các hằng có cùng hành vi**. Nó không tạo một mảng, không tạo một collection và không có nghĩa điều kiện phải đồng thời thỏa tất cả giá trị.

Ví dụ:

```java
static String classify(int code) {
    return switch (code) {
        case 200, 201, 204 -> "Thành công";
        case 400, 401, 403, 404 -> "Lỗi yêu cầu";
        case 500, 502, 503 -> "Lỗi máy chủ";
        default -> "Mã khác";
    };
}
```

Phương thức trên trả về một `String` cho mọi `int` đầu vào. Với `code == 201`, Java chọn ngay nhánh `case 200, 201, 204` và lấy kết quả `"Thành công"`.

## 3. Ngữ nghĩa: nhiều giá trị, một quy tắc

Một nhóm `case` thường diễn đạt một **lớp tương đương về hành vi**. Các giá trị khác nhau ở đầu vào nhưng cùng được xử lý theo một chính sách.

Ví dụ về mức độ ưu tiên:

```java
enum Priority {
    CRITICAL, HIGH, MEDIUM, LOW, INFO
}

static int responseHours(Priority priority) {
    return switch (priority) {
        case CRITICAL, HIGH -> 2;
        case MEDIUM -> 8;
        case LOW, INFO -> 24;
    };
}
```

Các nhóm có ý nghĩa nghiệp vụ:

- `CRITICAL` và `HIGH` cùng thuộc nhóm cần phản hồi trong 2 giờ.
- `MEDIUM` có thời hạn 8 giờ.
- `LOW` và `INFO` có thời hạn 24 giờ.

Với `enum` này, mọi hằng đều được xử lý, nên `switch expression` đã **đầy đủ nhánh** (*exhaustive*) mà không cần `default`. Nếu về sau nhóm ưu tiên thay đổi, compiler có thể giúp phát hiện các trường hợp chưa được xử lý khi mã được biên dịch lại.

### 3.1. Dấu phẩy là “hoặc”, không phải điều kiện ghép

Trong:

```java
case CRITICAL, HIGH -> 2;
```

`CRITICAL` và `HIGH` là hai **giá trị thay thế**: chỉ cần selector bằng một trong hai. Không tồn tại khả năng một biến enum vừa đồng thời bằng `CRITICAL` vừa bằng `HIGH`.

Nếu muốn kết hợp thêm **điều kiện khác** như ngày làm việc, số lượng hoặc một ngưỡng thay đổi lúc chạy, hãy đặt logic đó trong nhánh hoặc trước `switch`:

```java
static int responseHours(Priority priority, boolean weekend) {
    return switch (priority) {
        case CRITICAL, HIGH -> weekend ? 4 : 2;
        case MEDIUM -> 8;
        case LOW, INFO -> 24;
    };
}
```

Các phần tử trong danh sách `case` vẫn phải là hằng đúng quy tắc, không phải các biểu thức boolean tùy ý.

### 3.2. Không có fall-through khi dùng `->`

Xét đoạn sau:

```java
String kind = switch (letter) {
    case 'a', 'e', 'i', 'o', 'u' -> "Nguyên âm thường";
    default -> "Khác";
};
```

Khi `letter == 'a'`, kết quả là `"Nguyên âm thường"`. Java **không chạy tiếp** nhánh `default`; không cần `break` ở cuối nhánh arrow.

Điểm này làm nhóm nhiều hằng trong nhãn `case` rõ ràng hơn cách dùng nhiều nhãn liên tiếp với dấu hai chấm. Nó biểu đạt trực tiếp việc một tập giá trị dùng chung hành vi.

## 4. Nhóm nhiều hằng với những kiểu selector thông dụng

Java 17 hỗ trợ `switch` truyền thống với `byte`, `short`, `char`, `int` và các wrapper tương ứng, `String`, cùng `enum`. Mỗi nhãn `case` phải phù hợp với kiểu selector và các quy tắc về hằng của Java.

### 4.1. Các giá trị số nguyên

```java
static String ticketCategory(int priorityCode) {
    return switch (priorityCode) {
        case 1, 2 -> "Ưu tiên cao";
        case 3, 4 -> "Ưu tiên thường";
        case 5 -> "Ưu tiên thấp";
        default -> throw new IllegalArgumentException(
                "Unknown priority code: " + priorityCode);
    };
}
```

Đây là ví dụ của **những giá trị rời rạc**. Danh sách `1, 2` không tự suy rộng thành một khoảng số.

Khi muốn kiểm tra **một khoảng động hoặc khoảng rộng**, `if`/`else if` có thể dễ đọc hơn việc liệt kê hàng chục hằng:

```java
static String temperatureBand(int celsius) {
    if (celsius < 10) {
        return "Lạnh";
    }
    if (celsius < 30) {
        return "Ôn hòa";
    }
    return "Nóng";
}
```

Java 17 không có cú pháp `case 1..10 ->` cho khoảng số trong `switch expression`.

### 4.2. Các chuỗi `String`

```java
static String commandGroup(String command) {
    return switch (command) {
        case "START", "RUN", "RESUME" -> "Thực thi";
        case "STOP", "QUIT", "EXIT" -> "Dừng";
        case "STATUS", "INFO" -> "Xem trạng thái";
        default -> "Lệnh không hỗ trợ";
    };
}
```

Các chuỗi cần khớp **chính xác** về nội dung và chữ hoa/chữ thường. Ví dụ `"run"` không tự động khớp `"RUN"`.

Khi bài toán muốn không phân biệt chữ hoa/thường, chuẩn hóa một lần trước khi `switch`:

```java
static String commandGroupIgnoreCase(String command) {
    String normalized = java.util.Objects.requireNonNull(command, "command")
            .strip()
            .toUpperCase(java.util.Locale.ROOT);

    return switch (normalized) {
        case "START", "RUN", "RESUME" -> "Thực thi";
        case "STOP", "QUIT", "EXIT" -> "Dừng";
        case "STATUS", "INFO" -> "Xem trạng thái";
        default -> "Lệnh không hỗ trợ";
    };
}
```

Việc chuẩn hóa nên phù hợp với hợp đồng của hệ thống. `Locale.ROOT` phù hợp cho các mã lệnh kỹ thuật không phụ thuộc ngôn ngữ của người sử dụng.

**Chú ý null:** với `switch` dùng `String` trong Java 17 thông thường, selector là `null` sẽ ném `NullPointerException`; nhánh `default` không tự coi `null` là một lệnh chưa biết. Có thể chủ động yêu cầu không null, như `Objects.requireNonNull`, hoặc xử lý null trước khi `switch`.

### 4.3. Các hằng `enum`

```java
enum OrderStatus {
    CREATED, CONFIRMED, PACKING, SHIPPING, DELIVERED, CANCELED
}

static String statusGroup(OrderStatus status) {
    return switch (status) {
        case CREATED, CONFIRMED -> "Chờ xử lý";
        case PACKING, SHIPPING -> "Đang thực hiện";
        case DELIVERED -> "Hoàn tất";
        case CANCELED -> "Đã hủy";
    };
}
```

Trong `switch` với selector kiểu `OrderStatus`, các hằng trong `case` được viết bằng **tên đơn** như `CREATED`, `CONFIRMED`. Trong Java 17, không viết `case OrderStatus.CREATED, OrderStatus.CONFIRMED ->` trong ngữ cảnh `enum switch` như trên.

Nếu `status` là `null`, nó không khớp một enum constant nào, và `switch` sẽ ném `NullPointerException` trong Java 17 thông thường.

### 4.4. Hằng ký tự `char`

```java
static boolean isVowel(char c) {
    return switch (c) {
        case 'a', 'e', 'i', 'o', 'u',
             'A', 'E', 'I', 'O', 'U' -> true;
        default -> false;
    };
}
```

Có thể xuống dòng giữa các hằng để dễ đọc. Dấu phẩy cuối dòng vẫn biểu thị chúng thuộc **cùng một nhãn `case`** và dẫn đến kết quả `true`.

Ví dụ chỉ nhận diện năm nguyên âm cơ bản trong bảng chữ cái Latin; không phải thuật toán phân loại mọi ký tự nguyên âm Unicode.

## 5. Các hằng trong `case` phải hợp lệ tại compile time

Nhiều hằng không có nghĩa có thể viết mọi biến hoặc biểu thức chạy lúc runtime vào danh sách `case`. Với `int`, `char` và `String`, nhãn `case` thông thường phải là **constant expression** tương thích. Với selector kiểu `enum`, nhãn phải là hằng enum tương ứng.

Ví dụ:

```java
public class Codes {
    static final int ACCEPTED = 202;
    static final int NO_CONTENT = 204;

    static String describe(int code) {
        return switch (code) {
            case ACCEPTED, NO_CONTENT -> "Hợp lệ";
            default -> "Khác";
        };
    }
}
```

`ACCEPTED` và `NO_CONTENT` là các **constant variables** có giá trị nguyên được xác định ở compile time, nên có thể dùng làm case constants.

Ngược lại:

```java
static int calculateCode() {
    return 202;
}

static String invalid(int code) {
    int runtimeCode = calculateCode();
    return switch (code) {
        // case runtimeCode, 204 -> "Hợp lệ"; // Lỗi: runtimeCode không phải constant expression.
        case 204 -> "Hợp lệ";
        default -> "Khác";
    };
}
```

Dù khi chạy `runtimeCode` có giá trị `202`, quy tắc nhãn `case` yêu cầu **hằng tại thời điểm biên dịch**, không phải một biến có giá trị tình cờ không đổi trong một lần thực thi.

Với chuỗi, biểu thức hằng dạng nối literal có thể hợp lệ:

```java
static final String CMD_PREFIX = "RE";
static final String RESTART = CMD_PREFIX + "START";

static String action(String cmd) {
    return switch (cmd) {
        case RESTART, "RUN" -> "Khởi động";
        default -> "Khác";
    };
}
```

`RESTART` là một hằng `String` được tính tại compile time. Không thể thay nó bằng một chuỗi lấy từ file cấu hình hoặc một lời gọi hàm thông thường để tạo ra các nhãn thay đổi theo runtime.

## 6. Tránh các nhãn hằng bị trùng

Trong cùng một khối `switch`, **một giá trị hằng không được xuất hiện ở nhiều nhãn**, kể cả nằm trong các nhóm khác nhau.

Ví dụ **không hợp lệ**:

```java
static String bad(int code) {
    return switch (code) {
        case 1, 2 -> "Nhóm A";
        // case 2, 3 -> "Nhóm B"; // Lỗi trùng giá trị 2.
        case 3 -> "Nhóm B";
        default -> "Khác";
    };
}
```

Đặt cùng giá trị ở hai nhánh không có nghĩa Java sẽ dùng nhánh xuất hiện trước. Đây là lỗi thiết kế có thể bị trình biên dịch phát hiện.

Ngay trong một nhãn cũng không nên lặp hằng:

```java
// case 1, 1 -> "Lặp"; // Lỗi: nhãn bị trùng.
```

Hai hằng khác tên nhưng **cùng giá trị compile-time** cũng gây trùng:

```java
static final int OK = 200;
static final int SUCCESS = 200;

static String badStatus(int code) {
    return switch (code) {
        // case OK, SUCCESS -> "Thành công"; // Lỗi: cùng giá trị 200.
        case OK -> "Thành công";
        default -> "Khác";
    };
}
```

Vì vậy, trước khi gom hằng, hãy xác định rõ **mỗi giá trị đầu vào thuộc đúng một nhóm xử lý**.

## 7. Kết quả của một nhóm case: biểu thức, `yield` và `throw`

Một nhãn nhiều hằng không bị giới hạn chỉ trả về literal. Phần bên phải `->` trong `switch expression` có thể là **biểu thức**, **block** hoặc **`throw`** theo cú pháp Java.

### 7.1. Nhánh trả về biểu thức

```java
static int retryCount(int status) {
    return switch (status) {
        case 429, 502, 503, 504 -> 3;
        case 400, 401, 403 -> 0;
        default -> 1;
    };
}
```

Cách này thích hợp khi nhiều hằng dẫn đến **một giá trị kết quả đơn giản**. Chính sách retry thực tế còn phụ thuộc vào tính an toàn của request, timeout và khả năng retry của hệ thống; ví dụ trên chỉ minh họa cú pháp nhóm nhánh.

### 7.2. Nhánh cần nhiều câu lệnh: dùng block với `yield`

Khi phải tính toán trước khi tạo giá trị:

```java
static String deliveryMessage(String option, int distanceKm) {
    if (distanceKm < 0) {
        throw new IllegalArgumentException("distanceKm must be non-negative");
    }

    return switch (option) {
        case "EXPRESS", "PRIORITY" -> {
            int estimatedDays = distanceKm <= 30 ? 1 : 2;
            yield "Giao nhanh: " + estimatedDays + " ngày";
        }
        case "STANDARD", "ECONOMY" -> {
            int estimatedDays = distanceKm <= 30 ? 3 : 5;
            yield "Giao thường: " + estimatedDays + " ngày";
        }
        default -> throw new IllegalArgumentException("Unknown option: " + option);
    };
}
```

Với nhánh dạng block, `yield` cung cấp giá trị cho **`switch expression` đang bao quanh**. `yield` không phải là `break` và cũng không phải `return` của phương thức.

So sánh:

- `return` kết thúc phương thức đang thực thi.
- `yield` kết thúc nhánh của `switch expression` và cung cấp kết quả cho chính biểu thức đó.
- `break` chủ yếu dùng để thoát `switch statement` kiểu colon, không dùng để trả giá trị cho `switch expression`.

Các nhánh có thể sử dụng những cách tạo kết quả khác nhau miễn là toàn bộ biểu thức có kiểu kết quả phù hợp. Không cần thêm `yield` khi phần bên phải `->` đã là một biểu thức đơn như `-> 3`.

### 7.3. Nhánh ném ngoại lệ

Nếu một nhóm giá trị đầu vào là bất hợp lệ trong nghiệp vụ, có thể ném ngoại lệ:

```java
static String route(int kind) {
    return switch (kind) {
        case 1, 2 -> "Đường ưu tiên";
        case 3 -> "Đường thường";
        case -1, 0 -> throw new IllegalArgumentException(
                "kind must be positive");
        default -> "Đường dự phòng";
    };
}
```

Một nhánh `throw` không tạo ra giá trị thông thường vì luồng thực thi kết thúc bất thường. Nó vẫn là một nhánh hợp lệ của `switch expression`.

## 8. `switch expression` và `switch statement`: nhóm case khác gì?

Java 17 hỗ trợ cả `switch expression` và `switch statement`.

- **Expression** tạo **một giá trị** để gán, truyền làm tham số hoặc `return`.
- **Statement** thực hiện hành động theo nhánh; không tự tạo giá trị cho biểu thức bao ngoài.

Trong cả hai cách viết, các quy tắc arrow có thể nhóm nhiều hằng với dấu phẩy.

### 8.1. Switch expression: trả về giá trị

```java
static String dayType(java.time.DayOfWeek day) {
    return switch (day) {
        case SATURDAY, SUNDAY -> "Cuối tuần";
        case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY -> "Ngày làm việc";
    };
}
```

Nhánh `case SATURDAY, SUNDAY` tạo ra cùng một chuỗi cho cả hai ngày. Vì sử dụng `return switch (...)`, đây là một **switch expression**.

### 8.2. Switch statement: thực hiện hành động

```java
static void printDayType(java.time.DayOfWeek day) {
    switch (day) {
        case SATURDAY, SUNDAY -> System.out.println("Cuối tuần");
        case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY ->
                System.out.println("Ngày làm việc");
    }
}
```

Đây là **switch statement**. Mặc dù dùng `->`, nó không nhất thiết trả giá trị, vì toàn bộ `switch` được sử dụng như một câu lệnh.

Không nên suy ra rằng “có `->` thì chắc chắn là switch expression”. Hình thức sử dụng và yêu cầu kết quả quyết định `switch` là statement hay expression.

### 8.3. Cú pháp colon của switch truyền thống

Trong switch statement, cách viết cũ dùng nhiều nhãn liên tiếp và `break` để chia sẻ xử lý:

```java
static String olderStyle(int code) {
    String label;
    switch (code) {
        case 1:
        case 2:
            label = "Nhóm A";
            break;
        case 3:
        case 4:
            label = "Nhóm B";
            break;
        default:
            label = "Khác";
    }
    return label;
}
```

Ở cách này, nhiều nhãn `case 1:` và `case 2:` dùng chung phần xử lý vì các nhãn được đặt trước cùng một khối statement. Nếu quên `break` trong những vị trí cần thiết, mã có thể **fall-through** vào nhánh tiếp theo.

Cách dùng switch expression với arrow tương ứng:

```java
static String expressionStyle(int code) {
    return switch (code) {
        case 1, 2 -> "Nhóm A";
        case 3, 4 -> "Nhóm B";
        default -> "Khác";
    };
}
```

Phiên bản arrow bộc lộ trực tiếp quan hệ **cùng giá trị đầu ra → cùng một nhánh** và không có fall-through. Khi viết mới một phép ánh xạ giá trị sang giá trị, thường nên chọn phong cách này.

Java 17 cũng cho phép dùng dấu `:` cùng `yield` bên trong switch expression, nhưng đó là một cách viết khác. Trong một `switch` không được tùy ý trộn hai kiểu nhãn colon (`:`) và arrow (`->`).

## 9. Tính đầy đủ của `switch expression`

Một `switch expression` phải xử lý mọi trường hợp có thể xảy ra theo các quy tắc bao phủ (*exhaustiveness*) của Java.

### 9.1. Với `int` và `String`

Không thể liệt kê hữu hạn toàn bộ giá trị `int` hoặc mọi chuỗi, nên thường cần `default`:

```java
static String classify(int code) {
    return switch (code) {
        case 1, 2 -> "Nhóm A";
        case 3, 4 -> "Nhóm B";
        default -> "Chưa phân loại";
    };
}
```

`default` chỉ chạy khi không hằng nào khớp. Đừng dùng `default` để che giấu lỗi dữ liệu nếu mã nghiệp vụ yêu cầu từ chối đầu vào không hợp lệ; trong trường hợp đó có thể viết `default -> throw new IllegalArgumentException(...)`.

### 9.2. Với `enum`

Nếu đã liệt kê đầy đủ các hằng enum thì có thể bỏ `default`:

```java
enum Stage { NEW, QUEUED, RUNNING, FINISHED, FAILED }

static String stageGroup(Stage stage) {
    return switch (stage) {
        case NEW, QUEUED -> "Chờ";
        case RUNNING -> "Đang chạy";
        case FINISHED, FAILED -> "Đã kết thúc";
    };
}
```

Nếu thêm một enum constant mới và biên dịch lại đoạn mã sử dụng enum, compiler có thể yêu cầu cập nhật `switch expression` cho đầy đủ. Đây là lợi ích của việc **liệt kê tường minh các nhóm** thay vì luôn thêm `default` khi miền giá trị đã đóng.

Mỗi hằng enum phải xuất hiện **không quá một lần**. Một nhóm có thể chứa một hoặc nhiều hằng nhưng không được chứa một hằng đã dùng trong nhóm khác.

### 9.3. `default` không đồng nghĩa với xử lý `null`

Với `String`, wrapper hoặc `enum` là selector, `switch` Java 17 thông thường không tự đưa `null` vào `default`.

```java
static String classifyNullable(String value) {
    if (value == null) {
        return "Không có dữ liệu";
    }
    return switch (value) {
        case "A", "B" -> "Nhóm đầu";
        default -> "Nhóm khác";
    };
}
```

Mã này xử lý `null` **trước** khi gọi `switch`. Cú pháp `case null` thuộc hướng mở rộng pattern matching for switch ở các phiên bản sau, và **không phải cú pháp switch expression ổn định mặc định của Java 17**. Không dựa vào nó trong bài tập đặt target Java 17.

## 10. Ví dụ tích hợp hoàn chỉnh chạy bằng Java 17

Ứng dụng nhỏ sau gom các loại đơn hàng thành nhóm xử lý, đồng thời ánh xạ mã vận chuyển sang mức phí. Các nhóm dùng cả `enum` lẫn `String`, thể hiện tình huống thực tế mà nhiều hằng cùng dẫn đến một kết quả.

Tạo tệp `Main.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class Main {
    enum OrderStatus {
        CREATED, CONFIRMED, PACKING, SHIPPING, DELIVERED, CANCELED
    }

    static String statusGroup(OrderStatus status) {
        return switch (Objects.requireNonNull(status, "status")) {
            case CREATED, CONFIRMED -> "Chờ xử lý";
            case PACKING, SHIPPING -> "Đang thực hiện";
            case DELIVERED -> "Hoàn thành";
            case CANCELED -> "Đã hủy";
        };
    }

    static int shippingFeeCents(String service) {
        String normalized = Objects.requireNonNull(service, "service")
                .strip()
                .toUpperCase(Locale.ROOT);

        return switch (normalized) {
            case "EXPRESS", "PRIORITY" -> 1500;
            case "STANDARD" -> 500;
            case "ECONOMY", "FREE" -> 0;
            default -> throw new IllegalArgumentException(
                    "Unknown service: " + service);
        };
    }

    static String message(int count) {
        return switch (count) {
            case 0 -> "Chưa có đơn";
            case 1, 2, 3 -> "Ít đơn";
            default -> {
                if (count < 0) {
                    throw new IllegalArgumentException("count must be non-negative");
                }
                yield "Có " + count + " đơn";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(statusGroup(OrderStatus.CREATED));
        System.out.println(statusGroup(OrderStatus.SHIPPING));
        System.out.println(shippingFeeCents(" priority "));
        System.out.println(shippingFeeCents("FREE"));
        System.out.println(message(2));
        System.out.println(message(5));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Kết quả:

```text
Chờ xử lý
Đang thực hiện
1500
0
Ít đơn
Có 5 đơn
```

Các điểm cần đọc được trong mã:

1. `case CREATED, CONFIRMED ->` chọn một kết quả cho hai enum constants.
2. `case "EXPRESS", "PRIORITY" ->` nhóm hai mã dịch vụ chuỗi; việc chuẩn hóa đầu vào diễn ra trước `switch`.
3. `case "ECONOMY", "FREE" -> 0` tránh viết hai nhánh trả cùng một giá trị.
4. `case 1, 2, 3 ->` nhóm nhiều hằng `int` thành một nhánh.
5. Nhánh `default` trong `message` là block sử dụng `yield` để tạo kết quả, đồng thời có thể ném ngoại lệ với `count < 0`.
6. Mọi `switch` trong ví dụ đều trả một giá trị cho trường hợp hợp lệ; không cần `break` ở nhánh arrow.

Đây là ví dụ về cú pháp và cấu trúc mã; trong hệ thống thật, bảng phí và nhóm trạng thái nên xuất phát từ quy tắc nghiệp vụ được xác nhận, có kiểm thử và quản lý thay đổi phù hợp.

## 11. Các lỗi thường gặp

### 11.1. Quên dấu phẩy giữa các hằng

Sai:

```java
// case 1 2 3 -> "Một nhóm"; // Thiếu dấu phẩy.
```

Đúng:

```java
case 1, 2, 3 -> "Một nhóm";
```

Đoạn đúng là **một nhãn** có ba hằng.

### 11.2. Dùng toán tử `||` trong nhãn

Sai:

```java
// case 1 || 2 -> "Một nhóm"; // Không phải cách viết danh sách case constants.
```

Đúng:

```java
case 1, 2 -> "Một nhóm";
```

Trong một `case`, các hằng được liệt kê bằng dấu phẩy, không nối bằng toán tử boolean.

### 11.3. Dùng biến runtime thay cho hằng

Sai:

```java
int target = readCode();
// case target, 2 -> ... // target không phải constant expression.
```

Với ngữ cảnh các mã được định nghĩa trước, dùng literal hoặc constant variable hợp lệ. Nếu danh sách giá trị được nạp **động** từ cấu hình, có thể dùng `Set.contains`, `Map.get` hoặc điều kiện thường thay vì cố biến dữ liệu runtime thành `case` hằng.

### 11.4. Trùng giá trị ở nhiều nhóm

Sai:

```java
// case 1, 2 -> "A";
// case 2, 3 -> "B"; // 2 bị trùng.
```

Hãy thiết kế những nhóm rời nhau, xác định đúng chính sách cho mỗi giá trị rồi phân bổ mỗi hằng vào một nhãn duy nhất.

### 11.5. Dùng `break` thay cho `yield` trong block của switch expression

Sai về ý định:

```java
// return switch (code) {
//     case 1, 2 -> {
//         int value = code * 10;
//         break; // Không cung cấp kết quả cho switch expression.
//     }
//     default -> 0;
// };
```

Đúng:

```java
return switch (code) {
    case 1, 2 -> {
        int value = code * 10;
        yield value;
    }
    default -> 0;
};
```

### 11.6. Quên nhánh bao phủ cho switch expression

Nếu selector là `int` và chỉ có `case 1, 2`, biểu thức chưa xử lý các giá trị còn lại. Thêm nhánh `default` hợp lệ hoặc thiết kế lại miền giá trị để compiler xác nhận đủ nhánh.

### 11.7. Nhầm nhóm nhiều hằng với pattern matching cho switch

`case 1, 2 ->` chỉ nhóm **các hằng cụ thể**. Nó không phải kiểm tra kiểu, không có guard và không làm phép tách dữ liệu từ record. Pattern matching for `switch` chưa là tính năng ổn định mặc định của Java 17; các ví dụ về `case String s`, `case Point(int x, int y)` trong tài liệu Java mới hơn không thuộc cú pháp chuẩn của bài này.

## 12. Bài tập thực hành

### Bài 1 — Gom tháng theo quý

Viết phương thức `quarter(int month)` trả `"Q1"`, `"Q2"`, `"Q3"`, `"Q4"` với tháng từ 1 đến 12. Nếu tháng không hợp lệ, ném `IllegalArgumentException`.

Một lời giải:

```java
static String quarter(int month) {
    return switch (month) {
        case 1, 2, 3 -> "Q1";
        case 4, 5, 6 -> "Q2";
        case 7, 8, 9 -> "Q3";
        case 10, 11, 12 -> "Q4";
        default -> throw new IllegalArgumentException(
                "Invalid month: " + month);
    };
}
```

Trong mỗi nhãn, ba tháng có cùng kết quả; không có nhãn trùng và mọi `int` khác đều bị từ chối.

### Bài 2 — Nhóm tình trạng yêu cầu

Giả sử có enum:

```java
enum JobState { WAITING, RETRYING, RUNNING, SUCCESS, FAILED, CANCELED }
```

Hãy viết `group(JobState state)` sao cho `WAITING` và `RETRYING` trả `"Chờ"`; `RUNNING` trả `"Đang chạy"`; `SUCCESS`, `FAILED`, `CANCELED` trả `"Đã kết thúc"`.

Lời giải:

```java
static String group(JobState state) {
    return switch (state) {
        case WAITING, RETRYING -> "Chờ";
        case RUNNING -> "Đang chạy";
        case SUCCESS, FAILED, CANCELED -> "Đã kết thúc";
    };
}
```

Không cần `default` vì đã bao phủ đủ sáu enum constants. Nếu ứng dụng không cho phép `null`, hãy làm rõ hợp đồng tham số hoặc thêm kiểm tra không null trước switch.

### Bài 3 — Dự đoán kết quả

```java
static int points(String grade) {
    return switch (grade) {
        case "A+", "A" -> 4;
        case "B+", "B" -> 3;
        case "C+", "C" -> 2;
        default -> 0;
    };
}
```

Hãy dự đoán `points("A")`, `points("B+")`, `points("c")`, `points("D")`.

Đáp án tương ứng: `4`, `3`, `0`, `0`. `"c"` không khớp `"C"` vì so sánh `String` ở `switch` phân biệt chữ hoa và chữ thường.

### Bài 4 — Sửa lỗi dùng `break`

Xét phiên bản muốn trả về chuỗi sau khi xử lý hai mã:

```java
// return switch (code) {
//     case 10, 11 -> {
//         String label = "Accepted";
//         break;
//     }
//     default -> "Other";
// };
```

Sửa bằng cách thay `break` với `yield label;` trong block. Giải thích: đây là switch **expression** và phải cung cấp giá trị cho biểu thức.

### Bài 5 — Xử lý đầu vào động

Giả sử `Set<Integer> blockedCodes` được nạp từ cấu hình vào lúc chạy. Có thể viết `case blockedCodes -> ...` hay liệt kê các phần tử của set làm case constants?

Không: các giá trị runtime không thỏa quy tắc constant case labels. Một hướng phù hợp:

```java
static String decide(int code, java.util.Set<Integer> blockedCodes) {
    if (blockedCodes.contains(code)) {
        return "Blocked";
    }
    return switch (code) {
        case 200, 201 -> "Accepted";
        case 404 -> "Not found";
        default -> "Other";
    };
}
```

Ví dụ cho thấy sử dụng `switch` với **hằng cố định** và dùng collection khi tập điều kiện **thay đổi theo runtime**.

## 13. Tiêu chí hoàn thành

Người học đã nắm vững “nhiều hằng trong một nhãn `case`” khi tự thực hiện được các yêu cầu:

1. Viết `case A, B, C -> expression` và diễn giải đúng rằng **một trong ba hằng** khớp sẽ đi cùng một nhánh.
2. Đổi một đoạn `switch statement` lặp nhiều nhãn colon sang `switch expression` có nhóm hằng và kết quả tương đương.
3. Dùng nhóm hằng với selector kiểu `int`, `String` và `enum`; nêu được yêu cầu hằng compile-time và sự khác nhau giữa enum constant với string literal.
4. Giải thích vì sao nhánh `->` không fall-through và không cần `break`.
5. Viết đúng một nhánh block có nhiều câu lệnh và `yield`, hoặc nhánh `throw` khi đầu vào không hợp lệ.
6. Phát hiện nhãn bị trùng, biến runtime làm case label và thiếu nhánh `default` ở biểu thức dùng kiểu giá trị mở.
7. Xử lý chủ động `null` với `String`/`enum` theo ngữ nghĩa Java 17.
8. Biên dịch chương trình bằng `javac --release 17` mà không dùng cú pháp preview hoặc cú pháp chỉ có trong Java mới hơn.

## 14. Tài liệu chính thức

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): lý do thiết kế, quy tắc arrow, nhóm case constants và `yield`.
- [Java Language Specification SE 17 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): ngữ pháp và hành vi của switch statement.
- [Java Language Specification SE 17 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): cách một switch expression chọn nhánh và tạo kết quả.
- [Java SE 17 API — `java.time.Month`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html): ví dụ enum chuẩn có thể sử dụng với switch, hữu ích khi làm việc với tháng trong lịch.

**Ghi nhớ:** `case A, B, C -> result` là **một nhãn với nhiều lựa chọn đầu vào** và **một quy tắc xử lý chung**. Đây là cách diễn đạt ngắn, rõ ràng và ổn định trên Java 17 cho các giá trị rời rạc có cùng kết quả.
