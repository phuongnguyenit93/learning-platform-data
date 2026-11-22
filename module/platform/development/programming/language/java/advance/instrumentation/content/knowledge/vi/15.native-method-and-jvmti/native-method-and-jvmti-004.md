# Tiền tố riêng cho mỗi transformer và cơ chế thử phân giải native

Java agent có thể chèn bytecode trước và sau nhiều Java method. Nhưng một phương thức khai báo `native` **không có Java `Code` attribute** để chèn instructions vào thân như method bình thường. Để quan sát lời gọi native, transformer thường tạo một **Java wrapper không native**, rồi đổi tên khai báo native sang một tên có **tiền tố riêng của transformer**. Vấn đề tiếp theo là: thư viện JNI ban đầu chỉ biết tên native cũ, vậy JVM tìm lại native implementation bằng cách nào?

`Instrumentation.setNativeMethodPrefix(ClassFileTransformer transformer, String prefix)` trả lời đúng bài toán ấy. API thay đổi **cơ chế thử lại khi liên kết native method thất bại**, cho phép JVM xét các tiền tố mà agent đã đăng ký. **Mỗi transformer có tiền tố riêng** để nhiều lớp wrapper có thể xếp chồng mà vẫn tìm được JNI implementation gốc.

Bài học trong nhóm **Native và JVM TI** giải thích:

1. Khác biệt giữa method `native`, Java wrapper, JNI function và `ClassFileTransformer`.
2. Vì sao `setNativeMethodPrefix` **không** tự instrument một method, tự đổi tên JNI symbol hoặc tự load native library.
3. Hai đường phân giải: **JNI automatic symbol lookup** và **`RegisterNatives`**.
4. Thứ tự và điều kiện áp các tiền tố khi **nhiều transformer** tạo wrappers, kể cả khi một transformer bỏ qua method.
5. Cách kiểm tra capability/manifest, đặt prefix tránh collision, chẩn đoán `UnsatisfiedLinkError` và thử nghiệm Java 17+ với JNI C thật.

## 1. Bài toán: native method không có Java bytecode để chèn probe

Xét lớp Java:

```java
public final class NativeMath {
    public static native int sum(int left, int right);
}
```

Đây là **đoạn minh họa**, chưa chạy độc lập: muốn gọi `sum` phải load một native library chứa JNI implementation tương ứng. Source chỉ khai báo signature và modifier `native`, còn thân thực thi nằm phía native (ví dụ trong `.so`, `.dylib` hoặc `.dll`).

Đối với Java method có body, transformer có thể biến:

```text
calculate(a, b):
    return a + b
```

thành:

```text
calculate(a, b):
    Probe.enter()
    try:
        return a + b
    finally:
        Probe.exit()
```

Nhưng phương thức `native int sum(...)` không chứa một đoạn Java bytecode như vậy. JVM có thể gọi native implementation trực tiếp theo ràng buộc JNI; không có nơi để transformer chèn một `invokestatic Probe.enter` vào **thân Java của chính native declaration**.

### 1.1. Giải pháp wrapper: tạo Java method cùng tên

Một phép biến đổi class file được thiết kế cẩn thận có thể biến:

```java
// Trạng thái class trước khi transform:
public static native int sum(int left, int right);
```

thành logic tương đương:

```java
// Sơ đồ source sau khi transformer đã sửa class file:
public static int sum(int left, int right) {
    Probe.enter();
    try {
        return agent_sum(left, right);
    } finally {
        Probe.exit();
    }
}

private static native int agent_sum(int left, int right);
```

**Đoạn trên là mô phỏng source, không phải code runnable độc lập:** `Probe` chưa khai báo và việc sinh wrapper cần một thư viện xử lý class bytes. Mục tiêu là nhận ra hai method có vai trò khác nhau:

- `sum` trở thành **method Java không native** để chèn probe.
- `agent_sum` là **khai báo native còn lại** dùng để gọi implementation JNI gốc.
- Native implementation ban đầu có thể vẫn mang tên JNI cho `sum`, chẳng hạn `Java_NativeMath_sum`. Không nên buộc người vận hành biên dịch lại thư viện native chỉ để đổi tên hàm.
- Cần có **khả năng thử lại phân giải tên `agent_sum` theo prefix `agent_`**, để cuối cùng JVM tìm được implementation `sum`.

`setNativeMethodPrefix` cung cấp phần **thử lại resolution**. Còn transformer phải tự tạo wrapper và khai báo native hợp lệ, giữ descriptors, access rules và semantics phù hợp. Chỉ gọi API set prefix không tạo bất kỳ wrapper nào.

### 1.2. Phân biệt các tên

| Tên | Ví dụ | Do ai sở hữu? | Vai trò |
|---|---|---|---|
| Tên Java API trước biến đổi | `sum(int,int)` | Class gốc | Call site ứng dụng đang gọi |
| Tên Java wrapper sau biến đổi | `sum(int,int)` | Transformer tạo body | Chèn tracing/profiling |
| Tên native declaration sau biến đổi | `agent_sum(int,int)` | Transformer đổi tên/khai báo | Cửa ngõ gọi native cũ |
| Prefix của transformer | `agent_` | `setNativeMethodPrefix(t,"agent_")` | Quy tắc để JVM thử lại khi JNI resolution thường thất bại |
| Tên JNI implementation gốc | `Java_NativeMath_sum` | Native library | Symbol C/JNI thực thi phép tính |
| Native library file | `libnative_math.so` hoặc hệ tương ứng | Build/deployment | Chứa symbol cần resolve |

**Không nhầm** tên `agent_sum` trong class file với tên symbol C bắt buộc phải được đổi theo. Chính cơ chế retry cho phép dùng implementation C/JNI mang tên gốc.

## 2. Điều kiện cần để bật prefix

API có hai phần:

```java
boolean isNativeMethodPrefixSupported();

void setNativeMethodPrefix(
        java.lang.instrument.ClassFileTransformer transformer,
        String prefix);
```

Các phương thức thuộc `java.lang.instrument.Instrumentation`, là đối tượng agent nhận qua `premain(String,Instrumentation)` hoặc `agentmain(String,Instrumentation)` nếu JVM hỗ trợ dynamic loading.

### 2.1. Capability là tùy chọn, manifest phải yêu cầu

`isNativeMethodPrefixSupported()` trả `true` khi **JVM hỗ trợ** và agent đã yêu cầu capability thích hợp. Trong manifest của agent JAR:

```text
Manifest-Version: 1.0
Premain-Class: example.agent.PrefixAgent
Can-Set-Native-Method-Prefix: true

```

Đây là **mẫu manifest minh họa** cho class `example.agent.PrefixAgent` chưa được định nghĩa trong đoạn này. Trong ví dụ chạy đầy đủ ở mục 7, manifest dùng class thực `PrefixAgent`.

- `Can-Set-Native-Method-Prefix: true` **yêu cầu** JVM cấp khả năng, không ép mọi JVM implementation phải hỗ trợ.
- Nếu thuộc tính không được khai báo hoặc không phải `true`, không thể tự giả định native prefix capability được bật.
- `isNativeMethodPrefixSupported()` ổn định trong cùng một JVM instantiation theo hợp đồng.
- `Can-Retransform-Classes` và `Can-Redefine-Classes` là **các capability khác**, không tự bật native prefix.
- Việc JNI library hoạt động bình thường **không chứng minh** JVM/agent cho phép thiết lập prefix.

**Precheck đúng:**

```java
// Đoạn trong một agent; inst đã nhận từ premain/agentmain.
if (!inst.isNativeMethodPrefixSupported()) {
    System.out.println("SKIPPED: NATIVE_PREFIX_UNSUPPORTED");
    return;
}
```

Nếu không hỗ trợ, **đừng** cố gọi `setNativeMethodPrefix` rồi nuốt `UnsupportedOperationException` và báo “native instrumentation active”. Có thể fallback sang điểm đo khác theo chính sách, nhưng việc instrument Java wrapper và JNI binding của method này chưa được giải quyết.

### 2.2. Phải đăng ký transformer trước khi gán prefix

Thứ tự hợp lệ:

```java
ClassFileTransformer transformer = new MyNativeWrapperTransformer();

inst.addTransformer(transformer);
inst.setNativeMethodPrefix(transformer, "agent_");
```

**Đây là code minh họa, không độc lập**: `MyNativeWrapperTransformer` cần được triển khai. Cốt lõi là **đúng đối tượng transformer đã đăng ký**.

Thứ tự sai:

```java
ClassFileTransformer transformer = new MyNativeWrapperTransformer();
inst.setNativeMethodPrefix(transformer, "agent_"); // Chưa add.
inst.addTransformer(transformer);
```

`setNativeMethodPrefix` có thể ném `IllegalArgumentException` vì transformer chưa đăng ký. Không chỉ cần cùng **class name** của transformer: chính **instance** được truyền phải là instance đã đăng ký qua `addTransformer`.

Không nên đăng ký **cùng một instance** nhiều lần để thử thay đổi ordering. Javadoc `addTransformer` khuyến cáo mạnh tránh việc này; thiết kế nhiều lớp wrapper bằng các transformer có identity và trạng thái riêng sẽ dễ debug hơn.

### 2.3. Ba lỗi API cần phân biệt

| Tình huống | Kết quả theo hợp đồng | Cách khắc phục |
|---|---|---|
| `transformer == null` | `NullPointerException` | Tạo và đăng ký instance hợp lệ |
| JVM/manifest không hỗ trợ prefix | `UnsupportedOperationException` | Kiểm `isNativeMethodPrefixSupported`, manifest và JVM trước |
| Transformer chưa đăng ký | `IllegalArgumentException` | Gọi `addTransformer(t)` trước `setNativeMethodPrefix(t,...)` |
| Prefix `null` hoặc rỗng `""` | **Không thử lại** failed native resolution cho transformer này | Dùng để tắt prefix retry cho transformer, không phải lỗi input |
| Prefix trùng tên một method đang tồn tại | Có thể tạo ambiguity/collision hoặc sai cách nối tên | Dùng prefix độc nhất và kiểm tra đầy đủ class schema |
| Prefix hợp lệ nhưng JNI lib không được load | Native linking vẫn thất bại | Kiểm `System.loadLibrary`/đường dẫn/JNI symbol |

**Điểm quan trọng:** `setNativeMethodPrefix` không đổi bytecode hay symbol ngay tại lúc được gọi. Nó bổ sung quy tắc **khi native method resolution thất bại về sau**.

## 3. Cơ chế 1: automatic JNI native method resolution

Theo JNI specification, nếu Java có method native `sum(int,int)` trong class `NativeMath`, native implementation thường có tên xuất ra từ quy tắc JNI name mang prefix `Java_`, tên class, tên method đã escape và có thể thêm escaped signature đối với overloaded native methods.

Ví dụ không overloaded:

```java
public final class NativeMath {
    public static native int sum(int a, int b);
}
```

JNI implementation điển hình:

```c
#include <jni.h>

JNIEXPORT jint JNICALL Java_NativeMath_sum(
        JNIEnv* env, jclass type, jint a, jint b) {
    (void) env;
    (void) type;
    return a + b;
}
```

Đây chỉ là **cặp khai báo/minh họa**: còn cần compile JNI C thành shared library và load thư viện. Java method là `static`, do đó đối số thứ hai của JNI function là `jclass`; với instance method nó thường là `jobject`.

### 3.1. Không có prefix, JVM tìm theo tên native hiện hành

Sau khi transformer tạo `agent_sum`:

```text
Java native declaration:
    agent_sum(int, int)

Symbol tự động JVM thử trước (không tính overload suffix):
    Java_NativeMath_agent_1sum

Native library chỉ có:
    Java_NativeMath_sum

=> Standard lookup không thấy implementation tương ứng.
```

Trong JNI escaping, ký tự `_` của tên Java method thường được escape thành `_1`. Vì vậy `agent_sum` không có JNI symbol đơn giản là `Java_NativeMath_agent_sum`; tên tự động theo specification là `Java_NativeMath_agent_1sum`, chưa kể cách biểu diễn overloaded signature.

### 3.2. Có prefix: chỉ thử lại sau khi lookup thường thất bại

`setNativeMethodPrefix(t, "agent_")` hướng dẫn JVM thực hiện thêm một bước:

```text
Native declaration được gọi: agent_sum(int,int)

Thử tự động thông thường:
  method(agent_sum) -> nativeImplementation(agent_sum)
  tra symbol tương ứng tên agent_sum
  FAIL (symbol không có)

Thử lại với registered prefix của transformer:
  bỏ "agent_" khỏi tên implementation cần tìm
  method(agent_sum) -> nativeImplementation(sum)
  tra symbol tương ứng tên gốc sum
  FOUND Java_NativeMath_sum
```

Cách này **không đổi tên Java native method trở lại `sum`**. Trong class file, khai báo native vẫn tên `agent_sum`; chỉ native implementation được chọn là symbol của tên gốc.

**Vì sao phải standard lookup trước?** Nếu một native method `agent_sum` thực sự có implementation trùng tên, JVM không được tùy tiện bỏ qua nó để ưu tiên symbol gốc. Prefix retry chỉ là **fallback**. Nhờ vậy transformer có thể chọn wrapper theo từng method thay vì mặc định đổi resolution của tất cả native methods.

### 3.3. JNI short/long names và overload

JNI có quy tắc tìm native name dạng **short** trước và **long** có mã hóa parameter signature khi cần. Ví dụ `sum(int,int)` không overloaded dễ có symbol `Java_NativeMath_sum`. Nếu method có overload hoặc chứa các ký tự cần escape, đừng đoán symbol bằng cách nối string thô.

Cần kiểm tra:

- Binary class name của **class khai báo native** sau transform.
- Method name, descriptor/parameter types và static/instance.
- JNI escaping (ví dụ `_` thành `_1`).
- Short/long JNI symbol matching và tình huống tên dài có parameter signature.
- Library đang được load vào **loader phù hợp** với class khai báo native.

`setNativeMethodPrefix` **không xử lý** một JNI implementation sai signature, ABI calling convention hoặc thư viện bị load ở class loader khác.

## 4. Cơ chế 2: RegisterNatives không giống automatic symbol lookup

Native library có thể chủ động liên kết Java method với C function bằng `RegisterNatives(JNIEnv*, jclass, JNINativeMethod*, jint)`. Khi đó một entry gồm **method name, JNI descriptor và function pointer**; không nhất thiết phải có exported `Java_Class_method` symbol như trường hợp tự động.

Ý tưởng:

```c
// Đoạn C minh họa, không độc lập.
static jint native_sum(JNIEnv* env, jclass clazz, jint a, jint b) {
    return a + b;
}

/* JNINativeMethod entry cho bản gốc:
   { "sum", "(II)I", (void*)native_sum }
*/
```

Nếu class sau transform chỉ còn native `agent_sum(II)I` và `sum` đã trở thành Java wrapper, ánh xạ ban đầu:

```text
RegisterNatives:
  method("sum", "(II)I") -> function pointer native_sum

Thử mapping thông thường:
  tìm native method "sum" trong class
  FAIL vì "sum" hiện là method Java không native

Retry với registered prefix "agent_":
  tìm native method "agent_sum", descriptor "(II)I"
  FOUND
  liên kết agent_sum -> native_sum
```

**Đảo chiều dễ nhầm:**

| Đường phân giải | Đầu vào từ native library | Khi retry, prefix được xét ở đâu? |
|---|---|---|
| **Automatic JNI lookup** | JVM tìm symbol cho Java native declaration `agent_sum` | **Bỏ** prefix khỏi **tên implementation cần tìm**, để tìm implementation `sum` |
| **`RegisterNatives`** | Native code đăng ký method name `sum` + descriptor + pointer | **Thử thêm** prefix vào **tên Java native method** được tra, để nhận `agent_sum` |

Javadoc Instrumentation mô tả hai cơ chế riêng. Không nên biến `RegisterNatives` thành việc “Java tự tìm exported symbol `Java_...`”; nó là một ánh xạ function pointer trực tiếp.

### 4.1. Tại sao RegisterNatives dễ mắc lỗi khi đã instrument?

- Native code đăng ký một method name nhưng transformer đã đổi native declaration thành prefixed name.
- Descriptor bị đổi không tương thích, hoặc method đã không còn là native theo schema mới.
- Prefix chưa được đăng ký vào **đúng transformer instance**.
- Class loader của JNI class khác loader của class mà bạn đã transform.
- Native library gọi `RegisterNatives` trước khi transformer/prefix được thiết lập hoặc với class khác mong đợi.
- Một thư viện/agent khác đã đăng ký lại native implementation, gây tranh chấp hành vi.

Cũng không nên coi mọi lỗi `RegisterNatives` là do prefix. Kiểm tra `JNIEnv->ExceptionCheck`, JNI return code, tên/descriptor và những class thực tế được load; rủi ro `RegisterNatives` can thiệp vào logic native là đáng kể.

## 5. Vì sao mỗi transformer phải có một prefix riêng?

Một agent có thể chỉ có một transformer, nhưng JVM thường có nhiều agent/transformer. Ví dụ transformer A đo latency, transformer B đếm số lần gọi, transformer C thêm tracing. Mỗi transformer có quyền tạo một **Java wrapper quanh native declaration đang có**.

Javadoc `setNativeMethodPrefix` nêu rõ: vì nhiều `ClassFileTransformer` có thể sửa bytes theo thứ tự, **mỗi transformer cần tiền tố riêng**. Nếu ba transformers đều wrap `foo`, tên native ở cuối có thể là:

```text
Sau A:    a_foo
Sau B:    b_a_foo
Sau C:    c_b_a_foo
```

Trong đó có các Java wrappers:

```text
foo()         [Java wrapper A]
   |
   v
a_foo()       [Java wrapper B]
   |
   v
b_a_foo()     [Java wrapper C]
   |
   v
c_b_a_foo()   [native declaration cuối]
   |
   v
JNI implementation foo()
```

Đây là **mô hình sau khi ba transformer sinh class bytes**, không phải output tự động của `setNativeMethodPrefix`. Wrapper là các methods Java có `Code`; method tận cùng vẫn `native`. Sau các lần retry theo registered prefixes, JVM có thể liên kết đến native implementation gốc.

### 5.1. Thứ tự ghép tên

Nếu các transformer cùng nhóm được áp dụng theo thứ tự **A → B → C**, mỗi transformer đặt tiền tố của nó **bên ngoài** những tiền tố đã có:

```text
foo
A: a_foo
B: b_a_foo
C: c_b_a_foo
```

Không đảo thành `a_b_c_foo` chỉ vì A được đăng ký trước. Ở cuối pipeline, prefix mới nhất thường đứng **bên trái** tên native. Đây là cách diễn giải trực tiếp ví dụ nhiều transformers của Javadoc.

Trong `ClassFileTransformer`, cần nhớ JVM chia callback thành các nhóm:

1. Java transformers không hỗ trợ retransformation (`canRetransform=false`).
2. Native/JVMTI transformers không hỗ trợ retransformation.
3. Java transformers hỗ trợ retransformation (`canRetransform=true`).
4. Native/JVMTI transformers hỗ trợ retransformation.

**Trong từng nhóm** mới theo thứ tự đăng ký. Vì thế trước khi suy thứ tự prefix, phải biết thứ tự **biến đổi class thực tế**; không chỉ nhìn thứ tự các lệnh `addTransformer` rời rạc trong nhiều nhóm.

### 5.2. Khi B không wrap: không được đoán cứ có prefix B là phải áp

Nếu A và C wrap nhưng B không wrap `foo`:

```text
Sau A:  a_foo (native) + foo (Java wrapper)
Sau B:  không đổi tên native, không thêm wrapper
Sau C:  c_a_foo (native) + a_foo (Java wrapper)

Không có wrapper b_a_foo hoặc b_foo.
```

Theo Javadoc, **một prefix trung gian chỉ được áp khi wrapper không-native tương ứng tồn tại**. Vì vậy kết quả có thể là `c_a_foo`, không phải `c_b_a_foo`. Đừng thiết kế native resolution bằng cách mù quáng “gỡ ba prefix theo danh sách” mà không xét cấu trúc wrapper mà transformers thật đã tạo.

Javadoc đưa ví dụ một trường hợp không có wrapper của transformer thứ hai, nhưng prefix của transformer đầu vẫn được xét vì **non-native wrapper của nó hiện diện**. Đây là lý do **mỗi transformer riêng một prefix** giúp JVM suy đúng chuỗi trong những lớp wrapper bị bỏ qua có chọn lọc.

### 5.3. Trùng prefix có thể phá tính phân biệt

Không có một namespace prefix được JVM cấp phát tự động trên toàn bộ agents. Chọn `wrapped_` hay `agent_` quá phổ biến có thể trùng method đã tồn tại hoặc prefix của agent khác.

Mẫu prefix production có thể là:

```text
$$_com_acme_metrics_native_$
$$_com_acme_trace_native_$
```

Đây là **ví dụ quy ước tên**, không phải tên chuẩn được Java yêu cầu. Trong JVM bytecode, ký tự `$` được phép trong tên method thông thường nhưng có quy tắc JNI escaping; khi dùng prefix cần sinh bytes và symbol matching theo specification, không ghép thủ công các tên JNI thiếu escaping.

Đặt prefix ổn định theo agent/transformer, đủ khác biệt, và kiểm tra class schema trước khi thêm method. Phải xét overloads, bridge methods, synthetic names và những transformer khác khi tích hợp.

## 6. setNativeMethodPrefix không phải công cụ thay bytecode

Đối chiếu ba hành động độc lập:

```text
1. Transformer tạo body Java + native declaration prefixed
             |
             v
2. Agent đăng ký prefix cho đúng transformer (setNativeMethodPrefix)
             |
             v
3. Native library vẫn có implementation tương thích và được load
             |
             v
   Lúc JVM cần resolve prefixed native method:
   thử thường -> thất bại -> xét prefix -> tìm gốc
```

Chỉ có bước 2 nhưng không có bước 1: code app không tự có wrapper. Chỉ có bước 1 mà thiếu 2: native `agent_foo` có thể không resolve được tới JNI implementation `foo`, trừ khi thư viện cũng cung cấp symbol/registration phù hợp. Có bước 1+2 nhưng không load library: vẫn có `UnsatisfiedLinkError`.

### 6.1. Manifest và lifecycle

Đặt prefix **trước thời điểm cần phân giải native method** sẽ đơn giản và đáng tin hơn. Với startup agent, bạn có thể đăng ký trong `premain` trước khi class target được nạp. Với dynamic attach, target có thể đã load class và JNI binding trước đó; cần đánh giá lại giới hạn retransform/redefine và không giả định có thể đổi mọi native binding đã được JVM thiết lập.

`removeTransformer(t)` chỉ gỡ đăng ký biến đổi trong tương lai. Nó **không tự rollback** class bytes đã được cài, không tự xóa Java wrappers đã sinh và không bảo đảm native method đã liên kết bị unbind. Tương tự `setNativeMethodPrefix(t,"")` có ý nghĩa tắt **retry thất bại về sau cho transformer**, không phải khôi phục tự động mọi binding cũ.

### 6.2. Native prefix khác các API thường bị nhầm

| Khái niệm | Mục đích | Có làm nhiệm vụ `setNativeMethodPrefix` không? |
|---|---|---|
| `ClassFileTransformer.transform` | Sinh/đổi class bytes, tạo wrapper | **Không** thiết lập quy tắc retry native |
| `setNativeMethodPrefix` | Quy định retry cho native method resolution của một transformer | **Không** tự viết bytecode |
| `-javaagent` / `premain` | Khởi động Java instrumentation agent | Chỉ cho đường truy cập `Instrumentation` |
| `-agentpath` / native `Agent_OnLoad` | Khởi động native JVMTI agent | API/agent lifecycle khác Javaagent |
| `System.loadLibrary` | Tải JNI native library vào tiến trình/loader context phù hợp | Không tự tạo wrappers hay prefix |
| `RegisterNatives` | Liên kết name+signature Java native với native function pointer | Có retry prefix khi tương ứng, nhưng nó vẫn là cơ chế JNI binding |
| `NativeMethodBind` JVMTI event | Quan sát/điều chỉnh binding native ở tầng JVMTI khi có capability | Một hướng quan sát khác, không giống Java wrapper/prefix |
| `retransformClasses` | Chạy lại transformation process trên class đã nạp nếu hỗ trợ | Không tự bảo đảm JNI binding/đổi schema được phép |
| `redefineClasses` | Thay class definition bằng bytes được cung cấp | Không đồng nghĩa set prefix |

## 7. Ví dụ chạy được trên Java 17+ và JNI C: hai prefix, một implementation gốc

Ví dụ này cố tình **tạo sẵn hai Java wrappers trong source** để người học tập trung vào **cơ chế native method resolution** mà không phải viết một bytecode transformer bằng ASM. Hai `ClassFileTransformer` được đăng ký là **identity placeholders**, `transform` trả `null`; chúng chỉ cung cấp hai registered prefixes cho phép JVM xử lý tên native đã được wrap sẵn.

**Điều ví dụ minh họa:** cấu trúc Java sau khi hai transformers thật sự đã wrap một native method và native implementation chỉ giữ tên gốc. Nó **không** chứng minh hai no-op transformers đã tự tạo Java wrappers. Muốn tạo wrappers tự động trong agent production cần một bytecode transform khác và kiểm thử schema/verification riêng.

### 7.1. Yêu cầu môi trường

- **JDK 17+** có `java`, `javac` và `jar`.
- Một trình biên dịch C như `gcc`/`clang` hoặc MSVC, có khả năng build JNI shared library.
- JNI headers `jni.h` trong `$JAVA_HOME/include` và platform-specific include directory.
- JVM hỗ trợ native-prefix capability và agent manifest yêu cầu `Can-Set-Native-Method-Prefix: true`.
- Chỉ thực hiện thử nghiệm trong môi trường kiểm soát. Nó load native code vào cùng JVM process; không lấy library không tin cậy để thử trên máy production.

Tạo các file ở một thư mục `native-prefix-lab`:

```text
native-prefix-lab/
  NativeApi.java
  NativePrefixDemo.java
  PrefixAgent.java
  NoOpTransformer.java
  nativeprefixdemo.c
  agent.mf
```

Không có package declaration để giữ JNI symbol gốc dễ đọc. Trong ứng dụng thực, class nên có package riêng và JNI symbols phải escape tên class đầy đủ.

### 7.2. `NativeApi.java`: hai Java wrappers và một native declaration

```java
public final class NativeApi {
    static {
        System.loadLibrary("nativeprefixdemo");
    }

    private NativeApi() {
    }

    public static int sum(int a, int b) {
        System.out.println("WRAPPER_A");
        return a_sum(a, b);
    }

    private static int a_sum(int a, int b) {
        System.out.println("WRAPPER_B");
        return b_a_sum(a, b);
    }

    private static native int b_a_sum(int a, int b);
}
```

Diễn giải theo thời gian:

```text
Source concept ban đầu:    native sum(II)I

Sau transformer A giả lập:
    Java sum(II)I           -> gọi a_sum(II)I
    native a_sum(II)I

Sau transformer B giả lập:
    Java sum(II)I           -> gọi a_sum(II)I
    Java a_sum(II)I         -> gọi b_a_sum(II)I
    native b_a_sum(II)I
```

Đây là **source Java mô phỏng output đã transform**, không phải bytecode runtime được hai no-op transformers tạo ra. Cả hai prefixes được giữ ngắn `a_` và `b_` **chỉ trong bài lab** để dễ nhận diện; production nên dùng prefix độc nhất khó va chạm hơn.

### 7.3. `NativePrefixDemo.java`: ứng dụng Java

```java
public final class NativePrefixDemo {
    public static void main(String[] args) {
        int result = NativeApi.sum(4, 5);
        System.out.println("RESULT=" + result);
    }
}
```

`NativeApi` chỉ được initialize khi được sử dụng lần đầu; static block sẽ load JNI library `nativeprefixdemo`. Nếu thư viện chưa được build hoặc đường dẫn không đúng, lỗi `UnsatisfiedLinkError: no nativeprefixdemo in java.library.path` có thể xuất hiện trước khi thử phân giải `b_a_sum`.

### 7.4. `NoOpTransformer.java`: mỗi lần đăng ký là một instance riêng

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class NoOpTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {
        return null;
    }
}
```

`return null` nghĩa là **không đổi bytecode ở bước này**. Điều đó là chủ đích: wrappers đã được mô phỏng sẵn trong `NativeApi.java`, nên demo không cần bytecode generator. Trong một agent thật, transformer A phải tạo wrapper A, transformer B phải wrap tiếp native declaration của A, và cả hai phải có prefix đăng ký tương ứng.

### 7.5. `PrefixAgent.java`: hai prefixes cho hai transformer instances

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

public final class PrefixAgent {
    public static void premain(String options, Instrumentation inst) {
        boolean supported = inst.isNativeMethodPrefixSupported();
        System.out.println("PREFIX_CAPABILITY=" + supported);

        if (!supported) {
            // Không tuyên bố JNI binding đã được thiết lập.
            throw new IllegalStateException(
                    "NATIVE_METHOD_PREFIX_UNSUPPORTED");
        }

        ClassFileTransformer first = new NoOpTransformer();
        ClassFileTransformer second = new NoOpTransformer();

        // Theo đúng thứ tự các lớp wrapper đã mô phỏng.
        inst.addTransformer(first);
        inst.setNativeMethodPrefix(first, "a_");

        inst.addTransformer(second);
        inst.setNativeMethodPrefix(second, "b_");

        System.out.println("PREFIXES=a_,b_");
    }
}
```

Cả hai transformers đều đăng ký ở nhóm Java `canRetransform=false`, vì dùng overload `addTransformer(transformer)`. Chúng được tạo bằng **hai lần `new` riêng**, không dùng lại cùng một instance.

Nếu JVM không hỗ trợ capability, agent ném lỗi và startup có thể dừng; đó là **fail-fast chỉ dành cho bài lab** vì phép thử không còn ý nghĩa. Với telemetry optional của production, bạn nên báo `SKIPPED` rồi chọn fallback được duyệt thay vì làm ứng dụng dừng đột ngột.

### 7.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: PrefixAgent
Can-Set-Native-Method-Prefix: true

```

Bảo đảm file kết thúc bằng newline và dòng trống theo manifest format. Không cần `Can-Retransform-Classes: true` trong thí nghiệm; hai transformers không retransform classes. Không cần `Agent-Class` vì dùng startup agent `premain`.

### 7.7. `nativeprefixdemo.c`: JNI implementation **chỉ mang tên gốc**

```c
#include <jni.h>
#include <stdio.h>

/*
 * Chỉ có native symbol ứng với "sum", KHÔNG có symbol
 * cho Java native declaration "b_a_sum".
 */
JNIEXPORT jint JNICALL Java_NativeApi_sum(
        JNIEnv* env, jclass clazz, jint a, jint b) {

    (void) env;
    (void) clazz;

    puts("JNI_ORIGINAL");
    fflush(stdout);
    return a + b;
}
```

Native C không định nghĩa `Java_NativeApi_b_1a_1sum` cũng không định nghĩa `Java_NativeApi_a_1sum`. Nếu JVM thử normal automatic lookup cho Java declaration `b_a_sum`, nó sẽ không tìm được implementation. Chỉ sau khi áp quy tắc prefix từ hai transformer, nó mới có thể tìm tới `Java_NativeApi_sum`.

**Vì sao không dùng `javac -h` để lấy prototype trực tiếp cho symbol cuối?** `javac -h` sinh header theo **native declaration đang có trong source**, tức `b_a_sum`; trong bài lab, ta **cố ý xuất symbol JNI theo tên gốc `sum`** để kiểm tra retry. Vì vậy C function được khai báo tường minh, phải khớp signature `(II)I` và JNI calling convention. Đó là một điểm test, không phải lỗi ví dụ.

### 7.8. Biên dịch và chạy: Linux (Bash)

Đặt `JAVA_HOME` trỏ tới thư mục JDK 17+ của bạn; trình biên dịch C cài sẵn:

```shell
# Bước 1: build Java code và agent JAR.
javac NativeApi.java NativePrefixDemo.java PrefixAgent.java NoOpTransformer.java
jar cfm prefix-agent.jar agent.mf PrefixAgent.class NoOpTransformer.class

# Bước 2: build shared JNI library cho Linux.
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnativeprefixdemo.so nativeprefixdemo.c

# Bước 3: startup agent -> app -> JNI native resolution.
java -javaagent:prefix-agent.jar \
  -Djava.library.path=. \
  -cp . NativePrefixDemo
```

Lệnh cần `JAVA_HOME` hợp lệ và `gcc` trên `PATH`. Có thể kiểm tra trước:

```shell
java -version
javac -version
test -f "$JAVA_HOME/include/jni.h" && echo JNI_HEADERS_OK
```

Đoạn `test` là lệnh shell Bash, không chạy trong PowerShell. Nếu `JAVA_HOME` chưa được đặt, hãy trỏ tới thư mục JDK thật thay vì đoán đường dẫn. `java.library.path=.` cho phép `System.loadLibrary("nativeprefixdemo")` tìm file `libnativeprefixdemo.so` tại thư mục hiện tại trong môi trường Linux thường gặp.

### 7.9. Biên dịch C trên macOS hoặc Windows

Trên macOS với `clang`/`cc` và JDK đã được chọn:

```shell
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnativeprefixdemo.dylib nativeprefixdemo.c

java -javaagent:prefix-agent.jar \
  -Djava.library.path=. \
  -cp . NativePrefixDemo
```

Trên Windows, chạy **Developer Command Prompt** có MSVC compiler và `JAVA_HOME` trỏ đến JDK:

```bat
javac NativeApi.java NativePrefixDemo.java PrefixAgent.java NoOpTransformer.java
jar cfm prefix-agent.jar agent.mf PrefixAgent.class NoOpTransformer.class
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativeprefixdemo.c /link /OUT:nativeprefixdemo.dll
java -javaagent:prefix-agent.jar -Djava.library.path=. -cp . NativePrefixDemo
```

Các lệnh C cụ thể phụ thuộc toolchain/kiến trúc; sử dụng JDK và native compiler cùng kiến trúc (ví dụ x64 với x64). Ví dụ không tự bảo đảm chạy nếu hệ thống chưa có C compiler, build flags tương ứng hoặc quyền load native library.

### 7.10. Stdout mong đợi khi capability và automatic resolution hoạt động

Trên JVM HotSpot JDK 17/21 có native prefix capability và JNI library được build/load đúng:

```text
PREFIX_CAPABILITY=true
PREFIXES=a_,b_
WRAPPER_A
WRAPPER_B
JNI_ORIGINAL
RESULT=9
```

Đây là **kết quả mong đợi theo mô hình JNI native prefix của API**, không phải log từ một lần chạy đã được xác nhận trên máy hiện tại. Trật tự này có cơ sở:

1. `premain` chạy trước app, in capability và đăng ký `first→a_`, `second→b_`.
2. `NativePrefixDemo.main` gọi `NativeApi.sum(4,5)`.
3. `sum` là Java wrapper A, in `WRAPPER_A` rồi gọi `a_sum`.
4. `a_sum` là Java wrapper B, in `WRAPPER_B` rồi gọi native `b_a_sum`.
5. Normal JNI lookup cho tên `b_a_sum` thất bại vì thư viện chỉ có `Java_NativeApi_sum`. JVM xét prefixes gắn với transformer theo quy tắc, tìm implementation gốc.
6. Native C in `JNI_ORIGINAL` và trả `9`.
7. Java in `RESULT=9`.

**Giới hạn kiểm thử:** hai wrappers được viết trong source, **không** phải do `NoOpTransformer.transform` tạo. Một bài lab chuyển sang bytecode transform thực phải thêm QA cho class schema, wrapper ordering, method descriptors và tương thích với những transformer khác.

### 7.11. Đối chứng: bỏ `-javaagent`

Nếu chạy **không có agent**:

```shell
java -Djava.library.path=. -cp . NativePrefixDemo
```

Java vẫn vào `sum` rồi `a_sum`. Nhưng với native declaration `b_a_sum`, thư viện không có symbol mang tên tương ứng, và không có registered prefixes để retry. Kết quả được dự đoán là **`UnsatisfiedLinkError`** trong nhánh native resolution, không có dòng `RESULT=9`.

Không so khớp nguyên văn toàn bộ stack trace hoặc thông điệp lỗi: nó phụ thuộc JVM và platform. Điều cần chứng minh là **library được load nhưng native method không liên kết được**; nếu lỗi lại là “no nativeprefixdemo in java.library.path”, bạn đang kiểm tra sai điều kiện (library load thất bại trước khi resolution).

### 7.12. Đối chứng: chỉ đăng ký prefix đầu tiên

Nếu chỉ gán `a_` mà không có `b_`, Java source vẫn gọi native `b_a_sum`. Trong tình huống này không đủ quy tắc wrapper-prefix để quay về `sum`. Theo cơ chế minh họa, native method có thể không resolve và ném `UnsatisfiedLinkError`, trừ khi native library thật sự xuất symbol phù hợp một đường resolution khác.

Đây là lý do quan trọng phải đăng ký **một prefix cho từng lớp wrapper do từng transformer tạo**. Không thể lấy prefix của transformer A để thay thế luôn trách nhiệm của B.

## 8. Một transformer bỏ qua method: tương ứng với prefix bị bỏ giữa

Giả sử A tạo wrapper, B được đăng ký nhưng không match target, C tạo wrapper. Trạng thái class file cuối:

```text
Java foo()            -> Java wrapper A
Java a_foo()          -> Java wrapper C
native c_a_foo()      -> JNI implementation foo
```

B đã không tạo `b_foo` hay `b_a_foo`. Tên cuối là `c_a_foo`. Đây là tình huống **thực tế** khi agent có class filters, method exclusions, overload filters hoặc không đủ capability cho một transformer cụ thể.

### 8.1. Vì sao VM cần kiểm tra wrapper trung gian?

Nếu áp dụng mọi prefix một cách cứng nhắc, VM có thể thử một tên `c_b_a_foo` không tồn tại trong class. Theo Javadoc, một intermediate prefix chỉ được áp khi **non-native wrapper tương ứng hiện hữu**. Phải có dấu vết rằng transformer đã thật sự biến đổi method, không chỉ có một prefix cấu hình toàn cục.

Điều này bảo vệ tính chọn lọc: một agent chỉ wrap vài native methods vẫn có thể đăng ký prefix của mình mà không buộc mọi native method khác đi qua cùng chuỗi tên.

### 8.2. Ví dụ ma trận

| T1 prefix `a_` | T2 prefix `b_` | T3 prefix `c_` | Method native cuối có thể được tạo | Điều kiện cần |
|---|---|---|---|---|
| Có wrap | Có wrap | Có wrap | `c_b_a_foo` | Có wrappers của cả ba |
| Có wrap | Bỏ qua | Có wrap | `c_a_foo` | Có wrappers A và C |
| Bỏ qua | Có wrap | Có wrap | `c_b_foo` | Có wrappers B và C |
| Có wrap | Có wrap | Bỏ qua | `b_a_foo` | Có wrappers A và B |
| Bỏ qua | Bỏ qua | Bỏ qua | `foo` vẫn native | Không cần prefix retry nếu JNI name gốc resolve bình thường |

Đây là **mô hình tên của output transformation**, không phải cam kết mọi tổ hợp sẽ được phép nếu method descriptors/schema/loader không phù hợp. Mỗi transformer phải kiểm tra lớp/method hiện tại, không giả định tất cả transformers trước đó đã tạo wrapper.

### 8.3. Không phân giải bằng cách xóa chuỗi prefix tự viết

Một lỗi thường gặp là agent tự code logic:

```java
// Anti-pattern minh họa: không dùng làm cơ chế JNI resolution.
String original = nativeName.replace("a_", "")
                            .replace("b_", "")
                            .replace("c_", "");
```

Hàm `String.replace` này không bảo đảm đúng ranh giới prefix (có thể xóa substring giữa tên method), không xét wrapper có tồn tại, method descriptors, JNI symbol escaping hay thứ tự transformer. Tệ hơn, nó **không thay thế được cơ chế JNI của JVM**. Hãy để `setNativeMethodPrefix` xử lý retry theo hợp đồng; transformer chỉ tạo những wrappers/renamed natives hợp lệ.

## 9. Thiết kế transformer thực tế: điều kiện trước và hậu kiểm

Một transformer native wrapping chuyên nghiệp phải có một **phép biến đổi bytecode có kiểm soát**, không chỉ thay string của method name. Pseudocode:

```text
on transform(classBytes):
  parse class
  for each method:
    if method is not native:
      keep unchanged
    if !allowlisted(class, method, signature):
      keep unchanged
    if wrapper or prefixed native name already exists:
      report duplicate/conflict; SKIP or FAIL by policy

    capture original name, descriptor, flags
    move native declaration to prefix + originalName
    create non-native wrapper at originalName with same calling contract
    wrapper:
      collect approved minimal metrics
      invoke renamed native declaration using correct static/instance dispatch
      preserve return / exception semantics
    verify class file, frames, descriptors and access rules
  return new class bytes if modified else null
```

Mã trên là **thuật toán minh họa**, không phải DSL hay Java code. Các chi tiết quan trọng:

- Đúng **method descriptor**, return type, `static`/instance, access flags và ngoại lệ.
- Wrapper phải truyền nguyên argument types, không làm boxing/unboxing tùy ý khi dễ phá ABI.
- Với instance method, giữ receiver `this` đúng ngữ nghĩa.
- Không thêm trùng method name+descriptor trong cùng class.
- Native declaration mới cần được liên kết tới native implementation gốc; prefix phải khớp registration của transformer.
- Việc tạo wrapper thường làm thay **số methods và modifier `native`**; do đó **không được mặc định có thể áp cùng biến đổi bằng retransformation/redefinition** cho class đã nạp (các thay đổi schema bị giới hạn).
- Nếu helper gọi lại code ứng dụng hoặc JNI library, cần guard để tránh recursion và bảo toàn failure semantics.
- Đừng coi việc `transform` trả bytes là hậu kiểm đủ; cần JVM verify/link native và test method thật.

### 9.1. Thời điểm khởi tạo: vì sao load-time thường là tuyến chính?

Thay native method `foo` thành một Java wrapper `foo` và thêm native declaration `agent_foo` là thay đổi **method schema** của class. HotSwap tiêu chuẩn (`retransformClasses`/`redefineClasses`) thường **không** cho phép thêm/xóa/đổi tên methods. Vì vậy wrapper transformation kiểu này cần được thiết kế cho **lần định nghĩa class ban đầu** (load-time) hoặc một chiến lược phù hợp với giới hạn triển khai.

Một agent được attach sau khi target class đã load không thể chỉ gọi `setNativeMethodPrefix` rồi kỳ vọng wrapper tự xuất hiện. Cần báo `SKIPPED_EXISTING_CLASS` hoặc chọn một cơ chế khác đã được kiểm thử, thay vì ép retransform schema không hợp lệ.

### 9.2. Thứ tự transformer và idempotency

Nếu nhiều transformers cùng wrap native method:

- Mỗi transformer phải biết **tên native hiện tại** trong input bytes, có thể đã mang prefix của transformer trước.
- Quyết định tạo wrapper phải dựa vào target method thực tế (name+descriptor, owner), không khớp substring tùy ý.
- Nếu transformer chạy lại trong bối cảnh phù hợp, không được thêm hai lớp wrapper giống nhau ngoài ý muốn.
- Trong retransformation, các transformers không hỗ trợ retransformation không được gọi lại; JVM tái áp dụng kết quả trước đó theo quy tắc. Native wrappers đã tạo khi load không có nghĩa thay đổi method schema trong một lượt retransform mới luôn được phép.
- Thứ tự Java/native transformer groups có thể khác thứ tự đơn thuần của `addTransformer`, nên quy ước prefix phải phản ánh output pipeline thực.
- Nếu một transformer không wrap, **trả `null`** và không tạo prefix giả trong tên method.

### 9.3. Quy tắc chọn prefix

- Prefix thuộc về **một transformer có identity xác định**; không dùng một prefix chung cho nhiều transformer độc lập.
- Chọn tên ít có khả năng collision trong app/library; thử trên những method names/descriptors thực tế trước khi tạo.
- Nếu tên có ký tự `$`/`_`, kiểm tra JNI escaping đầy đủ; không tự suy C symbol chỉ từ một chuỗi.
- Tránh thay đổi prefix sau khi class đã load/native method đã được resolve; nếu cần rollout mới, thử bằng JVM mới.
- Khi bỏ prefix (`""`/`null`), không giả định native binding đã thiết lập sẽ tự được hủy.
- Đưa agent version, transformer ID và prefix vào log cấu hình có kiểm soát; không log raw method arguments vào hot path.

## 10. Chẩn đoán native method prefix: bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Điều nên kiểm tra |
|---|---|---|
| `isNativeMethodPrefixSupported()==false` | JVM không hỗ trợ hoặc manifest không yêu cầu | `Can-Set-Native-Method-Prefix: true`; phiên bản/VM vendor |
| `UnsupportedOperationException` khi set prefix | Capability unavailable | Precheck, manifest và JVM configuration |
| `IllegalArgumentException` khi set prefix | Transformer instance chưa đăng ký | `addTransformer(t)` phải thực hiện trước |
| `NullPointerException` khi set prefix | Transformer parameter `null` | Không nhầm với prefix `null` hợp lệ |
| `UnsatisfiedLinkError: no X in java.library.path` | Native library chưa load/tìm thấy | `System.loadLibrary`, `java.library.path`, tên thư viện theo OS |
| `UnsatisfiedLinkError` khi gọi prefixed method | JNI symbol/descriptor không khớp hoặc prefix retry không áp | Kiểm tên Java native, JNI escaping, prefix registration, library exports |
| App đã instrument nhưng không có log wrapper | Transformer không match, class đã load trước khi agent đăng ký, bytes bị transformer khác thay | Kiểm class loader, transform callbacks, load-time ordering |
| Wrapper A chạy nhưng B không chạy | B bỏ qua method hoặc B wrapper/code bị loại | Kiểm output class file và prefix/method descriptors |
| C JNI symbol đã có nhưng vẫn không link | Wrong class name, overloaded signature, architecture/ABI, loader ownership | `javap`, `nm -D`/`dumpbin`, JNI header/signature |
| Method chạy sai logic sau wrap | Return/exception handling, receiver hoặc descriptor mismatch | So sánh behavior trước/sau, test primitives/references/throws |
| Prefix quá chung như `wrapped_` | Tên đã được app định nghĩa hoặc trùng agent khác | Chọn namespace riêng; kiểm collision trước |
| RegisterNatives trả lỗi | Name/signature mismatch, wrong class, wrong mapping | Kiểm `JNINativeMethod`, method list thực và JNI exceptions |
| Chỉ register prefix, JNI vẫn gọi implementation gốc nhưng không có probe | Không có class transformation tạo Java wrapper | Đăng ký prefix không tự instrument |
| Agent attach muộn và không wrap được class đang chạy | Schema change bị giới hạn | Thiết kế startup agent hoặc fallback được báo rõ |
| Không thể dùng helper từ target class | Class-loader/module visibility | Kiểm helper path và access; prefix không chữa `NoClassDefFoundError` |
| Native call được bind trước khi thay prefix | Binding lifecycle không rollback/tự resolve lại như mong muốn | Khởi động sớm, không dựa vào đổi prefix muộn |
| Có nhiều agents, prefix order sai | Transformer order/grouping khác dự tính | Trace thứ tự callback và class bytes cuối |

### 10.1. Trình tự debug tối thiểu

1. **Precheck:** `isNativeMethodPrefixSupported` và manifest `Can-Set-Native-Method-Prefix`.
2. **Registration:** xác nhận đúng `ClassFileTransformer` instance đã add, prefix chính xác, không trùng với agent khác.
3. **Class source:** xác định binary class name, defining loader, class load order, method signatures.
4. **Output bytes:** dùng `javap -p -s -c Target` để xem đã có Java wrapper(s) và native declaration cuối chưa.
5. **Library:** kiểm `System.loadLibrary` trả thành công và shared library đúng architecture/runtime.
6. **JNI binding mode:** automatic symbol lookup hay `RegisterNatives`? Debug theo hướng retry tương ứng.
7. **JNI names:** kiểm escaped method/class names, overload descriptors. Với Linux có thể dùng `nm -D libname.so` hoặc `readelf -Ws` để xem exports; trên Windows dùng `dumpbin /exports` khi có MSVC.
8. **Runtime test:** gọi native method thật với input/expected output; phân biệt wrapper logs và JNI log.
9. **Multiple transformers:** kiểm thứ tự thực tế và những intermediate Java wrappers có tồn tại.
10. **Report:** `PREFIX_CONFIGURED` khác `WRAPPER_GENERATED`, `NATIVE_RESOLVED` và `FEATURE_VERIFIED`.

### 10.2. Định dạng báo cáo gợi ý

```json
{
  "feature": "native-call-latency",
  "targetClass": "com.example.NativeMath",
  "method": "sum",
  "descriptor": "(II)I",
  "nativePrefixCapability": true,
  "transformerId": "latency-v3",
  "registeredPrefix": "$$_agent_latency_$",
  "wrapperGenerated": true,
  "nativeResolution": "VERIFIED",
  "status": "APPLIED"
}
```

Đây là **schema log minh họa**, không phải JVM tự phát sinh. `nativeResolution=VERIFIED` chỉ nên ghi sau khi test/quan sát được native call thành công; việc `setNativeMethodPrefix` trả về không đủ để kết luận đã resolve. Nếu dynamic attach vào class đã load và không tạo được wrapper, báo `SKIPPED` với lý do thay vì báo feature đã bật.

## 11. Các giới hạn cần nói rõ trong production

### 11.1. Không tự thay thư viện JNI

Cơ chế prefix chỉ giúp **tìm đúng implementation hiện có** khi native declaration được renamed. Nó không tự đổi compiler flags, chức năng C, JNI API version, cách nạp library hay quyền chạy native code. Nếu `JNI_OnLoad` thất bại, native library sai CPU architecture, hoặc C function có signature không khớp, prefix không giúp được.

### 11.2. Không phải mọi native method đều nên wrap

Có những native methods ở tầng runtime/VM hoặc thư viện hệ thống rất nhạy cảm. Việc thay class schema/call path có thể ảnh hưởng class loading, thread synchronization, signal handling, native resource ownership hoặc các JNI assumptions. Filter target chặt, test theo JDK/OS/arch, và tránh instrument các native methods không có mục đích đo cụ thể.

### 11.3. Không quan sát được C internals chỉ vì Java wrapper

Java wrapper cho phép đo **thời điểm vào/ra** native call và thông tin được thiết kế thu thập ở Java side. Nó không tự cung cấp trace của các JNI function calls **bên trong C implementation**, và không thay một native JVMTI profiler. Nếu cần native stack/call internals, cần công cụ native phù hợp, kiểm soát quyền và overhead.

### 11.4. Thứ tự nhiều agent không phải API thay tên native toàn cục

Hai agents có thể đăng ký transformers và prefixes độc lập. Native resolution tôn trọng quy tắc ordering và wrapper existence, không đơn thuần strip mọi chuỗi trông giống prefix. Cần kiểm thử **tổ hợp agents thực tế**; không giả định agent của bạn luôn chạy đầu tiên hoặc cuối cùng.

### 11.5. Vấn đề bảo mật và riêng tư

Native method có thể nhận con trỏ, key buffers, byte arrays hoặc dữ liệu nhạy cảm qua JNI. Helper trong Java wrapper nên tránh gọi `toString`/serialize tùy tiện đối số, tránh ghi raw buffers và giữ nguyên exception/return semantics. Prefix resolution giúp linkage, không phải cơ chế để tự động bảo vệ thông tin.

## 12. Bài tập tình huống

### Tình huống A — Một transformer wrap, thư viện còn tên JNI gốc

- Ban đầu: `native int foo(int)` và symbol JNI cho `foo`.
- Sau transform: `int foo(int) { return a_foo(int); }` + `native int a_foo(int)`.
- Agent: `setNativeMethodPrefix(t,"a_")` cho đúng registered transformer.
- Automatic resolution: thử symbol cho `a_foo`, nếu không có thì thử lại tìm symbol cho `foo`.

**Kết luận:** có thể giữ implementation JNI cũ nếu mọi class/method signature và JNI binding điều kiện hợp lệ.

### Tình huống B — T1 tạo wrapper, T2 bỏ qua, T3 tạo wrapper

- Prefixes đăng ký: `a_`, `b_`, `c_`.
- Wrapped Java methods thực: `foo` và `a_foo`.
- Native declaration cuối: `c_a_foo`.
- Không có `b_a_foo`.

**Kết luận:** không bắt buộc có prefix `b_` trong native name. JVM xét intermediate wrappers để xác định chuỗi có ý nghĩa, không strip cứng mọi registered prefix.

### Tình huống C — Agent chỉ có prefix, không có wrapper

- `inst.setNativeMethodPrefix(t,"agent_")` trả thành công.
- Class target vẫn có `native foo`, không có Java wrapper.

**Kết luận:** native resolution của `foo` có thể vẫn bình thường. **Không có Java probe được chèn**, nên không được báo “native method traced”.

### Tình huống D — Prefixed declaration tồn tại nhưng library chưa load

- Class có `native agent_foo` và prefix hợp lệ.
- `System.loadLibrary` thất bại hoặc loader không tìm được native library.

**Kết luận:** prefix không khắc phục loader/library failure. Sửa đường load/packaging và kiểm JNI symbols trước.

### Tình huống E — RegisterNatives liên kết theo tên gốc

- Native code đăng ký `"foo"` + descriptor + pointer.
- Java method `foo` sau wrap là non-native.
- Prefixed native declaration `agent_foo` có mặt, prefix đã đăng ký.

**Kết luận:** khi mapping thường thất bại, cơ chế retry xem xét **tên Java method đã thêm prefix** để liên kết function pointer. Không nhầm với automatic JNI lookup đi theo chiều strip prefix khỏi implementation name.

## 13. Câu hỏi tự kiểm tra

1. **Tại sao `ClassFileTransformer` không thể chèn Java bytecode vào thân `native`?** Vì native declaration không có Java `Code` attribute; phải tạo một Java wrapper không native.
2. **`setNativeMethodPrefix` có tự tạo wrapper không?** Không. Nó chỉ thay quy tắc retry failed native resolution.
3. **Capability nào cần có?** `isNativeMethodPrefixSupported()` true và manifest yêu cầu `Can-Set-Native-Method-Prefix: true`.
4. **Gọi `setNativeMethodPrefix` trước `addTransformer` có thể bị lỗi gì?** `IllegalArgumentException` vì transformer chưa đăng ký.
5. **Truyền transformer `null` khác prefix `null` thế nào?** Transformer null gây `NullPointerException`; prefix null/tên rỗng có nghĩa tắt retry cho transformer.
6. **Với automatic JNI lookup, JVM thử gì trước?** Tra symbol theo tên native declaration hiện hành. Khi thất bại mới thử cơ chế prefix.
7. **Automatic fallback áp prefix theo chiều nào?** Bỏ prefix khỏi tên implementation cần tìm để quay lại native symbol gốc.
8. **`RegisterNatives` fallback áp theo chiều nào?** Khi mapping gốc thất bại, xét Java native method name có prefix tương ứng.
9. **Ba transformers A→B→C đều wrap `foo`, tên native cuối theo ví dụ là gì?** `c_b_a_foo`.
10. **B không wrap thì có bắt buộc tên `c_b_a_foo` không?** Không, kết quả có thể là `c_a_foo`.
11. **Vì sao một prefix trung gian chỉ được xét khi wrapper tương ứng tồn tại?** Để JVM phân biệt những transformer có thật sự wrap method với những transformer bỏ qua.
12. **Tại sao `wrapped_` bị Javadoc xem là prefix kém?** Nó có thể trùng tên method đã tồn tại.
13. **JNI symbol của Java method chứa dấu `_` có thể cần gì?** JNI escaping, ví dụ `_1`; không nối tên thô.
14. **Agent đã gán prefix nhưng quên load library. Có tự hoạt động không?** Không, native implementation vẫn phải có và được nạp.
15. **Chỉ nhìn `setNativeMethodPrefix` return thành công có kết luận probe hoạt động không?** Không; cần wrapper, native binding và effect verification.
16. **Đăng ký hai prefix bằng cùng một transformer instance nhiều lần có tốt không?** Không nên; Javadoc khuyến cáo tránh đăng ký trùng instance và cần identity rõ ràng.
17. **Native wrapping thay method schema có thể áp thoải mái bằng retransform class đã load không?** Không; HotSwap thường giới hạn thêm/xóa/đổi tên methods, nên load-time là tuyến phù hợp hơn.
18. **`removeTransformer` có tự xóa các Java wrappers đã cài không?** Không.
19. **Native prefix có phải chỉ định đường dẫn `.so`/`.dll` không?** Không; library loading là bước độc lập.
20. **`NativeMethodBind` JVMTI event có giống setNativeMethodPrefix không?** Không, đó là cơ chế theo dõi/thay binding ở JVMTI khi có capability.
21. **Trong demo, vì sao JNI C function tên `Java_NativeApi_sum` dù Java native declaration là `b_a_sum`?** Vì bài lab kiểm tra retry qua hai prefixes `a_` và `b_` để tìm implementation gốc.
22. **Không có agent, bài lab gặp lỗi gì khi gọi native `b_a_sum`?** Dự kiến `UnsatisfiedLinkError` ở native method binding, nếu library đã load và chỉ có symbol gốc.
23. **Nếu JNI C hàm sai signature, prefix có sửa được không?** Không. JNI ABI/descriptor còn phải đúng.
24. **Có nên instrument native methods hệ thống chỉ vì JVM cho phép prefix không?** Không. Cần scope, compatibility, hiệu năng và kiểm thử riêng.

## 14. Tài liệu tham khảo chính thức

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isNativeMethodPrefixSupported`, `setNativeMethodPrefix`, hai cơ chế retry, multiple transformer prefixes, exception/capability.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng tương thích với Java 17+ và yêu cầu manifest.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thứ tự bốn nhóm transformers, output bytes và retransformation behavior.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent entry points, manifest `Can-Set-Native-Method-Prefix`.
- [Java SE 21 — JNI Specification, Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): automatic JNI name mapping, name mangling, short/long symbol lookup, native library/class-loader behavior.
- [Java SE 21 — JNI Functions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): `RegisterNatives`, `JNINativeMethod`, name/signature/function pointer.
- [Java SE 21 — JVM TI Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): `SetNativeMethodPrefix`/`SetNativeMethodPrefixes` cho native JVMTI agents, multiple environments và native binding lifecycle.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-javaagent`, `-Djava.library.path` và runtime options.

**Ghi nhớ:** **mỗi transformer tạo native wrapper cần tiền tố riêng**. JVM thử JNI binding thông thường trước; chỉ khi thất bại mới dùng prefixes để thử lại, theo **đường khác nhau** với automatic symbol lookup và `RegisterNatives`. Prefix chỉ giải quyết **native resolution**, không sinh wrapper, không thay JNI library và không chứng minh probe đã hoạt động. Muốn thành công phải đồng thời có **wrapper class bytes hợp lệ + prefix đúng instance/thứ tự + JNI implementation tương thích + runtime verification**.