# Virtual thread chờ khởi tạo lớp và hành vi unmount trên Java 26

## 1. Mục tiêu và trạng thái hiện hành

Virtual thread được JVM mount lên một platform thread gọi là carrier để chạy Java code. Khi virtual thread chờ ở một thao tác có thể unmount, JVM lưu continuation của nó và trả carrier về scheduler để chạy virtual thread khác.

Trước JDK 26, một virtual thread truy cập lớp đang được một thread khác khởi tạo thường bị pin vào carrier trong lúc chờ class initializer hoàn tất. JDK 26 bổ sung khả năng preempt/unmount virtual thread ở các đường chờ khởi tạo lớp phổ biến. Thay đổi được ghi nhận trong JDK-8369238:

- Virtual thread chờ một thread khác chạy class initializer có thể unmount khỏi carrier trong hầu hết trường hợp.
- Carrier được trả về scheduler để chạy virtual thread khác.
- Điều này giảm carrier starvation và rủi ro deadlock trong một số tình huống khởi tạo lớp đồng thời.
- Ngữ nghĩa khởi tạo lớp của Java không thay đổi; chỉ thay đổi cách JVM giữ hoặc trả carrier khi một virtual thread phải chờ.

Đây là cải tiến runtime của HotSpot, không phải API Java mới, preview hoặc incubator. Không cần `--enable-preview` hay JVM flag riêng để bật. JDK 27 tiếp tục hỗ trợ virtual thread và cơ chế này.

Bài học giải thích class initialization lock, pinning, giới hạn của cơ chế unmount mới, cách viết static initializer an toàn và cách chẩn đoán bằng JFR/jcmd.

## 2. Virtual thread, carrier và mount/unmount

### 2.1. Virtual thread không gắn cố định với OS thread

Platform thread gắn với một OS thread trong suốt vòng đời. Virtual thread là một đối tượng `java.lang.Thread` do Java runtime lập lịch và có thể được mount lên các carrier khác nhau theo từng khoảng thực thi.

~~~text
Virtual thread V1 ----\
Virtual thread V2 -----+----> Scheduler ----> Carrier P1
Virtual thread V3 ----/                     -> Carrier P2
~~~

Khi virtual thread chạy, nó được mount lên carrier. Khi thực hiện một thao tác blocking mà JVM có thể xử lý bằng cách suspend continuation, virtual thread unmount và carrier được dùng cho virtual thread khác.

Ví dụ các thao tác blocking I/O được hỗ trợ thường cho phép virtual thread nhường carrier trong lúc chờ.

### 2.2. Pinning là gì?

Virtual thread bị pin khi không thể unmount trong lúc bị chặn. Khi đó carrier vẫn bị giữ, dù virtual thread không chạy Java code hữu ích.

Pinning không làm chương trình sai về mặt logic, nhưng nhiều virtual thread cùng pin có thể chiếm hết carrier và làm các virtual thread khác không được chạy.

Theo hướng dẫn virtual thread của JDK 26, những trường hợp quan trọng còn có thể pin gồm:

- Virtual thread chạy native method.
- Virtual thread chạy foreign function qua Foreign Function & Memory API.
- Một số đường chờ bên trong VM chưa thể preempt/unmount.

Pinning là vấn đề về khả năng mở rộng, không đồng nghĩa mọi blocking operation đều pin. Cần dùng JFR và thread dump để xác định trường hợp thực tế.

## 3. Java class initialization hoạt động như thế nào?

### 3.1. Khi nào một class được khởi tạo?

Class initialization xảy ra khi chương trình thực hiện một active use theo quy tắc của JVM, ví dụ:

- Tạo object bằng `new`.
- Gọi static method bằng `invokestatic`.
- Đọc hoặc ghi static field không phải constant variable bằng `getstatic` hoặc `putstatic`.
- Một số thao tác reflection như `Class.forName` yêu cầu khởi tạo class.

JVM thực hiện quá trình load, link và initialize theo quy tắc của Java Language Specification. Class initializer là phần static field initializer và static initializer block được trình biên dịch gom vào phương thức nội bộ `<clinit>()`.

### 3.2. Một thread khởi tạo, các thread khác phải chờ

Theo JLS `12.4.2, JVM đồng bộ hóa quá trình khởi tạo mỗi class bằng một initialization lock. Khi thread A đang chạy `<clinit>()`, thread B truy cập cùng class sẽ chờ cho đến khi quá trình khởi tạo hoàn tất.

Ví dụ:

~~~java
final class PluginRegistry {
    static final Map<String, Plugin> PLUGINS = loadPlugins();

    static Plugin find(String name) {
        return PLUGINS.get(name);
    }

    private static Map<String, Plugin> loadPlugins() {
        // Có thể đọc metadata, scan classpath hoặc khởi tạo plugin.
        return PluginLoader.loadAll();
    }
}
~~~

Nếu nhiều request đồng thời gọi `PluginRegistry.find()` lần đầu, chỉ một thread chạy `loadPlugins()`. Các thread còn lại phải đợi class initialization lock.

Cơ chế này đảm bảo các thread khác không quan sát được static field ở trạng thái khởi tạo dở dang. JDK 26 không thay đổi quy tắc này.

### 3.3. Chờ khởi tạo lớp khác với tranh chấp synchronized thông thường

Class initialization dùng synchronization nội bộ của JVM. Đây là đường chờ đặc biệt trong quá trình link/initialize class; không nên đánh đồng mọi trường hợp này với việc ứng dụng tự viết một `synchronized` block.

Việc JDK 26 cho phép unmount trong lúc chờ class initialization không có nghĩa JVM bỏ initialization lock hoặc cho phép hai thread chạy `<clinit>()` đồng thời.

## 4. Vấn đề trước JDK 26: virtual thread chờ class initializer bị pin

Khi một virtual thread chạm vào class đang được thread khác khởi tạo, nó có thể phải chờ bên trong VM. Trước JDK 26, đường chờ này có native/VM frame trên stack khiến continuation không thể unmount. Virtual thread bị pin vào carrier cho đến khi class initializer hoàn tất.

Tình huống dễ gặp trong ứng dụng:

- Nhiều request cùng lần đầu truy cập một class registry.
- Một static initializer thực hiện thao tác chậm.
- Nhiều virtual thread chờ class initialization lock.
- Carrier pool có ít platform thread hơn số virtual thread đang chờ.

### 4.1. Ví dụ carrier starvation

Giả sử scheduler chỉ có một carrier để minh họa:

1. Virtual thread A kích hoạt class `SlowBootstrap` và bắt đầu chạy `<clinit>()`.
2. A chờ một latch hoặc thao tác I/O có thể unmount; carrier được trả lại scheduler.
3. Virtual thread B truy cập `SlowBootstrap` và phải chờ class initializer của A.
4. Trước JDK 26, B bị pin vào carrier trong lúc chờ initialization lock.
5. Virtual thread C đang được xếp hàng để giải phóng latch mà A chờ. Nhưng carrier duy nhất bị B pin nên C không được chạy.
6. A không thể hoàn tất class initialization cho đến khi C chạy; B không thể nhả carrier cho đến khi A hoàn tất.

Đây là tình huống carrier starvation có thể dẫn tới deadlock: thread giữ trách nhiệm hoàn tất class initialization đang chờ một virtual thread khác, nhưng carrier đã bị các virtual thread chờ class initialization chiếm hết.

### 4.2. Sơ đồ trước JDK 26

~~~mermaid
flowchart TD
    A["Virtual thread A"] --> B["Chạy class initializer"]
    B --> C["Chờ latch / I/O"]
    C --> D["A unmount, carrier được trả lại"]
    E["Virtual thread B"] --> F["Truy cập cùng class"]
    F --> G["Chờ initialization lock"]
    G --> H["B bị pin vào carrier"]
    I["Virtual thread C"] --> J["Cần chạy để mở latch cho A"]
    H -. "carrier bị giữ" .-> J
    J -. "không được scheduler chạy" .-> C
~~~

Sơ đồ minh họa điều kiện xấu nhất khi carrier pool không còn carrier rảnh. Trong production, scheduler có thể có nhiều carrier, nhưng khi tải tăng và nhiều thread cùng bị pin, vấn đề vẫn có thể xuất hiện.

## 5. JDK 26: unmount virtual thread trong lúc chờ class initialization

JDK 26 tích hợp thay đổi JDK-8369238: virtual thread chờ một thread khác khởi tạo class có thể được preempt và unmount khỏi carrier trong các đường khởi tạo phổ biến.

Khi B chờ initialization lock:

1. JVM nhận diện đây là đường VM có thể preempt.
2. Continuation của B được suspend.
3. B chuyển sang trạng thái chờ mà không giữ carrier.
4. Carrier được trả về virtual thread scheduler.
5. Scheduler có thể chạy C hoặc virtual thread khác.
6. Khi class initializer hoàn tất, B được schedule lại và tiếp tục từ điểm chờ.

### 5.1. Các đường bytecode được hỗ trợ trong implementation ban đầu

OpenJDK review của JDK-8369238 mô tả các đường phổ biến được xử lý:

| Đường truy cập | Bytecode/điểm gọi | Ví dụ |
|---|---|---|
| Tạo instance | `new` | `new PluginRegistry()` |
| Gọi static method | `invokestatic` | `PluginRegistry.find(name)` |
| Đọc static field | `getstatic` | `PluginRegistry.PLUGINS` |
| Ghi static field | `putstatic` | Ghi static field trong quá trình active use |

Thay đổi cũng xử lý các đường đồng bộ liên quan đến link class và initialization lock ở các điểm gọi này.

### 5.2. Vì sao release note ghi “in most cases”?

Không nên hiểu đây là bảo đảm mọi trường hợp class loading hoặc reflection đều unmount được.

OpenJDK review của implementation ban đầu nêu rõ những đường interpreter phổ biến như `new`, `invokestatic`, `getstatic` và `putstatic`. Các đường khởi tạo xuất phát từ native method, ví dụ `Class.forName0`, được nêu là hướng có thể mở rộng sau.

Vì vậy:

- Không giả định mọi thao tác reflection/class loading đều có cùng hành vi unmount.
- Không giả định một virtual thread đang chạy native hoặc foreign function sẽ tự unmount được.
- Nếu JFR vẫn ghi nhận class-initialization pinning trên JDK 26+, hãy xem stack trace, bytecode path, provider/agent và JDK update cụ thể.
- Dùng bản JDK update còn được nhà cung cấp hỗ trợ và kiểm tra release notes của bản đó.

### 5.3. Sơ đồ sau JDK 26

~~~mermaid
flowchart TD
    A["Virtual thread A"] --> B["Chạy class initializer"]
    B --> C["Chờ latch / I/O"]
    C --> D["A unmount"]
    E["Virtual thread B"] --> F["Truy cập cùng class"]
    F --> G["Chờ initialization lock"]
    G --> H["B preempt và unmount"]
    H --> I["Carrier được trả cho scheduler"]
    I --> J["Virtual thread C được chạy"]
    J --> K["Giải phóng latch"]
    K --> L["A hoàn tất initializer"]
    L --> M["B được schedule và tiếp tục"]
~~~

JDK 26 làm giảm khả năng các waiter giữ hết carrier. Nó không chạy class initializer song song và không loại bỏ thời gian chờ của các thread đang truy cập class đó.

## 6. Phân biệt với JEP 491 của JDK 24

Một nguồn nhầm lẫn phổ biến là coi tất cả pinning liên quan monitor đã được xử lý trong cùng một thay đổi.

| Nội dung | JDK 24 — JEP 491 | JDK 26 — JDK-8369238 |
|---|---|---|
| Vấn đề | Virtual thread bị pin khi blocking trong synchronized method/block | Virtual thread bị pin khi chờ class initializer của thread khác |
| Cơ chế | Thay đổi cách JVM quản lý monitor để virtual thread có thể unmount | Cho phép preempt/unmount ở các đường class initialization phổ biến |
| Phạm vi | Java monitor và synchronized | Initialization lock và các đường link/initialize class |
| Mục tiêu | Giảm pinning do synchronized | Trả carrier khi virtual thread chờ class initialization |
| Có thay đổi Java API? | Không | Không |

Không nên áp dụng hướng dẫn cũ yêu cầu thay mọi `synchronized` bằng `ReentrantLock` chỉ vì sợ monitor pinning. JEP 491 đã xử lý phần pinning do synchronized trên JDK 24 trở lên.

JDK 26 xử lý một đường pinning khác. Native method và foreign function vẫn là các trường hợp cần quan sát riêng.

## 7. Thiết kế static initializer để tránh chờ kéo dài

Cải tiến JDK 26 giúp scheduler sử dụng carrier hiệu quả hơn, nhưng không làm cho static initializer trở thành nơi phù hợp để thực hiện tác vụ chậm.

### 7.1. Giữ initializer nhỏ và xác định

Nên dùng static initializer cho:

- Tạo immutable constant.
- Khởi tạo cấu trúc dữ liệu nội bộ nhỏ.
- Tạo lookup table có chi phí thấp và xác định.
- Khởi tạo dữ liệu không phụ thuộc network/database hoặc trạng thái bên ngoài.

Tránh thực hiện trực tiếp trong `<clinit>()`:

- HTTP request hoặc gọi service từ xa.
- Truy vấn database.
- Đọc file lớn hoặc scan toàn bộ classpath.
- Chờ thread khác hoàn thành tác vụ có thể phụ thuộc scheduler.
- Chờ lock nghiệp vụ hoặc khởi tạo nhiều plugin có side effect.

### 7.2. Chuyển bootstrap chậm thành bước tường minh

Ví dụ, thay vì load plugin trong static initializer:

~~~java
final class PluginRegistry {
    static final Map<String, Plugin> PLUGINS = PluginLoader.loadAll();
}
~~~

có thể chuyển thành bước bootstrap do application lifecycle quản lý:

~~~java
final class PluginRegistry {
    private static volatile Map<String, Plugin> plugins;

    static void initialize(Path pluginDirectory) throws IOException {
        Map<String, Plugin> loaded =
                PluginLoader.loadAll(pluginDirectory);

        plugins = Map.copyOf(loaded);
    }

    static Plugin find(String name) {
        Map<String, Plugin> current = plugins;
        if (current == null) {
            throw new IllegalStateException(
                    "PluginRegistry chưa được initialize"
            );
        }
        return current.get(name);
    }
}
~~~

Ứng dụng gọi `PluginRegistry.initialize(...)` trong giai đoạn startup trước khi nhận traffic. `volatile` đảm bảo công bố map đã khởi tạo cho các thread đọc sau đó.

Trong ứng dụng dùng dependency injection, có thể đặt công việc này trong lifecycle hook phù hợp của framework. Cần giữ quy tắc chỉ initialize một lần hoặc dùng cơ chế đồng bộ phù hợp nếu bootstrap có thể được gọi đồng thời.

### 7.3. Class initializer lỗi có hậu quả lâu dài

Nếu `<clinit>()` ném exception, class có thể chuyển sang trạng thái erroneous. Lần active use đầu có thể nhận `ExceptionInInitializerError`; các lần truy cập sau có thể nhận `NoClassDefFoundError`.

Vì vậy, tránh đưa các tác vụ dễ thất bại do network, credential hoặc hệ thống bên ngoài vào static initializer. JDK 26 chỉ cải thiện khả năng scheduler xử lý waiter; nó không thay đổi semantics lỗi của class initialization.

## 8. Chẩn đoán pinning và carrier starvation

### 8.1. JFR event jdk.VirtualThreadPinned

JDK Flight Recorder có event `jdk.VirtualThreadPinned` để ghi nhận virtual thread bị pin lâu hơn ngưỡng cấu hình. Theo hướng dẫn JDK 26, event được bật mặc định với threshold 20 ms và ghi lại blocking operation, lý do pin, carrier và stack trace.

Bắt đầu JFR recording:

~~~bash
java -XX:StartFlightRecording:filename=virtual-threads.jfr,dumponexit=true -jar app.jar
~~~

Đọc các event:

~~~bash
jfr print --events jdk.VirtualThreadPinned virtual-threads.jfr
~~~

Khi phân tích:

- Xem `pinnedReason` và `blockingOperation`.
- Xem stack trace có `Object.wait`, native method, FFM hoặc class initialization path không.
- Xem carrier thread có lặp lại cùng stack hay không.
- Đối chiếu timestamp với latency spike và throughput drop.

Event chỉ ghi pinning vượt threshold. Không thấy event không chứng minh không có pinning ngắn hơn 20 ms; có thể cấu hình JFR threshold thấp hơn trong môi trường kiểm thử.

Trên JDK 26, các class-init wait thuộc đường phổ biến được xử lý bằng unmount nên thường không còn tạo event pinning cho đúng đường đó. Nếu vẫn thấy event với `Waited for initialization`, cần xác định đường gọi và bản JDK cụ thể.

### 8.2. Thread dump có tất cả virtual thread

HotSpot thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Lệnh này hiển thị platform threads và virtual threads đang mounted cùng stack trace. Nó hữu ích để nhìn carrier đang chạy virtual thread nào.

Để xem cả virtual thread đang unmounted hoặc chờ scheduler:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json virtual-threads.json
~~~

Hoặc dạng text:

~~~bash
jcmd <pid> Thread.dump_to_file -format=text virtual-threads.txt
~~~

Thread dump dạng file liệt kê tất cả virtual thread, trạng thái và thông tin lock. Đây không phải snapshot nhất quán dừng toàn bộ VM và không tự thực hiện deadlock detection.

### 8.3. Quan sát scheduler

Có thể xem thông tin scheduler bằng:

~~~bash
jcmd <pid> Thread.vthread_scheduler
~~~

Lệnh này giúp quan sát parallelism, carrier workers và số virtual thread đang xếp hàng. Có thể dùng thêm:

~~~bash
jcmd <pid> Thread.vthread_pollers
~~~

`Thread.vthread_pollers` cung cấp thông tin về virtual thread chờ socket/network I/O. Kết hợp dữ liệu này với JFR và thread dump để phân biệt chờ I/O bình thường với carrier starvation.

## 9. Kiểm thử và benchmark trước/sau JDK 26

### 9.1. Workload cần có đồng thời class initialization

Benchmark chỉ tạo hàng nghìn virtual thread chạy `Thread.sleep` hoặc HTTP request không đủ để đánh giá thay đổi này.

Cần có workload mô phỏng:

- Nhiều virtual thread cùng lần đầu truy cập một class.
- Class initializer có thời gian chạy đáng kể hoặc chờ một thao tác có thể unmount.
- Một số virtual thread khác cần được scheduler chạy để hoàn tất tác vụ mà initializer đang chờ.
- Class được truy cập qua các đường `new`, `invokestatic`, `getstatic` hoặc `putstatic`.

Một static initializer dùng để mô phỏng có thể có dạng:

~~~java
final class SlowBootstrap {
    static {
        BootstrapGate.awaitRelease();
    }

    static void touch() {
        // Chỉ cần active use để kích hoạt class initialization.
    }
}
~~~

`BootstrapGate.awaitRelease()` là thao tác chờ được kiểm soát bởi test harness. Không dùng network hoặc database production trong benchmark.

### 9.2. So sánh JDK 25 và JDK 26/27

Giữ các yếu tố sau giống nhau:

- Cùng phần cứng, OS, CPU quota và memory limit.
- Cùng workload, classpath và số virtual thread.
- Cùng giá trị `jdk.virtualThreadScheduler.parallelism` nếu có đặt tường minh.
- Cùng warmup, số lần lặp và thời gian đo.
- Cùng JFR configuration và ngưỡng event.

Theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Throughput | Số tác vụ hoàn thành mỗi giây |
| p95/p99 latency | Độ trễ khi nhiều thread cùng truy cập class |
| Carrier utilization | Mức độ carrier bị chiếm giữ |
| Scheduler queue | Số virtual thread chờ được chạy |
| `jdk.VirtualThreadPinned` | Thời gian và nguyên nhân pinning |
| Class initialization duration | Thời gian class initializer thực thi |
| CPU utilization | CPU dành cho ứng dụng và scheduler |
| Completion time | Thời gian toàn bộ burst hoàn thành |

Không kết luận dựa trên một lần chạy. Cần chạy nhiều lần, có warmup và kiểm soát scheduling noise.

### 9.3. Đọc kết quả đúng cách

Kỳ vọng chính của JDK 26 là giảm carrier bị giữ bởi virtual thread đang chờ class initializer. Không nên kỳ vọng:

- Thời gian chạy `<clinit>()` tự giảm.
- Các thread chờ class initialization không còn phải đợi.
- Một class có thể được khởi tạo đồng thời bởi nhiều thread.
- Tác vụ CPU-bound tự động chạy nhanh hơn.
- Mọi loại pinning đều được loại bỏ.

Nếu class initializer mất 2 giây để tải cấu hình, JDK 26 không làm tác vụ đó thành 200 ms. Cải tiến nằm ở việc các virtual thread đang chờ không giữ carrier trong những đường được hỗ trợ.

## 10. Hướng dẫn vận hành khi nâng cấp JDK

### 10.1. Chọn runtime có hỗ trợ

- JDK 26 giới thiệu thay đổi JDK-8369238.
- JDK 27 tiếp tục hỗ trợ virtual thread và scheduler.
- Không cần preview flag hoặc module incubator.
- Dùng JDK update còn được nhà cung cấp hỗ trợ và kiểm tra release notes của runtime cụ thể.

### 10.2. Không tăng carrier pool để che giấu mọi pinning

Có thể cấu hình scheduler parallelism bằng system property:

~~~bash
java -Djdk.virtualThreadScheduler.parallelism=8 -jar app.jar
~~~

Nhưng tăng parallelism không sửa nguyên nhân pinning. Nếu hàng trăm virtual thread bị pin, thêm carrier chỉ trì hoãn lúc pool cạn và có thể tăng áp lực CPU/native thread.

Hãy xác định nguyên nhân qua JFR trước khi thay đổi scheduler. Đặc biệt, không dựa vào việc tăng pool size để bù cho static initializer chậm hoặc native call giữ carrier.

### 10.3. Virtual thread không thay thế giới hạn tài nguyên bên ngoài

Virtual thread giúp biểu diễn nhiều concurrent task với chi phí thấp hơn, nhưng không làm database, remote service, file descriptor hoặc CPU có năng lực vô hạn.

Dùng connection pool, semaphore, rate limiter hoặc bulkhead để giới hạn tài nguyên downstream. Cải tiến unmount giúp scheduler sử dụng carrier hiệu quả hơn; nó không thay đổi giới hạn concurrency của hệ thống bên ngoài.

## 11. Những hiểu lầm cần tránh

| Hiểu lầm | Thực tế |
|---|---|
| JDK 26 loại bỏ mọi pinning | Chỉ xử lý các đường class initialization phổ biến; native/foreign function vẫn có thể pin |
| Class initializer chạy song song sau JDK 26 | Vẫn chỉ một thread khởi tạo class; các thread khác vẫn chờ |
| JDK 26 làm static initializer nhanh hơn | Chủ yếu trả carrier cho scheduler trong lúc waiter chờ |
| Thay đổi này là preview API | Đây là runtime implementation fix, không cần `--enable-preview` |
| JEP 491 và JDK-8369238 là cùng một thay đổi | JEP 491 xử lý synchronized monitor pinning ở JDK 24; JDK-8369238 xử lý class-init wait ở JDK 26 |
| Không có JFR pin event nghĩa là không có pinning | Event mặc định chỉ ghi pinning vượt 20 ms |
| Thread.print hiển thị tất cả virtual thread | `Thread.dump_to_file` mới liệt kê cả virtual thread đang unmounted |

## 12. Kết luận

JDK 26 cải thiện khả năng mở rộng của virtual thread khi nhiều thread đồng thời chờ một class đang được khởi tạo. Trước thay đổi JDK-8369238, virtual thread waiter thường bị pin vào carrier do đường chờ initialization lock có VM/native frame. Trong các đường class initialization phổ biến, JDK 26 cho phép preempt continuation và unmount waiter, trả carrier về scheduler.

Các điểm cần nhớ:

- Class initialization vẫn được đồng bộ theo JLS; chỉ một thread thực thi `<clinit>()` cho một class tại một thời điểm.
- Virtual thread chờ class initializer có thể unmount trên các đường phổ biến trong JDK 26.
- Implementation ban đầu tập trung vào `new`, `invokestatic`, `getstatic` và `putstatic`; không giả định mọi đường native/reflection đều được bao phủ.
- JEP 491 của JDK 24 xử lý synchronized monitor pinning; đây là vấn đề khác với class initialization.
- JFR `jdk.VirtualThreadPinned`, `jcmd Thread.dump_to_file` và `Thread.vthread_scheduler` giúp chẩn đoán.
- Static initializer nên ngắn, xác định và tránh network/database hoặc chờ tác vụ khác.
- Cần benchmark workload class initialization đồng thời trên JDK 25 và JDK 26/27 để xác nhận tác động thực tế.

Cải tiến này giúp scheduler sử dụng carrier hiệu quả hơn trong lúc class initialization đang diễn ra. Ứng dụng vẫn cần thiết kế bootstrap rõ ràng, tránh static initializer kéo dài và theo dõi các nguyên nhân pinning còn lại.

## Tài liệu tham khảo chính thức

- [JDK 26 Release Notes — Virtual Threads Now Unmount from Carrier When Waiting for Another Thread to Execute a Class Initializer (JDK-8369238)](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK-8369238 — Allow virtual thread preemption on some common class initialization paths (OpenJDK review)](https://www.mail-archive.com/core-libs-dev%40openjdk.org/msg61386.html)
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
- [Virtual Threads — Java SE 26 Core Libraries Developer Guide](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html)
- [Virtual Threads — Java SE 27 Core Libraries Developer Guide](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html)
- [JLS `12.4.2 — Detailed Initialization Procedure, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html)
- [JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491)
- [JDK 24 Migration Guide — Synchronize Virtual Threads without Pinning](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)

