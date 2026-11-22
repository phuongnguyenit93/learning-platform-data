# Đồng bộ khởi tạo lớp giữa nhiều luồng trong Java

## 1. Vấn đề: nhiều luồng đồng thời dùng một lớp chưa khởi tạo

Khi một lớp Java được sử dụng chủ động (*active use*) lần đầu, JVM phải bảo đảm lớp được **khởi tạo** trước khi hoạt động đó tiếp tục. Ví dụ, nhiều luồng cùng đọc `Configuration.PORT`, gọi `Registry.lookup()` hoặc thực hiện `new Service()`. Nếu lớp chưa khởi tạo, cần xác định **luồng nào thực thi mã khởi tạo tĩnh**, những luồng còn lại đợi thế nào và kết quả được công bố ra sao.

Đối với **một định nghĩa lớp runtime**, JVM bảo đảm:

- Chỉ **một luồng** thực hiện khởi tạo tĩnh của lớp trong một lượt initialization; các luồng khác yêu cầu khởi tạo cùng lớp phải đợi khi cần.
- Khi khởi tạo **thành công**, JVM ghi nhận lớp đã khởi tạo; những lần sử dụng sau không chạy lại `<clinit>`.
- Những luồng tiếp tục sau khi lớp được khởi tạo nhìn thấy kết quả khởi tạo theo bảo đảm *happens-before* của Java Memory Model.
- Nếu khởi tạo **thất bại**, lớp chuyển sang trạng thái lỗi (*erroneous*); JVM không tự chạy lại initializer trên cùng định nghĩa lớp.

Điểm quan trọng: một định nghĩa lớp được xác định bởi **(tên nhị phân, defining class loader)**. Hai class loader khác nhau tự định nghĩa cùng tên `com.example.Configuration` tạo thành hai kiểu runtime khác nhau, nên chúng có trạng thái và quá trình khởi tạo riêng.

Cơ chế này thuộc JVM, không cần người lập trình tự `synchronized` mọi static initializer. Tuy nhiên, nó **không** tự bảo đảm thread safety cho mọi thao tác sửa trường tĩnh sau khi initialization hoàn tất.

## 2. Phải phân biệt loading, linking và initialization

Vòng đời của một lớp gồm những hoạt động có ý nghĩa khác nhau:

1. **Loading:** tìm hoặc tạo biểu diễn runtime từ định nghĩa nhị phân của class/interface.
2. **Linking:** verification, preparation và resolution theo các quy tắc JVM.
3. **Initialization:** thực thi các khai báo khởi tạo biến tĩnh và khối `static` theo thứ tự được chỉ định; compiler thường tạo phương thức đặc biệt `<clinit>` cho mã cần thực thi.

Bài này phân tích bước **initialization**. Nạp được `SomeClass.class` không có nghĩa initializer đã chạy.

Ví dụ minh họa (đoạn class, chưa phải chương trình độc lập):

```java
class Settings {
    static final int PORT_CONSTANT = 8080;
    static final int PORT_RUNTIME = readPort();

    static int readPort() {
        System.out.println("Settings initialized");
        return 9090;
    }
}
```

- `Settings.PORT_CONSTANT` là *constant variable* (primitive `static final` được gán biểu thức hằng tại compile time); truy cập giá trị hằng này có thể được compiler inline và **không buộc** khởi tạo `Settings`.
- `Settings.PORT_RUNTIME` được gán bằng lời gọi phương thức, không phải constant variable. Truy cập `getstatic` tới trường này là active use, có thể kích hoạt khởi tạo.
- `Settings.class` hoặc `Class.forName("Settings", false, loader)` không chủ động yêu cầu khởi tạo lớp.
- `Class.forName("Settings", true, loader)` hoặc `Class.forName("Settings")` yêu cầu initialization; nếu lớp đã được khởi tạo thì không chạy lại.

Một luồng có thể nhìn thấy đối tượng `Class<?>` sớm hơn lúc mã `static` chạy. Đọc log *class loading* vì thế khác với đọc các dòng log in từ initializer.

## 3. Đặc tả JLS §12.4.2: trạng thái và khóa khởi tạo riêng của mỗi lớp

Java Language Specification §12.4.2 mô tả quy trình chi tiết với một **khóa khởi tạo duy nhất** `L_C` cho mỗi lớp hoặc interface `C`.

| Trạng thái của C | Ý nghĩa |
| --- | --- |
| Chưa được khởi tạo | Chưa có luồng nào thực hiện initialization |
| Đang được khởi tạo bởi luồng T | T chịu trách nhiệm chạy initialization |
| Đã khởi tạo thành công | Các yêu cầu sau sử dụng trạng thái đã công bố |
| Ở trạng thái lỗi (*erroneous*) | Initialization đã thất bại; không được thử lại trên chính lớp runtime đó |

Khi một luồng muốn khởi tạo `C`, JVM thực hiện thủ tục về mặt khái niệm:

1. Đồng bộ trên khóa `L_C` để kiểm tra trạng thái của `C`.
2. **Nếu đã khởi tạo thành công:** nhả khóa rồi kết thúc thủ tục.
3. **Nếu một luồng khác đang khởi tạo C:** nhả khóa và chờ quá trình đó kết thúc; sau khi tỉnh dậy, kiểm tra lại trạng thái.
4. **Nếu chính luồng hiện tại đang khởi tạo C:** xử lý yêu cầu khởi tạo lặp trong cùng luồng như hoàn tất bình thường, tránh tự đợi chính mình.
5. **Nếu C đang erroneous:** nhả khóa và ném `NoClassDefFoundError` cho yêu cầu khởi tạo về sau.
6. **Nếu chưa khởi tạo:** đánh dấu C đang được khởi tạo bởi luồng hiện tại, **nhả khóa khởi tạo**, thực hiện các bước liên quan và chạy initialization theo đặc tả.
7. Khi hoàn tất hoặc thất bại, đồng bộ để ghi trạng thái kết quả và thông báo các luồng đang chờ.

**Không giữ khóa L_C suốt toàn bộ mã initializer.** Đây là chi tiết dễ hiểu sai: JVM dùng khóa để điều phối trạng thái chờ và kết thúc; nó không cần giữ khóa init trong khi thực thi tất cả câu lệnh bên trong `<clinit>`. JVM còn có quyền tối ưu việc đồng bộ khi vẫn bảo toàn quan hệ *happens-before*.

Đừng dựa vào giả định `synchronized (C.class)` là cách công khai để nắm chính xác khóa `L_C` nội bộ của JVM. Mục đích của `synchronized (C.class)` là khóa monitor của đối tượng `Class` trong code ứng dụng; đặc tả initialization có quy tắc riêng.

### 3.1. Hai luồng nhìn thấy điều gì?

```text
Thời gian   Thread A                          Thread B
---------   --------------------------------  --------------------------------
t0          đọc Config.VALUE                 đọc Config.VALUE
t1          nhận quyền init Config             thấy Config đang init bởi A
t2          chạy code initialization          đợi kết quả initialization
t3          đánh dấu init thành công
t4                                            tỉnh dậy, kiểm tra trạng thái
t5          tiếp tục dùng VALUE               tiếp tục dùng VALUE đã khởi tạo
```

Không có bảo đảm **A sẽ luôn thắng**: scheduler, việc nạp trước đó và thời điểm gọi quyết định luồng nào đến trước. JVM chỉ bảo đảm **không có hai lượt initialization chạy song song trên cùng runtime Class**.

## 4. Ví dụ Java 17+: bốn luồng, một lượt static initialization

Chương trình dùng ba `CountDownLatch` để bốn worker cùng sẵn sàng rồi bắt đầu đọc `Configuration.PORT`. Để stdout xác định, worker chỉ ghi vào một phần tử mảng riêng; main chờ tất cả hoàn thành và in kết quả theo thứ tự đã biết.

Lưu file `ConcurrentClassInitializationDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class ConcurrentClassInitializationDemo {

    static class Configuration {
        static int initializationCount;
        static final int PORT = initialize();

        private static int initialize() {
            initializationCount++;
            System.out.println("init: begin");
            try {
                Thread.sleep(150); // Mô phỏng bước init chậm.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("init interrupted", e);
            }
            System.out.println("init: end");
            return 8080;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        int workers = 4;
        int[] observed = new int[workers];

        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(workers);

        for (int i = 0; i < workers; i++) {
            final int index = i;
            Thread thread = new Thread(() -> {
                ready.countDown();
                try {
                    start.await();
                    observed[index] = Configuration.PORT;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                } finally {
                    finished.countDown();
                }
            }, "reader-" + i);
            thread.start();
        }

        ready.await();
        start.countDown();
        finished.await();

        System.out.println("initializations=" +
                Configuration.initializationCount);
        System.out.println("values=" + Arrays.toString(observed));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ConcurrentClassInitializationDemo.java
java ConcurrentClassInitializationDemo
```

Stdout trong điều kiện chạy bình thường, không bị ngắt ngoài ý muốn:

```text
init: begin
init: end
initializations=1
values=[8080, 8080, 8080, 8080]
```

Giải thích:

1. `PORT` được gán bằng `initialize()`, nên **không phải** compile-time constant và có thể kích hoạt initialization khi đọc.
2. `ready` bảo đảm bốn worker đều đến điểm chờ trước khi `start` được mở. Nó tạo điều kiện để tranh chấp nhưng không bảo đảm tất cả thật sự chạy cùng một lệnh `getstatic` trong cùng một nano-giây.
3. Luồng nào đến `Configuration.PORT` trước có thể nhận quyền chạy initializer. Các luồng khác yêu cầu khởi tạo trong lúc đó phải chờ, không thực thi `initialize()` thêm lần nữa.
4. `initializationCount` vì vậy bằng 1. Hai dòng `init` chỉ xuất hiện một lượt.
5. Sau khi `finished.await()` hoàn tất, main thấy các phép ghi vào `observed` của worker; mảng được in theo thứ tự index nên kết quả không thay đổi do scheduler.
6. `Thread.sleep(150)` chỉ để làm thời gian khởi tạo dễ quan sát, **không** mang lại thread safety.

**Phân biệt hai bảo đảm đồng bộ:** Class initialization công bố giá trị `Configuration.PORT`; `CountDownLatch` trong ví dụ còn bảo đảm main đợi cả bốn worker xong trước khi đọc mảng `observed`.

## 5. Happens-before: tại sao trạng thái tĩnh ban đầu được công bố đúng?

Việc chỉ cho một luồng chạy initializer chưa đủ: JVM còn phải bảo đảm các luồng đã vượt qua bước kiểm tra initialization có thể quan sát giá trị được thiết lập trong quá trình đó.

Theo Java Memory Model và JLS §12.4.2, các thao tác đồng bộ trong initialization tạo/bảo toàn quan hệ **happens-before** cần thiết. Khi một lớp khởi tạo thành công, các luồng dùng lớp sau đó không cần tự tạo thêm hàng rào bộ nhớ chỉ để nhìn thấy đúng giá trị mà initializer đã gán.

Ví dụ (class minh họa):

```java
final class Catalog {
    static final java.util.Map<String, Integer> PORTS = build();

    private static java.util.Map<String, Integer> build() {
        java.util.Map<String, Integer> data = new java.util.HashMap<>();
        data.put("http", 8080);
        data.put("admin", 9090);
        return java.util.Collections.unmodifiableMap(data);
    }
}
```

Các luồng đọc `Catalog.PORTS` sau khi init thành công sẽ quan sát cấu trúc đã chứa hai entry. Map gốc chỉ là biến cục bộ trong `build()`, không bị lộ ra nơi khác để sửa sau khi khởi tạo.

Tuy nhiên, việc công bố đúng **trạng thái ban đầu** không làm các thao tác ghi về sau tự đồng bộ:

```java
class Counter {
    static int count;

    static void increment() {
        count++; // Không atomic khi nhiều thread cùng cập nhật.
    }
}
```

`Counter.count++` vẫn là thao tác đọc–sửa–ghi có thể race giữa các thread. Cần `AtomicInteger`, `synchronized`, lock hoặc thiết kế bất biến thích hợp. `volatile` riêng lẻ cũng **không** biến `count++` thành thao tác atomic.

## 6. Yêu cầu initialization lặp lại trên chính luồng đang khởi tạo

Điểm khác biệt giữa **luồng khác** và **chính luồng đang khởi tạo** là thiết yếu.

Một initializer có thể gọi static method của chính lớp hoặc gián tiếp quay lại cần khởi tạo cùng lớp. JVM nhận ra trạng thái “đang được khởi tạo bởi thread hiện tại” và không đợi lại. Nhưng vì initializer chưa hoàn tất, những static field được gán **sau** vị trí hiện tại vẫn có thể đang ở giá trị mặc định từ bước preparation.

Lưu ví dụ độc lập `RecursiveInitializationDemo.java`:

```java
public class RecursiveInitializationDemo {

    static class State {
        static int early = readLater();
        static int later = 42;

        static int readLater() {
            return later;
        }
    }

    public static void main(String[] args) {
        System.out.println("early=" + State.early);
        System.out.println("later=" + State.later);
    }
}
```

```bash
javac RecursiveInitializationDemo.java
java RecursiveInitializationDemo
```

Stdout:

```text
early=0
later=42
```

Tại lúc chạy `readLater()` để gán `early`, luồng hiện tại đã ở trong quá trình khởi tạo `State`. `later` đã có giá trị mặc định `0` từ preparation nhưng lệnh `later = 42` chưa đến lượt chạy. Khi initializer hoàn thành, `later` mới bằng `42`.

Đây là lời cảnh báo về **thứ tự khai báo static field** và vòng gọi trong initializer. Khởi tạo lặp **cùng thread** không chờ vô hạn, nhưng có thể khiến logic thấy trạng thái khởi tạo dở dang.

## 7. Failure: nếu initializer thất bại thì các luồng còn lại ra sao?

Nếu static initializer ném một ngoại lệ chưa được xử lý, JVM đánh dấu lớp ở trạng thái **erroneous**, đánh thức các luồng đang đợi, và không thử khởi tạo lại định nghĩa lớp đó.

- Nếu nguyên nhân được ném ra **không phải một `Error`**, JVM thường bọc nó bằng `ExceptionInInitializerError` cho luồng thực hiện initializer (theo quy tắc của đặc tả).
- Nếu nguyên nhân vốn là `Error`, JVM truyền tiếp đối tượng lỗi thay vì bọc giống một exception thông thường.
- Các thread đã đợi và những lần active use sau khi lớp ở trạng thái erroneous thường nhận `NoClassDefFoundError`. Cần xem cả nguyên nhân ban đầu trong log, vì thông báo của lượt sau có thể không chỉ ra toàn bộ lỗi gốc.

Ví dụ độc lập `FailedInitializationDemo.java`:

```java
public class FailedInitializationDemo {

    static class Broken {
        static final int VALUE = parse();

        private static int parse() {
            throw new IllegalArgumentException("invalid configuration");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.VALUE);
            } catch (LinkageError error) {
                System.out.println("attempt-" + attempt + ": " +
                        error.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac FailedInitializationDemo.java
java FailedInitializationDemo
```

Stdout trong ví dụ:

```text
attempt-1: ExceptionInInitializerError
attempt-2: NoClassDefFoundError
```

Lượt đầu `Broken.VALUE` kích hoạt `parse()`, nó ném `IllegalArgumentException`. JVM bọc trong `ExceptionInInitializerError` và đánh dấu `Broken` erroneous. Lượt hai, JVM không gọi `parse()` nữa.

Việc `catch (LinkageError)` có mặt trong ví dụ chỉ để **quan sát tên lỗi**; trong hệ thống thật, không nên tùy tiện nuốt các `Error` quan trọng rồi tiếp tục chạy như thể trạng thái ứng dụng vẫn hợp lệ.

### Failure từ lớp cha hoặc superinterface

Khi initialization của một lớp phải khởi tạo superclass và những superinterface có khai báo default method theo quy tắc đặc tả, lỗi ở một phụ thuộc cần khởi tạo có thể làm quá trình khởi tạo lớp con không thành công. JVM không bỏ qua lỗi để hoàn thành lớp con.

Phải phân biệt hai dạng lỗi:
- **Thiếu class lúc loading/linking**: chẳng hạn `NoClassDefFoundError` vì thiếu superclass cần thiết.
- **Class đã được định nghĩa nhưng initializer thất bại**: nguyên nhân thường nằm ở mã `static`, cấu hình hoặc tác vụ được gọi trong init.

Cùng tên exception ở log không đủ để xác định loại lỗi; phải xem thời điểm, stack trace và chuỗi `Caused by`.

## 8. Deadlock giữa các lớp khi những luồng khác nhau khởi tạo chéo

JVM tránh trường hợp **một thread tự chờ chính nó khi khởi tạo lại cùng class**, nhưng không bảo đảm tránh mọi kiểu deadlock trong hệ thống nhiều lớp và nhiều thread.

Giả sử:
- Thread T1 đang khởi tạo `A`. Trong static initializer của `A`, nó cần sử dụng `B` và yêu cầu `B` khởi tạo xong.
- Thread T2 đang khởi tạo `B`. Trong static initializer của `B`, nó lại cần `A` hoàn tất initialization.

```text
T1: owns initialization of A -> needs B -> waits for T2
T2: owns initialization of B -> needs A -> waits for T1
```

Đây là **vòng chờ**; chương trình có thể treo. Khác với ví dụ đọc `State.later` ở cùng thread, hai thread không được bỏ qua một lớp do thread khác đang khởi tạo.

Để giảm nguy cơ:

1. Giữ static initializer ngắn; ưu tiên xây dựng dữ liệu bất biến và không có side effect dài.
2. Tránh trong static initializer những thao tác `Future.get()`, `Thread.join()`, callback, remote calls hoặc đợi singleton của lớp có quan hệ phụ thuộc vòng.
3. Tách các bước bootstrapping có khả năng chờ/block thành thủ tục ứng dụng có thứ tự rõ ràng, ngoài `<clinit>` khi phù hợp.
4. Không mở thread trong initializer rồi chờ thread ấy hoàn tất nếu thread mới có thể tham chiếu trở lại lớp đang init.
5. Khi ứng dụng treo lúc start, lấy thread dump (ví dụ `jcmd <pid> Thread.print` khi attach khả dụng) và đối chiếu stack của các thread tham gia class initialization.

Không nên cho rằng mọi công cụ phát hiện deadlock của object monitor đều tự mô tả đầy đủ vòng đợi liên quan initialization; thread dump và đồ thị phụ thuộc vẫn cần phân tích.

## 9. Ranh giới ClassLoader: cùng tên không nhất thiết cùng lượt khởi tạo

Trong hệ thống plugin, container hoặc môi trường reload động:

```text
ApplicationLoader
  |- Config (defined by application loader; one init state)
  |
  |- PluginLoader A
  |    |- PluginA (uses shared Config)
  |
  |- PluginLoader B
       |- PluginB (uses shared Config)
```

Nếu cả hai plugin **ủy quyền** cho loader cha và nhận chính lớp `Config` do cha định nghĩa, chúng chia sẻ trạng thái initialization duy nhất của `Config`.

Ngược lại:

```text
PluginLoader A -> defines com.example.Config -> init state A
PluginLoader B -> defines com.example.Config -> init state B
```

Nếu mỗi plugin **tự định nghĩa** `com.example.Config`, JVM xem đó là hai runtime Class riêng. Mỗi bên có static state, một lần initialization thành công (nếu thành công) và cơ chế điều phối riêng.

| Điều kiện | Có dùng chung initialization không? |
| --- | --- |
| Nhiều thread dùng cùng `Class<?>` | Có |
| Hai loader con cùng delegate tới một định nghĩa từ cha | Có |
| Hai loader khác nhau tự định nghĩa cùng binary name | Không |
| Một `Class<?>` đã khởi tạo thành công từ trước | Không khởi tạo lại |
| Một `Class<?>` đã erroneous | Không tự thử lại; yêu cầu init về sau bị lỗi |

Vì thế, việc thấy log “initialized” hai lần chưa đủ kết luận JVM phá quy tắc; phải so sánh **defining loader** của hai bản lớp. Ngược lại, một lớp bị erroneous trong loader cũ không làm một định nghĩa runtime hoàn toàn mới ở loader khác tự động erroneous.

## 10. Ứng dụng: initialization-on-demand holder cho lazy singleton

Một ví dụ thực dụng của đồng bộ JVM là **initialization-on-demand holder idiom**. Instance chỉ được tạo khi code lần đầu yêu cầu static field của lớp `Holder`.

Lưu file `LazyHolderDemo.java`:

```java
public class LazyHolderDemo {

    static final class Service {
        private Service() {
            System.out.println("Service constructed");
        }

        static Service instance() {
            return Holder.INSTANCE;
        }

        private static final class Holder {
            static final Service INSTANCE = new Service();
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        Service a = Service.instance();
        Service b = Service.instance();
        System.out.println("same=" + (a == b));
    }
}
```

```bash
javac LazyHolderDemo.java
java LazyHolderDemo
```

Stdout:

```text
before
Service constructed
same=true
```

Lần đầu `Holder.INSTANCE` được đọc, JVM điều phối initialization của `Holder`. Mã tạo `Service` chạy một lần cho cùng `Holder` runtime, và tham chiếu được công bố an toàn cho các thread. Cách này tránh phải đặt `synchronized` trên mọi lời gọi `instance()` chỉ để khởi tạo lazy singleton.

**Giới hạn:** một loader khác tự định nghĩa `Holder` có thể tạo singleton riêng; lỗi trong constructor làm initialization của `Holder` thất bại; trạng thái mutable bên trong `Service` vẫn cần thread safety riêng.

## 11. Ngộ nhận và lỗi thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “`static` chạy một lần duy nhất trong cả JVM.” | Một lần khởi tạo thành công cho **mỗi định nghĩa runtime Class**; nhiều loader có thể có nhiều định nghĩa. |
| “Hai thread có thể chạy cùng `<clinit>` song song.” | JVM điều phối để chỉ một thread thực hiện initialization của cùng lớp. |
| “JVM giữ `synchronized(C.class)` qua toàn bộ `<clinit>`.” | Khóa khởi tạo là cơ chế đặc tả riêng; không nên đồng nhất với monitor ứng dụng. |
| “Cứ đọc `static final` là khởi tạo lớp.” | Trường constant variable có thể được inline nên không bắt buộc init. |
| “Initialization xong thì mọi cập nhật static đều thread-safe.” | Cập nhật mutable sau đó vẫn cần đồng bộ thích hợp. |
| “Nếu `<clinit>` lỗi, thread sau sẽ thử lại.” | Cùng runtime Class sẽ giữ trạng thái erroneous; yêu cầu init tiếp bị lỗi. |
| “Recursive static call trên cùng thread luôn deadlock.” | JVM cho phép khởi tạo đệ quy cùng thread kết thúc bình thường; nhưng có thể thấy giá trị mặc định. |
| “JVM không thể deadlock lúc class init.” | Hai thread chờ hai lớp khởi tạo chéo có thể deadlock. |
| “Log trong `static` cho biết thứ tự loading.” | Log đó phản ánh initialization, không nhất thiết loading. |

## 12. Chẩn đoán một lỗi initialization đa luồng

Khi ứng dụng treo hoặc nhiều luồng nhận `NoClassDefFoundError` ở lần dùng lớp đầu:

1. **Xác định đúng lớp runtime.** In `type.getName()` và `type.getClassLoader()` khi có đối tượng `Class<?>`; `null` ở `getClassLoader()` thường chỉ bootstrap loader.
2. **Xác định active use đã kích hoạt init.** Chẳng hạn `new`, truy cập static field không phải hằng biên dịch, gọi static method hay API reflection yêu cầu init.
3. **Đọc toàn bộ static field initializer và `static {}`.** Chú ý thứ tự khai báo, method call gián tiếp và initializer lớp cha.
4. **Tìm thread đầu tiên khởi tạo.** Lấy thread dump để xác định nơi luồng đang chạy/chờ; đừng chỉ xem exception cuối cùng của các thread bị đánh thức.
5. **Tìm lỗi gốc.** Lần đầu có thể báo `ExceptionInInitializerError` với `Caused by` hữu ích; lần sau thường chỉ `NoClassDefFoundError` do trạng thái erroneous.
6. **Kiểm tra vòng phụ thuộc class A–B hoặc chờ task được khởi động từ `<clinit>`.**
7. **Với plugin, xác định defining loader và bản JAR thực sự.** Hai class cùng tên không đảm bảo chung một initialization.
8. **Nếu initializer đã thành công nhưng dữ liệu vẫn race, kiểm tra các ghi sau đó** và các quan hệ happens-before của ứng dụng thay vì sửa nhầm luồng init.

Trên JVM Java 17+ hỗ trợ unified logging, có thể quan sát quá trình **loading** bằng:

```bash
java -Xlog:class+load=info ConcurrentClassInitializationDemo
```

Đây là log loading; để biết initializer thực thi lúc nào, hãy kết hợp log từ mã `<clinit>` và stack/thread dump. Lệnh `jcmd <pid> Thread.print` cần quyền attach thích hợp và có thể thay đổi khả dụng theo môi trường.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Ba thread cùng chạm vào `Config.VALUE` lần đầu, cùng một defining loader. Mã `static` của `Config` có thể in “init” ba lần không?

**Trả lời:** Không. Chỉ một thread thực hiện initialization cho cùng runtime Class; các thread khác chờ khi cần rồi dùng kết quả.

**Câu 2.** Khởi tạo thành công rồi, hai thread thực hiện `Counter.count++`. Có chắc tăng đúng hai đơn vị không?

**Trả lời:** Không. `count++` không atomic; synchronization lúc initialization không bảo vệ các cập nhật sau đó.

**Câu 3.** Vì sao `State.early` bằng 0 trong ví dụ đệ quy?

**Trả lời:** `State.readLater()` chạy trước câu lệnh gán `later = 42` trong cùng quá trình initialization; lúc đó `later` còn giá trị mặc định từ preparation.

**Câu 4.** Vì sao truy cập `Broken.VALUE` lần đầu ra `ExceptionInInitializerError`, lần hai ra `NoClassDefFoundError`?

**Trả lời:** Lượt đầu initializer ném exception khiến JVM đánh dấu lớp erroneous; những lượt sau không chạy lại initializer.

**Câu 5.** Hai plugin mỗi bên tự định nghĩa `Config` cùng tên, và mỗi bên in “initialized” một lần. Có trái đặc tả không?

**Trả lời:** Không. Mỗi defining loader có một runtime Class riêng, nên mỗi lớp có lượt initialization riêng.

**Câu 6.** Thread A khởi tạo class A rồi cần B; thread B khởi tạo B rồi cần A. Có thể deadlock không?

**Trả lời:** Có. Hai yêu cầu chờ initialization qua hai thread tạo vòng chờ, khác với đệ quy cùng thread.

## 14. Kết luận và tài liệu chuẩn

Đồng bộ khởi tạo lớp là **hợp đồng của JVM theo từng runtime Class**: chỉ một thread thực hiện initialization, thread khác đợi kết quả khi cần, kết quả thành công được công bố đúng theo quan hệ *happens-before*, và trạng thái lỗi được ghi nhận để ngăn việc tự thử lại. Hãy tận dụng đặc tính này khi xây dựng dữ liệu tĩnh bất biến hoặc lazy holder, đồng thời tách rõ các vấn đề mutable state, vòng phụ thuộc giữa lớp và ranh giới class loader.

Tài liệu chính thức:

- JLS 17 §12.4.1, *When Initialization Occurs*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- JLS 17 §12.4.2, *Detailed Initialization Procedure*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- JVMS 17 §5.5, *Initialization*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- JLS 17 §17.4.5, *Happens-before Order*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5
