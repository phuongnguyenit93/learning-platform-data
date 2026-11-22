# Đặt TTL cố định cho thực thể lưu bằng Repository trong Spring Data Redis

Không phải dữ liệu nào được lưu vào Redis cũng cần tồn tại vô thời hạn. Một bản nháp đơn hàng có thể chỉ có giá trị trong 30 phút; một mã xác nhận có thể hết hiệu lực sau vài phút; dữ liệu tạm của quy trình xử lý có thể được loại bỏ khi không còn cần thiết. Với **Spring Data Redis Repository**, cách đơn giản để quy định thời gian sống cố định cho toàn bộ một loại thực thể là khai báo `timeToLive` trên annotation `@RedisHash`.

Ví dụ:

```java
@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {
    @Id
    private String id;
}
```

Số `1800` biểu thị **1.800 giây = 30 phút**. Khi Repository lưu một `CheckoutDraft`, Spring Data Redis thiết lập thời gian hết hạn cho Redis key đại diện cho thực thể. Khi hết hạn, key không còn được đọc như một entity tồn tại, ngay cả khi ứng dụng không gọi phương thức xóa.

Bài học giải thích ý nghĩa của TTL cố định, cách cấu hình, cách Redis Repository duy trì TTL trong vòng đời entity, và những điểm cần lưu ý với cập nhật, truy vấn, chỉ mục cùng sự kiện hết hạn.

## 1. TTL là gì và tại sao đặt cho entity?

**TTL (Time To Live)** là khoảng thời gian còn lại trước khi một Redis key hết hạn. Redis lưu thời điểm hết hạn ở cấp **key** và tự xử lý việc key hết hạn. Đối với thực thể do Redis Repository quản lý, dữ liệu entity thường nằm trong một Redis Hash, vì vậy TTL được áp dụng cho **Redis key chứa Hash đó**.

```text
Java entity: CheckoutDraft(id="draft-001")
          |
          | checkoutDraftRepository.save(...)
          v
Redis Hash: checkout-drafts:draft-001
          |
          +-- id            = draft-001
          +-- customerId    = customer-42
          +-- note          = Chờ xác nhận
          +-- _class        = ...CheckoutDraft
          |
          +-- TTL = 1800 giây
                    |
                    v
          Hết hạn --> key không còn truy cập được
```

TTL áp dụng cho **toàn bộ entity key**. Redis không xóa riêng field `note` trước rồi giữ lại `customerId`. Nếu cần từng thuộc tính có thời hạn khác nhau, phải thiết kế các key riêng hoặc một mô hình dữ liệu khác.

Một số ứng dụng phù hợp với TTL cố định:

| Loại dữ liệu | Mục tiêu của TTL | Ví dụ |
|---|---|---|
| Bản nháp thanh toán | Không giữ bản nháp bị bỏ quên mãi mãi | 30 phút |
| Mã xác nhận tạm | Giới hạn thời gian sử dụng | 5 phút |
| Trạng thái xử lý ngắn hạn | Dọn trạng thái không còn cần thiết | 1 giờ |
| Thông tin phiên nghiệp vụ tạm | Cho phiên có thời hạn rõ ràng | 20 phút |

Các con số chỉ để minh họa, không phải thời hạn mặc định của Spring Data Redis. Thời hạn phù hợp phải xuất phát từ yêu cầu nghiệp vụ.

### TTL khác gì với thao tác xóa thủ công?

- Với `deleteById(...)`, ứng dụng chủ động xóa entity qua Repository.
- Với TTL, Redis tự xác định thời điểm key hết hạn theo cấu hình đã gắn vào key.
- Việc **hết hạn (expiration)** khác với **trục xuất do thiếu bộ nhớ (eviction)**. Tùy chính sách `maxmemory`, Redis có thể trục xuất một key trước khi TTL của nó kết thúc.
- TTL của Redis là cơ chế quản lý vòng đời key, không tự động thay thế yêu cầu lưu trữ bền vững, audit hoặc các thao tác nghiệp vụ phải bảo đảm được thực thi.

Redis sử dụng thời điểm hết hạn và cơ chế phát hiện key hết hạn khi truy cập hoặc trong chu kỳ dọn nền. Vì vậy, không nên coi thời điểm phát ra sự kiện xóa là một đồng hồ chính xác từng mili giây. Dẫu vậy, sau khi thời hạn đã qua, các thao tác đọc bình thường sẽ coi key hết hạn là không tồn tại.

## 2. Cấu hình TTL cố định bằng @RedisHash

`@RedisHash` đánh dấu một lớp là aggregate root được lưu trong Redis Repository. Ngoài xác định **keyspace**, annotation hỗ trợ thuộc tính `timeToLive`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {

    @Id
    private String id;

    private String customerId;

    private String note;

    protected CheckoutDraft() {
        // Dành cho Spring Data khi khởi tạo entity.
    }

    public CheckoutDraft(String id, String customerId, String note) {
        this.id = id;
        this.customerId = customerId;
        this.note = note;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getNote() {
        return note;
    }

    public void changeNote(String note) {
        this.note = note;
    }
}
```

Trong ví dụ:

| Khai báo | Vai trò |
|---|---|
| `@RedisHash("checkout-drafts")` | Khai báo keyspace; Redis key thường có dạng `checkout-drafts:<id>` |
| `timeToLive = 1800` | Cấu hình thời hạn sống cho mỗi entity khi Repository lưu |
| `@Id` | Xác định giá trị id dùng để lập Redis key |
| `customerId`, `note` | Các thuộc tính nghiệp vụ được ánh xạ vào Redis Hash |

**Đơn vị mặc định của `timeToLive` là giây.** Vì thế, `timeToLive = 60` tương ứng một phút; `timeToLive = 3600` tương ứng một giờ. Hãy ghi rõ đơn vị trong comment hoặc đặt hằng số có tên cụ thể để giảm nhầm lẫn với mili giây.

Ví dụ:

```java
private static final long THIRTY_MINUTES_IN_SECONDS = 30 * 60;

@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {
    // ...
}
```

Annotation cần hằng số biên dịch nên không thể trực tiếp truyền một biến được đọc động từ `application.yml` vào `timeToLive`. Nếu thời hạn cần thay đổi theo cấu hình triển khai hoặc theo từng entity, nên xem xét các cách cấu hình TTL khác thay vì cố ép một giá trị động vào annotation.

**Lưu ý:** Giá trị cố định trong `@RedisHash` áp dụng chung cho những entity của lớp đó, theo chính sách khi lưu của Repository. Đây là điểm khác với `@TimeToLive` đặt trên thuộc tính/method để cho phép thời hạn thay đổi theo mỗi instance.

## 3. Kết nối Repository với Redis

Với một ứng dụng Spring Boot dùng Spring Data Redis, dependency thường là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ cấu hình kết nối trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Đây là cấu hình Redis local phục vụ minh họa; ứng dụng thực tế cần cấu hình kết nối, xác thực, TLS, cluster hoặc sentinel theo môi trường chạy. Trong môi trường Spring Boot có cấu hình repository phù hợp, các Redis Repository có thể được phát hiện tự động. Nếu cần bật tường minh:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories
public class RedisRepositoryConfig {
}
```

Repository cho entity:

```java
import org.springframework.data.repository.CrudRepository;

public interface CheckoutDraftRepository
        extends CrudRepository<CheckoutDraft, String> {
}
```

Khi dùng `CrudRepository`, ứng dụng gọi `save`, `findById`, `existsById` và `deleteById`. Spring Data Redis thực hiện ánh xạ và lưu/đọc Redis Hash bên dưới. Không cần tự viết `EXPIRE` sau mỗi lệnh lưu chỉ để áp dụng TTL cố định đã khai báo.

## 4. Ví dụ service sử dụng entity có TTL cố định

Một service thao tác với bản nháp:

```java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CheckoutDraftService {

    private final CheckoutDraftRepository repository;

    public CheckoutDraftService(CheckoutDraftRepository repository) {
        this.repository = repository;
    }

    public CheckoutDraft create(
            String draftId,
            String customerId,
            String note
    ) {
        CheckoutDraft draft =
                new CheckoutDraft(draftId, customerId, note);
        return repository.save(draft);
    }

    public Optional<CheckoutDraft> find(String draftId) {
        return repository.findById(draftId);
    }

    public CheckoutDraft updateNote(String draftId, String newNote) {
        CheckoutDraft draft = repository.findById(draftId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Draft does not exist or has expired: " + draftId
                ));

        draft.changeNote(newNote);
        return repository.save(draft);
    }

    public void delete(String draftId) {
        repository.deleteById(draftId);
    }
}
```

Luồng sử dụng:

```java
CheckoutDraft saved = draftService.create(
        "draft-001",
        "customer-42",
        "Chờ xác nhận địa chỉ giao hàng"
);

Optional<CheckoutDraft> draft = draftService.find("draft-001");

CheckoutDraft updated = draftService.updateNote(
        "draft-001",
        "Đã bổ sung địa chỉ"
);
```

Sau khi lưu, Repository thiết lập thời hạn của key. Khi key hết hạn, `findById("draft-001")` trả `Optional.empty()` nếu không có tiến trình nào tạo lại key đó. Service nên coi trường hợp không tìm thấy là kết quả bình thường đối với dữ liệu có TTL; một HTTP API có thể chuyển thành thông báo bản nháp đã hết hạn hoặc không tồn tại theo hợp đồng nghiệp vụ.

**Quan trọng:** mã service chỉ minh họa đường đi dữ liệu. Nếu thao tác cập nhật cần chống ghi đè đồng thời, việc đọc rồi gọi `save` đơn thuần không tự cung cấp cơ chế optimistic locking hay transaction phân tán. Cần xử lý vấn đề đồng thời riêng.

## 5. TTL bắt đầu từ khi nào và thay đổi ra sao?

Với TTL cố định của `@RedisHash`, mốc thực tế cần quan sát là **lần lưu thực thể bằng Repository**. Khi `save` thiết lập expiration, Redis bắt đầu đếm thời gian từ lúc thiết lập đó.

Ví dụ TTL = 1.800 giây:

```text
12:00  repository.save(draft)       -> TTL xấp xỉ 1800 giây
12:05  repository.findById(id)      -> TTL xấp xỉ 1500 giây
12:10  repository.findById(id)      -> TTL xấp xỉ 1200 giây
12:12  repository.save(draft)       -> TTL được đặt lại xấp xỉ 1800 giây
12:42  nếu không có lần lưu mới     -> key đã đến hạn hết hạn
```

Những mốc trên mang tính minh họa, chưa tính thời gian thực thi và các thao tác ghi khác.

### 5.1. Đọc không tự kéo dài TTL

Gọi `findById(...)` chỉ đọc thực thể. Nó **không phải** một thao tác gia hạn TTL theo kiểu sliding session. Nếu bản nháp được tạo lúc 12:00 và người dùng chỉ đọc liên tục, key vẫn đến hạn sau khoảng 30 phút kể từ lần lưu cuối, trừ khi có logic khác chủ động gia hạn.

Nếu nghiệp vụ yêu cầu “30 phút kể từ hoạt động cuối cùng”, đó là chính sách **sliding expiration**, khác với TTL cố định gắn trên `@RedisHash`. Cần thiết kế thao tác gia hạn rõ ràng, theo dõi hoạt động và chú ý tính đồng thời.

### 5.2. Save lại thường đặt lại thời hạn

Khi sửa entity rồi gọi `repository.save(entity)`, Spring Data Redis lưu trạng thái entity và áp dụng lại TTL đã cấu hình. Điều này thường dẫn đến việc **đặt lại** thời gian đếm kể từ lần lưu mới.

Điểm này quan trọng với bản nháp: nếu một job cập nhật `note` mỗi phút, bản nháp có thể tiếp tục tồn tại miễn là job vẫn lưu entity định kỳ. Nếu yêu cầu là “hết hạn tuyệt đối 30 phút sau khi tạo”, việc save lại với TTL cố định 30 phút **không** thể hiện đầy đủ yêu cầu đó.

Cần phân biệt hai chính sách:

| Chính sách | Ý nghĩa | TTL cố định trên `@RedisHash` |
|---|---|---|
| 30 phút kể từ lần lưu gần nhất | Mỗi lần save có thể gia hạn | Phù hợp với hành vi thường gặp |
| 30 phút kể từ lúc tạo, bất kể cập nhật | Hạn cuối tuyệt đối | Cần cơ chế tính thời gian còn lại hoặc tránh reset |
| 30 phút kể từ lần đọc hoặc thao tác của người dùng | Sliding expiration theo hoạt động | Chỉ đọc Repository không tự gia hạn |

Nếu chọn TTL “30 phút kể từ khi tạo”, một hướng là lưu `expiresAt` như dữ liệu nghiệp vụ rồi tính TTL còn lại khi lưu, áp dụng cơ chế `@TimeToLive` thích hợp hoặc kiểm soát thao tác ghi theo một chính sách riêng. Cần quy định cách xử lý khi thời điểm hết hạn đã qua và tránh gia hạn ngoài ý muốn.

### 5.3. Delete và tạo lại cùng ID

`deleteById(id)` chủ động xóa entity. Một lần `save` sau đó với **cùng id** có thể tạo key mới và TTL mới. Redis không lưu “lịch sử một ID đã hết hạn” để cấm tạo lại. Nếu nghiệp vụ cần ngăn sử dụng lại id, phải có cơ chế riêng.

## 6. Kiểm tra TTL trực tiếp trong Redis

Sau khi gọi `repository.save(...)`, có thể kiểm tra key bằng Redis CLI. Với `@RedisHash("checkout-drafts")` và id `draft-001`, key thường là:

```text
checkout-drafts:draft-001
```

Một lượt kiểm tra minh họa:

```redis
TYPE checkout-drafts:draft-001
# hash

HGETALL checkout-drafts:draft-001
# Các field/value đã được mapping từ CheckoutDraft

TTL checkout-drafts:draft-001
# (integer) 1794
```

`TTL` trả **số giây còn lại**. Giá trị `1794` chỉ là ví dụ sau khoảng sáu giây kể từ lúc lưu; không nên mong thấy đúng `1800` ở mọi thời điểm.

Để đo chính xác hơn theo mili giây:

```redis
PTTL checkout-drafts:draft-001
# (integer) 1793200
```

Ý nghĩa kết quả:

| Giá trị trả từ `TTL`/`PTTL` | Diễn giải |
|---|---|
| Số không âm | Thời gian còn lại: giây với `TTL`, mili giây với `PTTL` |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại, bao gồm trường hợp đã hết hạn |

Khi TTL hết hạn:

```redis
EXISTS checkout-drafts:draft-001
# (integer) 0

TTL checkout-drafts:draft-001
# (integer) -2
```

Nếu `TTL` trả `-1` ngay sau khi lưu qua Repository, hãy kiểm tra xem dữ liệu được ghi bằng đúng entity có `@RedisHash(timeToLive = ...)` hay không. Có thể thao tác thực tế đã dùng `RedisTemplate` hoặc lệnh Redis thô thay vì Repository, hoặc một lệnh sau đó đã xóa expiration. Cũng cần chắc chắn CLI đang kết nối cùng Redis instance và logical database với ứng dụng.

### Phân biệt thay đổi giá trị và thay đổi TTL bằng lệnh Redis

Để hiểu Redis ở cấp key:

```redis
SET demo:ttl "hello" EX 60
TTL demo:ttl
# còn khoảng 60 giây

EXPIRE demo:ttl 120
TTL demo:ttl
# còn khoảng 120 giây

PERSIST demo:ttl
TTL demo:ttl
# (integer) -1
```

Ví dụ này thao tác với Redis String để minh họa trực tiếp ý nghĩa `EXPIRE` và `PERSIST`. Với entity do Repository quản lý, nên để Repository quyết định chính sách TTL nhất quán. Việc thay TTL thủ công có thể bị lần `save` tiếp theo ghi đè bằng thời hạn cố định từ annotation.

## 7. @RedisHash(timeToLive) và @TimeToLive

Spring Data Redis hỗ trợ hai cách cấu hình TTL thường gặp:

### 7.1. TTL cố định cho cả lớp

```java
@RedisHash(value = "checkout-drafts", timeToLive = 1800)
public class CheckoutDraft {
    @Id
    private String id;
}
```

Mỗi entity cùng loại có chính sách TTL giống nhau theo khai báo của lớp. Phù hợp với dữ liệu có hạn sử dụng thống nhất, dễ đọc và dễ triển khai.

### 7.2. TTL thay đổi theo instance

Khi từng entity cần thời hạn khác nhau, có thể dùng `@TimeToLive` trên thuộc tính hoặc method:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("temporary-records")
public class TemporaryRecord {

    @Id
    private String id;

    @TimeToLive
    private Long remainingSeconds;

    protected TemporaryRecord() {
    }

    public TemporaryRecord(String id, long remainingSeconds) {
        this.id = id;
        this.remainingSeconds = remainingSeconds;
    }
}
```

Mỗi instance có thể cung cấp thời gian sống riêng, chẳng hạn 60, 300 hoặc 900 giây. Khi tải entity từ Redis, thuộc tính đánh dấu `@TimeToLive` cũng có thể được cập nhật bằng TTL còn lại từ Redis (bao gồm giá trị đặc biệt biểu thị không có expiration).

**Không nên vừa đặt TTL cố định trên lớp vừa thêm thuộc tính `@TimeToLive` mà chưa xác định rõ quy tắc ưu tiên.** Nếu cần TTL thống nhất cho tất cả entity, dùng `@RedisHash(timeToLive = ...)` là cách trực tiếp. Nếu cần TTL theo mỗi instance, thiết kế cơ chế `@TimeToLive` và cách tính/đọc thời gian một cách nhất quán.

| Tiêu chí | `@RedisHash(timeToLive = ...)` | `@TimeToLive` |
|---|---|---|
| Nơi đặt cấu hình | Trên lớp entity | Trên thuộc tính hoặc method |
| Giá trị TTL | Một giá trị cố định | Có thể khác giữa các instance |
| Phù hợp | Draft, cache entity có thời hạn chung | Thời hạn phụ thuộc nghiệp vụ hoặc từng bản ghi |
| Đọc lại TTL còn lại vào object | Không tự có thuộc tính TTL riêng | Có thể dùng field được annotation |
| Độ phức tạp | Thấp | Cần quản lý chính sách tính thời gian |

## 8. TTL trên entity khác TTL của các Redis key phụ trợ

Spring Data Redis Repository có thể lưu thêm những Redis key phụ trợ ngoài Hash của entity, chẳng hạn:

- Tập hợp theo dõi ID trong keyspace.
- Redis Set dùng làm secondary index cho thuộc tính `@Indexed`.
- Bản sao hỗ trợ sự kiện hết hạn, khi tính năng đó được bật.

Ví dụ:

```text
checkout-drafts:draft-001
  -> Redis Hash của entity, TTL 1800 giây

checkout-drafts
  -> Tập ID do hạ tầng Repository quản lý

checkout-drafts:customerId:customer-42
  -> Ví dụ một secondary index nếu customerId có @Indexed
```

**TTL của Hash không đồng nghĩa tất cả key phụ trợ có cùng TTL.** Redis expiration áp dụng trên từng Redis key. Với secondary index, hạ tầng Repository duy trì thành viên chỉ mục khi lưu/xóa entity và sử dụng sự kiện hết hạn để hỗ trợ dọn dữ liệu liên quan. Nếu một key hết hạn mà ứng dụng không nhận sự kiện cần thiết, một index Set có thể tạm còn ID của entity không tồn tại.

Do đó, không nên xây logic nghiệp vụ dựa trên giả định rằng Redis sẽ tự xóa mọi index Set cùng thời điểm với Hash. Khi cần đọc entity, hãy dùng Repository và xử lý trường hợp một ID trong index đã hết hạn.

## 9. Sự kiện hết hạn và “shadow copy” của Repository

Khi entity có TTL dương, Spring Data Redis Repository có cơ chế công bố `RedisKeyExpiredEvent` dựa trên Redis keyspace notifications. Để sự kiện có thể mang dữ liệu entity đã hết hạn, Repository có thể tạo một **shadow copy** (còn gọi là phantom copy) với thời hạn dài hơn key gốc khoảng **5 phút**.

Minh họa:

```text
12:00  Lưu CheckoutDraft
       |
       +-- Key gốc được đặt TTL = 30 phút
       |
       +-- Có thể tạo shadow copy phục vụ expiration event

12:30  Key gốc hết hạn
       |
       +-- Redis phát thông báo hết hạn (nếu cấu hình phù hợp)
       |
       +-- Spring Data có thể tạo RedisKeyExpiredEvent
       |
       +-- Shadow copy còn tồn tại thêm một khoảng thời gian
              để đọc dữ liệu dành cho sự kiện
```

**Hệ quả về bộ nhớ:** một số entity có TTL có thể kéo theo dung lượng Redis phụ trội từ shadow copy, nhất là khi dữ liệu lớn hoặc số lượng entity hết hạn cao. TTL của key gốc vẫn có hiệu lực; shadow copy phục vụ hạ tầng và không phải bản nháp còn dùng được qua Repository bằng ID gốc.

Nếu không cần dữ liệu của entity trong sự kiện hết hạn, có thể cân nhắc tắt shadow copy:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    shadowCopy = RedisKeyValueAdapter.ShadowCopy.OFF
)
public class RedisRepositoryConfiguration {
}
```

Khi tắt shadow copy, sự kiện hết hạn không còn mang bản sao đầy đủ của entity đã hết hạn. Quyết định này cần xét đến listener nghiệp vụ và cơ chế dọn secondary index đang sử dụng.

### 9.1. Keyspace notifications không phải event bus bảo đảm giao hàng

Redis expiration events dựa trên Pub/Sub. Sự kiện có thể không được quan sát nếu listener chưa khởi động, kết nối bị gián đoạn hoặc Redis không bật loại notification phù hợp. Trong Redis được quản lý (managed service), ứng dụng đôi khi không có quyền thay đổi cấu hình server bằng lệnh `CONFIG`.

Vì vậy:

- Không dùng `RedisKeyExpiredEvent` làm bằng chứng duy nhất để hoàn tất thao tác nghiệp vụ bắt buộc, chẳng hạn ghi sổ hay gửi một thông báo không được phép mất.
- Không giả định event được phát đúng khoảnh khắc TTL chạm 0; Redis nhận biết expiration theo cơ chế xử lý riêng.
- Với việc dọn index, theo dõi cấu hình keyspace notifications và khả năng bỏ lỡ sự kiện. Có thể cần cơ chế quét/reconcile bổ sung khi yêu cầu tính nhất quán cao.
- Trong Redis Cluster, các sự kiện liên quan đến node lưu key; listener cần kết nối và cấu hình phù hợp với topology đang dùng.

### 9.2. Cấu hình việc khởi tạo listener

Spring Data Redis cho phép điều khiển thời điểm đăng ký listener thông qua `@EnableRedisRepositories`. Ví dụ về lựa chọn khởi tạo khi ứng dụng bắt đầu:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
    enableKeyspaceEvents =
            RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
```

Tùy cấu hình, Spring Data Redis có thể cố thiết lập tham số notifications trên Redis server. Khi kết nối dịch vụ không cho phép `CONFIG`, cần cấu hình thông báo ở phía hạ tầng và điều chỉnh cách khởi tạo listener cho phù hợp. Không nên bật listener theo mẫu mà chưa xem xét môi trường và nhu cầu thực tế.

## 10. Những điểm cần chú ý khi cập nhật entity có TTL

### 10.1. Repository save và thao tác Redis thô không giống nhau

Ví dụ:

```java
repository.save(draft);
```

Sẽ sử dụng mapping và cấu hình TTL của Repository. Ngược lại:

```java
stringRedisTemplate.opsForHash().put(
        "checkout-drafts:draft-001",
        "note",
        "Sửa trực tiếp"
);
```

Lệnh trực tiếp trên Hash không chủ động đọc annotation `@RedisHash` để tạo TTL nếu key chưa có expiration. Nó cũng không thực hiện mọi bước cập nhật secondary index của Repository. Nếu thao tác trên key đã có TTL, lệnh `HSET` thông thường không tự gia hạn TTL của toàn bộ key. Vậy nên cùng một thay đổi nghiệp vụ có thể cho kết quả TTL khác nhau tùy đường ghi.

### 10.2. Không giả định thay đổi TTL ngay khi sửa Java object

```java
CheckoutDraft draft = repository.findById("draft-001")
        .orElseThrow();

draft.changeNote("Nội dung mới");
// Chưa có lệnh ghi tới Redis, TTL vẫn tiếp tục giảm.

repository.save(draft);
// Repository ghi thay đổi và áp dụng lại TTL cấu hình.
```

Thao tác sửa trường trong JVM không thay đổi Redis. Chỉ sau khi phương thức lưu được thực thi mới có tác động tới key và thời hạn của nó.

### 10.3. Cẩn thận với các tác vụ nền liên tục save

Nếu một job cập nhật trạng thái dự thảo mỗi 10 giây và lần nào cũng gọi `save`, TTL cố định 30 phút sẽ được đặt lại liên tục. Có thể bạn đã biến “bản nháp chỉ tồn tại tối đa 30 phút” thành “bản nháp tồn tại ít nhất 30 phút kể từ lần job cập nhật cuối”.

Nên định nghĩa rõ:

1. Hết hạn kể từ khi tạo, kể từ lần ghi, hay kể từ lần hoạt động cuối?
2. Những thao tác nào được phép gia hạn?
3. Lúc nào entity bắt buộc bị xem là không hợp lệ theo nghiệp vụ?
4. Nếu một luồng vừa đọc entity thì luồng khác xóa/hết hạn, kết quả ghi tiếp được xử lý thế nào?

TTL Redis bảo đảm giới hạn vòng đời key theo cấu hình hiện tại. Nó không thay thế được việc xây dựng quy tắc hết hạn nghiệp vụ.

## 11. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Điều cần kiểm tra | Hướng xử lý |
|---|---|---|
| `TTL key` luôn trả `-1` | Entity có `@RedisHash(timeToLive)` chưa, có ghi qua Repository không? | Dùng đúng Repository và xác nhận annotation/TTL dương |
| `TTL key` trả `-2` ngay sau khi ghi | Sai tên key, database, key đã xóa hoặc thời hạn quá ngắn | Kiểm tra keyspace/id, kết nối Redis và thời hạn |
| TTL liên tục trở lại gần giá trị ban đầu | Có job hoặc service gọi `save` lặp lại | Xác định rõ thao tác được gia hạn, đổi chính sách nếu cần |
| `findById(...)` trả rỗng sau một thời gian | Key đã hết hạn hoặc bị xóa/trục xuất | Xử lý trạng thái không tồn tại trong logic nghiệp vụ |
| Key đã hết hạn nhưng index Set vẫn còn ID | Missed expiration event hoặc ghi/xóa ngoài Repository | Rà soát listener, notifications và cơ chế reconcile |
| Redis sử dụng nhiều bộ nhớ hơn dự kiến | Shadow copy và các Redis key phụ trợ | Đo dung lượng; cân nhắc `shadowCopy = OFF` nếu phù hợp |
| Không nhận được `RedisKeyExpiredEvent` | Listener chưa bật, bị gián đoạn hoặc Redis thiếu notifications | Kiểm tra cấu hình kết nối, keyspace notifications và lifecycle |
| Gọi `opsForValue().set(...)` nhưng entity không có TTL như annotation | RedisTemplate không dùng entity mapping của Repository | Đặt TTL riêng cho thao tác template hoặc chuyển sang Repository |
| Giá trị thời hạn lệch 1.000 lần | Nhầm giây với mili giây | Quy định đơn vị rõ ràng, kiểm tra `TTL` và `PTTL` |
| Entity biến mất trước TTL | Có thao tác xóa, eviction hoặc ghi lại cấu hình TTL khác | Quan sát delete paths, `maxmemory` và truy cập key thực tế |

### Các lệnh quan sát cơ bản

```redis
EXISTS checkout-drafts:draft-001
TYPE checkout-drafts:draft-001
HGETALL checkout-drafts:draft-001
TTL checkout-drafts:draft-001
PTTL checkout-drafts:draft-001
INFO memory
```

Hãy quan sát chính xác key của entity chứ không suy ra từ việc còn thấy Set chỉ mục hoặc shadow copy. Cần phân biệt key gốc với các key do Repository tạo để hỗ trợ ánh xạ và sự kiện.

## 12. Bài thực hành: quan sát TTL cố định của Repository

Thực hành trên Redis dành cho học tập, dùng entity `CheckoutDraft` với `timeToLive = 30` để không phải đợi lâu. Các bước:

1. Đổi annotation thành `@RedisHash(value = "checkout-drafts", timeToLive = 30)`.
2. Dùng `repository.save(...)` tạo một entity có id `draft-demo`.
3. Gọi `TTL checkout-drafts:draft-demo`; ghi nhận giá trị xấp xỉ 30 giây.
4. Gọi `repository.findById("draft-demo")` vài lần, rồi xem TTL tiếp tục giảm.
5. Trước khi hết hạn, sửa `note` và gọi `repository.save(...)`; quan sát TTL được đặt lại gần 30 giây.
6. Không lưu thêm, đợi quá thời hạn và kiểm tra `findById(...)` trả rỗng cùng `TTL` trả `-2`.
7. Thử lưu lại entity với cùng id; quan sát Redis tạo một vòng đời TTL mới.

Có thể dùng đoạn mã minh họa:

```java
CheckoutDraft draft = new CheckoutDraft(
        "draft-demo", "customer-demo", "Created"
);

repository.save(draft);

// Sau một khoảng thời gian:
CheckoutDraft existing = repository.findById("draft-demo")
        .orElseThrow();
existing.changeNote("Updated");
repository.save(existing);
```

**Câu hỏi tự kiểm tra kiến thức:**

- Vì sao `findById` không làm TTL trở lại 30 giây?
- Vì sao `save` lại có thể làm thời hạn hết hạn thay đổi?
- Khi Redis Hash đã hết hạn, có chắc mọi secondary index Set cũng biến mất ngay không?
- Nếu yêu cầu “đúng 30 phút kể từ lúc tạo”, cần thay đổi điều gì để không vô tình gia hạn bằng `save`?

## 13. Nguyên tắc áp dụng trong production

Khi triển khai TTL cố định với Redis Repository, nên chọn thời hạn dựa trên **vòng đời nghiệp vụ**, thiết kế đường ghi qua Repository nhất quán và kiểm tra trực tiếp TTL của key thật. Chú ý rằng việc lưu lại entity đặt lại expiration, còn việc đọc thông thường không tự gia hạn.

Nếu entity có `@Indexed` hoặc ứng dụng phụ thuộc `RedisKeyExpiredEvent`, hãy xét thêm keyspace notifications, khả năng bỏ lỡ event, shadow copy và nhu cầu dọn index. Với những nghĩa vụ bắt buộc như thanh toán, ghi nhận giao dịch, phát hành tài liệu hoặc phát sự kiện không được mất, không dùng Redis expiration event như cơ chế thực thi duy nhất.

**Điểm ghi nhớ:** `@RedisHash(timeToLive = 1800)` quy định một TTL cố định ở cấp lớp cho entity được lưu bằng **Spring Data Redis Repository**. Repository áp dụng expiration cho Redis key của entity khi lưu; Redis quyết định khi nào key hết hạn; ứng dụng phải xử lý việc entity có thể không còn tồn tại và phải tự thiết kế chính sách gia hạn/hạn chót nếu yêu cầu nghiệp vụ phức tạp hơn.

## Tài liệu tham khảo

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): `@RedisHash(timeToLive)`, `@TimeToLive` và cơ chế sự kiện hết hạn.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): vòng đời entity và các thành phần Repository.
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): cách Repository quản lý chỉ mục phụ.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): gắn thời hạn cho Redis key.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): cách đọc thời hạn theo giây và các giá trị đặc biệt.
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): cách Redis phát thông báo khi key hết hạn và giới hạn của Pub/Sub.
