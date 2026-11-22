# Publication, subscription và phạm vi dữ liệu trong PostgreSQL

Logical replication cho phép PostgreSQL truyền các thay đổi dữ liệu ở mức hàng từ một database nguồn (publisher) tới một database đích (subscriber). Hai thành phần trung tâm của cơ chế này là **publication** và **subscription**:

- **Publication** xác định những bảng và loại thay đổi mà publisher cung cấp.
- **Subscription** xác định publisher nào được kết nối, publication nào được nhận và cách subscriber đồng bộ dữ liệu.

Phạm vi dữ liệu có thể được giới hạn theo bảng, schema, hàng (row filter) và cột (column list). Vì vậy, logical replication phù hợp với các bài toán như đồng bộ một nhóm bảng, tách dữ liệu theo tenant, đưa dữ liệu sang hệ thống phân tích hoặc di chuyển từng phần database.

Tuy nhiên, logical replication có ranh giới rõ ràng. Nó sao chép các thay đổi DML được publication cho phép; nó không tự đồng bộ mọi DDL, role, extension, sequence state hay cấu hình của database. Subscriber phải có schema tương thích và cần một kế hoạch riêng cho những thành phần ngoài phạm vi publication.

~~~mermaid
flowchart LR
    A["Publisher database"] --> B["Publication"]
    B --> C["WAL logical decoding"]
    C --> D["Logical replication stream"]
    D --> E["Subscription"]
    E --> F["Initial table sync"]
    E --> G["Apply worker"]
    F --> H["Subscriber tables"]
    G --> H
~~~

Bài học thuộc chương **Sao chép logic**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu publication, subscription, các thao tác được publish, phạm vi bảng/schema, row filters, column lists, replica identity, initial table synchronization, replication slots, partitioning và cách giám sát quá trình đồng bộ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò publisher, publication, subscriber và subscription.
2. Phân biệt logical replication với physical streaming replication.
3. Tạo publication cho một hoặc nhiều bảng.
4. Tạo publication cho toàn bộ bảng hoặc các bảng trong schema.
5. Chọn các thao tác INSERT, UPDATE, DELETE và TRUNCATE.
6. Dùng row filter để giới hạn các hàng được publish.
7. Dùng column list để giới hạn các cột được publish.
8. Hiểu replica identity và yêu cầu cho UPDATE/DELETE.
9. Tạo subscription và hiểu quá trình initial table synchronization.
10. Phân biệt copy_data true và false.
11. Cập nhật subscription khi publication thay đổi.
12. Quản lý replication slots ở publisher.
13. Hiểu giới hạn về DDL, sequences, large objects và global objects.
14. Xử lý partitioned tables và publication scope.
15. Theo dõi trạng thái apply/sync bằng các system views.
16. Chẩn đoán lỗi quyền, schema mismatch, duplicate rows và apply conflicts.
17. Thiết kế phạm vi dữ liệu phù hợp với workload và yêu cầu bảo mật.
18. Xây dựng checklist triển khai, kiểm thử và vận hành logical replication.

## 2. Kiến trúc logical replication

Logical replication truyền các thay đổi dữ liệu theo ý nghĩa SQL, chẳng hạn một hàng được INSERT, UPDATE hoặc DELETE. Publisher sử dụng WAL và logical decoding để tạo stream thay đổi. Subscriber nhận stream rồi apply vào các bảng tương ứng.

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| Publisher | Database nguồn phát thay đổi |
| Publication | Tập bảng và thao tác được phép phát |
| Logical decoding | Chuyển WAL thành thay đổi logic |
| Replication slot | Theo dõi tiến độ consumer và giữ WAL cần thiết |
| Subscription | Cấu hình kết nối và nhận publication |
| Initial table sync | Sao chép dữ liệu hiện có khi bắt đầu |
| Apply worker | Áp dụng thay đổi liên tục trên subscriber |

Một publisher có thể có nhiều publications. Một subscriber có thể tạo nhiều subscriptions. Một subscription có thể nhận một hoặc nhiều publications từ cùng một publisher database.

### Ví dụ

Giả sử hệ thống bán hàng có database nguồn sales_prod và database báo cáo sales_analytics.

- Publisher: sales_prod.
- Publication: sales_reporting_pub.
- Subscriber: sales_analytics.
- Subscription: sales_reporting_sub.

Publication chỉ đưa các bảng customers và orders vào stream. Subscriber tạo các bảng tương ứng và nhận dữ liệu ban đầu, sau đó apply các thay đổi mới.

Logical replication không phải cơ chế multi-master mặc định. Việc nhiều node cùng ghi vào cùng dữ liệu cần thiết kế conflict handling riêng; không nên giả định PostgreSQL tự giải quyết xung đột như một hệ thống distributed database đa chủ.

## 3. Publication là gì?

Publication là một đối tượng trong database publisher, định nghĩa tập thay đổi mà publisher sẽ cung cấp cho subscriber.

Publication có thể bao gồm:

- Một bảng cụ thể.
- Nhiều bảng.
- Tất cả bảng đủ điều kiện trong database.
- Các bảng thuộc một schema, trên những phiên bản hỗ trợ.
- Các thao tác INSERT, UPDATE, DELETE và TRUNCATE.
- Row filters và column lists, tùy loại publication và phiên bản.

Publication không phải bản sao của bảng và không lưu dữ liệu đã publish. Nó là metadata mô tả phạm vi thay đổi được phát.

### Publication thuộc database nào?

Publication là database-level object. Nó được tạo trong database nguồn và không tự xuất hiện trong database khác cùng cluster.

Ví dụ:

~~~sql
CREATE PUBLICATION sales_pub
FOR TABLE public.customers, public.orders;
~~~

Lệnh phải được chạy trong database publisher có các bảng đó.

### Publication không tạo bảng trên subscriber

Publication chỉ khai báo dữ liệu được phát. Subscriber cần có bảng tương ứng với schema tương thích, trừ phần initial table synchronization có thể nạp rows vào các bảng đã tồn tại. Logical replication không tự triển khai toàn bộ schema DDL sang subscriber.

## 4. Subscription là gì?

Subscription là đối tượng ở database subscriber, lưu thông tin publisher connection, tên publication cần nhận và trạng thái replication.

Subscription xác định:

- Publisher connection string.
- Một hoặc nhiều publication names.
- Subscription có enabled hay không.
- Có tạo replication slot trên publisher hay không.
- Có copy dữ liệu ban đầu hay không.
- Slot name và một số tùy chọn apply/streaming theo version.

Ví dụ:

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION sales_pub;
~~~

Trong ví dụ, subscriber kết nối database sales_prod trên publisher và nhận publication sales_pub.

### Subscription không chứa dữ liệu

Subscription là cấu hình điều phối. Dữ liệu được nạp vào các bảng subscriber; replication slot ở publisher theo dõi tiến độ logical consumer.

Nếu subscription bị disable, thay đổi mới có thể tiếp tục tích lũy trong WAL/slot tùy trạng thái. Khi enable lại, subscriber có thể cần apply backlog; nếu slot bị mất hoặc WAL không còn, cần quy trình phục hồi.

## 5. Phân biệt publication và subscription

| Tiêu chí | Publication | Subscription |
| --- | --- | --- |
| Nằm ở đâu | Publisher database | Subscriber database |
| Vai trò | Xác định dữ liệu/thay đổi được phát | Xác định nguồn và publication được nhận |
| Chứa connection string | Không | Có |
| Chứa table list | Có | Theo dõi relation membership đã đồng bộ |
| Có replication slot | Không trực tiếp | Thường tạo/điều khiển slot phía publisher |
| Có apply worker | Không | Có |
| Có initial copy | Không | Có thể thực hiện khi tạo/refresh |

Một publication có thể được nhiều subscribers sử dụng. Mỗi subscription thường có replication slot riêng để publisher theo dõi tiến độ từng consumer độc lập.

## 6. Các thao tác được publish

Publication có thể chọn những thao tác:

- INSERT
- UPDATE
- DELETE
- TRUNCATE

Ví dụ:

~~~sql
CREATE PUBLICATION orders_insert_only
FOR TABLE public.orders
WITH (publish = 'insert');
~~~

Publication chỉ phát INSERT cho bảng orders.

Mặc định, publication tạo theo cách thông thường publish các thao tác INSERT, UPDATE, DELETE và TRUNCATE. Nên ghi rõ option khi muốn kiểm soát phạm vi.

Ví dụ chỉ publish insert/update/delete:

~~~sql
CREATE PUBLICATION orders_dml_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete');
~~~

### TRUNCATE cần được chú ý

Nếu publication bao gồm TRUNCATE, lệnh TRUNCATE trên publisher có thể được gửi tới subscriber. Row filter không biến TRUNCATE thành thao tác xóa từng hàng theo điều kiện. Vì vậy, subscriber chứa dữ liệu cục bộ ngoài tập dữ liệu đồng bộ có thể bị ảnh hưởng khi nhận TRUNCATE.

Nếu không muốn TRUNCATE được phát, loại nó khỏi publish option.

### Không có SELECT publication

SELECT không phải thay đổi dữ liệu và không phải publish operation. Publication không phải cơ chế remote query hay read-through cache; subscriber có dữ liệu được đồng bộ để query cục bộ.

## 7. Tạo publication cho một bảng

Ví dụ:

~~~sql
CREATE PUBLICATION customers_pub
FOR TABLE public.customers;
~~~

Tạo publication cho nhiều bảng:

~~~sql
CREATE PUBLICATION sales_core_pub
FOR TABLE
    public.customers,
    public.orders,
    public.order_items;
~~~

Nếu muốn bổ sung bảng sau:

~~~sql
ALTER PUBLICATION sales_core_pub
ADD TABLE public.products;
~~~

Loại bỏ bảng:

~~~sql
ALTER PUBLICATION sales_core_pub
DROP TABLE public.products;
~~~

Thay danh sách bảng:

~~~sql
ALTER PUBLICATION sales_core_pub
SET TABLE
    public.customers,
    public.orders,
    public.order_items;
~~~

Cú pháp và các option thay đổi theo major version; kiểm tra tài liệu đúng phiên bản server.

### Bảng được thêm vào publication có tự được copy sang subscriber ngay không?

Không. Publication thay đổi ở publisher chưa tự động hoàn tất việc cập nhật relation membership và copy dữ liệu ở subscriber. Subscription cần refresh publication để phát hiện bảng mới và có thể chạy initial table synchronization.

## 8. Publication cho toàn bộ bảng

Có thể tạo publication cho tất cả bảng đủ điều kiện trong database:

~~~sql
CREATE PUBLICATION all_tables_pub
FOR ALL TABLES;
~~~

Publication này có phạm vi rộng. Việc tạo FOR ALL TABLES có yêu cầu quyền đặc biệt, thường cần superuser; hãy kiểm tra tài liệu phiên bản và policy của hệ thống.

### Khi nào dùng FOR ALL TABLES?

- Một subscriber cần bản sao gần như toàn bộ database.
- Môi trường quản trị tập trung, phạm vi được kiểm soát.
- Muốn tự động bao gồm nhiều bảng mà không quản lý từng bảng riêng.

### Rủi ro

- Có thể phát dữ liệu nhạy cảm ngoài dự kiến.
- Bảng mới đủ điều kiện có thể được đưa vào phạm vi publication.
- Subscriber cần schema và quyền phù hợp cho các bảng mới.
- Không thể dùng row filter/column list theo từng bảng như một publication table list thông thường.
- Scope rộng khiến khó kiểm soát data minimization.

Nếu chỉ cần một tập bảng, publication tường minh thường dễ review hơn.

## 9. Publication theo schema

Trên các PostgreSQL versions hỗ trợ schema-level publication (bắt đầu từ PostgreSQL 15), có thể dùng:

~~~sql
CREATE PUBLICATION finance_schema_pub
FOR TABLES IN SCHEMA finance;
~~~

Cách này bao gồm các bảng đủ điều kiện trong schema được chỉ định. Có thể thêm hoặc loại schema bằng các lệnh ALTER PUBLICATION tương ứng theo phiên bản.

Ví dụ:

~~~sql
ALTER PUBLICATION finance_schema_pub
ADD TABLES IN SCHEMA reporting;
~~~

### Schema publication có tự publish DDL không?

Không. Nó xác định bảng thuộc schema được đưa vào publication. Việc tạo table mới trên publisher không tự chạy CREATE TABLE ở subscriber. Schema tương ứng phải được triển khai ở subscriber; subscription cần refresh membership khi cần.

### Khi nào nên dùng schema-level publication?

- Các bảng trong schema có cùng chính sách dữ liệu.
- Schema được dùng làm ranh giới nghiệp vụ.
- Bảng mới trong schema cần được đưa vào publication theo quy trình refresh.
- Không cần row filter/column list khác nhau cho từng bảng.

Không dùng schema publication nếu một schema chứa cả dữ liệu nhạy cảm và dữ liệu được phép chia sẻ mà không có kế hoạch scope rõ ràng.

## 10. Row filter là gì?

Row filter là điều kiện WHERE được gắn với một bảng trong publication để giới hạn các hàng được publish.

Ví dụ chỉ phát orders đã hoàn tất:

~~~sql
CREATE PUBLICATION completed_orders_pub
FOR TABLE public.orders
WHERE (status = 'completed');
~~~

Một row filter giúp subscriber chỉ nhận một phần dữ liệu của bảng nguồn.

### Ví dụ theo tenant

~~~sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE public.orders
WHERE (tenant_id = 42);
~~~

Publication này giới hạn hàng orders có tenant_id bằng 42.

Nếu có nhiều tenant, có thể tạo các publications khác nhau theo chính sách dữ liệu, hoặc thiết kế pipeline riêng. Cần tính chi phí vận hành, số subscriptions và replication slots.

### Row filter chạy ở đâu?

Điều kiện được đánh giá ở publisher trong quá trình xác định thay đổi cần phát. Subscriber nhận các thay đổi đã qua điều kiện publication; subscriber không tự đánh giá lại toàn bộ bảng nguồn.

Row filter không phải cơ chế phân quyền SQL tổng quát. Người dùng có quyền truy cập publisher vẫn chịu các quyền PostgreSQL trên publisher; người dùng subscriber có thể đọc dữ liệu đã được sao chép theo quyền trên subscriber.

## 11. Giới hạn và semantics của row filter

Row filter có những giới hạn quan trọng:

- Điều kiện phải tham chiếu các cột của bảng tương ứng.
- Không phải mọi biểu thức SQL đều được chấp nhận; các hàm/operator cần đáp ứng yêu cầu volatility của PostgreSQL.
- Row filter của UPDATE/DELETE có giới hạn liên quan replica identity.
- Row filter không lọc thao tác TRUNCATE.
- Row filter không tự đồng bộ lại dữ liệu đã có chỉ vì biểu thức được thay đổi.

### UPDATE và DELETE

Với UPDATE, điều kiện row filter được đánh giá trên phiên bản hàng mới; với DELETE, điều kiện được đánh giá trên hàng cũ. Do đó, khi một hàng chuyển qua ranh giới filter, subscriber có thể không tự có trạng thái giống như kết quả của một truy vấn SELECT chạy lại toàn bộ điều kiện.

Ví dụ: một order trước đó có status completed, sau đó publisher đổi status thành cancelled. Nếu UPDATE mới không còn thỏa filter, thay đổi có thể không được gửi theo điều kiện hiện tại, trong khi subscriber vẫn giữ phiên bản completed trước đó.

Ngược lại, một hàng trước đó không nằm trong tập được publish rồi chuyển sang thỏa điều kiện cũng cần được thiết kế và kiểm thử cẩn thận; không giả định row filter tự động hoạt động như một full refresh.

Nếu yêu cầu subscriber luôn phản ánh chính xác tập hàng hiện tại theo một predicate có thể thay đổi, hãy thiết kế quy trình backfill/reconciliation hoặc dùng một pipeline khác phù hợp.

### Cột dùng trong row filter

Đối với UPDATE/DELETE, publisher cần xác định điều kiện trên row identity. PostgreSQL có các giới hạn về việc sử dụng cột trong row filter khi replica identity không bao gồm các cột đó. Nếu filter dùng một cột có thể thay đổi, cần kiểm tra quy tắc version và thiết kế replica identity phù hợp.

## 12. Column list là gì?

Column list giới hạn các cột được publish cho một bảng. Tính năng này được hỗ trợ trong các PostgreSQL versions hiện đại (từ PostgreSQL 15).

Ví dụ:

~~~sql
CREATE PUBLICATION customer_public_fields
FOR TABLE public.customers (customer_id, display_name, city);
~~~

Subscriber chỉ nhận các cột trong danh sách đó theo publication definition.

### Vì sao dùng column list?

- Loại bỏ cột chứa thông tin không cần chia sẻ.
- Giảm lượng dữ liệu truyền.
- Giới hạn phạm vi dữ liệu cho downstream system.
- Tách dữ liệu nghiệp vụ khỏi PII hoặc secret columns.
- Cho phép subscriber có schema tập trung vào một use case.

### Cột identity phải được xem xét

Nếu publication phát UPDATE hoặc DELETE, subscriber phải nhận đủ thông tin để định danh hàng được cập nhật/xóa. Column list phải tương thích với replica identity requirements. Thực tế thường cần bao gồm primary key hoặc các cột replica identity.

Ví dụ:

~~~sql
CREATE PUBLICATION customer_changes_pub
FOR TABLE public.customers
    (customer_id, display_name, city, updated_at)
WITH (publish = 'insert, update, delete');
~~~

Ở đây customer_id được đưa vào danh sách để subscriber có thể định danh row nếu nó là replica identity phù hợp.

### Column list không phải column masking hoàn chỉnh

Nó giới hạn các cột trong logical replication stream. Nó không tự xóa cột khỏi bảng publisher hoặc subscriber, và không thay thế quyền truy cập trên subscriber. Nếu subscriber table có thêm cột, cột đó có thể được giữ cục bộ theo schema và default/nullability phù hợp.

## 13. Kết hợp row filter và column list

Có thể kết hợp hai phạm vi:

~~~sql
CREATE PUBLICATION tenant_42_orders_pub
FOR TABLE public.orders
    (order_id, tenant_id, customer_id, status, total_amount)
    WHERE (tenant_id = 42);
~~~

Kết quả:

- Chỉ bảng orders.
- Chỉ hàng có tenant_id bằng 42.
- Chỉ các cột được liệt kê.
- Các thao tác publish được quyết định bởi publish option của publication.

Cú pháp và khả năng kết hợp cần được xác nhận theo major version. Column lists và row filters được giới thiệu ở PostgreSQL 15; publication theo schema cũng có hỗ trợ từ phiên bản này.

### Khi nào kết hợp hữu ích?

- Một subscriber chỉ cần một tenant.
- Một data warehouse chỉ cần một số trường.
- Một dịch vụ downstream không cần dữ liệu định danh nhạy cảm.
- Đồng bộ dữ liệu theo bounded context.

### Rủi ro

Nếu filter/column list thay đổi, cần đánh giá dữ liệu đã có ở subscriber. Thay publication definition không tự xóa các rows cũ đã được đồng bộ hoặc tự bổ sung mọi rows trước đó chưa được publish. Có thể cần refresh, resnapshot hoặc reconciliation.

## 14. Replica identity và UPDATE/DELETE

Logical replication cần biết cách định danh một hàng ở publisher để subscriber có thể áp dụng UPDATE hoặc DELETE tương ứng.

Mặc định, PostgreSQL dùng primary key làm replica identity nếu có.

Kiểm tra:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    c.relreplident AS replica_identity
FROM pg_class AS c
WHERE c.oid = 'public.orders'::regclass;
~~~

Giá trị d biểu thị default; i là index; f là full; n là nothing.

### REPLICA IDENTITY DEFAULT

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY DEFAULT;
~~~

PostgreSQL dùng primary key nếu có.

### REPLICA IDENTITY USING INDEX

Có thể chọn một unique index phù hợp:

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY USING INDEX orders_replica_key;
~~~

Index phải đáp ứng các yêu cầu của PostgreSQL về unique, non-partial và các cột cần thiết.

### REPLICA IDENTITY FULL

Nếu không có primary key/unique index phù hợp:

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY FULL;
~~~

FULL lưu/đưa thông tin toàn bộ row cũ cần thiết để định danh thay đổi. Cách này có thể làm WAL lớn hơn và subscriber phải tìm row theo nhiều cột; một index phù hợp trên subscriber giúp apply hiệu quả hơn.

### REPLICA IDENTITY NOTHING

NOTHING không cung cấp row identity cho UPDATE/DELETE. Không phù hợp với publication cần phát các thao tác này; có thể giới hạn publication chỉ phát INSERT hoặc chọn replica identity khác.

## 15. Publication chỉ INSERT và bảng không có primary key

Nếu bảng không có primary key, nhưng publication chỉ phát INSERT:

~~~sql
CREATE PUBLICATION audit_append_pub
FOR TABLE public.audit_events
WITH (publish = 'insert');
~~~

Có thể không cần replica identity cho UPDATE/DELETE vì các thao tác đó không được publish.

Nếu sau này thêm UPDATE/DELETE vào publication, phải xem xét replica identity và kiểm tra dữ liệu hiện có. Không giả định subscriber có thể áp dụng UPDATE/DELETE chỉ dựa trên vị trí vật lý của row.

## 16. Tạo subscription

Trên subscriber, trước tiên tạo bảng/schema tương thích. Sau đó:

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION sales_pub;
~~~

Các hành vi mặc định thường gồm:

- Subscription được enable.
- Publisher replication slot được tạo với tên theo subscription nếu không chỉ định khác.
- Dữ liệu hiện có của các bảng publication được copy.
- Apply worker bắt đầu nhận thay đổi sau quá trình khởi tạo.

Tùy chọn rõ ràng:

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION sales_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
~~~

Các option có thể khác theo version; kiểm tra CREATE SUBSCRIPTION của server đang dùng.

### Connection user trên publisher

Role dùng trong connection string cần có quyền replication phù hợp và quyền truy cập cần thiết tới các bảng được publish, đặc biệt trong initial table synchronization. Cần kiểm tra yêu cầu SELECT và quyền liên quan theo version, row filters và table scope.

Không dùng superuser cho connection user chỉ vì muốn tránh lỗi permission. Xác định quyền thiếu cụ thể và cấp tối thiểu cần thiết.

## 17. Chuẩn bị subscriber schema

Logical replication không tự tạo schema/table trên subscriber từ publication. Cần tạo schema tương ứng trước.

Ví dụ trên subscriber:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.customers (
    customer_id bigint PRIMARY KEY,
    display_name text,
    city text
);

CREATE TABLE sales.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint,
    status text,
    total_amount numeric(12,2)
);
~~~

Cấu trúc phải tương thích với publisher. Logical replication map cột theo tên; thứ tự cột có thể khác, nhưng tên và kiểu dữ liệu phải tương thích với dữ liệu được replicate.

Subscriber có thể có cột bổ sung nếu các cột đó được cung cấp giá trị mặc định hoặc cho phép NULL, tùy trường hợp. Không nên dựa vào schema mismatch như một cơ chế transformation.

### Schema drift

Nếu publisher thêm column, subscriber không tự được ALTER TABLE. Cần triển khai DDL theo thứ tự phù hợp:

1. Thêm cột tương thích trên subscriber.
2. Thêm cột trên publisher và cập nhật publication column list nếu dùng.
3. Refresh subscription khi cần cập nhật metadata.
4. Kiểm tra apply worker và dữ liệu.
5. Chỉ sau đó mới thay đổi logic ứng dụng phụ thuộc cột mới.

Khi drop/rename column, phải phối hợp cả hai phía và publication scope.

## 18. Initial table synchronization

Khi tạo subscription với copy_data = true, PostgreSQL thực hiện initial table synchronization cho các bảng được publication chọn.

Quy trình khái quát:

1. Subscription được tạo và kết nối publisher.
2. Các bảng cần đồng bộ được xác định.
3. Initial table sync workers copy dữ liệu hiện có.
4. Thay đổi phát sinh trong lúc copy được theo dõi để không bị mất.
5. Sau khi copy hoàn tất, apply worker tiếp tục streaming các thay đổi.
6. Subscription tiến tới trạng thái đồng bộ.

Với nhiều bảng, có thể có nhiều table sync workers, nhưng số lượng và lịch chạy phụ thuộc cấu hình/version.

### Initial copy không phải full database clone

Nó chỉ copy các bảng nằm trong publication và theo phạm vi row/column được áp dụng. Không tự copy:

- Roles/global objects.
- DDL không thuộc dữ liệu bảng.
- Sequence state như một cơ chế đồng bộ liên tục.
- Extension binaries.
- Large objects theo cách đồng bộ toàn diện.
- Server configuration.

## 19. copy_data true và false

### copy_data = true

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION sales_pub
WITH (copy_data = true);
~~~

Dữ liệu hiện có của các bảng được đồng bộ vào subscriber.

Dùng khi:

- Subscriber mới và bảng đích đang trống.
- Muốn initial synchronization do PostgreSQL điều phối.
- Chưa có một bản copy dữ liệu được xác minh trước đó.

### copy_data = false

~~~sql
CREATE SUBSCRIPTION sales_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION sales_pub
WITH (copy_data = false);
~~~

Subscription không copy dữ liệu hiện có khi khởi tạo. Nó nhận các thay đổi sau khi bắt đầu theo trạng thái replication.

Dùng khi:

- Subscriber đã được nạp dữ liệu trước bằng một phương pháp khác.
- Có quy trình đồng bộ baseline riêng.
- Muốn tránh copy lại dữ liệu đã chuẩn bị.

### Rủi ro của copy_data=false

Nếu subscriber không thực sự đồng nhất với publisher tại thời điểm bắt đầu, các thay đổi tiếp theo không tự sửa toàn bộ chênh lệch lịch sử. Có thể thiếu rows, thừa rows hoặc sai sequence state. Phải xác định một consistent starting point và kiểm chứng dữ liệu trước khi bật subscription.

## 20. Refresh publication

Khi publication thay đổi, subscriber cần cập nhật danh sách bảng được subscribe.

Ví dụ:

~~~sql
ALTER SUBSCRIPTION sales_sub
REFRESH PUBLICATION;
~~~

Có thể điều khiển việc copy data cho bảng mới:

~~~sql
ALTER SUBSCRIPTION sales_sub
REFRESH PUBLICATION
WITH (copy_data = false);
~~~

REFRESH PUBLICATION cập nhật relation membership của subscription theo publication hiện tại. Nếu có bảng mới, PostgreSQL có thể tạo table sync để copy dữ liệu ban đầu theo option.

### Khi nào cần refresh?

- Publisher thêm bảng vào publication.
- Publisher bỏ bảng khỏi publication.
- Schema publication có thêm bảng đủ điều kiện.
- Publication definition thay đổi và subscriber cần cập nhật relation metadata.
- Cột/row filter thay đổi cần được subscriber nhận biết theo semantics phiên bản.

### Bỏ bảng khỏi publication có xóa bảng subscriber không?

Không. Refresh publication cập nhật việc subscription nhận thay đổi từ bảng đó; nó không tự DROP TABLE trên subscriber. Bảng và dữ liệu đã có vẫn còn cho tới khi administrator xử lý riêng.

Đây là điểm quan trọng khi thay đổi data scope: ngừng replicate không đồng nghĩa xóa dữ liệu đã được đồng bộ.

## 21. ALTER SUBSCRIPTION

Một số thao tác quản lý:

Tạm dừng:

~~~sql
ALTER SUBSCRIPTION sales_sub DISABLE;
~~~

Bật lại:

~~~sql
ALTER SUBSCRIPTION sales_sub ENABLE;
~~~

Đổi publication list:

~~~sql
ALTER SUBSCRIPTION sales_sub
SET PUBLICATION sales_pub, customer_pub;
~~~

Refresh:

~~~sql
ALTER SUBSCRIPTION sales_sub
REFRESH PUBLICATION;
~~~

Đổi connection:

~~~sql
ALTER SUBSCRIPTION sales_sub
CONNECTION 'host=publisher-new.example.net dbname=sales_prod user=logical_repl sslmode=verify-full';
~~~

Cú pháp chi tiết và option phụ thuộc PostgreSQL major version. Khi đổi publisher host/credential, cần kiểm tra replication slot ở publisher cũ và mới, tránh bỏ sót slot hoặc tạo hai luồng apply.

## 22. Replication slot phía publisher

Subscription thường tạo một logical replication slot trên publisher để giữ WAL cho subscriber.

Xem slot:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY slot_name;
~~~

Các cột wal_status và một số field khác có thể phụ thuộc version.

### Vì sao cần slot?

Slot cho publisher biết consumer đã xác nhận tới đâu. PostgreSQL giữ WAL cần thiết để subscriber có thể tiếp tục nếu tạm thời disconnect.

### Rủi ro slot inactive

Nếu subscriber dừng lâu hoặc slot bị bỏ quên:

- WAL cần thiết có thể được giữ lại.
- pg_wal có thể tăng nhanh.
- Disk primary có thể đầy.
- Các workload khác có thể bị ảnh hưởng.

Theo dõi slot activity, confirmed_flush_lsn, restart_lsn và WAL retention. Không drop slot chỉ vì active = false; xác định subscription còn cần slot hay không.

## 23. Xóa subscription và replication slot

Khi drop subscription, PostgreSQL thường cố gắng xóa replication slot liên quan trên publisher. Việc này cần kết nối được tới publisher và quyền phù hợp.

Ví dụ:

~~~sql
DROP SUBSCRIPTION sales_sub;
~~~

Nếu publisher không thể truy cập và cần loại bỏ subscription ở subscriber, có thể phải disable subscription, bỏ liên kết slot theo quy trình phiên bản rồi drop subscription; sau đó kết nối publisher và drop orphaned slot riêng.

Không xóa slot khi subscriber vẫn cần nó để tiếp tục. Khi slot bị drop, WAL retention guarantee của slot không còn và subscriber có thể không bắt kịp nếu cần WAL đã bị recycle.

## 24. Publication và DDL

Logical replication không tự replicate DDL như:

- CREATE TABLE.
- ALTER TABLE.
- DROP TABLE.
- CREATE INDEX.
- ALTER TYPE.
- CREATE FUNCTION.
- CREATE EXTENSION.

DDL cần được triển khai riêng trên subscriber theo thứ tự tương thích.

### Ví dụ thêm cột

Publisher:

~~~sql
ALTER TABLE public.customers
ADD COLUMN loyalty_tier text;
~~~

Subscriber cần có cột tương ứng trước khi publisher bắt đầu gửi các row changes chứa column đó, tùy publication column list và version behavior.

Quy trình an toàn thường là triển khai DDL tương thích trên subscriber trước, sau đó thay đổi publisher và publication. Với schema migrations phức tạp, dùng expand-and-contract:

1. Thêm cột mới nullable/default phù hợp ở subscriber.
2. Thêm cột ở publisher.
3. Cập nhật publication scope.
4. Đồng bộ/backfill dữ liệu.
5. Chuyển ứng dụng.
6. Loại cột cũ sau khi mọi subscriber không còn cần.

## 25. Sequence và identity columns

Logical replication replicate row changes, nhưng sequence state không được đồng bộ liên tục như một table stream.

Nếu bảng dùng serial/identity:

- Các giá trị ID được truyền trong row changes.
- Sequence object và current value cần được quản lý riêng.
- Subscriber có thể có sequence value thấp hơn giá trị lớn nhất trong dữ liệu.
- Nếu subscriber được promote hoặc cho phép ghi, insert mới có thể tạo duplicate key nếu sequence chưa được điều chỉnh.

Trước khi chuyển subscriber thành nơi ghi, cần đồng bộ sequence state theo quy trình có kiểm soát và dừng/điều phối writes để tránh race condition.

Không dùng logical replication như một bản sao hoàn chỉnh mọi trạng thái database.

## 26. Large objects, extensions và global objects

Logical publication tập trung vào table changes. Không giả định nó đồng bộ:

- PostgreSQL large objects.
- Role definitions và memberships.
- Database-level grants/ownership toàn diện.
- Tablespace definitions.
- Extension binaries.
- Server configuration.
- DDL và object metadata ngoài publication table stream.

Nếu ứng dụng sử dụng large objects, cần quy trình copy/verify riêng. Nếu cần roles/extensions, dùng configuration management hoặc backup/restore global objects theo chính sách.

## 27. Partitioned tables

Logical replication hỗ trợ partitioned tables, nhưng publication scope và cách biểu diễn thay đổi phụ thuộc option.

Ví dụ:

~~~sql
CREATE PUBLICATION events_pub
FOR TABLE public.events;
~~~

Nếu events là partitioned table, publisher có thể publish changes từ partitions. Option publish_via_partition_root điều khiển changes được phát dưới dạng root partitioned table hay leaf partition, theo version.

Ví dụ:

~~~sql
CREATE PUBLICATION events_pub
FOR TABLE public.events
WITH (publish_via_partition_root = true);
~~~

Khi publish qua root, subscriber cần table structure phù hợp với root relation. Nếu publish qua leaf partitions, subscriber phải có relation mapping phù hợp cho các partition tables.

### Chọn chiến lược partition

- Muốn subscriber nhìn thấy một bảng logic: xem xét publish qua partition root.
- Muốn giữ mapping leaf partitions: kiểm tra partition structure ở cả hai phía.
- Khi attach/detach partition, hiểu thay đổi membership và publication behavior theo version.
- Test partition pruning, routing và DDL migrations trước production.

Không giả định partitioned table được xử lý giống một bảng thường trong mọi publication configuration.

## 28. Publication filters và nhiều publications

Một subscription có thể nhận nhiều publications từ cùng publisher database.

Ví dụ:

~~~sql
CREATE SUBSCRIPTION analytics_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION orders_pub, customers_pub;
~~~

Nếu cùng một bảng xuất hiện trong nhiều publications của subscription, row filters và column lists cần được hiểu theo quy tắc hợp nhất của PostgreSQL. Trong nhiều trường hợp, rows được chọn nếu thỏa filter của ít nhất một publication có bảng đó (OR semantics), và column lists được hợp nhất theo phạm vi cột được publish.

Điều này có thể làm scope dữ liệu rộng hơn dự kiến. Khi nhiều publications chồng lấn:

- Kiểm tra bảng nào xuất hiện ở nhiều publication.
- Kiểm tra filter từng publication.
- Kiểm tra column lists.
- Đánh giá publish operations.
- Test dữ liệu thực tế trên subscriber.

Không giả định nhiều publications tự động áp dụng filter theo phép AND.

## 29. Table mapping và tên cột

Logical replication ghép publisher/subscriber tables theo schema/table identity được quản lý bởi subscription và các cột tương ứng theo tên.

Các nguyên tắc thực tế:

- Subscriber table cần tồn tại.
- Column names và types phải tương thích.
- Column order có thể khác, vì mapping dựa trên tên.
- Cột bổ sung ở subscriber cần default hoặc cho phép NULL nếu không được publisher cung cấp.
- Cột bị loại khỏi publication không nhận giá trị từ stream.
- Constraints ở subscriber có thể khiến apply thất bại nếu dữ liệu không tương thích.

Nếu publisher rename column mà subscriber chưa được cập nhật, apply có thể lỗi hoặc metadata không khớp. DDL rollout phải được phối hợp.

## 30. Apply worker và xung đột dữ liệu

Subscriber apply các thay đổi nhận từ publisher. Nếu subscriber có dữ liệu được ghi độc lập vào cùng bảng, có thể xảy ra conflict:

- INSERT trùng primary key.
- UPDATE không tìm thấy row.
- DELETE không tìm thấy row hoặc dữ liệu đã khác.
- Unique constraint violation.
- Foreign key violation.
- Type/schema mismatch.
- Trigger/constraint ở subscriber làm thay đổi hoặc từ chối dữ liệu.

Logical replication mặc định không cung cấp cơ chế conflict resolution tổng quát để hợp nhất mọi thay đổi hai chiều. Apply worker có thể dừng ở lỗi và cần administrator xử lý.

### Best practice

- Tránh ghi trực tiếp vào bảng do subscription quản lý.
- Nếu cần subscriber-local data, tách schema/table riêng.
- Đảm bảo publisher là nguồn sự thật cho các bảng được replicate.
- Theo dõi logs và subscription stats.
- Thiết kế reconciliation khi có khả năng local writes.
- Không dùng một subscription như multi-master solution.

## 31. Triggers và constraints trên subscriber

Logical replication apply worker có behavior riêng đối với triggers. Các triggers thông thường trên subscriber không mặc nhiên chạy như khi ứng dụng thực hiện DML; các trigger có cấu hình phù hợp như ENABLE REPLICA hoặc ENABLE ALWAYS có thể được áp dụng theo semantics PostgreSQL.

Điều này cần được kiểm tra nếu subscriber dựa vào triggers để:

- Tính toán derived values.
- Ghi audit.
- Cập nhật bảng phụ.
- Enforce business rules.

Constraints trên subscriber vẫn có thể ảnh hưởng apply. Một constraint không tương thích với publisher data có thể làm worker lỗi. Không tắt constraints tùy tiện để cho replication chạy; hãy sửa schema hoặc dữ liệu gốc.

## 32. Theo dõi subscription

View pg_stat_subscription cho biết trạng thái worker và tiến độ nhận dữ liệu:

~~~sql
SELECT
    subid,
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

Các cột thời gian/LSN và cách thể hiện có thể thay đổi theo version. Có thể có một dòng cho apply worker chính và các table sync workers.

Xem cấu hình subscription:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

Catalog pg_subscription có connection information nhạy cảm ở các cột khác; không SELECT hoặc log connection string chứa secret khi không cần.

## 33. Theo dõi table synchronization

Catalog pg_subscription_rel lưu trạng thái đồng bộ từng relation.

~~~sql
SELECT
    s.subname,
    r.srrelid::regclass AS relation_name,
    r.srsubstate,
    r.srsublsn
FROM pg_subscription_rel AS r
JOIN pg_subscription AS s
    ON s.oid = r.srsubid
ORDER BY s.subname, r.srrelid::regclass::text;
~~~

srsubstate thể hiện giai đoạn đồng bộ của relation. Các ký tự state và semantics là metadata nội bộ; tham khảo catalog documentation của đúng version khi phân tích sâu.

Nếu một bảng ở trạng thái sync lâu, kiểm tra table sync worker, publisher load, network và logs.

## 34. Theo dõi publisher side

Trên publisher:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

Logical replication connections có thể xuất hiện trong các thống kê replication sender. Cần phân biệt chúng với physical standby dựa trên application name, slot và connection metadata.

Xem logical slots:

~~~sql
SELECT
    slot_name,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY slot_name;
~~~

Slot inactive hoặc confirmed_flush_lsn không tiến có thể báo subscriber không apply hoặc không kết nối.

## 35. Thống kê lỗi subscription

Trên các PostgreSQL versions cung cấp pg_stat_subscription_stats, có thể kiểm tra:

~~~sql
SELECT *
FROM pg_stat_subscription_stats;
~~~

View có thể chứa số lần apply error, sync error và thời điểm reset thống kê. Tên/cột và quyền truy cập phụ thuộc version.

Kết hợp với:

- Server logs của publisher.
- Server logs của subscriber.
- pg_stat_subscription.
- pg_subscription_rel.
- pg_replication_slots.
- pg_stat_replication.

Không chỉ nhìn subenabled = true rồi kết luận replication đang khỏe. Worker có thể liên tục lỗi hoặc lag lớn dù subscription được bật.

## 36. Xử lý lỗi permission denied

Lỗi có thể phát sinh khi:

- Replication role thiếu LOGIN/REPLICATION.
- HBA không cho phép nguồn kết nối.
- Publisher user thiếu quyền đọc bảng cho initial copy.
- Subscriber user thiếu quyền tạo/ghi table.
- Owner/privilege của subscription không phù hợp.
- Row filter hoặc object cần quyền đặc biệt theo version.

Kiểm tra từng phía:

1. Xác nhận user trong connection string.
2. Kiểm tra role attributes ở publisher.
3. Kiểm tra HBA rule và source IP.
4. Kiểm tra quyền SELECT trên bảng publisher khi initial sync cần.
5. Kiểm tra quyền tạo/ghi object trên subscriber.
6. Xem logs để xác định object và operation thất bại.

Không cấp SUPERUSER toàn cục chỉ để xử lý một lỗi quyền chưa được xác định.

## 37. Xử lý lỗi relation does not exist

Nguyên nhân thường gặp:

- Subscriber chưa tạo schema/table.
- Publication thêm table mới nhưng subscription chưa refresh.
- Schema/table name khác.
- DDL rename/drop không được triển khai đồng bộ.
- Partition mapping không tương thích.
- Table sync chưa hoàn tất hoặc state lỗi.

Khắc phục:

1. Xác định relation ở publisher và subscriber.
2. Kiểm tra publication table list.
3. Kiểm tra subscription relation state.
4. Triển khai DDL tương thích ở subscriber.
5. Refresh publication nếu membership thay đổi.
6. Retry sync theo hướng dẫn version.

Không tạo một bảng rỗng với tên đúng mà bỏ qua column/type/constraint compatibility.

## 38. Xử lý duplicate key và apply conflict

Ví dụ:

~~~text
ERROR: duplicate key value violates unique constraint
DETAIL: Key (order_id)=(1001) already exists.
~~~

Điều tra:

- Subscriber có được ứng dụng ghi local không?
- Initial copy có chạy lại trên bảng đã có dữ liệu không?
- Có nhiều subscriptions cùng ghi vào một table không?
- Publisher có phát cùng data scope từ nhiều publications không?
- Schema/table mapping có sai không?
- Một lần restore thủ công có tạo rows trùng không?

Chọn cách xử lý theo nguồn sự thật. Có thể cần xóa hoặc điều chỉnh row xung đột trên subscriber, resynchronize table hoặc tạo subscriber mới. Không bỏ constraint để worker chạy tiếp nếu chưa hiểu invariant dữ liệu.

## 39. Thay đổi publication scope có tác động gì?

Giả sử publication ban đầu phát mọi orders:

~~~sql
CREATE PUBLICATION orders_pub
FOR TABLE public.orders;
~~~

Sau đó giới hạn:

~~~sql
ALTER PUBLICATION orders_pub
SET TABLE public.orders
WHERE (status = 'completed');
~~~

Việc đổi filter không tự động xóa những rows đã được subscriber nhận trước đây nhưng giờ không còn thỏa điều kiện. Nó cũng không tự nạp lại toàn bộ rows hiện tại theo predicate mới.

Khi thay scope, cần quyết định:

- Có cần resnapshot table không?
- Có cần xóa dữ liệu cũ không?
- Có cần copy các rows trước đây chưa được publish không?
- Có thay đổi replica identity/column list không?
- Có cần tạm dừng apply để thực hiện migration không?

Scope change là một thay đổi dữ liệu, không chỉ là metadata update.

## 40. Dữ liệu nhạy cảm và tenant isolation

Row filters và column lists có thể giảm lượng dữ liệu truyền tới subscriber, nhưng không nên xem publication là security boundary duy nhất.

Ví dụ tách dữ liệu tenant:

~~~sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE public.orders
    (order_id, tenant_id, status, total_amount)
    WHERE (tenant_id = 42);
~~~

Cần bảo đảm:

- Chỉ role quản trị được thay đổi publication.
- Subscriber chỉ cho user được phép đọc dữ liệu tenant đó.
- Không có publication khác mở rộng scope ngoài ý muốn.
- Không có table-local writes phá vỡ consistency.
- Row filter không bị thay đổi ngoài quy trình review.
- Backups của subscriber cũng được bảo vệ như dữ liệu nhạy cảm.

Nếu mục tiêu là cách ly bảo mật mạnh, xem xét kiến trúc riêng database/cluster, quyền truy cập subscriber và network segmentation, không chỉ row filter.

## 41. Logical replication và failover

Logical replication có thể được dùng để di chuyển dữ liệu hoặc cấp dữ liệu cho một hệ thống khác, nhưng không thay thế physical standby cho HA toàn cluster.

Khi publisher failover:

- Subscriber cần kết nối tới publisher mới.
- Logical replication slot cần tồn tại và có trạng thái phù hợp ở node mới.
- Subscription connection string có thể cần cập nhật.
- WAL/logical decoding state phải được xử lý theo version và HA design.
- Không phải mọi cấu hình slot đều tự được đồng bộ sang standby theo mặc định.

Thiết kế HA cho logical replication cần xem xét replication slot synchronization/failover support của major version cụ thể. Không giả định promote physical standby là mọi logical subscriber sẽ tiếp tục không gián đoạn.

## 42. Khi nào dùng logical replication?

Các use cases phổ biến:

- Replicate một số bảng sang reporting database.
- Di chuyển dữ liệu giữa major versions.
- Tách workload đọc/analytics.
- Chia sẻ dữ liệu giữa các hệ thống.
- Đồng bộ bảng theo tenant hoặc business domain.
- Tạo downstream pipeline phục vụ search/analytics.

Không phù hợp nếu yêu cầu là bản sao vật lý đầy đủ của cluster, cần replicate mọi DDL/global object hoặc cần multi-master conflict resolution mà không có kiến trúc bổ sung.

## 43. Logical replication và physical replication

| Tiêu chí | Logical replication | Physical replication |
| --- | --- | --- |
| Đơn vị thay đổi | Row-level logical changes | WAL physical changes |
| Scope | Publications/tables | Toàn bộ cluster physical |
| Chọn bảng | Có | Không |
| Row/column filter | Có, theo version/features | Không |
| DDL | Quản lý riêng | Theo WAL |
| Cross-version migration | Có thể phù hợp trong giới hạn hỗ trợ | Thường yêu cầu tương thích physical |
| Subscriber đọc | Database bình thường có thể ghi theo policy | Physical standby read-only khi recovery |
| Conflict handling | Có thể có apply conflicts | Physical replay theo WAL |
| HA toàn cluster | Không thay thế physical standby | Use case chính |

Chọn cơ chế theo mục tiêu. Có thể dùng cả hai trong cùng kiến trúc: physical standby cho HA và logical publication/subscription cho data distribution.

## 44. Ví dụ end-to-end: đồng bộ bảng orders

Giả sử:

- Publisher database: sales_prod.
- Subscriber database: sales_reporting.
- Publisher host: publisher.example.net.
- Replication role: logical_repl.
- Publication: orders_reporting_pub.
- Subscription: orders_reporting_sub.

### Bước 1: Tạo role trên publisher

~~~sql
CREATE ROLE logical_repl
    WITH LOGIN REPLICATION
         NOSUPERUSER NOCREATEDB NOCREATEROLE;
~~~

Đặt password bằng cơ chế an toàn. Cấp thêm quyền SELECT trên các bảng cần initial synchronization theo policy.

### Bước 2: Tạo publication

~~~sql
CREATE PUBLICATION orders_reporting_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete');
~~~

### Bước 3: Cấu hình HBA/network

Giới hạn subscriber host, dùng TLS và authentication method theo policy. HBA rule cần khớp user, source address và connection type.

### Bước 4: Tạo schema/table trên subscriber

~~~sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    total_amount numeric(12,2) NOT NULL
);
~~~

Cấu trúc phải tương thích với publisher.

### Bước 5: Tạo subscription

~~~sql
CREATE SUBSCRIPTION orders_reporting_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION orders_reporting_pub
WITH (copy_data = true);
~~~

### Bước 6: Theo dõi

Subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription
WHERE subname = 'orders_reporting_sub';
~~~

Publisher:

~~~sql
SELECT
    slot_name,
    active,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name = 'orders_reporting_sub';
~~~

### Bước 7: Xác minh dữ liệu

Đối chiếu row counts, aggregates và các invariant nghiệp vụ trên hai database. Kiểm tra apply worker không có lỗi và lag nằm trong ngưỡng vận hành.

## 45. Ví dụ: đồng bộ một tenant và một số cột

Publisher:

~~~sql
CREATE PUBLICATION tenant_42_reporting_pub
FOR TABLE public.orders
    (order_id, tenant_id, customer_id, status, total_amount)
    WHERE (tenant_id = 42);
~~~

Subscriber cần table tương thích:

~~~sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    customer_id bigint,
    status text,
    total_amount numeric(12,2)
);
~~~

Tạo subscription:

~~~sql
CREATE SUBSCRIPTION tenant_42_reporting_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl sslmode=verify-full'
PUBLICATION tenant_42_reporting_pub;
~~~

Kiểm thử các trường hợp:

- INSERT với tenant_id = 42.
- INSERT với tenant_id khác.
- UPDATE thay đổi status nhưng giữ tenant_id.
- UPDATE đổi tenant_id qua ranh giới filter.
- DELETE hàng thuộc tenant.
- TRUNCATE table nếu publication cho phép thao tác này.

Không triển khai row filter tenant production trước khi xác định rõ hành vi khi row chuyển tenant và cách reconciliation dữ liệu.

## 46. Thay đổi publication và refresh subscription

Publisher thêm bảng:

~~~sql
ALTER PUBLICATION orders_reporting_pub
ADD TABLE public.order_items;
~~~

Subscriber tạo table tương ứng trước. Sau đó refresh:

~~~sql
ALTER SUBSCRIPTION orders_reporting_sub
REFRESH PUBLICATION
WITH (copy_data = true);
~~~

PostgreSQL sẽ cập nhật relation membership và đồng bộ dữ liệu ban đầu cho bảng mới theo option.

Nếu subscriber đã được nạp baseline chính xác từ một quy trình khác:

~~~sql
ALTER SUBSCRIPTION orders_reporting_sub
REFRESH PUBLICATION
WITH (copy_data = false);
~~~

Chỉ chọn false khi đã xác nhận dữ liệu baseline nhất quán.

## 47. Các lỗi thường gặp

1. **Nghĩ publication tự tạo schema/table trên subscriber**, khiến initial sync lỗi relation does not exist.
2. **Nghĩ logical replication đồng bộ DDL**, trong khi schema migration phải triển khai riêng.
3. **Dùng publication cho toàn bộ bảng mà không kiểm tra dữ liệu nhạy cảm**, làm scope rộng hơn dự kiến.
4. **Quên refresh subscription sau khi thêm bảng**, khiến subscriber chưa nhận relation mới.
5. **Nghĩ bỏ bảng khỏi publication sẽ DROP bảng subscriber**, trong khi dữ liệu subscriber vẫn còn.
6. **Dùng copy_data=false khi subscriber chưa có baseline đồng nhất**, gây thiếu dữ liệu.
7. **Dùng copy_data=true trên bảng subscriber đã có dữ liệu trùng**, gây duplicate key.
8. **Không cấu hình replica identity**, khiến UPDATE/DELETE không thể được publish/apply.
9. **Dùng REPLICA IDENTITY FULL mà không đánh giá WAL/CPU**, làm chi phí tăng.
10. **Loại cột identity khỏi column list**, khiến subscriber không định danh được row.
11. **Hiểu row filter như một full refresh predicate**, bỏ qua các chuyển trạng thái qua ranh giới filter.
12. **Giả định row filter áp dụng cho TRUNCATE**, dẫn tới xóa dữ liệu subscriber ngoài dự kiến.
13. **Dùng nhiều publications chồng lấn mà không hiểu OR/column union**, làm scope rộng hơn dự kiến.
14. **Không chuẩn bị table schema tương thích**, làm apply worker dừng.
15. **Ghi local vào subscriber table**, tạo apply conflicts.
16. **Quên sequence state**, khiến subscriber promote hoặc ghi tiếp có thể tạo duplicate IDs.
17. **Giả định large objects, roles, extensions được replicate**, dù chúng nằm ngoài publication table stream.
18. **Không theo dõi replication slot**, làm WAL tích tụ và đầy disk.
19. **Drop slot khi subscriber còn cần**, khiến subscriber mất khả năng tiếp tục từ vị trí cũ.
20. **Không kiểm tra table sync state**, nhầm initial copy đang chạy với replication đã hoàn tất.
21. **Không theo dõi logs apply worker**, bỏ sót lỗi permission hoặc constraint.
22. **Dùng logical replication thay physical HA**, không đáp ứng yêu cầu cluster recovery.
23. **Thay row filter mà không resnapshot/reconcile**, để subscriber chứa rows cũ.
24. **Thay column list mà không phối hợp schema subscriber**, gây mismatch.
25. **Không kiểm tra behavior partitioned table**, khiến subscriber mapping sai.
26. **Coi subscription enabled là replication khỏe**, dù worker có thể lỗi hoặc lag.
27. **Lộ connection string trong catalog query/log**, làm lộ secret.
28. **Không test publisher failover và slot continuity**, khiến subscription ngừng khi primary đổi.

## 48. Bài tập thực hành có đáp án

### Bài 1. Publication là gì?

**Đáp án:** Đối tượng ở publisher xác định bảng và loại thay đổi được phát tới subscribers.

### Bài 2. Subscription là gì?

**Đáp án:** Đối tượng ở subscriber xác định publisher connection, publications cần nhận và cách đồng bộ/apply.

### Bài 3. Publication thuộc phạm vi nào?

**Đáp án:** Một database cụ thể; nó không phải cluster-wide object.

### Bài 4. Tạo publication cho một table

~~~sql
CREATE PUBLICATION orders_pub FOR TABLE public.orders;
~~~

**Đáp án:** Publish thay đổi của bảng orders theo publish operations mặc định.

### Bài 5. Tạo publication chỉ INSERT

~~~sql
CREATE PUBLICATION orders_insert_pub
FOR TABLE public.orders
WITH (publish = 'insert');
~~~

**Đáp án:** Chỉ phát INSERT.

### Bài 6. Publication mặc định thường phát thao tác nào?

**Đáp án:** INSERT, UPDATE, DELETE và TRUNCATE.

### Bài 7. Tạo publication cho tất cả bảng

~~~sql
CREATE PUBLICATION all_pub FOR ALL TABLES;
~~~

**Đáp án:** Publication có phạm vi rộng cho tất cả bảng đủ điều kiện trong database; cần quyền phù hợp.

### Bài 8. Schema-level publication được hỗ trợ từ phiên bản nào?

**Đáp án:** PostgreSQL 15 trở lên.

### Bài 9. Row filter dùng để làm gì?

**Đáp án:** Giới hạn các rows được publish theo biểu thức điều kiện.

### Bài 10. Viết filter tenant

~~~sql
CREATE PUBLICATION tenant_pub
FOR TABLE public.orders
WHERE (tenant_id = 42);
~~~

**Đáp án:** Chỉ publish các thay đổi cho hàng thỏa tenant_id = 42 theo semantics row filter.

### Bài 11. Row filter có lọc TRUNCATE không?

**Đáp án:** Không. TRUNCATE được điều khiển bởi publish option và không được biến thành xóa từng row theo filter.

### Bài 12. Column list dùng để làm gì?

**Đáp án:** Giới hạn các cột được gửi cho một bảng trong publication.

### Bài 13. Column list và row filter được giới thiệu từ PostgreSQL nào?

**Đáp án:** PostgreSQL 15.

### Bài 14. Replica identity mặc định dùng gì?

**Đáp án:** Primary key nếu bảng có primary key.

### Bài 15. REPLICA IDENTITY FULL làm gì?

**Đáp án:** Dùng toàn bộ row cũ làm thông tin nhận diện cho UPDATE/DELETE, với chi phí dữ liệu và tìm row cao hơn.

### Bài 16. Tạo subscription

~~~sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=publisher.example.net dbname=sales_prod user=logical_repl'
PUBLICATION orders_pub;
~~~

**Đáp án:** Tạo subscription nhận publication orders_pub từ publisher database sales_prod.

### Bài 17. copy_data=true nghĩa gì?

**Đáp án:** Copy dữ liệu hiện có của các bảng được subscribe trong initial table synchronization.

### Bài 18. copy_data=false nghĩa gì?

**Đáp án:** Bỏ initial copy; subscriber phải có baseline dữ liệu nhất quán từ quy trình khác.

### Bài 19. Thêm bảng vào publication có tự tạo table subscriber không?

**Đáp án:** Không. Triển khai schema ở subscriber và refresh publication.

### Bài 20. Refresh subscription

~~~sql
ALTER SUBSCRIPTION orders_sub REFRESH PUBLICATION;
~~~

**Đáp án:** Cập nhật relation membership theo publication hiện tại và đồng bộ bảng mới theo option.

### Bài 21. Bỏ table khỏi publication có xóa dữ liệu subscriber không?

**Đáp án:** Không. Nó ngừng nhận thay đổi cho table; dữ liệu subscriber vẫn còn.

### Bài 22. Logical replication có replicate DDL không?

**Đáp án:** Không tự replicate DDL; schema changes phải được triển khai riêng.

### Bài 23. Sequence state có được replicate liên tục không?

**Đáp án:** Không. Cần quản lý sequence state riêng, nhất là trước khi subscriber bắt đầu ghi.

### Bài 24. pg_replication_slots dùng để xem gì?

**Đáp án:** Logical/physical slots, trạng thái active và LSN tiến độ/retention.

### Bài 25. Vì sao slot inactive có thể nguy hiểm?

**Đáp án:** Nó có thể giữ WAL cần thiết lâu dài, làm pg_wal tăng và đầy disk.

### Bài 26. pg_stat_subscription dùng để làm gì?

**Đáp án:** Theo dõi apply worker, received LSN và thời gian nhận message theo version.

### Bài 27. pg_subscription_rel dùng để làm gì?

**Đáp án:** Xem trạng thái table synchronization của từng relation trong subscription.

### Bài 28. Logical replication có tự xử lý local write conflict không?

**Đáp án:** Không có conflict resolution tổng quát; apply worker có thể dừng khi vi phạm constraint hoặc dữ liệu xung đột.

### Bài 29. Một subscription có thể nhận nhiều publications không?

**Đáp án:** Có, từ cùng một publisher database.

### Bài 30. Khi nào cần chọn physical replication thay logical replication?

**Đáp án:** Khi cần bản sao vật lý toàn cluster/HA và không cần giới hạn phạm vi ở mức table/row/column.

## 49. Checklist triển khai publication/subscription

- [ ] Xác định publisher, subscriber và nguồn sự thật của dữ liệu.
- [ ] Xác định rõ database và publication scope.
- [ ] Chọn table/schema/all tables theo nguyên tắc tối thiểu cần thiết.
- [ ] Chọn publish operations: INSERT/UPDATE/DELETE/TRUNCATE.
- [ ] Kiểm tra row filters và semantics khi row chuyển qua filter.
- [ ] Kiểm tra column lists và replica identity columns.
- [ ] Chuẩn bị primary key/replica identity phù hợp cho UPDATE/DELETE.
- [ ] Kiểm tra PostgreSQL version hỗ trợ schema publication/row filters/column lists.
- [ ] Tạo replication role và HBA/network controls phù hợp.
- [ ] Bảo vệ connection credentials và TLS.
- [ ] Tạo schema/table tương thích trên subscriber.
- [ ] Chuẩn bị extensions và object dependencies.
- [ ] Quyết định copy_data true/false dựa trên baseline.
- [ ] Kiểm tra initial table sync state.
- [ ] Refresh publication sau khi scope thay đổi.
- [ ] Xác định cách triển khai DDL riêng.
- [ ] Lập kế hoạch sequence/large object/global object.
- [ ] Theo dõi pg_stat_subscription và pg_subscription_rel.
- [ ] Theo dõi pg_replication_slots và WAL retention.
- [ ] Theo dõi publisher/subscriber logs và apply conflicts.
- [ ] Không ghi local vào subscribed tables nếu không có thiết kế conflict.
- [ ] Test INSERT/UPDATE/DELETE/TRUNCATE theo scope.
- [ ] Test row filter boundary transitions.
- [ ] Test partition behavior.
- [ ] Xác minh dữ liệu, constraints, indexes và quyền subscriber.
- [ ] Test disable/enable và reconnect.
- [ ] Test publisher failover/slot continuity theo HA design.
- [ ] Bảo vệ dữ liệu subscriber như dữ liệu nguồn.
- [ ] Ghi lại RPO/lag target và runbook phục hồi.

## 50. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — tổng quan publisher/subscriber và kiến trúc.
- [Publication](https://www.postgresql.org/docs/current/logical-replication-publication.html) — tạo publication, table scope, row filters, column lists và partition behavior.
- [Subscription](https://www.postgresql.org/docs/current/logical-replication-subscription.html) — tạo subscription, initial sync, refresh và lifecycle.
- [Logical Replication Architecture](https://www.postgresql.org/docs/current/logical-replication-architecture.html) — workers, apply và synchronization.
- [Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html) — DDL, sequences, large objects và các giới hạn.
- [CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html) — syntax và publication options.
- [ALTER PUBLICATION](https://www.postgresql.org/docs/current/sql-alterpublication.html) — thay đổi table/schema scope.
- [CREATE SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-createsubscription.html) — connection, copy_data, slot và options.
- [ALTER SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-altersubscription.html) — enable/disable, refresh, connection và publication list.
- [Logical Replication Monitoring](https://www.postgresql.org/docs/current/logical-replication-monitoring.html) — system views để theo dõi.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL sender, slots và replication settings.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — slot lifecycle và WAL retention.
- [REPLICA IDENTITY](https://www.postgresql.org/docs/current/sql-altertable.html) — cấu hình row identity trên table.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — quyền truy cập objects.
- [Client Connection Parameters](https://www.postgresql.org/docs/current/libpq-connect.html) — TLS và connection parameters.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Row filters, column lists, schema publications, partition options, subscription privileges và monitoring columns có thể thay đổi theo major version; xác nhận tài liệu đúng phiên bản server/client trước khi triển khai production.

## 51. Tổng kết

**Publication định nghĩa dữ liệu và thao tác được phát; subscription định nghĩa nguồn dữ liệu được nhận và cách apply thay đổi.** Việc kiểm soát scope là trách nhiệm thiết kế quan trọng của logical replication.

1. **Publication nằm ở publisher database; subscription nằm ở subscriber database.**
2. **Publication có thể chọn table, schema hoặc tất cả bảng đủ điều kiện**, tùy phiên bản và quyền.
3. **Publish operations gồm INSERT, UPDATE, DELETE và TRUNCATE.** Không mặc định bật mọi thao tác nếu yêu cầu dữ liệu không cần.
4. **Row filters giới hạn hàng và column lists giới hạn cột**, với tính năng được hỗ trợ từ PostgreSQL 15.
5. **TRUNCATE không được row filter lọc theo từng hàng.** Phải cân nhắc dữ liệu local trên subscriber.
6. **UPDATE/DELETE cần replica identity phù hợp.** FULL có chi phí cao hơn và cần benchmark.
7. **Subscription có thể copy dữ liệu ban đầu**, sau đó apply thay đổi liên tục.
8. **copy_data=false chỉ an toàn khi subscriber đã có baseline nhất quán.**
9. **Publication thay đổi cần refresh subscription khi relation membership/metadata cần cập nhật.** Bỏ bảng khỏi publication không tự xóa dữ liệu subscriber.
10. **DDL, sequences, large objects, roles và extensions cần quy trình riêng.**
11. **Replication slots giữ WAL cho consumer.** Slot không tiến có thể làm đầy disk.
12. **Logical replication không phải multi-master conflict resolver hoặc bản sao vật lý toàn cluster.**
13. **Theo dõi apply workers, table sync, slot lag và logs** để phát hiện lỗi sớm.
14. **Test scope transitions, schema migrations và failover** trước khi vận hành production.

Một thiết kế publication/subscription tốt phải xác định chính xác bảng, hàng, cột và thao tác được chia sẻ; chuẩn bị schema tương thích ở subscriber; đồng thời có quy trình quản lý thay đổi và kiểm chứng dữ liệu liên tục.
