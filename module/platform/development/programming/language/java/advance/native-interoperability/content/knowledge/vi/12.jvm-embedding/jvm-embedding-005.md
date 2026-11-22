# Tìm lớp, gọi điểm vào Java và quản lý ngoại lệ từ ứng dụng chủ bản địa

Một ứng dụng viết bằng C/C++ có thể **nhúng Java Virtual Machine (JVM)** để thực thi mã Java ngay trong tiến trình của chính ứng dụng đó. Đây là hướng gọi *native host → JVM → Java*, khác với trường hợp quen thuộc *Java → JNI native library → C*. Native host có trách nhiệm khởi tạo JVM bằng **JNI Invocation API**, tìm class phù hợp, xác định method ID với chữ ký JVM chính xác, tạo đối số JNI, gọi phương thức Java và xử lý mọi ngoại lệ phát sinh trước khi tiếp tục hoặc kết thúc tiến trình.

Ba quyết định quan trọng nhất trong một native host là:

1. **Tìm đúng lớp:** `FindClass` cần tên class đúng định dạng JNI và **class loader** nhìn thấy nó. Classpath/module path của JVM phải được thiết lập từ lúc tạo VM.
2. **Gọi đúng điểm vào:** `GetStaticMethodID`/`GetMethodID` yêu cầu tên và **method descriptor** chính xác; `CallStatic<Type>Method`/`Call<Type>Method` phải khớp kiểu trả về và danh sách tham số.
3. **Kiểm soát lỗi:** Java exception có thể trở thành **pending exception trên thread của native host**. Vì không nhất thiết có Java caller đang đợi phía trên, native host phải tự chọn xử lý, ghi nhận, chuyển đổi hoặc kết thúc an toàn; không được để exception pending rồi tiếp tục gọi JNI tùy tiện.

Bài học trình bày đầy đủ luồng này, ví dụ **Java 17+ và C11 chạy được trên Linux**, đường thành công, hai loại ngoại lệ đã biết, đường lỗi bất ngờ, quản lý local references, shutdown JVM, và những vấn đề thực tế về class loader, đa luồng và bảo mật.

## 1. Hiểu đúng chiều gọi khi nhúng JVM

Trong ứng dụng Java thông thường, lệnh `java com.example.Main` được Java launcher xử lý; JVM được tạo trước khi `public static void main(String[] args)` chạy. Trong ứng dụng native host, **C là nơi khởi động**, quyết định lúc tạo VM và gọi phương thức Java nào. Không nhất thiết phải gọi một phương thức tên `main`.

Sơ đồ vòng đời:

```text
Tiến trình native: main() của C
      |
      | Chuẩn bị JavaVMInitArgs, options
      v
JNI_CreateJavaVM(&vm, &env, &args)
      |
      +--> JavaVM *vm: giao diện quản lý JVM
      +--> JNIEnv *env: giao diện JNI CỦA THREAD hiện tại
      |
      | FindClass("com/example/EntryPoint")
      v
jclass entryClass (local reference)
      |
      | GetStaticMethodID(entryClass, "run", "(Ljava/lang/String;)I")
      v
jmethodID runMethod (ID, không phải local reference)
      |
      | NewStringUTF("21") -> jstring arg (local reference)
      | CallStaticIntMethod(entryClass, runMethod, arg)
      v
Java method thực thi trong JVM
      |
      +--> Nếu thành công: trả jint
      |
      +--> Nếu ném exception: pending trên JNI thread
      |    ExceptionCheck/ExceptionOccurred
      |    ExceptionClear nếu chọn xử lý
      |
      v
Dọn local references, bộ nhớ native, pending state
      |
      v
DestroyJavaVM(vm) -> native main() trả exit code
```

Đặc biệt, `JNI_CreateJavaVM` không phải một JNI native method do Java gọi. Nó thuộc **Invocation API**, có thể được gọi từ chương trình chủ bản địa đã link/nạp thư viện VM. Ngược lại, các lời gọi `(*env)->FindClass(...)` và `(*env)->CallStaticIntMethod(...)` thuộc giao diện `JNIEnv` sau khi JVM đã tồn tại.

### 1.1. Hai nhóm con trỏ không được lẫn

| Giá trị | Cấp bởi | Vai trò | Quy tắc lifetime |
| --- | --- | --- | --- |
| `JavaVM *vm` | `JNI_CreateJavaVM` | Truy cập Invocation API; attach/detach thread, destroy VM | Gắn với JVM đã được tạo; không dùng sau shutdown |
| `JNIEnv *env` | `JNI_CreateJavaVM` hoặc `AttachCurrentThread` | Gọi JNI functions trên **một thread** | Chỉ dùng ở thread nhận `env` |
| `jclass` / `jobject` / `jstring` | JNI calls | Tham chiếu opaque tới Java objects | Local/global/weak-global scope theo hợp đồng JNI |
| `jmethodID` | `GetStaticMethodID` / `GetMethodID` | ID opaque định danh method của class | Không phải `jobject`, không dùng `DeleteLocalRef`; lifetime gắn với class |
| `jint` / `jlong` | Java primitive ↔ JNI | Dữ liệu nguyên thủy | Không cần dọn local reference |

Cả `JavaVM *` và `JNIEnv *` có cú pháp tương ứng trong C khác với C++. Với **C**, gọi qua bảng hàm như `(*env)->FindClass(env, "java/lang/String")`; trong **C++**, thường viết `env->FindClass("java/lang/String")`. Không sao chép chữ ký C++ vào file C11.

## 2. Khởi tạo JVM: `JNI_CreateJavaVM` và `JavaVMInitArgs`

Các kiểu/entry point chính trong `jni.h`:

```c
jint JNI_CreateJavaVM(JavaVM **p_vm,
                      void **p_env,
                      void *vm_args);

typedef struct JavaVMInitArgs {
    jint version;
    jint nOptions;
    JavaVMOption *options;
    jboolean ignoreUnrecognized;
} JavaVMInitArgs;

typedef struct JavaVMOption {
    char *optionString;
    void *extraInfo;
} JavaVMOption;
```

Đây là phần **mô tả API**, không phải file C biên dịch độc lập. Header `jni.h` đã cung cấp các định nghĩa phù hợp với JDK và compiler. Không tự định nghĩa lại các typedef này trong dự án.

- `version`: phiên bản giao diện **JNI**, ví dụ `JNI_VERSION_1_8`. Đây **không phải** chuỗi phiên bản JDK 8/17/21; JNI 1.8 vẫn có thể sử dụng trên JDK 17+.
- `nOptions`, `options`: cấu hình VM ở thời điểm startup, chẳng hạn `-Djava.class.path=.`, `-Xms...`, `-Xmx...`, các tùy chọn module.
- `ignoreUnrecognized`: nếu `JNI_FALSE`, một số option không được nhận diện làm startup thất bại thay vì bị bỏ qua.
- `p_vm`: chỗ JVM điền `JavaVM *`.
- `p_env`: chỗ JVM điền `JNIEnv *` hợp lệ cho **thread đã gọi tạo VM**.
- Return code `JNI_OK` biểu thị thành công; mã âm khác như `JNI_ERR`, `JNI_EVERSION`, `JNI_ENOMEM`... thể hiện lỗi theo tình huống.

Ví dụ khởi tạo tối giản bằng C:

```c
#include <jni.h>

JavaVM *vm = NULL;
JNIEnv *env = NULL;

char classpath[] = "-Djava.class.path=.";
JavaVMOption option = { .optionString = classpath, .extraInfo = NULL };
JavaVMInitArgs args = {
    .version = JNI_VERSION_1_8,
    .nOptions = 1,
    .options = &option,
    .ignoreUnrecognized = JNI_FALSE
};

jint result = JNI_CreateJavaVM(&vm, (void **)&env, &args);
if (result != JNI_OK) {
    /* Không được gọi JNIEnv functions nếu JVM chưa tạo thành công. */
}
```

Đoạn trên **chỉ minh họa khối trong hàm C**; chương trình chạy đầy đủ ở phần 6. Tên `java.class.path` được set khi tạo VM, để system class loader nhìn thấy các `.class` trong thư mục hiện hành. Với JAR, đường dẫn khác hoặc môi trường nhiều module, phải thiết kế đường tìm lớp phù hợp.

### 2.1. Vì sao classpath phải đúng ngay từ đầu?

`FindClass` tìm class qua class loader của ngữ cảnh hiện tại. Khi native host dùng Invocation API mà không có native method Java đang ở call stack, JNI mặc định sử dụng **system class loader**. Vì vậy `-Djava.class.path=.` là lựa chọn rõ ràng cho chương trình mẫu có file `EmbeddedEntry.class` nằm trong working directory.

Nếu chạy binary từ thư mục khác, dấu `.` cũng chỉ sang thư mục khác. Kết quả có thể là `FindClass == NULL` và pending `NoClassDefFoundError`, dù `EmbeddedEntry.class` vẫn tồn tại ở một nơi trên máy.

Không nên dựa vào `CLASSPATH` môi trường khi native app đã tự truyền system property khác. Với module JPMS, custom loaders hoặc plugin architecture, cần xác định **chính class loader sở hữu class**; `FindClass` không tự quét mọi JAR/module/class loader.

### 2.2. Một tiến trình không được tạo tùy tiện nhiều JVM

Đặc tả Invocation API của JDK 17 nêu rằng **không hỗ trợ việc tạo nhiều Java VMs trong cùng một tiến trình**. Trong sản phẩm nhúng JVM, kiến trúc nên có một component quản lý VM dùng chung và những thread được attach khi cần, thay vì tạo/hủy VM cho từng request.

Cũng không nên xây thiết kế dựa trên kỳ vọng có thể gọi `DestroyJavaVM` rồi lập tức tạo VM mới nhiều lần. Tính khả dụng của việc restart VM trong cùng process không được bảo đảm. Nếu cần cách ly phiên làm việc hoặc khởi động lại sạch, cân nhắc **child process** riêng.

## 3. Tìm class: `FindClass`, tên nhị phân và class loader

Hàm:

```c
jclass FindClass(JNIEnv *env, const char *name);
```

Trong C:

```c
jclass entry = (*env)->FindClass(env, "EmbeddedEntry");

if (entry == NULL) {
    /* Có lỗi, thường kèm một Java exception pending. */
    return;
}
```

Hai đoạn là **prototype và cấu trúc minh họa**, không phải chương trình độc lập.

Tên truyền vào `FindClass` là tên ở **dạng dấu gạch chéo** cho package, không phải tên có dấu chấm:

| Java binary name | `FindClass` name |
| --- | --- |
| `EmbeddedEntry` (default package) | `EmbeddedEntry` |
| `com.example.EntryPoint` | `com/example/EntryPoint` |
| `java.lang.String` | `java/lang/String` |
| `java.lang.NumberFormatException` | `java/lang/NumberFormatException` |
| `java.lang.String[]` | `[Ljava/lang/String;` |

Không được nhầm **tên class** với **chữ ký method**. Đối số `FindClass("com/example/EntryPoint")` không có dấu `L...;` bao quanh; còn trong method descriptor, một object parameter được viết `Lcom/example/EntryPoint;`.

Nếu `FindClass` không tìm/không load được lớp, nó thường trả `NULL` với một exception pending như `NoClassDefFoundError`; những lỗi khác như lỗi xác minh bytecode, initialization hoặc thiếu dependency cũng có thể xuất hiện ở những bước liên quan. Sau khi nhận `NULL`, không gọi `GetStaticMethodID(env, NULL, ...)`.

### 3.1. Local reference đến `jclass`

`FindClass` trả về `jclass`, về mặt JNI là **local reference tới một đối tượng Class** trong invocation/thread. Native host có thể gọi `DeleteLocalRef(env, entry)` khi dùng xong. Xóa local ref không có nghĩa là “hủy Java class”. Những root khác, class loader và quy tắc class unloading vẫn quyết định vòng đời class.

Nếu cần giữ class qua nhiều lời gọi lâu dài, hoặc dùng trên những native threads khác, sử dụng `NewGlobalRef` rồi `DeleteGlobalRef` ở thời điểm release đúng. Không đưa `jclass` local vào global C variable rồi dùng sau khi thread detach hoặc local frame hết hiệu lực.

### 3.2. Custom class loader và module path

Trong ứng dụng thực, một class có thể được nạp bởi plugin loader riêng; lúc đó `FindClass` từ native host không nhất thiết thấy class. Cách đáng tin cậy hơn là nhận một `jclass` hợp lệ từ Java bootstrap code, hoặc lấy Java `ClassLoader` cần thiết rồi gọi `loadClass` thông qua JNI theo đúng quyền truy cập và class-loader contract.

Phân biệt:

- `FindClass("com/example/EntryPoint")`: dạng `/` của JNI.
- `ClassLoader.loadClass("com.example.EntryPoint")`: Java binary name dùng dấu `.`.
- `Class.forName("com.example.EntryPoint", true, loader)`: yêu cầu class initialization theo API Java, với loader cụ thể.

Khi cấu hình JPMS, các option như `--module-path=...`, `--add-modules=...`, `--add-exports=...` phải dùng **dạng option=value** trong `JavaVMOption.optionString` theo Invocation API. Việc thêm module path chưa tự đảm bảo API trong module có thể truy cập được từ mã gọi; còn phải xét module readability/exports và các ràng buộc reflection nếu dùng reflection.

## 4. Tìm method: `GetStaticMethodID` và phương thức điểm vào

Khi có `jclass`, bước tiếp theo là lấy ID của phương thức cần gọi.

```c
jmethodID GetStaticMethodID(JNIEnv *env,
                            jclass clazz,
                            const char *name,
                            const char *sig);
```

Mã C:

```c
jmethodID method = (*env)->GetStaticMethodID(
    env, entry, "evaluate", "(Ljava/lang/String;)I");

if (method == NULL) {
    /* Không tìm thấy method phù hợp hoặc có exception. */
    return;
}
```

Chữ ký `(Ljava/lang/String;)I` giải nghĩa:

- `(` và `)` bao quanh danh sách parameter types.
- `Ljava/lang/String;` là một đối số kiểu `java.lang.String`.
- `I` nghĩa là kiểu trả về `int`.

Bảng descriptor thường gặp:

| Java type | Chữ ký JNI |
| --- | --- |
| `void` | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `String[]` | `[Ljava/lang/String;` |
| `int[]` | `[I` |

Ví dụ:

| Java method | Descriptor |
| --- | --- |
| `static int evaluate(String text)` | `(Ljava/lang/String;)I` |
| `static void main(String[] args)` | `([Ljava/lang/String;)V` |
| `static long add(long a, long b)` | `(JJ)J` |
| `static boolean ready()` | `()Z` |
| `int size()` (instance) | `()I` |

Không đoán descriptor bằng tên phương thức. Để kiểm tra bytecode đã biên dịch, dùng:

```bash
javap -s -p EmbeddedEntry
```

Lệnh trên hiển thị các descriptor thực sự của class. Với generics, descriptor dùng **type erasure**; không có cú pháp tổng quát như `List<String>` ở cấp JNI descriptor. Với overloaded methods, cùng tên nhưng descriptor khác sẽ chọn overload khác.

**Phân biệt static/instance:**

- `GetStaticMethodID` → `CallStaticIntMethod`, `CallStaticObjectMethod`, `CallStaticVoidMethod`, v.v. và đối tượng nhận là `jclass`.
- `GetMethodID` → `CallIntMethod`, `CallObjectMethod`, `CallVoidMethod`, v.v. và đối tượng nhận là `jobject` instance phù hợp.
- Nếu cần tự tạo instance, phải có constructor `<init>`, `GetMethodID(env, clazz, "<init>", "(...)V")` rồi `NewObject`. Không gọi `<init>` như một phương thức tĩnh.

Cần kiểm tra return value của `GetStaticMethodID`; nếu method không tồn tại, có thể có `NoSuchMethodError` pending. Việc lấy method ID cũng có thể **khởi tạo class** nếu class chưa được initialize, và Java static initializer có thể ném exception. Do đó không giả định “chỉ lookup, không Java code chạy”.

`jmethodID` **không phải local JNI reference**; không dùng `DeleteLocalRef` cho nó. Nếu cache method ID qua lifetime dài, phải đảm bảo class/class loader liên quan còn hợp lệ; trong môi trường dynamic unloading, việc sử dụng lại ID của một class đã unload là sai contract.

## 5. Gọi Java: tạo đối số, lấy kết quả và kiểm tra lỗi

Đối với `evaluate(String) : int`, chuỗi C → Java có thể viết:

```c
/* Đoạn minh họa trong native host đã có env, entry, method. */
jstring arg = (*env)->NewStringUTF(env, "21");
if (arg == NULL) {
    /* Có thể có OutOfMemoryError pending. */
    return;
}

jint value = (*env)->CallStaticIntMethod(
    env, entry, method, arg);

/* DeleteLocalRef được phép ngay cả khi Java exception đang pending. */
(*env)->DeleteLocalRef(env, arg);

if ((*env)->ExceptionCheck(env)) {
    /* Không sử dụng value. Chọn xử lý exception. */
    return;
}

printf("value=%d\n", (int)value);
```

Đây là **cấu trúc minh họa**, không phải file độc lập. `NewStringUTF` nhận chuỗi C theo **Modified UTF-8** của JNI, không phải toàn bộ UTF-8 chuẩn; chuỗi ASCII `"21"` thì tương thích. Với dữ liệu quốc tế hóa/Unicode tùy ý, phải chuyển đổi encoding đúng chuẩn hoặc dùng cách tạo String từ UTF-16; không gửi byte sequences không hợp lệ vào `NewStringUTF`.

Phương thức Java có thể trả một số `0` hợp lệ, nên không được dùng giá trị `0` của `jint` để suy ra exception. **Kiểm tra pending exception sau `CallStaticIntMethod`** khi kết quả phụ thuộc Java callback.

Nếu Java method có kiểu trả về `void`, dùng `CallStaticVoidMethod` và vẫn kiểm tra exception. Nếu method trả object, dùng `CallStaticObjectMethod`, quản lý `jobject` local và phân biệt `NULL` hợp lệ (trả Java null) với exception pending khi cần.

### 5.1. Mỗi JNI call có thể gây lỗi khác nhau

| Bước | Lỗi thường gặp | Nguyên tắc |
| --- | --- | --- |
| `JNI_CreateJavaVM` | Sai option, không có JVM phù hợp, thiếu bộ nhớ | Kiểm tra `JNI_OK` trước khi dùng `env` |
| `FindClass` | Class không hiện diện, class loader sai, dependency thiếu | Kiểm tra `NULL` và pending state |
| `GetStaticMethodID` | Sai tên/descriptor/static, class initialization lỗi | Kiểm tra `NULL`; không call với method ID không hợp lệ |
| `NewStringUTF` | Không cấp phát được String, encoding sai | Kiểm tra `NULL`, không truyền ref không hợp lệ |
| `CallStaticIntMethod` | Java callback ném bất kỳ `Throwable` | Kiểm tra `ExceptionCheck`, không dùng result khi pending |
| `ExceptionOccurred` | Trả throwable local khi có pending | Quản lý local ref; **không tự clear** pending |
| `ExceptionClear` | Chủ động bỏ pending state | Chỉ gọi khi thật sự có chính sách xử lý |
| `DestroyJavaVM` | Có thể chờ non-daemon threads; có thể thất bại | Shutdown theo trật tự, kiểm tra status |

## 6. Chương trình chạy được: C host tạo JVM, tìm lớp Java, xử lý ngoại lệ

Chương trình demo cho thấy **C chủ động gọi Java ba lần**:

- Input `"21"`: Java trả `42`, host in một kết quả bình thường.
- Input `"bad"`: Java ném `NumberFormatException`; host lấy throwable, clear pending, phân loại và in một nhãn lỗi.
- Input `"-1"`: Java ném `IllegalArgumentException`; host xử lý tương tự nhưng phân biệt đúng class.
- Với exception **không thuộc hai nhóm lỗi được công nhận**, host **không nuốt lỗi**: đặt lại throwable thành pending, để nhánh fatal in chẩn đoán rồi thoát với mã lỗi.

Ví dụ dùng Java 17 và C11, chỉ dựa trên Java standard library, JNI từ JDK và một compiler C trên Linux. Không cần native method trong Java vì Java chỉ đóng vai **module được native host gọi vào**.

### 6.1. File `EmbeddedEntry.java`

```java
public final class EmbeddedEntry {
    private EmbeddedEntry() {
        // Chỉ cung cấp API tĩnh để native host gọi.
    }

    public static int evaluate(String text) {
        int value = Integer.parseInt(text);

        if (value < 0) {
            throw new IllegalArgumentException(
                "negative numbers are not allowed");
        }

        return Math.multiplyExact(value, 2);
    }
}
```

Class này cố ý **không có `main`**. Hàm C sẽ đóng vai launcher: sau khi khởi tạo JVM, nó tìm class `EmbeddedEntry` rồi gọi `evaluate` với descriptor `(Ljava/lang/String;)I`. Chúng ta dùng `Math.multiplyExact` để một input rất lớn có thể phát sinh `ArithmeticException` do overflow; đây là exception **không được coi là lỗi parse thông thường** trong chính sách mẫu.

### 6.2. File `embed_host.c`

```c
#include <jni.h>
#include <stdio.h>

/*
 * run_once trả 1 nếu đã xử lý kết quả hoặc lỗi nghiệp vụ
 * theo chính sách đã định nghĩa. Trả 0 khi có lỗi bất ngờ.
 *
 * formatType và argumentType là local refs tới hai Class
 * đã được tìm TRƯỚC khi Java callback có thể ném.
 */
static int run_once(JNIEnv *env,
                    jclass entryClass,
                    jmethodID evaluateMethod,
                    jclass formatType,
                    jclass argumentType,
                    const char *label,
                    const char *inputText) {

    jstring javaText = (*env)->NewStringUTF(env, inputText);
    if (javaText == NULL) {
        return 0;  /* Có thể có pending OutOfMemoryError. */
    }

    jint answer = (*env)->CallStaticIntMethod(
        env, entryClass, evaluateMethod, javaText);

    /* Cho phép cleanup local ref ngay cả khi exception pending. */
    (*env)->DeleteLocalRef(env, javaText);

    if ((*env)->ExceptionCheck(env) == JNI_FALSE) {
        printf("%s=%d\n", label, (int)answer);
        return 1;
    }

    /*
     * ExceptionOccurred tạo local ref tới Throwable,
     * nhưng chưa thay đổi pending state.
     */
    jthrowable error = (*env)->ExceptionOccurred(env);
    if (error == NULL) {
        return 0;  /* Không thể phân loại an toàn. */
    }

    /*
     * Cần clear TRƯỚC khi gọi IsInstanceOf.
     * Nếu không, IsInstanceOf sẽ không được phép gọi
     * trong trạng thái pending exception.
     */
    (*env)->ExceptionClear(env);

    jboolean isFormat = (*env)->IsInstanceOf(
        env, error, formatType);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, error);
        return 0;
    }

    if (isFormat == JNI_TRUE) {
        printf("%s=NumberFormatException\n", label);
        (*env)->DeleteLocalRef(env, error);
        return 1;
    }

    jboolean isArgument = (*env)->IsInstanceOf(
        env, error, argumentType);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, error);
        return 0;
    }

    if (isArgument == JNI_TRUE) {
        printf("%s=IllegalArgumentException\n", label);
        (*env)->DeleteLocalRef(env, error);
        return 1;
    }

    /*
     * Unexpected Throwable: ném lại cùng object.
     * Main sẽ gọi ExceptionDescribe và thoát với lỗi.
     */
    (void)(*env)->Throw(env, error);
    (*env)->DeleteLocalRef(env, error);
    return 0;
}

int main(void) {
    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    /* Dấu "." là working directory khi CHẠY executable. */
    char classpathOption[] = "-Djava.class.path=.";
    JavaVMOption options[1] = {
        { .optionString = classpathOption, .extraInfo = NULL }
    };
    JavaVMInitArgs args = {
        .version = JNI_VERSION_1_8,
        .nOptions = 1,
        .options = options,
        .ignoreUnrecognized = JNI_FALSE
    };

    jint rc = JNI_CreateJavaVM(&vm, (void **)&env, &args);
    if (rc != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "JNI_CreateJavaVM failed: %d\n", (int)rc);
        return 1;
    }

    int exitCode = 1;
    jclass entryClass = NULL;
    jclass formatType = NULL;
    jclass argumentType = NULL;

    entryClass = (*env)->FindClass(env, "EmbeddedEntry");
    if (entryClass == NULL) {
        goto cleanup;
    }

    /*
     * GetStaticMethodID có thể initialize class.
     * Nếu Java static initializer lỗi, sẽ có exception.
     */
    jmethodID evaluateMethod = (*env)->GetStaticMethodID(
        env, entryClass, "evaluate", "(Ljava/lang/String;)I");
    if (evaluateMethod == NULL) {
        goto cleanup;
    }

    /*
     * Preload classes trước CallStaticIntMethod:
     * không tìm class mới khi Java exception đã pending.
     */
    formatType = (*env)->FindClass(
        env, "java/lang/NumberFormatException");
    if (formatType == NULL) {
        goto cleanup;
    }

    argumentType = (*env)->FindClass(
        env, "java/lang/IllegalArgumentException");
    if (argumentType == NULL) {
        goto cleanup;
    }

    if (!run_once(env, entryClass, evaluateMethod,
                  formatType, argumentType, "ok", "21")) {
        goto cleanup;
    }

    if (!run_once(env, entryClass, evaluateMethod,
                  formatType, argumentType, "bad", "bad")) {
        goto cleanup;
    }

    if (!run_once(env, entryClass, evaluateMethod,
                  formatType, argumentType, "negative", "-1")) {
        goto cleanup;
    }

    puts("host=completed");
    exitCode = 0;

cleanup:
    /*
     * Không có Java caller đang chờ native main.
     * Với lỗi bất ngờ, chủ native phải báo lỗi rõ ràng.
     *
     * ExceptionDescribe in stacktrace và CLEAR pending:
     * chỉ dùng tại đường fatal này, không dùng để
     * "xem cho biết" khi muốn tiếp tục propagate.
     */
    if ((*env)->ExceptionCheck(env)) {
        fprintf(stderr, "Unexpected Java exception:\n");
        (*env)->ExceptionDescribe(env);
        exitCode = 1;
    } else if (exitCode != 0) {
        fprintf(stderr, "Host stopped due to a JNI error\n");
    }

    if (argumentType != NULL) {
        (*env)->DeleteLocalRef(env, argumentType);
    }
    if (formatType != NULL) {
        (*env)->DeleteLocalRef(env, formatType);
    }
    if (entryClass != NULL) {
        (*env)->DeleteLocalRef(env, entryClass);
    }

    /*
     * Shutdown sau khi đã xử lý pending exception và refs.
     * DestroyJavaVM có thể đợi non-daemon threads khác.
     */
    rc = (*vm)->DestroyJavaVM(vm);
    if (rc != JNI_OK) {
        fprintf(stderr, "DestroyJavaVM failed: %d\n", (int)rc);
        return 1;
    }

    return exitCode;
}
```

**Điểm đáng chú ý trong mã C:**

1. C không có `System.loadLibrary` hoặc `JNIEXPORT Java_...` vì chính **C tạo VM và gọi Java**, thay vì Java tìm một JNI native method do C export.
2. `JNI_CreateJavaVM` nhận địa chỉ của `JavaVM *`, địa chỉ của `JNIEnv *` được cast sang `void **` theo chữ ký Invocation API, và `JavaVMInitArgs`.
3. Sau khi tạo VM thành công, mọi JNI calls đều đi qua `env` đúng thread. Không dùng `env` nếu startup thất bại.
4. `FindClass("EmbeddedEntry")` tìm class ở default package qua system class loader; `-Djava.class.path=.` giúp tìm `EmbeddedEntry.class` trong working directory.
5. `GetStaticMethodID` dùng đúng descriptor `(Ljava/lang/String;)I` và có thể làm class initialization xảy ra; có nhánh lỗi nếu không lấy được ID.
6. Các class dùng để phân loại exception được tìm **trước** khi gọi Java. Nếu callback ném lỗi, không gọi `FindClass` khi exception còn pending.
7. `NewStringUTF` tạo `jstring` local. `run_once` gọi `DeleteLocalRef` trước khi đọc pending state, kể cả khi callback đã ném. Đây là JNI cleanup được phép.
8. `ExceptionCheck` không tạo local ref, giúp quyết định thành công hay lỗi. Chỉ khi thật sự cần biết loại lỗi mới gọi `ExceptionOccurred`.
9. `ExceptionOccurred` tạo local `jthrowable`, nhưng pending exception vẫn còn. Vì `IsInstanceOf` không thuộc nhóm JNI functions được phép khi pending, code gọi `ExceptionClear` trước.
10. `NumberFormatException` kế thừa `IllegalArgumentException`, nên phải kiểm tra **NumberFormatException trước** để phân loại đúng. Nếu đảo thứ tự, lỗi parse cũng có thể bị in là `IllegalArgumentException`.
11. Hai loại lỗi được nhận diện đều được xử lý có chủ đích, rồi xóa local ref `error`; native host có thể tiếp tục lượt gọi khác.
12. Lỗi ngoài dự tính được `Throw` lại bằng cùng `Throwable` object; nhánh cleanup cuối nhìn thấy pending và dùng `ExceptionDescribe` để in chẩn đoán rồi clear. Một lỗi như `ArithmeticException` không bị âm thầm chuyển thành kết quả hợp lệ.
13. `DestroyJavaVM` chạy sau khi đã xử lý lỗi và dọn references. Nếu ứng dụng Java tạo thêm non-daemon threads, bước destroy có thể chờ chúng; trong app thực phải có shutdown policy.
14. Kết quả `jint` chỉ dùng khi `ExceptionCheck == JNI_FALSE`. Một số như `0` có thể là kết quả nghiệp vụ hợp lệ, không phải tín hiệu lỗi JNI.

### 6.3. Biên dịch trên Linux với JDK 17+

Đặt hai file `EmbeddedEntry.java` và `embed_host.c` trong **cùng một thư mục**, rồi chạy lệnh trong chính thư mục đó. `JAVA_HOME` phải là thư mục JDK đang dùng, chứa `include/jni.h` và `lib/server/libjvm.so`.

```bash
javac EmbeddedEntry.java

cc -std=c11 -Wall -Wextra -Wpedantic \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host

./embed_host
```

**Stdout chính xác khi ba đường ví dụ chạy thành công:**

```text
ok=42
bad=NumberFormatException
negative=IllegalArgumentException
host=completed
```

Trên đường thành công thông thường, không có Java stacktrace trên `stderr` vì hai lỗi nghiệp vụ đã được chủ native xử lý rõ ràng. Nếu VM không khởi tạo hoặc có lỗi bất ngờ, chương trình có thể in thông điệp chẩn đoán lên `stderr`, trả exit code khác 0 và **không** tạo stdout hoàn chỉnh như trên.

**Tại sao không chạy `java EmbeddedEntry`?** Class không có `main`; đây là library entrypoint cho C host. Chương trình cần khởi động là executable `./embed_host`.

**Tại sao không dùng `javac -h`?** Java source không khai báo bất kỳ phương thức `native` nào nên không cần sinh JNI exported header. C chỉ dùng `jni.h` của JDK để tạo VM và gọi các Java methods. `javac -h` chủ yếu hữu ích khi Java khai báo native methods cần implementation C export.

**Lệnh C liên kết ra sao?** `-I` tìm header JNI, `-L` tìm `libjvm.so` tại bước link, `-ljvm` link Invocation API, và `-Wl,-rpath,...` cho runtime linker biết đường tìm thư viện JVM. Trên bản phân phối Linux khác, đường `libjvm.so` có thể nằm ở vị trí khác; kiểm tra JDK layout thực tế.

**Lưu ý nền tảng:** Windows dùng `jvm.dll` và import library/cấu hình loader theo toolchain (MSVC hoặc MinGW phù hợp); macOS dùng đường thư viện và linker options của JDK/macOS; không bê nguyên `include/linux` và `-Wl,-rpath` sang nền tảng khác. Native host và JVM phải có **kiến trúc/ABI tương thích** (x64 ↔ x64, ARM64 ↔ ARM64, calling convention và compiler runtime).

### 6.4. Kiểm thử phát sinh lỗi ngoài chính sách

Để kiểm tra nhánh fatal, một tình huống là gọi `evaluate("2147483647")`. `Integer.parseInt` thành công, nhưng `Math.multiplyExact(value, 2)` ném `ArithmeticException` vì overflow.

Chỉ thay **input của lời gọi thử nghiệm trong một bản copy dùng để test** (không phải stdout mặc định của mẫu). Vì đây không phải lỗi parse hoặc số âm, `run_once` sẽ gọi `Throw(env, error)` rồi trả 0. Nhánh `cleanup` thấy exception pending, in stacktrace bằng `ExceptionDescribe` và trả exit code 1. Stacktrace (dòng/tên file tùy bản code) không được coi là stdout cố định.

Về production, một native host có thể chọn ghi exception qua logging framework của C, chuyển thành error status của một plugin manager, hoặc chủ động dừng worker/subprocess. Quan trọng là **không tiếp tục gọi Java như thể không có lỗi**.

## 7. Ngoại lệ JNI từ góc nhìn ứng dụng chủ C

### 7.1. Native method do Java gọi và native host khác nhau ở đâu?

Trong đường `Java → native method → Java`, nếu JNI code giữ exception pending rồi return, Java caller phía trên có thể quan sát exception như một `throw`.

Trong đường `native main → embedded JVM → Java method`, **không có Java caller tại điểm native main** để tự động catch. Pending state vẫn gắn với JNI thread, nhưng native host phải chọn một trong các chiến lược:

- **Recover:** lấy exception, clear, xác nhận loại lỗi cho phép rồi trả kết quả thay thế hoặc ghi status.
- **Report-and-stop:** in diagnostic (ví dụ `ExceptionDescribe` ở đường fatal), clear và kết thúc native operation với mã lỗi phù hợp.
- **Propagate to a Java layer:** nếu kiến trúc host có Java callback/điểm xử lý tương ứng, phải thiết kế đường phát lại exception bằng `Throw` và lifetime phù hợp, không chỉ return từ C `main` rồi hy vọng JVM làm thay.
- **Isolate:** đưa plugin/job Java sang process riêng; host chính nhận status/IPC, bảo vệ tính sẵn sàng trước lỗi không thể phục hồi.

Không được mặc định `ExceptionClear` nghĩa là lỗi đã được xử lý nghiệp vụ. Clear chỉ xóa **trạng thái pending**. Nếu bỏ qua nguyên nhân, dữ liệu trả về có thể không còn hợp lệ.

### 7.2. `ExceptionCheck`, `ExceptionOccurred` và `ExceptionDescribe`

| API | Trả về/tác dụng | Pending sau lời gọi | Có thêm local ref? |
| --- | --- | --- | --- |
| `ExceptionCheck(env)` | `JNI_TRUE` hoặc `JNI_FALSE` | Không đổi | Không |
| `ExceptionOccurred(env)` | `jthrowable` local hoặc `NULL` | Không đổi | Có nếu khác `NULL` |
| `ExceptionClear(env)` | Xóa pending exception | Đã clear | Không |
| `ExceptionDescribe(env)` | In throwable + stacktrace vào kênh lỗi hệ thống | **Đã clear** theo đặc tả | Không |
| `Throw(env, throwable)` | Đặt throwable object thành pending | Trở thành pending nếu thành công | Không tự tạo ref tới object đã có |
| `ThrowNew(env, exceptionClass, message)` | Tạo/đặt exception mới | Pending nếu thành công | Không phải cách “in log” vô hại |

Với một lỗi bất kỳ, mẫu kiểm tra nhanh là:

```c
if ((*env)->ExceptionCheck(env)) {
    /* Cleanup bằng những JNI calls được cho phép. */
    /* Sau đó return hoặc xử lý có chủ đích. */
}
```

Nếu cần phân loại:

```c
jthrowable error = (*env)->ExceptionOccurred(env);
if (error != NULL) {
    (*env)->ExceptionClear(env);

    /* Giờ mới được gọi JNI API bình thường để inspect error. */

    (*env)->DeleteLocalRef(env, error);
}
```

Hai đoạn trên là **cấu trúc minh họa trong native host**, không phải file độc lập. `ExceptionOccurred` **không clear** pending, còn `DeleteLocalRef(error)` chỉ xóa handle local, **không xóa Java exception** đang pending.

### 7.3. Những JNI calls nào dùng được khi pending?

Khi pending exception, phần lớn các JNI APIs thông thường **không được gọi**. Những thao tác được đặc tả cho phép bao gồm:

- `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`.
- `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`.
- `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- `MonitorExit`, `PushLocalFrame`, `PopLocalFrame`, `DetachCurrentThread`.

Đó là lý do mẫu chạy **preload exception classes trước Java callback** và chỉ gọi `IsInstanceOf` sau `ExceptionClear`. Những API như `FindClass`, `GetStaticMethodID`, `NewStringUTF` hoặc `CallStaticIntMethod` không nằm trong nhóm an toàn trong lúc pending.

Nếu JNI callback đã phát sinh exception, **không dùng giá trị trả về** của `CallStaticIntMethod` cho nghiệp vụ dù nó tình cờ có một bit pattern giống dữ liệu hợp lệ. Dọn JNI resources trước rồi xử lý exception theo policy.

### 7.4. Khi class initialization ném exception

Một case hay bị bỏ sót là class có `static { ... }` thực hiện I/O hoặc ném lỗi. `GetStaticMethodID` có thể kích hoạt initialization nếu class chưa được initialize. Nếu initializer ném, JNI có thể gặp `ExceptionInInitializerError` hoặc lỗi liên quan; lần truy cập sau còn có thể gặp `NoClassDefFoundError` do class ở trạng thái initialization thất bại.

Đừng chỉ kiểm tra `FindClass != NULL` rồi tin rằng mọi method lookup sẽ thành công. Kiểm tra từng bước và quyết định liệu plugin/module đó cần bị đánh dấu unhealthy hay có thể tiếp tục chạy các thành phần khác.

### 7.5. Không “log” bằng `ExceptionDescribe` trước khi muốn ném lại

`ExceptionDescribe` **clear pending exception** sau khi in. Nếu native host muốn giữ object lỗi và sau đó ném lại, phải nắm rõ thao tác này; gọi `ExceptionDescribe` rồi tiếp tục như thể exception vẫn pending là sai.

Nếu muốn in log mà vẫn giữ throwable, cần policy có chủ đích: lấy `ExceptionOccurred` (local ref), clear, gọi API Java để lấy message/stacktrace khi không pending, sau đó `Throw` lại nếu cần. Quy trình này có thêm nguồn phát sinh exception trong lúc logging và phải được xử lý; trong đường fatal, in và dừng thường đơn giản hơn.

## 8. Vòng đời references, JNIEnv, threads và shutdown

### 8.1. Local references trong vòng lặp dài của C host

Native host có thể thực hiện hàng trăm nghìn lượt gọi Java trong **cùng một thread đã attach**. Local references được tạo ra trong ngữ cảnh Invocation API không nên để tích lũy đến tận khi thread detach hoặc JVM shutdown.

Với mỗi vòng lặp:

```c
/* Ví dụ cấu trúc trong một host đã có env và entryClass. */
for (int i = 0; i < count; ++i) {
    jstring value = (*env)->NewStringUTF(env, "x");
    if (value == NULL) {
        break; /* Xử lý pending exception sau cleanup. */
    }

    /* Dùng value cho JNI method call... */
    (*env)->DeleteLocalRef(env, value);
}
```

Đây là **mã minh họa**; không phải file độc lập. Nếu một iteration tạo rất nhiều object, có thể dùng `PushLocalFrame`/`PopLocalFrame`; phải pop ở cả đường success và đường exception hợp lệ. Local refs chỉ có hiệu lực trong thread tạo chúng, không truyền `jobject` local sang pthread khác.

### 8.2. Native host nhiều thread: `AttachCurrentThread` và `DetachCurrentThread`

Khi JVM đã tạo, một worker thread C muốn sử dụng JNI phải attach:

```c
/*
 * Minh họa: vm đã hợp lệ; đây là hàm C chạy trên
 * một OS thread khác với thread tạo JVM.
 */
JNIEnv *threadEnv = NULL;
jint status = (*vm)->AttachCurrentThread(
    vm, (void **)&threadEnv, NULL);

if (status == JNI_OK) {
    /* Dùng threadEnv CHỈ trong thread này. */

    /* Đảm bảo không còn Java methods trên call stack
       và dọn local/global references theo policy. */
    (*vm)->DetachCurrentThread(vm);
}
```

`JNIEnv *` được trả cho thread A **không thể** dùng ở thread B. Nếu nhiều host workers cần truy cập JVM, lưu `JavaVM *` để mỗi thread tự attach và lấy `JNIEnv *`. Native-created thread phải detach trước khi kết thúc khi dùng `AttachCurrentThread`, theo quy tắc Invocation API. Không detach thread khi nó vẫn có Java methods trên stack.

Nếu cần chia sẻ Java object giữa threads hoặc giữ qua nhiều công việc, tạo **global JNI reference** bằng `NewGlobalRef` trong điều kiện hợp lệ và xóa bằng `DeleteGlobalRef` khi không còn dùng. Một local `jclass`/`jobject` không trở thành an toàn chỉ vì sao chép giá trị pointer sang vùng heap native.

### 8.3. Shutdown một JVM nhúng

`DestroyJavaVM` kết thúc JVM theo Invocation API; nó có thể **chờ non-daemon Java threads và attached native threads khác kết thúc**. Nếu ứng dụng Java đã khởi động thread pool/timer/service non-daemon và không shutdown, native host có thể chờ lâu hoặc vô hạn.

Checklist shutdown thực tế:

1. Ngừng nhận các lệnh gọi Java mới và đưa host vào trạng thái stopping.
2. Chờ hoặc hủy các công việc đang chạy theo contract riêng; không free native allocations còn đang được callback dùng.
3. Báo Java layer shutdown executors/sockets/timers nếu có.
4. Dọn các JNI global refs và local refs không cần nữa.
5. Đảm bảo native workers đã detach đúng quy tắc; xử lý mọi pending exceptions trước khi kết thúc.
6. Gọi `DestroyJavaVM` ở thread/phạm vi hợp lệ, kiểm tra return code.
7. Không tiếp tục gọi JNI qua `env` hoặc `vm` sau khi VM đã bị destroy.

Trong một native app lớn, tài liệu JNI còn lưu ý trên một số hệ điều hành, việc khởi tạo JVM từ **primordial process thread** có những caveat về stack và thread handling; có thể nên tạo một dedicated thread để khởi tạo/điều phối VM. Ví dụ tối giản dùng `main` cho dễ hiểu; production cần xem xét platform-specific guidance.

## 9. Khi nào gọi điểm vào `main(String[])` thay vì API riêng?

Nếu Java module được thiết kế như một ứng dụng độc lập, native host có thể tìm:

```c
jmethodID mainMethod = (*env)->GetStaticMethodID(
    env, mainClass, "main", "([Ljava/lang/String;)V");
```

Đây là **mã minh họa**, chưa có `mainClass` hoặc tham số `String[]`. Muốn gọi đúng, native host phải tạo một `jobjectArray` kiểu `String[]` qua `NewObjectArray` (thường cần `FindClass("java/lang/String")` trước), set các chuỗi bằng `SetObjectArrayElement`, gọi `CallStaticVoidMethod`, rồi cleanup local references.

Tuy nhiên, việc gọi `main` của ứng dụng Java từ native host có thể kéo theo khởi động background threads, cấu hình global và `System.exit()` nếu code Java tự gọi nó. `System.exit()` có thể kết thúc cả **tiến trình native host**, điều thường không mong muốn đối với plugin host/server.

Một API Java riêng như `public static int evaluate(String)` hoặc một interface service có create/start/stop rõ ràng thường dễ nhúng, kiểm thử và quản lý shutdown hơn so với gọi một Java `main` tổng quát.

Nếu yêu cầu thật sự là dùng Java launcher thay vì nhúng in-process, nên cân nhắc spawn tiến trình `java -cp ... Main` riêng và giao tiếp bằng IPC/HTTP/gRPC. Lúc đó boundary là **process**, không phải JNI call, và native host không phải quản lý `JNIEnv *`.

## 10. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/cách sửa |
| --- | --- | --- |
| `JNI_CreateJavaVM` trả mã âm | Sai JVM option, architecture, môi trường/heap | Kiểm tra JDK, `JAVA_HOME`, options, return code |
| Chạy `./embed_host` báo không tìm thấy `libjvm.so` | Dynamic loader không thấy JVM shared library | Kiểm tra RPATH, `libjvm.so` và link command |
| `FindClass("EmbeddedEntry") == NULL` | Không có class trong classpath hay working dir sai | Xác minh `EmbeddedEntry.class` và `-Djava.class.path=.` |
| `FindClass("com.example.Foo")` thất bại | Dùng dấu chấm thay dấu gạch chéo | Dùng `com/example/Foo` |
| `GetStaticMethodID` trả `NULL` | Descriptor sai, method không static, method không tồn tại | `javap -s -p`, sửa tên và descriptor |
| Method lookup ném `ExceptionInInitializerError` | Class static initializer lỗi | Chẩn đoán nguyên nhân gốc, không dùng method ID |
| `CallStaticIntMethod` trả số “lạ” | Method có exception pending; kết quả không hợp lệ | `ExceptionCheck` trước khi sử dụng `jint` |
| Sau callback lỗi, `FindClass` tiếp theo crash hoặc bị CheckJNI cảnh báo | Có pending exception | Cleanup; clear chỉ khi có policy recover |
| `ExceptionOccurred` dùng trong loop mà không xóa ref | Tích lũy JNI local references | `DeleteLocalRef` từng handle |
| Thấy `NumberFormatException` nhưng bị gắn nhãn `IllegalArgumentException` | Hai class có quan hệ kế thừa | Test subclass cụ thể trước superclass |
| `ExceptionDescribe` xong không còn exception | API này **clear pending state** | Chỉ dùng cho chẩn đoán/fatal; rethrow có chủ đích |
| Native host bị treo khi `DestroyJavaVM` | Java non-daemon threads chưa dừng | Shutdown Java executors/workers trước |
| Dùng `JNIEnv *` của main trên worker khác | `JNIEnv` thread-local | `AttachCurrentThread` riêng và detach khi kết thúc |
| Thông báo `NoClassDefFoundError` dù JAR có class | Loader/module graph không nhìn thấy, dependency lỗi | Chọn loader đúng, classpath/module path và dependency |
| Cất `jclass` local vào static C variable | Reference mất hiệu lực/khác thread | `NewGlobalRef` hoặc lookup đúng scope |
| Native host và JVM khác kiến trúc | Link/load/JVM startup thất bại | Cùng ABI, architecture và thư viện JDK |

Để debug, có thể thêm JVM startup options như `-verbose:class` hoặc dùng JDK logging phù hợp, nhưng **không bật log vô tội vạ trong ví dụ có stdout xác định**. Với lỗi class loading, ghi thêm working directory, classpath đã cấu hình và exception stacktrace từ đường fatal thường đủ giúp tìm nguyên nhân.

## 11. Thiết kế native host an toàn và dễ vận hành

### 11.1. Ranh giới tin cậy

Khi C host nhúng JVM trong **cùng tiến trình**, lỗi native memory, native crash hoặc `abort()` có thể làm sập cả JVM lẫn host. Ngược lại, Java code được load có thể đọc tài nguyên trong process theo quyền hệ điều hành của host; JNI không phải sandbox cho code không tin cậy.

Không cho input bên ngoài tùy ý quyết định class name, classpath, JVM options, method name hoặc JNI descriptor mà không qua **allowlist** và validation. Khi cần chạy plugin không tin cậy, dùng tách process với quyền hạn/cgroups/IPC phù hợp thay vì tin rằng `FindClass` hoặc class loader tự cách ly đủ an toàn.

### 11.2. Định nghĩa contract lỗi trước khi code

Một native host thường có API C riêng, ví dụ trả:

```c
typedef enum {
    HOST_OK = 0,
    HOST_BAD_INPUT = 1,
    HOST_JAVA_FAILURE = 2,
    HOST_VM_FAILURE = 3
} HostStatus;
```

Đây là **ví dụ kiểu trả về cho API sản phẩm**, chưa phải chương trình đầy đủ. Bảng ánh xạ nên nói rõ:

- Java `NumberFormatException` → `HOST_BAD_INPUT` hoặc chi tiết lỗi parse.
- Java `IllegalArgumentException` → `HOST_BAD_INPUT` nếu input không hợp lệ theo contract.
- Java `OutOfMemoryError`/`LinkageError`/exception khác → `HOST_JAVA_FAILURE`, có logging và chính sách phục hồi cụ thể, không tự coi là lỗi người dùng.
- Lỗi khi tạo JVM → `HOST_VM_FAILURE`.
- Đường thành công → dữ liệu hợp lệ + `HOST_OK`, không trộn trạng thái lỗi vào miền số nếu số âm/0 có thể là kết quả hợp lệ.

Với API production, có thể cần lưu exception type/message/stacktrace dưới dạng dữ liệu được kiểm soát (không vô tình lộ bí mật), thay vì `ExceptionDescribe` trực tiếp ra `stderr`.

### 11.3. Quản lý class caching và garbage collection

Cache `jclass` có thể giúp tránh lookup lặp lại, nhưng một `jclass` local không nên sống qua các JNI thread hoặc detach. Nếu giữ lâu, tạo global reference; method ID không cần `DeleteLocalRef` nhưng phải ràng buộc với lifetime của class/class loader hợp lệ.

Java objects được JVM quản lý, C host **không `free(jobject)`**. Native buffers do `malloc` phải `free` đúng allocator; JNI buffers từ `GetStringUTFChars` phải `ReleaseStringUTFChars`; các resources có các owner và hàm release khác nhau.

### 11.4. Đồng thời và khả năng phục vụ

Nếu host có nhiều native worker threads:

- Mỗi thread cần `JNIEnv *` của chính nó, không chia sẻ một `JNIEnv *`.
- Java entrypoint phải thread-safe hoặc có cơ chế đồng bộ; không giả định vì được gọi từ C thì Java method không có race.
- Chọn concurrency cap và timeout cho Java callbacks; một Java method có thể block, khiến native worker và JNI invocation đều giữ tài nguyên.
- Không destroy VM khi các worker vẫn gọi JNI hoặc đang giữ Java refs.
- Tạo lớp bootstrap rõ ràng quản lý initialize/shutdown, thread attachment, local/global refs và reporting; tránh rải `JNI_CreateJavaVM` khắp ứng dụng.

## 12. Kiểm thử và đánh giá tính đúng

Những case tối thiểu cần xác nhận:

1. **Tạo JVM:** VM startup với classpath đúng, `JNI_CreateJavaVM == JNI_OK`, `env != NULL`; đường lỗi startup không dùng `env`.
2. **Class lookup:** `FindClass("EmbeddedEntry")` thành công; đổi tên class sai hoặc chạy sai working directory phải đi vào nhánh lỗi thay vì dereference `NULL`.
3. **Method descriptor:** `javap -s -p EmbeddedEntry` xác nhận `evaluate(String) : int` có `(Ljava/lang/String;)I`; method ID khác `NULL`.
4. **Success:** input `"21"` → `42`, host ghi `ok=42`.
5. **Parse exception:** input `"bad"` → `NumberFormatException`, host chủ động clear và phân loại.
6. **Value-policy exception:** input `"-1"` → `IllegalArgumentException`, không nhầm với `NumberFormatException`.
7. **Unexpected Java exception:** input `"2147483647"` → `ArithmeticException` từ `Math.multiplyExact`, đường fatal in lỗi và exit nonzero.
8. **String reference cleanup:** mọi `jstring` do `NewStringUTF` trả về được `DeleteLocalRef` sau khi dùng; cả khi callback ném exception.
9. **Throwable cleanup:** local `jthrowable` được `DeleteLocalRef` sau phân loại/rethrow; không dùng sau khi xóa.
10. **Class references:** `entryClass` và exception class references được delete trước shutdown; `jmethodID` không bị coi là local ref.
11. **Shutdown:** `DestroyJavaVM` được gọi đúng một lần sau cleanup; không còn Java non-daemon workers chờ vô hạn.
12. **Thread scope:** nếu thêm native worker thread, phải attach, lấy `JNIEnv *` mới và detach; không dùng JNI env main trong worker.
13. **Deployment:** thử đúng kiến trúc/ABI trên Linux target; kiểm tra runtime loader tìm thấy `libjvm.so`.
14. **Security:** input/classpath/option của native host phải được kiểm soát và không cho plugin không tin cậy có quyền native trong cùng process.

Với các ứng dụng lớn, bổ sung fault injection (lookup lỗi, JVM option sai, callback Java ném ngoại lệ bất ngờ), native memory leak detection và JVM/native thread profiling. Không chỉ kiểm tra stdout mà còn kiểm tra exit code, `stderr` và việc các resources được release đúng lúc.

## 13. Checklist trước khi tích hợp JNI Invocation API

- Native host đã quyết định dùng **embedded JVM in-process** thay vì spawn Java process chưa?
- Có chính xác **một nơi** chịu trách nhiệm tạo/đóng JVM và sở hữu các startup options không?
- Tên class trong `FindClass` là dạng slash, classpath/module loader phù hợp chưa?
- Method ID đã dùng đúng static/instance API và descriptor đã được đối chiếu qua `javap -s` chưa?
- Các `jobject` arguments được tạo hợp lệ, encoding đúng và local refs được dọn sau khi dùng chưa?
- Sau Java callback, code có kiểm tra pending exception **trước khi sử dụng giá trị trả về** không?
- Nếu gọi `ExceptionOccurred`, local `jthrowable` có được dọn và pending được xử lý có chủ đích không?
- Có tránh `FindClass`, `IsInstanceOf` và phần lớn JNI functions khi exception vẫn pending không?
- Đường fatal có log/exit status rõ ràng, không mặc định Java sẽ bắt exception thay C `main` không?
- Có chính sách shutdown cho Java executors và native workers để `DestroyJavaVM` không chờ vô hạn không?
- Mỗi native thread có `JNIEnv *` đúng thread, local/global refs và lifetime rõ ràng không?
- Có kế hoạch triển khai thư viện JVM cùng ABI và cấu hình loader trên từng hệ điều hành không?

**Quy tắc ghi nhớ:** trong ứng dụng nhúng JVM, C là bên chủ động **tạo VM → tìm lớp → tìm method → gọi Java → xử lý pending exception → dọn references → shutdown**. Đừng coi `FindClass` là tìm kiếm mọi class loader, đừng đoán method descriptor, và đừng dùng tiếp JNI bình thường khi Java callback vừa ném ngoại lệ. Cần một *error policy* minh bạch ở ranh giới native host/Java, vì C không tự có `try/catch` Java.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 17 — JNI Invocation API: JNI_CreateJavaVM, AttachCurrentThread, DestroyJavaVM](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Oracle Java SE 17 — JNI Functions: FindClass, GetStaticMethodID, CallStaticIntMethod, ExceptionCheck, ExceptionOccurred](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle Java SE 17 — JNI Design Overview: exception handling, references và garbage collection](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — javap để kiểm tra bytecode và descriptors](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
