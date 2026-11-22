# Gộp công việc để giảm số lần JNI, downcall và callback

## 1. Vì sao gộp công việc giúp tối ưu Java/native interop?

Java có thể gọi C/C++ bằng **JNI (Java Native Interface)** hoặc bằng **downcall** của Foreign Function & Memory API (FFM). Ở chiều ngược lại, native code gọi Java qua JNI callback hoặc một **FFM upcall stub**. Khi xử lý một số lượng lớn phần tử rất nhỏ, việc vượt ranh giới Java/native nhiều lần có thể tốn chi phí tương đối lớn so với chính phép toán.

Một crossing có thể bao gồm chuẩn bị chữ ký/đối số và kết quả theo ABI, thay đổi ngữ cảnh thực thi JVM/native, kiểm tra trạng thái/lifetime, truy xuất array/object, sao chép dữ liệu (nếu cần), điều phối callback và xử lý lỗi. Mức chi phí thật phụ thuộc JVM, API, CPU, JIT, chữ ký hàm, trạng thái dữ liệu và workload; không có một hằng số “JNI mất X ns” đúng cho mọi môi trường.

Ví dụ hai cách xử lý 10.000 số nguyên:

```text
Gọi lẻ:
Java ──transformOne(x0)──► C ──result──► Java
Java ──transformOne(x1)──► C ──result──► Java
... tổng cộng 10.000 lần Java → C

Gộp lô:
Java ──transformBatch(int[10_000])──► C
                    C lặp xử lý 10.000 phần tử
Java ◄────────────── mảng kết quả ──── C
... tổng cộng 1 lần Java → C
```

Cả hai có thể thực hiện cùng 10.000 phép tính. Cách gộp **giảm lượt crossing**, nhưng không mặc định nhanh hơn cùng tỷ lệ: thời gian cấp phát/copy buffer, latency chờ gom đủ lô, việc xử lý từng phần tử và áp lực bộ nhớ vẫn tồn tại.

Mục tiêu học tập: nhận diện các lời gọi “chatty”, đặt vòng lặp hợp lý ở phía native, chọn cấu trúc dữ liệu bulk, gộp callback, giữ đúng semantics và đo kết quả bằng benchmark phù hợp.

### Ba chiều crossing cần phân biệt

| Hướng | Cơ chế | Kiểu gọi nhiều lần | Gợi ý batch |
| --- | --- | --- | --- |
| Java → native | JNI native method | `nativeGet(index)` mỗi phần tử | `nativeGetRange(start, count, output)` |
| Java → native | FFM downcall qua `MethodHandle` | `process_one(pointer, index)` lặp lại | `process_many(pointer, count)` trên một buffer |
| Native → Java | JNI callback / FFM upcall | `onSample(value)` mỗi event | `onSamples(batch, count)` một lần mỗi lô |

Đổi JNI sang FFM chỉ thay đổi API giao tiếp; nếu vẫn downcall/upcall từng record nhỏ, vấn đề số lượt vượt biên chưa được giải quyết.

## 2. Mô hình chi phí và điểm cân bằng

Giả sử `N` phần tử cần xử lý và mỗi lô tối đa `B` phần tử. Nếu `N > 0`, số lô `K = ceil(N / B)`. Ước lượng mức khái niệm:

```text
T_total ≈ K_down × C_down
        + K_up   × C_up
        + T_native_compute
        + T_copy/serialize
        + T_allocation
        + T_queue/wait
```

Ở đây `C_down` và `C_up` là chi phí trung bình qua biên theo từng hướng; `K_down` và `K_up` là số lời gọi tương ứng. Công thức là mô hình giúp tìm nút thắt, **không** phải công thức suy ra tốc độ chính xác.

Với `N=10.000` và `B=512`, số lô là 20: gồm 19 lô 512 phần tử và một lô 272 phần tử. So với 10.000 JNI call riêng lẻ, còn 20 lần gọi, tức **giảm 500 lần về số lượt call**; không có nghĩa ứng dụng nhanh hơn 500 lần. Nếu native compute rất đắt, lợi ích từ giảm crossing có thể nhỏ; nếu việc copy dữ liệu tăng đột biến, batch thậm chí có thể chậm hơn.

Ba mục tiêu phải kiểm tra cùng lúc:

1. **Throughput:** bao nhiêu phần tử được xử lý mỗi giây.
2. **Latency:** mỗi phần tử đợi bao lâu đến khi có kết quả; đặc biệt p95/p99.
3. **Memory/concurrency:** lô và buffer đang chờ dùng bao nhiêu heap/off-heap, có gây backpressure hay giữ tài nguyên lâu không.

Batch lớn thường giảm overhead cố định trên mỗi phần tử nhưng có thể kéo dài thời gian chờ để đủ lô. Batch nhỏ đáp ứng nhanh hơn nhưng mất nhiều crossing hơn. Kích thước tối ưu phụ thuộc SLA/SLO, workload, bộ nhớ và loại xử lý.

## 3. Thiết kế API theo lô trước khi viết code

Một anti-pattern phổ biến:

```java
// Đoạn minh họa; mỗi vòng thực hiện một native call.
for (int i = 0; i < input.length; i++) {
    output[i] = nativeTransformOne(input[i]);
}
```

Đưa cùng vòng lặp sang native:

```java
// Chữ ký minh họa; ví dụ JNI chạy đầy đủ ở mục 4.
private static native void nativeTransformBatch(int[] values);

nativeTransformBatch(values); // Một crossing cho cả mảng.
```

Nếu input quá lớn hoặc đến theo stream, cần chia chunk có giới hạn:

```java
// Hợp đồng minh họa; native PHẢI kiểm tra offset/length.
private static native void nativeTransformRange(int[] values, int offset, int length);

for (int offset = 0; offset < values.length; offset += batchSize) {
    int length = Math.min(batchSize, values.length - offset);
    nativeTransformRange(values, offset, length);
}
```

Phải tính phần dư và tránh vòng lặp vô hạn: `batchSize` cần dương; với mảng quá lớn, xem xét nguy cơ overflow chỉ số và cách phân trang. Ví dụ trên minh họa thiết kế, không phải một lớp Java độc lập có implementation native.

Một hợp đồng bulk tốt nói rõ:

- **Input và layout:** kiểu phần tử, kích thước, byte order, alignment, offset, length, null/empty, encoding với chuỗi hoặc cấu trúc record.
- **Output:** in-place hay output buffer riêng, thứ tự theo input hay unordered, result count, trạng thái từng phần tử.
- **Lỗi:** cả lô fail hay partial success; cách báo failed index, lỗi JNI/OS, retry có idempotent không.
- **Ownership:** ai cấp phát, ai giải phóng, con trỏ được giữ tới khi nào, buffer có được dùng sau khi hàm return không.
- **Song song:** shared handle, thread affinity, synchronization, giới hạn các batch đồng thời.
- **Hủy và timeout:** xử lý bản ghi cuối cùng, flush khi end-of-stream, shutdown và callback tới muộn.

Không được tùy ý gộp các thao tác có ý nghĩa giao dịch độc lập rồi giả định chúng trở thành một transaction nguyên tử. Phải xác định rõ semantics về side effects và partial failures.

## 4. Ví dụ chạy được với Java 17+ và JNI: scalar so với bulk

Ví dụ dùng phép biến đổi `x ^ 0x5A` trên mảng số nguyên. Java gọi một hàm native cho từng phần tử ở đường scalar; ở đường batch, native nhận cả `int[]` và thực hiện vòng lặp. Kết quả hai đường phải bằng nhau.

**Tệp `JniBatchDemo.java`:**

```java
import java.util.Arrays;

public final class JniBatchDemo {
    static { System.loadLibrary("jnibatch"); }

    private static native int transformOne(int value);
    private static native void transformBatch(int[] values);

    public static void main(String[] args) {
        int[] input = {1, 2, 3, 4, 5, 6, 7};
        int[] scalar = input.clone();
        int[] batch = input.clone();

        for (int i = 0; i < scalar.length; i++) {
            scalar[i] = transformOne(scalar[i]);
        }
        transformBatch(batch);

        if (!Arrays.equals(scalar, batch)) {
            throw new AssertionError("Different results");
        }
        System.out.println("scalar JNI calls=" + scalar.length);
        System.out.println("batch JNI calls=1");
        System.out.println("result=" + Arrays.toString(batch));
    }
}
```

**Tệp `jni_batch.c`:**

```c
#include <jni.h>
#include <stdint.h>
#include <stddef.h>

static jint transform(jint value) {
    return value ^ 0x5A;
}

JNIEXPORT jint JNICALL
Java_JniBatchDemo_transformOne(JNIEnv *env, jclass cls, jint value) {
    (void)env;
    (void)cls;
    return transform(value);
}

JNIEXPORT void JNICALL
Java_JniBatchDemo_transformBatch(JNIEnv *env, jclass cls, jintArray values) {
    (void)cls;
    jsize length = (*env)->GetArrayLength(env, values);
    jint *items = (*env)->GetIntArrayElements(env, values, NULL);
    if (items == NULL) return; // OutOfMemoryError pending.

    for (jsize i = 0; i < length; i++) {
        items[i] = transform(items[i]);
    }
    (*env)->ReleaseIntArrayElements(env, values, items, 0);
}

// Cùng thư viện dùng cho ví dụ FFM ở phần sau.
int transform_buffer(int32_t *items, int32_t length) {
    if (length < 0 || (items == NULL && length != 0)) return -1;
    for (int32_t i = 0; i < length; i++) {
        items[i] ^= 0x5A;
    }
    return length;
}
```

Trên **Linux** có GCC và JDK 17 trở lên, mở terminal ở thư mục chứa hai tệp:

```bash
javac -h . JniBatchDemo.java
gcc -std=c11 -O2 -shared -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjnibatch.so jni_batch.c
java -Djava.library.path=. JniBatchDemo
```

`JAVA_HOME` cần trỏ đến JDK đang dùng. `javac -h .` sinh JNI header để đối chiếu tên hàm; vì lớp không có package, C symbol là `Java_JniBatchDemo_...`. Trên Windows/macOS, đường dẫn JNI header, tên thư viện và lệnh compiler/linker khác.

**Stdout:**

```text
scalar JNI calls=7
batch JNI calls=1
result=[91, 88, 89, 94, 95, 92, 93]
```

Đây là phép đếm **lời gọi trong chương trình**, không phải phép đo thời gian chạy. Phép XOR luôn thực hiện 7 lần trên cùng dữ liệu.

Cơ chế `GetIntArrayElements`: JVM có thể trả pointer đã pin hoặc pointer đến một bản copy; `ReleaseIntArrayElements(..., 0)` commit dữ liệu sửa đổi và release. Vì vậy “JNI call giảm” không nhất thiết là “copy giảm”; để chọn JNI array hay buffer khác, phải đo. Mã C minh họa giả định mảng không null và sở hữu hợp lệ trong suốt lời gọi; production cần validation, error handling và giới hạn tài nguyên đầy đủ.

### Vùng JNI critical không phải giải pháp batching mặc định

`GetPrimitiveArrayCritical` đôi khi giảm copy/pinning overhead nhưng là vùng có ràng buộc đặc biệt: không gọi các hàm JNI khác hoặc thao tác có thể chặn chờ Java thread ở giữa `Get...Critical` và `Release...Critical`; thời gian giữ phải ngắn. Đừng xử lý một batch rất dài dưới critical, giữ mutex lâu, đợi I/O hoặc gọi callback Java khi còn nằm trong vùng này. `GetIntArrayElements`, `GetIntArrayRegion` và direct buffer có chi phí/vòng đời khác nhau: thử trên workload thật.

## 5. FFM downcall: gom buffer và tạo MethodHandle một lần

**FFM ổn định từ Java 22** trong `java.lang.foreign` (JEP 454). `Linker.nativeLinker().downcallHandle(...)` gọi hàm native bằng một `MethodHandle`; nếu gọi hàm native để xử lý mỗi số nguyên, ta vẫn có nhiều crossing. Một `MemorySegment` chứa nhiều phần tử cho phép một downcall tới hàm C nhận pointer và length.

Ví dụ đầy đủ dưới đây dùng chính `libjnibatch.so` được tạo ở mục 4 và symbol C `transform_buffer` đã khai báo. Chạy với **JDK 22+**.

**Tệp `FfmBatchDemo.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Arrays;

public final class FfmBatchDemo {
    public static void main(String[] args) throws Throwable {
        int[] values = {1, 2, 3, 4, 5, 6, 7};
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup library = SymbolLookup.libraryLookup(
                    Path.of("./libjnibatch.so").toAbsolutePath(), arena);
            MemorySegment symbol = library.find("transform_buffer").orElseThrow();
            MethodHandle process = Linker.nativeLinker().downcallHandle(
                    symbol,
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.JAVA_INT));
            MemorySegment buffer = arena.allocate(
                    (long) values.length * ValueLayout.JAVA_INT.byteSize(),
                    ValueLayout.JAVA_INT.byteAlignment());
            for (int i = 0; i < values.length; i++) {
                buffer.setAtIndex(ValueLayout.JAVA_INT, i, values[i]);
            }
            int processed = (int) process.invokeExact(buffer, values.length);
            if (processed != values.length) throw new IllegalStateException("Native failure");
            for (int i = 0; i < values.length; i++) {
                values[i] = buffer.getAtIndex(ValueLayout.JAVA_INT, i);
            }
        }
        System.out.println("FFM downcalls=1");
        System.out.println("result=" + Arrays.toString(values));
    }
}
```

Ở cùng thư mục có `libjnibatch.so`:

```bash
javac FfmBatchDemo.java
java --enable-native-access=ALL-UNNAMED FfmBatchDemo
```

Khi thư viện native được liên kết và nạp đúng, kết quả:

```text
FFM downcalls=1
result=[91, 88, 89, 94, 95, 92, 93]
```

Giải thích kỹ:

1. `SymbolLookup` tìm symbol, `FunctionDescriptor` mô tả ABI C, còn `downcallHandle` tạo handle cho `int transform_buffer(int32_t*, int32_t)` trên Linux thông dụng (C `int` 32-bit). Ứng dụng thực nên resolve symbol và tạo handle **một lần cho mỗi lifetime phù hợp**, tái sử dụng cho các lô.
2. `MemorySegment` chứa một dãy `int` liên tục ngoài heap; Java copy input vào buffer và đọc lại sau downcall. Chỉ crossing một lần, nhưng vẫn có thời gian cấp phát và copy.
3. `Arena.ofConfined()` giới hạn lifetime và thread được phép truy cập. Đóng arena khi con trỏ không còn được native worker/callback sử dụng; không chuyển pointer cho luồng bất đồng bộ rồi đóng trước khi luồng xử lý xong.
4. `--enable-native-access=ALL-UNNAMED` phù hợp ví dụ classpath; ứng dụng named module phải cấu hình native access phù hợp. Không dùng API ổn định này nguyên xi trên JDK 17 hoặc 21.

FFM upcall là hướng ngược lại: C có thể gọi Java qua pointer do `Linker.upcallStub` tạo. Nếu C gọi một upcall cho từng record, overhead vẫn lặp lại. Thiết kế upcall nhận pointer tới nhiều phần tử cùng `count`, nhưng phải bảo đảm layout, lifetime, đồng bộ, quy tắc callback và xử lý lỗi. Không giữ Java `MemorySegment` hoặc con trỏ C ngoài phạm vi hợp lệ.

## 6. Gộp callback: giảm số lần C → Java

Ở chiều callback, thay vì `onEvent(e)` cho từng phần tử, native code gom event và gọi `onEvents(batch, count)`. Ví dụ 7 event chia lô 3 phần tử:

```text
Không batch:
onEvent(1), onEvent(2), ..., onEvent(7)
=> 7 callback C → Java

Batch size = 3:
onEvents([1,2,3])
onEvents([4,5,6])
onEvents([7])             <- phải flush phần dư
=> 3 callback C → Java
```

Ba cách kích hoạt flush:

- **Count threshold:** đủ `B` event thì phát một callback.
- **Time threshold:** phần tử đầu tiên không được chờ quá `maxWait` dù chưa đủ `B`.
- **Lifecycle threshold:** flush khi end-of-stream, close hoặc shutdown nếu hợp đồng yêu cầu không mất event.

Khi cần collapse các thay đổi cùng key (chỉ gửi trạng thái cuối), đó là **coalescing theo ngữ nghĩa**, chỉ hợp lệ nếu người nhận không cần thấy toàn bộ sự kiện trung gian. Không gộp mất event giao dịch, audit hoặc thứ tự bắt buộc.

Giao diện C minh họa, không phải chương trình độc lập:

```c
#include <stddef.h>
#include <stdint.h>

typedef void (*event_batch_callback)(
    const int32_t *events, size_t count, void *context);

/* Hợp đồng:
 * events hợp lệ trong khoảng callback đang thực thi;
 * callback muốn xử lý async phải copy hoặc retain với ownership rõ;
 * producer không giữ mutex native khi gọi vào Java;
 * count, layout và thứ tự sự kiện được định nghĩa.
 */
```

**Không giữ mutex C khi callback vào Java**: callback có thể tái nhập C để truy cập cùng tài nguyên và gây deadlock. Nếu xử lý callback trên executor khác, dữ liệu phải được copy hoặc giữ một vùng nhớ còn sống; pointer stack/native chỉ hợp lệ đến khi hàm gọi hoàn tất không thể giữ cho một tác vụ async tùy ý. Cần giới hạn hàng đợi và định nghĩa backpressure.

### Ví dụ Java 17: batch callback theo số lượng

Đây là **chương trình Java độc lập mô phỏng callback**, không tự kết nối JNI. Mục đích là cho thấy cách gom event và gọi listener **sau khi nhả khóa**. Tệp `CallbackBatchingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public final class CallbackBatchingDemo {
    private static final class Batcher {
        private final int limit;
        private final Consumer<List<Integer>> callback;
        private final List<Integer> pending = new ArrayList<>();

        Batcher(int limit, Consumer<List<Integer>> callback) {
            if (limit <= 0) throw new IllegalArgumentException("limit");
            this.limit = limit;
            this.callback = callback;
        }

        void accept(int event) {
            List<Integer> ready = null;
            synchronized (pending) {
                pending.add(event);
                if (pending.size() >= limit) {
                    ready = List.copyOf(pending);
                    pending.clear();
                }
            }
            if (ready != null) callback.accept(ready);
        }

        void flush() {
            List<Integer> ready = null;
            synchronized (pending) {
                if (!pending.isEmpty()) {
                    ready = List.copyOf(pending);
                    pending.clear();
                }
            }
            if (ready != null) callback.accept(ready);
        }
    }

    public static void main(String[] args) {
        int[] callbackCount = {0};
        Batcher batcher = new Batcher(3, events -> {
            callbackCount[0]++;
            System.out.println("callback " + callbackCount[0] + ": " + events);
        });
        for (int event = 1; event <= 7; event++) batcher.accept(event);
        batcher.flush();
        System.out.println("total callbacks=" + callbackCount[0]);
    }
}
```

```bash
javac CallbackBatchingDemo.java
java CallbackBatchingDemo
```

**Stdout:**

```text
callback 1: [1, 2, 3]
callback 2: [4, 5, 6]
callback 3: [7]
total callbacks=3
```

`List.copyOf` tạo snapshot riêng; callback không bị gọi khi đang giữ monitor của `pending`. Ví dụ chỉ có batch theo số lượng và giả định producer tuần tự. Hệ thống thực cần có timer maxWait, close/cancel, exception policy và bounded queue. Nếu nhiều producer gọi `accept` cùng lúc, thứ tự **dispatch** callback không tự được bảo đảm chỉ vì phần gom lô nằm trong `synchronized`; có thể dùng single-threaded dispatcher hoặc sequence number. Nếu callback ném exception khi lô đã bị xóa, cần retry/idempotency hoặc báo lỗi rõ ràng.

## 7. Buffer và vòng đời: tránh tối ưu call count nhưng làm hỏng bộ nhớ

| Cách truyền dữ liệu | Khi hữu ích | Chi phí hoặc hạn chế |
| --- | --- | --- |
| JNI `int[]` + `GetIntArrayElements` / `Release...` | Xử lý một batch các primitive Java | JVM có thể copy hoặc pin; phải release đúng mode |
| JNI `GetIntArrayRegion` / `SetIntArrayRegion` | Trao đổi chunk theo offset/length | Copy theo vùng, cần bounds checking |
| Direct `ByteBuffer` / `GetDirectBufferAddress` | Cùng đọc buffer off-heap trong một lifetime đã kiểm soát | Đòi hỏi đúng direct buffer, capacity, alignment/endian, ownership |
| FFM `MemorySegment` + `Arena` | Buffer native rõ bounds và lifetime, thuận tiện downcall | Alloc/copy, thread confinement và native access |
| Native callback kèm pointer và count | Trả một lô thay vì từng event | Phải giữ buffer sống đến khi callback xử lý xong; async phải copy/retain |

“Zero-copy” là một yêu cầu cần kiểm chứng, không phải một nhãn mặc định cho direct buffer hoặc FFM. Mỗi kỹ thuật khác nhau ở số lần copy, phạm vi pin, GC pressure, safety và latency.

Nếu batch chạy bất đồng bộ, một vùng nhớ được tạo trong hàm Java rồi đóng/hủy ngay sau khi schedule tác vụ là **không an toàn** nếu native vẫn đang giữ pointer. Thiết kế ownership phải ghi rõ người tạo, nơi sử dụng, khi nào hoàn tất và ai giải phóng. Không dùng `JNIEnv*` từ luồng A trên luồng B; nếu native thread tự gọi Java phải attach theo JNI và quản lý global reference cho object sống qua lời gọi bất đồng bộ.

**Đồng bộ:** snapshot input/state trong khóa ngắn, nhả khóa, sau đó gọi JNI/downcall hoặc callback. Callback commit trạng thái ngắn rồi dispatch listener bên ngoài khóa; không đợi worker/future khi đang giữ monitor Java hoặc mutex native. Batching giảm số lượt crossing nhưng có thể tạo deadlock nếu tăng thời gian giữ khóa.

## 8. Semantics khi batch có lỗi và kết quả từng phần

API bulk không được đánh đổi tính đúng đắn để lấy throughput:

1. **All-or-nothing:** chỉ commit khi mọi phần tử hợp lệ; nếu đã gây side effect bên ngoài, cần cơ chế transaction/compensation rõ ràng.
2. **Partial success:** trả số đã xử lý cùng `status[]`/`failedIndices[]` hoặc `(requestId, status)` cho từng item; xử lý phần dư và output order đúng hợp đồng.
3. **Retry:** chỉ retry phần có thể lặp an toàn, dùng idempotency key nếu có side effect; không tự chạy lại cả lô chưa biết phần nào đã hoàn tất.
4. **Callback trùng hoặc tới muộn:** gắn batchId/sequence/generation, chỉ hoàn tất request một lần, nhận biết sự kiện từ phiên đã hủy/đóng.
5. **Exception JNI/FFM/native:** chuyển native status sang Java có ngữ cảnh; không bỏ qua pending exception JNI rồi gọi tùy tiện API cấm; không dựa vào Java exception tự truyền xuyên C ABI của FFM.
6. **Backpressure:** bounded queue; nếu producer quá nhanh, có thể block, từ chối, drop hoặc coalesce tùy yêu cầu dữ liệu. Với sự kiện không được mất, không tự chọn drop.

Một interface `processBatch` nên mô tả rõ thứ tự thực thi, side effect, lifetime buffer và trạng thái mỗi item. Kết quả nhanh nhưng thiếu một event hay ghi trùng transaction là tối ưu sai.

## 9. Chọn kích thước lô và chính sách flush

Các mức thử nghiệm có thể là `B = 1, 16, 64, 256, 1024, 4096`, nhưng đây **chỉ là các điểm đo**. Không có cấu hình tốt nhất chung.

| Kiểu ứng dụng | Ưu tiên | Điều dễ xảy ra |
| --- | --- | --- |
| Batch offline, không yêu cầu phản hồi sớm | Lô lớn hơn, chunk cố định | Peak memory, long native call |
| Stream có SLA phản hồi | Batch theo count **và** maxWait | Đợi đủ lô làm tăng p99 |
| Native compute rất nhẹ | Giảm crossing, reuse buffer | Copy/alloc có thể vẫn chiếm đa số |
| Native compute rất nặng | Cân bằng batching với fair scheduling/cancel | Giảm call count nhưng ít cải thiện tổng thời gian |
| Event callback thưa | Flush theo thời gian hoặc lifecycle | Lô cuối tồn vô hạn |
| Nhiều producer, consumer chậm | Bounded queue và backpressure | RAM tăng, callbacks reorder |

Ví dụ payload của 512 số nguyên 32-bit là 2.048 byte. Nếu có 100 lô đồng thời, mỗi lô sở hữu cả input và output 2.048 byte, riêng payload đã khoảng 400 KiB, chưa tính object metadata, alignment, queue và vùng nhớ copy trung gian. Peak memory quan trọng không kém kích thước một lô.

Để không mất dữ liệu, flush lô cuối khi stream kết thúc; để không chờ mãi, flush sau `maxWait` kể từ event đầu nếu lô chưa đủ; để tránh buffer vô hạn, chặn/shed tải có chính sách. Callback có thể trả kết quả sau khi request bị hủy, nên cần requestId/generation.

## 10. Benchmark đúng: chứng minh throughput và latency

**Kiểm thử correctness tách khỏi phép đo hiệu năng.** Trước hết đối chiếu scalar và batch trên input rỗng, một phần tử, ranh giới kích thước, batch cuối không đủ lô, null/bounds, exception, callback trùng/trễ, chạy nhiều luồng và hủy. Cần kiểm tra **số native calls thực tế**, nhưng đừng đồng nhất phép đếm này với thời gian tiết kiệm.

Sau đó dùng **JMH** cho Java microbenchmark và benchmark end-to-end cho queue/callback/I/O. Các chiều đo:

| Chiều kiểm thử | Các mức nên thử |
| --- | --- |
| API | Java thuần tham chiếu; JNI scalar/batch; FFM scalar/batch |
| Số item | 0, 1, 32, 512, 10.000, 100.000 |
| Cỡ lô | 1, 16, 64, 256, 1024, 4096, cả mảng nếu phù hợp |
| Data transport | Java primitive array, region copy, direct/off-heap segment |
| Công việc native | No-op, phép toán nhẹ, business compute thực |
| Callback | Mỗi event; theo count; count + maxWait |
| Concurrency | 1 luồng, tải sản xuất và burst |

Đo throughput (items/s hoặc ops/s với **đơn vị công việc tương đương**), CPU, allocations/GC, native memory, bytes copied, số crossing, queue depth, p50/p95/p99 event latency. Có warmup và nhiều iteration/fork, tiêu thụ kết quả để JIT không tối ưu hóa bỏ phép toán; không đưa một lần đo bằng `System.nanoTime` làm chứng cứ chính.

Đặc biệt với callback: thời gian gọi callback giảm chưa đủ nếu event đầu đợi rất lâu trong buffer. **Latency end-to-end tính từ lúc event xuất hiện** mới phản ánh hiệu quả đối với người dùng. Không tuyên bố “nhanh hơn X lần” khi chưa đo trên môi trường thật.

### Một ví dụ cách đọc kết quả

Nếu đo cho thấy JNI scalar mất nhiều CPU khi xử lý các record 1–2 byte, còn JNI bulk giảm đáng kể thời gian nhưng làm p99 callback vượt SLA, hãy giữ bulk cho đường offline và dùng `maxWait`/batch nhỏ hơn cho đường realtime. Nếu native tính toán mỗi phần tử mất hàng mili-giây, crossing có thể không phải nút thắt chính; tối ưu hóa thuật toán C trước có thể hiệu quả hơn thay đổi API.

## 11. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Khắc phục |
| --- | --- | --- |
| JNI/downcall từng phần tử trong vòng lặp Java | Mỗi item gây một crossing | Nhận array/segment/range, đưa vòng lặp vào native |
| Resolve symbol/tạo `downcallHandle` cho mỗi item | Thừa setup | Tạo/reuse trong đúng lifetime rồi gọi theo lô |
| C callback Java từng record nhỏ | Nhiều upcall, scheduler/listener overhead | Event batch, count/maxWait/close flush |
| Chỉ flush khi đủ `B` | Lô cuối bị giữ mãi | Flush theo thời gian và end-of-stream |
| Luôn batch cả dataset | Bộ nhớ lớn, latency và fairness kém | Chunk có giới hạn, quan sát p99 |
| Dùng `GetPrimitiveArrayCritical` suốt batch dài | Vi phạm vùng critical/có thể cản GC | Critical ngắn, không callback/chặn, cân nhắc region/direct |
| Gộp nhưng không định nghĩa partial error | Retry sai, nhân đôi side effects | Per-item status, batchId, idempotency |
| Giữ mutex Java/C khi native call/callback | Reentrancy/deadlock | Snapshot → unlock → crossing → commit state |
| Dùng native pointer sau khi arena/buffer hết hạn | Use-after-free/crash | Lifetime rõ, copy/retain async và orderly close |
| Thấy call count ít hơn rồi kết luận nhanh hơn | Bỏ qua copy, alloc, queue latency | JMH + end-to-end đo thật và check correctness |

## 12. Quy trình thực hành để cải tiến một API thực tế

1. **Đếm crossing và vẽ luồng dữ liệu:** Java → JNI/downcall → C → callback/upcall → Java, số item mỗi request và trạng thái/thread.
2. **Xác định nút thắt:** CPU profile, độ nặng công việc, copy/alloc, callback volume, queue và latency.
3. **Chọn đơn vị batch:** nhóm phần tử có cùng contract, giữ thứ tự và semantics; thiết kế API `processBatch(data, count, statuses)`.
4. **Thiết kế buffer:** định nghĩa ownership, offset, alignment, thread, lifetime; không cấp phát từng item nếu có thể reuse an toàn.
5. **Gộp callback:** chỉ khi semantics cho phép; thêm count + maxWait + end flush và bounded queue.
6. **Kiểm tra đúng đắn:** scalar/bulk cho cùng output, xử lý phần dư, lỗi một item, timeout, cancellation, callback trùng/reentrant.
7. **Benchmark và điều chỉnh:** thử nhiều `B`, so throughput, CPU, memory, p95/p99; chỉ chấp nhận nếu đạt yêu cầu dịch vụ và giữ nguyên semantics.

**Nguyên tắc:** giảm số lần vượt biên bằng cách chuyển **một nhóm công việc nhất quán** qua mỗi JNI/downcall hoặc callback. Việc ít lời gọi hơn là tính chất của thiết kế; nhanh hơn và an toàn hơn phải được chứng minh bằng correctness, đo hiệu năng và kiểm soát vòng đời.

### Tài liệu tham khảo

- [Oracle JNI Specification — JNI Functions, Array Elements và Critical Arrays](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Java SE 22 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
