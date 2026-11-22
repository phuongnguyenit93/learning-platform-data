# Điều kiện lớp có thể được thu hồi và giới hạn bảo đảm của GC

## 1. Vì sao thay plugin không đồng nghĩa với giải phóng class?

Trong ứng dụng Java hỗ trợ plugin, mỗi lần nạp một phiên bản plugin có thể tạo thêm class loader, class và metadata tương ứng trong JVM. Khi cập nhật plugin, host thường chuyển request mới sang phiên bản mới và đóng phiên bản cũ. Nhưng việc gọi \`close()\`, xóa JAR hay bỏ một phần tử khỏi registry **không đồng nghĩa với các class cũ được JVM thu hồi ngay lập tức**.

Cần phân biệt ba việc:

1. **Ngừng sử dụng logic**: không cấp request mới cho plugin cũ; hoàn thành hoặc hủy tác vụ đang chạy.
2. **Giải phóng tài nguyên ứng dụng**: đóng socket, executor, file, listener, timer, connection pool và những thứ plugin đang sở hữu.
3. **Class unloading**: JVM có thể loại bỏ metadata của những class không còn cần thiết sau khi chúng và class loader liên quan đủ điều kiện thu hồi.

Bước thứ ba phụ thuộc vào trạng thái reachable của toàn bộ object graph và quyết định của garbage collector, không chỉ vào code gọi \`close()\`.

Trong hệ thống plugin chạy lâu ngày, nếu loader cũ vẫn bị giữ lại qua thread, callback, cache hoặc registry, việc hot reload lặp lại có thể làm bộ nhớ class metadata tăng dần và cuối cùng dẫn đến áp lực Metaspace.

## 2. Class identity và class loader trong thay thế plugin

Trong JVM, một kiểu được xác định bởi cặp **(tên nhị phân, defining class loader)**. Vì thế hai phiên bản plugin cùng khai báo \`com.example.plugin.ReportPlugin\`, nhưng được định nghĩa bởi hai loader khác nhau, vẫn là hai lớp riêng biệt.

\`\`\`text
Host/API Loader
      |
      +-- PluginLoader V1 --> ReportPlugin V1
      |
      +-- PluginLoader V2 --> ReportPlugin V2
\`\`\`

Khi V2 được công bố, V1 không tự biến mất. Nếu một object V1 vẫn được một phần của host giữ lại, defining loader V1 có thể vẫn reachable và các lớp được loader đó định nghĩa vẫn chưa đủ điều kiện unloading.

Ngược lại, một plugin dùng **application class loader chung** không có khả năng unload riêng các class của plugin theo kiểu “gỡ JAR rồi class biến mất”. Những class được loader dùng chung định nghĩa thường tồn tại theo vòng đời của loader đó. Đây là một lý do phải thiết kế ranh giới class loader **trước khi** triển khai hot reload.

Class loader riêng giúp tổ chức và có thể tạo cơ hội unload theo vòng đời loader, nhưng **không phải sandbox bảo mật** cho code không đáng tin.

## 3. Điều kiện để class có thể được unload

Mô tả thực dụng: với các class được định nghĩa bởi class loader có thể thu hồi, JVM chỉ có thể unload chúng khi không còn trạng thái sống nào đòi hỏi giữ class và loader ấy.

Các nguồn giữ sống có thể bao gồm:

- Instance của class plugin còn reachable từ root của JVM.
- Object \`Class<?>\`, \`Method\`, \`Field\`, \`Constructor\`, method handle hoặc proxy liên quan đến class/plugin còn được giữ.
- Static field và các mối liên hệ giữa class, instance, loader trong object graph.
- Thread đang thực thi mã plugin; stack frame và các biến còn sử dụng object/plugin class.
- Thread còn sống với **thread context class loader (TCCL)** trỏ vào loader plugin.
- \`ThreadLocal\` trên worker thread giữ instance plugin, callback hoặc class loader.
- Listener, subscriber, scheduled task, executor, timer, cache, DI container hay singleton của host giữ object từ plugin.
- Một class loader khác giữ tham chiếu đến plugin loader, class, instance hoặc resource của nó.
- JNI/native code hay cơ chế framework giữ global reference và trạng thái liên quan.

Điều kiện thu hồi thực tế phức tạp hơn một quy tắc đếm reference đơn giản. JVM có thể lưu metadata, tối ưu hóa JIT và tổ chức class-loader data theo implementation; thời điểm unload chịu ảnh hưởng garbage collector và các safepoint/chu kỳ GC. Không có lệnh chuẩn nào bảo đảm “unload chính xác class X ngay bây giờ”.

Một bất biến hữu ích ở cấp kiến trúc:

> Sau khi plugin cũ ngừng phục vụ và hoàn tất cleanup, **host không còn strong reference** nào tới loader, class hoặc instance riêng của phiên bản plugin đó.

Bất biến này không bảo đảm thời điểm JVM thực hiện unloading, nhưng là điều kiện thiết kế cốt lõi để nó có cơ hội xảy ra.

## 4. Reachability: vì sao một reference nhỏ có thể giữ cả loader?

Xét ví dụ:

\`\`\`text
GC Root
   |
   v
Host singleton
   |
   v
List<Runnable> callbacks
   |
   v
Plugin callback instance
   |
   v
Plugin implementation class
   |
   v
Plugin defining ClassLoader
\`\`\`

Ngay cả khi \`activePlugins.remove("old")\`, đường tham chiếu từ singleton qua callback vẫn tồn tại. Loader V1 vẫn sống.

Một ví dụ khác:

\`\`\`text
Worker Thread (được host tái sử dụng)
   |
   +--> Thread.contextClassLoader --> PluginLoader V1
   |
   +--> ThreadLocalMap --> PluginRequestContext V1
\`\`\`

Nếu host từng đặt TCCL hoặc ThreadLocal cho V1 và không khôi phục trong \`finally\`, loader có thể bị giữ sống suốt thời gian worker thread tồn tại.

**Không chỉ tìm reference trực tiếp tới \`ClassLoader\`.** Một object thường của plugin được host giữ trong event bus cũng có thể đủ để ngăn unloading.

## 5. Quy trình thay thế plugin đúng thứ tự

Một hot-reload lifecycle có thể được tổ chức:

\`\`\`text
Plugin V1 đang ACTIVE
         |
         v
Chuẩn bị / kiểm tra / khởi động V2
         |
         v
Công bố snapshot registry V2
         |
         v
Ngừng cấp lease mới cho V1
         |
         v
Chờ request / callback V1 đang chạy kết thúc
         |
         v
Hủy subscription, task, timer; đóng resource V1
         |
         v
Gỡ reference tới V1 khỏi host registry và cache
         |
         v
Đóng class loader có hỗ trợ close
         |
         v
V1 đủ điều kiện GC? (chỉ nếu không còn đường giữ sống)
         |
         v
JVM có thể thu hồi loader và class metadata về sau
\`\`\`

Nếu dùng \`URLClassLoader\`, \`close()\` giải phóng tài nguyên mở JAR/URL theo contract của nó và ngăn tải resource/class mới theo các điều kiện tương ứng; **nó không cưỡng bức unload class đã định nghĩa**.

Cần làm rõ ai sở hữu resource: một instance plugin được nhiều snapshot chia sẻ không thể tùy tiện bị đóng khi chỉ một snapshot ngừng dùng. Có thể sử dụng lease/ref-count hoặc một protocol drain được đồng bộ đúng để ngăn “close trong lúc reader còn gọi”.

Khi unload không chắc chắn, ứng dụng vẫn phải duy trì tính đúng đắn: registry mới không được định tuyến request sang plugin cũ; còn nếu plugin cũ chưa thu hồi được thì đó là vấn đề tài nguyên cần quan sát và xử lý riêng.

## 6. Ví dụ Java 17+: quan sát class loader được GC thu hồi

Để kiểm tra nguyên tắc **không còn strong reference**, có thể dùng \`WeakReference\` theo dõi một class loader. Chương trình bên dưới cố ý **không dựa vào một GC event chắc chắn**, vì GC được phép không chạy hoặc không thu hồi ngay.

Tạo file **\`LoaderGcDemo.java\`**:

\`\`\`java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;

public class LoaderGcDemo {
    private static WeakReference<ClassLoader> makeLoader() throws Exception {
        // Không cần JAR: mục đích là quan sát lifetime của loader.
        URLClassLoader loader = new URLClassLoader(
                new URL[0],
                LoaderGcDemo.class.getClassLoader()
        );
        WeakReference<ClassLoader> weak = new WeakReference<>(loader);

        loader.close();  // Đóng resource của loader, không ép GC/unload.
        return weak;     // Sau khi thoát, không cố giữ strong ref.
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> weak = makeLoader();
        System.out.println("weak reference created: true");

        for (int i = 0; i < 5 && weak.get() != null; i++) {
            System.gc(); // Chỉ là lời gợi ý; JVM không có nghĩa vụ đáp ứng.
            Thread.sleep(100);
        }

        System.out.println("loader collected: " + (weak.get() == null));
    }
}
\`\`\`

Chạy:

\`\`\`bash
javac LoaderGcDemo.java
java LoaderGcDemo
\`\`\`

Dòng đầu luôn là:

\`\`\`text
weak reference created: true
\`\`\`

Dòng cuối có thể là **\`loader collected: true\` hoặc \`loader collected: false\`** tùy JVM, GC, timing và tùy chọn khởi chạy. Không nên viết unit test yêu cầu kết quả phải là \`true\` trong thời hạn cố định.

Ví dụ này chứng minh cách theo dõi *loader reachability* qua weak reference, **không trực tiếp chứng minh một class riêng đã được unload**, vì loader mẫu không định nghĩa class plugin. Để quan sát class unloading thực tế cần tạo loader nạp một class từ plugin JAR, gỡ toàn bộ strong reference và kết hợp JVM class-unload logging hoặc profiling.

## 7. WeakReference, ReferenceQueue và giới hạn kiểm chứng

\`WeakReference<ClassLoader>\` thường hữu ích trong test/diagnostics:

\`\`\`java
WeakReference<ClassLoader> oldLoader =
        new WeakReference<>(pluginLoader);
\`\`\`

Sau khi gỡ mọi strong reference, \`oldLoader.get()\` **có thể** trở thành \`null\` khi GC xử lý đối tượng. Nếu đối tượng vẫn còn reachable mạnh, weak reference sẽ không bị clear bởi một GC thông thường có xét reachability đó.

Có thể dùng \`ReferenceQueue\` để nhận tín hiệu khi weak reference được enqueue, nhưng vẫn không có thời hạn chuẩn cho thông báo. \`PhantomReference\` cũng có thể giúp theo dõi một giai đoạn lifecycle tham chiếu; không có nghĩa JVM cung cấp một callback “class unload hoàn tất” có thời gian xác định.

Các hạn chế cần ghi nhớ:

- Weak reference chỉ theo dõi object mà nó tham chiếu, không trực tiếp xác nhận toàn bộ class metadata liên quan đã giải phóng.
- \`System.gc()\` là gợi ý cho JVM, không phải mệnh lệnh bắt buộc. JVM có thể vô hiệu hóa explicit GC hoặc chọn không làm full collection.
- JIT và tối ưu hóa lifetime của biến local có thể khiến kết quả thí nghiệm khác nhau, kể cả cùng mã nguồn.
- GC log và heap/metaspace metrics chịu ảnh hưởng runtime, workload và cơ chế cấp phát lại.
- **Metaspace usage giảm hay không giảm ngay** không là bằng chứng duy nhất cho việc class unloading; JVM có thể giữ vùng bộ nhớ đã cấp để tái sử dụng.

Vì thế cần kết hợp nhiều công cụ thay vì một phép thử GC duy nhất.

## 8. Dùng JVM logs và công cụ chẩn đoán

Trên HotSpot/JDK hiện đại có thể dùng Unified Logging để quan sát load/unload:

\`\`\`bash
java -Xlog:class+load=info,class+unload=info -jar host.jar
\`\`\`

Log sẽ nhiều; trong production nên giới hạn mức và đích ghi phù hợp, tránh tạo áp lực I/O hoặc lộ thông tin đường dẫn. Các event unload chỉ xuất hiện khi JVM thực sự unload class; không có event trong một khoảng thời gian ngắn không tự chứng minh leak.

Những công cụ hữu ích:

- **JFR (Java Flight Recorder)**: theo dõi class loading, allocation, GC và biến động runtime tùy event đã bật.
- **\`jcmd <pid> VM.classloader_stats\`** trên các phiên bản HotSpot hỗ trợ: thống kê class loader và metadata, hữu ích để xem nhiều loader phiên bản cũ có tồn tại.
- **\`jcmd <pid> GC.class_histogram\`**, heap dump và memory analyzer: tìm object còn giữ plugin instance/class loader. Một số lệnh có thể gây stop-the-world hoặc overhead; chọn thời điểm phù hợp.
- **Metaspace metrics** (qua JMX/MemoryPoolMXBean, JFR hoặc monitoring): theo dõi xu hướng khi hot reload lặp lại.

Để điều tra leak, chụp heap dump và lần theo **path to GC roots** từ plugin loader hoặc instance. Hãy xác minh đó là strong reference thực sự; soft/weak/phantom references có semantics khác nhau.

## 9. Những nguồn leak phổ biến trong plugin host

### 9.1 Thread không dừng

Plugin tự tạo thread/executor và quên shutdown. Thread còn chạy có stack/context hoặc runnable của plugin, giữ class loader.

Giải pháp: thread/executor phải có owner rõ; \`shutdown()\`/\`shutdownNow()\` theo policy, chờ kết thúc với timeout, và cảnh báo nếu không dừng.

### 9.2 Thread context class loader không được khôi phục

\`\`\`java
Thread t = Thread.currentThread();
ClassLoader previous = t.getContextClassLoader();
try {
    t.setContextClassLoader(pluginLoader);
    invokePlugin();
} finally {
    t.setContextClassLoader(previous);
}
\`\`\`

Đây là đoạn tích hợp; khôi phục TCCL kể cả khi invocation lỗi. Không gán loader plugin lên thread pool vĩnh viễn.

### 9.3 ThreadLocal và MDC

Worker thread của host tồn tại lâu hơn plugin; một \`ThreadLocal\` chứa instance của plugin có thể giữ object graph cũ. Dọn hoặc phục hồi trong \`finally\` tại đúng luồng đã set. Gọi \`remove()\` từ thread khác không xóa giá trị của worker thread.

### 9.4 Listener/subscription và callback

Event bus, scheduler, metrics registry, JMX MBean, shutdown hook hoặc DI scope có thể giữ callback/plugin class. Dùng registration handle và \`unsubscribe()\`/\`close()\` trong \`stop()\`.

### 9.5 Cache tĩnh hoặc singleton của host

Cache chứa \`Class<?>\`, reflective \`Method\`, method handle, lambda, dynamic proxy hay serialized metadata trỏ đến class plugin. Clear cache theo \`pluginId\` và version; đừng dùng \`ClassLoader\` làm key trong một global map không có eviction.

### 9.6 Native/JNI và thư viện bên ngoài

JNI global reference, native thread, logging bridge hoặc framework cache có thể giữ class/plugin loader. Một số thư viện không hỗ trợ unload sạch trong cùng JVM. Khi yêu cầu thu hồi đáng tin hơn, cân nhắc tách plugin sang process riêng.

## 10. Những tình huống không bảo đảm unload được

Có những giới hạn thuộc về kiến trúc hoặc runtime:

- **Không có unload theo tên class:** Java không cung cấp API \`unloadClass("...")\`.
- **Class trong loader còn sống:** không thể kỳ vọng JVM thu hồi độc lập một class bất kỳ mà loader đang được sử dụng, chỉ vì host không gọi class đó nữa.
- **Class loader chung:** không thể gỡ một plugin riêng như gỡ module class loader nếu tất cả được nạp chung vào application loader.
- **GC không có thời hạn xác định:** ngay cả khi đối tượng đã unreachable, thời điểm GC/unload vẫn do JVM quyết định.
- **Close không ép unload:** \`URLClassLoader.close()\`, \`JShell.close()\`, \`ModuleLayer\` hoặc tháo registry đều không phải lệnh unload tức thì.
- **Class/static/stack/native references:** các liên kết runtime vẫn có thể giữ định nghĩa còn cần thiết.
- **JPMS layer không có lệnh unload:** cần để layer, loader và mọi tham chiếu của chúng trở nên unreachable; việc tạo layer mới không tự thu hồi layer cũ.

Một collector/JVM cụ thể có thể có chiến lược unload khác nhau; nên kiểm chứng trên đúng JDK, GC và cấu hình production thay vì hứa hẹn theo kết quả máy phát triển.

## 11. Bảo đảm được điều gì ở cấp ứng dụng?

Thay vì cam kết “class V1 sẽ unload trong 500 ms”, hãy định nghĩa **các bảo đảm mà host tự kiểm soát**:

1. Sau điểm publish V2, request mới không chọn V1.
2. Không gọi \`stop/close\` V1 khi còn lease/in-flight request của V1.
3. Khi V1 stop, mọi subscription/task/resource thuộc ownership của nó được cleanup hoặc được đánh dấu lỗi rõ ràng.
4. Registry và cache của host không còn tham chiếu mạnh tới V1.
5. Host không giữ TCCL/ThreadLocal/plugin object V1 vượt quá scope.
6. Có giới hạn số phiên bản/plugin loader cùng tồn tại và chính sách xử lý nếu cleanup thất bại.
7. Có metrics, log và cảnh báo khi loader/metaspace không trở về xu hướng ổn định qua nhiều chu kỳ reload.

Những điều này **tăng khả năng** loader/class đủ điều kiện thu hồi, nhưng không ấn định thời điểm GC hay lượng memory thực tế được trả về hệ điều hành.

Nếu yêu cầu nghiệp vụ cần bảo đảm tài nguyên được thu hồi sau một deadline rõ ràng, **cô lập plugin bằng tiến trình riêng** thường cung cấp ranh giới kết thúc tài nguyên mạnh hơn việc dựa vào class unloading trong một JVM chia sẻ. Việc kết thúc process vẫn phải tuân thủ chính sách graceful shutdown và giới hạn thời gian.

## 12. Kiểm thử hot reload và class unloading

Một test integration nên:

1. Nạp V1 qua loader riêng và ghi nhận weak reference tới loader đó.
2. Đưa V1 vào registry, chạy một số lời gọi thật.
3. Chuẩn bị V2, chuyển request mới sang V2 theo snapshot atomic.
4. Drain V1, hủy callback, đóng executor/resource và bỏ mọi strong reference do test/host nắm.
5. Gợi ý GC hoặc chờ theo giới hạn kiểm thử hợp lý nhưng **không dùng việc GC chắc chắn trong deadline ngắn làm assertion về tính đúng đắn**.
6. Kiểm tra không còn V1 trong active registry và không còn in-flight lease.
7. Dùng JFR/logs/heap dump để chẩn đoán nếu nhiều vòng reload tạo xu hướng giữ loader cũ.

Kiểm thử nghiêm túc cần thêm trường hợp thất bại: callback không được gỡ, thread treo, resource \`close()\` lỗi, request dài, rollback V2 → V1 và plugin chứa native library. Quan sát số loader theo phiên bản qua hàng trăm vòng reload hữu ích hơn chỉ chạy một lần rồi gọi \`System.gc()\`.

## 13. Lỗi phổ biến

- Nghĩ \`URLClassLoader.close()\` sẽ gỡ ngay class đã tải.
- Xóa JAR trên ổ đĩa rồi kết luận code plugin đã biến mất khỏi JVM.
- Chỉ remove plugin khỏi một map nhưng bỏ quên event listeners và executors.
- Dùng static cache lưu \`Class\` hoặc method handle của plugin vô thời hạn.
- Quên phục hồi TCCL/ThreadLocal sau callback.
- Đóng plugin cũ trước khi request cũ hoàn thành.
- Giữ \`ModuleLayer\`, \`ServiceLoader\` hoặc \`CompiledScript\` của phiên bản cũ trong cache mà không có eviction.
- Kỳ vọng \`System.gc()\` làm một unit test class unloading ổn định.
- Dùng Metaspace usage tức thời làm bằng chứng duy nhất về leak.
- Không phân biệt class loader leak với resource leak hoặc heap leak.
- Quá tin vào class loader isolation như sandbox cho code không đáng tin.

## 14. Checklist trước khi triển khai thay thế plugin

- Plugin mỗi phiên bản có loader/layer riêng nếu mục tiêu là hỗ trợ unload theo vòng đời?
- Shared API được định nghĩa ở parent loader ổn định, tránh class identity conflict?
- Plugin V2 đã khởi tạo/kiểm tra trước khi chuyển request?
- Snapshot registry bảo đảm request mới không chọn V1?
- Có cơ chế drain và quản lý lease trước khi đóng V1?
- Executor, thread, callback, timer, listener, cache, JNI reference và TCCL/ThreadLocal đã được cleanup?
- Mọi strong reference từ host tới V1 được gỡ khi kết thúc?
- \`close()\` được gọi với các resource thích hợp, nhưng không nhầm với GC?
- Có giới hạn phiên bản cùng tồn tại và cảnh báo Metaspace/loader growth?
- Test và vận hành có công cụ quan sát class unloading trên đúng JVM?

**Ghi nhớ:** để class/plugin cũ có thể được thu hồi, trước hết phải **chấm dứt mọi đường tham chiếu mạnh và thực thi còn giữ class loader cũ**, sau đó để JVM quyết định việc garbage collection và class unloading. **Đủ điều kiện thu hồi không đồng nghĩa với được thu hồi ngay hay được bảo đảm trong một thời hạn cụ thể.**
