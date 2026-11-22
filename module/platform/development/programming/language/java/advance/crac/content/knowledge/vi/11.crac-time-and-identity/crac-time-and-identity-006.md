# ID tiến trình, tên máy và định danh bản sao sau restore

Khi một ứng dụng Java được khôi phục từ ảnh CRaC, các object trong heap trở lại trạng thái đã được lưu. Những giá trị nhận diện môi trường tại thời điểm checkpoint cũng có thể còn nằm trong bộ nhớ: PID, hostname đã đọc, container metadata, địa chỉ IP, tên node hoặc một UUID được tạo khi ứng dụng khởi động.

Các giá trị này không có cùng vòng đời. PID là định danh của một tiến trình trong một phạm vi hệ điều hành; hostname mô tả tên máy hoặc môi trường mạng; replica ID mô tả một bản sao logic của dịch vụ; còn process incarnation ID nhận diện một lần chạy cụ thể. Nếu dùng nhầm một giá trị tạm thời làm định danh bền vững, log, metric, lock và service discovery có thể trỏ đến sai tiến trình sau restore.

Thiết kế nên phân biệt rõ:

- **Service identity**: tên dịch vụ hoặc ứng dụng, thường ổn định qua nhiều lần chạy.
- **Replica identity**: định danh bản sao logic do nền tảng triển khai cấp hoặc cấu hình.
- **Process identity**: PID hiện tại trong namespace của hệ điều hành.
- **Process incarnation identity**: UUID mới cho mỗi lần JVM khởi động mới hoặc được restore.
- **Host identity**: hostname hoặc định danh node/container tại môi trường đang chạy.
- **Checkpoint identity**: mã nhận diện ảnh checkpoint hoặc phiên bản artifact đã tạo ra trạng thái.
- **Restore attempt identity**: mã nhận diện một lần khôi phục cụ thể, hữu ích khi thử restore nhiều lần.

Không nên gộp các khái niệm này thành một chuỗi duy nhất như pid@hostname. Chúng trả lời những câu hỏi khác nhau và có thể thay đổi ở những thời điểm khác nhau.

## 1. PID là gì và vì sao không thể dùng làm định danh lâu dài?

PID (Process ID) là số mà hệ điều hành cấp cho một tiến trình. Trên Linux, PID có phạm vi theo PID namespace. Trong container, PID mà ứng dụng nhìn thấy có thể khác PID của tiến trình đó trên host.

Java 9 trở lên cung cấp ProcessHandle.current().pid() để lấy PID của JVM hiện tại:

~~~java
long pid = ProcessHandle.current().pid();
System.out.println("Current process PID: " + pid);
~~~

PID hữu ích để:

- Tìm tiến trình khi xem log và công cụ giám sát hệ điều hành.
- Liên kết một lần đo CPU/RSS với tiến trình cụ thể.
- Hỗ trợ thao tác quản trị hoặc chẩn đoán trong cùng môi trường.
- Xác định tiến trình đang giữ socket hoặc file trong một namespace.

PID không phải định danh toàn cục hoặc bền vững:

- PID có thể được tái sử dụng sau khi tiến trình kết thúc.
- PID nhìn thấy trong container có thể khác PID trên host.
- Khi restore, PID có thể được giữ hoặc được cấp khác tùy cách runtime, CRIU và namespace được cấu hình.
- Một ảnh được chuyển sang môi trường khác không bảo đảm tiến trình sẽ có cùng PID.
- PID không xác định duy nhất một phiên bản ứng dụng hoặc một bản sao logic.

Vì vậy, không lưu PID vào cơ sở dữ liệu làm khóa lâu dài, không dùng PID làm idempotency key và không giả định PID trước checkpoint vẫn là PID sau restore.

### Đọc PID tại thời điểm cần dùng

Nếu log cần PID, hãy lấy PID hiện tại khi ghi log hoặc tạo một snapshot runtime sau restore. Tránh đọc PID một lần lúc khởi động rồi giữ trong static final long PID, vì giá trị đó được giữ trong heap checkpoint và có thể đã cũ sau restore.

~~~java
public final class ProcessInfo {

    private ProcessInfo() {
    }

    public static long currentPid() {
        return ProcessHandle.current().pid();
    }
}
~~~

Gọi ProcessInfo.currentPid() khi cần ghi nhận tiến trình hiện tại. Nếu cần liên kết PID với host PID, phải dùng thông tin từ nền tảng/container runtime; PID Java trả về không tự cung cấp PID ngoài namespace.

## 2. Hostname mô tả môi trường, không phải định danh duy nhất

Hostname là tên máy hoặc tên host mà hệ điều hành và hệ thống phân giải tên sử dụng. Trong Java có thể lấy hostname theo cách đơn giản:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

public final class HostInfo {

    private HostInfo() {
    }

    public static String currentHostName() {
        try {
            return InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException failure) {
            return "unknown";
        }
    }
}
~~~

Lời gọi này phụ thuộc cấu hình hostname và name service của môi trường. Nó có thể không trả về tên mà đội vận hành mong muốn, có thể chậm khi DNS hoặc cấu hình mạng có vấn đề, và không phải lúc nào cũng là tên canonical.

Hostname có thể:

- Giữ nguyên khi một container hoặc tiến trình được restore trong cùng môi trường.
- Thay đổi khi instance được tạo trên node khác.
- Được dùng chung bởi nhiều tiến trình trên một máy.
- Trùng hoặc thay đổi theo quy tắc đặt tên của nền tảng.
- Không phản ánh đúng địa chỉ IP mà client có thể truy cập.

Do đó, hostname phù hợp để hỗ trợ chẩn đoán và phân nhóm log, nhưng không nên là khóa duy nhất cho một tiến trình hoặc một replica.

### Không suy ra địa chỉ mạng từ hostname

Hostname và IP address là hai dữ liệu khác nhau. Một hostname có thể phân giải ra nhiều địa chỉ, DNS có thể thay đổi sau failover và container có thể nhận IP mới. Nếu ứng dụng cần địa chỉ để bind socket hoặc công bố endpoint, hãy lấy từ cấu hình mạng/service discovery phù hợp, rồi xác minh listener đã bind thành công.

Không nên gọi InetAddress.getLocalHost() như một phép kiểm tra readiness database hoặc network. Nó chỉ phản ánh thông tin host theo cấu hình resolver; không chứng minh một dependency bên ngoài có thể truy cập.

## 3. Phân biệt service, replica và process incarnation

Trong triển khai nhiều bản sao, một dịch vụ thường có nhiều instance cùng phục vụ. Cần định danh ở nhiều tầng.

| Định danh | Ví dụ | Vòng đời | Dùng cho |
|---|---|---|---|
| Service ID | orders-api | Ổn định qua các lần triển khai | Nhóm log, metric và cấu hình |
| Replica ID | orders-api-2 hoặc ID do orchestrator cấp | Theo vòng đời bản sao logic | Phân biệt các bản sao cùng service |
| Process incarnation ID | UUID mới mỗi lần chạy/restore | Một lần chạy cụ thể | Phân biệt các incarnation trong log và tracing |
| PID | 4217 | Theo tiến trình trong namespace | Chẩn đoán hệ điều hành |
| Hostname | node-a hoặc tên pod | Theo môi trường host | Chẩn đoán và phân vùng triển khai |
| Checkpoint ID | release-2026-11-13-01 | Theo artifact checkpoint | Truy vết nguồn gốc ảnh |
| Restore attempt ID | UUID cho mỗi lần restore | Một lần thử restore | Phân tích lỗi và retry |

### Replica ID không nhất thiết là process ID

Một replica logic có thể trải qua nhiều process incarnation:

1. Replica orders-api-2 khởi động lần đầu với PID 120 và incarnation A.
2. Ứng dụng tạo checkpoint.
3. JVM được restore với PID 120 hoặc PID khác, tùy môi trường; incarnation mới là B.
4. Replica logic vẫn có thể là orders-api-2, nếu nền tảng khôi phục đúng bản sao đó.

Nếu ảnh được restore vào một pod mới, replica ID có thể đổi theo pod hoặc instance mới. Nếu hệ thống dùng StatefulSet ordinal hay một logical replica key, nó có thể giữ nguyên qua lần tạo lại pod. Chính sách này thuộc nền tảng triển khai, không do CRaC tự quyết định.

### Process incarnation ID

Incarnation ID là một UUID được tạo mới mỗi khi ứng dụng khởi động mới hoặc được khôi phục. Nó giúp phân biệt:

- Log trước checkpoint và log sau restore.
- Hai tiến trình cùng chạy trên một host.
- Một replica đã trải qua nhiều lần restore.
- Một lần restore thành công với lần restore khác từ cùng ảnh.

Nếu UUID được tạo trước checkpoint rồi lưu trong heap, sau restore UUID đó vẫn được khôi phục. Khi cần nhận diện lần chạy mới, phải tạo UUID mới trong afterRestore().

## 4. Vì sao định danh trong heap có thể trở nên cũ?

Checkpoint lưu object graph tại một thời điểm. Một trường final hoặc static chứa PID, hostname hay container ID có thể được khôi phục cùng giá trị cũ.

Ví dụ:

~~~java
public final class RuntimeIdentity {
    public static final long PID = ProcessHandle.current().pid();
    public static final String HOST =
            HostInfo.currentHostName();
}
~~~

Các giá trị trên được tính khi class được khởi tạo. Nếu class đã được khởi tạo trước checkpoint, chúng có thể tiếp tục tồn tại sau restore. Không nên dùng chúng như thông tin runtime hiện tại.

Các trường hợp thường gặp:

- PID cũ được giữ trong object hoặc static field.
- Hostname được đọc một lần rồi cache.
- UUID của process được tạo lúc startup và được giữ trong heap.
- Container ID hoặc pod name được đọc từ environment variable trước checkpoint.
- Địa chỉ IP hoặc endpoint được resolve rồi cache trong client.
- Một thread-local hoặc singleton giữ thông tin node cũ.

Không phải mọi giá trị đều chắc chắn thay đổi sau restore. Vấn đề là ứng dụng không thể mặc định chúng còn đúng. Cần phân loại trường nào là cấu hình ổn định, trường nào phải refresh và trường nào chỉ dùng để ghi nhận lịch sử.

### System.getenv và system properties

System.getenv() trả về environment variables của tiến trình. Java không cung cấp API portable để thay đổi environment map đang tồn tại hoặc yêu cầu nó đọc lại một environment mới từ bên ngoài. Nếu giá trị được khôi phục từ ảnh, đừng giả định nó tự cập nhật chỉ vì container hoặc orchestrator đã thay đổi cấu hình bên ngoài.

System.getProperty() trả về system properties hiện tại trong JVM. Những giá trị được lưu trong heap hoặc cấu hình lúc khởi chạy cũng có thể không phản ánh cấu hình mới của một môi trường khác.

Nếu cần định danh động từ nền tảng, hãy truy vấn nguồn được hỗ trợ sau restore hoặc nhận thông tin qua một provider được cập nhật có kiểm soát. Không dùng environment variable đã lưu trong heap như bằng chứng rằng tiến trình hiện đang ở cùng một host hoặc pod.

## 5. Thiết kế identity provider cho CRaC

Thay vì để nhiều service tự đọc PID, hostname và UUID, tạo một thành phần quản lý identity thống nhất. Thành phần này:

1. Tạo incarnation ID khi JVM khởi động mới.
2. Đăng ký làm CRaC Resource.
3. Sau restore, đọc PID hiện tại và hostname theo nhu cầu.
4. Lấy replica identity từ provider cấu hình hoặc nền tảng.
5. Tạo incarnation ID mới cho lần restore.
6. Công bố một snapshot bất biến để các thành phần khác đọc.

Ví dụ sau dùng Java record (Java 16 trở lên). ReplicaIdProvider là abstraction của ứng dụng; nó có thể đọc một ID logic đã cấu hình hoặc lấy ID hiện hành từ nền tảng triển khai.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

public final class RuntimeIdentityResource implements Resource {

    @FunctionalInterface
    public interface ReplicaIdProvider {
        String currentReplicaId() throws Exception;
    }

    public record IdentitySnapshot(
            String serviceId,
            String replicaId,
            String incarnationId,
            long pid,
            String hostName,
            Instant observedAt,
            String phase) {
    }

    private final String serviceId;
    private final ReplicaIdProvider replicaIdProvider;
    private final AtomicReference<IdentitySnapshot> current =
            new AtomicReference<>();

    public RuntimeIdentityResource(
            String serviceId,
            ReplicaIdProvider replicaIdProvider) throws Exception {
        this.serviceId = serviceId;
        this.replicaIdProvider = replicaIdProvider;
        current.set(capture("startup"));
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        // Giữ snapshot cũ để truy vết nguồn gốc của checkpoint.
        // Không tạo incarnation mới tại thời điểm checkpoint.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Đây là một process incarnation mới.
        current.set(capture("restore"));
    }

    public IdentitySnapshot current() {
        IdentitySnapshot snapshot = current.get();
        if (snapshot == null) {
            throw new IllegalStateException("Runtime identity is not initialized");
        }
        return snapshot;
    }

    private IdentitySnapshot capture(String phase) throws Exception {
        String replicaId = replicaIdProvider.currentReplicaId();
        if (replicaId == null || replicaId.isBlank()) {
            throw new IllegalStateException("Replica ID is unavailable");
        }

        return new IdentitySnapshot(
                serviceId,
                replicaId,
                UUID.randomUUID().toString(),
                ProcessHandle.current().pid(),
                resolveHostName(),
                Instant.now(),
                phase
        );
    }

    private static String resolveHostName() {
        try {
            return InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException failure) {
            return "unknown";
        }
    }
}
~~~

Trong ví dụ:

- serviceId là định danh ổn định của ứng dụng.
- replicaIdProvider quyết định định danh bản sao logic theo môi trường.
- incarnationId được tạo mới trong constructor và được thay mới trong afterRestore().
- PID được đọc tại thời điểm snapshot được tạo.
- Hostname được lấy theo môi trường tại thời điểm capture; nếu không xác định được thì dùng giá trị chẩn đoán unknown.
- AtomicReference công bố snapshot bất biến để các thread khác đọc nhất quán.

Ví dụ dùng InetAddress.getLocalHost() để minh họa. Trong hệ thống có yêu cầu hostname chính xác hoặc truy vấn hostname có thể block, hãy thay bằng một HostIdentityProvider phù hợp với nền tảng và đặt timeout. Hostname không phải dependency bắt buộc của ứng dụng; lỗi phân giải hostname thường không nên ngăn database hoặc server phục hồi.

Nếu replica ID là bắt buộc để định tuyến hoặc bảo đảm tính duy nhất, việc không lấy được ID phải giữ ứng dụng chưa sẵn sàng. Nếu chỉ dùng ID đó để bổ sung log, có thể dùng giá trị fallback có chủ đích và ghi nhận rằng metadata chưa đầy đủ.

### Khởi động mới và restore

Constructor chạy khi JVM khởi động mới và tạo incarnation đầu tiên. Khi restore, object resource được khôi phục từ heap nên không tạo lại bằng constructor; CRaC gọi afterRestore() trên resource đã đăng ký. Vì vậy, việc tạo UUID mới trong afterRestore() là cần thiết để đánh dấu lần chạy mới.

Không đăng ký thêm cùng resource trong afterRestore(). Resource đã được đăng ký trước checkpoint và trạng thái đăng ký thuộc lifecycle được CRaC quản lý.

## 6. Lấy định danh từ container và orchestrator

Trong môi trường container, hostname, container ID, pod name và pod UID là các khái niệm khác nhau.

| Giá trị | Ý nghĩa | Lưu ý khi restore |
|---|---|---|
| Container hostname | Hostname nhìn thấy bên trong container | Có thể được cấu hình; không bảo đảm duy nhất |
| Container ID | ID container do runtime cấp | Không có API Java portable; có thể thay khi tạo container mới |
| Pod name | Tên pod trong Kubernetes | Có thể giữ theo quy tắc StatefulSet hoặc đổi khi thay pod |
| Pod UID | ID duy nhất của một pod incarnation | Pod mới có UID mới dù tên có thể giống |
| Node name | Tên node chạy pod | Có thể đổi khi pod được schedule sang node khác |
| Host PID | PID trên host, ngoài PID namespace | Khác với PID mà JVM trong container nhìn thấy |

Nếu ứng dụng cần Pod UID, có thể đưa giá trị đó vào container bằng Kubernetes Downward API. Nếu cần node name hoặc pod name, cũng có thể cung cấp qua cơ chế tương tự. Tuy nhiên, giá trị được đưa vào environment lúc container khởi động sẽ không tự đổi bên trong một process đã checkpoint khi pod hoặc môi trường bên ngoài thay đổi.

Với thông tin cần cập nhật sau restore, nên dùng một nguồn động được nền tảng hỗ trợ, ví dụ API nội bộ hoặc file được mount và cập nhật theo cơ chế rõ ràng. Cần phân biệt file cấu hình tĩnh với projected volume có thể cập nhật; cách mount và thời gian cập nhật tùy nền tảng.

### Restore trong cùng pod và restore sang pod mới

**Restore trong cùng pod/container**: pod UID, container ID hoặc hostname thường vẫn thuộc cùng môi trường. PID vẫn phải được đọc lại vì phụ thuộc cách restore và namespace.

**Restore sang pod/container mới**: pod UID và container ID mới có thể khác. Ảnh có thể chứa environment, đường dẫn và trạng thái hệ thống của môi trường tạo checkpoint. Khả năng di chuyển ảnh phụ thuộc CRIU, kernel, namespace, mount và runtime; không mặc định ảnh có thể chuyển tùy ý sang pod khác.

Nếu nền tảng hỗ trợ restore sang một replica mới, ứng dụng cần lấy identity mới từ nền tảng sau restore và cập nhật service discovery. Không lấy Pod UID cũ từ một field trong heap làm ID của pod mới.

## 7. Host ID và machine ID

Trên một số Linux, /etc/machine-id cung cấp một định danh hệ thống. Đây không phải một API Java portable và không nên được coi là định danh ứng dụng.

Trong môi trường container:

- File có thể không tồn tại hoặc được mount từ host.
- Nhiều container có thể nhìn thấy cùng machine ID.
- Image/container có thể được cấu hình khác nhau.
- Giá trị có thể nhạy cảm về quyền riêng tư và thông tin hạ tầng.

Không dùng machine ID làm public instance ID, không gửi nó cho client và không đưa nó vào telemetry bên ngoài nếu chưa có lý do cùng chính sách phù hợp. Nếu cần node identity, dùng định danh node được nền tảng cấp và chỉ công bố trong phạm vi cần thiết.

## 8. RuntimeMXBean và các API nhận diện JVM

Có thể lấy tên runtime qua:

~~~java
import java.lang.management.ManagementFactory;

String runtimeName =
        ManagementFactory.getRuntimeMXBean().getName();
~~~

Một số JVM trả về chuỗi có dạng pid@hostname. Tuy nhiên, định dạng này là chi tiết triển khai, không phải định dạng chuẩn để ứng dụng phân tích. Không nên tách chuỗi theo ký tự @ rồi dùng hai phần làm identity chính thức.

Các điểm cần nhớ:

- RuntimeMXBean.getName() là tên runtime do JVM cung cấp; không bảo đảm format giống nhau ở mọi implementation.
- Giá trị có thể phản ánh thông tin được tạo khi runtime khởi động và không phải API refresh identity sau CRaC restore.
- RuntimeMXBean.getStartTime() và getUptime() mô tả thời gian theo runtime; không dùng chúng thay cho một restore attempt ID.
- ProcessHandle.current().pid() phù hợp hơn để đọc PID hiện tại.
- Hostname nên được lấy qua provider riêng theo môi trường nếu cần refresh.

Ví dụ ghi thông tin chẩn đoán:

~~~java
import java.lang.management.ManagementFactory;

public final class RuntimeDiagnostics {

    private RuntimeDiagnostics() {
    }

    public static void print() {
        long pid = ProcessHandle.current().pid();
        String runtimeName =
                ManagementFactory.getRuntimeMXBean().getName();

        System.out.println("pid=" + pid);
        System.out.println("runtimeName=" + runtimeName);
    }
}
~~~

Hãy xem runtimeName như một trường log hỗ trợ điều tra. Không dùng nó làm khóa database, cache key hoặc tên tài nguyên cần tồn tại qua nhiều lần restore.

## 9. Định danh nào nên được giữ và định danh nào cần tạo mới?

Một quy tắc thực tế là phân loại theo vòng đời:

| Dữ liệu | Giữ qua restore? | Cách xử lý |
|---|---|---|
| Service ID | Có | Đọc từ cấu hình triển khai ổn định |
| Logical replica ID | Tùy chính sách nền tảng | Giữ nếu cùng replica; refresh nếu restore vào replica mới |
| Process incarnation ID | Không | Tạo UUID mới trong afterRestore() |
| PID | Không | Đọc bằng ProcessHandle.current().pid() |
| Hostname | Không mặc định | Refresh qua provider nếu cần |
| Container ID / Pod UID | Tùy môi trường | Lấy từ nền tảng; không suy ra từ PID hoặc hostname |
| Checkpoint ID | Có | Giữ để truy vết ảnh đã tạo |
| Restore attempt ID | Không | Tạo ID mới cho mỗi lần restore |
| Request ID | Theo request | Tạo hoặc truyền theo request, không dùng làm process identity |
| Idempotency key | Theo nghiệp vụ | Giữ theo giao dịch; không tạo lại chỉ vì process restore |

### Checkpoint ID và incarnation ID khác nhau

Checkpoint ID nhận diện ảnh đã tạo. Nếu cùng một ảnh được restore nhiều lần, checkpoint ID có thể giống nhau.

Incarnation ID nhận diện một lần chạy cụ thể. Mỗi lần restore từ cùng ảnh nên tạo incarnation ID mới. Khi log hai lần restore, cặp checkpointId + incarnationId giúp biết cả nguồn ảnh và lần chạy hiện tại.

Restore attempt ID có thể được tạo bởi orchestrator hoặc ứng dụng. Nếu ứng dụng cần theo dõi các lần thử restore thất bại trước khi process chạy được, ID do orchestrator cấp thường phù hợp hơn vì callback có thể chưa được gọi khi restore thất bại rất sớm.

## 10. Sử dụng identity trong log và tracing

Định danh nên được gắn vào log theo cấu trúc để liên kết các sự kiện:

~~~text
service=orders-api
replica=orders-api-2
incarnation=9d2a...
pid=4217
host=node-a
checkpoint=release-2026-11-13-01
phase=afterRestore
event=database_ready
~~~

Trong hệ thống log có structured logging, mỗi trường nên là một thuộc tính riêng, không ghép thành một chuỗi khó truy vấn.

Một số lưu ý:

- PID và hostname hỗ trợ chẩn đoán, nhưng không thay thế incarnation ID.
- Incarnation ID giúp nhóm log của một lần chạy.
- Replica ID giúp theo dõi một bản sao logic qua nhiều incarnation.
- Checkpoint ID giúp liên hệ sự cố với artifact đã tạo trạng thái.
- Request ID và trace ID phải tiếp tục được truyền theo giao thức tracing, không thay bằng process identity.

Không đưa PID, hostname hoặc incarnation ID vào metric label có cardinality cao nếu hệ thống metric không được thiết kế cho điều đó. Với Prometheus hoặc hệ thống tương tự, mỗi incarnation mới có thể tạo thêm time series; cần giới hạn thời gian lưu, dùng metric phù hợp hoặc chỉ giữ identity chi tiết trong log/tracing.

## 11. Sử dụng identity trong cache, lock và service discovery

### Cache key

Không dùng PID hoặc hostname làm cache key cho dữ liệu nghiệp vụ cần tồn tại qua restore. PID có thể thay đổi hoặc được tái sử dụng; hostname có thể được chia sẻ. Nếu cache là local theo process, có thể dùng incarnation ID để tách dữ liệu chỉ hợp lệ trong một lần chạy.

Nếu cache lưu dữ liệu cần giữ qua restore, key phải dựa trên định danh nghiệp vụ hoặc service/tenant phù hợp, không phụ thuộc process identity.

### Distributed lock và lease

Không dùng PID đơn lẻ làm owner ID cho distributed lock. Một PID có thể được tái sử dụng và không phân biệt được hai lần chạy. Dùng owner token ngẫu nhiên hoặc incarnation ID, kèm lease có thời hạn và cơ chế fencing token nếu hệ thống yêu cầu chống stale owner.

Sau restore, không giả định lease đã được cấp trước checkpoint vẫn còn hiệu lực. Hãy kiểm tra hoặc lấy lease mới. Một tiến trình có thể khôi phục heap trong khi lease bên ngoài đã hết hạn và được cấp cho tiến trình khác.

### Service discovery

Service discovery thường cần địa chỉ có thể truy cập, port, health status và replica identity. Sau restore:

1. Đọc địa chỉ/cổng listener hiện tại.
2. Xác minh listener đang hoạt động.
3. Lấy replica identity phù hợp với nền tảng.
4. Đăng ký hoặc làm mới endpoint trong service discovery.
5. Chỉ đưa endpoint vào trạng thái healthy sau khi readiness thành công.

Không công bố hostname cũ hoặc IP cũ chỉ vì chúng còn nằm trong một object được restore.

## 12. Cẩn trọng với static field, singleton và cache identity

Một số cách viết dễ tạo dữ liệu stale:

~~~java
public final class NodeMetadata {
    public static final long PID =
            ProcessHandle.current().pid();
    public static final String HOST =
            HostInfo.currentHostName();
    public static final String INSTANCE_ID =
            java.util.UUID.randomUUID().toString();
}
~~~

Sau checkpoint, các giá trị trên có thể được khôi phục nguyên trạng. Nếu cần metadata hiện tại, dùng provider có thể refresh:

~~~java
public interface RuntimeIdentityProvider {
    RuntimeIdentityResource.IdentitySnapshot current();
}
~~~

Các service nên truy cập provider khi cần thông tin runtime thay vì sao chép PID hoặc hostname vào field riêng. Nếu phải lưu snapshot trong log hoặc event, hãy ghi rõ thời điểm quan sát và incarnation ID đi kèm.

Không phải mọi static field đều cần refresh. Hằng số như service name, protocol version hoặc tên module có thể ổn định. Điều cần tránh là cache một giá trị phụ thuộc process/host rồi dùng nó như dữ liệu hiện hành sau restore.

## 13. Kiểm thử identity sau restore

Một kiểm thử hữu ích nên so sánh snapshot trước checkpoint với snapshot sau restore.

### Kịch bản cơ bản

1. Khởi động ứng dụng mới.
2. Ghi service ID, replica ID, incarnation ID, PID và hostname.
3. Tạo checkpoint.
4. Restore ảnh trên môi trường mục tiêu.
5. Trong afterRestore(), tạo snapshot mới.
6. Xác nhận incarnation ID mới khác ID trước checkpoint.
7. Xác nhận PID được đọc lại từ ProcessHandle.current().
8. Xác minh replica ID theo chính sách môi trường: giữ nguyên nếu cùng replica, đổi nếu restore sang replica mới.
9. Xác minh hostname phản ánh môi trường hiện tại hoặc được ghi nhận là unknown nếu không phân giải được.
10. Kiểm tra log, tracing và service discovery dùng snapshot mới.

Không đặt kỳ vọng PID bắt buộc phải khác hoặc bắt buộc phải giống. Kết quả phụ thuộc cách restore và namespace. Kiểm tra điều quan trọng là ứng dụng đọc PID hiện tại thay vì tin vào giá trị lưu trong heap.

### Các trường hợp bổ sung

| Tình huống | Điều cần xác minh |
|---|---|
| Restore trong cùng container | Replica/host metadata có thể giữ nguyên; incarnation ID phải mới |
| Restore trong pod mới | Pod UID/replica identity được lấy từ môi trường đích |
| PID namespace | PID trong container được phân biệt với PID trên host |
| Hostname không phân giải được | Ứng dụng vẫn phục hồi nếu hostname chỉ là metadata chẩn đoán |
| Provider replica ID không truy cập được | Giữ readiness false nếu ID bắt buộc cho định tuyến |
| Restore nhiều lần từ cùng ảnh | Mỗi lần có incarnation ID mới, checkpoint ID có thể giữ nguyên |
| Log sau restore | Không dùng PID/hostname đã cache trước checkpoint |
| Distributed lock | Lease cũ được xác minh hoặc cấp mới; owner token không bị tái sử dụng |

Kiểm thử phải chạy qua checkpoint/restore thực tế. Gọi trực tiếp một method tạo UUID mới chỉ kiểm tra code Java, không chứng minh CRaC đã khôi phục resource và gọi callback đúng lifecycle.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| PID là định danh duy nhất của ứng dụng. | PID chỉ nhận diện tiến trình trong một phạm vi namespace và có thể được tái sử dụng. |
| PID sau restore chắc chắn giữ nguyên. | PID phụ thuộc runtime, CRIU và namespace; phải đọc lại. |
| Hostname luôn duy nhất. | Nhiều process có thể dùng chung hostname; hostname có thể đổi hoặc không phân giải được. |
| RuntimeMXBean.getName() luôn có dạng pid@hostname. | Định dạng là chi tiết triển khai, không nên parse để làm identity. |
| UUID tạo trước checkpoint là ID của process sau restore. | UUID đó được giữ trong heap; cần tạo incarnation ID mới trong afterRestore(). |
| Pod name chính là Pod UID. | Tên pod và UID là hai giá trị khác nhau; pod mới có UID mới. |
| System.getenv() tự cập nhật sau restore. | Environment của tiến trình không tự đọc lại giá trị mới từ orchestrator. |
| Hostname có thể dùng làm distributed lock owner. | Dùng owner token/incarnation ID và lease/fencing phù hợp. |
| Checkpoint ID và restore ID giống nhau. | Checkpoint ID nhận diện ảnh; restore/incarnation ID nhận diện lần chạy được tạo từ ảnh. |

## 15. Checklist triển khai

### Phân loại identity

- [ ] Service ID ổn định và không phụ thuộc PID.
- [ ] Replica ID có nguồn cấp rõ ràng từ cấu hình hoặc orchestrator.
- [ ] Process incarnation ID được tạo mới cho mỗi lần khởi động/restore.
- [ ] PID được đọc bằng ProcessHandle.current().pid() khi cần.
- [ ] Hostname chỉ dùng làm metadata chẩn đoán, không làm khóa duy nhất.
- [ ] Checkpoint ID và restore attempt ID được phân biệt.

### CRaC lifecycle

- [ ] Identity provider được đăng ký làm Resource trước checkpoint.
- [ ] afterRestore() tạo snapshot runtime mới.
- [ ] Không giữ PID/hostname trong static final như dữ liệu hiện hành.
- [ ] Không đăng ký Resource lặp lại trong afterRestore().
- [ ] Identity bắt buộc được xác minh trước khi mở readiness.

### Nền tảng và vận hành

- [ ] Phân biệt PID trong container với PID trên host.
- [ ] Phân biệt container ID, pod name, pod UID và node name.
- [ ] Không giả định environment variable được refresh tự động.
- [ ] Service discovery dùng địa chỉ và replica identity hiện tại.
- [ ] Distributed lock không dựa trên PID hoặc hostname đơn lẻ.
- [ ] Log có service, replica, incarnation và checkpoint ID phù hợp.
- [ ] Metric không tạo cardinality cao không cần thiết.
- [ ] Đã kiểm thử restore trong cùng container và môi trường đích dự kiến.

Trong CRaC, bộ nhớ được khôi phục từ ảnh có thể chứa những định danh được tạo trước checkpoint. PID và hostname cần được xem là thông tin runtime có thể thay đổi; replica ID phải tuân theo chính sách của nền tảng; process incarnation ID cần được tạo mới trong afterRestore(). Khi tách các vòng đời này, ứng dụng có thể ghi log chính xác, quản lý lock an toàn và đăng ký đúng endpoint sau restore.
