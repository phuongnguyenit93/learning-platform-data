# SASI và phạm vi hỗ trợ theo phiên bản sử dụng

> **Chương:** Chỉ mục và mở rộng  
> **Công nghệ:** Apache Cassandra, CQL, Spring Data Cassandra, `CassandraRepository`, `CassandraTemplate` và Java driver.  
> **Trọng tâm:** hiểu **SASI** là gì, những khả năng truy vấn mà nó từng cung cấp, **giới hạn hỗ trợ và cờ cấu hình theo phiên bản Cassandra**, cách phân biệt SASI với 2i/SAI và cách chọn phương án thay thế an toàn cho hệ thống thực tế.

## 1. Vấn đề thực tế: cần tìm cảnh báo theo nội dung

Một hệ thống IoT có bảng sự kiện được phân vùng theo tenant, thiết bị và bucket ngày UTC. API timeline hiện tại hoạt động tốt vì người dùng biết đầy đủ partition key:

~~~sql
SELECT event_time, event_id, event_type, message
FROM telemetry.device_events
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Product muốn có thêm ô tìm kiếm:

- Tìm những event có `message` bắt đầu bằng `"Battery"`.
- Tìm những event có `message` chứa chuỗi `"voltage"`.
- Lọc event của mọi thiết bị có `event_type = 'BATTERY_LOW'`.
- Xem 50 kết quả mới nhất trong một site, có phân trang.

Khi đọc tài liệu Cassandra cũ, developer có thể gặp **SASI** với khả năng tìm tiền tố/chuỗi con bằng `LIKE` và cho rằng chỉ cần `CREATE INDEX` là giải quyết tất cả.

Đây là điểm phải kiểm tra cẩn thận: **SASI là một triển khai chỉ mục cũ, experimental, không được khuyến nghị cho production và có trạng thái khác nhau giữa các bản Cassandra**. Các hệ thống Cassandra mới hơn có thể hỗ trợ **SAI**, nhưng SAI không được phép coi là bản thay thế từng tính năng, nhất là truy vấn `LIKE '%text%'`.

Mục tiêu bài học không phải khuyến khích mở SASI trên cluster thật, mà giúp bạn **đọc hiểu legacy schema, đánh giá sự hỗ trợ và lựa chọn chiến lược truy vấn đúng**.

## 2. Kết quả học tập

Sau bài này, bạn cần trả lời được:

1. SASI viết tắt của gì và nó lưu chỉ mục liên quan đến SSTable ra sao?
2. SASI khác secondary index cũ (2i) và Storage-Attached Indexing (SAI) ở đâu?
3. Cassandra 3.11, 4.0, 4.1 và 5.0 khác nhau thế nào về **tên cờ cấu hình và giá trị mặc định**?
4. Vì sao một tài liệu có ví dụ `CREATE CUSTOM INDEX` vẫn không chứng minh tính năng được bật hoặc được hỗ trợ trên cluster của bạn?
5. Cú pháp `PREFIX`, `CONTAINS`, `SPARSE` và những truy vấn `LIKE` minh họa cho SASI có ý nghĩa gì?
6. Khi nào chỉ mục không giải quyết được `ORDER BY` toàn cục, JOIN, phân trang toàn site hay tổng hợp rộng?
7. Làm sao dùng `@Query`/`CqlTemplate` để kiểm tra CQL trên bản server tương ứng mà không vô tình mở một đường đọc nguy hiểm?
8. Làm sao kiểm tra index đang tồn tại, xây lại chỉ mục, thử nghiệm đúng/sai và di chuyển sang read model/SAI/search engine trước khi nâng cấp?

**Nguyên tắc:** quyết định index phải dựa trên **phiên bản server, bản phân phối, tính năng bật thật, access pattern, tải và kiểm chứng dữ liệu**, không chỉ dựa trên tên API Java.

## 3. SASI là gì?

SASI là **SSTable-Attached Secondary Index** (còn được gọi là SASIIndex), một triển khai của giao diện `Index` trong Cassandra. SASI xây dựng các cấu trúc chỉ mục gắn với SSTable, thay vì dựa hoàn toàn vào bảng ẩn của cơ chế secondary index truyền thống.

Ý tưởng kiến trúc:

~~~text
Cassandra table
  ├── Memtable
  │    └── chỉ mục in-memory tương ứng
  ├── SSTable A
  │    └── SASI index file của cột được index
  ├── SSTable B
  │    └── SASI index file của cột được index
  └── SSTable C
       └── SASI index file của cột được index
~~~

Khi flush/compaction tạo SSTable, việc xây hoặc duy trì cấu trúc chỉ mục có thể phát sinh công việc CPU, bộ nhớ và I/O. Khi đọc, server sử dụng các index entries tìm ứng viên rồi truy cập dữ liệu tương ứng theo cơ chế của phiên bản đang chạy.

SASI từng được tạo để cải thiện một số trường hợp **lọc dữ liệu và tìm kiếm chuỗi**, đặc biệt các truy vấn `LIKE` theo tiền tố hoặc chuỗi con. Nhưng nó **không phải full-text search engine hoàn chỉnh**, không phải relational query planner và không tạo một bảng được sắp xếp toàn cục theo bất kỳ trường nào.

Đừng nhầm tên viết tắt:

- **SASI:** *SSTable-Attached Secondary Index* — chỉ mục legacy, experimental.
- **SAI:** *Storage-Attached Indexing* — cơ chế chỉ mục mới hơn, được tích hợp vào Apache Cassandra 5.0.
- **2i:** secondary indexing truyền thống của Cassandra, có hành vi/chi phí riêng.

SASI và SAI đều liên quan đến lưu trữ, nhưng **không tương đương về API, operator, độ tin cậy, hỗ trợ hay chiến lược nâng cấp**.

## 4. Vì sao không nên xem SASI là tính năng production mặc định?

Tài liệu cấu hình Apache Cassandra xếp SASI vào nhóm **experimental features**, đồng thời nêu rõ không khuyến nghị dùng trong production. Tài liệu hệ sinh thái về Cassandra 5.0 cũng đánh dấu SASI **deprecated**, và nêu những rủi ro chất lượng kết quả của triển khai legacy.

Hệ quả kỹ thuật:

- Một câu `CREATE CUSTOM INDEX` từng chạy được ở cluster cũ không chứng minh nó an toàn trên cluster mới.
- Chỉ mục có thể bị **vô hiệu hóa mặc định** và cần quyền/cấu hình server mới cho phép tạo.
- Nâng cấp phiên bản có thể làm thay đổi tên cờ cấu hình hoặc chiến lược chỉ mục được khuyến nghị.
- Chi phí xây index/compaction có thể tăng theo dữ liệu và tần suất write.
- Một chỉ mục có thể tồn tại trong schema nhưng chưa ở trạng thái sẵn sàng phục vụ truy vấn trên mọi node.
- Với cơ chế experimental/deprecated, **không nên xây dependency nghiệp vụ mới** nếu có phương án được hỗ trợ tốt hơn.

Việc SASI xuất hiện trong phần tài liệu CQL của một phiên bản **không đồng nghĩa** đội vận hành nên bật nó lên. Cần phân biệt **có mã nguồn/tài liệu**, **được bật**, **được hỗ trợ vận hành** và **được khuyến nghị**.

## 5. Ma trận phiên bản: Cassandra 3.11, 4.0, 4.1 và 5.0

Đây là bảng đối chiếu từ các trang cấu hình theo phiên bản của Apache Cassandra. Giá trị là **mặc định được tài liệu cấu hình nêu**, không phải trạng thái cluster cụ thể của bạn.

| Apache Cassandra | Cờ liên quan SASI trong `cassandra.yaml` | Giá trị mặc định theo tài liệu | Đánh giá |
| --- | --- | --- | --- |
| **3.11** | `enable_sasi_indexes` | `true` | Experimental, không khuyến nghị production |
| **4.0** | `enable_sasi_indexes` | `false` | Experimental, vô hiệu hóa mặc định |
| **4.1** | `sasi_indexes_enabled` | `false` | Experimental, vô hiệu hóa mặc định |
| **5.0** | `sasi_indexes_enabled` | `false` | Experimental/deprecated, không dùng cho phát triển mới |

**Điểm dễ gây sự cố:** tên `enable_sasi_indexes` ở 3.11/4.0 **khác** `sasi_indexes_enabled` ở 4.1/5.0. Đừng copy một đoạn `cassandra.yaml` từ blog cũ sang version mới mà không đối chiếu schema cấu hình của đúng server.

Tài liệu về hướng phát triển SAI (CEP-7) đề xuất **deprecate SASI ở 5.0 và loại bỏ ở thế hệ sau**. Đây là kế hoạch/định hướng kiến trúc; với phiên bản ngoài bảng trên, phải kiểm tra release notes và tính năng thực tế, **không khẳng định đã bị xóa chỉ dựa trên lộ trình**.

Tài liệu Apache Cassandra 5.0 có trang SASI mô tả cú pháp và ví dụ, đồng thời cấu hình 5.0 vẫn xếp SASI là experimental và mặc định tắt. Hai thông tin này **không mâu thuẫn**: tài liệu kỹ thuật legacy có thể còn tồn tại khi tính năng không còn là lựa chọn được khuyến nghị.

### Tham chiếu cấu hình theo phiên bản

- Cassandra 3.11: [`enable_sasi_indexes`](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html).
- Cassandra 4.0: [`enable_sasi_indexes`](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html).
- Cassandra 4.1: [`sasi_indexes_enabled`](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html).
- Cassandra 5.0: [`sasi_indexes_enabled`](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html).

**Lưu ý về tên “stable”:** các liên kết `stable` có thể trỏ sang bản khác trong tương lai. Khi kiểm tra dự án, ưu tiên URL tài liệu gắn số version chính xác nếu có. Không dựa vào tên nhánh tài liệu để suy phiên bản binary hiện đang chạy.

## 6. Phân biệt phiên bản server, driver và Spring Boot

Một ứng dụng có thể sử dụng Spring Boot 3.x và Java driver 4.x để kết nối đến một server Cassandra 4.1 hoặc 5.0. Ba thứ đó có **vòng đời phiên bản khác nhau**:

| Thành phần | Quyết định điều gì? | Có tự bật SASI không? |
| --- | --- | --- |
| **Apache Cassandra server** | Engine, CQL, index implementation và feature flags | **Có quyền quyết định tính năng thực tế** |
| **Bản phân phối/managed provider** | Loại index được nhà cung cấp cho phép và hỗ trợ | Có thể hạn chế, không suy từ Apache version |
| **Java driver** | Kết nối, bind parameter, thực thi statement, metadata | Không |
| **Spring Data Cassandra** | Entity mapping, repository, `@Query`, template | Không |
| **Spring Boot** | Dependency management, auto-configuration của Cassandra client | Không |

Vì vậy, việc nâng dependency `spring-boot-starter-data-cassandra` **không** làm Cassandra server có thêm SASI hoặc SAI. Ngược lại, nếu server bị tắt SASI, không có annotation Java nào tự mở cờ cho node.

Đối với **Amazon Keyspaces, Astra DB, ScyllaDB, hoặc các bản Cassandra được nhà cung cấp tùy biến**, không suy ra khả năng SASI từ “compatible with CQL” hoặc chuỗi version giống Cassandra. Cần kiểm tra tài liệu của đúng nhà cung cấp, quyền DDL, feature matrix và thử truy vấn trong môi trường họ cung cấp.

## 7. Kiểm tra server trước khi làm bất kỳ thử nghiệm SASI nào

Trên môi trường có quyền truy cập CQL, có thể bắt đầu bằng:

~~~sql
SELECT release_version, cluster_name, data_center
FROM system.local;
~~~

Các trường trong `system.local` giúp xác định một số đặc điểm node mà session kết nối tới. Với cluster nhiều node hoặc managed service, phải đối chiếu thêm **version đang chạy trên từng node** và tài liệu hạ tầng; không suy rằng một row `system.local` chứng minh cả cluster đồng nhất.

Có thể dùng công cụ quản trị khi được phép:

~~~bash
nodetool version
nodetool status
~~~

`cqlsh` có thể giúp xem schema:

~~~text
DESCRIBE TABLE telemetry.device_events;
DESCRIBE INDEX telemetry.device_message_sasi_idx;
~~~

`DESCRIBE` là **lệnh riêng của cqlsh**, không phải câu CQL thông thường gửi qua `CqlSession.execute(...)`.

Checklist trước khi tạo index:

1. Xác nhận server là Apache Cassandra hay bản phân phối khác.
2. Ghi rõ major/minor/patch version **trên các node liên quan**.
3. Đối chiếu tên và giá trị cờ SASI theo `cassandra.yaml` của đúng version.
4. Kiểm tra có đủ quyền `CREATE INDEX` và thay đổi cấu hình không.
5. Đọc trạng thái experimental/deprecated và chính sách vận hành của tổ chức.
6. Thử trên môi trường cô lập có dữ liệu tổng hợp; **không bật SASI trên production chỉ để chạy ví dụ**.
7. Quyết định từ đầu có chuyển sang bảng đọc/SAI/search engine không.

Ở managed service, người dùng có thể không đọc được `cassandra.yaml`. Không cố “đoán” cờ bằng driver; cần bằng chứng từ tài liệu và cấu hình do provider công bố.

## 8. Cấu hình SASI: chỉ minh họa cho sandbox legacy

Để nghiên cứu một ứng dụng cũ, người học có thể gặp hai dạng:

~~~yaml
# Chỉ dành cho môi trường thử nghiệm Cassandra 3.11/4.0,
# tùy đúng version và điều kiện hạ tầng:
enable_sasi_indexes: true
~~~

~~~yaml
# Chỉ dành cho môi trường thử nghiệm Cassandra 4.1/5.0,
# khi hạ tầng cho phép nghiên cứu SASI legacy:
sasi_indexes_enabled: true
~~~

**Không coi những đoạn cấu hình trên là hướng dẫn bật SASI trong production.** Nếu có yêu cầu hỗ trợ legacy, đội vận hành phải đánh giá rủi ro, backup, tính tương thích khi nâng cấp, quy trình tắt/loại bỏ và ảnh hưởng đến các node.

SASI thường cần tính năng được cho phép ở các node liên quan trước khi tạo index. Với cluster nhiều node, tình trạng cấu hình không đồng nhất có thể khiến migration thất bại hoặc truy vấn bất thường. Mọi thay đổi cấu hình server phải theo quy trình quản trị, không phải thay đổi `application.yml` của Spring Boot.

Không có thuộc tính `spring.cassandra.sasi.enabled` mặc định nào giúp bật cơ chế chỉ mục SASI trên Cassandra server. Spring Boot chỉ cấu hình **client** kết nối.

## 9. Ví dụ schema phục vụ việc đọc hiểu legacy SASI

Tạo bảng sự kiện có khóa theo tenant, thiết bị và ngày để minh họa khác biệt giữa query-driven read và tìm trên regular column:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.device_events (
    tenant_id  uuid,
    device_id  uuid,
    event_day  date,
    event_time timestamp,
    event_id   uuid,
    event_type text,
    message    text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id ASC
);
~~~

Đọc một partition bình thường **không cần SASI**:

~~~sql
SELECT event_time, event_id, event_type, message
FROM telemetry.device_events
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Trong bảng này:

- `tenant_id, device_id, event_day` là **composite partition key**.
- `event_time` và `event_id` là clustering columns.
- `event_type` và `message` chỉ là **regular columns**.
- Truy vấn `WHERE message LIKE ...` hay `WHERE event_type = ...` **không phải** access pattern tối ưu nhờ primary key.

Các ví dụ SASI tiếp theo chỉ để hiểu và kiểm thử hệ thống legacy, không phải giải pháp production khuyến nghị.

## 10. Cú pháp CREATE CUSTOM INDEX của SASI

Với Cassandra legacy cho phép SASI, dạng khai báo tham khảo:

~~~sql
-- Chỉ chạy trên sandbox đã xác minh hỗ trợ SASI.
CREATE CUSTOM INDEX IF NOT EXISTS device_message_sasi_idx
ON telemetry.device_events (message)
USING 'org.apache.cassandra.index.sasi.SASIIndex'
WITH OPTIONS = {'mode': 'CONTAINS'};
~~~

Index class `org.apache.cassandra.index.sasi.SASIIndex` là dấu hiệu nhận diện SASI. Nó **khác** cách tạo SAI của Cassandra 5.0, vốn thường dùng `USING 'sai'`.

Có thể minh họa chỉ mục tiền tố trên cột khác:

~~~sql
-- Ví dụ legacy, không tạo trên production.
CREATE CUSTOM INDEX IF NOT EXISTS device_type_sasi_idx
ON telemetry.device_events (event_type)
USING 'org.apache.cassandra.index.sasi.SASIIndex'
WITH OPTIONS = {'mode': 'PREFIX'};
~~~

Không cần index cho những query vốn đã dùng đầy đủ partition key và clustering columns. Thêm index không tự làm query theo khóa nhanh hơn; nó tạo **chi phí bổ sung cho write, flush, compaction, streaming và storage**.

Sau khi tạo index, Cassandra có thể cần thời gian xây chỉ mục trên dữ liệu đã có. Chỉ xem statement DDL trả thành công là chưa đủ để kết luận index đã sẵn sàng hoặc kết quả tìm kiếm đầy đủ trên mọi replica.

**Nhắc lại:** nếu SASI bị tắt, DDL này có thể bị từ chối. Không cố vượt feature flag trên hạ tầng thật.

## 11. Các mode của SASI: PREFIX, CONTAINS và SPARSE

Tài liệu SASI mô tả ba mode chính:

| Mode | Mục đích ban đầu | Ví dụ cần kiểm chứng |
| --- | --- | --- |
| `PREFIX` | Tối ưu tìm theo tiền tố trên các term được lập chỉ mục | `LIKE 'Battery%'` |
| `CONTAINS` | Cho phép tìm chuỗi con/hậu tố với dữ liệu dạng text | `LIKE '%voltage%'` |
| `SPARSE` | Nhắm đến một số trường hợp range query với dữ liệu số/thời gian dày đặc | Range trên timestamp/numeric với workload phù hợp |

Trong tài liệu legacy, `PREFIX` là mode mặc định khi không đặt tùy chọn khác. `CONTAINS` cần bổ sung các term phục vụ tìm suffix/substring, vì vậy có thể làm tăng **kích thước index, công việc ghi và compaction** so với tiền tố đơn giản.

`SPARSE` không phải cấu hình “cứ bật là index nhỏ/rẻ”. Nó hướng đến một nhóm dữ liệu/range query đặc biệt và phải thử nghiệm với phân bố giá trị, mật độ, query selectivity và server version thật.

Ngoài mode còn có tùy chọn **analyzer** và normalization. Cùng một `LIKE` nhưng kết quả có thể khác tùy việc index giữ nguyên chữ hoa/thường, phân tách token hay stemming. Đừng trộn “chỉ mục text” với “đảm bảo tìm full-text theo mọi ngôn ngữ”.

## 12. LIKE trên SASI: prefix và contains

Nếu sandbox legacy có SASI `CONTAINS` cho `message`, các câu CQL minh họa có thể là:

~~~sql
-- Tìm message bắt đầu bằng từ Battery:
SELECT tenant_id, device_id, event_day, event_time, event_id
FROM telemetry.device_events
WHERE message LIKE 'Battery%';
~~~

~~~sql
-- Tìm message có chuỗi voltage ở bất kỳ vị trí thích hợp:
SELECT tenant_id, device_id, event_day, event_time, event_id
FROM telemetry.device_events
WHERE message LIKE '%voltage%';
~~~

**Chỉ chạy được khi phiên bản server, index mode, analyzer và quyền truy vấn thực sự hỗ trợ pattern đó.** Nếu không có SASI phù hợp, các câu này có thể bị từ chối. Một số dạng `LIKE` có giới hạn ngôn ngữ/cú pháp riêng; không suy ra hỗ trợ đầy đủ SQL LIKE hoặc Unicode full-text search.

Ví dụ data thử:

~~~sql
INSERT INTO telemetry.device_events (
    tenant_id, device_id, event_day, event_time,
    event_id, event_type, message
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    '2026-11-25',
    '2026-11-25T08:30:00Z',
    33333333-3333-4333-8333-333333333333,
    'BATTERY_LOW',
    'Battery voltage below threshold'
);
~~~

Đối chiếu kết quả `LIKE 'Battery%'` và `LIKE '%voltage%'` với row đã seed. Tạo thêm nhiều chuỗi gần giống, chữ hoa/chữ thường, ký tự tiếng Việt, ký hiệu và dấu khoảng trắng để kiểm thử normalization và tokenizer.

### Không tự suy ra hỗ trợ LIKE của SAI

SAI trên Apache Cassandra 5.0 được tài liệu riêng mô tả là index/filtering engine với các toán tử hỗ trợ theo kiểu dữ liệu. Các trang reference/FAQ nêu `LIKE` **không phải toán tử SAI được hỗ trợ theo cách SASI từng làm**. Vì vậy thay `USING 'org.apache.cassandra.index.sasi.SASIIndex'` bằng `USING 'sai'` có thể khiến câu `LIKE '%voltage%'` không còn hợp lệ.

Nếu cần **substring, stemming, ranking hoặc full-text**, nên đánh giá search engine phù hợp thay vì hứa SAI thay SASI 1:1. Hãy kiểm chứng với server thực tế và tài liệu operator của đúng phiên bản, vì khả năng và tài liệu có thể thay đổi.

## 13. Analyzer và ý nghĩa của phép tìm kiếm

SASI có các analyzer/tùy chọn xử lý text trong hệ legacy. Ví dụ mẫu thể hiện ý tưởng **không phân tách token và không phân biệt hoa/thường**:

~~~sql
-- Ví dụ sandbox SASI; kiểm tra options/version trước khi dùng.
CREATE CUSTOM INDEX IF NOT EXISTS device_type_ci_sasi_idx
ON telemetry.device_events (event_type)
USING 'org.apache.cassandra.index.sasi.SASIIndex'
WITH OPTIONS = {
    'mode': 'PREFIX',
    'analyzer_class':
        'org.apache.cassandra.index.sasi.analyzer.NonTokenizingAnalyzer',
    'case_sensitive': 'false'
};
~~~

Đây là ví dụ về cấu hình **legacy**, không phải API độc lập có thể chạy trên mọi Cassandra-compatible service. Đặc biệt, trước khi copy từ tài liệu:

- Xác định tên class analyzer còn có trong version server.
- Kiểm tra `analyzed`, `case_sensitive`, normalization và mode có tương thích không.
- Kiểm thử dữ liệu có chữ hoa/thường, ký tự có dấu và ký tự đa byte.
- Phân biệt **prefix search trên string nguyên khối** với **token search**; hai thứ khác về kết quả.
- Không coi stemming/normalization trong ví dụ tiếng Anh là phù hợp mặc định với nội dung tiếng Việt.
- Không dựa vào “LIKE khớp trên 3 row mẫu” để kết luận search phù hợp production.

Nếu sản phẩm cần full-text search nghiêm túc, phải định nghĩa rõ từ khóa, tokenizer, ngôn ngữ, accent handling, substring/prefix/ranking và độ mới index, rồi chọn công nghệ đáp ứng yêu cầu.

## 14. Truy vấn nhiều điều kiện và ALLOW FILTERING

Trong tài liệu SASI legacy có các câu gồm nhiều predicate trên những cột được lập chỉ mục, ví dụ:

~~~sql
-- Chỉ dành cho sandbox legacy có index phù hợp.
SELECT *
FROM telemetry.device_events
WHERE message LIKE 'Battery%'
  AND event_type = 'BATTERY_LOW'
ALLOW FILTERING;
~~~

Một số phiên bản CQL/SASI yêu cầu `ALLOW FILTERING` về mặt cú pháp để cho phép kết hợp điều kiện, ngay cả khi các predicate có thể được SASI xử lý qua index. Điều đó **không** có nghĩa query luôn rẻ hoặc luôn đúng ở mọi phiên bản.

Phân biệt hai điều quan trọng:

1. `ALLOW FILTERING` có thể cho phép một truy vấn mà Cassandra vốn từ chối vì không định tuyến theo primary key.
2. Việc query có index phù hợp, số row/partition xét, cách tổ hợp predicate và chi phí thực tế **phải được đo**.

Không lấy một câu ví dụ trong tài liệu SASI để suy rằng mọi tổ hợp `AND`, `OR`, prefix/contains và range đều được tối ưu trên mọi cluster. Có trường hợp một cột không có index hoặc index không tương thích với operator khiến Cassandra phải lọc dữ liệu đáng kể.

**LIMIT không chữa fan-out:** `LIMIT 50` chỉ giới hạn row trả về; không bảo đảm index lookup chỉ xử lý 50 candidate rows, cũng không tạo thứ tự thời gian toàn cục.

## 15. SASI không cung cấp JOIN, ORDER BY toàn cục hay OLAP

SASI chỉ là một **cơ chế chỉ mục**. Nó không thay đổi các ràng buộc cơ bản của Cassandra:

| Mong muốn | SASI có tự cung cấp không? | Cách tiếp cận |
| --- | --- | --- |
| JOIN giữa event, device và site | **Không** | Denormalization hoặc bounded lookup |
| 50 event mới nhất toàn site, sắp global theo timestamp | **Không bảo đảm** | Bảng cảnh báo theo site/time bucket |
| Tìm theo `device_id + day` đã biết | Không cần SASI | Primary key + clustering |
| COUNT/GROUP BY toàn cluster theo loại event | Không biến thành aggregate rẻ | Rollup, stream/batch hoặc OLAP |
| Substring search theo `LIKE` | SASI legacy có ví dụ hỗ trợ trong điều kiện cụ thể | Xác minh mode/version; cân nhắc search engine |
| Phân trang bằng offset SQL | Không | Driver paging state; query phù hợp partition |
| Điều kiện ad hoc trên mọi regular column | Không bảo đảm | SAI/index được hỗ trợ hoặc read models |

Ví dụ sai kỳ vọng:

~~~sql
-- Không có ORDER BY toàn cục nhờ SASI:
SELECT *
FROM telemetry.device_events
WHERE message LIKE '%voltage%'
ORDER BY event_time DESC
LIMIT 50;
~~~

Cassandra không biến những row nằm ở hàng nghìn partition khác nhau thành một timeline toàn cục chỉ nhờ index. Nếu product yêu cầu sort/top-N có SLO nghiêm ngặt, thiết kế **một bảng đọc theo access pattern** hoặc hệ search/analytics có khả năng sort phù hợp.

## 16. So sánh SASI, 2i, SAI và bảng theo truy vấn

| Tiêu chí | SASI | 2i truyền thống | SAI trên Cassandra 5.0 | Bảng read model |
| --- | --- | --- | --- | --- |
| Trạng thái | Experimental/deprecated, tránh phát triển mới | Legacy secondary index, có giới hạn | Index được khuyến nghị cho nhiều use case Cassandra 5.0 | Cách mô hình hóa chủ động theo truy vấn |
| Tổ chức dữ liệu | Gắn index theo SSTable | Local index theo cơ chế 2i | Storage-attached index mới hơn | Rows/partitions riêng theo query |
| Truy vấn text substring LIKE | Có ở một số mode SASI legacy | Không nên suy là hỗ trợ | Không thay thế `LIKE` của SASI 1:1 | Cần tự thiết kế; full-text thường dùng search |
| Điều kiện equality/range | Có điều kiện theo type/mode | Có giới hạn/index design riêng | Có operator được tài liệu hỗ trợ | Tốt nếu keys/clustering được thiết kế đúng |
| Global ORDER BY/JOIN | Không | Không | Không | Không tự JOIN; query mới có thể định tuyến hiệu quả |
| Chi phí write/storage | Thêm index và bảo trì | Thêm index | Thêm index, có tối ưu riêng | Thêm dữ liệu/đồng bộ giữa bảng |
| Tính di động version | Rủi ro cao | Tùy server/provider | Apache Cassandra 5.0 theo tài liệu | CQL tables phù hợp với nhiều phiên bản hơn |
| Chi phí thay đổi | Cấu hình, rebuild/migration và kiểm thử nghiêm ngặt | Quản lý index | Tạo SAI/đo tải và chuyển query | Backfill, dual-write, reconciliation |

**Không có một lựa chọn duy nhất cho mọi workload.** Bảng đọc theo truy vấn thường phù hợp khi API biết rõ partition key và yêu cầu sort/paging ổn định. SAI có thể giúp một số bộ lọc nhiều chiều trong Cassandra 5.0; search engine phù hợp hơn với full-text/substring/ranking phức tạp.

## 17. SAI từ Cassandra 5.0: đừng chuyển đổi máy móc

SAI (Storage-Attached Indexing) xuất hiện trong Apache Cassandra **5.0** và có tài liệu chính thức riêng về index creation, query operators, performance và vận hành.

Ví dụ **SAI**, không phải SASI:

~~~sql
-- Chỉ tạo khi server thực sự hỗ trợ SAI.
CREATE INDEX IF NOT EXISTS device_type_sai_idx
ON telemetry.device_events (event_type)
USING 'sai';
~~~

Câu truy vấn đẳng thức:

~~~sql
SELECT tenant_id, device_id, event_day, event_time, event_id
FROM telemetry.device_events
WHERE event_type = 'BATTERY_LOW'
LIMIT 50;
~~~

Việc SAI hỗ trợ một predicate không đồng nghĩa **toàn query** có chi phí thấp cho mọi cardinality/QPS, hoặc tạo order mới nhất toàn cluster. Vẫn phải đo selectivity, số candidate rows, latency, fan-out và tải index trên dữ liệu thật.

### Không có tính tương đương 1:1 về cú pháp

SASI legacy:

~~~sql
-- Chỉ minh họa SASI CONTAINS:
WHERE message LIKE '%voltage%'
~~~

SAI:

~~~sql
-- Không giả định SAI hỗ trợ LIKE như SASI.
-- Cần viết lại use case và đối chiếu bảng operator SAI.
~~~

Bảng SAI official reference/FAQ của Cassandra 5.0 nêu toán tử `LIKE` không thuộc tập hỗ trợ theo mô hình được mô tả. Một số tính năng `CONTAINS` của SAI liên quan **collection values/keys**, không có nghĩa “tìm substring tùy ý trong một cột text”.

Nếu có yêu cầu giữ nguyên truy vấn legacy `LIKE '%...%'` khi nâng từ 4.x lên 5.0, phải lập phương án riêng: search service, thay UI contract, hoặc cách index phù hợp được nhà cung cấp hỗ trợ. Không chỉ thay class index và kỳ vọng ứng dụng không cần sửa.

## 18. Kiểm tra index thật trên schema

Có thể xem metadata qua CQL:

~~~sql
SELECT keyspace_name, table_name, index_name, kind, options
FROM system_schema.indexes
WHERE keyspace_name = 'telemetry'
  AND table_name = 'device_events';
~~~

Với một SASI legacy, trường `kind`/`options` có thể giúp nhận diện custom index class và tùy chọn mode. Cần diễn giải schema theo **phiên bản Cassandra thực tế**, không parse `SELECT *` dựa vào thứ tự cột giả định.

Trong `cqlsh` có thể dùng:

~~~text
DESCRIBE TABLE telemetry.device_events;
DESCRIBE INDEX telemetry.device_message_sasi_idx;
~~~

Đối chiếu:

- Tên index và tên bảng/column được index.
- Class `org.apache.cassandra.index.sasi.SASIIndex` hay `USING 'sai'`.
- Mode/analyzer và các options cần thiết.
- Điều kiện/version để index được tạo thành công.
- Trạng thái build/rebuild và cảnh báo trong server logs/metrics.
- Schema agreement giữa các node sau DDL.

**Không xem “index có trong catalog” là bằng chứng index trả kết quả đúng.** Với legacy SASI, phải có integration test so khớp kết quả với nguồn dữ liệu và kiểm tra khi flush/compaction/restart.

## 19. Vận hành: tạo, xây lại và xóa index

Dưới Cassandra, tạo secondary index có thể kích hoạt **index build** cho dữ liệu đã tồn tại. Khi index đang được xây, cluster có thể chịu chi phí CPU, bộ nhớ và I/O bổ sung. Mọi thao tác DDL phải đi qua migration/change management, không chạy tự phát từ nhiều instance Spring Boot lúc startup.

Khi vận hành index legacy, nhóm SRE/DBA có thể phải sử dụng các công cụ như:

~~~bash
# Lệnh quản trị tham khảo, không chạy trong production khi chưa duyệt.
nodetool status
nodetool describecluster
nodetool rebuild_index telemetry device_events device_message_sasi_idx
~~~

Cú pháp/khả năng `rebuild_index` phụ thuộc phiên bản, bản phân phối và tên index thực. Cần kiểm tra hướng dẫn của đúng server. Rebuild index có thể tiêu tốn tài nguyên lớn; không thực hiện như cách chữa mọi query timeout.

Xóa index (sau khi đã chuyển đường đọc và xác nhận không còn dependency):

~~~sql
DROP INDEX IF EXISTS telemetry.device_message_sasi_idx;
~~~

**DROP INDEX không tự xóa table data** nhưng có thể làm các truy vấn từng dựa vào index bị từ chối hoặc đắt hơn. Vì vậy phải kiểm tra repository methods, CQL viết tay và dashboard trước khi drop.

Khi tạo/xóa/rebuild, đợi cluster đạt **schema agreement** và xác minh trạng thái index sau thao tác. Schema agreement không chứng minh kết quả tìm kiếm đầy đủ; cần thêm kiểm tra dữ liệu.

## 20. SASI trong ứng dụng Spring Data Cassandra

Spring Data Cassandra là **client abstraction**. Nó không “biết” phải tự tạo SASI chỉ vì một field có `@Column` hoặc một repository có `@Query`.

Entity ví dụ:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_events")
public class DeviceEvent {
    @PrimaryKey
    private DeviceEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("message")
    private String message;

    public DeviceEvent() { }

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey v) { key = v; }

    public String getEventType() { return eventType; }
    public void setEventType(String v) { eventType = v; }

    public String getMessage() { return message; }
    public void setMessage(String v) { message = v; }
}
~~~

`DeviceEventKey` ở đây là composite key ánh xạ `tenant_id, device_id, event_day, event_time, event_id` tương ứng với DDL ở mục 9; cần định nghĩa `@PrimaryKeyClass` và `@PrimaryKeyColumn` chính xác như schema thực tế.

Một repository có query CQL legacy:

~~~java
import java.util.List;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    // Chỉ ví dụ về query legacy khi SASI đã được phép và tạo index.
    // Không khuyến nghị public API trên bảng rất lớn.
    @Query("SELECT * FROM device_events WHERE message LIKE ?0 LIMIT 50")
    List<DeviceEvent> legacySearchMessage(String pattern);
}
~~~

Khi gọi `legacySearchMessage("%voltage%")`, Java method không tạo index hay bật flag. Cassandra quyết định statement có hợp lệ hay không. Nếu backend chỉ có SAI, SASI đã bị tắt hoặc index chưa sẵn sàng, query có thể lỗi.

Trong ứng dụng đa tenant, query trên **mỗi pattern** mà thiếu partition key có thể là một đường đọc rộng và gây khó kiểm soát ranh giới dữ liệu. Không triển khai như endpoint nhận text tự do từ mọi user mà chưa thiết kế authorization, giới hạn tải và phạm vi tenant.

## 21. CqlTemplate và CqlSession cũng không thể sửa giới hạn server

Có thể dùng `CqlTemplate` cho CQL viết tay:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.CqlTemplate;

public class LegacySasiSearchDao {
    private final CqlTemplate template;

    public LegacySasiSearchDao(CqlTemplate template) {
        this.template = template;
    }

    public record Match(UUID deviceId, String message) { }

    public List<Match> findByTextPattern(String pattern) {
        String cql =
            "SELECT device_id, message "
          + "FROM telemetry.device_events "
          + "WHERE message LIKE ? LIMIT 50";

        return template.query(
            cql,
            (row, rowNum) -> new Match(
                row.getUuid("device_id"),
                row.getString("message")),
            pattern
        );
    }
}
~~~

Mã này minh họa cách truyền pattern bằng bind marker, không nối input vào CQL. **Nó không chứng minh SASI được hỗ trợ hoặc an toàn**. Chỉ chạy trong sandbox legacy có index phù hợp; nếu không, hãy để test ghi nhận lỗi và chuyển sang phương án khác.

Tương tự, `CqlSession.prepare(...)` và `BoundStatement` chỉ kiểm soát cách gửi truy vấn, consistency, timeout và paging. Chúng không làm `LIKE` có khả năng mới ngoài những gì server hỗ trợ.

Nếu cần tìm lịch sử một device/day, hãy ưu tiên repository/`CassandraTemplate` sử dụng **đủ partition key**. Không đưa SASI vào đường đọc đã tốt.

## 22. Kiểm thử tính năng theo version bằng ma trận, không đoán

Một test suite đánh giá SASI legacy cần chỉ rõ **server version và trạng thái feature flag**. Ma trận đề xuất:

| Môi trường | SASI config | Kết quả kiểm tra mong đợi |
| --- | --- | --- |
| Cassandra 3.11 sandbox | Theo config version, có thể bật mặc định | Nếu được phép, DDL và LIKE phải kiểm chứng |
| Cassandra 4.0 sandbox mặc định | `enable_sasi_indexes=false` | DDL SASI có thể bị chặn; xác minh thông báo |
| Cassandra 4.1 sandbox mặc định | `sasi_indexes_enabled=false` | DDL SASI có thể bị chặn; không bypass trên production |
| Cassandra 5.0 sandbox mặc định | `sasi_indexes_enabled=false` | Không xây thiết kế mới phụ thuộc SASI |
| Cassandra 5.0 với SAI | SAI được hỗ trợ | Test equality/range theo SAI; **không** mặc định LIKE substring |
| Managed Cassandra | Theo hợp đồng provider | Kiểm tra availability từ provider, không đoán |

Không cần bật SASI ở tất cả môi trường chỉ để có một test green. Nếu mục tiêu test là **chứng minh ứng dụng không còn phụ thuộc SASI**, một test từ chối/không hỗ trợ index là tín hiệu hữu ích.

Khi có cluster legacy thực sự phải duy trì, kiểm thử nên so:

1. Truy vấn trực tiếp theo full primary key để tạo tập sự kiện nguồn chính xác.
2. Truy vấn SASI `LIKE` hoặc equality tương ứng.
3. Tập ID kết quả kỳ vọng, gồm lowercase/uppercase, dấu tiếng Việt, chuỗi rỗng, text dài, dấu cách và special characters.
4. Hành vi khi dữ liệu được update/delete/TTL.
5. Kết quả sau flush, compaction và restart trong sandbox.
6. Khả năng rebuild index và thời gian ổn định sau build.
7. p95/p99 và lượng I/O/CPU trên dữ liệu đủ lớn.

Nếu kết quả index có dấu hiệu sai hoặc thiếu, không chấp nhận vì “đã có index”. Một hệ tìm kiếm không đáng tin có thể gây tác động nghiệp vụ ngay cả khi latency thấp.

## 23. Mẫu integration test ở tầng Java

Giả sử test cluster legacy đã được cấu hình cho phép SASI và schema/index sẵn sàng. Có thể viết test phác thảo qua `CqlSession`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.Test;

class LegacySasiQueryIT {

    private final CqlSession session;

    LegacySasiQueryIT(CqlSession session) {
        this.session = session;
    }

    @Test
    void containsIndexFindsInsertedMessage() {
        UUID tenant = UUID.randomUUID();
        UUID device = UUID.randomUUID();
        UUID event = UUID.randomUUID();

        var insert = session.prepare(
            "INSERT INTO telemetry.device_events "
          + "(tenant_id, device_id, event_day, event_time, "
          + "event_id, event_type, message) "
          + "VALUES (?, ?, ?, ?, ?, ?, ?)");

        session.execute(insert.bind(
            tenant, device, LocalDate.of(2026, 11, 25),
            Instant.parse("2026-11-25T09:30:00Z"),
            event, "BATTERY_LOW",
            "Battery voltage below threshold"
        ));

        var search = session.prepare(
            "SELECT event_id FROM telemetry.device_events "
          + "WHERE message LIKE ?");

        var result = session.execute(search.bind("%voltage%"));

        assertThat(result.all().stream()
            .map(row -> row.getUuid("event_id")))
            .contains(event);
    }
}
~~~

Ví dụ chỉ minh họa truy vấn và một assertion cơ bản; trong project thật phải khởi tạo `CqlSession` qua framework test hoặc Testcontainers, tạo schema/index qua migration thử nghiệm, chờ index build hoàn tất và dọn dữ liệu cô lập. Việc dùng một constructor như trên không tự tạo JUnit dependency injection; cần chỉnh thành cách tích hợp phù hợp môi trường kiểm thử.

Quan trọng hơn, **test 1 row không chứng minh chất lượng index trên hàng triệu row**. Cần test dữ liệu âm, nhiều partition, cập nhật/xóa, đồng thời và phiên bản server. Không mở SASI trên production để chạy thử.

## 24. Đo chi phí index: cả đọc lẫn ghi

Đánh giá SASI hoặc phương án thay thế trên workload đại diện:

| Nhóm | Chỉ số | Câu hỏi |
| --- | --- | --- |
| Query | p50/p95/p99, timeout, QPS | Index cải thiện latency hay tạo spike? |
| Query | Số partition/candidate rows, bytes returned | Có fan-out lớn dù trả ít kết quả? |
| Selectivity | Tỷ lệ row khớp mỗi pattern | Pattern phổ biến/hiếm có hành vi khác nhau? |
| Storage | Index bytes, SSTable/partition size | Dung lượng index tăng thế nào theo CONTAINS? |
| Write | Write latency, flush time, CPU, I/O | Duy trì index làm chậm ingest bao nhiêu? |
| Compaction | Queue/backlog, CPU/I/O, thời gian | Index build/merge có làm chậm compaction? |
| Availability | Node restart/streaming, error rate | Bootstrap/rebuild có làm index thiếu sẵn sàng? |
| Data integrity | So khớp tập event ID với nguồn | Index có trả thiếu/thừa row sau update/delete? |
| Operational | Time-to-build, rebuild duration | Migration/rollback có cửa sổ đủ an toàn? |

Thử với:

- Nhiều tenant, nhiều thiết bị, phân bố event type lệch mạnh.
- Message từ vài byte đến nhiều kilobyte, ký tự UTF-8 có dấu.
- Pattern tiền tố ngắn, tiền tố dài, substring phổ biến và hiếm.
- Ghi/cập nhật/xóa nhiều, TTL và tombstone.
- Node có dữ liệu lớn hơn trung bình, burst traffic và compaction đang chạy.

Không tự công bố “SASI nhanh hơn SAI” hoặc “SASI luôn rẻ hơn 2i” dựa trên tài liệu quảng bá cũ. Cần số đo cùng dataset, cùng query semantics và cùng điều kiện hạ tầng.

## 25. Phương án thay thế 1: bảng đọc theo site/type/day

Nếu product thật sự muốn “50 sự kiện `BATTERY_LOW` mới nhất của một site” thì đây là access pattern ổn định, không nhất thiết cần text index.

Thiết kế read model:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alerts_by_site_type_day (
    tenant_id   uuid,
    site_id     uuid,
    event_type  text,
    event_day   date,
    event_time  timestamp,
    device_id   uuid,
    event_id    uuid,
    message     text,
    PRIMARY KEY (
        (tenant_id, site_id, event_type, event_day),
        event_time, device_id, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC, event_id ASC
);
~~~

Query:

~~~sql
SELECT event_time, device_id, event_id, message
FROM telemetry.alerts_by_site_type_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND site_id = 44444444-4444-4444-8444-444444444444
  AND event_type = 'BATTERY_LOW'
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Bảng này có đầy đủ partition key cho query, clustering theo thời gian và tie-breaker ổn định. Không cần `LIKE` hay `ALLOW FILTERING`. Trong một partition, Cassandra có thể trả event mới nhất trước.

Đổi lại phải xây pipeline tạo/duy trì bảng projection:

~~~mermaid
flowchart LR
    A["Event ingest"] --> B["Nguồn event bền vững"]
    B --> C["events_by_device_day"]
    B --> D["alerts_by_site_type_day"]
    D --> E["API cảnh báo theo site"]
    C --> F["Timeline theo device"]
~~~

Các ghi vào hai bảng/partition không tự là transaction ACID đa bảng. Cần event ID ổn định, retry idempotent, backfill, reconciliation và theo dõi độ trễ projection. Nếu bucket ngày có nhiều cảnh báo, phải đo partition size và cân nhắc bucket giờ/sharding.

## 26. Phương án thay thế 2: search engine cho substring/full-text

Nếu người dùng cần **tìm mọi message chứa từ khóa tùy ý**, có nhiều ngôn ngữ, fuzzy matching, ranking, highlight hay phân tích văn bản, hãy đánh giá search engine phù hợp với nghiệp vụ.

Một kiến trúc tổng quát:

~~~mermaid
flowchart LR
    A["Event stream"] --> B["Cassandra event tables"]
    A --> C["Search index pipeline"]
    C --> D["Search engine"]
    D --> E["Query kết quả: event IDs"]
    E --> F["Đọc chi tiết từ Cassandra khi cần"]
~~~

Các vấn đề phải thiết kế:

- Quyền tenant/site khi lập chỉ mục và truy vấn.
- Đồng bộ dữ liệu tạo/sửa/xóa, event đến muộn và TTL/retention.
- Event ID ổn định, index replay và chống trùng.
- Độ trễ index giữa Cassandra và search engine.
- Thời gian rebuild và khả năng rollback.
- Mapping từ kết quả search trở lại **full Cassandra primary key**.
- Ranh giới dữ liệu riêng tư và chính sách bảo mật của công cụ search.
- Paging/cursor và kết quả thay đổi khi dữ liệu tiếp tục được ingest.

Không đánh đổi chính xác/độ mới dữ liệu chỉ vì có `LIKE` tiện lợi. Nếu search engine trả event ID không tồn tại nữa ở Cassandra, cần xử lý kết quả rỗng theo contract, không coi là lỗi “JOIN” của Cassandra.

## 27. Kế hoạch di chuyển SASI legacy trước khi nâng cấp

Giả sử một ứng dụng cũ chạy Cassandra 3.11/4.0 và có nhiều SASI index. Khi nâng lên Cassandra 5.0 hoặc một nền tảng không hỗ trợ SASI, không nên “đổi version rồi xem chuyện gì xảy ra”.

Quy trình đề xuất:

1. **Kiểm kê:** lấy DDL từ `DESCRIBE KEYSPACE` hoặc `system_schema.indexes`; nhận diện mọi index class SASI và options.
2. **Tìm consumer:** rà soát repository `@Query`, `CqlTemplate`, câu CQL viết tay và các job dựa vào `LIKE`/range.
3. **Phân loại access pattern:** equality/range đơn giản, cảnh báo theo site/time, substring/full-text hay báo cáo tổng hợp.
4. **Chọn thay thế:** query-driven table, SAI được hỗ trợ, hoặc search/analytics engine.
5. **Viết schema mới:** tạo index/table mới bằng migration có phiên bản và review trên staging.
6. **Triển khai luồng đồng bộ:** dual-write hoặc projector idempotent từ nguồn sự kiện có thể replay.
7. **Backfill:** chuyển dữ liệu lịch sử có checkpoint, giới hạn concurrency và áp lực lên cluster.
8. **Đối soát:** so event IDs, row counts theo bucket, dữ liệu update/delete và trường hợp Unicode.
9. **Canary:** chạy một phần query qua đường mới, đo p95/p99, tính đầy đủ và projection lag.
10. **Chuyển traffic:** vô hiệu hóa đường query SASI trên ứng dụng, không tạo SASI mới.
11. **Xóa index SASI:** chỉ sau khi chắc chắn không còn consumer và đã có đường rollback phù hợp.
12. **Nâng cấp server:** theo tài liệu nâng cấp version cụ thể, kiểm tra schema và tính năng của bản mới.

**Không tự kết luận việc drop SASI “không ảnh hưởng dữ liệu” đồng nghĩa không ảnh hưởng ứng dụng.** Table data vẫn tồn tại, nhưng các CQL trước đó cần SASI có thể không chạy được. Rollback code cũng không tự phục hồi dữ liệu projection nếu pipeline đã ghi thiếu.

Trong giai đoạn nâng cấp rolling với mixed-version nodes, phải tuân theo quy định compatibility của Cassandra; không thử index mới hoặc đổi flags tùy tiện trong khi cluster đang chuyển version.

## 28. Troubleshooting khi SASI không hoạt động

| Hiện tượng | Khả năng nguyên nhân | Bước kiểm tra |
| --- | --- | --- |
| `CREATE CUSTOM INDEX` bị từ chối | SASI disabled, thiếu quyền, class không được hỗ trợ | Server version, provider docs, `cassandra.yaml`, log |
| Config cũ không có tác dụng sau nâng cấp | Tên flag đã đổi | `enable_sasi_indexes` vs `sasi_indexes_enabled` theo bảng version |
| `LIKE` báo query không hợp lệ | SASI không có/disabled, mode không tương thích, chỉ có SAI | Index class, mode, supported operators |
| `LIKE 'Bat%'` có kết quả nhưng `LIKE '%vol%'` lỗi | Prefix index không tương đương contains | Kiểm tra mode `PREFIX`/`CONTAINS` |
| Kết quả tìm kiếm khác nhau sau update/delete | Index chưa sẵn sàng, replication/legacy correctness issue | So nguồn full-key, logs, rebuild/repair policy |
| p99 tăng sau thêm SASI | Index build, write amplification, compaction hoặc fan-out | Đo CPU/I/O, index size, query selectivity |
| Một node trả lỗi, node khác trả dữ liệu | Cấu hình/version hoặc index state không đồng nhất | Kiểm tra node versions, schema agreement, index status |
| Thêm `LIMIT 50` vẫn chậm | Candidate scan/fan-out vẫn lớn | Thiết kế lại access pattern |
| Đổi SASI → SAI nhưng LIKE ngừng hoạt động | Operator không tương đương | Tách use case substring sang search |
| Cassandra 5.0 có trang docs SASI nhưng không tạo được | Docs legacy còn tồn tại, feature mặc định tắt/deprecated | Đối chiếu config 5.0 và hướng thay thế |

Khi debug, tránh tăng timeout và retry vô hạn. Một query rất rộng gây timeout rồi bị retry có thể làm cluster nặng hơn. Giới hạn tần suất, concurrency, đọc/ghi thử ở môi trường cô lập trước khi thay đổi cấu hình.

## 29. Bài tập thực hành

### Bài A — Đọc ma trận phiên bản

Một nhóm chuyển từ Cassandra 3.11 sang 4.1. Họ giữ cấu hình `enable_sasi_indexes: true`. Hãy chỉ ra vì sao không nên giả định index vẫn có thể tạo mới, tên cờ cần kiểm tra và trạng thái experimental của SASI trên 4.1.

**Gợi ý:** 3.11/4.0 dùng `enable_sasi_indexes`, 4.1 dùng `sasi_indexes_enabled`, mặc định false theo tài liệu. Không bật production chỉ để vượt lỗi.

### Bài B — Phân biệt SASI và SAI

Một PR thay `USING 'org.apache.cassandra.index.sasi.SASIIndex'` bằng `USING 'sai'` và giữ nguyên `WHERE message LIKE '%voltage%'`. Vì sao PR chưa thể được coi là tương thích?

**Gợi ý:** SAI Cassandra 5.0 có tập operator riêng và không phải thay thế trực tiếp phép LIKE substring legacy.

### Bài C — Đọc index từ catalog

Viết CQL đọc `system_schema.indexes` cho bảng `telemetry.device_events`; xác định thông tin cần ghi vào báo cáo migration: tên, kind, class, cột, options và mode. Vì sao chỉ thấy tên index chưa chứng minh đã build đầy đủ?

### Bài D — Đánh giá chi phí

Một index `CONTAINS` phải xử lý 50 triệu message, nhiều message dài và cập nhật liên tục. Nêu ít nhất tám metrics bạn sẽ đo và điều kiện nào khiến nhóm dừng thử nghiệm.

**Gợi ý:** p95/p99, QPS, CPU, disk I/O, index size, flush/compaction, candidate rows, timeout, correctness sau delete/TTL.

### Bài E — Thiết kế read model

Product muốn 50 `BATTERY_LOW` mới nhất theo tenant/site/day. Tạo bảng `alerts_by_site_type_day` với composite partition key và clustering time DESC; giải thích vì sao không cần SASI cho query này.

### Bài F — Substring search

Product muốn tìm message chứa từ khóa tiếng Việt không phân biệt dấu, có xếp hạng theo mức liên quan. Giải thích vì sao SASI legacy hoặc SAI equality không mặc nhiên đáp ứng yêu cầu; phác thảo kiến trúc search engine + Cassandra full-key lookup.

### Bài G — Hành vi @Query

Một repository có:

~~~java
@Query("SELECT * FROM device_events WHERE message LIKE ?0 LIMIT 50")
List<DeviceEvent> legacySearchMessage(String pattern);
~~~

Nếu server tắt SASI và không có index phù hợp, Java method sẽ có thể phản hồi thế nào? Vì sao thay bằng `CqlTemplate` không chữa lỗi?

**Gợi ý:** client gửi CQL, server quyết định hỗ trợ; có thể ném exception. Template không thay index implementation.

### Bài H — Upgrade và rollback

Dự án có ba index SASI. Lập kế hoạch kiểm kê consumers, chọn thay thế, backfill, dual-write, canary, drop index và nâng Cassandra. Nêu ít nhất ba failure mode phải theo dõi khi chuyển đổi.

### Bài I — Kiểm tra dữ liệu thiếu do index

Một câu query SASI trả 95 event, nhưng kiểm tra nguồn theo full keys có 100 event khớp điều kiện. Trình bày cách thu bằng chứng, phân biệt thiếu do analyzer/index/build và dữ liệu bị xóa/TTL, và vì sao không nên chấp nhận kết quả thiếu chỉ vì latency tốt.

**Tiêu chí đạt:** người học nhận diện đúng SASI là experimental/deprecated, đối chiếu flags theo version, phân biệt SASI/SAI, hiểu mode và LIKE, không dùng index để che mô hình query sai, xây được kế hoạch kiểm thử/migration có tính đến kết quả đúng và hiệu năng.

## 30. Checklist trước khi sử dụng hoặc loại bỏ SASI

- [ ] Đã xác nhận bản Cassandra **thật** và bản phân phối/managed provider?
- [ ] Đã kiểm tra SASI được bật, được hỗ trợ và được khuyến nghị hay chỉ có tài liệu legacy?
- [ ] Đã đối chiếu `enable_sasi_indexes`/`sasi_indexes_enabled` theo đúng version?
- [ ] Đã kiểm tra schema/index class, options, mode và analyzer thực tế?
- [ ] Query có cần full-text/substring hay chỉ cần equality/range?
- [ ] Có thể giải quyết bằng partition key, clustering và read model thay vì index không?
- [ ] Đã phân biệt operator SASI `LIKE` với operator SAI thực sự hỗ trợ?
- [ ] Không nhầm `LIMIT` và paging với bảo đảm ít partition/row được đọc?
- [ ] Đã đo write amplification, index build, compaction, CPU/I/O và p99?
- [ ] Đã đối chiếu kết quả với nguồn full-key sau insert/update/delete/TTL?
- [ ] Có integration test theo version và test không có SASI?
- [ ] Có kế hoạch migration sang SAI/read model/search khi nâng cấp?
- [ ] Đã xử lý backfill, replay, idempotency, consistency và reconciliation?
- [ ] Không bật experimental index hoặc rebuild trên production khi chưa có quy trình kiểm soát?
- [ ] Có log, metrics, owner, ngưỡng cảnh báo và rollback khi đường truy vấn mới lỗi?

## Tài liệu tham khảo

- [Apache Cassandra — SASI Index, tài liệu legacy](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/SASI.html): cách tạo custom index, `PREFIX`, `CONTAINS`, `SPARSE` và ví dụ `LIKE`.
- [Apache Cassandra 3.11 — cassandra.yaml](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html): cờ `enable_sasi_indexes` và default.
- [Apache Cassandra 4.0 — cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html): cờ `enable_sasi_indexes` và default.
- [Apache Cassandra 4.1 — cassandra.yaml](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html): cờ `sasi_indexes_enabled` và default.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): trạng thái SASI experimental và mặc định tắt.
- [Apache Cassandra — SAI Overview](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-overview.html): khái niệm SAI.
- [Apache Cassandra — SAI FAQ](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-faq.html): phạm vi support và các toán tử, gồm giới hạn `LIKE`.
- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/indexing-concepts.html): so sánh primary indexing, 2i và SAI.
- [Apache Cassandra — CEP-7 Storage Attached Index](https://cwiki.apache.org/confluence/spaces/CASSANDRA/pages/158873324/CEP-7%2BStorage%2BAttached%2BIndex): định hướng phát triển SAI và vòng đời SASI.
- [Spring Data Cassandra — Cassandra Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query` và bind CQL.
- [Spring Data Cassandra — CqlTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): thực thi CQL và ánh xạ row.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): mapping entity và composite primary key.
