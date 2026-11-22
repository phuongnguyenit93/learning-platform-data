# Index not found, alias sai và index bị chặn ghi

Một ứng dụng Spring Data Elasticsearch có thể hoạt động bình thường trong thời gian dài rồi đột nhiên gặp lỗi khi lưu hoặc tìm document. Ba nhóm sự cố thường thấy là **index không tồn tại**, **alias trỏ sai hoặc không xác định được index ghi**, và **index bị chặn ghi**.

Các lỗi này có thể xuất hiện cùng một HTTP status ở một số trường hợp, nhưng nguyên nhân và cách khắc phục rất khác nhau. Ví dụ, lỗi 404 có thể do tên index sai, alias chưa được tạo hoặc ứng dụng đang ghi vào tên index theo ngày chưa tồn tại. Lỗi 403 có thể là quyền truy cập bị từ chối hoặc Elasticsearch đặt index vào trạng thái read-only do dung lượng disk. Một alias trỏ tới nhiều index mà không có write index rõ ràng có thể khiến thao tác ghi thất bại dù các index đích đều tồn tại.

Bài học này trình bày cách phân loại lỗi, kiểm tra index và alias, chẩn đoán write block, cấu hình Spring Data Elasticsearch, khôi phục an toàn và xây dựng integration test để các sự cố được phát hiện sớm.

## 1. Phân biệt ba nhóm sự cố

Trước khi sửa cấu hình, hãy xác định request đang thất bại ở bước nào.

| Nhóm sự cố | Dấu hiệu thường gặp | Câu hỏi cần trả lời |
|---|---|---|
| Index not found | index_not_found_exception, HTTP 404 | Tên index hoặc alias mà request dùng có tồn tại không? |
| Alias sai | Alias không tồn tại, trỏ sai index, hoặc không có write index | Alias đang trỏ tới những index nào và index nào nhận ghi? |
| Index bị chặn ghi | cluster_block_exception, HTTP 403 hoặc lỗi write bị từ chối | Block nào đang bật, ai bật và vì sao? |

Không nên chỉ dựa vào HTTP status. Hãy đọc error.type, error.reason, tên resource trong response và log request. Một lỗi 403 do security_exception cần xử lý quyền; một lỗi 403 do cluster_block_exception cần xử lý block. Tạo lại index không giải quyết được cả hai trường hợp.

### Một luồng chẩn đoán tổng quát

~~~text
Request Spring Data thất bại
           |
           v
Đọc root cause, error.type, status và target
           |
           +---- index_not_found_exception
           |           |
           |           v
           |     Kiểm tra tên index / alias / môi trường
           |
           +---- lỗi alias hoặc write index
           |           |
           |           v
           |     Kiểm tra alias membership và is_write_index
           |
           +---- cluster_block_exception
           |           |
           |           v
           |     Kiểm tra index settings, disk và cluster state
           |
           +---- security_exception
                       |
                       v
                 Kiểm tra identity và privileges
~~~

Lấy đúng target từ request hoặc log là bước quan trọng. Tên trong @Document, alias và IndexCoordinates có thể khác nhau.

## 2. Index not found nghĩa là gì?

Elasticsearch trả lỗi index_not_found_exception khi request tham chiếu đến index hoặc alias không thể resolve trong cluster mà request đang gọi.

Ví dụ:

~~~http
GET /orders/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

Nếu cả index orders lẫn alias orders đều không tồn tại, Elasticsearch không thể thực hiện search.

Các nguyên nhân thường gặp:

- Index chưa được tạo.
- Tên index bị viết sai hoặc khác chữ hoa/thường.
- Ứng dụng dùng sai suffix ngày, tenant hoặc môi trường.
- Alias dự kiến được tạo trong provisioning nhưng bước đó chưa chạy.
- Index vừa bị xóa hoặc rollover/migration chưa hoàn tất.
- Ứng dụng kết nối nhầm cluster.
- Một profile cấu hình khác đang ghi vào endpoint khác.
- Một request dùng tên index cũ sau khi alias đã đổi.

Tên index Elasticsearch phải theo quy tắc đặt tên của Elasticsearch và thường được viết chữ thường. Không giả định tên class Java hoặc tên bảng database được chuyển thành tên index đúng như mong muốn.

### Phân biệt index vật lý và alias

orders-000001 có thể là index vật lý, còn orders-write là alias dùng để ghi. Nếu ứng dụng gửi request tới orders nhưng provisioning chỉ tạo orders-write, request sẽ không tự hiểu hai tên này tương đương.

Hãy kiểm tra target thực tế mà repository hoặc template dùng. Một alias chỉ có tác dụng khi alias đó đã được tạo trong cluster.

## 3. Kiểm tra tên index và alias bằng Elasticsearch API

Các API sau giúp xác định resource đang tồn tại.

Liệt kê index:

~~~http
GET /_cat/indices?v
~~~

Lọc theo prefix:

~~~http
GET /_cat/indices/orders*?v
~~~

Liệt kê alias:

~~~http
GET /_cat/aliases?v
~~~

Xem alias cụ thể:

~~~http
GET /_alias/orders-write
~~~

Ở các phiên bản Elasticsearch hỗ trợ Resolve Index API, có thể dùng:

~~~http
GET /_resolve/index/orders-write
~~~

Resolve Index giúp phân biệt tên được resolve thành concrete index, alias hay data stream. Nếu API này không có trong phiên bản cluster, dùng _cat/indices, _cat/aliases và endpoint alias tương ứng.

Kiểm tra trạng thái index:

~~~http
GET /_cluster/health/orders-000001?level=indices
~~~

Các lệnh này cần quyền monitoring/metadata phù hợp. Nếu API trả 403, đừng kết luận index không tồn tại; identity hiện tại có thể không có quyền xem metadata.

### Dùng HEAD để kiểm tra tồn tại

Có thể kiểm tra index hoặc alias bằng request HEAD:

~~~http
HEAD /orders
~~~

Kết quả thành công cho biết resource có thể được resolve theo endpoint và quyền hiện tại. HEAD không cho biết alias có write index hay không, mapping có đúng hay index có bị chặn ghi hay không.

Vì vậy, kiểm tra tồn tại chỉ là bước đầu, không phải kiểm tra sức khỏe đầy đủ.

## 4. Spring Data Elasticsearch chọn index từ đâu?

Spring Data Elasticsearch có thể lấy tên index từ annotation entity hoặc từ IndexCoordinates được truyền vào Operations.

Ví dụ:

~~~java
@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    private String status;
}
~~~

Khi dùng repository cho entity này, tên index được cấu hình trên @Document là một phần quan trọng trong việc xác định target.

Với Operations, target có thể được chỉ định rõ:

~~~java
operations.save(
    order,
    IndexCoordinates.of("orders")
);
~~~

Nếu ứng dụng dùng alias, orders trong annotation hoặc IndexCoordinates có thể chính là alias. Khi đó alias phải tồn tại và trỏ tới index phù hợp.

### Index động theo tenant hoặc thời gian

Một số ứng dụng chọn index theo tháng, tenant hoặc loại dữ liệu:

~~~java
String indexName = "orders-" + YearMonth.now();
IndexCoordinates coordinates =
    IndexCoordinates.of(indexName);

operations.save(order, coordinates);
~~~

Nếu code tạo suffix orders-2026-11 nhưng index provisioning chỉ tạo orders-2026-10, thao tác sẽ gặp index not found khi auto-create bị tắt hoặc user không có quyền tạo index.

Không nên dựa vào ngày hệ thống ở nhiều nơi để tạo tên index độc lập. Đưa quy tắc chọn index vào một component duy nhất và kiểm thử ranh giới tháng, múi giờ, tenant và môi trường.

### Tạo index tự động có phải cách sửa tốt?

Elasticsearch có thể tự tạo index trong một số cấu hình khi nhận write request tới tên chưa tồn tại. Hành vi này phụ thuộc cluster setting, auto-create policy và quyền của user.

Auto-create có thể che giấu lỗi tên index hoặc tạo index với mapping mặc định không đúng. Với index quan trọng, nên provisioning index template, mapping, settings và alias có chủ đích trước khi ứng dụng ghi dữ liệu.

## 5. Tạo index đúng cách trong Spring Data

Spring Data Elasticsearch cung cấp IndexOperations để kiểm tra, tạo và quản lý index.

Ví dụ:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("orders-000001"));

if (!indexOperations.exists()) {
    indexOperations.create();
}
~~~

Có thể tạo mapping từ entity:

~~~java
IndexOperations indexOperations =
    operations.indexOps(Order.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping()
    );
}
~~~

Chữ ký method và cách tạo mapping phụ thuộc phiên bản Spring Data Elasticsearch. Nếu mapping được quản lý bằng file resource, index template hoặc migration, hãy dùng cùng nguồn cấu hình với môi trường production.

### Tránh race condition khi nhiều instance cùng tạo index

Đoạn exists() rồi create() là hai request riêng. Nếu nhiều instance khởi động cùng lúc, chúng có thể cùng thấy index chưa tồn tại rồi cùng gọi create. Một instance tạo thành công, instance còn lại có thể nhận resource-already-exists.

Không nên coi lỗi này là lỗi dữ liệu nghiêm trọng nếu index đã được tạo đúng. Tuy nhiên, cần xử lý idempotent và xác nhận mapping/settings hiện tại tương thích thay vì bỏ qua mọi exception.

Một quy trình provisioning tập trung hoặc migration job có kiểm soát thường dễ vận hành hơn việc mỗi application instance tự tạo index trong production.

### @Document(createIndex = false)

Tùy phiên bản Spring Data Elasticsearch, @Document hỗ trợ tùy chọn kiểm soát việc tạo index tự động khi repository infrastructure khởi tạo. Nếu ứng dụng dùng provisioning riêng, có thể tắt việc tự tạo index để tránh tạo resource ngoài kế hoạch.

Dù dùng tùy chọn nào, ứng dụng vẫn cần bảo đảm index/alias tồn tại trước khi thực hiện request. Tắt auto-create không tự tạo index; nó chỉ thay đổi hành vi khởi tạo.

## 6. Alias dùng để làm gì?

Alias là tên logic trỏ tới một hoặc nhiều index vật lý. Ứng dụng có thể tiếp tục dùng alias ổn định trong khi index đích được thay đổi theo version hoặc rollover.

Ví dụ:

~~~text
orders-read  -> orders-000001, orders-000002
orders-write -> orders-000002
~~~

- orders-read là alias đọc có thể trỏ tới nhiều index.
- orders-write là alias ghi trỏ tới index hiện hành.
- orders-000001 và orders-000002 là index vật lý.

Lợi ích của alias:

- Ứng dụng không cần biết index version cụ thể.
- Có thể reindex sang index mới rồi chuyển alias.
- Có thể đọc dữ liệu từ nhiều index.
- Có thể tách read alias và write alias để thể hiện rõ mục đích.
- Có thể thực hiện chuyển đổi alias trong một request _aliases nguyên tử.

Alias không phải index vật lý và không chứa document riêng. Nó là một tên định tuyến tới index.

## 7. Alias trỏ tới nhiều index và write index

Một alias có thể trỏ tới nhiều index để search. Nhưng khi ghi, Elasticsearch cần biết index nào là đích.

Ví dụ alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-000001",
        "alias": "orders"
      }
    },
    {
      "add": {
        "index": "orders-000002",
        "alias": "orders"
      }
    }
  ]
}
~~~

Alias orders hiện trỏ tới hai index. Nếu không có write index được xác định rõ, thao tác ghi qua alias có thể thất bại vì Elasticsearch không biết index nào nhận document.

Đặt write index tường minh:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-000001",
        "alias": "orders",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "orders-000002",
        "alias": "orders",
        "is_write_index": true
      }
    }
  ]
}
~~~

Khi đó, write request tới alias orders được gửi tới orders-000002. Search qua alias vẫn có thể đọc cả hai index.

Nếu alias chỉ trỏ tới một index, Elasticsearch có thể mặc định index đó là write index trong những trường hợp phù hợp. Dù vậy, với alias phục vụ nhiều index, khai báo is_write_index rõ ràng giúp tránh sự mơ hồ.

### Dấu hiệu alias thiếu write index

Lỗi thường có nội dung cho biết không có write index được xác định cho alias hoặc alias không thể dùng làm write target. HTTP status và exception wrapper có thể khác theo API/client version.

Khi gặp lỗi này:

1. Kiểm tra alias có tồn tại.
2. Liệt kê tất cả index mà alias trỏ tới.
3. Kiểm tra is_write_index.
4. Xác nhận index được chọn là index mới nhất hoặc đúng index theo nghiệp vụ.
5. Sửa alias một cách nguyên tử sau khi xác nhận dữ liệu và mapping.

Không giải quyết bằng cách đổi tên @Document sang tên index vật lý nếu kiến trúc dự định dùng alias ổn định.

## 8. Đọc alias và write alias nên tách biệt

Một thiết kế phổ biến:

~~~text
Application
   |
   +---- Search / get collection ----> orders-read
   |
   +---- Index / update / delete ----> orders-write
                                          |
                                          v
                                    orders-000042
~~~

Tách alias giúp thể hiện mục đích và giảm nguy cơ một query ghi vô tình dùng alias đọc nhiều index.

Ví dụ cấu hình:

- orders-read: trỏ tới các index còn được giữ để tìm kiếm.
- orders-write: trỏ tới đúng một index nhận ghi.
- orders-000042: index vật lý mới nhất.

Với repository entity dùng một indexName, có thể cấu hình alias mà repository sẽ dùng theo pattern của ứng dụng. Nếu cần read/write alias khác nhau, có thể dùng custom repository fragment hoặc service dùng ElasticsearchOperations với IndexCoordinates riêng cho từng thao tác.

Không mặc định mọi method của repository có thể tự chọn hai alias khác nhau từ một annotation duy nhất. Hãy xác định rõ đường đọc và đường ghi trong thiết kế repository.

## 9. Chuyển alias nguyên tử khi tạo index mới

Khi reindex hoặc rollover thủ công, không nên xóa alias trước rồi mới thêm alias sau bằng hai request tách biệt. Trong khoảng trống đó, ứng dụng có thể nhận index not found.

Elasticsearch hỗ trợ nhiều action trong một _aliases request. Ví dụ chuyển orders-write từ index cũ sang index mới:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "orders-000001",
        "alias": "orders-write"
      }
    },
    {
      "add": {
        "index": "orders-000002",
        "alias": "orders-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Các thay đổi alias trong cùng request được áp dụng nguyên tử ở cluster state. Ứng dụng không phải quan sát một khoảng thời gian alias bị xóa hoàn toàn giữa hai bước.

### Trình tự cutover an toàn

1. Tạo index mới với mapping và settings mong muốn.
2. Xác nhận index mới tồn tại và mapping đúng.
3. Reindex hoặc nạp dữ liệu cần thiết.
4. Đối soát số lượng và dữ liệu quan trọng.
5. Chuyển alias trong một _aliases request.
6. Kiểm tra read/write alias sau cutover.
7. Chỉ xóa index cũ khi chính sách lưu trữ cho phép và đã xác nhận không còn cần rollback.

Nếu có ghi đồng thời trong lúc reindex, cần một chiến lược đồng bộ dữ liệu thay đổi phát sinh trong thời gian chuyển đổi. Chỉ copy snapshot rồi chuyển alias có thể làm mất các cập nhật đến sau snapshot.

## 10. Rollover và alias ghi

Rollover tạo index mới khi index hiện tại đạt điều kiện như tuổi hoặc dung lượng. Một write alias được dùng làm điểm ghi ổn định.

Ví dụ tạo write alias:

~~~http
PUT /orders-000001
{
  "aliases": {
    "orders-write": {
      "is_write_index": true
    },
    "orders-read": {}
  }
}
~~~

Gọi rollover:

~~~http
POST /orders-write/_rollover
{
  "conditions": {
    "max_age": "30d",
    "max_primary_shard_size": "40gb"
  }
}
~~~

Elasticsearch tạo index tiếp theo theo naming convention và chuyển write alias sang index mới nếu điều kiện được đáp ứng. Các điều kiện rollover được hỗ trợ tùy phiên bản và loại index; kiểm tra tài liệu cluster thực tế.

Sau rollover, xác nhận alias:

~~~http
GET /_cat/aliases/orders-write?v
~~~

Nếu ứng dụng ghi vào alias nhưng alias không được chuyển đúng, nó có thể tiếp tục ghi index cũ hoặc gặp lỗi write target. Không chỉ kiểm tra index mới đã được tạo; hãy kiểm tra alias thực sự trỏ tới đâu.

## 11. Index bị chặn ghi là gì?

Elasticsearch có index block để ngăn một số hoạt động khi cần bảo vệ cluster hoặc dữ liệu. Các block thường gặp:

| Setting | Tác động khái quát |
|---|---|
| index.blocks.write | Chặn thao tác ghi vào index |
| index.blocks.read_only | Đặt index ở chế độ chỉ đọc |
| index.blocks.read_only_allow_delete | Chặn ghi thông thường nhưng cho phép xóa theo semantics của block |
| index.blocks.metadata | Chặn một số thao tác metadata |
| index.blocks.read | Chặn thao tác đọc |

Tác động chính xác và API quản lý phụ thuộc Elasticsearch version. Trong sự cố write, ba setting đầu là những setting cần kiểm tra trước.

Một block có thể được operator bật thủ công để bảo vệ index trong quá trình bảo trì. Nó cũng có thể được Elasticsearch tự động đặt khi disk vượt flood-stage watermark.

### Dấu hiệu trong response

Ví dụ lỗi có thể cho biết index bị read-only hoặc bị chặn do flood-stage disk watermark:

~~~json
{
  "error": {
    "type": "cluster_block_exception",
    "reason": "blocked by: [FORBIDDEN/12/index read-only / allow delete (api)];"
  },
  "status": 403
}
~~~

Thông điệp cụ thể thay đổi theo phiên bản và nguyên nhân. Hãy giữ nguyên error.type và error.reason trong log để phân loại chính xác.

## 12. Disk flood-stage có thể tự đặt read-only block

Elasticsearch theo dõi mức sử dụng disk trên các node. Khi disk vượt các watermark, cluster có thể ngừng cấp shard mới hoặc chuyển index vào trạng thái read-only để tránh hết disk.

Flood-stage watermark là ngưỡng bảo vệ nghiêm trọng. Khi node vượt ngưỡng này, Elasticsearch có thể tự động đặt index.blocks.read_only_allow_delete trên các index có shard nằm trên node bị ảnh hưởng.

Vì vậy, một ứng dụng có thể đột nhiên không ghi được dù code không thay đổi.

### Quy trình xử lý đúng

1. Kiểm tra disk usage của các node.
2. Xác định node và shard đang vượt watermark.
3. Giải phóng hoặc mở rộng dung lượng theo quy trình vận hành.
4. Chờ Elasticsearch cập nhật trạng thái watermark.
5. Kiểm tra index settings và block còn tồn tại hay không.
6. Chỉ gỡ block sau khi nguyên nhân đã được xử lý và theo policy vận hành.
7. Thử một thao tác ghi nhỏ có kiểm soát rồi theo dõi cluster.

Không chỉ xóa block khi disk vẫn đầy. Elasticsearch có thể đặt block lại hoặc cluster tiếp tục gặp lỗi nghiêm trọng.

### Kiểm tra disk

Có thể dùng:

~~~http
GET /_cat/nodes?v&h=name,disk.used_percent,disk.avail,disk.total
~~~

Xem allocation theo node:

~~~http
GET /_cat/allocation?v
~~~

Tên cột và metric phụ thuộc version. Có thể kết hợp với monitoring của hạ tầng để xem disk theo thời gian, tốc độ tăng và dung lượng còn trống.

## 13. Kiểm tra index block settings

Xem settings của index:

~~~http
GET /orders-000001/_settings?flat_settings=true
~~~

Có thể lọc các block settings:

~~~http
GET /orders-000001/_settings/index.blocks.*?flat_settings=true
~~~

Nếu index có index.blocks.write: true hoặc index.blocks.read_only: true, thao tác ghi có thể bị từ chối.

Một số block được bật ở cluster hoặc theo policy khác. Nếu index settings không cho thấy nguyên nhân, hãy xem cluster settings, audit log, operator automation và error reason đầy đủ.

### Gỡ block sau khi xác nhận nguyên nhân

Ví dụ gỡ read-only-allow-delete block:

~~~http
PUT /orders-000001/_settings
{
  "index.blocks.read_only_allow_delete": null
}
~~~

Gỡ write block do operator đặt:

~~~http
PUT /orders-000001/_settings
{
  "index.blocks.write": null
}
~~~

Gỡ read-only block:

~~~http
PUT /orders-000001/_settings
{
  "index.blocks.read_only": null
}
~~~

Dùng đúng setting đang được bật và đúng index. Không gửi tất cả setting về false một cách máy móc nếu block được quản lý bởi cluster policy hoặc cơ chế tự động. Với flood-stage, giải phóng disk trước rồi mới kiểm tra việc gỡ block.

## 14. Phân biệt block với lỗi quyền truy cập

Cả block và quyền truy cập có thể trả HTTP 403, nhưng cách xử lý khác nhau.

| Error type / reason | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| cluster_block_exception | Index hoặc cluster đang chặn thao tác | Kiểm tra block settings, disk và policy |
| security_exception | User/API key không có privilege | Kiểm tra role và index privileges |
| index_not_found_exception | Không resolve được index hoặc alias | Kiểm tra tên, alias, cluster |
| Lỗi write index alias | Alias không xác định được index nhận ghi | Kiểm tra alias membership và is_write_index |
| mapper_parsing_exception | Payload không phù hợp mapping | Kiểm tra field và mapping |

Không cấp thêm quyền rộng hơn chỉ để khắc phục cluster_block_exception. Cũng không gỡ block khi lỗi thật sự là security_exception.

### Kiểm tra quyền

Elasticsearch security API có thể giúp xác định user hiện tại và privileges nếu identity có quyền gọi API tương ứng. Ví dụ:

~~~http
GET /_security/_authenticate
~~~

Kiểm tra quyền cụ thể cần API và privileges phù hợp với phiên bản security đang dùng. Với ứng dụng Spring, xác nhận credential đang được dùng bởi đúng profile và client bean, không chỉ credential của người vận hành gọi Kibana.

## 15. Chẩn đoán từ Spring Data exception

Spring Data Elasticsearch dùng Elasticsearch Java API Client và cơ chế exception translation của Spring. Exception ứng dụng nhận được có thể là exception từ client hoặc một DataAccessException/exception Spring bao quanh nguyên nhân.

Không nên chỉ log exception.getMessage() rồi bỏ qua cause. Hãy ghi nhận:

- Operation đang chạy: index, save, search, update, delete hay bulk.
- Target index/alias.
- Document ID nếu phù hợp.
- HTTP status.
- Elasticsearch error.type.
- Elasticsearch error.reason.
- Root cause class.
- Correlation ID hoặc job ID.
- Profile/cluster identity (không ghi secret).

Ví dụ xử lý ở service:

~~~java
try {
    return repository.save(order);
} catch (DataAccessException ex) {
    Throwable rootCause = NestedExceptionUtils.getMostSpecificCause(ex);

    log.error(
        "Unable to save order to Elasticsearch: {}",
        rootCause.getMessage(),
        ex
    );

    throw ex;
}
~~~

Đây là ví dụ logging tối giản. Trong ứng dụng thực tế, adapter hoặc exception handler nên trích xuất status và Elasticsearch error type từ cause phù hợp với client version. Không parse message string bằng một regex mong manh nếu có thể đọc typed exception hoặc structured response.

### Đừng retry mọi lỗi

- Index not found: retry ngay thường không giúp nếu provisioning chưa tạo resource.
- Alias thiếu write index: retry không sửa alias.
- Read-only block: retry làm tăng tải và tiếp tục thất bại.
- Security exception: retry không cấp quyền.
- Lỗi mapping: retry cùng payload vẫn lỗi.
- Timeout tạm thời: có thể retry theo policy, nhưng cần idempotency và giới hạn số lần thử.

Phân loại lỗi trước khi quyết định retry, tạo index, chuyển alias hoặc dừng job.

## 16. Thiết kế startup check cho ứng dụng

Ứng dụng có thể kiểm tra các điều kiện cần thiết khi khởi động hoặc trong readiness check:

- Cluster endpoint có phản hồi.
- Index/alias bắt buộc resolve được.
- Alias ghi có đúng write index.
- Mapping cần thiết tồn tại.
- Index không bị block ghi nếu service cần ghi.
- Service account có quyền cần thiết.
- Index template và lifecycle policy phù hợp.

Không nên tự động xóa block hoặc tự ý tạo lại index trong startup check. Startup check nên phát hiện và báo lỗi có ngữ cảnh. Việc sửa trạng thái cluster cần thuộc quy trình provisioning/operations được kiểm soát.

### Readiness khác liveness

Nếu Elasticsearch tạm thời không khả dụng, readiness có thể đánh dấu instance không nhận traffic phụ thuộc Elasticsearch. Liveness nên phản ánh process còn sống hay không; không nhất thiết restart liên tục ứng dụng chỉ vì cluster tạm thời mất kết nối.

Nếu mọi replica đều restart do Elasticsearch lỗi, hệ thống có thể tạo thêm connection storm khi cluster phục hồi.

### Health indicator

Spring Boot Actuator có thể cung cấp health indicator cho Elasticsearch tùy starter và phiên bản. Có thể dùng custom health indicator để kiểm tra alias hoặc index quan trọng ngoài việc kiểm tra kết nối cluster.

Health check không nên thực hiện thao tác ghi thật trên mỗi lần probe. Dùng metadata/read-only checks hoặc một canary strategy có kiểm soát nếu cần kiểm tra write path.

## 17. Quản lý index và alias bằng provisioning

Đối với production, nên quản lý index lifecycle bằng một quy trình có chủ đích:

1. Tạo index template với settings và mappings.
2. Tạo index vật lý hoặc để rollover tạo theo policy.
3. Tạo read/write alias.
4. Xác nhận is_write_index.
5. Cấp quyền đúng cho service account.
6. Kiểm tra index block và cluster health.
7. Cho phép ứng dụng nhận traffic.

Có thể thực hiện provisioning bằng deployment job, migration tool hoặc infrastructure automation. Ứng dụng runtime chỉ cần dùng alias ổn định và báo lỗi rõ ràng nếu resource chưa sẵn sàng.

### Không để nhiều instance tranh nhau quản lý alias

Nếu mỗi instance tự tạo index và sửa alias khi startup, nhiều instance có thể chạy các thao tác không đồng bộ. Điều này dễ dẫn đến alias trỏ sai hoặc chuyển write index ngoài ý muốn.

Một migration/provisioning job có ownership rõ ràng giúp thay đổi index và alias có thể kiểm tra, audit và rollback.

## 18. Integration test cho index not found và alias

Các test nên dùng Elasticsearch thật hoặc Testcontainers tương thích để xác nhận hành vi alias.

### Test index không tồn tại

- Tạo index test khác tên target.
- Gọi search hoặc write vào target không tồn tại.
- Xác nhận ứng dụng nhận lỗi phù hợp.
- Không tự tạo index ngoài policy của test.

Nếu auto-create đang bật, cần tắt trong test cluster hoặc dùng user không có quyền auto-create để test đúng tình huống index not found.

### Test alias trỏ tới một index

- Tạo orders-000001.
- Tạo alias orders-write với is_write_index: true.
- Ghi qua alias.
- Xác nhận document xuất hiện trong index vật lý.

### Test alias trỏ tới nhiều index

- Tạo hai index vật lý.
- Tạo alias đọc trỏ tới cả hai.
- Xác nhận search qua alias đọc thấy document ở cả hai.
- Tạo alias ghi hoặc cấu hình write index rõ ràng.
- Kiểm tra trường hợp alias nhiều index không có write index và xác nhận lỗi.

### Test chuyển alias

- Tạo index cũ và index mới.
- Gắn alias ghi vào index cũ.
- Thực hiện _aliases remove/add trong một request.
- Ghi qua alias sau cutover.
- Xác nhận document mới vào index mới và dữ liệu cũ vẫn đọc được qua read alias theo thiết kế.

## 19. Integration test cho write block

Test có thể bật block trên index test:

~~~http
PUT /orders-test/_settings
{
  "index.blocks.write": true
}
~~~

Sau đó thử một thao tác save và xác nhận request thất bại với nguyên nhân block.

Gỡ block khi kết thúc test:

~~~http
PUT /orders-test/_settings
{
  "index.blocks.write": null
}
~~~

Test nên dùng index riêng và đảm bảo cleanup ngay cả khi assertion thất bại. Không bật block trên index chia sẻ với test khác.

Đối với read_only_allow_delete do flood-stage, không nên giả lập flood-stage bằng cách làm đầy disk trong CI. Có thể kiểm tra xử lý exception của ứng dụng bằng fixture/error mapping, còn semantics block nên được kiểm tra trên một môi trường Elasticsearch riêng có thể kiểm soát.

### Test phân biệt 403 block và 403 security

Tạo một test cho index block và một test cho user thiếu privilege. Xác nhận ứng dụng phân loại đúng error type, không biến cả hai thành cùng một thông báo “không tìm thấy index”.

## 20. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| index_not_found_exception khi save | Index/alias chưa tồn tại hoặc sai target | Resolve tên và kiểm tra provisioning |
| Chỉ một profile bị 404 | Endpoint hoặc suffix index khác môi trường | So sánh effective configuration và cluster |
| Alias tồn tại nhưng ghi thất bại | Alias trỏ nhiều index nhưng thiếu write index | Đặt is_write_index tường minh |
| Ghi vào index cũ sau rollover | Write alias chưa chuyển | Kiểm tra alias và rollover result |
| HTTP 403 khi ghi | Block hoặc security privilege | Đọc error.type và reason |
| cluster_block_exception sau disk pressure | Flood-stage đặt read-only-allow-delete | Giải phóng disk, kiểm tra rồi gỡ block |
| security_exception | Service account thiếu index privilege | Cấp đúng quyền tối thiểu |
| Index tự tạo với mapping sai | Auto-create che giấu lỗi provisioning | Dùng template và quản lý index chủ động |
| Startup tạo index thất bại ngẫu nhiên | Nhiều instance cùng chạy exists/create | Dùng provisioning một lần và xử lý create race |
| Search qua alias thiếu dữ liệu cũ | Read alias không trỏ đủ index | Kiểm tra membership và cutover |
| Repository dùng sai index | @Document hoặc IndexCoordinates sai | Kiểm tra target thực tế trong log |
| Gỡ block nhưng lỗi quay lại | Nguyên nhân disk hoặc policy chưa được xử lý | Xử lý root cause trước khi gỡ |
| Test pass nhưng production 404 | Test dùng index riêng đã được tạo sẵn | Kiểm tra provisioning và alias trong production-like setup |

## 21. Runbook xử lý sự cố theo thứ tự

Khi ứng dụng báo không thể ghi document:

**Bước 1 — Giữ lại lỗi gốc.** Ghi operation, target, status, error.type và error.reason. Không chỉ ghi message đã được bọc ở service layer.

**Bước 2 — Xác định cluster.** Kiểm tra endpoint và profile mà instance đang dùng. Một index có thể tồn tại ở staging nhưng không tồn tại ở production.

**Bước 3 — Resolve target.** Kiểm tra tên đó là index, alias hay data stream. Liệt kê alias membership và write index.

**Bước 4 — Kiểm tra index state.** Xem index có open không, mapping/settings có phù hợp không và block nào đang bật.

**Bước 5 — Kiểm tra disk và allocation.** Nếu có read-only block, kiểm tra disk watermark, node và allocation trước khi thay đổi setting.

**Bước 6 — Kiểm tra quyền.** Xác nhận service identity có quyền cần thiết trên index hoặc alias target.

**Bước 7 — Sửa đúng nguyên nhân.** Tạo resource theo template, sửa alias atomically, cấp quyền tối thiểu hoặc xử lý disk rồi gỡ block theo quy trình.

**Bước 8 — Xác nhận cả write và read.** Ghi một document kiểm thử có ID xác định, đọc lại theo ID hoặc search sau refresh, rồi kiểm tra document nằm ở index vật lý dự kiến.

**Bước 9 — Theo dõi sau phục hồi.** Theo dõi lỗi 404/403, indexing rejection, disk usage và alias target để xác nhận sự cố không tái diễn.

Không xóa index hoặc xóa block chỉ để làm lỗi biến mất. Những hành động đó có thể gây mất dữ liệu hoặc che giấu nguyên nhân ban đầu.

## 22. Checklist vận hành

- [ ] Tên index/alias được quản lý tập trung.
- [ ] Endpoint và profile của từng môi trường được kiểm tra.
- [ ] Index template, mapping và settings được provision trước khi ghi.
- [ ] Ứng dụng biết rõ đang ghi vào index vật lý hay write alias.
- [ ] Alias đọc và ghi có mục đích rõ ràng.
- [ ] Alias nhiều index có is_write_index tường minh.
- [ ] Rollover chuyển write alias đúng index mới.
- [ ] Alias cutover dùng một _aliases request nguyên tử.
- [ ] Có kiểm tra index/alias bắt buộc trong readiness hoặc startup validation.
- [ ] Log giữ lại status, error.type, error.reason và target.
- [ ] Phân biệt cluster_block_exception với security_exception.
- [ ] Theo dõi disk watermark và index block settings.
- [ ] Chỉ gỡ read-only block sau khi nguyên nhân đã được xử lý.
- [ ] Không retry mù lỗi index not found, alias hoặc write block.
- [ ] Có integration test cho index missing và alias write index.
- [ ] Có test chuyển alias và kiểm tra dữ liệu sau cutover.
- [ ] Có test phân biệt write block và thiếu privilege.
- [ ] Test dùng index riêng, không tác động dữ liệu dùng chung.
- [ ] Không để nhiều application instance tranh nhau provisioning index/alias.

Index not found, alias sai và write block đều làm request Elasticsearch thất bại, nhưng mỗi lỗi cần một cách xử lý riêng. Hãy xác định chính xác target mà Spring Data đang dùng, kiểm tra alias membership và write index, đọc block settings cùng disk state, rồi mới thay đổi cluster. Provisioning index có mapping rõ ràng, alias đọc/ghi tách biệt, cutover nguyên tử và log có structured error details giúp ứng dụng tránh lỗi cấu hình âm thầm và khôi phục an toàn khi Elasticsearch từ chối thao tác.

