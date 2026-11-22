# Nhận diện Cleaner như cơ chế hỗ trợ có giới hạn

## 1. Cleaner giải quyết vấn đề gì?

Trong Java, **garbage collector (GC)** quản lý bộ nhớ của các đối tượng Java mà chương trình không còn sử dụng. Tuy nhiên, GC không trực tiếp đảm bảo giải phóng **tài nguyên bên ngoài heap Java** vào đúng thời điểm ứng dụng cần, chẳng hạn file descriptor, socket, native memory, con trỏ thư viện native hoặc các handle của hệ điều hành.

Một đối tượng quản lý tài nguyên có thể không còn được tham chiếu nhưng tài nguyên hệ điều hành vẫn chưa được đóng. Nếu chương trình tạo nhiều tài nguyên rồi chờ GC, số lượng handle có thể cạn trước khi JVM cần hoặc kịp thu gom heap.

Từ Java 9, `java.lang.ref.Cleaner` cho phép **đăng ký một hành động dọn dẹp** (cleaning action) gắn với trạng thái có thể thu gom của một đối tượng. Cleaner là một cơ chế dự phòng hữu ích trong một số thư viện quản lý tài nguyên; **không phải lịch trình đóng tài nguyên đáng tin cậy**.

Quy tắc cốt lõi:

> Tài nguyên cần được đóng đúng thời điểm thì dùng `AutoCloseable`, `close()` và `try-with-resources`. Cleaner chỉ có thể làm lớp hỗ trợ khi lập trình viên bỏ sót đường đóng rõ ràng, với những giới hạn phải được chấp nhận.

### Ba việc khác nhau dễ bị nhầm

| Cơ chế | Trách nhiệm | Điều không nên giả định |
| --- | --- | --- |
| GC | Thu hồi bộ nhớ do JVM quản lý khi đối tượng không còn cần thiết | GC sẽ gọi `close()` hoặc đóng handle OS ngay lập tức |
| `AutoCloseable` / `try-with-resources` | Thể hiện quyền sở hữu và đóng tài nguyên ở điểm xác định trong luồng điều khiển | Bảo vệ được tài nguyên nếu hoàn toàn bỏ qua đường `close()` |
| `Cleaner` | Đăng ký một hành động có thể chạy khi đối tượng trở thành **phantom reachable**, hoặc chạy khi gọi `Cleanable.clean()` | Hành động chắc chắn chạy đúng hạn, chạy khi thoát JVM, hoặc thay thế cho đóng rõ ràng |

Cleaner được xây dựng trên cơ chế `PhantomReference` và `ReferenceQueue`. Người học ở cấp này chỉ cần nắm quan hệ **object mất khả năng được truy cập → JVM có thể thông báo qua cơ chế tham chiếu → hành động dọn dẹp có cơ hội chạy**; không cần tự triển khai hàng đợi tham chiếu để sử dụng API.

## 2. Vòng đời của một đăng ký Cleaner

Các thành phần chính của API:

- `Cleaner.create()` tạo một bộ quản lý cleaning actions.
- `cleaner.register(referent, action)` đăng ký **đối tượng được theo dõi** (referent) và một `Runnable` dọn dẹp; trả về `Cleaner.Cleanable`.
- `cleanable.clean()` yêu cầu thực hiện hành động dọn dẹp **ngay khi gọi**, nếu hành động đó chưa được thực hiện.
- Nếu không gọi `clean()`, Cleaner **có thể** chạy hành động sau khi đối tượng được theo dõi trở thành phantom reachable và Cleaner được thông báo.
- Một cleaning action được thực hiện **tối đa một lần** theo đăng ký: gọi lại `clean()` không khiến cùng hành động chạy lần thứ hai.

Luồng sử dụng khuyến nghị:

~~~text
Tạo đối tượng quản lý tài nguyên
        |
        v
Đăng ký Cleaner(referent, cleanupState)
        |
        +--> Đường bình thường: try-with-resources / close()
        |                     |
        |                     v
        |               Cleanable.clean()
        |               chạy hành động dọn dẹp
        |
        +--> Đường bị bỏ quên close():
                              |
                              v
                 Đối tượng không còn reachable
                              |
                              v
                 GC/Cleaner có thể kích hoạt
                 cleaning action sau một thời gian
                 KHÔNG XÁC ĐỊNH, hoặc không chạy
                 trước khi tiến trình kết thúc
~~~

Từ “có thể” là quan trọng: **không có SLA, thời hạn tối đa hay bảo đảm sẽ được chạy trước khi JVM dừng**. Nếu không có áp lực bộ nhớ heap, GC có thể chưa xử lý đối tượng trong một khoảng thời gian dài, trong khi số lượng file/socket/native handle đã tăng quá mức.

Cleaner thường dùng thread daemon để xử lý tự động. Hành động nền nên **ngắn, không chặn lâu**, không phụ thuộc thread ứng dụng hay cần tương tác UI. Hành động dọn dẹp lỗi không phải kênh báo lỗi nghiệp vụ đáng tin: ngoại lệ do cleaning action ném ra bị cơ chế Cleaner bỏ qua; cần thiết kế quan sát lỗi tài nguyên qua đường đóng chủ động.

## 3. Ví dụ Java 17+: close() chủ động, Cleaner dự phòng

Ví dụ sau **mô phỏng** một tài nguyên bằng ID số nguyên. Nó ghi log để minh họa đúng thời điểm dọn dẹp; **không mở hay giải phóng tài nguyên hệ điều hành thật**. Cách viết quan trọng là đặt dữ liệu cần cleanup trong **lớp tĩnh `State` độc lập với đối tượng được theo dõi**.

Lưu thành file **CleanerDemo.java**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanerDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    // Chỉ giữ dữ liệu cần cleanup; KHÔNG giữ tham chiếu tới Handle.
    private static final class State implements Runnable {
        private final int id;
        private final AtomicBoolean released = new AtomicBoolean();

        State(int id) {
            this.id = id;
            System.out.println("open " + id);
        }

        void requireOpen() {
            if (released.get()) {
                throw new IllegalStateException("resource closed");
            }
        }

        @Override
        public void run() {
            // Mô phỏng thao tác giải phóng tài nguyên ngoài heap.
            if (released.compareAndSet(false, true)) {
                System.out.println("release " + id);
            }
        }
    }

    private static final class Handle implements AutoCloseable {
        private final State state;
        private final Cleaner.Cleanable cleanable;

        Handle(int id) {
            this.state = new State(id);
            this.cleanable = CLEANER.register(this, state);
        }

        void use() {
            state.requireOpen();
            System.out.println("use " + state.id);
        }

        @Override
        public void close() {
            // Chủ động cleanup khi người dùng đóng Handle.
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Handle handle = new Handle(7)) {
            handle.use();

            // Gọi nhiều lần không chạy lại cùng cleaning action.
            handle.close();
            handle.close();
        } // try-with-resources tự gọi close() thêm một lần.

        System.out.println("done");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CleanerDemo.java
java CleanerDemo
~~~

Kết quả **xác định của đường đóng chủ động**:

~~~text
open 7
use 7
release 7
done
~~~

Giải thích:

1. `new State(7)` tạo trạng thái độc lập cần thiết cho cleanup và in `open 7`.
2. `CLEANER.register(this, state)` theo dõi đối tượng `Handle`, còn `state` chỉ lưu ID và trạng thái đã giải phóng.
3. `handle.close()` gọi `cleanable.clean()` trực tiếp, nên `release 7` xuất hiện trước `done`. Mọi lần gọi `clean()` tiếp theo trên cùng đăng ký không chạy lại action.
4. `AtomicBoolean.compareAndSet(false, true)` giúp minh họa tính đơn lần ở tầng trạng thái và tránh thực hiện phần release hai lần nếu logic ứng dụng cũng cần phòng vệ. Bản thân `Cleanable` đã bảo đảm hành động đăng ký được gọi tối đa một lần.
5. `try-with-resources` vẫn là cơ chế chịu trách nhiệm đóng trong luồng bình thường. Dù thân `try` có lỗi, Java vẫn cố gọi `close()` khi ra khỏi khối.

Ví dụ không chờ GC và không dựa vào Cleaner chạy nền; nhờ vậy stdout kiểm chứng được. Trong mã sản xuất, phần mô phỏng `System.out.println("release " + id)` cần được thay bằng logic giải phóng tài nguyên thật, với quy tắc sở hữu, tính an toàn khi lỗi và thread safety phù hợp.

**Đừng viết unit test đợi `System.gc()` rồi khẳng định Cleaner bắt buộc phải chạy.** `System.gc()` chỉ là yêu cầu để JVM cân nhắc thực hiện GC, không bảo đảm cleaning action hoàn tất hoặc được gọi trong thời hạn kiểm thử.

## 4. Bẫy quan trọng nhất: hành động dọn dẹp giữ tham chiếu ngược

Đối tượng được đăng ký phải có cơ hội **không còn reachable** thì đường Cleaner tự động mới có thể hoạt động. Nếu chính cleaning action giữ tham chiếu mạnh tới đối tượng ấy, vòng đời bị kéo dài và action không được kích hoạt tự động.

**Ví dụ sai — chỉ để minh họa anti-pattern, không dùng trong sản xuất:**

~~~java
// Trong class Handle:
cleanable = CLEANER.register(this, () -> {
    // Đọc trường qua "this" làm lambda giữ Handle.
    System.out.println(this.state);
});
~~~

Vì lambda trên bắt giữ `this`, Cleaner lại có tham chiếu tới chính đối tượng đang được theo dõi. `Handle` không đạt trạng thái cần thiết để Cleaner tự xử lý. Tình trạng này có thể tạo ra leak ngầm kéo dài.

Những cách dễ vô tình giữ referent:

- `Runnable` là **non-static inner class** của đối tượng được theo dõi: class lồng không tĩnh thường giữ tham chiếu tới instance bên ngoài.
- Lambda gọi instance method hoặc truy cập trường qua `this`.
- `State` gián tiếp giữ đối tượng ngoài qua một collection, callback, listener hoặc đối tượng khác.

**Mẫu an toàn:** dùng `static nested class State implements Runnable` hoặc một hành động độc lập, chỉ chứa **thông tin thực sự cần để giải phóng tài nguyên**, không trỏ trở lại đối tượng đăng ký. Nếu `State` giữ một tài nguyên khác, cần kiểm tra chính tài nguyên ấy không gián tiếp giữ `Handle`.

Lưu ý thêm: đối tượng được theo dõi và trạng thái cleanup được tách ra không đồng nghĩa có thể giải phóng an toàn bất cứ lúc nào. Với native handle còn được dùng trong một thao tác dài, việc đồng bộ đóng/sử dụng, tính hợp lệ của handle và khi cần `Reference.reachabilityFence(...)` là những vấn đề riêng phải thiết kế cẩn thận.

## 5. Giới hạn cần ghi nhớ trước khi lựa chọn Cleaner

### 5.1. Không xác định thời gian

Trạng thái đối tượng trở thành phantom reachable **không đồng nghĩa** action chạy ngay. Thời điểm GC chạy, thời điểm đối tượng được xử lý trong reference queue và thời điểm thread Cleaner thi hành đều không phải lịch do mã nghiệp vụ kiểm soát.

Hậu quả thực tế: file descriptor/native memory có thể cạn trước khi Cleaner kịp xử lý. Không thiết kế giới hạn kết nối, số file mở hay dung lượng bộ nhớ native dựa vào một lời hứa “GC sẽ tự dọn sớm”.

### 5.2. Không bảo đảm khi tiến trình kết thúc

Với `System.exit(...)`, hành vi các cleaner phụ thuộc implementation; API không bảo đảm action được gọi. Khi JVM bị kill, máy mất điện hoặc hệ điều hành kết thúc tiến trình đột ngột, càng không thể đòi hỏi callback Java được chạy.

Không dùng Cleaner làm nơi duy nhất ghi giao dịch, gửi sự kiện quan trọng, flush dữ liệu cần bảo đảm hay cam kết phát hành lock tài nguyên ở thời điểm cụ thể.

### 5.3. Chạy ngoài luồng nghiệp vụ

Hành động tự động thường chạy trên thread do Cleaner quản lý. Không mặc định thread đó có transaction context, request context, MDC logging, UI thread, quyền truy cập thread-local hay dependency đang hoạt động như lúc mở tài nguyên.

Hành động cần ngắn, độc lập và an toàn khi có nhiều cleanup chạy đồng thời. Action bị chặn lâu có thể trì hoãn các action khác cùng cleaner. Nếu dọn dẹp cần I/O đáng tin, retry có kiểm soát, lỗi báo về caller hoặc thứ tự xác định, hãy dùng cơ chế quản lý vòng đời chủ động.

### 5.4. Khó quan sát lỗi và kiểm thử

Không nên trông đợi exception từ hành động tự động xuất hiện trong luồng caller. Cleaner sẽ bỏ qua exception do action ném ra; điều này khiến cleanup thất bại có thể khó phát hiện và làm tăng nguy cơ leak.

Kiểm thử hành vi chính nên gọi `close()`, xác minh giải phóng tài nguyên đúng một lần, và thử cả đường xử lý ngoại lệ của `try-with-resources`. Không viết test dựa vào thời gian GC hoặc thứ tự thread Cleaner; nếu cần kiểm tra logic action, hãy tách logic đó và chạy trực tiếp trong test.

### 5.5. Cleaner không quản lý được tất cả tài nguyên

Với kết nối, file, transaction, executor, subscription hoặc lock có quy tắc lifetime rõ ràng, **API đóng/hủy tường minh vẫn là nguồn kiểm soát chính**. Đặc biệt các thao tác cần commit/rollback, flush có bảo đảm hoặc trả kết nối vào pool đúng lúc không phù hợp làm cleanup trì hoãn tùy ý.

Cleaner cũng không có nghĩa là bất cứ `Runnable` nào cũng an toàn để chạy ở nền. Nó cần kiểm tra ownership, khả năng idempotent, concurrency và tham chiếu không giữ lại referent.

## 6. Lựa chọn đúng cơ chế theo loại tài nguyên

| Tình huống | Hướng xử lý ưu tiên | Vai trò của Cleaner |
| --- | --- | --- |
| Đọc file hoặc truy cập socket trong một scope | `try-with-resources` quanh `AutoCloseable` | Thường không cần viết Cleaner riêng |
| Tài nguyên theo vòng đời service/application | Đóng trong lifecycle hook rõ ràng hoặc `close()` của owner | Không thay thế shutdown/lifecycle logic |
| Native handle được wrapper Java sở hữu | API `close()` rõ ràng, cùng chính sách ownership | Có thể cân nhắc fallback nếu bỏ quên close |
| Transaction, database connection, lock | Commit/rollback/release tại phạm vi nghiệp vụ quy định | Không được xem như cơ chế đảm bảo thời gian |
| Đối tượng chỉ chứa dữ liệu Java thông thường | Để GC quản lý bộ nhớ | Thường không cần Cleaner |
| Thu thập telemetry/log khi object bị GC | Chỉ dùng nếu hoàn toàn chấp nhận tính không chắc chắn | Không dùng làm nguồn số liệu bắt buộc chính xác |

Với thư viện wrapper tài nguyên native, thiết kế phổ biến là **một đường cleanup chung** được dùng bởi cả `close()` chủ động và fallback Cleaner. Việc này có thể giảm trùng logic giải phóng; tuy nhiên vẫn phải tránh tham chiếu ngược và đảm bảo hành động có thể chạy từ nhiều ngữ cảnh thread.

## 7. Cleaner và finalize(): có liên quan nhưng không đồng nhất

Java cũ từng dùng `Object.finalize()` để chạy một phương thức khi đối tượng chuẩn bị được thu gom. Finalization có nhiều vấn đề về khả năng dự đoán, độ tin cậy, hiệu năng và an toàn; `finalize()` đã **deprecated for removal**. Mã Java mới không nên dựa vào nó.

Cleaner là API có cấu trúc tách action ra khỏi đối tượng được theo dõi, tránh nhiều vấn đề của finalization và cho phép **gọi `clean()` chủ động**. Tuy nhiên Cleaner **không khắc phục bản chất không xác định của GC**. Vì vậy:

- Không đổi máy móc mỗi `finalize()` thành một Cleaner rồi tiếp tục bỏ quên `close()`.
- Trước hết xác định ai sở hữu tài nguyên và khi nào phải kết thúc lifetime.
- Ưu tiên `AutoCloseable` / `try-with-resources`. Chỉ bổ sung Cleaner khi có lý do fallback cụ thể và chấp nhận giới hạn.

Cleaner không “chạy destructor kiểu C++”. Java không có destructor tự động theo scope với ngữ nghĩa giống RAII; `try-with-resources` là cách biểu đạt đóng tài nguyên có tính xác định trong Java.

## 8. Tình huống áp dụng: xét đúng bản chất yêu cầu

**Tình huống A — xử lý tệp báo cáo.** Chương trình mở file, ghi dữ liệu và phải bảo đảm đóng/flush trước khi báo “đã xuất xong”. Cleaner không phù hợp làm đường chính: tài nguyên phải đóng sau scope `try-with-resources`; lỗi I/O cần được quan sát và xử lý.

**Tình huống B — wrapper JNI giữ con trỏ native.** Code người dùng đôi lúc quên gọi `close()`, gây nguy cơ thất thoát native memory. Một Cleaner có thể làm dự phòng khi wrapper không còn reachable, nhưng wrapper vẫn phải có đường close xác định, state cleanup không giữ wrapper, và thư viện phải chấp nhận việc fallback có thể chậm hoặc không chạy trước khi tiến trình kết thúc.

**Tình huống C — dịch vụ giữ connection pool.** Pool cần khởi tạo, dùng và shutdown theo lifecycle của ứng dụng; Cleaner không biết lúc nào ứng dụng chuẩn bị dừng, không đảm bảo đóng thứ tự, và không thay thế hook đóng pool.

**Tình huống D — tác vụ cần ghi audit bắt buộc.** Không đăng ký gửi audit làm cleaning action: nếu JVM kết thúc, action có thể không chạy; nếu action lỗi, ngoại lệ không đến business flow. Ghi audit trong đường giao dịch hoặc một cơ chế giao nhận đáng tin cậy.

## 9. Lỗi phổ biến khi dùng Cleaner

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cho rằng `System.gc()` gọi Cleaner đúng hạn | Test và logic phụ thuộc GC không ổn định | Kiểm thử `close()`; tránh ép GC như lời bảo đảm |
| Chỉ có Cleaner, không có `close()` | Tài nguyên không được giải phóng theo lifetime mong muốn | Thiết kế `AutoCloseable` và owner rõ ràng |
| Action là lambda bắt giữ `this` | Referent bị giữ sống, fallback khó hoặc không chạy | `static State` độc lập, không tham chiếu ngược |
| Cleanup mất nhiều thời gian hoặc chờ vô hạn | Chặn việc xử lý action khác | Giữ action nhanh, tách thao tác nghiệp vụ |
| Chuyển ngoại lệ cleanup thành “đã thành công” | Lỗi bị che khuất | Chủ động close ở nơi có thể báo lỗi |
| Dùng Cleaner để thay `finally`/try-with-resources | Không đảm bảo đóng sau scope | Đóng rõ ràng trong đường thực thi chính |
| Tạo một cleaner/thread cho mỗi instance mà không cần | Tăng overhead quản lý | Cân nhắc chia sẻ Cleaner ở phạm vi thư viện hoặc lớp |
| Giải phóng native handle khi thao tác khác vẫn dùng | Lỗi truy cập tài nguyên, race | Thiết kế đồng bộ, ownership và lifetime nhất quán |

## 10. Câu hỏi tự kiểm tra

**1. Tạo `Cleaner.Cleanable` có khiến tài nguyên được đóng sau khi scope kết thúc không?**

Không. Hết scope không bảo đảm đối tượng ngay lập tức phantom reachable hay action chạy. Chỉ `close()`/`clean()` chủ động mới thực hiện đường cleanup ngay theo lời gọi.

**2. Tại sao state của action không được chứa `this`?**

Vì action có thể giữ mạnh tham chiếu tới referent, ngăn chính referent trở thành phantom reachable; như vậy fallback tự động không được kích hoạt.

**3. Có thể thay `try-with-resources` bằng Cleaner cho file output cần flush không?**

Không. Flush/đóng file cần xảy ra ở thời điểm xác định và lỗi phải được quan sát; dùng `try-with-resources`.

**4. Gọi `cleanable.clean()` hai lần có chạy action hai lần không?**

Không. Một action đã được thực thi thì không chạy lại qua cùng `Cleanable`.

**5. Nên ghi nhớ Cleaner theo một câu nào?**

Cleaner là **đường dọn dẹp dự phòng mang tính cơ hội**, không phải cơ chế cam kết hoàn tất cleanup đúng thời điểm. Đối với tài nguyên có vòng đời xác định, dùng owner + `AutoCloseable` + `try-with-resources` làm thiết kế chính.

## Tài liệu tham khảo chính thức

- [Java SE 21 — java.lang.ref.Cleaner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Java SE 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 21 — Object.finalize() (deprecated for removal)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#finalize())
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421)