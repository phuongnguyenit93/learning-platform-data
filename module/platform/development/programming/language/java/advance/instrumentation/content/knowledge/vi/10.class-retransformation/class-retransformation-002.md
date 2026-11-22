# Tìm lớp đích, kiểm tra isModifiableClass và yêu cầu retransformClasses

> **Bài toán:** Một Java agent đang chạy trong JVM muốn bổ sung instrumentation cho một class **đã được nạp**. Không thể chỉ đăng ký `ClassFileTransformer` rồi chờ JVM "load lại" class đó. Cần **tìm đúng đối tượng `Class<?>`**, xác nhận **JVM có capability retransformation**, kiểm tra **class cụ thể có thể sửa**, đăng ký transformer có khả năng retransformation, rồi **chủ động gọi `Instrumentation.retransformClasses(target)`** và xác minh hành vi sau khi yêu cầu thành công.

Đây là quy trình trọng tâm trong phần **Retransformation** của Java Advance – instrumentation. Bài học giải thích cả những chi tiết dễ làm sai: nhiều class loader cùng định nghĩa một tên lớp, sự khác nhau giữa `isModifiableClass` và `isRetransformClassesSupported`, cách JVM xử lý chuỗi transformer, giới hạn đổi cấu trúc class, xử lý exception và một ví dụ Java 17+ có thể biên dịch/chạy thực tế.

## 1. Khi nào phải dùng `retransformClasses`?

Với class chưa được định nghĩa, agent có thể đăng ký transformer trước khi JVM load class:

~~~text
Agent đăng ký transformer
       |
       v
JVM load TargetService lần đầu
       |
       v
ClassFileTransformer.transform(..., classBeingRedefined=null, ...)
       |
       v
Định nghĩa class bằng bytes sau biến đổi
~~~

Với class **đã được định nghĩa**, chỉ `addTransformer` không tự động gửi lại class đó vào callback. Muốn JVM xử lý lại class hiện hữu, cần lệnh riêng:

~~~text
JVM đã có Class<TargetService>
       |
       v
Agent lấy đúng đối tượng Class<?> từ JVM
       |
       v
isRetransformClassesSupported()? --> false: dừng hoặc chọn phương án khác
       |
       v
isModifiableClass(target)? ------> false: bỏ qua và ghi rõ lý do
       |
       v
Đăng ký ClassFileTransformer với canRetransform=true
       |
       v
Instrumentation.retransformClasses(target)
       |
       v
Transformer nhận callback cho class đang được retransform
       |
       v
JVM kiểm tra/áp dụng class-file bytes mới
       |
       v
Lần gọi method tiếp theo có thể dùng định nghĩa mới
~~~

`retransformClasses` **không nhận bytes thay thế trực tiếp** như `redefineClasses`. Thay vào đó, JVM tạo lại chuỗi biến đổi từ bytes nền của định nghĩa ban đầu hoặc lần redefine gần nhất, tái áp dụng kết quả của transformer không hỗ trợ retransformation và gọi lại transformer có hỗ trợ.

**Ba động từ cần phân biệt:**

| Hành động | API Java | Kết quả trực tiếp |
| --- | --- | --- |
| Khám phá class đã load | `getAllLoadedClasses()` | Danh sách `Class<?>` đang được JVM giữ là loaded; không tự đổi bytecode |
| Kiểm tra điều kiện | `isRetransformClassesSupported()` + `isModifiableClass(clazz)` | Hai câu trả lời về capability chung và khả năng sửa từng class |
| Yêu cầu JVM xử lý lại class | `retransformClasses(clazz)` | Thực thi lại quá trình biến đổi theo hợp đồng JVM; có thể đổi bytecode nếu transformer sinh bytes hợp lệ |

**Một nguyên tắc:** `Class<?>` là **danh tính class trong JVM**, gồm cả defining class loader, không chỉ là tên dạng chuỗi. Hai class cùng tên nhưng được định nghĩa bởi hai class loader khác nhau là **hai đích khác nhau**.

## 2. Bước 1: tìm class đích trong JVM

### 2.1. `getAllLoadedClasses()` và lọc theo tên đầy đủ

`Instrumentation.getAllLoadedClasses()` trả về mảng các class hiện đang loaded, gồm class/interface, array class và hidden class. Nó không giới hạn ở module hay ứng dụng của agent. Với tên class `com.example.billing.InvoiceService`, tìm theo `Class.getName()` bằng tên **có dấu chấm**:

~~~java
Class<?> chosen = null;
int matches = 0;

for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if ("com.example.billing.InvoiceService".equals(candidate.getName())) {
        matches++;
        chosen = candidate;
    }
}

if (matches != 1) {
    throw new IllegalStateException("Expected one loaded target, found " + matches);
}
~~~

Đây là **mảnh code minh họa bên trong agent đã có `Instrumentation inst`**, chưa phải chương trình độc lập. Mẫu này **không tự load** `InvoiceService`; nó chỉ xem danh sách loaded class JVM đã có. Nếu `matches == 0`, có thể class chưa được định nghĩa, sai tên, hoặc ứng dụng đang dùng một triển khai khác. Nếu `matches > 1`, **không được chọn phần tử đầu tiên**: rất có thể có hai defining class loader cùng nạp class cùng tên.

Trong callback `ClassFileTransformer.transform`, `className` lại là JVM internal name, ví dụ `com/example/billing/InvoiceService`. Đừng mang so sánh tên dạng slash từ callback sang `Class.getName()` mà không đổi định dạng.

### 2.2. Chọn đúng loader và module

Khi có nhiều matches, phải thu hẹp theo **defining class loader** và khi cần theo module/lớp tham chiếu đã biết:

~~~java
for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if (!"com.example.billing.InvoiceService".equals(candidate.getName())) {
        continue;
    }
    ClassLoader definingLoader = candidate.getClassLoader();
    Module module = candidate.getModule();
    // Ghi dấu định danh loader/module hoặc so với loader đích đã biết.
    // Chỉ chọn candidate khi nó đúng với ứng dụng cần instrument.
}
~~~

Đây cũng là **mảnh minh họa**, không có sẵn biến chỉ định loader đích. Một class do bootstrap loader định nghĩa có thể có `getClassLoader() == null`. Tên loader hoặc `toString()` chỉ để chẩn đoán; nếu có đối tượng loader đích, so sánh **cùng đối tượng** (`==`) sẽ chắc chắn hơn so sánh chuỗi hiển thị.

Những hệ thống thường có nhiều bản class cùng tên: application server, plugin framework, test runner, OSGi, container hỗ trợ hot reload hoặc service dùng isolated class loaders. Chọn theo tên lớp mà bỏ qua loader có thể biến đổi **nhầm tenant/plugin**, dẫn tới lỗi class verification hoặc hành vi khó đoán.

**Đừng giữ tham chiếu mạnh đến mọi `Class<?>`/`ClassLoader` vô thời hạn** chỉ để làm cache tìm lớp: tham chiếu đó có thể giữ cả class loader và hệ object graph của một lần deploy cũ, làm tăng rủi ro memory leak. Lọc trong phạm vi công việc và giải phóng reference không còn cần thiết.

### 2.3. `getInitiatedClasses(loader)` khác gì?

`getInitiatedClasses(loader)` trả về các lớp mà loader được ghi nhận là *initiating loader* và có thể tìm qua tên; nó **không đồng nghĩa** với "mọi lớp được loader đó định nghĩa". Với delegation, một loader có thể initiate class thực tế do parent loader define. Ngoài ra, method này không bao gồm hidden class theo hợp đồng API.

Khi chỉ biết tên class và chưa biết loader, `getAllLoadedClasses()` là công cụ phát hiện tổng quát. Khi cần giới hạn phạm vi theo loader liên quan, `getInitiatedClasses(loader)` có thể hỗ trợ nhưng vẫn phải kiểm tra `clazz.getClassLoader()`, tên và module để xác định danh tính chính xác.

### 2.4. Tại sao không chỉ dùng `Class.forName`?

~~~java
Class<?> c = Class.forName(
    "com.example.billing.InvoiceService", false, intendedLoader);
~~~

Lệnh này **có thể khiến JVM load/define lớp chưa được load** (dù tham số `initialize=false` không chủ động chạy class initialization). Vì vậy nó **không phải một phép truy vấn thuần** để biết class đã load hay chưa, và có thể làm thay đổi thời điểm class loading. Dùng `getAllLoadedClasses()` khi mục tiêu là **chỉ tìm class đã nạp**. `Class.forName` phù hợp khi bạn **chủ ý** yêu cầu class được load và đã kiểm soát loader/hệ quả.

## 3. Bước 2: kiểm tra hai điều kiện độc lập

Một class chỉ có thể được retransform khi **đồng thời** có:

1. Cấu hình JVM và agent **hỗ trợ retransformation**: `inst.isRetransformClassesSupported() == true`.
2. Đối tượng class đích **có thể thay đổi definition**: `inst.isModifiableClass(clazz) == true`.

Hai câu trả lời không thay thế nhau.

### 3.1. Capability của JVM: `isRetransformClassesSupported`

Đối với startup agent sử dụng `-javaagent:agent.jar`, manifest phải yêu cầu:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.agent.MyAgent
Can-Retransform-Classes: true
~~~

Đây là **mẫu manifest minh họa**; tên `com.example.agent.MyAgent` phải khớp class thực được đóng gói. `Can-Retransform-Classes: true` là điều kiện yêu cầu capability nhưng **không tự bảo đảm** JVM thực tế hỗ trợ. Không có cờ hoặc ghi `false` thì cấu hình agent này không được phép dùng retransformation.

Khi nhận `Instrumentation` từ `premain` hoặc `agentmain`:

~~~java
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransformation is unavailable");
}
~~~

Đoạn code này chủ ý **không** gọi `addTransformer(t, true)` hoặc `retransformClasses(...)` nếu capability không có. Nếu vẫn cố `addTransformer(t, true)` trên cấu hình không hỗ trợ, API có thể ném `UnsupportedOperationException`. Lỗi này không được giải quyết bằng cách chỉ đổi `isModifiableClass` hay chọn tên class khác.

### 3.2. Khả năng sửa một class: `isModifiableClass`

~~~java
boolean modifiable = inst.isModifiableClass(target);
if (!modifiable) {
    throw new IllegalStateException(
        "Not modifiable: " + target.getName());
}
~~~

`isModifiableClass` **kiểm tra class cụ thể có thể được đổi definition hay không**, dùng cho cả redefinition và retransformation. Kết quả **không bị quyết định** bởi `isRetransformClassesSupported()` hay `isRedefineClassesSupported()`. Vì vậy một JVM có thể trả `isModifiableClass(target) == true` nhưng retransformation vẫn bị cấm do capability chung là `false`.

Theo Java 17 API, **primitive class và array class không thể modifiable**:

~~~java
inst.isModifiableClass(int.class);        // false
inst.isModifiableClass(String[].class);   // false
~~~

Đây là các **lệnh minh họa** có kết quả đặc tả rõ, không phải toàn bộ chương trình. Không giả định tất cả class của JDK đều không thể sửa, cũng không giả định class ứng dụng nào cũng sửa được: hãy kiểm tra trên **JVM và class thực tế**. Một số class đặc biệt/hidden class có thể không modifiable.

### 3.3. Bảng kiểm nhanh

| `isRetransformClassesSupported()` | `isModifiableClass(target)` | Có nên gọi `retransformClasses(target)`? |
| --- | --- | --- |
| `false` | `false` | **Không**: thiếu capability và target không modifiable |
| `false` | `true` | **Không**: target có thể thay definition nhưng agent/JVM không được phép retransform |
| `true` | `false` | **Không**: gọi sẽ gặp `UnmodifiableClassException` |
| `true` | `true` | **Có thể yêu cầu**: vẫn cần transformer/bytes hợp lệ, đúng class và xử lý exception |

Ngay cả hàng cuối cũng không có nghĩa phép biến đổi chắc chắn thành công. JVM còn kiểm tra tính hợp lệ class file, các giới hạn thay đổi cấu trúc, các transformer khác và điều kiện concurrency.

## 4. Bước 3: đăng ký transformer có khả năng retransform

Đối với lớp đã load và muốn callback chạy khi `retransformClasses`:

~~~java
ClassFileTransformer transformer = new MyTransformer();
inst.addTransformer(transformer, true); // canRetransform = true
inst.retransformClasses(target);
~~~

Đây là đoạn mô tả API, **không phải file độc lập**: `MyTransformer` phải là một class tự triển khai đúng interface. Trong Java 17, `ClassFileTransformer` có các `transform` method mặc định, **không phải functional interface để tự động thay bằng lambda**. Ví dụ đầy đủ dùng class riêng.

**Phân biệt:**

- `inst.addTransformer(transformer)` tương đương `addTransformer(transformer, false)`. Transformer đó nhận callback lúc class được define và redefine, nhưng **không được gọi lại** trong retransform.
- `inst.addTransformer(transformer, true)` tạo *retransformation-capable transformer*. Khi class đã load được yêu cầu retransform, JVM gọi callback của transformer này.
- Một transformer `canRetransform=false` từng biến đổi class ở lần definition/redefine trước có **kết quả cũ được JVM tái áp dụng**, không cần callback mới. Không có callback từ nhóm này **không có nghĩa ảnh hưởng cũ biến mất**.
- Nếu transformer vừa được đăng ký sau khi lớp đã load, nó **không nhận lại sự kiện first definition của quá khứ**. Lệnh `retransformClasses` tạo lượt callback phù hợp với class đã có.
- Khi transformer trả `null`, nó không yêu cầu đổi bytes ở lượt callback đó; việc **gọi retransform thành công** không bảo đảm có instrumentation mới.

Trong callback dạng sáu tham số (Java 9+), tham số thứ tư giúp nhận biết ngữ cảnh:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        ProtectionDomain domain, byte[] classfileBuffer) {
    if (classBeingRedefined == null) {
        // Đang xử lý class lần đầu được định nghĩa.
        return null;
    }
    // Lớp đã tồn tại: có thể redefine HOẶC retransform.
    return null;
}
~~~

Đây chỉ là **thân callback minh họa bên trong class triển khai transformer**, cần import `java.security.ProtectionDomain` và `java.lang.instrument.ClassFileTransformer`. `classBeingRedefined != null` là điều kiện của class đã tồn tại, **không phân biệt được riêng retransform với redefine** nếu không có ngữ cảnh yêu cầu.

## 5. Thí nghiệm Java 17+: tìm class đã load và retransform thành công

Ta sẽ làm một startup agent `RetransformAgent`, nhưng **chỉ phát lệnh retransformation khi lớp đã được ứng dụng dùng**. Khi agent bắt đầu, `TargetService` chưa bị sửa. Ứng dụng tạo instance rồi gọi vào agent để:

1. Lấy snapshot bằng `getAllLoadedClasses()` và tìm `TargetService`.
2. Kiểm tra capability, modifiability và các trường hợp negative của primitive/array.
3. Đăng ký `ReplacementTransformer` với `canRetransform=true`.
4. Gọi `retransformClasses(target)`, nhận callback cho class đã tồn tại.
5. Hủy đăng ký transformer, quan sát **instance cũ và instance mới** dùng định nghĩa mới.

Để ví dụ hoàn toàn tự chạy mà không cần thư viện bytecode, transformer trả lại **class file biến thể** đã biên dịch trước, cùng tên/cùng field/method structure nhưng khác phần thân `value()`. Đây là kỹ thuật *demo*, không phải cách an toàn để biến đổi tùy ý class production.

### 5.1. Tệp `TargetService.java` (bản gốc)

~~~java
public final class TargetService {
    public String value() { return "ORIGINAL"; }
}
~~~

### 5.2. Tệp `variant/TargetService.java` (bản thay thế)

~~~java
public final class TargetService {
    public String value() { return "INSTRUMENTED"; }
}
~~~

Hai source cùng binary name `TargetService` được biên dịch **vào hai thư mục khác nhau**. Khi ứng dụng chạy, chỉ bản gốc nằm trên classpath root; bản variant chỉ được agent đọc như **bytes dữ liệu** ở `variant/TargetService.class`. Thay đổi từ `"ORIGINAL"` sang `"INSTRUMENTED"` chỉ ảnh hưởng method body, không thêm method/field hoặc đổi superclass.

### 5.3. Tệp `ReplacementTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ReplacementTransformer implements ClassFileTransformer {
    private final Class<?> target;
    private final byte[] replacement;

    public ReplacementTransformer(Class<?> target, byte[] replacement) {
        this.target = target;
        this.replacement = replacement.clone();
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain, byte[] original) {
        if (classBeingRedefined != target || !"TargetService".equals(className)) {
            return null;
        }
        System.out.println("transform-existing=" + className);
        return replacement.clone();
    }
}
~~~

Transformer cố ý lọc bằng **cùng đối tượng `Class<?>`** được chọn ở bước tìm class và tên JVM internal name `TargetService`. Nếu có hai loader định nghĩa cùng binary name, so sánh `classBeingRedefined != target` giúp không trả bytes thay thế cho class khác.

`original` chính là đầu vào của lượt transform hiện tại; ví dụ không sửa mảng này. `replacement.clone()` cung cấp một mảng riêng chứa class file hợp lệ. Vì demo chỉ target một class đơn giản, không cần xét phụ thuộc khác. Trong dự án thực, transformer nên biến đổi có chọn lọc trên bytes đầu vào (ví dụ bằng thư viện bytecode hỗ trợ JVM đang chạy), giữ nguyên cấu trúc và tương thích nhiều transformer.

### 5.4. Tệp `RetransformAgent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RetransformAgent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent=ready");
    }

    public static void retransformTarget() throws Exception {
        Instrumentation inst = instrumentation;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation capability unavailable");
        }
        Class<?> target = null;
        int matches = 0;
        for (Class<?> candidate : inst.getAllLoadedClasses()) {
            if ("TargetService".equals(candidate.getName())) {
                matches++;
                target = candidate;
            }
        }
        System.out.println("matches=" + matches);
        if (matches != 1) {
            throw new IllegalStateException("Ambiguous or missing class");
        }
        System.out.println("modifiable=" + inst.isModifiableClass(target));
        System.out.println("primitive-modifiable=" + inst.isModifiableClass(int.class));
        System.out.println("array-modifiable=" + inst.isModifiableClass(String[].class));
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Selected class is not modifiable");
        }
        byte[] updated = Files.readAllBytes(Path.of("variant/TargetService.class"));
        ReplacementTransformer transformer = new ReplacementTransformer(target, updated);
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
            System.out.println("retransform=done");
        } finally {
            System.out.println("transformer-removed=" + inst.removeTransformer(transformer));
        }
    }
}
~~~

**Vì sao kiểm tra `matches != 1`?** Trong demo chỉ có một class với tên `TargetService`. Nếu có nhiều class loader chứa cùng tên đó, một chọn lựa tự động không an toàn; agent thật cần nhận diện loader/module mục tiêu thay vì giả định phần tử thứ nhất là đúng.

**Vì sao đọc `updated` trước `addTransformer`?** Callback diễn ra trên đường class processing; đọc file hoặc phụ thuộc framework nặng trong `transform` có thể chậm, tạo vòng nạp class hoặc lỗi I/O. Ở đây đọc file một lần trước, giữ bytes bất biến bằng `clone()`.

**Vì sao `finally` remove?** Ví dụ chỉ cần một lần retransform có kiểm soát. Gỡ registration tránh transformer tiếp tục tham gia các lần xử lý tương lai. **Không nhầm remove với undo:** class đã được đổi method vẫn giữ định nghĩa mới cho tới khi có một thao tác thay definition khác.

### 5.5. Tệp `App.java`

~~~java
public final class App {
    public static void main(String[] args) throws Exception {
        TargetService service = new TargetService();
        System.out.println("before=" + service.value());
        RetransformAgent.retransformTarget();
        System.out.println("after=" + service.value());
        System.out.println("new-instance=" + new TargetService().value());
    }
}
~~~

Dòng `new TargetService()` xuất hiện **trước khi agent tìm class**; đây là điểm bảo đảm lớp đã được JVM định nghĩa trong thí nghiệm. Chúng ta không cần gọi `Class.forName` để tạo nó, và không cần attach động vào JVM khác.

### 5.6. Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: RetransformAgent
Can-Retransform-Classes: true
~~~

Đây là manifest của **startup agent**. Lưu file với dấu xuống dòng cuối và `Premain-Class` trỏ chính xác đến lớp có `premain(String, Instrumentation)`. Để làm bài bằng dynamic attach, cần manifest và lifecycle `Agent-Class`/`agentmain` tương ứng, nhưng API tìm class và retransform sau khi đã nhận `Instrumentation` vẫn có cùng ý nghĩa.

### 5.7. Biên dịch và chạy

Trong một thư mục trống, tạo các file:

~~~text
work/
  ReplacementTransformer.java
  RetransformAgent.java
  TargetService.java
  App.java
  agent.mf
  variant/
    TargetService.java
~~~

Di chuyển vào thư mục `work` và chạy bằng **JDK 17+**:

~~~bash
javac --release 17 ReplacementTransformer.java RetransformAgent.java TargetService.java App.java

javac --release 17 -d variant variant/TargetService.java

jar --create --file retransform-agent.jar --manifest agent.mf ReplacementTransformer.class RetransformAgent.class

java -javaagent:retransform-agent.jar App
~~~

Hai phiên bản `TargetService.class` không được để đè lên nhau. `javac -d variant` đưa bản thay thế vào thư mục `variant`; `java` dùng root classpath mặc định `.` nên nạp bản `ORIGINAL` đầu tiên. Nếu thư mục làm việc không đúng hoặc thiếu `variant/TargetService.class`, lời gọi `Files.readAllBytes` sẽ thất bại trước retransform.

**Stdout đã kiểm chứng trên OpenJDK 24, biên dịch với `--release 17`:**

~~~text
agent=ready
before=ORIGINAL
matches=1
modifiable=true
primitive-modifiable=false
array-modifiable=false
transform-existing=TargetService
retransform=done
transformer-removed=true
after=INSTRUMENTED
new-instance=INSTRUMENTED
~~~

### 5.8. Đọc kết quả và liên hệ với hợp đồng API

| Dòng stdout | Điều chứng minh |
| --- | --- |
| `agent=ready` | JVM gọi `premain` và cung cấp `Instrumentation` |
| `before=ORIGINAL` | `TargetService` được định nghĩa trước retransformation; instance đang chạy code gốc |
| `matches=1` | `getAllLoadedClasses()` tìm được **một** class mang tên `TargetService` |
| `modifiable=true` | Class cụ thể có thể đổi definition trên JVM thử nghiệm |
| `primitive-modifiable=false`, `array-modifiable=false` | Primitive và array class không modifiable |
| `transform-existing=TargetService` | Transformer có `canRetransform=true` nhận callback cho class đã tồn tại |
| `retransform=done` | Yêu cầu `retransformClasses(target)` trả về bình thường |
| `transformer-removed=true` | Đăng ký transformer được gỡ; việc này **không** tự hoàn nguyên bytes đã áp dụng |
| `after=INSTRUMENTED` | Cùng instance nay thực hiện phần thân method đã được thay |
| `new-instance=INSTRUMENTED` | Instance mới của cùng class cũng dùng definition mới |

Kết quả này **không có nghĩa** mọi JVM đều hỗ trợ retransformation, mọi class đều modifiable hoặc một transformer có thể tự do thêm/xóa method. Nó chứng minh thứ tự API và ngữ nghĩa **trên một JVM đã kiểm tra capability** với class demo có cấu trúc tương thích.

## 6. Bên trong `retransformClasses`: bytes và thứ tự transformer

Khi gọi `retransformClasses(target)`, JVM không lấy **bytes đang thực thi** rồi tùy tiện nối thêm instrumentation theo kiểu copy-paste. Hợp đồng mô tả việc xây dựng lại definition:

1. Bắt đầu từ class-file bytes nền của lần định nghĩa ban đầu, hoặc bytes nền của **lần redefine gần nhất**.
2. Kết quả của các transformer **không hỗ trợ retransformation** (`canRetransform=false`) từ lần load/redefine trước được **tái áp dụng tự động**, không gọi lại `transform` của chúng.
3. Transformer **hỗ trợ retransformation** (`canRetransform=true`) được **gọi lại** theo thứ tự hợp đồng JVM, và output của transformer trước trở thành input cho transformer sau.
4. JVM kiểm tra và cố gắng áp dụng class definition mới. Nếu class-file bytes không hợp lệ hoặc vi phạm giới hạn, yêu cầu thất bại.

~~~text
Class-file bytes nền của class
   |
   +-- kết quả cũ transformer non-retransformable (tái áp dụng, không callback)
   |
   +-- transformer capable 1: transform(...)  (callback mới)
   |
   +-- transformer capable 2: transform(...)  (callback mới)
   |
   v
JVM verify + install class definition
~~~

Trong Java 17 API, nhiều nhóm Java/native transformer có thứ tự xác định; khi có nhiều agent, kết quả cuối cùng phụ thuộc vào **cả chuỗi**. Việc chọn class đúng và đăng ký transformer đúng flag không bảo đảm một agent khác sẽ không sửa bytes tiếp theo.

Một chi tiết khó: JVM có thể tổ chức lại constant pool hay một số attribute trong quá trình tạo lại bytes nền. Đừng lấy hash `classfileBuffer` rồi khẳng định nó phải trùng từng byte với file `.class` gốc trên đĩa. Một transformer production nên kiểm tra cấu trúc class và bảo đảm output hợp lệ, tránh cách suy luận dựa trên những byte offsets không ổn định.

**Không sửa `classfileBuffer` tại chỗ.** Nếu không đổi gì thì `return null`; nếu đổi thì trả mảng bytes mới.

## 7. Các giới hạn và hệ quả của việc thay class đang chạy

Retransformation là công cụ mạnh nhưng không phải phép "load phiên bản Java hoàn toàn khác" không giới hạn.

- **Không tùy ý đổi cấu trúc:** API/JVM TI có giới hạn với việc thêm/xóa method hoặc field, đổi chữ ký method, thay quan hệ superclass/interface hoặc các thuộc tính cấu trúc bị cấm. Ví dụ chỉ thay **method body** để nằm trong loại biến đổi được hỗ trợ.
- **Không tạo lại object:** Đối tượng `service` trong demo vẫn là instance cũ; chỉ lượt gọi method mới có thể chạy definition mới. JVM không tạo một đối tượng replacement rồi tráo reference.
- **Không reset static fields:** Các giá trị static còn nguyên; `<clinit>` không tự chạy lại chỉ vì retransform.
- **Active stack frames:** Nếu một method đã có frame đang chạy khi đổi definition, frame đó có thể tiếp tục bytecode cũ; những lần invoke mới dùng definition mới. Không coi retransformation là điểm đồng bộ logic cho tất cả thread.
- **Không bảo đảm phục hồi nguyên bản khi gỡ transformer:** `removeTransformer` chỉ hủy registration; không tự đổi lại class đã được JVM cài definition mới.
- **Không bảo đảm mọi class loader/module cho phép helper mới:** Nếu bytes mới gọi vào class trợ giúp, cần class loader và module access hợp lệ; lỗi như `NoClassDefFoundError` hoặc `IllegalAccessError` có thể xuất hiện dù bản thân classfile hợp lệ.
- **Không tự thay đổi tương lai:** Class vừa retransform có thể tiếp tục hoạt động với bytes mới, nhưng những class khác không tự được retransform theo tên package. Muốn nhiều class phải chọn đúng từng `Class<?>` và truyền một mảng đích có chủ đích.

Ở môi trường nóng, retransformation có thể liên quan tới safepoint, deoptimization hoặc những chi phí JVM khác tùy implementation. Không áp dụng hàng loạt lên hàng nghìn class chỉ vì API cho phép; nên chọn phạm vi nhỏ, đo latency và có điều kiện an toàn khi bật.

## 8. Tình huống lỗi: phân biệt "không tìm thấy", "không được sửa" và "bytes sai"

| Tình huống | Triệu chứng/exception | Hướng xử lý |
| --- | --- | --- |
| Class thực tế chưa loaded | `matches=0` khi lọc `getAllLoadedClasses()` | Chờ class được load, hoặc chủ động load dưới loader phù hợp nếu tác vụ cho phép; không cố retransform một tên chuỗi |
| Nhiều loader nạp class cùng tên | `matches>1` | Chọn theo defining loader/module, không lấy phần tử đầu tiên |
| Manifest thiếu `Can-Retransform-Classes: true` hoặc JVM không hỗ trợ | `isRetransformClassesSupported()==false`; có thể `UnsupportedOperationException` | Sửa manifest/đánh giá VM; phải khởi động agent đúng cách để capability có hiệu lực |
| Target là primitive/array hoặc class không modifiable | `isModifiableClass(target)==false`; có thể `UnmodifiableClassException` nếu vẫn yêu cầu | Bỏ qua và ghi rõ lý do; chọn class khác phù hợp |
| Transformer đăng ký mặc định `false` | Không thấy callback trong retransform | Dùng `addTransformer(transformer, true)` nếu được hỗ trợ; lưu ý ảnh hưởng cũ của transformer incapable |
| `ClassFileTransformer` chỉ trả `null` | `retransformClasses` có thể hoàn tất nhưng behavior không đổi | Xác nhận bộ lọc tên/loader, log callback và bytes đầu ra |
| Bytes mới sai tên class | `NoClassDefFoundError` | Kiểm tra binary name của class file, không tráo definition cho class khác |
| Classfile lỗi hoặc JDK bytecode không tương thích | `ClassFormatError` hoặc `UnsupportedClassVersionError` | Kiểm tra công cụ sinh bytecode/JDK đích và classfile version |
| Thay đổi cấu trúc không được phép | `UnsupportedOperationException` hoặc lỗi VM tương ứng | Giữ cấu trúc theo giới hạn retransform; chỉ sửa method body khi cần |
| Liên kết lớp/helper không hợp lệ | `LinkageError`, `ClassCircularityError`, `IllegalAccessError` | Kiểm tra class loader, modules, package visibility và class loading recursion |
| Truyền mảng class `null` hoặc phần tử `null` | `NullPointerException` | Kiểm tra đầu vào trước khi gọi |
| Đã gỡ transformer nhưng instrumentation còn chạy | `removeTransformer()==true` nhưng class vẫn đổi | Định nghĩa đã áp dụng không tự hoàn tác; muốn rollback phải thiết kế cách riêng |

**Hai ngoại lệ cần biết rõ:**

- `UnmodifiableClassException` là checked exception khi yêu cầu sửa lớp không được phép; kiểm tra `isModifiableClass` trước giúp tránh nhiều ca thất bại nhưng không thay thế xử lý lỗi.
- `UnsupportedOperationException` liên quan capability hoặc những thay đổi không được JVM hỗ trợ. Có thể xảy ra dù `isModifiableClass(target)==true` khi transformer tạo ra thay đổi cấu trúc bất hợp lệ.

Theo đặc tả, nếu `retransformClasses` ném exception, **không class nào trong tập đích được retransform thành công**. Tuy vậy, callback transformer có thể đã được gọi trước khi JVM kiểm tra và áp dụng bytes cuối cùng; vì thế **log callback không chứng minh hoàn tất**. Ngoài ra callback ném exception chưa bắt có thể bị JVM xử lý như `return null` rồi tiếp tục chuỗi, nên cần thiết kế diagnostics và test output chặt chẽ hơn là chỉ mong exception trong callback chặn thao tác.

## 9. Làm sao tìm và retransform nhiều lớp an toàn?

Trong ứng dụng thực, "tìm mọi class theo prefix" có thể quá rộng. Một phương án là xây danh sách theo **allowlist rõ ràng** gồm binary name, defining loader hoặc module, sau đó sàng lọc:

~~~java
// Đoạn minh họa bên trong agent, không phải file Java độc lập.
if (!inst.isRetransformClassesSupported()) {
    return;
}

List<Class<?>> selected = new ArrayList<>();
for (Class<?> clazz : inst.getAllLoadedClasses()) {
    if (!allowedNames.contains(clazz.getName())) continue;
    if (clazz.isArray() || clazz.isPrimitive()) continue;
    if (!inst.isModifiableClass(clazz)) continue;
    if (!matchesExpectedLoaderAndModule(clazz)) continue;
    selected.add(clazz);
}

if (!selected.isEmpty()) {
    inst.retransformClasses(selected.toArray(new Class<?>[0]));
}
~~~

Mã giả Java này **không biên dịch độc lập** vì thiếu `inst`, `allowedNames`, `matchesExpectedLoaderAndModule` và import collections. Nó chỉ thể hiện thứ tự lọc và API gọi. Với tên class trùng ở nhiều loader, `matchesExpectedLoaderAndModule` là chính sách dự án phải tự xác định; không bỏ bước này rồi coi mọi match là cùng đích.

`retransformClasses(Class<?>... classes)` nhận varargs, bao gồm mảng **rỗng** (không làm gì). Nó có thể nhận **nhiều class trong một yêu cầu** để đáp ứng các thay đổi liên quan nhau; JVM có hành vi all-or-none khi thao tác thất bại theo đặc tả. Tuy nhiên, để vận hành dễ kiểm soát:

1. Dùng nhóm nhỏ theo logical feature/module, tránh quét toàn bộ JVM không giới hạn.
2. Ghi rõ danh tính class theo *name + loader + module*; snapshot số lượng match và lý do loại trừ.
3. Kiểm tra cả capability và `isModifiableClass` cho từng class, đồng thời chấp nhận có điều kiện race đến lúc gọi.
4. Test bytecode trên JVM thực tế với cùng transformer chain.
5. Thực thi ở giai đoạn an toàn, có giám sát performance và ngưỡng thất bại.
6. Xác nhận observation từ class sau thao tác thay vì chỉ đếm callback.

Nếu class chưa loaded, bạn có thể **đăng ký transformer chờ lần define đầu tiên** thay vì ép load lớp chỉ để retransform. Chọn cách nào phụ thuộc vào mục tiêu: cần tác dụng ngay cho class đang chạy, hay chỉ áp dụng cho class sắp được định nghĩa.

## 10. Quy trình production an toàn và khả năng rollback

Một playbook thực tế:

### Trước yêu cầu

- **Xác định mục tiêu:** tên đầy đủ, loader/module, ứng dụng và method cần instrument; loại trừ framework/core class rủi ro.
- **Kiểm tra capability:** `Can-Retransform-Classes: true` trong JAR agent đã deploy, `isRetransformClassesSupported()==true` trong JVM thật.
- **Kiểm tra eligibility:** `getAllLoadedClasses` trả class cụ thể, không chọn nhầm loader; `isModifiableClass` là `true`.
- **Chuẩn bị bytes/transformer:** giữ method/field layout hợp lệ, chuẩn hóa class version, tránh biến đổi lặp hai lần và tránh tự load class helper trong callback.
- **Thiết kế failure policy:** lỗi một class có làm dừng agent không? có cần canary/allowlist không? log và cảnh báo ở đâu?

### Khi yêu cầu

- Đăng ký transformer với `canRetransform=true` (nếu cần callback).
- Gọi `retransformClasses` với đúng đối tượng `Class<?>` được chọn.
- Xử lý `UnmodifiableClassException`, `UnsupportedOperationException` và các `Error` phản ánh class bytes sai theo chiến lược an toàn. Không nuốt tùy tiện `Throwable` để hệ thống có vẻ "thành công".
- Nếu chỉ cần thao tác một lần, hủy đăng ký trong `finally` sau lời gọi. Gỡ transformer **không** khôi phục bytecode đã được áp dụng.

### Sau yêu cầu

- Ghi trạng thái **request succeeded** khi API trả về bình thường; xác minh **functional result** bằng một test/metric có ngữ nghĩa trên lớp đích.
- Đo CPU, latency, allocation/GC và xem callback có gây recursion/deadlock hay không.
- Đừng suy luận instance đã reset: active frames và state hiện tại có semantics riêng.
- Nếu cần rollback, dùng phương án đã được kiểm thử trước: transformer có khả năng sinh bytes cũ qua retransform, `redefineClasses` với bytes tương thích hoặc restart JVM không agent. Không giả định chỉ `removeTransformer` là rollback.
- Tránh giữ vô hạn các mảng class và transformer/loader references, nhất là với ứng dụng có hot deployment.

## 11. Những nhầm lẫn cần xóa bỏ

- **"`addTransformer(t, true)` sẽ tự xử lý lại mọi class đang loaded":** Không. Nó đăng ký callback; bạn vẫn cần `retransformClasses(target)` cho class đã tồn tại.
- **"Chỉ cần tìm theo tên class":** Không đủ khi nhiều defining class loader/module. Class identity mới là đích thật.
- **"`isModifiableClass(target)==true` nghĩa là đã bật retransformation":** Sai. Đây là hai điều kiện độc lập; phải kiểm tra `isRetransformClassesSupported()`.
- **"Array class hoặc primitive có thể retransform vì `Class<?>` tồn tại":** Sai. Chúng không modifiable.
- **"`Class.forName(name, false, loader)` chỉ tìm lớp đã load":** Sai. Nó có thể kích hoạt class loading, mặc dù không bắt buộc initialization.
- **"Transformer `canRetransform=false` được gọi lại khi retransform":** Sai. JVM dùng lại kết quả cũ của transformer đó mà không gọi callback.
- **"Thấy `classBeingRedefined != null` thì chắc chắn là retransformation":** Sai. Redefinition cũng dùng đối tượng `Class<?>` non-null.
- **"Một lần retransform thành công bảo đảm method đã instrument":** Sai. Transformer có thể không match hoặc trả `null`, hoặc một transformer sau đó có thể ghi đè kết quả.
- **"Đã remove transformer thì class tự trở về code gốc":** Sai. Remove chỉ bỏ registration, không thay definition đã cài.
- **"Có thể thêm field/method tùy ý khi retransform":** Không. JVM áp dụng giới hạn thay đổi cấu trúc, nên cần kiểm tra bytes đầu ra và version tương thích.

### Tài liệu chính thức

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, `isRetransformClassesSupported`, `retransformClasses` và ngoại lệ.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback `transform`, bytes đầu vào, các nhóm transformer và thứ tự áp dụng.
- [Java SE 17 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): thuộc tính manifest, `premain`/`agentmain` và cách JVM cấp quyền instrumentation.
