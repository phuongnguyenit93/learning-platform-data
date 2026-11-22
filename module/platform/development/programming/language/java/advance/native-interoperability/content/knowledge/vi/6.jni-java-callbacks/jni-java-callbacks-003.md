# Lấy `jmethodID` và `jfieldID` theo tên, chữ ký chính xác trong JNI

## 1. Mục đích: native code gọi phương thức và truy cập trường Java

Khi Java gọi vào C/C++ bằng Java Native Interface (JNI), mã bản địa có thể cần **gọi ngược phương thức Java** hoặc **đọc/ghi trường của đối tượng Java**. JNI không nhận một tên đơn lẻ như `"add"` hay `"balance"` rồi tự chọn đúng thành viên: native code phải cung cấp **class, tên thành viên, chữ ký kiểu (descriptor)** và chọn đúng hàm tra cứu **instance hay static**.

JNI giải quyết việc này qua hai loại ID:

- **`jmethodID`:** định danh *một phương thức hoặc constructor*; dùng cùng các hàm `Call<Type>Method`, `CallStatic<Type>Method` hay `NewObject`.
- **`jfieldID`:** định danh *một trường*; dùng cùng các hàm `Get<Type>Field`, `Set<Type>Field`, `GetStatic<Type>Field`, `SetStatic<Type>Field`.

Cả hai là **ID opaque do JVM cấp**, không phải `jobject` và không phải địa chỉ trường C thông thường. Không dereference, không ép chúng thành offset bộ nhớ và **không gọi `DeleteLocalRef` cho `jmethodID`/`jfieldID`**. Chúng là thành phần của hợp đồng ABI/JVM, được cấp sau khi tra cứu.

Chuỗi thao tác thường gặp:

```text
Java object / class
         │
         ▼
GetObjectClass / FindClass → jclass
         │
         ├── GetMethodID(class, "add", "(I)I") ────→ jmethodID
         │                                           │
         │                                           ▼
         │                                    CallIntMethod(obj, ...)
         │
         └── GetFieldID(class, "count", "I") ────→ jfieldID
                                                     │
                                                     ▼
                                              GetIntField(obj, ...)
                                              SetIntField(obj, ...)
```

**Phân biệt hai tên dễ gây nhầm:** `GetMethodID` *tìm định danh* của phương thức, còn `CallIntMethod` *thực thi* phương thức đã tìm; `GetFieldID` *tìm định danh* của trường, còn `GetIntField` *đọc giá trị* từ một đối tượng.

## 2. Bốn API tra cứu chính

| Thành viên Java cần tra cứu | Hàm JNI (C) | Kết quả | Ví dụ |
| --- | --- | --- | --- |
| Phương thức **instance** | `GetMethodID(env, cls, name, signature)` | `jmethodID` | `add(int): int` → `"(I)I"` |
| Phương thức **static** | `GetStaticMethodID(env, cls, name, signature)` | `jmethodID` | `describe(int,int): String` → `"(II)Ljava/lang/String;"` |
| Trường **instance** | `GetFieldID(env, cls, name, signature)` | `jfieldID` | `int count` → `"I"` |
| Trường **static** | `GetStaticFieldID(env, cls, name, signature)` | `jfieldID` | `static int scale` → `"I"` |

Tên và chữ ký phải tương thích với **khai báo thực sự trong bytecode**, kể cả trường `private`. Một chữ ký đúng nhưng chọn sai họ static/instance vẫn là lỗi. `GetMethodID` không thay thế được `GetStaticMethodID`; `GetFieldID` không thay thế được `GetStaticFieldID`.

Ví dụ các lời gọi C cơ bản:

```c
jfieldID countId =
    (*env)->GetFieldID(env, cls, "count", "I");
jfieldID scaleId =
    (*env)->GetStaticFieldID(env, cls, "scale", "I");

jmethodID addId =
    (*env)->GetMethodID(env, cls, "add", "(I)I");
jmethodID describeId =
    (*env)->GetStaticMethodID(
        env, cls, "describe", "(II)Ljava/lang/String;");
```

Đoạn mã này **minh họa cách tra cứu**, giả định `env` và `cls` đã hợp lệ; ở mục 5 có chương trình đầy đủ với kiểm tra lỗi, biên dịch và chạy.

Các đối số có ý nghĩa:

- `env`: `JNIEnv *` của **luồng hiện tại**.
- `cls`: `jclass` cho class/interface cần tra cứu, không phải tên class dạng chuỗi.
- `name`: **tên chính xác**, phân biệt chữ hoa/chữ thường, ví dụ `"add"` khác `"Add"`.
- `signature`: **descriptor JVM chính xác**, truyền dưới dạng chuỗi C kết thúc bởi byte NUL; với tên Unicode, giao diện JNI sử dụng modified UTF-8. Ví dụ trong bài chỉ dùng tên ASCII.
- Giá trị trả về: ID hợp lệ hoặc `NULL` khi không tra cứu được; khi thất bại thường có **Java exception pending** như `NoSuchMethodError` hoặc `NoSuchFieldError`.

Một lần tra cứu có thể kích hoạt **class initialization** nếu class chưa được khởi tạo. Vì thế lỗi `ExceptionInInitializerError` hoặc `OutOfMemoryError` cũng phải được tính đến, không mặc định mọi `NULL` đều chỉ vì gõ sai tên.

## 3. Cách viết descriptor của trường và phương thức

JNI dùng **descriptor của JVM**, không dùng cú pháp source Java như `int`, `String`, `List<String>`. Đây là nguồn lỗi phổ biến nhất khi tìm ID.

### 3.1. Kiểu nguyên thủy

| Java | Descriptor | Kiểu JNI thường gặp |
| --- | --- | --- |
| `boolean` | `Z` | `jboolean` |
| `byte` | `B` | `jbyte` |
| `char` | `C` | `jchar` |
| `short` | `S` | `jshort` |
| `int` | `I` | `jint` |
| `long` | `J` | `jlong` |
| `float` | `F` | `jfloat` |
| `double` | `D` | `jdouble` |
| `void` | `V` | Chỉ dùng làm **kiểu trả về phương thức**, không phải kiểu trường |

Không nhầm `C` (`char`) với `L...;` (tham chiếu class). `J` là `long`, không phải `L`.

### 3.2. Kiểu đối tượng, mảng và class lồng nhau

- `java.lang.String` → `Ljava/lang/String;`.
- `java.lang.Object` → `Ljava/lang/Object;`.
- `java.util.List` → `Ljava/util/List;`.
- `int[]` → `[I`; `int[][]` → `[[I`.
- `String[]` → `[Ljava/lang/String;`.
- `demo.model.User` → `Ldemo/model/User;`.
- `Outer.Inner` là member class → dùng **binary name** có dấu `$`: ví dụ `Ldemo/model/Outer$Inner;`.

Trong descriptor, tên package/class dùng dấu **`/`**, đặt giữa `L` và dấu **`;`**. Viết `Ljava.lang.String;` (dấu chấm), thiếu dấu chấm phẩy, hoặc viết `LString;` thay cho tên class đầy đủ đều có thể khiến lookup thất bại.

**Generics không xuất hiện nguyên dạng trong descriptor**: trường `List<String> names` có descriptor `Ljava/util/List;` sau type erasure, không phải `Ljava/util/List<Ljava/lang/String;>;`. Varargs `String... args` ở bytecode là mảng `[Ljava/lang/String;`.

### 3.3. Descriptor cho phương thức

Công thức:

```text
(<descriptor tham số 1><descriptor tham số 2>...)<descriptor trả về>
```

Các tham số nối liền nhau, **không có dấu phẩy, khoảng trắng hay tên biến**. Kiểu trả về nằm **ngoài** cặp ngoặc. Ví dụ:

| Khai báo Java | Descriptor JNI |
| --- | --- |
| `int add(int x, int y)` | `(II)I` |
| `void log()` | `()V` |
| `String format(int n)` | `(I)Ljava/lang/String;` |
| `boolean contains(String text, int[] values)` | `(Ljava/lang/String;[I)Z` |
| `long count(byte[] data, String prefix)` | `([BLjava/lang/String;)J` |
| `String[] split(String s)` | `(Ljava/lang/String;)[Ljava/lang/String;` |
| `void accept(String... args)` | `([Ljava/lang/String;)V` |

Một phương thức không có tham số dùng `()`, không bỏ ngoặc. **Kiểu trả về là thành phần bắt buộc của descriptor**: `(I)I` khác `(I)V`. Khi nhiều phương thức overload cùng tên, descriptor giúp định danh đúng phiên bản, ví dụ `foo(int)` là `(I)V` và `foo(long)` là `(J)V` nếu đều trả `void`.

### 3.4. Field descriptor khác method descriptor

Trường `int count` có chữ ký **`"I"`**, không phải `"()I"`. Phương thức `int getCount()` có chữ ký **`"()I"`**, không phải `"I"`. Hai chuỗi không thể thay thế nhau. Cũng không có field có kiểu `void`.

Đối với constructor có tham số `(int, String)`, `GetMethodID` sử dụng tên đặc biệt **`"<init>"`** và descriptor `"(ILjava/lang/String;)V"`, rồi `NewObject` dùng ID này để tạo instance. `<init>` không phải tên một Java method bình thường; không tra cứu static initializer `<clinit>` bằng cách này.

## 4. Từ ID tới thao tác đúng kiểu

Lookup chỉ là bước một. Để **đọc, ghi, gọi**, chọn hàm tương ứng với **static/instance** và **kiểu thật** của member.

| Thành viên | Lấy ID | Truy cập đúng |
| --- | --- | --- |
| `int count` instance | `GetFieldID(...,"count","I")` | `GetIntField(env,obj,id)` / `SetIntField(env,obj,id,value)` |
| `static int scale` | `GetStaticFieldID(...,"scale","I")` | `GetStaticIntField(env,cls,id)` / `SetStaticIntField(env,cls,id,value)` |
| `String name` instance | `GetFieldID(...,"name","Ljava/lang/String;")` | `GetObjectField(env,obj,id)` / `SetObjectField(...)` |
| `int add(int)` instance | `GetMethodID(...,"add","(I)I")` | `CallIntMethod(env,obj,id,arg)` |
| `static String describe(int,int)` | `GetStaticMethodID(...,"describe","(II)Ljava/lang/String;")` | `CallStaticObjectMethod(env,cls,id,arg1,arg2)` |
| `void done()` instance | `GetMethodID(...,"done","()V")` | `CallVoidMethod(env,obj,id)` |

`GetObjectField` trả một **JNI local reference** tới giá trị đối tượng (có thể là `NULL`); giá trị reference này **khác** `jfieldID`. `CallObjectMethod` trả một reference tới đối tượng kết quả (hoặc `NULL`); nó **khác** `jmethodID`. Các họ gọi khác gồm `CallLongMethod`, `CallBooleanMethod` và `CallStaticVoidMethod`.

Các lệnh `Call<Type>MethodA` nhận mảng `jvalue`; `Call<Type>MethodV` nhận `va_list`, phù hợp khi đóng gói tham số động. Vẫn phải có descriptor và ID đúng. `CallNonvirtual<Type>Method` dành cho hành vi dispatch đặc biệt, không thay thế mặc định cho `Call<Type>Method`.

## 5. Ví dụ hoàn chỉnh Java 17+: lấy cả hai ID, gọi method và đọc/ghi field

Ví dụ này trình bày **đủ bốn API tra cứu**, không phụ thuộc thư viện bên ngoài. Java có một instance field, một static field, một instance method và một static method. C lấy ID theo tên/descriptor, đọc trạng thái, gọi Java để tính, cập nhật field, rồi gọi Java tạo chuỗi kết quả.

### 5.1. Cấu trúc dự án

```text
jni-id-lookup/
├── src/
│   └── demo/
│       └── jni/
│           └── IdLookupDemo.java
├── native/
│   └── idlookup.c
└── build/                   # được sinh trong quá trình build
```

Các lệnh bên dưới dành cho **Linux + JDK 17+ + GCC**. Trên Windows/macOS, tên file thư viện chia sẻ và đường dẫn include của JNI khác nhau; Java source và các descriptor giữ nguyên.

### 5.2. Tạo `src/demo/jni/IdLookupDemo.java`

```java
package demo.jni;

public final class IdLookupDemo {
    static {
        System.loadLibrary("idlookup");
    }

    private int count = 7;            // instance field: I
    private static int scale = 3;     // static field: I

    private int add(int delta) {      // instance method: (I)I
        return count + delta;
    }

    private static String describe(int before, int after) {
        // static method: (II)Ljava/lang/String;
        return "count " + before + " -> " + after;
    }

    private native String inspectAndUpdate();

    public static void main(String[] args) {
        IdLookupDemo demo = new IdLookupDemo();
        System.out.println("Before: " + demo.count);
        System.out.println("Native: " + demo.inspectAndUpdate());
        System.out.println("After: " + demo.count);
    }
}
```

Các thành viên cố ý để `private` để cho thấy lookup JNI không bị giới hạn bởi từ khóa truy cập Java. Với mã native không tin cậy, đây là một lý do quan trọng phải quản lý ranh giới JNI cẩn thận: native code có thể tương tác sâu với trạng thái trong JVM.

Bảng ID mong muốn:

| Member | Hàm tra cứu | Name | Signature |
| --- | --- | --- | --- |
| `count` | `GetFieldID` | `"count"` | `"I"` |
| `scale` | `GetStaticFieldID` | `"scale"` | `"I"` |
| `add(int)` | `GetMethodID` | `"add"` | `"(I)I"` |
| `describe(int,int)` | `GetStaticMethodID` | `"describe"` | `"(II)Ljava/lang/String;"` |

### 5.3. Sinh JNI header từ Java

Đứng tại thư mục `jni-id-lookup`:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/IdLookupDemo.java
```

Compiler tạo `build/classes/demo/jni/IdLookupDemo.class` và `build/headers/demo_jni_IdLookupDemo.h`. Header dành cho **native entry point** `inspectAndUpdate`, không tự động liệt kê tất cả field/method sẽ được C tra cứu về sau.

Đoạn quan trọng trong header tương đương:

```c
#include <jni.h>

/* Class: demo_jni_IdLookupDemo
 * Method: inspectAndUpdate
 * Signature: ()Ljava/lang/String;
 */
JNIEXPORT jstring JNICALL Java_demo_jni_IdLookupDemo_inspectAndUpdate
  (JNIEnv *, jobject);
```

Đây là đoạn trích minh họa; header thật còn có include guard và khối dành cho C++. C phải include **header do compiler thực tế sinh**, không tự sửa chữ ký entry point.

### 5.4. Cài đặt `native/idlookup.c`

```c
#include <jni.h>
#include "demo_jni_IdLookupDemo.h"

JNIEXPORT jstring JNICALL Java_demo_jni_IdLookupDemo_inspectAndUpdate(
        JNIEnv *env, jobject self) {

    // Vì đây là instance native method, self là đối tượng gọi.
    jclass cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return NULL;  // Giữ exception JVM đã đặt (nếu có).
    }

    jstring report = NULL;

    // 1) Instance field: int count  -> I
    jfieldID countId = (*env)->GetFieldID(env, cls, "count", "I");
    if (countId == NULL) {
        goto cleanup;
    }

    // 2) Static field: static int scale -> I
    jfieldID scaleId =
            (*env)->GetStaticFieldID(env, cls, "scale", "I");
    if (scaleId == NULL) {
        goto cleanup;
    }

    // 3) Instance method: int add(int) -> (I)I
    jmethodID addId =
            (*env)->GetMethodID(env, cls, "add", "(I)I");
    if (addId == NULL) {
        goto cleanup;
    }

    // 4) Static method: String describe(int,int)
    //    -> (II)Ljava/lang/String;
    jmethodID describeId = (*env)->GetStaticMethodID(
            env, cls, "describe", "(II)Ljava/lang/String;");
    if (describeId == NULL) {
        goto cleanup;
    }

    jint before = (*env)->GetIntField(env, self, countId); // 7
    jint factor = (*env)->GetStaticIntField(env, cls, scaleId); // 3

    // JNI gọi ngược vào Java instance method.
    jint sum = (*env)->CallIntMethod(env, self, addId, (jint)5); // 12
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }

    // Chỉ dùng giá trị nhỏ trong ví dụ để tránh overflow C.
    jint after = sum * factor; // 36
    (*env)->SetIntField(env, self, countId, after);

    // JNI gọi ngược vào Java static method.
    report = (jstring)(*env)->CallStaticObjectMethod(
            env, cls, describeId, before, after);

    if ((*env)->ExceptionCheck(env)) {
        report = NULL; // Exception Java sẽ được JVM chuyển về caller.
    }

cleanup:
    // cls là local reference, còn các ID không phải JNI references.
    (*env)->DeleteLocalRef(env, cls);
    return report;
}
```

Các điểm cần quan sát:

1. `GetObjectClass(env, self)` lấy `jclass` đúng với **runtime class** của đối tượng, tránh tự ghép chuỗi tên class cho ví dụ này.
2. Hai `Get...FieldID` nhận signature `"I"`, không có `()`. Hai `Get...MethodID` nhận signature có ngoặc tham số và kiểu trả về.
3. `GetIntField` cần **`self`**, `GetStaticIntField` cần **`cls`**; `CallIntMethod` cần `self`, `CallStaticObjectMethod` cần `cls`.
4. `CallIntMethod` thực hiện Java `add(5)` nên lấy `7 + 5 = 12`. C nhân `12 * 3 = 36` rồi `SetIntField` cập nhật `count` của **cùng đối tượng**.
5. `CallStaticObjectMethod` gọi Java `describe(7, 36)` để trả chuỗi `"count 7 -> 36"`. `report` là local reference đến chuỗi Java, có thể **return** về lời gọi native ở Java; không xóa `report` trước khi return.
6. Nếu một lookup trả `NULL`, JNI đã có thể để lại exception pending. `goto cleanup` chỉ dọn **local reference** rồi trả về JVM để exception được ném; không tiếp tục dùng ID lỗi. Nếu Java method ném exception, `ExceptionCheck` phát hiện và tránh tính tiếp bằng giá trị trả về không hợp lệ.

`DeleteLocalRef` là một trong những thao tác JNI được phép khi có pending exception, nên phần cleanup vẫn hợp lệ. Trong chương trình thực tế cần quyết định chính sách bắt/ghi log/đưa exception về caller; ví dụ giữ nguyên exception cho Java.

### 5.5. Biên dịch C và chạy

Cấu hình `JAVA_HOME` trỏ tới một **JDK** (có `include/jni.h` và `include/linux/jni_md.h`), sau đó chạy:

```bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libidlookup.so \
  native/idlookup.c

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.IdLookupDemo
```

Các đường dẫn:

- `-Ibuild/headers` để compiler C tìm `demo_jni_IdLookupDemo.h`.
- `libidlookup.so` tương ứng tên logic `"idlookup"` trong `System.loadLibrary`.
- `-Djava.library.path=build/lib` giúp JVM tìm thư viện ở vị trí vừa tạo.
- `-Xcheck:jni` bật kiểm tra JNI bổ sung để dễ phát hiện sai ID/tham chiếu/luồng ở giai đoạn học và debug.

**Stdout dự kiến chính xác** với dữ liệu trong ví dụ:

```text
Before: 7
Native: count 7 -> 36
After: 36
```

Trong lệnh chạy, `Before` in trước khi vào JNI; `Native` in khi `inspectAndUpdate()` trả chuỗi; `After` đọc trường `count` đã được C cập nhật qua `SetIntField`. Kết quả chứng minh cả lookup phương thức và lookup trường đã trỏ đúng thành viên.

## 6. Tự xác minh chữ ký bằng `javap -s -p`

Thay vì phỏng đoán descriptor, biên dịch Java rồi tra **bytecode** bằng `javap`:

```bash
javap -s -p -classpath build/classes demo.jni.IdLookupDemo
```

Ở phần liên quan, công cụ sẽ hiển thị các khai báo tương đương:

```text
private int count;
  descriptor: I
private static int scale;
  descriptor: I
private int add(int);
  descriptor: (I)I
private static java.lang.String describe(int, int);
  descriptor: (II)Ljava/lang/String;
private native java.lang.String inspectAndUpdate();
  descriptor: ()Ljava/lang/String;
```

Output thực tế còn các thành viên khác như constructor, static initializer và phương thức `main`. Chỉ cần so từng dòng `descriptor:` với chuỗi truyền cho `GetFieldID`/`GetMethodID`; đừng tự chuyển lại sang cú pháp Java. Với method overload, kiểm tra **đúng dòng overload** bằng tham số và descriptor.

`javac -h` và `javap -s` giải quyết hai việc khác nhau:

- `javac -h` sinh C header cho các **entry point native Java → C**.
- `javap -s -p` hỗ trợ kiểm tra descriptor của **member Java mà C sẽ tra cứu/gọi ngược**, kể cả member private.

Chính vì C gọi các phương thức Java có thân bình thường nên header JNI sinh từ `native` **không thể thay thế** bước tra descriptor của các member được truy cập ở runtime.

## 7. Trường hợp phức tạp: overload, kế thừa, constructor, generics

### 7.1. Overload phải khớp từng chữ ký

Giả sử Java có:

```java
int convert(int x) { return x; }
long convert(long x) { return x; }
String convert(String x) { return x; }
```

Các descriptor lần lượt là `(I)I`, `(J)J` và `(Ljava/lang/String;)Ljava/lang/String;`. Chỉ truyền `"convert"` sẽ không đủ; truyền `"(I)J"` cũng không khớp phương thức thứ nhất vì kiểu trả về khác `I`.

Java không cho phép chỉ khác kiểu trả về khi overload trong source, nhưng **JNI descriptor luôn chứa kiểu trả về**. Không bỏ nó khi xây dựng ID.

### 7.2. Kế thừa và field hiding

`GetMethodID` có thể tìm một instance method được khai báo trong superclass/interface và được kế thừa. Với instance method được override, các lời gọi `Call<Type>Method` thông thường dùng dispatch phù hợp với đối tượng Java. `CallNonvirtual<Type>Method` có semantics riêng và không nên dùng thay thế tùy tiện.

Trường có thể bị **hiding** khi subclass và superclass cùng khai báo tên trường. Khi cần trường được khai báo tại một cấp cụ thể, dùng `jclass` của **đúng class khai báo**, không mặc định class runtime của `self` sẽ chọn cấp mong muốn. `jfieldID` nhận diện trường, không phải tên chung để truy vấn lại theo ý định của native code.

### 7.3. Constructor

Để lấy constructor `new Widget(int)`:

```c
jmethodID ctor =
    (*env)->GetMethodID(env, widgetClass, "<init>", "(I)V");
if (ctor == NULL) {
    return NULL;  // Đoạn minh họa: phải xử lý exception và cleanup.
}

jobject obj = (*env)->NewObject(env, widgetClass, ctor, (jint)5);
```

Đây là **đoạn minh họa cục bộ**, giả định `env`/`widgetClass` hợp lệ và hàm bao quanh trả `jobject`. Constructor luôn có kiểu trả về descriptor `V`. `GetStaticMethodID` không dành cho constructor.

### 7.4. Type erasure và mảng

Các ví dụ Java sau (minh họa, không thuộc chương trình chạy ở mục 5):

```java
java.util.List<String> names;
int[][] matrix;
String[] labels;
void submit(java.util.List<Integer> values) { }
```

Chữ ký tương ứng là `Ljava/util/List;`, `[[I`, `[Ljava/lang/String;` và `(Ljava/util/List;)V`. Generic type argument bị **erasure** trong descriptor. Khi một API có bridge method do compiler sinh, hãy xem `javap -s -p` thay vì giả định mọi chữ ký trùng nguyên văn source.

### 7.5. Không thể lấy `array.length` bằng `GetFieldID`

`GetFieldID` không lấy “trường `length`” của Java array. Với `jarray array`, sử dụng `GetArrayLength(env, array)`. Tương tự, muốn lấy class của một instance, dùng `GetObjectClass`; đừng coi các khái niệm nội tại của VM là field có thể tra tùy ý.

## 8. Xử lý lỗi lookup và pending exception

Các API `GetMethodID`, `GetStaticMethodID`, `GetFieldID`, `GetStaticFieldID` trả ID hoặc `NULL`. Lookup thất bại theo chuẩn có thể gây:

- `NoSuchMethodError` nếu tên/chữ ký/loại phương thức không được tìm thấy.
- `NoSuchFieldError` nếu trường đúng tên/chữ ký/loại không tồn tại.
- `ExceptionInInitializerError` nếu class initialization ném exception.
- `OutOfMemoryError` khi JVM thiếu bộ nhớ.

Vì vậy quy trình an toàn là:

1. Gọi đúng `Get...ID`.
2. Kiểm tra ID có khác `NULL` hay không **trước khi** dùng.
3. Nếu `NULL`, dọn các local reference/tài nguyên native được phép rồi trở về Java với exception pending, **hoặc** chủ động xử lý exception theo hợp đồng đã thiết kế.
4. Không gọi `Call...Method`, `Get...Field` hay `Set...Field` với ID `NULL`. Không tiếp tục các JNI API tùy ý khi exception còn pending.

Ví dụ lỗi tra cứu do gõ sai signature:

```c
jmethodID bad = (*env)->GetMethodID(
    env, cls, "add", "(J)I");  // Sai: add nhận int, không phải long.
if (bad == NULL) {
    // JVM đã có thể đặt NoSuchMethodError.
    // Cleanup hợp lệ và return về Java để exception lan truyền.
}
```

Đây là **đoạn minh họa lỗi cố ý** để nhận diện vấn đề, không chèn vào `idlookup.c` chạy thành công ở mục 5.

Nếu lỗi là tình huống phải xử lý tại native, có thể xem thông tin bằng `ExceptionOccurred` (nó trả local reference đến throwable), quyết định có chuyển thành mã lỗi/exception mới không, rồi `ExceptionClear` **chỉ khi thực sự cần bỏ exception cũ**. Không tự động xóa mọi exception sau lookup sai: làm vậy che giấu lỗi lập trình JNI và tạo trạng thái khó debug.

Một lưu ý thực tế: `-Xcheck:jni` giúp phát hiện nhiều trường hợp dùng sai ID, loại tham chiếu hoặc gọi JNI khi còn pending exception, nhưng không chứng minh native code an toàn bộ nhớ. Có lỗi JNI gây crash JVM trực tiếp, không nhất thiết hiện thành một Java exception dễ bắt.

## 9. Vòng đời và cache `jmethodID`/`jfieldID` đúng cách

Tra cứu có chi phí, nên một số thư viện giữ ID để tái sử dụng. Tuy nhiên ID **chỉ còn hợp lệ khi class khai sinh ID còn được JVM nạp**. Theo JNI Specification, ID tự nó **không giữ class khỏi bị unload**. Nếu class bị unload, không được dùng lại ID cũ; phải giữ một tham chiếu sống tới class hoặc tra cứu lại.

Phân biệt ba khái niệm:

| Giá trị JNI | Thuộc loại nào? | Cách quản lý |
| --- | --- | --- |
| `jclass cls` từ `GetObjectClass` / `FindClass` | **Local reference** tới class Java | Hợp lệ theo local frame/luồng; `DeleteLocalRef` khi xong |
| `jmethodID`, `jfieldID` | **Opaque member IDs** | Không gọi `DeleteLocalRef`, không giữ class sống; chỉ dùng khi class còn loaded |
| `jclass globalCls` từ `NewGlobalRef(env, cls)` | **Global reference** tới class | Có thể lưu qua JNI call và nhiều luồng khi hợp lệ; cần `DeleteGlobalRef` lúc dọn dẹp |

Nếu thiết kế cache dài hạn, một mẫu an toàn về nguyên tắc là lấy `jclass` đúng class loader, tạo **global reference** để giữ class sống, lấy/cất member IDs đi cùng class đó, rồi khi shutdown ngừng callback/tra cứu đang dùng trước khi xóa global reference. Cần đồng bộ việc khởi tạo/hủy cache và các luồng đang dùng. Cache dựa trên tên class mà bỏ qua **class loader** có thể tra nhầm một class khác cùng tên.

**Không cache `JNIEnv *` để dùng từ luồng khác.** `JNIEnv` gắn với luồng; native thread tự tạo phải attach tới JVM theo Invocation API rồi lấy `JNIEnv *` của chính luồng đó. ID có thể tái sử dụng trong các luồng phù hợp khi class vẫn sống, nhưng đối tượng/reference, thứ tự callback và dữ liệu truy cập vẫn cần đồng bộ đúng.

Đối với ví dụ nhỏ, tra ID trong mỗi lời gọi là dễ hiểu và an toàn vòng đời hơn. Chỉ tối ưu cache sau khi kiểm tra thực tế về chi phí lookup và xác định ownership rõ ràng.

## 10. Chẩn đoán nhanh lỗi tên/chữ ký

| Hiện tượng | Nguyên nhân thường gặp | Cách xác nhận/sửa |
| --- | --- | --- |
| `GetMethodID` trả `NULL`, có `NoSuchMethodError` | Sai tên, tham số, **kiểu trả về**, static/instance | So `javap -s -p`; dùng đúng `GetMethodID` hoặc `GetStaticMethodID` |
| `GetFieldID` trả `NULL`, có `NoSuchFieldError` | Sai tên, descriptor, hoặc trường là static | So field descriptor trong `javap`; đổi sang `GetStaticFieldID` nếu cần |
| `GetObjectField` được dùng cho `int` | Sai họ getter theo kiểu | Dùng `GetIntField` với field ID kiểu `I` |
| Chuỗi tham chiếu `String` lookup lỗi | Dùng `Ljava.lang.String;` hoặc thiếu `;` | Dùng `Ljava/lang/String;` |
| Trường generic không tìm thấy | Dùng type argument thay vì type-erased descriptor | Dùng `Ljava/util/List;` cho `List<String>` |
| Method overload gọi sai | Chỉ nhìn tên method | Tra descriptor chính xác gồm tham số và kiểu trả về |
| ID cache lâu rồi JVM crash | Class đã unload hoặc ID thuộc class loader khác | Giữ global class reference hoặc tra lại ID đúng class |
| Native thread gọi JNI lỗi | Dùng `JNIEnv *` của thread khác | Attach/get `JNIEnv *` riêng trên thread hiện tại |
| Lookup đúng nhưng Java không chạy như dự kiến | Dùng sai `Call<Type>Method` hoặc sai đối tượng/class | Đối chiếu kiểu trả về, static/instance và Java dispatch |
| `UnsatisfiedLinkError` ở `inspectAndUpdate` | Không tìm đúng native entry point/thư viện | Sinh header bằng `javac -h`, kiểm tra `libidlookup.so` và `java.library.path` |

Không nên “sửa” vấn đề bằng cách ép kiểu `jmethodID` thành `jfieldID` hoặc dùng `jobject` giả. Nếu chuỗi descriptor hoặc cách truy cập sai, sửa **hợp đồng Java ↔ JNI** từ nguồn và build lại.

## 11. Bài tập củng cố

1. Với Java `private long id;` và `private static String label;`, viết đúng hai lời gọi `GetFieldID`/`GetStaticFieldID` (bao gồm descriptor) và getter tương ứng.
2. Với `boolean contains(String text, int[] values)`, descriptor phương thức là gì? Hàm `Call<Type>Method` nào phải dùng để nhận kết quả `boolean`?
3. Vì sao `GetMethodID(env, cls, "add", "(I)V")` sai với method `int add(int)`? Vì sao `GetFieldID(..., "count", "()I")` cũng sai?
4. Nếu chuyển `describe(int,int)` từ `static` thành instance method nhưng C giữ `GetStaticMethodID`, kết quả có thể là gì? Những lời gọi tiếp theo phải thay thế thế nào?
5. Trong ví dụ chạy được, hãy lần theo bốn ID để giải thích vì sao stdout là `Before: 7`, `Native: count 7 -> 36`, `After: 36`.
6. Một thư viện lưu `jmethodID` trong biến toàn cục và class bị unload. Vì sao ID không còn dùng được? Cần giữ loại reference nào và dọn dẹp ra sao?
7. Hãy dùng `javap -s -p` xác định descriptor của một phương thức có `String[]` và `List<Long>`; giải thích vì sao Generic type argument không xuất hiện trong JNI descriptor.

**Ghi nhớ:** Muốn lấy `jmethodID`/`jfieldID` chính xác, phải biết **đúng class, đúng tên, đúng descriptor, đúng static/instance**. Sau lookup kiểm tra `NULL` và exception; sau đó chọn đúng `Call...Method` hoặc `Get/Set...Field`. ID không phải Java reference và không giữ class khỏi unload.

### Tài liệu chính thức

- JNI Specification — [Types and Data Structures / Type Signatures](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html).
- JNI Specification — [Functions: `GetMethodID`, `GetFieldID`, static counterparts](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- JNI Specification — [Design Overview: Accessing Fields and Methods; ID lifetime](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- JDK `javap` tool (JDK 21): https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html.
