# Phân biệt khóa chính, khóa chỉ mục và khóa liên kết

Trong Redis, mọi phần tử dữ liệu đều được truy cập thông qua một **key**. Tuy nhiên, không phải key nào cũng mang cùng một ý nghĩa trong thiết kế ứng dụng. Khi xây dựng hệ thống với **Spring Data Redis**, ta thường cần phân biệt ba vai trò:

- **Khóa chính (primary/data key):** xác định bản ghi hoặc đối tượng cần lưu.
- **Khóa chỉ mục (index key):** giúp tra cứu một hoặc nhiều bản ghi theo thuộc tính, trạng thái hoặc thứ tự mà không phải quét toàn bộ keyspace.
- **Khóa liên kết (relationship/link key):** mô tả quan hệ giữa những bản ghi, chẳng hạn một khách hàng có những đơn hàng nào.

Đây là **cách phân loại ở mức mô hình dữ liệu ứng dụng**. Redis không có bảng, primary key, foreign key hay secondary index tổng quát giống cơ sở dữ liệu quan hệ. Spring Data Redis có thể quản lý một số key/index thay ứng dụng khi sử dụng Redis Repositories, nhưng khi thao tác trực tiếp bằng `RedisTemplate`, chính ứng dụng phải duy trì các cấu trúc phục vụ truy vấn và liên kết.

## 1. Nhìn tổng thể bằng một ví dụ cửa hàng

Giả sử hệ thống có khách hàng `42` và hai đơn hàng `1001`, `1002`. Mỗi đơn hàng có trạng thái, chủ sở hữu và thời điểm tạo.

Một thiết kế Redis minh họa:

~~~text
Khóa chính (dữ liệu của thực thể)
  shop:customer:42              HASH  {name: "Lan", tier: "GOLD"}
  shop:order:1001               HASH  {customerId: "42", status: "PAID", ...}
  shop:order:1002               HASH  {customerId: "42", status: "PENDING", ...}

Khóa chỉ mục (tra cứu theo điều kiện)
  shop:order:by-status:PAID     SET   {"1001", "1008", "1013", ...}
  shop:order:by-status:PENDING  SET   {"1002", "1010", ...}

Khóa liên kết (quan hệ khách hàng - đơn hàng)
  shop:customer:42:orders       ZSET  {"1001" → 1710000000000,
                                     "1002" → 1710000001000}
~~~

Trong ví dụ, mỗi phần tử bên trong SET/ZSET là **ID đơn hàng**, không phải toàn bộ nội dung đơn hàng. ID đó dẫn tới một khóa chính như `shop:order:1001`.

| Vai trò | Câu hỏi cần trả lời | Cấu trúc thường dùng | Giá trị/Member lưu |
|---|---|---|---|
| Khóa chính | “Đơn hàng 1001 là gì?” | HASH, STRING, JSON nếu hệ thống hỗ trợ | Thuộc tính của đơn hàng |
| Khóa chỉ mục | “Đơn nào có trạng thái PAID?” | SET, ZSET hoặc STRING ánh xạ duy nhất | ID những đơn thỏa điều kiện |
| Khóa liên kết | “Khách 42 có các đơn nào?” | SET, ZSET, LIST hoặc HASH tùy quan hệ | ID đối tượng có liên hệ |

**SET hoặc ZSET không tự xác định vai trò của một key.** Hai key đều là SET vẫn có thể khác nhau hoàn toàn về ý nghĩa: một key được dùng để tìm mọi đơn hàng theo trạng thái, key khác để lưu danh sách đơn thuộc một khách hàng. Cần đọc **quy tắc đặt tên và mục đích truy vấn**, không chỉ nhìn kiểu dữ liệu Redis.

## 2. Khóa chính: định danh và nơi chứa trạng thái của thực thể

### 2.1. Redis key là một chuỗi định danh trong một logical database

Ví dụ:

~~~redis
HSET shop:order:1001 id 1001 customerId 42 status PAID amount 250000
HGETALL shop:order:1001
HGET shop:order:1001 status
~~~

Khóa `shop:order:1001` là nơi ứng dụng xác định bản ghi đơn hàng số `1001`. Các field trong HASH chỉ là thuộc tính; field `id` có thể được lưu để hiển thị/ánh xạ object, nhưng bản thân Redis **không ép field `id` phải trùng phần cuối của key**.

Trong phạm vi một Redis logical database, tên key phải duy nhất: ghi một giá trị mới vào cùng tên key sẽ tác động lên cùng key. Redis không tự hiểu rằng `shop:order:1001` và `shop:invoice:1001` cùng chung một khóa chính nghiệp vụ.

Một key chính tốt cần có:

1. **Định danh ổn định:** ID không thay đổi vì tên người dùng, giá, trạng thái hay dữ liệu thường xuyên chỉnh sửa.
2. **Namespace rõ:** xác định ứng dụng, loại entity và ID để tránh đụng tên.
3. **Định dạng nhất quán:** mọi nơi tạo/đọc/xóa phải xây dựng key theo cùng quy tắc.
4. **Vòng đời xác định:** tồn tại vĩnh viễn, TTL ngắn hạn hay chỉ là cache snapshot đều phải được quyết định từ yêu cầu nghiệp vụ.
5. **Không làm lộ dữ liệu nhạy cảm:** ID hoặc nội dung key có thể hiện trong log, trace, dashboard và lệnh quản trị.

Nếu ID đã là UUID, có thể dùng `shop:order:550e8400-e29b-41d4-a716-446655440000`. Không nhất thiết phải có UUID; điều quan trọng là ID ổn định, không gây đụng khóa trong phạm vi nghiệp vụ.

### 2.2. Redis Repositories: `@Id` ánh xạ sang khóa chính

Spring Data Redis Repositories cho phép khai báo entity và repository:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("shop:customer")
public class CustomerSnapshot {

    @Id
    private String id;

    private String displayName;

    protected CustomerSnapshot() {
    }

    public CustomerSnapshot(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerSnapshotRepository
        extends CrudRepository<CustomerSnapshot, String> {
}
~~~

Đối tượng có ID `42` thường được ánh xạ thành một Redis HASH theo keyspace `shop:customer`, có dạng khóa chính `shop:customer:42`. Trong code Java, `@Id` xác định thuộc tính ID; `@RedisHash("shop:customer")` xác định keyspace của entity. Spring Data Redis còn có thể tạo những key nội bộ để quản lý repository và lập chỉ mục; không nên giả định toàn bộ key do framework quản lý đều tương đương với các key do ứng dụng tự đặt.

Lưu ý:

- `@Id` là khái niệm mapping của **Spring Data**, không phải một constraint primary key cấp Redis server.
- `CrudRepository.findById("42")` sử dụng cách ánh xạ ID/keyspace; không cần tự viết truy vấn quét keyspace.
- `CrudRepository.deleteById("42")` xử lý theo cơ chế repository, khác với việc xóa một hash thủ công mà không quan tâm các index nội bộ.
- Trong ứng dụng dùng Redis như **cache snapshot**, ID trong Redis có thể trùng ID tại database nguồn; điều đó không tự tạo transaction chung giữa hai hệ thống.
- Một đối tượng `@RedisHash` được lưu theo cơ chế mapping của Redis Repositories. Không nên trộn tùy tiện `HSET` bằng `RedisTemplate` với các thao tác repository trên cùng key mà không hiểu metadata/index mà repository duy trì.

### 2.3. Khóa chính không nhất thiết chứa mọi dữ liệu gốc

Nhiều hệ thống dùng PostgreSQL/MySQL làm nguồn chuẩn và Redis để tăng tốc đọc:

~~~text
Database row: orders.id = 1001          ← nguồn dữ liệu chuẩn
         │
         └── tạo bản cache/snapshot
                 ↓
Redis HASH: shop:order:1001             ← bản phục vụ truy cập nhanh
~~~

Trong mô hình này, “khóa chính Redis” có nghĩa là **key xác định bản snapshot**, không khẳng định Redis là nơi duy nhất và có tính giao dịch để lưu đơn hàng. Phải mô tả rõ nguồn dữ liệu chuẩn, TTL và quy tắc cập nhật cache.

## 3. Khóa chỉ mục: đi từ điều kiện tìm kiếm đến ID

### 3.1. Vì sao cần index key?

Redis không cung cấp truy vấn kiểu SQL sau cho mọi HASH một cách tự động:

~~~sql
SELECT id FROM orders WHERE status = 'PAID';
~~~

Nếu mỗi order chỉ nằm trong `shop:order:<id>`, ứng dụng phải biết danh sách key hoặc quét rồi đọc và lọc từng bản ghi. Quét toàn bộ keyspace cho mỗi request thường không phù hợp khi dữ liệu tăng trưởng.

Thay vào đó, nếu màn hình thường xuyên hỏi “tất cả order PAID?”, ta duy trì một **reverse lookup**:

~~~redis
SADD shop:order:by-status:PAID 1001 1008 1013
SMEMBERS shop:order:by-status:PAID
~~~

Kết quả là tập ID `{"1001", "1008", "1013"}`. Ứng dụng sau đó đọc các khóa chính `shop:order:1001`, `shop:order:1008` và `shop:order:1013` để lấy dữ liệu đầy đủ.

~~~mermaid
flowchart LR
    Q["Tìm đơn hàng PAID"] --> IDX["SET shop:order:by-status:PAID"]
    IDX --> I1["ID 1001"]
    IDX --> I2["ID 1008"]
    IDX --> I3["ID 1013"]
    I1 --> O1["HASH shop:order:1001"]
    I2 --> O2["HASH shop:order:1008"]
    I3 --> O3["HASH shop:order:1013"]
~~~

Điều này là **index do ứng dụng thiết kế**. Redis server không tự phát hiện field `status` trong HASH rồi đồng bộ SET index thay bạn.

### 3.2. Các kiểu index hay gặp

| Nhu cầu truy vấn | Cách lưu ví dụ | Gợi ý sử dụng |
|---|---|---|
| Lọc theo một thuộc tính nhiều bản ghi cùng giá trị | `shop:order:by-status:PAID` → SET ID | Tra cứu thành viên của nhóm, không cần thứ tự |
| Lấy đơn theo thời gian | `shop:order:by-created-at` → ZSET ID + timestamp | Truy vấn khoảng điểm số, thứ tự và giới hạn số kết quả |
| Lấy đơn đang chờ của một vùng | `shop:order:region:HCM:status:PENDING` → SET ID | Chỉ tạo index kết hợp khi có truy vấn thực sự |
| Tra cứu một ID qua mã ngoại vi duy nhất | `shop:order:by-external-ref:ABC-9` → STRING "1001" | Lookup một ID, cần kiểm soát trùng mã |
| Tra cứu theo điểm xếp hạng | `shop:product:by-popularity` → ZSET product ID + score | Sắp xếp theo số điểm, top-N |

**SET** thích hợp cho phép hợp/giao nhóm (`SINTER`, `SUNION`) nếu dữ liệu và topology cho phép. **ZSET** thích hợp cho thứ tự/range theo score; score là số thực, nên phải quyết định đơn vị và độ chính xác (ví dụ timestamp millisecond). **STRING** thuận tiện cho ánh xạ một giá trị duy nhất sang một ID.

Không nên tạo index cho mọi field chỉ vì “sau này có thể tìm kiếm”. Mỗi index tốn RAM và làm việc ghi, sửa, xóa trở nên phức tạp hơn.

### 3.3. Chỉ mục nhiều kết quả không đảm bảo duy nhất

Với SET:

~~~redis
SADD shop:customer:by-tier:GOLD 42
SADD shop:customer:by-tier:GOLD 57
SMEMBERS shop:customer:by-tier:GOLD
~~~

Giá trị `GOLD` có hai khách hàng là hoàn toàn hợp lệ. Nếu thuộc tính phải duy nhất, ví dụ username, chỉ đặt tên index kiểu `by-username` không tạo constraint tương đương `UNIQUE` của SQL.

Một hướng lookup duy nhất do ứng dụng quản lý:

~~~redis
SET shop:customer:by-username:lan 42 NX
GET shop:customer:by-username:lan
~~~

Tùy chọn `NX` khiến thao tác `SET` chỉ thành công khi key chưa tồn tại. Tuy nhiên, **thao tác đặt index key thành công chưa làm việc tạo customer HASH và mọi index khác trở nên nguyên tử**. Nếu sau đó tạo HASH lỗi hoặc thay username gặp cạnh tranh, hệ thống cần quy trình commit/rollback hoặc reconciliation phù hợp. Một ràng buộc duy nhất thật sự phải được bảo vệ xuyên **toàn bộ luồng tạo/cập nhật**.

### 3.4. Spring Data Redis `@Indexed`

Nếu dùng **Redis Repositories**, Spring Data Redis hỗ trợ secondary index cho các thuộc tính được khai báo bằng `@Indexed`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("shop:customer")
public class IndexedCustomer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;

    protected IndexedCustomer() {
    }

    public IndexedCustomer(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface IndexedCustomerRepository
        extends CrudRepository<IndexedCustomer, String> {

    List<IndexedCustomer> findByEmail(String email);
}
~~~

Với entity `IndexedCustomer` được lưu qua repository, framework có cơ chế duy trì secondary index cho field `email` để phục vụ truy vấn `findByEmail(...)`. Chỉ mục repository thường được hiện thực bằng các key chứa tập ID liên quan đến giá trị đã lập chỉ mục; tên key nội bộ cụ thể thuộc cơ chế mapping của framework và có thể thay đổi theo phiên bản, annotation và chiến lược keyspace.

Có ba giới hạn cần nắm:

1. **`@Indexed` không tự bảo đảm giá trị duy nhất.** Hai entity có cùng email vẫn có thể được lưu nếu nghiệp vụ không kiểm soát.
2. **Chỉ các đường ghi được framework quản lý mới được kỳ vọng duy trì index repository.** Nếu tự `HSET` field `email` qua `RedisTemplate`, index do repository tạo có thể không được cập nhật tương ứng.
3. **Không phải mọi kiểu truy vấn tùy ý đều có index.** Phải đọc phạm vi query method và khả năng index được Spring Data Redis hỗ trợ; không giả định nó là query engine tương đương SQL/JPA.

Ngoài `@Indexed`, Spring Data Redis còn có các cơ chế chỉ mục chuyên biệt (ví dụ dữ liệu địa lý) với yêu cầu mapping riêng. Bài này tập trung vào sự khác biệt vai trò của key, thay vì bao quát tất cả dạng index.

## 4. Khóa liên kết: lưu quan hệ giữa các thực thể

### 4.1. Một-nhiều: khách hàng và đơn hàng

Từ một khách hàng, ứng dụng thường muốn lấy danh sách đơn hàng của họ:

~~~redis
ZADD shop:customer:42:orders 1710000000000 1001
ZADD shop:customer:42:orders 1710000001000 1002
ZREVRANGE shop:customer:42:orders 0 19
~~~

Key `shop:customer:42:orders` biểu diễn **quan hệ** giữa customer 42 và các order. Member `1001`, `1002` là ID; score cho phép sắp xếp theo thời gian tạo. Truy vấn từ link key không trả toàn bộ order; sau khi lấy ID, ứng dụng cần dereference sang `shop:order:<id>`.

Về mặt kỹ thuật, link key này cũng là **một dạng chỉ mục tra cứu theo customer ID**. Ta gọi riêng là “khóa liên kết” để nhấn mạnh ý nghĩa domain: nó mô tả một mối quan hệ và kéo theo trách nhiệm duy trì hai phía.

Nếu chỉ cần biết customer có những order nào mà không cần sắp xếp, một SET đơn giản hơn:

~~~redis
SADD shop:customer:42:orders 1001 1002
SMEMBERS shop:customer:42:orders
~~~

Không đổi SET sang ZSET chỉ vì ZSET “nhiều tính năng hơn”: chọn cấu trúc dựa trên truy vấn thực tế và chi phí.

### 4.2. Một-nhiều hay nhiều-nhiều?

Đối với nhiều-nhiều, ví dụ học viên tham gia nhiều khóa học:

~~~text
learning:student:42:courses       SET {"spring", "redis"}
learning:course:redis:students     SET {"42", "51", "76"}
~~~

Hai key là **hai chiều của cùng một quan hệ**. Nếu cần truy vấn cả hai chiều, việc lưu hai SET giúp đọc nhanh nhưng phải cập nhật nhất quán:

~~~redis
SADD learning:student:42:courses redis
SADD learning:course:redis:students 42
~~~

Nếu chỉ ghi thành công lệnh đầu, quan hệ có thể bị nhìn thấy từ phía student nhưng không từ phía course. Cần chọn một trong các chiến lược:

- Chỉ giữ một chiều làm nguồn thông tin và chấp nhận quét/truy xuất khác ở chiều còn lại.
- Duy trì hai chiều trong một thao tác phối hợp có tính nguyên tử nếu topology cho phép.
- Chấp nhận nhất quán cuối cùng, bổ sung retry và cơ chế đối soát khi ghi lỗi.

Mỗi hướng có chi phí; việc lưu hai chiều là một **quyết định mô hình hóa**, không phải mặc định do Redis áp đặt.

### 4.3. Khóa liên kết không phải foreign key

Redis không tự ngăn những trạng thái sau:

~~~text
shop:customer:42:orders chứa ID 1001
nhưng shop:order:1001 đã bị xóa.
~~~

Member `1001` lúc này là **liên kết mồ côi** (orphan reference). Redis vẫn coi SET/ZSET hợp lệ, và không có foreign key constraint tự động xóa member. Ngược lại, order có thể tồn tại nhưng chưa được thêm vào link key nên không xuất hiện trong danh sách khách hàng.

Ứng dụng phải quyết định chính sách khi phát hiện reference mồ côi: bỏ qua khi đọc, xóa member bị hỏng, đọc lại nguồn dữ liệu chuẩn, đưa vào hàng đợi khôi phục, hoặc báo lỗi tùy yêu cầu.

### 4.4. Dùng field chứa ID hay tách link key?

Không phải quan hệ nào cũng cần key liên kết độc lập.

Với đơn hàng thuộc đúng một khách hàng, trường `customerId=42` trong HASH `shop:order:1001` đã đủ để trả lời “đơn này thuộc ai?” bằng một lần đọc. Link key `shop:customer:42:orders` chỉ cần thêm nếu phải trả lời nhanh câu hỏi ngược “khách này có những đơn nào?”.

Một quy tắc thiết kế hiệu quả:

- **Chiều đọc từ child đến parent:** cân nhắc lưu parent ID trực tiếp trong dữ liệu child.
- **Chiều đọc từ parent đến nhiều child:** cân nhắc SET/ZSET chứa child ID.
- **Chiều nào hiếm khi truy vấn:** không nhất thiết tạo thêm một key phải đồng bộ liên tục.

### 4.5. Spring Data Redis `@Reference` không tự biến Redis thành CSDL quan hệ

Spring Data Redis cung cấp `@Reference` để tham chiếu các đối tượng Redis được lưu riêng và hỗ trợ resolve reference trong quá trình mapping theo khả năng của repository.

Ví dụ mang tính minh họa về quan hệ tham chiếu:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("shop:order")
public class OrderSnapshot {

    @Id
    private String id;

    private String customerId;

    @Indexed
    private String status;

    // Constructors, getters, setters theo yêu cầu mapping.
}
~~~

Ở entity khác, một trường tham chiếu có thể được khai báo bằng `@Reference` và trỏ đến entity đã được lưu riêng. Tuy nhiên:

- Reference mapping **không phải foreign key constraint** tại Redis server.
- Không mặc định có cascade save/delete cho đối tượng được tham chiếu; mỗi entity có vòng đời riêng.
- Reference giải quyết việc biểu diễn/đọc quan hệ trong mô hình object, còn yêu cầu truy vấn “tất cả order của customer” vẫn cần cách truy cập phù hợp: secondary index, relationship key do ứng dụng quản lý hoặc nguồn dữ liệu khác.

Đừng dùng `@Reference` để ngầm giả định mọi quan hệ hai chiều, join và xóa dây chuyền sẽ hoạt động giống JPA.

## 5. Ba key làm việc cùng nhau như thế nào?

Xem luồng tạo đơn hàng `1001` của khách `42`, trạng thái `PAID`:

~~~mermaid
sequenceDiagram
    participant S as Spring Service
    participant R as Redis
    S->>R: HSET shop:order:1001 ...
    Note right of R: Dữ liệu chính
    S->>R: SADD shop:order:by-status:PAID 1001
    Note right of R: Chỉ mục theo trạng thái
    S->>R: ZADD shop:customer:42:orders timestamp 1001
    Note right of R: Liên kết customer → order
    S->>R: SMEMBERS shop:order:by-status:PAID
    R-->>S: [1001, ...]
    S->>R: HGETALL shop:order:1001
    R-->>S: customerId, status, amount, ...
~~~

**Bộ ba phải được duy trì nhất quán theo quy tắc nghiệp vụ**:

| Biến động | Khóa chính | Khóa chỉ mục | Khóa liên kết |
|---|---|---|---|
| Tạo order | Tạo HASH mới | Thêm ID vào nhóm trạng thái | Thêm ID vào danh sách order của customer |
| Đổi status `PENDING → PAID` | Sửa field `status` | Xóa ID khỏi index PENDING, thêm vào PAID | Giữ nguyên nếu customer không đổi |
| Chuyển customer (nếu được phép) | Sửa `customerId` | Giữ nguyên index status | Xóa từ customer cũ, thêm sang customer mới |
| Xóa order | Xóa HASH | Loại ID khỏi mọi index liên quan | Loại ID khỏi mọi quan hệ liên quan |
| Hết TTL trên HASH | HASH biến mất | Có nguy cơ giữ ID mồ côi nếu tự quản lý | Có nguy cơ giữ ID mồ côi nếu tự quản lý |

Từ bảng này có thể thấy: khi một field được dùng để tạo index hoặc liên kết thay đổi, **chỉ cập nhật HASH là chưa đủ**.

## 6. Một cách tổ chức key thống nhất

### 6.1. Quy ước đặt tên

Nên xây dựng một quy tắc có thể suy ra được từ loại dữ liệu, vai trò và điều kiện truy vấn:

~~~text
<app>:<entity>:<id>                         # Khóa chính
<app>:<entity>:by-<field>:<fieldValue>       # Khóa chỉ mục
<app>:<parent>:<parentId>:<children>         # Khóa liên kết
~~~

Ví dụ:

~~~text
shop:order:1001
shop:order:by-status:PAID
shop:customer:42:orders
~~~

Đây là **quy ước của ứng dụng**, không phải một chuẩn bắt buộc của Redis. Dấu `:` chỉ là ký tự phân cách, không tạo namespace bảo mật hay database con.

Tránh những tên mơ hồ như `users`, `data1` hoặc `lookup` mà không xác định vai trò. Khi nhiều loại key có thể tạo ra cùng một chuỗi, cần bổ sung marker `by-` hoặc `relation:` để không ghi nhầm một HASH bằng SET.

### 6.2. Cẩn trọng với giá trị thuộc tính trong tên index key

Khi xây dựng index theo email, URL, địa chỉ hoặc chuỗi người dùng nhập, cần xác định cách chuẩn hóa và encode:

- Email có cần phân biệt chữ hoa/thường không?
- Giá trị có chứa dấu phân cách `:` hoặc Unicode không?
- Chuẩn hóa có làm hai giá trị vốn khác nhau thành một không?
- Key có làm lộ PII hoặc thông tin bí mật qua log và công cụ quan sát không?

Với thuộc tính nhạy cảm, dùng một định danh tra cứu phù hợp, hoặc một chiến lược hash/HMAC được thiết kế với rủi ro tra cứu ngược và cách quản lý khóa bí mật được cân nhắc. Chỉ gọi `hash()` thông thường chưa đồng nghĩa an toàn thông tin.

### 6.3. Không nhầm tên key với kiểu cấu trúc

Redis phân biệt type thực tế của value. Nếu đã tồn tại `shop:order:by-status:PAID` dưới dạng STRING, lệnh `SADD` lên key đó sẽ trả lỗi kiểu dữ liệu `WRONGTYPE`. Vì thế nên có quy ước type rõ ràng cho mỗi pattern key và tránh để các phần hệ thống tạo cùng tên key bằng type khác nhau.

Các lệnh quan sát hữu ích trong môi trường thử nghiệm:

~~~redis
TYPE shop:order:1001
TYPE shop:order:by-status:PAID
TYPE shop:customer:42:orders
TTL shop:order:1001
SCARD shop:order:by-status:PAID
ZCARD shop:customer:42:orders
~~~

Kỳ vọng lần lượt có thể là `hash`, `set` và `zset`. Nếu key không tồn tại, `TYPE` trả `none`; đó không nhất thiết là lỗi logic khi cache có TTL.

## 7. Tự quản lý ba loại key bằng Spring Data Redis

### 7.1. Ví dụ dùng `StringRedisTemplate`

Đoạn code sau thể hiện rõ mỗi thao tác Redis ghi loại key nào. Nó phù hợp để **học mô hình và xây dựng read model/cache**; ba lệnh ghi độc lập **chưa bảo đảm nguyên tử**.

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderRedisView {

    private final StringRedisTemplate redis;

    public OrderRedisView(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private String orderKey(String orderId) {
        return "shop:order:" + orderId;
    }

    private String statusIndexKey(String status) {
        return "shop:order:by-status:" + status;
    }

    private String customerOrdersKey(String customerId) {
        return "shop:customer:" + customerId + ":orders";
    }

    public void putOrder(
            String orderId,
            String customerId,
            String status,
            long createdAtMillis
    ) {
        // (1) Khóa chính: HASH dữ liệu order.
        redis.opsForHash().putAll(
                orderKey(orderId),
                Map.of(
                        "id", orderId,
                        "customerId", customerId,
                        "status", status,
                        "createdAt", Long.toString(createdAtMillis)
                )
        );

        // (2) Khóa chỉ mục: SET ID theo trạng thái.
        redis.opsForSet().add(statusIndexKey(status), orderId);

        // (3) Khóa liên kết: ZSET ID của order theo khách hàng.
        redis.opsForZSet().add(
                customerOrdersKey(customerId),
                orderId,
                createdAtMillis
        );
    }

    public Map<Object, Object> getOrder(String orderId) {
        return redis.opsForHash().entries(orderKey(orderId));
    }

    public Set<String> findOrderIdsByStatus(String status) {
        Set<String> ids = redis.opsForSet().members(
                statusIndexKey(status)
        );
        return ids == null ? Set.of() : ids;
    }

    public Set<String> findRecentOrderIdsForCustomer(
            String customerId,
            long maxItems
    ) {
        if (maxItems <= 0) {
            return Set.of();
        }
        Set<String> ids = redis.opsForZSet().reverseRange(
                customerOrdersKey(customerId),
                0,
                maxItems - 1
        );
        return ids == null ? Set.of() : ids;
    }
}
~~~

Các hàm truy vấn danh sách trả về **ID**, vì SET/ZSET chỉ chứa ID. Để hiển thị từng order, cần đọc HASH theo các ID này. Có thể cân nhắc pipeline/batch để giảm số chuyến mạng, nhưng pipeline **không tự tạo transaction nguyên tử**.

Ví dụ không xử lý thay đổi status, thay đổi customer, xóa, ghi lặp, retry và cạnh tranh giữa các request. Nếu gọi `putOrder()` hai lần với cùng ID nhưng status khác nhau, index trạng thái cũ có thể giữ ID mồ côi. Đây là ví dụ cho thấy **thiết kế key phải đi kèm thiết kế vòng đời ghi**.

### 7.2. Chọn Redis Repositories hay template trực tiếp?

| Cách dùng | Điểm mạnh | Việc vẫn phải thiết kế |
|---|---|---|
| `CrudRepository` với `@RedisHash` / `@Indexed` | Framework ánh xạ object, ID và một số secondary index được quản lý | Query hỗ trợ, TTL, mapping, nguồn dữ liệu chuẩn, quan hệ phức tạp |
| `StringRedisTemplate` / `RedisTemplate` | Kiểm soát chính xác key, type, command, layout và truy vấn | Tạo/cập nhật/xóa index và link key thủ công, xử lý cạnh tranh, sửa dữ liệu mồ côi |
| Kết hợp cả hai | Có thể dùng repository cho một phần dữ liệu và template cho read model riêng | Phải xác định ranh giới ownership; không ghi đè metadata/index repository bằng thao tác thủ công |

Không nên mặc định rằng một `@Indexed` trên entity sẽ cập nhật một SET tùy ý do `StringRedisTemplate` tạo. **Index do framework quản lý** và **index ứng dụng tự quản lý** là hai cơ chế khác nhau, dù cùng chạy trên Redis.

## 8. Nhất quán khi tạo, cập nhật và xóa

### 8.1. Lỗi từng phần là nguyên nhân phổ biến nhất

Một luồng tạo ba key bằng ba lệnh:

~~~text
HSET order:1001                 ✅
SADD by-status:PAID 1001        ✅
ZADD customer:42:orders ...     ❌ timeout
~~~

Dù hai thao tác đầu đã thành công, yêu cầu tổng thể có thể bị báo lỗi. Nếu retry không cẩn thận, app có thể chèn ID vào sai index hoặc tạo các hiệu ứng phụ khác. Với SET, thêm lại cùng member là idempotent; với ZSET, thêm lại cùng member thường cập nhật score. **Tính idempotent của riêng SADD/ZADD không đủ để làm toàn bộ nghiệp vụ idempotent**.

Nếu cả ba key ở cùng một Redis instance và có thể được thao tác cùng nhau, có thể cân nhắc `MULTI/EXEC`, Lua script hoặc lệnh nguyên tử được xây dựng cho use case. Các lựa chọn này vẫn cần hiểu giới hạn:

- `MULTI/EXEC` thực thi các lệnh trong transaction Redis, nhưng không rollback mọi thay đổi kiểu SQL khi một lệnh báo lỗi lúc thực thi.
- Lua chạy cô lập với các lệnh Redis khác trong thời gian script thực thi, nhưng lỗi phát sinh sau một số thao tác cũng không tự undo những thao tác đó.
- Redis Cluster áp ràng buộc **hash slot** khi thao tác nhiều key trong một transaction/script; không thể giả định các key thuộc nhiều slot bất kỳ cùng tham gia được.
- Nếu nguồn chuẩn là PostgreSQL/MySQL, transaction Redis không gom thành một transaction ACID xuyên Redis và database quan hệ.

Với cache/read model tái tạo được, một chiến lược phổ biến là chấp nhận **eventual consistency có kiểm soát**, ghi sự kiện cập nhật khi database commit, retry idempotent và đối soát kỳ hạn. Với dữ liệu bắt buộc chính xác tuyệt đối, phải xác định kho dữ liệu có transaction phù hợp để thực thi invariant.

### 8.2. Đổi trạng thái phải cập nhật index cũ và mới

Khi `status` chuyển từ `PENDING` sang `PAID`, chuỗi thay đổi mong muốn là:

~~~redis
HSET shop:order:1002 status PAID
SREM shop:order:by-status:PENDING 1002
SADD shop:order:by-status:PAID 1002
~~~

Đây là mô tả các thao tác cần có, **không phải cam kết ba lệnh chạy nguyên tử hoặc an toàn trước hai request đồng thời**.

Nếu hai request đồng thời đổi status, cả hai có thể đọc cùng trạng thái cũ rồi ghi đè các index theo thứ tự khác nhau. Tùy yêu cầu có thể dùng kiểm soát phiên bản/optimistic locking, server-side logic, transaction phù hợp hoặc cơ chế serialized update theo ID.

Một nguyên tắc hữu ích là: **mọi field xuất hiện trong tên hoặc score của index phải có quy tắc di chuyển index khi field đổi**.

### 8.3. Đổi chủ sở hữu phải chuyển link

Nếu nghiệp vụ cho phép chuyển order `1001` từ customer `42` sang `57`, cần thay đổi field customer và hai link key:

~~~redis
HSET shop:order:1001 customerId 57
ZREM shop:customer:42:orders 1001
ZADD shop:customer:57:orders 1710000000000 1001
~~~

Với các quan hệ hai chiều, cần cập nhật cả hai phía tương ứng. Đừng tạo thêm reverse link chỉ vì thuận tiện rồi bỏ quên đường xóa/chuyển quan hệ.

### 8.4. Xóa khóa chính chưa xóa index và link tự quản lý

~~~redis
DEL shop:order:1001
~~~

Lệnh này **chỉ xóa key được nêu**. Redis không tự tìm `shop:order:by-status:PAID` hay `shop:customer:42:orders` để xóa member `1001`.

Với key tự quản lý, ứng dụng thường cần biết trạng thái cũ và customer ID trước khi xóa:

~~~text
Đọc HASH cũ → lấy status và customerId
        ↓
Loại ID khỏi index status
        ↓
Loại ID khỏi link customer
        ↓
Xóa HASH chính (hoặc phối hợp trong cùng thao tác an toàn)
~~~

Nếu nguồn chuẩn là database ngoài Redis, có thể áp dụng workflow khác (DB commit → phát sự kiện/invalidations → cập nhật read model). Dù chọn trình tự nào, phải mô tả điều gì xảy ra khi từng bước lỗi và liệu lệnh có thể được retry an toàn.

### 8.5. TTL có thể để lại member mồ côi

Giả sử đặt TTL cho hash order:

~~~redis
EXPIRE shop:order:1001 600
~~~

Sau 10 phút, HASH có thể không còn nhưng SET/ZSET tự quản lý vẫn giữ ID `1001` vì chúng là các **key độc lập**. Kết quả:

~~~text
SMEMBERS shop:order:by-status:PAID  → có "1001"
HGETALL shop:order:1001            → rỗng
~~~

Có thể chọn:

- Đặt vòng đời tương ứng cho index/link nếu các key có cùng ý nghĩa và TTL phù hợp.
- Xóa member khi xử lý tác vụ xóa/hết hạn theo cơ chế có retry và đối soát.
- Lúc đọc, bỏ qua ID không còn tồn tại và ghi nhận để dọn dẹp.
- Tái tạo index/link từ nguồn chuẩn định kỳ hoặc khi phát hiện sai lệch.

Nếu sử dụng **Spring Data Redis Repositories**, framework có hỗ trợ duy trì secondary index và các cơ chế liên quan đến sự kiện hết hạn khóa. Nhưng keyspace notification dạng Pub/Sub không phải hàng đợi bền vững; ứng dụng ngắt kết nối có thể bỏ lỡ sự kiện. Không được suy ra rằng mọi link/index tự định nghĩa luôn được dọn dẹp hoàn hảo khi TTL của entity hết hạn.

## 9. Redis Cluster làm thay đổi khả năng cập nhật nhiều key

Trong Redis Cluster, Redis đặt mỗi key vào một **hash slot**. Hai key thường thuộc các slot khác nhau, ví dụ:

~~~text
shop:order:1001
shop:order:by-status:PAID
shop:customer:42:orders
~~~

Các lệnh thao tác **nhiều key như một nhóm nguyên tử** phải tuân thủ quy tắc slot của Cluster. Nếu thiết kế yêu cầu thao tác nhiều key trong cùng slot, có thể sử dụng **hash tag** là phần nằm trong dấu ngoặc nhọn.

Ví dụ:

~~~text
shop:customer:{42}
shop:customer:{42}:orders
~~~

Hai tên này dùng cùng hash tag `42`, nên được ánh xạ vào cùng slot. Nhưng key `shop:order:{1001}` lại thuộc tag khác; không thể từ đó kết luận mọi thứ liên quan đều có thể cập nhật cùng một transaction multi-key.

Hash tag là quyết định kiến trúc:

- Nhóm nhiều key cùng customer trong một slot có thể hữu ích cho một số thao tác.
- Nhồi tất cả dữ liệu vào một tag để né lỗi CROSSSLOT có thể gây phân bố tải lệch và mất lợi thế sharding.
- Index toàn cục theo status thường chứa ID của order thuộc nhiều customer, khiến yêu cầu vừa “phân tán theo customer” vừa “cập nhật index status toàn cục nguyên tử” khó thỏa đồng thời.

Vì vậy, **cấu trúc khóa phải xét cả pattern truy vấn lẫn topology**. Thiết kế tốt ở Redis standalone không tự động có cùng thuộc tính khi chuyển sang Redis Cluster.

## 10. Khi nào index và link key trở nên tốn kém?

Mỗi index/link key tăng chi phí về dung lượng và số thao tác ghi. Đặc biệt:

1. **High cardinality:** một index theo giá trị gần như duy nhất tạo rất nhiều key nhỏ; có thể cân nhắc lookup STRING theo giá trị nếu thật sự cần.
2. **Large SET/ZSET:** một nhóm `PAID` chứa hàng triệu ID có thể tạo key lớn. `SMEMBERS` lấy toàn bộ member cùng lúc, dễ làm tăng độ trễ và kích thước phản hồi.
3. **Index update fan-out:** một thay đổi trạng thái làm thay đổi nhiều index kết hợp, tăng số lệnh và nguy cơ mất đồng bộ.
4. **Truy vấn phân trang:** `ZREVRANGE` có thứ tự; SET không có thứ tự ổn định cho pagination. Với tập lớn, cân nhắc truy vấn theo score/rank và cursor hợp lý.
5. **Dữ liệu cũ tồn đọng:** index/link không được dọn sau khi key chính xóa làm kết quả truy vấn sai và tiêu tốn RAM.

Lệnh `SCAN` giúp duyệt keyspace theo từng phần cho tác vụ bảo trì, nhưng **không thay một index truy vấn có chủ đích**. Tương tự, `SSCAN`/`ZSCAN` giúp duyệt member theo phần và có thể trả lặp; nếu cần trang kết quả theo thứ tự, phải chọn cấu trúc và chiến lược phân trang phù hợp. Không dùng `KEYS shop:order:*` trên một Redis lớn cho mỗi request người dùng.

Một bảng quyết định thiết kế:

| Câu hỏi | Nếu “có” | Gợi ý |
|---|---|---|
| Truy cập chủ yếu bằng ID chính xác? | Có | Chỉ khóa chính có thể đã đủ |
| Cần lọc nhanh theo một trạng thái? | Có | SET index theo trạng thái |
| Cần top-N / thứ tự thời gian? | Có | ZSET index hoặc relationship ZSET |
| Cần tìm từ parent đến nhiều child? | Có | SET/ZSET link tùy thứ tự |
| Cần tìm một bản ghi bằng mã duy nhất khác ID? | Có | STRING lookup có kiểm soát uniqueness |
| Dữ liệu thay đổi rất thường xuyên, quan hệ/index phức tạp? | Có | Cân nhắc giảm số index hoặc dùng database/search engine chuyên biệt làm nguồn truy vấn |

Không có quy tắc “càng nhiều index càng tốt”. Index chỉ có giá trị khi truy vấn nó phục vụ đủ quan trọng để bù chi phí duy trì.

## 11. Một quy trình thiết kế key thực tế

Giả sử yêu cầu của hệ thống:

> Hiển thị chi tiết đơn theo ID; cho phép lọc đơn theo trạng thái; hiển thị 20 đơn mới nhất của một khách hàng.

Có thể đi từ **câu hỏi truy vấn** đến key:

| Truy vấn | Key truy cập | Command tiêu biểu |
|---|---|---|
| Chi tiết order 1001 | `shop:order:1001` | `HGETALL` |
| ID của các order PAID | `shop:order:by-status:PAID` | `SMEMBERS` hoặc `SSCAN` theo nhu cầu |
| 20 order mới của customer 42 | `shop:customer:42:orders` | `ZREVRANGE 0 19` |

Sau đó mới đặt quy tắc vòng đời:

| Sự kiện nghiệp vụ | Hash chính | Status index | Customer link |
|---|---|---|---|
| Tạo order | Ghi hash | `SADD` | `ZADD` |
| Đổi status | `HSET` | `SREM` cũ / `SADD` mới | Không đổi |
| Xóa order | `DEL` | `SREM` | `ZREM` |

Nếu dữ liệu là cache có thể tái tạo, thêm TTL, reconciliation và giới hạn chấp nhận stale. Nếu là dữ liệu chuẩn có ảnh hưởng tài chính/hàng tồn kho, trước hết xác định transaction và ràng buộc tại nguồn dữ liệu thích hợp.

Với một hệ thống thực, nên ghi thành tài liệu ngắn ngay tại module: key pattern, kiểu Redis, keyspace/DB, serializer, TTL, người sở hữu ghi, query sử dụng, cách cập nhật và xóa. Đây là cách tránh việc một nhóm dùng `shop:order:1001` như HASH còn nhóm khác dùng cùng tên key như STRING.

## 12. Các sai lầm điển hình

**Sai lầm 1 — Gọi mọi Redis key là “primary key”.**

Điều đó che mất sự khác biệt giữa dữ liệu gốc và dữ liệu phục vụ truy vấn. Khi xóa `shop:order:1001`, ứng dụng có thể quên xóa các ID tham chiếu bên ngoài.

**Sai lầm 2 — Cho rằng `@Indexed` giống unique constraint của database quan hệ.**

`@Indexed` giúp tra cứu theo field trong phạm vi mapping repository. Nó không tự bảo đảm uniqueness, referential integrity hay hỗ trợ mọi kiểu join/query.

**Sai lầm 3 — Cập nhật HASH rồi mặc định index đã tự đổi.**

Với SET/ZSET tự tạo bằng template, Redis không biết field nào trong HASH tương ứng với member của index. Phải ghi rõ quy tắc đồng bộ.

**Sai lầm 4 — Dùng key liên kết như bản sao toàn bộ object.**

Nếu link key chứa bản sao object thay vì ID, cùng một đơn hàng bị nhân bản ở nhiều nơi và dễ lệch khi cập nhật. Lưu ID thường giúp có một điểm đọc dữ liệu thực thể, dù phải đánh đổi thêm bước dereference.

**Sai lầm 5 — Xóa data key hoặc hết TTL thì tưởng mọi liên kết tự mất.**

SET/ZSET độc lập vẫn còn. Đặt TTL hoặc cleanup phù hợp với từng loại key, và dự kiến khả năng sự kiện dọn dẹp bị bỏ lỡ.

**Sai lầm 6 — Dùng một transaction nhiều key như ở standalone mà không xét Cluster.**

Hash slot quyết định nhóm key nào có thể tham gia thao tác multi-key. Phải thiết kế từ nhu cầu phân vùng ngay khi có kế hoạch sharding.

**Sai lầm 7 — Truy vấn SET lớn bằng `SMEMBERS` trên mọi request.**

SET không cung cấp thứ tự kết quả; lệnh lấy tất cả member có thể trả lượng dữ liệu rất lớn. Chọn cấu trúc và cơ chế phân trang theo kích thước thực tế.

## 13. Ghi nhớ sự khác biệt cốt lõi

- **Khóa chính:** định danh thực thể và là điểm đi đến dữ liệu của thực thể, ví dụ `shop:order:1001`.
- **Khóa chỉ mục:** ánh xạ điều kiện tìm kiếm đến ID, ví dụ `shop:order:by-status:PAID`.
- **Khóa liên kết:** ánh xạ quan hệ giữa thực thể đến ID liên quan, ví dụ `shop:customer:42:orders`.

Một relationship key có thể được xem là index theo parent ID, nhưng việc tách tên và trách nhiệm thiết kế giúp người đọc hiểu rằng **đây là một quan hệ cần duy trì khi entity được tạo, chuyển chủ sở hữu hoặc bị xóa**.

Khi dùng **Spring Data Redis**, trước tiên phải chọn ai sở hữu từng key: **Redis Repositories** hay **logic ứng dụng viết bằng RedisTemplate**. Kế đến quyết định đường đọc, đường cập nhật, cơ chế tránh mất đồng bộ, TTL và topology Redis. Chỉ sau đó mới chọn SET, ZSET, HASH và cách xây dựng tên key.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Object References](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/references.html)
- [Spring Data Redis — Key Expirations](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/)
- [Redis — Sets](https://redis.io/docs/latest/develop/data-types/sets/)
- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/)
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
