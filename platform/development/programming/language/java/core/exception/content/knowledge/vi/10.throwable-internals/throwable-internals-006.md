# fillInStackTrace và tác động khi cập nhật dấu vết trong Java

> **Java Core – Exception** · Nhóm: **Đối tượng Throwable** · Ví dụ sử dụng Java 17 trở lên.

## 1. Vấn đề: stack trace của một Throwable biểu diễn thời điểm nào?

Khi Java phát sinh lỗi, đối tượng ngoại lệ thường mang thông tin về **ngăn xếp lời gọi** (*stack trace*), giúp lần theo các phương thức đã thực thi tại một thời điểm. Ví dụ một phần dấu vết có dạng:

~~~text
java.lang.IllegalStateException: service unavailable
    at Example.makeFailure(Example.java:12)
    at Example.main(Example.java:20)
~~~

Các dòng trên chỉ là **minh họa định dạng**, không phải output cố định của chương trình trong bài. Tên file, số dòng, các frame và cách hiển thị thực tế phụ thuộc chương trình, compiler và JVM.

Trong Java, đối tượng `Throwable` thường ghi thông tin stack trace lúc **được tạo ra**, vì phần lớn constructor chuẩn gọi `fillInStackTrace()`. Khi ném lại **cùng một instance** sau đó, lệnh `throw ex;` không tự động ghi lại dấu vết hiện tại của đối tượng này.

Nếu lập trình viên chủ động gọi:

~~~java
ex.fillInStackTrace();
~~~

thì phương thức cố gắng **ghi lại thông tin stack frame của luồng đang chạy tại vị trí gọi hiện tại** vào **chính đối tượng `ex`**, thay cho thông tin trace trước đó, trừ trường hợp khả năng ghi stack trace đã bị vô hiệu hóa hoặc những giới hạn của JVM.

**Điểm cốt lõi:** `fillInStackTrace()` không tạo exception mới, không ném exception đó và không tự bọc cause. Nó **cập nhật vị trí nguồn gốc được thể hiện trong stack trace** của một đối tượng Throwable đang tồn tại.

Sau bài này, bạn có thể:

1. Mô tả điều gì được ghi khi tạo Throwable và điều gì **không** đổi khi chỉ ném lại cùng instance.
2. Giải thích `fillInStackTrace()` ghi lại stack của **thread gọi phương thức**, trả về đối tượng nào và tác động lên dấu vết cũ.
3. Phân biệt `fillInStackTrace()`, `getStackTrace()`, `setStackTrace()`, `printStackTrace()`.
4. Kiểm tra tác động đến `cause`, suppressed exceptions và các ngoại lệ có stack trace không ghi được.
5. Biết khi nào nên giữ stack trace gốc thay vì cập nhật, đặc biệt khi debug và truyền ngoại lệ qua nhiều tầng ứng dụng.

## 2. Định nghĩa API chính thức

Theo [Java SE 17 API – Throwable.fillInStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#fillInStackTrace()), phương thức có chữ ký:

~~~java
public synchronized Throwable fillInStackTrace()
~~~

Phương thức ghi thông tin về trạng thái stack frame hiện tại của **thread đang gọi** vào chính đối tượng `Throwable`. Giá trị trả về là **cùng tham chiếu `this`**. Nếu writable stack trace của Throwable bị tắt, lời gọi **không có tác dụng** lên dấu vết.

Khi một stack trace đã được ghi lại, các thao tác như `getStackTrace()` và `printStackTrace()` phản ánh thông tin mới theo quy tắc tương ứng.

| API | Chức năng | Có thay thế trace bên trong Throwable? |
| --- | --- | --- |
| `fillInStackTrace()` | Ghi lại dấu vết stack tại thread/vị trí gọi hiện tại | **Có**, nếu trace ghi được |
| `getStackTrace()` | Trả về mảng các `StackTraceElement` biểu diễn trace hiện hành | **Không** |
| `setStackTrace(StackTraceElement[])` | Ghi đè các stack-frame element bằng mảng được chỉ định | **Có**, nếu trace ghi được |
| `printStackTrace()` | In đối tượng exception và dấu vết liên quan tới stream mặc định | **Không** |
| `getCause()` | Xem exception nguyên nhân nếu có | **Không** |
| `getSuppressed()` | Xem các exception bị suppressed, thường do cleanup | **Không** |

Ví dụ:

~~~java
Throwable same = ex.fillInStackTrace();
System.out.println(same == ex); // true
~~~

Đây là **đoạn minh họa**; cần đặt trong một phương thức với biến `ex` thuộc kiểu Throwable đã được tạo.

Lưu ý: từ “ghi lại” mô tả kết quả ở cấp API, không phải cam kết về cách lưu trữ nội bộ như native backtrace, cấu trúc JVM hay vị trí bộ nhớ. JVM được phép không cung cấp đầy đủ mọi frame trong một số tình huống.

## 3. Thời điểm capture mặc định và tác động của rethrow

### 3.1. Thông thường trace hình thành khi tạo exception

Ví dụ:

~~~java
static RuntimeException createFailure() {
    return new IllegalStateException("service unavailable");
}
~~~

Đoạn trên là phương thức minh họa. Constructor `IllegalStateException` gọi cơ chế của lớp cha `Throwable` để điền stack trace. Trong một JVM thông thường, frame đầu được quan sát sẽ gắn với nơi **tạo instance**, ở đây là `createFailure`.

Việc exception **được tạo** và việc nó **được ném** là hai hành động khác nhau:

~~~java
RuntimeException failure = createFailure();
// ... có thể làm thêm công việc ...
throw failure;
~~~

Lệnh `throw failure;` sử dụng instance đã có. Bản thân thao tác này **không bắt buộc làm mới trace**; trên những JVM thông dụng, trace tiếp tục chỉ đến `createFailure`, không đột nhiên đổi sang dòng `throw failure;`.

### 3.2. Chủ động gọi fillInStackTrace trước khi ném lại

~~~java
failure.fillInStackTrace();
throw failure;
~~~

Cấu trúc minh họa này khác ở chỗ `fillInStackTrace()` chủ động ghi stack của thread tại nơi gọi. Nếu trace ghi được, frame phía trên có thể đổi sang phương thức đã thực hiện refresh. Sau đó `throw failure;` ném **cùng instance** với trace đã được cập nhật.

**Cảnh báo thiết kế:** Cập nhật trace có thể khiến thông tin vị trí xuất hiện lỗi **ban đầu** bị thay thế bằng nơi rethrow. Trong luồng debug, nơi phát sinh lỗi gốc thường có giá trị hơn nơi chuyển tiếp lỗi. Vì vậy **không nên tự động gọi `fillInStackTrace()` trước mọi lệnh rethrow**.

Nếu cần bổ sung bối cảnh tầng trên mà vẫn giữ nguyên lỗi gốc, thường phù hợp hơn với **exception chaining**:

~~~java
try {
    serviceCall();
} catch (IOException ex) {
    throw new IllegalStateException("Cannot complete request", ex);
}
~~~

Đây là **mã minh họa**, cần có phương thức `serviceCall()` và import `IOException`. Exception mới có trace tại nơi được tạo, còn `ex` được lưu làm `cause` với trace nguồn gốc riêng. Đây là thay đổi **đối tượng và quan hệ nguyên nhân**, khác hoàn toàn với cập nhật trace của instance cũ.

## 4. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`FillInStackTraceDemo.java`**. Chương trình không dùng thư viện ngoài; mỗi ví dụ in giá trị ngắn có thể kiểm chứng, không in số dòng code hoặc toàn bộ stack trace dễ thay đổi.

~~~java
import java.io.IOException;

public class FillInStackTraceDemo {
    private static RuntimeException createFailure() {
        return new IllegalStateException("service unavailable");
    }

    private static String top(Throwable ex) {
        StackTraceElement[] frames = ex.getStackTrace();
        return frames.length == 0 ? "<empty>" : frames[0].getMethodName();
    }

    private static void throwSame(RuntimeException ex) {
        try {
            throw ex;
        } catch (RuntimeException caught) {
            System.out.println("same object=" + (caught == ex));
            System.out.println("top after throw=" + top(caught));
        }
    }

    private static void refreshHere(Throwable ex) {
        Throwable returned = ex.fillInStackTrace();
        System.out.println("fill returns this=" + (returned == ex));
        System.out.println("top after fill=" + top(ex));
    }

    private static final class NoTraceException extends Exception {
        NoTraceException() {
            super("no frames", null, true, false);
        }
    }

    public static void main(String[] args) {
        System.out.println("== creation and rethrow ==");
        RuntimeException original = createFailure();
        System.out.println("top on create=" + top(original));
        throwSame(original);
        refreshHere(original);
        throwSame(original);

        System.out.println("== manual trace ==");
        original.setStackTrace(new StackTraceElement[] {
                new StackTraceElement("Synthetic", "custom", "Fake.java", 123)
        });
        System.out.println("top after set=" + top(original));
        refreshHere(original);

        System.out.println("== cause and suppressed ==");
        IllegalArgumentException cause = new IllegalArgumentException("root");
        IllegalStateException wrapped = new IllegalStateException("wrapper", cause);
        wrapped.addSuppressed(new IOException("close failed"));
        Throwable result = wrapped.fillInStackTrace();
        System.out.println("same after fill=" + (result == wrapped));
        System.out.println("cause same=" + (wrapped.getCause() == cause));
        System.out.println("suppressed=" + wrapped.getSuppressed().length);
        StackTraceElement[] copy = wrapped.getStackTrace();
        copy[0] = new StackTraceElement("Fake", "change", "X.java", 1);
        System.out.println("defensive copy=" + !top(wrapped).equals("change"));

        System.out.println("== disabled stack ==");
        NoTraceException hidden = new NoTraceException();
        System.out.println("initial size=" + hidden.getStackTrace().length);
        System.out.println("fill returns this=" + (hidden.fillInStackTrace() == hidden));
        hidden.setStackTrace(new StackTraceElement[] {
                new StackTraceElement("Fake", "method", "X.java", 1)
        });
        System.out.println("after fill+set size=" + hidden.getStackTrace().length);
    }
}
~~~

Biên dịch theo mức tương thích **Java 17**, rồi chạy:

~~~bash
javac --release 17 -encoding UTF-8 FillInStackTraceDemo.java
java FillInStackTraceDemo
~~~

**Stdout thực tế, được kiểm chứng trên OpenJDK với đầy đủ frame của các phương thức minh họa:**

~~~text
== creation and rethrow ==
top on create=createFailure
same object=true
top after throw=createFailure
fill returns this=true
top after fill=refreshHere
same object=true
top after throw=refreshHere
== manual trace ==
top after set=custom
fill returns this=true
top after fill=refreshHere
== cause and suppressed ==
same after fill=true
cause same=true
suppressed=1
defensive copy=true
== disabled stack ==
initial size=0
fill returns this=true
after fill+set size=0
~~~

**Tính di động:** Javadoc cho phép một số JVM bỏ qua stack frame trong một số trường hợp, thậm chí trả về mảng rỗng. Vì vậy các dòng có tên phương thức đứng đầu như `createFailure` hoặc `refreshHere` là **kết quả của JVM đã được thử nghiệm**, không phải một cam kết bắt buộc cho mọi JVM, cờ tối ưu và môi trường. Các dòng kiểm tra cùng tham chiếu, cause và suppressed thể hiện hợp đồng API ổn định hơn. Trên JVM có dấu vết đầy đủ, kết quả cho thấy rõ thứ tự refresh.

## 5. Phân tích các phần của chương trình

### 5.1. Tạo ở createFailure rồi ném lại ở throwSame

Trong `main`, một instance `IllegalStateException` được tạo bởi `createFailure()`. Chương trình in:

~~~text
top on create=createFailure
~~~

Khi `throwSame(original)` thực thi, nó ném và bắt lại **chính đối tượng `original`**, kiểm tra `caught == ex` là `true`. Không có một constructor exception mới hoặc lời gọi `fillInStackTrace()`, nên trace vẫn chỉ tới nơi tạo:

~~~text
same object=true
top after throw=createFailure
~~~

**Điểm cần nhớ:** catch/rethrow không làm Java tự dựng lại dấu vết cho instance cũ. Đây là lý do log một exception được ném lại nhiều lần có thể hiển thị cùng vị trí nguồn gốc ban đầu.

### 5.2. refreshHere làm thay đổi frame ở đầu

Hàm:

~~~java
private static void refreshHere(Throwable ex) {
    Throwable returned = ex.fillInStackTrace();
    System.out.println("fill returns this=" + (returned == ex));
    System.out.println("top after fill=" + top(ex));
}
~~~

ghi lại dấu vết ở vị trí gọi. `returned == ex` là `true` vì API trả về chính instance được cập nhật. Trên JVM thử nghiệm, frame đầu đổi từ `createFailure` sang `refreshHere`.

Nếu sau đó cùng instance được ném lại, `throwSame` vẫn thấy frame `refreshHere`, không tự thay đổi thành `throwSame`. Thao tác `throw` không phải lệnh refresh ngầm.

### 5.3. setStackTrace khác fillInStackTrace như thế nào?

Trong phần `manual trace`, đoạn:

~~~java
original.setStackTrace(new StackTraceElement[] {
        new StackTraceElement("Synthetic", "custom", "Fake.java", 123)
});
~~~

**Chủ động gán danh sách frame được cung cấp**, thay vì lấy stack hiện tại của thread. Do đó `top(original)` trả về `custom`. Sau một lời gọi `refreshHere(original)`, API `fillInStackTrace()` ghi lại thông tin stack hiện tại, nên trên JVM thử nghiệm `top` đổi về `refreshHere`.

Phân biệt:

| Thao tác | Nguồn dữ liệu frame | Tác dụng |
| --- | --- | --- |
| `new SomeException(...)` thông thường | Stack hiện tại tại lúc tạo | Thiết lập trace ban đầu |
| `throw existingException;` | Không tự capture thêm | Giữ trace cũ |
| `existingException.fillInStackTrace()` | Stack **hiện tại** của thread gọi | Làm mới dấu vết |
| `existingException.setStackTrace(array)` | Các `StackTraceElement` do code cung cấp | Thay thế biểu diễn dấu vết theo mảng |
| `existingException.getStackTrace()` | Dấu vết đang có bên trong exception | Trả bản sao mảng để đọc |

`setStackTrace()` chủ yếu hữu ích cho framework RPC, hệ thống truyền stack trace qua ranh giới tiến trình hoặc công cụ kỹ thuật chuyên sâu. Việc tự ý gán frame giả vào exception nghiệp vụ có thể **làm sai lệch nơi lỗi thực sự bắt đầu**. Không dùng nó để “sửa” lỗi bằng cách chỉ thay thông tin log.

### 5.4. Cause và suppressed không bị xóa bởi fillInStackTrace

Trong nhánh `cause and suppressed`:

~~~java
IllegalArgumentException cause = new IllegalArgumentException("root");
IllegalStateException wrapped = new IllegalStateException("wrapper", cause);
wrapped.addSuppressed(new IOException("close failed"));
Throwable result = wrapped.fillInStackTrace();
~~~

Ta có các quan hệ độc lập:

- `wrapped.getCause() == cause` vẫn là `true`.
- `wrapped.getSuppressed().length` vẫn là `1`.
- `result == wrapped` vẫn là `true`.

`fillInStackTrace()` làm mới **trace của wrapped**, không tạo một cause khác và không xóa danh sách suppressed. Cause cũng là một đối tượng Throwable riêng có dấu vết của nó; phương thức này không tự động cập nhật trace của cause.

Do đó **stack trace**, **exception chaining (cause)** và **suppressed exceptions** là những phần thông tin khác nhau của một đối tượng Throwable. Debug đáng tin phải biết phần nào được giữ và phần nào bị thay.

### 5.5. Mảng getStackTrace là bản sao phòng vệ

API `getStackTrace()` trả về mảng `StackTraceElement[]` để truy cập bằng chương trình. Việc sửa các phần tử trong mảng đã nhận **không làm thay đổi trace được lưu** bên trong Throwable.

Đoạn thử:

~~~java
StackTraceElement[] copy = wrapped.getStackTrace();
copy[0] = new StackTraceElement("Fake", "change", "X.java", 1);
System.out.println("defensive copy=" + !top(wrapped).equals("change"));
~~~

in `defensive copy=true` trên JVM đã kiểm chứng. Nếu muốn thay đổi stack trace hiển thị, cần gọi **`setStackTrace()`**; chỉ sửa một mảng trả về từ getter là không đủ.

Để mã chạy an toàn trên mọi JVM, trước khi truy cập `copy[0]` hãy kiểm tra độ dài mảng vì đặc tả cho phép dấu vết rỗng trong một số hoàn cảnh. Ví dụ đầy đủ ở trên được kiểm chứng trong môi trường có frame thông thường; đây không phải unit test dùng cho mọi cấu hình JVM. Mã sản xuất nên viết:

~~~java
StackTraceElement[] frames = ex.getStackTrace();
if (frames.length > 0) {
    System.out.println(frames[0].getMethodName());
}
~~~

Đoạn này chỉ minh họa xử lý mảng an toàn; `ex` cần là một Throwable đã tồn tại.

### 5.6. Trường hợp writableStackTrace bị vô hiệu hóa

JDK cung cấp constructor bảo vệ:

~~~java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

Một lớp exception con có thể chọn `writableStackTrace=false`:

~~~java
private static final class NoTraceException extends Exception {
    NoTraceException() {
        super("no frames", null, true, false);
    }
}
~~~

Trong ví dụ này, tham số thứ ba `true` **cho phép suppression**; tham số thứ tư `false` **vô hiệu hóa việc ghi stack trace**. Theo Javadoc, khi writable stack trace bằng false, constructor không gọi `fillInStackTrace()`, lời gọi `fillInStackTrace()` về sau không cập nhật dấu vết và `setStackTrace(...)` cũng không thiết lập frame; `getStackTrace()` trả về mảng dài 0.

Kết quả thử:

~~~text
initial size=0
fill returns this=true
after fill+set size=0
~~~

Ngay cả khi trace không ghi được, `fillInStackTrace()` vẫn trả về **chính đối tượng**. Không nên nhầm trường hợp này với suppression bị tắt: nếu `enableSuppression=false`, `getSuppressed()` rỗng và `addSuppressed` không ghi thêm; đó là cấu hình **độc lập** với writable stack trace.

## 6. Cập nhật dấu vết ảnh hưởng log và điều tra lỗi như thế nào?

Giả sử một lỗi thực sự xảy ra ở tầng đọc file, sau đó được chuyển qua một service và controller. Nếu giữ cùng instance:

~~~java
try {
    readInput();
} catch (IOException ex) {
    log(ex);
    throw ex;
}
~~~

đây là mã minh họa, cần định nghĩa `readInput()`, `log()` và khai báo/handle `IOException` theo hợp đồng. Exception có thể giữ trace tại điểm lỗi gốc. Nếu thêm `ex.fillInStackTrace();` ngay trước khi ném lại, trace thường bị cập nhật về **tầng service** đang rethrow; một số frame ban đầu ở tầng đọc có thể không còn trong trace mới.

Điều này có thể gây hệ quả:

1. **Mất vị trí tạo exception ban đầu trong phần trace chính.** Log về sau dễ hướng người điều tra vào chỗ chuyển tiếp thay vì nơi lỗi phát sinh.
2. **Thay đổi việc nhóm sự cố trong công cụ quan sát.** Một số hệ thống nhóm lỗi theo lớp, message và stack frame; refresh có thể khiến cùng lỗi được phân nhóm khác.
3. **Tạo thông tin dễ gây nhầm khi exception bị chia sẻ.** Nếu một instance được giữ trong cache hoặc chia sẻ giữa nhiều luồng, cập nhật trace sẽ phản ánh **thread gọi fill** gần nhất, không phải tự động giữ nguyên thread phát sinh lỗi ban đầu.
4. **Có chi phí thực thi.** Thu thập stack frame có thể tốn công sức, đặc biệt trong các đường nóng tạo/cập nhật nhiều Throwable. Không gọi đi gọi lại chỉ để thực hiện logging thông thường.
5. **Không khôi phục các side effect hoặc điều kiện chương trình.** Dấu vết là thông tin chẩn đoán; refresh không chạy lại thao tác đã lỗi, không rollback và không thay đổi kết quả logic vốn đã xảy ra.

Với ứng dụng thông thường, cách làm phù hợp hơn là giữ Throwable gốc và **bọc với cause khi cần bổ sung ngữ cảnh**:

~~~java
try {
    readInput();
} catch (IOException ex) {
    throw new IllegalStateException("Input processing failed", ex);
}
~~~

Kết quả là một wrapper mới tại tầng hiện tại **và** một cause giữ nguồn gốc riêng. Trong stack trace được in, thường có phần `Caused by: ...` cho exception gốc. Không cần phá dấu vết cũ bằng cách gọi `fillInStackTrace()`.

### Có bao giờ nên chủ động gọi fillInStackTrace không?

Có, nhưng nên có lý do kỹ thuật rõ. Ví dụ một framework lưu trữ Throwable đại diện cho sự kiện **mới tại thời điểm hiện tại** và có hợp đồng yêu cầu **đổi điểm chẩn đoán** trên cùng instance. Khi đó gọi `fillInStackTrace()` là chủ ý, không phải mặc định.

Nếu muốn giữ lại vị trí gốc trước khi refresh, đừng mặc định có cơ chế history tự động. Có thể lưu snapshot từ `getStackTrace()` hoặc thiết kế wrapper/cause phù hợp. Tuy nhiên, việc lưu snapshot thủ công và thao tác set lại trace cần chính sách minh bạch, vì trace có thể chứa thông tin nhạy cảm về cấu trúc mã và làm khó chẩn đoán nếu bị thay đổi tùy tiện.

## 7. Sự khác nhau giữa stack trace hiện có và stack hiện tại của thread

Hai khái niệm dễ nhầm:

- **Trace của Throwable:** những frame mà exception đang lưu hoặc hiển thị qua `getStackTrace()`; thường bắt đầu ở nơi Throwable được tạo hoặc lần cuối được gọi `fillInStackTrace()`.
- **Stack hiện tại của thread:** các phương thức đang có mặt trên call stack tại thời điểm quan sát. Có thể xem bằng công cụ debug, `Thread.currentThread().getStackTrace()` hoặc API `StackWalker` trong các tình huống thích hợp.

Gọi `ex.fillInStackTrace()` yêu cầu cập nhật **trace của ex** bằng trạng thái stack **của thread đang gọi**. Nó không tự tìm “thread từng ném ex đầu tiên” và cũng không phải thao tác lấy stack của mọi luồng.

Đặc biệt, nếu một instance ngoại lệ được tái sử dụng trong nhiều thread, kết quả sau khi refresh có thể chuyển sang ngữ cảnh khác hẳn nguồn gốc. Tái sử dụng/cập nhật Throwable ở nhiều thread cũng làm thông tin điều tra thiếu ổn định; thông thường nên tạo exception cho từng lần thất bại và giữ trace ban đầu.

## 8. JLS và JVM cho phép dấu vết không hoàn toàn đầy đủ

Dựa trên [API getStackTrace của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getStackTrace()), phần tử tại chỉ số 0 thường là frame ở đầu stack (gần điểm ghi trace nhất). Tuy nhiên, **không được mặc định mảng luôn có phần tử**. Tùy JVM và hoàn cảnh, một số frame có thể bị bỏ qua hoặc mảng có thể rỗng.

Vì vậy khi viết chương trình thực tế:

~~~java
StackTraceElement[] frames = ex.getStackTrace();
if (frames.length == 0) {
    System.out.println("No stack trace available");
} else {
    StackTraceElement first = frames[0];
    System.out.println(first.getClassName());
    System.out.println(first.getMethodName());
}
~~~

Đoạn trên là minh họa, cần có biến `ex` đã khai báo thuộc kiểu Throwable. Tên lớp/phương thức có thể hữu ích khi điều tra, nhưng **file name/line number không phải luôn khả dụng**, nhất là với code không có thông tin debug hoặc được thực thi/tối ưu theo cách khác.

Không nên dùng việc so sánh một chuỗi `StackTraceElement.toString()` chính xác đến dấu cách và số dòng làm tiêu chí nghiệp vụ. Trong bài tập, in tên phương thức giúp nhìn rõ hiệu ứng refresh; trong automated test dùng rộng rãi, hãy kiểm tra định nghĩa API và tránh khẳng định chính xác các frame trên mọi JVM.

## 9. setStackTrace và tính toàn vẹn của dữ liệu chẩn đoán

`setStackTrace(StackTraceElement[])` cho phép gán những frame được cung cấp cho Throwable. Nó không cần gọi stack hiện tại của thread để điền dữ liệu. API cũng **sao chép mảng đầu vào**, nên sửa mảng đầu vào sau khi gọi không tự thay đổi trace đã đặt.

Ví dụ minh họa:

~~~java
StackTraceElement[] frames = {
    new StackTraceElement("RpcService", "call", "RpcService.java", 18)
};
ex.setStackTrace(frames);
frames[0] = new StackTraceElement("Other", "changed", "Other.java", 1);
// Dòng trên không trực tiếp thay trace đã set trong ex.
~~~

Đây là đoạn code minh họa, yêu cầu `ex` là Throwable có writable stack trace. `setStackTrace` phù hợp với một số hệ thống RPC hoặc phục dựng dấu vết từ thông tin truyền qua mạng; thông thường nên tránh dùng để thay thế dấu vết của bug trong ứng dụng.

Khi trace không ghi được (constructor `writableStackTrace=false`), Javadoc nêu `setStackTrace` không có tác dụng **ngoài việc kiểm tra hợp lệ đối số**. Nó không trở thành cách bật lại writable trace. Cần tạo instance mới với cấu hình phù hợp nếu hợp đồng đòi hỏi có dấu vết.

### Có nên override fillInStackTrace để tăng hiệu năng?

Một số exception đặc thù có thể được thiết kế để bỏ thu thập stack trace, nhưng đây là quyết định đánh đổi trực tiếp **khả năng chẩn đoán**. Với các lớp con của Throwable, hãy cân nhắc constructor bảo vệ nhận `writableStackTrace=false` nếu thật sự phù hợp.

Ngoài ra, constructor của Throwable thông thường gọi cơ chế điền stack trace; việc override một phương thức có thể được gọi trong quá trình xây dựng đối tượng cần được thiết kế thận trọng vì trạng thái riêng của subclass có thể chưa khởi tạo đầy đủ. Đừng tự đưa các optimization này vào mọi exception nghiệp vụ nếu chưa đo được chi phí thực tế và chưa chấp nhận việc mất trace.

## 10. Phân biệt các thao tác bằng câu hỏi ngắn

| Tình huống | Cùng một Throwable? | Dấu vết được xử lý như thế nào? |
| --- | --- | --- |
| `throw existing;` | Có | Không tự làm mới trace |
| `existing.fillInStackTrace(); throw existing;` | Có | Refresh trace trước khi throw, nếu ghi được |
| `Throwable other = existing.fillInStackTrace();` | Có, `other == existing` | Cùng instance đã cập nhật |
| `throw new IllegalStateException("context", existing);` | Không, có wrapper mới | Wrapper có trace riêng; existing làm cause |
| `existing.setStackTrace(frames);` | Có | Trace hiển thị được gán bằng các frame cung cấp |
| `existing.getStackTrace();` | Có | Chỉ đọc bản sao mảng, không refresh |
| `existing.printStackTrace();` | Có | In trace hiện có, không refresh |
| Gọi fill khi `writableStackTrace=false` | Có | Không thay đổi trace; thường mảng rỗng |

**Lưu ý riêng:** Nếu biểu thức sau `throw` có giá trị `null`, Java ném một `NullPointerException` do runtime tạo; đó là một tình huống khác với việc gọi `fillInStackTrace()` trên một đối tượng Throwable khác null.

## 11. Các lỗi hiểu sai thường gặp

1. **“Mỗi lần throw là Java ghi lại stack trace.”** Sai: ném lại cùng instance không tự refresh trace.
2. **“fillInStackTrace tạo một exception mới.”** Sai: API trả về chính đối tượng đang gọi.
3. **“fillInStackTrace tự động ném exception.”** Sai: chỉ cập nhật thông tin; muốn truyền lỗi vẫn cần `throw` hoặc cơ chế tương ứng.
4. **“Cập nhật trace cũng cập nhật cause và suppressed.”** Sai: các quan hệ này độc lập.
5. **“getStackTrace trả về mảng có thể sửa để đổi trace nội bộ.”** Sai: mảng getter được sao chép bảo vệ.
6. **“setStackTrace và fillInStackTrace giống nhau.”** Sai: một phương thức dùng frame do code cung cấp; phương thức kia lấy trạng thái stack hiện tại của thread.
7. **“Refresh giúp giữ được dấu vết nguyên gốc.”** Thường là ngược lại: trace cũ có thể bị thay thế.
8. **“Stack trace luôn có đầy đủ mọi frame và số dòng.”** Sai: API cho phép JVM bỏ qua frame hoặc trả mảng rỗng.
9. **“Không có trace là exception chưa thực sự tồn tại.”** Sai: Throwable có thể được tạo với stack trace không ghi được.
10. **“writableStackTrace=false cũng tự tắt suppression.”** Sai: hai cờ độc lập.
11. **“fillInStackTrace được gọi trên thread nào cũng luôn ra stack của thread gây lỗi ban đầu.”** Sai: nó dùng thread **đang thực thi lời gọi refresh**.
12. **“Cứ refresh ở tầng controller để có log đẹp hơn.”** Có thể làm mất frame gốc; cân nhắc exception chaining.
13. **“Cập nhật trace sẽ retry hoặc rollback thao tác lỗi.”** Sai: chỉ thông tin chẩn đoán thay đổi.
14. **“Có thể tin tuyệt đối frame giả do setStackTrace.”** Không: một thư viện/framework có thể chủ động chỉnh nội dung trace, phải đánh giá tính tin cậy của nguồn.

## 12. Bài tập tự kiểm tra

**Câu 1.** Exception tạo ở `createFailure()`, sau đó ném lại ở `controller()` mà không gọi fill: trace phải tự chuyển sang controller không?

*Đáp án:* Không. `throw existing;` không tự làm mới stack trace.

**Câu 2.** `Throwable ref = ex.fillInStackTrace();` có tạo object mới không?

*Đáp án:* Không. `ref == ex` là `true`.

**Câu 3.** Nếu `refreshHere(ex)` gọi fill, khi ném ex ở nơi khác lần nữa, trace sẽ phản ánh bước refresh hay throw lần hai?

*Đáp án:* Thông thường phản ánh vị trí refresh gần nhất, trừ các trường hợp stack trace bị vô hiệu hóa hoặc JVM lược bớt frame.

**Câu 4.** Nếu ex có cause và một suppressed exception, gọi fill có xóa chúng không?

*Đáp án:* Không. Cause và suppressed tồn tại độc lập với thao tác cập nhật stack trace.

**Câu 5.** Nếu sửa `StackTraceElement[] a = ex.getStackTrace(); a[0] = ...;`, trace của ex có tự đổi không?

*Đáp án:* Không. Mảng do getter trả về là bản sao; cần sử dụng API setter thích hợp nếu chủ động thay trace.

**Câu 6.** Vì sao `getStackTrace()[0]` cần được kiểm tra độ dài?

*Đáp án:* Javadoc cho phép một số Throwable/JVM có mảng trace rỗng; truy cập phần tử 0 khi đó ném `ArrayIndexOutOfBoundsException`.

**Câu 7.** Một subclass gọi constructor `super(message, cause, true, false)`; gọi fill nhiều lần có làm mảng trace có frame?

*Đáp án:* Không. Cờ writable stack trace false khiến fill và set không cập nhật trace; getter trả về mảng rỗng.

**Câu 8.** Khi service cần bổ sung bối cảnh nhưng vẫn giữ nguồn lỗi gốc, nên cân nhắc giải pháp nào?

*Đáp án:* Tạo wrapper exception mới với thông điệp và cause là exception ban đầu; không mặc định refresh trace cũ.

## 13. Tài liệu chính thức

- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): các constructor và thuộc tính cause/suppression/writable stack trace.
- [Java SE 17 API – fillInStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#fillInStackTrace()): ghi thông tin stack hiện tại của thread và trả về cùng instance.
- [Java SE 17 API – getStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getStackTrace()): thứ tự các frame và quyền JVM lược bớt trace.
- [Java SE 17 API – setStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#setStackTrace(java.lang.StackTraceElement%5B%5D)): gán mảng stack frames theo API.
- [Java SE 17 API – StackTraceElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): cấu trúc từng frame và getter cho tên lớp/phương thức, file, số dòng.
- [Java SE 17 API – Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): đọc danh sách exception thứ cấp.
- [Java SE 17 JLS mục 14.18 – throw statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): cách ném object Throwable; rethrow không đồng nghĩa refresh.

**Ghi nhớ:** `fillInStackTrace()` **cập nhật dấu vết tại thời điểm gọi trên chính Throwable hiện có**, không tạo Throwable mới và không tự ném lỗi. Sau refresh, nơi bắt đầu trace có thể chuyển từ vị trí gây lỗi gốc sang nơi cập nhật, ảnh hưởng mạnh đến debug. Chỉ dùng khi thật sự muốn thay dấu vết; thông thường nên giữ trace nguyên bản và dùng exception chaining để thêm ngữ cảnh.