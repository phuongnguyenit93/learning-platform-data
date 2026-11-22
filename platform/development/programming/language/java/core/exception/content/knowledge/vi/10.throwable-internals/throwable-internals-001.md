# Các constructor với message, cause và cấu hình nâng cao của `Throwable` trong Java

`java.lang.Throwable` là lớp gốc của các đối tượng có thể được ném và bắt trong cơ chế ngoại lệ Java. Khi tạo một ngoại lệ, **constructor** quyết định những thông tin chẩn đoán ban đầu được lưu vào đối tượng: **message** (thông điệp), **cause** (nguyên nhân), khả năng lưu **suppressed exceptions** (ngoại lệ phụ bị giữ lại) và khả năng ghi **stack trace** (dấu vết ngăn xếp lời gọi).

Ví dụ:

~~~java
throw new IllegalStateException(
        "Không thể khởi tạo dịch vụ",
        new java.io.IOException("Thiếu cấu hình"));
~~~

Lệnh trên thực hiện hai việc: constructor của `IllegalStateException` tạo đối tượng với message và cause; lệnh `throw` mới **ném** đối tượng khiến luồng điều khiển Java bắt đầu tìm handler phù hợp. Constructor **không tự ném** một ngoại lệ chỉ vì đối tượng được tạo thuộc loại `Throwable`.

Bài học tập trung vào năm dạng constructor của `Throwable`, ý nghĩa của từng tham số, cách lớp con sử dụng `super(...)`, ảnh hưởng tới `getMessage()`, `getCause()`, `getSuppressed()` và `getStackTrace()`, các tình huống thực tế khi bọc lỗi, và những rủi ro khi tắt suppression/stack trace.

## 1. Vị trí của `Throwable` trong hệ thống ngoại lệ

Phân cấp rút gọn:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    │   └── java.lang.OutOfMemoryError
    └── java.lang.Exception
        ├── java.io.IOException
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            └── java.lang.IllegalStateException
~~~

Tất cả đối tượng `Exception` và `Error` đều là `Throwable`. Tuy nhiên, chỉ vì mọi lớp này kế thừa `Throwable` **không có nghĩa chúng đều cung cấp cùng bộ constructor**.

**Constructor không được kế thừa trong Java.** Nếu một lớp con cần các overload tương ứng với message/cause, lớp đó phải khai báo constructor và gọi `super(...)` phù hợp. Một số lớp chuẩn chỉ cung cấp những overload riêng của chúng.

Một vài khác biệt:

- `Throwable` là nền tảng cho việc ném đối tượng, ghi nhận nguyên nhân và dấu vết lỗi.
- `Exception` thường đại diện các tình huống lỗi mà mã ứng dụng có thể cân nhắc xử lý.
- `RuntimeException` là nhánh **unchecked exception**.
- `Error` cũng thuộc loại unchecked, thường báo vấn đề nghiêm trọng mà mã nghiệp vụ không nên bắt đại trà để tiếp tục.
- Các lớp `Throwable` khác ngoài `RuntimeException` và `Error` cùng các lớp con của chúng chịu quy tắc checked exception của Java.

Việc truyền message hoặc cause vào constructor **không quyết định** đối tượng là checked hay unchecked: điều đó phụ thuộc **quan hệ kế thừa**.

## 2. Năm constructor của `Throwable`

Ở Java 17+, `java.lang.Throwable` cung cấp các dạng constructor sau:

~~~java
public Throwable()
public Throwable(String message)
public Throwable(String message, Throwable cause)
public Throwable(Throwable cause)
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

Đây là **các chữ ký API minh họa**, không phải một tệp khai báo lại lớp `Throwable`. Constructor cuối cùng là `protected`: mã ứng dụng thông thường không thể gọi trực tiếp `new Throwable(message, cause, true, true)` từ một lớp không có quyền truy cập thích hợp. Nó dành cho **lớp con** gọi qua `super(...)` theo quy tắc truy cập của Java.

| Dạng | Message ban đầu | Cause ban đầu | Suppression | Stack trace |
| --- | --- | --- | --- | --- |
| `Throwable()` | `null` | chưa khởi tạo cause | bật mặc định | ghi mặc định |
| `Throwable(String message)` | chuỗi truyền vào | chưa khởi tạo cause | bật mặc định | ghi mặc định |
| `Throwable(Throwable cause)` | thường là `cause.toString()`, hoặc `null` nếu cause null | cause đã khởi tạo | bật mặc định | ghi mặc định |
| `Throwable(String message, Throwable cause)` | chuỗi truyền vào | cause đã khởi tạo | bật mặc định | ghi mặc định |
| `Throwable(String message, Throwable cause, boolean, boolean)` | chuỗi truyền vào | cause đã khởi tạo | chọn bật/tắt | chọn ghi/không ghi |

**“Cause chưa khởi tạo” khác “cause đã khởi tạo bằng `null`”.** Dù `getCause()` có thể trả `null` trong cả hai tình huống, khả năng gọi `initCause(...)` về sau **khác nhau**; đây là một quy tắc quan trọng ở phần 7.

Các constructor thông thường mặc định bật cả lưu suppressed exceptions và writable stack trace. Constructor bốn tham số cho phép thay đổi hai hành vi ấy lúc khởi tạo và sự lựa chọn có ảnh hưởng lâu dài tới chẩn đoán lỗi.

## 3. Constructor không tham số: `Throwable()`

~~~java
Throwable issue = new Throwable();
System.out.println(issue.getMessage()); // null
System.out.println(issue.getCause());   // null
~~~

Hai dòng in ở ví dụ này đều là `null`. Đối tượng vẫn là một `Throwable` hợp lệ, có thể được ném nếu phương thức đáp ứng quy tắc checked exception, và thông thường có stack trace được ghi nhận khi tạo.

Dạng này thích hợp khi kiểu lớp đã đủ biểu đạt vấn đề hoặc khi lớp con chủ động cung cấp dữ liệu qua cơ chế khác. Tuy nhiên, trong mã ứng dụng, một thông điệp rõ ràng thường giúp đọc log và điều tra tốt hơn.

**Lưu ý:** `new Throwable()` đơn thuần **không** chuyển điều khiển sang `catch`. Phải có `throw issue;` hoặc một lệnh ném đối tượng tương ứng mới có ngoại lệ runtime được lan truyền.

## 4. Constructor nhận message: `Throwable(String message)`

~~~java
IllegalArgumentException issue =
        new IllegalArgumentException("age không được âm");

System.out.println(issue.getMessage());
// age không được âm
~~~

Message nên giúp người đọc hiểu điều kiện thất bại mà không cần đoán ngữ cảnh. Ví dụ:

- `"age phải nằm trong khoảng 0..150"` hữu ích hơn `"Sai"`.
- `"Không tải được cấu hình ứng dụng"` hữu ích hơn `"Có exception"`.
- Thông điệp cho hệ thống nội bộ nên tránh ghi token, mật khẩu, khóa API hoặc dữ liệu cá nhân nhạy cảm.

Không nên điều khiển logic bằng cách so sánh nội dung `getMessage()`. Message có thể đổi theo phiên bản, cách bản địa hóa hoặc chi tiết triển khai. Nếu ứng dụng cần mã lỗi ổn định, hãy định nghĩa kiểu ngoại lệ hoặc trường mã lỗi riêng.

### Message `null` và chuỗi rỗng

~~~java
Throwable a = new Throwable((String) null);
Throwable b = new Throwable("");

System.out.println(a.getMessage() == null);  // true
System.out.println(b.getMessage().isEmpty()); // true
~~~

`null` và `""` là hai giá trị khác nhau. Khi tạo đối tượng mà không đưa thông điệp, `getMessage()` thường là `null`. Một số cách hiển thị ngoại lệ có thể biểu diễn chúng khác nhau.

Constructor `Throwable(String)` **không tự gán cause**. Với một đối tượng được tạo bằng dạng này, có thể thiết lập cause sau đó bằng `initCause(...)` một lần, nếu cần và hợp lệ.

## 5. Constructor nhận cause: `Throwable(Throwable cause)`

~~~java
java.io.IOException root =
        new java.io.IOException("Không đọc được tệp");

Throwable wrapper = new Throwable(root);
System.out.println(wrapper.getCause() == root); // true
~~~

Constructor này đặt **cause** thành chính đối tượng `root`. Message của `wrapper` thường lấy từ `cause.toString()`; với cause là `null`, message là `null`.

Ví dụ riêng để thấy giá trị message:

~~~java
IllegalArgumentException root =
        new IllegalArgumentException("bad input");
Throwable outer = new Throwable(root);

System.out.println(outer.getMessage());
// java.lang.IllegalArgumentException: bad input
~~~

Chú ý: `outer.getMessage()` **không đơn giản bằng `root.getMessage()`**. Với constructor nhận duy nhất cause, nó dùng biểu diễn `toString()` của cause, thường có **tên lớp + message**.

Nếu API ở tầng cao cần một message mô tả thao tác thất bại, constructor nhận **cả message và cause** thường rõ nghĩa hơn.

### Truyền `null` vào constructor cause-only

~~~java
Throwable x = new Throwable((Throwable) null);
System.out.println(x.getMessage()); // null
System.out.println(x.getCause());   // null
~~~

Dù getter trả `null`, constructor nhận cause đã đánh dấu trạng thái cause là **được khởi tạo**. Gọi `x.initCause(...)` về sau không được phép, khác với đối tượng tạo bằng `new Throwable()` hoặc `new Throwable("message")`.

Ép kiểu `(Throwable) null` ở ví dụ giúp biểu đạt rõ ta muốn constructor nhận cause. Với lớp có nhiều overload nhận các kiểu tham chiếu không liên quan, truyền `null` không ép kiểu có thể dẫn tới lỗi overload không rõ ràng.

## 6. Constructor nhận message và cause: `Throwable(String, Throwable)`

Đây là dạng đặc biệt hữu ích khi **chuyển đổi ngoại lệ giữa các tầng ứng dụng**.

~~~java
static String loadConfig(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Không thể nạp cấu hình bắt buộc", cause);
    }
}
~~~

Đây là phương thức Java minh họa có thể đặt trong một lớp. `Files.readString` có thể ném `IOException`. Nếu điều đó xảy ra:

1. `catch` nhận đối tượng `IOException` gốc.
2. Constructor của `IllegalStateException` nhận message cho tầng hiện tại và cause gốc.
3. `throw` ném đối tượng mới, thuộc loại `IllegalStateException`.
4. `getMessage()` của đối tượng mới cho biết thao tác nào thất bại.
5. `getCause()` trỏ tới chính `IOException` đã được bắt.

Ưu điểm: giữ **ngữ cảnh nghiệp vụ** và **nguồn gốc kỹ thuật** trong hai trường riêng, thay vì gộp mọi thứ vào một chuỗi.

### Đừng biến cause thành một phần của message rồi bỏ tham chiếu

Cách chưa tốt:

~~~java
throw new IllegalStateException(
        "Không tải được: " + cause.getMessage());
~~~

Đây là đoạn minh họa trong phạm vi có biến `cause`. Chuỗi mô tả có thể vẫn hữu ích, nhưng đối tượng mới **không giữ liên kết `getCause()`** chỉ vì văn bản chứa message của cause.

Cách nên cân nhắc:

~~~java
throw new IllegalStateException(
        "Không tải được dữ liệu bắt buộc", cause);
~~~

Không cần chuyển mọi ngoại lệ sang `IllegalStateException`; loại ngoại lệ tầng cao phải phù hợp hợp đồng API. Điểm cốt lõi là **truyền cause** khi có lý do bọc lỗi.

### Truyền cause `null` vẫn được xem là đã khởi tạo cause

~~~java
Throwable problem = new Throwable("No cause", null);
System.out.println(problem.getCause()); // null
~~~

Ở đây `getCause()` trả `null`, nhưng `initCause(...)` **không thể dùng lần nữa** cho đối tượng này. Thiết kế constructor `(String, Throwable)` thể hiện rằng quan hệ cause đã được quyết định lúc khởi tạo, ngay cả khi quyết định là “không có cause”.

## 7. `initCause`: bổ sung nguyên nhân khi constructor chưa nhận cause

`Throwable.initCause(root)` cho phép gắn **một lần** nguyên nhân cho đối tượng tạo bằng constructor không tham số hoặc chỉ nhận message. Nếu constructor đã nhận cause, **kể cả `null`**, trạng thái cause đã được khởi tạo và gọi `initCause` tiếp sẽ ném `IllegalStateException`.

~~~java
Throwable error = new Throwable("Không thể nạp cấu hình");
error.initCause(new java.io.IOException("Tệp bị thiếu"));
System.out.println(error.getCause().getClass().getSimpleName());
// IOException
~~~

`getCause() == null` **không** chứng minh `initCause` còn được phép; `initCause(null)` cũng tiêu thụ cơ hội khởi tạo. Không được tự đặt đối tượng làm cause của chính nó (`IllegalArgumentException`). Với API mới, hãy ưu tiên constructor nhận `(String, Throwable)`; quy tắc trạng thái và chuỗi cause được phân tích chuyên sâu trong bài về `getCause`/`initCause`.

## 8. Constructor nâng cao: bốn tham số của `Throwable`

Dạng nâng cao có chữ ký:

~~~java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

Hai tham số cuối là:

- `enableSuppression`: có cho phép lưu những ngoại lệ được gắn vào đối tượng bởi `addSuppressed(...)` hay không.
- `writableStackTrace`: có cho phép ghi dấu vết stack trace cho chính đối tượng `Throwable` hay không.

Đây là cấu hình tại thời điểm khởi tạo; bạn không có một setter công khai tương đương để bật/tắt hai tính năng trên một đối tượng đã tạo.

Constructor này là `protected`. Cách dùng điển hình là **lớp ngoại lệ tùy biến** gọi `super(message, cause, enableSuppression, writableStackTrace)`:

~~~java
public class DomainProblem extends Exception {
    public DomainProblem(
            String message,
            Throwable cause,
            boolean enableSuppression,
            boolean writableStackTrace) {
        super(message, cause, enableSuppression, writableStackTrace);
    }
}
~~~

Đây là một lớp hoàn chỉnh nếu lưu trong `DomainProblem.java`. Constructor bốn tham số `protected` của `Exception` cho phép lớp con chuyển tiếp cấu hình tới cơ chế khởi tạo của `Throwable`. Không cần và không nên sử dụng reflection để truy cập constructor `protected` từ mã thông thường.

### Điều gì không thay đổi?

Tắt suppression hoặc stack trace **không**:

- Làm đối tượng thôi là `Throwable`.
- Thay đổi phân loại checked/unchecked của lớp con.
- Thay đổi message hoặc cause đã truyền vào constructor.
- Ngăn `throw`/`catch` hoạt động với đối tượng.
- Tự động tắt logging trong ứng dụng hay ngăn bên gọi tự in một message.

Các cờ này thay đổi **dữ liệu chẩn đoán được ghi và lưu trên chính đối tượng**, không phải bản chất của cơ chế lan truyền ngoại lệ.

## 9. `enableSuppression`: khả năng lưu lỗi bổ sung

Trong `try-with-resources`, nếu thân khối ném A rồi `close()` ném B, Java thường giữ A làm **primary** và gọi cơ chế `addSuppressed(B)` trên A. Nếu **đối tượng A** được tạo với `enableSuppression=false`, danh sách `getSuppressed()` của A vẫn rỗng: lỗi B có thể đã xảy ra nhưng không được lưu trên A.

~~~java
DomainProblem noExtras = new DomainProblem(
        "work failed", null, false, true);
noExtras.addSuppressed(new java.io.IOException("close failed"));
System.out.println(noExtras.getSuppressed().length); // 0
~~~

Đoạn trên dùng lớp `DomainProblem` đã khai báo trong phần constructor nâng cao. **Tắt suppression không tắt cause hoặc stack trace.** Đây là đánh đổi mất chẩn đoán, không phải cách khắc phục lỗi tài nguyên. Cách thêm/đọc lỗi phụ, thứ tự đóng nhiều tài nguyên và các lỗi đối số thuộc bài chuyên sâu `addSuppressed`/`getSuppressed`; bốn tổ hợp cờ thuộc bài cấu hình `Throwable`.

## 10. `writableStackTrace`: khả năng ghi dấu vết của chính Throwable

Constructor thông thường ghi trace khi tạo đối tượng. Với `writableStackTrace=false`, đối tượng vẫn được `throw`/`catch`, có message/cause, nhưng `getStackTrace()` trả mảng rỗng; `fillInStackTrace()` không điền frame và `setStackTrace(...)` không khôi phục khả năng ghi.

~~~java
DomainProblem noFrames = new DomainProblem(
        "operation failed", null, true, false);
System.out.println(noFrames.getStackTrace().length); // 0
~~~

Tắt stack trace **chỉ áp dụng cho đối tượng này**: cause và suppressed exceptions khác vẫn có thể lưu trace của riêng chúng. Không nên dùng cấu hình này chỉ để giảm log dài hoặc tái sử dụng exception; nó làm mất vị trí sự cố. Các bài về thời điểm ghi trace, `fillInStackTrace`, `setStackTrace` và cấu hình hai cờ xử lý các trường hợp sâu hơn.

## 11. Ví dụ Java 17+ hoàn chỉnh: đủ constructor và hai cấu hình nâng cao

Tạo tệp **`ThrowableConstructorsDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Arrays;

public class ThrowableConstructorsDemo {

    static final class Problem extends Exception {
        Problem() {
            super();
        }

        Problem(String message) {
            super(message);
        }

        Problem(Throwable cause) {
            super(cause);
        }

        Problem(String message, Throwable cause) {
            super(message, cause);
        }

        Problem(
                String message,
                Throwable cause,
                boolean enableSuppression,
                boolean writableStackTrace) {
            super(message, cause, enableSuppression, writableStackTrace);
        }
    }

    static final class ClosingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close error");
        }
    }

    public static void main(String[] args) {
        System.out.println("== constructors ==");
        Problem empty = new Problem();
        Problem described = new Problem("validation failed");
        IllegalArgumentException root =
                new IllegalArgumentException("bad input");
        Problem causeOnly = new Problem(root);
        Problem wrapped = new Problem("cannot load", root);

        System.out.println("empty.message=" + empty.getMessage());
        System.out.println("message=" + described.getMessage());
        System.out.println(
                "causeOnly.message=" + causeOnly.getMessage());
        System.out.println(
                "causeOnly.causeSame=" + (causeOnly.getCause() == root));
        System.out.println("wrapped.message=" + wrapped.getMessage());
        System.out.println(
                "wrapped.causeType="
                + wrapped.getCause().getClass().getSimpleName());

        System.out.println("== deferred cause ==");
        Problem late = new Problem("later");
        late.initCause(root);
        System.out.println("late.causeSame=" + (late.getCause() == root));

        try {
            late.initCause(new IOException("again"));
        } catch (IllegalStateException e) {
            System.out.println("initCause repeated=IllegalStateException");
        }

        Problem explicitNull = new Problem("null cause", null);
        try {
            explicitNull.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println(
                    "explicitNull replacement=IllegalStateException");
        }

        System.out.println("== advanced ==");
        Problem quiet = new Problem("quiet", root, false, false);
        quiet.addSuppressed(new IOException("ignored"));
        System.out.println("quiet.message=" + quiet.getMessage());
        System.out.println(
                "quiet.causeSame=" + (quiet.getCause() == root));
        System.out.println(
                "quiet.stackFrames=" + quiet.getStackTrace().length);
        System.out.println(
                "quiet.suppressed=" + quiet.getSuppressed().length);

        Problem full = new Problem("full", root, true, true);
        full.addSuppressed(new IOException("resource closed badly"));
        System.out.println(
                "full.stackPresent=" + (full.getStackTrace().length > 0));
        System.out.println(
                "full.suppressed=" + full.getSuppressed().length);
        System.out.println(
                "full.suppressedMessage="
                + full.getSuppressed()[0].getMessage());

        System.out.println("== stack timing ==");
        Problem created = createProblem();
        System.out.println(
                "frameAtCreation=" + containsCreateFrame(created));
        try {
            throw created;
        } catch (Problem e) {
            System.out.println(
                    "frameAfterThrow=" + containsCreateFrame(e));
        }

        System.out.println("== resources ==");
        resourceFailure(false);
        resourceFailure(true);
    }

    static Problem createProblem() {
        return new Problem("created");
    }

    static boolean containsCreateFrame(Throwable error) {
        return Arrays.stream(error.getStackTrace())
                .anyMatch(f -> f.getMethodName().equals("createProblem"));
    }

    static void resourceFailure(boolean enableSuppression) {
        try (ClosingResource ignored = new ClosingResource()) {
            throw new Problem(
                    "operation failed", null, enableSuppression, true);
        } catch (Exception e) {
            String prefix = enableSuppression
                    ? "suppressionOn"
                    : "suppressionOff";
            System.out.println(
                    prefix + ".primary=" + e.getMessage());
            System.out.println(
                    prefix + ".suppressed=" + e.getSuppressed().length);
            if (e.getSuppressed().length > 0) {
                System.out.println(
                        prefix + ".suppressedMessage="
                        + e.getSuppressed()[0].getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ThrowableConstructorsDemo.java
java ThrowableConstructorsDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
== constructors ==
empty.message=null
message=validation failed
causeOnly.message=java.lang.IllegalArgumentException: bad input
causeOnly.causeSame=true
wrapped.message=cannot load
wrapped.causeType=IllegalArgumentException
== deferred cause ==
late.causeSame=true
initCause repeated=IllegalStateException
explicitNull replacement=IllegalStateException
== advanced ==
quiet.message=quiet
quiet.causeSame=true
quiet.stackFrames=0
quiet.suppressed=0
full.stackPresent=true
full.suppressed=1
full.suppressedMessage=resource closed badly
== stack timing ==
frameAtCreation=true
frameAfterThrow=true
== resources ==
suppressionOff.primary=operation failed
suppressionOff.suppressed=0
suppressionOn.primary=operation failed
suppressionOn.suppressed=1
suppressionOn.suppressedMessage=close error
~~~

### Giải thích theo nhóm đầu ra

**Nhóm constructors:** `Problem()` không có message. `Problem("validation failed")` có message. `Problem(root)` dùng `root.toString()` làm message và giữ chính `root` làm cause. `Problem("cannot load", root)` giữ message độc lập và tham chiếu cause.

**Nhóm deferred cause:** `Problem("later")` tạo đối tượng chưa khởi tạo cause, nên `initCause(root)` hợp lệ một lần. Gọi lại ném `IllegalStateException`. Ngược lại, `Problem("null cause", null)` đã khởi tạo cause dù giá trị là `null`, nên không được thay thế sau.

**Nhóm advanced:** `quiet` có suppression và writable stack trace đều bị tắt, nên `getSuppressed()` rỗng và `getStackTrace()` rỗng. Cause và message vẫn được giữ. `full` bật hai tính năng nên có stack trace và lưu ngoại lệ được thêm qua `addSuppressed`.

**Nhóm stack timing:** `createProblem()` tạo đối tượng và tên phương thức này có trong stack trace. Ném lại chính đối tượng không làm mất frame đó; hai phép kiểm tra đều trả `true`.

**Nhóm resources:** Trong cả hai lần, thân try-with-resources ném `Problem("operation failed", ...)` và `ClosingResource.close()` ném `IOException("close error")`. Với suppression bị tắt trên ngoại lệ chính, `getSuppressed()` rỗng. Với suppression được bật, lỗi đóng tài nguyên nằm trong danh sách suppressed. **Lỗi khi đóng không được biến thành cause tự động.**

## 12. Message, cause, suppressed và stack trace là bốn thành phần riêng

Một mô hình hữu ích:

~~~text
Throwable X
├── message: văn bản mô tả chính X
├── cause: Throwable Y hoặc null
│   └── Y có message, cause, suppressed, stack trace riêng
├── suppressed: [Throwable S1, Throwable S2, ...]
└── stack trace: các frame được ghi cho chính X
~~~

Không nên đồng nhất những thành phần này.

| Thông tin | API đọc | Mục đích |
| --- | --- | --- |
| Message | `getMessage()` | Giải thích lỗi ở mức người đọc |
| Message bản địa hóa | `getLocalizedMessage()` | Có thể được lớp con tùy biến; mặc định theo message |
| Cause | `getCause()` | Truy vết nguyên nhân của lỗi bọc |
| Suppressed | `getSuppressed()` | Giữ những lỗi bổ sung mà không thay lỗi chính |
| Stack trace | `getStackTrace()` | Vị trí và đường gọi đã ghi cho đối tượng |
| In dấu vết | `printStackTrace()` | Hiển thị lỗi chính cùng quan hệ cause/suppressed |

**Không phải mọi ngoại lệ có cause đều do một constructor bốn tham số.** Phần lớn ứng dụng chỉ cần constructor `(String, Throwable)` thông thường. Constructor nâng cao phục vụ những yêu cầu riêng về lưu giữ dữ liệu chẩn đoán.

## 13. Constructor của lớp con: vì sao phải gọi `super(...)`?

Ví dụ lớp ngoại lệ miền nghiệp vụ:

~~~java
public final class ConfigurationException extends Exception {
    public ConfigurationException(String message) {
        super(message);
    }

    public ConfigurationException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là một lớp độc lập nếu lưu vào `ConfigurationException.java`. Các overload của nó gọi constructor tương ứng ở lớp cha, để `Throwable` nhận được message và cause.

Nếu chỉ định nghĩa:

~~~java
public ConfigurationException(String message) {
    // Không gọi super(message).
}
~~~

thì nếu lớp cha có constructor không tham số phù hợp, Java ngầm gọi `super()`. Chuỗi `message` không tự được lưu vào trạng thái của `Throwable`; `getMessage()` có thể vẫn là `null`. Đây là **đoạn minh họa phản ví dụ**, chỉ có ý nghĩa khi đặt trong lớp phù hợp.

Nếu cần tùy chọn `enableSuppression` hoặc `writableStackTrace`, lớp con có thể khai báo một constructor nhận thêm hai boolean và gọi overload `protected` của `Exception`/`RuntimeException` hoặc của `Throwable` theo đúng chuỗi kế thừa. Cần cân nhắc liệu **API công khai có nên để caller quyết định hai cờ nguy hiểm này** hay giữ chính sách cố định trong lớp.

### Lớp lỗi unchecked cũng có thể dùng cấu hình nâng cao

~~~java
public final class LightweightFailure extends RuntimeException {
    public LightweightFailure(String message) {
        super(message, null, false, false);
    }
}
~~~

Đây là lớp độc lập nếu lưu trong `LightweightFailure.java`. Vì kế thừa `RuntimeException` nên nó là unchecked exception; việc tắt suppression và stack trace **không phải nguyên nhân** khiến nó unchecked.

Một lỗi như vậy chỉ phù hợp khi hệ thống chủ động chấp nhận mất thông tin chẩn đoán trên những đối tượng của lớp này. Không nên coi đây là mẫu mặc định cho exception tùy biến.

## 14. Các API stack trace và giới hạn khi tùy chỉnh

`Throwable.fillInStackTrace()` và `Throwable.setStackTrace(StackTraceElement[])` cho phép thao tác với dữ liệu stack trace trong một số trường hợp.

Ví dụ sử dụng thông thường:

~~~java
Throwable problem = new Throwable("example");
StackTraceElement[] frames = problem.getStackTrace();

System.out.println(frames.length > 0);
~~~

Khi tạo đối tượng trong một phương thức đang chạy bình thường, thường in `true`. Tuy nhiên không nên viết kiểm tra ứng dụng dựa vào **chính xác số frame** hoặc tên file/dòng, vì thông tin stack phụ thuộc nơi tạo và môi trường thực thi.

Nếu `writableStackTrace = false`, việc cố gọi `fillInStackTrace()` hoặc `setStackTrace(...)` không khôi phục dấu vết cho chính đối tượng đã bị tắt theo cơ chế constructor.

### Không nên biến stack trace thành hợp đồng nghiệp vụ

Stack trace hữu ích để gỡ lỗi nhưng không ổn định để dùng làm khóa dữ liệu, điều kiện luồng hoặc thông điệp cho người dùng cuối. Ví dụ, không viết logic kiểu:

~~~java
if (error.getStackTrace()[0].getClassName()
        .equals("com.example.Service")) {
    // Quyết định phục hồi dựa trên frame đầu.
}
~~~

Đây là **mã phản ví dụ**, giả định biến `error` có sẵn. Nó còn có thể ném `ArrayIndexOutOfBoundsException` nếu stack trace rỗng (điều rất dễ xảy ra với `writableStackTrace=false`). Hãy dựa trên **kiểu ngoại lệ**, trường mã lỗi ổn định, trạng thái nghiệp vụ hoặc cause có cấu trúc.

## 15. Cấu hình nâng cao và hiệu năng: đánh đổi cần hiểu rõ

Việc tạo ngoại lệ và thu thập stack trace có chi phí. Tắt writable stack trace có thể giảm công việc thu thập dấu vết trong một số trường hợp đặc biệt, nhưng **không nên tối ưu hóa chỉ từ giả định**:

- Ngoại lệ vốn được thiết kế cho các tình huống bất thường; dùng `throw/catch` làm nhánh điều khiển bình thường với tần suất rất cao thường khiến thiết kế khó đọc.
- Tắt stack trace có thể gây thiệt hại lớn khi phải chẩn đoán sự cố production.
- Tắt suppression làm mất thông tin lỗi thứ cấp, nhất là khi đóng tài nguyên.
- Một đối tượng ngoại lệ tái sử dụng có thể mang message/cause/stack trace từ sự cố cũ, gây nhầm lẫn nếu phát sinh nhiều lỗi độc lập.
- Hiệu quả của một thay đổi hiệu năng phải được đánh giá bằng phép đo thực tế trong môi trường mục tiêu.

**Quy tắc thực hành:** dùng constructor chuẩn với message và cause trước; chỉ tạo lớp lỗi có cấu hình đặc biệt khi có lý do kiến trúc, đo đạc hoặc hợp đồng rõ ràng.

## 16. Những hiểu lầm thường gặp

### Hiểu lầm 1 — “Constructor ngoại lệ tự động ném lỗi”

Không. `new IOException("...")` chỉ tạo đối tượng. `throw new IOException("...");` mới phát sinh đường lan truyền ngoại lệ.

### Hiểu lầm 2 — “Mọi lớp con của `Throwable` thừa kế hết các constructor”

Không. Constructor không được kế thừa; mỗi lớp con phải khai báo overload nó muốn cung cấp.

### Hiểu lầm 3 — “`Throwable(cause)` dùng `cause.getMessage()` làm message”

Không chính xác. Constructor cause-only thường tạo message từ `cause.toString()`, có thể bao gồm tên lớp và message.

### Hiểu lầm 4 — “`getCause()==null` nghĩa là luôn được gọi `initCause(...)`”

Sai. Constructor nhận cause đã khởi tạo trạng thái cause ngay cả khi truyền `null`. Chỉ cause thực sự **chưa được khởi tạo** mới có thể dùng `initCause` hợp lệ.

### Hiểu lầm 5 — “Cause có thể được đổi nhiều lần”

Không. `initCause` chỉ dùng một lần trên trạng thái chưa khởi tạo; constructor đã nhận cause thì không thể thay thế bằng `initCause`.

### Hiểu lầm 6 — “`getCause()` và `getSuppressed()` cùng một cơ chế”

Không. Cause thể hiện quan hệ nguyên nhân; suppressed lưu các lỗi phụ được giữ lại, đặc biệt khi đóng tài nguyên.

### Hiểu lầm 7 — “Tắt suppression có nghĩa lỗi khi đóng tài nguyên không xảy ra”

Không. Lỗi vẫn có thể xảy ra; chỉ là đối tượng ngoại lệ chính không giữ danh sách suppressed.

### Hiểu lầm 8 — “`writableStackTrace=false` có nghĩa ngoại lệ không được ném”

Không. Đối tượng vẫn có thể bị `throw` và `catch`; chỉ thiếu dấu vết stack trace của chính nó.

### Hiểu lầm 9 — “Tắt stack trace ở wrapper cũng xóa stack trace của cause”

Không. Mỗi `Throwable` có thông tin chẩn đoán riêng. Cause vẫn có thể giữ stack trace của chính nó.

### Hiểu lầm 10 — “Có thể gọi `fillInStackTrace()` để bật lại stack trace đã bị tắt”

Không. Khi constructor đặt `writableStackTrace=false`, cơ chế stack trace của đối tượng được thiết lập theo cấu hình đó.

### Hiểu lầm 11 — “Message phải là khóa logic ổn định cho ứng dụng”

Không. Message là văn bản giải thích; nếu cần quyết định tự động, thiết kế mã lỗi có cấu trúc hoặc ngoại lệ chuyên biệt.

### Hiểu lầm 12 — “Bắt `Throwable` là cách chuẩn để tránh mọi lỗi”

Không. `Throwable` bao gồm cả `Error`; bắt quá rộng có thể che lỗi nghiêm trọng và làm ứng dụng tiếp tục trong trạng thái không an toàn. Chỉ dùng tại ranh giới hệ thống có chính sách rõ.

### Hiểu lầm 13 — “`printStackTrace()` luôn cho cùng định dạng”

Không nên dựa vào một định dạng byte-for-byte cho logic nghiệp vụ hoặc test cứng, vì stack trace có thể khác theo đường gọi và môi trường chạy.

### Hiểu lầm 14 — “Nếu đã có cause thì không cần message”

Không hẳn. Message cung cấp bối cảnh tầng hiện tại; cause giữ nguồn gốc. Constructor nhận cả hai thường giúp người đọc hiểu hơn.

### Hiểu lầm 15 — “Tắt cả hai cờ luôn là tối ưu hiệu năng tốt”

Không. Đó là đánh đổi giữa chi phí ghi nhận và khả năng chẩn đoán; cần đo đạc và chính sách thiết kế phù hợp.

## 17. Bài tập tự kiểm tra

1. Nêu điểm khác nhau giữa `new IllegalArgumentException("x")` và `throw new IllegalArgumentException("x");`.
2. Liệt kê năm dạng constructor của `Throwable` và chỉ ra overload nào là `protected`.
3. Khi tạo `new Throwable()`, `getMessage()` và `getCause()` trả gì?
4. Constructor `Throwable(Throwable cause)` lấy message từ `cause.getMessage()` hay `cause.toString()`?
5. `new Throwable("error", null)` có cho phép `initCause(new IOException())` về sau không? Vì sao?
6. Khi nào `initCause(...)` hợp lệ và khi nào ném `IllegalStateException`?
7. Nếu truyền chính một đối tượng ngoại lệ làm cause của nó bằng `initCause` thì điều gì xảy ra?
8. Hai cờ `enableSuppression` và `writableStackTrace` điều khiển hai loại dữ liệu nào?
9. Tắt suppression có xóa `getCause()` không?
10. Nếu thân try-with-resources ném một đối tượng có suppression bị tắt và `close()` cũng lỗi, `getSuppressed()` của lỗi chính phản ánh điều gì?
11. `writableStackTrace=false` ảnh hưởng `getStackTrace()` như thế nào?
12. Nếu wrapper tắt writable stack trace nhưng cause có stack trace bình thường, dữ liệu stack trace của cause có bị mất không?
13. Tại sao một lớp ngoại lệ tùy biến cần gọi `super(message, cause)`?
14. Tại sao `catch (Exception e)` không chắc nhận được mọi đối tượng trong nhánh `Throwable`?
15. `Throwable(String, Throwable, boolean, boolean)` có thể được gọi trực tiếp từ bất kỳ lớp nào hay không?
16. Nêu một trường hợp API cần constructor nhận cause thay vì chỉ có message.
17. Việc ném lại cùng một đối tượng ngoại lệ có tự động viết lại vị trí tạo trên stack trace không?
18. Tại sao dùng message hoặc frame của stack trace để quyết định nhánh nghiệp vụ là không ổn định?
19. Nếu `getStackTrace()` trả mảng rỗng, truy cập `[0]` có an toàn không?
20. Trước khi tắt stack trace vì hiệu năng, nên xem xét những yếu tố nào?

### Gợi ý đáp án

1. `new` tạo đối tượng; `throw` mới ném.
2. Không tham số; message; cause; message+cause; message+cause+enableSuppression+writableStackTrace; dạng cuối là `protected`.
3. Thường đều `null`.
4. `cause.toString()` khi cause khác `null`.
5. Không, vì cause đã được khởi tạo bằng constructor dù giá trị là `null`.
6. Hợp lệ một lần trên đối tượng có cause chưa khởi tạo; nếu đã khởi tạo thì `IllegalStateException`.
7. `IllegalArgumentException` vì self-causation không hợp lệ.
8. Danh sách suppressed exceptions và khả năng ghi stack trace.
9. Không.
10. Danh sách rỗng dù lỗi khi đóng thực sự có thể xảy ra.
11. Trả mảng rỗng cho chính đối tượng đó.
12. Không; cause có trạng thái riêng.
13. Để khởi tạo đúng các trường chẩn đoán do `Throwable` quản lý.
14. `Error` không thuộc nhánh `Exception`.
15. Không; overload bốn tham số của `Throwable` là `protected`.
16. Khi chuyển lỗi I/O thành một lỗi nghiệp vụ tầng cao mà vẫn cần giữ nguyên nhân.
17. Không; stack trace mặc định thường được ghi khi tạo, không tự viết lại cho mỗi lần ném.
18. Chúng có thể thay đổi theo ngữ cảnh, phiên bản, môi trường; nên dùng kiểu và mã lỗi có cấu trúc.
19. Không; phải kiểm tra độ dài trước.
20. Cần cân nhắc đo đạc hiệu năng, tần suất tạo lỗi và chi phí mất khả năng điều tra sự cố.

## 18. Ghi nhớ

**Constructor của `Throwable` khởi tạo dữ liệu chẩn đoán; `throw` mới ném đối tượng.** Dùng message để giải thích lỗi, cause để bảo toàn nguyên nhân, suppressed exceptions để giữ các lỗi phụ và stack trace để định vị nơi đối tượng được tạo. Constructor `protected` bốn tham số cho phép lớp con tắt suppression hoặc stack trace, nhưng có thể làm mất thông tin quan trọng khi điều tra sự cố. Với phần lớn mã Java, ưu tiên các constructor chuẩn `(String message)` và `(String message, Throwable cause)`; chỉ sử dụng cấu hình nâng cao khi hiểu rõ và chấp nhận các đánh đổi.