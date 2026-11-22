# sun.misc.Unsafe: kiểm kê cách dùng và lựa chọn API thay thế

## 1. Vì sao `sun.misc.Unsafe` là điểm rủi ro khi nâng cấp Java?

`sun.misc.Unsafe` là lớp từng được nhiều thư viện Java sử dụng để thực hiện các thao tác cấp thấp nằm ngoài mô hình an toàn thông thường của ngôn ngữ: đọc/ghi bộ nhớ theo offset, thao tác nguyên tử, truy cập vùng nhớ ngoài heap, quản lý fence, cấp phát đối tượng không đi qua constructor, và một số thao tác đặc biệt khác. Một phần các khả năng này phục vụ hiệu năng hoặc triển khai framework, nhưng chúng cũng có thể phá vỡ các bảo đảm về type safety, quản lý vòng đời bộ nhớ và đóng gói của JVM.

Khi chuyển từ một phiên bản JDK sang phiên bản khác, vấn đề không chỉ là “có import `sun.misc.Unsafe` hay không”. Dự án có thể gặp các tình huống:

- Source dùng trực tiếp field, method hoặc instance của `Unsafe`.
- Framework hoặc dependency bắc cầu truy cập `Unsafe` bên trong JAR.
- Code dùng reflection để lấy singleton `theUnsafe` hoặc gọi các method theo tên.
- Bytecode được sinh động, JNI, native library hoặc class loader dựa trên cấu trúc bộ nhớ riêng của JVM.
- Một bản build chạy được trên máy phát triển nhưng thất bại ở CI hoặc production do module access, phiên bản dependency hay runtime image khác.
- Một thao tác vẫn chạy nhưng semantics về memory ordering, alignment hoặc lifetime không còn phù hợp sau migration.

`sun.misc.Unsafe` thuộc tập API không được khuyến nghị làm hợp đồng ứng dụng. Từ Java 9, một số API tương thích như `sun.misc.Unsafe` được cung cấp qua module `jdk.unsupported`, nhưng điều đó không biến chúng thành API Java SE được bảo đảm ổn định. Cũng không nên chuyển sang `jdk.internal.misc.Unsafe` như một “bản nâng cấp” vì đây vẫn là API nội bộ của JDK, chịu ràng buộc đóng gói và không phải lựa chọn công khai, bền vững.

Mục tiêu của bài học là **kiểm kê đúng cách dùng `Unsafe`**, phân loại rủi ro theo hành vi thực tế, rồi chọn API Java được hỗ trợ để thay thế. Việc thay thế phải được kiểm chứng bằng test và benchmark phù hợp; không thể mặc định mỗi lời gọi `Unsafe` có một lời gọi thay thế tương đương về mọi khía cạnh.

## 2. Phân biệt “trực tiếp dùng”, “gián tiếp dùng” và “thực sự cần”

Một hệ thống có thể chứa `Unsafe` ở nhiều tầng. Trước khi sửa, cần trả lời ba câu hỏi riêng:

1. **Ai sử dụng?** Mã ứng dụng tự viết, thư viện nội bộ, dependency bên ngoài, agent instrumentation hay code sinh ra tại runtime?
2. **Dùng để làm gì?** CAS trên field, đọc mảng, cấp phát off-heap, serialization, park/unpark, hay thao tác khác?
3. **Có thực sự cần thay trực tiếp ở ứng dụng không?** Dependency đã có bản mới dùng API hỗ trợ chưa, hay API công khai của framework đã cung cấp đúng chức năng?

Ví dụ, phát hiện `Unsafe` trong một JAR của thư viện serialization không có nghĩa nhóm phải tự viết lại bộ serializer. Hướng ưu tiên là xác định phiên bản thư viện hỗ trợ JDK mục tiêu, xem release notes và nâng dependency tương thích. Chỉ khi ứng dụng thực sự sở hữu logic cấp thấp hoặc không có bản hỗ trợ phù hợp mới cần thiết kế lại phần sử dụng đó.

Ngược lại, nếu source ứng dụng gọi `Unsafe.allocateMemory()` và lưu native address trong một field `long`, đây là trách nhiệm trực tiếp của nhóm. Cần xác định ownership của vùng nhớ, quy tắc giải phóng và thread sharing trước khi thay thế.

### 2.1. Ba mức kết luận khi phát hiện

| Phát hiện | Ví dụ | Bước tiếp theo |
| --- | --- | --- |
| Sử dụng trực tiếp | `import sun.misc.Unsafe;` trong source ứng dụng | Kiểm kê từng call site và thiết kế API thay thế |
| Sử dụng gián tiếp | `jdeps --jdk-internals` báo một dependency | Xác định artifact/phiên bản, tìm bản nâng cấp được hỗ trợ |
| Chỉ có dấu vết, chưa chứng minh đường chạy | Chuỗi `sun.misc.Unsafe` trong code sinh, shaded JAR hoặc log | Xác định class được nạp và tính năng nào thực sự đi qua đường này |

Một chuỗi text hoặc cảnh báo analyzer là điểm khởi đầu điều tra, chưa đủ để quyết định sửa hay bỏ qua. Cần tìm đường gọi cụ thể, runtime thực tế và tác động nếu thay đổi.

## 3. Kiểm kê `Unsafe` trong mã nguồn và artifact

### 3.1. Tìm kiếm ở source và build configuration

Nên bắt đầu từ import, tên lớp và tên method. Ví dụ với công cụ tìm kiếm text trong repository:

~~~bash
rg -n 'sun[.]misc[.]Unsafe|jdk[.]internal[.]misc[.]Unsafe' src
rg -n 'theUnsafe|objectFieldOffset|allocateMemory|copyMemory' src
rg -n 'compareAndSwap|compareAndSet|putOrdered|loadFence|storeFence' src
rg -n 'allocateInstance|defineClass|park\(|unpark\(' src
~~~

Các lệnh là ví dụ dành cho môi trường có `rg` (ripgrep); không phải mọi dự án đều có công cụ này. Trong Windows PowerShell, có thể dùng `Get-ChildItem` cùng `Select-String` theo quy ước của repository.

Ngoài source chính, cần xem:

- Mã test, test utility và benchmark nội bộ.
- Generated source và annotation processor.
- Plugin build, code generator và tooling chạy trong CI.
- Các module dùng reflection để lấy `theUnsafe` mà không import trực tiếp.
- Source đa nền tảng hoặc source set dành riêng cho JDK (nếu có).

Đừng dừng ở từ khóa `Unsafe`. Có thể code sử dụng `MethodHandles`/reflection để gọi method theo tên, lưu class name trong resource, hoặc tải lớp một cách động.

### 3.2. Phân tích dependency bằng `jdeps`

`jdeps` là công cụ đi kèm JDK, có thể tìm tham chiếu tĩnh tới API nội bộ. Ví dụ:

~~~bash
jdeps --jdk-internals application.jar
jdeps --jdk-internals --recursive library.jar
~~~

Với multi-release JAR, có thể cần chỉ định mức release mục tiêu:

~~~bash
jdeps --multi-release 21 --jdk-internals library.jar
~~~

Kết quả giúp xác định lớp nào đang tham chiếu đến API không được hỗ trợ, trong đó có `sun.misc.Unsafe`. Tuy nhiên, `jdeps` chủ yếu phân tích liên kết ở class file; nó không thể bảo đảm tìm hết truy cập động qua reflection, method handle được xây dựng từ chuỗi, code sinh tại runtime hoặc JNI. Một kết quả “không phát hiện” vì vậy không chứng minh tuyệt đối rằng ứng dụng không dùng Unsafe.

Nếu ứng dụng có classpath phức tạp, cần phân tích đúng artifact và dependency đã đóng gói cho runtime. Không nên dùng một JAR không đầy đủ để kết luận về toàn bộ sản phẩm.

### 3.3. Xác định bản JAR thật được nạp

Trong migration, version mà build script khai báo có thể khác version thực tế được đưa vào container, shaded JAR hoặc runtime classpath. Vì vậy, kiểm kê nên ghi:

- Group/artifact/version của dependency trực tiếp và bắc cầu.
- Phiên bản framework, JDK và build tool.
- Loại artifact: normal JAR, fat/uber JAR, shaded JAR, agent JAR hay native image.
- Môi trường thực tế: local, CI, integration, staging, production.
- Đường thực thi có kích hoạt lời gọi `Unsafe` hay không.

Khi cần, dùng công cụ dependency graph tương ứng, ví dụ:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency target-artifact \
    --configuration runtimeClasspath
mvn dependency:tree
~~~

Đây là các lệnh tham khảo cho khâu điều tra, không phải điều kiện để sửa tài liệu này. Với plugin hoặc agent, cần xem cả classpath build/runtime riêng vì không phải dependency nào cũng xuất hiện trong `runtimeClasspath` của ứng dụng.

## 4. Mẫu bảng kiểm kê cho một đợt migration

Mỗi phát hiện nên có một bản ghi đủ để nhóm khác tiếp nhận, đánh giá và lên kế hoạch:

| Trường | Ý nghĩa |
| --- | --- |
| ID phát hiện | Mã issue để truy vết |
| Module/artifact | Thành phần sở hữu hoặc phụ thuộc |
| Phiên bản hiện tại/mục tiêu | Ví dụ runtime Java 17 → Java 21/22 |
| API `Unsafe` đang dùng | Tên method/field thực tế |
| Hành vi cần giữ | CAS, off-heap, fence, object creation, parking... |
| Đường sử dụng | Class, method, luồng nghiệp vụ, môi trường |
| Sở hữu | Code ứng dụng hay thư viện bên thứ ba |
| Rủi ro | Memory safety, module access, crash, hiệu năng, semantics |
| API thay thế dự kiến | VarHandle, Atomic*, FFM, ByteBuffer, LockSupport... |
| Ràng buộc | JDK tối thiểu, thread, alignment, lifecycle |
| Bằng chứng | Log, static analysis, test, benchmark, issue upstream |
| Quyết định | Sửa trực tiếp, nâng dependency, tạm giữ có kiểm soát |
| Owner/mốc hoàn thành | Người chịu trách nhiệm và release gate |

Ví dụ một mục kiểm kê:

~~~text
ID: JAVA-UNSAFE-014
Artifact: order-engine.jar
Call site: com.example.queue.SequenceCounter
Unsafe API: compareAndSwapLong(Object, long, long, long)
Purpose: CAS trên trường sequence của một đối tượng
Current JDK: 17
Target JDK: 21
Candidate: VarHandle.compareAndSet
Compatibility requirement: CAS atomic, không mất cập nhật khi đa luồng
Verification: concurrent stress test; linearizability review
Owner: Platform
~~~

Không nên xếp mọi lời gọi vào cùng một hạng mục “replace Unsafe”. Một ứng dụng có thể dùng `Unsafe` cho CAS, off-heap memory và object allocation; ba trường hợp này có cơ chế thay thế và tiêu chí kiểm chứng hoàn toàn khác nhau.

## 5. Ma trận lựa chọn API thay thế theo mục đích

| Nhóm cách dùng `Unsafe` | Ví dụ method cũ | Lựa chọn API được hỗ trợ | Điểm cần xem xét |
| --- | --- | --- | --- |
| CAS trên field | `compareAndSwapInt`, `compareAndSwapLong`, `compareAndSwapObject` | `VarHandle.compareAndSet` hoặc lớp `Atomic*` | Kiểu field, memory ordering, ABA, retry loop |
| Đọc/ghi volatile | `getObjectVolatile`, `putLongVolatile` | `VarHandle.getVolatile` / `setVolatile`; `volatile` field | Visibility, ordering, không đổi semantics vô ý |
| Ghi release/lazy | `putOrderedObject`, `putOrderedLong` | `VarHandle.setRelease` hoặc `Atomic*.lazySet` | Không mặc định giống `setVolatile` |
| Atomic update | `getAndAddInt`, `getAndSetObject` | `VarHandle.getAndAdd` / `getAndSet`; `AtomicInteger`/`AtomicReference` | Kiểu trả về, overflow, độ tranh chấp |
| Memory fences | `loadFence`, `storeFence`, `fullFence` | Fence tương ứng trong `VarHandle` hoặc higher-level synchronization | Happens-before, acquire/release, chứng minh đồng bộ |
| Array element access | `arrayBaseOffset`, `arrayIndexScale` kết hợp load/store | `MethodHandles.arrayElementVarHandle`, truy cập mảng thông thường | Không tự tính byte offsets |
| Byte buffer views | Đọc/ghi vùng byte theo offset | `ByteBuffer`, `byteBufferViewVarHandle` | Endianness, alignment, bounds |
| Off-heap allocation/access | `allocateMemory`, `freeMemory`, `getLong(long)`, `putLong(long, ...)` | Foreign Function & Memory API (`Arena`, `MemorySegment`, `ValueLayout`) trên JDK phù hợp | Ownership, lifetime, thread scope, alignment |
| Sao chép heap arrays | `copyMemory` cho array | `System.arraycopy`, `Arrays.copyOf` | Overlap, kiểu mảng, số phần tử vs byte |
| Sao chép memory segments | `copyMemory` giữa vùng native | `MemorySegment.copy` | Kiểm tra bounds và lifetime |
| Park/unpark thread | `park`, `unpark` | `LockSupport`, `Lock`, `Condition`, `Semaphore` | Permit, timeout, interrupt, spurious wakeup |
| Tạo object không chạy constructor | `allocateInstance` | Constructor, factory, builder, API serialization được hỗ trợ | Bất biến của object; không có thay thế trực tiếp phổ quát |
| Định nghĩa class động | Các API định nghĩa class cũ/không hỗ trợ | `MethodHandles.Lookup.defineClass`, `defineHiddenClass`, cơ chế class loading công khai | Package/lookup access, lifetime, class identity |
| Bỏ qua checked exception | `throwException` | Hợp đồng exception rõ ràng và wrapper/translation phù hợp | Không có lý do chung để bỏ qua compiler |

Ma trận là hướng dẫn định tuyến. Không được thay theo tên method bằng một thao tác “gần giống” khi chưa hiểu đầy đủ visibility, ordering, lifetime và hành vi lỗi.

## 6. Thay thao tác field CAS bằng `VarHandle`

### 6.1. Vì sao `VarHandle` phù hợp?

`VarHandle`, có từ Java 9, cung cấp API công khai để truy cập và thao tác nguyên tử với field, phần tử mảng hoặc một số view của buffer. Thay vì lấy memory offset thô và dùng `Unsafe` đọc/ghi, code có thể tạo handle gắn với kiểu và vị trí truy cập cụ thể.

Ví dụ một bộ đếm sequence dùng CAS trên field:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class SequenceCounter {
    private volatile long sequence;

    private static final VarHandle SEQUENCE;

    static {
        try {
            SEQUENCE = MethodHandles.lookup()
                    .findVarHandle(
                            SequenceCounter.class,
                            "sequence",
                            long.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public long next() {
        while (true) {
            long current = (long) SEQUENCE.getVolatile(this);
            long updated = current + 1;
            if (SEQUENCE.compareAndSet(this, current, updated)) {
                return updated;
            }
        }
    }
}
~~~

Trong ví dụ:

- `findVarHandle` xác định field theo lớp, tên và kiểu; không cần `objectFieldOffset`.
- `getVolatile` đọc với semantics volatile.
- `compareAndSet` thử thay giá trị atomically nếu giá trị hiện tại khớp kỳ vọng.
- CAS thất bại có thể lặp vì thread khác đã cập nhật.
- Trường `volatile` và việc dùng access mode thích hợp giúp mô hình đồng bộ dễ đọc hơn so với raw offsets.

Nếu chỉ cần một bộ đếm nguyên tử và không có yêu cầu giữ cấu trúc object cũ, `AtomicLong` thường đơn giản hơn:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class SequenceCounter {
    private final AtomicLong sequence = new AtomicLong();

    public long next() {
        return sequence.incrementAndGet();
    }
}
~~~

`AtomicLong` biểu diễn rõ mục đích, nhưng có thể khác về layout object, serialization, allocation và binary compatibility so với field `long` cũ. Đối với thư viện có yêu cầu giữ field hoặc class layout, `VarHandle` có thể phù hợp hơn; với code ứng dụng thông thường, atomic classes thường dễ duy trì hơn.

### 6.2. Không cần CAS loop nếu API đã cung cấp atomic update

Ví dụ trên có thể được rút gọn nếu mục tiêu là tăng bộ đếm:

~~~java
public long next() {
    return (long) SEQUENCE.getAndAdd(this, 1L) + 1L;
}
~~~

`getAndAdd` trả **giá trị trước khi cập nhật**, nên cần cộng thêm nếu method `next()` cam kết trả giá trị mới. Một thay đổi sai “old value vs new value” có thể làm lỗi nghiệp vụ dù thao tác atomic.

### 6.3. Field private và Java Module System

`MethodHandles.lookup()` trong chính lớp sở hữu field có thể tìm field private theo quyền truy cập của lớp đó. Đối với một class ở module khác, tạo private lookup có thể cần `MethodHandles.privateLookupIn` và package phải được mở cho module gọi.

Không nên tự động thay:

~~~java
field.setAccessible(true);
~~~

bằng `privateLookupIn` với kỳ vọng vượt mọi giới hạn đóng gói. API được hỗ trợ vẫn phải tôn trọng access control và module boundaries. Khi thiết kế một thư viện, ưu tiên cung cấp public/protected API hoặc đặt việc tạo `VarHandle` trong module sở hữu state.

## 7. Memory ordering: `plain`, `opaque`, `acquire/release` và `volatile`

Điểm khó nhất khi thay `Unsafe` thường không phải cú pháp mà là semantics đồng bộ.

`VarHandle` cung cấp nhiều access mode:

| Access mode | Ý nghĩa khái quát | Tình huống cần cân nhắc |
| --- | --- | --- |
| `get` / `set` | Truy cập plain | Chỉ an toàn khi được đồng bộ bằng cơ chế khác hoặc không chia sẻ bất an toàn |
| `getOpaque` / `setOpaque` | Opaque access, có giới hạn ordering yếu hơn volatile | Một số cấu trúc lock-free đã được chứng minh |
| `getAcquire` | Đọc theo acquire semantics | Nhận state đã publish bằng release phù hợp |
| `setRelease` | Ghi theo release semantics | Publish state theo quy tắc release/acquire |
| `getVolatile` / `setVolatile` | Semantics volatile | Truyền thông tin giữa thread với ordering mạnh hơn |
| `compareAndSet` | CAS có semantics quy định của VarHandle | Cập nhật có điều kiện, atomic |
| `getAndSet` / `getAndAdd` | Read-modify-write atomic | Bộ đếm, state transition |

Ví dụ:

~~~java
// Ghi release.
STATE.setRelease(this, READY);

// Đọc acquire.
int observed = (int) STATE.getAcquire(this);
~~~

Khi sử dụng đúng, cặp release/acquire có thể hỗ trợ publish dữ liệu giữa các thread. Tuy nhiên, không thể chỉ nhìn hai dòng trên rồi kết luận toàn bộ thuật toán thread-safe. Cần xem thứ tự các ghi/đọc xung quanh, đối tượng được chia sẻ, và điều kiện nào xác nhận dữ liệu đã được publish.

Không đổi `Unsafe.getObjectVolatile` thành `VarHandle.get` chỉ vì kết quả là cùng kiểu. Việc làm yếu ordering có thể tạo race hiếm gặp, đặc biệt trên phần cứng hoặc cấu hình tối ưu mà test thông thường khó tái hiện.

Ngược lại, thay tất cả bằng volatile mạnh nhất cũng không tự chứng minh thuật toán đúng. Nó có thể thay đổi hiệu năng, contention và vẫn không sửa được vấn đề atomicity khi một thao tác gồm nhiều bước.

### 7.1. CAS, ABA và retry

`compareAndSet` atomically kiểm tra giá trị hiện tại có bằng expected hay không rồi mới cập nhật. Nhưng CAS không tự giải quyết mọi trường hợp **ABA**: giá trị chuyển từ A → B → A có thể khiến một thread nghĩ rằng trạng thái chưa thay đổi.

Nếu thuật toán cần biết lịch sử thay đổi, có thể dùng version/stamp, chẳng hạn `AtomicStampedReference`, hoặc thiết kế state machine phù hợp. Không xem việc chuyển từ Unsafe CAS sang VarHandle CAS là bằng chứng rằng thuật toán lock-free đã an toàn.

### 7.2. Fence và đồng bộ cấp cao

`Unsafe.loadFence`, `storeFence` và `fullFence` có các lựa chọn fence công khai trong `VarHandle`, bao gồm `acquireFence`, `releaseFence`, `fullFence` và các dạng load/store fence thích hợp.

Ví dụ:

~~~java
VarHandle.releaseFence();
// Publish dữ liệu theo một protocol đồng bộ đã được thiết kế.
~~~

Một fence đứng riêng không biến mọi truy cập bình thường thành thread-safe. Nó cần được đặt trong giao thức đồng bộ hợp lệ. Trong nhiều trường hợp, dùng `synchronized`, `ReentrantLock`, `Atomic*` hoặc queue đồng thời đã được hỗ trợ sẽ dễ kiểm chứng và bảo trì hơn việc tự quản lý fence.

## 8. Truy cập phần tử mảng và buffer mà không tính offset thô

### 8.1. Array element `VarHandle`

Code Unsafe cũ có thể tính offset bằng base offset cộng index nhân index scale. Với mảng Java, nên ưu tiên truy cập mảng trực tiếp hoặc `arrayElementVarHandle` nếu cần CAS/volatile trên phần tử.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class ArraySlots {
    private static final VarHandle SLOT =
            MethodHandles.arrayElementVarHandle(int[].class);

    public static boolean replaceIfEqual(
            int[] values, int index, int expected, int update) {
        return SLOT.compareAndSet(values, index, expected, update);
    }
}
~~~

Code này làm rõ mảng và index, tránh phụ thuộc vào kích thước object header, base offset hoặc layout của JVM. Truy cập out-of-bounds và vấn đề kiểu dữ liệu được biểu diễn bằng API đã định nghĩa rõ hơn.

### 8.2. Buffer view theo kiểu và byte order

Khi dữ liệu là các byte trong `ByteBuffer`, có thể dùng API buffer hoặc view VarHandle:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class PacketReader {
    private static final VarHandle LONG_VIEW =
            MethodHandles.byteBufferViewVarHandle(
                    long[].class,
                    ByteOrder.LITTLE_ENDIAN);

    public static long readLong(ByteBuffer buffer, int byteOffset) {
        return (long) LONG_VIEW.get(buffer, byteOffset);
    }
}
~~~

Với byte-buffer view, offset được diễn giải theo byte, không phải index của một mảng `long[]`. Cần xác định alignment, bounds, byte order và những access mode mà view hỗ trợ. Không mặc định các thao tác atomic có thể thực hiện ở mọi địa chỉ chưa căn chỉnh.

Nếu chỉ đọc/ghi tuần tự, `ByteBuffer.order(...).getLong(...)` hoặc `putLong(...)` thường dễ hiểu hơn.

## 9. Thay `allocateMemory` và truy cập off-heap bằng Foreign Function & Memory API

### 9.1. Phạm vi hỗ trợ theo JDK

Foreign Function & Memory API (FFM) được chuẩn hóa trong JDK 22, với các API công khai chính ở package `java.lang.foreign`, bao gồm `MemorySegment`, `Arena` và `ValueLayout`. Các JDK trước đó có giai đoạn incubator/preview với cú pháp và mức ổn định khác nhau; không được copy nguyên ví dụ JDK 22 vào dự án JDK 17 hoặc JDK 21 rồi kỳ vọng chạy ngay.

Nếu runtime mục tiêu chưa hỗ trợ FFM ở dạng chuẩn, có thể cân nhắc `ByteBuffer.allocateDirect` cho nhu cầu lưu trữ byte ngoài heap, hoặc tiếp tục phụ thuộc thư viện cấp thấp có phiên bản được nhà cung cấp hỗ trợ theo một kế hoạch có thời hạn. Lựa chọn phụ thuộc việc cần native pointer, memory lifetime và layout hay chỉ cần buffer dữ liệu.

### 9.2. Ví dụ thay cấp phát và đọc/ghi vùng nhớ

Một mẫu Unsafe cũ (minh họa cách dùng cần thay):

~~~java
// Pseudocode legacy; giả sử đã có Unsafe instance.
long address = unsafe.allocateMemory(Long.BYTES);
try {
    unsafe.putLong(address, 123L);
    long value = unsafe.getLong(address);
} finally {
    unsafe.freeMemory(address);
}
~~~

Với JDK 22+ và FFM chuẩn, có thể dùng vùng nhớ có vòng đời rõ ràng:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class OffHeapSample {
    public static long readWrite() {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_LONG);

            segment.set(ValueLayout.JAVA_LONG, 0, 123L);
            return segment.get(ValueLayout.JAVA_LONG, 0);
        }
    }
}
~~~

Ở đây:

- `Arena` quyết định lifetime của segment.
- `try-with-resources` đóng confined arena khi rời scope.
- `MemorySegment` cung cấp kiểm tra truy cập dựa trên giới hạn, lifetime và threading constraints.
- `ValueLayout.JAVA_LONG` mô tả kiểu và alignment tương ứng.

Mô hình này tốt hơn việc phát tán raw address `long` cho nhiều lớp rồi cố nhớ gọi `freeMemory` ở đúng nơi. Tuy nhiên, nó vẫn cần thiết kế ownership và concurrency: segment từ confined arena không được tùy tiện chia sẻ để truy cập từ thread khác.

### 9.3. Layout, byte order và alignment

Khi đọc cấu trúc nhị phân, cần xác định byte order và kích thước field. Ví dụ:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16);
    ValueLayout.OfLong littleEndianLong =
            ValueLayout.JAVA_LONG.withOrder(ByteOrder.LITTLE_ENDIAN);

    segment.set(littleEndianLong, 0, 0x0102030405060708L);
    long decoded = segment.get(littleEndianLong, 0);
}
~~~

Khi port từ Unsafe, phải đối chiếu:

1. Byte order của format và của thao tác legacy.
2. Alignment và offsets trong struct hoặc packet.
3. Kích thước và kiểu (`int`, `long`, pointer, platform word).
4. Lifetime của vùng nhớ; ai tạo và ai đóng.
5. Thread nào được phép truy cập.
6. Copy có thể overlap hay không, và các quy tắc bounds.

Một phép chuyển cơ học từ `getLong(address + offset)` sang `segment.get(...)` nhưng chọn sai layout/offset vẫn có thể làm sai dữ liệu.

### 9.4. Sao chép dữ liệu

Nếu Unsafe chỉ dùng để copy các phần tử của mảng heap, nên cân nhắc:

~~~java
System.arraycopy(source, 0, target, 0, length);
~~~

`length` ở đây là **số phần tử** của mảng, không phải số byte. Cần bảo toàn semantics về overlap, kiểu phần tử và phần vùng được copy.

Với memory segments, có thể dùng API sao chép vùng nhớ:

~~~java
MemorySegment.copy(source, sourceOffset, target, targetOffset, bytes);
~~~

Giá trị `bytes` là số byte, và thao tác phải đáp ứng bounds/lifetime/access restrictions của segments. Không thay nhầm đơn vị khi chuyển từ mảng sang vùng nhớ.

### 9.5. Native interop không phải lúc nào cũng là nhu cầu

Không phải ứng dụng dùng `allocateMemory` nào cũng cần native linker hoặc arbitrary address. Nếu chỉ cần buffer dùng để gửi file/network hoặc chứa bytes, `ByteBuffer` và các API I/O công khai có thể đơn giản hơn FFM.

Nếu cần gọi native code, FFM cung cấp cơ chế native interoperability phù hợp với JDK hỗ trợ. Một số thao tác native access bị kiểm soát theo chính sách runtime và có thể cần cấu hình quyền truy cập phù hợp; hãy kiểm tra hướng dẫn chính thức của đúng phiên bản JDK mục tiêu thay vì thêm cờ tùy tiện.

## 10. `ByteBuffer.allocateDirect`: khi nào phù hợp và giới hạn

`ByteBuffer.allocateDirect` có thể cung cấp vùng byte ngoài Java heap theo implementation. API buffer hỗ trợ các thao tác đọc/ghi typed values mà không cần dùng `Unsafe`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer buffer = ByteBuffer.allocateDirect(16)
        .order(ByteOrder.LITTLE_ENDIAN);

buffer.putLong(0, 123L);
long value = buffer.getLong(0);
~~~

Phù hợp khi:

- Nhu cầu là đọc/ghi bytes và giá trị primitive với bounds rõ ràng.
- API I/O đã làm việc tốt với `ByteBuffer`.
- Không cần đưa native address trực tiếp cho C library.
- Vòng đời được quản lý qua cơ chế chuẩn của buffer và không đòi hỏi free ngay tại một thời điểm chính xác.

Hạn chế:

- Direct buffer không cho cùng mô hình deterministic lifetime như `Arena` có thể đóng chủ động.
- Không nên truy cập private cleaner hay địa chỉ nội bộ của direct buffer để tự giải phóng bằng Unsafe.
- Việc sharing giữa thread, byte order, alignment và ownership vẫn cần được thiết kế.

Nếu ứng dụng cần kiểm soát giải phóng vùng nhớ theo scope, FFM trên JDK hỗ trợ thường là lựa chọn rõ hơn.

## 11. Thay `park` / `unpark` bằng công cụ đồng bộ công khai

`Unsafe.park` và `Unsafe.unpark` được dùng trong một số cấu trúc đồng thời. Java cung cấp `LockSupport` để thao tác park/unpark mà không cần truy cập Unsafe:

~~~java
import java.util.concurrent.locks.LockSupport;

// Thread hiện tại tạm dừng (có thể quay lại vì unpark,
// interrupt hoặc spurious wakeup).
LockSupport.park();

// Ở thread khác, cấp permit để thread được tiếp tục.
LockSupport.unpark(workerThread);
~~~

Các điểm cần bảo toàn khi thay:

- Permit của `LockSupport` không tích lũy vô hạn như số lượng thông điệp trong queue.
- `park` có thể trở về khi bị interrupt hoặc spurious wakeup.
- Điều kiện chờ phải được kiểm tra trong vòng lặp phù hợp, không coi “park trở về” là điều kiện đã đúng.
- `parkNanos` và `parkUntil` khác nhau về cách hiểu thời gian; không chuyển nhầm tương đối/định thời tuyệt đối.
- Không bỏ qua interruption hoặc chặn thread không có đường wakeup hợp lệ.

Trong phần lớn code nghiệp vụ, `BlockingQueue`, `Semaphore`, `CountDownLatch`, `ReentrantLock` hoặc `Condition` phù hợp hơn tự xây dựng protocol park/unpark cấp thấp.

Ví dụ dùng điều kiện thay cho tự park:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

BlockingQueue<String> queue = new ArrayBlockingQueue<>(100);

// Producer:
queue.put("event");

// Consumer:
String event = queue.take();
~~~

Lớp queue chịu trách nhiệm cho phần lớn chi tiết đồng bộ và wakeup. Không nên tự tái tạo cấu trúc đồng thời chỉ để thay một lời gọi Unsafe nếu thư viện chuẩn đã đáp ứng yêu cầu.

## 12. `allocateInstance` và tạo đối tượng không gọi constructor

`Unsafe.allocateInstance(Class<?>)` có thể tạo object mà không đi qua constructor thông thường. Một số framework serialization, proxy hoặc object mapper từng dùng cơ chế này để dựng object khi không có constructor phù hợp.

Điểm rủi ro không chỉ là API nội bộ; nó còn bỏ qua invariant mà constructor tạo ra:

~~~java
public final class Session {
    private final String token;

    public Session(String token) {
        this.token = java.util.Objects.requireNonNull(token);
    }

    public String token() {
        return token;
    }
}
~~~

Nếu object được cấp phát mà không chạy constructor, `token` có thể không được khởi tạo theo quy tắc của ứng dụng. Gọi `token()` sau đó có thể nhận `null` dù API dự kiến luôn non-null.

Hướng thay thế ưu tiên:

1. Cung cấp constructor hoặc factory rõ ràng, kiểm tra invariant.
2. Với deserialization, dùng cơ chế được thư viện/framework hỗ trợ và cấu hình constructor/builder/record mapping thích hợp.
3. Với Java serialization truyền thống, sử dụng API serialization công khai nếu thực sự cần và hiểu rõ quy tắc riêng của cơ chế đó.
4. Nếu framework bên thứ ba phụ thuộc `allocateInstance`, ưu tiên nâng phiên bản framework được xác nhận hỗ trợ JDK mục tiêu.

Không có một public API phổ quát thay trực tiếp `allocateInstance` với cùng ý nghĩa “tạo mọi object mà không gọi constructor”. Đây thường là dấu hiệu phải thiết kế lại contract hoặc nâng công cụ cấp framework, chứ không phải chỉ đổi import.

## 13. Sinh và nạp class động

Một số đường dùng Unsafe hoặc API nội bộ phục vụ định nghĩa class từ bytecode. Trong những trường hợp phù hợp, Java cung cấp các API như:

- `MethodHandles.Lookup.defineClass(byte[])`: định nghĩa class trong phạm vi package/lookup phù hợp.
- `MethodHandles.Lookup.defineHiddenClass(...)`: tạo hidden class cho một số trường hợp sinh code triển khai động.
- Cơ chế `ClassLoader` công khai để nạp class thông thường theo quy tắc Java.

Ví dụ minh họa dạng gọi API, không phải đoạn code hoàn chỉnh tự sinh bytecode:

~~~java
import java.lang.invoke.MethodHandles;

// bytes là class file hợp lệ và thỏa điều kiện package/access.
Class<?> generated =
        MethodHandles.lookup().defineClass(bytes);
~~~

Điều cần đánh giá:

- Class mới thuộc package và module nào?
- Lookup object có quyền cần thiết không?
- Class được thiết kế để bên ngoài lookup bằng tên hay chỉ dùng nội bộ?
- Vòng đời class, class loader identity và khả năng garbage collection có thay đổi không?
- Bytecode generator có hỗ trợ class-file version của JDK mục tiêu không?

`defineHiddenClass` không phải thay thế một-một cho mọi class có tên thông thường. Hidden class có semantics identity/discovery khác với class nạp theo tên. Với framework sinh proxy/bytecode, ưu tiên dùng phiên bản của framework đã hỗ trợ JDK mục tiêu hơn là tự thay class-definition internals.

## 14. Vì sao `--add-opens` không phải phương án thay thế dài hạn?

Trong Java Module System, truy cập reflection sâu vào package không mở có thể bị chặn. Một số nhóm thêm các cờ như `--add-opens` để thư viện cũ tiếp tục chạy. Cờ này là **biện pháp tương thích tạm thời** ở những nơi có thể áp dụng và được phê duyệt, không phải API thay thế cho Unsafe.

Cần phân biệt:

- `--add-opens` có thể mở package để cho phép một số truy cập reflection sâu.
- `--add-exports` liên quan việc export package qua ranh giới module.
- Hai cờ không bảo đảm sự tồn tại hay tính ổn định của method nội bộ.
- Một JDK mới vẫn có thể thay đổi/loại bỏ hành vi mà code dựa vào.

Nếu thực sự cần một workaround:

1. Ghi rõ thư viện và method nào đang bị chặn.
2. Áp dụng phạm vi nhỏ nhất cho môi trường được kiểm soát.
3. Có owner, thời hạn và phiên bản dependency mục tiêu sẽ gỡ workaround.
4. Kiểm tra test và vấn đề bảo mật/vận hành liên quan.
5. Không kéo workaround thành cấu hình chung của toàn bộ hệ thống một cách vô thời hạn.

Đặc biệt, chuyển từ `sun.misc.Unsafe` sang `jdk.internal.misc.Unsafe` rồi mở module bằng cờ chỉ chuyển vấn đề từ một điểm nội bộ sang một điểm nội bộ khác.

## 15. Các thay đổi về tương thích JDK cần tính trước

Một kế hoạch migration nên nêu rõ baseline và target runtime:

| Mốc JDK | Khả năng liên quan bài học | Lưu ý |
| --- | --- | --- |
| Java 8 | Nhiều code legacy từng dùng `sun.misc.Unsafe` trực tiếp | Chưa có `VarHandle` |
| Java 9+ | Có `VarHandle` và JPMS; `sun.misc.Unsafe` tiếp tục nằm trong bối cảnh API không được hỗ trợ | Module access và dependency phải kiểm tra |
| Java 17 | Có `VarHandle`, `Atomic*`, `LockSupport` và `ByteBuffer` | FFM thời kỳ trước API chuẩn cuối cùng |
| Java 21 | Có các API concurrent chuẩn; FFM ở giai đoạn preview | Không giả định mã FFM JDK 22 chạy nguyên trạng |
| Java 22+ | FFM chuẩn (`java.lang.foreign`) có thể thay nhiều thao tác off-heap | Kiểm tra runtime vendor/version, native access policy |

Không chỉ căn cứ vào “JDK có API đó” để quyết định thay. Một thư viện có thể có mức Java tối thiểu thấp hơn runtime của ứng dụng hoặc cần biên dịch artifact để consumer Java cũ sử dụng.

Ví dụ: nếu thư viện phải tiếp tục hỗ trợ Java 17, không thể trực tiếp công bố API sử dụng `java.lang.foreign.Arena` của JDK 22 trong artifact cùng baseline Java 17. Có thể cần giữ interface độc lập với runtime implementation, chọn ByteBuffer hoặc phân tách module theo mức JDK được hỗ trợ.

### 15.1. Source, binary và behavioral compatibility

Một số thay đổi khi bỏ Unsafe có thể tác động khác nhau:

- **Source compatibility:** method public đổi từ nhận `long address` sang `MemorySegment` khiến consumer phải sửa source.
- **Binary compatibility:** JVM descriptor đổi, bytecode client cũ có thể không liên kết.
- **Behavioral compatibility:** giải phóng segment sớm hơn, cấm thread truy cập ngoài scope, hoặc kiểm tra bounds nghiêm hơn có thể làm lỗi cũ xuất hiện rõ ràng.
- **Performance compatibility:** layout, access mode và synchronization khác có thể làm latency/throughput đổi.

Nếu public API đang lộ raw addresses hoặc `Unsafe`, cần coi quá trình thay thế là một cuộc tiến hóa API có lộ trình, không chỉ refactor nội bộ.

## 16. Chiến lược chuyển đổi có kiểm soát

### Bước 1: Cố định baseline

Ghi lại JDK, vendor, JVM flags, build tool, dependency versions, architecture, OS, runtime image và các test/benchmark quan trọng. Xác định luồng có dùng Unsafe.

### Bước 2: Hoàn thành inventory

Kết hợp source scan, `jdeps`, dependency graph và bằng chứng runtime. Ghi call site, owner và mục đích; không kết luận chỉ dựa vào import hoặc scanner.

### Bước 3: Chọn API theo mục đích

- CAS/field access → `VarHandle` hoặc `Atomic*`.
- Queue/waiting → `LockSupport` hoặc concurrency abstractions.
- Heap arrays → truy cập chuẩn/`System.arraycopy`.
- Byte buffers → `ByteBuffer` hoặc buffer view.
- Off-heap memory → FFM trên JDK hỗ trợ.
- Object creation/class definition → constructor/factory, serializer/framework chính thống và `MethodHandles.Lookup` khi thích hợp.

### Bước 4: Tách thay đổi cấp thấp khỏi thay đổi framework lớn

Nếu có thể, thay riêng từng nhóm API Unsafe. Giữ test so sánh cũ/mới để xác định regression. Việc thay memory ordering và nâng cả framework trong một commit làm khó tìm nguyên nhân.

### Bước 5: Xác nhận semantics, không chỉ khả năng biên dịch

Cần kiểm tra:

- Giá trị trả về và side effects.
- Atomicity, memory visibility và concurrency.
- Buffer bounds, byte order, alignment.
- Lifetime và giải phóng native memory.
- Exception, failure behavior và cancellation.
- Thread confinement và khả năng chia sẻ.

### Bước 6: Xem xét hiệu năng đúng workload

Unsafe đôi khi được chọn vì mục tiêu latency hoặc allocation đặc thù. Sau thay thế, benchmark trên workload đại diện; xem warmup, throughput, tail latency, contention và memory footprint. Chỉ tối ưu sâu khi dữ liệu cho thấy cần thiết.

Không dùng một microbenchmark không phản ánh production làm lý do giữ API nội bộ vô thời hạn. Ngược lại, cũng không tuyên bố cách thay thế luôn nhanh hơn chỉ vì là API mới.

### Bước 7: Rollout, quan sát và gỡ workaround

Thử trên staging/canary, quan sát crash, native memory, GC, latency, error rate và log về illegal/restricted access. Xác minh container/JDK production đúng artifact. Xóa các cờ mở module và cấu hình legacy không còn cần sau khi thay thành công.

## 17. Ví dụ tổng hợp: từ native address thô sang segment có vòng đời

Giả sử một module cache legacy quản lý một bản ghi gồm `long id` và `int flags` trong native memory. Mã Unsafe có thể cấp phát một khối bytes, tự tính offsets, ghi dữ liệu rồi lưu native address trong registry.

Các rủi ro:

- Không giải phóng `address` khi exception xảy ra.
- Giải phóng hai lần khi nhiều owner cùng giữ address.
- Truy cập sau khi free gây lỗi khó chẩn đoán.
- Offset hoặc alignment sai khi đổi layout/architecture.
- Một thread dùng vùng nhớ trong khi thread khác giải phóng.

Với JDK 22+ và FFM, hướng thiết kế là mô tả layout và ownership:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class RecordBuffer implements AutoCloseable {
    private static final MemoryLayout LAYOUT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_LONG.withName("id"),
                    ValueLayout.JAVA_INT.withName("flags"),
                    MemoryLayout.paddingLayout(4));

    private final Arena arena = Arena.ofConfined();
    private final MemorySegment segment = arena.allocate(LAYOUT);

    public void setId(long id) {
        segment.set(ValueLayout.JAVA_LONG, 0, id);
    }

    public long id() {
        return segment.get(ValueLayout.JAVA_LONG, 0);
    }

    public void setFlags(int flags) {
        segment.set(ValueLayout.JAVA_INT, 8, flags);
    }

    public int flags() {
        return segment.get(ValueLayout.JAVA_INT, 8);
    }

    @Override
    public void close() {
        arena.close();
    }
}
~~~

Ví dụ sử dụng:

~~~java
try (RecordBuffer record = new RecordBuffer()) {
    record.setId(1001L);
    record.setFlags(2);

    System.out.println(record.id());
}
~~~

Đây là ví dụ minh họa một layout cụ thể: `long` ở offset 0, `int` ở offset 8, thêm padding để tổng kích thước hợp lý. Với dữ liệu thực, layout phải được đối chiếu đúng format/protocol/native ABI. Nếu struct từ C có quy tắc alignment hoặc packing khác, không được tự giả định các offset.

`Arena.ofConfined()` phù hợp nếu object chỉ được truy cập bởi thread sở hữu. Nếu logic cache cần chia sẻ giữa nhiều thread, phải chọn mô hình arena và synchronization khác. Việc “đã có MemorySegment” không tự khiến thiết kế cache thread-safe.

So với raw address, wrapper `RecordBuffer` biểu diễn được lifecycle qua `AutoCloseable`; khi đóng arena, vùng nhớ được quản lý theo scope. Đổi lại, API consumer có thêm trách nhiệm không dùng object sau `close()` và không giữ reference vượt lifetime.

## 18. Sai lầm thường gặp khi loại bỏ `Unsafe`

**Chỉ đổi import sang API nội bộ khác.** `jdk.internal.misc.Unsafe` không phải lựa chọn công khai bền vững.

**Cho rằng `--add-opens` giải quyết vấn đề lâu dài.** Cờ module có thể hỗ trợ một số truy cập reflection, nhưng không cung cấp hợp đồng API ổn định.

**Dùng `VarHandle.get()` thay mọi `getVolatile()`.** Tên method và kiểu dữ liệu có thể giống, nhưng memory ordering đã thay đổi.

**Đổi CAS nhưng bỏ qua giá trị trả về.** `compareAndSet` trả boolean; `getAndAdd` trả giá trị cũ; cần giữ contract của caller.

**Bỏ qua ABA và data race.** Atomic primitive operation không làm cả một thuật toán đồng thời tự động đúng.

**Thay raw memory bằng `ByteBuffer` rồi tìm cách lấy native address nội bộ.** Cách đó có thể đưa code trở lại API không hỗ trợ và không giải quyết ownership.

**Bỏ qua byte order và alignment.** Đọc `long` sai endian hoặc offset vẫn có thể trả một số hợp lệ nhưng sai nghĩa.

**Dùng confined arena cho dữ liệu chia sẻ đa luồng.** Lifetime và thread access rules phải được chọn theo thiết kế.

**Giữ raw pointer trong field `long` mà không có owner rõ.** Nếu chưa giải quyết vấn đề ai đóng/free và khi nào, thay lớp API không loại bỏ được rủi ro.

**Thay `allocateInstance` bằng cách vòng qua constructor khác.** Việc bỏ qua invariant là rủi ro thiết kế; hướng xử lý thường là factory/serialization contract phù hợp.

**Đánh giá dependency bằng source search nhưng bỏ qua JAR runtime.** Code ứng dụng không import Unsafe vẫn có thể chạy qua dependency sử dụng nó.

**Xem mọi phát hiện static analysis là blocker như nhau.** Một đường code chưa được kích hoạt và một direct off-heap memory manager trong production cần kế hoạch khác nhau, nhưng đều phải được ghi nhận.

**Khẳng định hiệu năng tốt hơn khi chưa có phép đo đại diện.** Cần kiểm tra cả throughput, tail latency và overhead quản lý memory.

## 19. Checklist trước khi chốt kế hoạch thay `Unsafe`

- [ ] Đã xác định chính xác artifact/module nào sử dụng `sun.misc.Unsafe`.
- [ ] Đã tìm cả source, dependency, shaded JAR và truy cập reflection có thể liên quan.
- [ ] Đã ghi method Unsafe, mục đích, call site và đường chạy quan trọng.
- [ ] Đã kiểm tra phiên bản library/framework được hỗ trợ trên JDK mục tiêu.
- [ ] Không coi `jdk.internal.misc.Unsafe` là API thay thế được hỗ trợ.
- [ ] Các thao tác CAS/atomic đã có lựa chọn `VarHandle` hoặc `Atomic*` phù hợp.
- [ ] Memory ordering cũ/mới được ghi rõ, không âm thầm làm yếu visibility.
- [ ] Đã đánh giá data race, ABA và correctness của thuật toán concurrency.
- [ ] Các thao tác array/buffer đã thay offsets thô bằng API có bounds/type rõ ràng khi có thể.
- [ ] Với off-heap, có owner, lifetime, alignment, byte order và thread-safety rõ ràng.
- [ ] Đã chọn API phù hợp với JDK tối thiểu được hỗ trợ, đặc biệt với FFM.
- [ ] Các luồng serialization/object creation giữ invariant và failure semantics.
- [ ] Dynamic class generation dùng cơ chế lookup/class loading phù hợp.
- [ ] Đã ghi ngoại lệ nếu phải giữ workaround và có owner/mốc gỡ bỏ.
- [ ] Có phương án kiểm thử, benchmark và rollout trên runtime image mục tiêu.
- [ ] Release notes và tài liệu migration chỉ rõ những consumer cần sửa source hoặc rebuild.

## 20. Tham khảo kỹ thuật

Các nguồn chính thức nên được đối chiếu với đúng phiên bản JDK đang triển khai:

- **JDK API Documentation — `java.lang.invoke.VarHandle`:** access modes, atomic operations và memory fences.
- **JDK API Documentation — `java.lang.invoke.MethodHandles`:** lookup, `privateLookupIn`, `defineClass` và `defineHiddenClass`.
- **JDK API Documentation — `java.util.concurrent.atomic`:** các lớp atomic cho counters, references và updaters.
- **JDK API Documentation — `java.util.concurrent.locks.LockSupport`:** park/unpark, timeout, interruption và permit.
- **JDK API Documentation — `java.nio.ByteBuffer`:** direct buffers và typed access với byte order.
- **JDK API Documentation — `java.lang.foreign` (JDK 22+):** `Arena`, `MemorySegment`, `MemoryLayout`, `ValueLayout` và native interop.
- **OpenJDK JEP 193 — Variable Handles:** bối cảnh bổ sung API thao tác biến an toàn hơn.
- **OpenJDK JEP 454 — Foreign Function & Memory API:** mục tiêu và trạng thái API chuẩn của JDK 22.
- **`jdeps` Tool Guide:** phát hiện tham chiếu tới JDK internal APIs trong class files.

Các ví dụ dùng FFM của bài học nhắm tới API chuẩn JDK 22+. Không áp dụng nguyên trạng cho JDK 17/21 mà không xét trạng thái API ở các bản đó.

## 21. Kết luận

`sun.misc.Unsafe` không phải một vấn đề có thể giải quyết chỉ bằng việc đổi import. Nó là tập hợp nhiều cơ chế cấp thấp với rủi ro khác nhau: memory access, atomic operations, fences, thread parking, object allocation và class generation. Muốn migration bền vững cần **kiểm kê theo mục đích dùng thực tế**, xác định chính xác ai sở hữu code, và chọn API hỗ trợ phù hợp với phiên bản JDK mục tiêu.

Đối với state đồng thời, ưu tiên `VarHandle` và các lớp `Atomic*` hoặc concurrency abstraction cấp cao. Đối với mảng và buffer, ưu tiên API Java có bounds và type rõ. Đối với off-heap memory trên JDK hỗ trợ, FFM cung cấp mô hình `Arena`/`MemorySegment` để quản lý quyền truy cập và lifetime. Với serialization, tạo object và sinh class động, cần đánh giá lại invariant, quyền lookup và khả năng của framework thay vì tìm một thao tác “bỏ qua kiểm soát” tương đương.

Một migration thành công không chỉ biên dịch được trên JDK mới: nó còn giữ đúng atomicity, visibility, layout, lifetime, exception và hành vi ở runtime, đồng thời giảm dần sự phụ thuộc vào các API nội bộ mà tổ chức không kiểm soát được.
