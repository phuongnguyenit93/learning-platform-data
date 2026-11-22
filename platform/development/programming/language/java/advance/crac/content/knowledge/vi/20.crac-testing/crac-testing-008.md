# Kiểm thử nhiều bản sao để phát hiện ID trùng và tác dụng phụ lặp

Một checkpoint CRaC có thể được dùng làm điểm khởi đầu cho nhiều tiến trình Java. Điều này giúp các replica bỏ qua phần khởi tạo tốn thời gian, nhưng cũng có một hệ quả quan trọng: mỗi replica có thể bắt đầu từ cùng một trạng thái heap. Những giá trị được tạo trước checkpoint như instance ID, bộ đếm cục bộ, seed của bộ sinh số, trạng thái scheduler, consumer metadata hoặc cờ leader có thể được sao chép sang nhiều bản sao.

Khi các replica hoạt động đồng thời, lỗi có thể xuất hiện dưới dạng ID bị trùng, hai instance cùng nghĩ mình sở hữu một tài nguyên, cùng xử lý một message hoặc cùng thực hiện một side effect. Những lỗi này thường khó tái hiện khi chỉ kiểm thử một lần restore. Cần tạo nhiều replica từ cùng một checkpoint image, cho chúng chạy đồng thời và quan sát kết quả tại các hệ thống có thẩm quyền như database, broker, payment provider hoặc distributed coordinator.

Mục tiêu của bài kiểm thử là chứng minh hai điều:

- Mỗi replica có danh tính và tài nguyên riêng theo đúng phạm vi, trong khi service identity và dữ liệu dùng chung vẫn nhất quán.
- Một thao tác nghiệp vụ chỉ tạo ra số side effect được hợp đồng cho phép, kể cả khi nhiều replica nhận cùng request/message hoặc cùng khôi phục từ một ảnh.

## 1. Vì sao cần kiểm thử nhiều bản sao từ cùng checkpoint?

Kiểm thử một JVM checkpoint rồi restore một lần chỉ chứng minh một đường đi. Nó không phơi bày những giá trị bị nhân bản giữa nhiều tiến trình. Khi hai hoặc nhiều replica cùng restore một ảnh, trạng thái ban đầu của chúng có thể giống nhau dù mỗi tiến trình có không gian bộ nhớ riêng.

Ví dụ, ứng dụng tạo ID trong quá trình khởi động:

~~~java
public final class InstanceState {
    static final String INSTANCE_ID = UUID.randomUUID().toString();
    static long nextSequence = 50_000;
    static boolean leader = true;
}
~~~

Nếu checkpoint được tạo sau khi các trường này đã khởi tạo, nhiều replica có thể nhận cùng INSTANCE_ID, cùng nextSequence và cùng giá trị leader. Từ thời điểm đó:

- Log và metric không phân biệt được replica nào tạo sự kiện.
- Bộ đếm cục bộ có thể cấp cùng ID cho các bản sao.
- Nhiều instance có thể cùng thực hiện công việc dành cho leader.
- Consumer có thể dùng chung member identity hoặc session metadata.
- Scheduler có thể chạy cùng một job trên tất cả replica.
- Tài nguyên cục bộ có thể tranh chấp cùng file path, socket path hoặc tên lock.

Không phải mọi giá trị giống nhau đều là lỗi. Service name, schema version, consumer group hoặc cấu hình bất biến thường được chia sẻ có chủ đích. Bài kiểm thử phải biết giá trị nào cần giống nhau và giá trị nào bắt buộc khác nhau.

### 1.1. Phân biệt các loại ID

| Loại định danh | Phạm vi | Kỳ vọng giữa các replica |
|---|---|---|
| Service identity | Một dịch vụ logic | Thường giống nhau |
| Workload identity | Một workload được cấp quyền | Có thể giống nhau theo chính sách nền tảng |
| Replica/instance ID | Một bản sao đang chạy | Phải khác nhau nếu dùng để phân biệt replica |
| Process incarnation ID | Một lần chạy/restore cụ thể | Phải mới theo mỗi incarnation nếu hệ thống yêu cầu |
| Consumer member ID | Một thành viên trong group | Phải tuân theo hợp đồng của broker; thường riêng cho từng member |
| Business entity ID | Đơn hàng, thanh toán, tài khoản | Duy nhất theo quy tắc nghiệp vụ |
| Idempotency key | Một thao tác có thể retry | Phải giữ ổn định cho cùng thao tác, kể cả khi retry qua replica khác |
| Lease/fencing token | Quyền sở hữu có thứ tự | Được coordinator cấp và xác minh; không lấy từ heap đã snapshot |

Một test chỉ kiểm tra “mọi ID phải khác nhau” là quá thô. Ví dụ, hai replica của orders-api cần cùng service identity để được định tuyến như một dịch vụ, nhưng phải có replica ID khác nhau. Một request tạo đơn hàng cần giữ cùng idempotency key qua retry; tạo key mới trên mỗi replica có thể khiến cùng một thao tác bị thực hiện hai lần.

### 1.2. Phân biệt ID bị trùng và side effect bị lặp

ID bị trùng và side effect bị lặp có liên quan nhưng là hai lỗi khác nhau:

- ID bị trùng là hai đối tượng độc lập nhận cùng định danh trong một phạm vi yêu cầu duy nhất.
- Side effect bị lặp là một thao tác nghiệp vụ gây ra nhiều lần thay đổi trạng thái bên ngoài.

Một hệ thống có thể tạo ID duy nhất nhưng vẫn gửi cùng lệnh thanh toán hai lần. Ngược lại, một request có thể được deduplicate đúng nhưng log vẫn có instance ID trùng làm việc điều tra khó khăn. Cần test riêng cả hai nhóm.

## 2. Thiết kế môi trường kiểm thử multi-replica

Một test đáng tin cậy cần sử dụng cùng checkpoint image cho nhiều replica. Mỗi replica phải chạy như một tiến trình độc lập, có tài nguyên runtime riêng và được quan sát bằng một định danh kiểm thử.

### 2.1. Tạo checkpoint chuẩn

Quy trình:

1. Build ứng dụng với JDK/runtime CRaC và dependency cố định.
2. Khởi động một instance theo cấu hình kiểm thử.
3. Hoàn tất phần warm-up được dự định lưu trong ảnh.
4. Đưa ứng dụng về trạng thái an toàn theo callback trước checkpoint.
5. Tạo checkpoint image.
6. Ghi lại digest, JDK build, engine, cấu hình và version dependency.
7. Giữ nguyên ảnh chuẩn để dùng cho mọi replica trong cùng một lượt test.

Không tạo một checkpoint riêng cho mỗi replica nếu mục tiêu là phát hiện giá trị bị nhân bản. Làm vậy có thể che giấu lỗi vì mỗi ảnh có thể tạo identity hoặc seed khác nhau.

### 2.2. Restore cùng ảnh thành nhiều tiến trình

Một harness có thể khởi chạy N tiến trình restore từ cùng image:

~~~text
checkpoint-image/
  replica-a/
  replica-b/
  replica-c/
~~~

Các thư mục trên chỉ minh họa workspace riêng cho từng lần restore; cách runtime tham chiếu ảnh phụ thuộc engine. Nếu engine hỗ trợ restore từ cùng một nguồn nhiều lần, hãy giữ ảnh gốc bất biến và cung cấp destination/runtime state riêng cho từng tiến trình theo tài liệu của engine.

Mỗi replica cần có:

- Process/container riêng.
- Writable directory hoặc overlay riêng.
- Log riêng hoặc log có replica tag.
- Port riêng, hoặc bind port động rồi công bố port thực tế.
- Thông tin metadata riêng của replica nếu nền tảng cung cấp.
- Kết nối và session riêng theo chính sách ứng dụng.

Không cho nhiều replica cùng ghi vào một thư mục writable được thiết kế cho một tiến trình. Việc dùng chung checkpoint image bất biến khác với việc dùng chung thư mục runtime, log hoặc file tạm.

### 2.3. Đồng bộ thời điểm bắt đầu

Lỗi race condition thường chỉ xuất hiện khi các replica thực hiện thao tác gần như cùng lúc. Sau restore, hãy dùng một barrier trong test harness:

1. Khởi chạy tất cả replica.
2. Chờ từng replica báo đã hoàn tất bootstrap và đang ở trạng thái ready-for-test.
3. Gửi tín hiệu bắt đầu chung.
4. Tất cả replica đồng thời tạo ID hoặc xử lý cùng một loại công việc.
5. Thu thập kết quả từ từng replica và nguồn dữ liệu có thẩm quyền.

Nếu chỉ khởi chạy tuần tự, một replica có thể hoàn tất đăng ký hoặc chiếm lock trước khi replica tiếp theo bắt đầu; race condition sẽ khó xuất hiện.

### 2.4. Tăng độ khó có kiểm soát

Chạy nhiều biến thể:

- Hai replica để kiểm tra lỗi cơ bản.
- Ba hoặc nhiều replica để tăng khả năng va chạm.
- Restore đồng thời và restore lệch thời điểm.
- Nhiều lần restore lặp lại từ cùng một image.
- Thời gian dừng ngắn, dài và vượt qua TTL/lease.
- Một replica khởi động chậm hoặc mất kết nối trong lúc bootstrap.
- Một replica bị kill rồi được tạo lại từ cùng image.

Không nên chỉ chạy một lần rồi kết luận không có collision. Một số lỗi phụ thuộc lịch chạy, entropy, timestamp hoặc tải đồng thời. Hãy lặp lại test đủ số lần theo mức rủi ro và ghi nhận số lần thực hiện.

## 3. Xây dựng test harness

Harness điều phối checkpoint image, khởi chạy replica, đồng bộ hoạt động và thu thập bằng chứng. Có thể xây dựng bằng shell, Testcontainers, JUnit, Kubernetes Job hoặc một test controller riêng.

### 3.1. Trách nhiệm của harness

Harness nên:

- Xác minh checkpoint image tồn tại và đúng digest.
- Khởi chạy N replica từ cùng một image.
- Cấp tên replica cho mục đích quan sát, không dùng tên này làm bằng chứng rằng ứng dụng tự tạo identity đúng.
- Chờ bootstrap và readiness.
- Thu thập service ID, replica ID và incarnation ID từ endpoint chẩn đoán an toàn.
- Đồng bộ thao tác qua barrier.
- Gửi request/message đồng thời.
- Truy vấn database, broker và hệ thống giả lập side effect.
- Kiểm tra số ID duy nhất, số record và số side effect thực tế.
- Lưu log, metric, trace, cấu hình và thông tin runtime của lượt test.
- Dọn tài nguyên sau khi test hoàn tất.

### 3.2. Không nhầm test label với identity ứng dụng

Harness có thể đặt tên tiến trình là replica-a, replica-b. Nhưng ứng dụng phải tự công bố identity được tạo hoặc xác minh sau restore. Nếu endpoint chỉ trả về biến môi trường do harness gán, test chưa chứng minh logic tạo identity trong ứng dụng hoạt động.

Nên thu thập cả hai:

- Test label do harness gán để biết output thuộc tiến trình nào.
- Application identity do ứng dụng tạo hoặc lấy từ metadata nền tảng.

Sau đó xác nhận mapping giữa hai giá trị. Test label không cần phải là bí mật; không đưa credential thật vào environment chỉ để đánh dấu replica.

### 3.3. Pseudocode điều phối

~~~java
List<ReplicaHandle> replicas =
        checkpointHarness.restoreMany(checkpointImage, 4);

try {
    for (ReplicaHandle replica : replicas) {
        replica.awaitBootstrap(Duration.ofMinutes(2));
    }

    List<ReplicaIdentity> identities = replicas.stream()
            .map(ReplicaHandle::readIdentity)
            .toList();

    assertUniqueReplicaIds(identities);

    TestBarrier barrier = new TestBarrier(replicas.size());
    List<Future<TestResult>> results = replicas.stream()
            .map(replica -> executor.submit(() -> {
                barrier.awaitReady();
                return replica.performConcurrentOperation();
            }))
            .toList();

    List<TestResult> completed = collect(results);
    assertBusinessInvariants(completed);
    assertExternalEffects(checkpointHarness.effectStore());
} finally {
    replicas.forEach(ReplicaHandle::stop);
}
~~~

Các kiểu CheckpointHarness, ReplicaHandle, ReplicaIdentity, TestBarrier và TestResult là thành phần giả định của test harness, không phải API có sẵn của CRaC. Pseudocode mô tả thứ tự kiểm thử: restore cùng ảnh, chờ bootstrap, đọc identity, đồng bộ hoạt động và xác minh kết quả từ nguồn có thẩm quyền.

## 4. Kiểm thử ID bị trùng

Không nên chỉ kiểm tra ID trong log. Hãy lấy ID từ ứng dụng và xác minh tại phạm vi nơi ID được dùng. Nếu ID là khóa database, constraint unique của database là bằng chứng quan trọng hơn một danh sách ID được thu thập trong JVM.

### 4.1. Instance ID và process incarnation ID

Kịch bản:

1. Tạo checkpoint sau khi ứng dụng đã khởi tạo.
2. Restore ít nhất hai replica từ cùng ảnh.
3. Gọi endpoint chẩn đoán hoặc thu thập metadata của từng tiến trình.
4. Xác nhận service identity giống nhau nếu đó là hợp đồng.
5. Xác nhận replica identity khác nhau.
6. Nếu mỗi lần restore phải có incarnation riêng, xác nhận incarnation ID cũng khác.
7. Lặp lại với cùng ảnh và nhiều lượt restore.

Tiêu chí:

- Không có hai replica đang hoạt động cùng dùng một replica ID trong phạm vi yêu cầu duy nhất.
- ID được tạo sau restore hoặc được lấy từ metadata hiện tại.
- Log và trace phân biệt được từng replica.
- Khi một replica restart/restore lần nữa, incarnation ID thay đổi nếu chính sách yêu cầu.

### 4.2. Bộ đếm cục bộ trong heap

Một static counter hoặc AtomicLong được snapshot có thể bắt đầu từ cùng giá trị ở nhiều replica. Test nên cho mọi replica cấp một dải ID đồng thời:

~~~java
long id = localSequence.incrementAndGet();
idRepository.insert(id, replicaIdentity);
~~~

Nếu hai replica cùng bắt đầu từ sequence 1000, cả hai có thể cấp 1001. Database phải có unique constraint trên ID để phát hiện collision thay vì âm thầm ghi đè.

Kiểm thử cần:

- Restore nhiều replica từ cùng ảnh.
- Đồng bộ tất cả replica trước khi cấp ID.
- Cho mỗi replica cấp một số lượng ID lớn trong thời gian ngắn.
- Ghi tất cả ID vào bảng có constraint unique.
- Xác nhận không có duplicate và không có lỗi insert bị nuốt.
- Kiểm tra nguồn cấp ID có thẩm quyền thay vì chỉ thay đổi biến cục bộ.

Nếu ứng dụng cần ID toàn cục, hãy dùng database sequence, ID service, UUID/ULID phù hợp hoặc dải ID được cấp không giao nhau. Đồng bộ trong một JVM không giải quyết collision giữa nhiều tiến trình.

### 4.3. UUID và bộ sinh ngẫu nhiên

Không nên kết luận UUID chắc chắn trùng hoặc chắc chắn không trùng chỉ từ việc các replica restore cùng ảnh. Kết quả phụ thuộc implementation, provider, trạng thái entropy và cách JDK xử lý generator qua checkpoint. Hãy kiểm tra đúng JDK/runtime và provider đang triển khai.

Test nên:

- Tạo nhiều UUID sau restore trên tất cả replica.
- Ghi lại số lượng và kiểm tra collision trong tập dữ liệu.
- Kiểm tra provider SecureRandom và chính sách entropy.
- Thử nhiều lần restore, nhiều process và thời gian bắt đầu đồng thời.
- Không dùng seed cố định hoặc timestamp đơn lẻ làm nguồn duy nhất.

Một phép thử không tìm thấy collision chỉ là bằng chứng thực nghiệm trong phạm vi mẫu đã chạy, không phải chứng minh toán học cho tính duy nhất. Nếu yêu cầu duy nhất tuyệt đối, hãy dùng constraint hoặc allocator có thẩm quyền.

### 4.4. Snowflake ID và node ID

Các bộ sinh ID kiểu Snowflake thường ghép timestamp, node/worker ID và sequence. Nếu node ID được cấu hình hoặc tạo trước checkpoint rồi nhân bản, hai replica có thể sinh cùng ID trong cùng millisecond.

Kiểm thử:

- Restore nhiều replica từ cùng ảnh.
- Cho mỗi replica sinh ID đồng thời trong cùng khoảng thời gian.
- Kiểm tra node ID của từng replica.
- Ghi ID vào storage có unique constraint.
- Thử đồng hồ lùi hoặc thời gian trùng.
- Kiểm tra sequence overflow và cách generator chờ sang millisecond tiếp theo.

Node ID cần được cấp duy nhất bởi coordinator hoặc lấy từ metadata nền tảng theo một hợp đồng rõ ràng. Không dùng một số worker ID được snapshot làm danh tính vĩnh viễn của mọi replica.

### 4.5. Consumer member ID

Broker thường phân biệt consumer group với member của group. Group ID có thể giống nhau vì nhiều replica cùng tham gia một nhóm; member ID hoặc generation/session metadata phải theo quy tắc của broker.

Kiểm thử:

- Restore nhiều consumer từ cùng checkpoint.
- Cho tất cả join cùng group gần như đồng thời.
- Quan sát member ID, generation và partition assignment do broker quản lý.
- Xác nhận không có member bị từ chối do identity trùng.
- Dừng một member và restore lại; xác nhận group rebalance và membership mới hợp lệ.

Không hard-code member ID trước checkpoint nếu broker yêu cầu mỗi member có danh tính riêng. Ưu tiên để client/broker tạo hoặc thương lượng member identity theo protocol.

### 4.6. Local resource ID và path

Một số ID không phải UUID nhưng vẫn phải riêng:

- Tên file tạm và thư mục spool.
- Unix domain socket path.
- PID file và lock file.
- Consumer checkpoint file.
- Cache namespace hoặc local database directory.
- Port và endpoint nội bộ.

Test cần xác nhận mỗi replica ghi vào path riêng hoặc dùng một cơ chế chia sẻ có locking đúng. Nếu dùng port động, kiểm tra port thực tế được bind. Không giả định một giá trị port được snapshot vẫn có thể bind trên nhiều tiến trình.

## 5. Kiểm thử side effect lặp

Side effect lặp thường xảy ra ở ranh giới không chắc chắn: ứng dụng đã gửi request nhưng chưa biết server đã thực hiện hay chưa; message đã xử lý nhưng chưa commit offset; transaction đã commit nhưng response chưa tới client; scheduler bị khởi động lại và chạy lại một lần đã thực hiện.

### 5.1. Xác định side effect cần bảo vệ

Liệt kê các hành động thay đổi trạng thái bên ngoài:

- Tạo đơn hàng, thanh toán, hoàn tiền hoặc đặt chỗ.
- Gửi email, SMS hoặc webhook.
- Tạo tài nguyên qua API bên ngoài.
- Gửi message/event tới broker.
- Cập nhật database hoặc object storage.
- Ghi nhận offset, acknowledgment hoặc job completion.
- Chạy tác vụ định kỳ có side effect.

Với từng hành động, xác định “một lần” được tính theo request, business operation, message ID hay lịch chạy. Không thể kiểm tra số lần gọi API mà không hiểu hợp đồng idempotency của API đó.

### 5.2. Idempotency key phải ổn định qua retry

Một request được retry bởi replica khác vẫn phải mang cùng idempotency key nếu nó đại diện cho cùng một thao tác nghiệp vụ.

Ví dụ HTTP:

~~~http
POST /payments
Idempotency-Key: pay-order-8392
Content-Type: application/json

{
  "orderId": "order-8392",
  "amount": 125000
}
~~~

Payment service cần lưu key cùng kết quả và từ chối hoặc trả lại kết quả cũ khi cùng key được gửi lần nữa. Nếu mỗi replica tạo key mới khi restore, provider sẽ xem đó là những thao tác khác nhau và có thể thực hiện nhiều khoản thanh toán.

Tiêu chí:

- Cùng business operation giữ cùng idempotency key qua checkpoint/restore và retry.
- Hai replica gửi cùng key không tạo hai business effect.
- Cùng key nhưng payload khác phải được phát hiện theo hợp đồng provider.
- Key có thời hạn lưu đủ dài so với retry window của hệ thống.
- Log có thể tương quan operation nhưng không làm lộ dữ liệu nhạy cảm.

### 5.3. Transactional outbox

Nếu ứng dụng vừa ghi database vừa gửi event, một transaction database không thể tự động bao trùm broker trong mọi kiến trúc. Outbox giúp ghi business update và event record trong cùng transaction. Một publisher đọc outbox rồi gửi message; nếu gửi thành công nhưng chưa đánh dấu đã publish, message có thể được gửi lại.

Vì vậy, outbox cần được kết hợp với consumer idempotency hoặc deduplication. Checkpoint có thể xảy ra giữa bước publish và bước đánh dấu. Nhiều replica restore từ cùng ảnh có thể cùng nhìn thấy một outbox record nếu cơ chế claim không an toàn.

Test:

1. Tạo outbox record đã commit.
2. Cho publisher gửi message tới broker.
3. Giả lập mất phản hồi hoặc checkpoint trước khi publisher đánh dấu record hoàn tất.
4. Restore nhiều replica.
5. Cho các publisher cùng xử lý record đó.
6. Xác nhận event có thể được giao nhiều lần nhưng business effect ở consumer chỉ được áp dụng một lần.
7. Xác nhận trạng thái outbox cuối cùng được cập nhật đúng.

Không đòi hỏi transport luôn giao đúng một lần nếu kiến trúc cung cấp at-least-once. Tiêu chí nên tập trung vào một business effect duy nhất bằng idempotency.

### 5.4. Inbox hoặc deduplication ở consumer

Consumer có thể ghi message ID vào inbox table với unique constraint trong cùng transaction với business update. Nếu message được giao lại, insert trùng bị phát hiện và consumer không lặp side effect.

Ví dụ SQL:

~~~sql
CREATE TABLE processed_message (
    message_id VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(100) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

Logic transaction có thể:

1. Insert message ID vào processed_message.
2. Nếu insert thành công, thực hiện business update.
3. Commit cả hai thay đổi cùng transaction.
4. Chỉ acknowledgment message sau khi commit.
5. Nếu message ID đã tồn tại, bỏ qua business update và acknowledgment theo protocol.

Trong test multi-replica, cho nhiều consumer xử lý cùng message ID gần như đồng thời. Unique constraint và transaction phải bảo đảm chỉ một transaction áp dụng business update.

### 5.5. Side effect với hệ thống ngoài

Với payment provider, email service hoặc API không tham gia transaction database, cần dùng idempotency key, operation reference hoặc reconciliation API.

Một test tốt mô phỏng tình huống:

- Provider nhận request và thực hiện side effect.
- Phản hồi bị mất hoặc bị trì hoãn.
- Ứng dụng checkpoint/restore hoặc replica khác retry.
- Provider nhận lại cùng idempotency key.
- Kết quả nghiệp vụ chỉ được ghi nhận một lần.

Nếu provider không hỗ trợ idempotency, ứng dụng cần một cơ chế reconciliation có thẩm quyền trước khi retry. Không thể bảo đảm exactly-once end-to-end chỉ bằng cách khóa một biến trong heap.

## 6. Kiểm thử scheduler, worker và quyền leader

Scheduler là nguồn phổ biến gây tác dụng phụ lặp. Nếu lịch hoặc trạng thái “lần chạy kế tiếp” được snapshot, nhiều replica có thể cùng khởi động và thực hiện cùng một công việc.

### 6.1. Scheduled task

Ví dụ tác vụ gửi hóa đơn lúc 02:00:

- Checkpoint được tạo sau khi scheduler đã đăng ký task.
- Nhiều replica restore cùng ảnh.
- Tất cả scheduler khôi phục cùng lịch và cùng lúc chạy tác vụ.

Kiểm thử:

1. Tạo checkpoint sau khi lịch đã được đăng ký.
2. Restore nhiều replica.
3. Đồng bộ thời điểm chạy.
4. Xác nhận chỉ một job claim được một business period nếu yêu cầu là single execution.
5. Nếu job được phép chạy trên nhiều replica, xác nhận mỗi partition/job key chỉ được claim một lần.
6. Kiểm tra missed run trong thời gian dừng được xử lý theo policy.

Sử dụng distributed scheduler, database claim hoặc lease có fencing token. Không dựa vào biến isRunning trong heap để bảo đảm chỉ một replica thực hiện job.

### 6.2. Lease và leader election

Trước checkpoint, replica A có thể đang giữ lease. Trong lúc JVM dừng, lease hết hạn và replica B nhận lease mới. Khi A restore, trường leader trong heap vẫn có thể là true.

Test:

1. Cho A acquire lease và nhận fencing token N.
2. Checkpoint A.
3. Đợi lease hết hạn.
4. Cho B acquire lease và nhận token lớn hơn N.
5. Restore A.
6. Yêu cầu A thực hiện write với token N.
7. Storage/coordinator phải từ chối write cũ.
8. A chỉ được chạy leader task sau khi acquire lease mới.

Fencing token cần được kiểm tra tại nơi thực hiện side effect. Một mutex cục bộ hoặc cờ leader trong JVM không bảo vệ được khi nhiều tiến trình hoạt động độc lập.

### 6.3. Worker queue và claim task

Nếu worker lấy task từ database hoặc broker, checkpoint có thể xảy ra sau khi task đã được claim nhưng trước khi hoàn tất. Cần kiểm tra:

- Claim có lease/visibility timeout không?
- Task có được trả lại khi worker mất heartbeat không?
- Hai replica có thể cùng claim một task không?
- Task có idempotent không?
- Trạng thái hoàn tất có được ghi bền vững trước acknowledgment không?

Test với nhiều replica cùng cố claim một task. Dùng database locking, atomic update, unique constraint hoặc broker semantics để chứng minh chỉ một owner hợp lệ hoặc mọi xử lý lặp đều idempotent.

## 7. Kiểm thử song song và race condition

Lỗi ID trùng và side effect lặp thường phụ thuộc thời điểm. Hãy làm cho test có khả năng tạo cạnh tranh đồng thời, nhưng vẫn giữ kết quả có thể phân tích.

### 7.1. Barrier và đồng bộ thời điểm

Mỗi replica báo “ready” cho harness. Khi đủ N replica, harness phát lệnh bắt đầu chung. Trong ứng dụng, có thể dùng test-only endpoint hoặc message broadcast để bắt đầu thao tác cùng lúc.

Không nên thêm endpoint nguy hiểm vào production chỉ để test. Có thể bật test hook bằng profile kiểm thử, giới hạn network access và tắt hoàn toàn trong artifact production.

### 7.2. Tạo tải cạnh tranh

Thực hiện nhiều lượt:

- N replica cùng tạo ID trong một cửa sổ thời gian ngắn.
- N replica cùng xử lý một message.
- N replica cùng gửi request với một idempotency key.
- N replica cùng claim một scheduled job.
- N replica cùng xin lease cho một tài nguyên.
- N replica cùng ghi vào một namespace hoặc file path.

Tăng số lần lặp, số luồng trong mỗi replica và độ trễ ngẫu nhiên. Giữ lại seed hoặc thông tin lịch chạy của test harness để có thể tái hiện một lần thất bại.

### 7.3. Tránh test giả tạo

Không nên cho tất cả replica dùng chung một biến static trong test harness rồi gọi đó là trạng thái heap của JVM. Mỗi process có heap riêng. Dùng database, broker hoặc service giả lập qua network để làm điểm quan sát chung.

Không chỉ kiểm tra log vì log có thể bị mất hoặc ghi trùng. Dùng authoritative store để xác nhận số business record, payment, email dispatch hoặc job completion.

## 8. Kịch bản kiểm thử tổng hợp

Giả sử một ứng dụng Orders có HTTP endpoint tạo đơn hàng, publisher outbox, consumer xử lý event và scheduler dọn đơn hết hạn. Một checkpoint image được dùng để tạo ba replica.

### 8.1. Chuẩn bị

1. Khởi động ứng dụng và hoàn tất warm-up.
2. Tạo checkpoint sau khi resource đã vào trạng thái an toàn.
3. Ghi lại digest của image và version runtime.
4. Khởi chạy ba replica từ cùng image với writable state riêng.
5. Chờ cả ba replica hoàn tất bootstrap.
6. Thu thập service identity, replica identity và incarnation ID.

### 8.2. Kiểm tra identity

- Service identity của ba replica phải giống nhau.
- Replica ID phải khác nhau.
- Incarnation ID phải khác nhau nếu chính sách yêu cầu.
- Consumer member ID phải hợp lệ và không bị broker từ chối.
- Local path và endpoint không được xung đột.

### 8.3. Kiểm tra ID nghiệp vụ

1. Gửi đồng thời request tạo đơn hàng qua ba replica.
2. Dùng cùng idempotency key cho các request đại diện cùng một thao tác.
3. Gửi thêm các request độc lập với key khác nhau.
4. Thu thập order ID do hệ thống cấp.
5. Kiểm tra unique constraint và mapping operation-key/order-ID.

Kết quả mong đợi:

- Cùng operation key chỉ tạo một order record.
- Các operation độc lập nhận ID riêng.
- Không có insert collision bị nuốt hoặc ghi đè.

### 8.4. Kiểm tra side effect

1. Cho publisher gửi outbox event.
2. Giả lập phản hồi broker bị mất sau khi broker đã nhận message.
3. Restore hoặc restart một replica để publisher retry.
4. Cho ba consumer có khả năng nhận cùng event do redelivery.
5. Kiểm tra inbox/deduplication và business table.

Kết quả mong đợi:

- Event có thể được giao lại theo delivery semantics.
- Business effect chỉ được áp dụng một lần.
- Acknowledgment chỉ xảy ra sau khi kết quả bền vững.

### 8.5. Kiểm tra scheduler và lease

1. Tạo một job định kỳ có key theo business date.
2. Cho một replica giữ lease trước checkpoint.
3. Để lease hết hạn trong thời gian dừng.
4. Restore ba replica.
5. Đồng bộ để tất cả scheduler thử claim job.
6. Xác nhận một owner hợp lệ được cấp lease và các replica khác không thực hiện side effect.
7. Thử write bằng fencing token cũ và xác nhận bị từ chối.

### 8.6. Assertion cuối

- Không có replica ID trùng.
- Không có business ID trùng ngoài trường hợp cùng operation trả về cùng kết quả.
- Không có hai khoản thanh toán hoặc hai email dispatch cho cùng một operation key.
- Consumer có thể nhận redelivery nhưng không lặp business effect.
- Scheduler không chạy trùng một job single-owner.
- Lease cũ không cho phép replica cũ ghi.
- Readiness chỉ mở sau khi bootstrap hoàn tất.
- Mọi kết quả đều có bằng chứng từ database, broker, provider giả lập và log theo incarnation.

## 9. Test matrix

| Nhóm kiểm thử | Số replica / điều kiện | Hành động đồng thời | Kết quả mong đợi |
|---|---|---|---|
| Instance identity | 2, 3, N replica cùng image | Đọc identity sau restore | Replica ID khác nhau |
| Incarnation identity | Restore lặp cùng replica/image | Tạo incarnation ID | Khác nhau theo policy |
| Service identity | N replica cùng workload | Đọc service identity | Giống nhau theo cấu hình |
| Local counter | N replica cùng counter snapshot | Cấp ID đồng thời | Không collision tại authoritative store |
| UUID/random | N replica, nhiều lần lặp | Sinh tập ID lớn | Không collision quan sát được; provider được xác minh |
| Snowflake/node ID | N replica cùng checkpoint | Sinh ID cùng millisecond | Node ID riêng hoặc allocator ngăn trùng |
| Consumer member | N consumer cùng group | Join group đồng thời | Member identity và assignment hợp lệ |
| HTTP idempotency | N replica cùng key | Gửi cùng request | Một business effect |
| Payment provider | N replica cùng operation | Retry cùng idempotency key | Một payment operation |
| Outbox publisher | N publisher cùng record | Publish đồng thời | Có thể redelivery; consumer effect một lần |
| Inbox consumer | N consumer cùng message | Process cùng message ID | Một business update |
| Scheduler | N replica cùng lịch | Trigger cùng job key | Một claim/side effect theo policy |
| Leader/lease | Owner cũ và mới | Restore owner cũ sau lease expiry | Fencing từ chối owner cũ |
| Local file/path | N replica cùng volume | Tạo file/socket path | Namespace riêng hoặc lock đúng |
| Delayed restore | Thời gian dừng ngắn và dài | Restore sau TTL/lease expiry | Refresh/reacquire trước khi hoạt động |
| Repeated restore | Nhiều chu kỳ | Lặp checkpoint/restore | Không tăng resource, không tạo duplicate |
| Failure injection | Một dependency lỗi | Restore và retry | Không mở readiness sớm; retry có giới hạn |

## 10. Acceptance criteria có thể đo được

Mỗi test nên có điều kiện đầu vào, hành động, kết quả mong đợi và bằng chứng.

**AC-01 — Replica identity duy nhất**

- Điều kiện: cùng một checkpoint image được restore thành ít nhất ba replica.
- Hành động: mỗi replica báo replica ID và incarnation ID.
- Kết quả: mọi replica ID khác nhau; incarnation ID khác nhau nếu policy yêu cầu.
- Bằng chứng: registry hoặc endpoint chẩn đoán, log theo test label.

**AC-02 — Business ID không trùng**

- Điều kiện: ba replica cùng cấp ít nhất 10.000 ID trong một lượt kiểm thử đồng bộ.
- Hành động: ghi ID vào bảng có unique constraint.
- Kết quả: không có duplicate; không có lỗi unique violation bị bỏ qua.
- Bằng chứng: số record, số ID duy nhất và log allocator.

**AC-03 — Cùng operation chỉ có một side effect**

- Điều kiện: ba replica nhận request cùng idempotency key.
- Hành động: gửi request đồng thời và retry sau khi mô phỏng mất response.
- Kết quả: chỉ một business record/payment effect; mọi response trả về cùng operation result theo hợp đồng.
- Bằng chứng: database/provider effect ledger và idempotency record.

**AC-04 — Message redelivery an toàn**

- Điều kiện: broker giao lại cùng message ID cho nhiều consumer theo tình huống test.
- Hành động: các consumer xử lý đồng thời.
- Kết quả: một business update; acknowledgment sau commit.
- Bằng chứng: inbox table, business table, offset/ack và consumer log.

**AC-05 — Scheduler single-owner**

- Điều kiện: ba replica cùng restore một lịch có job key duy nhất.
- Hành động: cùng trigger job trong một cửa sổ thời gian.
- Kết quả: một replica claim job hoặc các partition được phân chia không chồng lặp theo policy.
- Bằng chứng: job claim record, lease owner và side-effect ledger.

**AC-06 — Fencing token**

- Điều kiện: replica A checkpoint với token N; replica B nhận token N+1 khi A dừng.
- Hành động: restore A và yêu cầu A ghi bằng N.
- Kết quả: storage từ chối write; A chỉ được tiếp tục sau khi acquire quyền mới.
- Bằng chứng: coordinator record và rejected write.

**AC-07 — Readiness**

- Điều kiện: một dependency bắt buộc chưa sẵn sàng sau restore.
- Hành động: kiểm tra readiness và gửi traffic.
- Kết quả: readiness vẫn đóng; không nhận request nghiệp vụ cho tới khi dependency sẵn sàng.
- Bằng chứng: probe response, routing và lifecycle log.

Các ngưỡng như số ID, số lượt lặp và thời gian chờ phải được chọn theo rủi ro và tải dự kiến. Một test với 10.000 ID là mẫu kiểm thử cụ thể, không chứng minh tính duy nhất tuyệt đối cho mọi execution.

## 11. Xử lý lỗi và tình huống biên

### 11.1. Một replica bootstrap chậm

Nếu một replica chậm hơn các replica khác, test harness không nên bỏ qua nó. Ghi nhận:

- Thời gian restore.
- Thời gian tạo identity.
- Thời gian lấy credential.
- Thời gian tạo connection pool.
- Thời gian readiness.

Không phát tín hiệu bắt đầu chung cho tới khi đủ số replica theo test scenario đã sẵn sàng. Với test riêng về startup skew, hãy cố ý cho một replica bắt đầu chậm và xác nhận coordinator vẫn xử lý đúng.

### 11.2. Một replica bị kill sau khi side effect đã xảy ra

Giả lập:

1. Replica A gửi payment request.
2. Provider thực hiện payment.
3. A bị kill trước khi lưu response.
4. Replica B xử lý retry cùng operation.
5. Provider nhận cùng idempotency key.

Kết quả phải có một payment effect. Nếu provider không hỗ trợ idempotency, ứng dụng cần reconciliation trước khi retry.

### 11.3. Một replica dùng ID trùng nhưng chưa gây lỗi

Không chỉ chờ collision gây exception. Nếu ID trùng chưa được dùng trong cùng thời điểm, hệ thống có thể âm thầm chấp nhận và lỗi xuất hiện sau này. Test nên chủ động đăng ký tất cả replica vào một registry có unique constraint hoặc gửi ID tới endpoint kiểm tra uniqueness.

### 11.4. Retry sau khi hết thời hạn deduplication

Nếu idempotency record bị xóa quá sớm, một retry muộn sau restore có thể thực hiện side effect lần nữa. Kiểm tra thời hạn lưu deduplication record dài hơn retry window, thời gian tối đa dừng và thời gian retry từ client.

### 11.5. Đồng hồ lệch hoặc quay lùi

Các bộ sinh ID dựa trên timestamp có thể gặp collision hoặc dừng khi clock rollback. Test:

- Khởi tạo clock giả hoặc test clock có thể điều khiển.
- Tạo nhiều ID trong cùng millisecond.
- Đưa clock lùi.
- Cho các replica có clock skew.
- Xác nhận generator xử lý đúng theo contract hoặc từ chối cấp ID.

Không dùng wall-clock timestamp đơn lẻ làm ID duy nhất.

### 11.6. Restore từ checkpoint cũ

Một checkpoint image cũ có thể chứa cấu hình, counter hoặc credential đã lỗi thời. Kiểm thử:

- Restore ảnh cũ sau khi schema đã thay đổi.
- Restore ảnh cũ sau khi token/certificate bị rotate.
- Restore ảnh cũ sau khi một lease đã hết hạn.
- Restore ảnh cũ sau khi service endpoint hoặc DNS đổi.

Ứng dụng phải xác minh version và trạng thái hiện tại trước khi hoạt động. Nếu ảnh không còn tương thích, từ chối restore hoặc dùng đường khởi động bình thường theo policy.

## 12. Quan sát và thu thập bằng chứng

### 12.1. Log

Mỗi log liên quan test nên có:

- Test run ID.
- Checkpoint image digest hoặc version.
- Test label của replica.
- Service identity.
- Replica identity.
- Process incarnation ID.
- Operation ID hoặc message ID đã được làm sạch dữ liệu nhạy cảm.
- Callback phase và timestamp.

Không ghi token, private key, password hoặc payload chứa dữ liệu nhạy cảm. Dùng correlation ID để nối các sự kiện qua nhiều replica.

### 12.2. Metric

Các metric gợi ý:

| Metric | Mục đích |
|---|---|
| restored_replica_count | Số replica restore từ một image |
| replica_identity_collision_total | Số collision identity được phát hiện |
| business_id_collision_total | Số duplicate business ID |
| idempotency_replay_total | Số lần request cùng key được replay |
| duplicate_effect_prevented_total | Số side effect trùng được chặn |
| message_redelivery_total | Số message được giao lại |
| duplicate_message_suppressed_total | Số message trùng được deduplicate |
| job_claim_conflict_total | Số xung đột claim job |
| stale_fencing_write_rejected_total | Số write dùng fencing token cũ bị từ chối |
| restore_to_ready_seconds | Thời gian từ restore tới readiness |

Đây là tên metric gợi ý. Không đưa UUID, user ID hoặc operation ID vào label có cardinality cao; giữ các giá trị đó trong log/trace hoặc test artifact.

### 12.3. Bằng chứng từ hệ thống có thẩm quyền

Ưu tiên kiểm tra:

- Database unique constraint và số business record.
- Idempotency table và provider effect ledger.
- Broker offset, acknowledgment, group membership và redelivery.
- Coordinator lease owner và fencing generation.
- Registry record của các replica.
- File identity, path và nội dung sau restore.
- Readiness state và request routing.

Log của ứng dụng là bằng chứng hữu ích nhưng không thay thế trạng thái đã commit ở hệ thống ngoài. Một log “payment success” không chứng minh provider chỉ thực hiện payment một lần.

## 13. Phân tầng kiểm thử

### 13.1. Unit test

Kiểm tra logic cấp ID, idempotency và callback:

- Identity được tạo ở đúng lifecycle.
- Retry giữ nguyên operation key.
- Resource không đăng ký hoặc khởi động worker trùng.
- Callback có thể được gọi theo chu trình mà không rò rỉ.
- Lỗi allocator hoặc coordinator làm instance chưa sẵn sàng.

Unit test có thể dùng fake clock, fake ID allocator và mock provider để kiểm tra ranh giới logic.

### 13.2. Integration test với nhiều JVM

Chạy ít nhất hai process thật từ cùng checkpoint image. Đây là tầng cần thiết để phát hiện trạng thái heap bị nhân bản. Dùng database và broker dùng chung để quan sát xung đột.

### 13.3. End-to-end test

Gửi request qua load balancer hoặc test router để các replica nhận traffic. Kiểm tra ID, idempotency, outbox/inbox, scheduler và lease tại các hệ thống thực hoặc môi trường giả lập gần production.

### 13.4. Chaos/fault injection

Chủ động:

- Làm mất response sau khi provider đã thực hiện side effect.
- Kill replica giữa các bước publish/commit/ack.
- Làm database hoặc broker unavailable trong restore.
- Cho lease hết hạn và cấp cho replica khác.
- Làm credential hết hạn.
- Tạo race khi nhiều replica claim cùng task.
- Làm một replica restart nhiều lần.

Chỉ chạy fault injection trong môi trường kiểm thử được kiểm soát, với dữ liệu và provider giả lập hoặc tài khoản thử nghiệm.

## 14. Quy trình thực hiện một lượt kiểm thử

1. Chọn invariant và acceptance criteria cần xác minh.
2. Chuẩn bị dependency test có authoritative store và side-effect ledger.
3. Tạo một checkpoint image chuẩn.
4. Ghi digest và thông tin JDK/engine.
5. Restore N replica từ cùng image với runtime directory riêng.
6. Chờ bootstrap, thu thập application identity và readiness.
7. Kiểm tra ID cần riêng biệt và ID cần chia sẻ.
8. Đồng bộ replica bằng barrier.
9. Gửi request/message/job đồng thời theo test scenario.
10. Thực hiện retry, redelivery hoặc lease expiry nếu scenario yêu cầu.
11. Truy vấn database, broker, provider và coordinator.
12. Đánh giá từng acceptance criterion.
13. Lưu log, metric, trace, image digest và test parameters.
14. Dọn replica và tài nguyên test.
15. Lặp lại với số replica, thời gian dừng và failure mode khác.

## 15. Mẫu báo cáo kết quả

Một báo cáo kiểm thử nên có:

~~~text
Test run:
Checkpoint image digest:
JDK/runtime/engine:
Số replica:
Thời gian dừng:
Dependency versions:
Scenario:

Replica identities:
- test-label:
  service-id:
  replica-id:
  incarnation-id:

ID allocation:
- số ID đã tạo:
- số ID duy nhất:
- collision:
- unique constraint violation:

Side effects:
- số operation:
- số request/retry:
- số message delivery:
- số business effects:
- duplicate effect prevented:

Lease/scheduler:
- owner trước checkpoint:
- owner sau restore:
- fencing token:
- job claim:

Readiness:
- restore-to-ready duration:
- dependency failures:
- premature traffic:

Kết quả:
- PASS / FAIL / INCONCLUSIVE
Bằng chứng:
Log/metric/trace:
Lỗi và bước tái hiện:
~~~

Không ghi secret hoặc payload nhạy cảm vào báo cáo. Nếu test phát hiện duplicate, giữ lại image digest, lịch chạy, test seed, operation key đã được làm sạch và dữ liệu từ authoritative store để tái hiện.

## 16. Tiêu chí pass, fail và inconclusive

### Pass

- Các replica có identity riêng theo đúng phạm vi.
- ID nghiệp vụ không trùng theo constraint và allocator contract.
- Cùng operation key chỉ tạo một business effect.
- Message redelivery không lặp business update.
- Scheduler và worker tuân thủ single-owner hoặc partition policy.
- Lease/fencing ngăn owner cũ tiếp tục ghi.
- Readiness chỉ mở sau khi bootstrap hoàn tất.
- Có bằng chứng từ hệ thống có thẩm quyền.

### Fail

- Hai replica dùng cùng instance ID khi ID phải duy nhất.
- Business ID collision bị bỏ qua hoặc ghi đè.
- Một operation tạo nhiều payment, order, email hoặc side effect không được phép.
- Consumer acknowledgment xảy ra trước commit hoặc message lặp tạo nhiều business update.
- Nhiều replica cùng chạy một job single-owner.
- Replica cũ ghi được bằng lease/fencing token đã hết hiệu lực.
- Instance nhận traffic trước khi identity, credential hoặc dependency sẵn sàng.

### Inconclusive

- Test chỉ kiểm tra log mà không xác minh authoritative store.
- Chỉ có một replica restore.
- Không chứng minh các replica dùng cùng checkpoint image.
- Không đồng bộ thao tác nên race condition chưa thực sự được thử.
- Provider giả lập không phản ánh idempotency contract cần kiểm tra.
- Test dừng trước khi quan sát được kết quả commit/ack.

Không đánh dấu pass chỉ vì không nhìn thấy exception. Một duplicate có thể đã được ghi vào hệ thống ngoài mà ứng dụng không báo lỗi.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách kiểm thử đúng |
|---|---|---|
| Restore mỗi replica từ một image khác | Không phát hiện trạng thái heap bị nhân bản | Dùng cùng image digest |
| Chạy replica tuần tự | Race condition khó xuất hiện | Dùng barrier và thao tác đồng thời |
| Chỉ kiểm tra instance ID trong log | Có thể bỏ sót ID được dùng ở database/broker | Kiểm tra registry và unique constraint |
| Dùng ID mới cho mỗi retry | Cùng operation bị xem là thao tác mới | Giữ idempotency key ổn định |
| Chỉ kiểm tra số lần gọi API | Có thể provider deduplicate đúng hoặc sai theo contract | Kiểm tra business effect thực tế |
| Giả định broker exactly-once | Message redelivery vẫn có thể xảy ra tùy semantics | Test idempotent consumer và inbox/outbox |
| Dùng synchronized để bảo vệ nhiều JVM | Lock chỉ có phạm vi một process | Dùng database/coordinator/lease |
| Dựa vào leader boolean trong heap | Replica cũ có thể tiếp tục làm leader | Test lease expiry và fencing |
| Chỉ chạy một lần | Không phát hiện lỗi phụ thuộc lịch chạy | Lặp nhiều lượt và thay đổi concurrency |
| Chỉ dùng simulator callback | Không kiểm tra nhiều process và runtime thật | Restore nhiều JVM từ checkpoint thật |
| Không kiểm tra thời hạn deduplication | Retry muộn có thể lặp side effect | Dừng lâu hơn retry/retention window |
| Không kiểm tra restore lặp lại | Resource và ID có thể rò rỉ hoặc tái sử dụng sai | Chạy nhiều chu kỳ checkpoint/restore |

## 18. Checklist triển khai

### Môi trường

- [ ] Tạo một checkpoint image chuẩn và ghi digest.
- [ ] Dùng cùng image cho tất cả replica trong một test run.
- [ ] Mỗi replica có process/container và writable runtime state riêng.
- [ ] Có database, broker, coordinator hoặc provider giả lập dùng chung để quan sát.
- [ ] Có test barrier để đồng bộ thao tác.

### Identity và ID

- [ ] Phân biệt service, workload, replica, incarnation và business ID.
- [ ] Kiểm tra replica identity sau restore.
- [ ] Kiểm tra static counter và sequence.
- [ ] Kiểm tra UUID/SecureRandom theo provider thực tế.
- [ ] Kiểm tra Snowflake/node ID nếu có.
- [ ] Kiểm tra consumer member ID.
- [ ] Kiểm tra local file/socket path và port.
- [ ] Dùng unique constraint hoặc allocator có thẩm quyền.

### Side effect

- [ ] Xác định side effect và operation identity.
- [ ] Giữ idempotency key ổn định qua retry.
- [ ] Kiểm tra payment/API provider bằng effect ledger.
- [ ] Kiểm tra outbox publisher khi response bị mất.
- [ ] Kiểm tra inbox/deduplication khi message redelivery.
- [ ] Kiểm tra scheduler/job claim và lease.
- [ ] Kiểm tra fencing token khi owner cũ restore.

### Concurrency và failure

- [ ] Restore hai hoặc nhiều replica đồng thời.
- [ ] Lặp lại test với nhiều lượt và thời gian dừng khác nhau.
- [ ] Làm mất response sau side effect.
- [ ] Kill replica ở ranh giới commit/publish/ack.
- [ ] Cho lease/token hết hạn.
- [ ] Làm dependency unavailable trong bootstrap.
- [ ] Kiểm tra readiness không mở sớm.

### Bằng chứng

- [ ] Lưu image digest và runtime version.
- [ ] Lưu test run ID và replica mapping.
- [ ] Kiểm tra authoritative database/broker/provider/coordinator.
- [ ] Thu thập log, metric và trace theo incarnation.
- [ ] Báo cáo PASS/FAIL/INCONCLUSIVE theo từng acceptance criterion.

## 19. Nguyên tắc cần nhớ

- Dùng cùng một checkpoint image để phát hiện trạng thái heap bị nhân bản giữa các replica.
- Restore nhiều tiến trình thật và đồng bộ thời điểm thao tác để tạo race condition.
- Service identity có thể giống nhau; replica identity và incarnation ID phải tuân theo phạm vi duy nhất.
- Không dùng counter cục bộ được snapshot làm nguồn cấp ID toàn cục.
- Kiểm tra random generator, Snowflake/node ID và consumer member identity trên đúng runtime.
- Dùng unique constraint hoặc allocator có thẩm quyền để phát hiện và ngăn ID collision.
- Giữ idempotency key ổn định cho cùng một operation qua retry và restore.
- Kết hợp outbox/inbox, deduplication và acknowledgment đúng thứ tự để xử lý redelivery.
- Kiểm thử scheduler, lease và fencing token vì nhiều replica có thể cùng khôi phục một lịch hoặc trạng thái leader.
- Xác minh business effect tại database, broker hoặc provider, không chỉ dựa vào log.
- Lặp test với nhiều replica, nhiều lần restore, thời gian dừng và failure mode khác nhau.
- Chỉ kết luận pass khi có bằng chứng rằng identity, ID và side effect tuân thủ invariant.

Kiểm thử nhiều bản sao từ cùng checkpoint giúp phát hiện những lỗi mà một lần restore đơn lẻ không thể bộc lộ. Khi test đồng thời identity, ID nghiệp vụ, idempotency, message delivery, scheduler và lease tại các hệ thống có thẩm quyền, nhóm phát triển có thể chứng minh các replica hoạt động độc lập mà vẫn giữ đúng một kết quả nghiệp vụ cho mỗi thao tác được định nghĩa là duy nhất.
