# Tiến hóa UDT, collection và bộ chuyển đổi dữ liệu

Ứng dụng dùng **Spring Data Cassandra** thường bắt đầu với một mô hình dữ liệu đủ đơn giản: đơn hàng có địa chỉ giao hàng kiểu UDT (*user-defined type*), một tập nhãn `set<text>` và một bản đồ thuộc tính `map<text,text>`. Theo thời gian, địa chỉ cần thêm mã quốc gia, bản đồ thuộc tính cần kiểu dữ liệu chặt hơn, còn hệ thống Java phải đổi DTO và converter. Nếu thay đổi trực tiếp một lần, phiên bản ứng dụng cũ có thể không hiểu schema mới, dữ liệu đã ghi có thể thiếu field và tiến trình chuyển đổi có thể bỏ sót những dòng đang được cập nhật.

Bài thuộc chương **Tiến hóa và di trú** của module **SPRING_DATA_CASSANDRA**, nơi truy cập Apache Cassandra thông qua entity mapping, repository, `CassandraTemplate` và CQL. Trọng tâm là một phương pháp có thể kiểm tra và phục hồi để **tiến hóa UDT, collection và bộ chuyển đổi dữ liệu**, đồng thời giữ đúng partition key, tính nhất quán, paging và giới hạn hiệu năng của Cassandra phân tán.

**Nguyên tắc:** Thay đổi schema, thay đổi cách mã hóa dữ liệu, thay đổi đường đọc/ghi và chuyển đổi dữ liệu lịch sử là những việc liên quan nhưng không tương đương. Một câu `ALTER TABLE` chạy thành công chỉ chứng minh schema đã nhận lệnh; chưa chứng minh toàn bộ ứng dụng và dữ liệu đã sẵn sàng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt tiến hóa tại chỗ một UDT với tạo UDT phiên bản mới và chuyển dữ liệu.
2. Xác định các giới hạn của `frozen`, UDT lồng nhau và các collection `list`, `set`, `map`.
3. Thiết kế chuyển đổi dữ liệu không mất thông tin khi đổi kiểu hoặc cấu trúc field.
4. Ánh xạ UDT với `@UserDefinedType`, entity với `@Table`, và tách nghiệp vụ chuyển đổi khỏi mapper khi cần.
5. Sử dụng custom conversion của Spring Data Cassandra có phạm vi phù hợp và kiểm thử hai chiều Java–CQL.
6. Thực hiện quy trình **expand → migrate → cutover → contract** có kiểm soát tương thích và rollback.
7. Tổ chức backfill theo partition/token range, checkpoint, retry, idempotency và reconciliation.
8. Đo đúng số liệu vận hành, kiểm chứng dữ liệu cũ/mới và tránh tác động xấu đến consistency, paging, tombstone và compaction.

## 2. Tình huống mẫu: chuyển thông tin giao hàng sang mô hình mới

Giả sử ứng dụng đặt hàng ban đầu lưu địa chỉ và các thuộc tính tự do:

~~~sql
-- Keyspace một replica chỉ dành cho ví dụ và integration test.
CREATE KEYSPACE IF NOT EXISTS migration_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TYPE IF NOT EXISTS migration_lab.shipping_address_v1 (
    street text,
    city text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS migration_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    address_v1 frozen<migration_lab.shipping_address_v1>,
    labels set<text>,
    properties map<text, text>,
    updated_at timestamp,
    version bigint
);
~~~

Đường đọc phổ biến:

~~~sql
SELECT order_id, customer_id, address_v1, labels, properties, version
FROM migration_lab.orders_by_id
WHERE order_id = ?;
~~~

Một bản ghi có thể có:

~~~yaml
order_id: "..."
address_v1:
  street: "21 Nguyen Hue"
  city: "Ho Chi Minh City"
  postal_code: "700000"
labels: ["vip", "fragile"]
properties:
  source: "mobile"
  priority: "2"
  gift: "true"
version: 7
~~~

Nhu cầu mới:

- Địa chỉ phải có `country_code` bắt buộc trong nghiệp vụ, và vị trí `geo` tùy chọn.
- Thuộc tính `priority` phải là số nguyên, `gift` là boolean; không tiếp tục dựa vào chuyển đổi chuỗi tùy hứng.
- Nhãn cần chuẩn hóa giá trị cũ và có thể đổi cách biểu diễn theo nghiệp vụ.
- Dịch vụ Spring cũ và mới có thể hoạt động đồng thời trong lúc rolling deployment.
- Dữ liệu lịch sử phải đọc được, kể cả địa chỉ không có `country_code`.

Có hai hướng đáng cân nhắc:

| Hướng | Khi phù hợp | Giới hạn |
|---|---|---|
| **Tiến hóa cùng UDT** (thêm field tương thích khi CQL/phiên bản hỗ trợ) | Thay đổi nhỏ, các ứng dụng có thể chịu field mới | Không tự bổ sung dữ liệu lịch sử; cần kiểm tra tương thích codec/mapping |
| **UDT v2 + cột v2** | Đổi tên/ngữ nghĩa/kiểu field hoặc cần canary và rollback độc lập | Tốn thêm dung lượng, mutation, backfill và cơ chế đồng bộ |
| **Chuyển collection sang kiểu mới** | Muốn áp quy tắc kiểu, thứ tự, tính duy nhất mới | Chuyển dạng thường cần cột/bảng mới và logic chuyển đổi |

Phần tiếp theo dùng hướng **UDT phiên bản mới** làm ví dụ chính vì nó cho thấy đầy đủ quy trình migration. Không mặc định mọi trường hợp đều phải tạo UDT mới; đổi nhỏ đã xác minh tương thích có thể đơn giản hơn.

## 3. Hiểu UDT và ranh giới của việc tiến hóa

### 3.1. UDT là schema có tên

UDT mô tả tập trường có tên và kiểu CQL:

~~~sql
CREATE TYPE migration_lab.geo_point (
    lat double,
    lon double
);

CREATE TYPE migration_lab.shipping_address_v2 (
    street text,
    city text,
    postal_code text,
    country_code text,
    geo frozen<migration_lab.geo_point>
);
~~~

Tên `shipping_address_v1` và `shipping_address_v2` giúp hai schema đồng tồn tại; các cột tham chiếu chúng không có chung kiểu chỉ vì field trùng tên. Đối với Java Driver, dữ liệu UDT có metadata riêng về field và kiểu. Đối với Spring Data, ánh xạ Java phải khớp CQL type và cách biểu diễn của phiên bản đang dùng.

UDT nằm bên trong UDT, collection hoặc một cột còn bị ràng buộc bởi quy tắc **frozen/non-frozen** của Cassandra.

### 3.2. Frozen nghĩa là ghi/đọc như một giá trị

Trong bảng mẫu:

~~~sql
address_v1 frozen<migration_lab.shipping_address_v1>
~~~

Cassandra xử lý UDT frozen như một giá trị ở mức cell. Muốn thay `city` mà vẫn giữ `street` và `postal_code`, ứng dụng phải dựng **giá trị UDT đầy đủ cần lưu** và thay cả cột. Không suy diễn rằng có thể cập nhật field con tùy ý qua:

~~~sql
-- Không dùng cú pháp partial update này với một frozen UDT:
-- UPDATE migration_lab.orders_by_id
-- SET address_v1.city = 'Ha Noi'
-- WHERE order_id = ?;
~~~

Với các UDT không frozen ở những vị trí được Cassandra hỗ trợ, khả năng cập nhật trường riêng có thể khác. Khi thiết kế migration, phải nhìn vào **kiểu và vị trí thực tế của field**, không chỉ thấy tên UDT rồi suy luận ngữ nghĩa cập nhật.

Khi một địa chỉ chứa một UDT lồng nhau `geo`, giá trị bên trong cũng cần tuân thủ các ràng buộc kiểu lồng và `frozen`. Khả năng thay đổi một field con sâu không tương đương khả năng thay đổi nguyên giá trị bên ngoài.

### 3.3. ALTER TYPE không thay thế migration dữ liệu

Một số phiên bản Cassandra hỗ trợ dạng thêm field mới cho UDT:

~~~sql
-- Ví dụ thay đổi tương thích cần được kiểm tra trên phiên bản thật:
ALTER TYPE migration_lab.shipping_address_v1
ADD building text;
~~~

Ngay cả khi DDL thành công:

- Các giá trị UDT đã lưu **không tự có nội dung `building` nghiệp vụ**; field mới có thể được đọc là null tùy kiểu/codec và phiên bản.
- Client cũ phải được thử với metadata/type mới. Đừng cho rằng driver hoặc custom codec cũ luôn hiểu UDT đã đổi schema.
- Các trường hợp UDT được dùng trong primary key hoặc những cấu trúc có hạn chế riêng có thể không cho phép một số thao tác thay đổi.
- DDL không tự viết lại `address_v1` của hàng triệu đơn.
- Thay đổi loại của một field hiện hữu, xóa field hoặc đổi ngữ nghĩa thường cần **kiểu mới và chuyển đổi có kiểm soát**, thay vì cố ép `ALTER TYPE`.

Khả năng `ALTER TYPE`, đổi tên field và ràng buộc với type đang được dùng phụ thuộc phiên bản Apache Cassandra và loại tham chiếu. Kiểm thử câu DDL/metadata thực tế trước khi đưa vào kế hoạch. Nếu thay đổi không được hỗ trợ trực tiếp, dùng phiên bản UDT mới/cột mới là cách rõ ràng hơn.

### 3.4. Vì sao không tái sử dụng tên UDT cũ cho ngữ nghĩa mới?

Giả sử `postal_code` ở bản cũ đôi khi chứa chuỗi trống, còn bản mới bắt buộc mã bưu chính hợp lệ; hoặc `country_code` trong bản mới phải thuộc bộ mã quốc gia quy định. Nếu thay định nghĩa Java và kỳ vọng mọi giá trị cũ đều hợp lệ, mapper có thể ném lỗi hoặc trả dữ liệu bị biến đổi không kiểm soát.

Cần phân biệt:

- **Schema compatibility:** CQL type và Java codec đọc được dữ liệu.
- **Data compatibility:** giá trị cũ được diễn giải thành ý nghĩa mới đúng quy tắc.
- **API compatibility:** client API cũ/mới vẫn nhận được response hợp lệ.
- **Operational compatibility:** các phiên bản service đang chạy đồng thời không ghi đè lẫn nhau.

Một phép thử “application mới khởi động được” mới kiểm tra một phần rất nhỏ của bốn tầng trên.

## 4. Mở rộng schema theo hướng tương thích

Thêm cột v2 để ứng dụng mới có thể chuyển dần từng bản ghi:

~~~sql
CREATE TYPE migration_lab.order_attributes_v2 (
    source text,
    priority int,
    gift boolean
);

ALTER TABLE migration_lab.orders_by_id
ADD address_v2 frozen<migration_lab.shipping_address_v2>;

ALTER TABLE migration_lab.orders_by_id
ADD attributes_v2 frozen<migration_lab.order_attributes_v2>;
~~~

Bảng giờ chứa:

| Cột cũ | Cột mới | Ý nghĩa |
|---|---|---|
| `address_v1 frozen<shipping_address_v1>` | `address_v2 frozen<shipping_address_v2>` | Địa chỉ mở rộng + quốc gia + geo |
| `properties map<text,text>` | `attributes_v2 frozen<order_attributes_v2>` | Thuộc tính có kiểu rõ ràng |
| `labels set<text>` | Có thể giữ nguyên hoặc thêm `labels_v2` | Phụ thuộc yêu cầu thay đổi semantics |

**Không xóa cột cũ trong giai đoạn expand.** Cần giữ đường đọc cho phiên bản ứng dụng chưa nâng cấp và khả năng đối chiếu dữ liệu cũ/mới. Khi triển khai, đảm bảo schema đã được các node/driver nhận biết đầy đủ trước khi kích hoạt code yêu cầu cột/type mới; các prepared statement và metadata driver có thể cần cập nhật.

### 4.1. Khi nào nên thêm cột collection phiên bản mới?

Nếu chỉ chuẩn hóa nhãn từ `"VIP"` thành `"vip"`, có thể giữ `set<text>` và chuyển đổi dữ liệu theo chính sách, nhưng cần kiểm tra mọi writer hiện tại. Nếu đổi từ `set<text>` thành `list<text>` vì thứ tự ưu tiên có ý nghĩa nghiệp vụ, đó là đổi **ngữ nghĩa**, nên tạo cột mới:

~~~sql
ALTER TABLE migration_lab.orders_by_id
ADD labels_v2 list<text>;
~~~

Không giả định có thể thay tại chỗ loại `set<text>` thành `list<text>` bằng một câu `ALTER TABLE ... ALTER` trên mọi phiên bản Cassandra. Cách an toàn và dễ rollback là thêm cột mới rồi backfill.

Nếu một field trở thành khóa truy vấn mới, đổi collection không tự làm truy vấn hiệu quả. Cassandra vẫn tổ chức dữ liệu theo partition key của bảng; thường cần bảng projection phục vụ truy vấn mới chứ không dựa vào quét hoặc `ALLOW FILTERING`.

## 5. Tiến hóa collection: đúng kiểu và đúng ngữ nghĩa

### 5.1. Set — tính duy nhất và không có thứ tự chèn

`set<text>` lưu các phần tử duy nhất. Mỗi lần thêm nhãn `"vip"` trùng sẽ không tạo hai phần tử có giá trị như nhau. Nhưng `set` không diễn tả “nhãn nào đến trước” theo thứ tự thêm vào.

~~~sql
UPDATE migration_lab.orders_by_id
SET labels = labels + {'priority'}
WHERE order_id = ?;
~~~

Một lệnh cộng phần tử vào set không tương đương với cập nhật tất cả các giá trị nhãn đã tồn tại. Nếu đang chuẩn hóa chữ hoa/chữ thường, cần xác định quy tắc xử lý các cặp như `VIP` và `vip`, rồi viết lại tập nhãn kỳ vọng một cách có kiểm soát. Chú ý đến tombstone khi xóa hoặc thay các phần tử cũ.

**Test cần có:** không trùng; kết quả không dựa vào thứ tự; chuẩn hóa trùng giá trị được giải quyết rõ ràng; retry không tạo tác dụng phụ ngoài hợp đồng.

### 5.2. List — giữ thứ tự nhưng khó xử lý đồng thời theo index

`list<text>` phù hợp khi vị trí phần tử mang ý nghĩa. Nếu chuyển từ set sang list, **không thể tự suy ra thứ tự lịch sử** từ tập cũ.

Ví dụ:

~~~text
labels_v1 = {"priority", "vip"}
labels_v2 = ["vip", "priority"]
~~~

Thứ tự v2 phải được quy định bằng luật nghiệp vụ (như thứ tự cấu hình ưu tiên), không phải dựa vào thứ tự iteration của `Set` ở Java.

Với list, các thao tác theo index hoặc thêm/bớt giữa hai client cạnh tranh có thể dẫn đến kết quả khó dự đoán hoặc phải đọc trước khi ghi. Nếu trạng thái list cần kiểm soát phiên bản, dùng cơ chế điều phối và optimistic concurrency phù hợp. Đừng tự xem phép cập nhật list là thao tác cộng phần tử idempotent trong mọi kịch bản retry.

**Test cần có:** thứ tự, các phần tử trùng có được phép không, vị trí sau update, retry, ghi đồng thời, giới hạn kích thước list.

### 5.3. Map — kiểu key/value và cập nhật một entry

`map<text,text>` cho phép biểu diễn dữ liệu mở nhưng thường dễ bị lỗi kiểu ở tầng ứng dụng: `"2"` được dùng như số, `"true"` được dùng như boolean và `null` mang nhiều ý nghĩa.

Với non-frozen map, có thể cập nhật một entry:

~~~sql
UPDATE migration_lab.orders_by_id
SET properties['source'] = 'web'
WHERE order_id = ?;
~~~

Khi chuyển sang `order_attributes_v2`, cần **parse và kiểm tra**:

| Giá trị nguồn | Đích | Chính sách cần định nghĩa |
|---|---|---|
| `properties['source'] = 'mobile'` | `source text` | Giữ nguyên nếu hợp lệ |
| `properties['priority'] = '2'` | `priority int` | Parse nguyên, kiểm tra miền |
| `properties['gift'] = 'true'` | `gift boolean` | Chỉ chấp nhận tập chuỗi đã định |
| `properties['priority'] = 'high'` | `priority int` | Báo lỗi dữ liệu hoặc áp policy rõ |
| Không có key `gift` | `gift boolean` | Giá trị null hoặc default có chủ đích |
| Key không thuộc UDT v2 | Không có field tương ứng | Quyết định giữ ở legacy map, lưu riêng hay loại theo quy định |

Không âm thầm biến mọi chuỗi parse lỗi thành 0 hoặc `false`. Việc đó khiến migration chạy “thành công” nhưng làm sai nghĩa dữ liệu.

### 5.4. Frozen collection và collection chứa UDT

Ví dụ:

~~~sql
-- Trong một schema khác:
items list<frozen<migration_lab.shipping_address_v2>>
~~~

Các phần tử UDT nằm trong list phải là giá trị `frozen` theo quy tắc lồng của Cassandra. Việc UDT là frozen không khiến list tự mất thứ tự; nhưng cập nhật trường bên trong phần tử thường phải dựng lại giá trị phần tử hoặc collection theo thao tác được hỗ trợ.

Cần phân biệt:

- `frozen<map<text,text>>`: toàn bộ map được xử lý như một giá trị; không có ngữ nghĩa cập nhật từng entry như non-frozen map.
- `map<text,text>` thông thường: có thể cập nhật entry, song delete/TTL và cạnh tranh vẫn cần xem xét.
- `list<frozen<UDT>>`: list có thứ tự, các UDT element là giá trị đóng băng.
- `frozen<list<text>>`: cả list là giá trị frozen; cập nhật phần tử riêng không giống non-frozen list.

Cần kiểm tra khả năng DDL và codec với đúng version Cassandra/driver, đặc biệt khi cấu trúc lồng sâu hoặc có kiểu custom.

### 5.5. Null, empty và TTL

Không xây dựng migration dựa vào giả định tất cả tổ hợp **null / empty set / empty list / empty map** được lưu và đọc lại khác nhau ở mọi phiên bản, kiểu frozen và thao tác cập nhật. Hãy test đường viết/đọc thực tế. Nếu nghiệp vụ cần phân biệt “chưa nhập” với “đã nhập tập rỗng”, thêm trạng thái riêng hoặc quy tắc dữ liệu rõ ràng.

TTL áp dụng cho dữ liệu có thể làm field cũ và mới hết hạn ở những thời điểm khác nhau. Một backfill ghi lại dữ liệu với TTL mặc định có thể **kéo dài tuổi thọ thông tin** ngoài chính sách hoặc khiến bản v2 hết hạn sớm. Cần xác định chính sách TTL còn lại, timestamp ghi, luật retention và tác động đến tombstone trước khi chuyển dữ liệu.

## 6. Mapping UDT với Spring Data Cassandra

### 6.1. Hai Java type cho hai phiên bản CQL

Đặt hai lớp ánh xạ khác nhau để tránh một converter vô tình xử lý lẫn hai schema:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("shipping_address_v1")
public class ShippingAddressV1 {
    @Column("street")
    private String street;

    @Column("city")
    private String city;

    @Column("postal_code")
    private String postalCode;

    // Constructor và getters/setters tương thích Spring Data.
}

@UserDefinedType("shipping_address_v2")
public class ShippingAddressV2 {
    @Column("street")
    private String street;

    @Column("city")
    private String city;

    @Column("postal_code")
    private String postalCode;

    @Column("country_code")
    private String countryCode;

    @Column("geo")
    private GeoPoint geo;

    // Constructor và getters/setters tương thích Spring Data.
}

@UserDefinedType("geo_point")
public class GeoPoint {
    @Column("lat")
    private Double lat;

    @Column("lon")
    private Double lon;

    // Constructor và getters/setters.
}
~~~

Các lớp đã lược bớt constructor/accessor; chúng minh họa metadata mapping, chưa phải tệp Java chạy độc lập. Với `record`, immutable types hoặc constructor binding, kiểm tra phiên bản Spring Data Cassandra đang dùng.

### 6.2. Ánh xạ cả cột cũ và mới trong cùng entity

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRecord {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("address_v1")
    private ShippingAddressV1 addressV1;

    @Column("address_v2")
    private ShippingAddressV2 addressV2;

    @Column("labels")
    private Set<String> labels;

    @Column("properties")
    private Map<String, String> properties;

    @Column("attributes_v2")
    private OrderAttributesV2 attributesV2;

    @Column("updated_at")
    private Instant updatedAt;

    @Column("version")
    private Long version;

    // Constructor, getters/setters và mapping cho labels_v2 nếu dùng.
}
~~~

Cột `attributes_v2` yêu cầu lớp Java `OrderAttributesV2` được annotate `@UserDefinedType("order_attributes_v2")` và khai báo field `source`, `priority`, `gift` tương ứng.

**Chú ý keyspace:** `@UserDefinedType` và `@Table` ở ví dụ dùng tên không có prefix, giả sử `CqlSession`/Spring Data được cấu hình keyspace mặc định `migration_lab`. Nếu session không có keyspace mặc định, phải cấu hình mapping/keyspace/đường truy vấn nhất quán; không kết luận mapper sai chỉ vì test đang trỏ đến keyspace khác.

### 6.3. Tách DTO công khai khỏi entity đang chuyển đổi

Entity lưu cả `addressV1` và `addressV2` là chi tiết của migration. API thường chỉ nên trả một `ShippingAddressDto` thống nhất để client không phụ thuộc trạng thái chuyển cột:

~~~java
public record ShippingAddressDto(
    String street,
    String city,
    String postalCode,
    String countryCode,
    Double latitude,
    Double longitude
) {}
~~~

Reader có thể ưu tiên cột v2 đã hợp lệ, fallback về v1 với quy tắc bổ sung `countryCode` từ nguồn đáng tin cậy. Không tự động gán `country_code = "VN"` cho mọi địa chỉ lịch sử nếu dữ liệu có thể bao gồm quốc gia khác. Fallback phải có chính sách rõ: quốc gia suy ra từ địa chỉ, dữ liệu khách hàng, quy tắc miền đã được xác nhận, hoặc báo cần bổ sung.

Trong giai đoạn migrate, DTO là một lớp chống phụ thuộc schema: client API có thể nâng cấp độc lập với việc còn bao nhiêu bản ghi sử dụng cột cũ.

## 7. Bộ chuyển đổi dữ liệu: mapping khác chuyển đổi nghiệp vụ

Cần phân biệt ba tầng:

1. **CQL ↔ Java:** Spring Data Cassandra/Java Driver chuyển cột UDT, collection và scalar thành property Java theo metadata.
2. **Legacy data → domain mới:** service diễn giải các chuỗi cũ thành số, boolean, mã quốc gia và giá trị hợp lệ theo quy tắc nghiệp vụ.
3. **Domain → API DTO:** service giữ hợp đồng với client, kể cả khi cột v1/v2 cùng tồn tại.

Với UDT có field Java tương ứng CQL, nên dùng `@UserDefinedType` và mapping mặc định trước. Custom converter chỉ cần khi dữ liệu có biểu diễn đặc biệt hoặc domain muốn kiểu riêng. Không thể chỉ đăng ký custom converter rồi coi dữ liệu lịch sử đã được chuyển sang cột mới.

### 7.1. Ví dụ converter hai chiều cho value object

Thêm một cột scalar:

~~~sql
ALTER TABLE migration_lab.orders_by_id
ADD tracking_code text;
~~~

Domain cần phân biệt mã vận đơn với một chuỗi bất kỳ:

~~~java
public record TrackingCode(String value) {
    public TrackingCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "tracking code must not be blank");
        }
    }
}
~~~

Các converter có thể khai báo:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@ReadingConverter
public final class TrackingCodeReadConverter
        implements Converter<String, TrackingCode> {
    @Override
    public TrackingCode convert(String source) {
        return new TrackingCode(source);
    }
}

@WritingConverter
public final class TrackingCodeWriteConverter
        implements Converter<TrackingCode, String> {
    @Override
    public String convert(TrackingCode source) {
        return source.value();
    }
}
~~~

Ví dụ đăng ký trong ứng dụng sử dụng API `CassandraCustomConversions` tương ứng:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.convert.CassandraCustomConversions;

@Configuration
class CassandraConversionConfiguration {
    @Bean
    CassandraCustomConversions cassandraCustomConversions() {
        return new CassandraCustomConversions(List.of(
            new TrackingCodeReadConverter(),
            new TrackingCodeWriteConverter()
        ));
    }
}
~~~

Đây là ví dụ về cơ chế, không phải lời khuyên ghi đè cấu hình converter đang tồn tại. Khi dự án đã có custom conversions, cần giữ các converter cũ và kiểm tra cách đăng ký phù hợp phiên bản Spring Data, tránh làm hỏng mapping thuộc tính khác.

**Phạm vi converter rất quan trọng.** Converter `String → TrackingCode` có kiểu đích đặc trưng. Ngược lại, `Map<String,String> → OrderAttributesV2` nếu được đăng ký chung có thể tác động mọi field map cùng dạng trong hệ thống. Đối với việc chuyển legacy map thành UDT có kiểu mới, thường dễ kiểm soát hơn khi viết một **service chuyển đổi riêng theo cột/bảng**, sau đó dùng mapping UDT chuẩn để lưu.

### 7.2. Một hàm chuyển map cũ thành mô hình có kiểu

Ví dụ parser thuần Java, không đọc hay ghi Cassandra:

~~~java
import java.util.Locale;
import java.util.Map;

public record AttributesDraft(
    String source,
    Integer priority,
    Boolean gift
) {}

public final class LegacyAttributeParser {
    private LegacyAttributeParser() {}

    public static AttributesDraft parse(Map<String, String> old) {
        if (old == null) {
            return new AttributesDraft(null, null, null);
        }

        String source = old.get("source");
        if (source != null) {
            source = source.strip().toLowerCase(Locale.ROOT);
            if (!source.equals("mobile")
                    && !source.equals("web")
                    && !source.equals("partner")) {
                throw new IllegalArgumentException(
                    "Unknown source: " + source);
            }
        }

        Integer priority = null;
        String rawPriority = old.get("priority");
        if (rawPriority != null) {
            priority = Integer.valueOf(rawPriority);
            if (priority < 0 || priority > 10) {
                throw new IllegalArgumentException(
                    "priority out of range");
            }
        }

        Boolean gift = null;
        String rawGift = old.get("gift");
        if (rawGift != null) {
            switch (rawGift.strip().toLowerCase(Locale.ROOT)) {
                case "true" -> gift = true;
                case "false" -> gift = false;
                default -> throw new IllegalArgumentException(
                    "Invalid gift flag");
            }
        }
        return new AttributesDraft(source, priority, gift);
    }
}
~~~

Đưa `AttributesDraft` sang `OrderAttributesV2` là trách nhiệm mapper/domain riêng. Đoạn parser thể hiện **chính sách minh họa**, không tự áp chuẩn `source` hay khoảng `priority 0..10` cho mọi dự án. Giá trị `"high"`, `"Y"` hoặc số ngoài miền phải được phân loại và xử lý có chủ ý; không âm thầm biến thành 0/false để job có tỷ lệ thành công giả.

### 7.3. Quy tắc chuyển đổi cũng cần version

Trong rolling deployment, một service cũ có thể tiếp tục ghi `properties['gift'] = 'Y'` trong lúc bản mới chỉ chấp nhận `true/false`. Backfill chạy dài ngày lại có thể đổi rule sau lần deploy. Phải có quy tắc chuẩn hóa thống nhất, kiểm thử dữ liệu tồn tại thực tế và cách nhận biết những dòng đã được xử lý bằng phiên bản rule cũ.

Nếu thay đổi quy tắc giữa chừng, cần kế hoạch tái chạy các phạm vi ảnh hưởng hoặc một đợt reconcile mới. Một custom converter vừa được triển khai không làm các row cũ tự động đổi nội dung lưu trữ.

## 8. Quy trình expand → migrate → cutover → contract

~~~mermaid
flowchart TD
    A["EXPAND: thêm UDT/cột v2"] --> B["Triển khai reader có fallback"]
    B --> C["Writer tương thích và thu thay đổi"]
    C --> D["MIGRATE: backfill có checkpoint"]
    D --> E["Đối soát và sửa dữ liệu"]
    E -->|Chưa đạt| F["Retry/triage"]
    F --> E
    E -->|Đạt| G["CUTOVER: canary đọc v2"]
    G --> H["Theo dõi correctness, lag, latency"]
    H -->|Ổn định| I["CONTRACT: dừng phụ thuộc legacy"]
~~~

### 8.1. Expand: triển khai schema an toàn

- Tạo type v2, cột v2 và metadata cần thiết; không xóa v1.
- Đảm bảo schema được các node và driver nhận biết trước khi bật code phụ thuộc type mới.
- Deploy reader có khả năng đọc v2 và fallback v1 khi v2 chưa hợp lệ.
- Kiểm thử service cũ vẫn đọc/ghi bình thường khi schema đã mở rộng.
- Định nghĩa chính sách fallback, null/empty, quốc gia và dữ liệu parse lỗi.

Nếu reader mới được triển khai trước và biết đọc legacy, quá trình nâng cấp không phụ thuộc việc mọi row được backfill ngay lập tức.

### 8.2. Đường ghi trong giai đoạn chuyển tiếp

Với các cột cùng một row theo khóa `order_id`, có thể ghi các cột legacy và v2 trong **một UPDATE**:

~~~sql
UPDATE migration_lab.orders_by_id
SET address_v1 = ?,
    address_v2 = ?,
    properties = ?,
    attributes_v2 = ?,
    version = ?
WHERE order_id = ?
IF version = ?;
~~~

Đây là ví dụ **LWT** nếu dùng `IF`. Câu ghi được kiểm soát cạnh tranh trên phạm vi bản ghi theo semantics Cassandra, nhưng LWT có thêm round-trip/chi phí và không nên dùng mặc định cho mọi thao tác mà không đánh giá tải. Cần bind các tham số theo đúng kiểu UDT/map thay vì nối chuỗi CQL. Nếu không yêu cầu CAS, vẫn cần chiến lược chống race rõ ràng.

Điều kiện phiên bản chỉ đáng tin khi **tất cả writer liên quan** cập nhật `version` đúng quy tắc. Một service cũ sửa `address_v1` nhưng không tăng phiên bản có thể làm v2 stale dù backfill dùng LWT.

Với các bảng projection **khác partition hoặc khác bảng**, một UPDATE ở `orders_by_id` không đồng bộ chúng. Cần lưu thay đổi bền vững hoặc cơ chế event/CDC phù hợp, retry, idempotency và reconciliation. Không mặc định hai lần gọi repository là giao dịch ACID đa bảng.

### 8.3. Migrate: backfill lịch sử

Backfill nên làm việc theo phạm vi có thể checkpoint:

1. Đọc partition hoặc token range theo paging, có rate limit và giới hạn in-flight.
2. Lấy legacy fields, khóa, version và metadata retention cần thiết.
3. Chuyển đổi bằng parser/domain mapping có phiên bản.
4. Validate kết quả, ghi v2 bằng thao tác idempotent, an toàn khi chạy lại.
5. Ghi checkpoint sau khi tác vụ tương ứng được xử lý bền vững.
6. Đưa record không thể chuyển vào hàng đợi xử lý lỗi kèm nguyên nhân.
7. Replay thay đổi trong thời gian quét và đối soát với nguồn chuẩn.

Không gọi `SELECT *` toàn bảng production rồi `ResultSet.all()` để giữ hàng triệu row trong RAM. Có thể dùng công cụ bulk/offline hoặc token-range scan của driver có page size, throttling, checkpoint và xử lý vòng token ring. Tránh `ALLOW FILTERING` để tìm mọi record còn thiếu v2 khi không có index/query shape hỗ trợ.

### 8.4. Cutover: reader ưu tiên v2

Chỉ chuyển khi:

- Backfill đã bao phủ đủ phạm vi và không còn khoảng trống sự kiện.
- Parser có chính sách cho dữ liệu lỗi, không còn mismatch ngoài SLA.
- Writer mới đã được triển khai đúng quy tắc, không còn đường ghi v1-only gây stale mà không được reconcile.
- Các kiểm thử UDT, collection, converter, null/TTL, concurrent update đều đạt.
- p95/p99 latency, GC, write amplification và compaction trong ngân sách.
- Có dashboard, shadow read/canary và đường rollback.

Mở đọc v2 cho một phần nhỏ lưu lượng, so với nguồn chuẩn/legacy khi có thể, tăng dần khi các guardrail cùng đạt.

### 8.5. Contract: dọn phần legacy khi không còn phụ thuộc

Chỉ dừng ghi v1 khi mọi consumer/reader cũ đã ngừng sử dụng và kế hoạch rollback đã thay đổi tương ứng. Việc `DROP COLUMN`/`DROP TYPE` có thể không phục hồi được dữ liệu bằng cách quay lại phiên bản code cũ; chỉ thực hiện theo kế hoạch dọn schema riêng với backup, kiểm tra dependency và xác minh không còn tham chiếu đến UDT cũ.

**Rollback code không đồng nghĩa rollback dữ liệu.** Nếu writer mới đã ngừng ghi legacy từ trước, reader v1 có thể trả bản cũ. Muốn rollback được trong giai đoạn canary, cần duy trì khả năng đọc/ghi tương thích và reconcile theo cửa sổ đã định.

## 9. Ma trận tương thích khi rolling deployment

| Trạng thái | Reader | Writer | Yêu cầu |
|---|---|---|---|
| V1 ban đầu | Chỉ v1 | Chỉ v1 | Hoạt động bình thường |
| Schema mở rộng | V1 | V1 | Code cũ hiểu schema đã mở rộng |
| Reader có fallback | V2 rồi v1 | V1 | Không thiếu dữ liệu khi v2 null |
| Writer chuyển tiếp | V2/fallback | V1 và v2 | Hai biểu diễn hội tụ |
| Backfill đang chạy | V2/fallback | V1 và v2 | Không ghi lùi |
| Canary | Ưu tiên v2 | Theo cơ chế chuyển tiếp | Metrics, mismatch và rollback đạt |
| Sau contract | Chỉ v2 | Chỉ v2 | Không còn phụ thuộc legacy |

Khi service cũ và mới cùng ghi, “cột v2 không null” **không chứng minh** nó mới nhất. Có thể cần dừng writer cũ trước, đổi thứ tự deploy, hoặc replay thay đổi legacy để v2 bắt kịp. Đây là ràng buộc của kiến trúc triển khai chứ không phải lỗi riêng của Spring Data.

Thay đổi một UDT đã có client dùng có thể làm metadata/codec cũ gặp vấn đề. Kiểm tra ma trận phiên bản thật: Spring Data/Driver cũ + schema mới, Spring Data/Driver mới + dữ liệu cũ, và mixed deployment.

## 10. Chống lost update khi backfill chạy cùng writer

Tình huống:

1. Backfill đọc version 7, địa chỉ A.
2. Khách hàng cập nhật địa chỉ B, writer ghi version 8.
3. Backfill ghi v2 bằng A từ snapshot cũ.

Kết quả sai nếu backfill ghi vô điều kiện. Với source có version do tất cả writer cập nhật đúng, có thể kiểm tra:

~~~sql
UPDATE migration_lab.orders_by_id
SET address_v2 = ?,
    attributes_v2 = ?
WHERE order_id = ?
IF version = ?;
~~~

Nếu bản ghi đã lên version 8, backfill dựa trên v7 bị từ chối và phải đọc lại. Tuy nhiên:

- Nếu writer không tăng version nhất quán, guard không đủ.
- Nếu hai worker dùng cùng version nhưng rule chuyển đổi khác, kết quả vẫn không ổn định.
- LWT có latency cao hơn ghi thông thường, phải đo hiệu năng.
- LWT trên một row không bảo vệ các projection ở partition khác.
- Với dữ liệu cũ thiếu version, cần nhánh tương thích trước khi bật LWT.

**Idempotent backfill** nghĩa là xử lý lặp cùng khóa/cùng dữ liệu không tạo tác dụng phụ ngoài hợp đồng. Không tạo UUID ngẫu nhiên mới mỗi retry, không append list vô điều kiện, không tăng counter hoặc phát email ngoài ý muốn. Client timeout không chứng minh Cassandra chưa ghi; kiểm tra/readback khi kết quả chưa xác định.

## 11. Kiểm tra tính đúng đắn của chuyển đổi

So `COUNT` trước/sau là quá yếu: hai tập cùng số lượng vẫn có thể sai ID hoặc field.

### 11.1. So theo ngữ nghĩa đã quy định

~~~text
expected = normalizeLegacy(
    address_v1, properties, labels, policyVersion
)
actual = normalizeV2(
    address_v2, attributes_v2, labels_v2
)

assert expected == actual
assert sourceVersionIsComparable
~~~

`normalizeLegacy` phải định nghĩa chính xác quy tắc null, blank string, country code, chuyển `String → Integer`, `String → Boolean`, set/list và field không còn được giữ lại.

| Legacy | V2 | Phân loại |
|---|---|---|
| `priority = "2"` | `priority = 2` | Tương đương |
| `gift = "true"` | `gift = true` | Tương đương |
| `city = "HCMC"` | `city = "Ho Chi Minh City"` | Chỉ đúng nếu rule chuẩn hóa hợp lệ |
| Không có mã quốc gia | `country_code = "VN"` | Chỉ đúng nếu có căn cứ suy ra |
| `priority = "high"` | `priority = 0` | Sai nếu không có rule |
| `labels set` | `labels_v2 list` | Cần rule xác định thứ tự |

Nếu v1/v2 đang được ghi liên tục, phải so tại thời điểm/phiên bản có thể đối chiếu. Không xem mismatch vì dữ liệu được cập nhật giữa hai lần đọc là lỗi converter mà chưa phân loại.

### 11.2. Kiểm thử hai chiều Java và CQL

- **Spring write → CQL read:** lưu qua repository/`CassandraTemplate`, đọc bằng `CqlSession` và `UdtValue` để kiểm tra UDT field/collection thực tế.
- **CQL write → Spring read:** tạo fixture bằng prepared statements/driver codec, đọc qua Spring Data để kiểm tra deserialization và custom conversions.
- **API old/new → oracle:** cùng fixture ổn định, so DTO cho toàn bộ field có ý nghĩa, kể cả null/empty, đúng collection semantics và lỗi parse.
- **Race/retry:** update source giữa backfill, gửi event trùng hoặc sai thứ tự, timeout rồi chạy lại, xác minh kết quả hội tụ.

Chỉ viết test “save rồi findById cùng entity” có thể che một lỗi đối xứng giữa converter ghi và đọc. Cần kiểm tra giá trị độc lập ở CQL hoặc nguồn dữ liệu chuẩn.

### 11.3. Chỉ số đối soát

Theo dõi số partition/row đã quét, đã ghi v2, bỏ qua, lỗi parse, cần retry; số mismatch theo loại: thiếu v2, stale version, sai typed value, null/default sai, mất field nested UDT, collection sai, TTL/retention khác. Dùng một số mẫu định danh đủ để điều tra nhưng tránh ghi dữ liệu nhạy cảm vào log.

Job xử lý hết token range **không đồng nghĩa migration hoàn tất** nếu còn dữ liệu chuyển lỗi, retry hoặc sai lệch chưa được giải quyết.

## 12. Bộ kiểm thử bắt buộc trước khi cutover

Một migration thành công phải kiểm tra **cả schema, converter, dữ liệu đã chuyển và đường ghi đang chạy**. Nên tách các lớp test để tìm được nguyên nhân khi lỗi:

- **Unit test:** quy tắc parse, chuẩn hóa, fallback, tính idempotent và sinh UDT v2 từ source.
- **Integration test trên Cassandra thật:** DDL, UDT metadata, `frozen`, collection, `@UserDefinedType`, repository, `CassandraTemplate`, CQL readback, LWT và retry.
- **Migration rehearsal:** backfill trên một bản sao/snapshot dữ liệu đại diện, kiểm tra checkpoint, restart, reconcile và thời gian chạy.
- **Canary/soak test:** mixed deployment, error rate, p95/p99, CPU/GC, Cassandra tombstone/compaction và projection lag.

### 12.1. Ma trận regression

| ID | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| U01 | Legacy UDT chỉ có ba field | Reader mới fallback và diễn giải đúng |
| U02 | V2 có `country_code` + nested `geo` | Java/CQL hai chiều giữ đủ field |
| U03 | V2 không có `geo` | Không tự sinh tọa độ giả |
| U04 | UDT frozen thay địa chỉ | Không mất các field không đổi |
| U05 | DDL thêm field vào UDT cũ nếu được hỗ trợ | Client cũ/mới tương thích theo contract |
| U06 | Đọc type v2 bằng mã Java cũ | Chỉ những đường đã cam kết tương thích được dùng |
| C01 | `set` có nhãn trùng | Không có phần tử trùng |
| C02 | `set → list` | Thứ tự do rule quy định, không từ iteration |
| C03 | `map` thiếu `priority` | Xử lý null/default đúng policy |
| C04 | `priority = "high"` | Có lỗi dữ liệu được phân loại, không âm thầm biến 0 |
| C05 | `gift = "true"/"false"` | Đúng boolean |
| C06 | `gift = "Y"` | Xử lý theo rule đã định, không đoán |
| C07 | Collection null và rỗng | Đúng semantics phiên bản Cassandra/driver |
| C08 | Cập nhật một map entry | Không ghi mất entry khác |
| M01 | Spring write → CQL read | Giá trị UDT/collection thực khớp |
| M02 | CQL write → Spring read | Mapper/converter deserialize đúng |
| M03 | Hai lớp converter đã đăng ký | Không mất converter cũ |
| M04 | Java mapper mới đọc bản ghi lịch sử | Không throw do field tùy chọn |
| B01 | Backfill cùng một record hai lần | Kết quả giống nhau, không nhân dữ liệu |
| B02 | Dừng job giữa token range rồi restart | Không mất phần chưa xử lý |
| B03 | Source tăng version giữa read và write | Backfill không ghi lùi cột v2 |
| B04 | Timeout sau mutation có thể đã thành công | Retry/readback không nhân đôi tác dụng |
| B05 | Một record parse lỗi | Quarantine và tiếp tục record khác |
| B06 | Một worker khác cũng xử lý cùng key | Guard/điều phối bảo toàn bản mới nhất |
| D01 | Writer v1 và v2 chạy cùng giai đoạn | Reconcile phát hiện stale và hội tụ |
| D02 | Cutover rồi rollback đọc | v1 còn dữ liệu đúng trong cửa sổ rollback |
| D03 | TTL hoặc xóa record | Không hồi sinh dữ liệu đã hết hạn |
| P01 | Backfill tăng tải ở peak traffic | Giới hạn lỗi/latency vẫn đạt |
| P02 | Nhiều row có collection lớn | Bộ nhớ và thời gian scan trong ngân sách |

### 12.2. Ví dụ unit test cho quy tắc parse

Dùng JUnit 5 và AssertJ để kiểm tra hàm `LegacyAttributeParser` ở mục 7:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;
import org.junit.jupiter.api.Test;

class LegacyAttributeParserTest {
    @Test
    void parsesKnownLegacyValues() {
        AttributesDraft actual = LegacyAttributeParser.parse(
            Map.of(
                "source", "MOBILE",
                "priority", "2",
                "gift", "true"
            )
        );

        assertThat(actual)
            .isEqualTo(new AttributesDraft("mobile", 2, true));
    }

    @Test
    void rejectsInvalidPriority() {
        assertThatThrownBy(() -> LegacyAttributeParser.parse(
            Map.of("priority", "high")))
            .isInstanceOf(NumberFormatException.class);
    }

    @Test
    void preservesMissingValuesAsNull() {
        assertThat(LegacyAttributeParser.parse(Map.of()))
            .isEqualTo(new AttributesDraft(null, null, null));
    }
}
~~~

Đoạn test dùng trực tiếp code parser minh họa; bài toán thật có thể muốn bọc `NumberFormatException` thành lỗi migration có mã riêng, kèm nguồn dữ liệu và lý do để vận hành xử lý. Khi đó sửa test tương ứng với hợp đồng thực tế.

### 12.3. Kiểm thử lỗi cạnh tranh bằng Cassandra thật

Một kịch bản quan trọng:

~~~text
Given:
  order_id = X
  address_v1 = A
  version = 7

When:
  backfill đọc X ở version 7
  writer trực tuyến cập nhật address_v1 = B, address_v2 = B, version = 8
  backfill thử ghi address_v2 = convert(A) IF version = 7

Then:
  conditional write của backfill không applied
  address_v2 vẫn là B
  backfill đọc lại source và không đánh dấu snapshot v7 là đã migrate
~~~

Có thể viết integration test dùng `CqlSession` và `ResultSet.wasApplied()` để kiểm tra điều kiện LWT thực sự. Unit test mock repository chỉ chứng minh code gọi đúng method; nó không chứng minh Cassandra áp dụng điều kiện và timestamp theo mong đợi.

Với câu ghi có timeout, client có thể không biết kết quả. Test cần xác minh trạng thái cuối sau reconcile, không chỉ dựa vào exception rồi chạy lại một cách mù quáng.

### 12.4. Kiểm thử mapping UDT bằng fixture độc lập

Với Java Driver, dữ liệu CQL UDT có thể đọc dưới dạng `UdtValue`, sau đó assert `getString("country_code")`, nested `getUdtValue("geo")` và giá trị `getDouble("lat")`, `getDouble("lon")`. Với field nullable, kiểm tra null trước khi gọi getter primitive.

Một test chỉ kiểm tra `repository.save(entity)` rồi `findById` bằng cùng converter có thể không phát hiện lỗi serialize/deserialze đối xứng. Dùng fixture CQL độc lập hoặc driver metadata để đối chiếu thứ tự, tên và kiểu field.

## 13. Hiệu năng của một đợt di trú

Migration có thể khiến hệ thống bình thường đọc/ghi tốt trở nên chậm vì dùng chung coordinator, CPU, đĩa và compaction. Đặc biệt, thay toàn bộ UDT frozen hoặc collection lớn liên tục có thể làm tăng ghi và tombstone.

### 13.1. Tính chi phí cần đo

| Tín hiệu | Nguyên nhân có thể | Hành động |
|---|---|---|
| p95/p99 API tăng khi backfill | Cạnh tranh I/O/coordinator | Giảm concurrency/rate |
| Write timeout tăng | Quá tải cluster hoặc batch quá lớn | Giảm kích thước batch/công việc |
| Compaction backlog tăng | Thêm nhiều mutation/tombstone | Theo dõi, giảm tốc độ backfill |
| Heap/GC worker tăng | Đọc page hoặc collection quá lớn | Giảm page size, stream theo row |
| LWT contention tăng | Nhiều writer cùng một `order_id` | Điều phối theo khóa, xem lại CAS |
| Truy vấn quét chậm | Token range/hot partition mất cân đối | Chia nhỏ phạm vi và phân phối lại |
| Mismatch tăng dù đã backfill | Legacy writer, event lag, retry lỗi | Phân tích đường ghi/reconcile |
| Dung lượng bảng tăng mạnh | Giữ cả v1/v2 trong giai đoạn chuyển | Dự trù capacity trước khi migrate |

Không dùng batch lớn xuyên nhiều partition như công cụ mặc định tăng throughput. CQL logged batch có những bảo đảm riêng về mutation nhưng không cung cấp transaction isolation và không miễn phí; các mutation độc lập có thể phù hợp hơn với controlled concurrency.

### 13.2. Điều tiết backfill theo tình trạng cluster

Một chính sách vận hành có thể quy định:

- Mỗi worker có giới hạn số request in-flight.
- Khi p99 hoặc timeout vượt guardrail, giảm số worker/concurrency hoặc tạm dừng phát thêm thao tác.
- Retry với exponential backoff và jitter; phân biệt lỗi tạm thời và lỗi dữ liệu không thể parse.
- Checkpoint theo phạm vi được xác nhận, tránh giữ cả token range trong memory.
- Thử chạy ở nhiều mức tải và đo thời gian hoàn tất trước khi chọn tiến độ.

Không lấy ngưỡng cố định như “1000 row/s luôn an toàn” cho mọi cluster. Cần benchmark từ một đợt thử nhỏ, tính phân bố partition và chi phí UDT/collection thực tế.

### 13.3. Không đổi consistency level chỉ để migration “nhanh”

`LOCAL_ONE` có thể có latency thấp hơn `LOCAL_QUORUM` trong một số topology, nhưng đổi consistency level đồng thời với migration là thay đổi mức bảo đảm đọc/ghi. Nó không giải quyết stale projection hoặc lost update do quy tắc writer/backfill sai. Chọn consistency level theo RF, data center và hợp đồng ứng dụng, sau đó **giữ cố định khi so hiệu năng các phiên bản** nếu muốn tách ảnh hưởng của schema/converter.

Trong cluster đa replica, thao tác đọc backfill phải đủ tin cậy để không diễn giải giá trị cũ thành dữ liệu hiện tại. Đọc nhiều partition không tạo một snapshot nguyên tử toàn cluster. Sự nhất quán giữa cột v1/v2, bảng projection và sự kiện cần được quản lý ở tầng ứng dụng.

## 14. TTL, tombstone và xóa dữ liệu khi tiến hóa schema

### 14.1. Giữ đúng chính sách hết hạn

Một record cũ có thể chỉ còn 3 ngày trong retention window. Nếu migration ghi cột v2 với TTL đầy đủ 30 ngày kể từ hôm nay, dữ liệu có thể tồn tại lâu hơn chính sách ban đầu. Nếu ghi v2 mà bỏ TTL trong khi v1 đang hết hạn, cột mới có thể tồn tại vô thời hạn ngoài ý muốn.

Cần xác định:

- TTL áp dụng ở cấp cột/row theo schema và đường ghi thực tế.
- Thời gian hết hạn phải dựa vào thời điểm nghiệp vụ hay từ lúc migration.
- Metadata TTL còn lại được thu thập thế nào, với những kiểu cột CQL mà Cassandra hỗ trợ.
- Nếu TTL quá ngắn hoặc bị hết hạn giữa đọc và ghi, worker phải làm gì.
- Reconcile có được phép “hồi sinh” thông tin đã bị xóa theo chính sách không.

Nếu không thể giữ semantics retention với kiểu dữ liệu mới, phải xem đây là thay đổi chính sách có chủ đích và kiểm chứng riêng.

### 14.2. Xóa và tombstone

Xóa một phần tử collection, thay giá trị frozen UDT, xóa cột v1 hay chuyển dữ liệu giữa các bảng đều có thể làm phát sinh tombstone. Backfill không nên liên tục viết lại những dòng đã đúng; có thể dùng version/checksum/checkpoint để tránh write amplification không cần thiết.

Khi một bản ghi nguồn đã bị xóa, reconciler không nên suy diễn từ bản v2 rằng nó còn hợp lệ. Cần một nguồn sự thật hoặc hồ sơ xóa đủ để xóa/không phục hồi dữ liệu theo quy định. Nếu chỉ xóa cột v1 rồi vẫn có worker backfill đọc snapshot cũ, worker có thể tái ghi cột v2 không mong muốn.

`gc_grace_seconds`, repair của replica, compaction và cơ chế xóa phải được xét theo cấu hình/phiên bản Cassandra thực tế; không tùy tiện rút ngắn grace period để dọn tombstone nhanh hơn khi chưa hiểu nguy cơ dữ liệu đã xóa xuất hiện lại.

## 15. Những sai lầm thường gặp

**“Đã ALTER TYPE nên toàn bộ dữ liệu đã chuyển.”** DDL thay metadata; nó không thực hiện nghiệp vụ chuẩn hóa mã quốc gia, parse số hoặc sửa dữ liệu lịch sử.

**“Thêm field UDT luôn tương thích với mọi service.”** Khả năng đọc phụ thuộc phiên bản Cassandra, driver, codec và mapping. Phải thử mixed versions trên schema thật.

**“Frozen chỉ là tùy chọn tối ưu hiệu năng.”** Frozen quyết định ngữ nghĩa cập nhật toàn giá trị và hạn chế thao tác từng field. Nó ảnh hưởng trực tiếp logic migration.

**“Đổi set sang list rồi dùng thứ tự iteration của set.”** Set không có thứ tự chèn; không thể suy ra lịch sử ưu tiên từ tập không có thứ tự.

**“Map cũ parse được phần lớn là đủ.”** Record có giá trị không hợp lệ phải được phân loại và xử lý. Silent default có thể làm hỏng ý nghĩa nghiệp vụ.

**“Custom converter tự chuyển mọi row cũ.”** Converter chạy khi mapping; nó không tự backfill dữ liệu mới vào Cassandra và không giải quyết dữ liệu sai ở nguồn.

**“Repository.save cập nhật cột nào cũng an toàn.”** Khi entity chỉ được load một phần hoặc field null/unset thay đổi, câu CQL thực tế có thể không như mong đợi. Cần kiểm tra đường ghi bằng CQL readback, đặc biệt với frozen UDT và static columns nếu có.

**“Có version là không ghi lùi.”** Cột version chỉ hữu ích khi tất cả writer tuân theo hợp đồng và guard/điều phối được thực thi, không chỉ lưu con số.

**“Backfill xong tất cả token range nghĩa là đã hoàn tất.”** Còn retry, dữ liệu lỗi, sự kiện phát sinh trong lúc quét, mismatch và TTL cần giải quyết.

**“Rollback service chắc chắn quay được dữ liệu cũ.”** Nếu đã dừng dual-write hoặc drop cột, dữ liệu legacy có thể cũ/mất. Rollback cần tính cả đường ghi và phục hồi dữ liệu.

## 16. Bài tập thực hành

Một hệ thống sử dụng `shipping_address_v1` và `properties map<text,text>`. Thực hiện migration lên `shipping_address_v2` có `country_code` và `geo`, đồng thời tạo `attributes_v2` với `priority int` và `gift boolean`.

Các row dữ liệu nguồn:

| Đơn | Legacy | Điều khó |
|---|---|---|
| A | `priority="2", gift="true"`, địa chỉ ở Việt Nam có quốc gia xác minh | Có thể chuyển tự động |
| B | `priority="high"`, không có quốc gia | Không parse được, thiếu dữ liệu |
| C | `priority="3", gift="Y"` | Quy tắc boolean cũ chưa thống nhất |
| D | `properties=null`, địa chỉ hợp lệ | Phải quy định null/default |
| E | `labels={"vip","fragile"}` | Nếu đổi thành list phải định thứ tự |
| F | Địa chỉ được cập nhật từ version 7 sang 8 khi backfill đọc v7 | Nguy cơ ghi lùi |
| G | Đơn bị xóa/TTL hết hạn trong lúc migrate | Nguy cơ hồi sinh dữ liệu |

**Yêu cầu:**

1. Chọn record có thể tự động chuyển và record nào cần xử lý dữ liệu theo chính sách.
2. Viết một hàm chuyển `priority` bảo đảm không âm thầm biến `"high"` thành 0.
3. Xác định cách suy ra `country_code` có bằng chứng; nếu không có, API nên xử lý thế nào?
4. Giải thích vì sao `labels set` không đủ thông tin để tái tạo thứ tự một `list`.
5. Thiết kế bước ghi có guard để worker đọc version 7 không ghi đè version 8.
6. Đặt một bộ test Spring write → CQL read, CQL write → Spring read và retry/reconcile.
7. Lập kế hoạch cutover và rollback nếu reader mới chỉ đọc `address_v2` sau khi đủ dữ liệu.

**Hướng giải:** A có thể chuyển theo rule đã xác minh. B/C cần chính sách rõ hoặc đưa vào hàng xử lý lỗi. D cần quyết định null không tương đương mặc định bất kỳ. E phải quy định thứ tự từ nguồn ngoài. F yêu cầu điều phối hoặc conditional write thật sự; G cần áp chính sách xóa/TTL và tránh replay snapshot cũ. Từ góc độ triển khai, reader fallback, backfill có checkpoint, dual-write trong cửa sổ rollback và reconciliation là những thành phần không nên bỏ qua.

## 17. Checklist trước khi kết thúc migration

- [ ] Đã xác định nguồn dữ liệu chuẩn, schema cũ/mới và các mẫu truy vấn bị ảnh hưởng.
- [ ] Có sơ đồ UDT và collection, ghi rõ frozen/non-frozen, nested types và version áp dụng.
- [ ] Đã xác minh DDL hỗ trợ trên phiên bản Cassandra và driver thực tế.
- [ ] Đã thử Java mapping, codec, custom converter hai chiều và các trường hợp null/empty.
- [ ] Có quy tắc chuẩn hóa dữ liệu có phiên bản; các giá trị sai chuẩn được phân loại.
- [ ] Đã có reader tương thích v1/v2 và kế hoạch rolling deployment.
- [ ] Writer/update/backfill có hợp đồng version, idempotency và chống ghi lùi.
- [ ] Có checkpoint, retry, rate limit, dead-letter/quarantine và khả năng resume.
- [ ] Có reconciliation theo khóa và field, không chỉ so COUNT.
- [ ] Đã thử race, timeout, event trùng/sai thứ tự, xóa và TTL.
- [ ] Đã đo p95/p99, throughput, CPU/GC, compaction, tombstone và tăng dung lượng.
- [ ] Cutover qua canary với guardrail và dashboard rõ ràng.
- [ ] Đường rollback giữ đúng dữ liệu trong thời gian được cam kết.
- [ ] Chỉ dọn cột/type cũ sau khi chắc chắn không còn dependency và có kế hoạch phục hồi.

---

## Tổng kết

Trong Cassandra, **UDT và collection là một phần của mô hình truy cập dữ liệu phân tán**, không chỉ là cách tổ chức class Java. Đổi field, thay `frozen`, chuyển `set` sang `list` hoặc `map<text,text>` sang UDT có kiểu chặt có thể ảnh hưởng cách ghi, đọc, xử lý cạnh tranh, TTL và hiệu năng.

Spring Data Cassandra cung cấp `@UserDefinedType`, entity mapping, repository, `CassandraTemplate` và custom conversions, nhưng quy tắc chuyển dữ liệu lịch sử, checkpoint, chống ghi lùi, đối soát, cutover và rollback vẫn là trách nhiệm thiết kế ứng dụng. Hướng tiếp cận đáng tin cậy là **mở rộng schema → triển khai tương thích → backfill có kiểm soát → so sánh dữ liệu thật → chuyển đọc từng bước → dọn legacy khi an toàn**.

**Tài liệu cần đối chiếu theo phiên bản triển khai:** Apache Cassandra CQL về user-defined types, frozen values, collections, ALTER TYPE/ALTER TABLE, TTL, tombstones và lightweight transactions; Spring Data for Apache Cassandra Reference về mapping annotations, `CassandraCustomConversions`, repository và `CassandraTemplate`; DataStax Java Driver về `UdtValue`, prepared statements, metadata và paging. Các ví dụ DDL/Java của bài minh họa phương pháp và cần được kiểm tra với phiên bản Cassandra, Spring Data, driver thực tế trước khi áp dụng vào production.
