# Phân biệt `switch statement` và `switch expression` trong Java 17

**Chủ đề:** Java 17  
**Chương:** Switch expression  
**Bài học:** Phân biệt switch statement và switch expression

Trong Java 17, từ khóa `switch` có thể tạo ra **một câu lệnh điều khiển luồng** (*switch statement*) hoặc **một biểu thức tạo ra giá trị** (*switch expression*). Hai cách dùng chia sẻ nhiều phần cú pháp như `case`, `default`, dấu hai chấm `:` và mũi tên `->`, nhưng khác nhau về mục đích, kết quả, khả năng kết thúc nhánh và yêu cầu bao phủ các trường hợp.

Điểm cần nắm ngay từ đầu:

- **`switch statement`:** Chọn và thực thi các câu lệnh. Bản thân `switch` không có giá trị trả về.
- **`switch expression`:** Chọn một nhánh và **tạo ra một giá trị** để gán vào biến, trả về từ phương thức hoặc dùng trong một biểu thức lớn hơn.
- **Dấu `->` không đồng nghĩa với switch expression.** Cả switch statement lẫn switch expression trong Java 17 đều có thể viết nhánh bằng `->`.
- **`yield` không phải `break` và không phải `return`.** `yield` cung cấp giá trị cho switch expression; `break` dùng để điều khiển luồng của statement; `return` trả về khỏi phương thức.
- **Switch expression đã là cú pháp ổn định từ Java 14 (JEP 361)**, được Java 17 kế thừa. Pattern matching cho `switch` trong Java 17 vẫn là **preview**, không thuộc cú pháp ổn định dùng trong bài này.

## 1. Cùng một bài toán, hai cách viết

Giả sử hệ thống có trạng thái đơn hàng:

```java
enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Ta muốn biến một trạng thái thành dòng chữ hiển thị.

### 1.1. `switch statement`: thực hiện câu lệnh

```java
static String labelWithStatement(OrderStatus status) {
    String label;

    switch (status) {
        case NEW:
            label = "Mới tạo";
            break;
        case PAID:
            label = "Đã thanh toán";
            break;
        case CANCELLED:
            label = "Đã hủy";
            break;
        default:
            throw new IllegalStateException("Trạng thái không hỗ trợ");
    }

    return label;
}
```

Đây là **switch statement** vì toàn bộ cấu trúc đứng ở vị trí một **câu lệnh độc lập**. Các nhánh tự gán vào biến `label`; cấu trúc `switch` không trực tiếp tạo ra giá trị `String`.

Cú pháp dấu hai chấm `case ...:` có thể chuyển tiếp sang nhánh tiếp theo (*fall-through*), nên `break` được dùng để dừng xử lý sau mỗi nhánh. Biến `label` phải được Java chứng minh là đã gán trước khi câu lệnh `return label` sử dụng nó.

### 1.2. `switch expression`: tạo giá trị

```java
static String labelWithExpression(OrderStatus status) {
    return switch (status) {
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
```

Đây là **switch expression** vì `switch (status) { ... }` chính là biểu thức có giá trị `String`; giá trị đó được dùng làm đối số cho `return` của phương thức.

Khác biệt nổi bật:

- Không cần khai báo biến trung gian.
- Mỗi nhánh `->` trả về một giá trị biểu thức.
- Không cần `break`.
- Khi `status` là `enum OrderStatus`, compiler thấy đủ mọi hằng enum nên không bắt buộc viết `default`.

Cũng có thể dùng ở vế phải phép gán:

```java
String label = switch (status) {
    case NEW -> "Mới tạo";
    case PAID -> "Đã thanh toán";
    case CANCELLED -> "Đã hủy";
};
```

**Chú ý dấu chấm phẩy:** Dấu `;` cuối cùng trong ví dụ gán biến kết thúc **câu lệnh khai báo/gán bên ngoài**, không phải một `break` và cũng không thuộc nội dung từng nhánh.

## 2. Bảng so sánh tổng quan

| Tiêu chí | `switch statement` | `switch expression` |
|---|---|---|
| Vai trò | Câu lệnh điều khiển luồng | Biểu thức tạo ra một giá trị |
| Có giá trị của chính `switch`? | Không | Có |
| Vị trí thường dùng | Đứng riêng để thực hiện hành động | Trong phép gán, `return`, lời gọi phương thức hoặc biểu thức khác |
| Cú pháp `case:` | Có | Có |
| Cú pháp `case ->` | Có | Có |
| Có thể fall-through? | Có với kiểu `case:` | Có thể có với kiểu `case:`; `case ->` không fall-through |
| `break` | Thường dùng ở các nhánh `case:` để thoát statement | Không dùng `break` để cung cấp giá trị |
| `yield` | Không dùng để cung cấp kết quả cho chính statement | Dùng trong block hoặc nhóm nhánh để tạo giá trị |
| Bao phủ mọi trường hợp | Statement thông thường có thể không có nhánh khớp | Phải **exhaustive**: mọi giá trị đầu vào hợp lệ có đường tạo giá trị hoặc ném ngoại lệ |
| Kiểm tra kiểu kết quả | Không có kiểu kết quả của `switch` | Compiler xác định kiểu của switch expression |
| Tình huống điển hình | Ghi log, thực thi side effect, điều khiển tác vụ | Ánh xạ trạng thái thành giá trị, tính toán kết quả |

**Một quy tắc đọc mã đơn giản:** Nhìn **toàn bộ vị trí** của `switch` trong câu lệnh Java. Nếu là `String text = switch (...) { ... };` hoặc `return switch (...) { ... };`, đó là expression. Nếu đứng riêng `switch (...) { ... }` để gọi hàm hay gán biến, đó là statement. Không thể phân biệt chỉ dựa vào dấu `->`.

## 3. Hai phong cách viết nhánh: `case:` và `case ->`

Trên Java 17 có hai cách viết phần thân của một `switch`.

### 3.1. Phong cách truyền thống với dấu hai chấm

```java
static void showLevel(int level) {
    switch (level) {
        case 1:
            System.out.println("Cơ bản");
            break;
        case 2:
            System.out.println("Trung cấp");
            break;
        default:
            System.out.println("Khác");
    }
}
```

Mỗi `case ...:` là một nhãn trong switch block; khi chương trình đi vào một nhãn, nó tiếp tục chạy các statement phía sau cho đến khi gặp `break`, `return`, `throw` hoặc kết thúc block. Vì vậy, cú pháp này có **khả năng fall-through**.

### 3.2. Phong cách mũi tên trong switch statement

```java
static void showLevel(int level) {
    switch (level) {
        case 1 -> System.out.println("Cơ bản");
        case 2 -> System.out.println("Trung cấp");
        default -> System.out.println("Khác");
    }
}
```

Đây vẫn là **statement**. Mũi tên chỉ tạo **switch rule** với một nhánh thực thi độc lập:

- Chỉ thực thi phần bên phải mũi tên của nhánh được chọn.
- Không tự chạy tiếp phần của nhánh tiếp theo.
- Không cần `break` cho từng nhánh.
- Phần bên phải trong **switch statement** có thể là một *statement expression* như lời gọi phương thức, một block, hoặc `throw`.

Khi cần nhiều câu lệnh:

```java
switch (level) {
    case 1 -> {
        System.out.println("Bắt đầu");
        System.out.println("Học các khái niệm cơ bản");
    }
    case 2 -> {
        System.out.println("Tiếp tục");
        System.out.println("Luyện bài nâng cao");
    }
    default -> System.out.println("Không xác định");
}
```

Không có `yield` vì mục tiêu chỉ là thực hiện hành động, không tạo giá trị của switch.

### 3.3. Phong cách mũi tên trong switch expression

```java
static String levelName(int level) {
    return switch (level) {
        case 1 -> "Cơ bản";
        case 2 -> "Trung cấp";
        default -> "Không xác định";
    };
}
```

Phần bên phải `->` bây giờ là giá trị biểu thức, hoặc một block dùng `yield` để đưa ra giá trị, hoặc một lệnh `throw`. Bản thân `switch` tạo ra kết quả được sử dụng bởi `return`.

### 3.4. Mũi tên không phải bằng chứng về loại switch

Hai đoạn mã sau rất dễ bị đọc nhầm:

```java
// SWITCH STATEMENT
switch (status) {
    case NEW -> System.out.println("Tạo mới");
    case PAID -> System.out.println("Đã trả");
    case CANCELLED -> System.out.println("Đã hủy");
}
```

```java
// SWITCH EXPRESSION
String label = switch (status) {
    case NEW -> "Tạo mới";
    case PAID -> "Đã trả";
    case CANCELLED -> "Đã hủy";
};
```

Cả hai dùng `->` và đều không fall-through. **Điểm phân biệt là switch có được dùng làm một giá trị hay không**, cùng quy tắc giá trị của mỗi nhánh.

## 4. `break` và `yield` giải quyết hai nhu cầu khác nhau

### 4.1. `break`: thoát khỏi switch statement

```java
int day = 1;

switch (day) {
    case 1:
        System.out.println("Thứ Hai");
        break;
    case 2:
        System.out.println("Thứ Ba");
        break;
    default:
        System.out.println("Khác");
}
```

Ở đây, `break` kết thúc switch statement. Nó **không** trả về `String` hay một giá trị tính toán nào từ `switch`.

### 4.2. `yield`: trao giá trị cho switch expression

Khi một nhánh của expression phải thực hiện nhiều bước, dùng block và `yield`:

```java
static int shippingFee(String mode, int distanceKm) {
    return switch (mode) {
        case "STANDARD" -> {
            int base = 10_000;
            int extra = Math.max(0, distanceKm - 5) * 1_000;
            yield base + extra;
        }
        case "EXPRESS" -> {
            int base = 20_000;
            int extra = Math.max(0, distanceKm - 3) * 2_000;
            yield base + extra;
        }
        default -> throw new IllegalArgumentException(
                "Phương thức giao hàng không hợp lệ: " + mode);
    };
}
```

Luồng thực thi trong nhánh `STANDARD`:

1. Tính phí cơ bản.
2. Tính phần phí cộng thêm.
3. `yield base + extra;` tạo ra giá trị của **switch expression**.
4. Phương thức `shippingFee` nhận giá trị của biểu thức qua `return switch ...`.

Không thể thay `yield base + extra;` bằng `break;` để cung cấp phí vận chuyển. `break` không có giá trị kết quả.

### 4.3. `yield` khác `return`

```java
static String outcome(boolean valid) {
    return switch (valid ? 1 : 0) {
        case 1 -> {
            String message = "Hợp lệ";
            yield message;          // Trả giá trị cho switch expression
        }
        default -> "Không hợp lệ";
    };
}
```

`yield` kết thúc nhánh của expression; `return` bên ngoài trả giá trị từ **phương thức**. Trong tình huống có các bước xử lý ở nhánh, `yield` giữ cấu trúc rõ ràng.

`yield` không phải phiên bản mới của `break value`. Cú pháp thử nghiệm cũ `break value` không phải cách viết chuẩn của switch expression trong Java 17.

### 4.4. `throw` là một nhánh hợp lệ của expression

```java
static String roleLabel(int code) {
    return switch (code) {
        case 1 -> "ADMIN";
        case 2 -> "USER";
        default -> throw new IllegalArgumentException("Unknown role: " + code);
    };
}
```

Nhánh `default` không tạo chuỗi, nhưng **ném ngoại lệ**, nên không thể hoàn thành bình thường mà thiếu giá trị. Điều này hợp lệ với switch expression.

### 4.5. `case:` vẫn có thể dùng trong switch expression

```java
static String scoreLabel(int score) {
    return switch (score) {
        case 0:
            yield "Chưa có điểm";
        case 1:
        case 2:
            yield "Điểm thấp";
        default:
            yield "Điểm khác";
    };
}
```

Trong ví dụ này, phần thân là switch expression dù dùng `case:`. `yield` cung cấp giá trị cho biểu thức. Các nhãn `case 1:` và `case 2:` cùng dẫn đến nhánh xử lý chung.

Với cú pháp mũi tên, có thể viết ngắn hơn:

```java
static String scoreLabel(int score) {
    return switch (score) {
        case 0 -> "Chưa có điểm";
        case 1, 2 -> "Điểm thấp";
        default -> "Điểm khác";
    };
}
```

Khi không cần hiệu ứng fall-through, kiểu `->` thường dễ đọc và ít lỗi hơn.

## 5. Fall-through: đặc điểm của dấu hai chấm, không phải của statement nói chung

**Fall-through** nghĩa là sau khi chọn một nhánh, chương trình tiếp tục chạy các câu lệnh ở nhánh phía sau nếu không có điểm kết thúc luồng phù hợp.

### 5.1. Fall-through có thể gây lỗi

```java
int priority = 1;

switch (priority) {
    case 1:
        System.out.println("Cao");
        // Quên break!
    case 2:
        System.out.println("Trung bình");
        break;
    default:
        System.out.println("Thấp");
}
```

Kết quả:

```text
Cao
Trung bình
```

Nếu người viết muốn chỉ in `"Cao"`, việc quên `break` là lỗi. Nhưng cũng có tình huống cố ý gộp nhãn:

```java
switch (priority) {
    case 1:
    case 2:
        System.out.println("Cần xử lý");
        break;
    default:
        System.out.println("Để sau");
}
```

### 5.2. Dùng mũi tên để ngăn fall-through

```java
switch (priority) {
    case 1, 2 -> System.out.println("Cần xử lý");
    default -> System.out.println("Để sau");
}
```

Tương tự, trong switch expression:

```java
String action = switch (priority) {
    case 1, 2 -> "PROCESS_NOW";
    default -> "PROCESS_LATER";
};
```

Ở đây không có fall-through. **Không nên diễn giải “statement thì có fall-through, expression thì không”**. Điều chính xác là:

- Cách viết **`case:`** cho phép luồng chạy tiếp giữa các nhóm nhánh khi không bị chặn; cách này tồn tại trong cả switch statement và switch expression.
- Cách viết **`case ->`** không fall-through, dù toàn bộ `switch` là statement hay expression.

## 6. Exhaustiveness: switch expression phải bao phủ mọi giá trị đầu vào

Switch expression phải **exhaustive**: một giá trị selector hợp lệ không được dẫn đến việc biểu thức hoàn thành bình thường mà thiếu giá trị.

### 6.1. Switch statement có thể bỏ `default`

```java
static void printKnownCode(int code) {
    switch (code) {
        case 100 -> System.out.println("OK");
        case 404 -> System.out.println("NOT_FOUND");
    }
}
```

Với `code = 500`, không nhánh nào khớp. Switch statement hoàn thành mà không in gì. Đây là hành vi hợp lệ của statement trong ví dụ.

### 6.2. Switch expression trên `int` cần nhánh dự phòng

Đoạn sau **không hợp lệ**:

```java
// KHÔNG BIÊN DỊCH: switch expression không exhaustive.
static String httpLabel(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 404 -> "Not Found";
    };
}
```

`int` có quá nhiều giá trị để hai nhánh bao phủ hết. Cần bổ sung `default`:

```java
static String httpLabel(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 404 -> "Not Found";
        default -> "Other";
    };
}
```

Nhánh `default` có thể tạo giá trị hoặc ném ngoại lệ, tùy hợp đồng của phương thức.

### 6.3. `enum` được bao phủ toàn bộ có thể không cần `default`

```java
enum PaymentState {
    CREATED, APPROVED, DECLINED
}

static String describe(PaymentState state) {
    return switch (state) {
        case CREATED -> "Đã tạo";
        case APPROVED -> "Đã duyệt";
        case DECLINED -> "Bị từ chối";
    };
}
```

Compiler biết các hằng `enum` đang được khai báo, vì vậy ba nhánh đủ để chứng minh expression exhaustive. Không bắt buộc có `default`.

Nếu sau này thêm hằng `REFUNDED` vào `PaymentState`, khi biên dịch lại mã trên, switch expression có thể bị báo thiếu nhánh. Điều này hữu ích để phát hiện chỗ chưa cập nhật logic. Tuy nhiên, khi thay đổi enum độc lập với các class đã được biên dịch trước đó, vẫn cần xem xét tương thích runtime; exhaustive tại thời điểm biên dịch không bảo đảm mọi phiên bản triển khai sau này đã đồng bộ.

### 6.4. Statement có thể vẫn cần gán biến đầy đủ

Không nên nhầm “statement không bắt buộc exhaustive” với “compiler bỏ qua definite assignment”.

```java
static String statusText(int code) {
    String result;

    switch (code) {
        case 1:
            result = "ONE";
            break;
        // Không có default.
    }

    return result; // LỖI BIÊN DỊCH: result có thể chưa được gán.
}
```

Bản thân switch statement không bị cấm vì thiếu `default`. Nhưng biến cục bộ `result` có khả năng chưa được gán trước khi `return` dùng nó. Đây là một phép kiểm tra khác của Java.

Có thể sửa bằng `default`, gán giá trị ban đầu phù hợp, hoặc dùng switch expression có nhánh đầy đủ.

## 7. Kiểu dữ liệu selector trong Java 17

Với cú pháp switch **ổn định** của Java 17, selector thường là:

- `byte`, `short`, `char` hoặc `int`.
- Các wrapper tương ứng: `Byte`, `Short`, `Character`, `Integer`.
- `String`.
- Một kiểu `enum`.

Ví dụ với chuỗi:

```java
static int retryCount(String mode) {
    return switch (mode) {
        case "FAST" -> 1;
        case "NORMAL" -> 3;
        case "SAFE" -> 5;
        default -> throw new IllegalArgumentException("Unknown mode");
    };
}
```

Ví dụ với enum:

```java
enum Environment { DEV, TEST, PROD }

static boolean allowDebug(Environment environment) {
    return switch (environment) {
        case DEV, TEST -> true;
        case PROD -> false;
    };
}
```

**Lưu ý theo phiên bản:** Không sử dụng `switch` chuẩn Java 17 với `long`, `float`, `double` hay `boolean` làm selector. Một số cú pháp có thể được nới rộng hoặc thử nghiệm trong các phiên bản Java khác, nhưng bài này mô tả Java 17 ổn định.

### 7.1. `null` không phải một nhánh chuẩn trong Java 17

Nếu một selector kiểu tham chiếu là `null`, một switch statement hoặc expression thông thường trên Java 17 sẽ ném `NullPointerException`.

```java
String level = null;

// Ném NullPointerException khi đánh giá switch:
String label = switch (level) {
    case "HIGH" -> "Cao";
    default -> "Khác";
};
```

Nhánh `default` **không bắt `null`**. Cần kiểm tra trước:

```java
static String safeLabel(String level) {
    if (level == null) {
        return "Chưa xác định";
    }
    return switch (level) {
        case "HIGH" -> "Cao";
        case "LOW" -> "Thấp";
        default -> "Khác";
    };
}
```

Cú pháp `case null` thuộc phạm vi phát triển pattern matching for switch, **chưa là cú pháp switch ổn định trên Java 17**. Không đưa nó vào ví dụ biên dịch mặc định.

### 7.2. Các nhãn `case` không chấp nhận điều kiện bất kỳ

```java
int value = 20;

// KHÔNG PHẢI CÚ PHÁP SWITCH THÔNG THƯỜNG CỦA JAVA 17:
switch (value) {
    // case value > 10 -> System.out.println("Lớn");
}
```

Case trong switch truyền thống cần các nhãn hằng hợp lệ (hoặc hằng enum tương ứng), không phải biểu thức điều kiện tùy ý như `value > 10`. Với điều kiện khoảng, tổ hợp logic hoặc so sánh phức tạp, `if/else` có thể rõ ràng hơn:

```java
static String classify(int value) {
    if (value > 10) {
        return "Lớn";
    }
    return "Không lớn";
}
```

Không nên cố thay thế mọi `if` bằng `switch expression`.

## 8. Kiểu kết quả của switch expression

Vì switch expression tạo giá trị, compiler phải xác định **kiểu kết quả** từ các nhánh và ngữ cảnh sử dụng.

### 8.1. Các nhánh cùng kiểu

```java
int score = switch (grade) {
    case "A" -> 100;
    case "B" -> 80;
    default -> 0;
};
```

Các nhánh đều tạo `int` nên giá trị tổng có thể gán cho `int score`.

### 8.2. Trả trực tiếp từ phương thức

```java
static boolean canShip(OrderStatus status) {
    return switch (status) {
        case NEW -> false;
        case PAID -> true;
        case CANCELLED -> false;
    };
}
```

Kiểu của expression phù hợp với kiểu trả về `boolean` của phương thức. Việc gom logic thành biểu thức thường giúp kết quả được kiểm tra ngay tại điểm sử dụng.

### 8.3. Kiểu kết quả phải tương thích

Ví dụ dưới đây không hợp lệ nếu cần kết quả `int` mà một nhánh trả `String`:

```java
// KHÔNG HỢP LỆ: một nhánh là String, không thể gán toàn bộ vào int.
int result = switch (code) {
    case 1 -> 100;
    default -> "unknown";
};
```

Có thể chọn một kiểu kết quả thống nhất:

```java
String result = switch (code) {
    case 1 -> "100";
    default -> "unknown";
};
```

Đừng hiểu rằng mọi nhánh của switch expression buộc phải viết đúng **cùng một kiểu ký tự** trong mã nguồn. Java có cơ chế suy luận và chuyển kiểu hợp lệ tùy ngữ cảnh. Nguyên tắc thực tế là: **giá trị của expression phải phù hợp với kiểu mà nơi sử dụng yêu cầu**.

### 8.4. Khối lệnh có `yield` phải tạo giá trị phù hợp

```java
static int discountPercent(String customerTier) {
    return switch (customerTier) {
        case "GOLD" -> {
            int base = 10;
            int promotion = 5;
            yield base + promotion;
        }
        case "SILVER" -> 5;
        default -> 0;
    };
}
```

Giá trị được tạo ra trong nhánh block là kết quả của biểu thức sau `yield`, không phải giá trị của câu lệnh cuối bất kỳ trong block.

## 9. Switch statement có thể viết ngắn nhưng không biến thành expression

Người mới học thường dùng dấu `->` trong statement rồi cho rằng có thể gán toàn bộ switch vào biến. Hãy xem hai phiên bản cùng ý nghĩa.

**Statement với assignment ở từng nhánh:**

```java
static String categoryStatement(int code) {
    String category;

    switch (code) {
        case 1 -> category = "A";
        case 2 -> category = "B";
        default -> category = "OTHER";
    }

    return category;
}
```

Vì các nhánh dùng phép gán `category = ...` là statement expression, đây vẫn là **switch statement**. Biến nhận giá trị thông qua side effect của từng nhánh.

**Expression tạo giá trị trực tiếp:**

```java
static String categoryExpression(int code) {
    return switch (code) {
        case 1 -> "A";
        case 2 -> "B";
        default -> "OTHER";
    };
}
```

Trong ví dụ expression, không cần biến trung gian và cũng không có phép gán trong từng nhánh. `switch` là một giá trị có thể truyền vào phương thức khác:

```java
System.out.println(
    switch (code) {
        case 1 -> "A";
        case 2 -> "B";
        default -> "OTHER";
    }
);
```

Cách này phù hợp khi các nhánh đại diện cho **cùng một phép tính có nhiều khả năng**. Nếu mỗi nhánh làm hàng loạt thao tác độc lập như gửi email, ghi database, điều phối tác vụ, statement có thể thể hiện ý định rõ hơn.

## 10. Ví dụ áp dụng: tính giá theo loại vé

Giả sử chương trình cần chọn giá vé theo loại:

```java
enum TicketType {
    STANDARD, STUDENT, VIP
}
```

### 10.1. Dùng switch statement với dấu hai chấm

```java
static int priceWithStatement(TicketType type) {
    int price;

    switch (type) {
        case STANDARD:
            price = 100_000;
            break;
        case STUDENT:
            price = 70_000;
            break;
        case VIP:
            price = 200_000;
            break;
        default:
            throw new IllegalArgumentException("Unsupported ticket type");
    }

    return price;
}
```

Đúng về ngữ nghĩa, nhưng cần cập nhật biến và dừng từng nhánh bằng `break`.

### 10.2. Dùng switch statement với mũi tên

```java
static int priceWithArrowStatement(TicketType type) {
    int price;

    switch (type) {
        case STANDARD -> price = 100_000;
        case STUDENT -> price = 70_000;
        case VIP -> price = 200_000;
    }

    return price;
}
```

**Ví dụ này cần thận trọng:** Với một switch statement thông thường, dù mã đã liệt kê mọi hằng enum hiện tại, compiler không nhất thiết coi việc gán `price` trong các nhánh là bảo đảm definite assignment như trong switch expression. Khi cần chắc chắn tất cả đường đi gán giá trị, hãy thêm `default` hoặc dùng switch expression.

Phiên bản statement an toàn, rõ ràng:

```java
static int priceWithArrowStatement(TicketType type) {
    int price;

    switch (type) {
        case STANDARD -> price = 100_000;
        case STUDENT -> price = 70_000;
        case VIP -> price = 200_000;
        default -> throw new IllegalArgumentException("Unsupported ticket type");
    }

    return price;
}
```

### 10.3. Dùng switch expression

```java
static int priceWithExpression(TicketType type) {
    return switch (type) {
        case STANDARD -> 100_000;
        case STUDENT -> 70_000;
        case VIP -> 200_000;
    };
}
```

Cách viết này phản ánh trực tiếp ý nghĩa: **loại vé quyết định giá tiền**, và Java kiểm tra expression có đủ nhánh enum hiện tại.

Khi các nhánh đơn giản chỉ trả về giá trị, switch expression thường ngắn và có ít bước điều khiển luồng hơn.

## 11. Ví dụ hoàn chỉnh chạy trên Java 17

Để quan sát cả hai dạng mà không cần thư viện bên ngoài, lưu mã dưới đây thành **`SwitchStatementVsExpression.java`**:

```java
public class SwitchStatementVsExpression {

    enum State {
        CREATED, PAID, CANCELLED
    }

    // Statement truyền thống: gán biến rồi break.
    static String viaColonStatement(State state) {
        String label;

        switch (state) {
            case CREATED:
                label = "Đã tạo";
                break;
            case PAID:
                label = "Đã thanh toán";
                break;
            case CANCELLED:
                label = "Đã hủy";
                break;
            default:
                throw new IllegalArgumentException("Unsupported state");
        }

        return label;
    }

    // Statement dạng mũi tên: thực hiện hành động, không tạo giá trị switch.
    static void printAction(State state) {
        switch (state) {
            case CREATED -> System.out.println("Cho phép sửa đơn");
            case PAID -> System.out.println("Chuẩn bị giao hàng");
            case CANCELLED -> System.out.println("Không giao hàng");
        }
    }

    // Expression dạng mũi tên: trả giá trị trực tiếp.
    static String viaExpression(State state) {
        return switch (state) {
            case CREATED -> "Đã tạo";
            case PAID -> "Đã thanh toán";
            case CANCELLED -> "Đã hủy";
        };
    }

    // Expression với block: dùng yield.
    static int rewardPoints(State state, int amount) {
        return switch (state) {
            case CREATED, CANCELLED -> 0;
            case PAID -> {
                int basePoints = amount / 10_000;
                int bonus = amount >= 100_000 ? 5 : 0;
                yield basePoints + bonus;
            }
        };
    }

    public static void main(String[] args) {
        State state = State.PAID;

        System.out.println(viaColonStatement(state));
        printAction(state);
        System.out.println(viaExpression(state));
        System.out.println("Điểm thưởng: " + rewardPoints(state, 120_000));
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 SwitchStatementVsExpression.java
java SwitchStatementVsExpression
```

Kết quả dự kiến:

```text
Đã thanh toán
Chuẩn bị giao hàng
Đã thanh toán
Điểm thưởng: 17
```

Giải thích `17`: `120_000 / 10_000 = 12` điểm cơ bản, thêm `5` điểm thưởng vì đơn hàng từ `100_000` trở lên.

Trong cùng một chương trình, ba dạng khác nhau cùng tồn tại:

- Statement với `case:` và `break`.
- Statement với `case ->` để thực hiện hành động.
- Expression với `case ->` và `yield` khi cần tính toán trong block.

Tất cả đều là cú pháp **ổn định trên Java 17**.

## 12. Khi nào nên chọn statement, khi nào nên chọn expression?

### 12.1. Ưu tiên expression khi mọi nhánh cùng tạo một kết quả

Ví dụ chọn cấu hình:

```java
static int timeoutSeconds(String environment) {
    return switch (environment) {
        case "DEV" -> 5;
        case "TEST" -> 10;
        case "PROD" -> 30;
        default -> throw new IllegalArgumentException(
                "Unknown environment: " + environment);
    };
}
```

Ở đây, tất cả nhánh cùng trả về **thời gian timeout**, nên expression biểu diễn ý tưởng ngắn gọn và rõ ràng.

### 12.2. Ưu tiên statement khi mục đích là thực hiện tác vụ

```java
static void dispatch(String command) {
    switch (command) {
        case "START" -> System.out.println("Khởi động dịch vụ");
        case "STOP" -> System.out.println("Dừng dịch vụ");
        case "RELOAD" -> {
            System.out.println("Đọc lại cấu hình");
            System.out.println("Khởi tạo lại thành phần cần thiết");
        }
        default -> System.out.println("Lệnh không hỗ trợ");
    }
}
```

Cấu trúc này không cần tạo ra một giá trị. Cố ép thành expression chỉ để dùng cú pháp mới có thể làm mã khó hiểu hơn.

### 12.3. Với điều kiện phức tạp, có thể chọn `if/else`

```java
static String deliveryBand(int distanceKm) {
    if (distanceKm < 0) {
        throw new IllegalArgumentException("distanceKm must be non-negative");
    }
    if (distanceKm <= 3) {
        return "Gần";
    }
    if (distanceKm <= 15) {
        return "Trung bình";
    }
    return "Xa";
}
```

Đây là bài toán so sánh khoảng số chứ không phải chọn theo một danh sách nhãn hằng. Trong Java 17, `if/else` là lựa chọn phù hợp hơn.

### 12.4. Không trộn hiệu ứng phụ không cần thiết vào expression

Một switch expression vẫn có thể chứa lời gọi hàm, ghi log hoặc kiểm tra dữ liệu trong block. Tuy nhiên, nếu phần lớn mã chỉ thực hiện side effect, statement thường thể hiện mục đích tốt hơn. Dùng expression khi một **giá trị tổng hợp** là kết quả chính của phép chọn nhánh.

## 13. Các lỗi thường gặp khi chuyển từ statement sang expression

### Lỗi 1. Quên `break` trong statement kiểu dấu hai chấm

```java
switch (code) {
    case 1:
        System.out.println("A");
        // Quên break, sẽ tiếp tục sang case 2.
    case 2:
        System.out.println("B");
        break;
}
```

**Cách xử lý:** Dùng `break` đúng vị trí hoặc chuyển sang `case ->` nếu không chủ ý fall-through.

### Lỗi 2. Nhìn `->` rồi gọi đó là expression

```java
switch (code) {
    case 1 -> System.out.println("A");
    default -> System.out.println("B");
}
```

Đây là **switch statement**, vì nó đứng độc lập và chỉ thực hiện hành động.

### Lỗi 3. Cố dùng `break` để trả giá trị

```java
// KHÔNG HỢP LỆ trong switch expression chuẩn Java 17:
int size = switch (kind) {
    case 1 -> {
        break 10;
    }
    default -> 0;
};
```

Dùng `yield`:

```java
int size = switch (kind) {
    case 1 -> {
        yield 10;
    }
    default -> 0;
};
```

### Lỗi 4. Viết block nhưng quên `yield`

```java
// KHÔNG HỢP LỆ: nhánh block có thể kết thúc mà không tạo giá trị.
String text = switch (code) {
    case 1 -> {
        System.out.println("Đã chọn 1");
    }
    default -> "Other";
};
```

Sửa:

```java
String text = switch (code) {
    case 1 -> {
        System.out.println("Đã chọn 1");
        yield "One";
    }
    default -> "Other";
};
```

### Lỗi 5. Thiếu `default` trong expression trên `int` hoặc `String`

```java
// KHÔNG HỢP LỆ: chưa xử lý tất cả chuỗi có thể có.
String description = switch (mode) {
    case "A" -> "Mode A";
    case "B" -> "Mode B";
};
```

Sửa bằng nhánh `default` trả giá trị hoặc ném ngoại lệ.

### Lỗi 6. Xem `default` như cách xử lý `null`

```java
String mode = null;

String result = switch (mode) {
    case "A" -> "Mode A";
    default -> "Other";
};
```

Với Java 17 chuẩn, trường hợp selector `null` ném `NullPointerException`. Hãy xử lý `null` trước switch nếu đầu vào có thể null.

### Lỗi 7. Dùng cú pháp pattern matching của Java mới hơn cho Java 17 mặc định

```java
// Ví dụ kiểu cú pháp không phải phần ổn định mặc định của Java 17:
// return switch (obj) {
//     case String s -> s.length();
//     case Integer i -> i;
//     default -> 0;
// };
```

Pattern matching for switch ở Java 17 là preview (JEP 406). Nếu dự án yêu cầu **Java 17 ổn định, không preview**, hãy dùng `instanceof` hoặc các selector và nhãn `case` được hỗ trợ ổn định.

### Lỗi 8. Nghĩ switch expression sẽ tự ép mọi nhánh về cùng kiểu đích

Java có các quy tắc suy luận/chuyển kiểu, nhưng không thể biến một `String` bất kỳ thành `int` chỉ vì biến đích có kiểu `int`. Khi các nhánh không thống nhất về kiểu, cần quyết định rõ mô hình dữ liệu trả về.

## 14. Bài tập thực hành

### Bài 1. Nhận diện loại switch

Xem đoạn mã:

```java
switch (level) {
    case 1 -> System.out.println("Basic");
    default -> System.out.println("Other");
}
```

**Câu hỏi:** Đây là statement hay expression? Có fall-through không?

**Đáp án:** Đây là **statement**, vì `switch` đứng độc lập và chỉ in thông báo. Không có fall-through vì dùng `case ->`.

### Bài 2. Viết lại từ statement sang expression

Cho:

```java
static String season(int month) {
    String result;
    switch (month) {
        case 12:
        case 1:
        case 2:
            result = "WINTER";
            break;
        case 3:
        case 4:
        case 5:
            result = "SPRING";
            break;
        case 6:
        case 7:
        case 8:
            result = "SUMMER";
            break;
        case 9:
        case 10:
        case 11:
            result = "AUTUMN";
            break;
        default:
            throw new IllegalArgumentException("Invalid month");
    }
    return result;
}
```

**Yêu cầu:** Viết lại để trả về switch expression và không sử dụng biến `result`.

**Một lời giải:**

```java
static String season(int month) {
    return switch (month) {
        case 12, 1, 2 -> "WINTER";
        case 3, 4, 5 -> "SPRING";
        case 6, 7, 8 -> "SUMMER";
        case 9, 10, 11 -> "AUTUMN";
        default -> throw new IllegalArgumentException("Invalid month");
    };
}
```

### Bài 3. Chọn đúng `yield`

```java
static int compute(int kind, int base) {
    return switch (kind) {
        case 1 -> base;
        case 2 -> {
            int extra = base / 2;
            // Điền một câu lệnh tại đây.
        }
        default -> 0;
    };
}
```

**Yêu cầu:** Khi `kind == 2`, trả giá trị `base + extra` từ switch expression.

**Đáp án:** Điền `yield base + extra;`. `break;` không cung cấp giá trị.

### Bài 4. Phân biệt yêu cầu exhaustive

```java
enum Direction { NORTH, SOUTH, EAST, WEST }

static String directionName(Direction direction) {
    return switch (direction) {
        case NORTH -> "Bắc";
        case SOUTH -> "Nam";
        case EAST -> "Đông";
        case WEST -> "Tây";
    };
}
```

**Câu hỏi:** Tại sao expression này hợp lệ dù không có `default`?

**Đáp án:** Vì đã bao phủ mọi hằng của `Direction` tại thời điểm biên dịch. Java có thể chứng minh switch expression exhaustive với enum này.

### Bài 5. Tìm kết quả có fall-through

```java
int x = 2;

switch (x) {
    case 1:
        System.out.print("A");
    case 2:
        System.out.print("B");
    case 3:
        System.out.print("C");
        break;
    default:
        System.out.print("D");
}
```

**Câu hỏi:** Kết quả in ra là gì?

**Đáp án:** `BC`. Chương trình bắt đầu ở `case 2`, chạy tiếp `case 3` rồi gặp `break`.

### Bài 6. Chọn cấu trúc cho tình huống thực tế

Một hàm nhận loại gói dịch vụ và cần **trả về mức phí**. Một hàm khác nhận sự kiện và cần **gọi đúng handler, cập nhật trạng thái, ghi log**.

**Gợi ý:** Hàm chọn phí thường phù hợp với switch expression. Hàm điều phối tác vụ thường phù hợp với switch statement, có thể dùng `->` để loại fall-through.

### Bài 7. Vì sao ví dụ không biên dịch?

```java
static String classify(int value) {
    return switch (value) {
        case 1 -> "ONE";
        case 2 -> "TWO";
    };
}
```

**Đáp án:** Switch expression không exhaustive vì `value` có thể là bất kỳ `int` nào khác 1 hoặc 2. Cần bổ sung `default` để tạo giá trị hoặc ném ngoại lệ.

## 15. Ghi nhớ và tài liệu tham khảo

**Phân biệt theo vai trò của `switch`:**

1. `switch statement` thực thi câu lệnh; nó có thể viết bằng `case:` hoặc `case ->`.
2. `switch expression` tạo ra giá trị; nó cũng có thể dùng hai dạng case, nhưng mỗi đường hoàn thành bình thường phải tạo ra kết quả.
3. `case ->` ngăn fall-through cho **cả hai** dạng `switch`.
4. `break` thoát switch statement; `yield` cung cấp giá trị cho switch expression; `return` trả khỏi phương thức.
5. Switch expression phải exhaustive. Với `int` hoặc `String` thường cần `default`; với `enum` có thể liệt kê đầy đủ các hằng.
6. Switch expression ổn định từ **Java 14**, được Java 17 kế thừa. Pattern matching for switch vẫn là **preview trong Java 17**.

### Tài liệu chính thức

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): thiết kế và quá trình chuẩn hóa switch expression trong Java 14.
- [Oracle Java 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html): hướng dẫn phân biệt switch statement và switch expression, cú pháp `->`, `yield` và exhaustiveness.
- [Java Language Specification 17 — `14.11 The switch Statement`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): quy tắc switch statement.
- [Java Language Specification 17 — `15.28 switch Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): quy tắc switch expression, kiểu kết quả và bao phủ trường hợp.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): tính năng preview trong Java 17, cần phân biệt với switch expression đã ổn định.

**Kết luận thực hành:** Nếu mục đích của `switch` là **tạo một giá trị**, hãy cân nhắc switch expression. Nếu mục đích là **thực hiện hành động**, dùng switch statement. Dấu `->` hữu ích ở cả hai; điểm quan trọng nhất là cách kết thúc nhánh và cách Java bảo đảm kết quả phù hợp với nơi sử dụng.
