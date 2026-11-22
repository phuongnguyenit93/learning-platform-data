# Tạo, duyệt mảng đối tượng và dọn tham chiếu cục bộ phát sinh trong JNI

## 1. Bài toán và kiến thức nền

Trong Java Native Interface (JNI), kiểu Java `String[]`, `Object[]`, `Person[]` hoặc `String[][]` được thao tác từ mã C/C++ qua **mảng đối tượng JNI** (`jobjectArray`). Một Java array vẫn là một đối tượng do JVM quản lý; ở phía C/C++, `jobjectArray` là **tham chiếu mờ (opaque reference)**, không phải con trỏ C trỏ trực tiếp vào vùng lưu các phần tử.

Bài học tập trung vào ba thao tác gắn chặt với nhau:

1. **Tạo mảng:** Dùng `NewObjectArray` với số phần tử, class của **phần tử** và giá trị khởi tạo.
2. **Duyệt và cập nhật:** Dùng `GetArrayLength`, `GetObjectArrayElement` và `SetObjectArrayElement`; phân biệt null, phần tử object hợp lệ và Java exception.
3. **Dọn local references phát sinh:** Mỗi `GetObjectArrayElement` lấy một phần tử khác null thông thường tạo **local JNI reference mới**. Trong vòng lặp dài, phải `DeleteLocalRef` ngay khi dùng xong hoặc quản lý local frame.

Ví dụ định hướng:

~~~text
Java: String[] labels = {"red", "blue", "green"};
           |
           v
JNI: jobjectArray labels
           |
           +-- GetArrayLength(labels)               -> 3
           +-- GetObjectArrayElement(labels, 0)     -> local jstring #1
           |       +-- xử lý phần tử "red"
           |       +-- DeleteLocalRef(local #1)
           +-- GetObjectArrayElement(labels, 1)     -> local jstring #2
           |       +-- xử lý phần tử "blue"
           |       +-- DeleteLocalRef(local #2)
           +-- GetObjectArrayElement(labels, 2)     -> local jstring #3
                   +-- xử lý phần tử "green"
                   +-- DeleteLocalRef(local #3)
~~~

**Điểm quan trọng nhất:** `DeleteLocalRef` xóa **handle JNI tạm do lượt đọc phần tử tạo ra**; nó **không xóa ô trong mảng Java**, không tự gán phần tử thành `null` và không gọi `free` trên Java object. Mảng vẫn giữ tham chiếu tới phần tử nếu phần tử chưa bị thay thế.

## 2. Kiểu JNI nào tương ứng với mảng Java?

| Kiểu Java | Kiểu tham số/kết quả JNI | Cách truy cập phần tử |
| --- | --- | --- |
| `Object[]`, `String[]`, `MyClass[]` | `jobjectArray` | `GetObjectArrayElement`, `SetObjectArrayElement` |
| `int[]` | `jintArray` | `GetIntArrayRegion`, `GetIntArrayElements` và API primitive array |
| `byte[]` | `jbyteArray` | `GetByteArrayRegion`, `GetByteArrayElements` |
| `double[]` | `jdoubleArray` | `GetDoubleArrayRegion`, `GetDoubleArrayElements` |
| `String[][]` | `jobjectArray` cho mảng ngoài, mỗi hàng là `jobjectArray` | Lấy hàng bằng `GetObjectArrayElement`, rồi lấy các String trong hàng |
| `int[][]` | `jobjectArray` cho mảng ngoài, mỗi hàng là `jintArray` | Lấy hàng bằng API object array, xử lý từng hàng bằng API int array |

Một biến `jobjectArray` không phải `jobject*`. Mặc dù Java `Object[]` chứa các tham chiếu tới object, **cách JVM biểu diễn và di chuyển đối tượng là chi tiết triển khai**. Đọc phần tử bằng `array[i]` như mảng C là sai hợp đồng JNI.

Descriptor JVM cần phân biệt:

~~~text
Ljava/lang/String;        một đối tượng String
[Ljava/lang/String;       mảng String[]
[[Ljava/lang/String;      mảng String[][]
[I                        mảng int[]
[[I                       mảng int[][]
~~~

Ký tự `[` biểu diễn một chiều mảng; `L...;` biểu diễn reference type, còn `I` là kiểu primitive `int`. Trong JNI C, phương thức nhận `String[]` có tham số `jobjectArray`; phương thức nhận `int[]` có tham số `jintArray`. Chọn API theo **loại phần tử của chiều đang thao tác**, không chỉ vì tất cả đều là mảng trong Java.

## 3. Tạo mảng đối tượng: `NewObjectArray`

Chữ ký JNI C theo dạng gọi qua `JNIEnv*`:

~~~c
jobjectArray result = (*env)->NewObjectArray(
        env, length, elementClass, initialElement);
~~~

Ý nghĩa tham số:

| Tham số | Kiểu | Vai trò |
| --- | --- | --- |
| `env` | `JNIEnv*` | Giao diện JNI của thread hiện tại |
| `length` | `jsize` | Số phần tử, phải không âm; cấp phát có thể thất bại nếu thiếu bộ nhớ |
| `elementClass` | `jclass` | Java class của **mỗi phần tử** được phép lưu trong mảng |
| `initialElement` | `jobject` hoặc `NULL` | Reference ban đầu được gán cho **mọi vị trí** |
| Kết quả | `jobjectArray` | **Local reference** tới mảng mới, hoặc `NULL` khi thất bại |

Để tạo một `String[]` gồm ba phần tử null:

~~~c
/* Ví dụ đặt trong một native method; chưa phải chương trình độc lập. */
jclass stringClass = (*env)->FindClass(env, "java/lang/String");
if (stringClass == NULL) {
    return NULL; /* Một Java exception có thể đang pending. */
}

jobjectArray values = (*env)->NewObjectArray(
        env, 3, stringClass, NULL);
(*env)->DeleteLocalRef(env, stringClass);

if (values == NULL) {
    return NULL; /* Ví dụ: có thể do OutOfMemoryError. */
}

/* values là local reference tới String[3] ban đầu toàn null. */
return values;
~~~

Các bước:

1. `FindClass("java/lang/String")` trả local `jclass` mô tả class của **phần tử String**. Đây không phải chuỗi descriptor `"Ljava/lang/String;"`.
2. `NewObjectArray(env, 3, stringClass, NULL)` cấp mảng `String[3]`. Java heap chứa đối tượng array; việc cấp phát và GC do JVM quản lý.
3. Sau khi tạo mảng, local ref `stringClass` không còn cần nữa, nên gọi `DeleteLocalRef`.
4. Có thể **return local `values`** trực tiếp từ native method trả `String[]`; JVM xử lý kết quả trước khi dọn local frame.
5. Không gọi `DeleteLocalRef(env, values)` rồi return `values`: reference đã bị xóa sẽ không còn hợp lệ.

### Giá trị khởi tạo không phải bản sao cho từng phần tử

Nếu `initialElement` không null, tất cả ô ban đầu trỏ đến **cùng một Java object**, không phải N object khác nhau.

~~~c
/* Minh họa: shared là một jobject hợp lệ của đúng elementClass. */
jobjectArray repeated = (*env)->NewObjectArray(
        env, 3, elementClass, shared);
~~~

Khi đó, thay đổi trạng thái object `shared` có thể nhìn thấy qua cả ba vị trí, miễn object thực tế mutable. Điều này giống Java:

~~~java
// Chỉ minh họa; không phải chương trình độc lập.
StringBuilder one = new StringBuilder("x");
StringBuilder[] repeated = {one, one, one};
repeated[0].append("y");
// repeated[1] và repeated[2] cũng trỏ tới object "xy".
~~~

Khi muốn ba object độc lập, phải tạo từng object riêng và `SetObjectArrayElement` cho từng ô.

### Các lỗi cần xét khi tạo

`NewObjectArray` có thể thất bại do `NegativeArraySizeException` (kích thước âm) hoặc `OutOfMemoryError`. `FindClass` có thể thất bại vì class không tìm thấy hoặc không khởi tạo/giải quyết được trong ngữ cảnh thích hợp. Nếu API trả `NULL` và có pending Java exception, **không tiếp tục như thể mảng đã được tạo**.

Đặc biệt: `elementClass` là class phần tử. Nếu dùng `FindClass("java/lang/Object")`, ta tạo `Object[]`, không phải `String[]`, dù sau đó chỉ đưa vào các `String`. Khi Java method khai báo trả `String[]`, cần tạo array runtime type tương thích, chẳng hạn `String[]`.

## 4. Đọc và duyệt mảng với `GetArrayLength`, `GetObjectArrayElement`

Đối với mảng object hợp lệ:

~~~c
jsize n = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < n; i++) {
    jobject element = (*env)->GetObjectArrayElement(env, array, i);
    if ((*env)->ExceptionCheck(env)) {
        return; /* Ví dụ: native method trả void. */
    }

    if (element != NULL) {
        /* Dùng element qua các JNI API thích hợp. */
        (*env)->DeleteLocalRef(env, element);
    }
}
~~~

**Cơ chế chi tiết:**

- `GetArrayLength` trả số phần tử (type `jsize`), không phải kích thước bộ nhớ tính theo byte. `String[]` dài 3 có length 3 dù các chuỗi có độ dài khác nhau.
- `GetObjectArrayElement(array, i)` trả **local `jobject`** cho phần tử thứ `i`. Với `String[]`, phần tử không null có thể được dùng như `jstring` theo kiểu runtime đã được Java kiểm tra.
- Nếu chính phần tử Java ở vị trí `i` là `null`, API trả `NULL`. Nếu chỉ số không hợp lệ, API có thể báo Java exception. Vì vậy **`NULL` chưa đủ để xác định mọi lỗi**; kiểm tra `ExceptionCheck` khi cần phân biệt.
- Local ref từ mỗi lượt đọc được giữ cho tới khi xóa, khi local frame bị pop hoặc khi native invocation kết thúc. **Nó không tự hết hạn khi vòng lặp C chạy sang lượt tiếp theo**.
- Sau khi xử lý phần tử, xóa local ref mới bằng `DeleteLocalRef(env, element)`, đặc biệt ở vòng lặp dài.

Lấy một phần tử khác null từ `String[]` không biến mảng thành sở hữu của C. Tương tự, không dùng `free(element)`, `delete element` hoặc ép opaque reference thành con trỏ trực tiếp tới dữ liệu JVM.

### Đọc string bên trong phần tử

Giả sử Java chắc chắn truyền `String[]`:

~~~c
/* Trích đoạn minh họa: không phải hàm độc lập. */
jobject obj = (*env)->GetObjectArrayElement(env, labels, 0);
if ((*env)->ExceptionCheck(env)) {
    return 0;
}
if (obj != NULL) {
    jsize units = (*env)->GetStringLength(env, (jstring) obj);
    /* units là số UTF-16 code units, không phải số byte UTF-8. */
    (*env)->DeleteLocalRef(env, obj);
    return units;
}
return 0;
~~~

Ép kiểu `(jstring) obj` **chỉ hợp lệ vì phần tử thực sự là String**, không phải vì `jobject` nào cũng có thể coi là String. Nếu mảng là `Object[]` chứa nhiều kiểu, kiểm tra kiểu bằng `IsInstanceOf` khi cần, hoặc thiết kế API chấp nhận đúng kiểu dữ liệu.

Với `GetStringUTFChars`, con trỏ kết quả cần `ReleaseStringUTFChars`. Đây là **quy tắc release khác** với `DeleteLocalRef`; hai hành động giải quyết hai tài nguyên khác nhau.

## 5. Ghi phần tử bằng `SetObjectArrayElement`

Chữ ký ý tưởng:

~~~c
(*env)->SetObjectArrayElement(env, array, index, value);
~~~

- `array`: `jobjectArray` hợp lệ.
- `index`: vị trí kiểu `jsize`; phải trong khoảng `0 <= index < GetArrayLength(array)`.
- `value`: `jobject` tương thích với runtime component type hoặc `NULL`.
- API trả `void`; để biết có lỗi trong đường xử lý, có thể dùng `ExceptionCheck` sau lệnh.

Tạo ba chuỗi Java và lưu vào mảng:

~~~c
/* Trích đoạn minh họa nằm trong native method có env và values hợp lệ. */
for (jsize i = 0; i < 3; i++) {
    jstring part = (*env)->NewStringUTF(env, "item");
    if (part == NULL) {
        return NULL;
    }

    (*env)->SetObjectArrayElement(env, values, i, part);
    jboolean failed = (*env)->ExceptionCheck(env);

    /* Xóa local handle part sau khi đã dùng xong. */
    (*env)->DeleteLocalRef(env, part);

    if (failed) {
        return NULL;
    }
}
return values;
~~~

**Tại sao vẫn giữ được phần tử sau khi `DeleteLocalRef`?** Sau khi `SetObjectArrayElement` thành công, chính **array** đã giữ reference tới Java String đó. Xóa local handle `part` chỉ giảm một JNI root tạm; element trong `values[i]` vẫn trỏ tới object. Khi Java nhận `values`, `values[0]` vẫn đọc được String bình thường.

Nếu muốn thay bằng null:

~~~c
/* Chỉ minh họa, slot phải nằm trong phạm vi hợp lệ. */
(*env)->SetObjectArrayElement(env, values, slot, NULL);
~~~

Điều đó thay đổi phần tử mảng. Khác biệt:

| Thao tác | Tác dụng lên mảng Java | Tác dụng lên JNI reference |
| --- | --- | --- |
| `SetObjectArrayElement(array, i, obj)` | Gán `obj` vào vị trí `i` | Không tự dọn local `obj` |
| `SetObjectArrayElement(array, i, NULL)` | Gán null cho vị trí `i` | Không tự dọn mọi local ref đang trỏ object cũ |
| `DeleteLocalRef(env, obj)` | **Không** đổi `array[i]` | Xóa local JNI handle `obj` |
| `GetObjectArrayElement(array, i)` | Chỉ đọc phần tử | Có thể tạo **local JNI reference mới** cần dọn |

**Kiểm tra kiểu khi ghi:** Nếu `array` thực tế là `String[]` mà ta cố lưu một `Integer`, JVM có thể ném `ArrayStoreException`. Sự tương thích phụ thuộc **component type của mảng tại runtime**. Java arrays có covariance (`String[]` là `Object[]` về mặt kiểu), nên việc chỉ thấy kiểu tham số `Object[]` không đồng nghĩa được lưu bất kỳ object nào.

**Kiểm tra chỉ số:** `SetObjectArrayElement` có thể ném `ArrayIndexOutOfBoundsException` nếu index sai. Một native exception đang pending cần được propagate hoặc xử lý có chủ đích, không tự mặc định lệnh ghi thành công.

## 6. Cơ chế local reference khi tạo và duyệt mảng

Đây là phần dễ gây lỗi nhất khi xử lý hàng nghìn object:

~~~text
Native frame đang chạy
|
+-- local jobjectArray result    (array tạo bởi NewObjectArray)
+-- local jclass stringClass     (tạo bởi FindClass)
|
+-- vòng lặp i = 0
|      +-- local jstring element0 (tạo bởi NewStringUTF)
|      +-- SetObjectArrayElement(result, 0, element0)
|      +-- DeleteLocalRef(element0)
|
+-- vòng lặp i = 1
|      +-- local jstring element1
|      +-- SetObjectArrayElement(result, 1, element1)
|      +-- DeleteLocalRef(element1)
|
+-- DeleteLocalRef(stringClass)
+-- return result sang Java
       +-- JVM giữ object kết quả hợp lệ
       +-- JVM dọn các local refs còn lại của native invocation
~~~

`stringClass` và từng `element` được dọn sớm. `result` là mảng cuối cùng nên **phải giữ hợp lệ để return**. Có thể dọn những local ref khác khi xong mà không làm mảng Java mất phần tử của nó.

### Vì sao vòng lặp cần dọn sớm?

Trường hợp **không tốt**:

~~~c
/* Minh họa: method xử lý mảng rất dài nhưng bỏ qua cleanup. */
for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(env, array, i);
    /* Xử lý obj, rồi qua vòng mới mà không DeleteLocalRef. */
}
~~~

Các local JNI references phát sinh ở mỗi vòng **không tự được xóa khi biến C `obj` được ghi đè**. Chúng có thể tích lũy trong cùng native frame. JNI bảo đảm dung lượng tối thiểu cho một số local refs (theo đặc tả, ít nhất 16 khi vào native method), nhưng **không bảo đảm có thể tích lũy tùy ý**. Trên các JVM khác nhau, tạo quá nhiều local refs có thể gây cảnh báo, lỗi cấp phát hoặc tiêu thụ tài nguyên tăng.

Trường hợp tốt:

~~~c
/* Minh họa: array hợp lệ; method giả định trả void. */
for (jsize i = 0; i < n; i++) {
    jobject obj = (*env)->GetObjectArrayElement(env, array, i);

    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    if (obj != NULL) {
        /* Xử lý obj trước khi xóa local handle. */
        (*env)->DeleteLocalRef(env, obj);
    }
}
~~~

**Lưu ý:** Có thể xóa local `obj` dù object đó vẫn còn nằm trong mảng hoặc còn reference ở Java. `DeleteLocalRef` không gọi destructor Java hay trực tiếp giải phóng Java heap; nó chỉ bỏ handle JNI. Trên JVM có GC, đối tượng chỉ có thể được thu hồi khi không còn strong roots và khi GC quyết định thực hiện.

### Local, global và weak global là các loại handle khác nhau

| Loại reference | Tạo ra bởi | Vòng đời |
| --- | --- | --- |
| Local | `GetObjectArrayElement`, `FindClass`, `NewStringUTF`, `NewObjectArray`, ... | Thuộc thread/frame JNI; dọn khi xóa, pop frame hoặc native invocation kết thúc |
| Global | `NewGlobalRef` | Tồn tại qua nhiều lời gọi và có thể dùng trên thread đã attach; dọn bằng `DeleteGlobalRef` |
| Weak global | `NewWeakGlobalRef` | Không giữ object sống một mình; có thể bị GC xóa đích, dọn bằng `DeleteWeakGlobalRef` |

Với bài toán **duyệt mảng trong một native method**, không cần biến từng phần tử thành global reference. Điều đó chỉ tăng chi phí quản lý và có thể giữ object sống không cần thiết. Nếu thật sự cần dùng object sau native method hoặc từ một thread khác, phải thiết kế ownership và vòng đời riêng, thường bằng global reference.

## 7. Ví dụ hoàn chỉnh Java 17 + C/JNI

Mục tiêu chương trình:

- Từ Java gọi native method tạo `String[]` bằng `NewObjectArray`.
- Mã C tạo từng Java String bằng `NewStringUTF`, gán qua `SetObjectArrayElement` và **dọn local `jstring` ngay sau khi gán**.
- Java in các phần tử đã tạo.
- Java gọi native method khác duyệt chính mảng đó: `GetArrayLength`, `GetObjectArrayElement`, `GetStringLength` rồi `DeleteLocalRef`.
- Output xác định, giúp kiểm tra rằng xóa local handles **không xóa nội dung trong Java array**.

Môi trường chạy: **Linux + JDK 17 trở lên + GCC** (JDK và C compiler phải tương thích CPU/ABI). Biến `JAVA_HOME` phải trỏ vào thư mục JDK. Dự án có hai tệp ban đầu:

~~~text
jni-object-array-demo/
  ObjectArrayWalkDemo.java
  object_array_walk.c
~~~

### 7.1. Tệp `ObjectArrayWalkDemo.java`

~~~java
import java.util.Arrays;

public final class ObjectArrayWalkDemo {
    static {
        System.loadLibrary("objectarraywalk");
    }

    private static native String[] makeLabels(int count);

    private static native int sumUtf16Units(String[] labels);

    public static void main(String[] args) {
        String[] labels = makeLabels(3);

        System.out.println("length=" + labels.length);
        System.out.println("labels=" + Arrays.toString(labels));
        System.out.println("utf16Units=" + sumUtf16Units(labels));
    }
}
~~~

Java khai báo hai native methods `static`. Trong C/JNI, vị trí tham số JNI thứ hai là `jclass` (đối với instance native method là `jobject receiver`). Tên `makeLabels` biểu thị hàm tạo `String[]` và `sumUtf16Units` biểu thị phép duyệt tính tổng số **UTF-16 code units**, không phải byte của UTF-8.

### 7.2. Tệp `object_array_walk.c`

~~~c
#include <jni.h>
#include <stdio.h>
#include "ObjectArrayWalkDemo.h"

JNIEXPORT jobjectArray JNICALL Java_ObjectArrayWalkDemo_makeLabels(
        JNIEnv *env, jclass owner, jint count) {
    (void) owner;

    if (count < 0 || count > 100) {
        jclass badArgument = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (badArgument != NULL) {
            (*env)->ThrowNew(
                    env, badArgument, "count must be between 0 and 100");
            (*env)->DeleteLocalRef(env, badArgument);
        }
        return NULL;
    }

    jclass stringClass = (*env)->FindClass(
            env, "java/lang/String");
    if (stringClass == NULL) {
        return NULL;
    }

    jobjectArray labels = (*env)->NewObjectArray(
            env, (jsize) count, stringClass, NULL);

    /* Mảng đã có runtime component type String. */
    (*env)->DeleteLocalRef(env, stringClass);

    if (labels == NULL) {
        return NULL;
    }

    for (jsize i = 0; i < (jsize) count; i++) {
        char buffer[32];
        int written = snprintf(
                buffer, sizeof buffer, "item-%d", (int) i);

        /* Kiểm tra rõ dù count <= 100 khiến buffer đủ dài. */
        if (written < 0 || (size_t) written >= sizeof buffer) {
            jclass errorClass = (*env)->FindClass(
                    env, "java/lang/IllegalStateException");
            if (errorClass != NULL) {
                (*env)->ThrowNew(
                        env, errorClass, "label formatting failed");
                (*env)->DeleteLocalRef(env, errorClass);
            }
            return NULL;
        }

        jstring item = (*env)->NewStringUTF(env, buffer);
        if (item == NULL) {
            return NULL; /* Ví dụ: pending OutOfMemoryError. */
        }

        (*env)->SetObjectArrayElement(
                env, labels, i, item);
        jboolean failed = (*env)->ExceptionCheck(env);

        /* Đúng kể cả nếu SetObjectArrayElement sinh exception:
           item đã được tạo, cần xóa handle local. */
        (*env)->DeleteLocalRef(env, item);

        if (failed) {
            return NULL;
        }
    }

    /* Giữ local ref tới array để trả kết quả về Java. */
    return labels;
}

JNIEXPORT jint JNICALL Java_ObjectArrayWalkDemo_sumUtf16Units(
        JNIEnv *env, jclass owner, jobjectArray labels) {
    (void) owner;

    if (labels == NULL) {
        jclass npe = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (npe != NULL) {
            (*env)->ThrowNew(env, npe, "labels must not be null");
            (*env)->DeleteLocalRef(env, npe);
        }
        return 0;
    }

    jsize n = (*env)->GetArrayLength(env, labels);
    jint total = 0;

    for (jsize i = 0; i < n; i++) {
        jobject obj = (*env)->GetObjectArrayElement(
                env, labels, i);

        if ((*env)->ExceptionCheck(env)) {
            return 0;
        }

        if (obj != NULL) {
            /* Vì Java parameter là String[], phần tử là String. */
            total += (*env)->GetStringLength(
                    env, (jstring) obj);

            /* Mỗi GetObjectArrayElement tạo local ref cần dọn. */
            (*env)->DeleteLocalRef(env, obj);
        }
    }

    return total;
}
~~~

Giải thích các điểm then chốt:

1. `FindClass("java/lang/String")` trả local `jclass` cho component type; `NewObjectArray` tạo đúng `String[]` có độ dài `count`.
2. `DeleteLocalRef(env, stringClass)` dọn handle local cho class sau khi tạo mảng; **không đổi kiểu runtime của `labels`**.
3. `snprintf` tạo các chuỗi C ASCII `item-0`, `item-1`, `item-2`. ASCII hợp lệ trong Modified UTF-8 nên `NewStringUTF` tạo các Java Strings tương ứng; không cần làm giả định tùy tiện về Unicode phức tạp.
4. `SetObjectArrayElement(labels, i, item)` lưu Java String vào mảng. **Ngay sau đó** xóa local handle `item`; object vẫn reachable từ `labels[i]`.
5. Với lỗi ở `SetObjectArrayElement`, code nhớ dọn local `item` rồi trả về để Java nhận pending exception. Đối với đường lỗi trước khi return, local `labels` còn lại sẽ được dọn khi native method kết thúc; không trả một giá trị giả coi như thành công.
6. Hàm `sumUtf16Units` lấy `jobject` mỗi lượt `GetObjectArrayElement`, dùng `GetStringLength` và **`DeleteLocalRef` trong chính vòng lặp**.
7. Một phần tử null không tạo local handle khác null và được bỏ qua khi cộng độ dài. Đối với input của ví dụ, không có null.

**Giới hạn có chủ đích:** Ví dụ áp dụng cho tối đa 100 phần tử, mỗi chuỗi được dựng bằng ASCII ngắn. Với ứng dụng thực, cần xác định giới hạn đầu vào, kiểm soát tràn tổng và quy ước mã hóa; không nên giữ nguyên các giới hạn demo cho API production. Cú pháp `ExceptionCheck`, `DeleteLocalRef` và `return` trong đường lỗi được chọn để không tiếp tục dùng đối tượng khi đang có pending Java exception.

### 7.3. Biên dịch và chạy trên Linux

Trong thư mục có hai file:

~~~bash
javac -h . ObjectArrayWalkDemo.java

gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libobjectarraywalk.so object_array_walk.c

java -Djava.library.path=. ObjectArrayWalkDemo
~~~

- `javac -h .` biên dịch class và sinh header `ObjectArrayWalkDemo.h` theo đúng chữ ký native methods; không nên đoán tên symbol JNI cho các class có package/overload.
- `gcc -fPIC -shared` tạo thư viện động cho Linux. Thư viện phải dùng kiến trúc tương thích với JVM đang chạy.
- `System.loadLibrary("objectarraywalk")` yêu cầu JVM tìm `libobjectarraywalk.so` trên Linux thông dụng, trong đường `java.library.path=.` được truyền lúc khởi động.

**Stdout chính xác** của ví dụ:

~~~text
length=3
labels=[item-0, item-1, item-2]
utf16Units=18
~~~

Vì `item-0`, `item-1` và `item-2` đều có sáu UTF-16 code units, tổng `6 + 6 + 6 = 18`. Kết quả `Arrays.toString(labels)` chứng minh các phần tử vẫn còn hợp lệ **sau khi mã C xóa từng local `jstring`**.

Trên macOS, binary thường là `libobjectarraywalk.dylib`, với JNI include `$JAVA_HOME/include/darwin` và tùy chọn linker như `clang -dynamiclib`. Trên Windows, thư viện thường là `objectarraywalk.dll`, cần include JNI `%JAVA_HOME%\include\win32` và build toolchain tương ứng với JVM. Đó là những thay đổi ở khâu build/nạp thư viện; hợp đồng `NewObjectArray`, `GetObjectArrayElement`, `SetObjectArrayElement` và local references vẫn giữ nguyên.

## 8. Dọn tham chiếu trong vòng lặp lớn: các chiến lược

### 8.1. Xóa từng phần tử bằng `DeleteLocalRef`

Với thao tác chỉ cần một phần tử tại một thời điểm, cách thường dùng là:

~~~c
/* Minh họa trong một native method trả void. */
jsize count = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < count; i++) {
    jobject value = (*env)->GetObjectArrayElement(
            env, array, i);

    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    if (value != NULL) {
        /* Xử lý value ... */
        (*env)->DeleteLocalRef(env, value);
    }
}
~~~

Đây là cách giảm số handles sống đồng thời mà **không** cần tính toán local frame phức tạp. Chú ý mọi đường thoát sớm (`return`, nhánh lỗi, break) sau khi đã tạo handle phải tuân theo cleanup của tài nguyên đang còn sở hữu; nếu native method return, JVM vẫn dọn những local refs còn lại, nhưng **không thay thế trách nhiệm release native buffers được lấy bằng API riêng**.

### 8.2. Dùng `PushLocalFrame` / `PopLocalFrame` khi một lượt tạo nhiều refs

Nếu mỗi phần tử cần hàng loạt class/object/string tạm, dùng local frame con để gom việc dọn:

~~~c
/* Minh họa trong native method trả void.
   array là jobjectArray hợp lệ; không dùng nested results ngoài frame. */
jsize n = (*env)->GetArrayLength(env, array);

for (jsize i = 0; i < n; i++) {
    if ((*env)->PushLocalFrame(env, 16) < 0) {
        return; /* Có thể có pending OutOfMemoryError. */
    }

    jobject item = (*env)->GetObjectArrayElement(env, array, i);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        return;
    }

    if (item != NULL) {
        /* Tạo/tra thêm các JNI local references nếu cần,
           chỉ sử dụng chúng trước khi pop frame. */
    }

    /* Dọn cùng lúc các refs của frame con (gồm item). */
    (*env)->PopLocalFrame(env, NULL);
}
~~~

`PushLocalFrame(env, 16)` yêu cầu JVM đảm bảo chỗ cho ít nhất 16 local references trong frame mới. `PopLocalFrame(env, NULL)` loại bỏ refs của frame đó. Nếu cần chuyển một object ra frame cha, phải dùng **giá trị `jobject` do `PopLocalFrame(env, result)` trả về**, không dùng handle cũ thuộc frame đã pop.

Hai cách **không bắt buộc dùng đồng thời**: nếu chỉ tạo một local reference trong vòng lặp, `DeleteLocalRef` đơn giản hơn. Với native thread được tạo bởi C/C++ rồi `AttachCurrentThread`, việc dọn rõ ràng còn quan trọng hơn vì local refs có thể tồn tại tới lúc thread detach nếu không quản lý.

### 8.3. `EnsureLocalCapacity` dùng khi nào?

`EnsureLocalCapacity(env, required)` giúp yêu cầu JVM bảo đảm khả năng tạo thêm local refs trong frame hiện tại, trả mã lỗi khi không đáp ứng được (có thể kèm pending exception). API này **không tự động xóa** local refs cũ và **không thay thế** `DeleteLocalRef`. Nếu xử lý hàng triệu phần tử, giải pháp vẫn là giữ số local handles sống đồng thời nhỏ bằng cleanup hoặc phân lô.

## 9. Mảng nhiều chiều: tạo và duyệt từng hàng

Java `String[][]` là **mảng chứa các phần tử `String[]`**, không phải một vùng phẳng `jstring**`. Ở C/JNI, mảng ngoài là `jobjectArray`, mỗi hàng cũng là `jobjectArray`.

Tạo mảng ngoài có hai hàng String[]:

~~~c
/* Minh họa trong native method, có JNIEnv* env. */
jclass rowClass = (*env)->FindClass(
        env, "[Ljava/lang/String;");
if (rowClass == NULL) {
    return NULL;
}

jobjectArray matrix = (*env)->NewObjectArray(
        env, 2, rowClass, NULL);
(*env)->DeleteLocalRef(env, rowClass);

if (matrix == NULL) {
    return NULL;
}

/* Từng phần tử matrix[0], matrix[1] ban đầu là null.
   Có thể tạo String[] riêng rồi SetObjectArrayElement cho từng hàng. */
return matrix;
~~~

**Vì sao dùng `"[Ljava/lang/String;"`?** `FindClass` cần class biểu diễn **phần tử của mảng ngoài**, tức `String[]`, nên dùng JNI array-class descriptor có dấu `[`. Còn khi tạo trực tiếp mảng `String[]` một chiều, component type là `java.lang.String` nên dùng `FindClass("java/lang/String")`.

Duyệt mảng hai chiều:

~~~c
/* Minh họa trong native method trả void; matrix hợp lệ. */
jsize rowCount = (*env)->GetArrayLength(env, matrix);
for (jsize r = 0; r < rowCount; r++) {
    jobject rowObj = (*env)->GetObjectArrayElement(
            env, matrix, r);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }
    if (rowObj == NULL) {
        continue; /* Java cho phép hàng null. */
    }

    jobjectArray row = (jobjectArray) rowObj;
    jsize colCount = (*env)->GetArrayLength(env, row);

    for (jsize c = 0; c < colCount; c++) {
        jobject element = (*env)->GetObjectArrayElement(
                env, row, c);
        if ((*env)->ExceptionCheck(env)) {
            (*env)->DeleteLocalRef(env, rowObj);
            return;
        }
        if (element != NULL) {
            /* Xử lý String của hàng r, c ... */
            (*env)->DeleteLocalRef(env, element);
        }
    }

    (*env)->DeleteLocalRef(env, rowObj);
}
~~~

**Có hai mức local references:** handle `rowObj` của từng hàng và handle `element` của từng ô. Cả hai cần cleanup đúng tầng. Java cho phép mảng nhiều chiều dạng răng cưa (số phần tử mỗi hàng khác nhau) và hàng `null`; vì vậy luôn kiểm tra từng `GetArrayLength(row)` theo hàng hiện tại thay vì giả định rectangular matrix.

Cần phân biệt với `int[][]`: mảng ngoài vẫn là `jobjectArray`, nhưng mỗi hàng là `jintArray` nên xử lý phần tử số bằng `GetIntArrayRegion` hoặc `GetIntArrayElements` cùng API release tương ứng.

## 10. Exception safety khi tạo, gán và duyệt

Các lệnh JNI có thể thất bại và để lại **pending Java exception**; JNI C không dùng cơ chế exception C++ để thể hiện toàn bộ trường hợp đó. Ví dụ:

| API | Lỗi có thể xảy ra | Cách xử lý thực tế |
| --- | --- | --- |
| `FindClass` | Không tìm được class hoặc lỗi resolution/loading | Kiểm tra `NULL`; để Java exception propagate hoặc xử lý có chủ đích |
| `NewObjectArray` | Size âm, không đủ bộ nhớ | Kiểm tra `NULL`, không dùng mảng khi tạo thất bại |
| `NewStringUTF` | Thiếu bộ nhớ, dữ liệu Modified UTF-8 không đúng hợp đồng | Kiểm tra kết quả; cung cấp encoding hợp lệ |
| `GetObjectArrayElement` | Index ngoài biên | Kiểm tra `ExceptionCheck`; không coi `NULL` là phần tử null một cách mù quáng |
| `SetObjectArrayElement` | Index sai hoặc phần tử không tương thích runtime component type | Sau lệnh `void`, kiểm tra `ExceptionCheck` nếu nhánh tiếp theo cần thành công |
| `PushLocalFrame` | Không cấp đủ capacity | Kiểm tra giá trị trả về; dừng đường xử lý bình thường |

Trong ví dụ hoàn chỉnh, đoạn mã có thứ tự:

~~~c
(*env)->SetObjectArrayElement(env, labels, i, item);
jboolean failed = (*env)->ExceptionCheck(env);
(*env)->DeleteLocalRef(env, item);
if (failed) {
    return NULL;
}
~~~

Đây là mẫu quan trọng: **dù gán thất bại, vẫn dọn local reference `item` đã được tạo trước đó**. `DeleteLocalRef` là thao tác dọn được phép trong những tình huống JNI có pending exception phù hợp. Không tiếp tục gọi `NewStringUTF` hoặc sử dụng object khác trên đường xử lý bình thường khi đã có pending Java exception.

### Những khác biệt dễ bị đánh đồng

- **Null element:** `GetObjectArrayElement` có thể trả `NULL` mà không có pending exception; đây là trường hợp dữ liệu Java `null` hợp lệ.
- **Lỗi cấp phát:** `NewObjectArray` hoặc `NewStringUTF` có thể trả `NULL` kèm exception; không được dereference.
- **Type mismatch:** `SetObjectArrayElement` cho `Integer` vào `String[]` không giống gán null; JVM từ chối bằng `ArrayStoreException`.
- **Invalid index:** Truy cập ngoài biên có thể sinh `ArrayIndexOutOfBoundsException`; hãy dùng `jsize n = GetArrayLength(...)` và lặp `i < n` thay vì đoán kích thước.
- **Native crash:** Ép `jobjectArray` sang con trỏ C rồi đọc/ghi bộ nhớ có thể làm crash tiến trình. Đây không còn chỉ là Java exception thông thường.

Không nên xóa exception bằng `ExceptionClear` một cách vô điều kiện để tiếp tục chạy: điều đó có thể làm mất lỗi thực và khiến Java nhận kết quả không đáng tin.

## 11. Đọc phần tử rồi lưu qua lời gọi hoặc thread khác: không dùng local ref cũ

`GetObjectArrayElement` tạo local reference trong **thread hiện tại**, thường có hiệu lực tới khi native method return hoặc được xóa sớm. **Không được lưu raw local `jobject` vào static/global C variable rồi dùng sau native return**:

~~~c
/* SAI: cached chỉ sao chép JNI local handle. */
static jobject cached = NULL;

static void rememberWrong(jobject element) {
    cached = element;
}
~~~

Cách đó không giữ object một cách hợp lệ. Nếu cần sử dụng cùng Java object giữa nhiều native calls hoặc threads, dùng hợp đồng **global reference**:

~~~c
/* Minh họa tạo global ref trong khi local còn hợp lệ. */
jobject stable = (*env)->NewGlobalRef(env, element);
if (stable == NULL) {
    /* Có thể có pending OutOfMemoryError. */
}

/* Khi hết người dùng và không còn truy cập song song: */
if (stable != NULL) {
    (*env)->DeleteGlobalRef(env, stable);
}
~~~

Đoạn này chỉ minh họa API; production cần thiết kế người sở hữu handle, đồng bộ truy cập, xử lý lỗi, thời điểm release và thread attach. Dù global reference có thể dùng từ thread được attach đúng, **`JNIEnv*` phải lấy từ chính thread đang chạy** và Java object vẫn có thể cần synchronization nếu mutable.

Nếu Java có thể giữ array/object và **truyền lại trong lần native call sau**, JVM sẽ cấp local reference mới cho invocation đó. Thiết kế này nhiều khi đơn giản hơn quản lý global refs ở native code.

## 12. Những lỗi phổ biến và cách sửa

### Lỗi 1: dùng object array như mảng con trỏ C

~~~c
/* SAI: jobjectArray là opaque JNI reference. */
jobject *items = (jobject *) array;
jobject first = items[0];
~~~

**Sửa:** `GetObjectArrayElement(env, array, 0)`, kiểm tra lỗi và `DeleteLocalRef` cho local result khi xong.

### Lỗi 2: quên dọn local references trong vòng lặp

~~~c
/* SAI VỀ QUẢN LÝ TÀI NGUYÊN NẾU n RẤT LỚN. */
for (jsize i = 0; i < n; i++) {
    jobject element = (*env)->GetObjectArrayElement(env, array, i);
    /* Xong vòng lặp mà không DeleteLocalRef(element). */
}
~~~

**Sửa:** `DeleteLocalRef(env, element)` mỗi vòng hoặc `PushLocalFrame`/`PopLocalFrame` cho từng batch. Biến `element` hết phạm vi C **không** tự xóa JNI handle.

### Lỗi 3: xóa local reference của mảng kết quả trước khi return

~~~c
/* SAI: result không còn hợp lệ khi return. */
(*env)->DeleteLocalRef(env, result);
return result;
~~~

**Sửa:** Để `result` còn hợp lệ, return trực tiếp. JVM sẽ xử lý object trả về và dọn local frame. Nếu kết quả nằm trong nested local frame, `PopLocalFrame(env, result)` phải tạo local reference tương ứng ở frame cha, và **trả giá trị do PopLocalFrame cung cấp**.

### Lỗi 4: tưởng `DeleteLocalRef(item)` làm trống `array[i]`

~~~c
/* Đây không phải câu lệnh xóa phần tử mảng. */
(*env)->DeleteLocalRef(env, item);
~~~

**Sửa:** Nếu muốn gán null, gọi `SetObjectArrayElement(env, array, i, NULL)`. Dọn local handle và thay nội dung array là **hai thao tác khác nhau**.

### Lỗi 5: dùng class của array thay vì class của phần tử

~~~c
/* Tạo Object[] khi mong muốn String[] là sai runtime type. */
jclass objectClass = (*env)->FindClass(env, "java/lang/Object");
jobjectArray wrongType = (*env)->NewObjectArray(
        env, 3, objectClass, NULL);
~~~

**Sửa:** Với `String[]`, dùng `FindClass("java/lang/String")` để lấy component class; với mảng ngoài `String[][]`, mới dùng class `"[Ljava/lang/String;"` làm component type.

### Lỗi 6: giữ local reference từ `GetObjectArrayElement` cho callback bất đồng bộ

Lời gọi native đã kết thúc thì local ref của nó hết hiệu lực. **Sửa:** tạo global reference khi local còn hợp lệ, rồi đảm bảo release, hoặc để Java truyền lại phần tử khi callback tương lai bắt đầu.

### Lỗi 7: dùng sai encoding cho `NewStringUTF`

`NewStringUTF` nhận **Modified UTF-8**, không phải mọi chuỗi byte UTF-8 bất kỳ. Với ví dụ `"item-0"` chỉ có ASCII nên không có khác biệt. Với nội dung Unicode tổng quát, cần xác định encoding và có thể dùng `NewString` cùng buffer UTF-16, hoặc chuyển mã đúng.

### Lỗi 8: nhầm object array với primitive array

`String[]` dùng `GetObjectArrayElement`; `int[]` dùng `GetIntArrayRegion`/`GetIntArrayElements`. Các con trỏ thu được từ API primitive array phải release đúng hàm (`ReleaseIntArrayElements`); `DeleteLocalRef` không thay thế release của vùng elements.

### Lỗi 9: mỗi lần `GetObjectArrayElement` trả cùng object thì không cần dọn

Ngay cả nếu mảng chứa nhiều ô cùng trỏ **một Java object**, mỗi lần `GetObjectArrayElement` có thể tạo một **local handle riêng**. Vì vậy vẫn phải dọn các handles phát sinh theo lượt đọc. Cùng object identity không có nghĩa cùng vòng đời JNI reference.

## 13. Kiểm tra lỗi và hiệu năng trong ứng dụng thực

Với các mảng object lớn, chi phí có thể đến từ:

- Nhiều lời gọi JNI `GetObjectArrayElement`/`SetObjectArrayElement` và lượng local references tạm.
- Tạo nhiều Java object mới bằng `NewStringUTF`/`NewObject`.
- Chuyển đổi dữ liệu ký tự giữa Modified UTF-8, UTF-16 và encoding bên ngoài.
- Áp lực GC do số lượng Java arrays và objects, cùng chi phí xử lý Java exceptions nếu xảy ra.
- Việc giữ local/global references quá lâu, làm Java objects còn reachable không cần thiết.

**Không mặc định mọi lời gọi JNI đều zero-copy.** Với object arrays, ta thao tác qua các handles và JVM API; không có một lời hứa rằng toàn bộ mảng là vùng nhớ C liên tục có thể dereference trực tiếp.

Trên HotSpot, thử chạy demo với JNI checks:

~~~bash
java -Xcheck:jni -Djava.library.path=. ObjectArrayWalkDemo
~~~

`-Xcheck:jni` có thể phát hiện một số cách dùng JNI sai và tạo thông tin chẩn đoán; nó không thể chứng minh native code hoàn toàn an toàn. Với ứng dụng thực, nên thử cả array rỗng, có phần tử null, có hàng null nếu mảng hai chiều, array dài, lỗi index/type, OOME và các đường thoát sớm để kiểm tra cleanup.

Một danh sách tối thiểu khi review vòng lặp JNI object array:

1. Đúng `jobjectArray` cho runtime array type và đúng `jclass` cho element type?
2. Có `GetArrayLength`, ràng buộc `0 <= i < n` và xử lý array null?
3. Mỗi phần tử lấy từ `GetObjectArrayElement` có được dùng trong thread/frame còn hợp lệ?
4. Có phân biệt null element với pending exception?
5. Có `DeleteLocalRef` cho từng local reference mới phát sinh, kể cả đường lỗi?
6. `SetObjectArrayElement` có kiểm tra compatibility và pending exception khi cần?
7. Nếu return mảng, local result còn hợp lệ đến lúc return?
8. Nếu có buffer/string chars, có release bằng **đúng API**, không nhầm với `DeleteLocalRef`?
9. Với nested arrays, có dọn cả local ref của hàng và phần tử?
10. Có tránh giữ local refs xuyên native calls/threads và có chiến lược ownership khi thật sự cần global refs?

## 14. Tự kiểm tra kiến thức

1. `NewObjectArray(env, 4, stringClass, NULL)` tạo gì? Ban đầu các phần tử có giá trị nào?
2. Nếu `initialElement` là một `StringBuilder`, bốn ô trong mảng mới có trỏ tới bốn instance riêng không?
3. Vì sao `GetObjectArrayElement` không thể thay bằng `array[index]` trong C?
4. `GetObjectArrayElement` trả `NULL`: làm sao phân biệt một phần tử Java null với một lỗi có pending exception?
5. Sau `SetObjectArrayElement(array, i, part)` thành công, xóa `DeleteLocalRef(part)` có làm `array[i]` thành null không?
6. Tại sao một vòng lặp đọc một triệu phần tử nên chủ động `DeleteLocalRef` từng phần tử thay vì chỉ chờ native method return?
7. `String[][]` dùng loại JNI nào ở chiều ngoài, và cần class nào làm component type khi tạo mảng ngoài?
8. Khi muốn trả `jobjectArray` do native method tạo, có được `DeleteLocalRef` với chính mảng đó rồi return handle cũ không?
9. `SetObjectArrayElement` ghi một `Integer` vào `String[]` thường gặp loại Java exception nào?
10. Khi cần giữ phần tử array để native thread khác dùng sau khi method đã return, local `jobject` có đủ không?
11. Vì sao `GetStringUTFChars` yêu cầu release khác `DeleteLocalRef`?
12. Làm sao chạy demo để HotSpot kiểm tra thêm một số lỗi JNI?

**Đáp án gợi ý:** (1) `String[4]` với bốn phần tử null; (2) không, cùng tham chiếu `initialElement`; (3) array là opaque JNI ref; (4) kiểm tra pending exception; (5) không, array vẫn giữ object; (6) giới hạn số JNI local handles sống đồng thời; (7) `jobjectArray`, component class `"[Ljava/lang/String;"`; (8) không, chỉ return ref hợp lệ hoặc sử dụng kết quả `PopLocalFrame`; (9) `ArrayStoreException`; (10) không, cần global ref hoặc thiết kế Java giao lại dữ liệu; (11) string chars buffer có API release riêng, khác JNI object handle; (12) thêm `-Xcheck:jni` khi chạy.

## 15. Tài liệu chuẩn

- [Oracle JNI Specification — Array Operations: `NewObjectArray`, `GetObjectArrayElement`, `SetObjectArrayElement`](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Local and Global References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle JNI Specification — JNI Types and Array Descriptors](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)
- [Java SE 17 — `String` và UTF-16](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)

**Điểm cần nhớ:** `NewObjectArray` tạo **Java object array**, `GetObjectArrayElement` tạo handle local khi lấy phần tử, còn `SetObjectArrayElement` thay giá trị của **ô trong mảng**. Thao tác gán thành công không buộc JNI giữ local `jobject` mãi; **xóa local reference sau khi dùng không xóa Java object đang được array giữ**. Luôn tách rõ **vòng đời của Java array/object** với **vòng đời của JNI local handles**, nhất là trong vòng lặp dài và khi có ngoại lệ.
