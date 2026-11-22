# Chuỗi kết thúc bằng byte 0, dữ liệu nhị phân và tham số độ dài (C và ABI ↔ Java)

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt **C string** (chuỗi byte kết thúc tại byte `0`) với **dữ liệu nhị phân** (mọi byte đều có thể là dữ liệu), xác định khi nào ABI yêu cầu con trỏ kèm độ dài, chuyển đổi an toàn giữa `String`/`byte[]` của Java và vùng nhớ native, cũng như tránh lỗi cắt cụt dữ liệu, đọc quá biên và nhầm đơn vị độ dài.

Quy tắc trọng tâm: **không suy ra kích thước một buffer nhị phân bằng `strlen`**. Một con trỏ tự nó không mang thông tin về số byte còn hợp lệ để đọc. Định dạng và hợp đồng API mới quyết định điểm kết thúc của dữ liệu.

## 1. Ba khái niệm cần tách bạch

| Mô hình | Biểu diễn thường gặp | Xác định điểm kết thúc | Byte `0x00` có vai trò gì? |
| --- | --- | --- | --- |
| C string | `const char *` trỏ tới dãy byte | Byte `'\0'` đầu tiên mà hàm đọc tới | Là dấu kết thúc; không thuộc nội dung chuỗi theo `strlen` |
| Binary buffer | `const void *`/`const unsigned char *` + `size_t length` | Độ dài do caller cung cấp theo hợp đồng | Là dữ liệu bình thường; có thể xuất hiện ở bất kỳ vị trí nào |
| Java `String` | Đối tượng văn bản Unicode | `String.length()` trả số đơn vị mã UTF-16 | Có thể chứa ký tự U+0000; không tự kết thúc tại ký tự này |

Ở C, `'\0'` có giá trị số 0; về mặt lưu trữ đó là **một byte bằng 0** trong chuỗi `char` thông thường. Chuỗi C không có metadata bắt buộc để ghi sẵn độ dài. Hàm `strlen(s)` quét tới byte 0 đầu tiên và trả về **số byte trước dấu kết thúc**, không tính chính byte kết thúc.

Ví dụ, bộ nhớ `['A', 'B', 0, 'C', 'D']` có năm byte, nhưng nếu được coi là C string thì nội dung quan sát được là `"AB"`, dài hai byte. Hai byte `'C'` và `'D'` vẫn ở trong vùng nhớ; chỉ là các hàm chuỗi C thông thường không xem chúng là một phần của chuỗi bắt đầu tại `'A'`.

Một Java `String` không đồng nghĩa với `char *` của C. Muốn chuyển thành byte để gọi thư viện native, cần chọn **mã hóa** (thường là UTF-8), xác định **độ dài tính bằng byte**, rồi quyết định có thêm byte 0 theo hợp đồng C API hay không.

## 2. `strlen`, `sizeof`, độ dài dữ liệu và dung lượng buffer

Tạo tệp `CStringAndBinary.c`:

~~~c
#include <stdio.h>
#include <string.h>

int main(void) {
    const char text[] = "AB";
    const unsigned char binary[] = {'A', 0, 'B', 0xFF};

    printf("strlen(text) = %zu\n", strlen(text));
    printf("sizeof(text) = %zu\n", sizeof text);
    printf("strlen(binary as C string) = %zu\n",
           strlen((const char *) binary));
    printf("sizeof(binary) = %zu\n", sizeof binary);
    return 0;
}
~~~

Trên hệ thống có trình biên dịch C hỗ trợ C11, chạy:

~~~bash
cc -std=c11 -Wall -Wextra CStringAndBinary.c -o cstring-demo
./cstring-demo
~~~

Kết quả:

~~~text
strlen(text) = 2
sizeof(text) = 3
strlen(binary as C string) = 1
sizeof(binary) = 4
~~~

Giải thích:

- `"AB"` được khởi tạo vào mảng `text` gồm `'A'`, `'B'` và byte kết thúc `0`. Do đó độ dài văn bản là 2, còn dung lượng mảng là 3.
- Mảng `binary` gồm bốn byte, trong đó byte thứ hai bằng `0`. Ép kiểu sang `const char *` không biến nó thành dữ liệu văn bản hoàn chỉnh: `strlen` vẫn dừng ngay tại byte `0` đó.
- `sizeof local_array` chỉ cho biết kích thước mảng còn giữ nguyên kiểu mảng ở phạm vi này. Khi truyền mảng vào tham số hàm dạng con trỏ, `sizeof(pointer)` cho biết kích thước **con trỏ**, không phải kích thước dữ liệu mà nó trỏ tới.
- `size_t` là kiểu số nguyên không dấu dùng cho kích thước đối tượng C; định dạng `%zu` dùng để in `size_t`. Kích thước của `size_t` là đặc tính của ABI/kiến trúc, không được giả định cố định 32 hoặc 64 bit.

**Nguy hiểm:** gọi `strlen` trên một buffer không bảo đảm có byte kết thúc **trong vùng nhớ có thể truy cập** dẫn tới hành vi không xác định (undefined behavior); nó có thể đọc vượt vùng, truy cập lỗi hoặc vô tình đọc bộ nhớ khác. `strlen` không có tham số giới hạn kích thước nên bản thân hàm không thể kiểm tra biên.

Phân biệt bốn đại lượng:

- **Payload length:** số byte dữ liệu thực sự cần xử lý, ví dụ 4.
- **C-string length:** số byte trước byte `0` đầu tiên, ví dụ 1.
- **Capacity:** số byte vùng nhớ được cấp và còn được phép sử dụng, ví dụ 8.
- **Terminator storage:** một byte bổ sung cho `'\0'` khi xây dựng C string; không nằm trong kết quả `strlen`.

## 3. Chọn hợp đồng ABI: dấu kết thúc hay con trỏ + độ dài?

Hai kiểu hàm C có ý nghĩa rất khác:

~~~c
/* Yêu cầu name là C string có NUL hợp lệ. */
int use_name(const char *name);

/* Xử lý đúng length byte, kể cả các byte bằng 0. */
int consume_bytes(const unsigned char *data, size_t length);
~~~

Với `use_name`, bên gọi phải cấp ít nhất `n + 1` byte nếu tên mã hóa chiếm `n` byte, đặt `data[n] = '\0'` và bảo đảm không có byte 0 ngoài ý muốn trước vị trí kết thúc. Hàm native đọc tới dấu kết thúc theo hợp đồng.

Với `consume_bytes`, bên gọi phải bảo đảm `data` trỏ tới ít nhất `length` byte hợp lệ trong toàn bộ thời gian thực hiện. Hàm native **không tự gọi `strlen`, `strcpy` hoặc `strcmp` trên dữ liệu nhị phân**. Độ dài thường không bao gồm byte đánh dấu kết thúc nào, vì loại API này không cần terminator. Một buffer nhị phân tình cờ có byte cuối bằng 0 vẫn được xử lý đủ theo `length`.

Một cách bọc dữ liệu rõ ràng khi thiết kế C API:

~~~c
#include <stddef.h>

typedef struct {
    const unsigned char *data;
    size_t length;
} ByteSpan;

int parse_packet(ByteSpan packet);
~~~

`ByteSpan` không tự sở hữu vùng nhớ. Caller và callee vẫn phải thống nhất ai cấp phát, ai giải phóng, dữ liệu có thể thay đổi hay không, pointer còn sống bao lâu, và hàm có giữ lại pointer sau khi trả về không. Với callback/bất đồng bộ, tuyệt đối không để thư viện C giữ pointer tới một buffer Java đã hết vòng đời hoặc đã bị JNI release.

Với một buffer có dung lượng xác định nhưng muốn tìm C string, hãy dùng **tìm kiếm có giới hạn**, ví dụ `memchr`:

~~~c
#include <stddef.h>
#include <string.h>

/* Trả 0 nếu có NUL trong capacity byte; -1 nếu không có. */
int bounded_c_string_length(const char *buffer,
                            size_t capacity,
                            size_t *out_length) {
    if (out_length == NULL || (buffer == NULL && capacity != 0)) {
        return -1;
    }
    if (capacity == 0) {
        return -1;
    }
    const char *end = memchr(buffer, '\0', capacity);
    if (end == NULL) {
        return -1;
    }
    *out_length = (size_t) (end - buffer);
    return 0;
}
~~~

Ở đây `memchr` chỉ đọc tối đa `capacity` byte hợp lệ; nếu không thấy terminator, ta từ chối coi buffer là C string. `strnlen` có trên nhiều hệ POSIX, nhưng không nên giả định là hàm chuẩn ISO C có mặt ở mọi môi trường. Chỉ tìm NUL khi **hợp đồng thực sự nói đây là text dạng C string**, không dùng nó như cách tính độ dài packet.

## 4. Byte và ký tự: UTF-8, UTF-16 và độ dài phải dùng

Câu hỏi “chuỗi dài bao nhiêu?” cần nêu rõ **đơn vị**. Một chữ `é` có một Unicode code point, một UTF-16 code unit trong Java, nhưng **hai byte UTF-8** (`C3 A9`). Một emoji ngoài BMP thường có hai UTF-16 code unit và bốn byte UTF-8. Vì vậy:

- `javaString.length()` trả số UTF-16 code unit; không dùng kết quả này làm số byte của `UTF-8 char *`.
- `javaString.getBytes(StandardCharsets.UTF_8).length` trả số byte sau mã hóa UTF-8.
- `strlen(utf8CString)` đếm số byte đến NUL, không đếm Unicode code point.
- `byte[].length` là số phần tử byte; mỗi phần tử có kiểu Java `byte` có dấu (-128…127), nhưng bit pattern `0xFF` vẫn là cùng tám bit khi chuyển sang C `unsigned char`. Đừng dùng dấu của Java `byte` để suy luận nội dung giao thức.

Sơ đồ bộ nhớ cho văn bản `"é"` mã hóa UTF-8 theo C string:

~~~text
offset      0      1      2
byte       C3     A9     00
           └─ "é" ─┘     NUL
payload length = 2 bytes
allocated capacity = at least 3 bytes
strlen = 2
~~~

Nếu giao thức dùng `(pointer, length)`, thường truyền **2** làm payload length và không cần byte 0. Nếu hàm C cần `char *` dạng NUL-terminated, cần buffer **3** byte như hình. Không nên sử dụng platform default charset bằng cách gọi `getBytes()` không có tham số; chọn charset theo hợp đồng của thư viện/giao thức.

**Embedded NUL:** Java cho phép `"ab\0cd"`, nhưng khi mã hóa thành UTF-8 tiêu chuẩn, ký tự U+0000 cho ra byte `00`. C API dựa vào terminator sẽ chỉ thấy `"ab"`. Vì vậy cần **từ chối U+0000** nếu tên/đường dẫn/identifier phải đi qua C-string ABI và không hỗ trợ trường hợp này, hoặc chuyển sang API nhận độ dài nếu muốn giữ nguyên dữ liệu.

## 5. Java 17+: ví dụ chạy được, tách rõ C string và binary

Tạo `CStringVsBinary.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CStringVsBinary {
    // Chỉ dùng khi buffer thực sự phải là C string trong phạm vi mảng.
    static int boundedCStringLength(byte[] buffer) {
        for (int i = 0; i < buffer.length; i++) {
            if (buffer[i] == 0) {
                return i;
            }
        }
        throw new IllegalArgumentException("Missing NUL terminator");
    }

    // Hợp đồng nhận UTF-8 C string, không chấp nhận NUL nằm giữa nội dung.
    static byte[] encodeCString(String text) {
        if (text.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("Embedded NUL");
        }
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        return Arrays.copyOf(utf8, utf8.length + 1); // byte mới = 0
    }

    // Hợp đồng binary: length quyết định chính xác bao nhiêu byte được giữ.
    static byte[] copyBinary(byte[] source, int length) {
        if (length < 0 || length > source.length) {
            throw new IllegalArgumentException("Invalid length");
        }
        return Arrays.copyOf(source, length);
    }

    public static void main(String[] args) {
        byte[] payload = {65, 0, 66, (byte) 0xFF};

        int textLength = boundedCStringLength(payload);
        System.out.println("C text: " + new String(
                payload, 0, textLength, StandardCharsets.UTF_8));
        System.out.println("Binary bytes: "
                + Arrays.toString(copyBinary(payload, payload.length)));
        System.out.println("Encoded C: "
                + Arrays.toString(encodeCString("Hi")));
        System.out.println("UTF-8 bytes for é: "
                + "é".getBytes(StandardCharsets.UTF_8).length);

        try {
            boundedCStringLength(new byte[] {65, 66});
        } catch (IllegalArgumentException e) {
            System.out.println("Missing terminator rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CStringVsBinary.java
java CStringVsBinary
~~~

Stdout:

~~~text
C text: A
Binary bytes: [65, 0, 66, -1]
Encoded C: [72, 105, 0]
UTF-8 bytes for é: 2
Missing terminator rejected
~~~

Điểm quan sát:

1. C string nhìn buffer `{65, 0, 66, 255}` thành `"A"` vì dừng tại byte thứ hai. Dạng binary vẫn có đủ bốn byte; Java in bit pattern `0xFF` thành `-1` do `byte` có dấu.
2. `encodeCString("Hi")` cho `[72, 105, 0]`; byte 0 là vùng chứa terminator, còn payload chỉ có hai byte.
3. Không thể suy ra C-string length từ mảng không có NUL bằng cách quét vô hạn; ví dụ chủ động từ chối.
4. `Arrays.copyOf` trong ví dụ tạo mảng mới. Khi dùng JNI/FFM, cần xem API native có copy dữ liệu hay giữ tham chiếu tới vùng nhớ.

Ví dụ này minh họa chính xác **biểu diễn byte**; nó chưa tự gọi native. Phần sau dùng JNI để đưa binary buffer qua biên Java ↔ C.

Khi giải mã một byte buffer không đáng tin, `new String(bytes, UTF_8)` có thể thay chuỗi byte UTF-8 lỗi bằng ký tự thay thế. Nếu giao thức yêu cầu từ chối UTF-8 không hợp lệ, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` thay vì âm thầm chấp nhận dữ liệu bị thay đổi.

## 6. JNI: truyền `byte[]` như binary, giữ độ dài thực

Giả sử Java gọi native để đếm byte có giá trị 0. API này **phải đếm cả các byte sau NUL**, nên dùng `jbyteArray` cùng `GetArrayLength`, không dùng `strlen`.

Tệp `BinaryBridge.java`:

~~~java
public final class BinaryBridge {
    static {
        System.loadLibrary("binarybridge");
    }

    private native int countZeros(byte[] bytes);

    public static void main(String[] args) {
        byte[] packet = {65, 0, 66, 0};
        System.out.println(new BinaryBridge().countZeros(packet));
    }
}
~~~

Tệp `BinaryBridge.c`:

~~~c
#include <jni.h>
#include "BinaryBridge.h"

JNIEXPORT jint JNICALL Java_BinaryBridge_countZeros(
        JNIEnv *env, jobject receiver, jbyteArray bytes) {
    (void) receiver;

    if (bytes == NULL) {
        jclass type = (*env)->FindClass(env, "java/lang/NullPointerException");
        if (type != NULL) {
            (*env)->ThrowNew(env, type, "bytes");
        }
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, bytes);
    jbyte *data = (*env)->GetByteArrayElements(env, bytes, NULL);
    if (data == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            jclass type = (*env)->FindClass(env, "java/lang/OutOfMemoryError");
            if (type != NULL) {
                (*env)->ThrowNew(env, type, "Cannot access byte array");
            }
        }
        return 0;
    }

    jint zeros = 0;
    for (jsize i = 0; i < length; i++) {
        if (data[i] == 0) {
            zeros++;
        }
    }

    (*env)->ReleaseByteArrayElements(env, bytes, data, JNI_ABORT);
    return zeros;
}
~~~

Trên **Linux** có JDK 17+ và compiler C, đặt `JAVA_HOME` trỏ tới JDK đang dùng rồi chạy tại thư mục chứa hai tệp:

~~~bash
javac -h . BinaryBridge.java
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  BinaryBridge.c -o libbinarybridge.so
java -Djava.library.path=. BinaryBridge
~~~

Stdout:

~~~text
2
~~~

`javac -h .` sinh đúng header JNI theo khai báo native. Trên macOS/Windows, tên thư viện, cờ build và thư mục header nền tảng thay đổi; lệnh ở trên **dành riêng cho Linux**, không được xem như lệnh build đa nền tảng.

Giải thích cơ chế JNI:

- `GetArrayLength` trả số phần tử của `jbyteArray`, với kiểu `jsize`. Nó bao gồm mọi byte 0 vì mảng Java không dùng terminator.
- `GetByteArrayElements` có thể cấp một bản copy hoặc cho phép truy cập trực tiếp dữ liệu mảng tùy JVM. Không giả định đây là pointer ổn định có thể lưu lại sau hàm.
- `ReleaseByteArrayElements(..., JNI_ABORT)` giải phóng quyền truy cập mà **không copy thay đổi ngược** nếu JVM dùng buffer copy; phù hợp vì ví dụ chỉ đọc. Nếu native cần sửa mảng và trả thay đổi về Java, phải chọn chế độ release phù hợp.
- `jbyte` là kiểu byte có dấu của JNI. Với dữ liệu định dạng nhị phân, khi cần giá trị 0..255 hãy cast sang `unsigned char` hoặc mask đúng thay vì so sánh như số âm/dương.
- Nếu native muốn đọc một đoạn mảng qua bản copy ngắn, `GetByteArrayRegion` cũng là lựa chọn tốt; nó nhận **start** và **length** rõ ràng, có thể tránh quản lý cặp get/release. Vẫn phải kiểm tra ngoại lệ JNI và giới hạn vùng đọc.

**Không đưa `data` ra khỏi vòng đời acquire/release**. Không lưu pointer trong biến toàn cục, đối tượng C hoặc tác vụ chạy sau khi native method đã kết thúc. Nếu thư viện C cần sở hữu dữ liệu lâu hơn, hãy cấp phát/copy sang native storage do nó quản lý và quy định trách nhiệm giải phóng.

### JNI `String` và bẫy Modified UTF-8

JNI có các hàm `GetStringUTFChars`, `ReleaseStringUTFChars` và `NewStringUTF`. Chúng dùng **Modified UTF-8 (MUTF-8)** của JNI, không đồng nhất với UTF-8 chuẩn dùng bởi `StandardCharsets.UTF_8`. Chẳng hạn U+0000 được mã hóa theo quy tắc modified UTF-8 thay vì byte 0 thông thường; các ký tự ngoài BMP cũng có cách biểu diễn khác UTF-8 chuẩn.

Vì vậy, **không** tự động đưa output `GetStringUTFChars` vào một C API đòi UTF-8 chuẩn nếu đầu vào có thể chứa các ký tự chịu ảnh hưởng của khác biệt encoding. Ngược lại, không gọi `NewStringUTF` với dữ liệu UTF-8 tùy ý hoặc packet binary. Nếu hợp đồng C thật sự yêu cầu UTF-8 chuẩn, chuyển `String` sang `byte[]` bằng `StandardCharsets.UTF_8`, rồi thêm terminator/chuyển chiều dài theo đúng loại API; ở chiều về, giải mã chính xác `length` byte.

## 7. FFM ở JDK hiện đại và sự khác biệt với JNI

Từ **JDK 22**, Foreign Function & Memory API (FFM, package `java.lang.foreign`) là API chuẩn để Java gọi thư viện native và làm việc với vùng nhớ ngoài heap. Trong JDK 17, FFM còn ở giai đoạn incubator; giữa các phiên bản trước JDK 22, API/signature đã thay đổi. Do đó không áp một đoạn ví dụ FFM JDK 22 vào chương trình Java 17 mà kỳ vọng biên dịch trực tiếp.

Dù dùng JNI hay FFM, **hợp đồng C vẫn giữ nguyên**:

- Hàm nhận `const char *` dạng C string phải có NUL trong vùng nhớ hợp lệ; cần kiểm soát encoding và ký tự NUL giữa nội dung.
- Hàm nhận `(void *, size_t)` phải có đúng số byte, kể cả NUL; kích thước khai báo cho native không được vượt dung lượng vùng nhớ thực tế.
- Với FFM, `MemorySegment` mô tả vùng nhớ và giới hạn truy cập; `Arena` quản lý vòng đời. Pointer native không được dùng sau khi arena/segment hết hiệu lực.
- Mô tả native function descriptor phải khớp ABI của mục tiêu. `size_t` không được mặc nhiên đồng nhất với Java `int`; khi chuyển kích thước cần kiểm tra kiến trúc, signedness và giới hạn giá trị.

Chọn JNI hay FFM là quyết định công nghệ; **chọn giữa C-string và pointer-plus-length là quyết định về dữ liệu và ABI**, độc lập với công nghệ gọi native.

## 8. Độ dài, capacity và kiểm tra biên trước lời gọi native

Một hợp đồng đáng tin cậy nên nêu rõ sáu điểm:

1. **Đơn vị:** `length` tính theo byte, UTF-16 code unit, số phần tử hay số code point? Trong C API byte buffer, thông thường là byte.
2. **Ý nghĩa length:** gồm hay không gồm terminator, chỉ input hay cả capacity output? Ví dụ `inputLength` có thể là số byte payload; `outputCapacity` là dung lượng vùng output cho phép ghi, hoàn toàn khác nhau.
3. **Nullability:** `data == NULL` có hợp lệ khi `length == 0` không? Hàm nào từ chối, hàm nào chấp nhận? Đây là hợp đồng cần ghi rõ, không tự suy đoán.
4. **Ownership và lifetime:** ai cấp phát/giải phóng; callee có được giữ pointer không; buffer có thể bị ghi đè hay không?
5. **Encoding:** UTF-8 chuẩn, MUTF-8 của JNI, UTF-16, ASCII, hay nhị phân nguyên trạng? Ai encode/decode?
6. **Giới hạn và lỗi:** kiểm tra `length <= capacity`, kiểm tra phép tính `length + 1` không tràn, kiểm tra ép kiểu giữa `size_t` và `jsize`/Java `int`, và quy định cách báo lỗi.

Ví dụ, đoạn C sau chỉ được phép chạy nếu `capacity` có đủ chỗ cho payload **và** terminator:

~~~c
#include <stddef.h>
#include <string.h>

int write_c_string(char *destination, size_t capacity,
                   const char *source, size_t source_length) {
    if (destination == NULL || source == NULL) {
        return -1;
    }
    /* Điều kiện này đồng thời tránh source_length + 1 bị tràn. */
    if (source_length >= capacity) {
        return -1;
    }
    /* source phải trỏ tới ít nhất source_length byte có thể đọc. */
    memcpy(destination, source, source_length);
    destination[source_length] = '\0';
    return 0;
}
~~~

Hàm mẫu cố ý **không tự xác định** `source_length` bằng `strlen`: caller đã xác định số byte cần copy. Caller cũng phải bảo đảm hai vùng source/destination không chồng lấp (yêu cầu của `memcpy`) và input không chứa NUL giữa nội dung nếu đích được dùng như một C string đơn trị. Nếu caller truyền độ dài tính theo ký tự Java thay vì byte UTF-8, phép copy có thể cắt giữa chuỗi nhiều byte và gây lỗi giải mã.

**Về tràn số:** nếu cần tính `payloadLength + 1` để cấp phát, kiểm tra `payloadLength < SIZE_MAX` trước khi cộng. Nếu cần `count * elementSize`, kiểm tra phép nhân trước khi cấp phát. Khi ép `size_t` sang `int`/`jsize`, cần kiểm tra kích thước có biểu diễn được trong đích hay không; ép trực tiếp có thể mất dữ liệu.

**Về signedness:** Java `byte` có dấu; C `char` có thể có dấu hoặc không tùy implementation; `unsigned char` thích hợp khi làm việc với octet/byte nhị phân. Đừng dựa vào so sánh hoặc cast ngầm của byte lớn hơn `0x7F` nếu ý nghĩa yêu cầu 0..255.

## 9. Ca lỗi thực tế tại ranh giới Java ↔ C

**Ca 1 — packet bị cắt mất nội dung.** Java tạo `byte[] {0x50, 0x00, 0x4B, (byte) 0xFF}` (bốn byte), nhưng C dùng `strlen((char *)ptr)` và chỉ thấy một byte `0x50`. Parser nhận dữ liệu thiếu, checksum thất bại hoặc thông điệp bị hiểu sai. Cách sửa: chọn API `parse(ptr, 4)` và xử lý chính xác bốn byte.

**Ca 2 — Java và C xác thực khác nhau.** Java kiểm tra tên `"admin\0guest"` như chuỗi nguyên vẹn, còn C API dựa trên `char *` chỉ đọc `"admin"`. Nếu quy tắc quyền truy cập, tên tệp hoặc allowlist dùng hai cách diễn giải, có thể phát sinh lỗ hổng. Cách sửa: cùng một cách chuẩn hóa/validation theo **định dạng thực sự truyền**, từ chối NUL nhúng khi qua C-string ABI, và kiểm tra ngay trước call.

**Ca 3 — `String.length()` thành byte length.** `"café"` có bốn UTF-16 code unit nhưng năm byte UTF-8. Gửi `length = 4` cho native C API binary sẽ cắt mất byte cuối của `é`. Cách sửa: encode trước, dùng `utf8Bytes.length`.

**Ca 4 — dùng `sizeof` trên tham số pointer.** C code nhận `const unsigned char *bytes` rồi dùng `sizeof(bytes)` để suy ra packet length. Kết quả là kích thước con trỏ theo ABI, không phải length của packet. Cách sửa: truyền tham số `size_t length` hoặc một struct chứa length rõ ràng.

**Ca 5 — quên terminator hoặc cấp phát đúng `n` byte.** Buffer chứa `n` byte nội dung nhưng không có chỗ cho `'\0'`. Hàm chuỗi C quét qua ranh giới hoặc caller ghi terminator ngoài biên. Cách sửa: thỏa `capacity >= n + 1`, kiểm tra tràn số, gán terminator ở vị trí `n`.

**Ca 6 — native giữ pointer Java đã release.** Native đưa kết quả `GetByteArrayElements` vào callback bất đồng bộ, sau đó `ReleaseByteArrayElements` trước khi callback dùng xong. Pointer không còn hợp lệ. Cách sửa: copy sang vùng nhớ có vòng đời phù hợp hoặc thiết kế API để xử lý đồng bộ trong thời gian pointer còn hợp lệ.

## 10. Bài tự kiểm tra và đáp án

**Câu 1.** Với `unsigned char p[] = {'A', 0, 'B'};`, `sizeof p` bằng bao nhiêu? Nếu chuyển sang `const char *` để gọi `strlen` thì kết quả bao nhiêu?

Đáp án: `sizeof p == 3` byte trong cùng scope với khai báo mảng. `strlen((const char *)p) == 1` vì byte 0 nằm ở chỉ số 1. Không được dùng kết quả 1 để thay length của mảng binary.

**Câu 2.** Muốn truyền `"é"` dưới dạng UTF-8 C string, phải cấp bao nhiêu byte và truyền length bao nhiêu nếu C API khác yêu cầu pointer + payload length?

Đáp án: 3 byte nếu lưu cả terminator (`C3 A9 00`); payload length là 2 byte khi gọi API pointer-plus-length không tính terminator.

**Câu 3.** Khi nhận từ Java một `byte[]` có NUL ở giữa, nên dùng API `const char *` hay `(const void *, size_t)`?

Đáp án: nếu dữ liệu cần giữ nguyên toàn bộ byte, dùng pointer + length; nếu đó thực sự là văn bản C-string, phải xác nhận encoding và xử lý/từ chối NUL nhúng theo hợp đồng.

**Câu 4.** Một buffer C có capacity 8, payload UTF-8 chiếm đúng 8 byte. Có thể ghi terminator ở `buffer[8]` không?

Đáp án: không; index hợp lệ của buffer capacity 8 là 0..7. Muốn chứa thêm terminator cần capacity ít nhất 9 và kiểm tra overflow khi tính kích thước.

**Câu 5.** `GetStringUTFChars` có mặc nhiên tạo byte UTF-8 tiêu chuẩn giống `String.getBytes(StandardCharsets.UTF_8)` không?

Đáp án: không; JNI dùng Modified UTF-8. Với yêu cầu trao đổi UTF-8 chuẩn hoặc byte binary, cần chọn đường encode/decode phù hợp, không thay thế lẫn nhau bằng tên gọi gần giống.

## Checklist khi thiết kế hoặc review một Java/native boundary

- Đã phân loại dữ liệu thành **text** hay **binary** trước khi chọn dạng tham số chưa?
- Nếu là text, charset là gì; C ABI cần NUL không; có chấp nhận embedded NUL không?
- Nếu là binary, đã truyền **pointer + length**; tính length bằng byte; giữ nguyên mọi byte 0 chưa?
- `length` có nằm trong phạm vi buffer và kiểu số của ABI không? `capacity` có đủ chỗ cho terminator khi cần không?
- Con trỏ có hợp lệ xuyên suốt thời gian native dùng không? JNI get/release, FFM arena hoặc vùng nhớ tự cấp phát có được quản lý đúng không?
- Đã kiểm thử chuỗi rỗng, thiếu NUL, NUL nhúng, Unicode đa byte, byte `0xFF`, buffer length 0 và kích thước biên chưa?

## Tài liệu tham khảo

- [ISO C library `strlen`: hành vi và điều kiện NUL](https://en.cppreference.com/c/string/byte/strlen).
- [Java SE 17 JNI Functions: arrays, strings và release modes](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Java SE 22 Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).

**Ghi nhớ:** `'\0'` là quy ước kết thúc của **C string**, còn `length` là một phần của **hợp đồng binary buffer**. Bảo toàn dữ liệu qua ABI phụ thuộc vào encoding, kích thước thực, vùng nhớ hợp lệ và vòng đời pointer — không phụ thuộc vào việc có tình cờ tìm thấy byte 0 hay không.
