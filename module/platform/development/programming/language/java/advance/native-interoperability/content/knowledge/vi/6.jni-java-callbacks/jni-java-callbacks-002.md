# Tạo đối tượng Java qua constructor trong JNI và phân biệt với AllocObject

## Mục tiêu

Khi mã C/C++ chạy trong JNI cần **tạo một đối tượng Java**, có hai API dễ gây nhầm lẫn:

- `NewObject` (hoặc `NewObjectA`, `NewObjectV`): **tạo đối tượng và gọi constructor Java** đã được chọn.
- `AllocObject`: **cấp phát đối tượng Java nhưng không gọi bất kỳ constructor nào** của đối tượng đó.

Cả hai đều trả về `jobject` do JVM quản lý; chúng **không tương đương về trạng thái khởi tạo**. Phân biệt sai rất dễ tạo ra đối tượng có các field mang giá trị mặc định, phá vỡ bất biến của lớp và làm phương thức Java lỗi khi sử dụng.

Sau bài này, bạn có thể xác định constructor bằng `GetMethodID` với tên `<init>`, hiểu descriptor `(I)V`, tạo đối tượng bằng `NewObject`, diễn giải chính xác tác động của `AllocObject`, biên dịch ví dụ Java 17 + JNI C, xử lý ngoại lệ và quản lý local reference an toàn.

## 1. Hai thao tác không giống nhau

| Tiêu chí | `NewObject` | `AllocObject` |
|---|---|---|
| Mục đích | Tạo và **khởi tạo theo constructor** | Chỉ **cấp phát một instance** |
| Cần `jclass`? | Có | Có |
| Cần `jmethodID` của `<init>`? | Có | Không |
| Gọi constructor của lớp? | **Có** | **Không** |
| Chạy chuỗi constructor của superclass? | Theo ngữ nghĩa của constructor Java được gọi | **Không** gọi constructor nào của đối tượng |
| Chạy initializer của instance? | Có, theo luồng khởi tạo Java thông thường | Không chạy instance field initializer / instance initializer block |
| Field sau thao tác | Do constructor và các initializer thiết lập | Giá trị mặc định theo JVM: `0`, `false`, `null`… |
| Tác dụng phụ trong constructor | Diễn ra, hoặc constructor ném ngoại lệ | Không diễn ra |
| Độ an toàn cho đối tượng ứng dụng | Lựa chọn thông thường | Dễ tạo trạng thái bất hợp lệ; chỉ dùng có chủ đích |
| Giá trị trả về JNI | `jobject` hoặc `NULL` nếu không tạo được | `jobject` hoặc `NULL` nếu không cấp phát được |

Điểm then chốt: **`AllocObject` không phải phiên bản “nhanh hơn một chút” của `NewObject`**. Nó thay đổi ngữ nghĩa khởi tạo. Một đối tượng tồn tại trong heap nhưng thiếu constructor có thể không đáp ứng bất cứ giả định nào mà các phương thức Java của lớp đặt ra.

Cũng cần phân biệt **khởi tạo lớp** (*class initialization*, thường liên quan `<clinit>` và field `static`) với **khởi tạo instance** (*instance initialization*, chạy constructor `<init>`). Việc tìm class hoặc `GetMethodID` có thể dẫn đến class initialization theo quy tắc JNI/JVM; điều đó **không có nghĩa** `AllocObject` chạy instance constructor. Hai quá trình là riêng biệt.

## 2. Đối tượng Java được tạo bình thường như thế nào?

Với Java:

~~~java
final class UserProfile {
    private final int id;
    private String status = "initial";
    private static int constructed;

    UserProfile(int id) {
        this.id = id;
        this.status = "ready";
        constructed++;
    }

    String getStatus() {
        return status;
    }
}
~~~

Biểu thức Java `new UserProfile(42)` thực hiện việc cấp phát và khởi tạo theo quy tắc ngôn ngữ. Trong constructor, chuỗi gọi `this(...)`/`super(...)` phù hợp được thực hiện; các instance initializer của lớp được chạy ở vị trí mà ngôn ngữ quy định; thân constructor gán `id`, cập nhật `status` và tăng `constructed`. Khi trả về bình thường, đối tượng đáp ứng các bất biến mà constructor cam kết.

Trong JNI, một lệnh tương ứng về mục đích là:

~~~c
jmethodID ctor = (*env)->GetMethodID(env, cls, "<init>", "(I)V");
jobject user = (*env)->NewObject(env, cls, ctor, (jint)42);
~~~

Trái lại:

~~~c
jobject raw = (*env)->AllocObject(env, cls);
~~~

cấp phát đối tượng với `id == 0` và `status == NULL` (ở phía Java là `null`). Giá trị `"initial"` **cũng chưa được gán**: instance field initializer trong source Java được thực thi thông qua constructor, không được JVM tự chạy sau `AllocObject`. `constructed` không tăng do `AllocObject`.

Trong ví dụ này, `status.equals("ready")` trên đối tượng vừa `AllocObject` có thể ném `NullPointerException`. Những lớp chứa resource handle, khóa, collection, trường `final` hoặc kiểm tra tham số trong constructor còn dễ gặp hậu quả nghiêm trọng hơn.

## 3. Ba thành phần bắt buộc để gọi constructor từ JNI

### 3.1. `JNIEnv*` là bảng hàm của thread đang gọi

Trong C, các hàm JNI được truy cập qua:

~~~c
(*env)->FindClass(env, "example/UserProfile");
(*env)->GetMethodID(env, cls, "<init>", "(I)V");
(*env)->NewObject(env, cls, ctor, (jint)42);
~~~

`env` là con trỏ giao diện JNI dành cho thread hiện tại. Không tự truyền lại `JNIEnv*` sang thread native khác; thread native muốn gọi JVM phải có môi trường JNI hợp lệ của **chính thread đó** thông qua cơ chế attach thích hợp.

### 3.2. `jclass` xác định lớp thực sự muốn tạo

Ví dụ:

~~~c
jclass cls = (*env)->FindClass(env, "example/UserProfile");
if (cls == NULL) {
    return NULL; // Giữ nguyên lỗi JNI pending để Java nhận được.
}
~~~

Tên lớp trong `FindClass` dùng dấu `/` cho package: `example/UserProfile`, **không** phải `example.UserProfile`. Với nested class, dùng binary name, ví dụ `"JniConstructorDemo$Sample"` trong chương trình chạy đầy đủ bên dưới.

`jclass` là một JNI reference đến đối tượng `java.lang.Class`. Nó không phải địa chỉ native của cấu trúc object Java; không phép ép kiểu C nào biến nó thành layout field nội bộ JVM.

### 3.3. `GetMethodID` định danh chính xác constructor

~~~c
jmethodID ctor = (*env)->GetMethodID(
        env, cls, "<init>", "(I)V");
if (ctor == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return NULL;
}
~~~

- Tên đặc biệt `<init>` là tên JVM dành cho **instance constructor**, không phải tên lớp hay chuỗi `"UserProfile"`.
- Descriptor `(I)V` là “nhận một `int`, trả về `void`”. Constructor luôn có return descriptor `V`.
- `()V` tương ứng constructor không tham số; `(Ljava/lang/String;I)V` tương ứng `(String, int)`; `([I)V` tương ứng một tham số `int[]`.
- `GetMethodID` dùng cho instance method/constructor; `GetStaticMethodID` không dùng cho `<init>`.
- Cần trùng **đúng** danh sách tham số khi có constructor overload. `GetMethodID` trả về `NULL` khi không tìm thấy và có thể tạo `NoSuchMethodError`; nó cũng có thể kích hoạt class initialization và ném ngoại lệ liên quan initializer.
- `jmethodID` là ID native của method, **không phải local reference**: không gọi `DeleteLocalRef` trên ID này.

Nếu `FindClass` hoặc `GetMethodID` gặp lỗi, không tiếp tục dùng class/ID `NULL`. Cách đúng thường là return và để ngoại lệ JNI còn pending được truyền về Java.

## 4. Gọi `NewObject` và ba biến thể truyền tham số

Cú pháp cơ bản:

~~~c
jobject NewObject(JNIEnv *env, jclass clazz, jmethodID ctor, ...);
jobject NewObjectA(JNIEnv *env, jclass clazz, jmethodID ctor,
                   const jvalue *args);
jobject NewObjectV(JNIEnv *env, jclass clazz, jmethodID ctor,
                   va_list args);
~~~

Ba dạng cùng khởi tạo đối tượng bằng constructor đã chọn. Khác biệt là **cách biểu diễn tham số**:

- `NewObject`: truyền đối số trực tiếp sau `ctor`, thích hợp cho lời gọi đơn giản.
- `NewObjectA`: truyền mảng `jvalue`, hữu ích khi số lượng/loại tham số được chuẩn bị có cấu trúc.
- `NewObjectV`: truyền `va_list` từ hàm C variadic wrapper.

Ví dụ constructor `(I)V`:

~~~c
// Truyền trực tiếp; ctor lấy từ GetMethodID(..., "<init>", "(I)V").
jobject a = (*env)->NewObject(env, cls, ctor, (jint)42);

// Tương đương về mục đích: dạng mảng jvalue.
jvalue params[1];
params[0].i = (jint)42;
jobject b = (*env)->NewObjectA(env, cls, ctor, params);
~~~

Đây là **đoạn JNI minh họa**, giả định `env`, `cls`, `ctor` hợp lệ và không có ngoại lệ pending. Nếu muốn dùng cả `a` lẫn `b`, phải xử lý kết quả và local references đúng cách. Không áp dụng `NewObjectA` cho constructor bằng cách suy đoán chữ ký: mảng `jvalue` phải khớp chính xác descriptor và thứ tự tham số.

`NewObject` trả về reference đến **instance mới**; các chuỗi constructor được chạy, ngoại lệ trong constructor (nếu có) làm tạo object thất bại theo hợp đồng JNI. Không được dùng kết quả trước khi kiểm tra lỗi.

## 5. Ví dụ đầy đủ Java 17 + JNI C: nhìn rõ sự khác biệt

Ví dụ tạo cùng lớp Java bằng hai hàm native. Kết quả cho thấy constructor và instance field initializer chạy ở nhánh `NewObject`, nhưng bị bỏ qua ở nhánh `AllocObject`. Ta sử dụng nested `static` class để loại bỏ tham số outer instance ngầm.

### 5.1. File Java: `JniConstructorDemo.java`

~~~java
public final class JniConstructorDemo {
    static {
        System.loadLibrary("jniconstructdemo");
    }

    private static native Sample newByConstructor(int id);
    private static native Sample newByAllocObject();

    public static final class Sample {
        private static int constructorCalls;
        private final int id;
        private int marker = 7;
        private String phase = "field-initializer";

        public Sample(int id) {
            if (id < 0) {
                throw new IllegalArgumentException("id must be non-negative");
            }
            this.id = id;
            this.phase = "ready";
            constructorCalls++;
        }

        String describe() {
            return "id=" + id
                    + ", marker=" + marker
                    + ", phase=" + phase;
        }

        static int constructorCalls() {
            return constructorCalls;
        }
    }

    public static void main(String[] args) {
        Sample constructed = newByConstructor(42);
        Sample allocatedOnly = newByAllocObject();

        System.out.println("NewObject: " + constructed.describe());
        System.out.println("AllocObject: " + allocatedOnly.describe());
        System.out.println(
                "constructorCalls=" + Sample.constructorCalls());
    }
}
~~~

Điểm chủ ý trong `Sample`:

- `id` là `final` và chỉ được gán trong constructor.
- `marker = 7` và `phase = "field-initializer"` là **instance field initializer**, được thực thi trên đường khởi tạo bình thường.
- Constructor đổi `phase` thành `"ready"` và tăng bộ đếm `static constructorCalls`.
- `describe()` cố ý chỉ nối chuỗi để có thể quan sát `null`; một phương thức thật có thể dereference `phase` và thất bại đối với object chưa khởi tạo.
- `Sample` được khai báo `static`, do đó constructor `(I)V` chỉ có tham số `int`; một inner class **không static** có thể có tham số constructor bổ sung cho enclosing instance ở mức bytecode.

### 5.2. Tạo JNI header từ source Java

Tại thư mục chứa file Java, chạy với JDK 17 trở lên:

~~~bash
javac -h . JniConstructorDemo.java
~~~

Lệnh trên biên dịch `JniConstructorDemo.class`, `JniConstructorDemo$Sample.class` và sinh `JniConstructorDemo.h`. Tên/tham số của JNI exported function được tạo từ **khai báo native method thực tế**, tránh phải đoán quy tắc name mangling. Nếu package được thay đổi, tên JNI và `FindClass` cần thay tương ứng.

### 5.3. File C: `jniconstructdemo.c`

~~~c
#include "JniConstructorDemo.h"

JNIEXPORT jobject JNICALL
Java_JniConstructorDemo_newByConstructor(
        JNIEnv *env, jclass declaringClass, jint id) {
    (void)declaringClass;

    jclass sampleClass = (*env)->FindClass(
            env, "JniConstructorDemo$Sample");
    if (sampleClass == NULL) {
        return NULL; // Không dùng jclass khi FindClass thất bại.
    }

    jmethodID ctor = (*env)->GetMethodID(
            env, sampleClass, "<init>", "(I)V");
    if (ctor == NULL) {
        (*env)->DeleteLocalRef(env, sampleClass);
        return NULL; // Giữ nguyên ngoại lệ do JNI báo.
    }

    jobject result = (*env)->NewObject(
            env, sampleClass, ctor, id);

    // Xóa local reference tới Class; result vẫn được trả về Java.
    (*env)->DeleteLocalRef(env, sampleClass);
    return result;
}

JNIEXPORT jobject JNICALL
Java_JniConstructorDemo_newByAllocObject(
        JNIEnv *env, jclass declaringClass) {
    (void)declaringClass;

    jclass sampleClass = (*env)->FindClass(
            env, "JniConstructorDemo$Sample");
    if (sampleClass == NULL) {
        return NULL;
    }

    // Không tìm <init>, không truyền tham số, không chạy constructor.
    jobject result = (*env)->AllocObject(env, sampleClass);

    (*env)->DeleteLocalRef(env, sampleClass);
    return result;
}
~~~

Giải thích:

1. Hai hàm native được gọi **từ Java vào C**, rồi **C tạo object Java** thông qua JNI và trả về cùng kiểu Java `Sample`. Đây là một tình huống cụ thể của “gọi Java từ JNI”.
2. Với static native method, tham số JNI thứ hai có kiểu `jclass` (class khai báo native method). Nếu native method là instance method, tham số đó là `jobject` của receiver.
3. `FindClass("JniConstructorDemo$Sample")` sử dụng binary name của nested class trong default package. Với package `demo`, chuỗi tương ứng sẽ là `"demo/JniConstructorDemo$Sample"`.
4. `NewObject` gọi đúng constructor `Sample(int)`. `AllocObject` không truy vấn hay thực thi `<init>`.
5. Khi thành công, `FindClass` tạo local reference. Xóa `sampleClass` bằng `DeleteLocalRef` trong các nhánh phù hợp là an toàn. `result` được trả về Java dưới dạng local reference hợp lệ; không giải phóng reference này ngay trước khi return.
6. Nếu constructor ném ngoại lệ, `NewObject` có thể trả về `NULL` và ngoại lệ Java còn pending. `DeleteLocalRef` thuộc những thao tác dọn reference được phép khi có ngoại lệ pending. Tránh gọi tiếp API JNI tùy tiện trước khi xử lý ngoại lệ.
7. JNI object reference **không phải `malloc` pointer** và không thể trực tiếp dereference để đọc `Sample.id` bằng cấu trúc C. JVM quản lý object và bộ gom rác.

### 5.4. Biên dịch thư viện native

Đặt `JAVA_HOME` trỏ đến **JDK 17+ đúng kiến trúc** của tiến trình chạy. Các lệnh dưới đây giả định đang đứng trong thư mục có `JniConstructorDemo.java`, `JniConstructorDemo.h` và `jniconstructdemo.c`.

**Linux với GCC:**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    jniconstructdemo.c -o libjniconstructdemo.so

java -Djava.library.path=. JniConstructorDemo
~~~

**macOS với Clang:**

~~~bash
clang -dynamiclib -Wall -Wextra \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
    jniconstructdemo.c -o libjniconstructdemo.dylib

java -Djava.library.path=. JniConstructorDemo
~~~

**Windows với MSVC Developer Command Prompt:**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jniconstructdemo.c /Fe:jniconstructdemo.dll
java -Djava.library.path=. JniConstructorDemo
~~~

Đây là ba **lựa chọn build theo OS**, chỉ chạy nhánh tương ứng. Tên file native đáp ứng `System.loadLibrary("jniconstructdemo")` trên nền tảng đó. Đối với Linux/macOS, dùng shell hỗ trợ `$JAVA_HOME` và xuống dòng bằng `\`; với Windows, dùng Command Prompt có toolchain MSVC và `%JAVA_HOME%`. Thư viện phải được build cho **đúng kiến trúc/ABI của JVM** và có đầy đủ dependencies để loader mở được.

### 5.5. Đầu ra mong đợi

Khi build và load thành công trên một JVM tương thích:

~~~text
NewObject: id=42, marker=7, phase=ready
AllocObject: id=0, marker=0, phase=null
constructorCalls=1
~~~

**Vì sao?**

- `NewObject(…, 42)` tạo `Sample`, chạy instance initializer (`marker = 7`, `phase = "field-initializer"`), thực thi constructor, đổi `phase = "ready"` và tăng bộ đếm lên 1.
- `AllocObject` vẫn tạo một instance `Sample` có thể được trả về Java, nhưng **không chạy instance initializer hoặc constructor**. Vì thế `id` và `marker` ở giá trị mặc định `0`, còn `phase` là `null`.
- Bộ đếm `static` chỉ tăng trong constructor, nên kết quả cuối cùng là `1`. Đây là quan sát cho ví dụ cụ thể; không nên dùng bộ đếm ấy thay cho cơ chế xác minh trạng thái object trong phần mềm thật.

**Không cần dùng `GetMethodID` với `AllocObject`.** Nếu nhầm `AllocObject` với `NewObject`, chương trình có thể vẫn biên dịch và nạp thư viện thành công, nhưng trả về object phá vỡ invariants mà constructor phải bảo đảm.

## 6. Constructor, field initializer và class initializer: phân biệt đúng

Trong Java, source có thể chứa:

~~~java
final class Example {
    static int classState = initializeClass();

    private final int identifier;
    private int instanceState = 10;

    {
        instanceState += 5;  // instance initializer block
    }

    Example(int identifier) {
        this.identifier = identifier;
    }

    private static int initializeClass() {
        return 20;
    }
}
~~~

Đây là **đoạn minh họa về cấu trúc Java**, chưa phải chương trình tự chạy. Ý nghĩa:

- `classState` là trạng thái **static của class**; các bước khởi tạo class tuân theo lifecycle JVM/JLS, không phải mặc định “mỗi object tạo một lần”.
- `instanceState = 10` và block cộng 5 là **instance initialization**; ở đường khởi tạo bình thường, chúng được thực hiện qua constructor (đồng thời tuân theo thứ tự `super`/`this`).
- `identifier` là `final` dành cho từng instance; Java compiler kiểm tra việc gán nó khi constructor hoàn tất bình thường.

**`GetMethodID` có thể gây khởi tạo class chưa initialized**, vì vậy khi kiểm tra `AllocObject` không được nói rằng “toàn bộ initializer của class đều không chạy”. Điều đúng cần nhớ là: `AllocObject` **không gọi constructor của đối tượng**, nên không chạy phần khởi tạo *instance* được mã hóa trong những constructor đó. Trong chương trình ví dụ, bộ đếm static tồn tại và có giá trị 0 theo quy tắc default initialization dù instance cấp phát bằng `AllocObject` chưa được khởi tạo.

Với `NewObject`, nếu constructor có lời gọi `super(...)`, chain superclass constructor được thực hiện theo ngữ nghĩa Java. Với `AllocObject`, không có chain constructor này. Một instance có thể mang đầy đủ kiểu runtime nhưng **không được setup như đối tượng được tạo bằng Java `new`**.

### `final` không làm `AllocObject` tự gán field

`private final int id` giúp compiler kiểm soát gán biến trong Java source bình thường. Nhưng khi `AllocObject` bypass constructor, giá trị `id` của object mới vẫn là default `0`. Không suy luận rằng “field final chắc chắn đã nhận giá trị hợp lệ”. Nếu lớp dựa trên `final String token` không bao giờ null trong luồng khởi tạo bình thường, `AllocObject` có thể tạo trạng thái `token == null`. Những giả định liên quan đến immutable object, publication và Java Memory Model cũng có thể không còn đúng theo cách ứng dụng mong đợi.

Dùng `Set<Field>` bằng JNI để vá field sau `AllocObject`, đặc biệt là field `final`, không tự khôi phục các bất biến, kiểm tra tham số, resource lifetime, constructor chain và bảo đảm an toàn của object đã được xây dựng đúng. **Ưu tiên gọi constructor qua `NewObject`** khi cần một object dùng được.

## 7. Ngoại lệ: không được coi `NULL` là thành công

### Khi `FindClass` thất bại

Tên binary class sai, class loader không nhìn thấy lớp hoặc lỗi load có thể khiến `FindClass` trả về `NULL` và có ngoại lệ pending, ví dụ `NoClassDefFoundError`. Không gọi `GetMethodID` với `cls == NULL`.

### Khi `GetMethodID` thất bại

Constructor `(I)V` không tồn tại hoặc signature sai có thể sinh `NoSuchMethodError`. `GetMethodID` cũng có thể gây `ExceptionInInitializerError` nếu class initializer thất bại. Cần kiểm tra kết quả trước khi sử dụng `ctor`.

### Khi `NewObject` thất bại

Constructor ném `IllegalArgumentException`, `IOException` hoặc ngoại lệ Java khác (tùy constructor) thì lỗi được phản ánh về phía Java. `NewObject` cũng có thể thất bại với `InstantiationException` cho class không thể khởi tạo theo hợp đồng và `OutOfMemoryError`. Không tiếp tục truy cập object sau khi đã thấy JNI exception.

Trong ví dụ chạy đầy đủ, nếu chủ động gọi `newByConstructor(-1)`, constructor `Sample(int)` ném `IllegalArgumentException("id must be non-negative")`. JNI không cần biến ngoại lệ đó thành `NULL` rồi che giấu nó; nhánh return `NULL` trong lúc ngoại lệ còn pending sẽ để Java nhận đúng exception.

### Khi `AllocObject` thất bại

`AllocObject` không nhận constructor nên **không thể ném ngoại lệ xuất phát từ thân constructor** của object đó. Tuy nhiên API vẫn có thể trả `NULL`; đặc biệt `InstantiationException` nếu `clazz` trỏ đến interface hoặc abstract class, và `OutOfMemoryError` nếu thiếu bộ nhớ. `clazz` không được là array class. Không dùng `AllocObject` để tạo mảng; có các API tạo mảng JNI riêng như `NewObjectArray`.

### Mẫu xử lý sau lời gọi JNI

~~~c
jobject object = (*env)->NewObject(env, cls, ctor, (jint)42);

if ((*env)->ExceptionCheck(env)) {
    // Có ngoại lệ pending; dọn local refs được phép rồi return.
    (*env)->DeleteLocalRef(env, cls);
    return NULL;
}
if (object == NULL) {
    // Kiểm tra/báo lỗi theo hợp đồng của ứng dụng.
    // Không giả định một jobject NULL là đối tượng đã khởi tạo.
}
~~~

Đây là **mảnh code minh họa** chèn trong hàm JNI đã có biến `env`, `cls`, `ctor` hợp lệ. Một số hàm JNI có thể trả `NULL` do lỗi mà không ném exception; nếu `object == NULL` nhưng không có ngoại lệ pending, native method nên chuyển lỗi thành ngoại lệ/đường xử lý lỗi rõ ràng thay vì lặng lẽ trả “thành công”.

Theo JNI, khi có ngoại lệ pending chỉ được sử dụng những thao tác JNI được cho phép trong trạng thái đó (ví dụ dọn local reference); không tùy tiện gọi `GetFieldID`, `CallObjectMethod`, `NewObject` tiếp. `ExceptionClear` chỉ dùng khi thực sự định xử lý và thay thế lỗi, không tự xóa ngoại lệ chỉ để chương trình tiếp tục.

## 8. Quản lý `jobject`, `jclass` và vòng đời JNI reference

Cả `NewObject` lẫn `AllocObject` trả về **JNI object reference**, không trả về con trỏ C đến vị trí field trong Java heap.

- `jobject` là reference đến Java object; JVM/GC có thể di chuyển object khi quản lý heap. Không ép `jobject` thành `struct Sample*`.
- `jclass` là reference đến đối tượng Class. `FindClass` thông thường trả local reference; khi không cần nữa, gọi `DeleteLocalRef`.
- `jmethodID` là identifier, không phải object reference; **không** gọi `DeleteLocalRef` với nó.
- Các local references tạo trong native call được giới hạn bởi native frame; khi trả `jobject` từ JNI native method, JVM xử lý reference trả về để Java nhận object. Tránh tự `DeleteLocalRef` trên chính `result` trước khi return.
- Khi tạo nhiều object trong vòng lặp JNI dài, dọn local reference từng lượt hoặc dùng `PushLocalFrame`/`PopLocalFrame`. Đừng để local-ref table phình to.
- Nếu cần giữ một reference sang native call khác, dùng `NewGlobalRef`/`DeleteGlobalRef` theo vòng đời rõ ràng; đừng cache local `jclass` hoặc `jobject` qua lời gọi.
- `JNIEnv*` gắn với thread; không cache rồi sử dụng từ thread khác.

### Class loader và `FindClass`

Trong ví dụ, `FindClass("JniConstructorDemo$Sample")` nằm trong một native method được gọi từ Java, nên có ngữ cảnh class loader phù hợp của lớp khai báo native method. Với mã C chạy từ một thread native vừa `AttachCurrentThread` hoặc khi dùng custom class loader, quy tắc tìm class có thể khác. Nếu lookup không đáng tin, hãy truyền `Class<?>` từ Java hoặc quản lý class loader/global reference phù hợp; **không coi mọi class đều có thể được `FindClass` bằng loader hệ thống**.

Vì vậy ví dụ không được sao chép nguyên chuỗi `FindClass` sang một thread native không có Java caller frame rồi giả định nó vẫn resolve cùng lớp ứng dụng.

## 9. Khi nào `AllocObject` thực sự có lý do tồn tại?

`AllocObject` là API có chủ đích cho các cơ chế runtime đặc biệt, chẳng hạn bộ khôi phục trạng thái object có kiểm soát, một số framework serialization/VM integration, hoặc thuật toán native có hợp đồng riêng để cấp phát trước rồi hoàn thiện object. Tính hợp lệ của những trường hợp này phụ thuộc rất mạnh vào lớp đích, phiên bản JVM và bảo đảm của framework.

Nó **không phải** lựa chọn mặc định khi:

- Tạo domain object cần constructor validation, non-null fields, immutable state hoặc resource initialization.
- Muốn tránh chi phí constructor nhưng vẫn mong object hành xử như đã qua `new`.
- Muốn vượt qua kiểm tra quyền hoặc ràng buộc nghiệp vụ trong constructor.
- Chưa có phương án chứng minh an toàn cho field `final`, inheritance, lifecycle, exception cleanup và publishing giữa các thread.

Ngay cả khi dùng `AllocObject` xong rồi tìm cách gọi constructor riêng qua JNI, đó là luồng khởi tạo nâng cao dễ sai. Trường hợp chỉ cần “tạo và khởi tạo bằng constructor”, `NewObject` đã thực hiện đúng hai bước trong một API và thường là đường ngắn nhất, rõ nhất.

### Những lựa chọn tốt hơn cho lớp có constructor phức tạp

Nếu constructor làm nhiều việc hoặc signature dễ thay đổi, có thể chuyển phần khởi tạo phức tạp sang **static factory method Java** có hợp đồng rõ ràng, rồi JNI dùng `GetStaticMethodID` + `CallStaticObjectMethod` để gọi factory. Phương án đó vẫn thực thi logic Java theo thiết kế và có thể trả subtype, cache hoặc object tái sử dụng tùy hợp đồng factory. Đừng tự động thay factory bằng `AllocObject`.

Ví dụ Java:

~~~java
public static UserProfile createValidated(int id) {
    if (id <= 0) {
        throw new IllegalArgumentException("id must be positive");
    }
    return new UserProfile(id);
}
~~~

Đây là **đoạn Java minh họa** bên trong class phù hợp; nó chưa phải chương trình độc lập. JNI khi gọi factory phải dùng đúng return descriptor, ví dụ `(I)Lexample/UserProfile;` cho class ở package `example`. `GetStaticMethodID` không dùng cho constructor `<init>`; nó dùng cho factory method `createValidated`.

## 10. Lỗi phổ biến và cách tìm nguyên nhân

| Hiện tượng | Khả năng gây lỗi | Cách kiểm tra |
|---|---|---|
| `GetMethodID` trả `NULL` | Sai `<init>` hoặc descriptor; class chưa load/initializer thất bại | Kiểm tra bytecode bằng `javap -s -p` và ngoại lệ pending |
| `NewObject` trả `NULL` | Constructor ném ngoại lệ hoặc allocation thất bại | Kiểm tra `ExceptionCheck`, giữ stack trace gốc |
| `AllocObject` trả object nhưng field “mất giá trị” | Instance field initializer/constructor không chạy | So sánh với `NewObject`, xem zero/null defaults |
| `final` field quan sát là 0/null | Bypass constructor bằng `AllocObject` | Không coi `final` là bằng chứng khởi tạo |
| `NullPointerException` khi gọi method sau `AllocObject` | Method dựa vào invariant non-null | Khởi tạo bằng constructor/factory |
| `NoClassDefFoundError` dù tên class đúng source | Sai binary name `$`/`/` hoặc class loader | Xem `javap` và ngữ cảnh loader |
| `UnsatisfiedLinkError` trước khi thấy output | Tên thư viện sai, thiếu file, ABI/dependency không phù hợp | Kiểm tra `System.loadLibrary`, `java.library.path` và binary |
| Native crash/VM abort sau lookup lỗi | Tiếp tục dùng `NULL` hoặc gọi JNI không hợp lệ khi exception pending | Kiểm tra từng kết quả và trạng thái ngoại lệ |
| Local reference table overflow trong vòng lặp | Giữ quá nhiều local `jobject`/`jclass` | `DeleteLocalRef` hoặc JNI local frame |
| Class lookup thất bại từ thread native | `FindClass` không có loader ứng dụng mong muốn | Truyền Class/loader hoặc lưu global reference hợp lệ |

Để kiểm tra constructor thật sự có descriptor gì:

~~~bash
javap -s -p 'JniConstructorDemo$Sample'
~~~

Lệnh này đọc bytecode đã biên dịch trong cùng thư mục và thường hiển thị constructor kiểu:

~~~text
public JniConstructorDemo$Sample(int);
  descriptor: (I)V
~~~

Đây là **trích đoạn liên quan** trong output của `javap` (output đầy đủ còn liệt kê field và method khác). Trên Windows Command Prompt, có thể dùng dấu ngoặc kép để tránh những khác biệt cú pháp shell; trên POSIX shell, dấu nháy đơn giúp giữ nguyên ký tự `$`.

## 11. Quy trình review code JNI tạo object

Khi gặp một native method tạo object Java, hãy hỏi theo thứ tự:

1. **Lớp nào?** `jclass` có đúng binary name và class loader? Đúng class concrete, không phải interface/abstract/array?
2. **Có cần constructor không?** Với domain object thông thường, câu trả lời là **có**; dùng `GetMethodID("<init>", descriptor)` + `NewObject`, hoặc factory Java có hợp đồng.
3. **Descriptor đúng không?** Xác minh bằng `javap -s -p`, không đoán từ tên lớp hay overload; đúng primitive/reference/array type và `V` cho constructor.
4. **Tham số đúng không?** Dùng JNI types (`jint`, `jlong`, `jobject`...) và thứ tự theo descriptor; với `NewObjectA`, mảng `jvalue` khớp từng vị trí.
5. **Có kiểm tra lỗi không?** `FindClass`, `GetMethodID`, `NewObject` có thể thất bại. Không tiếp tục như thể object đã tồn tại, và không xóa ngoại lệ pending tùy tiện.
6. **Reference có đúng lifetime không?** Dọn các local refs không cần nữa; không xóa reference đang trả về, không lưu local reference qua các native calls.
7. **Class initialization có bị nhầm với instance initialization không?** Thấy static initializer chạy không có nghĩa constructor đã chạy; xem field và tác dụng phụ trong constructor.
8. **Có bằng chứng chạy thật không?** Build với JDK/native compiler phù hợp, nạp thư viện đúng target, so output của `NewObject`/`AllocObject`; thêm test constructor ném exception và lớp abstract nếu ứng dụng thực sự cần hỗ trợ các trường hợp này.

## 12. Bài tập tự luyện

**Bài 1 — dự đoán kết quả.** Với `Sample` trong chương trình đầy đủ, nếu gọi `newByConstructor(10)` rồi `newByAllocObject()` và cuối cùng in `Sample.constructorCalls()`, hãy giải thích vì sao object thứ hai có `phase == null` dù source khai báo `phase = "field-initializer"`. Đáp án: instance initializer thuộc đường constructor; `AllocObject` chỉ cấp phát object có default field values.

**Bài 2 — descriptor.** Viết constructor:

~~~java
public Sample(int id, String phase) {
    this.id = id;
    this.phase = phase;
}
~~~

Giả sử thay constructor cũ bằng constructor này trong cùng lớp, descriptor mới là `(ILjava/lang/String;)V`. Ở JNI, dùng `GetMethodID(env, cls, "<init>", "(ILjava/lang/String;)V")` và truyền `jint` cùng `jstring` tương ứng cho `NewObject`. Nếu không cập nhật descriptor, `GetMethodID` cho `(I)V` sẽ thất bại. **Đoạn Java chỉ là biến thể bài tập**, không thể đặt song song trong chương trình `Sample` ở trên mà không điều chỉnh quy tắc gán các field phù hợp.

**Bài 3 — lỗi constructor.** Gọi `newByConstructor(-1)` và bắt `IllegalArgumentException` ở Java. Xác nhận ngoại lệ từ constructor lan ngược qua JNI; khi đổi sang `newByAllocObject()`, không có tham số `id` hoặc kiểm tra `id < 0` được thực hiện. Suy ra `AllocObject` không phải cách “tạo đối tượng nhanh” an toàn nếu constructor kiểm tra dữ liệu.

**Bài 4 — code review.** Một hàm JNI dùng `AllocObject` để tạo object `Session` có `final String token` được gán trong constructor, rồi trả về Java. Sau đó method `token.length()` bị `NullPointerException`. Sửa bằng constructor/factory phù hợp và kiểm thử cả đường lỗi; không sửa bằng cách giả định `final` field tự được khởi tạo.

## Tài liệu chuẩn

- [JNI Functions — AllocObject, NewObject, GetMethodID và quản lý reference (Oracle JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [JNI Types and Data Structures — method signature, native types và references (Oracle JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)
- [Java Language Specification, chương về tạo object và khởi tạo class/instance (JLS 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)

## Ghi nhớ

**`NewObject` = cấp phát + gọi constructor Java**, yêu cầu đúng `jclass`, `GetMethodID("<init>", descriptor)` và tham số. **`AllocObject` = cấp phát instance nhưng bỏ qua tất cả constructor**; instance field initializer cũng không chạy, nên object mang default field values có thể vi phạm bất biến.

Class initializer và instance constructor là hai khái niệm khác nhau. `jobject` vẫn là reference JVM quản lý, không phải con trỏ bộ nhớ C. Khi tạo object ứng dụng dùng được, hãy ưu tiên **constructor/factory**, kiểm tra ngoại lệ và giải phóng local reference đúng vòng đời.
