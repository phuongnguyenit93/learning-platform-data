# list, set, map và lựa chọn cấu trúc phù hợp trong Spring Data Cassandra

Trong **Apache Cassandra**, một cột có thể chứa tập hợp giá trị thay vì chỉ một giá trị đơn. CQL cung cấp ba kiểu collection phổ biến: `list<T>`, `set<T>` và `map<K, V>`. **Spring Data Cassandra** ánh xạ chúng tương ứng với `List<T>`, `Set<T>` và `Map<K, V>` của Java, để ứng dụng dùng entity mapping, repository hoặc `CassandraTemplate` như với các cột khác.

Bài học thuộc chương **Kiểu dữ liệu** của module **SPRING_DATA_CASSANDRA**. Trọng tâm không chỉ là viết đúng cú pháp CQL: cần biết **khi nào một collection là cấu trúc phù hợp**, cách cập nhật từng phần tử, sự khác nhau giữa `frozen` và `non-frozen`, giới hạn về kích thước, tính nhất quán và khi nào phải chuyển sang bảng thiết kế theo truy vấn với partition key, clustering key và paging.

Sau bài này, bạn có thể chọn một kiểu collection từ yêu cầu nghiệp vụ cụ thể, ánh xạ nó sang Java, cập nhật có kiểm soát và nhận diện các trường hợp mà collection sẽ làm truy vấn hoặc hệ thống phân tán khó mở rộng.

## 1. Ba loại collection và ý nghĩa nghiệp vụ

| Kiểu CQL | Java | Đặc trưng | Ví dụ thích hợp |
|---|---|---|---|
| `list<text>` | `List<String>` | Có thứ tự vị trí; **cho phép trùng** phần tử | Vài bước hướng dẫn hiển thị theo thứ tự |
| `set<text>` | `Set<String>` | Mỗi giá trị chỉ xuất hiện một lần; **không giữ thứ tự thêm vào** | Nhãn của hồ sơ, quyền tính năng nhỏ |
| `map<text, boolean>` | `Map<String, Boolean>` | Mỗi khóa là duy nhất; ánh xạ khóa → giá trị | Một số lựa chọn bật/tắt thông báo |

Cú pháp định nghĩa:

~~~sql
list<text>
set<text>
map<text, boolean>
~~~

Cú pháp giá trị:

~~~sql
-- list: ngoặc vuông, có thứ tự và có thể lặp.
['WELCOME', 'VERIFY_EMAIL', 'WELCOME']

-- set: ngoặc nhọn, giá trị không được lặp như những phần tử riêng.
{'new', 'vip'}

-- map: ngoặc nhọn, mỗi key ánh xạ tới value.
{'email': true, 'sms': false}
~~~

Phân biệt ba câu hỏi sau trước khi chọn:

1. **Có cần vị trí hoặc phần tử lặp không?** Nếu có và tập hợp nhỏ, `list` có thể hợp lý.
2. **Chỉ cần biết một giá trị có mặt hay không?** `set` thường phù hợp hơn `list`.
3. **Cần tra một giá trị bằng một tên khóa duy nhất?** `map` có thể hợp lý khi số khóa nhỏ và đã biết.

Các ví dụ trên là **tập dữ liệu có kích thước hữu hạn và nhỏ**. Không nên dùng collection làm kho chứa hàng nghìn/hàng triệu sự kiện chỉ vì muốn “nhét toàn bộ dữ liệu của một user vào một hàng”.

## 2. Ví dụ xuyên suốt: cài đặt của một khách hàng

Giả sử một ứng dụng có API:

~~~text
GET /customers/{customerId}/preferences

Trả về:
  - Vài bước onboarding đã được hiển thị, theo thứ tự.
  - Các nhãn gắn vào hồ sơ.
  - Cách bật/tắt kênh thông báo theo tên kênh.
~~~

Mỗi khách hàng có **một** hàng theo `customer_id`. Số bước, nhãn và kênh thông báo được giới hạn bởi quy tắc nghiệp vụ (ví dụ vài chục giá trị), nên collection nằm trong cùng hàng có thể phù hợp:

~~~sql
CREATE TABLE customer_preferences_by_id (
    customer_id uuid PRIMARY KEY,
    onboarding_steps list<text>,
    tags set<text>,
    notification_settings map<text, boolean>,
    updated_at timestamp
);
~~~

`customer_id` là **partition key**, cũng là toàn bộ primary key. Ba cột collection chỉ là dữ liệu của hàng đó, **không giúp Cassandra định tuyến theo tag hoặc kênh thông báo**.

Viết một hàng mẫu:

~~~sql
INSERT INTO customer_preferences_by_id (
    customer_id,
    onboarding_steps,
    tags,
    notification_settings,
    updated_at
) VALUES (
    8f6e37fa-7af2-47e2-b4be-542e83a83848,
    ['WELCOME', 'VERIFY_EMAIL'],
    {'new', 'beta'},
    {'email': true, 'sms': false},
    '2026-11-25T09:00:00+00:00'
);
~~~

Đọc đúng đường truy cập:

~~~sql
SELECT customer_id, onboarding_steps, tags,
       notification_settings, updated_at
FROM customer_preferences_by_id
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

Cassandra xác định partition qua `customer_id`, rồi trả về các cột cần thiết. Dữ liệu collection được giải mã thành cấu trúc tương ứng trong Java; **paging của kết quả nhiều hàng không phân trang các phần tử bên trong một collection**.

## 3. Ánh xạ collection từ CQL sang entity Java

Spring Data Cassandra nhận biết các kiểu collection Java thông thường. Với bảng trên:

~~~java
package example.preferences;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customer_preferences_by_id")
public class CustomerPreferences {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("onboarding_steps")
    private List<String> onboardingSteps;

    @Column("tags")
    private Set<String> tags;

    @Column("notification_settings")
    private Map<String, Boolean> notificationSettings;

    @Column("updated_at")
    private Instant updatedAt;

    public CustomerPreferences() {}

    public CustomerPreferences(
            UUID customerId,
            List<String> onboardingSteps,
            Set<String> tags,
            Map<String, Boolean> notificationSettings,
            Instant updatedAt) {
        this.customerId = customerId;
        this.onboardingSteps = onboardingSteps;
        this.tags = tags;
        this.notificationSettings = notificationSettings;
        this.updatedAt = updatedAt;
    }

    public UUID getCustomerId() { return customerId; }
    public void setCustomerId(UUID value) { this.customerId = value; }

    public List<String> getOnboardingSteps() { return onboardingSteps; }
    public void setOnboardingSteps(List<String> value) {
        this.onboardingSteps = value;
    }

    public Set<String> getTags() { return tags; }
    public void setTags(Set<String> value) { this.tags = value; }

    public Map<String, Boolean> getNotificationSettings() {
        return notificationSettings;
    }
    public void setNotificationSettings(Map<String, Boolean> value) {
        this.notificationSettings = value;
    }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { this.updatedAt = value; }
}
~~~

| Java | CQL | Điểm cần kiểm tra |
|---|---|---|
| `List<String>` | `list<text>` | Thứ tự phần tử và việc có thể lặp |
| `Set<String>` | `set<text>` | Tính duy nhất; thứ tự iteration không phải thứ tự thêm |
| `Map<String, Boolean>` | `map<text, boolean>` | Kiểu của cả key và value |
| `UUID` | `uuid` | Dùng trong partition key |
| `Instant` | `timestamp` | Thời gian theo trục thời gian, khác hiển thị múi giờ |

Spring Data Cassandra thường tự suy ra kiểu CQL từ kiểu Java, nên **không bắt buộc đặt `@CassandraType`** trên ba field đơn giản này. Khi dùng converter tùy chỉnh, enum, UDT hoặc cần định rõ kiểu CQL khác mặc định, có thể phải dùng `@CassandraType` và kiểm tra mapping với schema thật.

Ví dụ chỉ định rõ một kiểu collection:

~~~java
import org.springframework.data.cassandra.core.mapping.CassandraType;

@CassandraType(
        type = CassandraType.Name.SET,
        typeArguments = CassandraType.Name.TEXT)
private Set<String> tags;
~~~

Đây là **phương án khai báo thay thế** cho field `tags` của entity, không phải khai báo thêm một field thứ hai cùng tên. Nếu có schema đã tồn tại, sửa annotation Java **không tự migrate kiểu cột** trong Cassandra.

## 4. Ghi và đọc bằng repository, CassandraTemplate

Repository khai báo kiểu khóa `UUID` vì bảng có một partition key đơn:

~~~java
package example.preferences;

import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerPreferencesRepository
        extends CassandraRepository<CustomerPreferences, UUID> {
}
~~~

Một service có thể tạo dữ liệu ban đầu:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

// Trong service đã inject CustomerPreferencesRepository repository:
CustomerPreferences profile = new CustomerPreferences(
        customerId,
        List.of("WELCOME", "VERIFY_EMAIL"),
        Set.of("new", "beta"),
        Map.of("email", true, "sms", false),
        Instant.now()
);

repository.save(profile);
~~~

`customerId` là UUID đã xác nhận quyền truy cập trong nghiệp vụ. Các hàm `List.of`, `Set.of`, `Map.of` giúp biểu đạt dữ liệu nhỏ ban đầu và tạo collection không thay đổi được ở Java. Nếu sau đó muốn sửa collection trong bộ nhớ, hãy tạo bản sao mutable hoặc truyền giá trị mới thay vì cố gọi `add()` vào `List.of(...)`.

Đọc một hàng:

~~~java
Optional<CustomerPreferences> preferences = repository.findById(customerId);
~~~

Qua `CassandraTemplate` hoặc `CassandraOperations`:

~~~java
// Trong service đã inject CassandraOperations operations:
CustomerPreferences preferences =
        operations.selectOneById(customerId, CustomerPreferences.class);
// Nếu không có hàng, kết quả có thể là null.
~~~

`repository.save(profile)` biểu thị thao tác lưu entity qua mapper; **đừng dùng lời gọi này làm cách mặc định để thêm đúng một phần tử vào set/map** nếu nhiều writer có thể cập nhật cùng hàng. Tùy cơ chế update và trạng thái entity, việc lưu toàn bộ giá trị collection có thể thay thế dữ liệu hiện tại; thay đổi từng phần tử bằng CQL chuyên biệt giúp kiểm soát ý định rõ hơn.

## 5. Cập nhật list: có thứ tự nhưng cần thận trọng

`list` có thứ tự vị trí và cho phép trùng. CQL hỗ trợ thay toàn bộ, nối thêm, thêm vào đầu, cập nhật/xóa theo index và xóa theo giá trị.

~~~sql
-- Thay toàn bộ danh sách bằng giá trị mới.
UPDATE customer_preferences_by_id
SET onboarding_steps = ['WELCOME', 'VERIFY_EMAIL']
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Nối bước vào cuối danh sách.
UPDATE customer_preferences_by_id
SET onboarding_steps = onboarding_steps + ['CHOOSE_PLAN']
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Thêm bước vào đầu danh sách.
UPDATE customer_preferences_by_id
SET onboarding_steps = ['START'] + onboarding_steps
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Thay phần tử ở index 0 (index bắt đầu từ 0).
UPDATE customer_preferences_by_id
SET onboarding_steps[0] = 'INTRO'
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

Những thao tác này có chi phí và tính chất khác nhau:

| Thao tác | Rủi ro chính |
|---|---|
| Thay cả `list` | Có thể xóa/ghi đè thay đổi từ writer khác |
| Append/prepend | **Không idempotent**: retry khi timeout có thể thêm trùng |
| Sửa hoặc xóa theo index | Một số thao tác cần **read-before-write** bên trong Cassandra |
| Xóa mọi phần tử bằng một giá trị | Có thể phải đọc trước và tạo thêm tombstone |

Thao tác thêm vào `list` **không phù hợp làm nhật ký nghiệp vụ phải ghi đúng một lần** nếu request có thể được retry tự động. Với dữ liệu sự kiện, hãy dùng **một hàng trên mỗi sự kiện** và primary key chứa ID sự kiện ổn định.

Ví dụ không nên làm:

~~~text
User gửi event E1
  -> ứng dụng append E1 vào list
  -> Cassandra ghi thành công
  -> mạng timeout trước khi client nhận phản hồi
  -> ứng dụng retry append E1
  -> list có thể chứa E1 hai lần
~~~

Nếu nghiệp vụ cho phép phần tử trùng có chủ đích, vẫn phải xây dựng retry/idempotency phù hợp. Chỉ cần đổi `List` thành `Flux` hay gọi bất đồng bộ không thay đổi tính chất của thao tác CQL.

## 6. Cập nhật set: thêm, bỏ và tính duy nhất

`set` diễn tả tập hợp giá trị phân biệt; phù hợp với nhãn, danh sách khả năng hoặc các mã chọn trong một phạm vi hữu hạn. CQL:

~~~sql
-- Ghi đè toàn bộ set.
UPDATE customer_preferences_by_id
SET tags = {'new', 'beta'}
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Thêm phần tử: thêm lại 'vip' không tạo một phần tử thứ hai.
UPDATE customer_preferences_by_id
SET tags = tags + {'vip'}
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Loại bỏ một phần tử.
UPDATE customer_preferences_by_id
SET tags = tags - {'beta'}
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

Trong CQL, phần tử của `set` được sắp theo bộ so sánh của kiểu dữ liệu, nhưng **đừng dùng set để biểu diễn thứ tự người dùng thêm phần tử**. Trong Java, `HashSet` và các triển khai `Set` cũng không đảm bảo iteration theo thứ tự thêm; nếu thứ tự hiển thị quan trọng, hãy định nghĩa quy tắc sắp xếp riêng.

Thao tác `tags = tags + {'vip'}` với cùng giá trị thường phù hợp hơn append list khi retry vì không tạo nhiều phần tử trùng. Tuy nhiên, **idempotency ở mức phần tử không thay thế kiểm soát nghiệp vụ**: các thao tác thêm và xóa xen kẽ từ nhiều writer vẫn có thể dẫn tới kết quả khác mong đợi theo thứ tự timestamp/mutation.

## 7. Cập nhật map: khóa riêng lẻ và giá trị đi kèm

`map` lưu quan hệ **key → value**; mỗi key chỉ có một value tại thời điểm đọc. Ví dụ `notification_settings` có ba kênh đã biết `email`, `sms`, `push`.

~~~sql
-- Thay toàn bộ map.
UPDATE customer_preferences_by_id
SET notification_settings = {'email': true, 'sms': false}
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Chỉnh riêng giá trị của một key.
UPDATE customer_preferences_by_id
SET notification_settings['sms'] = true
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Ghép nhiều key/value.
UPDATE customer_preferences_by_id
SET notification_settings =
    notification_settings + {'email': false, 'push': true}
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Xóa một key khỏi map.
DELETE notification_settings['push']
FROM customer_preferences_by_id
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

`map` không giống một bảng quan hệ con. Khi một key của map cần được **truy vấn độc lập trên nhiều khách hàng** (ví dụ “tìm tất cả khách có `sms = true`”), cấu trúc này **không tạo index toàn cục theo key/value**. Hãy xác định query pattern, loại index mà phiên bản Cassandra hỗ trợ, hoặc thiết kế bảng truy cập khác.

Trong CQL, map được sắp theo key để lưu/đọc, nhưng không có thứ tự chèn phần tử mang ý nghĩa nghiệp vụ như `list`. Cần chuẩn hóa key (`sms`, `SMS`, `Sms`) trước khi ghi để không vô tình tạo nhiều mục khác nhau.

### 7.1. Thao tác từng phần tử từ Java Driver

Nếu cần sửa đúng một phần tử mà không muốn lưu lại toàn bộ entity, có thể dùng `CqlSession` và prepared statement:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class NotificationSettingsWriter {
    private final PreparedStatement statement;
    private final CqlSession session;

    public NotificationSettingsWriter(CqlSession session) {
        this.session = session;
        this.statement = session.prepare(
                "UPDATE customer_preferences_by_id " +
                "SET notification_settings[?] = ? " +
                "WHERE customer_id = ?");
    }

    public void updateChannel(UUID customerId, String channel, boolean enabled) {
        session.execute(statement.bind(channel, enabled, customerId));
    }
}
~~~

Đoạn code minh họa cập nhật `map` theo key; `CqlSession` cần dùng chung từ bean được quản lý vòng đời. Các giá trị `channel` nên nằm trong tập kênh được phép, `customerId` cần kiểm tra quyền truy cập và cần cấu hình timeout/consistency phù hợp môi trường.

**Spring Data Cassandra repository và `CassandraTemplate` vẫn phù hợp** cho CRUD, chuyển đổi entity và query theo khóa. Khi cần phép cập nhật CQL riêng cho collection, sử dụng statement có tham số là một lựa chọn rõ ràng thay vì tự ghép chuỗi CQL từ dữ liệu người dùng.

## 8. Non-frozen và frozen khác nhau thế nào?

Theo mặc định, collection thường được lưu dưới dạng **non-frozen** (đa ô/cell), cho phép cập nhật từng phần tử qua các thao tác CQL phù hợp. Từ khóa `frozen` làm Cassandra xem toàn bộ giá trị collection như **một giá trị đơn** cho mục đích ghi/đọc.

~~~sql
CREATE TABLE customer_preferences_snapshot (
    customer_id uuid PRIMARY KEY,
    tags_snapshot frozen<set<text>>,
    settings_snapshot frozen<map<text, boolean>>
);
~~~

| Tiêu chí | Non-frozen | Frozen |
|---|---|---|
| Cách cập nhật | Có thể thay cả collection hoặc cập nhật các phần tử hợp lệ | **Phải thay toàn bộ giá trị** |
| TTL/timestamp | Có thể áp dụng cho các phần tử mới/được cập nhật | Áp dụng cho giá trị collection như một đơn vị |
| Mục đích | Tập nhỏ cần thêm/xóa/sửa từng phần tử | Snapshot nhỏ, ít thay đổi, được thay nguyên khối |
| Trong primary key | Collection thông thường không dùng trực tiếp làm khóa | Một số collection `frozen` có thể tham gia khóa theo quy tắc CQL |
| Giới hạn thiết kế | Không phù hợp tập dữ liệu không giới hạn | Cũng **không** phù hợp tập dữ liệu không giới hạn |

Thao tác đối với frozen map:

~~~sql
-- Hợp lệ: thay nguyên giá trị frozen map.
UPDATE customer_preferences_snapshot
SET settings_snapshot = {'email': true, 'sms': true}
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;

-- Không áp dụng cú pháp cập nhật một phần tử như với non-frozen map:
-- SET settings_snapshot['sms'] = true
~~~

Trong Spring Data Cassandra, `@Frozen` mô tả cột collection đã được khai báo frozen:

~~~java
import java.util.Map;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Frozen;

@Column("settings_snapshot")
@Frozen
private Map<String, Boolean> settingsSnapshot;
~~~

Đoạn field trên thuộc entity ánh xạ với **bảng `customer_preferences_snapshot`**, không thêm nó vào entity của bảng `customer_preferences_by_id` trước đó. Khi bảng đã tồn tại, gắn `@Frozen` trong Java **không tự đổi CQL schema**; cần bảo đảm mapping và schema vật lý khớp nhau.

**Không lựa chọn frozen chỉ vì có vẻ nhanh hơn.** Nếu mỗi yêu cầu thường xuyên sửa một key, non-frozen map sẽ thuận tiện hơn. Nếu luôn lưu snapshot và thay nguyên giá trị, frozen có thể phù hợp. Dù chọn cách nào, số phần tử vẫn nên bị giới hạn.

## 9. Vì sao collection không thay thế bảng sự kiện?

Hãy so sánh hai thiết kế cho yêu cầu: “Lấy 50 sự kiện mới nhất của một thiết bị trong ngày, rồi tiếp tục xem trang sau”.

**Cách dễ sai:** lưu tất cả sự kiện vào một `list` của thiết bị:

~~~sql
CREATE TABLE device_event_lists (
    device_id uuid PRIMARY KEY,
    events list<text>
);
~~~

Mỗi ngày dữ liệu có thể tăng liên tục. Việc đọc cột `events` phải xử lý một collection ngày càng lớn; **Cassandra không phân trang từng phần tử của collection như các hàng thông thường**. Append list liên tục còn gặp vấn đề retry, tombstone và concurrency.

**Cách phù hợp hơn:** một hàng cho mỗi sự kiện, partition theo thiết bị và ngày, clustering theo thời gian:

~~~sql
CREATE TABLE events_by_device_day (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Truy vấn:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM events_by_device_day
WHERE device_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848
  AND day_bucket = '2026-11-25'
LIMIT 50;
~~~

Ưu điểm của thiết kế hàng riêng:

- Đường truy vấn được xác định bằng **đầy đủ partition key**.
- `event_time` là clustering column, cho phép đọc sự kiện mới hơn trước.
- Driver và Spring Data Cassandra có thể **paging theo các hàng** và paging state của truy vấn.
- `event_id` phân biệt các sự kiện có cùng timestamp; giữ ID ổn định giữa các lần retry giúp tránh tạo hàng mới ngoài ý muốn.
- Có thể điều chỉnh day bucket thành hour bucket hoặc thêm shard khi dữ liệu thực tế tạo partition nóng, sau khi cân nhắc chi phí đọc nhiều partition.

**Đừng nhầm page size với giới hạn kích thước collection.** Page size chỉ kiểm soát số hàng trong kết quả CQL; nếu một cột chứa collection quá lớn, việc giảm page size xuống 1 **không làm collection đó được chia thành nhiều trang nhỏ**.

## 10. Chọn collection, bảng truy cập hay index từ nhu cầu

| Nhu cầu sản phẩm | Lựa chọn khởi đầu | Vì sao? |
|---|---|---|
| Vài nhãn độc nhất của một khách hàng | `set<text>` | Nhỏ, không quan trọng thứ tự, không cho phép lặp |
| Danh sách vài bước UI có vị trí và có thể lặp | `list<text>` | Giữ thứ tự và cho phép lặp |
| Một số tùy chọn `email/sms/push` theo tên kênh | `map<text, boolean>` | Key/value nhỏ, có thể cập nhật một key |
| Một snapshot lựa chọn ít thay đổi | `frozen<map<...>>` | Thay nguyên khối có chủ đích |
| Toàn bộ lịch sử hoạt động của user | **Bảng riêng** theo user/time bucket | Có partition, clustering, paging và TTL theo hàng |
| Truy vấn khách hàng theo một nhãn | **Bảng truy cập theo nhãn** hoặc index phù hợp | `set` của bảng theo user không tự đáp ứng query đảo |
| Tìm kiếm tự do trên nhiều thuộc tính | Search/index hoặc hệ phân tích | Không phải nhiệm vụ tự nhiên của một collection lớn |
| Một tập hàng cần cập nhật độc lập, có quyền/TTL riêng | **Bảng riêng** | Mỗi item có khóa, vòng đời và truy vấn độc lập |

Một cây quyết định gọn:

~~~mermaid
flowchart TD
    A[Giá trị có nhiều phần tử] --> B{Số phần tử bị giới hạn nhỏ?}
    B -->|Không| C[Bảng riêng với partition/clustering và paging]
    B -->|Có| D{Cần truy vấn hoặc phân trang từng phần tử độc lập?}
    D -->|Có| C
    D -->|Không| E{Cần thứ tự hoặc phần tử lặp?}
    E -->|Có| F[list]
    E -->|Không| G{Cần key gắn với value?}
    G -->|Có| H[map]
    G -->|Không| I[set]
    F --> J[Đánh giá retry, concurrency, read-before-write]
    H --> K[Đánh giá cập nhật từng key hay frozen snapshot]
    I --> K
    J --> L[Benchmark kích thước và thao tác thực]
    K --> L
~~~

**Câu hỏi quan trọng hơn việc chọn cú pháp:** ứng dụng truy vấn theo **khóa của hàng** hay cần tìm kiếm một phần tử nằm trong collection trên **nhiều hàng**? Nếu là vế sau, phải thiết kế đường đọc riêng hoặc đánh giá loại index mà phiên bản Cassandra hỗ trợ. Thêm `findByTagsContains(...)` vào repository không tự tạo một index phù hợp.

## 11. Hiệu năng, consistency và concurrency

### 11.1. Không để collection tăng vô hạn

Cassandra tối ưu cho truy vấn theo partition key, không phải lưu một danh sách khổng lồ trong một ô logic. Với collection lớn:

- Payload đọc/ghi và bộ nhớ của ứng dụng tăng.
- Một hàng hoặc một phần collection có thể chứa nhiều cell/tombstone, khiến truy vấn chậm.
- Không có paging theo từng phần tử của collection.
- List có những thao tác read-before-write và phép nối thêm không idempotent.
- Có thể chạm giới hạn thực tế của native protocol, driver, tài nguyên cluster trước khi chạm giới hạn kiểu dữ liệu lý thuyết.

Hãy **giới hạn số phần tử bằng quy tắc nghiệp vụ** và đo p95/p99 theo dữ liệu đại diện. Không dùng “hệ thống cho phép kiểu collection” để kết luận mọi kích thước đều an toàn.

### 11.2. TTL và tombstone

Với non-frozen collection, việc cập nhật phần tử của `map`/`set` có thể mang TTL riêng cho phần tử mới hoặc được cập nhật. Ví dụ:

~~~sql
-- TTL chỉ áp dụng cho phần tử map vừa cập nhật ở statement này.
UPDATE customer_preferences_by_id USING TTL 3600
SET notification_settings['push'] = true
WHERE customer_id = 8f6e37fa-7af2-47e2-b4be-542e83a83848;
~~~

Không suy luận rằng toàn bộ `notification_settings` hoặc cả hàng sẽ hết hạn sau một giờ. Khi xóa phần tử hoặc hết TTL, Cassandra có thể sinh **tombstone**; collection có thay đổi/xóa thường xuyên cần được theo dõi.

Với frozen collection, TTL vận hành ở mức giá trị frozen như một đơn vị. Nếu ứng dụng cần TTL độc lập và truy vấn riêng cho từng item, hãy cân nhắc một **bảng khác có một hàng cho mỗi item**.

### 11.3. Consistency level không phải transaction đa phần tử

Các mức như `LOCAL_ONE` và `LOCAL_QUORUM` quy định yêu cầu phản hồi replica cho từng thao tác tùy keyspace replication. Chúng **không tự biến** một chuỗi đọc-sửa-ghi collection của ứng dụng thành transaction có isolation giống hệ quan hệ.

Ví dụ hai writer đồng thời:

~~~text
Writer A đọc tags = {'new'}
Writer B đọc tags = {'new'}
A lưu toàn bộ tags = {'new', 'vip'}
B lưu toàn bộ tags = {'new', 'beta'}

Một thay đổi có thể bị ghi đè nếu lưu lại snapshot cũ.
~~~

Khi phù hợp, thay vì vòng `read → add Java → save entity`, dùng cập nhật phần tử CQL:

~~~sql
UPDATE customer_preferences_by_id
SET tags = tags + {'vip'}
WHERE customer_id = ?;
~~~

Dù vậy, update từng phần tử không tạo phép so sánh phiên bản trên toàn bộ nghiệp vụ. Nếu ứng dụng cần điều kiện “chỉ đổi cấu hình khi phiên bản hiện tại là X”, hãy xem xét **lightweight transaction (LWT)** hoặc mô hình kiểm soát version/command phù hợp; LWT có chi phí cao hơn và cần kiểm tra tính tương thích của điều kiện CQL cụ thể.

### 11.4. Dấu hiệu cần đo

Theo dõi:

- Kích thước serialized và số phần tử của từng collection theo percentile, đặc biệt các hàng lớn nhất.
- p50/p95/p99 latency của truy vấn đọc profile theo partition key.
- Tần suất list append/prepend, thao tác theo index, timeout và retry.
- Tombstone scan, compaction, memory/GC và byte trả về từ driver.
- Số thao tác cùng lúc lên một hàng/partition và tỷ lệ cập nhật cạnh tranh.
- Chi phí đọc/ghi khi chuyển sang access table khác, gồm fan-out, paging state, consistency và replication.

Việc thay repository blocking bằng reactive repository **không tự giảm** chi phí đọc một collection lớn. Mô hình gọi dữ liệu và mô hình lưu dữ liệu phải được tối ưu riêng.

## 12. Lỗi thường gặp và cách tránh

| Sai lầm | Biểu hiện | Cách sửa |
|---|---|---|
| Dùng `list` cho tập tag | Có tag trùng, append khi retry lặp | Dùng `set` nếu không cần thứ tự hoặc phần tử trùng |
| Dùng `set` cho lịch sử thao tác | Mất ý nghĩa thứ tự/lặp, khó paging | Dùng bảng sự kiện theo khóa và thời gian |
| Dùng `map` chứa hàng nghìn item độc lập | Hàng rất lớn, không paging phần tử | Tách thành bảng có một hàng cho mỗi item |
| Gọi `save(entity)` để thêm một tag khi nhiều writer | Snapshot cũ ghi đè thay đổi mới | Cân nhắc thao tác cập nhật phần tử hoặc version control |
| Retry `list = list + [...] ` sau timeout | Có thể thêm phần tử hai lần | ID ổn định và lưu event theo hàng riêng nếu cần idempotency |
| Dùng `set` để giữ thứ tự người dùng | Hiển thị không theo thứ tự thêm | Chọn list nhỏ hoặc mô hình riêng có cột thứ tự |
| Dùng frozen map nhưng update một key | CQL không hỗ trợ sửa phần tử riêng | Thay cả map hoặc đổi sang non-frozen |
| Chỉ sửa type annotation trong Java | Không khớp schema vật lý | Migration CQL có kiểm soát |
| Truy vấn `WHERE tags CONTAINS ?` trên bảng không có đường đọc phù hợp | Bị từ chối hoặc chi phí truy vấn khó dự đoán | Đánh giá index phù hợp theo version, hoặc bảng đọc theo tag |
| Dùng `LIMIT 20` và nghĩ map được chia trang | Vẫn phải xử lý toàn bộ giá trị map của một hàng | Giới hạn map hoặc chuyển thành nhiều hàng |
| Lưu `null` trong collection | Lỗi binding/CQL hoặc không có ngữ nghĩa mong muốn | Thiết kế giá trị hợp lệ; xử lý vắng mặt ở tầng nghiệp vụ |

## 13. Bài tập thực hành

Một hệ thống thương mại có các yêu cầu:

1. Mỗi sản phẩm có tối đa 15 nhãn `tags`, không cần thứ tự.
2. Mỗi khách chọn bật/tắt đúng ba kênh `email`, `sms`, `push`.
3. Một đơn hàng chứa vài mục ghi chú hiển thị theo thứ tự, các ghi chú có thể trùng.
4. Mỗi khách có thể tạo hàng triệu lượt xem sản phẩm; API cần 50 lượt gần nhất và xem trang tiếp.
5. Nhóm sản phẩm muốn tìm tất cả sản phẩm mang tag `sale` mà không biết trước product ID.

**Hãy chọn kiểu dữ liệu và giải thích đường truy vấn:**

| Yêu cầu | Hướng giải tham khảo |
|---|---|
| 1 | `set<text>` trong bảng sản phẩm, giới hạn tối đa 15 giá trị |
| 2 | `map<text, boolean>` trong bảng preferences của khách; chuẩn hóa key |
| 3 | `list<text>` nếu thật sự ít và có ranh giới kích thước; xem xét retry nếu append |
| 4 | **Bảng riêng** `views_by_customer_day`, mỗi lượt xem là một hàng với clustering theo thời gian và ID |
| 5 | Bảng truy cập `products_by_tag` hoặc index tương thích với phiên bản Cassandra và yêu cầu tải |

Ví dụ CQL để giải quyết (4):

~~~sql
CREATE TABLE views_by_customer_day (
    customer_id uuid,
    view_day date,
    viewed_at timestamp,
    view_id uuid,
    product_id uuid,
    PRIMARY KEY ((customer_id, view_day), viewed_at, view_id)
) WITH CLUSTERING ORDER BY (viewed_at DESC, view_id ASC);

SELECT viewed_at, view_id, product_id
FROM views_by_customer_day
WHERE customer_id = ?
  AND view_day = ?
LIMIT 50;
~~~

Hãy giải thích vì sao thêm `List<View>` vào entity khách hàng không đáp ứng tốt việc paging và lọc thời gian. Nếu một khách có lưu lượng quá lớn trong một ngày, hãy đề xuất cách chia bucket nhỏ hơn và nêu chi phí tăng số partition cần truy vấn.

### Câu hỏi tự kiểm tra

1. CQL `set` khác `list` về phần tử trùng và thứ tự ra sao?
2. Thao tác `UPDATE ... SET list = list + [...] ` có an toàn để retry mù sau timeout không? Vì sao?
3. `frozen<map<text, boolean>>` có cho phép `SET settings['sms'] = true` không?
4. `repository.save(entity)` có tự bảo đảm tránh ghi đè khi hai request cùng sửa collection không?
5. `CassandraPageRequest.first(20)` có giới hạn 20 phần tử của một `map` trong một hàng không?
6. Vì sao muốn tìm tất cả user có tag `vip` không thể mặc định truy vấn tối ưu bằng bảng `customer_preferences_by_id`?
7. TTL một phần tử non-frozen map có làm toàn bộ map hết hạn cùng lúc không?

**Đáp án ngắn:** (1) `set` độc nhất, không có thứ tự thêm; `list` có thứ tự vị trí và cho phép trùng; (2) không, append có thể lặp; (3) không, phải thay cả frozen map; (4) không, cần kiểm soát concurrency; (5) không, paging các hàng; (6) bảng phân vùng theo `customer_id`, chưa có đường đọc theo tag; (7) không, TTL áp dụng cho phần tử được cập nhật.

## 14. Checklist chọn collection

- [ ] Dữ liệu gồm vài phần tử có giới hạn rõ ràng, không tăng vô hạn.
- [ ] Đã quyết định có cần thứ tự vị trí, phần tử trùng hay ánh xạ key/value.
- [ ] Chỉ dùng `list` nếu cần thứ tự/lặp; cân nhắc retry và read-before-write.
- [ ] Dùng `set` khi cần giá trị duy nhất; không kỳ vọng thứ tự thêm.
- [ ] Dùng `map` khi số khóa nhỏ, được chuẩn hóa và đã biết cách cập nhật.
- [ ] Đã phân biệt `frozen` và non-frozen trong CQL lẫn entity mapping.
- [ ] Java generic types và CQL column types khớp nhau; xử lý dữ liệu thiếu hoặc rỗng rõ ràng.
- [ ] Không dùng collection cho lịch sử lớn cần tìm, sort, TTL riêng hoặc paging từng item.
- [ ] Truy vấn đọc luôn có đường theo partition key; kiểm tra nhu cầu tìm theo phần tử collection.
- [ ] Đã xác định idempotency, concurrency, TTL/tombstone và consistency mong muốn.
- [ ] Có benchmark trên dữ liệu đại diện với p95/p99, bộ nhớ và kích thước collection.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types và Collections](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra — Creating Collections](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/collections/collection-create.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
