# Tạo JVM bằng JNI_CreateJavaVM và nhận JNIEnv của luồng khởi tạo

## 1. Khi nào cần nhúng JVM vào ứng dụng native?

Thông thường ta chạy `java -cp ... Main` để **JVM khởi động trước**, rồi JVM gọi xuống thư viện C/C++ thông qua Java Native Interface (JNI). Ở mô hình **nhúng JVM (embedding)**, trình tự đảo ngược: một ứng dụng C/C++ là *host process*, tự khởi tạo Java Virtual Machine ngay trong tiến trình và dùng JNI để gọi class/method Java.

Ví dụ: phần mềm máy tính viết bằng C++, một game engine có Java scripting, công cụ xử lý dữ liệu có native entry point, hoặc chương trình host muốn tái sử dụng thư viện Java mà không chạy một Java process riêng.

Trong Java SE, cổng vào chính là **JNI Invocation API**:

```c
jint JNI_CreateJavaVM(
        JavaVM **p_vm,
        void **p_env,
        void *vm_args);
```

Khi tạo thành công:

- `*p_vm` nhận **`JavaVM *`**, interface đến JVM vừa khởi tạo, dùng để quản lý attach/detach các native threads và kết thúc VM.
- `*p_env` nhận **`JNIEnv *` của chính thread đã gọi `JNI_CreateJavaVM`**. Thread đó được JVM coi là main thread (theo nghĩa Invocation API) và **đã được attach**. Không cần gọi `AttachCurrentThread` lần nữa chỉ để sử dụng JNI ngay trên thread này.
- Hàm trả `JNI_OK` khi thành công; trả một mã lỗi JNI âm nếu không tạo được VM. Trong đường lỗi, không sử dụng `vm`/`env` như những interface hợp lệ.
- Từ `env` có thể `FindClass`, `GetStaticMethodID`, `CallStatic...Method`, tạo chuỗi/array Java, xử lý exception và các thao tác JNI thông thường.

Sơ đồ:

```text
Ứng dụng C/C++ (host executable)
  │
  │  JavaVMInitArgs / JavaVMOption
  ▼
JNI_CreateJavaVM(&vm, (void **)&env, &args)
  │
  ├── JavaVM *vm ───────────────────────► JVM instance
  │                                        │
  └── JNIEnv *env ─► thread tạo VM ─────────┤
                        │                  │
                        └── FindClass      │
                            GetMethodID    │
                            Call...Method ─► Java classes / methods
  │
  └── DestroyJavaVM(vm) khi host đã kết thúc công việc
```

**Đề bài quan trọng nhất:** phân biệt *interface quản lý VM* (`JavaVM *`) với *interface JNI dành cho thread tạo VM* (`JNIEnv *`); đây là hai địa chỉ khác vai trò và khác quy tắc dùng qua thread.

## 2. Chuẩn bị cấu hình bằng JavaVMInitArgs

`JNI_CreateJavaVM` không nhận các tham số kiểu `String[] args` của Java `main`. Nó nhận `JavaVMInitArgs` gồm phiên bản JNI và các tùy chọn startup.

```c
typedef struct JavaVMOption {
    char *optionString;
    void *extraInfo;
} JavaVMOption;

typedef struct JavaVMInitArgs {
    jint version;
    jint nOptions;
    JavaVMOption *options;
    jboolean ignoreUnrecognized;
} JavaVMInitArgs;
```

Các kiểu trên do `jni.h` định nghĩa; **không tự chép khai báo** sang code production. Phần hiển thị chỉ để giải thích những trường cần thiết.

### 2.1. Ý nghĩa từng trường

| Trường | Cần hiểu |
| --- | --- |
| `version` | Phiên bản **JNI interface được yêu cầu**, ví dụ `JNI_VERSION_1_8`; **không phải** số phiên bản JDK đang chạy |
| `nOptions` | Số phần tử thật sự có trong mảng `options` |
| `options` | Mảng `JavaVMOption` chứa từng chuỗi JVM startup option |
| `ignoreUnrecognized` | Chính sách xử lý tùy chọn không được công nhận theo Invocation API; thông thường đặt `JNI_FALSE` để phát hiện cấu hình sai |

Ví dụ C:

```c
char classPathOption[] = "-Djava.class.path=build/classes";

JavaVMOption options[1];
options[0].optionString = classPathOption;
options[0].extraInfo = NULL;

JavaVMInitArgs vmArgs = {0};
vmArgs.version = JNI_VERSION_1_8;
vmArgs.nOptions = 1;
vmArgs.options = options;
vmArgs.ignoreUnrecognized = JNI_FALSE;
```

Giá trị `JNI_VERSION_1_8` được JDK 17 hỗ trợ. Không dùng `JNI_VERSION_17`: tên hằng trong JNI không được suy ra bằng cách gắn số version Java vào tên. Một ứng dụng có thể yêu cầu mức JNI API thấp hơn phiên bản JDK thực tế để giữ khả năng tương thích.

Tùy chọn `-Djava.class.path=build/classes` giúp system/application class loader tìm bytecode được biên dịch vào thư mục `build/classes`. Trong mô hình host native **không có lệnh `java -cp` tự động**; nếu không cấu hình classpath thích hợp, `FindClass("demo/Calculator")` rất dễ thất bại.

Có thể thêm những tùy chọn JVM khác:

```c
/* Ví dụ minh họa: khai báo 3 option khi thực sự muốn dùng. */
JavaVMOption options[3];
options[0].optionString = "-Djava.class.path=build/classes";
options[1].optionString = "-Xmx256m";
options[2].optionString = "-Xcheck:jni";

JavaVMInitArgs args = {0};
args.version = JNI_VERSION_1_8;
args.nOptions = 3;
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;
```

Đây là **fragment**, không phải chương trình hoàn chỉnh. `-Xmx256m` giới hạn heap tối đa và `-Xcheck:jni` giúp phát hiện nhiều lỗi sử dụng JNI trên các JVM hỗ trợ. Các option như `-X...` là chi tiết implementation/JVM: hãy kiểm tra trên runtime mục tiêu; với `ignoreUnrecognized = JNI_FALSE`, option không hợp lệ có thể khiến VM không khởi động.

**Lưu ý encoding:** `JavaVMOption.optionString` được diễn giải theo mã hóa nền tảng mặc định của VM/JNI implementation; không mặc định coi mọi chuỗi bytes C truyền vào là UTF-8. Dùng ASCII cho ví dụ và thiết kế chuyển đổi encoding cẩn thận nếu phải truyền đường dẫn hay tham số chứa ký tự Unicode.

### 2.2. Thứ tự cấp phát và lifetime của options

`JNI_CreateJavaVM` cần đọc `JavaVMInitArgs` và mảng options trong quá trình khởi tạo. Giữ dữ liệu này hợp lệ trong suốt lời gọi. Mẫu dùng biến local như trên phù hợp vì không giải phóng trước khi `JNI_CreateJavaVM` trả về.

Trong C, nên dùng mảng `char[]` có thể gán cho `char *optionString`. Trong C++, string literal có kiểu `const char[]`; khi cần truyền cho API có trường `char *`, hãy quản lý buffer có thể sửa được hoặc làm theo hướng dẫn API, tránh tùy tiện cast `const char *` rồi để một API khác sửa vùng nhớ chỉ đọc.

## 3. Phân tích đúng ba tham số của JNI_CreateJavaVM

Lời gọi tiêu biểu trong **C**:

```c
JavaVM *vm = NULL;
JNIEnv *env = NULL;

jint rc = JNI_CreateJavaVM(
        &vm,
        (void **)&env,
        &vmArgs);
```

Giải thích từng đối số:

1. **`&vm`** có kiểu `JavaVM **`, là nơi VM trả về interface quản lý JVM.
2. **`(void **)&env`** được cast vì prototype `p_env` dùng `void **`, còn biến của ứng dụng là `JNIEnv *`. Hàm đặt giá trị `JNIEnv *` của chính *thread vừa gọi CreateJavaVM* vào đây. Không truyền `env` trần hoặc một `JNIEnv *` chưa cấp phát đúng nơi.
3. **`&vmArgs`** là địa chỉ của struct chứa phiên bản JNI và startup options.

Thành công được xác minh bằng mã trả về:

```c
if (rc != JNI_OK) {
    fprintf(stderr, "JNI_CreateJavaVM failed: %d\n", (int)rc);
    return 1;
}

/* Tại đây vm và env do JNI_CreateJavaVM trả về có thể dùng. */
```

Đây là fragment cho hàm C trả `int`. **Không** dereference `vm` hay `env` ở nhánh tạo VM thất bại. Các JNI return codes khác nhau theo lỗi: ví dụ `JNI_EVERSION` (phiên bản không hỗ trợ), `JNI_ENOMEM` (không đủ bộ nhớ), `JNI_EINVAL` (tham số không hợp lệ) hoặc `JNI_ERR` (lỗi chung). Thực tế runtime có thể báo thêm thông tin chi tiết trên stderr; nên giữ nguyên stderr khi chẩn đoán.

### 3.1. `JNIEnv *` vừa nhận có phải một thread “chưa attach” không?

**Không.** JNI specification nói rõ thread gọi `JNI_CreateJavaVM` được xem là main thread của VM. `env` được trả về đã là interface JNI của thread ấy. Có thể dùng ngay:

```c
jclass cls = (*env)->FindClass(env, "java/lang/String");
```

Không cần:

```c
/* Không cần attach lại chỉ vì vừa tạo VM thành công. */
(*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
```

Việc attach một thread đã attach có thể là no-op và trả interface của thread đó, nhưng thêm lời gọi thừa dễ che nhầm lẫn ownership/lifecycle. Quan trọng hơn, **`JNIEnv *env` không phải một biến “global” có thể chuyển sang mọi thread** chỉ vì nó được nhận lúc VM khởi tạo.

## 4. Ví dụ chạy được: C host tạo JVM rồi gọi Java method

Ví dụ dùng **JDK 17+**, **C11**, GCC hoặc Clang trên **Linux x86-64/aarch64** phù hợp với JDK cài đặt. Java chứa một phương thức static `add`. Chương trình C tạo VM, xác nhận `GetEnv` trên thread khởi tạo, tra cứu class, gọi phương thức Java và kết thúc VM.

Đây là **chương trình native C gọi Java**, không phải JNI shared library được nạp bằng `System.loadLibrary`. Vì vậy build host **link đến thư viện JVM (`libjvm.so`)**.

### 4.1. Cấu trúc dự án

```text
embed-jvm/
├── src/
│   └── demo/
│       └── Calculator.java
├── native/
│   └── embed.c
└── build/
    ├── classes/              # javac tạo
    └── embed                 # C compiler tạo
```

### 4.2. Java class

**Tệp `src/demo/Calculator.java`:**

```java
package demo;

public final class Calculator {
    private Calculator() {}

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

Phương thức `add` là `public static int add(int,int)`, với descriptor JNI **`(II)I`**:

- `(II)`: hai đối số Java `int`.
- `I` sau dấu ngoặc: kết quả Java `int`.

`Math.addExact` ném `ArithmeticException` nếu phép cộng tràn miền signed 32-bit Java `int`, giúp minh họa nhu cầu kiểm tra Java exceptions từ phía native. Trong đường thành công của ví dụ, `20 + 22 = 42`.

### 4.3. C host khởi tạo VM và nhận env của thread tạo VM

**Tệp `native/embed.c`:**

```c
#include <jni.h>
#include <stdio.h>

int main(void) {
    char cp[] = "-Djava.class.path=build/classes";

    JavaVMOption opts[1];
    opts[0].optionString = cp;
    opts[0].extraInfo = NULL;

    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_8;
    args.nOptions = 1;
    args.options = opts;
    args.ignoreUnrecognized = JNI_FALSE;

    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    jint createRc = JNI_CreateJavaVM(
            &vm, (void **)&env, &args);

    if (createRc != JNI_OK) {
        fprintf(stderr, "Cannot create JVM: %d\n", (int)createRc);
        return 1;
    }

    printf("JNI_CreateJavaVM: JNI_OK\n");

    int exitCode = 1;
    jclass calcClass = NULL;

    /* Xác minh thread vừa tạo VM đã có JNIEnv riêng. */
    JNIEnv *checkedEnv = NULL;
    jint getRc = (*vm)->GetEnv(
            vm, (void **)&checkedEnv, JNI_VERSION_1_8);

    if (getRc != JNI_OK || checkedEnv == NULL) {
        fprintf(stderr, "GetEnv failed: %d\n", (int)getRc);
        goto shutdown;
    }

    printf("GetEnv(init thread): JNI_OK\n");

    calcClass = (*env)->FindClass(env, "demo/Calculator");
    if (calcClass == NULL) {
        fprintf(stderr, "Cannot find demo.Calculator\n");
        if ((*env)->ExceptionCheck(env)) {
            (*env)->ExceptionDescribe(env);
        }
        goto shutdown;
    }

    jmethodID add = (*env)->GetStaticMethodID(
            env, calcClass, "add", "(II)I");
    if (add == NULL) {
        fprintf(stderr, "Cannot find Calculator.add(int,int)\n");
        if ((*env)->ExceptionCheck(env)) {
            (*env)->ExceptionDescribe(env);
        }
        goto shutdown;
    }

    jint result = (*env)->CallStaticIntMethod(
            env, calcClass, add, (jint)20, (jint)22);

    if ((*env)->ExceptionCheck(env)) {
        fprintf(stderr, "Java method threw an exception\n");
        (*env)->ExceptionDescribe(env);
        goto shutdown;
    }

    printf("Java add(20, 22): %d\n", (int)result);
    exitCode = 0;

shutdown:
    if (calcClass != NULL) {
        (*env)->DeleteLocalRef(env, calcClass);
    }

    jint destroyRc = (*vm)->DestroyJavaVM(vm);
    if (destroyRc == JNI_OK) {
        printf("DestroyJavaVM: JNI_OK\n");
    } else {
        fprintf(stderr, "DestroyJavaVM failed: %d\n",
                (int)destroyRc);
        exitCode = 1;
    }

    return exitCode;
}
```

### 4.4. Đọc từng bước

- `JNI_CreateJavaVM` nhận địa chỉ `vm` và `env`. Sau khi `JNI_OK`, **không cần attach lại thread tạo VM**.
- `GetEnv` trên **cùng thread** trả `JNI_OK` và một `JNIEnv *` hợp lệ. Ví dụ không in địa chỉ, vì địa chỉ phụ thuộc runtime/process.
- `FindClass(env, "demo/Calculator")` dùng tên class **JNI internal** có dấu slash. Khi được gọi từ ứng dụng native qua Invocation Interface mà không có Java native-method frame, JNI dùng **system class loader**. Vì đã đặt `-Djava.class.path=build/classes`, loader đó tìm được class.
- `GetStaticMethodID` dùng đúng tên `add` và descriptor `(II)I`. Nếu tên/chữ ký sai, JNI có thể có exception pending; không tiếp tục gọi method khi `add == NULL`.
- `CallStaticIntMethod` thực thi mã Java và trả `jint`. Phải gọi `ExceptionCheck` **trước khi xem `result` là kết quả hợp lệ**.
- `ExceptionDescribe` trong nhánh lỗi in stack trace vào stderr và **clear exception pending**; đây là chủ ý chỉ để chẩn đoán demo. Trong host production, có thể lấy exception object, trích thông tin và ánh xạ sang lỗi C/C++ theo giao thức riêng.
- `DeleteLocalRef` giải phóng local reference tới class. `DestroyJavaVM` được gọi khi không còn công việc và thread không còn pending JNI calls.
- `DestroyJavaVM` có thể phải chờ các **non-daemon Java threads/natively-attached threads** kết thúc. Đừng xem nó như một hàm `free()` luôn trả ngay; đoạn demo không tạo thêm worker.

### 4.5. Lệnh biên dịch và chạy trên Linux

Đứng trong thư mục `embed-jvm`. Cần JDK có `jni.h` và `libjvm.so`. Giả sử `JAVA_HOME` đã trỏ tới thư mục JDK chính xác:

```bash
mkdir -p build/classes

javac -d build/classes src/demo/Calculator.java

cc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/embed.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o build/embed

./build/embed
```

Vì host executable gọi trực tiếp `JNI_CreateJavaVM`, linker phải tìm được **`libjvm.so`**. `-L` cung cấp đường dẫn lúc liên kết; `-Wl,-rpath,...` đưa đường dẫn thư viện động vào executable để dynamic loader thường có thể tìm được `libjvm.so` lúc chạy. Một số môi trường packaging dùng biến môi trường `LD_LIBRARY_PATH` hoặc cơ chế loader path riêng thay vì rpath; không hard-code đường dẫn JDK hệ thống vào sản phẩm phát hành mà không kiểm soát phiên bản và quyền cập nhật.

Với Java classpath dạng đường dẫn tương đối `build/classes`, phải **chạy executable từ thư mục `embed-jvm`**. Nếu gọi `build/embed` từ thư mục khác, phải đổi cấu hình classpath thành đường dẫn phù hợp hoặc dùng đường dẫn tuyệt đối.

**Stdout mong đợi trên đường chạy thành công:**

```text
JNI_CreateJavaVM: JNI_OK
GetEnv(init thread): JNI_OK
Java add(20, 22): 42
DestroyJavaVM: JNI_OK
```

Chương trình không cần một Java `public static void main(String[] args)`: entry point ở đây là **`main(void)` của C**. JNI có thể gọi bất kỳ method Java hợp lệ nào có signature và visibility phù hợp. Nếu muốn gọi Java `main`, cần `GetStaticMethodID(..., "main", "([Ljava/lang/String;)V")` và tạo đối số `String[]` tương ứng trước khi `CallStaticVoidMethod`.

Lưu ý về nền tảng: trên macOS/Windows cần JNI include khác, tên/định dạng thư viện JVM khác và lệnh linker tương ứng; không dùng nguyên dòng `-L.../lib/server -ljvm` của Linux cho mọi hệ. Bản binary C và JDK phải tương thích kiến trúc/ABI (ví dụ x64 host cần JVM x64).

## 5. JNIEnv của thread khởi tạo và JNIEnv ở các thread khác

### 5.1. Điều gì xảy ra nếu host tạo thêm một native thread?

`JNIEnv *` là **thread-local interface**. Nó chỉ hợp lệ trên thread nhận interface, dù VM có thể hoạt động đồng thời trên nhiều threads.

```text
Native host process
│
├── Thread T0: JNI_CreateJavaVM
│   ├── JavaVM *vm ───────────────────────┐
│   └── JNIEnv *env0 (chỉ của T0)         │
│                                        │
└── Thread T1: pthread/std::thread       │
    ├── GetEnv → JNI_EDETACHED (nếu chưa attach)
    ├── AttachCurrentThread(vm) ◄────────┘
    ├── JNIEnv *env1 (chỉ của T1)
    ├── Thực hiện JNI calls
    └── DetachCurrentThread(vm) trước khi kết thúc
```

`JavaVM *vm` có thể được truyền tới threads khác để sử dụng Invocation API. **Không được chuyển `env0` của T0 sang T1** rồi gọi `(*env0)->FindClass(env0, ...)` trên T1. Một số JVM có thể phát hiện lỗi và abort; không có hợp đồng JNI nào cho phép thao tác này.

### 5.2. `GetEnv` kiểm tra tình trạng attach, không tự attach

Chữ ký C:

```c
jint GetEnv(
        JavaVM *vm, void **p_env, jint version);
```

Có ba kết quả quan trọng:

| Kết quả | Ý nghĩa |
| --- | --- |
| `JNI_OK` | Current thread đã attach; `*p_env` có `JNIEnv *` hợp lệ |
| `JNI_EDETACHED` | Current thread chưa attach; phải `AttachCurrentThread` nếu muốn gọi JNI |
| `JNI_EVERSION` | JNI version yêu cầu không được hỗ trợ |

Ví dụ helper C minh họa trường hợp host worker:

```c
/* Fragment: vm là JavaVM* hợp lệ; caller đang ở native worker.
   Không tự dùng vm sau khi VM đã DestroyJavaVM. */
JNIEnv *workerEnv = NULL;

jint rc = (*vm)->GetEnv(
        vm, (void **)&workerEnv, JNI_VERSION_1_8);

if (rc == JNI_EDETACHED) {
    rc = (*vm)->AttachCurrentThread(
            vm, (void **)&workerEnv, NULL);
    if (rc != JNI_OK) {
        /* Không dùng workerEnv nếu attach thất bại. */
        return;
    }

    /* ... JNI operations trên current worker thread ... */

    (*vm)->DetachCurrentThread(vm);

} else if (rc == JNI_OK) {
    /* Thread đã attach: dùng workerEnv, không detach tùy tiện
       nếu attach lifecycle thuộc một component khác. */

} else {
    /* JNI_EVERSION hoặc lỗi khác. */
}
```

Đây là **fragment giả định nằm trong hàm C trả `void`** và không có worker task cụ thể. Trong production nên lưu cờ `attachedHere` để bảo đảm detach **chỉ những thread do logic này attach**. Khi native thread tự tạo kết thúc, phải detach nếu vẫn attach, và không detach khi còn Java methods trên call stack.

**Điểm cần nhớ:** `JNI_CreateJavaVM` đã attach thread gọi nó, còn `AttachCurrentThread` dành cho thread khác cần tham gia VM. `GetEnv` giúp kiểm tra current thread, không phải cách lấy một `JNIEnv *` dùng chung cho tất cả.

### 5.3. Trường hợp tạo JVM từ “primordial thread”

JNI specification lưu ý trên một số hệ điều hành, **primordial process thread** (thường là thread chạy C `main` ban đầu) có cấu hình stack đặc biệt, có thể ảnh hưởng đến khả năng hoạt động như Java thread bình thường. Tài liệu **khuyến nghị tạo một native thread chuyên dụng để khởi tạo JVM** thay vì luôn dùng primordial thread.

Ví dụ phần 4 cố ý dùng `main(void)` để trình bày API ngắn, dễ chạy. Với ứng dụng host thực tế cần độ bền cao, hãy tạo một thread riêng có stack size phù hợp, gọi `JNI_CreateJavaVM` và điều phối Java code ngay trên thread ấy, rồi phối hợp `DestroyJavaVM` cùng vòng đời non-daemon threads. Lựa chọn này cần phù hợp với thư viện GUI, event loop và yêu cầu thread-affinity của host.

**Không nên hiểu “thread khởi tạo” là một singleton thread toàn tiến trình có quyền dùng mọi JNI call thay cho các thread khác**. Từng thread vẫn cần env riêng và phải tôn trọng state của JVM.

## 6. Cách xử lý exception khi C là chương trình host

Khi C gọi Java bằng `CallStaticIntMethod`/`CallObjectMethod`, một Java method có thể **ném Java exception**. JVM đặt exception ở trạng thái pending trên thread gọi JNI. C code **không tự động thực thi Java `catch`**, không tự nhận một C++ `std::exception`, cũng không thể suy ra lỗi chỉ từ giá trị trả về của JNI call.

Cách kiểm tra:

```c
jint value = (*env)->CallStaticIntMethod(
        env, clazz, methodId, (jint)1, (jint)2);

if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
    /* Có Java exception pending. Không xem value là kết quả. */
    (*env)->ExceptionDescribe(env);  /* In stack trace VÀ CLEAR. */
    /* Chuyển sang đường cleanup / host error. */
}
```

**Đây là fragment**, `clazz` và `methodId` phải đã tra cứu đúng và còn hợp lệ. `ExceptionDescribe` là tiện ích chẩn đoán, **có side effect xóa pending exception**; nếu muốn báo lỗi giữ nguyên cho một tầng Java khác, không dùng nó vô ý.

Trong host production, có thể:

1. Gọi `ExceptionOccurred` để nhận local ref tới `Throwable` đang pending.
2. Dùng `ExceptionClear` có chủ đích nếu cần gọi các JNI functions khác để lấy message/cause hoặc chuyển đổi lỗi.
3. Ánh xạ thông tin sang status/error object của C/C++, giữ log có ngữ cảnh và trả lỗi qua API host.
4. `DeleteLocalRef` đúng lifetime; không giữ local `jthrowable` sau native frame/thread nếu chưa tạo global ref và quản lý vòng đời.

**Khi exception đang pending, chỉ một số JNI API được phép dùng**, ví dụ `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear` và `DeleteLocalRef`. Không tiếp tục `FindClass`/`GetMethodID`/`Call...Method` ngẫu nhiên trong nhánh pending; phải dọn hoặc clear theo một chiến lược rõ.

### 6.1. Thử lỗi Java trong ví dụ

Nếu muốn tự quan sát lỗi từ Java `Math.addExact`, thay *tạm thời* phần gọi thành:

```c
/* Fragment thay cho lời gọi thành công ở phần 4. */
jint result = (*env)->CallStaticIntMethod(
        env, calcClass, add, (jint)2147483647, (jint)1);
```

Java sẽ ném `ArithmeticException` do overflow. Nhánh `ExceptionCheck` của host ghi stack trace ra stderr và không in dòng kết quả `Java add(20, 22): 42`. **Không có expected stderr cố định**, vì stack trace và chi tiết lỗi có thể thay đổi theo JDK/implementation. Sau khi quan sát, khôi phục lời gọi `20, 22` để chạy lại happy path.

## 7. FindClass trong native host và class loader

`FindClass` trong một Java native method thường chọn loader của **class khai báo native method**. Nhưng khi được gọi **qua Invocation Interface mà không có một Java native method trên stack**, như `FindClass` ngay sau `JNI_CreateJavaVM` từ C host, JNI dùng **system class loader**.

Vì thế trong ví dụ:

```c
jclass cls = (*env)->FindClass(env, "demo/Calculator");
```

tra cứu thành công khi bytecode `demo.Calculator` nằm trong classpath đúng. Nếu một Java class chỉ nằm trong một **custom `ClassLoader`/module layer** mà system loader không biết, tìm bằng tên có thể thất bại. Không mặc nhiên cho rằng `FindClass` tự biết loader của plugin hay container mà host muốn dùng.

Khi cần dùng custom loader:

- Gọi một Java bootstrap/entry class mà system loader nhìn thấy để dựng module/plugin layer, rồi cho Java trả về `Class<?>` hoặc callback object.
- Hoặc lưu **global ref tới `ClassLoader`** hợp lệ, gọi `loadClass(String)` theo tên Java dạng dấu chấm (ví dụ `"plugin.Service"`), rồi `GetMethodID`/`Call...Method` trên class trả về.
- Giữ ownership và cleanup cho các `jclass`/`jobject` reference; không cache một local ref sang thread khác hoặc qua nhiều JNI calls.

Sửa `-Djava.class.path=...` hoặc loader design ở chỗ đúng là giải pháp cho vấn đề class lookup; đổi tên sang `Class.forName` trong code C mà không có helper/loader đúng không giải quyết được.

### 7.1. Cách đặt JNI signature chính xác

JNI dùng method descriptors theo cấu trúc JVM, không dùng tên type Java theo cú pháp nguồn:

| Java declaration | JNI descriptor |
| --- | --- |
| `int add(int a, int b)` | `(II)I` |
| `void log(String message)` | `(Ljava/lang/String;)V` |
| `String format(int n)` | `(I)Ljava/lang/String;` |
| `void main(String[] args)` | `([Ljava/lang/String;)V` |

Tra cứu sai descriptor khiến `GetStaticMethodID`/`GetMethodID` thất bại, thường tạo `NoSuchMethodError` pending. `javap -s` hữu ích khi tên method phức tạp; dấu chấm trong tên class JNI dùng slash, các array type dùng ký pháp `[`.

## 8. Vòng đời JVM và giới hạn triển khai thực tế

### 8.1. `DestroyJavaVM` là bước lifecycle, không phải một lệnh reset tùy ý

Sau khi tạo VM thành công, ứng dụng C/C++ nên có **một owner rõ ràng** quản lý lúc kết thúc. `(*vm)->DestroyJavaVM(vm)` bắt đầu quá trình kết thúc VM và chờ điều kiện shutdown phù hợp. Nếu các non-daemon Java threads hoặc native-attached threads vẫn chạy, thao tác có thể **chờ lâu** hoặc không hoàn tất theo kỳ vọng ứng dụng.

Vì vậy, thứ tự shutdown thông thường là:

1. Ngừng gửi request mới sang Java.
2. Yêu cầu Java services, executors và các native-attached workers kết thúc.
3. Chờ callback đang chạy xong, hủy global JNI refs/handle, dọn native resources.
4. Bảo đảm không còn luồng nào định dùng `JNIEnv *` hay `JavaVM *` của VM đã kết thúc.
5. Gọi `DestroyJavaVM` theo cơ chế của runtime và kiểm tra mã trả về.

**Đừng thiết kế ứng dụng bằng cách tạo rồi hủy JVM lặp đi lặp lại trong cùng process** như một vòng restart rẻ. JNI specification nêu rõ **không hỗ trợ tạo nhiều JVM trong một process**. Khả năng khởi tạo lại sau khi destroy không phải một hợp đồng portable cần dựa vào; nếu cần hoàn toàn mới, restart tiến trình host hoặc chạy JVM ở process riêng.

### 8.2. `JNI_GetCreatedJavaVMs` dùng để làm gì?

JNI Invocation API còn cung cấp:

```c
jint JNI_GetCreatedJavaVMs(
        JavaVM **vmBuf, jsize bufLen, jsize *nVMs);
```

API này cho phép kiểm tra các VM đã tồn tại theo interface của runtime; **không phải một cách tạo thêm VM**. Dù interface dùng mảng kết quả, Java SE JNI không hỗ trợ tạo nhiều VM độc lập trong cùng một process.

Nếu một thư viện native được nhúng vào host ứng dụng khác và không sở hữu process, nó không được tùy tiện gọi `JNI_CreateJavaVM` hoặc `DestroyJavaVM` khi VM thuộc về component khác. Chủ sở hữu tiến trình/VM phải đưa ra hợp đồng lifecycle.

### 8.3. Khác nhau giữa nhúng JVM và nạp JNI shared library

| Khía cạnh | Native host nhúng JVM | Java nạp shared JNI library |
| --- | --- | --- |
| Entrypoint | C/C++ `main` hoặc native host | Java `main`/framework |
| Ai tạo JVM? | Host gọi `JNI_CreateJavaVM` | Java launcher/framework đã tạo |
| Ai lấy `JNIEnv *` đầu tiên? | `JNI_CreateJavaVM` trả trên thread khởi tạo | JVM truyền `JNIEnv *` làm tham số khi gọi native method |
| Link/nạp library chính | Host link/dynamic load `libjvm` | Java gọi `System.loadLibrary` để nạp thư viện ứng dụng |
| Quản lý shutdown VM | Host sở hữu và điều phối `DestroyJavaVM` | JVM launcher/runtime điều phối |
| Tra cứu class | Thường qua system loader nếu gọi từ Invocation Interface | Loader của class khai báo native method trong native-frame context |

`JNI_OnLoad` là hook của **thư viện JNI do Java VM nạp**, không phải hàm thay thế `JNI_CreateJavaVM` để khởi tạo VM từ một executable C.

## 9. Lỗi thường gặp và hướng khắc phục

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Linker báo `undefined reference to JNI_CreateJavaVM` | Không link tới JVM library hoặc sai thứ tự flags của linker | Thêm `-L.../lib/server -ljvm` sau mã nguồn/object files |
| Chạy binary báo thiếu `libjvm.so` | Dynamic loader không thấy JVM library | Kiểm tra rpath/`LD_LIBRARY_PATH`, kiến trúc và đường dẫn JDK |
| `JNI_CreateJavaVM` trả lỗi âm | Version JNI/option/path/memory không hợp lệ | Log mã lỗi và stderr; bắt đầu bằng cấu hình tối thiểu |
| `GetEnv` trả `JNI_EDETACHED` trên native worker | Worker chưa được attach | Gọi `AttachCurrentThread` trước JNI calls |
| Crash khi chuyển `JNIEnv *` sang thread khác | Dùng interface sai thread | Chỉ chia sẻ `JavaVM *`; mỗi thread nhận env riêng |
| `FindClass("demo/Calculator")` thất bại | Sai classpath, tên JNI hoặc loader | Kiểm tra `-Djava.class.path`, `javap`, system/custom loader |
| `GetStaticMethodID` trả `NULL` | Sai tên/descriptor hoặc method không static | Kiểm tra `javap -s`, `(II)I`, pending exception |
| Java method trả giá trị lạ sau lỗi | Host không gọi `ExceptionCheck` | Kiểm tra pending exception trước khi dùng kết quả |
| `DestroyJavaVM` không trả về | Non-daemon Java/native-attached thread còn chạy | Điều phối shutdown và detach workers |
| Gọi `JNI_CreateJavaVM` nhiều lần trong cùng process | Nhầm tưởng tạo VM thứ hai hoặc restart JVM là portable | Chỉ một JVM theo hợp đồng JNI; dùng process boundary nếu cần reset |
| C host chạy được ở thư mục dự án nhưng không chạy khi triển khai | Classpath đặt tương đối vào cwd | Xây dựng classpath/VM path tuyệt đối trong deployment |
| JVM khởi tạo nhưng Java callback không tìm được class plugin | `FindClass` từ Invocation Interface dùng system loader | Cho Java bootstrap chọn plugin loader rồi truyền `Class<?>`/object đúng |

### 9.1. Checklist trước khi giao bản nhúng JVM

- [ ] Host xác định đúng phiên bản JDK và CPU/ABI; có JNI headers và JVM shared library đúng môi trường.
- [ ] `JavaVMInitArgs.version` dùng hằng JNI thực sự được hỗ trợ, không nhầm với Java language version.
- [ ] `options` và `nOptions` khớp nhau; cấu hình classpath/module path đủ để tra class ứng dụng.
- [ ] `JNI_CreateJavaVM` được gọi một lần trong lifecycle host và kiểm tra `JNI_OK` trước khi dùng `vm`/`env`.
- [ ] `JNIEnv *` của thread tạo JVM **chỉ dùng trên thread đó**.
- [ ] Native threads khác dùng `JavaVM*` để `GetEnv`/`AttachCurrentThread` và detach đúng quyền sở hữu.
- [ ] Kiểm tra `ExceptionCheck` sau các JNI calls có thể gây Java exception, dọn local/global refs đúng lifetime.
- [ ] Shutdown có cơ chế stop/drain cho non-daemon threads và không sử dụng VM interfaces sau khi destroy.
- [ ] Không phụ thuộc khởi tạo nhiều JVM hay restart JVM trong một tiến trình.
- [ ] Kiểm thử cả classpath sai, option JVM sai, lỗi linker/libjvm, exception Java và shutdown có worker.

## 10. Câu hỏi tự kiểm tra

**1.** `JNI_CreateJavaVM(&vm, (void **)&env, &args)` thành công. `env` thuộc thread nào?  
**Đáp án:** Chính thread đã gọi `JNI_CreateJavaVM`. Thread đó đã attach vào VM; không cần attach lần nữa để gọi JNI trên thread ấy.

**2.** Có thể lưu `JNIEnv *env` vào biến global C rồi dùng từ mọi `pthread` không?  
**Đáp án:** Không. `JNIEnv *` chỉ hợp lệ trên thread sở hữu; lưu `JavaVM*` và lấy một env mới bằng `AttachCurrentThread` trên mỗi native worker.

**3.** `args.version = JNI_VERSION_1_8` trên Java 17 có sai do “1.8 khác 17” không?  
**Đáp án:** Không. Đây là phiên bản **JNI specification/API**, không phải JDK release number.

**4.** Tại sao `FindClass("demo/Calculator")` hoạt động trong C host của ví dụ?  
**Đáp án:** JVM được khởi tạo với `-Djava.class.path=build/classes` và `FindClass` qua Invocation Interface không có native Java frame dùng system class loader, nhìn thấy class ấy.

**5.** C host gọi `CallStaticIntMethod`, Java ném `ArithmeticException`. Có được dùng `jint result` như phép cộng thành công?  
**Đáp án:** Không. Phải kiểm tra `ExceptionCheck`. Khi Java exception pending, giá trị trả về không biểu thị một kết quả nghiệp vụ thành công.

**6.** Có thể tạo JVM thứ hai để chạy phiên bản Java khác trong cùng process không?  
**Đáp án:** Không theo hợp đồng portable của Java SE JNI Invocation API. Nhiều VM trong cùng process không được hỗ trợ.

**7.** `GetEnv` trả `JNI_EDETACHED`. Điều đó có nghĩa JVM không tồn tại?  
**Đáp án:** Không nhất thiết. Nó thường cho biết **current thread chưa attach** vào VM đang tồn tại; phải attach trước khi dùng JNI.

**8.** Vì sao `DestroyJavaVM` có thể chờ?  
**Đáp án:** JVM phải phối hợp shutdown với các non-daemon Java/native-attached threads. Nếu những thread ấy chưa kết thúc, không thể giả định `DestroyJavaVM` trả ngay.

## 11. Tóm tắt kiến thức cốt lõi

- **`JNI_CreateJavaVM` vừa tạo VM vừa trả `JavaVM *` và `JNIEnv *` của thread gọi hàm.** Đây là cơ chế nhúng JVM từ C/C++, khác với `System.loadLibrary`.
- **Cấu hình bằng `JavaVMInitArgs`**, đặc biệt `JNI_VERSION_1_8` cho ví dụ Java 17+ và `-Djava.class.path=...` để tra cứu class.
- **`JavaVM*` quản lý VM và hỗ trợ attach/detach; `JNIEnv*` chỉ dùng trên thread của nó.** Thread tạo VM đã attach, worker khác phải attach riêng.
- **JNI lookup cần tên class nội bộ và descriptor chuẩn**: `demo/Calculator`, `add`, `(II)I`.
- **Sau Java call phải kiểm tra pending exception** trước khi sử dụng kết quả. `ExceptionDescribe` có tác dụng in và xóa exception, nên chỉ dùng có chủ đích.
- **Chỉ tạo một VM trong process**, quản lý shutdown, threads, references và linkage tới `libjvm` như những phần của thiết kế sản phẩm.

### Tài liệu chuẩn

- [Oracle — JNI Invocation API, Creating the VM / JNI_CreateJavaVM (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): tham số, `JavaVMInitArgs`, interface `JNIEnv *`, main thread, giới hạn nhiều VM, `GetEnv` và `DestroyJavaVM`.
- [Oracle — JNI Design Overview (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): `JNIEnv *` gắn với thread và cách sử dụng JNI interfaces.
- [Oracle — JNI Functions (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `FindClass`, `GetStaticMethodID`, `CallStaticIntMethod`, `ExceptionCheck` và `ExceptionDescribe`.
- [Oracle — Java SE 17 javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem method descriptors bằng `javap -s` khi tra cứu bằng JNI.
