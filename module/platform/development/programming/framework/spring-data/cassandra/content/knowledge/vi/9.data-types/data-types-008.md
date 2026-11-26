# Frozen và non-frozen trong UDT hoặc collection

Trong **Apache Cassandra**, từ khóa CQL `frozen` thay đổi cách một giá trị phức hợp được lưu và cập nhật. Cùng một kiểu **user-defined type (UDT)**, `set`, `list` hoặc `map` có thể có hành vi khác nhau khi được khai báo **frozen** hoặc **non-frozen**. Khi dùng **Spring Data Cassandra**, khác biệt này ảnh hưởng trực tiếp tới entity mapping, lệnh CQL phát sinh từ repository hoặc `CassandraTemplate`, các cập nhật từng phần, TTL và chi phí vận hành.

Bài thuộc chương **Kiểu dữ liệu** của module **SPRING_DATA_CASSANDRA**. Mục tiêu là hiểu ý nghĩa lưu trữ của hai chế độ, viết đúng DDL/CQL, chọn kiểu theo truy vấn thực tế và không nhầm `frozen` với tính bất biến của đối tượng Java hoặc với cơ chế transaction.

## 1. Vì sao Cassandra cần phân biệt frozen và non-frozen?

Các kiểu đơn như `text`, `uuid` và `int` thường lưu một giá trị logic tại một cột của hàng. UDT và collection thì chứa nhiều thành phần:

- **UDT:** đối tượng có những field định danh trước, ví dụ `address` gồm `street`, `city`, `postal_code`.
- **Set:** tập hợp phần tử không trùng nhau, ví dụ nhãn `{'new', 'vip'}`.
- **Map:** tập các cặp khóa/giá trị, ví dụ `{'email': 1, 'sms': 0}`.
- **List:** dãy phần tử có thứ tự, có thể chứa phần tử trùng.

Cassandra có thể quản lý các thành phần trong UDT/collection như các **cell riêng** (non-frozen), hoặc đóng gói **toàn bộ giá trị phức hợp vào một cell** (frozen).

~~~text
non-frozen UDT/collection                 frozen UDT/collection
┌──────────────────────────┐            ┌──────────────────────────┐
│ address.street : cell    │            │ address : một cell       │
│ address.city   : cell    │            │  ├─ street               │
│ address.zip    : cell    │            │  ├─ city                 │
│                          │            │  └─ zip                  │
│ có thể cập nhật thành phần│            │ thay thế cả giá trị      │
└──────────────────────────┘            └──────────────────────────┘
~~~

Đây là sơ đồ **khái niệm** về cách Cassandra xử lý một giá trị phức hợp, không phải mô tả byte layout của SSTable. Thao tác ghi thực tế vẫn tuân theo timestamp, tombstone, consistency level và cơ chế phân tán của Cassandra.

## 2. So sánh nhanh hai cách khai báo

| Tiêu chí | Non-frozen | Frozen |
| --- | --- | --- |
| DDL | `address`, `set<text>`, `map<text, int>` | `frozen<address>`, `frozen<set<text>>`, `frozen<map<text, int>>` |
| Đơn vị lưu trữ logic | Nhiều thành phần/cell | Cả giá trị là một cell |
| Cập nhật một field UDT | Có thể khi kiểu/cấu trúc cho phép | Không; thay cả UDT |
| Cập nhật phần tử collection | Có các phép CQL theo phần tử/tập con | Phải ghi lại cả collection |
| Xóa một thành phần | Có thao tác theo field/element tương ứng | Không xóa riêng thành phần bằng phép collection/UDT thông thường |
| Cạnh tranh ghi | Các thành phần có thể có timestamp riêng | Ghi thay thế cạnh tranh trên cả giá trị |
| TTL/tombstone | Có thể tác động tới nhiều cell/thành phần | Tác động tới cell chứa toàn giá trị |
| Trường hợp thích hợp | Giá trị cần sửa từng phần | Giá trị nhỏ, thường được thay như một đơn vị |

**Không nên hiểu `frozen` là “không thể sửa dữ liệu”.** Một cột frozen vẫn có thể được `UPDATE` hoặc `INSERT` ghi đè; chỉ có điều **không cập nhật riêng thành phần bên trong bằng cú pháp cập nhật phần tử**.

Tương tự, **non-frozen không có nghĩa tự động hiệu quả hơn**. Nó chỉ cung cấp lựa chọn thao tác chi tiết hơn, kèm chi phí lưu trữ và tombstone phụ thuộc workload.

## 3. Tạo UDT và dùng cùng một kiểu ở hai chế độ

Giả sử ứng dụng quản lý hồ sơ khách hàng. Thông tin địa chỉ thanh toán `billing_address` ít thay đổi và thường thay **nguyên địa chỉ**. Địa chỉ giao hàng `shipping_address` có thể được chỉnh từng trường, ví dụ chỉ đổi thành phố.

Ví dụ tạo keyspace cho môi trường học tập, với datacenter thực sự được đặt tên `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS customer_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 1
};

USE customer_ks;

CREATE TYPE IF NOT EXISTS address (
    street      text,
    city        text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id       uuid PRIMARY KEY,
    billing_address   frozen<address>,
    shipping_address  address,
    labels            set<text>,
    label_snapshot    frozen<set<text>>
);
~~~

Trong ví dụ:

- `billing_address frozen<address>` là một **UDT frozen**; muốn thay thành phố, cần ghi lại giá trị UDT tương ứng.
- `shipping_address address` là **UDT non-frozen**; có thể cập nhật riêng field `city`.
- `labels set<text>` là **set non-frozen**; có thể thêm/xóa một phần tử bằng toán tử CQL.
- `label_snapshot frozen<set<text>>` được coi là một giá trị trọn vẹn, thích hợp khi đọc/ghi cả tập nhãn như một snapshot.

`customer_id` là partition key của bảng ví dụ; mỗi khách hàng có một hàng. Các cột địa chỉ và nhãn **không tham gia phân phối partition**. Tên datacenter và RF = 1 ở trên phục vụ minh họa; ở production cần thiết kế replication phù hợp topology và yêu cầu chịu lỗi.

**Lưu ý phiên bản:** khả năng dùng UDT non-frozen và những tổ hợp kiểu lồng nhau có khác biệt giữa các thế hệ Cassandra. Ví dụ ở đây hướng tới Cassandra hiện đại có hỗ trợ non-frozen UDT; luôn kiểm tra DDL trên **đúng phiên bản cluster** trước khi triển khai.

## 4. Cập nhật UDT frozen và non-frozen

Giả sử `customer_id` của khách hàng là UUID hợp lệ `550e8400-e29b-41d4-a716-446655440000`.

### 4.1. UDT frozen: thay cả giá trị

~~~sql
UPDATE customer_ks.customer_profiles
SET billing_address = {
    street: '12 Nguyen Trai',
    city: 'Ha Noi',
    postal_code: '100000'
}
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

Trong CQL, đây là một **UDT literal** gồm những field của kiểu `address`. Khi thay giá trị UDT frozen, hãy cung cấp đầy đủ những thành phần muốn giữ; đừng giả định trường bị bỏ qua sẽ được tự động bảo toàn như một thao tác patch.

Ví dụ ý định chỉ đổi field bên trong UDT frozen:

~~~sql
-- Không dùng cách này với cột frozen<address>.
UPDATE customer_ks.customer_profiles
SET billing_address.city = 'Da Nang'
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

Thao tác cập nhật field riêng như trên không áp dụng cho UDT frozen. Muốn đổi thành phố thì đọc/chuẩn bị giá trị địa chỉ đầy đủ, sửa ở ứng dụng, rồi ghi lại **toàn bộ** `billing_address`.

### 4.2. UDT non-frozen: có thể cập nhật một field

~~~sql
UPDATE customer_ks.customer_profiles
SET shipping_address.city = 'Da Nang'
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

Với UDT non-frozen, Cassandra có thể xử lý `city` như thành phần riêng mà không cần ứng dụng gửi lại `street` hoặc `postal_code`.

Nếu nghiệp vụ muốn thay cả địa chỉ giao hàng, vẫn có thể gán toàn bộ giá trị UDT:

~~~sql
UPDATE customer_ks.customer_profiles
SET shipping_address = {
    street: '8 Tran Phu',
    city: 'Da Nang',
    postal_code: '500000'
}
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

**Điểm cần phân biệt:** “non-frozen hỗ trợ cập nhật field riêng” không đồng nghĩa mọi API repository `save(entity)` đều tự sinh câu `SET shipping_address.city = ...`. Khi ghi một entity, converter/template có thể ghi **toàn bộ property UDT** theo cách API đó hỗ trợ. Muốn kiểm soát chính xác một field, dùng thao tác update/CQL được thiết kế rõ ràng và kiểm tra statement thực tế.

## 5. Cập nhật collection non-frozen và frozen

Với `set<text>` non-frozen:

~~~sql
-- Thêm phần tử mới.
UPDATE customer_ks.customer_profiles
SET labels = labels + {'vip'}
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;

-- Bỏ phần tử đã có.
UPDATE customer_ks.customer_profiles
SET labels = labels - {'trial'}
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

Với `frozen<set<text>>`:

~~~sql
-- Ghi lại toàn bộ tập nhãn của snapshot.
UPDATE customer_ks.customer_profiles
SET label_snapshot = {'vip', 'newsletter'}
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

Không áp dụng phép thêm/xóa phần tử theo kiểu non-frozen cho cột `label_snapshot`. Giá trị frozen được thay như **một đơn vị**.

Hai collection khác thường gặp:

~~~sql
CREATE TABLE customer_ks.preferences_by_customer (
    customer_id uuid PRIMARY KEY,
    channel_settings map<text, int>,
    recent_actions   list<text>,
    rules_snapshot   frozen<map<text, int>>
);
~~~

Với `map` non-frozen có thể cập nhật một entry:

~~~sql
UPDATE customer_ks.preferences_by_customer
SET channel_settings['email'] = 1
WHERE customer_id = 550e8400-e29b-41d4-a716-446655440000;
~~~

Với `list` non-frozen có cú pháp thêm phần tử, nhưng **list không nên được dùng như một lịch sử sự kiện không giới hạn**: thao tác theo vị trí và cập nhật/xóa có chi phí và rủi ro cạnh tranh ghi khác với một bảng nhiều hàng. Nếu cần lịch sử phân trang theo thời gian, thường thiết kế hàng và clustering key theo truy vấn thay vì dồn toàn bộ dữ liệu vào một list.

### Cẩn thận với ghi đồng thời

Giả sử hai request cùng đọc `label_snapshot = {'new'}` rồi lần lượt tạo:

~~~text
Request A -> ghi {'new', 'vip'}
Request B -> ghi {'new', 'newsletter'}
~~~

Với frozen set, hai thao tác đều **ghi lại cả giá trị**; kết quả có thể chỉ còn một tập theo cơ chế phân giải ghi của Cassandra, khiến thay đổi của một request bị mất. Với non-frozen set, các phép thêm phần tử riêng có ngữ nghĩa khác và tránh được **một số** tình huống ghi đè cả collection, nhưng vẫn cần hiểu timestamp, xóa/ghi đồng thời và tính nhất quán của Cassandra. Không suy ra rằng collection non-frozen cung cấp transaction đa thao tác.

## 6. Frozen trong kiểu lồng nhau

CQL còn cho phép những cấu trúc lồng nhau, nhưng phải phân biệt **frozen ở lớp nào**.

Ví dụ cú pháp điển hình:

~~~sql
CREATE TABLE customer_ks.address_books (
    customer_id        uuid PRIMARY KEY,
    address_list       list<frozen<address>>,
    address_book       map<text, frozen<address>>,
    address_book_copy  frozen<map<text, frozen<address>>>
);
~~~

Giải thích:

| Cột | Lớp ngoài | Lớp trong | Hành vi cần nhớ |
| --- | --- | --- | --- |
| `address_list` | `list` non-frozen | Mỗi phần tử UDT là frozen | Có các thao tác collection phù hợp trên list, nhưng không cập nhật trực tiếp một field bên trong phần tử UDT |
| `address_book` | `map` non-frozen | Giá trị UDT của từng entry là frozen | Có thể thay một entry theo key; muốn sửa field của entry phải thay cả UDT tại entry đó |
| `address_book_copy` | Toàn bộ map frozen | UDT bên trong frozen | Muốn sửa một entry phải thay toàn bộ map |

Trong nhiều phiên bản Cassandra, các UDT dùng làm phần tử của collection cần khai báo `frozen<address>`. Tương tự, những collection lồng nhau thường phải dùng frozen cho lớp trong; hãy xác minh ràng buộc CQL của phiên bản cluster thay vì suy đoán từ cú pháp Java generics.

**Ví dụ thực tế:** danh bạ có vài địa chỉ được thay cả entry có thể dùng `map<text, frozen<address>>`. Nếu một khách hàng có hàng chục nghìn địa chỉ hoặc cần tìm địa chỉ theo thành phố xuyên nhiều khách hàng, đưa tất cả vào một map thường không phải thiết kế phù hợp. Hãy nghĩ tới bảng riêng có partition key và clustering columns dựa trên truy vấn.

## 7. Hệ quả đối với TTL, tombstone và lưu trữ

Trong Cassandra, xóa dữ liệu hoặc TTL hết hạn tạo ra các dấu mốc xóa (**tombstone**) mà hệ thống xử lý trong quá trình đọc/compaction, tùy điều kiện và phiên bản.

Với collection hoặc UDT **non-frozen**, các thành phần được lưu ở nhiều cell nên cập nhật, xóa hay TTL có thể ảnh hưởng tới từng thành phần. Với kiểu **frozen**, toàn bộ giá trị được quản lý như một cell; ghi thay thế có thể tạo ra vòng đời/timestamp mới của **cả giá trị**.

Ví dụ ý nghĩa nghiệp vụ:

- `labels` non-frozen: ứng dụng có thể thêm/xóa phần tử riêng lẻ; tần suất sửa liên tục vẫn cần theo dõi tombstone và số cell.
- `label_snapshot` frozen: mỗi lần tạo snapshot mới, ghi toàn bộ tập, khiến lượng dữ liệu truyền và xử lý có thể lớn hơn so với ghi một phần tử nhỏ.
- `shipping_address` non-frozen: thay `city` không bắt buộc gửi lại những field địa chỉ khác.
- `billing_address` frozen: cập nhật địa chỉ là cập nhật một cell chứa cả địa chỉ.

**Không có kết luận “frozen luôn ít tombstone hơn”.** Chi phí phụ thuộc kiểu thao tác, TTL, xóa, compaction, số lần thay toàn bộ, kích thước giá trị và Cassandra version. Phải đo với workload thật.

Lưu ý thêm: TTL theo cell và thao tác gán nguyên giá trị có thể làm **thời hạn tồn tại của các thành phần** khác nhau giữa hai mô hình. Nếu nghiệp vụ cần xóa đồng loạt một bộ giá trị, frozen có thể dễ suy luận hơn; nếu mỗi thành phần có vòng đời riêng, non-frozen có thể linh hoạt hơn. Trước khi phụ thuộc vào TTL cụ thể của phần tử, kiểm tra cú pháp CQL và cách driver/ORM thực thi ở phiên bản đang dùng.

## 8. Mapping bằng Spring Data Cassandra

Spring Data Cassandra dùng entity mapping để chuyển giữa CQL và các object Java. Ví dụ Java rút gọn, phù hợp với bảng `customer_profiles`:

~~~java
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Frozen;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("address")
public class Address {

    private String street;
    private String city;

    @Column("postal_code")
    private String postalCode;

    // Constructor và getter/setter phù hợp với converter.
}

@Table("customer_profiles")
public class CustomerProfile {

    @PrimaryKey
    private UUID customerId;

    @Frozen
    @Column("billing_address")
    private Address billingAddress;

    @Column("shipping_address")
    private Address shippingAddress;

    @Column("labels")
    private Set<String> labels;

    @Frozen
    @Column("label_snapshot")
    private Set<String> labelSnapshot;

    // Constructor và getter/setter phù hợp với converter.
}
~~~

Trong ví dụ:

1. `@UserDefinedType("address")` khai báo type Java dùng cho CQL UDT `address`.
2. `@Frozen` trên `billingAddress` thể hiện ý định mapping cột `frozen<address>`.
3. `shippingAddress` được ánh xạ tới UDT non-frozen theo DDL của ví dụ.
4. `Set<String>` có thể đại diện cả `set<text>` và `frozen<set<text>>`; điều phân biệt nằm ở **CQL schema và mapping metadata**, không phải ở tên generic type.

Các annotation và chi tiết type resolution có thể thay đổi theo phiên bản Spring Data Cassandra. Mã trên là **minh họa mapping**, cần bổ sung constructor/accessor/kiểm thử round-trip theo phiên bản thư viện thực tế. Đừng cho rằng annotation Java có thể sửa một cột đã tồn tại từ non-frozen thành frozen lúc ứng dụng khởi động.

### Repository và CassandraTemplate có tự chuyển cập nhật thành phần không?

Một repository đồng bộ có thể được khai báo:

~~~java
public interface CustomerProfileRepository
        extends CassandraRepository<CustomerProfile, UUID> {
}
~~~

Lệnh `save(profile)` làm việc với entity được map theo schema. Nó **không phải** một “partial patch” có khả năng tự nhận biết field bên trong collection/UDT nào đã đổi rồi chỉ cập nhật thành phần đó.

Nếu ứng dụng cần cập nhật **chính xác** một field của UDT non-frozen hoặc một phần tử map/set, có thể dùng câu CQL rõ ràng qua Java Driver hay API phù hợp của `CassandraTemplate`:

~~~sql
UPDATE customer_ks.customer_profiles
SET shipping_address.city = ?
WHERE customer_id = ?;
~~~

Sử dụng **prepared statements và bind variables** cho dữ liệu từ người dùng, tránh nối chuỗi tùy ý vào CQL. Sau khi chạy, đọc lại dữ liệu qua repository hoặc template để xác minh converter đọc được dạng UDT đã ghi.

Trong cách truy cập reactive, `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate` trả `Mono`/`Flux` tương ứng, nhưng **không thay đổi** tính frozen của cột hoặc khả năng cập nhật từng thành phần theo CQL.

## 9. Frozen có thay đổi partition key, consistency và paging không?

**Không trực tiếp.** Frozen quy định cách biểu diễn/cập nhật **giá trị phức hợp**. Cassandra vẫn định tuyến dữ liệu dựa trên **partition key**, sắp xếp hàng bên trong partition theo **clustering columns**, và phục vụ truy vấn theo replication/consistency level được yêu cầu.

Ví dụ bảng sự kiện:

~~~sql
CREATE TABLE customer_ks.events_by_customer_day (
    customer_id uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    attributes  map<text, text>,
    snapshot    frozen<map<text, text>>,
    PRIMARY KEY ((customer_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

Truy vấn theo khách hàng/ngày:

~~~sql
SELECT event_time, event_id, attributes, snapshot
FROM customer_ks.events_by_customer_day
WHERE customer_id = ? AND event_day = ?
LIMIT 50;
~~~

`attributes` và `snapshot` chỉ là **cột dữ liệu** của hàng; không làm thay đổi partition key tổng hợp `(customer_id, event_day)` hoặc thứ tự clustering. Trong bảng này, chỉ vì `snapshot` là frozen không có nghĩa có thể tìm nhanh mọi hàng có một key/value bất kỳ trong map.

Khi cần lọc theo thuộc tính trên toàn hệ thống, hãy đánh giá **bảng thiết kế theo truy vấn**, index tương thích phiên bản hoặc hệ thống tìm kiếm/phân tích thích hợp. Không mặc định `ALLOW FILTERING` hoặc dùng collection lớn để thay thế một data model đúng.

Paging bằng Cassandra driver/Spring Data giúp đọc dữ liệu thành nhiều đợt; nó **không giảm kích thước giá trị frozen** mà mỗi hàng cần truyền khi cột đó được chọn. Nếu payload frozen lớn và màn hình chỉ cần thông tin nhỏ, chọn cột/projection hợp lý hoặc thiết kế dữ liệu thành các hàng riêng để giảm I/O.

## 10. Chọn frozen hay non-frozen theo access pattern

Hãy bắt đầu bằng **truy vấn và thao tác ghi thực tế**:

| Nhu cầu | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Địa chỉ ít thay đổi, ghi/đọc như một đơn vị | `frozen<address>` | Thao tác trên cả địa chỉ, mô hình cập nhật đơn giản |
| Địa chỉ cần đổi riêng city/postal code | UDT non-frozen `address` | CQL có thể cập nhật field riêng |
| Tập nhãn nhỏ, cần thêm/xóa từng nhãn | Non-frozen `set<text>` | Có toán tử cập nhật phần tử |
| Tập nhãn là ảnh chụp có kích thước giới hạn | `frozen<set<text>>` | Thay toàn bộ snapshot có chủ đích |
| Map nhỏ, thường thay từng entry | Non-frozen `map<text, int>` | Có cú pháp cập nhật entry |
| Map nhỏ, cần thay tất cả theo một phiên bản cấu hình | `frozen<map<text, int>>` | Toàn giá trị là một đơn vị |
| Lịch sử gồm hàng trăm nghìn sự kiện và cần paging | **Bảng nhiều hàng** với partition/clustering key | Tránh collection không giới hạn trong một hàng |

Hai câu hỏi nên đặt ra trước khi chọn kiểu:

1. **Ứng dụng ghi dữ liệu theo phần tử hay ghi lại cả nhóm?** Nếu nghiệp vụ thường sửa một field, non-frozen có thể hữu ích; nếu thường thay snapshot, frozen có thể rõ nghĩa hơn.
2. **Giá trị phức hợp có giới hạn kích thước và tần suất ghi không?** Một map/list/set tăng không giới hạn có thể gây độ trễ, kích thước cell/partition lớn và tốn bộ nhớ khi giải mã, dù frozen hay non-frozen.

Tránh suy luận rằng chỉ một lựa chọn là “nhanh hơn” trong mọi trường hợp. Benchmark với kích thước dữ liệu, tỷ lệ read/write, cập nhật đồng thời và topology cluster thực tế.

## 11. Những sai lầm khi triển khai và migration

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Tưởng `frozen` là dữ liệu bất biến | Có thể `UPDATE` lại **cả giá trị** | Phân biệt bất biến ở API/Java với đơn vị ghi CQL |
| Ghi `billing_address.city = ...` trên UDT frozen | CQL không hỗ trợ cập nhật field riêng | Thay toàn UDT hoặc dùng UDT non-frozen |
| Dùng `labels = labels + {...}` cho frozen set | Phép cập nhật phần tử không áp dụng | Ghi lại toàn bộ frozen set |
| Đổi `@Frozen` trong entity và nghĩ cột trên cluster đổi kiểu | Annotation không phải migration của bảng đã tồn tại | Tạo migration/tables mới theo ràng buộc của Cassandra |
| Cho phép map/list/set tăng vô hạn | Một hàng/partition có thể nặng, đọc/ghi khó dự đoán | Thiết kế bảng theo truy vấn với nhiều hàng, phân vùng hợp lý |
| Tưởng cập nhật một map entry là transaction toàn cluster | Không có giao dịch tổng quát chỉ nhờ non-frozen | Thiết kế tính nhất quán và concurrency rõ ràng |
| Bọc mọi UDT trong `frozen<>` vì dễ compile | Có thể làm mất khả năng sửa field riêng | Chọn theo access pattern và kiểm thử CQL |
| Quên frozen ở tầng type lồng nhau | DDL có thể không hợp lệ với phiên bản Cassandra | Kiểm tra cú pháp UDT/collection và driver codec |

### Thay đổi frozen/non-frozen trên cột đã có dữ liệu

Một thay đổi như:

~~~text
shipping_address address
          ↓
shipping_address frozen<address>
~~~

**Không nên được xem là việc thay đổi annotation Java.** CQL có ràng buộc đối với việc sửa type của cột đã lưu; các tổ hợp có thể không được phép `ALTER` trực tiếp hoặc cần migration dữ liệu. Cách an toàn thường là:

1. Xem schema thực tế và xác định các readers/writers đang dùng cột.
2. Tạo cột mới hoặc bảng mới với kiểu đích được Cassandra version hỗ trợ.
3. Backfill dữ liệu theo partition có giới hạn và kiểm tra giá trị tương ứng.
4. Chuyển code đọc/ghi, theo dõi latency, consistency và lỗi mapping.
5. Chỉ dọn cột/bảng cũ khi đã xác minh không còn consumer.

Spring Boot `schema-action: create_if_not_exists` không tự đồng bộ thay đổi frozen/non-frozen trên bảng đã tồn tại; `recreate` cũng không phải phương án migration an toàn cho production vì có nguy cơ mất dữ liệu.

## 12. Bài tập tự kiểm tra

**Câu 1.** Có kiểu `address` gồm ba field. Ứng dụng muốn chỉnh mỗi `city` mà không gửi lại `street`. Nên chọn kiểu cột nào?

**Đáp án:** UDT non-frozen `address` nếu phiên bản Cassandra hỗ trợ, rồi cập nhật bằng cú pháp field-level.

**Câu 2.** Cột `frozen<set<text>>` hiện là `{'a', 'b'}`. Có thể chỉ chạy `SET tags = tags + {'c'}` không?

**Đáp án:** Không theo kiểu cập nhật phần tử non-frozen. Cần ghi lại giá trị frozen mới, ví dụ `{'a', 'b', 'c'}`, và cân nhắc concurrent writes.

**Câu 3.** Vì sao `map<text, frozen<address>>` và `frozen<map<text, frozen<address>>>` khác nhau?

**Đáp án:** Kiểu thứ nhất có map ngoài non-frozen nên có thể thay entry riêng; kiểu thứ hai đóng băng **cả map**, do đó thay cả giá trị map.

**Câu 4.** Có thể dùng `@Frozen` để bảo đảm bảng Cassandra đã tồn tại tự đổi schema khi khởi động không?

**Đáp án:** Không. Annotation thể hiện ý định mapping, còn schema thực phải được quản lý bằng DDL/migration phù hợp.

**Câu 5.** Một thiết bị sinh một triệu sự kiện mỗi ngày. Có nên lưu tất cả vào `frozen<list<event>>` trong một hàng rồi dùng paging để đọc không?

**Đáp án:** Không nên. Giá trị frozen sẽ rất lớn, khó cập nhật từng phần và vẫn phải xử lý toàn bộ giá trị khi đọc cột đó. Hãy thiết kế bảng sự kiện theo partition key và clustering columns, có chia bucket thời gian nếu cần.

---

**Ghi nhớ:** **non-frozen** cho phép Cassandra xử lý các thành phần UDT/collection riêng hơn và hỗ trợ một số thao tác cập nhật từng phần; **frozen** coi cả giá trị phức hợp là một cell, thường được **thay nguyên giá trị**. Trong Spring Data Cassandra, CQL schema, Java mapping, repository và template phải thống nhất; lựa chọn frozen dựa trên **mẫu đọc/ghi, kích thước dữ liệu, concurrency và khả năng vận hành**, không chỉ dựa trên cú pháp Java.
