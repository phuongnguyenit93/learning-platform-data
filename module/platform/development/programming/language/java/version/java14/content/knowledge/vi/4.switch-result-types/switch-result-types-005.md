# Nhánh có `null` và ảnh hưởng tới kiểu suy luận của `switch` expression

**Ngữ cảnh:** *Java 14 → Kiểu kết quả switch*. Bài này phân tích trường hợp một nhánh của **`switch` expression trả về `null`**, cách Java quyết định kiểu kết quả tại thời điểm biên dịch, và sự khác biệt với **`null` ở biểu thức chọn nhánh**. Các quy tắc về `switch` expression đã ổn định từ Java 14; phần `case null` dành riêng cho Java 21+ là tính năng chính thức, không phải preview.

## 1. Phân biệt hai vị trí của `null`

| Tình huống | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Kết quả của nhánh là `null`** | `case 0 -> null;` | `switch` chọn được nhánh và **trả về tham chiếu null**; có thể hợp lệ nếu kiểu đích phù hợp |
| **Giá trị đem ra chọn nhánh là `null`** | `switch (name)` khi `name == null` | Java 14 không hỗ trợ `case null`, nên sẽ ném `NullPointerException`; Java 21+ có thể xử lý bằng `case null` |
| **Nhãn `case null`** | `case null -> "MISSING";` | So khớp đầu vào null, **khác hẳn** một nhánh trả về null; chỉ hợp lệ với kiểu tham chiếu và dùng được từ Java 21+ |

Ba tình huống trên thuộc các giai đoạn khác nhau. Compiler kiểm tra **kiểu của mọi biểu thức kết quả** (`"text"`, `null`, số...), còn lúc chạy chỉ đánh giá **nhánh được chọn**. Vì vậy, một nhánh `null` có thể khiến đoạn mã **không biên dịch được** ngay cả khi bạn nghĩ sẽ không bao giờ chọn nhánh đó.

### Ví dụ đầu tiên: trả về null là hợp lệ

~~~java
int state = 0;

String label = switch (state) {
    case 0 -> null;       // kết quả là tham chiếu null
    case 1 -> "READY";
    default -> "UNKNOWN";
};

System.out.println(label == null); // true
~~~

Đây là **đoạn mã đặt trong phương thức**, dùng cú pháp `switch` expression Java 14+. Kiểu đích `String` chấp nhận `null`, nên mã biên dịch. Không có `case null` trong ví dụ: `state` là một `int`, không thể mang `null`.

Một `switch` **expression** phải bao phủ mọi giá trị của selector ở mức quy tắc exhaustiveness (thường dùng `default`, hoặc đủ hằng enum); những nhánh tạo ra kết quả phải trả một giá trị thông qua `-> biểu_thức` hoặc `yield` trong khối. Đây là khác biệt quan trọng so với `switch` statement chỉ thực thi lệnh.

## 2. Quy tắc kiểu: poly expression và standalone expression

Theo *Java Language Specification* (JLS), `switch` expression có hai chế độ:

1. **Poly expression** khi đứng trong **ngữ cảnh gán** hoặc **ngữ cảnh tham số gọi phương thức**. Kiểu mục tiêu `T` được truyền xuống các biểu thức kết quả; tất cả nhánh phải tương thích với `T`. Kiểu của `switch` chính là `T`.
2. **Standalone expression** trong các ngữ cảnh còn lại, nổi bật là khởi tạo biến bằng **`var`**. Compiler xác định kiểu từ **toàn bộ các nhánh kết quả**, không được cung cấp sẵn kiểu đích từ `var`.

Điều này giải thích vì sao đổi `String` hoặc `Boolean` thành `var` đôi khi **không chỉ làm mã ngắn hơn** mà còn làm thay đổi **kiểu biểu thức và chuyển đổi boxing/unboxing**.

### 2.1. Khi đã khai báo kiểu đích

~~~java
int code = 0;

String text = switch (code) {
    case 0 -> null;
    default -> "OK";
};

Integer count = switch (code) {
    case 0 -> null;
    default -> 42;
};

Number amount = switch (code) {
    case 0 -> null;
    case 1 -> 42;       // int có thể được boxing thành Integer
    default -> 2.5;     // double có thể được boxing thành Double
};
~~~

Tất cả các đoạn trên **biên dịch được** trong Java 14+: `String`, `Integer`, `Number` đều là kiểu tham chiếu và chấp nhận giá trị `null`. Các nhánh số được chuyển đổi để tương thích với kiểu đích khi cần. Đặc biệt, `null` **không mang một kiểu lớp cố định như `String` hoặc `Integer`**: literal `null` có *null type* và có thể được chuyển đến kiểu tham chiếu phù hợp.

Ngược lại, ví dụ **cố ý không biên dịch**:

~~~java
int code = 0;
int count = switch (code) {
    case 0 -> null; // LỖI BIÊN DỊCH: null không thể gán cho int
    default -> 42;
};
~~~

`int` là primitive, không biểu diễn sự thiếu vắng bằng `null`. Nếu có nhánh thực sự mang nghĩa “không có số lượng”, cần kiểu kết quả cho phép vắng giá trị (`Integer`, `OptionalInt`, hoặc kiểu kết quả nghiệp vụ khác); nếu đó là trạng thái không hợp lệ, nên ném ngoại lệ có ý nghĩa.

### 2.2. Khi dùng `var`: compiler tự tính kiểu của mọi nhánh

~~~java
int code = 0;

var message = switch (code) {
    case 0 -> null;
    default -> "READY";
};
// message có kiểu String và giá trị hiện tại là null

var count = switch (code) {
    case 0 -> null;
    default -> 42;
};
// count có kiểu Integer (không phải int), giá trị hiện tại là null
~~~

Vì `var` không cung cấp kiểu mục tiêu, compiler sử dụng quy tắc tính kiểu *standalone switch*:

- Nếu các kết quả đều cùng một kiểu, dùng kiểu đó.
- Nếu tất cả kiểu kết quả là `boolean`/`Boolean`, dùng `boolean` (có thể **unboxing**).
- Nếu tất cả kết quả chuyển được thành kiểu số, dùng quy tắc **numeric promotion**.
- Các trường hợp còn lại: boxing các primitive khi cần, rồi tính **cận trên chung nhỏ nhất** (*least upper bound – LUB*) của các kiểu tham chiếu. Nhánh literal `null` có thể nằm trong nhóm này; `String` cùng `null` dẫn tới `String`, `Integer` cùng `null` dẫn tới `Integer`.

Trong hai ví dụ trên, `message` được suy ra `String`; `count` được suy ra `Integer`. **Suy luận kiểu không tự xóa khả năng kết quả là null.** Không có phép kiểm tra runtime hay `Optional` tự động nào được thêm vào.

### 2.3. Tất cả các nhánh đều trả `null`

~~~java
int code = 0;

// HỢP LỆ: đã cung cấp kiểu đích String
String text = switch (code) {
    case 0 -> null;
    default -> null;
};
~~~

Trong ngữ cảnh gán `String`, mọi nhánh đều tương thích với kiểu đích. Nhưng đổi thành `var` như sau là **lỗi biên dịch**:

~~~java
int code = 0;

// KHÔNG BIÊN DỊCH: chỉ suy ra null type, var không nhận kiểu này
var text = switch (code) {
    case 0 -> null;
    default -> null;
};
~~~

Hãy chỉ rõ kiểu cần biểu diễn hoặc thiết kế lại hợp đồng. Không nên viết `var` rồi mong compiler tự chọn `Object` hay `String` khi không có nhánh nào cung cấp thông tin kiểu.

### 2.4. Khác nhau giữa `var` và kiểu đích có thể gây lỗi lúc chạy

Xét một giá trị `Boolean` có thể là null:

~~~java
Boolean maybeEnabled = null;
int code = 0;

// HỢP LỆ, an toàn khi lưu null vào biến Boolean:
Boolean boxed = switch (code) {
    case 0 -> maybeEnabled;
    default -> true;
};
System.out.println(boxed == null); // true
~~~

Nhưng thay `Boolean boxed` bằng `var enabled`:

~~~java
Boolean maybeEnabled = null;
int code = 0;

// BIÊN DỊCH ĐƯỢC, nhưng có thể NPE lúc chạy:
var enabled = switch (code) {
    case 0 -> maybeEnabled;
    default -> true;
};
~~~

Vì đây là standalone switch và mọi kết quả là `Boolean`/`boolean`, **kiểu suy ra là primitive `boolean`**. Đánh giá nhánh `maybeEnabled == null` sẽ cố **unbox** và gây `NullPointerException`. Đây là lỗi rất dễ bỏ sót: sự xuất hiện của một giá trị **có kiểu `Boolean`** khác với một nhánh là literal `null`.

**Cách viết rõ ý định:** khai báo `Boolean` nếu null là kết quả hợp lệ; hoặc loại bỏ null trước khi trả về `boolean`, ví dụ `Boolean.TRUE.equals(maybeEnabled)` nếu quy tắc nghiệp vụ coi null là false.

## 3. Bảng phân tích những tổ hợp thường gặp

Giả sử selector là `int code` và `default` luôn có mặt. Các ví dụ chỉ minh họa **kiểu của biểu thức kết quả**, không yêu cầu chạy cả bảng:

| Biểu thức kết quả ở các nhánh | Cách nhận kết quả | Kết luận |
| --- | --- | --- |
| `null` và `"OK"` | `String x = switch (...)` | Hợp lệ; nhánh null cho `x == null` |
| `null` và `"OK"` | `var x = switch (...)` | Suy ra `String`; có thể null |
| `null` và `42` | `Integer x = switch (...)` | Hợp lệ; boxing nhánh số khi cần |
| `null` và `42` | `var x = switch (...)` | Suy ra `Integer`, không phải `int` |
| `null` và `42` | `int x = switch (...)` | **Lỗi biên dịch:** literal null không tương thích `int` |
| `null` và `null` | `String x = switch (...)` | Hợp lệ do có kiểu đích |
| `null` và `null` | `var x = switch (...)` | **Lỗi biên dịch:** không suy ra kiểu hợp lệ cho `var` |
| `10` và `20L` | `var x = switch (...)` | Suy ra `long` do numeric promotion |
| `Boolean` và `boolean` | `var x = switch (...)` | Suy ra `boolean`; có rủi ro unbox null |
| `1` và `"one"` | `var x = switch (...)` | Suy ra một **kiểu chung rộng** từ các nhánh (qua boxing/LUB); API cụ thể của `Integer`/`String` không tự được đảm bảo |

**Chủ đích thiết kế:** nếu các nhánh đại diện cho các loại kết quả khác nhau, đừng dựa mù vào một kiểu chung được suy ra khó hiểu. Cân nhắc một kiểu `Object` tường minh chỉ khi thật sự xử lý nhiều loại; thường tốt hơn là các nhánh có cùng kiểu nghiệp vụ hoặc một kiểu kết quả rõ ràng.

## 4. `yield null`, khối nhánh và ngoại lệ

Khi một nhánh cần nhiều câu lệnh, dùng khối `{ ... yield kết_quả; }`. `yield` truyền giá trị ra **switch expression**, và `yield null;` cũng là một giá trị hợp lệ nếu kiểu của switch cho phép.

~~~java
int code = 0;
String label = switch (code) {
    case 0 -> {
        System.out.println("Chưa có dữ liệu");
        yield null;
    }
    case 1 -> "READY";
    default -> throw new IllegalArgumentException("Trạng thái không hợp lệ");
};
~~~

Đây là **đoạn đặt trong phương thức**, có kết quả `null` khi `code == 0`. Nhánh `default -> throw ...` **không tạo biểu thức kết quả để suy kiểu** vì kết thúc bằng ngoại lệ; nó vẫn là một cách hợp lệ để xử lý trường hợp không thể trả giá trị. Không dùng `return` bên trong khối `switch` expression để trả giá trị từ nhánh; dùng `yield`.

Nếu ý nghĩa nhánh “không có dữ liệu” là hợp lệ, `yield null` có thể phù hợp theo hợp đồng; nếu đó là lỗi, dùng `throw`. Tránh biến một lỗi dữ liệu thành `null` khiến tầng gọi phải đoán nguyên nhân.

## 5. `null` của selector: sự khác biệt giữa Java 14 và Java 21+

Phần này nói về **đầu vào để chọn nhánh**, hoàn toàn độc lập với việc một nhánh có thể trả về null.

### 5.1. Cách viết dùng được với Java 14–20

~~~java
String status = null;

String label = switch (status) {
    case "READY" -> "Sẵn sàng";
    default -> "Khác";
};
// Nếu status == null thì ném NullPointerException.
// default KHÔNG phải nhánh xử lý null.
~~~

Trong Java 14, **không thể khai báo `case null`**. Vì thế, nếu `status` có thể là null và bạn cần biên dịch cho Java 14/17, xử lý trước switch:

~~~java
static String label14(String status) {
    if (status == null) {
        return "Chưa có trạng thái";
    }
    return switch (status) {
        case "READY" -> "Sẵn sàng";
        default -> "Khác";
    };
}
~~~

Phương thức minh họa trên thuộc một lớp Java. Dùng `Objects.requireNonNull(status, "status")` thay kiểm tra nếu **hợp đồng cấm null** và cần báo lỗi rõ ràng; không tự gán nghĩa mặc định cho mọi null.

### 5.2. Cách viết gọn hơn với Java 21+ (đã ổn định)

Từ Java 21, **pattern matching for switch** đã chính thức hỗ trợ `case null`:

~~~java
static String label21(String status) {
    return switch (status) {
        case null -> "Chưa có trạng thái";
        case "READY" -> "Sẵn sàng";
        default -> "Khác";
    };
}
~~~

Lưu ý:

- `case null` phù hợp khi **selector là kiểu tham chiếu** (như `String`, wrapper, enum...), không phải `int` primitive.
- `default` **không tự bắt null**; nếu không có nhãn phù hợp với selector null, vẫn ném `NullPointerException`.
- Có thể dùng nhãn kết hợp `case null, default -> "Khác hoặc null";` trong Java 21+ khi cả hai trường hợp có cùng xử lý. Nhãn kết hợp này phải nằm **cuối** phần case.
- Dù selector có được xử lý null hay không, **kiểu kết quả** của các nhánh vẫn tuân theo quy tắc poly/standalone trong mục 2.

Không sử dụng cú pháp `case null` nếu dự án còn biên dịch với `--release 14` hoặc `--release 17`. Đây là khác biệt **phiên bản ngôn ngữ**, không phải lý do dùng API cũ.

## 6. Chương trình hoàn chỉnh Java 14+: nhánh null và kiểu suy luận

Lưu với tên **`SwitchNullTypesDemo.java`**, chạy trên JDK 14+; câu lệnh dùng JDK 17+ minh họa cách đặt source compatibility Java 14:

~~~java
public class SwitchNullTypesDemo {
    static String label(int status) {
        return switch (status) {
            case 0 -> null;
            case 1 -> "READY";
            default -> {
                yield "UNKNOWN";
            }
        };
    }

    public static void main(String[] args) {
        String direct = switch (1) {
            case 0 -> null;
            default -> "READY";
        };

        var inferredText = switch (0) {
            case 0 -> null;
            default -> "READY";
        };

        Integer maybeCount = switch (0) {
            case 0 -> null;
            default -> 10;
        };

        var inferredCount = switch (0) {
            case 0 -> null;
            default -> 10;
        };

        System.out.println(direct);
        System.out.println(inferredText == null);
        System.out.println(maybeCount == null);
        System.out.println(inferredCount == null);
        System.out.println(label(1));
        System.out.println(label(2));

        // Một Integer được ép null rồi tự unbox thành int:
        try {
            int primitive = switch (0) {
                case 0 -> (Integer) null;
                default -> 5;
            };
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("UNBOX_NPE");
        }
    }
}
~~~

~~~bash
javac --release 14 -encoding UTF-8 SwitchNullTypesDemo.java
java SwitchNullTypesDemo
~~~

**Stdout:**

~~~text
READY
true
true
true
READY
UNKNOWN
UNBOX_NPE
~~~

Diễn giải:

1. `direct` là `String` có giá trị `"READY"`.
2. `inferredText` là `String`, nhưng nhánh được chọn trả `null`; biểu thức so sánh in `true`.
3. `maybeCount` là `Integer`, được phép nhận `null`.
4. `inferredCount` cũng là `Integer`, vì nhánh số `10` được boxing trong quá trình tính kiểu chung với `null`.
5. `label(1)` trả `"READY"`; `label(2)` trả `"UNKNOWN"`.
6. Nhánh `(Integer) null` khác với literal `null`: nó **có kiểu `Integer`**, nên tương thích với đích `int` qua unboxing. Code biên dịch nhưng ném `NullPointerException` khi chạy. `try/catch` cuối **chỉ để quan sát lỗi trong bài học**, không phải cách xử lý null được khuyến nghị cho nghiệp vụ.

## 7. Chương trình Java 21+: `case null` cho selector

Lưu thành **`SwitchNullSelector21Demo.java`**, yêu cầu JDK 21+ và biên dịch với `--release 21` (không cần preview):

~~~java
public class SwitchNullSelector21Demo {
    static String describe(String token) {
        return switch (token) {
            case null -> "MISSING";
            case "" -> "EMPTY";
            case "READY" -> "READY";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe(""));
        System.out.println(describe("READY"));
        System.out.println(describe("anything"));
    }
}
~~~

~~~bash
javac --release 21 -encoding UTF-8 SwitchNullSelector21Demo.java
java SwitchNullSelector21Demo
~~~

~~~text
MISSING
EMPTY
READY
OTHER
~~~

Đây là **null trong selector**; mỗi nhánh trả về một `String` không null. Ví dụ chứng minh hai lựa chọn độc lập: bạn có thể **bắt null đầu vào** mà vẫn **không trả null đầu ra**, hoặc ngược lại.

## 8. Cách thiết kế kết quả khi một nhánh “không có giá trị”

Có thể dùng `null` nếu hợp đồng API công khai và bên gọi xử lý đúng; nhưng nên chọn rõ ý nghĩa thay vì cho compiler tự đoán:

**Trường hợp A – null là một kết quả có thể xảy ra:**

~~~java
String label = switch (code) {
    case 0 -> null;
    case 1 -> "READY";
    default -> "UNKNOWN";
};

if (label == null) {
    System.out.println("Không có nhãn");
} else {
    System.out.println(label);
}
~~~

**Trường hợp B – muốn báo rõ sự vắng mặt bằng kiểu:**

~~~java
import java.util.Optional;

// Các dòng dưới đặt trong phương thức:
Optional<String> label = switch (code) {
    case 0 -> Optional.empty();
    case 1 -> Optional.of("READY");
    default -> Optional.of("UNKNOWN");
};

System.out.println(label.orElse("Không có nhãn"));
~~~

`Optional<String>` là kiểu kết quả tham chiếu rõ ràng và các nhánh tạo cùng loại kết quả. `Optional` hữu ích ở **ranh giới API** khi absence là một trạng thái hợp lệ; không cần biến **mọi biến cục bộ** thành `Optional`. Tránh đặt chính biến `Optional` bằng null. Với số nguyên, `OptionalInt` có thể là lựa chọn khi API cần diễn đạt việc thiếu một `int`.

**Trường hợp C – không thể có null theo hợp đồng:** xử lý đầu vào tại ranh giới và dùng `throw new IllegalArgumentException(...)`, `Objects.requireNonNull(...)` hoặc kiểm tra tương đương có thông điệp rõ. Không dùng giá trị `0`, chuỗi rỗng, `false` để “nuốt” dữ liệu thiếu nếu những giá trị đó có ý nghĩa nghiệp vụ riêng.

## 9. Lỗi phổ biến và cách tự kiểm tra

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `case 0 -> null` không gán được cho `int` | Literal null không chuyển thành primitive | Dùng kiểu tham chiếu hoặc đổi thiết kế nhánh |
| `var x = switch(...) { ... null ... null ... }` không biên dịch | Standalone chỉ có null type | Khai báo kiểu đích rõ ràng hoặc trả giá trị có kiểu |
| Có một `Boolean` nullable, dùng `var` rồi NPE | Quy tắc standalone cho `Boolean`/`boolean` suy ra `boolean` và unboxing | Chọn kiểu đích `Boolean` hoặc xử lý null trước |
| Dùng `default` để mong bắt selector null | `default` không khớp null | Với Java 14–20 kiểm tra trước; Java 21+ dùng `case null` |
| `case null` không biên dịch khi `--release 14` | Cú pháp chỉ ổn định từ Java 21 | Chuyển null-check ra ngoài switch cho Java 14 |
| Sau switch gọi `result.length()` và NPE | Nhánh hợp lệ đã trả null, kiểu `String` không bảo đảm non-null | Kiểm tra/đổi hợp đồng kết quả trước khi truy cập |
| Các nhánh trả kiểu quá khác nhau, `var` khó dùng | LUB suy ra kiểu chung rộng | Dùng cùng kiểu nghiệp vụ hoặc khai báo kiểu đích |
| `case null -> ...` và `case 0 -> null` bị nhầm | Nhãn **chọn đầu vào** khác biểu thức **trả đầu ra** | Đọc từng phía dấu `->` đúng vai trò |

Checklist khi đọc code:

1. Selector có thể là `null` không? Dự án dùng mức `--release` nào?
2. `null` xuất hiện **bên trái** hay **bên phải** dấu `->`?
3. Switch nằm trong phép gán/call có **kiểu đích tường minh**, hay `var` phải tự suy luận?
4. **Tất cả** nhánh trả kiểu gì? Có boxing/unboxing, promotion, LUB hoặc `yield null` không?
5. Kết quả được gán vào primitive, wrapper, hay kiểu tham chiếu? Null có hợp lệ theo **nghiệp vụ** không?
6. Bên gọi có kiểm tra kết quả trước khi dereference/unbox không?

## 10. Bài tập và câu hỏi tự đánh giá

1. Dự đoán kiểu và giá trị của `var x = switch (0) { case 0 -> null; default -> "A"; };`. Vì sao `x` có thể là null dù kiểu đã suy ra?
2. Dự đoán kết quả biên dịch của `int x = switch (0) { case 0 -> null; default -> 5; };`. Thử thay `int` bằng `Integer`.
3. Cho `Boolean b = null`. So sánh `Boolean x = switch(i) { case 0 -> b; default -> true; };` và `var x = switch(i) { case 0 -> b; default -> true; };` khi `i == 0`. Phân biệt lỗi compile-time và runtime.
4. So sánh `String x = switch(i) { case 0 -> null; default -> null; };` với phiên bản dùng `var`. Giải thích bằng poly/standalone.
5. Viết một nhánh khối có kiểm tra dữ liệu rồi `yield null`; dùng `throw` trong nhánh còn lại. Loại nào đóng góp vào kiểu kết quả của switch?
6. Viết `switch` xử lý `String status == null` theo hai cách: tương thích Java 14 (null-check trước) và Java 21+ (`case null`). Thử bỏ `case null` rồi quan sát `default` không thay thế được nó.
7. Refactor API trả `String` nullable thành `Optional<String>` ở một ranh giới phù hợp; so sánh mức độ rõ ràng của cách gọi.

### Tài liệu chuẩn để đối chiếu

- [Java SE 14 JLS §15.28 – Switch Expressions](https://docs.oracle.com/javase/specs/jls/se14/html/jls-15.html#jls-15.28): nền tảng phân loại poly/standalone và tính kiểu.
- [Java SE 21 JLS §15.28 – Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc kiểu hiện hành sau khi hỗ trợ pattern matching.
- [Java SE 21 JLS §14.11 – Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): điều kiện `case null`, exhaustiveness và cách chọn nhánh.

**Điểm cần nhớ:** `case 0 -> null` có thể là nhánh hợp lệ của `switch` expression; kiểu đích tường minh giúp compiler kiểm tra tương thích, còn `var` buộc compiler suy luận từ mọi nhánh và đôi khi sinh unboxing bất ngờ. `case null` dùng để xử lý **đầu vào** null chỉ từ Java 21+; nó không quyết định kiểu **đầu ra** của switch.