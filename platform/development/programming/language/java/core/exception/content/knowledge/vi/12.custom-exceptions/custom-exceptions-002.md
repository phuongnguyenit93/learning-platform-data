# Chọn `extends Exception` hay `extends RuntimeException` khi tạo ngoại lệ tùy chỉnh trong Java

Khi thiết kế một ngoại lệ tùy chỉnh (*custom exception*) trong Java, hai cách khai báo phổ biến là `class MyException extends Exception` và `class MyException extends RuntimeException`. Cả hai đều tạo một loại exception có thể `throw`, `catch`, truyền `cause` và lưu stack trace. Khác biệt quan trọng nhất là **nghĩa vụ kiểm tra lúc biên dịch** của bên gọi:

- **`extends Exception` trực tiếp** (hoặc kế thừa qua một lớp con checked) tạo **checked exception**: mã gọi phải bắt hoặc khai báo khả năng lan truyền exception theo quy tắc **catch-or-declare**.
- **`extends RuntimeException`** tạo **unchecked exception**: mã gọi không bị trình biên dịch buộc bắt hoặc khai báo, dù exception vẫn có thể khiến thao tác thất bại ở runtime.

Đây là quyết định về **hợp đồng API, trách nhiệm của caller, khả năng tiến hóa phần mềm và cách diễn đạt lỗi**, không chỉ là chuyện thêm hay bớt từ khóa `throws`. Không có quy tắc máy móc “lỗi nghiệp vụ thì checked, lỗi kỹ thuật thì unchecked” hoặc “có thể phục hồi thì checked, không thể phục hồi thì unchecked” áp dụng chính xác cho mọi hệ thống.

Bài này trình bày cơ chế ngôn ngữ, tiêu chí lựa chọn theo tình huống, ví dụ Java 17 chạy được, hợp đồng khi kế thừa/override, wrapping và cause, xử lý ở ranh giới ứng dụng, ảnh hưởng tương thích API, kiểm thử và các sai lầm thiết kế thường gặp.

## 1. Nhìn đúng hệ phân cấp `Throwable`

Sơ đồ rút gọn:

```text
java.lang.Throwable
├── java.lang.Error                         (unchecked)
│   └── ...
└── java.lang.Exception
    ├── YourCheckedException                 (checked)
    ├── java.io.IOException                  (checked)
    └── java.lang.RuntimeException           (unchecked)
        ├── YourUncheckedException           (unchecked)
        ├── java.lang.IllegalArgumentException
        └── java.lang.IllegalStateException
```

Phân loại theo Java:

| Lớp gốc của ngoại lệ mới | Phân loại | Caller có bắt buộc `catch` hoặc `throws` không? |
| --- | --- | --- |
| `extends Exception` trực tiếp | Checked | Có, nếu đường gọi có thể phát sinh exception đó |
| `extends SomeCheckedException` | Checked | Có |
| `extends RuntimeException` | Unchecked | Không |
| `extends SomeRuntimeException` | Unchecked | Không |
| `extends Error` | Unchecked | Không, nhưng thường **không** thích hợp cho lỗi nghiệp vụ |
| `extends Throwable` trực tiếp | Checked | Có, nhưng thường không nên vì tách khỏi nhánh `Exception` thông dụng |

Lưu ý: **`RuntimeException` vốn là lớp con của `Exception`**. Vì vậy câu “mọi lớp con của `Exception` đều checked” là sai; ngoại lệ thuộc nhánh `RuntimeException` không chịu bắt buộc catch-or-declare.

Đa số ngoại lệ ứng dụng nên thuộc một trong hai nhánh `Exception` (checked) hoặc `RuntimeException` (unchecked). `Error` được dành chủ yếu cho những điều kiện nghiêm trọng ở mức JVM/hệ thống; không nên chọn nó chỉ để tránh viết `throws`.

## 2. Khác biệt nằm ở **compile time**, không nằm ở khả năng ném tại runtime

Cú pháp khai báo tối thiểu:

```java
class DataImportException extends Exception {
    DataImportException(String message) {
        super(message);
    }
}

class InvalidImportRequestException extends RuntimeException {
    InvalidImportRequestException(String message) {
        super(message);
    }
}
```

Đây là **hai lớp minh họa**, chưa có `main`. Cả hai đều có thể ném:

```java
throw new DataImportException("Không đọc được dữ liệu");
// hoặc ở tình huống khác:
throw new InvalidImportRequestException("Sai tham số");
```

Đây là **hai lựa chọn độc lập**, không đặt liên tiếp trong cùng một luồng mã.

Với checked `DataImportException`, phương thức chứa câu lệnh `throw` phải **bắt hoặc khai báo** nó; nếu không, compiler báo lỗi. Với unchecked `InvalidImportRequestException`, Java không buộc thêm `throws` trong chữ ký. Tuy nhiên cả hai khi được ném đều gây **abrupt completion** của đường thực thi hiện tại và đều tìm handler `catch` tương thích trên call stack.

**Không có chuyện unchecked exception “nhẹ hơn”, “không phải exception thật” hay “không làm chương trình dừng”.** Khác biệt là ràng buộc tĩnh đối với mã gọi; hệ quả runtime vẫn phải được thiết kế xử lý.

## 3. Ví dụ đầy đủ: checked custom exception bắt buộc phải được xử lý

Lưu tệp **`CheckedCustomDemo.java`**:

```java
class MissingConfigException extends Exception {
    MissingConfigException(String message) {
        super(message);
    }
}

public class CheckedCustomDemo {
    static String loadConfig(boolean present)
            throws MissingConfigException {
        if (!present) {
            throw new MissingConfigException(
                    "Thiếu cấu hình bắt buộc");
        }
        return "ready";
    }

    public static void main(String[] args) {
        try {
            System.out.println("Kết quả: " + loadConfig(true));
            System.out.println("Kết quả: " + loadConfig(false));
        } catch (MissingConfigException e) {
            System.out.println("Không thể tiếp tục: " + e.getMessage());
        }
        System.out.println("Đã xử lý ở ranh giới main");
    }
}
```

Biên dịch/chạy Java 17+:

```bash
javac -encoding UTF-8 --release 17 CheckedCustomDemo.java
java CheckedCustomDemo
```

**Stdout chính xác** trên console UTF-8:

```text
Kết quả: ready
Không thể tiếp tục: Thiếu cấu hình bắt buộc
Đã xử lý ở ranh giới main
```

Phân tích:

1. `MissingConfigException extends Exception` nên là **checked**.
2. `loadConfig` có đường `throw new MissingConfigException(...)`, vì vậy khai báo `throws MissingConfigException`.
3. `main` bắt loại đã công bố, quyết định không thực hiện bước nạp tiếp theo, rồi chạy mã sau handler.
4. Khi lần gọi thứ hai ném exception, dòng `System.out.println("Kết quả: " + loadConfig(false))` **không** được in: biểu thức bên phải không hoàn tất.
5. Loại lỗi giúp caller phân biệt thiếu cấu hình với những loại thất bại khác mà API có thể báo.

Nếu bỏ `throws MissingConfigException` khỏi `loadConfig` mà không bắt tại đó, code **không biên dịch**. Nếu bỏ `catch` trong `main` mà không thêm `throws` phù hợp, `main` cũng không biên dịch. `throws` không bắt lỗi; nó chỉ cho phép exception đi tới caller theo hợp đồng.

## 4. Ví dụ đầy đủ: unchecked custom exception không ép caller viết `throws`

Lưu **`UncheckedCustomDemo.java`**:

```java
class InvalidQuantityException extends RuntimeException {
    InvalidQuantityException(String message) {
        super(message);
    }
}

public class UncheckedCustomDemo {
    static int calculateTotal(int quantity, int unitPrice) {
        if (quantity <= 0) {
            throw new InvalidQuantityException(
                    "quantity phải lớn hơn 0");
        }
        return quantity * unitPrice;
    }

    public static void main(String[] args) {
        System.out.println("Hợp lệ: " + calculateTotal(2, 50));

        try {
            calculateTotal(0, 50);
            System.out.println("Không tới dòng này");
        } catch (InvalidQuantityException e) {
            System.out.println("Không hợp lệ: " + e.getMessage());
        }

        System.out.println("Đã xử lý đầu vào");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 UncheckedCustomDemo.java
java UncheckedCustomDemo
```

**Stdout chính xác:**

```text
Hợp lệ: 100
Không hợp lệ: quantity phải lớn hơn 0
Đã xử lý đầu vào
```

`calculateTotal` không có `throws InvalidQuantityException` mà vẫn biên dịch, vì exception này là unchecked. `main` vẫn **có thể chủ động `catch`** để chuyển lỗi thành thông báo phù hợp. Việc bắt unchecked exception không bị cấm; chỉ là **không bắt buộc bởi compiler**.

Đây là ví dụ về tiền điều kiện của phương thức. Trong một hệ thống nhận dữ liệu từ người dùng, tầng nhập liệu thường nên xác thực trước và trả một kết quả kiểm tra hợp lệ, thay vì để exception do sai đầu vào đi xuyên các tầng. Việc chọn kiểu exception không thay thế thiết kế luồng xác thực.

## 5. Câu hỏi thiết kế quan trọng nhất: ai có trách nhiệm xử lý?

Thay vì hỏi “loại lỗi nào nghiêm trọng hơn?”, hãy hỏi:

**Caller có phải được buộc bằng hợp đồng Java để nhận diện và quyết định một kiểu thất bại đã công bố không, hay chúng ta muốn để nó lan truyền và xử lý tại ranh giới phù hợp?**

Khi một API thực hiện một thao tác có thất bại dự kiến, được mô tả rõ, và caller có một số cách xử lý hợp lệ, **checked exception có thể làm hợp đồng tường minh**. Ví dụ một bộ đọc dữ liệu phải phân biệt lỗi đọc có thể chuyển nguồn dự phòng.

Khi một lỗi biểu thị vi phạm tiền điều kiện hoặc trạng thái do cách gọi sai, **unchecked exception thường phù hợp hơn**, để mã có thể thất bại rõ ràng mà không buộc mọi tầng trung gian khai báo hoặc bắt một lỗi lập trình chưa biết cách sửa.

Nhưng cần nhớ:

- Một `IOException` là checked dù có tình huống không thể khắc phục.
- Một `IllegalArgumentException` là unchecked dù tầng giao diện có thể yêu cầu người dùng sửa đầu vào.
- Nhiều framework chọn unchecked domain exceptions để có ranh giới tập trung xử lý lỗi.
- Một hệ thống batch có thể dùng checked exception cho những điều kiện yêu cầu caller quyết định retry hoặc bỏ qua bản ghi.
- Một kết quả nghiệp vụ dự kiến có thể nên được trả bằng **giá trị/kết quả có trạng thái**, không phải exception bất kể checked hay unchecked.

Do đó, **“có thể phục hồi hay không” là một tín hiệu thiết kế, không phải phép thử duy nhất**.

## 6. Khi nào nên cân nhắc `extends Exception`?

Checked custom exception có ích khi những điều kiện sau hợp lý với API:

1. **Loại thất bại là một phần được công bố của hợp đồng phương thức.** Người dùng API cần nhận biết một điều kiện cụ thể để quyết định luồng tiếp theo.
2. **Caller có trách nhiệm đưa ra lựa chọn.** Ví dụ thử cấu hình dự phòng, dừng tác vụ, yêu cầu một lựa chọn khác hoặc báo lỗi tầng giao tiếp.
3. **Việc bắt/khai báo mang giá trị thực tế**, không chỉ là những `catch` rỗng sinh ra để làm compiler hết báo lỗi.
4. **Loại lỗi đủ ổn định** để được đưa vào chữ ký API và tài liệu phiên bản.
5. **Phạm vi API được kiểm soát.** Việc lan truyền checked exception qua nhiều lớp trừu tượng không gây ra quá nhiều phụ thuộc không cần thiết.

Ví dụ hợp đồng:

```java
static Report importReport(Path file)
        throws ReportFormatException, IOException {
    // Đọc file; phát hiện định dạng sai hoặc lỗi I/O.
}
```

Đây là **chữ ký minh họa**, chưa có định nghĩa `Report`, `ReportFormatException` và phần thân. `ReportFormatException extends Exception` có thể là lựa chọn nếu caller được kỳ vọng phân biệt dữ liệu sai định dạng với lỗi I/O để phản hồi phù hợp.

Nếu caller chỉ có thể thất bại và tất cả tầng trung gian phải bắt rồi ném lại mà không bổ sung gì, lợi ích của checked exception có thể thấp hơn chi phí hợp đồng phải truyền xuyên suốt.

## 7. Khi nào nên cân nhắc `extends RuntimeException`?

Unchecked custom exception thường hữu ích khi:

1. **Vi phạm tiền điều kiện lập trình** như đầu vào bắt buộc bị `null`, số lượng âm không được phép, hoặc gọi phương thức sai trình tự.
2. **Trạng thái hiện tại không phù hợp để thực hiện thao tác**, thường là một invariant hoặc `IllegalStateException` có ý nghĩa ở tầng ứng dụng.
3. **Caller thông thường không có hành động xử lý cục bộ hữu ích**; lỗi được chuyển tới một ranh giới giám sát hoặc được sửa ở nơi dùng API.
4. **Kiến trúc muốn tập trung xử lý exception**, ví dụ ở tầng HTTP/job/controller, thay vì ép mọi service/repository truyền `throws`.
5. **API nội bộ hoặc callback** có giới hạn về checked exceptions; cần hợp đồng unchecked phù hợp thay vì khai báo sai hoặc nuốt lỗi.

Ví dụ:

```java
class InvalidWorkflowStateException extends RuntimeException {
    InvalidWorkflowStateException(String message) {
        super(message);
    }
}
```

Nếu một đơn đã hủy nhưng mã tiếp tục cố hoàn tất nó, class này có thể truyền tín hiệu **vi phạm trạng thái workflow**. Caller có thể bắt cụ thể, nhưng thường lỗi cần được xử lý ở ranh giới biết trạng thái tổng thể.

Cần phân biệt **trạng thái không hợp lệ do bug** với **yêu cầu nghiệp vụ bị từ chối bình thường**. Ví dụ số dư không đủ hoặc sản phẩm hết hàng có thể được thiết kế thành kết quả domain có trạng thái thay vì ném exception. Unchecked exception không tự biến một kết quả dự kiến thành lỗi hệ thống.

## 8. Bảng quyết định nhanh

| Tình huống | Gợi ý ban đầu | Điều phải cân nhắc |
| --- | --- | --- |
| Phương thức công bố thất bại I/O và caller cần quyết định fallback | Checked hoặc giữ `IOException` | Bắt/khai báo ở caller mang ý nghĩa không? |
| Hàm tiện ích bị truyền tham số vi phạm hợp đồng | Unchecked | Nên dùng `IllegalArgumentException` có sẵn hay class riêng? |
| Trạng thái đối tượng bị dùng sai trình tự | Unchecked | `IllegalStateException` có đủ diễn đạt không? |
| Parser nhận tệp không hợp lệ và caller phải xử lý riêng | Checked có thể thích hợp | Định dạng sai là ngoại lệ hay kết quả dự kiến? |
| Luồng nhập liệu của người dùng có giá trị sai thường xuyên | Kết quả xác thực có cấu trúc | Đừng dùng exception để điều khiển luồng bình thường nếu không cần |
| Tầng service chuyển `IOException` thành lỗi domain | Tùy hợp đồng service | Giữ `cause` và chọn checked/unchecked dựa vào API |
| Request handler cần đưa mọi lỗi bất ngờ về phản hồi an toàn | Thường xử lý ở ranh giới, có thể dùng unchecked | Đừng làm lộ stack trace hoặc biến bug thành thành công |
| Thư viện công khai cần hứa loại lỗi cụ thể ổn định | Checked có giá trị trong một số API | Chi phí tiến hóa chữ ký/khả năng tương thích |
| Sự cố có thể gây hỏng JVM/không thể tiếp tục | Không tự tạo domain `Error` | Chính sách phục hồi/vận hành riêng, đừng nuốt `Error` |
| Cancellation bằng `InterruptedException` | Thường tiếp tục checked exception gốc | Không phá tín hiệu interrupt vì tiện xử lý |

Bảng trên là **khung quyết định**, không phải luật cứng. Kiểu exception nên phản ánh **ngữ nghĩa của API**, chính sách khôi phục và các quy ước nhất quán trong hệ thống.

## 9. `throws` của checked exception ảnh hưởng người gọi như thế nào?

Giả sử một API:

```java
static void exportData() throws ExportFailedException {
    // ...
}
```

với `ExportFailedException extends Exception`. Một caller muốn gọi `exportData()` có thể chọn:

**Xử lý tại chỗ:**

```java
try {
    exportData();
} catch (ExportFailedException e) {
    showExportError(e);
}
```

**Cho lan truyền:**

```java
static void runExport() throws ExportFailedException {
    exportData();
}
```

Đây là các **đoạn minh họa độc lập**, còn thiếu định nghĩa method phụ. Nhánh đầu phù hợp nếu tầng hiện tại biết cách xử lý. Nhánh thứ hai phù hợp nếu caller cao hơn chịu trách nhiệm. Cả hai đều thể hiện **catch-or-declare**.

Nếu đổi `ExportFailedException` sang `extends RuntimeException`, compiler không buộc caller phải viết handler hoặc `throws` nữa. Nhưng **exception vẫn có thể xảy ra**. Tài liệu API cần công bố ý nghĩa và cách phản ứng, thay vì chỉ dựa vào việc compiler có cảnh báo hay không.

Không nên cho rằng viết `throws` làm exception “chạy lên” còn bỏ `throws` khiến nó “biến mất”: cả checked và unchecked đều lan truyền theo đường thực thi khi không được bắt; `throws` là thông tin hợp đồng có kiểm tra cho checked exception.

## 10. Có cần viết `throws MyRuntimeException` không?

Không bắt buộc:

```java
static void validate(int amount)
        throws InvalidQuantityException {
    if (amount <= 0) {
        throw new InvalidQuantityException("amount <= 0");
    }
}
```

Đây là **phương thức minh họa** trong ngữ cảnh đã có class `InvalidQuantityException extends RuntimeException`. Chữ ký `throws InvalidQuantityException` hợp lệ nhưng **không làm compiler buộc caller bắt nó**.

Có thể chọn đưa unchecked exception vào `throws` để người đọc nhận biết một số điều kiện đặc biệt, nhưng cách này có thể gây hiểu nhầm rằng caller phải catch. Một lựa chọn thường rõ hơn là **JavaDoc `@throws`** để mô tả tiền điều kiện và ý nghĩa:

```java
/**
 * @throws InvalidQuantityException nếu amount không dương
 */
static void validate(int amount) {
    if (amount <= 0) {
        throw new InvalidQuantityException("amount <= 0");
    }
}
```

Đây là **phần minh họa**. Với public API, nên tài liệu hóa cả loại unchecked exception nếu caller cần biết để sử dụng đúng hoặc xử lý ở ranh giới.

## 11. Nên tạo class riêng hay dùng exception sẵn có?

Không phải lỗi nào cũng cần một custom exception. Trước khi chọn hai nhánh kế thừa, hỏi **“Có cần một loại mới không?”**

Các exception sẵn có có thể đã đủ:

| Ý nghĩa | Lớp sẵn có thường phù hợp |
| --- | --- |
| Tham số không hợp lệ | `IllegalArgumentException` |
| Tham số bắt buộc là `null` | `NullPointerException`, thường qua `Objects.requireNonNull` |
| Trạng thái đối tượng không phù hợp | `IllegalStateException` |
| Giá trị chuỗi không phân tích được thành số | `NumberFormatException` |
| Lỗi thao tác I/O | `IOException` và lớp con cụ thể |
| Lỗi định dạng số người dùng nhập | Có thể bắt `NumberFormatException` ở ranh giới và chuyển thành kết quả xác thực |

Custom exception hữu ích khi cần **phân biệt bằng kiểu** giữa các điều kiện quan trọng cho caller, cung cấp mã lỗi ổn định, hoặc gắn ngữ nghĩa module khác với loại Java chung.

Không nên tạo các class chỉ khác message nhưng không có tác dụng định tuyến hoặc kiểm thử, ví dụ `BadInput1Exception`, `BadInput2Exception` không có hợp đồng rõ ràng. Ngược lại, nếu hai lỗi cần những chính sách phục hồi khác nhau, loại riêng có thể giúp tránh `if (e.getMessage().contains(...))` mong manh.

## 12. Thiết kế constructor đúng: message, cause và cả hai

Một custom exception tốt thường có constructor tối thiểu phù hợp với hợp đồng. Ví dụ checked:

```java
public class ReportFormatException extends Exception {
    public ReportFormatException(String message) {
        super(message);
    }

    public ReportFormatException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **một class độc lập** cần đặt trong `ReportFormatException.java` nếu khai báo `public`. Phần quan trọng là các constructor gọi `super(...)` để giữ **detail message** và, khi có, **cause**.

Ví dụ unchecked:

```java
public class OrderStateException extends RuntimeException {
    public OrderStateException(String message) {
        super(message);
    }

    public OrderStateException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là class độc lập `OrderStateException.java`. Dù checked hay unchecked, **cause không được tự động tạo** nếu chỉ truyền message. Với `super(message, cause)`, caller có thể lần theo `getCause()`.

Bạn không bắt buộc tạo đủ bốn constructor (`()`, `(String)`, `(Throwable)`, `(String, Throwable)`) cho mọi class. Chỉ cung cấp những constructor cần thiết để tránh trạng thái exception khó hiểu. Nếu muốn giữ một nguyên nhân kỹ thuật, thường nên có dạng `(String, Throwable)`.

## 13. Ví dụ thực hành: bọc `IOException` thành checked custom exception

Nếu tầng đọc tệp có lỗi I/O nhưng API xử lý báo cáo muốn công bố **loại lỗi riêng**, có thể dùng checked exception wrapper. Lưu **`CheckedWrappingDemo.java`**:

```java
import java.io.IOException;

class ReportLoadException extends Exception {
    ReportLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class CheckedWrappingDemo {
    static String readRaw() throws IOException {
        throw new IOException("Không đọc được nguồn");
    }

    static String loadReport() throws ReportLoadException {
        try {
            return readRaw();
        } catch (IOException e) {
            throw new ReportLoadException("Không tải được báo cáo", e);
        }
    }

    public static void main(String[] args) {
        try {
            loadReport();
        } catch (ReportLoadException e) {
            System.out.println("Lỗi báo cáo: " + e.getMessage());
            System.out.println("Nguyên nhân: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CheckedWrappingDemo.java
java CheckedWrappingDemo
```

**Stdout chính xác:**

```text
Lỗi báo cáo: Không tải được báo cáo
Nguyên nhân: IOException
Cause message: Không đọc được nguồn
```

Phương thức `loadReport` công bố một checked `ReportLoadException` thay vì `IOException`. Caller buộc xử lý/khai báo loại domain đã công bố; `cause` vẫn lưu ngoại lệ gốc để chẩn đoán.

**Wrapping là quyết định thay đổi abstraction**, không chỉ một mẹo “thay tên lỗi”. Nếu caller vẫn cần xử lý riêng `IOException` để đổi nguồn dự phòng, giấu loại đó sau wrapper chưa chắc hợp lý. Có thể chọn giữ `throws IOException` hoặc cung cấp mã lỗi có cấu trúc.

## 14. Ví dụ thực hành: bọc checked thành unchecked tại ranh giới phù hợp

Một tầng service có thể công bố unchecked exception theo hợp đồng để các tầng trung gian không buộc truyền checked exception.

Lưu **`UncheckedWrappingDemo.java`**:

```java
import java.io.IOException;

class ServiceUnavailableException extends RuntimeException {
    ServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class UncheckedWrappingDemo {
    static void connect() throws IOException {
        throw new IOException("Kết nối bị từ chối");
    }

    static void performService() {
        try {
            connect();
        } catch (IOException e) {
            throw new ServiceUnavailableException(
                    "Dịch vụ chưa sẵn sàng", e);
        }
    }

    public static void main(String[] args) {
        try {
            performService();
        } catch (ServiceUnavailableException e) {
            System.out.println("Service: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 UncheckedWrappingDemo.java
java UncheckedWrappingDemo
```

**Stdout chính xác:**

```text
Service: Dịch vụ chưa sẵn sàng
Cause: IOException
```

`performService` không cần khai báo `throws` vì nó ném `ServiceUnavailableException extends RuntimeException`. Dù compiler không buộc `main` catch, handler ở ranh giới vẫn có thể quyết định cách thông báo hoặc thất bại an toàn.

Không lạm dụng **`throw new RuntimeException(e)`** một cách vô nghĩa ở mọi tầng. Việc bọc exception chỉ có giá trị khi nó thể hiện hợp đồng mới, thêm ngữ cảnh hữu ích hoặc đáp ứng một ranh giới API cụ thể; cần giữ `cause` để không mất stack trace gốc.

## 15. Một exception tùy chỉnh có mã lỗi ổn định

Message có thể thay đổi theo ngôn ngữ hoặc nội dung; **đừng dùng message để chọn nhánh chương trình**. Một custom exception có thể cung cấp `errorCode` ổn định.

Lưu **`ErrorCodeDemo.java`**:

```java
enum OrderError {
    INVALID_STATE,
    DUPLICATE_REQUEST
}

class OrderException extends RuntimeException {
    private final OrderError code;

    OrderException(OrderError code, String message) {
        super(message);
        this.code = code;
    }

    OrderError getCode() {
        return code;
    }
}

public class ErrorCodeDemo {
    static void commit(boolean alreadyCommitted) {
        if (alreadyCommitted) {
            throw new OrderException(
                    OrderError.DUPLICATE_REQUEST,
                    "Yêu cầu đã được xử lý");
        }
    }

    public static void main(String[] args) {
        try {
            commit(true);
        } catch (OrderException e) {
            System.out.println("Code: " + e.getCode());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 ErrorCodeDemo.java
java ErrorCodeDemo
```

**Stdout chính xác:**

```text
Code: DUPLICATE_REQUEST
Message: Yêu cầu đã được xử lý
```

Enum giúp caller chuyển hướng xử lý bằng **kiểu/mã lỗi có cấu trúc**, không bằng `e.getMessage().contains(...)`. Tuy nhiên, mã lỗi nghiệp vụ vẫn cần được đặt vào đúng hợp đồng: một yêu cầu trùng hợp lệ có thể phù hợp hơn với **kết quả idempotent** hoặc kiểu kết quả thay vì exception, tùy hệ thống.

Tính ổn định của mã lỗi không đồng nghĩa với việc có thể thay đổi ngữ nghĩa của mã bất kỳ mà không ảnh hưởng caller. Hãy tài liệu hóa phạm vi các mã được hỗ trợ.

## 16. Checked custom exception và quy tắc kế thừa/override phương thức

Lựa chọn checked/unchecked ảnh hưởng cách thực hiện interface và override method:

- Khi override một phương thức, bạn **không được khai báo checked exception mới hoặc rộng hơn** so với hợp đồng checked exception của phương thức bị override.
- Có thể khai báo **loại checked exception hẹp hơn** hoặc không khai báo.
- Có thể ném **unchecked exception** (nhánh `RuntimeException`) mà không bị giới hạn tương tự bởi mệnh đề `throws`.
- Việc override hợp lệ hay không do **kiểu tĩnh và chữ ký** của Java, không phải do caller có định bắt lỗi hay không.

Ví dụ chạy được **`OverrideContractDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Source {
    String read() throws IOException;
}

class LocalSource implements Source {
    @Override
    public String read() throws FileNotFoundException {
        throw new FileNotFoundException("Không thấy tệp");
    }
}

public class OverrideContractDemo {
    public static void main(String[] args) {
        Source source = new LocalSource();

        try {
            System.out.println(source.read());
        } catch (IOException e) {
            System.out.println("Bắt: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 OverrideContractDemo.java
java OverrideContractDemo
```

**Stdout chính xác:**

```text
Bắt: FileNotFoundException
```

`Source.read()` cho phép `IOException`. `LocalSource.read()` khai báo `FileNotFoundException`, một lớp con checked của `IOException`, nên override hợp lệ.

Nếu một interface có `void run();` **không khai báo checked exception**, implementation không được tự thêm `throws MyCheckedException` vào phương thức override. Đây là một yếu tố thực tế khi thiết kế callback, framework API hoặc phương thức được cung cấp cho bên thứ ba.

**Điểm thiết kế:** nếu một API dự kiến bắt buộc caller xử lý checked exception, hợp đồng đó nên được công bố đúng từ cấp interface/base method. Không thể sửa bằng cách chỉ thêm checked `throws` ở implementation override.

## 17. Checked exception trong lambda và functional interface

Hạn chế checked exceptions còn xuất hiện trong lambda. Ví dụ `Runnable.run()` không khai báo checked exception:

```java
Runnable r = () -> {
    // throw new MyCheckedException("Lỗi"); // Không hợp lệ.
};
```

Đây là **mã minh họa**; giả sử `MyCheckedException extends Exception`. Nếu viết dòng `throw` thực sự mà không xử lý checked exception bên trong lambda, mã bị lỗi compile vì `Runnable.run()` không cho phép checked exception đó.

Có những lựa chọn hợp lệ:

1. Xử lý checked exception **trong lambda**, nếu ở đây có cách phục hồi.
2. Dùng **functional interface riêng có `throws` phù hợp** khi sở hữu API.
3. Chuyển sang một unchecked exception có `cause`, **chỉ khi hợp đồng callback chấp nhận chuyển đổi**.
4. Thiết kế lại nơi gọi để checked exception được xử lý ở tầng hợp lý thay vì ép buộc callback làm công việc không thuộc trách nhiệm.

Ví dụ functional interface riêng:

```java
@FunctionalInterface
interface CheckedTask {
    void run() throws DataImportException;
}
```

Đây là **interface minh họa**, cần `DataImportException extends Exception` được khai báo. Khi lambda có target type `CheckedTask`, nó có thể ném loại checked được công bố. Chọn loại exception vì **hợp đồng API**, không vì cần một cú pháp nhanh để compile qua.

## 18. Thay đổi loại checked/unchecked ảnh hưởng caller và tương thích API

Đây không phải quyết định hoàn toàn riêng tư của class. Khi công bố một thư viện hoặc module, người dùng API có thể viết:

```java
try {
    client.execute();
} catch (YourCheckedException e) {
    recover(e);
}
```

Đây là **mã khung minh họa**. Nếu API hoặc cấu trúc kế thừa thay đổi:

- **Thêm một checked exception** mới vào đường thoát của phương thức có thể buộc mã nguồn caller sửa `catch` hoặc `throws` để biên dịch lại.
- **Đổi một checked exception thành unchecked** có thể ảnh hưởng các `catch`, tài liệu và kỳ vọng caller; đôi khi `catch` riêng cho một checked loại không còn có thể phát sinh từ `try` sẽ trở thành mã không hợp lệ khi biên dịch.
- **Thay loại exception** dù vẫn unchecked có thể phá các handler bắt theo lớp cụ thể.
- **Đổi superclass** của exception có thể ảnh hưởng các mối quan hệ `instanceof`, catch ordering, serialization và hợp đồng công khai.
- **Giữ nguyên chữ ký binary** chưa đủ để bảo đảm hành vi và khả năng tương thích mã nguồn, vì checked-exception checking diễn ra ở compile time và ứng dụng có thể phụ thuộc quy tắc xử lý cũ.

Vì vậy, nên chọn và tài liệu hóa sớm với API công khai, đồng thời thiết kế **phân loại lỗi có khả năng tiến hóa**. Đừng đổi giữa `Exception` và `RuntimeException` chỉ để dọn bớt `throws` khi chưa xem ảnh hưởng tới các module sử dụng.

## 19. Mối quan hệ giữa checked/unchecked và hành vi phục hồi

Một lỗi có thể **phục hồi được** nhưng unchecked. Ví dụ `NumberFormatException` có thể được giao diện nhập liệu bắt và yêu cầu nhập lại. Ngược lại, một `IOException` checked có thể xảy ra vì đĩa hỏng hoặc nguồn dữ liệu không còn tồn tại; caller có thể chỉ có lựa chọn dừng thao tác.

Bởi vậy, phân tích nên theo câu hỏi:

- Tầng hiện tại **có đủ thông tin** để phục hồi không?
- Caller **phải bị ép** bằng trình biên dịch để xét loại lỗi này hay không?
- Hệ thống có chính sách phục hồi ở **ranh giới cuối** không?
- Đây là **thất bại bất thường** hay **kết quả nghiệp vụ dự kiến**?
- Việc khôi phục có thực sự giữ **bất biến/side effect** hợp lệ không?

Ví dụ: API thanh toán báo “số tiền vượt hạn mức” có thể được thiết kế thành đối tượng kết quả từ chối hợp lệ, không nhất thiết `PaymentException`. Nhưng lỗi “dịch vụ ngân hàng không kết nối được” là sự cố kỹ thuật, có thể dùng exception, với phân loại checked/unchecked tùy hợp đồng.

**Khả năng phục hồi phụ thuộc ngữ cảnh, không phải do superclass tự quyết định.**

## 20. Vì sao không nên bắt mọi `Exception` rồi tiếp tục?

Một cách “giảm phiền” khi dùng checked exception là viết:

```java
try {
    doWork();
} catch (Exception ignored) {
    // Không làm gì.
}
```

Đây là **mã khung phản ví dụ**, `doWork()` chưa được định nghĩa. `catch (Exception)` có thể bắt cả checked lẫn `RuntimeException`. Việc nuốt lỗi khiến caller có thể tin thao tác thành công dù dữ liệu chưa hoàn chỉnh hoặc trạng thái bị hỏng.

Tương tự, một unchecked exception cũng không nên bị chặn mù quáng chỉ để hệ thống tiếp tục. Tầng ranh giới có thể cần bắt rộng để ngăn một request làm dừng vòng phục vụ, nhưng phải **ghi nhận thất bại, trả trạng thái chính xác và có chính sách thích hợp**.

Phân biệt ba hành vi:

1. **Phục hồi thật sự**: có fallback hợp lệ, kết quả được phép.
2. **Ném lại/bọc lỗi**: tầng hiện tại không thể phục hồi nhưng chuyển tín hiệu với ngữ cảnh đúng.
3. **Nuốt lỗi**: không xử lý, không báo thất bại, để caller hiểu nhầm — thường là bug.

Việc chọn `extends RuntimeException` không cho phép bỏ qua bước thiết kế chính sách xử lý.

## 21. Quản lý `InterruptedException`: ngoại lệ checked đặc biệt

`InterruptedException` là checked exception thường được dùng trong các thao tác chờ hoặc bị ngắt như `Thread.sleep`. Nó còn có ý nghĩa **tín hiệu yêu cầu dừng/hủy** một công việc đang chờ.

Khi chuyển `InterruptedException` thành một custom unchecked exception, không nên xóa mất ngữ nghĩa interrupt. Một ví dụ API đồng bộ có thể truyền tiếp `throws InterruptedException` là lựa chọn rõ nhất nếu hợp đồng cho phép.

Nếu ranh giới API không cho phép checked `throws InterruptedException`, một phương án thường dùng là:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Thao tác bị ngắt", e);
}
```

Đây là **mã minh họa trong phương thức**. Việc gọi `Thread.currentThread().interrupt()` khôi phục cờ interrupt mà những thao tác như `sleep` thường đã xóa khi ném exception. Wrapper có cause giữ dấu vết gốc.

Tuy nhiên, **không áp dụng mẫu này máy móc cho mọi API**. Nếu caller cần phân biệt ngắt để dừng một tác vụ, để checked `InterruptedException` lan tiếp có thể đúng hơn. Điều quan trọng là không nuốt hoặc coi interrupt là một lỗi thông thường được phép bỏ qua.

## 22. Không nên kế thừa `Error` cho ngoại lệ nghiệp vụ

`Error` và các lớp con là unchecked, nhưng điều đó không khiến `extends Error` thành lựa chọn thay thế cho `extends RuntimeException`. `Error` thường biểu thị những tình huống nghiêm trọng về môi trường/JVM hoặc các điều kiện không được mã nghiệp vụ thông thường xử lý như một sự cố dự kiến.

Ví dụ không nên làm:

```java
// Không khuyến nghị cho lỗi nghiệp vụ:
class ProductUnavailableError extends Error {
    ProductUnavailableError(String message) {
        super(message);
    }
}
```

Đây là class minh họa cho **thiết kế không nên dùng**. Với một sản phẩm không có sẵn, có thể chọn kết quả domain, hoặc một exception phù hợp thuộc `Exception`/`RuntimeException` nếu thật sự cần.

Tương tự, thường không nên `extends Throwable` trực tiếp: một số handler của người sử dụng API viết `catch (Exception e)` sẽ **không bắt** được loại trực tiếp chỉ thuộc `Throwable` mà không nằm trong `Exception`. Nên giữ hệ phân cấp theo quy ước chuẩn.

## 23. Cấu trúc phân cấp custom exception cho một module

Khi module có nhiều loại lỗi và caller cần phân biệt bằng kiểu, có thể tạo lớp nền có mã lỗi rồi cho các loại cụ thể kế thừa. Nhưng phải **giữ thống nhất chính sách checked/unchecked theo từng nhánh**, không tạo cây quá sâu.

Ví dụ thiết kế unchecked:

```java
class ApplicationException extends RuntimeException {
    ApplicationException(String message, Throwable cause) {
        super(message, cause);
    }
}

class ConfigurationException extends ApplicationException {
    ConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **các class minh họa**. `catch (ApplicationException e)` sẽ bắt cả `ConfigurationException`; `catch (ConfigurationException e)` cho phép xử lý cụ thể hơn. Nếu viết hai nhánh `catch` trong cùng cấu trúc, nhánh cụ thể phải đứng trước lớp cha.

Một thiết kế khác có thể là checked base `ApplicationException extends Exception`, nhưng khi đó các loại con checked sẽ đi vào hợp đồng `throws` của các phương thức có thể ném chúng. **Đừng chọn base checked chỉ vì nghe “nghiêm túc hơn”**; phải đánh giá caller có cần nghĩa vụ catch-or-declare với cả nhánh lỗi hay không.

Nếu một lỗi không thuộc cùng chính sách xử lý, không cần cố ép nó vào cùng cây kế thừa. Có thể dùng exception sẵn có hoặc nhánh class khác và ánh xạ về mã lỗi ở ranh giới.

## 24. Dùng `catch` nhiều loại khi caller có chính sách chung

Một caller có thể muốn xử lý nhiều ngoại lệ bằng một nhánh, kể cả khi hai loại thuộc checked và unchecked:

```java
try {
    execute();
} catch (ReportLoadException | IllegalArgumentException e) {
    System.out.println("Thất bại: "
            + e.getClass().getSimpleName());
}
```

Đây là **mã khung minh họa**, giả định `ReportLoadException extends Exception` và `execute()` có thể ném hai loại đã nêu. `ReportLoadException` và `IllegalArgumentException` không có quan hệ subtype, nên cú pháp multi-catch là hợp lệ.

Tham số multi-catch **ngầm định `final`**, không thể gán lại. Nó nhận **một object exception tại runtime**; loại runtime thực của object được giữ nguyên.

Nếu chính sách xử lý hai lỗi khác nhau, nên dùng **hai handler riêng** để giữ ý nghĩa, thay vì gộp chỉ để giảm số dòng. Không gộp một loại cha và một loại con trong cùng multi-catch vì compiler từ chối phần kiểu chồng lắp.

## 25. Kiểm thử checked/unchecked: không chỉ dựa vào khả năng biên dịch

Với checked exception, compiler giúp kiểm tra những đường ném theo chữ ký, nhưng **không bảo đảm phục hồi đúng**. Với unchecked exception, test cũng cần xác nhận hành vi vì caller không bị buộc catch.

Một test có giá trị cần kiểm tra:

| Trường hợp | Nội dung kiểm chứng |
| --- | --- |
| Đường thành công | Không ném exception, kết quả đúng |
| Tiền điều kiện không hợp lệ | Loại unchecked cụ thể, message hoặc mã lỗi hợp đồng |
| Thất bại checked được công bố | Caller phải catch/declare; runtime ném đúng loại |
| Bọc ngoại lệ | Wrapper đúng loại; `getCause()` giữ object gốc |
| Ném lại | Caller vẫn nhận đúng exception gốc nếu hợp đồng yêu cầu |
| Không có handler | Thao tác thực sự thất bại, không trả giá trị thành công giả |
| Handler tại ranh giới | Phản hồi cuối an toàn, không lộ dữ liệu nhạy cảm |
| Cleanup cùng thất bại | Primary, cause và suppressed được giữ đúng |
| Thay đổi API | Mã caller mẫu vẫn biên dịch với phiên bản mới |
| Callback và override | Không có checked `throws` trái hợp đồng kế thừa |

Có thể dùng JUnit `assertThrows` trong dự án, nhưng không cần thư viện ngoài để kiểm tra cơ bản. Ví dụ tự kiểm tra Java 17 dưới đây cho cả hai nhánh.

## 26. Chương trình tự kiểm tra cả checked và unchecked

Lưu **`CustomExceptionAssertionsDemo.java`**:

```java
class CustomChecked extends Exception {
    CustomChecked(String message) {
        super(message);
    }
}

class CustomUnchecked extends RuntimeException {
    CustomUnchecked(String message) {
        super(message);
    }
}

public class CustomExceptionAssertionsDemo {
    static void checked() throws CustomChecked {
        throw new CustomChecked("checked");
    }

    static void unchecked() {
        throw new CustomUnchecked("unchecked");
    }

    public static void main(String[] args) {
        try {
            checked();
            throw new AssertionError("Thiếu checked exception");
        } catch (CustomChecked e) {
            if (!"checked".equals(e.getMessage())) {
                throw new AssertionError("Sai checked message");
            }
            System.out.println("PASS checked");
        }

        try {
            unchecked();
            throw new AssertionError("Thiếu unchecked exception");
        } catch (CustomUnchecked e) {
            if (!"unchecked".equals(e.getMessage())) {
                throw new AssertionError("Sai unchecked message");
            }
            System.out.println("PASS unchecked");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 CustomExceptionAssertionsDemo.java
java CustomExceptionAssertionsDemo
```

**Stdout chính xác:**

```text
PASS checked
PASS unchecked
```

Chương trình chạy thành công khi cả hai exception đúng loại/message. `AssertionError` được dùng để chủ động làm test thất bại nếu không ném hoặc sai kết quả, không phụ thuộc tùy chọn `-ea` của từ khóa `assert`.

Việc chạy thành công không chứng minh một thiết kế checked/unchecked luôn phù hợp: test chỉ xác nhận **hành vi đã chọn**, còn chất lượng hợp đồng cần được review theo trách nhiệm caller, khả năng phục hồi và cách tiến hóa API.

## 27. Các sai lầm thường gặp

### 27.1. “Lỗi có thể sửa được thì luôn `extends Exception`”

Không đúng. Một input không hợp lệ do người dùng có thể sửa nhưng `NumberFormatException` là unchecked. Ngược lại, một `IOException` checked có thể do lỗi hạ tầng chưa có cách khắc phục. Thiết kế cần xem **ai quyết định và có nên buộc caller** xử lý tại compile time.

### 27.2. “Lỗi không quan trọng thì `extends RuntimeException`”

Sai. Unchecked exception vẫn có thể rất nghiêm trọng; nó chỉ không bị bắt/khai báo bắt buộc. Đừng dùng để đánh dấu mức độ ưu tiên xử lý.

### 27.3. “`extends Exception` sẽ bắt mọi bug ở caller”

Không. Checked exception chỉ được compiler kiểm tra theo **những đường ném được mô tả**. `RuntimeException` và `Error` vẫn có thể xảy ra dù không khai báo. Compiler không đảm bảo ứng dụng không có bug runtime.

### 27.4. “`catch (Exception)` là an toàn nhất”

Handler quá rộng có thể bắt cả `RuntimeException` do bug rồi che mất lỗi. Nếu chỉ xử lý một thất bại cụ thể, hãy bắt **loại cụ thể**.

### 27.5. “Cứ dùng `throws Exception` là đủ”

Mệnh đề quá rộng làm caller mất thông tin về loại lỗi. Nên khai báo các checked exception phù hợp hợp đồng nếu API cần tính chính xác.

### 27.6. “Muốn bỏ checked thì `throw new RuntimeException(e.getMessage())`”

Cách này tạo exception mới **không giữ cause**, làm mất thông tin chẩn đoán. Nếu phải bọc, dùng constructor có `cause`, ví dụ `new ServiceException("...", e)`.

### 27.7. “Custom exception nào cũng cần bốn constructor, field và nhiều lớp con”

Không bắt buộc. Chọn API gọn, có ý nghĩa; class riêng chỉ khi tăng khả năng phân biệt và quản lý lỗi.

### 27.8. “Có checked exception là caller đã xử lý xong”

Caller có thể chỉ `catch` rồi bỏ qua, in log trùng lặp hoặc trả kết quả sai. Compiler kiểm tra nghĩa vụ cú pháp, không đánh giá chất lượng phục hồi.

### 27.9. “Unchecked exception không cần tài liệu”

Sai. Bên dùng API vẫn cần biết tiền điều kiện, mã lỗi, hoàn cảnh thất bại và kỳ vọng xử lý, thường qua JavaDoc `@throws` và hướng dẫn sử dụng.

### 27.10. “Chuyển giữa checked và unchecked không ảnh hưởng ai”

Thay đổi có thể làm hỏng mã nguồn caller, logic `catch`, hợp đồng interface/override và cách framework xử lý. Cần đánh giá tương thích trước khi đổi superclass.

### 27.11. “Dùng `extends Error` để tránh `throws` là hợp lý”

Không nên. `Error` không phải vùng dành cho lỗi nghiệp vụ thông thường; chọn `RuntimeException` nếu hợp đồng cần unchecked.

### 27.12. “Mọi kết quả nghiệp vụ đều nên dùng custom exception”

Không nhất thiết. Những trường hợp dự kiến như tìm kiếm không có kết quả hoặc yêu cầu được từ chối hợp lệ có thể phù hợp với `Optional`, `enum`, `sealed interface` hoặc kiểu kết quả có trạng thái.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** `class DataException extends Exception` trực tiếp là checked hay unchecked?  
**Đáp án:** Checked; caller phải catch hoặc declare khi đường gọi có thể ném.

**Câu 2.** `class StateException extends RuntimeException` có thể được bắt bằng `catch (Exception e)` không?  
**Đáp án:** Có. `RuntimeException` nằm trong nhánh `Exception`, dù unchecked.

**Câu 3.** Vì sao không khai báo `throws` vẫn có thể ném `StateException`?  
**Đáp án:** Vì nó là unchecked exception; compiler không bắt buộc catch-or-declare.

**Câu 4.** Nếu `extends Exception`, liệu exception tự phục hồi hoặc caller tự xử lý đúng không?  
**Đáp án:** Không. Compiler chỉ buộc bắt/khai báo. Phục hồi cần logic có ý nghĩa.

**Câu 5.** Có nên tạo `CustomInvalidArgumentException` thay mọi `IllegalArgumentException` không?  
**Đáp án:** Chỉ khi class mới tăng khả năng phân loại/hợp đồng thực sự; nếu không, loại sẵn có có thể đủ.

**Câu 6.** Khi wrapping `IOException` thành exception dịch vụ, làm sao giữ nguyên nhân?  
**Đáp án:** Constructor `(String, Throwable)` và gọi `super(message, cause)`, để `getCause()` giữ exception gốc.

**Câu 7.** Đổi một custom checked exception thành unchecked có thể làm thay đổi caller không?  
**Đáp án:** Có. Nghĩa vụ catch/declare, tính hợp lệ của handler, override và kỳ vọng API có thể thay đổi.

**Câu 8.** Một phương thức override có thể khai báo checked exception rộng hơn base method không?  
**Đáp án:** Không, theo quy tắc checked-exception của Java; có thể hẹp hơn nếu hợp lệ.

**Câu 9.** Tại sao lambda target type `Runnable` không thể tùy ý ném custom checked exception?  
**Đáp án:** Vì `Runnable.run()` không khai báo checked exception đó; phải xử lý hoặc dùng functional interface khác phù hợp.

**Câu 10.** `getMessage()` có nên dùng để quyết định mã lỗi nghiệp vụ không?  
**Đáp án:** Không nên; message có thể thay đổi/được dịch. Dùng loại hoặc mã lỗi có cấu trúc.

**Câu 11.** Unchecked exception có thể được catch ở ranh giới HTTP/CLI không?  
**Đáp án:** Có. Không bắt buộc không đồng nghĩa không thể bắt.

**Câu 12.** `Error` thuộc checked hay unchecked? Có phù hợp cho lỗi “không đủ số dư” không?  
**Đáp án:** `Error` là unchecked nhưng không phù hợp cho lỗi nghiệp vụ như vậy.

**Câu 13.** Khi nào một kết quả có trạng thái tốt hơn exception?  
**Đáp án:** Khi thất bại là nhánh nghiệp vụ dự kiến và caller cần xử lý thường xuyên theo luồng bình thường.

**Câu 14.** Tại sao phải xử lý `InterruptedException` cẩn thận nếu định bọc thành unchecked?  
**Đáp án:** Nó mang tín hiệu ngắt/hủy. Cần truyền tiếp nếu hợp đồng cho phép hoặc phục hồi trạng thái interrupt khi phù hợp.

**Câu 15.** Nếu client luôn bắt `catch (ApplicationException e)`, subclass của `ApplicationException` có được bắt không?  
**Đáp án:** Có, nếu thuộc nhánh kế thừa đó và exception được ném vào phạm vi handler.

## 29. Checklist quyết định cho một custom exception mới

Trước khi tạo `XxxException`, hãy tự rà soát:

1. **Đây có phải exception không?** Hay là kết quả nghiệp vụ dự kiến nên được trả có trạng thái?
2. **Loại sẵn có có đủ rõ không?** Ví dụ `IllegalArgumentException`/`IllegalStateException`.
3. **Caller có bắt buộc phải xét loại lỗi này ở compile time không?** Nếu có và mang giá trị rõ ràng, cân nhắc checked.
4. **Caller thường không thể xử lý ở tầng gần mà cần ranh giới cuối?** Cân nhắc unchecked và tài liệu hóa.
5. **Loại lỗi ổn định theo hợp đồng API chứ?** Tránh thay superclass liên tục.
6. **Có cần biến thể recovery khác nhau?** Nếu có, phân loại bằng kiểu/mã lỗi cụ thể.
7. **Có giữ `cause` khi chuyển lỗi từ tầng thấp không?** Đảm bảo constructor phù hợp.
8. **Message có an toàn và hữu ích không?** Không đưa mật khẩu/token/nội dung nhạy cảm.
9. **Có mã lỗi ổn định cho ứng dụng không?** Không parse text message.
10. **Có interface/callback ảnh hưởng checked `throws` không?** Xem quy tắc override và functional interface.
11. **Có ngữ nghĩa cancellation/interrupt không?** Không tự nuốt tín hiệu hủy.
12. **Có tình huống cleanup làm phát sinh suppressed không?** Giữ cause/suppressed khi chẩn đoán.
13. **Handler cuối nằm ở đâu?** HTTP, CLI, job scheduler, UI hoặc caller thư viện.
14. **Đã test hành vi cả thành công và thất bại chưa?** Không chỉ dựa vào compiler.
15. **Việc thay đổi loại exception có phá caller đã triển khai không?** Xem xét cả source/API compatibility.
16. **Có đang viết `catch` chỉ để im lặng bỏ qua lỗi không?** Tránh biến thất bại thành thành công giả.

## 30. Kết luận

**`extends Exception` và `extends RuntimeException` tạo hai hợp đồng khác nhau cho custom exception Java**:

- **Checked (`extends Exception` trực tiếp):** caller có nghĩa vụ **catch hoặc declare** nếu phương thức có thể ném lỗi; phù hợp khi việc công bố và buộc xét một thất bại cụ thể là một phần có giá trị của API.
- **Unchecked (`extends RuntimeException`):** caller **không bị ép** bởi compiler; phù hợp với nhiều trường hợp vi phạm tiền điều kiện, trạng thái và các thiết kế xử lý tập trung, nhưng lỗi vẫn phải được chẩn đoán/điều phối đúng.

Không có quy tắc duy nhất dựa vào mức độ nghiêm trọng hoặc khả năng phục hồi. Hãy chọn theo **ý nghĩa lỗi, trách nhiệm caller, độ ổn định của API, chính sách xử lý cuối và trải nghiệm người dùng**. Giữ nguyên nhân qua `cause` khi wrapping, tài liệu hóa unchecked exceptions, dùng kết quả có trạng thái cho nhánh nghiệp vụ dự kiến, và tránh tạo cây exception phức tạp không có lợi ích.

Quy tắc thực hành gọn nhất: **hãy dùng checked khi việc ép caller xử lý/khai báo là một phần hữu ích của hợp đồng; dùng unchecked khi không muốn áp đặt nghĩa vụ ấy; và chỉ tạo exception mới khi loại mới diễn đạt một tình huống mà caller hoặc hệ thống thực sự cần phân biệt**.
