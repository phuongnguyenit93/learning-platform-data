# Đọc chuỗi C với bảng mã, byte kết thúc và giới hạn chiều dài

## Mục tiêu

Một thư viện C có thể trả về `const char *`, `char *` hoặc `unsigned char *` chứa các byte được hiểu là “chuỗi”. Khi đưa chuỗi đó sang Java qua JNI hoặc Foreign Function & Memory API (FFM), không thể chỉ ép địa chỉ native thành `String`: phải xác định **vùng nhớ còn hợp lệ bao lâu**, **có bao nhiêu byte được phép đọc**, **byte nào kết thúc chuỗi**, và **bảng mã nào biến các byte thành ký tự Unicode**.

Bài này giải thích đầy đủ ba phần của một hợp đồng đọc chuỗi C an toàn:

1. **Byte kết thúc:** một C string thông thường là dãy byte kết thúc bằng `'\0'` (byte có giá trị `0x00`). Byte này **không nằm trong nội dung** chuỗi.
2. **Giới hạn chiều dài:** chương trình chỉ được tìm terminator **bên trong vùng nhớ chắc chắn có thể truy cập**, đồng thời không vượt mức giới hạn byte mà ứng dụng cho phép.
3. **Bảng mã:** các byte trước `'\0'` có thể là UTF-8, ISO-8859-1, Windows-1252 hoặc một encoding đã thỏa thuận; Java `String` sử dụng chuỗi ký tự Unicode và không có “bảng mã nội tại” dưới dạng `byte[]`.

Ngữ cảnh của bài là **con trỏ và quyền sở hữu native memory**: đọc đúng byte nhưng sử dụng pointer đã hết lifetime vẫn có thể làm chương trình crash.

Sau khi học, bạn có thể:

- Phân biệt `char *` C, `jstring` JNI, Java `String`, `byte[]` và `MemorySegment`.
- Đọc chuỗi kết thúc NUL bằng vòng quét **có giới hạn thực sự**, không dùng `strlen` trên pointer không rõ độ dài.
- Xử lý dữ liệu không có terminator, terminator xuất hiện sớm, nội dung rỗng, buffer bị cắt và byte sequence sai encoding.
- Phân biệt **UTF-8 thông thường** với **JNI Modified UTF-8** (`NewStringUTF` và `GetStringUTFChars`).
- Biên dịch/chạy ví dụ **Java 17 + JNI C** đọc chuỗi C qua native pointer, copy thành Java `byte[]` và giải mã UTF-8 theo chế độ nghiêm ngặt.
- Hiểu thêm cách `MemorySegment.getString` hoạt động từ **JDK 22+** và khi nào nên dùng một hàm tự quét có bound.
- Thiết kế API native có rõ `pointer + accessibleLength + encoding + ownership`.

## 1. Hai cách biểu diễn chuỗi không giống nhau

### 1.1. Chuỗi C thông thường

Trong C, khái niệm *null-terminated byte string* thường là một mảng các `char` với byte `0x00` đánh dấu điểm kết thúc. Ví dụ:

~~~c
const unsigned char name[] = {'H', 'i', '!', 0};
~~~

Bộ nhớ chứa **bốn byte** nhưng nội dung chuỗi chỉ có **ba byte**. Hàm `strlen((const char *)name)` sẽ trả 3 trong ví dụ này vì thực sự có NUL nằm trong mảng hợp lệ.

~~~text
offset       0     1     2     3
byte        0x48  0x69  0x21  0x00
character     H     i     !    \0
payload    [-----------]     terminator
strlen = 3                   total storage = 4 bytes
~~~

Nhưng một giá trị `const char *` đơn độc **không cho biết dung lượng vùng nhớ**, không cho biết bảng mã và cũng không chứng minh có byte kết thúc ở bất kỳ offset nào. `strlen(ptr)` cần tiếp tục quét cho tới NUL; nếu không có NUL trước cuối vùng nhớ hợp lệ, nó có thể đọc vượt allocation và dẫn tới undefined behavior.

### 1.2. Java String

Java `String` là dãy ký tự Unicode được truy cập như các UTF-16 code units (`char`). Java không cần byte `'\0'` để kết thúc chuỗi. Một `String` có thể chứa ký tự U+0000 **ngay ở giữa**:

~~~java
String javaText = "A\u0000B";
System.out.println(javaText.length()); // 3
~~~

Đây là **mảnh Java minh họa**: ký tự U+0000 là thành phần hợp lệ của Java `String`, không có nghĩa chuỗi kết thúc ngay sau chữ A.

Nếu chuyển nó thành C string **kết thúc bằng NUL** bằng một encoding một byte như UTF-8, byte `0x00` ở giữa sẽ bị hàm C dùng terminator coi là cuối chuỗi. Do đó “chuyển `String` thành `char *`” có thể làm mất nội dung nếu API không có length riêng.

### 1.3. Đừng nhầm bốn đơn vị chiều dài

Giả sử chuỗi Unicode `"café"` được mã hóa theo UTF-8:

~~~text
Java String       "café"
Java length()     4 UTF-16 code units
Unicode scalars   c, a, f, é (4 code points)
UTF-8 bytes       63 61 66 C3 A9        = 5 bytes
C string bytes    63 61 66 C3 A9 00     = 6 bytes, gồm NUL
~~~

Với ký tự emoji nằm ngoài Basic Multilingual Plane như `"😀"`, `String.length()` trả 2 vì surrogate pair, trong khi UTF-8 thông thường biểu diễn ký tự bằng 4 byte. Không lấy `String.length()` làm dung lượng buffer C khi encoding có byte-length thay đổi.

| Đơn vị | API/khái niệm | Có bao gồm NUL? |
|---|---|---|
| Java UTF-16 code units | `String.length()` | Không dùng terminator; U+0000 có thể là nội dung |
| Unicode code points | `codePointCount(...)` | Không phải byte-length |
| Payload bytes theo encoding | `str.getBytes(charset).length` | Không tự thêm C NUL |
| Độ dài C string | `strlen(ptr)` **nếu pointer hợp lệ và có NUL** | Không |
| Storage cần cho UTF-8 C string | số byte payload + 1 | Có, thêm byte `0x00` |
| Buffer capacity | kích thước allocation mà pointer có quyền truy cập | Phải đủ chứa payload **và** terminator |

## 2. Quy tắc truy cập bộ nhớ trước khi đọc chuỗi

Một con trỏ C chỉ an toàn để đọc khi đáp ứng đồng thời các điều kiện:

1. Pointer **khác `NULL`** hoặc API có quy tắc riêng cho null; không dereference pointer null.
2. Pointer trỏ tới một allocation/buffer **còn sống** và có quyền đọc.
3. Người gọi biết **số byte có thể đọc hợp lệ kể từ pointer**; không tự đoán capacity từ kiểu `char *`.
4. Không có thread khác giải phóng hoặc thay đổi bộ nhớ một cách trái hợp đồng trong lúc đang quét.
5. Vùng ký tự được đọc theo đúng giao thức: C string thì phải có terminator trong bound; một buffer binary với length riêng thì **không** nhất thiết có terminator.
6. Sau khi đọc xong, phần memory phải được release bằng **đúng API của chủ sở hữu**, không mặc định `free`.

### 2.1. Bốn dữ kiện cần có

Một hợp đồng đủ rõ:

~~~text
pointer:        const unsigned char *data
accessibleSize: 64 bytes (theo allocation/API của SDK)
maxScanBytes:   32 bytes (giới hạn nghiệp vụ, tính cả terminator)
encoding:       UTF-8
ownership:      borrowed, còn sống cho tới khi return khỏi callback
~~~

Ứng dụng chỉ được đọc tối đa:

~~~text
scanLimit = min(accessibleSize, maxScanBytes)
~~~

Nếu thấy `0x00` trước `scanLimit`, payload chính là các byte trước NUL. Nếu **không** thấy NUL trong giới hạn, phải từ chối hoặc báo trạng thái **TRUNCATED/UNTERMINATED** theo hợp đồng. Không đọc byte kế tiếp để “xem thử”.

**Giới hạn cấu hình không chứng minh bộ nhớ tồn tại.** Việc đặt `maxScanBytes=4096` không cho phép đọc 4096 byte từ một pointer trỏ tới allocation chỉ có 12 byte. `strnlen(ptr, 4096)` hoặc `memchr(ptr, 0, 4096)` cũng có thể vượt bounds nếu 4096 byte chưa được chứng minh là accessible.

### 2.2. Vòng quét có kiểm tra cả hai giới hạn

~~~c
#include <stddef.h>

static int find_c_string_length(
        const unsigned char *data,
        size_t accessible,
        size_t policy_limit,
        size_t *payload_bytes) {

    if (data == NULL || payload_bytes == NULL ||
        accessible == 0 || policy_limit == 0) {
        return 0;
    }

    size_t limit =
            accessible < policy_limit ? accessible : policy_limit;

    size_t i = 0;
    while (i < limit && data[i] != (unsigned char)0) {
        ++i;
    }

    if (i == limit) {
        return 0;  /* Không tìm thấy NUL trong vùng được phép. */
    }

    *payload_bytes = i;
    return 1;      /* Success, kể cả chuỗi rỗng i == 0. */
}
~~~

Đây là **hàm C11 độc lập**. Nó chỉ an toàn khi caller bảo đảm `data` trỏ tới ít nhất `accessible` byte hợp lệ trong suốt lời gọi. Giới hạn `policy_limit` có thể nhỏ hơn `accessible` để tránh đọc dữ liệu quá dài hoặc vượt hạn mức ứng dụng.

**Thứ tự trong điều kiện `while` quan trọng:** C sử dụng short-circuit cho `&&`, nên `data[i]` chỉ được đọc sau khi `i < limit` đúng. Với `i == limit`, code không chạm vào phần tử ngoài phạm vi.

Nếu payload rỗng, byte đầu tiên là `0x00`, `i = 0` và hàm thành công. Nếu `limit` bằng đúng số byte payload nhưng **không chứa terminator**, hàm báo lỗi thay vì trả một chuỗi “đã đọc đủ” không được kết thúc.

### 2.3. Dùng memchr thay vòng lặp?

Khi đã có một bound hợp lệ:

~~~c
#include <string.h>

const unsigned char *end =
        memchr(data, '\0', accessible);

if (end != NULL) {
    size_t payload = (size_t)(end - data);
    /* Dữ liệu kết thúc NUL ở offset payload. */
}
~~~

Đây là **mảnh C minh họa**: `data` phải có đúng kiểu con trỏ và thực sự có ít nhất `accessible` byte hợp lệ. Nếu có thêm `maxScanBytes`, hãy truyền `min(accessible,maxScanBytes)` vào `memchr`. `memchr` tìm byte, còn `strnlen` là hàm thường thấy trên POSIX, **không phải API bắt buộc của ISO C11**; cả hai không thể sửa lỗi pointer invalid hoặc bound bị khai khống.

## 3. Bảng mã: các byte không tự biến thành ký tự Unicode

C `char *` thường chứa byte; một chuỗi byte có thể đại diện cho:

- **UTF-8:** mã hóa Unicode độ dài biến đổi, tương thích ASCII cho các ký tự U+0000–U+007F.
- **ISO-8859-1 (Latin-1):** ánh xạ một byte thành một ký tự trong tập ký tự cố định.
- **Windows-1252:** bảng mã 8-bit tương tự Latin-1 ở nhiều vị trí nhưng khác đáng kể vùng byte `0x80–0x9F` (ví dụ `0x80` là ký hiệu euro).
- **US-ASCII:** chỉ định nghĩa dải 0–127; byte ngoài dải phải được xử lý theo chính sách decoder.
- **Encoding do thư viện định nghĩa:** SDK có thể ghi rõ locale-dependent encoding, OEM code page, EBCDIC hoặc dữ liệu thực ra không phải chuỗi.

Không có một encoding chuẩn được đảm bảo cho mọi `char *` trong C. **Phải đọc tài liệu API**; cách gọi chung chung “ANSI string” không đủ xác định encoding xuyên Windows/Linux/macOS.

### 3.1. UTF-8 và giới hạn theo byte

Ví dụ chuỗi `"café"`:

~~~text
UTF-8 payload: c  a  f   é
hex:          63 61 66 C3 A9
C buffer:     63 61 66 C3 A9 00
max=6         đọc thành công 5 bytes trước NUL
max=5         không thấy NUL → lỗi, dù 5 payload bytes hợp lệ
max=4         không thấy NUL; còn cắt giữa ký tự é
~~~

Một giới hạn 5 byte **không** phải là giới hạn 5 ký tự. Khi quét, phải tính cả terminator vào số byte được phép đọc. Khi decoder xử lý UTF-8, nếu vô tình cắt byte giữa multibyte sequence, lỗi encoding có thể xuất hiện; đừng âm thầm coi chuỗi bị cắt là hoàn chỉnh.

### 3.2. Java decoder nghiêm ngặt

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public static String utf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Đây là **một method Java** có thể đưa vào class Java 17+. Nó làm việc trên **payload bytes đã được tách khỏi C pointer**, không cần byte `0x00` kết thúc.

Nếu byte sequence không hợp lệ với UTF-8, `CharsetDecoder` dùng `CodingErrorAction.REPORT` sẽ ném `CharacterCodingException` (cụ thể có thể là `MalformedInputException`). Ngược lại, constructor `new String(bytes, StandardCharsets.UTF_8)` có thể **thay thế** byte sequence không hợp lệ bằng ký tự thay thế; điều đó có thể chấp nhận với UI text nhưng không phù hợp khi cần phát hiện dữ liệu hỏng hay giao thức nghiêm ngặt.

### 3.3. Latin-1 và Windows-1252 không giống UTF-8

Một byte `0xE9` trong ISO-8859-1 biểu diễn ký tự `é`. Trong UTF-8, ký tự đó phải dùng **hai byte `0xC3 0xA9`**. Nếu decode byte `0xE9` đơn lẻ bằng UTF-8 strict, sẽ có lỗi. Nếu bạn dùng decode replacement, có thể xuất hiện ký tự `�`, khiến dữ liệu có vẻ “rác”.

Với Windows-1252, byte `0x80` được hiểu là `€`, trong khi ISO-8859-1 dùng code point kiểm soát ở vị trí tương ứng. Do đó không dùng `StandardCharsets.ISO_8859_1` thay cho `Charset.forName("windows-1252")` khi SDK đã ghi rõ Windows-1252.

## 4. JNI Modified UTF-8 không phải UTF-8 thông thường

JNI có các API:

~~~c
jstring NewStringUTF(JNIEnv *env, const char *utf);
const char *GetStringUTFChars(
        JNIEnv *env, jstring string, jboolean *isCopy);
void ReleaseStringUTFChars(
        JNIEnv *env, jstring string, const char *utf);
~~~

Các chữ ký trên là **mẫu mô tả JNI C interface**. `NewStringUTF` nhận chuỗi byte **Modified UTF-8 (MUTF-8) có NUL terminator**. `GetStringUTFChars` trả một chuỗi MUTF-8 và phải được ghép đúng `ReleaseStringUTFChars`.

**Modified UTF-8 khác UTF-8 chuẩn:**

| Trường hợp | UTF-8 thông thường | JNI Modified UTF-8 |
|---|---|---|
| ASCII không chứa NUL | Byte 1:1 giống nhau | Giống nhau |
| U+0000 | Byte `00` | Hai byte `C0 80` để tránh NUL trong payload |
| Ký tự ngoài BMP, ví dụ 😀 | Một chuỗi 4 byte | Mã hóa từng UTF-16 surrogate bằng các nhóm 3 byte (tổng 6 byte) |
| NUL terminator ngoài chuỗi | Có nếu giao thức C yêu cầu | Có cho `NewStringUTF` và chuỗi trả bởi `GetStringUTFChars` |
| Dữ liệu UTF-8 tùy ý từ thư viện C | Hợp lệ nếu decoder UTF-8 chấp nhận | **Không mặc định** là MUTF-8 |

**Không** đưa bất kỳ `const char *` “có vẻ UTF-8” nào vào `NewStringUTF`. Với những byte thông thường như chữ ASCII hoặc một số ký tự BMP, kết quả có thể trông đúng, nhưng khi gặp U+0000, emoji hay dữ liệu sai encoding, hành vi không còn tương đương. Với CheckJNI, một số invalid MUTF-8 có thể bị phát hiện.

Khi nguồn là UTF-8 hoặc Windows-1252 chuẩn, lựa chọn dễ kiểm soát là:

1. Quét NUL có giới hạn dựa trên capacity thật.
2. Copy đúng **payload bytes** thành Java `byte[]`.
3. Dùng `CharsetDecoder` hoặc `new String(bytes, charset)` theo policy.
4. Không ép Java `String` thành MUTF-8 nếu không có hợp đồng rõ ràng.

Nếu muốn tạo `jstring` hoàn toàn trong C mà không đi qua Java decoder, bạn có thể dùng thư viện chuyển mã đúng từ encoding nguồn sang UTF-16, sau đó gọi `NewString(env, jchar*, jsize)`. Phải quản lý số **UTF-16 code units**, không phải số byte; `NewString` không cần terminator C. Đừng cast raw UTF-8 bytes thành `jchar *`.

### 4.1. Hướng chuyển dữ liệu của các hàm

- **C → Java:** `NewStringUTF` chỉ cho MUTF-8, hoặc `NewString` với UTF-16 data; lựa chọn khác là `NewByteArray` + Java Charset decoder.
- **Java → C:** `GetStringUTFChars` trả MUTF-8, không được giả định kết quả là UTF-8 chuẩn. `ReleaseStringUTFChars` phải được gọi ngay khi xong.
- **Java → C UTF-8 chuẩn:** thường encode bằng `string.getBytes(StandardCharsets.UTF_8)`, rồi truyền byte array/FFM memory và length theo API cần. Nếu cần C string, thêm byte NUL **và** kiểm tra nội dung có embedded `0x00` theo chính sách.
- **Java → C UTF-16:** dùng `GetStringChars`/`ReleaseStringChars` với `jchar` và length; không coi đó là `wchar_t *` portable trên mọi OS.

## 5. Ví dụ đầy đủ Java 17 + JNI C: đọc có giới hạn, giải mã theo charset

Ví dụ này cố ý sử dụng dữ liệu native **fixture trong C** để không phụ thuộc vào thư viện bên ngoài và đảm bảo output kiểm tra được. C code có những chuỗi tĩnh với điều kiện khác nhau:

| Fixture ID | Byte nguồn | Đặc điểm |
|---|---|---|
| 0 | `63 61 66 C3 A9 00` | C string UTF-8 hợp lệ: `café` |
| 1 | `41 00 42 00` | NUL xuất hiện sớm: C string nhìn thấy chỉ `A` |
| 2 | `78 79 7A` | Không có byte NUL trong allocation |
| 3 | `C3 28 00` | Có NUL, nhưng payload sai UTF-8 |
| 4 | `63 61 66 E9 00` | C string Latin-1 `café`, không phải UTF-8 |
| 5 | `00` | C string rỗng |

Native method nhận `fixture` và `maxBytes`, **tự biết kích thước mảng C thực tế**, dùng `min(actualSize,maxBytes)` để quét NUL. Nếu terminator không nằm trong bound, hàm ném `IllegalArgumentException`, **không đọc ngoài buffer**.

Hàm native chỉ trả payload bytes (`byte[]`). Java quyết định cách decode theo charset. Mô hình này thể hiện rất rõ trách nhiệm của hai bên:

~~~text
const unsigned char *native_pointer
          |
     known capacity + maxBytes
          |
   bounded search for 0x00
          |
    length of payload bytes
          |
    JNI NewByteArray + copy
          |
        Java byte[]
          |
   CharsetDecoder UTF-8 strict
      hoặc ISO-8859-1 decoder
          |
        Java String
~~~

### 5.1. File `CStringReadDemo.java`

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class CStringReadDemo {

    static {
        System.loadLibrary("cstringread");
    }

    // Trả payload bytes, KHÔNG kèm byte NUL.
    private static native byte[] readCStringBytes(
            int fixture, int maxBytes);

    private static String decodeUtf8Strict(byte[] data)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(data))
                .toString();
    }

    public static void main(String[] args) throws Exception {

        byte[] valid = readCStringBytes(0, 6);
        System.out.println("utf8=" + decodeUtf8Strict(valid));
        System.out.println("payloadBytes=" + valid.length);

        // Byte 0x00 là điểm kết thúc; B nằm sau NUL bị bỏ qua.
        System.out.println(
                "embeddedNul="
                + decodeUtf8Strict(readCStringBytes(1, 4)));

        // Đúng encoding ISO-8859-1: byte E9 là ký tự é.
        System.out.println(
                "latin1="
                + new String(readCStringBytes(4, 5),
                             StandardCharsets.ISO_8859_1));

        // Chuỗi rỗng: NUL ở ngay vị trí đầu tiên.
        System.out.println(
                "emptyLength="
                + decodeUtf8Strict(readCStringBytes(5, 1)).length());

        try {
            readCStringBytes(2, 3); // buffer 3 byte không có NUL
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "missingNul=" + ex.getClass().getSimpleName());
        }

        try {
            // 5 byte payload, nhưng byte NUL nằm ở offset 5.
            readCStringBytes(0, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "limitTooSmall=" + ex.getClass().getSimpleName());
        }

        try {
            decodeUtf8Strict(readCStringBytes(3, 3));
        } catch (CharacterCodingException ex) {
            System.out.println(
                    "invalidUtf8=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Java code phân biệt hai loại lỗi: **không có terminator trong bound** được phát hiện bởi C trước khi copy; **byte sequence không đúng charset** được phát hiện bởi `CharsetDecoder` trong Java sau khi copy.

### 5.2. Sinh header JNI từ source thật

Chạy trên JDK 17 trở lên:

~~~bash
javac -h . CStringReadDemo.java
~~~

Lệnh này tạo `CStringReadDemo.class` và `CStringReadDemo.h`. Giữ file header cùng thư mục với mã C. Native method ở default package có tên JNI được sinh theo class; khi thay package hoặc overload, sinh lại header thay vì tự đoán exported symbol.

### 5.3. File `cstringread.c`

~~~c
#include "CStringReadDemo.h"

#include <stddef.h>
#include <string.h>

/* Các byte nguồn nằm trong static storage: không cần free. */
static const unsigned char TEXT_UTF8[] = {
    'c', 'a', 'f', 0xC3u, 0xA9u, 0
};
static const unsigned char EMBEDDED_NUL[] = {
    'A', 0, 'B', 0
};
static const unsigned char NO_NUL[] = {
    'x', 'y', 'z'
};
static const unsigned char INVALID_UTF8[] = {
    0xC3u, 0x28u, 0
};
static const unsigned char TEXT_LATIN1[] = {
    'c', 'a', 'f', 0xE9u, 0
};
static const unsigned char EMPTY_TEXT[] = {
    0
};

/* Chỉ gọi ở nơi chưa có pending Java exception. */
static void invalid_argument(JNIEnv *env, const char *message) {
    jclass klass = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");

    if (klass == NULL) {
        return; /* Giữ nguyên exception nếu FindClass thất bại. */
    }

    (*env)->ThrowNew(env, klass, message);
    (*env)->DeleteLocalRef(env, klass);
}

JNIEXPORT jbyteArray JNICALL
Java_CStringReadDemo_readCStringBytes(
        JNIEnv *env, jclass declaringClass,
        jint fixture, jint maxBytes) {

    (void)declaringClass;

    const unsigned char *source = NULL;
    size_t accessible = 0;

    switch (fixture) {
        case 0:
            source = TEXT_UTF8;
            accessible = sizeof TEXT_UTF8;
            break;
        case 1:
            source = EMBEDDED_NUL;
            accessible = sizeof EMBEDDED_NUL;
            break;
        case 2:
            source = NO_NUL;
            accessible = sizeof NO_NUL;
            break;
        case 3:
            source = INVALID_UTF8;
            accessible = sizeof INVALID_UTF8;
            break;
        case 4:
            source = TEXT_LATIN1;
            accessible = sizeof TEXT_LATIN1;
            break;
        case 5:
            source = EMPTY_TEXT;
            accessible = sizeof EMPTY_TEXT;
            break;
        default:
            invalid_argument(env, "unknown fixture");
            return NULL;
    }

    if (maxBytes <= 0) {
        invalid_argument(env, "maxBytes must be positive");
        return NULL;
    }

    /* Quy tắc kép: không vượt allocation THẬT,
       và không vượt hạn mức ứng dụng. */
    size_t policy = (size_t)maxBytes;
    size_t limit =
            accessible < policy ? accessible : policy;

    size_t payload = 0;

    while (payload < limit && source[payload] != 0) {
        ++payload;
    }

    if (payload == limit) {
        invalid_argument(
                env, "NUL terminator not found within bound");
        return NULL;
    }

    /*
     * Tất cả fixtures đều <= sizeof(TEXT_UTF8) == 6 byte.
     * Payload <= 5, nên vùng copy trên stack luôn đủ.
     * Không dùng cách này với data tùy ý dài vô hạn.
     */
    jbyte temp[sizeof TEXT_UTF8];

    if (payload != 0) {
        memcpy(temp, source, payload);
    }

    /* Tạo Java byte[], không gồm terminator. */
    jbyteArray result =
            (*env)->NewByteArray(env, (jsize)payload);

    if (result == NULL) {
        return NULL; /* Để JVM xử lý lỗi allocation. */
    }

    if (payload != 0) {
        (*env)->SetByteArrayRegion(
                env, result, 0, (jsize)payload, temp);

        if ((*env)->ExceptionCheck(env)) {
            return NULL;
        }
    }

    return result;
}
~~~

**Tại sao C code này tránh đọc ngoài buffer?**

1. `source` chỉ được chọn từ các mảng tĩnh có độ dài **thật** biết trước bằng `sizeof array`. Không dùng `sizeof pointer` để giả làm capacity.
2. `limit = min(accessible, policy)` bảo đảm vòng quét không đọc ngoài mảng C hay vượt mức mà Java caller cho phép.
3. `payload < limit` được kiểm tra trước `source[payload]`. Nếu chưa thấy NUL, trả lỗi, không gọi `strlen` để tiếp tục.
4. `temp` có kích thước đủ cho fixture lớn nhất, và `payload < limit <= accessible <= 6`. Dữ liệu được copy theo **byte**, không đọc thêm terminator.
5. `NewByteArray` cấp một mảng byte Java có số phần tử bằng payload. `SetByteArrayRegion` copy các byte từ vùng stack C trước khi hàm return.
6. `temp` là stack buffer; Java nhận một `byte[]` độc lập. Không giữ con trỏ stack sau return.
7. `INVALID_UTF8` vẫn vượt qua **bước C quét NUL** vì có terminator hợp lệ; lỗi decode được phát hiện sau đó bởi Java decoder.
8. Khi thiếu NUL, C dùng `ThrowNew` ném `IllegalArgumentException`, return ngay và không tiếp tục gọi JNI ngoài những thao tác cleanup được phép.

**Mở rộng cho production:** nếu nhận buffer lớn từ SDK, không tạo một stack array `jbyte temp[bytes]` tùy theo input. Dùng `SetByteArrayRegion` với buffer đúng kiểu và dung lượng đã kiểm chứng, hoặc copy theo chunk. Luôn kiểm tra payload có thể biểu diễn thành `jsize` và hạn mức `NewByteArray` trước khi cấp phát. Trong ví dụ mọi fixture đều dưới 6 byte nên phép chuyển `size_t → jsize` an toàn.

### 5.4. Biên dịch và chạy thư viện

Các lệnh bên dưới dùng JDK 17+, và compiler đúng OS/CPU/ABI của tiến trình JVM. Chọn **một** nền tảng.

**Linux (GCC):**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  cstringread.c -o libcstringread.so

java -Djava.library.path=. CStringReadDemo
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  cstringread.c -o libcstringread.dylib

java -Djava.library.path=. CStringReadDemo
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" cstringread.c /Fe:cstringread.dll
java -Djava.library.path=. CStringReadDemo
~~~

`System.loadLibrary("cstringread")` dùng tên thư viện logic; JVM tìm tên file theo convention của hệ điều hành. JDK headers phải đúng kiến trúc JVM và thư viện native phải load được; lỗi như `UnsatisfiedLinkError` xảy ra trước khi ví dụ in output.

### 5.5. Stdout mong đợi

~~~text
utf8=café
payloadBytes=5
embeddedNul=A
latin1=café
emptyLength=0
missingNul=IllegalArgumentException
limitTooSmall=IllegalArgumentException
invalidUtf8=MalformedInputException
~~~

Giải thích từng trường hợp:

- UTF-8 hợp lệ: 5 byte payload thành `"café"` (4 ký tự UTF-16 code units).
- `embeddedNul`: byte `0x00` đầu tiên kết thúc C string; chữ `B` nằm sau terminator **không** được copy.
- `latin1`: byte `0xE9` được giải mã đúng là `é` với `ISO_8859_1`.
- `emptyLength`: byte đầu đã là NUL nên payload rỗng.
- `missingNul`: `NO_NUL` không có byte `0x00` trong allocation được quét.
- `limitTooSmall`: chỉ có thể đọc 5 byte payload của UTF-8 fixture, nhưng cần byte thứ 6 là terminator, nên phải báo lỗi.
- `invalidUtf8`: byte `C3 28` không tạo thành UTF-8 hợp lệ, decoder strict ném `MalformedInputException`.

Không có `strlen` trên unknown pointer, không có `NewStringUTF` với raw UTF-8 và không có pointer native nào bị giữ lại sau return.

## 6. Quan hệ giữa maxBytes và buffer capacity

Hai đại lượng này khác nhau:

- **Accessible capacity:** số byte thực sự hợp lệ tính từ con trỏ, do allocation hoặc SDK/OS xác nhận.
- **Policy limit:** mức tối đa ứng dụng cho phép quét, ví dụ để tránh metadata quá lớn hoặc chiếm nhiều RAM.

~~~text
Native buffer thực tế: 32 bytes
Policy maxScanBytes:   12 bytes
NUL tại offset:        7
→ thành công, payload 7 bytes

Native buffer thực tế: 32 bytes
Policy maxScanBytes:   12 bytes
NUL tại offset:        20
→ từ chối, không đọc đến offset 20

Native buffer thực tế: 6 bytes
Policy maxScanBytes:   4096 bytes
NUL không có trong 6 bytes
→ từ chối sau tối đa 6 bytes, không được đọc tới 4096
~~~

**Không bao giờ tăng policy limit để “chữa” một pointer không có NUL** khi chưa biết accessible capacity. Với API trả `const char *` mà **không có length**, chỉ an toàn gọi các hàm kiểu `strlen` khi tài liệu bảo đảm con trỏ chỉ tới C string hợp lệ, được NUL-terminate và còn sống. Nếu nguồn không đáng tin, tốt hơn yêu cầu API có `pointer + byteCount` hoặc tự copy vào một buffer có giới hạn do ứng dụng kiểm soát.

### 6.1. Không thể tự “tính capacity” từ char*

C không có runtime metadata tự động gắn vào mọi pointer. Khi nhận:

~~~c
void consume(const char *ptr);
~~~

`sizeof(ptr)` là kích thước **biến pointer**, không phải số byte allocation mà `ptr` trỏ tới. Chỉ có `sizeof nativeArray` (khi `nativeArray` thực sự là một mảng trong cùng scope) mới trả độ dài mảng theo byte.

Đối với con trỏ do C SDK trả về, kích thước thường đến từ:

- tham số length hoặc capacity đi kèm;
- một struct mô tả buffer;
- một API lấy length có quy ước đáng tin;
- tài liệu đảm bảo NUL trong một số byte cố định;
- wrapper mà **chính ứng dụng** cấp phát, do đó biết chính xác capacity.

Không đoán capacity bằng cách cộng/trừ địa chỉ pointer, nhìn vào terminator tìm được ở vị trí rất xa hoặc quét toàn bộ virtual memory.

### 6.2. Khi cần báo lỗi như thế nào?

Tùy ứng dụng, có thể dùng một trong các trạng thái:

| Trạng thái | Ý nghĩa | Hành vi đề xuất |
|---|---|---|
| `OK` | Tìm được NUL trong bounds, decode hợp lệ | Trả chuỗi |
| `NULL_POINTER` | Pointer null và API không định nghĩa null hợp lệ | Báo lỗi hoặc trả optional theo hợp đồng |
| `NOT_TERMINATED` | Không có NUL trước scanLimit | Báo lỗi, không tự nối byte ngoài bounds |
| `TOO_LONG` | Hạn mức nghiệp vụ chặn trước NUL | Báo lỗi hoặc xử lý chuỗi có length rõ |
| `INVALID_ENCODING` | Byte payload không hợp lệ theo charset | Decoder REPORT hoặc replacement theo chính sách |
| `EXPIRED_POINTER` | Lifetime native đã kết thúc | Không đọc; đây là lỗi ownership nghiêm trọng |
| `INVALID_CAPACITY` | Capacity khai báo không đáng tin/không kiểm chứng | Từ chối API, không cố quét |

Ví dụ runnable dùng `IllegalArgumentException` cho hai tình huống NOT_TERMINATED/TOO_LONG, và `CharacterCodingException` cho INVALID_ENCODING. Một API production có thể dùng exception types hoặc error codes chi tiết hơn.

## 7. Nội dung có byte 0: chuỗi C và dữ liệu binary là hai hợp đồng khác nhau

Nếu nguồn chứa:

~~~text
41 00 42 00
 A \0  B \0
~~~

Một hàm đọc **C string** sẽ trả `"A"`. Nếu toàn bộ bốn byte là **payload binary** cần xử lý, dùng giao thức **pointer + byte length**, không dùng NUL terminator. Java `String` có thể biểu diễn `"A\u0000B"`, nhưng C string thuần không thể giữ U+0000 ở giữa mà vẫn dùng quy tắc kết thúc tại byte 0.

Không “fix” bằng cách bỏ qua mọi byte `0x00`. Việc đó thay đổi nội dung, mất dữ liệu và còn làm hỏng UTF-16/UTF-32 nếu nhầm encoding. Để chứa embedded zero bytes, bạn phải có **length riêng**.

Một số C library trả chuỗi rỗng bằng `""` (một byte NUL), số khác trả `NULL` để biểu diễn “không có giá trị”. Hai trường hợp không tương đương: contract phải phân biệt `null`, empty string và error state.

## 8. Nếu encoding không phải UTF-8

### 8.1. Luôn chỉ định charset khi decode

Trong Java:

~~~java
String utf8 = new String(bytes, StandardCharsets.UTF_8);
String latin1 = new String(bytes, StandardCharsets.ISO_8859_1);
String cp1252 = new String(bytes, java.nio.charset.Charset.forName(
        "windows-1252"));
~~~

Đây là **mảnh Java**, giả định `bytes` đã được copy từ native memory đúng bounds. Ba lệnh có thể trả kết quả khác nhau nếu byte >= `0x80`. Không dùng `new String(bytes)` khi giao thức cần encoding ổn định giữa các máy: lựa chọn charset mặc định phụ thuộc môi trường/JDK và không phải hợp đồng của SDK C.

### 8.2. Decoder với lỗi dữ liệu

Nếu dữ liệu là protocol text bắt buộc hợp lệ, dùng `CharsetDecoder` với `REPORT` như ví dụ. Nếu hiển thị text từ nguồn kém tin cậy, replacement có thể là một chính sách được cân nhắc, nhưng phải ghi rõ rằng có khả năng **mất thông tin**.

Với UTF-8, decoder strict cũng phát hiện các byte continuation sai, overlong encodings và sequence không hợp lệ. Nó không “sửa” encoding sai bằng cách thử random charsets. Nếu phát hiện nhiều dữ liệu bị mojibake, trước tiên xác minh encoding được nhà cung cấp khai báo.

### 8.3. Không áp dụng vòng quét byte 0 cho UTF-16/UTF-32

Một `wchar_t*` không nhất thiết là UTF-16. Trên Windows thường 16 bit; trên nhiều Unix-like platforms `wchar_t` thường 32 bit. Một “wide C string” dùng **zero code unit** ở độ rộng tương ứng, không phải “byte đầu tiên bằng zero”.

Với UTF-16LE, ký tự ASCII `A` là cặp byte `41 00`; dùng `memchr(buffer, 0, capacity)` sẽ nhìn thấy byte zero ngay ở offset 1 và tưởng chuỗi kết thúc, dẫn đến đọc sai. Phải chọn loại code unit, byte order, alignment và khả năng tiếp cận bộ nhớ theo đúng API; dùng length hay width-aware terminator scan.

Dữ liệu có BOM không tự bảo đảm đúng encoding. Nếu SDK nói UTF-16LE, không được lấy `char*` 8-bit và decode như UTF-8 chỉ vì hệ thống đang dùng Unicode.

## 9. Ownership: chuỗi C mượn và chuỗi C sở hữu

### 9.1. Borrowed pointer

Một hàm C có thể trả con trỏ tới bộ nhớ **do thư viện sở hữu**, ví dụ metadata nội bộ:

~~~c
const char *get_error_text(void);
~~~

Nếu tài liệu nói pointer có hiệu lực đến **lần gọi API kế tiếp**, bạn phải copy bytes trong khoảng đó; không cache pointer trong Java dưới dạng `long` rồi giải mã sau. Nếu thư viện có thread khác thay đổi cùng buffer, phải tuân thủ locking/API contract.

Không `free` borrowed pointer, và không dùng `ReleaseStringUTFChars` cho pointer không phải do `GetStringUTFChars` tạo ra.

### 9.2. Owned pointer

Một API khác có thể trả buffer đã cấp phát và chuyển ownership cho caller:

~~~c
char *make_error_text(void);
void release_error_text(char *ptr);
~~~

Nếu có `release_error_text`, phải gọi đúng hàm đó sau khi copy, kể cả khi tạo Java `byte[]` hoặc decoder thất bại. Không tự thay bằng `free` nếu tài liệu không cho phép. Một con trỏ do C++ `new[]` tạo phải được hủy theo đúng allocator/deallocator; một con trỏ từ SDK thường phải release qua SDK.

### 9.3. JNI object reference khác pointer C

`jstring` và `jbyteArray` là JNI object references do JVM quản lý; `jbyteArray result` trong ví dụ là local reference được trả về Java. `source` trong ví dụ là native pointer tới static memory và không phải JNI reference.

Hàm `DeleteLocalRef` chỉ quản lý JNI local references. Nó **không** giải phóng native `malloc`. Ngược lại `free` không được dùng trên `jbyteArray` hoặc `jstring`.

### 9.4. Không giữ stack pointer sau return

Nếu C code trả pointer tới một mảng local:

~~~c
const char *wrong(void) {
    char temp[] = "hello";
    return temp; /* SAI: lifetime của temp kết thúc khi return. */
}
~~~

Đây là **anti-pattern C**, không được sử dụng. Pointer trở thành dangling ngay khi hàm kết thúc. Java wrapper không thể sửa bằng cách “scan NUL nhanh hơn” sau return. Lựa chọn đúng là copy dữ liệu khi nguồn còn sống, dùng static storage theo hợp đồng, hoặc cấp phát vùng sở hữu có release function rõ.

## 10. Java 22+ FFM: MemorySegment.getString và giới hạn vùng

Từ JDK 22, `MemorySegment` có các phương thức:

~~~java
String getString(long byteOffset);
String getString(long byteOffset, java.nio.charset.Charset charset);
~~~

`getString(offset)` sử dụng **UTF-8**; overload nhận charset cho phép chỉ định encoding. Nó đọc một **null-terminated string** từ segment bắt đầu ở byte offset đã cho, trong giới hạn mà segment mô tả. **Nó không tạo một giới hạn policy tùy ý cho bạn** nếu segment quá lớn; muốn ràng buộc số byte, cần dựng một view có size giới hạn hoặc tự quét như phần đầu.

Đặc tả `getString(offset, charset)` nói rằng dữ liệu lỗi encoding được **thay thế** bằng replacement string; nếu cần báo lỗi nghiêm ngặt, hãy đọc các byte hợp lệ trong bound rồi dùng `CharsetDecoder` với `REPORT`.

### 10.1. Ví dụ chạy được JDK 22+ (không dùng C)

File `CStringFfmDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.charset.StandardCharsets;

public final class CStringFfmDemo {
    public static void main(String[] args) {
        byte[] cString = {
                'c', 'a', 'f', (byte) 0xC3, (byte) 0xA9, 0
        };

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeMemory = arena.allocate(cString.length);

            for (int i = 0; i < cString.length; i++) {
                nativeMemory.set(
                        ValueLayout.JAVA_BYTE, (long) i, cString[i]);
            }

            System.out.println(
                    "ffm=" + nativeMemory.getString(
                            0L, StandardCharsets.UTF_8));
            System.out.println("native=" + nativeMemory.isNative());
        }
    }
}
~~~

Chạy với JDK 22 hoặc mới hơn:

~~~bash
javac CStringFfmDemo.java
java CStringFfmDemo
~~~

Stdout mong đợi:

~~~text
ffm=café
native=true
~~~

Ở đây vùng nhớ native có **6 byte** và NUL ở offset 5. `getString` đọc đến NUL rồi decode theo UTF-8. Arena kiểm soát lifetime: sau khi `try` kết thúc, không được truy cập segment cũ dù biến Java còn tham chiếu đến nó.

### 10.2. Tại sao cần slice nếu có max length?

Giả sử một SDK cung cấp một segment 4096 byte nhưng giao thức cho phép chuỗi tối đa 32 byte **gồm terminator**. Không gọi `segment.getString(0)` trên toàn bộ 4096 byte rồi mới kiểm tra `str.length()`: thao tác đó có thể quét/giải mã quá giới hạn nghiệp vụ.

Thay vào đó, tạo một **slice có bound đúng**:

~~~java
long maxScanBytes = 32L;
long allowed = Math.min(segment.byteSize(), maxScanBytes);
MemorySegment bounded = segment.asSlice(0L, allowed);

// bounded.getString(0L, StandardCharsets.UTF_8):
// sẽ không được phép đọc vượt byteSize() của bounded.
~~~

Đây là **mảnh Java minh họa** trong method đã có `segment` còn sống, accessible và `maxScanBytes` hợp lệ. Nếu không có NUL trong slice, hãy xử lý lỗi bounds theo API, **không mở rộng scan tự động**.

**Giới hạn này chỉ có giá trị nếu `segment.byteSize()` thực sự mô tả vùng nhớ accessible.** Dùng `reinterpret` để “tự khai” con trỏ thô có 4096 byte khi thật sự chỉ có 12 byte là nguy hiểm; restricted FFM APIs không thể tự biết allocation thật hay lifetime của SDK C.

### 10.3. Khi cần strict decoding và trạng thái lỗi riêng

Với một segment đã biết valid bounds, tự quét byte từng bước rồi copy payload sang Java `byte[]`, sau đó gọi `CharsetDecoder`. Phương pháp đó giúp phân biệt rõ:

- không thấy NUL trong bound;
- byte payload hợp lệ nhưng encoding lỗi;
- pointer/segment hết lifetime;
- chuỗi vượt hạn mức ứng dụng.

Không cố suy ra từng loại lỗi chỉ bằng một lời gọi `getString`, vì overload này có chính sách **replacement** đối với malformed bytes. Với encoding nhiều byte có terminator là nhiều byte, cần áp dụng đúng hợp đồng của charset/FFM, không dùng logic kiểm tra byte 0 đơn lẻ cho mọi encoding.

## 11. Các lỗi phổ biến và cách sửa

| Sai lầm | Rủi ro | Cách đúng |
|---|---|---|
| Gọi `strlen(ptr)` khi không biết vùng nhớ và NUL | Đọc vượt allocation, undefined behavior | Yêu cầu contract có capacity + terminator hoặc length |
| Gọi `strnlen(ptr, 4096)` trên buffer thực tế 8 byte | Vẫn có thể đọc vượt 8 byte | `min(accessibleCapacity, policyLimit)` |
| Coi `sizeof(ptr)` là dung lượng buffer | Thường chỉ là 4/8 byte địa chỉ | Lấy size từ mảng thật/API riêng |
| Coi max length là “số ký tự” | UTF-8 nhiều byte, Java UTF-16 length khác | Định nghĩa limit **theo byte** |
| Không tính byte terminator | Chấp nhận buffer thiếu NUL hoặc ghi vượt | Storage cần payload bytes + 1 cho UTF-8 C string |
| Đọc qua byte `0x00` ở giữa | Đọc dữ liệu không thuộc C string | Dừng tại NUL đầu tiên, hoặc dùng length protocol nếu cần binary |
| Truyền UTF-8 tùy ý vào `NewStringUTF` | JNI yêu cầu Modified UTF-8 | Decode bytes rõ charset, hoặc chuyển sang UTF-16 rồi `NewString` |
| Cho rằng `GetStringUTFChars` trả UTF-8 chuẩn | Có thể khác ở U+0000, supplementary | Xử lý như MUTF-8 và Release đúng API |
| Dùng `new String(bytes)` không chỉ định charset | Encoding phụ thuộc runtime policy, dễ mojibake | Chỉ định `StandardCharsets.UTF_8`/charset của SDK |
| Decode lỗi bằng replacement trong protocol nghiêm ngặt | Âm thầm làm mất thông tin | `CharsetDecoder` + `CodingErrorAction.REPORT` |
| Giải mã `0xE9` Latin-1 như UTF-8 | Lỗi malformed bytes | Dùng charset được tài liệu SDK xác nhận |
| Quét byte 0 trong UTF-16LE | Byte 0 có thể nằm giữa code unit bình thường | Dùng code unit width và byte order đúng |
| Dùng pointer sau callback/native return | Dangling pointer/UAF | Copy khi lifetime còn hợp lệ, không cache borrowed pointer |
| `free` borrowed/static pointer | Crash/double free | Chỉ free/release khi ownership contract yêu cầu |
| Dùng `DeleteLocalRef` để giải phóng malloc pointer | Không liên quan | `DeleteLocalRef` cho JNI ref; `free`/SDK release cho native |
| Tin rằng FFM `getString` tự giới hạn theo policy | Quét tới NUL trong toàn bộ segment | Dùng `asSlice` hoặc bounded scan |
| Bỏ qua ngoại lệ JNI sau `NewByteArray`/`SetByteArrayRegion` | Tiếp tục xử lý trên trạng thái lỗi | Kiểm tra `NULL`/`ExceptionCheck` và dừng |
| Chuyển length `size_t` lớn sang `jsize` không kiểm tra | Tràn/đổi dấu, allocation lỗi | Kiểm tra giới hạn đại diện trước khi `NewByteArray` |
| Đưa C pointer dưới dạng Java `long` rồi dùng sau close | Không có kiểm tra lifetime native tự động | Có owner, lease và release protocol rõ |
| Đoán encoding theo OS/locale | Chạy đúng trên máy này, lỗi máy khác | Ghi encoding thành phần hợp đồng API |

## 12. Kiểm thử cần thiết trước khi đưa vào sản phẩm

Kiểm thử ít nhất các trường hợp:

1. Chuỗi ASCII có terminator đúng ở cuối buffer.
2. Chuỗi UTF-8 có ký tự nhiều byte, ví dụ `é`, emoji.
3. Chuỗi rỗng: byte đầu tiên `0x00`.
4. Embedded NUL: xác định chính sách cắt ở NUL hoặc dùng length protocol.
5. Không có NUL trong toàn bộ allocation.
6. NUL nằm tại byte cuối của `maxScanBytes`: **hợp lệ**.
7. NUL nằm **ngay ngoài** `maxScanBytes`: **không hợp lệ**.
8. Max length 0, âm, quá lớn, và các byte lengths sắp vượt giới hạn Java array.
9. Invalid UTF-8: byte continuation sai, chuỗi multibyte bị cắt, overlong byte sequence.
10. Legacy encodings: phân biệt Latin-1 và Windows-1252.
11. Pointer null, dangling hoặc ownership contract không rõ: từ chối thay vì đoán.
12. Native pointer do SDK sở hữu chỉ hợp lệ đến callback return: copy trước khi return.
13. Mã JNI có pending exception giữa việc copy: cleanup và return đúng.
14. Worker khác có thể sửa/free cùng buffer: lock hoặc snapshot/ownership đúng.
15. FFM segment sau `Arena.close()`: không truy cập lại và không giữ raw pointer.
16. Các trường hợp input lớn: không cấp stack memory theo độ dài không giới hạn; giới hạn cả scanning và allocation.

### Quy tắc review hữu ích

Khi review một hàm chuyển từ `char *` sang Java `String`, hãy yêu cầu người viết trả lời **bằng chứng cụ thể** cho:

- Con trỏ còn sống trong bao lâu và ai được phép release?
- Có bao nhiêu byte thực sự accessible từ vị trí bắt đầu?
- Giới hạn policy là bao nhiêu byte, có gồm terminator không?
- Có byte NUL không; nếu không thì phải báo gì?
- Payload encoding là gì; dùng decoder replacement hay REPORT?
- Có thể có embedded NUL không; nếu có thì API có length riêng không?
- Copy đã hoàn tất trước khi nguồn hết lifetime chưa?
- JNI reference/FFM scope và native ownership được dọn đúng không?

Một câu trả lời kiểu “C string nào cũng UTF-8 và strlen luôn an toàn” là dấu hiệu cần sửa thiết kế API.

## 13. Bài tập tự luyện có đáp án

**Bài 1 — tính byte length.** Chuỗi `"café"` theo UTF-8 cần tối thiểu bao nhiêu byte lưu dưới dạng C string? **6 byte**, gồm 5 payload bytes và 1 byte NUL. `String.length()` trong Java trả **4**, không phải 5 hoặc 6.

**Bài 2 — NUL không nằm trong giới hạn.** Buffer thực tế 6 byte `63 61 66 C3 A9 00` nhưng `maxScanBytes=5`. Có được trả `"café"` không? **Không**, vì byte NUL ở offset 5 nằm ngoài đoạn được quét [0,5). Nếu hợp đồng yêu cầu C string, phải báo lỗi thiếu terminator trong bound.

**Bài 3 — chuỗi rỗng.** Buffer có một byte `0x00`; `maxScanBytes=1`. Đọc thành công không? **Có**, payload length = 0, Java nhận `""`.

**Bài 4 — dữ liệu binary.** Buffer `41 00 42` có ba byte payload, nhưng hàm dùng C string. Kết quả đọc là gì? **`"A"`**, không phải `"A\u0000B"`. Muốn giữ cả ba byte cần API có explicit length, không dùng NUL string protocol.

**Bài 5 — sai encoding.** Một byte `E9` theo Latin-1 là `é`. Nếu decode strict UTF-8 thì sao? Byte `E9` đơn lẻ không tạo thành UTF-8 hợp lệ, decoder báo `MalformedInputException` hoặc một dạng `CharacterCodingException`.

**Bài 6 — UTF-8 và Modified UTF-8.** Vì sao không thể luôn truyền UTF-8 từ C vào `NewStringUTF`? Vì JNI yêu cầu **Modified UTF-8**, khác ở U+0000 và supplementary characters như emoji.

**Bài 7 — borrowed pointer.** SDK trả pointer hợp lệ chỉ đến lần gọi API kế tiếp. Có thể lưu pointer dưới dạng `long` rồi dùng trong Java callback tương lai không? **Không**, phải copy khi pointer còn sống hoặc sử dụng giao thức retain/lifetime được SDK hỗ trợ.

**Bài 8 — strnlen.** Một pointer được chứng minh truy cập được 7 byte, bạn gọi `strnlen(ptr, 1024)`. Có an toàn không? **Không được bảo đảm**; vẫn có thể quét quá 7 byte nếu không thấy NUL. Limit phải không lớn hơn accessible capacity.

**Bài 9 — UTF-16LE.** Vì sao không dùng `memchr(bytes, 0, max)` để tìm hết chuỗi UTF-16LE? Vì một byte 0 có thể xuất hiện trong biểu diễn của ký tự bình thường; phải tìm **zero code unit** ở đúng độ rộng/byte order.

**Bài 10 — FFM.** Một `MemorySegment` dài 4096 byte chứa NUL ở offset 200, nhưng policy chỉ cho 64 byte. Có nên gọi `segment.getString(0)` trên toàn segment rồi kiểm tra string length? **Không**. Cần giới hạn view/scan tối đa 64 byte và từ chối khi không thấy terminator trong bound.

## Tài liệu tham chiếu

- [Oracle Java SE 17 — JNI types: Modified UTF-8](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): quy tắc MUTF-8 và khác biệt với UTF-8 thông thường.
- [Oracle Java SE 17 — JNI functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewStringUTF`, `NewString`, `GetStringUTFChars`, `ReleaseStringUTFChars`, `NewByteArray`, `SetByteArrayRegion` và xử lý JNI exception.
- [Oracle Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): các chính sách `REPORT`, `REPLACE`, `IGNORE`.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, ISO-8859-1 và các charsets chuẩn.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `getString(offset, charset)`, access bounds, lifetime và quản lý vùng nhớ native.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): Java `java.lang.foreign` ổn định từ JDK 22.

## Ghi nhớ

**Đọc C string an toàn đòi đủ bốn thông tin: `pointer + số byte thực sự accessible + bảng mã + ownership/lifetime`.** Giới hạn ứng dụng là lớp bảo vệ bổ sung chứ **không chứng minh allocation có đủ byte**.

Thứ tự nên làm:

1. Kiểm tra pointer hợp lệ và còn lifetime, biết capacity thật.
2. Quét byte NUL trong `min(capacity, maxScanBytes)`, **không đọc vượt**.
3. Nếu không thấy NUL trong bound, trả lỗi chứ không đoán.
4. Copy đúng payload bytes khi nguồn còn sống.
5. Decode với charset được khai báo, dùng strict decoder khi cần phát hiện dữ liệu hỏng.
6. Release pointer theo owner/SDK đúng hợp đồng; Java `byte[]`/`String` sau copy không còn phụ thuộc source native.
7. Đừng lẫn UTF-8 thông thường với **JNI Modified UTF-8**, và đừng dùng byte NUL terminator cho binary/UTF-16 data có định dạng khác.

**Một câu cần nhớ:** `strlen` không làm một pointer thành an toàn; chỉ một hợp đồng rõ về **bounds, encoding và lifetime** mới cho phép đọc và chuyển C string sang Java đúng cách.
