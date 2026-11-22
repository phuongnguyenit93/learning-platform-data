# Tham số JNIEnv cùng jobject hoặc jclass ở đầu hàm JNI

Khi gọi một phương thức Java được khai báo **native**, Java Virtual Machine (JVM) chuyển quyền thực thi sang hàm C/C++ tương ứng. Hàm native nhận **hai tham số do JVM cung cấp ngầm ở đầu danh sách**: **JNIEnv \*env** và **jobject** (phương thức instance) **hoặc jclass** (phương thức static). Sau hai tham số đó mới đến những tham số được khai báo trong mã Java.

Đây là quy tắc cốt lõi khi viết hàm JNI đầu tiên: **env cung cấp API để tương tác với JVM; tham số thứ hai cho biết ngữ cảnh đối tượng hoặc lớp; các tham số sau là dữ liệu thật của lời gọi Java.** Hai tham số đầu không xuất hiện trong khai báo phương thức Java và cũng không do lập trình viên Java truyền tường minh.

## 1. Từ khai báo Java đến chữ ký hàm C

Xét hai phương thức độc lập:

~~~java
class Example {
    native int addOne(int value);            // instance
    static native int addTwo(int value);     // static
}
~~~

Với quy tắc đặt tên JNI thông thường, các hàm C tương ứng có dạng:

~~~c
/* Hai prototype minh họa; cần #include <jni.h> để có kiểu JNI. */

JNIEXPORT jint JNICALL Java_Example_addOne(
        JNIEnv *env, jobject self, jint value);

JNIEXPORT jint JNICALL Java_Example_addTwo(
        JNIEnv *env, jclass clazz, jint value);
~~~

| Vị trí trong hàm C | Instance native | Static native | Do ai truyền? |
| --- | --- | --- | --- |
| 1 | **JNIEnv \*env** | **JNIEnv \*env** | JVM; giao diện gọi chức năng JNI |
| 2 | **jobject self** | **jclass clazz** | JVM; receiver hoặc lớp khai báo native method |
| 3 | **jint value** | **jint value** | Đối số **int value** trong lời gọi Java |
| Giá trị trả về | **jint** | **jint** | Hàm C trả về cho Java |

Tên biến **env**, **self**, **thiz**, **obj**, **clazz** hay **klass** chỉ là tên do người viết C đặt; **kiểu, vị trí, calling convention và chữ ký** mới quyết định kết nối đúng ABI. Java không có khai báo nào kiểu **addOne(JNIEnv env, Object self, int value)**; JVM tự truyền hai đối số đầu của hàm C.

~~~text
Java:  new Example().addOne(10)
                 |
                 v
JVM:   Java_Example_addOne(env, thisObject, 10)
                                     ^
                                 jobject self

Java:  Example.addTwo(10)
                 |
                 v
JVM:   Java_Example_addTwo(env, Example.class, 10)
                                     ^
                                 jclass clazz
~~~

Các ví dụ biểu diễn lời gọi theo nghĩa logic. JVM tự thực hiện chuyển giao qua ABI native; mã Java không trực tiếp gọi hàm C như một function pointer.

## 2. JNIEnv* là gì và dùng để làm gì?

**JNIEnv** là kiểu do **jni.h** cung cấp, đại diện cho giao diện các hàm JNI của JVM. Nó cho phép mã native truy cập Java một cách hợp lệ: tìm lớp, đọc/ghi field, gọi method, tạo string/array, kiểm tra/đưa ngoại lệ, quản lý các JNI reference.

Các lời gọi phổ biến:

| Nhiệm vụ | Hàm JNI |
| --- | --- |
| Lấy lớp runtime của một đối tượng | **GetObjectClass** |
| Tìm instance field | **GetFieldID** |
| Đọc instance field kiểu int | **GetIntField** |
| Tìm static field | **GetStaticFieldID** |
| Đọc static field kiểu int | **GetStaticIntField** |
| Tạo chuỗi Java | **NewStringUTF** hoặc **NewString** |
| Tìm và gọi method | **GetMethodID**, **Call<type>Method** |
| Kiểm tra ngoại lệ đang chờ | **ExceptionCheck** |
| So sánh hai JNI reference theo identity | **IsSameObject** |
| Giải phóng local reference không còn cần | **DeleteLocalRef** |

### Vì sao trong C viết (*env)->...? 

Trong bản khai báo JNI dành cho C, **JNIEnv** là kiểu con trỏ đến bảng hàm, và tham số được nhận dưới dạng **JNIEnv \*env**. Vì thế cú pháp C của một lời gọi qua bảng hàm là:

~~~c
/* Đoạn minh họa bên trong instance native method đã có env và self. */
jclass type = (*env)->GetObjectClass(env, self);

if (type != NULL) {
    (*env)->DeleteLocalRef(env, type);
}
~~~

Phần **(*env)->GetObjectClass** chọn function pointer trong bảng JNI; **env** ở danh sách đối số là tham số đầu của chính hàm đó. Đây là cú pháp C mà header JNI công bố, không phải dereference trực tiếp một đối tượng Java.

Trong **C++**, **jni.h** cung cấp lớp/struct wrapper với các hàm thành viên inline nên có cú pháp ngắn hơn:

~~~cpp
// Đoạn minh họa bên trong C++ native method.
jclass type = env->GetObjectClass(self);

if (type != nullptr) {
    env->DeleteLocalRef(type);
}
~~~

Hai đoạn thể hiện cùng chức năng JNI nhưng **không dùng lẫn cú pháp C và C++**: file **.c** dùng **(*env)->...(..., env, ...)**, file **.cpp** thường dùng **env->...(...)**. Nếu viết C++, khai báo native entry point với **extern "C"** (hoặc dùng đúng header sinh ra bởi **javac -h**) để bảo đảm symbol linkage phù hợp.

### JNIEnv* gắn với thread

- JVM truyền **JNIEnv \*** hợp lệ cho thread đang chạy lời gọi JNI. Không cất **env** vào biến global rồi dùng từ thread khác.
- Hai lời gọi trên cùng Java thread được JVM bảo đảm nhận cùng JNI interface pointer; trên các thread khác có thể khác pointer.
- Nếu C/C++ tự tạo thread muốn gọi vào Java, thread đó phải được attach vào JVM qua **JavaVM**/**AttachCurrentThread** để lấy **JNIEnv \*** của chính thread; sau khi hoàn thành phải detach đúng quy tắc. Một **JNIEnv \*** đã nhận từ thread A không được chuyển cho thread B.
- **JNIEnv \*** là điểm truy cập API Java, không phải Java object, không phải reference đến **this**, và cũng không thay cho **JavaVM \***.

## 3. Tham số thứ hai là jobject khi nào?

Với phương thức **native không có static**, JVM truyền đối tượng nhận lời gọi Java (**this**) dưới dạng **jobject**, thường đặt tên **self**, **thiz** hoặc **obj**.

~~~java
class Counter {
    private int count = 10;

    native int increase(int delta);  // instance method
}
~~~

Hàm native có hình thức:

~~~c
JNIEXPORT jint JNICALL Java_Counter_increase(
        JNIEnv *env, jobject self, jint delta);
~~~

**self** tham chiếu đến đúng đối tượng **Counter** đã nhận lời gọi, nên nếu có hai instance khác nhau thì mỗi lời gọi nhận reference của instance tương ứng. Các trường như **count** phải được truy cập qua các chức năng JNI, không đọc như struct C (**self->count** là sai). Các bước thường là **GetObjectClass(env, self)** → **GetFieldID** → **GetIntField(env, self, ...)**.

**jobject là reference opaque của JVM**, không phải địa chỉ bố cục object mà C có thể tùy tiện dereference. JVM có quyền dùng representation riêng và garbage collector có thể di chuyển đối tượng. Không suy ra layout Java object hoặc trỏ thẳng tới field bằng phép tính offset trên **jobject**.

Trong một lời gọi Java instance hợp lệ, JVM cung cấp receiver object cho phương thức native; nếu gọi instance method với receiver **null** từ Java, lời gọi thất bại trước khi thực thi body native. Tuy nhiên, các đối số object khác do Java truyền vẫn có thể là **null** và cần được kiểm tra tùy API.

**jobject** là kiểu tổng quát của object reference trong JNI; các subtype như **jstring**, **jarray**, **jobjectArray**, **jclass** dùng theo vai trò cụ thể. Không cast bừa reference chỉ để tránh kiểm tra type; dùng các JNI API phù hợp.

## 4. Tham số thứ hai là jclass khi nào?

Với phương thức **static native**, JVM không có receiver **this**; tham số thứ hai là **jclass**, một reference đến đối tượng **java.lang.Class** đại diện cho **lớp khai báo phương thức native**.

~~~java
class Converter {
    private static int factor = 3;

    static native int multiply(int value);
}
~~~

Hàm native tương ứng:

~~~c
JNIEXPORT jint JNICALL Java_Converter_multiply(
        JNIEnv *env, jclass clazz, jint value);
~~~

Native code có thể dùng **clazz** ngay với **GetStaticFieldID(env, clazz, "factor", "I")** rồi **GetStaticIntField(env, clazz, ...)**. Nếu cố dùng **GetIntField** như instance field trên **clazz**, sẽ vi phạm hợp đồng API.

**jclass là JNI reference đến đối tượng Class**, không phải con trỏ kiểu C đến phần memory layout của class, không phải instance **Converter**, và không có khả năng đọc instance field khi thiếu một instance phù hợp. Ví dụ **GetObjectClass(env, clazz)** trả về lớp runtime của đối tượng **Class** (thường là **java.lang.Class**), không phải thao tác để lấy lại **Converter.class**: **clazz** đã đại diện cho lớp cần dùng.

| Câu hỏi | jobject trong instance native | jclass trong static native |
| --- | --- | --- |
| Đại diện cho | Đối tượng nhận lời gọi, tương đương **this** | Đối tượng **Class** của lớp khai báo method |
| Dữ liệu thường truy cập | Instance fields/methods | Static fields/methods |
| Lấy loại lớp để tra instance field | **GetObjectClass(env, self)** | Đã có **clazz** cho static members |
| Có phải địa chỉ C để dereference? | Không | Không |
| Lifetime khi JVM truyền vào native method | Local reference cho lời gọi hiện tại | Local reference cho lời gọi hiện tại |

## 5. Ví dụ hoàn chỉnh Java 17+ gọi cả instance và static native

Bài thực hành dưới đây dùng Java và C thuần, không yêu cầu Spring/Gradle. Cả hai phương thức đều nhận tham số **int** từ Java, nhưng native implementation truy cập hai loại field khác nhau để thấy rõ vai trò của tham số JNI thứ hai.

### 5.1. File FirstJni.java

Lưu file với **tên chính xác FirstJni.java**, không khai báo **package** để giữ tên C dễ đọc:

~~~java
public final class FirstJni {
    private final int base;
    private static int factor = 3;

    static {
        System.loadLibrary("firstjni");
    }

    public FirstJni(int base) {
        this.base = base;
    }

    // JVM se truyen JNIEnv*, jobject truoc tham so value.
    public native int addToBase(int value);

    // JVM se truyen JNIEnv*, jclass truoc tham so value.
    public static native int scale(int value);

    public static void main(String[] args) {
        FirstJni demo = new FirstJni(10);
        System.out.println("instance=" + demo.addToBase(5));
        System.out.println("static=" + FirstJni.scale(7));
    }
}
~~~

Từ Java, **addToBase(5)** được gọi trên instance có **base = 10**; **scale(7)** thuộc class có static field **factor = 3**. Lệnh **System.loadLibrary("firstjni")** tải thư viện native theo quy tắc tên của hệ điều hành. Tham số của **loadLibrary** là tên logic **firstjni**, không ghi tiền tố **lib** hoặc đuôi **.so/.dll/.dylib**.

### 5.2. Sinh header JNI từ chữ ký Java

Mở terminal có JDK 17+ và chạy tại thư mục chứa file:

~~~bash
javac -h . FirstJni.java
~~~

**javac** biên dịch **FirstJni.class** đồng thời tạo **FirstJni.h**. Trong header sẽ có các prototype tương ứng với:

~~~c
JNIEXPORT jint JNICALL Java_FirstJni_addToBase
        (JNIEnv *, jobject, jint);

JNIEXPORT jint JNICALL Java_FirstJni_scale
        (JNIEnv *, jclass, jint);
~~~

Hai tham số đầu được thêm ngầm, vì vậy khai báo Java chỉ có một **int value** nhưng C có ba đối số. Cùng một tên **FirstJni**, native instance và static được phân biệt tại **kiểu tham số thứ hai**. Không tự đổi thứ tự hoặc đổi **jobject** thành **jclass** chỉ vì chúng thường có representation pointer tương tự; API và hợp đồng signature khác nhau.

Nếu có **package**, dấu gạch dưới hoặc overload, tên symbol có quy tắc escape/suffix riêng. Hãy xem **header thật do javac -h tạo ra**; đây là cách chắc chắn hơn việc tự viết tên **Java_...** theo cảm tính.

### 5.3. File FirstJni.c

Lưu file C sau trong cùng thư mục với **FirstJni.h**:

~~~c
#include <jni.h>
#include "FirstJni.h"

/*
 * Instance native:
 * - env: cac ham JNI cua JVM
 * - self: doi tuong FirstJni nhan loi goi
 * - value: tham so int do Java truyen
 */
JNIEXPORT jint JNICALL Java_FirstJni_addToBase(
        JNIEnv *env, jobject self, jint value) {

    jclass receiverClass = (*env)->GetObjectClass(env, self);
    if (receiverClass == NULL) {
        return 0; /* JVM exception dang cho neu thao tac that bai */
    }

    jfieldID baseField =
            (*env)->GetFieldID(env, receiverClass, "base", "I");

    (*env)->DeleteLocalRef(env, receiverClass);

    if (baseField == NULL) {
        return 0; /* Vi du: NoSuchFieldError dang cho */
    }

    jint base = (*env)->GetIntField(env, self, baseField);
    return base + value;
}

/*
 * Static native:
 * - env: cac ham JNI cua JVM
 * - clazz: doi tuong Class cua FirstJni
 * - value: tham so int do Java truyen
 */
JNIEXPORT jint JNICALL Java_FirstJni_scale(
        JNIEnv *env, jclass clazz, jint value) {

    jfieldID factorField =
            (*env)->GetStaticFieldID(env, clazz, "factor", "I");

    if (factorField == NULL) {
        return 0; /* Vi du: NoSuchFieldError dang cho */
    }

    jint factor =
            (*env)->GetStaticIntField(env, clazz, factorField);

    return value * factor;
}
~~~

**Giải thích từng đường đi:**

1. **Java_FirstJni_addToBase** nhận **self**, gọi **GetObjectClass** để lấy reference đến class runtime của instance; **GetFieldID** tìm field **base** có descriptor **"I"** (Java **int**); **GetIntField** đọc **base** của chính **self**. Vì **base=10** và **value=5**, kết quả là **15**.
2. **Java_FirstJni_scale** nhận trực tiếp **clazz**, nên dùng **GetStaticFieldID** tìm static field **factor** cùng descriptor **"I"**, rồi **GetStaticIntField** lấy **factor=3**. Vì **value=7**, kết quả là **21**.
3. **GetObjectClass** tạo local reference mới nên **DeleteLocalRef** giải phóng nó sau khi dùng. **jfieldID** là ID field, không phải **jobject** và không được đưa vào **DeleteLocalRef**.
4. Khi **GetFieldID/GetStaticFieldID** trả **NULL** do lỗi, một Java exception thích hợp có thể đang pending. Đoạn mẫu trả **0** để thoát body C, nhưng nếu có exception pending thì Java nhận ngoại lệ chứ không coi **0** là kết quả thành công. Với chương trình production, cần thiết kế đường xử lý lỗi đầy đủ và bảo đảm không tiếp tục gọi các JNI API bị cấm trong trạng thái pending exception.
5. Hai phép toán nhỏ trong ví dụ không overflow **jint**. Khi làm số học thực tế, **jint** tương ứng Java **int** signed 32-bit; phải kiểm tra miền giá trị và quy tắc overflow, nhất là khi kết hợp C **long**, **size_t** hoặc con trỏ.

**Vì sao đọc được private field?** JNI có API tra cứu field theo lớp, tên, descriptor và có thể truy cập field **private** trong ví dụ. Không có cú pháp **self->base** hay **clazz->factor** trên JNI references.

### 5.4. Biên dịch thư viện trên Linux

Cần compiler C và biến môi trường **JAVA_HOME** trỏ đến JDK khớp kiến trúc của JVM. Dùng shell:

~~~bash
javac -h . FirstJni.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  FirstJni.c -o libfirstjni.so

java -cp . -Djava.library.path=. FirstJni
~~~

### 5.5. Biên dịch thư viện trên macOS

Thay thư mục JNI platform header và kiểu thư viện động:

~~~bash
javac -h . FirstJni.java

cc -std=c11 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  FirstJni.c -o libfirstjni.dylib

java -cp . -Djava.library.path=. FirstJni
~~~

### 5.6. Biên dịch thư viện trên Windows (MSVC)

Trong **x64 Native Tools Command Prompt for Visual Studio** có **cl** và JDK **JAVA_HOME**:

~~~bat
javac -h . FirstJni.java

cl /nologo /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" FirstJni.c /Fe:firstjni.dll

java -cp . -Djava.library.path=. FirstJni
~~~

Chọn đúng compiler/linker và cùng kiến trúc giữa JDK/JVM và DLL/shared library; thư viện 32-bit không tải được vào tiến trình JVM 64-bit. Các lệnh trên minh họa trường hợp build native ngay trên target thông dụng; khi cross-compile phải dùng đúng compiler, sysroot, JNI headers và ABI tương ứng.

**Stdout của cả ba bản build khi thành công:**

~~~text
instance=15
static=21
~~~

Cú pháp dùng với **.c**, vì code viết theo JNI C API. Nếu chuyển sang C++, phải biên dịch như C++, điều chỉnh cú pháp gọi API và linkage theo **jni.h**; không đơn giản đổi đuôi file rồi giữ nguyên mọi biểu thức **(*env)->...**.

## 6. Phân tích chính xác hai lời gọi chạy qua JVM

~~~text
new FirstJni(10).addToBase(5)
        |
        | Native method khong static
        v
JNIEXPORT jint Java_FirstJni_addToBase(
    JNIEnv *env,      // interface cua current Java thread
    jobject self,     // instance FirstJni(base=10)
    jint value        // 5
)
        |
        v
GetObjectClass(self) -> GetFieldID("base","I")
        -> GetIntField(self) -> 10 + 5 -> 15

FirstJni.scale(7)
        |
        | Static native method
        v
JNIEXPORT jint Java_FirstJni_scale(
    JNIEnv *env,      // interface cua current Java thread
    jclass clazz,     // Class object cua FirstJni
    jint value        // 7
)
        |
        v
GetStaticFieldID(clazz,"factor","I")
        -> GetStaticIntField(clazz) -> 7 * 3 -> 21
~~~

Thứ tự **env, receiver/class, các tham số Java** áp dụng ngay cả khi Java native method không có tham số. Ví dụ **native void ping()** vẫn nhận **(JNIEnv \*, jobject)**; **static native void pingGlobal()** vẫn nhận **(JNIEnv \*, jclass)**. Khi phương thức có nhiều đối số, chúng xuất hiện tiếp theo đúng thứ tự Java, với kiểu JNI tương ứng.

## 7. Kiểu dữ liệu JNI, signature và Java reflection

Hai tham số đầu **không** là phần của **Java method descriptor**. Với **addToBase(int)** trả **int**, descriptor là **(I)I**, không có ký tự nào mô tả **JNIEnv \*** hoặc **this**. Với **scale(int)** cũng là **(I)I**: thông tin static/instance là thuộc tính method, không phải đối số thứ hai được khai báo bởi Java.

Một số ánh xạ cơ bản:

| Java | C JNI | Ghi chú |
| --- | --- | --- |
| **boolean** | **jboolean** | Dùng **JNI_TRUE/JNI_FALSE** cho giá trị logic |
| **byte**, **short**, **char** | **jbyte**, **jshort**, **jchar** | Java **char** là UTF-16 code unit unsigned 16-bit |
| **int**, **long** | **jint**, **jlong** | Java **int** 32-bit, **long** 64-bit; C **long** không cố định 64-bit |
| **float**, **double** | **jfloat**, **jdouble** | Độ rộng tương ứng Java |
| **String** | **jstring** | Reference đến Java String |
| Đối tượng Java bất kỳ | **jobject** hoặc subtype JNI | Reference opaque, có thể null nếu do Java truyền |
| **Class<?>** | **jclass** | Java class object reference |
| **void** | **void** | Không có giá trị trả về |

Các field descriptor thông dụng: **I=int**, **J=long**, **Z=boolean**, **D=double**, **Ljava/lang/String;=String**, **[I=int[]**. Trong ví dụ, **"I"** truyền cho **GetFieldID/GetStaticFieldID** vì cả **base** và **factor** đều là Java **int**. Cần dùng đúng descriptor kể cả khi hai kiểu C có kích thước giống nhau trên một platform.

Một prototype native sai có thể biên dịch C thành công nếu không include header khớp, nhưng JVM gọi theo ABI/calling convention khác và gây lỗi nghiêm trọng. Bởi vậy nên include header do **javac -h** tạo ra trong file native và để compiler kiểm tra declaration/definition. **JNIEXPORT** yêu cầu exported symbol phù hợp, **JNICALL** áp dụng calling convention cần thiết theo platform, còn **Java_FirstJni_addToBase** là tên export theo quy tắc JNI (trừ khi dùng đăng ký động).

## 8. Lifetime của env, jobject và jclass

Ba tham số này **không** có cùng quy tắc lifetime:

| Thành phần | Phạm vi an toàn cơ bản | Không được làm |
| --- | --- | --- |
| **JNIEnv \*** | Thread đang thực hiện lời gọi JNI | Cache và gọi từ thread khác |
| **jobject self** do JVM truyền | Local reference trong native call hiện tại | Giữ raw reference trong biến global để dùng ở lần gọi sau |
| **jclass clazz** do JVM truyền | Local reference trong native call hiện tại | Cache raw **jclass** và giả định tồn tại mãi |
| **jfieldID / jmethodID** | ID của thành viên còn thuộc lớp hợp lệ | Coi như **jobject** hoặc giữ qua class unloading mà không quản lý vòng đời lớp |

JVM theo dõi **local references** được truyền hoặc tạo trong lời gọi; chúng hợp lệ trong chính thread đó và thường tự được giải phóng sau khi native method trả về. Reference mới có được từ **GetObjectClass** trong ví dụ đã được giải phóng sớm bằng **DeleteLocalRef**. Đừng tự gọi **DeleteLocalRef** trên **self**/**clazz** được JVM cấp rồi tiếp tục dùng chúng.

Nếu cần giữ đối tượng hay lớp sau khi native method kết thúc, phải cân nhắc **NewGlobalRef** tạo **global reference**, kiểm tra khả năng trả **NULL** khi cấp phát thất bại, rồi **DeleteGlobalRef** khi không còn dùng. Global reference vẫn phải được quản lý để tránh giữ object/class loader sống ngoài ý muốn. Nếu chỉ cần tham chiếu yếu, JNI có **weak global references** với semantics khác. Không truyền **local reference** sang native thread khác.

Hai JNI reference khác nhau có thể trỏ đến cùng Java object; **so sánh trực tiếp giá trị con trỏ bằng == không phải cách portable để so identity**. Dùng **(*env)->IsSameObject(env, a, b)** trong C hoặc **env->IsSameObject(a, b)** trong C++.

## 9. Static hay instance: quyết định theo mô hình Java

Phân biệt **jobject/jclass** dựa trên **khai báo native method**, không dựa trên tên biến, Java caller cụ thể hay body C.

- Nếu native method cần trạng thái của một object riêng biệt (**base**, **id**, buffer instance, native handle gắn với object), hãy chọn **instance native** và nhận **jobject**.
- Nếu native method biểu diễn thao tác mức lớp, factory hoặc tính toán không phụ thuộc receiver, có thể chọn **static native** và nhận **jclass**. Nếu muốn truy cập dữ liệu của một instance trong static native, cần instance ấy được truyền như đối số Java tường minh.
- Method **static native** vẫn có thể nhận **Object** do người gọi truyền; khi đó chữ ký C là **(JNIEnv \*, jclass, jobject ...)**. **jclass** vẫn là tham số ngầm thứ hai, **jobject** được truyền thêm là đối số thật.
- Method **instance native** có thể nhận thêm **Class<?>** từ Java; chữ ký C lúc này là **(JNIEnv \*, jobject, jclass ...)**. Không nhầm **jclass** do Java truyền ở vị trí sau với tham số ngầm thứ hai.

Ví dụ tương phản về loại tham số (đoạn khai báo, không phải chương trình độc lập):

~~~java
class BindingCases {
    static native void inspect(Object suppliedObject);
    native void inspectClass(Class<?> suppliedClass);
}
~~~

~~~c
/* Dạng chữ ký logic; có thể đặt tên C theo header sinh ra. */
JNIEXPORT void JNICALL Java_BindingCases_inspect(
        JNIEnv *env, jclass declaringClass, jobject suppliedObject);

JNIEXPORT void JNICALL Java_BindingCases_inspectClass(
        JNIEnv *env, jobject receiver, jclass suppliedClass);
~~~

**Vị trí**, không chỉ tên kiểu, quyết định tham số nào do JVM cung cấp ngầm.

## 10. Điều gì thay đổi khi dùng C++ hoặc RegisterNatives?

**C++:** vẫn luôn nhận **JNIEnv \*** rồi **jobject/jclass**. Khác biệt chủ yếu là cách gọi JNI API và linkage khi export. Một đoạn native C++ minh họa:

~~~cpp
#include <jni.h>
#include "FirstJni.h"

extern "C" JNIEXPORT jint JNICALL Java_FirstJni_scale(
        JNIEnv *env, jclass clazz, jint value) {

    jfieldID field = env->GetStaticFieldID(clazz, "factor", "I");
    if (field == nullptr) {
        return 0;
    }
    return value * env->GetStaticIntField(clazz, field);
}
~~~

Đây là **một implementation thay thế của scale** để minh họa cú pháp C++; không biên dịch đồng thời nó với **FirstJni.c** vào cùng thư viện nếu cả hai định nghĩa cùng symbol. Nếu dùng C++ toàn bộ, đổi các native function khác theo cú pháp tương ứng và cấu hình compiler/linker C++.

**RegisterNatives:** JNI còn cho phép ánh xạ Java native method đến function pointer C/C++ bằng **RegisterNatives**. Khi dùng cách này, hàm không bắt buộc tên export kiểu **Java_Class_method**, nhưng **chữ ký gọi vẫn bắt đầu với JNIEnv \* và jobject hoặc jclass đúng loại**, rồi mới đến đối số Java. Phải đăng ký đúng method name và descriptor, bảo đảm pointer có chữ ký ABI tương thích; sai kiểu có thể gây crash. Khi mới học JNI, cách **javac -h** và liên kết symbol truyền thống đơn giản hơn để quan sát đúng chữ ký.

## 11. Ngoại lệ và quy tắc an toàn khi sử dụng tham số JNI

Bất kỳ khi nào gọi JNI API qua **env**, kiểm tra tài liệu về kiểu trả về và lỗi:

1. **GetObjectClass** tạo **jclass** local reference; nếu thất bại và trả **NULL**, không được đưa **NULL** cho **GetFieldID**.
2. **GetFieldID** dành cho **instance field**; **GetStaticFieldID** dành cho **static field**. Hai API nhận một **jclass** làm ngữ cảnh tra cứu, nhưng cách đọc giá trị sau đó khác nhau: **GetIntField** nhận **jobject**; **GetStaticIntField** nhận **jclass**.
3. Khi có Java exception đang pending, nhiều JNI API không được phép gọi; muốn kiểm tra có thể dùng **ExceptionCheck**, và các thao tác dọn dẹp hợp lệ như **DeleteLocalRef** vẫn được phép. Thông thường để ngoại lệ pending truyền về Java, không xóa ngoại lệ chỉ để nhận một số trả về giả.
4. Việc đọc/ghi dữ liệu Java phải qua JNI API; đừng cast **jobject** sang con trỏ tới struct C, lưu raw **JNIEnv \*** để dùng sau, hoặc giả định field ID là con trỏ bộ nhớ.
5. Khi native method được nhiều Java thread gọi đồng thời, mỗi call có **env** và reference ngầm theo thread/call, nhưng biến **static** Java hay trạng thái C global vẫn có thể được các thread chia sẻ; cần đồng bộ riêng nếu chỉnh sửa đồng thời.

Không có chỉ dẫn nào cho phép mã C dereference **jobject** như Java object. Dùng công cụ **-Xcheck:jni** trong HotSpot khi cần phát hiện nhiều lỗi sử dụng JNI lúc chạy (tùy JVM và phiên bản):

~~~bash
java -Xcheck:jni -cp . -Djava.library.path=. FirstJni
~~~

Chế độ kiểm tra bổ sung không bảo đảm bắt tất cả lỗi C, memory safety, race hoặc sai ABI.

## 12. Lỗi thường gặp khi viết hàm JNI đầu tiên

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| **UnsatisfiedLinkError: no firstjni in java.library.path** | Thư viện sai tên hoặc không nằm trong đường tìm kiếm | Kiểm tra **System.loadLibrary("firstjni")**, tên file **libfirstjni.so / libfirstjni.dylib / firstjni.dll**, **java.library.path** |
| **UnsatisfiedLinkError** khi gọi method | Symbol native sai tên/package, thư viện chưa có hàm hoặc sai overload | Chạy **javac -h .** rồi khớp chính xác prototype và export |
| Biên dịch C báo lỗi về **GetObjectClass** | Dùng cú pháp C++ **env->...** trong file C | Dùng **(*env)->GetObjectClass(env, ...)** |
| Biên dịch C++ báo lỗi về cách gọi JNI | Giữ nguyên cú pháp dành cho C | Dùng **env->GetObjectClass(...)** |
| Native method instance bị khai báo đối số thứ hai là **jclass** | Nhầm static/instance; prototype không khớp | So lại **native** và **static native** ở Java/header |
| Native method static dùng **GetIntField** trên **clazz** | **clazz** là Class object, không phải instance | Dùng **GetStaticFieldID/GetStaticIntField**, hoặc nhận instance qua đối số tường minh |
| **NoSuchFieldError** hoặc field ID **NULL** | Sai tên, descriptor, field static/instance hoặc class | Kiểm tra **"base","I"** và **"factor","I"** cùng API tương ứng |
| Crash/JVM fatal error khi thao tác reference | Dereference/cast opaque reference, dùng reference sau lifetime, sai ABI | Dùng JNI API, quản lý local/global references, kiểm tra header/architecture |
| Crash hoặc hành vi lạ từ native thread | Dùng lại **JNIEnv \*** của thread khác | Attach thread để nhận env của thread đó; detach đúng lúc |
| C++ build có lỗi symbol | C++ name mangling hoặc thiếu export/linkage đúng | Include header từ **javac -h**, bảo đảm **extern "C"** và **JNIEXPORT/JNICALL** |
| JVM báo sai kiến trúc khi load thư viện | JVM 64-bit nhưng DLL/.so khác bitness hoặc ABI | Build cùng architecture với JVM và dùng native compiler/linker đúng target |

Khi debug, tách rõ ba giai đoạn: **load library**, **resolve đúng native symbol**, **thực thi JNI API đúng kiểu/thread/lifetime**. Sự cố tại mỗi giai đoạn có nguyên nhân khác nhau và không được giải quyết bằng cách cast tùy tiện.

## 13. Tự kiểm tra nhanh

**Câu 1.** Java khai báo **public native long read(int id)**. Hàm C phải bắt đầu bằng kiểu nào?

**Đáp án:** **jlong Java_..._read(JNIEnv \*env, jobject self, jint id)** với các macro **JNIEXPORT/JNICALL** đúng chuẩn; tham số **env** và **self** được JVM thêm trước đối số **id**. Kiểu trả về **jlong** tương ứng Java **long**, không mặc định dùng C **long**.

**Câu 2.** Java khai báo **public static native String format(int id)**. Tham số thứ hai của hàm C là gì?

**Đáp án:** **jclass clazz**, đại diện cho class khai báo native method; kiểu trả về **jstring**, đối số Java **int id** ánh xạ **jint id**. Không có instance **this**.

**Câu 3.** Trong hàm static native, có **jclass clazz**; dùng **GetObjectClass(env, clazz)** để lấy class khai báo method là đúng hay sai?

**Đáp án:** Sai về mục đích. **clazz** đã là Class object đại diện cho lớp. **GetObjectClass(env, clazz)** hỏi lớp runtime của chính object **java.lang.Class**, không phải lấy lại class mà **clazz** biểu diễn.

**Câu 4.** Có thể giữ **JNIEnv \*env** nhận được từ một native callback trong global để worker thread C gọi Java hôm sau không?

**Đáp án:** Không. **JNIEnv \*** chỉ hợp lệ trên thread của nó. Native thread muốn truy cập JVM phải attach để lấy env của chính thread, và quản lý reference/lifecycle độc lập; object cần giữ vượt call phải được quản lý bằng JNI global reference phù hợp.

**Câu 5.** Vì sao phương thức Java chỉ khai báo một tham số nhưng hàm C lại có ba?

**Đáp án:** JVM bổ sung **JNIEnv \*** và **jobject/jclass** ở hai vị trí đầu; chỉ tham số thứ ba mới đến từ khai báo Java. Đó là hợp đồng gọi JNI, không phải hai tham số Java ẩn có thể truy cập qua Java reflection.

## Tài liệu tra cứu

- Oracle Java 21 — JNI Design Overview (JNI interface pointer, native arguments, linking và references): https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html
- Oracle Java 21 — JNI Functions (GetObjectClass, GetFieldID, GetStaticFieldID, GetIntField, GetStaticIntField, reference APIs): https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html
- Oracle Java 21 — JNI Types and Data Structures: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html
- Oracle Java 21 — JNI Invocation API (AttachCurrentThread, DetachCurrentThread): https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html

**Điểm cần ghi nhớ:** Mỗi native method nhận **JNIEnv \*** đầu tiên. Phương thức **instance** nhận **jobject self** thứ hai; phương thức **static** nhận **jclass clazz** thứ hai. Những tham số thật do Java khai báo đến sau. Luôn dùng JNI API đúng với vai trò của từng reference, giữ đúng thread/lifetime và sinh header từ Java để bảo đảm chữ ký C/C++ khớp với JVM.