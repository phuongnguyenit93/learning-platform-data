# Vòng đời callback, truy cập đa luồng và ngăn ngoại lệ thoát qua biên native

Foreign Function & Memory API (FFM) cho phép mã native gọi ngược một phương thức Java thông qua *upcall stub*. Đây là cách triển khai callback khi gọi thư viện C/C++: Java tạo một function pointer đại diện cho method handle, sau đó truyền con trỏ đó cho hàm native. Callback có thể được gọi ngay trong một downcall đồng bộ hoặc được thư viện native lưu lại để gọi về sau.

Callback làm xuất hiện ba trách nhiệm an toàn cần được quản lý cùng nhau:

- **Vòng đời:** upcall stub và dữ liệu mà callback sử dụng phải còn hợp lệ trong toàn bộ thời gian native code có thể gọi callback.
- **Truy cập đa luồng:** native library có thể gọi callback từ thread khác hoặc đồng thời từ nhiều thread; mã Java phải tuân theo hợp đồng thread của thư viện.
- **Ngoại lệ:** không được để exception thoát khỏi method handle được gọi qua upcall stub. Theo hợp đồng FFM, nếu target ném exception, JVM có thể kết thúc đột ngột.

Các ví dụ trong bài sử dụng Foreign Function & Memory API đã hoàn thiện từ JDK 22 (`java.lang.foreign`). Chúng không dùng API incubator hoặc preview cũ.

## 1. Upcall là gì?

Một *downcall* xảy ra khi Java gọi hàm native. Một *upcall* xảy ra khi hàm native gọi ngược vào Java. FFM tạo cầu nối cho chiều gọi này bằng `Linker.upcallStub`.

Để tạo stub, cần ba thành phần:

1. **Method handle:** đại diện cho phương thức Java sẽ xử lý callback.
2. **Function descriptor:** mô tả chính xác kiểu trả về và các tham số theo ABI native.
3. **Arena:** quản lý vòng đời của vùng nhớ chứa upcall stub.

Ví dụ, nếu thư viện C khai báo callback như sau:

```c
typedef int (*value_callback)(int value);
```

thì descriptor tương ứng trong Java là:

```java
FunctionDescriptor callbackDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);
```

`JAVA_INT` ánh xạ kiểu `int` của Java tới kiểu số nguyên C tương ứng trên ABI mà linker hỗ trợ. Khi callback nhận con trỏ, layout tham số thường là `ValueLayout.ADDRESS`, có carrier Java là `MemorySegment`. Phải đối chiếu khai báo C thực tế, kích thước kiểu dữ liệu và ABI của nền tảng; không suy luận chữ ký chỉ từ tên hàm.

## 2. Tạo upcall stub và giữ chữ ký nhất quán

Ví dụ sau tạo method handle cho một phương thức Java có chữ ký `int onValue(int value)`, rồi tạo upcall stub từ descriptor tương ứng:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class SimpleCallback {
    private static final FunctionDescriptor CALLBACK_DESCRIPTOR =
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.JAVA_INT);

    private static final MethodHandle CALLBACK;

    static {
        try {
            CALLBACK = MethodHandles.lookup().findStatic(
                    SimpleCallback.class,
                    "onValue",
                    MethodType.methodType(int.class, int.class));
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static int onValue(int value) {
        return value * 2;
    }

    public static MemorySegment createStub(Arena arena) {
        return Linker.nativeLinker().upcallStub(
                CALLBACK,
                CALLBACK_DESCRIPTOR,
                arena);
    }
}
```

Kiểu method handle phải tương thích với kiểu được suy ra từ `FunctionDescriptor`. Nếu C mong đợi `int (*)(int)` nhưng Java tạo stub có kiểu trả về hoặc tham số khác, lời gọi có thể thất bại hoặc gây hành vi không xác định ở biên native. `upcallStub` là restricted method; ứng dụng phải bật native access cho module gọi API, ví dụ `--enable-native-access=ALL-UNNAMED` khi chạy ứng dụng trên classpath.

`upcallStub` trả về một `MemorySegment` có kích thước bằng 0 nhưng địa chỉ của nó là function pointer native. Truyền chính segment này cho downcall handle có tham số `ADDRESS`; không đọc hay ghi byte từ segment đó như một buffer thông thường.

## 3. Vòng đời của callback và upcall stub

Upcall stub được gắn với arena truyền vào `Linker.upcallStub`. Khi arena đóng, vùng nhớ của stub được giải phóng và con trỏ không còn hợp lệ. Bất kỳ native code nào còn giữ con trỏ đó đều có thể gọi vào vùng nhớ đã bị giải phóng, dẫn tới lỗi nghiêm trọng hoặc JVM crash.

Với callback chỉ được gọi đồng bộ trong một downcall, arena có thể có phạm vi ngắn:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment callbackStub = SimpleCallback.createStub(arena);

    // Gọi hàm native đồng bộ và truyền callbackStub cho hàm đó.
    // Hàm native phải hoàn tất mọi lần callback trước khi downcall trả về.
    invokeNativeOperation(callbackStub);
}
```

Đây là mô hình tương tự callback comparator mà `qsort` gọi trong lúc sắp xếp. Khi downcall kết thúc và native function không còn giữ hoặc sử dụng con trỏ, arena mới được đóng an toàn.

Callback bất đồng bộ có vòng đời dài hơn. Ví dụ, một thư viện đăng ký callback rồi gọi callback trong các worker thread của chính thư viện. Khi đó, không thể đóng arena ngay sau khi hàm đăng ký trả về. Quy trình quản lý cần có các bước:

1. Tạo arena và upcall stub.
2. Đăng ký stub với native library.
3. Giữ arena sống trong suốt thời gian native library được phép gọi callback.
4. Yêu cầu native library ngừng phát callback và hủy đăng ký.
5. Chờ các callback đang chạy hoàn tất hoặc dùng API native có cam kết hủy đăng ký đồng thời drain mọi callback đang chạy.
6. Chỉ sau khi chắc chắn không còn lời gọi nào có thể bắt đầu hoặc đang chạy mới đóng arena.

Mẫu dưới đây mô tả thứ tự vòng đời. `registerCallback`, `unregisterCallback`, `awaitNativeWork` và `awaitCallbacksToFinish` đại diện cho các downcall hoặc cơ chế đồng bộ do thư viện native cung cấp, không phải phương thức có sẵn của FFM:

```java
try (Arena callbackArena = Arena.ofShared()) {
    MemorySegment callbackStub = SimpleCallback.createStub(callbackArena);

    registerCallback(callbackStub);
    try {
        awaitNativeWork();
    } finally {
        unregisterCallback(callbackStub);
        // Phải đợi callback đang chạy kết thúc trước khi thoát arena.
        awaitCallbacksToFinish();
    }
}
```

Chỉ gọi hàm `unregister` chưa chắc đã đủ. Một số thư viện chỉ ngăn các callback mới, trong khi callback đã được đưa vào hàng đợi vẫn có thể chạy. Cần đọc hợp đồng của API native để biết thao tác hủy đăng ký có đợi các callback đang hoạt động hay không. Nếu không, phải có bước drain, join hoặc cơ chế tương đương.

Mọi vùng nhớ khác mà callback dùng, chẳng hạn context pointer, buffer hoặc cấu trúc native, cũng phải còn hiệu lực trong cùng khoảng thời gian. Giữ stub sống nhưng giải phóng context quá sớm vẫn là lỗi vòng đời.

## 4. Callback có thể chạy trên nhiều thread

Không nên giả định callback luôn chạy trên thread đã đăng ký nó. Với callback đồng bộ như `qsort`, callback thường được gọi trong luồng thực thi của downcall. Với API bất đồng bộ, native library có thể gọi callback từ thread native riêng, hoặc gọi đồng thời từ nhiều thread. Quy tắc cụ thể phụ thuộc vào hợp đồng của thư viện.

Điều này ảnh hưởng tới cả arena lẫn trạng thái Java:

- `Arena.ofConfined()` giới hạn quyền truy cập segment cho thread tạo arena. Nó phù hợp với dữ liệu chỉ được dùng trong một tác vụ đồng bộ trên thread sở hữu. Nếu callback từ thread khác cần đọc hoặc ghi segment thuộc arena confined, thao tác có thể ném `WrongThreadException`.
- `Arena.ofShared()` cho phép truy cập segment từ nhiều thread và có thể đóng từ thread khác. Đây thường là lựa chọn phù hợp cho buffer/context cần được callback bất đồng bộ dùng chung. Tuy nhiên, vẫn phải chờ các callback kết thúc trước khi đóng arena.
- Arena shared không tự làm cho object Java hoặc dữ liệu native trở thành thread-safe. Nếu callback đồng thời cập nhật trạng thái chung, ứng dụng cần đồng bộ bằng lock, atomic hoặc cấu trúc dữ liệu concurrent.

Ví dụ callback có thể được gọi đồng thời nên dùng trạng thái hỗ trợ truy cập đồng thời:

```java
import java.util.concurrent.atomic.LongAdder;

public final class ConcurrentCallbackState {
    private static final LongAdder CALLBACK_COUNT = new LongAdder();

    private static int onValue(int value) {
        CALLBACK_COUNT.increment();
        return value * 2;
    }

    public static long callbackCount() {
        return CALLBACK_COUNT.sum();
    }
}
```

`LongAdder` phù hợp với bộ đếm được cập nhật đồng thời từ nhiều thread. Với trạng thái có quan hệ phụ thuộc giữa nhiều trường, hãy dùng khóa hoặc một cấu trúc đồng bộ phù hợp thay vì dựa vào việc callback thường chạy tuần tự trong các lần thử nghiệm.

Ngoài truy cập đồng thời, cần tính đến *reentrancy*: callback có thể gọi lại một hàm native, và hàm native đó có thể gọi tiếp callback trước khi lần callback ban đầu kết thúc. Tránh giữ khóa trong lúc gọi native nếu native có thể gọi ngược vào Java và cần cùng khóa; thiết kế như vậy dễ gây deadlock.

## 5. Không để exception thoát khỏi biên native

Target method handle của upcall stub không được ném exception. Tài liệu API nêu rõ nếu target ném exception, JVM sẽ kết thúc đột ngột. Đây là quy tắc khác với lời gọi phương thức Java thông thường: native caller không có cơ chế exception của Java để nhận và xử lý exception đó.

Vì vậy, callback nên tự bắt lỗi, ghi nhận lỗi theo cách thread-safe và trả về một giá trị nằm trong hợp đồng của callback. Ví dụ sau dùng hàng đợi concurrent để lưu lỗi từ nhiều callback thread:

```java
import java.util.concurrent.ConcurrentLinkedQueue;

public final class SafeCallback {
    private static final int CALLBACK_ERROR = -1;
    private static final ConcurrentLinkedQueue<Throwable> FAILURES =
            new ConcurrentLinkedQueue<>();

    private static int onValue(int value) {
        try {
            return processValue(value);
        } catch (Throwable failure) {
            FAILURES.add(failure);
            return CALLBACK_ERROR;
        }
    }

    public static void checkCallbackFailures() {
        Throwable failure = FAILURES.poll();
        if (failure != null) {
            throw new IllegalStateException(
                    "Callback native thất bại", failure);
        }
    }

    private static int processValue(int value) {
        return Math.multiplyExact(value, 2);
    }
}
```

`CALLBACK_ERROR` chỉ hợp lệ nếu giao thức native dành riêng giá trị đó để báo lỗi. Nếu không có giá trị trả về đặc biệt, hãy lưu lỗi vào hàng đợi hoặc trạng thái kết quả riêng và để Java kiểm tra sau khi native operation hoàn tất. Không ném lại exception từ `onValue`.

Sau khi downcall kết thúc và callback đã được drain, mã Java có thể gọi `checkCallbackFailures()` để xử lý lỗi theo luồng điều khiển Java thông thường. Với callback dài hạn, cần thiết kế kênh báo lỗi, chính sách dừng đăng ký và cách chuyển lỗi tới thread điều phối. Nếu bắt `Throwable` ở biên callback để bảo đảm không thoát exception, ứng dụng vẫn nên phân loại lỗi và quyết định cách phản ứng ở phía Java; việc ghi nhận lỗi không có nghĩa mọi lỗi đều có thể bỏ qua.

Có thể dùng `MethodHandles.catchException` để bọc method handle và chuyển exception sang một handler có cùng kiểu trả về phù hợp. Dù dùng combinator hay `try`/`catch` trực tiếp, điều kiện cuối cùng vẫn là target được truyền cho `upcallStub` không để exception thoát ra ngoài.

## 6. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đóng arena ngay sau khi đăng ký callback | Native code gọi một upcall stub đã bị giải phóng. | Giữ arena sống đến khi hủy đăng ký và mọi callback đã hoàn tất. |
| Hủy đăng ký nhưng không chờ callback đang chạy | Callback có thể tiếp tục dùng stub hoặc context trong lúc arena đóng. | Dùng cơ chế drain/join hoặc bảo đảm đồng bộ do native API cung cấp. |
| Dùng segment của confined arena trong callback từ thread khác | Có thể gặp `WrongThreadException`. | Dùng shared arena cho dữ liệu cần truy cập chéo thread hoặc chuyển dữ liệu sang cơ chế sở hữu phù hợp. |
| Giả định native library gọi callback tuần tự | Race condition khi nhiều callback cập nhật trạng thái chung. | Thiết kế callback thread-safe theo hợp đồng concurrency của thư viện. |
| Để exception thoát khỏi callback | JVM có thể kết thúc đột ngột. | Bắt lỗi tại callback boundary, ghi nhận và trả kết quả theo giao thức native. |
| Descriptor không khớp khai báo native | Sai quy ước gọi, dữ liệu sai hoặc JVM crash. | Kiểm tra ABI, kiểu tham số, kiểu trả về và layout trước khi tạo stub. |
| Giữ lock khi gọi native có thể callback ngược | Deadlock hoặc reentrancy khó kiểm soát. | Giảm vùng giữ lock và tránh gọi native trong khi giữ khóa cần thiết cho callback. |

## 7. Checklist triển khai callback

- Xác minh chữ ký C và `FunctionDescriptor` khớp chính xác với ABI đích.
- Tạo method handle có kiểu tương thích với descriptor.
- Dùng `Linker.upcallStub` và bật native access cho module gọi restricted method.
- Chọn arena dựa trên thời gian native giữ callback và thread có thể gọi callback.
- Giữ stub và mọi context/buffer liên quan sống đến sau callback cuối cùng.
- Hủy đăng ký callback và đợi callback đang chạy hoàn tất trước khi đóng arena.
- Thiết kế trạng thái Java an toàn khi callback đồng thời hoặc reentrant.
- Bắt mọi exception tại target callback; chuyển lỗi qua mã trả về hoặc kênh báo lỗi riêng.
- Xử lý lỗi đã ghi nhận sau khi quay lại luồng điều khiển Java.

Callback native là một ranh giới tài nguyên và luồng thực thi. Khi ứng dụng quản lý đúng vòng đời của upcall stub, xác định rõ thread có thể gọi callback và chặn exception ngay tại target method handle, việc gọi ngược từ native vào Java sẽ dễ dự đoán và an toàn hơn.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — FFM API được hoàn thiện trong JDK 22.
- [Linker, Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html) — `upcallStub`, chữ ký callback, vòng đời và yêu cầu xử lý exception.
- [Arena, Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html) — confined/shared arena và quản lý vòng đời.
- [Upcalls: Passing Java Code as a Function Pointer to a Foreign Function](https://docs.oracle.com/en/java/javase/25/core/upcalls-passing-java-code-function-pointer-foreign-function.html) — ví dụ upcall và cách truyền callback cho native function.
- [Linker, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/Linker.html) — đối chiếu API hiện hành và các giới hạn an toàn của upcall stub.
