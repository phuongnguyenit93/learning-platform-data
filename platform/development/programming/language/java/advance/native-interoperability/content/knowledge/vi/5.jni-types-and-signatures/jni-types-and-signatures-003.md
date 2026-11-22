# `jobject`, `jclass`, `jstring` và các kiểu mảng là tham chiếu mờ trong JNI

## 1. Hiểu đúng “tham chiếu mờ” (opaque reference)

Khi Java gọi native method bằng **Java Native Interface (JNI)**, một đối tượng Java có thể được chuyển sang hàm C/C++ dưới dạng `jobject`, `jclass`, `jstring`, `jarray` hoặc các kiểu con như `jintArray` và `jobjectArray`. Các giá trị đó là **tham chiếu do JVM quản lý**: native code được dùng chúng để gọi các hàm JNI thích hợp, nhưng **không được giả định biết địa chỉ, bố cục bộ nhớ hay cấu trúc nội bộ của đối tượng Java**.

“Tham chiếu mờ” nghĩa là phần biểu diễn bên trong bị che giấu với mã ứng dụng:

- Không thể an toàn coi `jobject` là con trỏ C tới một `struct` mang các trường Java.
- Không thể dùng `jstring` như `char*`, vì `jstring` là tham chiếu tới **đối tượng `java.lang.String`**, không phải mảng byte C kết thúc bằng NUL.
- Không thể coi `jintArray` là `jint*` rồi truy cập bằng `numbers[i]`; phải sử dụng các API mảng của `JNIEnv` để đọc hoặc ghi.
- Không thể coi `jclass` là con trỏ tới kiểu C++ hoặc cấu trúc metadata class của JVM; đó là tham chiếu tới **đối tượng `java.lang.Class`**.

JVM có thể di chuyển đối tượng trong Java heap khi garbage collection (GC) diễn ra. **JNI reference là handle hợp lệ theo hợp đồng JNI**, giúp native code tham chiếu đối tượng trong phạm vi vòng đời được quy định mà không phụ thuộc vị trí vật lý hiện tại của object. Không suy luận về cấu trúc handle hay tự làm phép toán con trỏ trên JNI reference.

~~~text
Java heap                                Native JNI frame
+------------------------+               +----------------------+
| String ("Java")         |<-- JVM ------| jstring text         |
| StringBuilder ("node")  |<-- references| jobject value        |
| int[] {2, 3, 5}       |<--------------| jintArray numbers    |
| String[] {"a", "b"}    |<--------------| jobjectArray labels  |
| Class<StringBuilder>   |<--------------| jclass actualClass   |
+------------------------+               +----------------------+
      JVM quản lý bố cục                     C/C++ giữ JNI handles
      và tính sống của object                trong phạm vi hợp lệ
~~~

Mũi tên là quan hệ logic, **không khẳng định mỗi JNI reference chứa trực tiếp địa chỉ của đối tượng**. Khi cần đọc/ghi giá trị, native code gọi `(*env)->...` trong C, hoặc `env->...` trong C++.

## 2. Hệ kiểu JNI: nguyên thủy khác tham chiếu

JNI chia kiểu dữ liệu thành hai nhóm lớn.

**Kiểu nguyên thủy** biểu diễn giá trị tương ứng với kiểu primitive Java:

| Java | JNI | Ý nghĩa |
| --- | --- | --- |
| `boolean` | `jboolean` | Kiểu biểu diễn boolean của JNI, dùng hằng `JNI_TRUE`/`JNI_FALSE` khi thích hợp |
| `byte` | `jbyte` | Số nguyên có dấu 8 bit |
| `char` | `jchar` | Đơn vị mã UTF-16 không dấu 16 bit |
| `short` | `jshort` | Số nguyên có dấu 16 bit |
| `int` | `jint` | Số nguyên có dấu 32 bit |
| `long` | `jlong` | Số nguyên có dấu 64 bit |
| `float` | `jfloat` | Float 32 bit |
| `double` | `jdouble` | Float 64 bit |

**Kiểu tham chiếu** biểu diễn đối tượng JVM hoặc những dạng chuyên biệt của chúng:

| JNI type | Đối tượng Java tương ứng | Cách dùng thường gặp |
| --- | --- | --- |
| `jobject` | Một Java object bất kỳ | Tham số/giá trị trả về object, instance receiver |
| `jclass` | `java.lang.Class` | Lấy class, tra method/field, gọi static method |
| `jstring` | `java.lang.String` | Đọc độ dài, nội dung chuỗi qua API JNI |
| `jarray` | Bất kỳ Java array | Kiểu nền nhận tham chiếu mảng |
| `jobjectArray` | Mảng object như `String[]`, `Object[]` | Đọc/ghi từng phần tử là JNI object reference |
| `jbooleanArray`, `jbyteArray`, `jcharArray`, `jshortArray`, `jintArray`, `jlongArray`, `jfloatArray`, `jdoubleArray` | Mảng primitive tương ứng | Truy cập dữ liệu qua `Get...ArrayRegion` hoặc `Get...ArrayElements` |
| `jthrowable` | `java.lang.Throwable` | Thao tác với exception object |
| `jweak` | Weak global JNI reference | Tham chiếu yếu, có thể bị GC xóa đích |

**`jsize`** là kiểu dùng cho kích thước/chỉ số trong nhiều JNI API. **`jmethodID` và `jfieldID` không phải `jobject`**: chúng là định danh method/field của JVM, không áp dụng quy tắc local/global object reference và không được dùng như một object. **`jvalue`** là union chứa giá trị cho các lời gọi method với danh sách tham số kiểu `...A`; nó cũng không phải JNI object reference.

Trong `jni.h`, các typedef C và định nghĩa C++ có thể được trình bày khác nhau, nhưng **không được dựa vào cách typedef hiện tại để diễn giải cấu trúc bên trong của đối tượng**. Ví dụ, C header có thể alias nhiều loại tham chiếu về một dạng opaque pointer; tên kiểu chuyên biệt vẫn có giá trị giúp diễn đạt hợp đồng API và tránh nhầm lẫn.

## 3. `jobject` và `jclass`: object instance khác object `Class`

Đây là hai tình huống trong JNI:

~~~java
// Java minh họa, không phải chương trình độc lập
class Example {
    native int instanceWork(String text);
    static native int staticWork(String text);
}
~~~

Các hàm C tương ứng có dạng:

~~~c
/* Minh họa chữ ký; tên thực tế nên lấy từ javac -h. */
JNIEXPORT jint JNICALL Java_Example_instanceWork(
        JNIEnv *env, jobject receiver, jstring text);

JNIEXPORT jint JNICALL Java_Example_staticWork(
        JNIEnv *env, jclass declaringClass, jstring text);
~~~

- `JNIEnv*` cung cấp các hàm của JVM cho **thread đang gọi**. Không giữ lại rồi dùng `JNIEnv*` từ thread khác.
- Với **instance native method**, tham số JNI thứ hai là `jobject` tham chiếu tới receiver (`this` trong Java).
- Với **static native method**, tham số JNI thứ hai là `jclass` tham chiếu tới đối tượng `Class` khai báo method.
- Một tham số Java kiểu `String` thành `jstring`; Java kiểu `Object` thành `jobject`.

Các hàm thao tác object/class hữu ích:

| Hàm JNI | Mục đích |
| --- | --- |
| `GetObjectClass(env, obj)` | Trả `jclass` đại diện cho class thực tế của object |
| `FindClass(env, "java/lang/String")` | Tra một class theo tên JNI dạng slash |
| `IsInstanceOf(env, obj, clazz)` | Kiểm tra tính tương thích kiểu của object với class |
| `IsSameObject(env, a, b)` | Kiểm tra hai reference có chỉ tới **cùng Java object** không |
| `GetMethodID` / `GetStaticMethodID` | Lấy method ID cho lời gọi instance/static |
| `GetFieldID` / `GetStaticFieldID` | Lấy field ID của instance/static field |

**`jclass` vẫn là object reference**, nên có vòng đời local/global và có thể được giữ bằng `NewGlobalRef` nếu cần tồn tại qua nhiều lần native call. Không sử dụng `jclass` như địa chỉ vào vùng metaspace.

**Không so sánh hai JNI reference bằng `a == b` để kết luận chúng trỏ cùng Java object**. Hai handle có thể khác nhau nhưng cùng tham chiếu một object; hãy dùng `IsSameObject`. Kiểm tra một reference có bằng `NULL` là trường hợp hợp lệ, nhưng không dùng phép bằng con trỏ để xác định object identity.

### Truyền object xuống C/C++ không chuyển quyền sở hữu đối tượng

Tham số `jobject receiver` hoặc `jobject value` thường là **local reference** hợp lệ trong lời gọi native hiện hành. Java heap vẫn do JVM quản lý. Native code không được gọi `free(value)`, `delete value` hay giữ local reference để dùng về sau khi method đã trả về.

## 4. `jstring`: tham chiếu String, không phải buffer ký tự

`jstring` đại diện cho đối tượng Java `String`. Java dùng **UTF-16 code units** ở các API như `String.length()`; JNI cung cấp những API có hợp đồng về mã hóa và vòng đời.

| JNI API | Kết quả/công dụng | Nghĩa vụ |
| --- | --- | --- |
| `GetStringLength(env, str)` | Số **UTF-16 code units** của chuỗi | Không tạo con trỏ nội dung |
| `GetStringChars(env, str, ...)` | Con trỏ đọc các `jchar` (UTF-16); JVM có thể copy/pin | Gọi `ReleaseStringChars` |
| `GetStringUTFChars(env, str, ...)` | Chuỗi byte ở dạng **Modified UTF-8** của JNI, có kết thúc NUL | Gọi `ReleaseStringUTFChars` |
| `GetStringUTFLength(env, str)` | Số byte ở dạng **Modified UTF-8** (không tính NUL kết thúc) | Không bằng số ký tự Unicode hay nhất thiết bằng `GetStringLength` |
| `GetStringRegion` / `GetStringUTFRegion` | Sao chép một vùng nội dung vào buffer do caller cung cấp | Kiểm tra phạm vi/capacity; `GetStringUTFRegion` không bảo đảm thêm NUL cuối |
| `NewString` / `NewStringUTF` | Tạo Java String từ UTF-16 hoặc Modified UTF-8 | Đúng encoding; kết quả là local `jstring` |

Chẳng hạn, Java string `"A😀B"` có **4 UTF-16 code units**: chữ A (1), emoji 😀 (2 surrogate units), chữ B (1). Nó có **3 Unicode code points**. Vì vậy:

~~~java
// Mã Java minh họa trong một method:
String text = "A\uD83D\uDE00B";
System.out.println(text.length());             // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

Khi gửi `text` qua JNI, `GetStringLength` trả `4`, không phải `3`. Ngoài ra, **Modified UTF-8 không hoàn toàn giống UTF-8 chuẩn**: chẳng hạn ký tự U+0000 được mã hóa đặc biệt; các surrogate có quy tắc biểu diễn riêng. Không chuyển thẳng byte từ `GetStringUTFChars` tới API yêu cầu UTF-8 chuẩn mà không kiểm tra/chuyển đổi đúng encoding.

Ví dụ mã C trong native method:

~~~c
/* Minh họa khi text là jstring hợp lệ và env thuộc thread hiện tại. */
jsize units = (*env)->GetStringLength(env, text);
const jchar *chars = (*env)->GetStringChars(env, text, NULL);
if (chars == NULL) {
    return 0; /* Thường có pending exception như OutOfMemoryError. */
}
/* Chỉ đọc chars[0..units-1] khi vùng này còn hợp lệ. */
(*env)->ReleaseStringChars(env, text, chars);
~~~

`chars` là **con trỏ vùng nội dung do JNI cấp quyền truy cập tạm thời**, khác hẳn **`jstring` là tham chiếu đối tượng**. Không tự `free(chars)`. Phải release đúng API kể cả khi JVM đã cung cấp bản copy; không giữ con trỏ qua thời điểm release.

## 5. JNI arrays: `jarray` và các kiểu mảng chuyên biệt

Một Java array vẫn là Java object; `jarray` và các loại cụ thể là **opaque references**, không phải con trỏ trỏ thẳng tới phần tử C.

| Mảng Java | Tham số JNI | API thường dùng |
| --- | --- | --- |
| `int[]` | `jintArray` | `GetArrayLength`, `GetIntArrayRegion`, `GetIntArrayElements`, `SetIntArrayRegion` |
| `byte[]` | `jbyteArray` | `GetByteArrayRegion`, `GetByteArrayElements`, `SetByteArrayRegion` |
| `double[]` | `jdoubleArray` | `GetDoubleArrayRegion`, `GetDoubleArrayElements` |
| `String[]` | `jobjectArray` | `GetObjectArrayElement`, `SetObjectArrayElement` |
| `Object[]` | `jobjectArray` | `GetObjectArrayElement`, `SetObjectArrayElement` |
| `int[][]` | `jobjectArray` ở **chiều ngoài** | Lấy từng hàng bằng `GetObjectArrayElement` rồi xử lý như `jintArray` |

### 5.1. Mảng primitive: đọc vùng dữ liệu bằng Region

~~~c
/* Minh họa trong native method nhận jintArray numbers; cần kiểm tra độ dài. */
jint firstThree[3];
jsize n = (*env)->GetArrayLength(env, numbers);
if (n >= 3) {
    (*env)->GetIntArrayRegion(env, numbers, 0, 3, firstThree);
    if ((*env)->ExceptionCheck(env)) {
        return 0;
    }
    /* firstThree hiện chứa 3 số nguyên được sao chép từ mảng Java. */
}
~~~

`GetIntArrayRegion` **copy** số phần tử chỉ định vào buffer C do caller sở hữu; caller không cần `ReleaseIntArrayRegion`. Nếu truy cập sai biên, JVM có thể ném exception. Cần xử lý exception trước khi dùng buffer.

### 5.2. Mảng primitive: truy cập bằng Elements

~~~c
/* Minh họa khi numbers là jintArray hợp lệ. */
jsize n = (*env)->GetArrayLength(env, numbers);
jint *elements = (*env)->GetIntArrayElements(env, numbers, NULL);
if (elements == NULL) {
    return 0;
}
jint sum = 0;
for (jsize i = 0; i < n; i++) {
    sum += elements[i];
}
(*env)->ReleaseIntArrayElements(env, numbers, elements, JNI_ABORT);
~~~

JVM **có thể copy hoặc pin** mảng; tuyệt đối không mặc định là zero-copy. `JNI_ABORT` cho biết phần dữ liệu không cần sao chép ngược các sửa đổi khi release, phù hợp trường hợp **chỉ đọc** như ví dụ. Nếu code đã sửa buffer và muốn cập nhật lại mảng Java, chọn release mode thích hợp (`0` để cập nhật và giải phóng theo hợp đồng). Chế độ `JNI_COMMIT` có thể sao chép thay đổi trở lại mà **chưa giải phóng buffer**, nên vẫn cần bước release tiếp theo theo hợp đồng API.

### 5.3. Mảng object: mỗi phần tử lại là một JNI reference

~~~c
/* Minh họa khi labels là jobjectArray chứa String. */
jsize n = (*env)->GetArrayLength(env, labels);
if (n > 0) {
    jobject element = (*env)->GetObjectArrayElement(env, labels, 0);
    if ((*env)->ExceptionCheck(env)) {
        return 0;
    }
    if (element != NULL) {
        jsize units = (*env)->GetStringLength(env, (jstring) element);
        /* Sử dụng units khi cần. */
        (*env)->DeleteLocalRef(env, element);
    }
}
~~~

`GetObjectArrayElement` trả **local reference**, dù phần tử mảng Java có thể còn sống sau khi native method trả về. Cần cân nhắc xóa local refs trong vòng lặp lớn để tránh tăng áp lực lên bảng tham chiếu JNI. Ép kiểu từ `jobject` sang `jstring` chỉ hợp lệ nếu **biết kiểu Java thực tế** là `String`; đừng biến một object bất kỳ thành `jstring` bằng cast rồi gọi API String.

Với `GetPrimitiveArrayCritical` hoặc `GetStringCritical`, JVM có thể áp đặt ràng buộc nghiêm ngặt trong khoảng thời gian critical: tránh gọi các hàm JNI tùy ý hoặc thực hiện thao tác blocking kéo dài; hãy đọc hợp đồng critical access và giải phóng càng sớm càng tốt.

## 6. Vòng đời của local, global và weak global reference

`jobject`/`jclass`/`jstring`/mảng thể hiện **kiểu đối tượng**. Còn local/global/weak global là **phạm vi sống và sức mạnh giữ đối tượng**, là một chiều phân loại khác.

| Loại reference | Được tạo thế nào? | Phạm vi và trách nhiệm |
| --- | --- | --- |
| **Local** | Tham số JNI, `GetObjectClass`, `FindClass`, `GetObjectArrayElement`, `NewStringUTF`, ... | Thường hợp lệ đến khi lời gọi native kết thúc hoặc đến khi `DeleteLocalRef`/`PopLocalFrame`; chỉ dùng trong ngữ cảnh thread thích hợp |
| **Global** | `NewGlobalRef(env, ref)` | Giữ object reachable cho đến khi `DeleteGlobalRef`; có thể dùng qua nhiều lần native call và thread đã attach đúng |
| **Weak global** | `NewWeakGlobalRef(env, ref)` | Không giữ object sống một mình; GC có thể xóa đối tượng, phải xử lý kết quả null và dùng đúng `DeleteWeakGlobalRef` |

Các điểm quan trọng:

1. **Không lưu local ref** vào biến global C/C++, native handle hoặc queue dùng sau khi native method trả về. Cách làm này có thể thành use-after-invalid-reference.
2. Nếu thực sự cần giữ object qua nhiều lần gọi, tạo **global ref** rồi xóa đúng lúc. `NewGlobalRef` không sao chép đối tượng Java; nó tạo thêm một reference có vòng đời dài hơn.
3. Global reference giữ object sống, nên **quên `DeleteGlobalRef` gây giữ đối tượng không cần thiết** và có thể gây memory leak ở mức JNI/heap.
4. Weak global có thể bị GC xóa tại thời điểm bất kỳ giữa các lượt quan sát. Nếu cần dùng object, hãy **tạo strong local ref bằng `NewLocalRef(env, weakRef)`**, kiểm tra `NULL`, rồi thao tác trên local mới trong phạm vi hợp lệ.
5. **`JNIEnv*` gắn với thread**. Reference global có thể chia sẻ giữa các thread đã attach đúng, nhưng bản thân object Java **không tự trở thành thread-safe**; vẫn phải đồng bộ nếu có truy cập đồng thời.

Ví dụ pattern khi muốn giữ một object từ JNI call này sang JNI call khác:

~~~c
/* Các đoạn sau minh họa logic trong native code, không phải hàm độc lập. */
static jobject saved = NULL;

/* Khi lưu, trong một lời gọi JNI được đồng bộ phù hợp: */
saved = (*env)->NewGlobalRef(env, incoming);
if (saved == NULL) {
    /* Kiểm tra null/OOME và không sử dụng saved. */
}

/* Khi không cần giữ nữa: */
if (saved != NULL) {
    (*env)->DeleteGlobalRef(env, saved);
    saved = NULL;
}
~~~

Code minh họa dùng biến toàn cục để thấy vòng đời; ứng dụng thực tế phải thiết kế **ownership**, đồng bộ mọi truy cập vào `saved`, tránh thay thế làm rò ref và không giải phóng khi thread khác đang dùng. Với hệ thống có nhiều class loader, còn phải cân nhắc việc giữ class/object qua các vòng triển khai, unload.

Local references phát sinh liên tục trong loop cũng có thể lấp đầy bảng local-ref. Sử dụng `DeleteLocalRef` khi xong, hoặc `PushLocalFrame`/`PopLocalFrame` khi cần gom nhiều local refs. `GetObjectRefType` có thể cho biết loại reference *hợp lệ*; không dùng API này để “kiểm tra an toàn” một con trỏ đã bị xóa hoặc không phải JNI reference.

## 7. Ví dụ chạy hoàn chỉnh Java 17 + C/JNI

Chương trình sau minh họa đồng thời **`jobject`, `jclass`, `jstring`, `jintArray` và `jobjectArray`**. Hàm C đọc dữ liệu chỉ qua JNI API, xóa local references nó tự tạo, và release vùng dữ liệu mảng primitive.

Môi trường ví dụ: **Linux + JDK 17+ + GCC tương ứng kiến trúc của JVM**; biến `JAVA_HOME` trỏ tới JDK. Không cần thư viện bên thứ ba.

### 7.1. Tệp `OpaqueReferenceDemo.java`

~~~java
public final class OpaqueReferenceDemo {
    static {
        System.loadLibrary("opaque_refs");
    }

    private static native int score(
            Object value, String text, int[] numbers, String[] labels);

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";
        int result = score(
                new StringBuilder("node"),
                text,
                new int[]{2, 3, 5},
                new String[]{"alpha", "beta"});

        System.out.println("javaUtf16Units=" + text.length());
        System.out.println("score=" + result);
    }
}
~~~

Ý nghĩa: tham số thứ nhất là Java object; thứ hai là `String` có một ký tự ngoài BMP; tham số thứ ba là mảng primitive `int[]`; tham số cuối là mảng reference `String[]`. Java khai báo method `static native` nên JNI C nhận thêm `jclass declaringClass` ở vị trí thứ hai.

### 7.2. Tệp `opaque_refs.c`

~~~c
#include <jni.h>
#include "OpaqueReferenceDemo.h"

JNIEXPORT jint JNICALL Java_OpaqueReferenceDemo_score(
        JNIEnv *env,
        jclass declaringClass,
        jobject value,
        jstring text,
        jintArray numbers,
        jobjectArray labels) {

    (void) declaringClass;

    if (value == NULL || text == NULL
            || numbers == NULL || labels == NULL) {
        jclass ex = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (ex != NULL) {
            (*env)->ThrowNew(env, ex, "arguments must not be null");
            (*env)->DeleteLocalRef(env, ex);
        }
        return 0;
    }

    /* jclass cũng là JNI reference, không phải con trỏ C++ class. */
    jclass actual = (*env)->GetObjectClass(env, value);
    if (actual == NULL) {
        return 0;
    }

    jclass expected = (*env)->FindClass(
            env, "java/lang/StringBuilder");
    if (expected == NULL) {
        (*env)->DeleteLocalRef(env, actual);
        return 0;
    }
    jboolean sameType = (*env)->IsSameObject(
            env, actual, expected);

    /* jstring có số đơn vị mã UTF-16, không phải số code points. */
    jsize textUnits = (*env)->GetStringLength(env, text);

    /* jintArray được truy cập bằng API, không phải numbers[i]. */
    jsize count = (*env)->GetArrayLength(env, numbers);
    jint *elements = (*env)->GetIntArrayElements(
            env, numbers, NULL);
    if (elements == NULL) {
        (*env)->DeleteLocalRef(env, expected);
        (*env)->DeleteLocalRef(env, actual);
        return 0; /* JVM thường đã đặt pending exception. */
    }

    jint sum = 0;
    for (jsize i = 0; i < count; i++) {
        sum += elements[i];
    }
    (*env)->ReleaseIntArrayElements(
            env, numbers, elements, JNI_ABORT);

    /* Mỗi phần tử object array là một local JNI reference mới. */
    jsize labelCount = (*env)->GetArrayLength(env, labels);
    jsize firstLabelUnits = 0;
    if (labelCount > 0) {
        jobject first = (*env)->GetObjectArrayElement(
                env, labels, 0);
        if ((*env)->ExceptionCheck(env)) {
            (*env)->DeleteLocalRef(env, expected);
            (*env)->DeleteLocalRef(env, actual);
            return 0;
        }
        if (first != NULL) {
            /* Java khai báo String[] nên phần tử khác null là String. */
            firstLabelUnits = (*env)->GetStringLength(
                    env, (jstring) first);
            (*env)->DeleteLocalRef(env, first);
        }
    }

    (*env)->DeleteLocalRef(env, expected);
    (*env)->DeleteLocalRef(env, actual);

    /* Chỉ tính ví dụ nhỏ, không nhằm xử lý tràn số nguyên tổng quát. */
    return sum + textUnits + count + firstLabelUnits
            + (sameType ? 1 : 0);
}
~~~

**Điểm cần quan sát trong C:**

1. `jobject value` vẫn được giữ bởi local JNI reference; `GetObjectClass` trả thêm một local `jclass`.
2. `FindClass` cũng trả local `jclass`; `IsSameObject` so hai Java class objects. Với `new StringBuilder("node")` thì điều kiện đúng.
3. `GetStringLength` của chuỗi `A😀B` trả `4` UTF-16 code units.
4. `GetArrayLength(numbers)` trả `3`; `GetIntArrayElements` trả vùng phần tử tạm thời, tổng `2+3+5=10`; `ReleaseIntArrayElements(..., JNI_ABORT)` release vì chỉ đọc.
5. `GetObjectArrayElement(labels, 0)` trả local reference cho `"alpha"`; `GetStringLength` trả `5`; `DeleteLocalRef` giải phóng local handle, không `free` đối tượng Java.
6. Hai local `jclass` tự tạo cũng được release bằng `DeleteLocalRef`. Các tham số truyền vào từ Java không cần tự xóa trong ví dụ.

Đây là code minh họa đầy đủ cho **đầu vào cố định của bài học**, không phải API tổng quát cho mọi kiểu mảng hay các tổng số lớn. Các lỗi JNI có pending Java exception phải được xử lý ở mức thiết kế ứng dụng; ví dụ trả về ngay để JVM truyền exception hiện hữu về phía Java. Khi dùng trong production cần chính sách lỗi rõ ràng, kiểm tra ngoại lệ, input constraints và ownership theo workload.

### 7.3. Biên dịch và chạy

Lưu hai tệp trong cùng một thư mục; từ thư mục đó:

~~~bash
javac -h . OpaqueReferenceDemo.java
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libopaque_refs.so opaque_refs.c
java -Djava.library.path=. OpaqueReferenceDemo
~~~

`javac -h .` tạo class file và `OpaqueReferenceDemo.h` đúng chữ ký JNI. `gcc -fPIC -shared` tạo `libopaque_refs.so` cho Linux; `System.loadLibrary("opaque_refs")` tìm thư viện theo tên logic trong `java.library.path` đã thiết lập.

**Stdout chính xác** của ví dụ trên Linux/JDK 17+ khi build thành công:

~~~text
javaUtf16Units=4
score=23
~~~

Cách tính: `10` (tổng mảng int) + `4` (độ dài UTF-16) + `3` (số phần tử `int[]`) + `5` (độ dài `"alpha"`) + `1` (class đúng) = `23`.

Trên macOS, thư viện thường có tên `libopaque_refs.dylib` và cần dùng tùy chọn liên kết phù hợp như `clang -dynamiclib` cùng JNI include `$JAVA_HOME/include/darwin`. Trên Windows, tên thường là `opaque_refs.dll` và include JNI theo `%JAVA_HOME%\include\win32` với MSVC/MinGW tương ứng. **Mã Java, JNI header và ABI của native binary phải khớp đúng nền tảng**.

## 8. JNI type signature: `jobject`/`jstring`/mảng ánh xạ thế nào?

Chữ ký JVM/JNI dùng ký hiệu riêng, không phải tên typedef C. Với method của ví dụ:

~~~java
private static native int score(
        Object value, String text, int[] numbers, String[] labels);
~~~

Descriptor JVM là:

~~~text
(Ljava/lang/Object;Ljava/lang/String;[I[Ljava/lang/String;)I
~~~

Giải nghĩa từng phần:

| Thành phần descriptor | Ý nghĩa |
| --- | --- |
| `Ljava/lang/Object;` | Một reference tới `Object` |
| `Ljava/lang/String;` | Một reference tới `String` |
| `[I` | Mảng `int[]`, tương ứng `jintArray` |
| `[Ljava/lang/String;` | Mảng `String[]`, tương ứng `jobjectArray` |
| `)I` | Method trả về Java `int`/JNI `jint` |

Một số descriptor phổ biến: `Ljava/lang/Class;` cho `Class`, `[B` cho `byte[]`, `[J` cho `long[]`, `[[I` cho `int[][]`, `V` cho `void` (ở vị trí return type). **Array là reference type** dù phần tử là primitive.

**Hãy để `javac -h` sinh header**, đặc biệt khi class có package, method overloaded hoặc tên chứa ký tự cần mã hóa trong tên symbol. Native entry point `Java_OpaqueReferenceDemo_score` ở đây đơn giản vì class thuộc default package và tên method duy nhất, nhưng đây không phải quy tắc đủ để tự đoán mọi symbol JNI. Nếu dùng `RegisterNatives` thì native function có thể được đăng ký theo bảng thay vì chỉ dựa vào tên export.

## 9. An toàn tham chiếu: các lỗi dễ gây crash hoặc leak

### 9.1. Ép `jstring` thành `char*`

**Sai:**

~~~c
/* Sai: jstring không phải C string! */
const char *bytes = (const char *) text;
printf("%s\n", bytes);
~~~

Đoạn này không hợp lệ vì `text` là opaque reference. **Đúng hướng**: dùng `GetStringUTFChars` rồi `ReleaseStringUTFChars`; nhớ rằng byte nhận được là **Modified UTF-8**, cần chuyển đổi khi API đích yêu cầu UTF-8 chuẩn.

### 9.2. Ép `jintArray` thành `jint*`

**Sai:**

~~~c
/* Sai: jintArray không phải con trỏ mảng int C. */
jint *raw = (jint *) numbers;
jint first = raw[0];
~~~

**Đúng hướng**: dùng `GetIntArrayRegion` hoặc `GetIntArrayElements` và release theo hợp đồng. Nếu C cần giữ dữ liệu sau lời gọi JNI, tạo bản copy do C sở hữu hoặc thiết kế vòng đời riêng; không giữ con trỏ elements đã release.

### 9.3. Lưu local `jobject` cho native thread sử dụng về sau

**Sai về vòng đời:**

~~~c
/* Ý tưởng sai: giữ local ref của JNI call sau khi method trả về. */
static jobject cached;
cached = value;
~~~

**Đúng hướng**: nếu cần dùng về sau, `NewGlobalRef` trong khi local ref hợp lệ, đồng bộ truy cập và `DeleteGlobalRef` khi hoàn tất. Thread native cần attach vào JVM để lấy `JNIEnv*` riêng; có global ref **không đồng nghĩa được dùng `JNIEnv*` của thread tạo ref**.

### 9.4. Gọi API JNI trên reference không còn hợp lệ

Sau `DeleteLocalRef`, `DeleteGlobalRef`, `PopLocalFrame`, hoặc khi native call kết thúc, các reference bị chấm dứt hiệu lực **không được truy cập lại**. Đừng dùng `IsSameObject`, `GetObjectRefType` hoặc cast C để cố “hồi sinh” reference đã bị hủy.

### 9.5. Nhầm object array với primitive array

`String[]` là `jobjectArray`, không phải `jstring*`; mỗi phần tử lấy từ `GetObjectArrayElement` có local-ref lifetime. `int[]` là `jintArray`, không phải `jobjectArray`; chỉ dùng primitive-array API tương ứng.

### 9.6. Bỏ qua pending Java exception

Các API JNI như `FindClass`, `GetObjectArrayElement`, `GetIntArrayElements` có thể gặp lỗi và để lại pending exception. Khi một JNI API báo thất bại, không tiếp tục giả định kết quả hợp lệ. Trong nhiều tình huống chỉ một tập giới hạn API cleanup/exception handling được phép gọi khi exception đang pending. `ExceptionCheck` / `ExceptionOccurred` / `ExceptionClear` và các thao tác release phù hợp phải được dùng có chủ đích; **không tự ý xóa exception rồi trả kết quả thành công**.

### 9.7. Chỉ xóa local ref một lần không giải quyết mọi leak

Giải phóng local reference không làm object Java biến mất nếu còn reference khác. Ngược lại, global reference còn tồn tại có thể ngăn GC thu hồi object. Kiểm tra ownership thực tế: native code giữ local/global/weak reference nào, ai xóa, và bao giờ.

## 10. Quy tắc thực hành khi thiết kế API Java–JNI

- **Khai báo Java trước, sinh header bằng `javac -h`.** Đối chiếu `jobject`, `jclass`, `jstring`, `jintArray`, `jobjectArray` trong header thay vì tự viết chữ ký từ trí nhớ.
- **Dùng `JNIEnv` để thao tác object.** Không dereference, offset, pointer arithmetic hoặc `free` trên JNI object reference.
- **Ghi rõ ownership/lifetime.** Local chỉ trong native frame; global cần release; weak cần promote và kiểm tra null trước khi dùng.
- **Chọn chiến lược dữ liệu theo nhu cầu.** Với primitive arrays cần ít phần tử, `Get...ArrayRegion` đơn giản; với nhiều phần tử, `Get...ArrayElements` có thể phù hợp nhưng cần release; không giả định zero-copy.
- **Quy định encoding của chuỗi.** Phân biệt UTF-16 code units, Unicode code points, Modified UTF-8 và UTF-8 chuẩn.
- **Lưu ý exception và thread.** `JNIEnv*` không dùng chéo thread; mỗi JNI call phải xử lý kết quả lỗi và pending exception; object được share vẫn cần synchronized/memory model phù hợp.
- **Kiểm tra bằng công cụ phát hiện lỗi JNI khi cần.** Với HotSpot, `-Xcheck:jni` có thể phát hiện **một số** cách dùng JNI sai nhưng không chứng minh toàn bộ native memory-safe.
- **Giảm bề mặt native.** C/C++ chỉ nên nhận những kiểu/tham chiếu thực sự cần thiết và trả object/value qua API JNI, để Java tiếp tục quản lý đối tượng, còn native ownership được mô tả tường minh.

## 11. Tự kiểm tra kiến thức

1. Tại sao `jobject` không thể ép sang con trỏ C để truy cập field Java bằng offset?
2. Trong native method static, `jclass` nhận từ JVM là gì? Nó có phải C++ class pointer không?
3. Một hàm JNI nhận `jstring`. `GetStringLength` trả số byte UTF-8 hay UTF-16 code units?
4. Vì sao `GetIntArrayElements` phải ghép với `ReleaseIntArrayElements` ngay cả khi code chỉ đọc?
5. Tại sao `GetObjectArrayElement` trả một local reference và nó cần được xử lý khác với con trỏ C thông thường?
6. Nếu cần giữ `jobject` sau khi native method trả về, nên dùng kiểu reference nào và giải phóng bằng API nào?
7. Hai JNI references khác nhau cùng trỏ một Java object. Nên so sánh object identity bằng API nào?
8. `int[][]` ở chiều mảng ngoài có kiểu JNI nào? Mỗi phần tử hàng sẽ dùng kiểu nào?
9. Tại sao không nên truyền byte Modified UTF-8 của JNI như dữ liệu UTF-8 chuẩn mà không có bước xác minh?
10. Một thread native muốn sử dụng global reference được tạo ở thread khác cần lưu ý gì về `JNIEnv*`?

**Đáp án gợi ý:** (1) opaque handle, object layout do JVM quản lý; (2) object `Class`, không phải con trỏ class C++; (3) UTF-16 code units; (4) có thể copy/pin, phải giải phóng hoặc commit theo mode; (5) local JNI lifetime và JVM quản lý object; (6) `NewGlobalRef`/`DeleteGlobalRef`; (7) `IsSameObject`; (8) `jobjectArray` bên ngoài, `jintArray` cho hàng `int[]`; (9) hai encoding có quy tắc khác nhau; (10) thread phải attach và dùng `JNIEnv*` của chính thread, đồng thời bảo vệ truy cập object nếu cần.

## 12. Tài liệu chuẩn

- [Oracle JNI Specification — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)
- [Oracle JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)

**Điểm cốt lõi:** `jobject`, `jclass`, `jstring` và JNI array types là **tham chiếu đến các đối tượng JVM**, không phải địa chỉ bộ nhớ có thể diễn giải tùy ý từ C/C++. Việc đọc/ghi dữ liệu, so sánh object, quản lý local/global reference và giải phóng các buffer tạm đều phải thông qua hợp đồng `JNIEnv` tương ứng.
