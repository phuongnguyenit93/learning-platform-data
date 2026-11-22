# Gọi phương thức đối tượng, static và phương thức không đa hình từ JNI

> **Ngữ cảnh:** Java Advance → Native Interoperability → Gọi Java từ JNI. Bài này giải thích cách mã C/C++ dùng Java Native Interface (JNI) để gọi **instance method**, **static method** và **nonvirtual instance method** của Java, trong đó sự khác nhau quan trọng nhất là cách chọn phương thức sẽ thực thi.

## 1. Bài toán và ba kiểu gọi

JNI cho phép mã native đang chạy trong JVM truy cập đối tượng/lớp Java và gọi phương thức Java thông qua bảng hàm của `JNIEnv`. Trong mã C, ba họ API quan trọng là:

- `Call<Type>Method`: gọi **phương thức đối tượng** qua một `jobject`. Với phương thức instance có thể override, JVM áp dụng **dynamic dispatch** dựa trên kiểu thực của đối tượng.
- `CallStatic<Type>Method`: gọi **phương thức `static`** qua `jclass`. Không có receiver `jobject` và không có dynamic dispatch. Phương thức `static` của lớp con có thể **hide** (che khuất), nhưng không override, phương thức `static` cùng tên của lớp cha.
- `CallNonvirtual<Type>Method`: gọi **phương thức đối tượng theo lớp được chỉ định tường minh** bằng một `jclass` và `jmethodID` lấy từ lớp đó; bỏ qua cơ chế chọn override ở lớp con. Cách này hữu ích khi cố ý gọi phần triển khai của lớp cha trên một đối tượng lớp con.

`<Type>` trong tên API là **kiểu kết quả Java**: `Object`, `Void`, `Boolean`, `Byte`, `Char`, `Short`, `Int`, `Long`, `Float` hoặc `Double`. Ví dụ một phương thức trả `String` dùng `CallObjectMethod` và nhận kết quả kiểu JNI `jobject` (có thể ép sang `jstring`); phương thức trả `int` dùng `CallIntMethod` nhận `jint`; phương thức trả `void` dùng `CallVoidMethod`.

**Từ C vào Java** khác với **Java gọi hàm native C**: Java phải khai báo `native` và load thư viện để vào C; còn trong hàm native đó, C có thể gọi ngược phương thức Java bằng ba họ JNI API kể trên.

## 2. Bảng đối chiếu cách chọn phương thức

| Yếu tố | `CallObjectMethod` / `Call<Type>Method` | `CallStaticObjectMethod` / `CallStatic<Type>Method` | `CallNonvirtualObjectMethod` / `CallNonvirtual<Type>Method` |
|---|---|---|---|
| Phương thức Java | Instance, không `static` | `static` | Instance, không `static` |
| Receiver JNI | `jobject obj` | `jclass clazz` | `jobject obj` **và** `jclass clazz` |
| Lấy ID bằng | `GetMethodID` | `GetStaticMethodID` | `GetMethodID` trên chính `clazz` muốn chọn |
| Quy tắc chọn implementation | Dispatch theo lớp thực của đối tượng khi phương thức có thể override | Chọn phương thức `static` theo lớp/method ID | Chọn implementation theo lớp `clazz` chỉ định, bỏ qua override ở lớp con |
| Ví dụ tương ứng | `receiver.greet("Lan")` | `Parent.kind()` | Gần với ý định gọi `Parent`'s implementation trên `Child`; trong Java thông thường có thể gặp khi gọi `super.greet(...)` |
| Khi nào phù hợp | Callback vào đối tượng Java, polymorphism | Gọi hàm tiện ích/factory/cấu hình tĩnh | Cố ý gọi bản triển khai của lớp cha; một số tình huống default interface method |

Hình dung một đối tượng thật sự thuộc `Child extends Parent`, trong đó `Child` override `greet` và cả hai lớp khai báo `static kind`:

```text
                 receiver = new Child()
                           |
          +----------------+-------------------+
          |                |                   |
 CallObjectMethod   CallNonvirtualObjectMethod CallStaticObjectMethod
 (receiver, id)     (receiver, Parent, id)      (Parent, staticId)
          |                |                   |
 Child.greet()      Parent.greet()             Parent.kind()
                                           
 CallStaticObjectMethod(Child, childStaticId) -> Child.kind()
```

**Quan trọng:** `CallNonvirtual` vẫn cần **đối tượng thật** làm receiver. Nó không tạo đối tượng mới và không biến phương thức thành `static`. Tham số `clazz` quyết định phần triển khai instance cần gọi.

## 3. Lookup: `jclass`, `jmethodID` và JNI descriptor

Cần tìm đúng **lớp** và **method ID** trước khi gọi:

```c
jclass parentClass = (*env)->FindClass(env, "JniCallsDemo$Parent");

jmethodID instanceId = (*env)->GetMethodID(
    env, parentClass, "greet",
    "(Ljava/lang/String;)Ljava/lang/String;");

jmethodID staticId = (*env)->GetStaticMethodID(
    env, parentClass, "kind",
    "()Ljava/lang/String;");
```

Đây là **trích đoạn minh họa**, giả định `env` và các lớp Java tồn tại và mọi bước đều thành công; mã chạy đầy đủ và kiểm tra lỗi nằm ở mục 5.

- `jclass` là reference đến đối tượng `Class` của Java, không đồng nghĩa với đối tượng instance. `FindClass` nhận **tên nhị phân dạng JNI**: package dùng `/` (ví dụ `com/example/Parent`), lớp nested dùng `$` (ví dụ `JniCallsDemo$Parent`).
- `jmethodID` là định danh phương thức trong JVM. Nó **không phải** `jobject` và không được giải phóng bằng `DeleteLocalRef`. `GetMethodID` tìm phương thức **instance**, `GetStaticMethodID` tìm phương thức **static**.
- Lookup phải khớp đồng thời **tên và descriptor**; lớp có overload `greet(String)` và `greet(int)` là hai phương thức khác nhau.
- `GetMethodID` và `GetStaticMethodID` có thể kích hoạt **khởi tạo lớp** nếu chưa khởi tạo. Lookup thất bại trả `NULL` và thường đặt Java exception chờ xử lý (ví dụ `NoSuchMethodError`, `ExceptionInInitializerError`).

### Cách đọc descriptor

Descriptor `(Ljava/lang/String;)Ljava/lang/String;` có nghĩa: tham số là `java.lang.String`, kết quả là `java.lang.String`. Phần trước dấu `)` là danh sách tham số, phần sau là kiểu trả về.

| Kiểu Java | Descriptor |
|---|---|
| `boolean`, `byte`, `char`, `short` | `Z`, `B`, `C`, `S` |
| `int`, `long`, `float`, `double` | `I`, `J`, `F`, `D` |
| `void` (chỉ làm kiểu trả về) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

Ví dụ: `int sum(int a, int b)` có descriptor `(II)I`; `void log(String s, boolean enabled)` là `(Ljava/lang/String;Z)V`; `String kind()` là `()Ljava/lang/String;`. Trong terminal sau khi `javac`, chạy `javap -p -s JniCallsDemo` hoặc kiểm tra class nested để xem descriptor do compiler xuất ra. Khi Java khai báo native method, dùng `javac -h .` sinh **JNI header đúng tên hàm C**; không tự đoán cách mã hóa tên khi có package, dấu gạch dưới hay overload.

## 4. Cú pháp C và C++: nhìn giống nhau nhưng khác receiver

Các ví dụ dùng **JNI C API**, trong đó `JNIEnv *env` là con trỏ đến bảng hàm và lời gọi có dạng:

```c
(*env)->CallObjectMethod(env, receiver, instanceId, argument);
(*env)->CallStaticObjectMethod(env, parentClass, staticId);
(*env)->CallNonvirtualObjectMethod(
    env, receiver, parentClass, instanceId, argument);
```

Nếu viết bằng **C++ JNI API**, cú pháp tương ứng là:

```cpp
env->CallObjectMethod(receiver, instanceId, argument);
env->CallStaticObjectMethod(parentClass, staticId);
env->CallNonvirtualObjectMethod(
    receiver, parentClass, instanceId, argument);
```

Sự khác nhau trên là cú pháp wrapper JNI của C/C++; **quy tắc dynamic/static/nonvirtual dispatch vẫn giống nhau**. Không trộn `(*env)->...` kiểu C với `env->...` kiểu C++ trong cùng tệp.

Trong một phương thức native **static**, tham số JNI thứ hai là `jclass` của lớp khai báo native method; với phương thức native **instance**, tham số thứ hai là `jobject thiz`. Các tham số Java được chuyển tiếp sau hai tham số JNI đầu tiên. `JNIEnv *` chỉ hợp lệ cho thread đang sở hữu nó; không chia sẻ nó sang thread khác.

## 5. Ví dụ hoàn chỉnh chạy được: cả ba cách gọi trên cùng một đối tượng

Ví dụ có `Parent` và `Child`. `Child.greet(String)` **override** `Parent.greet(String)`, còn `Child.kind()` **hide** `Parent.kind()`. Một hàm JNI native `inspect` gọi bốn trường hợp, trả mảng `String[]` để Java in ra kết quả.

**Yêu cầu:** JDK 17+ và trình biên dịch C tạo shared library cho đúng hệ điều hành/CPU. Lệnh build dưới đây dành cho **Linux với GCC**; `JAVA_HOME` phải trỏ tới thư mục JDK.

### 5.1. Tệp Java: `JniCallsDemo.java`

```java
public class JniCallsDemo {
    static {
        System.loadLibrary("jni_calls");
    }

    public static class Parent {
        public String greet(String name) {
            return "Parent hello " + name;
        }

        public static String kind() {
            return "Parent static";
        }
    }

    public static class Child extends Parent {
        @Override
        public String greet(String name) {
            return "Child hello " + name;
        }

        public static String kind() {
            return "Child static";
        }
    }

    private static native String[] inspect(Parent receiver, String name);

    public static void main(String[] args) {
        String[] output = inspect(new Child(), "Lan");

        System.out.println("virtual = " + output[0]);
        System.out.println("nonvirtual = " + output[1]);
        System.out.println("static Parent = " + output[2]);
        System.out.println("static Child = " + output[3]);
    }
}
```

Dù tham số `receiver` khai báo kiểu `Parent`, ở runtime nó trỏ tới **`new Child()`**. Đó là điểm cần quan sát khi so sánh virtual và nonvirtual.

### 5.2. Sinh header JNI

```bash
javac -encoding UTF-8 -h . JniCallsDemo.java
```

Lệnh này tạo `JniCallsDemo.class`, hai class nested, và `JniCallsDemo.h`. Với native method `static` trên lớp `JniCallsDemo`, header mô tả hàm C tương ứng với tham số đầu là `JNIEnv *`, tham số thứ hai là `jclass`, tiếp theo là `jobject` (đối tượng `Parent`/`Child`) và `jstring` (tên `Lan`).

### 5.3. Tệp C: `JniCallsDemo.c`

```c
#include <jni.h>
#include "JniCallsDemo.h"

JNIEXPORT jobjectArray JNICALL Java_JniCallsDemo_inspect(
        JNIEnv *env, jclass owner, jobject receiver, jstring name) {
    (void) owner;

    // Tên binary của lớp nested dùng dấu '$'.
    jclass parentClass = (*env)->FindClass(env, "JniCallsDemo$Parent");
    if (parentClass == NULL) return NULL;

    jclass childClass = (*env)->FindClass(env, "JniCallsDemo$Child");
    if (childClass == NULL) return NULL;

    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass == NULL) return NULL;

    // Instance method: String greet(String).
    jmethodID greetId = (*env)->GetMethodID(
            env, parentClass, "greet",
            "(Ljava/lang/String;)Ljava/lang/String;");
    if (greetId == NULL) return NULL;

    // Hai static method có cùng tên nhưng thuộc hai lớp khác nhau.
    jmethodID parentKindId = (*env)->GetStaticMethodID(
            env, parentClass, "kind", "()Ljava/lang/String;");
    if (parentKindId == NULL) return NULL;

    jmethodID childKindId = (*env)->GetStaticMethodID(
            env, childClass, "kind", "()Ljava/lang/String;");
    if (childKindId == NULL) return NULL;

    // 1) Virtual: receiver là Child -> Child.greet được chọn.
    jstring virtualResult = (jstring)(*env)->CallObjectMethod(
            env, receiver, greetId, name);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // 2) Nonvirtual: chỉ định Parent -> Parent.greet được chọn.
    jstring nonvirtualResult = (jstring)(*env)->CallNonvirtualObjectMethod(
            env, receiver, parentClass, greetId, name);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // 3) Static: không cần receiver; dùng jclass và static method ID.
    jstring parentStaticResult = (jstring)(*env)->CallStaticObjectMethod(
            env, parentClass, parentKindId);
    if ((*env)->ExceptionCheck(env)) return NULL;

    jstring childStaticResult = (jstring)(*env)->CallStaticObjectMethod(
            env, childClass, childKindId);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // Gom bốn kết quả thành Java String[].
    jobjectArray output = (*env)->NewObjectArray(
            env, 4, stringClass, NULL);
    if (output == NULL) return NULL;

    (*env)->SetObjectArrayElement(env, output, 0, virtualResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    (*env)->SetObjectArrayElement(env, output, 1, nonvirtualResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    (*env)->SetObjectArrayElement(env, output, 2, parentStaticResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    (*env)->SetObjectArrayElement(env, output, 3, childStaticResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // Local JNI references tự được giải phóng khi native method kết thúc.
    return output;
}
```

Đây là một hàm JNI **hoàn chỉnh** dành cho ví dụ này. Nếu `FindClass`, `GetMethodID`, `GetStaticMethodID`, `NewObjectArray` hoặc Java method ném exception, JNI để exception ở trạng thái **pending** và hàm C trả về, để JVM chuyển tiếp exception về Java. Không nên tiếp tục gọi các API JNI tùy ý khi đang có exception pending.

Trong ví dụ ngắn, các local references (ba `jclass`, bốn `jstring`, mảng kết quả) được dọn khi lời gọi native kết thúc. Khi viết **vòng lặp native dài**, cần `DeleteLocalRef` hoặc quản lý local frame để không tích lũy local references.

### 5.4. Biên dịch thư viện native và chạy

```bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjni_calls.so JniCallsDemo.c

java -Djava.library.path=. JniCallsDemo
```

Trên **JDK 24+**, nên cấp quyền native access tường minh cho ứng dụng chạy trên classpath, tránh cảnh báo về restricted native access:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniCallsDemo
```

**stdout bình thường:**

```text
virtual = Child hello Lan
nonvirtual = Parent hello Lan
static Parent = Parent static
static Child = Child static
```

Các dòng chứng minh ba quy tắc:

1. `CallObjectMethod` nhận `greetId` tìm từ `Parent` nhưng **gọi `Child.greet`** vì receiver thực tế là `Child`.
2. `CallNonvirtualObjectMethod` nhận **cùng** receiver và `greetId`, bổ sung `parentClass` nên **gọi `Parent.greet`**.
3. Hai `CallStaticObjectMethod` dùng hai cặp `jclass` + `jmethodID` riêng, lần lượt gọi `Parent.kind` và `Child.kind`; không có override cho phương thức `static`.

Trên macOS và Windows, cần build `.dylib`/`.dll` bằng toolchain và đường dẫn header JNI tương ứng (macOS: `include/darwin`; Windows: `include/win32`). Tên thư viện logic trong Java vẫn là `jni_calls`; JVM ánh xạ tên này sang tên file theo hệ điều hành.

## 6. Cơ chế dispatch: vì sao một method ID lại cho hai kết quả?

Giả sử mã Java tương đương:

```java
JniCallsDemo.Parent p = new JniCallsDemo.Child();
System.out.println(p.greet("Lan"));                  // Child hello Lan
System.out.println(JniCallsDemo.Parent.kind());       // Parent static
System.out.println(JniCallsDemo.Child.kind());        // Child static
```

Đây là **trích đoạn minh họa**, không phải chương trình độc lập. Đối với lời gọi instance thông thường, Java chọn implementation dựa vào lớp thực tế khi phương thức được override. Với `static`, tên lớp được xác định theo reference biên dịch/method ID, còn gọi nonvirtual trong JNI yêu cầu **lựa chọn implementation bằng tham số `jclass`**.

Đối chiếu trực tiếp:

```c
// Receiver có runtime class là Child.
(*env)->CallObjectMethod(env, receiver, greetId, name);
// => Child.greet("Lan"), dù greetId lấy từ Parent.

// Bỏ qua Child override, chọn Parent implementation.
(*env)->CallNonvirtualObjectMethod(
    env, receiver, parentClass, greetId, name);
// => Parent.greet("Lan").
```

**Không thay `parentClass` bằng `GetObjectClass(receiver)` khi mục tiêu là gọi lớp cha.** `GetObjectClass(receiver)` trả runtime class `Child`. Với `CallNonvirtual...`, class truyền vào phải đúng lớp mà ta muốn chọn và method ID phải lấy qua `GetMethodID` trên lớp đó. Dùng `jclass` và ID không tương ứng hoặc receiver không tương thích là lỗi nghiêm trọng của chương trình native.

`CallNonvirtual...` hỗ trợ cả các trường hợp đặc biệt của **default method trên interface** theo quy tắc JNI. Tuy nhiên không nên hiểu nó chỉ là bản dịch máy móc của mọi lời gọi `super` trong Java: JVM có quy tắc riêng cho `invokespecial`, private/constructor/interface. Bài này minh họa trường hợp dễ kiểm chứng nhất là lựa chọn `Parent.greet` đã bị `Child` override.

## 7. Đổi kiểu kết quả và truyền tham số

Ba họ API đều có biến thể tương ứng kiểu kết quả. Chọn đúng hàm theo **return type thực của Java method**:

| Java method | Instance | Static | Nonvirtual |
|---|---|---|---|
| `int size()` | `CallIntMethod` → `jint` | `CallStaticIntMethod` → `jint` | `CallNonvirtualIntMethod` → `jint` |
| `boolean ready()` | `CallBooleanMethod` → `jboolean` | `CallStaticBooleanMethod` → `jboolean` | `CallNonvirtualBooleanMethod` → `jboolean` |
| `String greet(String)` | `CallObjectMethod` → `jobject` | `CallStaticObjectMethod` → `jobject` | `CallNonvirtualObjectMethod` → `jobject` |
| `void reset()` | `CallVoidMethod` | `CallStaticVoidMethod` | `CallNonvirtualVoidMethod` |

Lưu ý: `jstring` là một kiểu JNI reference tương thích với `jobject`; hãy ép đúng khi biết method thật sự trả `String`. Với phương thức trả `int`, dùng `CallIntMethod` thay vì `CallObjectMethod`; trộn kiểu trả về dẫn tới lỗi ABI/JNI nghiêm trọng.

Ba cách truyền tham số:

- Dạng thường: `CallObjectMethod(env, receiver, greetId, name)` truyền trực tiếp các argument sau ID.
- Hậu tố `A`: `CallObjectMethodA` nhận mảng `jvalue[]`. Phù hợp khi xây danh sách argument động theo descriptor.
- Hậu tố `V`: `CallObjectMethodV` nhận `va_list` C (không phải `V` nghĩa là `void`).

Ví dụ tương đương với một tham số object:

```c
// Trích đoạn trong hàm JNI, giả định các biến đã được khởi tạo.
jvalue args[1];
args[0].l = name;

jobject result = (*env)->CallObjectMethodA(
        env, receiver, greetId, args);
if ((*env)->ExceptionCheck(env)) {
    // Xử lý/để exception lan ra Java; không dùng result.
}
```

Nếu truyền kiểu nguyên thủy, điền đúng member của union `jvalue` như `.i` cho `jint`, `.j` cho `jlong`, `.z` cho `jboolean`, `.d` cho `jdouble`, v.v. Với `CallNonvirtual<Type>MethodA`, thứ tự vẫn là `env, obj, clazz, methodID, args`; với static dạng `A` là `env, clazz, methodID, args`.

## 8. Exception, bộ nhớ tham chiếu và vòng đời

### 8.1. Pending Java exception

Một lần `CallObjectMethod` có thể khiến Java code ném `RuntimeException`, `Error` hoặc exception khác. JNI thường **không tự biến** exception đó thành C exception. Native code cần:

```c
jobject value = (*env)->CallObjectMethod(
        env, receiver, greetId, name);
if ((*env)->ExceptionCheck(env)) {
    // Không dùng value; trả khỏi native method để Java thấy exception.
    return NULL; // Chỉ phù hợp với native method trả reference.
}
```

Nếu native method trả `jint`, câu lệnh trả trong C phải trả `jint` hợp lệ (ví dụ `0` khi exception pending, với Java phía trên nhận exception thay vì giá trị). Nếu ứng dụng thực sự muốn **dịch exception** sang lỗi khác, phải hiểu các JNI API được phép gọi khi exception pending; thường cần đọc/lưu exception, clear có chủ đích rồi throw lại/throw mới. Không dùng `ExceptionClear` chỉ để bỏ qua lỗi.

### 8.2. Local reference, global reference và `jmethodID`

- `jobject`, `jclass`, `jstring` trả về từ JNI thường là **local references**: hợp lệ trong native frame/thread hiện hành, tự dọn khi frame kết thúc. Trong loop dài, tạo nhiều reference mà không xóa sẽ tốn bảng local refs.
- Muốn giữ class/object qua nhiều native call hoặc dùng ở thread khác, cân nhắc `NewGlobalRef`, sau đó `DeleteGlobalRef` đúng thời điểm; Java reference không phải pointer C tùy ý.
- `jmethodID` không phải Java reference và **không làm class sống mãi**. Nó có thể được cache trong phạm vi vòng đời của lớp; khi class bị unload, ID trở nên không hợp lệ. Nếu cache lâu dài, phải quản lý vòng đời class/class loader tương ứng.
- `JNIEnv*` thuộc thread; với native thread tự tạo, cần attach qua `JavaVM` đúng quy trình và detach lúc kết thúc. Không giữ `JNIEnv*` để dùng tại thread khác.

### 8.3. Không nhầm class lookup với class loader bất kỳ

`FindClass(env, "JniCallsDemo$Parent")` trong native method của `JniCallsDemo` có thể tìm class qua class loader gắn với native method đang chạy. Nhưng `FindClass` khi gọi từ native thread tự attach và không có Java caller có những quy tắc loader khác; class thuộc custom loader có thể không tìm được. Khi thiết kế binding rộng, có thể truyền class/class loader từ Java, hoặc lưu `jclass` dưới dạng global reference theo vòng đời xác định.

Class name dùng slash `/` cho package, dollar `$` cho nested class; đừng thay bằng dấu chấm Java trong chuỗi `FindClass`.

## 9. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng / sai lầm | Nguyên nhân thường gặp | Kiểm tra/sửa |
|---|---|---|
| `NoSuchMethodError` khi `GetMethodID` | Sai descriptor, sai hoa/thường, dùng ID instance cho method static | Kiểm tra `javap -p -s`; phân biệt `GetMethodID` và `GetStaticMethodID` |
| `ClassNotFound` / `NoClassDefFoundError` quanh `FindClass` | Sai tên binary `/` và `$`; class loader không tìm thấy class | Kiểm tra binary name, class loader và ngữ cảnh native thread |
| `UnsatisfiedLinkError` | Load thiếu `.so/.dll/.dylib`, sai kiến trúc, sai thư viện phụ thuộc, sai tên symbol JNI | Kiểm tra `-Djava.library.path`, loader OS, file header `javac -h` và exported symbol |
| Gọi `Child.greet` trong khi mong `Parent.greet` | Dùng `CallObjectMethod` (virtual dispatch) | Dùng `CallNonvirtualObjectMethod` và đúng `parentClass`/`greetId` |
| Gọi `Parent.kind` nhưng lại mong `Child.kind` | Static method không override | Lookup static ID trên `Child` và truyền `childClass` |
| JVM crash hoặc kết quả rác | Sai đối tượng/class/method ID/return type/descriptor, dùng stale ref hoặc ID | Xác nhận chữ ký và receiver, bật JNI checking |
| Không thấy Java exception đúng chỗ | Tiếp tục JNI call khi exception đang pending, hoặc cố ý clear rồi quên throw | `ExceptionCheck` sau lookup/invoke có thể ném; propagate hoặc translate có chủ đích |
| Local reference table overflow | Tạo nhiều refs trong native loop dài | `DeleteLocalRef` hoặc `PushLocalFrame`/`PopLocalFrame` |
| Callback chạy lỗi ở native thread | Dùng `JNIEnv*` từ thread khác/chưa attach vào JVM | `AttachCurrentThread`, lấy `JNIEnv*` đúng thread, detach |
| Cache method ID gây lỗi sau reload | Class/class loader đã unload; class reference local hết scope | Gắn cache với vòng đời loader/class, quản lý global ref |

**Chẩn đoán hữu ích trong development:** chạy với `java -Xcheck:jni -Djava.library.path=. JniCallsDemo`. Một số lỗi JNI có thể được phát hiện sớm và báo lỗi chi tiết; tùy JDK phiên bản cũng cần `--enable-native-access=ALL-UNNAMED`. `-Xcheck:jni` không bảo đảm phát hiện mọi lỗi native memory, nhưng rất hữu ích trước khi tối ưu hóa.

## 10. Quy trình dùng JNI để gọi Java method an toàn

1. **Xác định contract Java:** lớp sở hữu, static hay instance, visibility, kiểu tham số/trả về, có override hay không. Không phân biệt static với nonstatic chỉ dựa vào tên.
2. **Sinh header:** dùng `javac -h` cho entrypoint Java → JNI; dùng `javap -p -s` để xác minh descriptor của method Java cần gọi từ C.
3. **Tìm lớp và ID:** `FindClass`/class ref, `GetMethodID` hoặc `GetStaticMethodID`. Nếu lookup lỗi hoặc có pending exception, dừng và truyền lỗi.
4. **Chọn họ Call đúng mục đích:** instance dynamic dispatch → `Call<Type>Method`; static → `CallStatic<Type>Method`; instance theo class tường minh → `CallNonvirtual<Type>Method`.
5. **Truyền đúng tham số:** Java primitive mapping sang JNI primitive, Java object sang reference, mảng tham số kiểu `jvalue[]` nếu dùng `A`. Không truyền pointer tùy tiện thay `jobject`.
6. **Kiểm tra sau call:** dùng `ExceptionCheck`/cơ chế xử lý exception nhất quán, rồi mới dùng kết quả. Đảm bảo không giải phóng reference trả về quá sớm.
7. **Quản lý lifetime:** dọn local refs khi lặp nhiều lần; cache `jmethodID` theo vòng đời class; class global refs khi cần; `JNIEnv*` theo thread.
8. **Test hành vi polymorphism:** chạy cùng một receiver `Child` bằng cả virtual và nonvirtual để kiểm chứng chính xác implementation được gọi; test static hiding riêng.
9. **Kiểm tra native deployment:** OS/CPU, symbol, thư viện phụ thuộc, quyền native access trên JDK mới; dùng `-Xcheck:jni` khi phát triển.

Đừng gọi nonvirtual chỉ vì muốn "nhanh hơn". Nó thay đổi **ngữ nghĩa** method dispatch, dễ bỏ qua validation/invariant được override trong lớp con. Chỉ dùng khi có lý do hành vi rõ ràng, được kiểm thử.

## 11. Bài tập kiểm tra hiểu biết

**Bài 1 — dự đoán kết quả.** Cho `Child extends Parent`, cả hai có `greet` override như trong demo. Native lấy `greetId` từ `Parent` và receiver là `new Child()`. Hỏi `CallObjectMethod` hay `CallNonvirtualObjectMethod(env, receiver, parentClass, greetId, ...)` gọi `Parent.greet`? **Đáp án:** chỉ nonvirtual với `parentClass`; virtual gọi `Child.greet`.

**Bài 2 — phân biệt static hiding.** Thêm `public static String kind()` vào cả hai lớp. Nếu JNI dùng `GetStaticMethodID(parentClass, "kind", "()Ljava/lang/String;")` và `CallStaticObjectMethod(parentClass, id)` thì trả về gì? **Đáp án:** `Parent static`; receiver runtime class không liên quan.

**Bài 3 — sửa descriptor.** Java có `public int score(String s, long threshold)`. Chọn descriptor JNI. **Đáp án:** `(Ljava/lang/String;J)I`. Chọn `CallIntMethod` hoặc `CallNonvirtualIntMethod` (nếu cần chỉ định implementation lớp cha); với `static score` dùng `GetStaticMethodID` + `CallStaticIntMethod`.

**Bài 4 — kiểm tra exception.** Sửa `Child.greet` ném `IllegalStateException` khi tên trống; gọi JNI với `""`. Mã C phải làm gì sau `CallObjectMethod`? **Đáp án:** thấy `ExceptionCheck` khác 0, ngừng dùng kết quả, trả khỏi native method hoặc xử lý/translate exception có chủ đích; Java caller nhận Java exception nếu được giữ pending.

**Bài 5 — tìm lỗi.** Native code tạo `jclass` bằng `GetObjectClass(receiver)` (receiver là `Child`), rồi cố dùng nó để "gọi phương thức cha". **Đáp án:** đó là `Child` runtime class; muốn gọi `Parent` thì cần class reference `Parent` và `jmethodID` lấy trên `Parent`.

## 12. Tài liệu tham khảo chuẩn

- [Java Native Interface Specification — JNI Functions: Calling Instance, Static, Nonvirtual Methods](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [JNI Specification — Design Overview: Accessing Fields and Methods](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html)
- [JNI Specification — Types and Field/Method Descriptors](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html)
- [JDK Tool Specification — javac và tùy chọn `-h`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [JDK Tool Specification — javap và tùy chọn `-s`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html)
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)

Khi cần chọn API, hãy nhớ: **`Call<Type>Method` chọn implementation dựa trên receiver runtime; `CallStatic<Type>Method` chọn static method theo class/ID; `CallNonvirtual<Type>Method` chọn implementation instance theo `clazz` tường minh**. Lookup đúng method ID, descriptor, loại receiver và xử lý exception là điều kiện tối thiểu để lời gọi JNI đáng tin.
