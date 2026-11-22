# Đi theo cặp GetStringChars hoặc GetStringUTFChars với hàm Release tương ứng trong JNI

Khi một phương thức native nhận `jstring` từ Java, C không thể coi `jstring` là `char *` hoặc `wchar_t *` để đọc trực tiếp. `jstring` là một **tham chiếu JNI tới đối tượng `java.lang.String`**. Để đọc các đơn vị ký tự hoặc các byte mã hóa, native code phải gọi API JNI phù hợp. Hai cặp cơ bản là:

- **`GetStringChars(env, text, ...)` → `ReleaseStringChars(env, text, chars)`:** lấy chuỗi dưới dạng các **đơn vị mã UTF-16 (`jchar`)**.
- **`GetStringUTFChars(env, text, ...)` → `ReleaseStringUTFChars(env, text, utf)`:** lấy biểu diễn byte **modified UTF-8 (`const char *`)** của chuỗi.

**Quy tắc không được quên:** Sau khi `Get...` thành công và trả về con trỏ khác `NULL`, phải gọi **đúng `Release...` của cùng loại**, truyền lại **đúng `jstring` gốc và con trỏ đã nhận**. Mỗi lần lấy thành công tạo một lần cần giải phóng tương ứng. Kết thúc hàm native không phải là sự thay thế đáng tin cậy cho `Release`, kể cả khi JNI local reference được dọn khi return.

Bài học này giải thích vì sao có quy tắc trên, điều gì xảy ra khi quên/mismatch `Release`, khác biệt UTF-16 với modified UTF-8, cách xử lý nhánh lỗi và một chương trình Java 17+ / JNI C có thể biên dịch để kiểm chứng.

## 1. `jstring`, vùng ký tự và ba lớp vòng đời

Nhìn vào lời khai báo Java:

```java
private static native int[] inspect(String text);
```

JNI header sinh từ `javac -h` sẽ có tham số C kiểu `jstring` cho `text`. Đó là **handle do JVM quản lý**, không mang nghĩa con trỏ tới byte UTF-8. Sau đây là ba lớp tài nguyên phải phân biệt:

| Tài nguyên | Ai quản lý? | Khi nào sử dụng được? | Giải phóng bằng gì? |
| --- | --- | --- | --- |
| Đối tượng Java `String` | JVM/GC | Khi còn tham chiếu hợp lệ | Không `free` đối tượng; quản lý JNI local/global references theo quy tắc JNI |
| `const jchar *` được trả từ `GetStringChars` | JVM quản lý lease/truy cập tới ký tự | Từ `GetStringChars` thành công đến `ReleaseStringChars` | **`ReleaseStringChars(env, sameString, samePointer)`** |
| `const char *` được trả từ `GetStringUTFChars` | JVM quản lý lease/biểu diễn modified UTF-8 | Từ `GetStringUTFChars` thành công đến `ReleaseStringUTFChars` | **`ReleaseStringUTFChars(env, sameString, samePointer)`** |

JVM có thể **sao chép dữ liệu**, **pin vùng nhớ**, hoặc tạo một biểu diễn trung gian phù hợp với encoding được yêu cầu. JNI không bắt ứng dụng hiểu implementation đó. `Release` thông báo rằng native code **không dùng vùng ký tự này nữa**, giúp JVM thu hồi bản sao hoặc bỏ giới hạn giữ vùng nhớ. Không phụ thuộc vào một chiến lược GC/JVM cụ thể.

`GetStringChars` trả `const jchar *`; `GetStringUTFChars` trả `const char *`. Từ khóa `const` là một phần của hợp đồng: không sửa nội dung thông qua con trỏ đó. Java `String` có tính bất biến; muốn chuyển đổi chuỗi, hãy tạo bộ đệm riêng rồi xây một `jstring` mới.

**Không nhầm `ReleaseStringChars` với `DeleteLocalRef`:** `DeleteLocalRef` chỉ giải phóng một **JNI reference**; nó không thay thế việc kết thúc quyền truy cập/bản sao mà `GetStringChars` đã cấp. Tương tự, `free(chars)` hay `delete[] chars` là sai: JVM cấp con trỏ, mã C không sở hữu vùng cấp phát đó.

## 2. Hai cặp API và ý nghĩa của tham số

### Cặp UTF-16

```c
const jchar *GetStringChars(
        JNIEnv *env, jstring string, jboolean *isCopy);

void ReleaseStringChars(
        JNIEnv *env, jstring string, const jchar *chars);
```

Giá trị trả về là dãy **`jchar` 16 bit**, tương ứng các đơn vị mã UTF-16 của Java `String`. `GetStringLength(env, string)` cho **số đơn vị mã**, giống `String.length()` của Java, chứ không phải nhất thiết là số Unicode code point.

- `jchar` là kiểu JNI không dấu 16 bit, không đồng nhất với `char` C 8 bit.
- Trên nhiều hệ Linux, `wchar_t` thường 32 bit; **không** ép `const jchar *` thành `const wchar_t *` rồi gọi `wcslen`.
- Không được giả định có ký tự kết thúc `0` sau phần dữ liệu dài `GetStringLength`; ngay bên trong Java `String` cũng có thể chứa U+0000 hợp lệ.
- Một ký tự Unicode ngoài BMP (ví dụ U+1F603, 😃) chiếm **hai `jchar`** tạo thành cặp surrogate; `GetStringLength` tính là 2.

Ví dụ công thức xử lý vùng:

```c
/* Đoạn minh họa trong hàm JNI có env và jstring text hợp lệ. */
jsize count = (*env)->GetStringLength(env, text);
const jchar *units = (*env)->GetStringChars(env, text, NULL);
if (units == NULL) {
    return; /* ví dụ chỉ phù hợp trong native function trả void */
}

for (jsize i = 0; i < count; ++i) {
    /* Chỉ đọc units[i] trong khoảng 0 .. count - 1. */
    /* Phép xử lý chỉ dùng C thông thường, không sửa units. */
}

(*env)->ReleaseStringChars(env, text, units);
```

`NULL` ở tham số `isCopy` nghĩa là “không cần biết JVM có tạo bản sao hay không”; **không** đồng nghĩa với bỏ qua giải phóng. Nếu hàm `GetStringChars` thất bại và trả `NULL`, không gọi `ReleaseStringChars` với con trỏ `NULL` chưa từng được cấp. Cần xử lý trạng thái lỗi/ngoại lệ theo contract JNI.

### Cặp modified UTF-8

```c
const char *GetStringUTFChars(
        JNIEnv *env, jstring string, jboolean *isCopy);

void ReleaseStringUTFChars(
        JNIEnv *env, jstring string, const char *utf);
```

Đây là biểu diễn **modified UTF-8 của JNI**, không nhất thiết giống UTF-8 chuẩn dùng trong file, JSON, HTTP hoặc thư viện C bên ngoài. Điểm quan trọng:

1. U+0000 được mã hóa bằng **hai byte `C0 80`** thay vì byte `00` như UTF-8 chuẩn.
2. Mỗi UTF-16 surrogate code unit được mã hóa riêng theo dạng 3 byte. Một supplementary code point như 😃 do hai surrogate tạo nên sẽ chiếm **6 byte** trong modified UTF-8, trong khi UTF-8 chuẩn của code point này chiếm 4 byte.
3. Các ký tự ASCII U+0001 tới U+007F được biểu diễn bằng một byte tương ứng.
4. Độ dài byte có thể khác `String.length()`; dùng `GetStringUTFLength` trên JDK 17 với giới hạn của kiểu `jsize`, hoặc `GetStringUTFLengthAsLong` trên JDK 24+ khi cần tính đúng byte count cho chuỗi cực lớn.
5. Đặc tả JNI không yêu cầu mọi con trỏ/buffer string trả về từ các API này đều **NUL-terminated**. Viết code portable bằng **độ dài đã biết**, không dùng `strlen`/`printf("%s")` vô điều kiện trên con trỏ lấy từ JNI.

Ví dụ đọc một vùng modified UTF-8:

```c
/* Đoạn minh họa trong hàm JNI, chuỗi ngắn và text hợp lệ. */
jsize byteCount = (*env)->GetStringUTFLength(env, text);
const char *bytes = (*env)->GetStringUTFChars(env, text, NULL);
if (bytes == NULL) {
    return; /* chỉ phù hợp với native function trả void */
}

for (jsize i = 0; i < byteCount; ++i) {
    unsigned char byteValue = (unsigned char)bytes[i];
    /* Dùng byteValue theo giao thức modified UTF-8 của JNI. */
}

(*env)->ReleaseStringUTFChars(env, text, bytes);
```

Không được truyền `bytes` như thể đó là UTF-8 chuẩn để lưu vào file hoặc API ngoài nếu dữ liệu có thể chứa U+0000/supplementary code point. Muốn **UTF-8 chuẩn**, có thể chuyển từ Java bằng `String.getBytes(StandardCharsets.UTF_8)` rồi trao đổi `byte[]` với native, hoặc dùng bộ chuyển mã Unicode đúng chuẩn ở phía C.

## 3. Ghép đúng: bảng cặp, kiểu và lỗi khi tráo

| Lấy dữ liệu | Kiểu con trỏ | Cách lấy độ dài | Release bắt buộc | Không được dùng |
| --- | --- | --- | --- | --- |
| `GetStringChars` | `const jchar *` | `GetStringLength` tính theo UTF-16 units | `ReleaseStringChars` | `ReleaseStringUTFChars` |
| `GetStringUTFChars` | `const char *` | `GetStringUTFLength` (JDK 17) hoặc `GetStringUTFLengthAsLong` (JDK 24+) tính theo modified UTF-8 bytes | `ReleaseStringUTFChars` | `ReleaseStringChars` |
| `GetStringCritical` | `const jchar *` | `GetStringLength` | `ReleaseStringCritical` | Các `Release` của hai cặp trên |
| `GetStringRegion` | Ghi vào **buffer do caller cấp** | Số UTF-16 units cần sao chép | **Không có** `ReleaseStringRegion` | Tự gọi `ReleaseStringChars` cho buffer |
| `GetStringUTFRegion` | Ghi modified UTF-8 vào **buffer do caller cấp** | Đủ byte capacity cho vùng đã yêu cầu | **Không có** `ReleaseStringUTFRegion` | Tự gọi `ReleaseStringUTFChars` cho buffer |

Tên `Get...` và `Release...` phải **đối xứng**, còn tham số `string` phải là cùng một đối tượng chuỗi đã dùng khi Get. Chẳng hạn:

```c
/* ĐÚNG: GetStringChars -> ReleaseStringChars */
const jchar *a = (*env)->GetStringChars(env, text, NULL);
if (a != NULL) {
    /* ... */
    (*env)->ReleaseStringChars(env, text, a);
}

/* ĐÚNG: GetStringUTFChars -> ReleaseStringUTFChars */
const char *b = (*env)->GetStringUTFChars(env, text, NULL);
if (b != NULL) {
    /* ... */
    (*env)->ReleaseStringUTFChars(env, text, b);
}

/* SAI (không được thực thi):
 * (*env)->ReleaseStringUTFChars(env, text, (const char *)a);
 * free((void *)a);
 * (*env)->ReleaseStringChars(env, anotherString, a);
 */
```

Tráo cặp khiến JVM nhận một con trỏ và kiểu dữ liệu **không phù hợp với resource lease** mà nó đã cấp. Hậu quả không chỉ là rò rỉ: có thể hỏng bộ nhớ native hoặc crash tiến trình. Việc ép kiểu C để “qua được compiler” không biến hành vi đó thành hợp lệ.

### Cùng một `jstring` có thể lấy hai lần không?

Có thể, nhưng **mỗi lần Get thành công phải có Release tương ứng**. Ví dụ lấy UTF-16 trước để phân tích code units, Release xong rồi mới lấy modified UTF-8 để phân tích bytes:

```text
jstring text
  │
  ├── GetStringChars ──> const jchar* u16 ──> đọc ──> ReleaseStringChars(text,u16)
  │
  └── GetStringUTFChars ──> const char* m8 ──> đọc ──> ReleaseStringUTFChars(text,m8)
```

Cách làm tuần tự này giảm thời gian giữ tài nguyên và giúp quản lý nhánh lỗi. Nếu cố ý giữ đồng thời nhiều lease, vẫn phải gọi `Release` cho **từng** con trỏ; tránh nhầm giữa hai tên pointer.

## 4. `isCopy` là thông tin, không phải quyền bỏ qua Release

`GetStringChars`/`GetStringUTFChars` nhận tham số thứ ba `jboolean *isCopy` (hoặc `NULL`). Khi truyền địa chỉ biến `jboolean`, JVM cho biết liệu nó đã tạo bản sao tại thời điểm lấy dữ liệu hay không:

```c
jboolean isCopy = JNI_FALSE;
const jchar *units = (*env)->GetStringChars(env, text, &isCopy);
if (units == NULL) {
    return; /* chỉ ví dụ cho JNI native method trả void */
}

/* JNI_TRUE: JVM đã tạo copy; JNI_FALSE: không tạo copy.
 * Cả hai trường hợp đều cần ReleaseStringChars.
 */
(*env)->ReleaseStringChars(env, text, units);
```

Bảng quyết định:

| Giá trị `isCopy` sau Get thành công | Điều có thể hiểu | Có gọi Release không? |
| --- | --- | --- |
| `JNI_TRUE` | JVM cho dữ liệu qua bản sao | **Có** |
| `JNI_FALSE` | JVM không báo cấp bản sao | **Có** |
| Không yêu cầu thông tin (`NULL`) | Ứng dụng không biết chiến lược JVM | **Có** |

Đừng suy từ `JNI_FALSE` rằng bộ nhớ sẽ “tự sống mãi” hoặc có thể lưu pointer sau `Release`. Đừng dùng `isCopy` để chọn `free` hay `DeleteLocalRef`. Các quyết định đó thuộc về hợp đồng JNI, không thuộc loại implementation của string.

## 5. Thời gian giữ pointer và nhánh lỗi

Một hàm native có thể có nhiều điểm trả về: đầu vào `null`, Get thất bại, logic xử lý lỗi, tạo Java object thất bại hoặc Java exception đang pending. Nếu một nhánh rời khỏi hàm sau `GetStringChars` thành công **mà chưa Release**, đó là lỗi quản lý tài nguyên.

### Mẫu xử lý hai lease tuần tự

```c
/* Đoạn minh họa cho native function trả jint; text hợp lệ.
 * Trả -1 nếu không còn dữ liệu để đọc; nếu JNI Get lỗi, trả 0
 * để thoát trong lúc lỗi/exception được caller xử lý theo contract.
 */
static jint read_two_forms(JNIEnv *env, jstring text) {
    jsize unitsCount = (*env)->GetStringLength(env, text);
    if (unitsCount == 0) {
        return -1;
    }

    const jchar *units = (*env)->GetStringChars(env, text, NULL);
    if (units == NULL) {
        return 0;
    }

    jint firstUnit = (jint)units[0];
    (*env)->ReleaseStringChars(env, text, units);

    const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        return 0;
    }

    /* Chỉ truy cập byte 0 vì string có ít nhất một đơn vị mã. */
    jint firstByte = (jint)(unsigned char)utf[0];
    (*env)->ReleaseStringUTFChars(env, text, utf);

    return firstUnit + firstByte;
}
```

Mã trên là **helper minh họa**, chưa phải một exported JNI entry point. Việc trả `0` khi Get lỗi chỉ có nghĩa là helper dừng; nó không thay thế cơ chế báo lỗi. `Get...` có thể trả `NULL` trong tình trạng lỗi JNI/thiếu bộ nhớ; mã gọi ở tầng cao phải có contract xử lý `NULL` và pending exception. Đối với API native có kiểu trả về `jobject`, có thể trả `NULL` để Java exception đang pending được truyền về Java.

### Khi có nhiều tài nguyên, dùng `cleanup` nhất quán

```c
/* Pseudocode C: không phải một chương trình độc lập. */
const jchar *units = NULL;
const char *utf = NULL;

/* ... lấy units khi cần ... */
/* ... lấy utf khi cần ... */

cleanup:
if (utf != NULL) {
    (*env)->ReleaseStringUTFChars(env, text, utf);
}
if (units != NULL) {
    (*env)->ReleaseStringChars(env, text, units);
}
/* Sau cleanup mới xử lý phần còn lại theo contract. */
```

Trong code thực tế, chỉ gán con trỏ sau khi Get thành công và bảo đảm mọi `goto cleanup` giữ thông tin chính xác. Đừng Release con trỏ chưa được cấp hoặc Release hai lần.

**Ngoại lệ JNI:** Không có gì bảo đảm thao tác native tiếp tục “bình thường” khi Java exception đang pending. Nếu cần thoát ra Java, hãy dọn những tài nguyên đã mượn trước khi return; các hàm Release string là nhóm thao tác được phép sử dụng để hoàn tất cleanup trong tình huống pending exception. Đừng gọi một chuỗi JNI methods không liên quan sau khi đã biết có pending exception.

## 6. Chương trình chạy được: Java 17+ và JNI C trên Linux

Ví dụ đầy đủ chứng minh:

1. `GetStringChars` duyệt các UTF-16 code units, đếm đơn vị mã bằng `0`.
2. Gọi `ReleaseStringChars` **trước khi** lấy representation khác.
3. `GetStringUTFChars` duyệt modified UTF-8 bytes, đếm cặp `C0 80`, rồi `ReleaseStringUTFChars`.
4. Một hàm khác biến các chữ ASCII thường thành hoa trên **bộ đệm riêng**, Release vùng đọc trước khi `NewString` tạo chuỗi mới.
5. Độ dài của UTF-16, modified UTF-8 và số Unicode code points khác nhau.

Các file sau đặt cùng thư mục trên **Linux**, JDK 17+ có `javac` và compiler C tương thích kiến trúc JVM. Để làm rõ giới hạn độ dài `jsize` trong bài demo, `metrics` chỉ chấp nhận tối đa 1024 UTF-16 units; xử lý file/chuỗi khổng lồ là bài toán cấp phát và phiên bản API khác.

### File 1: `JniStringLeaseDemo.java`

```java
import java.util.Arrays;

public final class JniStringLeaseDemo {
    static {
        System.loadLibrary("jnistringlease");
    }

    private static native int[] metrics(String input);
    private static native String asciiUpper(String input);

    public static void main(String[] args) {
        // a, U+0000, Ω, 😃 (một surrogate pair), z.
        String input = "a\0\u03A9\uD83D\uDE03z";

        System.out.println("javaUnits=" + input.length());
        System.out.println("codePoints="
                + input.codePointCount(0, input.length()));
        System.out.println("native=" + Arrays.toString(metrics(input)));

        String upper = asciiUpper(input);
        System.out.println("upperOk="
                + upper.equals("A\0\u03A9\uD83D\uDE03Z"));
    }
}
```

Java `String.length()` đếm UTF-16 units: `a` = 1, U+0000 = 1, `Ω` = 1, `😃` = 2, `z` = 1, tổng **6**. Số Unicode code points là **5**. `\0` trong Java string literal ở ví dụ là escape octal cho ký tự NUL; **không phải** dấu kết thúc Java String.

### File 2: `jni_string_lease_demo.c`

```c
#include "JniStringLeaseDemo.h"  /* sinh bằng javac -h */
#include <stdint.h>             /* SIZE_MAX */
#include <stdlib.h>             /* malloc, free */

static void throw_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass error_type = (*env)->FindClass(env, class_name);
    if (error_type != NULL) {
        (*env)->ThrowNew(env, error_type, message);
        (*env)->DeleteLocalRef(env, error_type);
    }
}

/*
 * Kết quả 6 số:
 * [UTF16 units, modified-UTF8 bytes, zero UTF16 units,
 *  encoded NUL count, first UTF16 unit, last UTF16 unit].
 */
JNIEXPORT jintArray JNICALL
Java_JniStringLeaseDemo_metrics(JNIEnv *env, jclass clazz,
                                jstring input) {
    (void)clazz;
    if (input == NULL) {
        throw_java(env, "java/lang/NullPointerException", "input");
        return NULL;
    }

    jsize units_count = (*env)->GetStringLength(env, input);
    if (units_count > 1024) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "demo accepts at most 1024 UTF-16 units");
        return NULL;
    }

    /* Đối với input <=1024 units, MUTF-8 tối đa 3072 bytes. */
    jsize byte_count = (*env)->GetStringUTFLength(env, input);

    /* CẶP 1: jchar * / ReleaseStringChars */
    const jchar *units = (*env)->GetStringChars(env, input, NULL);
    if (units == NULL) {
        return NULL;
    }

    jint zero_units = 0;
    jint first = units_count == 0 ? -1 : (jint)units[0];
    jint last = units_count == 0 ? -1
                                : (jint)units[units_count - 1];
    for (jsize i = 0; i < units_count; ++i) {
        if (units[i] == 0) {
            ++zero_units;
        }
    }

    (*env)->ReleaseStringChars(env, input, units);
    /* Không sử dụng 'units' sau dòng trên. */

    /* CẶP 2: char * / ReleaseStringUTFChars */
    const char *modified = (*env)->GetStringUTFChars(env, input, NULL);
    if (modified == NULL) {
        return NULL;
    }

    jint encoded_nuls = 0;
    for (jsize i = 0; i + 1 < byte_count; ++i) {
        unsigned char a = (unsigned char)modified[i];
        unsigned char b = (unsigned char)modified[i + 1];
        if (a == 0xC0 && b == 0x80) {
            ++encoded_nuls;
            ++i;  /* Bỏ qua byte thứ hai của cặp C0 80. */
        }
    }

    (*env)->ReleaseStringUTFChars(env, input, modified);
    /* Không giả định modified[byte_count] == '\0'. */

    jint values[6] = {
        (jint)units_count, (jint)byte_count,
        zero_units, encoded_nuls, first, last
    };
    jintArray output = (*env)->NewIntArray(env, 6);
    if (output == NULL) {
        return NULL;
    }

    (*env)->SetIntArrayRegion(env, output, 0, 6, values);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return output;
}

/*
 * Đổi chữ ASCII 'a'..'z' thành 'A'..'Z' nhưng giữ mọi
 * UTF-16 code unit khác, kể cả U+0000 và surrogate pair.
 */
JNIEXPORT jstring JNICALL
Java_JniStringLeaseDemo_asciiUpper(JNIEnv *env, jclass clazz,
                                   jstring input) {
    (void)clazz;
    if (input == NULL) {
        throw_java(env, "java/lang/NullPointerException", "input");
        return NULL;
    }

    jsize count = (*env)->GetStringLength(env, input);
    const jchar *units = (*env)->GetStringChars(env, input, NULL);
    if (units == NULL) {
        return NULL;
    }

    size_t length = (size_t)count;
    if (length > SIZE_MAX / sizeof(jchar)) {
        (*env)->ReleaseStringChars(env, input, units);
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native UTF-16 buffer too large");
        return NULL;
    }

    /* malloc(0) có hành vi tùy implementation: cấp ít nhất 1 ô. */
    size_t allocated = length == 0 ? 1 : length;
    jchar *buffer = (jchar *)malloc(allocated * sizeof(jchar));
    if (buffer == NULL) {
        (*env)->ReleaseStringChars(env, input, units);
        throw_java(env, "java/lang/OutOfMemoryError",
                   "cannot allocate native UTF-16 buffer");
        return NULL;
    }

    for (jsize i = 0; i < count; ++i) {
        jchar ch = units[i];
        if (ch >= (jchar)'a' && ch <= (jchar)'z') {
            ch = (jchar)(ch - (jchar)'a' + (jchar)'A');
        }
        buffer[i] = ch;
    }

    /* Từ đây buffer là bản sao do C sở hữu, không còn mượn JVM. */
    (*env)->ReleaseStringChars(env, input, units);
    jstring result = (*env)->NewString(env, buffer, count);
    free(buffer);
    return result;  /* Nếu NewString lỗi, Java exception được giữ. */
}
```

**Kiểm tra vòng đời trong ví dụ C:**

- `metrics` lấy `GetStringChars`, đọc, Release, rồi mới gọi `GetStringUTFChars`. Trên mọi đường đi thành công không có con trỏ mượn nào còn mở lúc tạo `jintArray`.
- Mỗi nhánh `Get... == NULL` trả về ngay vì chưa có lease hợp lệ cần Release. Với JNI API gọi thất bại, ứng dụng cần để lỗi/exception được xử lý bởi caller theo contract.
- `asciiUpper` có hai nhánh cấp phát lỗi; **cả hai đều Release `units` trước khi ném Java exception**. Trên nhánh thành công cũng Release trước `NewString`.
- `buffer` do `malloc` cấp nên mới `free(buffer)` được. Không bao giờ `free(units)` vì `units` do JNI quản lý.
- `NewString` nhận mảng `jchar` và **số đơn vị UTF-16 `count`**, không cần NUL terminator. Việc giữ U+0000 và surrogate pair là chủ ý.

Hàm đổi chữ trong ví dụ chỉ uppercase **ASCII**. Nó không phải thuật toán Unicode uppercase đầy đủ (quy tắc locale, các ký tự đổi thành nhiều code points, v.v.); muốn xử lý chữ hoa Unicode, ưu tiên `String.toUpperCase(Locale.ROOT)` hoặc thư viện Unicode phù hợp ở tầng Java.

### Biên dịch và chạy

Đảm bảo `JAVA_HOME` trỏ tới JDK đã cài (có `include/jni.h`), và compiler `cc` tạo library cùng kiến trúc với Java process. Các lệnh sau chạy trên Linux, trong thư mục có hai file đã nêu:

```bash
javac -encoding UTF-8 -h . JniStringLeaseDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnistringlease.so jni_string_lease_demo.c

java -Djava.library.path=. JniStringLeaseDemo
```

`javac -h .` biên dịch `JniStringLeaseDemo.class` và tạo `JniStringLeaseDemo.h` với exported C function signatures. `System.loadLibrary("jnistringlease")` tương ứng `libjnistringlease.so` trên Linux. Tùy chọn `-Djava.library.path=.` phải truyền **trước** main class để JVM tìm native library. Windows dùng `.dll` và quy trình build phù hợp; macOS dùng quy tắc native lib tương ứng.

**Stdout chính xác mong đợi khi biên dịch và nạp thành công:**

```text
javaUnits=6
codePoints=5
native=[6, 12, 1, 1, 97, 122]
upperOk=true
```

Giải thích con số `12` byte modified UTF-8:

| Thành phần | UTF-16 units | Modified UTF-8 bytes | Vì sao |
| --- | ---: | ---: | --- |
| `a` (U+0061) | 1 | 1 | ASCII |
| U+0000 | 1 | 2 | Mã đặc biệt `C0 80` |
| `Ω` (U+03A9) | 1 | 2 | Ký tự trong khoảng cần 2 byte |
| `😃` (U+1F603) | 2 | 6 | Hai surrogate, mỗi cái 3 byte |
| `z` (U+007A) | 1 | 1 | ASCII |
| **Tổng** | **6** | **12** | Khác số code points = 5 |

Vì chuỗi bắt đầu bằng `a` và kết thúc bằng `z`, code units đầu và cuối lần lượt có giá trị **97** và **122**. Có đúng một U+0000 và đúng một cặp `C0 80`. `asciiUpper` đổi `a`/`z` thành `A`/`Z`, còn U+0000, `Ω` và hai surrogate giữ nguyên, nên phép so sánh Java cho `true`.

Đoạn code này cố ý dựa vào **byte count**, không gọi `strlen(modified)` hay `printf("%s", modified)`. Đặc tả JNI nêu rằng các vùng string trả về không bắt buộc NUL-terminated; giả định terminator sẽ làm code phụ thuộc JVM hoặc đọc quá giới hạn. `GetStringUTFLength` trên JDK 17 trả byte count kiểu `jsize`; với chuỗi cực lớn, cần tránh giới hạn này. Trong JNI của JDK 24+, `GetStringUTFLengthAsLong` trả `jlong` cho độ dài modified UTF-8 đầy đủ. Ví dụ hiện tại giới hạn 1024 units nên `jsize` là đủ.

## 7. Vì sao Java `String.length()`, `strlen` và `GetStringUTFLength` không hoán đổi?

Java String là chuỗi các **đơn vị mã UTF-16**, không phải dãy byte UTF-8. Ký tự NUL U+0000 hoàn toàn hợp lệ trong Java `String` và không đánh dấu kết thúc. Ví dụ:

```java
String s = "A\0B";
System.out.println(s.length());      // 3 UTF-16 units
System.out.println(s.codePointCount(0, s.length())); // 3 code points
```

Ngược lại, `strlen` của C chỉ đếm số byte trước byte `0` **khi có C NUL terminator hợp lệ**; nó không đếm Java characters, không đếm Unicode code points và không bảo đảm an toàn trên một buffer không kết thúc bằng NUL. Với Java String chứa U+0000, JNI modified UTF-8 mã hóa nó thành `C0 80` để có biểu diễn riêng, nhưng điều đó không biến `const char *` từ JNI thành UTF-8 chuẩn.

Các đại lượng:

- `GetStringLength(env, text)`: số UTF-16 code units, kiểu `jsize`. Dùng với `const jchar *`.
- `GetStringUTFLength(env, text)`: số **modified UTF-8 bytes**, kiểu `jsize` ở JDK 17. Dùng để xác định byte count khi biết độ dài không vượt miền hỗ trợ.
- `GetStringUTFLengthAsLong(env, text)`: số modified UTF-8 bytes dưới dạng `jlong` ở **JDK 24+**, giải quyết giới hạn byte count của API cũ; **không** compile được nguyên trạng với `jni.h` từ JDK 17.
- `String.codePointCount(...)`: số Unicode code points trong vùng Java String, không trực tiếp là byte count và không phải số UTF-16 units khi có surrogate pair.

Đừng dùng `sizeof(pointer)` để suy ra dung lượng: `sizeof(chars)` chỉ là kích thước biến pointer trong C. Cũng đừng suy từ `GetStringLength` rằng bộ đệm `char *` có đúng từng ấy byte, vì modified UTF-8 có thể cần nhiều hơn một byte trên mỗi UTF-16 unit.

## 8. Mã hóa chuẩn và dữ liệu từ thư viện C bên ngoài

Nếu thư viện C nhận **UTF-8 chuẩn** (JSON, HTTP, file path protocol, HTTP request, database client...), đưa thẳng pointer của `GetStringUTFChars` vào có thể bị sai dữ liệu:

- U+0000: JNI MUTF-8 dùng `C0 80`; UTF-8 chuẩn dùng `00`.
- Supplementary characters: JNI MUTF-8 mã hóa hai surrogate riêng; UTF-8 chuẩn dùng một chuỗi 4 byte cho code point.
- Nếu thư viện C giả định chuỗi C kết thúc bằng NUL, pointer JNI chưa được bảo đảm terminator theo đặc tả. Cần bộ đệm do ứng dụng sở hữu với capacity và terminator được xây đúng.

Một cách rõ ràng khi phải truyền **UTF-8 chuẩn** từ Java:

```java
// Java 17+: chủ động mã hóa standard UTF-8 và truyền byte[].
byte[] bytes = value.getBytes(java.nio.charset.StandardCharsets.UTF_8);
sendUtf8Bytes(bytes); // native method riêng nhận jbyteArray
```

Đoạn trên là **minh họa**, chưa định nghĩa `sendUtf8Bytes`. Native `jbyteArray` có chiều dài riêng qua `GetArrayLength`; không được đo bằng `strlen` vì UTF-8 chuẩn của Java String chứa U+0000 có thể mang byte `00`. Ở phía C, nếu thư viện đòi C string, phải nêu rõ chính sách với embedded NUL và cấp thêm byte terminator khi hợp lệ. Đối với dữ liệu nhị phân/network, tốt nhất dùng cặp **pointer + length**.

Khi chiều ngược lại, `NewStringUTF(env, cBytes)` mong đợi **modified UTF-8**, không phải một bộ đệm UTF-8 chuẩn bất kỳ. Trong dữ liệu thật có emoji hoặc ký tự NUL, không giả định hai mã hóa hoán đổi. Với đầu vào Unicode từ thư viện ngoài, hãy decode chuẩn sang các `jchar` UTF-16 rồi gọi `NewString(env, chars, count)`, hoặc dùng cầu nối `byte[]` và decode rõ ràng tại Java.

## 9. Ngoại lệ, null, local reference và thread safety

### Kiểm tra null input trước khi gọi Get

Đặc tả JNI yêu cầu `jstring string` hợp lệ, không phải `NULL`, cho các API Get string. Phía Java có thể truyền `null`; native code phải chọn policy (ví dụ ném `NullPointerException`) **trước** khi gọi `GetStringChars`/`GetStringUTFChars`. Ví dụ runnable làm việc này bằng `FindClass("java/lang/NullPointerException")` và `ThrowNew`.

### Get có thể thất bại

Nếu `GetStringChars` hoặc `GetStringUTFChars` trả `NULL`, không được dereference. Có thể có lỗi cấp phát/exception pending; không chạy tiếp code xử lý ký tự, và không gọi Release cho pointer chưa có. Nếu hàm trả reference về Java, return `NULL` khi exception pending là mô hình phổ biến. Trong mã thư viện cần contract rõ cho trường hợp JVM chỉ trả `NULL` mà chưa đặt exception (đặc tả không buộc mọi lỗi Get đều đồng thời ném Java exception); khi cần, báo một lỗi Java phù hợp sau khi xác định chưa có pending exception.

### Java exception sau Get thành công

Nếu sau khi mượn vùng ký tự, mã C còn làm nhiều thao tác JNI có thể ném exception, một đường lỗi rất dễ bỏ sót Release. Nên hạn chế các JNI calls trong thời gian giữ pointer, chuyển dữ liệu cần thiết sang buffer native riêng, Release sớm, rồi mới thực hiện thao tác như `NewString`, `NewIntArray`, `CallObjectMethod`. Nếu có pending exception, ưu tiên cleanup (Release các vùng mượn, dọn local refs được phép) rồi trả control về Java.

### Local/global refs không thay thế Release

`jstring text` của một native method thường là local JNI reference hợp lệ trong thời gian gọi. Khi return, local refs có thể được dọn tự động, nhưng **đó không đồng nghĩa JVM tự giải phóng đúng mọi access lease**. Nếu cần giữ `jstring` lâu hơn một native call, tạo global reference `NewGlobalRef` theo lifecycle được thiết kế và `DeleteGlobalRef` về sau; vẫn phải Release mỗi vùng ký tự đã Get. Không truyền `JNIEnv *` hoặc local `jstring` sang thread khác để dùng sau return: native thread cần được attach theo JNI và nhận `JNIEnv *` của chính thread.

### Không giữ pointer sau Release

Đây là **use-after-release**:

```c
const jchar *p = (*env)->GetStringChars(env, text, NULL);
if (p == NULL) {
    return;  /* đoạn minh họa cho hàm trả void */
}
(*env)->ReleaseStringChars(env, text, p);

/* SAI: đọc p[0] sau Release, dù lần thử trước vẫn chạy được. */
/* printf("%u", (unsigned)p[0]); */
```

Hãy copy những giá trị thực sự cần dùng **trước khi Release**. Trình biên dịch và GC/JVM có thể khiến lỗi use-after-release chỉ xuất hiện gián đoạn hoặc trên một nền tảng khác.

## 10. Phân biệt với `GetStringCritical` và các hàm Region

### `GetStringCritical` cần cặp `ReleaseStringCritical` riêng

`GetStringCritical` trả `const jchar *`, nhưng có **ràng buộc mạnh hơn** `GetStringChars`: giữa Get và Release, native code không được gọi tùy ý các JNI functions khác hoặc làm thread hiện tại bị block. JVM có thể dùng pinning để giảm copy, ảnh hưởng tiến trình GC nếu vùng critical bị giữ lâu. Vì vậy chỉ dùng đoạn xử lý **ngắn và không block**, Release bằng đúng `ReleaseStringCritical`.

```c
/* Đoạn minh họa trong hàm JNI; text hợp lệ. */
jsize n = (*env)->GetStringLength(env, text);
const jchar *ptr = (*env)->GetStringCritical(env, text, NULL);
if (ptr == NULL) {
    return; /* hàm C ví dụ trả void */
}
jint zeros = 0;
for (jsize i = 0; i < n; ++i) {
    if (ptr[i] == 0) ++zeros;  /* chỉ tính toán trong C */
}
(*env)->ReleaseStringCritical(env, text, ptr);
/* Có thể gọi JNI tiếp theo ở đây nếu cần. */
```

Không gọi `ReleaseStringChars` cho `ptr` từ `GetStringCritical` dù cả hai đều có kiểu `const jchar *`. Nếu chỉ xử lý một mảng ký tự nhỏ, `GetStringRegion` có thể đơn giản hơn.

### `GetStringRegion` và `GetStringUTFRegion` không tạo lease cần Release

`GetStringRegion(env, text, start, len, jcharBuffer)` sao chép các UTF-16 units của vùng được chọn **vào buffer do bạn cấp**. Vì đây không phải pointer mượn từ JVM, không có `ReleaseStringRegion`; chủ của buffer sẽ `free` hoặc quản lý nó theo cách đã cấp phát.

`GetStringUTFRegion(env, text, start, len, charBuffer)` ghi **modified UTF-8** vào buffer do C cấp. Ở hàm này, `len` tính theo **UTF-16 units**, còn dung lượng output cần tính theo **bytes**, có thể tới `3 * len` bytes. Không được mặc định kết quả có NUL terminator; nếu cần C string, hãy cấp đủ byte capacity và tự bảo đảm kết thúc NUL sau khi biết số byte thực tế. Kiểm tra bounds và pending `StringIndexOutOfBoundsException` nếu vùng không hợp lệ.

Hàm Region phù hợp khi biết phạm vi nhỏ hoặc muốn chủ động sở hữu bộ nhớ, tránh một vòng Get/Release. Chọn theo contract thay vì tìm cách “bỏ Release” của các Get functions.

## 11. Lỗi thường gặp: triệu chứng và cách sửa

| Sai lầm | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| `GetStringChars` thành công rồi return sớm không Release | Leak/cản trở JVM quản lý bộ nhớ và GC | Mỗi nhánh phải đi qua `ReleaseStringChars` |
| `GetStringUTFChars` nhưng gọi `ReleaseStringChars` | Mismatch resource/kiểu; undefined behavior, có thể crash | Gọi `ReleaseStringUTFChars` |
| `isCopy == JNI_FALSE` nên bỏ Release | Nhầm implementation detail với hợp đồng ownership | **Luôn Release** nếu Get thành công |
| `free((void *)chars)` | Giải phóng bộ nhớ không thuộc C | Chỉ dùng JNI Release cho pointer JNI cấp |
| `DeleteLocalRef(text)` thay Release | Chỉ xóa reference, chưa kết thúc string access lease | Release trước, quản lý local ref riêng |
| `strlen` trên `jchar *` hoặc trên buffer không bảo đảm NUL | Sai đơn vị/đọc tràn | `GetStringLength`/`GetStringUTFLength` và giới hạn vòng lặp |
| Coi modified UTF-8 như UTF-8 chuẩn | U+0000/emoji bị biểu diễn khác | Encode/decode đúng chuẩn giao thức |
| Ép `jchar *` sang `wchar_t *` | `wchar_t` thường khác 16 bit | Dùng `jchar` và UTF-16 units |
| Truy cập `ptr[0]` khi Java String rỗng | Out-of-bounds | Kiểm tra `GetStringLength > 0` |
| Giữ pointer sau `Release` | Use-after-release | Copy dữ liệu cần thiết trước Release |
| Giữ pointer quá lâu trong vòng I/O | Tăng áp lực bộ nhớ/pinning, khó xử lý lỗi | Release sớm; xử lý I/O sau khi đã copy |
| Dùng `ReleaseStringCritical` cho `GetStringChars` | Sai cặp API | Ghép đúng tên đối xứng |
| Truyền `jstring NULL` vào Get | Vi phạm hợp đồng JNI, có thể crash | Kiểm tra null và báo Java exception |
| Gọi `GetStringUTFLengthAsLong` khi build `jni.h` JDK 17 | API mới xuất hiện từ JDK 24 | Dùng API đúng phiên bản hoặc nâng JDK |
| Dùng `NewStringUTF` với UTF-8 chuẩn từ network | Sai MUTF-8, có thể lỗi hoặc mất dữ liệu | Decode standard UTF-8 đúng cách rồi tạo Java String |

**Chẩn đoán:** trên JVM hỗ trợ, dùng `java -Xcheck:jni -Djava.library.path=. JniStringLeaseDemo` để kích hoạt nhiều kiểm tra bổ sung JNI. Chế độ này có thể phát hiện thao tác JNI sai nhưng không bảo đảm mọi lỗi con trỏ C đều được bắt. Nếu có crash native, giữ `hs_err_pid*.log`/backtrace và kiểm tra cả code Get/Release, ngoài phần Java exception.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `GetStringUTFChars` trả pointer và `isCopy == JNI_FALSE`. Có bỏ qua `ReleaseStringUTFChars` không?

**Không.** `isCopy` chỉ cho biết JVM có tạo bản sao hay không; thông báo kết thúc việc sử dụng pointer là nghĩa vụ của JNI caller.

**Câu 2.** Native nhận `"A\u0000B"`. Có được gọi `strlen` để xác định `String.length()` không?

**Không.** Java String có 3 UTF-16 units, kể cả U+0000. `GetStringLength` trả 3; modified UTF-8 mã hóa U+0000 bằng 2 byte, nên byte count là 4. Mọi phép đo bytes cần dùng API/length phù hợp, không dùng `strlen` trên buffer thiếu bảo đảm NUL.

**Câu 3.** `GetStringChars` trả pointer có 6 `jchar` cho `"a\0\u03A9\uD83D\uDE03z"`. Vì sao string chỉ có 5 code points?

**Vì** supplementary U+1F603 cần hai UTF-16 surrogate units. `GetStringLength` đếm units còn `codePointCount` đếm code points.

**Câu 4.** Sau `GetStringChars` thành công, `malloc` ở C thất bại. Hàm có thể ném `OutOfMemoryError` rồi return ngay không?

**Phải Release trước khi return.** Mẫu đúng là `ReleaseStringChars(env, text, chars)`, sau đó tạo/đẩy exception thích hợp (nếu chưa có exception pending), rồi return. Không dùng `free(chars)`.

**Câu 5.** Có thể dùng `ReleaseStringChars` cho pointer `GetStringCritical` vì cùng kiểu `jchar *` không?

**Không.** Mỗi API có cặp riêng. `GetStringCritical` phải ghép `ReleaseStringCritical` và còn chịu hạn chế nghiêm ngặt về blocking/arbitrary JNI calls.

**Câu 6.** Có thể trực tiếp đẩy `const char *` từ `GetStringUTFChars` sang một hàm JSON C yêu cầu UTF-8 chuẩn không?

**Không bảo đảm.** JNI dùng modified UTF-8; khác standard UTF-8 ở U+0000 và supplementary characters. Nếu API yêu cầu standard UTF-8, cần chuyển mã đúng và truyền length hoặc C-string buffer được chuẩn bị hợp lệ.

## Tài liệu chính thức

- Oracle JNI Specification — [String Operations, `GetStringChars`/`ReleaseStringChars`, `GetStringUTFChars`/`ReleaseStringUTFChars`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#string-operations)
- Oracle JNI Specification — [`GetStringCritical` và `ReleaseStringCritical`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getstringcritical-releasestringcritical)
- Oracle JNI Specification — [`GetStringRegion` và `GetStringUTFRegion`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getstringregion)
- Oracle JNI Specification — [`GetStringUTFLengthAsLong`, từ JDK 24](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getstringutflengthaslong)
- Oracle JNI Specification — [Modified UTF-8 Strings](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html#modified-utf-8-strings)
- Oracle Java SE 17 — [`String`, `length()`, `codePointCount()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- Oracle Java SE 17 — [`javac -h` tạo native headers](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Điều cần nhớ:** `GetStringChars` mượn **UTF-16 units**, `GetStringUTFChars` mượn **modified UTF-8 bytes**. Mỗi con trỏ mượn phải được giải phóng **một lần bằng đúng hàm Release tương ứng, với chính chuỗi và con trỏ đã lấy**, bất kể `isCopy`. Đo độ dài bằng đúng đơn vị, Release trên mọi nhánh lỗi, và không giữ con trỏ sau Release.