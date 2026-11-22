# Phương thức restricted và lý do cần cho phép truy cập bản địa tường minh

Trong Java, các API cho phép chạy mã ngoài JVM có thể **phá vỡ những bảo đảm an toàn của nền tảng Java** dù chính lời gọi xuất phát từ một file `.java` hợp lệ. Foreign Function & Memory API (FFM) từ **JDK 22** đánh dấu một số phương thức là **restricted methods**: chúng vẫn là API công khai, nhưng có thể load native library, tạo function pointer, gán sai chữ ký C ABI hoặc mở rộng một `MemorySegment` sang những byte mà JVM không thể chứng minh là hợp lệ. Nếu sử dụng sai, kết quả không chỉ là Java exception; native code có thể làm **JVM crash hoặc memory corruption âm thầm**.

Để người triển khai ứng dụng thực sự biết và **chấp thuận việc vượt ra ngoài vùng an toàn của JVM**, Java có cơ chế **native-access permission cho module**. Ví dụ chương trình chạy ở classpath cần `--enable-native-access=ALL-UNNAMED`; một module có tên `com.example.bridge` có thể được cấp riêng bằng `--enable-native-access=com.example.bridge`. Đây là **quyết định ở thời điểm chạy**, không phải chỉ một dòng import hay annotation trong source.

Từ **JDK 24**, JEP 472 mở rộng chính sách này để thống nhất các thao tác **load/bind JNI** với FFM: chương trình không được cấp quyền có thể bị cảnh báo mặc định; chế độ `--illegal-native-access=deny` làm các thao tác vi phạm ném `IllegalCallerException`. Chế độ mặc định có thể trở nên chặt hơn ở các JDK tương lai; không viết code phụ thuộc việc cảnh báo sẽ luôn là đủ.

Bài thuộc nhóm **Quyền truy cập native**, đi từ ý nghĩa “restricted”, danh mục cụ thể, sự khác biệt JDK 22–23 và 24+, cách cấp quyền cho classpath/named modules, ví dụ **Java 22+ + C11 chạy được** thực hiện `libraryLookup`, `downcallHandle`, `upcallStub` và `reinterpret`, tới chẩn đoán sai policy, vận hành và nguyên tắc bảo vệ ranh giới native.

## 1. “Restricted” nghĩa là gì và không nghĩa là gì?

Một phương thức **restricted** có thể được gọi bằng Java source hợp lệ và thường có kiểu trả về, parameter types và Javadoc chính thức. Tuy vậy, bản chất công việc của nó có thể **vượt ngoài những thứ JVM tự xác thực**. JVM yêu cầu **module chứa mã gọi** phải được cấp quyền native access nếu muốn dùng phương thức ấy mà không vi phạm chính sách.

~~~text
Java code (module M)
       |
       | gọi Linker.downcallHandle, libraryLookup,
       | reinterpret hoặc một restricted API khác
       v
JVM xét M có native access permission?
       |
       +--- CÓ ---> tiếp tục thao tác
       |             (vẫn phải tự đảm bảo ABI/bounds/ownership)
       |
       +--- KHÔNG -> "illegal native access"
                    |-- warn: cảnh báo rồi tiếp tục
                    |-- deny: IllegalCallerException
                    |-- allow: tiếp tục nhưng không cảnh báo
                    (mode availability phụ thuộc phiên bản JDK)
~~~

**Restricted không đồng nghĩa deprecated.** Ví dụ `Linker.downcallHandle` là thành phần chính thức của FFM chuẩn JDK 22, không phải một API chuẩn bị bị xóa; nó bị hạn chế vì linker **không thể chứng minh** rằng `FunctionDescriptor` bạn tự mô tả khớp đúng với mã C ở một địa chỉ native.

**Restricted không đồng nghĩa mọi FFM API đều restricted.** Bạn có thể tạo `MemoryLayout`, dùng `Arena` cấp vùng nhớ có giới hạn, thực hiện `MemorySegment.get/set` trong scope hợp lệ mà không nhất thiết cần cấp quyền native access. Khi gọi những điểm nguy hiểm như tạo downcall handle hoặc tự `reinterpret` mở rộng vùng memory, quyền native access trở thành điều kiện chính sách.

**Permission không làm mã native an toàn.** Đã có `--enable-native-access` thì JVM **cho phép** vượt qua ranh giới; nó **không xác minh** đúng ABI, kích thước buffer, lifetime, thread safety hay thư viện C có đáng tin cậy. Native code vẫn có thể crash tiến trình hoặc tác động đến dữ liệu của cùng process.

### 1.1. Ranh giới an toàn của Java và tính toàn vẹn nền tảng

Java thường thực hiện bytecode verification, array bounds checking, memory type safety, quản lý reference/lifetime và nhiều kiểm tra runtime. Native code được load vào **cùng tiến trình JVM**, có thể đọc/ghi memory thông qua con trỏ, gọi OS APIs, chạy initializer của thư viện, hoặc đưa vào thread/callback bất đồng bộ. Khi function pointer hoặc memory size sai, không có bằng chứng JVM đã ngăn được mọi hậu quả.

Vì thế chính sách yêu cầu **tường minh hóa lựa chọn “tôi chấp thuận mã này có native access”**. Nó giúp vận hành, auditing và phát hiện dependencies chưa được xem xét; không phải security sandbox để cách ly native library khỏi dữ liệu JVM. Muốn cách ly process hoặc chống binary độc hại, cần cơ chế isolation khác như process boundary, OS permissions hoặc sandbox phù hợp.

## 2. Những phương thức FFM nào bị đánh dấu restricted?

Bảng theo tài liệu Oracle JDK 22/24/25:

| API | Vì sao restricted? | Lỗi thiết kế phải tránh |
| --- | --- | --- |
| `SymbolLookup.libraryLookup(String, Arena)` và `libraryLookup(Path, Arena)` | Load thư viện native có thể kích hoạt initializer và thực thi code ngay lúc load, ví dụ hook của dynamic loader | Load file từ đường dẫn không đáng tin; không kiểm soát dependencies và ABI |
| `Linker.downcallHandle(...)` (cả dạng bind symbol lẫn dạng dùng descriptor) | Linker không biết chữ ký C thực của địa chỉ symbol, không chứng minh descriptor khớp ABI | Sai return type, số args, alignment, variadic convention |
| `Linker.upcallStub(MethodHandle, FunctionDescriptor, Arena, ...)` | Không thể xác minh function pointer callback C sẽ được gọi theo descriptor đã công bố | C lưu callback sau khi arena đóng; sai signature |
| `MemorySegment.reinterpret(long)` và các overload có `Arena`/cleanup | Tạo alias có **spatial/temporal bounds** do caller khẳng định; có thể khai sai size hoặc lifetime | Reinterpret 100 byte khi C chỉ cấp 8 byte, rồi dereference |
| `AddressLayout.withTargetLayout(MemoryLayout)` | Gắn layout vùng dữ liệu đằng sau pointer để đọc dereference theo kích thước do caller tuyên bố | Target layout lớn hơn allocation thật, pointer NULL/dangling |
| `ModuleLayer.Controller.enableNativeAccess(Module)` | Cho phép truyền quyền native-access sang module khác trong layer có điều kiện | Tạo cơ chế cấp quyền bừa bãi, không xác minh module được tin cậy |

Danh mục có thể thay đổi giữa các release. Trước khi triển khai, hãy kiểm tra **Javadoc đúng phiên bản JVM**, vì hành vi/tham số restricted đã phát triển qua quá trình incubator, preview và final hóa FFM.

### 2.1. Vì sao `libraryLookup` là một hành động nguy hiểm dù chưa gọi C function?

Trên nhiều hệ điều hành, **load một shared library tự nó có thể chạy native code**: static constructors, dynamic-loader initialization, dependency loading hoặc những hook do binary/OS cung cấp. Do đó một file `.dll/.so/.dylib` không phải dữ liệu trơ. `SymbolLookup.libraryLookup(path,arena)` có thể gây tác dụng phụ ngay khi lookup được tạo.

~~~java
// Mảnh JDK 22+: chỉ minh họa restricted load; chưa có đầy đủ imports.
SymbolLookup symbols =
        SymbolLookup.libraryLookup(pathToTrustedLibrary, arena);
~~~

Không dùng **đường dẫn do người dùng nhập tùy ý** làm file thư viện được load. Phải xác định provenance, kiến trúc, dependencies, chữ ký/phân phối đáng tin cậy và kiểm tra cách OS tìm shared libraries phụ trợ. Flag native access không phải chữ ký số xác nhận file.

### 2.2. Vì sao `downcallHandle` restricted?

Một C symbol `sum_i32` thường chỉ là **địa chỉ hàm**, không mang đủ metadata cho JVM biết prototype C thực sự là:

~~~c
#include <stdint.h>
int32_t sum_i32(int32_t a, int32_t b);
~~~

Nếu Java khai nhầm descriptor như `FunctionDescriptor.of(JAVA_LONG, ADDRESS)`, linker không thể luôn khẳng định sai từ symbol. Khi gọi handle, register/stack có thể được đọc khác ABI, dẫn tới undefined behavior. Ngay cả khi `MethodHandle.invokeExact` kiểm tra đúng **Java carrier types theo descriptor**, nó không chứng minh descriptor là hợp đồng chính xác của native function.

### 2.3. Vì sao `upcallStub` restricted?

`Linker.upcallStub` tạo C function pointer để C gọi lại Java `MethodHandle`. Nếu C cho rằng pointer có signature `int (*)(int)` nhưng Java tạo stub mô tả `double (*)(double)`, ABI bị lệch. Nếu C **lưu callback** rồi tiếp tục gọi sau khi `Arena` sở hữu stub đã đóng, native code có thể gọi vào địa chỉ hết hiệu lực.

Quyền native access cho phép tạo stub; người viết vẫn phải đảm bảo callback type, exception handling, thread model, unregister/stop và lifetime.

### 2.4. Vì sao `reinterpret`/`withTargetLayout` restricted?

Một pointer C trả về thường có representation `MemorySegment` size0 vì JVM **không biết số byte bên dưới**. `reinterpret(1024)` tạo view báo “1024 byte hợp lệ”, nhưng không hề hỏi allocator C xem allocation thật có đủ hay không. Tương tự, `ADDRESS.withTargetLayout(sequenceLayout(256,JAVA_INT))` khai thác giả thiết pointer trỏ tới 256 integers; nếu sai thì có thể dereference ra ngoài vùng nhớ.

Các API này nằm trong public JDK, nhưng rủi ro nằm ở **sự xác nhận do caller tự đặt về C memory**. Chỉ dùng khi có contract kích thước, ownership, alignment, nullability và lifetime đáng tin.

## 3. Phân biệt restricted với các thao tác FFM bình thường

Bảng thực hành cho JDK 22+:

| Thao tác | Có phải restricted chỉ vì thao tác này? | Giải thích |
| --- | --- | --- |
| `MemoryLayout.structLayout(...)`, `sequenceLayout(...)` | **Không** | Tạo mô tả dữ liệu, không tự execute native code |
| `ValueLayout.JAVA_INT`, `withOrder(...)` | **Không** | Metadata về carrier, size, alignment, endianness |
| `Arena.ofConfined()` và `arena.allocate(...)` | **Không** | Cấp vùng nhớ có scope/size do Java quản lý |
| `MemorySegment.get/set(...)` trong vùng hợp lệ | **Không** | Được kiểm tra bounds/lifetime/thread phía Java |
| `FileChannel.map(..., Arena)` | **Không theo danh mục restricted FFM ở trên** | Map file vẫn có rủi ro I/O/backing-file nhưng không phải native linking |
| `Linker.nativeLinker()` | Không nằm trong danh mục restricted JDK 22 | Lấy linker metadata/ABI, chưa tạo downcall handle |
| `Linker.canonicalLayouts()` | Không | Tra cứu C ABI layouts, không tự chạy foreign function |
| `SymbolLookup.libraryLookup(...)` | **Có** | Load binary và có thể execute initialization code |
| `Linker.downcallHandle(...)` | **Có** | Không biết C prototype thực tế |
| `Linker.upcallStub(...)` | **Có** | Tạo callback pointer vượt Java type system |
| `MemorySegment.reinterpret(...)` | **Có** | Thay đổi asserted bounds/scope |
| `AddressLayout.withTargetLayout(...)` | **Có** | Cho phép dereference pointer theo target size caller tự cam kết |

Không phải mọi lỗi `IllegalArgumentException` hay `IndexOutOfBoundsException` trong `MemorySegment.get/set` đều là lỗi **native access permission**. Cần tách **quyền gọi restricted API** khỏi **đúng sai dữ liệu/scope**. Ví dụ dùng `JAVA_INT` ở byte offset1 trên aligned segment có thể gây alignment exception dù module đã được cấp mọi quyền native.

## 4. Phiên bản JDK: điều gì thay đổi?

| Phiên bản | Trạng thái FFM | Native-access policy liên quan |
| --- | --- | --- |
| Java 17 | FFM incubator `jdk.incubator.foreign` (JEP 412) | Không dùng `java.lang.foreign` final API; native access/options theo incubator release, không suy từ JDK 22 |
| Java 19–21 | FFM preview (JEP 424/434/442) | Preview APIs/flags phụ thuộc release, không đồng nhất hoàn toàn final API |
| **Java 22–23** | FFM đã **final** từ JDK 22 (JEP 454) | Restricted FFM methods yêu cầu quyền; hành vi khi thiếu quyền khác biệt tùy có liệt kê modules qua `--enable-native-access` |
| **Java 24** | FFM final; JNI theo **JEP 472** được đưa vào cùng cơ chế | Cả **JNI load/bind** lẫn restricted FFM chịu `--enable-native-access`; có `--illegal-native-access=allow/warn/deny`, mặc định **warn** |
| Java 25 và các release sau | FFM/JNI tiếp tục chịu native-access rules; phải xem release hiện hành | Theo Oracle JDK 25, mặc định **warn**, `deny` dự kiến thành mặc định trong release tương lai, không chốt năm/version chưa được công bố |

**Chi tiết quan trọng của JDK 22–23:** Nếu chưa chỉ định bất cứ native-access grant nào, restricted FFM call có thể chạy và **cảnh báo**. Nếu đã cấp quyền cho một số modules bằng `--enable-native-access=M1,...`, một module khác chưa được liệt kê có thể nhận **`IllegalCallerException`** khi gọi restricted API. JDK 24 thay đổi hành vi để **đồng nhất** quy tắc warning/deny của JNI và FFM; vì thế không lấy kết quả cảnh báo của Java 22 rồi suy rằng Java 24 hoạt động hoàn toàn giống.

**Không nói “JNI bị xóa” hay “FFM bắt buộc thay JNI”.** JEP 472 không deprecate JNI; nó yêu cầu ứng dụng **thừa nhận rõ** quyền native khi load/link code có thể vượt giới hạn an toàn. JNI vẫn thiết yếu khi native C cần `JNIEnv`, `jobject`, Java fields/methods và class loaders.

### 4.1. Chế độ `--illegal-native-access` trên JDK 24+

| Mode | Khi module chưa được cấp native access | Mục đích |
| --- | --- | --- |
| `allow` | Cho chạy, không cảnh báo | Tương thích tạm thời; **không** phải giải pháp dài hạn |
| `warn` | Cho chạy, cảnh báo lần vi phạm đầu tiên theo module | **Mặc định JDK 24/25**, để xác định code cần cấp quyền |
| `deny` | Ném **`IllegalCallerException`** với mỗi restricted/illegal access | Kiểm toán trước khi policy mặc định chặt hơn |

`--illegal-native-access` không được dùng như flag tương đương cho những runtime cũ chưa hỗ trợ nó. Trên JDK 24/25, nên chạy ứng dụng thử với **`--illegal-native-access=deny`** để tìm ra thiếu sót; với ứng dụng sản xuất, **cấp quyền đúng cho các modules thực sự cần native**.

Khi không có native access, warning thường ghi vào **stderr**, không phải stdout do chương trình in. Số lượng/thứ tự/câu chữ warning phụ thuộc JDK và code path. Không assert **câu chữ chính xác** của warning trong unit tests; kiểm tra ý nghĩa và module bị báo.

## 5. Quyền cấp cho **module**, không cho từng C function

### 5.1. Classpath / unnamed module

Một class Java biên dịch và chạy bằng:

~~~sh
javac -d build/classes src/NativeAccessDemo.java
java -cp build/classes NativeAccessDemo
~~~

thuộc một **unnamed module** (module không có tên). Để cấp quyền restricted FFM methods cho code trên classpath:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

`ALL-UNNAMED` là tên đặc biệt áp dụng cho **mọi unnamed module**, không phải module tự đặt tên. Chế độ này thuận tiện cho demo/test nhưng mở tương đối rộng: nhiều thư viện trên classpath cùng có khả năng gọi restricted operations. Khi app lớn, nên cân nhắc đặt native binding vào **named module** riêng để grant hẹp hơn.

### 5.2. Named module và principle of least privilege

Giả sử module `com.example.nativebridge` chứa FFM calls. Run command ở Java 22+:

~~~sh
java --module-path mods \
  --enable-native-access=com.example.nativebridge \
  --module com.example.nativebridge/com.example.nativebridge.Main
~~~

Đây là **mẫu lệnh deployment**, không phải lệnh chạy trực tiếp source ở phần ví dụ (source ví dụ ở default package, classpath). Nó giả định bạn đã build một named module có `module-info.java`, main class và file ở `mods`. Không lấy command này chạy nguyên với `NativeAccessDemo.java` mặc định.

Nếu module `com.example.app` chỉ gọi Java API của `com.example.nativebridge`, nhưng **restricted calls thực sự nằm trong `com.example.nativebridge`**, nên cấp quyền cho **module bridge**, không nhất thiết cho module app. Module nào được kiểm tra phụ thuộc **caller của restricted operation**, không chỉ main class hoặc module chứa business logic.

Nếu có M1 và M2 đều cần trực tiếp dùng native, JVM flag:

~~~sh
java --enable-native-access=com.example.nativebridge,com.vendor.codec \
  --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

Danh sách module tên phân tách bằng dấu phẩy, **không** thêm khoảng trắng. Không dùng `ALL-UNNAMED` để thay cho tên named module; hai loại module khác nhau.

### 5.3. Tự kiểm tra quyền trong code

JDK 22 có:

~~~java
// Mảnh Java 22+, code nằm bên trong class
boolean enabled =
        NativeAccessDemo.class.getModule().isNativeAccessEnabled();
System.out.println("nativeAccess=" + enabled);
~~~

`Module.isNativeAccessEnabled()` là **phép hỏi** về quyền module, không tự cấp quyền. Với một demo classpath chạy cùng `--enable-native-access=ALL-UNNAMED`, giá trị in là `true`. Với module chưa được grant, nó là `false`, dù mode warn có thể vẫn tạm cho restricted operation tiếp tục. Đừng nhầm “đang được cho chạy vì warn” với “module có native access enabled”.

Một ứng dụng nghiêm ngặt có thể kiểm tra quyền và từ chối tự khởi động binding bằng error message rõ ràng trước khi load library, nhưng điều đó là **thiết kế ứng dụng**, không thay đổi hành vi thực sự của JVM `IllegalCallerException` khi mode=deny.

### 5.4. Các cách đưa grant vào deployment

Với code trên classpath, ngoài command line:

- `JDK_JAVA_OPTIONS` cho launcher nếu quy trình vận hành quản lý được môi trường.
- Java launcher argument file như `@java-args.txt` để chuẩn hóa flags.
- Manifest của **executable JAR** có attribute `Enable-Native-Access: ALL-UNNAMED`. Theo JDK docs, **không** đặt một tên named module làm value cho manifest attribute này.
- Runtime image do `jlink` tạo có thể nhúng launcher flags bằng cơ chế `--add-options` phù hợp.
- Với dynamic module layers, `ModuleLayer.Controller.enableNativeAccess(...)` là một restricted API có điều kiện, **không phải** quyền cho code thường xuyên tự nâng đặc quyền tùy ý.

Cách cấp quyền nên là **quyết định của người triển khai ứng dụng**, được review cùng binary artifacts, checksums, supply chain và permissions. Đừng để một thư viện thứ ba buộc mọi JVM trên host phải mở `ALL-UNNAMED` nếu có thể tách riêng module.

### 5.5. Điều gì **không thay thế** native-access permission?

- `--add-opens` mở reflection access đến package; không grant quyền gọi restricted FFM/native methods.
- `--add-exports` mở access đến internal/exported packages; không grant native access.
- `--enable-preview` kích hoạt preview features của đúng release; FFM **final JDK 22** không cần nó, và nó không cấp native access.
- `-Djava.library.path=...` giúp JNI tìm thư viện theo tên; không cấp quyền cho `System.loadLibrary` khi JDK 24+ kiểm tra policy.
- `System.loadLibrary("example")` tự nó không phải lời tuyên bố “tôi cho phép module này gọi native” và có thể tạo warning.
- `--illegal-native-access=allow` làm warning biến mất trong giai đoạn tương thích, nhưng không đánh dấu module đã được grant; đó là cách **bỏ qua policy**, không phải sự phân quyền hẹp.

## 6. Ví dụ chạy được: C library và Java FFM dùng bốn nhóm restricted APIs

Ta tạo thư viện C11 tên logic `nativegate` có ba exported functions:

1. `add_i32(int32_t a,int32_t b)`: trả tổng hai số nguyên; Java dùng `Linker.downcallHandle`.
2. `invoke_callback(int32_t value,int32_t(*callback)(int32_t))`: C gọi function pointer do `Linker.upcallStub` tạo và trả giá trị; ví dụ callback gọi đồng bộ.
3. `get_fixed_pair(void)`: C trả địa chỉ của `static const int32_t[2]={9,12}`. Java biết **chính xác 2×4 byte theo C contract**, nên dùng `MemorySegment.reinterpret(8,arena,null)` để đọc.

`SymbolLookup.libraryLookup(path,arena)` là restricted action khi load thư viện. Phần Java cũng in `Module.isNativeAccessEnabled()` để phân biệt chạy có grant với chạy trong mode chỉ cảnh báo. **Không có JNI entry point** vì cả ba functions là C ABI thuần.

Sơ đồ:

~~~text
native-permission-demo/
├── native/
│   └── nativegate.c
├── src/
│   └── NativeAccessDemo.java
└── build/
    ├── classes/
    └── lib/
~~~

### 6.1. C11 đầy đủ — `native/nativegate.c`

~~~c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

_Static_assert(sizeof(int32_t) == 4,
               "demo requires int32_t to be 4 bytes");

EXPORT int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}

typedef int32_t (*unary_callback)(int32_t);

EXPORT int32_t invoke_callback(
        int32_t value, unary_callback callback) {
    if (callback == NULL) {
        return 0;
    }
    /* Gọi đồng bộ và không lưu pointer để dùng sau call. */
    return callback(value);
}

EXPORT const int32_t *get_fixed_pair(void) {
    static const int32_t pair[2] = {9, 12};
    return pair;  /* Borrowed, static, read-only, không free. */
}
~~~

Contract của thư viện:

- `int32_t` có width 32 bit; `ValueLayout.JAVA_INT` có carrier Java int và size4. C compiler và JVM phải cùng target ABI; nếu port sang target khác cần xác nhận alignment/calling convention.
- `add_i32(20,22)` trả 42, không overflow ở giá trị demo.
- `invoke_callback(21,twice)` gọi callback **đúng một lần, đồng bộ**; không giữ function pointer vượt return. Java có thể đóng arena sau khi call đã hoàn tất.
- `get_fixed_pair()` trả pointer **không phải NULL**, trỏ tới ít nhất hai `int32_t` hợp lệ, **không được Java giải phóng hoặc sửa**. Pointer sống chừng nào binary library còn loaded và C static data còn valid.
- Không dùng `malloc`, không có native heap owner cần `free` trong bài. Nếu API trả malloc pointer trong thực tế, phải gọi đúng destroy/free và phối hợp lifetime với arena.

### 6.2. Java 22+ đầy đủ — `src/NativeAccessDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;

public final class NativeAccessDemo {
    private NativeAccessDemo() {
    }

    // Callback Java mà C nhận như function pointer int(*)(int).
    private static int twice(int x) {
        return x * 2;
    }

    public static void main(String[] args) throws Throwable {
        Module module = NativeAccessDemo.class.getModule();
        System.out.println("nativeAccess=" +
                module.isNativeAccessEnabled());

        Path library = Path.of("build", "lib",
                System.mapLibraryName("nativegate")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();

            // RESTRICTED #1: loading a native library.
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // int32_t add_i32(int32_t,int32_t)
            // RESTRICTED #2: downcall handle.
            MethodHandle add = linker.downcallHandle(
                    symbols.find("add_i32").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            int sum = (int) add.invokeExact(20, 22);
            System.out.println("add=" + sum);

            // C signature: int32_t invoke_callback(
            //     int32_t, int32_t (*)(int32_t))
            MethodHandle invokeCallback = linker.downcallHandle(
                    symbols.find("invoke_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle javaCallback = MethodHandles.lookup()
                    .findStatic(
                            NativeAccessDemo.class,
                            "twice",
                            MethodType.methodType(
                                    int.class, int.class));

            // RESTRICTED #3: create upcall function pointer.
            MemorySegment callback = linker.upcallStub(
                    javaCallback,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT),
                    arena);

            int callbackResult = (int)
                    invokeCallback.invokeExact(21, callback);
            System.out.println("callback=" + callbackResult);

            // C returns const int32_t pair[2] as pointer.
            MethodHandle getPair = linker.downcallHandle(
                    symbols.find("get_fixed_pair").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.ADDRESS));

            MemorySegment raw =
                    (MemorySegment) getPair.invokeExact();
            if (raw.address() == 0L) {
                throw new IllegalStateException(
                        "get_fixed_pair returned NULL");
            }
            System.out.println("rawSize=" + raw.byteSize());

            // RESTRICTED #4: reinterpret zero-length pointer.
            // Contract C guarantees exactly two int32_t values.
            long bytes = 2L * ValueLayout.JAVA_INT.byteSize();
            MemorySegment pair =
                    raw.reinterpret(bytes, arena, null);

            int first = pair.getAtIndex(ValueLayout.JAVA_INT, 0);
            int second = pair.getAtIndex(ValueLayout.JAVA_INT, 1);
            System.out.println("pair=" + first + "," + second);
        }
    }
}
~~~

Đây là **nguyên tệp Java chạy được** với JDK 22+ và native library phía trên. `NativeAccessDemo.class.getModule().isNativeAccessEnabled()` là introspection; không tự grant quyền. Khi chạy với `--enable-native-access=ALL-UNNAMED`, dòng đầu sẽ in `nativeAccess=true`.

### 6.3. Tại sao chương trình vẫn có những vùng có thể gây nguy hiểm?

- `libraryLookup` đang load một **binary native**; chỉ chọn file tin cậy và dependencies đúng target.
- `downcallHandle` dùng descriptor do Java tự chọn; đúng ở đây vì C source/prototype do ta kiểm soát. Nếu đổi prototype C mà không đổi Java descriptor, chương trình có thể hỏng.
- `upcallStub` chỉ sống trong `Arena`; C không lưu callback sau khi return. Nếu C làm việc bất đồng bộ, phải unregister callback và chờ mọi lần gọi hoàn tất **trước arena.close()**.
- `reinterpret(bytes,arena,null)` không kiểm tra C allocation thực sự là 8 byte. Ví dụ đúng vì C contract tĩnh cung cấp `int32_t[2]`; với pointer trả về từ API không rõ length, không được đoán rồi reinterpret.
- `pair` là borrowed view vào static C data, không được `free` hay mutate. Scope của `arena` giới hạn Java accesses, nhưng thư viện C phải còn loaded trong thời gian đọc.
- Java callback `twice` không ném exception và kết quả 21×2=42. Với callback production, phải có error-conversion strategy; không để Java exception lan ra C ABI tùy ý.

**Được cấp native access không đồng nghĩa được cấp quyền sửa mọi dữ liệu native.** Java có thể tự tạo một writable alias tới `const` C memory; việc viết có thể là undefined behavior hoặc OS protection fault. Luôn tuân thủ C const/ownership contract ngay cả khi không có Java-side read-only flag.

## 7. Build/run ví dụ trên Linux, macOS và Windows

Chạy từ thư mục gốc `native-permission-demo`. Cần **JDK 22 trở lên** và C compiler đúng CPU/OS ABI. Source Java dùng `java.lang.foreign` final, không cần `--enable-preview` và không dùng JNI `javac -h` vì thư viện export C ABI thường.

### 7.1. Linux, GCC hoặc Clang

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  native/nativegate.c -o build/lib/libnativegate.so

javac -d build/classes src/NativeAccessDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

### 7.2. macOS, Clang

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  native/nativegate.c -o build/lib/libnativegate.dylib

javac -d build/classes src/NativeAccessDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

### 7.3. Windows x64, MSVC Developer Command Prompt

~~~bat
mkdir build\classes
mkdir build\lib

cl /nologo /W4 /O2 /LD native\nativegate.c ^
  /link /OUT:build\lib\nativegate.dll

javac -d build\classes src\NativeAccessDemo.java

java --enable-native-access=ALL-UNNAMED ^
  -cp build\classes NativeAccessDemo
~~~

Trên Windows, dấu `^` nối dòng là cú pháp **Command Prompt**. Trên macOS Apple Silicon dùng binary arm64 cho JVM arm64; Windows x64 cần compiler cấu hình x64, không nhầm x86 DLL. `System.mapLibraryName("nativegate")` trả logical mapped filename theo OS; thư viện không nhất thiết nằm trong `java.library.path` vì `SymbolLookup.libraryLookup` được cung cấp **absolute Path**.

Nếu OS báo không tìm được dynamic dependencies, phải kiểm tra dependency search path theo platform. Thay đuôi DLL thành SO không thể sửa sai ABI.

### 7.4. Stdout chính xác ở chế độ cấp quyền đầy đủ

~~~text
nativeAccess=true
add=42
callback=42
rawSize=0
pair=9,12
~~~

Giải thích: module classpath được cấp native access nên introspection trả `true`. C `add_i32(20,22)` trả 42; Java callback `twice(21)` được C gọi một lần trả 42; raw pointer được trả qua `ValueLayout.ADDRESS` có `byteSize()==0` vì không có target layout; Java chỉ mở view 8 byte theo contract C `pair[2]={9,12}` rồi đọc đúng 2 integers.

Các dòng này là **output suy ra từ source với đúng ABI/build/runtime**; phải thực sự chạy trên JDK và OS mục tiêu mới xác minh executable end-to-end. Không in địa chỉ native hoặc log cảnh báo, vì chúng biến động theo process/JDK version.

## 8. Thí nghiệm native-access permission (đặc biệt JDK 24+)

Giả sử thư viện đã build và Java đã compile. **Không cần biên dịch lại** để chuyển giữa các policy flags.

### 8.1. Chạy có quyền (đường chuẩn)

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeAccessDemo
~~~

Dòng `nativeAccess=true` và 4 dòng còn lại như `Stdout` ở mục 7.4. Không có warning vì module thực hiện restricted operations đã được cấp quyền.

### 8.2. Chạy không cấp quyền, JDK 24/25 mặc định `warn`

~~~sh
java -cp build/classes NativeAccessDemo
~~~

Dòng đầu thường là `nativeAccess=false`. JVM có thể tiếp tục restricted operations đồng thời ghi **warning vào stderr** về lần truy cập native không hợp lệ trong unnamed module. **Không assert** thứ tự warning xen với stdout vì stdout/stderr buffering khác nhau; không copy cảnh báo một JDK cụ thể thành output cố định.

Mục đích của mode `warn` là cung cấp cơ hội nâng cấp dự án, không chứng minh binding an toàn. Đừng gửi log này vào production rồi tuyên bố chương trình đã được cho phép. Trên những JDK có chính sách chặt hơn trong tương lai, cùng lệnh có thể không chạy.

### 8.3. Chạy không cấp quyền với `deny` (JDK 24+)

~~~sh
java --illegal-native-access=deny \
  -cp build/classes NativeAccessDemo
~~~

Chương trình có thể in `nativeAccess=false` rồi ném **`IllegalCallerException` khi lần đầu gọi restricted API** (`SymbolLookup.libraryLookup`). Không dự đoán tuyệt đối stack trace line number, message hoặc Java stderr formatting. Đây là **lỗi chính sách**, không phải bằng chứng `nativegate.so/dylib/dll` thiếu symbol.

### 8.4. Cấp quyền đúng rồi kiểm tra với `deny`

~~~sh
java --enable-native-access=ALL-UNNAMED \
  --illegal-native-access=deny \
  -cp build/classes NativeAccessDemo
~~~

Trên JDK 24/25, đây là phép kiểm tra triển khai tốt: code chạy bình thường và có **đúng stdout** ở mục 7.4. Nếu một module khác trong ứng dụng cũng trực tiếp load/bind native mà **không có grant**, các operations của module đó vẫn bị `deny`; nhờ vậy bạn tìm được các dependencies cần review.

### 8.5. Với JDK 22–23 thì sao?

FFM final từ 22; `--enable-native-access=ALL-UNNAMED` là cách chạy minh bạch tương thích. Nhưng **không** copy `--illegal-native-access=deny` của JDK 24 sang launcher 22/23 rồi coi như flag luôn có sẵn. JDK 22/23 có quy tắc riêng: khi cấu hình native access cho một số modules, restricted calls từ modules khác có thể bị từ chối; khi không cấp cụ thể, runtime có thể cảnh báo. Hãy test đúng runtime thực tế, không trộn warning expectations giữa major releases.

## 9. JNI cũng cần quyền native access từ JDK 24

JEP 472 áp dụng chính sách cho **hai bước JNI** có khả năng vượt bảo đảm JVM:

1. **Load native library**, ví dụ `System.loadLibrary("legacy")`, `System.load(path)` và các overload tương ứng trên `Runtime`. Loading có thể chạy OS loader initializers và `JNI_OnLoad`.
2. **Bind/link native methods** khi JVM lần đầu liên kết phương thức `native` với function trong binary (`Java_package_Class_method` hoặc `RegisterNatives`). JNI có thể gọi Java objects/methods nhưng JVM không thể đảm bảo native function thật khớp ABI chỉ qua method declaration.

Ví dụ Java JNI **chỉ để minh họa chính sách**, chưa phải chương trình chạy độc lập:

~~~java
package demo;

public final class LegacyApi {
    static {
        System.loadLibrary("legacy");
    }

    public static native int calculate(int value);
}
~~~

Mảnh này chỉ cho thấy các điểm có thể tạo warning/deny khi module chưa được grant; để chạy phải có **native C/JNI implementation** và exported symbols tương ứng. Không dùng nó để thay thế chương trình C ABI/FMM demo ở trên.

Trên JDK 24+, nếu `LegacyApi` nằm trong một **named module** `com.example.legacyjni`, deployment có thể cấp:

~~~sh
java --enable-native-access=com.example.legacyjni \
  --illegal-native-access=deny \
  --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

Đây là **mẫu launcher** giả định named modules đã build, không chạy trực tiếp file `LegacyApi.java`. Việc JNI library được load bởi một module và `native` method được khai báo trong module khác có thể yêu cầu đánh giá **cả hai module**; đừng cấp quyền cho main module theo thói quen khi restricted operations thực tế nằm ở library/module khác.

### 9.1. JNI và FFM vẫn khác mục đích

- **JNI**: `JNIEnv`, `jobject`, Java arrays, fields, methods, Java exceptions, class loader integration, Invocation API. Cầu nối vào **JVM object model**.
- **FFM**: downcall C ABI, upcall function pointer, native memory, `MemorySegment`/`Arena`/`MemoryLayout`. Hữu ích cho thư viện C **không phụ thuộc Java objects**.
- **Điểm chung của chính sách:** cả hai có thể thực thi native code và phá tính toàn vẹn JVM nếu sử dụng sai, nên JVM cần sự chấp thuận rõ ràng từ người triển khai.
- **Không phải một lựa chọn loại trừ:** ứng dụng có thể dùng JNI cho phần native→Java objects và FFM cho C ABI thuần, cấp quyền cho đúng modules và quản lý tài nguyên riêng.

## 10. Tại sao không nên cấp quyền càng rộng càng tốt?

Giả sử một server có 50 libraries trên classpath. Khi chạy với `ALL-UNNAMED`, bất kỳ thư viện nào nằm trong unnamed modules cũng có thể trực tiếp gọi restricted FFM/JNI operations khi code path của nó được thực thi; điều đó là **lựa chọn tin cậy rộng**. Nếu một dependency bị thay thế hoặc có lỗ hổng, quyền native access có thể làm hậu quả nghiêm trọng hơn.

Tuy nhiên **named module permission cũng không sandbox** được code trong chính module đã được cấp quyền. Nó chỉ giảm bề mặt những modules được phép vượt ranh giới. Một native binary đã được load cũng đang ở **cùng OS process**, có thể có quyền file/network/process tương đương JVM host. Cần kết hợp:

- Dependency provenance, review binary, checksum/signature và kiểm soát cập nhật.
- Đúng module ownership; native binding module nhỏ, API Java typed, dữ liệu đầu vào được xác thực.
- Quản lý `Arena`, native allocation, callback registrations, worker threads và error handling.
- Build CI đa OS/architecture ABI; kiểm tra đặc biệt trên Windows với C `long` width và CRT/allocator family.
- Ngăn C function pointers tồn tại quá thư viện hoặc Arena sở hữu chúng.
- Quản lý OS permissions và process isolation cho native code không đủ tin cậy.

**FFM MemorySegment bounds checks chỉ bảo vệ Java-side accesses trong declared bounds.** Một C function gọi qua downcall có thể vẫn đọc/ghi quá buffer. Tương tự, `reinterpret` mở rộng bounds sai có thể khiến Java-side check chấp nhận thao tác không hợp lệ. Cấp quyền là **quyết định chấp nhận rủi ro**, không phải phép xác thực allocation.

## 11. Công cụ phát hiện và kiểm toán trước khi nâng JDK

### 11.1. Kết hợp warning, deny và runtime tests

Quy trình thực tế khi nâng một ứng dụng từ JDK 21 lên JDK 24+:

1. Chạy integration tests trên JDK đích với mode mặc định `warn`, thu thập **stderr** và xác định module có load/bind JNI hoặc gọi restricted FFM methods.
2. Chạy thêm với `--illegal-native-access=deny` để tìm đường code thực sự **cần quyền**; thao tác bị chặn bằng `IllegalCallerException` giúp xác định điểm thiếu grant.
3. Cấp `--enable-native-access=M1,M2,...` cho **các modules thực sự gọi restricted operations**, không vội cấp cho toàn bộ app.
4. Chạy lại với **vừa `--enable-native-access` vừa `--illegal-native-access=deny`** để xác minh không còn hidden callers chưa được cấp.
5. Test các đường lỗi và nhánh ít dùng: lazy JNI method binding có thể xảy ra khi method được gọi lần đầu, không chỉ trong application startup.
6. Xác nhận ABI and native library paths, allocator/lifetime/callbacks. Hết warning **không** có nghĩa native integration đã memory-safe.

### 11.2. `jnativescan` trên JDK 24+

JDK 24 giới thiệu công cụ `jnativescan` để **quét tĩnh Java code** tìm JNI usage có thể cần quyền, ví dụ khai báo `native` và restricted calls. Xem chính xác options bằng:

~~~sh
jnativescan --help
~~~

Với dự án có nhiều JARs/modules, dùng command line theo syntax mà **phiên bản JDK triển khai** hỗ trợ, vì options và cách thu thập module path/class path nên đối chiếu `jnativescan --help` trên máy. Không nên tự suy rằng static scan phủ mọi lời gọi reflective, generated code, dynamic loading hoặc native libraries chỉ được load ở runtime. Kết hợp static scan với integration tests.

### 11.3. JFR events và log

Trên runtime hỗ trợ, JDK Flight Recorder có các sự kiện `jdk.NativeLibraryLoad` và `jdk.NativeLibraryUnload` giúp quan sát thời điểm JVM load/dỡ native libraries. Sự kiện JFR là **diagnostics**, không phải bằng chứng C code đúng ABI hay mọi native methods được kiểm thử.

Theo dõi warning từ **stderr**, module name trong message, JDK version, launcher flags và dependency causing load. Đừng tìm lỗi bằng cách tắt warning ở mọi nơi với `--illegal-native-access=allow`; nó che mất bằng chứng cần sửa deployment.

## 12. Phân loại lỗi để không sửa sai hướng

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalCallerException` ở `libraryLookup`/`downcallHandle` | Module không có native access trong mode deny hoặc cấu hình JDK 22/23 restricted | Cấp `--enable-native-access` cho **module caller** đúng |
| Warning restricted FFM vào stderr | Native access chưa được cấp cho module | Kiểm tra module được liệt kê trong flag, không coi warning là thành công đầy đủ |
| Warning `System.loadLibrary`/native method binding trên JDK 24+ | JNI native access chưa được cấp | Cấp cho module load/bind tương ứng |
| `UnsatisfiedLinkError` khi load JNI | Không tìm được binary/dependency/symbol, sai OS/architecture | Kiểm tra path, library name, native exports, linker dependencies |
| `NoSuchElementException` khi `symbols.find(...).orElseThrow()` | Symbol C không export/tên không khớp | Dùng `nm`, `dumpbin`, kiểm tra C++ name mangling |
| `WrongMethodTypeException` khi `invokeExact` | Java carrier arity/return types không khớp MethodHandle đã tạo | Kiểm tra `FunctionDescriptor` và Java explicit casts |
| JVM crash khi gọi C | Có thể sai ABI/descriptor, pointer, lifetime, callback | Review C header, target ABI, native diagnostics/sanitizers |
| `IndexOutOfBoundsException` với `MemorySegment.get` | Java spatial bounds đã khai không đủ | Xác minh offset + layout size, không mở rộng bừa bằng reinterpret |
| `IllegalStateException` khi dùng segment | Arena scope đã đóng | Sửa ownership/lifetime, không cố gọi tiếp |
| `WrongThreadException` | Confined Arena access từ thread khác | Chọn owner thread hoặc shared arena có synchronization |
| Thư viện C load được nhưng callback crash sau close | UpcallStub address hết lifetime | Unregister/stop/join trước khi đóng Arena |
| Thêm `--add-opens` mà vẫn bị IllegalCallerException | Reflection flags không cấp native-access | Dùng `--enable-native-access`, không trộn hai cơ chế |
| Demo chạy với grant nhưng output sai | Không phải lỗi native permission | Kiểm tra C logic, ABI, format, endian, data race |
| JDK 22 chạy nhưng thêm `--illegal-native-access=deny` báo unknown option | Option quản lý JNI/FFM thống nhất từ JDK 24 | Dùng đúng flags theo JDK release |
| Mở quyền cho main module nhưng không mở cho binding module | Caller của restricted method ở module khác | Cấp tên module **định nghĩa code thực hiện thao tác** |

Không viết unit test cố tình tạo C function descriptor sai rồi kỳ vọng Java luôn ném một exception an toàn. Những failure path do native memory corruption có thể làm mất cả test JVM process; với API không tin cậy, dùng process isolation và C sanitizers.

## 13. Bốn tình huống kiến trúc

### 13.1. CLI tool chỉ tính toán với C ABI

Ứng dụng classpath sử dụng một C SDK nhỏ, nhân viên vận hành kiểm soát binary. Dùng FFM (JDK 22+) và `--enable-native-access=ALL-UNNAMED` là giải pháp đơn giản, rõ ràng. Nếu cần deploy với JDK 24/25, thêm `--illegal-native-access=deny` trong integration tests để phát hiện lời gọi native chưa được cấp ở những module khác.

### 13.2. Server nhiều dependency có native code

Nếu 50 JAR files chia sẻ classpath, `ALL-UNNAMED` cấp quyền rộng cho tất cả. Phân lớp: đưa native bridge riêng lên module path, đặt tên `com.example.nativebridge`, cấp `--enable-native-access=com.example.nativebridge` và chỉ expose Java interface an toàn cho phần còn lại. **Không** giả định Java modules trở thành sandbox; cần kiểm soát binary supply chain.

### 13.3. Plugin system có ClassLoader/ModuleLayer động

Một plugin có thể gọi JNI/FFM sau khi load, đồng thời native callbacks/global refs có thể giữ class loader sống. Đừng để plugin bất kỳ tự tăng native access; review và grant theo policy của host, biết chính xác module nào thực hiện restricted calls. Stop/unregister callbacks, free native resources, đóng Arena và release loader dependencies **trước** unload. `ModuleLayer.Controller.enableNativeAccess` là API restricted và không thay thế policy auditing.

### 13.4. Upgrading JNI framework Java 21 lên JDK 24+

Trước đây JNI `System.loadLibrary` có thể không sinh native-access warnings theo chính sách mới. Khi chạy JDK 24, library loads và native method binding có thể sinh warning dù logic nghiệp vụ không thay đổi. Không nhất thiết phải rewrite JNI sang FFM; thay vì thế xác định modules dùng JNI, thêm quyền phù hợp và kiểm thử dưới `deny`. Đọc JEP 472 và JDK migration guide đúng phiên bản để hiểu module attribution của native methods.

## 14. Bài tập và đáp án

1. **Restricted là deprecated?** Không. `Linker.downcallHandle` là API chính thức nhưng cần consent vì sai signature có thể phá memory safety.
2. **Cần grant để gọi `MemoryLayout.sequenceLayout(10,JAVA_INT)`?** Không chỉ vì thao tác ấy; tạo layout an toàn không đồng nghĩa thực thi native code.
3. **Ai kiểm tra permission?** JVM kiểm tra module của caller restricted API; không phải hệ điều hành xác thực C header.
4. **Classpath cấp quyền thế nào?** `--enable-native-access=ALL-UNNAMED`.
5. **Named module `com.acme.ffi`?** `--enable-native-access=com.acme.ffi`.
6. **`--add-opens` có tương đương native access?** Không, dùng cho reflective package access.
7. **`--enable-preview` có cần cho FFM JDK22?** Không, FFM đã final; preview và native access là hai cơ chế khác.
8. **`--illegal-native-access=deny` thuộc phase nào?** JDK 24+; runtime phản hồi `IllegalCallerException` với illegal native access.
9. **JDK 24 mode mặc định là gì?** `warn` theo JEP 472.
10. **Vì sao `libraryLookup` restricted trước khi gọi C?** Native library initializer có thể chạy ngay khi load.
11. **Vì sao `reinterpret` restricted?** Caller có thể khai quá size/lifetime, dẫn tới out-of-bounds hoặc dangling.
12. **Cấp quyền thì ABI có được JVM tự kiểm chứng?** Không. Permission không thay kiểm tra C prototype/memory lifetime.
13. **FFM upcall stub C lưu sau Arena.close sẽ ra sao?** Dangling function pointer, có thể crash/corruption.
14. **JNI `System.loadLibrary` trên JDK 24 có thể báo warning vì sao?** Load native library là restricted operation theo JEP 472 khi module không được grant.
15. **Dùng `--illegal-native-access=allow` trong production dài hạn?** Không nên; nó che warnings và không cấp quyền cụ thể cho module.
16. **App chạy với grant nhưng vẫn `UnsatisfiedLinkError`?** Là vấn đề binary/path/dependencies/symbol, không phải native-access grant.
17. **Làm sao audit dependencies?** Kết hợp warning stderr, `jnativescan`, native library load events, mode `deny` và integration tests.
18. **Tại sao module FFM bridge nên riêng?** Giảm phạm vi modules được grant theo least privilege, dù không phải sandbox.

## 15. Checklist production về native access

- [ ] **JDK:** Đã xác nhận runtime version thực, FFM final từ JDK22, JNI native access policy JDK24+?
- [ ] **Danh mục:** Đã biết code nào gọi `SymbolLookup.libraryLookup`, `Linker.downcallHandle`, `upcallStub`, `reinterpret`, `AddressLayout.withTargetLayout` hoặc chuyển quyền qua `ModuleLayer.Controller`?
- [ ] **JNI:** Trên JDK24+ đã tính cả `System/Runtime.load*` và native method linking?
- [ ] **Module:** Mã thực hiện restricted operation nằm trong module nào (named hay unnamed), đã cấp **đúng tên module caller**?
- [ ] **Least privilege:** Có thể đưa native binding vào module riêng thay vì dùng `ALL-UNNAMED` cho tất cả dependency không?
- [ ] **Flags:** Production launcher có `--enable-native-access=...`, môi trường/jlink/manifest options được quản lý nhất quán?
- [ ] **Tests:** Trên JDK24+ đã chạy CI với `--illegal-native-access=deny` và xem stderr/warnings của các nhánh lazy?
- [ ] **ABI:** FunctionDescriptor/MethodHandle khớp C header/ABI theo OS/CPU; không đoán `long`, `size_t` hoặc variadic types?
- [ ] **Memory:** `MemorySegment` có đúng size, alignment, scope, ownership; `reinterpret` chỉ sau khi xác thực C length contract?
- [ ] **Callbacks:** Upcall target/stub còn sống đủ lâu, native unregister callbacks, stop/join workers trước Arena.close?
- [ ] **Binary:** Library path/dependencies, provenance, signatures/hashes và kiến trúc JVM/compiler đã được review?
- [ ] **Errors:** Phân biệt `IllegalCallerException` vì policy với `UnsatisfiedLinkError`, `WrongMethodTypeException`, scope/bounds và OS crashes?
- [ ] **Security:** Không coi native access grant là sandbox hoặc xác nhận native library an toàn; có OS isolation nếu binary không đáng tin?
- [ ] **Maintenance:** Theo dõi JDK release notes vì `warn` dự kiến sẽ chuyển thành `deny` mặc định ở release tương lai; không phụ thuộc behavior cảnh báo vĩnh viễn.

**Kết luận:** Java đặt các điểm **có thể thực thi code hoặc diễn giải memory ngoài tầm kiểm chứng của JVM** vào nhóm restricted. `--enable-native-access` không “bật chức năng bị thiếu”; nó ghi rõ quyết định **cho phép module cụ thể vượt ranh giới an toàn**. Sự đồng thuận này nên đến từ deployment owner, được thử nghiệm bằng `deny` trên JDK24+, đi kèm C ABI chính xác, kiểm soát library binary, ownership và cleanup. Nếu JNI hoặc FFM call sai, một module đã được cấp quyền vẫn có thể làm crash cả JVM.

### Tài liệu tham khảo chính thức

- Oracle, [JDK 22 Restricted Methods](https://docs.oracle.com/en/java/javase/22/core/restricted-methods.html): danh mục FFM restricted, nguyên nhân, `--enable-native-access`.
- Oracle, [JDK 25 Restricted Methods](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html): named/unnamed grant, `Module.isNativeAccessEnabled`, `--illegal-native-access` modes.
- Oracle, [JDK 22 Linker API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): downcall/upcall và ABI risks.
- Oracle, [JDK 22 Module.isNativeAccessEnabled](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/Module.html#isNativeAccessEnabled()): Java-side permission inspection.
- Oracle, [JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): JNI load/binding, JEP 472, `jnativescan`, deployment flags và diagnostics.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454): FFM API final ở JDK22.
- OpenJDK, [JEP 472](https://openjdk.org/jeps/472): chuẩn bị hạn chế sử dụng JNI và thống nhất chính sách native access JDK24.
- Dev.java, [Troubleshoot FFM Calls — Restricted Methods](https://dev.java/learn/api/io/ffm/troubleshoot/): nguyên nhân restricted và ví dụ options.