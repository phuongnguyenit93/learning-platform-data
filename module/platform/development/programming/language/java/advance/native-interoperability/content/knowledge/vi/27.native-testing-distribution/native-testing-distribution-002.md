# Kiểm thử giá trị biên, null, Unicode, vùng đệm ngắn và tràn số kích thước khi tương tác Java–native

## Mục tiêu

Khi Java giao tiếp với C/C++ qua **Foreign Function & Memory API (FFM)** hoặc **JNI**, nhiều lỗi nghiêm trọng không xuất hiện ở “đường chạy đúng” mà ở đầu vào đặc biệt: số lượng bằng 0, địa chỉ `NULL`, chuỗi nhiều byte, buffer thiếu 1 byte, hoặc số byte cần cấp phát bị tràn trước khi gọi native. Bài này hướng dẫn xây dựng **hợp đồng dữ liệu**, bộ ca kiểm thử biên, ví dụ Java 22+ có thể chạy độc lập và cách kiểm chứng phần native thật bằng công cụ phát hiện lỗi bộ nhớ.

Sau bài học, bạn cần làm được:

1. Phân biệt `null` của Java, con trỏ C `NULL` và chuỗi C rỗng; chọn cách xử lý nhất quán và viết test cho từng trường hợp.
2. Tính đúng **độ dài theo byte** của dữ liệu UTF-8, chỗ dành cho ký tự kết thúc `NUL`, và nhận diện dấu `NUL` nằm giữa nội dung.
3. Xác định biên hợp lệ của `offset`, `length`, `capacity`, vùng đệm thiếu và vùng đệm vừa đủ; kiểm tra điều kiện không ghi quá giới hạn.
4. Phòng tràn khi tính `count * elementSize + overhead`, tránh thu hẹp kiểu số im lặng và đối chiếu C `size_t`/`jsize` với chữ ký Java.
5. Kết hợp test Java, test C, sanitizer, kiến trúc 32/64-bit và kiểm thử hồi quy mà không đánh đồng bảo đảm của `MemorySegment` với bảo đảm của thư viện native.

**Phạm vi phiên bản:** Ví dụ `java.lang.foreign` áp dụng cho **JDK 22 trở lên** (FFM được chuẩn hóa trong JDK 22). Chúng chỉ sử dụng các thao tác memory segment an toàn ở phía Java, không gọi hàm C, nên **không cần** `--enable-native-access`. Phần tích hợp downcall thực tế là thao tác restricted và cần cờ/chính sách native access phù hợp phiên bản JDK.

## 1. Định nghĩa hợp đồng trước khi viết ca kiểm thử

Một chữ ký C điển hình:

```c
int process_bytes(const unsigned char *src,
                  size_t src_len,
                  unsigned char *dst,
                  size_t dst_capacity,
                  size_t *written);
```

Trước khi kiểm thử, cần có câu trả lời rõ cho từng trường:

| Trường | Ý nghĩa | Câu hỏi cần chốt trong API contract |
| --- | --- | --- |
| `src` | Con trỏ vào buffer đầu vào | `NULL` có được chấp nhận khi `src_len == 0`? |
| `src_len` | **Số byte** hợp lệ ở `src` | Có tính `NUL` của chuỗi C không? Có được bằng 0 không? |
| `dst` | Con trỏ vào buffer đầu ra | `NULL` có được dùng để truy vấn dung lượng cần thiết không? |
| `dst_capacity` | Số byte **thực sự có thể ghi** tại `dst` | Nếu thiếu, trả status gì? Có ghi một phần không? |
| `written` | Số byte đã ghi hoặc số byte cần cấp phát, theo contract | Trong lỗi thì có về 0 không? Đơn vị có phải byte không? |
| Kết quả `int` | Mã trạng thái | Âm/dương/0 có nghĩa gì? Có thể được gọi lặp lại an toàn không? |

Không thể tự suy ra các quy tắc trên chỉ từ tên hàm. **Hợp đồng phải nói rõ**: có yêu cầu NUL-terminated hay dùng `pointer + length`; số byte trả về bao gồm NUL không; buffer ngắn trả lỗi/truncation/required size; con trỏ và bộ nhớ do bên nào sở hữu và giải phóng.

Bốn khái niệm rất dễ nhầm:

- **Java `null`**: không có đối tượng tham chiếu; có thể gây `NullPointerException` khi Java code cố sử dụng nó. Một wrapper có thể chủ động từ chối `null` bằng `Objects.requireNonNull`.
- **FFM `MemorySegment.NULL`**: đối tượng `MemorySegment` đại diện **địa chỉ native bằng 0**, có kích thước 0, thường dùng khi một tham số C cho phép con trỏ `NULL`. Nó khác Java `null`; `MemorySegment.NULL.get(...)` không phải thao tác đọc bộ nhớ hợp lệ.
- **Chuỗi C rỗng `""`**: có một byte kết thúc `0x00` khi mã hóa thành UTF-8 NUL-terminated; khác con trỏ `NULL` và khác một vùng đệm độ dài 0.
- **Buffer dung lượng 0**: có thể là yêu cầu hợp lệ trong API nhị phân (không dữ liệu), hoặc dùng để hỏi dung lượng cần thiết. Đừng mặc định thư viện native cho phép `NULL, 0` nếu contract không ghi rõ.

Nếu API sử dụng `pointer + length` và cho phép byte `0x00` ở giữa, hãy kiểm thử dữ liệu nhị phân theo đúng `length`, thay vì gọi `strlen`/`getString` và vô tình cắt dữ liệu tại NUL.

## 2. Ma trận ca kiểm thử bắt buộc

| Nhóm | Đầu vào/ranh giới | Điều cần xác nhận |
| --- | --- | --- |
| Độ dài | `0`; `1`; `capacity - 1`; `capacity`; `capacity + 1` | Trạng thái, độ dài trả về, không đọc/ghi ngoài phạm vi |
| Offset | `-1`; `0`; `capacity - 1`; `capacity`; `capacity + 1` | `offset == capacity` chỉ hợp lệ cho thao tác **0 byte**, không hợp lệ khi cần đọc/ghi ít nhất 1 byte |
| Null | Java `null`; `MemorySegment.NULL`; segment rỗng; chuỗi `""` | Đúng chính sách đầu vào; không dereference NULL hoặc thay NULL bằng chuỗi rỗng |
| Unicode | ASCII; `é`; tiếng Việt; CJK; emoji ngoài BMP; ký tự kết hợp | Tròn dữ liệu theo đúng charset; so **byte length** với **UTF-16 char length** |
| Byte NUL nhúng | `"A\u0000B"` (Java string) hoặc `{65, 0, 66}` (byte[]) | Với C string, kết quả thường chỉ `"A"`; với dữ liệu có length, phải giữ đủ 3 byte |
| Unicode bất hợp lệ | Surrogate đơn lẻ; chuỗi byte UTF-8 sai | Reject rõ ràng hoặc replacement theo hợp đồng; không âm thầm nhận định round-trip đúng |
| Buffer ngắn | Thiếu 1 byte so với payload; thiếu NUL; buffer 0 | Lỗi/truncation/required-size đúng tài liệu; canary không đổi |
| Tràn kích thước | `count * stride`; cộng header/NUL; chuyển `long` → `int` | Phát hiện tràn **trước** cấp phát/copy; không yêu cầu cấp bộ nhớ khổng lồ để tạo test |
| ABI/cross-platform | `size_t` 32/64-bit; pointer 32/64-bit; signed/unsigned | `FunctionDescriptor`/`jni` dùng đúng C type theo ABI; không làm rơi bit cao |
| Lỗi trộn | NULL + độ dài dương; buffer thiếu + Unicode nhiều byte; overflow + length âm | Thứ tự validation rõ ràng, status ổn định, không phụ thuộc hành vi undefined |

**Thiết kế test theo ranh giới `n-1, n, n+1`** là cách bắt lỗi lệch một đơn vị. Với một chuỗi UTF-8 cần `B` byte nội dung và **1 byte NUL**, kiểm thử buffer `B` (thiếu đúng 1), `B+1` (vừa đủ), `B+2` (dư 1). Nếu API không dùng NUL-terminated thì không tự cộng 1.

### Quy tắc kiểm tra phạm vi tránh tràn phép cộng

Điều kiện ngây thơ `offset + length <= capacity` có thể sai khi `offset + length` **tràn số**. Cách kiểm tra trên các `long` không âm an toàn hơn:

```java
static boolean fits(long offset, long length, long capacity) {
    return offset >= 0 && length >= 0 && capacity >= 0
            && offset <= capacity && length <= capacity - offset;
}
```

Chỉ tính `capacity - offset` sau khi biết `offset <= capacity`. Với buffer dài `capacity`, `fits(capacity, 0, capacity)` là `true` nhưng `fits(capacity, 1, capacity)` là `false`.

## 3. Kiểm thử null và chuỗi rỗng

### Phía Java/FFM

```java
// Minh họa bên trong một method Java có biến arena đang mở:
MemorySegment nullPointer = MemorySegment.NULL; // địa chỉ native 0
MemorySegment emptyCString = arena.allocateFrom(""); // một byte 0x00

boolean reallyNull = nullPointer.address() == 0;
boolean reallyEmpty = emptyCString.getString(0).isEmpty();
```

Đoạn trên phụ thuộc biến `arena`, không phải chương trình độc lập; chương trình chạy được ở mục 6.

Một wrapper nhận chuỗi Java không nullable nên dùng `Objects.requireNonNull(text, "text")`, hoặc trả lỗi miền nghiệp vụ có tài liệu. Wrapper cho phép C pointer nullable phải ánh xạ **có chủ đích** từ input sang `MemorySegment.NULL`. **Không** dùng Java `null` làm một cách viết tắt mơ hồ cho C `NULL` tại mọi FFM API.

Đối với C API kiểu `(ptr, len)`: cần kiểm thử cả `(NULL, 0)`, `(NULL, 1)`, `(valid_ptr, 0)`. Trường hợp nào hợp lệ phụ thuộc contract; `len == 0` không đương nhiên cho phép sử dụng con trỏ invalid với các thư viện có tiền điều kiện nghiêm ngặt.

### Phía JNI

JNI có cả `jstring` (tham chiếu Java có thể null) và các hàm trả vùng ký tự native như `GetStringUTFChars`. Việc dùng một con trỏ `NULL` trả về khi truy xuất thất bại phải được xử lý theo đặc tả JNI trước khi đọc; quản lý đúng cặp release và lifetime. Đừng coi `GetStringUTFChars` là quy ước UTF-8 chuẩn: JNI sử dụng **Modified UTF-8**, khác UTF-8 chuẩn ở U+0000 và ký tự ngoài BMP. Việc test chuỗi phải biết chính xác API nào mã hóa/giải mã.

## 4. Unicode: phân biệt UTF-16, code point, UTF-8 và NUL

Java `String.length()` đếm **đơn vị mã UTF-16**, `codePointCount(...)` đếm code points, còn buffer C UTF-8 tính **byte**. Ví dụ:

| Chuỗi | `String.length()` | Unicode code points | UTF-8 bytes (không tính NUL) |
| --- | ---: | ---: | ---: |
| `""` | 0 | 0 | 0 |
| `"A"` | 1 | 1 | 1 |
| `"é"` (U+00E9) | 1 | 1 | 2 |
| `"🌍"` (U+1F30D) | 2 | 1 | 4 |
| `"A🌍ế"` | 4 | 3 | 8 |

Với `"A🌍ế"`, C string UTF-8 chuẩn cần **9 byte**: 8 byte nội dung + 1 byte NUL. Việc dùng `text.length() + 1` sẽ tính ra 5, thiếu 4 byte. `Arena.allocateFrom(text)` cấp phát một segment có kích thước phù hợp và thêm terminator theo charset; `MemorySegment.getString(0)` đọc UTF-8 NUL-terminated.

### NUL nằm giữa chuỗi

`"A\0B"` trong Java bao gồm ba ký tự: `A`, U+0000, `B`. `arena.allocateFrom(...)` vẫn mã hóa byte `0x00` nằm giữa, và thêm terminator cuối. Nhưng `segment.getString(0)` dừng tại NUL đầu tiên, trả `"A"`. Đây **không phải** lỗi của UTF-8; đó là bản chất C string. Nếu `B` có nghĩa, hãy chuyển dữ liệu dưới dạng **byte[] + byte length** hoặc một giao thức có length riêng, đồng thời test round-trip trên byte gốc.

### Unicode không hợp lệ và normalization

- Một surrogate đơn lẻ, ví dụ mã UTF-16 `0xD800` không có low surrogate tương ứng, không phải một scalar Unicode hợp lệ. `String.getBytes(StandardCharsets.UTF_8)` theo kiểu tiện dụng có thể **thay thế** dữ liệu không mã hóa được. Với API yêu cầu chính xác, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` và kiểm thử `MalformedInputException`.
- Chuỗi UTF-8 byte không hợp lệ cũng cần chính sách rõ: reject hoặc replacement. `MemorySegment.getString(..., Charset)` dùng replacement cho malformed input; nếu muốn reject, dùng decoder có `REPORT` trên đúng dãy byte có độ dài.
- Hai chuỗi có vẻ giống nhau như `"é"` (U+00E9) và `"e\u0301"` (U+0065 + U+0301) có thể khác byte. Chỉ normalize (`Normalizer.Form.NFC`, v.v.) nếu giao thức yêu cầu; không tự thay đổi dữ liệu đầu vào ở lớp JNI/FFM.
- **JNI Modified UTF-8** không tương đương UTF-8 chuẩn; nếu giao tiếp với C function ngoài JNI dùng UTF-8 thông thường, không đem số byte từ `GetStringUTFLength` cũ hoặc dữ liệu `GetStringUTFChars` mặc nhiên dùng như UTF-8 chuẩn. Trên JDK 24+, `GetStringUTFLengthAsLong` trả `jlong` để tránh giới hạn `jsize` của API cũ; vẫn cần kiểm soát độ dài/buffer theo contract.

## 5. Buffer ngắn: tính dung lượng và chứng minh không ghi tràn

Đối với một API **UTF-8 NUL-terminated**, phần Java có thể tính:

```java
String text = "é";
byte[] payload = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
long required = Math.addExact((long) payload.length, 1L); // 2 + 1 = 3
```

Nếu chỉ cấp 2 byte:

```java
// Ví dụ này dùng biến arena đang mở:
MemorySegment shortBuffer = arena.allocate(2);
shortBuffer.setString(0, "é");  // IndexOutOfBoundsException
```

Nếu cấp 3 byte, `setString(0, "é")` và `getString(0)` hoạt động đúng. **FFM Java bounds check** chứng minh thao tác `setString` qua Java API không được ghi vượt phạm vi segment. Điều đó **chưa chứng minh** một hàm native nhận con trỏ không ghi vượt `dst_capacity`; cần test riêng phần C/C++.

Khi native trả “buffer too small”, test nên kiểm tra **cả nội dung và trạng thái**:

- `written` là 0, số byte đã ghi hay số byte yêu cầu? Phải khớp hợp đồng, không suy đoán.
- Buffer ngắn có bị sửa một phần không? Nếu hợp đồng cam kết “không sửa gì khi lỗi”, khẳng định toàn bộ payload và hai canary trước/sau **không đổi**.
- Nếu native hỗ trợ truncation, chỉ cho phép truncate tại **ranh giới ký tự** khi giao thức quy định chuỗi UTF-8, và phải đảm bảo byte NUL cuối; dữ liệu nhị phân thì có thể dùng semantics khác.
- API kiểu `snprintf`, `strncpy`, `memcpy` có các quy tắc hoàn toàn khác về return value/terminator; không dùng test expectation của hàm này cho hàm khác.

Một dạng phòng vệ nhỏ đối với API do ta sở hữu:

```c
/* copy_bytes.c: hợp đồng nhị phân, len/capacity tính theo BYTE.
   Không yêu cầu NUL, không ghi một phần khi buffer thiếu.
   Dữ liệu được phép có 0x00 bên trong. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

enum { COPY_OK = 0, COPY_BAD_ARG = 1, COPY_TOO_SMALL = 2 };

int copy_bytes(const uint8_t *src, size_t len,
               uint8_t *dst, size_t capacity,
               size_t *written) {
    if (written == NULL) return COPY_BAD_ARG;
    *written = 0;

    if ((len != 0 && src == NULL) ||
        (capacity != 0 && dst == NULL)) {
        return COPY_BAD_ARG;
    }
    if (len > capacity) return COPY_TOO_SMALL;

    if (len != 0) {
        memmove(dst, src, len);
    }
    *written = len;
    return COPY_OK;
}
```

Hàm trên có **contract được thiết kế riêng để học**, không phải wrapper cho mọi C API. `memmove` chọn để xử lý vùng nguồn/đích có thể chồng lấn; một API thực tế có thể cấm overlap và yêu cầu kiểm tra khác. Đặc biệt, C **không tự biết** con trỏ `src`/`dst` thật sự chỉ tới vùng được cấp phát bao nhiêu byte: caller phải bảo đảm `len` và `capacity` trung thực.

C test harness tên `copy_bytes_test.c`:

```c
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "copy_bytes.c"  /* Chỉ include .c trong ví dụ học độc lập. */

int main(void) {
    uint8_t src[] = {0x41, 0x00, 0xE2, 0x82, 0xAC};
    uint8_t dst[7];
    size_t written = 99;
    memset(dst, 0xA5, sizeof dst);

    assert(copy_bytes(src, 5, dst + 1, 5, &written) == COPY_OK);
    assert(written == 5);
    assert(memcmp(dst + 1, src, 5) == 0);
    assert(dst[0] == 0xA5 && dst[6] == 0xA5);

    memset(dst + 1, 0x7E, 5);
    written = 99;
    assert(copy_bytes(src, 5, dst + 1, 4, &written) == COPY_TOO_SMALL);
    assert(written == 0);
    for (size_t i = 1; i < 6; ++i) assert(dst[i] == 0x7E);
    assert(dst[0] == 0xA5 && dst[6] == 0xA5);

    assert(copy_bytes(NULL, 0, NULL, 0, &written) == COPY_OK);
    assert(written == 0);
    assert(copy_bytes(NULL, 1, dst, sizeof dst, &written) == COPY_BAD_ARG);
    assert(copy_bytes(src, 5, dst, sizeof dst, NULL) == COPY_BAD_ARG);

    puts("C contract PASS");
    return 0;
}
```

Trên Linux/macOS với GCC/Clang (có hỗ trợ sanitizer), ở thư mục chứa hai file C:

```bash
cc -std=c11 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
  -o copy_bytes_test copy_bytes_test.c
./copy_bytes_test
```

**Stdout khi các assert đều thành công:**

```text
C contract PASS
```

Khi dùng sanitizer, theo dõi cả exit code và stderr: một lỗi AddressSanitizer/UndefinedBehaviorSanitizer phải làm test fail ngay cả khi các assert logic chưa bắt được. Môi trường hoặc compiler không hỗ trợ sanitizer cần lệnh build tương ứng; bảo đảm của sanitizer chỉ áp dụng cho các đường chạy đã thực thi. C test trên kiểm chứng rõ byte `0x00` nhúng ở vị trí thứ hai và canary của destination. Trong dự án thực tế nên tách prototype sang header thay vì include `.c`.

## 6. Lab Java 22+: 27 trường hợp kiểm thử độc lập

Tạo file **`NativeBoundaryLab.java`**. Mã sau không cần JUnit, không tải thư viện native và có thể chạy với `javac`/`java` JDK 22+:

```java
import java.lang.foreign.*;
import java.nio.CharBuffer;
import java.nio.charset.*;
import java.util.Objects;

public class NativeBoundaryLab {
    private static int passes = 0;

    @FunctionalInterface
    interface Action { void run() throws Throwable; }

    private static void ok(String name, boolean valid) {
        if (!valid) throw new AssertionError("FAIL " + name);
        passes++;
        System.out.println("PASS " + name);
    }

    private static void expect(String name,
                               Class<? extends Throwable> expected,
                               Action action) {
        try {
            action.run();
        } catch (Throwable ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError("Wrong exception: " + name, ex);
            }
            passes++;
            System.out.println("PASS " + name + " -> "
                    + ex.getClass().getSimpleName());
            return;
        }
        throw new AssertionError("Missing exception: " + name);
    }

    private static long requiredBytes(long count, long stride, long extra) {
        if (count < 0 || stride <= 0 || extra < 0) {
            throw new IllegalArgumentException("invalid size");
        }
        return Math.addExact(Math.multiplyExact(count, stride), extra);
    }

    private static boolean fits(long offset, long length, long capacity) {
        return offset >= 0 && length >= 0 && capacity >= 0
                && offset <= capacity && length <= capacity - offset;
    }

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment eight = arena.allocate(8);
            ok("last-byte", eight.get(ValueLayout.JAVA_BYTE, 7) == 0);
            expect("offset-at-capacity", IndexOutOfBoundsException.class,
                    () -> eight.get(ValueLayout.JAVA_BYTE, 8));
            ok("empty-slice-end", eight.asSlice(8, 0).byteSize() == 0);
            expect("slice-past-end", IndexOutOfBoundsException.class,
                    () -> eight.asSlice(8, 1));

            ok("null-address", MemorySegment.NULL.address() == 0
                    && MemorySegment.NULL.byteSize() == 0);
            expect("null-dereference", IndexOutOfBoundsException.class,
                    () -> MemorySegment.NULL.get(ValueLayout.JAVA_BYTE, 0));
            expect("java-null-policy", NullPointerException.class,
                    () -> Objects.requireNonNull(null, "text"));

            MemorySegment empty = arena.allocateFrom("");
            ok("empty-c-string", empty.byteSize() == 1
                    && empty.getString(0).isEmpty());

            String unicode = "A" + Character.toString(0x1F30D)
                    + Character.toString(0x1EBF);
            byte[] utf8 = unicode.getBytes(StandardCharsets.UTF_8);
            ok("utf16-vs-codepoints", unicode.length() == 4
                    && unicode.codePointCount(0, unicode.length()) == 3);
            ok("utf8-bytes", utf8.length == 8);
            MemorySegment encoded = arena.allocateFrom(unicode);
            ok("encoded-capacity", encoded.byteSize() == 9);
            ok("utf8-round-trip", encoded.getString(0).equals(unicode));

            MemorySegment embedded = arena.allocateFrom("A\0B");
            ok("embedded-nul-stops-c-string", embedded.byteSize() == 4
                    && embedded.getString(0).equals("A"));
            expect("no-zero-terminator", IndexOutOfBoundsException.class,
                    () -> MemorySegment.ofArray(new byte[]{65, 66}).getString(0));

            String accent = Character.toString(0x00E9);
            expect("buffer-too-short", IndexOutOfBoundsException.class,
                    () -> arena.allocate(2).setString(0, accent));
            MemorySegment exact = arena.allocate(3);
            exact.setString(0, accent);
            ok("buffer-exact", exact.getString(0).equals(accent));

            byte[] canary = {9, 0, 0, 9};
            MemorySegment body = MemorySegment.ofArray(canary).asSlice(1, 2);
            body.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
            body.set(ValueLayout.JAVA_BYTE, 1, (byte) 8);
            ok("canary-untouched", canary[0] == 9 && canary[3] == 9);
            expect("canary-guarded-write", IndexOutOfBoundsException.class,
                    () -> body.set(ValueLayout.JAVA_BYTE, 2, (byte) 1));

            ok("zero-count", requiredBytes(0, 8, 0) == 0);
            ok("checked-size", requiredBytes(4, 8, 1) == 33);
            expect("negative-count", IllegalArgumentException.class,
                    () -> requiredBytes(-1, 8, 0));
            expect("product-overflow", ArithmeticException.class,
                    () -> requiredBytes(Long.MAX_VALUE, 8, 0));
            expect("sum-overflow", ArithmeticException.class,
                    () -> requiredBytes(Long.MAX_VALUE, 1, 1));
            expect("narrowing-overflow", ArithmeticException.class,
                    () -> Math.toIntExact((long) Integer.MAX_VALUE + 1));
            expect("unpaired-surrogate", MalformedInputException.class,
                    () -> StandardCharsets.UTF_8.newEncoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .encode(CharBuffer.wrap(
                                    Character.toString((char) 0xD800))));
            ok("range-at-end-empty", fits(8, 0, 8));
            ok("range-at-end-nonempty-rejected", !fits(8, 1, 8));
        }
        System.out.println("TOTAL=" + passes);
    }
}
```

Chạy ở thư mục chứa `NativeBoundaryLab.java`:

```bash
javac -encoding UTF-8 NativeBoundaryLab.java
java NativeBoundaryLab
```

**Stdout kiểm chứng:**

```text
PASS last-byte
PASS offset-at-capacity -> IndexOutOfBoundsException
PASS empty-slice-end
PASS slice-past-end -> IndexOutOfBoundsException
PASS null-address
PASS null-dereference -> IndexOutOfBoundsException
PASS java-null-policy -> NullPointerException
PASS empty-c-string
PASS utf16-vs-codepoints
PASS utf8-bytes
PASS encoded-capacity
PASS utf8-round-trip
PASS embedded-nul-stops-c-string
PASS no-zero-terminator -> IndexOutOfBoundsException
PASS buffer-too-short -> IndexOutOfBoundsException
PASS buffer-exact
PASS canary-untouched
PASS canary-guarded-write -> IndexOutOfBoundsException
PASS zero-count
PASS checked-size
PASS negative-count -> IllegalArgumentException
PASS product-overflow -> ArithmeticException
PASS sum-overflow -> ArithmeticException
PASS narrowing-overflow -> ArithmeticException
PASS unpaired-surrogate -> MalformedInputException
PASS range-at-end-empty
PASS range-at-end-nonempty-rejected
TOTAL=27
```

**Giải thích các khẳng định đáng chú ý:**

- `arena.allocate(8)` tạo buffer 8 byte có offset hợp lệ từ 0 đến 7. `asSlice(8, 0)` hợp lệ vì phần rỗng có thể bắt đầu ngay cuối segment; `asSlice(8, 1)` vượt giới hạn.
- `MemorySegment.NULL` có địa chỉ 0 và dung lượng 0; cố đọc 1 byte dẫn đến `IndexOutOfBoundsException`. Việc kết luận một pointer nullable có được truyền cho native hay không vẫn phụ thuộc hợp đồng hàm C.
- Chuỗi `"A🌍ế"` được dựng từ mã Unicode để code nguồn không phụ thuộc terminal encoding; nó có 4 UTF-16 units, 3 code points và 8 byte UTF-8. Segment C string có 9 byte do NUL terminator.
- `"A\0B"` có NUL giữa nên `getString(0)` trả `"A"`. Đây là phép thử cho “C string” chứ không phải round-trip toàn bộ dữ liệu nhị phân.
- Buffer dành cho `"é"` cần 2 byte UTF-8 cộng 1 byte NUL. `setString` vào 2 byte sẽ bị chặn; 3 byte thì thành công.
- Canary `9` nằm hai bên body trên một `byte[]`; sau hai thao tác ghi hợp lệ, canary vẫn nguyên vẹn, còn ghi offset ngoài body bị Java FFM bounds check từ chối. **Native C được đưa con trỏ trực tiếp có thể vượt rào FFM này**, nên vẫn phải chạy sanitizer/test C.
- `requiredBytes(...)` kiểm tra input âm và dùng `Math.multiplyExact`/`Math.addExact`; phép toán quá giới hạn ném `ArithmeticException` thay vì vòng về giá trị nhỏ hoặc âm. `Math.toIntExact` phát hiện trường hợp API C/JNI thật chỉ nhận số nguyên 32-bit.
- Bộ test **không cố cấp phát** `Long.MAX_VALUE` byte. Tràn được chứng minh bằng số học thuần túy để tránh `OutOfMemoryError`, treo tiến trình hoặc làm cạn RAM của máy CI.

## 7. Kích thước: tràn phép nhân, cộng và chuyển kiểu qua ABI

Lỗi phổ biến:

```java
// Sai: có thể tràn int TRƯỚC khi gán sang long.
long total = itemCount * elementBytes;

// Sai: tổng có thể tràn ngay cả khi tích chưa tràn.
long withHeader = total + headerBytes;
```

Nếu `itemCount` và `elementBytes` đều là `int`, phép nhân đầu tiên tính bằng `int`. Ép sang `long` **sau** phép nhân không khôi phục các bit đã mất. Cách đúng:

```java
// Đây là đoạn minh họa, không phải chương trình độc lập.
if (itemCount < 0 || elementBytes <= 0 || headerBytes < 0) {
    throw new IllegalArgumentException("Invalid sizes");
}
long payloadBytes = Math.multiplyExact((long) itemCount, (long) elementBytes);
long totalBytes = Math.addExact(payloadBytes, (long) headerBytes);

// Chỉ khi API native thật sự nhận 32-bit int/jsize:
int nativeLength = Math.toIntExact(totalBytes);
```

**Đừng dùng `Math.toIntExact` một cách máy móc** cho API nhận `size_t` 64-bit: nó có thể từ chối dữ liệu hợp lệ. Ngược lại, dù Java `long` chứa số dương, C `size_t` ở môi trường 32-bit có thể nhỏ hơn và `size_t` là số **unsigned**. Phải kiểm tra giới hạn C theo ABI (đặc biệt nếu chuyển từ `long` sang C size_t 32-bit) và quy mô bộ nhớ thực tế trước khi gọi native.

FFM hỗ trợ truy vấn layout chuẩn ABI:

```java
// Snippet dành cho JDK 22+, không tự gọi native function.
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;

Linker linker = Linker.nativeLinker();
MemoryLayout cSizeT = linker.canonicalLayouts().get("size_t");
MemoryLayout cInt = linker.canonicalLayouts().get("int");
System.out.println("size_t bytes=" + cSizeT.byteSize());
```

Đây là **đoạn ý tưởng không phải file Java chạy độc lập** (các `import` đặt ở đầu file khi đưa vào chương trình). Giá trị in ra phụ thuộc nền tảng, thường 4 byte trên ABI 32-bit và 8 byte trên ABI 64-bit; không gán một stdout cố định cho mọi hệ điều hành. Khi tạo `FunctionDescriptor`, dùng layout đúng của `size_t` và `int` theo `Linker.canonicalLayouts()` thay vì giả sử mọi C `long` có cùng độ rộng ở Linux và Windows.

Ở phía C, khi phải tính `count * stride + extra` với `size_t`:

```c
#include <stddef.h>
#include <stdint.h>

int compute_bytes(size_t count, size_t stride,
                  size_t extra, size_t *out) {
    if (out == NULL || stride == 0) return 0;
    if (count > SIZE_MAX / stride) return 0;
    size_t payload = count * stride;
    if (extra > SIZE_MAX - payload) return 0;
    *out = payload + extra;
    return 1;
}
```

Hàm này trả 0 khi không thể tính đúng, 1 khi thành công; không đọc/ghi dữ liệu và không cấp phát. Nó kiểm tra phép nhân trước rồi phép cộng, sử dụng `SIZE_MAX` thay vì mặc định C `size_t` cùng giới hạn với Java `long`. Khi input là `jlong`, `jint` hoặc một unsigned C size, thiết kế phép chuyển đổi và giới hạn tương thích rõ ràng ở điểm giao tiếp.

## 8. Tích hợp FFM/JNI: kiểm thử với thư viện native thật

Các test `MemorySegment` là một lớp bảo vệ hữu ích nhưng chưa thay thế được **integration test** dùng thư viện được build thực tế.

### 8.1. Đúng chữ ký ABI và native access

Với hàm C `copy_bytes` ở mục 5, chữ ký ABI phải mô tả đúng:

```c
int copy_bytes(const uint8_t *src, size_t len,
               uint8_t *dst, size_t capacity,
               size_t *written);
```

Về mặt FFM: return `int`, tham số `src`/`dst`/`written` là address, còn `len`/`capacity` là `size_t`. Cần dùng `Linker.canonicalLayouts()` để xác định `size_t` và kiểu carrier Java tương ứng. Đừng cố ép handle có `size_t` 32-bit thành lời gọi `long` 64-bit qua `invokeExact` rồi mong JVM tự chuyển; kiểm tra `methodHandle.type()`. Module đang thực hiện restricted downcall phải được cấp native access khi JDK yêu cầu; ví dụ ứng dụng classpath có thể dùng `--enable-native-access=ALL-UNNAMED`.

**Quy trình kiểm thử**: build thư viện cho đúng OS/CPU, nạp symbol, xác nhận kiểu handle, cấp phát native buffers bằng arena, truyền đúng địa chỉ/dung lượng, kiểm tra status + `written` + bytes trả về, đóng arena sau khi lời gọi hoàn tất. Không hard-code `size_t == long` hoặc assumed charset.

### 8.2. Giữ ranh giới giữa bộ nhớ Java và bộ nhớ C

- `MemorySegment.get/set` chặn truy cập vượt giới hạn segment theo API Java. **Con trỏ đi qua FFM xuống C không mang sẵn bảo đảm kích thước đó cho C**; mã C sai vẫn có thể ghi quá dung lượng, làm hỏng heap/stack hoặc crash JVM.
- Thư viện native có thể giữ con trỏ sau khi hàm trả về. Test phải biết API là **borrowed pointer** (chỉ dùng trong lời gọi) hay **retained pointer** (giữ để dùng sau), ai giải phóng, callback và worker thread nào tiếp tục dùng. Không đóng `Arena` trước khi native đã ngừng sử dụng buffer.
- `MemorySegment.ofAddress(...)`/`reinterpret(...)` không xác nhận vùng nhớ đằng sau con trỏ thực sự còn sống hoặc đủ lớn. Không dùng `reinterpret` như cách làm cho test pointer thiếu dung lượng “qua được”.
- Một số lỗi JNI/FFM có thể crash tiến trình thay vì ném Java exception. Chạy bài test native gây rủi ro trong **process JVM riêng** và xem exit status/ASan/UBSan/`hs_err_pid*.log` nếu phát sinh. Không dùng try/catch làm bằng chứng bắt được lỗi truy cập bộ nhớ thô.

### 8.3. Ma trận platform

| Mục tiêu | Điều kiện cần kiểm tra |
| --- | --- |
| Windows x64 | Kiểu `long` của C thường 32-bit trong ABI LLP64; `size_t` 64-bit; DLL đúng kiến trúc |
| Linux x64 | C `long` và `size_t` thường 64-bit trong ABI LP64; ELF và dependencies phù hợp |
| macOS ARM64 | AArch64 ABI, dylib/architecture đúng; layout/alignment và charset theo contract |
| Môi trường 32-bit (nếu sản phẩm hỗ trợ) | `size_t`/pointer thường 32-bit; thử giá trị vượt `UINT32_MAX` mà không cấp phát |
| JDK 22+ | FFM chuẩn; test API `java.lang.foreign` và cấu hình quyền native theo phiên bản |
| JNI legacy | Quy tắc `GetStringUTFChars` Modified UTF-8, reference và local/global refs; kiểm tra ownership/release |

Không thử nghiệm con trỏ giả bằng cách ghi qua `MemorySegment.ofAddress(1).reinterpret(...)`: thao tác đó có thể gây crash. Kiểm thử số học và giới hạn ABI độc lập trước, sau đó thử vùng nhớ **thực sự được cấp phát** bằng thư viện.

## 9. Tổ chức bộ kiểm thử và tiêu chí PASS/FAIL

Thiết kế ba tầng:

1. **Unit/contract Java**: kiểm tra `null`/empty, encoding, byte size, checked arithmetic, range guard. Chạy nhanh, không phụ thuộc native binary; lab 27 test ở mục 6 có thể chạy ở tầng này.
2. **Native unit + sanitizer**: kiểm tra trực tiếp hàm C với buffer 0, thiếu 1, vừa đủ, byte NUL nhúng, canary, overflow và error path. Chạy ASan/UBSan hoặc công cụ tương đương, ưu tiên biên dịch debug.
3. **Integration Java ↔ native**: nạp thư viện thật, cấu hình ABI/FFM/JNI, kiểm tra status, out-param, độ dài trả về, dữ liệu byte, lifecycle, thread và path lỗi. Chạy trên các OS/JDK/CPU thực sự hỗ trợ; isolate test có nguy cơ crash JVM.

Thêm **property-based/fuzz test** với seed tái lập: sinh `byte[]` ngẫu nhiên (kể cả `0x00`), các length/capacity ở sát biên và Unicode nhiều byte; yêu cầu round-trip đúng từng byte khi contract là nhị phân, hoặc đúng theo charset/terminator khi contract là chuỗi. Ghi seed và input tối thiểu khi fail. Với Java–C, so sánh **bytes**, status, `written` và canary, không chỉ so sánh hiển thị chuỗi.

**Tiêu chí chấp nhận một case** gồm: đúng mã lỗi/exception theo contract; không hỏng dữ liệu bên ngoài buffer; không sai số byte hoặc cắt Unicode trái quy định; không tràn phép toán; không leak/double-free; không báo lỗi sanitizer; không treo/crash JVM ngoài những ca kiểm thử cố ý cách ly. Nếu API cho phép partial write, xác nhận chính xác phần nào có thể thay đổi.

### Lỗi thường gặp khi viết test

- Dùng `String.length()` làm số byte UTF-8, quên byte `NUL` cuối.
- Coi Java `null`, `MemorySegment.NULL` và `""` là một trạng thái.
- Chỉ test ASCII; bỏ qua emoji (surrogate pair), tiếng Việt và NUL nhúng.
- Test buffer 100 byte nhưng quên `required - 1`, `required`, `required + 1`.
- Dùng `int total = count * stride` hoặc ép kiểu sang `long` sau khi tích đã tràn.
- Giả sử C `size_t`, C `long`, Java `long` có độ rộng/ABI giống nhau trên mọi platform.
- Chỉ test phía Java, nên bỏ sót C viết quá buffer dù `MemorySegment` đã bounds-check đúng.
- Quên rằng `getString` là API NUL-terminated và không tự mang length của dữ liệu nhị phân.
- Dùng `CharsetEncoder` mặc định thay thế surrogate sai mà vẫn khẳng định “round-trip nguyên vẹn”.
- Chỉ test “không ném exception”, không kiểm tra status, bytes, canary, ownership và leak.

## 10. Câu hỏi thực hành

**Bài 1.** Java `String s = "A🌍ế";` có `s.length() == 4`. Một C API cần UTF-8 NUL-terminated. Dung lượng vừa đủ là bao nhiêu? **9 byte**: 1 cho `A`, 4 cho emoji, 3 cho `ế`, 1 cho NUL.

**Bài 2.** Buffer có `capacity=8`. Lời gọi cần ghi 1 byte tại `offset=8`. Có hợp lệ không? **Không.** Byte cuối cùng là offset 7; `offset=8` chỉ hợp lệ nếu thao tác 0 byte và API cho phép.

**Bài 3.** Một binary API nhận bytes `{65,0,66}` và length 3. Có thể dùng `getString(0)` để xác nhận đúng đủ 3 byte không? **Không.** Hàm chuỗi dừng ở NUL, chỉ trả `"A"`; phải so sánh ba byte theo độ dài.

**Bài 4.** `int count=1_100_000_000; int stride=8; long bytes=count*stride;` có đúng không? **Không.** `int * int` bị tràn trước khi gán. Dùng `Math.multiplyExact((long)count, (long)stride)`.

**Bài 5.** `MemorySegment` Java chặn `setString` trên buffer thiếu 1 byte. Điều đó chứng minh C function được gọi qua FFM không thể tràn buffer? **Không.** C chỉ nhận địa chỉ/dung lượng theo ABI và có thể ghi sai; phải có native test, sanitizer và contract rõ ràng.

## Tài liệu để đối chiếu

- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM chính thức từ JDK 22.
- [Java SE 25 — MemorySegment](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html): `NULL`, `byteSize`, `getString`/`setString`, bounds checks, zero-length segments.
- [Java SE 25 — SegmentAllocator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SegmentAllocator.html) và [Arena](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html): `allocateFrom(String)`, vòng đời bộ nhớ, cách cấp phát.
- [Java SE 25 — Linker](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): canonical C layouts, `size_t`, ABI và rủi ro của downcall.
- [Java SE 25 — JNI Functions](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html): `GetStringUTFChars`, `GetStringUTFLength`, `GetStringUTFLengthAsLong` (từ JDK 24) và JNI string behavior.
- [Java SE 25 — JNI Types](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html): `jsize`, Modified UTF-8 và primitive data types.
