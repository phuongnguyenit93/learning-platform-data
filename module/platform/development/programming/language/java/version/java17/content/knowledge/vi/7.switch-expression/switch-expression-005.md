# Nhánh ném ngoại lệ trong `switch expression` — Java 17

`switch expression` được dùng khi một giá trị đầu vào quyết định **giá trị kết quả** của một biểu thức. Tuy nhiên, không phải trường hợp nào cũng hợp lệ để tạo ra kết quả. Trong Java 17, một nhánh của `switch expression` có thể **ném ngoại lệ bằng `throw`** thay vì trả một giá trị.

Ví dụ:

```java
static String label(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 201 -> "Created";
        default -> throw new IllegalArgumentException(
                "Unsupported code: " + code
        );
    };
}
```

Khi `code` là `200` hoặc `201`, biểu thức `switch` tạo ra chuỗi tương ứng. Với giá trị khác, nhánh `default` ném `IllegalArgumentException`; không có chuỗi kết quả nào được tạo.

Đây là cú pháp chính thức trong **Java 17**, không cần `--enable-preview`. Bài học giải thích cách viết nhánh `throw`, quan hệ giữa `throw` và `yield`, các quy tắc biên dịch và cách chọn ngoại lệ phù hợp.

## 1. Phân biệt `switch expression` với `switch statement`

Một `switch statement` thực hiện các câu lệnh theo nhánh; một `switch expression` **được sử dụng như một biểu thức có giá trị**.

### `switch statement`

```java
String result;
switch (code) {
    case 200:
        result = "OK";
        break;
    case 201:
        result = "Created";
        break;
    default:
        throw new IllegalArgumentException("Unsupported code: " + code);
}
```

Trong dạng statement truyền thống, các nhánh thường gán vào một biến bên ngoài. `break` được dùng để ngăn luồng rơi xuống nhánh tiếp theo khi dùng cú pháp nhãn dấu hai chấm `case ...:`.

### `switch expression`

```java
String result = switch (code) {
    case 200 -> "OK";
    case 201 -> "Created";
    default -> throw new IllegalArgumentException(
            "Unsupported code: " + code
    );
};
```

Ở dạng expression:

- Toàn bộ `switch (...) { ... }` là **một biểu thức**.
- Nhánh `case 200 -> "OK"` tạo ra giá trị `"OK"`.
- Nhánh `default -> throw ...` **kết thúc bằng ngoại lệ**.
- Không cần `break` sau mỗi nhánh dùng mũi tên `->`.
- Dấu `;` cuối `};` kết thúc câu lệnh gán chứa `switch expression`.

`throw` được phép ở cả switch statement lẫn switch expression. Điểm cần nắm là với **switch expression**, một nhánh ném ngoại lệ được chấp nhận mặc dù nó **không trả về giá trị**.

## 2. Ba dạng thân nhánh sau `->`

Trong Java 17, với dạng nhãn mũi tên (*switch rule*), phần bên phải `->` có thể là:

| Dạng thân nhánh | Cú pháp | Ý nghĩa |
|---|---|---|
| **Biểu thức** | `case A -> expression;` | Đánh giá và cung cấp giá trị cho `switch expression` |
| **Khối lệnh** | `case B -> { ... }` | Thực hiện nhiều câu lệnh, thường kết thúc bằng `yield` hoặc `throw` |
| **Câu lệnh `throw`** | `case C -> throw new ExceptionType(...);` | Ném ngoại lệ, không cung cấp giá trị |

Ví dụ kết hợp cả ba dạng:

```java
static String message(int status) {
    return switch (status) {
        case 0 -> "READY";

        case 1 -> {
            String text = "RUNNING";
            yield text.toLowerCase();
        }

        default -> throw new IllegalArgumentException(
                "Unknown status: " + status
        );
    };
}
```

Nhánh `case 0` cung cấp giá trị trực tiếp. Nhánh `case 1` thực hiện nhiều câu lệnh rồi `yield` một giá trị. Nhánh `default` ném ngoại lệ.

**`throw` là một câu lệnh, không phải biểu thức thông thường của Java 17.** Nó được Java cho phép đặt ngay sau `->` theo quy tắc ngữ pháp riêng của switch rule. Vì vậy cú pháp `case X -> throw new ...;` là hợp lệ, nhưng không suy ra rằng `throw` có thể tùy ý thay cho một biểu thức ở mọi vị trí trong Java.

## 3. Điều gì xảy ra khi nhánh `throw` được chọn?

Xét:

```java
static int level(String role) {
    return switch (role) {
        case "USER" -> 1;
        case "EDITOR" -> 2;
        case "ADMIN" -> 3;
        default -> throw new IllegalArgumentException(
                "Unknown role: " + role
        );
    };
}
```

Khi gọi `level("EDITOR")`:

1. Java đánh giá biểu thức selector `role`.
2. Giá trị khớp nhãn `case "EDITOR"`.
3. Nhánh trả số `2`.
4. Toàn bộ `switch expression` có giá trị `2`, nên phương thức trả về `2`.

Khi gọi `level("GUEST")`:

1. Java đánh giá selector `role`.
2. Không nhãn `"USER"`, `"EDITOR"` hay `"ADMIN"` nào khớp.
3. Nhánh `default` chạy và tạo đối tượng `IllegalArgumentException`.
4. `throw` ném đối tượng ngoại lệ đó.
5. Việc đánh giá `switch expression` **kết thúc bất thường** (*abrupt completion*); không có `int` kết quả để đưa vào `return`.

Sơ đồ:

```text
                      switch (role)
                           |
              +------------+------------+
              |                         |
         Nhãn hợp lệ               Không khớp nhãn
              |                         |
       Nhận giá trị int            default -> throw
              |                         |
        return giá trị             Ném ngoại lệ
                                        |
                               Đi tìm catch phù hợp
                                 hoặc truyền lên
```

Với nhánh `throw`, Java không cần “tạo một giá trị mặc định giả” để thỏa mãn kiểu kết quả của `switch expression`.

### Không có hiện tượng chạy sang nhánh tiếp theo

Nhánh mũi tên `->` không có *fall-through*. Khi đã chọn một nhánh, Java không tự động thực hiện nhánh ở dưới.

```java
static String select(int value) {
    return switch (value) {
        case 1 -> "ONE";
        case 2 -> throw new IllegalStateException("Rejected");
        default -> "OTHER";
    };
}
```

Nếu `value == 2`, chương trình ném ngoại lệ. Nó **không tiếp tục** đến `default` để trả về `"OTHER"`.

## 4. Cú pháp cơ bản: ném trực tiếp từ một `case`

Có thể đặt `throw` trực tiếp sau `->`:

```java
static String category(int code) {
    return switch (code) {
        case 1 -> "STANDARD";
        case 2 -> "PREMIUM";
        case 0 -> throw new IllegalArgumentException(
                "Code 0 is reserved"
        );
        default -> throw new IllegalArgumentException(
                "Unsupported category: " + code
        );
    };
}
```

Ở đây có **hai nhánh ném ngoại lệ**:

- `case 0` có ý nghĩa riêng: mã `0` đã được dành trước, không được sử dụng.
- `default` xử lý các mã ngoài danh sách đã định nghĩa.

Một nhánh `throw` không bắt buộc phải nằm ở `default`. Bất kỳ nhãn `case` hợp lệ nào cũng có thể ném ngoại lệ.

### Nhiều nhãn cùng ném một ngoại lệ

Java 17 cho phép gộp các nhãn `case` bằng dấu phẩy:

```java
static int retryDelaySeconds(int status) {
    return switch (status) {
        case 200 -> 0;
        case 429, 503 -> 30;
        case 400, 401, 403 -> throw new IllegalArgumentException(
                "Non-retryable status: " + status
        );
        default -> throw new IllegalStateException(
                "Status not covered: " + status
        );
    };
}
```

`case 400, 401, 403` là **một switch rule**. Khi một trong ba giá trị khớp, toàn bộ rule chạy `throw`; không cần lặp lại cùng một ngoại lệ ba lần.

### Đặt thông tin hữu ích vào thông điệp lỗi

Thông điệp ngoại lệ nên cho biết **giá trị nào không hợp lệ** và **ràng buộc nào bị vi phạm**:

```java
default -> throw new IllegalArgumentException(
        "Invalid priority " + priority + "; expected 1, 2 or 3"
);
```

Tránh thông báo quá chung chung như `"Error"` nếu không đủ ngữ cảnh để truy ra nguyên nhân. Với dữ liệu nhạy cảm, không đưa bí mật hoặc thông tin không nên ghi log vào thông điệp.

## 5. Dùng `throw` bên trong khối `case ... -> { ... }`

Khi cần thực hiện kiểm tra hoặc xây dựng nội dung lỗi trước khi ném, dùng **block**:

```java
static String parseMode(String mode) {
    return switch (mode) {
        case "READ" -> "read-only";
        case "WRITE" -> "read-write";

        default -> {
            String description = "Unsupported mode: " + mode;
            throw new IllegalArgumentException(description);
        }
    };
}
```

Dấu `;` sau `throw new ...` thuộc câu lệnh ném ngoại lệ. **Không** đặt dấu `;` sau dấu `}` của block `default -> { ... }`; dấu `;` sau `};` cuối cùng thuộc câu lệnh `return` hoặc phép gán bên ngoài.

### Khi nhánh vừa có đường trả giá trị vừa có đường ném

Một block switch rule có thể dùng điều kiện để quyết định **ném hoặc `yield`**:

```java
static int calculateFee(int tier, int amount) {
    return switch (tier) {
        case 1 -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount < 0");
            }

            yield amount / 10;
        }
        case 2 -> {
            if (amount < 100) {
                throw new IllegalArgumentException(
                        "Tier 2 requires amount >= 100"
                );
            }

            yield amount / 5;
        }
        default -> throw new IllegalArgumentException(
                "Unsupported tier: " + tier
        );
    };
}
```

Với `tier == 1`:

- Nếu `amount < 0`, `throw` chạy; nhánh không cung cấp giá trị.
- Nếu `amount >= 0`, code đi tới `yield amount / 10;`; đây là giá trị kết quả của `switch expression`.

Điều kiện đặt trong block không làm `switch expression` mất tính chất biểu thức. **Mỗi đường thực thi có thể đi hết block phải kết thúc bằng một giá trị `yield` hoặc một ngoại lệ phù hợp**.

## 6. Quy tắc quan trọng: nhánh nào cũng phải có kết quả hoặc ném

`switch expression` phải có khả năng **hoàn thành bình thường với một giá trị** hoặc **hoàn thành bất thường vì một ngoại lệ**.

Không hợp lệ:

```java
// LỖI: block case 1 có thể kết thúc bình thường mà không yield.
static String broken(int code) {
    return switch (code) {
        case 1 -> {
            System.out.println("Known");
        }
        default -> "Other";
    };
}
```

Trình biên dịch không biết lấy giá trị nào cho `case 1`.

Sửa bằng `yield`:

```java
static String valid(int code) {
    return switch (code) {
        case 1 -> {
            System.out.println("Known");
            yield "ONE";
        }
        default -> "Other";
    };
}
```

Hoặc nếu nghiệp vụ không cho phép `code == 1`, sửa bằng `throw`:

```java
static String reject(int code) {
    return switch (code) {
        case 1 -> {
            System.out.println("Rejected");
            throw new IllegalStateException("Code 1 is disabled");
        }
        default -> "Other";
    };
}
```

**Trường hợp dễ nhầm: một nhánh chỉ thỉnh thoảng ném**

```java
// LỖI: khi invalid == false, block case 1 có thể đi hết.
static int broken(int code, boolean invalid) {
    return switch (code) {
        case 1 -> {
            if (invalid) {
                throw new IllegalArgumentException();
            }
        }
        default -> 10;
    };
}
```

Sửa thành:

```java
static int valid(int code, boolean invalid) {
    return switch (code) {
        case 1 -> {
            if (invalid) {
                throw new IllegalArgumentException();
            }
            yield 1;
        }
        default -> 10;
    };
}
```

`yield 1` đảm bảo đường `invalid == false` vẫn tạo kết quả. Đây là quy tắc về **khả năng hoàn tất của block**, khác với quy tắc phải có đủ nhãn `case`.

## 7. Phân biệt `yield`, `throw`, `return` và `break`

Bốn câu lệnh này có mục đích khác nhau:

| Từ khóa | Vai trò trong ngữ cảnh `switch expression` | Có cung cấp giá trị cho `switch expression`? |
|---|---|---|
| `yield value;` | Kết thúc nhánh block, đưa `value` thành kết quả của switch | **Có** |
| `throw exception;` | Kết thúc bằng ngoại lệ và chuyển điều khiển tới handler phù hợp | **Không** |
| `return value;` | Trả kết quả từ phương thức, không phải công cụ để tạo giá trị cho switch | **Không** |
| `break;` | Dùng trong các cấu trúc điều khiển được phép; không dùng để cấp kết quả switch expression | **Không** |

Ví dụ đúng với `yield` và `throw`:

```java
static String format(int number) {
    return switch (number) {
        case 0 -> {
            String result = "ZERO";
            yield result;
        }
        case -1 -> {
            throw new IllegalArgumentException("Negative sentinel");
        }
        default -> Integer.toString(number);
    };
}
```

Không viết:

```java
// LỖI: throw không phải giá trị để yield.
// case -1 -> { yield throw new IllegalArgumentException(); }

// LỖI: dùng break để gửi một giá trị từ switch expression.
// case 0 -> { break "ZERO"; }

// LỖI: return ở vị trí này không phải cách tạo kết quả switch.
// case 0 -> { return "ZERO"; }
```

Ở Java 17, `yield` tồn tại để cung cấp giá trị từ block của switch expression. `throw` là **phương án hoàn tất bằng ngoại lệ**, không phải một kiểu `yield` đặc biệt.

### Biến kiểu kết quả đến từ đâu nếu một nhánh chỉ có `throw`?

`throw` không đưa thêm một giá trị `String` hay `int` vào quá trình xác định kiểu kết quả. Các nhánh **thực sự cung cấp giá trị** và ngữ cảnh sử dụng switch expression là những yếu tố xác định kiểu.

Ví dụ:

```java
int port = switch (environment) {
    case "development" -> 8080;
    case "production" -> 80;
    default -> throw new IllegalArgumentException(
            "Unknown environment: " + environment
    );
};
```

Hai nhánh hợp lệ tạo giá trị kiểu `int`. Nhánh `default` không phải tạo một giá trị `int` giả.

## 8. `switch expression` vẫn phải bao phủ đầy đủ các giá trị

Khái niệm **exhaustiveness**: với các giá trị thuộc miền hợp lệ của selector, switch expression phải có nhãn thích hợp để xử lý chúng.

### Với selector kiểu `int` hoặc `String`

Thường cần `default`:

```java
static String weekdayName(int day) {
    return switch (day) {
        case 1 -> "Monday";
        case 2 -> "Tuesday";
        case 3 -> "Wednesday";
        case 4 -> "Thursday";
        case 5 -> "Friday";
        case 6 -> "Saturday";
        case 7 -> "Sunday";
        default -> throw new IllegalArgumentException(
                "Day must be between 1 and 7: " + day
        );
    };
}
```

Nhánh `default` **ném ngoại lệ** nhưng vẫn khiến switch bao phủ được các giá trị khác, vì nó xác định kết quả xử lý cho mọi giá trị không khớp một `case` cụ thể.

Đoạn sau không hợp lệ vì thiếu cách xử lý các giá trị khác `1`:

```java
// LỖI: switch expression không exhaustive.
static String broken(int day) {
    return switch (day) {
        case 1 -> "Monday";
    };
}
```

### Với selector là `enum`

Khi liệt kê **tất cả hằng số của enum** trong `case`, Java 17 cho phép bỏ `default`:

```java
enum DeliveryState {
    READY,
    IN_TRANSIT,
    DELIVERED,
    CANCELLED
}

static String display(DeliveryState state) {
    return switch (state) {
        case READY -> "Ready";
        case IN_TRANSIT -> "In transit";
        case DELIVERED -> "Delivered";
        case CANCELLED -> throw new IllegalStateException(
                "Cancelled orders have no delivery label"
        );
    };
}
```

Ở đây `CANCELLED` vẫn được **xử lý** bằng cách ném ngoại lệ, nên switch expression bao phủ cả bốn hằng số.

Nếu muốn ứng dụng luôn xử lý một hằng số mới sau khi enum thay đổi, cần cân nhắc chính sách cập nhật mã và biên dịch lại. Compiler có thể tạo cơ chế xử lý ngầm cho trường hợp không khớp enum khi không có `default`; **không nên coi việc ném ngoại lệ ngầm lúc runtime là cách thay thế kiểm soát phiên bản enum**.

### Không lạm dụng `default -> throw` để che thiếu chức năng

Có hai thiết kế khác nhau:

- **Dữ liệu đầu vào không hợp lệ:** `default -> throw new IllegalArgumentException(...)` là cách từ chối rõ ràng.
- **Một trạng thái enum mới đòi hỏi nghiệp vụ phải xử lý:** nếu viết `default` mọi nơi, compiler có thể không buộc bạn cập nhật từng switch sau khi thêm hằng số enum. Với một hệ phân cấp trạng thái cố định, việc liệt kê tường minh toàn bộ enum và bỏ `default` có thể giúp compiler phát hiện thiếu nhánh khi biên dịch lại.

Chọn dựa trên hợp đồng của API, không dùng `throw` chỉ để lấp một nhánh còn chưa thiết kế.

## 9. Giá trị `null`: trường hợp đặc biệt của Java 17

Với switch expression cơ bản của Java 17, nếu selector là một tham chiếu `null`, việc chọn nhánh sẽ ném `NullPointerException`; **`default` không phải nhánh bắt `null`**.

Ví dụ:

```java
static String classify(String input) {
    return switch (input) {
        case "A" -> "Alpha";
        case "B" -> "Beta";
        default -> throw new IllegalArgumentException(
                "Unknown input: " + input
        );
    };
}
```

Với `classify(null)`, người dùng không nên chờ nhận `IllegalArgumentException` từ `default`; biểu thức selector là `null` và quy tắc switch thông thường ném `NullPointerException` trước khi một nhánh bình thường được chọn.

Nếu muốn chính sách rõ ràng cho `null`, kiểm tra **trước switch**:

```java
static String classify(String input) {
    if (input == null) {
        throw new IllegalArgumentException("input must not be null");
    }

    return switch (input) {
        case "A" -> "Alpha";
        case "B" -> "Beta";
        default -> throw new IllegalArgumentException(
                "Unknown input: " + input
        );
    };
}
```

Hoặc sử dụng `Objects.requireNonNull(input, "input")` nếu quy ước API là ném `NullPointerException` khi input null.

> **Giới hạn phiên bản:** Java 17 có tính năng *pattern matching for switch* ở trạng thái **preview**, trong đó có cú pháp xử lý `null` riêng. Bài này chỉ sử dụng **switch expression ổn định của Java 17**, không sử dụng cú pháp preview để tránh yêu cầu cờ biên dịch và hành vi phụ thuộc phiên bản.

## 10. Chọn loại ngoại lệ cho nhánh `throw`

Cú pháp switch không quy định phải ném một loại exception cụ thể. Lựa chọn phụ thuộc **nghĩa của tình huống lỗi**:

| Ngoại lệ | Phù hợp khi | Ví dụ |
|---|---|---|
| `IllegalArgumentException` | Người gọi truyền giá trị đối số ngoài miền hợp lệ | `default -> throw new IllegalArgumentException("Bad code: " + code)` |
| `IllegalStateException` | Trạng thái hiện tại của hệ thống không cho phép thao tác | `case CLOSED -> throw new IllegalStateException("Already closed")` |
| `UnsupportedOperationException` | Thao tác cụ thể không được hỗ trợ theo hợp đồng API | `case ARCHIVE -> throw new UnsupportedOperationException("Archive disabled")` |
| `IOException` | Có lỗi vào/ra được mô tả phù hợp với hợp đồng API | `default -> throw new IOException("Invalid record data")` |
| Ngoại lệ nghiệp vụ riêng | Muốn biểu đạt lỗi domain có cấu trúc rõ | `case REJECTED -> throw new OrderRejectedException(...)` |

Các ngoại lệ `IllegalArgumentException`, `IllegalStateException` và `UnsupportedOperationException` là **unchecked exceptions** vì thuộc nhánh `RuntimeException`. `IOException` là **checked exception**.

Không phải lúc nào giá trị không hỗ trợ cũng là lỗi. Nếu nghiệp vụ có lựa chọn “không xác định” được xem là hợp lệ, có thể trả một giá trị biểu thị điều đó thay vì ném ngoại lệ. Nhánh `throw` phù hợp khi việc tiếp tục mà không báo lỗi sẽ vi phạm hợp đồng của phương thức.

### Ví dụ với một enum trạng thái

```java
enum AccessState {
    ACTIVE,
    LOCKED,
    DELETED
}

static String accessMessage(AccessState state) {
    return switch (state) {
        case ACTIVE -> "Access granted";
        case LOCKED -> throw new IllegalStateException(
                "The account is locked"
        );
        case DELETED -> throw new IllegalStateException(
                "The account was deleted"
        );
    };
}
```

`LOCKED` và `DELETED` là trạng thái enum **đã biết**, nhưng có thể được xem là những trạng thái không cho phép tạo thông điệp truy cập thành công. Việc chủ động ném ngoại lệ cho chúng khác với dùng `default` để bắt một giá trị không nhận diện.

## 11. Checked exception trong nhánh `throw`

Một nhánh `case ... -> throw ...` phải tuân theo các quy tắc checked exception thông thường của Java.

Ví dụ hợp lệ khi phương thức **khai báo `throws IOException`**:

```java
import java.io.IOException;

class Decoder {
    static String decode(int format) throws IOException {
        return switch (format) {
            case 1 -> "TEXT";
            case 2 -> "BINARY";
            default -> throw new IOException(
                    "Unsupported file format: " + format
            );
        };
    }
}
```

Nếu bỏ `throws IOException` và không bắt ngoại lệ này ở nơi thích hợp, mã sẽ có **lỗi biên dịch** vì `IOException` là checked exception.

Có thể bắt ngoại lệ ở nơi gọi:

```java
try {
    String result = Decoder.decode(99);
    System.out.println(result);
} catch (java.io.IOException ex) {
    System.err.println("Decode failed: " + ex.getMessage());
}
```

Ở ví dụ này, `decode(99)` ném `IOException` nên câu lệnh `System.out.println(result)` **không chạy**; chương trình chuyển đến `catch`.

### Checked và unchecked chỉ khác ở nghĩa vụ khai báo/bắt

Cả hai loại đều làm `switch expression` **kết thúc bất thường**. Sự khác nhau nằm ở quy tắc biên dịch của Java:

```java
static int selectUnchecked(int value) {
    return switch (value) {
        case 0 -> 10;
        default -> throw new IllegalArgumentException("bad value");
    };
}
```

Ở đây không bắt buộc khai báo `throws IllegalArgumentException`. Tuy nhiên, ngoại lệ vẫn có thể lan tới caller khi chạy.

Nếu chuyển `IllegalArgumentException` thành một checked exception (ví dụ `IOException`), cần xử lý hoặc khai báo theo hợp đồng.

## 12. Ngoại lệ đi qua `switch expression` và phép gán như thế nào?

Xét:

```java
String label = "unchanged";

try {
    label = switch (code) {
        case 1 -> "ONE";
        case 2 -> "TWO";
        default -> throw new IllegalArgumentException("Invalid: " + code);
    };
} catch (IllegalArgumentException ex) {
    System.out.println("Rejected: " + ex.getMessage());
}

System.out.println(label);
```

Nếu `code == 1`, `label` trở thành `"ONE"`.

Nếu `code == 99`, switch expression ném trước khi hoàn thành giá trị cần gán; **phép gán không thực hiện**, nên `label` vẫn là `"unchanged"`. Sau đó code trong `catch` có thể xử lý ngoại lệ.

Điều này giúp hiểu vì sao không nên coi `throw` như một giá trị đặc biệt của biểu thức. Nó làm **chuyển luồng điều khiển**, chứ không tạo ra một giá trị theo kiểu của switch.

### Nguyên tắc tránh nuốt lỗi

Không nên bao quanh toàn bộ switch bằng `catch (Exception ex)` rồi trả về một giá trị hợp lệ giả nếu bạn không biết cách phục hồi. Ví dụ, chọn `"OK"` sau khi gặp một ngoại lệ bất ngờ có thể làm hệ thống hiểu nhầm trạng thái.

Thay vào đó, hãy:

- Bắt loại ngoại lệ mà tầng hiện tại có trách nhiệm xử lý.
- Ghi/biểu đạt lỗi theo hợp đồng API.
- Cho ngoại lệ truyền tiếp khi tầng hiện tại không có cách phục hồi phù hợp.

Đây là nguyên tắc xử lý ngoại lệ chung, áp dụng như nhau dù `throw` nằm trong switch hay ngoài switch.

## 13. Cú pháp nhãn dấu hai chấm `case ...:` vẫn hỗ trợ `throw`

Ngoài `->`, `switch expression` trong Java 17 vẫn hỗ trợ các **switch-labeled statement groups** dùng `case ...:` và `yield`.

Ví dụ:

```java
static String getLabel(int code) {
    return switch (code) {
        case 1:
            yield "ONE";

        case 2:
            System.out.println("Preparing TWO");
            yield "TWO";

        default:
            throw new IllegalArgumentException(
                    "Unsupported: " + code
            );
    };
}
```

Dù dùng cú pháp dấu hai chấm, nhánh `default` vẫn có thể trực tiếp `throw`. Điểm cần nhớ:

- `yield` đưa giá trị ra khỏi **switch expression**.
- `throw` ném ngoại lệ, không cần thêm `yield`.
- Với kiểu `case ...:`, cần hiểu quy tắc nhóm lệnh và khả năng *fall-through*. Nếu không có lý do cần giữ cú pháp cũ, `case ... ->` thường rõ hơn cho logic chọn giá trị.

Không nên viết `break` để gửi giá trị từ switch expression: `break value;` không phải cách cung cấp kết quả ở Java 17.

## 14. Các lỗi biên dịch và lỗi thiết kế thường gặp

### Lỗi 1 — Cố viết `yield throw ...`

Sai:

```java
// LỖI: throw là statement, không phải expression để yield.
// return switch (code) {
//     case 1 -> 10;
//     default -> {
//         yield throw new IllegalArgumentException();
//     }
// };
```

Đúng:

```java
return switch (code) {
    case 1 -> 10;
    default -> throw new IllegalArgumentException("Invalid code");
};
```

Hoặc:

```java
return switch (code) {
    case 1 -> 10;
    default -> {
        throw new IllegalArgumentException("Invalid code");
    }
};
```

### Lỗi 2 — Block có thể đi hết mà không `yield` hoặc `throw`

Sai:

```java
// LỖI:
// return switch (code) {
//     case 1 -> {
//         if (invalid) {
//             throw new IllegalStateException();
//         }
//         System.out.println("Still running");
//     }
//     default -> 0;
// };
```

Sửa bằng cách cho đường không ném ngoại lệ tạo giá trị:

```java
return switch (code) {
    case 1 -> {
        if (invalid) {
            throw new IllegalStateException();
        }
        yield 1;
    }
    default -> 0;
};
```

### Lỗi 3 — Nghĩ `default` nhận giá trị `null`

Sai về kỳ vọng:

```java
// Với input == null, đoạn này không vào default để ném
// IllegalArgumentException như người viết có thể tưởng.
String result = switch (input) {
    case "YES" -> "accepted";
    default -> throw new IllegalArgumentException("invalid value");
};
```

Đối với switch cơ bản trong Java 17, xử lý `null` ở trước nếu cần thông báo riêng.

### Lỗi 4 — Dùng sai loại ngoại lệ

Ví dụ `IllegalArgumentException` thường đúng khi đối số API không hợp lệ, nhưng không phải lựa chọn tối ưu nếu một thao tác thất bại do hệ thống đã ở trạng thái không cho phép. Hãy chọn loại ngoại lệ phản ánh nguyên nhân mà caller có thể hiểu và xử lý.

### Lỗi 5 — Bắt ngoại lệ rồi tự tạo giá trị thành công giả

```java
// Cách xử lý thường không tốt nếu fallback không thuộc hợp đồng:
// try {
//     return switch (code) {
//         case 1 -> "ONE";
//         default -> throw new IllegalArgumentException();
//     };
// } catch (Exception ignored) {
//     return "ONE"; // Có thể làm sai nghĩa dữ liệu
// }
```

Nếu API quy định một fallback hợp lệ, hãy thể hiện rõ trong thiết kế, chẳng hạn một nhánh trả về giá trị `"UNKNOWN"`. Nếu đầu vào bắt buộc hợp lệ, để ngoại lệ truyền ra sẽ rõ ràng hơn.

### Lỗi 6 — Dùng tính năng `switch` đang preview trong Java 17

Ở Java 17, các *type pattern case labels* như `case String s -> ...` thuộc tính năng preview của **pattern matching for switch**, không phải cú pháp cơ bản được bảo đảm chạy khi biên dịch Java 17 theo mặc định.

Trong bài này dùng các nhãn hằng số như `case 1`, `case "A"` hoặc `case ENUM_CONSTANT`, vốn ổn định trong Java 17. Không cần kích hoạt preview để học nhánh ném ngoại lệ của switch expression.

## 15. Ví dụ hoàn chỉnh chạy bằng JDK 17

Tạo file `SwitchThrowDemo.java`:

```java
public class SwitchThrowDemo {
    enum OrderState {
        NEW,
        PAID,
        SHIPPED,
        CANCELLED
    }

    static String nextAction(OrderState state) {
        return switch (state) {
            case NEW -> "Collect payment";
            case PAID -> "Prepare shipment";
            case SHIPPED -> "Track delivery";
            case CANCELLED -> throw new IllegalStateException(
                    "Cancelled order cannot continue"
            );
        };
    }

    static int parsePriority(String text) {
        if (text == null) {
            throw new IllegalArgumentException("priority is null");
        }

        return switch (text) {
            case "LOW" -> 1;
            case "MEDIUM" -> 2;
            case "HIGH" -> 3;
            default -> throw new IllegalArgumentException(
                    "Unsupported priority: " + text
            );
        };
    }

    public static void main(String[] args) {
        System.out.println(nextAction(OrderState.NEW));
        System.out.println(nextAction(OrderState.PAID));
        System.out.println(parsePriority("HIGH"));

        try {
            System.out.println(nextAction(OrderState.CANCELLED));
        } catch (IllegalStateException ex) {
            System.out.println("Order error: " + ex.getMessage());
        }

        try {
            System.out.println(parsePriority("URGENT"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Priority error: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SwitchThrowDemo.java
java SwitchThrowDemo
```

Kết quả dự kiến:

```text
Collect payment
Prepare shipment
3
Order error: Cancelled order cannot continue
Priority error: Unsupported priority: URGENT
```

Giải thích:

1. `OrderState.NEW` và `OrderState.PAID` dẫn đến nhánh trả `String`.
2. `OrderState.CANCELLED` là một hằng số enum đã được liệt kê nhưng nhánh tương ứng **ném ngoại lệ**.
3. Không có `default` trong switch enum vì bốn giá trị enum đã được bao phủ hết.
4. `parsePriority("HIGH")` tạo ra `3`.
5. `parsePriority("URGENT")` đi tới `default -> throw`.
6. Các khối `catch` trong `main` chỉ xử lý ngoại lệ được dự kiến; chúng không biến một nhánh `throw` thành nhánh tự trả giá trị.

## 16. Bài tập thực hành

### Bài 1 — Hoàn thiện `default -> throw`

Viết phương thức nhận mã trạng thái `0`, `1`, `2`. Mọi mã khác phải ném `IllegalArgumentException`.

Một cách làm:

```java
static String statusName(int status) {
    return switch (status) {
        case 0 -> "PENDING";
        case 1 -> "RUNNING";
        case 2 -> "DONE";
        default -> throw new IllegalArgumentException(
                "Invalid status: " + status
        );
    };
}
```

Thử tự trả lời: phương thức có trả về `null` khi nhận `99` không?

**Đáp án:** Không. Nó ném ngoại lệ, nên không tạo `String` kết quả.

### Bài 2 — Kết hợp `yield` và `throw`

Yêu cầu: tính phí xử lý với mã `1` hoặc `2`; nếu giá trị tiền âm phải ném ngoại lệ; mã khác cũng bị từ chối.

```java
static int fee(int code, int amount) {
    return switch (code) {
        case 1 -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount < 0");
            }
            yield amount / 10;
        }
        case 2 -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount < 0");
            }
            yield amount / 5;
        }
        default -> throw new IllegalArgumentException(
                "Invalid fee code: " + code
        );
    };
}
```

Chỉ ra hai loại đường đi: đường có kết quả `yield` và đường kết thúc bằng `throw`. Không có đường nào đi hết block mà bỏ trống kết quả.

### Bài 3 — Với enum, nhánh ném ngoại lệ có được tính là xử lý không?

```java
enum Light {
    RED,
    YELLOW,
    GREEN
}

static int seconds(Light light) {
    return switch (light) {
        case RED -> 30;
        case YELLOW -> 5;
        case GREEN -> throw new IllegalStateException(
                "No waiting time for green light"
        );
    };
}
```

**Đáp án:** Có. `GREEN` đã có nhánh xử lý bằng `throw`; switch expression bao phủ đủ ba hằng số enum. Nhánh không nhất thiết trả `int` trong mọi trường hợp, nhưng mỗi đường phải kết thúc bằng giá trị hoặc ngoại lệ.

### Bài 4 — Tìm lỗi trong block

```java
// Không biên dịch:
static int getValue(int key, boolean rejected) {
    return switch (key) {
        case 1 -> {
            if (rejected) {
                throw new IllegalStateException();
            }
        }
        default -> 0;
    };
}
```

**Nguyên nhân:** Nếu `key == 1` và `rejected == false`, block kết thúc bình thường mà không tạo giá trị. Sửa bằng `yield` ở đường này:

```java
static int getValue(int key, boolean rejected) {
    return switch (key) {
        case 1 -> {
            if (rejected) {
                throw new IllegalStateException();
            }
            yield 100;
        }
        default -> 0;
    };
}
```

### Bài 5 — Nhận diện checked exception

Điều gì cần thay đổi để phương thức sau biên dịch?

```java
// Đoạn thiếu khai báo throws:
static String load(int type) {
    return switch (type) {
        case 1 -> "TEXT";
        default -> throw new java.io.IOException("Unsupported");
    };
}
```

**Đáp án:** Vì `IOException` là checked exception, cần khai báo `throws java.io.IOException` ở chữ ký phương thức (hoặc tổ chức bắt/xử lý ngoại lệ phù hợp). Với cách tiếp cận khai báo:

```java
static String load(int type) throws java.io.IOException {
    return switch (type) {
        case 1 -> "TEXT";
        default -> throw new java.io.IOException("Unsupported");
    };
}
```

## 17. Ghi nhớ quy tắc ngắn gọn

Mẫu thường dùng:

```java
Result result = switch (selector) {
    case VALID_A -> createResultA();
    case VALID_B -> {
        if (someInvalidCondition()) {
            throw new IllegalStateException("Invalid state");
        }
        yield createResultB();
    }
    default -> throw new IllegalArgumentException(
            "Unsupported value: " + selector
    );
};
```

Khi đọc một switch expression có `throw`, hãy xét:

1. **Nhánh nào trả giá trị?** Dùng biểu thức sau `->` hoặc `yield` trong block.
2. **Nhánh nào ném ngoại lệ?** Dùng `throw` trực tiếp sau `->` hoặc trong block.
3. **Có đường thực thi nào kết thúc block mà không trả giá trị hoặc ném không?** Nếu có, code thường bị lỗi biên dịch.
4. **Danh sách case có exhaustive không?** Với `int`/`String` thường dùng `default`; với enum có thể liệt kê hết hằng số.
5. **Ngoại lệ được khai báo/xử lý đúng chưa?** Đặc biệt khi dùng checked exception.
6. **Nếu selector có thể là `null`, API đã quy định rõ cách xử lý chưa?** Trong switch cơ bản Java 17, `default` không bắt `null`.

Nhánh `throw` giúp mô tả rõ ràng những trường hợp **không có kết quả hợp lệ để trả về**, thay vì gán một giá trị giả chỉ để làm cho biểu thức biên dịch.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions-and-statements.html).
- [Java Language Specification 17 — `15.28`: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28).
- [Java Language Specification 17 — `14.11`: Switch Statements and Switch Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11).
- [Java Language Specification 17 — `14.21`: The `yield` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21).
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361).

