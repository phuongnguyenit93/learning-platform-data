# Ảnh hưởng của hidden class đến stack trace và công cụ chẩn đoán (Java 15+)

## 1. Vấn đề cần hiểu

**Hidden class** được Java hỗ trợ chính thức từ **Java 15** (JEP 371), thường được tạo động bằng `MethodHandles.Lookup.defineHiddenClass(...)`. Chúng hữu ích cho runtime sinh mã, các framework, và những triển khai cần lớp có vòng đời linh hoạt nhưng **không muốn các lớp đó được khám phá bằng tên như class thông thường**.

Khả năng này có hệ quả trực tiếp đối với **debugging, stack trace, logging, profiler và Java agent**:

- Một exception có thể thực sự phát sinh bên trong hidden class nhưng **stack trace thông thường không hiện frame** đó.
- `StackWalker` có chế độ hiển thị frame bị ẩn, cho phép phân tích sâu hơn khi đang ở **đúng thread và thời điểm chạy**.
- Tên trả về từ `Class.getName()` của hidden class **không phải binary name thông thường**, nên việc tra cứu lớp theo chuỗi tên có thể thất bại.
- Công cụ truy vấn **toàn bộ class trong JVM** có thể thấy hidden class, trong khi cơ chế chỉ tìm class **qua tên/class loader** lại không thấy.
- Hidden class có thể được dỡ khi không còn được giữ sống theo các quy tắc của JVM. Vì vậy danh sách lớp quan sát tại những thời điểm khác nhau có thể khác nhau.

**Thông điệp quan trọng:** *hidden* nghĩa là ẩn khỏi những cách tra cứu và khung stack mặc định nhất định; **không** có nghĩa mã không thực thi, exception không xảy ra, hay debugger/profiler hoàn toàn không thể quan sát lớp đó.

Tất cả các API được dùng trong bài (`defineHiddenClass`, `Class.isHidden`, `StackWalker`, `Instrumentation` và JVM TI) đều còn có ý nghĩa trong Java hiện hành. Ví dụ biên dịch được ở Java 15 và chạy tốt trên Java 17+.

## 2. Định danh hidden class: không thể suy ra từ tên như lớp thường

Sau khi định nghĩa:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classBytes, true);
Class<?> hidden = hiddenLookup.lookupClass();
~~~

Đây là **mã minh họa**, trong đó `classBytes` phải là bytecode class file hợp lệ thuộc cùng runtime package và `Lookup` phải có full privilege (`PRIVATE` và `MODULE`). `hiddenLookup` là đối tượng `Lookup` mới trỏ đến hidden class; từ nó có thể lấy `Class<?>` hoặc tìm `MethodHandle`.

Một số thuộc tính:

~~~java
hidden.isHidden();                // true
hidden.getName().contains("/");  // true đối với tên được JVM tạo
~~~

`Class.getName()` đối với hidden class trả chuỗi có ký tự gạch chéo `/` và hậu tố do JVM tạo, ví dụ theo dạng mô tả:

~~~text
com.example.Template/0x...      (phần hậu tố không ổn định)
~~~

**Không** lấy chuỗi trên làm binary name chuẩn hoặc dùng nó làm ID ổn định. Đặc biệt:

~~~java
Class.forName(hidden.getName()); // ClassNotFoundException
~~~

Đây là kết quả **đúng thiết kế**, không chứng minh hidden class chưa từng được định nghĩa hay đã bị dỡ. Hidden class không thể được tìm lại qua `Class.forName` hoặc `ClassLoader.loadClass` theo tên thông thường.

**Để chẩn đoán**, giữ `Class<?>` hoặc `MethodHandles.Lookup`/`MethodHandle` trả về từ lần định nghĩa. Nếu cần log định danh ổn định ở mức nghiệp vụ, tạo ID riêng cho **bản sinh mã**, ví dụ tên component, generation ID và version, thay vì chỉ trông vào hậu tố `/0x...` của JVM.

## 3. Exception stack trace có thể bỏ qua frame của hidden class

Xét đường thực thi:

~~~text
HiddenClassDiagnosticsDemo.main()
    └─ MethodHandle.invokeExact()
         └─ HiddenClass(...).fail()
              └─ throw new IllegalArgumentException("boom")
~~~

Ở runtime, `fail()` **thực sự chạy bên trong hidden class**. Tuy nhiên, trên JDK 24 (HotSpot) dùng ở ví dụ kiểm chứng, các frame của hidden class bị lọc khỏi `Throwable.getStackTrace()` và stack trace dạng in ra thông thường. Frame đầu nhìn thấy có thể là `main` — nơi thực hiện lời gọi `MethodHandle`.

Điều này giải thích tình huống phổ biến khi lỗi từ mã sinh động xuất hiện với một trace ngắn, hoặc trace bắt đầu tại bộ điều phối/framework thay vì phương thức sinh ra lỗi.

~~~java
try {
    // Gọi MethodHandle trỏ vào phương thức hidden class...
} catch (IllegalArgumentException ex) {
    ex.printStackTrace();
}
~~~

`catch` vẫn nhận được đúng exception. **Nội dung thông điệp lỗi, cause, suppressed exceptions và kiểu exception không tự biến mất chỉ vì frame của hidden class bị ẩn**. Nhưng stack trace dùng mặc định có thể thiếu đoạn call chain giúp xác định vị trí sinh lỗi.

**Không suy luận từ việc frame vắng mặt rằng hidden class đã bị garbage collected**: stack trace là một cách trình bày lời gọi; vòng đời class là vấn đề độc lập.

### Stack trace thông thường không phải bằng chứng đầy đủ về call stack

Các cơ chế lấy stack khác nhau có thể lọc frame theo những quy tắc và tùy chọn khác nhau. Ví dụ mặc định ở trên được kiểm chứng bằng chương trình trong mục 6; không nên giả định mọi debugger, JFR configuration, native agent hay JVM vendor đều sẽ hiển thị đúng cùng một tập frame.

## 4. Dùng `StackWalker` để xem frame ẩn

`java.lang.StackWalker` có từ Java 9 và vẫn là API chuẩn để duyệt **stack của thread hiện tại**. Hai tùy chọn liên quan nhất:

| Tùy chọn | Tác dụng |
| --- | --- |
| `StackWalker.Option.SHOW_HIDDEN_FRAMES` | Yêu cầu hiển thị mọi hidden frame, bao gồm các reflection/implementation frame thường bị lọc |
| `StackWalker.Option.RETAIN_CLASS_REFERENCE` | Cho phép gọi `StackFrame.getDeclaringClass()` để nhận `Class<?>` thật, kể cả để kiểm tra `isHidden()` |

### 4.1. Mặc định: bỏ hidden frames

~~~java
StackWalker normalWalker = StackWalker.getInstance();
~~~

`normalWalker.walk(...)` không đưa hidden frames vào luồng frame, theo cấu hình mặc định. Ngay cả khi chỉ thêm `RETAIN_CLASS_REFERENCE`, điều đó **không bật hiển thị frame ẩn**.

### 4.2. Muốn nhìn thấy hidden class thì bật cả hai tùy chọn

~~~java
import java.lang.StackWalker;
import java.util.Set;

StackWalker detailedWalker = StackWalker.getInstance(
        Set.of(
                StackWalker.Option.SHOW_HIDDEN_FRAMES,
                StackWalker.Option.RETAIN_CLASS_REFERENCE));

boolean containsHidden = detailedWalker.walk(
        frames -> frames.anyMatch(
                frame -> frame.getDeclaringClass().isHidden()));
~~~

Đây là **mã minh họa**, chạy tại thread mà bạn đang muốn quan sát. Nếu đang thực thi bên trong một hidden class, `containsHidden` có thể là `true`.

- `SHOW_HIDDEN_FRAMES` có thể làm xuất hiện cả những frame nội bộ liên quan tới reflection hoặc MethodHandle; **không phải tất cả hidden frames đều là frame của hidden class do bạn sinh**.
- Để tìm đúng một hidden class đã biết, so sánh `frame.getDeclaringClass() == hiddenClass`, thay vì lọc các tên chứa `/`.
- `getDeclaringClass()` cần `RETAIN_CLASS_REFERENCE`; nếu bỏ tùy chọn này mà gọi phương thức, bạn có thể nhận `UnsupportedOperationException`.
- `StackWalker.walk(...)` chỉ làm việc trên **stack đang hoạt động tại thời điểm gọi**; nếu hidden method đã chạy xong, không thể gọi một `StackWalker` mới ở bên ngoài rồi mong xem lại lịch sử frame đã biến mất.
- Đừng đưa `Stream<StackFrame>` nhận từ `walk(...)` ra ngoài callback để duyệt muộn: luồng stack này chỉ hợp lệ trong thời gian callback được thực hiện.

### 4.3. Không nhầm `getCallerClass()` với `walk()`

`StackWalker.getCallerClass()` lọc các frame reflection, MethodHandle và hidden frames ngay cả khi walker có `SHOW_HIDDEN_FRAMES`. Nếu mục tiêu là **quan sát chính hidden frames**, hãy dùng `walk(...)` với option phù hợp, không dùng `getCallerClass()` như một API thay thế.

## 5. Quan sát được frame chưa chắc có đủ thông tin mã nguồn

Khi một công cụ xem được hidden frame, việc hiển thị **file nguồn, dòng, bytecode index hay method name** phụ thuộc metadata trong class file và khả năng của công cụ.

- `StackWalker.StackFrame.getFileName()` trả tên file nguồn từ metadata như `SourceFile` nếu có, ngược lại có thể trả `null`.
- `getLineNumber()` đọc thông tin debug như `LineNumberTable`; nếu không có dòng tương ứng, có thể trả giá trị âm.
- `getMethodName()` là tên phương thức tại frame; `getByteCodeIndex()` trả vị trí bytecode khi có thông tin phù hợp.
- Nếu một framework **tự sinh bytecode** mà không thêm metadata debug, dù đã bật `SHOW_HIDDEN_FRAMES`, công cụ vẫn có thể không biết dòng code nguồn ứng với lệnh bytecode.

Để hỗ trợ chẩn đoán lớp sinh động, nếu phù hợp hãy sinh metadata nguồn/line number đúng chuẩn và lưu mapping **generation ID → nguồn tạo ra bytecode → phiên bản template/script → method**. Không nên ghi log toàn bộ bytecode hoặc nội dung nhạy cảm chỉ để debug.

## 6. Ví dụ Java hoàn chỉnh: so sánh lớp thường và hidden class

Chương trình dưới đây tạo một lớp `Template` thông thường, lấy bytes của `Template.class` và định nghĩa lại chúng thành **hidden class**. Hai biến thể có cùng bytecode nhưng khác **danh tính lớp và quy tắc hiển thị stack**.

Trong `Template.inspect()`, chương trình gọi `StackWalker` ngay **khi phương thức đang chạy**, kiểm tra lớp hiện tại có xuất hiện trong walker mặc định và walker có `SHOW_HIDDEN_FRAMES` hay không; sau đó tạo exception để kiểm tra `getStackTrace()`.

Tên tệp: **`HiddenClassDiagnosticsDemo.java`**.

~~~java
import java.io.InputStream;
import java.lang.StackWalker;
import java.lang.StackWalker.Option;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;
import java.util.Set;

public class HiddenClassDiagnosticsDemo {
    static class Template {
        public static boolean[] inspect() {
            Class<?> self = MethodHandles.lookup().lookupClass();
            boolean defaultSeesSelf = StackWalker.getInstance(
                    Set.of(Option.RETAIN_CLASS_REFERENCE))
                    .walk(frames -> frames.anyMatch(
                            frame -> frame.getDeclaringClass() == self));
            boolean expandedSeesSelf = StackWalker.getInstance(
                    Set.of(Option.RETAIN_CLASS_REFERENCE, Option.SHOW_HIDDEN_FRAMES))
                    .walk(frames -> frames.anyMatch(
                            frame -> frame.getDeclaringClass() == self));
            Throwable captured = new IllegalStateException("captured");
            boolean throwableSeesSelf = Arrays.stream(captured.getStackTrace())
                    .anyMatch(frame -> frame.getClassName().equals(self.getName()));
            return new boolean[]{defaultSeesSelf, expandedSeesSelf, throwableSeesSelf};
        }

        public static void fail() {
            throw new IllegalArgumentException("boom");
        }
    }

    public static void main(String[] args) throws Throwable {
        boolean[] ordinary = Template.inspect();

        byte[] bytes;
        try (InputStream in = HiddenClassDiagnosticsDemo.class.getResourceAsStream(
                "HiddenClassDiagnosticsDemo$Template.class")) {
            if (in == null) throw new IllegalStateException("class bytes missing");
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, true);
        Class<?> hidden = hiddenLookup.lookupClass();
        boolean[] inspected = (boolean[]) hiddenLookup.findStatic(
                hidden, "inspect", MethodType.methodType(boolean[].class))
                .invokeExact();

        System.out.println("ordinaryDefaultSeesSelf=" + ordinary[0]);
        System.out.println("ordinaryThrowableSeesSelf=" + ordinary[2]);
        System.out.println("isHidden=" + hidden.isHidden());
        System.out.println("nameHasSlash=" + hidden.getName().contains("/"));
        System.out.println("defaultWalkerSeesHidden=" + inspected[0]);
        System.out.println("showHiddenWalkerSeesHidden=" + inspected[1]);
        System.out.println("capturedThrowableSeesHidden=" + inspected[2]);

        try {
            Class.forName(hidden.getName());
            System.out.println("classForName=found");
        } catch (ClassNotFoundException expected) {
            System.out.println("classForName=notFound");
        }

        try {
            hiddenLookup.findStatic(
                    hidden, "fail", MethodType.methodType(void.class))
                    .invokeExact();
            System.out.println("unexpectedNoException");
        } catch (IllegalArgumentException expected) {
            System.out.println("caughtMessage=" + expected.getMessage());
            boolean hiddenInTrace = Arrays.stream(expected.getStackTrace())
                    .anyMatch(frame -> frame.getClassName().equals(hidden.getName()));
            System.out.println("caughtTraceSeesHidden=" + hiddenInTrace);
            System.out.println("firstTraceClass=" +
                    expected.getStackTrace()[0].getClassName());
        }

        System.out.println("checks=" + (
                ordinary[0] && ordinary[2] && hidden.isHidden()
                && hidden.getName().contains("/")
                && !inspected[0] && inspected[1] && !inspected[2]));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 HiddenClassDiagnosticsDemo.java
java HiddenClassDiagnosticsDemo
~~~

Các API sử dụng ở đây đều có trong Java 15, nên cũng biên dịch được với `javac --release 15 ...`. Chương trình đã được kiểm chứng bằng chế độ `--release 15`, `--release 17` và JVM JDK 24. **Đầu ra chính xác của lần kiểm chứng**:

~~~text
ordinaryDefaultSeesSelf=true
ordinaryThrowableSeesSelf=true
isHidden=true
nameHasSlash=true
defaultWalkerSeesHidden=false
showHiddenWalkerSeesHidden=true
capturedThrowableSeesHidden=false
classForName=notFound
caughtMessage=boom
caughtTraceSeesHidden=false
firstTraceClass=HiddenClassDiagnosticsDemo
checks=true
~~~

### Giải thích kết quả

1. `ordinaryDefaultSeesSelf=true` và `ordinaryThrowableSeesSelf=true`: với `Template` bình thường, các API stack đang thử có thể tìm thấy frame của lớp đó.
2. `isHidden=true`: `defineHiddenClass` thật sự định nghĩa hidden class mới từ class file của `Template`.
3. `nameHasSlash=true`: tên runtime của hidden class có hậu tố dạng `/0x...`; không in toàn bộ vì mỗi lần chạy có thể khác.
4. `defaultWalkerSeesHidden=false`: walker **không** bật `SHOW_HIDDEN_FRAMES` đã bỏ qua frame của hidden class hiện tại.
5. `showHiddenWalkerSeesHidden=true`: walker bật **cả** `SHOW_HIDDEN_FRAMES` và `RETAIN_CLASS_REFERENCE` tìm thấy đúng đối tượng `Class<?>` của hidden class.
6. `capturedThrowableSeesHidden=false`: exception tạo ngay trong hidden class vẫn không cho thấy frame của lớp đó trong `Throwable.getStackTrace()` ở JVM kiểm chứng.
7. `classForName=notFound`: không tìm lại được hidden class bằng chuỗi tên của nó.
8. `caughtMessage=boom`: exception phát sinh trong hidden class vẫn đi ra và bị bắt bình thường.
9. `caughtTraceSeesHidden=false` và `firstTraceClass=HiddenClassDiagnosticsDemo`: frame hidden bị lọc trong trace mặc định; frame của nơi gọi trở thành vị trí đầu tiên nhìn thấy trong ví dụ.
10. `checks=true`: kiểm tra lại những điều kiện chính bằng biểu thức boolean.

**Không nhầm hai loại hidden:** `SHOW_HIDDEN_FRAMES` là tùy chọn **lọc frame**, còn `Class.isHidden()` là thuộc tính của **lớp**. Một frame do JVM ẩn để đơn giản hóa stack trace không nhất thiết thuộc hidden class mà ứng dụng định nghĩa.

**Lưu ý về file phụ:** khi biên dịch, `javac` tạo `HiddenClassDiagnosticsDemo.class` và `HiddenClassDiagnosticsDemo$Template.class`. Chương trình đọc class file thứ hai từ classpath bằng `getResourceAsStream(...)`. Không cần thư viện ngoài hoặc kết nối mạng.

## 7. Công cụ chẩn đoán: “không tìm bằng tên” khác “không hiện trong JVM”

### 7.1. Java agent và `java.lang.instrument.Instrumentation`

Với **một Java agent thực sự đã được khởi tạo** và có đối tượng `Instrumentation`:

| API | Hidden class được bao gồm? | Ý nghĩa |
| --- | --- | --- |
| `Instrumentation.getAllLoadedClasses()` | **Có**, nếu lớp đang được JVM giữ và liệt kê tại lúc gọi | Danh sách toàn bộ lớp đang có trong JVM bao gồm hidden classes |
| `Instrumentation.getInitiatedClasses(loader)` | **Không** | API này trả các lớp được class loader tìm được theo tên, nên loại hidden classes |
| `Class.forName(hidden.getName())` | **Không tìm được** | Không phải cách tra hidden class |
| `Class.isHidden()` trên một đối tượng `Class<?>` | **Có thể nhận diện** | Cách xác định trực tiếp đối tượng lớp đang giữ |

Điều này giải thích vì sao một profiler hoặc công cụ instrumentation có thể phát hiện hidden class dù ứng dụng không gọi `Class.forName` để tìm nó được.

`getAllLoadedClasses()` chỉ dùng được nếu bạn đang viết/điều khiển **agent**, không phải một phương thức tĩnh có thể gọi từ bất kỳ code ứng dụng nào. Nếu muốn inspect từ ứng dụng bình thường, nên lưu `Class<?>` hoặc method handle trong hệ thống sinh mã từ đầu.

**Giới hạn instrumentation:** khả năng *liệt kê* không có nghĩa có thể sửa bytecode của hidden class bằng `redefineClasses`/`retransformClasses`. Hidden classes không phải mục tiêu sửa đổi lớp theo cơ chế instrumentation thông thường; với code cần tái tạo, thiết kế đường sinh **một hidden class mới** từ nguồn/bytecode mới thay vì giả định hot-redefine lớp cũ. Khi dùng agent, kiểm tra chính sách và `isModifiableClass(Class<?>)` trước mọi hành động sửa lớp.

### 7.2. JVM Tool Interface (JVMTI)

Trong đặc tả JVM TI hiện hành:

- `GetLoadedClasses` bao gồm hidden classes nếu chúng có mặt trong JVM tại thời điểm liệt kê.
- `GetClassLoaderClasses` **không** bao gồm hidden classes, vì loader không thể tìm chúng bằng tên thông thường.
- `GetClassSignature` cho hidden class có dạng **khác JNI type signature chuẩn** của named class; không thể giả định mọi chuỗi signature đều hợp lệ như type descriptor của lớp bình thường.

Vì vậy, **đừng viết debugger/agent dựa duy nhất vào danh sách lớp tra được theo tên** để kết luận hidden class không tồn tại. Tương tự, đừng ép tên chứa `/` của hidden class thành tên class để tự gọi `ClassLoader.loadClass`.

### 7.3. JFR, debugger và profilers

Java Flight Recorder (JFR), debugger dùng JDWP/JVMTI và profilers có các điểm quan sát khác `Throwable.getStackTrace()`. Việc chúng thấy lớp/frame nào phụ thuộc **loại sự kiện, cách lấy stack, các tùy chọn ghi nhận, thời điểm lấy mẫu, phiên bản JDK và khả năng của công cụ**.

Không nên hứa rằng chỉ bật JFR là mọi frame hidden sẽ hiện, hoặc rằng vì `Throwable` đã lọc frame thì JVM TI/JFR không thể ghi nhận lớp. Cách thực hành đúng là xác minh bằng chính **bản JDK và công cụ** đang chạy sản phẩm, lưu tên/cấu hình tool trong kết quả điều tra.

Với HotSpot/JDK hỗ trợ Unified Logging, có thể xem hoạt động class loading khi cần:

~~~bash
java -Xlog:class+load=info -cp . HiddenClassDiagnosticsDemo
~~~

Lệnh này có thể tạo **rất nhiều dòng log**, trong đó có thông tin tải lớp, nên dùng khi chẩn đoán và lọc theo phạm vi phù hợp. Đừng nhầm log “đã định nghĩa class” với bằng chứng class còn sống mãi. Có thể cấu hình thêm class unloading logging tùy JDK, nhưng sample ngắn trên **không bảo đảm sẽ có một sự kiện unload**.

## 8. Tác động đến vòng đời và việc chẩn đoán sau khi lớp được giải phóng

Theo cơ chế hidden class, JVM có thể dỡ một hidden class **không strong** khi nó không còn được tham chiếu theo những quy tắc hiện hành; `ClassOption.STRONG` thay đổi quan hệ giữ sống giữa class và class loader.

**Đối với chẩn đoán:**

- Một hidden class xuất hiện trong lần chụp danh sách JVM trước nhưng không còn ở lần sau **không tự động có nghĩa rò rỉ hay lỗi**. Nó có thể đã được dỡ hợp lệ.
- Khi còn tham chiếu mạnh tới `Class<?>`, đối tượng của class, method handle hoặc những cấu trúc khác giữ lớp sống, hành vi unload sẽ khác. Đừng dùng `System.gc()` làm kiểm chứng có tính quyết định về thời điểm dỡ lớp.
- Nếu ứng dụng sinh rất nhiều hidden classes, theo dõi **số lượng tạo, số lượng còn sống, tần suất sinh mã, tải metaspace, class unloading và thời gian GC** theo khả năng quan sát của runtime. Chỉ nhìn trace ngắn không đủ để đánh giá metaspace.
- Nếu cần kiểm tra lỗi xảy ra muộn, log **generation ID, script/template version, nguồn bytecode, tên lớp chủ sinh và vị trí call site** ngay khi sinh code. Không cố khôi phục lớp từ hậu tố tên sau khi frame hoặc class đã biến mất.

`STRONG` **không** phải công tắc giúp stack trace hiện hidden frames, và `SHOW_HIDDEN_FRAMES` **không** phải công tắc điều khiển vòng đời class.

## 9. Hướng dẫn điều tra một lỗi từ mã sinh động

Giả sử hệ thống gọi một `MethodHandle` trỏ tới hidden class và log chỉ xuất hiện lỗi ở lớp dispatcher.

**Quy trình hợp lý:**

1. **Bảo toàn exception thật:** ghi lại loại exception, thông điệp, cause, suppressed exceptions và context nghiệp vụ; không thay mọi lỗi thành một exception chung làm mất thông tin.
2. **Gắn context tại biên sinh mã:** tạo generation ID và ghi mapping đến nguồn/template, phiên bản, component và class/method mục tiêu. Đừng dùng mỗi `hiddenClass.getName()` làm khóa truy vết.
3. **Giữ handle trực tiếp:** dùng `Lookup`/`Class<?>`/`MethodHandle` khi cần kiểm tra. Không gọi `Class.forName` trên tên hidden.
4. **Khi cần xem stack thật**, bổ sung điểm chụp `StackWalker` **bên trong đường thực thi đang sống** với `SHOW_HIDDEN_FRAMES`; nếu cần biết class nào là hidden, thêm `RETAIN_CLASS_REFERENCE`.
5. **Kiểm tra metadata debug** trong class file do framework tạo; nếu thiếu tên file/dòng, tính năng hiển thị frame không thể tự đoán ra mapping với mã nguồn.
6. **Nếu dùng agent**, so sánh `getAllLoadedClasses` với các API loader-discoverable. Đừng dùng danh sách initiated classes làm số liệu tổng lớp trong JVM.
7. **Khi nghi metaspace/classloader leak**, dùng số liệu class loading/unloading và bộ nhớ theo thời gian; phân biệt hidden class mạnh/yếu và các tham chiếu giữ sống.
8. **Với code sinh động kém tin cậy**, không bật logging tràn lan thông tin nhạy cảm. Chỉ ghi metadata cần thiết, giới hạn truy cập và lưu log theo chính sách bảo mật.

### Các nhầm lẫn dễ gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| “Stack trace không hiện phương thức sinh mã, vậy nó không chạy” | Hidden frames có thể bị lọc khỏi trace mặc định |
| “`getName()` trả chuỗi thì có thể `Class.forName` lại” | Tên hidden class không là binary name tìm được qua loader |
| “Bật `RETAIN_CLASS_REFERENCE` là sẽ hiện hidden frame” | Cần **`SHOW_HIDDEN_FRAMES`** để không lọc chúng |
| “`SHOW_HIDDEN_FRAMES` chỉ hiển thị hidden classes của ứng dụng” | Có thể hiện cả reflection và hidden implementation frames |
| “`getCallerClass()` sẽ trả hidden caller nếu bật SHOW_HIDDEN_FRAMES” | `getCallerClass()` vẫn lọc hidden/MethodHandle/reflection frames |
| “Công cụ JVM TI không thấy hidden class vì Class.forName thất bại” | `GetLoadedClasses` bao gồm hidden classes |
| “`getAllLoadedClasses` và `getInitiatedClasses` luôn có cùng tập” | Hidden classes thuộc nhóm khác biệt quan trọng |
| “Có thể sửa trực tiếp hidden class như lớp thường trong mọi agent” | Không được suy ra khả năng sửa từ khả năng liệt kê |
| “Mất frame nghĩa là class đã unload” | Lọc stack và vòng đời class là hai vấn đề độc lập |
| “Bật `STRONG` sẽ làm stack trace đầy đủ” | STRONG liên quan quan hệ giữ sống, không phải hiển thị frame |

## 10. Tự kiểm tra

**Câu 1.** Một exception được ném trong hidden class, nhưng `ex.getStackTrace()[0]` lại là phương thức dispatcher. Điều này có thể đúng không? **Có**. Stack trace mặc định có thể lọc frame của hidden class.

**Câu 2.** Muốn xét `getDeclaringClass().isHidden()` trên các frame bị ẩn, cần những option nào? **`SHOW_HIDDEN_FRAMES` và `RETAIN_CLASS_REFERENCE`**.

**Câu 3.** Tại sao `Class.forName(hidden.getName())` thất bại trong khi agent vẫn liệt kê được class? Vì hidden class **không tìm được theo tên thông thường**, nhưng JVM vẫn có đối tượng class và các API enumerate-all có thể thấy nó.

**Câu 4.** Có thể chờ đến sau khi hidden method đã trả về rồi gọi `StackWalker` từ main để xem lại frame cũ không? **Không**. `StackWalker` duyệt stack của thread hiện tại tại lúc gọi; cần chụp stack trong lúc phương thức còn hoạt động hoặc dùng điểm quan sát khác.

**Câu 5.** Một hidden frame hiện ra nhưng không có line number. `SHOW_HIDDEN_FRAMES` có thể tự khôi phục nguồn không? **Không**. Công cụ còn phụ thuộc metadata debug và mapping của hệ thống sinh mã.

## Tài liệu chuẩn còn áp dụng

- Oracle Java SE 26, **`MethodHandles.Lookup#defineHiddenClass`** và tùy chọn `STRONG`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle Java SE 25, **`StackWalker`** (lọc hidden frames mặc định, `getCallerClass`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StackWalker.html
- Oracle Java SE 25, **`StackWalker.Option`** (`SHOW_HIDDEN_FRAMES`, `RETAIN_CLASS_REFERENCE`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StackWalker.Option.html
- Oracle Java SE 25, **`StackWalker.StackFrame`** (`getDeclaringClass`, `getFileName`, `getLineNumber`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StackWalker.StackFrame.html
- Oracle Java SE 26, **`Instrumentation`** (`getAllLoadedClasses` và `getInitiatedClasses`): https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle Java SE 26, **JVM Tool Interface** (`GetLoadedClasses`, `GetClassLoaderClasses`, `GetClassSignature`): https://docs.oracle.com/en/java/javase/26/docs/specs/jvmti.html
- Oracle Java 15 Release Notes, **JEP 371 Hidden Classes** (tên hidden class không phải binary name): https://www.oracle.com/java/technologies/javase/15-relnote-issues.html
- OpenJDK **JEP 371: Hidden Classes**, chuẩn hóa từ Java 15: https://openjdk.org/jeps/371