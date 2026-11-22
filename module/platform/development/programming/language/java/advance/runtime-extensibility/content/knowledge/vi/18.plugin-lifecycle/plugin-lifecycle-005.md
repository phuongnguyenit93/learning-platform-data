# Công bố tập plugin đang hoạt động an toàn cho luồng đọc đồng thời

## 1. Bài toán: nhiều luồng đọc trong khi plugin được thay thế

Một hệ thống plugin thường có nhiều request thread liên tục chọn và gọi plugin, trong khi một luồng quản trị có thể thêm, cập nhật, vô hiệu hóa hoặc thay thế plugin. Tại một thời điểm, hệ thống cần công bố một **tập plugin đang hoạt động (active plugin set)** để các reader sử dụng.

Nếu registry chỉ là một \`ArrayList\` hoặc \`HashMap\` mutable được chia sẻ trực tiếp, writer có thể thay đổi cấu trúc trong khi reader đang duyệt. Hậu quả gồm dữ liệu không nhất quán, chọn nhầm provider, \`ConcurrentModificationException\` trong một số trường hợp, hoặc lỗi hiển thị bộ nhớ do thiếu quan hệ happens-before. \`ConcurrentModificationException\` **không phải cơ chế đồng bộ** và cũng không bảo đảm xuất hiện ở mọi cuộc đua dữ liệu.

Mục tiêu thiết kế:

- Reader nhìn thấy **một snapshot hoàn chỉnh, đã được kiểm tra và kích hoạt**, không thấy trạng thái xây dựng dở dang.
- Mỗi lần reader lấy registry là một thao tác đọc nhất quán, không cần khóa trên đường xử lý nóng.
- Writer có thể chuẩn bị snapshot mới ngoài đường đọc, rồi **công bố bằng một thao tác nguyên tử**.
- Plugin bị thay thế không bị đóng tài nguyên khi request cũ vẫn đang gọi nó.
- Các trạng thái lifecycle như \`NEW\`, \`STARTING\`, \`ACTIVE\`, \`DRAINING\`, \`STOPPED\` không bị đánh đồng với việc một object còn xuất hiện trong map.

Giải pháp nền tảng dễ bảo trì là **immutable snapshot + atomic/volatile reference + lifecycle drain**.

## 2. An toàn ở đây có những lớp nào?

Cần tách bốn loại an toàn:

| Khía cạnh | Cần bảo đảm | Ví dụ lỗi nếu thiếu |
|---|---|---|
| Memory visibility | Reader thấy các ghi trước publication | Thấy cấu hình hay field chưa được khởi tạo |
| Atomic publication | Reader nhận một phiên bản registry hoàn chỉnh | Thấy provider A mới nhưng B vẫn là bản cũ ngoài ý muốn |
| Snapshot immutability | Writer không sửa object registry reader đã nhận | Duyệt map bị thay đổi giữa chừng |
| Lifecycle safety | Plugin còn được dùng không bị đóng sớm | \`IllegalStateException\`, socket/loader đóng giữa request |

**\`volatile\` hoặc \`AtomicReference\` chỉ giải quyết publication của tham chiếu**, không biến object mutable phía sau thành immutable, và không tự bảo đảm các plugin bên trong thread-safe.

Điểm tuyến tính hóa (linearization point) của lần công bố thường là thao tác \`active.set(next)\` hoặc ghi vào field \`volatile\`. Reader lấy snapshot trước điểm đó dùng bản cũ; reader lấy sau đó có thể dùng bản mới. Với một lần đọc reference, không cần tạo khóa toàn cục để duyệt cấu trúc immutable.

## 3. Immutable snapshot và AtomicReference

Mô hình cơ bản:

\`\`\`java
record PluginRegistry(long revision, Map<String, Plugin> plugins) {
    PluginRegistry {
        plugins = Map.copyOf(plugins);
    }
}

AtomicReference<PluginRegistry> active =
        new AtomicReference<>(new PluginRegistry(0, Map.of()));
\`\`\`

Một writer tạo registry mới:

\`\`\`java
Map<String, Plugin> nextPlugins = new HashMap<>(current.plugins());
nextPlugins.put("csv", readyCsvPlugin);
PluginRegistry next = new PluginRegistry(current.revision() + 1, nextPlugins);
active.set(next);
\`\`\`

Một reader dùng:

\`\`\`java
PluginRegistry snapshot = active.get();
Plugin selected = snapshot.plugins().get("csv");
\`\`\`

Đây là **copy-on-write ở cấp registry**, không phải clone mọi plugin object. \`Map.copyOf\` tạo một map không cho sửa qua API; bản sao là **shallow**. Plugin object trong map có thể giữ mutable state. Vì thế cần bảo đảm plugin đã được khởi tạo đúng, có trạng thái phù hợp và xử lý các cuộc gọi đồng thời theo contract của nó.

Ưu điểm:

- Reader chỉ thực hiện \`get()\` rồi tra cứu map đã chốt.
- Không cần khóa trong vòng lặp đọc.
- Snapshot đã lấy không bị writer chỉnh sửa cấu trúc.
- Revision giúp quan sát thay đổi và so khớp log.

Nhược điểm:

- Mỗi lần thay đổi cần tạo registry/map mới; phù hợp khi số lần cập nhật ít hơn rất nhiều so với số lần đọc.
- Cùng một plugin instance có thể được dùng bởi nhiều snapshot.
- Không tự giải quyết lifetime của instance và resource.

## 4. Vì sao AtomicReference hoặc volatile đủ cho publication?

Theo Java Memory Model, việc ghi vào biến \`volatile\` và lần đọc phù hợp tạo quan hệ **happens-before**. \`AtomicReference.set\`/\`get\` có memory effects của volatile. Do đó nếu writer xây dựng object snapshot hoàn chỉnh **trước** \`set\`, reader nhận reference đó sẽ nhìn thấy các ghi được xuất bản hợp lệ trước đó.

Mô hình:

\`\`\`text
Writer thread                            Reader thread
-------------                            -------------
create Plugin A
initialize Plugin A
build immutable Map
build Registry revision 7
active.set(registry7)  -------->         registry = active.get()
                                        registry.plugins().get("A")
                                        invoke plugin A
\`\`\`

**Không** làm thế này:

\`\`\`java
Map<String, Plugin> mutable = new HashMap<>();
active.set(new PluginRegistryMutable(mutable));
mutable.put("A", plugin); // sửa sau publication: sai
\`\`\`

Đồng thời, chỉ sử dụng \`final\` field trong một object không tự bảo đảm các thao tác thay thế reference mà nhiều reader đang quan sát là an toàn nếu bạn gán vào một biến thường không đồng bộ.

## 5. Ví dụ Java 17+ hoàn chỉnh: snapshot đọc đồng thời

Ví dụ sử dụng một writer xuất bản bản registry mới và hai reader đọc snapshot. Nó không yêu cầu dependency ngoài. Nội dung log giữa các thread có thể xen kẽ, vì lịch scheduling không cố định, nhưng mỗi reader luôn dùng cùng một revision trong một lần đọc.

Tạo file **\`PluginSnapshotDemo.java\`**:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class PluginSnapshotDemo {
    interface Plugin {
        String run(String input);
    }

    record Registry(long revision, Map<String, Plugin> plugins) {
        Registry {
            plugins = Map.copyOf(plugins);
        }
    }

    static final class PluginManager {
        private final AtomicReference<Registry> active =
                new AtomicReference<>(new Registry(0, Map.of()));

        Registry snapshot() {
            return active.get();
        }

        void publish(Registry next) {
            active.set(next);
        }
    }

    public static void main(String[] args) throws Exception {
        PluginManager manager = new PluginManager();
        Plugin upper = s -> s.toUpperCase(java.util.Locale.ROOT);
        manager.publish(new Registry(1, Map.of("format", upper)));

        CountDownLatch readersCaptured = new CountDownLatch(2);
        CountDownLatch writerPublished = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Runnable reader = () -> {
                Registry local = manager.snapshot();
                readersCaptured.countDown();
                try {
                    writerPublished.await();
                    System.out.println(
                            "reader revision=" + local.revision()
                            + " result="
                            + local.plugins().get("format").run("hello"));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            };

            var first = executor.submit(reader);
            var second = executor.submit(reader);

            readersCaptured.await();
            Plugin lower = s -> s.toLowerCase(java.util.Locale.ROOT);
            Map<String, Plugin> changed =
                    new HashMap<>(manager.snapshot().plugins());
            changed.put("format", lower);
            manager.publish(new Registry(2, changed));
            writerPublished.countDown();

            first.get();
            second.get();

            Registry latest = manager.snapshot();
            System.out.println("latest revision=" + latest.revision()
                    + " result=" + latest.plugins().get("format")
                    .run("HELLO"));
        } finally {
            executor.shutdown();
        }
    }
}
\`\`\`

Chạy:

\`\`\`bash
javac PluginSnapshotDemo.java
java PluginSnapshotDemo
\`\`\`

Một kết quả hợp lệ (hai dòng reader có thể đổi thứ tự):

\`\`\`text
reader revision=1 result=HELLO
reader revision=1 result=HELLO
latest revision=2 result=hello
\`\`\`

Giải thích:

1. Writer công bố registry revision 1 chứa provider \`upper\`.
2. Hai reader giữ reference tới **cùng một snapshot revision 1** rồi chờ writer công bố revision 2.
3. Writer thay registry bằng revision 2 chứa \`lower\`.
4. Hai reader hoàn tất bằng provider cũ, vì snapshot của chúng không bị sửa.
5. Lần đọc mới sau publication nhận revision 2 và dùng \`lower\`.

Đây là demonstration về **publication và snapshot consistency**. Nó chưa đóng provider, chưa quản lý in-flight requests và chưa xử lý hai writer cạnh tranh; các phần đó phải được thiết kế bổ sung.

## 6. Cập nhật đồng thời: set, compareAndSet và updateAndGet

Nếu chỉ có **một writer được serialize** (ví dụ một control-plane thread), \`active.set(next)\` là đủ cho việc công bố.

Nếu có nhiều writer:

\`\`\`text
Writer A đọc revision 4
Writer B đọc revision 4
Writer A thêm plugin X -> revision 5
Writer B thêm plugin Y -> revision 5
Writer B set(...) ghi đè X
\`\`\`

Đây là **lost update**. Có thể giải quyết bằng:

- Dùng một writer lock hoặc serial executor cho toàn bộ thay đổi registry.
- Dùng vòng lặp \`compareAndSet(expected, next)\` để chỉ công bố nếu snapshot chưa đổi; nếu CAS thất bại, đọc lại và dựng snapshot mới.
- Dùng \`updateAndGet\` với một hàm tạo giá trị mới **không có side effect**, vì hàm này có thể được gọi lại khi CAS cạnh tranh.

Ví dụ CAS:

\`\`\`java
// Đoạn tích hợp; active là AtomicReference<Registry>, plugin đã sẵn sàng.
for (;;) {
    Registry old = active.get();
    Map<String, Plugin> changed = new HashMap<>(old.plugins());
    changed.put("new-provider", plugin);
    Registry next = new Registry(old.revision() + 1, changed);
    if (active.compareAndSet(old, next)) {
        break;
    }
}
\`\`\`

**Không gọi \`plugin.start()\` trong callback CAS hoặc hàm \`updateAndGet\`**. Vì retry có thể xảy ra, một lifecycle operation có side effect có thể chạy lặp. Hãy khởi tạo plugin trước khi vào vòng cập nhật và chỉ publish instance đã sẵn sàng; nếu bị thất bại do xung đột, áp dụng chính sách xử lý/tái dùng hoặc cleanup rõ ràng.

CAS chỉ giải quyết xung đột thay đổi snapshot; lifecycle cleanup khi một writer thất bại vẫn phải do manager điều phối.

## 7. Đừng đóng plugin ngay sau khi publish bản mới

Tình huống nguy hiểm:

\`\`\`text
Reader A lấy snapshot cũ chứa Plugin V1
        |
Writer công bố snapshot mới chứa Plugin V2
        |
Writer gọi V1.close() ngay
        |
Reader A vẫn đang chạy V1.run() --> lỗi tài nguyên đóng giữa chừng
\`\`\`

Publication không đồng nghĩa với việc **mọi reader đã ngừng dùng snapshot cũ**.

Một quy trình hot swap đúng cần:

1. Tạo, kiểm tra và khởi động V2 trước.
2. Công bố snapshot V2 nguyên tử để request mới nhận V2.
3. Đánh dấu V1 chuyển sang trạng thái \`DRAINING\`, không cấp phát thêm lời gọi mới từ registry hiện hành.
4. Chờ các lời gọi V1 đang chạy hoàn thành (có timeout/chính sách hủy).
5. Khi không còn lời gọi, đóng V1 và giải phóng resource/class loader.

Các cơ chế có thể dùng để bảo vệ lifetime:

- **Reference-counted lease:** reader tăng bộ đếm quyền sử dụng trước khi gọi và giảm trong \`finally\`; writer chờ bộ đếm về 0.
- **Reader-writer lock:** reader giữ read lock trong toàn bộ thời gian sử dụng; writer lấy write lock trước khi dừng/đóng phiên bản cũ.
- **Epoch/quiescent-state reclamation:** reader tham gia epoch; writer chỉ thu hồi sau khi mọi reader liên quan đã rời epoch. Cần hiện thực cẩn thận.
- **Grace-period drain:** ngừng tiếp nhận request mới và chờ các request in-flight được theo dõi bởi request manager.

**Cảnh báo về reference counting:** chỉ tăng bộ đếm **sau khi** lấy snapshot là chưa đủ nếu writer có thể đóng plugin ngay trước khi bộ đếm được tăng. Phải thiết kế một bước **acquire lease nguyên tử với kiểm tra trạng thái**; nếu không thành công thì reader lấy lại snapshot mới. Writer chuyển trạng thái từ \`ACTIVE\` sang \`DRAINING\` theo cùng protocol trước khi chờ số lease về 0.

## 8. Một mô hình lease an toàn hơn

Có thể dùng object holder cho mỗi plugin version:

\`\`\`text
PluginHolder {
    plugin
    state: ACTIVE | DRAINING | CLOSED
    activeLeases
}
\`\`\`

Protocol tối thiểu:

**Reader**
1. Lấy registry snapshot.
2. Xác định holder mong muốn.
3. Thử \`acquire()\`: chỉ thành công nếu holder còn ACTIVE; tăng lease count theo thao tác đồng bộ/atomic không có race với DRAINING.
4. Nếu không acquire được, đọc lại snapshot và thử hoặc trả lỗi.
5. Gọi plugin.
6. \`release()\` trong \`finally\`.

**Writer**
1. Chuẩn bị holder mới ở trạng thái sẵn sàng.
2. Công bố registry mới.
3. Chuyển holder cũ sang DRAINING, ngăn lease mới.
4. Chờ các lease còn lại về 0.
5. Đóng plugin và chuyển CLOSED.

Protocol phải bảo đảm nếu reader đang acquire cùng lúc writer drain, chỉ một kết quả được phép: reader sở hữu lease hợp lệ và writer đợi; hoặc acquire thất bại và reader retry. Cần kiểm thử race kỹ lưỡng.

Một phương án đơn giản, thường dễ chứng minh đúng hơn khi tải không quá lớn là dùng **read/write lock bảo vệ cả snapshot acquisition và giai đoạn sử dụng**. Điều đó làm tăng contention nhưng phù hợp ứng dụng có ít request. Atomic snapshot và lease protocol là lựa chọn tối ưu hơn khi read-heavy, nhưng phức tạp hơn.

## 9. ConcurrentHashMap có thay thế snapshot không?

\`ConcurrentHashMap\` cung cấp các thao tác thread-safe ở cấp cấu trúc và lookup. Nhưng:

- Một chuỗi thao tác đọc nhiều key có thể thấy các thời điểm cập nhật khác nhau.
- Iterator của \`ConcurrentHashMap\` thường có **weakly consistent** semantics, không phải snapshot nhất quán tuyệt đối theo phiên bản.
- \`put\` hoặc \`remove\` từng key không tạo ra một transaction cập nhật toàn bộ registry.
- Lifecycle của plugin vẫn không được quản lý tự động.

Do vậy, nếu yêu cầu là **công bố toàn bộ tập plugin như một phiên bản logic**, immutable registry được swap nguyên tử có ngữ nghĩa rõ hơn. Nếu chỉ cập nhật từng key độc lập và không cần snapshot đồng nhất, \`ConcurrentHashMap\` có thể đủ.

Tương tự, \`Collections.synchronizedMap\` yêu cầu đồng bộ cả khi duyệt và cả chuỗi thao tác; không tự biến một quy trình publish nhiều bước thành transaction không gián đoạn.

## 10. Kiểm tra tính bất biến và cấu hình plugin

\`Map.copyOf\` bảo vệ cấu trúc map; mọi giá trị \`Plugin\` vẫn là reference. Nếu plugin có field mutable như cấu hình, connection pool hoặc cache, reader có thể thấy thay đổi giữa request.

Nên đặt:

- **Metadata bất biến**: ID, version, API compatibility, capability, thứ tự lựa chọn.
- **Cấu hình bất biến theo revision**: mỗi snapshot tham chiếu một configuration đã được validate.
- **State runtime rõ ownership**: tài nguyên và bộ đếm bên trong holder, quản lý riêng với map metadata.
- **Hợp đồng concurrency của plugin**: single-threaded, thread-safe, per-request instance hoặc pool có giới hạn.

Nếu plugin **không thread-safe**, việc publish vào map thread-safe không cho phép nhiều reader gọi nó đồng thời một cách an toàn. Host phải serialize invocation hoặc tạo instance riêng theo request.

Một snapshot nên có \`revision\` hoặc \`generation\` để log lựa chọn plugin, hỗ trợ trace/audit và phân biệt phiên bản trong lúc cập nhật nóng.

## 11. Lỗi, rollback và quản lý trạng thái

Một thay đổi registry có thể thất bại tại nhiều điểm:

| Giai đoạn | Lỗi | Hướng xử lý |
|---|---|---|
| Chuẩn bị | JAR hoặc metadata không hợp lệ | Không publish |
| Khởi tạo | Plugin V2 không start/health check | Giữ snapshot V1 |
| Công bố | CAS thất bại do writer khác | Tính lại snapshot hoặc từ chối theo conflict policy |
| Drain | V1 có request treo | Timeout, stop accepting, cancellation hoặc chính sách vận hành |
| Cleanup | Plugin close lỗi | Log cảnh báo, thu hồi phần còn lại và đánh dấu cần xử lý |
| Rollback | V2 có lỗi sau khi publish | Tạo/công bố snapshot rollback; không giả định V1 vẫn còn tài nguyên nếu đã đóng |

Rollback ở đây là **một lần công bố revision mới** trỏ đến plugin hợp lệ (nếu còn sử dụng được), không phải xóa dấu vết của revision trước. Nếu V1 đã đóng, rollback có thể phải khởi tạo lại.

Khi shutdown, hệ thống phải ngừng nhận request mới, chờ in-flight operations và đóng plugin trong thứ tự phụ thuộc thích hợp. Tránh giữ reference tới class loader plugin cũ trong static cache, callback hoặc thread; nếu không, hot unload có thể bị cản trở.

## 12. Kiểm thử concurrency và observability

Không thể chứng minh an toàn thread chỉ bằng một lần chạy demo. Các ca kiểm thử quan trọng:

1. Nhiều reader liên tục lấy snapshot trong khi writer thay revision.
2. Writer tạo snapshot mới nhưng chưa publish: reader không được thấy cấu hình dở dang.
3. Hai writer đồng thời thêm các key khác nhau: không được lost update.
4. Reader giữ snapshot cũ lâu; writer phải tránh close sớm.
5. Reader acquire lease đúng lúc writer chuyển DRAINING.
6. Plugin start thất bại: snapshot hiện hành không thay đổi.
7. Plugin run ném exception: lease vẫn được release trong \`finally\`.
8. Rollback, shutdown, timeout và hot reload lặp nhiều lần.

Có thể kết hợp JUnit concurrency tests, stress tests và các công cụ như JCStress để kiểm tra các giao thức atomic/visibility phức tạp. Không nên dùng \`Thread.sleep\` làm bằng chứng về thứ tự; dùng \`CountDownLatch\`, barrier hoặc test harness đồng bộ để kiểm soát race.

Ghi metrics/log theo \`registryRevision\`, \`pluginId\`, \`pluginVersion\`, thời gian publish, số in-flight calls, thời gian drain và trạng thái cleanup. Không log dữ liệu nhạy cảm từ request/plugin.

## 13. Những lỗi thường gặp

- Chia sẻ \`HashMap\` hoặc \`ArrayList\` mutable mà không đồng bộ.
- Giữ map mutable trong \`AtomicReference\` rồi tiếp tục sửa map đó.
- Nghĩ rằng \`volatile\` làm các object plugin bên trong thread-safe.
- Dùng \`ConcurrentHashMap\` nhưng đòi toàn bộ registry phải nhất quán theo một revision.
- Dùng \`set(next)\` cho nhiều writer mà không ngăn lost update.
- Khởi tạo plugin có side effect bên trong hàm CAS có thể được gọi lại.
- Đóng plugin V1 ngay sau publish V2 mà chưa đợi reader V1 hoàn thành.
- Tăng reference count không đồng bộ với thao tác đóng/drain, tạo race “acquire sau close”.
- Để reader tra cứu registry hai lần trong cùng request rồi vô tình dùng provider khác phiên bản.
- Bỏ qua cleanup của callback, thread và class loader khi hot reload.
- Cho rằng \`Map.copyOf\` tạo bản sao sâu của plugin và cấu hình.

## 14. Checklist thiết kế

Trước khi đưa plugin manager vào hoạt động:

- Snapshot được tạo hoàn chỉnh và không thể sửa cấu trúc sau publication?
- Tham chiếu active được công bố bằng \`volatile\`/\`AtomicReference\`?
- Reader giữ **một snapshot cho mỗi tác vụ logic**?
- Writer cập nhật theo single-writer policy hoặc CAS/lock tránh lost update?
- Plugin mới được khởi tạo, kiểm tra compatibility và health check trước khi publish?
- Lifecycle của plugin cũ có drain/lease hoặc lock bảo vệ trước khi close?
- Mỗi plugin tuân thủ yêu cầu thread safety trong quá trình invoke?
- Các bản registry có revision, logs và khả năng rollback rõ?
- Có test race, hot swap, cleanup, lỗi start và lỗi invoke?
- Khi plugin không đáng tin, có ranh giới bảo mật ngoài cơ chế class loader/snapshot?

**Ghi nhớ:** cách công bố một tập plugin cho reader đồng thời là **xây một immutable snapshot hoàn chỉnh, rồi swap tham chiếu bằng thao tác atomic/volatile**. Nhưng để hot swap an toàn, cần thêm **quản lý quyền sử dụng (lease) hoặc đồng bộ vòng đời** để không đóng plugin đang được một request cũ sử dụng.
