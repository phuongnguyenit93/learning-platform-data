# Vì sao Arena quản lý thời gian sống chung cho nhiều vùng nhớ?

## 1. Bối cảnh: nhiều vùng nhớ native, một thời điểm kết thúc

Trong Java, object thông thường được Java heap và garbage collector (GC) quản lý. Khi tương tác với native code, ta thường cần **off-heap memory**: bộ nhớ nằm ngoài Java heap để chứa cấu trúc C, mảng bytes, chuỗi kết thúc bằng NUL hoặc vùng trả về từ foreign function. Nếu quản lý theo kiểu cấp phát từng vùng rồi phải nhớ giải phóng từng vùng, code dễ bị rò rỉ, double-free và dùng sau giải phóng (*use-after-free*).

Foreign Function & Memory API (FFM) giải quyết một phần quan trọng của vấn đề bằng hai khái niệm:

- `MemorySegment`: một **view có kích thước, ranh giới và thông tin vòng đời** đối với một vùng nhớ. Segment là cách Java truy cập bộ nhớ có kiểm tra.
- `Arena`: đối tượng **cấp phát và xác định thời gian sống chung** của các native memory segments được tạo từ arena đó.

Ví dụ:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment header = arena.allocate(16);
    MemorySegment payload = arena.allocate(128);
    MemorySegment checksum = arena.allocate(ValueLayout.JAVA_INT);

    // Cả ba segments thuộc cùng arena scope.
    // Xử lý dữ liệu khi arena còn mở ...
} // close: cả ba vùng nhớ do arena quản lý đều hết hiệu lực
~~~

Đây là **đoạn minh họa nằm trong một Java method**, cần import `java.lang.foreign.Arena`, `MemorySegment` và `ValueLayout`. Không cần gọi riêng `free(header)`, `free(payload)` và `free(checksum)`. `try-with-resources` đóng đúng **một arena**, khiến các vùng native do arena đó sở hữu không còn được truy cập qua FFM segment nữa.

**Ý chính:** Arena nhóm bộ nhớ theo **vòng đời sử dụng**, không phải nhất thiết gom tất cả allocations vào một khối bytes liên tục. Ba lần `allocate` có thể trả ba vùng native riêng biệt, nhưng chúng có **cùng temporal boundary**: scope của arena.

### Mục tiêu bài học

Sau khi học, bạn có thể:

1. Giải thích vì sao chia sẻ một arena scope giúp quản lý một nhóm vùng nhớ nhất quán.
2. Phân biệt **reference Java còn sống** với **bộ nhớ native còn hợp lệ**.
3. Hiểu cơ chế `allocate` → `MemorySegment.scope()` → `Arena.close()` và kiểm tra use-after-close.
4. Chọn `Arena.ofConfined()`, `ofShared()`, `ofAuto()` hay `global()` theo ownership và vòng đời.
5. Viết và chạy ví dụ hoàn chỉnh trên **JDK 22+**, nơi FFM API được chuẩn hóa.
6. Thiết kế API nhận `Arena` hoặc trả về nhiều `MemorySegment` mà không để pointer “thoát” khỏi thời gian sống hợp lệ.
7. Nhận diện lỗi wrong thread, close quá sớm, đồng thời truy cập/close, lifetime không khớp khi gọi native.

## 2. Phiên bản JDK và nhóm API cần dùng

Bài này sử dụng **`java.lang.foreign`, API chính thức từ JDK 22** (JEP 454). Chạy các ví dụ với JDK 22 trở lên; **không yêu cầu `--enable-preview`** cho thao tác cấp phát/truy cập bộ nhớ đơn giản ở đây.

Không copy nguyên mã vào JDK 17 và kỳ vọng biên dịch: ở JDK 17, foreign memory access còn nằm trong **incubator API khác**, còn các JDK 19–21 đã trải qua các phiên bản preview với chữ ký thay đổi. Ví dụ này cố ý chọn API ổn định để có kết quả nhất quán.

Các kiểu chính:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| `Arena` | Tạo và sở hữu native allocations, xác định scope/lifetime và quy tắc thread |
| `SegmentAllocator` | Giao diện trừu tượng cho việc cấp phát; `Arena` cũng là `SegmentAllocator` |
| `MemorySegment` | Mô tả vùng nhớ, byte size, khả năng truy cập; mọi read/write chịu kiểm tra spatial/temporal |
| `MemorySegment.Scope` | Trạng thái sống của scope, với `isAlive()` |
| `ValueLayout.JAVA_INT`, `JAVA_LONG`... | Kích thước, alignment và kiểu truy cập primitive |
| `MemoryLayout` | Mô tả cấu trúc native phức tạp, giúp cấp phát theo layout thay vì tự tính offset |

**Phân biệt:** `MemorySegment` có thể là **heap segment** như `MemorySegment.ofArray(int[])` hoặc **native segment** từ `arena.allocate(...)`. Một heap segment được tạo từ Java array không tự trở thành “bộ nhớ do arena sở hữu”. Bài này tập trung vào **những segments được cấp phát từ một Arena**.

## 3. Scope chung là hợp đồng vòng đời

Một arena có **một arena scope**. Theo hợp đồng API, mọi segment được arena cấp phát đều gắn với scope đó:

~~~text
                  Arena A
                     |
                     v
                Arena A.scope()
                   / | \
                  /  |  \
                 v   v   v
           segment 1  2   3
           (header) (body) (footer)
                 |   |   |
                 +---+---+
                     |
                     v
               arenaA.close()
                     |
              scope.isAlive() == false
                     |
         Cả 3 segments đều không thể truy cập
         qua FFM API; native backing memory
         do arena sở hữu được giải phóng
~~~

Khi gọi `arena.close()` và lời gọi **hoàn tất bình thường**:

- Scope của arena không còn sống (`arena.scope().isAlive() == false`).
- **Tất cả** segments gắn với scope đó đều trở nên không hợp lệ để truy cập bằng FFM.
- Các vùng nhớ native cấp phát bởi arena được deallocate theo hợp đồng.
- Segment có thể vẫn còn là **Java object/reference** trong biến, collection, field hoặc record, nhưng điều đó **không khôi phục** vùng nhớ đã hết hiệu lực.
- Truy cập bộ nhớ qua một segment đã hết scope sẽ ném `IllegalStateException`, thay vì trở thành một con trỏ native âm thầm dùng sau `free` trong các API an toàn.

Ví dụ lỗi logic:

~~~java
MemorySegment escaped;

try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(ValueLayout.JAVA_INT);
    escaped.set(ValueLayout.JAVA_INT, 0, 42);
}

int value = escaped.get(ValueLayout.JAVA_INT, 0);
// IllegalStateException: arena scope đã đóng.
~~~

Đây là ví dụ giải thích hành vi, không phải chương trình đầy đủ. Dù `escaped` vẫn trỏ tới một Java object `MemorySegment`, việc đọc bộ nhớ native **không còn hợp lệ**.

### 3.1. “Scope chung” không có nghĩa “địa chỉ chung”

Ba segments cấp phát từ cùng arena **không mặc nhiên chia sẻ bytes** hoặc là ba phần của một khối contiguous. API `Arena.allocate` bảo đảm các vùng cấp phát riêng **không chồng lấn** theo hợp đồng allocator thông thường. Điều được chia sẻ là **scope/lifetime**, không phải nội dung hay địa chỉ.

~~~text
Arena A
  segment header:   [ địa chỉ X ... X+15 ]
  segment body:     [ địa chỉ Y ... Y+127 ]
  segment trailer:  [ địa chỉ Z ... Z+3 ]

X, Y, Z không bắt buộc liền kề nhau.
Nhưng A.close() kết thúc cả ba vùng.
~~~

Nếu cần nhiều “view” cùng trỏ tới bytes của **một allocation**, dùng `segment.asSlice(...)`; slice chia sẻ backing memory **và** kế thừa scope của segment gốc. Không nhầm “các allocations cùng arena” với “các slices cùng allocation”.

### 3.2. Hai dạng safety quan trọng

FFM segment có:

- **Spatial bounds:** không đọc/ghi vượt `segment.byteSize()`. Sai offset thường gây `IndexOutOfBoundsException`, sai alignment có thể gây `IllegalArgumentException`.
- **Temporal bounds:** không đọc/ghi khi scope hết sống. Sai lifetime thường gây `IllegalStateException`.

Arena chịu trách nhiệm rất lớn ở **temporal safety**: một lệnh close đóng lại quyền truy cập **cả nhóm**.

Tuy nhiên sự an toàn này áp dụng cho **FFM access qua Java segment**. Nếu bạn lấy raw address, đưa cho C rồi giữ con trỏ native sau khi arena đóng, **C có thể dùng dangling pointer** và gây lỗi nguy hiểm; FFM không thể kiểm tra mọi đường truy cập raw pointer ở phía native.

## 4. Vì sao nhóm nhiều vùng nhớ vào cùng Arena hợp lý?

Giả sử một lần gọi thư viện C cần:

- Buffer chứa header.
- Buffer chứa dữ liệu.
- Buffer chứa tên file hoặc chuỗi UTF-8 NUL-terminated.
- Struct kết quả.
- Vùng tạm dùng cho các thao tác chuyển đổi.

Nếu mỗi vùng có một owner khác nhau, code phải có nhiều lệnh cleanup và xử lý nhánh lỗi. Khi một bước giữa chừng ném exception, một số buffer có thể đã được cấp phát nhưng chưa đưa vào danh sách cleanup.

Mẫu sử dụng một arena:

~~~java
void processOneRequest() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment header = arena.allocate(32);
        MemorySegment payload = arena.allocate(2048);
        MemorySegment result = arena.allocate(ValueLayout.JAVA_LONG);

        // Ghi dữ liệu chuẩn bị.
        // Gọi native hàm đồng bộ, bảo đảm native không giữ pointer sau khi trả về.
        // Đọc result khi arena còn sống.
    } // Tất cả native allocations của request được thu hồi cùng lúc.
}
~~~

Đây là đoạn **minh họa**, không chứa native downcall thực tế. Lợi ích là **một lifetime boundary tương ứng một đơn vị công việc**.

### 4.1. Ba lợi ích chính

**Thứ nhất — ownership dễ kiểm toán.** Có thể nói: “Tất cả dữ liệu tạm cho request R tồn tại từ lúc mở Arena R đến khi kết thúc xử lý R”. Review code chỉ cần kiểm tra điểm mở/đóng và nơi reference được chia sẻ.

**Thứ hai — cleanup khi có exception.** `try-with-resources` tự gọi `close()` khi khối kết thúc bình thường hoặc vì exception, giảm nguy cơ quên giải phóng ở một nhánh lỗi. Một arena có thể quản lý nhiều allocations mà không yêu cầu mỗi buffer có một `finally` riêng.

**Thứ ba — tránh dùng dở một bộ dữ liệu đã hết hạn.** Nếu ba segments cùng scope, việc close khiến cả bộ cùng không còn truy cập hợp lệ. Bạn không rơi vào trạng thái “header đã free nhưng payload còn được coi là dữ liệu của cùng request”. Dĩ nhiên, **ứng dụng vẫn phải đồng bộ** nếu một thread khác đang dùng những segments đó.

### 4.2. Tư duy ownership: “mượn” thay vì “trao quyền sở hữu”

Khi một helper nhận `Arena` và cấp phát các segments, nó thường **mượn quyền cấp phát**, chứ không nên tự động đóng Arena của caller:

~~~java
record Buffers(MemorySegment header, MemorySegment payload) { }

static Buffers newBuffers(Arena arena) {
    return new Buffers(arena.allocate(16),
                      arena.allocate(128));
}

static void useBuffers() {
    try (Arena arena = Arena.ofConfined()) {
        Buffers b = newBuffers(arena);
        b.header().set(ValueLayout.JAVA_INT, 0, 42);
        int x = b.header().get(ValueLayout.JAVA_INT, 0);
        System.out.println(x);
    } // caller đóng Arena, cả hai buffers hết hiệu lực.
}
~~~

Đây là **đoạn source minh họa trong một class**, không phải chương trình độc lập. Điểm mấu chốt: `newBuffers` không gọi `arena.close()`, vì **caller** chịu trách nhiệm lifetime.

**Không** để helper tạo confined arena cục bộ bằng `try-with-resources` rồi trả `MemorySegment` ra ngoài:

~~~java
static MemorySegment wrongFactory() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(16);
    } // đóng trước khi caller kịp dùng segment
}
~~~

Đây là ví dụ **sai**, không đưa vào production. Giá trị Java return vẫn tồn tại, nhưng backing memory không còn hợp lệ.

## 5. Chương trình chạy được: một Arena, ba MemorySegments

Mục tiêu thí nghiệm: cấp phát **hai vùng native độc lập** và tạo **một slice**; xác minh cả ba có cùng scope, rồi close Arena một lần và quan sát tất cả đều không thể được đọc.

### 5.1. File `ArenaLifetimeDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class ArenaLifetimeDemo {
    private ArenaLifetimeDemo() {
    }

    private static void checkClosed(
            String name, MemorySegment segment) {
        try {
            segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println(name + ": unexpectedly accessible");
        } catch (IllegalStateException ex) {
            System.out.println(name + ": IllegalStateException");
        }
    }

    public static void main(String[] args) {
        MemorySegment first;
        MemorySegment second;
        MemorySegment secondView;

        try (Arena arena = Arena.ofConfined()) {
            first = arena.allocate(ValueLayout.JAVA_INT);
            second = arena.allocate(ValueLayout.JAVA_INT);

            first.set(ValueLayout.JAVA_INT, 0, 10);
            second.set(ValueLayout.JAVA_INT, 0, 32);

            // Alias cùng backing memory với second.
            secondView = second.asSlice(
                    0, ValueLayout.JAVA_INT.byteSize());

            int sum = first.get(ValueLayout.JAVA_INT, 0)
                    + second.get(ValueLayout.JAVA_INT, 0);

            System.out.println("sum=" + sum);
            System.out.println(
                    "view=" + secondView.get(ValueLayout.JAVA_INT, 0));

            boolean sameScope =
                    first.scope() == second.scope()
                    && second.scope() == secondView.scope();
            System.out.println("same scope=" + sameScope);
            System.out.println(
                    "alive inside=" + arena.scope().isAlive());
        } // AutoCloseable.close() được gọi chính xác một lần.

        System.out.println(
                "alive after=" + first.scope().isAlive());

        checkClosed("first", first);
        checkClosed("second", second);
        checkClosed("view", secondView);
    }
}
~~~

### 5.2. Biên dịch, chạy và stdout

Dùng **JDK 22+**:

~~~bash
javac ArenaLifetimeDemo.java
java ArenaLifetimeDemo
~~~

Stdout:

~~~text
sum=42
view=32
same scope=true
alive inside=true
alive after=false
first: IllegalStateException
second: IllegalStateException
view: IllegalStateException
~~~

Giải thích từng dòng:

1. `first` lưu `10`, `second` lưu `32`, nên tổng là `42`.
2. `secondView` là slice của `second`, nên đọc cùng bytes và được `32`.
3. Hai allocations độc lập cùng được gắn với `arena.scope()`; slice kế thừa scope đó.
4. Trong `try`, scope còn sống.
5. Ra khỏi `try`, `Arena.close()` thành công làm scope không còn sống.
6. Cả `first`, `second` và `secondView` đều bị từ chối truy cập; Java reference vẫn tồn tại nhưng native backing memory đã hết hiệu lực.

Ví dụ bắt `IllegalStateException` **chỉ để minh họa temporal safety**. Ở production không cố truy cập sau close để hỏi “đã đóng chưa”; hãy thiết kế ownership để không thể sử dụng nhầm đối tượng hết lifetime, và chỉ dùng `scope().isAlive()` cho chẩn đoán khi phù hợp.

### 5.3. Vì sao chỉ dùng `first.scope().isAlive()` đã nói được điều gì?

Trong ví dụ, cả ba segments gắn với cùng scope, nên trạng thái `isAlive()` của scope đó áp dụng cho toàn bộ nhóm. Đây chính là **điểm gom quản lý vòng đời**. Tuy nhiên kiểm tra `isAlive()` không biến đoạn code đa luồng thành an toàn: thread khác có thể close ngay **sau lần kiểm tra** và trước lúc read/write. Phải phối hợp ownership và synchronization thực tế.

## 6. Một Arena khác không bị đóng cùng Arena đầu

Chia sẻ lifetime là quan hệ **trong một arena**, không phải một trạng thái toàn cục của JVM. Có thể giữ một arena lâu hơn và dùng một arena ngắn hơn cho dữ liệu tạm:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class TwoArenasDemo {
    public static void main(String[] args) {
        MemorySegment temporary;

        try (Arena longLived = Arena.ofConfined()) {
            MemorySegment persistentForOperation =
                    longLived.allocate(ValueLayout.JAVA_INT);
            persistentForOperation.set(
                    ValueLayout.JAVA_INT, 0, 100);

            try (Arena shortLived = Arena.ofConfined()) {
                temporary = shortLived.allocate(ValueLayout.JAVA_INT);
                temporary.set(ValueLayout.JAVA_INT, 0, 7);
                System.out.println(
                        "temp=" + temporary.get(ValueLayout.JAVA_INT, 0));
            }

            System.out.println(
                    "short alive=" + temporary.scope().isAlive());
            System.out.println(
                    "long alive="
                            + persistentForOperation.scope().isAlive());
            System.out.println(
                    "long value="
                            + persistentForOperation.get(
                                    ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Chạy:

~~~bash
javac TwoArenasDemo.java
java TwoArenasDemo
~~~

Stdout:

~~~text
temp=7
short alive=false
long alive=true
long value=100
~~~

Điểm học được: `shortLived.close()` chỉ hết hiệu lực **các segments thuộc shortLived**, không ảnh hưởng `persistentForOperation` do `longLived` cấp phát. “Một arena cho mọi thứ” không phải quy tắc bắt buộc; dùng **nhiều arena theo vòng đời thực tế** thường đúng hơn.

Không hiểu nhầm nested `try` thành nested scope theo quan hệ cha-con: hai arena được tạo bằng `ofConfined()` là **hai owner độc lập**, không có quan hệ thu hồi phụ thuộc chỉ vì code viết lồng trong nhau.

## 7. Các loại Arena và lựa chọn thời gian sống

JDK 22 cung cấp bốn factory thường gặp:

| Loại | Tạo bằng | Đóng thủ công? | Thread có thể truy cập | Khi nào giải phóng |
| --- | --- | --- | --- | --- |
| Confined | `Arena.ofConfined()` | **Có** | **Chỉ owner thread** | Khi `close()` thành công |
| Shared | `Arena.ofShared()` | **Có** | **Nhiều thread** | Khi `close()` thành công |
| Automatic | `Arena.ofAuto()` | **Không** | Nhiều thread | GC thu hồi không xác định thời điểm sau khi arena và các segments không còn reachable |
| Global | `Arena.global()` | **Không** | Nhiều thread | Các vùng native do global arena cấp phát **không tự được thu hồi** bởi arena |

Hai dạng **confined** và **shared** là **bounded lifetime có explicit close**. Cả **automatic** và **global** không có explicit close, nhưng **automatic** có thể được GC thu hồi trong tương lai, trong khi **global** có lifetime không giới hạn bởi chương trình.

### 7.1. `Arena.ofConfined()`: một thread sở hữu

Confined arena do thread tạo ra sở hữu. Chỉ owner thread được allocate, truy cập segments và close. Nếu thread khác đọc segment hoặc cố close arena, API có thể ném `WrongThreadException`.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(ValueLayout.JAVA_LONG);
    data.set(ValueLayout.JAVA_LONG, 0, 123L);

    // Đọc trên đúng owner thread: hợp lệ.
    long value = data.get(ValueLayout.JAVA_LONG, 0);
}
~~~

Đây là snippet không độc lập. Confined thường phù hợp cho request xử lý tuần tự, native call đồng bộ ngắn, codec/buffer tạm hoặc parsing trên một thread.

Nó **không phải** synchronized lock: owner confinement giúp JVM kiểm tra thread hợp lệ; nó không tự chuyển việc thực thi sang owner khi bạn gọi từ thread khác.

### 7.2. `Arena.ofShared()`: một lifetime cho nhiều thread

Một shared arena không hạn chế truy cập vào một owner. Các threads khác nhau có thể dùng segments do nó cấp phát, nhưng **truy cập dữ liệu vẫn cần đồng bộ** để tránh data race và visibility problems.

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment value = arena.allocate(ValueLayout.JAVA_LONG);

    Thread writer = new Thread(
            () -> value.set(ValueLayout.JAVA_LONG, 0, 123L));

    writer.start();
    writer.join(); // Thiết lập happens-before cho kết quả ghi.

    System.out.println(
            value.get(ValueLayout.JAVA_LONG, 0));
} // Chỉ close sau khi writer đã kết thúc.
~~~

Đây là snippet bên trong một method khai báo hoặc xử lý `InterruptedException`. `Thread.join()` giúp tránh close khi worker vẫn đang dùng segment và cung cấp quan hệ happens-before từ writer tới thread chờ. **Shared scope không tự làm read/write thành atomic**, không tự bảo vệ hai threads cùng ghi.

### 7.3. `Arena.ofAuto()`: GC quản lý vòng đời chung

~~~java
Arena arena = Arena.ofAuto();
MemorySegment a = arena.allocate(64);
MemorySegment b = arena.allocate(128);
// Không gọi arena.close(): automatic arena không hỗ trợ close thủ công.
~~~

Automatic arena có shared lifetime của nhóm allocations, nhưng **không có thời điểm giải phóng xác định**. Bộ nhớ do nó cấp phát chỉ có thể được thu hồi sau khi arena **và các segments liên quan** không còn reachable; việc GC chạy khi nào không do ứng dụng quyết định.

Không dùng `ofAuto` chỉ vì “không muốn viết try-with-resources” nếu service có áp lực native memory lớn: lượng off-heap memory có thể tồn tại lâu hơn dự đoán. Khi cần cleanup có thời hạn chắc chắn, confined/shared với explicit close tốt hơn.

### 7.4. `Arena.global()`: lifetime thực chất không giới hạn

~~~java
MemorySegment permanent = Arena.global().allocate(1024);
// Không có close cho global arena.
~~~

Global arena có thể dùng cho vùng dữ liệu cần sống **suốt vòng đời tiến trình/VM**, ví dụ static native table không thu hồi theo request. Tuy nhiên **mỗi lần allocate từ global là một vùng native không được thu hồi bởi Arena**, nên việc cấp phát lặp lại theo request vào global arena là đường dễ tích lũy bộ nhớ ngoài heap.

Không dùng global như “giải pháp dễ nhất để khỏi bị IllegalStateException”. Hãy làm đúng **ownership và lifetime**.

## 8. Chương trình đa luồng minh họa shared và confined

Đoạn sau là source hoàn chỉnh chạy trên JDK 22+, có kết quả xác định. Nó thể hiện:

- `ofShared` cho phép thread khác ghi segment.
- `join()` kết thúc công việc trước khi close shared arena.
- `ofConfined` từ chối thread không phải owner truy cập segment.

### 8.1. File `ArenaThreadsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class ArenaThreadsDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment shared = arena.allocate(ValueLayout.JAVA_INT);

            Thread worker = new Thread(
                    () -> shared.set(ValueLayout.JAVA_INT, 0, 77),
                    "arena-writer");
            worker.start();
            worker.join();

            System.out.println(
                    "shared read=" + shared.get(ValueLayout.JAVA_INT, 0));
        }

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment confined =
                    arena.allocate(ValueLayout.JAVA_INT);

            Thread worker = new Thread(() -> {
                try {
                    confined.get(ValueLayout.JAVA_INT, 0);
                    System.out.println("unexpected success");
                } catch (WrongThreadException ex) {
                    System.out.println("confined wrong thread");
                }
            }, "foreign-thread");

            worker.start();
            worker.join();
        }
    }
}
~~~

### 8.2. Biên dịch và chạy

~~~bash
javac ArenaThreadsDemo.java
java ArenaThreadsDemo
~~~

Stdout:

~~~text
shared read=77
confined wrong thread
~~~

Trong `java.lang`, `WrongThreadException` được import ngầm như các lớp khác của `java.lang`. Thread writer đã `join` trước khi shared arena đóng nên ví dụ không gặp race giữa read và close. Thread truy cập confined thực hiện trong khi arena còn sống, vì vậy kiểm tra thread được kích hoạt và in thông báo ổn định.

**Tương tác nhiều thread:** `Arena.ofShared()` cho phép dùng segment trên nhiều thread; nó **không thay thế** `synchronized`, lock, VarHandle với access mode thích hợp hoặc cơ chế điều phối tác vụ.

## 9. Close dùng chung và hậu quả với aliases/slices

Khi có một native allocation:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(64);
    MemorySegment topHalf = block.asSlice(0, 32);
    MemorySegment bottomHalf = block.asSlice(32, 32);

    // topHalf và bottomHalf là views không chồng lấn
    // trên CÙNG backing allocation, với cùng scope.
}
~~~

Ở đây **một** allocation tạo **ba Java segment views**. Khi arena đóng, cả ba đều hết hiệu lực. Điều này cũng đúng khi segment được:

- Đưa vào `List<MemorySegment>` hoặc giữ trong object field.
- Trả về qua một method helper (nếu helper không đóng arena).
- Chuyển thành slice hoặc read-only view.
- Truyền tạm vào một method xử lý và lưu ở nhiều biến alias.

Reference không sở hữu một “quyền sống thêm” riêng. **Scope của arena** mới quyết định khi nào các accesses qua những views đó trở nên vô hiệu.

### 9.1. Không dựa vào kiểm tra `isAlive()` để chống close cạnh tranh

Mẫu sau có race:

~~~java
// Pseudocode: thread A và B có thể chạy cạnh tranh.
if (segment.scope().isAlive()) {
    // Thread B có thể đóng shared arena ngay sau lệnh kiểm tra.
    int value = segment.get(ValueLayout.JAVA_INT, 0);
}
~~~

Đây là **đoạn minh họa sai về đồng bộ**. `isAlive()` trả trạng thái tại thời điểm gọi, **không khóa scope** cho các thao tác tiếp theo. Với shared arena, hãy quy định mọi người dùng đã hoàn tất công việc trước khi owner gọi close, ví dụ dùng `Future.get()`, `CountDownLatch`, `Thread.join()` hoặc một lifecycle lock phù hợp.

Đặc tả `Arena.close()` thậm chí cho phép `IllegalStateException` nếu segment liên quan đang bị truy cập đồng thời theo một đường FFM đặc biệt (ví dụ native downcall). Đừng dùng try/catch quanh close như cơ chế điều phối chính; **hoàn tất việc dùng vùng nhớ trước, rồi close**.

### 9.2. Arena close không phải thao tác idempotent

~~~java
Arena arena = Arena.ofConfined();
arena.close();
arena.close(); // IllegalStateException: đã close trước đó.
~~~

Đây là minh họa. Do vậy thiết kế owner rõ ràng để gọi close đúng một lần, thường qua `try-with-resources`. Đừng truyền một arena cho hai thành phần đều tin rằng mình là owner và đều chủ động đóng nó.

## 10. API thiết kế tốt: caller sở hữu Arena

FFM hỗ trợ tách **người cung cấp chỗ đặt kết quả** khỏi **người tạo kết quả**. Một service có thể nhận `Arena`/`SegmentAllocator` như tham số và cấp phát nhiều kết quả với **lifetime do caller quyết định**.

Ví dụ một parser tạo hai vùng dữ liệu:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class RequestBuffers {
    public record Parts(MemorySegment flags, MemorySegment count) { }

    public static Parts create(Arena arena) {
        MemorySegment flags = arena.allocate(8);
        MemorySegment count = arena.allocate(ValueLayout.JAVA_INT);

        flags.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
        count.set(ValueLayout.JAVA_INT, 0, 3);
        return new Parts(flags, count);
    }

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            Parts p = create(arena);
            byte active = p.flags().get(ValueLayout.JAVA_BYTE, 0);
            int count = p.count().get(ValueLayout.JAVA_INT, 0);

            System.out.println("active=" + active);
            System.out.println("count=" + count);
        }
    }
}
~~~

Chạy:

~~~bash
javac RequestBuffers.java
java RequestBuffers
~~~

Stdout:

~~~text
active=1
count=3
~~~

Dù `create` tạo **hai native allocations**, nó **không** sở hữu việc đóng arena. Caller bao quanh toàn bộ request bằng một scope. Record `Parts` là Java object bình thường và có thể giữ references; nhưng sau close, các segments trong record vẫn không thể truy cập.

**Hợp đồng API nên được tài liệu hóa:** “Các segments trả về chỉ hợp lệ trong thời gian arena do caller cung cấp còn sống, và chỉ từ những threads được arena cho phép”.

Nếu một helper không cần biết policy thread/close, có thể nhận `SegmentAllocator` thay vì `Arena`. Tuy nhiên không phải mọi `SegmentAllocator` đều có lifetime/memory non-overlap bảo đảm giống `Arena`; đừng tùy tiện giả định khi interface quá trừu tượng.

## 11. Khi nào dùng một Arena, khi nào tách Arena?

Không có quy tắc “luôn một arena cho toàn bộ ứng dụng”. Dùng scope chung **khi dữ liệu có cùng thời điểm hết hạn**.

| Loại dữ liệu | Vòng đời phù hợp | Gợi ý |
| --- | --- | --- |
| Header, payload, checksum của một native request đồng bộ | Từ bắt đầu tới kết thúc request | Một `ofConfined()` |
| Các buffers của batch parsing trên cùng thread | Toàn batch | Một `ofConfined()` cho batch, không một arena cho mỗi phần tử |
| Các segments trong một tác vụ dùng nhiều Java threads | Đến khi mọi worker đã hoàn tất | Một `ofShared()`; close sau join/future |
| Buffer tạm trong helper riêng không cần sống cùng request | Chỉ trong helper | Một arena ngắn hơn, tách scope |
| Dữ liệu cache cần sống qua nhiều requests | Lâu hơn một request | Arena có owner lâu hơn và explicit close |
| Vùng mà không kiểm soát được thời điểm sử dụng kết thúc, và có thể GC thu hồi về sau | Không cần cleanup chính xác | Cân nhắc `ofAuto()`, kiểm soát áp lực off-heap |
| Vùng thật sự sống tới hết VM/process | Toàn vòng đời ứng dụng | `global()`, cân nhắc nguy cơ tích lũy |

Ví dụ batch 1.000 records: nếu mỗi record dùng 3 allocations cùng vòng đời batch, tạo **một arena cho batch** giúp cleanup ngắn và dễ kiểm chứng. Nhưng nếu 10 records cần giữ làm cache sau batch, chúng **không nên** nằm trong arena của batch rồi bị close; hãy copy dữ liệu cần giữ vào arena của cache có vòng đời dài hơn.

### 11.1. Copy để chuyển ownership, không chỉ gán biến

Nếu dữ liệu cần sống lâu hơn arena nguồn, **không** thể gia hạn lifetime bằng cách gán sang field hoặc record:

~~~java
// SAI về ý tưởng: saved trỏ vào vùng thuộc temp.
MemorySegment saved;
try (Arena temp = Arena.ofConfined()) {
    saved = temp.allocate(16);
}
// saved đã hết hiệu lực.
~~~

Phương án đúng là **cấp phát lại trong arena đích** rồi copy bytes khi cả hai scopes vẫn còn sống:

~~~java
// Pseudocode đặt trong method của owner thread.
try (Arena longLived = Arena.ofConfined()) {
    MemorySegment saved = longLived.allocate(16);

    try (Arena shortLived = Arena.ofConfined()) {
        MemorySegment temp = shortLived.allocate(16);

        // Chuẩn bị temp khi nó còn sống.
        // Copy vào saved ngay lúc cả 2 scopes còn hiệu lực.
        saved.copyFrom(temp);
    }

    // saved vẫn hợp lệ: scope của longLived còn sống.
}
~~~

Đoạn trên là minh họa; `MemorySegment.copyFrom` copy bytes trong giới hạn phù hợp, không thay thế các quy tắc ownership của raw pointer nằm trong một struct. **Cực kỳ quan trọng:** nếu struct được copy chứa một trường địa chỉ C trỏ về bộ nhớ của shortLived, copy **bytes** sang longLived **không tự biến con trỏ bên trong thành hợp lệ**. Bạn phải copy sâu/điều chỉnh các pointer fields theo hợp đồng native API.

### 11.2. Tách arena nếu vòng đời khác nhau

Thiết kế sai:

~~~text
Arena request (có cả buffer tạm và cache sống dài)
    |
    +-- temporary A   (nên chết sau request)
    +-- temporary B   (nên chết sau request)
    +-- cached C      (phải sống nhiều requests)
    |
    +-- close request
               |
               +-- cached C vô hiệu quá sớm
~~~

Thiết kế tốt hơn:

~~~text
Arena request: temp A, temp B  --> close sau request
Arena cache:   cached C       --> close khi cache bị dispose
~~~

Arena không tự suy ra dữ liệu nào “quan trọng hơn”. Nếu gắn nhiều segments vào cùng scope, **bạn đang chủ động chọn chung một thời điểm hết hạn** cho tất cả chúng.

## 12. Ví dụ gần thực tế: chuẩn bị tham số cho native call

Giả sử Java muốn gọi thư viện C có API khái niệm:

~~~c
int process_request(
    const char *name,
    const unsigned char *bytes,
    size_t length,
    int *result);
~~~

Đây là **prototype minh họa**; bài không implement hay link thư viện C này. Một lần gọi có thể cần:

- Chuỗi `name` ở vùng native kết thúc bằng NUL.
- Buffer `bytes` native.
- Vùng `result` cho output.
- Một số temporary structs bổ sung.

Phần Java chuẩn bị bằng cùng arena (minh họa, **không phải chương trình tự chạy**):

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment name = arena.allocateFrom("report.bin");

    byte[] input = { 1, 2, 3, 4 };
    MemorySegment bytes = arena.allocateFrom(
            ValueLayout.JAVA_BYTE, input);

    MemorySegment result = arena.allocate(ValueLayout.JAVA_INT);

    // Gọi downcall đồng bộ trong phạm vi arena còn sống.
    // FunctionDescriptor và MethodHandle phải khớp native ABI.
    // Sau khi downcall trả về, đọc result.
} // Kết thúc cả 3 vùng native trong cùng một lifetime boundary.
~~~

Trên JDK 22, `arena.allocateFrom(String)` tạo chuỗi native UTF-8 có NUL kết thúc. `arena.allocateFrom(ValueLayout.JAVA_BYTE, input)` cấp phát và copy từ byte array sang native memory. Chi phí allocation/copy vẫn tồn tại; Arena chủ yếu giải quyết **lifetime**, không hứa hẹn mọi conversion là zero-copy.

**Điều kiện bắt buộc:** C function đồng bộ được gọi phải **không giữ các con trỏ này sau khi trả về**. Nếu native code bắt đầu background job hoặc lưu pointer vào static state, arena phải sống **ít nhất tới khi native code xác nhận không dùng pointer nữa**. Đóng arena ngay sau khi một hàm “submit_async” trả về sẽ là use-after-free tiềm ẩn ở phía C.

### 12.1. Downcall, callback/upcall và thời gian sống

Một số tài nguyên FFM khác cũng nhận arena để gắn lifetime, ví dụ upcall stub hoặc native library symbol lookup. Khi một callback pointer được đưa cho C, nó chỉ hợp lệ theo phạm vi được API/hợp đồng gắn vào. Phải đóng arena **sau khi** native code ngừng gọi callback. Không đóng arena rồi tin rằng C sẽ tự thấy `IllegalStateException`; C chỉ có địa chỉ máy và có thể crash hoặc corrupt memory.

Mối quan hệ nên là:

~~~text
Java owner tạo arena
     |
     +-- allocate input/outputs
     +-- tạo native callback stub nếu cần
     |
     +-- native process sử dụng đồng bộ
     |   hoặc async có một handshake hoàn tất rõ ràng
     |
     +-- native xác nhận đã ngừng dùng pointers/stubs
     |
     +-- arena.close()
~~~

Đối với **restricted FFM APIs** như một số linker/symbol lookup và reinterpret, JDK có cơ chế cấp quyền native access. Những quyền này là chủ đề riêng; **bốn ví dụ runnable chỉ cấp phát/đọc/ghi bằng Java 22 API và không cần `--enable-native-access`**. Đừng áp dụng lẫn yêu cầu của restricted downcall APIs cho việc dùng `Arena.allocate` thuần túy.

## 13. Thread confinement và close trong shared Arena

### 13.1. Confined: quản lý an toàn bằng một owner

Một confined arena giúp tránh nhiều tình huống cạnh tranh: JVM chỉ cho thread sở hữu nó truy cập memory segments và close. Điều này phù hợp với dữ liệu tạm của một native call được thực hiện tuần tự trên một thread.

Nhưng nếu truyền segment sang worker khác:

~~~java
// Mảnh code minh họa bên trong owner thread.
Arena a = Arena.ofConfined();
MemorySegment s = a.allocate(ValueLayout.JAVA_INT);

Thread other = new Thread(() -> {
    s.get(ValueLayout.JAVA_INT, 0); // WrongThreadException
});
other.start();
other.join();

a.close();
~~~

Lệnh `join()` ở đây giả định method xử lý `InterruptedException`. Nếu exception trên worker không được catch thì sẽ in stack trace; **không chạy snippet này như một demo có stdout xác định**; dùng `ArenaThreadsDemo` ở phần 8.

`WrongThreadException` không có nghĩa arena đã close; nó cho biết thread hiện tại **không được phép truy cập** vùng nhớ đó.

### 13.2. Shared: dễ chia sẻ hơn, nhưng close cần giao thức

Shared arena cho phép các thread truy cập, nhưng nếu một thread close khi thread khác vẫn đang chạy native downcall liên quan segment, JVM có thể chặn việc đóng không hợp lệ bằng `IllegalStateException`; ngay cả khi FFM runtime phát hiện một số race, **đừng dựa vào exception để làm đồng bộ**.

Một pattern nên dùng:

1. Owner ngừng nhận tasks mới sử dụng arena.
2. Gửi yêu cầu stop hoặc chờ futures/threads đang xử lý.
3. Xác nhận mọi đường sử dụng segments/upcall pointers đã hoàn tất.
4. Gọi `arena.close()` một lần.
5. Cấm mọi task mới dùng memory segments đã hết lifetime.

Nếu các thread đồng thời ghi cùng memory, còn phải có quy tắc đồng bộ **dữ liệu**, độc lập với việc arena shared. Memory safety về lifetime không tự bằng thread-safety của thuật toán.

## 14. MemorySegment là view chứ không phải chủ tài nguyên

Một cách thiết kế có ích là tách ba câu hỏi:

1. **Ai sở hữu resource?** Arena (hoặc ngoại lệ: heap array, external allocation có owner riêng).
2. **View nào đọc/ghi nó?** Một hay nhiều `MemorySegment`, slices hoặc read-only views.
3. **Khi nào resource hết hạn?** Khi arena scope đóng hoặc theo policy automatic/global.

~~~text
                         Lifetime owner
                              Arena
                                |
                        (một scope duy nhất)
                                |
          +---------------------+-------------------+
          |                     |                   |
       Allocation 1         Allocation 2       Allocation 3
          |                     |                   |
       Segment A            Segment B           Segment C
          |                     |
          +-- Slice A1         +-- read-only B1
          +-- Slice A2
                                |
                    Arena đóng -> mọi views trên
                    các allocations đó mất hiệu lực
~~~

Đây là lý do **một Arena quản lý nhiều vùng nhớ** mạnh hơn một biến chứa một con trỏ: vòng đời được xác định ở **mức nhóm tài nguyên**, còn mỗi segment là một **view có kiểm tra**.

### 14.1. Không lẫn lifetime với GC của Java object

- **Confined/shared:** Java object `MemorySegment` còn được giữ trong field **không ngăn** explicit `arena.close()` làm backing memory hết hiệu lực.
- **Automatic:** lifetime được quản lý bởi reachability của arena **và các segments**; GC mới quyết định thời điểm native memory được thu hồi.
- **Global:** lifetime không bị kết thúc bằng `close()`; việc chỉ mất reference Java không có nghĩa native allocation được deallocate bởi arena.
- **Heap segment:** underlying Java array tiếp tục có lifetime do Java heap/GC quản lý, không phải do một native arena bạn vừa đóng.

FFM giảm rủi ro use-after-free **trong Java-level FFM accesses**, nhưng không thay thế quản lý đúng ownership khi C giữ raw pointer.

## 15. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Sửa đúng |
| --- | --- | --- |
| Return `MemorySegment` từ `try (Arena arena=...)` của chính helper | Caller nhận segment đã hết hạn | Caller tạo/đóng arena, helper nhận arena làm tham số |
| Giữ segments trong cache nhưng arena là per-request | Cache chứa Java references không còn truy cập được | Tách cache arena dài hạn hoặc copy data hợp lệ |
| Dùng `Arena.global()` cho mỗi request | Memory native tích lũy vì global không có cleanup | Confined/shared per request và explicit close |
| Coi `Arena.ofAuto()` tương đương close ngay | Off-heap memory thu hồi thời điểm không xác định | Explicit close khi yêu cầu cleanup dự đoán được |
| Đọc `segment.get(...)` sau `arena.close()` | `IllegalStateException` | Tổ chức scope bằng try-with-resources |
| Đưa confined segment cho thread khác | `WrongThreadException` | Giữ trong owner thread hoặc chọn shared arena |
| Dùng shared arena rồi cho rằng tự thread-safe | Data race / visibility lỗi | Lock, join, futures hoặc VarHandle phù hợp |
| Close shared arena khi worker/downcall vẫn dùng data | Truy cập lỗi, close có thể thất bại, nguy hiểm với raw pointer C | Có handshake hoàn tất và close sau khi mọi người dùng xong |
| Gọi `close()` hai lần trên arena explicit | `IllegalStateException` | Một owner, một lần close |
| Copy bytes của struct nhưng giữ địa chỉ cũ bên trong struct | Dangling native pointer sau close nguồn | Deep copy và cập nhật các pointer fields |
| Nghĩ allocations chung arena phải liền nhau | Tính offset C sai, đọc tràn vùng | Tôn trọng địa chỉ/byteSize từng segment |
| Tin rằng GC Java luôn giải phóng off-heap ngay | Dự đoán RAM sai, rò rỉ logic | Dùng try-with-resources và đo native footprint |

### 15.1. Exception nào cần phân biệt?

- `IllegalStateException`: thường là scope đã đóng, hoặc close gọi lần thứ hai; cũng có thể do close khi resource đang bị truy cập trong một số trường hợp.
- `WrongThreadException`: truy cập/đóng confined arena từ thread sai.
- `IndexOutOfBoundsException`: offset/length nằm ngoài ranh giới segment.
- `IllegalArgumentException`: alignment hoặc allocation size không hợp lệ.
- `UnsupportedOperationException`: cố `close()` automatic/global arena.
- `OutOfMemoryError`: không đủ tài nguyên để cấp phát; phải cân nhắc áp lực native memory, chứ không chỉ Java heap.

Đừng bắt hết các ngoại lệ trên rồi tiếp tục “thử dùng thêm” một segment có trạng thái không chắc chắn. Hãy xem lại scope, quyền sở hữu và quy tắc dừng.

## 16. Checklist thiết kế vòng đời trong dự án native interoperability

Trước khi đưa Arena vào public API hoặc JNI/FFM bridge, trả lời:

- Các segments có **thật sự hết hạn cùng lúc** không? Nếu không, nên chia arena.
- Ai là **owner duy nhất** được đóng arena, và họ đóng ở đâu?
- Có dùng `try-with-resources` để đảm bảo cleanup ngay cả khi Java code ném exception không?
- Có Java object/collection/cache nào giữ segment **lâu hơn scope** không?
- Có native code giữ raw pointer sau khi call trả về hoặc sau khi coroutine/task đã hoàn tất không?
- Nếu multi-thread: arena cần **shared** hay có thể confined? Đã chặn data races và bảo đảm workers kết thúc trước close chưa?
- Có slice/read-only alias nào khiến người dùng tưởng đó là một allocation/lifetime riêng không?
- Có dùng `ofAuto`/`global` chỉ để tránh phải giải quyết ownership không?
- Các struct/arrays chứa pointer đến allocation khác đã được **copy sâu hoặc cùng lifetime** chưa?
- Khi có cancellation, timeout hoặc exception, có còn thread/native code đang giữ pointer không?
- Đã đo native memory footprint, lifetime và concurrency behavior trong workload thực tế chưa?

**Nguyên tắc:** Arena nên gắn với một **đơn vị công việc** có vòng đời rõ ràng (một request, batch, transaction, native invocation, cache object). Khi đơn vị công việc kết thúc, **đóng arena** là tuyên bố “toàn bộ vùng nhớ thuộc công việc này không còn hợp lệ”.

## 17. Câu hỏi tự kiểm tra

**1.** Một arena cấp phát ba segments. Hai segments đã “được dùng xong”, một còn dùng. Có nên close arena để giải phóng hai cái đầu không?  
**Đáp án:** Không, nếu segment thứ ba vẫn cần truy cập. `close()` kết thúc **toàn bộ arena scope**. Nếu muốn giải phóng riêng, nên tách allocations vào arenas với lifetimes khác nhau hoặc thay đổi ownership.

**2.** `MemorySegment` vẫn nằm trong một `List` sau `arena.close()`. Tại sao không đọc được nữa?  
**Đáp án:** Java reference còn sống không quyết định native backing memory còn hợp lệ. Segment có **temporal bounds** theo arena scope; close làm scope không còn alive.

**3.** Hai segments tạo bằng `arena.allocate(...)` có nhất thiết cùng địa chỉ hoặc nằm cạnh nhau?  
**Đáp án:** Không. Chúng cùng **scope**, không nhất thiết cùng backing allocation hoặc liên tiếp trong address space.

**4.** Một slice của segment đã được cấp phát bằng Arena A có sống lâu hơn Arena A không?  
**Đáp án:** Không; slice kế thừa temporal bounds của segment nguồn.

**5.** Tại sao `Arena.ofConfined()` phù hợp với request chạy một thread?  
**Đáp án:** Owner thread được xác định, API ngăn thread khác truy cập và một lần close có thể thu hồi tất cả các native buffers cùng request.

**6.** `Arena.ofShared()` có tự bảo đảm hai threads ghi cùng một `int` không xảy ra race không?  
**Đáp án:** Không. Nó cho phép truy cập đa luồng về **lifetime**, nhưng thuật toán vẫn cần synchronization và memory-ordering thích hợp.

**7.** Dùng `Arena.ofAuto()` rồi gọi `close()` để nhanh chóng giải phóng mọi allocation được không?  
**Đáp án:** Không. Automatic arena không hỗ trợ explicit close; GC quyết định thời điểm thu hồi sau khi unreachable.

**8.** Vì sao dùng `Arena.global()` cho hàng triệu request nhỏ nguy hiểm?  
**Đáp án:** Native allocations từ global arena không được deallocate bởi arena; memory có thể tăng theo số request dù Java đã bỏ references.

**9.** Một native function giữ pointer được truyền từ segment để dùng bất đồng bộ. Có thể đóng arena ngay khi hàm submit trả về không?  
**Đáp án:** Không, trừ khi hợp đồng native bảo đảm đã copy dữ liệu và không giữ pointer. Nếu C còn dùng pointer sau close, FFM không tự kiểm soát raw C accesses; có thể gây corruption/crash.

**10.** Hai arenas được mở lồng nhau bằng `try` có tự tạo quan hệ “đóng cha đóng con” không?  
**Đáp án:** Không. Chúng là hai arena độc lập; lệnh close của mỗi arena chỉ tác động tới allocations thuộc scope tương ứng. Code `try` lồng nhau chỉ định thứ tự lexical cleanup.

**11.** `arena.scope().isAlive()` trả `true` trong shared arena. Có thể yên tâm sử dụng segment ở thread khác mà không cần phối hợp close không?  
**Đáp án:** Không. Check trạng thái có thể lỗi thời ngay sau đó; cần protocol về lifetime và completion của tasks.

**12.** Một API helper cần tạo nhiều buffers trong lifecycle do caller quyết định. Tại sao nhận `Arena` là một thiết kế tốt?  
**Đáp án:** Caller giữ quyền sở hữu, chọn confined/shared và thời điểm đóng; helper tạo nhiều segments đều có lifetime chung rõ ràng mà không tự giải phóng quá sớm.

## 18. Tài liệu chính thức để đào sâu

- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): arena scope, phân loại confined/shared/automatic/global, `close`, owner thread và invalidation của mọi segments.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): temporal/spatial bounds, slicing, `scope()`, `get`/`set` và `IllegalStateException`.
- [Oracle Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): cấp phát bằng layout/giá trị, lợi ích của việc nhận allocator làm tham số.
- [Oracle Java SE 22 — FFM package overview](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html): bối cảnh memory access, off-heap và foreign function calls.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API chính thức ở JDK 22, động cơ thiết kế và vòng đời memory segments.
- [Oracle Java 22 Core Libraries Guide — Memory Segments and Arenas](https://docs.oracle.com/en/java/javase/22/core/java-core-libraries-developer-guide.pdf): các ví dụ cấp phát, access native memory và ownership.

**Kết luận:** Arena quản lý **thời gian sống chung** vì các segments được cấp phát từ nó cùng tham chiếu **một scope**, nên một lần close đóng lại quyền truy cập của **toàn bộ nhóm vùng nhớ**. Điều này giúp code JNI/FFM có ownership rõ ràng và cleanup tập trung; lựa chọn đúng **ranh giới công việc**, **thread model** và **thời điểm close** mới là yếu tố quyết định an toàn.
