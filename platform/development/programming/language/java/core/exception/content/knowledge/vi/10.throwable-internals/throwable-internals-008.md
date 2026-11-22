# `getCause()`, `initCause()` và điều kiện khởi tạo nguyên nhân của `Throwable` trong Java

Trong Java, một ngoại lệ có thể được tạo **do một ngoại lệ khác gây ra**. Đối tượng gốc được gọi là *cause* (nguyên nhân); đối tượng ngoại lệ bao bên ngoài thường bổ sung ngữ cảnh ở một tầng xử lý cao hơn. `Throwable.getCause()` cho phép truy ngược nguyên nhân, còn `Throwable.initCause(Throwable)` hỗ trợ **gắn nguyên nhân sau khi tạo đối tượng** trong những điều kiện rất cụ thể.

Điểm quan trọng nhất của bài:

> **`getCause() == null` không có nghĩa là chắc chắn được gọi `initCause(...)`.** Java phân biệt trạng thái cause **chưa được khởi tạo** với trạng thái cause **đã được khởi tạo bằng `null`**.

Cùng thấy `getCause()` trả `null`, nhưng hai đối tượng tạo bởi `new Throwable("message")` và `new Throwable("message", null)` lại có quyền gọi `initCause(...)` khác nhau.

Bài này giải thích sự khác biệt đó, quan hệ với các constructor, cách tạo chuỗi nguyên nhân có ý nghĩa, những ngoại lệ do chính `initCause` ném ra, và các tình huống nên dùng constructor thay vì thiết lập cause muộn. Các ví dụ tương thích Java 17+.

## 1. Cause trong ngoại lệ Java là gì?

Ví dụ ứng dụng đang đọc cấu hình từ tệp. Lỗi tầng thấp là `IOException`, nhưng tầng khởi tạo dịch vụ muốn báo rằng **không thể khởi tạo dịch vụ**:

~~~java
try {
    readConfiguration();
} catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Không thể khởi tạo dịch vụ", original);
}
~~~

Đây là **đoạn minh họa** giả định phương thức `readConfiguration()` có thể ném `IOException`.

Trong ví dụ:

- `original` là ngoại lệ I/O ban đầu.
- `new IllegalStateException("...", original)` tạo một đối tượng ngoại lệ **mới** với thông điệp của tầng dịch vụ.
- Constructor nhận cause giữ **tham chiếu đến chính ngoại lệ `original`**.
- Lệnh `throw` ném đối tượng `IllegalStateException` mới.
- Caller nhận lỗi tầng dịch vụ có thể gọi `getCause()` để truy tìm lỗi I/O.

Mô hình:

~~~text
IllegalStateException: Không thể khởi tạo dịch vụ
    |
    +-- getCause() --> IOException: Không đọc được cấu hình
                           |
                           +-- getCause() --> null
~~~

**Cause là một mối liên kết giữa những đối tượng `Throwable`, không phải bản sao chuỗi message.** Nếu một ngoại lệ có cause, Java có thể hiển thị quan hệ `Caused by:` khi in stack trace, hỗ trợ chẩn đoán các lớp nguyên nhân.

Chuỗi nguyên nhân có thể có nhiều tầng:

~~~text
ServiceInitializationException
    -> ConfigurationException
        -> IOException
            -> FileNotFoundException
~~~

Đây là **sơ đồ khái niệm**; kiểu cụ thể trong ứng dụng có thể khác. Việc bọc quá nhiều lớp không hữu ích nếu mỗi lớp không bổ sung ngữ nghĩa hoặc hợp đồng đáng kể.

## 2. `getCause()` đọc gì, trả gì?

Chữ ký API cơ bản:

~~~java
public synchronized Throwable getCause()
~~~

Đây là **chữ ký minh họa API**, không phải một khai báo cần chép vào chương trình. `getCause()` trả về tham chiếu đến đối tượng `Throwable` được lưu làm nguyên nhân trực tiếp; nếu không có nguyên nhân được biểu lộ thì trả `null`.

~~~java
java.io.IOException root =
        new java.io.IOException("Đọc thất bại");

IllegalStateException outer =
        new IllegalStateException("Khởi tạo thất bại", root);

System.out.println(outer.getCause() == root); // true
System.out.println(outer.getCause().getMessage()); // Đọc thất bại
~~~

Trong đoạn trên, toán tử `==` cho thấy cause **đúng là cùng đối tượng** `root`, không phải ngoại lệ được tạo lại.

### Cause trực tiếp khác cause sâu nhất

`getCause()` chỉ trả **một bước nguyên nhân trực tiếp**. Nếu A bọc B và B bọc C:

~~~text
A.getCause() == B
B.getCause() == C
C.getCause() == null
~~~

Muốn tìm lỗi gốc, ứng dụng có thể lần theo chuỗi. Tuy nhiên không nên viết một vòng lặp mù quáng cho hệ thống nhận `Throwable` từ các nguồn không tin cậy: do code tùy biến hoặc cấu trúc bất thường, chuỗi cause **có thể tạo vòng**, nên thuật toán phân tích cần tránh lặp vô hạn. Phần sau có ví dụ xử lý an toàn.

### Giá trị `null` là trạng thái công khai, không phải “cờ chưa khởi tạo”

Người gọi `getCause()` chỉ quan sát được “không có cause được trả về”. Giá trị đó **không cho biết** constructor đã thiết lập cause hay chưa. Trạng thái nội bộ của `Throwable` mới quyết định `initCause(...)` có hợp lệ.

## 3. Tất cả các constructor liên quan tới khả năng gọi `initCause`

`Throwable` cung cấp nhiều constructor. Hai nhóm cần phân biệt:

| Cách tạo `Throwable` | `getCause()` ban đầu | Trạng thái cause cho `initCause` |
| --- | --- | --- |
| `new Throwable()` | `null` | **Chưa khởi tạo**, có thể gắn một lần |
| `new Throwable("message")` | `null` | **Chưa khởi tạo**, có thể gắn một lần |
| `new Throwable((Throwable) null)` | `null` | **Đã khởi tạo bằng null**, không gắn lại |
| `new Throwable(root)` | `root` | **Đã khởi tạo**, không gắn lại |
| `new Throwable("message", null)` | `null` | **Đã khởi tạo bằng null**, không gắn lại |
| `new Throwable("message", root)` | `root` | **Đã khởi tạo**, không gắn lại |
| Constructor `protected` bốn tham số có cause | Tương ứng giá trị cause truyền vào | **Đã khởi tạo**, kể cả khi cause là null |

Chú ý các overload `Throwable(Throwable)` và `Throwable(String, Throwable)`: chúng **khởi tạo trạng thái cause ngay tại constructor**. Điều này vẫn đúng nếu đối số `cause` bằng `null`.

Ví dụ đối chiếu:

~~~java
Throwable a = new Throwable("A");
Throwable b = new Throwable("B", null);

System.out.println(a.getCause() == null); // true
System.out.println(b.getCause() == null); // true

a.initCause(new java.io.IOException("root")); // Hợp lệ.
b.initCause(new java.io.IOException("root")); // Ném IllegalStateException.
~~~

Đoạn này **cố ý chứa lệnh gây lỗi runtime ở cuối** để chỉ ra sự khác biệt. Không chạy nó không có `try/catch` nếu muốn chương trình tiếp tục.

Tương tự, constructor nhận duy nhất `Throwable cause` cũng đánh dấu cause là đã khởi tạo ngay cả khi nhận null:

~~~java
Throwable noCause = new Throwable((Throwable) null);
System.out.println(noCause.getCause()); // null
noCause.initCause(new Exception("later")); // IllegalStateException
~~~

Việc ép kiểu `(Throwable) null` khiến người đọc biết chính xác overload nào được gọi.

## 4. Vì sao tồn tại trạng thái “chưa khởi tạo” dù getter trả null?

Trong cách triển khai chuẩn của `Throwable`, trạng thái cause được biểu diễn bằng một giá trị đánh dấu riêng trước khi người dùng thiết lập cause, cho phép `getCause()` trả `null` ở trạng thái đó và phân biệt nó với “đã gán null”. Không nên viết code phụ thuộc vào trường nội bộ hay cố sửa nó bằng reflection.

Có thể hình dung bằng sơ đồ trạng thái **khái niệm**:

~~~text
Tạo với Throwable() hoặc Throwable(String)
                 |
                 v
       [CAUSE CHƯA KHỞI TẠO]
             |        |
             |        +--> getCause() trả null
             |
             +--> initCause(root) thành công
             |       |
             |       v
             |  [CAUSE ĐÃ KHỞI TẠO: root]
             |
             +--> initCause(null) thành công
                     |
                     v
               [CAUSE ĐÃ KHỞI TẠO: null]

Tạo với Throwable(cause) hoặc Throwable(message, cause)
                 |
                 v
       [CAUSE ĐÃ KHỞI TẠO: cause]
                 |
                 +--> mọi initCause(...) sau đó bị từ chối
~~~

Ngay cả khi người dùng gọi `initCause(null)`, trạng thái đã chuyển thành **đã khởi tạo**. Không có cơ chế công khai để hoàn nguyên về chưa khởi tạo.

### Không suy luận dựa trên `getCause() == null`

Mẫu kiểm tra sau là **sai về ý nghĩa**:

~~~java
if (problem.getCause() == null) {
    problem.initCause(root);
}
~~~

`problem` và `root` ở đây là các biến giả định có sẵn. Nếu `problem` được tạo bằng constructor `(String, Throwable)` với cause `null`, điều kiện `getCause() == null` là đúng nhưng `initCause(root)` vẫn ném `IllegalStateException`.

Thực hành tốt hơn: lựa chọn một trong hai con đường ngay tại nơi tạo đối tượng:

- Truyền cause **trong constructor** khi lớp hỗ trợ overload đó.
- Nếu chỉ có constructor không nhận cause và API cho phép, gọi `initCause` **một lần ngay sau khi tạo**.

Đừng thiết kế luồng “đọc getter rồi đoán xem có được initCause không”.

## 5. `initCause(Throwable cause)` hoạt động thế nào?

Chữ ký API:

~~~java
public synchronized Throwable initCause(Throwable cause)
~~~

Phương thức này thiết lập nguyên nhân cho đối tượng `Throwable` hiện tại **khi trạng thái cause chưa được khởi tạo**.

~~~java
Throwable outer = new Throwable("Không thể tiếp tục");
java.io.IOException root =
        new java.io.IOException("Kết nối hỏng");

Throwable returned = outer.initCause(root);

System.out.println(outer.getCause() == root); // true
System.out.println(returned == outer);        // true
~~~

Hai phép so sánh đều là `true`:

1. `outer.getCause()` trỏ tới đối tượng `root`.
2. `initCause(...)` trả về **chính đối tượng `outer`**, không tạo một đối tượng `Throwable` khác.

Dữ liệu message và stack trace đã có của `outer` không bị tự động thay bằng dữ liệu của `root`. `initCause` chỉ nhằm thiết lập quan hệ nguyên nhân.

### Điều kiện thành công

Một lời gọi `initCause(cause)` hợp lệ khi đáp ứng các yêu cầu của hành vi mặc định `Throwable`:

- Cause của đối tượng nhận **chưa được khởi tạo trước đó**.
- `cause` **không phải chính đối tượng nhận** (`cause != this`).
- Không có ràng buộc khác do lớp con triển khai theo hợp đồng của nó.

Sau thành công, khả năng thiết lập cause theo phương thức này đã được dùng hết. Thêm cause thứ hai không phải một thao tác hợp lệ.

### Khi nào nên dùng?

Mục đích ban đầu của `initCause` là hỗ trợ những lớp ngoại lệ không cung cấp constructor nhận cause, đặc biệt khi cần tương thích với những API có từ trước.

Ví dụ lớp lỗi tùy biến cũ:

~~~java
public class LegacyProblem extends Exception {
    public LegacyProblem(String message) {
        super(message);
    }
}
~~~

Giả sử API lớp này chỉ cung cấp constructor message:

~~~java
LegacyProblem outer =
        new LegacyProblem("Lỗi nghiệp vụ");
outer.initCause(new java.io.IOException("Hỏng kết nối"));
throw outer;
~~~

Đây là đoạn minh họa trong một phương thức có khai báo/bắt checked `LegacyProblem` thích hợp. Vì constructor `LegacyProblem(String)` gọi `super(message)` và không thiết lập cause, `initCause` có thể gắn nguyên nhân một lần.

Với mã mới do bạn kiểm soát, nên cân nhắc bổ sung constructor `LegacyProblem(String, Throwable)` vào lớp hơn là bắt mọi caller dùng `initCause` hai bước.

## 6. `IllegalStateException`: cause đã được khởi tạo

Lỗi phổ biến nhất:

~~~java
Throwable problem = new Throwable(
        "Không đọc được dữ liệu", null);

problem.initCause(new java.io.IOException("I/O"));
// Runtime: IllegalStateException
~~~

Tuy `problem.getCause()` ban đầu là `null`, constructor `Throwable(String, Throwable)` đã khởi tạo trạng thái cause. Vì vậy `initCause` không còn hợp lệ.

Một tình huống khác:

~~~java
Throwable error = new Throwable("Lỗi");
error.initCause(new java.io.IOException("Lỗi lần đầu"));
error.initCause(new java.io.IOException("Lỗi lần hai"));
// Runtime: IllegalStateException
~~~

`initCause` thành công ở lần đầu, nhưng **không thay thế được** nguyên nhân trong lần sau.

### `initCause(null)` cũng chiếm quyền khởi tạo

~~~java
Throwable problem = new Throwable("Lỗi");
problem.initCause(null);
System.out.println(problem.getCause()); // null

problem.initCause(new Exception("Lý do mới"));
// Runtime: IllegalStateException
~~~

Nếu gọi `initCause(null)`, bạn đã đưa ra quyết định “cause là null”. Không thể đảo lại bằng cách gọi `initCause` thêm lần nữa.

Vì vậy, tránh coi `initCause(null)` là câu lệnh “reset”. Nó **không reset trạng thái** về chưa khởi tạo.

## 7. `IllegalArgumentException`: không được tự làm cause của chính mình

Tình huống tự tham chiếu trực tiếp:

~~~java
Throwable problem = new Throwable("Lỗi");
problem.initCause(problem);
// Runtime: IllegalArgumentException
~~~

Java không cho một `Throwable` thiết lập **chính nó** thành nguyên nhân trực tiếp của nó. Tự tham chiếu trực tiếp như vậy không tạo thêm ngữ nghĩa, có thể khiến việc duyệt chuỗi cause rơi vào vòng lặp.

**Điểm khác biệt cần nhớ:**

- Cause đã được khởi tạo trước: lỗi `IllegalStateException`.
- Cause là chính đối tượng nhận: lỗi `IllegalArgumentException` trong tình huống chưa khởi tạo phù hợp.
- Cause bằng `null` trong lần thiết lập đầu: hợp lệ nếu trạng thái chưa khởi tạo; nhưng nó vẫn là một lần khởi tạo.

Không nên viết logic nghiệp vụ phụ thuộc vào **thứ tự ưu tiên giữa nhiều điều kiện sai đồng thời**, trừ khi API của phiên bản và lớp cụ thể cam kết rõ. Hãy luôn tránh cả hai điều kiện.

### Chuỗi cause có thể tạo vòng gián tiếp

Việc cấm `problem.initCause(problem)` chỉ ngăn **tự tham chiếu trực tiếp**. Không nên suy ra mọi vòng tham chiếu gián tiếp đều bị mọi API ngăn tự động:

~~~java
Throwable a = new Throwable("A");
Throwable b = new Throwable("B");

a.initCause(b);
b.initCause(a);
~~~

Đây là **đoạn minh họa không nên áp dụng**: hai đối tượng khác nhau có thể tạo chuỗi A → B → A. Một thuật toán tự viết chỉ lặp `current = current.getCause()` cho tới khi gặp `null` sẽ có nguy cơ không dừng. Các công cụ hiển thị stack trace có thể có bảo vệ riêng; mã duyệt tùy biến vẫn phải được thiết kế an toàn.

## 8. Constructor cause-only và ý nghĩa của message

Các constructor thường gặp của `Throwable`:

~~~java
new Throwable()
new Throwable("message")
new Throwable(cause)
new Throwable("message", cause)
~~~

Dạng `Throwable(Throwable cause)` vừa thiết lập cause vừa tạo message từ `cause.toString()` khi cause khác `null`:

~~~java
Throwable root =
        new IllegalArgumentException("Tuổi không hợp lệ");

Throwable outer = new Throwable(root);

System.out.println(outer.getMessage());
// java.lang.IllegalArgumentException: Tuổi không hợp lệ
~~~

Cần phân biệt:

- `root.getMessage()`: `"Tuổi không hợp lệ"`.
- `root.toString()`: thường là `"java.lang.IllegalArgumentException: Tuổi không hợp lệ"`.
- `outer.getMessage()` từ constructor cause-only: bằng chuỗi tạo từ `root.toString()`.

Với constructor nhận cả message và cause, message độc lập:

~~~java
Throwable outer = new Throwable(
        "Không thể hoàn thành đăng ký", root);

System.out.println(outer.getMessage());
// Không thể hoàn thành đăng ký
~~~

Hai dạng constructor đều khởi tạo cause, nên `initCause(...)` **không thể dùng để thay đổi**.

### Constructor nhận null có overload dễ nhầm

Dùng:

~~~java
Throwable messageNull = new Throwable((String) null);
Throwable causeNull = new Throwable((Throwable) null);
~~~

Sự khác biệt:

- `messageNull` được tạo bằng constructor `(String)` nên trạng thái cause chưa khởi tạo.
- `causeNull` được tạo bằng constructor `(Throwable)` nên trạng thái cause đã khởi tạo bằng `null`.

Cả hai đều trả `null` từ `getMessage()` và `getCause()` ban đầu, nhưng quyền gọi `initCause(...)` khác nhau.

Đặc biệt, câu lệnh `new Throwable(null)` **không biên dịch** do Java không biết chọn overload `Throwable(String)` hay `Throwable(Throwable)` vì hai kiểu này không có quan hệ subtype phù hợp để chọn một overload cụ thể nhất. Sử dụng ép kiểu nếu cần truyền `null` chủ động.

## 9. Constructor bốn tham số và nguyên nhân

`Throwable` còn có constructor `protected`:

~~~java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

Nó cho phép lớp con điều khiển khả năng lưu suppressed exceptions và ghi stack trace. Nhưng đối với `initCause`, điểm quan trọng là **constructor này vẫn khởi tạo cause ngay lúc tạo đối tượng**, kể cả khi truyền `null`.

Ví dụ lớp con:

~~~java
public final class DomainProblem extends Exception {
    public DomainProblem(
            String message,
            Throwable cause,
            boolean enableSuppression,
            boolean writableStackTrace) {
        super(message, cause, enableSuppression, writableStackTrace);
    }
}
~~~

Đây là một **lớp độc lập** nếu lưu trong `DomainProblem.java`. `Exception` có overload protected tương ứng để lớp con gọi `super(...)`.

Ví dụ dùng:

~~~java
DomainProblem problem =
        new DomainProblem("Lỗi đặc biệt", null, true, false);

System.out.println(problem.getCause()); // null
System.out.println(problem.getStackTrace().length); // 0

problem.initCause(new java.io.IOException("Nguyên nhân"));
// Runtime: IllegalStateException
~~~

**Cờ `writableStackTrace` không quyết định quyền gắn cause.** Trong ví dụ, cause đã được khởi tạo bằng `null`; stack trace tắt là một lựa chọn cấu hình độc lập.

Tương tự, tắt `enableSuppression` chỉ ảnh hưởng khả năng giữ `getSuppressed()`, không có nghĩa mở lại khả năng `initCause`.

## 10. Khi bọc checked và unchecked exceptions

Cause có ích khi một tầng gọi cần **chuyển cách biểu đạt lỗi** mà vẫn giữ nguồn gốc.

~~~java
static int readPort(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Cổng không phải số nguyên: " + text, cause);
    }
}
~~~

Đây là một phương thức Java minh họa. `NumberFormatException` cũng là unchecked; nó được bọc để bổ sung ngữ cảnh cổng mạng và giữ liên kết cause.

Với checked exception:

~~~java
static String loadRequired(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Thiếu cấu hình bắt buộc", cause);
    }
}
~~~

Ở đây, `IOException` là checked, nhưng ngoại lệ mới `IllegalStateException` là unchecked. Quy tắc `catch` và `throws` với caller phụ thuộc **loại ngoại lệ thực tế được ném ra ở tầng ngoài**, không phải chỉ loại của cause. `catch (IOException e)` ở caller **không tự động bắt `IllegalStateException`** vì nó có cause là `IOException`.

Có nên đổi checked thành unchecked hay không là một quyết định API/kiến trúc; đừng bọc mọi ngoại lệ theo thói quen. Đặc biệt không nên tạo hàng loạt wrapper vô nghĩa chỉ làm chuỗi cause sâu hơn mà không bổ sung ngữ cảnh.

## 11. `getCause()` không phải `getSuppressed()`

Hai quan hệ trong `Throwable` có mục đích riêng.

**Cause:** lý do nền tảng khiến một ngoại lệ khác được tạo. Ví dụ `IllegalStateException("Khởi tạo thất bại", ioError)` có `ioError` là cause.

**Suppressed:** các ngoại lệ phụ được lưu **cùng một ngoại lệ chính**, ví dụ lỗi khi đóng tài nguyên trong try-with-resources:

~~~java
Throwable primary = new Throwable("Thao tác thất bại");

primary.addSuppressed(
        new java.io.IOException("Đóng tài nguyên thất bại"));

System.out.println(primary.getCause()); // null
System.out.println(primary.getSuppressed().length); // 1
~~~

Đoạn trên cho thấy suppressed exception **không** trở thành cause tự động. `getCause()` vẫn là `null` dù `getSuppressed().length` là `1`.

Điều ngược lại cũng đúng: thiết lập `initCause(root)` **không tự thêm `root` vào danh sách suppressed**.

Với try-with-resources, khi thân `try` ném ngoại lệ chính rồi `close()` ném lỗi, Java thường gắn lỗi close làm suppressed vào ngoại lệ chính. Trường hợp cause của ngoại lệ chính đã khởi tạo hay chưa là **vấn đề tách biệt**.

### Đừng thay cause bằng suppressed hoặc ngược lại

Nếu `IOException` là nguồn gốc của thất bại nghiệp vụ, hãy giữ nó làm cause của wrapper. Nếu một lỗi xảy ra thêm trong quá trình dọn dẹp khi đã có lỗi chính, suppressed exceptions thường là quan hệ phù hợp. Chọn loại quan hệ đúng giúp đọc stack trace và lập công cụ phân tích chính xác.

## 12. Cause và stack trace không thay thế nhau

`Throwable` thường ghi stack trace **khi đối tượng được khởi tạo**. Stack trace phản ánh các frame gọi đến nơi tạo, còn cause liên kết tới **một ngoại lệ khác**.

~~~java
IOException root = new IOException("Không đọc được");
IllegalStateException wrapper =
        new IllegalStateException("Không tải được", root);
~~~

Đây là một đoạn minh họa trong phạm vi có import hoặc sử dụng tên đầy đủ cho `IOException`. Khi tạo wrapper, Java thông thường ghi stack trace cho wrapper. Nó không xóa stack trace của `root`.

Do đó có thể có:

- Wrapper có message, stack trace và cause.
- Cause có message và stack trace của chính nó.
- Wrapper không có cause, nhưng vẫn có stack trace.
- Wrapper có cause, nhưng stack trace riêng đã bị tắt bằng constructor cấu hình đặc biệt của lớp con.

**Đọc `getCause()` để tìm nguyên nhân**, **đọc stack trace để tìm vị trí/đường gọi**, không dùng một thứ thay thế thứ kia.

### `getLocalizedMessage()` có liên quan gì?

`getLocalizedMessage()` mặc định trả thông điệp theo hành vi của `Throwable`; lớp con có thể tùy biến. Nó không làm thay đổi trạng thái cause. Không nên suy luận thông điệp đã được bản địa hóa là dữ liệu bắt buộc để xác định nguyên nhân chính thức của lỗi.

## 13. Chương trình Java 17+ chạy độc lập

Chương trình sau chứng minh trực tiếp:

1. `getCause()==null` trong **hai trạng thái khác nhau**.
2. `initCause` thành công một lần; lần thứ hai thất bại.
3. Cause được constructor khởi tạo bằng `null` **không thể gắn lại**.
4. Tự làm cause của chính mình gây `IllegalArgumentException`.
5. Constructor nhận cause-only tạo message từ `cause.toString()`.
6. Bọc `NumberFormatException` vẫn giữ nguyên nhân gốc.
7. Suppressed exceptions không phải cause.
8. Duyệt chuỗi cause cần chống vòng tham chiếu.

Tạo tệp **`ThrowableCauseDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class ThrowableCauseDemo {

    static final class ConfigException extends Exception {
        ConfigException(String message) {
            super(message);
        }

        ConfigException(String message, Throwable cause) {
            super(message, cause);
        }

        ConfigException(Throwable cause) {
            super(cause);
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("disk");

        System.out.println("== uninitialized ==");
        Throwable fresh = new Throwable("fresh");
        System.out.println("fresh.before=" + fresh.getCause());
        Throwable returned = fresh.initCause(root);
        System.out.println("fresh.same=" + (fresh.getCause() == root));
        System.out.println("init.returnedSelf=" + (returned == fresh));
        try {
            fresh.initCause(new IOException("later"));
        } catch (IllegalStateException e) {
            System.out.println("fresh.second=IllegalStateException");
        }

        System.out.println("== initialized null ==");
        Throwable explicitNull = new Throwable("empty", null);
        System.out.println("explicitNull.cause=" + explicitNull.getCause());
        try {
            explicitNull.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println(
                    "explicitNull.later=IllegalStateException");
        }

        Throwable byCauseNull = new Throwable((Throwable) null);
        try {
            byCauseNull.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println(
                    "byCauseNull.later=IllegalStateException");
        }

        Throwable nullViaInit = new Throwable("initially free");
        nullViaInit.initCause(null);
        try {
            nullViaInit.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println("nullViaInit.again=IllegalStateException");
        }

        System.out.println("== self cause ==");
        Throwable self = new Throwable("self");
        try {
            self.initCause(self);
        } catch (IllegalArgumentException e) {
            System.out.println("self.error=IllegalArgumentException");
        }

        System.out.println("== constructors ==");
        Throwable onlyCause = new Throwable(root);
        Throwable messageAndCause = new Throwable("load failed", root);
        System.out.println("onlyCause.message=" + onlyCause.getMessage());
        System.out.println(
                "onlyCause.same=" + (onlyCause.getCause() == root));
        System.out.println(
                "messageAndCause.message=" + messageAndCause.getMessage());
        System.out.println(
                "messageAndCause.same="
                        + (messageAndCause.getCause() == root));

        System.out.println("== wrapping ==");
        try {
            parsePort("abc");
        } catch (ConfigException e) {
            System.out.println("outer.message=" + e.getMessage());
            System.out.println(
                    "inner.type=" + e.getCause().getClass().getSimpleName());
            System.out.println(
                    "inner.message=" + e.getCause().getMessage());
        }

        System.out.println("== suppressed ==");
        Throwable primary = new Throwable("primary");
        primary.addSuppressed(new IOException("close"));
        System.out.println("primary.cause=" + primary.getCause());
        System.out.println(
                "primary.suppressed=" + primary.getSuppressed().length);

        System.out.println("== traversal ==");
        Throwable outer = new Throwable("outer", root);
        System.out.println(
                "chain.length=" + countDistinctCauses(outer));

        Throwable a = new Throwable("A");
        Throwable b = new Throwable("B");
        a.initCause(b);
        b.initCause(a);
        System.out.println(
                "cycle.distinct=" + countDistinctCauses(a));
    }

    static int parsePort(String text) throws ConfigException {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException cause) {
            throw new ConfigException(
                    "Invalid port: " + text, cause);
        }
    }

    static int countDistinctCauses(Throwable error) {
        Set<Throwable> seen =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());
        Throwable current = error;

        while (current != null && seen.add(current)) {
            current = current.getCause();
        }
        return seen.size();
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac ThrowableCauseDemo.java
java ThrowableCauseDemo
~~~

**Stdout xác định:**

~~~text
== uninitialized ==
fresh.before=null
fresh.same=true
init.returnedSelf=true
fresh.second=IllegalStateException
== initialized null ==
explicitNull.cause=null
explicitNull.later=IllegalStateException
byCauseNull.later=IllegalStateException
nullViaInit.again=IllegalStateException
== self cause ==
self.error=IllegalArgumentException
== constructors ==
onlyCause.message=java.io.IOException: disk
onlyCause.same=true
messageAndCause.message=load failed
messageAndCause.same=true
== wrapping ==
outer.message=Invalid port: abc
inner.type=NumberFormatException
inner.message=For input string: "abc"
== suppressed ==
primary.cause=null
primary.suppressed=1
== traversal ==
chain.length=2
cycle.distinct=2
~~~

### Phân tích chi tiết kết quả

**Nhóm uninitialized:** `fresh` tạo bằng constructor `(String)` nên cause chưa khởi tạo. `getCause()` trả `null`. `initCause(root)` hợp lệ, trả về chính `fresh`. Khi thử gắn cause thứ hai, Java ném `IllegalStateException`.

**Nhóm initialized null:** `explicitNull` tạo bằng constructor `(String, Throwable)` với cause `null`; `byCauseNull` tạo bằng constructor `(Throwable)` với cause `null`. Cả hai đã khởi tạo trạng thái cause và không cho gọi `initCause`. `nullViaInit` gọi `initCause(null)` thành công, nhưng sau đó quyền khởi tạo cause cũng đã được sử dụng.

**Nhóm self cause:** Java từ chối `self.initCause(self)`; lỗi này thuộc `IllegalArgumentException` khi cause của `self` còn chưa được khởi tạo.

**Nhóm constructors:** Dạng cause-only tạo message từ `IOException.toString()`; dạng message+cause giữ message của wrapper tách biệt. Cả hai giữ tham chiếu nguyên nhân gốc.

**Nhóm wrapping:** `Integer.parseInt("abc")` ném `NumberFormatException`. `parsePort` bọc nó vào `ConfigException`; caller đọc message của lớp ngoài và type/message của cause để thấy cả hai tầng. `NumberFormatException` không biến mất chỉ vì ngoại lệ bên ngoài là checked `ConfigException`.

**Nhóm suppressed:** `primary` có một suppressed exception nhưng `getCause()` vẫn `null`; hai quan hệ không tự chuyển hóa qua lại.

**Nhóm traversal:** `countDistinctCauses` dùng một tập dựa trên **identity** của tham chiếu đối tượng thay vì `equals` để bảo đảm thuật toán dừng khi có vòng. Chuỗi `outer → root → null` có hai đối tượng; chuỗi `a → b → a` cũng có hai đối tượng phân biệt nên hàm trả `2`, không chạy vô hạn.

## 14. Thực hành tốt: ưu tiên constructor có cause

Khi API cung cấp constructor:

~~~java
public SomeException(String message, Throwable cause)
~~~

hãy ưu tiên tạo object hoàn chỉnh trong một bước:

~~~java
throw new IllegalStateException(
        "Không thể tải tài nguyên", original);
~~~

Đây là hai **dạng minh họa**, trong đó `SomeException` là tên tượng trưng và `original` là một cause hiện có.

So với:

~~~java
IllegalStateException outer =
        new IllegalStateException("Không thể tải tài nguyên");
outer.initCause(original);
throw outer;
~~~

cả hai có thể biểu thị message và cause tương tự trong trường hợp `original` hợp lệ. Tuy nhiên, constructor giúp:

- Cause được khởi tạo ngay tại thời điểm tạo đối tượng.
- Mã có ít bước và ít trạng thái trung gian.
- Giảm nguy cơ quên gắn cause.
- Tránh vô tình gọi `initCause` khi constructor đã thiết lập cause.

Không cần chuyển các đoạn mã hiện có chỉ vì thích cú pháp ngắn hơn nếu hợp đồng API có yêu cầu khác; hãy chọn dựa trên kiểu ngoại lệ và hành vi caller cần.

### Không đổi kiểu lỗi chỉ để có constructor cause

Nếu lỗi nguyên thủy `IOException` đã phù hợp hợp đồng, có thể ném lại hoặc khai báo `throws IOException` thay vì bọc thành một loại lỗi khác. Bọc lỗi nên mang lại **thông tin ngữ cảnh hoặc ranh giới API** thực sự có ích.

## 15. Khi lớp ngoại lệ cũ chỉ có constructor message

Một số thư viện hoặc lớp lỗi lịch sử chỉ cung cấp overload:

~~~java
LegacyException(String message)
~~~

Khi cần bảo toàn nguyên nhân, nếu `LegacyException` kế thừa hành vi `Throwable` cho phép `initCause`, có thể dùng:

~~~java
LegacyException error =
        new LegacyException("Thao tác thất bại");
error.initCause(original);
throw error;
~~~

Các đoạn trên là minh họa, không phải API thật của một lớp có tên `LegacyException` trong JDK. **Luôn xem constructor và hợp đồng của lớp cụ thể**:

- Một số lớp ngoại lệ chuyên biệt có cơ chế lưu/đọc cause riêng hoặc ghi đè API liên quan.
- Một số lớp chủ động khóa khả năng thiết lập cause.
- Không suy ra một lớp chỉ từ tên hoặc quan hệ kế thừa mà bỏ qua tài liệu API.

Nếu kiểm soát nguồn mã lớp cũ, có thể bổ sung overload `(String, Throwable)` để mọi caller mới không cần gắn cause muộn.

## 16. Điều gì xảy ra nếu `initCause` bị gọi sau khi đã `throw`?

Về mặt kỹ thuật, `Throwable` là một đối tượng và `initCause` kiểm tra **trạng thái cause**, không có yêu cầu riêng “chỉ được gọi trước lần ném đầu”. Nếu một đối tượng vẫn chưa khởi tạo cause, API mặc định có thể cho phép gắn cause khi đối tượng đã được bắt sau một lần `throw`.

Ví dụ:

~~~java
static void lateLink() {
    Throwable problem = new Throwable("late");
    try {
        throw problem;
    } catch (Throwable e) {
        e.initCause(new java.io.IOException("cause"));
        System.out.println(e.getCause().getMessage());
    }
}
~~~

Đây là phương thức minh họa có thể đặt trong một lớp Java. Nó in `cause`. Tuy nhiên, **không nên xem đây là cách thiết kế mặc định**: cause nên được quyết định khi bạn tạo hoặc bọc ngoại lệ, trước khi nó được công bố qua các tầng xử lý. Thêm cause sau khi đã ném/gửi log có thể khiến các thành phần quan sát được thông tin không nhất quán.

Nếu nhiều luồng cùng có tham chiếu đến ngoại lệ, hành vi đồng bộ cụ thể của `getCause` và `initCause` không thay thế được quy trình thiết kế immutable/error-reporting rõ ràng. Tránh dùng một đối tượng ngoại lệ chung có cause thay đổi theo thời gian để đại diện cho nhiều sự cố độc lập.

## 17. Những lỗi thường gặp

### Lỗi 1 — Thấy `getCause() == null` rồi luôn gọi `initCause`

Sai. Một cause **đã được khởi tạo bằng `null`** vẫn cho getter trả null nhưng không cho gắn lại.

### Lỗi 2 — Tưởng constructor message+cause với cause null tương đương constructor chỉ message

Không tương đương về quyền `initCause`. `new Throwable("x", null)` khóa trạng thái cause; `new Throwable("x")` vẫn để trạng thái chưa khởi tạo.

### Lỗi 3 — Tưởng `initCause(null)` là reset

Không. Nó được tính như một lần khởi tạo cause. Lần sau `initCause(nonNull)` không hợp lệ.

### Lỗi 4 — Gọi `initCause` hai lần để đổi nguyên nhân

Sai. `initCause` không phải setter có thể gọi nhiều lần; lần thứ hai ném `IllegalStateException`.

### Lỗi 5 — Tự làm cause

`error.initCause(error)` không được phép vì tự làm nguyên nhân trực tiếp gây vòng tham chiếu.

### Lỗi 6 — Duyệt cause mà không chống vòng

Không nên mặc định mọi chuỗi tùy biến đều kết thúc bằng `null`; thuật toán xử lý dữ liệu lỗi từ nhiều nguồn cần phát hiện tham chiếu đã gặp.

### Lỗi 7 — Nhầm cause với suppressed exceptions

`getCause()` trả nguyên nhân trực tiếp. `getSuppressed()` trả danh sách lỗi phụ đã giữ lại; việc thêm suppressed không tự điền cause.

### Lỗi 8 — Chỉ chép `cause.getMessage()` vào message mới

Nếu chỉ nối chuỗi mà không lưu cause, sẽ mất liên kết đối tượng và stack trace của nguyên nhân trong cấu trúc lỗi được ném ra.

### Lỗi 9 — Cho rằng `Throwable(Throwable)` dùng nguyên message của cause

Không chính xác. Constructor cause-only dùng `cause.toString()` khi cause khác null, thường gồm cả tên lớp.

### Lỗi 10 — Tưởng lớp con được thừa kế constructor cause

Constructor không được thừa kế; lớp con phải định nghĩa overload hoặc dùng API nó cung cấp.

### Lỗi 11 — Dùng cause để đoán kiểu ngoại lệ được catch

Một `IllegalStateException` có cause là `IOException` **không** được bắt trực tiếp bởi `catch (IOException)`. Handler chọn theo kiểu của ngoại lệ ngoài đang lan truyền, không tự chui vào cause.

### Lỗi 12 — Cho rằng cause là một thuộc tính có thể cập nhật từ nhiều nơi

Thiết kế mặc định hướng tới một lần khởi tạo. Không viết hệ thống điều phối lỗi phụ thuộc vào khả năng “sửa cause” nhiều lần.

### Lỗi 13 — Dùng `printStackTrace()` làm dữ liệu máy đọc ổn định

Stack trace có ích để chẩn đoán nhưng không phải hợp đồng định dạng ổn định. Dùng API đọc có cấu trúc khi cần xây dựng hệ thống quan sát lỗi.

### Lỗi 14 — Ghi dữ liệu bí mật trong message/cause

Thông tin của cause có thể đi kèm trong stack trace, logs và công cụ observability. Tránh đưa token, mật khẩu, dữ liệu cá nhân hoặc nội dung nội bộ nhạy cảm vào thông điệp lỗi.

### Lỗi 15 — Bọc ngoại lệ qua quá nhiều tầng không thêm ngữ cảnh

Một chuỗi dài nhiều wrapper giống hệt nhau làm tăng độ phức tạp khi điều tra. Bọc tại các ranh giới có ý nghĩa, giữ cause và thông điệp đủ cụ thể.

## 18. Câu hỏi tự kiểm tra

1. Cause khác với message như thế nào?
2. `getCause()` trả gì nếu chưa có nguyên nhân công khai?
3. Vì sao `getCause() == null` không đủ để kết luận `initCause(...)` hợp lệ?
4. Với `new Throwable()`, có thể `initCause(root)` một lần không?
5. Với `new Throwable("message", null)`, có thể `initCause(root)` không?
6. Với `new Throwable((Throwable) null)`, `getCause()` bằng bao nhiêu? Cause đã được khởi tạo chưa?
7. `initCause(null)` có cho phép gọi tiếp `initCause(root)` không?
8. `initCause` trả về một đối tượng mới hay chính đối tượng đang gọi?
9. Hai lỗi runtime nào thường gặp khi sử dụng `initCause` sai, và mỗi lỗi tương ứng điều kiện gì?
10. `getCause()` trả ngay ngoại lệ gốc sâu nhất hay chỉ một cấp trực tiếp?
11. Vì sao duyệt cause tùy biến nên dùng tập theo identity?
12. Constructor `Throwable(Throwable cause)` tạo message từ đâu?
13. Việc truyền cause vào constructor có thay đổi checked/unchecked của lớp ngoài không?
14. Suppressed exception có tự động trở thành cause không?
15. Khi nào constructor `(String, Throwable)` tốt hơn `initCause`?
16. Khi nào `initCause` vẫn hữu ích trong mã kế thừa hoặc tương thích API cũ?
17. Tại sao constructor protected bốn tham số với cause null vẫn không cho gọi `initCause` lần nữa?
18. Nếu ngoại lệ bên ngoài đã có cause, có cần đọc `getStackTrace()` của cause nữa không?
19. Việc `throw` cùng một ngoại lệ hai lần có tự làm `initCause` hợp lệ trở lại không?
20. Caller có nên dựa vào `getCause().getMessage()` mà không kiểm tra `getCause() != null` không?

### Đáp án gợi ý

1. Message là văn bản mô tả; cause là tham chiếu tới `Throwable` nguyên nhân.
2. `null`.
3. Null có thể do chưa khởi tạo hoặc đã khởi tạo bằng null.
4. Có, nếu cause chưa được khởi tạo.
5. Không, constructor đã khởi tạo cause bằng null.
6. Getter trả null, nhưng cause đã được khởi tạo.
7. Không; lần gắn null cũng chiếm quyền khởi tạo.
8. Chính đối tượng đang gọi.
9. `IllegalStateException` nếu cause đã được khởi tạo; `IllegalArgumentException` nếu tự làm cause của chính mình.
10. Chỉ một bước cause trực tiếp.
11. Để phát hiện vòng bằng tham chiếu đối tượng chứ không phụ thuộc `equals`.
12. `cause.toString()` khi cause khác null.
13. Không; phân loại của ngoại lệ ngoài phụ thuộc lớp của nó.
14. Không.
15. Khi constructor có sẵn và muốn tạo đối tượng hoàn chỉnh với ngữ cảnh ngay lập tức.
16. Khi lớp ngoại lệ chỉ có overload không nhận cause nhưng cho phép gắn cause một lần.
17. Vì overload bốn tham số đã khởi tạo cause, kể cả với giá trị null.
18. Có thể cần, vì cause có stack trace riêng.
19. Không; `throw` không reset trạng thái cause.
20. Không; phải xử lý trường hợp cause là null.

## 19. Ghi nhớ

**`getCause()` cho biết tham chiếu nguyên nhân trực tiếp, còn `initCause(...)` chỉ thiết lập nguyên nhân khi trạng thái cause của `Throwable` chưa từng được khởi tạo.** Các constructor không nhận cause có thể cho phép gọi `initCause` một lần; các constructor có tham số cause đã quyết định trạng thái ngay cả khi truyền `null`. Lần thiết lập thứ hai gây `IllegalStateException`; tự làm cause của chính mình gây `IllegalArgumentException`. Trong mã Java mới, ưu tiên constructor nhận message và cause; sử dụng `initCause` khi cần tương thích với lớp lỗi không có overload phù hợp.