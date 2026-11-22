# `setStackTrace()` và giới hạn khi tự thay đổi thông tin chẩn đoán trong Java

Một đối tượng `Throwable` không chỉ lưu kiểu và thông điệp lỗi mà còn có thể mang **stack trace** — danh sách những khung gọi phương thức (*stack frames*) giúp lập trình viên hình dung nơi thông tin chẩn đoán được ghi nhận. Java cung cấp `Throwable.getStackTrace()` để đọc và `Throwable.setStackTrace(StackTraceElement[])` để **thay thế danh sách frame được hiển thị** cho một đối tượng ngoại lệ cụ thể.

Khả năng thay thế này hữu ích trong vài tình huống hạ tầng đặc biệt, chẳng hạn công cụ RPC cần dựng lại dấu vết nhận từ máy khác. Nhưng nó cũng có một giới hạn lớn: **stack trace có thể bị sửa không còn phản ánh trung thực đường thực thi**. `setStackTrace()` không sửa stack đang chạy của JVM, không chuyển ngoại lệ về quá khứ, không thay đổi nguyên nhân gây lỗi, và không chứng minh rằng những phương thức được liệt kê đã thực sự được gọi.

Bài này giải thích chính xác hợp đồng API, dữ liệu `StackTraceElement`, bản sao phòng vệ (*defensive copy*), tính khả ghi của stack trace, mối liên hệ với `fillInStackTrace()`, `cause`, `suppressed exceptions`, cùng cách dùng an toàn khi logging và truyền lỗi qua ranh giới hệ thống. Các chương trình độc lập sử dụng **Java 17+**.

## 1. Stack trace trên `Throwable` là gì?

Khi tạo một đối tượng ngoại lệ theo constructor thông thường, Java thường ghi lại thông tin khung gọi hiện tại bằng `fillInStackTrace()`. Mảng được trả về từ `getStackTrace()` thường chứa các frame theo thứ tự:

- **Phần tử đầu** (chỉ số 0): điểm gần nhất với lúc thông tin trace được ghi nhận; thường là nơi tạo đối tượng ngoại lệ.
- **Các phần tử tiếp theo**: những lời gọi ở tầng ngoài.
- **Phần tử cuối**: frame gần đáy chuỗi gọi được ghi nhận.

Ví dụ minh họa sơ đồ:

```text
main()
  └── service()
        └── repository()
              └── new IOException("read failed")

getStackTrace() thông thường:
[0] repository(...)
[1] service(...)
[2] main(...)
```

Đây là **sơ đồ ý niệm**, không phải cam kết về toàn bộ frame và số dòng xuất hiện ở mọi JVM. Đặc tả JDK cho phép VM bỏ qua một hoặc nhiều frame, thậm chí trả mảng rỗng trong những hoàn cảnh đặc biệt. Tối ưu hóa, thông tin debug và cách JVM ghi nhận stack có thể làm đầu ra khác nhau.

Một frame là đối tượng `StackTraceElement`. Nó thường chứa tên lớp, tên phương thức, tên tệp nguồn và số dòng. Tùy JDK, frame còn có thể chứa tên class loader, tên module và phiên bản module.

**Stack trace trên ngoại lệ không phải là live call stack.** Khi phương thức đã hoàn tất hoặc thread đã chuyển sang thực thi nơi khác, đối tượng ngoại lệ vẫn có thể giữ trace cũ. Việc đọc hay ghi thông tin này không làm thay đổi các frame thật đang thực thi.

## 2. Hợp đồng của `setStackTrace()`

Chữ ký phương thức:

```java
public void setStackTrace(StackTraceElement[] stackTrace)
```

Theo Javadoc của Java SE 17, phương thức này:

1. **Gán danh sách frame được trả về bởi `getStackTrace()`** và được thể hiện bởi `printStackTrace()` cùng các phương thức liên quan.
2. **Chấp nhận một mảng `StackTraceElement[]`**, gồm cả mảng rỗng. Mảng rỗng thể hiện không có frame trong trace được công bố.
3. **Sao chép mảng đầu vào** thay vì lưu trực tiếp tham chiếu mảng do bên gọi truyền vào. Sửa mảng đầu vào sau khi phương thức trả về không làm đổi trace đã được lưu.
4. **Kiểm tra `null`**: nếu chính mảng là `null` hoặc một phần tử trong mảng là `null`, nó ném `NullPointerException`.
5. **Không cập nhật trace nếu đối tượng có stack trace không khả ghi**, dù tham số vẫn được kiểm tra hợp lệ.

Javadoc nói phương thức này được thiết kế cho framework RPC và các hệ thống nâng cao cần thay thế trace mặc định, chẳng hạn dấu vết được chuyển qua cơ chế tuần tự hóa. Nó **không phải thao tác chuẩn nên gọi trên mọi ngoại lệ nghiệp vụ**.

### Điều gì thực sự được sửa?

| Thành phần | `setStackTrace()` có thay đổi không? |
| --- | --- |
| Mảng frame do `Throwable.getStackTrace()` cung cấp cho đối tượng này | **Có**, nếu trace khả ghi và mảng hợp lệ |
| Phần frame chính của `printStackTrace()` cho đối tượng này | **Có**, hiển thị theo trace đã đặt |
| Loại lớp ngoại lệ, ví dụ `IOException` hay `IllegalStateException` | **Không** |
| `getMessage()`, mã lỗi nghiệp vụ riêng | **Không** |
| `getCause()` và nguyên nhân lỗi gốc | **Không** |
| Danh sách `getSuppressed()` | **Không** |
| Stack frame thực tế đang hoạt động của JVM/thread | **Không** |
| Những dòng mã đã thật sự chạy trước khi ngoại lệ xuất hiện | **Không** |
| Khả năng `catch` chọn kiểu ngoại lệ tương thích | **Không** |

Hệ quả quan trọng: không có gì ngăn bạn tạo `StackTraceElement` mang tên một lớp hoặc phương thức **không hề được thực thi** rồi gán vào trace. Khi đó log có thể chứa thông tin trông giống thật nhưng do ứng dụng tự cung cấp.

## 3. Chương trình Java 17+: thay thế trace bằng frame tự tạo

Lưu thành `SetStackTraceDemo.java`:

```java
public class SetStackTraceDemo {
    public static void main(String[] args) {
        IllegalStateException failure =
                new IllegalStateException("request failed");

        StackTraceElement remote = new StackTraceElement(
                "remote.Worker", "run", "Worker.java", 120);

        StackTraceElement[] replacement = {remote};
        failure.setStackTrace(replacement);

        System.out.println("frame=" + failure.getStackTrace()[0]);
        System.out.println("message=" + failure.getMessage());

        replacement[0] = new StackTraceElement(
                "changed.Place", "other", "Other.java", 1);
        System.out.println("after source-array change="
                + failure.getStackTrace()[0].getClassName());

        StackTraceElement[] snapshot = failure.getStackTrace();
        snapshot[0] = new StackTraceElement(
                "another.Place", "fake", "Fake.java", 2);
        System.out.println("after returned-array change="
                + failure.getStackTrace()[0].getClassName());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SetStackTraceDemo.java
java SetStackTraceDemo
```

Kết quả xác định khi dùng JDK 17+ với tên lớp đơn giản trong demo:

```text
frame=remote.Worker.run(Worker.java:120)
message=request failed
after source-array change=remote.Worker
after returned-array change=remote.Worker
```

Giải thích:

- `remote` là một frame **tổng hợp**, được tạo bằng constructor `StackTraceElement`. Không có lời gọi thật nào tới `remote.Worker.run` trong chương trình này.
- `setStackTrace(replacement)` thay thế trace mặc định của `failure` bằng mảng một phần tử. `getStackTrace()[0]` và phần frame của `printStackTrace()` sẽ sử dụng giá trị tổng hợp ấy.
- Thay `replacement[0]` sau khi gọi `setStackTrace` không làm đổi trace đã lưu, vì phương thức đã sao chép mảng đầu vào.
- Tương tự, thay một phần tử của **mảng được `getStackTrace()` trả về** không cập nhật trace bên trong `Throwable`.
- `getMessage()` vẫn trả `request failed`: can thiệp frame không sửa nội dung message.

**Đừng đưa frame giả vào log sản xuất như thể đó là bằng chứng về đường gọi thật.** Ví dụ có mục tiêu kiểm chứng hợp đồng API; tên `remote.Worker` chỉ là nhãn minh họa.

## 4. `StackTraceElement` chứa những trường nào?

Constructor cơ bản:

```java
new StackTraceElement(
        String declaringClass,
        String methodName,
        String fileName,
        int lineNumber)
```

Các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `declaringClass` | Tên lớp được ghi trong frame; không được `null` |
| `methodName` | Tên phương thức; không được `null` |
| `fileName` | Tên tệp nguồn; **có thể `null`** khi không có thông tin |
| `lineNumber` | Số dòng; giá trị âm biểu thị thiếu hoặc dạng thông tin đặc biệt |
| `-2` ở `lineNumber` | Quy ước thể hiện phương thức native khi dùng constructor này |

Từ Java 9 còn có constructor bảy tham số, bổ sung `classLoaderName`, `moduleName` và `moduleVersion` trước bốn tham số kể trên. Những trường mở rộng thường không cần thiết cho việc học `setStackTrace` cơ bản.

Các phương thức đọc thông tin hữu ích gồm:

- `getClassName()`, `getMethodName()`;
- `getFileName()`, `getLineNumber()`;
- `isNativeMethod()`;
- `getModuleName()`, `getModuleVersion()`, `getClassLoaderName()` (nếu có thông tin).

Một frame do chương trình tự dựng **không được JVM kiểm chứng rằng tên lớp, tên phương thức, tệp và số dòng ấy thật sự có liên hệ với nhau**. Điều này làm `StackTraceElement` hữu ích để biểu diễn dấu vết từ xa nhưng cũng khiến trace bị sửa có thể đánh lừa người đọc.

### Ví dụ minh họa cấu trúc frame

```java
StackTraceElement element = new StackTraceElement(
        "example.Service", "execute", "Service.java", 25);

System.out.println(element.getClassName());   // example.Service
System.out.println(element.getMethodName());  // execute
System.out.println(element.getFileName());    // Service.java
System.out.println(element.getLineNumber());  // 25
```

Đoạn trên là **mã đặt trong một phương thức**, không phải tệp chương trình độc lập. Nó minh họa cách đọc dữ liệu đã cung cấp, **không có nghĩa mã nguồn thực tế chứa `Service.java` ở dòng 25**.

## 5. Bản sao phòng vệ: vì sao sửa mảng chưa đủ?

Hai API đều tách mảng mà bên gọi thao tác ra khỏi trạng thái nội bộ:

```text
Mảng đầu vào do ứng dụng tạo
    |
    | setStackTrace(input)     [sao chép]
    v
Dữ liệu stack trace gắn với Throwable
    |
    | getStackTrace()         [trả mảng độc lập]
    v
Mảng mà bên gọi có thể sửa
```

Vì thế mã kiểu sau **không thay đổi trace đang lưu**:

```java
StackTraceElement[] frames = failure.getStackTrace();
frames[0] = new StackTraceElement("x.Y", "z", "Y.java", 10);
```

Đây là đoạn minh họa khi `failure` là một `Throwable` có trace không rỗng; nhớ kiểm tra `frames.length > 0` trước khi truy cập chỉ số 0 trong mã tổng quát.

Nếu cần thay đổi có chủ đích, phải tạo mảng đã sửa và gọi lại:

```java
StackTraceElement[] frames = failure.getStackTrace();
if (frames.length > 0) {
    frames[0] = new StackTraceElement(
            "example.NewOrigin", "process", "NewOrigin.java", 15);
    failure.setStackTrace(frames);
}
```

Đoạn này là **mẫu minh họa cơ chế**, không phải khuyến nghị thay frame thật bằng tên giả trong hệ thống. Phần tử `StackTraceElement` là đối tượng biểu diễn dữ liệu; người dùng không có API setter thay className/fileName trực tiếp trên phần tử đó.

**Giới hạn đồng thời:** bản sao phòng vệ của mảng chỉ ngăn sửa gián tiếp qua cùng tham chiếu mảng. Nó không tự biến việc nhiều thread cùng lúc gọi `setStackTrace()`, `fillInStackTrace()` và ghi log cùng một `Throwable` thành một quy trình chẩn đoán nhất quán theo thời gian. Tránh thay trace khi ngoại lệ đang được chia sẻ và ghi nhận ở các thread khác.

## 6. Trường hợp đầu vào không hợp lệ: mảng `null` và phần tử `null`

Hai lỗi sau làm `setStackTrace()` ném `NullPointerException`:

```java
Throwable ex = new Exception("example");

ex.setStackTrace(null); // Không hợp lệ: mảng null.

ex.setStackTrace(new StackTraceElement[] {
        null
}); // Không hợp lệ: phần tử null.
```

Đây là **đoạn cố ý gây lỗi khi chạy**; lệnh thứ hai sẽ không được thực thi nếu ngoại lệ từ lệnh thứ nhất không được bắt trước. Vì mục đích là minh họa xác thực tham số, đừng dùng nó làm mẫu xử lý lỗi sản xuất.

Mảng rỗng lại **hợp lệ**:

```java
Throwable ex = new Exception("example");
ex.setStackTrace(new StackTraceElement[0]);
System.out.println(ex.getStackTrace().length); // 0
```

Mảng rỗng loại bỏ thông tin frame được công bố của ngoại lệ nếu stack trace của đối tượng khả ghi. Nó **không biến đối tượng ngoại lệ thành không tồn tại**, không đổi loại, message, cause hay danh sách suppressed.

Một điều đặc biệt: với đối tượng có stack trace **không khả ghi**, `setStackTrace()` **vẫn kiểm tra tham số**; mảng chứa `null` vẫn không hợp lệ dù không có thay đổi nào được lưu.

## 7. `writableStackTrace=false`: khi `setStackTrace()` không có tác dụng

Lớp `Throwable` có constructor bảo vệ (*protected*):

```java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
```

Các lớp ngoại lệ con có thể gọi constructor này để cấu hình việc hỗ trợ suppressed exceptions và khả năng cập nhật stack trace. Khi `writableStackTrace=false`:

- Constructor không tạo stack trace mặc định bằng `fillInStackTrace()`;
- `getStackTrace()` trả mảng rỗng;
- `setStackTrace(...)` không cập nhật trace, dù vẫn xác thực tham số;
- `fillInStackTrace()` cũng không cập nhật trace.

Đây là thiết kế đặc biệt, ví dụ khi một hệ thống cần dùng lại một đối tượng lỗi bất biến theo một chính sách rất cụ thể. Không nên mặc định tắt trace để “tối ưu” mọi lỗi nghiệp vụ, vì điều đó làm khó quan sát nguyên nhân sự cố.

### Chương trình Java 17+: một ngoại lệ có trace không khả ghi

Lưu thành `NonWritableTraceDemo.java`:

```java
public class NonWritableTraceDemo {
    static final class NoTraceException extends Exception {
        NoTraceException(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        NoTraceException failure = new NoTraceException("short error");

        System.out.println("initial=" + failure.getStackTrace().length);

        StackTraceElement[] synthetic = {
            new StackTraceElement("remote.Worker",
                                  "run", "Worker.java", 42)
        };
        failure.setStackTrace(synthetic);
        System.out.println("after set=" + failure.getStackTrace().length);

        failure.fillInStackTrace();
        System.out.println("after fill=" + failure.getStackTrace().length);

        try {
            failure.setStackTrace(new StackTraceElement[]{null});
        } catch (NullPointerException ex) {
            System.out.println("invalid input rejected");
        }

        System.out.println("message=" + failure.getMessage());
    }
}
```

```bash
javac -encoding UTF-8 NonWritableTraceDemo.java
java NonWritableTraceDemo
```

Kết quả:

```text
initial=0
after set=0
after fill=0
invalid input rejected
message=short error
```

Phân tích:

1. `NoTraceException` gọi `Exception` constructor tương ứng của `Throwable` với `enableSuppression=true` và `writableStackTrace=false`.
2. Đọc trace ban đầu được mảng rỗng.
3. Truyền mảng hợp lệ vào `setStackTrace` không thêm frame.
4. Gọi `fillInStackTrace` cũng không thêm frame.
5. Mảng chứa phần tử `null` vẫn làm `setStackTrace` ném `NullPointerException`.
6. Message vẫn tồn tại bình thường và có thể được lấy bằng `getMessage()`.

Không nên nhầm `writableStackTrace=false` với việc đặt `setStackTrace(new StackTraceElement[0])`: thao tác sau là **thay nội dung trace hiện tại** của một ngoại lệ khả ghi; một lần gọi `fillInStackTrace()` tương lai có thể ghi lại trace mới.

## 8. `fillInStackTrace()` khác `setStackTrace()` như thế nào?

Hai phương thức có mục tiêu khác nhau:

| Phương thức | Hành động chính | Loại dữ liệu |
| --- | --- | --- |
| `getStackTrace()` | Lấy dữ liệu frame mà `Throwable` đang công bố | Mảng `StackTraceElement[]` |
| `setStackTrace(frames)` | Thay thế bằng mảng frame do ứng dụng cung cấp | **Có thể hoàn toàn tổng hợp** |
| `fillInStackTrace()` | Ghi nhận lại thông tin stack của **thread hiện tại** tại thời điểm gọi | Dữ liệu chẩn đoán do JVM thu thập |
| `printStackTrace()` | In mô tả lỗi, trace, và khi có thì cause/suppressed | Văn bản chẩn đoán ra stream |

Theo Javadoc, khi tạo đối tượng `Throwable` bằng constructor thông thường, `fillInStackTrace()` được dùng để khởi tạo thông tin trace. Việc **ném lại cùng một đối tượng** bằng `throw ex;` thường không tự động ghi mới trace. Nếu tự gọi `fillInStackTrace()`, bạn đang yêu cầu ghi lại một thời điểm khác và có nguy cơ **làm mất vị trí chẩn đoán trước đó**.

### Chương trình Java 17+: ghi lại trace sau khi đã thay

Lưu thành `RefreshTraceDemo.java`:

```java
public class RefreshTraceDemo {
    static void refresh(Throwable failure) {
        failure.fillInStackTrace();
    }

    public static void main(String[] args) {
        IllegalStateException failure =
                new IllegalStateException("example");

        StackTraceElement remote = new StackTraceElement(
                "remote.Worker", "run", "Worker.java", 77);

        failure.setStackTrace(new StackTraceElement[]{remote});
        System.out.println("before="
                + failure.getStackTrace()[0].getClassName());

        refresh(failure);

        StackTraceElement[] captured = failure.getStackTrace();
        boolean noLongerSynthetic =
                captured.length == 0 || !captured[0].equals(remote);
        System.out.println("replaced=" + noLongerSynthetic);
        System.out.println("message=" + failure.getMessage());
    }
}
```

```bash
javac -encoding UTF-8 RefreshTraceDemo.java
java RefreshTraceDemo
```

Kết quả trên Java 17+:

```text
before=remote.Worker
replaced=true
message=example
```

Sau `refresh(failure)`, `fillInStackTrace()` đã làm mới trace từ thread hiện tại, nên frame tổng hợp trước đó không còn là trace hiện hành. Mã **không in ra tên frame JVM cụ thể**, vì Javadoc cho phép các VM khác nhau ghi nhận/loại bỏ một số frame. Phép kiểm tra cho phép mảng rỗng hoặc frame đầu khác frame giả đã đặt, nên giữ ý nghĩa chẩn đoán mà không phụ thuộc số dòng.

**Đừng dùng `fillInStackTrace()` chỉ để làm log “đẹp hơn”**: hành động này có thể đẩy nơi trace bắt đầu sang một tầng xử lý lỗi trung gian thay vì nơi lỗi gốc được tạo. Nếu cần thêm ngữ cảnh, thường nên bọc ngoại lệ mới với `cause` hơn là ghi đè trace cũ.

## 9. Việc sửa trace không sửa `cause` hoặc `suppressed exceptions`

Một ngoại lệ có thể được bọc bởi ngoại lệ tầng cao hơn:

```text
ServiceException("cannot process")
    ├── cause -> IOException("read failed")
    │              └── original stack trace
    └── suppressed -> CleanupException("close failed")
                       └── own stack trace
```

Mỗi đối tượng `Throwable` trong sơ đồ có **trace riêng**. Gọi `setStackTrace()` trên `ServiceException` không tự thay trace của `IOException` làm cause hay của `CleanupException` bị suppress. Gọi trên đối tượng cause cũng không tự thay thuộc tính trace của wrapper.

Lưu thành `TraceGraphDemo.java`:

```java
public class TraceGraphDemo {
    public static void main(String[] args) {
        IllegalStateException cause =
                new IllegalStateException("original");

        Exception wrapper = new Exception("service error", cause);
        wrapper.addSuppressed(
                new IllegalArgumentException("cleanup error"));

        wrapper.setStackTrace(new StackTraceElement[0]);

        System.out.println("wrapperFrames="
                + wrapper.getStackTrace().length);
        System.out.println("message=" + wrapper.getMessage());
        System.out.println("causeMessage="
                + wrapper.getCause().getMessage());
        System.out.println("suppressedCount="
                + wrapper.getSuppressed().length);
        System.out.println("suppressedMessage="
                + wrapper.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac -encoding UTF-8 TraceGraphDemo.java
java TraceGraphDemo
```

Kết quả:

```text
wrapperFrames=0
message=service error
causeMessage=original
suppressedCount=1
suppressedMessage=cleanup error
```

Mặc dù trace của `wrapper` đã được đặt rỗng, thông điệp lỗi, cause và suppressed vẫn được giữ. Việc in `wrapper.printStackTrace()` còn có thể hiển thị những thông tin được giữ trên cause và suppressed vì hai đối tượng ấy quản lý trace riêng.

**Lưu ý:** nội dung được hiển thị bởi `printStackTrace()` không đồng nghĩa chỉ gồm mảng của ngoại lệ ngoài cùng. Đầu ra còn phản ánh cấu trúc liên kết nguyên nhân và lỗi bị suppress. Cắt mảng trên wrapper không làm mất toàn bộ bằng chứng ở các đối tượng khác, nhưng vẫn có thể gây nhầm lẫn về ngữ cảnh nơi wrapper được tạo.

## 10. `printStackTrace()`, logging và sự sai lệch của trace tự đặt

Khi gọi:

```java
failure.printStackTrace();
```

phiên bản không tham số ghi chẩn đoán vào `System.err`, bao gồm thông tin về đối tượng throwable và các frame có thể hiển thị. Còn các overload `printStackTrace(PrintStream)` và `printStackTrace(PrintWriter)` cho phép chọn đích ghi. Hệ thống logging thông thường cũng có thể sử dụng thông tin từ chính `Throwable` để biểu diễn nguyên nhân và stack trace.

**Một frame tổng hợp có thể được in như một frame thật.** Vì vậy:

- Lỗi đọc log sẽ khó hơn nếu một tầng xóa các frame mà không ghi rõ việc đã lọc.
- Nhóm vận hành có thể truy nhầm tệp, nhầm số dòng hoặc nhầm dịch vụ nếu không biết trace đã được tái dựng.
- Công cụ phân nhóm lỗi dựa vào “top frame” có thể phân nhóm sai sau khi trace bị sửa.
- Dấu vết bị viết lại có thể làm mất thông tin xác định tầng đã phát sinh hoặc đã chuyển đổi ngoại lệ.
- Nếu nội dung ngoại lệ đến từ nguồn ngoài đáng tin cậy thấp, không được coi tên lớp/method/file do bên ngoài khai báo là một sự thật đã được JVM xác thực.

Do đó, **đừng tự ý dùng `setStackTrace()` để che giấu nơi lỗi thực tế xảy ra**. Những nhu cầu hợp lệ như giảm thông tin nhạy cảm, giới hạn khối lượng log hoặc tái dựng dấu vết phân tán nên thực hiện theo thiết kế chẩn đoán rõ ràng: có thông tin gốc, đánh dấu frame từ xa/tổng hợp, kiểm soát quyền truy cập log và giữ ngữ cảnh liên quan.

Trong kiểm thử, tránh so sánh nguyên văn toàn bộ `printStackTrace()` vì tên file, số dòng, số frame, mô tả module hoặc cách trình bày có thể thay đổi theo JDK/JVM. Với những khẳng định cốt lõi, so sánh các trường dữ liệu cần thiết hoặc các frame tổng hợp mà bài test tự tạo.

## 11. Khi nào thay trace có thể hợp lý?

Javadoc nhắc tới **framework RPC** và các hệ thống nâng cao. Chẳng hạn một dịch vụ nhận một lỗi đã được tuần tự hóa từ máy từ xa. Dấu vết gốc có thể biểu diễn điểm xử lý của remote service, nhưng máy nhận không có các frame đó trong stack hiện tại.

Một thiết kế có thể:

1. Nhận dữ liệu lỗi có cấu trúc từ phía remote.
2. Xác định dữ liệu đó là **dấu vết từ xa**, không phải những lời gọi JVM ở máy nhận.
3. Lưu hoặc trình bày riêng remote stack; nếu thật sự cần tương thích một API dựa trên `Throwable`, có thể dựng các `StackTraceElement` có nguồn gốc được ghi chú rõ.
4. Giữ cả thông tin lỗi gốc lẫn điểm tiếp nhận ở máy cục bộ qua metadata, sự kiện tracing hoặc cause chain.
5. Hạn chế giả mạo/làm nhiễm log: kiểm tra dữ liệu nhận, giới hạn độ dài, làm sạch chuỗi có ký tự điều khiển nếu dữ liệu sẽ vào log, không coi remote frames là chứng cứ tin cậy tự thân.

**Nên ưu tiên các trường chẩn đoán có cấu trúc** (service, trace ID, span ID, remote error type, timestamps, environment) khi cần mô tả cả hành trình phân tán. `StackTraceElement[]` không tự cung cấp đầy đủ thông tin về các ranh giới mạng, thời gian hoặc mối liên hệ giữa các trace.

Nếu không có yêu cầu tương thích buộc phải thay trace, phương án đơn giản hơn thường là **giữ nguyên `Throwable` và gắn ngữ cảnh trong exception wrapper**:

```java
try {
    callRemote();
} catch (RemoteCallException ex) {
    throw new ServiceException(
            "Remote operation failed; service=inventory", ex);
}
```

Đây là **mẫu minh họa**, giả định `RemoteCallException`, `ServiceException` và `callRemote()` đã được khai báo phù hợp. Phần `cause` giúp giữ đường đi chẩn đoán của ngoại lệ gốc; message thêm ngữ cảnh ở tầng dịch vụ. Không cần ghi đè trace của đối tượng gốc.

## 12. Khác biệt giữa “trace tổng hợp” và “trace bị cắt ngắn”

Có ba thao tác dễ bị đánh đồng:

| Thao tác | Hậu quả |
| --- | --- |
| `setStackTrace(new StackTraceElement[0])` | Trace đang công bố của đối tượng trở thành mảng rỗng (nếu khả ghi) |
| `setStackTrace(Arrays.copyOf(frames, n))` | Giữ một số frame, bỏ các frame còn lại khỏi thông tin công bố |
| `setStackTrace(syntheticFrames)` | Thay bằng dữ liệu có thể do bên gọi tự tạo, không phản ánh lịch sử gọi thật |

Chọn số frame hữu hạn để giảm độ dài log có thể là yêu cầu hợp lệ, nhưng sửa trực tiếp trace của ngoại lệ **thay đổi chính đối tượng** đang được những thành phần khác dùng. Nếu một hệ thống chỉ muốn hiển thị tối đa vài frame, thường an toàn hơn khi **giới hạn cách định dạng log** mà không đụng vào trạng thái `Throwable` ban đầu.

Đặc biệt với chương trình đa luồng, cùng một ngoại lệ có thể được truyền qua các tầng, lưu trong `Future` hoặc được nhiều thành phần tham khảo. Việc thay trace làm thay đổi dữ liệu chẩn đoán mà những người sử dụng sau đó nhìn thấy; không nên coi đây là phép toán thuần không có tác dụng phụ.

## 13. Các lỗi hiểu sai thường gặp

| Hiểu sai | Thực tế |
| --- | --- |
| “`setStackTrace()` thay đổi stack thực của thread.” | Không. Nó chỉ thay thông tin trace của một đối tượng `Throwable`. |
| “Ghi frame giả chứng minh phương thức đó đã chạy.” | Không. Bên gọi tự tạo được `StackTraceElement` với tên tùy chọn. |
| “Thay `getStackTrace()[0]` là sửa trực tiếp ngoại lệ.” | Không. `getStackTrace()` trả mảng không chia sẻ trạng thái nội bộ theo cách đó. |
| “Chỉnh mảng đầu vào sau `setStackTrace()` làm trace cũng đổi.” | Không. `setStackTrace()` sao chép mảng đã nhận. |
| “Mảng `null` hoặc phần tử `null` nghĩa là frame không rõ.” | Không. Đây là đầu vào không hợp lệ và gây `NullPointerException`. Dùng mảng rỗng nếu muốn biểu diễn không có frame. |
| “Nếu `writableStackTrace=false`, `setStackTrace()` sẽ ghi lại frame.” | Không. Nó chỉ xác thực tham số, không thay trace. |
| “`setStackTrace()` đồng thời thay đổi `getMessage()`, `cause` và suppressed.” | Không. Những dữ liệu đó có cơ chế riêng. |
| “Ném lại cùng một đối tượng tự động ghi stack mới tại `throw ex;`.” | Không nên giả định như vậy; trace thường gắn với lần tạo hoặc lần gọi `fillInStackTrace()`. |
| “`fillInStackTrace()` tương đương `setStackTrace()`.” | Không. `fillInStackTrace()` yêu cầu JVM ghi nhận stack hiện tại; `setStackTrace()` nhận mảng do ứng dụng cung cấp. |
| “Mọi JVM đều trả đầy đủ mọi frame, luôn có frame đầu.” | Không. Javadoc cho phép lược bỏ frame, thậm chí trả mảng rỗng trong một số trường hợp. |
| “Gọi `setStackTrace(new StackTraceElement[0])` là cách tốt để bảo mật.” | Không đủ. Message, cause, suppressed và log ở nơi khác vẫn có thể chứa thông tin nhạy cảm; mất trace còn làm giảm khả năng điều tra. |
| “Trace in ra từ một ngoại lệ là bằng chứng không thể bị thay đổi.” | Không. API Java cho phép can thiệp; nguồn log phải được đánh giá theo mức độ tin cậy và chuỗi thu thập dữ liệu. |

## 14. Checklist khi review mã dùng `setStackTrace()`

Khi thấy một đoạn mã gọi `setStackTrace()`, hãy kiểm tra theo thứ tự:

1. **Mục đích:** có thật sự cần sửa đối tượng ngoại lệ, hay chỉ muốn đổi cách hiển thị log?
2. **Nguồn frame:** các frame đến từ JVM, từ hệ thống từ xa, hay do chương trình tạo giả? Có gắn nhãn provenance không?
3. **Bằng chứng gốc:** trace cũ có được giữ nguyên ở nơi thích hợp để điều tra không?
4. **Cause và suppressed:** liệu việc dựng trace mới có khiến người đọc nhầm rằng nguyên nhân và các lỗi phụ đã được cập nhật tương ứng?
5. **Khả ghi:** đối tượng được tạo với `writableStackTrace=false` hay không? API lúc đó không ghi giá trị mới.
6. **Đầu vào hợp lệ:** mảng và mọi phần tử có khác `null` không? Dữ liệu frame có độ dài hợp lý không?
7. **Đa luồng:** một nơi khác có thể đồng thời đọc/in cùng đối tượng ngoại lệ không? Có đang thay dấu vết mà bên khác dùng?
8. **Khả năng quan sát:** công cụ monitoring có phân nhóm theo top frame hay so sánh stack trace để gom lỗi không?
9. **Thông tin nhạy cảm:** message, cause, suppressed, tệp nguồn, tham số log hoặc metadata remote có lộ dữ liệu không?
10. **Giải pháp thay thế:** có thể dùng cause chain, structured logging, tracing phân tán, định dạng có giới hạn frame hoặc message có ngữ cảnh thay cho sửa trace?

Nếu mục tiêu chỉ là thêm ngữ cảnh, ưu tiên:

```java
throw new ServiceException("Cannot complete request", original);
```

Đây là mẫu minh họa yêu cầu `ServiceException` có constructor nhận `Throwable cause`. Ngoại lệ mới có trace riêng tại tầng bọc, còn ngoại lệ `original` giữ trace gốc và có thể truy qua `getCause()`. Điều này thường minh bạch hơn việc dùng `setStackTrace()` trên đối tượng ban đầu.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `setStackTrace()` có thay đổi nơi ngoại lệ được ném lúc runtime không?  
**Không.** Nó thay dữ liệu frame được cung cấp để đọc/in, không thay lịch sử thực thi hoặc cơ chế ném.

**Câu 2.** Nếu gọi `setStackTrace(input)` rồi thay `input[0]`, trace lưu trong ngoại lệ có đổi theo không?  
**Không.** `setStackTrace()` đã sao chép mảng đầu vào.

**Câu 3.** Nếu lấy `frames = ex.getStackTrace()` rồi gán `frames[0]`, có sửa trace nội bộ không?  
**Không.** Phải gọi `ex.setStackTrace(frames)` nếu muốn thực sự cập nhật một ngoại lệ có trace khả ghi.

**Câu 4.** `ex.setStackTrace(new StackTraceElement[]{null})` có được hiểu là “một frame không rõ” không?  
**Không.** Phần tử `null` không hợp lệ và gây `NullPointerException`.

**Câu 5.** Có thể đặt `setStackTrace(new StackTraceElement[0])` không?  
**Có**, mảng rỗng hợp lệ và tạo trace công bố rỗng nếu stack trace khả ghi.

**Câu 6.** Khi `writableStackTrace=false`, gọi `setStackTrace(validFrames)` có làm xuất hiện frame không?  
**Không.** Nó không thay trace của đối tượng; `getStackTrace()` tiếp tục trả mảng rỗng.

**Câu 7.** `fillInStackTrace()` khác `setStackTrace()` ở đâu?  
**`fillInStackTrace()`** yêu cầu ghi nhận lại stack của thread đang gọi; **`setStackTrace()`** sử dụng mảng frame được cung cấp.

**Câu 8.** `setStackTrace()` trên wrapper có làm đổi trace của đối tượng `getCause()` không?  
**Không.** Mỗi đối tượng `Throwable` quản lý trace riêng.

**Câu 9.** Một hệ thống RPC có thể cần trace tổng hợp không?  
**Có thể.** Nhưng nên đánh dấu rõ đó là dấu vết từ xa/tổng hợp và không coi nó là frame thật ở thread cục bộ.

**Câu 10.** Khi chỉ cần giảm số dòng stack trace trong log, có nên sửa trace của `Throwable` dùng chung không?  
**Thông thường không.** Nên giới hạn cách trình bày log, giữ nguyên thông tin gốc để điều tra.

## 16. Tài liệu tham khảo

- [Java SE 21 Javadoc — `Throwable.setStackTrace()`, `getStackTrace()` và `fillInStackTrace()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [Java SE 21 Javadoc — `StackTraceElement`, constructor và các trường frame](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StackTraceElement.html).
- [JLS Java SE 21 — §11.3, xử lý ngoại lệ ở runtime](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.3).

**Ghi nhớ:** `setStackTrace()` chỉ thay **danh sách frame chẩn đoán được công bố** trên một `Throwable` có trace khả ghi. Nó không thay đổi luồng thực thi, loại ngoại lệ, thông điệp, cause hay suppressed exceptions. Chỉ sửa trace khi có nhu cầu hệ thống rõ ràng và luôn phân biệt dấu vết gốc với dấu vết do ứng dụng hoặc hệ thống từ xa cung cấp.
