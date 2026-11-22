# Mô hình kết quả thành công, thất bại và các biến thể hợp lệ với `sealed` trong Java 17

Khi một phương thức thực hiện thao tác nghiệp vụ, kết quả thường không chỉ là một giá trị. Chẳng hạn, tìm khách hàng theo mã có thể **tìm thấy**, **không tìm thấy**, hoặc **bị từ chối vì mã không hợp lệ**. Nếu chỉ trả về `null`, `boolean` hoặc một đối tượng chứa nhiều trường tùy chọn, người gọi dễ hiểu nhầm trạng thái và bỏ sót cách xử lý.

Trong Java 17, **`sealed interface`/`sealed class`** cho phép xác định trước những kiểu nào được trực tiếp triển khai hoặc kế thừa một kiểu gốc. Kết hợp với **`record`**, ta biểu diễn từng trường hợp bằng một kiểu dữ liệu có ý nghĩa, mang đúng thông tin cần thiết. Đây là cách thiết kế đặc biệt hữu ích cho **kết quả thành công/thất bại**, **trạng thái luồng xử lý**, **thông điệp nghiệp vụ** và những tập biến thể được kiểm soát.

> Nội dung thực hành chỉ sử dụng tính năng ổn định trong Java 17: `sealed` (ổn định từ Java 17), `record` và pattern matching cho `instanceof` (đều ổn định trước Java 17). Không cần bật `--enable-preview`.

## 1. Vấn đề: một đối tượng kết quả có quá nhiều trạng thái mơ hồ

Giả sử chương trình tìm khách hàng và dùng kiểu dữ liệu sau:

~~~java
class LookupResponse {
    boolean success;
    Customer customer;
    String errorCode;
    String errorMessage;
}
~~~

Về ý nghĩa nghiệp vụ, ta chỉ muốn một trong hai nhánh:

- Thành công: có khách hàng.
- Thất bại: có lý do thất bại.

Nhưng kiểu dữ liệu trên lại cho phép các tổ hợp không nhất quán:

| `success` | `customer` | `errorCode` | Vấn đề |
| --- | --- | --- | --- |
| `true` | Khách hàng | `null` | Trạng thái thành công hợp lệ |
| `false` | `null` | Mã lỗi | Trạng thái thất bại hợp lệ |
| `true` | `null` | `null` | Thành công nhưng không có dữ liệu |
| `false` | Khách hàng | Mã lỗi | Vừa có dữ liệu thành công vừa báo lỗi |
| `true` | Khách hàng | Mã lỗi | Hai kết luận mâu thuẫn |

Việc “quy ước bằng lời” rằng lập trình viên không được gán các trường sai tổ hợp là chưa đủ. Thiết kế tốt hơn là biến **trạng thái hợp lệ** thành **kiểu dữ liệu hợp lệ**.

Một dạng đơn giản:

~~~java
sealed interface LookupResult permits Found, Failed { }

record Found(Customer customer) implements LookupResult { }

record Failed(ErrorInfo error) implements LookupResult { }
~~~

Ở đây, một `LookupResult` chỉ có thể trực tiếp là `Found` hoặc `Failed`. Mỗi record lưu dữ liệu riêng của trường hợp đó: `Found` không có trường lỗi; `Failed` không có trường khách hàng.

**Điểm quan trọng:** `sealed` chỉ giới hạn hệ phân cấp kiểu. Nó không tự cấm `null`, chuỗi trống, giá trị số âm hoặc các bất biến nghiệp vụ bị vi phạm. Muốn bảo vệ những điều ấy cần thêm kiểm tra trong constructor.

## 2. Cách hoạt động của `sealed` trong Java 17

Từ khóa `sealed` có thể dùng với class hoặc interface:

~~~java
public sealed interface OperationResult permits Success, Failure {
}
~~~

Danh sách `permits` khai báo các kiểu được phép **trực tiếp** triển khai `OperationResult`. Mỗi kiểu con được cho phép phải quyết định cách mở rộng hệ phân cấp:

| Khai báo kiểu con | Ý nghĩa |
| --- | --- |
| `final` | Không cho kế thừa tiếp |
| `sealed` | Cho kế thừa tiếp nhưng giới hạn bằng một danh sách kiểu con |
| `non-sealed` | Mở lại khả năng kế thừa cho các lớp/kiểu con tiếp theo |

Một `record` luôn là kiểu `final`, vì vậy phù hợp để làm “lá” trong mô hình kết quả đóng:

~~~java
sealed interface Result permits Success, Failure { }

record Success(String value) implements Result { }

record Failure(String reason) implements Result { }
~~~

Nếu khai báo một kiểu mới không nằm trong `permits`:

~~~java
// Lỗi biên dịch: Cancelled không được Result cho phép.
record Cancelled(String reason) implements Result { }
~~~

Compiler sẽ từ chối. Điều này bảo vệ việc mở rộng trực tiếp mô hình kết quả ngoài ý muốn.

### Quy tắc vị trí kiểu con

Trong **named module** của Java Platform Module System, kiểu con được cấp phép phải thuộc **cùng module** với kiểu `sealed`. Trong **unnamed module** (cách chạy classpath thông thường), kiểu con phải thuộc **cùng package**. Kiểu con cũng phải khai báo trực tiếp `extends` hoặc `implements` đối với kiểu `sealed` tương ứng.

Trong một trường hợp khác, khi tất cả kiểu con trực tiếp được khai báo trong cùng một compilation unit (cùng file nguồn), trình biên dịch có thể suy luận danh sách permitted types nếu bỏ `permits`. Tuy nhiên, khai báo tường minh `permits` thường giúp người học nhìn rõ phạm vi biến thể được chấp nhận.

### Vì sao thường kết hợp với `record`?

`record` cung cấp dữ liệu trạng thái rõ ràng với constructor, accessor, `equals`, `hashCode` và `toString` được sinh tự động. Ví dụ:

~~~java
record Found(Customer customer) implements LookupResult { }
~~~

Có accessor `customer()` và dữ liệu lưu trong thành phần record là `final`. Không cần viết getter hay setter thủ công cho dữ liệu kết quả.

Tuy nhiên, record chỉ đảm bảo **bất biến nông**: nếu một thành phần tham chiếu đến collection có thể sửa, nội dung collection vẫn có thể thay đổi. Khi cần bất biến thực chất, ưu tiên thành phần bất biến và sao chép phòng vệ, ví dụ `List.copyOf(input)`.

## 3. Mô hình thành công/thất bại cho một ca sử dụng cụ thể

Ta thiết kế chức năng tìm khách hàng theo mã nhập từ dòng lệnh.

### 3.1. Những kết quả hợp lệ

Giả sử dữ liệu khách hàng đã có trong bộ nhớ. Một yêu cầu có thể cho ra:

1. `Found`: tìm thấy khách hàng với một mã hợp lệ.
2. `Failed` có `INVALID_ID`: mã đầu vào trống, không phải số nguyên hoặc không dương.
3. `Failed` có `NOT_FOUND`: mã hợp lệ nhưng không tồn tại trong dữ liệu.

Hai kiểu trực tiếp `Found` và `Failed` thể hiện hai nhánh thành công/thất bại. Trong `Failed`, enum `ErrorCode` phân biệt các lý do được hỗ trợ.

~~~text
FindResult                          (sealed interface)
├── Found(Customer)                 (record, thành công)
└── Failed(ErrorInfo)               (record, thất bại)
      └── ErrorInfo
          ├── INVALID_ID
          └── NOT_FOUND
~~~

Vì danh sách mã lỗi hữu hạn và các mã này có cùng dạng dữ liệu (`code`, `message`), enum là phù hợp. Ở phần sau, ta sẽ dùng thêm `sealed` lồng nhau cho các lỗi mang **payload khác nhau**.

### 3.2. Ví dụ Java 17 có thể biên dịch và chạy độc lập

Đặt toàn bộ mã dưới đây vào **`src/demo/SealedResultDemo.java`**:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;

public final class SealedResultDemo {

    private SealedResultDemo() {
    }

    public record Customer(int id, String name) {
        public Customer {
            if (id <= 0) {
                throw new IllegalArgumentException("ID phải dương");
            }
            Objects.requireNonNull(name, "name");
            if (name.isBlank()) {
                throw new IllegalArgumentException("Tên không được trống");
            }
        }
    }

    public enum ErrorCode {
        INVALID_ID,
        NOT_FOUND
    }

    public record ErrorInfo(ErrorCode code, String message) {
        public ErrorInfo {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
            if (message.isBlank()) {
                throw new IllegalArgumentException("Thông báo lỗi không được trống");
            }
        }
    }

    public sealed interface FindResult permits Found, Failed {
    }

    public record Found(Customer customer) implements FindResult {
        public Found {
            Objects.requireNonNull(customer, "customer");
        }
    }

    public record Failed(ErrorInfo error) implements FindResult {
        public Failed {
            Objects.requireNonNull(error, "error");
        }
    }

    private static final Map<Integer, Customer> CUSTOMERS = Map.of(
            1, new Customer(1, "An"),
            2, new Customer(2, "Bình")
    );

    public static FindResult findCustomer(String rawId) {
        if (rawId == null || rawId.isBlank()) {
            return new Failed(new ErrorInfo(
                    ErrorCode.INVALID_ID,
                    "ID phải là số nguyên dương"));
        }

        final int id;
        try {
            id = Integer.parseInt(rawId.strip());
        } catch (NumberFormatException ex) {
            return new Failed(new ErrorInfo(
                    ErrorCode.INVALID_ID,
                    "ID phải là số nguyên dương"));
        }

        if (id <= 0) {
            return new Failed(new ErrorInfo(
                    ErrorCode.INVALID_ID,
                    "ID phải là số nguyên dương"));
        }

        Customer customer = CUSTOMERS.get(id);
        if (customer == null) {
            return new Failed(new ErrorInfo(
                    ErrorCode.NOT_FOUND,
                    "Không tìm thấy khách hàng"));
        }

        return new Found(customer);
    }

    public static String describe(FindResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof Found found) {
            return "Tìm thấy: " + found.customer().name()
                    + " (#" + found.customer().id() + ")";
        }

        if (result instanceof Failed failed) {
            ErrorInfo error = failed.error();
            return "Thất bại [" + error.code() + "]: " + error.message();
        }

        throw new IllegalStateException(
                "Biến thể kết quả chưa được xử lý: "
                        + result.getClass().getName());
    }

    public static void main(String[] args) {
        for (String rawId : new String[] {"1", "99", "abc"}) {
            System.out.println(
                    rawId + " -> " + describe(findCustomer(rawId)));
        }
    }
}
~~~

Đây là một file Java nguồn tự chứa: `Customer`, `ErrorInfo`, `FindResult` và các kiểu con đều nằm trong lớp bao `SealedResultDemo`. `Map.of(...)` cung cấp dữ liệu nhỏ để chạy được mà không phải thiết lập cơ sở dữ liệu.

### 3.3. Biên dịch và chạy với JDK 17

Từ thư mục gốc chứa `src/demo/SealedResultDemo.java`:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/SealedResultDemo.java
java -cp out demo.SealedResultDemo
~~~

Tham số `--release 17` yêu cầu Java compiler nhắm tới ngôn ngữ, API và bytecode Java 17. `-encoding UTF-8` cho biết mã hóa của file nguồn. `-d out` đặt các file `.class` vào thư mục đầu ra; `java -cp out` chạy lớp theo tên package đầy đủ.

Kết quả mong đợi:

~~~text
1 -> Tìm thấy: An (#1)
99 -> Thất bại [NOT_FOUND]: Không tìm thấy khách hàng
abc -> Thất bại [INVALID_ID]: ID phải là số nguyên dương
~~~

Khi muốn kiểm thử các tình huống khác, có thể thay mảng trong `main` thành `{"2", "0", "-3", " 1 ", "99999999999999999"}`; phương thức `findCustomer` vẫn luôn trả về một trong hai kiểu hợp lệ. Mã ID quá lớn cho `int` được xử lý qua `NumberFormatException` thành `INVALID_ID`.

## 4. Bất biến và ý nghĩa của từng kiểu kết quả

Thiết kế ở ví dụ mang những bất biến sau:

| Kiểu | Dữ liệu bắt buộc | Bất biến |
| --- | --- | --- |
| `Found` | `Customer` | Khách hàng khác `null` |
| `Failed` | `ErrorInfo` | Thông tin lỗi khác `null` |
| `Customer` | `id`, `name` | ID dương; tên khác `null` và không trống |
| `ErrorInfo` | `code`, `message` | Mã lỗi khác `null`; thông báo không rỗng |

Các compact constructor của record thực hiện kiểm tra khi đối tượng được tạo:

~~~java
public record Found(Customer customer) implements FindResult {
    public Found {
        Objects.requireNonNull(customer, "customer");
    }
}
~~~

Nhờ đó, không thể tạo trạng thái `new Found(null)` mà không nhận ngoại lệ ngay tại constructor. Phương thức xử lý kết quả không cần kiểm tra lại tính tồn tại của khách hàng sau khi đã xác nhận kiểu `Found`.

Đừng nhầm **đóng hệ phân cấp** với **chứng minh mọi bất biến của miền dữ liệu**. Compiler đảm bảo `Found` và `Failed` là những kiểu kế thừa trực tiếp hợp lệ; còn điều kiện như ID phải dương là trách nhiệm của constructor hoặc quy tắc tạo đối tượng.

Có thể giới hạn constructor, sử dụng factory method hoặc đặt các record trong phạm vi package/module phù hợp nếu cần kiểm soát vị trí được phép tạo kết quả. Mức độ đóng gói tùy yêu cầu API.

## 5. Xử lý kết quả bằng pattern matching cho `instanceof`

Cú pháp:

~~~java
if (result instanceof Found found) {
    System.out.println(found.customer().name());
}
~~~

vừa kiểm tra kiểu, vừa tạo biến đã ép kiểu an toàn trong phạm vi nhánh. Đây là **pattern matching for `instanceof`**, tính năng ổn định và dùng được trong Java 17 không cần preview.

Với mô hình kết quả, nên xử lý từng biến thể tường minh:

~~~java
static void printResult(SealedResultDemo.FindResult result) {
    if (result instanceof SealedResultDemo.Found found) {
        System.out.println("Tên: " + found.customer().name());
    } else if (result instanceof SealedResultDemo.Failed failed) {
        System.out.println("Mã lỗi: " + failed.error().code());
    } else {
        throw new IllegalStateException(
                "Chưa hỗ trợ kiểu " + result.getClass().getName());
    }
}
~~~

**Lưu ý riêng về Java 17:** Chuỗi `if`/`else if` không được compiler chứng minh là bao phủ mọi biến thể của sealed hierarchy. Khi thêm một kiểu mới vào `permits`, những chuỗi `if` cũ không nhất thiết sinh lỗi biên dịch. Nhánh dự phòng giúp tránh im lặng bỏ qua một trường hợp mới, nhưng vẫn cần cập nhật mọi nơi xử lý kết quả khi API thay đổi.

**Pattern matching for `switch`** trong Java 17 mới ở trạng thái *preview*, chưa phải tính năng ổn định của bản phát hành này. Nếu mục tiêu là source code Java 17 ổn định, có thể dùng `instanceof` như trên hoặc thiết kế phương thức xử lý rõ ràng trong các kiểu con. Không lấy cú pháp `switch` của Java 21 trở lên làm ví dụ Java 17 rồi bỏ qua yêu cầu preview.

## 6. Mô hình các biến thể thất bại với `sealed` lồng nhau

Một enum mã lỗi phù hợp nếu mọi lỗi có cấu trúc tương tự. Tuy nhiên, nhiều nghiệp vụ cần những **loại lỗi mang dữ liệu khác nhau**:

- Giỏ hàng không hợp lệ: cần thông báo về lý do sai.
- Số dư không đủ: cần số tiền phải trả và số dư hiện có.
- Thanh toán thành công: cần mã biên nhận.

Khi đó, dùng sealed hierarchy hai tầng sẽ diễn đạt tốt hơn:

~~~java
sealed interface CheckoutResult
        permits Paid, CheckoutFailure {
}

record Paid(String receiptId) implements CheckoutResult {
}

sealed interface CheckoutFailure extends CheckoutResult
        permits InvalidCart, InsufficientFunds {
}

record InvalidCart(String reason) implements CheckoutFailure {
}

record InsufficientFunds(long required, long available)
        implements CheckoutFailure {
}
~~~

Sơ đồ:

~~~text
CheckoutResult (sealed)
├── Paid(receiptId) (record)
└── CheckoutFailure (sealed)
    ├── InvalidCart(reason) (record)
    └── InsufficientFunds(required, available) (record)
~~~

`CheckoutFailure` là kiểu **sealed**, vì vẫn cho phép hai kiểu con trực tiếp. Cả ba kiểu record là những “lá” cuối cùng của hệ phân cấp. Trên thực tế, cũng nên bổ sung kiểm tra constructor: mã biên nhận không rỗng, nội dung lỗi không rỗng, số tiền không âm, và với `InsufficientFunds` cần xác định rõ quan hệ giữa `required` và `available` theo quy tắc nghiệp vụ.

Thiết kế này giúp từng nơi xử lý yêu cầu có dữ liệu chính xác:

~~~java
static String message(CheckoutResult result) {
    if (result instanceof Paid paid) {
        return "Thanh toán thành công: " + paid.receiptId();
    }
    if (result instanceof InvalidCart invalid) {
        return "Giỏ hàng không hợp lệ: " + invalid.reason();
    }
    if (result instanceof InsufficientFunds insufficient) {
        return "Thiếu "
                + (insufficient.required() - insufficient.available())
                + " đơn vị tiền";
    }
    throw new IllegalStateException("Kết quả chưa được hỗ trợ");
}
~~~

Dù `InvalidCart` và `InsufficientFunds` không trực tiếp implement `CheckoutResult` mà đi qua `CheckoutFailure`, cả hai vẫn là các trường hợp hợp lệ của `CheckoutResult`. Cách phân cấp này đáng dùng khi các lý do thất bại có dữ liệu và hành vi khác nhau, hoặc khi cần biểu diễn nhóm lỗi bằng một kiểu riêng.

Không nên dùng `non-sealed` cho nhánh thất bại nếu chủ đích là **liệt kê toàn bộ biến thể hợp lệ**: `non-sealed` cho phép tiếp tục mở rộng nhánh đó bằng những kiểu con mới và làm mất tính đóng của phần cây bên dưới.

## 7. Tái sử dụng qua mô hình generic `Result<T>`

Nếu nhiều thao tác có cùng hai dạng kết quả, thay vì định nghĩa lại `Found`/`Failed` ở mọi nơi, có thể tạo kiểu generic. Ví dụ này là một mẫu thiết kế độc lập, khác với lớp `SealedResultDemo` phía trên:

~~~java
import java.util.Objects;

record Problem(String code, String message) {
    public Problem {
        Objects.requireNonNull(code, "code");
        Objects.requireNonNull(message, "message");
        if (code.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException("Thông tin lỗi không hợp lệ");
        }
    }
}

sealed interface Result<T> permits Result.Ok, Result.Err {

    record Ok<T>(T value) implements Result<T> {
        public Ok {
            Objects.requireNonNull(value, "value");
        }
    }

    record Err<T>(Problem problem) implements Result<T> {
        public Err {
            Objects.requireNonNull(problem, "problem");
        }
    }
}
~~~

Ví dụ khai báo và sử dụng:

~~~java
Result<String> success = new Result.Ok<>("Đã lưu");
Result<String> failure =
        new Result.Err<>(new Problem("CONFLICT", "Dữ liệu đã tồn tại"));

if (success instanceof Result.Ok<?> ok) {
    System.out.println(ok.value());
}
~~~

Phép kiểm tra `instanceof Result.Ok<?>` xác nhận biến thể `Ok` mà không giả định có thể kiểm tra tham số generic `String` tại runtime. Do **type erasure**, kiểu tham số không tự trở thành thông tin định danh đáng tin cậy ở runtime. Để triển khai API chuyển đổi giá trị `T` an toàn và thuận tiện hơn, có thể bổ sung các phương thức `map`, `flatMap` hoặc `fold` với chữ ký generic rõ ràng.

Điểm hữu ích của `Result<T>` là **kiểu dữ liệu thành công** thay đổi theo thao tác, nhưng cấu trúc thành công/thất bại vẫn nhất quán:

~~~java
Result<Customer> customerResult;
Result<Integer> countResult;
Result<String> messageResult;
~~~

Tuy vậy, một kiểu `Problem` chung dễ trở nên quá rộng: người gọi có thể phải tự diễn giải chuỗi mã lỗi. Khi biến thể lỗi có ý nghĩa nghiệp vụ riêng và dữ liệu khác nhau, chọn hierarchy riêng như `CheckoutFailure` thường rõ ràng hơn.

## 8. Chọn `sealed`, `enum`, `Optional`, exception hay kiểu trả về khác?

| Công cụ | Nên dùng khi | Giới hạn cần chú ý |
| --- | --- | --- |
| `sealed interface` + `record` | Có số lượng biến thể được kiểm soát, mỗi biến thể có dữ liệu riêng | Cần định nghĩa và duy trì hierarchy |
| `enum` | Tập giá trị tên cố định và ít dữ liệu riêng theo từng trường hợp | Không thể gắn record component riêng cho từng hằng như một kiểu con |
| `Optional<T>` | Kết quả chỉ là có hoặc không có giá trị, không cần giải thích vì sao vắng mặt | Không mô tả chi tiết nguyên nhân |
| Ngoại lệ | Lỗi lập trình, vi phạm tiền điều kiện, hỏng hạ tầng hoặc luồng xử lý ngoại lệ phù hợp | Không nên dùng thay mọi kết quả nghiệp vụ dự kiến |
| Một `record` chứa `success` và nhiều trường nullable | Tương tác nhanh với một định dạng ngoại vi bắt buộc | Cho phép nhiều trạng thái mâu thuẫn nếu không kiểm tra nghiêm ngặt |

Ví dụ, tra cứu cache và không có giá trị có thể trả về `Optional<Value>`; nhưng đăng ký tài khoản có các lỗi như email đã được sử dụng, tên không hợp lệ, chưa đủ điều kiện… thì một tập kiểu thất bại có tên sẽ diễn đạt tốt hơn.

Cần phân biệt **thất bại nghiệp vụ dự kiến** (ví dụ mã khách hàng không tồn tại) với **lỗi bất thường** (ví dụ dữ liệu bị hỏng, mất kết nối cơ sở dữ liệu, cấu hình thiếu). Có thể chuyển một số lỗi hạ tầng thành biến thể thất bại nếu hợp đồng API thực sự yêu cầu như vậy, nhưng không nên bắt mọi `RuntimeException` rồi trả về một `Failed("UNKNOWN")` khiến lỗi lập trình bị che khuất.

## 9. Thiết kế hợp đồng API và tránh trạng thái không hợp lệ

Khi xây dựng mô hình sealed cho một phương thức, có thể đi theo trình tự:

1. **Liệt kê kết cục nghiệp vụ có ý nghĩa.** Ví dụ: `Created`, `AlreadyExists`, `ValidationFailed`; không bắt đầu từ các trường `boolean` sẵn có.
2. **Xác định dữ liệu riêng cho mỗi kết cục.** `Created` cần ID mới, `AlreadyExists` có thể cần ID trùng, `ValidationFailed` cần danh sách lỗi nhập liệu.
3. **Chọn tầng phân loại.** Nếu chỉ có thành công/thất bại với lỗi cùng cấu trúc, dùng hai record. Nếu mỗi lỗi có payload riêng, dùng thêm `sealed` cho nhánh lỗi.
4. **Ràng buộc bất biến tại điểm tạo.** Kiểm tra null, chuỗi trống, số âm; sao chép collection đầu vào bằng `List.copyOf` nếu cần.
5. **Định nghĩa cách xử lý bên nhận.** Đọc được mọi biến thể có chủ đích, có đường xử lý rõ ràng cho trường hợp chưa được hỗ trợ.
6. **Xem xét mức ổn định của hierarchy.** Việc thêm một biến thể mới là thay đổi quan trọng đối với bên tiêu thụ API vì họ có thể cần xử lý thêm một trường hợp.

Ví dụ với lỗi kiểm tra nhập liệu, một danh sách lỗi cần được sao chép phòng vệ:

~~~java
import java.util.List;
import java.util.Objects;

record ValidationFailed(List<String> errors) {
    public ValidationFailed {
        Objects.requireNonNull(errors, "errors");
        errors = List.copyOf(errors);
        if (errors.isEmpty()) {
            throw new IllegalArgumentException(
                    "Phải có ít nhất một lỗi kiểm tra");
        }
    }
}
~~~

`List.copyOf` tạo bản sao không thể sửa qua reference trả về, đồng thời từ chối phần tử `null`; nhờ vậy không thể sửa nội dung `errors` qua danh sách đầu vào sau khi tạo record.

**Lưu ý về mô hình đóng:** Sealed ngăn **kiểu mới triển khai trực tiếp** ngoài danh sách cho phép. Nó không tự bảo đảm toàn bộ hệ thống không có trạng thái lỗi, không đảm bảo xử lý hết biến thể bằng một chuỗi `if`, và không thay thế việc kiểm chứng bất biến của từng payload.

## 10. Kết hợp sealed với cách tổ chức mã nguồn

Trong dự án thực tế, có thể đặt các kiểu kết quả gần ca sử dụng mà chúng mô tả:

~~~text
src/main/java/
└── vn/example/customer/
    ├── Customer.java
    ├── CustomerService.java
    └── FindCustomerResult.java
~~~

Ví dụ một file `FindCustomerResult.java` đặt interface và các record trực tiếp bên trong để giữ các biến thể gần nhau:

~~~java
package vn.example.customer;

import java.util.Objects;

public sealed interface FindCustomerResult
        permits FindCustomerResult.Found,
                FindCustomerResult.NotFound {

    record Found(Customer customer) implements FindCustomerResult {
        public Found {
            Objects.requireNonNull(customer, "customer");
        }
    }

    record NotFound(int requestedId) implements FindCustomerResult {
        public NotFound {
            if (requestedId <= 0) {
                throw new IllegalArgumentException("ID phải dương");
            }
        }
    }
}
~~~

Với cách viết này, người dùng API có thể tham chiếu `FindCustomerResult.Found` và `FindCustomerResult.NotFound`. Hai record được lồng trong interface là member types; record vốn `final`. Nếu muốn có kiểu lỗi `InvalidId`, thêm vào danh sách `permits` và định nghĩa record tương ứng.

Nếu một module cung cấp public API cho các module khác, việc giữ một hợp đồng kết quả rõ ràng giúp hạn chế sai lệch khi chuyển qua tầng service, controller hay adapter. Nhưng thay đổi thêm/bớt các biến thể được phép cần được coi là thay đổi hợp đồng API và có kế hoạch tương thích.

### Lưu ý khi tuần tự hóa

Nhiều API trả kết quả ra JSON. JSON chỉ là dữ liệu, không có khái niệm Java `sealed`. Nếu cần trao đổi qua mạng, nên thiết kế một **discriminator** tường minh như `"type": "found"`, `"type": "not_found"` hoặc `"type": "invalid_id"`, kết hợp schema/validation của giao thức. Cơ chế mapping Java ↔ JSON phụ thuộc thư viện, không tự động được bảo đảm bởi `sealed`.

Tương tự, record và sealed là lựa chọn tốt cho **domain model** bên trong ứng dụng, nhưng DTO công khai cần được thiết kế theo hợp đồng API thực tế. Không nên để định dạng JSON vô tình phụ thuộc vào tên lớp Java hoặc chi tiết package.

## 11. Bài tập thực hành

1. Sửa `SealedResultDemo`: thêm mã `CUSTOMER_INACTIVE` vào `ErrorCode`, bổ sung một khách hàng bị vô hiệu hóa và trả về `Failed` đúng mã khi tra cứu.
2. Tách `Failed` thành hai record `InvalidId` và `NotFound` trực tiếp implement `FindResult`. Cập nhật `permits`, phương thức tìm kiếm và các nhánh xử lý.
3. Thiết kế `OrderResult` có `Placed(orderId)`, `Rejected(reason)` và `Pending(retryAfterSeconds)`. Đặt kiểm tra để `orderId` không rỗng và `retryAfterSeconds` dương.
4. Chuyển mô hình từ các kiểu riêng sang `Result<T>` generic; xác định điểm nào thuận tiện hơn và điểm nào làm mất thông tin nghiệp vụ.
5. Thêm một biến thể mới vào `permits` rồi quan sát các nhánh `if` cũ. Giải thích vì sao Java 17 cần xử lý cập nhật thủ công hoặc nhánh dự phòng thay vì mặc định compiler báo mọi trường hợp còn thiếu.

Một mô hình kết quả tốt phải khiến người đọc nhận ra ngay **những kết cục nào có thể xảy ra, mỗi kết cục chứa dữ liệu gì, và trạng thái nào bị loại ngay từ lúc tạo đối tượng**. Trong Java 17, `sealed` xác định tập biến thể, `record` diễn đạt dữ liệu của từng biến thể, còn constructor và logic ứng dụng giữ các bất biến nghiệp vụ.
