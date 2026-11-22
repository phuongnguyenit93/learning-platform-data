# Truyền con trỏ hàm vào thư viện C và đọc dữ liệu tham số bằng FFM upcall

## 1. Khi Java không chỉ gọi C mà C còn phải gọi ngược Java

Trong Java Foreign Function & Memory API (FFM), **downcall** là lời gọi **Java → hàm native**, còn **upcall** là chiều ngược lại: **mã native C → callback Java**. Một thư viện C có thể yêu cầu người dùng truyền vào **con trỏ hàm** để nó gọi mỗi khi có dữ liệu mới, cần tính toán một giá trị, lọc record hoặc gửi sự kiện.

Ví dụ hợp đồng C:

```c
#include <stdint.h>

typedef struct {
    int32_t id;
    int32_t x;
    int32_t y;
} Event;

typedef int32_t (*event_callback)(
        const Event *event,
        int32_t event_bytes,
        void *user_data);

int32_t run_events(event_callback callback, void *user_data);
```

Khi gọi `run_events`, chương trình Java cần cung cấp một địa chỉ có thể được **C coi như function pointer**. Nếu C thực hiện `callback(&event, sizeof(Event), user_data)`, Java callback phải nhận được **địa chỉ của struct**, **số byte của struct** và **địa chỉ của dữ liệu ngữ cảnh**; sau đó giải mã các trường `id`, `x`, `y`, trả một số `int32_t` cho C.

Điều này được thực hiện bằng **`Linker.upcallStub`**: biến một `MethodHandle` trỏ tới Java method thành một **upcall stub** nằm ở địa chỉ native có thể truyền vào C.

### 1.1. Mục tiêu của bài

Sau khi học, bạn sẽ có thể:

1. Đọc chữ ký **callback function pointer** trong header C.
2. Xây `FunctionDescriptor` và `MethodHandle` tương thích **đúng ABI**.
3. Tạo callback pointer bằng `Linker.upcallStub` và truyền nó như một tham số `ADDRESS` cho downcall.
4. Đọc **tham số nguyên thủy** và dữ liệu **được trỏ tới** từ Java callback, bao gồm struct, mảng byte và `void *user_data`.
5. Xử lý `NULL`, kích thước buffer, alignment, scope và việc con trỏ chỉ có giá trị tạm thời.
6. Giữ callback stub và context sống đủ lâu; tránh treo callback qua lần đóng `Arena`.
7. Xử lý exception **bên trong callback**, vì một exception thoát khỏi upcall target có thể khiến JVM kết thúc đột ngột.
8. Biên dịch/chạy một ví dụ Java và C hoàn chỉnh trên Linux, macOS và Windows x64.

### 1.2. Phiên bản Java

Code dùng API **ổn định từ JDK 22** (`java.lang.foreign`, JEP 454). Java 17 **không có** API FFM chuẩn với những chữ ký này; các bản preview/incubator trước đó có khác biệt. Hãy dùng JDK 22+ cho chương trình trong bài.

Các lệnh như `Linker.upcallStub`, `Linker.downcallHandle`, `SymbolLookup.libraryLookup` và `MemorySegment.reinterpret` là **restricted operations**. Khi chạy ứng dụng Java trên classpath, cấp native access cho unnamed module:

```bash
java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

Cấu hình native access **không sửa ABI, không xác thực C pointer** và không tự kéo dài lifetime của con trỏ. Cấp quyền cho module có tên bằng tên module thay vì `ALL-UNNAMED` khi triển khai modular application.

## 2. Hình dung luồng gọi với function pointer

```text
Java main()
   |
   | Linker.nativeLinker()
   | SymbolLookup.libraryLookup("...so/.dylib/.dll", arena)
   | downcallHandle(run_events, C signature)
   |
   | MethodHandles.lookup().findStatic(JavaCallback, "onEvent", ...)
   | Linker.upcallStub(methodHandle, callbackSignature, arena)
   |                     |
   |             MemorySegment callbackStub
   |               (native function pointer)
   |                     |
   | call run_events(callbackStub, contextAddress)
   v                     v
C: run_events(event_callback cb, void *ctx)
   |
   | Event event = ...
   | cb(&event, sizeof(Event), ctx)
   v
JVM upcall stub
   |
   | Dispatch tới Java MethodHandle
   v
Java: onEvent(MemorySegment eventPtr,
              int eventBytes,
              MemorySegment contextPtr)
   |
   | kiểm tra pointer/size
   | reinterpret để đọc vùng dữ liệu hợp lệ
   | đọc id, x, y và hệ số từ context
   | return int
   v
C nhận int32_t kết quả callback
   |
   | tiếp tục vòng lặp/gom kết quả
   v
Trả tổng về Java qua downcall
```

**Có hai function signature độc lập:**

- **C API được Java gọi (downcall)**: `int32_t run_events(event_callback, void*)`.
- **Callback do C gọi (upcall)**: `int32_t callback(const Event*, int32_t, void*)`.

Hai descriptor **không giống nhau**. Dù đều chứa `ADDRESS`, callback có ba tham số, còn `run_events` có hai tham số.

## 3. Đọc đúng typedef của function pointer trong C

### 3.1. Dịch kiểu C sang carrier Java

| C ABI | FFM layout thường dùng | Java carrier trong `MethodHandle` |
| --- | --- | --- |
| `int32_t` | `ValueLayout.JAVA_INT` | `int` |
| `uint8_t`/`char` | `JAVA_BYTE` | `byte` |
| `int64_t` | `JAVA_LONG` | `long` |
| `double` | `JAVA_DOUBLE` | `double` |
| `const Event *` | `ValueLayout.ADDRESS` | `MemorySegment` |
| `void *user_data` | `ValueLayout.ADDRESS` | `MemorySegment` |
| Function pointer `event_callback` | `ValueLayout.ADDRESS` | `MemorySegment` |
| C `void` return | `FunctionDescriptor.ofVoid(...)` | `void` |

Đối với ví dụ này, C dùng **`int32_t`**, không dùng C `long` hoặc `size_t`, để tránh khác biệt độ rộng giữa Linux và Windows 64-bit. `Event` có ba trường `int32_t`; trên compiler/ABI mục tiêu của demo, layout kỳ vọng là 12 byte với các offset lần lượt 0, 4 và 8.

Nếu dùng struct thực tế phức tạp, phải kiểm tra **`sizeof`, `alignof`, `offsetof`** theo đúng compiler target; không suy ra layout chỉ từ tên trường hay các số byte trong ví dụ.

### 3.2. Callback descriptor

C:

```c
typedef int32_t (*event_callback)(
    const Event *event,
    int32_t event_bytes,
    void *user_data
);
```

FFM:

```java
FunctionDescriptor callbackSignature =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT, // C trả int32_t
                ValueLayout.ADDRESS,  // const Event*
                ValueLayout.JAVA_INT, // int32_t event_bytes
                ValueLayout.ADDRESS   // void*
        );
```

Đây là **trích đoạn trong Java code có imports thích hợp**, không phải một chương trình chạy riêng. Thứ tự của `FunctionDescriptor.of(...)` là **return layout trước**, rồi danh sách các layout tham số theo **đúng thứ tự C**.

Java target phải có chữ ký:

```java
private static int onEvent(
        MemorySegment eventPtr, int eventBytes,
        MemorySegment userDataPtr) {
    // Xử lý rồi trả int.
    return 0;
}
```

Cần phân biệt `int eventBytes` là một **giá trị truyền theo value** và `MemorySegment eventPtr` là một **địa chỉ**. Java không nhận `Event` như một Java object tự động; nó phải tự đọc dữ liệu từ vùng native theo layout.

### 3.3. Descriptor cho hàm C nhận callback

C:

```c
int32_t run_events(event_callback callback, void *user_data);
```

FFM:

```java
FunctionDescriptor runSignature =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT, // return int32_t
                ValueLayout.ADDRESS,  // function pointer
                ValueLayout.ADDRESS   // void* user_data
        );
```

`downcallHandle` tạo từ descriptor này có **Java MethodType** tương đương:

```text
(MemorySegment callbackFunctionPointer,
 MemorySegment userDataAddress) -> int
```

Những đoạn `FunctionDescriptor` ở trên mô tả **hai hướng gọi**, không phải lệnh thực hiện callback. JVM chỉ biết địa chỉ cần gọi khi bạn truyền symbol của C function vào `downcallHandle` hoặc tạo stub với `upcallStub`.

## 4. Tạo Java MethodHandle trỏ tới callback

Có thể dùng `MethodHandles.lookup().findStatic(...)` để lấy handle của một Java static method:

```java
MethodHandle target = MethodHandles.lookup().findStatic(
        FfmCallbackDemo.class,
        "onEvent",
        MethodType.methodType(
                int.class,
                MemorySegment.class,
                int.class,
                MemorySegment.class
        )
);
```

Đây là trích đoạn bên trong class `FfmCallbackDemo` với một static method `onEvent` có chữ ký tương ứng; ví dụ hoàn chỉnh ở mục 8. `findStatic` có thể truy cập private static method nếu lookup được thực hiện từ chính class ấy.

**Tại sao không dùng Java method object hoặc một lambda bất kỳ?**

- `Linker.upcallStub` nhận **`MethodHandle`**, không trực tiếp nhận một interface lambda tùy ý.
- MethodType phải tương thích descriptor FFM cả **số lượng**, **thứ tự** và **carrier type**.
- Có thể chuyển lambda/method reference qua một static adapter hoặc bound MethodHandle, nhưng vẫn phải tạo ra handle đúng signature ở điểm đưa vào `upcallStub`.

### 4.1. Tạo upcall stub

```java
Linker linker = Linker.nativeLinker();

MemorySegment functionPointer =
        linker.upcallStub(target, callbackSignature, arena);
```

Ở đây `arena` là một `Arena` còn sống và caller có quyền native access. `functionPointer` là **một segment đại diện cho địa chỉ code stub**, **không phải** một Java `Runnable` hoặc địa chỉ của Java object. C có thể nhận nó như một **function pointer** qua đối số `ADDRESS`.

Theo Javadoc JDK 22, stub gắn với `Arena`: đóng arena sẽ **giải phóng stub**. Vì vậy callback function pointer **không còn hợp lệ** sau khi arena đóng.

### 4.2. Truyền qua downcall

```java
MethodHandle run = linker.downcallHandle(
        nativeFunctionAddress,
        runSignature
);

int sum = (int) run.invokeExact(
        functionPointer, userDataSegment
);
```

`run.invokeExact` thực hiện bước Java→C. Trong thân `run_events`, C gọi function pointer; bước C→Java đi qua stub mà `upcallStub` đã tạo. Khi Java callback trả về `int`, C nhận một `int32_t` theo ABI và tiếp tục.

`invokeExact` dùng kiểm tra kiểu **chính xác**. Nếu descriptor là `(ADDRESS, ADDRESS) -> JAVA_INT`, phải truyền hai `MemorySegment` và cast/nhận kết quả bằng `int`. Sai carrier có thể gây `WrongMethodTypeException`; sai descriptor native có thể gây crash/corruption vì FFM không thể đối chiếu metadata chữ ký trực tiếp từ C binary.

## 5. Đọc tham số con trỏ: vì sao `MemorySegment` nhận được dài 0?

Đây là phần quan trọng nhất về an toàn của callback.

C gọi:

```c
callback(&event, (int32_t) sizeof(Event), user_data);
```

JVM tạo Java argument cho `const Event *` dưới dạng **`MemorySegment` đại diện con trỏ native**. Khi layout tương ứng là `ValueLayout.ADDRESS` không chỉ định target layout, segment này **thường có `byteSize() == 0`**. Nó giữ **địa chỉ**, không giữ thông tin kích thước, vì JVM không thể biết thực tế con trỏ C đang trỏ tới bao nhiêu byte.

Do đó code sau **không đúng**:

```java
// SAI: eventPtr chưa có bounds cho dữ liệu struct.
int id = eventPtr.get(ValueLayout.JAVA_INT, 0L);
```

`get` yêu cầu ít nhất bốn byte trong bounds của segment, nên với zero-length segment sẽ bị `IndexOutOfBoundsException`.

### 5.1. Kiểm tra hợp đồng trước khi mở rộng bounds

Đối với C `Event` đã biết kích thước 12:

```java
if (eventPtr.address() == 0L) {
    // NULL pointer, không được dereference.
    return -1;
}
if (eventBytes != EVENT_LAYOUT.byteSize()) {
    // Kích thước dữ liệu không khớp.
    return -1;
}

MemorySegment event = eventPtr.reinterpret(eventBytes);
```

Đây là **trích đoạn trong callback trả `int`** với `EVENT_LAYOUT` được định nghĩa như mục 6. Lời gọi `reinterpret(long)` **gán bounds mới theo yêu cầu**, không tự xác minh con trỏ C có thực sự trỏ đến vùng hợp lệ dài như vậy.

**Điểm an toàn không thể bỏ qua:**

- `reinterpret` là **restricted, unsafe operation**. Nếu `eventPtr` sai địa chỉ hoặc vùng native đã bị free, việc đọc có thể làm JVM **crash**.
- Chỉ dùng khi tin cậy ABI/library và đã kiểm tra độ dài, `NULL` và lifecycle theo **hợp đồng native**.
- Không dùng `reinterpret(Long.MAX_VALUE)` để “cho chắc”; bounds giả lớn không làm bộ nhớ trở nên hợp lệ.
- Không lưu `event`/`eventPtr` để xử lý sau khi C đã rời callback, trừ khi native API **minh thị cấp quyền sở hữu và đảm bảo lifetime**.
- `const Event *` là cam kết C rằng callback không sửa struct; Java segment tự nó **không tự hiểu C `const`**. Hãy chỉ đọc dữ liệu và không gọi `set` lên vùng borrow này.

### 5.2. Đọc trường theo offset/layout

Java mô tả:

```java
StructLayout EVENT_LAYOUT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
);

long ID_OFFSET = EVENT_LAYOUT.byteOffset(
        MemoryLayout.PathElement.groupElement("id")
);
long X_OFFSET = EVENT_LAYOUT.byteOffset(
        MemoryLayout.PathElement.groupElement("x")
);
long Y_OFFSET = EVENT_LAYOUT.byteOffset(
        MemoryLayout.PathElement.groupElement("y")
);
```

Trích đoạn này thuộc class dùng FFM. Với ABI mẫu, `ID_OFFSET=0`, `X_OFFSET=4`, `Y_OFFSET=8`. Callback đọc:

```java
int id = event.get(ValueLayout.JAVA_INT, ID_OFFSET);
int x  = event.get(ValueLayout.JAVA_INT, X_OFFSET);
int y  = event.get(ValueLayout.JAVA_INT, Y_OFFSET);
```

Các offset đo **bằng byte**. Dùng `MemoryLayout`/`PathElement` giúp code thể hiện cấu trúc và giảm lỗi cộng byte khi struct có nhiều trường/padding.

### 5.3. Vì sao cần `sizeof` và `offsetof` phía C?

FFM biết layout **bạn khai báo**, không tự đọc header C hoặc kiểm tra ABI ở runtime. Nếu C struct thực tế có padding khác, layout Java có thể đọc nhầm field. Trong ví dụ ở mục 8, thư viện C export thêm:

```c
int32_t ffm_event_size_2026(void) {
    return (int32_t) sizeof(Event);
}
int32_t ffm_event_y_offset_2026(void) {
    return (int32_t) offsetof(Event, y);
}
```

Java downcall hai hàm này rồi kiểm tra có đúng **12 byte** và offset `y=8` trước khi gửi callback pointer. Với API thật, cũng nên xác thực ABI, alignment, phiên bản struct, endian và các compiler flags `#pragma pack` nếu liên quan.

## 6. `void *user_data`: truyền trạng thái callback mà không dùng global mutable state

Một callback C thường nhận thêm `void *user_data` (hay `void *ctx`). Mục đích là truyền ngữ cảnh của caller:

```c
int32_t run_events(event_callback callback, void *user_data);
```

Ở phía Java, ta có thể cấp một vùng native cho một hệ số kiểu `int32_t`:

```java
MemorySegment context = arena.allocate(ValueLayout.JAVA_INT);
context.set(ValueLayout.JAVA_INT, 0L, 2);
```

Sau đó truyền `context` vào C như đối số thứ hai của downcall. C giữ nguyên địa chỉ và chuyển lại thành tham số thứ ba của callback. Lúc Java callback nhận `MemorySegment contextPtr`, nó thường cũng là **pointer segment zero-length**. Vì vậy:

```java
if (contextPtr.address() == 0L) {
    return -1;
}

MemorySegment contextView =
        contextPtr.reinterpret(ValueLayout.JAVA_INT.byteSize());
int factor = contextView.get(ValueLayout.JAVA_INT, 0L);
```

Đây là **trích đoạn trong callback**, không nên đọc context sau khi owner đóng arena hoặc C giữ pointer quá hạn. Trong demo, factor luôn bằng 2.

**Lợi ích của `user_data`:** nhiều callback có thể dùng cùng Java method/FunctionDescriptor nhưng giữ ngữ cảnh riêng mà không cần các static fields thay đổi liên tục.

**Điều cần phân biệt:** `user_data` là một con trỏ C tới native memory, **không phải Java object reference thông thường**. Đừng cast địa chỉ Java object thành `void*` bằng suy đoán. Nếu cần liên hệ Java object với callback, có thể dùng ID/handle trong native context và một bảng registry Java được quản lý vòng đời, nhưng không tự tạo raw pointer tới object Java trên heap.

## 7. Đọc mảng byte khi C truyền `(pointer, length)`

Bên cạnh struct, các API callback thường nhận cặp `const uint8_t *data` và `int32_t length`. Đó là **vùng byte liên tục**, không phải C string mặc định:

```c
typedef int32_t (*bytes_callback)(
        const uint8_t *bytes,
        int32_t byte_count,
        void *user_data);
```

Java target có thể có **cùng loại MethodType** với callback nhận struct pointer:

```text
(MemorySegment, int, MemorySegment) -> int
```

nhưng **semantics của argument thứ nhất khác**: ở callback dạng bytes, `byte_count` là số lượng byte của mảng, thay vì kích thước cố định `Event`.

### 7.1. Pattern đọc an toàn trong phạm vi callback

```java
if (bytesPtr.address() == 0L
        || byteCount < 0
        || byteCount > MAX_INPUT_BYTES) {
    return -1;
}
MemorySegment view = bytesPtr.reinterpret(byteCount);
byte[] copy = view.toArray(ValueLayout.JAVA_BYTE);
```

Đây là trích đoạn trong callback trả `int`; `MAX_INPUT_BYTES` là giới hạn do ứng dụng định nghĩa và native caller đáng tin phải đảm bảo pointer có ít nhất `byteCount` byte. Có thể dùng `view.get(ValueLayout.JAVA_BYTE,i)` để xử lý trực tiếp nếu không muốn copy.

**Tại sao `toArray` có ích?** Nó tạo một **`byte[]` độc lập** trong Java. Trong callback đồng bộ, C có thể truyền pointer tới một mảng cục bộ trên stack — sau khi callback return, địa chỉ ấy không còn được đảm bảo hợp lệ. Nếu Java cần giữ dữ liệu, hãy **copy nội dung trước khi return**, thay vì cache `bytesPtr` hay `view`.

Nếu nhận UTF-8 bytes:

- Phải biết rõ `length` có bao gồm byte `\0` kết thúc không.
- Nếu là **length-delimited data**, dùng giải mã theo `StandardCharsets.UTF_8` trên bytes đã copy, không cần quét tới `\0`.
- Nếu C truyền **C string null-terminated**, cần giới hạn số byte tối đa và hợp đồng về NUL, không quét vô hạn trên con trỏ zero-length.

### 7.2. Số lượng phần tử không phải byte count

Với `int32_t data[4]`, `count=4` nghĩa là **4 phần tử**, tương đương **16 byte**; `reinterpret(4)` là sai nếu muốn đọc hết mảng. Công thức cần kiểm tra overflow:

```java
long byteCount = Math.multiplyExact(
        (long) elementCount,
        ValueLayout.JAVA_INT.byteSize()
);
MemorySegment view = ptr.reinterpret(byteCount);
```

Trích đoạn giả định `elementCount` hợp lệ và `ptr` còn sống. Đơn vị đo của `MemorySegment.reinterpret` và `MemorySegment.get` offset là **byte**; đừng nhầm với array index.

## 8. Ví dụ hoàn chỉnh: C gọi Java callback để xử lý struct, buffer và context

Ví dụ thực hành sẽ tạo một shared library C export ba entry points:

- `ffm_event_size_2026()` và `ffm_event_y_offset_2026()`: xác minh ABI struct.
- `ffm_run_events_2026(callback, user_data)`: tạo ba `Event`, gọi callback Java từng event và cộng kết quả.
- `ffm_run_bytes_2026(callback, user_data)`: truyền một mảng byte và độ dài sang callback Java.

C và Java đều dùng mã `int32_t` cho giá trị, `ADDRESS` cho mọi con trỏ. C **gọi callback đồng bộ trước khi return**, không lưu function pointer vào global state. Vì thế dùng **`Arena.ofConfined()`** trong Java là hợp lý.

### 8.1. Tệp `FfmCallbackDemo.c`

```c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
    int32_t id;
    int32_t x;
    int32_t y;
} Event;

typedef int32_t (*event_callback)(
        const Event *event,
        int32_t event_bytes,
        void *user_data);

typedef int32_t (*bytes_callback)(
        const uint8_t *bytes,
        int32_t byte_count,
        void *user_data);

FFM_EXPORT int32_t ffm_event_size_2026(void) {
    return (int32_t) sizeof(Event);
}

FFM_EXPORT int32_t ffm_event_y_offset_2026(void) {
    return (int32_t) offsetof(Event, y);
}

FFM_EXPORT int32_t ffm_run_events_2026(
        event_callback callback,
        void *user_data) {

    if (callback == NULL || user_data == NULL) {
        return -1;
    }

    const Event events[] = {
        {1, 10, 20},
        {2, 30, 40},
        {3, -4, 7}
    };

    int32_t total = 0;
    const size_t count = sizeof(events) / sizeof(events[0]);

    for (size_t i = 0; i < count; ++i) {
        // events[i] còn sống trong suốt lời gọi này.
        const int32_t answer = callback(
                &events[i],
                (int32_t) sizeof(Event),
                user_data);

        // -1 là mã lỗi do ứng dụng tự chọn.
        if (answer < 0) {
            return -1;
        }
        total += answer;
    }
    return total;
}

FFM_EXPORT int32_t ffm_run_bytes_2026(
        bytes_callback callback,
        void *user_data) {

    if (callback == NULL || user_data == NULL) {
        return -1;
    }

    const uint8_t bytes[] = {2, 4, 6, 8};

    // Mảng bytes nằm trên stack, chỉ hợp lệ khi callback chạy.
    return callback(
            bytes,
            (int32_t) sizeof(bytes),
            user_data);
}
```

**Đặc điểm của C code:**

- Có macro export symbol dùng được trên Linux/macOS/Windows. Trên Windows nên build x64; các nền 32-bit có thể cần xử lý thêm calling convention và symbol decoration.
- `Event` có ba trường số `int32_t`. Java phải khai báo đúng layout và không được giả định sai padding.
- `event_callback` và `bytes_callback` là **con trỏ hàm**; C không biết `MethodHandle` hay Java object là gì.
- `events[]` và `bytes[]` là **biến cục bộ**. C chỉ truyền địa chỉ cho callback đồng bộ; Java không được giữ raw pointer để dùng sau khi C return.
- Mã lỗi `-1` là **quy ước của ví dụ**, không phải mã lỗi có sẵn của FFM/JNI.
- C không ném exception Java. Nó nhận `int32_t` từ callback rồi xử lý như một giá trị C.

### 8.2. Tệp `FfmCallbackDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;
import java.util.Arrays;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public final class FfmCallbackDemo {

    private static final StructLayout EVENT_LAYOUT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("id"),
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y")
            );

    private static final long ID_OFFSET =
            EVENT_LAYOUT.byteOffset(groupElement("id"));

    private static final long X_OFFSET =
            EVENT_LAYOUT.byteOffset(groupElement("x"));

    private static final long Y_OFFSET =
            EVENT_LAYOUT.byteOffset(groupElement("y"));

    // C callback: int32_t cb(const pointer*, int32_t length, void* ctx)
    private static final FunctionDescriptor CALLBACK_DESC =
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS
            );

    // C driver: int32_t run(callback_function_ptr, void* ctx)
    private static final FunctionDescriptor RUN_DESC =
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.ADDRESS
            );

    private FfmCallbackDemo() {
    }

    private static int factor(MemorySegment contextAddress) {
        if (contextAddress.address() == 0L) {
            throw new IllegalArgumentException("NULL user_data");
        }
        MemorySegment context = contextAddress.reinterpret(
                ValueLayout.JAVA_INT.byteSize());
        return context.get(ValueLayout.JAVA_INT, 0L);
    }

    // MethodType: (MemorySegment, int, MemorySegment) -> int
    private static int onEvent(MemorySegment eventAddress,
                               int eventBytes,
                               MemorySegment contextAddress) {
        try {
            if (eventAddress.address() == 0L
                    || eventBytes != EVENT_LAYOUT.byteSize()) {
                return -1;
            }

            // Pointer do native truyền vào có size 0.
            // C cam kết cung cấp một Event hợp lệ trong callback này.
            MemorySegment event = eventAddress.reinterpret(eventBytes);

            int id = event.get(ValueLayout.JAVA_INT, ID_OFFSET);
            int x = event.get(ValueLayout.JAVA_INT, X_OFFSET);
            int y = event.get(ValueLayout.JAVA_INT, Y_OFFSET);
            int multiplier = factor(contextAddress);

            int answer = Math.multiplyExact(
                    Math.addExact(x, y), multiplier);

            System.out.println("event id=" + id
                    + " x=" + x
                    + " y=" + y
                    + " factor=" + multiplier
                    + " result=" + answer);
            return answer;
        } catch (Throwable unexpected) {
            // Không bao giờ để Throwable thoát qua ranh giới upcall.
            // Trả sentinel lỗi theo hợp đồng C.
            return -1;
        }
    }

    private static int onBytes(MemorySegment bytesAddress,
                               int byteCount,
                               MemorySegment contextAddress) {
        try {
            if (bytesAddress.address() == 0L
                    || byteCount < 0
                    || byteCount > 1024) {
                return -1;
            }

            MemorySegment view =
                    bytesAddress.reinterpret(byteCount);

            // Snapshot Java độc lập trước khi native stack biến mất.
            byte[] copied = view.toArray(ValueLayout.JAVA_BYTE);

            int sum = 0;
            for (byte value : copied) {
                sum = Math.addExact(
                        sum, Byte.toUnsignedInt(value));
            }

            int multiplier = factor(contextAddress);
            int answer = Math.multiplyExact(sum, multiplier);

            System.out.println("bytes=" + Arrays.toString(copied)
                    + " sum=" + sum
                    + " factor=" + multiplier
                    + " result=" + answer);

            return answer;
        } catch (Throwable unexpected) {
            return -1;
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        Path path = Path.of(
                System.mapLibraryName("ffmcallbackdemo")
        ).toAbsolutePath().normalize();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup library =
                    SymbolLookup.libraryLookup(path, arena);

            MethodHandle eventSize = linker.downcallHandle(
                    library.find("ffm_event_size_2026").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            MethodHandle eventYOffset = linker.downcallHandle(
                    library.find("ffm_event_y_offset_2026").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            int nativeEventSize = (int) eventSize.invokeExact();
            int nativeYOffset = (int) eventYOffset.invokeExact();

            if (nativeEventSize != EVENT_LAYOUT.byteSize()
                    || nativeYOffset != Y_OFFSET) {
                throw new IllegalStateException(
                        "C Event ABI does not match Java layout");
            }

            System.out.println("eventBytes=" + nativeEventSize
                    + " yOffset=" + nativeYOffset);

            MethodHandle runEvents = linker.downcallHandle(
                    library.find("ffm_run_events_2026").orElseThrow(),
                    RUN_DESC
            );

            MethodHandle runBytes = linker.downcallHandle(
                    library.find("ffm_run_bytes_2026").orElseThrow(),
                    RUN_DESC
            );

            MethodType callbackType = MethodType.methodType(
                    int.class,
                    MemorySegment.class,
                    int.class,
                    MemorySegment.class
            );

            MethodHandle eventTarget =
                    MethodHandles.lookup().findStatic(
                            FfmCallbackDemo.class,
                            "onEvent",
                            callbackType
                    );

            MethodHandle bytesTarget =
                    MethodHandles.lookup().findStatic(
                            FfmCallbackDemo.class,
                            "onBytes",
                            callbackType
                    );

            MemorySegment eventStub = linker.upcallStub(
                    eventTarget, CALLBACK_DESC, arena);
            MemorySegment bytesStub = linker.upcallStub(
                    bytesTarget, CALLBACK_DESC, arena);

            MemorySegment context =
                    arena.allocate(ValueLayout.JAVA_INT);
            context.set(ValueLayout.JAVA_INT, 0L, 2);

            // Java -> C -> Java, đồng bộ trên cùng luồng.
            int eventTotal = (int) runEvents.invokeExact(
                    eventStub, context);

            if (eventTotal < 0) {
                throw new IllegalStateException(
                        "Event callback failed");
            }
            System.out.println("events total=" + eventTotal);

            int bytesTotal = (int) runBytes.invokeExact(
                    bytesStub, context);

            if (bytesTotal < 0) {
                throw new IllegalStateException(
                        "Bytes callback failed");
            }
            System.out.println("bytes total=" + bytesTotal);

            // C đã trả về: không giữ con trỏ Event hoặc bytes.
        }
        // Arena đóng: function pointers, context và
        // thư viện gắn với lookup không được dùng tiếp.
    }
}
```

### 8.3. Giải thích code Java theo từng bước

1. **`EVENT_LAYOUT` và offsets**: mô tả 3 trường `id`/`x`/`y` theo C; dùng `byteOffset(groupElement(...))` để không hard-code offset trong callback.
2. **`CALLBACK_DESC`**: khai báo callback target `int(MemorySegment,int,MemorySegment)`; khi C gọi function pointer, JVM sẽ chuyển 3 tham số ABI này sang Java theo descriptor.
3. **`RUN_DESC`**: khai báo C driver `int(void*,void*)`. C không thực sự xem tham số thứ nhất là data pointer, mà xem nó như **function pointer**, nhưng carrier Java đều là `ADDRESS`.
4. **`libraryLookup(Path,Arena)`**: mở đúng shared library do ta biên dịch. Không cần Java `native` method, `javac -h` hoặc `JNI_OnLoad`.
5. **ABI validation**: Java gọi `ffm_event_size_2026` và `ffm_event_y_offset_2026` trước khi nhận dữ liệu; nếu layout sai, từ chối thay vì âm thầm đọc sai field.
6. **`findStatic`**: tạo MethodHandle trỏ tới `onEvent` và `onBytes`; cả hai dùng cùng dạng tham số nhưng có logic giải mã dữ liệu khác.
7. **`upcallStub`**: tạo hai function pointers. C nhận chúng trong `runEvents`/`runBytes`, không phải nhận Java MethodHandle như một pointer JVM tùy ý.
8. **`context`**: cấp phát 4 byte native, chứa `int=2`, truyền qua `void *user_data`. C chỉ trả địa chỉ đó lại cho Java callback.
9. **`onEvent`**: nhận raw pointer và độ dài, xác minh `NULL`/size, mở rộng bounds bằng `reinterpret` rồi đọc 3 số. Tổng `(x+y)*2` được trả về C.
10. **`onBytes`**: xác thực length và upper bound 1024, copy mảng vào `byte[]` bằng `toArray`, cộng unsigned bytes rồi nhân hệ số.
11. **`catch(Throwable)`**: callback luôn trả `int` mã lỗi nếu Java ném một lỗi không mong đợi; không để `Throwable` vượt qua upcall boundary.
12. **Arena/Scope**: giữ `library`, `eventStub`, `bytesStub`, `context` còn sống **đến sau khi cả hai C calls trả về**. Chỉ cuối `try` mới đóng arena.

Đây là ví dụ **callback đồng bộ**. Nếu thư viện C lưu con trỏ để gọi từ thread khác về sau, mô hình này **không đủ**, xem mục 11.

### 8.4. Biên dịch/chạy trên Linux

Điều kiện: JDK 22+ và GCC/Clang tương ứng ABI/JVM, chạy trong thư mục có cả hai file nguồn.

```bash
gcc -std=c11 -O2 -shared -fPIC \
    FfmCallbackDemo.c -o libffmcallbackdemo.so

javac FfmCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

`SymbolLookup.libraryLookup(Path,Arena)` nhận path tuyệt đối được tạo từ `System.mapLibraryName`, do đó **không cần `-Djava.library.path=.`** trong bài này.

Nếu `gcc` và `javac` target kiến trúc khác nhau, Java sẽ không thể load shared library. Ví dụ x86_64 JVM cần một `libffmcallbackdemo.so` có ABI/architecture tương thích x86_64.

### 8.5. Biên dịch/chạy trên macOS

Dùng Clang và JDK 22+ thích hợp Apple Silicon hoặc Intel:

```bash
clang -std=c11 -O2 -dynamiclib \
    FfmCallbackDemo.c -o libffmcallbackdemo.dylib

javac FfmCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

Trên macOS, filename từ `System.mapLibraryName("ffmcallbackdemo")` thường là `libffmcallbackdemo.dylib`. Bảo đảm toolchain, binary và JDK dùng cùng CPU architecture; code ví dụ không phụ thuộc JNI headers.

### 8.6. Biên dịch/chạy trên Windows x64

Mở **x64 Native Tools Command Prompt** của Visual Studio, thiết lập JDK 22+ x64 trong `PATH`, sau đó chạy trong thư mục có hai file nguồn:

```bat
cl /nologo /O2 /LD FfmCallbackDemo.c /link /OUT:ffmcallbackdemo.dll

javac FfmCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

`FFM_EXPORT` trên Windows dùng `__declspec(dllexport)` để các tên `ffm_*` có thể được lookup. Nên dùng x64 để tránh các khác biệt calling convention/export-name decoration của Windows x86. Path native library của chương trình sẽ là `ffmcallbackdemo.dll` nằm ở thư mục làm việc.

### 8.7. Stdout chính xác khi chạy thành công

```text
eventBytes=12 yOffset=8
event id=1 x=10 y=20 factor=2 result=60
event id=2 x=30 y=40 factor=2 result=140
event id=3 x=-4 y=7 factor=2 result=6
events total=206
bytes=[2, 4, 6, 8] sum=20 factor=2 result=40
bytes total=40
```

**Giải thích phép tính:**

- `sizeof(Event)=12`, `offsetof(Event,y)=8` phù hợp với Java `EVENT_LAYOUT` và `Y_OFFSET`.
- Event 1: `(10+20)*2=60`.
- Event 2: `(30+40)*2=140`.
- Event 3: `(-4+7)*2=6`.
- C cộng ba kết quả: `60+140+6=206`.
- Byte buffer chứa `2,4,6,8`; Java copy ra mảng mới, tính tổng unsigned bytes `20`, nhân hệ số 2 thành `40`.
- Mỗi `runEvents/runBytes` gọi callback ngay trước khi return, nên các dòng log xuất hiện theo thứ tự này trong **đường đi thành công**.
- Không có `System.out` trong C; toàn bộ stdout hiển thị do Java chủ động in.

Nếu chương trình báo lỗi ABI mismatch trên target khác, **đừng bỏ validation chỉ để chạy**: cần thay đổi `StructLayout` theo C ABI thật hoặc sửa C build target cho khớp.

## 9. Những điểm then chốt khi đọc tham số C từ Java

### 9.1. Giá trị primitive khác với pointer

C callback:

```c
int32_t cb(const Event *event, int32_t event_bytes, void *ctx);
```

tương ứng:

```java
static int cb(MemorySegment eventPtr,
              int eventBytes,
              MemorySegment ctxPtr) { ... }
```

`eventBytes` đã là **`int` Java**: không cần `reinterpret` để đọc nó. Ngược lại, `eventPtr` và `ctxPtr` là địa chỉ; phải biết vùng backing có bao nhiêu byte trước khi dereference.

**Sai:** gọi `eventPtr.get(JAVA_INT,0)` khi segment có size 0, rồi gán lỗi cho JDK. Đó là hệ quả cố ý của bounds checking.

### 9.2. Pointer truyền vào không mang theo lifetime thật

Theo Javadoc FFM, pointer truyền vào upcall có thể được biểu diễn bằng zero-length segment liên kết với **global scope**. Global scope đó **không khẳng định vùng nhớ của C sẽ tồn tại mãi**. Scope của Java wrapper và lifetime thật của C allocation **là hai chuyện khác nhau**.

Trong ví dụ, C truyền địa chỉ của `Event events[]`/`uint8_t bytes[]` sống trên native stack. Bạn chỉ được đọc nó trong chính callback đồng bộ; nếu cần xử lý sau, **copy bytes hoặc chuyển thành Java DTO** khi C vẫn bảo đảm vùng nhớ hợp lệ.

### 9.3. Byte order và alignment

`ValueLayout.JAVA_INT` truy cập `int` 4 byte với byte order theo layout của platform. Nếu C struct được biên dịch trên cùng native ABI và không đổi định dạng, đây là cách hợp lý. Khi đọc buffer từ network/file có thứ tự byte khác, cần `withOrder(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)` tương ứng.

Một `MemorySegment.reinterpret(length)` không tự sửa alignment. Đối với trường C không được căn chỉnh hoặc packed struct, dùng layout có alignment thích hợp (ví dụ `JAVA_INT_UNALIGNED`) **chỉ khi** C ABI thực sự quy định packed data. Không chọn unaligned để che lỗi bố trí struct.

### 9.4. `const` trong C không được Java tự thực thi

`const Event *` có ý nghĩa về cách caller/callee C được phép dùng pointer; `MemorySegment` Java không tự trở thành read-only chỉ từ metadata `ADDRESS`. Vì thế Java callback phải **tôn trọng hợp đồng native**: nếu tham số C là `const`, chỉ đọc.

Nếu cần phòng ngừa sửa vô ý trong Java code, có thể tạo read-only view:

```java
MemorySegment event = eventPtr
        .reinterpret(eventBytes)
        .asReadOnly();
```

Đây là trích đoạn trong callback sau khi đã kiểm tra pointer/size. `asReadOnly` ngăn thao tác ghi thông qua view này; nó không xác thực con trỏ C hoặc đóng băng dữ liệu nếu thread C khác sửa cùng vùng.

## 10. Tùy chọn nâng cao: `AddressLayout.withTargetLayout`

Ngoài cách `reinterpret` trong callback, có thể tạo **`AddressLayout` với target layout**. Ý tưởng:

```java
var eventAddressLayout =
        ValueLayout.ADDRESS.withTargetLayout(EVENT_LAYOUT);

FunctionDescriptor describedCallback =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                eventAddressLayout,
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS
        );
```

Đây là **trích đoạn** với `EVENT_LAYOUT` đã khai báo. Theo Javadoc `Linker.upcallStub`, nếu đối số callback thuộc `AddressLayout` có target layout `T`, segment truyền cho Java target có thể được biểu diễn với size `T.byteSize()` thay vì 0.

**Không đồng nghĩa an toàn tuyệt đối.** `withTargetLayout` là restricted/unsafe; bạn đang khẳng định rằng pointer thực sự trỏ tới đối tượng hợp lệ có size và alignment phù hợp. Java runtime không thể tự kiểm chứng native pointer, và khi C chỉ truyền buffer có kích thước động thì **không thể** áp dụng một target layout cố định tùy ý.

Đối với API C có tham số `pointer + length` động như callback bytes, dùng `ADDRESS` cộng kiểm tra `length` rồi `reinterpret(length)` có thể rõ nghĩa hơn.

### 10.1. Khi nào dùng target layout?

- Tham số luôn trỏ tới một struct cố định và ABI được xác thực.
- Muốn hạn chế boilerplate `reinterpret(EVENT_LAYOUT.byteSize())`.
- Có thể kiểm tra `sizeof` và offsets ở native side trước.
- Không dùng nếu pointer là optional/NULL hay trỏ tới vùng có hình dạng thay đổi mà chưa xác minh.

### 10.2. `MemoryLayout` không phải serializer C tự động

Bố trí `StructLayout` trong Java chỉ mô tả **hình dạng bytes**. Nó không tự gọi constructor C, không tự quản lý lifetime của C allocation, không biến pointer thành object graph Java, và không kiểm tra `ABI version` trong shared library. Muốn model một struct phức tạp trong Java, phải thiết kế schema đúng hoặc tạo DTO Java sau khi đọc.

## 11. Nếu thư viện C lưu callback để gọi sau: đổi mô hình vòng đời

Ví dụ ở mục 8 **không lưu callback**. Điều này rất quan trọng vì `Arena.ofConfined()` và các địa chỉ stack C chỉ sống đúng phạm vi đồng bộ của downcall.

Giả sử C API có dạng:

```c
void register_callback(event_callback callback, void *user_data);
void unregister_callback(void);
```

Đây là **mẫu C minh họa**, không có implementation trong demo chạy. Thư viện có thể gọi callback từ một native worker/thread bất kỳ **sau khi `register_callback` đã trả về**. Khi đó tuyệt đối không dùng pattern `try(Arena.ofConfined()) { register(...); }` rồi đóng arena trước khi callback kết thúc.

### 11.1. Mô hình lifecycle cho callback bất đồng bộ

```text
Java owner khởi tạo
    |
    | tạo Arena.ofShared()
    | cấp phát native context có lifetime dài
    | tạo upcallStub bằng shared arena
    | register_callback(stub, context)
    v
ACTIVE
    |
    | C có thể phát callback từ native threads
    | Java callback phải không throw, thread-safe
    | dữ liệu C phải còn sống trong từng callback
    v
STOPPING
    |
    | yêu cầu C ngừng tạo callback mới
    | unregister_callback / stop_native_threads
    | chờ mọi in-flight callback hoàn tất
    v
SAFE_TO_CLOSE
    |
    | đóng arena (giải phóng stub/context)
    v
CLOSED
```

Đây là **mô hình ứng dụng**, không phải một API lifecycle tự có của Java FFM. `Arena.ofShared()` cho phép access đa thread tương ứng scope, nhưng **không tự tạo cơ chế stop/unregister/join**. Nếu C giữ function pointer sau khi arena đóng, một lần gọi C→địa chỉ đã free có thể làm JVM crash.

### 11.2. Một callback có thể chạy trên native thread khác

Một số thư viện C gọi callback đồng bộ ngay trên thread Java dùng để downcall; một số thư viện khác dùng thread pool tự tạo. Phải nghiên cứu hợp đồng thread của thư viện:

- Callback có thể đồng thời chạy nhiều instance không?
- Callback có được reentrant (callback lại gọi API C) không?
- Callback được phép block bao lâu?
- Thread native có thể kết thúc trong khi Java callback đang xử lý không?
- Ai dừng worker và chờ tất cả callback trước khi đóng arena?
- Java callback có dùng ThreadLocal, security context, class loader, virtual thread assumption hay UI thread không?

Không giả định callback luôn chạy trên Java `main`. Các state Java dùng chung nên được đồng bộ (`AtomicInteger`, queue, locks...); tránh giữ locks qua callback nếu callback có thể gọi ngược native và tạo vòng chờ.

### 11.3. Đừng trộn `std::thread::detach` với FFM callback lifetime

Thư viện C++ có thể tạo background threads rồi tách chúng khỏi `std::thread` object bằng `detach()`. Điều đó chỉ bỏ khả năng `join` qua object ấy, **không** đảm bảo callback đã ngừng và **không** kéo dài FFM upcall stub. Với callback bất đồng bộ, nên có **unregister + stop + quiescence acknowledgment** hoặc một contract shutdown tương đương.

### 11.4. User data được lưu trữ lâu dài

Nếu C giữ `void *user_data` sau khi `register_callback`, context cũng phải sống tới khi C xác nhận sẽ không dùng nữa. Không truyền địa chỉ của biến C stack đã ra khỏi scope hoặc Java native arena sẽ đóng sớm. Nếu muốn đưa Java object làm context, dùng một cơ chế ID/registry ổn định và cleanup đúng lúc; không truyền raw Java object pointer vào C.

## 12. Java exception trong upcall là tình huống nguy hiểm

Điểm khác với callback Java thông thường: **Javadoc `Linker.upcallStub` cảnh báo target MethodHandle không được ném exception ra ngoài**. Nếu exception thoát từ upcall target, **JVM có thể chấm dứt đột ngột**; không có cách bình thường để C `try/catch` Java exception như Java code.

Vì thế callback code của ví dụ:

```java
private static int onEvent(/* các tham số */) {
    try {
        // validate và đọc dữ liệu
        // ...
        return computedResult;
    } catch (Throwable unexpected) {
        return -1;
    }
}
```

Đây là **mẫu ý tưởng**, không phải Java method độc lập do danh sách tham số đã rút gọn. Mục đích của `catch(Throwable)` trong callback là **ngăn Java Throwable vượt qua ranh giới ABI**; không nên sao chép thói quen “bắt hết Throwable” vào code Java thông thường. Trên ứng dụng production, cần báo lỗi vào kênh logging/telemetry chịu lỗi, đưa mã lỗi rõ ràng về C và quan sát kết quả đó ở Java caller. Tránh logging gây lỗi rồi lại throw tiếp khỏi callback.

### 12.1. Phải thống nhất mã lỗi giữa Java và C

Ví dụ chọn `-1` là lỗi:

- Java callback trả `-1` nếu pointer/size không hợp lệ hoặc có exception.
- C `ffm_run_events_2026` kiểm tra callback result, thấy âm thì dừng và trả `-1`.
- Java sau downcall thấy tổng âm, ném `IllegalStateException` **ở phía Java gọi downcall**, nơi exception bình thường được phép xử lý.

Nếu API C thật cho phép callback trả số âm là kết quả hợp lệ, không thể tự chọn `-1` làm sentinel. Phải theo thiết kế C API: có thể có tham số `error_code*`, boolean success, callback `void` và result buffer, hoặc state trong `user_data`.

### 12.2. Không gọi lại Java logic nặng bên trong callback khi chưa hiểu contract

Một callback chạy trong native thread có thể xảy ra khi C đang giữ mutex hoặc đang xử lý signal. Gọi Java code nặng, blocking I/O, synchronized methods hoặc callback ngược vào chính thư viện C có thể gây **deadlock/reentrancy problems**.

Ưu tiên callback ngắn, validate nhanh và đẩy dữ liệu sang queue/worker Java khi C API cho phép. Nếu cần giữ payload sau callback, **copy vào Java-owned data** trước khi return. Trong môi trường low-latency, đo chi phí chuyển Java↔C↔Java thay vì giả định upcall miễn phí.

## 13. Vấn đề về callback pointer và `Arena`

### 13.1. Arena sở hữu stub

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment stub =
            linker.upcallStub(callbackHandle, descriptor, arena);
    // C chỉ được dùng stub trong khoảng mà arena sống.
}
// Bên ngoài, không được truyền stub cho C để gọi tiếp.
```

Đây là trích đoạn với `linker`/`callbackHandle`/`descriptor` hợp lệ. `MemorySegment` đại diện function pointer **không phải** một tham chiếu bất tử. Khi arena đóng, vùng code stub sẽ bị hủy. Việc Java vẫn còn giữ biến `stub` không làm địa chỉ đó hợp lệ trở lại.

### 13.2. Giữ cả native library còn sống

Nếu Java tạo downcall từ `SymbolLookup.libraryLookup(path, arena)`, library lookup cũng có lifecycle phụ thuộc arena. Không chỉ stub/context, **địa chỉ hàm C** và MethodHandle xuống C cũng cần thư viện còn nạp.

Vì vậy nên sử dụng một owner quản lý:

- Arena của native library.
- Upcall stub và native context allocations.
- Các downcall handles.
- Trạng thái `RUNNING/STOPPING/CLOSED`.
- Cơ chế unregister và chờ in-flight callback nếu API bất đồng bộ.

Đừng đóng arena trước khi C API thực sự không còn hoạt động; đừng phát sinh downcall sau khi owner đã đóng.

### 13.3. `Arena.ofAuto` không phù hợp để phó mặc callback dài hạn

Nếu callback được lưu trong C và Java không còn reference rõ ràng, automatic arena có thể được GC thu hồi ở thời điểm không kiểm soát. Với callback registration cần lifetime tường minh, dùng arena có owner và bước đóng cụ thể; `Arena.ofShared()` là lựa chọn nếu native threads khác cần truy cập. Tham số từ C nằm trên stack vẫn tuân thủ thời gian sống riêng của C, không được “kéo dài” chỉ bằng shared arena.

## 14. Phân biệt truyền pointer, truyền struct by value và truyền con trỏ tới pointer

Không phải header C nào cũng dùng cùng ABI.

### 14.1. Pointer to struct

```c
void notify(const Event *event);
```

Java callback nhận `MemorySegment` đại diện **địa chỉ của struct**, rồi đọc từng field sau khi xác minh bounds. Với descriptor: `ofVoid(ADDRESS)`.

### 14.2. Struct by value

```c
void notify(Event event);
```

Đây là **truyền struct by value**, không phải pointer. ABI có thể chia struct qua registers/stack tùy architecture. FFM dùng **`GroupLayout`** trong descriptor và carrier tương ứng có thể khác, ví dụ một `MemorySegment` chứa bản sao/struct data theo quy tắc linker. **Không** thay một struct by-value bằng `ADDRESS` chỉ vì thấy cả hai đều chứa bytes.

### 14.3. Pointer to pointer

```c
void notify(Event **event_ptr);
```

Tham số là **địa chỉ của một ô nhớ chứa địa chỉ Event**, không phải trực tiếp địa chỉ của Event. Java phải có layout/scope phù hợp để đọc một `ADDRESS` tại địa chỉ đó, rồi tiếp tục theo pointer được đọc. Nếu xử lý như `Event*`, bạn sẽ diễn giải bytes của một con trỏ thành id/x/y và gây lỗi.

### 14.4. Arrays và `char*`

`const uint8_t *bytes, int32_t length` là **mảng byte có độ dài tường minh**. `const char *text` có thể là **C string kết thúc NUL**, nhưng không phải mọi `char*` đều là string. Không sử dụng `getString(0)` hoặc đọc không giới hạn trừ khi hợp đồng dữ liệu, NUL termination và bounds đã được chứng minh hợp lệ.

## 15. Truyền state Java mà không có `void *ctx`

Một số C API chỉ nhận:

```c
typedef int32_t (*simple_callback)(int32_t value);
void register_simple(simple_callback cb);
```

Không có `void *user_data`. Java vẫn có thể tạo một **bound MethodHandle** để gắn một Java object/state vào callback target:

```java
// Ví dụ ý tưởng: state object cần được giữ sống
// bởi owner của callback registration.
MethodHandle bound = MethodHandles.insertArguments(
        instanceMethodHandle, 0, stateObject);

MemorySegment stub = linker.upcallStub(
        bound,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT, ValueLayout.JAVA_INT),
        arena);
```

Đây là **trích đoạn minh họa**, yêu cầu `instanceMethodHandle` có tham số đầu tương ứng `stateObject` và method type sau bind là `(int)int`. `MethodHandles.insertArguments` không cấp cho C một Java object pointer; `upcallStub` làm bridge qua MethodHandle đã bound.

So sánh:

| Phương án | C API cần `void *user_data`? | C có giữ Java object trực tiếp? | Vấn đề lifecycle |
| --- | --- | --- | --- |
| Native context `Arena.allocate` | Có | Không | Giữ context memory tới khi callback ngừng |
| Java bound MethodHandle | Không | Không | Owner phải giữ stub/state còn sống |
| ID registry trong Java | Thường có | Không | C giữ ID, Java tra ID có đồng bộ và cleanup |
| Raw Java object address tự cast | Không được khuyến nghị | Sai mô hình | GC có thể di chuyển object, unsafe |

## 16. Debug upcall khi có lỗi

### 16.1. Không tìm thấy symbol C

Nếu `library.find("ffm_run_events_2026")` trả empty:

- Kiểm tra file `.so`/`.dll`/`.dylib` đúng tên.
- Kiểm tra symbol export bằng `nm -D` (Linux), `nm -gU` (macOS), `dumpbin /EXPORTS` (Windows).
- Kiểm tra C++ name mangling và visibility; ví dụ C của bài dùng macro `FFM_EXPORT`.
- Đảm bảo build đúng bản binary đang được Java load; không chỉ nhìn vào header C.

### 16.2. FFM báo `WrongMethodTypeException`

Thường do `MethodHandle` không khớp `FunctionDescriptor`, `invokeExact` sai kiểu hoặc nhầm callback signature với driver signature. Trong ví dụ:

```text
C callback: int32_t (*)(Event*, int32_t, void*)
Upcall:      (MemorySegment, int, MemorySegment) -> int

C driver:   int32_t (*)(callback_ptr, void*)
Downcall:    (MemorySegment, MemorySegment) -> int
```

Không được tạo callback target `(MemorySegment,long,MemorySegment)->int` trong khi `event_bytes` là `int32_t`.

### 16.3. Callback nhận pointer nhưng đọc bị IndexOutOfBoundsException

Lý do phổ biến: pointer segment size 0, chưa `reinterpret` hoặc `AddressLayout` không có target layout. Trước khi đọc, phải có hợp đồng kích thước và lifetime hợp lệ. Không sửa bằng cách bịa một size cực lớn.

### 16.4. Crash JVM sau khi callback đã kết thúc

Nguyên nhân khả dĩ:

- C giữ function pointer tới upcall stub nhưng `Arena` đã đóng.
- Java giữ pointer tới C stack data và đọc sau khi callback return.
- ABI sai (nhầm struct value với struct pointer, kiểu số/độ rộng tham số sai, calling convention không khớp).
- Java exception thoát khỏi upcall target.
- Native C code viết vượt bounds, hoặc trả pointer đã free.

Khi JVM crash, không nên đoán là lỗi Java bình thường. Kiểm tra C ABI, scope ownership và log crash/hotspot error file; dùng ASan/UBSan hoặc công cụ native debugger khi môi trường cho phép.

### 16.5. Lỗi native access

`java.lang.IllegalCallerException` có thể xảy ra khi caller chưa có quyền dùng restricted API. Với ứng dụng classpath trên JDK 22+, chạy `--enable-native-access=ALL-UNNAMED`. Với named module, cấp quyền đúng module gọi restricted methods. **Không** dùng flag này như một cách bỏ qua kiểm tra pointer/size.

### 16.6. Callback chạy nhiều lần hoặc nhiều thread

Nếu C cho phép concurrent callback, Java target phải thread-safe. Những biến `static` mutable dùng chung cần đồng bộ. Nếu C callback được gọi từ thread khác và arena là confined, cần xem lại hợp đồng scope; một **shared arena** là yêu cầu thường gặp cho callback bất đồng bộ xuyên thread. Tránh đóng shared arena khi vẫn còn callback đang chạy.

## 17. Các lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Truyền `MethodHandle` trực tiếp cho C | Không phải native function pointer | Dùng `Linker.upcallStub` và truyền `MemorySegment` stub |
| Dùng cùng `FunctionDescriptor` cho C driver và callback khi chữ ký khác | Sai ABI | Mô tả hai signatures riêng |
| Trả `long` từ Java target khi C callback trả `int32_t` | MethodType không khớp | Dùng `JAVA_INT` và `int` |
| Không xét pointer zero-length | `IndexOutOfBoundsException` | Kiểm tra size/NULL rồi `reinterpret` hợp đồng |
| Dùng `reinterpret` với số byte tùy ý | Crash/memory corruption | Tin cậy native provider, xác minh size/lifetime |
| Đọc `Event*` như một Java object | Không có marshaling tự động | Dùng `StructLayout`/offsets để đọc bytes |
| Quên `void *user_data` | Callback không có context | Cấp phát native context và truyền sang C |
| Truyền địa chỉ Java heap object giả làm native pointer | Vi phạm GC/lifetime | Dùng native context hoặc Java registry |
| Giữ pointer tới C stack buffer sau return | Use-after-free | Copy dữ liệu trong callback |
| Đóng Arena ngay sau đăng ký callback bất đồng bộ | C gọi stub đã bị hủy | Unregister, chờ in-flight callbacks rồi đóng |
| Callback ném Java exception ra ngoài | JVM có thể chấm dứt đột ngột | Bắt lỗi trong target và trả status C hợp lệ |
| Bỏ kiểm tra `sizeof/offsetof` | Đọc sai fields | Đối chiếu struct layout với ABI C |
| Gọi `getString` trên `uint8_t *` không rõ NUL | Đọc quá giới hạn | Xử lý theo pointer + length và charset |
| Tin rằng `const` là read-only Java memory | Có thể sửa vùng C trái contract | Chỉ đọc, cân nhắc `asReadOnly` |
| Dùng confined Arena với callbacks từ worker C khác | Thread access lỗi | Shared arena và lifecycle synchronization |
| C/Java dùng khác compiler/architecture | Load/ABI lỗi | Build cùng architecture/JDK phù hợp |
| Xem FFM upcall là JNI `Java_Class_method` | Nhầm hai cơ chế | FFM dùng MethodHandle và function pointer |
| Quên cấp native access | Restricted operation bị từ chối | Cấu hình `--enable-native-access` đúng module |

## 18. Bài tập thực hành mở rộng

**Bài tập 1 — Đọc thêm trường `timestamp`:** Thêm `int64_t timestamp` vào `Event` của C và `JAVA_LONG` vào Java `StructLayout`. Tính lại padding/alignment, dùng `offsetof` trong C để kiểm chứng trước khi dereference. So sánh các ABI Windows/Linux.

**Bài tập 2 — Payload chứa số âm:** Đổi `bytes[]` thành các byte như `{0x80, 0xFF}`. Java `byte` là signed; dùng `Byte.toUnsignedInt` để tính 128, 255 thay vì -128, -1. Viết output rõ giá trị logical unsigned.

**Bài tập 3 — Callback trả lỗi:** Thay C truyền `event_bytes=0` một lần. Callback Java cần trả `-1`, C dừng và Java caller phát hiện `IllegalStateException` sau downcall. Không để exception thoát qua upcall boundary.

**Bài tập 4 — Hai callback dùng chung context:** Giữ `factor=2` rồi đổi thành 3 trước lời gọi `ffm_run_bytes_2026`. Kết quả event vẫn là 206 nhưng bytes result trở thành `60`; giải thích vì C chỉ chuyển lại địa chỉ context mà không copy giá trị.

**Bài tập 5 — Callback bất đồng bộ:** Thiết kế C `register_callback` + `unregister_callback` + `join_native_thread`. Ở Java, dùng `Arena.ofShared()`, một lifecycle owner và stop barrier, không đóng arena cho đến khi C xác nhận không còn callback. Đây là bài tập **thiết kế**, không phải thay vài dòng trong demo đồng bộ.

**Bài tập 6 — Chuyển `Event` thành Java record:** Định nghĩa `record EventDto(int id, int x, int y) {}`, đọc fields trong callback rồi copy sang DTO Java. Không giữ raw `Event*`; cho phép xử lý DTO sau khi callback return.

## 19. Checklist trước khi giao production FFM callback

1. Xác nhận **JDK 22+** (hoặc điều chỉnh API theo JDK đích), và native access được cấp đúng module.
2. Lấy chữ ký callback từ **C header**: return, tham số, pointer/value, calling convention và enum/struct width.
3. Tạo `FunctionDescriptor` chính xác cho **upcall callback** và **downcall C driver**.
4. `MethodHandle` Java target khớp chính xác carrier types và không để exception thoát.
5. Tạo stub qua `Linker.upcallStub` với `Arena` sở hữu rõ ràng.
6. Truyền stub `MemorySegment` qua tham số `ADDRESS` của C, không truyền Java object/raw JVM pointer.
7. Với pointer data, xác minh NULL, byte length, overflow, alignment, struct layout và native lifetime trước khi `reinterpret`/đọc.
8. Với `void* user_data`, xác định owner memory/context, giữ sống suốt callback và tránh global mutable state thiếu đồng bộ.
9. Nếu C truyền stack data, **copy trong callback** trước khi trả; không leak raw pointer.
10. Nếu C giữ callback dài hạn, có register/unregister/stop/join/quiescence trước khi đóng arena.
11. Nếu callback chạy đa thread, dùng shared arena phù hợp và bảo đảm callback logic thread-safe.
12. Kiểm tra giá trị/mã lỗi C sau downcall, logging, crash diagnostics và test với native inputs sai.
13. Biên dịch C shared library có exported symbols, dùng đúng OS/architecture và xác minh ABI thực tế.
14. Không nhầm FFM upcall với JNI `AttachCurrentThread`, Java `native` declaration hoặc `JNI_OnLoad`.
15. Chạy integration tests cả success, NULL pointer, wrong length, callback error và shutdown path.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `nativeLinker`, `downcallHandle`, `upcallStub`, quy tắc ABI, scope và lưu ý exception trong upcall target.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): zero-length segments khi truyền pointer vào upcall, restricted `reinterpret`, `toArray`, `get` và scope.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): mô tả return/argument layouts.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared scope, cấp phát context và giải phóng upcall stub.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): struct layout, group path và byte offsets.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): tra ký hiệu từ shared library.
- [OpenJDK — JEP 454](https://openjdk.org/jeps/454): FFM API ổn định trong JDK 22.