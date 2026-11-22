# Ném ngoại lệ có thông điệp và ngữ cảnh phù hợp trong Java

Lệnh `throw` thông báo rằng thao tác **không thể tiếp tục như hợp đồng đã cam kết**. Tuy nhiên, chỉ ném đúng loại ngoại lệ vẫn chưa đủ: nếu thông điệp quá chung chung, thiếu thông tin về thao tác và nguyên nhân, người đọc log hoặc người gọi API sẽ rất khó xác định phải sửa điều gì.

Ví dụ:

```java
throw new IllegalArgumentException("Invalid");
```

Người đọc chỉ biết “không hợp lệ”, nhưng không biết **tham số nào**, **quy tắc nào** hoặc **đang thực hiện thao tác nào**. Thông điệp tốt hơn là:

```java
throw new IllegalArgumentException(
        "field=quantity: must be a positive integer");
```

Đây là **các câu lệnh minh họa**, không phải chương trình độc lập. Với dữ liệu đầu vào sai, câu thứ hai cho người xử lý biết tên trường và điều kiện vi phạm mà không phải tiết lộ giá trị đầu vào.

Nguyên tắc xuyên suốt: **chọn kiểu ngoại lệ đúng bản chất lỗi; viết thông điệp mô tả thất bại có thể hành động; đưa ngữ cảnh cần thiết ở tầng có đủ thông tin; giữ nguyên nhân gốc khi chuyển ngoại lệ; hạn chế dữ liệu nhạy cảm**.

## 1. `throw` làm gì và thông điệp đóng vai trò gì?

Trong Java, `throw` là câu lệnh ném một giá trị có kiểu `Throwable` hoặc một lớp con; thực tế ta thường ném một đối tượng `Exception` hay `RuntimeException` cụ thể:

```java
static int requirePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "value must be greater than zero");
    }
    return value;
}
```

Đây là một **phương thức minh họa**, cần đặt trong lớp Java để biên dịch. Khi `value <= 0`:

1. Đối tượng `IllegalArgumentException` được tạo với thông điệp `"value must be greater than zero"`.
2. `throw` làm phương thức hoàn tất bất thường tại câu lệnh này; `return` không được chạy.
3. JVM tìm `catch` phù hợp trong chuỗi lời gọi đang hoạt động.
4. Nếu người gọi bắt được ngoại lệ, `ex.getMessage()` cung cấp thông điệp; `ex.getClass()` cung cấp kiểu để phân loại.

**Thông điệp không phải kiểu ngoại lệ.** Một chuỗi có nội dung `"IOException"` bên trong `IllegalArgumentException` không biến ngoại lệ đó thành `IOException`. Handler được chọn theo kiểu thực tế của đối tượng và quan hệ kế thừa, không theo nội dung chuỗi.

Phân biệt ba thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Kiểu ngoại lệ | Loại thất bại và nhánh `catch` có thể xử lý | `IllegalArgumentException` |
| Thông điệp (`message`) | Mô tả ngắn gọn điều kiện hoặc thao tác thất bại | `"field=quantity: must be positive"` |
| Nguyên nhân (`cause`) | Liên kết tới ngoại lệ gốc khi lỗi được chuyển đổi hoặc bổ sung ngữ cảnh | `NumberFormatException` bên trong `IllegalArgumentException` |

Ngoài ra, đối tượng `Throwable` thường mang stack trace và có thể chứa các ngoại lệ bị *suppressed* trong quá trình dọn tài nguyên. Một lỗi có thể có **message tốt nhưng cause bị mất**, hoặc cause đầy đủ nhưng message thiếu ngữ cảnh; hai vấn đề cần được giải quyết riêng.

## 2. Thông điệp tốt nên trả lời những câu hỏi nào?

Một thông điệp hữu ích thường giúp nhận ra:

- **Điều gì thất bại?** Ví dụ: chuyển đổi trường `quantity`, tải cấu hình, tạo đơn hàng.
- **Điều kiện nào không được đáp ứng?** Ví dụ: phải là số nguyên dương, tệp bắt buộc không tồn tại, trạng thái hiện tại chưa cho phép chuyển bước.
- **Ngữ cảnh nào giúp xác định lần thất bại?** Ví dụ: một mã tác vụ nội bộ không nhạy cảm, tên thao tác, tên trường, tên cấu hình.
- **Người nhận có thể hành động gì?** Ví dụ: sửa trường nhập, bổ sung cấu hình, kiểm tra kết nối. Không phải mọi ngoại lệ đều cần đưa hướng dẫn cho người dùng cuối.

Ví dụ so sánh:

| Thông điệp mơ hồ | Thông điệp có ích hơn | Lý do |
| --- | --- | --- |
| `"Error"` | `"field=port: must be between 1 and 65535"` | Nêu trường và điều kiện |
| `"Bad input"` | `"field=quantity: expected a positive integer"` | Cho biết quy tắc dữ liệu |
| `"Cannot continue"` | `"order transition rejected: expected status DRAFT"` | Nêu trạng thái mong đợi |
| `"Failed"` | `"configuration loading failed: resource=app-settings"` | Nêu thao tác và định danh tài nguyên an toàn |
| `"null"` | `"required dependency 'paymentGateway' was not configured"` | Chỉ ra phụ thuộc bị thiếu |

Các câu trên chỉ minh họa cấu trúc thông điệp; tên trường, giới hạn và trạng thái phải phản ánh **hợp đồng thật** của ứng dụng. Không nên phát minh một quy tắc “1–65535” nếu ứng dụng dùng một tập cổng nhỏ hơn, hay phát biểu “không tồn tại” khi API chỉ báo “không thể đọc”.

### Nên mô tả *sự thật quan sát được*

Nếu `Files.readString(path)` báo `IOException`, chưa chắc nguyên nhân là tệp không tồn tại. Có thể thiếu quyền, lỗi thiết bị hoặc một sự cố I/O khác. Vì vậy thông điệp `"failed to read configuration"` chính xác hơn `"file does not exist"` trừ khi đã xác định đúng loại `NoSuchFileException`.

Tương tự, `NumberFormatException` cho biết không thể diễn giải chuỗi theo cú pháp số được yêu cầu; `Integer.parseInt` còn có thể ném nó khi số vượt khỏi phạm vi `int`. Thông điệp `"must fit into a signed 32-bit integer"` chỉ nên dùng khi hợp đồng cần ràng buộc ấy.

### Dùng từ ngữ ổn định, súc tích

Thông điệp nên đủ ngắn để đọc trong log, đủ cụ thể để phân tích. Có thể nhất quán theo mẫu:

```text
operation=<operation>, field=<field>: <violated condition>
```

hoặc viết câu tự nhiên dễ hiểu. Mẫu chỉ là gợi ý; Java không áp đặt định dạng `message`. Điều quan trọng hơn là **không thay đổi ý nghĩa lỗi qua các tầng**.

## 3. Lỗi ở đâu thì ném ở đó; thông tin ở tầng nào thì bổ sung tại tầng đó

Một hàm chuyển chuỗi thành số biết dữ liệu cần là số nguyên dương; nó **không tự biết** chuỗi đang dùng cho đơn hàng nào. Tầng nghiệp vụ gọi hàm có thể biết mã đơn và tên trường. Phân chia trách nhiệm giúp tránh đẩy quá nhiều tham số chỉ để phục vụ thông báo lỗi.

```text
submitOrder(orderId, rawQuantity)
  └── parseQuantity(rawQuantity)
       ├── biết quy tắc “bắt buộc có dữ liệu”
       ├── biết quy tắc “phải là số nguyên”
       └── biết quy tắc “phải lớn hơn 0”
  └── biết đây là trường quantity của orderId
       └── bổ sung bối cảnh và giữ cause khi chuyển lỗi
```

Nhờ đó:

- Tầng thấp ném một lỗi mô tả **quy tắc bị vi phạm**.
- Tầng gọi thêm **bối cảnh hoạt động** mà nó chắc chắn biết.
- Tầng giao tiếp có thể chuyển lỗi thành phản hồi thân thiện cho người dùng; tầng log có thể lưu thông tin điều tra theo chính sách.

Không phải lúc nào cũng cần bọc ngoại lệ ở từng tầng. Nếu một ngoại lệ đã đủ rõ và người gọi không có thêm thông tin hữu ích, cứ để nó lan truyền sẽ đơn giản hơn.

## 4. Ví dụ Java 17+ hoàn chỉnh: thông điệp, ngữ cảnh và nguyên nhân

Chương trình dưới đây mô phỏng xử lý số lượng đặt hàng, không cần file hay dịch vụ ngoài. Tên đơn hàng trong ví dụ là **định danh giả lập, được coi là an toàn để đưa vào thông điệp**. Trong ứng dụng thực, cần xét tính nhạy cảm của từng định danh.

Lưu thành tệp **`ThrowWithContextDemo.java`**:

```java
public class ThrowWithContextDemo {

    static final class OrderValidationException extends RuntimeException {
        OrderValidationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static int parseQuantity(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "quantity is required");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException(
                    "quantity must be an integer", cause);
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return quantity;
    }

    static void submitOrder(String orderId, String rawQuantity) {
        try {
            int quantity = parseQuantity(rawQuantity);
            System.out.println(
                    "OK order=" + orderId + ", quantity=" + quantity);
        } catch (IllegalArgumentException cause) {
            throw new OrderValidationException(
                    "order=" + orderId
                    + ", field=quantity: " + cause.getMessage(),
                    cause);
        }
    }

    static void runCase(String orderId, String rawQuantity) {
        try {
            submitOrder(orderId, rawQuantity);
        } catch (OrderValidationException ex) {
            System.out.println("ERROR " + ex.getMessage());

            Throwable root = ex;
            while (root.getCause() != null) {
                root = root.getCause();
            }
            System.out.println(
                    "ROOT " + root.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        runCase("A-1", "2");
        runCase("A-2", "abc");
        runCase("A-3", "0");
        runCase("A-4", null);
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ThrowWithContextDemo.java
java ThrowWithContextDemo
```

**Stdout chính xác**:

```text
OK order=A-1, quantity=2
ERROR order=A-2, field=quantity: quantity must be an integer
ROOT NumberFormatException
ERROR order=A-3, field=quantity: quantity must be positive
ROOT IllegalArgumentException
ERROR order=A-4, field=quantity: quantity is required
ROOT IllegalArgumentException
```

### Phân tích ba kiểu thất bại

**Chuỗi `"abc"`:** `Integer.parseInt("abc")` ném `NumberFormatException`. `parseQuantity` bắt lỗi đó và ném `IllegalArgumentException("quantity must be an integer", cause)`. `submitOrder` bổ sung ngữ cảnh `order=A-2, field=quantity` bằng `OrderValidationException`, vẫn giữ toàn bộ chuỗi nguyên nhân. Tầng ngoài có thể xem message dành cho nghiệp vụ hoặc đi theo `getCause()` để phân tích sâu.

**Chuỗi `"0"`:** chuyển đổi số thành công nhưng `quantity <= 0` sai hợp đồng. Không có `NumberFormatException`; lỗi gốc là `IllegalArgumentException` về điều kiện nghiệp vụ. Message nêu “must be positive”. Vì vậy chỉ dựa vào kiểu gốc `IllegalArgumentException` là chưa đủ để phân biệt mọi quy tắc; thông điệp và/hoặc thuộc tính lỗi có cấu trúc có thể bổ sung ngữ nghĩa.

**`null`:** điều kiện `raw == null || raw.isBlank()` có **short-circuit**, nên khi `raw == null`, lời gọi `raw.isBlank()` không chạy và không phát sinh `NullPointerException`. Thông điệp nêu rõ trường được yêu cầu. Đây là lựa chọn hợp đồng của ví dụ; một API khác có thể ưu tiên `NullPointerException` cho tham số bắt buộc không `null`.

### Điểm cần lưu ý trong cách bọc lỗi

`submitOrder` có nhiệm vụ thêm định danh đơn và trường dữ liệu nên có lý do bọc lỗi. Trong một API lớn, thông thường không nên tạo một wrapper mới ở *mọi* phương thức, vì chuỗi `Caused by` quá dài có thể làm việc chẩn đoán trở nên ồn ào.

Ví dụ cũng **không in rawQuantity khi dữ liệu sai**. Trong mã thực tế, chuỗi đầu vào có thể chứa thông tin không nên đưa vào log. Nếu cần nhận diện lần xử lý cụ thể, hãy dùng mã yêu cầu/tác vụ được cho phép thay vì đưa toàn bộ dữ liệu người dùng vào message.

## 5. Cách giữ cause khi dùng `throw new ...`

Một phương thức bắt lỗi ở tầng thấp có thể muốn chuyển nó sang loại ngoại lệ phù hợp với hợp đồng tầng trên.

### Cách làm thiếu thông tin

```java
try {
    readConfiguration();
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Cannot initialize service");
}
```

Đây là mã **minh họa trong một phương thức**, giả định `readConfiguration()` được định nghĩa và có thể ném `IOException`. Mã này tạo lỗi mới nhưng **không giữ quan hệ cause** tới `IOException` đã bắt. Khi lỗi được điều tra, nguyên nhân gốc có thể bị mất khỏi chuỗi ngoại lệ.

### Cách làm giữ nguyên nhân

```java
try {
    readConfiguration();
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Cannot initialize service: configuration loading failed",
            cause);
}
```

Constructor `(String message, Throwable cause)` của `IllegalStateException` giúp tạo thông điệp ở tầng ứng dụng và bảo toàn `cause`. Caller có thể đọc:

```java
Throwable rootCause = failure.getCause();
```

Câu lệnh này chỉ minh họa; `failure` cần là một biến ngoại lệ có thật, và `getCause()` có thể trả về `null`. Muốn theo toàn bộ chuỗi nguyên nhân, phải duyệt cho đến khi không còn cause; nếu có API nhận dữ liệu không đáng tin hoặc ngoại lệ tùy chỉnh, mã điều tra cũng cần đề phòng chuỗi cause bất thường.

**Một lỗi nên có trách nhiệm rõ giữa các tầng:** tầng đọc file thông báo thao tác I/O thất bại; tầng khởi tạo ứng dụng có thể thêm “không thể khởi tạo dịch vụ”; tầng ngoài quyết định phản hồi hoặc dừng ứng dụng. Nhiều wrapper liên tiếp cùng thông điệp `"failed"` không giúp chẩn đoán tốt hơn.

### Có cần luôn chuyển checked exception thành unchecked?

Không. Nếu người gọi có khả năng phục hồi lỗi đọc cấu hình/tệp, để phương thức khai báo `throws IOException` và truyền `IOException` lên có thể đúng hơn. Bọc sang `IllegalStateException` chỉ nên làm khi tầng hiện tại thật sự muốn coi việc mất cấu hình là **trạng thái hệ thống không thể đáp ứng hợp đồng**.

Ngoại lệ checked cần được xử lý hoặc khai báo đúng luật Java; `throw new IOException(...)` từ một phương thức không khai báo và không tự bắt checked exception sẽ gây lỗi biên dịch (trừ những trường hợp đặc biệt được ngôn ngữ cho phép). `IllegalArgumentException` và `IllegalStateException` là unchecked exception, nên không bắt buộc khai báo `throws`.

## 6. Thông điệp và ngữ cảnh: phần nào đặt ở đâu?

Không phải tất cả ngữ cảnh đều cần nằm trong một chuỗi message. Khi hệ thống lớn dần, nên tách những thông tin có mục đích khác nhau:

| Loại thông tin | Nơi phù hợp | Ví dụ |
| --- | --- | --- |
| Nguyên nhân có thể hành động | Message của ngoại lệ | `"field=age: must be non-negative"` |
| Loại lỗi để chương trình phân nhánh | Kiểu ngoại lệ hoặc mã/thuộc tính có cấu trúc | `InvalidOrderException`, `ErrorCode.INVALID_QUANTITY` |
| Nguyên nhân từ thư viện khác | `Throwable cause` | `NumberFormatException`, `IOException` |
| Định danh vận hành an toàn | Log có cấu trúc hoặc context theo request | Mã tác vụ nội bộ, correlation ID |
| Stack trace | Bản thân `Throwable` và hệ thống log | Nơi tạo/lời gọi khi lỗi được ném |
| Thông báo cho người dùng cuối | Tầng giao diện hoặc API | `"Số lượng phải lớn hơn 0."` |

Ví dụ, ngoại lệ có thông điệp `"Cannot finalize order: status must be PAID"`; tầng API có thể hiển thị một câu tiếng Việt thân thiện; tầng log giữ kiểu ngoại lệ, thời điểm, tên thao tác, mã yêu cầu và chuỗi nguyên nhân. Không nên mặc định dùng nguyên văn `ex.getMessage()` làm nội dung HTTP trả cho khách hàng.

### Khi cần xử lý máy móc, tạo trường dữ liệu có kiểu

Đừng dựa vào:

```java
if (ex.getMessage().contains("quantity")) {
    // Chuyển sang mã lỗi dữ liệu.
}
```

Đây là đoạn minh họa, không phải logic phân loại đáng tin. Message có thể đổi câu chữ hoặc ngôn ngữ, và `getMessage()` có thể là `null`. Nếu bên gọi cần phân biệt lỗi theo cách ổn định, dùng **loại ngoại lệ cụ thể**, **mã lỗi**, hoặc **thuộc tính chuyên biệt**.

Ví dụ một ngoại lệ tùy chỉnh (một lớp cần lưu dưới tên `ValidationException.java`):

```java
public final class ValidationException
        extends IllegalArgumentException {

    private final String field;

    public ValidationException(
            String field, String message, Throwable cause) {
        super(message, cause);
        this.field = field;
    }

    public String getField() {
        return field;
    }
}
```

Khi bắt lỗi, code có thể gọi `ex.getField()` thay vì phân tích chuỗi. Tên trường là một **giá trị dữ liệu có cấu trúc**. Nếu cần mã lỗi ổn định cho API, có thể thêm `enum` hoặc hằng mã theo thiết kế của hệ thống. Không nên tạo nhiều lớp ngoại lệ chỉ khác message nếu cách xử lý hoàn toàn giống nhau.

## 7. Chọn đúng loại ngoại lệ trước khi viết message

Thông điệp hay không thể sửa một kiểu ngoại lệ sai. Một số lựa chọn thường gặp:

| Tình huống | Kiểu ngoại lệ cân nhắc | Thông điệp nên tập trung |
| --- | --- | --- |
| Tham số trái điều kiện của phương thức | `IllegalArgumentException` | Tên tham số và điều kiện mong đợi |
| Tham số không được phép `null` | `NullPointerException` hoặc `IllegalArgumentException` tùy hợp đồng API | Tham số bắt buộc |
| Đối tượng ở trạng thái không cho phép thao tác | `IllegalStateException` | Trạng thái hiện tại và yêu cầu |
| Chuỗi không parse được thành số | `NumberFormatException` hoặc wrapper phù hợp | Tên trường và kiểu định dạng mong đợi |
| Không đọc/ghi được tài nguyên I/O | `IOException` hoặc subclass | Thao tác/tài nguyên và nguyên nhân đã xác minh |
| Một điều kiện nghiệp vụ riêng cần caller phân biệt | Ngoại lệ ứng dụng được đặt tên phù hợp | Quy tắc nghiệp vụ, mã/thuộc tính phân loại |
| Không tìm thấy trong phép tìm kiếm mà vắng mặt là bình thường | Có thể là `Optional.empty()` hoặc tập rỗng | Có thể không cần `throw` |

`Objects.requireNonNull(value, "field must not be null")` là một cách tiện lợi để kiểm tra điều kiện không null; thông điệp được dùng nếu phương thức ném `NullPointerException`. Chỉ dùng nó khi điều kiện và kiểu lỗi phù hợp với hợp đồng.

Đừng dùng `Error` cho lỗi nghiệp vụ. `Error` biểu thị các tình huống hệ thống nghiêm trọng theo thiết kế Java và thường không nên bắt để phục hồi như một lỗi nhập liệu.

## 8. Khi nào đưa giá trị lỗi vào thông điệp?

Dữ liệu đầu vào có thể làm quá trình điều tra nhanh hơn, nhưng việc đưa trực tiếp giá trị vào message có rủi ro:

- Token, mật khẩu, cookie, khóa API, mã xác thực một lần hoặc chuỗi kết nối có thông tin đăng nhập có thể bị lộ.
- Dữ liệu cá nhân, số định danh hoặc nội dung khách hàng có thể bị ghi vào log tồn tại lâu và được nhiều hệ thống sao chép.
- Chuỗi không đáng tin có thể chứa ký tự xuống dòng hoặc ký tự điều khiển, làm log khó đọc, gây **log injection** hoặc làm sai cấu trúc bản ghi.
- Dữ liệu rất dài có thể làm log quá tải; một message kiểu `"invalid input=" + entirePayload` có thể vô tình nhân đôi dữ liệu lớn.
- Message có thể xuất hiện qua stack trace, telemetry, hệ thống báo lỗi hoặc trong phản hồi API nếu tầng ngoài trả nguyên văn.

Với một trường nhạy cảm, thay vì:

```java
throw new IllegalArgumentException(
        "invalid credential: " + credential);
```

hãy dùng:

```java
throw new IllegalArgumentException(
        "credential validation failed");
```

Hai câu lệnh chỉ minh họa; `credential` là biến giả định. Nếu cần điều tra nguyên nhân, dùng mã lỗi/ID sự kiện và ghi thông tin **đã được chọn lọc** ở hệ thống quan sát có phân quyền. Không suy ra rằng “không đưa bí mật vào message” đồng nghĩa có thể ghi nguyên văn bí mật vào log ở nơi khác.

Khi định danh an toàn được đưa vào thông điệp, nên giới hạn độ dài và kiểm soát ký tự hoặc dùng logger có tham số/context có cấu trúc. Không nên viết `"user=" + rawRequestBody` để tiết kiệm công xây dựng ngữ cảnh.

## 9. Đừng dùng message thay cho stack trace hoặc cause

Một số mã bắt rồi biến toàn bộ lỗi thành chuỗi:

```java
try {
    loadData();
} catch (java.io.IOException ex) {
    throw new IllegalStateException(ex.toString());
}
```

Đây là đoạn minh họa, giả định `loadData()` có thể ném `IOException`. `ex.toString()` thường gồm tên lớp và thông điệp, nhưng **không bảo toàn đối tượng cause** nếu chỉ truyền vào constructor nhận `String`.

Cách an toàn hơn:

```java
try {
    loadData();
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Data loading failed", cause);
}
```

Nếu logger nhận một đối tượng `Throwable`, truyền đối tượng lỗi như tham số chuyên dụng theo API logger đang dùng giúp ghi được stack trace và cause. Không nên chỉ in `ex.getMessage()` rồi coi như đã lưu đủ thông tin điều tra.

### `throw ex;` hay `throw new ...(..., ex);`?

- `throw ex;`: ném lại **cùng đối tượng** đã bắt, giữ loại và cause hiện có. Phù hợp khi tầng hiện tại không cần đổi hợp đồng, nhưng có thể đã làm một việc như dọn dẹp.
- `throw new SomeException("context", ex);`: tạo **ngoại lệ mới** với thông điệp bổ sung và cause trỏ đến lỗi gốc; phù hợp khi cần biểu diễn lỗi ở cấp trừu tượng khác.
- `throw new SomeException("context");` sau khi đã bắt một lỗi khác: có nguy cơ đánh mất mối liên hệ nguyên nhân nếu không có cơ chế lưu khác.

Một số đoạn mã dùng `fillInStackTrace()` hoặc tạo ngoại lệ mới chỉ để điều chỉnh vị trí hiển thị stack trace; đừng làm điều này để “che” nguồn lỗi nếu không có nhu cầu đặc biệt và hiểu đầy đủ hệ quả. Stack trace thường phản ánh thời điểm đối tượng ngoại lệ được tạo/khởi tạo stack trace; chuỗi `Caused by` mới cho thấy các nguyên nhân nằm dưới wrapper.

## 10. Logging và trách nhiệm ở từng tầng

Một lỗi có thể đi qua thư viện, service, controller, job scheduler và lớp giao diện. Nếu **mỗi tầng đều in cả stack trace rồi ném tiếp**, hệ thống có thể ghi một sự cố thành nhiều bản log gần như trùng nhau.

Một mô hình thường hợp lý:

1. **Nơi phát hiện:** ném đúng loại lỗi với message nói rõ điều kiện.
2. **Tầng nghiệp vụ:** chỉ bọc lỗi nếu thêm được ngữ cảnh mới hoặc thay đổi hợp đồng; giữ cause. Không bắt chỉ để ghi log y hệt rồi ném.
3. **Tầng giao tiếp hoặc biên tác vụ:** chuyển lỗi thành kết quả/HTTP/status thất bại thích hợp; đây có thể là nơi log lỗi một cách tập trung.
4. **Hệ thống quan sát:** bổ sung mã tương quan, thời gian, tên thao tác, độ nghiêm trọng và các trường được phép ghi.

Trạng thái HTTP, thông báo người dùng và chuỗi message không nhất thiết giống nhau. Chẳng hạn, lỗi thiếu quyền nội bộ cần phản hồi công khai hạn chế thông tin, còn log vận hành được kiểm soát có thể chứa thông tin nguyên nhân sâu hơn.

Tại ranh giới API, đừng hiển thị mọi exception message cho client. Ngoài lộ thông tin, message còn có thể là nội dung kỹ thuật, chưa được bản địa hóa, hoặc thay đổi khi đổi phiên bản thư viện.

## 11. Một phương thức checked exception bổ sung ngữ cảnh ra sao?

Ví dụ sau **chỉ là một phương thức minh họa**, không phải chương trình độc lập. Nó đọc tệp và thêm tên logic của cấu hình trong message nếu gặp lỗi, đồng thời giữ `cause`:

```java
static String readRequiredConfig(
        java.nio.file.Path path, String logicalName)
        throws java.io.IOException {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new java.io.IOException(
                "Cannot read required configuration: " + logicalName,
                cause);
    }
}
```

Ý nghĩa:

- `Files.readString` có thể ném nhiều loại `IOException`; thông điệp wrapper chỉ nói **không đọc được cấu hình**, không tự khẳng định tệp không tồn tại.
- `logicalName` được giả định là **tên nội bộ an toàn**, không phải đường dẫn hay dữ liệu người dùng có chứa bí mật. Nếu không có định danh an toàn, có thể bỏ nó khỏi message.
- Thông tin sâu như `NoSuchFileException` hoặc nguyên nhân I/O khác vẫn có thể có trong `getCause()`.
- Vì vẫn ném `IOException` checked, chữ ký `throws IOException` phù hợp; caller phải tiếp tục khai báo hoặc bắt khi dùng phương thức.
- Nếu API không cần đổi message mà vẫn hữu ích, có thể để ngoại lệ gốc truyền lên và log bối cảnh ở ranh giới thích hợp.

**Không nên thay kiểu ngoại lệ gốc bằng một wrapper quá rộng chỉ để “có thông điệp đẹp”**. Khi caller cần phân biệt `NoSuchFileException` với lỗi I/O khác, bọc mọi thứ trong `IOException` mới có thể làm mất khả năng `catch (NoSuchFileException)` trực tiếp, mặc dù cause còn nguyên. Hãy cân nhắc điều đó trước khi thay đổi hợp đồng kiểu của API.

## 12. Các lỗi thường gặp khi viết `throw`

### A. Thông điệp quá ngắn

```java
throw new IllegalStateException("Invalid state");
```

Thường không đủ bối cảnh. Tốt hơn là nêu **trạng thái hiện tại và trạng thái yêu cầu** nếu cả hai đã biết và được phép hiển thị, chẳng hạn `"cannot submit order: expected DRAFT status"`.

### B. Thông điệp chứa dữ liệu nhạy cảm

```java
throw new IllegalArgumentException(
        "bad password: " + password);
```

Đây là **ví dụ không nên làm**. Không cho mật khẩu xuất hiện trong exception message, dù đối tượng chỉ được ném ở tầng nội bộ; nhiều framework tự động ghi stack trace khi không bắt được lỗi.

### C. Bọc nhưng quên `cause`

```java
catch (java.io.IOException ex) {
    throw new IllegalStateException("Startup failed");
}
```

Nếu chính sách yêu cầu đổi kiểu, hãy dùng constructor truyền `ex` làm nguyên nhân; nếu không cần đổi, có thể để `IOException` đi lên.

### D. Lấy message làm mã lỗi

```java
if ("quantity must be positive".equals(ex.getMessage())) {
    // ...
}
```

Đây là **mã không nên dùng để phân nhánh nghiệp vụ**. Một lần sửa câu chữ có thể thay đổi hành vi. Dùng kiểu ngoại lệ, enum lỗi hoặc thuộc tính cụ thể.

### E. Cứ nhận lỗi là thêm wrapper

Viết `throw new RuntimeException("Failed at A", ex)` trong A, rồi `"Failed at B"` ở B, rồi `"Failed at C"` ở C khiến stack trace dài mà ít thêm nghĩa. Hãy chỉ bọc tại tầng có **ngữ cảnh mới, thật và hữu ích**.

### F. Thông điệp khẳng định nguyên nhân chưa được kiểm chứng

Nếu API ném `IOException`, đừng lập tức viết `"network is offline"` nếu chưa biết chắc. Dùng `"remote operation failed"` rồi để `cause` cung cấp chi tiết kỹ thuật, hoặc phân loại thêm bằng ngoại lệ cụ thể.

### G. Bắt rồi chuyển lỗi thành thành công giả

```java
try {
    return parseRequiredValue();
} catch (RuntimeException ex) {
    return 0;
}
```

Đây là **đoạn minh họa chống mẫu**, giả định phương thức trả về `int`. Nếu `0` hợp lệ, caller không phân biệt thành công với thất bại. Khi hợp đồng không cho phép giá trị dự phòng, phải truyền lỗi có ý nghĩa; nếu `0` là giá trị mặc định hợp lệ theo chính sách, hãy ghi rõ hợp đồng và giới hạn loại lỗi có thể được thay thế.

### H. Thông điệp gây hiểu sai vì cùng lúc báo nhiều tầng

Ví dụ ở tầng parse, viết `"Database server is down"` chỉ vì hàm được gọi trong quy trình lưu dữ liệu là sai nếu lỗi thực sự do nhập sai số. Thông điệp cần bám vào **điều đã được xác minh ở nơi ném**.

## 13. Quy trình thiết kế một ngoại lệ dễ bảo trì

Khi định viết `throw`, có thể áp dụng thứ tự sau:

1. **Định nghĩa điều kiện thất bại.** Đây là lỗi bắt buộc dừng, hay một kết quả vắng mặt hợp lệ? Không ném ngoại lệ chỉ vì một phép tìm kiếm thông thường không trả kết quả.
2. **Chọn kiểu ngoại lệ phù hợp.** Ví dụ `IllegalArgumentException` cho tiền điều kiện tham số, `IllegalStateException` cho trạng thái đối tượng, `IOException` cho thao tác I/O không thành công.
3. **Viết message có thể hành động.** Gọi tên trường hoặc thao tác và điều kiện bị vi phạm. Tránh `"error"`, `"failed"` đơn độc.
4. **Thêm ngữ cảnh đúng tầng.** Nếu cấp gọi có một mã tác vụ an toàn giúp nhận biết lỗi, thêm tại đó hoặc vào log có cấu trúc. Không đoán thông tin mà tầng đó không biết.
5. **Giữ nguyên nhân gốc nếu đổi ngoại lệ.** Dùng constructor nhận `cause`. Kiểm tra hợp đồng của kiểu mới: việc đổi loại không vô tình che đi một nhánh `catch` cần thiết.
6. **Rà soát dữ liệu nhạy cảm.** Message, `cause`, stack trace và log có thể ra khỏi tiến trình. Không cho secret hoặc payload thô vào đó.
7. **Đặt handler ở nơi có thể xử lý.** Bắt tại nơi có thể phục hồi hoặc chuyển thành phản hồi phù hợp; đừng nuốt lỗi trong tầng thấp.
8. **Kiểm thử nhánh thất bại.** Kiểm tra loại ngoại lệ, cause và dữ liệu có cấu trúc; tránh kiểm tra toàn bộ câu message nếu câu chữ không là một phần hợp đồng công khai.

## 14. Bài tập tình huống

**Tình huống 1:** Phương thức nhận tham số `retryCount = -2`, hợp đồng quy định không âm. Nên ném gì?

Có thể dùng:

```java
throw new IllegalArgumentException(
        "retryCount must be non-negative");
```

Lỗi rõ tên tham số và điều kiện. Không cần in chính giá trị nếu nó không giúp ích thêm hoặc có chính sách hạn chế ghi đầu vào.

**Tình huống 2:** Tầng đọc tệp ném `IOException`. Tầng khởi tạo ứng dụng biết rằng tệp là cấu hình bắt buộc nhưng không biết nguyên nhân kỹ thuật. Nên báo ra sao?

Có thể bọc bằng `new IllegalStateException("Service startup failed: required configuration could not be read", cause)` nếu tầng đó quyết định không thể khởi tạo. Giữ `cause`; không khẳng định “tệp không tồn tại” trừ khi có bằng chứng.

**Tình huống 3:** Caller cần biết lỗi do `quantity` hay `price` để trả về lỗi chính xác của từng trường. Có nên kiểm tra `ex.getMessage().contains("quantity")`?

Không. Nếu caller cần phân loại ổn định, hãy cung cấp thuộc tính `field` hoặc một enum/mã lỗi trên ngoại lệ chuyên biệt. Message dành cho người đọc và chẩn đoán, không phải giao thức máy móc dựa trên từ khóa dễ thay đổi.

**Tình huống 4:** Lỗi từ thư viện đã có kiểu và message rất rõ, tầng giữa không có thêm ngữ cảnh. Có nên bọc lỗi một lần nữa cho “đầy đủ” không?

Thường không cần. Cho phép ngoại lệ lan truyền giúp giữ nguyên kiểu, giảm số wrapper và để tầng có trách nhiệm xử lý.

**Tình huống 5:** Exception message ghi nguyên văn yêu cầu có chứa mã xác thực. Hệ thống chỉ in lỗi ở môi trường phát triển. Có an toàn không?

Không nên. Môi trường, logger và chính sách lưu trữ có thể thay đổi; bí mật có thể bị gửi ra telemetry hoặc báo cáo lỗi. Hãy chọn trường ngữ cảnh an toàn từ đầu và giới hạn dữ liệu nhạy cảm trong cả message lẫn log.

**Điểm cần ghi nhớ:** `throw` cho biết **thao tác đã thất bại**; **kiểu ngoại lệ** cho biết lỗi thuộc loại nào; **message** giải thích điều kiện và thao tác thất bại; **cause** giữ dấu nguyên nhân sâu hơn; **ngữ cảnh có cấu trúc và an toàn** giúp truy vết đúng sự kiện. Khi các phần này được thiết kế nhất quán, lỗi dễ xử lý, dễ kiểm thử và dễ điều tra mà không phải để lộ dữ liệu không cần thiết.