# Tạo lại định danh, tài nguyên và thông tin xác thực riêng từng bản sao

CRaC cho phép tạo checkpoint của một tiến trình Java đã được khởi tạo rồi khôi phục tiến trình đó để giảm thời gian khởi động. Trong môi trường triển khai có nhiều replica, cùng một ảnh checkpoint có thể được dùng để tạo nhiều bản sao ứng dụng. Đây là cách hiệu quả để nhân bản phần khởi tạo dùng chung, nhưng cũng tạo ra một vấn đề quan trọng: mọi bản sao bắt đầu từ cùng một trạng thái trong heap.

Nếu ảnh checkpoint chứa một instance ID, hostname, consumer ID, số thứ tự cục bộ, trạng thái leader, session, khóa riêng hoặc token đã được tạo trước checkpoint, những giá trị đó có thể xuất hiện giống nhau ở nhiều replica. Một số giá trị giống nhau là chủ đích, ví dụ tên dịch vụ hoặc consumer group. Những giá trị khác phải riêng cho từng bản sao, ví dụ danh tính của một tiến trình, khóa phiên, file tạm, socket, lease hoặc credential có phạm vi instance.

Vì vậy, ứng dụng cần phân biệt ba loại dữ liệu:

1. **Cấu hình và trạng thái có thể chia sẻ:** tên dịch vụ, cấu hình giao thức, schema, metadata bất biến hoặc dữ liệu khởi tạo có thể dùng chung.
2. **Định danh và tài nguyên riêng từng bản sao:** instance ID, member ID, thư mục tạm, socket, connection pool, worker, lease và trạng thái cục bộ.
3. **Thông tin xác thực có vòng đời riêng:** token ngắn hạn, chứng chỉ, private key, session và credential cần lấy mới hoặc xác minh lại sau restore.

Mỗi replica cần hoàn tất bước khởi tạo riêng của mình trước khi nhận lưu lượng hoặc xử lý công việc. CRaC giữ lại phần trạng thái khởi tạo có thể tái sử dụng; callback sau restore phải làm mới những giá trị phụ thuộc vào danh tính và môi trường của replica hiện tại.

## 1. Vì sao nhiều replica từ cùng checkpoint có thể xung đột?

Giả sử ứng dụng khởi động một lần, tạo đối tượng định danh, mở một consumer, lấy lease và lưu tất cả các đối tượng đó trong heap. Sau đó ứng dụng được checkpoint. Khi hệ thống tạo ba replica từ cùng ảnh, mỗi tiến trình mới có thể bắt đầu với một bản sao của các đối tượng Java đã tồn tại tại thời điểm checkpoint.

Ví dụ, heap tại thời điểm checkpoint có thể chứa:

~~~java
static final String INSTANCE_ID = UUID.randomUUID().toString();
static final String CONSUMER_MEMBER_ID = "worker-17";
static volatile boolean leader = true;
static long localSequence = 10_500;
~~~

Nếu các trường này được giữ nguyên khi restore từ cùng checkpoint, nhiều replica có thể cùng nhận diện mình là worker-17, cùng tin rằng mình đang là leader và cùng tiếp tục từ một sequence number. Khi các bản sao hoạt động đồng thời, hệ thống có thể gặp:

- Trùng instance ID trong service registry, log, metrics hoặc trace.
- Nhiều consumer sử dụng cùng member ID và gây xung đột khi tham gia group.
- Nhiều replica cùng tin mình giữ distributed lock hoặc quyền leader.
- Trùng tên file tạm, socket path, PID file hoặc thư mục làm việc.
- Dùng chung token hoặc private key đã được lưu trong heap.
- Sinh ID nghiệp vụ trùng nếu bộ sinh số ngẫu nhiên hoặc bộ đếm được sao chép mà không có cơ chế bảo đảm duy nhất.
- Ghi đè trạng thái của nhau khi cùng cập nhật một tài nguyên bên ngoài.

Checkpoint không biết giá trị nào có ý nghĩa toàn dịch vụ, giá trị nào có ý nghĩa riêng từng tiến trình. Việc phân loại phải được thực hiện trong thiết kế ứng dụng.

### 1.1. Trạng thái nào được giữ lại?

Một ảnh checkpoint có thể giữ trạng thái Java như:

- Trường static và instance.
- Singleton, cache, cấu hình đã nạp và đối tượng đã khởi tạo.
- Đối tượng client, session, token hoặc credential còn được tham chiếu.
- Bộ đếm, seed của bộ sinh số ngẫu nhiên và trạng thái scheduler trong heap.
- Tham chiếu tới tài nguyên hệ điều hành hoặc native tùy khả năng hỗ trợ của runtime và nền tảng.

Khi nhiều tiến trình restore từ cùng ảnh, mỗi tiến trình có không gian bộ nhớ riêng, nhưng giá trị ban đầu của các trường được sao chép từ cùng một snapshot. Việc các bản sao không chia sẻ cùng một địa chỉ bộ nhớ không làm cho các giá trị định danh bên trong tự trở nên khác nhau.

Một số tài nguyên bên ngoài có thể không được khôi phục hoặc có thể đã mất hiệu lực. Dù vậy, đối tượng Java đại diện cho tài nguyên vẫn có thể còn trong heap. Ứng dụng cần đóng, loại bỏ hoặc tái tạo tài nguyên theo API của thư viện và callback CRaC.

### 1.2. Không phải mọi giá trị đều phải khác nhau

Không nên tạo ID mới cho mọi thứ. Các replica có thể cần dùng chung:

- Tên dịch vụ logic như orders-api.
- Consumer group mà tất cả replica cùng tham gia.
- Tên topic hoặc queue.
- Schema, phiên bản giao thức và cấu hình nghiệp vụ bất biến.
- CA gốc hoặc chính sách trust chung của dịch vụ.
- Cấu hình feature flag nếu nguồn cấu hình quy định như vậy.

Trong khi đó, những giá trị sau thường phải khác nhau hoặc được cấp lại cho từng replica:

- Instance ID hoặc process incarnation ID.
- Consumer member ID nếu broker yêu cầu mỗi thành viên có danh tính riêng.
- Hostname, pod UID hoặc địa chỉ endpoint của bản sao.
- Tên socket, thư mục tạm, file lock và tài nguyên cục bộ.
- Lease token, fencing token hoặc quyền leader.
- Credential có phạm vi instance, session hoặc connection.
- Trace/process metadata và metric label nhận diện instance.

Điểm cần xác định là phạm vi sở hữu và phạm vi duy nhất của từng giá trị, không phải chỉ tên gọi của nó.

## 2. Phân biệt định danh dịch vụ, định danh replica và định danh nghiệp vụ

Một hệ thống phân tán thường có nhiều loại ID cùng tồn tại. Dùng một ID cho mọi mục đích dễ dẫn tới việc nhân bản nhầm hoặc tạo ra các ID không ổn định.

| Loại định danh | Phạm vi | Ví dụ | Cách xử lý khi restore |
|---|---|---|---|
| Service identity | Đại diện cho một dịch vụ logic | orders-api, billing-worker | Thường giữ nguyên theo cấu hình |
| Workload identity | Đại diện cho workload được cấp quyền | Service account, SPIFFE ID | Xác minh hoặc lấy lại theo nền tảng |
| Replica/instance identity | Một bản sao hoặc một lần chạy tiến trình | Pod UID, instance UUID | Lấy mới hoặc truy vấn metadata của replica hiện tại |
| Process incarnation ID | Một lần khởi động/restore cụ thể | UUID tạo sau restore | Tạo mới cho mỗi lần restore nếu cần phân biệt incarnation |
| Consumer member ID | Một thành viên trong consumer group | Member ID do broker cấp hoặc client tạo | Đăng ký lại và nhận member ID riêng |
| Business entity ID | Một đối tượng nghiệp vụ | Order ID, payment ID, account ID | Đọc hoặc tạo từ nguồn dữ liệu có thẩm quyền; không reset theo replica |
| Operation/idempotency ID | Một yêu cầu nghiệp vụ có thể retry | Idempotency key | Giữ ổn định qua retry của cùng thao tác |
| Fencing token | Thứ tự quyền sở hữu tài nguyên | Generation number tăng dần | Xin token mới từ coordinator hoặc storage |

Ví dụ, orders-api có thể là service identity chung cho tất cả replica. Mỗi pod có pod UID riêng. Mỗi lần tiến trình restore trong pod có thể tạo một process incarnation ID mới. Khi một request tạo đơn hàng, order ID phải được cấp theo cơ chế nghiệp vụ bền vững; không được tạo từ instance ID hoặc bộ đếm được snapshot.

### 2.1. Service identity ổn định

Service identity thường được dùng trong cấu hình, routing, authorization policy hoặc tên dịch vụ. Giá trị này có thể được chia sẻ giữa các replica vì nó đại diện cho cùng một dịch vụ logic.

Không dùng service identity chung làm instance ID. Nếu log hoặc metric chỉ ghi orders-api, vận hành sẽ khó xác định bản sao nào gây ra lỗi. Hãy gắn service identity cùng replica ID và process incarnation ID khi cần chẩn đoán.

### 2.2. Replica identity

Replica identity phân biệt các bản sao đang chạy đồng thời. Nguồn cấp ID có thể là:

- Metadata do nền tảng điều phối cung cấp, ví dụ UID của pod hoặc task.
- Một UUID được tạo bằng bộ sinh số ngẫu nhiên an toàn khi tiến trình restore.
- Một ID do coordinator cấp và đăng ký với service registry.
- Một định danh kết hợp workload identity với thông tin incarnation do hệ thống quản lý.

Nếu dùng metadata của nền tảng, hãy truy vấn metadata của replica đang chạy sau restore. Không dựa vào hostname hoặc pod name đã được ghi vào heap trước checkpoint nếu ảnh có thể được chuyển sang replica khác.

### 2.3. Process incarnation ID

Một replica có thể trải qua nhiều lần restore hoặc restart. Khi cần phân biệt từng lần tiến trình được tạo, hãy dùng process incarnation ID. Giá trị này được tạo mới khi tiến trình bước vào một incarnation mới.

Incarnation ID hữu ích cho:

- Log và distributed tracing.
- Metrics theo tiến trình.
- Correlation của sự kiện khởi động.
- Phát hiện message hoặc heartbeat đến từ tiến trình cũ.
- Chẩn đoán trường hợp một replica cũ và mới cùng tồn tại tạm thời.

Không dùng incarnation ID làm ID nghiệp vụ cần ổn định qua retry. Một request được gửi lại sau restore vẫn phải giữ idempotency key ban đầu.

## 3. Tạo ID riêng cho từng replica

### 3.1. Tạo mới sau restore

Nếu ứng dụng cần một ID ngẫu nhiên riêng cho mỗi incarnation, hãy tạo ID trong giai đoạn phục hồi sau restore, hoặc tại bootstrap của một tiến trình mới trước khi nó được phép phục vụ.

Ví dụ đơn giản:

~~~java
import java.util.UUID;

public final class InstanceIdentity {
    private volatile String instanceId;

    public void initializeForCurrentProcess() {
        instanceId = UUID.randomUUID().toString();
    }

    public String getInstanceId() {
        String current = instanceId;
        if (current == null) {
            throw new IllegalStateException(
                    "Instance identity is not initialized");
        }
        return current;
    }
}
~~~

Không khởi tạo ID duy nhất một lần rồi đóng băng nó trong checkpoint nếu ảnh có thể được restore thành nhiều replica. Mỗi bản sao phải chạy initializeForCurrentProcess() trong lifecycle của chính nó.

UUID v4 cung cấp xác suất va chạm rất thấp khi được tạo bằng implementation phù hợp. Tuy nhiên, nếu hệ thống yêu cầu duy nhất tuyệt đối, có thứ tự hoặc phải được xác nhận bởi coordinator, hãy dùng cơ chế cấp ID có thẩm quyền như database sequence, registry hoặc service cấp ID. UUID không thay thế constraint duy nhất ở database.

### 3.2. Dùng metadata của nền tảng

Trong Kubernetes, pod name và pod UID có phạm vi khác nhau. Pod name có thể được tái sử dụng sau khi pod bị xóa; UID phân biệt một đối tượng pod cụ thể. Nếu cần danh tính replica, hãy dùng metadata được nền tảng cấp và truy vấn từ môi trường của replica đang chạy.

Các nền tảng khác có thể cung cấp task ARN, machine ID, container ID hoặc workload identity. Cần xác định:

- Giá trị đó ổn định trong suốt vòng đời replica hay thay đổi khi container được tạo lại?
- Giá trị có được cấp riêng cho mỗi bản sao hay chỉ là tên dịch vụ?
- Metadata endpoint có thể truy cập sau restore không?
- Giá trị có được cập nhật khi replica được di chuyển sang node khác không?
- Có thể dùng nó trong log/metric mà không làm lộ thông tin nhạy cảm không?

Nếu metadata không thể được truy vấn trong callback ngay lập tức, hãy thực hiện bootstrap bất đồng bộ có readiness rõ ràng. Không sử dụng giá trị cũ như thể đã xác minh được danh tính hiện tại.

### 3.3. Không dựa vào bộ đếm trong heap để cấp ID toàn cục

Một biến long trong heap có thể được snapshot cùng checkpoint. Khi nhiều replica restore, chúng có thể tiếp tục từ cùng giá trị và cấp ra các ID trùng nhau.

Ví dụ rủi ro:

~~~java
private static long nextId = 1000;

public static synchronized long allocateId() {
    return ++nextId;
}
~~~

Đồng bộ synchronized chỉ có hiệu lực trong một JVM. Nó không phối hợp các replica khác nhau. Nếu mỗi replica bắt đầu từ nextId = 1000, cả hai có thể cấp ra 1001.

Với ID nghiệp vụ, hãy dùng:

- Database sequence hoặc identity column.
- UUID hoặc ULID được tạo bằng implementation phù hợp.
- Dịch vụ cấp ID phân tán.
- Phân vùng dải ID theo một lease hoặc allocation record bền vững.
- Constraint unique tại nơi lưu trữ để phát hiện va chạm.

Không dùng một bộ đếm cục bộ được snapshot làm nguồn duy nhất cho ID toàn cục.

### 3.4. Làm mới bộ sinh số ngẫu nhiên

Checkpoint có thể giữ trạng thái của các đối tượng sinh số ngẫu nhiên trong heap. Nếu một PRNG thông thường có trạng thái nội bộ được sao chép, các replica có thể sinh ra cùng chuỗi giá trị sau restore. Với dữ liệu bảo mật, không được dùng bộ sinh giả ngẫu nhiên tự cài đặt hoặc seed cố định.

Đối với giá trị dùng trong bảo mật, dùng SecureRandom và provider được hỗ trợ trên JDK/nền tảng đang triển khai. Kiểm tra tài liệu CRaC của JDK và provider về cách xử lý trạng thái entropy khi checkpoint/restore. Nếu ứng dụng tự giữ một generator hoặc seed trong heap, hãy có cơ chế tái tạo hoặc reseed sau restore theo hướng dẫn của provider.

Không nên chỉ gọi setSeed() với thời gian hiện tại để tạo tính duy nhất. Timestamp có thể giống nhau giữa các replica và không phải nguồn entropy bảo mật. Nếu yêu cầu duy nhất cao, kết hợp random ID với cơ chế đăng ký hoặc constraint ở hệ thống có thẩm quyền.

## 4. Tạo lại tài nguyên cục bộ cho từng bản sao

Tài nguyên cục bộ là những đối tượng hoặc tài nguyên hệ điều hành chỉ thuộc về một tiến trình, container hoặc replica. Nếu chúng được giữ nguyên từ checkpoint, nhiều replica có thể tranh chấp cùng một tên hoặc sử dụng một trạng thái không còn hợp lệ.

### 4.1. Thư mục tạm và tệp cục bộ

Ứng dụng có thể tạo thư mục tạm theo instance ID:

~~~java
Path workDirectory = Path.of(
        System.getProperty("java.io.tmpdir"),
        "orders",
        instanceId
);
Files.createDirectories(workDirectory);
~~~

Sau restore, tạo hoặc xác minh lại thư mục của replica hiện tại. Không dùng một đường dẫn cố định được lưu trong checkpoint nếu các replica cùng mount một volume và cùng ghi vào đó.

Tệp lock, PID file, Unix domain socket path, file spool và cache cục bộ cũng cần được phân loại. Nếu chúng là tài nguyên riêng tiến trình, hãy tạo tên riêng hoặc mở lại theo quy tắc ownership sau restore. Tránh xóa tệp của replica khác chỉ vì tên tệp giống giá trị cũ trong checkpoint.

### 4.2. Socket và cổng mạng

Không giữ giả định rằng socket đã mở trước checkpoint còn hợp lệ sau restore. Đóng socket cũ trước checkpoint theo API của thư viện. Sau restore, bind hoặc connect lại để hệ điều hành cấp trạng thái mạng mới.

Nếu ứng dụng cần lắng nghe trên cổng động, hãy bind port 0 và đọc cổng thực tế sau khi bind. Nếu cần cổng cố định, nền tảng điều phối phải bảo đảm mỗi replica có endpoint riêng hoặc có một proxy/load balancer đứng trước. Không sao chép một local port hoặc socket descriptor từ ảnh checkpoint sang nhiều replica.

### 4.3. Connection pool và client

HTTP client, JDBC pool, broker client và SDK có thể giữ connection, thread, executor, DNS cache hoặc session. Mỗi replica cần tạo client/pool thuộc sở hữu của nó sau restore. Không chia sẻ một pool hoặc một đối tượng client bằng cách sao chép trạng thái heap rồi giả định các kết nối đó là độc lập.

Trước checkpoint:

- Ngừng nhận request hoặc message mới qua client.
- Drain thao tác đang chạy.
- Hoàn tất hoặc rollback transaction.
- Đóng pool/client theo API chính thức.

Sau restore:

- Tạo pool/client mới.
- Nạp cấu hình endpoint hiện hành.
- Tạo kết nối mới và xác thực.
- Kiểm tra health/readiness trước khi nhận việc.

### 4.4. Consumer và scheduler

Consumer group thường là một danh tính logic dùng chung giữa các replica, còn member ID là danh tính riêng của từng thành viên. Sau restore, hãy tham gia lại group để broker cấp hoặc xác nhận member identity mới. Không tiếp tục dùng member ID đã snapshot nếu broker yêu cầu mỗi thành viên có ID riêng.

Tương tự, scheduler có thể giữ trạng thái lần chạy kế tiếp trong heap. Nhiều replica restore từ cùng snapshot có thể cùng chạy một tác vụ. Với tác vụ phân tán, hãy dùng distributed scheduler, lock có fencing token hoặc cơ chế claim task bền vững. Nếu tác vụ có thể chạy lặp, thiết kế idempotent.

## 5. Quyền sở hữu phân tán: lease, lock và leader

Một trong những rủi ro nghiêm trọng nhất là nhân bản trạng thái quyền sở hữu. Ví dụ, tại thời điểm checkpoint, tiến trình đang giữ distributed lock và trường leader = true. Khi hai replica restore, cả hai bản sao của trường này đều có thể là true.

Trạng thái trong heap không phải bằng chứng rằng hệ thống bên ngoài vẫn công nhận quyền sở hữu. Lease có thể đã hết hạn trong thời gian tiến trình dừng và được cấp cho replica khác. Một leader cũ được restore có thể cùng hoạt động với leader mới.

### 5.1. Không khôi phục quyền leader từ boolean

Không sử dụng biến boolean được checkpoint để kết luận một replica là leader. Sau restore, hãy đăng ký lại với coordinator hoặc hệ thống election và chờ kết quả xác nhận.

Ví dụ, thay vì:

~~~java
if (wasLeaderBeforeCheckpoint) {
    startLeaderTasks();
}
~~~

hãy thực hiện:

~~~java
LeadershipLease lease = coordinator.acquireLeadership(instanceId);
if (lease.isGranted()) {
    startLeaderTasks(lease.fencingToken());
}
~~~

Đoạn mã thứ hai minh họa ý tưởng. API coordinator cụ thể phụ thuộc hệ thống phân tán đang sử dụng. Việc acquire phải xác minh quyền sở hữu hiện tại và trả về token/generation mới nếu hệ thống hỗ trợ.

### 5.2. Lease và fencing token

Lease là quyền sở hữu có thời hạn. Nếu tiến trình dừng và không gia hạn lease, quyền có thể hết hạn. Sau restore, tiến trình phải xin lease mới.

Fencing token là số thứ tự hoặc generation do coordinator cấp, tăng dần qua mỗi lần cấp quyền. Hệ thống lưu trữ kiểm tra token trước khi chấp nhận thao tác ghi. Khi replica cũ tỉnh lại với token cũ, storage từ chối thao tác vì token đó thấp hơn token hiện hành.

Đây là lớp bảo vệ quan trọng vì chỉ giải phóng lock trong callback không đủ nếu tiến trình bị kill đột ngột hoặc mạng phân vùng. Fencing cần được kiểm tra tại nơi thực hiện side effect, không chỉ ở biến trong heap.

### 5.3. Consumer group và message processing

Khi nhiều replica restore cùng lúc, chúng có thể đồng thời tham gia một consumer group. Điều này có thể là hành vi mong muốn nếu broker phân phối partition cho các thành viên mới. Tuy nhiên, mỗi member cần được nhận diện riêng và việc xử lý message phải có cơ chế chống trùng.

Hãy:

- Dừng consumer và hoàn tất hoặc trả lại message đang giữ trước checkpoint.
- Chỉ acknowledgment sau khi kết quả nghiệp vụ đã bền vững.
- Tham gia lại group sau restore và nhận member assignment mới.
- Không dùng consumer member ID được snapshot làm ID cố định cho mọi replica.
- Dùng message ID, idempotency key hoặc inbox table để chống xử lý lặp.
- Để broker quản lý offset và group membership theo giao thức chính thức.

### 5.4. Sequence và counter phân tán

Nếu một replica có bộ đếm local để cấp sequence, cùng checkpoint có thể nhân bản giá trị đó sang nhiều replica. Cách an toàn là xin dải sequence riêng từ nguồn có thẩm quyền hoặc sử dụng sequence do database/broker quản lý. Nếu dùng dải ID được cấp trước, mỗi replica phải có allocation range không giao nhau và lưu ownership bền vững.

## 6. Thông tin xác thực cần cấp lại hoặc xác minh lại

Credential có thể được giữ trong heap: access token, refresh token, session cookie, API key, client certificate, private key, cloud credential hoặc thông tin xác thực database. Khi checkpoint được nhân bản, các bản sao có thể nhận cùng một bản sao credential.

Điều đó có thể tạo ra rủi ro:

- Token chỉ dành cho một session hoặc một client bị sử dụng đồng thời bởi nhiều replica.
- Token hết hạn trong lúc JVM dừng.
- Token bị thu hồi nhưng bản sao trong heap vẫn tồn tại.
- Credential gắn với một workload hoặc instance cụ thể được dùng từ replica khác.
- Nhiều replica cùng làm mới một refresh token có cơ chế rotation một lần, khiến các lần refresh cạnh tranh.
- Private key được sao chép tới nhiều instance, làm mở rộng phạm vi ảnh hưởng nếu một replica bị xâm nhập.

Không phải mọi credential đều cần khác nhau. Một workload identity có thể được chia sẻ theo chính sách của nền tảng, nhưng token và private key dùng để chứng minh identity cần có vòng đời và phạm vi phù hợp.

### 6.1. Workload identity và instance identity

Workload identity đại diện cho một workload được cấp quyền, ví dụ một service account hoặc một SPIFFE ID. Nhiều replica của cùng workload có thể được phép sử dụng cùng một danh tính logic.

Instance identity phân biệt từng replica cụ thể. Nó có thể được lấy từ pod UID, task identity hoặc một ID được tạo khi tiến trình restore.

Một thiết kế có thể dùng:

- Service identity chung để xác định quyền của ứng dụng.
- Replica identity riêng để ghi log, metrics và phân biệt member.
- Credential ngắn hạn được cấp dựa trên workload identity của replica hiện tại.
- Private key được tạo hoặc nạp riêng theo chính sách mTLS của từng replica.

Không nên dùng một static API key được đóng gói trong ảnh checkpoint như cách duy nhất để chứng minh danh tính của mọi replica.

### 6.2. Access token và refresh token

Access token thường có thời hạn ngắn. Refresh token có thể có rotation hoặc ràng buộc với client/session. Nếu token được snapshot, sau restore nó có thể hết hạn hoặc bị dịch vụ xác thực từ chối.

Sau restore:

1. Xác định danh tính workload hiện tại.
2. Lấy token mới từ identity provider hoặc secret/token service.
3. Kiểm tra audience, scope, issuer và thời hạn.
4. Cập nhật client dùng token mới.
5. Chỉ mở readiness khi xác thực với dịch vụ bắt buộc thành công.

Nếu refresh token chỉ được phép dùng một lần hoặc bị xoay vòng mỗi khi refresh, không để nhiều replica dùng cùng một bản sao refresh token. Mỗi replica cần có luồng cấp credential riêng hoặc một dịch vụ quản lý token có cơ chế concurrency phù hợp.

### 6.3. Chứng chỉ và private key

Trong mTLS, client có thể cần chứng chỉ và private key. Nếu private key nằm trong heap hoặc file được đóng gói vào checkpoint, tất cả replica restore có thể có cùng key. Điều này có thể không phù hợp với chính sách yêu cầu key riêng cho mỗi instance.

Các lựa chọn:

- Tạo key pair riêng cho mỗi replica sau restore và xin chứng chỉ từ CA.
- Lấy key từ HSM hoặc secret manager theo identity hiện tại.
- Dùng workload certificate có thời hạn ngắn và cơ chế tự động rotation.
- Dùng một danh tính workload chung nếu chính sách cho phép, nhưng giới hạn quyền và thời gian sống của chứng chỉ.

Không ghi private key vào log hoặc đưa nó vào image nếu không cần thiết. Nếu buộc phải giữ secret trong checkpoint, phải bảo vệ ảnh như một bản sao chứa credential: mã hóa khi lưu trữ và truyền, giới hạn quyền truy cập, thời hạn lưu giữ và khả năng thu hồi.

### 6.4. Credential database và broker

Một JDBC pool hoặc broker client có thể giữ credential trong đối tượng cấu hình, session hoặc connection. Sau restore, không chỉ mở lại socket; hãy xác minh credential còn hợp lệ và tạo client/pool mới theo cấu hình hiện hành.

Nếu database password được rotate trong thời gian JVM dừng, pool mới phải lấy password mới. Nếu broker dùng OAuth hoặc mTLS, client cần lấy token/chứng chỉ mới và tham gia lại theo giao thức của broker.

### 6.5. Secret manager và metadata service

Trong cloud hoặc Kubernetes, credential thường được cấp qua workload identity, projected service account token, metadata service hoặc secret manager. Các nguồn này có thể cung cấp thông tin mới cho replica hiện tại sau restore.

Không nên mặc định một token được đọc từ file hoặc environment trước checkpoint vẫn là token hiện hành. Hãy kiểm tra:

- Token file có được rotate hoặc thay symlink không?
- Metadata endpoint có phản hồi trong môi trường restore không?
- Identity của replica có đúng workload hiện tại không?
- Secret manager có thể cấp credential riêng và có thời hạn không?
- Client có cần tạo lại sau khi secret thay đổi không?

Environment variable trong process thường là một phần trạng thái của tiến trình. Nếu nhiều replica được dựng từ cùng một ảnh process, không giả định giá trị env đã snapshot sẽ tự khác nhau. Khi cần thông tin riêng từng replica, lấy nó từ nguồn metadata/identity được nền tảng hỗ trợ sau restore.

## 7. Tạo mới tài nguyên và credential bằng CRaC Resource

Một resource quản lý bootstrap của replica có thể điều phối việc đóng tài nguyên cũ trước checkpoint và tạo lại trạng thái riêng sau restore.

Trình tự tổng quát:

### beforeCheckpoint()

1. Chuyển replica sang trạng thái quiescing.
2. Ngừng nhận request và công việc mới.
3. Drain worker, consumer và transaction.
4. Đóng connection pool, client, socket và tài nguyên cục bộ.
5. Giải phóng lease hoặc lock nếu giao thức yêu cầu.
6. Xóa hoặc đánh dấu không hợp lệ các tham chiếu tới session/credential không thể tiếp tục dùng an toàn.

### afterRestore()

1. Đọc metadata của replica hiện tại.
2. Tạo replica ID và process incarnation ID mới nếu cần.
3. Tạo thư mục, socket path, cache và tài nguyên cục bộ riêng.
4. Xác thực workload identity và lấy credential mới.
5. Tạo SSLContext, client, connection pool hoặc consumer mới.
6. Xin lại lease, lock hoặc member assignment.
7. Kiểm tra dependency và mở readiness.

Không nên khởi động worker hoặc nhận lưu lượng trước khi bước tạo identity và credential hoàn tất. Nếu một callback phục hồi thất bại, replica phải giữ trạng thái chưa sẵn sàng và có chính sách retry hữu hạn.

### 7.1. Ví dụ Resource điều phối bootstrap từng replica

Ví dụ sau minh họa một lớp quản lý các tài nguyên phụ thuộc vào danh tính replica. Các provider được trừu tượng hóa để ứng dụng có thể kết nối với Kubernetes metadata, cloud identity service, secret manager hoặc coordinator cụ thể.

~~~java
import java.util.UUID;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ReplicaBootstrapResource implements Resource {
    private final ReplicaMetadataProvider metadataProvider;
    private final CredentialProvider credentialProvider;
    private final ReplicaResourceFactory resourceFactory;

    private volatile ReplicaResources resources;
    private volatile ReplicaIdentity identity;

    public ReplicaBootstrapResource(
            ReplicaMetadataProvider metadataProvider,
            CredentialProvider credentialProvider,
            ReplicaResourceFactory resourceFactory) throws Exception {
        this.metadataProvider = metadataProvider;
        this.credentialProvider = credentialProvider;
        this.resourceFactory = resourceFactory;

        initializeForCurrentReplica();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        closeReplicaResources();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        initializeForCurrentReplica();
    }

    private void initializeForCurrentReplica() throws Exception {
        ReplicaMetadata metadata = metadataProvider.currentMetadata();

        String processIncarnationId = UUID.randomUUID().toString();
        ReplicaIdentity newIdentity = new ReplicaIdentity(
                metadata.serviceName(),
                metadata.replicaId(),
                processIncarnationId
        );

        ReplicaCredential credential =
                credentialProvider.obtainFor(newIdentity);

        ReplicaResources newResources =
                resourceFactory.create(newIdentity, credential);

        // Chỉ công bố identity/resources sau khi khởi tạo thành công.
        this.identity = newIdentity;
        this.resources = newResources;
    }

    private void closeReplicaResources() throws Exception {
        ReplicaResources current = resources;
        resources = null;
        identity = null;

        if (current != null) {
            current.close();
        }
    }

    public ReplicaIdentity identity() {
        ReplicaIdentity current = identity;
        if (current == null) {
            throw new IllegalStateException(
                    "Replica identity is not ready");
        }
        return current;
    }
}
~~~

Các kiểu ReplicaMetadataProvider, CredentialProvider, ReplicaResourceFactory, ReplicaMetadata, ReplicaIdentity, ReplicaCredential và ReplicaResources là interface/model do ứng dụng định nghĩa; chúng không phải lớp có sẵn trong JDK hoặc CRaC. Ví dụ tập trung vào thứ tự: lấy metadata hiện tại, tạo incarnation ID, lấy credential theo identity, tạo tài nguyên riêng, rồi mới công bố trạng thái sẵn sàng.

Trong ứng dụng thực tế, việc tạo tài nguyên có thể thất bại ở bất kỳ bước nào. Cần đóng một phần tài nguyên đã tạo nếu bước tiếp theo thất bại, không công bố identity khi credential chưa hợp lệ và không mở readiness cho tới khi các phụ thuộc bắt buộc đã sẵn sàng.

Nếu metadataProvider hoặc credentialProvider cũng có resource riêng cần callback, hãy thiết kế thứ tự đăng ký phù hợp. Provider nền tảng phải sẵn sàng trước ReplicaBootstrapResource. Nếu bootstrap resource phụ thuộc một client secret manager, client đó phải được tạo trước và phục hồi trước.

### 7.2. Ví dụ interface của các provider

Một hợp đồng đơn giản có thể như sau:

~~~java
public interface ReplicaMetadataProvider {
    ReplicaMetadata currentMetadata() throws Exception;
}

public interface CredentialProvider {
    ReplicaCredential obtainFor(ReplicaIdentity identity)
            throws Exception;
}

public interface ReplicaResourceFactory {
    ReplicaResources create(
            ReplicaIdentity identity,
            ReplicaCredential credential
    ) throws Exception;
}

public interface ReplicaResources extends AutoCloseable {
    @Override
    void close() throws Exception;
}
~~~

Ứng dụng có thể triển khai metadata provider bằng Kubernetes Downward API hoặc API metadata của nền tảng; credential provider có thể dùng workload identity để lấy token hoặc chứng chỉ ngắn hạn. Không hard-code một nhà cung cấp cụ thể vào lifecycle nếu ứng dụng cần chạy ở nhiều môi trường.

## 8. Thứ tự khởi tạo và readiness

Một replica không nên nhận traffic ngay khi JVM restore hoàn tất. Restore chỉ khôi phục tiến trình; nó không bảo đảm replica đã có identity, credential và tài nguyên riêng hợp lệ.

Một trình tự thường dùng:

1. Khởi tạo các cấu hình bất biến có thể chia sẻ.
2. Truy vấn metadata của replica hiện tại.
3. Tạo instance/incarnation identity.
4. Lấy credential mới và xác minh thời hạn, scope, audience.
5. Tạo tài nguyên cục bộ và client.
6. Tham gia service registry, broker group hoặc coordinator.
7. Xin lease/lock mới nếu cần.
8. Kiểm tra sức khỏe của các dependency.
9. Đánh dấu readiness và nhận traffic.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Restore JVM] --> B[Đọc metadata replica hiện tại]
    B --> C[Tạo replica/incarnation ID]
    C --> D[Lấy credential mới]
    D --> E[Tạo tài nguyên riêng]
    E --> F[Đăng ký với broker/registry/coordinator]
    F --> G[Xin lease và xác minh quyền sở hữu]
    G --> H[Health check]
    H --> I{Mọi dependency bắt buộc sẵn sàng?}
    I -->|Có| J[Readiness: nhận traffic]
    I -->|Không| K[Giữ chưa sẵn sàng và retry có giới hạn]
    K --> H
~~~

Readiness cần phản ánh khả năng phục vụ thực tế. Liveness chỉ cho biết tiến trình còn sống; nó không thay thế readiness. Nếu credential chưa được cấp hoặc replica chưa tham gia broker group, không nên cho load balancer gửi request nghiệp vụ tới replica.

Nếu một số thành phần có thể khởi tạo bất đồng bộ, hãy phân biệt dependency bắt buộc với dependency tùy chọn. Không để một dịch vụ tùy chọn làm toàn bộ ứng dụng không sẵn sàng nếu kiến trúc cho phép phục vụ các chức năng còn lại; nhưng cũng không đánh dấu sẵn sàng nếu một luồng nghiệp vụ quan trọng chưa thể hoạt động.

## 9. Xử lý lỗi và retry khi tạo identity/credential

Sau restore, các dịch vụ cấp metadata, credential hoặc lease có thể chưa sẵn sàng. Một số lỗi thường gặp:

| Tình huống | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Metadata trả về replica ID cũ | Ứng dụng dùng giá trị đã snapshot hoặc cache | Truy vấn nguồn metadata hiện tại sau restore |
| Hai replica có cùng instance ID | ID được tạo trước checkpoint và bị nhân bản | Tạo ID mới hoặc dùng ID do nền tảng cấp |
| Token hết hạn | Credential được snapshot từ trước | Lấy token mới và xác minh expiry/audience |
| Refresh token bị từ chối | Nhiều replica dùng chung refresh token đã rotation | Cấp credential riêng hoặc dùng token broker có concurrency control |
| Chứng chỉ client bị từ chối | Key/certificate cũ hoặc sai identity | Tạo/nạp key material mới và xin chứng chỉ theo identity hiện tại |
| Lease không được cấp | Replica khác đang sở hữu hoặc coordinator chưa sẵn sàng | Retry có backoff, không dùng lại trạng thái leader cũ |
| Consumer bị từ chối member ID | Member ID trùng giữa các replica | Tham gia group lại với member identity riêng |
| Tạo thư mục tạm thất bại | Volume read-only hoặc permission không phù hợp | Kiểm tra mount/permission; giữ readiness chưa sẵn sàng |
| Resource khởi tạo một phần rồi lỗi | Bước sau thất bại nhưng tài nguyên trước vẫn mở | Dọn dẹp theo thứ tự ngược và retry có kiểm soát |
| Hai replica cùng ghi một tài nguyên | Quyền sở hữu chỉ được lưu trong heap | Dùng coordinator, lease và fencing token ở storage |

Retry cần có timeout, backoff và jitter để nhiều replica không cùng dồn request tới identity provider hoặc secret manager ngay sau restore. Nếu credential service đang lỗi, giữ replica chưa sẵn sàng và phát tín hiệu vận hành rõ ràng.

Không log secret, private key hoặc token khi chẩn đoán. Có thể log loại credential, issuer, thời hạn đã rút gọn, request correlation ID và mã lỗi mà không ghi giá trị bí mật.

## 10. Bảo vệ ảnh checkpoint chứa thông tin nhạy cảm

Checkpoint có thể chứa nhiều đối tượng trong heap, bao gồm token, mật khẩu, private key, session cookie, dữ liệu cá nhân và nội dung request. Nếu cùng ảnh được nhân bản sang nhiều replica, mỗi replica có thể nhận một bản sao của các giá trị đó.

Hãy xem ảnh checkpoint như một artifact nhạy cảm:

- Mã hóa ảnh khi lưu trữ và truyền tải theo chính sách của môi trường.
- Giới hạn quyền đọc, ghi, tải xuống và khôi phục ảnh.
- Chỉ cho phép workload hoặc pipeline được ủy quyền sử dụng ảnh.
- Giới hạn thời gian lưu giữ và xóa ảnh cũ theo quy trình an toàn.
- Không đưa credential dài hạn vào ảnh nếu có thể lấy credential mới sau restore.
- Xoay vòng hoặc thu hồi credential có thể đã xuất hiện trong ảnh khi có sự cố.
- Không ghi secret vào log trong callback hoặc lúc tạo ảnh.
- Theo dõi phiên bản ảnh và nguồn tạo ảnh để tránh restore một artifact cũ có cấu hình hoặc credential lỗi thời.

Nếu ảnh bắt buộc phải chứa secret, cần đánh giá phạm vi ảnh hưởng khi ảnh bị lộ hoặc được dùng ngoài dự kiến. Một private key dùng chung trong checkpoint có thể làm tất cả replica cùng chia sẻ một bí mật; việc mã hóa ảnh bảo vệ dữ liệu khi lưu trữ nhưng không làm cho key trở thành riêng từng replica sau restore.

## 11. Những lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Cách điều chỉnh |
|---|---|---|
| Tạo INSTANCE_ID static trước checkpoint | Tất cả replica có thể dùng cùng ID | Tạo lại trong lifecycle sau restore hoặc lấy từ metadata replica |
| Dùng hostname đã snapshot làm replica identity | Hostname có thể thuộc replica tạo ảnh | Truy vấn metadata hiện tại |
| Giữ leader=true trong heap | Nhiều replica cùng nghĩ mình là leader | Xin lease/election mới và dùng fencing token |
| Dùng một refresh token cho mọi replica | Rotation hoặc single-use semantics gây xung đột | Credential riêng theo replica hoặc token broker |
| Giữ private key client trong checkpoint | Nhiều replica chia sẻ cùng private key | Tạo key riêng hoặc dùng identity service/HSM |
| Dùng bộ đếm static để tạo ID toàn cục | Các bản sao tiếp tục từ cùng counter | Database sequence hoặc ID service |
| Tạo file tạm với tên cố định | Replica ghi đè hoặc xóa tệp của nhau | Thư mục/tên tệp riêng theo replica |
| Khôi phục socket/connection pool cũ | Peer có thể đã đóng hoặc credential đã cũ | Đóng trước checkpoint, tạo client/pool mới |
| Dùng member ID cố định cho consumer | Broker từ chối hoặc các replica tranh chấp | Join group lại và nhận member identity riêng |
| Mở readiness ngay sau JVM restore | Replica chưa có credential hoặc dependency | Readiness sau bootstrap và health check |
| Dùng idempotency key mới cho mỗi retry | Một thao tác có thể được thực hiện nhiều lần | Giữ key ổn định cho cùng operation |
| Dùng timestamp làm nguồn ID duy nhất | Nhiều replica có thể tạo cùng thời điểm | Dùng UUID, ID service hoặc unique constraint |

## 12. Kiểm thử nhiều replica từ cùng checkpoint

Kiểm thử một tiến trình restore đơn lẻ không phát hiện được mọi lỗi nhân bản. Hãy dùng cùng một checkpoint để tạo nhiều replica trong môi trường kiểm thử và quan sát hành vi đồng thời.

Một kịch bản tổng quát:

1. Khởi động ứng dụng, tạo checkpoint sau khi các cấu hình dùng chung đã được nạp.
2. Dùng cùng ảnh checkpoint để restore ít nhất hai replica.
3. Thu thập service identity, replica identity và process incarnation ID từ từng bản sao.
4. Xác nhận replica identity/incarnation ID khác nhau theo yêu cầu.
5. Xác nhận cấu hình và service identity cần chia sẻ vẫn nhất quán.
6. Xác nhận mỗi replica tạo tài nguyên cục bộ và connection pool riêng.
7. Kiểm tra credential được cấp theo chính sách, token có thời hạn hợp lệ và private key không bị chia sẻ ngoài chủ đích.
8. Xác nhận consumer group có member riêng và broker phân phối công việc đúng.
9. Thử để một replica hết lease rồi restore lại; xác nhận nó không tiếp tục dùng quyền leader cũ.
10. Thử nhiều replica cùng thực hiện thao tác nghiệp vụ; xác nhận ID nghiệp vụ và idempotency không bị trùng hoặc xử lý lặp sai.
11. Thử identity provider hoặc secret manager tạm thời không sẵn sàng; xác nhận readiness vẫn đóng và retry có giới hạn.
12. Kiểm tra log, metrics và trace có thể phân biệt replica.

### 12.1. Ma trận kiểm thử

| Hạng mục | Điều kiện kiểm thử | Kết quả mong đợi |
|---|---|---|
| Replica identity | Restore hai bản sao từ cùng ảnh | ID riêng biệt |
| Service identity | Restore nhiều bản sao cùng workload | Cùng service identity theo cấu hình |
| Process incarnation | Restore lại cùng replica | Incarnation mới nếu chính sách yêu cầu |
| Temporary directory | Hai replica cùng mount volume | Đường dẫn riêng, không ghi đè |
| Socket/port | Hai replica cùng chạy | Socket được tạo mới, không dùng descriptor cũ; port theo cơ chế cấp riêng |
| Credential | Restore đồng thời nhiều replica | Credential hợp lệ theo phạm vi và không xung đột |
| Certificate rotation | CA/certificate thay trong lúc JVM dừng | Client nạp key/trust material mới theo policy |
| Lease/leader | Lease cũ hết hạn trước restore | Replica phải acquire lại; token cũ không ghi được |
| Consumer group | Nhiều replica cùng join | Member identity và assignment đúng |
| ID nghiệp vụ | Nhiều replica tạo record đồng thời | Không trùng nhờ nguồn cấp ID/constraint |
| Readiness | Secret manager bị lỗi | Replica chưa sẵn sàng và retry có giới hạn |
| Observability | Cùng request đi qua nhiều replica | Log/trace có thể phân biệt instance |

### 12.2. Những gì cần ghi nhận

Trong môi trường thử nghiệm, có thể ghi lại:

- Service identity.
- Replica ID và process incarnation ID.
- Thời điểm restore và thời điểm readiness mở.
- Loại credential, issuer và expiry (không ghi token).
- Phiên bản certificate hoặc fingerprint công khai nếu phù hợp.
- Lease generation/fencing token.
- Consumer member ID do broker cấp.
- Kết quả health check và lỗi bootstrap.

Không ghi private key, secret, password hoặc access token vào log hay báo cáo kiểm thử.

## 13. Quy trình triển khai đề xuất

Một quy trình có thể chia thành ba giai đoạn.

### Khi chuẩn bị checkpoint

1. Xác định các trường và tài nguyên nào được phép chia sẻ giữa replica.
2. Ngừng nhận công việc mới và drain worker.
3. Hoàn tất hoặc rollback transaction.
4. Đóng connection, socket, consumer và client theo API hỗ trợ.
5. Giải phóng lease/lock nếu giao thức yêu cầu.
6. Xóa hoặc vô hiệu hóa tham chiếu tới credential/session không nên được tái sử dụng.
7. Chỉ tạo checkpoint khi resource đã về trạng thái an toàn.

### Khi restore từng replica

1. Truy vấn metadata của replica hiện tại.
2. Tạo replica/incarnation identity mới hoặc xác minh identity được nền tảng cấp.
3. Tạo tài nguyên cục bộ và endpoint riêng.
4. Lấy credential ngắn hạn theo workload/replica identity.
5. Tạo lại SSLContext, client, connection pool, consumer và scheduler.
6. Đăng ký lại service, tham gia group và xin lease.
7. Kiểm tra quyền sở hữu, health và readiness.

### Khi replica hoạt động

1. Gia hạn hoặc làm mới credential theo vòng đời.
2. Theo dõi lease và fencing token.
3. Dùng ID nghiệp vụ từ nguồn có thẩm quyền.
4. Duy trì log, metric và trace có replica identity.
5. Khi checkpoint tiếp theo, lặp lại quy trình drain và giải phóng tài nguyên.

## 14. Nguyên tắc thiết kế

- Cùng một checkpoint có thể tạo nhiều bản sao với cùng giá trị ban đầu trong heap.
- Phân biệt service identity, workload identity, replica identity, process incarnation ID và business ID.
- Chỉ giữ nguyên các giá trị thực sự được chia sẻ theo thiết kế.
- Tạo lại ID riêng cho từng replica sau restore hoặc lấy ID từ metadata của nền tảng.
- Không dùng bộ đếm local trong heap làm nguồn cấp ID toàn cục.
- Kiểm tra trạng thái PRNG/SecureRandom theo JDK và provider; không dùng seed cố định hoặc PRNG tự chế cho bảo mật.
- Tạo lại thư mục, socket, connection pool, consumer và scheduler thuộc về từng replica.
- Không khôi phục quyền leader hoặc lease từ boolean trong heap; acquire lại và dùng fencing token.
- Lấy token/chứng chỉ từ identity provider hoặc secret manager theo chính sách sau restore.
- Hạn chế credential dài hạn và private key trong checkpoint.
- Chỉ mở readiness sau khi identity, credential và dependency riêng của replica đã sẵn sàng.
- Kiểm thử nhiều replica đồng thời từ cùng một ảnh checkpoint.

CRaC có thể tái sử dụng phần khởi tạo chung của JVM, nhưng không thể tự phân biệt danh tính của các bản sao được tạo từ cùng snapshot. Ứng dụng phải chủ động tạo hoặc xác minh identity riêng, tạo lại tài nguyên cục bộ, lấy credential theo chính sách và xin lại quyền sở hữu phân tán sau restore. Khi các bước đó hoàn tất trước readiness, nhiều replica có thể dùng chung lợi ích của checkpoint mà vẫn hoạt động như những instance độc lập.
