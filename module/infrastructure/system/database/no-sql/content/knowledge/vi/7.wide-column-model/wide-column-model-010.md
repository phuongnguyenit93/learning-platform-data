# Chỉ mục phụ và lựa chọn dựa trên đặc điểm phiên bản/sản phẩm

Trong cơ sở dữ liệu **cột rộng** (*wide-column database*), thiết kế dữ liệu thường bắt đầu bằng câu hỏi: **ứng dụng cần đọc theo khóa nào, trên phạm vi partition nào và theo thứ tự nào?** Cách tổ chức partition key và clustering key giúp những truy vấn chính truy cập đúng dữ liệu mà không phải dò qua nhiều partition. Nhưng sản phẩm thực tế đôi khi cần tìm bản ghi theo thuộc tính không nằm trong khóa chính: trạng thái đơn hàng, email người dùng, loại thiết bị, thời điểm tạo, thẻ phân loại hoặc mã tham chiếu từ đối tác.

**Chỉ mục phụ** (*secondary index*) là một cách tạo thêm đường truy cập từ thuộc tính không phải khóa truy cập chính đến những bản ghi cần tìm. Tuy vậy, trong họ cơ sở dữ liệu cột rộng, cùng cụm từ “secondary index” có thể chỉ các cơ chế rất khác nhau. Apache Cassandra có chỉ mục phụ truyền thống (thường gọi **2i**) và, ở các phiên bản hỗ trợ, **Storage-Attached Index (SAI)**. ScyllaDB có các cơ chế chỉ mục phụ với triển khai và khả năng định tuyến riêng. Apache HBase thường được truy cập trực tiếp bằng row key hoặc scan; việc tìm theo thuộc tính khác có thể dựa vào Apache Phoenix, bảng chỉ mục do ứng dụng quản lý hoặc hệ tìm kiếm bổ trợ. Dịch vụ được quản lý và sản phẩm tương thích API cũng có thể khác nhau về tính năng, phiên bản và giới hạn.

Vì vậy, thiết kế đúng không bắt đầu bằng câu “wide-column có secondary index hay không?” mà bằng: **truy vấn nào cần tối ưu, cơ chế chỉ mục nào thực sự có trong đúng phiên bản/sản phẩm, chỉ mục được duy trì và phân phối thế nào, và chi phí đọc–ghi có đáp ứng workload hay không?**

## 1. Từ truy vấn theo khóa chính đến nhu cầu chỉ mục phụ

Giả sử hệ thống bán hàng tổ chức đơn hàng theo cửa hàng:

~~~sql
CREATE TABLE orders_by_store (
    store_id uuid,
    order_id timeuuid,
    status text,
    customer_id uuid,
    created_at timestamp,
    amount decimal,
    PRIMARY KEY ((store_id), order_id)
) WITH CLUSTERING ORDER BY (order_id DESC);
~~~

Với cấu trúc này, ứng dụng có thể truy cập các đơn của một cửa hàng bằng partition key:

~~~sql
SELECT order_id, status, customer_id, amount
FROM orders_by_store
WHERE store_id = ?;
~~~

Partition key xác định nhóm dữ liệu, còn clustering key **order_id** điều khiển tổ chức và thứ tự trong partition. Đây là ví dụ CQL theo phong cách Cassandra/ScyllaDB. Những cơ sở dữ liệu cột rộng khác, như HBase, có ngữ nghĩa bảng và API khác; không nên áp dụng cú pháp CQL cho mọi sản phẩm.

Giờ bổ sung yêu cầu: **“Tìm tất cả đơn đang chờ xử lý của cửa hàng A.”** Truy vấn mong muốn:

~~~sql
SELECT order_id, customer_id, amount
FROM orders_by_store
WHERE store_id = ? AND status = 'PENDING';
~~~

Cột **status** không phải một thành phần của primary key. Tùy phiên bản database, loại index, điều kiện truy vấn và cấu hình, câu lệnh có thể bị từ chối, yêu cầu chỉ mục, phải lọc thêm, hoặc tạo một truy vấn không phù hợp khi dữ liệu lớn. Không nên cho phép quét toàn bộ dữ liệu rồi lọc trong ứng dụng chỉ vì bộ dữ liệu thử nghiệm nhỏ.

Một chỉ mục phụ về mặt ý tưởng duy trì ánh xạ:

~~~text
Thuộc tính được tra cứu              Vị trí/bản ghi đích

status = PENDING       ────────>    (store-1, order-101)
                          ├────>    (store-1, order-108)
                          └────>    (store-2, order-203)

status = COMPLETED     ────────>    (store-1, order-100)
                          └────>    (store-3, order-304)
~~~

Đây là mô hình khái niệm. Trong thực tế, chỉ mục có thể nằm cùng các tệp lưu trữ của từng node, là cấu trúc riêng theo shard, hoặc được hiện thực dưới dạng bảng/view bổ sung. **Cách phân phối chỉ mục quyết định một truy vấn theo status phải liên lạc với bao nhiêu node và lấy bản ghi thật từ đâu.**

## 2. Vì sao chỉ mục phụ không phải lời giải mặc định?

Trong hệ quan hệ, tạo một B-tree index trên cột thường là lựa chọn quen thuộc. Với wide-column phân tán, câu hỏi phức tạp hơn vì dữ liệu được chia thành nhiều partition và có thể được sao chép ở nhiều node. Một truy vấn theo cột không phải partition key có thể không biết trước node nào chứa kết quả.

Có thể hình dung hai kiểu đường đi:

~~~text
Tra cứu bằng partition key:
Client -> Coordinator -> Replica phụ trách partition -> Rows
                     (đích được xác định theo khóa)

Tra cứu bằng thuộc tính phụ:
Client -> Coordinator -> Tìm chỉ mục trên nhiều vùng dữ liệu
                     -> Xác định row/partition ứng viên
                     -> Đọc bản ghi tương ứng -> Kết quả
~~~

Số bước thực tế phụ thuộc loại index. Không phải mọi secondary index đều phát sinh hai round trip hoặc scan toàn cụm; cũng không phải index nào cũng loại được fan-out khi thiếu partition key.

### Các chi phí cần tính

| Chi phí | Biểu hiện | Vì sao quan trọng |
| --- | --- | --- |
| **Write amplification** | Một cập nhật dữ liệu gốc tạo thêm việc cập nhật chỉ mục. | Ghi nhiều, cột index thay đổi liên tục có thể tăng latency, I/O và compaction. |
| **Dung lượng** | Posting list, metadata, index table hoặc view dùng thêm disk/RAM. | Chỉ mục trên nhiều cột có thể làm tăng đáng kể dung lượng lưu trữ và backup. |
| **Fan-out** | Query phải liên lạc nhiều node/shard/partition. | Tail latency và khả năng chịu lỗi phụ thuộc nhiều điểm trong cụm. |
| **Lookup bổ sung** | Kết quả index chỉ chứa khóa ứng viên, sau đó phải fetch dữ liệu gốc. | Truy vấn trả về nhiều row có thể tạo nhiều lần đọc. |
| **Độ chọn lọc thấp** | Một giá trị như ACTIVE xuất hiện trong 90% bản ghi. | Chỉ mục tìm được quá nhiều ứng viên nên ít giúp giảm chi phí quét. |
| **Giá trị cực nóng** | Một từ khóa/nhãn được đọc hoặc cập nhật rất nhiều. | Cấu trúc index hoặc partition liên quan dễ bị nghẽn. |
| **Xóa/cập nhật** | Tombstone, TTL, stale entry, reindex/repair. | Hiệu quả index thay đổi theo vòng đời dữ liệu, không chỉ lúc nạp ban đầu. |
| **Điều hành** | Build, rebuild, nâng phiên bản, quan sát index trạng thái chưa sẵn sàng. | Một index khả dụng về cú pháp vẫn có thể chưa sử dụng được lúc triển khai. |

Chỉ mục phụ **không biến cơ sở dữ liệu cột rộng thành công cụ truy vấn ad hoc tự do với chi phí luôn thấp**. Nếu sản phẩm cần lọc 15 trường tùy chọn, sắp xếp bất kỳ và phân trang sâu, phải đánh giá riêng khả năng lập kế hoạch truy vấn của sản phẩm hoặc thiết kế một tầng tìm kiếm/analytics phù hợp.

## 3. Các khái niệm cần phân biệt khi đánh giá index

### 3.1. Primary key, partition key và clustering key

Trong Cassandra/ScyllaDB, **partition key** quyết định cách định tuyến và phân vùng; **clustering key** sắp xếp các hàng bên trong partition theo cấu hình. Một truy vấn dùng đầy đủ partition key và khoảng clustering phù hợp thường là đường truy cập dự kiến từ lúc mô hình hóa dữ liệu.

Ví dụ:

~~~sql
CREATE TABLE events_by_device (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    kind text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Truy vấn “liệt kê sự kiện gần đây của thiết bị X trong ngày Y” phù hợp với tổ chức partition. Truy vấn “mọi sự kiện kind = ERROR của tất cả thiết bị trong 30 ngày” lại không tìm được partition trực tiếp; đó là một **access pattern khác**, cần index, bảng truy vấn chuyên biệt hoặc hệ phân tích.

### 3.2. Selectivity và cardinality

**Cardinality** là số giá trị khác nhau của thuộc tính. **Selectivity** mô tả độ thu hẹp tập bản ghi khi áp dụng một điều kiện; có thể biểu diễn đơn giản bằng tỷ lệ số bản ghi khớp trên tổng số bản ghi trong phạm vi xét.

~~~text
10.000.000 bản ghi

status = ACTIVE   khớp 9.000.000  -> 90% bản ghi: ít chọn lọc
email = a@b.com   khớp 1          -> gần 0%: rất chọn lọc
~~~

Không có quy tắc bất biến rằng “cardinality cao luôn tốt” hay “cardinality thấp luôn xấu”. Tối ưu thực tế phụ thuộc **phiên bản/index engine**, phân bố giá trị, giới hạn partition, số dòng trả về, các predicate kết hợp, cách tìm trên node và thời điểm đọc dữ liệu gốc. Ví dụ cột status chỉ có ba giá trị có thể hiệu quả nếu **đã xác định store_id** và mỗi store chỉ có ít đơn; nhưng truy vấn toàn hệ theo ACTIVE với hàng triệu kết quả thường không đáng dùng index đơn lẻ.

### 3.3. Local index, global index và nơi duy trì index

Thuật ngữ **local** và **global** dễ bị hiểu nhầm vì có thể mang nghĩa khác giữa sản phẩm:

- **Local theo dữ liệu/partition:** chỉ mục gắn với phần dữ liệu tại node/shard hoặc một partition. Tìm thuộc tính phụ mà không biết partition có thể phải hỏi nhiều nơi.
- **Global theo khóa tra cứu:** cấu trúc chỉ mục riêng được tổ chức theo giá trị index để định tuyến truy vấn theo thuộc tính phụ. Đường ghi có thể phải ghi thêm một partition/index view khác.
- **Storage-attached:** index được gắn với đường lưu trữ và tệp dữ liệu, tận dụng vòng đời SSTable/compaction và cấu trúc tìm kiếm của engine.

Đây là những ý tưởng, **không phải ba định nghĩa API dùng chung**. Trước khi chọn chỉ mục có tên “local”, phải đọc tài liệu đúng sản phẩm xem “local” có nghĩa cùng partition, cùng node, cùng region hay một cơ chế triển khai cụ thể.

### 3.4. Chỉ mục phụ không nhất thiết đảm bảo uniqueness

Một index trên email giúp tìm người dùng theo email nhưng **không mặc nhiên tạo ràng buộc email duy nhất**. Hai request cạnh tranh có thể cùng chèn dữ liệu chứa một email nếu chỉ dựa vào việc “index đã tồn tại”.

Yêu cầu uniqueness phải được thực thi bằng **khóa duy nhất, cập nhật điều kiện, transaction hoặc giao thức phù hợp**. Nếu dùng bảng ngược email → user_id, quá trình claim email và tạo user cũng phải xử lý xung đột/idempotency và tình huống lỗi giữa hai thao tác.

## 4. Apache Cassandra: 2i, SASI và SAI là những công nghệ khác nhau

Cassandra có lịch sử nhiều cơ chế secondary indexing. Không thể đọc một bài benchmark “Cassandra index” rồi suy ra kết quả cho phiên bản đang chạy.

| Cơ chế | Bản chất và vị trí trong lịch sử | Điều cần cân nhắc |
| --- | --- | --- |
| **Secondary index truyền thống (2i)** | Chỉ mục phụ kiểu cũ, được duy trì gắn với các replica/dữ liệu tại node. | Với nhiều truy vấn không có partition key, coordinator có thể phải hỏi nhiều node; độ chọn lọc, số kết quả và phân bố giá trị ảnh hưởng mạnh. |
| **SASI** (*SSTable-Attached Secondary Index*) | Cơ chế index tùy chọn xuất hiện trong các phiên bản trước; có giới hạn và lịch sử bảo trì/khuyến nghị riêng. | Không nên coi SASI là SAI hoặc chọn SASI cho hệ mới chỉ vì nhìn thấy cú pháp trong blog cũ. Phải xác minh hỗ trợ và tình trạng theo bản phát hành. |
| **SAI** (*Storage-Attached Index*) | Cơ chế index gắn với bộ lưu trữ; có trong Apache Cassandra 5.0. | Kiểm tra tính năng/operator, kiểu dữ liệu hỗ trợ, predicate, hiệu năng, lifecycle và trạng thái index của bản triển khai cụ thể. |

Điểm cần nhớ: **SAI không phải tên gọi mới của 2i/SASI**. Chúng có thiết kế khác nhau, nên kết quả benchmark, cú pháp và khuyến nghị vận hành không thể trộn lẫn.

### 4.1. Ví dụ tạo SAI trong Apache Cassandra 5.0

Ví dụ theo cú pháp CQL sử dụng provider **StorageAttachedIndex** trong bản hỗ trợ SAI:

~~~sql
CREATE TABLE orders_by_store (
    store_id uuid,
    order_id timeuuid,
    status text,
    customer_id uuid,
    amount decimal,
    PRIMARY KEY ((store_id), order_id)
);

CREATE CUSTOM INDEX IF NOT EXISTS orders_status_sai
ON orders_by_store (status)
USING 'StorageAttachedIndex';
~~~

Một truy vấn theo status có thể tận dụng index nếu cú pháp và predicate được phiên bản đó hỗ trợ:

~~~sql
SELECT store_id, order_id, amount
FROM orders_by_store
WHERE status = 'PENDING';
~~~

Tuy nhiên, truy vấn trên không có **store_id**. Index có thể giúp xác định bản ghi khớp, nhưng phải xem **fan-out trên các replica, số kết quả, phân trang và lượng dữ liệu fetch**. Nếu 60% đơn toàn cụm ở trạng thái PENDING thì dù index hoạt động, việc xuất ra hàng triệu bản ghi vẫn là workload rất tốn kém.

Nếu ứng dụng thực sự chỉ xem đơn PENDING **trong một cửa hàng**, cần xem cách engine kết hợp điều kiện partition với index và đo đường truy vấn thực tế. Không tự mặc định việc thêm index làm mọi dạng lọc/sắp xếp trở nên hợp lệ hoặc rẻ.

### 4.2. Những giới hạn query cần tra theo bản phát hành

Cùng là index trên cột, cơ chế có thể hỗ trợ khác nhau đối với:

- Phép so sánh bằng, khoảng giá trị, toán tử **IN**, kết hợp nhiều điều kiện.
- Kiểu số, text, date, collection, map entry hoặc vector; cú pháp index cho phần tử collection.
- Nhiều chỉ mục tham gia cùng truy vấn; **AND/OR**, thao tác lọc trên clustering column.
- **ORDER BY**, **GROUP BY**, phân trang, giới hạn kết quả và các điều kiện không gắn partition key.
- TTL, delete/tombstone, compaction, rebuild và khoảng thời gian index chưa sẵn sàng.
- Hiệu năng khi cùng lúc ghi và query theo thuộc tính index có cardinality khác nhau.

Ví dụ, một hệ hỗ trợ index cột **status** không có nghĩa câu lệnh **ORDER BY amount DESC** trên toàn cụm được thực hiện như một truy vấn có thứ tự tối ưu. **Chỉ mục tìm được các hàng ứng viên** và **khả năng sắp xếp kết quả** là hai chức năng riêng; không suy diễn từ một chức năng sang chức năng còn lại.

### 4.3. ALLOW FILTERING không thay thế thiết kế index

Trong CQL, **ALLOW FILTERING** có thể cho phép một số dạng truy vấn mà hệ không khuyến khích vì cần lọc thêm. Nó **không tạo index** và không bảo đảm truy vấn sẽ mở rộng hiệu quả khi dữ liệu lớn. Có trường hợp lọc nhỏ sau khi đã giới hạn bằng partition key là chấp nhận được; với truy vấn rộng, ALLOW FILTERING có thể dẫn tới quét lượng lớn dữ liệu, timeout và tail latency cao.

Cần so sánh lựa chọn **mô hình lại theo truy vấn**, **secondary index đúng phiên bản**, **materialized view/bảng denormalized**, hoặc **search engine**. Dùng ALLOW FILTERING như một biện pháp khắc phục tổng quát là một tín hiệu phải xem lại access pattern.

## 5. ScyllaDB: chú ý cơ chế index và khả năng định tuyến

ScyllaDB dùng CQL nhưng **không đồng nghĩa mọi index behavior giống Apache Cassandra**. Các cơ chế secondary index trong ScyllaDB có liên quan đến các view/index table được duy trì từ dữ liệu gốc; giữa các loại index có thể khác biệt về **cách phân phối dữ liệu chỉ mục, điều kiện query và số lượt đọc cần để lấy hàng gốc**.

Khi xem tài liệu hoặc chạy thử, cần ghi rõ:

1. Phiên bản ScyllaDB, edition và topology.
2. Loại index được hỗ trợ trong phiên bản đó; **local/global** được định nghĩa thế nào.
3. Cột index có tương ứng partition key hoặc clustering key của bảng gốc không.
4. Query có chứa partition key bảng gốc và predicate nào; có phải truy cập index table rồi quay lại bảng gốc không.
5. Thời điểm cập nhật index được nhìn thấy; lỗi tạm thời hoặc rebuild ảnh hưởng ra sao.
6. Cột index có thể bị cập nhật thường xuyên không; index/view cần bao nhiêu write amplification.
7. Có giới hạn nào cho **collection, static column, TTL, materialized view hoặc truy vấn nhiều predicate** không.

Không nên bê câu lệnh hoặc benchmark “SAI Cassandra 5.0” sang ScyllaDB mà mặc định cùng provider. Cũng không nên mặc định có index cho phép mọi loại điều kiện chỉ vì CQL parser có từ khóa **CREATE INDEX**. Điều quyết định là **tài liệu tính năng của chính sản phẩm và truy vấn thực chạy theo workload**.

## 6. HBase và Apache Phoenix: index thường là cấu trúc bổ sung

Apache HBase tổ chức truy cập chủ yếu theo **row key** và các bộ lọc/scan theo phạm vi. Nếu row key không chứa giá trị cần tìm, việc scan một bảng lớn có thể rất tốn kém. Không nên suy rằng HBase có cùng kiểu CREATE INDEX của Cassandra.

**Apache Phoenix**, khi dùng trên HBase ở triển khai/phiên bản phù hợp, cung cấp lớp SQL và khả năng quản lý index. Một index có thể tạo ra **cấu trúc dữ liệu tương ứng trên HBase** để truy vấn dựa trên cột khác với row key. Tùy phiên bản, có các phương án liên quan tới **global index**, **local index**, việc lưu thêm cột, và quá trình cập nhật trạng thái chỉ mục.

Ví dụ *minh họa ý tưởng*, không phải DDL có thể chạy trên mọi HBase/Phoenix:

~~~sql
-- Kiểu cú pháp CREATE INDEX phụ thuộc phiên bản Phoenix
CREATE INDEX idx_events_kind ON events(kind);
~~~

Trước khi áp dụng cần xác định thật sự ứng dụng có chạy **Phoenix** hay chỉ đang dùng HBase API; xem tên schema/table, kiểu dữ liệu, quy tắc index và optimizer của Phoenix. Một câu SQL **CREATE INDEX** trong Phoenix không tự biến thành tính năng của client HBase thuần.

### Tùy chọn bảng chỉ mục do ứng dụng duy trì

Nếu hệ không có secondary index phù hợp, có thể tự tạo bảng ánh xạ ngược:

~~~text
Bảng gốc:
rowkey = DEVICE#42#2026-11-14#EVENT#999
value  = {kind: ERROR, timestamp: ..., payload: ...}

Bảng tra cứu phụ:
rowkey = KIND#ERROR#2026-11-14#DEVICE#42#EVENT#999
value  = {originalRowKey: DEVICE#42#2026-11-14#EVENT#999}
~~~

Truy vấn theo **kind = ERROR**, ngày 2026-11-14 có thể quét một khoảng row key được thiết kế theo nhu cầu, thay vì toàn bộ bảng gốc. Nhưng ứng dụng giờ phải chịu trách nhiệm:

- Ghi bảng gốc và bảng index theo thứ tự/chính sách nhất quán.
- Xử lý lỗi một bên ghi thành công, bên kia thất bại; retry idempotent.
- Cập nhật/xóa entry cũ khi kind thay đổi, kể cả TTL hoặc xóa bản ghi.
- Tái dựng index từ dữ liệu gốc khi bị lỗi hoặc thay schema.
- Phân tán key để tránh mọi sự kiện cùng kind/day dồn vào một region/partition.
- Quy định người dùng có thể thấy entry cũ bao lâu trước khi quá trình đồng bộ hoàn tất.

Nếu không có transaction phù hợp trên cả hai bảng, mô hình này thường mang **nhất quán cuối cùng** cho đường tra cứu phụ. Một cách xây dựng đáng tin cậy là dùng luồng thay đổi dữ liệu/event log/outbox có khả năng replay và reconciliation, tùy hạ tầng cho phép.

## 7. Dịch vụ tương thích CQL và hệ cột rộng được quản lý

Khi dùng **Amazon Keyspaces**, **DataStax Enterprise/Astra DB** hoặc dịch vụ managed khác, tên API và cú pháp có thể gần Cassandra nhưng **ma trận tính năng không nhất thiết giống bản Apache Cassandra tự vận hành**. Mức độ hỗ trợ index, loại index, materialized view, vector search, giới hạn truy vấn hoặc lộ trình nâng cấp có thể khác theo edition/Region/phiên bản dịch vụ.

Với **Google Cloud Bigtable**, hãy xác định các cơ chế truy cập và tính năng index/tìm kiếm hiện hành của dịch vụ thay vì coi CQL CREATE INDEX là tính năng mặc định. Row-key design, prefix/range scan, bảng tra cứu riêng và dịch vụ tìm kiếm phụ trợ là những phương án cần đối chiếu với tính năng thực tế.

**Quy tắc triển khai:** viết cụ thể *sản phẩm + phiên bản/dịch vụ + loại index + query dự kiến*. Ví dụ “Cassandra 5.0 với SAI trên status” chính xác hơn “NoSQL có secondary index”.

## 8. Khi nào chọn index, khi nào tạo bảng theo truy vấn?

Giả sử ứng dụng cần ba API:

~~~text
GET /stores/{storeId}/orders?limit=50
GET /stores/{storeId}/orders?status=PENDING&limit=50
GET /customers/{customerId}/orders?limit=50
~~~

Một mô hình chỉ có **orders_by_store** đáp ứng tốt đường thứ nhất, nhưng hai đường còn lại có điều kiện truy cập khác.

### Phương án A — Chỉ mục phụ

Giữ bảng **orders_by_store**, thêm index trên **status** hoặc **customer_id** nếu engine hỗ trợ và benchmark chứng minh phù hợp.

Ưu điểm:
- Ít phải tự thiết kế bảng đồng bộ theo từng truy vấn.
- Có thể bổ sung một số truy vấn khi không đổi khóa truy cập chính.
- Engine đảm nhận một phần vòng đời cập nhật index.

Nhược điểm:
- Query không có partition key có thể fan-out; index khác nhau theo engine.
- Ghi/update chịu thêm chi phí index.
- Khả năng sort, predicate, TTL, consistency và phân trang bị giới hạn theo sản phẩm.
- Query có nhiều kết quả hoặc giá trị ít chọn lọc có thể vẫn đắt.

### Phương án B — Bảng denormalized theo access pattern

Tạo bảng phục vụ chính xác truy vấn cần chạy:

~~~sql
CREATE TABLE orders_by_store_status (
    store_id uuid,
    status text,
    order_id timeuuid,
    customer_id uuid,
    amount decimal,
    PRIMARY KEY ((store_id, status), order_id)
) WITH CLUSTERING ORDER BY (order_id DESC);
~~~

Truy vấn:

~~~sql
SELECT order_id, customer_id, amount
FROM orders_by_store_status
WHERE store_id = ? AND status = ?
LIMIT 50;
~~~

Bảng được tổ chức để đọc trực tiếp một partition, thường dễ dự báo chi phí truy vấn hơn nếu dữ liệu được phân bố hợp lý. Nhưng đổi trạng thái đơn từ **PENDING** sang **COMPLETED** phải **xóa entry ở partition cũ và tạo entry mới**; nếu nguồn dữ liệu gốc nằm bảng khác, cần quản lý đồng bộ, lỗi giữa các lần ghi và khôi phục. Một status/store có lượng đơn cực lớn còn có thể tạo partition quá to: nên đưa thêm **time bucket** hoặc chiều phân vùng phù hợp.

Cần cân nhắc cả API **orders_by_customer**:

~~~sql
CREATE TABLE orders_by_customer (
    customer_id uuid,
    order_id timeuuid,
    store_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id), order_id)
) WITH CLUSTERING ORDER BY (order_id DESC);
~~~

Đây không phải “chuẩn hóa” dữ liệu kiểu SQL quan hệ, mà là **sao chép có chủ đích phục vụ truy vấn**. Thiết kế nên xác định bản ghi nguồn của sự thật, cách phát sự kiện cập nhật, idempotency, thứ tự thay đổi và cách đối soát.

### Phương án C — Tầng tìm kiếm hoặc phân tích

Nếu người dùng muốn lọc theo nhiều trường tùy ý, tìm full-text, faceting và sắp xếp linh hoạt, một tầng **search index** chuyên dụng có thể hợp lý hơn. Dữ liệu gốc phát thay đổi sang index; hệ có thể cho phép **độ trễ cập nhật có giới hạn** và hiển thị thời điểm dữ liệu được đồng bộ.

Ưu điểm là linh hoạt trong tìm kiếm; nhược điểm là thêm một hệ thống phải vận hành, pipeline đồng bộ, backfill, xử lý duplicate và reindex. Không dùng chỉ mục tìm kiếm cập nhật bất đồng bộ làm cơ chế duy nhất quyết định một giao dịch đòi hỏi atomicity.

### Ma trận ra quyết định

| Đặc điểm nhu cầu | Index phụ của engine | Bảng theo truy vấn | Search/analytics chuyên dụng |
| --- | --- | --- | --- |
| Truy vấn theo một vài cột phụ | Có thể phù hợp nếu engine hỗ trợ và selectivity tốt | Rất phù hợp khi access pattern ổn định | Thường thừa nếu chỉ có lookup đơn giản |
| Đọc với QPS rất cao, mẫu truy vấn ổn định | Cần benchmark fan-out và chi phí index | Thường dễ định tuyến và dự báo | Có thể thêm độ trễ và chi phí vận hành |
| Nhiều filter/sort tự do | Khả năng phụ thuộc engine/phiên bản | Cần nhiều bảng, khó tổ hợp | Thường thuận lợi hơn |
| Ghi/cập nhật thuộc tính index liên tục | Có write amplification | Phải duy trì nhiều bản ghi | Pipeline update/reindex phát sinh chi phí |
| Dữ liệu phải đồng bộ tức thời giữa nhiều dạng đọc | Kiểm tra bảo đảm và phạm vi consistency | Cần transaction/giao thức đồng bộ phù hợp | Thường có độ trễ hội tụ |
| Tải lớn trên giá trị ít chọn lọc | Có thể fan-out và trả rất nhiều kết quả | Phân vùng theo khóa truy vấn và bucket | Cần đo truy vấn phổ biến, cache và phân mảnh |
| Chi phí vận hành tối thiểu | Ít hệ thống hơn nhưng phụ thuộc tính năng engine | Nhiều bảng và quy tắc đồng bộ | Thêm sản phẩm/pipeline |

**Không có một lựa chọn thắng cho mọi truy vấn.** Chọn dựa trên workload được đo: dữ liệu lớn đến đâu, bao nhiêu request/s, bao nhiêu kết quả, giá trị nào nóng, tỷ lệ cập nhật thuộc tính index và mức nhất quán cần đạt.

## 9. Phương pháp đánh giá theo phiên bản và sản phẩm

Trước khi viết **CREATE INDEX** vào migration, lập một hồ sơ có thể kiểm chứng:

~~~yaml
storage:
  product: "Apache Cassandra"
  version: "5.0.x"
  edition: "Apache upstream"
  topology: "3 datacenter/replica theo cấu hình thực tế"
  indexType: "Storage-Attached Index (SAI)"
  featureSource: "Tài liệu sản phẩm đúng release và driver đang dùng"

workload:
  sourceTable: "orders_by_store"
  indexedColumn: "status"
  queryShapes:
    - "WHERE store_id = ? AND status = ?"
    - "WHERE status = ?"
  totalRows: 10000000
  resultSizes: [10, 50, 1000]
  selectivities: ["0.01%", "1%", "60%"]
  concurrentReadsPerSecond: 500
  concurrentWritesPerSecond: 300

requirements:
  correctness: "Kết quả đúng theo hợp đồng nhất quán đã chọn"
  latencyP95Ms: 150
  latencyP99Ms: 350
  freshness: "Cập nhật index được đọc theo bảo đảm đã xác minh"
  availability: "Hành vi khi index build/replica failover được định nghĩa"
  writeBudget: "Độ trễ và chi phí cập nhật tăng không vượt ngân sách"

acceptance:
  - "Cú pháp DDL và các predicate được phiên bản hỗ trợ"
  - "Index build hoàn tất, read path thực dùng chỉ mục"
  - "Đạt p95/p99 ở các mức selectivity và result size"
  - "Ghi/TTL/delete/compaction không làm sai kết quả"
  - "Lỗi node, timeout, retry và rebuild có phương án xử lý"
~~~

Thông tin trong YAML trên là **mẫu yêu cầu**, các ngưỡng và topology chỉ mang tính minh họa; dự án thật phải điền số liệu riêng, không lấy như cam kết chung về Cassandra 5.0.

### 9.1. Những gì phải khóa trong bản mô tả hệ

- **Phiên bản database chính xác:** major/minor/patch và bản dịch vụ/edition.
- **API và driver:** CQL native, Phoenix SQL, HBase client hoặc provider index riêng.
- **Loại index:** 2i, SAI, SASI, local/global, Phoenix index, bảng do ứng dụng duy trì.
- **Cú pháp truy vấn được hỗ trợ:** predicate, collection, ordering, paging, limit, kết hợp nhiều index.
- **Topology:** số node, replica, datacenter/Region, partitioner, data placement.
- **Bộ dữ liệu:** dung lượng, cardinality, skew, TTL, tombstone và tần suất đổi cột index.
- **Đường dữ liệu:** tính nhất quán đọc, mức xác nhận ghi, thời điểm index nhìn thấy thay đổi.
- **Vận hành:** index build/rebuild, snapshot/restore, nâng phiên bản, theo dõi trạng thái và giới hạn công cụ.

Một mẫu benchmark trên 100.000 bản ghi RAM nóng không đủ để đánh giá index trên 500 triệu bản ghi có TTL, compaction và cập nhật liên tục.

## 10. Đo hiệu năng với selectivity, fan-out và write amplification

Giả sử có 10 triệu đơn với ba phân bố:

~~~text
Truy vấn A: status = PENDING
  6.000.000 hàng khớp (60%)

Truy vấn B: customer_id = C123
  20 hàng khớp (0,0002%)

Truy vấn C: store_id = S17 AND status = FAILED
  15 hàng khớp trong một phạm vi đã xác định
~~~

Chúng là ba workload khác nhau. Chỉ số p95 của truy vấn B không thể đại diện cho A. Khi đo index, nên có các nhóm:

1. **Lookup chọn lọc cao**: rất ít hàng khớp, trả 10–50 record.
2. **Lookup trung bình**: vài nghìn hàng khớp, ứng dụng phân trang.
3. **Thuộc tính phổ biến**: phần lớn dữ liệu khớp, đo số lượng hàng đọc và phân trang lớn.
4. **Truy vấn có partition key**: phạm vi hẹp và vị trí dữ liệu xác định.
5. **Truy vấn không có partition key**: có thể fan-out, đo số node/replica được truy cập.
6. **Ghi đồng thời**: cột được index thường xuyên thay đổi, có TTL/delete và compaction.
7. **Dữ liệu tăng trưởng**: nhiều SSTable/region, số tombstone, tập dữ liệu vượt RAM.
8. **Lỗi và bảo trì**: index rebuild, node restart, thay schema và nâng phiên bản.

### Các chỉ số nên ghi

| Chỉ số | Ý nghĩa |
| --- | --- |
| **p50/p95/p99 query latency** | Độ trễ từng query shape, bao gồm trường hợp trả ít/nhiều kết quả. |
| **Throughput đạt được** | Số request xử lý đúng/s với offered load đã đạt mục tiêu. |
| **Timeout/error** | Lỗi khi fan-out, quá tải hoặc index chưa sẵn sàng. |
| **Bytes read / rows examined** | Lượng dữ liệu thực phải đọc để trả một kết quả. |
| **Disk và memory overhead** | Chi phí của index và metadata. |
| **Write latency & write amplification** | Tác động của index lên ghi/update/delete. |
| **Compaction/rebuild duration** | Khả năng vận hành lâu dài và tác động khi bảo trì. |
| **Node/shard imbalance** | Có một node nóng trong khi cụm còn rảnh không? |
| **Consistency/freshness** | Đường đọc phụ có thấy thay đổi theo hợp đồng hay không? |

Không nên chỉ đo **p95 đọc** mà bỏ **p99**, tỷ lệ timeout, chi phí ghi và kết quả đúng. Một index đọc nhanh nhưng khiến quá trình ghi bị backlog hoặc rebuild kéo dài có thể phá vỡ SLO của dịch vụ.

### Phân trang không làm query trở nên miễn phí

Nếu query khớp sáu triệu bản ghi nhưng API chỉ trả 50 bản ghi/trang, database vẫn phải xác định đường lấy trang tiếp theo và duy trì paging state theo cơ chế của sản phẩm. Truy vấn không có thứ tự ổn định có thể trả nhiều bản ghi “bất kỳ”; nếu nghiệp vụ yêu cầu **50 bản ghi mới nhất**, index trên status chưa chắc đủ để tạo thứ tự theo created_at. Thiết kế bảng với clustering key phù hợp hoặc một hệ tìm kiếm hỗ trợ sort hiệu quả hơn có thể cần thiết.

## 11. Index lifecycle: từ migration đến dữ liệu đã có

Thêm secondary index vào một bảng đang phục vụ production không chỉ là một lệnh DDL. Hệ thống phải xử lý dữ liệu lịch sử, tạo/bổ sung cấu trúc chỉ mục và duy trì những thay đổi phát sinh khi đang build. Quy trình và trạng thái phụ thuộc engine, nhưng các câu hỏi chung gồm:

~~~mermaid
flowchart TD
    A[Thiết kế predicate và đánh giá phiên bản] --> B[Tạo index / bảng tra cứu phụ]
    B --> C[Build hoặc backfill dữ liệu hiện có]
    C --> D[Theo dõi trạng thái sẵn sàng và đồng bộ]
    D --> E[Chạy query kiểm chứng]
    E --> F[Cho phép traffic theo rollout]
    F --> G[Theo dõi độ trễ, ghi, disk và dữ liệu]
    G --> H[Rebuild / upgrade / decommission khi cần]
~~~

Cần chuẩn bị:

- **Schema migration:** lệnh index có được hỗ trợ trong môi trường thực hay chỉ trong bản local test?
- **Backfill:** dữ liệu có trước khi tạo index được đưa vào index thế nào? Khi nào query mới được coi là đầy đủ?
- **Cập nhật trong lúc build:** hệ đảm bảo đồng bộ ra sao, hay cần replay sau build?
- **Index repair:** cách phát hiện/chữa chỉ mục thiếu hoặc stale sau sự cố.
- **Rollback:** có thể bỏ index mà không mất bảng gốc không, và query phụ thuộc index sẽ được chuyển thế nào?
- **Giới hạn vận hành:** memory/disk/network headroom trong lúc build; index build có ảnh hưởng p99 ghi/đọc không?
- **Thay đổi phiên bản:** có cần rebuild index hoặc chuyển cú pháp/provider sau nâng cấp?
- **Quan sát:** metric/tracing nào chứng minh query đang dùng index và kết quả có chính xác không?

**Sự tồn tại của metadata index chưa chứng minh index đã sẵn sàng hoặc optimizer thực sự sử dụng nó.** Cần đối chiếu trạng thái runtime, explain/tracing và bài kiểm tra kết quả theo tính năng được hỗ trợ.

## 12. Một ví dụ lựa chọn hoàn chỉnh

**Yêu cầu:** Nhân viên cửa hàng xem danh sách 50 đơn PENDING mới nhất của cửa hàng mình. Hệ có 8 triệu đơn, 20.000 cửa hàng, nhiều cửa hàng ít đơn nhưng một số cửa hàng lớn có hàng trăm nghìn đơn. Trạng thái đơn thay đổi vài lần từ PENDING đến COMPLETED/CANCELLED.

**Giải pháp ban đầu:** Bảng **orders_by_store** với partition theo store_id, clustering theo thời gian/order_id; muốn lọc status nên cân nhắc SAI hoặc bảng **orders_by_store_status**.

### Câu hỏi phân tích

1. Truy vấn có **store_id**. Một số store rất lớn: partition có vượt giới hạn vận hành của engine không?
2. Phần lớn đơn đã COMPLETED; **PENDING** chiếm bao nhiêu phần trong từng cửa hàng và toàn cụm?
3. Từ “mới nhất” có yêu cầu thứ tự chính xác theo thời điểm tạo không? **Index status không tự bảo đảm ORDER BY created_at**.
4. Có bao nhiêu request/s vào cửa hàng lớn nhất? Một partition **(store_id, status)** có trở thành hot partition không?
5. Trạng thái đơn có cập nhật nhanh không? Bảng phụ sẽ phải chuyển entry giữa hai partition khi status đổi.
6. Có cần màn hình không bao giờ thấy đơn đã chuyển COMPLETED nữa không, hay chấp nhận độ trễ hội tụ dưới vài giây?
7. Đang chạy Apache Cassandra 5.0, Cassandra phiên bản cũ, ScyllaDB hay dịch vụ managed? Index nào thực sự có?
8. Cần quy trình backfill và đối soát lịch sử khi tạo bảng/index mới không?

### Hai thiết kế để thử

**Thiết kế 1: SAI trên status của bảng gốc (nếu dùng Cassandra 5.0 phù hợp).** Dùng truy vấn có partition key và predicate, đo xem engine kết hợp các điều kiện ra sao; kiểm tra yêu cầu sắp xếp và phân trang theo thời gian. Phù hợp khi lượng kết quả trả ít và hiệu năng/consistency được chứng minh, nhưng không được mặc định mọi kiểu sắp xếp đều hỗ trợ tốt.

**Thiết kế 2: Bảng orders_by_store_status_by_day.** Partition theo cửa hàng, trạng thái và ngày/tháng phù hợp; clustering theo thời gian giảm dần. Mỗi lần đổi status, pipeline cập nhật entry tương ứng và đảm bảo cuối cùng không còn entry cũ. API truy vấn bucket gần nhất trước, lấy đủ 50 đơn và tiếp tục bucket trước đó khi cần. Phù hợp khi yêu cầu thứ tự và pattern rất ổn định, đổi lại phải duy trì dữ liệu denormalized có idempotency/đối soát.

### Nghiệm thu minh họa

| Điều kiện | Mục tiêu giả định | Cách kiểm chứng |
| --- | --- | --- |
| Trả 50 đơn PENDING mới nhất | Đúng tập kết quả và thứ tự đã định nghĩa | So với dữ liệu chuẩn, kể cả khi trạng thái vừa đổi. |
| p95 độ trễ | ≤ 150 ms ở tải mục tiêu | Benchmark cùng dataset, đo end-to-end. |
| p99 và timeout | p99 ≤ 350 ms; timeout < 0,1% | Histogram, phân loại lỗi và tải đã phát thực tế. |
| Ghi cập nhật trạng thái | Không vượt ngân sách latency ghi | Chạy trạng thái thay đổi cùng tải đọc. |
| Dung lượng | Trong giới hạn disk/replica dự kiến | Đo index/table size sau nạp đầy đủ dữ liệu. |
| Hot partition | Cửa hàng lớn vẫn đạt yêu cầu | Tạo workload skew, đo từng node/shard. |
| Khôi phục | Có phương án backfill/rebuild đúng | Thử xây lại và đối soát số record. |

Các số trên chỉ là mục tiêu **giả lập** để minh họa cách quyết định. Sau khi cùng cấu hình, dataset và workload được dùng để thử cả hai phương án, nhóm mới có căn cứ chọn kiến trúc.

## 13. Những ngộ nhận cần tránh

**“Cứ thêm secondary index là truy vấn nào cũng nhanh.”** Chỉ mục thường hữu ích với **một số predicate và phân bố dữ liệu cụ thể**. Truy vấn quá nhiều kết quả, sort không được hỗ trợ hoặc fan-out rộng vẫn có thể rất chậm.

**“Mọi Cassandra-compatible engine có cùng index.”** Cú pháp gần nhau không có nghĩa triển khai và phiên bản hỗ trợ giống nhau. Cần đọc đúng tài liệu Apache Cassandra, ScyllaDB hoặc dịch vụ managed.

**“SAI, SASI và 2i chỉ là các tên khác nhau.”** Chúng có cơ chế, giới hạn và lịch sử khác nhau; benchmark không chuyển ngang tự động.

**“ALLOW FILTERING là một kiểu tạo index.”** Đây là điều kiện cho phép thực hiện một số truy vấn lọc; không phải chỉ mục và không bảo đảm tránh quét.

**“Có secondary index trên email tức là email unique.”** Index tra cứu không tự tạo ràng buộc uniqueness. Chống trùng phải thiết kế ràng buộc/conditional write riêng.

**“Index phụ có tính nhất quán giống bảng gốc trong mọi hệ.”** Index gắn storage, materialized view, bảng phụ do ứng dụng duy trì và search index độc lập có thể có cơ chế cập nhật, lỗi và thời điểm nhìn thấy dữ liệu khác nhau.

**“Chỉ cần test vài nghìn bản ghi rồi thêm index vào production.”** Phải đo dữ liệu lớn, phân bố hot key, TTL/tombstone, ghi đồng thời, fan-out và chi phí build/rebuild.

**“Index giải quyết yêu cầu đọc không xác định trước.”** Nếu sản phẩm thay đổi filter, full-text, sort và faceting liên tục, cần xem giải pháp tìm kiếm chuyên dụng hoặc thiết kế phân tích phù hợp.

## 14. Quy trình ra quyết định thực tế

~~~mermaid
flowchart TD
    A[Liệt kê query shape thực tế] --> B{Có đầy đủ partition key và clustering range phù hợp?}
    B -->|Có| C[Dùng đường truy cập chính, đo workload]
    B -->|Không| D[Chọn sản phẩm, phiên bản và loại index có thật]
    D --> E{Secondary index hỗ trợ predicate, sort, kết quả cần trả?}
    E -->|Có| F[Benchmark index trên dữ liệu và tải đại diện]
    E -->|Không| G[Bảng theo truy vấn hoặc search service]
    F --> H{Đạt latency, ghi, consistency, chi phí và recovery?}
    H -->|Có| I[Chấp nhận index và kế hoạch lifecycle]
    H -->|Không| G
    G --> J[Định nghĩa đồng bộ, backfill và đối soát]
    C --> K[Viết hợp đồng truy vấn và test]
    I --> K
    J --> K
~~~

Thứ tự áp dụng:

1. **Ghi cụ thể từng truy vấn**: điều kiện lọc, khóa biết trước, sort, limit, lượng kết quả, QPS và độ tươi yêu cầu.
2. **Kiểm tra đường theo primary key**: partition key/clustering key có phục vụ truy vấn mà không cần index mới không?
3. **Xác định sản phẩm và phiên bản**: loại index nào được hỗ trợ, đang ổn định hay có giới hạn, cú pháp và cơ chế phân phối nào.
4. **So sánh phương án thực**: index phụ, bảng denormalized/materialized view, index table ứng dụng quản lý, search/analytics.
5. **Benchmark trên workload đại diện**: cardinality/selectivity, hot partitions, số kết quả, ghi đồng thời, TTL, compaction và dữ liệu lớn.
6. **Định nghĩa consistency và recovery**: khi thay đổi dữ liệu thì đường tra cứu phụ thấy bản mới khi nào, khi mất node có thể phục hồi/rebuild ra sao.
7. **Tài liệu hóa quyết định**: chỉ mục nào tồn tại, truy vấn nào phụ thuộc nó, khi nâng phiên bản hoặc đổi sản phẩm phải kiểm chứng lại những gì.

## Kết luận

**Chỉ mục phụ là một lựa chọn về đường truy cập, không phải tính năng đồng nhất của mọi hệ cột rộng.** Việc chọn index phải dựa vào **access pattern**, phạm vi partition, độ chọn lọc, phân bố dữ liệu, chi phí ghi và các ràng buộc đúng với **phiên bản và sản phẩm đang triển khai**. Cassandra 2i/SASI/SAI, cơ chế index của ScyllaDB, Phoenix trên HBase hay bảng chỉ mục do ứng dụng duy trì không thể coi như một giải pháp giống nhau.

Khi truy vấn ổn định và hiệu năng cần dự báo cao, **bảng được thiết kế theo truy vấn** thường là một phương án quan trọng để so sánh. Khi cần lọc linh hoạt, index phù hợp hoặc tầng tìm kiếm riêng có thể có lợi. Dù chọn cách nào, hãy nghiệm thu cả **độ trễ đọc, tác động ghi, tính đúng của kết quả, khả năng phục hồi và chi phí vận hành** trước khi đưa chỉ mục phụ thành một phần bắt buộc của kiến trúc.
