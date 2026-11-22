# Tách constructor nhẹ khỏi thao tác mở tài nguyên và kích hoạt

Trong hệ thống Java có khả năng mở rộng tại runtime, một plugin có thể được **khám phá**, **tạo instance**, **chuẩn bị tài nguyên**, **kích hoạt để nhận công việc**, rồi **ngừng hoạt động và giải phóng tài nguyên**. Nếu nhồi tất cả bước này vào constructor, chỉ một thao tác như gọi new, ServiceLoader.Provider.get() hoặc tạo đối tượng bằng dependency injection đã có thể mở socket, khởi chạy thread, đăng ký callback, sửa file hay bắt đầu nhận request. Lúc đó host khó kiểm soát thứ tự khởi động, khó xử lý lỗi giữa chừng và khó bảo đảm plugin chưa sẵn sàng sẽ không nhận công việc.

Nguyên tắc thiết kế: **constructor chỉ thiết lập danh tính và cấu hình tối thiểu; phương thức prepare()/initialize() mới kiểm tra và mở tài nguyên; phương thức activate()/start() mới chuyển plugin sang trạng thái phục vụ**. Host sở hữu trình tự này và luôn có cơ chế close()/stop() để hoàn tác khi một bước thất bại.

Bài này tập trung vào **vòng đời plugin** trong Java 17+: tại sao cần tách ba trách nhiệm, xây dựng state machine hợp lệ, xử lý rollback khi khởi tạo lỗi, điều phối nhiều plugin, kiểm tra bằng code chạy được và tránh những rò rỉ tài nguyên phổ biến.

## 1. Phân biệt ba hành động có ý nghĩa khác nhau

Hãy tưởng tượng plugin phân tích dữ liệu cần một đường dẫn log, cấu hình kết nối và một callback đăng ký với host:

| Giai đoạn | Việc nên làm | Việc không nên làm |
| --- | --- | --- |
| **Construction** – constructor | Nhận cấu hình bất biến, kiểm tra null và dạng dữ liệu rẻ, gán field, tạo đối tượng trạng thái ban đầu | Mở socket/file, tạo thread, kết nối DB, đăng ký listener hoặc tự công bố readiness |
| **Preparation** – prepare/init | Kiểm tra tài nguyên thực tế, mở file/socket/connection theo quyền đã cấp, nạp metadata, kiểm tra dependency, tạo thành phần vận hành nhưng chưa nhận traffic | Công khai plugin cho request khi chưa chuẩn bị xong; làm rơi tài nguyên khi prepare lỗi |
| **Activation** – activate/start | Bật scheduler/consumer, đăng ký endpoint hoặc callback phục vụ, công bố readiness khi mọi điều kiện đạt, chuyển sang ACTIVE | Tiếp tục phục vụ nếu một bước kích hoạt đã thất bại |
| **Deactivation/close** | Ngừng nhận việc, drain/cancel công việc còn chạy, hủy đăng ký, đóng tài nguyên theo thứ tự và xóa tham chiếu | Đóng file/scheduler trong lúc handler vẫn được phép sử dụng; coi close là tương đương JVM class unloading |

**Constructor nhẹ** không có nghĩa không làm gì. Nó có thể validate tên plugin, chuẩn hóa giá trị đơn giản, sao chép cấu hình bất biến và thiết lập state NEW. Điều cần tránh là những **side effect khó đảo ngược hoặc có thể chặn lâu**. Việc gọi new không nên làm dịch vụ ngoài chịu tải hoặc thay đổi trạng thái toàn cục.

**Prepare** là giai đoạn tài nguyên đã được cấp phát nhưng plugin **chưa sẵn sàng phục vụ**. Ví dụ một TCP connection đã mở hoặc file đã có writer; host vẫn chưa phát request đến plugin.

**Activate** mới là điểm cam kết vận hành. Một hệ thống cần readiness rõ ràng không nên cho traffic vào chỉ vì constructor đã trả về một instance.

## 2. Ví dụ thiết kế sai: constructor tự mở và tự kích hoạt

Mẫu dưới đây là **đoạn minh họa anti-pattern**, không phải class hoàn chỉnh:

~~~java
final class RiskyPlugin {
    private final java.net.Socket connection;

    RiskyPlugin(String host, int port) throws java.io.IOException {
        connection = new java.net.Socket(host, port); // I/O trong constructor
        HostCallbacks.register(this);                 // công bố instance quá sớm
    }
}
~~~

Trong đoạn minh họa này, HostCallbacks chỉ là một giả định về API host, không được định nghĩa nên đoạn này **không biên dịch độc lập**. Nó cho thấy hai rủi ro khác nhau:

1. **I/O trong constructor:** tạo một instance chỉ để khám phá metadata đã có thể timeout, ném IOException hoặc giữ socket. Nếu bước tiếp theo thất bại, caller có thể không có instance hoàn chỉnh để gọi close().
2. **Để this thoát khỏi constructor:** registry có thể gọi callback khi object còn đang xây dựng; field hoặc cấu trúc nội bộ có thể chưa thiết lập xong. Đây là lỗi về publication và thứ tự khởi tạo, không chỉ là vấn đề hiệu năng.

Tình huống thực tế thường khó hơn: constructor gọi một thư viện bên thứ ba, thư viện ấy tạo executor/thread hoặc đăng ký JDBC driver bên dưới. Nếu việc cấp phát không có điểm tập trung và không ghi lại ownership, host khó biết tài nguyên nào cần đóng sau lỗi.

Thay vào đó, constructor chỉ nên nhận những tham số cần thiết:

~~~java
final class PluginConfig {
    final String id;
    final java.nio.file.Path outputFile;

    PluginConfig(String id, java.nio.file.Path outputFile) {
        this.id = java.util.Objects.requireNonNull(id);
        this.outputFile = java.util.Objects.requireNonNull(outputFile);
    }
}
~~~

Đây là class độc lập đơn giản có thể đặt trong file PluginConfig.java; nó chưa mở file và cũng chưa kích hoạt dịch vụ. Có thể dùng record trong Java 17 khi dữ liệu cấu hình thích hợp; lưu ý đối tượng Path là một tham chiếu đường dẫn, **không phải bằng chứng file đã tồn tại hoặc truy cập được**. Kiểm tra I/O thật nên nằm trong prepare.

## 3. Mô hình trạng thái cho vòng đời plugin

Một mô hình điển hình:

~~~text
                  tạo instance
                       |
                       v
                     NEW
                       |
                  prepare OK
                       v
                   PREPARED
                       |
                  activate OK
                       v
                    ACTIVE
                       |
               ngừng nhận request
                       v
                   STOPPING
                       |
                 close resources
                       v
                    CLOSED
~~~

Ở bất kỳ giai đoạn nào phát sinh lỗi, host cần hủy những phần đã cấp phát và đi đến trạng thái dừng/đóng. Có thể biểu diễn lỗi và cleanup:

~~~text
NEW ── prepare lỗi ──────────────┐
PREPARED ── activate lỗi ────────┼──> cleanup/close ──> CLOSED
ACTIVE ── handler/stop lỗi ──────┘
~~~

Đây là **sơ đồ khái niệm**, không ép mọi implementation phải có đúng các tên trạng thái. Ví dụ chạy được ở mục 6 dùng bốn trạng thái **NEW, PREPARED, ACTIVE, CLOSED** để tránh làm rối bài; STOPPING/FAILED là những trạng thái bổ sung thường cần cho runtime có thread và tác vụ dài.

### Bất biến (invariants) cần bảo vệ

- **NEW:** chỉ có cấu hình, chưa sở hữu tài nguyên vận hành của plugin.
- **PREPARED:** những tài nguyên cần thiết đã mở thành công, nhưng plugin chưa được công bố là sẵn sàng.
- **ACTIVE:** điều kiện phục vụ đã đạt và host có thể điều phối lời gọi tới plugin.
- **CLOSED:** plugin không nhận việc mới; những tài nguyên mà nó sở hữu đã được yêu cầu giải phóng.
- **Transition hợp lệ:** start/activate không được gọi trước prepare; handle không chạy khi NEW/PREPARED/CLOSED; tránh gọi prepare nhiều lần trừ khi API thiết kế hỗ trợ.
- **Rollback:** nếu prepare/activate thất bại, phải thu hồi cả những tài nguyên đã cấp phát trước điểm lỗi.
- **Idempotent close:** gọi close lần hai nên an toàn và không khởi động lại tài nguyên; nếu một close trước đó đã lỗi, cần cơ chế theo dõi cleanup chưa hoàn tất.

Các bất biến trên bảo vệ **hành vi điều phối**, không phải bảo mật trước plugin không đáng tin. Một plugin ác ý vẫn có thể tự tạo thread hoặc mở socket trong constructor dù quy ước nói không được.

## 4. Giao diện vòng đời: host kiểm soát, plugin thực thi

Một contract có thể tách rõ:

~~~java
public interface ManagedPlugin extends AutoCloseable {
    String id();                    // metadata nhẹ
    void prepare() throws Exception;  // mở và kiểm tra tài nguyên
    void activate() throws Exception; // kích hoạt phục vụ
    String handle(String input) throws Exception;
    @Override
    void close() throws Exception;    // cleanup
}
~~~

Đây là **ví dụ giao diện**, có thể lưu trong ManagedPlugin.java. Hệ thống thật nên định nghĩa kiểu exception cụ thể thay cho throws Exception nếu cần phân biệt lỗi cấu hình, lỗi I/O, lỗi phụ thuộc hay lỗi kích hoạt. **Java AutoCloseable** phù hợp với try-with-resources hoặc finally, nhưng bản thân nó không xác định các trạng thái NEW/PREPARED/ACTIVE; host và plugin phải đồng thuận contract.

Trách nhiệm hai phía:

**Host/plugin manager:**
- Chỉ chọn hoặc tạo plugin dựa trên metadata, version và compatibility.
- Quyết định lúc nào prepare/activate, timeout và giới hạn tài nguyên.
- Không công bố instance vào registry đang phục vụ trước khi activate thành công.
- Bắt lỗi và đóng các tài nguyên đã cấp phát, ghi lại trạng thái.
- Khi dừng: ngừng chuyển request, chờ tác vụ cũ kết thúc, close plugin và giải phóng loader.

**Plugin implementation:**
- Giữ constructor rẻ, không tự đăng ký bên ngoài.
- Prepare có tính toàn vẹn: nếu lỗi, không để resource mở mà không được quản lý.
- Activate không báo thành công trước khi thật sự có khả năng phục vụ.
- Handle chỉ chạy trong trạng thái ACTIVE.
- Close được gọi được từ cả trường hợp prepare/activate chưa hoàn tất và trường hợp đang hoạt động.

Điểm quan trọng là **host quản lý readiness**, không chỉ hỏi plugin đã tồn tại hay chưa. Một Java object đã được new thành công không phải bằng chứng plugin hoặc dependency của nó đã sẵn sàng.

## 5. Vì sao việc tách pha đặc biệt quan trọng với ServiceLoader và class loader riêng

Trong mô hình mở rộng kiểu SPI, host có thể gọi:

~~~java
ServiceLoader<ManagedPlugin> loader =
        ServiceLoader.load(ManagedPlugin.class, pluginClassLoader);
for (ManagedPlugin plugin : loader) {
    // Duyệt provider có thể làm provider được tạo instance.
}
~~~

Đây là đoạn minh họa **đặt trong method đã có pluginClassLoader hợp lệ và interface ManagedPlugin nằm ở loader chung**; cần import java.util.ServiceLoader, không phải một chương trình chạy độc lập. Với cơ chế provider thông thường, việc gọi iterator.next() hoặc ServiceLoader.Provider.get() có thể **khởi tạo provider**. Nếu constructor tự kết nối DB hoặc khởi động thread, một thao tác discovery đơn giản đã biến thành activation không kiểm soát.

Với constructor nhẹ:

1. Host khám phá danh sách provider và kiểm tra metadata/capability.
2. Host quyết định plugin nào được phép chạy, tài nguyên nào được cấp.
3. Host khởi tạo provider mà chưa mở tài nguyên đắt tiền.
4. Host gọi prepare() theo thứ tự phụ thuộc cần thiết.
5. Host gọi activate() khi điều kiện sẵn sàng đã đạt.
6. Host mới đưa plugin vào registry để client sử dụng.

Trong hệ thống dùng **mỗi plugin một ClassLoader**, constructor có thể chạy khi một JAR vừa được nạp. Nếu nó tạo thread giữ context class loader, tải thêm class nội bộ hay giữ static reference ở host, việc unload/reload về sau sẽ khó. Constructor nhẹ giúp **giảm** cửa sổ xảy ra tác dụng phụ, nhưng **không bảo đảm class initialization không chạy**: static initializer hoặc logic của provider factory vẫn có thể có side effect. Cần kiểm tra cả static block và đường đi factory, không chỉ thân constructor.

Cũng cần phân biệt **load class** với **initialize class** và **instantiate object**: chúng là những sự kiện liên quan nhưng không đồng nhất. Tính lazy của ServiceLoader không biến constructor đã viết nặng thành an toàn; nó chỉ trì hoãn thời điểm tác dụng phụ xảy ra.

## 6. Ví dụ Java 17+ chạy được: constructor không mở file, prepare mở, activate quyết định readiness

Ví dụ dưới đây minh họa **hai instance plugin** có cấu hình file log độc lập. Plugin thứ nhất chuẩn bị và kích hoạt thành công. Plugin thứ hai được chuẩn bị nhưng cố ý thất bại ở activate(). Cả hai đều được đóng bởi finally. File output được mở bằng BufferedWriter để kiểm chứng rằng thao tác cấp tài nguyên nằm ở **prepare**, không nằm trong constructor.

Không dùng thư viện ngoài JDK và không cần kết nối mạng. Code thực thi trên JDK 17+; file log tạm được xóa khi main hoàn tất.

### 6.1. Mã nguồn đầy đủ

Tạo một file **PluginLifecycleDemo.java** với nội dung:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public final class PluginLifecycleDemo {
    enum State { NEW, PREPARED, ACTIVE, CLOSED }

    static final class FilePlugin implements AutoCloseable {
        private final String id;
        private final Path file;
        private final boolean failActivation;
        private BufferedWriter writer;
        private State state = State.NEW;

        FilePlugin(String id, Path file, boolean failActivation) {
            this.id = Objects.requireNonNull(id);
            this.file = Objects.requireNonNull(file);
            this.failActivation = failActivation;
        }

        synchronized State state() {
            return state;
        }

        synchronized void prepare() throws IOException {
            require(State.NEW);
            BufferedWriter candidate = Files.newBufferedWriter(
                    file, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            try {
                candidate.write("prepared " + id + "\n");
                candidate.flush();
                writer = candidate;
                state = State.PREPARED;
            } catch (IOException | RuntimeException failure) {
                try {
                    candidate.close();
                } catch (IOException cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
                throw failure;
            }
        }

        synchronized void activate() throws IOException {
            require(State.PREPARED);
            if (failActivation) {
                throw new IllegalStateException("activation rejected");
            }
            writer.write("activated " + id + "\n");
            writer.flush();
            state = State.ACTIVE;
        }

        synchronized String handle(String value) throws IOException {
            require(State.ACTIVE);
            String result = id + ":" + value.toUpperCase(Locale.ROOT);
            writer.write("processed " + result + "\n");
            writer.flush();
            return result;
        }

        private void require(State expected) {
            if (state != expected) {
                throw new IllegalStateException(
                        "expected " + expected + " but was " + state);
            }
        }

        @Override
        public synchronized void close() throws IOException {
            if (state == State.CLOSED) {
                return;
            }
            state = State.CLOSED;
            if (writer != null) {
                try {
                    writer.close();
                } finally {
                    writer = null;
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("plugin-lifecycle-");
        Path goodFile = dir.resolve("good.log");
        Path badFile = dir.resolve("bad.log");

        try {
            FilePlugin good = new FilePlugin("good", goodFile, false);
            FilePlugin bad = new FilePlugin("bad", badFile, true);

            System.out.println("constructorFiles=" +
                    Files.exists(goodFile) + "," + Files.exists(badFile));

            try {
                good.prepare();
                System.out.println("preparedExists=" +
                        Files.exists(goodFile));
                good.activate();
                System.out.println("result=" + good.handle("hello"));
            } finally {
                good.close();
            }
            System.out.println("goodState=" + good.state());

            try {
                bad.prepare();
                bad.activate();
            } catch (IllegalStateException failure) {
                System.out.println("badError=" + failure.getMessage());
            } finally {
                bad.close();
            }
            System.out.println("badState=" + bad.state());
            System.out.println("goodLog=" + String.join("|",
                    Files.readAllLines(goodFile, StandardCharsets.UTF_8)));
            System.out.println("badLog=" + String.join("|",
                    Files.readAllLines(badFile, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(goodFile);
            Files.deleteIfExists(badFile);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

FilePlugin mô hình hóa vòng đời một resource-backed plugin. Constructor chỉ lưu id, Path và cờ mô phỏng lỗi; **không gọi Files.newBufferedWriter**, không mở socket, không tạo file và không tự công bố instance. Java class này nằm trong cùng file để bài dễ copy và chạy; trong dự án thực, interface, plugin implementation và host có thể ở những artifact/module khác nhau.

### 6.2. Biên dịch và chạy

Đứng tại thư mục chứa PluginLifecycleDemo.java, dùng **JDK 17 trở lên**:

~~~powershell
javac --release 17 -encoding UTF-8 PluginLifecycleDemo.java
java PluginLifecycleDemo
~~~

Hai lệnh cũng áp dụng cho terminal Linux/macOS có cài javac và java. Chương trình tạo thư mục tạm theo hệ điều hành, không phụ thuộc vào đường dẫn Windows cố định. Những file tạo trong thư mục tạm được dọn bằng finally của main; trong bài học, file log được đọc trước khi xóa.

**Stdout chính xác khi chạy:**

~~~text
constructorFiles=false,false
preparedExists=true
result=good:HELLO
goodState=CLOSED
badError=activation rejected
badState=CLOSED
goodLog=prepared good|activated good|processed good:HELLO
badLog=prepared bad
~~~

Đây là kết quả đã được kiểm chứng bằng lệnh javac --release 17 và thực thi Java thực tế.

### 6.3. Đọc ý nghĩa từng dòng stdout

- **constructorFiles=false,false:** sau khi tạo cả hai plugin, chưa có file good.log và bad.log. Điều này kiểm chứng **constructor không tạo hai file tài nguyên**; thư mục tạm đã được host tạo trước đó.
- **preparedExists=true:** good.prepare() mở file log bằng Files.newBufferedWriter và ghi dòng prepared good. Đây là giai đoạn mở tài nguyên.
- **result=good:HELLO:** chỉ sau activate() thành công, lời gọi handle("hello") mới được phép thực hiện.
- **goodState=CLOSED:** finally bảo đảm gọi close sau pha phục vụ; trạng thái chuyển về CLOSED.
- **badError=activation rejected:** bad.prepare() đã thành công nhưng activate() cố ý ném IllegalStateException. Lỗi được host bắt và vẫn gọi close trong finally.
- **badState=CLOSED:** lỗi khởi động **không để lại một plugin ở trạng thái phục vụ**; close đã yêu cầu giải phóng tài nguyên.
- **goodLog=prepared good|activated good|processed good:HELLO:** tài nguyên được dùng lần lượt trong pha chuẩn bị, kích hoạt và xử lý; ký hiệu | là dấu nối các dòng khi in để dễ quan sát.
- **badLog=prepared bad:** plugin lỗi chỉ kịp ghi dữ liệu lúc prepare, không ghi "activated" hay "processed". File được giữ đủ lâu để xem kết quả, rồi host xóa khi kết thúc.

### 6.4. Tại sao prepare giữ resource trong biến candidate?

Code sử dụng biến cục bộ candidate trước khi gán vào field writer:

~~~java
BufferedWriter candidate = Files.newBufferedWriter(
        file, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
try {
    candidate.write("prepared " + id + "\n");
    candidate.flush();
    writer = candidate;
    state = State.PREPARED;
} catch (IOException | RuntimeException failure) {
    try {
        candidate.close();
    } catch (IOException cleanupFailure) {
        failure.addSuppressed(cleanupFailure);
    }
    throw failure;
}
~~~

**Đây là đoạn trích có thể tìm trong phương thức prepare của ví dụ**, không phải một file độc lập. Ý nghĩa: tài nguyên mới mở được xem như tài nguyên **tạm thời** cho đến khi bước chuẩn bị thành công. Nếu ghi hoặc flush bị lỗi, code đóng candidate trước khi ném lỗi ra ngoài. Nếu close cũng lỗi, lỗi cleanup được gắn làm suppressed exception thay vì vô tình che khuất nguyên nhân ban đầu.

Điều đó **không bảo đảm file được xóa** sau lỗi. CREATE_NEW đã có thể tạo file ngay trước khi việc ghi thất bại. Việc dọn artifact còn sót trên filesystem là trách nhiệm khác, có thể thuộc host/workspace manager. Hãy phân biệt **giải phóng handle** với **rollback mọi side effect bền vững**.

### 6.5. Vì sao activate không được tự giả định prepare đã chạy?

Phương thức require(State.PREPARED) bảo đảm chỉ được kích hoạt từ trạng thái hợp lệ. Nếu host gọi activate ngay sau new, chương trình báo IllegalStateException thay vì phát sinh lỗi ngẫu nhiên như NullPointerException khi writer vẫn null.

Tương tự, handle() gọi require(State.ACTIVE) để ngăn nhận việc khi plugin chưa được kích hoạt hoặc đã đóng. Kiểm tra trạng thái ở biên API giúp phát hiện lỗi điều phối sớm.

Từ góc độ khả năng kiểm thử, việc có **ba điểm riêng** constructor → prepare → activate giúp viết test xác định phạm vi lỗi. Không phải tạo đối tượng đồng nghĩa đã kích hoạt một dịch vụ ngoài.

## 7. Quy tắc rollback khi một pha khởi động thất bại

Giả sử một plugin cần ba tài nguyên: file log, kết nối DB và consumer đăng ký với message broker. Prepare có thể mở file rồi tạo connection, activate mới subscribe consumer. Nếu bước thứ hai hoặc thứ ba lỗi, những resource đã có **vẫn phải được thu hồi**.

Một trình tự an toàn có dạng:

~~~text
new plugin
   |
   v
prepare()
   |-- open file
   |-- create connection
   |-- validate readiness
   |      |
   |      +-- nếu lỗi: đóng những gì đã mở; báo thất bại
   v
activate()
   |-- register consumer / publish capability
   |      |
   |      +-- nếu lỗi: hủy đăng ký một phần, đóng connection/file
   v
ACTIVE / publish to host registry
~~~

Lỗi ở prepare/activate có thể là checked exception, runtime exception, timeout hoặc ngắt thread. Không nên chỉ dọn tài nguyên khi đúng một loại IOException xảy ra.

### 7.1. Host dùng finally/try-with-resources đúng thời điểm

Một sơ đồ điều phối tối giản:

~~~java
ManagedPlugin plugin = createPlugin();
boolean published = false;
try {
    plugin.prepare();
    plugin.activate();
    registry.publish(plugin.id(), plugin);
    published = true;
    // Plugin đã ACTIVE và thuộc quyền quản lý của registry.
} catch (Exception startupFailure) {
    if (published) {
        registry.unpublish(plugin.id());
    }
    try {
        plugin.close();
    } catch (Exception cleanupFailure) {
        startupFailure.addSuppressed(cleanupFailure);
    }
    throw startupFailure;
}
~~~

Đây là **mã minh họa thuật toán**, không phải đoạn Java biên dịch độc lập: createPlugin, registry và chính sách publish/unpublish cần được định nghĩa; phải đặt trong method khai báo throws Exception thích hợp. Host thật cần bảo đảm registry.publish là **atomic**, hoặc rollback publication nếu publication có thể thực hiện một phần trước khi ném exception. Không được hiểu biến boolean published là giải pháp giao dịch tổng quát cho mọi registry.

Điểm thiết kế chính là: **host chỉ công bố plugin sau khi prepare và activate thành công**; nếu bất kỳ bước khởi động nào thất bại, host phải close instance và xử lý mọi tài nguyên/callback đã đăng ký một phần.

Khi dùng try-with-resources để quản lý một plugin chỉ sống trong phạm vi method, Java sẽ tự close khi rời block. Nhưng với plugin cần sống lâu để nhận request, không thể bao nó trong try-with-resources rồi **return plugin hoặc đăng ký vào runtime registry** mà không chuyển rõ quyền sở hữu vòng đời; block kết thúc thì plugin đã bị close. Khi chuyển ownership sang manager, manager mới là nơi gọi close lúc shutdown.

### 7.2. Nếu bản thân cleanup ném lỗi

Một lỗi thường gặp:

~~~java
catch (Exception original) {
    plugin.close();  // có thể ném exception khác và che lỗi gốc
    throw original;
}
~~~

Đây là **anti-pattern minh họa**. Nếu close ném IOException, lỗi khởi động ban đầu có thể bị mất khỏi đường điều khiển quan sát được. Hãy giữ lỗi khởi động làm lỗi chính, gắn lỗi đóng tài nguyên làm suppressed, hoặc dùng cấu trúc try-with-resources phù hợp.

Nếu một tài nguyên A phụ thuộc tài nguyên B, thường cần đóng **ngược thứ tự mở** (sau khi đã ngừng nhận việc). Đảm bảo close cố gắng giải phóng các tài nguyên độc lập kể cả khi một lần close đầu tiên thất bại, đồng thời tổng hợp lỗi để chẩn đoán.

**Lưu ý giới hạn của ví dụ runnable:** FilePlugin chỉ sở hữu một BufferedWriter, nên close có thể đơn giản. Trong hệ thống có nhiều resource, close nên dùng nhiều khối try/catch/finally theo thứ tự; cần cẩn thận với InterruptedException, timeout và trạng thái không xác định của mạng.

## 8. Tránh kích hoạt ngầm trong DI container, framework và factory

Không chỉ ServiceLoader mới tạo plugin. Instance có thể xuất hiện do:

- Dependency injection container tạo object.
- Factory method hoặc Builder.create() trả về implementation.
- Reflection gọi constructor bằng Constructor.newInstance().
- SPI provider factory hoặc ServiceLoader.Provider.get().
- Test fixture tạo instance để kiểm tra metadata/config.
- Công cụ phân tích classpath hoặc cơ chế reload nạp lại plugin.

Nếu constructor mở resource, **mọi đường tạo instance** đều cần chuẩn bị đầy đủ môi trường và cleanup. Một framework gọi constructor để introspect thông tin, hoặc test chỉ muốn tạo mock object, đã có thể mở DB ngoài ý muốn.

Một số framework hỗ trợ hook khởi tạo như phương thức được đánh dấu @PostConstruct hoặc callback startup. Những hook này **cũng có thể được framework gọi sớm**, nên cần hiểu đúng thời điểm chúng được thực thi. Nếu host yêu cầu tách prepare khỏi activate, không nên chuyển toàn bộ tác dụng phụ của constructor sang @PostConstruct rồi gọi đó là giải pháp hoàn chỉnh.

Cách mạnh hơn là cung cấp **lifecycle contract tường minh** và để host/plugin manager điều phối. DI framework có thể tạo instance trước, nhưng plugin chỉ phục vụ sau khi manager xác nhận ACTIVE.

### Quy ước về cấu hình

Constructor có thể nhận một cấu hình bất biến như:

~~~java
record PluginSettings(String id, Path outputPath) {
    PluginSettings {
        Objects.requireNonNull(id);
        Objects.requireNonNull(outputPath);
        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
    }
}
~~~

Đây là đoạn minh họa Java 17 độc lập **cần import java.nio.file.Path và java.util.Objects**, có thể đặt trong PluginSettings.java khi record được khai báo public hoặc dùng record package-private với tên file phù hợp. Cách này kiểm tra giá trị thuần trong constructor; nó không gọi Files.exists(), không truy vấn DB và không kết nối mạng. Các kiểm tra yêu cầu môi trường I/O phải dời sang prepare vì môi trường có thể đổi giữa lúc tạo instance và lúc khởi động.

## 9. Sẵn sàng phục vụ là trách nhiệm của activation, không phải construction

Trong một plugin hệ thống thật, activation có thể gồm:

1. Bắt đầu nhận message từ queue.
2. Đăng ký callback vào event bus.
3. Công bố endpoint/capability trong registry.
4. Bật scheduler hoặc background worker.
5. Cho health/readiness chuyển sang trạng thái ready.

Điểm công bố trạng thái **ACTIVE** phải xảy ra sau những bước cần thiết. Nếu callback có thể chạy ngay khi vừa đăng ký, hãy chuẩn bị toàn bộ nội bộ cần thiết **trước khi công bố callback**. Không nên thực hiện:

~~~text
publish plugin to registry
    |
    v
initialize connection
    |
    v
subscribe background worker
~~~

Theo trình tự sai này, request có thể đến trong lúc connection chưa có. Nếu bước initialize connection bị lỗi, client đã nhìn thấy một plugin không khả dụng.

Trình tự hợp lý hơn:

~~~text
construct (no externally visible side effect)
    |
    v
prepare (resources acquired but not serving)
    |
    v
activate internal capability
    |
    v
publish readiness / open routing
~~~

**Chú ý ranh giới giữa activate và publish:** Trong một số hệ thống, đăng ký listener chính là thao tác kích hoạt, bởi event có thể đến ngay lúc register. Khi ấy cần một cơ chế chặn xử lý cho đến khi ACTIVE, hoặc thiết kế đăng ký theo dạng atomic staging/enable. Không thể chỉ đảo thứ tự các lời gọi mà bảo đảm an toàn nếu framework tự phát callback đồng thời.

Nếu activation có side effect bên ngoài không thể hoàn tác hoàn toàn (ví dụ gửi lệnh thanh toán, phát một event có hiệu lực), hãy tách **chuẩn bị tài nguyên** khỏi **cam kết tác vụ nghiệp vụ** và áp dụng idempotency key, transactional outbox hoặc giao thức phục hồi phù hợp. Lifecycle method không tự tạo giao dịch phân tán.

## 10. Đồng thời: không được close khi request còn chạy

Bài toán runtime plugin thường có nhiều thread: host đang shutdown trong khi worker đang thực hiện handle(), hoặc plugin mới đang activate khi hệ thống nhận request. Khi đó enum State và một vài phép kiểm tra chưa chắc đủ.

Ví dụ runnable ở mục 6 dùng **synchronized** cho prepare, activate, handle, state và close. Điều này tuần tự hóa các lời gọi trong **cùng instance**, phù hợp để dạy bất biến cơ bản. Nó không giải quyết mọi vấn đề production:

- Nếu handle() làm I/O lâu, close() chờ khóa và có thể không kịp shutdown deadline.
- Nếu callback do thread riêng của plugin tạo mà không gọi synchronized method, chúng có thể tiếp tục chạy sau close.
- Nếu một plugin khác vẫn giữ tham chiếu tới instance cũ, registry ngừng cấp request mới vẫn chưa đủ.
- Nếu resource được dùng bởi đối tượng khác không đi qua khóa của FilePlugin, close có thể xảy ra khi resource vẫn đang sử dụng.

Một lộ trình dừng đầy đủ:

~~~text
ACTIVE
  |
  | mark NOT_READY / remove from routing
  v
STOPPING
  |
  | wait for in-flight requests to drain
  | cancel/interrupt cooperative tasks if deadline expires
  | unsubscribe listeners / stop scheduler
  v
CLOSING
  |
  | close connections, streams, executors, caches
  v
CLOSED
~~~

Nên phân biệt **quiesce** (ngừng nhận việc mới), **drain** (chờ việc cũ), và **close** (giải phóng tài nguyên). Nếu plugin dùng ExecutorService, phải thiết kế chính sách shutdown()/awaitTermination()/shutdownNow() theo loại task, không chỉ close socket ngay khi service bắt đầu dừng.

Trạng thái lifecycle phải có cơ chế quan sát đồng bộ phù hợp: synchronized, volatile, lock, AtomicReference hay state machine thread-safe. Mọi transition cần tránh tình huống check-then-act không nguyên tử. Ví dụ:

~~~java
if (plugin.isActive()) {
    plugin.handle(request);
}
~~~

Đây là **đoạn minh họa rủi ro** nếu isActive và handle không được điều phối cùng một cơ chế đồng bộ: plugin có thể chuyển CLOSED ở giữa. Trong hệ thật, registry nên cấp lease/in-flight permit hoặc sử dụng một API handle có kiểm tra trạng thái và kiểm soát vòng đời trong cùng đường gọi.

## 11. Reload và ownership của ClassLoader

Java ClassLoader là đơn vị quản lý namespace lớp; đối với plugin chạy trong JVM, một loader riêng thường giữ các class implementation và dependency của chính plugin đó. Constructor nhẹ không đủ để làm hot reload an toàn. Khi thay một phiên bản plugin, cần:

1. Ngừng điều phối request tới plugin cũ.
2. Drain hoặc hủy tác vụ đang chạy theo deadline.
3. Gọi stop/close để ngắt callback, executor, thread, socket, file, timer.
4. Hủy đăng ký khỏi registry và bỏ những tham chiếu còn giữ instance/class của plugin cũ.
5. Nếu loader có Closeable contract như URLClassLoader, đóng loader và tài nguyên JAR của nó.
6. Mới sau đó coi loader cũ là **đủ điều kiện** được GC/unload, nếu không còn tham chiếu; không bảo đảm unload tức thì.

Các nguồn rò rỉ thường gặp:

- Thread sống lâu giữ **Thread Context ClassLoader** của plugin.
- ThreadLocal hoặc callback còn được lưu trong thread pool của host.
- Global registry giữ instance, Method, Class hoặc ClassLoader của plugin.
- JDBC driver, logging adapter, shutdown hook, metrics listener không unregister.
- Lambda hoặc scheduled task bị giữ trong executor của host.
- Static singleton của thư viện dùng chung có tham chiếu ngược vào class plugin.

Nếu plugin tự khởi động thread trong constructor, một lỗi khởi tạo rất sớm đã có thể giữ ClassLoader sống dai. Tách construction và activation giúp host kiểm soát khi nào thread được tạo, khi nào được đăng ký và khi nào phải dừng.

**Bảo mật:** một class loader riêng tách dependency/namespace, không phải sandbox. Plugin chưa được tin cậy có thể bỏ qua mọi quy ước lifecycle. Muốn chạy code không đáng tin, phải xét cô lập tiến trình, quyền file/network, CPU/bộ nhớ và cơ chế IPC phù hợp.

## 12. Test đúng hành vi lifecycle, không chỉ test constructor

Các test hữu ích cho plugin manager:

| Test | Kỳ vọng |
| --- | --- |
| Chỉ gọi constructor | Không mở file/socket hoặc đăng ký callback; state NEW |
| Prepare thành công | Resource cần thiết đã mở, state PREPARED, chưa nhận request |
| Gọi handle trước activate | Từ chối với lỗi trạng thái rõ ràng |
| Activate thành công | State ACTIVE; host có thể công bố readiness |
| Prepare lỗi giữa chừng | Resource đã mở trước lỗi được đóng; không publish |
| Activate lỗi sau prepare | Host cleanup resource, không đưa plugin vào routing |
| Close sau prepare nhưng trước activate | Đóng được, không cần giả lập đã ACTIVE |
| Close sau activate | Ngừng phục vụ trước khi close resource |
| Close hai lần | Không mở lại tài nguyên và không gây side effect thừa |
| Nhiều request đồng thời với stop | Không có request mới sau quiesce; in-flight được xử lý theo policy |
| Reload nhiều lần | Không tăng số thread/file handle/classloader bị giữ ngoài dự kiến |

Ví dụ mã ở mục 6 minh họa trực tiếp bốn test: constructor không tạo file log, prepare tạo file, activate thành công mới xử lý được, và lỗi activate vẫn close. Trong production, nên dùng test giả lập connection/file failure có thể lặp lại thay vì gây lỗi ngoài hệ thống thật.

### Test prepare thất bại ngay khi mở file

Trong ví dụ FilePlugin, prepare dùng StandardOpenOption.CREATE_NEW. Nếu file mục tiêu đã tồn tại, Files.newBufferedWriter có thể ném FileAlreadyExistsException. Khi đó writer vẫn null và state vẫn NEW; nếu host bắt lỗi, nó phải gọi close để chuyển instance sang CLOSED, rồi quyết định chính sách xử lý file tồn tại.

Bài toán này hữu ích vì chứng minh **không được xử lý lỗi prepare bằng cách tiếp tục activate**. Nếu file tồn tại là trường hợp bình thường, hãy thay đổi chính sách mở file một cách chủ động (CREATE/APPEND/TRUNCATE_EXISTING), không tự động đổi từ CREATE_NEW thành ghi đè trong lúc xử lý exception.

### Test lỗi sau khi mở tài nguyên

Nếu việc ghi hoặc flush dữ liệu prepared bị lỗi sau khi writer đã được mở, nhánh catch trong prepare cố close candidate và gắn cleanup failure làm suppressed khi cần. Đây là phạm vi bảo đảm **đóng handle trong code minh họa**. File có thể còn trên đĩa và cần bước cleanup ngoài plugin. Với nhiều resource, phải xây dựng rollback cho từng resource đã được cấp.

## 13. Những lỗi thiết kế thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Discovery SPI tự mở kết nối DB | Constructor/factory làm I/O | Để constructor nhận config, dời I/O sang prepare |
| Plugin xuất hiện trong registry trước khi sẵn sàng | Publish trong constructor hoặc trước activate | Chỉ publish sau activation/health check |
| Startup lỗi làm lộ file descriptor/thread | Không rollback resource mở giữa chừng | Ghi ownership và close trong catch/finally |
| Constructor bị chặn lâu khi DB/network trục trặc | Đồng bộ chờ I/O trong new | Dời vào prepare với timeout/cancellation |
| Activate sau prepare lỗi gây NullPointerException | Thiếu state transition guard | Yêu cầu PREPARED trước activate |
| Request vẫn tới sau close | Registry chưa quiesce, callback chưa unsubscribe | Ngừng routing, drain, sau đó close |
| Close làm che nguyên nhân khởi động | Cleanup ném lỗi mới | Giữ lỗi gốc, gắn suppressed hoặc tổng hợp lỗi |
| Reload rò ClassLoader | Thread/TCCL/cache/registry còn tham chiếu | Cleanup lifecycle và bỏ reference đúng thứ tự |
| Stop gây treo | Handler chặn, giữ lock hoặc không hỗ trợ cancellation | Deadline, drain, interrupt/cooperative stop và giám sát |
| Khởi động lại object CLOSED nhưng tài nguyên không hợp lệ | Restart không có contract rõ | Dùng instance và loader mới; chỉ cho restart nếu state machine được thiết kế riêng |

Một mẫu sai đáng chú ý là **"constructor bắt lỗi nhưng nuốt lỗi"**: trong constructor, code mở tài nguyên, bắt IOException và chỉ log, rồi để instance được tạo thành công dù tài nguyên không có. Host có thể tưởng plugin đã sẵn sàng. Nếu constructor chỉ nhận cấu hình, vấn đề này phần lớn không xuất hiện; prepare trả lỗi rõ ràng và host có thể chuyển plugin sang FAILED.

## 14. Checklist quyết định cho một plugin mới

Trước khi chấp nhận plugin vào hệ thống, hãy trả lời các câu hỏi:

1. **Constructor có side effect không?** Có mở file, socket, tạo thread, đăng ký event, gọi API ngoài, tạo transaction hay thay global state không?
2. **Ai sở hữu tài nguyên?** File/socket/executor được tạo ở đâu, được close bởi method nào, đóng theo thứ tự nào?
3. **Prepare có bảo đảm nguyên tử ở mức ownership không?** Nếu thất bại ở bước thứ ba thì hai resource đã mở có được giải phóng không?
4. **Điểm sẵn sàng phục vụ nằm ở đâu?** Plugin có bị registry lộ ra trước khi activate xong không?
5. **Có lời gọi handle khi chưa ACTIVE không?** API phải fail fast rõ ràng, không dựa vào NullPointerException.
6. **Nếu activate thất bại thì sao?** Đã có quy trình cleanup và không còn routing chưa?
7. **Nếu close thất bại thì sao?** Có giữ lỗi gốc, ghi log đầy đủ và báo resource leak cần can thiệp không?
8. **Có chạy đồng thời không?** State, in-flight requests, callback, scheduler và close được điều phối ra sao?
9. **Có hot reload không?** ClassLoader, TCCL, listener, static reference và thread có được dọn đúng cách không?
10. **Tính năng nào cần test thực tế?** Constructor nhẹ, prepare, activate, failure rollback, stop, double-close và reload.

## 15. Tài liệu chuẩn

- Java SE 17, **AutoCloseable** và close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- Java SE 17, **Files.newBufferedWriter**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)
- Java SE 17, **ServiceLoader** và thời điểm khởi tạo provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17, **URLClassLoader.close**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()
- Java SE 17, **ExecutorService** và shutdown: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Kết luận:** constructor nhẹ giúp **tạo đối tượng mà không đồng thời khởi chạy plugin**. Prepare chịu trách nhiệm **mở và xác minh tài nguyên**. Activate xác định **thời điểm được phép nhận công việc**. Stop/close quản lý **thu hồi tài nguyên kể cả khi startup thất bại**. Tách ba giai đoạn giúp plugin host có startup có thể kiểm thử, trạng thái quan sát được, rollback đáng tin và vòng đời rõ ràng khi reload hoặc shutdown.
