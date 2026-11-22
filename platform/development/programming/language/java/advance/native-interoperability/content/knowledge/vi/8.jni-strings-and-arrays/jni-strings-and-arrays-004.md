# Đọc hoặc ghi một vùng mảng bằng GetArrayRegion và SetArrayRegion trong JNI

## Mục tiêu

Khi chương trình Java gọi mã C/C++ qua Java Native Interface (JNI), đôi khi native code chỉ cần **đọc một đoạn** của mảng Java hoặc **ghi kết quả vào một đoạn** của mảng đó. JNI cung cấp họ hàm `Get<PrimitiveType>ArrayRegion` và `Set<PrimitiveType>ArrayRegion` để sao chép các phần tử trong một vùng xác định.

Sau bài này, bạn có thể:

- Hiểu chính xác ý nghĩa của `array`, `start`, `len` và `buf` trong hai họ API; phân biệt **index phần tử** với **byte offset**.
- Chọn đúng hàm cho tám kiểu mảng nguyên thủy của Java: `boolean[]`, `byte[]`, `char[]`, `short[]`, `int[]`, `long[]`, `float[]`, `double[]`.
- Đọc dữ liệu từ mảng Java vào buffer C, hoặc ghi dữ liệu từ buffer C vào mảng Java, mà không cần giữ một con trỏ tới toàn bộ mảng.
- Kiểm tra bounds và buffer capacity an toàn; phát hiện ngoại lệ JNI thay vì tiếp tục chạy với dữ liệu không hợp lệ.
- Biên dịch và chạy ví dụ Java 17 + JNI C thực hiện cả `GetIntArrayRegion` và `SetIntArrayRegion`, gồm đọc theo từng chunk để không cần buffer lớn.
- Biết khi nào nên chọn `Get/Set<Type>ArrayRegion`, khi nào cân nhắc `Get/Release<Type>ArrayElements`, và vì sao các API region không áp dụng trực tiếp cho `Object[]`.

> **Lưu ý tên API:** Không có hai hàm JNI thực thi độc lập mang tên chính xác `GetArrayRegion` và `SetArrayRegion`. Đó là cách gọi rút gọn của **họ hàm theo kiểu nguyên thủy**, ví dụ `GetByteArrayRegion`, `SetByteArrayRegion`, `GetIntArrayRegion` hoặc `SetIntArrayRegion`.

## 1. Mô hình dữ liệu: mảng Java và buffer native

Giả sử Java có:

~~~java
int[] values = {10, 20, 30, 40, 50, 60};
~~~

Ta chỉ muốn đọc ba phần tử bắt đầu ở index 1:

~~~text
Java int[]:
index       0    1    2    3    4    5
value      10   20   30   40   50   60
                 |-------------|
                    start=1
                    len=3

GetIntArrayRegion(values, 1, 3, buf)
                              ↓
C buffer:   buf[0]=20, buf[1]=30, buf[2]=40
~~~

Mô hình này có bốn điểm:

1. `start` là **index của phần tử đầu tiên trong Java array**, tính từ 0.
2. `len` là **số lượng phần tử**, không phải byte và không phải index cuối cùng.
3. `buf` là một vùng nhớ native do caller chuẩn bị, phải chứa đủ `len` phần tử của kiểu JNI tương ứng. Dữ liệu copy luôn bắt đầu từ `buf[0]`.
4. `GetIntArrayRegion` chỉ **copy từ Java sang native buffer**; nó không xóa hay thay đổi phần tử gốc của mảng.

Hướng ngược lại:

~~~text
C buffer: [7, 8, 9]

SetIntArrayRegion(values, 2, 3, buf)
                               ↓
Java int[] sau khi ghi:
index       0    1    2    3    4    5
value      10   20    7    8    9   60
                       |------------|
                         start=2
                         len=3
~~~

Ở đây `SetIntArrayRegion` đọc **ba `jint` từ buffer C** rồi ghi đè đúng `values[2]`, `values[3]`, `values[4]`. Các phần tử Java nằm ngoài vùng không được sửa bởi thao tác này. Sau khi ghi xong, `buf` vẫn là buffer của native code; JVM không tiếp quản quyền sở hữu hoặc tự động giải phóng nó.

## 2. Chữ ký hàm và ý nghĩa tham số

Dạng C tổng quát theo JNI specification:

~~~c
void Get<PrimitiveType>ArrayRegion(
    JNIEnv *env, ArrayType array,
    jsize start, jsize len, NativeType *buf);

void Set<PrimitiveType>ArrayRegion(
    JNIEnv *env, ArrayType array,
    jsize start, jsize len, const NativeType *buf);
~~~

Đây là **mẫu tên API trong tài liệu**; mã C thực tế phải thay `<PrimitiveType>` bằng `Int`, `Byte`, `Double`,... và `ArrayType`/`NativeType` bằng kiểu JNI cụ thể.

| Thành phần | Vai trò | Chú ý |
|---|---|---|
| `JNIEnv *env` | Giao diện JNI gắn với thread hiện hành | Không lấy `JNIEnv*` của thread này đem dùng trên thread khác |
| `array` | Reference tới mảng Java nguyên thủy | Phải có kiểu mảng khớp hàm; không truyền `NULL` |
| `start` | Index bắt đầu trong Java array | Phải không âm và hợp lệ |
| `len` | Số phần tử cần copy | Không âm; không tính bằng byte |
| `buf` (Get) | **Đích** trong bộ nhớ C | Có đủ chỗ cho `len` phần tử; không `NULL` |
| `buf` (Set) | **Nguồn** trong bộ nhớ C | Đã khởi tạo dữ liệu cần ghi; không `NULL` |
| Kiểu trả về | `void` | Thành công/thất bại được nhận biết qua **JNI exception**, không có mã trả về |

Hàm tương ứng thường được viết như sau trong source C:

~~~c
(*env)->GetIntArrayRegion(env, javaArray, start, len, buf);
(*env)->SetIntArrayRegion(env, javaArray, start, len, buf);
~~~

Với C++ dùng JNI C++ wrapper, cú pháp thông thường là:

~~~cpp
env->GetIntArrayRegion(javaArray, start, len, buf);
env->SetIntArrayRegion(javaArray, start, len, buf);
~~~

Hai đoạn trên **minh họa cú pháp gọi** trong một native function đang có đủ các biến và kiểu hợp lệ. Đừng trộn cú pháp C và C++: `(*env)->...` là kiểu dùng trong C, còn `env->...` là cú pháp của JNI C++ interface.

### 2.1. Tám cặp hàm được hỗ trợ

| Java array | JNI array reference | Kiểu buffer C | Hàm đọc và ghi vùng |
|---|---|---|---|
| `boolean[]` | `jbooleanArray` | `jboolean` | `GetBooleanArrayRegion` / `SetBooleanArrayRegion` |
| `byte[]` | `jbyteArray` | `jbyte` | `GetByteArrayRegion` / `SetByteArrayRegion` |
| `char[]` | `jcharArray` | `jchar` | `GetCharArrayRegion` / `SetCharArrayRegion` |
| `short[]` | `jshortArray` | `jshort` | `GetShortArrayRegion` / `SetShortArrayRegion` |
| `int[]` | `jintArray` | `jint` | `GetIntArrayRegion` / `SetIntArrayRegion` |
| `long[]` | `jlongArray` | `jlong` | `GetLongArrayRegion` / `SetLongArrayRegion` |
| `float[]` | `jfloatArray` | `jfloat` | `GetFloatArrayRegion` / `SetFloatArrayRegion` |
| `double[]` | `jdoubleArray` | `jdouble` | `GetDoubleArrayRegion` / `SetDoubleArrayRegion` |

**Tại sao dùng kiểu JNI?** `jint` tương ứng Java `int` (32 bit), `jlong` tương ứng Java `long` (64 bit), `jchar` là UTF-16 code unit 16 bit; không tự giả định `long` của C luôn bằng Java `long`. `jboolean` biểu diễn boolean qua giá trị JNI `JNI_FALSE` / `JNI_TRUE`; khi thao tác, sử dụng kiểu JNI được chỉ định. `jbyte` là 8-bit signed tương ứng `byte` của Java.

Vùng sao chép được tính theo **phần tử**: `GetLongArrayRegion(..., start, 3, buf)` yêu cầu chỗ cho ba `jlong`, không phải ba byte. Nếu một buffer C được cấp phát động, tính kích thước dựa trên `sizeof(jlong)` và kiểm tra overflow của phép nhân cấp phát.

### 2.2. Tại sao `Object[]` không dùng các hàm trên?

`Get<PrimitiveType>ArrayRegion`/`Set<PrimitiveType>ArrayRegion` dành cho **primitive arrays**. Với `String[]` hoặc `MyObject[]`, JNI có `GetObjectArrayElement` và `SetObjectArrayElement` theo từng index; mỗi `jobject` lấy ra là JNI reference cần quản lý đúng vòng đời. Không giả định tồn tại `GetObjectArrayRegion` tương đương những hàm dành cho kiểu nguyên thủy.

Với `String` còn có `GetStringRegion` và `GetStringUTFRegion`, nhưng đó là **API thao tác chuỗi** có ngữ nghĩa đơn vị ký tự/modified UTF-8 riêng; không thay thế primitive array region.

## 3. Điều kiện hợp lệ của vùng và cách tránh overflow

Đặt:

- `n = GetArrayLength(env, array)`.
- `start` là vị trí bắt đầu.
- `len` là số phần tử.

Một vùng chuẩn có dạng nửa mở `[start, start + len)`. Khi xử lý cả vùng rỗng, có thể biểu diễn `len == 0` mà không cần copy phần tử.

Cách kiểm tra **an toàn khi dùng số nguyên có dấu**:

~~~c
if (start < 0 || len < 0 || start > n || len > n - start) {
    /* Vùng không hợp lệ */
}
~~~

**Vì sao không chỉ dùng `start + len > n`?** Nếu đầu vào là số nguyên rất lớn, phép cộng signed trong C có thể overflow trước khi so sánh. Sau khi kiểm tra `start >= 0` và `start <= n`, biểu thức `n - start` luôn không âm, giúp kiểm tra `len` mà không cần cộng quá giới hạn. Điều này cũng là ý tưởng dùng trong Java với `int`/`jsize`.

Ví dụ cho mảng sáu phần tử:

| `start` | `len` | Ý nghĩa | Kết luận |
|---:|---:|---|---|
| 1 | 3 | Index 1, 2, 3 | Hợp lệ |
| 0 | 6 | Toàn bộ mảng | Hợp lệ |
| 3 | 0 | Vùng rỗng | Hợp lệ theo kiểm tra ứng dụng; không cần copy |
| 6 | 0 | Vùng rỗng ở cuối | Có thể xử lý ở tầng ứng dụng mà **không gọi hàm region** |
| -1 | 1 | Start âm | Không hợp lệ |
| 4 | 3 | Vượt quá index 5 | Không hợp lệ |
| 2 | -1 | Độ dài âm | Không hợp lệ |
| 7 | 0 | Start ngoài mảng | Không hợp lệ |

Trong ví dụ runnable ở dưới, khi `len == 0`, native code chủ động bỏ qua `Get/Set...ArrayRegion` nên không phụ thuộc vào cách triển khai JNI xử lý pointer/boundary cho copy độ dài 0. Đặc tả JNI yêu cầu `buf` khác `NULL` khi **thực sự gọi** hàm region; không truyền `NULL` chỉ vì `len == 0`.

### `GetArrayLength` trả gì?

~~~c
jsize n = (*env)->GetArrayLength(env, array);
~~~

`GetArrayLength` trả độ dài của mảng Java; kiểu `jsize` là kiểu nguyên dùng cho kích thước/index JNI. API cũng dùng cho object array nhưng không có nghĩa object array hỗ trợ `Get<Type>ArrayRegion`. `array` phải là JNI array reference hợp lệ, khác `NULL`.

**Không nhầm ba đơn vị**:

- `start`/`len`: **số phần tử Java**.
- `sizeof(jint) * len`: số **byte native** tối thiểu khi chứa `len` giá trị `jint` liên tiếp trong C.
- `sizeof(array)` với biến `jintArray` trong C: kích thước **biến JNI reference**, hoàn toàn không phải số byte của Java array.

## 4. Get: sao chép dữ liệu từ Java sang bộ nhớ native

Ví dụ C cho một mảng `int[]`, trong hàm native đã nhận biến `jintArray numbers` và kiểm tra `start`/`len`:

~~~c
jint local[3];

(*env)->GetIntArrayRegion(env, numbers, 1, 3, local);
if ((*env)->ExceptionCheck(env)) {
    return;  // Mẫu dùng trong hàm native trả void.
}

/* local[0], local[1], local[2] chứa bản sao giá trị Java. */
~~~

Hàm `GetIntArrayRegion` viết các giá trị vào vùng nhớ C mà `local` trỏ tới. Có thể dùng stack buffer như trên cho đoạn nhỏ, hoặc heap buffer được cấp phát và kiểm tra dung lượng với đoạn lớn. **Mảng Java không bị thay đổi** chỉ vì bạn sửa `local[0]` sau khi copy; muốn ghi lại, phải gọi `SetIntArrayRegion`.

Cụ thể:

~~~text
Java:    [4, 8, 15, 16, 23, 42]
Get: start=2, len=3
C:       [15, 16, 23]

C sửa local[1] thành 99:
C:       [15, 99, 23]
Java:    [4, 8, 15, 16, 23, 42]   (chưa thay đổi)
~~~

**Không có hàm release tương ứng với `GetIntArrayRegion`.** Chỉ có một lần copy; buffer thuộc trách nhiệm của mã native. Nếu cần giữ buffer, tự quản lý nó; nếu không, stack buffer hết hiệu lực khi hàm C return. Không được lưu địa chỉ stack buffer dùng sau khi hàm native kết thúc.

## 5. Set: sao chép từ buffer native vào mảng Java

Ví dụ ghi ba số ở các index 2–4:

~~~c
jint patch[3] = {7, 8, 9};

(*env)->SetIntArrayRegion(env, numbers, 2, 3, patch);
if ((*env)->ExceptionCheck(env)) {
    return;
}
~~~

Nếu `numbers` trước đó là `[10, 20, 30, 40, 50, 60]`, sau khi ghi hợp lệ sẽ là:

~~~text
[10, 20, 7, 8, 9, 60]
~~~

`SetIntArrayRegion` **không** phải “nhận quyền sở hữu” vùng `patch`. Java array giữ bản sao các giá trị; sau khi API hoàn tất, buffer C có thể tiếp tục được sử dụng hoặc giải phóng theo quy tắc C. Với kiểu nguyên thủy, không có `jobject` hay local reference riêng cho từng phần tử.

Không gọi `Set<Type>ArrayRegion` khi `buf` trỏ vào bộ nhớ chưa khởi tạo hoặc không đủ số phần tử. JVM không thể suy ra capacity của một con trỏ C thô, nên lỗi capacity có thể trở thành truy cập bộ nhớ không hợp lệ thay vì một Java exception có thể bắt.

## 6. Ví dụ hoàn chỉnh Java 17 + JNI C: copy một đoạn rồi ghi vùng

Ta xây hai native method:

1. `copyRegion(int[] source, int start, int len)` tạo một mảng Java mới rồi copy vùng nguồn theo từng khối nhỏ: **Get từ mảng nguồn → buffer C → Set vào mảng kết quả**.
2. `fillRegion(int[] destination, int start, int len, int value)` tạo một buffer `jint` chứa giá trị cần ghi và dùng **Set vào mảng Java đang có**.

Cả hai đều xác minh bounds. Buffer cố định tám `jint` nên không cần `malloc` và không giữ phần tử Java qua nhiều JNI calls. Ví dụ này dùng lớp ở **default package** để tên JNI và lệnh build dễ thử.

### 6.1. File `JniRegionDemo.java`

~~~java
import java.util.Arrays;

public final class JniRegionDemo {
    static {
        System.loadLibrary("jniregiondemo");
    }

    private static native int[] copyRegion(
            int[] source, int start, int length);

    private static native void fillRegion(
            int[] destination, int start, int length, int value);

    public static void main(String[] args) {
        int[] numbers = {10, 20, 30, 40, 50, 60};

        int[] part = copyRegion(numbers, 1, 3);
        System.out.println("part=" + Arrays.toString(part));

        fillRegion(numbers, 2, 2, 99);
        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("partAfterWrite=" + Arrays.toString(part));

        int[] empty = copyRegion(numbers, numbers.length, 0);
        System.out.println("empty=" + Arrays.toString(empty));

        try {
            copyRegion(numbers, 5, 2);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println(
                    "bounds=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Ý nghĩa của thử nghiệm:

- `copyRegion(numbers, 1, 3)` chọn ba phần tử `20, 30, 40` và tạo **mảng mới**, không dùng chung storage với `numbers`.
- `fillRegion(numbers, 2, 2, 99)` ghi vào hai index `2` và `3` của mảng gốc.
- `part` giữ nguyên dù `numbers` sau đó thay đổi, vì `Get/Set...ArrayRegion` đã tạo **bản sao giá trị**, không tạo một Java array view.
- `copyRegion(numbers, numbers.length, 0)` trả `int[0]`; không gọi hàm region với `len == 0`.
- `copyRegion(numbers, 5, 2)` vượt bounds và bị từ chối trước khi copy.

### 6.2. Sinh JNI header

Dùng JDK 17+ tại thư mục chứa file Java:

~~~bash
javac -h . JniRegionDemo.java
~~~

Lệnh này sinh `JniRegionDemo.class` và `JniRegionDemo.h`. Header được tạo theo chữ ký thật của hai native method. Khi thay đổi class/package hoặc overload native method, phải sinh lại header rồi build lại mã C tương ứng.

### 6.3. File `jniregiondemo.c`

~~~c
#include "JniRegionDemo.h"

#define BLOCK_SIZE 8

/* Hàm phụ trợ gọi Java exception khi chưa có exception pending. */
static void throw_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass exception_class = (*env)->FindClass(env, class_name);
    if (exception_class == NULL) {
        return; /* Để nguyên exception do FindClass gây ra. */
    }

    (*env)->ThrowNew(env, exception_class, message);
    (*env)->DeleteLocalRef(env, exception_class);
}

/* Kiểm tra bounds an toàn: tránh overflow start + count. */
static jboolean valid_range(JNIEnv *env, jintArray array,
                            jint start, jint count) {
    if (array == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "array must not be null");
        return JNI_FALSE;
    }

    jsize length = (*env)->GetArrayLength(env, array);
    if (start < 0 || count < 0 ||
        start > length || count > length - start) {
        throw_java(env, "java/lang/ArrayIndexOutOfBoundsException",
                   "invalid start or length");
        return JNI_FALSE;
    }

    return JNI_TRUE;
}

JNIEXPORT jintArray JNICALL
Java_JniRegionDemo_copyRegion(
        JNIEnv *env, jclass clazz, jintArray source,
        jint start, jint count) {
    (void)clazz;

    if (!valid_range(env, source, start, count)) {
        return NULL;
    }

    jintArray result = (*env)->NewIntArray(env, count);
    if (result == NULL) {
        return NULL; /* Giữ nguyên lỗi allocation của JVM. */
    }

    jint buffer[BLOCK_SIZE];

    for (jsize copied = 0; copied < count; ) {
        jsize remaining = count - copied;
        jsize batch = remaining < BLOCK_SIZE
                ? remaining : BLOCK_SIZE;

        /* Copy từ source[start + copied] vào buffer[0]. */
        (*env)->GetIntArrayRegion(
                env, source, start + copied, batch, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return NULL;
        }

        /* Copy từ buffer[0] vào result[copied]. */
        (*env)->SetIntArrayRegion(
                env, result, copied, batch, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return NULL;
        }

        copied += batch;
    }

    return result;
}

JNIEXPORT void JNICALL
Java_JniRegionDemo_fillRegion(
        JNIEnv *env, jclass clazz, jintArray destination,
        jint start, jint count, jint value) {
    (void)clazz;

    if (!valid_range(env, destination, start, count)) {
        return;
    }

    jint buffer[BLOCK_SIZE];
    for (jsize i = 0; i < BLOCK_SIZE; ++i) {
        buffer[i] = value;
    }

    for (jsize written = 0; written < count; ) {
        jsize remaining = count - written;
        jsize batch = remaining < BLOCK_SIZE
                ? remaining : BLOCK_SIZE;

        (*env)->SetIntArrayRegion(
                env, destination, start + written, batch, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return;
        }

        written += batch;
    }
}
~~~

**Đọc từng đoạn mã:**

1. `valid_range` dùng `GetArrayLength` để kiểm tra `start` và `count`. Khi array `null`, nó tạo `NullPointerException`; khi vùng vượt bounds, tạo `ArrayIndexOutOfBoundsException`. Cả hai nhánh đều trả về trước khi gọi region API với tham số sai.
2. `NewIntArray` tạo Java array đích có `count` phần tử. Nếu cấp phát thất bại, không được dùng `result` như mảng hợp lệ.
3. `GetIntArrayRegion` copy tối đa tám phần tử từ source sang `buffer`, `SetIntArrayRegion` copy chính tám phần tử ấy sang result. Vòng lặp xử lý mảng dài tùy ý theo nhiều chunk nhưng dùng lượng stack memory cố định.
4. `fillRegion` chuẩn bị tám `jint` cùng giá trị `value`, sau đó dùng `SetIntArrayRegion` ghi liên tiếp các khối. Không cần `Get` vì việc ghi này không phụ thuộc giá trị cũ.
5. `ExceptionCheck` được gọi ngay sau mỗi region API; nếu có ngoại lệ, native method dừng. Với `GetIntArrayRegion`/`SetIntArrayRegion`, **không có `ReleaseIntArrayRegion`**.
6. `result` là local JNI reference được trả về Java, JVM xử lý khi native method return. Buffer `jint[8]` thuộc stack C; không trả địa chỉ buffer này về Java.

Không có lời gọi `DeleteLocalRef` cho `result` ở nhánh thành công, vì ta đang trả nó cho Java. Ở nhánh lỗi, local references không được trả về sẽ được JVM thu hồi khi native frame kết thúc.

### 6.4. Build thư viện native theo hệ điều hành

Dùng **JDK có JNI headers** và native compiler phù hợp với OS, kiến trúc/ABI của JVM. Mỗi nhóm lệnh sau dành cho một môi trường, không chạy đồng thời.

**Linux — GCC:**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  jniregiondemo.c -o libjniregiondemo.so

java -Djava.library.path=. JniRegionDemo
~~~

**macOS — Clang:**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  jniregiondemo.c -o libjniregiondemo.dylib

java -Djava.library.path=. JniRegionDemo
~~~

**Windows — MSVC Developer Command Prompt:**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jniregiondemo.c /Fe:jniregiondemo.dll
java -Djava.library.path=. JniRegionDemo
~~~

`System.loadLibrary("jniregiondemo")` dùng **tên logical**; JVM tìm tên file theo quy tắc hệ điều hành (như `libjniregiondemo.so`, `libjniregiondemo.dylib`, `jniregiondemo.dll`). Nếu không tìm thấy thư viện hoặc binary không khớp ABI, bạn có thể gặp `UnsatisfiedLinkError` trước khi chương trình in output. Trên Windows, lệnh `cl` cần được chạy trong môi trường đã cấu hình MSVC compiler. Nếu project có package Java khác default package, dùng đúng JNI header mới và tên lookup tương ứng.

### 6.5. Output chính xác khi biên dịch và nạp thành công

~~~text
part=[20, 30, 40]
numbers=[10, 20, 99, 99, 50, 60]
partAfterWrite=[20, 30, 40]
empty=[]
bounds=ArrayIndexOutOfBoundsException
~~~

Giải thích theo thứ tự:

- `part` lấy `numbers[1..3]`, nên là `[20, 30, 40]`.
- `fillRegion(numbers, 2, 2, 99)` thay `numbers[2]` và `numbers[3]` bằng 99. `numbers[4]` và `numbers[5]` không đổi.
- `part` được tạo bởi `NewIntArray` rồi copy bằng region API: sửa `numbers` không thay đổi `part`.
- Vùng rỗng `start = numbers.length`, `length = 0` trả mảng mới độ dài 0.
- `start=5`, `len=2` trên mảng độ dài 6 bị từ chối bởi `valid_range` nên Java bắt được `ArrayIndexOutOfBoundsException`.

Điểm cần phân biệt: chương trình này **chủ động ném ngoại lệ từ JNI helper** nếu bounds sai. Bản thân các hàm `Get/Set<Type>ArrayRegion` cũng quy định ngoại lệ `ArrayIndexOutOfBoundsException` cho vùng không hợp lệ; kiểm tra trước nhằm tránh gọi API khi dữ liệu đầu vào đã sai và giúp mã giải thích rõ điều kiện.

## 7. Khi nào cần cấp phát buffer và quản lý dung lượng?

Trong ví dụ, `jint buffer[8]` cố định nên không có nguy cơ dùng buffer nhỏ hơn `batch`, vì `batch <= BLOCK_SIZE`. Trường hợp muốn copy toàn bộ `len` phần tử một lần với `malloc`, phải kiểm tra kích thước trước:

~~~c
/* Đoạn minh họa: giả định len > 0, vùng Java đã hợp lệ. */
if ((size_t)len > SIZE_MAX / sizeof(jint)) {
    /* Không thể biểu diễn số byte cần cấp phát. */
    return;
}

jint *buffer = malloc((size_t)len * sizeof(jint));
if (buffer == NULL) {
    /* Báo lỗi và return; không truyền NULL vào region API. */
    return;
}

/* Sao chép, kiểm tra lỗi, rồi free(buffer) ở mọi nhánh. */
free(buffer);
~~~

Đoạn trên **không phải native function độc lập**: cần `#include <stdint.h>` (cho `SIZE_MAX`), `#include <stdlib.h>` (cho `malloc`/`free`) và cơ chế báo lỗi Java thích hợp. Đoạn code là minh họa các điểm cần kiểm tra trước khi cấp phát.

Với `len` nhỏ, stack buffer đơn giản. Với `len` lớn, buffer cấp phát động có thể tiêu thụ nhiều RAM; một buffer cố định copy theo chunk thường dễ kiểm soát hơn. Dù dùng cách nào, không truyền `buf` không đủ chỗ: vì native pointer không mang thông tin capacity, JVM không thể tự bảo vệ ứng dụng khỏi mọi lỗi tràn bộ nhớ C.

### Sao chép không mặc nhiên atomic

Hàm `GetIntArrayRegion` không định nghĩa một transaction hoặc một snapshot được đồng bộ hóa giữa các thread. Nếu thread Java khác sửa cùng mảng trong lúc native code copy nhiều chunk, các phần có thể phản ánh thời điểm khác nhau. Với `SetIntArrayRegion`, thread khác cũng có thể quan sát mảng đang được cập nhật từng đoạn. Khi cần nhất quán liên luồng, phải có cơ chế đồng bộ hóa ở tầng ứng dụng: khóa, snapshot đã tạo trước, hoặc thiết kế ownership sao cho không có writer cạnh tranh.

## 8. So sánh với GetArrayElements/ReleaseArrayElements

Đây là hai mô hình quản lý khác nhau:

| Tiêu chí | `Get/Set<Type>ArrayRegion` | `Get/Release<Type>ArrayElements` |
|---|---|---|
| Dữ liệu cần thao tác | Một đoạn `start,len`; cũng có thể copy toàn bộ | Truy cập phần tử của mảng theo một pointer trả về |
| Buffer từ đâu? | **Caller cung cấp**; JVM copy dữ liệu vào/ra | JVM trả pointer, có thể là **copy hoặc vùng được pin** |
| Có cần Release? | **Không có Release...ArrayRegion** | **Bắt buộc Release** với pointer thành công |
| Copy hai chiều | `Get` để đọc, `Set` để ghi | Thay đổi trên pointer; `Release` tùy mode để copy back/giải phóng |
| Giữ pointer lâu? | Chỉ là buffer native do bạn quản lý | Tuân thủ hợp đồng Release; không giữ sau Release |
| Dùng cho một đoạn nhỏ | Rõ ràng, không cần giữ cả mảng | Có thể dư thừa nếu chỉ cần vài phần tử |
| Hạn chế | Copy dữ liệu, call overhead nếu quá nhiều chunk nhỏ | Phải xử lý copy/pin, release mode, lifetime và GC ảnh hưởng |

Khi dùng `GetIntArrayElements`:

~~~c
jboolean is_copy;
jint *elements = (*env)->GetIntArrayElements(env, array, &is_copy);
if (elements == NULL) {
    return; /* Có thể có lỗi cấp phát hoặc exception. */
}

/* Đọc/ghi elements[index] trong giới hạn độ dài mảng. */

(*env)->ReleaseIntArrayElements(env, array, elements, 0);
~~~

Đây là **mảnh JNI C minh họa** trong native method trả `void`, giả định `array` hợp lệ. `is_copy == JNI_FALSE` cho biết JVM có thể cho phép truy cập mảng trực tiếp thay vì tạo bản copy, nhưng không thể suy ra điều này trước khi gọi. Khi `elements` đã được lấy thành công, cần Release đúng quy tắc; mode `0` thường dùng để copy back (nếu là copy) và giải phóng buffer tương ứng. `JNI_ABORT` bỏ qua việc copy back của một bản sao, `JNI_COMMIT` copy back nhưng có thể chưa giải phóng buffer copy.

**`GetPrimitiveArrayCritical` khác nữa:** nó có các hạn chế đặc biệt, như không được chặn thread hoặc gọi JNI tùy tiện khi đang ở critical region. Không sử dụng nó chỉ vì muốn sao chép vài phần tử; region API sẽ dễ hiểu và an toàn hơn cho tác vụ đó.

Không khẳng định `Get/Set<Type>ArrayRegion` luôn nhanh hơn hay chậm hơn `Get/Release<Type>ArrayElements`. Hiệu năng phụ thuộc JVM, kích thước, số lần gọi và cách quản lý bộ nhớ. Với tác vụ chỉ cần một đoạn nhỏ, bắt đầu bằng region API; benchmark trong môi trường thực tế nếu hiệu năng là yêu cầu quan trọng.

## 9. Điểm khác biệt theo kiểu dữ liệu

### `byte[]` và file/network data

`GetByteArrayRegion` copy từng `jbyte`, nhưng `byte` Java là signed từ -128 đến 127. Nếu C muốn hiển thị byte thành 0–255, hãy chủ động diễn giải dưới dạng unsigned khi cần; không coi `jbyte` là mã ký tự.

~~~c
jbyte header[4];

(*env)->GetByteArrayRegion(env, data, 0, 4, header);
if ((*env)->ExceptionCheck(env)) {
    return;
}

/* header chứa bốn giá trị jbyte; không chứa dấu kết thúc chuỗi '\0'. */
~~~

Đây là mảnh code JNI của một hàm trả `void`, đã bảo đảm `data` là `jbyteArray` chứa ít nhất bốn phần tử. Không dùng `strlen` trên buffer byte thô; dữ liệu nhị phân có thể chứa `0` ở bất cứ vị trí nào.

### `char[]` không phải chuỗi C/UTF-8

`jchar` là một UTF-16 code unit, không nhất thiết là một Unicode code point đầy đủ (có thể là một nửa surrogate pair). Dùng `GetCharArrayRegion` với `jchar[]` nếu đang thao tác đúng Java `char[]`. Không ép `jchar*` thành `char*` rồi coi là UTF-8 hay chuỗi C kết thúc bằng byte NUL.

### `boolean[]`

JNI `jboolean` thường được biểu diễn bằng phần tử 8-bit và dùng giá trị logic `JNI_FALSE` (0) / `JNI_TRUE` (1). Nếu tạo buffer để ghi sang `boolean[]`, hãy dùng các hằng JNI đó thay vì giả định mọi giá trị byte phi 0 đều được chuẩn hóa theo cách bạn mong đợi.

### `long[]`, `float[]`, `double[]`

Dùng `jlong`, `jfloat`, `jdouble`; không dùng tùy tiện C `long` hoặc `double` vì “có vẻ cùng tên”. JNI định nghĩa mapping giữa Java primitive và native type cụ thể. `len` vẫn tính theo **phần tử**; ví dụ `SetDoubleArrayRegion(array, 3, 2, buffer)` ghi hai số `double` vào index 3 và 4.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi `GetArrayRegion` theo đúng tên đó | Không có hàm JNI cụ thể tương ứng | Dùng `GetIntArrayRegion`, `GetByteArrayRegion`… theo kiểu |
| Nhầm `len` với index kết thúc | Copy thừa hoặc vượt bounds | Mô tả vùng `[start, start+len)` |
| Nhầm phần tử với byte | Cấp phát buffer thiếu, đọc/ghi sai | Buffer có ít nhất `len * sizeof(NativeType)` byte |
| `start + len` gây overflow signed | Kiểm tra bounds sai | Dùng `start > n || len > n-start` sau khi loại số âm |
| Gọi region với `array == NULL` | Vi phạm precondition JNI, có thể crash | Kiểm tra `NULL` trước rồi throw `NullPointerException` |
| Dùng `buf == NULL` hoặc buffer không đủ | Truy cập native memory không hợp lệ | Bảo đảm pointer hợp lệ và capacity phù hợp |
| Bỏ qua exception vì hàm trả `void` | Native code tiếp tục trong trạng thái JNI lỗi | `ExceptionCheck` và return/cleanup |
| Sửa buffer sau `Get` nhưng mong Java đổi | Java array chưa được copy back | Gọi `Set<Type>ArrayRegion` khi có ý định ghi |
| Tìm `ReleaseIntArrayRegion` | JNI không có API Release đó | Tự quản lý buffer native; chỉ ArrayElements cần Release |
| Dùng `GetObjectArrayRegion` | Không có họ region cho `Object[]` | Dùng `GetObjectArrayElement`/`SetObjectArrayElement` |
| Dùng một buffer ngắn cho `len` dài | Tràn stack/native heap, có thể crash JVM | Kiểm tra độ dài hoặc chia chunk |
| Ghi nhiều chunk và cho rằng atomic | Thread khác có thể thấy dữ liệu cập nhật dở | Đồng bộ hóa ở tầng ứng dụng |
| Copy in-place giữa hai vùng chồng lấn bằng loop tiến | Các chunk sau có thể đọc dữ liệu vừa bị ghi | Dùng snapshot trung gian hoặc thuật toán xử lý overlap rõ ràng |

### Cẩn thận khi copy giữa hai vùng chồng lấn

Nếu đọc toàn bộ `source[start..start+len)` vào một native buffer đủ lớn **trước khi Set**, việc `Set` ghi vào vùng khác của cùng Java array có thể dựa trên bản sao nguyên thủy và tránh tự ghi đè nguồn của chính lần copy đó.

Trái lại, thuật toán `Get` một chunk rồi `Set` ngay chunk ấy, sau đó lặp tiến từ trái sang phải, **không tương đương `memmove`** khi source và destination là cùng một array và hai vùng chồng lấn theo hướng có nguy cơ ghi lên phần chưa đọc. Ví dụ copy `[1,2,3,4]` sang vùng bắt đầu sau đó một index bằng loop tiến dễ làm mất phần tử cần đọc. Muốn hỗ trợ overlap, hãy chọn hướng copy thích hợp hoặc đọc snapshot độc lập trước khi ghi. Ví dụ runnable trong bài tạo **mảng đích mới** nên không gặp vấn đề aliasing này.

## 11. Ngoại lệ JNI, cleanup và vòng đời

`Get<Type>ArrayRegion`/`Set<Type>ArrayRegion` trả `void` nên lỗi bounds được biểu diễn bằng **Java exception pending**, chẳng hạn `ArrayIndexOutOfBoundsException`. Khi phát hiện exception:

1. Dừng xử lý kết quả của region call vừa thất bại; không tin rằng native buffer đã có toàn bộ dữ liệu mong muốn.
2. Giữ nguyên Java exception để Java caller nhận được, trừ khi bạn thực sự có quy trình xử lý/thay thế lỗi.
3. Nếu đã cấp phát buffer bằng `malloc`, giải phóng nó bằng `free` trước khi return. Nếu đã tạo global references, xử lý lifecycle theo ownership. Các thao tác JNI dọn local reference được JNI cho phép khi exception pending có thể được gọi.
4. Không tiếp tục gọi các JNI function tùy ý khi exception còn pending; dùng `ExceptionCheck` để kiểm tra, `ExceptionClear` chỉ khi bạn chủ động xử lý ngoại lệ.

Nếu lỗi phát sinh sau khi `Set` ghi được một số chunk, mảng Java **có thể đã thay đổi một phần**. Điều này khác với việc ném exception trước mọi thao tác nhờ prevalidation. Nếu tác vụ bắt buộc all-or-nothing, thiết kế bước tính toán vào buffer/mảng mới rồi commit theo cơ chế có kiểm soát; không giả định chuỗi lời gọi JNI là transaction.

Reference tới Java array, ví dụ `jintArray`, là JNI object reference. Buffer `jint*` ở stack/heap C là vùng nhớ native khác. Không cache `JNIEnv*` sang thread khác, không giữ pointer stack sau khi native call kết thúc; khi callback JNI khác thao tác cùng Java array, cần đặt quy ước đồng bộ.

## 12. Bài tập có đáp án

**Bài 1 — dự đoán bản sao.** Java có `int[] a = {1, 2, 3, 4, 5};`. JNI gọi `GetIntArrayRegion(a, 1, 3, buf)`. Buffer thu được gì? **`{2, 3, 4}`**, vì bắt đầu ở index 1 và copy ba phần tử.

**Bài 2 — tác dụng của ghi.** Với chính mảng ở trên và `jint patch[2] = {8, 9};`, gọi `SetIntArrayRegion(a, 2, 2, patch)`. Mảng trở thành **`{1, 2, 8, 9, 5}`**. Những index ngoài 2–3 giữ giá trị cũ.

**Bài 3 — kiểm tra tràn.** Mảng dài 6; `start = 5`, `len = 2`. Điều kiện `len > n - start` tương đương `2 > 1`, nên vùng không hợp lệ. Trong ví dụ runnable, helper tạo `ArrayIndexOutOfBoundsException` trước khi copy.

**Bài 4 — chỉ một phần mảng byte.** Một `byte[]` dài 1000 byte nhưng native chỉ cần header 12 byte bắt đầu ở index 4. Nên dùng `GetByteArrayRegion(array, 4, 12, header)` với `jbyte header[12]` đã có dung lượng, thay vì lấy pointer toàn bộ mảng rồi quên `ReleaseByteArrayElements`.

**Bài 5 — vòng đời.** Nếu hàm C tạo `jint buffer[8]`, `GetIntArrayRegion` thành công rồi return, Java array có bị mất không? **Không**. Buffer native hết hiệu lực khi C return, còn Java array do JVM quản lý; data copy không trao quyền sở hữu Java object cho mã C.

**Bài 6 — mảng object.** Một `String[]` cần cập nhật phần tử thứ 3. Có thể dùng `SetStringArrayRegion` không? **Không.** JNI dùng `SetObjectArrayElement` với một `jstring` hợp lệ và index được kiểm tra; `String[]` không thuộc họ primitive arrays.

## Tài liệu tham chiếu

- [Oracle Java SE 17 JNI Function Specification — Get/Set<PrimitiveType>ArrayRegion](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivetypearrayregion-routines).
- [Oracle Java SE 17 JNI Functions — GetArrayLength, Get/Release<PrimitiveType>ArrayElements, critical access](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Oracle Java SE 17 JNI Types — primitive types, jarray và jsize](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html).

## Ghi nhớ

- **`Get<Type>ArrayRegion` = Java array → native buffer; `Set<Type>ArrayRegion` = native buffer → Java array.** Hai API này copy một đoạn mảng nguyên thủy và **không có cặp Release**.
- `start` là index, `len` là số phần tử; kiểm tra vùng an toàn bằng `start >= 0`, `len >= 0`, `start <= n` và `len <= n-start`.
- Buffer C phải có đủ chỗ, kiểu JNI phải khớp chính xác với kiểu mảng Java, và mọi exception pending cần được xử lý đúng.
- Với vùng nhỏ hoặc copy theo chunk, region API rất rõ ràng; với pointer từ `Get<Type>ArrayElements`, phải dùng `Release<Type>ArrayElements` theo hợp đồng riêng.
- Copy vùng không tạo lock, transaction hay bản sao atomic qua các thread. Nếu cần nhất quán, hãy thiết kế đồng bộ hóa và ownership rõ ràng.
