# Chỉ mục trên collection, map hoặc cấu trúc theo phiên bản

> **Chương:** Chỉ mục  
> **Học phần:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, hệ cơ sở dữ liệu phân tán wide-column.

## Mục tiêu

Trong Cassandra, việc có thể viết điều kiện `WHERE` không đồng nghĩa với việc truy vấn sẽ chạy hiệu quả trên một cụm lớn. Khóa phân vùng vẫn quyết định cách dữ liệu được phân bố giữa các node; secondary index cho phép tìm theo một số cột khác nhưng có chi phí ghi, lưu trữ, bảo trì và tìm kiếm. Vấn đề khó hơn khi cột chứa `set`, `list`, `map`, kiểu `frozen`, hoặc payload thay đổi cấu trúc theo phiên bản ứng dụng.

Sau bài này, bạn sẽ:

- Xác định khi nào có thể lập chỉ mục phần tử collection, khóa map, giá trị map hoặc cặp khóa–giá trị map.
- Viết CQL tạo và truy vấn chỉ mục trên collection; phân biệt điều kiện `CONTAINS`, `CONTAINS KEY` và `map['key'] = value`.
- Phân biệt **secondary index truyền thống (2i)** và **Storage-Attached Index (SAI)**, cùng sự khác nhau về hỗ trợ giữa các phiên bản/phân phối Cassandra.
- Hiểu giới hạn của `frozen`, UDT và dữ liệu có `schema_version`; quyết định khi nào nên tạo bảng theo truy vấn thay vì tìm kiếm bằng index.
- Đánh giá hệ quả của replication, consistency level, TTL/tombstone, compaction, repair và cập nhật index từ ứng dụng Java.

## 1. Vì sao index trên collection khác index cột đơn?

Một cột `text` đơn chứa một giá trị; collection có nhiều phần tử. Với `map<text,text>` chẳng hạn, ta có ít nhất ba kiểu câu hỏi khác nhau:

| Câu hỏi nghiệp vụ | CQL minh họa | Thành phần cần lập chỉ mục |
| --- | --- | --- |
| Sản phẩm có gắn nhãn `sale`? | `tags CONTAINS 'sale'` | Phần tử trong `set` / `list` |
| Thuộc tính có khóa `color`? | `attributes CONTAINS KEY 'color'` | **Khóa** của map |
| Thuộc tính có giá trị `blue` ở bất kỳ khóa nào? | `attributes CONTAINS 'blue'` | **Giá trị** của map |
| Thuộc tính `color` chính xác là `blue`? | `attributes['color'] = 'blue'` | **Cặp khóa–giá trị** của map |
| Cả collection chính xác bằng một giá trị? | `frozen_attrs = {'color':'blue'}` | **Toàn bộ** collection đã `frozen` |

Bốn điều kiện đầu không tương đương. Nếu map là `{'color':'blue', 'status':'active'}`, điều kiện `CONTAINS 'blue'` không chứng minh khóa `color` chứa `blue`; giá trị `blue` có thể nằm dưới khóa khác. Ngược lại, `CONTAINS KEY 'color'` chỉ kiểm tra có khóa, không kiểm tra nội dung tại khóa đó.

### Dữ liệu minh họa

Các ví dụ sau giả sử đã chọn một keyspace trong `cqlsh`, ví dụ `USE demo;`, và dùng UUID cố định để dễ thực hành:

```sql
CREATE TABLE catalog_items_by_id (
    item_id uuid PRIMARY KEY,
    tags set<text>,
    revision_labels list<text>,
    attributes map<text, text>,
    schema_version int,
    title text
);

INSERT INTO catalog_items_by_id
    (item_id, tags, revision_labels, attributes, schema_version, title)
VALUES
    (11111111-1111-1111-1111-111111111111,
     {'sale', 'eco'}, ['draft', 'published'],
     {'color': 'blue', 'tier': 'premium'},
     2, 'Bình nước');

INSERT INTO catalog_items_by_id
    (item_id, tags, revision_labels, attributes, schema_version, title)
VALUES
    (22222222-2222-2222-2222-222222222222,
     {'new'}, ['draft'],
     {'color': 'red', 'tier': 'standard'},
     1, 'Balo');
```

**Lưu ý về thiết kế:** Bảng này cố tình dùng một khóa chính đơn giản để tập trung vào cú pháp index. Trong sản phẩm thực, phải xét thêm `tenant_id`, phân vùng, độ lớn collection và quyền truy cập. Không dùng ví dụ này như kiến trúc tìm kiếm đa tenant mặc định.

## 2. Index trên `set` và `list`: tìm một phần tử

Với collection không `frozen`, truy vấn thành viên thường sử dụng `CONTAINS` và chỉ mục trên các giá trị phần tử:

```sql
-- Secondary index truyền thống (2i), minh họa cho collection không frozen.
CREATE INDEX catalog_tags_values_idx
ON catalog_items_by_id (VALUES(tags));

SELECT item_id, title
FROM catalog_items_by_id
WHERE tags CONTAINS 'sale';
```

Tương tự, nếu cần tìm hàng có phần tử `'published'` trong `revision_labels`:

```sql
CREATE INDEX catalog_revision_values_idx
ON catalog_items_by_id (VALUES(revision_labels));

SELECT item_id, title
FROM catalog_items_by_id
WHERE revision_labels CONTAINS 'published';
```

Điểm cần hiểu:

- `set` không giữ thứ tự và không có phần tử trùng; `list` có thứ tự và có thể chứa phần tử trùng. Index thành viên chỉ trả lời liệu một giá trị có nằm trong collection, không trả lời vị trí của nó trong `list`.
- Collection lớn, thay đổi liên tục có thể gây nhiều lần cập nhật cấu trúc index và tạo tombstone khi xóa hoặc thay phần tử.
- Index thành viên không tự tối ưu những truy vấn như “phần tử mới nhất trong list”, “ba nhãn đầu tiên” hoặc lọc theo thứ tự. Đó là dấu hiệu nên mô hình hóa riêng bằng clustering key hoặc bảng theo truy vấn.
- Không nên nhồi hàng nghìn phần tử vào một collection chỉ để lấy lại hành vi của bảng quan hệ nhiều–nhiều; hãy xem xét bảng riêng có khóa chính thể hiện truy vấn.

Nếu chỉ có một tập giá trị cố định nhỏ như trạng thái `active/inactive`, index có thể phải đọc rất nhiều kết quả trùng nhau trên nhiều partition. Khả năng viết được `CONTAINS` không bảo đảm chi phí thấp.

## 3. Index trên `map`: KEY, VALUE và ENTRY

Trên `map<text,text>`, ba dạng truy vấn thông dụng đòi hỏi ba kiểu lập chỉ mục khác nhau. Những câu lệnh dưới đây minh họa **các lựa chọn index độc lập**; không nên tạo tất cả cho một cột trong môi trường thật chỉ vì có sẵn cú pháp. Hãy chọn theo truy vấn cần phục vụ và kiểm tra khả năng hỗ trợ của phiên bản/phân phối Cassandra đang chạy.

### 3.1. Tìm theo khóa: `KEYS(map)`

```sql
CREATE INDEX catalog_attrs_keys_idx
ON catalog_items_by_id (KEYS(attributes));

SELECT item_id, title
FROM catalog_items_by_id
WHERE attributes CONTAINS KEY 'color';
```

Kết quả gồm các hàng có khóa `color` dù giá trị là `blue` hay `red`. Loại index này phù hợp câu hỏi “có thuộc tính X hay không”, không đủ để hỏi “X bằng Y”.

### 3.2. Tìm theo giá trị: `VALUES(map)`

```sql
CREATE INDEX catalog_attrs_values_idx
ON catalog_items_by_id (VALUES(attributes));

SELECT item_id, title
FROM catalog_items_by_id
WHERE attributes CONTAINS 'premium';
```

Câu lệnh tìm bất kỳ hàng nào có ít nhất một giá trị map là `premium`; nó **không xác định** giá trị đó nằm dưới khóa `tier`. Nếu chỉ quan tâm một khóa cố định thì kiểu index này quá rộng về ý nghĩa.

### 3.3. Tìm theo đúng cặp: `ENTRIES(map)`

```sql
CREATE INDEX catalog_attrs_entries_idx
ON catalog_items_by_id (ENTRIES(attributes));

SELECT item_id, title
FROM catalog_items_by_id
WHERE attributes['tier'] = 'premium';
```

Điều kiện này yêu cầu đúng khóa `tier` gắn với giá trị `premium`. Nó có ngữ nghĩa khác với `CONTAINS KEY 'tier'` kết hợp `CONTAINS 'premium'`: hai điều kiện `CONTAINS` riêng lẻ có thể cùng đúng nhưng giá trị `premium` lại thuộc khóa khác.

| Index | Tập thông tin dùng để tìm | Kiểu điều kiện |
| --- | --- | --- |
| `KEYS(attributes)` | Tên khóa | `attributes CONTAINS KEY 'tier'` |
| `VALUES(attributes)` | Giá trị, không gắn với khóa cụ thể | `attributes CONTAINS 'premium'` |
| `ENTRIES(attributes)` | Khóa *và* giá trị đi cùng nhau | `attributes['tier'] = 'premium'` |

**Điểm cần kiểm tra theo bản triển khai:** CQL cho phép biểu đạt các dạng index kể trên trong các bản Cassandra hỗ trợ collection index, nhưng loại index có sẵn, khả năng phối hợp nhiều index trên cùng cột và giới hạn kiểu dữ liệu có thể khác nhau giữa bản Apache Cassandra, Cassandra dịch vụ và bản phân phối tương thích. Khi triển khai, xác nhận DDL trực tiếp trên môi trường mục tiêu, thay vì coi ví dụ là ma trận tương thích cho mọi phiên bản.

## 4. 2i và SAI: khác nhau thế nào theo phiên bản?

**2i (secondary index truyền thống)** là cơ chế đã có từ các dòng Cassandra trước. Index được duy trì cùng dữ liệu ở replica; truy vấn qua nhiều partition có thể phân tán đến nhiều node. Trên tập dữ liệu lớn, độ chọn lọc thấp hoặc giá trị xuất hiện dày đặc, chi phí quét kết quả, fan-out và hợp nhất có thể tăng đáng kể.

**SAI (Storage-Attached Index)** là cơ chế lập chỉ mục gắn với vòng đời lưu trữ SSTable, được tích hợp vào Apache Cassandra **5.0**. SAI phù hợp hơn cho nhiều truy vấn phụ có chọn lọc, nhưng vẫn có chi phí ghi/đọc và không thay thế việc thiết kế bảng theo truy vấn.

| Môi trường | Điều cần biết |
| --- | --- |
| Apache Cassandra 3.x và 4.x tiêu chuẩn | 2i là lựa chọn index truyền thống; không mặc định có SAI tích hợp như Cassandra 5.0. Có thể gặp các cơ chế custom index tùy bản phân phối. |
| Apache Cassandra 5.0 trở lên | Có SAI tích hợp; cần xem phiên bản cụ thể hỗ trợ kiểu dữ liệu, cách đánh index collection và cú pháp tùy chọn nào. |
| Cassandra do nhà cung cấp vận hành / bản phân phối tùy biến | SAI, custom index và các hạn chế có thể khác upstream; đối chiếu tài liệu và cấu hình thực tế. |

Ví dụ DDL minh họa cách chỉ định SAI một cách tường minh trên bản hỗ trợ:

```sql
-- Apache Cassandra 5.0+ hoặc bản phân phối có SAI tương thích.
-- Thử trên một bảng mới/chưa có index khác cho cùng mục tiêu.
CREATE CUSTOM INDEX catalog_tags_sai_idx
ON catalog_items_by_id (VALUES(tags))
USING 'StorageAttachedIndex';

SELECT item_id, title
FROM catalog_items_by_id
WHERE tags CONTAINS 'eco';
```

Nếu cần SAI cho map, phải xác định bản Cassandra đang chạy có hỗ trợ loại target tương ứng (`KEYS`, `VALUES`, `ENTRIES`) hay không. Ví dụ cấu trúc DDL để **kiểm tra trên bản hỗ trợ**:

```sql
CREATE CUSTOM INDEX catalog_attrs_entries_sai_idx
ON catalog_items_by_id (ENTRIES(attributes))
USING 'StorageAttachedIndex';
```

**Không chạy ví dụ SAI cùng lúc với các ví dụ 2i trên cùng cột** trong một môi trường dùng chung: đó là các phương án so sánh, không phải chỉ dẫn tạo toàn bộ. Nếu DDL bị từ chối, đọc thông báo lỗi và ma trận hỗ trợ bản đang dùng; không lách bằng `ALLOW FILTERING` để giả lập index.

SAI không cung cấp công cụ tìm kiếm văn bản đầy đủ kiểu search engine cho mọi nhu cầu và không thay thế keyspace partitioning, replication hay consistency level. Với truy vấn luôn xuất hiện và có tải lớn, bảng theo truy vấn vẫn thường dễ dự đoán hơn.

## 5. `frozen`, UDT, tuple và cấu trúc lồng nhau

### 5.1. Collection không frozen so với frozen

Collection không `frozen` cho phép Cassandra quản lý/cập nhật phần tử riêng lẻ; vì vậy có thể áp dụng các dạng chỉ mục phần tử phù hợp theo phiên bản.

Collection `frozen` được lưu và cập nhật như **một giá trị nguyên khối**. Thao tác thành viên hoặc cập nhật riêng một entry thường không áp dụng giống collection không frozen; nếu phiên bản cho phép index toàn bộ frozen collection, đó là so khớp **toàn bộ giá trị** chứ không phải từng khóa map.

```sql
CREATE TABLE shipping_rules_by_id (
    rule_id uuid PRIMARY KEY,
    frozen_options frozen<map<text, text>>
);

-- Chỉ áp dụng khi phiên bản/loại index hỗ trợ FULL trên frozen collection.
CREATE INDEX shipping_frozen_options_idx
ON shipping_rules_by_id (FULL(frozen_options));

INSERT INTO shipping_rules_by_id (rule_id, frozen_options)
VALUES (
    33333333-3333-3333-3333-333333333333,
    {'carrier': 'A', 'zone': 'north'}
);

-- So sánh toàn bộ map; thêm/bớt một entry sẽ thành giá trị khác.
SELECT rule_id
FROM shipping_rules_by_id
WHERE frozen_options = {'carrier': 'A', 'zone': 'north'};
```

Với `frozen<map<text,text>>`, hai map có cùng tập cặp khóa–giá trị mới được coi là giá trị tương đương; `FULL` không có nghĩa “chỉ mục mọi thuộc tính nằm sâu bên trong”.

### 5.2. User-defined type (UDT) hoặc tuple

Cassandra có UDT và `tuple` để gom nhiều trường thành một cột:

```sql
CREATE TYPE delivery_address (
    city text,
    district text
);

CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    address frozen<delivery_address>,
    schema_version int
);
```

Đừng mặc định có thể tạo cú pháp kiểu `CREATE INDEX ... ON orders_by_id (address.city)` hoặc query mọi nhánh JSON như trong document database. Hỗ trợ index trên UDT, tuple, collection lồng nhau hay trường nội bộ phụ thuộc kiểu dữ liệu và cơ chế index của phiên bản. Nếu truy vấn `WHERE city = ?` là nhu cầu cốt lõi, thiết kế dữ liệu để `city` trở thành cột rõ ràng hoặc khóa của bảng đọc chuyên dụng là hướng an toàn hơn.

Cassandra hỗ trợ một số cách nhập/xuất JSON qua CQL, nhưng điều đó **không** biến mọi thuộc tính trong payload JSON thành trường có chỉ mục tự động.

## 6. Cấu trúc dữ liệu thay đổi theo `schema_version`

Giả sử ứng dụng lưu `attributes` với phiên bản 1 dùng `'colour'`, phiên bản 2 dùng `'color'`. Truy vấn `attributes['color'] = 'blue'` chỉ hiểu được dữ liệu ghi đúng khóa `color`; index không tự đồng nhất hai ý nghĩa.

```text
Version 1: {'colour': 'blue', 'tier': 'premium'}
Version 2: {'color': 'blue', 'tier': 'premium'}
                                 │
                                 └── Cùng ý nghĩa nghiệp vụ,
                                     nhưng khác khóa map khi truy vấn
```

Các hướng xử lý:

1. **Chuẩn hóa ở thời điểm ghi:** đọc dữ liệu cũ, chuyển tên trường sang một dạng chuẩn và ghi backfill có kiểm soát. Quy định rõ cách xử lý phiên bản ứng dụng cũ còn gửi dữ liệu.
2. **Thêm cột ổn định:** cột `color text`, `category text`, `schema_version int` để truy vấn. `attributes` chỉ giữ phần mở rộng hiếm dùng.
3. **Dùng bảng theo truy vấn và phiên bản:** lưu dữ liệu dẫn xuất từ payload, có khóa chính phù hợp truy vấn; duy trì nhất quán bằng quy trình ghi và đối soát.
4. **Giai đoạn chuyển tiếp:** nếu phải tra cả `colour` và `color`, truy vấn hai tập dữ liệu có kiểm soát và gộp theo ID ở ứng dụng; lên kế hoạch bỏ khóa cũ. Không giả định `OR` và `ALLOW FILTERING` sẽ có hiệu suất tốt trên mọi phiên bản.

Ví dụ truy vấn quan trọng là “danh sách sản phẩm trong tenant X, phiên bản cấu trúc V, danh mục C”, có thể mô hình hóa thành bảng theo truy vấn:

```sql
CREATE TABLE items_by_tenant_category_version (
    tenant_id text,
    schema_version int,
    category text,
    item_id uuid,
    title text,
    PRIMARY KEY ((tenant_id, schema_version, category), item_id)
);

SELECT item_id, title
FROM items_by_tenant_category_version
WHERE tenant_id = 'shop-01'
  AND schema_version = 2
  AND category = 'water-bottles';
```

Câu `SELECT` xác định **đúng khóa phân vùng** nên không phụ thuộc global secondary index. Đổi lại, ứng dụng phải duy trì bảng theo truy vấn khi dữ liệu sản phẩm thay đổi. Nếu một tổ hợp tenant/version/category có kích thước hoặc tần suất truy cập quá lớn, bổ sung bucket phù hợp ngay trong partition key và điều chỉnh cách đọc theo bucket.

**Quy tắc lựa chọn:** thuộc tính thay đổi hoặc thưa thớt có thể lưu trong map; thuộc tính quan trọng để lọc/sắp xếp ở nhiều truy vấn thường nên được nâng lên cột có ý nghĩa rõ ràng hoặc bảng truy vấn riêng. `schema_version` giúp biết cách diễn giải payload, nhưng chỉ mục trên `schema_version` đơn lẻ hiếm khi là giải pháp đủ tốt nếu mỗi phiên bản có hàng triệu dòng.

## 7. Chi phí vận hành, consistency và những lỗi thường gặp

### 7.1. Index phải được cập nhật khi dữ liệu thay đổi

Ví dụ cập nhật map không frozen:

```sql
UPDATE catalog_items_by_id
SET attributes['color'] = 'green'
WHERE item_id = 11111111-1111-1111-1111-111111111111;

UPDATE catalog_items_by_id
SET tags = tags + {'featured'}
WHERE item_id = 11111111-1111-1111-1111-111111111111;
```

Cassandra cần phản ánh trạng thái dữ liệu mới vào các index liên quan. Với map rất lớn, update thường xuyên, TTL và xóa phần tử liên tục, chi phí index, tombstone và compaction có thể tăng. Hãy đo độ trễ ghi, dung lượng index, p95/p99 độ trễ đọc và số partition/row được truy vấn.

### 7.2. Index, replication và mức nhất quán

Replication quyết định bản sao dữ liệu được lưu ở đâu; consistency level của một thao tác quyết định số replica phải tham gia hoặc xác nhận theo yêu cầu. Index phục vụ tìm bản ghi, **không thay thế** giao thức replication và consistency.

- Một truy vấn phụ qua index có thể phải hỏi nhiều replica hoặc nhiều node, tùy cơ chế index, khóa phân vùng và dữ liệu.
- Độ mới của kết quả sau ghi, trạng thái xây dựng index và hành vi khi node lỗi cần được kiểm tra trên cụm thật. Tránh suy ra rằng tạo index đồng nghĩa mọi truy vấn đều thấy ngay tất cả dữ liệu ở mọi tình huống.
- Compaction tác động vòng đời SSTable/tombstone và dữ liệu index tương ứng; repair giúp đồng bộ replica trong phạm vi cơ chế của Cassandra. Chúng không tối ưu lại mô hình truy vấn kém phù hợp hay sửa lỗi logic `schema_version`.
- Khi thêm index vào bảng đã có dữ liệu, cần theo dõi tiến độ xây dựng/backfill index và tình trạng node trước khi dựa vào kết quả truy vấn để ra quyết định nghiệp vụ.

### 7.3. Quy trình kiểm chứng trước production

| Việc cần kiểm tra | Câu hỏi cụ thể |
| --- | --- |
| Phiên bản | Cụm đang là Apache Cassandra 4.x, 5.x hay bản phân phối tương thích? Có SAI không? Có hỗ trợ `FULL`, `KEYS`, `VALUES`, `ENTRIES` với kiểu cụ thể không? |
| DDL và truy vấn | Index được tạo thành công không? Điều kiện `WHERE` dự định có được hỗ trợ mà không phải lạm dụng `ALLOW FILTERING` không? |
| Chọn lọc | Một điều kiện trả vài hàng hay hàng triệu hàng? Có giới hạn tenant/partition rõ ràng không? |
| Kích thước và biến động | Mỗi collection có bao nhiêu phần tử? Có cập nhật/xóa nhiều, TTL ngắn hoặc tombstone tích tụ không? |
| Hiệu năng | Đo trên dữ liệu kích thước thực và tải có ghi; đo p95/p99, số node tham gia, tài nguyên CPU/disk và chi phí xây index. |
| Vận hành | Kiểm tra tình trạng build/rebuild, node lỗi, repair, compaction, sao lưu/khôi phục và khả năng truy vấn trong giai đoạn chuyển đổi phiên bản. |

Có thể quan sát schema bằng `DESCRIBE TABLE catalog_items_by_id;` trong `cqlsh`. Để xem trạng thái/loại index đã khai báo, có thể xem metadata phù hợp với phiên bản qua `system_schema.indexes` hoặc công cụ quản trị cụm. Dùng `TRACING ON;` ở môi trường thử nghiệm để hiểu đường đi truy vấn, nhưng không bật tracing rộng rãi trong production vì có overhead.

### 7.4. Liên hệ với ứng dụng Java

Ứng dụng Java dùng driver Cassandra có thể gửi `SELECT` với điều kiện `CONTAINS` hoặc map entry giống CQL thủ công. Việc bind biến không làm đổi cơ chế truy vấn:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class CatalogSearch {
    private final CqlSession session;
    private final PreparedStatement byTag;

    public CatalogSearch(CqlSession session) {
        this.session = session;
        this.byTag = session.prepare(
            "SELECT item_id, title FROM catalog_items_by_id " +
            "WHERE tags CONTAINS ?");
    }

    public ResultSet findByTag(String tag) {
        return session.execute(byTag.bind(tag));
    }
}
```

Ví dụ giả định keyspace và index cần thiết đã sẵn sàng, driver 4.x đã kết nối đúng cluster/local data center. Vì câu truy vấn tìm theo index không nhất thiết xác định một partition key, cơ chế routing và độ trễ có thể khác truy vấn theo khóa chính. Trong ứng dụng thực tế nên giới hạn page size, phân trang đúng cách, đặt timeout phù hợp và đo tải bằng dữ liệu thật. Đừng dùng `ALLOW FILTERING` để ép các truy vấn chưa được mô hình hóa.

## 8. Tình huống quyết định thiết kế

Giả sử một hệ thống có 30 triệu sản phẩm, mỗi sản phẩm chứa map thuộc tính và nhiều tenant. Có ba yêu cầu:

1. **Tra một sản phẩm bằng ID:** dùng bảng theo khóa chính `product_id` và tenant phù hợp. Index trên map không mang thêm giá trị cho truy vấn này.
2. **Lọc tùy chọn theo một vài thuộc tính hiếm khi dùng:** đánh giá SAI nếu phiên bản hỗ trợ, độ chọn lọc tốt và đã benchmark. Với 2i trên bảng lớn, phải đặc biệt chú ý fan-out và số bản ghi trúng điều kiện.
3. **Liệt kê thường xuyên toàn bộ sản phẩm của tenant và danh mục, có phân trang:** tạo bảng theo truy vấn `items_by_tenant_category` với partition key/bucket phù hợp, clustering key cho thứ tự mong muốn. Không dựa vào `CONTAINS` toàn cluster làm đường đọc chính.

Nếu map đổi tên khóa theo `schema_version`, phải chuẩn hóa giá trị hoặc duy trì chỉ mục/bảng dẫn xuất theo trường nghiệp vụ ổn định. Việc Cassandra trả kết quả cho một phiên bản không chứng minh các phiên bản còn lại đã được bao phủ.

## 9. Bài tự kiểm tra

**Câu 1.** Với `attributes = {'color':'blue', 'tier':'premium'}`, điều kiện `attributes CONTAINS 'premium'` có chứng minh `attributes['tier'] = 'premium'` không? Nếu không, index nào diễn đạt chính xác yêu cầu?

**Câu 2.** Bạn có một cột `frozen<map<text,text>>`; người dùng yêu cầu “tìm các map chứa khóa `color`, bất kể các khóa khác”. Có nên dùng `FULL(frozen_map)` và so sánh toàn map để đáp ứng yêu cầu này không?

**Câu 3.** Hệ thống Cassandra 4.x tiêu chuẩn cần tìm kiếm trên nhiều trường phụ với tải lớn. Có thể mặc nhiên chạy DDL SAI của Apache Cassandra 5.0 không? Bạn cần kiểm tra gì trước?

**Câu 4.** Hai phiên bản sự kiện lưu khóa `'colour'` và `'color'` cho cùng ý nghĩa. Tạo index `ENTRIES(attributes)` có tự giải quyết sai khác đó không? Thiết kế nào bền vững hơn?

**Gợi ý đáp án:**

1. Không. `CONTAINS 'premium'` chỉ nói có một giá trị `premium` ở đâu đó. Dùng index entry nếu được phiên bản hỗ trợ và truy vấn `attributes['tier'] = 'premium'`.
2. Không. `FULL` trên frozen map (nếu được hỗ trợ) phục vụ so sánh nguyên giá trị. Để tìm từng khóa, dùng map không frozen với index khóa phù hợp, hoặc đưa thuộc tính cần tìm lên cột/bảng truy vấn riêng.
3. Không. Cần xác định bản phân phối, SAI có thực sự có mặt, hỗ trợ kiểu collection và DDL, tính chọn lọc, hiệu năng và kế hoạch vận hành.
4. Không. Index không hiểu hai tên trường là đồng nghĩa. Chuẩn hóa khi ghi, migrate dữ liệu cũ hoặc duy trì bảng/cột truy vấn theo thuộc tính chuẩn hóa và `schema_version`.

## Ghi nhớ

- Index collection trả lời những câu hỏi khác nhau: **phần tử** của `set/list`, **khóa**, **giá trị**, hoặc **cặp** trong `map`; chọn index phải khớp ngữ nghĩa `WHERE`.
- `FULL` đối với collection `frozen` (khi được hỗ trợ) là tìm theo **toàn giá trị**, không phải chỉ mục theo từng trường lồng nhau.
- 2i có ở các thế hệ Cassandra cũ; SAI được tích hợp trong Apache Cassandra 5.0. Cú pháp và hỗ trợ collection cần xác nhận theo phiên bản/phân phối.
- Index không thay thế thiết kế bảng theo truy vấn, khóa phân vùng, kiểm tra hiệu năng, replication hay consistency level.
- Khi cấu trúc thay đổi theo phiên bản, hãy chuẩn hóa ngữ nghĩa trường và xây luồng migrate/đối soát; index tự nó không hiểu `'colour'` và `'color'` là một.
