# Arena.global và bộ nhớ có thời gian sống không giới hạn

## 1. Bài toán: bộ nhớ native tồn tại trong bao lâu?

Trong **Foreign Function & Memory API (FFM)** của Java, `MemorySegment` biểu diễn một vùng bộ nhớ (có thể nằm ngoài Java heap), còn `Arena` là cơ chế cấp phát và xác định **vòng đời** của các vùng bộ nhớ native được cấp phát qua nó. Khi làm việc với native libraries, việc chọn sai arena có thể tạo ra hai kiểu lỗi đối nghịch:

- **Giải phóng quá sớm:** native code còn đang giữ con trỏ tới dữ liệu nhưng `Arena` đã bị đóng. Các truy cập Java vào segment sẽ bị kiểm tra vòng đời; native C code giữ con trỏ cũ có thể dùng vùng nhớ không hợp lệ.
- **Giữ bộ nhớ quá lâu:** mỗi request tạo native buffer nhưng không có cách thu hồi cho tới khi tiến trình kết thúc, gây tăng bộ nhớ ngoài heap dù Java objects hoặc biến Java đã không còn được tham chiếu.

`Arena.global()` nằm ở cực thứ hai: nó cung cấp một **global arena với vòng đời không giới hạn** (*unbounded lifetime*). Các vùng native memory do arena này cấp phát **không được arena thu hồi trong suốt thời gian hoạt động của JVM**, và các `MemorySegment` tương ứng được phép truy cập từ **bất kỳ Java thread nào**.

Vì vậy cần hiểu chính xác câu “bộ nhớ có thời gian sống không giới hạn”: đó là **hợp đồng vòng đời của arena scope**, không có nghĩa có nguồn RAM vô hạn, không có lỗi cấp phát, không có ràng buộc truy cập và cũng **không tự bảo đảm thread safety cho dữ liệu đang được đọc/ghi**.

Bài này sử dụng API **FFM chính thức của JDK 22+ (JEP 454)** để minh họa `Arena.global()`. Trong **JDK 21 (JEP 442)**, FFM vẫn là preview và cần `--enable-preview`; một số overload cấp phát có tên khác, nên không copy nguyên ví dụ JDK 22 sang JDK 21.

## 2. Bốn loại Arena và vị trí của Arena.global

FFM có bốn kiểu arena quan trọng. Chúng khác nhau theo **thời gian sống**, **ai giải phóng**, **khả năng close** và **quyền truy cập giữa các thread**.

| Arena | Thời gian sống native memory | Có thể `close()`? | Thread được truy cập segment | Cơ chế thu hồi |
|---|---|---|---|---|
| `Arena.ofConfined()` | Hữu hạn, do lập trình viên quyết định | **Có**, từ thread sở hữu | Chỉ owner thread | Giải phóng khi arena được đóng thành công |
| `Arena.ofShared()` | Hữu hạn, do lập trình viên quyết định | **Có**, từ thread phù hợp | Nhiều thread | Giải phóng khi arena được đóng thành công |
| `Arena.ofAuto()` | Hữu hạn nhưng thời điểm thu hồi không xác định | **Không** | Nhiều thread | JVM/GC quản lý, khi arena cùng các segments không còn reachable |
| **`Arena.global()`** | **Không giới hạn** | **Không** | **Nhiều thread** | **Không được arena thu hồi** trong vòng đời tiến trình JVM |

Hai tiêu chí cần tách riêng:

1. **Lifetime:** vùng nhớ có tự động hết hiệu lực không? Có thể yêu cầu thu hồi bằng `close()` không?
2. **Thread access:** segment có thuộc về một thread cụ thể hay có thể truy cập từ nhiều thread?

`Arena.global()` vừa có **unbounded lifetime** vừa **thread-unrestricted**. `Arena.ofAuto()` cũng cho nhiều thread truy cập nhưng **không** có thời gian sống vô hạn: native memory của nó sẽ đủ điều kiện được JVM thu hồi sau khi không còn reachable và GC quyết định dọn.

**Không nên dùng `global` chỉ vì ứng dụng đa luồng.** Khi cần dùng chung dữ liệu giữa các thread **nhưng vẫn cần giải phóng ở một thời điểm rõ ràng**, `Arena.ofShared()` thường là lựa chọn tốt hơn.

### 2.1. Hình dung bằng sơ đồ vòng đời

~~~text
Thời gian của tiến trình JVM ----------------------------------------->

Arena.ofConfined():
    tạo arena -> allocate -> dùng (owner thread) -> close -> memory freed
                                                        ^
                                                segment không còn hợp lệ

Arena.ofShared():
    tạo arena -> allocate -> dùng ở nhiều threads -> close -> memory freed
                                                  (cần phối hợp các threads)

Arena.ofAuto():
    tạo arena -> allocate -> còn reachable -> không còn reachable
                                         -> GC quyết định thu hồi (không chắc lúc nào)

Arena.global():
    Arena.global() -> allocate ---------------------------> ...
                     vùng nhớ luôn thuộc global scope, không có close/free bởi arena
                     bộ nhớ được hệ điều hành thu hồi khi tiến trình kết thúc
~~~

Sơ đồ là **mô hình khái niệm**, không phải cam kết rằng GC sẽ thu hồi `ofAuto` đúng lúc một Java variable bị gán `null`. Với `global`, ngay cả khi wrapper Java không còn được tham chiếu, native allocation vẫn không được giải phóng theo cơ chế arena.

## 3. API Arena.global và ý nghĩa của global scope

Trong Java SE 22, API có factory method:

~~~java
Arena global = Arena.global();
~~~

Đây là **trích đoạn**, phải có `import java.lang.foreign.Arena;` khi dùng trong một class thực. Tài liệu Java mô tả global arena như arena có **global scope** và **unbounded lifetime**.

Ba thuộc tính cốt lõi:

- **`global.scope().isAlive()` luôn biểu thị scope còn sống**: global arena không có sự kiện đóng hợp lệ làm invalid scope.
- **Các segments do `global.allocate(...)` trả về gắn với global scope**: vùng native memory backing chúng **không được arena tự deallocate**.
- **Segments dùng được trên nhiều Java threads** theo quy tắc kiểm tra truy cập của FFM: không có owner-thread restriction như confined arena.

### 3.1. Cấp phát thông qua global arena

Ví dụ JDK 22:

~~~java
MemorySegment bytes = Arena.global().allocate(64);
MemorySegment ints = Arena.global().allocateFrom(
        ValueLayout.JAVA_INT, 10, 20, 30
);
~~~

Đây là **trích đoạn**, chưa phải chương trình độc lập; `MemorySegment` và `ValueLayout` phải được import. Tùy overload, `allocate` nhận số byte hoặc `MemoryLayout`, còn `allocateFrom` tạo vùng mới và **chép dữ liệu Java ban đầu** sang vùng đó.

Đặc tả `Arena.global()` quy định các segments được nó cấp phát là **zero-initialized**. Nếu chưa ghi giá trị khác, đọc một vị trí hợp lệ với layout thích hợp sẽ nhận giá trị tương ứng với các byte bằng 0. Tuy nhiên, **zero-initialized không đồng nghĩa mọi cách diễn giải bit pattern đều có nghĩa nghiệp vụ hợp lệ**: một struct hay pointer C có quy tắc riêng.

### 3.2. Từ khóa “global” không phải Java biến global

Có hai ý khác nhau:

~~~java
// Đây là biến local CỦA JAVA đang tham chiếu một segment có global scope.
MemorySegment data = Arena.global().allocate(128);
~~~

- Biến Java `data` có thể chỉ sống trong một phương thức. Khi nó ra khỏi phạm vi hoặc không còn reachable, **wrapper Java** có thể được GC xử lý.
- **Backing off-heap memory** cấp phát bởi `Arena.global()` vẫn **không được arena giải phóng**. Việc Java reference biến mất không biến global allocation thành automatic allocation.
- Khai báo `static MemorySegment data` cũng không phải điều kiện tạo global scope: bạn có thể có `static` field giữ segment từ `Arena.ofShared()`; arena đó vẫn close được. **Scope do arena quy định, không do từ khóa Java `static` quyết định.**

Đây là khác biệt nền tảng giữa **object reachability trong Java heap** và **lifetime của bộ nhớ native**.

## 4. Ví dụ Java 22 hoàn chỉnh: global segment sống lâu, đọc được từ thread khác và không close được

Tạo tệp **`GlobalArenaDemo.java`** với mã dưới đây. Chương trình chỉ dùng phần *foreign memory* của FFM, **không gọi hàm native C**, nên không cần compiler C hay cờ quyền native access.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class GlobalArenaDemo {
    public static void main(String[] args) throws InterruptedException {
        Arena global = Arena.global();

        // Cấp phát và chép ba số int từ Java vào native memory.
        MemorySegment values = global.allocateFrom(
                ValueLayout.JAVA_INT, 10, 20, 30
        );

        // Cấp phát một vùng int chưa được gán dữ liệu nguồn.
        // Vùng nhớ do Arena cấp phát được zero-initialized.
        MemorySegment zero = global.allocate(ValueLayout.JAVA_INT);

        System.out.println("bytes = " + values.byteSize());
        System.out.println("alive = " + values.scope().isAlive());
        System.out.println("zero = " + zero.get(ValueLayout.JAVA_INT, 0));
        System.out.println("main = " + values.getAtIndex(
                ValueLayout.JAVA_INT, 0
        ));

        // Worker chỉ ĐỌC trong khi main chờ join: không có ghi đồng thời.
        Thread reader = new Thread(() -> {
            int number = values.getAtIndex(ValueLayout.JAVA_INT, 1);
            System.out.println("other thread = " + number);
        });
        reader.start();
        reader.join();

        try {
            global.close();
        } catch (UnsupportedOperationException ex) {
            System.out.println("close = unsupported");
        }

        // Một lần cố close thất bại không làm scope hết hiệu lực.
        System.out.println("alive after close = "
                + values.scope().isAlive());

        values.setAtIndex(ValueLayout.JAVA_INT, 2, 99);
        System.out.println("last = " + values.getAtIndex(
                ValueLayout.JAVA_INT, 2
        ));
    }
}
~~~

### 4.1. Biên dịch và chạy

Yêu cầu **JDK 22 trở lên** có FFM final. Với JDK 22:

~~~bash
java -version
javac -version
javac --release 22 GlobalArenaDemo.java
java GlobalArenaDemo
~~~

Trong PowerShell, Command Prompt, bash và zsh, các lệnh `javac`/`java` trên đều có dạng tương tự nếu chúng đã có trong `PATH`. **Không thêm `--enable-preview`** chỉ để chạy FFM trên JDK 22. Trong ví dụ này, không có `Linker.downcallHandle` hoặc `SymbolLookup.libraryLookup`, nên cũng **không cần `--enable-native-access`** cho việc allocate/get/set thông thường.

**Stdout chính xác của chương trình:**

~~~text
bytes = 12
alive = true
zero = 0
main = 10
other thread = 20
close = unsupported
alive after close = true
last = 99
~~~

Lý do đầu ra có thứ tự ổn định: main in bốn dòng đầu, sau đó chờ `reader.join()` hoàn thành, rồi mới thử `close()` và ghi giá trị cuối. Thread kia **chỉ đọc**; chương trình không cố diễn giải các hành vi khi read/write đồng thời mà không đồng bộ.

### 4.2. Giải thích từng phần

- `allocateFrom(JAVA_INT, 10, 20, 30)` tạo ba phần tử `int` 32-bit liên tiếp; độ dài segment là **3 × 4 = 12 byte**.
- `allocate(JAVA_INT)` cấp đủ bộ nhớ cho một `int` và đảm bảo vùng mới được zero-initialized, nên đọc bằng `get(JAVA_INT, 0)` trả 0.
- `values.scope().isAlive()` trả `true` vì scope của `Arena.global()` không có vòng đời kết thúc.
- Một thread khác đọc giá trị `20` hợp lệ về **quyền truy cập scope**; không có `WrongThreadException` chỉ vì thread khác truy cập global segment.
- `global.close()` ném **`UnsupportedOperationException`** theo đặc tả; chương trình bắt ngoại lệ đó và in `close = unsupported`.
- Sau lỗi close, scope vẫn `alive`, và việc ghi phần tử thứ ba thành `99` là hợp lệ trong giới hạn segment.

**Điều không được suy ra từ stdout:** chương trình **không chứng minh các allocations sẽ được giải phóng khi biến `values`/`zero` ra khỏi phạm vi**. Đặc tả nói điều ngược lại đối với bộ nhớ backing do global arena cấp phát: chúng không được deallocate thông qua arena. Khi tiến trình kết thúc, hệ điều hành thường thu hồi các tài nguyên của tiến trình; đó **không phải** một lệnh `Arena.close()` hoặc một lần dọn GC theo chương trình.

## 5. Vì sao không thể close Arena.global?

`Arena` kế thừa `AutoCloseable`, nhưng **không phải arena nào cũng hỗ trợ close**. Với global arena, Java SE 22 quy định:

~~~java
Arena global = Arena.global();
global.close(); // Ném UnsupportedOperationException.
~~~

Đây là trích đoạn **có chủ ý ném lỗi**, không phải ví dụ sử dụng tài nguyên đúng. Không viết:

~~~java
// SAI: try-with-resources sẽ gọi close() và gây exception.
try (Arena global = Arena.global()) {
    MemorySegment data = global.allocate(64);
}
~~~

Đây là ví dụ **SAI, không dùng làm hướng dẫn chạy**. Cuối `try`, Java tự gọi `global.close()` và nhận `UnsupportedOperationException`. Một số mã có thể hoạt động tới cuối block rồi mới lỗi, nên nguyên nhân dễ bị hiểu nhầm.

**Cách đúng** khi cố ý muốn unbounded lifetime:

~~~java
Arena global = Arena.global();
MemorySegment data = global.allocate(64);
// Không gọi global.close() và không đặt global vào try-with-resources.
~~~

Nếu yêu cầu của ứng dụng là “cấp phát rồi chắc chắn trả lại bộ nhớ khi hoàn thành”, đừng cố tìm cách ép global arena đóng. **Chọn arena khác ngay từ đầu**: `ofConfined` hoặc `ofShared` tùy nhu cầu thread.

### 5.1. Vì sao Global và Auto đều không close nhưng rất khác nhau?

`Arena.ofAuto()` cũng ném `UnsupportedOperationException` nếu gọi `close()`. Tuy nhiên:

- **Auto:** backing native memory *có thể được deallocate* khi runtime/GC xác định arena và các segment đã không còn reachable. **Không có thời điểm thu hồi xác định**.
- **Global:** backing native memory do `global` cấp phát **không bao giờ được arena deallocate**; việc Java references biến mất không khiến vùng nhớ trở thành automatic allocation.

Vì thế, “không có close” **không đồng nghĩa** “sống vô hạn”. Phải xem chính xác loại arena.

## 6. Java GC và native memory: hai đời sống song song

Cần phân biệt hai loại tài nguyên:

| Thành phần | JVM/GC có thể quản lý gì? | Kết luận |
|---|---|---|
| Biến Java kiểu `MemorySegment` | Đối tượng wrapper có thể không còn reachable và được GC xử lý | Không quyết định backing global allocation sẽ được trả |
| Native backing memory của `Arena.global().allocate(...)` | Theo đặc tả global arena, **không được deallocate** trong đời sống tiến trình | Hủy Java wrapper không giải phóng native bytes |
| Native backing memory của `Arena.ofAuto()` | GC có thể kích hoạt deallocation sau khi không còn reachable | Không có thời điểm xác định |
| Native backing memory của `Arena.ofConfined()/ofShared()` | Giải phóng qua `close()` thành công | Có thể kiểm soát một cách xác định |
| Memory từ C `malloc` | Chịu quy tắc ownership/release của native library | Không thể coi là global-arena allocation chỉ vì có một Java pointer tới nó |

Một ngộ nhận rất nguy hiểm: “Tôi chỉ cần đặt `segment = null`, khi GC chạy global arena sẽ giải phóng off-heap memory”. Điều này **sai**. `Arena.global` không được thiết kế với cơ chế reclamation của `ofAuto`.

### 6.1. Lỗi tăng bộ nhớ dù heap chart ổn định

Giả sử một service nhận request:

~~~java
// Ví dụ SAI về quản lý vòng đời: không chạy trong service thực.
public static void handleRequest() {
    MemorySegment temp = Arena.global().allocate(1024 * 1024);
    // Xử lý request...
}
~~~

Mỗi lần gọi có thể giữ lại khoảng **1 MiB native backing memory** cho phần đời còn lại của tiến trình JVM. Nếu gọi 1.000 lần, tổng kích thước được yêu cầu là khoảng **1.000 MiB**, dù biến Java `temp` đã hết scope sau mỗi lời gọi. **Đừng chạy vòng lặp cấp phát lớn chỉ để “xem memory leak”**; thử nghiệm kiểu đó có thể làm tiến trình hết bộ nhớ native.

Heap profiler chỉ đo Java heap có thể không phản ánh trực tiếp lượng bộ nhớ native này. Khi điều tra, hãy xem thêm memory usage ở cấp tiến trình, native memory metrics và log lỗi phù hợp. Không suy ra mọi native memory tăng đều do `Arena.global`; thư viện C, direct buffers, JVM subsystems và mapped files cũng tiêu thụ tài nguyên native.

### 6.2. Trách nhiệm bộ nhớ không biến mất ở ranh giới FFM

Nếu C library cấp phát vùng nhớ bằng `malloc` hoặc allocator riêng, nó thường có hàm release tương ứng. Ngay cả khi Java nhận được địa chỉ đó dưới dạng một `MemorySegment` có global scope, **không thể kết luận FFM sở hữu vùng nhớ ấy** hoặc rằng vùng nhớ không bao giờ bị C code free.

Tương tự, không bao giờ gọi C `free` trực tiếp lên một địa chỉ được cấp bởi `Arena.global().allocate(...)` để “giải phóng thủ công” nếu không có hợp đồng API cho phép. Làm thế có thể dẫn tới **use-after-free**, free sai allocator hoặc trạng thái JVM không nhất quán. Arena API không cung cấp thao tác deallocate riêng cho từng global allocation.

**Global scope nói về ranh giới kiểm tra của Java segment; quyền sở hữu (ownership) của bộ nhớ phải theo nguồn cấp phát và hợp đồng native library.**

## 7. Cho phép truy cập đa luồng không có nghĩa dữ liệu tự động thread-safe

Java SE 22 đảm bảo các segments cấp bởi `Arena.global()` **có thể được truy cập từ bất kỳ thread nào**. Nghĩa là:

- Không áp dụng ràng buộc “chỉ owner thread” như `Arena.ofConfined()`.
- Không có hoạt động `close` hợp lệ có thể invalid toàn bộ global scope giữa các thread.
- **Nhưng** hai thread ghi/đọc cùng một vị trí bộ nhớ không được đồng bộ vẫn có thể tạo **data race** và vi phạm tính đúng đắn của ứng dụng.

Phân biệt:

~~~text
Allowed by scope:
    Thread A đọc index 0
    Thread B đọc index 1
    -> có thể thực hiện trên global segment, không bị chặn do owner thread

NOT automatically synchronized:
    Thread A ghi index 0
    Thread B ghi index 0 cùng lúc
    -> không có đảm bảo thứ tự/hợp tác dữ liệu chỉ vì arena là global
~~~

Ngay cả khi một segment luôn alive và đủ byte, vẫn cần xác định **memory consistency** của những truy cập vào cùng vùng nhớ. Có thể dùng Java synchronization phù hợp, `VarHandle` với access modes thích hợp khi đảm bảo alignment, hoặc thiết kế dữ liệu immutable/read-only sau bước khởi tạo được công bố an toàn.

### 7.1. Mẫu chia sẻ an toàn khi chỉ đọc

Trong ví dụ `GlobalArenaDemo`, luồng main khởi tạo mọi giá trị **trước khi** gọi `reader.start()`, worker chỉ đọc, và main đợi bằng `reader.join()`. Không có read/write cạnh tranh trên cùng vị trí.

Điểm quan trọng: chương trình dùng `Arena.global()` để **cho phép** truy cập cross-thread, nhưng còn dựa vào **thứ tự start/join và không ghi đồng thời** để giữ đúng ý nghĩa dữ liệu.

Nếu ứng dụng có nhiều worker cập nhật cùng vùng native, cần một thiết kế đồng bộ cụ thể. Chỉ đổi từ `Arena.ofConfined()` sang `Arena.global()` sẽ không tự giải quyết vấn đề đua dữ liệu.

### 7.2. Global không giới hạn kích thước hay alignment

FFM vẫn thực hiện kiểm tra không gian:

~~~java
MemorySegment s = Arena.global().allocate(8);
s.get(ValueLayout.JAVA_INT, 8); // Lỗi: cần 4 byte bắt đầu tại offset 8.
~~~

Đây là **trích đoạn cố ý gây lỗi**, không phải code chạy hợp lệ. Segment có byte offsets hợp lệ từ 0 tới 7, còn đọc `int` tại offset 8 cần truy cập từ 8 tới 11, vượt phạm vi. Kết quả là **`IndexOutOfBoundsException`**.

Các layout còn có **yêu cầu alignment**; một địa chỉ đủ byte nhưng không thẳng hàng theo layout vẫn không hợp lệ cho thao tác yêu cầu alignment. `Arena.global()` không bỏ các kiểm tra này.

## 8. So sánh bằng chương trình thứ hai: closed confined arena khác global arena thế nào?

Tạo file **`ArenaLifetimeComparison.java`** để nhìn thấy đoạn memory sống ngắn bị invalid, trong khi global vẫn alive. Chương trình này cũng dùng **JDK 22+**, không cần native C library.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaLifetimeComparison {
    public static void main(String[] args) {
        MemorySegment local;

        try (Arena confined = Arena.ofConfined()) {
            local = confined.allocateFrom(ValueLayout.JAVA_INT, 7);
            System.out.println("confined inside = "
                    + local.get(ValueLayout.JAVA_INT, 0));
        }

        try {
            local.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("confined should be closed");
        } catch (IllegalStateException ex) {
            System.out.println("confined after close = invalid");
        }

        MemorySegment global = Arena.global().allocateFrom(
                ValueLayout.JAVA_INT, 7
        );
        System.out.println("global value = "
                + global.get(ValueLayout.JAVA_INT, 0));
        System.out.println("global alive = "
                + global.scope().isAlive());
    }
}
~~~

Chạy:

~~~bash
javac --release 22 ArenaLifetimeComparison.java
java ArenaLifetimeComparison
~~~

**Stdout chính xác:**

~~~text
confined inside = 7
confined after close = invalid
global value = 7
global alive = true
~~~

Tại sao:

1. Trong `try (Arena confined = Arena.ofConfined())`, segment `local` đang alive và đọc được số 7.
2. Ra khỏi block, `confined.close()` được gọi tự động, vùng native memory được giải phóng và segment `local` bị invalid.
3. Cố đọc `local` sau close ném `IllegalStateException`, chương trình catch để in dòng thứ hai.
4. Segment cấp bằng `Arena.global()` không phụ thuộc vào phạm vi confined; vẫn đọc được số 7 và có scope alive.

So sánh này chứng minh **khác biệt lifetime** chứ không phải phép đo lượng bộ nhớ mà hệ điều hành đã giải phóng. Đừng truy cập con trỏ thô từ C sau khi arena của nó đã close để “kiểm tra” lỗi: native use-after-free có thể làm JVM crash thay vì ném một exception Java gọn gàng.

## 9. Khi nào Arena.global là lựa chọn hợp lý?

`Arena.global()` **không phải API sai**; nó có vai trò rõ ràng khi *chủ đích thiết kế* yêu cầu vùng native memory tồn tại tới cuối vòng đời JVM.

Một số tình huống có thể phù hợp, với điều kiện kích thước nhỏ và được kiểm soát:

- **Dữ liệu immutable dùng chung lâu dài**: ví dụ một bảng cấu hình native có kích thước rất nhỏ, khởi tạo một lần và sử dụng liên tục đến khi tiến trình kết thúc.
- **Pointer/callback cần sống xuyên suốt chương trình**: trong một số thiết kế FFM upcall, stub/địa chỉ callback được giữ bằng scope phù hợp; nếu thật sự phải sống bằng tiến trình và số lượng được giới hạn chặt, global arena có thể có ý nghĩa. Việc native code lưu và gọi callback còn đòi hỏi ABI, thread và loader lifecycle đúng.
- **Các cấu trúc process-lifetime**: native library được nạp một lần và giữ cấu trúc cố định, không có yêu cầu tháo gỡ/khởi tạo lại trong cùng JVM.

Dù vậy, luôn ghi rõ trong thiết kế: **ai quyết định cấp phát, cấp phát tối đa bao nhiêu lần, kích thước tổng có giới hạn nào và vì sao chấp nhận không thu hồi**. “Dữ liệu được dùng ở nhiều thread” **chưa đủ** làm lý do chọn global; `ofShared()` cũng hỗ trợ nhiều thread và **có thể close**.

### 9.1. Trường hợp không nên dùng global

| Nhu cầu | Arena thường phù hợp hơn | Lý do |
|---|---|---|
| Một lần gọi native, xong thì hết dữ liệu | `Arena.ofConfined()` | Cleanup xác định ngay sau lời gọi |
| Một batch chạy trong một thread | `Arena.ofConfined()` | Chủ sở hữu đơn giản, hạn chế lỗi vòng đời |
| Nhiều worker chia sẻ buffer, sau đó kết thúc batch | `Arena.ofShared()` | Cross-thread access và close khi kết thúc |
| Bộ nhớ có thể tự dọn khi không còn được tham chiếu, chấp nhận độ trễ | `Arena.ofAuto()` | GC có thể thu hồi native backing memory |
| Cache có thể xóa hoặc kích thước thay đổi theo traffic | `ofShared()`/`ofConfined()` theo owner rõ ràng | Tránh giữ mọi lần cấp phát tới cuối JVM |
| Request, message, query hoặc transaction tạm thời | `Arena.ofConfined()` hoặc shared có scope đúng | Request-scoped memory phải có biên deallocation |

Đây là định hướng; lựa chọn còn phụ thuộc ownership, concurrency và hành vi native library. Một arena có thể chứa **nhiều allocations** để dọn theo nhóm khi kết thúc phạm vi.

## 10. Thiết kế thay thế: vùng nhớ dùng chung nhưng được giải phóng

Nếu mục tiêu thực sự là “nhiều thread dùng chung một buffer, nhưng sau khi hoàn tất phải giải phóng”, dùng **`Arena.ofShared()`** với quy trình đóng tài nguyên rõ ràng.

Ví dụ **JDK 22 hoàn chỉnh** — tệp `SharedArenaDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SharedArenaDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena shared = Arena.ofShared()) {
            MemorySegment data = shared.allocateFrom(
                    ValueLayout.JAVA_INT, 3, 5, 7
            );

            Thread reader = new Thread(() -> {
                System.out.println("worker = " +
                        data.getAtIndex(ValueLayout.JAVA_INT, 1));
            });
            reader.start();
            reader.join();

            System.out.println("main = " +
                    data.getAtIndex(ValueLayout.JAVA_INT, 2));
        } // shared.close(): dọn vùng native khi không còn thread sử dụng.
        System.out.println("shared closed");
    }
}
~~~

Chạy:

~~~bash
javac --release 22 SharedArenaDemo.java
java SharedArenaDemo
~~~

**Stdout:**

~~~text
worker = 5
main = 7
shared closed
~~~

`reader.join()` đảm bảo worker đã đọc xong trước khi block kết thúc và arena được close. Như vậy các threads đều có thể sử dụng segment khi còn sống, **nhưng application vẫn có một thời điểm giải phóng xác định**.

**Đừng close shared arena khi thread khác đang dùng nó.** Các kiểm tra temporal safety và quy tắc close của FFM có thể báo lỗi nếu đóng khi hoạt động truy cập đang diễn ra; ngoài ra, native pointers giữ bởi C code còn đòi hỏi phối hợp riêng để không trở thành dangling pointers. `Arena.ofShared()` không tự đồng bộ dữ liệu và không tự chờ mọi native callback hoàn tất.

## 11. Những hiểu lầm quan trọng về global scope

### 11.1. “Unbounded lifetime” không phải unlimited memory capacity

Bạn có thể yêu cầu một allocation rất lớn, nhưng JVM/OS không có đủ native memory. Khi cấp phát thất bại, ứng dụng có thể nhận **`OutOfMemoryError`**. `Arena.global()` không cung cấp lượng RAM vô hạn hay khả năng tự co vùng nhớ khi không dùng nữa.

Tài nguyên native của tiến trình còn bị giới hạn bởi địa chỉ ảo, quota container, cấu hình hệ điều hành, dependency native và bộ nhớ thật. Thiết kế production phải **đặt ngân sách cho số bytes cấp phát** và không cấp phát mỗi request vào global arena vô hạn.

### 11.2. “Any thread may access” không phải “các thao tác là atomic”

Các `get` và `set` thông thường không vì nằm trong global arena mà trở thành atomic/volatile. Nếu cần counter dùng chung, hãy thiết kế synchronization hoặc `VarHandle` đúng layout và memory ordering.

Sự an toàn của **lifetime** và **races** là hai trục tách biệt:

~~~text
Arena.global() đảm bảo:
    Global scope luôn alive
    Segment có thể truy cập từ nhiều threads (không giới hạn owner)

Arena.global() KHÔNG đảm bảo:
    Ghi/đọc đồng thời có thứ tự mong muốn
    Tất cả field updates là atomic
    Native code tuân thủ đúng phạm vi segment
    C pointer từ thư viện ngoài luôn hợp lệ
    Memory luôn có đủ để cấp phát
~~~

### 11.3. “Global scope always alive” không có nghĩa pointer bên ngoài luôn hợp lệ

Một `MemorySegment` có scope không giới hạn có thể đại diện **địa chỉ do native library quản lý**, ví dụ một con trỏ nhận về từ C. Nếu library đã free vùng nhớ, việc Java có một wrapper với global scope **không làm vùng nhớ sống lại**.

FFM checks không thể tự biết toàn bộ ownership của malloc/free ở ngoài JVM. Không tự diễn giải hoặc mở rộng các địa chỉ lạ bằng `reinterpret` khi không biết kích thước, vòng đời và chủ sở hữu. Các thao tác nguy hiểm có thể là restricted và có nguy cơ memory corruption.

### 11.4. “Không close được” khác với “không cần quản lý”

Không có `close()` khiến trách nhiệm quản lý **lớn hơn**, không nhỏ đi: phải giới hạn số lượng allocations, chỉ tạo lúc khởi tạo nếu phù hợp và đánh giá khả năng tái sử dụng cấu trúc dữ liệu.

Nếu yêu cầu hot reload, redeploy, tái tạo resource trong cùng JVM hoặc giải phóng khi người dùng logout, global arena rất dễ không phù hợp. Cần một bounded arena (confined/shared) có ownership và lifecycle gắn với component.

### 11.5. Global arena không tự tạo một vùng memory dùng chung giữa các tiến trình

“Global” trong API này là **scope của JVM process**, không phải shared-memory segment giữa các tiến trình. Hai Java programs chạy ở hai JVM khác nhau không thể dùng chung địa chỉ được cấp qua `Arena.global()` chỉ vì cùng tên API.

Muốn IPC/shared memory giữa processes phải dùng cơ chế OS/native library riêng và quản lý synchronization cũng như quyền truy cập; API `Arena.global()` không tự cung cấp việc đó.

## 12. Các lỗi phổ biến và hướng xử lý

| Lỗi hoặc cách hiểu sai | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt `Arena.global()` vào try-with-resources | `close()` cuối block ném `UnsupportedOperationException` | Không đóng global; dùng confined/shared nếu muốn close |
| Nghĩ `segment = null` sẽ giải phóng native allocation global | Native memory vẫn được arena giữ suốt vòng đời JVM | Chọn `ofAuto` hoặc bounded arena |
| Cấp buffer toàn bộ requests bằng global | Memory footprint ngoài heap tăng dần | Dùng request-scoped arena, đặt memory budget |
| Chọn global chỉ để dùng nhiều thread | Dùng unbounded lifetime không cần thiết | Cân nhắc `Arena.ofShared()` có thể close |
| Cho hai threads ghi cùng offset không đồng bộ | Race, mất update hoặc dữ liệu không nhất quán | Synchronization, immutable data, VarHandle đúng semantics |
| Dùng `MemorySegment` sau close của confined/shared | `IllegalStateException` | Giới hạn truy cập trong arena lifetime |
| Đọc vượt `segment.byteSize()` | `IndexOutOfBoundsException` | Tính offset theo bytes và layout |
| Dùng alignment sai | `IllegalArgumentException`/lỗi alignment theo API | Cấp phát theo `MemoryLayout` và kiểm tra byte alignment |
| Gọi C `free` trực tiếp cho global allocation | Free sai allocator, nguy cơ use-after-free | Không tự free allocation do global arena quản lý |
| Gán global scope cho một C pointer đã bị free | Scope check không phát hiện ownership/liveness thực | Theo dõi chính xác hợp đồng native allocator |
| Nghĩ Java heap ổn định nghĩa native memory ổn định | Bỏ sót tăng memory ngoài heap | Theo dõi process/native memory riêng |
| Sao chép `allocateFrom` vào JDK 21 preview | API khác version, có thể không compile | Dùng JDK22+ cho ví dụ hoặc đổi theo API JDK21 |
| Dùng JDK 17 chạy class có `java.lang.foreign` final | FFM final chưa có ở Java17 | Chạy bằng JDK22+ |
| Dùng `--enable-native-access` cho mọi chương trình FFM không cần thiết | Cấu hình quá rộng quyền native | Chỉ cấp quyền khi sử dụng restricted APIs |

Trong bước kiểm tra lỗi, phân biệt vấn đề **lifetime** (arena closed), **spatial bounds** (offset/layout), **thread confinement** và **resource exhaustion**. Mỗi nhóm có hướng khắc phục khác nhau; chuyển tất cả sang `Arena.global()` để “cho chạy” thường che giấu thiết kế sai.

## 13. JDK 21 preview và JDK 22 final: lưu ý về cú pháp

`Arena.global()` đã xuất hiện trong FFM preview của **JDK 21**, nhưng toàn bộ `java.lang.foreign` ở phiên bản đó là **preview** (JEP 442). Với JDK21 phải biên dịch/chạy với cờ:

~~~bash
javac --enable-preview --release 21 MyFfm21Class.java
java --enable-preview MyFfm21Class
~~~

Hai lệnh là **khuôn mẫu**, không phải lệnh chạy file có sẵn trong bài; cần thay `MyFfm21Class` bằng tên tệp/class thực của dự án dùng đúng API preview JDK21.

JDK 22 finalized FFM (JEP 454), nên các chương trình `GlobalArenaDemo`, `ArenaLifetimeComparison`, `SharedArenaDemo` trong bài chạy mà không cần `--enable-preview`. Nhưng **đừng** kỳ vọng method `arena.allocateFrom(...)` có mặt trên JDK21 như ở JDK22. Ở JDK21 một số phương thức khởi tạo có tên như `allocateArray`, `allocateUtf8String`, `allocate(ValueLayout, value)`.

Đối với bài này, ngữ nghĩa **global arena có unbounded lifetime và không thể close** là điểm cốt lõi trong cả hai phiên bản. Sự khác nhau về trạng thái API và phương thức cấp phát không làm global trở thành “tự dọn” trên JDK nào.

**Cảnh báo về cờ native access:** những ví dụ chỉ cấp phát/đọc/ghi memory bằng FFM ở đây **không gọi restricted native downcall**. Khi chương trình thực tế dùng `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, upcall stub hoặc thao tác restricted khác, phải xem chính sách `--enable-native-access` tương ứng với JDK/runtime đó. “Final” không có nghĩa mọi foreign function call hoàn toàn không cần cấp quyền.

## 14. Checklist thiết kế khi định chọn Arena.global

Trước khi dùng global arena trong production, kiểm tra ít nhất:

1. **Lifetime:** dữ liệu có thực sự phải tồn tại đến khi JVM kết thúc? Nếu chỉ cần đến cuối request/batch, chọn bounded arena.
2. **Số lượng cấp phát:** có đảm bảo số allocations hữu hạn, không tỉ lệ vô hạn với traffic?
3. **Giới hạn bytes:** tổng memory process-lifetime tối đa được tính và theo dõi chưa?
4. **Ownership:** vùng native được cấp bởi FFM arena hay do C library cấp? Ai có quyền giải phóng?
5. **Cung cấp con trỏ cho native code:** con trỏ có bị C giữ lâu hơn thời gian dữ liệu hợp lệ không?
6. **Thread safety:** các threads cùng đọc hay cùng ghi? Có phương thức synchronization đúng với memory ordering không?
7. **Khả năng reload/teardown:** component có phải giải phóng trước khi JVM kết thúc? Nếu có, global không phù hợp.
8. **Điều kiện fail:** nếu cấp phát native memory thất bại, hệ thống có degrade/fail-fast thích hợp không?
9. **Boundary và alignment:** cách tính byteSize, offset, layout theo C ABI đã được kiểm tra chưa?
10. **Quan sát vận hành:** metric/native memory log nào có thể phát hiện tăng memory ngoài heap?
11. **Version:** JDK22+ dùng FFM final và `allocateFrom`; JDK21 preview dùng bộ API/cờ khác.
12. **Tài liệu nội bộ:** có ghi rõ lý do một allocation không bao giờ được trả trong suốt JVM lifetime không?

Nếu không trả lời được câu hỏi “**vì sao bộ nhớ này không cần được trả trước khi JVM kết thúc?**”, lựa chọn mặc định hợp lý thường là một arena có vòng đời **hữu hạn** thay vì `Arena.global()`.

## 15. Câu hỏi và bài tập

1. `Arena.global()` khác `Arena.ofAuto()` ở điều gì nếu cả hai đều không thể close?
2. `Arena.global().scope().isAlive()` trả gì sau một lần gọi `close()` thất bại? Vì sao?
3. Khi một Java method tạo `MemorySegment s = Arena.global().allocate(1024)` rồi kết thúc, native memory có được giải phóng vì biến `s` ra khỏi scope không?
4. Trường hợp nào nên dùng `Arena.ofShared()` thay cho global dù có nhiều worker threads?
5. Tại sao quyền truy cập global segment từ mọi thread không tự bảo đảm các thao tác `get`/`set` atomic?
6. `Arena.global().allocate(ValueLayout.JAVA_INT)` có giá trị byte ban đầu là gì và tại sao?
7. Vì sao `try (Arena a = Arena.global())` là một mẫu không phù hợp?
8. Nếu cần một buffer C chỉ trong một downcall, loại arena nào là lựa chọn đơn giản và dễ cleanup?
9. `MemorySegment.ofAddress` có global scope có làm cho một C pointer đã bị `free` trở nên an toàn không?
10. Một service cấp 1 MiB bằng global cho mỗi request. Sau 1.000 requests, vấn đề tài nguyên nào cần xem xét?
11. Khi nào một allocation process-lifetime nhỏ có thể là chủ đích hợp lý thay vì một lỗi?
12. Vì sao phải xét riêng Java heap và native memory khi phân tích bộ nhớ của ứng dụng FFM?
13. Nếu một segment có byteSize bằng 8, đọc `JAVA_INT` tại offset 8 sẽ gây lỗi gì?
14. Mã ví dụ Java 22 dùng `allocateFrom` có thể copy nguyên sang JDK21 không? Vì sao?

**Kết luận:** `Arena.global()` cấp phát bộ nhớ native với **unbounded lifetime**, scope luôn alive, và segment có thể được truy cập bởi nhiều threads. Đổi lại, **không thể `close()` và không có deallocation theo arena**, kể cả khi Java wrapper không còn reachable. Đây là công cụ đúng cho lượng dữ liệu process-lifetime **nhỏ, hữu hạn và có chủ đích**, không phải lựa chọn mặc định cho vùng nhớ tạm hay cache thay đổi theo traffic. Với tài nguyên hữu hạn, hãy chọn `Arena.ofConfined()`, `Arena.ofShared()` hoặc `Arena.ofAuto()` theo nhu cầu kiểm soát lifecycle và thread.

### Tài liệu chính thức

- [Java SE 22 — Arena API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): global scope, unbounded lifetime, `close()` và bảng so sánh arena.
- [Java SE 22 — MemorySegment API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): phạm vi bộ nhớ, bounds, alignment, thread access, scope.
- [Java SE 22 — SegmentAllocator API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): `allocate`, `allocateFrom` và các overload.
- [Java SE 22 — FFM API, JEP 454](https://openjdk.org/jeps/454): trạng thái finalized của FFM.
- [Java SE 21 — Arena API preview](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html): global arena trong FFM preview.
- [Dev.java — Access Off-Heap or On-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/): hướng dẫn thực hành bốn loại arena và vòng đời bộ nhớ.
