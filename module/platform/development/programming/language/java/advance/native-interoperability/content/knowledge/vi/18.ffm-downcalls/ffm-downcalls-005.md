# Tạo downcall MethodHandle và đối chiếu MethodType thực tế trong Java FFM

## 1. Mục tiêu: biết chính xác kiểu Java cần dùng khi gọi hàm native

Với Foreign Function & Memory API (FFM), Java có thể gọi một hàm C bằng **downcall `MethodHandle`** mà không cần viết JNI wrapper cho từng hàm. Tuy nhiên, chữ ký C, `FunctionDescriptor` và `MethodType` không phải ba biểu diễn giống hệt nhau.

Ví dụ một thư viện native có hàm:

```c
int32_t add_i32(int32_t left, int32_t right);
```

Trên nền tảng mà C `int32_t` tuân theo ABI của scalar 32 bit phù hợp, Java mô tả hàm bằng:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

Sau khi tạo **downcall handle đã gắn địa chỉ hàm**, kiểu thực tế:

```text
(int,int)int
```

Nhưng một **downcall handle chưa gắn địa chỉ** lại có kiểu:

```text
(MemorySegment,int,int)int
```

Bởi vì khi gọi, trường hợp thứ hai còn cần **địa chỉ function pointer** (biểu diễn bằng `MemorySegment`) làm tham số Java đầu tiên.

Vấn đề này thường lộ ra khi dùng:

```java
MethodHandle handle = linker.downcallHandle(...);
System.out.println(handle.type());
```

và thấy chữ ký không giống tưởng tượng. Hãy **đọc `handle.type()` trước khi chọn `invokeExact` hoặc viết wrapper**, thay vì đoán rằng FFM nhận đúng các kiểu trong khai báo C theo cách đọc Java thông thường.

**Phiên bản sử dụng:** bài áp dụng API chính thức `java.lang.foreign` từ **JDK 22+** (JEP 454). Trên JDK 17, package và API tương đương không có cùng phiên bản ổn định. Ví dụ chạy bên dưới cần JDK 22+, compiler C và môi trường **Linux x86-64** để quy ước ABI/đường dẫn thư viện được xác định rõ. Không cố gắn các lệnh này với Java 17.

## 2. Bốn khái niệm cần tách riêng

### 2.1. Native function signature

Chữ ký khai báo trong C thể hiện kiểu mà **ABI native** dùng để nhận tham số và trả kết quả:

```c
double mul_f64(double a, double b);
void write_sum(int32_t *output, int32_t a, int32_t b);
```

Các kiểu C như `int`, `long`, `size_t`, `void *` hoặc `struct` có quy tắc truyền ở mức ABI phụ thuộc nền tảng, không nhất thiết tương ứng một-một với từ khóa Java cùng tên.

### 2.2. `FunctionDescriptor`: hợp đồng về layout ở biên C/Java

Một `FunctionDescriptor` liệt kê **layout của kết quả** (nếu có) và **layout của các tham số native**:

```java
// int32_t add_i32(int32_t, int32_t)
FunctionDescriptor addDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

// void write_sum(int32_t*, int32_t, int32_t)
FunctionDescriptor writeDescriptor = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

Đây là fragment, đặt trong phương thức có imports từ `java.lang.foreign`.

- `FunctionDescriptor.of(returnLayout, arguments...)`: tham số layout **đầu** là **return layout**, các layout kế tiếp là arguments.
- `FunctionDescriptor.ofVoid(arguments...)`: hàm không có giá trị trả về, tương đương C `void`. **Không** dùng `FunctionDescriptor.of(ValueLayout.JAVA_VOID, ...)` vì không có layout `JAVA_VOID` tương ứng.
- `ValueLayout.ADDRESS`: native pointer, carrier Java là `MemorySegment`, không phải `long` hoặc `String`.
- `ValueLayout.JAVA_INT`: carrier là Java `int`, không phải boxed `Integer`.
- `GroupLayout` như C `struct`: carrier Java là `MemorySegment`, nhưng **hàm trả group layout** cần một allocator bổ sung lúc gọi.

**Quan trọng:** `FunctionDescriptor` không thực thi hàm và không tự kiểm chứng C ABI của symbol được lookup. Một descriptor sai có thể tạo handle nhìn bề ngoài hợp lệ nhưng gọi vào C theo convention sai, dẫn đến **JVM crash hoặc memory corruption**.

### 2.3. `MethodType`: chữ ký Java thực tế

`java.lang.invoke.MethodType` mô tả **Java parameter classes** và **Java return class** của một `MethodHandle`.

Ví dụ:

```java
import java.lang.invoke.MethodType;

MethodType t = MethodType.methodType(
        int.class, int.class, int.class);

System.out.println(t); // (int,int)int
```

Đây là một fragment. `MethodType` không nói về C calling convention hay physical struct layout; nó nói những đối số **Java** nào cần truyền vào `MethodHandle`. Hai `MethodType` giống nhau có thể đại diện cho các native functions khác nhau về ABI nếu descriptor hoặc linker options của chúng khác nhau.

### 2.4. `Linker`: biến descriptor thành downcall handle

`Linker.nativeLinker()` dùng ABI của **nền tảng JVM hiện tại**. Có hai overload chính:

```java
// Gắn địa chỉ hàm NGAY KHI tạo handle.
MethodHandle bound = linker.downcallHandle(
        functionAddress, descriptor);

// Chưa gắn địa chỉ: truyền functionAddress khi invoke.
MethodHandle unbound = linker.downcallHandle(
        descriptor);
```

Cả hai là **restricted methods**; ứng dụng phải bật native access cho module gọi FFM, chẳng hạn chạy chương trình trên classpath bằng `--enable-native-access=ALL-UNNAMED`.

Cách thứ nhất tương đương về ngữ nghĩa liên kết với:

```java
MethodHandle unbound = linker.downcallHandle(descriptor);
MethodHandle bound = unbound.bindTo(functionAddress);
```

Khi **bind** địa chỉ, tham số `MemorySegment` đứng đầu đại diện cho function pointer không còn phải được truyền ở mỗi lần gọi.

## 3. Công thức cho MethodType thực tế

Với `FunctionDescriptor` có return `R` và native arguments `A1, A2, ..., An`, nếu tất cả là scalar/address values:

```text
descriptor.toMethodType() = (A1, A2, ..., An)R

bound downcall handle     = (A1, A2, ..., An)R

unbound downcall handle   = (MemorySegment, A1, A2, ..., An)R
                             └── target function address
```

`R` và `Ai` ở đây là **Java carrier types** của layouts, không phải tên type C. Với return `void`, `R=void`.

Ví dụ với hàm `int32_t add_i32(int32_t,int32_t)`:

| Thao tác | Kết quả dạng `MethodType.toString()` |
| --- | --- |
| `addDesc.toMethodType()` | `(int,int)int` |
| `linker.downcallHandle(address, addDesc).type()` | `(int,int)int` |
| `linker.downcallHandle(addDesc).type()` | `(MemorySegment,int,int)int` |

Nếu Java code gọi unbound handle như thể nó là bound handle, chương trình sẽ thiếu **function address** và không khớp Java MethodType.

### 3.1. `FunctionDescriptor.toMethodType()` không phải lúc nào là `handle.type()`

`FunctionDescriptor.toMethodType()` suy ra carrier types từ descriptor. Nó **không thể tự biết** bạn sẽ gọi overload bound/unbound, hoặc có thêm tham số do linker/runtime options.

Vì vậy quy trình kiểm tra đúng:

```java
System.out.println("FD carrier type: " +
        descriptor.toMethodType());
System.out.println("actual handle type: " +
        handle.type());
```

Không viết `descriptor.toMethodType().equals(handle.type())` như một quy luật tổng quát. Phép so sánh có thể đúng đối với downcall scalar **bound** không có synthetic parameters, nhưng **không đúng** cho unbound handle hoặc group-return/capture-state cases.

### 3.2. Bản đồ kiểu: từ layout sang Java carrier

| Native ABI type (ví dụ Linux/x64) | Layout FFM | Java carrier trong MethodType |
| --- | --- | --- |
| C `int` / `int32_t` trên ABI phù hợp | `ValueLayout.JAVA_INT` | `int` |
| C `short` 16-bit | `ValueLayout.JAVA_SHORT` | `short` |
| C `long long` 64-bit | `ValueLayout.JAVA_LONG` | `long` |
| C `float` | `ValueLayout.JAVA_FLOAT` | `float` |
| C `double` | `ValueLayout.JAVA_DOUBLE` | `double` |
| C `bool` khi canonical mapping hỗ trợ | `ValueLayout.JAVA_BOOLEAN` | `boolean` |
| C `char *` / `void *` | `ValueLayout.ADDRESS` | `MemorySegment` |
| C `struct Pair` (by value) | `GroupLayout`/`StructLayout` đúng ABI | `MemorySegment` |
| Native return `void` | `FunctionDescriptor.ofVoid(...)` | `void` |

**Không đồng nhất `MemorySegment` với Java `String`:** `char*` là một địa chỉ C (thường trỏ chuỗi NUL-terminated), không phải object Java. Muốn gọi C `strlen(const char*)`, phải cấp phát và mã hóa chuỗi vào vùng nhớ native trước khi truyền một `MemorySegment`.

Đối với C `unsigned int`/`size_t`, Java carrier không tự thể hiện signedness. Nếu lấy giá trị unsigned lớn, cần xử lý bit patterns hoặc chuyển sang kiểu rộng hơn theo ABI. **Đúng MethodType chưa chắc đúng semantics dữ liệu**.

## 4. Bound và unbound: cùng native function nhưng chữ ký Java khác

Giả sử `address` là kết quả của:

```java
MemorySegment address =
        symbols.find("add_i32").orElseThrow();
```

Nó đại diện **địa chỉ hàm C**, không phải Java method object. Với descriptor:

```java
FunctionDescriptor addDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

Tạo hai handle:

```java
MethodHandle bound =
        linker.downcallHandle(address, addDesc);

MethodHandle unbound =
        linker.downcallHandle(addDesc);
```

Gọi:

```java
int a = (int) bound.invokeExact(20, 22);

int b = (int) unbound.invokeExact(
        address, 20, 22);
```

Trong ngữ cảnh đã import đầy đủ, hai lời gọi đều có thể nhận `42` nếu C function thật sự có signature đúng descriptor. Điểm cần kiểm tra trong Java:

```java
MethodType expectedBound =
        MethodType.methodType(
                int.class, int.class, int.class);

MethodType expectedUnbound =
        MethodType.methodType(
                int.class,
                MemorySegment.class, int.class, int.class);

System.out.println(bound.type().equals(expectedBound));
System.out.println(unbound.type().equals(expectedUnbound));
```

Hai phép so sánh dự kiến là `true` trong trường hợp này. **Đây là fragment**, vì `linker`, `symbols` và `address` chưa được khởi tạo tại đây; chương trình hoàn chỉnh bên dưới sẽ tạo chúng.

### 4.1. Khi nào chọn mỗi loại?

**Bound handle** phù hợp khi:

- Một Java wrapper luôn gọi cùng native symbol.
- Library được load và giữ lifetime rõ ràng.
- Muốn lời gọi Java có ít tham số hơn, gần với native function.

**Unbound handle** phù hợp khi:

- Một native function signature áp dụng cho **nhiều function pointers** khác nhau.
- Function address sẽ được chọn tại thời điểm gọi (vtable, plugin resolver, dynamic dispatch).
- Cần kiểm soát symbol/lifetime theo mỗi lần sử dụng.

Nhược điểm: người dùng API dễ bỏ quên function pointer và không hiểu tham số `MemorySegment` đầu tiên là **địa chỉ hàm** chứ không phải dữ liệu `char*`/`int*` thuộc chữ ký C.

### 4.2. Hai tham số `MemorySegment` không đồng nghĩa nhau

Một C hàm:

```c
void write_sum(int32_t *out, int32_t a, int32_t b);
```

có descriptor:

```java
FunctionDescriptor writeDesc = FunctionDescriptor.ofVoid(
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

- Bound handle: `(MemorySegment,int,int)void`. `MemorySegment` đầu tiên là **out buffer pointer** do C nhận.
- Unbound handle: `(MemorySegment,MemorySegment,int,int)void`. `MemorySegment` **thứ nhất** là **địa chỉ hàm**; `MemorySegment` **thứ hai** là **out buffer pointer**.

Mặc dù Java types có thể giống nhau, **vai trò của từng tham số khác nhau**. `MethodType` chỉ biết class; source code phải đặt tên `functionAddress` và `outBuffer` rõ ràng để tránh đổi chỗ.

## 5. Ví dụ đầy đủ: biên dịch thư viện C rồi kiểm tra MethodType tại runtime

Ví dụ chính minh họa bốn kiểu chữ ký:

1. `int32_t add_i32(int32_t,int32_t)`: trả `int`.
2. `double mul_f64(double,double)`: trả `double`.
3. `void write_sum(int32_t*,int32_t,int32_t)`: return `void`, nhận native pointer.
4. `struct Pair make_pair(int32_t,int32_t)`: trả **struct by value**, khiến downcall handle có thêm `SegmentAllocator`.

Để tránh nhầm với `size_t`/`long` phụ thuộc OS, ví dụ giới hạn **Linux x86-64, C ABI System V, JDK 22+** và dùng `int32_t` rõ ràng. Chương trình có phần kiểm tra `handle.type()` bằng `MethodType` thay vì giả định đúng.

### 5.1. Cấu trúc thư mục

```text
ffm-method-types/
├── native/
│   └── ffm_types.c
├── src/
│   └── FFMMethodTypes.java
└── build/
    └── libffm_types.so          # được build từ C
```

### 5.2. Native library: `native/ffm_types.c`

```c
#include <stdint.h>

/* Trên Linux/x64, int32_t tương thích ABI của int 32 bit. */
int32_t add_i32(int32_t a, int32_t b) {
    return a + b;
}

double mul_f64(double a, double b) {
    return a * b;
}

void write_sum(int32_t *out, int32_t a, int32_t b) {
    if (out != 0) {
        *out = a + b;
    }
}

struct Pair {
    int32_t left;
    int32_t right;
};

struct Pair make_pair(int32_t left, int32_t right) {
    struct Pair result = {left, right};
    return result;
}
```

Không có Java/JNI header trong thư viện C này. FFM sẽ tìm những **exported native symbols** và gọi trực tiếp theo ABI. Hàm `write_sum` ghi kết quả vào vùng nhớ mà Java cấp phát; `make_pair` trả **struct by value**, không phải `struct Pair*`.

Mẫu cố ý chỉ cộng các số nhỏ để không gây signed overflow trong C. Với dữ liệu production, phải xác định chính sách overflow và xử lý lỗi native rõ ràng.

### 5.3. Java: `src/FFMMethodTypes.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.file.Path;

public class FFMMethodTypes {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Path library = Path.of("build", "libffm_types.so")
                .toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            // Library được load và gắn lifetime với arena.
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // C: int32_t add_i32(int32_t, int32_t)
            MemorySegment addAddress =
                    symbols.find("add_i32").orElseThrow();

            FunctionDescriptor addDesc = FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);

            MethodHandle addBound =
                    linker.downcallHandle(addAddress, addDesc);
            MethodHandle addUnbound =
                    linker.downcallHandle(addDesc);

            System.out.println(
                    "descriptor type: " + addDesc.toMethodType());
            System.out.println(
                    "bound type: " + addBound.type());
            System.out.println(
                    "unbound type: " + addUnbound.type());

            MethodType expectedBound = MethodType.methodType(
                    int.class, int.class, int.class);
            MethodType expectedUnbound = MethodType.methodType(
                    int.class,
                    MemorySegment.class, int.class, int.class);

            System.out.println(
                    "bound verified: " +
                    addBound.type().equals(expectedBound));
            System.out.println(
                    "unbound verified: " +
                    addUnbound.type().equals(expectedUnbound));

            int boundResult =
                    (int) addBound.invokeExact(20, 22);
            int unboundResult =
                    (int) addUnbound.invokeExact(
                            addAddress, 7, 8);

            System.out.println("bound result: " + boundResult);
            System.out.println("unbound result: " + unboundResult);

            // C: double mul_f64(double, double)
            FunctionDescriptor mulDesc = FunctionDescriptor.of(
                    ValueLayout.JAVA_DOUBLE,
                    ValueLayout.JAVA_DOUBLE,
                    ValueLayout.JAVA_DOUBLE);

            MethodHandle multiply = linker.downcallHandle(
                    symbols.find("mul_f64").orElseThrow(),
                    mulDesc);

            System.out.println(
                    "double type: " + multiply.type());
            double product =
                    (double) multiply.invokeExact(1.5d, 2.0d);
            System.out.println("double result: " + product);

            // C: void write_sum(int32_t*, int32_t, int32_t)
            FunctionDescriptor writeDesc =
                    FunctionDescriptor.ofVoid(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT);

            MethodHandle write = linker.downcallHandle(
                    symbols.find("write_sum").orElseThrow(),
                    writeDesc);

            System.out.println("void type: " + write.type());

            MemorySegment output =
                    arena.allocate(ValueLayout.JAVA_INT);

            // MethodHandle có return void:
            // KHÔNG cố cast kết quả sang int hoặc Object.
            write.invokeExact(output, 4, 5);
            System.out.println("out value: " +
                    output.get(ValueLayout.JAVA_INT, 0L));

            // C: struct Pair { int32_t left, right; }
            //    struct Pair make_pair(int32_t,int32_t)
            StructLayout pairLayout = MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("left"),
                    ValueLayout.JAVA_INT.withName("right"));

            FunctionDescriptor pairDesc = FunctionDescriptor.of(
                    pairLayout,
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);

            MethodHandle makePair = linker.downcallHandle(
                    symbols.find("make_pair").orElseThrow(),
                    pairDesc);

            System.out.println(
                    "pair descriptor type: " +
                    pairDesc.toMethodType());
            System.out.println(
                    "pair bound type: " + makePair.type());

            // Trả về struct by value: phải đưa SegmentAllocator
            // vào vị trí synthetic parameter của downcall handle.
            SegmentAllocator allocator = arena;
            MemorySegment pair = (MemorySegment)
                    makePair.invokeExact(allocator, 11, 12);

            System.out.println("pair values: " +
                    pair.get(ValueLayout.JAVA_INT, 0L) + "," +
                    pair.get(ValueLayout.JAVA_INT, 4L));

            // Có thể tạo đúng handle, nhưng gọi invokeExact
            // sai return type Java tại call site.
            try {
                long wrongReturn = (long)
                        addBound.invokeExact(1, 2);
                System.out.println(wrongReturn);
            } catch (WrongMethodTypeException ex) {
                System.out.println(
                        "wrong exact return: WrongMethodTypeException");
            }
        }
    }
}
```

Chương trình **không dùng `System.loadLibrary`**: `SymbolLookup.libraryLookup(Path, Arena)` chủ động load file từ đường dẫn. Bởi vậy không cần thiết lập `-Djava.library.path` cho ví dụ này nếu thư viện nằm đúng trong `build`.

Lưu ý `import java.lang.invoke.MethodHandle` và `import java.lang.invoke.MethodType` khác package `java.lang.foreign`: FFM tạo handle, còn Java `java.lang.invoke` cung cấp cơ chế kiểu và invocation.

### 5.4. Biên dịch, chạy

Từ thư mục `ffm-method-types` trên Linux x86-64:

```bash
mkdir -p build

cc -std=c11 -O2 -fPIC -shared \
  native/ffm_types.c -o build/libffm_types.so

javac -d build src/FFMMethodTypes.java

java --enable-native-access=ALL-UNNAMED \
  -cp build FFMMethodTypes
```

- `-fPIC -shared` tạo ELF shared library, export các C symbols nêu trên.
- `javac` cần **JDK 22+**. Đây là FFM API chính thức nên không cần `--enable-preview` ở JDK 22.
- `--enable-native-access=ALL-UNNAMED` cấp quyền gọi các **restricted FFM methods** trên classpath, đặc biệt `SymbolLookup.libraryLookup` và `Linker.downcallHandle`. Với named modules, chỉ cấp quyền cho các modules thích hợp.
- `Path.toAbsolutePath()` khiến việc mở thư viện dùng absolute path, nhưng vẫn giả định current working directory là gốc dự án.
- Khi phát hành cho Windows/macOS phải build lại đúng ABI, đặt tên file theo hệ điều hành và xét C naming/export conventions; **đừng dùng nguyên lệnh Linux**.

**Stdout dự kiến trên môi trường đã nêu:**

```text
descriptor type: (int,int)int
bound type: (int,int)int
unbound type: (MemorySegment,int,int)int
bound verified: true
unbound verified: true
bound result: 42
unbound result: 15
double type: (double,double)double
double result: 3.0
void type: (MemorySegment,int,int)void
out value: 9
pair descriptor type: (int,int)MemorySegment
pair bound type: (SegmentAllocator,int,int)MemorySegment
pair values: 11,12
wrong exact return: WrongMethodTypeException
```

Mỗi dòng kiểu là kết quả của **`MethodType.toString()` tại runtime**, không phải kiểu do chúng ta suy đoán từ tên C symbol.

### 5.5. Vì sao ví dụ có ba kiểu signature đặc biệt?

**`add_i32`**:
- Mỗi `JAVA_INT` cho Java carrier `int`.
- Bound có hai tham số `int`.
- Unbound thêm một `MemorySegment` đầu cho function address.

**`write_sum`**:
- `ofVoid` cho return `void`.
- C `int32_t*` ánh xạ Java carrier `MemorySegment`.
- Phương thức `invokeExact(output, 4, 5)` phải ở ngữ cảnh **void invocation**; không thể kỳ vọng một kết quả trả về.
- C ghi vào output buffer; Java đọc qua `output.get(JAVA_INT, 0)`.
- Không truyền `byte[]` heap segment mặc định như một C pointer nếu downcall chưa được cấu hình cho heap access; `arena.allocate` cấp phát native memory phù hợp.

**`make_pair`**:
- Struct return by value được mô tả bằng `GroupLayout`.
- `pairDesc.toMethodType()` chỉ thấy native arguments `(int,int)MemorySegment`.
- **Downcall handle thực tế** còn cần `SegmentAllocator`, để FFM runtime bố trí vùng nhận struct return.
- Vì return là Java `MemorySegment`, code đọc fields theo layout/offset thực (ở đây hai int liên tiếp, offset 0 và 4). Bản demo dùng struct C tương ứng và ABI Linux/x64.

### 5.6. Kiểm tra logic chương trình trước khi áp dụng vào thư viện thật

- C hàm `add_i32` trả `int32_t`; Java `JAVA_INT` có carrier `int`, cả hai đều 32-bit trên ABI đã chọn.
- C `mul_f64` nhận/trả `double`; Java `JAVA_DOUBLE` carrier `double`.
- C `write_sum` nhận một **native pointer** (không phải `int` chứa địa chỉ), Java truyền `MemorySegment` có lifetime hợp lệ.
- Struct `Pair` gồm hai `int32_t` nên layout minh họa hai `JAVA_INT` liền nhau, kích thước 8 byte trên Linux/x64; đối với struct khác phải đối chiếu C ABI padding/alignment thực.
- `SymbolLookup.libraryLookup` gắn lifetime của library với arena. Tất cả lần gọi handle đều thực hiện **trong scope arena**, không dùng handles/symbols sau khi arena đóng.
- Ví dụ bắt `WrongMethodTypeException` vì sai **Java call-site return type**. Đây là một lỗi khác về bản chất với descriptor không đúng native ABI (có thể crash).

## 6. Đối chiếu MethodType: cách đọc từng tham số

Một `MethodType` có:

```java
MethodType type = handle.type();

Class<?> result = type.returnType();
int arity = type.parameterCount();

for (int i = 0; i < arity; i++) {
    Class<?> parameter = type.parameterType(i);
    System.out.println(i + " -> " + parameter.getName());
}
```

Đây là **fragment**; `handle` phải có trước. Bạn không nên chỉ nhìn một `toString()` rồi phân tích bằng regex; API `returnType()` và `parameterType(i)` cho phép đối chiếu **chính xác Java classes**.

### 6.1. So sánh kiểu chặt bằng `MethodType.equals`

`MethodType` là một value-based immutable descriptor. Dùng:

```java
MethodType expected = MethodType.methodType(
        int.class, int.class, int.class);

if (!handle.type().equals(expected)) {
    throw new IllegalStateException(
            "Unexpected FFM downcall type: " + handle.type());
}
```

Mẫu này hữu ích trong initialization code của binding library, để phát hiện **sai chỗ bind/unbound** hoặc sai carrier trước khi gọi lần đầu. Nhưng nó **không xác minh native declaration**; để xác nhận ABI, bạn phải kiểm tra header C, data model, compiler/platform và tài liệu thư viện native.

### 6.2. `MethodType.changeReturnType` và `insertParameterTypes` dùng để giải thích

Để hiểu khác biệt synthetic parameter:

```java
MethodType descriptorType =
        addDesc.toMethodType();  // (int,int)int

MethodType predictedUnbound =
        descriptorType.insertParameterTypes(
                0, MemorySegment.class); // (MemorySegment,int,int)int

System.out.println(
        predictedUnbound.equals(addUnbound.type())); // true
```

Đây là fragment dựa trên biến của ví dụ `add_i32`. Công thức chỉ đúng cho mẫu scalar đơn giản **không có options thêm tham số**. Đối với group return hoặc `captureCallState`, phải xét các synthetic arguments khác và vẫn **đọc `handle.type()` thực tế**.

**Không cố tự sửa MethodType của native descriptor chỉ để ép cho bằng chữ ký Java mong muốn**. Bản `FunctionDescriptor` vẫn phải mô tả đúng hàm C; các combinators của MethodHandle chỉ thích nghi Java call site, không biến hàm C thật thành chữ ký native khác.

## 7. `invokeExact`, `invoke` và `invokeWithArguments`

### 7.1. `invokeExact`: khớp chính xác kiểu call site

`MethodHandle.invokeExact` là một **signature-polymorphic method**. Java compiler suy ra method type của call site từ kiểu tham số **tĩnh** và kiểu kết quả trong ngữ cảnh biểu thức.

Ví dụ handle có `(int,int)int`:

```java
// ĐÚNG: hai int, kiểu kết quả cũng là int.
int x = (int) addBound.invokeExact(20, 22);

// SAI: caller kỳ vọng long thay vì int.
// Phần native function không tự đổi return type.
long y = (long) addBound.invokeExact(20, 22);
```

Hai dòng là fragments để đối chiếu; dòng thứ hai **có thể biên dịch** nhưng sẽ ném `WrongMethodTypeException` khi chạy bởi `MethodType` thực tế không khớp call site `(int,int)long`. Chính ví dụ hoàn chỉnh đã catch lỗi đó.

Nếu chỉ gọi `addBound.invokeExact(20, 22);` như **statement** và bỏ kết quả, call site thường có return type `void`, cũng không khớp handle có return `int`. Với `invokeExact`, *việc kết quả có được sử dụng như một kiểu cụ thể hay không* cũng ảnh hưởng đến phương thức gọi.

**Lời khuyên:** khi cần `int`, hãy khai báo biến `int` hoặc cast kết quả `(int)` đúng chỗ; khi cần `long` do C trả `size_t` 64-bit, descriptor/carrier cũng phải là `JAVA_LONG` chứ không chỉ cast ở Java.

### 7.2. `invoke`: có thể thích nghi Java types

`handle.invoke(...)` có thể áp dụng các chuyển đổi Java được `MethodHandle` cho phép, gần với `asType`. Nó hữu ích khi call sites không cố định chặt, nhưng:

- Không được dùng `invoke` để che descriptor sai ABI.
- Boxing/unboxing và chuyển đổi có chi phí/khả năng ném exception.
- Với FFM hot paths, khi chữ ký ổn định, `invokeExact` giúp minh bạch kiểu và tối ưu hóa.

Ví dụ `invoke` có thể thích nghi một số primitive conversions:

```java
// Fragment: addBound có (int,int)int.
int sum = (int) addBound.invoke((short) 20, (short) 22);
```

`invoke` ở đây không thay kiểu `int32_t` của C. Nó chỉ thích nghi **Java call-site short → int** theo quy tắc MethodHandle trước khi thực hiện downcall.

### 7.3. `invokeWithArguments` là đường gọi linh hoạt

```java
Object result = addBound.invokeWithArguments(20, 22);
System.out.println(result); // 42
```

Đây là fragment. `invokeWithArguments` trả `Object` với boxing và xử lý danh sách arguments linh hoạt; nó phù hợp cho reflection-like tooling, nhưng **không nên là mặc định** trong vòng lặp native calls hiệu năng cao. Giá trị `42` ở ví dụ là boxed `Integer`, không phải C pointer.

### 7.4. `asType` không sửa được ABI sai

Giả sử bạn làm:

```java
MethodHandle adapted = addBound.asType(
        MethodType.methodType(
                int.class, short.class, short.class));
```

Đây là fragment. Adapted handle có Java signature `(short,short)int` và chuyển `short` sang `int` trước khi gọi. **Native `add_i32` vẫn nhận hai 32-bit integers** theo descriptor gốc. Cần phân biệt adaptation của MethodHandle và mô tả C function; không thể tự đổi signature C bằng `asType`.

## 8. Mapping C ABI: MethodType đúng Java vẫn có thể sai native

### 8.1. `int`, `long`, `size_t` không giống nhau trên mọi nền tảng

Java `int` là 32-bit và `long` là 64-bit theo ngôn ngữ. C `int`, `long`, `size_t` phụ thuộc **ABI/data model**.

| C type | Linux/x64 điển hình | Windows/x64 điển hình | Hệ quả cho FFM |
| --- | --- | --- | --- |
| `int` | 32-bit | 32-bit | Thường `JAVA_INT` |
| `long` | 64-bit | 32-bit | Linux `JAVA_LONG`, Windows `JAVA_INT` |
| `long long` | 64-bit | 64-bit | Thường `JAVA_LONG` |
| `size_t` | 64-bit | 64-bit | `JAVA_LONG` trên hai hệ 64-bit này |
| `void *` | 64-bit pointer | 64-bit pointer | `ADDRESS` → `MemorySegment` |

Đây là những mapping ví dụ của ABIs thường dùng. Một biến `C long` không phải lúc nào là Java `long`. Nếu nhầm C `long` trên Windows x64 và dùng `JAVA_LONG`, `handle.type()` vẫn có thể in `long` đẹp mắt, nhưng **native call có thể sai ABI**.

### 8.2. Đọc `canonicalLayouts` của Linker

FFM cung cấp map canonical layout theo native ABI:

```java
Linker linker = Linker.nativeLinker();

var canonical = linker.canonicalLayouts();
var cLong = canonical.get("long");
var cSizeT = canonical.get("size_t");

System.out.println(cLong);
System.out.println(cSizeT);
```

Đây là fragment; output phụ thuộc ABI/runtime nên không cung cấp một stdout cố định. Nó cho biết layout canonical của các C types trên chính nền tảng, giúp thiết kế đúng `FunctionDescriptor`. Nếu cần carrier, với layout thuộc `ValueLayout` có thể dùng `((ValueLayout)cSizeT).carrier()`.

**Không thay mọi kiểu C bằng `JAVA_LONG` vì đang chạy JVM 64-bit.** Phải hiểu C header và calling convention. Với typedef của thư viện, có thể cần tra cứu type platform theo header cụ thể, không thể dựa vào tên typedef chung.

### 8.3. Ví dụ C `strlen` và vấn đề `size_t`

Khai báo:

```c
size_t strlen(const char *s);
```

Trên **Linux/x64**, `size_t` là 64-bit, nên descriptor thường là:

```java
FunctionDescriptor strlenDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_LONG,
        ValueLayout.ADDRESS);
```

Downcall handle **bound** có Java type:

```text
(MemorySegment)long
```

C `const char *` không biến thành Java `String`: phải tạo một native C string, ví dụ `arena.allocateFrom("Hello")`, rồi:

```java
long length = (long) strlen.invokeExact(
        arena.allocateFrom("Hello")); // 5
```

Đây là fragment khi `strlen` đã được linker resolve, arena còn sống. Trên 32-bit ABI, `size_t` có thể map sang `JAVA_INT`, khiến MethodType là `(MemorySegment)int`. Dùng `canonicalLayouts().get("size_t")` để tránh hard-code sai khi cần hỗ trợ đa nền tảng.

**Chú ý:** `size_t` là unsigned; Java carrier có thể signed. Với length rất lớn vượt miền positive của Java type, ứng dụng phải có chính sách diễn giải unsigned/bounds riêng.

## 9. Synthetic parameter cho group/struct return

Một C hàm trả struct by value:

```c
struct Pair { int32_t left; int32_t right; };
struct Pair make_pair(int32_t left, int32_t right);
```

Được mô tả bằng một **group layout** trả về và hai argument layouts:

```java
StructLayout pairLayout = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("left"),
        ValueLayout.JAVA_INT.withName("right"));

FunctionDescriptor pairDesc = FunctionDescriptor.of(
        pairLayout,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

`pairDesc.toMethodType()`:

```text
(int,int)MemorySegment
```

Nhưng downcall handle **bound** có thêm `SegmentAllocator`:

```text
(SegmentAllocator,int,int)MemorySegment
```

và downcall handle **unbound** có:

```text
(MemorySegment,SegmentAllocator,int,int)MemorySegment
```

Ý nghĩa:

- `MemorySegment` đầu tiên của unbound là **địa chỉ hàm**.
- `SegmentAllocator` là nơi FFM runtime cấp phát **bộ nhớ nhận struct return by value**.
- Hai `int` cuối là tham số thật của C.
- `MemorySegment` trả về là **view tới kết quả struct**.

Ví dụ:

```java
// Fragment: makePair đã được link bằng pairDesc.
SegmentAllocator allocator = arena;

MemorySegment pair = (MemorySegment)
        makePair.invokeExact(allocator, 11, 12);

int first = pair.get(ValueLayout.JAVA_INT, 0L);
int second = pair.get(ValueLayout.JAVA_INT, 4L);
```

Trong đoạn này, `arena` phải còn sống, đủ quyền truy cập và tương thích ABI của struct. **Đừng nhầm struct by value với pointer tới struct**:

- `struct Pair make_pair(...)` → return group layout, Java return carrier `MemorySegment`, handle có thêm `SegmentAllocator`.
- `struct Pair* make_pair(...)` → return `ValueLayout.ADDRESS`, Java return `MemorySegment`, **không** phát sinh allocator synthetic parameter vì return là pointer value.

Hai trường hợp có cùng Java return carrier `MemorySegment` nhưng **chữ ký native và quy tắc ownership hoàn toàn khác**. Đây là lý do phải đọc **FunctionDescriptor** lẫn `MethodHandle.type()`.

### 9.1. Vì sao allocator là tham số Java, không xuất hiện trong C header?

FFM runtime cần nơi cấp phát vùng chứa struct result, nhưng C ABI có thể truyền struct qua register hoặc sử dụng một hidden return buffer theo calling convention. `SegmentAllocator` là cơ chế phía Java để quản lý bộ nhớ kết quả, **không phải một tham số C `SegmentAllocator*`**. Đừng tự chèn một pointer vào `FunctionDescriptor` chỉ để “khớp” Java MethodType.

### 9.2. Struct layout phải khớp ABI thật

`MemoryLayout.structLayout(...)` không tự thêm mọi padding ABI; phải mô tả alignment, field offsets và trailing padding thật sự. Ví dụ trong bài có hai `int32_t` nên trên Linux/x64 không cần padding giữa chúng. Với C `struct { int a; double b; }`, layout thường cần padding trước `double`, và `sizeof` theo ABI. Một descriptor tạo được handle không chứng minh struct mapping của bạn đúng.

## 10. Linker options cũng có thể thay đổi MethodType

Một số `Linker.Option` ảnh hưởng cách native linker tạo handle.

### 10.1. `captureCallState("errno")` thêm `MemorySegment`

Ví dụ:

```java
FunctionDescriptor descriptor = FunctionDescriptor.ofVoid();

Linker.Option capture =
        Linker.Option.captureCallState("errno");

MethodHandle handle =
        linker.downcallHandle(functionAddress, descriptor, capture);
```

Đây là fragment trên ABI có hỗ trợ capture `errno`, không phải chương trình độc lập. `descriptor.toMethodType()` là `()void`, nhưng **bound handle** có thêm `MemorySegment` để trỏ tới **capture-state segment**:

```text
descriptor.toMethodType(): ()void
handle.type():            (MemorySegment)void
```

Nếu dùng **unbound handle**, còn thêm tham số **function address** ở đầu, nên `(MemorySegment,MemorySegment)void`. Với hàm trả struct, thứ tự các synthetic parameters có thêm allocator; cách bền vững là **in `handle.type()` và kiểm tra theo JDK/docs**, không suy đoán từ C header.

`Linker.Option.captureStateLayout()` cho biết layout cần dùng để cấp phát capture state. State segment phải đúng size/alignment; `errno` là state của native call và không nên đọc muộn qua C function khác sau đó vì có thể bị thay đổi. **Không** dùng captureCallState như cách tự động chuyển một C error code thành Java exception.

### 10.2. `firstVariadicArg` không phải một Java varargs array

Với C variadic function như:

```c
int printf(const char *format, ...);
```

nếu chuyên biệt hóa cho format và một `int` thì descriptor có hai native argument layouts: `ADDRESS` cho format, `JAVA_INT` cho giá trị, và dùng `Linker.Option.firstVariadicArg(1)` để báo rằng argument index 1 bắt đầu phần biến thiên.

```java
FunctionDescriptor printfDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT);

MethodHandle printf = linker.downcallHandle(
        printfAddress,
        printfDesc,
        Linker.Option.firstVariadicArg(1));
```

Đây là **fragment**, không khuyến nghị dùng `printf` cho ví dụ đơn giản vì format string/ABI và side effects có thêm nhiều điểm cần kiểm soát. `firstVariadicArg(1)` điều chỉnh native calling convention của variadic arguments; nó **không chuyển handle thành Java `Object...` hoặc `Object[]`**, cũng không tự tạo mọi biến thể type. Muốn gọi số lượng/kiểu variadic arguments khác, phải thiết kế một descriptor chuyên biệt khác.

### 10.3. `critical(boolean)` không phải phép sửa chữ ký

`Linker.Option.critical(...)` đánh dấu downcall theo điều kiện tối ưu riêng; nó **không làm ABI signature trở nên tùy ý**. Đặc biệt, critical functions không nên call back vào Java hay thực hiện hành vi vi phạm hợp đồng critical call, và `critical` không kết hợp được với `captureCallState`. Không bật critical chỉ để giải quyết `WrongMethodTypeException`.

## 11. Phân biệt những lỗi có thể bắt được và lỗi ABI nguy hiểm

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` từ `invokeExact` | Java call site không khớp `handle.type()` về arguments hoặc return | In `handle.type()`, sửa kiểu tĩnh/cast/result và bound/unbound |
| Cần thêm `MemorySegment` đầu khi invoke | Dùng unbound `downcallHandle(descriptor)` | Truyền function address trước C arguments hoặc bind symbol |
| Cần thêm `SegmentAllocator` | Native return là group layout by value | Truyền allocator tương thích với lifetime của kết quả |
| Cần thêm một `MemorySegment` nhưng C không có tham số đó | Dùng `captureCallState` | Cấp capture segment theo `captureStateLayout` |
| `NoSuchElementException` khi `orElseThrow()` | Symbol lookup không tìm thấy tên | Kiểm tra export, C++ name mangling, đường dẫn thư viện |
| `IllegalCallerException` hoặc cảnh báo native access | Module chưa được cấp quyền restricted FFM methods | Cấu hình `--enable-native-access` cho đúng module |
| `IllegalArgumentException` ở `downcallHandle` | Descriptor/layout/options không được linker hỗ trợ; function address không hợp lệ | Kiểm tra canonical layouts, ABI và flags |
| `IllegalStateException`/`WrongThreadException` khi truyền segment | Arena đã đóng hoặc confined segment bị dùng sai thread | Sửa ownership/lifetime/thread scope |
| Truyền heap segment cho C pointer bị từ chối | ADDRESS parameter thường yêu cầu native segment | Dùng `Arena.allocate(...)`/native memory theo contract |
| C function nhận dữ liệu sai dù `handle.type()` đúng | `FunctionDescriptor` sai ABI, signedness, struct padding hoặc pointer ownership | Đối chiếu C header, ABI, compiler và từng layout |
| JVM crash hoặc dữ liệu bị hỏng | Native signature mismatch/dangling pointer/invalid memory | Dừng, kiểm chứng descriptor và ownership; không dựa vào Java exception |

### 11.1. Lỗi Java MethodType và lỗi native ABI hoàn toàn khác nhau

**Lỗi Java MethodType** thường phát hiện được trước khi thực sự gọi C:

```java
try {
    long value = (long) addBound.invokeExact(1, 2);
} catch (WrongMethodTypeException ex) {
    System.out.println("wrong Java call-site return type");
}
```

Nhưng **sai native descriptor** nghiêm trọng hơn:

```java
// SAI ABI nếu C function thật sự nhận/return int32_t.
// Không nên TẠO/GỌI handle này trong code thực tế.
FunctionDescriptor wrongNative = FunctionDescriptor.of(
        ValueLayout.JAVA_DOUBLE,
        ValueLayout.JAVA_DOUBLE,
        ValueLayout.JAVA_DOUBLE);
```

Hàm C thật nhận hai `int32_t` trong integer registers và trả `int32_t`, còn descriptor sai yêu cầu floating-point registers và double return. `handle.type()` vẫn có thể nhìn “hợp lý” `(double,double)double`, nhưng linker không có cách tự xác minh C symbol có đúng chữ ký đó. Nếu thực hiện downcall, kết quả có thể bất định, kể cả crash.

**Kết luận:** `MethodHandle.type()` kiểm tra **Java invocation protocol**. `FunctionDescriptor` phải khớp **ABI thực tế** của native function bằng cách đối chiếu tài liệu và header C.

### 11.2. Khác nhau giữa `ClassCastException` và `WrongMethodTypeException`

`WrongMethodTypeException` đến từ mismatch giữa kiểu call site của `invokeExact`/adaptation và `MethodType` của handle. `ClassCastException` có thể phát sinh từ quá trình cast runtime object không đúng class, đặc biệt khi dùng `invoke`/`invokeWithArguments`/custom adaptation. Không nên gom mọi lỗi FFM vào một loại “native linkage error”; hãy xem stack trace và actual MethodType.

## 12. Kiểm thử chữ ký bằng cách tự động hóa ở thời điểm khởi tạo

Một thư viện Java gọi nhiều C functions nên có bước xác minh Java-facing method types ngay khi tạo handles.

```java
static void requireType(
        String symbol,
        MethodHandle handle,
        MethodType expected) {

    MethodType actual = handle.type();
    if (!actual.equals(expected)) {
        throw new IllegalStateException(
                symbol + " MethodType mismatch: expected " +
                expected + ", actual " + actual);
    }
}
```

Đây là **một helper Java static**; imports `MethodHandle` và `MethodType` cần có trong class chứa helper. Ví dụ:

```java
// Fragment cho handle bound int32_t add_i32(int32_t,int32_t).
requireType(
        "add_i32",
        addBound,
        MethodType.methodType(
                int.class, int.class, int.class));
```

Đối với thư viện đa nền tảng, `requireType` giúp bắt lỗi **đoán carrier** hoặc thiếu tham số tổng hợp. Tuy nhiên, để bảo đảm descriptor đúng trên nhiều OS, cần thêm:

1. Kiểm tra `Linker.nativeLinker().canonicalLayouts()` của các C types quan trọng.
2. Cung cấp bộ test native với functions trả những giá trị nhận diện được, gồm `int`, `double`, pointer và struct.
3. Dùng giá trị test không gây undefined behavior (không overflows, không pointer NULL nếu C function không cho).
4. Dùng golden expected outputs có nêu rõ ABI/môi trường.
5. Đảm bảo library/symbol/segments còn sống cho đến khi downcalls kết thúc.
6. Kiểm tra mã hóa `char*`, size/unsignedness, struct padding và ownership.
7. Thử cả bound/unbound cases nếu framework sử dụng function pointers.

Nếu cần phát hành đa nền tảng, nên có CI ít nhất Linux x64 và Windows x64; các ABI thật sự có thể khác nhau dù Java `MethodType` trông giống hệt.

## 13. Vấn đề lifetime của symbol, downcall handle và native data

### 13.1. Giữ thư viện native còn load

Với:

```java
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup symbols =
            SymbolLookup.libraryLookup(path, arena);
    MemorySegment addr =
            symbols.find("add_i32").orElseThrow();

    MethodHandle handle =
            linker.downcallHandle(addr, descriptor);

    int result = (int) handle.invokeExact(1, 2);
}
```

Đây là fragment. Library lookup gắn với `arena`. Sau khi arena đóng, library có thể bị unload; không lưu handle bound vào static field để **gọi sau khi library đã unload**. Function pointer trong bound handle không tự đảm bảo module C vẫn còn load vô thời hạn.

### 13.2. Dữ liệu native phải hợp lệ suốt lời gọi

Nếu function nhận `ADDRESS`, đối số Java là `MemorySegment`. Native linker kiểm tra những điều kiện truy cập/keep-alive thích hợp, nhưng không thể bảo đảm C function dùng pointer đúng trong **mọi hoàn cảnh sau khi downcall trả về**.

Ví dụ C giữ pointer vào một global variable để dùng bất đồng bộ: Java không được đóng arena ngay sau downcall nếu C chưa sử dụng xong dữ liệu. Thiết kế phải có **release callback, acknowledgment hoặc ownership transfer** theo API contract. Không coi việc `handle.invokeExact` đã return là chứng minh C không còn giữ pointer.

### 13.3. Downcall có restricted access vì lỗi có thể vượt ranh giới JVM safety

Không có Java compiler hay linker runtime nào chứng minh C header thật của một symbol tùy ý. `Linker.downcallHandle` được đánh dấu restricted vì mismatches có thể làm hỏng tiến trình. Chỉ liên kết thư viện đáng tin, kiểm soát đúng ABI, đọc header và tránh đầu vào native pointers không rõ nguồn.

## 14. Các bẫy ngữ nghĩa hay gặp

### 14.1. “`FunctionDescriptor` in ra đúng thì `handle.type()` chắc chắn giống”

Không. Descriptor có thể được linker bổ sung synthetic params: function address cho unbound, allocator cho group return, capture-state segment cho `captureCallState`. Luôn kiểm tra **actual handle type**.

### 14.2. “C `void*` tương đương Java `long`”

Không. FFM `ADDRESS` có Java carrier **`MemorySegment`**. Một `long` thường không hợp lệ làm đối số `invokeExact` cho tham số pointer. Muốn truyền C NULL dùng `MemorySegment.NULL` khi contract cho phép, không truyền Java `null` hoặc `0L` làm function pointer.

### 14.3. “Tôi cast `(long)` ở chỗ gọi nên C sẽ trả 64 bit”

Sai. Cast tại Java call site thay đổi **kiểu kỳ vọng của `invokeExact`**, không làm thay đổi `FunctionDescriptor`. Nếu native function thật sự trả `int`, `handle.type()` là return `int`; cast kết quả trực tiếp sang `long` ở vị trí invokeExact có thể gây `WrongMethodTypeException`. Muốn nhận `long` từ `int`, hãy nhận `int` trước:

```java
int raw = (int) addBound.invokeExact(20, 22);
long widened = raw;
```

### 14.4. “Có thể truyền Java String vào C char* vì cùng nói về chuỗi”

Không. FFM `ADDRESS` yêu cầu pointer `MemorySegment`. C `char *` có quy tắc encoding/NUL termination/lifetime riêng. Ví dụ `Arena.allocateFrom("Hello")` cấp phát native UTF-8 string được NUL-terminate; giữ arena còn sống trong lúc C gọi `strlen`.

### 14.5. “Hàm trả `struct*` chắc chắn có thêm `SegmentAllocator`”

Không. `struct *` là một **pointer value** với `ADDRESS` → `MemorySegment`; không có allocator synthetic cho **return pointer**. Chỉ khi **descriptor return là group layout** cho struct by value thì handle mới có thêm allocator. `MemorySegment` carrier không đủ để kết luận trường hợp nào.

### 14.6. “SymbolLookup tìm được tên nên FFM đã xác nhận chữ ký”

Không. Native symbol lookup thường chỉ trả **địa chỉ**. FFM không có thông tin C type đầy đủ từ tên symbol, nên việc liên kết nhầm ABI có thể gây crash. Kiểm chứng header và function typedef từ thư viện.

### 14.7. “`invoke` và `asType` có thể sửa mọi type mismatch”

Không. Chúng thích nghi **Java-side invocation** trong giới hạn được phép. Chúng không có quyền biến một C function nhận `double` thành hàm nhận `int32_t` trong máy native. Nếu descriptor sai, phải sửa descriptor.

## 15. Quy trình thực hành khi tích hợp một API C mới

1. **Đọc chính xác C declaration**: kiểu return, kiểu đối số, calling convention, const/pointer, struct by value vs pointer, variadic hay không.
2. **Xác định ABI runtime**: `Linker.nativeLinker()`, canonical layouts; kiểm tra C `long`/`size_t`/pointers/struct padding.
3. **Tạo FunctionDescriptor theo thứ tự return trước, args sau** (hoặc `ofVoid`).
4. **Resolve symbol** bằng `SymbolLookup.defaultLookup` hoặc `SymbolLookup.libraryLookup`; giữ library alive.
5. **Chọn bound/unbound** theo use case, không trộn lẫn.
6. **Tạo MethodHandle** và in/đối chiếu `handle.type()`.
7. **Xử lý synthetic parameters**: function pointer nếu unbound, allocator nếu group return, capture segment nếu dùng `captureCallState`.
8. **Chuẩn bị native values**: C strings thành native `MemorySegment`; output buffers đủ size/alignment; arena lifetime đúng.
9. **Gọi đúng static types** qua `invokeExact`; return `void` ở ngữ cảnh statement, primitive result có cast đúng.
10. **Đối chiếu output** với implementation C bằng golden tests; không chỉ kiểm tra không ném Java exception.
11. **Dọn tài nguyên/lifetime**: không gọi function pointer sau unload, không đóng buffer khi C còn dùng, gọi đúng deallocator.
12. **Tạo test đa nền tảng** khi code phụ thuộc `size_t`/`long`/struct ABIs.

Quy trình này giảm hai nhóm lỗi khác nhau: sai Java MethodType (thường phát hiện được) và sai C ABI (có thể nguy hiểm ở mức process).

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)` tương ứng chữ ký Java nào khi tạo downcall **bound**?  
**Đáp án:** `(int,int)int`. `JAVA_INT` đầu tiên là return, hai `JAVA_INT` sau là arguments.

**Câu 2.** Cũng descriptor trên, tạo handle bằng `linker.downcallHandle(desc)` chưa truyền địa chỉ hàm. `handle.type()` là gì?  
**Đáp án:** `(MemorySegment,int,int)int`. Tham số đầu là function address.

**Câu 3.** C hàm `void update(int *p)`, Java descriptor `ofVoid(ADDRESS)`. Bound MethodType là gì?  
**Đáp án:** `(MemorySegment)void`. `MemorySegment` là pointer C; return là `void`.

**Câu 4.** Java ghi `long value = (long) addBound.invokeExact(1,2);` nhưng handle trả `int`. Điều gì xảy ra?  
**Đáp án:** `WrongMethodTypeException` do call-site return `long` không khớp actual return `int`. Nhận `int` trước rồi Java-widen sang `long` nếu cần.

**Câu 5.** `struct Pair make_pair(int,int)`: vì sao bound handle có thêm `SegmentAllocator`?  
**Đáp án:** Native return là group layout by value; FFM cần allocator tạo buffer chứa kết quả struct. Đây không phải tham số C khai báo.

**Câu 6.** Nếu C trả `struct Pair*` thay vì `struct Pair`, có thêm `SegmentAllocator` không?  
**Đáp án:** Không. Return layout là `ADDRESS`, carrier `MemorySegment` nhưng không phải group-return allocator.

**Câu 7.** Trên Windows/x64, C `long` có nên luôn ánh xạ sang `JAVA_LONG` vì Java `long` là 64-bit?  
**Đáp án:** Không. C `long` thường 32-bit trên Windows/x64, phải chọn layout theo ABI/canonical layouts, thường `JAVA_INT`.

**Câu 8.** `FunctionDescriptor.toMethodType()` và `MethodHandle.type()` có thể khác nhau khi nào?  
**Đáp án:** Khi downcall chưa bound function address, khi return group layout bổ sung allocator, khi có `captureCallState` hoặc linker options khác bổ sung Java arguments.

**Câu 9.** `Linker.Option.firstVariadicArg(1)` có biến Java MethodHandle thành `Object...` không?  
**Đáp án:** Không. Phải khai báo đầy đủ các concrete variadic arguments trong descriptor; option mô tả convention của chúng.

**Câu 10.** `handle.type()` khớp `(double,double)double`, liệu có chứng minh symbol C là `double f(double,double)`?  
**Đáp án:** Không. Kiểu handle được **dựng từ descriptor** do Java cung cấp; symbol lookup không tự kiểm tra C declaration. Descriptor sai có thể gây crash.

**Câu 11.** Unbound handle có hai `MemorySegment` liên tiếp cho `void write_sum(int32_t*,...)`. Thứ tự là gì?  
**Đáp án:** Đầu tiên **function address**; tiếp theo **out buffer pointer** của C; sau đó là các `int`.

**Câu 12.** Vì sao không nên lưu handle bound sau khi đóng arena dùng `SymbolLookup.libraryLookup`?  
**Đáp án:** Arena quản lý lifetime library/symbols; sau khi đóng, library có thể unload, handle cũ có thể trỏ đến địa chỉ hàm không còn hợp lệ.

## 17. Ghi nhớ

- **`FunctionDescriptor`** mô tả **native signature qua layouts**; **`MethodType`** mô tả **kiểu Java call-site** của MethodHandle.
- **`FunctionDescriptor.toMethodType()` không phải luôn là `handle.type()`**; hãy dùng `handle.type()` để kiểm tra chữ ký downcall thực tế.
- **Bound downcall:** không cần truyền function address mỗi lần gọi. **Unbound downcall:** có thêm tham số `MemorySegment` đầu cho address.
- **ADDRESS ↔ MemorySegment; JAVA_INT ↔ int; JAVA_DOUBLE ↔ double; ofVoid ↔ void**; C types như `long` và `size_t` phải map theo ABI, không suy đoán từ tên.
- **Struct return by value** thêm `SegmentAllocator`; **pointer-to-struct return** không tự thêm allocator.
- **`captureCallState`** thêm capture-state segment; variadic option thay đổi calling convention, không phải Java varargs tự do.
- **`invokeExact`** đòi Java argument/return types khớp tuyệt đối với `MethodHandle.type()`. Sai Java type có thể ném `WrongMethodTypeException`.
- **MethodType đúng không bảo đảm ABI đúng**. FFM không tự suy ra C function prototype từ symbol name; descriptor sai có thể khiến JVM crash.
- **Giữ thư viện và native segments còn sống** suốt lời gọi, quản lý buffer/ownership theo contract và cấp native access cho module thích hợp.

### Tài liệu chính thức

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): downcallHandle bound/unbound, hidden function address, SegmentAllocator khi return group layout, ABI mapping và restricted methods.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): of/ofVoid, argumentLayouts, returnLayout và toMethodType.
- [Oracle Java SE 22 — Linker.Option](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html): captureCallState, captureStateLayout, firstVariadicArg và critical.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): libraryLookup(Path, Arena), defaultLookup và lifetime native library.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): carrier types, size/alignment và ADDRESS.
- [Oracle Java SE 22 — MethodHandle](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html): invokeExact, invoke, invokeWithArguments, MethodType matching và WrongMethodTypeException.
- [Oracle Java SE 22 — MethodType](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodType.html): Java parameter/return type descriptor, equals, parameterType và returnType.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): final FFM API từ JDK 22, downcalls và restricted access.
