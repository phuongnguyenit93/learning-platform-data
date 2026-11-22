# Safe publication và nguy cơ đọc đối tượng khởi tạo dở trong Java

> **Trọng tâm:** Tạo được một object đúng trong một thread **chưa đủ** để thread khác quan sát object đó đúng. Cần **safe publication**: đưa tham chiếu đến object cho thread khác qua một cơ chế đồng bộ có hợp đồng *happens-before*. Nếu tham chiếu được chia sẻ quá sớm, thread khác còn có thể nhìn thấy một object **đang khởi tạo dở**. `final` giúp bảo vệ trạng thái bất biến khi object được dựng đúng cách, nhưng không sửa việc `this` thoát khỏi constructor quá sớm.

Bài thuộc nhóm **Java Memory Model** của Java concurrency nói chung, dùng các cơ chế Java SE (`volatile`, `synchronized`, class initialization, `java.util.concurrent`). Không bàn tới vòng đời bean, dependency injection, proxy hoặc cơ chế concurrency riêng của Spring.

## 1. Ba công việc cần phân biệt

Giả sử ta muốn một thread tạo cấu hình và các thread khác sử dụng nó:

~~~text
Thread A (producer)                     Thread B (consumer)
-------------------                     -------------------
1. Cấp phát object
2. Khởi tạo các field
3. Công bố tham chiếu ----------------> 4. Đọc tham chiếu
                                        5. Đọc các field
~~~

Một thiết kế đúng cần trả lời ba câu hỏi:

1. **Construction — object đã khởi tạo xong chưa?** Mọi invariant (trạng thái phải nhất quán) của object đã được thiết lập chưa? Constructor hoặc factory đã hoàn thành chưa?
2. **Publication — consumer nhận tham chiếu bằng cách nào?** Có quan hệ đồng bộ bảo đảm các ghi trong quá trình khởi tạo được quan sát trước các lần đọc của consumer không?
3. **Subsequent mutation — object có bị sửa sau khi công bố không?** Nếu có, các sửa đổi về sau phải được bảo vệ riêng; safe publication của một snapshot ban đầu không biến mọi hoạt động tương lai thành thread-safe.

**Đừng đánh đồng object tồn tại với object đã được công bố an toàn.** Tham chiếu `ref != null` không mặc nhiên chứng minh các field đã được consumer nhìn thấy theo đúng trạng thái cuối của constructor.

### Khởi tạo dở có nghĩa gì?

Java cấp giá trị mặc định cho field của object trước khi các bước khởi tạo chạy: `int` mặc định `0`, `boolean` là `false`, tham chiếu là `null`. Constructor có thể thay đổi các field sang giá trị hợp lệ, ví dụ `port = 8080` và `name = "primary"`.

Nếu thread B lấy được tham chiếu khi constructor chưa hoàn thành, B có thể đọc một số field ở trạng thái mặc định hoặc thấy invariant chưa thiết lập. Nếu object đã dựng xong nhưng được trao tham chiếu qua một **data race**, B cũng có thể không được JMM bảo đảm quan sát các ghi tới field thông thường theo cách A dự định. Hai nguyên nhân cần phân biệt:

- **Early escape:** object được công bố **trước khi hoàn tất construction**; việc đọc dở có thể xảy ra thực sự vì field chưa được ghi.
- **Unsafe publication:** object có thể đã được xây xong trong A, nhưng không có quan hệ *happens-before* thích hợp giữa các ghi xây dựng object và những lần đọc trong B.

## 2. Java Memory Model và `happens-before`

Java Memory Model (JMM) quy định những giá trị một thread được phép quan sát và các giới hạn của việc tái sắp xếp đọc/ghi. Nó không buộc mọi thread luôn nhìn thấy ngay lập tức các ghi thông thường của nhau khi chương trình thiếu đồng bộ.

Quan hệ **happens-before** (HB) là công cụ suy luận chính. Nếu ghi dữ liệu của A *happens-before* lần đọc tương ứng của B, quan hệ này cung cấp ràng buộc visibility và ordering cần thiết, với điều kiện không có ghi cạnh tranh khác làm thay đổi kết quả. HB **không phải chỉ là** “A xảy ra trước B theo đồng hồ”.

Một số nguồn HB phổ biến:

| Cơ chế | Quan hệ quan trọng |
| --- | --- |
| **Program order** | Hành động trước trong cùng thread HB hành động sau của thread đó. |
| **`volatile`** | Ghi vào biến volatile HB lần đọc volatile tiếp theo của chính biến đó theo thứ tự đồng bộ. |
| **Monitor (`synchronized`)** | Unlock trên một monitor HB lần lock tiếp theo trên cùng monitor. |
| **`Thread.start()`** | Các hành động trước `start()` HB những hành động của thread được start. |
| **`Thread.join()` thành công** | Hành động của thread đã kết thúc HB những hành động phía sau `join()` trong thread đợi. |
| **Class initialization** | JVM điều phối việc khởi tạo class một lần theo các quy tắc khởi tạo class; static state được công bố phù hợp qua cơ chế đó. |
| **Concurrent utilities** | Các API như `BlockingQueue`, `Future.get()`, executor có các bảo đảm memory consistency cụ thể theo tài liệu của chúng. |

HB có tính **bắc cầu**: nếu `A HB B` và `B HB C` thì `A HB C`. Vì thế khi producer ghi các field, sau đó thực hiện thao tác release và consumer thực hiện thao tác acquire tương ứng, ta có thể suy ra việc quan sát các ghi đã xảy ra trước release.

Ví dụ đơn giản:

~~~text
Thread A:  config = new Config(...);   // Khởi tạo field
           READY = config;             // Ghi volatile (release)

Thread B:  local = READY;              // Đọc volatile thấy tham chiếu (acquire)
           local.port();               // Đọc dữ liệu đã khởi tạo
~~~

Nếu `READY` là field `volatile` và B thấy tham chiếu A đã ghi, các hành động chuẩn bị object trước volatile write sẽ được công bố thích hợp cho B. B phải đọc qua cơ chế đó; không được bypass bằng đường tham chiếu khác chưa được đồng bộ.

### Safe publication khác atomicity

Safe publication bảo đảm **trạng thái lúc công bố** được nhìn thấy đúng theo quan hệ đồng bộ. Nó **không có nghĩa** mọi thay đổi về sau của các field đều atomic. Nếu các thread cùng tăng một biến đếm mutable bằng `count++`, vẫn cần `synchronized`, atomic RMW hoặc cơ chế phù hợp. **`volatile` của biến chứa tham chiếu cũng không làm các field bên trong object tự động volatile.**

## 3. Sai lầm 1 — công bố qua field thông thường

Xem đoạn minh họa sau (cố tình không đồng bộ, không phải chương trình độc lập):

~~~java
final class MutableConfig {
    int port;
    String host;

    MutableConfig(int port, String host) {
        this.port = port;
        this.host = host;
    }
}

class Registry {
    static MutableConfig shared; // Không volatile; không có lock.

    static void publish() {
        shared = new MutableConfig(8080, "primary");
    }

    static void consume() {
        MutableConfig local = shared;
        if (local != null) {
            System.out.println(local.port + " / " + local.host);
        }
    }
}
~~~

Nếu `publish()` và `consume()` chạy trên các thread khác nhau mà **không** có một cơ chế HB khác, việc ghi/đọc `shared` tạo data race. JMM không cung cấp bảo đảm rằng consumer sẽ quan sát object đúng như producer vừa xây, hoặc thậm chí luôn nhìn thấy tham chiếu mới trong một vòng polling không đồng bộ.

Không nên ép một stdout cụ thể cho ví dụ sai này: trên máy quen thuộc nó có thể in `8080 / primary` hàng triệu lần và **vẫn sai về mặt hợp đồng**. Trong một execution không đồng bộ, việc thread đọc default/stale field hoặc không nhận được cập nhật có thể xảy ra tùy JMM và tối ưu hóa, nhưng ta không được coi “thường chạy đúng” là proof.

Điểm đáng lưu ý: producer viết `new MutableConfig(...)` **trước** câu gán `shared` trong source không tự tạo HB với consumer. Program order chỉ tạo quan hệ nội bộ trong producer; để ràng buộc consumer cần một synchronization edge liên thread.

## 4. Sai lầm 2 — `this` thoát khỏi constructor quá sớm

Một object không nên được thread khác truy cập khi các invariant còn đang được dựng. Các ví dụ gây **constructor escape**:

- Gán `this` vào một biến static/global mà thread khác đọc.
- Gọi callback hoặc đăng ký listener để có thể được gọi ngay và truyền `this` ra ngoài.
- Gửi lambda capture `this` vào executor trước khi constructor xong.
- Khởi động thread trong constructor với `new Thread(() -> use(this)).start()` rồi tiếp tục thiết lập field.
- Gọi phương thức có thể bị override trong constructor; mã override ở subclass có thể thấy subclass chưa khởi tạo xong.

Đặc biệt, `Thread.start()` chỉ bảo đảm các ghi **trước lời gọi start** HB hành động của thread mới; các field được gán **sau start** không tự có bảo đảm tương tự.

### Ví dụ 1 — nhìn thấy object chưa dựng xong một cách xác định

Để thấy đây là vấn đề thứ tự khởi tạo thật sự, chương trình dưới **chủ động cho phép consumer đọc giữa constructor**. Tạo `EscapingThisDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;

public class EscapingThisDemo {
    private static volatile Leaky shared;
    private static final CountDownLatch exposed = new CountDownLatch(1);
    private static final CountDownLatch resume = new CountDownLatch(1);

    static final class Leaky {
        int answer; // Ban đầu là 0.

        Leaky() throws InterruptedException {
            shared = this;      // Sai: công bố trước khi hoàn thành.
            exposed.countDown();
            resume.await();     // Cố ý giữ constructor ở giữa chừng.
            answer = 42;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread maker = new Thread(() -> {
            try {
                new Leaky();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        maker.start();
        exposed.await();
        System.out.println("while constructing = " + shared.answer);

        resume.countDown();
        maker.join();
        System.out.println("after construction = " + shared.answer);
    }
}
~~~

Chạy:

~~~bash
javac EscapingThisDemo.java
java EscapingThisDemo
~~~

Kết quả trong trường hợp không có interruption bên ngoài:

~~~text
while constructing = 0
after construction = 42
~~~

Vì `shared = this` xảy ra **trước** `answer = 42` và latch giữ constructor tại điểm đó, consumer chắc chắn đọc `answer` lúc field vẫn đang ở default `0`. Sau `resume.countDown()`, constructor tiếp tục. `maker.join()` bảo đảm main đợi maker hoàn tất trước khi in `42`.

Ví dụ này **không cần** dựa vào một hiệu ứng reordering mơ hồ: nó cho thấy một object có thể thực sự bị công bố trước khi sẵn sàng. Quan trọng hơn, `shared` ở đây **đã là volatile**: dùng volatile không thể “đẩy” những phép ghi ở tương lai trong constructor quay ngược về trước thời điểm publish. Safe publication phải xảy ra **sau khi** object hoàn tất khởi tạo.

### Sửa cách tổ chức

Không đăng ký callback, khởi động worker hoặc gắn `this` vào registry từ trong constructor khi consumer có thể chạy ngay. Hãy:

1. Xây dựng object trong constructor **không cho tham chiếu thoát**.
2. Kiểm tra invariant và hoàn thành construction.
3. Công bố tham chiếu qua một cơ chế HB; hoặc gọi một phương thức `start()`/`register()` **sau khi** factory đã trả về object hoàn chỉnh.

Nếu một callback có thể chạy đồng thời, chính callback cũng cần dùng giao thức đồng bộ thích hợp cho trạng thái mà nó truy cập.

## 5. Cách 1 — public snapshot bất biến qua `volatile`

Đối với cấu hình được thay thế nguyên khối, cách đơn giản là tạo một object **bất biến** hoàn chỉnh rồi gán tham chiếu của nó vào một field `volatile`.

Tạo `VolatilePublication.java` (Java 17+):

~~~java
public class VolatilePublication {
    record Config(String host, int retries) {}

    private static volatile Config current;

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            Config snapshot;
            while ((snapshot = current) == null) {
                Thread.onSpinWait(); // Chỉ dành cho demo ngắn.
            }
            System.out.println(snapshot.host() + " / " + snapshot.retries());
        });

        consumer.start();                // Consumer đã được khởi động.
        Config built = new Config("primary", 3);
        current = built;                 // Publish sau construction.
        consumer.join();
    }
}
~~~

Chạy:

~~~bash
javac VolatilePublication.java
java VolatilePublication
~~~

Đầu ra:

~~~text
primary / 3
~~~

Điều cốt lõi không phải bản thân `record`, mà là chuỗi:

~~~text
Producer: khởi tạo Config -> ghi volatile current
                                 |
                                 | synchronizes-with
                                 v
Consumer:                 đọc volatile current -> đọc field Config
~~~

Consumer chỉ đọc những field của **snapshot nó vừa lấy vào biến local**, không đọc tham chiếu từ registry nhiều lần rồi trộn field của các phiên bản khác nhau. `record` tạo các component final; ở đây `String` và `int` không chứa trạng thái mutable có thể bị sửa sau khi công bố.

Vòng `Thread.onSpinWait()` là **busy-wait chỉ để dạy ngữ nghĩa volatile**, không phải khuyến nghị production. Với công việc thật, dùng `BlockingQueue`, `CountDownLatch`, `Future` hoặc cơ chế notification để chờ hiệu quả.

### Thay thế snapshot an toàn, nhưng cập nhật hợp thành chưa chắc an toàn

~~~java
// Minh họa: mỗi lần cập nhật được publish nguyên một snapshot.
current = new Config("backup", 5);
~~~

Mỗi consumer có thể lấy một trong các phiên bản đã được công bố; snapshot đó nhất quán về hai trường của nó. Tuy nhiên, nếu **nhiều producer** đồng thời đọc `current`, tính bản mới, rồi ghi lại, chuỗi read-modify-write vẫn có thể lost update. Khi yêu cầu điều phối cập nhật, cần lock hoặc `AtomicReference.updateAndGet()`/CAS và hàm cập nhật thuần.

Ngoài ra, một field `volatile` chỉ bảo đảm publication qua chính field ấy; nếu publish object rồi **tiếp tục sửa các field ordinary** bên trong mà không đồng bộ, các thay đổi về sau có thể tạo data race.

## 6. Cách 2 — `synchronized` và cùng một monitor

`synchronized` có hai vai trò liên quan: **mutual exclusion** (loại trừ đồng thời trong critical section) và **visibility/ordering** nhờ unlock/lock trên cùng monitor.

Tạo `MonitorPublication.java` (Java 17+):

~~~java
public class MonitorPublication {
    static final class Config {
        final String host;
        final int retries;

        Config(String host, int retries) {
            this.host = host;
            this.retries = retries;
        }
    }

    private static final Object LOCK = new Object();
    private static Config shared; // Không cần volatile khi luôn dùng LOCK.

    private static void publish(Config config) {
        synchronized (LOCK) {
            shared = config;
            LOCK.notifyAll();
        }
    }

    private static Config awaitConfig() throws InterruptedException {
        synchronized (LOCK) {
            while (shared == null) {
                LOCK.wait();
            }
            return shared;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            try {
                Config snapshot = awaitConfig();
                System.out.println(snapshot.host + " / " + snapshot.retries);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        publish(new Config("primary", 3));
        consumer.join();
    }
}
~~~

Chạy:

~~~bash
javac MonitorPublication.java
java MonitorPublication
~~~

Kết quả bình thường:

~~~text
primary / 3
~~~

`publish()` dựng `Config` **trước khi** đặt tham chiếu vào `shared` dưới monitor `LOCK`. `awaitConfig()` đọc `shared` dưới **chính monitor đó**. Unlock của producer HB lần lock tiếp theo ở consumer. `notifyAll()` giúp đánh thức thread đang đợi; việc kiểm tra điều kiện trong vòng `while` là cần thiết vì Java cho phép *spurious wakeup*.

**Lỗi hay gặp:** producer dùng `synchronized(lockA)` nhưng consumer đọc `shared` bên ngoài lock hoặc dùng `lockB`. Không có bảo đảm HB từ `lockA` sang `lockB` chỉ vì chúng đều là lock.

Nếu reader phải trả về snapshot để xử lý lâu dài, nên để trạng thái snapshot bất biến. Nếu object mutable được sửa sau khi lấy ra khỏi lock, công việc vẫn cần bảo vệ riêng.

## 7. Cách 3 — chuyển quyền sở hữu qua `BlockingQueue`

Một queue thread-safe vừa chuyên chở tham chiếu, vừa là giao thức giao việc có quan hệ memory consistency. Các hành động trước khi producer đặt phần tử vào `BlockingQueue` HB những hành động sau khi consumer lấy phần tử đó ra theo API.

Tạo `QueuePublication.java` (Java 17+):

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueuePublication {
    record Message(String text, int code) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Message message = queue.take();
                System.out.println(message.text() + " / " + message.code());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        Message built = new Message("ready", 200);
        queue.put(built);
        consumer.join();
    }
}
~~~

Chạy:

~~~bash
javac QueuePublication.java
java QueuePublication
~~~

Kết quả:

~~~text
ready / 200
~~~

Ưu điểm: consumer có thể **block** chờ dữ liệu, không cần vòng polling volatile; queue còn mô hình hóa thứ tự và backpressure theo capacity. Cần nắm quy tắc ownership: nếu producer `queue.put(mutableObject)` rồi tiếp tục mutate object trong khi consumer đọc, queue chỉ chuyển giao an toàn **những hành động trước put**; các sửa đổi đồng thời sau đó cần bảo vệ riêng.

Giao tiếp bằng snapshot bất biến hoặc ownership transfer rõ ràng thường làm bài toán ít shared mutable state hơn.

## 8. Cách 4 — Java class initialization và initialization-on-demand holder

JVM có quy tắc đồng bộ hóa quá trình khởi tạo class. Khi một static field được gán trong quá trình class initialization, mã khác sử dụng class đã khởi tạo đúng theo hợp đồng sẽ quan sát trạng thái static đã hoàn tất.

Ví dụ lazy singleton bằng *initialization-on-demand holder*. Tạo `LazySingleton.java`:

~~~java
public class LazySingleton {
    static final class Service {
        final int answer;

        Service(int answer) {
            this.answer = answer;
        }
    }

    private static final class Holder {
        static final Service INSTANCE = new Service(42);
    }

    static Service getService() {
        return Holder.INSTANCE;
    }

    public static void main(String[] args) {
        Service first = getService();
        Service second = getService();

        System.out.println("same instance = " + (first == second));
        System.out.println("answer = " + first.answer);
    }
}
~~~

Chạy:

~~~bash
javac LazySingleton.java
java LazySingleton
~~~

Đầu ra:

~~~text
same instance = true
answer = 42
~~~

`Holder` được khởi tạo khi cần dùng static field của nó; JVM bảo đảm khởi tạo class một lần đúng quy tắc concurrency. Các thread gọi `getService()` nhận cùng instance đã được constructor hoàn tất, miễn constructor không để `this` thoát sớm. Cách này tránh phải tự viết double-checked locking cho một singleton khởi tạo lười đơn giản.

### Static field `final` khác “object hoàn toàn bất biến”

~~~java
static final java.util.List<String> NAMES =
        new java.util.ArrayList<>();
~~~

`final` ở đây **chỉ giữ cố định tham chiếu** tới list; bản thân list vẫn mutable và không thread-safe. Nếu nhiều thread đồng thời thêm/xóa phần tử cần thiết kế synchronization/ownership hoặc chọn cấu trúc dữ liệu phù hợp. Với cấu hình read-only, ưu tiên immutable snapshots như `List.copyOf(source)`. Lưu ý immutable collection không tự làm các **phần tử bên trong** bất biến nếu phần tử chứa trạng thái mutable.

## 9. `final` field semantics: mạnh, nhưng có điều kiện

JMM dành các quy tắc đặc biệt cho `final` fields. Khi object được **constructed correctly** — tức tham chiếu `this` không thoát trong quá trình construction — và constructor kết thúc, cơ chế *freeze* trên final fields giúp thread khác quan sát giá trị final đã gán trong constructor, ngay cả trong một số tình huống tham chiếu được truyền bằng data race.

Ví dụ:

~~~java
// Ví dụ dạng type declaration, không phải chương trình độc lập.
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Khi một `Point` được xây dựng đúng cách, final-field semantics cung cấp bảo đảm đặc biệt cho `x` và `y`. Tuy nhiên **không nên diễn dịch** thành “cứ dùng final là mọi publication đều an toàn”. Phân biệt:

- `final` trên một field được gán ở constructor và **không có constructor escape** có bảo đảm riêng về giá trị được khởi tạo.
- Field thông thường (non-final) không tự nhận được bảo đảm final-field semantics; cho object có dữ liệu ordinary mutable, hãy publish qua HB.
- `final SomeObject reference` chỉ ngăn **gán lại tham chiếu** sau construction; nếu object được tham chiếu có thể bị sửa, các sửa đổi sau này vẫn cần synchronization.
- Quy tắc cho object mà reference được truy cập qua final field có những bảo đảm visibility đối với trạng thái trước freeze, nhưng **không phải phép bảo đảm mọi mutation về sau là an toàn**.
- Nếu `this` thoát sớm, thread khác có thể đọc field **trước khi gán** hoặc trước lúc constructor kết thúc; không có quyền dựa vào freeze để sửa hành vi đó.
- Dùng reflection, unsafe mechanisms hoặc serialization đặc biệt để sửa final fields về sau có ngữ nghĩa phức tạp; đừng dựa vào pattern như vậy cho state chia sẻ.

**Thực hành an toàn:** thiết kế object bất biến thật sự và publish qua một cơ chế HB rõ ràng. Final fields giúp tính đúng đắn của dữ liệu bất biến, còn cơ chế publication giúp kiểm soát luồng giao nhận và mở rộng dễ hiểu khi kiểu dữ liệu thay đổi.

### Record có làm mọi object thread-safe?

`record` thường thuận tiện để tạo một immutable snapshot về mặt component references:

~~~java
record Settings(String endpoint, int timeoutSeconds) {}
~~~

Các component fields là final. Nhưng một record có component là `List<MutableItem>` vẫn có thể mang mutable objects nếu không defensive copy và không bảo vệ các item. Các constructor cũng phải tránh cho `this` thoát sớm, và các method không nên phơi nội bộ mutable state một cách không kiểm soát.

## 10. Safe publication bằng `Thread.start()` và `Thread.join()`

Không phải lúc nào cũng cần một field volatile mới. Khi **producer xây object rồi mới gọi `start()`** cho consumer, `start()` chính nó là một synchronization event:

~~~java
// StartPublication.java — Java 17+
public class StartPublication {
    static final class Data {
        int value;

        Data(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Data built = new Data(42); // Hoàn tất trước start.

        Thread consumer = new Thread(
                () -> System.out.println("value = " + built.value));
        consumer.start();
        consumer.join();
    }
}
~~~

Chạy `javac StartPublication.java` và `java StartPublication`:

~~~text
value = 42
~~~

Các hành động xây dựng object ở main trước `consumer.start()` HB các hành động của consumer. Không cần `volatile` ở `built` cho tình huống một chiều này.

`Thread.join()` tạo hướng **ngược lại**: nếu main đợi consumer kết thúc, các hành động consumer trước khi kết thúc HB hành động main sau `join()`. Ví dụ một worker ghi kết quả vào ordinary field và main chỉ đọc **sau join thành công** có cơ sở visibility. Nhưng join chỉ giúp **thread đã đợi**; không có nghĩa một thread thứ ba đang đọc shared state sẽ tự nhiên được đồng bộ.

**Chú ý:** khởi động thread **trong constructor** rồi tiếp tục gán các field của `this` có thứ tự đảo ngược; những ghi sau `start()` không được bao phủ tự động bởi HB của `start()`. Đây là một nguyên nhân constructor escape phổ biến.

## 11. Future, executor và concurrent collections

Các tiện ích chuẩn Java thường có quy tắc memory consistency đã được API tài liệu hóa. Ví dụ với `ExecutorService`, hành động của thread gửi task **trước khi submit** HB hành động của task; hành động trong task HB hành động sau khi thread khác lấy kết quả bằng `Future.get()`. Khi dùng đúng, cặp `submit/get` là một kênh an toàn để truyền state và lấy kết quả.

Tạo `FuturePublication.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FuturePublication {
    static final class Result {
        final int sum;
        Result(int sum) {
            this.sum = sum;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<Result> future = executor.submit(
                    () -> new Result(20 + 22));

            Result result = future.get();
            System.out.println("sum = " + result.sum);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac FuturePublication.java
java FuturePublication
~~~

Đầu ra:

~~~text
sum = 42
~~~

`Future.get()` đợi computation hoàn thành và đem kết quả qua một quan hệ HB được API quy định. Nếu task bị lỗi, `get()` có thể ném `ExecutionException`; nếu bị hủy, có thể ném `CancellationException`. An toàn publication không thay thế quy tắc xử lý lỗi/hủy.

Tương tự, `ConcurrentHashMap`, các blocking queue và những synchronization primitives khác có các cam kết riêng cho thao tác được hỗ trợ. **Không suy ra từ tên “concurrent” rằng một chuỗi get → compute → put nhiều bước hoặc một transaction nhiều key tự động atomic.** Safe publication và compound-action atomicity là hai yêu cầu tách biệt.

## 12. Double-checked locking và vai trò của `volatile`

Một lỗi cổ điển của lazy singleton là dùng **double-checked locking (DCL)** nhưng quên `volatile` ở reference:

~~~java
// Minh họa lỗi: instance không volatile.
private static Service instance;

static Service get() {
    if (instance == null) {
        synchronized (LOCK) {
            if (instance == null) {
                instance = new Service();
            }
        }
    }
    return instance;
}
~~~

Lần kiểm tra đầu tiên ở ngoài lock là lần đọc không đồng bộ với writer trong lock. Vì thiếu HB thích hợp, thiết kế không an toàn: thread khác có thể thấy tham chiếu mà không có bảo đảm về trạng thái object cần quan sát. Câu chuyện lịch sử hay diễn giải thành “có thể thấy đối tượng chưa được khởi tạo đầy đủ”; thực tế cần phân tích theo hợp đồng visibility và các field cụ thể, tránh khẳng định mọi JVM chắc chắn sẽ tái hiện hiện tượng.

DCL đúng cho Java 5+ cần field `volatile`, constructor không escape và cùng monitor cho phép khởi tạo:

~~~java
// Dạng phương thức minh họa, các field nằm trong class chứa singleton.
private static volatile Service instance;
private static final Object LOCK = new Object();

static Service get() {
    Service local = instance;
    if (local == null) {
        synchronized (LOCK) {
            local = instance;
            if (local == null) {
                local = new Service();
                instance = local; // Volatile write sau construction.
            }
        }
    }
    return local;
}
~~~

`volatile` bảo đảm lần đọc nhanh ở ngoài lock vẫn tham gia cơ chế publication. Dùng biến local giảm số lần đọc volatile ở đường fast path. Nếu use case chỉ là static singleton đơn giản, **holder idiom** ở phần 8 thường ít phức tạp hơn.

DCL không giải quyết trường hợp constructor của `Service` tự đăng ký `this` vào registry khác, hoặc không chịu trách nhiệm đảm bảo thread-safe cho các method mutable của `Service` về sau.

## 13. Vì sao “volatile reference” chưa đủ nếu object còn mutable?

Giả sử `volatile Config shared` được publish đúng sau construction, rồi thread A thay đổi một field ordinary:

~~~java
// Minh họa lỗi logic, không phải chương trình độc lập.
Config snapshot = new Config();
snapshot.port = 8080;
shared = snapshot;  // Publish an toàn trạng thái đã xây tới đây.

// Một lúc khác, thread A:
snapshot.port = 9090; // Mutation ordinary không đồng bộ.

// Trong khi đó, thread B:
int observed = shared.port;
~~~

Lần gán `shared` ban đầu có thể publish an toàn giá trị `8080`. Nhưng lần ghi `snapshot.port = 9090` ở **sau publication** không tự trở thành thread-safe chỉ vì field giữ reference là volatile. Nếu B đọc dữ liệu đồng thời với A sửa mà không có HB thích hợp, còn data race. B cũng có thể đọc state cũ hoặc state thay đổi từng phần khi có nhiều field.

Ba cách thiết kế thường tốt hơn:

1. **Immutable snapshots:** xây `new Config(...)` đầy đủ và gán reference volatile mới; consumer làm việc với snapshot local.
2. **Shared lock:** các thao tác đọc/ghi trạng thái mutable cùng khóa bảo vệ toàn bộ invariant.
3. **Atomic whole-state replacement:** `AtomicReference<State>` giữ immutable state; muốn tính state mới từ state cũ dưới cạnh tranh thì dùng CAS/`updateAndGet()`. Hàm update nên thuần vì có thể chạy lại khi retry.

Nếu cần giữ một collection mutable lâu dài, chọn cấu trúc concurrent đúng ngữ nghĩa và tránh rò rỉ tham chiếu tới trạng thái nội bộ chưa được bảo vệ.

## 14. Chọn chiến lược publication theo nhu cầu

| Nhu cầu | Cơ chế nên dùng | Lưu ý |
| --- | --- | --- |
| Một producer cập nhật snapshot cấu hình, nhiều reader lấy bản hiện tại | `volatile` reference tới immutable object | Publish **sau** construction; mutation sau publish phải tránh hoặc bảo vệ |
| Đọc/ghi nhiều field mutable như một invariant | `synchronized` hoặc `Lock` chung | Cả writer và reader phải tham gia cùng protocol |
| Chuyển thông điệp/công việc giữa producer–consumer | `BlockingQueue` | Trạng thái của object sau `put` cần quy tắc ownership rõ |
| Singleton static khởi tạo lười | Initialization-on-demand holder | Constructor không escape; state bên trong phải có policy concurrency riêng |
| Worker tạo dữ liệu và main cần kết quả | `Future.get()`, `Thread.join()` trong trường hợp phù hợp | Chờ đúng đối tượng và xử lý failure/interruption |
| Thay nguyên trạng thái nhiều trường dưới cạnh tranh | `AtomicReference<ImmutableState>` + CAS | Atomicity áp dụng cho **một reference**, không cho side effect bên ngoài |
| Tham chiếu được đưa tới thread **sau** khi khởi tạo trong cùng thread | `Thread.start()` | Những ghi **sau start** không tự nằm trong quan hệ HB trước start |
| Bất kỳ object nào cần chia sẻ an toàn | Không để `this` escape từ constructor | Không gọi code ngoài kiểm soát có thể publish `this` quá sớm |

Không dùng việc thử chạy thấy đúng, `Thread.sleep`, thứ tự timestamp hay giả định “CPU tự đồng bộ cache” làm tiêu chí chứng minh safe publication.

## 15. Quy trình rà soát một lỗi publication

**Bước 1 — Tìm nơi tạo object.** Constructor có khởi tạo đầy đủ invariant không? Có gọi method overridable, callback, listener registration hay khởi động thread trong constructor không?

**Bước 2 — Tìm đường tham chiếu đi đến consumer.** Qua static field, instance field, global registry, queue, future, local variable capture hay một callback? Tham chiếu có bị chia sẻ trước khi constructor kết thúc không?

**Bước 3 — Vẽ cạnh HB.** Trước đường consumer đọc có volatile write/read, unlock/lock cùng monitor, `start`, `join`, `Future.get`, queue put/take, static class init hoặc một protocol khác đã được tài liệu hóa không? Nếu không chỉ ra được cạnh, đừng kết luận visibility là an toàn.

**Bước 4 — Phân biệt field.** Trường nào là `final` đúng cách, trường nào ordinary mutable, trường nào volatile? Final-field semantics có điều kiện gì? Có nested mutable object cần bảo vệ không?

**Bước 5 — Tìm mutation sau publication.** Consumer đang dùng snapshot cố định hay đọc reference lại nhiều lần? Có nhiều producer làm RMW và làm mất cập nhật không? Object có bị sửa không đồng bộ sau khi consumer giữ tham chiếu không?

**Bước 6 — Chọn sửa ở đúng ranh giới.** Chuyển publish ra sau constructor, dùng immutable snapshot và volatile, hoặc đồng bộ hóa cả producer/consumer, hoặc đưa dữ liệu qua concurrency API có HB. Chỉ thêm `volatile` vào reference không sửa vấn đề publish quá sớm.

**Bước 7 — QA đúng tính chất.** Ví dụ lỗi racy có thể chạy “đúng” nhiều lần; không xem đó là test chứng minh. Dùng một ví dụ có latch điều khiển early escape để cho thấy thứ tự khởi tạo, và dùng lập luận HB/kiểm tra code cho tính đúng của sửa lỗi. Stress test có thể giúp phát hiện lỗi, nhưng không thay thế lập luận về JMM.

### Những lỗi thường gặp

- **“Reference khác `null` thì object chắc chắn dựng xong.”** Không: `this` có thể bị đưa ra ngoài khi constructor chưa xong.
- **“Producer đã kết thúc constructor nên mọi reader luôn thấy toàn bộ field.”** Không đủ với ordinary fields khi thiếu safe publication; `final` có bảo đảm đặc biệt chỉ khi được dựng đúng cách.
- **“Dùng `volatile` cho reference thì các field bên trong mãi mãi thread-safe.”** Không: mutation sau publish cần cơ chế riêng.
- **“`final` nghĩa là mọi object được tham chiếu đều bất biến sâu.”** Không: final khóa tham chiếu, không đóng băng object mutable được tham chiếu.
- **“Chạy `new Thread(...).start()` trong constructor luôn an toàn.”** Không: child có thể quan sát `this` trước những field được gán sau start.
- **“Producer và consumer đều có synchronized, khóa nào cũng được.”** Không: cần cùng monitor/protocol để có cạnh HB liên quan.
- **“`Future.isDone()` thôi đã cho mọi bảo đảm.”** Đối với kết quả cụ thể, dùng `Future.get()`/quy tắc completion được tài liệu hóa và xử lý lỗi; không suy luận tùy ý về mọi state ngoài phép tính.
- **“Đã publish an toàn thì có thể làm compound action không khóa.”** Không: safe publication khác atomic read-modify-write hoặc giao dịch nhiều field.

## 16. Tự kiểm tra

**Câu 1.** Thread A khởi tạo một `Config` hoàn chỉnh rồi gán vào field ordinary; thread B đọc field ordinary không khóa. A đã chạy trước theo đồng hồ. Có chắc B thấy đúng mọi ordinary field không?  
**Đáp án:** Không có bảo đảm từ **thời gian thực** đơn thuần. Cần edge HB hoặc cơ chế phù hợp; final fields dựng đúng có quy tắc riêng.

**Câu 2.** Object gán vào một static `volatile` reference ở đầu constructor, rồi mới đặt các field. Consumer có thể đọc default value không?  
**Đáp án:** Có. Volatile publish **những ghi xảy ra trước nó**, không bảo đảm các field sẽ được ghi sau này trước khi reader chạy.

**Câu 3.** Producer tạo snapshot immutable xong rồi volatile-write; consumer volatile-read được tham chiếu đó. Có cần lock thêm chỉ để đọc các field bất biến đã tạo không?  
**Đáp án:** Không, nếu object được constructed correctly và đúng protocol, volatile write/read tạo HB cho các giá trị đã khởi tạo.

**Câu 4.** Thread A xây object rồi `consumer.start()`, consumer chỉ đọc object không bị sửa tiếp. Có cơ sở HB không?  
**Đáp án:** Có: các hành động trong A trước `start()` HB các hành động của thread được start.

**Câu 5.** `final List<MutableItem> items` có chứng minh list và item không thể bị sửa đồng thời không?  
**Đáp án:** Không. `final` giữ reference; collection và các item có thể còn mutable.

**Câu 6.** Một `BlockingQueue` giao message bất biến từ producer tới consumer. Vì sao consumer không cần dùng một volatile field riêng chỉ để lấy message?  
**Đáp án:** Queue đã có protocol đồng bộ và bảo đảm memory consistency cho hành động trước put so với hành động sau take của chính phần tử đó.

**Câu 7.** DCL dùng đọc reference ngoài lock nhưng field không volatile. Tại sao đáng ngại?  
**Đáp án:** Read ngoài lock thiếu HB với writer khởi tạo; reader không được bảo đảm quan sát trạng thái phù hợp. Cần `volatile` hoặc chọn holder idiom.

## Nguồn tham khảo chính thức

- [Java Language Specification, Java SE 17 — `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): synchronization order, happens-before, data races.
- [Java Language Specification, Java SE 17 — `17.5 final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): constructor freeze, correctly constructed objects và giới hạn của final.
- [Java Language Specification, Java SE 17 — `12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): quy tắc khởi tạo class.
- [`Thread` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): start, join và memory consistency.
- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): bảo đảm giao nhận công việc/dữ liệu.
- [`AtomicReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cập nhật nguyên tử một reference.

**Ghi nhớ:** **Construct first → publish safely → protect later mutation.** Để một consumer thấy object đáng tin cậy, hãy tránh constructor escape và xác lập cơ chế *happens-before* rõ ràng giữa các thread.