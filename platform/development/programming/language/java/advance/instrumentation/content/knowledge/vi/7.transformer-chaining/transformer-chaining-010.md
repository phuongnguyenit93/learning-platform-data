# Gỡ transformer không tự khôi phục các lớp đã được biến đổi

> **Quy tắc quan trọng:** `Instrumentation.removeTransformer(transformer)` **hủy đăng ký transformer để JVM không gửi các yêu cầu biến đổi lớp mới cho đăng ký đó trong tương lai**. Nó **không tự tải lại class, không hoàn nguyên bytecode đã được JVM định nghĩa, không quay ngược những lời gọi trước đó và không gỡ toàn bộ Java agent**. Vì vậy `removeTransformer(...) == true` hoàn toàn có thể đi cùng với việc những object đã tồn tại — và object mới tạo từ **cùng một class đã được định nghĩa** — vẫn chạy mã đã instrument.

Bài này làm rõ chuỗi biến đổi class file trong Java Instrumentation, thời điểm bytecode trở thành định nghĩa đang chạy, ý nghĩa chính xác của `removeTransformer`, cách kiểm chứng bằng Java 17+, và các phương án phục hồi có giới hạn khi thật sự cần thay đổi định nghĩa lớp.

## 1. Transformer không phải là "bộ lọc" giữ bytecode sống liên tục

Một `ClassFileTransformer` là đối tượng mà agent **đăng ký** với JVM. Trong lúc JVM xử lý một class definition hoặc class redefinition/retransformation, JVM gọi `transform(...)` để lấy bytecode đầu ra của từng transformer trong chuỗi.

~~~text
Class bytes đầu vào
       |
       v
Transformer A.transform(...) -- trả bytes A hoặc null
       |
       v
Transformer B.transform(...) -- trả bytes B hoặc null
       |
       v
Transformer C.transform(...) -- trả bytes C hoặc null
       |
       v
JVM kiểm tra và định nghĩa/áp dụng class từ kết quả cuối
       |
       v
Method được thực thi theo định nghĩa class đã được áp dụng
~~~

Trong chuỗi này:

- **`return null`** từ một transformer nghĩa là **transformer đó không yêu cầu thay đổi** bytes đầu vào ở lượt gọi ấy. Nó không yêu cầu JVM "khôi phục nguyên bản", và cũng không xóa những thay đổi do transformer trước tạo ra.
- **`return byte[]`** yêu cầu JVM dùng class bytes mới làm đầu vào cho transformer tiếp theo hoặc để định nghĩa class. Mảng trả về phải biểu diễn class hợp lệ, đúng tên và phù hợp giới hạn thay đổi.
- Sau khi JVM đã định nghĩa `Greeting` với method `text()` trả `"INSTRUMENTED"`, mã đó trở thành **định nghĩa đang chạy** của class. JVM không cần gọi lại transformer mỗi khi method `text()` được gọi.
- **Gỡ đăng ký** chỉ sửa danh sách callback mà JVM tham khảo ở những hoạt động biến đổi tiếp theo. JVM không tự giữ một "undo stack" dành riêng cho `removeTransformer`.

Ví dụ một agent biến đổi method `calculate()` để thêm log vào đầu phương thức. Sau khi lớp được định nghĩa, lời gọi `calculate()` chạy phiên bản đã thêm log. Bỏ transformer khỏi danh sách callback **không loại bỏ câu lệnh log đã nằm trong định nghĩa đó**.

## 2. Hợp đồng chính xác của `removeTransformer`

Phương thức trong Java 17+:

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

Đây là **đoạn minh họa**, giả sử `inst` là `Instrumentation` JVM truyền vào `premain` hoặc `agentmain`; `transformer` là chính đối tượng đã được đăng ký bằng `inst.addTransformer(...)`.

| Quan sát / hành động | Hợp đồng của API | Không nên suy ra |
| --- | --- | --- |
| `removeTransformer(t) == true` | Một đăng ký tương ứng với `t` đã được tìm thấy và hủy | Các class từng bị `t` biến đổi đã trở về bytes cũ |
| `removeTransformer(t) == false` | Không tìm thấy đăng ký tương ứng để hủy | Các class trước đây chắc chắn không bị instrument |
| Gọi `removeTransformer(null)` | Ném `NullPointerException` | `null` là cách xóa mọi transformer |
| Cùng instance `t` được đăng ký nhiều lần | Một lời gọi xóa **lần đăng ký khớp gần nhất** | Một lần gọi tự xóa toàn bộ đăng ký trùng |
| Một thread đang định nghĩa lớp trong khi thread khác vừa remove | Callback **có thể vẫn xảy ra sau thời điểm remove** do tính đồng thời | Remove hoạt động như hàng rào dừng tức thì mọi callback |
| Agent đã tạo thread, logger, exporter hay hook khác | Chúng **không tự dừng** chỉ vì transformer bị remove | Agent đã được unload khỏi JVM |

Theo Javadoc, `removeTransformer` dùng để **unregister**. Nó không nhận `Class<?>` đích, không nhận bytes gốc, không yêu cầu JVM retransform/redefine, và không trả về thông tin về class nào đã bị biến đổi trước đó.

**Chú ý việc gọi nhiều lần:** JVM cho phép đăng ký cùng một transformer nhiều lần nhưng không khuyến khích. Tránh tạo các đăng ký trùng; giữ rõ ownership của từng instance. Nếu đã đăng ký trùng và muốn xóa hết, cần xử lý các lần đăng ký còn lại thay vì chỉ dựa vào một giá trị `true`.

**Chú ý callback chạy song song:** Ở hệ thống có class loading đồng thời, việc `removeTransformer` trả về không chứng minh không còn callback đang thực thi hoặc đã xếp lịch. Code transformer nên đủ an toàn để xử lý callback muộn và không dùng boolean `removed` làm giả định tuyệt đối rằng không bao giờ bị gọi nữa.

## 3. Ba nhóm class sau khi remove

Hãy tách **thời điểm JVM đã định nghĩa class** khỏi **thời điểm agent hủy đăng ký**.

| Class/tình huống | Trước khi gỡ | Sau khi gỡ nếu không có thao tác đặc biệt khác |
| --- | --- | --- |
| `A` đã được định nghĩa qua transformer, method được thay bytes | `A` chạy phiên bản đã transform | **`A` tiếp tục chạy phiên bản đó**; object cũ và object mới dùng cùng định nghĩa |
| `B` chưa được định nghĩa khi transformer bị gỡ | Chưa có `Class<?>` của `B` | Khi định nghĩa `B`, **transformer đã gỡ không tham gia**; các transformer còn đăng ký vẫn có thể tham gia |
| `C` vốn đã định nghĩa trước lúc agent đăng ký | Class `C` chạy định nghĩa cũ | Remove không đổi `C`; nó cũng không làm phát sinh một lần transform hồi tố |
| `A` sau đó được yêu cầu `retransformClasses` hoặc `redefineClasses` | Đã tồn tại class đã instrument | **Định nghĩa có thể thay đổi** do yêu cầu mới; kết quả tùy bytes nền, capability và các transformer còn hiệu lực |

Sơ đồ thời gian:

~~~text
T0: agent.addTransformer(T)
T1: JVM load A -> T biến đổi bytes -> A đã định nghĩa với instrumentation
T2: JVM chạy A.method() -> instrumentation hoạt động
T3: agent.removeTransformer(T) -> callback registration của T bị gỡ
T4: JVM chạy A.method() -> instrumentation trong A vẫn hoạt động
T5: JVM load B -> T đã gỡ không được gọi cho B
T6: [tùy chọn] redefine/retransform A có kiểm soát -> A có thể đổi định nghĩa
~~~

Một đối tượng Java được tạo bằng `new A()` **không khiến JVM định nghĩa lại class `A`** mỗi lần. Đó là lý do tạo một instance mới sau remove **không** làm tác dụng của bytecode transformation mất đi. Tương tự, gọi lại method không phải một lần gọi `ClassFileTransformer.transform(...)`.

## 4. Thí nghiệm Java 17+: gỡ transformer, bytecode cũ vẫn tồn tại

Ví dụ dưới đây **thực sự thay class bytes**: agent thay bytes định nghĩa `Greeting` bằng một phiên bản khác có cùng tên class và cùng cấu trúc, nhưng method `text()` trả chuỗi khác. Agent cũng có khả năng biến đổi `LaterGreeting`; ta chỉ nạp class này **sau khi đã remove transformer**, nên nó vẫn có hành vi ban đầu.

Sau đó, chương trình gọi **`redefineClasses` một cách tường minh** với bytes gốc của `Greeting`. Bước riêng này cho thấy một trường hợp có thể khôi phục method **khi được chủ động yêu cầu** — không phải kết quả tự động của remove.

Thí nghiệm cần một JDK 17+ có `javac`, `jar` và `java`, sử dụng các lệnh có sẵn trong JDK. Không cần thư viện bytecode ngoài. JVM phải hỗ trợ `redefineClasses` để chạy **bước phục hồi cuối**; HotSpot/OpenJDK thông thường hỗ trợ khi agent khai báo capability tương ứng.

### 4.1. Tạo `SwapTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.Map;

public final class SwapTransformer implements ClassFileTransformer {
    private final Map<String, byte[]> replacements;

    public SwapTransformer(Map<String, byte[]> replacements) {
        this.replacements = replacements;
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
        byte[] replacement = replacements.get(className);
        if (replacement == null) {
            return null;
        }
        System.out.println("transform=" + className);
        return replacement.clone();
    }
}
~~~

Đây là transformer chủ ý đơn giản: chỉ thay bytes cho hai tên class `Greeting` và `LaterGreeting` (không có package). Với dự án thật có package, `className` dùng JVM internal name, ví dụ `demo/Greeting`, không phải `demo.Greeting`.

`replacements` là các class files được biên dịch sẵn, **không** phải bytecode được sinh tại runtime. `clone()` tạo mảng trả về riêng, tránh lỡ sửa vùng bytes được giữ lại để dùng ở lần khác. Transformer trả `null` với những class ngoài phạm vi.

**Giới hạn của ví dụ:** Hai phiên bản class có cùng tên và cấu trúc; chỉ khác phần thân method. Đừng áp dụng kiểu "thay toàn bộ `byte[]`" vào bất kỳ class production nào mà không xác thực class file, class loader, dependency, cấu trúc, security và tính tương thích với transformer khác.

### 4.2. Tạo `SwapAgent.java`

~~~java
import java.io.IOException;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public final class SwapAgent {
    private static Instrumentation instrumentation;
    private static SwapTransformer transformer;

    public static void premain(String args, Instrumentation inst) throws IOException {
        Map<String, byte[]> replacements = Map.of(
            "Greeting", Files.readAllBytes(Path.of("variant/Greeting.class")),
            "LaterGreeting", Files.readAllBytes(Path.of("variant/LaterGreeting.class"))
        );
        instrumentation = inst;
        transformer = new SwapTransformer(replacements);
        inst.addTransformer(transformer);
        System.out.println("agent=registered");
    }

    public static void remove() {
        System.out.println("remove=" + instrumentation.removeTransformer(transformer));
        System.out.println("remove-again=" + instrumentation.removeTransformer(transformer));
    }

    public static void restore(Class<?> type, Path original) throws Exception {
        if (!instrumentation.isRedefineClassesSupported()
                || !instrumentation.isModifiableClass(type)) {
            throw new IllegalStateException("Class redefinition unsupported");
        }
        instrumentation.redefineClasses(
                new ClassDefinition(type, Files.readAllBytes(original)));
        System.out.println("explicit-redefine=complete");
    }
}
~~~

Bốn điểm thiết yếu của agent này:

1. `premain` đọc **bytes thay thế** trước khi đăng ký, nên callback chỉ tra cứu map và không thực hiện đọc file trên mỗi lần nạp lớp.
2. `addTransformer(transformer)` tương đương đăng ký với `canRetransform=false`; capability này **không bắt buộc** cho initial class load.
3. `remove()` gọi hai lần với **cùng instance** để cho thấy kết quả `true` ở lần đầu, `false` khi không còn đăng ký.
4. `restore(...)` **là một thao tác riêng**, dùng `redefineClasses` sau khi kiểm tra support và class modifiability. Nó không được `removeTransformer` tự gọi.

Agent không xóa hoặc gỡ thư viện/agent JAR; nó chỉ xóa đăng ký transformer của chính mình. `Instrumentation` vẫn có thể được dùng cho thao tác mà JVM hỗ trợ.

### 4.3. Hai class ban đầu

**`Greeting.java`** trong thư mục gốc:

~~~java
public final class Greeting {
    public String text() {
        return "ORIGINAL";
    }
}
~~~

**`LaterGreeting.java`** trong thư mục gốc:

~~~java
public final class LaterGreeting {
    public String text() {
        return "LATER_ORIGINAL";
    }
}
~~~

Cả hai có cùng mô hình: method Java `text()` trả chuỗi cố định. Chúng dùng để tạo lớp ban đầu mà ứng dụng sẽ nạp từ classpath.

### 4.4. Hai class thay thế, cùng tên nhưng khác nội dung method

**`variant/Greeting.java`** trong thư mục con `variant`:

~~~java
public final class Greeting {
    public String text() {
        return "INSTRUMENTED";
    }
}
~~~

**`variant/LaterGreeting.java`** trong thư mục con `variant`:

~~~java
public final class LaterGreeting {
    public String text() {
        return "LATER_INSTRUMENTED";
    }
}
~~~

Các tên class lặp lại là **có chủ đích**. Ta sẽ biên dịch hai file variant sang thư mục riêng và chỉ đọc bytes `.class` ở đó từ agent. **Không** đưa cả hai phiên bản `Greeting.class` vào cùng vị trí của classpath hoặc đóng gói variant như class ứng dụng.

`LaterGreeting` có phương án biến đổi được chuẩn bị trước, nên khi ứng dụng in `LATER_ORIGINAL` sau remove, đó là bằng chứng rõ rằng transformer đã không tham gia vào lần định nghĩa class muộn này.

### 4.5. Ứng dụng điều khiển vòng đời

**`DemoApp.java`**:

~~~java
import java.nio.file.Path;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        Greeting first = new Greeting();
        System.out.println("first=" + first.text());

        SwapAgent.remove();
        System.out.println("same-instance=" + first.text());
        System.out.println("new-instance=" + new Greeting().text());

        System.out.println("later=" + new LaterGreeting().text());

        SwapAgent.restore(Greeting.class, Path.of("Greeting.class"));
        System.out.println("after-explicit-redefine=" + first.text());
    }
}
~~~

Thứ tự này quan trọng:

- Tạo `Greeting` **trước** khi remove, buộc JVM định nghĩa class lần đầu lúc transformer còn đăng ký.
- Gỡ transformer, rồi gọi method trên **instance cũ và instance mới** để kiểm tra định nghĩa class vẫn còn.
- Lần đầu sử dụng `LaterGreeting` xảy ra **sau** khi remove.
- Cuối cùng cung cấp original class-file bytes cho `redefineClasses` để tạo một lần phục hồi **tường minh**.

### 4.6. Manifest startup agent

**`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: SwapAgent
Can-Redefine-Classes: true
~~~

Lưu file manifest có dấu xuống dòng ở cuối (có thể thêm dòng trống). `Premain-Class` khiến JVM gọi `SwapAgent.premain` lúc khởi động bằng `-javaagent`.

`Can-Redefine-Classes: true` chỉ cần cho bước **restore bằng `redefineClasses`** của bài; nó không bắt buộc đối với `addTransformer`/`removeTransformer`. Khai báo `true` vẫn cần JVM thực sự hỗ trợ, nên code kiểm tra `isRedefineClassesSupported()`.

### 4.7. Biên dịch, đóng gói, thực thi

Từ thư mục gốc đang chứa `SwapTransformer.java`, `SwapAgent.java`, `Greeting.java`, `LaterGreeting.java`, `DemoApp.java`, `agent.mf` và thư mục con `variant` chứa hai source variant, thực hiện:

~~~bash
javac --release 17 SwapAgent.java SwapTransformer.java Greeting.java LaterGreeting.java DemoApp.java

javac --release 17 -d variant variant/Greeting.java variant/LaterGreeting.java

jar --create --file swap-agent.jar --manifest agent.mf SwapAgent.class SwapTransformer.class

java -javaagent:swap-agent.jar -cp . DemoApp
~~~

Dùng JDK 17 trở lên để biên dịch `--release 17`. Lệnh trong ví dụ có cú pháp JDK chuẩn, chạy từ đúng thư mục bài thực hành trên Bash/CMD/PowerShell. `variant/Greeting.class` và `variant/LaterGreeting.class` chỉ được agent đọc như dữ liệu. JAR agent chứa **cả `SwapAgent.class` và `SwapTransformer.class`**, tránh lỗi thiếu lớp phụ thuộc.

**Stdout của ví dụ trên trong JVM hỗ trợ redefine:**

~~~text
agent=registered
transform=Greeting
first=INSTRUMENTED
remove=true
remove-again=false
same-instance=INSTRUMENTED
new-instance=INSTRUMENTED
later=LATER_ORIGINAL
explicit-redefine=complete
after-explicit-redefine=ORIGINAL
~~~

Kết quả được kiểm tra bằng `javac --release 17` và chạy thực tế trên OpenJDK 21. Tùy JVM/JDK, bước redefine cuối có thể không được hỗ trợ; khi đó code phát sinh `IllegalStateException` với thông điệp rõ và **phần chứng minh remove ở các dòng trước vẫn hợp lệ**.

### 4.8. Đọc kết quả theo sự kiện

| Dòng stdout | Bằng chứng |
| --- | --- |
| `agent=registered` | Transformer đã được đăng ký trong `premain` |
| `transform=Greeting` | JVM lần đầu định nghĩa `Greeting`, transformer đã trả bytes thay thế |
| `first=INSTRUMENTED` | Class đang chạy với code từ `variant/Greeting.class` |
| `remove=true` | Đăng ký transformer đã được tìm thấy và gỡ |
| `remove-again=false` | Lần gọi remove thứ hai không còn đăng ký đó |
| `same-instance=INSTRUMENTED` | **Gỡ đăng ký không khôi phục định nghĩa của class đã load** |
| `new-instance=INSTRUMENTED` | `new Greeting()` không định nghĩa lại class; đối tượng mới dùng method đã thay |
| `later=LATER_ORIGINAL` | `LaterGreeting` được định nghĩa sau remove, không bị transformer cũ thay bằng variant |
| `explicit-redefine=complete` | Ứng dụng chủ động yêu cầu một lần redefine riêng với bytes gốc |
| `after-explicit-redefine=ORIGINAL` | Chỉ **sau lần redefine tường minh**, method của `Greeting` trở về phần thân gốc trong ví dụ |

Điểm phân biệt cốt lõi nằm giữa hai dòng `remove=true` và `after-explicit-redefine=ORIGINAL`. **Câu lệnh remove và câu lệnh restore là hai thao tác khác nhau**, cả về ý định lẫn cơ chế JVM.

## 5. Tại sao `removeTransformer` không phải thao tác "undo"?

Khi JVM định nghĩa class, nó có một **kết quả class-file cuối** sau khi các transformer được gọi. Method bytecode từ kết quả này được JVM dùng để thực thi. Danh sách transformer phục vụ **những lần xử lý class tiếp theo**; không phải bảng ánh xạ từ từng instruction đã chạy về một transformer cần được hoàn tác khi xóa nó.

Hãy hình dung các bước sau:

~~~text
A.class đầu vào:   bytecode gốc
     |
     v
Transformer A:     thêm đo thời gian
     |
     v
Transformer B:     thêm ghi log
     |
     v
JVM định nghĩa A:  bytecode đo thời gian + log
     |
     v
removeTransformer(A)
     |
     v
JVM hiện vẫn có:   bytecode đo thời gian + log
~~~

Gỡ `Transformer A` không đủ thông tin để biết **instruction nào** do nó tạo ra, instruction nào do `Transformer B` hoặc compiler tạo ra, hay cách bỏ chúng mà vẫn giữ class hợp lệ. Tương tự, gỡ `Transformer B` không có nghĩa có thể giữ phần A và xóa sạch phần B bằng một lệnh remove.

Trong trường hợp nhiều transformer, kết quả còn phụ thuộc thứ tự đăng ký và các lớp được nạp ở những thời điểm khác nhau. Không có lời hứa rằng trạng thái JVM sau remove tương đương với một JVM chưa từng cài transformer đó.

**Phân biệt ba khái niệm:**

- **Unregister:** `removeTransformer` thay đổi danh sách callback đăng ký với `Instrumentation`.
- **Replace definition:** `redefineClasses` đưa class-file bytes khác vào cho class đã định nghĩa; JVM và các transformer còn đăng ký tham gia xử lý theo hợp đồng.
- **Rerun transformation:** `retransformClasses` xử lý lại class từ bytes nền, tái áp dụng kết quả của nhóm transformer không hỗ trợ retransformation và gọi lại nhóm có hỗ trợ. Đây cũng là **yêu cầu chủ động**, không phải bước tự động sau remove.

## 6. Muốn thực sự phục hồi hành vi, có những lựa chọn nào?

### 6.1. Dừng việc đo đạc bằng cờ bật/tắt trong bytecode đã chèn

Nếu mục tiêu là **ngừng log/metric, không bắt buộc khôi phục bytes y hệt**, một agent có thể chèn wrapper đọc cờ cấu hình:

~~~java
// Minh họa phần thân method SAU KHI instrumentation.
// Không phải class Java độc lập có thể chạy vì thiếu định nghĩa flags và businessLogic().
public Result execute(Request req) {
    if (!FeatureFlags.isInstrumentationEnabled()) {
        return businessLogic(req);
    }
    long start = System.nanoTime();
    try {
        return businessLogic(req);
    } finally {
        Metrics.record(System.nanoTime() - start);
    }
}
~~~

Giải pháp này cần được thiết kế **ngay lúc instrumentation**: tắt flag làm method đã chèn trở thành no-op cho phần đo đạc, nhưng bytecode wrapper vẫn tồn tại, và vẫn có chi phí kiểm tra flag. Đảm bảo class loader của ứng dụng nhìn thấy class chứa flag và các thay đổi thread-safe.

### 6.2. Redefine với class-file bytes thích hợp

Ví dụ `SwapAgent.restore` minh họa:

~~~java
if (inst.isRedefineClassesSupported() && inst.isModifiableClass(targetClass)) {
    inst.redefineClasses(new ClassDefinition(targetClass, originalBytes));
}
~~~

Đây chỉ là **mảnh code API** nằm trong agent có `Instrumentation inst`, `Class<?> targetClass` và `byte[] originalBytes`; không phải file Java độc lập. Khi class structure vẫn tương thích và không có transformer khác sửa lại bytes, redefine có thể phục hồi method body như bài thực hành.

Nhưng trong production có các giới hạn:

- **Phải có bytes gốc đáng tin cậy.** Không tùy tiện lấy file `.class` mới nhất trên đĩa và coi nó chắc chắn tương đương class đã định nghĩa: class loader, class version, shading, build, module và các lần redefine trước có thể khác.
- **Không được thay đổi cấu trúc tùy ý.** Redefine/retransform có giới hạn với việc thêm/xóa field hoặc method, sửa chữ ký và quan hệ kế thừa. Nếu instrumentation ban đầu chèn thêm method/field, việc quay về một class file không có chúng có thể bị JVM từ chối.
- **Các transformer còn đăng ký có thể biến đổi lại.** Bytes đầu vào của redefine đi qua chuỗi transformer tương ứng. Nếu muốn rollback một tác dụng cụ thể phải kiểm soát **toàn bộ chuỗi**, không chỉ transformer của mình.
- **Class có thể không sửa được.** Kiểm tra `isRedefineClassesSupported()` và `isModifiableClass(clazz)`; xử lý lỗi đúng loại như `UnmodifiableClassException`, `UnsupportedOperationException` hoặc `ClassFormatError`.
- **Đối tượng và thread đang chạy không bị "quay ngược".** Instance hiện có vẫn là chính nó; stack frame đang chạy có thể tiếp tục bytecode cũ, còn những invocation mới dùng định nghĩa mới. Static initializer không tự chạy lại và dữ liệu runtime không được tự hoàn tác.

Vì vậy, lời nói **"redefine lúc nào cũng restore nguyên trạng"** là sai. Trong bài thực hành, điều này thành công vì chỉ đổi phần thân của một method, dùng đúng bytes gốc và không có transformer khác tiếp tục sửa class sau remove.

### 6.3. Retransform theo capability và tình trạng chain thực tế

`retransformClasses(Class<?>...)` là lựa chọn khác nếu agent khai báo `Can-Retransform-Classes: true`, JVM hỗ trợ, và lớp được phép sửa. Điểm khác với redefine: JVM tái dựng chuỗi từ **class-file bytes nền** của định nghĩa ban đầu hoặc lần redefine gần nhất; nó không cần caller cung cấp một classfile tùy chọn.

Nhưng kết quả còn phụ thuộc:

- Transformer đăng ký với `canRetransform=false` vẫn có thể **được tái áp dụng kết quả cũ** trong một lần retransform; callback của nó không được gọi lại. Do đó, **chỉ thấy không có callback không chứng minh tác dụng bytecode đã mất**.
- Transformer đăng ký với `canRetransform=true` được gọi lại; có thể thêm hoặc không thêm instrumentation theo cấu hình hiện tại.
- Nếu transformer đã được remove, một lần retransform chủ động có thể cho ra định nghĩa khác, nhưng **không có hợp đồng "tự restore mọi thay đổi trước đây"**. Các transformer khác, bytes nền và lần redefine trước vẫn có thể giữ hành vi instrument.
- Việc thêm hoặc bỏ method/field trong quá trình retransform cũng chịu các giới hạn thay đổi cấu trúc; không dùng retransform như cách bảo đảm rollback mọi kiểu biến đổi.

Không gọi `retransformClasses` chỉ để đoán kết quả ở production: hãy thiết kế thử nghiệm, kiểm tra capability, kiểm tra class modifiability, triển khai trên tập class nhỏ và xác nhận ngữ nghĩa sau thay đổi.

### 6.4. Khởi động lại JVM không có agent

Khi cần quay về trạng thái chạy **sạch** và không thể chứng minh tính đúng đắn của rollback runtime, tái khởi động ứng dụng mà không có `-javaagent` tương ứng thường là lựa chọn vận hành dễ kiểm soát hơn. Khi đó JVM mới định nghĩa lại các class từ bộ artifact được chọn và không có transformer đã gỡ tham gia, với điều kiện không còn agent/cấu hình khác có tác dụng tương tự.

**Restart là một quy trình deployment**, không phải chức năng của `removeTransformer`; cần cân nhắc tính sẵn sàng, dữ liệu phiên, trạng thái hệ thống và đường rollback phù hợp.

## 7. Các lỗi kỹ thuật và chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách xác minh |
| --- | --- | --- |
| `removeTransformer(t) == true` nhưng log đo đạc vẫn xuất hiện | Log đã được chèn **vào bytecode của lớp đã load** | Xem trạng thái class đang chạy, phân biệt callback-time log với method-execution log |
| Tạo object mới mà vẫn thấy instrumentation | Object mới dùng cùng `Class<?>` đã định nghĩa | Kiểm tra loader, tên class và thời điểm first definition |
| `removeTransformer(t) == false` | Đã remove, chưa từng add, hoặc truyền sai instance | Giữ reference transformer duy nhất, theo dõi đăng ký/tháo đăng ký |
| Sau remove vẫn thấy callback `transform` xuất hiện | Lời gọi đã bắt đầu trước/đồng thời với remove; hoặc instance được đăng ký nhiều lần | Kiểm tra concurrent class loading và lần đăng ký gần nhất; tránh kết luận JVM vi phạm hợp đồng |
| Lớp mới sau remove vẫn bị transform | Transformer khác vẫn đăng ký hoặc một đăng ký trùng của cùng instance chưa bị xóa | Liệt kê ownership của agent/transformer và chuỗi đang hoạt động |
| Redefine bằng bytes gốc thất bại | Class bytes sai tên/version, cấu trúc không tương thích, JVM/class không cho sửa, transformer khác làm lỗi | Kiểm tra `isRedefineClassesSupported`, `isModifiableClass`, lỗi root cause và classfile thực |
| Retransform nhưng không thấy callback `canRetransform=false` | JVM tái dùng kết quả transformer incapable mà không gọi callback | Đối chiếu API `addTransformer(..., false)` và quy tắc retransform |
| Ngừng exporter nhưng ứng dụng vẫn log qua wrapper | Có instrumentation trong class hoặc hook khác còn hoạt động | Phân biệt resource cleanup, callback registration và bytecode đang thực thi |

**Cách thu thập bằng chứng rõ ràng:** ghi sự kiện `addTransformer`/`removeTransformer` cùng mã định danh instance, `ClassLoader`/tên class được transform, thời điểm class definition, và request redefine/retransform. Đừng đồng nhất log "transformer removed" với log "class definition restored".

Với các hệ thống nhiều agent, một request `redefineClasses` có thể đi qua **cả các transformer còn lại**, làm output khác original. Ngoài ra, nếu transformer đã chèn lời gọi đến class helper của agent, gỡ transformer không gỡ helper: cố unload các helper hoặc class loader trong khi bytecode đang gọi chúng có thể gây `NoClassDefFoundError` hoặc lỗi linkage.

## 8. Thiết kế cơ chế vô hiệu hóa/cleanup an toàn

Một agent production nên phân biệt ba cấp độ vận hành:

1. **Dừng nhận những callback mới:** gọi `removeTransformer(t)`; xử lý kết quả và việc callback đang chạy song song.
2. **Dừng các tài nguyên do agent tự tạo:** tắt background worker/scheduler, flush queue telemetry có giới hạn, đóng exporter, bỏ listener/hook riêng khi phù hợp. `removeTransformer` không làm những việc này.
3. **Đổi hành vi class đã instrument:** bật/tắt nhánh đo đạc có thiết kế sẵn, hoặc dùng `redefineClasses`/`retransformClasses` khi đã kiểm chứng tính tương thích, hoặc triển khai JVM mới không có agent.

Nếu transformer của bạn giữ một `volatile boolean active` để dừng logic callback mới, cách đó **không làm bytecode đã cài biến mất**. Nó chỉ khiến callback về sau quyết định không trả thêm bytes; chính JVM vẫn dùng class definitions hiện hữu cho tới khi có yêu cầu biến đổi class khác.

### Quy tắc kiểm thử khi tắt agent

- Chuẩn bị hai class cùng cấu trúc như bài thực hành: một class **load trước remove**, một class **load sau remove**.
- Xác nhận class đầu tiên vẫn có hành vi đã biến đổi sau remove; class thứ hai không chịu biến đổi của transformer vừa gỡ.
- Test lặp `removeTransformer` nhận `false`; test dùng sai instance và đăng ký trùng nếu dự án có nguy cơ đó.
- Test concurrency: cho nhiều thread nạp class hoặc kích hoạt class load khi remove, bảo đảm callback xử lý an toàn nếu tới muộn.
- Nếu có "restore" runtime, test với **đúng JDK, class loader, module và toàn bộ chuỗi transformer**, không chỉ một class mẫu.
- Test failure mode: bytes gốc thiếu/không hợp lệ, unsupported redefine/retransform, class không modifiable, rollback không đầy đủ.
- Đo overhead và kiểm tra dữ liệu telemetry ở trạng thái disabled. "Không còn callback" không đồng nghĩa "không còn overhead của wrapper".

## 9. Câu hỏi kiểm tra hiểu biết

**Câu 1.** Một transformer thêm `System.out.println("trace")` vào `OrderService.submit()` lúc class định nghĩa. Sau đó `removeTransformer` trả `true`. Lời gọi tiếp theo của `submit()` có còn in `trace` không?

**Đáp án:** Có thể vẫn in, vì lời gọi đi qua method bytecode đã sửa. Xóa đăng ký transformer không tự thay lại method body.

**Câu 2.** Sau remove, `new OrderService()` có tự lấy bytecode nguyên bản không?

**Đáp án:** Không. Nếu vẫn là **cùng `Class<?>`**, object mới dùng định nghĩa hiện tại của class, không định nghĩa lại nó.

**Câu 3.** Vì sao `removeTransformer` có thể trả `true` rồi một callback khác vẫn xuất hiện ngay sau đó?

**Đáp án:** Vì class loading/transform có thể xử lý đồng thời; Javadoc cho phép callback đã chạy hoặc có liên quan đến lần xử lý đang diễn ra tới muộn. Ngoài ra, cùng instance được đăng ký nhiều lần sẽ còn đăng ký khác.

**Câu 4.** Trong demo, hành vi `Greeting.text()` trở về `"ORIGINAL"` tại thời điểm nào?

**Đáp án:** Sau **`SwapAgent.restore(...)`**, khi một lần `redefineClasses` tường minh áp dụng bytes gốc. Không phải khi `removeTransformer` trả `true`.

**Câu 5.** `retransformClasses` luôn khôi phục class về nguyên bản trước mọi agent?

**Đáp án:** Không. Nó tái xây dựng từ bytes nền và quy tắc của các transformer, bao gồm cơ chế tái áp dụng kết quả của transformer incapable còn đăng ký. Nguồn bytes, lịch sử redefine, transformer khác và giới hạn cấu trúc có thể khiến kết quả khác.

### Tài liệu chuẩn

- [Java SE 17 — `Instrumentation.removeTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#removeTransformer(java.lang.instrument.ClassFileTransformer)): giá trị trả về, xóa lần đăng ký khớp gần nhất và callback đồng thời.
- [Java SE 17 — `Instrumentation.retransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)): bytes nền, transformer capable/incapable và giới hạn thay định nghĩa.
- [Java SE 17 — `Instrumentation.redefineClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): cung cấp class-file bytes thay thế, quyền sửa class và ảnh hưởng lên frames/instances.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): chuỗi transformer, kết quả `null`/`byte[]` và thời điểm JVM gọi callback.
