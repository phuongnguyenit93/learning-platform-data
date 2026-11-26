# Tạo upcall stub để thư viện native gọi ngược vào Java

## Upcall là gì?

Khi Java gọi một hàm trong thư viện C/C++, đó là *downcall*. Chiều gọi ngược lại — mã native gọi một phương thức Java — được gọi là *upcall*.

Một thư viện native có thể cần callback để báo tiến độ, xử lý sự kiện, yêu cầu ứng dụng cung cấp dữ liệu hoặc tùy biến một thao tác. Ví dụ quen thuộc là hàm `qsort` của thư viện C: hàm này sắp xếp mảng nhưng để bên gọi cung cấp một hàm so sánh hai phần tử. Java có thể viết hàm so sánh đó rồi truyền cho `qsort` dưới dạng con trỏ hàm.

Foreign Function & Memory API (FFM) cung cấp `Linker.upcallStub(...)` để biến một `MethodHandle` của Java thành function pointer mà mã native có thể gọi. API FFM trở thành chính thức từ JDK 22 qua JEP 454; ví dụ trong bài sử dụng API ổn định từ JDK 22 trở lên, không cần bật preview.

## Luồng hoạt động

```text
Java code                         Native library
    |                                   |
    | 1. Tạo MethodHandle               |
    | 2. Mô tả chữ ký bằng               |
    |    FunctionDescriptor             |
    |                                   |
    | 3. Linker.upcallStub(...)          |
    |---------------------------------->| function pointer
    |                                   |
    | 4. Gọi hàm native (downcall)       |
    |---------------------------------->| qsort(..., callback)
    |                                   |
    |                         5. Native gọi callback
    |<----------------------------------|
    |                                   |
    | 6. JVM chuyển lời gọi thành        |
    |    lời gọi MethodHandle            |
    |                                   |
    | 7. Java trả kết quả                |
    |---------------------------------->| native tiếp tục
    |                                   |
    | 8. Native kết thúc                 |
    |<----------------------------------|
```

`upcallStub` tạo một đoạn mã trung gian theo ABI của nền tảng. Địa chỉ của đoạn mã đó hoạt động như con trỏ hàm native. Khi thư viện gọi con trỏ, JVM chuyển các tham số theo ABI thành các giá trị Java tương ứng rồi thực thi `MethodHandle` đã đăng ký.

## Ba thành phần cần có

| Thành phần | Vai trò |
|---|---|
| `MethodHandle` | Đại diện cho phương thức Java sẽ được thực thi khi native gọi callback. |
| `FunctionDescriptor` | Mô tả chữ ký hàm theo quy tắc ABI: kiểu trả về và layout của từng tham số native. |
| `Arena` | Quản lý vòng đời của upcall stub. Đóng arena sẽ giải phóng stub và làm function pointer không còn hợp lệ. |

Phương thức chính có dạng:

```java
MemorySegment Linker.upcallStub(
        MethodHandle target,
        FunctionDescriptor function,
        Arena arena,
        Linker.Option... options);
```

Kết quả là một `MemorySegment` có kích thước bằng 0 nhưng chứa địa chỉ của upcall stub. Segment này được truyền cho native code như một function pointer; không đọc hoặc ghi dữ liệu qua segment đó.

Chữ ký của `MethodHandle` phải tương thích với kiểu Java được suy ra từ `FunctionDescriptor`. Chẳng hạn, `JAVA_INT` tương ứng với `int`, còn `ADDRESS` tương ứng với `MemorySegment`. Nếu địa chỉ có target layout, segment nhận được trong callback có kích thước bằng `targetLayout.byteSize()`.

## Ví dụ: dùng Java comparator với hàm C `qsort`

### Hàm native cần gọi

Hàm chuẩn C `qsort` có chữ ký:

```c
void qsort(
    void *base,
    size_t nmemb,
    size_t size,
    int (*compar)(const void *, const void *)
);
```

Các tham số gồm:

- `base`: địa chỉ phần tử đầu tiên của mảng.
- `nmemb`: số lượng phần tử.
- `size`: kích thước mỗi phần tử tính bằng byte.
- `compar`: con trỏ tới hàm so sánh hai phần tử. Hàm trả số âm, 0 hoặc số dương tùy quan hệ thứ tự.

Ta sẽ để `qsort` thực hiện thuật toán sắp xếp trong native code, còn hàm so sánh được viết bằng Java.

### Viết callback Java

Mỗi tham số `const void *` của C trỏ tới một số nguyên `int`. Trong FFM, con trỏ được biểu diễn bằng `MemorySegment`; `ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)` mô tả rằng địa chỉ đó trỏ tới một giá trị `int`.

```java
private static int compareInts(MemorySegment left, MemorySegment right) {
    int a = left.get(ValueLayout.JAVA_INT, 0L);
    int b = right.get(ValueLayout.JAVA_INT, 0L);
    return Integer.compare(a, b);
}
```

`Integer.compare` trả về số âm nếu `a` nhỏ hơn `b`, 0 nếu bằng nhau và số dương nếu `a` lớn hơn `b`. Cách này tránh phép trừ `a - b`, vốn có thể tràn số nguyên và làm comparator trả thứ tự sai.

### Mô tả chữ ký callback

```java
FunctionDescriptor comparatorDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));
```

Descriptor mô tả hàm C có kiểu trả về `int` và hai tham số là con trỏ tới `int`. Có thể lấy `MethodType` tương ứng trực tiếp từ descriptor để tạo `MethodHandle`:

```java
MethodHandle comparatorHandle = MethodHandles.lookup().findStatic(
        QsortWithJavaComparator.class,
        "compareInts",
        comparatorDescriptor.toMethodType());
```

Kiểu Java được suy ra là:

```java
int (MemorySegment, MemorySegment)
```

Vì mỗi địa chỉ có target layout `JAVA_INT`, mỗi `MemorySegment` truyền vào callback có thể đọc một giá trị `int` tại offset `0L`. Nếu chỉ mô tả tham số bằng `ValueLayout.ADDRESS` mà không có target layout, segment nhận được có kích thước 0; khi đó không thể đọc trực tiếp dữ liệu qua `get` nếu chưa cung cấp giới hạn bộ nhớ hợp lệ bằng một cơ chế khác.

### Tạo upcall stub và gọi `qsort`

Ví dụ hoàn chỉnh:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.util.Arrays;

public class QsortWithJavaComparator {

    private static int compareInts(MemorySegment left, MemorySegment right) {
        int a = left.get(ValueLayout.JAVA_INT, 0L);
        int b = right.get(ValueLayout.JAVA_INT, 0L);
        return Integer.compare(a, b);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Chữ ký qsort: void(void*, size_t, size_t, function pointer).
        // Ví dụ này giả định ABI 64-bit, nơi size_t được biểu diễn bằng JAVA_LONG.
        MethodHandle qsort = linker.downcallHandle(
                linker.defaultLookup().findOrThrow("qsort"),
                FunctionDescriptor.ofVoid(
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_LONG,
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS));

        // Chữ ký callback C: int(const int*, const int*).
        FunctionDescriptor comparatorDescriptor = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));

        MethodHandle comparatorHandle = MethodHandles.lookup().findStatic(
                QsortWithJavaComparator.class,
                "compareInts",
                comparatorDescriptor.toMethodType());

        int[] values = {9, 3, 7, 1, 4};

        // Stub và mảng native chỉ cần sống trong thời gian qsort thực thi.
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment array = arena.allocateArray(ValueLayout.JAVA_INT, values);

            MemorySegment comparatorStub = linker.upcallStub(
                    comparatorHandle,
                    comparatorDescriptor,
                    arena);

            // Native qsort gọi ngược comparatorStub mỗi khi cần so sánh.
            qsort.invokeExact(
                    array,
                    (long) values.length,
                    (long) ValueLayout.JAVA_INT.byteSize(),
                    comparatorStub);

            int[] sorted = array.toArray(ValueLayout.JAVA_INT);
            System.out.println(Arrays.toString(sorted));
        }
    }
}
```

Kết quả:

```text
[1, 3, 4, 7, 9]
```

Trong ví dụ này, `qsort` là downcall từ Java sang thư viện C. Trong lúc `qsort` đang chạy, nó gọi function pointer `comparatorStub`; đó là upcall từ native code trở lại phương thức `compareInts` của Java.

Mẫu dùng `JAVA_LONG` cho hai tham số `size_t`, phù hợp với ABI 64-bit. Nếu cần hỗ trợ ABI khác, hãy lấy layout chuẩn từ `linker.canonicalLayouts().get("size_t")` thay vì mặc định mọi nền tảng đều biểu diễn `size_t` bằng `long`.

## Chạy chương trình và cấp quyền native access

`Linker.upcallStub(...)` là restricted method. Trong ví dụ, `Linker.downcallHandle(...)` và `AddressLayout.withTargetLayout(...)` cũng là restricted methods. Những phương thức này cho phép tương tác với mã ngoài JVM và có thể gây crash hoặc hỏng bộ nhớ nếu khai báo ABI sai.

Với ứng dụng chạy trên classpath, hãy bật native access khi khởi chạy:

```shell
javac QsortWithJavaComparator.java
java --enable-native-access=ALL-UNNAMED QsortWithJavaComparator
```

Nếu ứng dụng chạy dưới dạng named module, thay `ALL-UNNAMED` bằng tên module cần sử dụng native access:

```shell
java --module-path mods --enable-native-access=my.application --module my.application/com.example.Main
```

Trong JDK 24 trở lên, truy cập restricted method khi chưa bật native access mặc định phát cảnh báo và vẫn cho phép thực thi theo chế độ `warn`; chế độ `deny` sẽ ném `IllegalCallerException`. Hãy bật quyền tường minh cho module thực sự cần gọi native code và thử nghiệm với `--illegal-native-access=deny` để phát hiện nơi còn thiếu cấu hình. Đây là quyền native access, không phải cờ preview.

## Quản lý vòng đời của upcall stub

Upcall stub được cấp phát trong `Arena` được truyền vào `Linker.upcallStub`. Khi arena đóng, bộ nhớ chứa stub được giải phóng và function pointer không còn hợp lệ.

Trong ví dụ `qsort`, callback chỉ được gọi đồng bộ trong thời gian lời gọi `qsort` đang chạy. Vì vậy, có thể tạo stub trong `Arena.ofConfined()`, gọi `qsort`, đọc kết quả rồi đóng arena.

Với thư viện đăng ký callback để gọi về sau, cần quản lý vòng đời chặt chẽ hơn:

1. Tạo arena có thời gian sống bao phủ toàn bộ thời gian đăng ký callback.
2. Truyền function pointer cho thư viện native và giữ tham chiếu tới stub/arena trong đối tượng quản lý đăng ký.
3. Khi kết thúc, yêu cầu thư viện hủy đăng ký callback.
4. Chờ hoặc xác nhận không còn callback nào đang chạy.
5. Chỉ sau đó mới đóng arena.

Nếu đóng arena trong khi native code vẫn giữ và có thể gọi function pointer, chương trình có thể gọi vào vùng stub đã giải phóng và gây hành vi không xác định hoặc crash JVM. Không dựa vào garbage collector để xác định thời điểm an toàn cho một callback mà native code đang giữ.

Chọn `Arena` dựa trên vòng đời và mô hình thread:

| Arena | Khi nào phù hợp |
|---|---|
| `Arena.ofConfined()` | Callback chỉ dùng trong một lời gọi native đồng bộ và phạm vi xử lý thuộc một thread, như ví dụ `qsort`. |
| `Arena.ofShared()` | Stub hoặc các segment liên quan cần được truy cập trong thiết kế có nhiều thread; ứng dụng vẫn phải đồng bộ dữ liệu dùng chung. |
| `Arena.ofAuto()` | Có thể chấp nhận vòng đời do garbage collector quản lý và không cần đóng tường minh. Phải giữ tham chiếu Java tới stub trong suốt thời gian native code còn giữ function pointer; không dùng cách này để thay thế quy trình hủy đăng ký callback. |
| `Arena.global()` | Chỉ khi stub thực sự cần tồn tại suốt vòng đời tiến trình; không thể đóng arena này. |

Arena kiểm soát vòng đời và quyền truy cập của các segment gắn với nó. Arena shared không tự làm callback thread-safe và cũng không thay thế giao thức đăng ký/hủy đăng ký ở phía native.

## Xử lý exception bên trong callback

Phương thức Java được gắn với upcall stub **không được để exception thoát ra ngoài**. Theo hợp đồng của `Linker.upcallStub`, nếu target `MethodHandle` ném exception khi native gọi callback, JVM sẽ kết thúc đột ngột.

Nếu callback có thể gặp lỗi, hãy bắt lỗi ngay bên trong phương thức Java, ghi nhận lỗi vào một kênh an toàn theo từng lần đăng ký callback, rồi trả về giá trị fallback mà hợp đồng C quy định. Sau khi lời gọi native kết thúc, Java kiểm tra trạng thái lỗi và chuyển lỗi đó thành exception Java ở phía gọi. Với callback có thể chạy đồng thời, trạng thái lỗi cần thread-safe và không nên dùng một biến dùng chung không phân biệt các lần đăng ký.

Ví dụ về nguyên tắc xử lý:

```java
import java.util.concurrent.atomic.AtomicReference;

private static final AtomicReference<Throwable> CALLBACK_FAILURE = new AtomicReference<>();

private static int compareInts(MemorySegment left, MemorySegment right) {
    try {
        int a = left.get(ValueLayout.JAVA_INT, 0L);
        int b = right.get(ValueLayout.JAVA_INT, 0L);
        return Integer.compare(a, b);
    } catch (Throwable failure) {
        CALLBACK_FAILURE.compareAndSet(null, failure);
        // 0 là fallback của comparator qsort trong ví dụ này.
        return 0;
    }
}

private static void checkCallbackFailure() {
    Throwable failure = CALLBACK_FAILURE.getAndSet(null);
    if (failure != null) {
        throw new IllegalStateException("Java comparator failed", failure);
    }
}
```

Gọi `checkCallbackFailure()` ngay sau khi `qsort` trả về. Đây là biến thể xử lý lỗi cho một lần gọi `qsort` tại một thời điểm. Trong ứng dụng có thể chạy nhiều callback đồng thời, hãy tạo trạng thái lỗi riêng cho từng registration và gắn nó vào `MethodHandle` bằng cách bind đối số hoặc một cơ chế quản lý tương đương. Kiểu tham số, kiểu trả về và giá trị fallback phải khớp chính xác với hợp đồng native; không thể dùng `return 0` cho mọi loại callback.

## Các lỗi thường gặp

| Vấn đề | Nguyên nhân và cách xử lý |
|---|---|
| `IllegalCallerException` khi tạo stub | Module chưa được cấp native access. Bổ sung `--enable-native-access` cho đúng module. |
| `IllegalArgumentException` khi gọi `upcallStub` | Chữ ký `MethodHandle` không tương thích với `FunctionDescriptor`, hoặc descriptor không được linker hỗ trợ. So sánh `target.type()` với `descriptor.toMethodType()` và kiểm tra ABI. |
| `IndexOutOfBoundsException` khi đọc tham số con trỏ | Address layout không có target layout phù hợp hoặc target layout mô tả sai kích thước dữ liệu. |
| `WrongThreadException` | Segment thuộc confined arena bị truy cập từ thread khác. Dùng shared arena khi mô hình truy cập thực sự cần nhiều thread và đồng bộ dữ liệu. |
| JVM crash hoặc memory corruption | Function pointer bị gọi sau khi stub đã giải phóng, descriptor không khớp chữ ký native, hoặc native code truyền con trỏ không hợp lệ. |
| JVM kết thúc khi callback gặp lỗi | Exception thoát khỏi target method handle. Bắt và xử lý lỗi bên trong callback. |

## Giới hạn và nguyên tắc an toàn

- **Mô tả ABI chính xác.** Kiểu trả về, thứ tự tham số, layout, alignment, kiểu con trỏ và quy ước gọi phải khớp với khai báo C thực tế. Linker không thể xác minh đầy đủ rằng function pointer được truyền cho native code có đúng kiểu hay không.
- **Giữ stub sống đủ lâu.** Native code không được giữ function pointer sau khi arena đã đóng. Với callback đăng ký dài hạn, phải hủy đăng ký và chờ callback hoàn tất trước khi đóng arena.
- **Không ném exception qua biên native.** Mọi lỗi cần được bắt và chuyển qua trạng thái hoặc error channel do ứng dụng thiết kế.
- **Không trả con trỏ hết hạn.** Nếu callback trả một `MemorySegment` dưới dạng địa chỉ, vùng nhớ mà địa chỉ đó trỏ tới phải còn hợp lệ sau khi callback kết thúc theo hợp đồng native.
- **Tránh deadlock và reentrancy ngoài dự kiến.** Native library có thể gọi callback trong lúc đang giữ lock nội bộ. Callback nên ngắn, tránh gọi ngược các API có thể chờ cùng tài nguyên hoặc tái nhập thư viện theo cách không được hỗ trợ.
- **Đối chiếu phiên bản và ABI của thư viện.** Cùng tên hàm không đảm bảo cùng chữ ký giữa các phiên bản thư viện hoặc nền tảng.

## Khi nào nên dùng upcall stub?

Upcall stub phù hợp khi API native yêu cầu function pointer do ứng dụng cung cấp, chẳng hạn:

- Comparator hoặc predicate cho thuật toán native như `qsort`.
- Callback báo tiến độ hoặc sự kiện từ thư viện C/C++.
- Hàm xử lý dữ liệu được native framework gọi theo giao thức đã định nghĩa.
- Đăng ký callback cho event loop, thư viện thiết bị hoặc API hệ điều hành.

Nếu thư viện chỉ cần nhận một vùng dữ liệu hoặc trả kết quả trực tiếp, downcall thông thường có thể đủ. Nếu cần callback, hãy xác định rõ ai sở hữu function pointer, callback có đồng bộ hay bất đồng bộ, callback chạy trên thread nào và khi nào có thể hủy đăng ký. Các thông tin đó quyết định cách tạo arena và quản lý trạng thái Java.

## Tài liệu tham khảo

- [JEP 454 — Foreign Function & Memory API (JDK 22)](https://openjdk.org/jeps/454)
- [Java SE 27 API — `Linker.upcallStub`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 27 API — `FunctionDescriptor`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Java SE 27 API — `AddressLayout.withTargetLayout`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Oracle Java 27 Core Libraries Guide — Upcalls: Passing Java Code as a Function Pointer to a Foreign Function](https://docs.oracle.com/en/java/javase/27/core/upcalls-passing-java-code-function-pointer-foreign-function.html)
- [Oracle Java 27 Core Libraries Guide — Restricted Methods](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html)
