# Native method prefix và phạm vi sử dụng của công cụ Instrumentation (Java 17+)

## 1. Tóm tắt: native prefix giải quyết vấn đề nào?

Java agent có thể dùng `ClassFileTransformer` chèn bytecode để đo thời gian, đếm lời gọi hoặc thêm tracing cho **phương thức Java thông thường**. Nhưng một phương thức khai báo với từ khóa `native` không có Java bytecode body để instrument. Nó là điểm vào mã native thông qua **Java Native Interface (JNI)**. Muốn thêm logging/metrics *quanh một lời gọi JNI* ở phía Java, một công cụ chuyên biệt có thể tạo **phương thức Java wrapper** và đổi tên native declaration gốc để wrapper gọi vào.

Việc đổi tên native declaration có thể làm JVM không tìm được symbol hoặc đăng ký JNI function tương ứng tên cũ. **Native method prefix** trong `java.lang.instrument.Instrumentation` giải quyết đúng tình huống hẹp đó: nếu native resolution bình thường không thành công, JVM có thể **thử lại dựa trên prefix** được đăng ký cùng `ClassFileTransformer`.

Hai API chính:

- `boolean Instrumentation.isNativeMethodPrefixSupported()`: JVM trong cấu hình agent hiện tại có hỗ trợ capability này hay không.
- `void Instrumentation.setNativeMethodPrefix(ClassFileTransformer transformer, String prefix)`: khai báo prefix mà **transformer đã đăng ký** sử dụng khi biến một native method thành wrapper + renamed native method.

**Không hiểu nhầm:** gọi `setNativeMethodPrefix` **không** sửa bytecode, **không** tự tạo wrapper, **không** patch native library, **không** tải DLL/.so, **không** làm cho mọi native method đều được profiling. Nó chỉ tác động tới *fallback handling của JNI native method resolution*.

Bài thuộc nhóm **Instrumentation** trong module Java 6, nhưng chỉ sử dụng các API vẫn còn phù hợp trên **Java 17, Java 21 và Java 25**. Các ví dụ hoàn chỉnh được biên dịch với `javac --release 17`. Cơ chế có từ trước vẫn được Oracle Javadoc 17/25 mô tả; giới thiệu sớm không có nghĩa tính năng đã bị loại bỏ.

### Mục tiêu

Sau bài, bạn có thể giải thích native wrapper, hai kiểu JNI native resolution, điều kiện manifest `Can-Set-Native-Method-Prefix`, vòng đời transformer, các exceptions, giới hạn class đã load, thứ tự nhiều agents, cách kiểm thử và khi nào nên chọn các công cụ observability khác.

## 2. Ba khái niệm phải tách bạch

| Thành phần | Vai trò | Không tự thực hiện |
| --- | --- | --- |
| `ClassFileTransformer` | Nhận bytes của class file trước class definition; có thể trả bytes mới nếu muốn rewrite. | Không tự liên kết JNI library hoặc cấp native prefix. |
| `Instrumentation.setNativeMethodPrefix` | Nói với JVM prefix của transformer để thử lại native resolution khi normal lookup thất bại. | Không biến native declaration thành Java wrapper, không viết native code. |
| JNI native library | Cung cấp native function để Java native method có thể gọi, qua automatic name lookup hoặc `RegisterNatives`. | Không tự thêm Java metrics/tracing wrapper. |

Ví dụ: một Java application có method `native int read(int id)`. Nếu application chỉ muốn gọi native library đúng cách, cần JNI library/signatures/`System.loadLibrary` hoặc `System.load` phù hợp, **không cần `setNativeMethodPrefix`**. Chỉ khi có agent **cố tình đổi cấu trúc method** để thêm Java wrapper thì native prefix mới có thể cần.

### 2.1. Tại sao không chèn mã trực tiếp vào native method?

Method Java:

```java
int plus(int a, int b) {
    return a + b;
}
```

có `Code` attribute trong class file; transformer có thể thay đổi bytecode nếu làm đúng verifier/stack-map constraints. Trong khi:

```java
native int read(int id);
```

không chứa instructions Java. Phần thi hành thuộc native library và JNI binding. Không có body Java để công cụ “chèn thêm một dòng trước return”. Một agent cần *đổi cấu trúc Java-level method* hoặc dùng profiler/JVMTI/native tracing ở tầng khác.

### 2.2. Native prefix là tiền tố của **method name**

Với prefix `$NP362$`, transformed native method tên `$NP362$read`, tức chuỗi đặt **trước** `read`. Tài liệu có câu “appended prefix” theo nghĩa gắn tiền tố vào tên, không phải thêm hậu tố vào cuối.

Prefix quá chung chung như `wrapped_` dễ trùng method/symbol có sẵn; nên chọn chuỗi đủ đặc trưng, nhất quán giữa code transformer và `setNativeMethodPrefix`. Không có một “prefix mặc định” áp dụng cho tất cả agents.

## 3. Trước và sau quá trình wrap native method

### 3.1. Trước transformation

Giả sử class gốc:

```java
package sample;

public final class NativeApi {
    public native int read(int id);
}
```

**Đây là source minh họa, không phải chương trình chạy độc lập.** Muốn gọi `read` phải có native library cung cấp/bind function JNI tương ứng. Một export dạng dễ hiểu có thể là `Java_sample_NativeApi_read`. Tên JNI export thật chịu quy tắc *name mangling* và overload signatures của JNI spec; không nên tự ghép chuỗi bằng ví dụ này khi viết C.

### 3.2. Cấu trúc do transformer có thể tạo ở class-load time

Một kết quả Java-level **tương đương về ý tưởng**, không phải mã nguồn transformer hoàn chỉnh:

```java
package sample;

public final class NativeApi {
    public int read(int id) {
        long start = System.nanoTime();
        try {
            return $NP362$read(id);
        } finally {
            long elapsed = System.nanoTime() - start;
            Metrics.observe(elapsed);
        }
    }

    private native int $NP362$read(int id);
}
```

**Chỉ là mã giả giải thích cơ chế**, vì `Metrics`, JNI implementation và bytecode rewriting chưa được cung cấp. Không được biên dịch/chạy và gán một stdout tưởng tượng cho mẫu này.

Từ đó ta có:
- `read` trở thành **Java wrapper**, có bytecode và có thể ghi metrics.
- `$NP362$read` là **native declaration mới** do transformer tạo, vẫn không có bytecode body.
- Native implementation bên dưới có thể tiếp tục mang tên/binding của `read` ban đầu.
- JVM cần biết rằng nếu không tìm được native implementation cho tên đã prefix, nó có thể **thử lại với tên gốc**.

Không chỉ đổi tên text trong Java source rồi hy vọng JNI tự hiểu; class file phải hợp lệ, method flags/descriptors và wrapper call phải được transformer tạo đúng.

### 3.3. Native resolution sau khi wrap

```text
Lúc class được định nghĩa:
  ClassFileTransformer:
    native read(int id)
      -> Java wrapper read(int id)
      -> native $NP362$read(int id)

Lúc native $NP362$read cần liên kết:
  Bước 1: normal JNI lookup/registration
     method($NP362$read) -> nativeImplementation($NP362$read)
  Nếu thất bại và transformer đã đăng ký prefix:
  Bước 2: prefix-aware fallback
     method($NP362$read) -> nativeImplementation(read)

Nếu native function tương thích:
  Java wrapper read -> $NP362$read -> native implementation read
```

**Thứ tự quan trọng:** normal resolution xảy ra trước, prefix fallback chỉ được xét sau khi normal resolution thất bại. Việc đã gọi `setNativeMethodPrefix` không chứng minh một native method cụ thể chắc chắn resolve thành công.

## 4. Hai cơ chế JNI liên kết phương thức

### 4.1. Automatic JNI lookup

Native library có thể export JNI function theo quy tắc tên tự động. Với class `sample.NativeApi` và method `read`, một tên dạng dễ đọc là:

```text
Java method                 JNI export/function (minh họa)
read(int)                   Java_sample_NativeApi_read
$NP362$read(int)            Java_sample_NativeApi_$NP362$read
```

Tên chứa ký tự đặc biệt trong JNI export thật phải **mangling** theo specification; bảng chỉ diễn giải sự khác biệt tên ở mức khái niệm.

Khi một JVM biết prefix gắn với transformer, nó có thể thử automatic lookup theo tên đã đổi, sau đó thử cách không có prefix. Nếu native library vẫn export function cho `read`, JNI có cơ hội liên kết thành công mà library không cần build lại với tên của agent.

### 4.2. Explicit `RegisterNatives`

Native library cũng có thể gọi `RegisterNatives` để ánh xạ tên/signature Java native method tới native function pointer:

```text
Tên đăng ký gốc: read
JNI signature:  (I)I
Function pointer: nativeImplRead

Sau class transformation:
  read(int)         là Java wrapper, không còn native
  $NP362$read(int)  là native method

Khi mapping thông thường không khớp,
JVM có thể thử lại tên Java có prefix:
  $NP362$read(int) <-> nativeImplRead
```

Theo Oracle Javadoc, `setNativeMethodPrefix` hỗ trợ fallback cả ở tình huống `RegisterNatives` và automatic resolution, nhưng **hai cơ chế không phải cùng một thao tác**. Bản đồ trên minh họa ý nghĩa chứ không phải source C/JNI runnable.

**Hệ quả:** trước khi chẩn đoán `UnsatisfiedLinkError`, phải biết library dùng `RegisterNatives` hay JNI exported symbols, và target class thực sự đã được transformer wrap hay chưa.

### 4.3. Không “đón đầu” bình thường

Normal resolution thắng khi tìm được native function phù hợp. Vì vậy nếu prefix của agent trùng tên native method/symbol vốn tồn tại, JVM có thể liên kết theo đường không mong đợi hoặc gây xung đột. Dùng prefix độc nhất với agent và kiểm thử end-to-end để tránh va chạm.

## 5. Instrumentation API và vòng đời Java agent

### 5.1. Lấy Instrumentation từ JVM

`Instrumentation` là interface thuộc package `java.lang.instrument`, module `java.instrument`. JVM truyền đối tượng cho Java agent qua:

```java
public static void premain(String agentArgs, Instrumentation inst) {
    // Đăng ký transformer, kiểm tra capability và cấu hình prefix.
}
```

Đây là snippet, không độc lập. Với startup agent, trong JAR manifest phải có `Premain-Class`, ứng dụng chạy:

```bash
java -javaagent:my-agent.jar -cp classes Main
```

Không tự `new Instrumentation()`, không cast objects tùy ý để lấy quyền biến đổi classes. Trên một số JVM có thể có `agentmain` dùng với cơ chế attach/dynamic loading, nhưng khả năng đó phụ thuộc runtime/security policy. Với nhu cầu đổi method structure trước class load, **startup `-javaagent` dễ kiểm soát và dễ kiểm thử hơn**.

### 5.2. Hai API chính

```java
boolean supported = inst.isNativeMethodPrefixSupported();
if (supported) {
    inst.setNativeMethodPrefix(transformer, "$NP362$");
}
```

**Snippet:** `transformer` phải là **cùng object instance đã đăng ký** qua `inst.addTransformer(transformer, ...)`, không chỉ là một object cùng class.

`isNativeMethodPrefixSupported()` là một capability **tùy chọn**; trong một JVM instantiation, kết quả lặp lại của nó phải ổn định theo Javadoc. Nếu `false`, đừng gọi set rồi cho rằng native wrapping vẫn hoạt động; agent phải có fallback hoặc lỗi khởi tạo rõ.

### 5.3. Agent JAR manifest

Main manifest:

```text
Manifest-Version: 1.0
Premain-Class: NativePrefixAgent
Can-Set-Native-Method-Prefix: true
```

Chính xác tên attribute **`Can-Set-Native-Method-Prefix`**; nó là manifest entry, không phải một Java system property. Khi không có hoặc đặt false, mặc định capability không được agent yêu cầu.

**Capability tách biệt:**
- `Can-Set-Native-Method-Prefix: true` cho phép xin native-prefix support.
- `Can-Retransform-Classes: true` xin retransform capability.
- `Can-Redefine-Classes: true` xin redefine capability.

Không cái nào tự động cấp hai cái còn lại. Ngay cả khi manifest true, **JVM vẫn có thể không hỗ trợ optional capability**, nên code phải kiểm tra kết quả thực tế.

### 5.4. Thứ tự addTransformer → setNativeMethodPrefix

```java
ClassFileTransformer transformer = /* instance đã được tạo */;
inst.addTransformer(transformer, false);

if (inst.isNativeMethodPrefixSupported()) {
    inst.setNativeMethodPrefix(transformer, "$NP362$");
}
```

Đây là snippet trong `premain`. Đưa transformer chưa add vào `setNativeMethodPrefix` là `IllegalArgumentException`. `addTransformer(..., false)` xác định transformer **không có yêu cầu retransform callback**, không ảnh hưởng đến điều kiện native prefix manifest.

`removeTransformer(transformer)` unregister transformer, nhưng do class loading đa luồng có thể vẫn nhận callback đang diễn ra sau remove. Transformer thật phải thread-safe và chú ý race. Cũng không nên đăng ký **cùng object transformer nhiều lần** để tránh sequence/prefix khó dự đoán.

### 5.5. prefix null hoặc chuỗi rỗng

`setNativeMethodPrefix(transformer, null)` hoặc `setNativeMethodPrefix(transformer, "")` tắt việc retry native resolution cho transformer này. Nó **không xóa bytecode wrapper đã tạo**, không hủy những native bindings đã hoàn thành và không load lại library. Không nên tắt prefix trong khi còn wrapper native chưa resolve mà agent vẫn cần sử dụng.

## 6. Ngoại lệ và behavior khi JVM không hỗ trợ

| Điều kiện | API behavior | Hướng xử lý |
| --- | --- | --- |
| Transformer truyền vào là `null` | `NullPointerException` | Khởi tạo transformer đúng, không đặt prefix trên null. |
| Transformer chưa đăng ký | `IllegalArgumentException` | Gọi `addTransformer` trước, dùng đúng instance. |
| `isNativeMethodPrefixSupported()==false` | `setNativeMethodPrefix` ném `UnsupportedOperationException` | Tôn trọng optional capability; disable feature hoặc fail theo chính sách. |
| Prefix là `null` | Không retry native resolution cho transformer. | Chỉ dùng khi muốn hủy setting, không phải “tự chọn prefix”. |
| Prefix là `""` | Tương tự null. | Chọn prefix không rỗng khi cần fallback. |
| Native implementation không tìm thấy | Có thể `UnsatisfiedLinkError` khi liên kết/gọi native method. | Xem JNI library/ABI/symbol/signature/prefix/transformer. |
| Transformer tạo bytes sai | JVM verify/define class có thể fail. | Kiểm tra classfile validity và rewrite library. |

**Không bắt mọi lỗi rồi im lặng tiếp tục** nếu mục tiêu chính của tool là thu native metrics bắt buộc. Nếu native instrumentation chỉ là tùy chọn, in một thông báo có cấu trúc và giữ các metrics Java bình thường theo policy.

## 7. Nhiều transformers: mỗi công cụ có prefix riêng

Giả sử ba transformers chạy lần lượt:

```text
Native method ban đầu:
   foo

Transformer A (prefix $A$):
   Java wrapper foo          -> native $A$foo

Transformer B (prefix $B$):
   Java wrapper $A$foo       -> native $B$$A$foo

Transformer C (prefix $C$):
   Java wrapper $B$$A$foo    -> native $C$$B$$A$foo
```

Đây là mô hình về tên methods sau khi mỗi transformer wrap; nếu transformer B không wrap, kết quả có thể là `$C$$A$foo`. Oracle Javadoc chỉ rõ logic prefix cho **wrapper trung gian thực sự tồn tại**. Không có quy tắc tự thêm mọi prefix của tất cả agents vào mọi native method.

### Các nguyên tắc phối hợp

- Mỗi `ClassFileTransformer` có prefix riêng, đúng chuỗi mà nó dùng để tạo renamed native method.
- Transform callbacks theo thứ tự registration **trong nhóm tương ứng**; retransformation capable/incompatible và native JVMTI transformers có các nhóm riêng theo Javadoc.
- Một transformer có thể nhìn thấy class bytes đã được transformer trước thay đổi.
- `setNativeMethodPrefix` không thay bytecode của transformer khác, không buộc các agents tương thích.
- Nếu có nhiều profilers/coverage agents, hãy kiểm thử agent order, prefix collisions, target class load order và JNI binding thực tế.
- Không giả định việc thay đổi thứ tự `-javaagent` giữa hai môi trường là vô hại.

### Vì sao không dùng một prefix ngắn cho mọi tool?

Prefix như `wrapped_` có thể trùng method có sẵn hoặc prefix của công cụ khác. Normal JNI resolution được thử trước fallback, nên collision có thể làm method resolve không như dự kiến. Dùng prefix có namespace/tool identifier đủ đặc trưng và cố định qua transformer/manifest lifecycle.

## 8. Demo chạy được trên Java 17+: capability probe

Ví dụ **chỉ cần JDK**, không cần JNI native library hoặc Byte Buddy/ASM. Hai chương trình:
- `NativePrefixAgent.java`: nhận Instrumentation, kiểm tra capability, đăng ký transformer **no-op**, kiểm tra ngoại lệ, set/disable prefix, rồi remove.
- `NativePrefixApp.java`: application đơn giản chứng minh `premain` chạy trước main.

**Phân định rõ:** no-op transformer trả `null`, **không tạo Java wrapper/native declaration mới**. Vì vậy kết quả demo chứng minh **hành vi API và manifest**, không chứng minh real JNI linking fallback. Thực hành wrapper thật phải dùng một bytecode rewriting library phù hợp và native toolchain; tài liệu không bịa stdout cho phần đó.

### 8.1. File NativePrefixAgent.java hoàn chỉnh

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class NativePrefixAgent {
    private static final String PREFIX = "$NP362$";

    public static void premain(String options, Instrumentation inst) {
        boolean supported = inst.isNativeMethodPrefixSupported();
        System.out.println("agent.supported=" + supported);

        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String name, Class<?> type, ProtectionDomain domain,
                    byte[] bytes) {
                return null; // No class rewriting: capability demo only.
            }
        };

        if (supported) {
            boolean unregisteredRejected = false;
            try {
                inst.setNativeMethodPrefix(transformer, PREFIX);
            } catch (IllegalArgumentException expected) {
                unregisteredRejected = true;
            }
            if (!unregisteredRejected) {
                throw new AssertionError("unregistered transformer accepted");
            }
            System.out.println("agent.unregisteredRejected=" + unregisteredRejected);
        }

        inst.addTransformer(transformer, false);
        try {
            if (supported) {
                boolean nullRejected = false;
                try {
                    inst.setNativeMethodPrefix(null, PREFIX);
                } catch (NullPointerException expected) {
                    nullRejected = true;
                }
                if (!nullRejected) {
                    throw new AssertionError("null transformer accepted");
                }
                System.out.println("agent.nullRejected=" + nullRejected);

                inst.setNativeMethodPrefix(transformer, PREFIX);
                System.out.println("agent.prefixSet=true");

                inst.setNativeMethodPrefix(transformer, null);
                System.out.println("agent.prefixDisabled=true");
            } else {
                boolean unsupportedRejected = false;
                try {
                    inst.setNativeMethodPrefix(transformer, PREFIX);
                } catch (UnsupportedOperationException expected) {
                    unsupportedRejected = true;
                }
                if (!unsupportedRejected) {
                    throw new AssertionError("unsupported prefix accepted");
                }
                System.out.println("agent.unsupportedRejected=" + unsupportedRejected);
            }
        } finally {
            System.out.println("agent.transformerRemoved="
                    + inst.removeTransformer(transformer));
        }
    }
}
```

Code này dùng API `ClassFileTransformer.transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])` hiện đại. `return null` đúng contract nghĩa **không chỉnh class bytes**. Hai nhánh của program dựa vào `isNativeMethodPrefixSupported`, nên không giả định manifest true luôn hoạt động trên mọi JVM.

### 8.2. File NativePrefixApp.java

```java
public final class NativePrefixApp {
    public static void main(String[] args) {
        System.out.println("app.started=true");
    }
}
```

Ứng dụng main không tự lấy Instrumentation. Nó chỉ chạy sau khi agent `premain` kết thúc, giúp stdout phản ánh thứ tự thực.

### 8.3. Hai manifest để kiểm tra capability

File **`native-on.mf`**:

```text
Manifest-Version: 1.0
Premain-Class: NativePrefixAgent
Can-Set-Native-Method-Prefix: true
```

File **`native-off.mf`**:

```text
Manifest-Version: 1.0
Premain-Class: NativePrefixAgent
Can-Set-Native-Method-Prefix: false
```

Tạo file UTF-8 và **newline cuối file**. Dùng `jar --create --manifest` để đưa manifest vào `META-INF/MANIFEST.MF`. Đây là **main attributes của agent JAR**, không phải tên environment variable hoặc một `-D...` system property.

### 8.4. Biên dịch, đóng gói và chạy

Với PowerShell, tạo thư mục output:

```powershell
New-Item -ItemType Directory -Force -Path classes | Out-Null
```

Với bash/zsh:

```bash
mkdir -p classes
```

Sau đó các lệnh JDK đều giống nhau:

```bash
javac --release 17 -encoding UTF-8 -d classes NativePrefixAgent.java NativePrefixApp.java
jar --create --file native-on.jar --manifest native-on.mf -C classes .
jar --create --file native-off.jar --manifest native-off.mf -C classes .
java -javaagent:native-on.jar -cp classes NativePrefixApp
java -javaagent:native-off.jar -cp classes NativePrefixApp
```

Tất cả công cụ nằm trong JDK 17+ (một JDK có `javac`/`jar`), không cần Maven, Gradle hay compiler C. `java.instrument` là module JDK riêng; `java.base` chứa các classes nền tảng như `Module` và `ProtectionDomain`. Nếu viết agent như named JPMS module, cần xử lý module graph/`requires java.instrument;` theo kiến trúc thực; demo chạy trên classpath/agent JAR thông thường.

### 8.5. Stdout đã kiểm chứng: manifest true

Trên **OpenJDK 24**, với agent JAR có `Can-Set-Native-Method-Prefix: true`, kết quả gồm **7 dòng**:

```text
agent.supported=true
agent.unregisteredRejected=true
agent.nullRejected=true
agent.prefixSet=true
agent.prefixDisabled=true
agent.transformerRemoved=true
app.started=true
```

Những kết quả trên thực sự quan sát được sau khi:
- Biên dịch `javac --release 17 -encoding UTF-8`.
- Tạo JAR với `jar --create --manifest`.
- Chạy `java -javaagent:native-on.jar`.

`agent.unregisteredRejected=true` xác nhận `IllegalArgumentException` trước `addTransformer`. `agent.nullRejected=true` xác nhận null transformer. `agent.prefixSet=true` chỉ được in sau khi set thành công; nó **không có nghĩa đã wrap native code**. `agent.prefixDisabled=true` chứng minh có thể hủy setting. `agent.transformerRemoved=true` xác nhận remove chính instance được đăng ký.

### 8.6. Stdout đã kiểm chứng: manifest false

Trong một **JVM run riêng biệt, chỉ có agent này**, `Can-Set-Native-Method-Prefix: false` cho ra **4 dòng**:

```text
agent.supported=false
agent.unsupportedRejected=true
agent.transformerRemoved=true
app.started=true
```

`agent.unsupportedRejected=true` xác nhận `UnsupportedOperationException`. Application vẫn chạy vì agent xử lý optional capability mà không cố sửa native code.

**JVM capability phụ thuộc môi trường**. Với manifest true, một JVM không hỗ trợ có thể vẫn in nhánh false. Đừng ghi “mọi Java 17/25 đều in true” vào CI assertion. Hai stdout trên là kết quả của **môi trường OpenJDK 24 đã kiểm chứng**.

## 9. Giới hạn của demo và yêu cầu để thử JNI fallback thật

Capability probe dùng transformer **no-op** nên không có renamed native method. Muốn test full functionality, cần thêm phần native library và bytecode rewrite:

1. Xây Java class có native declaration và signature xác định.
2. Viết C/C++ JNI library cung cấp function hoặc `RegisterNatives` mapping hợp lệ.
3. Dùng `javac -h` hoặc JNI specification để tạo tên/signature chuẩn; phải biên dịch native library đúng OS/architecture.
4. Dùng một transformer thực sự sửa class bytes **trước initial class definition**: chuyển native declaration gốc thành wrapper method Java, thêm native declaration có prefix, giữ signature và access semantics.
5. Trong `premain`, đăng ký **chính transformer đó** và set **đúng prefix** trước khi class target load.
6. Gọi wrapper và kiểm tra result/exception bên native implementation; kiểm tra metrics được ghi mà method vẫn giữ behavior.
7. Negative tests: không có prefix, sai native symbol, JNI signature sai hoặc library không load được phải fail rõ.
8. Test nhiều JDK vendors, OS/CPU architectures và agent order thực.

**Không tuyên bố demo trên đã kiểm tra bước 2–7.** Trong môi trường kiểm thử hiện tại không có compiler C/native linker, do đó chỉ JDK-only capability API và các exceptions đã được chạy xác minh.

### 9.1. Cẩn thận về symbol names

JNI exports có escaping cho package/class/method name và có thể cần hậu tố signature khi overload. Sơ đồ `Java_sample_NativeApi_read` là dạng dễ nhìn. **Không viết native exports chỉ bằng cách thêm/bớt chuỗi `$NP362$` từ tên C**. Phải tuân JNI spec hoặc sử dụng `RegisterNatives` được cấu hình đúng.

### 9.2. Class-load time và hạn chế retransform

Để tạo wrapper có thể phải thêm/đổi tên methods và đổi `native` flag. Trên JVM tiêu chuẩn, `retransformClasses`/`redefineClasses` có **giới hạn cấu trúc class**, không cam kết thay đổi method layout/đổi tên/thêm methods của class đã nạp.

Do đó:
- Nếu cần native wrapper, **đăng ký transformer từ startup `premain`** trước target class load.
- `Can-Retransform-Classes`/`isRetransformClassesSupported` là capability **riêng** và không phá giới hạn structural edits.
- `isModifiableClass` chỉ cho biết class có thể modifiable theo những thay đổi cho phép, **không** bảo đảm có thể thêm native method.
- Đừng dựa vào dynamic attach để instrument native wrappers đã qua initial definition mà không kiểm thử rõ.
- Nếu class có active stack frames, các quy tắc redefine/retransform và linkage có thể khiến behavior phức tạp; không tự động “retarget” các call sites đã resolved.

## 10. Khi nào nên chọn công cụ khác?

| Nhu cầu | Lựa chọn thích hợp | Cần native prefix? |
| --- | --- | --- |
| Đo thời gian method Java thông thường | `ClassFileTransformer`/Java APM instrumentation, JFR events. | Không. |
| Monitor heap/thread/GC/basic JVM metrics | JMX/MXBean, JFR, exporter phù hợp. | Không. |
| Application tracing HTTP/database | OpenTelemetry SDK/Java agent phù hợp, Micrometer cho metrics. | Thông thường không. |
| Gọi native library JNI | `System.loadLibrary`, đúng JNI signature, ABI. | Không khi không đổi native method name. |
| Chèn Java logging quanh một **native declaration** được transformer wrap | Java agent + transformer + native prefix fallback + JNI library. | Có thể cần. |
| Phân tích lỗi C/native stack | Native debugger/OS profiler/JVMTI trong phạm vi hỗ trợ. | Không đồng nhất với API này. |
| Gọi native function qua Foreign Function & Memory API | FFM interop, policy phù hợp JDK hiện hành. | Không tự động chịu native prefix JNI. |
| Chỉ muốn biết JNI method nào được gọi | Chọn observability/native tracing API được thiết kế cho mục tiêu và policy. | Không nhất thiết. |

**Không dùng native prefix như bản vá `UnsatisfiedLinkError`** do thiếu `.dll`/`.so`, sai cấu trúc CPU, thiếu JNI exports hoặc sai `java.library.path`. Nguyên nhân cơ bản vẫn phải sửa ở native library/linking.

## 11. Bảo mật và tác động của Java agent

Một agent có thể biến đổi classes ở phạm vi rộng, quan sát dữ liệu và thay đổi behavior. Vì vậy:

- Chỉ chạy Java agent được tin tưởng, pin/verify JAR provenance và dependencies.
- Không tải agents không rõ nguồn vào process xử lý secrets.
- Lọc transformer theo đúng class names, loaders và modules cần thiết.
- Tránh instrument core JDK classes mà bản thân transformer cần để hoạt động; class loading recursion có thể tạo `LinkageError`, circularity hoặc deadlock.
- Không log JNI arguments, credentials, tokens hoặc dữ liệu khách hàng nếu không được phép.
- Đo overhead của wrappers; không gọi network exporter/blocking I/O nặng từ mọi method invocation.
- Giữ nguyên return values, exceptions, synchronization và timing semantics được kỳ vọng.
- Cẩn thận `finally` logging có thể ném exception, làm che mất exception native thật.
- Kiểm tra thread-safety, recursion guards, memory retention theo classloader.
- Không tự bật dynamic agent loading hoặc tắt native access restrictions của JDK hiện đại chỉ để vượt policy production.
- Có rollback plan và quan sát startup errors; nếu `premain` fail, JVM có thể abort startup.

**Native method prefix chỉ là capability của JVM, không là hệ thống phân quyền**. Việc bật nó không cấp quyền tùy ý patch native binaries hoặc vượt security manager/OS protections.

## 12. Lỗi phổ biến và troubleshooting

| Hiện tượng | Nguyên nhân điển hình | Cách khắc phục |
| --- | --- | --- |
| `isNativeMethodPrefixSupported()==false` | Manifest không có capability hoặc JVM không hỗ trợ. | Kiểm tra JAR manifest, runtime và fallback. |
| `setNativeMethodPrefix` ném UOE | Optional capability false. | Không set; báo tính năng không khả dụng. |
| `setNativeMethodPrefix` ném IAE | Transformer chưa đăng ký. | `addTransformer` trước, đúng instance. |
| `setNativeMethodPrefix` ném NPE | Transformer null. | Khởi tạo object đúng. |
| Prefix null/empty, native method không resolve | Prefix retry đã bị vô hiệu hóa. | Đặt nonempty prefix đúng lúc. |
| Set prefix thành công nhưng không có native metrics | Transformer no-op hoặc chưa rewrite target. | Inspect class transformation output, load order, wrappers. |
| `UnsatisfiedLinkError` | Library chưa load, sai JNI symbol/ABI/signature hoặc native prefix fallback sai. | Kiểm tra native library trước, rồi transformer/prefix. |
| `VerifyError` / `ClassFormatError` | Classfile rewrite không hợp lệ. | Kiểm chứng method flags, Code attr, stack maps/constant pool. |
| `UnmodifiableClassException` / `UnsupportedOperationException` khi retransform | JVM/capability không cho phép thay đổi yêu cầu. | Transform trước initial load hoặc chọn cách khác. |
| `ClassCircularityError` / `LinkageError` | Transformer gây class-loading recursion. | Filter chặt, tránh phụ thuộc vào classes đang instrument. |
| Nhiều agents, kết quả bất thường | Prefix/layer order va chạm. | Mỗi transformer prefix riêng, test đúng thứ tự. |
| `removeTransformer` nhưng còn callback | Class loading thread concurrent. | Design callback defensive, idempotent. |
| Client/sản phẩm khác có JVM behavior khác | Optional capability/JVM vendor/OS khác. | Support matrix và fallback. |
| Native method được wrap nhưng argument/return sai | Transformer phá signature/JNI mapping. | Verify signatures và call semantics, native integration tests. |
| App startup fail sau agent update | `premain` exception, manifest/JAR/rewrite hỏng. | Rollback agent và xem diagnostic, không tắt controls mù quáng. |

**Thứ tự debug đề xuất:** xác minh `-javaagent` được tải → đọc manifest `Premain-Class`/`Can-Set-Native-Method-Prefix` → log `isNativeMethodPrefixSupported` → kiểm tra `addTransformer` trước `setNativeMethodPrefix` → xác định class target đã load chưa → xem transform có trả bytes mới không → kiểm tra native declarations và prefix names → xem JNI library/linking/signatures → test normal vs fallback path → test multi-agent order/semantics.

## 13. Bộ test nên có cho công cụ thực

| Test | Kỳ vọng |
| --- | --- |
| Agent jar manifest true + JVM hỗ trợ | Supported true, set prefix thành công. |
| Manifest false hoặc không xin capability | Khi chỉ agent này chạy, supported false; set ném UOE. |
| Manifest true nhưng JVM từ chối | Supported false; fallback rõ. |
| Transformer chưa đăng ký | IAE với supported true. |
| Transformer null | NPE. |
| Prefix null/empty | Disable retry cho transformer. |
| Transformer no-op | Capability có thể được set nhưng không có native wrapping. |
| Transformer rewrite valid target class | Wrapper/non-native và renamed native declaration được tạo đúng. |
| Target class đã loaded | Không giả định có thể thêm method bằng retransform. |
| Automatic JNI symbol lookup | Có đường fallback đúng sau normal failure. |
| JNI `RegisterNatives` | Prefix fallback đúng tên/signature theo contract. |
| Prefix collision | Không liên kết nhầm symbol/native method. |
| Two or more Java agents | Layer prefix theo registration order, handles skipped wrappers. |
| Native exception/return | Wrapper bảo toàn behavior và metrics không che lỗi. |
| Native library thiếu/sai kiến trúc | Bắt lỗi rõ, không gắn nhãn instrumentation success. |
| Concurrent class loading | Transformer thread-safe, không deadlock. |
| JVM vendors/Java17/21/25 | Behavior optional capability và failover nhất quán. |
| Agent security/supply chain | Không instrument ngoài allowlist, không lộ secrets. |
| Runtime overhead | Benchmark/sampling, không tạo memory leaks. |

**Cần phân tách test suite:** Java capability tests chạy mọi nơi chỉ có JDK; JNI integration tests yêu cầu compiler native/linker và native library tương ứng OS. Không chạy thử các wrappers chưa kiểm chứng trên production workload.

## 14. FAQ

**1. `setNativeMethodPrefix` còn có trên Java 17/25 không?** Có, trong `java.lang.instrument.Instrumentation`. Nó vẫn được tài liệu hóa nhưng capability tùy chọn.

**2. Nó tự chèn bytecode vào native method?** Không. Native method không có Java bytecode body. Công cụ phải tạo wrapper và renamed native declaration bằng transformer.

**3. Có cần một JNI library thật không?** Nếu muốn chứng minh fallback vào native implementation thật thì có; chỉ kiểm tra capability API thì không cần.

**4. Vì sao cần đặt prefix trên transformer cụ thể?** Vì mỗi transformer có thể tạo wrapper với tên khác, thứ tự nhiều lớp cần được JVM theo dõi.

**5. Tôi đặt prefix trước `addTransformer` được không?** Không, bị `IllegalArgumentException` nếu capability cho phép.

**6. Manifest true bảo đảm `isNativeMethodPrefixSupported()==true`?** Không; JVM có thể không hỗ trợ optional capability.

**7. Prefix null có nghĩa JVM tự tìm tên tốt nhất?** Không, null hoặc chuỗi rỗng **tắt retry** cho transformer.

**8. Normal JNI resolution và prefix fallback ai chạy trước?** Normal resolution trước; fallback sau khi nó thất bại.

**9. `RegisterNatives` có khác automatic JNI linking?** Có, nhưng Javadoc mô tả prefix-aware retry cho cả hai cơ chế.

**10. Có nên chọn prefix `wrapped_` không?** Không lý tưởng, dễ va chạm. Dùng prefix riêng của agent.

**11. Bật native prefix có tự bật `Can-Retransform-Classes` không?** Không. Hai capabilities độc lập.

**12. Có thể thêm native wrapper vào class đã load?** Không thể giả định; redefinition/retransformation bị giới hạn thay đổi cấu trúc. Ưu tiên load-time.

**13. Có thể dùng để sửa thiếu .dll?** Không. Cần sửa thư viện native/paths/symbols/ABI.

**14. Có instrument mọi JDK native method được không?** Không được cam kết; phụ thuộc class modifiability, timing, JVM internals và policy.

**15. Có phải `return null` trong `transform` đã instrument method?** Không, nghĩa là không sửa classfile.

**16. Tại sao program demo chạy được khi manifest false?** Nó bắt và assert UOE rồi tiếp tục; không có native code nào cần prefix để hoạt động.

**17. Có nên dùng JFR/JMX thay vì native prefix?** Nhiều mục tiêu observability phù hợp JFR/JMX/APM hơn; native prefix là công cụ chuyên biệt cho JNI wrapper.

**18. Có thể dùng prefix này cho FFM API không?** Không tự động; FFM interop khác JNI native method resolution.

**19. Tại sao cần security review agent?** Agent có khả năng thay class bytecode và tác động hành vi cả process, không chỉ đọc metrics.

**20. Ví dụ này thực sự kiểm chứng được gì?** Java agent startup, manifest capability true/false, các exceptions, set/clear prefix và removeTransformer; **không** kiểm chứng một JNI binding end-to-end.

## 15. Checklist trước khi đưa vào công cụ thật

- [ ] Xác nhận bài toán cần wrap **native method**, không chỉ instrument Java methods.
- [ ] Đọc Javadoc `setNativeMethodPrefix` và hiểu fallback native resolution, không phải JNI binary patch.
- [ ] Dùng `ClassFileTransformer` tạo wrapper Java và native method renamed đúng signature.
- [ ] Gắn mỗi transformer một prefix đủ đặc trưng, test tránh collision.
- [ ] Đăng ký transformer trước khi set prefix, dùng đúng instance.
- [ ] Đặt `Can-Set-Native-Method-Prefix: true` trong main manifest khi cần.
- [ ] Kiểm tra `isNativeMethodPrefixSupported`, fallback khi capability false.
- [ ] Không nhầm `Can-Retransform-Classes`/`Can-Redefine-Classes` với native prefix capability.
- [ ] Với structural rewrite, đăng ký sớm trong `premain` trước target class initial definition.
- [ ] Test JNI automatic symbol lookup và `RegisterNatives` khi tool hỗ trợ.
- [ ] Không coi code demo no-op đã chứng minh JNI fallback.
- [ ] Không dùng prefix để “sửa” lỗi native library deployment.
- [ ] Kiểm soát agent ordering và multi-layer wrappers.
- [ ] Bảo toàn argument/return/exception/ABI, bảo đảm code instrument không đệ quy.
- [ ] Không instrument bừa bãi core JDK classes hoặc methods nhạy cảm.
- [ ] Có bảo mật agent JAR, allowed class set, monitoring overhead và rollback.
- [ ] Chạy tests trên đúng JVM vendor/OS/JNI library và Java 17/21/25 mục tiêu.

## 16. Nguồn chính thức

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `setNativeMethodPrefix`, `isNativeMethodPrefixSupported`, exceptions, JNI fallback, nhiều transformer layers.
- [Java SE 25 — Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng API hiện hành trên JDK mới.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `transform`, `return null`, class-load order và định nghĩa transformer.
- [Java SE 25 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): multi-agent transformer order và lỗi class circularity.
- [Java SE 17 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, `Agent-Class`, capability manifest.
- [Java SE 25 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agent lifecycle và dynamic loading controls.
- [Java Native Interface Specification, JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): native method resolution, mangling và `RegisterNatives`.
- [JVM TI Specification, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): redefine/retransform limitations, native tooling behavior.
