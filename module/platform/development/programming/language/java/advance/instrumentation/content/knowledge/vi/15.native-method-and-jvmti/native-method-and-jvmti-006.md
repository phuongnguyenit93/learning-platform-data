# Java agent khác với thư viện agent native dùng -agentlib hoặc -agentpath

**Chủ đề:** Java Advance → instrumentation → **Native và JVM TI**.

Các công cụ profiling, debugging, tracing và bytecode instrumentation thường khai báo agent khi khởi động JVM. Có ba tùy chọn rất dễ bị nhầm:

- **`-javaagent:/path/to/agent.jar[=options]`**: nạp **Java agent JAR**, dựa vào `Premain-Class` trong manifest và `public static void premain(...)`. Đường Java chuẩn để can thiệp bytecode là `java.lang.instrument.Instrumentation`.
- **`-agentlib:agentname[=options]`**: nạp **native agent shared library** theo tên thư viện và cơ chế native library search của hệ điều hành/JVM, rồi gọi exported `Agent_OnLoad`. Native agent có thể dùng **JVMTI** và **JNI**.
- **`-agentpath:/absolute/path/libagent.so[=options]`**: cũng nạp **native shared library**, nhưng chỉ định tệp theo đường dẫn cụ thể thay vì tên ngắn.

**Không thể tráo ba tùy chọn cho cùng một file.** JAR Java agent không tự biến thành `.so`/`.dll`; một thư viện native không có manifest `Premain-Class` và JVM không gọi `premain` từ thư viện ấy. Điểm khác giữa `-agentlib` và `-agentpath` chủ yếu là **cách định vị tệp native**, không phải một cặp API JVMTI khác nhau.

Bài này giải thích sự khác biệt về **điểm vào, lifecycle, API, capabilities, packaging, ABI, load rules, concurrency, bảo mật và lỗi thường gặp**. Sau đó là hai lab Java 17+ và native C độc lập, có mã nguồn đầy đủ, lệnh build, stdout dự kiến và cách kiểm chứng.

> **Phạm vi môi trường:** Lab Java chạy trên JDK 17+; lab JVMTI C yêu cầu JDK headers và C compiler, hướng dẫn chính dùng GCC/Linux. Thư viện native phải được biên dịch riêng cho OS, kiến trúc CPU, runtime library và ABI phù hợp. Tất cả ví dụ sử dụng **startup agent**, không yêu cầu attach động.

## 1. Bảng phân biệt nền tảng

| Hạng mục | Java agent `-javaagent` | Native `-agentlib` / `-agentpath` |
| --- | --- | --- |
| File triển khai | JAR có `.class` và manifest | Native library: `.so`, `.dylib` hoặc `.dll` |
| Entry point lúc JVM start | `premain(String, Instrumentation)` hoặc `premain(String)` | `Agent_OnLoad(JavaVM*, char*, void*)` |
| API chủ yếu | `java.lang.instrument.Instrumentation`, `ClassFileTransformer` | `jvmtiEnv*`, `jvmtiEventCallbacks`, JNI |
| Cách nạp | JVM đọc agent JAR và manifest | JVM/OS loader tải binary, resolve exported C symbol |
| Tương thích nền tảng | JAR bytecode có thể dùng đa OS nếu JDK/JVM và dependencies phù hợp | Phải build và test theo OS/CPU/ABI/libc |
| Khả năng thao tác class | Transformer, redefine/retransform nếu VM hỗ trợ | `ClassFileLoadHook`, JVMTI events/capabilities nếu VM hỗ trợ |
| Độ an toàn bộ nhớ | Java memory model và GC, vẫn có thể gây lỗi instrumentation | Native pointers/memory; một bug có thể crash cả process |
| Cấu hình | Agent JAR manifest và chuỗi `options` | Exported functions, native dependencies, chuỗi `options` |
| Tải sau startup | `Agent-Class` và `agentmain`, khi attach được phép | `Agent_OnAttach`, khi native attach được phép |
| Các lỗi thường gặp | Sai JAR, thiếu manifest, sai `premain`, thiếu class | Không tìm thấy library, symbol missing, wrong architecture, JVMTI error |

### 1.1. Cả hai đều có thể cùng hiện diện

Một JVM có thể chạy cả Java agent và JVMTI agent. Việc chọn `-javaagent` không loại trừ việc chương trình dùng JNI; một native JVMTI agent cũng có thể tương tác với Java objects khi phase/API cho phép. Nhưng **giao thức JVM khởi động agent** vẫn khác nhau. Khi hai agents cùng biến đổi một class, phải xem pipeline, thứ tự callback, tính hợp lệ của class file và khả năng trùng instrumentation.

## 2. Luồng khởi động Java agent: JAR → manifest → `premain`

Lệnh mẫu:

```bash
java -javaagent:java-agent.jar=demo -cp out lab.App
```

Luồng:

```text
Khởi động JVM
    │
    ├── đọc META-INF/MANIFEST.MF trong java-agent.jar
    │      Premain-Class: lab.JavaAgent
    │
    ├── nạp class lab.JavaAgent
    ├── gọi premain(agentArgs, Instrumentation)
    │      └── có thể addTransformer(...)
    │
    └── gọi main(...) của lab.App
```

Javadoc `java.lang.instrument` cho phép hai chữ ký Java:

```java
public static void premain(
        String agentArgs, Instrumentation instrumentation);

public static void premain(String agentArgs);
```

Đây là **chữ ký API minh họa**, không phải file nguồn Java có thể biên dịch độc lập. JVM ưu tiên overload nhận `Instrumentation`. Với startup `-javaagent`, JVM gọi `premain` trước `main`. Nếu agent không khởi động được hoặc `premain` ném lỗi chưa bắt, JVM có thể **dừng trước khi chạy ứng dụng**.

Manifest Java agent phổ biến:

| Entry | Dùng khi nào? |
| --- | --- |
| `Premain-Class` | **Bắt buộc** cho startup `-javaagent` |
| `Agent-Class` | Cho dynamic loading Java agent sau startup nếu implementation hỗ trợ |
| `Can-Redefine-Classes` | Agent yêu cầu capability redefine, mặc định `false` |
| `Can-Retransform-Classes` | Agent yêu cầu capability retransform, mặc định `false` |
| `Can-Set-Native-Method-Prefix` | Yêu cầu native method prefix capability |
| `Boot-Class-Path` | Bổ sung đường tìm class cho bootstrap loader theo spec |

**Cờ manifest không phải phép bảo đảm cấp quyền.** Khi cần redefine/retransform, vẫn gọi `Instrumentation.isRedefineClassesSupported()` / `isRetransformClassesSupported()` và kiểm tra `isModifiableClass(clazz)`.

### 2.1. Java `Instrumentation` làm gì?

Một Java agent có thể:

- Đăng ký `ClassFileTransformer` qua `addTransformer(transformer)`, hoặc `addTransformer(transformer,true)` nếu cần retransform và JVM hỗ trợ.
- Quan sát `getAllLoadedClasses()` / `getInitiatedClasses(loader)`.
- Yêu cầu `retransformClasses(...)` hoặc `redefineClasses(...)` trong giới hạn schema/capability.
- Truy vấn `isModifiableClass`, khả năng thay đổi module, append JAR vào class-loader search.
- Đọc `classfileBuffer` trong callback. Nếu không biến đổi, **trả `null`**; nếu biến đổi, **trả mảng `byte[]` mới** chứa class file hợp lệ. **Không sửa tại chỗ mảng JVM cung cấp**.

Thông thường không cần dùng native pointer hay viết C chỉ để chặn/load một số classes Java. Tuy nhiên Java agent vẫn có rủi ro do recursive class loading, logger deadlocks, code chưa verify hoặc bytecode sai.

## 3. Native JVMTI agent: binary → `Agent_OnLoad` → callback

Tùy chọn ví dụ:

```bash
java -agentpath:/opt/agents/libnativeprobe.so=demo -cp out lab.App
```

JVM tải shared library vào **cùng process**, sau đó tìm exported symbol `Agent_OnLoad`. Chữ ký C:

```c
JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM *vm, char *options, void *reserved);
```

Đây là **fragment C**, yêu cầu các headers `jni.h` và `jvmti.h`. `options` chứa chuỗi sau dấu `=`; `reserved` không dùng ở bài lab. Agent khởi tạo thành công thường trả `JNI_OK`; nếu không, trả mã lỗi phù hợp, và JVM có thể không vào `main`.

Các entry points khác:

```c
JNIEXPORT jint JNICALL Agent_OnAttach(
        JavaVM *vm, char *options, void *reserved);

JNIEXPORT void JNICALL Agent_OnUnload(JavaVM *vm);
```

- `Agent_OnAttach` dành cho nạp agent native **vào JVM đang chạy** nếu VM/policy cho phép.
- `Agent_OnUnload` được gọi khi agent sắp được unload theo lifecycle, thích hợp dọn resource.
- Không lấy `Agent_OnAttach` làm callback mặc định của lệnh `-agentpath` lúc startup.
- Các entry points không thay thế Java `premain`/`agentmain`.

### 3.1. `JavaVM*`, `JNIEnv*` và `jvmtiEnv*`

| Kiểu native | Mục đích |
| --- | --- |
| `JavaVM*` | Handle giao diện invocation JVM, được JVM truyền vào agent C |
| `JNIEnv*` | Giao diện JNI của **thread hiện tại** để tương tác Java objects/classes |
| `jvmtiEnv*` | Giao diện JVMTI để lấy capabilities, đăng ký events, truy vấn VM |
| `jvmtiError` | Mã kết quả hàm JVMTI, `JVMTI_ERROR_NONE` nghĩa thành công |
| `jvmtiCapabilities` | Tập capabilities agent có thể yêu cầu cấp thêm |
| `jvmtiEventCallbacks` | Struct chứa function pointers cho các sự kiện JVMTI |

Lấy `jvmtiEnv*` từ `JavaVM*` qua `GetEnv`:

```c
// Fragment: trong Agent_OnLoad, với JavaVM *vm đã có.
jvmtiEnv *jvmti = NULL;
jint status = (*vm)->GetEnv(
        vm, (void **)&jvmti, JVMTI_VERSION_1_2);
if (status != JNI_OK || jvmti == NULL) {
    return JNI_ERR;
}
```

Lấy được environment **không cấp mọi capability**. Nhiều JVMTI events/functions phụ thuộc **VM phase** (OnLoad, Start, Live...) và quyền `AddCapabilities`. API native có nhiều mã lỗi; bỏ qua return code rồi dereference pointer có thể làm process crash.

### 3.2. Những tính năng ở tầng JVMTI

Các ví dụ:

- `VMInit`, `VMDeath`: báo giai đoạn JVM sẵn sàng/kết thúc.
- `ClassFileLoadHook` và `ClassPrepare`: thấy class-file bytes và class preparation.
- `ThreadStart`/`ThreadEnd`: sự kiện thread.
- `MethodEntry`/`MethodExit`, `Exception`: chẩn đoán ở mức lời gọi/ngoại lệ.
- `GetLoadedClasses`/`GetClassSignature`: khảo sát runtime types.
- Một số heap/gc/object tagging và callback: cần capability riêng.

**Không mặc định mọi event đã bật** chỉ bởi `Agent_OnLoad` chạy. Agent phải đăng ký callback và bật notification mode; nhiều event còn cần xin `jvmtiCapabilities`. Các native callbacks trong đường nóng có thể làm tăng latency rất lớn, nên phải lọc/chọn mục tiêu phù hợp.

## 4. `-agentlib` và `-agentpath` khác nhau ở cách tìm tệp

Cú pháp của Java launcher:

```text
-agentlib:<libname>[=<options>]
-agentpath:<pathname>[=<options>]
```

**`-agentlib:foo`**: JVM tìm native library theo tên ngắn và quy tắc platform. Trên Linux thường là `libfoo.so`, trên Windows là `foo.dll`. Library search path/dependencies phải cho phép nạp, chẳng hạn `LD_LIBRARY_PATH` trên Linux hoặc `PATH` trên Windows. Java `-cp` chỉ định nơi tìm Java classes/JARs, **không** tự giải quyết native library search.

**`-agentpath:/full/path/libfoo.so`**: JVM dùng đường dẫn tuyệt đối tới đúng binary file. Cách này hữu ích để khoanh vùng lỗi search path hoặc dùng nhiều bản library ở các vị trí khác nhau. Nhưng file vẫn phải đúng architecture/ABI và dependencies.

| OS | Native file thường gặp | Build/kiểm tra |
| --- | --- | --- |
| Linux | `libfoo.so` | GCC/Clang `-fPIC -shared`, `ldd`, `file` |
| macOS | `libfoo.dylib` hoặc tên theo quy ước VM | Clang `-dynamiclib`, kiến trúc/codesigning |
| Windows | `foo.dll` | MSVC/MinGW, `dumpbin /EXPORTS`, `PATH` |

**Quan trọng:** `-agentlib` và `-agentpath` **không đòi source code C khác nhau**; cả hai có thể tải **chính một binary native agent**. Sự khác nhau là tên thư viện/đường dẫn và OS loader configuration.

## 5. Lab Java 17+: agent JAR quan sát class load

Cấu trúc:

```text
two-agent-types/
├── java-agent.mf
├── src/lab/
│   ├── JavaAgent.java
│   ├── App.java
│   └── Sample.java
├── nativeprobe.c
└── out/                (tạo khi biên dịch)
```

Lab Java không dùng dependency bên ngoài; agent chỉ nhìn đúng lớp `lab/Sample` và **không biến đổi class**.

### 5.1. `src/lab/JavaAgent.java`

```java
package lab;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class JavaAgent {
    private JavaAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("JAVA_PREMAIN=" + options);
        inst.addTransformer(new Observer());
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if ("lab/Sample".equals(className)) {
                System.out.println("JAVA_SEES=lab/Sample");
            }
            return null;
        }
    }
}
```

Override `transform` năm tham số là hợp lệ ở Java 17; từ JDK 9+ còn có overload sáu tham số với `Module`. Java agent này chỉ nhận callback rồi trả `null` để JVM dùng bytes không đổi. Không ghi lên `classfileBuffer` và không giữ reference mảng đó.

Trong production, `System.out.println` trong transformer trên mọi class là ý tưởng không tốt vì có thể gây reentrant loading, I/O latency và log storm. Bài lab cố ý filter một tên class.

### 5.2. `src/lab/Sample.java`

```java
package lab;

public final class Sample {
    private Sample() {}

    public static String message() {
        return "ok";
    }
}
```

### 5.3. `src/lab/App.java`

```java
package lab;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("APP_MAIN");
        Class<?> type = Class.forName(
                "lab.Sample", true, App.class.getClassLoader());
        Object result = type.getDeclaredMethod("message").invoke(null);
        System.out.println("SAMPLE=" + result);
    }
}
```

Lớp được chỉ bằng **string** `"lab.Sample"`, không có tham chiếu trực tiếp kiểu `Sample.class` trong `App`. Vì thế lệnh `Class.forName` sau dòng `APP_MAIN` tạo điểm load mục tiêu dễ quan sát.

### 5.4. `java-agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: lab.JavaAgent
```

Đặt newline kết thúc tệp manifest. Lab không cần `Agent-Class` vì không load động; cũng không cần `Can-Redefine-Classes`/`Can-Retransform-Classes` vì không sửa class đang load.

### 5.5. Build và chạy

Trên Linux/macOS Bash:

```bash
mkdir -p out
javac --release 17 -d out \
    src/lab/JavaAgent.java src/lab/App.java src/lab/Sample.java
jar --create --file java-agent.jar --manifest java-agent.mf -C out .
java -javaagent:java-agent.jar=demo -cp out lab.App
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out src/lab/JavaAgent.java src/lab/App.java src/lab/Sample.java
jar --create --file java-agent.jar --manifest java-agent.mf -C out .
java -javaagent:java-agent.jar=demo -cp out lab.App
```

**Stdout ứng dụng và agent dự kiến** với một JVM khởi động sạch, không có công cụ khác tải `lab.Sample` trước đó:

```text
JAVA_PREMAIN=demo
APP_MAIN
JAVA_SEES=lab/Sample
SAMPLE=ok
```

Phân tích: `JAVA_PREMAIN` do JVM gọi entry point Java trong JAR; `JAVA_SEES` do callback `ClassFileTransformer`; `APP_MAIN`/`SAMPLE` do ứng dụng. Method `Sample.message()` vẫn trả `ok` nên agent **không đổi behavior**.

Chạy không agent:

```bash
java -cp out lab.App
```

Stdout:

```text
APP_MAIN
SAMPLE=ok
```

Điều này xác nhận Java application có thể tự chạy, còn hai dòng bổ sung do JVM khởi động Java agent.

## 6. Lab native JVMTI C: `Agent_OnLoad` và `VMInit`

Dùng cùng `lab.App` và `lab.Sample` ở phần 5, nhưng thay `-javaagent` bằng native shared library. Ta đăng ký callback `VMInit` để chứng minh **JVM TI agent** đã được nạp; ví dụ không biến đổi bytecode.

### 6.1. Tạo `nativeprobe.c`

```c
#include <jni.h>
#include <jvmti.h>
#include <stdio.h>
#include <string.h>

static void JNICALL on_vm_init(
        jvmtiEnv *jvmti,
        JNIEnv *jni,
        jthread thread) {

    (void)jvmti;
    (void)jni;
    (void)thread;

    puts("NATIVE_VM_INIT");
    fflush(stdout);
}

JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM *vm, char *options, void *reserved) {

    (void)reserved;
    jvmtiEnv *jvmti = NULL;

    jint status = (*vm)->GetEnv(
            vm, (void **)&jvmti, JVMTI_VERSION_1_2);
    if (status != JNI_OK || jvmti == NULL) {
        fputs("JVMTI_GET_ENV_FAILED\n", stderr);
        return JNI_ERR;
    }

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.VMInit = &on_vm_init;

    jvmtiError error = (*jvmti)->SetEventCallbacks(
            jvmti, &callbacks, (jint)sizeof(callbacks));
    if (error != JVMTI_ERROR_NONE) {
        fputs("SET_CALLBACKS_FAILED\n", stderr);
        return JNI_ERR;
    }

    error = (*jvmti)->SetEventNotificationMode(
            jvmti, JVMTI_ENABLE, JVMTI_EVENT_VM_INIT, NULL);
    if (error != JVMTI_ERROR_NONE) {
        fputs("ENABLE_VM_INIT_FAILED\n", stderr);
        return JNI_ERR;
    }

    printf("NATIVE_ON_LOAD=%s\n", options == NULL ? "" : options);
    fflush(stdout);
    return JNI_OK;
}

JNIEXPORT void JNICALL Agent_OnUnload(JavaVM *vm) {
    (void)vm;
    puts("NATIVE_ON_UNLOAD");
    fflush(stdout);
}
```

Các chi tiết cần hiểu:

- `jni.h` định nghĩa `JavaVM` và calling convention; `jvmti.h` cung cấp `jvmtiEnv`, `jvmtiError`, các events/capability definitions.
- JVM gọi `Agent_OnLoad` khi tải library theo agent startup option.
- `GetEnv` yêu cầu JVMTI version mà JVM hỗ trợ; ví dụ dùng `JVMTI_VERSION_1_2`.
- `memset` xóa struct callbacks trước khi gán `VMInit`, tránh con trỏ rác.
- `SetEventCallbacks` đăng ký hàm nhận event. `SetEventNotificationMode` **bật** sự kiện. Chỉ đăng ký thôi không đủ.
- Cả ba thao tác `GetEnv`, `SetEventCallbacks` và bật event phải kiểm tra lỗi.
- `NATIVE_ON_LOAD=demo` chứng minh options được truyền từ native launcher; `NATIVE_VM_INIT` là callback lúc VM initialization.
- `Agent_OnUnload` dọn tài nguyên khi library sắp unload; lab không dùng heap/native global reference riêng.

**Đây là source C hoàn chỉnh cho agent startup**, không phải JNI library chỉ chứa `JNI_OnLoad`. Việc có `Agent_OnLoad` không đồng nghĩa tự động được cấp mọi capability JVMTI. Vì chỉ bật `VMInit`, lab không cần xin capability của `MethodEntry` hay `ClassFileLoadHook`.

### 6.2. Build Linux bằng GCC

Cần đặt `JAVA_HOME` trỏ tới **JDK 17+** và cài GCC. Kiểm tra headers:

```bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
test -f "$JAVA_HOME/include/jvmti.h"
test -f "$JAVA_HOME/include/jni.h"
```

Biên dịch:

```bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -o libnativeprobe.so nativeprobe.c
```

`-fPIC -shared` tạo Linux shared library, còn `-I` đưa JDK/JNI headers vào build. `JAVA_HOME` không hợp lệ hoặc JDK không có headers sẽ làm compile fail; không sửa bằng cách tải một file `jni.h` ngẫu nhiên không khớp JDK.

### 6.3. Chạy native agent bằng `-agentpath`

```bash
java "-agentpath:$(pwd)/libnativeprobe.so=demo" -cp out lab.App
```

Trên HotSpot Linux có JVMTI và chương trình kết thúc bình thường, stdout **dự kiến**:

```text
NATIVE_ON_LOAD=demo
NATIVE_VM_INIT
APP_MAIN
SAMPLE=ok
NATIVE_ON_UNLOAD
```

Thứ tự minh họa: native `Agent_OnLoad` chạy khi tải agent; `VMInit` diễn ra khi JVM chuẩn bị thực thi Java application; `APP_MAIN`/`SAMPLE` là Java app; `Agent_OnUnload` phục vụ shutdown/cleanup. Trong trường hợp process bị kill, JVM chết trước khi cleanup, stdout bị đóng hay startup fail, có thể thiếu dòng `NATIVE_ON_UNLOAD`; không coi log cuối là bảo đảm tuyệt đối tài nguyên đã được thu hồi.

### 6.4. Chạy bằng `-agentlib` với cùng binary

Trên Linux Bash, đưa current directory vào native search path rồi gọi theo tên ngắn:

```bash
LD_LIBRARY_PATH="$PWD:$LD_LIBRARY_PATH" \
    java -agentlib:nativeprobe=demo -cp out lab.App
```

Ở đây JVM cần tìm được **`libnativeprobe.so`**; tùy cấu hình distro/VM, đường tìm/thư viện phụ thuộc có thể khác. Nếu library đã build nhưng option `-agentlib` báo không tìm thấy, hãy thử `-agentpath` tuyệt đối và kiểm tra `ldd libnativeprobe.so`, kiến trúc bằng `file libnativeprobe.so`, rồi chẩn đoán search path.

Với cùng thư viện và `options=demo`, mã native chạy giống thí nghiệm `-agentpath`. **Không có hai kiểu `Agent_OnLoad` riêng cho hai option.**

### 6.5. macOS và Windows

Trên macOS có Clang và JDK hỗ trợ JVMTI:

```bash
clang -std=c11 -Wall -Wextra -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -o libnativeprobe.dylib nativeprobe.c
java "-agentpath:$(pwd)/libnativeprobe.dylib=demo" -cp out lab.App
```

Trên Windows x64, chạy trong **Developer Command Prompt** có MSVC `cl` và JDK cùng kiến trúc:

```bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativeprobe.c /link /OUT:nativeprobe.dll
java -agentpath:"%CD%\nativeprobe.dll"=demo -cp out lab.App
```

Các lệnh native phụ thuộc toolchain, kiến trúc và OS loader. Tệp `.dll` không chạy được trực tiếp như `.so` trên Linux. Khi có nghi vấn cách native library được đặt tên trên macOS, dùng **`-agentpath` chỉ rõ file thực tế** và đọc lỗi OS loader.

## 7. Vì sao đây là hai cơ chế instrumentation khác nhau?

Cả Java Instrumentation và JVMTI đều có thể cung cấp đường thay đổi class, nhưng cách biểu diễn callback/output khác:

| Vấn đề | Java agent | JVMTI native agent |
| --- | --- | --- |
| Callback nhận bytes | `ClassFileTransformer.transform(...)` | `ClassFileLoadHook` |
| Giao diện callback | Java, mảng `byte[] classfileBuffer` | Native C, con trỏ bytes và vùng output |
| Không thay class | `return null` | Giữ `new_class_data`/`len` theo hợp đồng hook |
| Thay class | Trả **mảng `byte[]` mới hợp lệ**, không mutate input | Cấp output buffer theo JVMTI allocator và hợp đồng pointer |
| Nguồn loaded classes | `Instrumentation.getAllLoadedClasses()` | JVMTI `GetLoadedClasses` |
| Đổi definitions | `retransformClasses`/`redefineClasses` theo khả năng VM | JVMTI `RetransformClasses`/`RedefineClasses` theo capability/phase |
| Event method entry/exit | Thường chèn bytecode hook của chính agent | JVMTI `MethodEntry`/`MethodExit` events khi bật và có capability |
| Thao tác runtime state | Java object references/reflection | JNI/JVMTI types, JNI refs, native memory rules |

Hai đường có thể xuất hiện trong cùng class-load pipeline nhưng không nên suy luận rằng thứ tự log của hai agents chính là thứ tự biến đổi đã được JVM đặc tả. Khi cùng instrument, phải theo dõi transformer groups, output format và idempotency.

### 7.1. Lỗi vi phạm ownership

Java `ClassFileTransformer` **không được sửa trực tiếp `classfileBuffer`**. Nếu không thay đổi, trả `null`; nếu có thay đổi, trả một mảng mới chứa class file hợp lệ.

Ở `ClassFileLoadHook` native, khi xuất class file khác, JVMTI yêu cầu dùng quy tắc output pointers/size và bộ cấp phát tương ứng. Không trỏ `new_class_data` vào một buffer stack local đã hết vòng đời, không tự `free` vùng do JVMTI quản lý bằng allocator không đúng, và không bỏ qua các constraints của `new_class_data_len`/class format.

**Không** dùng Java byte arrays hoặc native pointers như chỗ lưu shared mutable state giữa callbacks nếu chưa thiết kế thread safety và ownership.

## 8. JVMTI phases, capabilities và event lifecycle

Một native agent hoàn chỉnh hơn thường làm:

```text
Agent_OnLoad
  -> GetEnv(JVMTI_VERSION_...)
  -> GetPotentialCapabilities / AddCapabilities nếu cần
  -> SetEventCallbacks
  -> SetEventNotificationMode
  -> return JNI_OK

JVM bắt đầu hoạt động:
  -> events đến ở đúng phase
  -> xử lý callback có kiểm soát (không block nặng)
  -> kiểm tra return codes, đồng bộ state

Agent_OnUnload
  -> cleanup native memory, monitors, references...
```

Đây là **sơ đồ thiết kế**, không phải lời hứa mọi callback có cùng phase và capability. `VMInit` trong lab đơn giản hơn rất nhiều so với `ClassFileLoadHook` hay `MethodEntry`. Các công cụ profiler ở mức mọi method entry/exit có thể tốn tài nguyên đáng kể và thay đổi latency ứng dụng.

### 8.1. `JNIEnv*` gắn với thread

`JNIEnv*` lấy ở callback không thể lưu global rồi dùng trên mọi native worker thread. Worker thread tự tạo phải được attach với JVM bằng invocation APIs phù hợp trước khi gọi JNI và detach đúng lifecycle. Native code có thể gọi vào Java runtime khi phase/threads chưa sẵn sàng, gây deadlock/crash; chỉ gọi khi documented contract cho phép.

### 8.2. Cấp phát bộ nhớ đúng allocator

Các JVMTI API có thể cấp phát buffers cần giải phóng qua `jvmti->Deallocate`. Không tự `free` nếu bộ nhớ đến từ allocator của JVMTI. Tương tự, không giữ callback-local references sau khi chúng hết lifetime. Các `jobject` global references nếu được tạo phải dọn bằng JNI tương ứng khi lifecycle phù hợp.

### 8.3. Phân tách lỗi Java và lỗi native

Lỗi Java agent có thể dẫn tới `ClassFormatError`, `VerifyError`, exception trong `premain` hoặc vấn đề module/dependency. Lỗi C có thể gây segmentation fault, invalid pointer, corrupted heap hoặc JVM crash. Native shared library chạy **cùng quyền OS của process Java**, không phải một sandbox độc lập.

## 9. Startup agent khác dynamic attach

| Giai đoạn | Java agent | JVMTI native agent |
| --- | --- | --- |
| JVM startup | `-javaagent:agent.jar` → `premain` | `-agentlib:name` / `-agentpath:path` → `Agent_OnLoad` |
| Sau startup (nếu được hỗ trợ) | JAR có `Agent-Class` → `agentmain` | Native library có `Agent_OnAttach` |
| Tùy chọn mẫu từ Attach API | `VirtualMachine.loadAgent(jar, opts)` | `loadAgentLibrary` / `loadAgentPath` |
| Hạn chế | JDK/runtime policy, OS rights, attach availability | Tương tự, cộng native ABI |
| Có tự attach vì dùng startup option? | Không | Không |

Với Java Attach API, một fragment:

```java
// Fragment: cần module jdk.attach, import VirtualMachine;
// targetPid và jarPath là String đã được kiểm tra.
VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    vm.loadAgent(jarPath, "demo");
} finally {
    vm.detach();
}
```

Đây không phải source độc lập. `loadAgent` chủ yếu cho **Java agent JAR**; thư viện JVMTI native có `loadAgentPath`/`loadAgentLibrary` trên những implementation hỗ trợ. Đưa `.so` vào `loadAgent` không tương đương `-agentpath`.

**JEP 451 từ JDK 21:** dynamic agent loading tạo cảnh báo và hướng tới policy chặt hơn. Ví dụ trên HotSpot JDK 21, `-XX:+EnableDynamicAgentLoading` là opt-in và `-XX:-EnableDynamicAgentLoading` từ chối nạp động; hành vi mặc định ở những phiên bản/vendor mới cần xác minh thực tế. Startup agent đã khai báo trên command line không đồng nghĩa một nỗ lực attach vào JVM đang chạy.

## 10. `Agent_OnLoad` không phải `JNI_OnLoad`

Đây là một nhầm lẫn quan trọng.

```java
System.loadLibrary("nativeprobe");
```

Dòng Java **fragment** trên đi qua **JNI library loading**, có thể gọi `JNI_OnLoad` nếu library cung cấp. Nó **không tự thay thế** `-agentlib:nativeprobe` của JVMTI.

- `Agent_OnLoad`: JVM native-agent startup entry point.
- `Agent_OnAttach`: native-agent dynamic attach entry point.
- `JNI_OnLoad`: JNI library load entry point.
- `premain`: Java-agent startup entry point.
- `agentmain`: Java-agent dynamic-load entry point.

Một binary có thể export nhiều entry points nếu được tác giả thiết kế, nhưng điều đó không cho phép sử dụng sai loader và cho rằng mọi callback sẽ được gọi.

## 11. Ví dụ thật: JDWP debugger là một native agent

`-agentlib:jdwp` nạp implementation Java Debug Wire Protocol (JDWP) dùng JVMTI/JNI. Ví dụ JDK 17:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 \
    -cp out lab.App
```

- `dt_socket` là transport TCP.
- `server=y` lắng nghe debugger.
- `suspend=n` không dừng trước `main`.
- `127.0.0.1:5005` ràng buộc loopback.

**Bảo mật:** Debugger có khả năng truy cập trạng thái JVM mạnh. Không bind `*:5005` ra internet nếu chưa có firewall/network isolation và phê duyệt. `lab.App` kết thúc rất nhanh nên debugger có thể chưa kịp kết nối; lệnh này chỉ nhằm chỉ rõ `-agentlib` có sử dụng thực tế.

## 12. Chọn cơ chế nào trong dự án?

### Ưu tiên Java agent khi

- Mục tiêu là bytecode-level tracing, metrics, test instrumentation hoặc thay method implementation trong khuôn khổ Java API.
- Muốn triển khai JAR qua nhiều OS mà không build native binary riêng.
- Cần `ClassFileTransformer`, `getAllLoadedClasses`, redefine/retransform và Java tooling.
- Muốn tránh trực tiếp xử lý ABI, pointers, native memory và thread-local JNI.
- Có sẵn nền tảng Java agent phù hợp và không cần VM-level events chỉ JVMTI cung cấp.

### Ưu tiên JVMTI native khi

- Mục tiêu yêu cầu các VM-level events/capabilities như class/method/thread/heap inspection chi tiết.
- Cần kết hợp profiler/debugger C/C++ hoặc tương tác thấp tầng với VM.
- Có chuyên môn JVMTI, phase/capability handling và C/C++ concurrency.
- Có pipeline build/test native matrix cho Linux/macOS/Windows, architectures, libc/ABI và JDK vendor.
- Chấp nhận yêu cầu kiểm soát memory safety, native dependencies, crash dump và security.

### Khi nào cần cùng lúc cả hai?

Có thể dùng Java transformer và native JVMTI agent trong cùng process, nhưng phải xem **thứ tự pipeline, target scope, callback recursion, overhead** và khả năng conflict. Nếu một agent đã chèn hook rồi agent khác chèn tiếp, hai output phải tạo class file hợp lệ; không dùng file hash/console log thay cho verifier và behavior tests.

## 13. Vận hành trong container và môi trường production

| Tiêu chí | Java agent JAR | Native agent |
| --- | --- | --- |
| Artifact | `.jar` | `.so`/`.dylib`/`.dll` + các dependencies |
| Search path | Đường file JAR | Native loader search path hoặc đường `-agentpath` |
| OS/CPU | JAR thường portable trong JDK tương thích | Đúng OS, CPU, ABI, libc/glibc/musl |
| Startup | `-javaagent` | `-agentlib`/`-agentpath` |
| Class bytecode | `Instrumentation` | JVMTI hook/capability |
| Lỗi build | Jar manifest/source/Java bytecode | C ABI/toolchain/JDK headers/shared library |
| Memory safety | Quản lý Java GC; vẫn có nguy cơ instrumentation error | Native code có thể làm process crash |
| Bảo mật | Có quyền quan sát/thay class Java | Có quyền của process và truy cập native memory |
| Container | Copy/mount JAR + JDK runtime | Copy/mount native binary + đúng dependencies/runtime |

Native agent build bằng glibc phiên bản mới có thể không chạy trên distro glibc cũ; tệp build cho x86-64 không chạy như x86-64 trên ARM64. Với Alpine/musl cần kiểm tra toolchain/loader phù hợp; đừng cho rằng `.so` build ở bất kỳ container nào đều portable.

**Kiểm soát quyền:** hai loại agent đều là code tin cậy chạy cùng JVM. Kiểm tra origin, checksum/signature, access tới đường artifact và giới hạn ai được thay file agent trước startup. Với native agent, quyền ghi library ở path startup có thể biến thành thực thi mã C không kiểm soát trong process.

### 13.1. Checklist triển khai

- [ ] Chỉ định rõ agent JAR hay native library và command-line option tương ứng.
- [ ] Pin artifact version và JDK/vendor version đã thử.
- [ ] Kiểm tra dependencies native bằng `ldd`/`otool`/`dumpbin` hoặc công cụ phù hợp.
- [ ] Kiểm tra startup entry point và error codes trước khi bật tracing nặng.
- [ ] Không mở debug port ra network không tin cậy.
- [ ] Có đường rollback/restart nếu startup agent fail.
- [ ] Giới hạn log và sampling để không tạo bottleneck.
- [ ] Native cleanup đúng allocator/phase; Java caches không giữ ClassLoader vô hạn.
- [ ] Các JVM flags/Attach policies phải được xác minh theo phiên bản, không sao chép cứng cấu hình cũ.

## 14. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng chẩn đoán |
| --- | --- | --- |
| Thiếu `Premain-Class` | JAR không có manifest agent đúng | `jar tf`, đọc `META-INF/MANIFEST.MF` |
| Java agent fail trước `main` | `premain` throw, sai class/dependency | Đọc stderr JVM, kiểm tra JAR/classpath |
| `NoClassDefFoundError` khi Java agent chạy | Dependency thiếu hoặc module/class visibility sai | Kiểm tra JAR dependencies, boot/system loader |
| `-agentlib:foo` không tìm library | Native search path không có binary | Kiểm tra `libfoo.so`/`foo.dll` và `LD_LIBRARY_PATH`/`PATH` |
| `-agentpath` không load được | Path sai, quyền file hoặc binary không tương thích | Kiểm tra đường tuyệt đối, `file`, `ldd`, OS errors |
| `Agent_OnLoad` không tìm thấy | Library chỉ có `JNI_OnLoad` hoặc export symbol sai | `nm -D`/`dumpbin /EXPORTS` |
| `GetEnv` lỗi | JVMTI không được VM hỗ trợ hoặc version không khớp | Kiểm tra `JVMTI_VERSION_1_2`, vendor, JDK |
| `SetEventCallbacks` lỗi | Callback table/phase không hợp lệ | Kiểm tra `jvmtiError`, struct size |
| Không thấy `VMInit` | Event chưa được enable, nạp muộn, callback sai | `SetEventNotificationMode` và phase |
| JVM crash khi có native agent | Pointers/ABI/threads/allocator sai | Native debugger/core dump/JVMTI error logging |
| `System.loadLibrary` nhưng không thấy agent callback | Dùng JNI library loading, không phải agent startup | Phân biệt `JNI_OnLoad`/`Agent_OnLoad` |
| `ClassFileTransformer` không thấy target | Target đã load, internal class name filter sai | `premain` sớm, kiểm tra `lab/Sample` |
| `VerifyError` sau instrumentation | Bytecode/frames/constant pool sai | Dùng parser/writer và test JVM verifier |
| JDK21+ báo dynamic-agent warning | Nạp agent sau startup | Xem JEP451, explicit startup option và policy |
| App chậm mạnh khi profiling | MethodEntry/Exit quá nhiều, log sync | Giới hạn scope, sampling, đo overhead |
| Thư viện có tên đúng nhưng sai CPU | Architecture/libc mismatch | Kiểm tra `file`, compiler target và image |
| OS không cho load binary | Security policy, signing/permissions hoặc container | Kiểm tra system logs và deployment policy |

## 15. Tự kiểm tra

1. **`-javaagent:foo.jar` khởi động thứ gì?** JAR có `Premain-Class`, gọi Java `premain`, nhận `Instrumentation` theo chữ ký phù hợp.
2. **`-agentlib:foo` khác `-agentpath:/x/libfoo.so` về API?** Không; khác cách tìm thư viện native.
3. **Startup native library thường cần export hàm nào?** `Agent_OnLoad`.
4. **Native attach vào JVM đang chạy dùng entry point nào?** `Agent_OnAttach` nếu implementation hỗ trợ.
5. **Java agent attach động cần manifest nào?** `Agent-Class` và `agentmain`.
6. **`System.loadLibrary` gọi `Agent_OnLoad` không?** Không tự động; đó là JNI loading path, có entry point `JNI_OnLoad` riêng.
7. **Lấy `jvmtiEnv*` bằng API nào?** `JavaVM.GetEnv` với version JVMTI được hỗ trợ.
8. **Có `jvmtiEnv*` là mọi event được gửi tự động?** Không; cần event callbacks, notification mode và capability/phase đúng.
9. **JVMTI `VMInit` có phải Java `premain`?** Không; callback native và Java agent entry point là hai cơ chế khác.
10. **`JNIEnv*` được chia sẻ giữa threads tùy ý?** Không; nó gắn với thread.
11. **Tại sao binary `libfoo.so` không chạy trên Windows?** ABI/OS loader khác; cần build DLL phù hợp.
12. **Vì sao `-agentlib:jdwp` không phải một JAR `Instrumentation`?** Nó dùng native debugger agent JVMTI/JNI.
13. **Trong lab Java, `return null` của transformer có nghĩa gì?** Agent chỉ quan sát, không thay class bytes.
14. **Có thể dùng đồng thời hai loại agents không?** Có, nhưng phải kiểm tra pipeline, performance, compatibility và security.
15. **JEP 451 tác động đường nào?** Chuẩn bị hạn chế **dynamic agent loading** sau startup, không đồng nhất với khai báo startup agent.
16. **Native agent có thể làm JVM crash không?** Có; invalid native memory, calling convention, pointers và threading có thể làm process crash.
17. **Khi `-agentlib` không thấy library, bước dễ khoanh vùng?** Dùng `-agentpath` trỏ đúng file tuyệt đối, kiểm tra OS dependencies/architecture và exported symbol.

## 16. Nguồn chính thức

- Oracle JDK 17 **`java.lang.instrument`**: startup `-javaagent`, `premain`, dynamic `agentmain`, manifest — https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Oracle JDK 17 **`Instrumentation`** và **`ClassFileTransformer`** — https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle JDK 17 **`java` launcher**: `-agentlib` và `-agentpath` — https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle **JVMTI specification**: `Agent_OnLoad`, `Agent_OnAttach`, `GetEnv`, capabilities, callbacks — https://docs.oracle.com/en/java/javase/20/docs/specs/jvmti.html
- Oracle **Creating a Debugging and Profiling Agent with JVMTI**, C sample — https://www.oracle.com/technical-resources/articles/javase/jvmti.html
- Oracle **Attach API VirtualMachine**: Java/native dynamic load methods — https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- Oracle **JDWP agent invocation** — https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html
- OpenJDK **JEP 451**: cảnh báo dynamic agent loading — https://openjdk.org/jeps/451
- Java SE 17 **JNI Specification** — https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html

**Tóm lại:** `-javaagent` tải **Java agent JAR** qua `Premain-Class`/`premain` và `Instrumentation`; `-agentlib`/`-agentpath` tải **native JVMTI agent library** qua `Agent_OnLoad` và `JavaVM.GetEnv`. Hai tùy chọn native khác nhau ở tên/path. Khi triển khai, hãy cân nhắc API cần thiết, lifecycle, JVM capabilities, OS/ABI và bảo mật thay vì chỉ đổi launcher flag.
