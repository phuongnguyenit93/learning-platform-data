# Arena.ofConfined và quyền truy cập của luồng sở hữu (Java FFM)

## 1. Bức tranh tổng thể: ai sở hữu vùng nhớ được cấp phát?

Foreign Function & Memory API (FFM) của Java cho phép tạo, đọc, ghi và chuyển các vùng nhớ native (off-heap) thông qua `MemorySegment`. Từ JDK 22, FFM là API chính thức trong package `java.lang.foreign`. Một cách cấp phát phổ biến là tạo **confined arena**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

// Minh họa một đoạn trong method, không phải chương trình độc lập.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment value = arena.allocate(ValueLayout.JAVA_INT);
    value.set(ValueLayout.JAVA_INT, 0, 42);
    int answer = value.get(ValueLayout.JAVA_INT, 0);
}
~~~

Một `Arena` là **bộ quản lý vòng đời** của các vùng nhớ mà nó cấp phát. `Arena.ofConfined()` tạo arena có ba tính chất then chốt:

1. **Có owner thread (luồng sở hữu):** thread gọi `Arena.ofConfined()` chính là owner.
2. **Thread confinement:** các vùng nhớ được cấp phát từ confined arena chỉ được truy cập hợp lệ bởi owner thread, dù một thread khác giữ được biến Java kiểu `MemorySegment` trỏ tới cùng vùng.
3. **Vòng đời có giới hạn và dọn xác định:** owner đóng arena bằng `close()` (thường nhờ `try-with-resources`). Sau khi đóng, những segments được cấp phát từ arena đều hết hiệu lực, và native memory do arena sở hữu được giải phóng.

Hai ranh giới cần kiểm tra cho **mỗi lần truy cập**:

~~~text
                          Một MemorySegment hợp lệ?
                                    |
               +--------------------+--------------------+
               |                                         |
      Scope còn sống?                         Thread này có quyền?
     scope().isAlive()                   segment.isAccessibleBy(T)
               |                                         |
               +--------------- cùng hợp lệ ------------+
                                    |
                  Kiểm tra thêm bounds, alignment,
                  read-only, layout của thao tác
                                    |
                             Có thể truy cập
~~~

Nếu **đúng thread nhưng arena đã đóng**, thao tác đọc/ghi có thể ném `IllegalStateException`. Nếu **arena còn sống nhưng sai thread**, thao tác đọc/ghi có thể ném `WrongThreadException`. Đây là hai lỗi khác nhau; đừng gom chúng thành một lỗi “segment không hợp lệ”.

> **Quy tắc cốt lõi:** Không phải thread nào **nhìn thấy** một `MemorySegment` trong Java cũng có quyền **truy cập nội dung** segment đó. Chuyển reference qua thread không chuyển quyền sở hữu của confined arena.

## 2. Arena, scope và segment: ba khái niệm dễ lẫn

| Khái niệm | Đại diện Java | Tác dụng | Điều không nên suy ra |
| --- | --- | --- | --- |
| Arena | `Arena` | Cấp phát native memory và quản lý vòng đời những segments liên quan | Không có nghĩa mọi arena đều truy cập đa luồng |
| Scope | `MemorySegment.Scope` | Biểu diễn thời gian sống chung của các segments liên kết với scope | `isAlive() == true` không chứng minh thread hiện tại có quyền truy cập |
| Segment | `MemorySegment` | View có địa chỉ, kích thước, quyền đọc/ghi và scope cho một vùng nhớ | Không phải Java array; không sở hữu độc lập vùng nhớ ngoài scope |
| Value layout | `ValueLayout.JAVA_INT`, `JAVA_LONG`, ... | Quy định kiểu, kích thước, alignment, byte order khi đọc/ghi | Không tự bỏ qua giới hạn thread, thời gian sống hoặc bounds |
| Owner thread | `Thread` tạo arena confined | Thread được phép truy cập các segments thuộc confined arena | Không thể đổi owner chỉ bằng gán biến hoặc `Thread.start()` |

Ví dụ:

~~~java
// Minh họa trong một method.
Arena arena = Arena.ofConfined();
MemorySegment first = arena.allocate(16);
MemorySegment second = arena.allocate(32);
MemorySegment view = first.asSlice(4, 8);

// first, second và view gắn với scope của arena.
// asSlice KHÔNG tạo owner mới và KHÔNG kéo dài vòng đời.
arena.close();
~~~

- `first` và `second` là các segment khác nhau nhưng cùng scope.
- `view` chỉ là một *slice* của `first`, có spatial bounds hẹp hơn; nó vẫn chịu **cùng giới hạn owner và lifetime**.
- Không phải đóng `view` riêng: nó không có `close()` để giải phóng độc lập.
- Một số phương thức metadata (`byteSize()`, `scope()`) có thể cung cấp thông tin mà không đọc native bytes; việc thu được metadata **không** đồng nghĩa có quyền dereference memory.

`MemorySegment.ofArray(...)` lại là một **heap segment** dựa trên Java array, không phải một allocation do `Arena.ofConfined()` quản lý. Heap segment có luật ownership/lifetime khác; không dùng nó để suy ra quyền truy cập đối với native segment của confined arena.

## 3. Owner được xác lập thế nào?

Giả sử `main` tạo arena:

~~~text
Thread main
    |
    +-- Arena.ofConfined()  -> owner = main
    |       |
    |       +-- arena.allocate(...) -> segment S
    |       +-- S.get(...)          -> hợp lệ trên main
    |       +-- S.set(...)          -> hợp lệ trên main
    |       +-- arena.close()       -> hợp lệ trên main
    |
    +-- Thread worker giữ tham chiếu Java tới S
            |
            +-- S.get(...)          -> WrongThreadException
            +-- S.set(...)          -> WrongThreadException
            +-- arena.close()       -> WrongThreadException
~~~

Trong confined arena, **owner thread là luồng tạo arena** theo API, không phải:

- Thread nào giữ biến `Arena arena` hoặc `MemorySegment segment` trong heap;
- Thread chạy `main` nói chung, nếu arena thực tế được tạo trong một worker thread;
- Thread gọi method cuối cùng;
- Thread quản lý `ExecutorService`;
- Thread đang có lock Java `synchronized`;
- Native OS thread gọi một function FFM thay cho Java owner.

Nếu một `Runnable` tạo confined arena **bên trong** `run()`, owner của arena đó là thread thực thi `run()`, không nhất thiết là thread đã *khởi tạo đối tượng Runnable*.

### 3.1. Sai lầm phổ biến: giao đối tượng segment sang worker

~~~java
// Minh họa lỗi; chưa phải chương trình độc lập.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);

    Thread worker = new Thread(() -> {
        segment.set(ValueLayout.JAVA_INT, 0, 99);
        // Sai thread: có thể ném WrongThreadException.
    });

    worker.start();
    worker.join();
}
~~~

Biến `segment` là một Java object reference có thể đưa vào lambda; Java compiler không cấm. **Nhưng FFM kiểm tra quyền truy cập khi thao tác với native memory**. Biến có thể được chuyển, quyền truy cập của confined arena thì không.

Nếu worker bắt exception và im lặng, chương trình có thể tạo cảm giác “work completed” trong khi không ghi byte nào. Trong ứng dụng thực cần propagate lỗi hoặc thay thiết kế ownership.

### 3.2. Sai lầm ngược: worker tạo arena, main không được đọc

~~~java
// Minh họa sai mô hình handoff:
Thread worker = new Thread(() -> {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment created = arena.allocate(8);
        // owner là worker, không phải main.
        // Truyền created sang main không tự cấp quyền cho main.
    }
});
~~~

Nếu worker return sau khi thoát `try`, arena còn bị đóng, nên segment bên main vừa **không thuộc owner** vừa **hết vòng đời**. Thiết kế đúng là để worker sao chép kết quả ra Java value/array, hoặc thiết kế shared arena được quản lý có chủ đích.

## 4. Truy cập thế nào được coi là hợp lệ?

Các thao tác truy cập nội dung bị ràng buộc bởi confinement gồm:

- `segment.get(ValueLayout.JAVA_INT, offset)` và `segment.set(...)`;
- `segment.getAtIndex(...)`, `setAtIndex(...)`;
- `segment.copyFrom(other)` hoặc phương thức copy bộ nhớ: các segment nguồn/đích đều phải có scope và quyền truy cập phù hợp;
- `segment.toArray(...)` khi đọc native memory thành Java array;
- đọc/ghi các phần tử qua một `VarHandle` thu được từ `MemoryLayout`;
- sử dụng segment trong một FFM downcall nếu downcall cần đọc/ghi pointer native mà segment đại diện.

**Không phải chỉ lệnh `set` mới bị kiểm tra.** Ngay cả đọc một `int` bằng `get` từ thread khác cũng vi phạm confinement. `asReadOnly()` chỉ làm vùng nhớ không thể bị ghi qua view đó; nó **không** biến confined segment thành segment đọc được từ mọi thread.

### 4.1. Các API kiểm tra sẵn có trong JDK 22

~~~java
// JDK 22+, minh họa với segment hiện hữu:
boolean ownerCanAccess =
        segment.isAccessibleBy(Thread.currentThread());

boolean stillAlive =
        segment.scope().isAlive();

long size = segment.byteSize();
~~~

- `isAccessibleBy(thread)` kiểm tra khả năng truy cập theo **thread** mà API segment cho phép.
- `scope().isAlive()` báo trạng thái **lifetime**.
- `byteSize()` báo kích thước logic theo byte.

Nên kiểm tra **cả thread và lifetime** khi cần chủ động phân nhánh, nhưng vẫn phải để FFM access API thực hiện checks thật ở thời điểm thao tác vì tình trạng scope có thể thay đổi. Một câu `if (scope().isAlive())` không phải giấy phép vượt quyền owner.

Không dùng những predicates trên để “chứng minh” rằng một **native pointer thô** được tạo bằng `MemorySegment.ofAddress` có backing memory hợp lệ. Khi làm việc với raw pointer, FFM không thể tự xác minh mọi giới hạn ABI/ownership bên ngoài.

## 5. Vòng đời: `try-with-resources` và `Arena.close()`

Mẫu chuẩn:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

// Minh họa trong method của Java 22+.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
    segment.set(ValueLayout.JAVA_INT, 0, 25);

    int value = segment.get(ValueLayout.JAVA_INT, 0);
    // value == 25, và thao tác ở đúng owner.
} // arena.close() tự gọi, cũng trên owner thread.
~~~

`Arena` implements `AutoCloseable`, nên `try-with-resources` là cách thường dùng để giải phóng **tất cả** native allocations liên quan tới confined arena theo vòng đời rõ ràng, kể cả khi block ném exception. Các segments cấp phát từ arena sẽ không được dùng sau khi arena đóng.

Đặc điểm quan trọng:

1. **Đóng là dứt khoát:** đóng thành công làm scope không còn alive.
2. **Không idempotent:** cố `close()` lần nữa trên arena đã đóng sẽ ném `IllegalStateException`, không phải no-op an toàn.
3. **Đúng thread:** đóng confined arena từ thread khác sẽ ném `WrongThreadException`; việc đóng **không** chuyển owner.
4. **Đang được truy cập:** nếu có foreign downcall giữ segment đang được truy cập đồng thời với close, JVM có thể báo `IllegalStateException` theo hợp đồng thay vì giải phóng bất chấp.
5. **Không dùng segment sau close:** truy cập nội dung sau khi scope hết hiệu lực sẽ ném `IllegalStateException` ở đúng thread (trong trường hợp thông thường).

### 5.1. Sau khi arena close thì còn dữ liệu nào sống?

~~~java
// Minh họa trong method, không phải chương trình độc lập.
MemorySegment escaped;

try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(ValueLayout.JAVA_INT);
    escaped.set(ValueLayout.JAVA_INT, 0, 101);
}

boolean alive = escaped.scope().isAlive(); // false
// escaped.get(ValueLayout.JAVA_INT, 0) -> IllegalStateException.
~~~

**Biến Java `escaped` vẫn có thể tồn tại**, nhưng native region mà nó đại diện đã hết lifetime. Việc Java GC chưa thu hồi chính đối tượng `MemorySegment` **không giữ vùng nhớ native sống lại**. Đây là khía cạnh *temporal safety*.

Với `Arena.ofConfined()`, quản lý tài nguyên **không** dựa vào GC để kết thúc ở thời điểm xác định: chủ động đóng arena trong đúng thread.

### 5.2. Arena close không phải `free(pointer)` tùy tiện

Arena theo dõi memory mà nó cấp phát. Không tự `free` native address lấy từ `segment.address()` qua JNI hoặc C `free()` trong khi arena vẫn sở hữu allocation: đó là nguy cơ double-free hoặc use-after-free. Tương tự, không truyền address cho một thư viện native sẽ giữ pointer sau khi arena close, trừ khi đã thiết kế transfer ownership rõ ràng và có contract tương thích.

## 6. Ví dụ runnable 1: quyền của owner, quyền của worker và close

Đây là chương trình độc lập **JDK 22+**, không dùng JNI hoặc thư viện C. Nó kiểm tra ba trường hợp:

1. Owner thread đọc/ghi native segment thành công.
2. Worker thread có Java reference tới segment nhưng đọc thất bại bằng `WrongThreadException`; worker cũng không được đóng arena.
3. Owner đóng arena đúng quy định. Sau close, owner cố đọc lại sẽ nhận `IllegalStateException`.

Tạo file **`ConfinedArenaOwnerDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicReference;

public final class ConfinedArenaOwnerDemo {
    public static void main(String[] args)
            throws InterruptedException {

        MemorySegment escaped;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_INT);

            segment.set(ValueLayout.JAVA_INT, 0, 42);

            System.out.println(
                    "ownerAccessible="
                    + segment.isAccessibleBy(Thread.currentThread()));
            System.out.println(
                    "ownerValue="
                    + segment.get(ValueLayout.JAVA_INT, 0));

            AtomicReference<String> readOutcome =
                    new AtomicReference<>();

            Thread reader = new Thread(() -> {
                boolean allowed =
                        segment.isAccessibleBy(Thread.currentThread());

                try {
                    segment.get(ValueLayout.JAVA_INT, 0);
                    readOutcome.set(allowed + "/unexpectedSuccess");
                } catch (WrongThreadException ex) {
                    readOutcome.set(allowed + "/WrongThreadException");
                }
            }, "reader");

            reader.start();
            reader.join();
            System.out.println("workerRead=" + readOutcome.get());

            AtomicReference<String> closeOutcome =
                    new AtomicReference<>();

            Thread closer = new Thread(() -> {
                try {
                    arena.close();
                    closeOutcome.set("unexpectedSuccess");
                } catch (WrongThreadException ex) {
                    closeOutcome.set("WrongThreadException");
                }
            }, "closer");

            closer.start();
            closer.join();
            System.out.println("workerClose=" + closeOutcome.get());
            System.out.println(
                    "aliveBeforeOwnerClose="
                    + arena.scope().isAlive());

            escaped = segment;
        }

        System.out.println(
                "aliveAfterOwnerClose=" + escaped.scope().isAlive());

        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
            System.out.println("afterClose=unexpectedSuccess");
        } catch (IllegalStateException ex) {
            System.out.println("afterClose=IllegalStateException");
        }
    }
}
~~~

Biên dịch và chạy với **JDK 22 hoặc cao hơn**:

~~~bash
javac ConfinedArenaOwnerDemo.java
java ConfinedArenaOwnerDemo
~~~

**Stdout dự kiến khi chạy thành công:**

~~~text
ownerAccessible=true
ownerValue=42
workerRead=false/WrongThreadException
workerClose=WrongThreadException
aliveBeforeOwnerClose=true
aliveAfterOwnerClose=false
afterClose=IllegalStateException
~~~

Phân tích từng dòng:

- Main tạo arena bằng `Arena.ofConfined()`, vì vậy `isAccessibleBy(Thread.currentThread())` trả `true`. Main ghi và đọc `42`.
- `reader` nhận biến `segment` nhờ Java lambda capture nhưng là một Java thread khác. `isAccessibleBy` trả `false`; `get` bị từ chối bằng `WrongThreadException`.
- `closer` cũng là thread khác. `arena.close()` bị từ chối bằng `WrongThreadException` nên arena **chưa đóng**. Lúc này `scope().isAlive()` trên main vẫn là `true`.
- Khi main ra khỏi `try`, Java tự gọi `close()` **trên main**; arena đóng thành công.
- `escaped` vẫn trỏ tới Java `MemorySegment` nhưng backing native memory đã hết hiệu lực, nên `scope().isAlive()` là `false`. Main (vẫn đúng thread) đọc lại gặp `IllegalStateException`.

Chương trình sử dụng `AtomicReference` và `join()` để đưa kết quả worker về main theo thứ tự xác định; nó không dựa vào thứ tự in từ các thread chạy song song. Mã cố ý bắt exception của hai hành vi sai để **minh họa**; trong logic nghiệp vụ, thay vì thường xuyên gây exception rồi bắt, nên thiết kế đúng ownership ngay từ đầu.

**Cần nhớ:** `WrongThreadException` nằm trong package **`java.lang`**, nên có thể dùng trực tiếp như trên; không import nhầm `java.lang.foreign.WrongThreadException`. Đây là unchecked exception, không phải một dạng `IllegalStateException`.

## 7. Ví dụ runnable 2: chia sẻ kết quả bằng bản sao Java, không chia sẻ confined segment

Khi worker thread khác cần dữ liệu, phương án an toàn và thường đơn giản là:

1. Owner cấp phát native memory với `Arena.ofConfined()`.
2. Owner tính toán và **sao chép dữ liệu** thành `int[]` hoặc giá trị Java thông thường **trước khi close**.
3. Đóng arena trên owner.
4. Truyền bản sao Java cho worker; worker không đụng vào confined segment.

Tạo file **`ConfinedCopyHandoffDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicInteger;

public final class ConfinedCopyHandoffDemo {
    public static void main(String[] args)
            throws InterruptedException {

        int[] snapshot;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 2, 3, 5, 7);

            snapshot = numbers.toArray(ValueLayout.JAVA_INT);
        }

        AtomicInteger result = new AtomicInteger();

        Thread worker = new Thread(() -> {
            int sum = 0;
            for (int number : snapshot) {
                sum += number;
            }
            result.set(sum);
        }, "sum-worker");

        worker.start();
        worker.join();

        System.out.println("copiedLength=" + snapshot.length);
        System.out.println("copiedSum=" + result.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConfinedCopyHandoffDemo.java
java ConfinedCopyHandoffDemo
~~~

**Stdout:**

~~~text
copiedLength=4
copiedSum=17
~~~

`arena.allocateFrom(ValueLayout.JAVA_INT, 2, 3, 5, 7)` là cú pháp JDK 22+; `numbers.toArray(ValueLayout.JAVA_INT)` sao chép dữ liệu sang **Java `int[]` độc lập**. Sau khi arena bị đóng, Java array vẫn hợp lệ, vì lifetime của nó không còn phụ thuộc vào native arena. Worker chỉ đọc dữ liệu Java nên không vi phạm FFM thread confinement.

Nếu không muốn copy vì dữ liệu rất lớn, phải chọn kiến trúc phù hợp hơn, chẳng hạn một confined owner thread xử lý toàn bộ thao tác native, hoặc `Arena.ofShared()` đi kèm đồng bộ và lifecycle rõ ràng. Không có phép “chuyển owner” của confined arena qua một setter đơn giản.

## 8. Ví dụ runnable 3: thực sự cần cùng segment trên nhiều thread

Đối chiếu `Arena.ofConfined()` và `Arena.ofShared()`:

| Tiêu chí | Confined arena | Shared arena |
| --- | --- | --- |
| Factory | `Arena.ofConfined()` | `Arena.ofShared()` |
| Owner thread | Có, thread tạo arena | Không gắn vào một owner thread |
| Segment có được đọc/ghi từ thread khác không? | **Không** | **Có**, nếu scope còn sống và điều kiện khác phù hợp |
| Ai được close? | Owner thread | Bất kỳ thread nào theo contract, phải điều phối với truy cập đang diễn ra |
| Trách nhiệm đồng bộ mutable memory | Có thể đơn giản hơn nhờ thread confinement | **Vẫn bắt buộc tự thiết kế**; không tự thread-safe |
| Lifetime | Dọn xác định bằng close | Dọn xác định bằng close, nhưng cần tránh close khi còn người dùng |
| Tình huống phù hợp | Native work ngắn, đơn luồng, buffer tạm | Đọc song song hoặc chia sẻ native region có kiểm soát |

Chương trình sau dùng shared arena và **chỉ đọc** từ worker sau khi main đã ghi xong; `join()` bảo đảm worker kết thúc **trước khi arena close**.

Tạo file **`SharedArenaReadDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicReference;

public final class SharedArenaReadDemo {
    public static void main(String[] args)
            throws InterruptedException {

        try (Arena arena = Arena.ofShared()) {
            MemorySegment values = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 11, 13);

            AtomicReference<String> observation =
                    new AtomicReference<>();

            Thread reader = new Thread(() -> {
                boolean allowed = values.isAccessibleBy(
                        Thread.currentThread());
                int total = values.getAtIndex(
                        ValueLayout.JAVA_INT, 0)
                        + values.getAtIndex(
                        ValueLayout.JAVA_INT, 1);

                observation.set(allowed + "/" + total);
            }, "shared-reader");

            reader.start();
            reader.join();

            System.out.println(
                    "sharedRead=" + observation.get());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SharedArenaReadDemo.java
java SharedArenaReadDemo
~~~

**Stdout:**

~~~text
sharedRead=true/24
~~~

Phân tích:

- `Arena.ofShared()` cho phép worker truy cập `values`.
- Main tạo và điền segment **trước** `Thread.start()`; `Thread.start()` có quan hệ happens-before thích hợp đối với việc xuất bản kết quả ban đầu cho worker. Không có việc ghi/đọc native memory đồng thời trong ví dụ.
- Worker chỉ đọc, sau đó `join()` trả về; main mới ra khỏi `try` để close arena.
- **Không kết luận** rằng mọi truy cập đồng thời đến native memory thông qua shared arena đều an toàn. Với nhiều writer hoặc writer-reader đồng thời, phải có synchronization thích hợp; API FFM không tự áp dụng toàn bộ Java Memory Model cho các thao tác truy cập off-heap như object fields.

Nếu áp dụng `ofShared()` chỉ để “né `WrongThreadException`” mà không quy định thread nào đóng và khi nào không còn người dùng, bạn đã đổi **lỗi confinement dễ nhận thấy** thành nguy cơ **race và lifecycle** phức tạp hơn.

## 9. Những cách handoff hợp lệ và không hợp lệ

### 9.1. Owner thực hiện native work; thread khác chỉ gửi yêu cầu

Hợp đồng hữu ích trong thiết kế actor/event-loop:

~~~text
Thread owner
    |
    +-- Arena.ofConfined()
    +-- tạo native segments
    +-- vòng lặp xử lý message/command
    |       +-- nhận yêu cầu từ các worker qua queue thread-safe
    |       +-- tự get/set trong owner thread
    |       +-- trả Java result/snapshot
    +-- dừng nhận command mới
    +-- close arena trên owner thread
~~~

Worker threads không giữ `MemorySegment` của confined arena để dereference trực tiếp. Chúng chỉ gửi command qua Java `BlockingQueue`, `Executor` đơn luồng hoặc cơ chế message passing tương đương; **owner** thực hiện các thao tác FFM.

Lợi ích: memory safety dễ suy luận, close trong cùng thread, không cần chia sẻ native mutable state giữa threads. Chi phí: không tận dụng trực tiếp cùng vùng memory trên nhiều threads, có overhead queue và có thể có nút cổ chai.

### 9.2. Mỗi worker tự tạo một confined arena

~~~java
// Minh họa lời gọi trong worker thread, không phải chương trình đầy đủ.
Runnable job = () -> {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment tmp =
                arena.allocate(ValueLayout.JAVA_LONG);
        tmp.set(ValueLayout.JAVA_LONG, 0, 100L);

        long computed = tmp.get(ValueLayout.JAVA_LONG, 0);
        // Gửi computed về Java queue/future, KHÔNG gửi tmp.
    }
};
~~~

Nếu công việc có thể chia thành nhiều phần độc lập, để **mỗi worker tạo và đóng arena của chính mình** thường đơn giản hơn việc chia sẻ một confined segment. Chú ý: task được submit vào thread pool có thể chạy ở thread bất kỳ, nhưng arena được tạo **bên trong worker đang chạy** thì owner được xác lập đúng.

Không nên tạo arena ở producer thread rồi đưa instance arena vào queue để consumer worker dùng. Arena đã confined vào producer từ thời điểm tạo.

### 9.3. Snapshot Java hoặc sao chép sang native shared allocation

Đối với kết quả nhỏ/vừa: snapshot Java `byte[]`/`int[]`/record/immutable object. Với dữ liệu lớn thực sự cần native shared memory, có thể cấp phát **đích trong `Arena.ofShared()`** rồi **copy dữ liệu từ confined source trên owner thread** vào đích, sau đó mới cho worker dùng. Khi copy, cả source và destination phải đang sống và cho phép owner truy cập.

~~~java
// Mẫu minh họa trong owner thread:
try (Arena confined = Arena.ofConfined();
     Arena shared = Arena.ofShared()) {

    MemorySegment source = confined.allocate(16);
    MemorySegment destination = shared.allocate(16);

    // source và destination còn sống, owner truy cập được cả hai.
    destination.copyFrom(source);

    // Sau copy, worker chỉ truy cập destination và phải kết thúc
    // trước khi shared.close() diễn ra.
}
~~~

Đây **không phải chương trình đa luồng hoàn chỉnh**; sample chỉ mô tả thao tác copy. Nếu native memory chứa pointers trỏ tới allocations trong confined arena, **copy các byte pointer không kéo dài lifetime vùng nhớ mà pointer đó trỏ vào**. Cần deep-copy hoặc điều chỉnh ownership theo ABI thật.

### 9.4. Không có `transferOwnership()` tự động

Không dùng những cách sau để “chuyển” owner:

- Gán `MemorySegment` vào static field;
- Đưa segment vào `CompletableFuture` rồi complete ở owner;
- Đưa segment qua `BlockingQueue`;
- Chuyển `segment.address()` thành `long` rồi tái tạo `MemorySegment.ofAddress(...)` ở thread khác;
- Tạo `segment.asSlice(...)`, `segment.asReadOnly()` hoặc truyền qua `ByteBuffer`;
- Dùng `ThreadLocal` để giữ handle trên worker khác.

Những hành động này có thể làm **giá trị/địa chỉ** đi qua thread, nhưng không thay đổi quyền sở hữu của backing allocation. Cố dùng raw address để bypass checks còn nguy hiểm hơn vì JVM có thể không theo dõi bounds/lifetime ở lớp wrapper mới.

## 10. Vì sao `asSlice` và `asReadOnly` không phá confinement?

~~~java
// Minh họa, segment thuộc Arena.ofConfined():
MemorySegment slice = segment.asSlice(8, 16);
MemorySegment ro = segment.asReadOnly();
~~~

- `slice` có kích thước/offset khác, nhưng **scope và backing allocation vẫn là của segment gốc**.
- `ro` mang thuộc tính chỉ đọc, nhưng **không** thay đổi owner thread của scope.
- `slice.get(...)` và `ro.get(...)` từ worker không phải owner vẫn bị kiểm tra confinement khi truy cập.
- Sau khi arena đóng, cả segment gốc, slice và read-only view đều không còn được đọc/ghi nội dung.
- Một `ByteBuffer` view tạo từ native segment cũng không phải “giấy phép” bỏ qua lifetime/thread access contract; đừng xây giải pháp dựa vào chuyện một view có thể được truyền như Java object.

### Tại sao không dùng `reinterpret` để thoát giới hạn?

`MemorySegment.reinterpret(...)` là nhóm API restricted vì có thể giả định lại spatial/temporal bounds cho địa chỉ native. Nếu dùng sai, rủi ro không còn là chỉ `WrongThreadException`: có thể gây **memory corruption hoặc crash JVM**.

Không dùng `reinterpret`, `ofAddress` và pointer arithmetic làm workaround cho confined arena thread ownership. Khi cần đa luồng, thiết kế **shared arena với synchronization và ownership** hoặc sao chép dữ liệu; không bỏ safety checks bằng một wrapper chứa địa chỉ thô.

## 11. Những lỗi phổ biến khác: lifetime, alignment, bounds, read-only

`WrongThreadException` không phải lỗi duy nhất có thể xảy ra khi làm việc với segment:

| Tình huống | Loại lỗi thường thấy theo API JDK 22 | Cách sửa đúng |
| --- | --- | --- |
| Đọc/ghi segment confined từ thread khác | `WrongThreadException` | Thao tác trên owner hoặc chọn kiến trúc shared có kiểm soát |
| Đóng confined arena từ non-owner | `WrongThreadException` | Đảm bảo owner thực thi close |
| Đọc/ghi segment sau khi arena close | `IllegalStateException` | Không escape segment quá lifetime; copy dữ liệu trước close |
| Gọi `arena.close()` lần thứ hai | `IllegalStateException` | Một owner chịu trách nhiệm đóng đúng một lần |
| Truy cập ngoài byte bounds | `IndexOutOfBoundsException` | Dùng `byteSize()`, offsets/index và layouts đúng |
| Layout alignment không phù hợp | `IllegalArgumentException` | Chọn layout phù hợp alignment hoặc unaligned layout khi cần |
| Ghi qua read-only view | `IllegalArgumentException` | Chọn writable segment hoặc không ghi |
| Cấp phát kích thước âm/căn chỉnh không hợp lệ | `IllegalArgumentException` | Validate size/alignment trước cấp phát |
| Close shared arena lúc segment đang trong foreign call | Có thể bị từ chối hoặc cần đợi hoạt động liên quan | Điều phối lifecycle, chờ worker/dowcall hoàn thành |
| Truy cập native address được tái tạo tùy tiện | Có thể crash/corrupt ngoài bảo vệ FFM | Không tự gán pointer bounds/lifetime khi chưa xác minh ABI |

### 11.1. `byteSize()` không thay cho scope/owner check

Ví dụ một segment có byteSize 16 không chứng minh bạn được đọc 16 bytes ngay bây giờ. Cần **bốn chiều hợp lệ**:

1. **Spatial bounds:** `0 <= offset` và `offset + layout.byteSize() <= byteSize()`, tránh overflow khi tự tính.
2. **Temporal bounds:** scope còn alive.
3. **Thread access:** thread hiện tại được phép truy cập.
4. **Layout/write permissions:** alignment đúng, segment không read-only nếu ghi; native layout/endianness phù hợp.

### 11.2. Không nhầm confined với “synchronized”

Một confined arena giúp bảo đảm segment chỉ truy cập trong owner thread. Điều này làm giảm nhiều loại shared-memory races vì **không có truy cập hợp lệ từ thread khác**. Nhưng arena **không phải một Java lock**:

- Không có việc “lock arena rồi worker khác truy cập”;
- `synchronized(arena)` không cấp quyền cho non-owner;
- `volatile MemorySegment` chỉ đảm bảo visibility của **Java reference**, không thay đổi confinement;
- `AtomicReference<MemorySegment>` chỉ truyền reference qua thread một cách nguyên tử, **không** chuyển ownership.

## 12. So sánh `ofConfined`, `ofShared`, `ofAuto` và `global`

| Factory | Quyền truy cập | Có close tường minh? | Điểm cần nhớ |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Chỉ thread tạo arena | Có; owner phải close | Nên dùng cho native work đơn luồng, thời gian sống rõ |
| `Arena.ofShared()` | Bất kỳ thread nào | Có; cần phối hợp mọi người dùng | Shared access không phải tự động data-race-free |
| `Arena.ofAuto()` | Bất kỳ thread nào | Không; close ném `UnsupportedOperationException` | Lifetime được GC quản lý, không xác định thời điểm giải phóng |
| `Arena.global()` | Bất kỳ thread nào | Không; close ném `UnsupportedOperationException` | Memory có lifetime toàn cục, không phải vùng nhớ tạm cần dọn |

**Mốc phiên bản:** `Arena.ofConfined()` xuất hiện trong API preview JDK 21, và FFM trở thành API chính thức từ **JDK 22 (JEP 454)**. Các đoạn code `import java.lang.foreign.*` trong bài được trình bày cho JDK 22+. JDK 20 preview dùng factory `Arena.openConfined()` và các signatures khác, nên không thể chỉ mang ví dụ ở đây sang JDK 20 mà không đối chiếu Javadoc phiên bản.

**Không sử dụng `ofAuto()` chỉ vì ngại gọi close** khi cần giải phóng memory theo deadline nhất định. Ngược lại, không dùng `global()` cho từng request nhỏ vì native memory có thể tồn tại tới khi process kết thúc.

## 13. Arena trong FFM downcall: trách nhiệm khi truyền pointer cho C

Confined arenas thường được dùng để cấp phát một buffer có thời gian sống giới hạn rồi truyền vào native function **đồng bộ** thông qua FFM downcall.

Ví dụ ý tưởng:

~~~text
Java owner thread
    |
    +-- try (Arena arena = Arena.ofConfined()) {
    |       buffer = arena.allocate(...)
    |       downcall.invokeExact(buffer)  <-- C dùng buffer trong call
    |       đọc kết quả sau khi downcall return
    |   }  <-- owner close arena
    |
    +-- Không còn dùng buffer.
~~~

Điều kiện:

- Downcall được thực hiện từ đúng thread có quyền truy cập segment confined; native code biết kích thước/alignment/ABI của buffer.
- C không lưu pointer vào global state để dùng **sau khi Java đã close arena**.
- Khi C return, ứng dụng phải bảo đảm không có **native worker bất đồng bộ** còn đọc/ghi buffer; sự kiện “function return” không đủ nếu function chỉ enqueue công việc.
- Nếu C giữ pointer để callback sau, **confined buffer ngắn hạn không phù hợp**, trừ khi callback và lifetime được thiết kế không vượt qua phạm vi arena.
- Không dùng raw `long address` để thay cho quyết định ownership có kiểm chứng.

### 13.1. Ví dụ tình huống lỗi asynchronous native library

~~~text
Java:
  try (Arena a = Arena.ofConfined()) {
      MemorySegment buffer = a.allocate(4096);
      native_enqueue_work(buffer); // Trả về ngay, C dùng sau!
  } // a.close(): buffer bị giải phóng

C worker vài mili giây sau:
  đọc buffer -> use-after-free / corruption / crash
~~~

Vấn đề không nằm ở “method JNI hay FFM” mà ở **lifetime của native allocation**. Trước khi đóng arena, phải chờ xác nhận native work đã dừng sử dụng vùng nhớ. Khi phải chia sẻ giữa native threads và Java threads, thường cần arena shared cùng cơ chế giữ sống/synchronization rõ ràng, hoặc buffer được native library tự cấp phát và sở hữu theo API thích hợp.

**Nhớ:** Native code không tự hiểu `Arena` và không tự bị “bảo vệ” hoàn toàn bởi Java exception nếu dùng một pointer đã hết hạn bên C. FFM bounds/lifetime checks bảo vệ các Java-side operations đi qua API, không thể đảm bảo an toàn cho mọi raw C pointer escape.

## 14. Cách phối hợp với ExecutorService và CompletableFuture

### 14.1. Một task tạo arena ở đúng nơi thực thi

~~~java
// Minh họa kiểu thiết kế; executor được khai báo/đóng ở chỗ khác.
Future<Integer> future = executor.submit(() -> {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment cell = arena.allocate(ValueLayout.JAVA_INT);
        cell.set(ValueLayout.JAVA_INT, 0, 123);
        return cell.get(ValueLayout.JAVA_INT, 0);
    }
});
~~~

Code này đúng về **thread confinement** vì cùng một task tạo, dùng và đóng arena trên worker thread đang thực thi task. Trả **`Integer`** cho thread gọi, không trả `MemorySegment` gắn với arena sắp close.

### 14.2. Không trả segment confined đã đóng qua future

~~~java
// Anti-pattern minh họa:
CompletableFuture<MemorySegment> bad = CompletableFuture.supplyAsync(() -> {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    } // close trước khi caller có thể dùng result
});
~~~

Future có thể complete bằng Java object `MemorySegment`, nhưng memory đã hết hiệu lực. Đổi `return MemorySegment` thành `return int[]` hoặc một Java value được materialize trước close thường phù hợp hơn. Nếu thật sự muốn return một native buffer cho caller, hãy định nghĩa ownership và arena phù hợp để caller được phép đọc **trong lifetime được quản lý**, không dùng confined arena do worker tạo rồi đóng.

### 14.3. Tính chất của virtual threads

Thread confinement ràng buộc theo **định danh Java `Thread`**, không phải theo một assumption rằng virtual thread luôn gắn với một OS carrier thread duy nhất. Nếu một virtual thread tạo arena rồi tiếp tục chạy trong chính virtual thread ấy, hãy suy luận bằng Java thread identity và lifetime, không tự suy carrier OS thread; đặc biệt không mang segment sang **một virtual thread khác** chỉ vì chúng chạy trên cùng carrier.

Kiểm tra lại JDK mục tiêu và thư viện FFM/downcall cụ thể nếu chương trình kết hợp pinning, synchronous downcalls hoặc callback native; confinement không tự bảo đảm native operation có thể được chuyển tự do giữa threads.

## 15. Kiểm tra và xử lý lỗi trong code production

### 15.1. Chọn một chủ thể chịu trách nhiệm đóng

Với mỗi arena có thể close, tài liệu hóa:

- Owner thread nào tạo arena?
- Có bao nhiêu đoạn code được phép truy cập?
- Khi nào công việc kết thúc?
- Ai gọi close và làm sao đảm bảo đúng một lần?
- Có downcall/native callback/thread phụ đang giữ pointer không?
- Dữ liệu cần xuất ra ngoài được copy sang Java trước close chưa?

Đối với confined arena, câu trả lời đơn giản và có thể review: “**Worker T tạo arena, T thực hiện mọi truy cập, T đóng arena tại cuối try**”. Nếu mô hình không còn phù hợp, đừng cố vượt safety check.

### 15.2. Đừng coi việc catch `WrongThreadException` là phương án đồng bộ

Mẫu xấu:

~~~java
// Anti-pattern, minh họa:
try {
    segment.get(ValueLayout.JAVA_INT, 0);
} catch (WrongThreadException e) {
    // Thử lại sau hoặc thêm synchronized? Không giải quyết owner.
}
~~~

`WrongThreadException` báo **sai mô hình ownership**, không phải transient lock contention. Sleep rồi retry từ cùng non-owner thread không khiến owner tự đổi. Hướng sửa là thay luồng thực hiện truy cập hoặc đổi arena/lifetime có chủ đích.

### 15.3. Tránh nhầm `IllegalStateException` khi arena đóng và lỗi quyền thread

Một đoạn code có thể đồng thời vi phạm nhiều điều kiện (arena đã closed **và** chạy ở non-owner thread). Đừng viết test buộc một **thứ tự ưu tiên exception** nếu Javadoc không cam kết; muốn kiểm tra lỗi chính xác, tách các trường hợp: sai thread **khi arena còn alive**, và đúng thread **sau khi arena đã close**. Ví dụ runnable thứ nhất được tổ chức như vậy.

### 15.4. Cân nhắc synchronized data và raw off-heap

Nếu dùng shared arena và nhiều writers, `synchronized`/lock Java hoặc cơ chế native atomic/VarHandle phù hợp có thể là cần thiết. Thao tác `get`/`set` trên native memory **không mặc nhiên** có mọi đảm bảo visibility/atomicity như Java field access. Quy tắc JMM đối với off-heap cần đọc theo FFM package specification; nếu cần atomic updates hãy chọn primitives/VarHandle modes được hỗ trợ và ràng buộc memory ordering phù hợp.

**Confined arena** không giải quyết bài toán đồng bộ ứng dụng giữa các đối tượng Java khác nhau; nó chỉ kiểm soát truy cập vào segment dựa trên owner thread.

## 16. Tình huống quyết định chọn arena

| Nhu cầu | Cách tiếp cận thích hợp | Lý do |
| --- | --- | --- |
| Gọi một C function đồng bộ, tạo buffer tạm ở một thread | `Arena.ofConfined()` trong `try` | Lifetime đơn giản, owner rõ, dọn xác định |
| Mỗi request chạy riêng trên thread pool | Tạo confined arena **bên trong** từng task | Owner trùng thread chạy task |
| Chuyển kết quả nhỏ từ worker sang main | Copy sang Java array/value/record trước close | Không chuyển native pointer/arena ownership |
| Một shared read-only native buffer được nhiều threads đọc | `Arena.ofShared()`, publish rồi join trước close | Các threads được phép truy cập, lifetime phải phối hợp |
| Nhiều threads vừa đọc vừa ghi cùng memory | Shared arena cộng synchronization/atomic design | Thread access được phép nhưng memory consistency không miễn phí |
| Dữ liệu được native library giữ sau function return | Contract lifetime dài hơn, ownership đồng bộ | Tránh arena close quá sớm và use-after-free |
| Dữ liệu cần tồn tại tới process exit | `Arena.global()` nếu thật sự cần | Không có explicit close, không thích hợp cho request tạm |
| Không yêu cầu close có thời điểm chính xác | `Arena.ofAuto()` khi được chấp nhận | GC quản lý thời điểm giải phóng, không phù hợp hard deadline |

Mẹo chọn: nếu bạn còn bối rối “thread nào được đóng”, **quay lại thiết kế ownership** thay vì đổi ngẫu nhiên từ `ofConfined` sang `ofShared`.

## 17. Một số anti-pattern và cách sửa

### Sai 1: “Truyền `MemorySegment` qua queue là thread-safe”

~~~java
// Minh họa lỗi logic:
MemorySegment segment = confinedArena.allocate(128);
queue.put(segment); // Chỉ truyền Java reference.
~~~

Worker lấy được biến trong queue nhưng không vì thế có quyền đọc/ghi backing native memory. **Sửa:** queue command để owner xử lý, queue Java snapshot, hoặc shared arena có lifetime thật.

### Sai 2: “Gọi `synchronized (arena)` rồi close ở thread khác”

~~~java
// Sai về ownership dù có monitor.
synchronized (arena) {
    arena.close(); // Non-owner vẫn vi phạm confined contract.
}
~~~

Java monitor không thay đổi trường owner của arena. **Sửa:** yêu cầu owner thực thi close; dùng queue/owner executor nếu cần.

### Sai 3: “Chỉ cần lấy slice mới thì ai cũng đọc được”

`segment.asSlice` không cấp phát arena mới, không chuyển scope, không thay owner. **Sửa:** copy thành Java array hoặc native shared allocation riêng nếu cần.

### Sai 4: “`asReadOnly` chắc chắn truy cập đa luồng được”

Read-only chỉ cấm ghi qua view, không thay owner. **Sửa:** dùng shared arena cho truy cập chéo thread có chủ đích; read-only không phải giải pháp cho WrongThreadException.

### Sai 5: “Một `long` địa chỉ đã thoát khỏi arena nên không sợ close”

Địa chỉ raw không giữ allocation còn sống. Sau close có thể trỏ vào vùng đã free/tái sử dụng. **Sửa:** đảm bảo pointer không escape quá lifetime; không dựng lại `ofAddress` để lách kiểm tra.

### Sai 6: “GC tự cleanup confined arena, bỏ `try` được”

`Arena.ofConfined()` được thiết kế cho explicit close và lifetime xác định. Bỏ close có thể gây rò tài nguyên native. **Sửa:** `try-with-resources` và close trên owner thread.

### Sai 7: “Cứ close arena từ watchdog thread khi worker bị treo”

Confined arena không cho watchdog thread close; thêm nữa, native function có thể đang dùng pointer. **Sửa:** hợp đồng hủy hợp tác, worker owner đóng khi safe; nếu code native không hợp tác cần timeout ở đúng tầng hoặc process isolation.

### Sai 8: “Chỉ cần `scope().isAlive() == true`”

Scope alive không biểu thị quyền owner; một non-owner vẫn không thể `get/set`. **Sửa:** dùng đúng owner design, kiểm tra `isAccessibleBy` khi cần chẩn đoán, và để access API kiểm tra tại thời điểm thao tác.

### Sai 9: “Chuyển sang `Arena.ofShared()` sẽ tự hết data race”

Shared arena cho phép thread khác truy cập nhưng **không** tự tổ chức các mutable accesses hoặc đảm bảo mã native đang xử lý pointer kết thúc trước close. **Sửa:** xác định protocol publish/consume/close, khóa hoặc atomics thích hợp.

## 18. Quy trình review và test

### 18.1. Checklist review

- [ ] Biên dịch trên **JDK 22+** với import `java.lang.foreign`; không trộn API preview `Arena.openConfined`.
- [ ] Arena confined được tạo trong **đúng thread** sẽ sử dụng nó.
- [ ] Mọi thao tác `get/set/toArray/copy` native memory đều diễn ra trên owner thread.
- [ ] Mọi closure được thiết kế **đóng đúng một lần** trên owner thread.
- [ ] Không trả một `MemorySegment` của arena đã close ra `Future` hoặc API public.
- [ ] Không dùng `asSlice/asReadOnly/ByteBuffer` để che giấu quyền truy cập sai.
- [ ] Khi dùng upcall/downcall, native pointer không escape quá scope.
- [ ] Khi dùng `Arena.ofShared()`, có synchronization và protocol chờ mọi worker xong trước close.
- [ ] Có test hai lỗi riêng biệt: non-owner access và owner access-after-close.
- [ ] Có test bounds, alignment, read-only, size/overflow cho inputs quan trọng.
- [ ] Có test ngoại lệ trong `try` vẫn close, không double-close.
- [ ] Khi đo hiệu năng, không đánh đổi thread safety và lifetime chỉ để giảm một phép copy nhỏ.

### 18.2. Các test tối thiểu

| Test | Kỳ vọng |
| --- | --- |
| Owner tạo confined arena, `get/set` trong `try` | Thành công |
| Worker gọi `isAccessibleBy(worker)` trên segment confined | `false` |
| Worker gọi `get` trên segment confined còn sống | `WrongThreadException` |
| Worker gọi `arena.close()` trên confined arena còn sống | `WrongThreadException`, arena không bị đóng |
| Owner gọi `arena.close()` khi không còn sử dụng | Thành công, scope không còn alive |
| Owner đọc segment sau owner close | `IllegalStateException` |
| Slice của confined segment được đọc từ worker | Cũng bị ràng buộc bởi owner |
| Owner `toArray` trước close rồi worker đọc Java array sau close | Thành công |
| Shared arena, worker chỉ đọc sau publish và trước join/close | Thành công |
| Shared arena, truy cập mutable đồng thời | Cần test synchronization/visibility thực tế, không dựa riêng `ofShared` |

Đối với chương trình runnable, có thể kiểm tra version:

~~~bash
java -version
javac -version
javac ConfinedArenaOwnerDemo.java
java ConfinedArenaOwnerDemo
~~~

Chương trình chỉ dùng allocation và Java-side FFM segment access, nên trong **JDK 22** không cần `--enable-preview` hoặc thư viện C. `--enable-native-access=ALL-UNNAMED` liên quan đến các phương thức FFM **restricted** như một số downcalls/`reinterpret`, không phải điều kiện mặc định của `Arena.ofConfined()` + `allocate` + `get/set` ở ví dụ này.

## 19. Tự kiểm tra kiến thức

1. Trong `Arena.ofConfined()`, thread nào trở thành owner?
2. Một `MemorySegment` được tạo trên main và chuyển vào lambda worker. Worker có thể `get(ValueLayout.JAVA_INT, 0)` không? Kể cả khi main vẫn giữ arena mở?
3. Khi worker gọi `arena.close()` với một confined arena do main tạo, loại exception là gì?
4. Nếu main là owner nhưng arena đã đóng, `segment.get(...)` thường gặp lỗi gì?
5. Vì sao `scope().isAlive()` không đủ để xác định một thread được phép truy cập?
6. Tạo `segment.asSlice(...)` hoặc `asReadOnly()` có đổi owner không?
7. Vì sao `AtomicReference<MemorySegment>` không phải cách chuyển owner?
8. Nếu muốn gửi dữ liệu sang Java worker thread sau khi arena close, có thể dùng `segment.toArray(...)` theo thứ tự nào?
9. Khi nào nên chọn `Arena.ofShared()` thay vì `ofConfined()`?
10. `ofShared()` có tự làm mọi `get/set` off-heap thread-safe không?
11. Nếu C lưu raw pointer vào segment rồi chạy bất đồng bộ sau khi Java đóng arena, có thể có hậu quả gì?
12. Có thể dùng `Arena.global()` cho từng request ngắn mà đòi release memory sau request không?
13. Khi submit task cho executor, nên tạo confined arena trong producer hay trong worker?
14. `Arena.close()` gọi hai lần có được coi là no-op không?
15. Trong ví dụ owner demo, vì sao `aliveBeforeOwnerClose=true` dù worker đã cố đóng arena?
16. `WrongThreadException` có nằm trong `java.lang.foreign` không?

**Đáp án gợi ý:** (1) Java thread gọi factory; (2) không, `WrongThreadException` khi đọc native memory; (3) `WrongThreadException`; (4) `IllegalStateException`; (5) lifetime và thread permission là hai kiểm tra khác; (6) không; (7) chỉ chuyển Java reference, không đổi scope; (8) owner copy **trước close**, worker đọc Java array sau; (9) khi cần nhiều threads truy cập cùng native segment trong lifetime có kiểm soát; (10) không, vẫn cần synchronization; (11) use-after-free/corruption/crash; (12) không phù hợp vì không close; (13) trong worker thực sự thao tác; (14) không, thường `IllegalStateException`; (15) wrong-thread close thất bại, không đóng arena; (16) không, thuộc `java.lang`.

## 20. Tài liệu chính thức

- [Java SE 22 — `Arena` (factory `ofConfined`, `ofShared`, `close`)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 — `MemorySegment` (truy cập, `isAccessibleBy`, scope, slices)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 — `MemorySegment.Scope` (lifetime, `isAlive`)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [Java SE 22 — `WrongThreadException` thuộc `java.lang`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/WrongThreadException.html)
- [Java SE 22 — package `java.lang.foreign`: memory model, restricted methods](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)
- [Java Developers — Access Off-Heap or On-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/)

**Kết luận:** `Arena.ofConfined()` là lựa chọn mạnh cho native memory tạm thời khi **một Java thread** có thể tạo, truy cập và đóng toàn bộ arena. Nó kiểm soát **cả quyền truy cập theo thread** lẫn **vòng đời vùng nhớ**. Nếu phải truyền kết quả sang thread khác, ưu tiên sao chép thành Java data hoặc để mỗi worker tạo arena riêng; khi thực sự cần truy cập chung native memory, dùng `Arena.ofShared()` với quản lý synchronization và lifetime đúng đắn. Không dùng việc chia sẻ Java reference, slice, read-only view hoặc raw pointer làm cách lách giới hạn của confined arena.
