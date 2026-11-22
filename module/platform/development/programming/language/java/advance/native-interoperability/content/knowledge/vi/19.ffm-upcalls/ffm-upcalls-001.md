# Hàm gọi lại (callback), con trỏ hàm và khái niệm upcall trong Java FFM

## Mục tiêu học tập

Khi Java gọi thư viện C bằng **Foreign Function & Memory API (FFM)**, chiều đi quen thuộc là từ Java sang native: **downcall**. Nhưng nhiều API C lại muốn nhận **con trỏ hàm** để sau đó gọi ngược vào code của ứng dụng, chẳng hạn comparator của `qsort`, listener nhận sự kiện, hoặc callback báo hoàn tất một tác vụ. Khi code native gọi ngược đến logic Java, quá trình đó được gọi là **upcall**.

FFM cho phép biến một **Java `MethodHandle`** thành một **native function pointer** thông qua `Linker.upcallStub`. Đây không phải phép ép Java object thành địa chỉ máy, mà là việc JVM tạo **upcall stub** có thể được C gọi theo ABI được khai báo.

Sau bài này, bạn sẽ:

- Phân biệt callback, C function pointer, downcall, upcall và upcall stub.
- Đọc prototype C có tham số `int (*comparator)(const void *, const void *)`.
- Ghép đúng `MethodHandle`, `FunctionDescriptor`, `Linker`, `Arena` và `ValueLayout.ADDRESS`.
- Tạo/trao function pointer cho native code và giải thích lifetime của upcall stub.
- Chạy một ví dụ Java gọi C `qsort`, trong đó C gọi lại comparator viết bằng Java.
- Nhận diện lỗi ABI, signature, callback exception, pointer bounds, race, callback registration bất đồng bộ, shutdown và ownership.

**Phiên bản:** ví dụ dùng `java.lang.foreign` **API chính thức từ JDK 22+** (JEP 454), được chạy thử bằng **JDK 24**. **JDK 17** có FFM incubator với package và API khác nên không chạy nguyên văn ví dụ này. `upcallStub` là restricted method, cần **native-access permission**.

## 1. Callback và function pointer trong C là gì?

Trong C, một hàm có thể nhận con trỏ tới hàm khác như một tham số. Ví dụ tiêu biểu là hàm `qsort` trong thư viện C chuẩn:

~~~c
#include <stdlib.h>

void qsort(void *base,
           size_t nmemb,
           size_t size,
           int (*compar)(const void *a, const void *b));
~~~

Đây là **prototype**, không phải định nghĩa lại hàm `qsort` trong chương trình. `qsort` nhận một vùng các phần tử cần sắp xếp, số phần tử, kích thước mỗi phần tử, và **con trỏ hàm comparator**.

Phân tích từng tham số:

| Tham số C | Vai trò |
| --- | --- |
| `void *base` | Địa chỉ đầu vùng chứa các phần tử |
| `size_t nmemb` | Số phần tử trong mảng |
| `size_t size` | Kích thước **mỗi phần tử** tính bằng byte |
| `int (*compar)(const void *, const void *)` | Một **địa chỉ của hàm** có thể nhận hai pointers và trả một `int` |

Khi `qsort` thực hiện sắp xếp, nó gọi con trỏ hàm `compar` để biết thứ tự các phần tử. Theo hợp đồng `qsort`, comparator phải trả số **âm** nếu phần tử thứ nhất nhỏ hơn phần tử thứ hai, **0** nếu bằng nhau, và số **dương** nếu lớn hơn. Không cần trả đúng -1, 0, 1; chỉ cần dấu của kết quả phù hợp.

C viết comparator thường trông như:

~~~c
#include <stdint.h>
#include <string.h>

int compare_i32(const void *a, const void *b) {
    int32_t left;
    int32_t right;
    memcpy(&left, a, sizeof left);
    memcpy(&right, b, sizeof right);

    return (left > right) - (left < right);
}
~~~

Đoạn trên là **C function snippet**, minh họa callback thông thường. `memcpy` giúp đọc hai giá trị mà không phụ thuộc vào phép cast gây vi phạm alignment; ví dụ giả định các phần tử là `int32_t` theo format đã định nghĩa. Không dùng `return left - right;` khi chưa xử lý overflow của số nguyên.

Nếu Java muốn giao comparator của chính mình cho `qsort`, C **không hiểu** Java `Comparator<Integer>` hay `java.lang.invoke.MethodHandle`. C đòi một **function pointer đúng ABI**. Vì vậy cần cầu nối upcall stub.

## 2. Ba hướng gọi: downcall, upcall và callback registration

~~~text
Java application                  Native C library
----------------                  ----------------
Java main
    |
    | downcall: qsort(array, n, size, callbackPointer)
    +---------------------------------------------->
                                                   qsort
                                                     |
                                                     | gọi function pointer
                                                     v
                                        [FFM-generated upcall stub]
                                                     |
    <------------------------------------------------+
    |
Java static compare(leftSegment, rightSegment)
    |
    | trả int (negative / zero / positive)
    +---------------------------------------------->
                                                   qsort tiếp tục
    <----------------------------------------------+
    |
Java nhận kết quả mảng đã được sắp xếp
~~~

- **Downcall:** Java gọi hàm C. FFM dùng `Linker.downcallHandle` và `MethodHandle` để thực hiện.
- **Upcall:** Native C gọi lại **Java method handle** qua một địa chỉ function pointer đã tạo bằng `Linker.upcallStub`.
- **Callback:** Khái niệm tổng quát: một hàm được truyền/đăng ký để bên khác gọi vào thời điểm thích hợp. Trong ví dụ, callback logic nằm ở Java.
- **Synchronous callback:** Native gọi callback trong chính lời gọi downcall và hoàn tất trước khi downcall trả về, như ví dụ `qsort` thông thường.
- **Asynchronous/retained callback:** C lưu function pointer trong một registry và gọi nó **sau khi** lời gọi đăng ký đã kết thúc; cần thiết kế lifetime, unregister và concurrency riêng.

Upcall không phải cơ chế dùng `JNIEnv *` để chạy Java method trong một đoạn JNI viết tay. FFM linker thực hiện chuyển đổi giữa ABI của C và method handle của Java. Nếu hệ thống cũng dùng JNI, cần phân biệt hai cơ chế, không mang các con trỏ `JNIEnv *` qua thread một cách tùy tiện.

## 3. Function pointer không phải địa chỉ của một Java method trong heap

Một native function pointer là **địa chỉ mã có thể gọi theo ABI**; nó không phải `jobject`, không phải địa chỉ `Class`, không phải pointer tới `MethodHandle` Java object. JVM có trách nhiệm tạo thunks/stubs và chuyển đổi arguments/return values.

Trong Java FFM:

~~~java
Linker linker = Linker.nativeLinker();

MemorySegment functionPointer =
        linker.upcallStub(targetHandle, callbackDescriptor, arena);
~~~

Đây là **snippet minh họa**, ba biến `targetHandle`, `callbackDescriptor` và `arena` phải được tạo trước; nó không phải Java file chạy độc lập.

Ý nghĩa:

1. `targetHandle` là logic Java có thể được gọi thông qua một `MethodHandle`.
2. `callbackDescriptor` định nghĩa **chữ ký C** và layout của các tham số/giá trị trả về.
3. `linker` biết ABI của OS/CPU hiện tại.
4. `arena` quản lý lifetime của function pointer stub.
5. `functionPointer` là **`MemorySegment` có địa chỉ khác 0 và `byteSize() == 0`** trỏ tới stub. Đây là **con trỏ hàm**, không phải vùng dữ liệu để đọc/ghi bytes.

Bởi vậy, không bao giờ xử lý function pointer như memory của một `int` hay một mảng bytes. **Không** gọi `functionPointer.get(JAVA_INT,0)` và không tự `free` địa chỉ của stub; chỉ chuyển nó cho API C thực sự đòi con trỏ hàm, trong thời gian stub còn sống.

## 4. Năm thành phần FFM tham gia một upcall

| Thành phần | Cách dùng điển hình | Hợp đồng quan trọng |
| --- | --- | --- |
| `Linker.nativeLinker()` | Lấy linker hỗ trợ ABI hiện tại | Không phải linker tùy ý cho ABI của OS khác |
| `MethodHandles.lookup().findStatic(...)` | Tạo method handle tới callback Java | Type phải khớp chữ ký Java được suy từ descriptor |
| `FunctionDescriptor` | Mô tả return/argument layouts của callback C | Đúng số tham số, thứ tự, kiểu, ABI |
| `Linker.upcallStub(target, desc, arena)` | Tạo function pointer gọi ngược Java | Restricted, cần native access và arena còn sống |
| `Arena` | Quản lý lifetime của stub | Không đóng trước khi C hết khả năng gọi callback |

`ValueLayout.ADDRESS` xuất hiện trong hai vị trí khác nhau:

- Trong **callback descriptor**, `ADDRESS` mô tả tham số C có kiểu pointer, ví dụ `const void *a`.
- Trong **downcall descriptor**, `ADDRESS` mô tả tham số C có kiểu **function pointer**, ví dụ `compar` của `qsort`, bởi giá trị truyền cho C vẫn là một địa chỉ.

Không nhầm rằng `ADDRESS` chứng minh pointer trỏ tới 4 hay 8 byte: **pointer value không tự mang bounds**. Khi callback thật sự được gọi, nếu layout chỉ là `ADDRESS` thì tham số `MemorySegment` cho pointer thường có size 0.

## 5. Kiểu của MethodHandle phải đúng với FunctionDescriptor

Callback C:

~~~c
int compare(const void *left, const void *right);
~~~

Một Java method có thể được chọn làm target:

~~~java
static int compare(MemorySegment left, MemorySegment right) {
    // Đọc các phần tử, so sánh rồi trả số âm, 0 hoặc dương.
    return 0;
}
~~~

Nhưng chỉ xem tên hàm không đủ. Cần descriptor:

~~~java
FunctionDescriptor comparisonDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.ADDRESS
);
~~~

Với descriptor này, JVM suy kiểu method handle:

~~~text
(MemorySegment, MemorySegment)int
~~~

Bạn có thể kiểm bằng:

~~~java
MethodType methodType = comparisonDescriptor.toMethodType();
~~~

Hãy dùng `MethodHandles.lookup().findStatic(...)` với `methodType` để tạo target handle, hoặc tạo handle phù hợp bằng các combinators của `java.lang.invoke`.

Nếu method handle trả `long` thay `int`, có thêm một `MemorySegment` argument hoặc đổi thứ tự tham số, `upcallStub` không thể tùy tiện đoán/ép sang ABI C. Một target type không tương thích descriptor có thể khiến tạo stub ném **`IllegalArgumentException`**. Trường hợp ký hiệu target và descriptor **cùng nhìn hợp lệ ở Java nhưng sai C ABI thực**, native code có thể crash khi gọi function pointer.

### Target layout cho con trỏ callback

Trong `qsort`, C comparator nhận pointers tới từng phần tử. Với hợp đồng phần tử là C `int` 4 byte, Java có thể khai báo:

~~~java
FunctionDescriptor comparisonDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)
);
~~~

`withTargetLayout` giúp hai pointer arguments nhận được trong Java là `MemorySegment` có **`byteSize() == 4`**. Nếu không có target layout, hai tham số pointer được truyền vào upcall bình thường là **segment 0 byte**, và `get(JAVA_INT,0)` sẽ bị bounds check chặn.

**Cảnh báo:** `AddressLayout.withTargetLayout` là **restricted operation**. Nó tin rằng C sẽ truyền pointer hợp lệ tới vùng có kích thước/alignment như khai báo; nó **không kiểm chứng C memory allocation thật**. Với sai ABI hoặc pointer không hợp lệ, chương trình có thể gặp memory corruption hay JVM crash. Chỉ dùng khi C API có hợp đồng cụ thể về các pointer arguments.

## 6. Đặc tả ABI: đừng hardcode `size_t` trên mọi hệ

Hàm `qsort` dùng `size_t` cho `nmemb` và `size`. Trên nhiều hệ 64-bit, `size_t` có thể biểu diễn bằng Java `long`/`JAVA_LONG`; trên hệ 32-bit thường khác. **Không được suy ra C `size_t` luôn là `long`**.

Từ JDK 22, `Linker.canonicalLayouts()` cung cấp layouts của các kiểu C cơ bản theo linker/ABI. Có thể dùng:

~~~java
Linker linker = Linker.nativeLinker();
ValueLayout sizeT = (ValueLayout) linker.canonicalLayouts().get("size_t");
MemoryLayout cInt = linker.canonicalLayouts().get("int");
~~~

Trên môi trường kiểm thử Java 24 Windows/x64, `size_t` có carrier `long.class` và C `int` có size 4. Bài này có ví dụ runnable dành cho những ABI thông dụng thỏa hai điều kiện đó; code **tự kiểm tra** trước khi gọi native:

~~~java
if (sizeT.carrier() != long.class || cInt.byteSize() != 4) {
    throw new UnsupportedOperationException(
            "Example requires size_t=64-bit and C int=32-bit");
}
~~~

Cần lưu ý việc C `int` có size 4 chưa nhất thiết đảm bảo mọi ABI lạ được mô phỏng đúng; trong ví dụ nhắm tới Linux/x64 và Windows/x64, `ValueLayout.JAVA_INT` đúng. Ở ABI khác, thiết kế descriptor dựa trên canonical layouts và method type tương ứng, không cố ép bằng `invokeExact` kiểu không khớp.

## 7. Ví dụ hoàn chỉnh: C `qsort` gọi Java comparator qua upcall

Ví dụ này **không cần viết hay biên dịch C code**: nó gọi `qsort` đã có trong native C runtime mà JVM linker có thể tra cứu. Nó vẫn thực hiện **native downcall và real upcall**, không chỉ giả lập một Java callback.

Điều kiện chạy:

- **JDK 22+**, đã kiểm thử trên JDK 24 Windows/x64.
- Native runtime expose symbol `qsort` qua `linker.defaultLookup()`. Oracle không bảo đảm cùng một tập symbols trên mọi OS; nếu thiếu symbol, hãy dùng `SymbolLookup.libraryLookup(...)` của native library thực hoặc một fixture thư viện riêng.
- Nền tảng thỏa C `int` 4 byte, C `size_t` dùng Java `long` 8 byte; chương trình kiểm tra điều kiện đó.
- Chạy với native-access permission cho unnamed module.

### 7.1. Java source: `CallbackQsortDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class CallbackQsortDemo {
    private static final AtomicInteger calls = new AtomicInteger();
    private static final AtomicReference<Throwable> callbackError =
            new AtomicReference<>();

    private static int compare(MemorySegment left, MemorySegment right) {
        try {
            calls.incrementAndGet();

            int a = left.get(ValueLayout.JAVA_INT, 0);
            int b = right.get(ValueLayout.JAVA_INT, 0);
            return Integer.compare(a, b);
        } catch (Throwable t) {
            // Không để exception vượt qua native callback boundary.
            callbackError.compareAndSet(null, t);
            return 0; // Fallback value hợp lệ về ABI; sẽ báo lỗi sau downcall.
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        ValueLayout sizeT = (ValueLayout)
                linker.canonicalLayouts().get("size_t");

        if (sizeT.carrier() != long.class
                || linker.canonicalLayouts().get("int").byteSize() != 4) {
            throw new UnsupportedOperationException(
                    "Example requires size_t=64-bit and C int=32-bit");
        }

        FunctionDescriptor comparatorDesc = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));

        MethodHandle comparator = MethodHandles.lookup().findStatic(
                CallbackQsortDemo.class,
                "compare",
                comparatorDesc.toMethodType());

        FunctionDescriptor qsortDesc = FunctionDescriptor.ofVoid(
                ValueLayout.ADDRESS, // base: void*
                sizeT,               // nmemb: size_t
                sizeT,               // size: size_t
                ValueLayout.ADDRESS  // compar: function pointer
        );

        MethodHandle qsort = linker.downcallHandle(
                linker.defaultLookup().find("qsort").orElseThrow(),
                qsortDesc);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment array =
                    arena.allocateFrom(ValueLayout.JAVA_INT, 9, 2, 7, 1, 5);

            MemorySegment comparatorPointer = linker.upcallStub(
                    comparator, comparatorDesc, arena);

            System.out.println("stub-nonnull="
                    + (comparatorPointer.address() != 0L));

            // exact method type: (MemorySegment,long,long,MemorySegment)void
            qsort.invokeExact(array, 5L, 4L, comparatorPointer);

            if (callbackError.get() != null) {
                throw new IllegalStateException(
                        "Java callback failed", callbackError.get());
            }

            System.out.println("callback-called=" + (calls.get() > 0));
            System.out.println("sorted=" +
                    Arrays.toString(array.toArray(ValueLayout.JAVA_INT)));
        }
    }
}
~~~

Lưu `CallbackQsortDemo.java` ở thư mục làm việc, chạy:

~~~bash
javac -encoding UTF-8 CallbackQsortDemo.java
java --enable-native-access=ALL-UNNAMED CallbackQsortDemo
~~~

Stdout trên **JDK 24 Windows/x64 đã kiểm thử**:

~~~text
stub-nonnull=true
callback-called=true
sorted=[1, 2, 5, 7, 9]
~~~

`callback-called` được tính thành boolean thay vì in số lần comparator chạy, vì `qsort` không hứa một số lần gọi comparator cố định giữa các C runtime. `Comparator` phải đưa ra thứ tự nhất quán; ví dụ dùng `Integer.compare` tránh overflow do trừ trực tiếp hai số nguyên.

### 7.2. Vì sao ví dụ thật sự có upcall?

Đường thực thi là:

1. Java tạo dữ liệu int trong **native memory** qua `Arena.allocateFrom`.
2. Java tạo `MethodHandle comparator` tới static method `compare`.
3. Java tạo `comparatorPointer` qua `Linker.upcallStub`; pointer này có thể được C gọi.
4. Java dùng `qsort` downcall handle để gọi **C runtime** với function pointer vừa tạo.
5. `qsort` gọi comparator pointer khi so sánh các phần tử.
6. Upcall stub chuyển hai native pointers thành các `MemorySegment` 4 byte theo target layouts, rồi gọi method `compare` của Java.
7. Java comparator trả `int` theo quy tắc âm/0/dương, native `qsort` tiếp tục và ghi kết quả sắp xếp vào mảng.
8. Khi `qsort` trả về, Java xác minh callback không báo lỗi, rồi in mảng đã sắp.
9. Ra khỏi khối try, `arena.close()` thu hồi array và stub. Không có native code nào giữ pointer lại sau thời điểm này.

**Không** gọi `comparatorPointer.get(JAVA_BYTE,0)`: đây là function pointer có byteSize 0, không phải vùng dữ liệu có thể dereference. **Không** tự nhảy/call raw numeric address như `comparatorPointer.address()` từ Java; FFM linker quản lý ABI boundary.

### 7.3. Tại sao dùng `Integer.compare` thay `a - b`?

Nếu `a = Integer.MAX_VALUE` và `b = -1`, phép `a-b` sẽ tràn 32-bit signed và có thể tạo dấu sai. `qsort` cần thứ tự so sánh đúng, có tính nhất quán. `Integer.compare(a,b)` đáp ứng điều đó cho Java int khi C int tương ứng 32-bit.

### 7.4. Khi callback thất bại

Trong `compare`, code bắt `Throwable` và lưu exception đầu tiên vào `callbackError`. Trả `0` là **mã fallback đúng kiểu C int**, không phải khẳng định sắp xếp đã thành công. Sau khi `qsort` trả về, Java **kiểm tra và báo lỗi**.

Cơ chế này làm tránh việc để Java exception vượt qua C ABI boundary. Với callback async, không có downcall đang chờ để kiểm tra; cần error channel riêng (queue, future, log có kiểm soát, error callback phù hợp API). Nếu callback operation không thể hoàn thành an toàn sau lỗi, chọn native API có cơ chế **cancellation/status** thay vì tiếp tục sắp xếp vô điều kiện.

**Quan trọng:** Không thể thu hồi an toàn từ mọi sự cố native memory bằng Java try/catch; nếu C truyền pointer sai hoặc layout sai, code có thể crash JVM trước khi Java xử lý exception.

## 8. UpcallStub là function pointer, nhưng lifetime thuộc Arena

Khi gọi:

~~~java
MemorySegment stub = linker.upcallStub(target, descriptor, arena);
~~~

FFM tạo một stub trong native code và trả về **segment 0 byte** mang địa chỉ function pointer. `Arena` xác định khi nào stub được giải phóng. Khi arena đóng, **C không còn được gọi** function pointer ấy.

### Cách hiểu đúng

| Điều kiện | Được làm gì? |
| --- | --- |
| Stub vừa tạo, arena còn sống | Có thể truyền pointer cho native API có signature tương thích |
| C gọi callback đồng bộ và trả về trước khi arena đóng | Trường hợp đơn giản, dùng try-with-resources như ví dụ `qsort` |
| C lưu pointer để gọi ở tương lai | Phải giữ arena và các tài nguyên liên quan sống tới khi unregister và mọi callbacks đang chạy kết thúc |
| Arena đã đóng | **Không** gọi pointer nữa; có nguy cơ use-after-free/crash JVM |
| `stub.byteSize() == 0` | Điều này bình thường: function pointer không phải data buffer |
| `stub.address() != 0L` | Chỉ xác nhận có địa chỉ; không tự chứng minh signature đúng hoặc lifecycle an toàn |

Đối với callback đồng bộ trên thread tạo arena, `Arena.ofConfined()` tạo phạm vi dễ kiểm soát. **Đối với callback do C thực hiện từ thread khác hoặc lưu dài hạn**, cần xem xét `Arena.ofShared()`, quy tắc thread access của các `MemorySegment` nhận từ Java, và cơ chế đồng bộ shutdown.

Không chọn `Arena.ofAuto()` một cách vô thức nếu native C giữ function pointer qua nhiều lời gọi; callback lifecycle do C quyết định nhưng GC timing không mang lại signal unregister đáng tin cậy.

### Không free stub bằng C `free`

Upcall stub không phải một allocation do caller tạo bằng C `malloc`. `Linker.upcallStub` và arena sở hữu cơ chế release phù hợp. Không gọi `free(stub.address())` và không dùng `MemorySegment.NULL` như biện pháp thay thế cho unregister; thay giá trị trong một biến Java không vô hiệu hóa mọi bản sao function pointer mà C đã lưu.

## 9. Registration callback bất đồng bộ: một hợp đồng khác

Không phải native API nào cũng giống `qsort`. Xét interface C minh họa:

~~~c
typedef void (*event_callback)(int event_code, void *user_data);

void register_event_callback(event_callback cb, void *user_data);
void unregister_event_callback(void);
~~~

Đây là **prototype giả định**, không phải một thư viện đã tồn tại để tải/chạy. Giả sử `register_event_callback` giữ function pointer và có thể gọi lại **sau khi register return**. Một mô hình an toàn cần phân biệt các giai đoạn:

~~~text
Java tạo callback target + upcall stub trong long-lived arena
                |
                v
C register_event_callback(stub, userData)
                |
                v
Native event loop / native worker thread
                |
                +-- callback(stub) xảy ra 0, 1 hoặc nhiều lần
                |
                v
Java yêu cầu unregister
                |
                v
C xác nhận không thể phát sinh callback mới
và mọi callback đang chạy đã kết thúc
                |
                v
Java close arena, giải phóng tài nguyên liên quan
~~~

**Chỉ gọi unregister là chưa chắc đủ** nếu C library không bảo đảm chờ callbacks đang chạy. Hợp đồng thư viện phải nói rõ khi nào native đã ngừng dùng pointer (có thể cần join workers, flush event queue, reference counts hoặc synchronization). Không được đóng arena trước thời điểm đó.

Với nhiều callback chạy đồng thời:

- Trạng thái Java được callback sử dụng phải thread-safe.
- Nếu callback đọc/ghi `MemorySegment` cấp từ một confined arena trên thread khác, có thể gặp `WrongThreadException`; chọn arena/phạm vi truy cập phù hợp.
- Không giữ một mutex Java rồi gọi native function nếu native function có thể synchronous callback vào Java và cố lấy lại mutex/lock theo cách gây deadlock. Java monitor reentrant trên cùng thread, nhưng nhiều locks/threads có thể tạo chu trình chờ.
- Không giả định callback luôn thực hiện trên Java main thread, Swing EDT hoặc JavaFX Application Thread. Nếu UI cần cập nhật, hãy chuyển công việc sang thread của UI framework.
- Một callback chạy trên thread native khác có thể có context riêng; tránh dựa vào `ThreadLocal` hay transaction context của thread đã đăng ký.

## 10. Java callback state, context pointer và Java object

Một số C APIs truyền thêm `void *user_data` vào callback để caller phân biệt việc đăng ký. Đó là **native pointer-sized value**, không có cơ chế tự chuyển Java object thành con trỏ C.

**Sai:** ép Java object hoặc `System.identityHashCode(obj)` thành `void *` rồi mong native callback tìm lại đúng object.

Các lựa chọn thiết kế đúng:

1. **Bind trạng thái Java vào `MethodHandle`:** Với một Java instance có method `onEvent`, `lookup.findVirtual(...).bindTo(instance)` tạo handle đã chứa receiver. Stub đi với handle đó; native caller chỉ thấy pointer. Đảm bảo lifetime của stub/instance được phối hợp.
2. **Native context allocation:** Nếu C API bắt buộc cần `user_data`, cấp native struct/token trong một arena còn sống; mapping token → Java object do ứng dụng quản lý rõ và được dọn khi unregister.
3. **Registry bằng ID:** C lưu một số nguyên/opaque token qua `uintptr_t` hoặc struct theo ABI đã xác minh; Java registry quản lý mapping, đồng bộ và cleanup. Không giả định mọi bit pattern có thể chuyển thẳng thành pointer an toàn.
4. **Immutable payload copy:** Nếu chỉ cần dữ liệu mà C sở hữu, copy sang native memory, không giữ Java object reference giả dạng pointer.

Các cách tiếp cận khác nhau theo contract của thư viện. Không áp `ValueLayout.ADDRESS` lên một số Java `long` rồi gọi nó là pointer hợp lệ nếu không có API tạo/nhận địa chỉ đáng tin cậy.

### Đăng ký nhiều callbacks

Nếu native API đăng ký nhiều listeners, mỗi lần có thể có một stub, một handler/receiver và tài nguyên riêng. Dùng một owner rõ ràng để unregister đúng callback. Không tái sử dụng stub cũ sau khi arena đóng; không dựa vào numeric address để làm ID lâu dài, vì allocator có thể tái sử dụng địa chỉ.

## 11. Exception từ Java callback: vì sao rất nguy hiểm?

Phần mô tả `Linker.upcallStub` của Oracle JDK 24 nêu rất rõ: **target method handle không nên ném bất kỳ exception nào; nếu nó ném exception, JVM có thể kết thúc đột ngột**. Đây là ranh giới native, không phải lời gọi Java-to-Java bình thường có thể tự lan truyền stack trace qua C.

Sai:

~~~java
static int unsafeCompare(MemorySegment a, MemorySegment b) {
    int x = a.get(ValueLayout.JAVA_INT, 0);
    int y = b.get(ValueLayout.JAVA_INT, 0);
    if (x == 0) {
        throw new IllegalStateException("cannot compare zero");
    }
    return Integer.compare(x, y);
}
~~~

Đây là **phản ví dụ** (không đưa làm callback thực tế); việc ném `IllegalStateException` có thể vượt qua native ABI boundary và khiến runtime kết thúc bất ngờ.

Đúng hơn là **bắt lỗi trong callback**, ghi nhận trạng thái, trả một giá trị C ABI phù hợp, rồi xử lý ở tầng Java/native owner khi hợp đồng cho phép:

~~~java
static int safeCompare(MemorySegment a, MemorySegment b) {
    try {
        return Integer.compare(
                a.get(ValueLayout.JAVA_INT, 0),
                b.get(ValueLayout.JAVA_INT, 0));
    } catch (Throwable failure) {
        // Lưu lỗi vào thread-safe error channel.
        return 0; // Không bao giờ là lời hứa kết quả sort hợp lệ.
    }
}
~~~

Đoạn trên chỉ là snippet mẫu, chưa triển khai error channel; ví dụ đầy đủ đã dùng `AtomicReference<Throwable>`. Nếu callback là `void`, handler lỗi phải tiếp tục bảo đảm không thoát bằng Java exception. Không được giả định `try/catch` bắt được segmentation fault do ABI/pointer sai.

**Thiết kế API:** Một callback trả int kiểu status nên có quy ước rõ ràng C hiểu được, ví dụ nonzero báo lỗi, nếu native API hỗ trợ. Nhưng `qsort` comparator **không** có status lỗi riêng; code mẫu lưu lỗi cho Java kiểm tra khi downcall return.

## 12. Pointer arguments trong upcall không tự có bounds

C callback kiểu:

~~~c
int compare(const void *a, const void *b);
~~~

Khi C gọi callback, FFM chuyển `a`, `b` thành `MemorySegment`. Nếu callback descriptor khai báo `ADDRESS` thuần, segments tương ứng thông thường có `byteSize()==0` và global scope; không thể `get(JAVA_INT,0)` trực tiếp.

Khi **đã biết chắc C luôn truyền pointer tới int 4 byte**, có thể sử dụng `ADDRESS.withTargetLayout(JAVA_INT)`. Điều này **không** làm C memory do Java sở hữu; nó chỉ gán bounds dựa trên hợp đồng native.

Quy tắc an toàn:

- Kiểm pointer address 0 nếu C cho phép NULL, nhưng **non-NULL không đủ** để đảm bảo pointer còn hợp lệ.
- Target layout phải khớp dữ liệu thực tế; ví dụ array `double` không thể được đọc như một vùng `int` chỉ vì cả hai có địa chỉ.
- C pointer có thể chỉ hợp lệ **trong suốt một lần callback**. Không giữ segment wrapper từ callback để đọc sau khi native library đã free/realloc dữ liệu.
- C `const void *` là hợp đồng read-only; `ADDRESS` layout không tự ép mọi alias Java/native thành bất biến.
- Bảo đảm alignment thích hợp với ValueLayout. Trên struct packed có thể cần unaligned layout và logic đúng ABI.
- Nếu muốn giữ dữ liệu sau callback, copy bytes vào vùng Java/arena do bạn sở hữu **trong lifetime của callback** và xác minh kích thước trước.
- Không tạo raw pointer từ Java heap segment bằng ép địa chỉ, bởi JVM GC quản lý heap và có thể di chuyển object.

Nếu callback nhận `void *ctx`, không tự dereference ctx nếu không biết length/ownership. `MemorySegment.NULL` là C null pointer và có thể hợp lệ tùy API; kiểm `ctx.address()==0L` trước khi dùng.

## 13. ABI và signature: lỗi nào Java bắt được, lỗi nào không?

Giữa hai lớp cần phân biệt:

**Lớp Java MethodHandle:** FFM có thể đối chiếu type của target handle với `FunctionDescriptor`. Nếu số/type tham số không tương thích, `upcallStub` có thể ném `IllegalArgumentException`.

**Lớp native C ABI:** JVM không thể nhìn vào máy/foreign library và tự suy mọi chữ ký của con trỏ hàm. Nếu C gọi stub bằng function pointer có calling convention, return type, variadic status hoặc argument layouts khác descriptor, hành vi có thể không xác định, dẫn đến memory corruption/JVM crash.

| Lỗi | Khi nào xảy ra? | Phòng tránh |
| --- | --- | --- |
| Target Java sai `MethodType` | Khi gọi `upcallStub` hoặc xây handle | Suy type từ descriptor, dùng `findStatic`/`findVirtual` đúng signature |
| Callback C `int (char*)` nhưng Java mô tả `int(int)` | Native gọi function pointer | So sánh với C header/ABI thực, không đoán |
| C `size_t` bị mô tả cố định bằng `JAVA_LONG` trên ABI khác | Trong downcall `qsort` | Dùng `canonicalLayouts().get("size_t")` |
| Pointer-to-pointer bị nhầm pointer-to-data | Callback xử lý `T **` như `T *` | Vẽ mức indirection; dùng layout/address slot đúng |
| Native gọi callback sau arena close | Asynchronous/registered callback | Unregister + drain in-flight callbacks trước close |
| Java callback ném exception qua upcall | Khi callback đang chạy | Catch lỗi trong target, trả fallback/status theo C contract |
| C callback truyền pointer sai/lifetime hết | Khi Java truy cập segment | Kiểm contract; đừng xem withTargetLayout là validation |
| Stub dùng sai thread/confinement | Callback từ native worker thread | Lựa chọn Arena/segments và đồng bộ phù hợp |
| Không bật native access | Khi gọi restricted method | Chạy với flag hoặc cấu hình module được phép |
| Native function symbol không tìm thấy | Tạo downcall `qsort` | Kiểm `SymbolLookup`/đường dẫn shared library thực |

`Linker.upcallStub` có thể từ chối một descriptor không được linker hỗ trợ. Điều này khác với sai ABI mà linker không có đủ thông tin để phát hiện. Tính đúng đắn của C header, compiler target, data layouts và calling convention là trách nhiệm người tích hợp.

## 14. Thread model: callback có thể không quay lại đúng thread đã đăng ký

Ví dụ `qsort` minh họa cuộc gọi đồng bộ và là một phạm vi đơn giản. Nhưng nhiều C libraries có native worker threads, callback queue hoặc event loop.

- Một callback FFM có thể chạy trên **thread được native library dùng để gọi function pointer**, không mặc nhiên là thread Java đăng ký listener.
- `Arena.ofConfined()` thích hợp khi stub và các memory segments chỉ được dùng trong phạm vi owner thread/lời gọi đồng bộ có hợp đồng rõ ràng.
- Khi callback được gọi từ các threads khác nhau, `Arena.ofShared()` hoặc một lifetime mechanism thread-accessible có thể phù hợp hơn, **nhưng bản thân shared arena không bảo vệ shared mutable state**.
- Đồng bộ dữ liệu Java: dùng atomics/locks/queues tương ứng; đọc native memory cũng phải xét data race.
- Tránh giữ khóa Java qua downcall nếu C có thể gọi ngược synchronously và callback cần các tài nguyên đang bị khóa; thiết kế để không deadlock.
- Không cho callback đóng chính arena/stub đang được gọi nếu C vẫn có thể sử dụng function pointer; đợi lifetime phối hợp từ owner.
- Nếu callback cần cập nhật UI, dispatch tới đúng UI thread; không trực tiếp cập nhật UI từ arbitrary native callback thread.

Không nên giả định FFM upcall có contract giống JNI native method với `JNIEnv *` được truyền sẵn. `MethodHandle` là Java logic; làm việc với JNI riêng đòi cơ chế attach/context phù hợp.

## 15. Callback trả về pointer cần thêm lifetime contract

Một callback có return type `void *` hoặc `char *` sẽ có descriptor trả `ValueLayout.ADDRESS` và Java target trả `MemorySegment`. Đây là trường hợp nguy hiểm: C có thể giữ địa chỉ mà Java trả về.

Ví dụ **chỉ là prototype**:

~~~c
const char *get_name(void *ctx);
~~~

Nếu Java callback trả pointer tới buffer cấp bằng `Arena.ofConfined()` bên trong callback rồi arena đóng ngay khi return, C nhận **dangling pointer**. Không sửa được bằng cách giữ Java `String`: phải chuẩn bị vùng native đúng encoding/terminator, giữ nó sống theo hợp đồng C và xác định ai chịu trách nhiệm giải phóng.

Tương tự, nếu C API yêu cầu callback trả pointer mà C sẽ `free`, vùng trả về phải được cấp bằng allocator mà C được phép free. Không thể trả tùy ý `arena.allocate(...)` rồi mong `free` của C tương thích; ownership mismatch có thể crash.

Ngoài ra, method handle trả về `MemorySegment.NULL` có ý nghĩa C null pointer; không dùng Java `null` để thay tùy tiện. Native ABI carrier `ADDRESS` là `MemorySegment`.

## 16. Upcall đồng bộ và bất đồng bộ: so sánh thiết kế

| Thuộc tính | Đồng bộ như `qsort` | Registered / asynchronous callback |
| --- | --- | --- |
| Khi C gọi callback | Trong một downcall | Sau khi registration return, có thể rất lâu |
| Ai quản lý lifetime stub? | Khối `try (Arena ...)` bao quanh downcall | Owner dài hạn, đóng sau unregister và drain |
| Arena thường phù hợp | Confined khi thread/lifetime bảo đảm | Shared hoặc thiết kế phù hợp native worker threads |
| Callback state | Có thể là trạng thái của lời gọi hiện tại | Cần thread-safe, chống callbacks sau shutdown |
| Error reporting | Java có thể kiểm error channel sau downcall | Cần kênh lỗi bất đồng bộ hoặc native status contract |
| Đóng stub | Sau khi downcall return và callback kết thúc | Sau khi chắc chắn C không còn gọi pointer |
| Con trỏ dữ liệu callback | Chỉ tin memory trong thời hạn C bảo đảm | Cần explicit ownership/snapshot nếu vượt callback |

Điểm chung: **không thể chỉ giữ numeric address của function pointer để làm callback sống mãi**. Điều quan trọng là arena và native library cùng hiểu giới hạn thời gian, cũng như Java target/state còn phù hợp.

## 17. Hiệu năng và các cân nhắc thực tế

Một callback crossing Java/native boundary có chi phí liên quan đến ABI transition, thread state và JVM runtime. Do đó:

- Không giả định FFM upcall luôn nhanh hơn JNI callback hay function C thuần. Hãy benchmark trên JDK/OS/CPU và workload thật.
- Với `qsort`, comparator có thể được gọi nhiều lần; thực hiện network I/O, logging dày, cấp phát nhiều object hoặc blocking trong callback có thể gây chi phí rất lớn.
- Tránh gọi Java callback theo từng byte của một stream lớn nếu có thể batch dữ liệu theo hợp đồng API.
- Khi native đồng bộ gọi lại Java, callback có thể làm phát sinh reentrant logic; cần thiết kế idempotency/synchronization nếu API cho phép.
- Không nhầm `MethodHandle` với Java reflection `Method.invoke`: target handle được linker dùng cho ABI boundary, còn việc tìm/điều chỉnh handle được thực hiện trước callback.
- Kiểm tình trạng native library bị unload khi stub/pointer còn được lưu; symbol lookup, downcall handle và upcall stub đều chịu lifecycle của tài nguyên native liên quan.

## 18. Tình huống sửa lỗi

### 18.1. `IllegalArgumentException` khi tạo upcall stub

Kiểm tra `FunctionDescriptor.of` có return/argument layouts đúng như C callback prototype, và `comparatorDesc.toMethodType()` có khớp static method signature không. Nếu C comparator trả `int`, Java target không được khai báo `void` hoặc `long`. Trường hợp dùng callback instance method, cần `bindTo(instance)` trước khi kết hợp với descriptor thiếu receiver parameter.

### 18.2. `IllegalCallerException` khi tạo stub/downcall

`upcallStub` và việc tạo downcall handle là restricted. Trên classpath chạy `java --enable-native-access=ALL-UNNAMED ...`; trên module path cấp permission cho module thích hợp. Tùy JDK và chế độ kiểm soát native access, thiếu quyền có thể dẫn tới cảnh báo hoặc lỗi; đừng bỏ qua contract.

### 18.3. Native `qsort` không có trong default lookup

`Linker.defaultLookup()` được JVM chọn và tập symbols khác nhau theo nền tảng. Ví dụ học tập có thể chạy trên JDK24 Windows/x64 đã thử, nhưng không bảo đảm OS/JDK khác expose `qsort` giống hệt. Khi API C thật thuộc một shared library riêng, dùng `SymbolLookup.libraryLookup` và đúng đường dẫn/thư viện, kiểm lỗi symbol trước khi gọi.

### 18.4. `IndexOutOfBoundsException` trong Java comparator

Nếu hai pointer callback arguments được mô tả bằng `ADDRESS` không có target layout, chúng thường có size 0; `get(JAVA_INT,0)` sẽ thất bại. Khi C contract chắc chắn mỗi pointer trỏ tới một int 4 byte, dùng `ADDRESS.withTargetLayout(JAVA_INT)`. Không gán target layout lớn tùy ý để né lỗi vì sẽ làm mất memory safety.

### 18.5. Native worker gọi callback sau khi plugin dừng

Đây là lỗi lifetime **use-after-free** có thể gây crash, không chỉ một Java exception. Phải thiết kế `unregister`/`cancel`/`join` sao cho không còn callback in flight và không còn đường gọi lại trước khi đóng arena. Nếu native API không hỗ trợ unregister, không được tự đóng stub lúc native vẫn cầm pointer; cần xem lại kiến trúc hoặc giữ lifetime đến khi native subsystem hoàn toàn kết thúc.

### 18.6. Thấy callback trả 0 nhưng kết quả native không đúng

Một comparator trả 0 nghĩa là hai phần tử tương đương **theo comparator**. Nếu dùng 0 làm fallback vì Java code gặp lỗi, kết quả sort không còn đáng tin. Ghi nhận lỗi và phát hiện sau downcall (hoặc error channel async); đừng lặng lẽ diễn giải sắp xếp là thành công.

### 18.7. Callback bị gọi nhiều hơn dự đoán

`qsort` không cam kết số lần/comparison order. Không đếm số lần như một phần của yêu cầu correctness. Nếu API callback có thể gọi lặp, handler cần có logic tương ứng (đặc biệt với callback có side effect).

## 19. Checklist code review cho FFM upcall

- [ ] Đã đọc đúng C prototype callback, bao gồm return type, arguments, pointer indirection và calling convention?
- [ ] `FunctionDescriptor` mô tả đúng ABI/C types, không đoán `size_t` hoặc struct layout theo Java types?
- [ ] `MethodHandle.type()` khớp `FunctionDescriptor.toMethodType()`?
- [ ] `Linker.upcallStub` được gọi với native-access permission và một arena còn sống?
- [ ] Function pointer được truyền dưới dạng `MemorySegment` cho tham số C kiểu function pointer/`ValueLayout.ADDRESS`?
- [ ] Không dereference `upcallStub` như buffer dữ liệu hoặc tự C `free` địa chỉ của stub?
- [ ] Với pointer arguments nhận từ C, đã xác định size, alignment, lifetime, NULL policy trước `get`/`set`?
- [ ] Nếu dùng `withTargetLayout`, target layout được C contract xác minh?
- [ ] Callback target bắt lỗi trong boundary và **không** để Java exception thoát sang C?
- [ ] Với callback đồng bộ, arena tồn tại ít nhất suốt downcall; với callback async, có unregister và drain in-flight callbacks?
- [ ] Java callback state thread-safe; không giả định callback chạy trên main/UI thread?
- [ ] Không dùng confined segments trong callback ở native thread khác mà không kiểm ownership?
- [ ] Nếu callback trả pointer, memory đó còn sống đúng thời gian C cần và deallocator đúng owner?
- [ ] Không có double-free, use-after-free, dangling callback pointer hoặc callback sau unload?
- [ ] Test input rỗng, duplicates, phần tử âm/dương, callback nhiều lần, shutdown race và error path.
- [ ] Đã chạy thử đúng OS/CPU/JDK, với native library và ABI thực tế thay vì chỉ nhìn source Java?

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Native C gọi một function pointer dẫn tới Java `MethodHandle` thông qua FFM được gọi là gì?

**Đáp án:** **Upcall**, được kết nối thông qua `Linker.upcallStub`. Việc Java gọi C là downcall.

**Câu 2.** Có thể truyền trực tiếp Java `Comparator<Integer>` làm tham số `int (*compar)(...)` của `qsort` không?

**Đáp án:** Không. Phải tạo Java `MethodHandle` có kiểu phù hợp, khai báo C function descriptor, tạo upcall stub (một native function pointer), rồi chuyển pointer sang downcall của `qsort`.

**Câu 3.** Tại sao `upcallStub` nhận thêm `Arena`?

**Đáp án:** Arena **quản lý lifetime của stub**. Sau arena close, function pointer không còn hợp lệ; không thể để C tiếp tục gọi.

**Câu 4.** Với callback C `int compare(const void *a, const void *b)`, Java descriptor như thế nào?

**Đáp án:** Return `JAVA_INT`, hai arguments là `ADDRESS`. Nếu API bảo đảm mỗi pointer trỏ int 4 byte, có thể dùng `ADDRESS.withTargetLayout(JAVA_INT)` để Java nhận segment 4 byte; đây là restricted operation cần contract tin cậy.

**Câu 5.** Vì sao `qsort` downcall descriptor dùng `sizeT` thay vì Java `JAVA_LONG` cố định?

**Đáp án:** C `size_t` phụ thuộc ABI. Ví dụ kiểm tra `linker.canonicalLayouts().get("size_t")` rồi chỉ chạy trên ABI size_t 64-bit.

**Câu 6.** Nếu target Java callback ném exception thoát ra khỏi upcall, điều gì có thể xảy ra?

**Đáp án:** Oracle Javadoc cảnh báo JVM có thể **terminate abruptly**. Cần catch trong callback, trả fallback/status đúng C ABI và báo lỗi qua cơ chế riêng.

**Câu 7.** Vì sao `stub.byteSize() == 0` không chứng minh callback bị hỏng?

**Đáp án:** Upcall stub biểu diễn **function pointer**, không phải data buffer. Segment 0 byte với address là kiểu trả về bình thường của `upcallStub`.

**Câu 8.** C giữ callback sau khi register trả về. Java có được đóng arena ngay không?

**Đáp án:** Không. Arena phải sống suốt khi C còn khả năng gọi; phải unregister và đợi hết in-flight callbacks trước khi đóng.

**Câu 9.** Một callback C nhận `void *user_data`. Có được ép Java object thành raw pointer không?

**Đáp án:** Không. Bind Java state vào method handle hoặc dùng native context/registry với lifetime và synchronization rõ ràng.

**Câu 10.** `qsort` có hứa đúng 7 lần gọi comparator cho 5 phần tử không?

**Đáp án:** Không. Thư viện C có thể có thuật toán/số lần so sánh khác nhau. Chỉ kiểm tính chất callback được gọi và mảng được sắp đúng.

**Câu 11.** Dùng một confined arena cho callback nhận dữ liệu từ native worker thread khác có chắc đúng không?

**Đáp án:** Không. Cần cân nhắc quyền truy cập thread, lifetime stub và các segments. Một shared arena hay thiết kế đồng bộ khác có thể cần thiết, tùy native callback contract.

**Câu 12.** Callback trả `MemorySegment` đại diện C pointer. Có thể trả memory của arena đã đóng ngay lúc callback return không?

**Đáp án:** Không nếu C sẽ tiếp tục dùng pointer. Phải giữ allocation sống ít nhất đến khi C xong và release bằng đúng cơ chế sở hữu.

## Tài liệu chính thức

1. [Oracle Java SE 24 — Linker API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): `upcallStub`, `downcallHandle`, `nativeLinker`, canonical C layouts, ABI và safety considerations.
2. [Oracle Java SE 24 — FFM Guide](https://docs.oracle.com/en/java/javase/24/core/foreign-function-and-memory-api.html): hướng dẫn upcalls bằng C `qsort` và function pointers.
3. [Oracle Java SE 24 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): signature layouts và `toMethodType`.
4. [Oracle Java SE 24 — AddressLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/AddressLayout.html): `ADDRESS`, `withTargetLayout` và pointer bounds.
5. [Oracle Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared memory lifetime.
6. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API chính thức từ Java 22.
7. [Java 24 — MethodHandles](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html): `findStatic`, `bindTo` và combinators.

**Kết luận:** **Callback** là mô hình gọi lại tổng quát; **function pointer** là địa chỉ hàm theo ABI C; **upcall** là native code gọi Java thông qua **FFM upcall stub**. Một integration đúng không chỉ tạo được pointer mà còn phải đúng **C signature, native access, lifetime của Arena, ownership của dữ liệu callback và quy tắc không để Java exception thoát qua C boundary**.
