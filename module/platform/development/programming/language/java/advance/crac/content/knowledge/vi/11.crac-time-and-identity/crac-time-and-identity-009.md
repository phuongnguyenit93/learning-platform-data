# Lease, khóa phân tán và nhiệm kỳ chủ sở hữu đã hết hiệu lực

Trong một hệ thống Java chạy nhiều replica, đôi khi chỉ một tiến trình được phép thực hiện một công việc tại một thời điểm. Ví dụ: một replica chạy tác vụ tổng hợp dữ liệu, một worker sở hữu partition, một tiến trình thực hiện migration, hoặc một scheduler phát hành báo cáo định kỳ. Khi nhiều instance cùng chạy, hệ thống cần cơ chế phối hợp để xác định ai đang có quyền sở hữu công việc.

Khóa phân tán (*distributed lock*) thường được dùng để bảo đảm chỉ một bên được quyền thực hiện một vùng công việc. Lease là một dạng quyền sở hữu có thời hạn: chủ sở hữu phải gia hạn trước khi hết hạn; nếu không, hệ thống có thể cấp quyền cho tiến trình khác. Tuy nhiên, lease hết hạn không tự động ngăn tiến trình cũ tiếp tục chạy. Một tiến trình bị treo, mất kết nối hoặc bị checkpoint có thể thức dậy sau khi quyền sở hữu đã được chuyển cho instance khác.

Đây là vấn đề đặc biệt quan trọng với CRaC (Coordinated Restore at Checkpoint). Tiến trình có thể được checkpoint trong lúc đang giữ lease, sau đó nằm yên lâu hơn thời hạn lease. Trong thời gian đó, lease có thể hết hạn và một replica khác có thể trở thành owner mới. Khi tiến trình cũ được restore, các biến trong heap vẫn có thể ghi nhớ rằng nó từng là owner. Nếu tiến trình tiếp tục ghi dữ liệu hoặc thực hiện side effect dựa trên thông tin cũ, hai owner có thể cùng hành động.

Thiết kế an toàn cần coi lease là quyền có thời hạn được xác nhận bởi hệ thống phối hợp, dùng fencing token hoặc owner epoch để từ chối thao tác của owner cũ, và yêu cầu tiến trình restore xác nhận hoặc giành lại quyền sở hữu trước khi làm việc.

## 1. Khóa phân tán giải quyết vấn đề gì?

Trong một JVM đơn lẻ, synchronized, ReentrantLock hoặc Semaphore có thể điều phối các thread cùng tiến trình. Nhưng nếu ứng dụng chạy trên nhiều máy hoặc nhiều container, mỗi tiến trình có bộ nhớ riêng. Một synchronized trong replica A không ngăn replica B vào cùng vùng logic.

Ví dụ, một dịch vụ có ba replica A, B và C. Tất cả cùng kiểm tra xem có cần chạy tác vụ đóng sổ cuối ngày hay không. Nếu chỉ dùng biến boolean isRunning trong heap, mỗi tiến trình có một bản sao riêng và cả ba có thể cùng thấy false, rồi cùng chạy tác vụ.

Khóa phân tán cung cấp một điểm phối hợp chung để các tiến trình tranh quyền. Một giao thức khóa thường có các thao tác:

- Acquire: yêu cầu quyền sở hữu nếu chưa có owner hợp lệ.
- Renew: gia hạn quyền sở hữu đang có.
- Release: giải phóng quyền sở hữu.
- Validate: xác nhận quyền sở hữu còn hiệu lực.
- Expire: hệ thống phối hợp tự hết hạn quyền sở hữu sau một khoảng thời gian nếu không được gia hạn.

Khóa phân tán không phải chỉ là một biến có tên locked. Nó cần một giao thức nguyên tử ở nơi lưu trạng thái chung, cùng quy tắc về timeout, gia hạn, lỗi mạng và quyền thực hiện side effect.

## 2. Lease là gì?

Lease là quyền sở hữu có thời hạn do một hệ thống phối hợp cấp. Khi client nhận lease, nó có quyền thực hiện một công việc trong khoảng thời gian được cấp. Trước khi lease hết hạn, client phải gia hạn thành công. Nếu không gia hạn, quyền sở hữu hết hiệu lực và hệ thống có thể cấp lease mới cho owner khác.

Một lease thường chứa:

- Resource hoặc tên công việc được bảo vệ.
- Owner ID xác định tiến trình hoặc instance đang giữ lease.
- Lease ID hoặc token ngẫu nhiên để phân biệt lần cấp quyền.
- Thời điểm hết hạn hoặc TTL do hệ thống phối hợp quản lý.
- Revision, generation hoặc fencing token nếu hệ thống hỗ trợ.
- Thông tin phục vụ gia hạn và giải phóng.

Ví dụ, worker A lấy lease cho daily-report trong 30 giây. A phải gia hạn trước khi hết hạn. Nếu A dừng hoạt động hoặc không thể liên lạc với dịch vụ lease, quyền sở hữu hết hạn. Worker B có thể lấy lease mới và tiếp tục công việc.

~~~text
Thời gian ---------------------------------------------------->

Worker A:  Acquire lease A -------- Renew -------- Renew
Lease:     [------------------ hiệu lực ------------------]
Worker B:                                                  Acquire lease B
Lease:                                                      [--- hiệu lực ---]
~~~

TTL là khoảng thời gian sống của lease. TTL ngắn giúp phát hiện owner mất hoạt động nhanh hơn nhưng tăng tần suất renew và nhạy cảm với độ trễ mạng. TTL dài giảm chi phí gia hạn nhưng làm chậm việc chuyển quyền khi owner thực sự chết.

Lease không giống một lock vô thời hạn. Với lock vô thời hạn, nếu owner chết mà không release, hệ thống có thể bị khóa mãi trừ khi có cơ chế phục hồi. Lease tự hết hạn sau một khoảng thời gian, nhưng đổi lại owner phải thường xuyên chứng minh quyền sở hữu vẫn còn hiệu lực.

## 3. Phân biệt lock, lease và owner

Các thuật ngữ thường được dùng lẫn nhau nhưng có ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa | Điều cần chú ý |
|---|---|---|
| Lock | Quyền loại trừ tương hỗ đối với một tài nguyên hoặc vùng công việc | Phải có quy tắc acquire/release và xử lý owner lỗi |
| Lease | Quyền sở hữu có thời hạn | Có thể hết hạn khi client bị pause hoặc mất kết nối |
| Owner | Tiến trình hoặc chủ thể hiện đang được hệ thống công nhận có quyền | Owner trong heap có thể đã cũ so với trạng thái trung tâm |
| Lease ID | Định danh của một lần cấp lease | Dùng để renew/release đúng lease |
| Owner epoch / generation | Số thế hệ tăng theo mỗi lần chuyển quyền | Giúp phân biệt owner mới với owner cũ |
| Fencing token | Token có thứ tự tăng, gắn với quyền sở hữu | Hệ thống đích có thể từ chối thao tác từ owner cũ |

Một lock chỉ hữu ích nếu mọi bên cùng tuân thủ giao thức. Nếu một tiến trình giữ biến isOwner = true trong bộ nhớ nhưng lease đã hết hạn ở hệ thống trung tâm, biến đó không còn là bằng chứng về quyền sở hữu.

## 4. Vì sao lease cần TTL?

Trong môi trường phân tán, client có thể chết, mất mạng hoặc bị dừng ngoài dự kiến. Nếu chỉ dựa vào thao tác release tường minh, một lock có thể bị bỏ lại sau sự cố.

TTL cho phép hệ thống phối hợp tự thu hồi quyền sau một khoảng thời gian. Owner phải renew định kỳ để chứng minh nó vẫn hoạt động và vẫn muốn giữ quyền.

Ví dụ, với TTL 30 giây, client có thể renew mỗi 10 giây. Đây chỉ là cấu hình minh họa; chu kỳ renew cần tính đến latency, jitter, thời gian GC pause, tải hệ thống và độ tin cậy của dịch vụ lease.

Một số nguyên tắc:

- Renew trước khi còn quá ít thời gian.
- Dùng timeout cho mỗi lần renew.
- Không coi timeout là renew thành công.
- Nếu không thể xác nhận renew thành công, dừng bắt đầu công việc mới.
- Không chờ đến sát thời điểm hết hạn mới xử lý lỗi.
- Sau khi restore, xác minh lease ở hệ thống trung tâm thay vì dựa vào timestamp cũ trong heap.

TTL không bảo đảm rằng owner cũ đã dừng chạy khi lease hết hạn. Nó chỉ cho phép hệ thống phối hợp cấp quyền mới. Owner cũ có thể vẫn đang chạy trong một máy bị cô lập mạng, hoặc có thể được resume sau một khoảng pause dài.

## 5. Khóa phân tán không tự ngăn owner cũ hoạt động

Hãy xem tình huống:

1. Worker A lấy lease và bắt đầu xử lý partition 7.
2. A bị pause dài do stop-the-world, treo máy ảo, mất kết nối hoặc được checkpoint.
3. A không renew được lease.
4. TTL hết hạn.
5. Worker B lấy lease mới cho partition 7 và bắt đầu xử lý.
6. A được resume hoặc restore và tiếp tục từ lệnh kế tiếp trong bộ nhớ.

Tại thời điểm này, A có thể vẫn tin rằng nó là owner vì biến trong heap chưa được cập nhật. B cũng đang là owner hợp lệ theo hệ thống phối hợp. Nếu cả hai cùng ghi vào database hoặc phát message, hệ thống có thể gặp ghi đè, mất cập nhật hoặc xử lý trùng.

~~~text
Thời gian ---------------------------------------------------------->

A:  Acquire A ---- làm việc ---- CHECKPOINT/PAUSE ------------ RESTORE -- ghi tiếp
Lease A:           [---------- hết hạn ----------------]
B:                                            Acquire B ---- làm việc ---->
Lease B:                                         [----------- hiệu lực ---->

Rủi ro: A tiếp tục ghi sau khi B đã trở thành owner mới.
~~~

Đây là tình huống stale owner (*chủ sở hữu cũ đã hết hiệu lực*). Một distributed lock dựa trên TTL mà không có cách bảo vệ hệ thống đích trước stale owner có thể chưa đủ để bảo đảm tính đúng đắn.

## 6. CRaC làm rủi ro stale lease rõ ràng hơn

CRaC cho phép lưu trạng thái tiến trình tại checkpoint rồi restore sau đó. Một tiến trình có thể được chuẩn bị, checkpoint, lưu ảnh trong kho artifact và chỉ restore nhiều phút hoặc nhiều giờ sau. Trong thời gian đó, lease cũ chắc chắn có thể hết hạn.

Các giá trị trong heap có thể vẫn phản ánh thời điểm trước checkpoint:

- owner = true.
- leaseId của lần acquire cũ.
- leaseExpiresAt cũ.
- lastRenewal cũ.
- fencingToken cũ.
- Bộ đếm hoặc trạng thái tác vụ đang chạy.
- Thread nền đang chờ và sẽ tiếp tục khi tiến trình được khôi phục.

Không nên xem các giá trị này là bằng chứng về quyền hiện tại. Chúng chỉ là dữ liệu lịch sử của tiến trình tại thời điểm checkpoint.

Đặc biệt, không nên đưa một tiến trình vào checkpoint khi nó vẫn giữ lease cho công việc cần độc quyền. Trước checkpoint, ứng dụng nên dừng nhận công việc, hoàn tất hoặc tạm dừng tại ranh giới an toàn, từ bỏ lease theo giao thức và xác nhận trạng thái bền vững. Sau restore, tiến trình phải acquire lease mới hoặc xác minh một lease mới được cấp cho đúng lần chạy hiện tại.

Nếu checkpoint là ảnh dùng chung để tạo nhiều instance, không được mang lease ID hoặc owner identity của tiến trình chuẩn bị sang mọi replica. Mỗi instance phải có danh tính riêng và giành quyền theo cơ chế phối hợp khi cần.

## 7. Fencing token là gì?

Fencing token là một giá trị có thứ tự tăng được cấp mỗi lần quyền sở hữu được chuyển giao. Nó cho phép hệ thống đích nhận biết thao tác đến từ owner mới hay owner cũ.

Giả sử hệ thống cấp các token:

- Worker A nhận token 41.
- Lease A hết hạn.
- Worker B nhận token 42.
- A được resume và gửi một thao tác với token 41.
- B gửi thao tác với token 42.

Nếu hệ thống đích chỉ chấp nhận token lớn hơn hoặc bằng token mới nhất đã ghi nhận, thao tác của A sẽ bị từ chối vì 41 nhỏ hơn 42.

~~~text
Lease service:
  A acquires resource -> token 41
  A expires
  B acquires resource -> token 42

Protected database:
  highest token = 42

Request from A (token 41) -> REJECTED
Request from B (token 42) -> ACCEPTED
~~~

Fencing token phải được kiểm tra tại nơi thực hiện side effect, chẳng hạn database, storage service hoặc API bảo vệ tài nguyên. Chỉ cấp token ở lock service nhưng không truyền và kiểm tra nó ở hệ thống đích thì không bảo vệ được dữ liệu.

Một UUID ngẫu nhiên có thể nhận diện lease nhưng không có thứ tự. Nó không thay thế fencing token nếu cần biết owner nào mới hơn. Fencing token cần được cấp theo thứ tự đơn điệu bởi một nguồn có tính nhất quán phù hợp.

## 8. Owner epoch và nhiệm kỳ chủ sở hữu

Một owner epoch (còn gọi generation hoặc term) là số thế hệ gắn với quyền sở hữu. Mỗi lần quyền được cấp mới hoặc chuyển owner, hệ thống tăng epoch.

Ví dụ:

| Lần cấp quyền | Owner | Epoch |
|---|---|---:|
| Lần 1 | worker-A | 101 |
| Lần 2 | worker-B | 102 |
| Lần 3 | worker-C | 103 |

Epoch giúp phân biệt hai lần chạy của cùng một instance. Ví dụ, container worker-A có thể restart hoặc restore; lần chạy mới vẫn có cùng tên instance nhưng phải nhận epoch mới. Không dùng hostname hoặc pod name làm bằng chứng rằng đó là cùng một nhiệm kỳ quyền sở hữu.

Một số hệ thống lưu epoch ở database hoặc metadata service. Mỗi thao tác ghi cần kèm epoch và bị từ chối nếu epoch thấp hơn giá trị hiện hành. Với một resource có nhiều owner, epoch cần có phạm vi rõ ràng, ví dụ theo resource key hoặc partition.

## 9. Bảo vệ database bằng fencing token

Có thể lưu token lớn nhất được chấp nhận cùng bản ghi trạng thái của resource. Mỗi thao tác ghi cần gửi token. Database chỉ cho phép thao tác nếu token không cũ hơn token đã được chấp nhận.

Ví dụ bảng trạng thái:

~~~sql
CREATE TABLE resource_owner (
    resource_key VARCHAR(200) PRIMARY KEY,
    fencing_token BIGINT NOT NULL,
    payload      VARCHAR(2000)
);
~~~

Một thao tác cập nhật có thể kiểm tra token trong cùng transaction:

~~~sql
UPDATE resource_owner
SET payload = :payload
WHERE resource_key = :resourceKey
  AND fencing_token <= :token;
~~~

Tuy nhiên, điều kiện trên một mình có thể chưa đủ nếu thao tác không đồng thời cập nhật fencing_token lên token mới. Một cách là cập nhật token và payload trong cùng câu lệnh/transaction:

~~~sql
UPDATE resource_owner
SET fencing_token = :token,
    payload = :payload
WHERE resource_key = :resourceKey
  AND fencing_token <= :token;
~~~

Nếu số hàng được cập nhật bằng 0, token đã cũ hoặc resource không tồn tại. Ứng dụng cần coi đây là lỗi mất quyền sở hữu và dừng xử lý.

Trong hệ thống nhiều thao tác, nên có một bảng fencing riêng hoặc một row đại diện cho resource. Cần bảo đảm thao tác kiểm tra token và side effect được thực hiện nguyên tử trong cùng transaction. Nếu ứng dụng kiểm tra token trước rồi cập nhật dữ liệu trong một transaction khác, owner cũ có thể chen vào giữa hai bước.

Ví dụ logic JDBC:

~~~java
public void writeWithFence(
        Connection connection,
        String resourceKey,
        long fencingToken,
        String payload) throws SQLException {

    String sql = """
        UPDATE resource_owner
           SET fencing_token = ?,
               payload = ?
         WHERE resource_key = ?
           AND fencing_token <= ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, fencingToken);
        statement.setString(2, payload);
        statement.setString(3, resourceKey);
        statement.setLong(4, fencingToken);

        int updated = statement.executeUpdate();
        if (updated != 1) {
            throw new StaleOwnerException(
                    "Lease owner is stale for " + resourceKey);
        }
    }
}
~~~

Đây là minh họa cho một hàng trạng thái được bảo vệ. Nếu thao tác thực tế ghi vào nhiều bảng, các cập nhật cần cùng transaction và cùng điều kiện fencing. Cũng cần định nghĩa cách khởi tạo hàng, cách serialize các thao tác cạnh tranh và cách xử lý token bằng nhau theo giao thức.

## 10. Tạo token tăng đơn điệu

Fencing token phải được cấp theo thứ tự. Có thể dùng sequence của database, revision của một kho dữ liệu nhất quán hoặc số phiên do hệ thống điều phối cung cấp.

Ví dụ với sequence trong database:

~~~sql
CREATE SEQUENCE lease_fencing_seq START WITH 1 INCREMENT BY 1;
~~~

Khi cấp lease mới, coordinator lấy một giá trị sequence mới và gắn nó với lease. Token được trả cho owner cùng lease ID.

Không nên tự tăng token trong biến AtomicLong của từng JVM vì mỗi replica có bộ đếm riêng. Cũng không nên dùng timestamp cục bộ làm token nếu đồng hồ các node có thể lệch hoặc quay lùi. Token cần được cấp từ nguồn chung có thứ tự và tính nhất quán phù hợp.

Nếu dùng revision hoặc transaction ID từ hệ thống điều phối, hãy xác minh rằng giá trị đó tăng theo đúng phạm vi resource. Một revision toàn cục có thể phù hợp; một version chỉ tăng trong từng key cũng có thể phù hợp nếu hệ thống đích so sánh theo đúng key.

## 11. Mẫu acquire/renew/release an toàn

Một lease client nên cung cấp API rõ ràng và không để mã nghiệp vụ tự thao tác các lệnh rời rạc. Mô hình khái quát:

~~~java
public interface LeaseService {
    Lease acquire(String resourceKey, Duration ttl);
    Lease renew(Lease lease, Duration ttl);
    void release(Lease lease);
    Lease current(String resourceKey);
}

public record Lease(
        String resourceKey,
        String ownerId,
        String leaseId,
        long fencingToken,
        Instant expiresAt) {
}
~~~

Đây là interface minh họa do ứng dụng định nghĩa, không phải API chuẩn của Java hoặc CRaC. acquire() phải thực hiện cấp quyền một cách nguyên tử. Nếu resource đang có lease hợp lệ, nó phải trả về kết quả không có quyền hoặc một lỗi tương ứng. renew() và release() cần xác minh lease ID/owner token để một client cũ không vô tình gia hạn hoặc xóa lease của owner mới.

Release nên có điều kiện. Không được xóa khóa chỉ dựa trên resource key vì lease mới có thể đã được cấp cho owner khác. Cần so sánh lease ID hoặc owner token hiện tại trước khi release.

Một lease object trong heap chỉ là bản sao thông tin được cấp trước đó. Trước mỗi thao tác quan trọng, hệ thống cần áp dụng fencing ở đích hoặc xác minh quyền theo giao thức. Không nên coi việc có một object Lease còn trong bộ nhớ là đủ.

## 12. Ví dụ dùng lease với fencing token trong Java

Một service xử lý partition có thể nhận lease và dùng token trong mọi lần ghi:

~~~java
public final class PartitionWorker {
    private final LeaseService leases;
    private final PartitionStore store;
    private final String ownerId;

    public PartitionWorker(
            LeaseService leases,
            PartitionStore store,
            String ownerId) {
        this.leases = leases;
        this.store = store;
        this.ownerId = ownerId;
    }

    public void runPartition(String partition) {
        Lease lease = leases.acquire(partition, Duration.ofSeconds(30));
        if (lease == null) {
            return;
        }

        try {
            processRecords(partition, lease.fencingToken());
        } finally {
            leases.release(lease);
        }
    }

    private void processRecords(String partition, long token) {
        for (Record record : loadPendingRecords(partition)) {
            store.apply(partition, token, record);
        }
    }
}
~~~

Trong ví dụ, PartitionStore.apply() phải kiểm tra token tại nơi lưu trạng thái. Nếu token đã cũ, nó phải từ chối thao tác. Chỉ kiểm tra token một lần ở đầu runPartition() là chưa đủ: lease có thể hết hạn giữa lúc xử lý nhiều record.

Một worker thực tế cũng cần renew lease trong lúc chạy. Nếu renew thất bại hoặc kết quả không xác định, worker nên dừng nhận record mới và không phát sinh thêm side effect. Nếu một thao tác đang diễn ra, hệ thống đích vẫn phải kiểm tra fencing token để ngăn stale owner.

## 13. Gia hạn lease và xử lý lỗi renew

Lease thường được renew định kỳ. Client không nên xem renew là một tác vụ phụ có thể thất bại mà vẫn tiếp tục làm việc vô hạn.

Một vòng renew có thể được tổ chức như sau:

1. Nhận lease có TTL từ hệ thống phối hợp.
2. Lên lịch renew với khoảng an toàn trước thời điểm hết hạn.
3. Gửi renew với lease ID hiện tại.
4. Nếu renew được xác nhận, cập nhật trạng thái và thời hạn.
5. Nếu renew bị từ chối vì lease không còn thuộc owner, đánh dấu mất quyền.
6. Nếu timeout hoặc mất kết nối, coi trạng thái quyền sở hữu là không chắc chắn và ngừng bắt đầu side effect mới.
7. Chỉ tiếp tục khi hệ thống phối hợp xác nhận lease còn hợp lệ hoặc cấp lease mới.

Không phải mọi lỗi renew đều có nghĩa lease chắc chắn đã hết hạn. Ví dụ, response có thể bị mất sau khi server đã gia hạn. Nhưng client không thể tự suy đoán rằng renew thành công. Cần query trạng thái hoặc thực hiện giao thức khôi phục an toàn. Trong lúc chưa xác nhận, hãy dừng công việc cần độc quyền.

Một ScheduledExecutorService có thể chạy renew loop, nhưng cần tính đến thread bị pause, GC pause, tải CPU, mạng chậm và checkpoint. Không nên chỉ đặt lịch renew mỗi 10 giây rồi giả định callback chắc chắn chạy đúng thời điểm.

## 14. Đồng hồ, TTL và thời gian sau checkpoint

Lease dựa trên thời gian nhưng các máy không nhất thiết có đồng hồ giống nhau. System.currentTimeMillis() là đồng hồ wall-clock có thể thay đổi do NTP hoặc thao tác quản trị. System.nanoTime() phù hợp để đo khoảng thời gian trong một JVM đang chạy, nhưng giá trị của nó là mốc tùy ý và không phải timestamp toàn cục để lưu lâu dài hoặc so sánh giữa máy.

Một số nguyên tắc:

- Để hệ thống lease có thẩm quyền quyết định lease đã hết hạn hay chưa.
- Không dùng timestamp do client tự tạo làm nguồn duy nhất để cấp quyền.
- Không lưu một deadline trong heap rồi tin nó còn chính xác sau một thời gian checkpoint không xác định.
- Dùng đồng hồ monotonic cho timeout nội bộ trong một khoảng thực thi phù hợp; không dùng nó làm token hoặc timestamp phân tán.
- Sau restore, đọc lại trạng thái lease từ hệ thống phối hợp và acquire hoặc renew theo giao thức.
- Tính đến clock skew nếu giao thức yêu cầu client tự ước lượng thời hạn; giữ safety margin đủ lớn.

Nếu một tiến trình checkpoint trong 20 phút trong khi lease TTL là 30 giây, lease đã hết hạn từ lâu theo hệ thống phối hợp. Không có cách nào suy ra quyền sở hữu còn hiệu lực chỉ bằng một biến expiresAt được khôi phục từ heap.

## 15. Chuẩn bị checkpoint khi đang giữ lease

Cách đơn giản và an toàn nhất cho nhiều workload là không tạo checkpoint khi tiến trình còn sở hữu lease cho một công việc độc quyền. Trước checkpoint, ứng dụng có thể:

1. Ngừng nhận công việc mới.
2. Dừng phân phối record hoặc tác vụ mới cho worker.
3. Chờ công việc đang chạy hoàn tất tại ranh giới an toàn.
4. Commit tiến độ hoặc lưu checkpoint nghiệp vụ riêng của workload.
5. Từ bỏ lease bằng release có điều kiện.
6. Xác nhận không còn worker nào được phép thực hiện side effect.
7. Cho phép CRaC tạo checkpoint.

Sau restore, tiến trình không được tự tiếp tục bằng lease ID cũ. Nó cần đăng ký identity hiện tại, acquire lease mới và nhận fencing token mới. Chỉ sau khi có quyền hợp lệ mới được bắt đầu công việc.

Nếu workload không thể dừng hoàn toàn, cần thiết kế một giao thức pause/resume có khả năng khôi phục. Tuy nhiên, pause tiến trình bằng checkpoint không phải là cơ chế lease. Hệ thống phối hợp bên ngoài vẫn tiếp tục tính TTL trong khi tiến trình không chạy.

## 16. Dùng CRaC Resource để nhả và lấy lại lease

Có thể dùng CRaC Resource để phối hợp vòng đời lease. Callback trước checkpoint yêu cầu worker dừng công việc và nhả lease. Callback sau restore chuẩn bị trạng thái mới; việc acquire lease có thể được thực hiện sau khi dependency và identity đã sẵn sàng.

Ví dụ:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class LeaseCheckpointResource implements Resource {
    private final LeaseCoordinator coordinator;

    public LeaseCheckpointResource(LeaseCoordinator coordinator) {
        this.coordinator = coordinator;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        coordinator.stopClaimingWork();
        coordinator.drainInFlightOperations();
        coordinator.persistProgress();
        coordinator.releaseCurrentLease();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        coordinator.refreshInstanceIdentity();
        coordinator.clearRestoredLeaseState();
        coordinator.prepareForNewLease();
    }

    public interface LeaseCoordinator {
        void stopClaimingWork() throws Exception;
        void drainInFlightOperations() throws Exception;
        void persistProgress() throws Exception;
        void releaseCurrentLease() throws Exception;
        void refreshInstanceIdentity() throws Exception;
        void clearRestoredLeaseState() throws Exception;
        void prepareForNewLease() throws Exception;
    }
}
~~~

Các phương thức LeaseCoordinator là hợp đồng ứng dụng tự định nghĩa, không phải API CRaC. Ví dụ cố ý chưa acquire lease trong afterRestore() vì nhiều ứng dụng cần đợi service discovery, database, credential hoặc worker pool sẵn sàng trước. Một lifecycle coordinator có thể acquire lease sau khi các dependency được phục hồi và trước khi mở traffic cho workload.

Nếu beforeCheckpoint() không thể drain công việc hoặc release lease, callback cần báo lỗi để quy trình checkpoint không tiếp tục trong trạng thái không rõ ràng. Nếu restore không lấy được lease, instance vẫn có thể chạy web health endpoint nhưng không được nhận phần công việc đòi hỏi quyền owner. Readiness cần phản ánh đúng vai trò đó.

## 17. Tạo checkpoint từ một tiến trình chuẩn bị và restore nhiều replica

Một ảnh checkpoint có thể được dùng làm điểm xuất phát cho nhiều instance nếu JDK và nền tảng hỗ trợ mô hình đó. Tuy nhiên, ảnh không nên chứa lease đang hoạt động hoặc owner identity của tiến trình chuẩn bị.

Giả sử tiến trình chuẩn bị có lease cho scheduler-global với token 500. Nếu ảnh được restore thành 10 replica, cả 10 tiến trình có thể bắt đầu với cùng giá trị token 500 trong heap. Chúng không được xem đó là 10 lease hợp lệ. Lease ban đầu chỉ được cấp cho một owner tại một thời điểm và có thể đã hết hạn trước khi ảnh được dùng.

Thiết kế phù hợp:

- Không acquire lease trong giai đoạn tạo ảnh nền.
- Nếu ứng dụng cần chạy warm-up cho một thành phần độc quyền, dùng môi trường hoặc resource riêng không gây side effect sản xuất.
- Xóa trạng thái owner/lease khỏi cấu hình nền trước checkpoint.
- Mỗi replica tạo owner ID riêng sau restore.
- Mỗi replica chỉ xử lý công việc sau khi acquire lease hợp lệ.
- Mọi thao tác ghi đều mang fencing token được cấp cho lần sở hữu hiện tại.
- Nếu chỉ một replica được phép chạy tác vụ toàn cục, các replica còn lại chờ lease thay vì tự chạy dựa trên biến heap.

Đối với worker xử lý partition, nhiều replica có thể cùng chạy nhưng chỉ owner của từng partition mới được xử lý partition đó. Lease và token cần có phạm vi theo partition; không nên dùng một biến global để đại diện quyền sở hữu toàn bộ workload nếu giao thức phân chia quyền theo key.

## 18. Các hệ thống thường dùng để triển khai lease

Lease có thể được xây dựng trên nhiều hệ thống lưu trữ hoặc điều phối. Mỗi hệ thống có bảo đảm và giới hạn riêng.

| Nền tảng | Cách triển khai thường gặp | Điểm cần xác minh |
|---|---|---|
| Database quan hệ | Row lock, advisory lock, lease row có expires_at và version | Transaction boundary, isolation, thời gian server, atomic update, fencing |
| Redis | SET NX với TTL, token sở hữu và thao tác compare-and-delete | Failover/replication, mất lock khi chuyển primary, fencing token riêng |
| ZooKeeper | Ephemeral node và version/zxid | Session expiration, watcher, reconnect, generation |
| etcd | Lease gắn key và revision | Lease revoke/expiry, revision, quorum và retry |
| Consul | Session và lock delay | Session invalidation, behavior khi mất kết nối, fencing ở đích |
| Kubernetes | Lease object trong coordination API | Renewal deadline, resourceVersion, leader election, fencing trong hệ thống đích |

Không có một lựa chọn nào tự động bảo vệ mọi side effect. Hãy đọc tài liệu của phiên bản nền tảng, hiểu consistency model, failover behavior và giới hạn khi network partition. Một distributed lock service có thể cấp lease mới trong khi owner cũ vẫn còn chạy; fencing tại hệ thống đích vẫn là lớp bảo vệ quan trọng.

## 19. Ví dụ lease bằng database

Một cách đơn giản là lưu resource key, owner ID, expiration và fencing token trong một bảng. Acquire cần thực hiện nguyên tử: chỉ chiếm quyền nếu lease hiện tại đã hết hạn hoặc chưa có owner. Mỗi lần cấp mới phải tăng token.

Bảng minh họa:

~~~sql
CREATE TABLE distributed_lease (
    resource_key  VARCHAR(200) PRIMARY KEY,
    owner_id      VARCHAR(200),
    lease_id      VARCHAR(200),
    expires_at    TIMESTAMP WITH TIME ZONE,
    fencing_token BIGINT NOT NULL
);
~~~

Ý tưởng acquire trên database hỗ trợ transaction:

1. Bắt đầu transaction.
2. Khóa row tương ứng bằng SELECT ... FOR UPDATE hoặc cơ chế nguyên tử phù hợp.
3. Dùng thời gian của database để so sánh expires_at.
4. Nếu lease còn hiệu lực, không cấp quyền.
5. Nếu lease hết hạn, tăng fencing_token, gán owner_id, lease_id và expires_at mới.
6. Commit và trả token cho client.

Pseudocode SQL có thể biểu diễn bằng một câu lệnh cập nhật có điều kiện, nhưng cú pháp và hỗ trợ phụ thuộc database. Ví dụ khái quát:

~~~sql
UPDATE distributed_lease
   SET owner_id = :owner,
       lease_id = :leaseId,
       expires_at = CURRENT_TIMESTAMP + :ttl,
       fencing_token = fencing_token + 1
 WHERE resource_key = :resource
   AND (expires_at IS NULL OR expires_at <= CURRENT_TIMESTAMP);
~~~

Nếu một hàng được cập nhật, client có thể lấy token mới trong cùng transaction hoặc bằng RETURNING nếu database hỗ trợ. Nếu không có hàng nào được cập nhật, resource đang có lease còn hiệu lực hoặc key chưa được khởi tạo. Phải xử lý việc tạo row ban đầu để không có race giữa hai client cùng insert.

Renew phải kiểm tra cả owner ID và lease ID:

~~~sql
UPDATE distributed_lease
   SET expires_at = CURRENT_TIMESTAMP + :ttl
 WHERE resource_key = :resource
   AND owner_id = :owner
   AND lease_id = :leaseId
   AND expires_at > CURRENT_TIMESTAMP;
~~~

Nếu update count bằng 0, client không được coi là đã gia hạn. Release cũng phải có điều kiện tương tự và không được xóa lease của owner khác.

Đây là mô hình minh họa. Trong hệ thống thực tế, cần kiểm tra cú pháp timestamp, isolation, transaction, index, cách lấy fencing token mới và hành vi khi database failover. Dùng thời gian phía database giúp tránh việc mỗi client so sánh TTL bằng clock cục bộ khác nhau.

## 20. Redis lock và các giới hạn cần hiểu

Một pattern phổ biến với Redis là đặt key chỉ khi key chưa tồn tại và gắn TTL:

~~~text
SET lock:partition-7 <random-owner-token> NX PX 30000
~~~

NX yêu cầu chỉ đặt nếu key chưa tồn tại; PX đặt thời gian sống tính bằng millisecond. Nếu lệnh thành công, client được quyền giữ lock trong TTL theo giao thức đang dùng.

Khi release, không nên dùng DEL lock:partition-7 vô điều kiện. Owner A có thể hết hạn, B đã lấy lock mới, rồi A chạy muộn và xóa nhầm lock của B. Cần một thao tác nguyên tử chỉ xóa key nếu giá trị hiện tại vẫn bằng owner token của A, thường thực hiện bằng Lua script hoặc cơ chế compare-and-delete được hỗ trợ.

Tuy vậy, owner token ngẫu nhiên chỉ giúp release đúng lease; nó không tự ngăn A gửi thao tác ghi cũ đến database sau khi lease hết hạn. Nếu cần chống stale owner, cần fencing token tăng đơn điệu và hệ thống đích kiểm tra token. Cũng phải hiểu replication và failover của Redis: một lần ghi lock có thể chưa được nhân bản bền vững trước khi primary lỗi, tùy cấu hình. Đừng mặc định pattern đơn giản là một giao thức khóa tuyến tính mạnh trong mọi topology.

## 21. Leader election và lease

Leader election chọn một tiến trình làm leader trong một nhóm. Lease thường được dùng để giới hạn nhiệm kỳ của leader: leader phải renew, và khi lease hết hạn một thành viên khác có thể được bầu.

Tuy nhiên, leader election chỉ trả lời ai được xem là leader theo hệ thống điều phối. Nó không tự ngăn leader cũ tiếp tục phát lệnh tới hệ thống đích. Một hệ thống quan trọng nên gắn term/epoch vào mọi lệnh hoặc thao tác ghi, để downstream từ chối lệnh từ term cũ.

Ví dụ, một scheduler leader có thể phát lệnh run-job với term 77. Sau khi leader mới được bầu với term 78, database hoặc job coordinator chỉ chấp nhận term 78 trở lên. Nếu tiến trình cũ resume và phát lệnh term 77, lệnh bị từ chối.

Đối với Kubernetes Lease, resourceVersion và leader election record giúp phối hợp việc chọn leader. Nhưng ứng dụng vẫn cần thiết kế cách truyền fencing/epoch đến tài nguyên mà leader điều khiển. Không nên coi việc một pod từng giữ Lease object là bằng chứng nó vẫn có quyền sau một khoảng checkpoint dài.

## 22. Lease, distributed lock và transaction

Lock không thay thế transaction. Lock có thể ngăn hai owner hợp lệ cùng bắt đầu công việc, nhưng không bảo đảm các thao tác database bên trong được commit nguyên tử. Ngược lại, transaction database có thể bảo đảm một nhóm thao tác nguyên tử nhưng không tự điều phối quyền sở hữu một job chạy dài giữa nhiều process.

Một số cách phối hợp:

- Acquire lease trước khi bắt đầu một công việc độc quyền.
- Dùng fencing token trong các transaction cập nhật dữ liệu.
- Lưu progress và thay đổi nghiệp vụ trong cùng transaction khi có thể.
- Dùng idempotency key để xử lý retry sau kết quả không rõ ràng.
- Release lease sau khi trạng thái bền vững đã được cập nhật.
- Nếu lease hết hạn giữa transaction, fencing check ở database phải ngăn owner cũ commit side effect.

Với công việc dài, không nên giữ một transaction database mở suốt thời gian lease. Hãy chia công việc thành batch hoặc đơn vị nhỏ, mỗi batch có transaction ngắn và kiểm tra fencing token.

## 23. Quy tắc khi lease hết hạn hoặc renew không chắc chắn

Khi client không thể xác nhận lease còn hiệu lực, hành vi an toàn là ngừng bắt đầu side effect mới. Cụ thể:

1. Đánh dấu local ownership state là UNCERTAIN hoặc LOST.
2. Dừng nhận thêm record/job.
3. Hủy hoặc dừng worker theo cách an toàn.
4. Không gửi lệnh ghi mới với token cũ.
5. Nếu một thao tác đang chờ kết quả, tra cứu trạng thái bằng operation ID hoặc để cơ chế idempotency xử lý retry.
6. Khi kết nối trở lại, query hoặc acquire lease mới.
7. Chỉ tiếp tục khi có token mới và downstream chấp nhận token đó.

Không nên tự gia hạn bằng cách cộng TTL vào expiresAt trong heap. Chỉ server phối hợp mới có thể xác nhận renew. Nếu response timeout, có thể server đã renew nhưng client không nhận được; hãy query trạng thái hoặc acquire theo giao thức thay vì đoán.

## 24. Kiểm thử stale owner với checkpoint/restore

Một bài kiểm thử hữu ích phải tái hiện tình huống owner cũ được resume sau khi owner mới đã giành quyền.

Kịch bản:

1. Worker A acquire lease cho resource X và nhận fencing token 10.
2. A xử lý một vài record và ghi token 10 vào database.
3. Tạo checkpoint hoặc dừng A đủ lâu để lease hết hạn.
4. Worker B acquire lease mới và nhận token 11.
5. B ghi một thay đổi bằng token 11; database chấp nhận và lưu token mới.
6. Restore hoặc resume A.
7. A cố ghi bằng token 10.
8. Database phải từ chối thao tác của A.
9. A phải chuyển sang trạng thái mất quyền và không tiếp tục công việc.

Kiểm tra thêm các tình huống:

- Renew timeout nhưng server đã gia hạn.
- Lease hết hạn trong lúc client đang chờ response từ database.
- Hai worker cùng acquire gần như đồng thời.
- Owner release sau khi lease đã được cấp cho người khác.
- Tiến trình restore từ ảnh chứa lease ID/token cũ.
- Nhiều replica restore từ cùng ảnh và cùng cố acquire một resource.
- Database hoặc lock service failover trong khi đang cấp lease.
- Clock của client lệch hoặc thay đổi.
- Downstream nhận request cũ sau khi owner mới đã ghi dữ liệu.

Kết quả cần xác nhận không chỉ là lock service báo đúng owner. Hệ thống đích cũng phải từ chối thao tác của stale owner.

## 25. Quan sát và vận hành lease

Các metric giúp phát hiện lease đang hoạt động không ổn định:

| Metric | Ý nghĩa |
|---|---|
| Acquire success/failure | Tỷ lệ lấy quyền thành công và tranh chấp |
| Renew success/failure/timeout | Sức khỏe của vòng gia hạn |
| Lease age và remaining TTL | Thời gian lease đã tồn tại và thời gian còn lại theo nguồn có thẩm quyền |
| Ownership changes | Số lần chuyển owner hoặc tăng epoch |
| Fencing rejection count | Số thao tác bị từ chối do token cũ |
| Work stopped after lease loss | Số lần worker dừng khi không xác nhận được quyền |
| Restore-to-reacquire duration | Thời gian từ restore đến khi lấy được lease mới |
| Stale operation count | Số request từ owner cũ bị downstream từ chối |

Log nên chứa resource key, owner ID, lease ID đã được che phù hợp, fencing token, epoch, kết quả acquire/renew/release và correlation ID. Tránh log credential hoặc token bí mật dùng để xác thực.

Một cảnh báo hữu ích là lease renew liên tục thất bại hoặc fencing rejection tăng đột biến. Đây có thể là dấu hiệu GC pause, checkpoint/restore, network partition, lock service quá tải hoặc thời gian TTL đặt quá ngắn.

## 26. Những lỗi thiết kế thường gặp

**Coi biến isOwner trong heap là nguồn sự thật.** Biến này không tự thay đổi khi lease hết hạn ở hệ thống trung tâm. Luôn xác minh quyền và dùng fencing tại downstream.

**Chỉ dùng TTL mà không có fencing token.** Owner cũ có thể resume và ghi sau khi lease mới được cấp. Downstream phải từ chối token cũ.

**Release lock vô điều kiện.** Owner cũ có thể xóa lease mới của owner khác. Release phải so sánh lease ID/owner token một cách nguyên tử.

**Dùng timestamp client làm fencing token.** Đồng hồ lệch hoặc quay lùi có thể phá thứ tự. Dùng sequence/revision tăng từ nguồn chung.

**Tiếp tục làm việc khi renew timeout.** Timeout không chứng minh lease vẫn còn hiệu lực. Dừng side effect mới cho đến khi xác minh được quyền.

**Checkpoint khi vẫn giữ lease.** Tiến trình restore có thể mang theo owner state đã cũ. Nhả lease trước checkpoint và acquire lại sau restore.

**Dùng cùng owner ID cho mọi replica restore.** Các replica có thể nhầm là cùng một chủ thể. Mỗi lần chạy cần identity riêng; token phải do hệ thống cấp.

**Chỉ kiểm tra fencing ở đầu job.** Lease có thể hết hạn giữa job. Kiểm tra token tại mỗi ranh giới ghi hoặc transaction.

**Cho rằng leader election tự bảo vệ downstream.** Leader cũ có thể tiếp tục phát lệnh. Gắn term/epoch vào lệnh và kiểm tra ở tài nguyên đích.

**Giữ transaction dài bằng thời gian lease.** Điều này làm tăng lock contention và rủi ro database. Dùng transaction ngắn và kiểm tra fencing token.

## 27. Checklist thiết kế lease cho ứng dụng Java dùng CRaC

- [ ] Resource cần độc quyền đã có khóa hoặc lease key rõ ràng chưa?
- [ ] Hệ thống cấp lease có bảo đảm nguyên tử và consistency phù hợp chưa?
- [ ] TTL, chu kỳ renew, timeout và safety margin đã được chọn dựa trên tải thực chưa?
- [ ] Renew timeout có dẫn đến trạng thái quyền sở hữu không chắc chắn và dừng công việc mới không?
- [ ] Release có kiểm tra lease ID/owner token để tránh xóa lease của owner khác không?
- [ ] Mỗi lần cấp quyền có fencing token hoặc owner epoch tăng đơn điệu không?
- [ ] Downstream có kiểm tra token trong cùng transaction với side effect không?
- [ ] Tiến trình có nhả lease và drain công việc trước checkpoint không?
- [ ] Sau restore, tiến trình có bỏ trạng thái lease cũ và acquire lease mới không?
- [ ] Nhiều replica restore từ cùng ảnh có owner ID riêng không?
- [ ] Không dùng wall-clock hoặc biến heap làm nguồn duy nhất để xác nhận lease còn hiệu lực không?
- [ ] Job có thể dừng an toàn tại batch boundary khi lease mất không?
- [ ] Progress và side effect có idempotency hoặc transaction bền vững không?
- [ ] Đã kiểm thử stale owner resume sau khi owner mới đã được cấp quyền chưa?
- [ ] Metric và log có thể truy vết acquire, renew, release, epoch và fencing rejection không?

## Kết luận

Lease là quyền sở hữu có thời hạn; distributed lock giúp các tiến trình phối hợp để không cùng nhận một quyền tại cùng thời điểm theo giao thức đã chọn. Nhưng khi owner bị pause, mất kết nối hoặc checkpoint lâu hơn TTL, lease có thể hết hạn và quyền có thể được cấp cho tiến trình khác. Owner cũ vẫn có thể resume với trạng thái trong heap chưa được cập nhật.

CRaC khiến tình huống này cần được xử lý có chủ đích: không checkpoint khi đang giữ quyền độc quyền, drain công việc và release lease trước checkpoint; sau restore, tạo identity mới và acquire lease mới. Với dữ liệu quan trọng, hãy dùng fencing token hoặc owner epoch tăng đơn điệu và bắt buộc hệ thống đích kiểm tra token trong cùng transaction với side effect. Như vậy, ngay cả khi tiến trình cũ thức dậy muộn, nó cũng không thể ghi đè kết quả của owner mới.
