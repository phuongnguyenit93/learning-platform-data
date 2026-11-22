# Quan hệ giữa nhánh `throw` với suy luận kiểu kết quả của `switch expression` (Java 14+)

## 1. Vấn đề cần hiểu

Khi dùng `switch` như một **biểu thức tạo giá trị**, Java phải xác định kiểu của toàn bộ biểu thức để kiểm tra phép gán, giá trị trả về hoặc tham số của phương thức. Một số nhánh có thể không tạo giá trị vì chúng **ném ngoại lệ**:

~~~java
String label = switch (state) {
    case READY -> "Sẵn sàng";
    case RUNNING -> "Đang chạy";
    case REJECTED -> throw new IllegalStateException("Bị từ chối");
};
~~~

Dù `REJECTED` ném ra đối tượng `IllegalStateException`, Java **không cố ghép `String` với `IllegalStateException` để suy ra kiểu của `switch`**. `throw new ...` là một **câu lệnh `throw`**, làm luồng thực thi kết thúc đột ngột. Nó không sinh một giá trị `IllegalStateException` làm kết quả của `switch expression`.

Trong ví dụ, chỉ `"Sẵn sàng"` và `"Đang chạy"` là các **result expressions** (biểu thức kết quả). Nhánh `throw` vẫn là nhánh hợp lệ về điều khiển luồng, nhưng không góp kiểu vào tập biểu thức kết quả.

Phân biệt ba câu hỏi độc lập:

1. **Bao phủ (`exhaustiveness`):** Các nhãn `case`/`default` đã xử lý hết khả năng của selector chưa?
2. **Hoàn tất nhánh:** Đường đi trong nhánh đã trả giá trị bằng biểu thức/`yield` hoặc kết thúc đột ngột (chẳng hạn `throw`) chưa?
3. **Kiểu kết quả:** Những **biểu thức thực sự tạo giá trị** có tương thích với kiểu yêu cầu hoặc có thể suy ra cùng một kiểu theo quy tắc ngôn ngữ chưa?

Một `throw` có thể đáp ứng câu hỏi 2, nhưng không tự thay thế việc kiểm tra câu hỏi 1 và câu hỏi 3.

## 2. Chính xác biểu thức nào được xét khi suy luận kiểu?

Theo **Java Language Specification, §15.28.1**, các thành phần được tính là *result expressions* gồm:

- Biểu thức ở bên phải quy tắc `case X -> expression;`, ví dụ `case READY -> "OK";`.
- Biểu thức nằm trong `yield expression;` trỏ tới chính `switch expression` đang xét, ví dụ `case RUNNING -> { yield "Đang chạy"; }`.

Ngược lại:

- `case REJECTED -> throw new IllegalStateException(...);` **không** có result expression.
- `case REJECTED -> { throw new IllegalStateException(...); }` cũng **không** có result expression.
- `case RUNNING -> { if (invalid) throw ...; yield "OK"; }` **có** một result expression là `"OK"`, vì `yield` là đường đi tạo giá trị.

Ví dụ minh họa trong một phương thức có biến `state` kiểu enum thích hợp:

~~~java
String result = switch (state) {
    case READY -> "ready";
    case RUNNING -> {
        if (needsRetry) {
            throw new IllegalStateException("Hãy thử lại");
        }
        yield "running";
    }
    case REJECTED -> throw new IllegalArgumentException("Đầu vào bị từ chối");
};
~~~

Ở đây tập result expressions là `"ready"` và `"running"`. Điều kiện `needsRetry` và các nhánh ném ngoại lệ chỉ quyết định **có tạo được giá trị ở runtime hay không**; chúng không thêm một kiểu kết quả mới.

**Lưu ý quan trọng:** Java còn yêu cầu `switch expression` phải có **ít nhất một** result expression. Nếu **mọi nhánh đều là `throw`**, dù các `case` đã exhaustive, chương trình vẫn gặp **lỗi biên dịch** vì không có biểu thức kết quả nào để xác định kiểu. Quy tắc này được phân tích ở mục 6.

## 3. Hai cơ chế kiểu: có kiểu đích và tự xác định kiểu

### 3.1. Switch expression có kiểu đích (poly expression)

Khi `switch expression` đứng trong **ngữ cảnh phép gán** hoặc **ngữ cảnh gọi phương thức** (assignment/invocation context), nó là *poly expression* nếu ngữ cảnh đó cung cấp kiểu đích `T`. Java kiểm tra **từng result expression** có tương thích với `T` hay không. Kiểu của toàn bộ poly switch expression chính là `T`.

Ví dụ:

~~~java
String text = switch (state) {
    case READY -> "ready";
    case RUNNING -> "running";
    case REJECTED -> throw new IllegalStateException("rejected");
};
~~~

Kiểu đích ở đây là `String`. Hai biểu thức chuỗi hợp lệ; nhánh ném ngoại lệ không có giá trị cần chuyển đổi sang `String`, nên không gây lỗi kiểu.

Tương tự, `return switch (...) { ... };` trong phương thức trả về `String` sử dụng kiểu trả về của phương thức làm kiểu đích; khi truyền switch expression cho một phương thức có tham số được xác định là `String`, tham số này cũng tạo ngữ cảnh kiểu đích thích hợp.

Ví dụ mảnh mã minh họa:

~~~java
static String describe(State state) {
    return switch (state) {
        case READY -> "ready";
        case RUNNING -> "running";
        case REJECTED -> throw new IllegalStateException("rejected");
    };
}
~~~

Đoạn trên giả định `State` là enum khai báo đủ ba hằng. Kiểu của phương thức là `String`; không có yêu cầu `IllegalStateException` phải tương thích với `String`.

Kiểu đích còn hỗ trợ kiểm tra các **kiểu số hợp lệ theo phép gán**, kể cả một số phép thu hẹp hằng số:

~~~java
byte small = switch (state) {
    case READY -> 10;
    case RUNNING -> 20;
    case REJECTED -> throw new IllegalStateException("rejected");
};
~~~

Hai số `10` và `20` là hằng `int` nằm trong miền `byte`, nên có thể dùng trong ngữ cảnh gán cho `byte`. Nhánh throw không có giá trị cần chuyển sang `byte`. Nếu đổi nhánh `RUNNING` thành `200`, nhánh này sẽ không còn tương thích với kiểu đích `byte`, dù vẫn có nhánh `throw`.

### 3.2. Switch expression tự xác định kiểu (standalone expression)

Khi không có ngữ cảnh kiểu đích như trên, `switch expression` là **standalone expression**. Java suy ra kiểu từ các result expressions bằng các quy tắc về cùng kiểu, `boolean`/`Boolean`, numeric promotion, boxing và least upper bound của các kiểu tham chiếu.

Một ví dụ điển hình là khởi tạo biến bằng `var`:

~~~java
var count = switch (state) {
    case READY -> 1;
    case RUNNING -> 2L;
    case REJECTED -> throw new IllegalStateException("rejected");
};
~~~

Với `READY`, kết quả là biểu thức `int` (`1`); với `RUNNING`, kết quả là `long` (`2L`). Do các result expressions đều là kiểu số, numeric promotion xác định kiểu của switch là **`long`**, và `var count` suy ra **`long`**. Nhánh `throw` không làm `count` mang kiểu exception.

Điểm cần nhớ: `var` không truyền kiểu đích cụ thể vào initializer như `String x = ...`; kiểu cục bộ được suy ra từ **kiểu của initializer**. Việc có `throw` không cho phép `var` bỏ qua các quy tắc suy luận kiểu của các nhánh tạo giá trị.

### 3.3. Bảng so sánh

| Cách viết | Nguồn quyết định kiểu | Vai trò của nhánh `throw` |
| --- | --- | --- |
| `String x = switch (...)` | Kiểu đích `String` | Không phải result expression |
| `return switch (...)` trong phương thức trả `String` | Kiểu trả về `String` | Không phải result expression |
| `acceptString(switch (...))` | Kiểu tham số `String` trong ngữ cảnh gọi | Không phải result expression |
| `var x = switch (...)` | Các result expressions còn lại của switch | Không đóng góp kiểu |
| `long x = switch (...)` | Kiểu đích `long` và phép chuyển đổi hợp lệ | Không đóng góp kiểu |

Đừng ghi nhớ rằng “Java luôn lấy kiểu của nhánh không throw đầu tiên”: Java **xét tất cả** result expressions theo cơ chế tương ứng với ngữ cảnh.

## 4. Chương trình hoàn chỉnh chạy trên Java 17+

Ví dụ này tách riêng suy luận kiểu từ `var`, kiểm tra kiểu đích khi `return`, và việc suy luận generic với `List<String>`.

Lưu dưới tên **`SwitchThrowTypingDemo.java`**, dùng UTF-8:

~~~java
import java.util.List;

public class SwitchThrowTypingDemo {
    enum Mode {
        TEXT, NUMBER, DENIED
    }

    static String label(Mode mode) {
        return switch (mode) {
            case TEXT -> "text";
            case NUMBER -> {
                String prefix = "num";
                yield prefix + "ber";
            }
            case DENIED -> throw new IllegalArgumentException("mode denied");
        };
    }

    static long units(Mode mode) {
        var value = switch (mode) {
            case TEXT -> 1;            // int
            case NUMBER -> 2L;         // long
            case DENIED -> throw new IllegalArgumentException("mode denied");
        };
        return value;                  // value được suy ra long
    }

    static List<String> tags(Mode mode) {
        return switch (mode) {
            case TEXT -> List.of("text");
            case NUMBER -> List.of("number");
            case DENIED -> throw new IllegalArgumentException("mode denied");
        };
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            try {
                System.out.println(
                    mode + " | " + label(mode)
                         + " | units=" + units(mode)
                         + " | tags=" + tags(mode)
                );
            } catch (IllegalArgumentException ex) {
                System.out.println(
                    mode + " | ERROR: " + ex.getMessage()
                );
            }
        }
    }
}
~~~

Lệnh biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 SwitchThrowTypingDemo.java
java SwitchThrowTypingDemo
~~~

Kết quả chuẩn:

~~~text
TEXT | text | units=1 | tags=[text]
NUMBER | number | units=2 | tags=[number]
DENIED | ERROR: mode denied
~~~

**Phân tích theo phương thức:**

1. `label`: `return switch` có kiểu đích `String`. `"text"` và giá trị từ `yield prefix + "ber"` đều là chuỗi. Nhánh `DENIED` ném ngoại lệ mà không tạo giá trị để xác định kiểu.
2. `units`: `var value` nhận kiểu từ standalone switch. `1` (`int`) và `2L` (`long`) dẫn đến `long`. Việc `return value;` tương thích với kiểu trả về `long` là một kiểm tra bổ sung; nhánh throw không làm thay đổi `long`.
3. `tags`: kiểu đích là `List<String>`. Các lệnh gọi generic `List.of("text")` và `List.of("number")` đều có thể được suy luận tương thích với kiểu đích này. Nhánh throw không góp một kiểu phần tử hay một kiểu `List` khác.
4. Với `DENIED`, lời gọi `label(mode)` ném ngoại lệ trước khi phần còn lại của phép nối chuỗi trong `println` hoàn tất. Không có dòng kết quả thành công; chỉ dòng `catch` được in.

Đây là chương trình độc lập, không cần thư viện ngoài. Nó kiểm tra đồng thời **cú pháp**, **kiểu biên dịch** và **luồng chạy khi ném ngoại lệ**.

## 5. Nhánh throw không hợp thức hóa các nhánh trả sai kiểu

Xét ví dụ **cố ý không biên dịch** sau (giả định enum `Mode` như mục 4):

~~~java
String label = switch (mode) {
    case TEXT -> "text";
    case NUMBER -> 42;  // int không tương thích với kiểu đích String
    case DENIED -> throw new IllegalArgumentException("denied");
};
~~~

Tuy `DENIED` hợp lệ về luồng điều khiển, `case NUMBER -> 42;` vẫn là một result expression không tương thích với `String`. Compiler báo lỗi kiểu; **nhánh throw không xóa hoặc sửa sai kiểu của nhánh khác**.

Giải pháp phải dựa trên hợp đồng dữ liệu:

- Nếu mọi trường hợp thành công đều cần chuỗi: viết `case NUMBER -> "42";` hoặc chuyển đổi sang chuỗi một cách có chủ đích.
- Nếu API muốn trả nhiều dạng dữ liệu: thiết kế kiểu kết quả chung thích hợp, chẳng hạn một kiểu miền nghiệp vụ rõ ràng; không dùng `Object` chỉ để né compiler nếu điều đó làm mất an toàn kiểu.
- Nếu `NUMBER` đúng ra là tình huống lỗi: có thể thay bằng một nhánh `throw`, nhưng **chỉ khi** yêu cầu nghiệp vụ xác định nó là lỗi, không phải để “bịt” lỗi type mismatch.

Ví dụ khác là kiểu số trong `var`:

~~~java
var number = switch (mode) {
    case TEXT -> 1;      // int
    case NUMBER -> 2.5;  // double
    case DENIED -> throw new IllegalStateException("denied");
};
~~~

Kiểu suy ra là `double` vì hai result expressions là số và được numeric promotion. Nó **không** trở thành kiểu `Throwable`, cũng không nhất thiết giữ kiểu của nhánh đầu tiên.

Nếu các nhánh thành công trả các kiểu tham chiếu khác nhau, Java có thể tính least upper bound sau các chuyển đổi thích hợp. Kết quả đôi khi là kiểu chung hoặc kiểu giao phức tạp; tránh khẳng định rằng `var` sẽ luôn suy ra `Object` cho mọi cặp kiểu khác nhau. Muốn API dễ hiểu, hãy chủ động thống nhất một kiểu kết quả.

## 6. Trường hợp **mọi nhánh đều throw**: vẫn lỗi biên dịch

Một hiểu lầm phổ biến là “nếu không thể chạy bình thường thì không cần kiểu kết quả”. Quy tắc thực tế nghiêm hơn: một **switch expression bắt buộc có ít nhất một result expression**, dù các nhánh có thể ném ngoại lệ.

Ví dụ dưới đây **cố ý không biên dịch**:

~~~java
String result = switch (mode) {
    case TEXT -> throw new IllegalStateException("text");
    case NUMBER -> throw new IllegalStateException("number");
    case DENIED -> throw new IllegalStateException("denied");
};
~~~

Mọi hằng enum đã được liệt kê (exhaustive), mọi nhánh đều kết thúc đột ngột, nhưng **không có bất kỳ biểu thức kết quả** nào. JLS §15.28.1 quy định đây là lỗi compile; thông báo chi tiết phụ thuộc JDK.

Nếu mục tiêu là **luôn ném lỗi**, một cách đơn giản là dùng **switch statement** (không yêu cầu tạo giá trị):

~~~java
switch (mode) {
    case TEXT -> throw new IllegalStateException("text");
    case NUMBER -> throw new IllegalStateException("number");
    case DENIED -> throw new IllegalStateException("denied");
}
~~~

Đoạn switch statement ở trên là mã minh họa đặt trong phương thức có biến `mode`; nó không phải biểu thức gán cho `String`. Chọn cấu trúc phản ánh đúng ý định: nếu không có kết quả hợp lệ nào có thể được trả ra, đừng cố ép chương trình dùng switch expression.

Một ví dụ **có ít nhất một biểu thức kết quả** là hợp lệ:

~~~java
String result = switch (mode) {
    case TEXT -> "text";
    case NUMBER, DENIED -> throw new IllegalStateException("not text");
};
~~~

Giờ `"text"` là result expression; các giá trị còn lại vẫn có đường xử lý qua throw. Kiểu đích `String` tương thích với biểu thức duy nhất này.

## 7. Phân biệt `throw` với *trả về đối tượng exception*

Cả hai dòng sau **khác nhau về kiểu và hành vi**:

~~~java
case DENIED -> throw new IllegalStateException("denied");
~~~

~~~java
case DENIED -> new IllegalStateException("denied");
~~~

Dòng đầu là **throw statement**, không đóng góp result expression; dòng sau là **expression tạo đối tượng** có kiểu `IllegalStateException`. Nếu dòng sau xuất hiện trong một switch gán cho `String`, compiler sẽ báo lỗi kiểu vì `IllegalStateException` không tương thích với `String`. Nó cũng **không tự động ném ngoại lệ** ở runtime.

Một lỗi tư duy tương tự xuất hiện với lời gọi hàm vốn luôn ném ngoại lệ:

~~~java
static String fail() {
    throw new IllegalStateException("denied");
}

// Đây vẫn là MỘT result expression có kiểu String:
case DENIED -> fail();
~~~

Từ góc nhìn kiểm tra kiểu, `fail()` là **biểu thức gọi phương thức**, mang kiểu trả về đã khai báo `String`, dù thực thi của hàm luôn ném ngoại lệ. Khác với `case DENIED -> throw ...;`, nhánh `case DENIED -> fail();` **vẫn đóng góp kiểu `String`**. Compiler dựa vào cú pháp và khai báo kiểu, không dự đoán mọi hành vi runtime để loại bỏ lời gọi hàm khỏi danh sách result expressions.

Có thể viết một helper tạo exception rồi dùng `throw` tường minh:

~~~java
static IllegalStateException denied() {
    return new IllegalStateException("denied");
}

// Nhánh này không tạo result expression:
case DENIED -> throw denied();
~~~

Các mảnh mã trong mục 7 dùng để đối chiếu ngữ nghĩa; hãy đặt chúng vào class/switch đầy đủ khi chạy.

## 8. Kết hợp `throw` với `yield` trong khối

Một nhánh `case ... -> { ... }` có thể thực hiện nhiều thao tác. Nếu có đường đi thành công, dùng `yield` cho đường đó; nếu có lỗi, `throw` kết thúc đường lỗi:

~~~java
static String normalize(Mode mode, boolean available) {
    return switch (mode) {
        case TEXT -> {
            if (!available) {
                throw new IllegalStateException("text unavailable");
            }
            yield "text";
        }
        case NUMBER -> "number";
        case DENIED -> throw new SecurityException("access denied");
    };
}
~~~

Đoạn này đặt trong class đã khai báo enum `Mode` ở mục 4. Cặp result expressions là `"text"` và `"number"`, nên tương thích với `String`.

Trong thân khối:

- `throw` **không** tạo kết quả và không cần `yield` sau nó trên cùng đường đi.
- `yield "text";` cung cấp giá trị cho switch expression.
- Nếu một đường đi có thể **thoát khỏi cuối khối** mà không `yield` hoặc kết thúc đột ngột, compiler báo lỗi vì khối của switch expression không được hoàn tất bình thường mà thiếu giá trị.
- `yield throw new ...` không phải cú pháp hợp lệ; `throw` là câu lệnh, không phải một biểu thức kết quả để đặt sau `yield`.

Nói cách khác, **bảo đảm kết thúc nhánh** và **suy luận kiểu từ biểu thức kết quả** phối hợp với nhau, nhưng là hai kiểm tra khác nhau của compiler.

## 9. Checked exception ảnh hưởng lời gọi, không ảnh hưởng kiểu kết quả

Một nhánh `throw` có thể ném **unchecked exception** (`RuntimeException` và các lớp con) hoặc **checked exception** như `IOException`. Quy tắc exception checking hoạt động độc lập với việc suy ra kiểu của switch expression.

Ví dụ sau là phương thức minh họa đầy đủ về mặt cú pháp (đặt trong class có `import java.io.IOException;`):

~~~java
enum Source { MEMORY, REMOTE }

static int loadCount(Source source) throws IOException {
    return switch (source) {
        case MEMORY -> 3;
        case REMOTE -> throw new IOException("Remote source unavailable");
    };
}
~~~

- Kiểu đích của `return switch` là `int`, do phương thức `loadCount` khai báo `int`. `case MEMORY -> 3;` tương thích; `throw new IOException(...)` không góp kiểu `IOException` vào kết quả.
- Vì `IOException` là checked exception, phương thức cần khai báo `throws IOException` hoặc xử lý exception ở phạm vi phù hợp. Nếu bỏ `throws` mà không `catch`, mã không biên dịch.
- Lệnh gọi `loadCount(Source.REMOTE)` không trả một `int`; nó ném exception. Caller phải tuân thủ quy tắc exception checking của Java.

Không nên suy từ việc “nhánh throw không ảnh hưởng kiểu kết quả” thành “nhánh throw không ảnh hưởng tính hợp lệ của chương trình”. **Các nghĩa vụ kiểm tra ngoại lệ vẫn áp dụng đầy đủ.**

## 10. Các tình huống biên: `null`, `var` và thay đổi enum

### 10.1. Chỉ có `null` là kết quả

`null` là **biểu thức kết quả** khi được dùng trực tiếp ở nhánh `-> null;`, khác hoàn toàn với một nhánh `throw`:

~~~java
String optional = switch (mode) {
    case TEXT -> null;
    case NUMBER, DENIED -> throw new IllegalStateException("not available");
};
~~~

Mã có kiểu đích `String` nên hợp lệ: `null` có thể gán vào kiểu tham chiếu, còn các nhánh throw không góp giá trị.

Tuy nhiên, nếu đổi sang:

~~~java
var optional = switch (mode) {
    case TEXT -> null;
    case NUMBER, DENIED -> throw new IllegalStateException("not available");
};
~~~

thì đây là **lỗi biên dịch** vì `var` không thể suy ra kiểu biến cục bộ hợp lệ khi kiểu standalone switch là *null type*. `throw` không cung cấp kiểu để bù vào. Giải pháp là khai báo kiểu đích cụ thể nếu hợp đồng dữ liệu thực sự cho phép `null`, hoặc thiết kế kết quả có nghĩa hơn.

### 10.2. Selector bằng `null` là chuyện khác

Nếu biến `mode` bằng `null`, các nhánh `case TEXT`, `case NUMBER` và `case DENIED` không tự tạo ra kết quả. Với switch enum thông thường trên Java 17, quá trình đánh giá sẽ ném `NullPointerException`. Đây là hành vi của **selector**, không liên quan đến việc một nhánh `throw` có đóng góp kiểu hay không.

Nếu null bị cấm, kiểm tra trước bằng `Objects.requireNonNull(mode)` hoặc kiểm tra tường minh. Từ Java 21, `case null -> ...` là cú pháp chính thức nếu bạn muốn xử lý null trong switch. Dùng cú pháp tương thích với phiên bản JDK mục tiêu.

### 10.3. Enum có thêm hằng mới

Nếu enum `Mode` có thêm hằng `ARCHIVED`, mọi switch expression không có `default` và chưa xử lý `ARCHIVED` sẽ **không còn exhaustive khi biên dịch lại**. Có sẵn `case DENIED -> throw ...` không giúp xử lý giá trị `ARCHIVED`.

Một `default -> throw ...;` có thể là chính sách chủ ý để từ chối mọi giá trị khác, nhưng cũng có nghĩa compiler sẽ không buộc bạn xử lý riêng hằng mới. Khi enum biểu diễn trạng thái nghiệp vụ đóng, thường nên liệt kê case tường minh và biên dịch lại các module phụ thuộc khi mở rộng enum.

## 11. Những hiểu nhầm cần tránh

| Hiểu nhầm | Quy tắc thực tế |
| --- | --- |
| “Nhánh throw làm switch có kiểu `Exception`.” | Throw statement không phải result expression; kiểu switch đến từ kiểu đích hoặc các result expressions khác. |
| “Chỉ cần mọi nhánh có throw là switch expression hợp lệ.” | Cần exhaustive **và ít nhất một result expression**. |
| “Có throw thì không cần kiểm tra kiểu các case khác.” | Mọi result expression vẫn phải hợp lệ theo ngữ cảnh kiểu. |
| “Trong `var`, compiler lấy kiểu nhánh đầu tiên.” | Standalone switch áp dụng bộ quy tắc suy luận kiểu trên toàn bộ result expressions. |
| “`case X -> new Exception(...)` tương đương throw.” | Đó là biểu thức tạo đối tượng exception, không ném ngoại lệ. |
| “Gọi hàm chắc chắn throw cũng không tính là result expression.” | Nếu viết `case X -> fail();`, lời gọi hàm là result expression theo kiểu trả về được khai báo. |
| “Throw checked exception không liên quan đến compile.” | Java vẫn yêu cầu bắt hoặc khai báo checked exception. |
| “Nhánh throw bao phủ cả enum mới và selector null.” | Exhaustiveness và xử lý null là các kiểm tra độc lập. |

Một quy trình review ngắn: xác định `switch` ở **ngữ cảnh poly hay standalone**, gạch chân tất cả **result expressions**, kiểm tra quy tắc kiểu trên các biểu thức đó, sau cùng kiểm tra exhaustive, đường đi `yield`/`throw`, và checked exceptions.

## 12. Bài tập áp dụng

**Bài 1 — Dự đoán kiểu `var`.** Với enum `Mode` ở mục 4, suy ra kiểu của biến bên dưới trước khi biên dịch:

~~~java
var value = switch (mode) {
    case TEXT -> 4;
    case NUMBER -> 5.0;
    case DENIED -> throw new IllegalStateException("denied");
};
~~~

Đáp án: `double` nhờ numeric promotion từ `int` và `double`. Nếu chương trình đi vào `DENIED`, ngoại lệ được ném và phép khởi tạo không hoàn tất.

**Bài 2 — Vì sao lỗi compile?** Dự đoán tại sao mã sau không biên dịch, dù có kiểu đích rõ ràng:

~~~java
Object value = switch (mode) {
    case TEXT -> throw new IllegalArgumentException("text");
    case NUMBER -> throw new IllegalArgumentException("number");
    case DENIED -> throw new IllegalArgumentException("denied");
};
~~~

Đáp án: switch expression không có result expression nào. **Thêm kiểu đích `Object` không thay thế được** yêu cầu phải có ít nhất một biểu thức kết quả.

**Bài 3 — Sửa hai vấn đề độc lập.** Ban đầu:

~~~java
String result = switch (mode) {
    case TEXT -> "text";
    case NUMBER -> 10;
    case DENIED -> throw new IllegalStateException("denied");
};
~~~

Đề bài: (a) giải thích lỗi kiểu ở nhánh `NUMBER`; (b) sửa `NUMBER` thành chuỗi; (c) thêm hằng `ARCHIVED` vào `Mode` rồi giải quyết lỗi exhaustive riêng, chọn trả về giá trị hay throw theo yêu cầu nghiệp vụ.

**Bài 4 — Kiểu khai báo của helper.** Viết `static String fail() { throw new IllegalStateException("fail"); }`, rồi so sánh `case DENIED -> fail();` và `case DENIED -> throw new IllegalStateException("fail");`. Câu hỏi: cú pháp nào đóng góp một result expression? Vì sao cả hai vẫn có thể ném cùng ngoại lệ ở runtime?

## Tài liệu chính thức

- [Java Language Specification, §15.28.1 — The Switch Block of a switch Expression (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28.1): quy tắc result expressions, yêu cầu ít nhất một result expression và sự khác nhau giữa poly và standalone switch.
- [Java Language Specification, §15.28.2 — Run-Time Evaluation of switch Expressions (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28.2): hoàn tất bình thường, `yield` và hoàn tất đột ngột do `throw`.
- [Oracle Java Language Updates — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): cách viết `case ->`, khối lệnh, `yield` và `throw`.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): thiết kế switch expression được chuẩn hóa trong Java 14.
