# Thứ tự byte, căn chỉnh địa chỉ và byte đệm của `struct` trong C và tương tác với Java

## Mục tiêu

Khi Java trao đổi dữ liệu với mã native, một nhóm byte chỉ có ý nghĩa khi hai phía thống nhất **thứ tự byte (endianness)**, **vị trí/căn chỉnh trường (alignment)** và **byte đệm (padding)**. Ba quy tắc này liên quan nhưng không thay thế nhau. Sau bài học, bạn có thể:

- Đọc đúng biểu diễn byte của giá trị nhiều byte trên máy little-endian và big-endian.
- Dự đoán layout `struct` theo một ABI đã biết, rồi kiểm tra bằng `sizeof`, `_Alignof` và `offsetof` thay vì coi dự đoán là hợp đồng phổ quát.
- Hiểu vì sao tổng kích thước các field có thể nhỏ hơn `sizeof(struct)`, và vì sao mảng `struct` còn cần tail padding.
- Ánh xạ đúng các offset khi dùng `ByteBuffer` ở Java; biết khi nào phải dùng định dạng wire độc lập với ABI.
- Tránh lỗi đọc nhầm số, truy cập lệch căn chỉnh, so sánh/ghi thẳng vùng nhớ có padding và phụ thuộc sai vào compiler/platform.

## 1. Ba khái niệm độc lập

| Khái niệm | Quyết định điều gì? | Minh họa |
|---|---|---|
| **Endianness** | Thứ tự các byte của *một giá trị nhiều byte* trong bộ nhớ hoặc định dạng dữ liệu | `0x01020304` có thể là `04 03 02 01` hoặc `01 02 03 04` |
| **Alignment** | Địa chỉ nào hợp lệ/thích hợp để đặt một đối tượng hoặc trường; thường là bội của một số byte | Một field 4 byte có thể cần bắt đầu ở offset chia hết cho 4 |
| **Padding** | Các byte được chèn giữa trường hoặc ở cuối `struct` để đáp ứng layout/alignment | Sau `char` 1 byte có thể có 3 byte đệm trước `uint32_t` |

**ABI (Application Binary Interface)** là tập quy ước nhị phân mà các thành phần biên dịch riêng phải cùng tuân thủ. Tùy nền tảng, nó có thể chi phối kích thước/alignment kiểu C, cách đặt field, truyền tham số, giá trị trả về và quy ước gọi hàm. Cùng mã nguồn C vẫn có thể có layout khác trên ABI hoặc cấu hình compiler khác. Endianness của CPU cũng không đủ để suy ra toàn bộ ABI.

## 2. Endianness: giá trị số và thứ tự byte

Giả sử ta muốn lưu số nguyên 32 bit `0x01020304` vào bốn byte liên tiếp, địa chỉ tăng từ trái sang phải:

~~~text
Địa chỉ tăng →      +0  +1  +2  +3
Little-endian:      04  03  02  01
Big-endian:         01  02  03  04
Giá trị logic:      0x01020304 (giống nhau)
~~~

- **Little-endian:** byte có trọng số thấp nhất ở địa chỉ thấp nhất. Đây là thứ tự phổ biến trên x86/x64 và nhiều hệ ARM khi chạy ở chế độ little-endian.
- **Big-endian:** byte có trọng số cao nhất ở địa chỉ thấp nhất. Nhiều định dạng giao thức định nghĩa thứ tự này; thuật ngữ *network byte order* thường chỉ big-endian.
- Endianness **không đảo thứ tự các phần tử** trong mảng và **không tự thay đổi offset field** của `struct`. Nó quyết định cách những byte *bên trong một giá trị nhiều byte* được diễn giải.
- Với giá trị một byte, không có lựa chọn thứ tự giữa nhiều byte. Thứ tự bit trong một byte hay bố trí C bit-field là câu chuyện khác; không nên suy ra từ little-endian/big-endian.

Ví dụ byte `01 02 03 04` đọc như số nguyên unsigned 32 bit sẽ cho:

~~~text
Big-endian:    0x01020304
Little-endian: 0x04030201
~~~

**Hệ quả:** một buffer ghi bằng little-endian nhưng được đọc bằng big-endian sẽ cho sai giá trị dù số byte và offset đều chính xác. Với dữ liệu lưu file, mạng hoặc wire protocol, hãy quy định endianness một cách tường minh; không dựa ngầm vào `ByteOrder.nativeOrder()`.

## 3. Alignment: địa chỉ và ràng buộc ABI

Một kiểu C có yêu cầu căn chỉnh (alignment requirement). Nếu `alignof(T) = A`, địa chỉ hợp lệ của đối tượng `T` phải đáp ứng ràng buộc căn chỉnh đó; trên ABI thông dụng, địa chỉ thường phải là bội của `A`. Ví dụ field có alignment 4 thường nằm ở offset 0, 4, 8, 12, ... so với đầu `struct` được căn chỉnh phù hợp.

Khi đặt lần lượt các trường, compiler thường áp dụng cách tính:

1. Đặt offset trường đầu tiên theo layout của kiểu.
2. Trước mỗi trường kế tiếp, làm tròn offset hiện tại lên bội số của alignment mà ABI yêu cầu cho trường đó.
3. Sau field cuối, làm tròn tổng kích thước theo alignment của chính `struct` để mỗi phần tử của mảng `struct` cũng được căn chỉnh.

Hàm làm tròn chung cho offset không âm và `A > 0`:

~~~text
align_up(offset, A) = ceil(offset / A) * A
~~~

Chẳng hạn `align_up(1, 4) = 4` nên có 3 byte đệm. Trên nhiều ABI, alignment của `struct` bằng alignment lớn nhất trong các field, nhưng compiler, ABI và thuộc tính layout có thể áp dụng ràng buộc khác; **hãy đo cấu trúc thực tế**.

Truy cập đối tượng C thông qua con trỏ không đáp ứng alignment của kiểu có thể gây **undefined behavior**, dù trên một CPU cụ thể truy cập lệch căn chỉnh đôi lúc vẫn chạy. Có kiến trúc gây lỗi phần cứng; kiến trúc khác chạy chậm hơn hoặc compiler tối ưu dựa trên giả định địa chỉ đã căn đúng. Không suy luận rằng “chạy được trên máy mình” đồng nghĩa với an toàn.

## 4. Internal padding, tail padding và kích thước thật

Xét một `struct` C:

~~~c
struct Record {
    char tag;        // 1 byte nếu CHAR_BIT == 8
    uint32_t value;  // 4 byte nếu CHAR_BIT == 8 và kiểu tồn tại
    uint16_t code;   // 2 byte nếu CHAR_BIT == 8 và kiểu tồn tại
};
~~~

Trên một ABI thông dụng có `CHAR_BIT = 8`, alignment của `char` là 1, `uint32_t` là 4 và `uint16_t` là 2, bố trí có thể là:

| Offset | Số byte | Nội dung |
|---:|---:|---|
| 0 | 1 | `tag` |
| 1–3 | 3 | **Internal padding** trước `value` |
| 4–7 | 4 | `value` |
| 8–9 | 2 | `code` |
| 10–11 | 2 | **Tail padding** cuối `struct` |

~~~text
Offset:  00 | 01 02 03 | 04 05 06 07 | 08 09 | 10 11
         tag|  padding |    value    |  code | padding
sizeof(struct Record) = 12 byte; alignment thường là 4
Tổng byte field hữu ích = 1 + 4 + 2 = 7 byte
~~~

**Internal padding** phục vụ căn chỉnh field phía sau. **Tail padding** phục vụ căn chỉnh phần tử kế tiếp trong mảng: nếu `Record records[2]`, phần tử thứ hai thường bắt đầu tại `base + 12`, không phải `base + 10` hoặc `base + 7`. `sizeof(struct Record)` đo cả phần padding và chính là bước nhảy giữa các phần tử mảng.

Các con số trên là **ví dụ theo giả định ABI**, không phải quy luật layout cố định của mọi compiler. Kiểu `uint32_t`/`uint16_t` đến từ `<stdint.h>` và chỉ hiện diện khi môi trường cung cấp kiểu có độ rộng đúng như tên; kích thước byte C còn phụ thuộc `CHAR_BIT`. Không tự giả định `long`, `size_t`, con trỏ hay `enum` có cùng kích thước trên mọi kiến trúc: chẳng hạn Windows 64-bit thường dùng mô hình LLP64, trong khi nhiều hệ Unix 64-bit dùng LP64.

### Đo bằng chương trình C11

Lưu mã sau vào file `record.c`:

~~~c
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

struct Record {
    char tag;
    uint32_t value;
    uint16_t code;
};

int main(void) {
    printf("CHAR_BIT=%d\n", CHAR_BIT);
    printf("sizeof=%zu, align=%zu\n",
           sizeof(struct Record), _Alignof(struct Record));
    printf("offsets: tag=%zu, value=%zu, code=%zu\n",
           offsetof(struct Record, tag),
           offsetof(struct Record, value),
           offsetof(struct Record, code));
    return 0;
}
~~~

Biên dịch với GCC hoặc Clang hỗ trợ C11:

~~~bash
gcc -std=c11 -Wall -Wextra -pedantic record.c -o record
./record
~~~

Một kết quả **thường gặp** trên x86-64 là:

~~~text
CHAR_BIT=8
sizeof=12, align=4
offsets: tag=0, value=4, code=8
~~~

Nếu máy của bạn in số khác, layout do môi trường vừa đo mới là dữ liệu phải dùng để tương tác native. `offsetof` nhận tên một member thông thường; không sử dụng nó để suy offset của C bit-field. Dùng `_Static_assert` khi một ABI cụ thể là điều kiện bắt buộc của chương trình, chẳng hạn:

~~~c
_Static_assert(offsetof(struct Record, value) == 4,
               "Unexpected Record.value offset");
_Static_assert(sizeof(struct Record) == 12,
               "Unexpected Record size");
~~~

Đặt các kiểm tra này trong source chỉ khi đã **chủ đích yêu cầu** layout 12 byte cho target tương ứng; chúng giúp biên dịch thất bại sớm khi ABI không khớp, nhưng không biến layout đó thành portable.

## 5. Nhìn cả endianness *lẫn* padding trong cùng một buffer

Giả sử ABI đo được layout 12 byte như trên, `tag = 0x7A`, `value = 0x01020304` và `code = 0x0506`. Nếu biểu diễn `value` và `code` theo little-endian, ta muốn chuỗi byte quy định rõ ràng như sau:

~~~text
Offset:  00 01 02 03 04 05 06 07 08 09 10 11
Byte:    7A 00 00 00 04 03 02 01 06 05 00 00
         └tag┘ pad   └─ value ───┘ └code┘ pad
~~~

Ở đây các byte đệm được **chủ động đặt thành 00 trong định dạng ví dụ**. Với một đối tượng `struct` C thông thường, byte padding có thể chứa giá trị không xác định/không đáng tin để sử dụng làm dữ liệu: không nên coi toàn bộ `sizeof(struct)` byte là định dạng tuần tự hóa ổn định. Việc compiler sinh padding và endianness của các số nguyên là hai quyết định khác nhau.

Nếu đổi sang big-endian nhưng **giữ nguyên layout field**, các offset vẫn là 0, 4, 8; chỉ các byte thuộc `value` và `code` đổi thứ tự:

~~~text
Offset:  00 01 02 03 04 05 06 07 08 09 10 11
Byte:    7A 00 00 00 01 02 03 04 05 06 00 00
~~~

Cần kiểm tra thêm kích thước, signedness và quy ước mã hóa từng field nếu bên Java và C trao đổi giá trị có dấu, số thực hoặc các kiểu không có độ rộng cố định.

## 6. Ánh xạ layout minh bạch trong Java 17 bằng ByteBuffer

`ByteBuffer` cho phép đặt endianness cho các thao tác đọc/ghi nhiều byte, nhưng **không tự thêm padding theo C ABI**. Ta phải dùng offset đã kiểm chứng. Ví dụ này xây đúng 12 byte minh họa little-endian ở mục trước.

Lưu vào `LayoutDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class LayoutDemo {
    public static void main(String[] args) {
        ByteBuffer data = ByteBuffer.allocate(12)
                .order(ByteOrder.LITTLE_ENDIAN);

        // Offset từ layout C đã kiểm chứng: tag=0, value=4, code=8.
        // Bộ nhớ được allocate() khởi tạo 0, nên các offset đệm là 00.
        data.put(0, (byte) 0x7A);
        data.putInt(4, 0x01020304);
        data.putShort(8, (short) 0x0506);

        for (int i = 0; i < data.capacity(); i++) {
            System.out.printf("%02X%s", data.get(i) & 0xFF,
                    i == data.capacity() - 1 ? "\n" : " ");
        }

        System.out.printf("value=0x%08X, code=0x%04X%n",
                data.getInt(4), data.getShort(8) & 0xFFFF);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac LayoutDemo.java
java LayoutDemo
~~~

Đầu ra:

~~~text
7A 00 00 00 04 03 02 01 06 05 00 00
value=0x01020304, code=0x0506
~~~

Giải thích những điểm dễ nhầm:

- `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` điều khiển việc giải mã/ghi `short`, `int`, `long`, v.v.; `put(int index, byte b)` chỉ ghi một byte.
- `ByteBuffer` mặc định có byte order **BIG_ENDIAN**; hãy thiết lập rõ theo hợp đồng dữ liệu. `ByteOrder.nativeOrder()` chỉ phản ánh thứ tự native của máy chạy Java, không đại diện cho một giao thức/file và không tự chỉ ra padding.
- `data.putInt(4, ...)` ghi từ offset 4 chính xác vì **chúng ta chọn 4**, không phải vì `ByteBuffer` biết `struct Record`. `putInt(1, ...)` trên heap buffer cũng ghi được byte, nhưng sẽ không tương ứng với layout C vừa đo.
- `byte` của Java là kiểu signed, nên dùng `data.get(i) & 0xFF` khi cần in giá trị byte 0–255. Với C `uint16_t`, `short` của Java cũng signed; `& 0xFFFF` giúp đọc giá trị unsigned 16 bit ở mức số học.
- Đây là **bản dựng byte trong Java**, không có nghĩa Java heap `ByteBuffer` là con trỏ native của `struct`. Để chia sẻ bộ nhớ thật với C qua JNI hoặc Foreign Function & Memory API, cần tuân thủ thêm lifetime, ownership, địa chỉ, độ an toàn truy cập và ABI của đối tượng native.

Trong Java mới hơn, Foreign Function & Memory API (ổn định từ JDK 22) cung cấp `MemoryLayout`, `MemorySegment` và các `ValueLayout` để mô tả/đọc bộ nhớ native. Vẫn phải xác định rõ kích thước, alignment, byte order và những padding cần thiết khi mô hình hóa C `struct`; không suy đoán layout chỉ từ tên kiểu Java.

## 7. Tại sao không được ghi thẳng `struct` ra file hoặc mạng?

Một thao tác C kiểu:

~~~c
// Phản ví dụ đối với định dạng file/network độc lập nền tảng:
fwrite(&record, sizeof record, 1, file);
~~~

có thể ghi cả **internal/tail padding**. Nội dung padding không phải field có nghĩa, có thể không ổn định qua các lần gán và có nguy cơ chứa byte bộ nhớ không mong muốn. Thêm nữa, raw dump mang theo endianness, alignment, kích thước kiểu và quy tắc layout của môi trường tạo ra nó. File được tạo trên ABI A không nhất thiết đọc đúng trên ABI B, ngay cả khi tên `struct` giống nhau.

Tương tự, `memcmp(&a, &b, sizeof a) == 0` không phải phép so sánh giá trị logic đáng tin của hai `struct`: hai object có các field bằng nhau vẫn có thể khác byte padding. Hãy so sánh từng field có nghĩa.

**Định dạng wire tốt hơn:** định nghĩa tuần tự một chuỗi field, không sao chép `struct` trực tiếp. Chẳng hạn `Record` có thể được mã hóa thành **7 byte**:

~~~text
Byte 0       : tag (1 byte)
Byte 1..4    : value (uint32, big-endian theo giao thức)
Byte 5..6    : code (uint16, big-endian theo giao thức)
Tổng         : 7 byte; không mang theo C padding
~~~

Hợp đồng này phải ghi rõ kích thước, thứ tự byte, signedness, encoding của chuỗi (nếu có), version và xử lý giá trị không hợp lệ. Phía Java và C cùng giải mã theo hợp đồng này, không cần cùng ABI. Nếu bắt buộc truyền **mảng `struct` trong memory native**, trái lại phải lấy đúng C layout trên cùng target ABI và dùng stride bằng `sizeof(struct Record)`.

## 8. Truy cập lệch căn chỉnh, packed struct và dữ liệu nhị phân

### Con trỏ lệch căn chỉnh

Không nên chuyển tùy tiện địa chỉ của một mảng byte thành con trỏ có alignment chặt hơn:

~~~c
// Sai/không an toàn: buf+1 có thể không căn chỉnh đúng cho uint32_t.
uint32_t *p = (uint32_t *)(buf + 1);
uint32_t value = *p;
~~~

Ngay cả khi buffer đủ số byte, dereference như vậy có thể vi phạm alignment hoặc quy tắc effective type của C. Khi đọc bytes từ một buffer, `memcpy` vào một biến có kiểu phù hợp tránh dereference con trỏ lệch căn chỉnh:

~~~c
uint32_t value;
memcpy(&value, buf + 1, sizeof value); // buf phải chứa đủ byte
~~~

Cách `memcpy` này chỉ sao chép byte: **không tự chuyển endianness**. Nếu dữ liệu tuân theo network byte order, hãy giải mã thứ tự byte tường minh hoặc dùng API chuyển đổi thích hợp. Include `<string.h>` cho `memcpy`.

### `packed` và pragma

`#pragma pack` (như trên MSVC) hoặc `__attribute__((packed))` (như trên GCC/Clang) là mở rộng theo compiler. Chúng có thể giảm/thay đổi padding và alignment, nhưng đổi luôn hợp đồng layout, có thể tạo field chưa căn chỉnh và gây truy cập chậm/lỗi trên một số target. Lấy địa chỉ của packed field làm con trỏ kiểu bình thường rồi dereference là đặc biệt nguy hiểm. Chỉ dùng khi đặc tả nhị phân và compiler/target được kiểm soát, rồi kiểm tra `sizeof`, `offsetof` và cách code truy cập thực tế.

### Bit-field, union và kiểu có biểu diễn phụ thuộc môi trường

Bố trí bit-field C (đơn vị cấp phát, thứ tự bit, việc trải qua boundary) phụ thuộc implementation/ABI, nên không thích hợp để định nghĩa giao thức portable bằng cách dump nguyên vùng nhớ. `union` chia sẻ vùng lưu trữ giữa các member; việc đọc diễn giải phải xét quy tắc C và biểu diễn dữ liệu, không thể chỉ dựa vào endianness. Cũng không gửi trực tiếp `long`, con trỏ, `size_t` hoặc native `struct` qua ranh giới hệ thống mà chưa chuẩn hóa độ rộng và layout.

## 9. Quy trình kiểm tra layout khi làm JNI/FFM hoặc đọc binary

1. **Xác định hợp đồng:** dữ liệu là native in-memory ABI hay file/wire format? Nếu là wire, quy định từng byte độc lập ABI; nếu là native, xác định OS, kiến trúc, compiler, cờ ABI/packing và phiên bản thư viện.
2. **Kiểm tra C thật:** đo `CHAR_BIT`, `sizeof(type)`, `_Alignof(type)`, `offsetof(type, field)` và `sizeof(struct)`. Với định dạng C native bắt buộc, đặt `_Static_assert` cho những offset/kích thước đã được xác nhận.
3. **Phân biệt field và padding:** lập bảng offset–size–alignment; nếu là mảng, dùng stride `sizeof(struct)`. Đừng đo layout qua tổng kích thước field.
4. **Thống nhất byte order:** xác định thứ tự riêng cho mỗi field nhiều byte; Java dùng `ByteBuffer.order(...)` hoặc layout/order tương ứng. Không hiểu chữ “native” là đồng nghĩa “little-endian” trên mọi máy.
5. **Đọc/ghi an toàn:** kiểm tra bounds, alignment, signedness và vòng đời bộ nhớ. Với raw buffer, tránh ép kiểu pointer lệch căn chỉnh; với wire format, tự mã hóa/giải mã các field.
6. **Kiểm thử bằng byte mẫu cố định:** chọn giá trị dễ thấy như `0x01020304`, in hex dump có offset, đối chiếu một mẫu C ↔ Java và kiểm tra cả vùng padding/stride khi cần.
7. **Thử môi trường khác nếu có hỗ trợ:** đổi target ABI/compiler/packing hoặc endianness của sample decode; test phải thất bại rõ nếu một giả định native không còn đúng.

## 10. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| `0x01020304` thành `0x04030201` | Đọc sai endianness | In hex dump, đặt byte order tường minh |
| Java đọc sai field thứ hai trở đi | Quên internal padding hoặc offset khác ABI | So `offsetof` C với index Java |
| Phần tử thứ hai của mảng sai dù phần tử đầu đúng | Bỏ qua tail padding | Dùng stride `sizeof(struct)`, không dùng tổng kích thước field |
| Chạy trên x86 nhưng lỗi/crash trên target khác | Dereference lệch căn chỉnh hoặc packed member | Kiểm tra alignment, dùng `memcpy`/accessor an toàn |
| Hai `struct` cùng field nhưng `memcmp` khác | Padding chứa byte khác nhau | So sánh field có nghĩa |
| File binary đọc sai trên hệ khác | Dump raw struct; khác endian/type size/ABI | Thiết kế wire format có độ rộng và thứ tự byte cố định |
| Bật `#pragma pack` làm crash/đổi API native | Bố trí field không còn khớp ABI thư viện | Bỏ override tùy tiện; xác minh compile flags và offset |

## 11. Tự luyện

**Bài 1 — dự đoán và kiểm chứng.** Trên ABI giả định `char` align 1, `uint16_t` align 2, `uint32_t` align 4, hãy đổi thứ tự khai báo thành:

~~~c
struct CompactRecord {
    uint32_t value;
    char tag;
    uint16_t code;
};
~~~

Dự đoán: `value` ở offset 0–3, `tag` ở 4, có một byte padding ở 5, `code` ở 6–7; `sizeof(struct CompactRecord) = 8` và alignment 4. Kiểm tra bằng chương trình C thay vì coi `8` là bảo đảm đa nền tảng. Bài học: **đổi thứ tự field có thể giảm padding**, nhưng cũng làm thay đổi ABI và không an toàn nếu thư viện phía bên kia vẫn dùng layout cũ.

**Bài 2 — đọc byte.** Với dãy `11 22 33 44`, giá trị unsigned 32 bit là `0x11223344` theo big-endian và `0x44332211` theo little-endian. Hãy thử `ByteBuffer.wrap(new byte[]{0x11, 0x22, 0x33, 0x44})`, đọc `getInt()` sau khi đặt từng byte order.

**Bài 3 — chọn hợp đồng.** Một file cần chứa `tag`, `value`, `code` để Java và C cùng đọc trên nhiều hệ điều hành. Chọn định dạng 7 byte có endian cố định và mô tả byte offset. Nếu yêu cầu thay thành chia sẻ native `struct Record[]`, hãy bổ sung thông số ABI, layout 12 byte giả định, stride 12, alignment, lifetime và bộ test xác minh tương thích.

## Ghi nhớ

- **Endianness** trả lời “trong một số nhiều byte, byte nào đứng trước?”; **alignment** trả lời “field/object bắt đầu ở địa chỉ nào?”; **padding** là phần trống được thêm để thỏa layout.
- `sizeof(struct)` có thể lớn hơn tổng `sizeof` các field; `offsetof` và `_Alignof` là công cụ xác minh trên target, không phải cớ để dự đoán layout mọi ABI.
- Java `ByteBuffer` không mô hình hóa C `struct` tự động. Offset, byte order, độ rộng field và padding phải được thỏa thuận/kiểm chứng.
- Dữ liệu cần bền vững qua file/network nên có **wire format độc lập ABI**. Chia sẻ object native trong bộ nhớ đòi hỏi hợp đồng ABI chặt chẽ và kiểm tra thực tế.
