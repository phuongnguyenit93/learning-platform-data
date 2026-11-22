# Kiến thức C, con trỏ và quản lý tài nguyên trước khi thực hành Java–native

Khi Java gọi mã native qua JNI hoặc Foreign Function & Memory (FFM) API, một phần công việc chạy ngoài các bảo đảm thông thường của JVM. Java quản lý đối tượng bằng garbage collector (GC), kiểm tra biên mảng và ném exception; C thao tác trực tiếp với địa chỉ, độ dài buffer, kiểu dữ liệu theo ABI và vòng đời tài nguyên. Một lỗi C như truy cập vùng nhớ đã giải phóng có thể làm hỏng dữ liệu hoặc khiến cả tiến trình JVM dừng.

**Mục tiêu sau bài này:** đọc và viết được những đoạn C nhỏ; hiểu `&`, `*`, mảng, con trỏ và vùng nhớ; xác định ai sở hữu một tài nguyên, khi nào phải giải phóng; nhận ra rủi ro về độ dài, chuỗi, alignment và ABI; biết cách áp dụng các quy tắc ấy vào JNI/FFM trước khi viết binding thực tế.

## 1. Bản đồ tư duy khi vượt ranh giới Java/C

| Khía cạnh | Java thông thường | C/native |
| --- | --- | --- |
| Đối tượng và vòng đời | GC quản lý vùng nhớ đối tượng còn reachable | Vùng cấp phát động cần quy ước sở hữu và giải phóng; nhiều tài nguyên không phải bộ nhớ cũng phải đóng |
| Mảng | `array.length`, kiểm tra chỉ số | Con trỏ thường không mang độ dài; lập trình viên phải truyền `length` và kiểm tra biên |
| Tham chiếu | Reference do JVM quản lý | Pointer là giá trị biểu diễn vị trí/địa chỉ theo nền tảng, có thể null, treo hoặc mất hiệu lực |
| Chuỗi | `String` là chuỗi bất biến, dựa trên Unicode | `char *` thường trỏ đến dãy byte kết thúc bằng `'\0'`; encoding phải được quy định |
| Kiểu và layout | `int` luôn 32 bit, `long` luôn 64 bit | Kích thước `int`, `long`, pointer và cách bố trí `struct` phụ thuộc nền tảng/ABI |
| Lỗi | Exception, phần lớn lỗi truy cập được JVM kiểm soát | Mã lỗi, `NULL`, `errno` khi API có quy định; truy cập sai bộ nhớ có thể gây undefined behavior |

**Quy tắc trung tâm:** với mỗi dữ liệu đi qua ranh giới, phải biết **kiểu và layout**, **địa chỉ/độ dài hợp lệ**, **quyền sở hữu**, **thời hạn sử dụng**, **cách xử lý lỗi** và **bên chịu trách nhiệm cleanup**. Đừng suy luận một pointer có an toàn chỉ vì Java giữ reference đến đối tượng liên quan.

## 2. Nền tảng C tối thiểu cần đọc được

### 2.1. Cấu trúc chương trình, kiểu và biểu thức

Một tệp C thường gồm directive `#include`, khai báo kiểu/hàm, định nghĩa hàm và lệnh. Ví dụ:

~~~c
#include <stdint.h>
#include <stddef.h>

int64_t add_values(const int32_t *values, size_t count) {
    int64_t total = 0;
    for (size_t i = 0; i < count; ++i) {
        total += values[i];
    }
    return total;
}
~~~

Hàm nhận địa chỉ phần tử đầu và số phần tử, rồi trả tổng. Đây là **mảnh minh họa**, không phải chương trình chạy độc lập; caller phải cung cấp `values` trỏ đến ít nhất `count` phần tử `int32_t` hợp lệ. Với một mảng hợp lệ có tối đa `INT32_MAX` phần tử `int32_t`, tổng vẫn nằm trong `int64_t`; nhưng một API tổng quát vẫn nên công bố rõ miền dữ liệu và kiểm tra lỗi cần thiết. Ví dụ chạy độc lập ở mục 8 còn kiểm tra pointer và overflow khi cộng.

Những cấu trúc quan trọng:

- `if/else`, `for`, `while`, `return` và block `{ ... }` điều khiển luồng; biến cục bộ thường có thời hạn sống tới khi block kết thúc.
- `T x` khai báo một giá trị kiểu `T`; `T *p` khai báo một pointer tới `T`; `T a[n]` khai báo một mảng có `n` phần tử.
- `struct` gom các field, `enum` biểu diễn hằng số nguyên có tên; `typedef` tạo tên kiểu.
- `const` cấm sửa **thông qua lối truy cập đó**; nó không tự cấp phát, giữ sống hay giải phóng bộ nhớ.
- `sizeof x` cho kích thước theo **C byte**; dùng `sizeof *p` khi cấp phát vùng chứa kiểu mà `p` trỏ đến.
- `size_t` dùng cho kích thước/số phần tử (`sizeof` trả về `size_t`), in bằng `%zu`; `ptrdiff_t` dùng cho hiệu con trỏ hợp lệ.
- `int32_t`, `uint8_t`, `int64_t` từ `<stdint.h>` diễn đạt đúng số bit khi nền tảng có kiểu tương ứng. `<inttypes.h>` cung cấp macro in như `PRId64`.

Trong Java, `int` và `long` có kích thước cố định. Trong C, đừng mặc định `sizeof(int) == 4`, `sizeof(long) == 8` hay `sizeof(void *) == 8`. Ngay cả trên máy 64 bit, `long` thường 32 bit ở Windows (LLP64) nhưng 64 bit ở nhiều hệ Unix (LP64). Cũng phải phân biệt signed/unsigned: số âm chuyển sang số không dấu và phép tính kích thước có thể tạo giá trị rất lớn; signed integer overflow trong C là undefined behavior. Khi nhân `count * sizeof(T)`, kiểm tra overflow **trước** khi nhân.

### 2.2. Giá trị, địa chỉ, con trỏ và giải tham chiếu

~~~c
int score = 10;
int *ptr = &score;   // & lấy địa chỉ của score
*ptr = 15;           // * giải tham chiếu và gán qua pointer
int copy = *ptr;     // copy == 15; score == 15
~~~

`ptr` chứa một vị trí có thể truy cập `int`. `*ptr` đọc/ghi đối tượng ở vị trí đó, với điều kiện địa chỉ hợp lệ, còn sống, đúng kiểu và alignment. Cú pháp giống nhau nhưng hai dấu `*` có vai trò khác nhau: trong khai báo là “pointer đến”; trong biểu thức là “đọc/ghi đối tượng được trỏ đến”.

~~~c
int values[3] = {4, 5, 6};
int *begin = values;       // values thường chuyển thành &values[0]
int second = *(begin + 1); // tương đương values[1], bằng 5
~~~

Pointer arithmetic bước theo **đơn vị phần tử**, không phải số byte: `begin + 1` tiến `sizeof(int)` byte trong ví dụ. Chỉ tính toán con trỏ trong cùng đối tượng mảng (hoặc đúng một vị trí sau phần tử cuối); không dereference pointer “one past end”. `values[3]` và `*(begin + 3)` đều vượt phạm vi đọc. Một địa chỉ không phải “hợp lệ” chỉ vì nó khác `NULL`.

Ba dạng `const` dễ nhầm:

~~~c
const int *read_only_value = &score; // không sửa score qua pointer này
int *const fixed_pointer = &score;   // không đổi đích của pointer này
const int *const both = &score;       // cả hai hạn chế trên
~~~

`void *` là pointer dữ liệu không gắn kiểu phần tử; không được dereference trực tiếp hay tự làm pointer arithmetic theo C chuẩn. `T **` là pointer tới pointer, thường dùng khi một hàm cần thay đổi pointer của caller. `NULL` biểu thị null pointer; kiểm tra null trước khi dereference, nhưng kiểm tra null **không** xác nhận length, quyền sở hữu hay lifetime.

### 2.3. Mảng không tự mang kích thước khi truyền vào hàm

Khai báo tham số `int x[]` trong hàm tương đương một tham số pointer `int *x`, không kèm `length`. `sizeof(x)` bên trong hàm trả kích thước pointer, **không** trả kích thước mảng bên gọi. Vì vậy:

~~~c
void process(const int *data, size_t length);
~~~

Caller phải bảo đảm `data` có ít nhất `length` phần tử có thể đọc (hoặc hai bên quy ước `data == NULL` hợp lệ khi `length == 0`). Trong native code, nên truyền pointer **cùng độ dài** như một cặp không thể tách; dùng `size_t` cho số phần tử C, kiểm tra kiểu khi chuyển từ `jsize`, `jlong` hay độ dài Java.

## 3. Vòng đời bộ nhớ: còn sống quan trọng hơn có địa chỉ

| Loại bộ nhớ/tài nguyên | Ví dụ | Thời hạn và cleanup |
| --- | --- | --- |
| Automatic storage | `int local;`, `int a[4];` trong block | Thông thường hết lifetime khi rời block/call; không được `free(&local)` |
| Static storage | `static int cache;`, biến global | Tồn tại suốt thời gian chạy chương trình; cần đồng bộ khi truy cập chung |
| Dynamic allocation | `malloc`, `calloc`, `realloc` | Tồn tại cho đến khi `free` theo hợp đồng; không do Java GC tự giải phóng |
| Handle hệ điều hành/thư viện | `FILE *`, socket, file descriptor, native library handle | Có quy tắc `fclose`, `close` hoặc hàm giải phóng chuyên biệt |
| Dữ liệu mượn từ JVM | `GetIntArrayElements`, `GetStringUTFChars` | Chỉ hợp lệ theo hợp đồng JNI cho đến `Release...` tương ứng |
| Foreign memory theo FFM | `MemorySegment` với phạm vi do `Arena` quản lý | Quyền truy cập và lifetime gắn với scope/arena; sau khi đóng scope không được dùng tiếp |

“Stack” và “heap” là cách nói thông dụng để hình dung, nhưng tiêu chuẩn C mô tả **storage duration**, không bắt buộc mọi biến automatic nằm trên vùng stack vật lý. Điểm cần giữ là thời hạn sử dụng và ai có quyền kết thúc nó.

### 3.1. Cấp phát và giải phóng động

~~~c
size_t count = 100;
int32_t *buffer = NULL;

if (count > SIZE_MAX / sizeof *buffer) {
    /* count * sizeof *buffer sẽ overflow: báo lỗi */
} else {
    buffer = malloc(count * sizeof *buffer);
    if (buffer == NULL) {
        /* xử lý thiếu bộ nhớ */
    } else {
        /* buffer[0] ... buffer[count - 1] hợp lệ */
        free(buffer);
        buffer = NULL; // tránh vô tình tái sử dụng chính biến pointer này
    }
}
~~~

Đây là mảnh minh họa, cần `#include <stdint.h>` và `#include <stdlib.h>` trong chương trình thực tế. `malloc` cấp phát các byte **chưa được khởi tạo**; chỉ đọc sau khi đã ghi giá trị hợp lệ. `calloc(n, size)` khởi tạo các byte về 0 (vẫn cần kiểm tra kết quả/overflow theo API), nhưng 0 byte không tự động phù hợp cho mọi layout dữ liệu. Với số phần tử bằng 0, nên xử lý riêng vì `malloc(0)` có hành vi kết quả phụ thuộc triển khai.

Không bao giờ gọi `free` cho địa chỉ biến cục bộ, phần tử giữa một allocation, vùng nhớ do Java giữ, hoặc pointer do API khác sở hữu. `free(NULL)` hợp lệ. `free` hai lần cùng allocation, dereference sau `free`, dùng lại pointer alias sau khi giải phóng, hoặc quên `free` gây lỗi nghiêm trọng. Đặt một biến pointer thành `NULL` **không vô hiệu hóa các alias** đang trỏ đến vùng đã giải phóng.

**Đổi kích thước an toàn với `realloc`:**

~~~c
void *tmp = realloc(buffer, new_byte_count);
if (tmp == NULL) {
    /* Khi new_byte_count > 0, allocation cũ vẫn còn và phải free sau */
} else {
    buffer = tmp; // allocation có thể đã chuyển địa chỉ
}
~~~

Đừng gán trực tiếp `buffer = realloc(buffer, ...)`: nếu thất bại, bạn làm mất địa chỉ cần giải phóng. Đoạn này giả định `buffer` là allocation còn sống do allocator tương thích tạo ra, `new_byte_count > 0` và đã kiểm tra phép tính kích thước; tránh dùng `realloc(ptr, 0)` vì ngữ nghĩa không phải nền tảng tốt cho code portable. Sau một `realloc` thành công, các pointer alias cũ không được dùng tiếp.

### 3.2. Ownership và borrowed pointer

Mỗi API native nên trả lời rõ bốn câu: **ai tạo? ai sở hữu? ai được mượn? ai giải phóng bằng hàm nào?**

- **Owned:** caller nhận ownership và phải gọi đúng hàm hủy (`free`, `destroy_handle`, `CloseHandle` tùy API) trên tất cả đường kết thúc.
- **Borrowed:** caller chỉ đọc/ghi theo quyền được cấp; không tự giải phóng. Tài nguyên phải còn sống trong toàn bộ lúc mượn.
- **Transferred:** ownership chuyển từ A sang B; A phải ngừng sử dụng hoặc giải phóng theo hợp đồng chuyển giao.
- **Shared:** nhiều bên có thể truy cập; phải có quy tắc reference count, khóa hoặc cơ chế lifetime/đồng bộ khác. Nhiều pointer cùng địa chỉ **không tự tạo shared ownership**.

Ví dụ: hàm C trả về `char *` có thể trả một buffer caller phải `free`, một buffer nội bộ mà caller không được `free`, hoặc một pointer chỉ hợp lệ đến lần gọi tiếp theo. Chữ ký `char *` **không mô tả được** quyền sở hữu; bắt buộc đọc và ghi hợp đồng API.

### 3.3. Cleanup trên mọi nhánh lỗi

C không có `try/finally` hay destructor tự động như một số ngôn ngữ khác. Với nhiều tài nguyên, quy ước `goto cleanup` giúp không bỏ sót bước giải phóng:

~~~c
int run_task(void) {
    int status = -1;
    FILE *file = fopen("input.bin", "rb");
    if (file == NULL) return -1;

    unsigned char *buffer = malloc(1024);
    if (buffer == NULL) goto cleanup;

    /* đọc/xử lý; nếu thất bại có thể goto cleanup */
    status = 0;

    free(buffer);
cleanup:
    fclose(file);
    return status;
}
~~~

Đây là mảnh minh họa pattern cleanup, cần `#include <stdio.h>` và `#include <stdlib.h>`; chưa thực hiện I/O thực tế. Trong code nhiều đường thoát, bố trí nhãn cleanup tương ứng sao cho mọi tài nguyên đã khởi tạo được giải phóng đúng một lần, theo thứ tự ngược lúc lấy tài nguyên khi có dependency. Một cách khác là tách các hàm nhỏ và trả về rõ ràng; mục tiêu là kiểm tra được tất cả đường lỗi.

## 4. Con trỏ treo, overflow và undefined behavior

Các loại lỗi phải nhận diện trước khi gọi native:

1. **Null pointer dereference:** `p == NULL` nhưng vẫn đọc `*p`.
2. **Uninitialized/wild pointer:** chưa gán một địa chỉ hợp lệ mà đã dereference; hoặc dùng byte `malloc` chưa khởi tạo.
3. **Dangling pointer / use-after-free:** vùng nhớ hết lifetime; còn giữ địa chỉ cũng vô ích.
4. **Out-of-bounds:** đọc/ghi ngoài mảng, nhầm số phần tử với số byte, dùng `strlen` trên buffer thiếu terminator.
5. **Double-free / invalid-free / memory leak:** giải phóng sai nguồn hoặc quên giải phóng.
6. **Signed overflow, size overflow, truncation:** đổi `jlong` sang `int`, nhân `count * size` hoặc cộng offset không kiểm tra.
7. **Misalignment / type punning sai:** ép `char *` thành `int64_t *` rồi dereference địa chỉ không đủ alignment; vi phạm effective type/strict aliasing.

**Undefined behavior (UB)** nghĩa là C không đảm bảo kết quả nào; chương trình có thể chạy có vẻ đúng, crash hoặc bị compiler tối ưu theo giả định không có UB. `try/catch` ở Java không sửa được việc native code đã ghi sai bộ nhớ. Với dữ liệu không tin cậy, cần kiểm tra pointer/null, độ dài, capacity, phép nhân/cộng và giá trị trả về **trước** mỗi thao tác.

`memcpy(dst, src, n)` sao chép **n byte**, chỉ an toàn khi cả hai vùng chứa ít nhất `n` byte hợp lệ và không chồng lấp; với vùng có thể overlap dùng `memmove`. Không suy ra capacity từ pointer. Khi API nhận `void *buffer, size_t bytes`, đơn vị được tính theo byte; khi nhận `int32_t *buffer, size_t elements`, đơn vị theo phần tử.

## 5. Chuỗi, byte buffer và Unicode tại biên Java/native

C string thông thường là dãy `char` kết thúc bằng byte NUL `'\0'`. Ví dụ `char name[] = "Java";` chiếm ít nhất 5 C byte gồm 4 ký tự ASCII và NUL. `strlen(name)` trả số byte trước NUL đầu tiên; nó không biết capacity và sẽ đọc vượt biên nếu thiếu terminator. Một blob nhị phân có thể chứa NUL ở giữa, nên **không** dùng `strlen` để tính độ dài blob. Với dữ liệu nhị phân, truyền cặp (`pointer`, `byte_length`).

Java `String` dựa trên Unicode; `char` Java là một UTF-16 code unit. Trong C, `char` là một C byte, không tương đương một ký tự Unicode. UTF-8 có độ dài byte thay đổi; số code point, số `char` Java và số byte UTF-8 thường khác nhau. Cần quy định encoding khi chuyển đổi và xử lý NUL trong dữ liệu.

**JNI có hai đường chuỗi phổ biến:**

- `GetStringChars` trả các `jchar` (UTF-16 code unit) và đi với `ReleaseStringChars`.
- `GetStringUTFChars` trả chuỗi theo **Modified UTF-8 (MUTF-8)** của JNI, phải dùng `ReleaseStringUTFChars`; MUTF-8 không hoàn toàn là UTF-8 thông thường (ví dụ biểu diễn U+0000 và supplementary characters). Không tự động chuyển kết quả ấy thành một giao thức đòi chuẩn UTF-8.

`const char *` không có nghĩa pointer luôn trỏ đến string hợp lệ hoặc tồn tại mãi. Một native API muốn trả UTF-8 cần chỉ rõ ai tạo/giải phóng buffer, độ dài byte, có NUL terminator hay không và cách báo lỗi mã hóa. Khi nhận buffer từ Java, tránh giữ pointer đó qua thời hạn mượn.

## 6. Layout, alignment, endian và ABI

ABI (Application Binary Interface) quy định cách gọi hàm và biểu diễn dữ liệu ở mức machine: kích thước/align kiểu, cách truyền/trả tham số, layout cấu trúc, tên symbol và calling convention. Cùng source code có thể có layout khác trên hai hệ điều hành hoặc kiến trúc.

~~~c
#include <stddef.h>
#include <stdint.h>

struct Packet {
    uint8_t tag;
    uint32_t length;
};

size_t bytes = sizeof(struct Packet);
size_t length_offset = offsetof(struct Packet, length);
~~~

Không giả định `bytes == 5` hoặc `length_offset == 1`; compiler thường thêm **padding** để bảo đảm alignment. Đừng ghi trực tiếp `struct` bằng `fwrite` rồi coi byte của nó là định dạng truyền mạng ổn định: padding, endian và ABI có thể khác nhau. Hãy định nghĩa layout trao đổi theo từng byte/field, dùng kích thước cố định, và quy định byte order (network byte order thường big-endian).

Ví dụ số 32 bit `0x01020304` có thứ tự byte `01 02 03 04` trên big-endian và `04 03 02 01` trên little-endian. Khi đọc native memory bằng Java FFM hoặc `ByteBuffer`, phải chọn đúng `ByteOrder`; khi định nghĩa `MemoryLayout` cần xét alignment/padding rõ ràng. Ép pointer qua kiểu khác tùy tiện không giải quyết vấn đề ABI và có thể tạo UB; để đọc biểu diễn byte, dùng `unsigned char *` hoặc `memcpy` với điều kiện vùng nhớ hợp lệ.

**Các ánh xạ cần nhớ khi làm JNI:**

| Java / JNI | Ý nghĩa | Điều tránh |
| --- | --- | --- |
| Java `int` / JNI `jint` | Giá trị số nguyên 32 bit | Giả định mọi C `int` ở mọi ABI có cùng layout |
| Java `long` / JNI `jlong` | Giá trị số nguyên 64 bit | Dùng C `long` làm kiểu thay thế trên mọi hệ |
| Java `char` / JNI `jchar` | UTF-16 code unit 16 bit, unsigned | Ép thành C `char` và coi là một byte ký tự |
| Java `boolean` / JNI `jboolean` | Boolean JNI | Tự suy ra kích thước/layout từ `bool` C |
| `jobject`, `jarray`, `jstring` | JNI reference/handle do JVM quản lý | Ép thành `T *` rồi truy cập như pointer C |
| `jint *` sau `GetIntArrayElements` | Con trỏ mượn dữ liệu JNI trong thời hạn được phép | Giữ pointer sau `ReleaseIntArrayElements` |

Không truyền `struct` “by value” qua FFI nếu chưa xác nhận convention/layout của đúng target ABI. Với union/bitfield/compiler packing, rủi ro sai khác còn lớn hơn. Kiểu native dùng làm handle nên được biểu diễn bằng opaque handle có API tạo/hủy, không bắt Java tự đoán layout nội bộ.

## 7. Ranh giới tài nguyên trong JNI và FFM

### 7.1. JNI: mượn dữ liệu phải trả bằng cặp Release

Trong JNI, các hàm `Get<Type>ArrayElements` và `GetString...Chars` có thể trả pointer đến bản copy hoặc vùng được pin; caller **không được giả định** lựa chọn nào. Khi thành công, phải gọi hàm `Release...` tương ứng, kể cả khi chỉ đọc. `JNI_ABORT` ở `ReleaseIntArrayElements` yêu cầu bỏ copy-back khi chỉ đọc; nó không có nghĩa bỏ việc release.

`GetPrimitiveArrayCritical`/`ReleasePrimitiveArrayCritical` có ràng buộc nghiêm ngặt hơn vì có thể ảnh hưởng GC: giữ critical section ngắn, tránh I/O blocking và các JNI call không được phép trong đoạn critical. Đọc đúng tài liệu API trước khi dùng; không thay mọi `GetArrayElements` bằng Critical để “tối ưu”.

JNI local reference thường chỉ hợp lệ trong native call/frame hiện tại. Nếu cần giữ đối tượng Java sau khi hàm native trả về, dùng `NewGlobalRef` hoặc cơ chế reference tương ứng, rồi `DeleteGlobalRef` khi hết cần; đồng thời giải quyết lifetime/thread-safety. `JNIEnv *` gắn với thread, **không** cache để dùng ở thread khác. Native thread tự tạo muốn gọi JVM phải attach theo JNI Invocation API, rồi detach theo đúng hợp đồng.

Lúc JNI API báo lỗi bằng `NULL` hoặc để pending Java exception, thực hiện cleanup các tài nguyên đã mượn trước khi trả về; đừng tiếp tục gọi JNI API tùy tiện khi exception đang pending. Khi cần ném lỗi chủ động, dùng `ThrowNew` với lớp exception phù hợp và trả về ngay sau khi dọn tài nguyên.

### 7.2. FFM: địa chỉ vẫn cần scope và layout hợp lệ

FFM sử dụng các khái niệm như `MemorySegment` (vùng bộ nhớ), `Arena` (quản lý lifetime), `MemoryLayout` (cách diễn giải dữ liệu) và `Linker` (liên kết native function), tùy phiên bản JDK có hỗ trợ API. Các abstraction này giúp ràng buộc truy cập theo scope và layout; chúng **không tự bảo đảm** native library tôn trọng buffer length, ownership, calling convention hoặc thread safety. Nếu C giữ địa chỉ sau khi arena đã đóng, native code có thể dereference vùng không còn hợp lệ.

Đừng trộn allocator/deallocator: vùng do `malloc` cấp phát phải dùng cơ chế giải phóng tương thích; vùng do thư viện cấp cần đúng hàm `library_free` của thư viện; vùng do arena quản lý được kết thúc theo cơ chế arena. Java GC không thay thế việc close handle/socket/native allocation. Nếu native code lưu callback pointer hoặc user-data pointer, phải giữ callback/segment và dữ liệu nền còn sống **cho tới khi native xác nhận ngừng dùng**.

### 7.3. Bảng hợp đồng trước khi gọi hàm

| Câu hỏi | Ví dụ câu trả lời cần có |
| --- | --- |
| Pointer và kích thước được tính theo gì? | `const uint8_t *bytes` + `size_t byte_count`, hoặc `int32_t *items` + `size_t element_count` |
| Ai sở hữu buffer? | “caller cấp, callee chỉ mượn trong lời gọi” / “callee cấp, caller gọi `library_free`” |
| Có được giữ pointer sau khi return không? | “không” / “có, đến khi `release_callback` trả về và thread dừng” |
| Native có sửa dữ liệu không? | “read-only”; `const` ở C nói lên intent nhưng không thay validation của JNI/FFM |
| Sai input hoặc thiếu bộ nhớ thì sao? | giá trị trả về, exception, error code, `errno` nếu API quy định |
| Có thread/callback nào dùng chung không? | thread nào được gọi, synchronization, JNI attach/detach, scope có hỗ trợ truy cập đa luồng không |

## 8. Ví dụ C độc lập: dùng pointer và sở hữu buffer có kiểm soát

Lưu mã sau thành `native_basics.c`. Ví dụ tự chạy, không cần JNI; nó thể hiện kiểm tra kích thước, cấp phát, mượn pointer `const`, tính tổng, và cleanup duy nhất.

~~~c
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static bool sum_i32(const int32_t *data, size_t count, int64_t *result) {
    if (result == NULL || (count != 0 && data == NULL)) {
        return false;
    }

    int64_t total = 0;
    for (size_t i = 0; i < count; ++i) {
        int64_t value = data[i];
        if ((value > 0 && total > INT64_MAX - value) ||
            (value < 0 && total < INT64_MIN - value)) {
            return false;
        }
        total += value;
    }
    *result = total;
    return true;
}

int main(void) {
    const size_t count = 4;
    int32_t *items = NULL;
    int64_t total = 0;
    int status = EXIT_FAILURE;

    if (count > SIZE_MAX / sizeof *items) {
        fputs("size overflow\n", stderr);
        return EXIT_FAILURE;
    }

    items = malloc(count * sizeof *items);
    if (items == NULL) {
        fputs("allocation failed\n", stderr);
        return EXIT_FAILURE;
    }

    for (size_t i = 0; i < count; ++i) {
        items[i] = (int32_t)((i + 1) * 10);
    }

    const int32_t *borrowed_view = items;
    if (!sum_i32(borrowed_view, count, &total)) {
        fputs("invalid data or sum overflow\n", stderr);
        goto cleanup;
    }

    printf("count=%zu\n", count);
    printf("sum=%" PRId64 "\n", total);
    printf("second=%" PRId32 "\n", borrowed_view[1]);
    status = EXIT_SUCCESS;

cleanup:
    free(items);
    items = NULL;
    return status;
}
~~~

Biên dịch bằng GCC/Clang hỗ trợ C11:

~~~sh
cc -std=c11 -Wall -Wextra -Wpedantic -O0 -g native_basics.c -o native_basics
./native_basics
~~~

Trên Windows dùng môi trường có GCC/Clang và chạy executable tương ứng (ví dụ `.\native_basics.exe`). Trên đường chạy thành công, stdout chính xác:

~~~text
count=4
sum=100
second=20
~~~

`items` là **owned pointer**; `borrowed_view` là alias chỉ đọc, không được `free` riêng và mất hiệu lực sau `free(items)`. `&total` là địa chỉ out-parameter, còn `result` trong `sum_i32` chỉ được dùng trong lúc hàm chạy. Guard `count > SIZE_MAX / sizeof *items` bảo vệ phép nhân size; guard trong vòng lặp bảo vệ phép cộng `int64_t`. Kiểu in sử dụng `PRId64`/`PRId32` thay vì đoán format specifier theo ABI.

Nếu có AddressSanitizer/UndefinedBehaviorSanitizer với compiler hỗ trợ, có thể biên dịch bài tập này thêm `-fsanitize=address,undefined -fno-omit-frame-pointer` rồi cố tình kiểm thử các lỗi trong một sandbox riêng. Sanitizer giúp tìm lỗi nhưng không biến native code thành memory-safe; chế độ/hỗ trợ trên Windows và từng compiler khác nhau.

## 9. Ví dụ Java 17 + JNI nhỏ: mượn mảng Java đúng cách

Ví dụ này nối trực tiếp quy tắc ở trên với JNI, dùng **một** phương thức native tính tổng mảng `int[]`. Tạo tệp `NativeSum.java`:

~~~java
package demo;

public final class NativeSum {
    static {
        System.loadLibrary("nativesum");
    }

    public static native long sum(int[] values);

    public static void main(String[] args) {
        System.out.println(sum(new int[] {10, 20, 30, 40}));
    }
}
~~~

Chạy `javac -h .` sẽ sinh header `demo_NativeSum.h` với đúng chữ ký JNI. Tạo tệp `nativesum.c` cùng thư mục:

~~~c
#include "demo_NativeSum.h"

JNIEXPORT jlong JNICALL
Java_demo_NativeSum_sum(JNIEnv *env, jclass ignored, jintArray values) {
    (void)ignored;

    if (values == NULL) {
        jclass exception_class =
            (*env)->FindClass(env, "java/lang/NullPointerException");
        if (exception_class != NULL) {
            (*env)->ThrowNew(env, exception_class,
                             "values must not be null");
            (*env)->DeleteLocalRef(env, exception_class);
        }
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, values);
    jint *elements = (*env)->GetIntArrayElements(env, values, NULL);
    if (elements == NULL) {
        return 0; // thất bại; kiểm tra pending exception của JNI
    }

    jlong total = 0;
    for (jsize i = 0; i < length; ++i) {
        total += (jlong)elements[i];
    }

    (*env)->ReleaseIntArrayElements(env, values, elements, JNI_ABORT);
    return total;
}
~~~

Trên **Linux** với JDK 17+ và C compiler (thiết lập `JAVA_HOME` trỏ đến cùng JDK đang dùng), chạy trong thư mục chứa hai tệp:

~~~sh
javac -h . -d . NativeSum.java
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  nativesum.c -o libnativesum.so
java -Djava.library.path=. demo.NativeSum
~~~

Stdout của ví dụ:

~~~text
100
~~~

Trên macOS dùng include `darwin` và tạo `libnativesum.dylib` với cờ chia sẻ thư viện thích hợp; trên Windows dùng include `win32`, tạo `nativesum.dll` bằng toolchain phù hợp. Tên thư viện phải theo quy ước của `System.loadLibrary("nativesum")`. Build nhiều nền tảng cần cấu hình toolchain/JDK headers tương ứng, không dùng nguyên dòng Linux cho mọi OS.

Giải thích ownership trong lời gọi JNI:

1. `values` là **JNI handle**, không phải `jint *`. JVM vẫn kiểm soát mảng và representation của nó.
2. `GetArrayLength` lấy số **phần tử**; `GetIntArrayElements` cho pointer tạm có thể là copy hoặc pinned storage.
3. Trong lúc borrow còn hiệu lực, vòng lặp chỉ đọc `elements[i]` với `0 <= i < length`. Tổng an toàn trong `jlong` vì `length` là `jsize` và mỗi phần tử là `jint` 32 bit; ngay cả giới hạn dương lớn nhất cũng không vượt miền `jlong`.
4. `ReleaseIntArrayElements(..., JNI_ABORT)` giải phóng borrow mà không copy dữ liệu ngược về Java, hợp lý vì không có sửa phần tử. Nếu sửa dữ liệu và cần trả về Java, phải chọn mode release phù hợp.
5. Khi `GetIntArrayElements` thất bại, không dereference `NULL`; API có thể đã để pending exception (ví dụ thiếu bộ nhớ). Khi `values == NULL`, mã chủ động báo `NullPointerException`.

Ví dụ dùng cách truy cập đơn giản để minh họa ownership; với mảng rất lớn, đo lường chi phí pin/copy và cân nhắc `GetIntArrayRegion`, direct buffer hoặc FFM cho bài toán cụ thể. Không cache `elements` qua nhiều lần gọi Java. Không `free(elements)`, vì đây không phải allocation do `malloc` của bạn tạo.

## 10. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `malloc(count * sizeof(T))` không kiểm tra | Phép nhân `size_t` có thể wrap thành allocation nhỏ | Kiểm tra `count <= SIZE_MAX / sizeof(T)` trước khi nhân |
| `return pointer_to_local;` | Biến automatic hết lifetime khi hàm trả về | Caller cấp buffer, hoặc trả allocation owned có hàm free rõ ràng |
| `free(pointer_from_GetStringUTFChars)` | Pointer do JNI cho mượn, không thuộc C allocator của caller | Gọi `ReleaseStringUTFChars` đúng cặp |
| `(int *)jintArray_handle` | JNI reference không phải pointer vào phần tử | Dùng JNI array access API, `Release...` và length |
| `strlen(bytes)` với buffer nhị phân | NUL giữa payload làm ngắn sai; thiếu NUL có thể đọc quá biên | Truyền length tường minh |
| Gọi `free` rồi tiếp tục dùng alias | Pointer khác vẫn trỏ tới allocation đã chết | Thống nhất ownership/lifetime; ngừng mọi borrow trước free |
| Giả định `sizeof(struct)` đúng bằng tổng field | Padding/alignment có thể thêm byte | Xác nhận `sizeof`, `offsetof`, ABI và serialize theo format xác định |
| Dùng `JNIEnv *` ở thread khác | Pointer môi trường JNI theo thread | Thread tương ứng attach và lấy env của chính nó |
| Native giữ pointer sau khi arena đóng | Memory segment hết lifetime | Thiết kế scope/ownership bao trùm mọi tác vụ native |
| Thiếu cleanup khi lỗi nửa chừng | Leak hoặc lock/handle không được trả | Ghi một cleanup path, kiểm tra từng nhánh thành công/thất bại |

## 11. Checklist trước khi viết một lời gọi native thật

- **Kiểu và ABI:** mỗi tham số/giá trị trả về là số bit gì? Signed hay unsigned? Pointer hay handle? Calling convention, alignment, endian, layout có được xác nhận?
- **Biên bộ nhớ:** length đo bằng byte hay phần tử? Có checked conversion và checked multiplication chưa? Pointer có thể null không? Buffer có đủ capacity và còn sống không?
- **Ownership:** bên nào tạo, bên nào mượn, bên nào huỷ? Dùng chính xác hàm release/close nào? Có thể native giữ lại pointer hoặc callback sau khi return không?
- **Chuỗi:** UTF-8, UTF-16 hay Modified UTF-8? Có NUL terminator không? Có NUL nhúng không? Length/capacity được truyền riêng chưa?
- **Lỗi:** check mã trả về và pending exception ở đâu? Mọi đường lỗi có dọn hết thứ đã mượn/cấp phát không? Có nguy cơ trả về dữ liệu chưa khởi tạo không?
- **Đa luồng:** tài nguyên có được truy cập đồng thời không? JNI environment thuộc thread nào? Callback và scope tồn tại bao lâu? Có race khi Java và C cùng sửa buffer không?
- **Kiểm thử:** thử input rỗng, null theo hợp đồng, length biên, ký tự Unicode, lỗi cấp phát và thao tác lặp; kiểm thử trên đúng OS/CPU/JDK/ABI mục tiêu, dùng sanitizer hoặc memory checker khi hỗ trợ.

**Tiêu chí sẵn sàng thực hành:** khi nhìn một prototype như `int native_process(const uint8_t *input, size_t input_len, uint8_t **output, size_t *output_len)`, bạn phải hỏi được: buffer nào caller sở hữu, pointer nào chỉ được mượn, ai cấp `*output`, giải phóng bằng hàm nào, các độ dài có đơn vị gì, lỗi được báo ra sao và bao giờ pointer không còn hợp lệ. Nếu tài liệu thư viện chưa trả lời được các câu hỏi này, chưa đủ thông tin để viết binding Java an toàn.