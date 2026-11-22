# Đánh giá mức hỗ trợ CRaC của thư viện và phiên bản đang dùng

Một ứng dụng Java thường phụ thuộc vào nhiều thư viện: framework web, JDBC driver, connection pool, HTTP client, message broker client, cache, logging, metrics, thư viện native và các thành phần nội bộ. Khi dùng CRaC, không thể chỉ xác nhận ứng dụng biên dịch được với JDK có API CRaC rồi kết luận toàn bộ stack tương thích.

Checkpoint ghi lại trạng thái của một tiến trình. Mỗi thư viện có thể giữ những tài nguyên với vòng đời riêng: socket, file descriptor, thread, executor, timer, lock, native handle, TLS session, connection pool hoặc trạng thái kết nối đến dịch vụ bên ngoài. Sau restore, các tài nguyên đó có thể đã hết hiệu lực hoặc không còn phù hợp với môi trường hiện tại.

Vì vậy, mức hỗ trợ CRaC phải được đánh giá theo **đúng thư viện, đúng phiên bản, đúng phiên bản JDK CRaC và đúng môi trường chạy**. Một thư viện có thể hỗ trợ CRaC ở phiên bản mới nhưng chưa hỗ trợ ở phiên bản mà ứng dụng đang dùng. Một framework có tích hợp CRaC cũng không tự động bảo đảm mọi thư viện bắc cầu của ứng dụng đều an toàn.

Mục tiêu của việc đánh giá là xác định được:

- Thư viện nào được nhà cung cấp công bố hỗ trợ CRaC cho phiên bản cụ thể.
- Thư viện nào tự quản lý lifecycle bằng CRaC Resource hoặc cơ chế tích hợp tương đương.
- Thư viện nào cần ứng dụng đóng, tái tạo hoặc xác minh tài nguyên thủ công.
- Thư viện nào chưa có bằng chứng hỗ trợ hoặc có giới hạn chưa được xử lý.
- Phiên bản JDK, CRIU, hệ điều hành và native dependency nào đã được kiểm chứng.
- Những bài kiểm thử nào phải chạy trước khi đưa checkpoint vào triển khai.

## 1. CRaC support không chỉ là khả năng biên dịch

Có ít nhất bốn khía cạnh cần phân biệt:

1. **Compile-time compatibility**: thư viện có thể được biên dịch hoặc chạy trên phiên bản Java/JDK đang dùng.
2. **Checkpoint compatibility**: trạng thái của thư viện có thể được lưu trong lúc checkpoint mà không gặp tài nguyên hoặc hoạt động không được hỗ trợ.
3. **Restore compatibility**: sau khi tiến trình được khôi phục, thư viện có thể tiếp tục hoạt động đúng hoặc tái lập tài nguyên đã mất hiệu lực.
4. **Operational support**: nhà cung cấp có tài liệu, phiên bản được hỗ trợ, quy trình xử lý lỗi và kiểm thử cho môi trường CRaC cụ thể.

Một thư viện có thể vượt qua kiểm tra compile-time nhưng vẫn thất bại khi restore. Ví dụ, HTTP client có thể tạo object bình thường nhưng giữ connection pool chứa socket cũ. Ứng dụng restore thành công, nhưng request đầu tiên lại nhận lỗi connection reset.

Ngược lại, thư viện không triển khai trực tiếp `org.crac.Resource` vẫn có thể hoạt động tốt nếu nó chỉ giữ dữ liệu Java thuần hoặc nếu ứng dụng quản lý tài nguyên của nó qua một wrapper phù hợp. Việc có hay không có lớp Resource chỉ là một dấu hiệu cần xem xét, không phải kết luận cuối cùng.

### Bốn câu hỏi khi đánh giá một dependency

| Câu hỏi | Bằng chứng cần tìm |
|---|---|
| Phiên bản này có chạy trên JDK mục tiêu không? | Java baseline, bytecode level, module và compatibility matrix |
| Có tài nguyên nào cần chuẩn bị trước checkpoint không? | Tài liệu lifecycle, danh sách socket/thread/file/native resource |
| Sau restore, thư viện tự phục hồi hay cần ứng dụng can thiệp? | CRaC integration, callback, API close/reopen hoặc hướng dẫn reconnect |
| Nhà cung cấp có xác nhận tổ hợp phiên bản đang dùng không? | Tài liệu chính thức, release note, issue đã xử lý và ma trận hỗ trợ |

Không nên dùng một câu trả lời “thư viện hỗ trợ CRaC” chung chung. Hãy ghi rõ phiên bản artifact, JDK, nền tảng và phạm vi tính năng đã được xác nhận.

## 2. Phân loại mức hỗ trợ

Để đánh giá nhất quán, có thể phân loại mỗi dependency theo các mức sau. Đây là thang đánh giá nội bộ cho dự án; nó không thay thế mức hỗ trợ chính thức do nhà cung cấp công bố.

| Mức | Ý nghĩa | Cách xử lý |
|---|---|---|
| A — Officially supported | Nhà cung cấp xác nhận CRaC cho đúng phiên bản hoặc dải phiên bản, JDK và nền tảng mục tiêu | Dùng theo hướng dẫn; vẫn chạy kiểm thử tích hợp của ứng dụng |
| B — CRaC-aware integration | Thư viện có Resource/callback hoặc module tích hợp chính thức, nhưng phạm vi hỗ trợ có điều kiện | Kiểm tra điều kiện, thứ tự callback và giới hạn của phiên bản |
| C — Application-managed | Không có tích hợp tự động đầy đủ, nhưng API công khai cho phép đóng, tạo lại và xác minh tài nguyên an toàn | Viết adapter/resource ở cấp ứng dụng và kiểm thử restore thật |
| D — Unverified | Có thể chạy trong một số thử nghiệm nhưng chưa có tài liệu hoặc bằng chứng đủ rõ | Chưa coi là được hỗ trợ; bổ sung thử nghiệm và xác nhận |
| E — Unsupported/incompatible | Nhà cung cấp tuyên bố không hỗ trợ hoặc đã xác định lỗi không thể xử lý trong cấu hình mục tiêu | Nâng cấp, thay thế hoặc loại dependency khỏi luồng checkpoint |

Ghi thêm trạng thái kiểm chứng để tránh nhầm lẫn:

- **Documented**: có tài liệu chính thức mô tả hỗ trợ.
- **Tested**: tổ hợp phiên bản đã vượt qua bài kiểm thử do dự án chạy.
- **Vendor-confirmed**: nhà cung cấp xác nhận qua tài liệu hoặc kênh hỗ trợ.
- **Limited**: chỉ hỗ trợ một số tính năng hoặc môi trường.
- **Unknown**: chưa có đủ thông tin.

Ví dụ, một thư viện có thể được phân loại là “B — CRaC-aware integration, tested trên JDK A ở Linux x86_64, chưa xác nhận trên JDK B”. Không rút gọn thành “B — supported everywhere”.

## 3. Lập danh sách dependency thực tế

Đánh giá bắt đầu từ dependency mà ứng dụng thực sự đóng gói và chạy, bao gồm dependency bắc cầu. Chỉ xem file khai báo trực tiếp trong build script sẽ bỏ sót nhiều thành phần quan trọng.

### Maven

Liệt kê dependency tree ở runtime:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Có thể xuất cây dependency ra file để lưu cùng hồ sơ đánh giá:

~~~bash
mvn dependency:tree -Dscope=runtime -DoutputFile=target/runtime-dependencies.txt
~~~

Nếu một thư viện xuất hiện nhiều phiên bản, xem dependency mediation và phiên bản cuối cùng được chọn. Dependency trực tiếp khai báo phiên bản A không có nghĩa runtime thực sự dùng A nếu một dependency khác kéo phiên bản B và Maven chọn B theo quy tắc resolution.

### Gradle

Liệt kê cấu hình runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để biết vì sao một phiên bản được chọn:

~~~bash
./gradlew dependencyInsight --dependency <library-name> --configuration runtimeClasspath
~~~

Kiểm tra cả các configuration đặc thù như runtime của integration test, plugin hoặc module triển khai nếu chúng được đóng gói vào cùng tiến trình.

### Những thành phần không nên bỏ sót

- Dependency trực tiếp và bắc cầu.
- Framework và các starter/autoconfiguration module.
- JDBC driver và connection pool.
- HTTP client, TLS provider và DNS resolver.
- Message broker, Redis hoặc cache client.
- Logging backend, async appender và exporter.
- Metrics, tracing và telemetry exporter.
- Scheduler, executor, event loop và thread pool.
- Native library, JNI, Java agent và profiler.
- Plugin được nạp động hoặc thư viện qua custom class loader.
- Thư viện nội bộ do tổ chức tự phát triển.

Không phải dependency nào cũng có cùng rủi ro. Một thư viện chỉ xử lý JSON thuần Java thường có ít tài nguyên bên ngoài hơn một driver database. Tuy nhiên, vẫn phải xem xét static state, thread, cache và lazy initialization của từng thư viện.

## 4. Xác định tài nguyên và hành vi của thư viện

Sau khi có dependency tree, phân loại từng thư viện theo những gì nó sở hữu hoặc tạo ra trong runtime.

| Loại thư viện | Tài nguyên/hành vi cần xem xét | Câu hỏi sau restore |
|---|---|---|
| JDBC driver | Socket, TLS, native code, connection state | Connection cũ có bị đóng và driver có tạo kết nối mới được không? |
| Connection pool | Connection, housekeeping thread, timer | Pool có thể được tái tạo hoặc phục hồi theo API được hỗ trợ không? |
| HTTP client | Socket pool, DNS cache, TLS session, selector/event loop | Client có loại bỏ connection cũ và kết nối lại không? |
| Message client | TCP connection, consumer group, heartbeat, offset | Client có reconnect/rejoin và xử lý message trùng an toàn không? |
| Cache client | Socket, cluster topology, local cache | Cache và topology có được xác minh lại không? |
| Scheduler | Thread, timer, lịch chạy | Task có bị chạy trùng hoặc bỏ lỡ sau restore không? |
| Executor/event loop | Thread, queue, selector | Thread đã dừng có được tạo lại đúng cách không? |
| Logging | File handle, async queue, background thread | Appender còn ghi được và không mất log không? |
| Metrics/tracing | Exporter socket, batch queue, periodic task | Exporter có flush/reconnect và tránh gửi trùng không? |
| File/storage client | File descriptor, lock, memory mapping | File/lock/mount còn hợp lệ không? |
| Native/JNI library | Native pointer, handle, thread, callback | Native state có được CRIU/runtime hỗ trợ không? |
| Cryptography/TLS | Native provider, entropy, session/cache | Provider và key material có tiếp tục hợp lệ không? |

Một thư viện có thể nằm trong nhiều nhóm. Ví dụ một client broker vừa có network connection, vừa có heartbeat thread, timer, buffer và callback. Đánh giá phải xét toàn bộ vòng đời của nó.

### Phân biệt trạng thái Java và tài nguyên bên ngoài

Object Java có thể được khôi phục trong heap trong khi tài nguyên mà object đại diện đã thay đổi. Ví dụ:

- Object `Connection` vẫn tồn tại nhưng socket đã bị peer đóng.
- Object `ScheduledExecutorService` vẫn tồn tại nhưng worker thread không còn ở trạng thái có thể tiếp tục.
- Object file wrapper còn trong heap nhưng file descriptor hoặc lock không còn hợp lệ.
- Object cache vẫn chứa dữ liệu nhưng TTL đã hết trong thời gian checkpoint.
- Object TLS client còn giữ session cũ nhưng certificate hoặc endpoint đã thay đổi.

Không suy ra tính hợp lệ của tài nguyên bên ngoài từ việc object Java không null.

## 5. Tìm bằng chứng hỗ trợ trong tài liệu và release note

Với mỗi dependency, tìm thông tin theo đúng artifact và version đang dùng. Nguồn có giá trị cao nhất thường là tài liệu chính thức, release note và compatibility matrix của nhà cung cấp.

### Thứ tự nguồn nên xem

1. **Tài liệu CRaC chính thức của nhà cung cấp**: mô tả phiên bản được hỗ trợ, cấu hình và callback cần thiết.
2. **Release notes/changelog**: tìm thay đổi liên quan checkpoint, restore, socket, thread, native state hoặc CRaC.
3. **Compatibility matrix**: đối chiếu JDK, hệ điều hành, architecture và runtime.
4. **Tài liệu tích hợp framework**: xem framework quản lý resource nào và dependency nào vẫn cần xử lý riêng.
5. **Issue/bug tracker**: tìm lỗi đã biết, phiên bản sửa lỗi, giới hạn và workaround.
6. **Test hoặc sample chính thức**: xác định tổ hợp được kiểm thử và cách tái hiện.
7. **Xác nhận từ nhà cung cấp**: dùng khi tài liệu chưa nói rõ hoặc phiên bản đang dùng nằm ngoài ma trận công bố.

Khi đọc release note, tìm các thuật ngữ như CRaC, checkpoint, restore, snapshot, restart, reconnect, native state, file descriptor, thread, socket và lifecycle. Không chỉ tìm từ khóa “CRaC”: một bản sửa lỗi reconnect hoặc thread lifecycle có thể rất quan trọng dù release note không nhắc trực tiếp đến CRaC.

### Cần ghi lại bằng chứng cụ thể

Một ghi chú “đã đọc docs” không đủ để người khác kiểm tra lại. Lưu:

- URL hoặc tên tài liệu chính thức.
- Phiên bản tài liệu và ngày truy cập.
- Tên artifact và version được nói đến.
- JDK/OS/architecture được hỗ trợ.
- Điều kiện cấu hình hoặc API bắt buộc.
- Giới hạn đã biết.
- Bài kiểm thử nội bộ đã chạy và kết quả.

Nếu tài liệu chỉ xác nhận phiên bản mới hơn phiên bản đang dùng, không tự suy ra phiên bản cũ được hỗ trợ. Nếu issue nói lỗi đã được sửa trong bản 4.2.1, hãy kiểm tra ứng dụng đang resolve đúng 4.2.1 hay vẫn dùng 4.1.x.

## 6. Kiểm tra artifact và metadata của phiên bản đang chạy

Sau khi xác định dependency tree, kiểm tra artifact thực tế trong package để tránh đánh giá nhầm phiên bản.

Có thể dùng:

~~~bash
jar tf path/to/library.jar
~~~

Để xem dependency hoặc module metadata, dùng công cụ phù hợp với định dạng artifact, chẳng hạn `jdeps` cho quan hệ phụ thuộc bytecode:

~~~bash
jdeps --recursive --summary path/to/library.jar
~~~

Nếu cần xem manifest:

~~~bash
unzip -p path/to/library.jar META-INF/MANIFEST.MF
~~~

Các lệnh này giúp xác định nội dung, package, module và một phần metadata. Chúng không chứng minh thư viện hỗ trợ CRaC. Việc tìm thấy class có tên chứa “crac” hoặc dependency tới `org.crac` chỉ là manh mối; phải đối chiếu tài liệu, hành vi thực tế và phiên bản.

### Tìm dấu hiệu tích hợp CRaC

Có thể kiểm tra package/class của artifact:

~~~bash
jar tf path/to/library.jar | grep -i crac
~~~

Hoặc kiểm tra các entry service provider:

~~~bash
jar tf path/to/library.jar | grep META-INF/services
~~~

Kết quả rỗng không chứng minh thư viện không hỗ trợ. Thư viện có thể đăng ký resource bằng code khác hoặc dựa vào adapter của framework. Ngược lại, tìm thấy một lớp triển khai Resource không chứng minh mọi thành phần của thư viện đều an toàn khi restore.

### Xác minh dependency được resolve

Với Maven/Gradle, kiểm tra dependency tree sau khi build. Nếu ứng dụng dùng fat JAR hoặc shaded JAR, xác minh version thực tế được đóng gói và tránh dựa duy nhất vào tên file trong cache của build tool.

Nếu nhiều module dùng các phiên bản khác nhau, ghi nhận từng artifact. Ví dụ, framework core có thể ở phiên bản mới nhưng starter hoặc client module vẫn ở phiên bản cũ do dependency override.

## 7. Đánh giá hỗ trợ của JDK và runtime CRaC

Một thư viện chỉ được xác nhận trong một môi trường cụ thể. Ngoài version của thư viện, cần ghi rõ:

- Nhà phân phối và phiên bản JDK CRaC.
- Phiên bản Java language/runtime baseline.
- Phiên bản CRaC API được compile và chạy.
- Phiên bản CRIU.
- Kernel và distribution Linux.
- CPU architecture.
- Container runtime, namespace, cgroup và capability.
- Native library và thư viện hệ thống.

Không giả định mọi JDK có cùng cách đóng gói hoặc cùng hành vi CRaC chỉ vì chúng cùng có tên phiên bản Java. Một bản phân phối có thể có patch, tùy chọn hoặc quy trình đóng gói khác.

### API dependency và JDK runtime

Ứng dụng có thể cần dependency cung cấp API `org.crac` để biên dịch resource. Cách khai báo và version API phải phù hợp với JDK CRaC và hướng dẫn của nhà phân phối.

Không thêm một version CRaC API tùy ý chỉ để build thành công. API compile-time không thay thế implementation/runtime của JDK, CRIU hoặc tính năng kernel cần thiết. Tránh đóng gói nhầm class API trùng lặp vào fat JAR nếu hướng dẫn runtime yêu cầu dùng API từ JDK.

### Native dependency

Nếu thư viện có JNI, native executable hoặc FFM/native access, phải đánh giá thêm:

- Native handle có thể được checkpoint/restore không?
- Có thread native hoặc callback đang chạy không?
- File descriptor, shared memory, device handle có được hỗ trợ không?
- Binary có tương thích architecture, libc và kernel ở môi trường restore không?
- Thư viện có API chính thức để giải phóng và tạo lại native state không?

Một Java wrapper có thể được khôi phục trong heap trong khi con trỏ native bên trong không còn hợp lệ. Không tự copy hoặc tái sử dụng native pointer nếu nhà cung cấp không xác nhận cách làm.

## 8. Đánh giá CRaC integration của framework

Framework có thể giúp quản lý một số resource, nhưng cần xác định chính xác phạm vi tích hợp.

### Những điều cần kiểm tra

- Framework có hỗ trợ JDK CRaC và phiên bản nào?
- Có adapter hoặc module riêng cho CRaC không?
- Framework tự đăng ký resource nào?
- Các bean/client do ứng dụng tạo có được quản lý tự động không?
- Resource có thể được đăng ký trùng khi restore không?
- Thứ tự callback giữa server, pool, broker và application resource được quy định thế nào?
- Có thể cấu hình thứ tự hoặc nhóm resource theo dependency không?
- Readiness/liveness có được giữ đúng trong lúc restore không?

Không suy ra toàn bộ stack được hỗ trợ chỉ từ việc framework có một integration module. Ví dụ, framework có thể dừng embedded web server nhưng không biết ứng dụng tự tạo một native client hoặc một scheduler ngoài container.

### Framework và thư viện con

Tạo bảng ownership:

| Thành phần | Ai sở hữu lifecycle? | Cần xác minh |
|---|---|---|
| Embedded web server | Framework hoặc application | Listener, accept thread, active request |
| JDBC DataSource | Framework/pool/library | Pool close/recreate và validation |
| HTTP client | Application/library | Connection pool, DNS và TLS |
| Message consumer | Application/library | Pause, ack, rejoin và offset |
| Scheduler | Framework/application | Job đang chạy, duplicate schedule |
| Custom native client | Application/vendor | Native state và API recreate |

Mỗi tài nguyên nên có một owner chịu trách nhiệm rõ ràng. Nếu framework và application cùng đăng ký resource để đóng một pool hoặc server, có thể xảy ra đóng hai lần, mở hai lần hoặc thứ tự không an toàn.

## 9. Khi thư viện không có hỗ trợ CRaC tích hợp

Không có tích hợp chính thức không đồng nghĩa phải thay thư viện ngay. Trước tiên xác định thư viện có API công khai cho phép quản lý vòng đời hay không.

Một adapter ở cấp ứng dụng có thể phù hợp khi:

- Tài nguyên có thể đóng hoàn toàn trước checkpoint.
- Có factory để tạo instance mới sau restore.
- Có health check hoặc thao tác xác minh thực tế.
- Các service dùng một provider/proxy ổn định thay vì giữ tham chiếu tới instance cũ.
- Nhà cung cấp không cấm hoặc không cảnh báo về cách sử dụng đó.

Adapter không phù hợp khi thư viện giữ native state không thể giải phóng, có thread nội bộ không thể dừng, hoặc trạng thái không thể tái tạo từ API công khai.

### Mẫu Resource quản lý một client

Ví dụ dưới đây dùng interface do ứng dụng định nghĩa. `LibraryClient` đại diện cho client của một thư viện; `ClientFactory` tạo client mới; `ClientProvider` giữ tham chiếu hiện tại để các service lấy client sau restore.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.concurrent.atomic.AtomicReference;

public final class LibraryClientResource implements Resource {

    public interface LibraryClient extends AutoCloseable {
        void verify() throws Exception;

        @Override
        void close() throws Exception;
    }

    @FunctionalInterface
    public interface ClientFactory {
        LibraryClient create() throws Exception;
    }

    public static final class ClientProvider {
        private final AtomicReference<LibraryClient> current =
                new AtomicReference<>();

        public LibraryClient get() {
            LibraryClient client = current.get();
            if (client == null) {
                throw new IllegalStateException("Client is not ready");
            }
            return client;
        }

        LibraryClient detach() {
            return current.getAndSet(null);
        }

        void install(LibraryClient client) {
            if (!current.compareAndSet(null, client)) {
                throw new IllegalStateException("A client is already installed");
            }
        }
    }

    private final ClientFactory factory;
    private final ClientProvider provider;

    public LibraryClientResource(
            ClientFactory factory,
            ClientProvider provider) {
        this.factory = factory;
        this.provider = provider;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        LibraryClient oldClient = provider.detach();
        if (oldClient != null) {
            oldClient.close();
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        LibraryClient candidate = factory.create();
        try {
            candidate.verify();
            provider.install(candidate);
        } catch (Exception failure) {
            try {
                candidate.close();
            } catch (Exception closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }
}
~~~

Đây là mẫu lifecycle, không phải adapter có thể áp dụng nguyên trạng cho mọi thư viện. Trong ứng dụng thật:

- Admission phải đóng và request đang dùng client phải drain trước khi detach.
- Provider cần được inject vào mọi consumer; không để service giữ trực tiếp client cũ.
- Factory phải dùng cấu hình và credential hiện hành.
- `verify()` phải kiểm tra khả năng hoạt động thật, không chỉ kiểm tra object khác null.
- Nếu việc tạo client thất bại, readiness phải giữ false.
- Cần quy định rollback khi checkpoint bị hủy sau khi client đã đóng.
- Không tạo lại thread hoặc scheduler nếu thư viện đã có integration quản lý chúng.

Nếu thư viện có API CRaC chính thức, ưu tiên tích hợp đó. Adapter thủ công chỉ nên dùng khi vòng đời của tài nguyên đã được hiểu và nhà cung cấp không khuyến cáo cách làm khác.

## 10. Đánh giá các nhóm thư viện thường gặp

### JDBC driver và connection pool

Kiểm tra driver có hỗ trợ JDK/runtime mục tiêu, pool có tài liệu CRaC và connection có được đóng trước checkpoint hay không.

Cần thử:

- Database restart hoặc failover giữa checkpoint và restore.
- Credential được rotate.
- DNS/endpoint đổi.
- Pool cũ bị đóng và pool mới được tạo.
- Connection validation thực hiện được truy vấn nhẹ.
- Nhiều instance restore đồng thời không gây connection storm.

Đừng đánh giá chỉ bằng việc `DataSource` còn tồn tại sau restore. Pool object có thể còn trong heap nhưng mọi connection bên trong đã stale.

### HTTP client và networking

Kiểm tra socket pool, selector/event loop, DNS cache, TLS session, proxy configuration và timeout.

Cần thử:

- Đóng connection trước checkpoint.
- Restore khi server phía bên kia đã restart.
- Tạo connection mới và thực hiện request thật.
- Kiểm tra TLS/certificate và credential.
- Kiểm tra event loop/thread không bị dừng hoặc nhân đôi.

### Message broker

Kiểm tra client có lifecycle để pause/close và reconnect/rejoin sau restore không. Cần xác minh consumer group, partition assignment, offset, heartbeat và acknowledgment.

Thử checkpoint khi consumer đang xử lý message, sau đó restore và xác minh không mất message hoặc xử lý trùng ngoài chính sách. Ứng dụng vẫn cần idempotency/deduplication; CRaC không tạo transaction phân tán với broker.

### Cache client và local cache

Kiểm tra kết nối đến cache server, cluster topology, subscription/invalidation và TTL. Dữ liệu local trong heap có thể hết hạn trong lúc tiến trình tạm dừng. Xác định cache nào có thể giữ, cache nào phải refresh và cache miss có tạo tải đột biến lên database hay không.

### Logging, metrics và tracing

Kiểm tra file appender, async queue, background exporter, batch buffer, socket và periodic task. Sau restore, cần xác minh log tiếp tục được ghi, exporter kết nối lại và telemetry không bị mất hoặc gửi trùng quá mức.

Không dùng việc log console vẫn xuất hiện làm bằng chứng rằng mọi appender hoặc exporter đã phục hồi.

### Scheduler và executor

Kiểm tra thread lifecycle, task đang chạy, queue, timer và lịch định kỳ. Một executor object còn trong heap không bảo đảm worker thread đã sẵn sàng. Không gọi `start()` lần hai trên một Thread đã kết thúc; cần tạo worker mới theo API của thư viện.

Thử restore gần thời điểm một job bắt đầu để xác minh không bỏ lỡ hoặc chạy trùng. Với job nghiệp vụ, cần cơ chế lease, idempotency hoặc trạng thái bền vững.

### Native/JNI và thư viện hệ thống

Yêu cầu tài liệu rõ ràng về native state và khả năng checkpoint/restore. Nếu nhà cung cấp không xác nhận, phân loại là unverified hoặc unsupported cho đến khi có bằng chứng.

Không giả định một native pointer, file descriptor hoặc callback được lưu trong heap sẽ còn hợp lệ sau restore. Nếu thư viện có API close/reinitialize, phải kiểm tra đó là quy trình được hỗ trợ chính thức.

## 11. Lập compatibility matrix

Ma trận giúp đội phát triển và vận hành biết chính xác tổ hợp nào đã được kiểm chứng.

Ví dụ cấu trúc:

| Thành phần | Artifact/version | CRaC support | JDK/OS đã kiểm tra | Resource owner | Kết quả |
|---|---|---|---|---|---|
| Web framework | Ghi version thực tế | Official / partial / unknown | Ghi tổ hợp cụ thể | Framework | Pending / Pass / Fail |
| JDBC driver | Ghi version thực tế | Vendor-confirmed / unknown | Ghi tổ hợp cụ thể | App/pool | Pending / Pass / Fail |
| Connection pool | Ghi version thực tế | CRaC-aware / manual | Ghi tổ hợp cụ thể | Pool adapter | Pending / Pass / Fail |
| HTTP client | Ghi version thực tế | Manual / unknown | Ghi tổ hợp cụ thể | App/client | Pending / Pass / Fail |
| Broker client | Ghi version thực tế | Official / limited | Ghi tổ hợp cụ thể | Client adapter | Pending / Pass / Fail |
| Native library | Ghi version thực tế | Supported / unsupported | OS/arch cụ thể | Vendor/app | Pending / Pass / Fail |

Với mỗi dòng, ghi thêm:

- Link tài liệu hoặc release note.
- Phiên bản nhỏ nhất được xác nhận.
- Known limitations.
- Cấu hình bắt buộc.
- Test case và ngày kiểm thử.
- Người/nhóm sở hữu việc cập nhật.

Không để các nhãn “Pass” mà không có tổ hợp version. “Pass trên Java 21” là chưa đủ nếu dự án có nhiều bản phân phối JDK hoặc nhiều kiến trúc CPU.

## 12. Quy trình đánh giá từ dependency tree đến quyết định

Có thể thực hiện theo các bước sau:

### Bước 1 — Chốt môi trường mục tiêu

Ghi JDK CRaC distribution/version, CRIU, kernel, Linux distribution, architecture, container runtime và cấu hình quyền. Đây là nền để đối chiếu compatibility.

### Bước 2 — Xuất dependency tree runtime

Lấy toàn bộ dependency runtime từ Maven/Gradle, bao gồm dependency bắc cầu. Xác định version cuối cùng được resolve và artifact thực sự được đóng gói.

### Bước 3 — Phân loại tài nguyên

Với từng thư viện, ghi socket, thread, timer, file, native state, cache hoặc external connection mà nó sở hữu. Xác định ai là owner của lifecycle.

### Bước 4 — Tìm bằng chứng nhà cung cấp

Đọc CRaC documentation, compatibility matrix, release note và issue đã biết. Ghi đúng version và điều kiện. Nếu thông tin chưa rõ, hỏi nhà cung cấp hoặc giữ trạng thái unverified.

### Bước 5 — Chọn cách quản lý

Chọn một trong các hướng:

- Dùng tích hợp CRaC chính thức của thư viện.
- Dùng tích hợp của framework nếu nó bao phủ đúng resource.
- Viết adapter bằng API công khai khi việc đóng/tạo lại được hỗ trợ.
- Nâng cấp lên phiên bản được xác nhận.
- Thay thế hoặc loại dependency không tương thích khỏi tiến trình checkpoint.

### Bước 6 — Kiểm thử từng dependency

Tạo test tối thiểu để chứng minh resource có thể đóng trước checkpoint và phục hồi sau restore. Kiểm tra lỗi khi dependency không sẵn sàng và xác nhận readiness không mở sớm.

### Bước 7 — Kiểm thử toàn bộ ứng dụng

Chạy checkpoint/restore thật với dependency tree và cấu hình production-like. Kiểm tra luồng request, background job, telemetry và dữ liệu nghiệp vụ.

### Bước 8 — Ghi quyết định và điều kiện phát hành

Lưu compatibility matrix, giới hạn, phiên bản đã test, log kết quả và người chịu trách nhiệm. Chỉ đưa tổ hợp vào phát hành khi các dependency bắt buộc đã có bằng chứng phù hợp.

## 13. Kiểm thử checkpoint/restore cho thư viện

Một bài kiểm thử compile hoặc unit test thông thường không đủ. Cần kiểm thử trong JVM CRaC thật và môi trường hệ điều hành mục tiêu.

### Các giai đoạn cần xác nhận

1. Ứng dụng khởi động với đúng dependency version.
2. Thư viện tạo tài nguyên và hoạt động bình thường.
3. Callback trước checkpoint được gọi và tài nguyên được đóng/tạm dừng theo hướng dẫn.
4. Checkpoint hoàn tất.
5. Restore ảnh trong môi trường mục tiêu.
6. Callback sau restore tạo lại hoặc xác minh tài nguyên.
7. Thao tác thực tế qua thư viện thành công.
8. Readiness chỉ bật sau khi các dependency bắt buộc đã sẵn sàng.

### Ma trận tình huống

| Tình huống | Điều cần xác minh |
|---|---|
| Restore bình thường | Resource phục hồi và thao tác thực tế thành công |
| Dependency bên ngoài restart | Client reconnect hoặc báo lỗi có kiểm soát |
| Credential rotate | Client dùng credential hiện hành |
| DNS/endpoint thay đổi | Client không dùng địa chỉ cũ đã cache |
| Resource đóng thất bại | Checkpoint không được coi là an toàn |
| Restore callback thất bại | Instance không mở readiness |
| Restore nhiều lần từ cùng ảnh | Không đăng ký Resource, thread hoặc scheduler trùng |
| Tải đồng thời tăng | Không tạo connection storm hoặc worker tăng vô hạn |
| Shutdown bình thường | Lifecycle không bị nhầm với checkpoint pause |
| Nhiều resource phụ thuộc nhau | Thứ tự đóng/mở được xác định và kiểm chứng |

### Test đơn vị và test tích hợp

Unit test phù hợp để kiểm tra adapter:

- `beforeCheckpoint` đóng client.
- `afterRestore` tạo client mới.
- Client candidate lỗi thì được đóng.
- Provider không công bố client chưa xác minh.
- Exception được truyền ra và readiness vẫn false.

Integration test cần chứng minh hành vi thật:

- CRaC gọi callback trong lifecycle thực.
- Socket/file/native state hoạt động đúng.
- Database, broker hoặc server bên ngoài có thể restart.
- Ứng dụng tiếp tục phục vụ sau restore.

Không dùng mock để kết luận native library hoặc socket được CRIU hỗ trợ. Mock chỉ xác nhận logic adapter.

## 14. Quản lý version và nâng cấp dependency

Hỗ trợ CRaC có thể được bổ sung hoặc thay đổi giữa các phiên bản thư viện. Vì vậy, mỗi lần nâng cấp dependency cần cập nhật compatibility matrix.

Khi nâng cấp:

- Xác định version mới có CRaC support chính thức hay không.
- Đọc migration guide và breaking changes.
- Kiểm tra API callback hoặc resource registration có thay đổi không.
- Kiểm tra transitive dependency có bị nâng hoặc hạ version không.
- Chạy lại test checkpoint/restore cho resource bị ảnh hưởng.
- Đo lại latency, memory và thời gian phục hồi nếu thay đổi lifecycle.

Không nâng cấp một dependency riêng lẻ nếu framework quản lý version qua BOM hoặc platform mà không kiểm tra toàn bộ dependency resolution. Việc ép một version mới có thể tạo xung đột binary hoặc API.

### Pin version trong môi trường sản xuất

Ghi rõ version được kiểm chứng và tránh dùng dynamic version hoặc range không kiểm soát cho dependency quan trọng. Nếu build có thể resolve version khác giữa hai lần, ảnh checkpoint được tạo từ một dependency set nhưng restore lại chạy artifact khác có thể gây lỗi khó điều tra.

Với checkpoint artifact, lưu metadata bên ngoài ảnh gồm:

- Application build/version.
- Dependency lockfile hoặc dependency tree.
- JDK distribution/version.
- JVM flags.
- CRIU/kernel/OS/architecture.
- Checkpoint creation timestamp và ID.

Metadata này giúp xác định ảnh được tạo từ tổ hợp nào và có phù hợp với runtime restore hiện tại hay không.

## 15. Những dấu hiệu cần điều tra thêm

| Dấu hiệu | Khả năng cần xem xét |
|---|---|
| Checkpoint báo lỗi liên quan thread hoặc file descriptor | Thư viện còn tài nguyên hoạt động hoặc chưa có CRaC integration |
| Restore thành công nhưng request đầu thất bại | Connection cũ, DNS/TLS hoặc resource chưa được tạo lại |
| Thread count tăng sau mỗi lần restore | Worker/executor được khởi tạo trùng |
| CPU tăng bất thường sau restore | Warm-up, JIT, retry hoặc background task trùng |
| Log/exporter ngừng hoạt động | Appender hoặc telemetry client không được phục hồi |
| Native crash sau restore | Native state hoặc library chưa hỗ trợ môi trường checkpoint/restore |
| Lỗi chỉ xuất hiện ở một JDK patch | Tổ hợp JDK/library/runtime có khác biệt version |
| Lỗi chỉ xuất hiện trong container | Namespace, cgroup, capability, mount hoặc network khác |
| Lỗi chỉ xảy ra với dependency bắc cầu | Phiên bản thực tế khác với dependency trực tiếp được xem xét |

Khi điều tra, ghi lại stack trace, phiên bản artifact, JDK, CRIU, kernel và điều kiện tái hiện. Tránh quy kết lỗi cho “CRaC nói chung” khi chưa xác định thành phần hoặc version gây ra.

## 16. Checklist đánh giá hỗ trợ CRaC

### Inventory và version

- [ ] Đã xuất dependency tree runtime đầy đủ, gồm dependency bắc cầu.
- [ ] Đã xác định version artifact thực sự được resolve và đóng gói.
- [ ] Đã ghi JDK CRaC distribution/version, CRIU, kernel, OS và architecture.
- [ ] Đã rà soát framework, driver, pool, network client, broker, scheduler, logging và native library.

### Bằng chứng hỗ trợ

- [ ] Đã đọc tài liệu CRaC và release note của đúng version.
- [ ] Đã kiểm tra compatibility matrix và known limitations.
- [ ] Đã phân biệt official support với kết quả thử nghiệm nội bộ.
- [ ] Không kết luận chỉ từ việc tìm thấy hoặc không tìm thấy class Resource.
- [ ] Đã ghi nguồn bằng chứng và tổ hợp môi trường cụ thể.

### Lifecycle và ownership

- [ ] Đã xác định resource nào cần đóng hoặc tạm dừng trước checkpoint.
- [ ] Đã xác định resource nào cần tạo lại hoặc xác minh sau restore.
- [ ] Mỗi tài nguyên có một owner quản lý lifecycle rõ ràng.
- [ ] Các provider/proxy không để consumer giữ tham chiếu đến object cũ đã đóng.
- [ ] Thread, scheduler, socket, file và native state có cách xử lý được hỗ trợ.

### Kiểm thử và phát hành

- [ ] Đã chạy checkpoint/restore thật trên JDK và OS mục tiêu.
- [ ] Đã thử dependency restart, credential/DNS thay đổi và lỗi phục hồi.
- [ ] Đã xác minh request, background job và telemetry sau restore.
- [ ] Readiness chỉ mở sau khi dependency bắt buộc sẵn sàng.
- [ ] Compatibility matrix có kết quả, giới hạn và ngày kiểm thử.
- [ ] Dependency version và metadata của checkpoint được ghi nhận.

Đánh giá CRaC support là việc xác nhận một tổ hợp cụ thể của thư viện, phiên bản, JDK và môi trường. Dependency tree cho biết ứng dụng thực sự chạy những artifact nào; tài liệu nhà cung cấp cho biết phạm vi hỗ trợ; phân tích lifecycle chỉ ra tài nguyên cần quản lý; còn checkpoint/restore integration test chứng minh hành vi trong hệ thống thực tế. Khi lưu lại bằng chứng và compatibility matrix, đội phát triển có thể quyết định rõ thư viện nào dùng trực tiếp, thư viện nào cần adapter, thư viện nào phải nâng cấp hoặc thay thế trước khi đưa CRaC vào sản xuất.
