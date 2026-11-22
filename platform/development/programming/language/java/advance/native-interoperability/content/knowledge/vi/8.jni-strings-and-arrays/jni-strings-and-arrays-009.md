# JNI: xử lý ký tự 0, Unicode ngoài BMP, mảng rỗng và kiểm tra giới hạn

Ở ranh giới Java–native, dữ liệu văn bản và mảng có thể bị hỏng dù mã biên dịch thành công. Nguyên nhân thường không nằm ở JNI syntax mà ở **cách hiểu khác nhau về độ dài**: ký tự U+0000 hợp lệ trong Java nhưng kết thúc một chuỗi C dùng NUL; ký tự Unicode ngoài Basic Multilingual Plane (BMP) chiếm hai UTF-16 code units nhưng một code point; một mảng rỗng có độ dài 0 chứ không phải con trỏ được phép đọc; và phép tính `start + count` có thể tràn số nguyên trước khi kiểm tra.

Bài học thuộc nhóm **Chuỗi và mảng JNI**. Mục tiêu là thiết kế đúng hợp đồng truyền dữ liệu, phân biệt UTF-16/UTF-8/Modified UTF-8, xử lý chuỗi/mảng rỗng và null, kiểm tra chỉ số an toàn, giữ đúng thời hạn mượn pointer JNI, rồi tự chạy một ví dụ **Java 17 + C11** kiểm chứng từng biên.

## 1. Năm khái niệm phải tách biệt

| Khái niệm | Ví dụ | Ý nghĩa khi dùng JNI |
| --- | --- | --- |
| Ký tự Unicode **U+0000** | `'\0'`, code point 0 | Là **nội dung hợp lệ** trong Java `String`; không đồng nghĩa Java `null` |
| Byte NUL **0x00** | Byte kết thúc C string | Trong C string thông thường, `strlen` dừng ở NUL đầu tiên; với buffer nhị phân, 0x00 là dữ liệu |
| Java **null reference** | `String s = null` | Không có đối tượng `jstring`/`jarray`; nhiều JNI API yêu cầu đối số non-null |
| **Chuỗi rỗng** | `""` | Có đối tượng `String` hợp lệ với `GetStringLength == 0` |
| **Mảng rỗng** | `new byte[0]` | Có đối tượng `jbyteArray` hợp lệ với `GetArrayLength == 0`; khác `NULL` |

Các cách tính “độ dài” cũng khác nhau:

- `String.length()` và JNI `GetStringLength` trả **số đơn vị mã UTF-16 (16 bit)**, không nhất thiết bằng số Unicode code points.
- `String.codePointCount(0, text.length())` đếm code points theo quy tắc Java; mỗi cặp surrogate hợp lệ được ghép thành một code point.
- `text.getBytes(StandardCharsets.UTF_8).length` là **số byte UTF-8 chuẩn** được Java mã hóa; với chuỗi chứa surrogate lẻ, encoder mặc định có thể thay thế dữ liệu lỗi, tùy cách cấu hình.
- `GetStringUTFLength` trả số **byte Modified UTF-8** theo JNI, không phải số byte UTF-8 chuẩn và không bao gồm byte terminator mà một giao thức C riêng có thể yêu cầu.
- `GetArrayLength(env, array)` trả **số phần tử** của mảng Java, không phải số byte. Dùng đúng đơn vị khi truyền `jint *`, `jbyte *`, hoặc địa chỉ vào thư viện C.

Không suy ra capacity của buffer từ pointer, cũng không suy ra số Unicode code points từ số byte.

## 2. U+0000 trong Java không phải kết thúc chuỗi

Java `String` có thể chứa NUL nằm ở giữa:

~~~java
String data = "A" + '\0' + "B";
System.out.println(data.length());          // 3
System.out.println(data.charAt(1) == 0);    // true
~~~

Kết quả:

~~~text
3
true
~~~

Đây là một đoạn Java có thể đặt trong `main`, chưa phải tệp độc lập. Nó minh họa rằng ký tự ở giữa vẫn được tính vào độ dài, không làm String bị cắt. Ngược lại, C string thường là dãy byte kết thúc ở `'\0'`:

~~~c
char bytes[] = {'A', '\0', 'B', '\0'};
/* sizeof bytes == 4, nhưng strlen(bytes) == 1.
   Đây là mảnh minh họa; cần #include <string.h>. */
~~~

Vì `strlen` dừng tại byte NUL đầu tiên nên không thể dùng để đo một buffer nhị phân tùy ý, kể cả buffer chứa UTF-8 chuẩn hợp lệ có U+0000. Khi gọi C API nhận `const unsigned char *bytes, size_t byte_count`, hãy truyền **pointer cùng số byte**. Nếu API chỉ nhận C string, phải biết rõ nó có cho phép U+0000 trong dữ liệu hay không; nếu không, cần từ chối hoặc dùng một API có độ dài tường minh.

**Không nhầm Java `'\0'` với Java `null`.** JNI `GetStringLength(env, (jstring)NULL)` không phải lời gọi hợp lệ chỉ vì “độ dài có vẻ bằng 0”. Kiểm tra null riêng trước khi gọi API yêu cầu đối tượng hợp lệ.

### 2.1. Vì sao Modified UTF-8 xử lý NUL khác UTF-8 chuẩn?

JNI có họ API `GetStringUTFChars`, `GetStringUTFLength`, `GetStringUTFRegion` và `NewStringUTF` dùng **Modified UTF-8 (MUTF-8)**, không phải UTF-8 chuẩn. Trong MUTF-8:

- U+0000 được mã hóa bằng **hai byte `C0 80`**, thay vì byte `00` của UTF-8 chuẩn.
- Các UTF-16 code units từ U+0001 đến U+007F dùng một byte; nhiều giá trị BMP dùng hai hoặc ba byte.
- Một ký tự ngoài BMP được biểu diễn thành **cặp surrogate**, sau đó mỗi surrogate được mã hóa ba byte: tổng cộng sáu byte, thay vì bốn byte theo UTF-8 chuẩn.
- Không được giả định dữ liệu trả về có encoding UTF-8 chuẩn; một parser UTF-8 chuẩn có thể từ chối `C0 80` và các surrogate được mã hóa riêng.

Ví dụ String `"A" + '\0' + emoji U+1F600 + "Z"` có:

| Phép đo | Kết quả | Diễn giải |
| --- | ---: | --- |
| Java `String.length()` / JNI `GetStringLength` | **5** | `A` (1) + U+0000 (1) + emoji (2 surrogate units) + `Z` (1) |
| Unicode code points | **4** | `A`, U+0000, U+1F600, `Z` |
| UTF-8 chuẩn, số byte | **7** | 1 + 1 + 4 + 1 |
| JNI Modified UTF-8, số byte | **10** | 1 + 2 + 6 + 1 |

Đó là lý do một API nhận `GetStringUTFChars` và một API nhận UTF-8 chuẩn có thể nhìn cùng text bằng các byte khác nhau. Nếu native API cần UTF-8 chuẩn, dùng một chuyển đổi UTF-8 rõ ràng, thí dụ Java `getBytes(StandardCharsets.UTF_8)` rồi truyền `byte[]` cùng độ dài. Nếu native API yêu cầu MUTF-8/JNI, dùng đúng API JNI và giải phóng dữ liệu bằng đúng hàm đi kèm.

`GetStringUTFChars` trả một pointer mượn từ JVM, hợp lệ đến `ReleaseStringUTFChars` tương ứng; không `free` pointer này. Đừng dùng pointer đó sau release hoặc giữ làm trạng thái lâu dài trong C. Với dữ liệu độ dài lớn, cũng phải tránh dựa vào một `jsize` để mô tả byte buffer có kích thước vượt miền số nguyên 32 bit; kiểm tra giới hạn và chọn API/thiết kế cho dữ liệu lớn.

### 2.2. `NewStringUTF` không phải bộ giải mã UTF-8 chuẩn

Hàm `NewStringUTF(env, bytes)` được đặc tả nhận chuỗi byte **Modified UTF-8** của JNI. Đừng truyền bừa buffer UTF-8 chuẩn chứa byte NUL giữa chừng hoặc emoji bốn byte rồi hy vọng Java khôi phục đúng dữ liệu. Dữ liệu UTF-8 từ HTTP, file, JSON hoặc giao thức mạng cần được giải mã/kiểm tra bằng bộ giải mã UTF-8 chuẩn.

Nếu chủ động xử lý text theo UTF-16 trong native, có thể dùng `NewString(env, jchar_buffer, len)` để tạo String với **độ dài tường minh**, bảo toàn U+0000 và các code units; phải đảm bảo buffer hợp lệ, đủ `len` phần tử và xét dữ liệu surrogate không hợp lệ theo hợp đồng ứng dụng.

## 3. Unicode ngoài BMP, surrogate pairs và ký tự không hợp lệ

BMP là các code points từ U+0000 đến U+FFFF, ngoại trừ khoảng U+D800–U+DFFF dành cho **surrogate code units** và không phải Unicode scalar values hợp lệ. Một Unicode code point ngoài BMP (U+10000–U+10FFFF) được UTF-16 biểu diễn bằng:

- **High surrogate:** U+D800 đến U+DBFF.
- **Low surrogate:** U+DC00 đến U+DFFF.
- Hai code units liền kề tạo thành **một** code point ngoài BMP.

Ví dụ U+1F600 (😀) được biểu diễn bởi high surrogate `0xD83D` và low surrogate `0xDE00`. Với cặp hợp lệ, công thức kết hợp là:

~~~c
/* Mảnh minh họa, high/low đã được kiểm tra thuộc đúng dải. */
unsigned int code_point =
    0x10000u +
    (((unsigned int)high - 0xD800u) << 10) +
    ((unsigned int)low - 0xDC00u);
/* Kết quả cho D83D DE00: U+1F600. */
~~~

Ngược lại, một `char` Java đơn lẻ hay một `jchar` JNI chỉ chứa **16 bit** nên không thể chứa toàn bộ U+1F600. Không ép U+1F600 thành C `char`/`jchar` rồi coi như đã giữ nguyên ký tự.

Với Java:

~~~java
String smile = new String(Character.toChars(0x1F600));
System.out.println(smile.length()); // 2 UTF-16 code units
System.out.println(smile.codePointCount(0, smile.length())); // 1
System.out.printf("U+%X%n", smile.codePointAt(0)); // U+1F600
~~~

Stdout:

~~~text
2
1
U+1F600
~~~

Lưu ý thêm:

1. `GetStringChars` cho con trỏ `const jchar *` (UTF-16 code units), không cho số code points. Khi duyệt phải nhận diện cặp high/low rồi tăng index thêm một unit.
2. `GetStringRegion` cũng sao chép theo UTF-16 code-unit indices. Một slice cắt giữa surrogate pair tạo chuỗi có surrogate lẻ, có thể không phải Unicode text well-formed.
3. Java `String` có thể chứa **unpaired surrogate**. Nếu mục tiêu là Unicode scalar values hợp lệ, phải tự kiểm tra và chọn quy tắc lỗi; đừng giả định mọi Java String đều là well-formed Unicode.
4. `codePointCount` của Java xử lý mỗi unpaired surrogate là một đơn vị được đếm; điều này **không** khẳng định chuỗi hợp lệ cho bộ mã hóa chuẩn nào đó.
5. **Grapheme cluster** (ký tự người dùng nhìn thấy) không đồng nghĩa code point. Emoji ghép bằng zero-width joiner hoặc ký tự có dấu kết hợp có thể gồm nhiều code points. JNI xử lý code units/bytes; nếu cần cắt theo “ký tự hiển thị”, cần thuật toán Unicode segmentation ở tầng thích hợp.

### 3.1. Cách nhận diện surrogate pair an toàn bằng C

~~~c
/* Mảnh minh họa: chars trỏ tới len jchar hợp lệ. */
for (jsize i = 0; i < len; ++i) {
    jchar c = chars[i];
    if (c >= 0xD800 && c <= 0xDBFF &&
        i + 1 < len &&
        chars[i + 1] >= 0xDC00 &&
        chars[i + 1] <= 0xDFFF) {
        /* Đây là một code point ngoài BMP. */
        ++i;  /* Bỏ qua low surrogate đã ghép. */
    } else if ((c >= 0xD800 && c <= 0xDBFF) ||
               (c >= 0xDC00 && c <= 0xDFFF)) {
        /* Unpaired surrogate: quyết định báo lỗi/thay thế. */
    }
}
~~~

Điều kiện `i + 1 < len` phải được kiểm tra trước khi đọc `chars[i + 1]` để không vượt biên với high surrogate ở phần tử cuối. Mã này là mảnh minh họa, **không phải chương trình C độc lập**; ví dụ runnable ở mục 7 sẽ đếm zero units, surrogate pairs và lone surrogates.

## 4. Chọn JNI String API theo điều bạn thật sự cần

| JNI API | Dữ liệu | Trách nhiệm và lưu ý |
| --- | --- | --- |
| `GetStringLength` | Số UTF-16 code units (`jsize`) | Chuỗi phải non-null; trả 0 cho String rỗng |
| `GetStringChars` | Con trỏ mượn đến `jchar`/UTF-16 | Kiểm tra `NULL`; gọi `ReleaseStringChars` khi thành công |
| `GetStringRegion` | Copy một vùng UTF-16 vào buffer do caller cấp | Cần capacity theo số `jchar`, kiểm tra `start/len` |
| `GetStringUTFLength` | Độ dài byte Modified UTF-8 | Không phải số byte UTF-8 chuẩn; cần xét khả năng kích thước rất lớn |
| `GetStringUTFChars` | Con trỏ mượn đến byte MUTF-8 | Kiểm tra `NULL`; gọi `ReleaseStringUTFChars`; không `free` |
| `GetStringUTFRegion` | Copy vùng thành MUTF-8 | Output có thể **không có NUL terminator**; caller phải cấp đủ byte capacity |
| `NewString` | Tạo Java String từ `jchar *` với `len` | Bảo toàn embedded U+0000; nếu `len==0`, `unicodeChars==NULL` được phép |
| `NewStringUTF` | Tạo Java String từ MUTF-8 | Không nhận arbitrary UTF-8/byte[] như parser chuẩn |
| `GetStringCritical` | Mượn vùng string dạng critical | Chỉ dùng cho đoạn rất ngắn, theo các hạn chế JNI Critical |

**Lưu ý về độ dài/buffer:** `GetStringUTFRegion` nhận `start` và `len` **theo UTF-16 code units**, nhưng tạo số **byte MUTF-8** có thể nhiều gấp ba số code units. Không cấp một buffer `char[len + 1]` nếu chưa chứng minh đủ. Một upper bound đơn giản cho đoạn dài `len` code units là `3 * len` byte dữ liệu, cộng một byte nếu ứng dụng **tự** cần terminator; trước khi nhân/cộng phải kiểm tra overflow của `size_t`. JNI không bảo đảm `GetStringUTFRegion` tự ghi terminator cho bạn.

**Điểm quan trọng về quản lý tài nguyên:** C nhận pointer từ `GetStringChars` hoặc `GetStringUTFChars` không thể suy ra là view trực tiếp hay bản copy; JNI có quyền chọn. Khi mượn thành công, luôn release, kể cả chỉ đọc và kể cả native function sắp trả lỗi. Không truyền pointer borrowed này cho native code bất đồng bộ giữ lại sau khi release. Không gọi `strlen` trên dữ liệu chưa được xác nhận là C string NUL-terminated.

Một lựa chọn hữu ích cho dữ liệu ngắn hoặc cần giới hạn thời gian mượn là `GetStringRegion`: bạn tự cấp buffer, JNI copy vào và không cần gọi Release. Nếu làm việc với text rất dài, có thể xử lý theo chunk nhưng phải giữ được surrogate pair ở biên giữa hai chunk và kiểm tra mọi chỉ số/độ dài.

## 5. Mảng rỗng, null và cách đọc dữ liệu

Các giá trị sau không tương đương:

~~~java
byte[] missing = null;
byte[] empty = new byte[0];
byte[] oneZero = new byte[] {0};

System.out.println(empty.length);   // 0
System.out.println(oneZero.length); // 1
~~~

Stdout:

~~~text
0
1
~~~

Trong JNI, kiểm tra `array == NULL` trước `GetArrayLength`. Nếu không null và length bằng 0, có thể trả một kết quả trống/hợp lệ ngay mà không cần lấy pointer phần tử. Đừng dereference phần tử 0 hoặc làm `array[0]` với mảng rỗng.

**Các lựa chọn phổ biến để đọc primitive array:**

- `GetIntArrayRegion(env, array, start, count, buffer)`: copy đoạn mảng int sang `jint *` do caller cung cấp. Không cần Release, nhưng buffer phải đủ `count` phần tử và chỉ số phải hợp lệ. `GetByteArrayRegion` tương tự cho `jbyte[]`.
- `GetIntArrayElements`/`GetByteArrayElements`: trả pointer do JNI cung cấp, có thể là bản copy hoặc pin; nếu lấy thành công phải dùng `ReleaseIntArrayElements`/`ReleaseByteArrayElements` đúng cặp. Khi chỉ đọc, `JNI_ABORT` thường tránh copy-back không cần thiết.
- `GetPrimitiveArrayCritical`: dùng với hạn chế đặc biệt, không thực hiện I/O, thao tác chặn lâu hoặc JNI calls không được phép khi còn giữ critical pointer. Không chọn API này chỉ vì tưởng nó luôn không copy.
- `NewIntArray(0)`/`NewByteArray(0)`: tạo **mảng rỗng hợp lệ** nếu thành công. Khi tạo mảng từ `n` phần tử native, cần bảo đảm `n >= 0` và trong miền `jsize`, không ép âm thành số không dấu lớn.

**Không gắn nghĩa đặc biệt cho kết quả pointer trên mảng 0 phần tử.** Trên các JVM/API cụ thể, gọi array-elements cho mảng rỗng có thể có hành vi cấp buffer khác nhau; code không nên phụ thuộc “zero length ⇒ pointer luôn NULL” hoặc “pointer luôn non-NULL”. Đường an toàn là kiểm tra length rồi xử lý rỗng trước khi copy/read.

Với mảng tham chiếu `jobjectArray`, `GetObjectArrayElement` trả local reference (có thể `NULL` nếu phần tử Java thật sự null); khi duyệt rất nhiều phần tử, phải xóa local refs sau khi dùng hoặc dùng local frame hợp lý. `GetArrayLength` vẫn trả số phần tử, không phải số byte.

## 6. Kiểm tra chỉ số chống overflow trước khi tính địa chỉ

Giả sử Java truyền `start` và `count` cho một mảng dài `length`. Quy tắc chấp nhận một slice:

~~~text
start >= 0
count >= 0
start <= length
count <= length - start
~~~

Nếu cả bốn điều kiện đúng thì miền nửa mở `[start, start + count)` nằm trong mảng; một slice rỗng `count == 0` được phép bắt đầu tại `start == length`. Kiểm tra **trước khi** thực hiện phép cộng, vì mã sau có lỗi:

~~~c
/* SAI: start + count có thể signed overflow trước lúc so sánh. */
if (start + count > length) {
    /* reject */
}
~~~

Cách kiểm tra an toàn với `jint`/`jsize`:

~~~c
/* Mảnh C minh họa: các tham số đều là số nguyên JNI signed 32 bit. */
if (start < 0 || count < 0 ||
    start > length || count > length - start) {
    /* Báo IndexOutOfBoundsException, không truy cập buffer. */
}
~~~

Nhờ thứ tự short-circuit của `||`, phép trừ `length - start` chỉ được đánh giá sau khi đã xác nhận `start` không âm và không lớn hơn `length`. Trường hợp `start == length` và `count == 0` hợp lệ; `start == length` nhưng `count > 0` bị từ chối. Đừng dùng `start >= length` để từ chối mọi slice, vì như vậy bạn vô tình chặn cả empty slice hợp lệ.

| length | start | count | Hợp lệ? | Lý do |
| ---: | ---: | ---: | --- | --- |
| 0 | 0 | 0 | Có | Empty slice duy nhất của mảng rỗng |
| 4 | 4 | 0 | Có | Empty slice ở cuối mảng |
| 4 | 1 | 3 | Có | Đọc phần tử 1, 2, 3 |
| 4 | 3 | 2 | Không | Vượt cuối mảng |
| 4 | -1 | 1 | Không | Chỉ số âm |
| 4 | 2 | -1 | Không | Số phần tử âm |
| 4 | 2147483647 | 2147483647 | Không | Ngoài length; không được cộng trước khi kiểm tra |

Khi đổi từ `jlong`, `size_t`, `long` hoặc các thư viện C khác sang `jsize`, **kiểm tra miền trước khi ép kiểu**. Kiểu `jsize` là signed 32-bit theo JNI, còn `size_t` không dấu và có thể lớn hơn. Với buffer native, kiểm tra `count <= SIZE_MAX / sizeof(T)` **trước** phép nhân `count * sizeof(T)` và xác minh capacity theo đúng đơn vị.

**Chốt nghĩa vụ:** Kiểm tra biên ở Java có ích để báo lỗi sớm, nhưng native function cũng phải kiểm tra vì nó có thể được gọi qua đường khác hoặc nhận dữ liệu không hợp lệ. Một lỗi kiểm tra biên ở C có thể khiến JVM crash, chứ không chỉ sinh Java exception an toàn.

## 7. Ví dụ JNI đầy đủ: kiểm thử NUL, surrogate, mảng rỗng và bounds

Ví dụ gồm một file Java và một file C. Java truyền text chứa **U+0000** và emoji **U+1F600**, JNI đếm zero units, valid surrogate pairs và unpaired surrogates bằng `GetStringChars`; JNI sao chép lại String bằng `NewString` với chiều dài tường minh. Hai hàm khác tính tổng slice `int[]` và tổng **unsigned byte** từ `byte[]` theo chunk 64 phần tử bằng `Get<Type>ArrayRegion`.

Tạo thư mục:

~~~text
jni-edges/
├── src/
│   └── demo/
│       └── StringArrayEdges.java
├── native/
│   └── edges.c
└── build/
    ├── classes/
    ├── include/
    └── lib/
~~~

### 7.1. Java 17: file `src/demo/StringArrayEdges.java`

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class StringArrayEdges {
    static {
        System.loadLibrary("edges");
    }

    private StringArrayEdges() {
    }

    // [U+0000 units, supplementary pairs, unpaired surrogates].
    private static native int[] inspect(String text);
    private static native String roundTrip(String text);
    private static native long sumIntRange(int[] values, int start, int count);
    private static native long sumUnsignedBytes(byte[] values, int start, int count);

    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String sample = "A" + '\0' + emoji + "Z";

        System.out.println("utf16Units=" + sample.length());
        System.out.println("codePoints=" +
                sample.codePointCount(0, sample.length()));
        System.out.println("utf8Bytes=" +
                sample.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("inspect=" + Arrays.toString(inspect(sample)));
        System.out.println("roundTripEqual=" + sample.equals(roundTrip(sample)));

        System.out.println("emptyString=" + Arrays.toString(inspect("")));
        System.out.println("emptyRoundTrip=" + "".equals(roundTrip("")));
        String loneHigh = new String(new char[] {(char) 0xD83D});
        System.out.println("loneSurrogate=" +
                Arrays.toString(inspect(loneHigh)));

        int[] integers = {7, -2, 9};
        System.out.println("sumInts=" + sumIntRange(integers, 1, 2));
        System.out.println("sumEmptyInts=" + sumIntRange(new int[0], 0, 0));

        byte[] bytes = {0, (byte) 0x80, (byte) 0xFF};
        System.out.println("unsignedByteSum=" +
                sumUnsignedBytes(bytes, 0, bytes.length));
        System.out.println("emptyBytes=" +
                sumUnsignedBytes(new byte[0], 0, 0));

        try {
            sumIntRange(integers, 2, 2);
            System.out.println("invalidRangeRejected=false");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("invalidRangeRejected=true");
        }
    }
}
~~~

Giải thích:

- `'\0'` là **một ký tự U+0000** trong Java, không phải null reference. Dùng literal escape phù hợp thay vì đặt byte NUL thật vào file source.
- `Character.toChars(0x1F600)` tạo hai UTF-16 code units. `new String(char[])` giữ cả cặp.
- `new char[] {(char) 0xD83D}` cố ý tạo high surrogate **không có** low surrogate để test dữ liệu không well-formed.
- `byte[]` trong Java chứa **signed** 8-bit values: `(byte)0x80 == -128`, `(byte)0xFF == -1`. Hàm native giải thích chúng theo unsigned byte 0–255 như hợp đồng của bài.
- Hai lệnh sum trên mảng rỗng hợp lệ và trả `0`. Tham số `start=2,count=2` với mảng ba phần tử là invalid range, native chủ động ném `IndexOutOfBoundsException`.

### 7.2. C11: file `native/edges.c`

Chạy `javac -h` ở mục 8 trước để sinh header `demo_StringArrayEdges.h`; C source include trực tiếp header sinh ra để compiler đối chiếu prototype JNI.

~~~c
#include "demo_StringArrayEdges.h"
#include <stdint.h>

enum { CHUNK_SIZE = 64 };

static void throw_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass ex = (*env)->FindClass(env, class_name);
    if (ex != NULL) {
        (*env)->ThrowNew(env, ex, message);
        (*env)->DeleteLocalRef(env, ex);
    }
}

static int require_text(JNIEnv *env, jstring text) {
    if (text != NULL) {
        return 1;
    }
    throw_java(env, "java/lang/NullPointerException", "text");
    return 0;
}

static int require_array(JNIEnv *env, jarray array) {
    if (array != NULL) {
        return 1;
    }
    throw_java(env, "java/lang/NullPointerException", "array");
    return 0;
}

static int valid_range(JNIEnv *env, jsize length,
                       jint start, jint count) {
    if (start < 0 || count < 0 ||
        start > length || count > length - start) {
        throw_java(env, "java/lang/IndexOutOfBoundsException",
                   "invalid array range");
        return 0;
    }
    return 1;
}

static int is_high(jchar c) {
    return c >= 0xD800 && c <= 0xDBFF;
}

static int is_low(jchar c) {
    return c >= 0xDC00 && c <= 0xDFFF;
}

JNIEXPORT jintArray JNICALL
Java_demo_StringArrayEdges_inspect(JNIEnv *env, jclass owner,
                                   jstring text) {
    (void)owner;
    if (!require_text(env, text)) {
        return NULL;
    }

    jsize length = (*env)->GetStringLength(env, text);
    jint stats[3] = {0, 0, 0};

    if (length > 0) {
        const jchar *chars = (*env)->GetStringChars(env, text, NULL);
        if (chars == NULL) {
            if (!(*env)->ExceptionCheck(env)) {
                throw_java(env, "java/lang/OutOfMemoryError",
                           "GetStringChars failed");
            }
            return NULL;
        }

        for (jsize i = 0; i < length; ++i) {
            jchar c = chars[i];
            if (c == 0) {
                ++stats[0];
            }

            if (is_high(c)) {
                if (i + 1 < length && is_low(chars[i + 1])) {
                    ++stats[1];
                    ++i; /* Cặp hợp lệ; bỏ low surrogate. */
                } else {
                    ++stats[2];
                }
            } else if (is_low(c)) {
                ++stats[2];
            }
        }
        (*env)->ReleaseStringChars(env, text, chars);
    }

    jintArray result = (*env)->NewIntArray(env, 3);
    if (result == NULL) {
        return NULL;
    }
    (*env)->SetIntArrayRegion(env, result, 0, 3, stats);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return result;
}

JNIEXPORT jstring JNICALL
Java_demo_StringArrayEdges_roundTrip(JNIEnv *env, jclass owner,
                                     jstring text) {
    (void)owner;
    if (!require_text(env, text)) {
        return NULL;
    }

    jsize length = (*env)->GetStringLength(env, text);
    if (length == 0) {
        /* JNI cho phép NULL pointer khi len == 0. */
        return (*env)->NewString(env, NULL, 0);
    }

    const jchar *chars = (*env)->GetStringChars(env, text, NULL);
    if (chars == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/OutOfMemoryError",
                       "GetStringChars failed");
        }
        return NULL;
    }

    /* NewString dùng len, không tìm terminator NUL. */
    jstring result = (*env)->NewString(env, chars, length);
    (*env)->ReleaseStringChars(env, text, chars);
    return result;
}

JNIEXPORT jlong JNICALL
Java_demo_StringArrayEdges_sumIntRange(JNIEnv *env, jclass owner,
                                       jintArray values, jint start,
                                       jint count) {
    (void)owner;
    if (!require_array(env, values)) {
        return 0;
    }
    jsize length = (*env)->GetArrayLength(env, values);
    if (!valid_range(env, length, start, count)) {
        return 0;
    }
    if (count == 0) {
        return 0; /* Không gọi region accessor với buffer rỗng. */
    }

    jint chunk[CHUNK_SIZE];
    jlong total = 0;
    jint offset = 0;

    while (offset < count) {
        jint remain = count - offset;
        jint take = remain < CHUNK_SIZE ? remain : CHUNK_SIZE;
        (*env)->GetIntArrayRegion(env, values,
                                  start + offset, take, chunk);
        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Exception tự truyền về Java. */
        }
        for (jint i = 0; i < take; ++i) {
            total += (jlong)chunk[i];
        }
        offset += take;
    }
    return total;
}

JNIEXPORT jlong JNICALL
Java_demo_StringArrayEdges_sumUnsignedBytes(JNIEnv *env, jclass owner,
                                            jbyteArray values, jint start,
                                            jint count) {
    (void)owner;
    if (!require_array(env, values)) {
        return 0;
    }
    jsize length = (*env)->GetArrayLength(env, values);
    if (!valid_range(env, length, start, count)) {
        return 0;
    }
    if (count == 0) {
        return 0;
    }

    jbyte chunk[CHUNK_SIZE];
    jlong total = 0;
    jint offset = 0;

    while (offset < count) {
        jint remain = count - offset;
        jint take = remain < CHUNK_SIZE ? remain : CHUNK_SIZE;
        (*env)->GetByteArrayRegion(env, values,
                                   start + offset, take, chunk);
        if ((*env)->ExceptionCheck(env)) {
            return 0;
        }
        for (jint i = 0; i < take; ++i) {
            /* jbyte là signed 8-bit; uint8_t diễn giải 0..255. */
            total += (jlong)(uint8_t)chunk[i];
        }
        offset += take;
    }
    return total;
}
~~~

Đây là mã C **đầy đủ** cho JNI library của ví dụ, không phải chương trình C standalone có `main`. Nó dùng `jni.h` do generated header include, và `stdint.h` cho `uint8_t`. Những nền tảng phổ biến chạy JDK 17 đều hỗ trợ số nguyên 8 bit, nhưng build vẫn phải dùng compiler và JDK đúng ABI.

### 7.3. Vì sao mã C tránh được các lỗi biên?

**Chuỗi:** `inspect` lấy `GetStringLength` và chỉ mượn `GetStringChars` nếu length dương; mọi lần mượn thành công đều có `ReleaseStringChars`. Vòng lặp nhận diện high surrogate có low surrogate theo sau bằng điều kiện kiểm tra `i + 1 < length` trước khi đọc. Nó đếm U+0000 bằng so sánh `c == 0` mà không bị cắt tại NUL. `roundTrip` truyền `length` rõ ràng cho `NewString`, nên cả NUL và surrogate pair được giữ nguyên. Với chuỗi rỗng, `NewString(env, NULL, 0)` là hợp lệ theo JNI.

**Mảng:** Hai hàm tính tổng kiểm tra null, length, start/count rồi trả 0 sớm cho empty slice. Khi có dữ liệu, `GetIntArrayRegion`/`GetByteArrayRegion` copy tối đa 64 phần tử một lần; địa chỉ native dùng một buffer stack có capacity chính xác 64 phần tử và không cần `Release...`. Các JNI region accessors có thể throw mà không báo bằng return code, nên mã kiểm tra `ExceptionCheck` trước khi đọc chunk. Không giữ pointer do JVM quản lý sau lời gọi.

**Overflow:** `start + offset` chỉ tính sau `valid_range`, với `0 <= offset <= count` và `start + count <= length <= INT32_MAX`; không thể vượt miền `jint` trong ví dụ. `total` dùng `jlong`, đủ chứa tổng của tối đa `INT32_MAX` số nguyên `jint`, vì trị tuyệt đối tối đa xấp xỉ `2^62`, nhỏ hơn giới hạn `jlong`. Tổng unsigned bytes tối đa `255 * INT32_MAX` cũng nằm trong `jlong`. Nếu một thuật toán nhân nhiều kích thước hoặc cộng các giá trị lớn hơn, vẫn phải kiểm tra miền riêng của thuật toán ấy.

**Lỗi JNI:** Mã chủ động ném `NullPointerException` hoặc `IndexOutOfBoundsException` với input không hợp lệ. Sau một JNI operation thất bại, native không tiếp tục đọc dữ liệu chưa có; một exception đang pending được JVM truyền về Java khi native return. `GetStringChars` trả `NULL` có thể báo lỗi cấp phát; ví dụ kiểm tra pending exception trước khi ném `OutOfMemoryError` dự phòng.

## 8. Build và chạy trên Java 17+

Chạy từ thư mục `jni-edges`. Cần JDK chứa `jni.h`, compiler C11, và binary native có cùng kiến trúc CPU với JVM. Đặt `JAVA_HOME` tới đường dẫn JDK, không phải thư mục `bin`.

### 8.1. Linux + GCC/Clang

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/StringArrayEdges.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -Ibuild/include native/edges.c \
  -o build/lib/libedges.so

java -Djava.library.path=build/lib -cp build/classes demo.StringArrayEdges
~~~

### 8.2. macOS + Clang

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/StringArrayEdges.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include native/edges.c \
  -o build/lib/libedges.dylib

java -Djava.library.path=build/lib -cp build/classes demo.StringArrayEdges
~~~

### 8.3. Windows x64 + MSVC Developer Command Prompt

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib
javac -h build\include -d build\classes src\demo\StringArrayEdges.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" native\edges.c ^
  /link /OUT:build\lib\edges.dll

java -Djava.library.path=build\lib -cp build\classes demo.StringArrayEdges
~~~

Các lệnh Windows trên dành cho **Command Prompt**, dùng `^` nối dòng. `System.loadLibrary("edges")` tự ánh xạ tên logic sang `libedges.so`, `libedges.dylib` hoặc `edges.dll` tùy nền tảng. `javac -h` tạo `build/include/demo_StringArrayEdges.h`; khi đổi Java method signature hoặc package, phải chạy lại build header và thư viện.

### 8.4. Stdout kỳ vọng

Khi build/load thành công và chạy lớp `demo.StringArrayEdges`, stdout chính xác là:

~~~text
utf16Units=5
codePoints=4
utf8Bytes=7
inspect=[1, 1, 0]
roundTripEqual=true
emptyString=[0, 0, 0]
emptyRoundTrip=true
loneSurrogate=[0, 0, 1]
sumInts=7
sumEmptyInts=0
unsignedByteSum=383
emptyBytes=0
invalidRangeRejected=true
~~~

Đối chiếu:

- `inspect=[1, 1, 0]`: có một U+0000, một surrogate pair (emoji), không có surrogate lẻ.
- `loneSurrogate=[0, 0, 1]`: riêng high surrogate bị đếm là một lỗi cấu trúc UTF-16 nếu API cần well-formed Unicode.
- `roundTripEqual=true`: `NewString` với độ dài tường minh giữ chính xác chuỗi, kể cả NUL và cặp surrogate.
- `sumInts=7`: lấy `-2 + 9` từ slice `start=1,count=2`.
- `unsignedByteSum=383`: bytes theo unsigned là 0, 128, 255. Java `byte[]` vẫn lưu các bit tương ứng dù xem kiểu signed.
- `invalidRangeRejected=true`: native ném `IndexOutOfBoundsException` và Java bắt đúng exception.

Output trên xác minh theo logic nguồn; compiler/toolchain thực tế phụ thuộc máy và phải được kiểm thử ở target platform. Khi lỗi load, kiểm tra `java.library.path`, tên thư viện đúng OS và kiến trúc; khi lỗi `UnsatisfiedLinkError` lúc gọi, kiểm tra exported JNI symbols và header đã tạo từ Java source.

## 9. API dùng buffer: checklist dung lượng và ownership

Đặt các câu hỏi này trước khi nối Java String/array vào C library:

1. **Đơn vị length:** Java UTF-16 units, Unicode code points, UTF-8 bytes, MUTF-8 bytes hay số phần tử mảng?
2. **NUL:** U+0000 có được phép trong dữ liệu? C API có nhận length tường minh hay chỉ C string?
3. **Encoding:** C library đòi UTF-8 chuẩn, UTF-16, MUTF-8 hay byte payload bất kỳ? Có policy cho surrogate lẻ/invalid input?
4. **Capacity:** Buffer native có đủ chứa dữ liệu và terminator nếu **giao thức riêng** đòi hỏi không? Có checked multiplication/addition khi cấp phát?
5. **Ownership:** Pointer do `GetStringChars`/`GetStringUTFChars`/`Get<Type>ArrayElements` trả ra thuộc JVM; khi dùng xong phải gọi đúng Release; không `free`.
6. **Thread:** Có đưa pointer borrowed qua thread khác hoặc callback asynchronous không? Nếu có, phải copy dữ liệu vào vùng sở hữu riêng có lifetime phù hợp, không giữ pointer JNI sau release.
7. **Bounds:** Có check null, negative start/count, `start<=length`, `count<=length-start` và chuyển đổi kiểu trước khi đọc không?
8. **Failure:** Nếu `Get...` trả `NULL`, `NewString` trả `NULL` hoặc `Get...Region` throw, native có trả về ngay và không sử dụng buffer chưa khởi tạo không?

### 9.1. Khi cần copy một phần String thành C buffer

`GetStringRegion(env, string, start, count, jchar_buffer)` làm việc theo UTF-16 code units. Nếu buffer gồm `capacity` phần tử `jchar`, điều kiện tối thiểu là `capacity >= count`. Để tránh overflow khi malloc:

~~~c
/* Mảnh minh họa với count >= 0; buffer owned bởi C. */
size_t n = (size_t)count;
if (n > SIZE_MAX / sizeof(jchar)) {
    /* reject size overflow */
} else {
    jchar *buf = malloc(n * sizeof(jchar));
    /* kiểm tra malloc; n=0 xử lý riêng rồi mới GetStringRegion */
}
~~~

Tệp C thực cần include `<stdint.h>`/`<stdint.h>` hoặc `<stdint.h>` tùy macro `SIZE_MAX` và `<stdlib.h>` cho `malloc`; phần quan trọng là mẫu kiểm tra trước phép nhân. Với `n=0`, không cần gọi accessor hoặc cấp phát: xử lý kết quả rỗng riêng, tránh suy diễn từ `malloc(0)`.

Khi copy MUTF-8 bằng `GetStringUTFRegion`, một code unit có thể tạo tối đa ba byte, nên cần tối đa `3*n` byte payload, cộng một nếu **bạn** muốn thêm terminator. Không đọc với `strlen` nếu chưa chủ động bảo đảm terminator hợp lệ, và không nhầm `3*n` với size của UTF-8 chuẩn.

### 9.2. Tạo mảng Java từ native

`NewByteArray(env, length)` và `NewIntArray(env, length)` nhận `jsize` không âm; cả hai có thể tạo mảng rỗng nếu length 0. Sau khi tạo mảng mới, chỉ gọi `SetByteArrayRegion`/`SetIntArrayRegion` với range hợp lệ và buffer đủ số phần tử; với length 0 không cần copy.

Một native API trả về pointer cùng `size_t length` phải kiểm tra `length <= INT32_MAX` (hoặc giới hạn `jsize` có ý nghĩa) trước `NewByteArray((jsize)length)`. Đừng ép `size_t` 64 bit thành `jsize` 32 bit trước rồi mới kiểm tra, vì dữ liệu có thể đã bị cắt/trở thành số âm. Khi dữ liệu thật sự vượt kích thước Java array, cần streaming/chunking hoặc một cơ chế buffer khác được thiết kế rõ.

## 10. Kiểm thử theo ma trận biên

| Input | Kết quả đúng | Lỗi thường gặp |
| --- | --- | --- |
| `""` | `GetStringLength=0`; round-trip ra `""` | Tưởng null String, truy cập phần tử 0 |
| `"A\0B"` | Length 3, U+0000 ở vị trí 1 | Dùng `strlen` cắt thành `"A"` |
| `"A" + U+1F600 + "Z"` | UTF-16 length 4, code points 3 | Đếm `jchar` như code points |
| High surrogate cuối chuỗi | Không đọc `chars[i+1]` | Out-of-bounds/UB |
| Lone low surrogate | Nhận diện invalid Unicode scalar sequence | Tự ghép sai với phần tử trước |
| `new int[0], start=0,count=0` | Sum 0, không đọc phần tử nào | Dereference `data[0]` |
| `new byte[]{0}` | Một phần tử 0, không phải mảng rỗng | Dùng sentinel NUL để tính array length |
| `byte[]{(byte)0xFF}` | Unsigned interpretation 255 nếu API yêu cầu | Tính thành -1 khi bỏ qua signedness |
| `start=length,count=0` | Empty slice hợp lệ | Dùng `start>=length` từ chối sai |
| `start=length,count=1` | Ném lỗi range | Bỏ qua capacity |
| `start<0` hoặc `count<0` | Ném lỗi trước khi ép unsigned | Ép thành `size_t` tạo số rất lớn |
| `start=INT_MAX,count=INT_MAX` với mảng nhỏ | Ném lỗi, không thực hiện cộng | Signed overflow trong `start+count` |
| `null` String/array | Báo `NullPointerException` rõ ràng | Gọi JNI API không cho phép null |
| `GetStringChars==NULL` | Thoát có xử lý lỗi; không dereference | Tiếp tục dùng pointer lỗi |
| `Get...Region` có pending exception | Thoát trước khi đọc buffer đích | Đọc dữ liệu chưa được copy đầy đủ |

Với bộ test tự động, nên kiểm tra cả **nội dung và số đơn vị độ dài**. Test so sánh text sau round-trip mà không có U+0000 hoặc surrogate có thể bỏ lọt lỗi truncation. Test chỉ dùng mảng có ít nhất một phần tử cũng không phát hiện path `length==0`.

Khi cần kiểm tra hành vi JNI kỹ hơn, chạy:

~~~sh
java -Xcheck:jni -Djava.library.path=build/lib \
  -cp build/classes demo.StringArrayEdges
~~~

`-Xcheck:jni` giúp phát hiện một số cách gọi JNI sai tùy JVM, nhưng không bảo đảm phát hiện mọi lỗi C như invalid pointer, buffer overflow hoặc data race. Với compiler phù hợp, chạy thêm AddressSanitizer/UndefinedBehaviorSanitizer và kiểm thử với input lớn trên đúng OS/architecture.

## 11. Những lỗi sai phổ biến và cách khắc phục

**Sai 1: Dùng `GetStringUTFChars` để gửi UTF-8 chuẩn.** MUTF-8 không phải UTF-8 chuẩn khi có U+0000 hoặc non-BMP. Cần encoder/decoder UTF-8 chuẩn và độ dài byte rõ ràng cho API ngoài JNI.

**Sai 2: Dùng `strlen` để đo Java String.** Java String có NUL và UTF-16; C strlen đo byte trước terminator trong C string. Chọn `GetStringLength` cho UTF-16 units, `codePointCount` khi cần code points, `byte[].length` khi có encoding UTF-8 cụ thể.

**Sai 3: Coi hai `jchar` là hai emoji.** Một non-BMP code point gồm hai surrogate units. Khi cần Unicode scalar values, phải ghép đúng cặp và từ chối/định nghĩa policy cho unpaired surrogates.

**Sai 4: Đưa 4-byte UTF-8 emoji vào `NewStringUTF`.** JNI NewStringUTF nhận MUTF-8; input UTF-8 ngoài JNI cần giải mã rõ ràng trước.

**Sai 5: Mảng rỗng được xử lý như một pointer có ít nhất một phần tử.** `GetArrayLength == 0` nghĩa là không được đọc phần tử; trả kết quả rỗng/sum0 mà không dereference.

**Sai 6: Xác minh `start + count <= length` bằng kiểu signed.** Phép cộng có thể overflow trước khi so sánh. Thay bằng guard `start>=0, count>=0, start<=length, count<=length-start`.

**Sai 7: Quên release pointer JNI.** `GetStringChars` và `Get...ArrayElements` yêu cầu cặp Release khi trả pointer thành công, kể cả chỉ đọc. Không lấy `NULL` hay mảng rỗng làm lý do gọi Release với pointer chưa lấy hợp lệ.

**Sai 8: Nhầm byte với phần tử.** `memcpy` và UTF-8 đo byte, `GetIntArrayRegion` đo số `jint`, `GetStringRegion` đo UTF-16 units. Mỗi API có đơn vị riêng.

**Sai 9: Trộn lỗi Java và lỗi native.** Một JNI region accessor trả void vẫn có thể throw; phải kiểm tra pending exception trước khi dùng buffer đích. Native code không được tự ý bỏ exception rồi tiếp tục báo thành công.

**Sai 10: Phân tích grapheme theo code point.** Một glyph/emoji có thể gồm nhiều code points; phân tích theo surrogate/code point chỉ giải quyết encoding, không tự giải quyết ngôn ngữ hiển thị.

## 12. Bảng tự kiểm trước khi triển khai JNI String/array API

- Java `null` và String/array rỗng có đường xử lý **khác nhau**, thông báo lỗi đúng contract.
- NUL U+0000 được cho phép hoặc từ chối có chủ đích; không mất dữ liệu vì hàm C string.
- Đã chọn **UTF-16**, **UTF-8 chuẩn** hay **MUTF-8** theo consumer; không gán chúng cùng một ý nghĩa.
- Độ dài là **byte / UTF-16 code units / code points / phần tử**, được ghi ngay trong prototype và docs.
- Đã kiểm tra surrogate pairs, unpaired surrogates và chính sách với Unicode không well-formed.
- Buffer được cấp theo capacity đúng đơn vị; kiểm tra overflow trước `count*sizeof(T)`, `3*len+1` hoặc phép cộng offset.
- Một empty slice `(start==length,count==0)` hợp lệ nếu API quy định; không gọi accessor bất cẩn với zero length.
- Không dereference con trỏ null, không truy cập `index==length`, không để overflow trong `start+count`.
- Mọi JNI borrowed pointer đều được release đúng cặp trên mọi đường thoát.
- Có kiểm tra lỗi sau hàm JNI trả `NULL` và sau `Get...Region` trả void; exception được chuyển về Java hợp lý.
- Kiểm thử mảng rỗng, Unicode ngoài BMP, embedded U+0000, negative/oversized slice và dữ liệu byte chứa 0x00/0x80/0xFF.
- Build native library cho đúng OS/ABI; chạy test thật với JDK mục tiêu và bật kiểm tra JNI khi phù hợp.

**Nguyên tắc cốt lõi:** JNI không tự hiểu bạn đang đếm byte hay Unicode, cũng không tự biến dữ liệu rỗng thành buffer có thể dereference. Xác định rõ encoding, đơn vị độ dài, quyền sở hữu và miền chỉ số **trước** khi truy cập native memory là cách tránh lỗi mất dữ liệu và lỗi vượt biên.

### Tài liệu tham khảo

- Oracle, [JNI Specification — Functions (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): String Operations, Array Operations, Get/Release, Region, NewString và exception contracts.
- Oracle, [JNI Specification — Types (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `jchar`, `jsize`, `jstring` và primitive array types.
- Oracle, [JNI Specification — Design Overview (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): Java exceptions và nguyên tắc gọi JNI.
- Oracle, [Java Language Specification `3.1–3.2 (Java 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html): UTF-16 và supplementary characters.
- Oracle, [Java SE 17 String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `codePointCount`, `getBytes`.