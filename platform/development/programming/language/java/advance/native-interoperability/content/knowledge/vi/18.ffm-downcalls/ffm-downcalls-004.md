# Mô tả chữ ký C bằng FunctionDescriptor.of hoặc ofVoid trong Java FFM

## 1. Vấn đề cần giải: Java hiểu một hàm C có những đối số nào?

Trong **Foreign Function & Memory API (FFM)**, mã Java có thể gọi trực tiếp native function của một thư viện C qua `Linker` và `MethodHandle`. Để tạo handle, chương trình Java cần mô tả **đúng chữ ký C ở cấp ABI**: hàm nhận bao nhiêu đối số, kiểu dữ liệu/độ rộng/căn chỉnh nào và trả về gì. Lớp đảm nhận việc này là **`java.lang.foreign.FunctionDescriptor`**.

Hai factory quan trọng nhất:

~~~java
// Java 22+; đây là trích đoạn API, không phải chương trình độc lập.
FunctionDescriptor.of(returnLayout, argumentLayouts...);
FunctionDescriptor.ofVoid(argumentLayouts...);
~~~

- **`FunctionDescriptor.of(returnLayout, argLayouts...)`**: dùng cho hàm C **có giá trị trả về**. Layout đầu tiên là **kiểu kết quả C**, các layout sau là **tham số C theo đúng thứ tự**.
- **`FunctionDescriptor.ofVoid(argLayouts...)`**: dùng cho hàm C có **return type là `void`**. Chỉ truyền layouts của các tham số; **không có return layout**.
- Cả hai đều chấp nhận **0 tham số**. Một hàm C `int forty_two(void)` được mô tả bằng `FunctionDescriptor.of(ValueLayout.JAVA_INT)`; `void reset(void)` bằng `FunctionDescriptor.ofVoid()`.
- `FunctionDescriptor` **chỉ là mô tả chữ ký**, không tìm symbol, không gọi native function, không cấp phát vùng nhớ và **không tự kiểm chứng C header**.
- `Linker.downcallHandle` sử dụng descriptor để tạo `MethodHandle` gọi native function. **Descriptor sai có thể gây kết quả sai, memory corruption hoặc crash JVM**, ngay cả khi Java biên dịch không báo lỗi.

Ví dụ trên môi trường **Linux x86-64** với `int` C 32-bit:

| Chữ ký C | Java FFM descriptor | Kiểu method handle dự kiến |
| --- | --- | --- |
| `int add(int a, int b);` | `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` | `(int,int)int` |
| `void store(int *out, int value);` | `FunctionDescriptor.ofVoid(ADDRESS, JAVA_INT)` | `(MemorySegment,int)void` |
| `double mul(double x, double y);` | `FunctionDescriptor.of(JAVA_DOUBLE, JAVA_DOUBLE, JAVA_DOUBLE)` | `(double,double)double` |
| `void reset(void);` | `FunctionDescriptor.ofVoid()` | `()void` |
| `void *allocate(size_t n);` | `FunctionDescriptor.of(ADDRESS, sizeTLayout)` | Phụ thuộc carrier của `size_t` |
| `size_t strlen(const char *s);` | `FunctionDescriptor.of(sizeTLayout, ADDRESS)` | Phụ thuộc ABI của `size_t` |

`JAVA_INT`, `ADDRESS` và `JAVA_DOUBLE` trong bảng là các hằng của `ValueLayout`; có thể dùng static import cho gọn nhưng ví dụ đầy đủ sẽ viết `ValueLayout.JAVA_INT` để dễ theo dõi.

**Mục tiêu bài học:** nắm cách chọn `of`/`ofVoid`, đọc C prototype, chọn đúng `MemoryLayout` theo ABI, hiểu `toMethodType` và `invokeExact`, dùng `Linker`/`SymbolLookup` để chạy ví dụ thật với Java 22+, và tránh các lỗi đặc biệt nguy hiểm như mô tả `void*` thành `void` hoặc mô tả C pointer như giá trị C struct.

## 2. Chốt phiên bản: FFM JDK 22+ và sự khác biệt với các bản preview

Bài sử dụng API FFM **final từ JDK 22** (JEP 454):

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

FFM ở JDK 17–18 còn trong module incubator `jdk.incubator.foreign`; JDK 19–21 sử dụng `java.lang.foreign` dạng preview và có nhiều đổi tên/signature. Không đem ví dụ `FunctionDescriptor.of` của một bản preview sang bản khác mà không đối chiếu **Javadoc đúng version**.

Với JDK 22 trở lên:

- `FunctionDescriptor` và các memory layouts chính thức thuộc `java.base`; **không cần `--enable-preview`** cho chương trình chỉ tạo descriptor.
- Tạo downcall handle bằng `Linker.downcallHandle` và tự nạp native library bằng `SymbolLookup.libraryLookup` là các thao tác **restricted**: cấp native access cho module gọi chúng, ví dụ `--enable-native-access=ALL-UNNAMED` khi chạy class ở classpath.
- `FunctionDescriptor.of(...)` bản thân nó **không phải phép gọi C**. Do đó chương trình chỉ in descriptor (phần 8) không cần native library và không cần cấp quyền native.
- Chính sách báo warning/chặn thao tác restricted thay đổi qua các JDK đời sau; kiểm tra JDK và flags thực tế. Với chương trình minh họa liên kết C (phần 9), **bật native access tường minh**.

Trước khi bắt đầu:

~~~bash
java -version
javac -version
~~~

Nếu build đang dùng JDK 21 preview nhưng terminal chạy JDK 22, việc code không compile có thể do toolchain/preview flag, không phải do bản chất mô tả chữ ký C. Luôn ghi rõ **JDK target, OS, CPU architecture và ABI của C compiler**.

## 3. Cách đọc chính xác hai chữ ký factory

Trong JDK 22, phương thức có ý nghĩa:

~~~java
static FunctionDescriptor of(
        MemoryLayout resLayout,
        MemoryLayout... argLayouts);

static FunctionDescriptor ofVoid(
        MemoryLayout... argLayouts);
~~~

### 3.1. `of`: kết quả đứng đầu, không phải tham số đầu tiên của C

C:

~~~c
/* Các prototype minh họa. */
int sum(int left, int right);
double ratio(double numerator, double denominator);
char *duplicate_text(const char *source);
~~~

FFM trên Linux/x64, với mapping ABI đã được xác minh:

~~~java
// Java 22+; trích đoạn không độc lập.
FunctionDescriptor sumDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,    // C return int
        ValueLayout.JAVA_INT,    // C parameter 1: left
        ValueLayout.JAVA_INT);   // C parameter 2: right

FunctionDescriptor ratioDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_DOUBLE, // C return double
        ValueLayout.JAVA_DOUBLE, // C parameter 1
        ValueLayout.JAVA_DOUBLE);// C parameter 2

FunctionDescriptor dupDescriptor = FunctionDescriptor.of(
        ValueLayout.ADDRESS,     // C return char*
        ValueLayout.ADDRESS);    // C parameter const char*
~~~

Thứ tự `of(return, arg1, arg2, ...)` khác `FunctionDescriptor.ofVoid(arg1, arg2, ...)`. Nếu vô tình viết:

~~~java
// SAI nếu mục tiêu là int sum(int,int).
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

thì bạn đã khai báo **một** tham số C, chứ không phải hai. Đoạn Java vẫn compile và descriptor vẫn tồn tại, nhưng khi dùng nó để link vào `sum`, native call có thể truyền sai số lượng đối số.

### 3.2. `ofVoid`: kết quả C là `void`

C:

~~~c
/* Prototype minh họa. */
void reset(void);
void log_code(int code);
void store(int *destination, int value);
~~~

Java:

~~~java
// Java 22+, trích đoạn.
FunctionDescriptor resetDescriptor =
        FunctionDescriptor.ofVoid();

FunctionDescriptor logDescriptor =
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);

FunctionDescriptor storeDescriptor =
        FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS,
                ValueLayout.JAVA_INT);
~~~

Không có “`ValueLayout.JAVA_VOID`” tương ứng để truyền vào `of`. **`void` ở return** thể hiện bằng việc không có return layout; `void` trong **danh sách tham số C `f(void)`** nghĩa là **không có tham số**, nên truyền 0 argument layouts.

So sánh:

| C declaration | Ý nghĩa | Chọn factory |
| --- | --- | --- |
| `void stop(void);` | Không đối số, không kết quả | `ofVoid()` |
| `int status(void);` | Không đối số, trả int | `of(JAVA_INT)` |
| `void update(int id);` | Một đối số int, không kết quả | `ofVoid(JAVA_INT)` |
| `int update(int id);` | Một đối số int, trả int | `of(JAVA_INT, JAVA_INT)` |
| `void *create(void);` | Không đối số, trả **pointer** | `of(ADDRESS)` |
| `void consume(void *p);` | Một **pointer** đối số, không kết quả | `ofVoid(ADDRESS)` |

**Một pointer đến kiểu `void` (C `void*`) không phải một function trả `void`.** Đây là lỗi nhầm khái niệm rất dễ dẫn tới descriptor sai.

## 4. FunctionDescriptor mô tả ABI, không mô tả Java source signature

C prototype:

~~~c
int add_i32(int a, int b);
~~~

FFM descriptor:

~~~java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

Sau khi `Linker` tạo downcall handle, Java `MethodHandle` tương ứng có dạng:

~~~text
(int, int) -> int
~~~

Bạn không khai báo một Java `native int add(int,int)`; FFM làm việc với `MethodHandle` mà JVM tạo dựa trên **C calling convention**. `FunctionDescriptor` không phải `MethodType` truyền tay như một số API CLinker incubator đời cũ.

Sự khác nhau:

| Thành phần | Java type/API | Đáp ứng câu hỏi nào? |
| --- | --- | --- |
| C prototype | `int add(int,int);` | Native function mong gì theo header? |
| FFM descriptor | `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` | Return/arguments có layout ABI nào? |
| Java carrier type | `int.class`, `MemorySegment.class` | Java object/primitive nào đưa qua handle? |
| Method type | `(int,int)int` | `invokeExact` cần những Java arguments và return nào? |
| Symbol address | `MemorySegment` từ `SymbolLookup` | Function nằm ở đâu trong native library? |
| Linker handle | `MethodHandle` từ `downcallHandle` | Cơ chế thực thi downcall theo ABI nào? |

Tạo descriptor **không chứng minh** symbol có thật. Symbol lookup **không mang đủ thông tin signature** để JVM tự biết native function nhận kiểu gì. Vì vậy có thể tạo handle “hợp lệ về Java” nhưng lại trỏ tới hàm C có prototype khác: FFM sẽ không tự sửa lỗi ABI cho bạn.

### 4.1. `returnLayout()` và `argumentLayouts()`

~~~java
// Java 22+, trích đoạn.
FunctionDescriptor d = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS, ValueLayout.JAVA_INT);

boolean hasReturn = d.returnLayout().isPresent(); // false
int arguments = d.argumentLayouts().size();        // 2
~~~

- `returnLayout()` trả `Optional<MemoryLayout>`: với `ofVoid` sẽ là empty; với `of` sẽ có layout.
- `argumentLayouts()` trả danh sách chỉ đọc theo **đúng thứ tự tham số C**. Không có một “argument ẩn” tên là return trong danh sách này.
- Các descriptor không thể bị sửa bằng cách gọi `argumentLayouts().add(...)`, vì danh sách trả về là unmodifiable.
- `toMethodType()` cho phép kiểm tra các Java carrier types mà layouts quy định, rất hữu ích trước khi gọi `MethodHandle.invokeExact`.

## 5. Ánh xạ từ C type sang `MemoryLayout`

Đừng chọn một `ValueLayout` chỉ vì tên giống. C type phải được map theo **ABI của thư viện native** trên OS/architecture hiện tại. Bảng tham khảo **Linux x86-64/System V ABI**:

| C type | FFM layout thường dùng | Java carrier |
| --- | --- | --- |
| `_Bool` / `bool` | `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| `char`, `signed char`, `unsigned char` | `ValueLayout.JAVA_BYTE` | `byte` |
| `short` / `unsigned short` | `ValueLayout.JAVA_SHORT` | `short` |
| `int` / `unsigned int` | `ValueLayout.JAVA_INT` | `int` |
| `long` / `unsigned long` | `ValueLayout.JAVA_LONG` | `long` |
| `long long` / `unsigned long long` | `ValueLayout.JAVA_LONG` | `long` |
| `float` | `ValueLayout.JAVA_FLOAT` | `float` |
| `double` | `ValueLayout.JAVA_DOUBLE` | `double` |
| `size_t` | `ValueLayout.JAVA_LONG` | `long` |
| `char*`, `const char*`, `int*`, `void*`, function pointer | `ValueLayout.ADDRESS` | `MemorySegment` |
| C struct **by value** | `MemoryLayout.structLayout(...)` đúng ABI | `MemorySegment` |
| C union **by value** | `MemoryLayout.unionLayout(...)` đúng ABI | `MemorySegment` |

Không coi bảng này là portable tuyệt đối. Ví dụ trên Windows x64, C `long` thường **32 bit**, còn Linux x64 là **64 bit**. Ở hệ 32-bit, `size_t` có thể 32-bit. Chọn sai layout return làm kết quả từ thanh ghi/stack bị giải mã sai.

### 5.1. Truy vấn canonical layouts khi có linker

JDK 22 cho phép hỏi mapping kiểu C theo native ABI hiện tại:

~~~java
// Java 22+, minh họa; linker được phép dùng trên target hỗ trợ.
Linker linker = Linker.nativeLinker();

MemoryLayout cInt = linker.canonicalLayouts().get("int");
MemoryLayout cLong = linker.canonicalLayouts().get("long");
MemoryLayout cSizeT = linker.canonicalLayouts().get("size_t");
MemoryLayout cPtr = linker.canonicalLayouts().get("void*");
~~~

API trả một map các canonical C types theo ABI của linker. Với ứng dụng chạy đa nền tảng, hãy kiểm tra mapping thực thay vì giả định luôn dùng `JAVA_LONG` cho `long` hoặc `size_t`.

Đối với signed/unsigned, canonical layouts của C thường mô tả kích thước/calling convention, **không tự chuyển Java primitive thành unsigned type**. Ví dụ dùng `Integer.toUnsignedLong(intValue)` để diễn giải kết quả `unsigned int` nhưng phải biết rõ native function dùng unsigned contract.

### 5.2. `void*`/con trỏ không trở thành dữ liệu Java tự động

`ValueLayout.ADDRESS` biểu diễn **một con trỏ C ở mức ABI**, còn carrier Java là `MemorySegment`:

~~~java
// Java 22+, ví dụ descriptor, không phải native call hoàn chỉnh.
FunctionDescriptor strlen = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG,    // size_t trên Linux x64
        ValueLayout.ADDRESS);     // const char*
~~~

Truyền String Java thẳng vào `invokeExact` không được: cần buffer native tương thích (ví dụ `arena.allocateFrom("hello")`) và tuân theo encoding, NUL terminator, lifetime.

Một pointer trả về từ C có thể là `NULL`. Trong FFM hiện đại, `MemorySegment.NULL` biểu diễn native null address; **không** gọi `getString(0)`/`reinterpret` bừa bãi khi chưa kiểm tra NULL, bounds, ownership và vòng đời native allocation.

### 5.3. C array trong danh sách tham số

Trong tham số function C, một declaration như:

~~~c
void process_values(int values[], int count);
~~~

thường được điều chỉnh thành pointer type tương đương `int*`. Descriptor vì vậy là:

~~~java
// Java 22+, trích đoạn.
FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT);
~~~

Không phải `sequenceLayout(n, JAVA_INT)` như một struct-by-value, vì **tham số C nhận địa chỉ** của phần tử đầu tiên, không nhận một array object Java hay copy-by-value toàn bộ array.

Ngược lại, một **struct có trường array inline** vẫn cần khai báo `sequenceLayout(...)` khi dựng `StructLayout` cho struct ấy.

## 6. Con trỏ đến struct khác với struct truyền theo giá trị

Xét C:

~~~c
// Các declaration minh họa, không phải chương trình độc lập.
struct Point { int x; int y; };

void move_point(struct Point *p, int dx, int dy);
struct Point translate(struct Point p, int dx, int dy);
~~~

Đối với `move_point`, tham số đầu tiên là **pointer**:

~~~java
// Java 22+, chỉ mô tả signature của hàm pointer.
FunctionDescriptor pointerDescriptor = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

Đối với `translate`, tham số và return là **struct by value**, nên descriptor phải dùng `GroupLayout` (ở đây có thể dựng `StructLayout`):

~~~java
// Java 22+, trích đoạn, POINT phải được kiểm chứng C sizeof/alignof/offsetof.
var POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));

FunctionDescriptor byValue = FunctionDescriptor.of(
        POINT, POINT, ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
~~~

Điều này **không có nghĩa** có thể tùy tiện gọi bất kỳ ABI nào chỉ vì `POINT.byteSize()==8`. Với struct by value, calling convention C có thể chia fields vào thanh ghi, stack hoặc vùng sret. Linker sử dụng ABI để xử lý, nhưng **bạn phải mô tả chính xác C layout**.

Chú ý thêm: downcall trả **group layout by value** thường có thêm đối số Java `SegmentAllocator` để cấp vùng nhớ chứa kết quả. `FunctionDescriptor.toMethodType()` chỉ chuyển layouts thành carrier types; **method type thực của downcall handle có thể có tham số dẫn đầu bổ sung**. Đừng suy từ `toMethodType` ra đầy đủ arity của mọi handle khi có struct return.

### 6.1. Padding trong group layout, không phải một đối số độc lập

`MemoryLayout.paddingLayout(n)` giúp mô tả bytes đệm **bên trong** `structLayout`:

~~~java
// Java 22+; minh họa layout theo ABI giả định.
MemoryLayout RECORD = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value"));
~~~

Nhưng factory `FunctionDescriptor.of`/`ofVoid` **không chấp nhận padding layout trực tiếp** làm return hoặc argument:

~~~java
// SAI: không được dùng padding layout như một C parameter!
FunctionDescriptor wrong = FunctionDescriptor.ofVoid(
        MemoryLayout.paddingLayout(4));
~~~

JDK 22 ném `IllegalArgumentException` nếu return hoặc argument layout là padding layout. Padding có chỗ trong composite/group layout khi ABI đòi hỏi; nó không đại diện một đối số C.

### 6.2. ABI của composite type cần kiểm chứng bằng C

Với struct:

~~~c
// Header thật nên được dùng để đo, đoạn sau chỉ minh họa.
struct Packet {
    unsigned char kind;
    int count;
    double value;
};
~~~

Cần đo `sizeof(struct Packet)`, `_Alignof(struct Packet)`, `offsetof(struct Packet, count)`, `offsetof(struct Packet, value)` bằng đúng C compiler/flags của thư viện. `MemoryLayout.structLayout(...)` không tự thêm mọi padding compiler C đã chọn. Layout sai có thể khiến `Linker.downcallHandle` từ chối descriptor hoặc, nguy hiểm hơn, giao tiếp ABI sai.

## 7. `toMethodType()` và các quy tắc carrier type

`FunctionDescriptor.toMethodType()` hữu ích để kiểm tra **Java types được suy ra từ các layouts**, trước khi thực hiện native call.

| Layout | Carrier của JDK 22 |
| --- | --- |
| `ValueLayout.JAVA_INT` | `int` |
| `ValueLayout.JAVA_LONG` | `long` |
| `ValueLayout.JAVA_DOUBLE` | `double` |
| `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| `ValueLayout.ADDRESS` | `MemorySegment` |
| `GroupLayout` / `SequenceLayout` | `MemorySegment` |
| `ofVoid` không return layout | `void` |

Ví dụ:

~~~java
// Java 22+, trích đoạn.
FunctionDescriptor add = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
System.out.println(add.toMethodType());       // (int,int)int

FunctionDescriptor set = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT);
System.out.println(set.toMethodType());       // (MemorySegment,int)void
~~~

Một `MethodHandle` có `type()` là metadata Java về tham số/return. `invokeExact` yêu cầu **khớp chính xác** type, bao gồm Java primitive width, return context và số đối số. Một số lỗi thường chỉ xuất hiện khi invoke:

~~~java
// Giả sử addHandle là MethodHandle kiểu (int,int)int:
int ok = (int) addHandle.invokeExact(1, 2);     // Hợp lệ.
long bad = (long) addHandle.invokeExact(1, 2);  // WrongMethodTypeException.
~~~

`invoke` có khả năng chuyển đổi theo một số luật MethodHandle, nhưng nó **không sửa descriptor ABI sai**. Không thay `invokeExact` bằng `invoke` như cách sửa một lỗi kiểu mà chưa kiểm tra C function prototype.

### 7.1. Bound versus unbound `downcallHandle`

Trong FFM JDK 22, có thể tạo:

~~~java
// Java 22+, trích đoạn; symbol và descriptor được tạo ở nơi khác.
MethodHandle bound =
        linker.downcallHandle(symbol, descriptor);

MethodHandle unbound =
        linker.downcallHandle(descriptor);
~~~

- `bound` đã gắn địa chỉ hàm C, do đó gọi handle bằng đối số của function (cộng các đối số bổ trợ ABI đặc biệt khi có).
- `unbound` chưa gắn địa chỉ; Java method handle cần thêm đối số **`MemorySegment` địa chỉ native function**.
- Với hàm trả struct by value, linker có thể thêm `SegmentAllocator` để chứa return value; kiểm tra **`handle.type()`** thay vì giả định luôn bằng `descriptor.toMethodType()`.
- Kết quả `symbol` từ `SymbolLookup.find(...)` là một `MemorySegment` biểu diễn địa chỉ hàm, không phải một byte buffer để tự ý đọc/ghi.

Đối với các ví dụ chạy thật ở phần 9, dùng `bound` để tập trung vào cách chọn `of` và `ofVoid`; không có các đối số ABI ẩn khác vì return types là `int`, `double` hoặc `void`.

## 8. Ví dụ chạy độc lập 1 — mô tả chữ ký, không gọi C

Chương trình **`DescriptorOnly22.java`** dùng riêng API FFM để tạo descriptors, kiểm tra `returnLayout`, `argumentLayouts` và `toMethodType`. Nó chạy với **JDK 22+** mà không cần thư viện C hoặc cấp quyền restricted native access.

Tạo file:

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;

public final class DescriptorOnly22 {
    public static void main(String[] args) {

        FunctionDescriptor add = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT);

        FunctionDescriptor store = FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS,
                ValueLayout.JAVA_INT);

        FunctionDescriptor reset = FunctionDescriptor.ofVoid();

        FunctionDescriptor strlen = FunctionDescriptor.of(
                ValueLayout.JAVA_LONG,
                ValueLayout.ADDRESS);

        System.out.println(
                "add.hasReturn=" + add.returnLayout().isPresent());
        System.out.println(
                "store.hasReturn=" + store.returnLayout().isPresent());
        System.out.println(
                "add.arguments=" + add.argumentLayouts().size());
        System.out.println(
                "store.arguments=" + store.argumentLayouts().size());

        System.out.println(
                "add.type=" + add.toMethodType());
        System.out.println(
                "store.type=" + store.toMethodType());
        System.out.println(
                "reset.type=" + reset.toMethodType());
        System.out.println(
                "strlen.type=" + strlen.toMethodType());
    }
}
~~~

Chạy:

~~~bash
javac DescriptorOnly22.java
java DescriptorOnly22
~~~

Stdout chính xác:

~~~text
add.hasReturn=true
store.hasReturn=false
add.arguments=2
store.arguments=2
add.type=(int,int)int
store.type=(MemorySegment,int)void
reset.type=()void
strlen.type=(MemorySegment)long
~~~

Giải thích:

1. `add` dùng `of` nên có return layout. Layout đầu tiên không được tính vào `argumentLayouts().size()`.
2. `store` dùng `ofVoid` nên `returnLayout().isPresent()` là `false` dù có hai đối số.
3. `reset` không có tham số C và không trả giá trị.
4. `strlen` mô tả ví dụ `size_t strlen(const char*)` **trên Linux x86-64**; `JAVA_LONG` chỉ là mapping phù hợp mục tiêu được nêu, không đại diện mọi ABI.
5. Chuỗi `(MemorySegment,int)void` nghĩa là Java gọi một handle nhận `MemorySegment` cho C pointer và một `int` cho C int, không có giá trị trả về.
6. Không có `Linker.downcallHandle` trong chương trình này, do đó không có native symbol được gọi hay quyền truy cập native bị yêu cầu.

Nếu in `FunctionDescriptor.toString()`, biểu diễn textual của object có thể không phải output ổn định bạn nên kiểm tra bằng string comparison. Với bài kiểm thử, `returnLayout`, `argumentLayouts` và `toMethodType` rõ hơn.

## 9. Ví dụ chạy độc lập 2 — C library và Java FFM gọi `of` / `ofVoid` thật

Phần này là ví dụ end-to-end trên **Linux x86-64** với **C11 compiler (`cc`/GCC/Clang)** và **JDK 22+**.

Mục tiêu:

- C cung cấp `int32_t add_i32(int32_t,int32_t)` — return value; dùng `FunctionDescriptor.of`.
- C cung cấp `void store_i32(int32_t*,int32_t)` — không return; dùng `FunctionDescriptor.ofVoid`.
- C cung cấp `double multiply_f64(double,double)` — chứng minh carrier `double`.
- Java nạp `libffmdescriptors.so`, tìm symbols bằng `SymbolLookup.libraryLookup`/`find`, tạo bound downcall handles, gọi `invokeExact` và đọc kết quả từ native memory.
- Chương trình in cả kiểu của các handles để người học thấy **descriptor quyết định callsite**.

Thư mục làm việc:

~~~text
ffm-descriptor-demo/
  native_math.c
  FfmDescriptorsDemo.java
~~~

### 9.1. Mã C: `native_math.c`

~~~c
#include <stdint.h>

/* Trên Linux x86-64, int32_t dùng ABI của int 32-bit. */
int32_t add_i32(int32_t left, int32_t right) {
    return left + right;
}

/* C trả void: hiệu ứng quan sát được là ghi vào vùng con trỏ. */
void store_i32(int32_t *destination, int32_t value) {
    if (destination != 0) {
        *destination = value;
    }
}

double multiply_f64(double left, double right) {
    return left * right;
}
~~~

Đoạn C dùng hai đối số `int32_t` đều nằm trong range nhỏ, nên phép cộng trong ví dụ **không overflow signed int32_t**. `store_i32` không cấp phát, không trả về pointer và không giữ `destination` sau khi return. Java phải cấp phát một vùng nhớ hợp lệ cho một `int32_t`, giữ vùng nhớ ấy sống trong suốt native call rồi đọc dữ liệu sau khi call kết thúc.

Với thư viện thật, C API có thể quy định null không hợp lệ thay vì im lặng bỏ qua; ví dụ này dùng null check để minh họa, **không phải khuyến nghị mặc định cho mọi API**.

### 9.2. Mã Java: `FfmDescriptorsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class FfmDescriptorsDemo {
    public static void main(String[] args) throws Throwable {

        Linker linker = Linker.nativeLinker();

        FunctionDescriptor addSignature =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT);

        FunctionDescriptor storeSignature =
                FunctionDescriptor.ofVoid(
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_INT);

        FunctionDescriptor multiplySignature =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_DOUBLE,
                        ValueLayout.JAVA_DOUBLE,
                        ValueLayout.JAVA_DOUBLE);

        try (Arena arena = Arena.ofConfined()) {
            Path libraryPath =
                    Path.of("libffmdescriptors.so").toAbsolutePath();

            SymbolLookup library =
                    SymbolLookup.libraryLookup(libraryPath, arena);

            MethodHandle add = linker.downcallHandle(
                    library.find("add_i32").orElseThrow(),
                    addSignature);

            MethodHandle store = linker.downcallHandle(
                    library.find("store_i32").orElseThrow(),
                    storeSignature);

            MethodHandle multiply = linker.downcallHandle(
                    library.find("multiply_f64").orElseThrow(),
                    multiplySignature);

            System.out.println("add.type=" + add.type());
            System.out.println("store.type=" + store.type());
            System.out.println("multiply.type=" + multiply.type());

            int sum = (int) add.invokeExact(17, 25);

            MemorySegment cell = arena.allocate(
                    ValueLayout.JAVA_INT);
            store.invokeExact(cell, 91);

            int stored = cell.get(ValueLayout.JAVA_INT, 0);

            double product =
                    (double) multiply.invokeExact(1.5d, 2.0d);

            System.out.println("sum=" + sum);
            System.out.println("stored=" + stored);
            System.out.println("product=" + product);
        }
    }
}
~~~

Giải thích từng bước:

1. `Linker.nativeLinker()` lấy native linker theo ABI JVM đang chạy.
2. Ba descriptors mô tả **đúng return type và đúng thứ tự C arguments**. Không có bước truyền `MethodType` thủ công.
3. `Arena.ofConfined()` cho phép nạp thư viện/giữ symbol lookup và cấp buffer tạm trong phạm vi có thể đóng.
4. `SymbolLookup.libraryLookup(Path, arena)` là cách lấy symbols từ thư viện riêng theo đường dẫn, khác `Linker.defaultLookup()` thường dùng cho thư viện hệ thống.
5. `library.find("add_i32").orElseThrow()` trả một địa chỉ native function dạng `MemorySegment`; nếu symbol không được export thì thất bại rõ ràng.
6. `downcallHandle(symbol, descriptor)` tạo **bound handle**; mỗi handle cần đúng số và kiểu Java arguments theo descriptor.
7. `add.invokeExact(17,25)` trả `int` vì C function trả `int32_t` trên ABI được nêu. Cast `(int)` ở Java là cần thiết cho callsite `invokeExact`.
8. `store.invokeExact(cell,91)` là lệnh dạng statement có **return type `void`**. Không có giá trị C return để gán. Thay vào đó, C viết số 91 vào vùng memory `cell`.
9. `cell.get(ValueLayout.JAVA_INT,0)` đọc kết quả qua pointer output do C đã ghi.
10. `multiply.invokeExact(1.5d,2.0d)` nhận hai `double` và trả `double`; suffix `d` không bắt buộc nhưng làm kiểu rõ.
11. Hết `try`, arena đóng; không dùng lại pointer `cell` hoặc symbol của library qua lifetime được quy định.

### 9.3. Build thư viện và chạy chương trình

Trong thư mục có hai file, thực hiện:

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -o libffmdescriptors.so native_math.c

javac FfmDescriptorsDemo.java

java --enable-native-access=ALL-UNNAMED \
  FfmDescriptorsDemo
~~~

Lệnh trên không cần tạo JNI header, không gọi `javac -h` vì đây là **FFM downcall**, không có `native` method Java được JNI bind.

**Stdout dự kiến trên Linux x86-64 khi build và nạp thư viện thành công:**

~~~text
add.type=(int,int)int
store.type=(MemorySegment,int)void
multiply.type=(double,double)double
sum=42
stored=91
product=3.0
~~~

Tại sao đáng tin:

- `17 + 25 = 42` với C `int32_t`; không overflow.
- `store_i32` ghi 91 vào vùng `int32_t*` hợp lệ; Java đọc lại cùng bytes qua `JAVA_INT`.
- `1.5 × 2.0 = 3.0` trong `double`; Java `Double.toString` in `3.0` cho giá trị này.
- `MethodHandle.type()` biểu diễn Java carrier type của một **bound** native function handle; vì C returns không phải group layouts, không có thêm `SegmentAllocator` argument.
- `store.type` kết thúc bằng `void`, phù hợp `FunctionDescriptor.ofVoid`.

Nếu chương trình báo không tìm được thư viện, kiểm tra **working directory**, file `libffmdescriptors.so` có tồn tại, kiến trúc của C compiler và JVM có khớp hay không, và DLL dependencies. Nếu báo `IllegalCallerException`/cảnh báo native access, kiểm tra flag/module đúng JDK, **đừng đổi descriptor** chỉ để né lỗi quyền.

## 10. Vì sao `ofVoid` không phải “không làm gì”?

Hàm C trả `void` vẫn có thể:

- Ghi vào con trỏ output: `void store_i32(int32_t *dest, int32_t value)`.
- Thay đổi trạng thái native context: `void reset(Context*)`.
- Gửi dữ liệu đến thiết bị, file hoặc network.
- Nhận callback pointer và đăng ký một tác vụ dài hạn.
- Tạo side effect không nhìn thấy qua return value.

FFM descriptor chỉ diễn tả **giá trị trả về theo ABI**, không mô tả các side effects hay hợp đồng ownership.

Ví dụ:

~~~c
/* Chữ ký C minh họa. */
void copy_bytes(void *dest, const void *src, size_t count);
~~~

Java mô tả trên Linux x64:

~~~java
// Java 22+; chỉ khai báo descriptor, không phải chương trình độc lập.
FunctionDescriptor copy = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,   // dest
        ValueLayout.ADDRESS,   // src
        ValueLayout.JAVA_LONG);// size_t Linux x64
~~~

Để gọi an toàn, cần bảo đảm `dest`/`src` trỏ tới vùng nhớ còn sống, đủ `count` bytes, không vi phạm quy tắc overlap của API thật, và C function có semantics đúng. `ofVoid` không chứng minh vùng output đã đủ kích thước.

Nếu C function trả `int error_code` thay vì `void`, phải dùng `of(JAVA_INT,...)` dù **logic ứng dụng coi kết quả chỉ là mã lỗi**. Không tùy ý đổi thành `ofVoid` vì không muốn đọc return: ABI vẫn có return value thực.

## 11. Cách khai báo `void f(void)`, hàm không tham số, và return pointer

Ba trường hợp hay nhầm:

~~~c
int get_version(void);
void reset(void);
void *create_context(void);
~~~

Mô tả:

~~~java
// Java 22+, trích đoạn.
FunctionDescriptor getVersion =
        FunctionDescriptor.of(ValueLayout.JAVA_INT);

FunctionDescriptor reset =
        FunctionDescriptor.ofVoid();

FunctionDescriptor createContext =
        FunctionDescriptor.of(ValueLayout.ADDRESS);
~~~

Không tự thêm một `ValueLayout.ADDRESS` cho tham số `void` trong `f(void)`. Trong C, từ khóa `void` được dùng một mình trong prototype `f(void)` để biểu diễn **không có tham số**, không phải con trỏ.

Ngược lại:

~~~c
void dispose_context(void *context);
~~~

phải dùng `ofVoid(ValueLayout.ADDRESS)` — function có **một pointer argument** và **không return**.

### 11.1. Return pointer phải có quy tắc ownership

Nếu gọi `create_context()` nhận `MemorySegment` pointer:

- Có thể trả `MemorySegment.NULL`, phải kiểm tra.
- Một memory segment mô tả địa chỉ không tự tạo Java object sở hữu native struct.
- Nếu C cấp phát context, thường có hàm `dispose_context(context)` tương ứng. Java phải gọi đúng phương thức native khi xong, không tự dùng `Arena.close()` để giải phóng vùng do C tạo không thuộc arena.
- Không đọc trực tiếp từ zero-length address segment mà không biết bounds, lifetime và API restricted cần thiết.
- Để callback hoặc thread phụ giữ pointer sau Java invocation, cần rõ thread safety và cleanup.

**Tóm tắt:** `FunctionDescriptor.of(ADDRESS)` chỉ nói “native return là pointer”. Nó không nói vùng nhớ đủ bao nhiêu bytes hay được giải phóng như thế nào.

## 12. Kết hợp descriptor với `Linker` và `SymbolLookup`

Đường gọi hoàn chỉnh:

~~~text
C header: return_type fn(arg1_type, arg2_type);
     |
     +--> Xác định ABI, widths, pointer/struct, ownership
               |
               +--> FunctionDescriptor.of(...) / ofVoid(...)
                             |
         Native library --> SymbolLookup.find("fn")
                             |
                             +--> MemorySegment: function address
                             |
                Linker.downcallHandle(symbol, descriptor)
                             |
                     Java MethodHandle
                             |
              invokeExact(...) với carrier types đúng
                             |
                    Native C function chạy
~~~

Có thể tạo descriptor **trước** khi load native library, vì nó không phụ thuộc vào địa chỉ cụ thể của function. Bạn có thể dùng một descriptor cho nhiều symbols có **cùng signature**, miễn đúng ABI.

Ví dụ:

~~~java
// Trích đoạn Java 22+, giả sử linker và symbolA/symbolB hợp lệ.
FunctionDescriptor unaryInt = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

MethodHandle a = linker.downcallHandle(symbolA, unaryInt);
MethodHandle b = linker.downcallHandle(symbolB, unaryInt);
~~~

Nhưng **cùng số lượng tham số và return không đủ** để khẳng định hai C functions tương thích; phải xét các nguyên mẫu type/ABI thực, kể cả signedness, floating point, varargs, aggregate return và callback pointer.

### 12.1. `SymbolLookup.find` không phải kiểm tra chữ ký C

`find("name")` thường chỉ biết **tên symbol**, trả `Optional<MemorySegment>`, không biết nó là `int(int,int)` hay `void(int*)`. Một số native binaries có symbol table/debug info, nhưng FFM linker không tự suy C prototype đáng tin từ chúng.

Chữ ký phải lấy từ **header/public API của thư viện**, không tự đoán theo tên hàm. Một tên `read_value` không cho biết C return là `int`, `long`, pointer hay `void`.

### 12.2. Nạp thư viện: default, loader và library lookup

| Lookup | Nguồn symbol | Khi dùng |
| --- | --- | --- |
| `Linker.nativeLinker().defaultLookup()` | Các thư viện hệ thống phổ biến mà native linker exposes | `strlen`, `malloc` nếu symbol có trên platform |
| `SymbolLookup.loaderLookup()` | Thư viện đã được nạp qua `System.load/System.loadLibrary` gắn với caller class loader | Khi cùng class loader sở hữu JNI-loaded library |
| `SymbolLookup.libraryLookup(Path/String, Arena)` | Một thư viện cụ thể, được nạp/lookup với lifetime gắn arena | Khi ứng dụng chủ động gọi thư viện C riêng qua FFM |

Không tự giả định `defaultLookup()` luôn có symbol trong thư viện custom hoặc symbol `strlen` giống nhau trên mọi OS. Và không nhầm một **filename** như `libffmdescriptors.so` với **logical library name** truyền `System.loadLibrary`.

## 13. Descriptor và MethodHandle ở hàm trả struct: tham số bổ trợ

Với scalar return như `int` hoặc `double`, một **bound** downcall handle có `type()` phù hợp với `descriptor.toMethodType()` trong ví dụ đơn giản.

Với group return như:

~~~c
/* C declaration minh họa. */
struct Pair { int first; int second; };
struct Pair make_pair(int x, int y);
~~~

descriptor có thể là:

~~~java
// Java 22+, minh họa layout sau khi đã kiểm chứng C ABI.
MemoryLayout PAIR = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("first"),
        ValueLayout.JAVA_INT.withName("second"));

FunctionDescriptor makePair = FunctionDescriptor.of(
        PAIR, ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);
~~~

`makePair.toMethodType()` biểu thị `(int,int)MemorySegment` theo carrier rules. **Tuy nhiên**, khi `Linker` tạo downcall handle cho C function trả struct by value, handle cần **thêm `SegmentAllocator`** để biết nơi chứa kết quả. Do đó `handle.type()` có thể là một Java signature dài hơn `descriptor.toMethodType()`.

Dựa vào Java SE 22 `Linker`, không được quên parameter do linker thêm. Khi làm việc với aggregate-by-value, hãy:

1. Đo chính xác `sizeof/alignof/offsetof` của C struct với C compiler target.
2. Dựng group layout chính xác, có padding cần thiết.
3. Kiểm tra linker target hỗ trợ layout đó.
4. In `handle.type()` rồi tạo callsite `invokeExact` với đúng arguments, kể cả `SegmentAllocator`.
5. Bảo đảm vùng chứa kết quả còn sống và được dùng đúng thread/lifetime của arena.

**Không tự lấy `FunctionDescriptor.toMethodType()` làm bằng chứng đầy đủ cho những handle ABI đặc biệt**. Với unbound downcalls, còn có thêm địa chỉ hàm C.

## 14. Mô tả hàm variadic C: `of` chưa đủ nếu không có linker option

Một function như:

~~~c
int printf(const char *format, ...);
~~~

nhận một tham số cố định là format string, sau đó là số đối số biến đổi. FFM không “biết” format string sẽ dẫn tới bao nhiêu giá trị C. Bạn phải tạo descriptor cho **một callsite chuyên biệt** và đánh dấu ranh giới variadic.

Ví dụ ý tưởng (JDK 22+, Linux x64):

~~~java
// Minh họa; không phải chương trình độc lập:
// "printf(\"%d + %d\", 2, 3)" có 1 fixed và 2 variadic args.
FunctionDescriptor printfDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,     // return int
        ValueLayout.ADDRESS,      // fixed: const char* format
        ValueLayout.JAVA_INT,     // variadic: first int
        ValueLayout.JAVA_INT);    // variadic: second int

MethodHandle printf = linker.downcallHandle(
        printfSymbol,
        printfDescriptor,
        Linker.Option.firstVariadicArg(1));
~~~

`firstVariadicArg(1)` nghĩa là tham số tại **index 1 của danh sách C arguments** (zero-based) là variadic đầu tiên; `format` có index 0. Nó **không** đếm return layout.

C variadic calls áp dụng **default argument promotions**: ví dụ `float` thường được promote thành `double`, các integer types nhỏ hơn `int` có thể promote lên `int`. Native linker có thể từ chối các variadic layouts chưa được promote. Nếu mô tả nhầm varargs, native call có thể hỏng ngay cả khi các arguments Java có kiểu số đúng.

Không gọi một function C variadic đơn giản bằng descriptor của phần fixed arguments rồi kỳ vọng hệ thống tự gửi thêm varargs. `FunctionDescriptor` cần phản ánh **callsite cụ thể**, `Linker.Option` cần phản ánh **vị trí bắt đầu variadic** và ABI phải được đối chiếu.

## 15. Đổi/chèn argument layouts một cách bất biến

`FunctionDescriptor` là immutable/value-based. Ngoài hai factory chính, JDK 22 cung cấp:

| Phương thức | Tác dụng |
| --- | --- |
| `appendArgumentLayouts(extra...)` | Trả descriptor mới với arguments nối thêm |
| `insertArgumentLayouts(index, extra...)` | Trả descriptor mới có arguments chèn tại index, tính từ 0 |
| `changeReturnLayout(newLayout)` | Trả descriptor mới có return layout được thay/thiết lập |
| `dropReturnLayout()` | Trả descriptor mới không có return layout |
| `argumentLayouts()` | Đọc unmodifiable list of argument layouts |
| `returnLayout()` | Đọc optional return layout |
| `toMethodType()` | Chuyển layouts thành Java method type qua carrier rules |

Ví dụ Java 22+:

~~~java
// Trích đoạn minh họa.
FunctionDescriptor unary = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, ValueLayout.JAVA_INT);

FunctionDescriptor binary =
        unary.appendArgumentLayouts(ValueLayout.JAVA_INT);

FunctionDescriptor binaryVoid =
        binary.dropReturnLayout();
~~~

Kiểm tra:

~~~text
unary.toMethodType()      -> (int)int
binary.toMethodType()     -> (int,int)int
binaryVoid.toMethodType() -> (int,int)void
~~~

`unary` không đổi sau khi gọi `appendArgumentLayouts`. `dropReturnLayout` không “chuyển” C function có return thành C function void trong native library; nó chỉ **tạo ra mô tả chữ ký khác**. Nếu dùng descriptor mới link cùng symbol cũ có prototype khác, kết quả có thể sai.

`insertArgumentLayouts` có thể ném `IllegalArgumentException` khi index không hợp lệ; mọi phương thức thêm argument đều từ chối **padding layout đứng độc lập**. Đừng dùng `changeReturnLayout`/`dropReturnLayout` như cách lách mismatch ABI.

## 16. Debug lỗi thường gặp khi mô tả FunctionDescriptor

| Triệu chứng | Lỗi thiết kế có thể gây ra | Kiểm tra/sửa |
| --- | --- | --- |
| `WrongMethodTypeException` khi `invokeExact` | Sai số lượng Java arguments, primitive type hoặc return cast | In `handle.type()` và so với callsite Java |
| `IllegalArgumentException` khi tạo descriptor | Truyền `paddingLayout` làm argument/return layout | Padding chỉ thuộc group layout, không là C argument độc lập |
| `IllegalArgumentException` khi `downcallHandle` | Layout không được linker hỗ trợ, option không hợp lệ | Đối chiếu ABI và loại layouts |
| `IllegalCallerException` / native-access warning | Module chưa cấp quyền cho restricted FFM calls | Dùng `--enable-native-access` đúng module/JDK |
| `NoSuchElementException` tại `find(...).orElseThrow()` | Symbol không được export/không ở library lookup đó | Kiểm tra tên symbol, visibility, tên thư viện và lookup |
| `UnsatisfiedLinkError` hoặc lỗi load library | File native không tìm thấy/thiếu dependency/sai kiến trúc | Kiểm tra đường dẫn, ABI, file permissions, dependencies |
| Java nhận số bất thường ở hàm trả `long` | C `long` có width khác Java long trên ABI | Sử dụng `canonicalLayouts()` theo C target |
| C hàm không có return nhưng Java đọc một giá trị | Nhầm `ofVoid` với `of` | Đọc C prototype, return `void` thì `ofVoid` |
| C hàm trả pointer nhưng descriptor `ofVoid` | Nhầm `void*` với `void` | Pointer return dùng `of(ADDRESS)` |
| C nhận pointer nhưng Java truyền primitive `int` | Dùng `JAVA_INT` thay `ADDRESS` | C `int*` yêu cầu pointer, Java `MemorySegment` hợp lệ |
| Java gọi native rồi process crash | Descriptor không khớp ABI, vùng nhớ invalid, lifetime sai | Đối chiếu header, calling convention, pointers, memory bounds |
| Dữ liệu từ C struct lệch trường | Padding, alignment, by-value/by-pointer sai | Đo `sizeof`/`alignof`/`offsetof` bằng C probe |
| Java chỉ kiểm `descriptor.toMethodType` nhưng handle type khác | Unbound symbol argument hoặc struct return allocator | In `handle.type()` thực |
| Code C varargs trả sai giá trị | Chưa khai báo specialized signature, không dùng `firstVariadicArg` | Mô tả đúng callsite và default argument promotions |
| Nhầm `System.loadLibrary` với `libraryLookup` | Hai cơ chế nạp/lookup khác nhau | Xác định class loader lookup hay library-scoped lookup |
| Code mô tả `size_t` như `int` trên Linux x64 | Return width 64-bit bị giảm | Dùng mapping canonical `size_t` và kiểm ABI |

### 16.1. Sai lầm nguy hiểm: “Java đã compile thì descriptor đúng”

Không đúng. C symbol thường không cung cấp C type metadata để `Linker` kiểm tra tự động. Chỉ biết một địa chỉ không cho phép suy luận kiểu function mà địa chỉ đó trỏ tới. Nhiều mismatches chỉ lộ ra khi function được gọi, có thể gây **memory corruption/crash** thay vì Java exception.

Ví dụ tệ:

~~~c
/* C thực tế: hai tham số, return double. */
double compute(double x, double y);
~~~

~~~java
// Sai ABI! Java code tạo descriptor vẫn compile.
FunctionDescriptor wrong = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
~~~

Nếu dùng descriptor ấy gọi `compute`, lời gọi có thể truyền argument sai registers và đọc return sai registers. **Không chạy** một thử nghiệm ABI cố ý sai trên hệ quan trọng; sửa descriptor theo C header rồi kiểm tra trên môi trường phát triển riêng.

### 16.2. `invokeExact` vs `invoke`

`MethodHandle.invokeExact` kiểm tra chữ ký tại Java callsite:

~~~java
// Giả định add là MethodHandle kiểu (int,int)int.
int value = (int) add.invokeExact(3, 4);
~~~

Nếu biến `value` đổi thành `long` hoặc truyền `3L` mà không đổi handle, `WrongMethodTypeException` có thể xảy ra. `invoke` có thể cho một số phép chuyển đổi Java method handle nhưng **không** chuyển `int*` thành vùng nhớ hợp lệ hay thay `C long` bằng type đúng của ABI.

Khi debug, in `handle.type()`, `descriptor.returnLayout()`, `descriptor.argumentLayouts()` và so với C declaration thật.

## 17. Native function callback / upcall dùng descriptor cùng quy tắc C

`FunctionDescriptor` không chỉ dành cho Java → C downcalls. Với Java callback được chuyển thành function pointer cho C, `Linker.upcallStub(targetHandle, descriptor, arena)` cũng cần một descriptor **khớp chữ ký callback C**.

Ví dụ callback C:

~~~c
/* Chỉ minh họa C type, không phải chương trình độc lập. */
typedef void (*on_value)(int value);
~~~

Mô tả Java:

~~~java
// Java 22+, trích đoạn:
FunctionDescriptor callbackSignature =
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);
~~~

Đây là callback trả `void` và nhận một `int`. Target Java `MethodHandle` cần có method type tương thích `(int)void`. Stub được cấp trong lifetime một `Arena`; không cho native code gọi function pointer sau khi arena đã đóng.

**Khác với downcall:** lỗi Java exception thoát ra ngoài upcall callback có thể gây hậu quả nghiêm trọng, tới mức JVM terminate. Callback phải xử lý lỗi phù hợp bên trong, không giả định exception Java sẽ tự chuyển thành C error code. Ngoài ra phải rõ thread attach, callback reentrancy, owner/lifetime và synchronization của native context.

Quy tắc `of`/`ofVoid` hoàn toàn giống: **trả void** dùng `ofVoid`; **trả int** dùng `of(JAVA_INT,...)`; **trả pointer** dùng `of(ADDRESS,...)`.

## 18. Quy trình chọn descriptor an toàn cho một hàm C bất kỳ

### Bước 1 — lấy nguyên mẫu C chính xác

Ví dụ:

~~~c
// Header ABI thực, ví dụ minh họa:
int32_t process(const uint8_t *bytes, size_t length, uint32_t flags);
~~~

Xác định có bao nhiêu tham số, kiểu return, pointer hay by-value aggregate, `const`, packing, varargs và calling convention. Đừng suy từ tên method hay data binding Python/C#/Java gần giống.

### Bước 2 — chọn đúng ABI và canonical types

Trên Linux x64 thường:

- `int32_t` tương ứng 32-bit `int` → `ValueLayout.JAVA_INT`.
- `const uint8_t *` là pointer → `ValueLayout.ADDRESS`.
- `size_t` thường 64-bit → `ValueLayout.JAVA_LONG`.
- `uint32_t` là 32-bit unsigned → `ValueLayout.JAVA_INT` ở mức carrier, chuyển giá trị không dấu khi cần.

Trên ABI khác, hỏi `Linker.nativeLinker().canonicalLayouts()` hoặc biên dịch C probe thay vì copy bảng Linux.

### Bước 3 — quyết định `of` hay `ofVoid`

Return `int32_t` nên dùng `of`:

~~~java
// Java 22+, mô tả cho Linux x64:
FunctionDescriptor process = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,     // C return int32_t
        ValueLayout.ADDRESS,      // const uint8_t *
        ValueLayout.JAVA_LONG,    // size_t
        ValueLayout.JAVA_INT);    // uint32_t
~~~

Nếu C header đổi thành `void process(...)`, descriptor mới phải là `ofVoid(ADDRESS,JAVA_LONG,JAVA_INT)`. Không được chuyển chỉ vì Java không quan tâm return code.

### Bước 4 — kiểm tra Java carrier/MethodHandle type

Với descriptor `process`:

~~~text
(MemorySegment,long,int)int
~~~

Nếu dùng bound downcall handle cho C function này, Java callsite phải truyền `MemorySegment` pointer còn sống, `long` length và `int` flags. Khi chỉ có heap `byte[]`, cần chuẩn bị vùng nhớ phù hợp với native pointer contract (thường native allocation) và bảo đảm memory không bị free trước khi C dùng xong.

### Bước 5 — kiểm tra lifetimes và out-parameters

Đối với pointer arguments, xác định **input/output**, `NULL` có hợp lệ không, kích thước/endianness, ownership của vùng nhớ, native code có giữ pointer sau return hay không. Với `ofVoid`, nhiều kết quả nằm trong out-parameters nên bước này đặc biệt quan trọng.

### Bước 6 — tạo linker handle và chạy test hai phía

- Thư viện được build bằng compiler/ABI nào?
- `SymbolLookup` tìm đúng symbol chưa?
- `Linker.downcallHandle` có chấp nhận layout không?
- `handle.type()` có khớp Java callsite không?
- C test gọi function với input/expected đã biết chưa?
- Java downcall trả đúng output, kể cả giá trị biên, null/zero-length và lỗi chưa?
- Có test các nền tảng/kiến trúc bạn thực sự hỗ trợ chưa?

Không bắt đầu bằng benchmark hay tối ưu `invokeExact` cho đến khi correctness và safety đã được chứng minh.

## 19. Checklist review trước khi merge

- [ ] Đã đọc **C header thực** thay vì đoán chữ ký từ symbol name?
- [ ] Đã ghi đúng **JDK target** (JDK 22+ final) và native ABI?
- [ ] Hàm có return dùng `FunctionDescriptor.of(return, args...)`?
- [ ] Hàm return `void` dùng `FunctionDescriptor.ofVoid(args...)`?
- [ ] `void f(void)` được mô tả với **0 arguments**, không phải `ADDRESS`?
- [ ] `void*` được mô tả là pointer `ADDRESS`, không nhầm với `void`?
- [ ] `of` không bị quên một argument do tính nhầm return layout là argument?
- [ ] C `char*`/`int*`/`struct T*` dùng `ADDRESS`, không dùng layout of pointee như by-value?
- [ ] C struct/union **by value** dùng group layout chính xác theo `sizeof/alignof/offsetof`?
- [ ] C `long`, `size_t`, `bool` và unsigned types được map đúng ABI?
- [ ] `ValueLayout` và `FunctionDescriptor` không dùng padding layout làm C parameter độc lập?
- [ ] `returnLayout` và `argumentLayouts` phản ánh chính xác C prototype?
- [ ] `descriptor.toMethodType()` được kiểm tra và `handle.type()` được kiểm tra nếu có linker-added params?
- [ ] `invokeExact` dùng đúng Java primitive types, arity và return context?
- [ ] Downcall `Linker`/`SymbolLookup` được cấp đúng native access?
- [ ] Native library được nạp đúng cách và symbol thực sự được export?
- [ ] C function variadic có `firstVariadicArg` đúng index và promotions đúng?
- [ ] Native buffer đủ kích thước, đúng alignment và còn sống khi C dùng?
- [ ] Out-parameters của `ofVoid` được Java cấp phát và đọc lại đúng quy định?
- [ ] C function không giữ pointer tới buffer sau khi arena close?
- [ ] Có kiểm thử input bình thường, biên, null/error code và sự khác biệt ABI trên mọi platform cam kết hỗ trợ?

## 20. Câu hỏi tự kiểm tra

1. Tham số đầu tiên của `FunctionDescriptor.of(return, args...)` là gì? Nó có được tính là một C function argument không?
2. Vì sao `void reset(void)` phải dùng `ofVoid()` chứ không dùng `ofVoid(ADDRESS)`?
3. `void *create(void)` cần `of` hay `ofVoid`, và tại sao?
4. Chữ ký C `int add(int,int)` map thành descriptor nào trên Linux x64?
5. Chữ ký C `void write(int*,int)` map thành descriptor nào, Java quan sát output bằng cách nào?
6. `ValueLayout.ADDRESS` có Java carrier type nào? Vì sao không truyền một Java `String` trực tiếp cho `char*`?
7. `FunctionDescriptor.toMethodType()` có luôn bằng `boundHandle.type()` không? Nêu một ngoại lệ.
8. Tại sao `SymbolLookup.find("function")` không chứng minh C signature tương thích descriptor?
9. Vì sao không map C `long` thành `JAVA_LONG` cho mọi OS/ABI?
10. Mô tả C struct **by value** khác pointer tới struct ra sao?
11. Mô tả `printf(const char*, ...)` cần thêm option nào ngoài specialized descriptor?
12. Vì sao `FunctionDescriptor.ofVoid` vẫn có thể tạo side effects và out-parameters?
13. Có thể chèn `MemoryLayout.paddingLayout(8)` trực tiếp làm một đối số `ofVoid` không?
14. Khi `invokeExact` báo `WrongMethodTypeException`, thao tác đầu tiên giúp debug là gì?
15. `appendArgumentLayouts` có thay đổi descriptor gốc không?
16. Nếu C function trả pointer tới native allocation mới, `Arena.close()` của caller có chắc sẽ giải phóng allocation đó không?
17. Một Java method handle callback C `void (*on_event)(int)` cần descriptor nào?
18. Có nên tin một descriptor đúng chỉ vì Java compiler và linker tạo được handle thành công không?

**Đáp án tóm tắt:** (1) return layout, không tính vào argument list; (2) C `(void)` nghĩa là không có arguments; (3) `of(ADDRESS)` vì return pointer; (4) `of(JAVA_INT,JAVA_INT,JAVA_INT)`; (5) `ofVoid(ADDRESS,JAVA_INT)`, đọc native memory mà pointer `out` trỏ tới; (6) `MemorySegment`, cần native-compatible buffer và lifetime; (7) không, unbound symbol argument hoặc allocator cho struct return; (8) symbol lookup chỉ tìm địa chỉ; (9) Windows x64 thường dùng C long 32-bit; (10) by-value dùng `StructLayout`, pointer dùng `ADDRESS`; (11) `Linker.Option.firstVariadicArg(index)`; (12) C vẫn có side effects; (13) không, ném `IllegalArgumentException`; (14) in `handle.type()` rồi so C signature/descriptor/callsite; (15) không, trả descriptor mới; (16) không, phải gọi đúng native disposer; (17) `ofVoid(JAVA_INT)`; (18) không, phải đối chiếu C header và ABI/test native.

## 21. Tài liệu chính thức

- [Oracle JDK 22 — `FunctionDescriptor`: `of`, `ofVoid`, `returnLayout`, `toMethodType`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle JDK 22 — `Linker`: native ABI, `downcallHandle`, variadic options, canonical layouts](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle JDK 22 — `SymbolLookup`: `find`, `libraryLookup`, `loaderLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Oracle JDK 22 — `ValueLayout`: primitive carriers và `ADDRESS`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle JDK 22 — `MemoryLayout`: group/sequence/padding](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle JDK 22 — `MemorySegment`: pointer, bounds, lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle JDK 22 — `Arena`: cấp phát và giải phóng bộ nhớ](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454)
- [Oracle JDK 22 — Restricted Methods và Native Access](https://docs.oracle.com/en/java/javase/22/core/restricted-methods.html)

**Kết luận:** `FunctionDescriptor.of` dành cho hàm C **có giá trị trả về**; đối số đầu tiên là return layout, tiếp theo là layouts của các C parameters. `FunctionDescriptor.ofVoid` dành cho hàm C **return `void`**, và chỉ nhận arguments. Chọn đúng factory mới là bước đầu: để FFM an toàn, còn phải **map type theo C ABI thật**, phân biệt pointer và by-value struct, kiểm tra `MethodHandle.type()`, cấp native access đúng và bảo đảm pointers/lifetime hợp lệ. Một descriptor có thể compile nhưng vẫn mô tả sai function C; hãy luôn kiểm chứng dựa trên C header và test native.
