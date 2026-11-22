# Deadlock khi nhiều loader ủy quyền chéo

Một `ClassLoader` tùy chỉnh có thể hỏi class loader khác để tìm một class. Điều này cần thiết trong hệ plugin, application server, OSGi hoặc những kiến trúc có nhiều không gian nạp lớp. Nhưng nếu **loader A đang giữ khóa nạp lớp của mình và gọi loader B**, đồng thời **loader B đang giữ khóa của mình và gọi ngược loader A**, hai thread có thể chờ nhau mãi: **deadlock**.

Khác với `ClassNotFoundException` (tìm không thấy class) hay `ClassCastException` (không tương thích kiểu), deadlock thường khiến chương trình **treo tại bước nạp lớp**, không tiến đến câu lệnh cần thực thi, đôi khi không in exception. Sự cố có thể chỉ xuất hiện khi tải plugin đồng thời hoặc khi startup được tối ưu chạy nhiều thread.

Trọng tâm của bài là **quan hệ giữa class-loading lock, thứ tự ủy quyền và đồ thị phụ thuộc loader**. Cần hiểu rõ cả rủi ro ở loader thông thường (khóa toàn loader) và loader **parallel-capable** (khóa theo tên class): đăng ký parallel-capable có thể giảm tranh chấp không cần thiết, nhưng **không tự khắc phục một chu trình ủy quyền thực sự**.

## 1. Khóa nào góp phần tạo deadlock?
`ClassLoader.loadClass(name, resolve)` mặc định đồng bộ trên `getClassLoadingLock(name)` suốt chu trình `findLoadedClass` → parent/bootstrap → `findClass` → optional `resolveClass`. Loader chưa đăng ký parallel-capable dùng **monitor trên chính loader instance**; loader đã đăng ký dùng **khóa theo từng binary name**. Cả hai vẫn phải phối hợp để không `defineClass` hai lần cùng tên.
Deadlock xảy ra khi **hai thread giữ hai khóa mà bên kia cần**. Trong mô hình ủy quyền chéo, request có thể đi từ loader A sang B trong lúc vẫn giữ khóa A, và từ B quay lại A trong lúc giữ khóa B. Những mục tiếp theo chứng minh vòng chờ bằng chương trình có kiểm soát, rồi phân tích vì sao khóa theo tên chỉ giảm một phần rủi ro.

## 2. Deadlock hình thành khi hai loader ủy quyền chéo

Giả sử A và B có chính sách tìm class qua nhau:

~~~text
           Thread T1                              Thread T2

     giữ lock loader A                      giữ lock loader B
             |                                      |
             v                                      v
    A.loadClass("lab.A")                    B.loadClass("lab.B")
             |                                      |
             v                                      v
    gọi B.loadClass("lab.B")                gọi A.loadClass("lab.A")
             |                                      |
             v                                      v
      CHỜ lock B                              CHỜ lock A
             |                                      |
             +---------------+----------------------+
                             |
                      CIRCULAR WAIT
                         DEADLOCK
~~~

T1 không nhả khóa A cho đến khi B trả kết quả. T2 không nhả khóa B cho đến khi A trả kết quả. Nếu cả hai monitor được giữ và hai lời gọi chéo xảy ra đồng thời, không thread nào tiếp tục được.

Một cách mô hình hóa là **wait-for graph**:

~~~text
T1 giữ A, muốn B:    T1 ──wait-for──► T2
T2 giữ B, muốn A:    T2 ──wait-for──► T1

Chu trình T1 → T2 → T1 → deadlock
~~~

Chữ “đồng thời” ở đây quan trọng: với một thread, một vòng ủy quyền logic A→B→A có thể biểu hiện thành **đệ quy vô hạn / StackOverflowError** thay vì monitor deadlock, tùy cách các loader kiểm tra cache và trả lỗi. Với hai thread giữ khóa theo thứ tự ngược nhau, cùng đồ thị phụ thuộc có thể thành deadlock.

Không phải mọi lần A gọi B rồi B gọi A đều lập tức deadlock. Nếu một yêu cầu được giải quyết bởi class đã load, parent hợp lệ hoặc fallback kết thúc, có thể không chờ chéo. Vấn đề nằm ở **đồ thị ủy quyền không bảo đảm tiến trình kết thúc** và thứ tự giữ khóa giữa các thread.

## 3. Ví dụ Java 17: tái hiện deadlock bằng hai loader tùy chỉnh

Ví dụ này **cố ý tạo deadlock thật** ở cấp Java monitor để minh họa cơ chế; nó không cần ClassFile bên ngoài và không định nghĩa class ứng dụng nào. Chúng ta tạo hai subclass `ClassLoader` **không đăng ký parallel-capable**, mỗi loader giữ monitor khi gọi loader kia.

Để chương trình **không treo khi chạy thử**, hai thread tham gia deadlock được đánh dấu `daemon`. Thread chính chỉ xác nhận cả hai đã vào vùng khóa và in kết quả, rồi JVM có thể thoát dù hai daemon thread đang BLOCKED. Đây là minh họa để học tập, **không được dùng cấu trúc ủy quyền chéo này trong ứng dụng thật**.

Tạo tệp **`CrossLoaderDeadlockDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class CrossLoaderDeadlockDemo {
    static final class CrossingLoader extends ClassLoader {
        private final String requestedName;
        private final CountDownLatch bothHoldingLocks;
        private CrossingLoader peer;

        CrossingLoader(String requestedName,
                       CountDownLatch bothHoldingLocks) {
            super(null);
            this.requestedName = requestedName;
            this.bothHoldingLocks = bothHoldingLocks;
        }

        void setPeer(CrossingLoader peer) {
            this.peer = peer;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                if (name.equals(requestedName)) {
                    bothHoldingLocks.countDown();

                    try {
                        bothHoldingLocks.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new ClassNotFoundException(name, e);
                    }

                    // Gọi chéo trong lúc vẫn giữ monitor của chính loader.
                    return peer.loadClass(peer.requestedName);
                }

                return super.loadClass(name, resolve);
            }
        }
    }

    private static void request(CrossingLoader loader, String name) {
        try {
            loader.loadClass(name);
        } catch (ClassNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch bothHoldingLocks = new CountDownLatch(2);

        CrossingLoader loaderA =
                new CrossingLoader("lab.A", bothHoldingLocks);
        CrossingLoader loaderB =
                new CrossingLoader("lab.B", bothHoldingLocks);

        loaderA.setPeer(loaderB);
        loaderB.setPeer(loaderA);

        Thread threadA = new Thread(
                () -> request(loaderA, "lab.A"), "load-A");
        Thread threadB = new Thread(
                () -> request(loaderB, "lab.B"), "load-B");

        // Daemon: tránh giữ JVM sống mãi trong ví dụ cố ý deadlock.
        threadA.setDaemon(true);
        threadB.setDaemon(true);

        threadA.start();
        threadB.start();

        // Chỉ tiếp tục khi cả hai thread đang giữ lock riêng của mình.
        bothHoldingLocks.await();

        // Thread A phải lấy lock B, thread B phải lấy lock A.
        // Cả hai không thể hoàn thành nếu vẫn giữ lock hiện tại.
        threadA.join(100);
        threadB.join(100);

        System.out.println("Crossed delegation deadlocked: "
                + (threadA.isAlive() && threadB.isAlive()));

        ClassLoader sharedParent =
                ClassLoader.getPlatformClassLoader();

        ClassLoader safeA = new ClassLoader(sharedParent) { };
        ClassLoader safeB = new ClassLoader(sharedParent) { };

        boolean sameRuntimeType =
                safeA.loadClass("java.lang.String")
                        == safeB.loadClass("java.lang.String");

        System.out.println("Shared parent String identity: "
                + sameRuntimeType);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 CrossLoaderDeadlockDemo.java
java CrossLoaderDeadlockDemo
~~~

**Stdout dự kiến theo logic đồng bộ trong ví dụ:**

~~~text
Crossed delegation deadlocked: true
Shared parent String identity: true
~~~

**Giải thích từng phần:**

1. Hai loader `loaderA` và `loaderB` thuộc subclass không có `registerAsParallelCapable`, nên `getClassLoadingLock(name)` trả khóa loader. Mỗi thread nhận một monitor khác nhau.
2. `CountDownLatch(2)` bảo đảm cả hai thread đã tiến vào monitor của loader riêng trước khi đi tiếp. Đây không phải vòng chờ trên latch: lần thứ hai `countDown()` làm latch về 0 và **đánh thức cả hai**.
3. Sau latch, thread A vẫn giữ lock A và gọi `loaderB.loadClass("lab.B")`; thread B vẫn giữ lock B và gọi `loaderA.loadClass("lab.A")`. Mỗi lời gọi chéo cần monitor đang bị phía kia giữ: hình thành **deadlock**.
4. `join(100)` chỉ đợi tối đa 100 ms mỗi thread, **không giải quyết deadlock**. Cả hai thread vẫn còn sống, nên dòng đầu là `true`.
5. Hai thread được đặt `daemon` **trước khi start**, giúp JVM thoát khi thread main kết thúc. Trong một ứng dụng thật, đánh dấu thread daemon **không phải cách sửa deadlock**.
6. Hai loader `safeA` và `safeB` đều dùng chung một parent để nạp `java.lang.String`. Chúng được viết bằng `ClassLoader` mặc định, không tạo ủy quyền chéo; class được trả là cùng `String.class`, nên dòng thứ hai là `true`.

Lưu ý mục tiêu demo: **chứng minh tranh chấp khóa**, không xây một ClassFile hợp lệ hay class loader phục vụ production. Các tên `lab.A` / `lab.B` được dùng làm trigger trước khi tra cứu ClassFile; hai thread bị chặn ở monitor, không cần có `A.class` hoặc `B.class` trên đĩa.

### Tại sao thread chính không treo theo hai loader?

Thread main không gọi hai loader đang deadlock. Nó chỉ chờ latch được mở và thử `join` có timeout. Do T1/T2 là daemon, JVM có thể kết thúc khi chỉ còn daemon threads. Nếu đổi chúng thành **non-daemon** mà không hủy vòng ủy quyền, JVM thường không thoát. Đây là lý do ví dụ cố ý cô lập sự cố trong daemon thread; đừng suy ra cách này bảo vệ hệ thống thật.

## 4. registerAsParallelCapable có giúp không?

Java cung cấp:

~~~java
static {
    ClassLoader.registerAsParallelCapable();
}
~~~

Đây là **fragment trong thân một subclass ClassLoader**; ở ứng dụng thật, nên gọi một lần trong static initializer của subclass và kiểm tra điều kiện các superclass theo API. Phương thức protected static này không phải lời gọi công khai từ tùy ý một class không liên quan.

**Parallel-capable giải quyết vấn đề gì?**

- Khi loader không parallel-capable, nhiều thread tải **hai tên class khác nhau** vẫn có thể phải chờ **một monitor của loader**.
- Khi parallel-capable, `getClassLoadingLock(name)` cung cấp **khóa theo tên** giúp cho phép tiến hành song song các tên khác nhau, giảm một số trường hợp nghẽn cổ chai hoặc khóa theo toàn loader.
- Nó không tự thay đổi chính sách `parent-first`/`child-first`, không tạo đường đi mới giữa các loader và không sửa vòng phụ thuộc class.

**Quan trọng: parallel-capable không phải thuốc chữa mọi deadlock.** Nếu T1 giữ khóa cho `A` của loader A và cần `B` của loader B, còn T2 giữ khóa cho `B` của loader B và cần `A` của loader A, thì ngay cả khóa **theo tên** vẫn tạo vòng chờ trên đúng hai khóa ấy. Ngoài ra custom loader có thể tự giữ monitor, `ReentrantLock`, global cache hoặc lock của framework khi gọi sang loader khác.

Không nên đăng ký parallel-capable mà chưa kiểm tra thread-safety của:

- Bộ nhớ đệm bytecode, map ClassFile, metadata package/`ProtectionDomain` và nguồn tài nguyên.
- `findClass`, `loadClass` override, các hàm fallback/resolve và khóa tùy chỉnh.
- Chính sách load đúng một lần cho mỗi binary name, tránh race dẫn tới `LinkageError`.
- Deadlock do loader A/B gọi chéo, cùng các lock ngoài `getClassLoadingLock`.

Quy tắc thực dụng: **thiết kế đồ thị ủy quyền không có chu trình** trước, sau đó mới xem parallel loading như tối ưu/đúng đắn đồng thời khi cần.

## 5. Một chiều parent delegation và vòng gọi chéo khác gì?

**Đồ thị an toàn điển hình** là cây/hệ DAG một chiều:

~~~text
Plugin-A loader ──► Shared API loader ──► Platform/Bootstrap
Plugin-B loader ──► Shared API loader ──► Platform/Bootstrap

Không có cạnh Shared API loader quay về Plugin-A/Plugin-B.
~~~

Cả hai plugin có thể cô lập implementation của chúng nhưng cùng sử dụng một định nghĩa API. Với cùng tên contract, parent loader là **defining loader chung**, tránh `ClassCastException` do duplicate API.

**Đồ thị nguy hiểm:**

~~~text
Plugin-A loader ──► Plugin-B loader
        ▲                 |
        |                 ▼
        +─────────────────+
~~~

Ngay cả khi có logic fallback, cơ chế “A không thấy thì hỏi B, B không thấy thì hỏi A” có thể không có điểm dừng. Nếu có hai thread nạp đồng thời, rủi ro deadlock rất lớn; nếu trên một thread, có thể đệ quy vô tận.

Một số hệ plugin cần **cross-plugin visibility**. Thay vì để hai loader hỏi nhau tự do:

1. Đặt **API chia sẻ** trong một loader parent chung, không chứa implementation riêng.
2. Định nghĩa một **registry/route lookup** theo tên package hoặc module, đảm bảo mỗi yêu cầu có một **chủ sở hữu** hoặc lộ trình tra cứu có điểm kết thúc.
3. Nếu cần chuyển tiếp giữa nhiều loader, duy trì **visited set / cycle detection** ở tầng điều phối thích hợp và fail rõ ràng khi gặp vòng, thay vì gọi đệ quy vô hạn.
4. Không gọi code tùy ý của plugin khi đang giữ khóa nạp lớp rộng.
5. Không tự đổi type identity bằng cách nhờ loader khác rồi lại `defineClass` cùng bytes trong loader hiện tại; đó sẽ là **định nghĩa thứ hai** có identity khác.

**Chú ý:** Java không yêu cầu mọi custom loader luôn có đúng một parent path và không có tương tác bên ngoài. Tuy nhiên, khi thiết kế đường tìm class xuyên loader, cần bảo đảm các nhánh tìm kiếm **có thể kết thúc** và có quy tắc ownership, đồng bộ đúng.

## 6. Tình huống thực tế nào dễ phát sinh deadlock?

### 6.1. Hai plugin tham chiếu trực tiếp implementation của nhau

Plugin A cố tải `plugin.b.Helper` thông qua loader B; cùng lúc B cố tải `plugin.a.Adapter` thông qua loader A. Nếu mỗi loader giữ lock rộng trong khi gọi sang bên kia, có thể hình thành vòng chờ.

Cách cải thiện: để cả hai gọi qua **interface/API chung**, chuyển dữ liệu qua DTO chia sẻ, hoặc dùng service registry với lifecycle rõ. Tránh phụ thuộc implementation chéo khó kiểm soát.

### 6.2. Ủy quyền “peer loader” tự viết trong child-first loader

Một custom loader có thể viết:

~~~java
// Fragment anti-pattern: chưa có cơ chế chống lặp/cycle.
try {
    return findClass(name);
} catch (ClassNotFoundException missing) {
    return peerLoader.loadClass(name);
}
~~~

Nếu `peerLoader` cũng làm vậy và hỏi ngược loader đầu khi không tìm thấy class, tạo vòng A→B→A. Đoạn fragment không biểu diễn đầy đủ xử lý `findLoadedClass`, lock hoặc `resolveClass`, chỉ minh họa chính sách có nguy cơ.

**Đừng nuốt tất cả `LinkageError` rồi fallback sang peer**: lỗi định nghĩa/liên kết không đồng nghĩa với “class không có ở nguồn này”. Bắt lỗi quá rộng có thể che bytecode hỏng hoặc xung đột type identity.

### 6.3. Class initialization chồng với class loading

`static initializer` có thể gọi code/plugin khác, kích hoạt nạp lớp mới. Deadlock cũng có thể đến từ **khóa khởi tạo class**, static cache lock hoặc application lock, không chỉ monitor của class loader. Ví dụ một thread giữ application lock rồi dùng class cần khởi tạo, trong khi thread khác đang khởi tạo class đó và muốn application lock.

Vì vậy cần phân biệt **class-loading lock deadlock** với **class-initialization deadlock**. Hai loại có thể trông giống nhau trong log “treo khi dùng class” nhưng thread dump và khóa chờ có thể khác.

### 6.4. Thread pool và startup song song

Trong ứng dụng có nhiều worker, lỗi có thể khó tái hiện:

- Khi chạy đơn luồng, một nhánh tìm class có thể hoàn tất hoặc thất bại trước nhánh khác.
- Khi start nhiều plugin cùng lúc, hai thread có thể đồng thời giữ lock loader tương ứng và gọi nhau.
- Những lần chạy khác nhau có thời điểm khởi tạo lớp/cache khác, khiến lỗi xuất hiện không đều.
- Thay đổi thread count hoặc timing có thể làm lỗi “tạm biến mất” nhưng **không loại bỏ chu trình ủy quyền**.

Không nên sửa bằng `Thread.sleep`, tăng timeout hoặc giảm pool size rồi coi hết lỗi; đó chỉ thay đổi lịch chạy. Mục tiêu là **loại vòng chờ hoặc định rõ lock ordering**.

## 7. Chẩn đoán bằng thread dump và JVM tools

Khi ứng dụng treo lúc nạp class:

1. Ghi nhận thread nào đang BLOCKED/WAITING và stack trace tại `ClassLoader.loadClass`, `findClass`, `getClassLoadingLock`, synchronized block hoặc code plugin.
2. Thu **thread dump** lúc treo. Với HotSpot/JDK tiêu chuẩn, có thể dùng lệnh:

~~~bash
jcmd <PID> Thread.print -l
~~~

Thay `<PID>` bằng process ID của JVM cần kiểm tra; đây là placeholder trong **câu lệnh công cụ**, không phải một đoạn Java để biên dịch. Một lựa chọn khác:

~~~bash
jstack -l <PID>
~~~

Các công cụ có thể thay đổi khả dụng theo phân phối JDK, OS và quyền truy cập process. Không nên chạy trong môi trường có hạn chế giám sát mà chưa được phép.

3. Tìm đoạn mô tả thread đang chờ monitor mà thread khác giữ, rồi đối chiếu monitor của `LoaderA` và `LoaderB`.
4. Nếu JVM phát hiện vòng chờ Java-level, thread dump có thể có phần đại ý **“Found one Java-level deadlock”**. Không phải mọi tình huống treo đều được công cụ này phát hiện tự động.
5. Kiểm tra mô hình class loader và policy fallback: loader A muốn name nào từ B, loader B muốn name nào từ A; có cách kết thúc hoặc class owner rõ không?
6. Xem các khóa **ngoài loader** (registry cache lock, framework synchronization, `<clinit>`, lock của plugin); class-loading lock không nhất thiết là nguyên nhân duy nhất.
7. Tìm cách tái hiện trong test bằng latch/barrier thay vì `sleep`, để đảm bảo thứ tự hai thread giữ lock như ví dụ ở trên.

### Dùng ThreadMXBean khi cần

Java cung cấp `java.lang.management.ThreadMXBean` để truy vấn deadlock liên quan **object monitor** và, tùy runtime/API, **ownable synchronizer**.

Ví dụ **fragment** (chỉ minh họa, không tự thiết lập deadlock):

~~~java
java.lang.management.ThreadMXBean bean =
        java.lang.management.ManagementFactory.getThreadMXBean();

long[] deadlocked = bean.findDeadlockedThreads();

if (deadlocked != null) {
    System.out.println("Deadlocked thread count: "
            + deadlocked.length);
}
~~~

`findDeadlockedThreads()` có thể trả `null` nếu không phát hiện chu trình tại thời điểm gọi. Nó không bảo đảm phát hiện mọi dạng vòng chờ ở mức ứng dụng, JNI, I/O, `CountDownLatch` hoặc class initialization, nên cần đọc stack trace và hệ thống khóa thực tế. Đặc biệt, trong ví dụ `CrossLoaderDeadlockDemo`, các thread chết treo do **hai monitor của loader**; việc lấy snapshot đúng thời điểm có thể phát hiện nhưng không cần để chứng minh deadlock.

**Các chi tiết giúp phân biệt:**

| Triệu chứng | Gợi ý điều tra |
| --- | --- |
| Hai thread đều `BLOCKED` và mỗi thread giữ monitor loader kia cần | Deadlock monitor/cross-delegation đáng nghi. |
| `WAITING` trên class initialization | Có thể là chu trình khởi tạo class hoặc chờ tác vụ khác, không nên vội kết luận loader lock. |
| Một thread chạy dài với stack `loadClass→findClass→peer.loadClass` lặp | Có thể là **đệ quy ủy quyền vô hạn** trên một thread. |
| `ClassNotFoundException` nhanh và xác định | Thường là đường tìm không thấy class, không phải deadlock. |
| `LinkageError` khi nạp đồng thời | Có thể định nghĩa trùng hoặc loader constraints; đừng coi là deadlock chỉ vì đều xảy ra lúc loading. |
| Chỉ treo sau redeploy | Kiểm tra class loader cũ bị giữ bởi thread, cache, registry và callback. |

## 8. Cách phòng tránh và khắc phục

### 8.1. Ưu tiên đồ thị nạp không chu trình

Parent delegation từ plugin tới shared API/runtime thường tạo một đồ thị có hướng một chiều, dễ kiểm soát. Đưa class/API dùng chung về loader **cao hơn hoặc độc lập và ổn định**, không bắt loader cha phải hỏi ngược loader con để tìm dependency.

### 8.2. Thống nhất ownership cho mỗi binary name

Với `com.acme.api.*`, xác định một defining loader chung. Với `plugin.a.impl.*` hoặc `plugin.b.impl.*`, xác định loader riêng. Nếu một yêu cầu không thuộc phạm vi loader và không có lộ trình kết thúc, báo `ClassNotFoundException` thay vì hỏi peer vô hạn.

### 8.3. Không giữ khóa rộng khi gọi loader không kiểm soát

Nếu code tự viết thêm `synchronized (this)`, `synchronized (registry)` hoặc global lock bao quanh lookup chéo, hãy cân nhắc thu hẹp critical section. Nhưng **không tùy tiện bỏ khóa nạp lớp chuẩn**: thao tác kiểm tra đã nạp, định nghĩa và resolve vẫn cần tuân theo hợp đồng JVM. Cách tốt hơn là thiết kế lộ trình một chiều, tránh callback tùy ý khi đang giữ khóa.

### 8.4. Dùng parallel-capable khi thread-safety thực sự đáp ứng

Đăng ký parallel-capable có thể giảm contention cho những tên class **khác nhau**, nhưng phải kiểm tra mọi state dùng chung của loader và **không coi là fix cho vòng A→B→A**. Nếu một chu trình tồn tại trên chính những class đang được nạp, per-name lock vẫn có thể deadlock.

### 8.5. Chặn lặp ở tầng điều phối và fail fast

Nếu kiến trúc phải có lookup qua nhiều nguồn, có thể xây một resolver với đồ thị được validate trước, hoặc theo dõi đường đi `A → B → C` và từ chối khi gặp lại loader/name theo logic phù hợp. Đừng dựa vào một `ThreadLocal` đơn giản làm biện pháp duy nhất cho deadlock **giữa hai thread**: mỗi thread có thể nhìn một nửa chu trình và không thấy quan hệ chờ xuyên thread.

### 8.6. Viết test concurrency

- Tạo tình huống hai thread bắt đầu yêu cầu hai loader cùng lúc bằng `CountDownLatch`/`CyclicBarrier`.
- Dùng timeout ở **test harness** và thu thread dump khi vượt thời gian.
- Xác nhận lớp được trả đúng defining loader và không có `LinkageError` do định nghĩa trùng.
- Kiểm tra cả đường thành công, class không tồn tại, plugin restart/redeploy và shutdown.
- Dùng một mô hình với API dùng chung và hai implementation riêng để đảm bảo class loader không hỏi nhau vô hạn.

Đối với các test cố tình tạo deadlock, nên chạy trong **process cô lập** hoặc daemon thread như ví dụ, để không làm treo toàn bộ bộ test. Không đưa code cố ý deadlock vào loader production.

## 9. Những hiểu nhầm cần tránh

**“ClassLoader chỉ có một khóa toàn cục của JVM.”** Không. Cơ chế nạp lớp và locking phụ thuộc loader/parallel-capable; ở loader không parallel-capable, khóa mặc định gắn với **instance loader**, không phải một monitor duy nhất cho mọi loader của JVM.

**“registerAsParallelCapable chữa mọi deadlock.”** Không. Nó cho phép lock theo tên và giảm tranh chấp, nhưng **không giải quyết vòng chờ giữa hai lock cụ thể** hoặc lock bên ngoài.

**“Có parent chung thì mọi kiểu luôn cùng identity.”** Không. Parent phải thực sự định nghĩa class đó. Nếu mỗi child vẫn tự định nghĩa cùng binary name, đó là hai kiểu riêng; policy delegation phải được áp dụng nhất quán.

**“Nếu chỉ một thread thì không có vấn đề gì.”** Không. Có thể không xảy ra *deadlock giữa hai thread*, nhưng vòng ủy quyền không có điểm dừng có thể gây đệ quy vô hạn hoặc failure khác.

**“Chỉ cần nâng timeout hoặc giảm số thread.”** Điều này có thể che lịch chạy dẫn tới deadlock, không sửa đồ thị phụ thuộc vòng.

**“Class initialization lock cũng chính là monitor của loader.”** Không. Thủ tục khởi tạo class có cơ chế đồng bộ riêng theo JVM. Hãy đọc thread dump để xác định loại khóa liên quan.

**“Bắt mọi lỗi load rồi thử loader khác là an toàn.”** Không. `ClassFormatError`, `LinkageError`, `NoClassDefFoundError` hoặc lỗi initialization có thể báo sai code/dependency nghiêm trọng, không tương đương `ClassNotFoundException` để fallback mù quáng.

## 10. Tự kiểm tra

**Câu 1.** T1 giữ monitor loader A rồi đợi monitor B; T2 giữ monitor B rồi đợi monitor A. Đây là hiện tượng gì?

**Đáp án:** **Deadlock** do circular wait; cả hai không thể hoàn thành khi mỗi thread giữ khóa mà thread kia cần.

**Câu 2.** `ClassLoader` không parallel-capable thường trả loại khóa nào từ `getClassLoadingLock(name)`?

**Đáp án:** Chính đối tượng loader, tức mọi tên class trong loader đó dùng cùng monitor mặc định.

**Câu 3.** Chuyển sang parallel-capable có bảo đảm loại deadlock chéo A/B không?

**Đáp án:** Không. Nếu các yêu cầu tạo vòng chờ trên hai khóa theo tên, deadlock vẫn có thể xảy ra.

**Câu 4.** Nếu A hỏi B, B không thấy rồi hỏi ngược A trên một thread, chắc chắn có monitor deadlock không?

**Đáp án:** Không. Khóa monitor của cùng thread có tính reentrant; đường đi không có điểm dừng có thể đệ quy mãi và cuối cùng gây `StackOverflowError` hoặc failure khác.

**Câu 5.** Thiết kế hai plugin có API chung và implementation riêng nên đặt lớp ở đâu?

**Đáp án:** API chung do shared/parent loader định nghĩa; implementation được đặt tại loader riêng của từng plugin. Hạn chế lookup implementation chéo và bảo đảm đồ thị ủy quyền có hướng không tạo vòng.

**Câu 6.** Có nên bỏ `synchronized` quanh mọi `loadClass` để chữa treo không?

**Đáp án:** Không. Bỏ đồng bộ tùy tiện có thể gây race/định nghĩa trùng. Phải sửa đồ thị gọi chéo và thực hiện thread-safety, parent delegation/parallel loading đúng hợp đồng.

## Ghi nhớ

**Deadlock khi nhiều loader ủy quyền chéo** xảy ra khi các thread nạp lớp giữ những **class-loading lock** khác nhau và lần lượt chờ khóa của loader còn lại. Để tránh, hãy **loại chu trình ủy quyền**, xác định defining loader sở hữu mỗi class/API, dùng parent/shared loader cho contract chung, giới hạn cross-loader lookup và kiểm tra concurrency bằng thread dump. **Parallel-capable cải thiện khả năng nạp song song nhưng không thay thế thiết kế đồ thị không chu trình.**

**Tài liệu chính thức:**

- Java SE 17 API, `ClassLoader`: `loadClass`, `getClassLoadingLock` và `registerAsParallelCapable` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification §5.3 — *Creation of Classes and Interfaces* — https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java SE 17 API, `ThreadMXBean` — https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 17 API, `CountDownLatch` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 17 API, `Thread` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
