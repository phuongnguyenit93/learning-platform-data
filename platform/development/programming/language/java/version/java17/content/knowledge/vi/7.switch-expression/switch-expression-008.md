# Null và các kiểu selector được hỗ trợ chính thức trên Java 17

## 1. Phạm vi bài học: chọn nhánh bằng `switch expression` trên Java 17

`switch expression` là biểu thức lựa chọn một nhánh để **tạo ra giá trị**. Nó được chuẩn hóa từ Java 14 và có thể sử dụng trực tiếp trên Java 17, không cần bật tính năng preview. Tuy nhiên, không phải mọi kiểu dữ liệu đều có thể đặt sau từ khóa `switch`, và một selector có giá trị `null` có hành vi đặc biệt cần hiểu rõ.

Ví dụ:

~~~java
int httpStatus = 201;

String result = switch (httpStatus) {
    case 200, 201 -> "Thành công";
    case 400 -> "Yêu cầu không hợp lệ";
    case 404 -> "Không tìm thấy";
    default -> "Trạng thái khác";
};

System.out.println(result); // Thành công
~~~

Trong `switch (httpStatus)`:

- **Selector expression** là biểu thức `httpStatus`, nơi chương trình lấy giá trị để chọn nhánh.
- **Selector type** là kiểu tĩnh của biểu thức đó, ở đây là `int`.
- **Case labels** là các nhãn `200`, `201`, `400`, `404` và `default`.
- **Result** là giá trị do nhánh đã được chọn tạo ra, ở đây là `String`.

Chủ đề bài này chỉ tập trung vào hai câu hỏi:

1. Kiểu nào được sử dụng làm **selector** trong một `switch expression` **ổn định trên Java 17**?
2. Điều gì xảy ra khi **selector có giá trị `null`**, và nên thiết kế code ra sao?

Các quy tắc selector và `null` cơ bản cũng áp dụng với `switch statement` thông thường trên Java 17. Khác biệt chính là **switch expression phải tạo ra giá trị và có yêu cầu về tính bao phủ nhánh**, trong khi switch statement thường được dùng để thực thi các hành động.

> **Ranh giới phiên bản:** Java 17 có preview của *pattern matching for switch*, trong đó có các khả năng xử lý `null` theo cú pháp mới. Bài này dùng **tập tính năng Java 17 đã chuẩn hóa**, không yêu cầu `--enable-preview` và không dựa vào cú pháp preview làm ví dụ chính.

## 2. Bảng các kiểu selector được Java 17 hỗ trợ chính thức

Với switch theo các quy tắc ổn định của Java 17, selector phải có một trong các kiểu sau:

| Nhóm | Kiểu selector hợp lệ | Ví dụ biểu thức | Có thể chứa `null`? |
|---|---|---|---|
| Primitive số nguyên nhỏ | `byte` | `byte level = 2;` | Không |
| Primitive số nguyên nhỏ | `short` | `short code = 100;` | Không |
| Primitive ký tự | `char` | `char grade = 'A';` | Không |
| Primitive số nguyên | `int` | `int status = 200;` | Không |
| Wrapper tương ứng | `Byte` | `Byte level = 2;` | **Có** |
| Wrapper tương ứng | `Short` | `Short code = 100;` | **Có** |
| Wrapper tương ứng | `Character` | `Character grade = 'A';` | **Có** |
| Wrapper tương ứng | `Integer` | `Integer status = 200;` | **Có** |
| Chuỗi | `String` | `String command = "START";` | **Có** |
| Kiểu liệt kê | Một kiểu `enum` cụ thể | `Mode mode = Mode.AUTO;` | **Có** |

Đây là **danh sách các kiểu selector thuộc Java 17 ổn định**. Việc đối tượng tại runtime trông giống một số nguyên hay chuỗi **không đủ**; trình biên dịch phải thấy kiểu tĩnh của selector là kiểu được cho phép.

Ví dụ, `Integer` được chấp nhận nhưng `Number` không được chấp nhận, dù biến `Number` có thể đang chứa một đối tượng `Integer`.

### 2.1. Các kiểu không được hỗ trợ như selector trong Java 17 ổn định

| Kiểu / biểu thức | Có thể làm selector trực tiếp? | Lý do |
|---|---|---|
| `long`, `Long` | **Không** | Không thuộc các kiểu selector được Java 17 ổn định cho phép |
| `float`, `Float` | **Không** | Số thực không phải selector chuẩn của switch Java 17 |
| `double`, `Double` | **Không** | Tương tự |
| `boolean`, `Boolean` | **Không** | Không thuộc tập kiểu cho phép |
| `Object` | **Không** | Kiểu tĩnh quá rộng |
| `Number` | **Không** | Không phải một trong bốn wrapper được liệt kê |
| `CharSequence` | **Không** | Chỉ `String` được phép trong nhóm chuỗi |
| `BigInteger`, `BigDecimal` | **Không** | Không có hỗ trợ selector trực tiếp |
| Class/record tùy ý | **Không** | Không phải enum hoặc kiểu selector được phép |
| Array hoặc `List` | **Không** | Không thuộc tập kiểu selector |
| `null` như biểu thức selector không có kiểu phù hợp | **Không** | Không tạo được một selector hợp lệ; với selector tham chiếu hợp lệ có giá trị null thì xem phần 4 |

Ví dụ **không hợp lệ**:

~~~java
long code = 200L;
// String text = switch (code) {
//     case 200 -> "OK";
//     default -> "OTHER";
// };
// Không biên dịch trên Java 17: selector long không được hỗ trợ.
~~~

~~~java
Object command = "START";
// String action = switch (command) {
//     case "START" -> "Run";
//     default -> "Unknown";
// };
// Không biên dịch: kiểu tĩnh của command là Object.
~~~

~~~java
Number number = Integer.valueOf(1);
// String category = switch (number) {
//     case 1 -> "ONE";
//     default -> "OTHER";
// };
// Không biên dịch: Number không phải Integer.
~~~

Từ khóa `var` không phải một kiểu selector mới. Nếu viết `var status = 200;`, compiler suy ra `int` và dùng được trong switch. Nếu viết `var item = (Object) "START";`, compiler suy ra `Object`, nên không dùng được dù giá trị thực là chuỗi.

## 3. Switch expression với từng nhóm selector hợp lệ

### 3.1. `int` và các kiểu nguyên thủy `byte`, `short`, `char`

Ví dụ với `int`:

~~~java
static String classifyHttpStatus(int status) {
    return switch (status) {
        case 200, 201, 204 -> "SUCCESS";
        case 400, 422 -> "CLIENT_ERROR";
        case 500, 503 -> "SERVER_ERROR";
        default -> "OTHER";
    };
}
~~~

Ví dụ với `byte`:

~~~java
static String levelName(byte level) {
    return switch (level) {
        case 1 -> "LOW";
        case 2 -> "MEDIUM";
        case 3 -> "HIGH";
        default -> "UNSUPPORTED";
    };
}
~~~

Ví dụ với `short`:

~~~java
static String protocolVersion(short version) {
    return switch (version) {
        case 1 -> "V1";
        case 2 -> "V2";
        default -> "UNKNOWN";
    };
}
~~~

Ví dụ với `char`:

~~~java
static String letterGrade(char grade) {
    return switch (grade) {
        case 'A' -> "Xuất sắc";
        case 'B' -> "Tốt";
        case 'C' -> "Đạt";
        default -> "Cần xem lại";
    };
}
~~~

Selector kiểu nguyên thủy **không thể có giá trị `null`**, nên không gặp lỗi NPE do chính selector là null. Tuy nhiên vẫn phải xử lý mã không hợp lệ hoặc ngoài miền dữ liệu bằng `default` hoặc cơ chế xác thực phù hợp.

Giá trị của case phải thỏa các quy tắc về **hằng compile-time** và tương thích với selector. Với selector `byte` hoặc `short`, có thể dùng hằng `int` nằm trong phạm vi biểu diễn cho phép, nhưng không thể dùng một số vượt phạm vi chỉ vì JVM lưu nó bằng kiểu số nguyên rộng hơn.

~~~java
byte value = 1;
String label = switch (value) {
    case 1 -> "ONE";
    default -> "OTHER";
};

// Không hợp lệ nếu thêm nhãn case 200 cho selector byte:
// case 200 -> "TWO_HUNDRED";
// 200 nằm ngoài phạm vi của byte (-128 đến 127).
~~~

Những nhãn trùng nhau về giá trị sau các quy tắc chuyển đổi hợp lệ cũng không được phép xuất hiện hai lần.

### 3.2. Wrapper: `Byte`, `Short`, `Character`, `Integer`

Java 17 cho phép dùng wrapper tương ứng với bốn kiểu nguyên thủy trên:

~~~java
Integer status = Integer.valueOf(200);

String response = switch (status) {
    case 200 -> "OK";
    case 404 -> "NOT_FOUND";
    default -> "OTHER";
};
~~~

Wrapper tiện lợi khi dữ liệu từ một API, database hoặc cấu trúc chứa đối tượng có thể vắng mặt. Nhưng ở đây xuất hiện ranh giới quan trọng: **wrapper có thể là `null`**.

~~~java
Integer status = null;

// Biên dịch được, nhưng khi thực thi switch sẽ ném
// NullPointerException trước khi chọn nhánh:
//
// String result = switch (status) {
//     case 200 -> "OK";
//     default -> "OTHER";
// };
~~~

Về mặt triển khai, selector wrapper được xử lý theo các quy tắc liên quan đến việc lấy giá trị số/ký tự, có thể bao gồm unboxing. Một tham chiếu wrapper null không thể cung cấp giá trị để đối chiếu nhãn `case`, nên switch ném `NullPointerException`.

Điều này tương tự với `Byte`, `Short` và `Character`, không chỉ `Integer`.

### 3.3. `String` selector

`String` cho phép ánh xạ những mã chữ có tập giá trị rõ:

~~~java
static String actionFor(String command) {
    return switch (command) {
        case "CREATE" -> "Tạo mới";
        case "UPDATE" -> "Cập nhật";
        case "DELETE" -> "Xóa";
        default -> "Lệnh không được hỗ trợ";
    };
}
~~~

Với selector là `String`:

- So khớp nhãn theo nội dung chuỗi, **phân biệt chữ hoa/chữ thường**.
- `"CREATE"` và `"create"` là hai giá trị khác nhau.
- `" CREATE "` có khoảng trắng khác `"CREATE"`.
- `default` xử lý chuỗi không trùng bất kỳ case nào, nhưng **không xử lý được selector `null`**.
- `case` là các giá trị hằng phù hợp; switch Java 17 ổn định **không hỗ trợ** regex, pattern guard hoặc kiểm tra `startsWith` trực tiếp như một case.

Nếu giao thức nghiệp vụ cho phép bỏ qua khoảng trắng và chữ hoa/chữ thường, hãy **chuẩn hóa trước khi switch**:

~~~java
import java.util.Locale;

static String normalizedAction(String rawCommand) {
    if (rawCommand == null) {
        return "Thiếu lệnh";
    }

    String command = rawCommand.strip().toUpperCase(Locale.ROOT);

    return switch (command) {
        case "CREATE" -> "Tạo mới";
        case "UPDATE" -> "Cập nhật";
        case "DELETE" -> "Xóa";
        default -> "Lệnh không được hỗ trợ";
    };
}
~~~

Sử dụng `Locale.ROOT` giúp việc đổi chữ hoa/chữ thường cho **mã kỹ thuật** không phụ thuộc vào locale mặc định của môi trường. Tuy nhiên, chỉ chuẩn hóa như vậy khi hợp đồng đầu vào cho phép; mã định danh hoặc token phân biệt chính xác ký tự có thể không được phép thay đổi.

### 3.4. `enum` selector

Enum là lựa chọn tốt khi miền đã được biểu diễn bằng một tập hằng được định nghĩa trong mã Java:

~~~java
enum PaymentStatus {
    NEW, PAID, CANCELLED
}

static String paymentLabel(PaymentStatus status) {
    return switch (status) {
        case NEW -> "Chưa thanh toán";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Vì đã liệt kê **tất cả hằng enum** trong switch expression, ví dụ không cần `default`. Trình biên dịch Java 17 có thể xác nhận tính bao phủ của các trường hợp enum được biết ở thời điểm biên dịch.

Trong Java 17 ổn định, nhãn của enum ở ví dụ là tên hằng **không có tiền tố tên enum**:

~~~java
case NEW -> "Chưa thanh toán";
~~~

Không viết `case PaymentStatus.NEW` để thay thế cho cú pháp trên trong switch enum chuẩn của Java 17.

Một enum là **kiểu tham chiếu**, nên biến `PaymentStatus status` vẫn có thể là `null`:

~~~java
PaymentStatus status = null;

// NullPointerException khi đánh giá switch:
// String label = switch (status) {
//     case NEW -> "New";
//     case PAID -> "Paid";
//     case CANCELLED -> "Cancelled";
// };
~~~

Việc liệt kê hết các hằng enum chỉ bảo đảm các **giá trị enum hợp lệ khác null** đều có nhánh xử lý. Nó không có nghĩa có thêm một nhánh ngầm định dành cho `null`.

Nếu một enum được thay đổi trong phiên bản thư viện khác với thời điểm biên dịch, cần xem xét lại logic và triển khai đồng bộ. Khi cập nhật mã nguồn để thêm enum constant, các switch expression liệt kê hết nhánh cũ cần được cập nhật theo quy tắc bao phủ.

## 4. `null` selector trên Java 17: hành vi chính thức là gì?

### 4.1. Selector tham chiếu có giá trị null làm switch ném `NullPointerException`

Xem ví dụ:

~~~java
String command = null;

String result = switch (command) {
    case "START" -> "RUNNING";
    case "STOP" -> "STOPPED";
    default -> "UNKNOWN";
};
~~~

Đoạn mã **biên dịch được** vì selector có kiểu `String` hợp lệ. Nhưng khi thực thi, `command` là null nên việc chọn nhánh ném `NullPointerException`.

Quy tắc tương tự áp dụng cho những selector kiểu tham chiếu khác được Java 17 hỗ trợ:

| Selector | Nếu giá trị `null` | `default` có nhận null? |
|---|---|---|
| `String` | `NullPointerException` | Không |
| `Byte` | `NullPointerException` | Không |
| `Short` | `NullPointerException` | Không |
| `Character` | `NullPointerException` | Không |
| `Integer` | `NullPointerException` | Không |
| Một `enum` | `NullPointerException` | Không |

Giá trị null không phải một chuỗi khác lạ, không phải mã số ngoài phạm vi và cũng không phải một enum constant không được khai báo. Nó là **sự vắng mặt của tham chiếu** trước khi bộ chọn nhánh có giá trị hợp lệ.

### 4.2. Tại sao `default` không chặn được null?

`default` là nhánh dành cho selector hợp lệ **không khớp với những nhãn case khác**. Trong Java 17 ổn định, khi selector tham chiếu là null, switch không chuyển null sang `default`; nó ném exception.

Ví dụ:

~~~java
static String mapCode(Integer code) {
    return switch (code) {
        case 1 -> "ACTIVE";
        case 2 -> "INACTIVE";
        default -> "UNKNOWN";
    };
}
~~~

Kết quả theo đầu vào:

| Lời gọi | Kết quả |
|---|---|
| `mapCode(1)` | `"ACTIVE"` |
| `mapCode(2)` | `"INACTIVE"` |
| `mapCode(99)` | `"UNKNOWN"` |
| `mapCode(null)` | Ném `NullPointerException` |

Việc có `default` không thay đổi dòng cuối.

### 4.3. `case null` có dùng được không?

Một điểm rất dễ nhầm giữa các phiên bản Java:

~~~java
// KHÔNG dùng như cú pháp Java 17 ổn định:
//
// String result = switch (command) {
//     case null -> "MISSING";
//     case "START" -> "RUNNING";
//     default -> "UNKNOWN";
// };
~~~

Trong **Java 17**, khả năng khớp `null` bằng `case null` thuộc phần **preview của pattern matching for switch (JEP 406)**; không phải phần ngôn ngữ ổn định được sử dụng mặc định. Không dùng cách đó trong bài Java 17 yêu cầu code chuẩn, không bật preview.

`case null` được đưa vào quy tắc switch ổn định về sau cùng với pattern matching for switch ở **Java 21 (JEP 441)**. Vì thế, một đoạn ví dụ hợp lệ trên Java 21 có thể **không** biên dịch theo `--release 17`.

Không nên bật cờ preview chỉ để thay thế một kiểm tra `if (value == null)` đơn giản trong code cần tương thích Java 17.

### 4.4. Giá trị trả về `null` khác với selector `null`

Hai tình huống sau **khác nhau hoàn toàn**:

**Tình huống A: selector null — lỗi khi chọn nhánh.**

~~~java
String command = null;
// switch (command) { ... } -> NullPointerException
~~~

**Tình huống B: selector hợp lệ, nhánh chủ động trả về null.**

~~~java
static String optionalCode(int code) {
    return switch (code) {
        case 0 -> null;
        case 1 -> "READY";
        default -> "UNKNOWN";
    };
}

String value = optionalCode(0); // null
~~~

Tình huống B **hợp lệ trên Java 17** vì selector `code` là `int` và switch expression có thể tạo ra kết quả tham chiếu null khi kiểu kết quả phù hợp. Cần quyết định xem API của bạn có muốn trả `null` không; một `Optional<String>`, kiểu kết quả riêng hoặc giá trị trạng thái rõ nghĩa có thể dễ hiểu hơn trong những trường hợp cần biểu diễn sự vắng mặt.

Nói chính xác: **quy tắc switch selector null** và **quy tắc giá trị mà switch expression trả về** là hai vấn đề độc lập.

## 5. Các cách xử lý null trước switch trong Java 17

### 5.1. Null là đầu vào không hợp lệ: từ chối ngay tại ranh giới

Nếu nghiệp vụ yêu cầu luôn có trạng thái:

~~~java
import java.util.Objects;

static String labelRequired(String status) {
    Objects.requireNonNull(status, "status");

    return switch (status) {
        case "OPEN" -> "Đang mở";
        case "CLOSED" -> "Đã đóng";
        default -> "Không được hỗ trợ";
    };
}
~~~

`Objects.requireNonNull(status, "status")` ném `NullPointerException` với thông báo rõ ràng hơn về tham số vi phạm hợp đồng. Đây là phương án phù hợp cho các **API nội bộ có tiền điều kiện không null**, miễn là contract đã nêu rõ điều đó.

Không dùng nó khi null là trạng thái nghiệp vụ hợp lệ và cần trả về thông tin cho người dùng.

### 5.2. Null có ý nghĩa nghiệp vụ: xử lý bằng `if` trước switch

Ví dụ một API cho phép người dùng chưa chọn bộ lọc:

~~~java
static String filterDescription(String filter) {
    if (filter == null) {
        return "Chưa chọn bộ lọc";
    }

    return switch (filter) {
        case "TODAY" -> "Hôm nay";
        case "THIS_WEEK" -> "Tuần này";
        case "ALL" -> "Tất cả";
        default -> "Bộ lọc không hợp lệ";
    };
}
~~~

Cách đọc mã rất rõ: một nhánh kiểm tra **vắng mặt**, switch xử lý các **giá trị hợp lệ đã có**. Nếu `filter = ""` hoặc `filter = "UNKNOWN"`, switch sẽ tới `default`; đó là trường hợp khác với null.

### 5.3. Đầu vào nullable cần chuẩn hóa

Ví dụ với mã trạng thái người dùng nhập qua form:

~~~java
import java.util.Locale;

static String normalizeAndDescribe(String input) {
    if (input == null || input.isBlank()) {
        return "Thiếu trạng thái";
    }

    String status = input.strip().toUpperCase(Locale.ROOT);

    return switch (status) {
        case "ACTIVE" -> "Đang hoạt động";
        case "SUSPENDED" -> "Đã tạm khóa";
        case "DELETED" -> "Đã xóa";
        default -> "Trạng thái không nhận diện được";
    };
}
~~~

Trong ví dụ này:

1. `null` và chuỗi chỉ gồm khoảng trắng được coi là dữ liệu **thiếu**.
2. Chuỗi hợp lệ được chuẩn hóa dựa trên hợp đồng đầu vào.
3. Switch đối chiếu các mã thống nhất.
4. `default` bắt giá trị có nội dung nhưng không được hỗ trợ.

Không phải domain nào cũng cho phép chuẩn hóa như vậy. Ví dụ mã định danh phân biệt hoa/thường hoặc chữ ký điện tử không nên biến đổi trước khi xác thực.

### 5.4. Null thay bằng mặc định: chỉ khi nghiệp vụ cho phép

Java 9 đã có `Objects.requireNonNullElse`, dùng được trên Java 17:

~~~java
import java.util.Objects;

static String languageLabel(String preferredLanguage) {
    String language = Objects.requireNonNullElse(
            preferredLanguage, "en"
    );

    return switch (language) {
        case "vi" -> "Tiếng Việt";
        case "en" -> "English";
        default -> "Khác";
    };
}
~~~

Cách này chỉ hợp lý nếu **thiếu lựa chọn đồng nghĩa dùng `en` mặc định** theo yêu cầu sản phẩm. Đừng tự động đổi null thành số 0, chuỗi rỗng hoặc một enum constant khi việc đó có thể che giấu lỗi đầu vào.

### 5.5. Wrapper nullable: kiểm tra trước khi unbox

~~~java
static String ratingText(Integer rating) {
    if (rating == null) {
        return "Chưa đánh giá";
    }

    return switch (rating) {
        case 1 -> "Rất thấp";
        case 2 -> "Thấp";
        case 3 -> "Trung bình";
        case 4 -> "Tốt";
        case 5 -> "Rất tốt";
        default -> "Điểm không hợp lệ";
    };
}
~~~

Đây là dạng rất phổ biến khi làm việc với dữ liệu từ database hoặc JSON: kiểu Java là `Integer` vì giá trị có thể thiếu, nhưng phép phân loại chỉ có ý nghĩa với số nguyên đã tồn tại.

## 6. Khi nào nên chọn `enum` thay vì `String` selector?

Trong mô hình miền, `String` thường đến từ API bên ngoài, request, file hoặc dữ liệu tích hợp. Nếu trạng thái bên trong có tập giá trị hữu hạn, việc **parse sang enum tại ranh giới hệ thống** có thể giúp code rõ ràng hơn.

~~~java
enum JobState {
    QUEUED,
    RUNNING,
    COMPLETED,
    FAILED
}

static String jobMessage(JobState state) {
    return switch (state) {
        case QUEUED -> "Đang chờ";
        case RUNNING -> "Đang xử lý";
        case COMPLETED -> "Đã xong";
        case FAILED -> "Thất bại";
    };
}
~~~

Điểm mạnh của enum:

- Compiler biết tập hằng tại thời điểm biên dịch.
- Có thể viết switch expression đầy đủ các nhánh mà không cần `default`.
- Tránh lỗi gõ sai chuỗi ở những nơi code đã sử dụng enum.
- Hạn chế những trạng thái ngoài hợp đồng xuất hiện sâu trong tầng xử lý.

Nhưng enum vẫn là **tham chiếu có thể null**. Và việc chuyển chuỗi ngoài hệ thống sang enum vẫn cần xác thực:

~~~java
import java.util.Locale;

static JobState parseJobState(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Thiếu trạng thái công việc");
    }

    String normalized = raw.strip().toUpperCase(Locale.ROOT);
    try {
        return JobState.valueOf(normalized);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Trạng thái không hợp lệ: " + raw, ex
        );
    }
}
~~~

Ở lớp API, bạn có thể chuyển ngoại lệ sang phản hồi phù hợp với giao thức. Không nên mặc định rằng mọi giá trị String từ bên ngoài đều là enum constant hợp lệ.

**Lưu ý khi phát triển enum:** Tránh thêm `default` chỉ để làm code dễ biên dịch nếu mục tiêu là yêu cầu cập nhật logic mỗi khi thêm enum constant mới. Với switch expression trên enum, liệt kê các hằng có thể giúp compiler phát hiện trường hợp chưa được xử lý khi biên dịch lại mã nguồn.

## 7. Switch expression phải bao phủ các trường hợp lựa chọn

### 7.1. Sự khác nhau giữa `switch expression` và `switch statement`

Switch statement có thể chỉ thực thi một hành động và kết thúc:

~~~java
static void printStatus(int status) {
    switch (status) {
        case 200 -> System.out.println("OK");
        case 404 -> System.out.println("Not found");
    }
}
~~~

Ví dụ trên hợp lệ: nếu `status` không khớp, statement có thể không làm gì.

Switch expression cần tạo ra giá trị:

~~~java
static String statusText(int status) {
    return switch (status) {
        case 200 -> "OK";
        case 404 -> "Not found";
        default -> "Other";
    };
}
~~~

Với những selector số nguyên hoặc String của Java 17, thông thường phải có `default` để bao phủ các giá trị khác.

~~~java
// KHÔNG HỢP LỆ: switch expression chưa bao phủ mọi int có thể có.
//
// String text = switch (status) {
//     case 200 -> "OK";
//     case 404 -> "Not found";
// };
~~~

Với enum, một switch expression có thể đủ nhánh nếu liệt kê **mọi enum constant**, như ví dụ `PaymentStatus` ở trên. Dù vậy, quy tắc này vẫn **không làm `null` trở thành nhánh hợp lệ** trên Java 17.

### 7.2. Một nhánh có thể tạo giá trị bằng biểu thức, `yield` hoặc `throw`

~~~java
static String responseMessage(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 400 -> {
            String description = "Bad request";
            yield "Lỗi client: " + description;
        }
        case 500 -> throw new IllegalStateException("Lỗi server");
        default -> "Không xác định";
    };
}
~~~

- `case 200 -> "OK"`: trực tiếp tạo giá trị.
- `case 400 -> { ... yield ...; }`: nhiều lệnh trong nhánh, `yield` tạo giá trị của switch expression.
- `case 500 -> throw ...`: nhánh ném exception, không tạo giá trị bình thường.
- `default`: bao phủ các mã khác 200/400/500.

`yield` dùng trong switch expression không giống `return`: `return` thoát khỏi method, còn `yield` chuyển giá trị về cho biểu thức switch.

Quy tắc cú pháp này độc lập với việc selector tham chiếu có thể null. Nếu selector null, không có nhánh nào được chọn để chạy `yield` hay `throw` bên trong.

### 7.3. Selector được đánh giá trước khi chọn nhánh

Selector là một **biểu thức**, không bắt buộc là tên biến:

~~~java
static int readStatus() {
    System.out.println("Đọc trạng thái");
    return 200;
}

String text = switch (readStatus()) {
    case 200 -> "OK";
    default -> "OTHER";
};
~~~

Biểu thức `readStatus()` được đánh giá để lấy giá trị selector, sau đó switch mới chọn nhánh. Với biểu thức tham chiếu nullable, một kết quả null sẽ dẫn tới `NullPointerException` theo quy tắc đã trình bày.

Do đó, nên tránh nhúng các thao tác có side effect phức tạp vào selector. Đọc giá trị một lần, xác thực rồi mới switch thường giúp code dễ hiểu và dễ ghi log hơn.

## 8. Ví dụ Java 17 hoàn chỉnh: số, wrapper nullable, String nullable và enum

Lưu toàn bộ mã sau vào **SwitchSelectorJava17Demo.java**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class SwitchSelectorJava17Demo {

    enum JobState {
        QUEUED, RUNNING, COMPLETED
    }

    static String fromInt(int statusCode) {
        return switch (statusCode) {
            case 200, 201 -> "SUCCESS";
            case 400 -> "BAD_REQUEST";
            case 404 -> "NOT_FOUND";
            default -> "OTHER";
        };
    }

    static String fromNullableInteger(Integer statusCode) {
        if (statusCode == null) {
            return "NOT_PROVIDED";
        }
        return fromInt(statusCode);
    }

    static String fromNullableString(String rawCommand) {
        if (rawCommand == null || rawCommand.isBlank()) {
            return "MISSING_COMMAND";
        }

        String command =
                rawCommand.strip().toUpperCase(Locale.ROOT);

        return switch (command) {
            case "START" -> "RUN";
            case "STOP" -> "HALT";
            case "RETRY" -> "TRY_AGAIN";
            default -> "UNSUPPORTED_COMMAND";
        };
    }

    static String fromEnum(JobState state) {
        Objects.requireNonNull(state, "state");

        return switch (state) {
            case QUEUED -> "WAITING";
            case RUNNING -> "WORKING";
            case COMPLETED -> "DONE";
        };
    }

    static String fromChar(char grade) {
        return switch (grade) {
            case 'A' -> "EXCELLENT";
            case 'B' -> "GOOD";
            default -> "OTHER_GRADE";
        };
    }

    public static void main(String[] args) {
        System.out.println(fromInt(200));
        System.out.println(fromNullableInteger(null));
        System.out.println(fromNullableString(" start "));
        System.out.println(fromNullableString(null));
        System.out.println(fromEnum(JobState.RUNNING));
        System.out.println(fromChar('A'));
    }
}
~~~

Biên dịch và chạy trên **JDK 17**, không bật preview:

~~~shell
java -version
javac --release 17 SwitchSelectorJava17Demo.java
java SwitchSelectorJava17Demo
~~~

Kết quả:

~~~text
SUCCESS
NOT_PROVIDED
RUN
MISSING_COMMAND
WORKING
EXCELLENT
~~~

Điểm quan trọng trong thiết kế:

1. `fromInt` dùng primitive `int`: selector không thể null.
2. `fromNullableInteger` xử lý null **trước** khi chuyển sang logic chọn nhánh số.
3. `fromNullableString` tách riêng đầu vào thiếu và mã lệnh không được hỗ trợ.
4. `fromEnum` xác nhận tiền điều kiện non-null, sau đó liệt kê tất cả enum constant.
5. `fromChar` minh họa `char` là selector hợp lệ dù không phải số nguyên theo cách nhìn thông thường.
6. Tất cả case dùng cú pháp switch được chuẩn hóa ở hoặc trước Java 17, không có `case null`, type pattern trong `switch` hay guard preview.

## 9. Các ví dụ dễ nhầm về kiểu tĩnh và chuyển đổi

### 9.1. `Object` chứa `String` vẫn không phải `String` selector

~~~java
Object raw = "READY";

// KHÔNG HỢP LỆ:
// String result = switch (raw) {
//     case "READY" -> "OK";
//     default -> "OTHER";
// };
~~~

Nếu đầu vào là `Object` do một API tổng quát, cần xác nhận kiểu trước:

~~~java
static String classifyObject(Object raw) {
    if (!(raw instanceof String text)) {
        return "Giá trị không phải chuỗi";
    }

    return switch (text) {
        case "READY" -> "OK";
        default -> "OTHER";
    };
}
~~~

`instanceof String text` là **pattern matching for instanceof**, đã ổn định trong Java 16 và được hỗ trợ trên Java 17. Nó khác với việc dùng type pattern như `case String text` **bên trong switch**, vốn chưa ổn định ở Java 17.

Nếu `raw` bằng null, biểu thức `raw instanceof String text` trả `false`, nên ví dụ có xử lý riêng cho dữ liệu không phải chuỗi. Không cần switch trực tiếp trên `Object`.

### 9.2. `Number` và `Integer` không tương đương với selector

~~~java
Number number = Integer.valueOf(3);

// Không thể switch trực tiếp trên Number trong Java 17.
// String name = switch (number) { ... };
~~~

Nếu cần giá trị số nguyên kiểu `Integer`:

~~~java
static String classifyNumber(Number number) {
    if (!(number instanceof Integer integer)) {
        return "Cần Integer";
    }
    return switch (integer) {
        case 1 -> "ONE";
        case 2 -> "TWO";
        default -> "OTHER";
    };
}
~~~

Đừng tự đổi mọi `Number` thành `int` bằng `intValue()` mà không xác minh miền: ví dụ số thực có thể bị mất phần thập phân, `long` có thể bị thu hẹp ngoài phạm vi và giá trị null gây lỗi. Nếu nghiệp vụ yêu cầu chính xác một loại dữ liệu, hãy diễn đạt điều đó bằng kiểu phù hợp hoặc kiểm tra giá trị có chủ đích.

### 9.3. `long` không được hỗ trợ trực tiếp

~~~java
long id = 2_500_000_000L;

// Không hợp lệ trên Java 17:
// String label = switch (id) {
//     case 2500000000L -> "LARGE";
//     default -> "OTHER";
// };
~~~

Nếu miền thực sự có giá trị lớn hơn `Integer.MAX_VALUE`, dùng `if`/`else`, `Map<Long, ...>` hoặc cách thiết kế khác. **Không ép `(int)` cho mọi `long` chỉ để dùng switch**, vì có thể mất dữ liệu.

Nếu miền bảo đảm luôn vừa `int` và việc ép kiểu cần được kiểm soát, `Math.toIntExact(longValue)` có thể phát hiện trường hợp ngoài phạm vi bằng exception; tuy nhiên vẫn nên cân nhắc xem cần switch hay không.

### 9.4. `boolean` không phải selector Java 17

~~~java
boolean enabled = true;

// Không hợp lệ:
// String state = switch (enabled) {
//     case true -> "ON";
//     case false -> "OFF";
// };
~~~

Với boolean, toán tử điều kiện thường rõ hơn:

~~~java
String state = enabled ? "ON" : "OFF";
~~~

Không cần mã hóa `true`/`false` thành `1`/`0` chỉ để dùng switch.

### 9.5. Kiểu của nhãn `case` phải phù hợp với selector

~~~java
int status = 200;

String result = switch (status) {
    case 200 -> "OK";
    default -> "OTHER";
};

// Không hợp lệ:
// case "200" -> "OK";
// Chuỗi "200" không phải hằng số phù hợp với selector int.
~~~

Với selector `String`, nhãn case phải là giá trị hằng `String` phù hợp. Với enum, dùng các hằng thuộc đúng enum. Không thể dùng cú pháp pattern type trong switch Java 17 ổn định để trộn nhiều loại giá trị khác nhau.

## 10. Bài toán thực tế: phân biệt null, giá trị không xác định và giá trị hợp lệ

Giả sử một dịch vụ nhận trạng thái đơn hàng từ dữ liệu ngoài. Có ba nhóm cần tách:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| **Thiếu** | `null` hoặc chuỗi rỗng theo quy ước API | Không có dữ liệu trạng thái đáng tin |
| **Không hỗ trợ** | `"IN_TRANSIT_UNKNOWN"` | Có giá trị nhưng ứng dụng chưa nhận diện |
| **Hợp lệ** | `"NEW"`, `"PACKED"`, `"SHIPPED"` | Có thể xử lý theo nhánh nghiệp vụ |

Ví dụ:

~~~java
import java.util.Locale;

static String orderStatusMessage(String externalValue) {
    if (externalValue == null || externalValue.isBlank()) {
        return "Thiếu trạng thái đơn hàng";
    }

    String status = externalValue.strip()
            .toUpperCase(Locale.ROOT);

    return switch (status) {
        case "NEW" -> "Đơn hàng mới";
        case "PACKED" -> "Đã đóng gói";
        case "SHIPPED" -> "Đã giao vận";
        default -> "Không hỗ trợ trạng thái: " + status;
    };
}
~~~

Thiết kế này có lợi cho log, metric và phản hồi API vì **thiếu dữ liệu** khác với **giá trị mới hoặc lỗi định dạng**. Nếu bất ngờ gặp một trạng thái mới do hệ thống tích hợp bổ sung, nhánh `default` cho thấy rõ đây là trường hợp cần xem lại hợp đồng.

Với dữ liệu nội bộ đã được validate, chuyển trạng thái sang enum có thể giúp giảm số chuỗi magic. Tuy vậy, nếu trạng thái có thể mở rộng ngoài quyền kiểm soát của service, phải lên kế hoạch thích hợp cho những mã ngoài danh sách hiện tại.

## 11. Kế hoạch lựa chọn giải pháp phù hợp

Khi viết switch expression trong Java 17, có thể dùng quy trình suy nghĩ sau:

**Bước 1 — Xác định kiểu tĩnh.** Selector là `int`, wrapper, `String` hay enum? Nếu nó là `Object`, `Number`, `long` hoặc một kiểu không được hỗ trợ, cần thiết kế lại biểu thức lựa chọn.

**Bước 2 — Xác định có thể null hay không.** Primitive không null. `String`, enum và wrapper có thể null, kể cả khi dữ liệu nghiệp vụ “đáng lẽ” luôn tồn tại.

**Bước 3 — Quyết định ý nghĩa của null.** Đây là lỗi contract phải ném exception, trường hợp đầu vào vắng mặt cần phản hồi riêng, hay yêu cầu dùng giá trị mặc định?

**Bước 4 — Xử lý null trước switch.** Dùng `Objects.requireNonNull`, `if (value == null)` hoặc fallback có ý nghĩa nghiệp vụ.

**Bước 5 — Viết các case chính xác.** Case label phải tương thích kiểu selector, dùng hằng hoặc enum constant hợp lệ. Đảm bảo switch expression có đủ nhánh: thường dùng `default` cho String/số và có thể liệt kê mọi enum constant.

**Bước 6 — Chỉ dùng cú pháp ổn định của Java 17.** Không copy `case null`, `case String s`, `when` guard hay record pattern từ tài liệu Java mới hơn vào code bắt buộc chạy với `--release 17`.

**Bước 7 — Xem xét khả năng phát triển.** Mã trạng thái có thể tăng thêm không? Selector nên là enum hay String? Việc gặp mã lạ cần trả `UNKNOWN`, ném lỗi hay ghi nhận để xử lý sau?

### Bảng quyết định nhanh

| Ngữ cảnh | Cách dùng gợi ý trên Java 17 |
|---|---|
| Mã HTTP dạng `int` | `switch (status)` và `default` |
| Mã số nullable dạng `Integer` | Kiểm tra null trước, sau đó switch |
| Chuỗi lấy từ request | Kiểm tra null/rỗng, chuẩn hóa nếu contract cho phép, rồi switch |
| Enum trạng thái nội bộ | Kiểm tra/đảm bảo non-null, liệt kê các enum constant |
| Số `long` lớn | `if`/`else` hoặc cấu trúc ánh xạ phù hợp |
| Logic chỉ có true/false | `if` hoặc toán tử điều kiện |
| Đầu vào `Object` không biết kiểu | Xác minh kiểu, sau đó dùng giá trị đã được định kiểu phù hợp |
| Cần case kiểu `case String s`, `case null` | Cân nhắc yêu cầu JDK mới hơn; không coi là cú pháp Java 17 ổn định |

## 12. Các sai lầm thường gặp

### Sai lầm 1 — Nghĩ `default` cũng xử lý `null`

~~~java
String command = null;
// switch (command) có default vẫn gây NullPointerException.
~~~

**Đúng:** nếu null có thể xuất hiện, hãy xử lý trước switch.

### Sai lầm 2 — Dùng `case null` từ bài viết về Java mới hơn

~~~java
// case null -> "MISSING"; // preview trong Java 17
~~~

**Đúng:** Java 17 ổn định không dùng nhánh này. Xử lý `if (selector == null)` hoặc dùng hợp đồng non-null trước switch.

### Sai lầm 3 — Coi mọi số là selector được hỗ trợ

`int` được hỗ trợ, nhưng `long`, `float`, `double` không phải selector chính thức trong Java 17 ổn định. Các wrapper như `Long` và `Double` cũng không được hỗ trợ.

**Đúng:** kiểm tra kiểu được cho phép trước khi chọn cấu trúc switch.

### Sai lầm 4 — Dùng `Number`/ `Object` vì giá trị thực là `Integer`/`String`

Compiler dựa vào kiểu tĩnh của biểu thức. **Đúng:** định kiểu hoặc kiểm tra kiểu trước khi switch, thay vì nghĩ runtime sẽ tự chấp nhận `Object`.

### Sai lầm 5 — Quên wrapper và enum đều có thể null

`Integer` không có cùng ràng buộc null với `int`. Enum là kiểu tham chiếu, cũng có thể null. **Đúng:** nêu rõ contract và kiểm tra tại ranh giới phù hợp.

### Sai lầm 6 — Thêm `default` vào enum để che mọi trường hợp mới

Nếu đội muốn compiler yêu cầu cập nhật khi bổ sung enum constant, dùng switch expression bao phủ từng hằng enum có thể tốt hơn một `default` chung. **Đúng:** chọn chiến lược theo yêu cầu tương thích và xử lý trạng thái mới.

### Sai lầm 7 — Giả định chuỗi được so khớp linh hoạt

`"start"`, `"START"`, `" START "` là các giá trị khác nhau. **Đúng:** chuẩn hóa một cách có chủ đích, theo hợp đồng dữ liệu.

### Sai lầm 8 — Nhầm kết quả null với selector null

Một nhánh của switch expression có thể trả về null nếu kiểu kết quả cho phép; đó **không** phải `case null`. **Đúng:** phân biệt giá trị đưa vào switch với giá trị switch trả về.

## 13. Bài tập thực hành

### Bài 1 — Phân loại kiểu selector

Cho các biến:

~~~java
byte b = 1;
short s = 2;
char c = 'A';
int i = 3;
long l = 4L;
Integer boxed = 5;
Long boxedLong = 6L;
String text = "OPEN";
Object object = "OPEN";
~~~

Hãy xác định biến nào có thể dùng trực tiếp trong `switch (variable)` trên Java 17 ổn định. Với từng biến không được hỗ trợ, giải thích vì sao **kiểu tĩnh**, chứ không phải giá trị tại runtime, quyết định kết quả biên dịch.

### Bài 2 — Null và default

Dự đoán kết quả:

~~~java
static String check(Integer code) {
    return switch (code) {
        case 1 -> "ONE";
        default -> "OTHER";
    };
}
~~~

Với `check(1)`, `check(3)`, `check(null)`, hãy phân biệt nhánh case, nhánh default và exception. Sau đó sửa phương thức để null trả `"MISSING"` mà vẫn chỉ dùng cú pháp ổn định của Java 17.

### Bài 3 — Parse chuỗi trạng thái có thể null

Viết `String parseCommand(String value)` đáp ứng:

- `null` hoặc chuỗi rỗng chỉ gồm khoảng trắng trả `"EMPTY"`.
- `"START"` (bất kể hoa/thường, có thể có khoảng trắng hai đầu) trả `"RUN"`.
- `"STOP"` trả `"HALT"`.
- Mã khác trả `"UNSUPPORTED"`.

Dùng `strip()`, `toUpperCase(Locale.ROOT)` và switch expression. Giải thích vì sao kiểm tra null cần thực hiện **trước** `strip()`.

### Bài 4 — Enum bao phủ nhánh

Khai báo:

~~~java
enum DeliveryState {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED
}
~~~

Viết switch expression ánh xạ enum sang thông báo mà không dùng `default`. Thử thêm `RETURNED` vào enum và biên dịch lại để quan sát yêu cầu cập nhật các nhánh. Sau đó xét `DeliveryState state = null`: liệu liệt kê đủ hằng có ngăn `NullPointerException` không?

### Bài 5 — Xử lý dữ liệu `Object`

Một API nhận `Object rawStatus` do dữ liệu từ thư viện ngoài, nhưng chỉ nhận mã chuỗi `"READY"`, `"BLOCKED"`.

Hãy viết code Java 17:

1. Nếu `rawStatus` không phải `String`, trả một thông báo đầu vào sai kiểu.
2. Nếu đúng `String`, kiểm tra trường hợp rỗng hoặc không hợp lệ.
3. Dùng switch expression trên biến `String` đã được xác minh.
4. Không dùng switch trực tiếp trên `Object`, `case String s` hoặc `case null` preview.

### Bài 6 — Thiết kế lại lựa chọn dùng `long`

Bạn nhận các ID kiểu `long` và muốn ánh xạ vài mã đặc biệt sang thông báo. Hãy đề xuất ít nhất hai phương án Java 17 ổn định không mất dữ liệu; giải thích khi nào `if`/`else` hợp lý, khi nào `Map<Long, String>` dễ bảo trì hơn và vì sao ép `(int)` có thể gây lỗi.

## 14. Câu hỏi tự kiểm tra

1. Selector expression là gì? Nó khác kết quả của switch expression thế nào?
2. Bốn kiểu primitive nào làm selector được trên Java 17 ổn định?
3. Bốn wrapper tương ứng nào được phép? Khi nào chúng ném `NullPointerException`?
4. `String` và enum có thể làm selector không? Chúng có thể null không?
5. Vì sao `long` hoặc `Boolean` không thể làm selector trực tiếp trong Java 17?
6. Vì sao `Object raw = "READY"` vẫn không thể switch trực tiếp theo nhãn chuỗi?
7. `default` có bắt null selector không? Vì sao?
8. `case null` ở Java 17 thuộc trạng thái nào? Khi nào nó trở thành tính năng ổn định?
9. Có thể trả về null từ một nhánh switch expression hay không? Điều này khác null selector thế nào?
10. Tại sao switch expression trên enum có thể bỏ `default` khi liệt kê đủ hằng?
11. Dùng `yield` trong switch expression khi nào?
12. Vì sao nên tách việc kiểm tra null, chuẩn hóa đầu vào và chọn nhánh khi xử lý dữ liệu ngoài hệ thống?

## 15. Tài liệu tham khảo

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): quá trình chuẩn hóa switch expression ở Java 14, nền tảng cho Java 17.
- [Java Language Specification 17, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): các quy tắc selector, nhãn `case`, kiểu được hỗ trợ và xử lý switch.
- [Java Language Specification 17, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): ngữ nghĩa của switch expression và yêu cầu bao phủ nhánh.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): lý do `case null` và type patterns chưa thuộc tập tính năng ổn định của Java 17.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): mốc chuẩn hóa cú pháp pattern matching trong switch ở Java 21, giúp tránh nhầm lẫn khi đọc tài liệu phiên bản mới.
- [Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/): tài liệu chính thức cho `String`, `Integer`, `Objects`, `Locale` và các kiểu khác.

Trong Java 17 ổn định, hãy ghi nhớ hai ranh giới độc lập: **selector chỉ hỗ trợ những kiểu được quy định cụ thể** và **selector tham chiếu null sẽ ném `NullPointerException` trước khi chọn case, kể cả khi có `default`**. Việc kiểm tra null trước switch cùng với lựa chọn kiểu tĩnh phù hợp giúp code vừa rõ hợp đồng miền vừa tránh phụ thuộc vào cú pháp preview của Java 17.
