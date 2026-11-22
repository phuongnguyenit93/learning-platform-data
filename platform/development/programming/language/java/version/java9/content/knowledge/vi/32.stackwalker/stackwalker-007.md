# Khung phản chiếu, khung ẩn và tùy chọn quan sát với `StackWalker`

Java 9 giới thiệu `java.lang.StackWalker`, API chuyên dụng để duyệt call stack của thread hiện tại. Mặc định, `StackWalker` tập trung vào các khung gọi hữu ích của ứng dụng và ẩn một số khung triển khai như khung phản chiếu (reflection frames) và khung ẩn do JVM đánh dấu (hidden frames). Khi cần chẩn đoán sâu hơn, có thể chọn các tùy chọn `SHOW_REFLECT_FRAMES`, `SHOW_HIDDEN_FRAMES` và `RETAIN_CLASS_REFERENCE`.

Ba tùy chọn này phục vụ những mục đích khác nhau: quan sát khung phản chiếu, quan sát mọi khung ẩn, hoặc lấy tham chiếu `Class<?>` từ một stack frame. Chúng không thay đổi luồng thực thi; chúng chỉ điều chỉnh thông tin mà lần stack walk có thể quan sát.

## 1. Stack frame và cách StackWalker quan sát call stack

Mỗi lần gọi phương thức tạo ra một frame trong call stack của thread. Frame chứa thông tin về phương thức đang hoạt động, lớp khai báo, vị trí mã nguồn nếu có và một số thuộc tính thực thi. Khi phương thức gọi phương thức khác, frame của lời gọi mới được đặt lên trên stack; khi phương thức kết thúc, frame đó được gỡ xuống.

`StackWalker` cho phép duyệt các frame này theo thứ tự từ frame hiện tại đi ngược về các caller. Nó cung cấp stream `StackWalker.StackFrame`, nhờ đó ứng dụng có thể lọc, ánh xạ hoặc lấy một số frame cần thiết mà không nhất thiết phải tạo trước một mảng stack trace đầy đủ.

Ví dụ đọc tên lớp và tên phương thức:

```java
StackWalker walker = StackWalker.getInstance();
walker.forEach(frame ->
    System.out.println(frame.getClassName() + "." + frame.getMethodName()));
```

`StackWalker.getInstance()` tạo walker với các tùy chọn mặc định. Các frame phản chiếu và frame ẩn bị lọc khỏi kết quả mặc định, giúp call stack ít bị nhiễu bởi chi tiết nội bộ của cơ chế gọi.

## 2. Reflection frames là gì?

Reflection cho phép chương trình tìm lớp, phương thức hoặc constructor rồi gọi chúng khi chạy. Những lời gọi như `Method.invoke(...)` và `Constructor.newInstance(...)` đi qua các lớp triển khai reflection của JDK. Các frame nội bộ này có thể xuất hiện trong call stack trong lúc lời gọi phản chiếu đang diễn ra.

Ví dụ:

```java
Method method = Service.class.getDeclaredMethod("run");
method.invoke(service);
```

Trong lúc `run()` đang thực thi, call stack có thể chứa frame của phương thức ứng dụng, frame gọi `Method.invoke` và các frame triển khai reflection của JDK. Những frame triển khai này thường không giúp ích khi tìm caller nghiệp vụ, vì vậy `StackWalker` ẩn chúng theo mặc định.

Reflection frame là một nhóm frame triển khai đặc biệt. Tùy chọn `SHOW_REFLECT_FRAMES` cho phép hiện nhóm này mà vẫn giữ cơ chế lọc các hidden frame khác.

## 3. Hidden frames là gì?

Hidden frame là frame mà JVM đánh dấu là ẩn trong stack walk thông thường. Các frame hỗ trợ việc gọi method handle là một ví dụ quan trọng: JVM có thể dùng các frame nội bộ để thực thi lời gọi method handle, nhưng chúng không nhất thiết là một phần của call stack nghiệp vụ mà ứng dụng muốn hiển thị.

Reflection frames cũng thuộc nhóm frame bị ẩn theo mặc định. Vì vậy, `SHOW_HIDDEN_FRAMES` là lựa chọn rộng hơn: nó yêu cầu hiển thị tất cả hidden frames, bao gồm reflection frames và các frame ẩn khác do JVM đánh dấu.

Không nên nhầm hidden frame với hidden class. Hidden frame là khái niệm về việc JVM có hiển thị một frame trong stack walk hay không; hidden class là một cơ chế định nghĩa lớp riêng của JVM. Hai khái niệm có liên quan đến runtime nhưng không đồng nghĩa.

## 4. Ba tùy chọn quan sát của StackWalker

`StackWalker.Option` định nghĩa ba tùy chọn:

| Tùy chọn | Tác dụng | Khi nên dùng |
| --- | --- | --- |
| `RETAIN_CLASS_REFERENCE` | Giữ khả năng lấy đối tượng `Class<?>` từ `StackFrame`. | Khi cần so sánh class identity, annotation, module hoặc metadata của lớp. |
| `SHOW_REFLECT_FRAMES` | Hiển thị các frame reflection thường bị lọc. | Khi điều tra lời gọi thông qua reflection hoặc framework dựa trên reflection. |
| `SHOW_HIDDEN_FRAMES` | Hiển thị tất cả hidden frames, gồm reflection frames và frame ẩn do JVM đánh dấu. | Khi phân tích sâu luồng gọi, method handle hoặc chi tiết runtime. |

Có thể tạo walker với một tùy chọn:

```java
StackWalker reflectionWalker =
    StackWalker.getInstance(StackWalker.Option.SHOW_REFLECT_FRAMES);

StackWalker hiddenWalker =
    StackWalker.getInstance(StackWalker.Option.SHOW_HIDDEN_FRAMES);

StackWalker classWalker =
    StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);
```

Hoặc kết hợp nhiều tùy chọn bằng một tập hợp:

```java
StackWalker walker = StackWalker.getInstance(Set.of(
    StackWalker.Option.RETAIN_CLASS_REFERENCE,
    StackWalker.Option.SHOW_REFLECT_FRAMES
));
```

`Set.of(...)` có từ Java 9. Nếu cần vừa lấy `Class<?>` vừa quan sát reflection frames, có thể kết hợp hai tùy chọn trong cùng một walker.

## 5. `SHOW_REFLECT_FRAMES` và `SHOW_HIDDEN_FRAMES` khác nhau thế nào?

Đây là khác biệt quan trọng nhất khi chọn chế độ quan sát:

- Mặc định: reflection frames và hidden frames bị ẩn.
- `SHOW_REFLECT_FRAMES`: hiện reflection frames; các hidden frame khác vẫn được lọc.
- `SHOW_HIDDEN_FRAMES`: hiện tất cả hidden frames, bao gồm reflection frames và frame method handle do JVM đánh dấu.

Bảng minh họa:

| Loại frame | Mặc định | `SHOW_REFLECT_FRAMES` | `SHOW_HIDDEN_FRAMES` |
| --- | --- | --- | --- |
| Frame phương thức ứng dụng | Hiện | Hiện | Hiện |
| Reflection frame | Ẩn | Hiện | Hiện |
| Hidden frame khác, ví dụ method-handle plumbing | Ẩn | Ẩn | Hiện |

`SHOW_HIDDEN_FRAMES` phù hợp khi cần quan sát rộng nhất. Tuy nhiên, kết quả có thể chứa nhiều chi tiết triển khai của JDK và JVM, khiến log dài hơn và phụ thuộc phiên bản runtime hơn.

## 6. `RETAIN_CLASS_REFERENCE` và đối tượng Class

Mặc định, `StackFrame` cung cấp tên lớp qua `getClassName()`. Nếu cần đối tượng lớp thực tế, phải tạo walker với `RETAIN_CLASS_REFERENCE` rồi gọi `getDeclaringClass()`.

```java
StackWalker walker = StackWalker.getInstance(
    StackWalker.Option.RETAIN_CLASS_REFERENCE);

Class<?> declaringClass = walker.walk(frames ->
    frames.findFirst()
        .orElseThrow()
        .getDeclaringClass());
```

Khi walker không bật `RETAIN_CLASS_REFERENCE`, gọi `getDeclaringClass()` sẽ ném `UnsupportedOperationException`. Vì vậy, hãy bật tùy chọn này ngay từ lúc tạo walker nếu logic cần class identity.

`getClassName()` phù hợp khi chỉ cần tên để ghi log hoặc hiển thị. `getDeclaringClass()` hữu ích khi cần so sánh bằng `==`, kiểm tra annotation, đọc metadata hoặc thực hiện logic dựa trên chính đối tượng `Class<?>`.

`RETAIN_CLASS_REFERENCE` không tự hiện thêm reflection frames hay hidden frames. Nó độc lập với hai tùy chọn hiển thị frame; có thể kết hợp chúng khi cần cả class identity và stack trace chi tiết.

## 7. Tạo walker và duyệt frame

Các factory thường dùng:

```java
StackWalker.getInstance();
StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);
StackWalker.getInstance(Set.of(
    StackWalker.Option.SHOW_REFLECT_FRAMES,
    StackWalker.Option.RETAIN_CLASS_REFERENCE
));
```

`StackWalker.getInstance(Set<Option> options, int estimateDepth)` còn cho phép cung cấp độ sâu stack ước lượng để tối ưu việc chuẩn bị vùng lưu trữ nội bộ. Đây là gợi ý về kích thước, không phải giới hạn số frame được phép duyệt.

Có hai cách duyệt phổ biến:

```java
walker.forEach(frame -> inspect(frame));

List<String> methods = walker.walk(frames ->
    frames.map(StackWalker.StackFrame::getMethodName)
        .toList());
```

`forEach` phù hợp khi xử lý từng frame ngay trong callback. `walk` phù hợp khi cần lọc, tìm frame, ánh xạ sang dữ liệu khác hoặc tính kết quả tổng hợp.

## 8. Các thông tin có thể lấy từ StackFrame

`StackWalker.StackFrame` cung cấp các thông tin thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getClassName()` | Tên đầy đủ của lớp khai báo phương thức. |
| `getMethodName()` | Tên phương thức. |
| `getDeclaringClass()` | Đối tượng `Class<?>`; cần `RETAIN_CLASS_REFERENCE`. |
| `getFileName()` | Tên file nguồn nếu runtime có thông tin. |
| `getLineNumber()` | Số dòng nếu có thông tin debug phù hợp. |
| `getByteCodeIndex()` | Chỉ số bytecode của vị trí thực thi nếu xác định được. |
| `isNativeMethod()` | Cho biết frame có thuộc native method hay không. |
| `toStackTraceElement()` | Chuyển frame thành `StackTraceElement`. |

Không phải frame nào cũng có tên file hoặc số dòng. Ví dụ, mã không có thông tin debug, native method hoặc frame nội bộ có thể trả về giá trị không xác định. Không nên xem `getFileName()` và `getLineNumber()` là dữ liệu luôn có.

## 9. Stream trong walk chỉ dùng trong phạm vi callback

`walk(Function<Stream<StackFrame>, T>)` cấp stream cho hàm callback và thực hiện stack walk trong phạm vi lời gọi đó. Hãy tiêu thụ stream ngay trong callback và trả về dữ liệu đã xử lý.

Đúng:

```java
List<String> callers = walker.walk(frames ->
    frames.limit(10)
        .map(StackWalker.StackFrame::getClassName)
        .toList());
```

Không nên trả nguyên stream ra ngoài để dùng sau:

```java
// Không dùng stream sau khi walk đã kết thúc.
Stream<StackWalker.StackFrame> frames =
    walker.walk(stream -> stream);
```

Stream frame gắn với lần stack walk hiện tại; sau khi callback kết thúc, không thể giữ nó để duyệt tùy ý về sau. Nếu cần dùng sau đó, hãy chuyển các thông tin cần thiết thành `List<String>`, `List<StackTraceElement>` hoặc một cấu trúc dữ liệu khác ngay bên trong callback.

## 10. Ví dụ hoàn chỉnh: quan sát reflection và method-handle frames

Chương trình dưới đây thực hiện hai lời gọi khác nhau: một lời gọi qua `Method.invoke`, một lời gọi qua `MethodHandle`. Nó so sánh ba chế độ quan sát và xác nhận `RETAIN_CLASS_REFERENCE` có thể lấy lớp khai báo.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.List;

public class Main {
    private static final StackWalker DEFAULT = StackWalker.getInstance();
    private static final StackWalker REFLECT =
        StackWalker.getInstance(StackWalker.Option.SHOW_REFLECT_FRAMES);
    private static final StackWalker HIDDEN =
        StackWalker.getInstance(StackWalker.Option.SHOW_HIDDEN_FRAMES);
    private static final StackWalker RETAIN =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    public static void main(String[] args) throws Throwable {
        Method reflected = Main.class.getDeclaredMethod("capture", String.class);
        reflected.invoke(null, "reflection");

        MethodHandle handle = MethodHandles.lookup().findStatic(
            Main.class, "capture", MethodType.methodType(void.class, String.class));
        handle.invokeExact("method-handle");
    }

    private static void capture(String path) {
        List<String> ordinary = DEFAULT.walk(frames ->
            frames.map(StackWalker.StackFrame::getClassName).toList());
        List<String> reflection = REFLECT.walk(frames ->
            frames.map(StackWalker.StackFrame::getClassName).toList());
        List<String> hidden = HIDDEN.walk(frames ->
            frames.map(StackWalker.StackFrame::getClassName).toList());

        boolean defaultReflect = ordinary.stream().anyMatch(Main::isReflectionFrame);
        boolean shownReflect = reflection.stream().anyMatch(Main::isReflectionFrame);
        boolean hiddenReflect = hidden.stream().anyMatch(Main::isReflectionFrame);
        boolean defaultInvoke = ordinary.stream().anyMatch(Main::isMethodHandleFrame);
        boolean reflectInvoke = reflection.stream().anyMatch(Main::isMethodHandleFrame);
        boolean hiddenInvoke = hidden.stream().anyMatch(Main::isMethodHandleFrame);

        String declaringClass = RETAIN.walk(frames ->
            frames.filter(frame -> frame.getClassName().equals(Main.class.getName()))
                .findFirst()
                .orElseThrow()
                .getDeclaringClass()
                .getName());

        if ("reflection".equals(path)) {
            check(!defaultReflect && shownReflect && hiddenReflect,
                "reflection option behavior");
            check(Main.class.getName().equals(declaringClass),
                "retained class reference");
            System.out.println("reflection: default=" + defaultReflect
                + ", reflect-option=" + shownReflect
                + ", hidden-option=" + hiddenReflect);
            System.out.println("retained declaring class: " + declaringClass);
        } else {
            check(!defaultInvoke && !reflectInvoke && hiddenInvoke,
                "hidden method-handle behavior");
            System.out.println("method handles: default=" + defaultInvoke
                + ", reflect-option=" + reflectInvoke
                + ", hidden-option=" + hiddenInvoke);
        }
    }

    private static boolean isReflectionFrame(String name) {
        return name.startsWith("java.lang.reflect.")
            || name.startsWith("jdk.internal.reflect.");
    }

    private static boolean isMethodHandleFrame(String name) {
        return name.startsWith("java.lang.invoke.");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout trên môi trường JDK 17 dùng để kiểm thử:

```text
reflection: default=false, reflect-option=true, hidden-option=true
retained declaring class: Main
method handles: default=false, reflect-option=false, hidden-option=true
```

Kết quả cho thấy `SHOW_REFLECT_FRAMES` làm hiện reflection frames nhưng không làm hiện các frame method handle. `SHOW_HIDDEN_FRAMES` làm hiện cả hai nhóm trong ví dụ. Tên và số lượng frame nội bộ cụ thể có thể thay đổi theo JDK và JVM; chương trình kiểm tra nhóm frame theo package thay vì phụ thuộc vào toàn bộ stack trace.

## 11. Lọc stack frame để tìm caller phù hợp

Trong ứng dụng, thường không cần in toàn bộ stack. Có thể lọc frame thuộc package nội bộ của framework hoặc bỏ qua một số lớp tiện ích để tìm frame ứng dụng gần nhất:

```java
String caller = StackWalker.getInstance().walk(frames ->
    frames
        .map(StackWalker.StackFrame::getClassName)
        .filter(name -> !name.startsWith("com.example.logging."))
        .findFirst()
        .orElse("<unknown>"));
```

Ví dụ này chỉ minh họa cách lọc theo tên lớp. Trong hệ thống thực tế, nên dùng package hoặc module namespace do ứng dụng kiểm soát; không dựa vào tên lớp nội bộ của JDK vì chúng có thể thay đổi giữa các bản phát hành.

Khi cần caller dưới dạng `Class<?>`, dùng walker có `RETAIN_CLASS_REFERENCE` và `getCallerClass()` hoặc `StackFrame.getDeclaringClass()` theo nhu cầu. `getCallerClass()` là tiện ích cho trường hợp cần caller class mà không phải tự duyệt frame; nó yêu cầu walker giữ class reference.

## 12. Khi nào nên bật từng tùy chọn?

| Nhu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Log caller của ứng dụng | Mặc định | Tránh nhiễu bởi chi tiết reflection và runtime. |
| Điều tra framework gọi ứng dụng bằng reflection | `SHOW_REFLECT_FRAMES` | Quan sát đường gọi reflection. |
| Điều tra method handle hoặc luồng gọi nội bộ JVM | `SHOW_HIDDEN_FRAMES` | Quan sát đầy đủ hơn các frame bị ẩn. |
| So sánh lớp theo identity hoặc đọc metadata | `RETAIN_CLASS_REFERENCE` | Lấy đối tượng `Class<?>` thực tế. |
| Vừa xem reflection vừa cần class identity | Kết hợp `SHOW_REFLECT_FRAMES` và `RETAIN_CLASS_REFERENCE` | Mỗi tùy chọn đảm nhiệm một mục đích riêng. |

Không nên bật `SHOW_HIDDEN_FRAMES` cho mọi log mặc định nếu ứng dụng chỉ cần tên caller. Nó có thể làm log dài, thêm chi tiết phụ thuộc runtime và khiến việc đọc call stack nghiệp vụ khó hơn.

## 13. Hiệu năng và giới hạn quan sát

- **Chỉ duyệt khi cần:** stack walk có chi phí. Tránh lấy toàn bộ stack trong vòng lặp nóng hoặc trên mọi sự kiện có tần suất rất cao.
- **Giới hạn số frame:** dùng `limit(n)` khi chỉ cần một số caller đầu tiên.
- **Lọc sớm:** ánh xạ hoặc lọc ngay trong `walk` thay vì chuyển toàn bộ frame thành chuỗi rồi mới xử lý.
- **Chỉ giữ class reference khi cần:** `RETAIN_CLASS_REFERENCE` cho phép lấy đối tượng lớp, nhưng nếu lưu các class này lâu dài có thể giữ tham chiếu đến class loader; chỉ giữ dữ liệu cần thiết.
- **Không giả định frame luôn đầy đủ:** tên file, số dòng và bytecode index có thể không xác định.
- **Không quan sát thread khác bằng walker hiện tại:** `StackWalker` duyệt call stack của thread đang thực hiện stack walk.
- **Không phụ thuộc frame nội bộ:** reflection và method-handle implementation có thể thay đổi giữa các JDK; chỉ dùng chúng cho chẩn đoán phù hợp.
- **Không xem stack trace là ranh giới bảo mật:** tên lớp và frame không nên được dùng thay cho xác thực hoặc kiểm soát quyền truy cập.

`StackWalker` cung cấp một góc nhìn tại thời điểm gọi. Nó không phải bản ghi lịch sử lời gọi, không theo dõi các thread trong tương lai và không thay thế profiler hoặc công cụ quan sát hiệu năng.

## 14. Lỗi thường gặp

1. **Mặc định mong đợi thấy `Method.invoke`.** Reflection frames thường bị lọc; bật `SHOW_REFLECT_FRAMES` khi cần chẩn đoán.
2. **Dùng `SHOW_REFLECT_FRAMES` để xem mọi hidden frame.** Tùy chọn này chỉ nhắm đến reflection; dùng `SHOW_HIDDEN_FRAMES` khi cần tất cả hidden frames.
3. **Nghĩ `SHOW_HIDDEN_FRAMES` chỉ là tên khác của `SHOW_REFLECT_FRAMES`.** Nó rộng hơn và có thể hiện cả frame method handle do JVM đánh dấu.
4. **Gọi `getDeclaringClass()` mà không bật `RETAIN_CLASS_REFERENCE`.** Lời gọi có thể ném `UnsupportedOperationException`; cấu hình walker đúng ngay từ đầu.
5. **Bật `RETAIN_CLASS_REFERENCE` để hiện frame.** Tùy chọn này giữ class reference, không thay đổi chính sách hiển thị frame.
6. **Trả stream từ `walk` để dùng về sau.** Stream chỉ dùng trong callback của lần stack walk; hãy chuyển kết quả cần thiết thành collection hoặc giá trị khác.
7. **Dựa vào tên frame nội bộ của JDK.** Những tên như `jdk.internal.reflect...` hoặc `java.lang.invoke...` là chi tiết triển khai; không dùng làm hợp đồng nghiệp vụ.
8. **Giả định mọi frame đều có file và số dòng.** Thông tin nguồn có thể không có hoặc không xác định.
9. **In toàn bộ hidden frames trong log production.** Stack có thể rất dài và chứa chi tiết runtime không cần thiết; chỉ bật khi điều tra.
10. **Dùng StackWalker để kiểm tra quyền.** Caller frame không phải cơ chế xác thực; dùng security boundary và kiểm tra quyền thực sự của ứng dụng.

## 15. Ghi nhớ

1. `StackWalker` được giới thiệu trong Java 9 để duyệt call stack của thread hiện tại.
2. Reflection frames và hidden frames bị lọc theo mặc định.
3. `SHOW_REFLECT_FRAMES` hiện reflection frames.
4. `SHOW_HIDDEN_FRAMES` hiện tất cả hidden frames, gồm reflection và method-handle frames.
5. `RETAIN_CLASS_REFERENCE` cho phép `StackFrame.getDeclaringClass()` trả về `Class<?>`.
6. `RETAIN_CLASS_REFERENCE` không tự thay đổi frame visibility; có thể kết hợp với tùy chọn hiển thị.
7. `walk` và `forEach` nên xử lý frame trong phạm vi stack walk; không giữ stream để dùng sau callback.
8. Tên và số lượng frame nội bộ phụ thuộc JDK/JVM; kiểm tra theo mục đích thay vì hard-code toàn bộ stack trace.