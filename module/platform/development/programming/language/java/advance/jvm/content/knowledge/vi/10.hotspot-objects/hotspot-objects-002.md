# Cấp phát nhanh bằng con trỏ và vùng cấp phát riêng của luồng (TLAB) trong HotSpot

## 1. Mục tiêu và vấn đề cần giải quyết

Trong Java, biểu thức `new Item(...)` trông rất đơn giản. Nhưng ở cấp JVM, runtime phải cấp phát đủ dung lượng cho object, bảo đảm alignment và trạng thái trường ban đầu, khởi tạo object, rồi trả về một reference hợp lệ. Nếu **mọi** lần tạo object của **mọi thread** đều phải xin một khóa global của heap, tốc độ tạo object trong ứng dụng nhiều luồng có thể bị giới hạn nghiêm trọng.

**HotSpot** thường giải quyết bài toán này bằng hai kỹ thuật gắn kết:

1. **Bump-the-pointer allocation**: trong một vùng heap phù hợp còn chỗ trống liên tục, giữ con trỏ `top` chỉ đầu phần chưa cấp phát. Để cấp object có kích thước đã căn chỉnh `size`, kiểm tra `top + size <= end` rồi dịch `top` lên.
2. **Thread-Local Allocation Buffer (TLAB)**: cấp cho một luồng thực thi một **đoạn heap** dùng để tự cấp phát object theo cơ chế fast path, giảm nhu cầu tranh chấp khi mỗi object được tạo.

Bài học giúp bạn giải thích được:

- TLAB **nằm trong Java heap**, **không phải JVM stack**, **không phải `ThreadLocal<T>`** và không phải “bộ nhớ riêng vĩnh viễn” chứa mọi object của thread.
- Tại sao mỗi allocation trong TLAB thường chỉ cần kiểm tra giới hạn, bump pointer và làm các bước initialization.
- Khi TLAB không đủ chỗ, HotSpot có thể thử **refill/retire TLAB**, cấp phát ngoài TLAB hoặc đi vào **slow path** tùy collector, kích thước object và chính sách runtime.
- Vì sao object sau khi cấp phát trong TLAB vẫn có thể **được thread khác đọc** khi reference được công bố an toàn.
- Vì sao `new` trong source **không bảo đảm** luôn tồn tại một heap allocation tại runtime: JIT escape analysis/scalar replacement có thể loại bỏ allocation.
- Cách quan sát `-XX:+UseTLAB`, `-XX:-UseTLAB` và `-Xlog:gc+tlab=...` trong HotSpot, cùng giới hạn của logging/benchmark.

**Giới hạn phạm vi:** TLAB và bump-pointer fast path là **chi tiết triển khai HotSpot**, không phải yêu cầu mọi Java Virtual Machine implementation trong JVMS phải dùng cùng cấu trúc hoặc cùng flags.

## 2. Từ Java source đến thao tác cấp phát

Mã nguồn:

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}

// Nằm bên trong một method:
Point p = new Point(3, 4);
~~~

Đoạn trên **minh họa** class và statement; chưa phải file có `main` độc lập. Với `javac` thông dụng, đường bytecode để tạo object thường gồm:

~~~text
new           #...   // class Point
dup
iconst_3
iconst_4
invokespecial #...   // Point.<init>:(II)V
astore_1
~~~

Diễn giải:

1. `new` là opcode yêu cầu cấp phát object của class tương ứng (sau class resolution và initialization requirements thích hợp).
2. `dup` giữ một reference trên operand stack để biểu thức `new Point(...)` còn reference sau khi constructor được gọi.
3. `iconst_3`/`iconst_4` chuẩn bị tham số.
4. `invokespecial Point.<init>` chạy constructor. **Constructor không phải là chính thao tác cấp phát**: nó khởi tạo object đã được cấp phát.
5. `astore_1` lưu reference vào local-variable slot. **Reference nằm trong frame; object theo mô hình JVM được cấp phát trong heap.**

Đây là mức **bytecode trừu tượng**. Khi interpreter hoặc JIT xử lý `new`, HotSpot có thể chọn nhiều đường allocation khác nhau. Bạn **không thấy TLAB pointer arithmetic trực tiếp qua `javap -c`**, vì `javap` chỉ hiển thị JVM bytecode, không phải machine code của JIT hoặc C++ runtime helpers.

### JVMS bảo đảm gì, HotSpot lựa chọn gì?

| Tầng | Điều được bảo đảm/mô tả | Không nên suy |
| --- | --- | --- |
| Java language/JVMS | Ngữ nghĩa `new`, kiểu reference, object initialization, Java heap là run-time data area dùng chung | Mọi VM phải cấp phát qua TLAB |
| HotSpot allocator | Tối ưu phổ biến: TLAB, bump pointer, allocation slow path | Mỗi object đều đi qua cùng fast path |
| Garbage collector | Quản lý free/used regions, di chuyển hoặc thu hồi objects theo collector | Heap luôn luôn chỉ có một Eden liên tục |
| JIT compiler | Có thể inline, loại bỏ allocations nhờ scalar replacement, điều chỉnh machine code | Thấy `new` là đủ để đếm heap allocations thực |

## 3. Bump-the-pointer: từ `top` tới vị trí object

Giả sử HotSpot có một vùng heap đang sử dụng để cấp phát tuần tự. Đặt:

- `start`: đầu vùng được cấp phát cho allocator.
- `top`: vị trí phần bộ nhớ kế tiếp còn trống.
- `end`: giới hạn vùng có thể cấp phát.
- `size`: kích thước object **đã bao gồm header, fields, padding/alignment** theo layout cụ thể.

~~~text
Đoạn bộ nhớ liên tục được dành cho allocation:

start                        top                         end
  |                           |                           |
  v                           v                           v
  +---------------------------+---------------------------+
  |  các object đã cấp phát   |       phần còn trống       |
  +---------------------------+---------------------------+

Yêu cầu object mới có aligned size = S:

  nếu top + S <= end:
       objectAddress = top
       top = top + S
       chuẩn bị memory/header/object fields theo semantics
       trả reference tới object

  nếu không:
       không thể dùng đường fast path đó
       -> xử lý refill/slow path/đường khác phù hợp
~~~

Đây là **pseudo-code mô hình hóa**, không phải nguyên văn machine code HotSpot. Implementations còn xử lý overflow, alignment, memory ordering, JFR/JVMTI instrumentation, barriers, GC state, zeroing và các yêu cầu khác.

### Ví dụ số học minh họa, không phải object layout thực

Giả sử một vùng có `top = 1_000`, `end = 1_128`, cần cấp object với **aligned size = 24 bytes**:

~~~text
1_000 + 24 = 1_024 <= 1_128  -> cấp được
object bắt đầu ở offset giả định 1_000
new top = 1_024

Lần sau cần 112 bytes:
1_024 + 112 = 1_136 > 1_128 -> không đủ trong vùng này
~~~

Những số 1_000, 1_128, 24, 112 là **số giả định để hiểu thuật toán**. Chúng không nói rằng mọi Java object luôn có header 12/16 bytes hoặc Point luôn chiếm đúng 24 bytes. Layout phụ thuộc JDK, compressed oops/class pointers, object alignment, loại object và cấu hình JVM.

### Vì sao bump pointer nhanh?

Nếu có **phần heap rỗi liên tục**, allocator không cần tìm một block phù hợp trong freelist cho mỗi object. Các thao tác chính có thể được tối ưu thành vài phép so sánh và cộng con trỏ. Tuy nhiên nếu **nhiều threads cùng cập nhật một con trỏ `top` của heap**, VM cần đồng bộ bằng atomic operations, CAS hoặc cơ chế khác; đây là nơi TLAB giúp giảm tranh chấp.

**Không nhầm** bump pointer của allocator với Java object reference: application không được phép cộng trừ `Object` references như con trỏ C. `top` là dữ liệu quản lý cấp phát bên trong HotSpot.

## 4. TLAB là gì và nằm ở đâu?

**TLAB = Thread-Local Allocation Buffer**: một vùng **con của Java heap** mà HotSpot cấp cho một thread thực thi để tạo phần lớn object nhỏ với fast path. Có thể hình dung một heap gồm nhiều đoạn, trong đó một số đoạn đang được “dành quyền cấp phát” cho những threads:

~~~text
                    JAVA HEAP (shared JVM-wide)
+----------------------------------------------------------------+
| Collector-managed regions / allocation space                   |
|                                                                |
| +----------------+  +----------------+  +--------------------+ |
| | TLAB thread A  |  | TLAB thread B  |  | Other heap space   | |
| | start/top/end  |  | start/top/end  |  | large allocations  | |
| +----------------+  +----------------+  | objects from past  | |
|                                          | TLABs, GC regions  | |
|                                          +--------------------+ |
+----------------------------------------------------------------+

Thread A có quyền bump pointer trong TLAB A khi đang sở hữu vùng đó.
Thread B có quyền bump pointer trong TLAB B.
Object tạo trong TLAB vẫn là object trong HEAP và có thể escape.
~~~

**Ba điều quan trọng:**

1. **TLAB không phải vùng nhớ riêng về ngữ nghĩa Java.** Nó chỉ là vùng cấp phát dành cho một thread trong một thời điểm. Khi object đã được công bố đúng cách, thread khác vẫn có thể truy cập nó.
2. **TLAB không phải thread stack**: local `Foo f` thường là reference trong frame; bản thân `new Foo()` là object thuộc heap (trừ khi JIT loại allocation). Object không “chuyển từ stack sang heap” chỉ vì reference escape từ thread cấp phát.
3. **TLAB không phải `ThreadLocal<Foo>`**: `ThreadLocal` là một Java API lưu giá trị theo thread; TLAB là bộ đệm quản lý memory cấp phát trong VM. Hai thứ có tên giống một phần nhưng chức năng khác nhau hoàn toàn.

### Per-thread nhưng không nhất thiết là per-virtual-thread

Trong HotSpot, TLAB gắn với **execution thread context** mà allocator sử dụng. Với **virtual threads**, công việc có thể chạy trên nhiều carrier platform threads theo lịch scheduler. Vì vậy **không được khẳng định cứng** “mỗi virtual thread có một TLAB riêng không đổi trong toàn bộ vòng đời”. Những chi tiết TLAB/OS-thread/carrier là implementation-specific và có thể thay đổi theo release.

## 5. Cơ chế fast path trong TLAB

Mỗi TLAB điển hình có các giới hạn/quản lý như `start`, `top` và `end`. OpenJDK HotSpot giữ những thành phần nội bộ liên quan trong mã `ThreadLocalAllocBuffer`.

### Đường cấp phát khái niệm

~~~text
Java code: new SmallObject(...)
                  |
                  v
             allocation needed?
                  |
                  +-- No (optimized away via EA/scalar replacement)
                  |       -> không cấp heap object thực ở đường này
                  |
                  +-- Yes
                        |
                        v
                 TLAB fast path enabled?
                        |
             +----------+----------+
             |                     |
            Yes                    No
             |                     |
             v                     v
       aligned size fit?       collector/VM
             |                allocation path
       +-----+-----+
       |           |
      Yes          No
       |           |
       v           v
  bump TLAB top   refill TLAB
  init object     or outside-TLAB/slow path
  return ref          |
                      v
                có đủ memory?
                 |        |
                Yes      No
                 |        |
               init/ref   có thể GC/allocate
                          hoặc ném OOME
~~~

Cần phân biệt “allocation fast path” với toàn bộ constructor. Allocator dành memory và khởi tạo trạng thái object theo contract; constructor code có thể thực hiện logic phức tạp, thậm chí ném exception. Một constructor chậm **không chứng minh** allocation bump pointer chậm.

### Mô hình pseudo-code

~~~text
allocateInTLAB(thread, objectSize):
    tlab = thread.currentTLAB
    size = align(objectSize)

    if tlab is usable and size <= tlab.end - tlab.top:
        address = tlab.top
        tlab.top = tlab.top + size
        prepare_memory_and_object_header(address, size)
        return address

    return slowAllocationPath(thread, size)
~~~

**Pseudo-code trên cố ý bỏ bớt chi tiết JVM.** Trong HotSpot thật, allocation paths còn có kiểm soát sampling/observability, zeroing, GC barriers, headroom reserve và các điều kiện khác. `tlab.end` không nhất thiết tương đương dấu `allocation_end` của mọi implementation; không học thuộc internal field layout như Java API contract.

### Vì sao không cần khóa global mỗi object?

Chỉ **thread đang giữ TLAB** cập nhật allocation pointer của TLAB ấy ở fast path, nên các phép bump liên tiếp thường không phải tranh chấp cùng một global pointer với threads khác. VM vẫn cần phối hợp để cấp **TLAB mới**, thu hồi phần chưa dùng, quản lý heap và GC.

Vì vậy phát biểu chính xác là:

> TLAB giảm chi phí tranh chấp **trên nhiều allocation nhỏ ở fast path**, không có nghĩa ứng dụng hoàn toàn không dùng synchronization hay allocation luôn lock-free trên mọi nhánh.

## 6. TLAB đầy: refill, retire, outside-TLAB và slow path

Một TLAB không phải hộp không đáy. Mỗi allocation làm `top` tiến gần `end`. Khi không đủ chỗ cho object tiếp theo, HotSpot có thể thực hiện một số phương án:

1. **Refill TLAB**: xin một vùng heap khác phù hợp, retire vùng cũ và tiếp tục cấp phát từ buffer mới.
2. **Allocate outside TLAB**: với object tương đối lớn so với phần trống/cách tính kích thước TLAB, VM có thể cấp phát object trực tiếp qua heap allocator thay vì bỏ nhiều phần trống ở TLAB.
3. **Slow allocation path**: liên hệ collector, xem xét các vùng cấp phát, phối hợp allocation, thử GC hoặc cơ chế khác; nếu vẫn không đủ memory, có thể kết thúc bằng **`OutOfMemoryError`**.
4. **TLAB resize**: HotSpot điều chỉnh desired TLAB size theo allocation profile và chính sách, thay vì một kích thước cố định toàn ứng dụng.

OpenJDK `ThreadLocalAllocBuffer` theo dõi số lần refill, allocation ngoài TLAB/slow allocations và lượng không gian còn lại bị bỏ khi retire TLAB. Thông tin này giúp phân tích trade-off giữa throughput và fragmentation/waste.

### Tại sao đôi khi cấp ngoài TLAB hiệu quả hơn?

Giả sử vùng TLAB A còn 48 bytes, object mới cần 256 bytes. Nếu buộc retire TLAB ngay, còn 48 bytes có thể không dùng được cho allocation khác bên trong TLAB đó. Với một số điều kiện, VM có thể cấp **object lớn hơn ngoài TLAB** và tiếp tục dùng phần còn lại cho các object nhỏ hơn. Quyết định phụ thuộc **refill waste limit** và chính sách HotSpot, không phải câu lệnh Java được phép chọn trực tiếp.

~~~text
TLAB A:
+-------------------------+----------+
| objects đã cấp          | 48B free |
+-------------------------+----------+

Yêu cầu 256B:
  Lựa chọn có thể xảy ra:
  - outside-TLAB allocation, giữ TLAB cho vật nhỏ
  - retire/refill TLAB rồi allocate bằng TLAB mới
  - slow path phụ thuộc collector, heap state và policy
~~~

Không diễn giải ví dụ thành quy tắc “cứ object lớn hơn 48B thì luôn cấp ngoài TLAB”. Đây chỉ là **một nhánh chính sách**. Kích thước TLAB, alignment, headroom và GC allocation interfaces phức tạp hơn ví dụ.

### Phần TLAB còn thừa đi đâu?

Khi retire một TLAB, có thể còn khoảng trống không đủ cho object đang yêu cầu. HotSpot cần khiến heap vẫn **parsable** đối với collector và heap walk; implementation có thể chèn **filler/dummy objects** hoặc điều chỉnh accounting phù hợp. Phần space chưa dùng được ghi nhận dưới các chỉ số waste tương ứng.

TLAB waste **không phải Java memory leak** theo nghĩa references giữ objects sống vô hạn. Đó là chi phí nội bộ của chiến lược phân vùng cấp phát. Collector có thể thu hồi/tái sử dụng không gian ở thời điểm thích hợp.

### TLAB size có cố định cho mọi thread không?

**Không.** HotSpot có các thông số như desired size, initial size, refills/alloc fraction và giới hạn alignment. VM có thể tự động điều chỉnh theo **allocation rate** của từng execution thread, workload và chính sách GC. Không được kết luận mỗi thread luôn giữ đúng “1 MB TLAB” hoặc cứ tạo 1 triệu object thì phải có chính xác N lần refill.

## 7. Object layout và chi phí thực của một allocation

Một object cần nhiều hơn dữ liệu field. Kích thước allocated thường liên quan:

- **Object header** và metadata cần cho runtime/GC.
- **Instance fields** và cách sắp xếp/alignment.
- **Padding** để thỏa object alignment.
- Với array: thông tin độ dài, phần tử và padding.
- Những lựa chọn HotSpot như compressed oops, compressed class pointers, compact object headers ở các release hỗ trợ và kích thước địa chỉ.

~~~text
Minh họa khái niệm:

+--------------------+
| object header      |
+--------------------+
| field int x        |
| field int y        |
+--------------------+
| optional padding   |
+--------------------+

allocation size = aligned total bytes
~~~

Không dùng một ví dụ kích thước object cụ thể làm quy luật cho mọi JDK/architecture. Ví dụ câu “`new Point(3,4)` luôn là 24 bytes” không đúng nếu cấu hình layout khác nhau. Bạn có thể dùng công cụ phân tích object layout chuyên dụng trong môi trường phù hợp, nhưng kết quả có tính **implementation- và build-specific**.

**Zero initialization:** Java yêu cầu fields có giá trị mặc định đúng trước khi constructor code gán giá trị. HotSpot có thể đạt điều đó bằng zeroed memory từ TLAB refill, zeroing trên allocation path hoặc cách tối ưu tương đương. Không được suy rằng bump pointer “chỉ cần cộng địa chỉ, không bao giờ cần chuẩn bị memory/header”.

## 8. TLAB và GC: phạm vi/collector rất quan trọng

Mô tả phổ biến của HotSpot truyền thống là mỗi thread cấp phát phần lớn object mới trong **young generation/Eden** thông qua TLAB. Nhưng **đừng biến hình ảnh này thành luật mọi collector ở mọi release**:

- Các collectors quản lý heap bằng regions/spaces và các fast allocation interfaces khác nhau.
- Một số objects lớn hoặc có điều kiện đặc biệt có thể đi **outside TLAB**, vào vùng cấp phát đặc biệt, hoặc đường khác.
- Collector có thể di chuyển object sang vùng khác trong khi GC chạy; object không “thuộc TLAB mãi mãi” sau khi được tạo.
- Refilling TLAB cần phối hợp với nguồn cấp phát của collector; việc đó có thể tạo GC pressure hoặc request GC khi heap không đủ space.

### TLAB không phải vùng “được miễn GC”

Một object cấp phát trong TLAB:

1. Là **Java heap object** nếu được materialize.
2. Có thể trở nên unreachable sau khi không còn references sống.
3. Có thể bị thu hồi hoặc di chuyển bởi GC theo collector.
4. Có thể được truy cập từ thread khác nếu reference được chia sẻ theo JMM.

Việc TLAB cấp phát nhanh **không** làm object thuộc “stack-local heap không bao giờ quét”. Collector vẫn phải đảm bảo tính đúng của object graph, roots, barriers và metadata.

### TLAB và ThreadLocal khác nhau

| Khái niệm | TLB? | Mục tiêu | Object có thể chia sẻ? |
| --- | --- | --- | --- |
| **TLAB** | Không phải CPU TLB | Tối ưu **cấp phát heap** theo thread context | **Có**, sau khi reference được chia sẻ |
| **`ThreadLocal<T>`** | Không phải TLAB | Lưu **value gắn với Java thread** qua các calls | Value vẫn là object Java và có thể escape |
| **CPU TLB (Translation Lookaside Buffer)** | Phần cứng MMU | Cache ánh xạ virtual → physical addresses | Không phải cơ chế cấp phát Java |
| **JVM stack** | Không phải heap TLAB | Chuỗi frames, locals/operand stacks | Frames theo thread riêng |

Vì các chữ viết tắt tương tự nhau, cần đọc đầy đủ: **Thread-Local Allocation Buffer** khác **Translation Lookaside Buffer** của CPU.

## 9. Escape analysis: thấy `new` nhưng không phải lúc nào cũng có allocation

JIT compiler có thể phân tích một object **có escape khỏi method/thread không** và có thể thay thế object bằng các giá trị trường riêng lẻ (**scalar replacement**) hoặc loại bỏ thao tác allocation khi không cần object materialized.

Ví dụ (đoạn method minh họa):

~~~java
static int compute(int input) {
    Point point = new Point(input, input + 1);
    return point.x + point.y;
}
~~~

Nếu không có observable escape, JIT có thể biến đường thực thi thành arithmetic tương đương:

~~~text
compute(input):
    result = input + (input + 1)
    return result
~~~

Ở mức **bytecode `javap`**, `new Point` vẫn có thể hiện diện. Ở mức optimized machine code, allocation **có thể không tồn tại**. Nhưng đây là **khả năng tối ưu**, không phải bảo đảm JIT luôn loại được mọi allocation của một object không escape.

**Đặc biệt trên HotSpot:** các tài liệu hiệu năng của Oracle mô tả scalar replacement là tối ưu loại bỏ heap allocation; **không nên khẳng định HotSpot mặc định “chuyển tất cả non-escaping objects sang stack”**. Escape analysis có thể giúp loại allocation hoàn toàn; nếu vẫn cần materialize, allocator có thể dùng TLAB hoặc đường khác.

### Phân biệt kết quả JIT và diễn giải source

| Source | Khả năng HotSpot tối ưu | Không bảo đảm |
| --- | --- | --- |
| `new Point(a,b)` chỉ đọc fields rồi return sum | Scalar replacement/loại allocation | Mỗi lần gọi đều được JIT compile ngay |
| `new Point(a,b)` và trả reference ra ngoài | Có thể cần materialize object | Luôn phải cấp ở TLAB; có thể đường khác |
| `new HugeArray[...]` | Có thể allocation ngoài TLAB/large-object path | Mọi array đều vào TLAB |
| `new Foo()` trong loop | Có thể nhiều allocations hoặc bị tối ưu | Số lần `new` source = số TLAB allocations chính xác |

## 10. Chương trình Java 17+: cấp phát từ hai threads

Ví dụ dưới đây giúp phân biệt **object trên heap dùng chung** với **quyền cấp phát có tính thread-local**. Nó có output xác định và **không** yêu cầu truy cập cấu trúc TLAB nội bộ.

Tạo file **`AllocationLab.java`**:

~~~java
public class AllocationLab {
    static final class Item {
        final int number;

        Item(int number) {
            this.number = number;
        }
    }

    private static long buildAndSum(int start) {
        Item[] items = new Item[2_000];

        for (int i = 0; i < items.length; i++) {
            items[i] = new Item(start + i);
        }

        long total = 0;
        for (Item item : items) {
            total += item.number;
        }
        return total;
    }

    public static void main(String[] args) throws InterruptedException {
        long[] result = new long[2];

        Thread first = new Thread(() -> result[0] = buildAndSum(0));
        Thread second = new Thread(() -> result[1] = buildAndSum(2_000));

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("first=" + result[0]);
        System.out.println("second=" + result[1]);
        System.out.println("sum=" + (result[0] + result[1]));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -g AllocationLab.java
java AllocationLab
~~~

**Stdout chính xác khi chương trình chạy bình thường:**

~~~text
first=1999000
second=5999000
sum=7998000
~~~

Giải thích:

- First thread cộng các số nguyên 0..1999: `(0 + 1999) * 2000 / 2 = 1_999_000`.
- Second thread cộng 2000..3999: `(2000 + 3999) * 2000 / 2 = 5_999_000`.
- Main `join` cả hai threads trước khi đọc `result[]`; do đó thứ tự output chỉ phụ thuộc main và các writes của workers đã hoàn tất.
- `Item[]` và từng `Item` có **ngữ nghĩa objects trên heap**. Trong HotSpot, TLAB có thể tối ưu nhiều allocations này, nhưng **stdout không đo TLAB refills hay số bytes đã cấp**.
- Cũng không được tự suy rằng mọi `new Item` thực sự tạo một allocation độc lập: JIT optimization tùy code shape và execution profile.

### So sánh chạy với TLAB bật và tắt

Trên HotSpot (nếu bản JVM hỗ trợ các flags), thử:

~~~bash
java -XX:+UseTLAB AllocationLab
java -XX:-UseTLAB AllocationLab
~~~

Cả hai lượt phải giữ **ngữ nghĩa chương trình** và in đúng ba dòng giá trị nói trên trong điều kiện chạy bình thường. Tuy nhiên:

- Khác biệt thời gian thực thi **không nhất thiết phản ánh lợi ích TLAB**, vì chương trình nhỏ chịu ảnh hưởng JIT warmup, startup, scheduling và escape-analysis.
- `-XX:-UseTLAB` chỉ thay đổi chiến lược cấp phát, **không** đổi việc objects thuộc Java heap.
- Không dùng output đúng/sai của chương trình để tuyên bố HotSpot đã chọn collector path nào cho mỗi object.

Để benchmark nghiêm túc, sử dụng **JMH**, chuẩn bị warmup/forks, kiểm soát GC, allocation rate, hardware và profiling. Không rút ra kết luận hiệu năng từ một phép lấy thời gian thủ công duy nhất.

## 11. Một ví dụ thứ hai: JIT có thể loại allocation của object không escape

Tạo file **`ScalarCandidate.java`**:

~~~java
public class ScalarCandidate {
    static final class Pair {
        final int left;
        final int right;

        Pair(int left, int right) {
            this.left = left;
            this.right = right;
        }
    }

    static int compute(int value) {
        Pair pair = new Pair(value, value + 1);
        return pair.left + pair.right;
    }

    public static void main(String[] args) {
        System.out.println("result=" + compute(7));
    }
}
~~~

~~~bash
javac ScalarCandidate.java
java ScalarCandidate
javap -c -p ScalarCandidate
~~~

**Stdout của chương trình (không tính phần output `javap`):**

~~~text
result=15
~~~

`javap` vẫn có thể hiển thị bytecode `new ScalarCandidate$Pair` bên trong `compute`. Nhưng khi method đủ “nóng” để JIT tối ưu, compiler **có thể** scalar-replace Pair và loại cấp phát ở machine code.

**Không thể chứng minh scalar replacement chỉ bằng output `result=15` hoặc bằng `javap -c`**. Để đo allocation thực tế, cần profiler, JFR hoặc tooling được cấu hình phù hợp và xét compilation state. Không khẳng định method đơn giản này chắc chắn được optimized sau một lần gọi.

## 12. Quan sát TLAB bằng HotSpot flags và unified logging

Oracle JDK/HotSpot hiện đại hỗ trợ:

| Flag hoặc công cụ | Công dụng | Lưu ý |
| --- | --- | --- |
| `-XX:+UseTLAB` | Bật Thread-Local Allocation Buffers | Trên HotSpot thường **bật mặc định** |
| `-XX:-UseTLAB` | Tắt cơ chế này để so sánh/điều tra | Có thể làm allocation chậm; không phải cấu hình production mặc định được khuyến nghị |
| `-Xlog:gc+tlab=trace` | Yêu cầu logging chi tiết các sự kiện/thống kê TLAB nếu tag/mức được JVM hỗ trợ | Output phụ thuộc collector, workload, version; rất nhiều log |
| `-Xlog:gc+tlab=debug` | Thử mức log ít chi tiết hơn | Không bảo đảm có dòng log nếu chưa có sự kiện/mốc GC tương ứng |
| `-XX:+PrintFlagsFinal` | Liệt kê flags HotSpot và giá trị hiện hành | Không đo các allocations cụ thể |
| **JFR** | Thu thập allocation events tùy cấu hình | Event selection/sampling phải được hiểu đúng; không mặc định đếm đầy đủ từng object |
| **JMH** | Benchmark JVM có warmup/forks | Không tự đo TLAB chỉ từ một con số ns/op |

Các lệnh thử trên HotSpot JDK 17+:

~~~bash
java -Xlog:help
java -XX:+PrintFlagsFinal -version
java -Xlog:gc+tlab=trace AllocationLab
~~~

**Chú ý:** flag/logging không phải API portable của Java language. Trên JVM không phải HotSpot, lệnh có thể bị từ chối. Khi `-Xlog:gc+tlab=trace` tạo nhiều output, đừng lẫn log diagnostic với ba dòng stdout của chương trình.

Để lọc `UseTLAB` trong terminal:

~~~bash
# Linux/macOS shell:
java -XX:+PrintFlagsFinal -version 2>&1 | grep UseTLAB
~~~

PowerShell/Windows:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String "UseTLAB"
~~~

### Diễn giải thống kê TLAB

Tùy phiên bản HotSpot, log của `gc+tlab` có thể nhắc tới:

- **Refills**: bao nhiêu lần cần đổi TLAB.
- **Slow allocs**: những allocations cần nhánh chậm theo cách VM thống kê.
- **Refill waste**: dung lượng còn thừa bị bỏ khi TLAB retire/refill.
- **GC waste**: space không dùng hết khi GC thu thập thống kê/đóng TLAB phù hợp.
- **Desired size**: dung lượng TLAB mà VM đang nhắm tới theo policy.

Không suy rằng một dòng `refills: 3` nghĩa JVM chỉ tạo **ba objects**. Mỗi TLAB chứa nhiều allocations, và ngoài TLAB có thể còn đường khác. TLAB statistics cũng có thể được in **theo GC/event** thay vì một con số tổng đời process, và JIT elimination có thể làm giảm allocations quan sát.

### JFR và allocation events

Java Flight Recorder có các event names liên quan allocation, chẳng hạn **`jdk.ObjectAllocationInNewTLAB`** và **`jdk.ObjectAllocationOutsideTLAB`** trên các bản JDK hỗ trợ. Cấu hình recording quyết định event nào được bật, có sampling hoặc threshold gì. Đừng diễn giải số events như “chính xác bằng số `new` source đã chạy” nếu chưa kiểm tra setting.

Một lựa chọn để khám phá event support:

~~~bash
jfr help
java -XX:StartFlightRecording=duration=10s,filename=allocation.jfr AllocationLab
~~~

**Với `AllocationLab` chạy quá ngắn**, recording 10 giây có thể không đủ workload dài để quan sát nhiều allocation samples. Lệnh này chỉ minh họa cách bật recording trên JDK có JFR; không bảo đảm tất cả event loại allocation tự động được thu và không dùng để kết luận TLAB size. Dùng một workload đủ dài/đã warmup và cấu hình event phù hợp nếu làm profiling thực sự.

## 13. Khi nào Fast Path không đại diện cho toàn bộ allocation?

Các điều kiện có thể khiến allocation **không** đi qua bump pointer nhanh trong TLAB:

1. **Object quá lớn** hoặc không phù hợp TLAB size/refill policy.
2. **TLAB không đủ chỗ**, cần refill/retire.
3. **Collector-specific slow path**: vùng cấp phát không sẵn, cần phối hợp GC/refill hoặc allocation ngoài vùng mặc định.
4. **Instrumentation/profiling**: JVMTI/JFR sampling và các yêu cầu observability có thể tác động allocation path.
5. **JIT chưa compile hoặc đã deoptimize**: interpreter, C1, C2 có thể có đường thực thi khác.
6. **Escape analysis loại allocation**: khi không còn allocation thực, “fast vs slow” không còn áp dụng cho object đó.
7. **VM flags**: `UseTLAB` bị tắt hoặc chính sách collector khác.

Đừng rút ra từ số byte còn trống của TLAB rằng “vùng heap không còn memory”. TLAB có thể hết chỗ khi heap tổng thể còn rất nhiều capacity; refill giúp lấy buffer mới từ phần heap thích hợp. Ngược lại, còn vài byte trong TLAB không bảo đảm JVM có thể đáp ứng object rất lớn.

## 14. “Con trỏ” của HotSpot không phải con trỏ của mã Java

Bump pointer `top` là một address/offset mà **VM allocator quản lý nội bộ**. Java source không có toán tử pointer arithmetic như C/C++. Java references là giá trị có kiểu và các phép toán hợp lệ theo JVM, có thể trải qua GC relocation/barriers.

Quan sát:

~~~java
Object a = new Object();
Object b = new Object();
System.out.println(a == b);
~~~

Khi đặt trong một chương trình có `main`, dòng này in `false` vì hai lần `new Object()` tạo hai identities khác nhau theo ngữ nghĩa Java, dù VM có thể optimize trong trường hợp cụ thể mà không đổi kết quả. **Không suy khoảng cách địa chỉ giữa a và b** từ `==`. Cũng không đọc `System.identityHashCode` rồi coi đó là memory address.

### TLAB không phá vỡ Java Memory Model

Nếu Thread A tạo và công bố object cho Thread B:

~~~text
Thread A:
  - allocate object (có thể qua TLAB A)
  - initialize fields
  - publish reference theo cơ chế thread-safe

Thread B:
  - nhận reference
  - truy cập cùng object
~~~

TLAB chỉ tối ưu **chỗ cấp phát ban đầu**. Nó không cho phép B tự động đọc fields mà A đã ghi nếu cách publication/synchronization không đúng quy tắc. Hãy dùng `volatile`, `synchronized`, concurrent collections, final field semantics hoặc các cơ chế happens-before thích hợp.

TLAB cũng không bảo đảm object chỉ được phép dùng từ thread cấp phát; Java heap **chia sẻ giữa các JVM threads**, theo JVMS `2.5.3.

## 15. Tối ưu thực tế: khi nào cần để ý TLAB?

Những câu hỏi có giá trị trước khi can thiệp VM flags:

- Allocation rate có thật sự cao? GC pause, object churn hay CPU bị giới hạn ở đâu?
- Object lớn hay nhiều object nhỏ? Có pattern allocation đột biến theo threads?
- Profiling có cho thấy TLAB refill/waste hoặc outside-TLAB allocations đáng kể?
- JIT đã warmup và allocation có bị scalar-replaced không?
- Bản Java, GC và host architecture có phù hợp với assumption benchmark không?
- Vấn đề thực tế là allocation throughput, GC memory pressure hay synchronization trên shared object?

**Không nên tự động tắt TLAB khi thấy một ít “waste”.** Trade-off thường là: cho mỗi thread một vùng allocation riêng để tránh tranh chấp, đổi lại có thể có unused tail space/refill overhead. Hiệu quả thực cần đánh giá bằng workload thực, không bằng một thông số đơn lẻ.

### Mô hình so sánh

| Cấp phát qua TLAB fast path | Cấp phát ngoài TLAB / slow path |
| --- | --- |
| Có vùng per-execution-thread còn đủ chỗ | TLAB hết chỗ, object lớn, TLAB disabled hoặc chính sách khác |
| Bump pointer cục bộ, thường ít contention | Có thể cần coordination/CAS, refill, collector-specific logic |
| Fast path có thể được inline tối ưu | Thường nhiều checks và bookkeeping hơn |
| Vẫn cần object initialization và GC correctness | Cũng phải tuân thủ object initialization và GC correctness |
| Vẫn là object trên Java heap | **Cũng là object trên Java heap** |

Không diễn giải bảng thành đo đạc tốc độ cố định, ví dụ “TLAB luôn nhanh hơn N lần”; JDK, collector, CPU, kích thước objects và contention đều ảnh hưởng.

## 16. Những lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “TLAB là một phần JVM stack của thread.” | TLAB là **buffer trong Java heap** dành cho thread context cấp phát. |
| “Object cấp phát trong TLAB không thể được thread khác truy cập.” | Vẫn có thể chia sẻ reference và truy cập object theo Java Memory Model. |
| “`ThreadLocal<T>` dùng TLAB để giữ value riêng.” | ThreadLocal là API value per Java thread, không đồng nghĩa TLAB. |
| “TLAB là CPU TLB.” | TLAB = Thread-Local Allocation Buffer; CPU TLB là Translation Lookaside Buffer. |
| “TLAB nghĩa mỗi `new` không cần bất kỳ synchronization ở mọi nhánh.” | TLAB fast path giảm contention; refill/slow path/GC vẫn cần phối hợp. |
| “Cứ đầy TLAB là JVM hết heap.” | Có thể refill từ heap khi còn nguồn memory. |
| “Object lớn luôn nằm trong TLAB.” | Có thể cấp outside TLAB hoặc qua đường khác. |
| “TLAB chỉ cấp phát objects trong young Eden ở mọi JVM mọi GC.” | Nhiều collector có chính sách/regions khác nhau; không phải luật JVMS. |
| “TLAB size cố định cho toàn bộ luồng.” | HotSpot có adaptive sizing và thresholds. |
| “Bump pointer chỉ tăng `top`; không có object header/zeroing.” | Cấp phát hợp lệ còn có preparation/header/alignment và GC requirements. |
| “Thấy `new` trong `javap` thì chắc chắn có một heap allocation.” | JIT có thể scalar-replace hoặc loại allocations. |
| “Escape analysis HotSpot chuyển mọi object không escape lên stack.” | HotSpot thường dùng scalar replacement để loại allocation; không hứa stack allocation tổng quát. |
| “Tắt TLAB sẽ làm Java source output khác.” | `-XX:-UseTLAB` đổi strategy allocation, không đổi Java semantics. |
| “Chỉ cần một lần đo `System.nanoTime` là biết TLAB giúp bao nhiêu.” | Phải xét warmup, JIT, GC, benchmark framework và workload. |
| “`System.identityHashCode` là địa chỉ object sau cấp phát.” | Không; identity hash không phải địa chỉ native. |
| “Một virtual thread luôn giữ một TLAB riêng không đổi.” | Cơ chế gắn với execution/carrier threads tùy HotSpot; không nên tuyệt đối hóa. |
| “TLAB waste là memory leak không thể GC.” | Thường là internal allocation fragmentation/accounting, không tương đương Java reference leak. |
| “Bump pointer tồn tại trong JVMS như một opcode.” | Không; đó là chi tiết implementation phía dưới bytecode `new`. |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** TLAB thuộc JVM stack hay heap?  
**Đáp án:** Thuộc **Java heap** theo HotSpot allocation strategy; nó là vùng **tạm được thread sử dụng để cấp object**, không phải call stack.

**Câu 2.** Fast path bump pointer cần hai thông tin quan trọng nào?  
**Đáp án:** Vị trí hiện tại `top` và giới hạn `end`, cùng object aligned size để kiểm tra còn đủ chỗ và cập nhật `top`.

**Câu 3.** Vì sao TLAB giảm contention trong nhiều luồng?  
**Đáp án:** Các luồng dùng các allocation pointers cục bộ cho nhiều objects nhỏ, thay vì tranh chấp một global pointer cho mọi object.

**Câu 4.** Khi TLAB còn 48B mà object cần 256B, VM có chắc chắn ném OOME không?  
**Đáp án:** Không. VM có thể refill TLAB hoặc allocate outside TLAB nếu heap có nguồn cấp phát phù hợp.

**Câu 5.** Có thể chia sẻ object được cấp từ TLAB A cho Thread B không?  
**Đáp án:** Có. Object thuộc Java heap; cần publication/synchronization đúng JMM để bảo đảm visibility và safety khi chia sẻ mutable data.

**Câu 6.** Có phải mọi `new` luôn đi qua TLAB?  
**Đáp án:** Không. Có outside-TLAB allocation, slow path, TLAB disabled hoặc JIT có thể loại allocation.

**Câu 7.** Vì sao `javap -c` không chứng minh TLAB allocation đang dùng?  
**Đáp án:** `javap` hiển thị JVM bytecode, không hiển thị internal allocation path trong HotSpot/JIT machine code.

**Câu 8.** Có cần interpreter hay compiler gọi Java constructor trước khi memory cho object đã được cấp hợp lệ không?  
**Đáp án:** Constructor chỉ có thể chạy sau khi object đã được tạo/chuẩn bị phù hợp theo semantics; allocation và constructor invocation là các bước phân biệt.

**Câu 9.** `UseTLAB` là yêu cầu của JVMS cho mọi JVM implementation?  
**Đáp án:** Không. Đây là flag/technique của HotSpot; JVM khác có thể chọn allocator khác.

**Câu 10.** `ScalarCandidate.compute(7)` luôn tạo một Pair object thật?  
**Đáp án:** Không thể bảo đảm: JIT có thể scalar-replace nếu đủ điều kiện, nhưng cũng có thể tạo object tùy compilation state.

**Câu 11.** JFR ghi 100 allocation events có nghĩa source chỉ chạy 100 `new`?  
**Đáp án:** Không. Event configuration/sampling và allocation elimination làm số event không đồng nghĩa số biểu thức `new` thực thi.

**Câu 12.** Có nên đổi `-XX:-UseTLAB` trên production chỉ vì thấy một phần refill waste không?  
**Đáp án:** Không. Cần đo workload thực, GC, throughput và contention trước khi can thiệp allocation policy.

## 18. Nguồn chính thức để tìm hiểu sâu

- [JVMS Java SE 25 — `2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): Java heap chứa instances/arrays dùng chung, không quy định thuật toán cấp phát TLAB.
- [JVMS Java SE 25 — `6.5 Instructions](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): opcode `new`, `newarray`, `anewarray` và ngữ nghĩa khởi tạo/lệnh JVM.
- [Oracle JDK 25 — `java` launcher command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): documented HotSpot flags `-XX:+UseTLAB` và `-XX:-UseTLAB`.
- [OpenJDK HotSpot — `threadLocalAllocBuffer.hpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/threadLocalAllocBuffer.hpp): interface và state nội bộ TLAB.
- [OpenJDK HotSpot — `threadLocalAllocBuffer.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/threadLocalAllocBuffer.cpp): refill, resize, accounting, waste và logging.
- [OpenJDK HotSpot — `memAllocator.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/memAllocator.cpp): các đường allocation inside/outside TLAB, slow path.
- [Oracle — Memory Management in Java HotSpot VM](https://www.oracle.com/technetwork/java/javase/tech/memorymanagement-whitepaper-1-150020.pdf): giải thích lịch sử bump-pointer allocation và lý do TLAB giảm contention; nội dung collector của whitepaper cũ không nên coi là hiện trạng mọi JDK.
- [Oracle — Java HotSpot VM Performance Enhancements](https://docs.oracle.com/en/java/javase/22/vm/java-hotspot-virtual-machine-performance-enhancements.html): escape analysis và scalar replacement, các tối ưu allocation.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): framework benchmark JVM có warmup/forks đúng phương pháp.
- [JDK 25 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/): công cụ và API flight recording, quan sát events khi được bật.

**Tóm tắt một câu:** HotSpot thường cấp object nhanh bằng **bump pointer trong TLAB — một đoạn của heap được trao cho một execution thread**, nên phần lớn allocations nhỏ không phải tranh chấp global allocation pointer; khi hết chỗ hoặc không đủ điều kiện VM chuyển sang refill/outside-TLAB/slow path, còn GC, object initialization và Java Memory Model vẫn phải được tuân thủ.