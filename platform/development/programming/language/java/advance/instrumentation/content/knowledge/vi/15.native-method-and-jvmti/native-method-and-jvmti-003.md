# `setNativeMethodPrefix` và `Can-Set-Native-Method-Prefix` trong Java Instrumentation

Một Java agent có thể thêm bytecode vào **phương thức Java thông thường**, nhưng một method khai báo `native` **không có thân bytecode Java** để chèn lệnh trước/sau lời gọi JNI. Để instrument ở **ranh giới Java → native**, agent thường dùng `ClassFileTransformer` tạo **một wrapper method không còn `native`** và chuyển phương thức native gốc sang **tên có tiền tố**. JVM sau đó cần một cơ chế liên kết phương thức native đã đổi tên với **JNI implementation đang mang tên cũ**.

Cặp công cụ trực tiếp giải quyết việc đó:

- **`Can-Set-Native-Method-Prefix: true`** trong `META-INF/MANIFEST.MF` của agent JAR: **yêu cầu capability** native-method prefix.
- **`Instrumentation.isNativeMethodPrefixSupported()`**: kiểm tra JVM/agent hiện tại **thực sự có capability** hay không.
- **`Instrumentation.setNativeMethodPrefix(transformer, prefix)`**: đăng ký **tiền tố gắn với một transformer đã đăng ký**, để **JNI native method resolution** có thể thử thêm cách đối chiếu tên khi lookup thông thường thất bại.

**Điểm cốt lõi:** `setNativeMethodPrefix` **không tự biến đổi `.class`, không tự tạo wrapper, không đổi tên method Java, không nạp thư viện `.dll/.so`**. Nó chỉ **sửa quy tắc thử lại khi liên kết native implementation thất bại theo cách thông thường**. Việc tạo wrapper + renamed native method là phần việc **riêng của `ClassFileTransformer`**.

Bài học thuộc nhóm **Native và JVM TI**: mô tả cơ chế Java Instrumentation, tương quan với `JVMTI SetNativeMethodPrefix`, JNI automatic resolution/`RegisterNatives`, cách dùng capability an toàn, và hai bài thực hành: một bài kiểm tra API **thuần Java 17+** và một bài kiểm chứng **JNI thực sự với thư viện C** trên Linux.

## 1. Tại sao một phương thức `native` không được instrument như method Java?

Ví dụ Java:

~~~java
package demo;

public class NativeTarget {
    public native int add(int value);
}
~~~

Một method có cờ `ACC_NATIVE` trong class file **không có thuộc tính `Code`**. Nó không mang các opcode Java như `ILOAD`, `IADD`, `INVOKESTATIC`, `IRETURN` để transformer thêm lời gọi ghi log hay timestamp vào giữa.

So sánh:

| Phương thức | Có thân `Code` để sửa? | Cách instrument thường dùng |
|---|---|---|
| `int add(int x) { return x + 5; }` | Có | Biến đổi các opcode trong method |
| `native int add(int x);` | **Không** | Tạo một **Java wrapper** có bytecode; wrapper gọi một native method riêng |
| `abstract int add(int x);` | Không | Không thể chèn vào thân abstract; cần chọn implementation cụ thể |

Mục tiêu là biến lời gọi:

~~~text
Ứng dụng
   └── NativeTarget.add(7)
         └── native implementation add → 12
~~~

thành:

~~~text
Ứng dụng
   └── NativeTarget.add(7)       // Java wrapper
         ├── trước JNI: đo thời gian / ghi sự kiện
         ├── gọi $AgentWrapped$add(7)
         │     └── native implementation add → 12
         └── sau JNI: ghi metric / cleanup
~~~

Đối với phương thức `native`, agent không tạo ra bytecode **bên trong hàm C**; nó đặt code đo tại **wrapper Java bao quanh biên JNI**. Đây là lý do *native method prefixing* có giá trị.

## 2. Trước và sau khi wrapper hóa native method

Giả sử class nguồn có method:

~~~java
public native boolean foo(int x);
~~~

Một class-file transformer có thể tạo mô hình tương đương:

~~~java
public boolean foo(int x) {
    long start = System.nanoTime();
    try {
        return $AgentWrapped$foo(x);
    } finally {
        record(System.nanoTime() - start);
    }
}

private native boolean $AgentWrapped$foo(int x);
~~~

**Đây là pseudocode ở mức Java cho kết quả một phép biến đổi class file**, không phải hai method để dán nguyên xi vào class nguồn mà không khai báo `record(...)`. Trong biến đổi thật:

1. Method Java **`foo(int)`** giữ nguyên tên và descriptor để mã ứng dụng vẫn gọi `foo` như trước, nhưng bỏ cờ `ACC_NATIVE` và có thân `Code`.
2. Method native được đặt tên **`$AgentWrapped$foo`**; cần giữ **cùng kiểu tham số/return** và các modifier cần thiết để liên kết và call hợp lệ.
3. Wrapper ghi metric rồi gọi native method đã đổi tên.
4. Một JNI library cũ có thể vẫn export implementation của tên **`foo`**, không phải `$AgentWrapped$foo`. Đó là phần mà `setNativeMethodPrefix` hỗ trợ khi JVM liên kết.
5. Class bytes cuối phải vượt qua class-file verifier. Nếu sửa wrapper phức tạp, phải xử lý đúng constant pool, method descriptors, operand stack, exception table và stack map frames.

Vì JNI names và binding liên quan class/method identity, không thể chỉ `String.replace` bừa trong file `.class`. Việc **thêm wrapper method, thay đổi `ACC_NATIVE` và xây code** thuộc class-file transformation; cần ASM, Byte Buddy hoặc Class-File API trên JDK phù hợp.

## 3. Manifest: `Can-Set-Native-Method-Prefix`

Manifest của agent chạy bằng `-javaagent`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

Bốn quy tắc cơ bản:

1. Thuộc tính phải ở **main section** của **manifest bên trong agent JAR** mà JVM thực sự nạp, không phải một file `.MF` nằm rời rạc hoặc manifest của app JAR bất kỳ.
2. **`Can-Set-Native-Method-Prefix` mặc định là `false`** khi thiếu. Boolean `true`/`false` không phân biệt hoa thường; giá trị khác `true` được coi là `false`.
3. Khai báo `true` là **yêu cầu capability**, không bắt buộc mọi JVM cung cấp. Cần kiểm tra runtime bằng `isNativeMethodPrefixSupported()`.
4. `Premain-Class` chỉ định class có callback `premain` khi dùng `-javaagent`. Nếu agent được nạp động trong môi trường cho phép, entrypoint thường dùng `Agent-Class`/`agentmain`; đó là cơ chế khởi động khác, không làm thay đổi ý nghĩa capability.

**Không nhầm với hai thuộc tính khác:**

| Manifest attribute | Capability |
|---|---|
| `Can-Set-Native-Method-Prefix` | Cho phép cấu hình **native method prefix lookup fallback** |
| `Can-Retransform-Classes` | Cho phép retransform lớp đã tải theo hợp đồng JVM |
| `Can-Redefine-Classes` | Cho phép redefine lớp đã tải với bộ class-file bytes mới |

Ba cờ **độc lập**. Bật native prefix không tự cấp quyền retransform hoặc redefine. Để tạo wrapper chứa **method mới** và đổi cấu trúc method, cách thường gặp là **biến đổi ở lần định nghĩa class ban đầu**, vì redefinition/retransformation của class đã tải có nhiều giới hạn về thêm/xóa method và sửa schema.

## 4. Ba API Java cần hiểu đúng

### 4.1. Hỏi capability

~~~java
boolean supported = inst.isNativeMethodPrefixSupported();
~~~

`inst` là instance `java.lang.instrument.Instrumentation` do JVM truyền vào `premain`/`agentmain`, không phải object do ứng dụng tự tạo.

`true` nghĩa là trong **cấu hình JVM hiện tại**, việc set native prefix được hỗ trợ (manifest phù hợp và JVM có capability). `false` nghĩa là không được. Theo API, gọi nhiều lần trong **cùng JVM** cho cùng một kết quả.

Không thể suy ra “native method nào cũng đang được instrument” từ `true`; đây chỉ là khả năng cấu hình resolution.

### 4.2. Đăng ký transformer trước

~~~java
ClassFileTransformer transformer = new ClassFileTransformer() {
    // Có thể override transform(...) để xây wrapper class file.
};

inst.addTransformer(transformer, false);
~~~

Đây là một đoạn Java hợp lệ nằm bên trong callback agent (cần import `java.lang.instrument.ClassFileTransformer`). Việc đăng ký transformer làm nó tham gia **chuỗi biến đổi class file** ở các thời điểm mà API hỗ trợ. Với demo thực tế bên dưới, transformer **chủ ý không sửa bytes** vì class Java đã có wrapper được biên dịch sẵn.

**Transformer phải đã được đăng ký với `addTransformer` trước khi set prefix.** `setNativeMethodPrefix` cho một transformer chưa đăng ký sẽ ném `IllegalArgumentException`.

### 4.3. Set tiền tố

~~~java
if (inst.isNativeMethodPrefixSupported()) {
    inst.setNativeMethodPrefix(transformer, "$AgentWrapped$");
}
~~~

Cú pháp:

~~~java
void setNativeMethodPrefix(
        ClassFileTransformer transformer, String prefix);
~~~

Ý nghĩa:

- `transformer`: **chính object đã được `addTransformer` đăng ký**, không phải chỉ object mới cùng một class.
- `prefix`: chuỗi tên tiền tố transformer sử dụng khi **đặt tên native method được wrapper hóa**.
- **`null` hoặc chuỗi rỗng `""`**: **không thử lại native resolution bằng prefix cho transformer đó**.
- **Một prefix riêng cho mỗi transformer** giúp JVM phân tích nhiều lớp wrapper được áp dụng tuần tự.

**Tên prefix nên khó trùng với tên method hợp lệ hiện có**, ví dụ `"$MyAgentNative$"` hoặc prefix có namespace cố định riêng agent. Tên ngắn như `"wrapped_"` có thể đụng method đã tồn tại; đặc tả Oracle cũng cảnh báo điều này.

Không nên chọn prefix ngẫu nhiên mỗi lần callback trong khi native method đã bị đổi tên bằng prefix cũ. Prefix cần **khớp chính xác** với cách transformer đặt tên và phải tồn tại trong giai đoạn JVM còn có thể liên kết các native methods tương ứng.

## 5. `setNativeMethodPrefix` thực sự thay đổi **native method resolution** như thế nào?

Có hai đường JNI binding tiêu biểu:

1. **Automatic native resolution**: JVM tự tìm symbol JNI tương ứng trong native libraries đã nạp.
2. **Explicit registration** bằng JNI **`RegisterNatives`**: native code đăng ký phương thức Java với con trỏ hàm C/C++.

Cả hai đều được API native prefix hỗ trợ, nhưng chiều thử lại tên hơi khác nhau.

### 5.1. Automatic resolution

Giả sử transformer đổi native method Java `foo` thành `$AgentWrapped$foo`, còn thư viện cũ vẫn export:

~~~text
Java_somePackage_someClass_foo
~~~

Khi phương thức native `$AgentWrapped$foo` được gọi:

~~~text
Bước 1: JVM thử JNI name thông thường của "$AgentWrapped$foo".
             │
             ├─ Nếu tìm thấy symbol khớp: sử dụng như bình thường.
             │
             └─ Nếu không tìm thấy:
                  thử loại bỏ prefix "$AgentWrapped$"
                  khi đối chiếu implementation name
                        │
                        ▼
             JNI symbol gốc của "foo"
~~~

Ở bước fallback, **JVM không sửa tên class/method trong bytecode**; nó chỉ dùng quy tắc phân giải tên bổ sung để đi tới implementation của `foo`. Nếu thư viện native gốc không được nạp hoặc không chứa symbol đúng, prefix **không** thể tạo ra implementation.

Điểm quan trọng: prefix **chỉ được xét khi resolution thông thường thất bại**. Nó không vô hiệu hóa những symbol JNI thực sự khớp tên prefixed và không ép tất cả native method chuyển hướng vô điều kiện.

### 5.2. Explicit `RegisterNatives`

JNI có dạng:

~~~c
jint RegisterNatives(
        JNIEnv *env, jclass clazz,
        const JNINativeMethod *methods, jint nMethods);
~~~

Khi native library dùng `RegisterNatives` với tên cũ `foo`, trong class đã biến đổi có thể tồn tại:

~~~text
foo(int)                  → Java wrapper, KHÔNG native
$AgentWrapped$foo(int)     → native method thật
~~~

Với prefix đã đăng ký, nếu association thông thường cho `foo` thất bại, JVM có thể **thử thêm prefix** để tìm đúng method native `$AgentWrapped$foo` và gắn function pointer vốn được cung cấp dưới tên `foo`.

Đây là **đường thử ngược chiều** so với automatic JNI symbol lookup:

| JNI binding | Ban đầu JVM thử | Fallback khi thất bại |
|---|---|---|
| Automatic | Prefixed native Java method → symbol JNI có tiền tố | Bỏ prefix khỏi tên implementation cần tìm → symbol JNI tên gốc |
| `RegisterNatives` | Tên method trong bảng native registration | Thêm prefix vào tên Java method ứng viên để tìm native method đã đổi tên |

Cơ chế này không phải một trình biên dịch JNI, không sửa DLL/SO và không bảo đảm provider/native function đúng nếu class loader, symbol hoặc method descriptor sai.

## 6. Thực hành 1: kiểm tra capability và các lỗi API bằng Java 17+

Bài đầu **không cần C compiler**. Nó chứng minh manifest quyết định capability, một transformer hợp lệ phải được đăng ký trước và những lỗi liên quan đến object transformer. Đây **không phải** bài demo native binding; ví dụ JNI thật ở phần sau.

Cấu trúc:

~~~text
prefix-api-lab/
├── src/demo/
│   ├── PrefixAgent.java
│   ├── ProbeTarget.java
│   └── ProbeMain.java
├── PREFIX-ON.MF
├── PREFIX-OFF.MF
└── out/
~~~

### 6.1. `src/demo/PrefixAgent.java`

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class PrefixAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("supported="
                + inst.isNativeMethodPrefixSupported());

        ClassFileTransformer transformer =
                new ClassFileTransformer() {
                    @Override
                    public byte[] transform(
                            Module module,
                            ClassLoader loader,
                            String className,
                            Class<?> classBeingRedefined,
                            ProtectionDomain protectionDomain,
                            byte[] classfileBuffer) {
                        if ("demo/ProbeTarget".equals(className)) {
                            System.out.println("transformTarget=true");
                        }
                        return null;
                    }
                };

        inst.addTransformer(transformer, false);

        try {
            inst.setNativeMethodPrefix(transformer, "$Agent_");
            System.out.println("prefix=registered");
        } catch (UnsupportedOperationException error) {
            System.out.println("prefix=unsupported");
        }

        if (inst.isNativeMethodPrefixSupported()) {
            try {
                inst.setNativeMethodPrefix(
                        new ClassFileTransformer() {},
                        "$Unknown_");
            } catch (IllegalArgumentException error) {
                System.out.println(
                        "unregistered=IllegalArgumentException");
            }

            try {
                inst.setNativeMethodPrefix(null, "$Other_");
            } catch (NullPointerException error) {
                System.out.println(
                        "nullTransformer=NullPointerException");
            }
        }
    }
}
~~~

**Giải thích:**

- `transformer` được đăng ký **bằng object cụ thể**; prefix set cho chính object ấy.
- Hàm `transform` chỉ in log cho `demo/ProbeTarget`, rồi **`return null`**. Nó **không sửa `.class`** và không tạo wrapper. Vì vậy chương trình này đo **API registration**, không chứng minh JNI liên kết.
- Prefix vẫn được set hợp lệ vì JVM/agent có capability nếu `isNativeMethodPrefixSupported()` là `true`.
- Với một transformer **chưa đăng ký** (anonymous instance thứ hai), API ném `IllegalArgumentException`.
- Với `transformer=null`, API ném `NullPointerException`.
- Manifest tắt capability khiến lời gọi hợp lệ khác (`setNativeMethodPrefix` trên transformer đã đăng ký) ném `UnsupportedOperationException`; code bắt và in `prefix=unsupported`.

### 6.2. `src/demo/ProbeTarget.java`

~~~java
package demo;

public final class ProbeTarget {
    public static String message() {
        return "ok";
    }
}
~~~

### 6.3. `src/demo/ProbeMain.java`

~~~java
package demo;

public final class ProbeMain {
    public static void main(String[] args) {
        System.out.println("result=" + ProbeTarget.message());
    }
}
~~~

### 6.4. Hai file manifest

`PREFIX-ON.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

`PREFIX-OFF.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: false

~~~

Giữ **dòng trống kết thúc**. Ngoài `false`, việc **bỏ hẳn** thuộc tính trong manifest cũng làm nó mặc định `false`.

### 6.5. Biên dịch, đóng JAR và chạy

Từ `prefix-api-lab`, tạo thư mục `out`. Với Bash/Git Bash:

~~~bash
mkdir -p out
~~~

Với Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Chạy JDK 17+:

~~~bash
javac --release 17 -d out src/demo/PrefixAgent.java src/demo/ProbeTarget.java src/demo/ProbeMain.java

jar --create --file agent-on.jar --manifest PREFIX-ON.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class' -C out 'demo/PrefixAgent$2.class'
jar --create --file agent-off.jar --manifest PREFIX-OFF.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class' -C out 'demo/PrefixAgent$2.class'
jar --create --file app.jar -C out demo/ProbeMain.class -C out demo/ProbeTarget.class

java -javaagent:agent-on.jar -cp app.jar demo.ProbeMain
java -javaagent:agent-off.jar -cp app.jar demo.ProbeMain
~~~

Lưu ý `PrefixAgent$1.class` và `PrefixAgent$2.class` là các anonymous class do compiler sinh ra; **phải đưa cả hai vào agent JAR**. Dấu nháy đơn quanh tên trong lệnh `jar` tránh Bash/PowerShell diễn giải `$1`, `$2` thành biến. Có thể thay bằng một lệnh đóng gói toàn bộ class files của agent khi cấu trúc dự án được phân tách phù hợp.

**Stdout đã được kiểm chứng trên JDK 24, biên dịch bằng `--release 17`:**

Khi dùng `agent-on.jar`:

~~~text
supported=true
prefix=registered
unregistered=IllegalArgumentException
nullTransformer=NullPointerException
transformTarget=true
result=ok
~~~

Khi dùng `agent-off.jar`:

~~~text
supported=false
prefix=unsupported
transformTarget=true
result=ok
~~~

Đọc kết quả:

- `supported=true` thể hiện capability được manifest yêu cầu **và** JVM cấp.
- `prefix=registered` không có nghĩa `ProbeTarget` được instrument; vì transformer `return null`, `message()` vẫn trả `"ok"`.
- `IllegalArgumentException` và `NullPointerException` chứng minh điều kiện tiền tố về transformer registration và tính hợp lệ của tham số.
- `supported=false` không cản `addTransformer(..., false)` hoạt động cho **lần định nghĩa class Java**, chỉ cản set prefix cho JNI resolution.

**Không chạy thêm biến thể `prefix=""` hoặc `prefix=null` trong bài chính**, vì chúng tắt tính năng retry đối với transformer đó. Nếu chủ động thay prefix khi lớp đã có prefixed native methods, cần xét thời điểm JNI resolution: binding có thể diễn ra muộn hơn class loading.

## 7. Thực hành 2: JNI end-to-end với một wrapper có sẵn

Bài này **có cả Java + C** và chứng minh **native resolution fallback thật sự**. Để tập trung vào `setNativeMethodPrefix`, ta **biên dịch sẵn** Java wrapper và native method mang tiền tố; một transformer no-op chỉ cung cấp registration gắn prefix. Ở agent production, wrapper tương đương phải do **class-file transformer tạo ra trong lần định nghĩa class ban đầu**. Không nhầm ví dụ prewrapped này với một transformer có khả năng tự viết bytecode.

**Môi trường đã thử:** OpenJDK 21 trên Linux và GCC; Java source biên dịch `--release 17`. Không cần Gradle/Maven hoặc thư viện Java bên ngoài. Nếu chạy trên Windows/macOS, phải có C compiler và dùng cách xây native library dành riêng hệ điều hành, xem cuối phần này.

Cấu trúc:

~~~text
native-prefix-jni/
├── src/demo/
│   ├── PrefixAgent.java
│   ├── NativeTarget.java
│   └── NativeMain.java
├── native.c
├── ON.MF
├── OFF.MF
└── out/
~~~

### 7.1. `src/demo/PrefixAgent.java` (agent gắn prefix)

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

public final class PrefixAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("supported="
                + inst.isNativeMethodPrefixSupported());

        ClassFileTransformer transformer =
                new ClassFileTransformer() {};
        inst.addTransformer(transformer, false);

        if (inst.isNativeMethodPrefixSupported()) {
            inst.setNativeMethodPrefix(transformer, "$AgentWrapped$");
            System.out.println("prefix=registered");
        } else {
            System.out.println("prefix=unsupported");
        }
    }
}
~~~

Ở đây `ClassFileTransformer` dùng **default/no-op implementation**, chỉ để JVM có một registered transformer tương ứng prefix. Java source `NativeTarget` bên dưới **đã có sẵn wrapper**; ví dụ nhằm cô lập đúng phần **JNI link resolution**.

### 7.2. `src/demo/NativeTarget.java`

~~~java
package demo;

public final class NativeTarget {
    public int add(int x) {
        System.out.println("wrapper-enter");
        int result = $AgentWrapped$add(x);
        System.out.println("wrapper-exit");
        return result;
    }

    private native int $AgentWrapped$add(int x);
}
~~~

**Phương thức `add(int)` không native**, có bytecode để instrument. **Phương thức `$AgentWrapped$add(int)` là native**, không có bytecode và đòi JNI binding. Prefix chính xác là `"$AgentWrapped$"`; phần tên gốc còn lại là `add`.

`javac` chấp nhận dấu `$` trong Java identifiers, dù tên như vậy không nên dùng bừa trong API ứng dụng. Ở một class thật ban đầu chỉ có `native int add(int)`, transformer sẽ chịu trách nhiệm tạo một class có cấu trúc tương đương đoạn trên.

### 7.3. `src/demo/NativeMain.java`

~~~java
package demo;

public final class NativeMain {
    public static void main(String[] args) {
        System.load(args[0]);

        try {
            System.out.println(
                    "value=" + new NativeTarget().add(7));
        } catch (UnsatisfiedLinkError error) {
            System.out.println(
                    "nativeResolution="
                            + error.getClass().getSimpleName());
        }
    }
}
~~~

`System.load` nhận **đường dẫn tuyệt đối** của native library. `UnsatisfiedLinkError` được bắt có chủ đích để so sánh hai cấu hình; production không nên dùng cách này để che lỗi JNI. Nếu chính `System.load` thất bại (thiếu file, sai architecture), lỗi xảy ra **trước khối `try`**; cần sửa đường dẫn/library thay vì kết luận native prefix không hoạt động.

### 7.4. `native.c` — implementation JNI chỉ mang **tên gốc**

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_demo_NativeTarget_add(JNIEnv* env, jobject self, jint x) {
    return x + 5;
}
~~~

Điểm đặc biệt: thư viện **không export** một hàm tên tương ứng `$AgentWrapped$add`, mà chỉ export JNI name của method gốc **`add`**. Đó là tiền đề để thử fallback.

JNI function nhận `JNIEnv*`, `jobject` của instance (vì Java method không `static`) và `jint x`. `JNIEXPORT`/`JNICALL` là macro từ `jni.h`. Ở đây native implementation luôn trả `x+5`, nên `add(7)` cho `12`.

Bài này **không dùng `RegisterNatives`**, mà kiểm tra **automatic JNI symbol resolution**. Phần `RegisterNatives` đã được giải thích ở phần 5, nhưng không giả vờ rằng nó được chạy trong demo.

### 7.5. `ON.MF` và `OFF.MF`

`ON.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

`OFF.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: false

~~~

### 7.6. Lệnh đầy đủ trên Linux (đã kiểm chứng)

Tạo `out`:

~~~bash
mkdir -p out
~~~

Biên dịch Java theo Java 17, đóng agent và ứng dụng **thành JAR riêng**:

~~~bash
javac --release 17 -d out src/demo/PrefixAgent.java src/demo/NativeTarget.java src/demo/NativeMain.java

jar --create --file agent-on.jar --manifest ON.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class'
jar --create --file agent-off.jar --manifest OFF.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class'
jar --create --file app.jar -C out demo/NativeTarget.class -C out demo/NativeMain.class
~~~

**Biên dịch native library bằng GCC**, dùng JNI headers của JDK hiện hành:

~~~bash
JDK_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

gcc -shared -fPIC \
    -I"$JDK_HOME/include" \
    -I"$JDK_HOME/include/linux" \
    native.c -o libnativeprefixdemo.so
~~~

Ở môi trường JDK tùy biến, cần xác nhận biến `JDK_HOME` trỏ tới đúng bộ headers `jni.h` và `jni_md.h`. File native output trên Linux là `.so`. Dấu `\` kết thúc dòng trong Bash chỉ cho phép nối câu lệnh; có thể viết GCC trên một dòng.

Chạy **trong hai JVM riêng**:

~~~bash
java -javaagent:agent-on.jar -cp app.jar demo.NativeMain "$PWD/libnativeprefixdemo.so"
java -javaagent:agent-off.jar -cp app.jar demo.NativeMain "$PWD/libnativeprefixdemo.so"
~~~

Đường dẫn `"$PWD/libnativeprefixdemo.so"` là **absolute path** mà `System.load` yêu cầu.

**Stdout đã kiểm chứng trên OpenJDK 21 + GCC:**

Manifest **ON**:

~~~text
supported=true
prefix=registered
wrapper-enter
wrapper-exit
value=12
~~~

Manifest **OFF**:

~~~text
supported=false
prefix=unsupported
wrapper-enter
nativeResolution=UnsatisfiedLinkError
~~~

### 7.7. Vì sao output xác nhận đúng cơ chế?

Trong cả hai JVM, class files `NativeTarget` và native library là **giống hệt nhau**. Chỉ manifest của **agent** khác.

- **ON:** Native method Java tên `$AgentWrapped$add` được gọi. Lookup JNI theo tên prefixed không tìm thấy. JVM **thử bỏ prefix theo cấu hình đã đăng ký**, tìm được symbol `Java_demo_NativeTarget_add`, trả `12`, rồi wrapper in `wrapper-exit`.
- **OFF:** JNI lookup không có prefix fallback; cùng native method `$AgentWrapped$add` **không tìm thấy symbol**. JVM ném `UnsatisfiedLinkError` trước khi wrapper có thể in `wrapper-exit`.
- **Không có bước classfile rewrite trong ví dụ này**: cả Java wrapper lẫn prefixed native method đều có sẵn từ source. Thực hành cô lập khả năng **native method prefix resolution**; nó không chứng minh agent đã tự tạo wrapper.
- Nếu JVM không hỗ trợ capability dù manifest ON, kết quả sẽ theo nhánh unsupported. Không nên coi mọi bản phân phối JVM sẽ cho output ON thành công.
- Native library chỉ được `System.load` nạp vào JVM. Prefix không làm library xuất hiện nếu `System.load` thiếu.

**Trên Windows**, extension thường là `.dll`, cần JNI headers dưới `include/win32` và C compiler toolchain tương thích (MSVC/MinGW). **Trên macOS**, extension thường là `.dylib` và compile/link flags khác. Các lệnh Linux ở trên **không được dùng nguyên xi** cho hai hệ điều hành đó; hãy biên dịch thư viện đúng target OS/architecture trước rồi truyền absolute path tương ứng cho `NativeMain`.

## 8. Debug lớp Java và JNI symbol trong thí nghiệm

### 8.1. Xem các method thực sự trong class file

~~~bash
javap -p -s out/demo/NativeTarget.class
~~~

Bạn sẽ thấy có **method Java wrapper** `add(int)` và **native method** `$AgentWrapped$add(int)`; cả hai cùng nhận `int`, trả `int` nên descriptor JVM là `(I)I`.

Cờ `native` thuộc **method thứ hai**. Có thể dùng `javap -v` để xem `ACC_NATIVE` và xác nhận method đó không có thuộc tính `Code`.

### 8.2. Xem symbol do thư viện Linux export

~~~bash
nm -D libnativeprefixdemo.so | grep Java_demo_NativeTarget_add
~~~

Nếu có công cụ `nm`, kết quả tìm thấy JNI symbol của **tên gốc**, không phải tên `$AgentWrapped$add`. Không cần `nm` để thực thi demo; đây chỉ là bước hỗ trợ debug native symbol export.

### 8.3. Những cách thí nghiệm có thể hỏng

- `ClassNotFoundException` cho `demo.NativeMain`: kiểm tra `app.jar` trên `-cp`.
- `NoClassDefFoundError` cho `demo.PrefixAgent$1`: quên đóng anonymous class vào **agent JAR**.
- `UnsatisfiedLinkError: Can't load library`: absolute path không đúng, `.so`/`.dll` thiếu hoặc architecture không phù hợp.
- `UnsatisfiedLinkError` dù manifest bật: prefix khác tên method, library không có symbol, native method chưa được wrap đúng, JVM không hỗ trợ capability hoặc lookup theo class/signature không phù hợp.
- `NoSuchMethodError` ở wrapper: class file và helper methods không tương thích; xem tên/descriptor, biến đổi có phá schema không.
- JVM verifier từ chối class đã transform: class-file bytes bị tạo sai. Trường hợp này **khác** native-method resolution thất bại.

Trong ứng dụng thật, `native` method có thể dùng nhiều tên JNI export do overload và chữ ký. Đừng coi một tên symbol ngắn như `Java_demo_NativeTarget_add` là công thức đầy đủ cho **mọi** chữ ký; hãy theo JNI Name Mangling Spec và kiểm tra overload khi viết native library.

## 9. Từ ví dụ “prewrapped” đến một `ClassFileTransformer` thật

Một transformer production thường có flow:

~~~text
Lớp gốc chưa được JVM định nghĩa
  |
  v
ClassFileTransformer.transform(...)
  |
  +-- Lọc class + native method mục tiêu theo name/descriptor/flags
  |
  +-- Thay "native int add(int)" thành Java wrapper "int add(int)"
  |      - đặt Code attribute hợp lệ
  |      - thêm đo lường / logging
  |      - gọi "$AgentWrapped$add"
  |
  +-- Tạo native method "$AgentWrapped$add(int)"
  |      - giữ descriptor và linkage hợp lệ
  |      - có ACC_NATIVE và KHÔNG có Code
  |
  +-- return byte[] class file mới
  |
  v
JVM định nghĩa class đã biến đổi
  |
  v
Lời gọi Java add() → wrapper → "$AgentWrapped$add" → JNI fallback
~~~

Đây là **quy trình khái niệm**, không phải một `transform` triển khai hoàn chỉnh. Việc tạo bytes có thể thực hiện bằng:

- **ASM/Byte Buddy** trên các JDK mục tiêu hỗ trợ, đặc biệt khi agent muốn chạy trên Java 17.
- **Java Class-File API** (`java.lang.classfile`) được chuẩn hóa từ **JDK 24**; muốn dùng API này trong agent, **JVM chạy agent phải có API tương ứng**, không thể biên dịch bằng JDK 24 rồi chạy thẳng trên Java 17.
- Một class-file generation toolkit có khả năng tạo Code, exception table và frames đúng với class version mục tiêu.

**Những yêu cầu tối thiểu của transformer:**

1. Chọn đúng class từ `className`, loader/module, tránh instrument class bootstrap/JDK hoặc chính agent khi chưa thiết kế riêng.
2. Chọn đúng native method theo **tên và full method descriptor**, không chỉ tên.
3. Phát hiện **đã wrapper hóa hay chưa**; đừng thêm cùng wrapper/native method trùng tên nếu transformer có thể chạy lại.
4. Giữ semantics của **static vs instance**, method parameters, return type, access flags cần thiết và exceptions.
5. Đảm bảo wrapper khôi phục/trả kết quả hoặc ném exception đúng theo nghiệp vụ. Instrumentation trong `finally` không được để recorder tự ném lỗi che exception JNI.
6. Không thay public method API mà caller dùng; wrapper nên giữ tên và chữ ký ban đầu.
7. Không tạo tên prefix dễ trùng. Nếu nhiều agents/wrappers cùng tham gia, xử lý thứ tự và classfile schema phù hợp.
8. Đăng ký prefix **trước khi native method có thể được liên kết**, và giữ nó đủ lâu vì JNI resolution có thể diễn ra muộn.
9. Không dựa vào `redefineClasses` để thêm method mới vào class **đã tải**. Các giới hạn class schema khiến việc tạo wrapper ở lần **class load đầu** thường thích hợp hơn.
10. Kiểm tra `isNativeMethodPrefixSupported()` và có fallback hữu ích nếu capability không tồn tại.

## 10. Nhiều agent và nhiều lớp wrapper

Mỗi `ClassFileTransformer` có thể tạo một wrapper khác nhau, nên **mỗi transformer cần prefix riêng**. Theo đặc tả:

~~~text
foo
  → $trans1_foo
  → $trans2_$trans1_foo
  → $trans3_$trans2_$trans1_foo
~~~

Trong thực tế, các wrapper có thể được đặt theo thứ tự biến đổi; một lớp wrapper chỉ xuất hiện khi transformer đó **thực sự wrapper hóa** method. Ví dụ nếu transformer thứ hai không sửa `foo`, chuỗi prefix có thể chỉ gồm `$trans3_$trans1_foo`.

JVM xét các prefix theo thứ tự phù hợp với transformation chain, và **không tự giả định một prefix trung gian tồn tại**: đặc tả dùng sự tồn tại của wrapper non-native tương ứng để suy ra chuỗi prefix đúng.

**Vì sao không dùng chung prefix?** Khi hai transformer dùng cùng prefix mà có method trùng tên, tên cuối có thể mơ hồ, JNI lookup nhầm method hoặc khó chẩn đoán. Mỗi agent nên có namespace prefix rõ ràng, đồng thời kiểm tra tên method trước/sau biến đổi.

**Tại sao không hủy prefix quá sớm?** JVM TI nêu rõ native binding có thể được trì hoãn tùy ý. Prefix phải được giữ **chừng nào còn prefixed native methods cần được liên kết**. Tắt prefix `null`/`""` trong khi class đã biến đổi còn dùng native method prefixed có thể khiến các lượt native resolution về sau thất bại.

Nội dung trên là **Java Instrumentation/JVMTI method prefixing**, không phải **`MethodHandles.Lookup`**, cũng không phải tính năng đổi tên method trong source code Java.

## 11. `setNativeMethodPrefix` không thay thế các JVMTI native event khác

Ở tầng native agent, JVMTI còn có:

- **`SetNativeMethodPrefix`**: cùng ý tưởng **JNI resolution fallback** theo prefix, yêu cầu capability `can_set_native_method_prefix`.
- **`SetNativeMethodPrefixes`**: một JVM TI environment, ví dụ meta-agent, có thể cung cấp **một danh sách prefix** cho nhiều phép biến đổi độc lập.
- **`NativeMethodBind` event**: quan sát thời điểm JVM bind native method với địa chỉ hàm native và có thể chuyển hướng binding trong điều kiện JVMTI phù hợp; đây là **cơ chế khác** so với tạo Java wrapper và set prefix.
- **`RegisterNatives`**: JNI function native code dùng để đăng ký implementation, không phải Java `Instrumentation` API.

Không nhập nhằng:

| Mục tiêu | API/cơ chế |
|---|---|
| Cho native wrapper mới liên kết tới JNI implementation tên cũ | `setNativeMethodPrefix` |
| Chèn bytecode Java ghi latency trước/sau JNI call | `ClassFileTransformer` xây Java wrapper |
| Theo dõi native bind ở JVMTI native agent | `NativeMethodBind` |
| Gắn JNI function pointer tường minh từ native library | `RegisterNatives` |
| Biến đổi bytecode method Java không native | Class-file transformation bình thường |

Việc JNI library có cơ chế lookup riêng, `JNI_OnLoad`, `RegisterNatives`, class loader visibility và module access khiến native instrumentation phức tạp hơn việc chèn một `System.nanoTime()` vào method Java thông thường. Khi nào cần tác động đến **bên trong hàm C/C++**, Java wrapper **không cung cấp** quyền quan sát từng lệnh native; cần profiler/native tooling thích hợp.

## 12. Xử lý lỗi của Java API

Hợp đồng `setNativeMethodPrefix` có ba ngoại lệ chính:

| Ngoại lệ | Khi nào | Cách xử lý |
|---|---|---|
| `UnsupportedOperationException` | JVM/agent **không hỗ trợ** capability (`isNativeMethodPrefixSupported() == false`) | Kiểm tra `Can-Set-Native-Method-Prefix` trong **agent JAR thực tế**; hỏi runtime; không ép gọi API |
| `IllegalArgumentException` | `transformer` **chưa được đăng ký** bằng `addTransformer` | Giữ đúng instance đã đăng ký, không tạo instance mới khi set prefix |
| `NullPointerException` | `transformer == null` | Đảm bảo object hợp lệ, khởi tạo trước khi gọi |

`prefix == null` **không** phải lỗi tương đương `transformer == null`: prefix null dùng để **tắt retry** của transformer đó. Có thể truyền `""` để không thử lại theo prefix.

**Cách viết phòng thủ trong `premain`:**

~~~java
ClassFileTransformer transformer = createTransformer();

inst.addTransformer(transformer, false);

if (inst.isNativeMethodPrefixSupported()) {
    inst.setNativeMethodPrefix(transformer, "$MyAgentNative$");
} else {
    // Không tạo prefixed native wrapper nếu không có chiến lược
    // JNI binding tương thích; có thể bỏ qua instrumentation native.
}
~~~

Đây là **fragment**, cần phương thức `createTransformer()` do agent định nghĩa. Đáng chú ý: nếu JVM không có capability, **đừng vẫn tạo native method có prefix rồi hy vọng sẽ link**. Hãy chọn fallback rõ ràng, chẳng hạn không instrument native methods, hoặc dùng cách đo khác không cần renaming.

Khi agent chạy với `-javaagent`, exception không bắt trong `premain` có thể làm JVM **abort startup**. Vì vậy validation capability và transformer registration phải diễn ra trước các thay đổi rủi ro.

## 13. Những điều kiện JNI cần kiểm tra độc lập

**Có prefix hợp lệ chưa đủ để native method chạy.** Một lời gọi JNI còn phụ thuộc:

1. **Class loader/library association:** native library phải được nạp vào ngữ cảnh phù hợp; nhiều loader/plugin có quy tắc riêng về nạp native libraries.
2. **Đúng kiến trúc:** x86-64/ARM64, 32/64-bit và ABI toolchain phải khớp JVM.
3. **Đúng symbol name:** JNI mangling theo tên class/package/method và descriptor nếu có overload. Prefix lookup không bỏ qua các thành phần còn lại.
4. **Đúng kiểu method:** `static` native dùng `jclass` thay vì `jobject` ở vị trí đối số thứ hai của JNI function; instance native dùng `jobject`.
5. **Đúng method descriptor:** `int` là `I`, `long` là `J`, mảng/object có encoding riêng. Wrapper và native method cần ăn khớp.
6. **Đúng thời điểm:** method chưa bị bind sai hoặc fail resolution trước khi prefix được đăng ký.
7. **Đúng class-file bytes:** class đã transform phải qua verifier và không phá module/classloader constraints.
8. **Đúng vòng đời:** prefix có hiệu lực cho những prefixed methods còn cần được resolve; không tắt sớm.
9. **Đúng thứ tự nhiều agent:** các prefix được áp dụng theo chuỗi biến đổi, có thể bị tương tác với transformer khác.
10. **Đúng chiến lược lỗi:** `UnsatisfiedLinkError` là một `LinkageError`, không phải `Exception`; `catch (Exception)` sẽ không bắt lỗi đó.

Dùng `javap -p -s -v` và công cụ native symbol (`nm`, `objdump`, `dumpbin`) để xem bytes và symbol thực tế trước khi kết luận rằng lỗi do capability.

## 14. Những ngộ nhận phổ biến

| Nhận định | Đúng/sai | Giải thích |
|---|---|---|
| “Manifest `true` là JVM chắc chắn hỗ trợ” | **Sai** | Capability còn phụ thuộc JVM |
| “Không cần `addTransformer`, có thể set prefix trước” | **Sai** | Transformer phải đã đăng ký |
| “`setNativeMethodPrefix` tự đổi tên các method trong class file” | **Sai** | Chỉ sửa resolution retry; class rewrite là việc khác |
| “Prefix hoạt động như một alias unconditional” | **Sai** | Chỉ được xét nếu resolution thông thường thất bại |
| “Native method có thân `Code` để chèn logging” | **Sai** | Cần Java wrapper không native |
| “Prefix null gây NullPointerException” | **Sai** | Prefix null/empty làm tắt prefix retry; transformer null mới là lỗi |
| “Có prefix thì không cần native library” | **Sai** | Library và native implementation phải tồn tại |
| “Bật prefix tự bật retransformation” | **Sai** | Capabilities độc lập |
| “Có thể thêm wrapper mới tùy ý khi retransform class đã tải” | **Sai** | Có giới hạn schema/JVMTI; thường wrap ở initial definition |
| “Một transformer phải dùng chung prefix với agent khác” | **Sai** | Mỗi transformer cần prefix riêng để tránh nhầm lớp wrapper |
| “Prefix chỉ ảnh hưởng automatic JNI symbol lookup” | **Sai** | API còn nêu `RegisterNatives` fallback |
| “Không có native C compiler vẫn kiểm tra được JNI fallback thực?” | **Không theo demo này** | Java-only probe chỉ kiểm tra capability; demo JNI cần một library có symbol thật |
| “Tắt prefix ngay sau khi class load là an toàn” | **Không bảo đảm** | Native resolution có thể thực hiện muộn hơn |
| “`-javaagent` đặt sau class main cũng như đặt trước?” | **Sai** | `-javaagent` là JVM option, cần đứng trước main class/`-jar` theo cú pháp launcher |

## 15. Checklist triển khai trong agent thật

1. **Chốt mục tiêu:** đo thời gian biên JNI hay thực sự cần quan sát bên trong native implementation? Prefix + Java wrapper chỉ bao lấy **biên gọi**.
2. **Yêu cầu capability** bằng manifest `Can-Set-Native-Method-Prefix: true`.
3. **Dùng đúng entrypoint** `premain` cho startup agent, hoặc `agentmain` khi môi trường hỗ trợ dynamic loading phù hợp.
4. **Kiểm tra `isNativeMethodPrefixSupported()`** trước khi quyết định tạo prefixed native methods.
5. **Đăng ký `ClassFileTransformer` trước**, giữ lại đúng instance.
6. **Gọi `setNativeMethodPrefix` với prefix duy nhất và ổn định**, trước khi transformed native methods được bind.
7. **Chỉ biến đổi class/method đúng mục tiêu**, đặc biệt với các class hệ thống hoặc JNI core có rủi ro ảnh hưởng toàn JVM.
8. **Ở lần định nghĩa class đầu**: tạo wrapper non-native và prefixed native method đúng tên/descriptor/modifiers, build bytes hợp lệ.
9. **Giữ semantic của method gốc**: return, exception, synchronization, native transitions, class loading và thread safety.
10. **Kiểm tra JNI resolution** với native library thật, cả automatic symbol lookup và `RegisterNatives` nếu sản phẩm cần hai đường.
11. **Thử đường capability OFF**: agent bỏ qua thay đổi không tương thích, ứng dụng vẫn chạy hoặc có thông báo rõ ràng.
12. **Thử nhiều prefix/agents**: tránh collision và double instrumentation; kiểm tra thứ tự chain.
13. **Không reset prefix sớm**: JVM có thể resolve native implementation muộn hơn thời điểm class được định nghĩa.
14. **Đo overhead và tính ổn định**: Java wrapper có chi phí, có thể làm ảnh hưởng JIT, class loading và timing.
15. **Kiểm tra trên JVM/OS production**: JNI binary format, JVM TI capability, class-file version và module boundaries phải tương thích.

## 16. Tự kiểm tra

1. **`native int add(int)` có `Code` để transformer thêm opcode vào giữa không?** Không.
2. **Muốn đo thời gian gọi native từ Java nên tạo gì?** Một Java wrapper method không native, gọi một native method đã đổi tên.
3. **`Can-Set-Native-Method-Prefix` mặc định thế nào?** `false`.
4. **Manifest `true` có buộc `isNativeMethodPrefixSupported()` trả `true`?** Không; còn phụ thuộc JVM.
5. **`setNativeMethodPrefix` tự tạo wrapper không?** Không; nó chỉ điều chỉnh native resolution fallback.
6. **Set prefix trước khi gọi `addTransformer` có hợp lệ không?** Không; ném `IllegalArgumentException`.
7. **`transformer == null` thì sao?** `NullPointerException`.
8. **`prefix == null` thì sao?** Tắt native resolution retry cho transformer ấy.
9. **JNI automatic lookup của prefixed native method thất bại thì JVM thử gì?** Xem xét loại bỏ prefix để tìm implementation tên gốc.
10. **Với JNI `RegisterNatives` đăng ký tên gốc, JVM có thể thử gì?** Thêm prefix để khớp prefixed native method trong class.
11. **Vì sao phần JNI demo dùng một C function mang tên `Java_demo_NativeTarget_add`?** Để kiểm tra rằng prefixed Java native method được link tới implementation **tên gốc** nhờ fallback.
12. **Manifest OFF của JNI demo tạo `UnsatisfiedLinkError` dù `.so` đã được nạp vì sao?** Không có prefix fallback; native method prefixed không có JNI symbol tương ứng.
13. **Thí nghiệm JNI có thực hiện classfile transformation không?** Không. Source đã chứa wrapper/prefixed native method; transformer cố ý no-op để cô lập resolution.
14. **Bật native prefix có cho phép tùy ý thêm method khi retransform một class đã tải?** Không; giới hạn JVM TI/class schema vẫn áp dụng.
15. **Vì sao nhiều transformer nên dùng prefix riêng?** Để JVM tìm đúng các lớp wrapper nối tiếp, tránh tên trùng và resolver nhầm.
16. **Vì sao không tắt prefix ngay sau khi class load?** JNI binding có thể bị trì hoãn đến lần gọi sau.
17. **Prefix có giúp liên kết nếu `.dll/.so` không tồn tại?** Không; thư viện và native function vẫn phải có.
18. **Muốn xử lý native binding từ phía JVM TI native agent thì có cơ chế nào khác?** `NativeMethodBind` event, khác với Java wrapper prefix.

### Tài liệu chính thức

- [Java SE 21 — `Instrumentation`: `isNativeMethodPrefixSupported` và `setNativeMethodPrefix`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): điều kiện capability, registration, hai kiểu JNI resolution fallback, nhiều prefix và ngoại lệ.
- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent manifest và `Can-Set-Native-Method-Prefix`.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback biến đổi bytecode và thứ tự transformer.
- [Java SE 21 — JVM Tool Interface: Set Native Method Prefix / Prefixes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): capability `can_set_native_method_prefix`, automatic resolution, `RegisterNatives`, nhiều lớp wrapper và lifetime.
- [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): JNI name mangling, native method lookup và libraries.
- [JNI Specification — Functions: `RegisterNatives`](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): explicit JNI method registration.
- [Java Virtual Machine Specification, §4.6 Methods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.6): method flags và `Code` attribute.

**Kết luận:** `Can-Set-Native-Method-Prefix` là **yêu cầu của agent**, `isNativeMethodPrefixSupported()` là **phép xác nhận capability**, `ClassFileTransformer` là **nơi tạo Java wrapper/prefixed native method**, còn `setNativeMethodPrefix` giúp JVM **tìm lại JNI implementation mang tên gốc khi native resolution thông thường thất bại**. Phân biệt bốn vai trò này sẽ tránh được phần lớn lỗi liên kết native trong Java instrumentation.