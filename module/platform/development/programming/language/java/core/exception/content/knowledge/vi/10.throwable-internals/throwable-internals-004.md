# `printStackTrace` và cách biểu diễn đầy đủ một ngoại lệ trong Java

Khi Java ném ngoại lệ, việc chỉ nhìn một câu thông báo như `"read failed"` thường không đủ để chẩn đoán. Đối tượng **`Throwable`** còn mang loại lỗi, *stack trace* (chuỗi lời gọi), *cause* (nguyên nhân bên dưới) và *suppressed exceptions* (các lỗi phụ bị giữ lại, thường phát sinh lúc đóng tài nguyên). Phương thức **`printStackTrace()`** dùng để in thông tin chẩn đoán từ đối tượng đó.

Điểm quan trọng nhất:

> `getMessage()` chỉ cung cấp thông điệp; `toString()` thường thêm tên lớp; `printStackTrace()` hiển thị thông tin lỗi cùng các khung gọi, chuỗi nguyên nhân và ngoại lệ bị suppressed theo định dạng stack trace. Không nên nhầm ba cách biểu diễn này là tương đương.

Bài học trình bày cách đọc đầy đủ một ngoại lệ, cách lấy hoặc ghi lại stack trace, các giới hạn của nó, và cách dùng an toàn trong chương trình Java 17+.

## 1. Một đối tượng `Throwable` lưu những gì?

Gốc của hệ phân cấp ngoại lệ Java là `java.lang.Throwable`. Hai nhánh trực tiếp quan trọng là `Exception` và `Error`; `RuntimeException` là lớp con của `Exception`. `Throwable` cung cấp các API chung để kiểm tra thông tin lỗi.

| Thành phần | API thông dụng | Thông tin nhận được |
| --- | --- | --- |
| Kiểu ngoại lệ | `ex.getClass()`, `ex.getClass().getName()` | Tên lớp thực tế của đối tượng được ném |
| Thông điệp | `ex.getMessage()` | Chuỗi mô tả lỗi, có thể là `null` |
| Thông điệp bản địa hóa | `ex.getLocalizedMessage()` | Theo mặc định thường giống `getMessage()`, có thể khác nếu lớp ghi đè |
| Tóm tắt lỗi | `ex.toString()` | Thường là tên lớp, kèm thông điệp nếu có |
| Nguyên nhân | `ex.getCause()` | Một `Throwable` khác hoặc `null` |
| Danh sách lỗi phụ | `ex.getSuppressed()` | Mảng `Throwable[]`, có thể rỗng |
| Các khung gọi | `ex.getStackTrace()` | Mảng các `StackTraceElement` mô tả những vị trí ghi nhận stack |
| Hiển thị đầy đủ | `ex.printStackTrace()` | In dạng người đọc được ra `System.err` |
| Hiển thị tới luồng tùy chọn | `ex.printStackTrace(PrintStream/PrintWriter)` | In stack trace tới đích được cung cấp |

Các khái niệm ở bảng không có nghĩa rằng mọi đối tượng lúc nào cũng có đầy đủ message, cause, suppressed hay stack frames. Chẳng hạn, `getMessage()` và `getCause()` có thể trả về `null`, còn `getSuppressed()` có thể là mảng rỗng.

### Cùng một lỗi nhưng các mức biểu diễn khác nhau

Giả sử:

```java
IllegalArgumentException ex =
        new IllegalArgumentException("quantity must be positive");
```

Đây là một câu lệnh minh họa cần nằm trong một phương thức/lớp. Các cách quan sát:

```java
System.out.println(ex.getMessage());
System.out.println(ex.toString());
```

**Stdout:**

```text
quantity must be positive
java.lang.IllegalArgumentException: quantity must be positive
```

Nếu viết `ex.printStackTrace();`, Java thường in thêm những dòng `at ...` ra **stderr**, không phải stdout. Vị trí và số dòng cụ thể phụ thuộc tệp nguồn, đường gọi và runtime; do đó không nên coi toàn bộ bản in là một chuỗi cố định có thể hard-code trong tài liệu.

## 2. `printStackTrace()` thực sự làm gì?

`Throwable` có ba cách gọi phổ biến:

```java
ex.printStackTrace();
ex.printStackTrace(System.err);
ex.printStackTrace(new java.io.PrintWriter(writer));
```

Đây là các **câu lệnh minh họa**, với `ex` là `Throwable` và `writer` là một `java.io.Writer` hợp lệ.

- **`printStackTrace()`:** in stack trace của đối tượng tới **`System.err`** — luồng lỗi chuẩn.
- **`printStackTrace(PrintStream stream)`:** in ra `PrintStream` được truyền, chẳng hạn `System.out` hoặc `System.err`.
- **`printStackTrace(PrintWriter writer)`:** in ra `PrintWriter` do caller quản lý, thuận tiện khi cần ghi vào một buffer hoặc writer.

Cả ba đều **trả về `void`**. `printStackTrace()` không trả lại `String`, không khôi phục chương trình khỏi lỗi, và **không ném lại ngoại lệ** đang được in.

### Phân biệt stdout với stderr

`System.out` dành cho đầu ra chuẩn; `System.err` dành cho đầu ra lỗi. Một lệnh:

```java
System.out.println("before");
ex.printStackTrace();
System.out.println("after");
```

có thể tạo hai dòng stdout và một stack trace trên stderr. Khi console hoặc môi trường thực thi gộp hai luồng, thứ tự hiển thị có thể phụ thuộc cơ chế thu gom luồng. Vì vậy:

- Không dùng sự xen kẽ giữa stdout và stderr làm bằng chứng chắc chắn về thứ tự xử lý.
- Trong ví dụ cần **stdout chính xác**, nên in dữ liệu tóm tắt ổn định thay vì đoán số dòng/đường dẫn trong stack trace.
- `printStackTrace()` phù hợp để điều tra nhanh, nhưng ứng dụng production thường nên dùng logger có khả năng nhận `Throwable` và quản lý nơi lưu, mức độ, ngữ cảnh.

**Một stack trace được in** và **một ngoại lệ chưa được bắt** là hai khái niệm khác nhau. Có thể gọi `printStackTrace()` trong `catch` rồi tiếp tục chương trình; ngược lại, một ngoại lệ có thể không được bắt và cơ chế xử lý mặc định của thread mới là nơi in thông tin lỗi.

## 3. Hình dạng thường gặp của một stack trace

Một ví dụ mang tính **minh họa cấu trúc**, không phải transcript số dòng cố định:

```text
java.lang.IllegalStateException: cannot complete checkout
    at example.CheckoutService.checkout(CheckoutService.java:<line>)
    at example.Main.main(Main.java:<line>)
    Suppressed: java.lang.IllegalArgumentException: close warning
        at example.Resource.close(Resource.java:<line>)
        ... <frames omitted>
Caused by: java.io.IOException: storage offline
    at example.Storage.read(Storage.java:<line>)
    ... <frames omitted>
```

Những mục quan trọng:

1. **Dòng đầu:** `Throwable.toString()` — tên lớp ngoại lệ và thông điệp nếu có.
2. **`at package.Class.method(File.java:line)`:** một vị trí trong stack trace. Các khung thường được liệt kê từ vị trí gần nguồn lỗi nhất tới caller.
3. **`Suppressed: ...`:** một ngoại lệ phụ gắn với ngoại lệ chính, thường từ thao tác đóng tài nguyên.
4. **`Caused by: ...`:** một đối tượng `Throwable` được gắn làm nguyên nhân.
5. **`... N more`:** một số khung cuối trùng với stack của ngoại lệ bao ngoài nên được rút gọn khi in. Đây là **cách nén hiển thị**, không có nghĩa thông tin “bị mất” khỏi đối tượng.

Một số stack trace có nhiều cấp `Caused by` hoặc nhiều mục `Suppressed`, và mỗi ngoại lệ phụ có thể lại mang cause hoặc suppressed riêng. Không phải ngoại lệ nào cũng có đủ các mục trên; chương trình chỉ in những gì đối tượng đang mang.

### Cách đọc nhanh khi có nhiều lớp ngoại lệ

Nếu dòng đầu là `ServiceException` còn cuối phần cause là `SocketTimeoutException`, điều đó thường có nghĩa tầng service đã **bọc** một lỗi sâu hơn từ tầng mạng. Nên đọc cả hai:

- **Ngoại lệ ngoài:** loại lỗi mà tầng gọi hiện tại đang xử lý, cùng ngữ cảnh cấp cao.
- **Nguyên nhân bên trong:** điều gì đã thất bại ở lớp thấp hơn.
- **Vị trí trong stack:** đoạn mã nào tạo/làm lan truyền lỗi theo dấu vết đã ghi.
- **Suppressed:** các vấn đề dọn dẹp/tài nguyên xuất hiện ngoài ngoại lệ chính.

Không nên chỉ lấy dòng `Caused by` cuối cùng làm nguyên nhân chắc chắn trong mọi trường hợp. Các tầng có thể chuyển lỗi sai, làm mất cause, hoặc tạo một lỗi không liên quan; cần đối chiếu ngữ cảnh và hành vi thực tế.

## 4. `StackTraceElement` là gì?

Mỗi frame được biểu diễn bằng một `java.lang.StackTraceElement`. Khi đọc một bản `printStackTrace()`, dòng `at package.Class.method(File.java:line)` thường tương ứng với thông tin của một frame.

| API | Câu hỏi trả lời |
| --- | --- |
| `getClassName()`, `getMethodName()` | Lớp và phương thức nào được ghi? |
| `getFileName()`, `getLineNumber()` | Có tệp nguồn và số dòng nào không? |
| `isNativeMethod()` | Frame có thuộc native method không? |
| `getModuleName()`, `getClassLoaderName()` | Có metadata module/class loader không? |

Tên tệp có thể `null`, số dòng có thể âm, và trace có thể rỗng; không parse chuỗi `File.java:123` như dữ liệu ổn định. `getStackTrace()` trả **mảng frame**, còn `printStackTrace()` là bản hiển thị có cả cause/suppressed. Nếu cần khám phá getter, bản sao phòng vệ và dữ liệu module, bài `getStackTrace`/`StackTraceElement` là nơi giải thích chính.

## 5. Khi nào stack trace được ghi lại?

Trong hành vi thông thường của `Throwable`, stack trace được ghi nhận **khi đối tượng ngoại lệ được tạo/khởi tạo** (thông qua cơ chế như `fillInStackTrace()`), chứ không nhất thiết tại mỗi lần dùng `throw`.

Ví dụ:

```java
static IllegalArgumentException createError() {
    return new IllegalArgumentException("invalid quantity");
}

static void raiseError(IllegalArgumentException ex) {
    throw ex;
}
```

Đây là hai phương thức minh họa. Nếu tạo đối tượng bằng `createError()` rồi ném nó ở `raiseError()`, việc ném lại **cùng đối tượng** không tự động viết lại stack trace thành vị trí `raiseError()`. Điều này giúp bảo toàn nguồn gốc đã ghi nhưng đôi khi làm người đọc tưởng ngoại lệ được ném đúng tại chỗ nó được tạo.

**`Throwable.fillInStackTrace()`** có thể cập nhật stack trace dựa trên vị trí hiện tại, nhưng đây là thao tác thay đổi bằng chứng chẩn đoán. Trừ trường hợp có chủ đích và kiểm thử rõ, nên **ném lại cùng đối tượng** để giữ thông tin gốc, hoặc **bọc bằng ngoại lệ mới có cause** nếu cần một tầng ngữ cảnh mới.

Với một ngoại lệ mới:

```java
throw new IllegalStateException(
        "checkout processing failed", original);
```

Biến `original` phải là một `Throwable` thật đã tồn tại trong phạm vi. Ngoại lệ ngoài có stack trace được ghi ở nơi tạo nó; ngoại lệ gốc giữ stack trace riêng và được nối qua `getCause()`. `printStackTrace` giúp đọc cả hai.

### Re-throw không phải tạo ngoại lệ mới

So sánh:

- **`throw ex;`:** ném lại cùng đối tượng. Kiểu runtime, message, cause và stack trace hiện tại vẫn thuộc đối tượng đó.
- **`throw new SomeException("context", ex);`:** tạo đối tượng mới với stack trace riêng, gắn `ex` làm cause.
- **`throw new SomeException(ex.getMessage());`:** có thể làm mất liên kết tới đối tượng gốc nếu không có cơ chế giữ khác.

Đừng bọc nhiều tầng chỉ để thêm thông điệp `"failed"` giống nhau; stack trace dài hơn không có nghĩa chẩn đoán tốt hơn.

## 6. `getMessage()`, `toString()` và `printStackTrace()` khác nhau ra sao?

Giả sử `IOException ex = new IOException("read failed");`:

| Cách gọi | Ví dụ đầu ra hoặc loại kết quả | Có stack frames? | Có chuỗi cause/suppressed đầy đủ? |
| --- | --- | --- | --- |
| `ex.getMessage()` | `"read failed"` | Không | Không |
| `ex.toString()` | `"java.io.IOException: read failed"` | Không | Không |
| `ex.getStackTrace()` | `StackTraceElement[]` | Có dưới dạng dữ liệu | Không trực tiếp chứa quan hệ cause/suppressed |
| `ex.printStackTrace()` | In thông tin định dạng trên `System.err` | Có | Có nếu ngoại lệ đang mang dữ liệu đó |
| `ex.printStackTrace(writer)` | Ghi vào `PrintWriter` | Có | Có nếu ngoại lệ đang mang dữ liệu đó |

**`toString()`** mặc định của `Throwable` đưa tên lớp và thông điệp được bản địa hóa (`getLocalizedMessage()`) nếu thông điệp không null. Một lớp ngoại lệ tùy chỉnh có thể override các phương thức liên quan nên chuỗi chính xác còn phụ thuộc loại lỗi.

**`getMessage()`** có thể là `null`, vì vậy một lệnh như:

```java
System.out.println(ex.getMessage().length());
```

có thể ném `NullPointerException` trong chính handler. Khi xây dựng thông điệp chẩn đoán, hãy dùng cơ chế xử lý giá trị null phù hợp.

**`printStackTrace()`** là hành động **ghi ra đích đầu ra**, không phải API trả chuỗi. Gọi `String trace = ex.printStackTrace();` là **lỗi biên dịch** vì phương thức trả `void`.

## 7. Ví dụ Java 17+ hoàn chỉnh: biểu diễn ngoại lệ gồm type, cause, suppressed và trace

Chương trình sau tạo một ngoại lệ ngoài, gắn nguyên nhân gốc và một ngoại lệ phụ, rồi **bắt stack trace bằng `StringWriter`**. Thay vì in raw trace chứa số dòng không ổn định, nó in các kiểm tra dạng boolean có kết quả xác định với JDK 17 thông thường.

Lưu tệp **`ThrowablePortraitDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class ThrowablePortraitDemo {

    static IllegalStateException buildError() {
        IOException cause = new IOException("storage offline");

        IllegalStateException error =
                new IllegalStateException(
                        "cannot complete checkout", cause);

        error.addSuppressed(
                new IllegalArgumentException("close warning"));
        return error;
    }

    public static void main(String[] args) {
        IllegalStateException error = buildError();

        System.out.println(
                "type: " + error.getClass().getSimpleName());
        System.out.println("message: " + error.getMessage());
        System.out.println("toString: " + error);

        System.out.println(
                "cause: "
                + error.getCause().getClass().getSimpleName());
        System.out.println(
                "suppressed count: "
                + error.getSuppressed().length);

        System.out.println(
                "first method: "
                + error.getStackTrace()[0].getMethodName());

        StringWriter buffer = new StringWriter();
        error.printStackTrace(new PrintWriter(buffer));
        String trace = buffer.toString();

        System.out.println(
                "has header: "
                + trace.startsWith(
                        "java.lang.IllegalStateException: "
                        + "cannot complete checkout"));

        System.out.println(
                "has frame: "
                + trace.contains("ThrowablePortraitDemo.buildError"));

        System.out.println(
                "has suppressed: "
                + trace.contains(
                        "Suppressed: java.lang.IllegalArgumentException: "
                        + "close warning"));

        System.out.println(
                "has cause: "
                + trace.contains(
                        "Caused by: java.io.IOException: storage offline"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ThrowablePortraitDemo.java
java ThrowablePortraitDemo
```

**Stdout chính xác** (không phụ thuộc số dòng trong tệp):

```text
type: IllegalStateException
message: cannot complete checkout
toString: java.lang.IllegalStateException: cannot complete checkout
cause: IOException
suppressed count: 1
first method: buildError
has header: true
has frame: true
has suppressed: true
has cause: true
```

### Phân tích từng phần

- `getClass().getSimpleName()` xác định **kiểu thực tế** của ngoại lệ ngoài: `IllegalStateException`.
- `getMessage()` chỉ hiển thị thông điệp của ngoại lệ ngoài.
- `toString()` hiển thị cả tên lớp đầy đủ và message.
- `getCause()` dẫn đến `IOException("storage offline")`. Đây là nguyên nhân do lập trình viên chuyển vào constructor.
- `getSuppressed()` chứa một `IllegalArgumentException("close warning")`, được thêm bằng `addSuppressed`.
- `getStackTrace()[0].getMethodName()` là `buildError`, bởi đối tượng `IllegalStateException` được tạo ở phương thức đó.
- `printStackTrace(new PrintWriter(buffer))` ghi văn bản vào buffer. Các phép `contains` kiểm tra thông tin nguyên nhân, lỗi phụ và khung gọi trong bản hiển thị đầy đủ.

Ví dụ **không tự ném ngoại lệ** ra ngoài `main`. Bạn hoàn toàn có thể dùng `printStackTrace` để phân tích một đối tượng `Throwable` chỉ vừa được tạo hoặc đã được bắt; việc in không đồng nghĩa ngoại lệ đang lan truyền.

## 8. Ví dụ Java 17+ hoàn chỉnh: đọc từng khung của một chuỗi lời gọi

Lưu thành **`TraceOriginDemo.java`**:

```java
public class TraceOriginDemo {

    static void origin() {
        throw new IllegalArgumentException("bad quantity");
    }

    static void middle() {
        origin();
    }

    public static void main(String[] args) {
        try {
            middle();
        } catch (IllegalArgumentException ex) {
            StackTraceElement[] frames = ex.getStackTrace();

            System.out.println(
                    "first method: " + frames[0].getMethodName());
            System.out.println(
                    "second method: " + frames[1].getMethodName());
            System.out.println(
                    "third method: " + frames[2].getMethodName());
            System.out.println(
                    "first file: " + frames[0].getFileName());
            System.out.println(
                    "line positive: "
                    + (frames[0].getLineNumber() > 0));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TraceOriginDemo.java
java TraceOriginDemo
```

**Stdout với trình biên dịch Java thông thường có thông tin dòng nguồn:**

```text
first method: origin
second method: middle
third method: main
first file: TraceOriginDemo.java
line positive: true
```

**Giải thích:**

1. `main()` gọi `middle()`.
2. `middle()` gọi `origin()`.
3. `origin()` tạo và ném `IllegalArgumentException`.
4. Handler ở `main()` nhận cùng đối tượng và truy cập mảng `StackTraceElement[]`.
5. Khung đầu nằm ở `origin`; những khung tiếp theo là `middle` rồi `main`. Đây là thứ tự của chuỗi gọi tại thời điểm stack được ghi.

Ví dụ này tập trung vào Java chạy từ các tệp nguồn bằng `javac`. Với bytecode được tối ưu hóa, thiếu thông tin debug hoặc hoàn cảnh runtime đặc biệt, thông tin dòng/khung có thể khác. **Không nên viết kiểm thử ứng dụng phụ thuộc vào số dòng cụ thể** trong stack trace.

## 9. `Caused by`: chuỗi nguyên nhân từ nhiều tầng

Một API tầng thấp có thể ném `IOException`, tầng trên bọc thành `IllegalStateException` để biểu diễn rằng ứng dụng không thể hoàn tất thao tác. Ví dụ:

```java
static void loadRequiredData() {
    try {
        readFromStorage();
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Required data could not be loaded", cause);
    }
}
```

Đây là **phương thức minh họa**, giả định `readFromStorage()` tồn tại và có thể ném `IOException`.

Nếu error ngoài được in với `printStackTrace()`, người đọc có thể thấy:

```text
java.lang.IllegalStateException: Required data could not be loaded
    at ... <stack of wrapper>
Caused by: java.io.IOException: <underlying problem>
    at ... <stack of original exception>
```

Đây là **mô tả cấu trúc**, không phải stdout cố định. `Throwable.getCause()` trả về đối tượng nguyên nhân trực tiếp; có thể lần theo nhiều cấp khi có wrapper lồng nhau.

### Ném lại và bọc lỗi phải là lựa chọn có chủ đích

- Nếu caller ở tầng ngoài vẫn có thể xử lý `IOException`, truyền nguyên ngoại lệ đó lên đôi khi tốt hơn bọc.
- Nếu tầng service cần trình bày lỗi ở mức trừu tượng cao hơn, tạo wrapper có `cause` giúp giữ dấu vết gốc.
- Nếu chỉ viết `throw new IllegalStateException("failed");`, caller có thể **mất nguyên nhân cụ thể** đã bắt.
- Đừng dựa vào nội dung `getMessage()` để dò nguyên nhân theo chuỗi: người viết thư viện có thể đổi cách diễn đạt và nhiều lỗi có thể chia sẻ thông điệp.

Có thể dùng một hàm đọc cause chain khi thực sự cần:

```java
Throwable current = ex;

while (current.getCause() != null) {
    current = current.getCause();
}

System.out.println(current.getClass().getSimpleName());
```

Đây là đoạn minh họa với `ex` là một đối tượng `Throwable`. Trong những lớp tùy chỉnh hoặc dữ liệu không đáng tin, ứng dụng cần đề phòng chuỗi cause bất thường và tránh giả định “lỗi cuối cùng” luôn là nguyên nhân thực tế duy nhất.

## 10. `Suppressed`: ghi nhận lỗi thứ cấp, đặc biệt trong `try-with-resources`

Trong `try-with-resources`, Java tự đóng những tài nguyên `AutoCloseable` khi rời phạm vi. Có trường hợp:

1. Thân `try` đang ném ngoại lệ **E1**.
2. Trong quá trình đóng, `close()` ném ngoại lệ **E2**.
3. Java giữ **E1 là ngoại lệ chính** và gắn E2 làm **suppressed exception** của E1, thay vì để E2 che mất lỗi đã gây thất bại ban đầu.

Dạng minh họa:

```java
try (AutoCloseable resource = openResource()) {
    performWork(resource);
}
```

Đây là khung minh họa; `openResource`, `performWork` phải được định nghĩa, và chữ ký checked exception của `AutoCloseable.close()` có thể yêu cầu `throws Exception` hoặc handler phù hợp.

Tầng ngoài có thể đọc:

```java
for (Throwable secondary : ex.getSuppressed()) {
    System.out.println("secondary: " + secondary);
}
```

`getSuppressed()` trả về mảng, không phải `null`; có thể rỗng khi không có lỗi phụ được lưu.

### Lưu ý về `addSuppressed()`

`Throwable.addSuppressed(Throwable exception)` cho phép gắn một ngoại lệ phụ bằng tay khi chính sách yêu cầu. Không được truyền `null` hoặc tự suppress chính đối tượng đó. Hãy để Java quản lý trường hợp `try-with-resources` chuẩn, tránh tự tái tạo cơ chế nếu không cần thiết.

**Suppressed khác với cause.** Một ngoại lệ cleanup không nhất thiết là nguyên nhân gây lỗi đọc dữ liệu; vì vậy nó thường là *suppressed*, không phải `cause`. `printStackTrace` hiển thị cả hai quan hệ, nhưng `getCause()` không tự chứa danh sách suppressed.

### Một lớp `Throwable` có thể tắt suppression hoặc stack trace

API có những constructor dành cho subclass cho phép điều chỉnh cơ chế suppression và khả năng ghi stack trace. Do đó, trong ứng dụng dùng các ngoại lệ tùy chỉnh đặc biệt, không nên giả định `getSuppressed()` lúc nào cũng phản ánh mọi lỗi phụ hay `getStackTrace()` luôn chứa một tập khung đầy đủ.

Những tùy chọn này chủ yếu phục vụ thiết kế hiệu năng hoặc hợp đồng đặc biệt; với lỗi nghiệp vụ thông thường nên giữ thông tin chẩn đoán đủ dùng.

## 11. Không phải mọi stack trace đều được in nguyên văn mọi khung

Định dạng phổ biến của `printStackTrace` có thể chứa:

```text
... 3 more
```

Điều này nói rằng một số khung cuối của phần cause/suppressed giống các khung cuối đã được in ở ngoại lệ bao ngoài. Chúng được **rút gọn để tránh lặp**. Không phải Java dừng theo dõi lỗi sau ba lời gọi.

Nếu phải phân tích máy móc, hãy làm việc với API có cấu trúc:

```java
Throwable cause = ex.getCause();
StackTraceElement[] frames = ex.getStackTrace();
Throwable[] suppressed = ex.getSuppressed();
```

thay vì tách chuỗi thô theo các dòng `"Caused by:"`, `"Suppressed:"` hoặc `"at "`. Định dạng có thể khác do JVM, module info, logger và công cụ thu thập lỗi.

Mỗi đối tượng nguyên nhân có mảng `getStackTrace()` riêng. Bạn có thể điều tra từng đối tượng thay vì phụ thuộc số lượng dòng mà `printStackTrace` hiển thị.

## 12. `printStackTrace()` có “bắt” hoặc “xử lý” ngoại lệ không?

Không. Ví dụ:

```java
try {
    doWork();
} catch (IllegalStateException ex) {
    ex.printStackTrace();
    System.out.println("handler finished");
}
```

Đây là khung minh họa. `printStackTrace` **chỉ in thông tin**. Handler sẽ kết thúc bình thường nếu không có lệnh ném lại hoặc một ngoại lệ mới xuất hiện, và code có thể tiếp tục ở sau cấu trúc `try-catch`.

Nếu muốn chuyển ngoại lệ lên caller:

```java
try {
    doWork();
} catch (IllegalStateException ex) {
    ex.printStackTrace();
    throw ex;
}
```

Lệnh `throw ex;` mới thật sự ném lại đối tượng; `printStackTrace` không thực hiện điều đó. Dù đoạn này có thể hữu ích trong một thí nghiệm, ứng dụng thật thường không nên vừa in stack trace ở nhiều tầng vừa ném tiếp vì gây **log trùng lặp**.

### Trường hợp không có handler

Một ngoại lệ thoát khỏi điểm bắt đầu của một thread có thể được chuyển đến `UncaughtExceptionHandler`. Triển khai mặc định phổ biến sẽ báo thông tin lỗi và stack trace ra stderr. Nhưng:

- Handler tùy chỉnh có thể thay đổi cách ghi hoặc không ghi.
- Thread gặp lỗi kết thúc; handler không khiến nó quay lại câu lệnh đã thất bại.
- Lỗi trong một tác vụ `ExecutorService.submit()` có thể được framework lưu trong `Future` và đưa về caller qua `ExecutionException` thay vì thành uncaught exception của worker.

Đừng coi mọi stack trace nhìn thấy trong console là ngoại lệ “không được bắt”; nó cũng có thể do lập trình viên hoặc logger in trong một `catch`.

## 13. Cách lấy stack trace thành chuỗi khi thật sự cần

Vì `printStackTrace()` trả `void`, cách thường dùng để lấy bản biểu diễn dạng chuỗi là:

```java
java.io.StringWriter buffer = new java.io.StringWriter();
java.io.PrintWriter writer = new java.io.PrintWriter(buffer);

ex.printStackTrace(writer);
writer.flush();

String traceText = buffer.toString();
```

Đây là đoạn minh họa với `ex` là `Throwable`. `writer.flush()` làm mục đích rõ ràng khi dùng một writer có bộ đệm; `StringWriter` lưu chuỗi trong bộ nhớ.

Không nên dùng cách này trong mọi request production chỉ để lấy message:

- Stack trace có thể rất dài, tiêu thụ bộ nhớ và lưu trữ.
- Bản văn có thể chứa tên file, lớp nội bộ, SQL, đường dẫn hoặc dữ liệu nhạy cảm trong message.
- Nếu hệ thống log hỗ trợ nhận `Throwable`, đưa thẳng đối tượng lỗi cho logger thường tốt hơn việc tạo chuỗi thủ công.

Ví dụ với Java Util Logging (một **đoạn minh họa**, cần biến `ex` và logger thích hợp):

```java
java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("application");

logger.log(
        java.util.logging.Level.SEVERE,
        "Order processing failed",
        ex);
```

Ở đây logger nhận **đối tượng Throwable**, giúp cấu hình handler/formatter quyết định cách ghi trace, thay vì chỉ ghi `ex.getMessage()` và mất chuỗi nguyên nhân.

## 14. Giới hạn của trace: nơi tạo ngoại lệ, không phải mọi điều từng xảy ra

Stack trace là thông tin **chẩn đoán về stack đã được ghi**, không phải bản ghi lịch sử đầy đủ.

Một số giới hạn quan trọng:

- `getStackTrace()` thường phản ánh nơi đối tượng được tạo hoặc nơi `fillInStackTrace()` được gọi gần nhất, **không ghi lại mọi lần rethrow**.
- Stack trace của một thread không tự chứa stack của những thread khác.
- Với bất đồng bộ, callback, `CompletableFuture` hoặc executor, chuỗi cause/wrapper có thể quan trọng hơn một stack đơn.
- Khi code được biên dịch khác, số dòng và tên lớp sinh tự động có thể thay đổi.
- Một số frame có thể không có file/line, hoặc stack trace có thể bị rút gọn/giới hạn bởi runtime.
- Không phải tất cả lỗi đều có cause hay suppressed, ngay cả khi người điều tra muốn có chúng.
- Stack trace đầy đủ không chứng minh dữ liệu đã được rollback hay tài nguyên đã được giải phóng thành công.

Vì vậy, để điều tra production cần kết hợp stack trace với **thời điểm**, **tên thao tác**, **request/correlation ID an toàn**, **phiên bản ứng dụng** và các chỉ số vận hành liên quan.

## 15. Các lỗi thường gặp khi biểu diễn ngoại lệ

| Cách làm sai hoặc thiếu | Hậu quả | Cách tốt hơn |
| --- | --- | --- |
| Chỉ log `ex.getMessage()` | Mất vị trí lỗi, cause, suppressed | Truyền `Throwable` cho logger khi cần điều tra |
| Nghĩ `System.out.println(ex)` in stack trace | Thường chỉ gọi `toString()` | Dùng `printStackTrace` hoặc logger nhận Throwable |
| Nghĩ `ex.printStackTrace()` trả về `String` | Lỗi biên dịch: kiểu trả về `void` | Dùng `StringWriter` + `PrintWriter` khi cần |
| Không phân biệt stdout/stderr | Output trộn, thứ tự khó đoán | Đọc/định tuyến luồng đúng mục đích |
| Cắt trace đến dòng `Caused by` đầu tiên | Mất chuỗi nguyên nhân sâu hoặc lỗi suppressed | Xem toàn bộ Throwable/cause/suppressed |
| Bắt lỗi rồi tạo ngoại lệ mới không giữ `cause` | Mất liên hệ với lỗi gốc | Bọc bằng constructor nhận cause khi phù hợp |
| Giả định mọi `StackTraceElement` có số dòng dương | Sai với native/unknown source | Kiểm tra giá trị và không phụ thuộc số dòng |
| Dò business logic bằng `trace.contains("Parser.java:42")` | Dễ hỏng khi sửa mã/phiên bản | Dùng kiểu ngoại lệ, error code hoặc dữ liệu có cấu trúc |
| In cùng trace ở repository, service, controller | Log trùng, khó phân biệt một sự cố | Chọn ranh giới log và chuyển lỗi rõ ràng |
| In mọi exception message ra API response | Có thể lộ bí mật nội bộ | Tách message công khai và log nội bộ được kiểm soát |
| Nghĩ `printStackTrace` phục hồi chương trình | Chỉ là hành động xuất thông tin | Quyết định `catch`, retry, return hay rethrow riêng |
| Nghĩ suppressed là cause | Hiểu sai quan hệ lỗi | Xem `getCause()` và `getSuppressed()` riêng |
| Dùng `setStackTrace` để giấu vị trí lỗi | Chẩn đoán sai lệch, giảm khả năng kiểm toán | Giữ stack gốc, bổ sung ngữ cảnh bằng wrapper/log |

### Vì sao chỉ log message chưa đủ?

Giả sử log ghi:

```text
failed to read data
```

Dòng này không cho biết lỗi xuất hiện ở đoạn nào, là lỗi I/O nào, ai đã gọi thao tác hay có lỗi đóng tài nguyên không.

Ngược lại, nếu logger nhận cả `Throwable`, bản ghi có thể thể hiện stack trace, nguyên nhân và các lỗi phụ. Tuy nhiên, muốn điều tra hiệu quả vẫn cần **ngữ cảnh an toàn và chính xác**; một stack trace dài mà không biết request nào liên quan có thể vẫn khó xử lý.

## 16. Cẩn thận với dữ liệu nhạy cảm và khối lượng log

Stack trace có thể tiết lộ nhiều thông tin nội bộ. Dòng đầu có thể chứa message do ứng dụng tự tạo hoặc do thư viện cung cấp. Nếu code viết:

```java
throw new IllegalArgumentException(
        "invalid token: " + suppliedToken);
```

thì token có nguy cơ xuất hiện trong `toString()`, `printStackTrace()` và các hệ thống log ghi `Throwable`. Đây là **đoạn chống mẫu**, với `suppliedToken` là biến giả định.

Nên thay bằng thông điệp không lộ bí mật:

```java
throw new IllegalArgumentException("invalid authentication token");
```

Các hướng dẫn thực hành:

1. Không ghép password, secret, API key, cookie hay payload người dùng vào message ngoại lệ.
2. Chọn mã yêu cầu/correlation ID không nhạy cảm cho log có cấu trúc.
3. Không trả toàn bộ stack trace cho khách hàng qua HTTP hay giao diện công khai.
4. Quy định một ranh giới ghi log phù hợp để tránh in nhiều lần cùng một lỗi.
5. Kiểm soát mức log, quyền truy cập, thời gian lưu trữ và số lượng sự kiện khi có lỗi lặp.
6. Không nuốt ngoại lệ chỉ để giảm log; hãy xử lý có chủ đích và quan sát ở tầng phù hợp.

`printStackTrace` là công cụ chẩn đoán, **không phải giao thức phản hồi lỗi ổn định hoặc an toàn để công khai mặc định**.

## 17. Bài tập tự kiểm tra

**Bài A.** `System.out.println(ex)` có tương đương `ex.printStackTrace()` không?

**Không.** Câu đầu thường dùng `Throwable.toString()`, in tên lớp và message; câu sau hiển thị các khung stack cùng cause/suppressed và mặc định ra stderr.

**Bài B.** `Throwable.printStackTrace()` trả về gì?

**`void`.** Muốn bản văn trong một chuỗi, truyền `PrintWriter` gắn với `StringWriter` rồi lấy `buffer.toString()`.

**Bài C.** Nếu `new IllegalStateException("outer", cause)`, `getCause()` trả gì?

Trả về đối tượng `cause` đã được truyền vào constructor (nếu hợp lệ), không phải chuỗi message của cause.

**Bài D.** Trong `try-with-resources`, thân `try` và `close()` cùng ném lỗi. Lỗi khi đóng thường nằm ở đâu?

Trong **`getSuppressed()`** của ngoại lệ chính đến từ thân `try`. Không nên mặc định tìm nó bằng `getCause()`.

**Bài E.** Stack trace in `... 2 more` có nghĩa Java đã làm mất hai frame không?

Không. Đây là cách rút gọn các khung trùng phần cuối đã được in ở ngoại lệ bao ngoài. Có thể xem mảng `getStackTrace()` của từng đối tượng nếu cần dữ liệu theo cấu trúc.

**Bài F.** Một đối tượng ngoại lệ tạo trong `createError()` rồi được `throw` ở `process()`. Phần tử đầu của stack trace luôn là `process()` sao?

Không. Stack trace thông thường được ghi khi ngoại lệ được tạo/khởi tạo; rethrow cùng đối tượng không tự làm lại stack. Cần xét nơi đối tượng được tạo và liệu `fillInStackTrace` có được gọi hay không.

**Bài G.** Có an toàn khi cố định kiểm thử rằng stack trace chứa `OrderService.java:137` không?

Thường không. Số dòng có thể thay đổi khi refactor, biên dịch hoặc chạy ở môi trường khác. Nên kiểm thử loại ngoại lệ, cause, thuộc tính có cấu trúc và hành vi xử lý; chỉ kiểm tra stack khi có yêu cầu chẩn đoán cụ thể.

**Bài H.** Nếu `ex.getMessage()` là `null` thì `ex.toString()` có bị `null` theo không?

Không nhất thiết. Theo hành vi mặc định của `Throwable.toString()`, chuỗi vẫn có tên lớp ngay cả khi thông điệp null. Một lớp tùy chỉnh có thể thay đổi cách biểu diễn.

**Bài I.** `printStackTrace` có làm cho `catch` phục hồi sau ngoại lệ không?

Không. Nó chỉ in thông tin. Handler cần quyết định tiếp tục, chuyển kết quả thất bại, ném lại hoặc bọc ngoại lệ theo chính sách.

**Bài J.** Khi production đã có logger nhận `Throwable`, có nên gọi thêm `printStackTrace()` ở mọi tầng không?

Thường không. Làm vậy dễ tạo bản ghi trùng và bỏ qua cơ chế định tuyến, mức log hay kiểm soát nhạy cảm của logger. Hãy chọn ranh giới logging phù hợp.

## 18. Checklist đọc và ghi một ngoại lệ có trách nhiệm

Khi gặp stack trace, hãy lần lượt:

1. **Xác định loại ngoại lệ ngoài:** đọc dòng đầu hoặc `getClass()`.
2. **Đọc message:** hiểu điều kiện thất bại; xác minh có dữ liệu nhạy cảm không.
3. **Xem các frame:** xác định những phương thức liên quan và vị trí gần nơi stack được ghi nhất.
4. **Xem chuỗi `Caused by`:** tìm nguyên nhân từ tầng thấp và liên hệ tới lỗi cấp cao.
5. **Xem `Suppressed`:** tìm lỗi dọn dẹp/đóng tài nguyên có thể bị bỏ quên.
6. **Hiểu `... N more`:** đó là rút gọn khung trùng, không phải toàn bộ nội dung của nguyên nhân.
7. **Tách stdout và stderr:** đừng suy luận thứ tự chính xác từ console đã gộp luồng.
8. **Xác định ranh giới xử lý:** lỗi đã được `catch`/logger ghi lại hay thực sự thoát khỏi thread?
9. **Đọc ngữ cảnh an toàn:** request ID, thao tác, phiên bản và trạng thái hệ thống, không dựa vào trace đơn lẻ.
10. **Phân biệt xử lý với biểu diễn:** `printStackTrace` không quyết định retry, fallback, rollback hay kết thúc.
11. **Kiểm thử có chủ đích:** ưu tiên loại ngoại lệ/cause/suppressed thay vì so sánh toàn bộ bản trace có số dòng.
12. **Giữ bí mật:** không phát tán stack trace hoặc exception message tùy tiện ra nơi công khai.

**Kết luận:** một ngoại lệ Java không chỉ có message. `Throwable` cho phép quan sát **loại lỗi, thông điệp, stack frames, cause và suppressed exceptions**. `printStackTrace()` là cách biểu diễn tổng hợp thuận tiện để điều tra, mặc định in ra **`System.err`**, còn các overload `PrintStream`/`PrintWriter` cho phép chọn đích ghi. Trong ứng dụng thật, nên giữ nguyên chuỗi nguyên nhân, quản lý lỗi đóng tài nguyên đúng cách và đưa `Throwable` cho logger ở ranh giới có trách nhiệm, thay vì chỉ in thông điệp hoặc hard-code định dạng stack trace.