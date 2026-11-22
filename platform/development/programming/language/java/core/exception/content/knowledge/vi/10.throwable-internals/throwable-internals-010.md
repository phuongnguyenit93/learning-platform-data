# Cấu hình `enableSuppression` và `writableStackTrace` trong Java `Throwable`

Một đối tượng `Throwable` trong Java mang nhiều loại thông tin để giải thích sự cố: **thông điệp**, **nguyên nhân** (`cause`), **những ngoại lệ phụ** (`suppressed exceptions`) và **stack trace** mô tả vị trí/ngăn xếp lời gọi. Với các lớp ngoại lệ được thiết kế có chủ đích, Java cung cấp hai tùy chọn khi khởi tạo:

- **`enableSuppression`**: có cho phép gắn và lưu các ngoại lệ phụ bằng `addSuppressed()` hay không.
- **`writableStackTrace`**: đối tượng có được xây dựng với stack trace có thể ghi lại và cập nhật hay không.

Hai cờ **độc lập**. Tắt `enableSuppression` không tự động bỏ stack trace; tắt `writableStackTrace` không tự động xóa `cause` hay thông điệp; tắt cả hai cũng **không ngăn ngoại lệ được ném và bắt**. Các lựa chọn này chủ yếu hữu ích khi thiết kế một **lớp ngoại lệ đặc biệt**, vì chúng làm thay đổi thông tin chẩn đoán mà các API, logger và `try-with-resources` có thể lưu giữ.

Trên Java 17+, các cờ được cấu hình tại thời điểm tạo đối tượng, qua constructor bốn tham số dạng `(String message, Throwable cause, boolean enableSuppression, boolean writableStackTrace)` mà các lớp `Throwable`/`Exception`/`RuntimeException` cung cấp ở mức truy cập **`protected`**. Vì vậy code sử dụng thường định nghĩa **lớp ngoại lệ con** và chuyển các cờ tới `super(...)`, chứ không gọi constructor bốn tham số của `Throwable` trực tiếp từ mã client không có quyền truy cập.

## 1. Bốn mảnh thông tin của một `Throwable`

Xét cách tạo ngoại lệ tiêu chuẩn:

~~~java
// Đoạn minh họa bên trong một phương thức.
Throwable original = new IllegalArgumentException("đầu vào sai");
IllegalStateException wrapped =
        new IllegalStateException("không xử lý được", original);
~~~

Đối tượng `wrapped` mang những thông tin có ý nghĩa khác nhau:

| Thông tin | API thường dùng | Ý nghĩa |
| --- | --- | --- |
| Thông điệp | `getMessage()` | Mô tả thất bại, ví dụ `không xử lý được` |
| Nguyên nhân | `getCause()` | Ngoại lệ trước dẫn tới ngoại lệ hiện tại, ở đây là `original` |
| Ngoại lệ phụ | `getSuppressed()`, `addSuppressed(Throwable)` | Các lỗi bổ sung xuất hiện trong khi xử lý hoặc dọn dẹp, chẳng hạn `close()` thất bại |
| Stack trace | `getStackTrace()`, `printStackTrace()`, `fillInStackTrace()` | Những frame lời gọi được ghi nhận tại thời điểm capture stack trace |

**`cause` và `suppressed` không đồng nghĩa.** Ví dụ một `IOException` từ bước đọc có thể là ngoại lệ chính, còn lỗi đóng stream được `try-with-resources` đính kèm như suppressed. Khi tầng nghiệp vụ bọc `IOException` thành ngoại lệ khác, `IOException` có thể trở thành `cause` của ngoại lệ bọc.

Theo cách tạo thông thường, stack trace được điền khi một `Throwable` được xây dựng, nhưng một số lớp và constructor có thể chọn không thu thập hoặc thay đổi thông tin đó. Hai cờ của bài học không quyết định một lời gọi có ném ngoại lệ hay không; chúng quyết định **đối tượng giữ lại những thông tin chẩn đoán nào**.

## 2. Cú pháp constructor bốn tham số

Các lớp nền liên quan cung cấp constructor:

~~~java
// Chữ ký minh họa, không phải lời khai báo có thể đặt độc lập ngoài lớp.
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

`Exception` và `RuntimeException` cũng có constructor bốn tham số với ý nghĩa tương ứng, ở mức `protected`. Để sử dụng an toàn, định nghĩa một lớp ngoại lệ riêng:

~~~java
public class ConfigurableFailure extends RuntimeException {
    public ConfigurableFailure(
            String message,
            Throwable cause,
            boolean enableSuppression,
            boolean writableStackTrace) {
        super(message, cause, enableSuppression, writableStackTrace);
    }
}
~~~

Đây là một **lớp độc lập hợp lệ** nếu lưu trong tệp `ConfigurableFailure.java`. Vì kế thừa `RuntimeException`, nó là **unchecked exception**; nếu cần checked exception, lớp có thể kế thừa `Exception` và dùng constructor tương ứng.

Các tham số:

1. `message`: thông điệp chi tiết, có thể là `null`; trả về từ `getMessage()`.
2. `cause`: nguyên nhân gây ra ngoại lệ hiện tại, có thể `null`; trả về từ `getCause()`.
3. `enableSuppression`: bật/tắt khả năng ghi nhận các ngoại lệ bổ sung.
4. `writableStackTrace`: bật/tắt việc tạo và ghi stack trace trên **chính đối tượng này**.

Ví dụ tạo một ngoại lệ có đầy đủ thông tin:

~~~java
ConfigurableFailure detailed =
        new ConfigurableFailure("lỗi chi tiết", null, true, true);
~~~

Ví dụ tạo ngoại lệ tối giản:

~~~java
ConfigurableFailure minimal =
        new ConfigurableFailure("lỗi tối giản", null, false, false);
~~~

Các đoạn gọi trên giả định lớp `ConfigurableFailure` đã được khai báo. Việc tạo `minimal` không tự ném lỗi; khi cần chuyển sang xử lý ngoại lệ, bạn mới dùng `throw minimal;`.

**Lưu ý phạm vi truy cập:** vì constructor trên `Throwable` là `protected`, đoạn client ngoài phạm vi được phép như `new Throwable("x", null, false, false)` sẽ không biên dịch. Dùng lớp con phù hợp và công bố constructor của lớp con theo ý định thiết kế.

## 3. `enableSuppression=true`: lưu các lỗi phụ

Khi suppression được bật, lời gọi:

~~~java
// Đoạn minh họa trong phương thức có biến Throwable primary.
primary.addSuppressed(new java.io.IOException("lỗi đóng"));
~~~

có thể thêm một `Throwable` phụ vào danh sách của `primary`. Gọi:

~~~java
Throwable[] extra = primary.getSuppressed();
~~~

sẽ trả một mảng các lỗi đã được ghi nhận, theo thứ tự thêm vào. Với một `Throwable` thông thường có bật suppression và chưa có lỗi phụ nào, `getSuppressed()` trả về mảng rỗng.

Cơ chế này được Java dùng trong `try-with-resources` khi thao tác chính ném lỗi, và việc đóng tài nguyên cũng ném lỗi. Lỗi chính vẫn được ưu tiên làm ngoại lệ truyền ra; ngoại lệ đóng được ghi nhận như thông tin phụ.

Ví dụ logic:

~~~text
Đọc dữ liệu ném IOException("lỗi đọc")
    |
    +-- close() ném IOException("lỗi đóng")
    |
    v
Ngoại lệ chính: lỗi đọc
    Suppressed: lỗi đóng
~~~

Lưu ý rằng Java **không tự gắn mọi ngoại lệ thứ hai thành suppressed**. Cơ chế đó có trong các hoàn cảnh cụ thể như `try-with-resources`, hoặc do lập trình viên chủ động gọi `addSuppressed()`. Một `try/finally` tự viết có thể làm ngoại lệ từ `finally` che lỗi trước đó nếu không xử lý đúng.

## 4. `enableSuppression=false`: `addSuppressed()` không ghi nhận lỗi

Khi một đối tượng `Throwable` được xây dựng với `enableSuppression=false`:

- Danh sách suppressed của **đối tượng đó** bị vô hiệu hóa.
- Gọi `getSuppressed()` trả về **mảng rỗng**.
- Lời gọi `addSuppressed(validThrowable)` không lưu ngoại lệ mới vào đối tượng đó.
- Việc tắt suppression **không** làm mất `message`, `cause`, hoặc tự động vô hiệu hóa stack trace.
- Đối tượng vẫn có thể được `throw`, được `catch`, được dùng làm `cause` của đối tượng khác và được in/log như ngoại lệ.

Ví dụ:

~~~java
// Đoạn minh họa trong một phương thức, ConfigurableFailure đã định nghĩa.
ConfigurableFailure failure =
        new ConfigurableFailure("không xử lý được", null, false, true);

failure.addSuppressed(new java.io.IOException("đóng tệp lỗi"));
System.out.println(failure.getSuppressed().length); // 0
~~~

Điều đáng lo nhất xuất hiện với `try-with-resources`: nếu **lỗi chính bị ném trong body là một đối tượng tắt suppression**, Java vẫn có thể gọi `addSuppressed()` để cố gắn lỗi đóng tài nguyên, nhưng thông tin này sẽ **không được lưu trên đối tượng chính**.

Vì vậy, dù tắt suppression có thể có chủ đích trong một lớp ngoại lệ đặc biệt, **không nên tắt nó cho các lỗi dùng trong code cần truy vết thất bại khi đóng tài nguyên**.

Quy tắc API vẫn tồn tại: `addSuppressed(null)` không trở thành một thao tác hợp lệ, và cố tự suppress chính đối tượng cũng là sử dụng sai; đừng xem cờ `false` là cách bỏ qua mọi quy tắc kiểm tra đối số. Trường hợp cụ thể nên kiểm tra theo hợp đồng `Throwable.addSuppressed`.

## 5. `writableStackTrace=true`: stack trace được thu thập theo cách thông thường

Với `writableStackTrace=true`, constructor của `Throwable` thường thu thập stack trace tại thời điểm xây dựng. Đây là các frame cho biết đường gọi gần điểm tạo ngoại lệ, đặc biệt hữu ích khi tìm vị trí lỗi.

~~~java
// Đoạn minh họa khi đối tượng đã tạo.
StackTraceElement[] frames = failure.getStackTrace();
for (StackTraceElement frame : frames) {
    System.out.println(frame.getClassName() + "." + frame.getMethodName());
}
~~~

Các khía cạnh quan trọng:

- `getStackTrace()` trả một mảng `StackTraceElement`; vị trí đầu thường ứng với điểm stack trace được điền.
- `printStackTrace()` có thể hiển thị stack trace cùng thông tin `cause` và `suppressed`.
- `fillInStackTrace()` có thể cập nhật vị trí stack trace theo trạng thái stack hiện tại, khi ghi stack trace được cho phép.
- `setStackTrace(StackTraceElement[])` cho phép đặt một stack trace được cung cấp hợp lệ theo hợp đồng API.
- Việc `throw ex;` một đối tượng đã tồn tại **không tự động đồng nghĩa với chụp stack trace mới** ở dòng `throw`.

Mặc dù stack trace thường có ít nhất một frame đối với ngoại lệ ứng dụng thông thường, Java cho phép các tình huống đặc biệt mà VM hoặc một lớp `Throwable` tùy chỉnh không cung cấp đầy đủ frame. Vì vậy không nên viết ứng dụng phụ thuộc vào vị trí cố định của một frame mà không kiểm tra mảng.

## 6. `writableStackTrace=false`: đối tượng không ghi stack trace

Khi `writableStackTrace=false`, constructor bốn tham số không thu thập stack trace thông thường cho đối tượng; stack trace được để **`null` ở trạng thái nội bộ**. Ở giao diện API công khai:

- `getStackTrace()` trả **mảng rỗng**.
- `fillInStackTrace()` **không cập nhật** stack trace và trả về chính `Throwable` đó.
- `setStackTrace(...)` **không thay đổi** stack trace của đối tượng.
- `printStackTrace()` có thể vẫn in tên lớp và thông điệp, cũng như các nhánh `cause` hoặc `suppressed` nếu có, nhưng không có những frame stack trace thông thường của đối tượng đã bị tắt.
- `throw`/`catch` đối tượng vẫn hoạt động bình thường.
- Nếu `enableSuppression=true`, bạn vẫn có thể lưu các ngoại lệ phụ với **stack trace riêng của chính chúng**, dù đối tượng chính không có frame.

Ví dụ:

~~~java
// Đoạn minh họa trong phương thức, ConfigurableFailure đã định nghĩa.
ConfigurableFailure failure =
        new ConfigurableFailure("không lưu vị trí", null, true, false);

failure.fillInStackTrace();
failure.setStackTrace(new StackTraceElement[] {
        new StackTraceElement("Demo", "run", "Demo.java", 42)
});
System.out.println(failure.getStackTrace().length); // 0
~~~

Không nên nhầm với `setStackTrace(new StackTraceElement[0])` ở đối tượng có `writableStackTrace=true`: hai tình huống có thể cùng cho mảng rỗng hiện tại, nhưng **cấu hình ghi stack trace khác nhau**. Đối tượng bị vô hiệu hóa qua constructor không trở lại trạng thái ghi được chỉ bằng gọi `setStackTrace` hoặc `fillInStackTrace`.

Vì không còn frame, việc xác định nơi tạo hoặc phát sinh lỗi có thể trở nên khó khăn. Chỉ chọn cấu hình này khi bạn có lý do rõ ràng và thông tin chẩn đoán khác đủ dùng.

## 7. Hai cờ độc lập: bốn tổ hợp

| `enableSuppression` | `writableStackTrace` | `addSuppressed()` | `getStackTrace()` |
| --- | --- | --- | --- |
| `true` | `true` | Ghi nhận lỗi phụ | Ghi/đọc stack trace thông thường |
| `true` | `false` | Vẫn ghi nhận lỗi phụ | Không có các frame của đối tượng chính |
| `false` | `true` | Không ghi nhận lỗi phụ | Vẫn có stack trace thông thường |
| `false` | `false` | Không ghi nhận lỗi phụ | Không có stack trace của đối tượng chính |

Không có quy tắc “tắt một cờ bắt buộc tắt cờ còn lại”. Nếu chỉ muốn bớt chi phí ghi stack trace của một loại ngoại lệ đặc biệt, **không bắt buộc tắt suppression**; việc tắt suppression riêng chỉ nên làm khi thật sự chấp nhận mất khả năng đính kèm lỗi phụ.

Cả hai cờ là cấu hình **khi khởi tạo**. API công khai không có một setter đơn giản tên `setEnableSuppression(boolean)` hoặc `setWritableStackTrace(boolean)` để bật lại tùy ý trên một đối tượng đã tạo.

## 8. Ví dụ Java 17+ hoàn chỉnh: thử cả bốn tổ hợp

Lưu tệp `ThrowableFlagsDemo.java`:

~~~java
import java.io.IOException;

public class ThrowableFlagsDemo {
    static class ConfigurableFailure extends RuntimeException {
        ConfigurableFailure(String message, Throwable cause,
                            boolean enableSuppression, boolean writableStackTrace) {
            super(message, cause, enableSuppression, writableStackTrace);
        }
    }

    static void show(String name, boolean suppress, boolean trace) {
        ConfigurableFailure ex = new ConfigurableFailure(name, null, suppress, trace);
        ex.addSuppressed(new IOException("đóng tài nguyên"));
        System.out.println(name + ": suppressed=" + ex.getSuppressed().length
                + ", stackAvailable=" + (ex.getStackTrace().length > 0));
    }

    public static void main(String[] args) {
        show("true/true", true, true);
        show("true/false", true, false);
        show("false/true", false, true);
        show("false/false", false, false);

        Throwable root = new IllegalArgumentException("lỗi gốc");
        ConfigurableFailure minimal = new ConfigurableFailure("thất bại", root, false, false);
        minimal.fillInStackTrace();
        minimal.setStackTrace(new StackTraceElement[] {
            new StackTraceElement("Demo", "work", "Demo.java", 5)
        });
        System.out.println("cause=" + minimal.getCause().getMessage());
        System.out.println("stack sau cập nhật=" + minimal.getStackTrace().length);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ThrowableFlagsDemo.java
java ThrowableFlagsDemo
~~~

**Đầu ra đã kiểm chứng trên Java 17+ đối với chương trình này:**

~~~text
true/true: suppressed=1, stackAvailable=true
true/false: suppressed=1, stackAvailable=false
false/true: suppressed=0, stackAvailable=true
false/false: suppressed=0, stackAvailable=false
cause=lỗi gốc
stack sau cập nhật=0
~~~

Diễn giải:

1. `show(...)` tạo từng ngoại lệ với bộ cờ riêng. Tên `true/false` ở đầu dòng theo thứ tự **suppression/stack trace**, không phải giá trị của cause hay lỗi được ném.
2. Với suppression bật, một `IOException` phụ được thêm nên `getSuppressed().length == 1`. Với suppression tắt, lời gọi thêm không lưu nên độ dài bằng `0`.
3. Với writable stack trace bật, đối tượng `ConfigurableFailure` được tạo trong một chuỗi lời gọi có stack trace khả dụng; với cờ tắt, `getStackTrace()` trả mảng rỗng.
4. `minimal` là đối tượng bị tắt cả hai tính năng, nhưng vẫn mang cause `IllegalArgumentException("lỗi gốc")`, vì cấu hình này **không tắt quan hệ nguyên nhân**.
5. Các lời gọi `fillInStackTrace()` và `setStackTrace(...)` không biến `minimal` thành đối tượng có stack trace ghi được. Vì thế dòng cuối là `0`.

Dùng `ex.getStackTrace().length > 0` để minh họa khả năng stack trace trong chương trình chạy thông thường; không nên tổng quát hóa rằng mọi đối tượng Java trong mọi hoàn cảnh và mọi JVM bắt buộc có số frame dương.

## 9. Ứng dụng thực tế: lỗi đóng tài nguyên bị mất khỏi `getSuppressed()`

Đây là khác biệt có ảnh hưởng nhất đến việc xử lý lỗi. `try-with-resources` có cơ chế ưu tiên ngoại lệ từ body hoặc initializer làm **lỗi chính**, đồng thời cố giữ lỗi phát sinh khi đóng tài nguyên dưới dạng suppressed.

Nếu chính ngoại lệ chính được tạo với `enableSuppression=false`, quá trình tự động thêm suppressed vẫn có thể được gọi theo ngữ nghĩa của Java, nhưng **không có lỗi phụ nào được lưu lại trên ngoại lệ đó**.

Tệp `SuppressedFlagsDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedFlagsDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đóng tài nguyên");
            throw new IOException("lỗi đóng");
        }
    }

    static class TaskFailure extends Exception {
        TaskFailure(boolean suppression) {
            super("lỗi tác vụ", null, suppression, true);
        }
    }

    static void run(boolean suppression) {
        try (Resource resource = new Resource()) {
            throw new TaskFailure(suppression);
        } catch (Exception ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Suppressed: " + ex.getSuppressed().length);
        }
    }

    public static void main(String[] args) {
        System.out.println("Suppression bật");
        run(true);
        System.out.println("Suppression tắt");
        run(false);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SuppressedFlagsDemo.java
java SuppressedFlagsDemo
~~~

Stdout chính xác:

~~~text
Suppression bật
Đóng tài nguyên
Lỗi chính: lỗi tác vụ
Suppressed: 1
Suppression tắt
Đóng tài nguyên
Lỗi chính: lỗi tác vụ
Suppressed: 0
~~~

Điểm cần quan sát:

- `TaskFailure` là **checked exception** vì kế thừa `Exception`, nhưng phương thức `run` bắt nó qua `catch (Exception)`; không cần khai báo `throws` để lỗi truyền ra ngoài.
- Cả hai lượt đều chạy `close()`, và `close()` đều ném `IOException`.
- Lượt suppression bật giữ lỗi đóng trong `getSuppressed()`; lượt suppression tắt giữ lỗi `TaskFailure` làm chính nhưng **không giữ thông tin `IOException` phụ** trong danh sách.
- `writableStackTrace` được truyền `true` trong cả hai lượt; kết quả khác nhau là do cờ suppression, không phải stack trace.

Điều này giải thích vì sao **không nên tắt suppression cho exception thông thường của nghiệp vụ hoặc I/O**. Khi dữ liệu chẩn đoán từ quá trình đóng tài nguyên có thể rất quan trọng, việc tắt nó có thể làm điều tra sự cố khó hơn đáng kể.

## 10. `cause` độc lập với cả hai cờ

Constructor bốn tham số nhận **`cause` riêng**. Tắt suppression và writable stack trace của ngoại lệ bao ngoài **không xóa** cause đã được truyền vào:

~~~java
// Đoạn minh họa, ConfigurableFailure đã khai báo.
Throwable root = new java.io.IOException("đọc cấu hình lỗi");
ConfigurableFailure wrapper =
        new ConfigurableFailure("khởi động thất bại", root, false, false);

System.out.println(wrapper.getMessage());      // khởi động thất bại
System.out.println(wrapper.getCause() == root); // true
~~~

Đối tượng `root` có stack trace riêng theo cách nó được tạo. Do đó một ngoại lệ bọc bị tắt stack trace **vẫn có thể chứa một cause có stack trace**; việc in chuỗi nguyên nhân có thể cung cấp dấu vết lỗi gốc. Tuy nhiên, không nên mặc định luôn có cause hoặc nó luôn đủ thông tin: `getCause()` có thể là `null`.

Hãy phân biệt hai công việc khi debug:

- **Cause:** tìm *vì sao một ngoại lệ này được tạo từ một ngoại lệ trước*.
- **Suppressed:** tìm *những ngoại lệ bổ sung xảy ra trong quá trình xử lý/dọn dẹp*.

Một đối tượng có thể có cause nhưng không có suppressed, có suppressed nhưng không có cause, có cả hai, hoặc không có cả hai. Stack trace của đối tượng chính là một kênh thông tin thứ ba, tách biệt.

Có một điểm triển khai constructor cần biết: truyền trực tiếp `cause` vào constructor bốn tham số (kể cả `null`) là cách **khởi tạo trạng thái cause**. Không nên dự định gọi `initCause()` sau đó trên cùng đối tượng chỉ để thay đổi nguyên nhân; `initCause()` được thiết kế cho các ngoại lệ chưa khởi tạo cause. Nếu cần cause, hãy xác định và truyền vào constructor theo thiết kế hợp đồng.

## 11. Cờ cấu hình thuộc `Throwable` hiện tại, không lan truyền tự động

Giả sử:

~~~java
// Đoạn minh họa với ConfigurableFailure đã định nghĩa.
Throwable root = new IllegalArgumentException("đầu vào sai");
ConfigurableFailure wrapper =
        new ConfigurableFailure("không hoàn thành", root, false, false);
~~~

Cờ suppression/trace ở `wrapper` áp dụng trên **wrapper**. Nó **không thay đổi** các đặc tính hay stack trace của `root`. Nếu `root` có suppressed exceptions, chúng vẫn gắn với `root`; nếu wrapper tắt suppression, chỉ danh sách suppressed của wrapper không ghi nhận thêm.

Tương tự:

~~~java
// Minh họa trường hợp wrapper giữ được lỗi phụ dù stack trace wrapper đã tắt.
ConfigurableFailure wrapper =
        new ConfigurableFailure("thất bại", null, true, false);
wrapper.addSuppressed(new IllegalStateException("lỗi phụ"));
~~~

Đối tượng wrapper không có frame stack trace của nó, nhưng `getSuppressed()` vẫn có thể trả về ngoại lệ phụ `IllegalStateException`, và ngoại lệ phụ có thể có stack trace riêng.

Hai cờ **không được truyền theo quan hệ kế thừa động** tới mọi ngoại lệ được tạo về sau; mỗi đối tượng có trạng thái tùy theo constructor và cách nó được tạo. Đây là điểm quan trọng khi đọc `printStackTrace()` của một chuỗi nhiều tầng cause/suppressed.

## 12. `printStackTrace()` thể hiện sự khác biệt thế nào?

Với một `Throwable` thường được tạo có stack trace ghi được, `printStackTrace()` thường in thông tin như:

~~~text
com.example.Failure: thao tác lỗi
    at com.example.Service.run(Service.java:25)
    at com.example.Main.main(Main.java:10)
    Suppressed: java.io.IOException: lỗi đóng
        at ...
Caused by: java.lang.IllegalArgumentException: đầu vào sai
    at ...
~~~

Đây là **sơ đồ minh họa, không phải stdout cố định**: tên lớp, đường dẫn, số dòng và bố cục rút gọn khác nhau theo code/JDK và độ dài stack trace.

Khi `writableStackTrace=false`, phần **frame của ngoại lệ chính** thường không có; nhưng thông điệp vẫn có thể xuất hiện. Khi `enableSuppression=false`, những suppressed exceptions được thêm qua `addSuppressed()` không xuất hiện từ đối tượng chính. Nếu có cause, stack trace của cause vẫn có thể được trình bày.

Việc thiếu frame không đồng nghĩa với việc ngoại lệ không được ném hoặc không có lỗi. Đó có thể là **quyết định cấu hình**, nên đừng kết luận “không có stack trace tức là không có call stack”.

## 13. Khi nào nên cân nhắc tắt `writableStackTrace`?

Các constructor `Throwable` thông thường thu thập stack trace và quá trình này có thể có chi phí. Trong một số hệ thống rất đặc thù, người phát triển có thể cân nhắc một loại ngoại lệ chỉ đóng vai trò **tín hiệu luồng điều khiển nội bộ**, được ném/bắt rất thường xuyên, vị trí ném đã biết rõ và không cần thông tin call stack cho từng lượt.

Nhưng đây là lựa chọn **đánh đổi**, không phải mặc định nên áp dụng:

1. Cần đo bằng **benchmark/profile của chính ứng dụng**, không giả định mọi lần tắt trace đều tăng hiệu năng đáng kể ở mức hệ thống.
2. Xác định mất stack trace có làm quá trình điều tra production khó hơn không. Các lỗi hiếm, khó tái hiện thường cần stack trace.
3. Xem liệu đang dùng ngoại lệ cho một trường hợp luồng điều khiển thông thường hay không; nếu có, **trả về giá trị hoặc kiểu kết quả phù hợp** thường rõ nghĩa hơn việc dùng exception thường xuyên.
4. Nếu phải tối ưu một ngoại lệ chuyên dụng, cân nhắc vẫn bật suppression khi code có thể đi qua `try-with-resources` hoặc cơ chế cần giữ lỗi phụ.
5. Đánh giá logging, metrics và observability. Một số hệ thống coi stack trace là dữ liệu bắt buộc để phân nhóm sự cố.

**Không nên dùng `writableStackTrace=false` như một cách giấu thông tin nhạy cảm.** Việc bảo mật dữ liệu phải dựa vào thiết kế thông điệp, chính sách log, kiểm soát truy cập và lọc thông tin. Một đối tượng lỗi thiếu trace có thể vẫn chứa `message`, `cause` hoặc dữ liệu khác cần bảo vệ.

## 14. Khi nào nên hoặc không nên tắt suppression?

Tắt suppression chỉ thích hợp khi một lớp ngoại lệ **được thiết kế đặc biệt** và người viết có thể khẳng định việc lưu các lỗi phụ không có giá trị hay sẽ không dùng đến. Đây là trường hợp hẹp.

Lý do nên giữ mặc định `true` trong phần lớn code:

- `try-with-resources` dựa vào suppressed exceptions để không mất lỗi đóng tài nguyên khi đã có lỗi chính.
- Một số chiến lược cleanup/audit thủ công cũng dùng `addSuppressed()` để giữ lỗi phụ.
- Công cụ ghi log có thể in suppressed giúp truy ra tất cả bước thất bại.
- Nếu tắt suppression, những lời gọi `addSuppressed()` hợp lệ **không lưu dữ liệu**, dễ khiến code xử lý tưởng đã bảo toàn lỗi trong khi thực tế không có.
- Việc tắt suppression trên một đối tượng không có nghĩa các đối tượng khác sẽ tự tắt; nên tránh trạng thái hỗn hợp khó lý giải nếu chưa có hợp đồng thiết kế.

Nhìn chung, chi phí tiềm năng của việc mất thông tin chẩn đoán thường quan trọng hơn lợi ích giả định khi tắt suppression đại trà. Với exception nghiệp vụ, I/O, cơ sở dữ liệu và thao tác phân tán, nên ưu tiên traceability và khả năng bảo toàn nguyên nhân.

## 15. Các bẫy API và hiểu nhầm phổ biến

| Nhầm lẫn / cách dùng sai | Thực tế và cách sửa |
| --- | --- |
| `enableSuppression=false` có nghĩa ngoại lệ không thể bị `throw` | Sai. Ngoại lệ vẫn được ném/bắt theo kiểu của nó. Chỉ tính năng lưu lỗi phụ bị tắt. |
| `writableStackTrace=false` xóa cả message và cause | Sai. Message/cause vẫn độc lập với stack trace của đối tượng đó. |
| Tắt suppression sẽ làm `try-with-resources` không gọi `close()` | Sai. Tài nguyên vẫn được đóng; chỉ việc ghi nhận lỗi đóng như suppressed trên lỗi chính bị ảnh hưởng. |
| `getSuppressed().length == 0` chứng minh không có lỗi đóng | Không chắc. Suppression có thể đã bị tắt, hoặc đơn giản chưa có lỗi phụ. |
| `getStackTrace().length == 0` chứng minh lỗi không hề phát sinh | Sai. Có thể stack trace đã bị tắt hoặc bị thay đổi; kiểm tra loại lỗi và bối cảnh. |
| `fillInStackTrace()` tự bật lại `writableStackTrace` | Sai. Với cờ `false`, nó không cập nhật stack trace của đối tượng. |
| `setStackTrace(...)` luôn làm đối tượng có stack frame | Sai. Đối tượng được tạo với writable trace bị tắt sẽ không nhận thay đổi. |
| Truyền `cause=null` nghĩa là constructor chưa thiết lập cause | Constructor nhận cause trực tiếp khởi tạo trạng thái cause. Đừng dự tính thay bằng `initCause()` sau đó. |
| Tắt cờ trên wrapper thì cause cũng mất trace/suppressed | Sai. Cờ thuộc từng `Throwable` riêng, không thay đổi đối tượng cause. |
| Gọi `new Throwable(message, cause, false, false)` ở bất kỳ mã client nào | Constructor bốn tham số là `protected`; cần dùng trong lớp con/ngữ cảnh được phép. |
| Dùng cả hai cờ `false` cho mọi lỗi để tăng tốc | Làm mất dữ liệu quan trọng; chỉ tối ưu khi có profile, hợp đồng rõ và chấp nhận đánh đổi. |
| Ghi log mỗi `getMessage()` là đủ | Có thể mất cause, suppressed và stack trace; ưu tiên ghi nguyên đối tượng `Throwable` tại ranh giới phù hợp. |

## 16. Tự kiểm tra kiến thức

**Câu 1.** `enableSuppression=false` có làm `getCause()` trả `null` không?

**Đáp án:** Không. Cause là thông tin độc lập; nếu truyền một cause khác `null` vào constructor, `getCause()` vẫn trả tham chiếu đó.

**Câu 2.** Ngoại lệ bị tắt stack trace có được ném lại bằng `throw ex;` không?

**Đáp án:** Có. `writableStackTrace=false` không thay đổi việc ngoại lệ có thể được ném/bắt.

**Câu 3.** `Throwable` được tạo với `writableStackTrace=false` trả về gì từ `getStackTrace()`?

**Đáp án:** Mảng rỗng, đối với cơ chế constructor bốn tham số được mô tả.

**Câu 4.** Có thể dùng `setStackTrace()` để bật lại việc ghi stack trace đã tắt bằng constructor không?

**Đáp án:** Không. Lời gọi không khôi phục tính năng ghi stack trace của đối tượng đó.

**Câu 5.** Nếu `try-with-resources` có lỗi body và lỗi đóng, nhưng lỗi body tắt suppression, chuyện gì xảy ra?

**Đáp án:** Lỗi body vẫn là ngoại lệ chính; lỗi đóng sẽ không được lưu trong `getSuppressed()` của nó theo cơ chế suppression thông thường.

**Câu 6.** Hai cờ có luôn phải nhận cùng giá trị không?

**Đáp án:** Không. Bốn tổ hợp `true/true`, `true/false`, `false/true`, `false/false` đều có ý nghĩa hợp lệ.

**Câu 7.** Tắt stack trace của wrapper có xóa stack trace của cause không?

**Đáp án:** Không. Cause là đối tượng khác, có trạng thái riêng.

**Câu 8.** Chữ ký bốn tham số trực tiếp của `Throwable` có thể được gọi từ mọi lớp code thông thường không?

**Đáp án:** Không; constructor đó là `protected`. Lớp ngoại lệ con có thể gọi `super(message, cause, enableSuppression, writableStackTrace)`.

**Câu 9.** Nếu một loại exception thường dùng để báo lỗi I/O, có nên mặc định tắt suppression không?

**Đáp án:** Không. Suppressed exception có thể là nơi duy nhất ghi lại lỗi đóng tài nguyên xảy ra cùng lỗi chính.

**Câu 10.** Vì sao hai cờ không phải giải pháp hiệu năng mặc định?

**Đáp án:** Vì chúng có thể làm mất thông tin chẩn đoán, còn lợi ích hiệu năng phụ thuộc cách dùng và cần đo thực tế.

## 17. Tài liệu tham khảo chính thức

- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): constructor bốn tham số, `getCause()`, `addSuppressed()`, `getSuppressed()`, `getStackTrace()`, `setStackTrace()` và `fillInStackTrace()`.
- [Java SE 17 API — `Exception`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): constructor `protected` cho checked exception tùy chỉnh với hai cờ.
- [Java SE 17 API — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): constructor `protected` với suppression và writable stack trace.
- [Java Language Specification 17 — §14.20.3, `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): đóng tài nguyên và cách lưu ngoại lệ phụ khi có lỗi chính.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): ngoại lệ, lan truyền và xử lý theo ngữ nghĩa Java.

**Kết luận:** `enableSuppression` kiểm soát **lưu lỗi phụ**, còn `writableStackTrace` kiểm soát **ghi stack trace** của chính `Throwable`. Chúng được cấu hình khi tạo đối tượng, không thay đổi khả năng ném/bắt và không tự xóa cause. Phần lớn ứng dụng nên giữ thông tin chẩn đoán đầy đủ; chỉ tắt một hoặc cả hai cờ cho những lớp ngoại lệ chuyên biệt khi đã hiểu và chấp nhận rõ hậu quả.
