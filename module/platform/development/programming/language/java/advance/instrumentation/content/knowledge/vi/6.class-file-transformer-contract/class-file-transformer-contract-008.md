# Phân biệt định nghĩa lần đầu với redefine hoặc retransform qua ngữ cảnh callback

> **Ý chính:** Trong `ClassFileTransformer.transform(...)`, tham số `Class<?> classBeingRedefined` là dấu hiệu đáng tin cậy để phân biệt **định nghĩa lớp lần đầu** với **xử lý lại lớp đã định nghĩa**: `null` khi lớp đang được định nghĩa lần đầu; **khác `null`** khi JVM đang **redefine hoặc retransform**. Tuy nhiên, **chỉ giá trị này không phân biệt được hai thao tác `redefine` và `retransform`**: cả hai đều truyền đối tượng `Class<?>`. Muốn giải thích đúng callback, cần thêm ngữ cảnh về API khởi phát thao tác, capability `canRetransform` của transformer, và nguồn class-file bytes JVM đang xử lý.

Bài học thuộc nhóm **Hợp đồng transformer** trong Java Instrumentation. Mục tiêu là đọc callback theo đúng vòng đời và tránh hiểu nhầm một lần `transform` được gọi là "lớp đang load lần đầu" hoặc "chắc chắn đang retransform".

## 1. Ba thời điểm JVM có thể gọi `transform`

Một Java agent đăng ký đối tượng `ClassFileTransformer` bằng `Instrumentation.addTransformer(...)`. JVM sử dụng transformer trong các tình huống sau:

1. **Định nghĩa lần đầu (first definition / class load).** Class loader hoặc cơ chế tương đương yêu cầu JVM tạo định nghĩa `Class` từ class-file bytes. Callback được gọi **trước khi JVM xác minh và định nghĩa lớp**. Lúc này **`classBeingRedefined == null`** vì chưa có `Class<?>` được định nghĩa cần thay thế.
2. **Redefine (định nghĩa lại).** Một công cụ yêu cầu `Instrumentation.redefineClasses(new ClassDefinition(existingClass, replacementBytes))` hoặc cơ chế JVM TI tương đương. Lớp **đã tồn tại**; hệ thống cung cấp class-file bytes thay thế. Callback nhận **`classBeingRedefined != null`**.
3. **Retransform (biến đổi lại).** Một công cụ yêu cầu `Instrumentation.retransformClasses(existingClass)` hoặc tương đương. Lớp **đã tồn tại**; JVM chạy lại quy trình transform từ bytes nền của lần định nghĩa ban đầu hoặc lần redefine gần nhất, với cơ chế tái sử dụng kết quả của transformer không hỗ trợ retransformation. Callback của **transformer hỗ trợ retransformation** nhận **`classBeingRedefined != null`**.

~~~mermaid
flowchart TD
    A["JVM xử lý định nghĩa lớp"] --> B{"Có Class<?> đã định nghĩa?"}
    B -->|Chưa| C["First definition: classBeingRedefined = null"]
    B -->|Đã có| D["Redefine hoặc retransform: classBeingRedefined != null"]
    D --> E["Không thể suy ra riêng redefine/retransform từ tham số này"]
    C --> F["Transformer trả null hoặc bytes mới"]
    E --> F
    F --> G["JVM tiếp tục kiểm tra và áp dụng định nghĩa"]
~~~

Đối với **định nghĩa lần đầu**, transformer có thể xử lý lớp dù ứng dụng chưa từng thực thi một dòng nào trong lớp đó. Đối với **redefine/retransform**, đã tồn tại `Class<?>` và có thể đã tồn tại instance cùng stack frame đang thực thi mã cũ.

## 2. Đọc đúng các tham số của callback

Trong Java 17+, dạng đầy đủ có tham số `Module` là:

~~~java
byte[] transform(Module module,
                 ClassLoader loader,
                 String className,
                 Class<?> classBeingRedefined,
                 ProtectionDomain protectionDomain,
                 byte[] classfileBuffer);
~~~

Đây là **chữ ký minh họa của API**, chưa phải một chương trình Java độc lập. API còn có dạng năm tham số (không có `Module`):

~~~java
byte[] transform(ClassLoader loader,
                 String className,
                 Class<?> classBeingRedefined,
                 ProtectionDomain protectionDomain,
                 byte[] classfileBuffer);
~~~

Hai phương thức trong interface đều có triển khai mặc định ở JDK hiện đại: dạng sáu tham số mặc định gọi dạng năm tham số, và dạng năm tham số mặc định trả `null`. Vì vậy bạn có thể override **một trong hai**; đoạn thực hành phía dưới override dạng sáu tham số, tương thích Java 17+.

| Tham số | Ý nghĩa thực tế | Sai lầm phổ biến |
| --- | --- | --- |
| `module` | Module chứa lớp đang được transform (API từ Java 9) | Cho rằng đó là module của agent |
| `loader` | Class loader định nghĩa lớp; `null` có thể nghĩa là bootstrap loader | Đồng nhất `loader == null` với redefine/retransform |
| `className` | Tên lớp dạng JVM internal name, ví dụ `com/acme/Target` | Lọc bằng `com.acme.Target` hoặc nhầm nó với `Class.getName()` |
| **`classBeingRedefined`** | `null` khi **first definition**; đối tượng `Class<?>` khi **redefine/retransform** | Coi non-null là "chắc chắn retransform" |
| `protectionDomain` | Protection domain được dùng khi định nghĩa lớp | Coi nó là mã sự kiện hay nguyên nhân thao tác |
| `classfileBuffer` | Class-file bytes đầu vào cho **lượt transform hiện tại** | Cho rằng luôn là bytes gốc trên đĩa hoặc được phép sửa trực tiếp |

**Quy tắc đọc trong code:**

~~~java
if (classBeingRedefined == null) {
    // Class load/first definition.
} else {
    // Class đã tồn tại: redefine HOẶC retransform.
    // Chỉ riêng tham số này KHÔNG cho biết chính xác thao tác nào.
}
~~~

Đây là **mảnh điều kiện minh họa trong một callback**, không phải mã chạy độc lập. Nếu cần in tên, dùng `className` cho cả hai trường hợp; khi `classBeingRedefined != null`, có thể dùng `classBeingRedefined.getName()`. Với tên có package, hai dạng khác nhau: `com/acme/Target` và `com.acme.Target`.

Ngoài ra:

- `classfileBuffer` **không được sửa tại chỗ**. Trả `null` khi không biến đổi; nếu cần biến đổi, tạo một `byte[]` mới chứa class file hợp lệ.
- Callback có thể chạy trong đường nạp lớp trên nhiều thread. Không dùng một biến toàn cục `currentMode` để suy luận chắc chắn thao tác nếu có nhiều tác nhân/JVM TI tool hoạt động đồng thời.
- Callback xảy ra **trong quá trình JVM xử lý yêu cầu**, trước khi bytes mới được áp dụng hoàn tất. Log "transform called" **chưa chứng minh** redefine/retransform đã thành công.
- Việc lớp đã được định nghĩa trong quá khứ **không tự gọi lại transformer**; cần yêu cầu thực tế (redefine/retransform) và cấu hình transformer phù hợp.

## 3. Bảng phân biệt tình huống và quyền nhận callback

Một transformer có hai kiểu đăng ký:

~~~java
inst.addTransformer(transformer);        // Tương đương canRetransform=false
inst.addTransformer(transformer, false); // Retransformation-incapable
inst.addTransformer(transformer, true);  // Retransformation-capable
~~~

Đây là các **lệnh minh họa** trong method nhận `Instrumentation inst`. Tham số `true` đòi JVM/agent cho phép retransformation. Đừng nhầm `canRetransform` của transformer với việc có thể gọi `redefineClasses`.

| Sự kiện | `classBeingRedefined` trong callback | Transformer `canRetransform=false` | Transformer `canRetransform=true` |
| --- | --- | --- | --- |
| Lớp **định nghĩa lần đầu** sau khi đăng ký | `null` | **Được gọi** | **Được gọi** |
| `redefineClasses` của lớp đã tồn tại | **non-null** | **Được gọi** | **Được gọi** |
| `retransformClasses` của lớp đã tồn tại | **non-null** | **Không gọi lại**; JVM tái áp dụng kết quả transform cũ | **Được gọi** |

Điều cần nhấn mạnh là ô "không gọi lại" trong hàng retransform: **không nhận callback không có nghĩa transformer bất lực ấy đã mất hiệu lực**. JVM giữ và áp dụng lại kết quả lần trước của transformer đó, thay vì gọi phương thức `transform` lần nữa.

Trong nhiều JVM, thứ tự các nhóm transform là:

1. Java transformer **không** hỗ trợ retransformation.
2. Native transformer **không** hỗ trợ retransformation (thông qua JVM TI).
3. Java transformer **có** hỗ trợ retransformation.
4. Native transformer **có** hỗ trợ retransformation.

Trong từng nhóm, các transformer được gọi theo thứ tự đăng ký. Khi retransform, nhóm không hỗ trợ được **tái áp dụng kết quả** mà không gọi callback; nhóm hỗ trợ được gọi thực tế. Nếu nhiều transformer cùng sửa bytes, mỗi lượt sau nhận đầu ra của lượt trước. Trả `null` nghĩa là không thay đổi bytes ở lượt đó.

**Quan trọng:** Ngay cả khi bạn chỉ cài một transformer `canRetransform=true`, non-null **vẫn không cho biết** đây là redefine hay retransform; transformer đó nhận cả hai. Hãy phân biệt bằng **nguồn yêu cầu và ngữ cảnh có kiểm soát**, không bằng một phép so sánh đơn lẻ trên tham số callback.

## 4. Ví dụ thực hành Java 17+: quan sát cả ba ngữ cảnh

Thí nghiệm này cố ý đăng ký **hai transformer**:

- `fixed`: `canRetransform=false`.
- `capable`: `canRetransform=true`.

Cả hai chỉ log và **trả `null`, không sửa bytecode**. Sau khi lớp `Target` được load, ứng dụng yêu cầu **retransform**, rồi **redefine** chính lớp đó bằng bytes của một bản thay thế cùng cấu trúc. Nhờ vậy log cho thấy rõ callback nào được gọi và `classBeingRedefined` nhận giá trị gì.

Bạn cần JDK 17+ với `javac`, `jar`, `java`; JVM phải thực sự hỗ trợ cả hai capability. Không cần thư viện bên ngoài.

### 4.1. Tạo `TraceTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class TraceTransformer implements ClassFileTransformer {
    private final String label;

    public TraceTransformer(String label) {
        this.label = label;
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] originalBytes) {
        if (!"Target".equals(className)) {
            return null;
        }
        String context = classBeingRedefined == null ? "FIRST_DEFINITION" : "REVISIT";
        String target = classBeingRedefined == null ? "null" : classBeingRedefined.getName();
        System.out.println(label + ": " + context + ", classBeingRedefined=" + target);
        return null;
    }
}
~~~

Vì lớp `Target` trong ví dụ ở **default package**, `className` bằng `"Target"`. Trong dự án thực có `package demo;` thì phải lọc bằng `"demo/Target"`. Biến `context` cố tình chỉ có **FIRST_DEFINITION** và **REVISIT**: không đặt tên **RETRANSFORM** chỉ vì `classBeingRedefined` khác `null`.

### 4.2. Tạo `EventAgent.java`

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class EventAgent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported() || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("This demo requires both capabilities");
        }
        inst.addTransformer(new TraceTransformer("fixed"), false);
        inst.addTransformer(new TraceTransformer("capable"), true);
    }

    public static void retransform(Class<?> type) throws Exception {
        instrumentation.retransformClasses(type);
    }

    public static void redefine(Class<?> type, Path replacement) throws Exception {
        byte[] newClassFile = Files.readAllBytes(replacement);
        instrumentation.redefineClasses(new ClassDefinition(type, newClassFile));
    }
}
~~~

`Instrumentation` được JVM truyền vào `premain`. Agent lưu reference để ứng dụng demo chủ động kích hoạt hai thao tác, giúp phân biệt nguyên nhân của từng đoạn log. Trong production, chỉ những thành phần được cấp quyền nên gọi cơ chế redefine/retransform; không mặc định xuất mọi API điều khiển ra mã nghiệp vụ.

`retransformClasses(Class<?>...)` yêu cầu JVM tự dùng bytes nền của lớp đã load. `redefineClasses(ClassDefinition...)` nhận **bytes mới** do caller cung cấp. Trong ví dụ, bytes cho redefine được đọc từ `replacement/Target.class`.

### 4.3. Tạo hai phiên bản của `Target`

**`Target.java`** tại thư mục gốc của bài thực hành:

~~~java
public final class Target {
    public String value() {
        return "v1";
    }
}
~~~

**`replacement/Target.java`** tại thư mục con `replacement`:

~~~java
public final class Target {
    public String value() {
        return "v2";
    }
}
~~~

Hai tệp dùng **cùng tên class và cùng cấu trúc field/method**; chỉ đổi hằng chuỗi trả về của method. Không đưa cả hai `Target.class` vào classpath ứng dụng cùng lúc. Bản `v2` là **class-file bytes đầu vào của redefine**, không phải một lớp Java độc lập có tên khác. Nếu thay đổi tên class, thêm/xóa method hay sửa signature tùy ý, JVM có thể từ chối `redefineClasses` vì vi phạm giới hạn cấu trúc.

### 4.4. Tạo `EventApp.java`

~~~java
import java.nio.file.Path;

public final class EventApp {
    public static void main(String[] args) throws Exception {
        Target target = new Target();
        System.out.println("initial=" + target.value());

        EventAgent.retransform(Target.class);
        System.out.println("after-retransform=" + target.value());

        EventAgent.redefine(Target.class, Path.of("replacement/Target.class"));
        System.out.println("after-redefine=" + target.value());
    }
}
~~~

Chú ý ứng dụng **không tạo lại** đối tượng `target` sau redefine; cùng một instance sẽ gọi implementation `value()` mới trên những lượt gọi tiếp theo nếu redefine thành công.

### 4.5. Tạo manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: EventAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Đây là **main manifest section** của startup agent, cần lưu văn bản có xuống dòng cuối. Cả hai capability đều tùy chọn theo cấu hình JVM; có cờ `true` chỉ là điều kiện yêu cầu, vẫn phải kiểm tra kết quả bằng `isRetransformClassesSupported()` và `isRedefineClassesSupported()`. Nếu JVM không hỗ trợ, ví dụ dừng với thông báo chủ đích từ `premain`.

### 4.6. Biên dịch, đóng gói và chạy

Từ một thư mục rỗng chứa bốn tệp `TraceTransformer.java`, `EventAgent.java`, `Target.java`, `EventApp.java`, `agent.mf` và thư mục con `replacement/Target.java`, chạy:

~~~bash
javac --release 17 TraceTransformer.java EventAgent.java Target.java EventApp.java

javac --release 17 -d replacement replacement/Target.java

jar --create --file event-agent.jar --manifest agent.mf EventAgent.class TraceTransformer.class

java -javaagent:event-agent.jar -cp . EventApp
~~~

Các lệnh dùng cú pháp JDK, có thể chạy trong shell Bash, CMD hoặc PowerShell từ **thư mục bài thực hành**. `javac --release 17` yêu cầu JDK hỗ trợ release 17. `EventAgent.class` và `TraceTransformer.class` phải nằm trong agent JAR; `Target.class` phiên bản `v1` nằm ở thư mục ứng dụng; `replacement/Target.class` là file bytes cung cấp cho redefine.

Trên OpenJDK/HotSpot hỗ trợ cả hai capability, **stdout của các đoạn code trên**:

~~~text
fixed: FIRST_DEFINITION, classBeingRedefined=null
capable: FIRST_DEFINITION, classBeingRedefined=null
initial=v1
capable: REVISIT, classBeingRedefined=Target
after-retransform=v1
fixed: REVISIT, classBeingRedefined=Target
capable: REVISIT, classBeingRedefined=Target
after-redefine=v2
~~~

### 4.7. Đọc từng nhóm log

**Nhóm 1 — first definition:**

~~~text
fixed: FIRST_DEFINITION, classBeingRedefined=null
capable: FIRST_DEFINITION, classBeingRedefined=null
initial=v1
~~~

Hai transformer được đăng ký từ `premain`, trước khi `Target` được load. Vì vậy cả `fixed` và `capable` đều được gọi khi JVM **định nghĩa `Target` lần đầu**, với `classBeingRedefined == null`.

**Nhóm 2 — retransform:**

~~~text
capable: REVISIT, classBeingRedefined=Target
after-retransform=v1
~~~

Ứng dụng vừa gọi `EventAgent.retransform(Target.class)`. Transformer `capable` được gọi vì `canRetransform=true`; transformer `fixed` **không được gọi lại**. JVM vẫn tái áp dụng kết quả lần trước của `fixed` nếu transformer đó từng làm thay đổi bytes. Ở demo, cả hai đều trả `null`, nên `Target.value()` vẫn là `"v1"`.

**Nhóm 3 — redefine:**

~~~text
fixed: REVISIT, classBeingRedefined=Target
capable: REVISIT, classBeingRedefined=Target
after-redefine=v2
~~~

Ứng dụng vừa gọi `EventAgent.redefine(...)` với class bytes của `Target` phiên bản `v2`. **Cả hai transformer** nhận callback trong redefine. Cả hai lại trả `null`, nên bytes `v2` được áp dụng và instance `target` gọi `value()` mới.

**Kết luận quan sát:** Hai dòng `capable: REVISIT` của nhóm 2 và nhóm 3 **có cùng kiểu dữ liệu callback** (`classBeingRedefined=Target`). Chúng chỉ được phân biệt nhờ **thao tác mà ứng dụng yêu cầu** và mẫu callback của `fixed`, chứ không nhờ giá trị `classBeingRedefined` đơn lẻ.

## 5. Redefine và retransform khác nhau ở nguồn bytes

Cả hai xử lý class đã tồn tại, nhưng *đầu vào* cho transformer không giống nhau:

| Thuộc tính | `retransformClasses(Target.class)` | `redefineClasses(new ClassDefinition(Target.class, bytes))` |
| --- | --- | --- |
| Ai cung cấp bytes? | JVM lấy bytes nền của định nghĩa ban đầu hoặc **lần redefine gần nhất** | Caller đưa **bytes thay thế** qua `ClassDefinition` |
| Có gọi lại transformer `canRetransform=false`? | **Không**; tái sử dụng kết quả transform cũ | **Có** |
| Có gọi transformer `canRetransform=true`? | **Có** | **Có** |
| `classBeingRedefined` trong callback nhận được | Non-null | Non-null |
| Kiểm tra capability | `isRetransformClassesSupported()` và quyền sửa lớp | `isRedefineClassesSupported()` và quyền sửa lớp |
| Kịch bản thường gặp | Cập nhật instrumentation cho lớp đã load | Hotfix hoặc thay definition từ class-file bytes được chọn |

### 5.1. Bytes trong `classfileBuffer` có phải luôn giống file trên ổ đĩa?

**Không.** Đối với class load, đầu vào đầu tiên xuất phát từ class file bytes được đưa vào `ClassLoader.defineClass` (hoặc cơ chế tương ứng). Với redefine, đầu vào đầu tiên là `ClassDefinition.getDefinitionClassFile()`; đó có thể là bytes do người dùng build riêng. Với retransform, JVM tái tạo đầu vào từ bytes nền sau lần load hoặc redefine gần nhất, cộng kết quả của các transformer không hỗ trợ retransformation được tự động tái áp dụng.

Tài liệu Java lưu ý bytes nền khi retransform **không nhất thiết đồng nhất từng byte** với bytes ban đầu: constant-pool entries và một số thuộc tính có thể được tái tổ chức. Do đó, so sánh hash `classfileBuffer` với file `.class` trên đĩa để nhận dạng DEFINE/REDEFINE/RETRANSFORM sẽ dễ sai.

### 5.2. Tác dụng sau khi lớp được định nghĩa lại

- **Không chạy lại class initializer `<clinit>`** chỉ vì redefine/retransform. Giá trị static field hiện hữu được giữ theo ngữ nghĩa chuẩn.
- Instance đã tạo trước đó **không bị thay đối tượng**; những invocation mới có thể dùng bytecode mới.
- Với method có stack frame đang chạy tại thời điểm thay định nghĩa, frame đó có thể tiếp tục code cũ; lời gọi mới dùng định nghĩa mới.
- Việc thay đổi định nghĩa có **giới hạn cấu trúc**. Không tùy ý thêm/xóa field/method, đổi signature hoặc quan hệ kế thừa trong một lần redefine/retransform theo cơ chế Java instrumentation hiện hành.
- Một method đang thực thi không được "chạy lại từ đầu" khi instrumentation thay đổi định nghĩa của class.

Trong ví dụ, cùng instance `target` trả `"v1"` sau retransform nhưng trả `"v2"` sau redefine, vì chỉ thao tác thứ hai đưa vào **class-file bytes mới**.

## 6. Điều kiện để callback xuất hiện như kỳ vọng

Để kiểm tra mã thật, phân biệt **năng lực JVM**, **năng lực transformer** và **tính có thể sửa của lớp**:

1. Manifest của agent yêu cầu `Can-Retransform-Classes: true` nếu cần retransform; yêu cầu `Can-Redefine-Classes: true` nếu cần redefine. Chúng là **hai thuộc tính độc lập**.
2. JVM có thể không hỗ trợ một hoặc cả hai, nên phải gọi `inst.isRetransformClassesSupported()` và `inst.isRedefineClassesSupported()` trước khi sử dụng.
3. Đối với lớp cụ thể, gọi `inst.isModifiableClass(Target.class)`. Lớp mảng và primitive không thể sửa theo API; không nên giả định mọi lớp bootstrap, VM-generated hoặc class đặc biệt đều sửa được.
4. Chỉ transformer đăng ký với `addTransformer(t, true)` mới được gọi lại trong một lần retransform. `addTransformer(t)` ngầm dùng `false`.
5. Một số lớp có thể đã được định nghĩa **trước khi đăng ký** transformer. Khi đó không bao giờ có callback DEFINE hồi tố; agent chỉ thấy lần xử lý sau nếu JVM và lớp cho phép.
6. Transformer nên được đăng ký đủ sớm để quan sát initial class definition. Trong startup agent, đăng ký ở `premain` thường đáp ứng mục tiêu này cho lớp ứng dụng được load sau; nếu nạp agent động, nhiều class có thể đã được định nghĩa.
7. Không đánh đồng việc **gọi `retransformClasses` thành công** với việc *mọi transformer đã chạy*: transformer incapable không được gọi lại, kể cả khi kết quả cũ vẫn có tác dụng.

Nếu `addTransformer(t, true)` được dùng khi capability không hỗ trợ, có thể nhận `UnsupportedOperationException`. Nếu `retransformClasses` hoặc `redefineClasses` được yêu cầu với lớp không thể sửa, có thể gặp `UnmodifiableClassException`, hoặc các lỗi class format/version/linkage khi bytes không hợp lệ. API từ chối một yêu cầu không đồng nghĩa trước đó chưa có callback: một số callback có thể đã chạy trước bước kiểm tra/áp dụng cuối.

## 7. Viết transformer an toàn khi class có thể được xử lý nhiều lần

Transformer dùng trong môi trường production phải xử lý tốt cả load ban đầu và nhiều lần redefine/retransform:

- **Đúng tên và class loader:** `className` ở dạng `com/example/Target`, không tự chuyển sang dotted name khi so sánh. Hai class loader có thể định nghĩa **hai class khác nhau** dù cùng tên; theo dõi cả `loader` và tên class nếu cần.
- **Idempotent theo ngữ nghĩa:** đừng tự ý chèn lại cùng một lời gọi log vào bytecode mỗi lần thấy `classBeingRedefined != null`. Retransformation thường dùng bytes nền đã được tạo lại, nhưng khi có nhiều transformer hoặc redefine từ bytes bên ngoài, marker/instrumentation có thể đã có. Cần xác nhận cấu trúc thực tế của bytes đầu vào.
- **Không sửa input tại chỗ:** tạo byte array mới nếu transform; nếu không sửa thì trả `null`.
- **Không sử dụng callback để phân loại thao tác quá mức:** `classBeingRedefined != null` nghĩa là *existing class*, không suy ra `retransform`; theo dõi source action nếu tác vụ buộc phải phân biệt.
- **Thread-safe và tránh class-loading cycle:** callback có thể được gọi đồng thời; việc log bằng framework nặng, reflection sâu hoặc load thêm class bị instrument có thể gây recursion, deadlock hoặc lỗi linkage.
- **Giữ cấu trúc class hợp lệ cho các lần thay định nghĩa:** nếu transformer thêm method/field lúc initial load, lần redefine/retransform tiếp theo phải xuất một class definition hợp lệ theo quy tắc cho phép. Các thay đổi cấu trúc tùy tiện có thể bị từ chối.
- **Tách quyết định phân loại với quyết định biến đổi:** callback có thể log "FIRST_DEFINITION"/"REVISIT" từ tham số, rồi quyết định có transform dựa vào chính sách và bytes thực tế. Đừng giữ state toàn cục suy diễn "class này chỉ transform một lần trong đời JVM".
- **Quản lý vòng đời:** `removeTransformer` ngừng đăng ký cho các lượt tương lai, nhưng vì xử lý song song callback vẫn có thể xảy ra sau lời gọi remove; nó không tự hoàn tác class bytes đã thay.

### Ví dụ log an toàn hơn khi cần theo dõi vận hành

~~~java
String identity = String.valueOf(className);
String context = classBeingRedefined == null ? "DEFINE" : "EXISTING_CLASS";
String loaderName = loader == null ? "bootstrap" : loader.getClass().getName();
System.out.println(context + " " + identity + " loader=" + loaderName);
~~~

Đây là **đoạn code minh họa đặt trong `transform`**, không phải file `.java` độc lập. Đừng để logging khiến transformer load lại chính những class mà nó chặn: đặt filter hẹp và dùng logging ít dependency cho các callback nhạy cảm.

## 8. Khi log chỉ có callback, có thể kết luận đến đâu?

| Dấu hiệu thấy được | Kết luận có cơ sở | Điều **chưa** thể kết luận |
| --- | --- | --- |
| `classBeingRedefined == null` | JVM đang xử lý class definition ban đầu | Lớp chắc chắn chưa có trên hệ thống file, hoặc `main` sắp chạy |
| `classBeingRedefined != null` | JVM đang xử lý class đã được định nghĩa | Là redefine hay retransform **nếu không có ngữ cảnh khác** |
| Transformer `canRetransform=false` xuất hiện | Callback đó **không thể là retransformation thông thường** | Là DEFINE hay REDEFINE nếu chưa xem `classBeingRedefined` |
| Transformer `canRetransform=true` xuất hiện với non-null | Là một lần revisit | Là redefine hay retransform chỉ dựa vào flag |
| Không thấy callback `fixed` khi thao tác retransform | Đúng quy tắc không gọi lại transformer incapable | Kết quả cũ của `fixed` chắc chắn không còn tác dụng |
| `transform` trả `null` | Transformer này không yêu cầu thay đổi bytes ở lượt hiện tại | Cả chuỗi transformer hoặc thao tác JVM chắc chắn không thay đổi lớp |
| Có log "REVISIT" | Transformer đã được gọi trong xử lý một yêu cầu sửa lớp | Yêu cầu đã áp dụng thành công hoặc method đang chạy đã đổi code ngay lập tức |

**Cách xác định chính xác nguyên nhân trong một ứng dụng có quyền điều khiển:**

- Log tại điểm gọi `Instrumentation.retransformClasses` hoặc `Instrumentation.redefineClasses`: tên loại thao tác, class đích, thời gian, trạng thái thành công/thất bại.
- Log hẹp trong callback: `className`, `classBeingRedefined`, nhóm registration `canRetransform`, class loader/module cần thiết.
- Đối chiếu hai loại log và kết quả thử nghiệm. Không dựa vào việc "callback chạy trên thread X" để chứng minh thao tác Y: JVM TI tool khác hoặc nhiều tác vụ đồng thời có thể gây callback.
- Nếu không kiểm soát được công cụ khởi phát và log chỉ có `classBeingRedefined != null`, hãy báo **"redfine/retransform chưa phân biệt được"** thay vì suy đoán.

## 9. Tự kiểm tra nhận thức

**Tình huống A:** Callback nhận `classBeingRedefined == null`, `className="sample/Widget"`. Điều có thể nói: `Widget` đang trong quá trình định nghĩa đầu tiên từ class-file bytes cho class loader ấy. Không dùng `classBeingRedefined.getName()` vì sẽ gây `NullPointerException`.

**Tình huống B:** Một transformer `canRetransform=false` vừa log với `classBeingRedefined != null`. Theo hợp đồng callback, đây là **redefine** chứ không phải retransform (transformer incapable không được gọi lại trong retransform).

**Tình huống C:** Một transformer `canRetransform=true` log với `classBeingRedefined != null`. Có thể là **redefine hoặc retransform**. Phải dựa vào thao tác khởi phát hoặc bằng chứng bổ sung.

**Tình huống D:** Khi gọi retransform, log không thấy transformer `fixed`, nhưng class behavior vẫn chứa instrumentation do `fixed` tạo từ lần định nghĩa trước. Đây là hành vi bình thường vì JVM **tái sử dụng kết quả** mà không gọi lại transformer incapable.

**Tình huống E:** Sau redefine, một instance hiện hữu trả kết quả mới ở lượt gọi tiếp theo, trong khi không thấy static initializer chạy lại. Điều này khớp semantics của đổi định nghĩa, không có nghĩa JVM đã tạo một class mới mang tên trùng.

### Tài liệu chuẩn để đối chiếu

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hai chữ ký `transform`, ý nghĩa `classBeingRedefined`, thứ tự transformer, nguồn bytes và quy tắc callback.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `redefineClasses`, capability và giới hạn lớp có thể sửa.
- [Java SE 17 — ClassDefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cặp `Class<?>` và class-file bytes được caller cung cấp cho redefine.
