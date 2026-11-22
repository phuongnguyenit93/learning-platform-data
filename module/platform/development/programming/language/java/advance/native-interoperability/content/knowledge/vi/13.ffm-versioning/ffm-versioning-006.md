# Những thông tin về ABI, con trỏ và hợp đồng C mà FFM không tự suy ra

## Mục tiêu

Foreign Function & Memory API (**FFM**) cho phép Java gọi hàm native, thao tác vùng nhớ ngoài Java heap và đưa Java callback cho thư viện C mà không nhất thiết phải viết lớp JNI C trung gian. Nhưng FFM **không phải một bộ suy luận đầy đủ về mã C**: nó chỉ có thể liên kết chính xác khi lập trình viên cung cấp những thông tin mà ABI và chữ ký hàm thực tế yêu cầu.

Sau bài học, bạn sẽ:

1. Phân biệt **những gì native Linker biết về ABI** với **những điều FunctionDescriptor, MemoryLayout và code Java phải mô tả thủ công**.
2. Biết vì sao **C long, size_t, con trỏ, struct, union, padding, alignment, by-value aggregate và variadic arguments** không thể ánh xạ bừa sang kiểu Java.
3. Hiểu giới hạn an toàn của **MemorySegment**, **AddressLayout**, **Arena**, **reinterpret** và callback/upcall: byte bounds trong Java không chứng minh quyền sở hữu hoặc tuổi thọ của pointer C.
4. Đọc hợp đồng **ownership, nullability, buffer length, encoding, deallocator, error reporting, thread-safety và lifetime** trước khi tạo binding.
5. Biên dịch và chạy ví dụ **Java 22+ kết hợp thư viện C11**: native code cung cấp sizeof/alignof/offsetof của struct; Java xác minh trước khi truy cập.
6. Thiết kế checklist và test để phát hiện sai ABI, sai lifetime, lỗi con trỏ và tương thích phiên bản thư viện.

**Ý chính:** FFM có cơ chế an toàn theo **thông tin nó được cung cấp**. Một FunctionDescriptor sai, một MemoryLayout sai hoặc một pointer C bị giải phóng quá sớm vẫn có thể gây hỏng bộ nhớ hoặc làm sập JVM. Không được hiểu “có FFM” là “Java tự phát hiện toàn bộ hợp đồng C”.

## 1. FFM thực sự biết được điều gì?

Ở JDK 22 trở lên, gói API ổn định là **java.lang.foreign**. Các thành phần chính:

| Thành phần | Biết/đảm nhiệm | Không tự biết |
| --- | --- | --- |
| **Linker.nativeLinker()** | ABI của nền tảng hiện tại, quy tắc chuyển đối số và nhận kết quả khi descriptor đúng | Ý nghĩa của hàm C, tham số là input/output/borrowed, hàm có side effect gì |
| **SymbolLookup** | Tra địa chỉ symbol export theo tên trong library được chọn | Prototype C thực của symbol, ABI của một function pointer tùy ý, chữ ký C++ bị name mangling |
| **FunctionDescriptor** | Mô hình layout của tham số/giá trị trả về mà **bạn khai báo** | Không tự mở header C để kiểm chứng số tham số/kiểu/chữ ký |
| **ValueLayout / MemoryLayout** | Độ rộng, alignment, byte order, cấu trúc hoặc dãy theo layout được cung cấp | Không chứng minh layout giống một struct được compiler C thực tế build với flags cụ thể |
| **MemorySegment** | Phạm vi byte được mô hình hóa và kiểm tra scope/khả năng truy cập theo hợp đồng Java | Không bảo đảm một địa chỉ do C đưa sang còn được cấp phát, đủ dài hoặc thuộc đúng allocator |
| **Arena** | Cấp phát và quản vòng đời vùng nhớ do arena sở hữu | Không tự giải phóng pointer mà C malloc/cấp phát riêng nếu không có contract/cleanup đúng |
| **Upcall stub** | Tạo function pointer để C gọi một Java MethodHandle với descriptor đã khai báo | Không tự biết C sẽ giữ callback bao lâu, gọi từ luồng nào hay có được phép giữ pointer sau khi arena đóng không |

Ví dụ sơ lược:

~~~java
Linker linker = Linker.nativeLinker();
MethodHandle handle = linker.downcallHandle(
    symbol,
    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS)
);
~~~

Đây chỉ là **snippet**, giả định symbol đã được tìm và đúng là địa chỉ một hàm C có kiểu trả về tương thích int 32-bit, một tham số pointer. FFM dùng descriptor đó để tạo downcall. Nhưng nếu hàm thực tế nhận **hai tham số** hoặc trả về **struct by value**, FFM không tự truy lại header để phát hiện. Việc gọi handle với descriptor sai là **không an toàn**, có thể có kết quả sai hoặc crash.

### Hình dung ranh giới

~~~text
           C header / tài liệu / ABI
           -------------------------
   C function name, prototype, typedef,
   ownership, buffer length, free function,
   thread safety, error codes, layout
                       |
            BẠN xác nhận + biểu diễn
                       |
        +--------------v--------------+
        | Java FFM binding           |
        | SymbolLookup               |
        | FunctionDescriptor          |
        | MemoryLayout, Arena         |
        +--------------+--------------+
                       |
              Linker + native ABI
                       |
             C binary thực sự đã build
                       |
              KẾT QUẢ / CON TRỎ
                       |
       BẠN tiếp tục kiểm chứng lifetime,
        bounds, null, lỗi, dữ liệu đầu ra
~~~

Không nên nhầm việc linker biết **calling convention của platform** với việc nó biết **hợp đồng semantic của library**.

## 2. Bối cảnh phiên bản: API ổn định từ JDK 22

FFM trải qua giai đoạn incubator/preview trước khi ổn định:

| Nhóm JDK | Trạng thái khái quát | Ý nghĩa khi viết tài liệu và binding |
| --- | --- | --- |
| **JDK 17–18** | Các phiên bản incubator của Foreign Function & Memory API | API/package/cách kích hoạt khác; không thể dùng nguyên xi code JDK 22 |
| **JDK 19–21** | Preview, tiếp tục thay đổi qua các lần JEP | Cần build và tùy chọn preview phù hợp từng phiên bản |
| **JDK 22+** | FFM API được hoàn thiện theo **JEP 454**, trong **java.lang.foreign** | Phù hợp để chọn làm baseline cho code trong bài này |

Bài thực hành phía dưới **yêu cầu JDK 22 hoặc mới hơn**, không tuyên bố chạy trên JDK 17. Một số kiến thức về ABI/ownership áp dụng cho mọi phiên bản, nhưng **tên API và chi tiết ngôn ngữ** phải đối chiếu với JDK đích.

Lời gọi native và một số hoạt động FFM được đánh dấu **restricted**. Khi ứng dụng chạy trên classpath, ví dụ có thể dùng:

~~~bash
java --enable-native-access=ALL-UNNAMED AbiContractDemo
~~~

Trong ứng dụng modularized, nên cấp quyền cho **module cụ thể** thay vì mở cho toàn bộ unnamed modules. Từ JDK 24, chính sách **--illegal-native-access** có các chế độ như **warn/deny**; cài đặt mặc định có thể thay đổi ở các bản JDK sau. Đừng coi một lệnh Java khởi chạy thành công trên JDK này là bằng chứng nó sẽ chạy không cần quyền trên JDK khác.

**Không liên hệ sai phạm vi:** Việc “FFM ổn định từ JDK 22” không có nghĩa C ABI, thư viện native hoặc mọi quy tắc ownership đã trở nên bất biến xuyên các hệ điều hành. API Java có thể ổn định trong khi binary C vẫn phụ thuộc compiler/OS/CPU/ABI.

## 3. ABI là gì, và Linker không thể suy ra những gì?

**Application Binary Interface (ABI)** là hợp đồng ở mức binary: cách truyền tham số qua register/stack, quy tắc trả giá trị, alignment, layout kiểu dữ liệu, calling convention, biểu diễn struct, tên symbol và các ràng buộc nền tảng.

Ví dụ cùng chạy 64-bit:

| C type/đặc điểm | Linux x86-64 thông dụng (LP64) | Windows x64 thông dụng (LLP64) |
| --- | --- | --- |
| **int** | 32 bit | 32 bit |
| **long** | 64 bit | 32 bit |
| **long long** | 64 bit | 64 bit |
| **void \*** | 64 bit | 64 bit |
| **size_t** | Thường 64 bit | Thường 64 bit |
| Calling convention và trả struct | System V x86-64 ABI | Microsoft x64 ABI |

Các giá trị trên là đặc điểm của **hai môi trường tiêu biểu**, không phải quy tắc cho mọi compiler, mọi CPU hoặc mọi bản build.

### Tại sao Java long không đồng nghĩa C long?

- Java **long** luôn là kiểu signed 64 bit.
- C **long** có độ rộng do data model/ABI quy định, thường 64 bit trên LP64 và 32 bit trên LLP64.
- Java **int** là signed 32 bit; việc C **int** có độ rộng đó phải dựa vào ABI đích hoặc một typedef chuẩn như **int32_t** khi có.
- C **size_t** là integer unsigned phù hợp biểu diễn kích thước của môi trường, không phải một kiểu Java cố định xuyên nền tảng.

Vì vậy **FunctionDescriptor.of(ValueLayout.JAVA_LONG)** cho hàm **long f(void)** có thể đúng ở Linux/x64 nhưng sai ở Windows/x64. Ngược lại, **size_t** trên Windows/x64 có thể vẫn là 64 bit dù C long là 32 bit. Không áp dụng một mapping chung cho tất cả tên C có chữ “long”.

### Dùng canonicalLayouts của native linker

FFM cung cấp:

~~~java
Linker linker = Linker.nativeLinker();

MemoryLayout cLong = linker.canonicalLayouts().get("long");
MemoryLayout cSizeT = linker.canonicalLayouts().get("size_t");
MemoryLayout cPointer = linker.canonicalLayouts().get("void*");
~~~

Đây là **snippet Java 22+**, không phải main() độc lập. **canonicalLayouts()** trả map tên kiểu C cơ bản sang layout của ABI mà native linker hiện tại hỗ trợ. Các tên như **long**, **size_t**, **void\*** được native linker bảo đảm hỗ trợ theo tài liệu JDK 22.

**Giới hạn quan trọng:** canonicalLayouts không tự truy header của một library cụ thể. Nó không biết typedef tùy chỉnh **my_count_t**, một struct do bạn định nghĩa hoặc compiler flags đã dùng khi build thư viện. Nó cũng không biết C header có thay đổi giữa hai phiên bản binary hay không.

Đối với integer unsigned, carrier Java có thể là kiểu signed cùng độ rộng. Ví dụ **uint32_t** thường được biểu diễn bằng **int**/JAVA_INT ở binding. Java phải tự giữ đúng semantics unsigned: so sánh, range check và conversion phù hợp. Với **uint64_t**, một số giá trị hợp lệ vượt **Long.MAX_VALUE**; không coi Java long âm là một giá trị size hợp lệ rồi đưa thẳng sang allocator.

### Các loại ABI khó hơn scalar

Ngoài scalar còn có:

- **struct by value:** hệ ABI có thể truyền/trả một struct nhỏ qua register, memory hoặc cơ chế riêng; descriptor phải có group layout phù hợp, không thay bằng ADDRESS tùy tiện.
- **union:** các thành viên chồng lấn bộ nhớ; người gọi phải biết nhánh đang có hiệu lực và cách diễn giải.
- **bit-field:** thứ tự bit, allocation unit và padding có thể phụ thuộc implementation; không suy ra từ tên trường.
- **packed struct / pragma pack:** giảm alignment hoặc thay padding; layout mặc định Java có thể không khớp.
- **variadic functions:** cần mô hình tham số bổ sung và promotion C đúng, ví dụ các loại nhỏ/float có quy tắc nâng kiểu riêng.
- **calling convention không mặc định** hoặc function pointer từ một library tuân theo ABI đặc thù: native linker mặc định có thể không gọi đúng.
- **long double, complex types hoặc vector types:** không mặc định có layout/calling convention được linker hỗ trợ.

FFM giúp gọi những descriptor mà linker hỗ trợ. Nó **không chứng minh thư viện C thực sự xuất đúng loại hàm** bạn đã mô tả.

## 4. Chữ ký C là một hợp đồng phải kiểm chứng

Giả sử C header khai báo:

~~~c
#include <stddef.h>

size_t library_count(const unsigned char *buffer, size_t n);
~~~

Từ chữ ký này, Java phải biết:

1. **buffer** là một pointer: biểu diễn bằng **ValueLayout.ADDRESS** trong FunctionDescriptor.
2. **n** là **size_t**, nên dùng canonical layout size_t theo native ABI, không hardcode JAVA_INT/JAVA_LONG xuyên nền tảng.
3. Giá trị trả về cũng là **size_t**.
4. **const** biểu đạt C function không được sửa nội dung qua pointer đó theo ràng buộc của API; FFM không tự tạo một “const MemorySegment” bảo vệ dữ liệu.
5. Hàm nhận một buffer **dài n byte**, nhưng signature không nói rõ **n có thể bằng 0 hay không**, **buffer NULL có hợp lệ khi n=0** hay không, hoặc hàm có **giữ pointer sau khi trả về** hay không.
6. Tham số n được đo bằng **byte** trong hợp đồng hàm này, không phải Java characters/UTF-16 code units.

Một mô tả FFM về hình dạng lời gọi có thể là:

~~~java
Linker linker = Linker.nativeLinker();
MemoryLayout sizeT = linker.canonicalLayouts().get("size_t");

FunctionDescriptor countDescriptor =
    FunctionDescriptor.of(
        sizeT,                  // return size_t
        ValueLayout.ADDRESS,    // const unsigned char *
        sizeT                   // size_t n
    );
~~~

Đây là **snippet Java 22+**. Nó cho linker biết layout đối số và kết quả, **chưa tìm symbol**, chưa tạo handle và chưa giải quyết nullability/ownership. Khi gọi handle, carrier Java cho size_t phụ thuộc layout (thường int ở 32-bit, long ở 64-bit). Không thể luôn dùng **invokeExact(ptr, longN)** rồi kỳ vọng linker ép đúng nếu thực tế handle yêu cầu **int**.

### FunctionDescriptor không thể được “xác thực” chỉ bằng symbol

Một symbol native thường chỉ có địa chỉ và tên export. Nó không nhất thiết chứa metadata đầy đủ về:

- Kiểu và số lượng tham số.
- Có phải function variadic hay không.
- Kiểu trả về thực; struct by value hay pointer.
- Phần tử pointer trỏ tới.
- Calling convention do compiler yêu cầu.
- Trạng thái lỗi, side effect hoặc thread safety.

Nếu mô tả **int native_sum(int, int)** nhưng symbol thực tế là **double native_sum(double, double)**, Java vẫn có thể tạo MethodHandle với descriptor sai; chỉ khi gọi mới xảy ra vấn đề. **Không xem việc downcallHandle tạo thành công là bằng chứng chữ ký đúng.**

### C++ name mangling và extern "C"

FFM tra symbol theo **tên export thực sự**. Một hàm C++ có thể bị compiler đổi tên bằng name mangling; string **"calculate"** không nhất thiết là symbol xuất ra.

Để thiết kế bề mặt FFI bền hơn, cân nhắc wrapper C ABI:

~~~cpp
// Snippet trong file C++: giữ ABI ổn định cho caller FFM.
extern "C" int32_t api_calculate(int32_t input) noexcept {
    return input + 1;
}
~~~

Đoạn này còn cần header **<cstdint>** và cơ chế export symbol tùy OS để thành một library hoàn chỉnh. **extern "C"** giúp tránh C++ name mangling và chọn liên kết tên C; nó **không** tự bảo đảm struct layout, exception safety hay version compatibility. Native exceptions của C++ không nên đi xuyên ranh giới FFM; wrapper phải bắt và chuyển thành error result theo hợp đồng API.

## 5. Layout của C struct: byte offset phải khớp compiler

Một trong những sai lầm phổ biến là mô tả struct C bằng cách đặt các Java ValueLayout liên tiếp rồi cho rằng mọi compiler cũng bố trí như vậy.

C header:

~~~c
#include <stdint.h>

typedef struct Record {
    uint8_t  kind;    // 1 byte
    uint32_t count;   // 4 byte trên platform hỗ trợ uint32_t
} Record;
~~~

Trên ABI thông dụng có alignment 4 byte cho uint32_t, compiler thường bố trí:

~~~text
Record memory (ví dụ ABI thông dụng)
byte offset    0    1    2    3    4    5    6    7
               +----+----+----+----+----+----+----+----+
               |kind|       padding     |   count      |
               +----+----+----+----+----+----+----+----+
offsetof(kind)  = 0
offsetof(count) = 4
sizeof(Record)  = 8
_Alignof(Record)= 4
~~~

Nhưng con số **4/8** trên đây là ví dụ, **không phải điều FFM tự biết từ tên struct**. Nếu compiler dùng packing khác, target ABI khác hoặc header thay đổi, layout có thể khác.

### Khai báo MemoryLayout có padding tường minh

Một mô tả tương ứng với sơ đồ phổ biến trên:

~~~java
MemoryLayout recordLayout = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("count")
);
~~~

Đây là một **layout minh họa có điều kiện ABI**. **MemoryLayout.structLayout không tự chèn C-style padding** giữa các member để khớp compiler. Mỗi layout cần được xây từ **thông tin ABI thực**.

Nếu struct đi **by value** vào foreign call, linker có thể yêu cầu layout tuân thủ những giới hạn chặt chẽ hơn về alignment và padding. Với **pointer to struct**, bạn có thể dùng ADDRESS ở descriptor, nhưng vẫn phải có layout chính xác khi truy cập field từ Java. Cả hai hướng đều không miễn nhiệm việc xác minh.

### Nguồn xác minh layout đáng tin

Nguồn của sự thật không phải “trông giống C” mà là **C compiler đã build binary thực tế**.

Dùng:

- **sizeof(Record)** để biết tổng byte size kể cả padding cuối.
- **_Alignof(Record)** hoặc **alignof** theo C standard/compiler để biết alignment.
- **offsetof(Record, count)** (từ **<stddef.h>**) để biết byte offset field thông thường.
- **Static assertions** trong C để kiểm tra giả định về kiểu và ABI.
- **Một shim xuất các giá trị trên** để Java kiểm chứng lúc khởi động nếu build hỗ trợ nhiều target.
- **ABI test** chạy trên chính binary/OS/compiler flags sẽ deploy, nhất là với packing/typedef/macro.

**Lưu ý:** **offsetof** không dùng trực tiếp cho mọi bit-field vì bit-field không có address như field bình thường. Với bit-field hoặc packed layout bất thường, wrapper có C getter/setter thường an toàn và dễ bảo trì hơn việc Java tự đoán bit offsets.

### Vì sao kiểm tra mỗi sizeof chưa đủ?

Hai struct có thể có **cùng tổng byte size nhưng khác field offset hoặc kiểu member**. Khi FFM đọc nhầm offset, giá trị có thể sai mà không chạm ngoài bounds, nên Java không ném exception. Vì vậy khi phải truy cập field trực tiếp, hãy xác minh **size, alignment, offsets và loại field**, không chỉ tổng size.

## 6. Pointer C không tự mang bounds, ownership hay lifetime

Trong C, hai prototype sau đều trả về một con trỏ:

~~~c
const char *api_borrow_name(void);
char *api_make_name(void);
~~~

Nhưng hành vi có thể hoàn toàn khác:

- Hàm **borrow_name** có thể trả pointer mượn tới vùng static, vùng nội bộ của một object, hoặc buffer chỉ tồn tại đến lần gọi tiếp theo.
- Hàm **make_name** có thể yêu cầu caller giải phóng bằng **api_free_name**, **free** hoặc một allocator riêng.
- Cũng có khả năng một hoặc cả hai trả **NULL** khi lỗi.

**FFM chỉ thấy địa chỉ và descriptor**, không tự suy ra những nghĩa trên từ tên hàm. Ngay cả **const char\*** cũng không chỉ rõ độ dài, encoding, dữ liệu có NUL terminator, thời điểm hết hạn hoặc khả năng null.

### Pointer trả về thường là segment có chiều dài 0

Khi FFM nhận pointer không có kích thước đã biết, nó thường biểu diễn pointer bằng **MemorySegment có byteSize() == 0**. Đây là lựa chọn thận trọng: không thể xác định đọc bao nhiêu byte từ một địa chỉ trần.

Ví dụ:

~~~java
MemorySegment ptr = /* kết quả của hàm C trả void* */;
System.out.println(ptr.byteSize()); // thường 0 cho raw pointer
~~~

Đây là **snippet khái niệm**, không thể chạy độc lập do chưa có hàm C và ptr thực. Không coi **byteSize()==0** là “C thực sự cấp phát 0 byte”; nó có thể chỉ có nghĩa **Java chưa biết bounds**.

FFM có phương thức restricted **MemorySegment.reinterpret(...)** để gán bounds/lifetime mới khi bạn **đã có bằng chứng từ hợp đồng C**. Nhưng **reinterpret không cấp phát thêm bộ nhớ và không chứng minh địa chỉ hợp lệ**. Nếu tự reinterpret một con trỏ dangling thành 1 GB, giới hạn FFM có thể cho phép đọc trong phạm vi 1 GB do bạn khai báo, còn OS/native memory có thể không hợp lệ; truy cập sai có thể gây crash.

### Một pointer đúng cần ít nhất sáu thông tin

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| **Address và nullability** | Có thể trả NULL không? NULL nghĩa empty hay error? |
| **Size và đơn vị** | Có bao nhiêu **byte**, phần tử hay code units? Ai cung cấp size? |
| **Element layout** | Con trỏ trỏ tới char, int32_t, struct hay một vùng bytes opaque? |
| **Ownership** | Caller sở hữu, chỉ mượn, hay chia sẻ? |
| **Lifetime** | Tồn tại đến khi nào? Đến khi free, đến khi object C đóng, hay chỉ trong callback? |
| **Deallocator** | Có được dùng free không? Cần api_destroy? Có được giải phóng ở thread khác? |

Ngoài ra còn có **alignment, mutability, thread-safety, aliasing và khả năng pointer được giữ sau lời gọi**.

### Không được kết hợp sai allocator

Nếu C API cấp phát bằng **api_create_buffer**, không mặc định **Arena.close()** hoặc C **free** phù hợp để giải phóng. Thư viện có thể dùng custom pool, C++ new/delete, allocator theo phiên bản runtime hoặc yêu cầu gọi **api_release_buffer** để giảm reference count.

**Đúng về ý tưởng:** wrapper Java triển khai **AutoCloseable**, lưu address và gọi **đúng deallocator được tài liệu C chỉ định**, đúng một lần, ở thời điểm không còn dùng.

**Sai về ý tưởng:** gán một address bất kỳ vào arena rồi coi việc đóng arena như một phép giải phóng an toàn tự động. Arena không thể giải phóng vùng nhớ mà nó không sở hữu chỉ từ địa chỉ.

### Pointer-to-pointer và output parameters

Một API như:

~~~c
int api_read_data(unsigned char **out, size_t *out_len);
~~~

có **hai cấp con trỏ** và một tham số output. FFM không thể tự suy ra:

- Ai cấp bộ nhớ cho **\*out**?
- Giá trị **\*out_len** đo byte hay phần tử?
- Khi result lỗi, **\*out** có được khởi tạo không?
- Caller có phải free **\*out** không?
- Có thể trả **\*out == NULL** và **\*out_len == 0** không?
- Kích thước của **size_t** trên ABI này là gì?

Java phải cấp chỗ chứa **một address** và **một size_t**, đọc chúng sau khi hàm trả thành công, kiểm tra bound/overflow rồi giải phóng kết quả đúng cách. **ValueLayout.ADDRESS** cho **out** không tự cung cấp các quy tắc đó.

## 7. Arena chỉ quản được những gì thuộc scope của nó

**Arena** giúp Java cấp phát native memory và quản lý thời điểm vùng nhớ đó bị thu hồi theo hợp đồng scope. Nhưng nó không biến một borrowed C pointer thành owned pointer hoặc bảo vệ một pointer đã bị C giải phóng ở ngoài Java.

| Arena | Đặc điểm | Cẩn thận |
| --- | --- | --- |
| **Arena.ofConfined()** | Native segment chỉ truy cập được từ thread sở hữu, có thể đóng rõ ràng | Không trao segment cho async native worker rồi đóng arena trước khi worker xong |
| **Arena.ofShared()** | Segment có thể được dùng từ nhiều Java threads, đóng rõ ràng | Dùng chung được không có nghĩa truy cập dữ liệu tự đồng bộ |
| **Arena.ofAuto()** | Vùng nhớ được quản qua khả năng thu hồi tự động | Thời điểm giải phóng không xác định; khó dùng để khớp callback lifetime |
| **Arena.global()** | Scope sống không giới hạn trong JVM | Không được đóng, dễ tạo vùng nhớ tồn tại suốt process nếu cấp phát tùy tiện |

Ví dụ:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment buffer = arena.allocate(128, 8);
    buffer.set(ValueLayout.JAVA_INT, 0, 42);

    // Chỉ chuyển buffer cho hàm C đã được xác nhận là
    // KHÔNG giữ pointer sau khi downcall hoàn tất.
}
// Arena.close() làm buffer không còn hợp lệ.
~~~

Đây là **snippet Java 22+**, không có C downcall thật. Các kiểm tra FFM về lifetime/bounds giúp phát hiện **lỗi truy cập do Java thực hiện sau khi scope đóng**. Nhưng nếu C code đã lưu địa chỉ vào một hàng đợi và còn dùng sau khi arena đóng, Java không thể chặn tất cả truy cập đó vì chúng diễn ra bên ngoài JVM.

### Borrowed trong một lần gọi khác async retention

**C contract A:** “Function chỉ đọc buffer trong khi lời gọi đang diễn ra; không giữ pointer.” Có thể tạo buffer từ confined arena, gọi downcall đồng bộ, trả về rồi đóng arena.

**C contract B:** “Function lưu pointer và có thể dùng sau khi trả về; callback được gọi trên worker.” Không được tự động đóng arena khi downcall trả về. Cần scope đủ dài, có shutdown/unregister, bảo đảm callback kết thúc trước khi giải phóng và quản lý synchronization.

**C contract C:** “Function trả pointer nội bộ, chỉ hợp lệ đến lần gọi kế tiếp.” Không nên giữ pointer qua lời gọi khác rồi truy cập; copy dữ liệu cần thiết ngay trong cửa sổ hợp lệ hoặc dùng API copy do library cung cấp.

FFM không tự phân biệt A/B/C khi chỉ nhìn thấy C pointer parameter và return type.

## 8. String, null terminator và buffer length: hợp đồng của C là bắt buộc

Một chữ ký C:

~~~c
int api_parse(const char *text);
~~~

**Không đủ** để biết text phải theo UTF-8, ASCII, Latin-1, UTF-16 hay một encoding chuyên biệt. C cũng có thể yêu cầu byte **00** kết thúc chuỗi. Trên Java, String là dữ liệu Unicode (được biểu diễn theo UTF-16), không đồng nghĩa trực tiếp với **char\***.

FFM hỗ trợ tạo **C string** với allocator (ví dụ **Arena.allocateFrom(String)** trong JDK 22), dùng encoding theo API Java đó và NUL terminator. Điều này hữu ích **nếu** C API thực sự yêu cầu C-string theo encoding tương ứng.

Tuy nhiên phải kiểm tra:

- C API cần **UTF-8 chuẩn** hay một encoding khác?
- C string có thể chứa **U+0000** ở giữa không? Nếu C dùng strlen, byte 00 sẽ kết thúc sớm.
- C API dùng **số byte**, số ký tự, số element hay delimiter để xác định length?
- API có sửa **char\*** không? Buffer Java cấp có đủ capacity cho output và terminator không?
- Một biến **size_t length** có đo **đầu vào**, **dung lượng đầu ra** hay **độ dài thực tế đã ghi**?
- C API có thể giữ pointer tới text sau lời gọi hay không?

Đặc biệt, không lấy **Java String.length()** (số UTF-16 code units) rồi truyền như số byte UTF-8. Một emoji ngoài BMP có thể là 2 code units nhưng 4 UTF-8 bytes. Ngược lại, C API dùng **modified UTF-8** theo JNI có một hợp đồng khác UTF-8 chuẩn.

**FFM không thể tự đổi nghĩa của tham số length chỉ vì nó mang kiểu size_t.** Tài liệu C phải định nghĩa đơn vị đo và quan hệ giữa pointer và length.

## 9. Hợp đồng callback, error handling và luồng

Một C API có thể nhận function pointer:

~~~c
typedef void (*event_cb)(int code, void *user_data);

int api_register_callback(event_cb cb, void *user_data);
void api_unregister_callback(void);
~~~

**FFM upcall stub** có thể tạo function pointer trỏ vào Java MethodHandle. Nhưng C prototype trên không nói:

- C sẽ giữ cb đến khi nào?
- Callback có thể chạy **trên native thread** không?
- Có gọi đồng thời nhiều callback không?
- Có thể callback re-enter API C không?
- Sau unregister, C có bảo đảm không còn callback đang chạy không?
- **user_data** có thuộc quyền Java/C không, và ai giải phóng?
- Callback có thể ném exception Java không? Thực tế callback phải có chính sách bắt/chuyển lỗi rõ ràng; không để một Java exception tùy ý “bay qua” C ABI.

Nếu upcall stub thuộc một arena đã đóng, mà C vẫn giữ và gọi function pointer đó, chương trình có thể crash. Phải đặt **scope của stub** khớp thời gian C dùng callback và có giao thức unregister/drain trước khi giải phóng.

### Error code, errno và kết quả một phần

C API thường có nhiều kiểu báo lỗi:

| Kiểu | Điều cần biết |
| --- | --- |
| Trả **int status** | Những giá trị nào là success/failure? Có output parameter hợp lệ khi lỗi không? |
| Trả **NULL** | NULL nghĩa lỗi, không có dữ liệu hay giá trị hợp lệ? |
| Đặt **errno** | Có phải đọc ngay sau downcall trên cùng thread không? Có dùng lựa chọn capture call state của linker phù hợp không? |
| Trả **size_t** | Có sentinel như SIZE_MAX không, và Java xử lý unsigned thế nào? |
| Dùng **callback báo lỗi** | Callback chạy ở thread nào, có thứ tự/bảo đảm delivery nào? |
| C++ ném exception | Wrapper phải chuyển thành C ABI error model; không để exception vượt ABI FFM |

**Linker không đoán error semantics**. Một return value kiểu **int** chỉ là số nguyên về mặt ABI. Việc **-1** là lỗi, hay là một kết quả hợp lệ, hoàn toàn phụ thuộc hợp đồng.

### Thread-safe không đồng nghĩa dùng được từ mọi thread

Ngay cả khi **Arena.ofShared()** cho phép Java threads truy cập MemorySegment, library C có thể yêu cầu mọi API được gọi trên cùng một native thread, một event loop hoặc giữ một mutex do library quản lý.

Nếu API có thread-affinity, Java cần điều phối các downcall trên đúng executor/thread. Nếu API tự lưu pointer vào worker, Java phải giữ vùng nhớ sống đủ lâu. Những điều này **không thể được suy ra chỉ từ FunctionDescriptor hoặc MemorySegment**.

## 10. Một bảng hợp đồng C tối thiểu trước khi viết binding

Với mỗi hàm native, nên ghi lại ít nhất:

| Hạng mục | Câu hỏi cần trả lời | Nguồn kiểm chứng |
| --- | --- | --- |
| **Tên symbol** | Tên export chính xác là gì? Có C++ mangling không? | Header, binary symbols, export map |
| **Prototype** | Return/argument types, by-value hay by-pointer, varargs? | Header đúng phiên bản |
| **ABI** | OS/CPU/compiler, calling convention, typedef width? | Build/toolchain docs, linker canonical layouts |
| **Struct layout** | sizeof, alignof, offsetof, padding/packing? | sizeof/_Alignof/offsetof từ binary/shim |
| **Pointer length** | Bao nhiêu byte/element? Ai cung cấp length? | Docs, header comments, tests |
| **Nullability** | Cho phép NULL ở tham số/return không? | API contract |
| **Ownership** | Borrowed, returned owned hay transfer ownership? | API contract |
| **Deallocator** | Gọi free, destroy, release hay không được free? | API contract, allocator docs |
| **Lifetime** | Pointer còn hợp lệ đến khi nào? | Docs, callback/worker lifecycle |
| **Encoding** | UTF-8, ASCII, UTF-16 hay binary? NUL terminator? | API contract |
| **Mutability** | const/input/output/in-out? Buffer capacity? | API contract |
| **Threading** | Reentrant/thread-safe, thread affinity, callback async? | Docs/tests |
| **Errors** | Status, NULL, errno, sentinel, partial output? | Docs/tests |
| **Versioning** | Struct ABI/symbol thay đổi theo release nào? | SDK version, changelog, ABI tests |

Nếu câu trả lời còn thiếu, một **C adapter mỏng** có thể giúp biến một giao diện khó gọi thành API rõ ràng hơn: kiểu **int32_t/uint32_t** khi phù hợp, pointer+byte-length, error code ổn định, hàm release nhất quán và các probe sizeof/offsetof. Adapter **không thay thế tài liệu lifecycle**, nhưng giảm bề mặt ABI mà FFM phải mô tả.

## 11. Ví dụ hoàn chỉnh: Java 22+ và C11 tự xác nhận ABI trước khi đọc struct

Ví dụ minh họa sự khác nhau giữa:

- **Thông tin FFM có thể lấy từ native Linker:** canonical layout của **size_t**.
- **Thông tin phải lấy từ C binary thực:** **sizeof**, **alignment** và **offsetof** của struct.
- **Hợp đồng phải do C API công bố:** hàm chỉ **mượn** pointer trong thời gian downcall, không giữ pointer sau khi trả về; giá trị âm **-1** dùng báo lỗi.
- **Điều mà FFM làm được sau khi có thông tin:** cấp buffer đúng size/alignment, đặt field đúng offset và gọi native function.

### 11.1. Header/implementation C: ffm_contract.c

Tạo file **ffm_contract.c**:

~~~c
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

/*
 * Ví dụ cố ý yêu cầu uint8_t là 1 byte và uint32_t là 4 byte.
 * Không dùng pragma pack; layout do C compiler thực quyết định.
 */
_Static_assert(CHAR_BIT == 8, "this demo requires 8-bit bytes");
_Static_assert(sizeof(uint32_t) == 4, "uint32_t must be 4 bytes");

typedef struct Record {
    uint8_t kind;
    uint32_t count;
} Record;

/* Trả metadata đúng với binary C đã biên dịch. */
API size_t record_size(void) {
    return sizeof(Record);
}

API size_t record_alignment(void) {
    return _Alignof(Record);
}

API size_t record_count_offset(void) {
    return offsetof(Record, count);
}

/*
 * HỢP ĐỒNG:
 * - p được mượn, không bị lưu sau khi hàm trả về.
 * - p != NULL, trỏ tới một Record hợp lệ, đúng alignment.
 * - delta >= 0.
 * - count, kind là số không dấu.
 * - Trả kết quả không âm hoặc -1 khi p/delta không hợp lệ
 *   hoặc tổng vượt phạm vi int32_t.
 * - Hàm không cấp phát/giải phóng và không giữ callback.
 */
API int32_t record_score(const Record *p, int32_t delta) {
    if (p == NULL || delta < 0) {
        return -1;
    }

    uint64_t sum = (uint64_t)p->count
                 + (uint64_t)p->kind
                 + (uint64_t)(uint32_t)delta;

    if (sum > INT32_MAX) {
        return -1;
    }
    return (int32_t)sum;
}
~~~

**Giải thích C contract:**

- **size_t** là kiểu native theo ABI; FFM phải lấy layout từ native linker. Không viết cứng “size_t = C long”.
- **uint8_t** và **uint32_t** biểu diễn số nguyên width cố định trong môi trường mà chúng có sẵn; static assertions giúp chặn build không phù hợp.
- **Record** có hai trường, nhưng code Java không mặc định field count nằm ở offset 4: C cung cấp **record_count_offset()**.
- **record_alignment()** giúp Java cấp phát đúng alignment. C không yêu cầu Java tự suy đoán từ tên field.
- **record_score** chỉ đọc pointer, không giữ hoặc giải phóng. Vì thế Java có thể dùng confined arena trong phạm vi một lời gọi đồng bộ.
- Error **-1** được dùng rõ ràng theo hợp đồng; giá trị hợp lệ của hàm được giới hạn không âm.

### 11.2. Biên dịch native library

**Linux (GCC hoặc Clang, C11):**

~~~bash
cc -std=c11 -O2 -fPIC -shared \
  ffm_contract.c -o libffmcontract.so
~~~

**macOS (Clang, C11):**

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  ffm_contract.c -o libffmcontract.dylib
~~~

**Windows (Visual Studio 2022 Developer Command Prompt, hỗ trợ C11):**

~~~bat
cl /nologo /W4 /std:c11 /LD ffm_contract.c /link /OUT:ffmcontract.dll
~~~

Các lệnh trên là **phương án build thay thế theo hệ điều hành**, không phải các bước chạy liên tiếp. Chọn toolchain native tương thích JDK/OS/CPU/ABI đang sử dụng. Tên thư viện do lệnh build tạo tương ứng với **System.mapLibraryName("ffmcontract")** trên các nền tảng thông dụng.

### 11.3. Tạo AbiContractDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class AbiContractDemo {
    private AbiContractDemo() {
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // size_t là C ABI type, không được hardcode JAVA_LONG.
        MemoryLayout sizeT =
                linker.canonicalLayouts().get("size_t");
        if (!(sizeT instanceof ValueLayout)) {
            throw new IllegalStateException("No size_t layout");
        }

        // Arena giữ native library lookup và buffer cùng sống.
        try (Arena arena = Arena.ofConfined()) {
            Path library = Path.of(
                    System.mapLibraryName("ffmcontract")
            ).toAbsolutePath();

            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // C size_t record_size(void)
            MethodHandle sizeof = linker.downcallHandle(
                    symbols.find("record_size").orElseThrow(),
                    FunctionDescriptor.of(sizeT)
            );

            // C size_t record_alignment(void)
            MethodHandle alignof = linker.downcallHandle(
                    symbols.find("record_alignment").orElseThrow(),
                    FunctionDescriptor.of(sizeT)
            );

            // C size_t record_count_offset(void)
            MethodHandle offsetof = linker.downcallHandle(
                    symbols.find("record_count_offset").orElseThrow(),
                    FunctionDescriptor.of(sizeT)
            );

            /*
             * C size_t có carrier int hoặc long tùy ABI.
             * invokeWithArguments trả boxed Number ứng với carrier,
             * thay vì invokeExact sai kiểu trên một nền tảng.
             * Đây là các giá trị metadata nhỏ, không phải SIZE_MAX.
             */
            long size = ((Number) sizeof.invokeWithArguments())
                    .longValue();
            long alignment = ((Number) alignof.invokeWithArguments())
                    .longValue();
            long countOffset =
                    ((Number) offsetof.invokeWithArguments())
                            .longValue();

            /*
             * Chính sách ứng dụng: chỉ hỗ trợ Record nhỏ, có
             * alignment ít nhất 4 và field count được căn 4 byte.
             * Bắt sai ABI/probe trước khi tự đọc hoặc ghi vùng nhớ.
             */
            boolean valid = size >= 8
                    && size <= 1024
                    && alignment >= 4
                    && (alignment & (alignment - 1)) == 0
                    && countOffset >= 1
                    && countOffset % 4 == 0
                    && countOffset <= size - Integer.BYTES;

            if (!valid) {
                throw new IllegalStateException(
                        "Unsupported native Record layout"
                );
            }

            MemorySegment record = arena.allocate(size, alignment);

            // kind là uint8_t, count là uint32_t trong C.
            // Giá trị 3 và 7 nằm trong miền có dấu của carrier Java.
            record.set(ValueLayout.JAVA_BYTE, 0, (byte) 3);
            record.set(ValueLayout.JAVA_INT, countOffset, 7);

            // C int32_t record_score(const Record*, int32_t)
            MethodHandle score = linker.downcallHandle(
                    symbols.find("record_score").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT
                    )
            );

            // invokeExact: (MemorySegment, int) -> int.
            int result = (int) score.invokeExact(record, 2);
            if (result < 0) {
                throw new IllegalStateException(
                        "Native record_score failed"
                );
            }

            System.out.println("abiVerified=true");
            System.out.println("result=" + result);
        }
    }
}
~~~

### 11.4. Biên dịch và chạy trên JDK 22+

Đặt **AbiContractDemo.java** và native library trong cùng thư mục đang làm việc. Không cần JNI header hoặc JNI native method; ứng dụng này dùng FFM trực tiếp.

~~~bash
javac AbiContractDemo.java
java --enable-native-access=ALL-UNNAMED AbiContractDemo
~~~

Nếu binary C đúng hợp đồng trên một ABI được demo chấp nhận, **stdout chính xác** là:

~~~text
abiVerified=true
result=12
~~~

Vì Java ghi **kind=3**, **count=7** và truyền **delta=2**, hàm C trả **3 + 7 + 2 = 12**.

Những thông tin **size, alignment, countOffset** được lấy từ C binary ngay khi chạy, vì thế code **không in các giá trị giả định** như “sizeof=8” làm kết quả trở thành platform-dependent. Nếu platform không thỏa chính sách layout mẫu, Java dừng bằng exception **trước khi gọi record_score**, thay vì đoán offset.

### 11.5. Bài demo chứng minh và không chứng minh điều gì?

**Chứng minh:**

- Linker cho phép lấy **canonical layout của size_t** theo ABI native.
- SymbolLookup tìm function pointer theo symbol names mà C export.
- Các hàm C **record_size/record_alignment/record_count_offset** cung cấp metadata mà FFM không biết từ tên **Record**.
- Java dùng size/alignment/offset đã kiểm tra để cấp và ghi native memory trong arena.
- Descriptor cho **record_score** được khai báo tường minh và chỉ đúng nhờ hợp đồng C source/binary thực.
- Với một hàm C chỉ mượn pointer trong lời gọi, arena có thể đóng sau downcall.

**Không chứng minh:**

- Một layout C khác ngoài **Record** tự nhiên đúng; phải probe/kiểm thử riêng.
- Mọi **size_t** đều vừa long signed hoặc đều có thể chuyển thành Number.longValue cho giá trị lớn; demo chỉ đọc metadata nhỏ.
- Mọi hàm C trả pointer đều có bounds/lifetime an toàn; ví dụ không có pointer return/async.
- FFM sẽ phát hiện descriptor sai nếu C library bị thay bằng binary khác.
- Một lời gọi Java/C thành công đồng nghĩa thư viện C thread-safe hoặc sẵn sàng cho concurrency.
- Demo tương thích JDK 17–21; nó yêu cầu **JDK 22+**.

**Giới hạn kiểm chứng:** Đây là một ví dụ Java/C đầy đủ về mặt source. Kết quả stdout được xác định từ code khi build/deploy thành công; integration cần được chạy trên JDK/toolchain thực tế trước khi đưa vào production.

## 12. Vì sao probe native và header vẫn chưa đủ?

Có compiler-probe không thay thế việc đọc tất cả hợp đồng C.

### 12.1. Pointer lifetime không có trong sizeof

Bạn có thể biết **sizeof(Record)=8** nhưng vẫn đưa C một pointer vào arena rồi **đóng arena trước callback bất đồng bộ**. Layout đúng không cứu được use-after-free. Metadata type/layout không trả lời câu hỏi “C còn dùng pointer sau khi hàm trả về không?”.

### 12.2. Một field offset đúng không xác thực semantic

Ví dụ field **count** nằm ở offset 4 trên cả hai bản C library, nhưng version 2 thay đổi đơn vị từ **bytes** sang **elements**. Java vẫn đọc một int đúng offset nhưng logic sai. Phải versioning và contract test ngữ nghĩa.

### 12.3. ABI có thể đổi mà Java source không đổi

Nhiều yếu tố có thể làm native ABI khác:

- Đổi compiler, target triple, compiler flags hoặc packing.
- Đổi cấu hình typedef/macro khi build library.
- Đổi JDK runtime architecture so với library.
- Đổi cách compiler export C++ symbols.
- Nâng version library nhưng không đồng bộ header.
- Đổi calling convention hoặc bản build optimized với assumptions khác.

**Cần khóa phiên bản header và binary** vào một gói triển khai rõ ràng, ghi checksum/build metadata và kiểm tra ABI ở CI/khởi động khi thích hợp.

### 12.4. Generated bindings không thay thế contract review

Công cụ như **jextract** có thể đọc header bằng parser C và tạo Java bindings/layout phù hợp cho loại khai báo được hỗ trợ. Nó giúp giảm lỗi gõ descriptor và offsets, nhưng **không tự làm rõ mọi ý nghĩa** như:

- Caller có sở hữu pointer không?
- Hàm có lưu buffer sau khi trả về không?
- Nên gọi free hay destroy riêng?
- API callback có thể chạy từ thread nào?
- Giá trị nào là error sentinel?
- Một trường độ dài dùng byte hay code point trong giao thức?
- Có version nào làm thay đổi semantics không?

Vì vậy generated code phải đi cùng **wrapper hợp đồng được kiểm thử**. Đừng hiểu “binding compile được” là “memory safe đã được chứng minh”.

## 13. Một số tình huống thực tế

### Tình huống A — C long sai trên Windows x64

Java wrapper viết:

~~~java
FunctionDescriptor.of(ValueLayout.JAVA_LONG)
~~~

cho hàm **long get_total(void)** vì code được phát triển trên Linux/x64. Khi chạy Windows/x64, **C long thường là 32 bit**; descriptor có thể làm lệch cách truyền/nhận kết quả.

**Cách xử lý:** dùng canonical layout **"long"** cho native ABI và code chọn carrier đúng; tốt hơn nữa, với một public C API được kiểm soát, cân nhắc xuất hàm có kiểu cố định **int64_t** nếu điều đó phù hợp hợp đồng.

### Tình huống B — Pointer + length bị nhầm byte và elements

C API yêu cầu:

~~~c
void api_write(const uint16_t *items, size_t item_count);
~~~

Java truyền **buffer.byteSize()** vào **item_count**, dẫn tới C có thể đọc gấp đôi số phần tử.

**Cách xử lý:** mô tả count là **số uint16_t elements**, tính theo tổng byte **chia sizeof(uint16_t)** sau kiểm tra chia hết và range, không gửi byte count bừa.

### Tình huống C — Pointer mượn bị free sai

C API trả **const char\*** trỏ vào vùng static/internal. Java wrapper tạo một cleanup action gọi **free(pointer)** khi arena đóng.

**Hậu quả:** cố giải phóng vùng không thuộc quyền caller, có thể crash hoặc phá allocator.

**Cách xử lý:** tài liệu hóa borrowed pointer, **không free**; nếu cần sống lâu, copy dữ liệu vào vùng Java/caller sở hữu trong thời hạn hợp lệ.

### Tình huống D — C ghi output vượt buffer

C API nhận **char *out, size_t capacity**, có thể ghi tới **capacity** bytes và chèn terminator tùy trạng thái. Java cấp **capacity** nhỏ nhưng báo con số lớn.

**Hậu quả:** C tràn buffer. FFM không thể chặn write trực tiếp từ C chỉ bằng bounds của Java segment nếu C đã được truyền pointer và length sai.

**Cách xử lý:** truyền capacity đúng byteSize của vùng đã cấp (hoặc capacity được kiểm chứng nhỏ hơn), có giao thức output length riêng và fuzz test với input xấu.

### Tình huống E — Callback dùng sau khi arena đóng

Java tạo upcall stub trong confined arena, C lưu callback và dùng sau khi đăng ký hoàn tất. Java kết thúc try-with-resources rồi C worker gọi pointer.

**Hậu quả:** pointer tới stub đã hết hạn; có thể crash.

**Cách xử lý:** tách scope callback dài hạn, có hàm unregister và bảo đảm không còn callback đang chạy trước khi đóng arena. Dùng synchronization và Java exception policy phù hợp.

### Tình huống F — Struct field đọc sai nhưng không crash

C đổi packing làm **offsetof(count)** từ 4 sang 1. Java wrapper vẫn dùng offset 4. Segment vẫn đủ byte và Java get không vượt bounds, nhưng đọc giá trị rác.

**Cách xử lý:** lấy/kiểm tra **offsetof**, **alignment**, **size** của binary thực hoặc bọc struct bằng C accessor functions. Không dùng ngoại lệ Java như một phương pháp xác nhận ABI.

## 14. Kiểm thử và kiểm chứng trong CI

Đối với FFM bindings, các loại kiểm thử nên tách rõ:

1. **Header/binary identity:** xác minh đúng native library, version, export names và checksum.
2. **ABI probe:** so sánh **sizeof, _Alignof, offsetof** của struct; kiểm tra width của C typedef cần dùng.
3. **Function signature smoke test:** gọi từng hàm với input đơn giản, giá trị sentinel và return structure thật; đặc biệt các hàm nhận/trả struct by value.
4. **Pointer contract tests:** NULL/zero-length, buffer nhỏ, output capacity, alignment, ownership, double-free và use-after-free có kiểm soát trong môi trường test.
5. **Error handling tests:** mã lỗi, errno/call-state, partial writes và đường cleanup.
6. **Threading/callback tests:** concurrent calls, unregister, callback đến muộn, arena lifetime, thread affinity.
7. **Boundary tests:** SIZE_MAX/overflow, ký tự Unicode, empty strings, dữ liệu lớn và malformed input.
8. **Platform matrix:** Linux/macOS/Windows và CPU/ABI/JDK mà sản phẩm thực sự hỗ trợ.
9. **Native diagnostics:** có thể dùng ASan/UBSan của compiler và JVM crash logs khi thích hợp; Java exception không chặn mọi memory corruption trong C.
10. **Upgrade/rollback:** thay native binary hoặc header version, xác minh wrapper từ chối ABI không tương thích trước khi xử lý dữ liệu thật.

Nếu library là mã bên thứ ba, ưu tiên chạy phép thử phức tạp trên **tiến trình riêng**. Một lỗi native có thể làm sập cả JVM đang chạy test, nên test harness cần chịu được crash và phân loại kết quả rõ ràng.

## 15. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Mọi **C long** đều map JAVA_LONG | LP64 và LLP64 khác nhau | Dùng linker canonical layout **long** hoặc API cố định width |
| Mọi **size_t** đều là Java long | Trên 32-bit có thể là 32 bit, unsigned semantics khác | Dùng canonical **size_t** và carrier đúng |
| Tìm được symbol nghĩa là signature chính xác | Symbol không mang toàn bộ prototype | Đối chiếu header/binary, build ABI smoke tests |
| Dùng ADDRESS là đã biết pointer trỏ bao nhiêu byte | Address không tự có length | Lấy size từ hợp đồng, kiểm tra rồi mới truy cập |
| Reinterpret 1 GB là được 1 GB bộ nhớ hợp lệ | reinterpret chỉ thay bounds mô hình hóa | Chỉ reinterpret theo thông tin cấp phát/owner đã xác minh |
| Arena.close() giải phóng mọi con trỏ C | Arena chỉ quản vùng do nó sở hữu hoặc cleanup đã cấu hình đúng | Gọi deallocator do C API quy định |
| Thấy **const char\*** thì mặc định UTF-8 và owned | const không nêu charset/lifetime | Đọc contract, kiểm tra encoding và ownership |
| Copy struct fields liên tục không padding | Compiler có padding/alignment | Probe **sizeof/alignof/offsetof** |
| Struct sizeof đúng thì offsets chắc đúng | Cùng size vẫn có thể khác layout | So mọi field offset/type cần dùng |
| Truyền Java String.length làm số byte UTF-8 | Java length đếm UTF-16 units | Encode rồi lấy byte count |
| Để C lưu arena pointer qua return | Use-after-free khi arena đóng | Scope dài đủ và giải phóng sau drain |
| Dùng callback sau khi arena chứa stub đóng | Function pointer hết hạn | Unregister/join callback trước khi close |
| Library C không thread-safe nhưng dùng shared Arena | Shared arena chỉ cho phép truy cập segment đa luồng | Đồng bộ và tuân thủ thread affinity C |
| Bỏ qua errno/status do đã có MethodHandle | FFM không tự chuyển C error thành Java exception | Đọc contract và check lỗi tường minh |
| Dùng C++ function trực tiếp không xét ABI/mangling | Không tìm đúng symbol hoặc gọi sai ABI | Tạo **extern "C"** adapter được kiểm thử |
| Generated binding từ header = đã an toàn | Header không mô tả đầy đủ lifetime/semantics | Review ownership, errors, callbacks và versioning |

## 16. Checklist trước khi đưa FFM binding vào production

- [ ] Đã khóa **JDK baseline** và kiểm tra native access settings (JDK 22+ cho API ở bài).
- [ ] Có **đúng header và đúng binary** cho OS/CPU/ABI/compiler target.
- [ ] Đã xác định tên export/C++ name mangling và calling convention.
- [ ] Mỗi FunctionDescriptor mô tả đúng số tham số, kiểu return, by-value/by-pointer, variadic nếu có.
- [ ] Với **long, size_t, wchar_t** và C typedef: dùng ABI canonical layout/probe, không suy diễn từ kiểu Java.
- [ ] Với **struct/union/array**: đã xác minh size, alignment, field offsets, padding/packing và endian khi cần.
- [ ] Với mọi pointer: có **length + đơn vị + nullability + ownership + lifetime + deallocator**.
- [ ] Không dùng reinterpret để tự bịa bounds; biết rõ khi nào pointer C có thể hết hiệu lực.
- [ ] Không đóng arena trước khi native worker/callback dùng xong pointer/stub.
- [ ] Mỗi hàm C có error model, state khi thất bại và cleanup path được kiểm chứng.
- [ ] Buffer length và capacity chống tràn integer, tránh overflow/over-read/over-write.
- [ ] Đã xác nhận encoding/terminator và xử lý embedded NUL khi chuyển String.
- [ ] Đã xem xét thread-safety/reentrancy, callback thread, unregister và shutdown.
- [ ] Có smoke test & ABI test trên từng release, toolchain và native runtime đích.
- [ ] Có cách cô lập crash và rollback khi nâng cấp thư viện native.

## 17. Câu hỏi tự kiểm tra

**1. Tại sao native Linker biết ABI nhưng vẫn không tự kiểm chứng một FunctionDescriptor?**

**Trả lời:** Linker biết cách **thực hiện** lời gọi theo ABI khi nhận layout đã khai báo; symbol thường không cung cấp đầy đủ thông tin prototype. Người viết binding phải cung cấp đúng layout của hàm C thực.

**2. Tại sao C long trên Windows x64 thường không được map bằng ValueLayout.JAVA_LONG?**

**Trả lời:** Data model LLP64 thường có C long 32 bit, trong khi Java long 64 bit. Dùng canonical layout **long** theo ABI hoặc wrapper có fixed-width type.

**3. Một C function trả void*; FFM trả MemorySegment có byteSize bằng 0. Có nghĩa C cấp phát 0 byte?**

**Trả lời:** Không. FFM có thể chỉ biết địa chỉ mà không biết kích thước hoặc lifetime. Muốn đọc phải có hợp đồng kích thước thực và thao tác reinterpret/target layout đúng, vẫn chịu rủi ro nếu pointer không hợp lệ.

**4. Vì sao sizeof(struct) chưa đủ để truy cập field an toàn?**

**Trả lời:** Hai layout có thể cùng total size nhưng khác offsets hoặc kiểu field. Cần kiểm chứng alignment, offsetof, field types và version/packing.

**5. Khi nào Arena.ofConfined có thể đóng ngay sau downcall?**

**Trả lời:** Khi C API chỉ **mượn pointer trong thời gian lời gọi đồng bộ**, không lưu pointer hay khởi chạy async callback sử dụng buffer đó sau khi return.

**6. Vì sao const char* không đồng nghĩa UTF-8, NUL-terminated và borrowed?**

**Trả lời:** const chỉ ràng buộc việc sửa dữ liệu qua pointer theo hợp đồng C. Charset, kết thúc chuỗi, size, nullability và ownership cần tài liệu C định nghĩa riêng.

**7. Dùng jextract có xóa được trách nhiệm quản lý memory ownership không?**

**Trả lời:** Không. Generated bindings có thể giúp biểu diễn type/layout từ header, nhưng không tự chứng minh deallocator, pointer lifetime, callback concurrency hoặc error semantics.

**8. Nếu một C API nhận uint16_t* và item_count, Java có nên truyền byteSize làm item_count không?**

**Trả lời:** Không. item_count là số phần tử uint16_t theo hợp đồng. Cần tính đúng số phần tử, kiểm tra byte count chia hết cho element size và không vượt khả năng size_t.

**9. FFM kiểm tra bounds của MemorySegment có ngăn C ghi vượt buffer được không?**

**Trả lời:** Không bảo đảm. C nhận raw address có thể truy cập ngoài vùng cấp phát nếu caller truyền capacity sai hoặc native code có bug. Cần hợp đồng, validation và native diagnostics.

**10. Trong demo, vì sao C xuất hàm record_count_offset thay vì Java mặc định offset bằng 4?**

**Trả lời:** Vì layout C do compiler/ABI/packing quyết định. Probe từ **binary C thực** cho Java một giá trị có thể kiểm chứng thay vì suy đoán.

## Tài liệu chính thức

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454).
- [Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Java SE 22 — Linker: ABI, canonicalLayouts, FunctionDescriptor và safety considerations](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Java SE 22 — MemorySegment: bounds, alignment, zero-length pointers, reinterpret](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Java SE 22 — Arena: scope và lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java SE 22 — SymbolLookup và native library loading](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [JDK 24 Restricted Methods — Native access permissions](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html).

**Kết luận:** **FFM tự thực thi phần cầu nối mà ABI và layout khai báo cho phép; nó không tự biết toàn bộ ABI cụ thể của một binary, tính đúng của descriptor, kích thước pointer, ownership, deallocator, lifetime, encoding, callback hay error contract.** Để dùng FFM bền vững, cần phối hợp **header đúng version + ABI/probe từ C binary + Java layout/descriptor đúng + ownership/lifetime có kiểm chứng + test trên nền tảng thực**. Khi thiếu thông tin, hãy bổ sung C adapter/hàm probe thay vì đoán.
