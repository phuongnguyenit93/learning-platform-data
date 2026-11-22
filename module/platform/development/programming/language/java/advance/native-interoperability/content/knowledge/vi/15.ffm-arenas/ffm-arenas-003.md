# Arena.ofShared và quy tắc đóng khi có nhiều luồng sử dụng

## Mục tiêu

Từ JDK 22, Foreign Function & Memory API (FFM, JEP 454) đã là API chuẩn trong package `java.lang.foreign`. `Arena` cấp phát và quản lý vòng đời của các vùng nhớ native được biểu diễn bởi `MemorySegment`. Khi chỉ một thread làm việc, `Arena.ofConfined()` thường đơn giản nhất. Nhưng khi **nhiều Java threads phải truy cập cùng một hoặc nhiều native segments**, `Arena.ofShared()` cho phép việc đó mà không giới hạn truy cập vào thread khởi tạo.

Tuy vậy, **“shared” không có nghĩa “đóng lúc nào cũng an toàn”**. Nó cũng **không tự đồng bộ hóa dữ liệu** khi nhiều thread cùng đọc/ghi. Chủ đề của bài là thiết kế hợp đồng phối hợp giữa người quản lý arena và những worker đang sử dụng memory.

Sau bài học, bạn có thể:

- Phân biệt `Arena.ofShared()`, `Arena.ofConfined()`, `Arena.ofAuto()` và `Arena.global()`.
- Hiểu khái niệm scope, thời hạn truy cập, quyền truy cập xuyên thread và hiệu ứng đối với mọi segments/slices được cấp bởi arena.
- Hiểu chính xác `Arena.close()`: close thành công làm scope hết hiệu lực; close **không idempotent**; close có thể ném `IllegalStateException` khi segment đang được truy cập đồng thời.
- Tổ chức vòng đời **tạo → giao việc → chờ mọi công việc kết thúc → close** kể cả khi worker lỗi hoặc thread chờ bị interrupt.
- Phân biệt **lifecycle safety** với **data-race safety**; biết khi nào cần partition, lock hoặc atomic/VarHandle.
- Dùng `ReentrantReadWriteLock` như một cơ chế lease để ngăn close chen vào operation.
- Chạy một ví dụ Java JDK 22+ với bốn workers cùng sử dụng native segment và kiểm tra lỗi khi truy cập sau khi đóng.
- Nhận diện các bẫy với `ExecutorService.shutdown()`, `scope().isAlive()`, callback/reentrancy, native pointer escape và FFM downcalls.

> **Phiên bản:** Code chính dùng `java.lang.foreign.Arena`, `MemorySegment` và `ValueLayout` **ổn định từ JDK 22**; với JDK 22 không cần `--enable-preview`. JDK 17 không có package `java.lang.foreign` ổn định, nên không biên dịch ví dụ bằng `javac 17`. Nếu project vẫn chạy Java 17, có thể nghiên cứu `ByteBuffer.allocateDirect`/JNI hoặc API incubator đúng phiên bản, nhưng hợp đồng vòng đời sẽ khác.

## 1. Arena quản lý cả bộ nhớ và giới hạn thời gian

`MemorySegment` là một đối tượng Java mô tả vùng memory liên tục, có kích thước và phạm vi truy cập. `Arena` cấp phát vùng native và gắn các segment với một **scope**. Ngoài bounds theo byte, FFM kiểm soát **temporal bounds**: một segment không được truy cập sau khi scope của nó hết hiệu lực.

~~~text
        Arena.ofShared()
              |
          shared scope
              |
     +--------+---------+----------------+
     |                  |                |
     v                  v                v
native segment A   native segment B   mapped segment C
     |                  |                |
     +------------------+----------------+
              |
T1/T2/T3 được phép truy cập trong thời hạn scope còn sống
              |
coordinator chờ mọi người dùng xong
              |
          arena.close()
              |
      scope bị invalidated
              |
A, B, C và mọi slice của chúng không được truy cập nữa
~~~

Các điểm cần nhớ:

1. `Arena.ofShared()` tạo scope **không gắn với một owner thread cụ thể**. Segment của nó có thể được truy cập từ bất kỳ thread nào theo giới hạn còn lại của FFM.
2. Một thread bất kỳ có thể **gọi** `close()` trên shared arena. Đây là khả năng của API, **không** phải gợi ý để mỗi worker tự đóng khi xong.
3. **Khi `close()` hoàn tất bình thường**, scope không còn sống và native regions do arena cấp được giải phóng.
4. Một `MemorySegment`, một `asSlice(...)`, và một mapped segment dùng cùng arena **chia sẻ lifetime**. Giữ Java reference tới slice không kéo dài lifetime native sau close.
5. `MemorySegment` là đối tượng Java do GC quản lý; vùng **native** do arena cấp vẫn thuộc lifecycle của arena, không chờ Java GC khi arena đã được đóng tường minh.

### So sánh bốn loại Arena

| Kiểu | Thread được truy cập | Đóng tường minh | Điểm khác biệt |
|---|---|---|---|
| `Arena.ofConfined()` | Chỉ thread tạo arena | Có, chỉ thread sở hữu | Dễ kiểm soát, sai thread có thể ném `WrongThreadException` |
| `Arena.ofShared()` | Bất kỳ thread nào | Có, thread bất kỳ | Cần phối hợp close với các lượt sử dụng |
| `Arena.ofAuto()` | Bất kỳ thread nào | Không: `close()` ném `UnsupportedOperationException` | Lifetime phụ thuộc GC, không xác định thời điểm dọn |
| `Arena.global()` | Bất kỳ thread nào | Không: `close()` ném `UnsupportedOperationException` | Vùng memory có lifetime không giới hạn, tránh dùng bừa bãi |

API `Arena` được đặc tả là thread-safe ở mức triển khai, nhưng **không phải một cấu trúc dữ liệu có khóa bảo vệ mọi byte bên trong segment**. Thread-safe allocation và thread-safe access tới state nghiệp vụ là hai vấn đề riêng.

## 2. Hai loại an toàn khác nhau

### An toàn vòng đời (lifecycle/temporal safety)

T1 phải không còn sử dụng native memory khi coordinator đóng arena. Trên API FFM, mỗi access kiểm tra scope trong phạm vi runtime kiểm soát, và sau close thành công một access mới sẽ không hợp lệ. Tuy nhiên, ứng dụng vẫn phải sắp xếp các **operation gồm nhiều bước** và các native callbacks không bị kết thúc tài nguyên bất ngờ.

### An toàn dữ liệu (data-race safety)

Giả sử T1 và T2 cùng làm:

~~~java
int old = segment.get(ValueLayout.JAVA_INT, 0L);
segment.set(ValueLayout.JAVA_INT, 0L, old + 1);
~~~

Đây là **mảnh Java JDK 22+**, giả định `segment` còn sống và vùng đủ kích thước/alignment. Hai câu lệnh `get` và `set` **không phải phép tăng nguyên tử**. T1 và T2 có thể cùng đọc giá trị cũ, sau đó cả hai cùng ghi lại một kết quả → mất một lần tăng. `Arena.ofShared()` không sửa lỗi này.

Khi chỉ cần các workers xử lý những vùng **không chồng lấn**, có thể phân chia index riêng. Khi nhiều threads dùng chung cùng một vị trí, phải chọn một trong các công cụ:

- `synchronized`/`Lock` để tuần tự hóa thao tác liên quan;
- `VarHandle` với access mode được hỗ trợ, layout và alignment đúng để thực hiện các thao tác atomic thích hợp;
- mô hình single writer/multiple readers có happens-before rõ ràng;
- tổ chức dữ liệu thành các vùng riêng theo worker rồi giảm gộp sau khi join.

**Khóa để giữ tài nguyên sống** và **khóa để bảo vệ dữ liệu** có thể là hai khóa khác nhau. Không được coi việc có một `Arena.ofShared()` là đã giải quyết cả hai.

## 3. Close có những quy tắc chính xác nào?

Theo Java SE 22 API của `Arena.close()`:

| Trường hợp | Hợp đồng |
|---|---|
| Close thành công | `arena.scope().isAlive() == false`; các segments thuộc scope không được truy cập; native backing regions được giải phóng |
| Gọi close lần nữa | `IllegalStateException`; close **không idempotent** |
| Đang có truy cập đồng thời tới segment thuộc arena | Close **có thể ném `IllegalStateException`**, ví dụ đang có FFM downcall sử dụng segment |
| Gọi close confined arena từ thread khác owner | `WrongThreadException` |
| Gọi close trên `ofAuto()`/`global()` | `UnsupportedOperationException` |
| Custom cleanup action thất bại | `RuntimeException` có thể được ném theo hợp đồng |

**Điểm quan trọng:** `Arena.ofShared()` không hứa rằng `close()` sẽ đợi mọi worker hoàn tất. Đặc tả còn nêu điều kiện close **có thể thất bại khi segment đang được truy cập đồng thời**. Một chương trình đúng không sử dụng exception đó như một kỹ thuật chờ (“thử close liên tục cho tới khi hết lỗi”).

Và **không đánh dấu resource là CLOSED nếu chưa biết close đã hoàn tất thành công**. Nếu close bị lỗi do concurrent access, duplicate close hoặc cleanup khác, chính sách phải dựa vào nguyên nhân và trạng thái thực.

### API bảo đảm điều gì khi close thành công?

Sau một `close()` trả về bình thường:

- Scope của arena bị invalidated.
- Tất cả allocations/mappings thuộc arena mất quyền truy cập, không chỉ segment mà thread gọi close cầm trong tay.
- Các local variables/fields Java vẫn có thể giữ `MemorySegment` object, nhưng object đó **không còn quyền dùng native backing memory**.
- Access sau close bị từ chối, thường bằng `IllegalStateException`.

**Không nhầm “object Java vẫn còn” với “resource native vẫn còn”.** Đây là nguồn gây nhiều lỗi use-after-close trong code dùng FFM.

## 4. Vì sao nhiều thread cần một người điều phối đóng?

Thay vì cho mọi worker gọi `arena.close()` khi “tôi đã xong”, hãy thiết kế một owner:

~~~text
coordinator                  worker A         worker B
    |                           |                |
create shared arena           |                |
    |                           |                |
allocate segments             |                |
    |---- submit segment ------>|                |
    |-------------------------- submit ---------->|
    |                           |                |
    |                        access A          access B
    |                           |                |
    |<------- task A done ------|                |
    |<-------------------- task B done ----------|
    |
stop new submissions
join all in-flight work
    |
arena.close() ONE TIME
    |
CLOSED
~~~

Trong ví dụ thực tế, coordinator cần đảm bảo:

1. Những người sử dụng biết chính xác lifetime được mượn; không lưu một `MemorySegment` hoặc raw pointer vào công việc tương lai ngoài giao thức đã định.
2. Không cấp thêm công việc sau khi bắt đầu shutdown.
3. Đợi **tất cả** users đang dùng segment kết thúc, kể cả khi một Future ném exception.
4. Sau khi tài nguyên không còn người dùng, gọi `close()` một lần.
5. Chỉ cho phép release/recreate dưới hợp đồng đã định; không “sửa” một segment hết scope bằng cách giữ lại địa chỉ cũ.

**Nguyên tắc:** “Shared cho phép nhiều thread dùng; owner đóng sau khi mọi thread đã trả quyền dùng”.

## 5. Ví dụ hoàn chỉnh JDK 22+: bốn worker ghi bốn vùng riêng

Chương trình sau dùng một `Arena.ofShared()`, cấp một vùng native đủ cho bốn `int`, rồi submit bốn tasks vào thread pool. Mỗi worker được gán một index duy nhất. Sau khi các tasks hoàn tất, main đọc theo thứ tự và arena đóng. Cuối cùng chương trình thử dùng một slice đã thoát scope để chứng minh hiệu ứng close.

### 5.1. File `SharedArenaDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class SharedArenaDemo {
    private static final int WORKERS = 4;
    private static final ValueLayout.OfInt INT = ValueLayout.JAVA_INT;

    /*
     * Đợi TẤT CẢ task thực sự xong trước khi arena đóng.
     * Nếu thread chờ bị interrupt, vẫn chờ rồi khôi phục
     * cờ interrupt. Đây là chính sách học tập, không có timeout.
     */
    private static void shutdownAndJoin(ExecutorService pool) {
        pool.shutdown();
        boolean interrupted = false;

        try {
            for (;;) {
                try {
                    if (pool.awaitTermination(1, TimeUnit.DAYS)) {
                        break;
                    }
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        MemorySegment escapedSlice;

        try (Arena arena = Arena.ofShared()) {
            long bytes = (long) WORKERS * INT.byteSize();
            MemorySegment shared = arena.allocate(
                    bytes, INT.byteAlignment());

            // Slice có cùng scope, KHÔNG kéo dài lifetime.
            escapedSlice = shared.asSlice(0L, INT.byteSize());

            ExecutorService pool =
                    Executors.newFixedThreadPool(WORKERS);
            List<Future<?>> jobs = new ArrayList<>();

            try {
                for (int i = 0; i < WORKERS; i++) {
                    final int index = i;

                    jobs.add(pool.submit(() -> {
                        // Mỗi worker ghi slot riêng, không chồng lấn.
                        shared.setAtIndex(
                                INT, index, (index + 1) * 10);
                    }));
                }

                for (Future<?> job : jobs) {
                    job.get();
                }
            } finally {
                // Kể cả khi get() ném, worker khác vẫn được join.
                shutdownAndJoin(pool);
            }

            int[] values = new int[WORKERS];
            for (int i = 0; i < WORKERS; i++) {
                values[i] = shared.getAtIndex(INT, i);
            }

            System.out.println("values=" + Arrays.toString(values));
            System.out.println(
                    "sameScope="
                    + shared.scope().equals(escapedSlice.scope()));
            System.out.println(
                    "aliveInside=" + arena.scope().isAlive());

        } // arena.close() chỉ sau shutdownAndJoin.

        System.out.println(
                "aliveOutside=" + escapedSlice.scope().isAlive());

        try {
            escapedSlice.get(INT, 0L);
            System.out.println("unexpected access");
        } catch (IllegalStateException ex) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }
    }
}
~~~

### 5.2. Biên dịch và chạy

Dùng **JDK 22 hoặc mới hơn**:

~~~bash
java -version
javac -version
javac SharedArenaDemo.java
java SharedArenaDemo
~~~

Không cần thư viện C, không có bước JNI header, và không cần `--enable-preview` trên JDK 22. Nếu `javac` không tìm thấy `java.lang.foreign`, hãy kiểm tra `JAVA_HOME`, `PATH` và phiên bản JDK thực sự mà terminal đang dùng.

### 5.3. Output mong đợi

~~~text
values=[10, 20, 30, 40]
sameScope=true
aliveInside=true
aliveOutside=false
afterClose=IllegalStateException
~~~

Phân tích:

- Bốn worker chạy ở thứ tự scheduler tùy ý, nhưng index của mỗi worker được chốt bằng `final int index`. Worker 0 ghi 10 vào slot 0, worker 1 ghi 20 vào slot 1, v.v. Không có tranh chấp trên cùng vùng.
- `Future.get()` chờ kết thúc task và cung cấp quy tắc memory visibility để main thấy các kết quả của task sau khi completion.
- `shutdownAndJoin(pool)` đợi executor đạt trạng thái terminated **kể cả trong đường lỗi** trước khi try-with-resources có thể đóng arena.
- `escapedSlice` chia sẻ scope với `shared`; do đó `sameScope=true`.
- Bên trong `try`, scope còn sống. Sau khi đóng thành công, `aliveOutside=false`.
- Lệnh `escapedSlice.get(...)` sau close bị từ chối bằng `IllegalStateException`; vì exception được bắt, không có dòng `unexpected access`.

### 5.4. Vì sao không chỉ gọi shutdown()?

`ExecutorService.shutdown()` **không chờ** những tasks đã nhận hoàn tất: nó chỉ ngừng nhận tasks mới và cho tasks đang chạy tiếp tục. Nếu sau `shutdown()` bạn rời `try (Arena ...)` ngay, arena có thể bị đóng khi worker còn đang truy cập.

`Future.get()` đợi **một** task. Nếu một Future ném `ExecutionException`, vòng get có thể dừng trong khi những task khác chưa xong. Vì thế ví dụ dùng `finally` gọi `awaitTermination` để đợi **tất cả**, không chỉ task đã get thành công.

`shutdownNow()` cũng không bảo đảm worker đã dừng. Nó cố gắng interrupt, nhưng native calls và tasks không hợp tác có thể vẫn chạy. **Không đóng native memory chỉ vì đã gửi tín hiệu hủy.**

### 5.5. Điều gì nếu worker bị treo?

`shutdownAndJoin` trên đây cố ý chờ đến khi hoàn tất và khôi phục interrupt flag, nhằm bảo vệ lifetime. Nếu một worker treo vô hạn, việc chờ có thể kéo dài vô hạn. Đây là **một đánh đổi liveness**; ứng dụng production cần cancellation, deadline, task tracking và ownership protocol riêng. Tuy nhiên, **đã timeout không đồng nghĩa tài nguyên an toàn để free**. Khi không thể chứng minh users đã dừng, việc close có thể thất bại hoặc phá hỏng tác vụ ngoài sự kiểm soát của Java.

Đối với server, cần thiết kế quy trình shutdown graceful và một trạng thái thất bại rõ ràng thay vì bỏ qua workers đang dùng native pointers.

## 6. Sai lầm: gửi task rồi đóng arena ngay

Ví dụ **anti-pattern** sau có race:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
try (Arena arena = Arena.ofShared()) {
    MemorySegment region = arena.allocate(16);

    pool.submit(() -> {
        // Task có thể mới bắt đầu khi arena đã đóng.
        region.set(ValueLayout.JAVA_BYTE, 0L, (byte) 1);
    });
}
pool.shutdown();
~~~

Đây là **mảnh mã minh họa trong method JDK 22+** (cần imports). `submit` không đợi. Thread điều phối có thể rời try trước khi task bắt đầu, vì vậy việc dùng `region` bên worker sẽ thất bại với lifetime đã đóng, hoặc tạo ra tình huống close cạnh tranh.

Sửa đúng là **join tasks bên trong scope của arena**, hoặc chuyển arena thành resource do coordinator sống lâu hơn nhiệm vụ và chỉ close khi mọi lượt mượn trả xong.

Không sửa bằng `Thread.sleep(100)`. Timing trên scheduler thay đổi theo máy, CPU load, GC và I/O; sleep không chứng minh task đã hoàn thành.

## 7. Sai lầm: isAlive() được xem như một lock

~~~java
if (segment.scope().isAlive()) {
    // Một thread khác có thể đóng arena ngay sau if.
    int x = segment.get(ValueLayout.JAVA_INT, 0L);
}
~~~

Đây là **mảnh minh họa**, có biến `segment` được cấp phù hợp. `isAlive()` là **quan sát trạng thái tại một thời điểm**. Không có lease nào được tạo bởi điều kiện if.

Dù một thao tác FFM bị phát hiện truy cập vào scope đã đóng và ném `IllegalStateException`, ứng dụng vẫn có thể cần **tính nhất quán trên cả một nghiệp vụ nhiều bước**. Ví dụ:

~~~text
Thread A:
  kiểm tra isAlive() == true
                                  Thread B:
                                    close() thành công
  đọc/ghi segment -> exception
~~~

**Giải pháp đúng:** check và use đều phải nằm bên trong một vùng được bảo vệ bởi lifecycle lock/lease; close không thể vào khi thao tác đang giữ quyền dùng. Nếu chỉ cần xử lý batch tasks, join toàn bộ trước close cũng đáp ứng mục tiêu.

Không dựa vào `try/catch IllegalStateException` quanh mọi access để thay thế synchronization. Bắt lỗi hữu ích để xử lý tình trạng invalid, nhưng không bảo vệ tính nguyên tử của một operation gồm nhiều accesses.

## 8. Sai lầm: hai thread cùng đóng một Arena

`Arena.close()` **không idempotent**. Một chương trình gọi:

~~~java
Arena arena = Arena.ofShared();
arena.close();
// arena.close(); // IllegalStateException
~~~

là đủ để thấy hợp đồng. Shared arena có thể được close từ thread khác, nhưng **không** có nghĩa mọi thread nên tự gọi close khi không dùng nữa.

Mẫu sai:

~~~java
if (arena.scope().isAlive()) {
    arena.close();
}
~~~

Nếu hai threads cùng thấy true, cả hai có thể gọi close; một thread thành công, thread kia gặp `IllegalStateException`. `isAlive` không phải CAS/lock.

Một owner có thể cung cấp `close()` **idempotent ở mức wrapper**, trong đó chỉ một đường đóng thật sự thực hiện `arena.close()`. Đây là một hợp đồng ứng dụng bổ sung; nó không thay đổi tính **không idempotent** của Arena gốc.

Quan trọng: chỉ đánh dấu wrapper CLOSED **sau khi arena.close hoàn tất thành công**, không khi close vừa được gọi. Nếu close thất bại, phải báo lỗi và có phương án xử lý trạng thái thực.

## 9. State machine cho một service dùng lâu

Một service phân phối segment cho nhiều asynchronous tasks nên quản lý states:

~~~text
             CREATE / ALLOCATE
                    |
                    v
                   OPEN
         worker có thể acquire lease
             |           |
           lease A      lease B
             |           |
             v           v
           USE A        USE B
             |           |
   requestClose()       |
             |           |
             v           |
          CLOSING       |
     chặn lease mới     |
             |           |
             +---- wait--+
                    |
          active leases == 0
                    |
            arena.close() once
                    |
         +----------+------------+
         |                       |
      success                  failure
         |                       |
         v                       v
       CLOSED               CLOSE_FAILED
     scope invalid          không coi là CLOSED
~~~

**Quy tắc của coordinator:**

- OPEN: nhận thêm công việc theo chính sách cấp phát.
- CLOSING: không nhận lượt dùng mới; những tasks đã mượn được phép hoàn thành hoặc bị hủy **có xác nhận**.
- Chờ tổng số leases đang hoạt động về 0, hoặc đợi đầy đủ `Future`/callback/native completion.
- Thực hiện close đúng một lần, không tranh chấp với operator khác.
- Sau close thành công, CLOSED; operations tiếp theo bị từ chối.
- Khi close ném exception, không âm thầm chuyển CLOSED. Lỗi có thể do đã đóng trước, access còn hoạt động hoặc custom cleanup failure; chính sách phụ thuộc nguyên nhân.

Một token `MemorySegment` trả về worker mà **không có điều kiện lifetime** không phải lease. Lease là một cam kết phối hợp với close: tài nguyên không bị đóng trước khi worker nhả quyền dùng.

## 10. Mẫu lifecycle lease bằng ReentrantReadWriteLock

Trong Java, `ReentrantReadWriteLock` có thể cho phép **nhiều lượt đọc được bảo vệ đồng thời**, trong khi `close` cần quyền độc quyền và phải đợi những lượt đang dùng kết thúc.

Mẫu dưới đây là một class hợp lệ trên JDK 22+, có thể đặt vào `SharedInts.java`. Nó tập trung vào tính đúng đắn đơn giản: method `get` giữ read lock trong khi truy cập; `put` dùng write lock để tránh data races; `close` cũng lấy write lock và thực hiện một lần.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

final class SharedInts implements AutoCloseable {
    private final Arena arena = Arena.ofShared();

    private final MemorySegment segment = arena.allocate(
            4L * ValueLayout.JAVA_INT.byteSize(),
            ValueLayout.JAVA_INT.byteAlignment());

    private final ReentrantReadWriteLock lifecycle =
            new ReentrantReadWriteLock(true);

    private boolean closed;

    private void checkOpen() {
        if (closed) {
            throw new IllegalStateException("SharedInts closed");
        }
    }

    int get(int index) {
        Lock lease = lifecycle.readLock();
        lease.lock();
        try {
            checkOpen();
            return segment.getAtIndex(
                    ValueLayout.JAVA_INT, index);
        } finally {
            lease.unlock();
        }
    }

    void put(int index, int value) {
        Lock exclusive = lifecycle.writeLock();
        exclusive.lock();
        try {
            checkOpen();
            segment.setAtIndex(
                    ValueLayout.JAVA_INT, index, value);
        } finally {
            exclusive.unlock();
        }
    }

    @Override
    public void close() {
        Lock exclusive = lifecycle.writeLock();
        exclusive.lock();
        try {
            if (closed) {
                return; // wrapper đóng lặp lại là no-op
            }

            arena.close(); // không có ai giữ read/write lock
            closed = true; // chỉ cập nhật nếu close thành công
        } finally {
            exclusive.unlock();
        }
    }
}
~~~

**Vì sao mẫu này bảo vệ lifetime?**

1. `get` giữ read lock từ lúc check OPEN cho tới sau `segment.getAtIndex`. Close cần write lock, nên không thể xảy ra giữa check và get.
2. `put` giữ write lock suốt lệnh `set`, nên không có ghi đè đồng thời qua wrapper này.
3. `close` đợi tất cả lượt truy cập trong wrapper đã nhả lock, gọi `arena.close`, sau đó đánh dấu closed. Gọi close lần hai chỉ return, **không** gọi `arena.close` lần thứ hai.
4. Những callers vào sau khi closed sẽ ném `IllegalStateException` từ wrapper trước khi dùng segment native.

**Đây chỉ là một mẫu quản lý một wrapper.** Nếu segment thô bị xuất ra bên ngoài hoặc native code tự giữ địa chỉ, lock trong `SharedInts` **không bảo vệ những consumers đó**. Tất cả người sử dụng phải tham gia cùng hợp đồng lease hoặc việc close vẫn có thể xảy ra khi consumer bên ngoài đang dùng.

### Vì sao put dùng write lock, dù Arena là shared?

Để tránh đọc/ghi cùng slot cạnh tranh, mẫu chọn chính sách đơn giản là tuần tự hóa writes và readers. Điều đó có thể hạn chế concurrency. Nếu cần các worker cùng ghi **những vùng không chồng lấn**, bạn có thể cho các lượt sử dụng giữ **read lock cho lifetime** và dùng partition/atomic/data locks riêng. Nhưng phải chứng minh không có data race và không thả lifecycle lease trước khi operation thực sự xong.

### Bẫy read-lock → close reentrant

Đừng gọi `close()` ngay **bên trong** callback hoặc một code path đang giữ read lock trên cùng wrapper: nâng read lock lên write lock có thể deadlock. Với native callback có thể quay về Java và gọi close, hãy thiết kế reentrancy, deferred close hoặc state machine/lease riêng. `ReentrantReadWriteLock` không tự giải quyết việc chuyển từ read ownership thành exclusive close.

### Khi nào dùng synchronized đơn giản hơn?

Một wrapper có thể dùng `synchronized` trên mọi operation và `close`, cho phép **một** operation tại mỗi thời điểm. Cách này dễ review và thường đủ cho một resource nhỏ. `ReentrantReadWriteLock` hữu ích khi nhiều lượt read có thể chạy song song, nhưng không thay thế data atomicity hoặc ownership của native pointer.

## 11. Downcall và native pointer escape

Khi dùng FFM, một `MemorySegment` có thể được truyền đến native function qua downcall method handle. Theo API JDK 22, `Arena.close()` **có thể ném `IllegalStateException`** nếu segment thuộc arena đang được truy cập đồng thời, và tài liệu dùng downcall làm ví dụ.

~~~text
Thread T1: downcall(nativeProcess, segment)
                     |
                     +------ native C đang dùng pointer
                                   |
Thread T2: requestClose() ---------+
                     |
             close có thể thất bại,
             không mặc nhiên đợi đến khi T1 xong
~~~

Vì vậy, tốt nhất là **điều phối ở tầng ứng dụng** để không đóng arena khi đang có downcall hay một consumer khác.

**Trường hợp còn nguy hiểm hơn:** thư viện C nhận pointer từ downcall, **lưu nó vào queue nội bộ**, rồi return ngay; thread C khác chỉ dùng pointer về sau. Java `Future.get()` của thao tác submit đã hoàn tất, nhưng native consumer **chưa** xong. Nếu coordinator close arena lúc này, raw pointer trong C có thể hết lifetime.

FFM có thể kiểm soát truy cập thông qua API của nó, nhưng **không thể tự chứng minh lifetime của một địa chỉ thô mà native code giữ riêng**. Cần hợp đồng native rõ:

- Native code trả callback hoặc future chỉ khi thao tác sử dụng pointer thực sự kết thúc.
- Có token/lease hoặc retain/release cho buffer đang dùng bất đồng bộ.
- Owner chỉ close arena khi mọi native consumers đã xác nhận hoàn tất.
- Tránh truyền pointer tới hệ thống lưu giữ lâu hơn lifetime của arena.

Không coi `Arena.ofShared()` là tính năng “pin mọi pointer mãi mãi”.

## 12. Vòng đời của nhiều segments, slices và mappings

Một arena có thể cấp nhiều allocations:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment root = arena.allocate(64);
    MemorySegment left = root.asSlice(0L, 32L);
    MemorySegment right = root.asSlice(32L, 32L);

    // left/right có các bounds không chồng lấn;
    // cả hai dùng cùng scope với root.
}
// root, left, right đều không được dùng nữa.
~~~

Đoạn trên là mảnh Java JDK 22+. `asSlice` tạo một view, **không copy** dữ liệu và không tạo scope riêng. Arena đóng làm **mọi** segment liên quan hết quyền truy cập. Nếu worker T1 đã xong với left nhưng T2 còn dùng right, bạn **không thể đóng arena** mà không ảnh hưởng T2.

Memory-mapped segments được tạo bằng overload `FileChannel.map(..., Arena)` cũng có thể dùng scope của arena. Khi thiết kế shutdown:

- Đảm bảo workers đã ngừng đọc/ghi mapping.
- Với read-write mapping, gọi `force()` khi có yêu cầu đồng bộ xuống file theo đặc tả, và xử lý I/O errors.
- Đóng `FileChannel` và đóng `Arena` theo ownership/lifetime tương ứng; **close channel không thay thế close arena**.
- Không cho external process truncate file trong khi mapping còn được dùng nếu ứng dụng không có chính sách xử lý.
- Nếu các nhóm tác vụ có lifetime khác nhau, cân nhắc **arena riêng cho từng nhóm**; `Arena.close()` không phải API hủy riêng một slice.

## 13. Exception safety và thất bại khi shutdown

### Một Future lỗi không làm các Future khác tự hủy

~~~text
Future A: hoàn thành
Future B: ném ExecutionException
Future C: vẫn đang viết segment
Coordinator: bỏ vòng for vì lỗi B
~~~

Nếu tại đây coordinator thoát `try (Arena ...)`, Future C còn có thể đang dùng vùng native. Vì vậy, trong ví dụ runnable, `finally` vẫn gọi `shutdownAndJoin` để đợi pool terminated. Sau đó Java exception từ B có thể được truyền ra ngoài, trong khi arena được đóng khi không còn workers.

### InterruptedException khi đang chờ

Nếu thread coordinator bị interrupt trong `awaitTermination`, việc return ngay và close arena có thể khiến workers còn hoạt động dùng memory hết hiệu lực. Ví dụ dùng một chính sách minh họa: ghi nhận interruption, tiếp tục đợi mọi task kết thúc, rồi khôi phục interrupt flag. Production code có thể cần chính sách khác, nhưng phải đáp ứng điều kiện **không còn in-flight users trước close**, ngay cả khi có timeout/cancellation.

### Close thất bại hoặc custom cleanup lỗi

Đừng làm:

~~~java
try {
    arena.close();
} catch (IllegalStateException ignored) {
    // Sai: đánh dấu closed mà không biết close có thành công.
}
~~~

Đây là anti-pattern. `IllegalStateException` có thể biểu thị arena đã đóng hoặc close đang cạnh tranh với access; custom cleanup còn có thể ném `RuntimeException`. Một hệ thống cần phân biệt trạng thái, ngừng cấp lease mới, bảo toàn lỗi và có quy trình shutdown/recovery thích hợp. Không vòng lặp liên tục thử close cho tới khi “tình cờ hết lỗi”.

### Khi worker đang giữ lock dữ liệu

Đợi mọi worker xong cũng có thể bị deadlock nếu coordinator giữ một lock mà worker cần để hoàn tất, rồi coordinator gọi `Future.get` dưới lock ấy. Chính sách lock ordering rõ ràng rất quan trọng. Một shutdown tốt **không giữ lock ngăn worker finish trong lúc chờ Future**. Nếu dùng `ReentrantReadWriteLock`, write-lock close chỉ đợi khi readers có thể nhả lock độc lập.

### Không nhầm Arena.close và Cleaner/GC

`Arena.ofShared()` là arena đóng **thủ công**. Đừng nghĩ Java GC sẽ tự đóng arena đúng thời điểm nếu quên `close()`. Với shared native allocations, dùng `try-with-resources` hoặc owner lifecycle chính thức. `Arena.ofAuto()` có GC-managed cleanup nhưng không cho explicit close đúng hạn; `Arena.global()` không được deallocate qua arena. Chọn theo lifetime thực sự.

## 14. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ `ofShared` tự đồng bộ dữ liệu | Mất update, data race | Data locks/atomic hoặc phân vùng byte riêng |
| Cho mọi worker gọi `arena.close` khi xong | Close lặp lại, invalid các workers khác | Chỉ một owner/coordinator close |
| Thoát `try (Arena...)` ngay sau `submit` | Task chạy sau close | Chờ completion trước khi thoát |
| Gọi `shutdown()` rồi coi như pool đã dừng | Tasks đang chạy vẫn dùng memory | `awaitTermination`/Future join |
| Một `Future.get` ném rồi bỏ các tasks khác | Arena close khi worker khác còn dùng | `finally` đợi toàn bộ users |
| Dùng `isAlive()` thay lock | Race giữa check và use | Lease/lock giữ trong suốt operation |
| Close shared arena lần hai | `IllegalStateException` | Owner state bảo đảm chỉ close một lần |
| Nuốt `IllegalStateException` từ close | Nhầm trạng thái đã giải phóng | Xử lý lỗi, không tự đánh dấu CLOSED |
| Đóng arena khi downcall đang dùng segment | Close có thể thất bại | Phối hợp downcall completion |
| C lưu raw pointer sau downcall return | JVM không biết C còn dùng resource | Native completion/retain-release |
| Sử dụng `asSlice` rồi nghĩ slice sống độc lập | Access sau close bị từ chối | Slice chia sẻ scope |
| Dùng confined arena từ worker khác | `WrongThreadException` | Chọn shared arena nếu cần cross-thread |
| Dùng `Arena.global()` để khỏi đóng | Native memory không được thu hồi qua arena | Shared/confined với close đúng lúc |
| Dùng `Thread.sleep` để chờ worker | Race khó tái hiện | CountDownLatch/Future/Phaser/Executor termination |
| Gọi close reentrant khi đang giữ read lock | Có thể deadlock nâng read→write | Cấm/rework callback và deferred close |
| Tưởng close == atomic transaction | Thao tác nhiều bước có thể bị cắt ngang nếu protocol sai | Giữ lease qua toàn bộ operation |
| Coi memory segment Java là raw C pointer vô hạn | Pointer hết lifetime | Không leak pointer hoặc xác nhận native lifetime |

## 15. Kiểm thử và quan sát

Một bộ test nên kiểm tra:

1. **Cross-thread read/write khi OPEN:** dùng `ofShared`, worker đọc/ghi vùng hợp lệ; không gặp `WrongThreadException`.
2. **Confined contrast:** cùng kiểu access từ worker không phải owner với `Arena.ofConfined()` phải bị từ chối.
3. **Partitioned writes:** N workers ghi các index không chồng lấn, main join rồi nhận kết quả đúng.
4. **Same-slot race:** nếu cố tình làm increment bằng get+set ở nhiều workers, không giả định kết quả đúng; test phiên bản khóa/atomic.
5. **Scope after close:** `isAlive()==false` và một access sau close ném `IllegalStateException`.
6. **Close lần hai:** trên arena gốc ném `IllegalStateException`.
7. **Wrapper idempotency:** `close` wrapper nhiều lần không gọi `arena.close` lại.
8. **Failed task path:** một Future ném, các tasks khác vẫn được join trước close.
9. **Close-vs-operation:** một lượt sử dụng giữ lease; close phải chờ hoặc bị trì hoãn theo thiết kế.
10. **Async native pointer:** callback/ack bảo đảm native consumer đã dừng mới cho close.
11. **Cancellation:** interrupt/timeout không khiến coordinator giải phóng memory khi worker chưa xong.
12. **Nhiều segments cùng arena:** close làm invalid mọi segments và slices.
13. **Lỗi close:** policy không đánh dấu CLOSED khi không có bằng chứng close hoàn tất.

### Tránh test race dựa vào sleep

Một thử nghiệm `Thread.sleep(10)` rồi hy vọng close xảy ra đúng giữa hai dòng code là không tất định. Dùng `CountDownLatch`, `CyclicBarrier` hoặc `Phaser` để điều phối giai đoạn; song điều cần chứng minh là **giao thức không cho close trong lúc còn người dùng**, không phải cố đoán kết quả một lịch scheduler.

Nếu có JNI/FFM downcalls tới C, dùng thêm native memory sanitizer, leak tracking và log ownership. `MemorySegment` hỗ trợ temporal bounds nhưng không tự bảo vệ việc một thư viện C khác dereference pointer ngoài phạm vi FFM.

## 16. Lựa chọn giải pháp theo nhu cầu

| Bối cảnh | Lựa chọn hợp lý |
|---|---|
| Một thread xử lý native buffer trong `try` ngắn | `Arena.ofConfined()` |
| Nhiều threads cùng dùng một native buffer, cần đóng đúng hạn | `Arena.ofShared()` + join/lease |
| Nhiều read methods; close phải đợi readers | Lifecycle read-write lock |
| Ghi chung cùng dữ liệu | Data lock/VarHandle phù hợp, ngoài lifecycle lock |
| Tasks độc lập, chỉ ghi các offset không chồng lấn | Shared arena + index partition + Future join |
| Bộ nhớ được dùng tới hết process | `Arena.global()` khi thật sự cần lifetime vô hạn |
| Cleanup có thể chờ GC, không phải resource gấp | `Arena.ofAuto()` khi chấp nhận không xác định thời điểm |
| Native SDK giữ pointer qua async call | Native ownership/retain-release/ack completion; shared arena một mình chưa đủ |
| Task có lifetime khác nhau | Nhiều arenas theo nhóm/lifecycle, tránh đóng chéo |

Không chọn `ofShared` chỉ vì nghe “nhiều luồng thì nhanh”. Cấu trúc dữ liệu Java trên heap có thể phù hợp hơn nếu không cần native memory. Off-heap có chi phí cấp phát, memory pressure và quản lý lifetime; nên đo benchmark theo workload thực sự.

## 17. Câu hỏi tự luyện và đáp án

**1. Khác biệt chính giữa `ofConfined` và `ofShared`?** Confined chỉ cho owner thread dùng/đóng; shared cho phép các threads khác dùng và đóng, nhưng đòi phối hợp lifecycle.

**2. Shared arena có tự ngăn hai threads cùng ghi một int không?** Không. Nếu hai threads cùng sửa một slot, cần data lock, atomic/VarHandle hoặc thiết kế tránh writer cạnh tranh.

**3. `Arena.close()` trên shared arena luôn đợi FFM downcall xong?** Không. Đặc tả Java SE 22 cho phép `IllegalStateException` nếu một segment thuộc arena đang được truy cập đồng thời, ví dụ downcall.

**4. Đóng hai lần có vô hại không?** Không với `Arena.close()`; lần hai ném `IllegalStateException`. Wrapper có thể tự bảo đảm close idempotent bằng state/lock.

**5. `segment.scope().isAlive()` là true, có chắc thao tác tiếp theo hợp lệ?** Không; thread khác có thể đóng arena giữa check và use.

**6. Sau `shutdown()` đã được phép close chưa?** Chưa chắc. Shutdown không đợi task đang chạy; phải join/await termination hoặc có protocol tương đương.

**7. Một worker Future ném exception, có thể bỏ qua các Futures còn lại không?** Không nếu chúng dùng cùng arena. Đường cleanup phải đợi các users khác dừng trước khi close.

**8. Tại sao ví dụ 4-worker có stdout ổn định dù lịch thread không ổn định?** Mỗi worker ghi một index riêng, main chỉ đọc sau completion/termination và in theo thứ tự index.

**9. Một slice có giữ native allocation sống sau close không?** Không. Slice dùng chung scope và backing memory với segment gốc.

**10. `Arena.ofAuto()` có thay `ofShared()` để đóng đúng hạn không?** Không. Auto arena không hỗ trợ close tường minh; thời điểm cleanup do GC quyết định.

**11. C giữ pointer và dùng sau khi Java Future complete, có an toàn để close arena không?** Không nếu Future chỉ báo việc submit đã xong. Cần native completion/lease xác nhận pointer không còn được dùng.

**12. Khóa `ReentrantReadWriteLock` trong `SharedInts` bảo vệ điều gì?** Giữ các method dùng segment không chồng lên close; write lock còn tuần tự hóa writes. Nó chỉ bảo vệ callers đi qua wrapper, không bảo vệ users bypass lock.

## 18. Checklist code review

1. Đã sử dụng **JDK 22+** và FFM API chuẩn?
2. Có nhu cầu chia sẻ cross-thread thật sự, hay `ofConfined` đủ?
3. Ai sở hữu arena? Bao nhiêu nơi có thể gọi close?
4. Khi bắt đầu shutdown, có ngăn tasks mới acquire segment?
5. Có thống kê và chờ mọi active leases/tasks/native consumers không?
6. Nếu một Future fail, tasks còn lại được join trước close?
7. Sau interruption/timeout, có chứng minh users đã thật sự dừng?
8. `close()` được gọi một lần và chỉ đánh dấu CLOSED khi thành công?
9. `scope().isAlive()` có bị dùng thay cho lock/lease không?
10. Có methods nào trả segment thô cho bên ngoài rồi không kiểm soát lifetime?
11. Có callback gọi close reentrant từ operation đang giữ lock không?
12. Dữ liệu có bị nhiều threads ghi cùng offset? Có synchronization/atomic hợp lệ?
13. Có segments, slices hoặc mapped regions khác cùng scope vẫn đang được dùng?
14. Native downcall có giữ pointer sau khi trả về? Ai xác nhận completion?
15. Có test after-close, double-close, concurrent tasks và failed close?
16. Có giám sát native memory leaks, task completion và deadlock trong shutdown?

## Tài liệu tham chiếu

- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): shared/confined/auto/global, quy tắc đóng và `IllegalStateException` khi có concurrent access.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): kiểm tra bounds, scope, access và thread confinement.
- [Oracle Java SE 22 — MemorySegment.Scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html): `isAlive` và lifetime của segments.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): size, alignment và layouts.
- [Oracle Java SE 22 — ExecutorService](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `awaitTermination` và task lifecycle.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM trở thành API chuẩn từ Java 22.

## Ghi nhớ

**`Arena.ofShared()` cho phép nhiều luồng dùng native memory, nhưng việc đóng phải do một coordinator kiểm soát.** Shared không tự biến dữ liệu thành thread-safe và `close()` không được coi là phép đợi workers kết thúc.

Luồng đúng:

1. Tạo một shared arena với owner rõ ràng.
2. Chỉ phát quyền dùng (lease) khi arena còn OPEN.
3. Đồng bộ riêng dữ liệu đọc/ghi nếu nhiều threads chia sẻ cùng bytes.
4. Ngừng cấp công việc mới; chờ mọi workers/downcalls/native pointers hết sử dụng.
5. Gọi `arena.close()` **một lần**, chỉ coi CLOSED sau khi close thành công.
6. Không sử dụng bất kỳ segment hay slice nào thuộc scope đã đóng.

Nếu nhớ một điều: **shared là quyền truy cập qua nhiều threads; an toàn khi đóng là một giao thức vòng đời phải được thiết kế riêng**.
