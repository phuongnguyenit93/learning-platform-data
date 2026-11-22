# Thêm JAR vào đường tìm kiếm không sửa một tham chiếu đã phân giải thất bại trước đó

## 1. Bài toán: helper đã có trong JAR nhưng call site cũ vẫn lỗi

Khi xây Java agent, một giải pháp phổ biến để các class được instrument nhìn thấy helper là nối thêm JAR vào đường tìm kiếm bằng `Instrumentation`:

- `appendToBootstrapClassLoaderSearch(JarFile)`: mở rộng nguồn tìm class của bootstrap loader.
- `appendToSystemClassLoaderSearch(JarFile)`: mở rộng nguồn tìm class của system loader, khi loader này hỗ trợ cơ chế append.

Điều dễ gây ngạc nhiên là: **nếu JVM đã thử phân giải một symbolic reference trong runtime constant pool và lần đó thất bại, việc thêm JAR sau đó không làm lần phân giải kế tiếp của chính reference ấy tự thành công**.

Hãy hình dung:

1. Method `OldCaller.read()` chứa lệnh `invokestatic demo/helper/BridgeHelper.value`.
2. `BridgeHelper` chưa có trên đường tìm kiếm class ở thời điểm method chạy lần đầu.
3. JVM resolve method reference từ constant pool của `OldCaller` và thất bại với `NoClassDefFoundError`.
4. Agent gọi `appendToSystemClassLoaderSearch(helperJar)`.
5. System loader nay có thể tìm được `BridgeHelper`, nhưng **`OldCaller.read()` vẫn nhận lỗi cho symbolic reference cũ**.
6. Một class `NewCaller` có symbolic reference **riêng**, chưa từng thất bại, có thể gọi `BridgeHelper.value()` sau khi JAR được bổ sung.

Đây là điểm trọng tâm: **khả năng tìm thấy class mới** khác với **kết quả đã ghi nhận khi resolve một reference cụ thể**.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt class loading, linking, resolution và initialization.
- Hiểu đúng hợp đồng của hai API append, bao gồm trường hợp system loader không hỗ trợ và việc `java.class.path` không thay đổi.
- Giải thích vì sao `Class.forName` thành công sau append **không** chứng minh lời gọi bytecode đã lỗi trước đó được sửa.
- Xác định phạm vi của “cached failure”: **một symbolic reference trong runtime constant pool**, không phải một lệnh cấm global đối với binary name.
- Lặp lại hiện tượng bằng ví dụ Java 17+ **đã được kiểm thử thực tế** và xây quy trình chuẩn bị helper JAR an toàn cho Java agent.

## 2. Nền tảng JVM: ba hoạt động cần tách biệt

### 2.1. Loading, linking và initialization

| Hoạt động | Bản chất | Kết quả thường thấy |
|---|---|---|
| **Loading** | Class loader tìm bytes và định nghĩa một class có tên cùng defining loader xác định | Có `Class<?>` tương ứng |
| **Linking** | Verify, prepare và resolve các symbolic references theo quy tắc JVM | Đích của class/method/field reference được xác định hoặc báo lỗi |
| **Initialization** | Thực hiện `<clinit>` khi cần khởi tạo class | Static fields/logic được khởi tạo |

**Một class đã load không có nghĩa mọi method reference trong class đó đều được resolve thành công**. JVM có thể thực hiện lazy resolution khi một instruction được dùng hoặc eager resolution theo cách implementation lựa chọn, với ràng buộc thời điểm báo lỗi của đặc tả.

Ví dụ source:

~~~java
package demo.app;

import demo.helper.BridgeHelper;

public final class OldCaller {
    public static String read() {
        return BridgeHelper.value();
    }
}
~~~

Compiler sẽ tạo một method reference đến `demo/helper/BridgeHelper.value:()Ljava/lang/String;` trong constant pool của `OldCaller.class`. Khi bytecode thực hiện `invokestatic`, JVM phải xác định class owner và method đích.

### 2.2. Symbolic reference là một entry cụ thể

Có thể hình dung disassembly như sau (chỉ số `#N` là minh họa, không cố định):

~~~text
Constant pool:
    #N = Methodref demo/helper/BridgeHelper.value:()Ljava/lang/String;

OldCaller.read:
    invokestatic #N
    areturn
~~~

Một biểu diễn đơn giản:

~~~text
OldCaller runtime constant pool
    #N -> Methodref BridgeHelper.value:()String
               |
               v
       JVM resolve symbolic reference
               |
       +-------+--------+
       |                |
    Thành công        Thất bại
       |                |
    Dùng entity       Ghi nhận lỗi
    đã xác định       resolution cho #N
                        |
                        v
                   Gọi lại #N
                    vẫn thất bại
~~~

`JVMS `5.4.3` quy định khi một lần phân giải symbolic reference thất bại, các lần cố phân giải **chính tham chiếu đó** vẫn thất bại với lỗi của lần đầu. Bổ sung JAR không xóa trạng thái này.

### 2.3. “Cùng tham chiếu” không có nghĩa “cùng tên lớp trong cả JVM”

Đây là **một runtime constant-pool entry của một class/interface cụ thể**. Nó không đồng nghĩa:

- Toàn bộ JVM vĩnh viễn bị cấm load `demo.helper.BridgeHelper`.
- Mọi class loader cùng thất bại khi tìm class ấy.
- Mọi class có code `BridgeHelper.value()` đều dùng chung trạng thái resolution.
- Bất kỳ lỗi `ClassNotFoundException` nào từ reflection cũng phải được cache theo đúng quy tắc symbolic-reference resolution.

Hai class `OldCaller` và `NewCaller` có hai constant pools riêng. Dù hai source methods giống nhau, việc một entry trong `OldCaller` đã fail **không tự động làm entry của `NewCaller` fail**.

Cụm “cùng lỗi” trong JVMS là hợp đồng về kết quả resolution; không cần dựa vào việc so sánh `Throwable` bằng `==` hoặc đòi hai lần in ra cùng stack trace/message chính xác trên mọi JVM.

## 3. Cơ chế append JAR và giới hạn của nó

### 3.1. Bootstrap search

~~~java
// Mã minh họa ở trong Java agent có Instrumentation inst.
inst.appendToBootstrapClassLoaderSearch(helperJar);
~~~

Khi bootstrap loader không tìm được một class, các entry từ JAR đã append có thể được tìm tiếp. Nếu append nhiều JAR, thứ tự tra cứu bổ sung dựa trên **thứ tự gọi append**.

Javadoc cảnh báo helper bootstrap JAR nên chứa **chỉ những class/resource cần thiết** cho instrumentation. Một JAR lớn hoặc có class trùng tên với class của loader con có thể bị bootstrap loader định nghĩa trước theo parent delegation, phá class identity, package-private access hoặc cơ chế nestmate. Một tình huống có thể sinh `IllegalAccessError` là loader con mong accessor class thuộc cùng runtime package nhưng class ấy lại bị bootstrap loader định nghĩa. Cần đặt helper trong package riêng, tên độc nhất và kiểm tra contents của JAR.

**Append bootstrap không biến helper thành một named module có quyền truy cập mọi module và không hồi sinh reference đã resolve lỗi trước đó.**

### 3.2. System class loader search

~~~java
// Mã minh họa ở trong Java agent có Instrumentation inst.
inst.appendToSystemClassLoaderSearch(helperJar);
~~~

Method này thêm các JAR entries vào nguồn tìm class của **system loader** khi system loader hỗ trợ cơ chế append dành cho instrumentation. Theo Javadoc Java SE 17:

- Nó có thể được gọi nhiều lần, theo thứ tự JAR bổ sung.
- Nó **không sửa giá trị** `java.class.path` system property.
- Nó có thể ném `UnsupportedOperationException` nếu system loader tùy chỉnh không hỗ trợ.
- Method `appendToClassPathForInstrumentation(String)` trên system loader là một cơ chế hỗ trợ mà API dựa vào; method này không nhất thiết phải `public`.
- Nó không buộc các class đang tồn tại resolve lại method/field/class references đã thất bại.

Hai API nhận `JarFile`, không nhận thư mục classes hoặc một chuỗi classpath tùy ý. Đừng gọi chúng là “thay đổi classpath toàn JVM” theo nghĩa bỏ qua class-loader delegation và module graph.

### 3.3. Bảng phân biệt “mở rộng đường tìm” với “sửa kết quả resolution”

| Trường hợp | Append có thể giúp? | Giải thích |
|---|---|---|
| Search một helper trước đây chưa từng được tìm, sau khi append vào đúng loader | **Có thể** | Loader có thêm nguồn class |
| Call site chưa từng resolve reference, helper mới visible | **Có thể** | Lần resolve đầu tiên có thể thành công |
| Một symbolic reference đã thất bại **trước** append | **Không** | JVMS giữ kết quả thất bại của reference đó |
| Một symbolic reference đã resolve thành công đến class/method cũ | **Không thay entity đã resolve** | Append không thay thế class đã load |
| Custom plugin loader không ủy quyền tới loader được append | **Không bảo đảm** | Phụ thuộc topology loader |
| Named module thiếu quyền đọc/export/open tới helper | **Chưa đủ** | Cần xem JPMS access độc lập |
| Muốn làm lại static initializer đã từng thất bại | **Không** | Đây là trạng thái initialization khác |
| Muốn biến đổi body của method đang chạy | **Không** | Cần Instrumentation redefine/retransform hợp lệ, không phải append |

## 4. Vì sao sau append gọi cũ vẫn thất bại?

Một timeline điển hình:

~~~text
t0. JVM định nghĩa OldCaller.
t1. OldCaller.read() lần đầu dùng Methodref #N.
t2. JVM cố resolve #N; helper chưa tìm được -> lỗi.
t3. Java agent append helper.jar vào system search.
t4. System loader có thể tìm BridgeHelper từ helper.jar.
t5. OldCaller.read() lại dùng chính #N -> vẫn lỗi resolution cũ.
t6. NewCaller.read() có Methodref riêng -> resolve lần đầu thành công.
~~~

**Điểm t4 và điểm t5 trả lời hai câu hỏi khác nhau.** Tại t4, ta hỏi *loader có thể load class này nếu tìm bây giờ không?* Tại t5, ta hỏi *JVM có thử resolve lại cùng reference đã lỗi không?* Theo đặc tả, không.

### Có phải negative cache của class loader?

Không được đồng nhất hai cơ chế:

1. Một số `ClassLoader` tùy chỉnh có thể memoize/negative-cache một tên lớp không tìm thấy. Đó là chi tiết của loader/implementation.
2. JVM Specification có quy tắc riêng về **kết quả resolution của symbolic references trong runtime constant pool**.

Một loader có thể tìm class thành công **sau khi append**, trong khi `OldCaller` dùng reference cũ vẫn lỗi. Đó chính là bằng chứng việc chẩn đoán chỉ dựa vào “loader có đọc thấy JAR hay không” là không đủ.

### `NoClassDefFoundError` khác `ClassNotFoundException`

`ClassNotFoundException` là checked exception thường xuất hiện từ API yêu cầu tìm một class theo tên, ví dụ `Class.forName`. `NoClassDefFoundError` là `LinkageError` có thể xuất hiện khi JVM cần một class definition ở giai đoạn linking/resolution nhưng không có class thích hợp, mặc dù bytecode chứa reference được compile trước đó.

Không nên viết logic production giả định **mọi** `NoClassDefFoundError` đều do thiếu JAR; class init failure cũng có thể khiến class bị đánh dấu lỗi và những lần dùng tiếp theo gặp `NoClassDefFoundError: Could not initialize class ...`. Hãy kiểm tra stack trace, `Caused by` và lần lỗi đầu tiên.

## 5. Thực hành Java 17+: hai call sites và một helper JAR

Thí nghiệm sẽ cho kết quả:

~~~text
OldCaller.read() trước append -> NoClassDefFoundError
Agent append helper.jar        -> append thành công
Class.forName(BridgeHelper)    -> tìm class thành công
OldCaller.read() sau append    -> NoClassDefFoundError
NewCaller.read() sau append    -> READY
~~~

**Vì sao dùng hai caller?** Mỗi class chứa một symbolic method reference trong **constant pool riêng**. Ta cố ý cho reference của `OldCaller` lỗi trước append, rồi kiểm tra reference của `NewCaller` chưa từng được sử dụng trước đó.

Demo dùng **startup agent** để lấy `Instrumentation` sẵn mà không phải attach tới JVM đang chạy. Agent sẽ **chưa append helper trong `premain`**; ứng dụng chủ động gọi API append **sau khi tạo lỗi đầu tiên**. Đây là bố trí thí nghiệm, **không phải chiến lược production được khuyến nghị**.

### 5.1. Cây thư mục

~~~text
resolution-demo/
├── AGENT.MF
├── src/
│   ├── helper/demo/helper/BridgeHelper.java
│   ├── agent/demo/agent/SearchAgent.java
│   └── app/demo/app/
│       ├── OldCaller.java
│       ├── NewCaller.java
│       └── App.java
└── out/
    ├── helper/
    ├── agent/
    ├── app/
    ├── helper.jar
    └── search-agent.jar
~~~

Có **năm tệp Java** và **một manifest**. Tất cả đều dùng API có trong Java 17. Ví dụ đã được biên dịch với `javac --release 17` và chạy trên JDK 24 tương thích; không cần ASM, Byte Buddy hay Attach API.

### 5.2. Tệp `src/helper/demo/helper/BridgeHelper.java`

~~~java
package demo.helper;

public final class BridgeHelper {
    private BridgeHelper() {}

    public static String value() {
        return "READY";
    }
}
~~~

Method static đơn giản cho phép kiểm tra kết quả chính xác, không phụ thuộc trạng thái mutable hoặc I/O. Class này được đóng thành JAR riêng và **chưa có trong runtime classpath ban đầu**.

### 5.3. Tệp `src/app/demo/app/OldCaller.java`

~~~java
package demo.app;

import demo.helper.BridgeHelper;

public final class OldCaller {
    private OldCaller() {}

    public static String read() {
        return BridgeHelper.value();
    }
}
~~~

Với `javac`, method `read()` có symbolic reference tới `demo/helper/BridgeHelper.value:()Ljava/lang/String;`. Build phải đưa helper JAR vào **compile-time classpath** để type-check; nhưng file helper không bắt buộc có trong runtime classpath khi vừa chạy `OldCaller`.

### 5.4. Tệp `src/app/demo/app/NewCaller.java`

~~~java
package demo.app;

import demo.helper.BridgeHelper;

public final class NewCaller {
    private NewCaller() {}

    public static String read() {
        return BridgeHelper.value();
    }
}
~~~

Code giống `OldCaller` ở phương thức `read`, nhưng đây là **class khác** với constant pool khác. Chương trình chỉ gọi `NewCaller.read()` **sau** khi helper JAR đã được append. Ta không dựa vào tên method hay source giống nhau để kết luận chúng chia sẻ reference.

### 5.5. Tệp `src/agent/demo/agent/SearchAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class SearchAgent {
    private static Instrumentation instrumentation;
    private static JarFile keptOpen;

    private SearchAgent() {}

    public static void premain(String arg, Instrumentation inst) {
        instrumentation = inst;
    }

    public static synchronized void append(Path jarPath) throws Exception {
        if (keptOpen != null) {
            throw new IllegalStateException("already appended");
        }

        JarFile jar = new JarFile(jarPath.toFile());
        instrumentation.appendToSystemClassLoaderSearch(jar);
        keptOpen = jar;

        System.out.println("[agent] appended");
    }
}
~~~

Giải thích:

- `premain` lưu `Instrumentation` mà JVM cấp cho agent; **không append ngay** vì bài thực hành cần tạo failure ở `OldCaller`.
- `append(Path)` mở file thật bằng `JarFile` rồi gọi API mở rộng đường tìm cho system loader.
- `keptOpen` giữ tham chiếu tới JAR đã append trong đời sống ngắn của demo; có guard tránh append lặp. Ứng dụng sản xuất cần thiết kế lifecycle và cleanup rõ ràng.
- System loader tùy chỉnh không hỗ trợ append có thể ném `UnsupportedOperationException`. Ví dụ dùng system loader mặc định trên một JDK chuẩn.
- Không cần `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`; ta không sửa classfile nào.

### 5.6. Tệp `src/app/demo/app/App.java`

~~~java
package demo.app;

import demo.agent.SearchAgent;
import java.nio.file.Path;

public final class App {
    private App() {}

    private static void oldCall(String phase) {
        try {
            System.out.println(
                    "[app] " + phase + "=" + OldCaller.read());
        } catch (NoClassDefFoundError error) {
            System.out.println(
                    "[app] " + phase + "=NoClassDefFoundError");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "helper JAR path required");
        }

        // 1) Cố ý gây symbolic-reference resolution failure.
        oldCall("before");

        // 2) Mở rộng search path sau lỗi đầu tiên.
        SearchAgent.append(Path.of(args[0]).toAbsolutePath());

        // 3) Một thao tác tìm class riêng bây giờ có thể thành công.
        System.out.println(
                "[app] load="
                + Class.forName("demo.helper.BridgeHelper").getName());

        // 4) Cùng symbolic reference cũ => vẫn lỗi.
        oldCall("after");

        // 5) Symbolic reference từ class khác => có thể thành công.
        System.out.println(
                "[app] fresh=" + NewCaller.read());
    }
}
~~~

Trong demo, `oldCall` bắt `NoClassDefFoundError` để in một chuỗi ổn định dễ so sánh. **Không sao chép cách nuốt linkage error này vào production.** Nếu application thật ném lỗi, hãy giữ stack trace và cause để biết chính xác vị trí/loại lỗi. Điều kiện bắt ở đây chỉ phục vụ thí nghiệm.

### 5.7. Tệp manifest `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SearchAgent

~~~

Đảm bảo manifest kết thúc bằng newline và `Premain-Class` nằm trong **main section**. `jar cfm` đưa manifest thành `META-INF/MANIFEST.MF` của agent JAR.

### 5.8. Biên dịch theo đúng thứ tự

Tạo các thư mục output từ root `resolution-demo`.

**Bash / macOS / Linux:**

~~~bash
mkdir -p out/helper out/agent out/app
~~~

**PowerShell / Windows:**

~~~powershell
New-Item -ItemType Directory -Force out/helper, out/agent, out/app | Out-Null
~~~

Biên dịch helper, đóng JAR:

~~~bash
javac --release 17 -d out/helper src/helper/demo/helper/BridgeHelper.java
jar cf out/helper.jar -C out/helper .
~~~

Biên dịch agent, đóng JAR với manifest:

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/SearchAgent.java
jar cfm out/search-agent.jar AGENT.MF -C out/agent .
~~~

**Khi biên dịch ứng dụng, cần thấy cả helper JAR và agent JAR.** Dùng dấu `:` trên Unix:

~~~bash
javac --release 17 -cp "out/helper.jar:out/search-agent.jar" -d out/app src/app/demo/app/OldCaller.java src/app/demo/app/NewCaller.java src/app/demo/app/App.java
~~~

Dùng dấu `;` trên Windows:

~~~powershell
javac --release 17 -cp "out/helper.jar;out/search-agent.jar" -d out/app src/app/demo/app/OldCaller.java src/app/demo/app/NewCaller.java src/app/demo/app/App.java
~~~

**Điều kiện bắt buộc của thí nghiệm:** mặc dù có `out/helper.jar` ở **compile-time classpath**, **không thêm nó vào runtime `-cp`** ở bước tiếp theo. Nếu có helper từ đầu, lỗi symbolic resolution ban đầu sẽ không phát sinh.

### 5.9. Chạy đúng runtime classpath

**Bash / macOS / Linux:**

~~~bash
java -javaagent:out/search-agent.jar -cp "out/app:out/search-agent.jar" demo.app.App out/helper.jar
~~~

**Windows:**

~~~powershell
java -javaagent:out/search-agent.jar -cp "out/app;out/search-agent.jar" demo.app.App out/helper.jar
~~~

`out/helper.jar` chỉ là **application argument** để `SearchAgent` mở **sau** failure đầu tiên. Nó **không** nằm trong classpath khi `OldCaller.read()` chạy lần đầu.

**Stdout đã kiểm chứng trên JDK thử nghiệm:**

~~~text
[app] before=NoClassDefFoundError
[agent] appended
[app] load=demo.helper.BridgeHelper
[app] after=NoClassDefFoundError
[app] fresh=READY
~~~

Thực nghiệm đã biên dịch toàn bộ source với `--release 17` và chạy thành công trên JDK 24 (target Java 17). Các dòng trên phản ánh môi trường system class loader mặc định, không được suy diễn thành cam kết với mọi custom class loader, module topology hoặc JVM policy.

### 5.10. Giải mã kết quả

| Dòng | Điều thực sự được chứng minh |
|---|---|
| `before=NoClassDefFoundError` | Reference ở `OldCaller` thất bại khi helper chưa visible |
| `[agent] appended` | API thêm JAR vào system search đã trả về |
| `load=demo.helper.BridgeHelper` | Một yêu cầu class loading riêng sau append đã tìm được helper |
| `after=NoClassDefFoundError` | Reference cũ của `OldCaller` vẫn ở trạng thái thất bại |
| `fresh=READY` | Một reference riêng ở `NewCaller` được resolve thành công sau append |

Hai khẳng định cần tách: **agent JAR đã append thành công** và **đường thực thi cũ đã được chữa**. Chỉ khẳng định thứ nhất từ log `[agent] appended`; các dòng cuối chứng minh điểm gọi cũ **không được chữa**, dù search path đã mở rộng.

## 6. Quan sát symbolic references bằng `javap`

Từ thư mục demo, chạy:

~~~bash
javap -classpath out/app -c -v demo.app.OldCaller
javap -classpath out/app -c -v demo.app.NewCaller
~~~

Tìm:

~~~text
Constant pool:
  #N = Methodref ... demo/helper/BridgeHelper.value:()Ljava/lang/String;
Code:
  invokestatic #N
  areturn
~~~

Số index `#N` thay đổi theo compiler/chi tiết build; đừng hard-code. Mỗi class file có constant pool riêng, dù text của method reference giống nhau.

Để chắc JAR có đúng file:

~~~bash
jar tf out/helper.jar
jar tf out/search-agent.jar
~~~

`helper.jar` phải chứa `demo/helper/BridgeHelper.class`. `search-agent.jar` phải chứa `META-INF/MANIFEST.MF` và `demo/agent/SearchAgent.class`. Kiểm tra artifact thực tế thay vì tin rằng `.java` đã được biên dịch đúng vào JAR.

Nếu có log class loading của HotSpot, dùng `-Xlog:class+load=info` để khảo sát nguồn class; nhưng **class-load log không thể thay thế bằng chứng về resolution failure của một runtime constant-pool entry**.

## 7. Các loại “thành công” và “thất bại” dễ bị lẫn

### 7.1. `Class.forName` thành công không phục hồi `OldCaller`

Sau append, phép thử sau có thể thành công:

~~~java
Class<?> helper = Class.forName(
        "demo.helper.BridgeHelper",
        false,
        ClassLoader.getSystemClassLoader()
);
System.out.println(helper.getName());
~~~

Nó trả lời *loader có thể tìm class bây giờ không?* chứ không thay kết quả resolution trước đó. Overload `initialize=false` tránh **yêu cầu khởi tạo class ngay**, nhưng cũng không làm reset state của JVM.

Ngược lại, nếu `Class.forName` thất bại sau append thì có thể do JAR sai, class entry sai, loader không hỗ trợ append, delegation khác mong muốn hoặc JPMS access. **Chưa thể kết luận** đó là cơ chế cached symbolic reference từ một call site cũ.

### 7.2. Thay system property `java.class.path` không mở class loader search

~~~java
System.setProperty("java.class.path", "another.jar");
~~~

Đó là cập nhật một **system property**, không phải lời gọi Instrumentation API để thay nguồn tìm class. Ngay cả `appendToSystemClassLoaderSearch` thật sự cũng **không thay** giá trị `java.class.path`, theo Javadoc.

Kiểm tra việc append thành công bằng **một lần class loading mới** qua đúng loader, không bằng cách in property.

### 7.3. Symbolic-reference failure khác class initialization failure

Hai tình huống có thể cùng thấy `NoClassDefFoundError` nhưng bản chất khác nhau:

~~~text
Thiếu class khi resolve:
    OldCaller Methodref -> helper chưa load được
    -> lỗi resolution của constant-pool reference
    -> append sau đó không tự re-resolve reference cũ

Class initialization lỗi:
    BridgeHelper đã load
    -> <clinit> ném exception
    -> class ở trạng thái erroneous
    -> lần dùng sau có thể NoClassDefFoundError
    -> append JAR cũng không reset class initialization
~~~

Vì vậy phải giữ **lần lỗi đầu tiên**, `Caused by` và stack trace. Với `ExceptionInInitializerError`/`Could not initialize class`, không nên áp dụng máy móc hướng xử lý “cần thêm JAR”.

### 7.4. Lỗi do method/field hoặc access cũng là resolution

`NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` và các `LinkageError` khác có thể sinh từ symbol/member resolution hoặc access checks. Đính kèm JAR có một class trùng tên **không** làm JVM thay class đã load thành định nghĩa mới. Muốn thay một method body hoặc quyền module phải giải quyết đúng cơ chế tương ứng, và lỗi symbolic reference đã ghi nhận vẫn cần được tính đến.

## 8. Java agent nên chuẩn bị helper **khi nào**?

### 8.1. Startup agent: đúng thứ tự trong `premain`

Một chuỗi đáng tin cậy hơn:

~~~text
JVM khởi động
     |
     v
premain(args, Instrumentation)
     |
     +-- xác định helper JAR nhỏ, đúng nguồn
     +-- append vào bootstrap hoặc system search phù hợp
     +-- chuẩn bị module access / helper visibility nếu cần
     +-- sau đó mới đăng ký transformer
     |
     v
Ứng dụng load các class nghiệp vụ
     |
     +-- transformer phát bytecode gọi helper
     |
     v
Lần đầu resolve reference helper -> class đã visible
~~~

Nếu agent instrument class rồi để bytecode gọi helper **trước** khi JAR helper được append, chính agent có thể tạo ra một resolution failure bền vững. Hãy xem “helper đã sẵn trước lần resolve đầu tiên” là **điều kiện của thiết kế**, không phải chi tiết triển khai có thể tùy ý đảo thứ tự.

### 8.2. Attach agent: còn phải xét class đã load

Trong `agentmain`, nhiều class đã được nạp. Công cụ có thể:

1. Kiểm tra quyền attach/dynamic agent loading và `Instrumentation` hiện có.
2. Append helper JAR vào loader search thích hợp **trước** khi instrument thêm.
3. Xác định loader identity, module readability/exports/opens của class đích.
4. Đăng ký transformer, kiểm tra JVM capability, rồi yêu cầu `retransformClasses` với các class modifiable được chọn nếu cần instrument lớp đã nạp.
5. **Không hứa** một lần retransform/redefine sẽ xóa mọi symbolic-resolution failure cũ. Các API này nhằm thay đổi định nghĩa/biến đổi class dưới giới hạn riêng, không được đặc tả như `clearResolutionErrors()`.

Điều cần phân biệt là **chèn một reference mới vào bytecode sau khi helper visible** khác với **điểm gọi đã có reference cũ và đã fail**. Một instrumentation framework tốt phải phân tích cả hai tình huống.

### 8.3. Bootstrap helper JAR: package và dependency tối thiểu

Một helper dùng bởi bytecode của bootstrap class phải nằm ở loader có thể thấy được. Nhưng bootstrap helper lại không nên phụ thuộc trực tiếp vào thư viện chỉ có trong application loader; nếu helper bootstrap gọi tới class app không visible, bạn có thể tạo `NoClassDefFoundError` ở chiều ngược.

Một thiết kế bridge thường chia thành helper API bootstrap rất nhỏ và implementation ở loader phù hợp. Nếu dùng pattern này, cần kiểm tra method descriptors, loader constraints, module visibility và lifecycle. Package helper phải độc lập để tránh parent-loader collision.

### 8.4. Named modules và quyền truy cập

Append JAR vào system/bootstrap search không tự động làm:

- Named module nhận thêm `requires` hoặc readability tới module chứa helper.
- Package của helper được export/open cho mọi module.
- Class custom loader đổi package identity.
- Class loader khác tự nhìn thấy JAR mà nó không delegate tới.

`Instrumentation.redefineModule(...)` có thể hỗ trợ chỉnh một số quan hệ JPMS khi hợp lệ, nhưng **không có tác dụng hồi tố lên symbolic reference đã resolve thất bại**. JVMS còn nêu ví dụ: một type đã bị từ chối trong bước resolution do package chưa export vẫn thất bại với reference ấy dù export được bổ sung sau đó.

## 9. Cách khắc phục: đừng sửa sai tầng

| Chiến lược | Khi nào hợp lý | Giới hạn |
|---|---|---|
| Đặt helper vào runtime classpath/module path ngay từ startup | Dependency bình thường của ứng dụng | Phải chọn loader và module đúng |
| Append helper trong `premain` trước khi bytecode được instrument sử dụng | Instrumentation helper cần xuất hiện sớm | Không sửa reference đã fail trước `premain` |
| Attach sớm, append helper rồi mới retransform các class được phép | JVM đang chạy, agent có quyền và capability | Đã-fail references không tự được chữa |
| Tạo **class definition/call site mới** trong loader/lifecycle được kiểm soát | Kiến trúc plugin/hot reload hỗ trợ | Đổi class identity và liên quan state/compatibility |
| Khởi động lại với helper sẵn sàng từ đầu | Call site cũ không có cách phục hồi an toàn | Cần kế hoạch restart/rolling deployment |

**Không có một API Java chuẩn “clear cached symbolic reference resolution failure”** để gọi sau khi append. Nếu trạng thái đã hỏng và có yêu cầu correctness nghiêm ngặt, restart với dependency đúng thời điểm thường đáng tin cậy hơn cố gọi `Class.forName` hoặc append nhiều lần.

## 10. Checklist chẩn đoán khi append xong mà vẫn lỗi

1. **Xem lỗi gốc:** `NoClassDefFoundError` do thiếu class, do class initialization hay do resolution tới member? Ghi lại `Caused by` và stack trace đầu tiên.
2. **Kiểm tra thời gian:** reference của call site đã được sử dụng trước khi append hay chưa?
3. **Xem bytecode caller:** dùng `javap -c -v` xác định instruction và class/method/field reference tương ứng.
4. **Kiểm tra defining loader:** tên giống nhau không bảo đảm class identity giống nhau. Xem đúng loader mà caller dùng.
5. **Kiểm tra JAR:** `jar tf` xác nhận binary name và package path trong file.
6. **Kiểm tra append API:** bootstrap hay system? Custom system loader có hỗ trợ append không?
7. **Kiểm tra class lookup mới:** thử qua loader phù hợp để tách vấn đề search path khỏi lịch sử resolution failure.
8. **Kiểm tra điểm gọi mới:** một caller/reference chưa từng fail có thể dùng helper không?
9. **Kiểm tra JPMS:** module reads/exports/opens có đáp ứng không, nhất là class thuộc named module.
10. **Phân biệt log:** `append returned` ≠ `fresh class load succeeded` ≠ `old call site repaired`.
11. **Đánh giá chiến lược phục hồi:** nếu lỗi đã cache, đừng retry vô hạn; cân nhắc restart hoặc thiết kế class mới theo policy.
12. **Kiểm chứng end-to-end:** helper visible chưa đủ; chức năng đã instrument phải thực sự chạy đúng.

Mẫu log tự thiết kế (không phải log chuẩn của JDK):

~~~text
helperJarOpened=true
appendToSystemClassLoaderSearch=returned
freshClassLookup=success
oldCallerResolution=failed
freshCallerResolution=success
~~~

Các trạng thái này cung cấp chứng cứ cho hai trục khác nhau: **class discovery** và **symbolic reference resolution**.

## 11. Những ngộ nhận thường gặp

### Nhầm 1 — “Append JAR sẽ cho JVM thử lại mọi symbolic reference”

Sai. JVM Specification yêu cầu reference đã resolve thất bại tiếp tục thất bại với lỗi cũ. Append thay nguồn tìm class **trong tương lai**, không sửa kết quả resolution đã xác định.

### Nhầm 2 — “`Class.forName` thành công có nghĩa method cũ cũng thành công”

Sai. `Class.forName` là một hoạt động load riêng; method cũ có thể sử dụng constant-pool reference đã fail. Demo cho cả hai kết quả trong cùng process.

### Nhầm 3 — “Một tên class bị lỗi là hỏng trong toàn JVM”

Sai. Quy tắc lỗi ở **symbolic reference cụ thể**. Class khác/loader khác có thể có reference riêng và xử lý khác nhau.

### Nhầm 4 — “`java.class.path` phải đổi sau append”

Sai. Javadoc `appendToSystemClassLoaderSearch` nói rõ không cập nhật property này.

### Nhầm 5 — “Chỉ cần bỏ hết libraries vào bootstrap helper JAR”

Nguy hiểm. Class-name collisions, class loader identity, package-private access và module boundaries có thể bị phá. Helper bootstrap nên tối thiểu và có namespace riêng.

### Nhầm 6 — “`NoClassDefFoundError` lúc nào cũng là class bị thiếu”

Không. Class initialization thất bại, linkage/access errors và các dạng khác cần chẩn đoán riêng. Đừng bỏ qua lỗi đầu và cause.

### Nhầm 7 — “Gọi `retransformClasses` chắc chắn xóa cache lỗi”

Không được đặc tả. Retransformation thay bytecode theo giới hạn; không phải cơ chế reset toàn bộ historical resolution state.

### Nhầm 8 — “Đổi `java.class.path` property tự sửa class loader”

Không. System property không phải lời gọi append, và cũng không xóa trạng thái resolution lỗi.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Nếu `OldCaller` đã resolve thất bại reference tới `Helper`, append JAR helper có làm method ấy tự hết lỗi không?

> Không. JVM Specification `5.4.3` quy định các lần phân giải lại cùng symbolic reference vẫn nhận lỗi từ lần trước.

**Câu 2.** Tại sao `NewCaller` vẫn có thể gọi helper sau append?

> NewCaller có runtime constant pool riêng và reference chưa từng bị resolve thất bại. Sau append, loader có thể tìm helper, nên reference mới có thể thành công.

**Câu 3.** `Class.forName` thành công sau append chứng minh điều gì?

> Chứng minh một yêu cầu tìm class mới qua loader đó đã thành công; không chứng minh reference cũ trong một caller khác đã được reset.

**Câu 4.** Hai API append khác nhau chủ yếu ở điểm nào?

> Một API mở rộng bootstrap search, API còn lại mở rộng system loader search khi system loader hỗ trợ. Cần chọn theo loader visibility của class sẽ sử dụng helper.

**Câu 5.** Sau `appendToSystemClassLoaderSearch`, `java.class.path` tự thay đổi không?

> Không. Javadoc nói rõ API không thay đổi system property này.

**Câu 6.** Có phải mọi lỗi `NoClassDefFoundError` trong production đều là cached resolution failure?

> Không. Có thể có vấn đề class initialization, bytecode dependency, class loader hoặc module khác. Xem cause và lỗi đầu tiên trước khi kết luận.

**Câu 7.** Vì sao helper bootstrap JAR cần namespace độc lập và ít dependency?

> Để giảm nguy cơ class-name collision do parent delegation, type/loader mismatch và `IllegalAccessError` khi các class vốn cần được định nghĩa bởi loader khác.

**Câu 8.** Chiến lược đơn giản nhất để tránh lỗi này ở ứng dụng mới triển khai?

> Đảm bảo helper JAR visible ở đúng loader/module **trước lần symbolic reference được resolve đầu tiên**, thường qua startup classpath hoặc append sớm trong `premain`.

**Câu 9.** Nếu method cũ đã lỗi, có nên liên tục gọi `Class.forName` cho tới khi hết lỗi không?

> Không. `Class.forName` thành công không xóa failure của reference cũ; retry không nhắm đúng trạng thái JVM cần xử lý.

**Câu 10.** Nếu attach agent muộn, vì sao cần thận trọng với helper đã từng bị caller tham chiếu?

> Có thể JVM đã ghi lỗi resolution cho các references đó trước thời điểm agent append helper. Chỉ mở rộng search path không sửa được lịch sử liên kết của call sites ấy.

## 13. Tài liệu chuẩn

- Java SE 17, `Instrumentation` — `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch` và cảnh báo chính thức về references đã resolve thất bại: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- JVM Specification Java SE 17, `5.4.3 Resolution` — quy tắc lưu kết quả symbolic-reference resolution và lỗi của lần đầu: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3
- JVM Specification Java SE 17, `5.3 Creation of Classes and Interfaces` — loader identity, định nghĩa/khởi tạo class: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVM Specification Java SE 17, `5.5 Initialization` — class initialization state khi thất bại: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java SE 17, `ClassLoader` — delegation và loading: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17, `JarFile` — nguồn JAR dùng cho Instrumentation append: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
