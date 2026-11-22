# OpenSearch shard, replica và quản lý dữ liệu theo thời gian

Amazon OpenSearch Service lưu dữ liệu trong index, chia index thành các shard và phân phối shard trên data node. Primary shard phân vùng dữ liệu gốc; replica shard là bản sao của primary, giúp tăng khả năng chịu lỗi và có thể phục vụ truy vấn tìm kiếm. Số lượng shard, replica, node và cách phân bổ theo Availability Zone ảnh hưởng trực tiếp đến dung lượng, throughput, latency, thời gian phục hồi và chi phí.

Với log, metric, event và dữ liệu quan sát, số bản ghi thường tăng liên tục. Nếu tạo index không giới hạn hoặc giữ mọi dữ liệu trên tầng lưu trữ hiệu năng cao, cluster sẽ tăng shard count, tốn heap, khó cân bằng và ngày càng đắt. Vì vậy, kiến trúc cần kết hợp shard sizing, replica strategy, rollover, retention, snapshot và storage tiering.

Bài học này tập trung vào Amazon OpenSearch Service domains trong hệ sinh thái AWS. Người học sẽ hiểu cách chọn shard count, replica count, phân phối dữ liệu qua node/AZ, quản lý index theo thời gian bằng Data Streams và Index State Management (ISM), cũng như chuyển dữ liệu từ hot storage sang UltraWarm và cold storage. Các quyết định cần dựa trên workload thực tế, yêu cầu truy vấn, RPO/RTO và chính sách lưu giữ dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích index, document, primary shard, replica shard, node và cluster.
- Phân biệt vai trò của primary và replica trong ghi, đọc, độ sẵn sàng và phục hồi.
- Ước lượng số primary shard theo dung lượng dữ liệu, tăng trưởng và loại workload.
- Nhận diện over-sharding, under-sharding, shard skew và unassigned shard.
- Thiết kế replica count và Multi-AZ phù hợp yêu cầu durability/availability.
- Hiểu giới hạn thay đổi primary shard count và chọn reindex, shrink hoặc split khi cần.
- Thiết kế index theo thời gian, alias rollover hoặc Data Streams.
- Tạo index template để thống nhất mapping, settings và policy cho index mới.
- Dùng ISM để rollover, giảm replica, force merge, snapshot, migrate tier và xóa dữ liệu.
- Phân biệt hot, UltraWarm và cold storage của Amazon OpenSearch Service.
- Theo dõi shard allocation, cluster health, storage, JVM, indexing/search latency và lifecycle action.
- Xây dựng retention policy có thể kiểm toán, khôi phục và kiểm soát chi phí.

## 2. OpenSearch lưu trữ dữ liệu như thế nào?

Amazon OpenSearch Service domain là cluster gồm các node chuyên trách. Trong đó:
- **Data node** lưu shard và xử lý indexing/search.
- **Dedicated cluster manager node** quản lý cluster state, node membership, index metadata và shard allocation; không phục vụ truy vấn dữ liệu thông thường.
- **Coordinating node** nhận request từ client, phân phối request đến shard phù hợp và tổng hợp kết quả. Trong nhiều cấu hình, data node cũng đảm nhiệm vai trò coordinating.
- **UltraWarm node** phục vụ index read-only trên tầng warm.
- **Cold storage** lưu index ít truy cập trên nền tảng Amazon S3; index được gắn vào warm node khi cần truy vấn.

Một index tương tự một bảng logic trong hệ quản trị dữ liệu. Document tương tự một bản ghi JSON. Field là thuộc tính của document. OpenSearch dùng mapping để xác định cách index và truy vấn từng field.

Một index có thể gồm nhiều primary shard. Mỗi primary shard là một phân vùng độc lập của index. Khi tạo document, OpenSearch xác định shard đích bằng routing, thường dựa trên document ID hoặc routing key. Mỗi primary shard có thể có một hoặc nhiều replica shard.

Ví dụ:

~~~text
Index: orders
  Primary shard 0  ---> Replica shard 0
  Primary shard 1  ---> Replica shard 1
  Primary shard 2  ---> Replica shard 2

Data nodes:
  Node A: Primary 0, Replica 1
  Node B: Primary 1, Replica 2
  Node C: Primary 2, Replica 0
~~~

Một replica chứa bản sao dữ liệu của primary tương ứng. OpenSearch phân bổ primary và replica của cùng shard lên các node khác nhau để tránh một lỗi node làm mất mọi bản sao của shard đó. Khi bật zone awareness, dịch vụ cố gắng phân phối các bản sao qua Availability Zone theo topology domain.

Shard là đơn vị phân phối, phục hồi và thực thi truy vấn. Một index quá ít shard có thể không tận dụng được tài nguyên cluster; quá nhiều shard tạo overhead quản lý và heap. Kích thước shard và cách phân bổ quan trọng hơn việc chỉ tăng số lượng node.

## 3. Primary shard và replica shard

### 3.1 Primary shard

Primary shard là phân vùng dữ liệu gốc của index. Khi client gửi index, update hoặc delete request, OpenSearch xác định primary shard tương ứng. Primary xử lý operation và đồng bộ thay đổi sang replica theo cơ chế replication.

Primary shard count được xác định khi tạo index. Với Amazon OpenSearch Service, mặc định của index thường là **5 primary shard và 1 replica cho mỗi primary**, tức tổng cộng 10 shard copies. Mặc định này khác upstream OpenSearch, nơi mặc định thường là 1 primary và 1 replica. Vì vậy, không nên để mặc định mà không kiểm tra workload.

Số primary shard ảnh hưởng:
- Mức độ song song khi indexing.
- Số shard tham gia mỗi truy vấn.
- Dung lượng mỗi shard.
- Số replica tương ứng.
- Chi phí heap, file handle, CPU và recovery.

### 3.2 Replica shard

Replica shard là bản sao của primary shard. Replica có hai vai trò:

1. **Khả năng chịu lỗi:** nếu node chứa primary gặp sự cố, một replica đủ điều kiện có thể được promote thành primary.
2. **Khả năng đọc:** search request có thể được điều phối đến primary hoặc replica, giúp phân phối tải truy vấn.

Replica không thay thế backup. Một thao tác xóa nhầm, update sai hoặc ingest dữ liệu lỗi sẽ được replication sang replica. Muốn khôi phục dữ liệu về thời điểm trước đó, cần snapshot hoặc một nguồn dữ liệu có thể replay.

### 3.3 Tác động của replica đến workload

Giả sử index có 4 primary shard:

| Replica count | Tổng shard copies | Tác động |
|---:|---:|---|
| 0 | 4 | Ít storage và write replication hơn; không có bản sao để chịu lỗi shard/node |
| 1 | 8 | Một bản sao bổ sung cho mỗi primary; tăng redundancy và read capacity |
| 2 | 12 | Hai bản sao bổ sung; có thể phân phối qua ba AZ theo thiết kế phù hợp |
| 3 | 16 | Thêm read capacity và redundancy nhưng tăng storage, network và write work |

Mỗi replica bổ sung gần như một bản sao dữ liệu của toàn index. Tăng replica giúp mở rộng khả năng đọc và khả năng chịu lỗi, nhưng không làm tăng số primary partition hay mức song song ghi vào primary theo cùng cách tăng primary shard.

Khi index đang ghi liên tục, primary phải đồng bộ thay đổi đến replica. Vì vậy, replica count lớn hơn có thể làm tăng network traffic và write amplification. Hãy benchmark read/write mix trước khi tăng replica chỉ để “tăng tốc”.

### 3.4 Khi nào có thể giảm replica?

Với dữ liệu lịch sử đã read-only, một số tổ chức giảm replica để tiết kiệm storage. Amazon OpenSearch Service có thể dùng ISM `replica_count` để tự động giảm replica sau một khoảng thời gian.

Chỉ làm việc này khi:
- Index đã ngừng ghi.
- Có snapshot hoặc nguồn dữ liệu có thể khôi phục.
- Chính sách availability cho phép giảm redundancy.
- Index không còn thuộc yêu cầu phục vụ production critical.
- Có kiểm thử restore và runbook.

Đặt replica count bằng 0 làm mất khả năng promote replica nếu node chứa primary gặp lỗi. Đây là trade-off durability, không chỉ là một thao tác tiết kiệm disk.

## 4. Cluster health và shard allocation

OpenSearch báo trạng thái cluster dựa trên khả năng phân bổ primary và replica shard.

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Green | Tất cả primary và replica shard đã được phân bổ | Theo dõi xu hướng và capacity |
| Yellow | Tất cả primary đã được phân bổ nhưng một hoặc nhiều replica chưa được phân bổ | Kiểm tra node, AZ, disk watermark, replica count và allocation rule |
| Red | Ít nhất một primary shard chưa được phân bổ | Ưu tiên khôi phục dữ liệu/primary, kiểm tra node failure và snapshot |

Yellow không có nghĩa dữ liệu primary đã mất, nhưng mức dự phòng giảm. Red có thể khiến một phần dữ liệu index không thể truy vấn đầy đủ.

Các nguyên nhân shard không được phân bổ:
- Không đủ data node hoặc node đang offline.
- Replica không thể nằm cùng node với primary tương ứng.
- Không đủ dung lượng hoặc vượt disk watermark.
- Allocation awareness/filter không cho phép node nào nhận shard.
- Shard recovery hoặc relocation bị throttle.
- Quá giới hạn shard trên node/cluster.
- Mapping, plugin hoặc version incompatibility sau thay đổi cluster.
- Node vừa thêm chưa đủ capacity để nhận shard.

Một số API kiểm tra:

~~~http
GET _cluster/health?pretty
GET _cluster/health?level=indices
GET _cat/nodes?v
GET _cat/shards?v
GET _cat/allocation?v
GET _cluster/allocation/explain
~~~

`_cluster/allocation/explain` cung cấp lý do cụ thể vì sao một shard chưa được phân bổ hoặc vì sao shard nằm trên node hiện tại. Không nên chỉ tăng node hoặc tắt allocation rule trước khi đọc nguyên nhân.

## 5. Chọn số primary shard

### 5.1 Mục tiêu kích thước shard

AWS khuyến nghị bắt đầu với các khoảng tham khảo:

| Loại workload | Kích thước primary shard gợi ý |
|---|---:|
| Search cần latency thấp | 10–30 GiB |
| Log analytics và workload ghi nhiều | 30–50 GiB |

Đây là điểm bắt đầu để benchmark, không phải giới hạn cứng áp dụng cho mọi index. Shard quá lớn làm recovery, relocation và query segment tốn thời gian. Shard quá nhỏ làm tăng số shard, metadata, heap, file handle và scheduling overhead.

Không nên tạo hàng trăm shard nhỏ chỉ để tận dụng hết node. Với index 5 GiB, một primary shard có thể hợp lý hơn nhiều primary shard vài trăm MiB.

### 5.2 Công thức ước lượng

Ước lượng sơ bộ số primary shard:

~~~text
Primary shard count
  ≈ (Source data + Growth allowance)
     x (1 + Indexing overhead)
     / Target primary shard size
~~~

Trong đó:
- Source data là lượng dữ liệu nguồn dự kiến index.
- Growth allowance là phần tăng trưởng trong khoảng lập kế hoạch.
- Indexing overhead là hệ số dự phòng cho mapping, inverted index, doc values, stored fields và cấu trúc Lucene.
- Target shard size là kích thước primary shard mong muốn.

Tỷ lệ dữ liệu nguồn so với kích thước index trên disk thay đổi theo mapping, analyzer, compression và field type. AWS đưa ra hệ số tham khảo gần 1,1 trong ví dụ sizing; nên index thử một mẫu dữ liệu để đo tỷ lệ thực tế.

### 5.3 Ví dụ tính shard count

Một workload log dự kiến tạo 360 GiB dữ liệu index trong một kỳ. Chọn mục tiêu 40 GiB mỗi primary shard và dự phòng overhead 10%:

~~~text
Primary shards
  ≈ 360 x 1.1 / 40
  ≈ 9.9
~~~

Có thể bắt đầu với 10 primary shard. Nếu index có một replica, tổng shard copies là 20.

Trước khi chốt, cần kiểm tra:
- Số data node.
- Số shard copies mỗi node.
- JVM heap.
- CPU và network.
- Mức tăng trưởng theo kỳ.
- Khả năng phục hồi trong thời gian node offline.
- Số shard của các index khác trong domain.

### 5.4 Không over-plan cho tăng trưởng quá xa

Giả sử dữ liệu hiện tại chỉ có 60 GiB nhưng dự kiến có thể tăng lên 300 GiB trong năm tới. Nếu tạo 10 primary shard ngay từ đầu, shard hiện tại chỉ khoảng 6–7 GiB. Số shard nhỏ làm tăng overhead ngay lập tức.

Có thể chọn một phương án trung gian:
- Tạo ít shard hơn để kích thước hiện tại hợp lý.
- Dùng rollover để tạo index mới theo ngưỡng kích thước.
- Khi index cũ quá lớn, reindex sang index có primary shard count mới.
- Benchmark trước khi thay đổi thiết kế.

Với time-series data, rollover theo size thường giúp giữ kích thước shard ổn định hơn tạo index theo ngày một cách máy móc.

## 6. Shard count theo data node và JVM heap

Ngoài shard size, cần kiểm soát số shard trên mỗi node. Mỗi shard có metadata, segment, file handle, cache và hoạt động nền. Quá nhiều shard nhỏ có thể tiêu thụ heap và CPU ngay cả khi dung lượng dữ liệu không lớn.

AWS đưa ra các hướng dẫn tham khảo:
- Cố gắng không vượt quá 25 shard trên mỗi GiB JVM heap của data node.
- Với OpenSearch Service đến phiên bản 2.15, giới hạn thường là 1.000 shard trên mỗi node.
- Với OpenSearch Service 2.17 trở lên, giới hạn hỗ trợ được tính theo 1.000 shard cho mỗi 16 GiB JVM heap, tối đa 4.000 shard mỗi node.
- Một số cấu hình như Multi-AZ with Standby có giới hạn riêng; tài liệu hiện hành nêu tối đa 1.000 shard trên mỗi node và 75.000 shard trên toàn cluster cho chế độ này.

Giới hạn dịch vụ là trần kỹ thuật, không phải mục tiêu thiết kế. Cluster có thể gặp vấn đề hiệu năng trước khi chạm trần.

Ví dụ, node có JVM heap 16 GiB:
- Theo guideline 25 shard/GiB, điểm bắt đầu thận trọng là khoảng 400 shard trên node.
- Không nên mặc định dùng toàn bộ quota 1.000 shard chỉ vì dịch vụ cho phép.

Cần tính cả primary và replica shard. Nếu một index có 10 primary và 2 replica thì nó đóng góp 30 shard copies vào cluster.

## 7. Phân phối shard trên node và Availability Zone

### 7.1 Phân phối theo node

OpenSearch cố gắng phân phối shard copies để tránh đặt primary và replica của cùng shard trên một node. Tuy nhiên, số shard count chia không đều, node size khác nhau hoặc allocation filter có thể tạo storage/CPU skew.

Một index có 12 primary shard thường dễ phân phối đều hơn khi data node count là 2, 3, 4, 6 hoặc 12. Đây chỉ là gợi ý cân bằng; shard size và workload vẫn là yếu tố chính.

Theo dõi:
- Shard count mỗi node.
- Primary/replica count.
- Storage used mỗi node.
- CPU và JVM pressure.
- Search/indexing queue.
- Request latency.
- Shard relocation và recovery.

### 7.2 Zone awareness

Với domain Multi-AZ, OpenSearch Service cố gắng đặt primary và replica ở các AZ khác nhau. Nếu một AZ gặp sự cố, bản sao ở AZ khác có thể tiếp tục phục vụ.

Trong Multi-AZ without Standby, AWS khuyến nghị tối thiểu một replica cho mỗi index nếu cần phân phối bản sao qua AZ. Nếu không có replica, dịch vụ không có bản sao để đặt ở AZ khác.

### 7.3 Multi-AZ with Standby

Với production domain đủ điều kiện, AWS khuyến nghị Multi-AZ with Standby. Cấu hình này có các yêu cầu chính:
- Ba Availability Zone.
- Ba dedicated cluster manager nodes.
- Ba hoặc bội số của ba data nodes.
- Ít nhất hai replica cho mỗi index, tạo ba bản sao dữ liệu gồm primary và hai replica.
- Instance type, storage type và một số cấu hình domain nằm trong danh sách hỗ trợ.

Mỗi AZ có một bản sao dữ liệu đầy đủ. Một AZ được giữ ở chế độ standby và không phục vụ search request trong trạng thái bình thường. Khi AWS phát hiện lỗi hạ tầng, standby được kích hoạt để duy trì khả năng phục vụ.

Đối với Multi-AZ with Standby, hãy kiểm tra giới hạn riêng về shard count, shard size, instance type và UltraWarm node count trước khi chọn cấu hình.

### 7.4 Replica không phải cross-Region DR

Multi-AZ bảo vệ trước một số sự cố node/AZ trong cùng Region. Nó không bảo vệ đầy đủ trước:
- Xóa index nhầm.
- Mapping sai làm hỏng dữ liệu.
- Ingest dữ liệu lỗi.
- Lỗi ứng dụng ghi đè dữ liệu.
- Sự cố ảnh hưởng toàn Region.
- Yêu cầu khôi phục về thời điểm trước đó.

Dùng snapshot và kế hoạch disaster recovery/cross-Region phù hợp với RPO/RTO.

## 8. Thay đổi primary shard count

Số primary shard được xác định khi tạo index và không thể đơn giản thay đổi bằng cách cập nhật `number_of_shards` trên index đang hoạt động.

Các phương án thường dùng:

| Phương án | Mục đích | Điều kiện/đánh đổi |
|---|---|---|
| Reindex | Sao chép document sang index mới với shard count/mapping mới | Tốn thời gian, CPU, disk và network; cần dual-write hoặc cutover |
| Shrink | Gộp nhiều primary shard thành ít shard hơn | Source cần read-only và đáp ứng điều kiện allocation |
| Split | Tạo index mới với nhiều primary shard hơn | Phụ thuộc `number_of_routing_shards` và điều kiện split |
| Rollover | Tạo index mới cho dữ liệu tiếp theo | Không thay đổi shard count của index cũ |

### 8.1 Reindex

Tạo index đích với settings/mapping mong muốn, sau đó chạy reindex:

~~~http
PUT orders-v2
{
  "settings": {
    "number_of_shards": 6,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "order_id": { "type": "keyword" },
      "created_at": { "type": "date" },
      "status": { "type": "keyword" }
    }
  }
}

POST _reindex
{
  "source": {
    "index": "orders-v1"
  },
  "dest": {
    "index": "orders-v2"
  }
}
~~~

Đây là ví dụ cấu trúc; trong production cần kiểm tra task status, throttling, version conflicts, ingest pipeline, routing và dữ liệu phát sinh trong lúc reindex.

Quy trình cutover thường gồm:
1. Tạo index đích và mapping.
2. Reindex dữ liệu lịch sử.
3. Đồng bộ phần ghi mới bằng dual-write, CDC hoặc một cửa sổ freeze phù hợp.
4. So sánh count, aggregate và sample document.
5. Chuyển alias đọc/ghi sang index mới.
6. Theo dõi query và indexing.
7. Chỉ xóa index cũ sau khi hết thời gian rollback.

### 8.2 Shrink và split

Shrink hữu ích khi index có quá nhiều primary shard nhỏ. Split hữu ích khi một index đã lớn và cần tăng mức song song.

Cả hai thao tác đều có điều kiện về routing, shard allocation và trạng thái index. Trước khi thực hiện, đọc tài liệu phiên bản OpenSearch đang chạy, kiểm tra dung lượng tạm thời và chạy thử trên bản sao.

Không dùng shrink/split để thay thế một chiến lược rollover hợp lý cho dữ liệu time-series mới.

## 9. Thiết kế index cho dữ liệu theo thời gian

Log, metric và event thường có trường timestamp. Một số mô hình phổ biến:

| Mô hình | Cách tổ chức | Phù hợp |
|---|---|---|
| Một index lâu dài | Ghi toàn bộ dữ liệu vào một index | Dữ liệu ít, retention đơn giản |
| Index theo ngày | `logs-2026.11.20` | Lưu lượng lớn, cần xóa theo ngày |
| Index theo tuần/tháng | `logs-2026.11` hoặc theo tuần | Dữ liệu tăng vừa phải, muốn giảm số index |
| Rollover alias | Alias trỏ đến write index hiện tại | Muốn tự động rollover theo size/age |
| Data Stream | Tên stream trỏ đến nhiều backing index | Dữ liệu time-series append-only |

Không nên tạo index theo ngày nếu mỗi ngày chỉ có vài trăm MiB dữ liệu. Cách đó có thể tạo rất nhiều shard nhỏ. Ngược lại, index theo tháng cho workload ghi lớn có thể tạo shard quá lớn và khiến recovery lâu.

Chọn chu kỳ dựa trên:
- Ingest rate và tăng trưởng.
- Số primary shard.
- Shard size mục tiêu.
- Truy vấn theo time range.
- Retention và compliance.
- Khả năng replay/backfill.
- Tần suất rollover và chi phí quản lý metadata.

Một nguyên tắc thực tế: để rollover theo size/age điều khiển kích thước shard, thay vì giả định một ngày luôn tạo ra cùng lượng dữ liệu.

## 10. Index template và mapping

Index template áp dụng settings và mappings cho index mới khớp pattern. Template giúp tránh index mới tự sinh mapping không nhất quán.

Các thành phần nên định nghĩa:
- `number_of_shards`.
- `number_of_replicas`.
- `refresh_interval`.
- ISM policy được áp dụng bằng `ism_template` hoặc API add policy.
- Timestamp field.
- `keyword`, `text`, `date`, numeric và boolean type.
- Dynamic mapping policy.
- Analyzer/normalizer nếu cần.
- Alias hoặc data stream settings.

Ví dụ template cho log:

~~~json
PUT _index_template/logs-template
{
  "index_patterns": ["logs-*"],
  "data_stream": {},
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "30s"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "service": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "level": { "type": "keyword" },
        "message": { "type": "text" },
        "status_code": { "type": "integer" },
        "duration_ms": { "type": "long" }
      }
    }
  }
}
~~~

`keyword` phù hợp cho exact match, filter, sort và aggregation. `text` phù hợp cho full-text search. Dùng `text` cho mọi field có thể làm tăng inverted index và khiến aggregation cần fielddata hoặc multi-field phù hợp.

Không cho phép dynamic mapping tạo vô hạn field từ payload không kiểm soát. Log JSON thường có field tùy biến; nên chuẩn hóa schema, dùng `dynamic: false` hoặc dynamic template có giới hạn nếu phù hợp với ứng dụng.

## 11. Data Streams cho log và metric

Data Stream cung cấp một tên logic để ghi và tìm kiếm dữ liệu time-series. Bên dưới, stream chứa nhiều backing index được rollover theo thời gian hoặc kích thước.

Đặc điểm:
- Mọi document phải có timestamp field.
- Dữ liệu theo mô hình append-only.
- Write request gửi đến backing index hiện tại.
- Search request chạy trên các backing index của stream.
- Backing index được tạo theo index template có `data_stream`.
- Rollover tạo backing index mới và đặt nó làm write index.

Data Streams phù hợp với log, metric và event liên tục phát sinh, trong đó document cũ hiếm khi được cập nhật.

### 11.1 Tạo Data Stream

Tạo index template:

~~~http
PUT _index_template/app-logs-template
{
  "index_patterns": ["logs-app-*"],
  "data_stream": {},
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "30s"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "application": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "message": { "type": "text" }
      }
    }
  }
}
~~~

Tạo stream:

~~~http
PUT _data_stream/logs-app-prod
~~~

Gửi document:

~~~http
POST logs-app-prod/_doc
{
  "@timestamp": "2026-11-20T04:30:00Z",
  "application": "checkout",
  "environment": "prod",
  "message": "payment authorization completed"
}
~~~

Tìm kiếm:

~~~http
GET logs-app-prod/_search
{
  "query": {
    "range": {
      "@timestamp": {
        "gte": "now-24h"
      }
    }
  }
}
~~~

### 11.2 Rollover Data Stream

Có thể rollover thủ công:

~~~http
POST logs-app-prod/_rollover
~~~

Hoặc dùng ISM để rollover tự động theo age, size hoặc document count.

Lưu ý:
- ISM policy được áp dụng cho backing index khi backing index được tạo.
- Khi gắn policy vào data stream, policy tác động đến backing index mới trong tương lai.
- Không cần `rollover_alias` cho data stream vì policy nhận diện stream từ backing index.
- Mọi document cần timestamp hợp lệ.
- Data Stream phù hợp append-only; update/delete document cần thao tác qua backing index hoặc API phù hợp.

### 11.3 Backfill và dữ liệu đến muộn

Data Stream ghi document mới vào write index hiện tại ngay cả khi `@timestamp` của document là thời điểm cũ. Điều này có thể xảy ra khi replay log hoặc backfill dữ liệu.

Nếu cần truy vấn theo khoảng thời gian, OpenSearch vẫn có thể lọc theo timestamp, nhưng lifecycle của backing index dựa trên tuổi index và policy. Vì vậy:
- Phân biệt event time và ingest time.
- Xác định quy trình backfill.
- Kiểm tra liệu dữ liệu cũ có nên ghi vào stream hiện tại hay một index lịch sử riêng.
- Tránh để dữ liệu đến muộn làm sai giả định về thời điểm xóa/archival.

### 11.4 Data Stream và cold storage

Có một giới hạn quan trọng: khi backing index của Data Stream được migrate sang cold storage, OpenSearch Service tách index đó khỏi Data Stream. Nếu migrate index trở lại UltraWarm, index vẫn là index độc lập và không tự gắn lại vào stream. Truy vấn trên tên Data Stream sẽ không còn trả dữ liệu của backing index đã tách.

Write index hiện tại không thể chuyển sang cold storage. Cần rollover trước khi migrate backing index cũ. Snapshot recovery của Data Stream có backing index ở UltraWarm cũng có thể không khôi phục đầy đủ trạng thái stream; trước snapshot dùng để phục hồi toàn bộ stream, hãy đưa các backing index về hot storage theo hướng dẫn AWS.

Nếu yêu cầu tìm kiếm lịch sử phải luôn truy cập qua một tên stream duy nhất, hãy đánh giá kỹ cold storage và thiết kế archive/search path trước khi bật lifecycle.

## 12. Rollover alias cho index truyền thống

Nếu dữ liệu không phù hợp với Data Stream, có thể dùng index alias với write index.

Pattern `legacy-logs-*` được tách riêng với Data Stream ở phần trước để tránh hai index template cùng khớp một index. Tạo template settings trước khi tạo index:

~~~http
PUT _index_template/legacy-logs-settings
{
  "index_patterns": ["legacy-logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "plugins.index_state_management.rollover_alias": "legacy-logs-write"
    }
  }
}
~~~

Tạo index đầu tiên với write alias và read alias:

~~~http
PUT legacy-logs-000001
{
  "aliases": {
    "legacy-logs-write": {
      "is_write_index": true
    },
    "legacy-logs-read": {}
  }
}
~~~

Ứng dụng ghi qua `legacy-logs-write` và tìm kiếm qua `legacy-logs-read`.

Khi index đạt ngưỡng:

~~~http
POST legacy-logs-write/_rollover
{
  "conditions": {
    "max_age": "1d",
    "max_size": "50gb"
  },
  "aliases": {
    "legacy-logs-read": {}
  }
}
~~~

Các điều kiện `max_age`, `max_size`, `max_docs` trong rollover API được kết hợp theo OR: chỉ cần một điều kiện đạt là rollover có thể xảy ra. Kiểm tra response `rolled_over` để biết rollover đã thực sự diễn ra.

Rollover tạo index mới, chuyển write alias sang index mới và giữ index cũ làm dữ liệu lịch sử. Alias giúp ứng dụng không phải thay tên index sau mỗi lần rollover.

## 13. Index State Management (ISM)

ISM tự động thực hiện thao tác quản lý index dựa trên tuổi, kích thước hoặc số document. Policy là một state machine gồm:
- State: trạng thái hiện tại của index, ví dụ hot, warm, cold, delete.
- Action: thao tác thực hiện khi vào state.
- Transition: điều kiện chuyển sang state tiếp theo.

Các action thường dùng:
- `rollover`: tạo index mới cho alias hoặc data stream.
- `replica_count`: thay đổi số replica.
- `force_merge`: gộp segment.
- `snapshot`: tạo snapshot vào repository đã cấu hình.
- `warm_migration`: chuyển index sang UltraWarm.
- `cold_migration`: chuyển index sang cold storage.
- `delete`: xóa index thông thường.
- `cold_delete`: xóa index trong cold storage.

Trong Amazon OpenSearch Service, ISM API thường dùng prefix `_plugins/_ism`. Domain Elasticsearch/OpenSearch cũ có thể dùng prefix legacy `_opendistro`.

### 13.1 Gắn policy cho index

Tạo policy trong OpenSearch Dashboards hoặc qua API:

~~~http
PUT _plugins/_ism/policies/logs-retention
{
  "policy": {
    "description": "Rollover và quản lý vòng đời log",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "warm",
            "conditions": {
              "min_index_age": "30d"
            }
          }
        ]
      },
      {
        "name": "warm",
        "actions": [
          {
            "warm_migration": {}
          }
        ],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "90d"
            }
          }
        ]
      },
      {
        "name": "delete",
        "actions": [
          {
            "delete": {}
          }
        ],
        "transitions": []
      }
    ],
    "ism_template": {
      "index_patterns": ["logs-*"],
      "priority": 100
    }
  }
}
~~~

Ví dụ trên minh họa hot-to-warm-to-delete và giả định domain đã bật UltraWarm. Nó chưa phải retention policy production hoàn chỉnh: cần bổ sung snapshot, cold storage hoặc thời hạn lưu theo yêu cầu tổ chức.

Áp dụng policy thủ công cho index:

~~~http
POST _plugins/_ism/add/logs-2026.11.20
{
  "policy_id": "logs-retention"
}
~~~

Kiểm tra policy và trạng thái managed index:

~~~http
GET _plugins/_ism/policies/logs-retention
GET _plugins/_ism/explain/logs-2026.11.20
~~~

### 13.2 ISM template

Có thể khai báo `ism_template` trong policy để policy tự áp dụng cho index mới khớp pattern. Đây là trường của policy ISM.

Trong Amazon OpenSearch Service, không nên dựa vào cách cũ gắn ISM policy trực tiếp từ index template bằng setting legacy. AWS đã thay đổi cơ chế; dùng `ism_template` trong policy theo tài liệu hiện hành.

ISM template chỉ áp dụng cho index mới được tạo sau khi policy/template có hiệu lực. Index cũ cần được gắn policy riêng hoặc qua quy trình migration.

### 13.3 Rollover bằng ISM

Với alias-based index, cần:
- Tên index kết thúc bằng số, ví dụ `logs-000001`.
- Alias được chỉ định làm write alias.
- Setting `plugins.index_state_management.rollover_alias` trỏ đến alias.
- Policy có action `rollover`.

Ví dụ action:

~~~json
{
  "rollover": {
    "min_index_age": "1d",
    "min_primary_shard_size": "30gb",
    "copy_alias": true
  }
}
~~~

Các điều kiện trong action được kết hợp theo OR. Khi một điều kiện đạt, ISM có thể rollover ở lần chạy policy tiếp theo. `copy_alias: true` giúp giữ các alias đọc như `legacy-logs-read` trên index mới. Với data stream, không cần cấu hình rollover alias.

### 13.4 ISM không chạy tức thời

ISM chạy theo chu kỳ job. Trên Amazon OpenSearch Service, job thường chạy mỗi 5–8 phút tùy phiên bản; cluster ở trạng thái red sẽ không chạy các job ISM. Vì vậy, không xem điều kiện `min_index_age: 30d` là một lịch chạy chính xác đến từng giây.

Một action có thể mất thời gian do shard migration, force merge, snapshot hoặc cold migration. Cần theo dõi policy execution, retry và lỗi. Nếu action thất bại, hãy đọc explain API và xử lý nguyên nhân trước khi retry.

### 13.5 Chính sách ví dụ hot → warm → cold → delete

Đây là ví dụ cho domain đã bật UltraWarm và cold storage. Thời hạn 10/90/365 ngày chỉ mang tính minh họa:

~~~json
PUT _plugins/_ism/policies/logs-hot-warm-cold
{
  "policy": {
    "description": "Lifecycle cho log lịch sử",
    "default_state": "hot",
    "schema_version": 1,
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "warm",
            "conditions": {
              "min_index_age": "10d"
            }
          }
        ]
      },
      {
        "name": "warm",
        "actions": [
          {
            "warm_migration": {},
            "retry": {
              "count": 5,
              "delay": "1h"
            }
          }
        ],
        "transitions": [
          {
            "state_name": "cold",
            "conditions": {
              "min_index_age": "90d"
            }
          }
        ]
      },
      {
        "name": "cold",
        "actions": [
          {
            "cold_migration": {
              "timestamp_field": "@timestamp"
            }
          }
        ],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "365d"
            }
          }
        ]
      },
      {
        "name": "delete",
        "actions": [
          {
            "cold_delete": {}
          }
        ],
        "transitions": []
      }
    ],
    "ism_template": {
      "index_patterns": ["logs-*"],
      "priority": 100
    }
  }
}
~~~

Lưu ý:
- Cold migration qua ISM cần chỉ rõ timestamp field.
- Cold index phải dùng `cold_delete`, không dùng action `delete` thông thường.
- Policy áp dụng theo index age và chu kỳ job, không theo thời điểm event trong document.
- Nếu dùng Data Stream, cold migration sẽ detach backing index khỏi stream.
- Phải xác nhận snapshot/restore, retention, compliance và khả năng truy vấn trước khi bật policy xóa.

## 14. Hot, UltraWarm và cold storage

Amazon OpenSearch Service hỗ trợ các tầng lưu trữ với đặc tính hiệu năng và chi phí khác nhau.

| Tier | Nền tảng lưu trữ | Mục đích | Cách truy cập |
|---|---|---|---|
| Hot | Instance store hoặc EBS trên data node | Index mới, dữ liệu thường xuyên ghi/đọc | Search và indexing bình thường |
| UltraWarm | Amazon S3 kết hợp cache trên warm node | Dữ liệu read-only, ít ghi và ít truy vấn hơn | Search qua OpenSearch API, có thể có latency cao hơn hot |
| Cold | Amazon S3, metadata quản lý riêng | Dữ liệu lịch sử ít truy cập, phân tích theo nhu cầu | Attach/migrate trở lại warm để truy vấn |

### 14.1 Hot storage

Hot storage phù hợp với:
- Dữ liệu mới ingest.
- Truy vấn có yêu cầu latency thấp.
- Index đang cập nhật thường xuyên.
- Workload cần indexing và refresh liên tục.

Dung lượng hot storage thường là EBS hoặc instance store theo loại data node. Tăng dung lượng hot node có thể làm tăng chi phí ngay cả khi dữ liệu ít được truy vấn.

### 14.2 UltraWarm

UltraWarm dùng S3 làm nền tảng lưu trữ và cache để truy vấn dữ liệu read-only. Nó phù hợp với log, audit và dữ liệu lịch sử cần tìm kiếm nhưng không cần tốc độ như hot tier.

Đặc điểm:
- Index trên warm tier là read-only.
- Muốn ghi lại phải migrate index về hot tier.
- Cần bật UltraWarm và dedicated cluster manager nodes.
- Số warm node và instance type phải phù hợp với dung lượng cần quản lý.
- Migrate sang warm thường cần force merge, do đó có thể tốn thời gian và tài nguyên.
- Query có thể chậm hơn hot tier vì sử dụng storage/caching khác.

UltraWarm vẫn cho phép dùng OpenSearch API và Dashboards để tìm kiếm index. Tuy nhiên, cần benchmark query thực tế, nhất là các truy vấn aggregation lớn hoặc quét time range rộng.

### 14.3 Cold storage

Cold storage dành cho dữ liệu ít truy cập, phục vụ forensic, audit hoặc điều tra lịch sử định kỳ.

Đặc điểm:
- Dựa trên Amazon S3.
- Cần bật UltraWarm trên cùng domain.
- Hỗ trợ OpenSearch/Elasticsearch 7.9 trở lên theo điều kiện dịch vụ.
- Index cold được attach vào warm node khi cần truy vấn.
- Có thể migrate cold ↔ warm theo quy trình dịch vụ.
- Cold index cần timestamp metadata khi dùng ISM cold migration.
- Không thể ghi trực tiếp vào cold index.

Cold storage không phải một node pool luôn sẵn sàng phục vụ search. Dữ liệu cần được gắn lại vào warm để truy vấn. Hãy đưa thời gian attach/migration vào quy trình điều tra và SLA truy xuất dữ liệu.

### 14.4 Chọn tier theo tuổi và tần suất truy vấn

Ví dụ chính sách:
- 0–10 ngày: hot, ingest liên tục và truy vấn thường xuyên.
- 10–90 ngày: UltraWarm, chủ yếu đọc và điều tra.
- 90–365 ngày: cold, chỉ truy vấn khi có yêu cầu.
- Trên 365 ngày: snapshot/archive hoặc xóa theo chính sách lưu giữ.

Đây chỉ là ví dụ. Hệ thống thanh toán, bảo mật hoặc tuân thủ pháp lý có thể yêu cầu retention dài hơn, snapshot riêng và thời gian khôi phục cụ thể.

## 15. Force merge và tối ưu index lịch sử

Mỗi shard được tạo từ nhiều Lucene segment. Update/delete tạo document mới hoặc đánh dấu document cũ đã xóa; segment có thể cần merge để giải phóng dữ liệu đã xóa và giảm số segment phải đọc.

Force merge có thể:
- Gộp nhiều segment thành ít segment hơn.
- Giảm overhead đọc/query trên index read-only.
- Chuẩn bị index trước khi migrate sang UltraWarm.
- Thu hồi một phần dung lượng từ document đã xóa.

Nhưng force merge là tác vụ nặng:
- Tạo I/O và CPU.
- Có thể cần dung lượng tạm thời.
- Tăng tải cluster.
- Không phù hợp với index đang ingest liên tục.
- Không nên chạy đồng loạt trên tất cả index trong giờ cao điểm.

Chỉ force merge khi index đã rollover và không còn ghi, hoặc theo quy trình được thiết kế cho workload. Có thể dùng ISM action `force_merge` trong warm state.

## 16. Snapshot và khả năng khôi phục

Replica bảo vệ trước một số lỗi node/shard, còn snapshot bảo vệ khả năng phục hồi dữ liệu theo thời điểm.

Amazon OpenSearch Service có:
- Automated snapshots do dịch vụ quản lý theo lịch và retention của dịch vụ.
- Manual snapshots lưu vào S3 repository do người dùng cấu hình.

Manual snapshot thường dùng khi:
- Cần kiểm soát thời điểm backup.
- Cần lưu giữ dài hơn automated snapshot.
- Cần khôi phục index hoặc domain theo kế hoạch.
- Cần hỗ trợ migration/DR giữa domain hoặc Region trong phạm vi tương thích.

Khi dùng manual snapshot:
1. Tạo S3 bucket và IAM role/policy phù hợp.
2. Đăng ký snapshot repository với domain.
3. Tạo snapshot theo lịch.
4. Theo dõi trạng thái snapshot.
5. Thử restore vào domain staging.
6. Kiểm tra index, alias, mapping, document count và truy vấn.

Snapshot có thể tốn thời gian khi domain có nhiều shard hoặc dedicated master node không đủ capacity. AWS khuyến nghị sizing dedicated master node theo shard count và giữ shard count trong mức hợp lý.

Snapshot không tự thay thế quy trình kiểm thử restore. Một backup chưa từng được restore thử chưa chứng minh được RTO.

### 16.1 Snapshot và Data Stream

Nếu Data Stream có backing index đã migrate sang UltraWarm, snapshot recovery có thể không khôi phục đầy đủ trạng thái Data Stream. AWS khuyến nghị đưa tất cả backing index về hot storage trước khi tạo snapshot với mục đích phục hồi toàn bộ stream.

Cold migration còn detach backing index khỏi Data Stream. Hãy kiểm tra kiến trúc truy vấn và snapshot trước khi đưa backing index sang cold.

## 17. Retention, compliance và xóa dữ liệu

Retention policy cần được xác định cùng owner dữ liệu, security, finance và compliance.

Các câu hỏi:
- Dữ liệu nào phải giữ và giữ bao lâu?
- Thời hạn được tính từ event time hay ingest time?
- Dữ liệu có PII, payment data hoặc secret không?
- Có yêu cầu legal hold hoặc eDiscovery không?
- Ai được phép thay đổi policy hoặc xóa index?
- Snapshot có retention độc lập không?
- Có cần xóa dữ liệu khỏi cả hot, warm, cold và snapshot?
- Có yêu cầu chứng minh việc xóa đã hoàn tất không?

Xóa index bằng ISM không đồng nghĩa mọi bản sao backup đã biến mất. Nếu snapshot vẫn chứa dữ liệu, dữ liệu có thể được khôi phục từ snapshot trong thời hạn snapshot retention. Cần chính sách xóa đồng bộ giữa index lifecycle, snapshot lifecycle và kho dữ liệu gốc.

Đối với dữ liệu nhạy cảm, hãy xem xét field-level filtering, encryption, access control, audit log và quy trình data deletion xuyên hệ thống.

## 18. Theo dõi shard, node và lifecycle

### 18.1 API quan sát thường dùng

| API | Mục đích |
|---|---|
| `GET _cluster/health` | Trạng thái cluster |
| `GET _cat/indices?v` | Số primary/replica, document count và storage theo index |
| `GET _cat/shards?v` | Trạng thái, node và size từng shard |
| `GET _cat/allocation?v` | Shard count và disk allocation theo node |
| `GET _cat/nodes?v` | Node roles, heap, CPU và tài nguyên |
| `GET _cluster/allocation/explain` | Giải thích shard unassigned hoặc placement |
| `GET _plugins/_ism/explain/<index>` | Trạng thái policy và action của ISM |
| `GET _data_stream` | Danh sách Data Stream và backing index |
| `GET _data_stream/<name>/_stats` | Thống kê Data Stream |

Ví dụ tìm index lớn:

~~~http
GET _cat/indices?v&s=store.size:desc
~~~

Xem shard allocation:

~~~http
GET _cat/shards?v&s=store:desc
GET _cat/allocation?v
~~~

Xem trạng thái lifecycle:

~~~http
GET _plugins/_ism/explain/logs-*
~~~

### 18.2 CloudWatch metrics

Amazon OpenSearch Service tích hợp CloudWatch. Các metric cần theo dõi gồm:

| Metric/nhóm | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| `ClusterStatus.green/yellow/red` | Sức khỏe cluster | Yellow/red kéo dài |
| `FreeStorageSpace` | Dung lượng trống | Disk gần watermark |
| `JVMMemoryPressure` | Áp lực heap JVM | Heap cao kéo dài, GC nhiều |
| `CPUUtilization` | Tải CPU | CPU cao và queue tăng |
| `SearchLatency` | Độ trễ tìm kiếm | P95/P99 vượt SLA |
| `IndexingLatency` | Độ trễ ghi | Ingest chậm |
| `IndexingRate` | Tốc độ index document | Thay đổi bất thường |
| `SearchRate` | Tốc độ query | Traffic tăng hoặc query fan-out |
| `Nodes` | Số node hiện có | Node giảm hoặc không ổn định |
| `MasterReachableFromNode` | Khả năng liên lạc với cluster manager | Node không liên lạc được manager |
| `ThreadpoolSearchQueue` | Queue của search thread pool | Query bị dồn |
| `ThreadpoolWriteQueue` | Queue của write thread pool | Ingest bị dồn |
| `WarmToColdMigrationQueueSize` | Queue migrate warm-to-cold | Lifecycle bị chậm |
| `SnapshotFailure` | Snapshot lỗi | Rủi ro không có backup hợp lệ |

Tên metric và dimensions có thể thay đổi theo loại domain, engine version và tier. Dùng CloudWatch metric reference hiện hành để tạo alarm.

### 18.3 Chỉ số shard cụ thể

Nên theo dõi:
- Shard size trung bình và phân vị lớn nhất.
- Shard count mỗi node.
- Primary/replica ratio.
- Unassigned shard count.
- Relocating/initializing shard.
- Under-replicated shard.
- Disk skew.
- Hot partition/index.
- Segment count.
- Recovery duration.

Đừng chỉ xem tổng storage của cluster. Một node có thể gần đầy trong khi các node khác còn nhiều dung lượng do shard skew.

## 19. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Cluster yellow kéo dài | Replica unassigned, node thiếu disk hoặc allocation constraint | Allocation explain, node count, AZ awareness |
| Cluster red | Primary shard unassigned | Kiểm tra node failure, recovery và snapshot |
| Shard quá lớn | Rollover không hoạt động hoặc primary count thấp | Xem index age/size, policy execution, reindex plan |
| Quá nhiều shard nhỏ | Index-per-day không phù hợp hoặc primary count cao | Gộp kỳ, reindex/shrink, rollover theo size |
| Một node gần đầy | Shard/storage skew | Cat allocation, shard size và relocation |
| JVM pressure cao | Quá nhiều shard, mapping field lớn hoặc query nặng | Shard/heap ratio, mapping, fielddata, query |
| Search latency tăng | Query fan-out, shard quá lớn, hot node hoặc cold tier | Search profile, latency per node, tier |
| Indexing latency tăng | Replica/write pressure, refresh quá thường xuyên, merge hoặc disk bottleneck | Write queue, replica count, refresh interval |
| Warm migration thất bại | UltraWarm capacity, force merge hoặc index state | ISM explain, warm capacity, migration log |
| Cold migration thất bại | Thiếu timestamp field hoặc cold storage chưa bật | Domain config, timestamp mapping, ISM action |
| ISM không chạy | Cluster red, policy lỗi hoặc action đang retry | ISM explain, cluster health, job status |
| Data Stream thiếu dữ liệu cũ | Backing index đã bị detach khi chuyển cold | Kiểm tra Data Stream API, cold index list và query path |
| Snapshot restore thiếu stream state | Backing index đang ở UltraWarm | Đưa index về hot trước snapshot/restore workflow |

Khi điều tra, ưu tiên đọc bằng chứng từ API và metric. Không tăng replica, xóa index hoặc tắt allocation awareness chỉ để đưa cluster về green mà chưa hiểu tác động.

## 20. Ví dụ kiến trúc log analytics trên AWS

Một ứng dụng thương mại điện tử ghi log từ ECS/EKS và Lambda. Log được đưa qua pipeline ingest đến Amazon OpenSearch Service để tìm kiếm sự cố và phân tích hoạt động.

~~~text
ECS / EKS / Lambda
       |
       | Application logs + @timestamp
       v
Amazon Data Firehose / OpenSearch Ingestion
       |
       v
Amazon OpenSearch Service domain
       |
       +---- Hot data nodes
       |       - 0-10 ngày
       |       - Indexing + search thường xuyên
       |
       +---- UltraWarm
       |       - 10-90 ngày
       |       - Read-only investigation
       |
       +---- Cold storage (S3-backed)
       |       - 90-365 ngày
       |       - Attach khi cần forensic
       |
       +---- Snapshot repository in S3
               - Backup/restore theo policy
~~~

Một thiết kế có thể gồm:
- Multi-AZ with Standby cho production nếu domain/Region/instance đáp ứng yêu cầu.
- Index template hoặc Data Stream để chuẩn hóa mapping.
- Primary shard count được sizing theo throughput và shard target.
- Replica count theo HA requirement.
- ISM rollover để giới hạn kích thước backing index.
- ISM warm/cold migration theo retention.
- Snapshot schedule riêng.
- CloudWatch dashboard và alarm.
- Access policy theo application team và security team.

Pipeline ingest nên chuẩn hóa timestamp, service, environment, severity và trace ID. Tránh tạo field mới không giới hạn từ payload động vì mapping explosion có thể làm cluster quá tải.

## 21. Runbook quản lý shard và lifecycle

### 21.1 Trước khi tạo index

1. Xác định data volume theo ngày/tuần/tháng.
2. Đo source-to-index ratio bằng dữ liệu mẫu.
3. Chọn target shard size.
4. Tính primary shard count.
5. Xác định replica count theo HA.
6. Kiểm tra shard/heap ratio và node capacity.
7. Tạo template và mapping.
8. Xác minh policy/alias/data stream.

### 21.2 Khi cluster tăng tải

1. Kiểm tra cluster health.
2. Xem top index theo storage.
3. Xem shard count và shard size.
4. Kiểm tra CPU, heap, disk và queue.
5. Xác định hot index hoặc hot partition.
6. Kiểm tra query fan-out và ingest pattern.
7. Scale node hoặc tối ưu shard/index theo kết quả đo.
8. Rehearse thay đổi trên staging.

### 21.3 Khi index đến tuổi rollover

1. Xác nhận index đạt size/age threshold.
2. Kiểm tra ISM explain.
3. Xác nhận backing index mới được tạo.
4. Kiểm tra write alias hoặc data stream write index.
5. Xác minh index cũ không còn nhận ghi.
6. Theo dõi search và ingest qua alias/stream.
7. Kiểm tra policy transition sang warm.

### 21.4 Trước khi migrate sang warm/cold

1. Xác nhận index đã read-only.
2. Kiểm tra snapshot và retention.
3. Kiểm tra query pattern và nhu cầu latency.
4. Kiểm tra UltraWarm/cold storage đã bật.
5. Kiểm tra timestamp field nếu migrate cold bằng ISM.
6. Kiểm tra Data Stream backing index có bị detach khỏi stream không.
7. Theo dõi migration queue và action status.
8. Thử attach cold index trở lại warm trong staging.

### 21.5 Trước khi xóa

1. Xác nhận retention đã hết.
2. Xác nhận không có legal hold.
3. Xác nhận snapshot/backup đáp ứng policy.
4. Kiểm tra index không còn write alias hoặc consumer phụ thuộc.
5. Xác nhận xóa cold dùng `cold_delete`.
6. Lưu bằng chứng lifecycle và approval.
7. Theo dõi dung lượng được giải phóng.

## 22. Checklist thiết kế production

- [ ] Đã đo dữ liệu nguồn và tỷ lệ tăng trưởng.
- [ ] Đã benchmark source-to-index ratio.
- [ ] Primary shard count dựa trên target shard size và workload.
- [ ] Shard size nằm trong khoảng phù hợp với search hoặc log workload.
- [ ] Đã tính cả primary và replica khi tính shard count/node.
- [ ] Shards per GiB JVM heap nằm trong giới hạn vận hành.
- [ ] Không dùng quota shard per node làm mục tiêu sizing.
- [ ] Replica count đáp ứng HA, read capacity và durability.
- [ ] Primary và replica được phân phối qua node/AZ theo thiết kế.
- [ ] Multi-AZ with Standby đáp ứng 3 AZ, dedicated masters, data node count và replica requirement.
- [ ] Có snapshot/restore test; không coi replica là backup.
- [ ] Đã chọn index-per-period, alias rollover hoặc Data Stream phù hợp.
- [ ] Data Stream có timestamp field và workload append-only.
- [ ] Index template có mapping/settings nhất quán.
- [ ] Dynamic mapping được kiểm soát.
- [ ] Rollover threshold dựa trên shard size và ingest rate.
- [ ] ISM policy áp dụng cho index mới bằng `ism_template`.
- [ ] ISM policy có retry, monitoring và owner.
- [ ] Warm/cold tier đã được benchmark theo latency và retention.
- [ ] Đã hiểu cold migration ảnh hưởng đến Data Stream backing index.
- [ ] Snapshot retention được phối hợp với index retention.
- [ ] CloudWatch alarm bao phủ health, disk, heap, latency, queue và migration.
- [ ] Có runbook cho unassigned shard, shard skew, rollover, restore và deletion.
- [ ] Retention và deletion được phê duyệt theo compliance/business owner.

## 23. Bài tập thực hành

### Bài 1: Tính số primary shard

Một index log dự kiến có 420 GiB dữ liệu đã index trong tháng. Chọn shard target 35 GiB. Bỏ qua tăng trưởng trong ví dụ.

Yêu cầu:
1. Ước lượng primary shard count với overhead 10%.
2. Nếu có 1 replica, tổng shard copies là bao nhiêu?

Đáp án:
- Primary shard count ≈ 420 × 1,1 / 35 = 13,2, làm tròn khoảng 14.
- Với một replica: 14 × 2 = 28 shard copies.

### Bài 2: Nhận diện over-sharding

Một index chỉ có 4 GiB nhưng được tạo với 20 primary shard và 1 replica.

Yêu cầu: nêu vấn đề và phương án xử lý.

Đáp án: mỗi primary chỉ khoảng 0,2 GiB, quá nhỏ so với guideline. Có thể reindex vào index mới với ít primary shard hơn, kiểm tra mapping/query và cutover qua alias. Không thể chỉ cập nhật `number_of_shards` trên index hiện tại.

### Bài 3: Replica count

Một domain có 3 primary shard, 2 replica cho mỗi primary.

Yêu cầu: tổng số shard copies và dung lượng dữ liệu tương đối là bao nhiêu so với không replica?

Đáp án: 3 × (1 + 2) = 9 shard copies. Về dữ liệu, có ba bản sao của mỗi phần dữ liệu; storage gần ba lần primary-only, chưa tính overhead khác.

### Bài 4: Cluster yellow

Cluster health là yellow, tất cả primary đã assigned nhưng một số replica unassigned.

Yêu cầu: nêu ba nguyên nhân cần kiểm tra.

Đáp án:
- Không đủ data node hoặc node offline.
- Disk watermark/capacity không cho phép allocation.
- Zone awareness, allocation filter hoặc replica placement không phù hợp.
Có thể dùng `_cluster/allocation/explain` để xác định nguyên nhân cụ thể.

### Bài 5: Chọn Multi-AZ

Một production domain yêu cầu HA cao và chạy ở Region có ba AZ. Đội muốn dùng Multi-AZ with Standby.

Yêu cầu: nêu các cấu hình chính cần đáp ứng.

Đáp án: ba AZ, ba dedicated cluster manager nodes, data node count là ba hoặc bội số của ba, ít nhất hai replica cho mỗi index và instance/storage type được hỗ trợ.

### Bài 6: Data Stream

Một hệ thống log append-only có trường `@timestamp`. Đội muốn ghi vào một tên ổn định và tự động tạo backing index mới.

Đáp án: Data Stream phù hợp. Tạo index template có `data_stream`, mapping timestamp và settings, sau đó ghi/search qua tên stream và dùng ISM để rollover.

### Bài 7: Cold storage

Một backing index cũ của Data Stream được chuyển sang cold storage. Người dùng không còn thấy dữ liệu đó khi search tên stream.

Đáp án: cold migration detach backing index khỏi Data Stream. Có thể truy vấn index độc lập sau khi attach lại warm theo quy trình hỗ trợ; cần thiết kế lại search path nếu lịch sử phải luôn xuất hiện trong một stream.

### Bài 8: ISM không chạy

Policy chuyển index sang warm sau 30 ngày nhưng index đã 31 ngày và chưa chuyển.

Đáp án: kiểm tra cluster health, ISM explain, policy attachment, action retry, UltraWarm capacity và job interval. ISM không chạy khi cluster state red và action có thể cần thời gian.

## 24. Câu hỏi tự kiểm tra

1. Index và shard khác nhau như thế nào?
2. Primary shard có vai trò gì?
3. Replica shard giúp gì ngoài redundancy?
4. Vì sao replica không phải backup?
5. Mặc định Amazon OpenSearch Service thường tạo bao nhiêu primary và replica cho index?
6. Vì sao không nên tạo quá nhiều shard nhỏ?
7. Kích thước shard tham khảo cho search và log analytics là bao nhiêu?
8. Công thức ước lượng primary shard count gồm những yếu tố nào?
9. Vì sao phải tính cả replica khi ước lượng shard count/node?
10. Cluster green, yellow và red khác nhau như thế nào?
11. Vì sao Multi-AZ without Standby cần replica?
12. Multi-AZ with Standby yêu cầu những cấu hình chính nào?
13. Có thể thay đổi `number_of_shards` trên index hiện hữu trực tiếp không?
14. Khi nào dùng reindex, shrink hoặc split?
15. Data Stream phù hợp loại dữ liệu nào?
16. Rollover tạo ra thay đổi gì đối với write index?
17. ISM gồm state, action và transition như thế nào?
18. Vì sao ISM job không phải lịch chạy chính xác?
19. UltraWarm khác cold storage như thế nào?
20. Vì sao cold migration backing index có thể ảnh hưởng truy vấn Data Stream?
21. Force merge phù hợp khi nào?
22. Snapshot khác replica ở điểm nào?
23. Cần theo dõi metric nào để phát hiện shard skew?
24. Trước khi xóa index cần xác nhận điều gì?

Gợi ý trả lời:

1. Index là tập document logic; shard là phân vùng dữ liệu của index.
2. Lưu phân vùng dữ liệu gốc và nhận indexing operation.
3. Replica có thể phục vụ search và được promote khi primary lỗi.
4. Lỗi logic và thao tác xóa/ghi sai cũng được replication.
5. Năm primary shard và một replica mỗi primary theo default của Amazon OpenSearch Service.
6. Mỗi shard có overhead heap, CPU, metadata và file handle.
7. Search: 10–30 GiB; log/write-heavy: 30–50 GiB.
8. Dung lượng nguồn, tăng trưởng, indexing overhead và shard size mục tiêu.
9. Replica là shard copy tiêu thụ storage/heap và allocation.
10. Green tất cả shard assigned; yellow thiếu replica; red thiếu ít nhất một primary.
11. Để có bản sao dữ liệu ở AZ khác.
12. Ba AZ, ba dedicated masters, data nodes bội số ba, ít nhất hai replica/index và cấu hình được hỗ trợ.
13. Không; cần tạo index mới bằng reindex hoặc dùng shrink/split khi đủ điều kiện.
14. Reindex linh hoạt; shrink giảm shard; split tăng shard.
15. Log, metric, event append-only có timestamp.
16. Tạo backing index/index mới và chuyển write target sang index mới.
17. State là trạng thái, action là thao tác, transition là điều kiện chuyển.
18. Job chạy theo chu kỳ và có jitter; cluster red sẽ không chạy.
19. UltraWarm là read-only S3-backed có cache; cold lưu lịch sử và attach về warm khi cần query.
20. Cold migration detach backing index khỏi Data Stream.
21. Khi index đã read-only để gộp segment, tối ưu query và chuẩn bị warm.
22. Replica là bản sao đồng bộ trong cluster; snapshot là điểm phục hồi dữ liệu.
23. Shard count, storage/node, CPU, JVM, allocation và relocation.
24. Retention, legal hold, snapshot, alias/consumer dependency và approval.

## 25. Tài liệu tham khảo chính thức

- [Choosing the number of shards - Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp-sharding.html)
- [Operational best practices for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp.html)
- [Configuring a multi-AZ domain](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-multiaz.html)
- [Dedicated master nodes](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-dedicatedmasternodes.html)
- [Index State Management in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ism.html)
- [Managing indexes in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managing-indices.html)
- [Managing time-series data with Data Streams](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/data-streams.html)
- [UltraWarm storage](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ultrawarm.html)
- [Cold storage](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cold-storage.html)
- [Creating index snapshots](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-snapshot-create.html)
- [OpenSearch Data Streams](https://docs.opensearch.org/latest/opensearch/data-streams/)
- [OpenSearch Index State Management](https://docs.opensearch.org/latest/im-plugin/ism/)
- [OpenSearch rollover API](https://docs.opensearch.org/latest/api-reference/index-apis/rollover/)
- [OpenSearch shard routing](https://docs.opensearch.org/latest/search-plugins/searching-data/search-shard-routing/)
- [OpenSearch Cluster Allocation Explain API](https://docs.opensearch.org/latest/api-reference/cluster-api/cluster-allocation/)

Tính năng, shard quota, giới hạn instance, engine version và khả năng storage tier thay đổi theo phiên bản/Region. Trước khi triển khai, hãy kiểm tra tài liệu cho đúng domain và benchmark với dữ liệu, truy vấn và retention thực tế.
