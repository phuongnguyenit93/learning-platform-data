# Tránh kế thừa trực tiếp `Throwable` hoặc `Error` khi không phù hợp trong Java

Khi tạo **ngoại lệ tùy chỉnh (custom exception)**, câu hỏi đầu tiên không chỉ là *“đặt tên class gì?”* mà còn là *“class đó nên kế thừa nhánh nào trong cây `Throwable`?”*. Lựa chọn lớp cha quyết định loại lỗi có bị kiểm tra lúc biên dịch hay không, các khối `catch` có nhận được nó hay không, ý nghĩa mà API gửi đến caller và mức độ dễ bảo trì.

**Quy tắc thực hành cho hầu hết ứng dụng Java:**

- Với lỗi ứng dụng mà bên gọi **được kỳ vọng bắt hoặc khai báo** theo hợp đồng checked exception, cân nhắc kế thừa `Exception` hoặc một subclass checked phù hợp.
- Với lỗi tham số, trạng thái hoặc hợp đồng ứng dụng sử dụng **unchecked exception**, cân nhắc `RuntimeException` hay một subclass như `IllegalStateException`.
- **Không kế thừa trực tiếp `Throwable`** chỉ để “tạo loại lỗi tổng quát nhất”: điều này thường tạo một checked exception không thuộc nhánh `Exception` và gây bất ngờ cho caller.
- **Không kế thừa `Error`** cho những thất bại nghiệp vụ, validation, I/O hay lỗi tích hợp thông thường: nhánh này có ý nghĩa đặc biệt và không nên dùng như cách né `throws`.

Hai lựa chọn cuối không phải lúc nào cũng bị Java cấm về mặt cú pháp. Điều quan trọng là chúng thường **không đúng ngữ nghĩa hoặc hợp đồng xử lý** của lỗi mà bạn đang thiết kế.

## 1. Đọc đúng cây kế thừa `Throwable`

Phân cấp rút gọn:

~~~text
java.lang.Object
    |
    +-- java.lang.Throwable
          |
          +-- java.lang.Error
          |      +-- AssertionError
          |      +-- LinkageError
          |      +-- VirtualMachineError
          |             +-- OutOfMemoryError
          |
          +-- java.lang.Exception
                 |
                 +-- IOException
                 |
                 +-- RuntimeException
                        +-- IllegalArgumentException
                        +-- IllegalStateException
                        +-- NullPointerException
~~~

Trong Java:

- `Throwable` là lớp gốc của đối tượng có thể dùng với `throw` và nhận qua `catch`.
- `Exception` là nhánh thường dùng để biểu diễn những điều kiện ngoại lệ mà ứng dụng có thể quyết định xử lý.
- `RuntimeException` là nhánh **unchecked**, thường dùng cho những điều kiện không bắt buộc caller phải bắt hoặc khai báo ở compile-time.
- `Error` cũng là nhánh **unchecked**, thường biểu thị vấn đề nghiêm trọng của VM, liên kết lớp, bất biến hệ thống hoặc những điều kiện mà mã ứng dụng thông thường không được kỳ vọng phục hồi.
- Một lớp **kế thừa trực tiếp `Throwable`**, nhưng không thuộc `RuntimeException` hoặc `Error`, là **checked exception**.

Điều kiện checked/unchecked được suy ra từ **kiểu kế thừa**, không từ tên class và cũng không từ mức độ “nguy hiểm” mà người viết gán cho lỗi.

### Phân biệt “có thể viết” với “nên viết”

Ví dụ Java **hợp lệ về cú pháp**:

~~~java
final class DirectFailure extends Throwable {
    DirectFailure(String message) {
        super(message);
    }
}
~~~

Cũng có thể định nghĩa:

~~~java
final class BusinessFailureError extends Error {
    BusinessFailureError(String message) {
        super(message);
    }
}
~~~

Nhưng hai cách đó có hậu quả quan trọng mà không thể nhìn thấy chỉ bằng tên class. Bài học sẽ phân tích vì sao trong phần lớn code nghiệp vụ nên chọn hướng khác.

## 2. Vì sao kế thừa trực tiếp `Throwable` thường là lựa chọn sai?

Một custom exception trực tiếp kế thừa `Throwable` nằm **ngoài cả nhánh `Exception` lẫn `Error`**. Java vẫn cho ném nó, nhưng nhiều API và handler của ứng dụng được thiết kế theo `Exception`, không theo lớp gốc `Throwable`.

Ví dụ:

~~~java
final class DirectFailure extends Throwable {
    DirectFailure(String message) {
        super(message);
    }
}

static void work() throws DirectFailure {
    throw new DirectFailure("cannot complete work");
}
~~~

Đây là hai khai báo minh họa có thể đặt trong cùng một lớp Java.

`DirectFailure` ở đây là **checked**. Vì vậy `work()` phải bắt hoặc khai báo nó như ví dụ. Caller cũng cần xử lý hoặc chuyển tiếp loại checked đó.

### 2.1. `catch (Exception)` không nhận được subclass trực tiếp của `Throwable`

~~~java
static void caller() throws DirectFailure {
    try {
        work();
    } catch (Exception e) {
        System.out.println("Exception handler");
    }
}
~~~

Đây là phương thức minh họa **có thể biên dịch** khi `work()` ném `DirectFailure`. `catch (Exception e)` không bắt được `DirectFailure` vì nó không kế thừa `Exception`. Do đó `caller()` vẫn phải khai báo `throws DirectFailure` hoặc có một handler khác phù hợp.

Caller thông thường dễ lầm tưởng `catch (Exception)` xử lý toàn bộ lỗi kiểu “exception” của ứng dụng, nhưng với một subtype trực tiếp của `Throwable`, giả định đó không đúng.

### 2.2. Có thể làm chữ ký `throws` trở nên quá rộng

Nếu thư viện dùng `throws Throwable` để tránh nêu từng lỗi:

~~~java
static void execute() throws Throwable {
    throw new DirectFailure("cannot complete work");
}
~~~

thì caller có thể bị buộc bắt/khai báo `Throwable` hoặc một kiểu phù hợp với lỗi được khai báo ở nơi gọi. Chữ ký đó rộng đến mức trộn các tình huống thông thường với cả `Error`, khiến hợp đồng kém rõ ràng.

Không nên sử dụng `throws Throwable` trong API nghiệp vụ chỉ để “an toàn cho mọi tương lai”. Càng rộng không có nghĩa càng tốt; nó có thể bắt người dùng API xử lý một tập hợp loại lỗi không phù hợp.

### 2.3. Không ăn khớp với nhiều ranh giới xử lý `Exception`

Trong ứng dụng thực tế, những lớp xử lý chung, bộ ánh xạ response hoặc mã xử lý nghiệp vụ có thể chủ động nhận `Exception`. Một subtype trực tiếp của `Throwable` **không thuộc nhóm đó**.

Không khẳng định mọi framework đều không nhận được nó: một framework có thể dùng `Throwable` hoặc các cơ chế đặc biệt. Nhưng việc chọn trực tiếp `Throwable` làm cha **tăng khả năng tạo tình huống bất ngờ**, và cần có hợp đồng rõ ràng nếu thực sự muốn làm vậy.

**Kết luận:** Trừ trường hợp thiết kế framework/máy ảo có lý do đặc biệt, lỗi tùy chỉnh thông thường nên nằm trong nhánh `Exception` hoặc `RuntimeException`, không trực tiếp dưới `Throwable`.

## 3. Vì sao không nên kế thừa `Error` cho lỗi nghiệp vụ?

`Error` là nhánh unchecked của `Throwable`, nhưng nó **không phải tên thay thế cho mọi lỗi nghiêm trọng**.

Một số lớp chuẩn minh họa ý nghĩa khác biệt:

| Lớp | Ý nghĩa tiêu biểu |
| --- | --- |
| `OutOfMemoryError` | JVM không cấp phát được bộ nhớ theo yêu cầu |
| `StackOverflowError` | Quá trình gọi lồng sâu gây tràn stack |
| `LinkageError` | Vấn đề liên kết/định nghĩa lớp |
| `AssertionError` | Một khẳng định nội bộ bị vi phạm |
| `Error` | Lớp cha chung của nhóm lỗi đặc biệt |

Không phải mọi đối tượng `Error` trong mọi môi trường đều có mức độ nghiêm trọng giống nhau, và một chương trình đặc biệt có thể cố ý dùng `AssertionError` trong kiểm thử. Tuy nhiên, **ý nghĩa thông thường của `Error` không phải lỗi nghiệp vụ có thể phục hồi**.

### 3.1. `catch (Exception)` không bắt `Error`

~~~java
try {
    throw new AssertionError("Unexpected invariant failure");
} catch (Exception e) {
    System.out.println("Exception caught");
} catch (AssertionError e) {
    System.out.println("AssertionError caught");
}
~~~

Đây là mảnh mã Java hợp lệ. Đầu ra là:

~~~text
AssertionError caught
~~~

`AssertionError` không kế thừa `Exception`, nên nhánh đầu không nhận nó. Nhánh sau chỉ được dùng ở đây để **minh họa phân cấp kiểu**; không nên biến việc bắt rộng `Error` thành cách phục hồi thông thường ở production.

Nếu bạn tự định nghĩa `PaymentDeclinedError extends Error` cho một kết quả thanh toán dự kiến, các handler vốn bắt `Exception` có thể không nhận nó. Tên `Error` còn truyền sai thông điệp rằng lỗi thuộc loại bất thường nghiêm trọng như lỗi của VM hoặc bất biến hệ thống.

### 3.2. Dùng `Error` để tránh checked exception là sai động cơ

Một số người muốn tránh `throws` nên nghĩ rằng:

~~~java
final class DatabaseUnavailableError extends Error {
    DatabaseUnavailableError(String message) {
        super(message);
    }
}
~~~

Đây là **phản ví dụ về thiết kế**, dù class biên dịch. `DatabaseUnavailableError` là unchecked vì nằm dưới `Error`, nhưng điều đó không biến mất kết nối cơ sở dữ liệu thành lỗi máy ảo. Nếu muốn một lỗi ứng dụng unchecked với ý nghĩa đúng, thường nên dùng `RuntimeException` hoặc một subclass thích hợp.

### 3.3. Tại sao không “bắt `Throwable` rồi tiếp tục”?

~~~java
try {
    performBusinessAction();
} catch (Throwable t) {
    logAndContinue(t);
}
~~~

Đây là đoạn minh họa có hai hàm giả định. Bắt `Throwable` bao gồm `Exception`, `RuntimeException`, `Error` và cả subtype trực tiếp của `Throwable`. Nếu cứ tiếp tục nghiệp vụ sau mọi `Error`, hệ thống có thể vận hành ở trạng thái không an toàn hoặc không còn đủ tài nguyên.

**Bắt `Throwable` chỉ nên có ở các ranh giới đặc biệt với chính sách lỗi rất rõ**, chẳng hạn một số khung thực thi phải ghi nhận trạng thái trước khi thất bại. Nó không phải handler mặc định cho request, thao tác cơ sở dữ liệu hoặc xử lý nhập liệu.

## 4. Chọn lớp cha đúng: `Exception`, `RuntimeException` hay lớp chuyên biệt?

Một cây quyết định đơn giản:

~~~text
Có thật sự cần tạo loại ngoại lệ riêng?
             |
     +-------+-------+
     |               |
    Không            Có
     |               |
Sử dụng ngoại lệ     Caller cần hợp đồng checked?
chuẩn hoặc kiểu           |
kết quả dữ liệu       +----+----+
                      |         |
                     Có        Không
                      |         |
               extends Exception   extends RuntimeException
               (checked)           hoặc subclass unchecked
~~~

Sơ đồ là **định hướng thực hành**, không phải công thức cứng. Một số API chọn unchecked cho lỗi có thể phục hồi, vì caller được thiết kế xử lý ở tầng biên; một số API chọn checked để buộc tầng gọi cân nhắc việc thất bại.

### 4.1. Dùng `Exception` cho hợp đồng checked

~~~java
public final class ConfigurationLoadException extends Exception {
    public ConfigurationLoadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là một lớp độc lập trong `ConfigurationLoadException.java`.

Khi dùng:

~~~java
static void initialize() throws ConfigurationLoadException {
    try {
        readConfiguration();
    } catch (java.io.IOException cause) {
        throw new ConfigurationLoadException(
                "Cannot initialize configuration", cause);
    }
}
~~~

Đoạn phương thức giả định `readConfiguration()` đã được định nghĩa. Vì `ConfigurationLoadException` là checked, caller cần bắt hoặc khai báo phù hợp.

**Khi hữu ích:** lỗi có ý nghĩa rõ trong hợp đồng, caller được kỳ vọng có quyết định khôi phục hoặc chuyển tiếp, và việc compile-time yêu cầu xử lý đem lại giá trị.

### 4.2. Dùng `RuntimeException` cho hợp đồng unchecked

~~~java
public final class DomainStateException
        extends RuntimeException {
    public DomainStateException(String message) {
        super(message);
    }
}
~~~

Đây là một lớp Java độc lập. Caller không bị trình biên dịch yêu cầu bắt/khai báo nó, nhưng nó vẫn có thể lan truyền và làm thao tác thất bại.

**Khi hữu ích:** một bất biến nghiệp vụ bị vi phạm, một trạng thái không hợp lệ hoặc chính sách API muốn xử lý lỗi tập trung, không áp đặt checked exception ở mọi tầng.

### 4.3. Kế thừa subclass JDK khi nó đã mang đúng nghĩa

Nếu loại lỗi riêng thực sự là một trạng thái không hợp lệ, có thể dùng:

~~~java
public final class OrderNotReadyException
        extends IllegalStateException {
    public OrderNotReadyException(String orderId) {
        super("Order " + orderId + " is not ready");
    }
}
~~~

Đây là một lớp độc lập. Nó vừa có thể được nhận bởi `catch (OrderNotReadyException e)`, vừa thuộc nhóm `IllegalStateException`.

Tuy nhiên, không nên kế thừa một lớp JDK chỉ vì tên nghe có vẻ gần. Ví dụ, một lỗi mất kết nối không phải lỗi tham số; `extends IllegalArgumentException` sẽ truyền sai ngữ nghĩa.

**Mẹo lựa chọn:** cân nhắc cả điều kiện phát sinh lỗi, cách caller dự kiến xử lý, ranh giới module và việc lớp cha có đúng ý nghĩa hay không.

## 5. Checked và unchecked: quy tắc chính xác

Java chia nhóm ngoại lệ cho mục đích kiểm tra tại biên dịch:

**Unchecked:** `RuntimeException` và tất cả subclass của nó; `Error` và tất cả subclass của nó.

**Checked:** các subclass khác của `Throwable` không nằm trong hai nhóm trên. Vì thế **`Throwable` trực tiếp và subclass trực tiếp của nó** là checked.

| Khai báo lớp | Loại | Caller có nghĩa vụ checked? |
| --- | --- | --- |
| `class A extends Exception` | Checked, trừ khi A thực sự kế thừa RuntimeException — điều này không xảy ra với câu lệnh trên | Có |
| `class B extends IOException` | Checked | Có |
| `class C extends RuntimeException` | Unchecked | Không |
| `class D extends IllegalStateException` | Unchecked | Không |
| `class E extends Error` | Unchecked | Không |
| `class F extends Throwable` | Checked | Có |

Cần phân biệt:

- **Checked** không nghĩa là “nhẹ” hay “có thể luôn sửa lỗi”.
- **Unchecked** không nghĩa là “không thể xử lý” hay “không cần log”.
- **Error** không nghĩa là mọi đối tượng được tạo ra từ nó đều do JVM tự ném.
- **Hợp đồng `throws`** mô tả khả năng ngoại lệ checked có thể truyền ra, **không** bảo đảm mọi lần gọi đều ném lỗi.

Khi một API có thể gặp `IOException` do đọc file, giữ `IOException` hoặc định nghĩa subclass checked phù hợp có thể tự nhiên hơn tạo một `Error` chỉ vì sợ viết `throws`.

## 6. Các vấn đề thực tế khi `extends Throwable` trực tiếp

### Vấn đề 1 — Bên gọi bắt `Exception` nhưng vẫn để lọt lỗi

~~~java
final class DirectIssue extends Throwable {
    DirectIssue(String message) {
        super(message);
    }
}

static void throwDirect() throws DirectIssue {
    throw new DirectIssue("direct issue");
}

static void caller() throws DirectIssue {
    try {
        throwDirect();
    } catch (Exception e) {
        System.out.println("Caught as Exception");
    }
}
~~~

Đoạn này có thể đặt các khai báo trong một lớp Java. `caller()` vẫn phải khai báo `throws DirectIssue` vì `catch (Exception)` **không bao phủ** `DirectIssue`.

Nếu thay `DirectIssue extends Throwable` bằng `DirectIssue extends Exception`, một `catch (Exception e)` phù hợp có thể bắt nó. Đó là lý do phân cấp loại ngoại lệ quan trọng hơn việc chỉ nhìn từ khóa `throw`.

### Vấn đề 2 — Chữ ký API trở nên khác thường

~~~java
public void save() throws Throwable
~~~

Đây là chữ ký minh họa. Một public API yêu cầu caller xét `Throwable` là hợp đồng rất rộng. Nó gợi ý rằng phương thức có thể ném cả những nhóm mà mã nghiệp vụ không nên được yêu cầu khôi phục theo cách thông thường.

Nếu nhóm lỗi thực sự chỉ là lỗi I/O hoặc lỗi lưu dữ liệu nghiệp vụ, hãy khai báo `throws IOException`, `throws StorageException` hoặc một nhóm ngoại lệ cụ thể theo kiến trúc.

### Vấn đề 3 — Các handler và tooling có thể không theo kỳ vọng

Code xử lý lỗi với `catch (Exception)` hoặc handler được cấu hình cho các subclass `Exception` sẽ không nhận trực tiếp subtype `Throwable` ở ngoài nhánh đó. Điều này gây ra tình huống handler có vẻ tổng quát nhưng không nhận lỗi được cho là “ngoại lệ ứng dụng”.

Không suy ra rằng tất cả framework sẽ thất bại: những hệ thống bắt `Throwable` có thể nhận. Nhưng đó không phải một lý do tốt để làm loại custom exception thông thường nằm ngoài nhánh `Exception`.

### Vấn đề 4 — Khó bảo trì hợp đồng checked

Một dự án có nhiều lớp kế thừa `Throwable` trực tiếp dễ dẫn tới các chữ ký `throws Throwable` lan rộng. Khi client muốn thu hẹp trách nhiệm, việc đổi loại ngoại lệ và làm cho phần bắt lỗi đúng ngữ nghĩa có thể tốn công.

Với mã nghiệp vụ mới, chọn lớp cha được quy ước và biểu đạt đúng trách nhiệm caller ngay từ đầu sẽ tốt hơn.

## 7. Các vấn đề thực tế khi `extends Error` cho lỗi ứng dụng

Ví dụ **thiết kế không nên áp dụng**:

~~~java
public final class CustomerNotFoundError extends Error {
    public CustomerNotFoundError(String customerId) {
        super("Customer not found: " + customerId);
    }
}
~~~

Dù mã này có thể biên dịch, “không tìm thấy khách hàng” thông thường là một trạng thái nghiệp vụ hoặc kết quả truy vấn, không phải một sự cố thuộc nhánh `Error`.

Phương án cần xét:

- Nếu “không tìm thấy” là kết quả bình thường của tra cứu: cân nhắc `Optional<Customer>` hoặc kiểu kết quả có mã `NOT_FOUND`.
- Nếu thiếu khách hàng vi phạm tiền điều kiện hoặc bất biến: có thể dùng `IllegalArgumentException`, `IllegalStateException` hoặc subclass unchecked phù hợp.
- Nếu hợp đồng API yêu cầu caller bắt cụ thể: cân nhắc một checked `CustomerNotFoundException extends Exception`.
- Nếu dự án dùng lỗi miền unchecked nhất quán: cân nhắc `CustomerNotFoundException extends RuntimeException`.

Mỗi lựa chọn có ý nghĩa riêng. Không có một câu trả lời duy nhất cho mọi ứng dụng, nhưng **`extends Error` thường không phù hợp**.

### Tác động lên các khối `catch`

~~~java
try {
    findCustomer("C-100");
} catch (Exception e) {
    // Handler dành cho các lỗi Exception.
}
~~~

Đây là đoạn minh họa. Nếu `findCustomer` ném `CustomerNotFoundError extends Error`, handler này không bắt được đối tượng đó. Điều này thường không phù hợp với kỳ vọng của tầng ứng dụng đang chuẩn bị phản hồi “không tìm thấy khách hàng”.

Nếu loại riêng kế thừa `RuntimeException` hoặc `Exception`, handler rộng `catch (Exception)` có thể nhận nó, mặc dù **vẫn nên dùng catch hẹp hơn** khi tầng hiện tại có cách xử lý riêng.

## 8. Khi nào có thể hợp lý để tạo subtype của `Error`?

Từ “tránh khi không phù hợp” không có nghĩa mã Java **cấm tuyệt đối** người phát triển tạo subclass `Error`.

Có những tình huống rất đặc biệt trong thư viện cấp thấp, công cụ nội bộ hoặc cơ chế kiểm tra bất biến mà tác giả chủ động muốn biểu đạt thất bại không thuộc hợp đồng ngoại lệ nghiệp vụ thông thường. Một số thư viện kiểm thử sử dụng `AssertionError` để báo một phép kiểm tra thất bại. `AssertionError` thuộc nhánh `Error` theo thiết kế.

Tuy nhiên, trước khi cân nhắc một subclass `Error` riêng, cần trả lời:

1. Lỗi này thực sự có ý nghĩa tương tự một vấn đề hệ thống/khẳng định nội bộ mà caller thông thường không nên xử lý không?
2. Có biết rõ điều gì xảy ra khi `catch (Exception)` không bắt được nó không?
3. Có cần hệ thống tiếp tục hoạt động sau lỗi đó không? Nếu có, dùng `Error` có thể gây hiểu nhầm.
4. Có thể dùng `AssertionError` hoặc exception chuẩn phù hợp thay vì tạo một nhánh `Error` mới không?
5. Tất cả handler và công cụ quan sát có hiểu hợp đồng bất thường này không?

Với code dịch vụ nghiệp vụ, web API, batch job, repository, validation và tích hợp thông thường, **gần như luôn có lựa chọn hợp lý hơn subclass `Error`**.

## 9. Không cần custom exception nếu loại chuẩn đã đủ

Một hệ thống đơn giản có thể chỉ cần:

~~~java
static int divide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException(
                "denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

Đây là phương thức Java hợp lệ. Không cần tạo `ZeroDenominatorThrowable extends Throwable` hoặc `ZeroDenominatorError extends Error`; cả hai sẽ làm hợp đồng khó hiểu hơn.

Tương tự:

- Đối số sai → `IllegalArgumentException`, hoặc `NullPointerException` khi một tham chiếu bắt buộc không được null.
- Trạng thái không phù hợp → `IllegalStateException`.
- Thao tác không hỗ trợ → `UnsupportedOperationException`.
- Lỗi I/O → `IOException` hoặc subtype.
- Thất bại JDBC → `SQLException` ở ranh giới tương ứng.

Nếu nhiều client phải xử lý một loại lỗi miền theo cách riêng, **lúc đó** mới cân nhắc thêm class cụ thể. Loại custom tốt phải có lợi ích rõ ràng, không chỉ có tên dài hơn.

## 10. Đừng dùng ngoại lệ cho mọi kết quả nghiệp vụ dự kiến

Một kết quả không thành công không phải lúc nào cũng là lỗi bất thường.

Ví dụ, tra cứu mặt hàng có thể không tìm thấy ID:

~~~java
static java.util.Optional<String> lookupItem(String id) {
    if ("SKU-1".equals(id)) {
        return java.util.Optional.of("Keyboard");
    }
    return java.util.Optional.empty();
}
~~~

Đây là phương thức Java hợp lệ. Caller có thể xử lý nhánh `Optional.empty()` như một kết quả dự kiến, thay vì tạo `ItemNotFoundError` hoặc `ItemNotFoundThrowable`.

Tương tự, thanh toán bị từ chối có thể được biểu diễn bằng `enum` hoặc `record` chứa trạng thái `DECLINED`. Chỉ nên dùng ngoại lệ khi hợp đồng thực sự coi tình huống là thất bại cần lan truyền, thay vì một kết quả mà caller luôn phải xét.

Bảng quyết định:

| Tình huống | Phương án thường hợp lý |
| --- | --- |
| Lỗi tham số đơn giản | Exception chuẩn như `IllegalArgumentException` |
| Lỗi trạng thái miền cần bắt riêng | Custom `RuntimeException` hoặc subtype phù hợp |
| Lỗi recoverable theo hợp đồng compile-time | Custom checked `Exception` |
| Lỗi I/O ở tầng thấp | `IOException` hoặc subclass |
| Không tìm thấy dữ liệu là kết quả dự kiến | `Optional`/result type |
| Lỗi VM hoặc sự cố rất đặc biệt ở tầng thấp | Các lớp `Error` có ý nghĩa phù hợp; không biến thành lỗi nghiệp vụ |
| Muốn “bắt hết và xử lý tiếp” | Không mặc định `catch (Throwable)`; thiết kế biên xử lý đúng loại |

## 11. Ví dụ Java 17+ chạy độc lập: so sánh bốn nhóm lỗi

Chương trình sau chứa:

1. **Checked custom exception đúng hướng** kế thừa `Exception`.
2. **Unchecked custom exception đúng hướng** kế thừa `IllegalStateException`.
3. **Direct subclass của `Throwable`** để thấy nó là checked nhưng không thuộc `Exception`.
4. **`AssertionError` chuẩn** để thấy nhánh `Error` không đi qua `catch (Exception)`. Đây là minh họa kiểm tra kiểu, không phải mẫu xử lý `Error` cho production.

Tạo tệp **`ThrowableInheritanceDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowableInheritanceDemo {

    static final class ConfigurationFailure extends Exception {
        ConfigurationFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class OrderStateFailure
            extends IllegalStateException {
        OrderStateFailure(String message) {
            super(message);
        }
    }

    // Phản ví dụ về thiết kế: chỉ dùng để so sánh phân cấp.
    static final class DirectThrowableFailure extends Throwable {
        DirectThrowableFailure(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        System.out.println("== checked ==");
        try {
            initializeConfig(true);
            System.out.println("configuration=ready");
        } catch (ConfigurationFailure e) {
            System.out.println("unexpected configuration failure");
        }

        try {
            initializeConfig(false);
        } catch (ConfigurationFailure e) {
            System.out.println(
                    "configuration=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
            System.out.println(
                    "cause=" + e.getCause().getClass().getSimpleName()
                            + ": " + e.getCause().getMessage());
        }

        System.out.println("== unchecked ==");
        try {
            verifyOrder(false);
        } catch (IllegalStateException e) {
            System.out.println(
                    "state=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("== direct Throwable ==");
        try {
            throwDirect();
        } catch (DirectThrowableFailure e) {
            System.out.println(
                    "direct=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("== Error hierarchy ==");
        try {
            throw new AssertionError("illustrative assertion");
        } catch (Exception e) {
            System.out.println("caught by Exception");
        } catch (AssertionError e) {
            System.out.println(
                    "assertion=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("app=completed");
    }

    static void initializeConfig(boolean available)
            throws ConfigurationFailure {
        try {
            readConfig(available);
        } catch (IOException cause) {
            throw new ConfigurationFailure(
                    "cannot initialize config", cause);
        }
    }

    static void readConfig(boolean available) throws IOException {
        if (!available) {
            throw new IOException("disk inaccessible");
        }
    }

    static void verifyOrder(boolean paid) {
        if (!paid) {
            throw new OrderStateFailure(
                    "cannot ship before payment");
        }
    }

    static void throwDirect() throws DirectThrowableFailure {
        throw new DirectThrowableFailure("direct root");
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac ThrowableInheritanceDemo.java
java ThrowableInheritanceDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
== checked ==
configuration=ready
configuration=ConfigurationFailure: cannot initialize config
cause=IOException: disk inaccessible
== unchecked ==
state=OrderStateFailure: cannot ship before payment
== direct Throwable ==
direct=DirectThrowableFailure: direct root
== Error hierarchy ==
assertion=AssertionError: illustrative assertion
app=completed
~~~

### Giải thích nhóm checked

`initializeConfig(true)` hoàn tất bình thường. Khi `available=false`, `readConfig` ném `IOException("disk inaccessible")`. Tầng cấu hình bọc nó thành `ConfigurationFailure` và giữ chính `IOException` trong `getCause()`. `main` bắt loại checked được khai báo; không cần `catch(Throwable)`.

### Giải thích nhóm unchecked

`OrderStateFailure extends IllegalStateException`, và `IllegalStateException extends RuntimeException`, nên ngoại lệ này là unchecked. Caller có thể `catch(IllegalStateException)` để xử lý trạng thái không cho phép thao tác. Đây là ví dụ hợp lý nếu lỗi trạng thái đơn hàng có ý nghĩa riêng trong API.

### Giải thích nhóm direct Throwable

`DirectThrowableFailure extends Throwable` không nằm dưới `Exception` hoặc `Error` nên là checked. `throwDirect()` phải khai báo `throws DirectThrowableFailure`. `main` dùng handler hẹp `catch(DirectThrowableFailure e)`. Nếu chỉ có `catch(Exception e)`, loại lỗi này **không được bắt**.

### Giải thích nhóm Error

`AssertionError` thuộc nhánh `Error`, không thuộc `Exception`. Vì thế trong khối `try` cuối, `catch (Exception e)` không chạy; `catch (AssertionError e)` chạy. Đây là **ví dụ kiểm tra đặc tính của cây kế thừa**, không phải khuyến nghị bắt và bỏ qua những `Error` không kiểm soát được.

Chương trình không cố tình gây `OutOfMemoryError`, `StackOverflowError` hay dừng JVM. Tạo các sự cố đó để “thử nghiệm” không cần thiết và có thể làm môi trường chạy không ổn định.

## 12. Mã phản ví dụ: bắt `Exception` không thể thay nghĩa của subclass `Throwable`

Xét:

~~~java
static void demonstrate() throws DirectThrowableFailure {
    try {
        throwDirect();
    } catch (Exception e) {
        System.out.println("not reached for DirectThrowableFailure");
    }
}
~~~

Đây là phương thức có thể đặt trong cùng lớp `ThrowableInheritanceDemo`.

**Tại sao cần `throws DirectThrowableFailure`?** Vì handler `catch(Exception)` không nhận subtype trực tiếp của `Throwable`. Lời gọi vẫn có khả năng truyền checked `DirectThrowableFailure` ra ngoài.

Nếu bỏ `throws DirectThrowableFailure` mà không thêm handler tương ứng, sẽ có **lỗi biên dịch** vì ngoại lệ checked chưa được bắt hoặc khai báo.

Sửa theo đúng mục tiêu nghiệp vụ không phải lúc nào cũng là thêm `catch(Throwable)`. Thường giải pháp tốt hơn là **thiết kế lại loại lỗi riêng để kế thừa `Exception`** ngay từ đầu, nếu nó thực sự là ngoại lệ checked của ứng dụng.

## 13. Có thể kế thừa một exception chuẩn chuyên biệt không?

Có, nếu điều kiện lỗi giữ **quan hệ “is-a” có ý nghĩa** với lớp cha.

Ví dụ:

~~~java
public final class InsufficientOrderStateException
        extends IllegalStateException {
    public InsufficientOrderStateException(String message) {
        super(message);
    }
}
~~~

Đây là lớp Java độc lập nếu lưu trong `InsufficientOrderStateException.java`.

Khi đó:

- `catch (InsufficientOrderStateException e)` xử lý riêng.
- `catch (IllegalStateException e)` cũng có thể nhận vì quan hệ subtype.
- `catch (RuntimeException e)` là handler rộng hơn, nhưng không nên dùng tùy tiện.

Ngược lại, một lỗi kết nối mạng không trở thành `IllegalArgumentException` chỉ vì thư viện muốn đưa nó vào nhánh unchecked. Hãy chọn superclass đúng ý nghĩa, không chỉ đúng đặc tính compile-time.

## 14. Cause và constructor của custom exception

Lựa chọn lớp cha đúng chỉ là bước đầu. Khi bọc một ngoại lệ tầng thấp, custom exception phải **bảo toàn cause** bằng constructor phù hợp.

~~~java
public final class RepositoryUnavailableException
        extends Exception {

    public RepositoryUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là một lớp độc lập. Caller có thể tạo:

~~~java
throw new RepositoryUnavailableException(
        "Repository is unavailable", sqlException);
~~~

Đây là đoạn minh họa có biến `sqlException` và cần xử lý checked exception theo hợp đồng. Constructor `super(message, cause)` giúp `getCause()` của wrapper giữ tham chiếu lỗi gốc.

**Không viết chỉ:**

~~~java
super(message + ": " + cause.getMessage());
~~~

trong constructor của lớp lỗi nếu mục tiêu là giữ cause. Nối message không làm `getCause()` của wrapper có nguyên nhân.

### Constructor không tự được kế thừa

Nếu `Exception` cung cấp constructor `(String, Throwable)`, lớp `RepositoryUnavailableException` vẫn **phải khai báo** overload tương ứng nếu muốn caller gọi được. Java không kế thừa constructor như phương thức instance.

### Đừng tắt stack trace/suppression theo mặc định

Một số lớp gốc như `Exception` và `RuntimeException` có constructor `protected` cho phép điều khiển `enableSuppression` và `writableStackTrace`. Không nên tắt hai tính năng đó chỉ để cải thiện hiệu năng giả định: nó có thể làm mất dữ liệu chẩn đoán hữu ích. Hãy đo đạc và xác định chính sách rõ ràng trước khi dùng cấu hình đặc biệt.

## 15. `Error` không đồng nghĩa “lỗi nghiêm trọng nhất cần catch”

Nhiều người mới học nghĩ rằng lỗi nặng thì kế thừa `Error`, còn lỗi nhẹ thì `Exception`. Java không dùng tiêu chí đơn giản như vậy.

Ví dụ:

- Không khởi động được một hệ thống nghiệp vụ do thiếu cấu hình có thể là sự cố **rất nghiêm trọng** đối với hoạt động, nhưng vẫn hoàn toàn có thể biểu diễn bằng một `Exception` hoặc `RuntimeException` thích hợp.
- Một `AssertionError` do test chủ động ném có thể mô tả một bất biến sai trong môi trường kiểm thử, không phải toàn bộ JVM đã hỏng.
- Một `IOException` do mất kết nối có thể đòi hỏi chính sách retry/khôi phục, không phải subclass của `Error`.
- Một `OutOfMemoryError` có thể làm chương trình không còn đủ tài nguyên để tiếp tục an toàn, nên việc catch rồi chạy tiếp là rất rủi ro.

Chọn superclass dựa vào **bản chất hợp đồng và cách phục hồi dự kiến**, không dựa vào việc người dùng có cảm thấy lỗi “nặng” hay không.

## 16. Đừng tạo một `BaseApplicationThrowable`

Một kiến trúc đôi khi bắt đầu bằng:

~~~java
public class BaseApplicationThrowable extends Throwable {
    public BaseApplicationThrowable(String message) {
        super(message);
    }
}
~~~

Đây là **phản ví dụ thiết kế** nếu định dùng cho tất cả ngoại lệ nghiệp vụ. Nó khiến mọi subclass checked của hệ thống nằm ngoài `Exception`, dẫn đến cùng vấn đề về `catch(Exception)` và chữ ký `throws`.

Nếu dự án thực sự cần một base exception để nhóm nhiều loại lỗi:

~~~java
public class ApplicationException extends Exception {
    public ApplicationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

hoặc một base unchecked:

~~~java
public class ApplicationRuntimeException extends RuntimeException {
    public ApplicationRuntimeException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Các đoạn là hai **lớp minh họa độc lập**, không phải bắt buộc phải tạo cả hai. Việc có một superclass chung chỉ hữu ích khi có một **hợp đồng chung thực sự**; không cần xây phân cấp sâu chỉ để thỏa một sơ đồ OOP.

## 17. Khi nào nên bắt `Throwable` ở ranh giới đặc biệt?

Một số môi trường hệ thống muốn ghi nhận thất bại của một đơn vị thực thi, ngay cả khi lỗi không nằm trong nhánh `Exception`. Khi đó có thể thấy:

~~~java
try {
    executePlugin();
} catch (Throwable failure) {
    recordFailure(failure);
    throw failure;
}
~~~

Đây là **mảnh mã minh họa**, trong đó `executePlugin` và `recordFailure` do hệ thống cung cấp; phương thức bao quanh phải đáp ứng quy tắc checked exception và kiểu được ném lại.

Đặc điểm quan trọng là handler **ghi nhận rồi ném tiếp**, không ngầm tuyên bố mọi `Error` đều có thể phục hồi.

Trong thực tế, nếu cần xử lý cả `Error` và `Exception` ở một ranh giới framework, phải có phân tích cụ thể về:

- Tài nguyên còn có thể hoạt động an toàn hay không.
- Mức độ thu hồi trạng thái sau `OutOfMemoryError` hoặc `LinkageError`.
- Cách tránh vòng lặp ghi log hoặc lỗi thứ cấp do thiếu bộ nhớ.
- Việc báo cáo lỗi một lần và quyết định dừng/tái khởi động ở đâu.
- Hợp đồng của thư viện/framework trong môi trường thực tế.

**Đây là trường hợp đặc biệt, không phải lý do để tạo custom `Error` cho nghiệp vụ.**

## 18. Khác biệt với `finally` và try-with-resources

Một số người chọn `Error` vì muốn làm cho lỗi “thoát nhanh” qua các handler. Nhưng `Error` **không tự bỏ qua các khối `finally`** khi Java rời cấu trúc `try` theo luồng ngoại lệ bình thường.

Ví dụ:

~~~java
try {
    throw new AssertionError("assertion failed");
} finally {
    System.out.println("cleanup");
}
~~~

Đây là đoạn minh họa. `finally` vẫn được thực thi trước khi `AssertionError` tiếp tục truyền ra ngoài, miễn là luồng Java còn thực hiện được quá trình rời `try`.

Tuy nhiên, những sự cố làm JVM/tiến trình không thể tiếp tục (kill cưỡng bức, `Runtime.halt`, crash, mất điện) không được bảo đảm có cơ hội dọn dẹp. Sự khác nhau ở đây là **cách JVM/tiến trình kết thúc**, không phải cứ là subtype `Error` thì “bỏ qua finally”.

Try-with-resources cũng hoạt động khi mã Java có cơ hội rời scope; nó không trở thành cơ chế chống mất dữ liệu do VM dừng cưỡng bức.

## 19. Cách thiết kế API không buộc caller bắt nhầm `Error`

Một API tốt phân định:

1. **Lỗi mà caller cần xử lý theo hợp đồng**.
2. **Lỗi lập trình hoặc vi phạm trạng thái**.
3. **Sự cố môi trường nghiêm trọng** mà ứng dụng không tự giải quyết ở mỗi lời gọi.
4. **Kết quả nghiệp vụ dự kiến**.

Ví dụ API đọc cấu hình có thể chọn:

~~~java
public Configuration read(String path)
        throws ConfigurationLoadException
~~~

Đây là chữ ký minh họa. Nó cho caller biết một checked failure có ý nghĩa rõ: đọc cấu hình có thể thất bại.

Một API thực thi thao tác trạng thái có thể chọn unchecked `IllegalStateException` hay một subtype cụ thể để báo bất biến bị vi phạm.

Một API tra cứu không tìm thấy dữ liệu có thể trả `Optional.empty()` thay vì ném exception.

Không cần quảng bá `throws Throwable` hoặc cho caller bắt `Error` chỉ để “bao trùm mọi tình huống”. API càng đúng phạm vi, caller càng dễ viết mã hợp lệ.

## 20. Câu hỏi cần trả lời trước khi chọn superclass

| Câu hỏi | Hướng suy nghĩ |
| --- | --- |
| Caller có được yêu cầu xử lý/khai báo lỗi lúc biên dịch không? | Chọn checked `Exception` hoặc subtype phù hợp |
| Lỗi là vi phạm trạng thái/tiền điều kiện? | `RuntimeException` hoặc subclass JDK phù hợp |
| Có cần type riêng để phân biệt hành động? | Custom subtype trong nhánh đúng |
| Đây là kết quả dự kiến thay vì ngoại lệ? | Xem `Optional`, enum, record hoặc result type |
| Có đang định dùng `Throwable` để tránh chọn nhánh? | Dừng và xác định hợp đồng chính xác |
| Có đang định dùng `Error` vì không thích `throws`? | Dùng unchecked `RuntimeException` nếu ngữ nghĩa phù hợp |
| Có thật sự là cơ chế VM/framework đặc biệt không? | Chỉ cân nhắc nhánh đặc biệt khi hiểu đầy đủ hậu quả |
| Có cần giữ nguyên nhân tầng thấp không? | Constructor `(String, Throwable)` với `super(message, cause)` |

Nếu bạn không thể nêu rõ một lợi ích cụ thể của việc trực tiếp kế thừa `Throwable` hoặc `Error`, đó là tín hiệu mạnh rằng chúng **không phù hợp**.

## 21. Những hiểu lầm và lỗi thường gặp

### 21.1. “`Throwable` là lớp cha của tất cả lỗi nên kế thừa trực tiếp sẽ linh hoạt hơn”

Đúng là `Throwable` là gốc, nhưng trực tiếp kế thừa nó khiến custom type nằm ngoài `Exception`, trở thành checked và không được `catch(Exception)` nhận. Đó thường là **mất tương thích về kỳ vọng**, không phải tăng linh hoạt.

### 21.2. “Một lỗi nặng phải kế thừa `Error`”

Sai. Mức độ ảnh hưởng kinh doanh không phải tiêu chí phân nhánh trong cây `Throwable`. Lỗi cấu hình khiến dịch vụ không khởi động vẫn có thể là custom `Exception`.

### 21.3. “`Error` luôn là lỗi do JVM tự ném”

Không. Code có thể tự `throw new AssertionError(...)`, và cũng có thể định nghĩa subtype `Error`. Vấn đề nằm ở ý nghĩa và cách hệ thống xử lý, không phải cú pháp.

### 21.4. “`Error` không bao giờ được bắt”

Không nên diễn giải tuyệt đối. Có trường hợp kiểm thử hoặc ranh giới hệ thống đặc biệt bắt một loại `Error` cụ thể. Tuy nhiên, **bắt mọi `Error` rồi tiếp tục nghiệp vụ như bình thường là thực hành nguy hiểm**.

### 21.5. “`catch(Exception)` bắt mọi `Throwable`”

Sai. Nó không bắt `Error` và không bắt subtype trực tiếp khác của `Throwable` nằm ngoài `Exception`.

### 21.6. “`catch(Throwable)` luôn tốt hơn vì tổng quát”

Không. Nó có thể gom các lỗi mà ứng dụng không có cách khôi phục an toàn. Dùng handler hẹp nhất phù hợp trách nhiệm của tầng.

### 21.7. “Nếu kế thừa `RuntimeException` thì lỗi sẽ không làm chương trình dừng”

Sai. Unchecked vẫn được ném, truyền và có thể làm tác vụ kết thúc bất thường. Unchecked chỉ không buộc `catch`/`throws` theo luật checked.

### 21.8. “`extends Throwable` thì là unchecked vì Throwable ở cấp cao nhất”

Sai. Những subtype của `Throwable` không nằm dưới `RuntimeException` hay `Error` là checked.

### 21.9. “`throws Throwable` mô tả API tốt hơn `throws IOException`”

Thường không. Một chữ ký quá rộng làm caller khó biết lỗi nào thực sự là hợp đồng có thể phục hồi.

### 21.10. “Một custom exception bắt buộc phải kế thừa trực tiếp `Exception`”

Không. Có thể kế thừa `RuntimeException` hoặc subclass như `IllegalStateException`, hoặc một lớp checked chuyên biệt phù hợp. Quan trọng là superclass đúng ngữ nghĩa.

### 21.11. “Cứ đổi lớp cha thành `Error` để khỏi thêm `throws`”

Sai định hướng. Nếu muốn unchecked vì hợp đồng, cân nhắc `RuntimeException`. `Error` mang ý nghĩa khác.

### 21.12. “Tên lớp có chữ Error sẽ khiến nó thuộc nhánh `Error`”

Không. Phân loại phụ thuộc `extends`, không phải tên. Dù vậy, đặt tên `SomethingError` cho loại kế thừa `RuntimeException` có thể vẫn gây hiểu lầm, nên đặt tên phản ánh vai trò.

### 21.13. “Lỗi trong `finally` chỉ xảy ra với `Exception`”

Không. Một `Throwable` bất kỳ có thể truyền qua cấu trúc `try/finally`; luật thực thi `finally` không phụ thuộc tên lớp ngoại lệ.

### 21.14. “Kế thừa `Error` là cách biểu diễn business rejection”

Không. Một quyết định từ chối hợp lệ nên được thiết kế bằng result/enum nếu phù hợp; nếu là lỗi nghiệp vụ bất thường thì dùng exception đúng nhánh.

### 21.15. “Constructor của lớp cha tự được kế thừa”

Không. Khi custom exception cần message/cause, phải khai báo constructor và gọi `super(...)` phù hợp.

### 21.16. “Bọc lỗi bằng một message mới đã giữ nguyên cause”

Không. Chỉ sao chép `cause.getMessage()` không tạo liên kết cause. Truyền đối tượng gốc tới constructor hoặc cơ chế thiết lập nguyên nhân hợp lệ.

## 22. Tự kiểm tra kiến thức

1. `Throwable` khác `Exception` và `Error` trong cây kế thừa như thế nào?
2. `class X extends Throwable` là checked hay unchecked? Vì sao?
3. `class Y extends Error` là checked hay unchecked?
4. Một `catch (Exception e)` có bắt được `DirectThrowableFailure extends Throwable` không?
5. Một `catch (Exception e)` có bắt được `AssertionError` không?
6. Vì sao `throws Throwable` thường là chữ ký quá rộng cho API nghiệp vụ?
7. Khi nào nên chọn `extends Exception` cho lớp lỗi riêng?
8. Khi nào nên chọn `extends RuntimeException`?
9. Vì sao không nên chọn `extends Error` chỉ để tránh `throws`?
10. Một sự cố cấu hình rất nghiêm trọng có nhất thiết là `Error` không?
11. Nếu lỗi trạng thái đơn hàng có nghĩa miền riêng, bạn có thể kế thừa lớp chuẩn nào?
12. Nếu người dùng nhập tham số sai đơn giản, có nhất thiết phải tạo custom exception không?
13. Có thể dùng `Optional.empty()` cho trạng thái không tìm thấy dự kiến không?
14. Chọn `Error` cho lỗi nghiệp vụ có thể khiến handler nào bỏ sót nó?
15. `throw new AssertionError("x")` có làm `finally` bị bỏ qua theo luồng ngoại lệ thông thường không?
16. Một custom checked exception có cần khai báo trong `throws` khi lan ra caller không?
17. Nếu custom unchecked exception không bị bắt, có thể xảy ra gì?
18. `getCause()` giúp gì khi chuyển lỗi hạ tầng thành lỗi nghiệp vụ?
19. Khi nào một `catch(Throwable)` đặc biệt có thể tồn tại hợp lý?
20. Khi bắt lỗi `Error` ở một ranh giới đặc biệt, vì sao không nên mặc định tiếp tục công việc?
21. Tại sao subtype của `IllegalStateException` có thể phù hợp hơn subtype trực tiếp của `RuntimeException` trong một số trường hợp?
22. Hai loại lỗi khác nhau về thông điệp có bắt buộc cần hai subclass không?
23. Nếu thư viện định nghĩa `BaseApplicationThrowable extends Throwable` cho tất cả lỗi, vấn đề compile-time là gì?
24. Constructor `(String, Throwable)` trong custom exception nên gọi gì?
25. Có nên đặt logic nghiệp vụ trong message exception để caller parse không?

### Gợi ý đáp án

1. `Throwable` là lớp gốc; `Exception` và `Error` là hai nhánh con trực tiếp quan trọng.
2. Checked, vì không nằm dưới `RuntimeException` hay `Error`.
3. Unchecked.
4. Không.
5. Không.
6. Nó bắt caller xét nhóm rất rộng, kể cả những loại không phù hợp với hợp đồng ứng dụng.
7. Khi caller được kỳ vọng bắt hoặc khai báo lỗi có thể xử lý theo hợp đồng.
8. Khi dùng unchecked exception đúng ý nghĩa và không muốn buộc checked handling ở mỗi tầng.
9. `Error` có ý nghĩa đặc biệt; chọn `RuntimeException` nếu thực sự cần unchecked cho nghiệp vụ.
10. Không; mức độ nghiêm trọng không đồng nghĩa nhánh `Error`.
11. Ví dụ `IllegalStateException`.
12. Không; `IllegalArgumentException` có thể đủ.
13. Có, nếu hợp đồng coi đó là kết quả dự kiến.
14. Ví dụ handler `catch(Exception)`.
15. Không, `finally` thông thường vẫn chạy nếu luồng Java rời `try`.
16. Có, khi không được bắt và thuộc checked exception.
17. Nó vẫn có thể truyền lên ngoài và làm tác vụ thất bại.
18. Bảo toàn nguyên nhân và stack trace gốc.
19. Trong một số ranh giới framework/VM cần ghi nhận rồi xử lý theo chính sách đặc biệt.
20. Vì có thể thiếu tài nguyên hoặc hệ thống đã ở trạng thái không an toàn.
21. Vì nó giữ đúng ý nghĩa “trạng thái không phù hợp” đồng thời cho phép handler rộng theo superclass.
22. Không, nếu caller không xử lý khác và loại chuẩn cùng message đã đủ.
23. Các subtype vẫn là checked nhưng không thuộc `Exception`; `catch(Exception)` không bao phủ.
24. `super(message, cause)` khi superclass hỗ trợ.
25. Không; dùng kiểu lỗi hoặc mã lỗi có cấu trúc.

## 23. Tổng kết

**Kế thừa trực tiếp `Throwable` hoặc `Error` không bị cấm tuyệt đối, nhưng thường sai mục đích trong custom exception của ứng dụng.** Subtype trực tiếp của `Throwable` là checked nhưng không nằm trong nhánh `Exception`, dễ gây bất ngờ cho caller và handler. Subtype `Error` là unchecked nhưng mang ngữ nghĩa lỗi đặc biệt, không phải đường tắt thay cho `RuntimeException` khi muốn tránh `throws`.

Hãy chọn **`Exception` cho custom checked exception**, **`RuntimeException` hoặc subclass chuyên biệt phù hợp cho custom unchecked exception**, và **các exception có sẵn hoặc kiểu kết quả** khi chúng đã diễn đạt đủ. Một lớp ngoại lệ tốt phải giúp caller hiểu, phân biệt hoặc xử lý tình huống đúng hơn — không chỉ làm cây kế thừa phức tạp hơn.