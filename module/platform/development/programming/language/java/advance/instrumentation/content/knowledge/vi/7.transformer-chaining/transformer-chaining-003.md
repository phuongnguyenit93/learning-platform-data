# Thứ tự bốn nhóm transformer Java, native và khả năng retransformation

> **Mục tiêu:** Hiểu thứ tự chuẩn của bốn nhóm `ClassFileTransformer` Java và `ClassFileLoadHook` native JVMTI; biết sự khác biệt giữa *retransformation incapable* và *retransformation capable*; dự đoán class bytes đi qua các transformer khi **load**, **redefine** và **retransform**; tự kiểm chứng thứ tự bằng Java 17+; nhận diện giới hạn để tránh đếm probe trùng hoặc giải thích sai log agent.

Bài học thuộc phần **Chuỗi biến đổi**. Đây là thứ tự JVM áp dụng biến đổi **class-file bytes**, không phải thứ tự thực thi các method của ứng dụng sau khi class đã nạp.

## 1. Một lớp có thể đi qua nhiều transformer

Trong cùng JVM, ta có thể cài coverage Java agent, profiler native JVMTI, tracing Java agent và một công cụ phân tích bytecode khác. Tất cả có thể quan tâm tới cùng `com/example/OrderService`. JVM không ghi đè class độc lập theo “agent cuối cùng thắng”; thay vào đó nó **ghép kết quả từng tầng**:

```text
Class bytes gốc
    │
    ▼
Transformer A → bytes A
    │
    ▼
Transformer B → bytes B (nhận bytes A làm đầu vào)
    │
    ▼
Transformer C → bytes C
    │
    ▼
Verifier / JVM áp dụng định nghĩa class
```

Java `ClassFileTransformer.transform(...)` có thể trả `null` nếu không thay đổi, hoặc một mảng `byte[]` mới nếu đã tạo class file hợp lệ. Khi một tầng trả `null`, bytes hiện hành **đi tiếp nguyên trạng**, không tự quay về bytes gốc. Native JVMTI `ClassFileLoadHook` cũng có thể giữ hoặc thay class data qua giao diện native.

Vấn đề quan trọng là **A, B, C được xếp theo quy tắc nào?** Nếu có cả Java transformer và native transformer, việc chỉ xem thời gian đăng ký toàn cục sẽ cho đáp án sai. JVM chia transformer thành đúng **bốn nhóm có thứ tự cố định**.

## 2. Bốn nhóm theo đặc tả JDK

Theo Javadoc của `ClassFileTransformer`, thứ tự biến đổi là:

| Thứ tự | Nhóm | Cơ chế | Retransformation |
| --- | --- | --- | --- |
| **1** | Java **retransformation incapable** | `Instrumentation.addTransformer(t, false)` hoặc `addTransformer(t)` | Không có callback mới khi retransform |
| **2** | Native **retransformation incapable** | JVMTI `ClassFileLoadHook` của environment incapable | Không có callback mới khi retransform |
| **3** | Java **retransformation capable** | `Instrumentation.addTransformer(t, true)` | Có callback mới khi retransform |
| **4** | Native **retransformation capable** | JVMTI `ClassFileLoadHook` của environment capable | Có callback mới khi retransform |

Hãy nhớ đúng chuỗi:

```text
1. Java incapable
       ↓
2. native incapable
       ↓
3. Java capable
       ↓
4. native capable
```

Đây là quy tắc JVM áp dụng **giữa các nhóm**, bất kể agent nào bắt đầu hoặc đăng ký trước. **Trong từng nhóm**, transformer được xử lý theo thứ tự đăng ký. Đối với native JVMTI, trong từng nhóm thứ tự các environment dựa trên thứ tự tạo environment theo đặc tả JVMTI; không xếp theo tên thư viện `.so`/`.dll`.

Từ “native” tại đây chỉ native JVMTI agent có callback **`ClassFileLoadHook`**. Nó không có nghĩa mọi method Java viết với keyword `native` đều là transformer, và cũng không có nghĩa một thư viện JNI bất kỳ tham gia chuỗi biến đổi.

### Ví dụ dễ nhầm về thứ tự đăng ký

Giả sử:

```text
09:00: Java capable C đăng ký
09:01: native capable D được bật
09:02: Java incapable A đăng ký
09:03: native incapable B được bật
```

Nếu một class được nạp **sau 09:03**, thứ tự biến đổi của nó vẫn là:

```text
A → B → C → D
```

Bảng giờ chỉ là tình huống giả định. Điều này không có nghĩa một transformer vừa được đăng ký có thể tự nhận lại sự kiện **class load đã xảy ra**. Class đã nạp trước đó cần một sự kiện cập nhật phù hợp, và khi cập nhật các nhóm tuân thủ quy tắc riêng.

### Khi nhiều transformer trong cùng nhóm

Java incapable A1 đăng ký trước Java incapable A2 thì A1 nhận bytes trước A2. Cả hai đều thuộc **nhóm 1**. Nếu Java capable C đăng ký trước cả A1 và A2, nó vẫn đứng **sau toàn bộ nhóm 1 và nhóm 2**.

Những phép biến đổi không nhất thiết giao hoán:

```text
A(B(originalBytes)) có thể khác B(A(originalBytes))
```

Một agent chèn probe ở method entry và agent khác viết wrapper có thể tạo kết quả khác nhau nếu đổi thứ tự. Vì thế việc biết chain là điều kiện cần khi phân tích lớp đã instrument.

## 3. Hai chiều phân loại: Java/native và incapable/capable

### Java transformer

`ClassFileTransformer` là interface thuộc module `java.instrument`. Java agent lấy `Instrumentation` qua `premain` lúc startup hoặc `agentmain` khi JVM cho phép nạp agent động. Các cách đăng ký:

```java
// Cú pháp trong mã agent có biến Instrumentation inst và transformer t:
inst.addTransformer(t);        // Nhóm 1, mặc định false
inst.addTransformer(t, false); // Nhóm 1
inst.addTransformer(t, true);  // Nhóm 3
```

**Capable** ở đây nghĩa là transformer **được gọi lại khi class retransform**. Nó không có nghĩa transformer luôn trả bytes mới, không có nghĩa nó được chạy trước các transformer khác, và không bảo đảm mọi class trong JVM đều có thể cập nhật.

### Native JVMTI transformer

Native agent có thể yêu cầu callback sự kiện `ClassFileLoadHook` trong JVMTI. Tại callback, nó nhận class data hiện tại và có thể cung cấp class data thay thế.

Một JVMTI environment được phân loại:

- **Incapable** nếu **chưa có capability** `can_retransform_classes` tại lần đầu bật `ClassFileLoadHook` trong environment đó.
- **Capable** nếu **đã có capability** `can_retransform_classes` trước lần đầu bật hook.

Đây là ràng buộc về **thời điểm sở hữu capability**. Không được giả định environment đã bật hook ở chế độ incapable sẽ tự đổi thành capable chỉ vì sau đó thử lấy thêm capability.

Ở native C/JVMTI, ý tưởng cấu hình là:

```c
// Mã C mang tính minh họa; thiếu bootstrap và xử lý lỗi.
jvmtiCapabilities capabilities = {0};
capabilities.can_retransform_classes = 1;
(*jvmti)->AddCapabilities(jvmti, &capabilities);

// Sau khi kiểm tra thành công, đăng ký ClassFileLoadHook,
// rồi mới bật JVMTI_EVENT_CLASS_FILE_LOAD_HOOK.
```

Đây **không phải chương trình C độc lập**. Native agent hoàn chỉnh còn cần `Agent_OnLoad`, `GetEnv`, `SetEventCallbacks`, `SetEventNotificationMode`, quản lý bộ nhớ cấp bởi JVMTI, error codes và build library cho hệ điều hành. Bài này tập trung vào **quy tắc nhóm**, không triển khai đầy đủ JVMTI agent.

**Quan trọng:** Java code không thể tạo hai nhóm native chỉ bằng cách gọi `Instrumentation.addTransformer`. Hai nhóm đó thuộc cơ chế JVMTI; ví dụ Java ở phần sau chỉ kiểm chứng trực tiếp nhóm 1 và nhóm 3.

## 4. Ba loại sự kiện: class load, redefine và retransform

Transformer có thể tham gia những sự kiện liên quan đến việc JVM tạo/cập nhật định nghĩa class:

| Sự kiện | Nguồn bytes đầu vào | Nhóm 1 và 2 | Nhóm 3 và 4 |
| --- | --- | --- | --- |
| **Class load lần đầu** | Bytes đưa vào định nghĩa class mới | Callback nếu áp dụng | Callback nếu áp dụng |
| **`redefineClasses`** | Bytes class mới do caller cung cấp | Callback nếu áp dụng | Callback nếu áp dụng |
| **`retransformClasses`** | Initial bytes của định nghĩa hiện tại, cùng kết quả incapable được tái áp dụng | **Không gọi callback**; reuse kết quả trước | **Gọi callback mới** |

Khi class load lần đầu hoặc redefine, chuỗi về mặt logic:

```text
initial bytes
   → [1] Java incapable (callback)
   → [2] native incapable (callback)
   → [3] Java capable (callback)
   → [4] native capable (callback)
   → verify/apply
```

Khi retransform:

```text
initial bytes của định nghĩa hiện tại
   → [1] reuse output Java incapable, KHÔNG callback
   → [2] reuse output native incapable, KHÔNG callback
   → [3] Java capable, callback MỚI
   → [4] native capable, callback MỚI
   → verify/apply
```

Cụm “callback nếu áp dụng” có nghĩa transformer/event đã được đăng ký/bật ở thời điểm liên quan và JVM xử lý được class đó. Đăng ký transformer sau khi một lớp đã load không làm sự kiện class load cũ phát lại ngay lập tức.

### Tại sao redefine và retransform khác nhau?

`Instrumentation.redefineClasses(ClassDefinition...)` nhận **class-file bytes mới** từ công cụ gọi. JVM đưa bytes mới vào chuỗi và gọi lại các nhóm transformer thích hợp, bao gồm incapable.

`Instrumentation.retransformClasses(Class<?>...)` không nhận một `byte[]` mới do caller truyền vào. JVM bắt đầu từ initial bytes của định nghĩa hiện tại, phục hồi các phần biến đổi incapable cũ, rồi gọi lại capable. Nếu lớp đã từng được redefine, initial bytes dùng cho retransform về sau tương ứng lần redefine gần nhất theo quy tắc JVM.

Vì thế:

```text
redefine    = có bytes mới từ caller + 4 nhóm có callback
retransform = có initial bytes + reuse 2 nhóm đầu + 2 nhóm sau callback
```

Không nên gọi cả hai thao tác bằng một tên chung “load lại class” rồi suy ra thứ tự callback giống nhau.

## 5. “Tái sử dụng output” thật sự nghĩa là gì?

Giả sử lớp `OrderService` ban đầu có bytes `B0`. Trong lần load:

```text
B0
 ├─ A (Java incapable)    → B1, có probe coverage
 ├─ B (native incapable)  → B2, có metadata bổ sung
 ├─ C (Java capable)      → B3, có probe trace phiên bản 1
 └─ D (native capable)    → B4, có probe sample phiên bản 1
```

Sau đó agent C/D thay đổi chính sách. Khi `retransformClasses` diễn ra:

```text
initial bytes của class
 ├─ A: reuse B1, không gọi A.transform lần nữa
 ├─ B: reuse phần biến đổi của B, không gửi hook mới tới B
 ├─ C: gọi transform mới, có thể tạo trace phiên bản 2
 └─ D: gửi hook mới, có thể tạo sample phiên bản 2
      → class bytes mới nếu hợp lệ
```

A/B **không bị xóa khỏi class**. Output của chúng được JVM **áp dụng lại nguyên trạng**, không yêu cầu tính toán lại. Nếu A đã chèn bytecode coverage thì hiệu ứng coverage tiếp tục tồn tại qua retransformation thành công, trừ khi một tầng khác tạo biến đổi làm thay đổi hiệu ứng đó.

Đây là lý do không nên đọc log như sau:

> “Không thấy log từ coverage transformer trong đợt retransform, vậy coverage probe đã biến mất.”

Kết luận đó sai: không có callback mới từ nhóm 1/2 là **hành vi chuẩn**.

### Không phải lấy bytes cuối rồi thêm mã vô hạn

Mô hình sai:

```text
SAI: B4 → A → B → C → D → B8 → A → ...
```

Mô hình đúng xuất phát từ **initial class-file bytes**, sau đó tái áp dụng phần incapable và gọi lại phần capable. Điều này giúp tránh tự động nhân đôi mọi biến đổi chỉ vì gọi retransform nhiều lần.

Tuy nhiên, nếu capable transformer không nhận diện được bytes đã do nhóm khác chèn probe và lại tạo một wrapper cùng ý nghĩa, hệ thống vẫn có thể đo trùng. “Bắt đầu từ initial bytes” không thay thế việc thiết kế transformer có thể phối hợp.

### “Initial bytes” có luôn bằng file `.class` trên đĩa?

Không nhất thiết. JDK nói rằng bytes đầu vào cho retransformation **có thể khác chi tiết nhị phân** so với bytes ban đầu từ `ClassLoader.defineClass` hoặc lần redefine. Constant pool có thể được tổ chức lại, một số attributes có thể khác hoặc thiếu, thứ tự method có thể thay đổi ở nơi thứ tự không có ý nghĩa.

Vì vậy không nên dựa vào `Arrays.equals(bytes, Files.readAllBytes(classPath))` như tiêu chuẩn duy nhất. Khi cần phân tích, hãy xem **semantics, class structure và bytecode hợp lệ**, không yêu cầu mọi offset luôn giữ nguyên.

## 6. Quy tắc callback và bytes ở từng tầng

Javadoc mô tả việc ghép transformer: nếu callback thứ nhất trả mảng `byte[]` mới thì callback tiếp theo nhận output đó trong `classfileBuffer`. Nếu trả `null`, không có thay đổi ở tầng đó.

Ví dụ giả định:

```text
T1 nhận B0, trả B1.
T2 nhận B1, trả null.
T3 nhận B1, trả B3.
```

Output sau T2 **là B1**, không phải B0. Java transformer phải coi input `classfileBuffer` là **read-only**. Muốn thay, nó phải tạo mảng bytes mới chứa class file đúng cấu trúc; không sửa trực tiếp input của callback.

### Transformer ném exception thì sao?

Nếu `transform(...)` ném exception mà không tự xử lý, theo hợp đồng Java transformer, JVM vẫn gọi những transformer phía sau và tiếp tục cố gắng load/redefine/retransform. Đối với tầng đó, exception có hiệu lực tương tự **trả `null`**. `IllegalClassFormatException` có thể dùng để báo class file đầu vào lỗi format cho chẩn đoán; đừng dùng exception như một “nút dừng chắc chắn” của toàn chuỗi.

Ngược lại, nếu callback trả **bytes không hợp lệ**, JVM có thể từ chối định nghĩa/cập nhật class ở bước verify/apply, sau khi callback của các tầng đã chạy. Dòng log “transform thành công” **không chứng minh** lớp đã được cài đặt thành công.

### Class đã được `redefine` hoặc `retransform` trong callback trông thế nào?

Trong Java `ClassFileTransformer`:

- `classBeingRedefined == null` đối với class load ban đầu.
- `classBeingRedefined != null` khi callback đang xử lý **redefine hoặc retransform**.

Tham số này **không tự phân biệt** hai thao tác cập nhật. Nếu bài lab chỉ gọi retransform thì ta biết callback với class hiện hữu đến từ thao tác đó **nhờ luồng chương trình**, không phải vì JVM trả riêng một flag `isRetransform`.

## 7. Kiểm tra capability trước khi đăng ký capable transformer

Java agent đăng ký chế độ capable nên kiểm tra:

```java
if (!instrumentation.isRetransformClassesSupported()) {
    throw new IllegalStateException(
            "Retransformation unavailable on this JVM/configuration");
}
instrumentation.addTransformer(myTransformer, true);
```

Đoạn mã trên là **minh họa trong agent** có sẵn `Instrumentation instrumentation` và `ClassFileTransformer myTransformer`.

Đối với agent JAR khởi động với `-javaagent`, manifest cần có:

```text
Premain-Class: MyAgent
Can-Retransform-Classes: true

```

`MyAgent` ở đây là tên lớp ví dụ, không phải tên của bài lab. `Can-Retransform-Classes: true` là điều kiện cần để JVM xem agent có yêu cầu capability; bản thân JVM còn phải hỗ trợ. Nếu `isRetransformClassesSupported()` là false, gọi `addTransformer(t, true)` có thể ném `UnsupportedOperationException`.

Ngoài capability toàn JVM, trước khi sửa một class cụ thể phải kiểm tra:

```java
if (!instrumentation.isModifiableClass(targetClass)) {
    throw new IllegalArgumentException("Target class cannot be modified");
}
instrumentation.retransformClasses(targetClass);
```

Hai dòng này được hiểu trong ngữ cảnh agent có `targetClass`. `isModifiableClass` và `isRetransformClassesSupported` hỏi **hai điều khác nhau**. `int.class` và class mảng không modifiable; những class đặc biệt khác cũng có thể có giới hạn.

Cũng cần phân biệt `isRedefineClassesSupported()` (capability redefine) với `isRetransformClassesSupported()` (capability retransform). Transformer incapable vẫn được gọi trong những đợt **redefine** phù hợp.

## 8. Bài thực hành Java 17+: đăng ký capable trước nhưng callback chạy sau

Ta sẽ tạo một Java agent đăng ký **capable trước**, rồi **incapable sau**. Khi class được load, callback incapable phải được gọi trước capable theo nhóm. Sau khi retransform, chỉ callback capable được gọi lại.

Để tập trung kiểm tra thứ tự, hai transformer **đều trả `null`**: không có bytecode nào bị thay. Đây là một thí nghiệm về **sự kiện và thứ tự callback**, không phải demo chèn probe thực sự.

### 8.1. Cấu trúc file

```text
transform-order-demo/
├── OrderAgent.java
├── WatchedTarget.java
├── DemoApp.java
└── agent.mf
```

**Tệp `WatchedTarget.java`:**

```java
public final class WatchedTarget {
    public String value() {
        return "OK";
    }
}
```

**Tệp `OrderAgent.java`:**

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class OrderAgent {
    private static Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        boolean capable = inst.isRetransformClassesSupported();
        System.out.println("agent: retransform=" + capable);

        if (!capable) {
            throw new IllegalStateException(
                    "This lab requires retransform capability");
        }

        // Đăng ký capable trước để quan sát thứ tự theo NHÓM.
        inst.addTransformer(logger("capable"), true);
        inst.addTransformer(logger("incapable"), false);
        System.out.println("agent: registered=capable-then-incapable");
    }

    private static ClassFileTransformer logger(String label) {
        return new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {

                if ("WatchedTarget".equals(className)) {
                    String phase = classBeingRedefined == null
                            ? "initial" : "existing";
                    System.out.println(
                            "transform: " + label + " " + phase);
                }
                return null; // Chỉ ghi nhận callback, không sửa bytecode.
            }
        };
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        if (instrumentation == null) {
            throw new IllegalStateException("Agent did not start");
        }
        if (!instrumentation.isModifiableClass(target)) {
            throw new IllegalStateException("Target not modifiable");
        }
        instrumentation.retransformClasses(target);
    }
}
```

**Tệp `DemoApp.java`:**

```java
public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("app: first load");
        Class<?> type = Class.forName("WatchedTarget");

        Object instance = type.getDeclaredConstructor().newInstance();
        System.out.println(
                "app: value=" + type.getMethod("value").invoke(instance));

        System.out.println("app: retransform");
        OrderAgent.retransform(type);

        System.out.println(
                "app: value=" + type.getMethod("value").invoke(instance));
    }
}
```

`Class.forName("WatchedTarget")` gọi nạp class mục tiêu **sau** khi `premain` đăng ký transformer. Bài lab chủ động dùng chuỗi tên lớp để tránh tham chiếu kiểu tĩnh trước thời điểm đó. Sau khi tạo object, chương trình yêu cầu JVM retransform **chính class ấy**.

**Tệp `agent.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: OrderAgent
Can-Retransform-Classes: true

```

Bảo đảm manifest kết thúc bằng newline, tốt nhất có một dòng trống kết thúc section.

### 8.2. Biên dịch và chạy

Lệnh Bash ở thư mục chứa bốn tệp:

```bash
mkdir -p out
javac -encoding UTF-8 -d out OrderAgent.java WatchedTarget.java DemoApp.java
jar --create --file order-agent.jar --manifest agent.mf -C out .
java -javaagent:order-agent.jar -cp out DemoApp
```

Tương đương trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -encoding UTF-8 -d out OrderAgent.java WatchedTarget.java DemoApp.java
jar --create --file order-agent.jar --manifest agent.mf -C out .
java -javaagent:order-agent.jar -cp out DemoApp
```

Để thao tác ít tệp, JAR ở đây chứa cả các class demo; trong ứng dụng thật nên đóng gói agent riêng. `-cp out` bảo đảm `DemoApp` và `WatchedTarget` có thể tìm thấy trên class path. Thí nghiệm dùng Java 17+ và JVM phổ biến hỗ trợ retransformation, như HotSpot/OpenJDK với capability được bật.

### 8.3. Stdout dự kiến

```text
agent: retransform=true
agent: registered=capable-then-incapable
app: first load
transform: incapable initial
transform: capable initial
app: value=OK
app: retransform
transform: capable existing
app: value=OK
```

Giải thích:

1. `premain` đăng ký **capable trước incapable**.
2. Khi class `WatchedTarget` được load, JVM vẫn gọi **incapable initial trước capable initial**. Nhóm 1 đi trước nhóm 3.
3. Khi gọi `retransformClasses`, JVM **không gọi** incapable transformer; kết quả cũ được tái sử dụng. `capable existing` xuất hiện.
4. `WatchedTarget.value()` vẫn trả `"OK"` vì cả hai transformer trả `null`. Callback được gọi **không có nghĩa** bytes đã thay đổi.

Không có nhóm 2/4 trong stdout vì bài lab không cài native JVMTI agent. Đừng tự suy ra output của native từ ví dụ Java; quy tắc native cần đối chiếu trực tiếp bằng JVMTI hoặc đọc đặc tả.

Nếu `isRetransformClassesSupported()` là false, agent dừng với thông báo lỗi ở `premain`, và bạn **không** thấy đủ output dự kiến. Nếu class không modifiable, phép kiểm ở `retransform` chủ động từ chối; đây là lỗi capability/đối tượng, không phải lỗi thứ tự nhóm.

### 8.4. Quan sát thứ tự **bên trong** nhóm

Nếu đăng ký thêm hai transformer incapable theo thứ tự:

```java
// Đoạn code minh họa đặt bên trong premain:
inst.addTransformer(logger("incapable-A"), false);
inst.addTransformer(logger("incapable-B"), false);
```

Khi load một class mới, `incapable-A` nhận callback trước `incapable-B` **trong cùng nhóm 1**. Hai transformer này vẫn đứng trước **mọi** transformer capable thuộc nhóm 3, ngay cả khi capable đăng ký sớm hơn.

### 8.5. Tại sao không đặt `return classfileBuffer` trong ví dụ?

Để chứng minh callback mà không thay bytes, `return null` là ý nghĩa rõ nhất. Javadoc yêu cầu không sửa mảng input; nếu tạo transformation thật, hãy tạo **mảng mới** chứa class file hợp lệ rồi trả mảng đó. Không dùng thí nghiệm callback để kết luận mã đã instrument.

## 9. Minh họa đủ bốn nhóm khi có native agent

Giả sử native JVMTI environment B (incapable) và D (capable) cũng lắng nghe `ClassFileLoadHook` của `WatchedTarget`. Khi load:

```text
Input ClassFile bytes
  │
  ├─ 1. Java incapable A: callback; thêm coverage
  │
  ├─ 2. Native incapable B: callback; thêm metadata
  │
  ├─ 3. Java capable C: callback; thêm trace v1
  │
  └─ 4. Native capable D: callback; thêm sample v1
          ↓
     Class definition v1
```

Sau một lần `retransformClasses` thành công:

```text
Initial ClassFile bytes của định nghĩa hiện tại
  │
  ├─ 1. Java incapable A: reuse coverage; KHÔNG callback
  │
  ├─ 2. Native incapable B: reuse metadata; KHÔNG callback
  │
  ├─ 3. Java capable C: callback; tạo trace v2
  │
  └─ 4. Native capable D: callback; tạo sample v2
          ↓
     Class definition v2
```

**Đây là mô phỏng logic, không phải stdout của chương trình Java ở mục 8.** Output bytecode thực tế phụ thuộc các agent và nội dung class.

Giả sử sau đó công cụ yêu cầu `redefineClasses` bằng bytes mới. Khi ấy **cả bốn nhóm** (nếu vẫn được đăng ký và áp dụng cho lớp) nhận callback mới theo A → B → C → D. Đó là điểm phân biệt rất quan trọng khi điều tra vì sao không thấy log từ native/Java incapable sau một thao tác cụ thể.

### Trường hợp trả `null` và nhiều tầng phối hợp

Giả sử A tạo coverage probe, B giữ nguyên, C thêm tracing, D giữ nguyên. Chuỗi kết quả:

```text
B0 ─ A → B1 ─ B(null) → B1 ─ C → B3 ─ D(no change) → B3
```

Không thể nói “B trả null nên coverage bị xóa”; B chỉ không đóng góp thay đổi mới. Nếu D không đổi, final bytes vẫn là output của C.

## 10. Hạn chế của retransformation và ý nghĩa với instrumentation

**Capable** không phải lời hứa rằng mọi chỉnh sửa class đều hợp lệ. `retransformClasses` có các điều kiện:

- JVM/agent phải hỗ trợ capability; Java agent yêu cầu `Can-Retransform-Classes: true` khi khởi động theo cơ chế manifest phù hợp.
- Class phải modifiable. Primitive types và array classes không modifiable; JVM có thể có những loại class khác không cho sửa.
- Class bytes mới phải thỏa điều kiện **legal redefinition**. Không được tùy ý thêm/xóa/đổi tên field, method; đổi method signature/modifiers, inheritance hoặc các structural attributes bị cấm. Việc thay **method body** phù hợp thường là mục tiêu của instrumentation.
- Callback được gọi trong quá trình xử lý trước verify/apply. Việc transformer log xong chưa khẳng định class mới đã được cài.
- `retransformClasses` không chạy lại class initializer, không reset static fields, và không làm object hiện có biến mất.
- Các stack frame đang chạy method phiên bản cũ có thể tiếp tục với bytecode cũ; lần gọi mới sử dụng định nghĩa mới sau khi JVM áp dụng thành công.

Việc cài đặt có thể thất bại vì `UnmodifiableClassException`, class bytes sai hoặc một giới hạn nền tảng. Với yêu cầu retransform nhiều class, thao tác phải xử lý theo semantics atomic được JDK/JVMTI mô tả; không coi callback riêng lẻ là bằng chứng tất cả class đã đổi.

### Không nhầm ba capability

| API | Câu hỏi |
| --- | --- |
| `isRetransformClassesSupported()` | JVM/cấu hình agent có cho phép **retransform** hay không? |
| `isRedefineClassesSupported()` | JVM/cấu hình agent có cho phép **redefine** hay không? |
| `isModifiableClass(clazz)` | **Class cụ thể** có phải loại có thể sửa định nghĩa không? |

Một câu trả lời `true` trong bảng không thay thế hai câu hỏi còn lại. Native JVMTI lại có capability riêng tại environment tương ứng. Không tự coi “có Java capable transformer” đồng nghĩa native capable hook chắc chắn đã bật.

## 11. Những lỗi triển khai và đọc log phổ biến

### Sai 1: Java transformer luôn chạy trước native

Sai. **Native incapable (nhóm 2)** đứng trước **Java capable (nhóm 3)**. Hãy kiểm tra đủ bốn nhóm.

### Sai 2: `canRetransform=true` giúp transformer giành ưu tiên đầu tiên

Sai. Capable thuộc nhóm 3 đối với Java, sau cả nhóm 1 và 2. Thứ tự đăng ký trước/sau chỉ so được trong cùng nhóm.

### Sai 3: Nhóm incapable “không tham gia” retransform

Sai về **kết quả**. JVM không gọi callback nhóm 1/2, nhưng **replay output trước đó**. Nếu coverage probe vẫn có trong bytecode thì nó vẫn tiêu thụ CPU ở runtime.

### Sai 4: `redefineClasses` cũng bỏ qua incapable

Sai. Với redefine, cả incapable và capable đều được gọi lại theo thứ tự nhóm, dựa trên bytes từ `ClassDefinition`.

### Sai 5: Trả `null` làm mất mọi thay đổi trước

Sai. `null` chỉ là không đổi **tầng hiện tại**. Chaining vẫn giữ kết quả của những tầng trước.

### Sai 6: `classBeingRedefined != null` chứng tỏ callback do retransform

Sai. Cả redefine lẫn retransform đều có class hiện hữu. Cần kết hợp sự kiện do tool yêu cầu và log từ tầng điều phối.

### Sai 7: `removeTransformer` lập tức gỡ probe khỏi class đang chạy

Sai. `removeTransformer` tác động việc đăng ký cho **sự kiện sau đó**; bytes class đã cài có vòng đời khác. Do class loading đa luồng, callback còn có thể đến sau khi một transformer bị remove. Không suy luận việc gỡ agent/transformer là rollback toàn bộ class.

### Sai 8: Có capability thì class nào cũng sửa được

Sai. Cần kiểm tra class cụ thể, các hạn chế structural và tính hợp lệ class-file bytes.

### Sai 9: Throw exception trong transformer sẽ chặn các transformer sau

Sai đối với hợp đồng Java callback: JVM vẫn gọi tiếp và hành vi của tầng ném exception tương đương không biến đổi. Nếu muốn từ chối cài đặt, phải hiểu lỗi ở giai đoạn verify/apply và cách xử lý của thao tác gọi.

### Sai 10: Java keyword `native` là native JVMTI transformer

Sai. Native ở sơ đồ là agent dùng JVMTI `ClassFileLoadHook`, không phải method có `native` modifier, JNI wrapper hoặc `System.loadLibrary` thông thường.

## 12. Checklist thiết kế chain nhiều agent

1. **Xác định class mục tiêu:** dùng internal class name, loader, module và phiên bản JDK, không chỉ simple class name.
2. **Liệt kê transformer theo nhóm:** Java incapable, native incapable, Java capable, native capable; biết rõ `canRetransform`/JVMTI capability.
3. **Ghi thứ tự bên trong nhóm:** phân biệt thứ tự đăng ký Java và thứ tự environment JVMTI; không tạo một thứ tự timestamp duy nhất cho tất cả.
4. **Phân biệt event:** class load, redefine hay retransform. Với retransform, không chờ callback nhóm 1/2.
5. **Biết input bytes:** từ định nghĩa mới, redefine bytes, hoặc initial bytes của định nghĩa hiện tại với incapable output reused.
6. **Bảo toàn hợp đồng biến đổi:** không sửa input `classfileBuffer`; trả `null` hoặc bytes mới hợp lệ; xử lý đúng method signatures, frames, exception flow.
7. **Tránh recursion:** loại trừ lớp của agent/helper; cẩn thận với logger và classloader gọi lại từ `transform`.
8. **Tránh probe lặp:** nhận diện phép đo của từng tầng, không đếm mọi wrapper/bridge như nhiều thao tác nghiệp vụ độc lập.
9. **Đo chi phí:** callback có chi phí biến đổi khi load/redefine/retransform; probe cài vào bytes có chi phí chạy ở mọi lần gọi phương thức.
10. **Kiểm chứng kết quả:** thử `isModifiableClass`, API success, bytecode/class loader đúng và hành vi runtime; log callback chưa đủ.
11. **Lập kế hoạch phục hồi:** remove transformer không tự phục hồi class; phải có chiến lược update hợp lệ hoặc restart với cấu hình nhất quán.
12. **Kiểm thử tương thích:** thử cả JVM/JDK và tổ hợp agent trong môi trường mục tiêu; một chain có thêm JVMTI native agent có thể thay đổi bytes đưa vào Java capable.

### Một chuỗi log chẩn đoán hữu ích

Khi có thể kiểm soát code agent, ghi tối thiểu:

```text
class=<internal-name>
loader=<loader-identity>
event=<load|redefine|retransform do tầng điều phối biết>
group=<1|2|3|4>
inputSize=<bytes>
outputSize=<bytes hoặc unchanged>
```

Các giá trị trong `text` này là **mẫu trường log**, không phải output thực. Trong production, tránh in toàn bộ bytecode hoặc dữ liệu nhạy cảm. Nếu cần hash, phân biệt hash bytes với tương đương semantic: JVM có thể tổ chức lại constant pool khi retransform.

## 13. Câu hỏi tự kiểm tra

**1.** Java capable đăng ký lúc 09:00, Java incapable đăng ký lúc 09:05. Class mới load lúc 09:10; ai chạy trước?  
**Đáp:** Java incapable, vì nhóm 1 đứng trước nhóm 3.

**2.** Native incapable so với Java capable: nhóm nào trước?  
**Đáp:** Native incapable là nhóm 2, đứng trước Java capable nhóm 3.

**3.** Một class đã được instrument bởi Java incapable. Khi retransform, callback của nó không chạy. Có mất hiệu ứng instrumentation không?  
**Đáp:** Không tự mất. JVM tái sử dụng kết quả của transformer incapable từ lần load/redefine trước.

**4.** Khi `redefineClasses`, các nhóm incapable có callback không?  
**Đáp:** Có, nếu đang đăng ký/áp dụng, vì redefine đưa bytes mới vào chuỗi và khác retransform.

**5.** `addTransformer(t)` tương đương overload nào?  
**Đáp:** `addTransformer(t, false)`.

**6.** Bật native `ClassFileLoadHook` trước khi sở hữu `can_retransform_classes`; sau này môi trường sẽ thuộc nhóm 4?  
**Đáp:** Không theo quy tắc phân loại JVMTI; capability phải có trước **lần đầu bật hook** để môi trường được xem là capable.

**7.** `transform` nhận bytes đã qua tầng trước hay luôn nguyên bản?  
**Đáp:** Nhận bytes hiện hành của chuỗi; output của tầng trước là input của tầng kế tiếp.

**8.** `retransformClasses` có khởi tạo lại static fields không?  
**Đáp:** Không. Class initializer không chạy lại chỉ vì retransform.

**9.** `classBeingRedefined != null` đủ phân biệt `redefine` và `retransform` không?  
**Đáp:** Không. Cả hai đều cho class đang tồn tại.

**10.** Vì sao bài lab không chứng minh thứ tự native?  
**Đáp:** Vì chỉ dùng Java `ClassFileTransformer`, không cài JVMTI `ClassFileLoadHook`; native cần agent/capability riêng.

## 14. Tài liệu chuẩn

- [JDK 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): bốn nhóm và thứ tự áp dụng, chaining, xử lý `null`/exception.
- [JDK 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer, capability, retransform và redefine.
- [JDK 21 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent startup, manifest và ngữ cảnh nhận `Instrumentation`.
- [JDK 21 — JVM Tool Interface (JVMTI)](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): `ClassFileLoadHook`, `can_retransform_classes`, thời điểm bật hook và trình tự native.

**Ghi nhớ:** **1. Java incapable → 2. native incapable → 3. Java capable → 4. native capable.** Khi **load/redefine**, nhóm liên quan được gọi theo trật tự này; khi **retransform**, hai nhóm incapable **không có callback mới nhưng kết quả cũ vẫn được tái áp dụng**, rồi hai nhóm capable chạy. Luôn xét cả **loại event**, **thứ tự nhóm** và **nguồn class bytes** trước khi phân tích một kết quả instrumentation.