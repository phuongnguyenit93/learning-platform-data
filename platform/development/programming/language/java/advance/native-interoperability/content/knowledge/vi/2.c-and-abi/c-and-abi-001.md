# API ở mã nguồn và ABI ở mức nhị phân khi Java tương tác với C

## 1. Hai hợp đồng khác nhau

Khi một chương trình Java dùng thư viện C, có ít nhất hai câu hỏi phải trả lời: **mã nguồn có thể sử dụng giao diện nào?** và **mã máy đã biên dịch có gọi đúng thư viện nhị phân đang được nạp hay không?** Câu hỏi thứ nhất thuộc về API; câu hỏi thứ hai thuộc về ABI.

- **API (Application Programming Interface)** là hợp đồng ở mức người viết chương trình: tên hàm/phương thức, kiểu tham số và kiểu trả về, hằng số, kiểu dữ liệu công khai, cách gọi, tiền điều kiện, hậu điều kiện, lỗi và ý nghĩa của thao tác. Với C, API thường được mô tả bằng tệp header (`.h`) và tài liệu; với Java, bằng khai báo lớp/phương thức cùng tài liệu hành vi.
- **ABI (Application Binary Interface)** là hợp đồng để các thành phần *đã biên dịch* liên kết và trao đổi dữ liệu ở mức máy: tên ký hiệu xuất ra, cách truyền tham số và nhận giá trị trả về, kích thước/căn chỉnh/bố trí dữ liệu, quy ước gọi hàm, cơ chế liên kết và nạp thư viện, cùng các quy ước riêng của hệ điều hành, kiến trúc và bộ công cụ.
- **Hợp đồng hành vi** cũng cần được xét riêng khi đánh giá khả năng nâng cấp: một thư viện có thể giữ nguyên ABI nhưng trả kết quả khác hoặc thay đổi ý nghĩa của tham số, khiến ứng dụng sai dù việc liên kết thành công.

| Câu hỏi | API ở mã nguồn | ABI ở nhị phân |
| --- | --- | --- |
| Ai trực tiếp sử dụng? | Lập trình viên và trình biên dịch khi đọc/biên dịch mã nguồn | Trình biên dịch, linker, loader, runtime và mã máy đã tạo |
| Ví dụ của hợp đồng | `int32_t sum(int32_t a, int32_t b)`; yêu cầu đầu vào; ý nghĩa kết quả | Symbol `sum`; vị trí thanh ghi/stack cho hai đối số; quy tắc trả về `int32_t` |
| Kiểm tra điển hình | Biên dịch mã khách với header/API mới; chạy thử hành vi | Chạy **binary cũ** với thư viện mới; kiểm tra symbol, layout, calling convention |
| Lỗi điển hình | Compiler báo tên/kiểu không tồn tại hoặc lời gọi sai | Không tìm thấy symbol, gọi sai chữ ký nhị phân, đọc nhầm offset, crash hoặc hỏng dữ liệu |
| Đổi nền tảng | Có thể giữ nguyên lời gọi trong mã nguồn | Có thể cần thư viện nhị phân khác cho OS/CPU/ABI mới |

**Điểm mấu chốt:** mã nguồn còn biên dịch được **không chứng minh** binary cũ vẫn chạy đúng; nạp được thư viện **không chứng minh** lời gọi có đúng ABI hoặc giữ nguyên hành vi. Khả năng tương thích nguồn, nhị phân và hành vi là ba phép kiểm tra có liên quan nhưng khác nhau.

## 2. Một khai báo C không mô tả toàn bộ ABI

Giả sử thư viện công bố header sau:

```c
/* calc.h */
#ifndef CALC_H
#define CALC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Trả về tổng của hai số có dấu 32 bit. */
int32_t add_i32(int32_t left, int32_t right);

#ifdef __cplusplus
}
#endif

#endif
```

Từ góc nhìn API, mã khách biết tên `add_i32`, hai đầu vào `int32_t`, kiểu trả về `int32_t` và ý nghĩa phép cộng. Mã C có thể viết `int32_t result = add_i32(7, 5);` nếu đã đưa header vào và liên kết thư viện thích hợp.

Từ góc nhìn ABI, còn phải thỏa thuận những điều mà chỉ nhìn vào dòng khai báo chưa thể xác định hết:

1. **Symbol và liên kết:** mã máy cần tìm được đúng tên symbol được xuất ra từ thư viện động/tĩnh. `extern "C"` khi biên dịch bằng C++ yêu cầu C language linkage, thường tránh C++ name mangling cho giao diện C; nó **không** tự bảo đảm tính tương thích của mọi kiểu, layout hay calling convention.
2. **Calling convention:** đối số nào ở thanh ghi nào, đối số nào nằm trên stack, stack được căn chỉnh và dọn dẹp ra sao, kết quả trả về ở đâu. Quy tắc thực tế tùy ABI mục tiêu.
3. **Biểu diễn dữ liệu:** số bit, căn chỉnh, signedness; với `struct` còn có thứ tự trường, padding, offset và cách truyền/nhận struct qua biên hàm. `int32_t` có độ rộng chính xác 32 bit khi kiểu này được cung cấp, nhưng không quyết định toàn bộ cách truyền tham số.
4. **Định dạng và môi trường nhị phân:** object format như ELF/PE/Mach-O, định dạng thư viện, kiến trúc CPU, độ rộng con trỏ, quy tắc loader và phiên bản các thư viện phụ thuộc.
5. **Quy tắc quản lý tài nguyên ở biên:** ai cấp phát/giải phóng, con trỏ còn hợp lệ trong bao lâu, callback chạy trên luồng nào, ai sở hữu bộ nhớ. Phần này thường được công bố như hợp đồng API nhưng việc làm sai có thể gây lỗi native nghiêm trọng.

ABI không phải một chuẩn C duy nhất áp dụng cho mọi máy. Chẳng hạn trên nhiều hệ x86-64, Linux dùng mô hình LP64 (`long` và pointer thường 64 bit), còn Windows x64 dùng LLP64 (`long` 32 bit, pointer 64 bit). Cả hai có thể chấp nhận cùng cú pháp C nhưng cần bản binary và mapping dữ liệu phù hợp với nền tảng.

## 3. Phân biệt thay đổi API và thay đổi ABI qua các tình huống

### Tình huống A — Giữ API, giữ ABI

Thư viện thay thuật toán bên trong `add_i32` nhưng vẫn xuất symbol cũ, giữ đúng chữ ký nhị phân và kết quả được cam kết. Mã nguồn khách vẫn biên dịch; binary khách cũ vẫn có thể liên kết/chạy trên cùng môi trường ABI. Việc tối ưu nội bộ, khi không làm đổi hợp đồng công khai, thường là thay đổi tương thích.

### Tình huống B — Đổi tên API và làm mất symbol cũ

Header v1 khai báo `add_i32`; v2 chỉ còn `sum_i32`. Mã nguồn cũ gọi `add_i32` không còn biên dịch với header v2; binary cũ yêu cầu symbol `add_i32` cũng không thể liên kết nếu thư viện v2 đã xóa symbol ấy. Đây là thay đổi phá vỡ cả hai lớp.

Có thể giữ tương thích nhị phân bằng cách **tiếp tục xuất hàm `add_i32` như một wrapper** gọi `sum_i32`, đồng thời công bố tên mới cho mã nguồn mới. Việc đổi tên trong header không bắt buộc phải xóa entry point của binary cũ.

### Tình huống C — Mã nguồn vẫn hợp lệ nhưng layout nhị phân đã đổi

Xét một kiểu công khai trao đổi trực tiếp giữa thư viện và mã khách:

```c
/* ABI v1 */
typedef struct {
    uint32_t id;
    uint8_t enabled;
} Record;

/* ABI v2: giữ tên hai trường nhưng đảo thứ tự */
typedef struct {
    uint8_t enabled;
    uint32_t id;
} Record;
```

Mã C sử dụng `record.id` và `record.enabled` có thể vẫn biên dịch sau khi cập nhật header. Nhưng mã máy biên dịch theo v1 đã ghi nhớ offset của từng trường; nếu nhận con trỏ tới đối tượng mang layout v2, nó sẽ đọc/ghi sai vị trí. Trên một ABI phổ biến căn chỉnh `uint32_t` theo 4 byte, v1 thường đặt `id` tại offset 0 và `enabled` tại 4; v2 thường đặt `enabled` tại 0 và `id` tại 4. **Không được giả định các offset ấy trên mọi nền tảng**: hãy xác nhận bằng `offsetof`/`sizeof` theo đúng compiler, target và flags.

```c
#include <stddef.h>
#include <stdio.h>
#include <stdint.h>

typedef struct {
    uint32_t id;
    uint8_t enabled;
} Record;

int main(void) {
    printf("id=%zu enabled=%zu size=%zu\n",
           offsetof(Record, id),
           offsetof(Record, enabled),
           sizeof(Record));
}
```

Biên dịch/chạy, ví dụ trên Linux có C11: `cc -std=c11 record.c -o record && ./record`. Chương trình **in các offset và size thực tế của môi trường đang chạy**, không có một chuỗi stdout cố định bảo đảm cho mọi ABI. Nếu đổi cấu trúc, so sánh kết quả ở hai phiên bản trên cùng target.

### Tình huống D — Linker tìm được symbol nhưng chữ ký máy không khớp

Giả sử binary cũ được biên dịch với `int32_t get_total(void)`, còn thư viện mới triển khai một hàm xuất **cùng tên** nhưng trả `int64_t`. Trong C, tên symbol thông thường không mã hóa đầy đủ kiểu tham số hay kiểu trả về. Linker vì thế có thể tìm thấy symbol, nhưng mã gọi cũ và hàm mới không còn cùng thỏa thuận về cách đọc giá trị trả về; việc gọi qua giao diện không tương thích có thể dẫn tới hành vi không xác định. Không được dùng tiêu chí “load thành công” để kết luận ABI an toàn.

Thay đổi calling convention, đổi tham số từ giá trị sang con trỏ hoặc đổi cơ chế cấp phát cũng có thể phá hợp đồng nhị phân. Tùy loại thay đổi, lỗi có thể biểu hiện ngay khi gọi hoặc chỉ lộ ra dưới tải thực tế.

### Tình huống E — ABI giữ nguyên nhưng hành vi sai

Hàm `read_data(void *buf, size_t size)` vẫn có symbol và cách gọi như cũ, nhưng phiên bản mới ngầm hiểu `size` là “số phần tử” thay vì “số byte”. Binary vẫn nạp và gọi được; dữ liệu có thể bị ghi quá vùng nhớ. Đây là **phá hợp đồng hành vi của API** dù hình dạng ABI không đổi.

Một thay đổi chỉ thêm comment, đặt lại tên tham số trong khai báo C hay thêm hàm `static inline` tiện ích vào header thường không đòi hỏi đổi ABI đã xuất của thư viện. Tuy vậy, mã đã biên dịch không tự nhận logic inline mới cho đến khi được biên dịch lại.

## 4. Ranh giới Java ↔ C: hai lớp phải khớp cùng lúc

Java chạy bytecode theo hệ kiểu của JVM; C dùng quy ước binary của nền tảng. JNI (Java Native Interface) tạo cầu nối với quy tắc cụ thể về tên native method, mapping kiểu, tham số ẩn và thời hạn sử dụng đối tượng. Java API công khai có thể trông đơn giản, nhưng thư viện C phải đúng JNI ABI.

Ví dụ tối thiểu chạy được với JDK 17 trở lên, GCC/Clang và hệ Linux.

**Tệp `demo/NativeMath.java`:**

```java
package demo;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    private NativeMath() {}

    public static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println(add(7, 5));
    }
}
```

**Sinh khai báo JNI và triển khai native** bằng cách đứng tại thư mục chứa `demo`:

```bash
javac -h . demo/NativeMath.java
```

Lệnh này tạo class file cùng header `demo_NativeMath.h` cho JNI. Trong trường hợp trên, header khai báo hàm với tên `Java_demo_NativeMath_add`, kiểu trả về `jint` và tham số `JNIEnv *`, `jclass`, `jint`, `jint`.

**Tệp `native_math.c`:**

```c
#include "demo_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_NativeMath_add(
        JNIEnv *env, jclass type, jint a, jint b) {
    (void)env;
    (void)type;
    return a + b;
}
```

**Biên dịch và chạy trên Linux** (đặt `JAVA_HOME` trỏ tới JDK đang dùng):

```bash
cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native_math.c -o libnative_math.so

java -Djava.library.path=. demo.NativeMath
```

Kết quả chuẩn trên **stdout**:

```text
12
```

Tùy phiên bản JDK và cấu hình quyền native access, có thể xuất hiện cảnh báo bổ sung trên **stderr**. Trên Windows/macOS, tên phần mở rộng thư viện, lệnh build và thư mục JNI include của hệ điều hành sẽ khác.

Ở đây cần thấy rõ ba tầng:

- **Java API:** `NativeMath.add(int, int)` trả về `int`, đồng thời caller hiểu ý nghĩa phép cộng. Bytecode mang method descriptor `(II)I` (hai `int` vào, một `int` ra).
- **JNI bridge:** tên entry point `Java_demo_NativeMath_add` (đối với phương thức không overload trong ví dụ), tham số ẩn `JNIEnv *` và `jclass` vì method là `static`, `jint` cho Java `int`; macro `JNIEXPORT`/`JNICALL` xử lý export và calling convention cần thiết.
- **Native platform ABI:** file `libnative_math.so` phải được build cho OS/CPU/ABI mà JVM thực sự chạy; thư viện phải xuất đúng symbol, gọi đúng quy tắc của target và tuân thủ các quy tắc JNI.

Nếu đổi Java `int add(int,int)` thành `long add(long,long)`, JVM descriptor đổi từ `(II)I` sang `(JJ)J` và mã native phải cập nhật tương ứng sang `jlong`. Không được giữ nguyên hàm C cũ nhận `jint` rồi giả định rằng việc có cùng tên symbol là đủ. Khi có các method `native` overload, tên JNI dài có mã hóa descriptor để phân biệt; nên luôn dùng header tạo bởi `javac -h` hoặc đăng ký chính xác bằng `RegisterNatives`.

**Phân biệt lỗi:** `NoSuchMethodError` có thể xuất hiện khi bytecode Java cũ gọi một method Java không còn đúng tên/descriptor; `UnsatisfiedLinkError` thường liên quan nạp thư viện hoặc tìm implementation native không thành công. Cả hai là tín hiệu cần điều tra, không tự xác nhận nguyên nhân cụ thể. Trường hợp signature C/JNI sai nhưng symbol vẫn tìm được có thể nguy hiểm hơn: JVM có thể crash hoặc dữ liệu bị hỏng mà không có exception Java hữu ích.

### Nếu dùng Foreign Function & Memory API (FFM)

Từ **JDK 22**, FFM API (`java.lang.foreign`) đã chính thức, cho phép gọi C function qua `Linker` và mô tả chữ ký bằng `FunctionDescriptor`. Ví dụ một chữ ký “trả `int`, nhận hai `int`” có thể được mô tả bằng fragment Java sau (chưa phải chương trình độc lập):

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
Linker linker = Linker.nativeLinker();
```

`Linker.nativeLinker()` dùng ABI của nền tảng native đang chạy; descriptor phải phản ánh **đúng** chữ ký của hàm C mà symbol trỏ tới. FFM thay cách khai báo bridge, **không xóa bỏ trách nhiệm bảo đảm ABI**: chọn sai layout, loại con trỏ, quyền truy cập hay thời hạn sống của memory segment vẫn có thể làm chương trình sai hoặc gặp lỗi nghiêm trọng. Lời gọi restricted API có quy định native access theo phiên bản JDK và cấu hình module.

## 5. Checklist khi thay phiên bản thư viện native

Đánh giá thay đổi theo **hai hướng riêng**: xây lại khách từ source và chạy khách đã biên dịch.

1. **Định nghĩa API công khai:** so sánh tên hàm, prototype, public structs/enums, hằng số, mô tả lỗi, nghĩa tham số, quy tắc ownership. Nếu hành vi thay đổi, ghi rõ đó là breaking change ngay cả khi ABI không đổi.
2. **Đối chiếu ABI trên từng target:** kiểm tra symbol xuất, tên thư viện, số/kích thước tham số, calling convention, kích thước/căn chỉnh/offset của public structs, độ rộng con trỏ, quy ước cấp phát và phụ thuộc vào runtime hệ thống.
3. **Giữ binary khách cũ để thử nâng cấp:** chạy executable/JNI wrapper đã build với phiên bản N-1 cùng thư viện N; đồng thời biên dịch lại mã nguồn với header N. Chỉ một trong hai phép thử là chưa đủ.
4. **Kiểm tra đúng thư viện được nạp:** trên Linux, `nm -D libnative_math.so` hoặc `readelf -Ws libnative_math.so` xem symbol, `ldd` xem phụ thuộc động; trên Windows thường dùng `dumpbin /exports`; phía Java dùng `javap -s demo.NativeMath` để xem descriptor. Công cụ khác nhau theo OS và định dạng binary.
5. **Test biên khó:** giá trị biên số nguyên, null pointer, struct ở cả hai phía, lifetime sau khi release, callback, nhiều luồng, xử lý lỗi và độ dài buffer. Các lỗi layout/ownership thường không lộ ở bài test “hello world”.

### Thiết kế API C để ABI bền vững hơn

- Ưu tiên **opaque handle** thay vì để khách truy cập trực tiếp layout struct nội bộ, ví dụ công bố `typedef struct Context Context;` rồi cung cấp `context_create`/`context_destroy` và các hàm thao tác. Đổi trường nội bộ không làm khách cũ phụ thuộc offset.
- Dùng kiểu độ rộng rõ ràng (`int32_t`, `uint64_t`) khi cần biểu diễn chính xác; đừng giả định `long` hay pointer có cùng size ở mọi OS. Ghi rõ endian, encoding, alignment và cách truyền buffer.
- Công bố C linkage ở biên C++ bằng `extern "C"`; tránh đưa trực tiếp C++ class, STL container, exception hoặc layout phụ thuộc compiler qua ABI dự kiến dùng đa toolchain.
- Không âm thầm đổi signature hoặc tái sử dụng symbol cũ với ý nghĩa mới. Khi breaking change là cần thiết, tạo symbol/entry point phiên bản mới và duy trì wrapper cũ trong giai đoạn chuyển tiếp nếu có thể.
- Nếu bắt buộc truyền struct công khai, cân nhắc trường `size`/`version` và vùng reserved được định nghĩa rõ; có quy tắc versioning, initialization và độ lớn buffer trước khi thêm trường. Không giả định việc thêm trường vào cuối struct luôn an toàn khi truyền struct **by value**.
- Chỉ rõ “ai tạo thì ai giải phóng”, allocator nào được dùng, pointer có còn hợp lệ sau lời gọi hay không và cách trả lỗi. Bảo đảm cùng runtime/allocator khi API yêu cầu, đặc biệt ở ranh giới module hoặc nền tảng khác nhau.

## 6. Tự kiểm tra hiểu bài

**Câu 1.** Header mới chỉ đổi tên tham số `left` thành `x`, còn prototype, symbol và hành vi vẫn giữ nguyên. Có cần build lại tất cả ứng dụng cũ? **Không vì lý do ABI này**: tên tham số C không tham gia calling convention hay symbol của hàm.

**Câu 2.** Vẫn có symbol `process` nhưng đảo thứ tự trường trong public struct truyền qua con trỏ. Mã nguồn khách mới vẫn compile. Có thể thay ngay binary thư viện mà không build lại khách? **Không thể mặc định là an toàn**: binary cũ dùng offset của layout cũ; phải duy trì layout cũ hoặc có cơ chế chuyển đổi/phiên bản phù hợp.

**Câu 3.** Một thư viện JNI load được, nhưng method Java đổi `int` thành `long`. Chỉ cần đổi tên file thư viện cho đúng là đủ? **Không**: phải đồng bộ descriptor Java, mapping kiểu (`jint`/`jlong`), native registration hoặc entry point, chữ ký C và binary triển khai.

**Câu 4.** Cùng header và cùng ABI có đồng nghĩa với ứng dụng chạy đúng? **Không**: còn cần hợp đồng hành vi, quản lý bộ nhớ, môi trường thực thi và các giả định xuyên biên Java/C.

## 7. Ghi nhớ

- **API** trả lời “mã nguồn được phép gọi gì và thao tác nghĩa là gì?”.
- **ABI** trả lời “binary đã build chuyển quyền điều khiển và trao đổi dữ liệu với binary khác theo quy ước nào?”.
- **Source compatibility ≠ binary compatibility ≠ behavioral compatibility.** Trên ranh giới Java–C, cần kiểm tra cả Java method descriptor/JNI hoặc FFM mapping **và** ABI thực của OS/CPU/compiler.
- Đối với nâng cấp thư viện, bằng chứng mạnh nhất là **build mã nguồn cũ với giao diện mới, đồng thời chạy binary cũ với thư viện mới**, rồi kiểm tra kết quả và memory safety theo hợp đồng.

### Tài liệu đối chiếu

- [GCC — Binary Compatibility](https://gcc.sourceware.org/onlinedocs/gcc/Compatibility.html): calling convention, layout, binary compatibility.
- [Oracle — JNI Design Overview](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html): mapping tên phương thức JNI và quy tắc liên kết.
- [Oracle — Foreign Function and Memory API (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): calling native functions và quản lý foreign memory.
