# Cluster, node, shard và replica

Elasticsearch được thiết kế để lưu trữ và tìm kiếm dữ liệu phân tán trên nhiều máy hoặc nhiều tiến trình. Một ứng dụng Spring Data Elasticsearch thường làm việc với Elasticsearch thông qua HTTP client và các abstraction như `ElasticsearchRepository` hoặc `ElasticsearchOperations`. Để hiểu dữ liệu được lưu ở đâu, request được xử lý thế nào và hệ thống chịu lỗi ra sao, cần phân biệt bốn khái niệm: **cluster**, **node**, **shard** và **replica**.

Quan hệ tổng quát:

```text
Spring Data Elasticsearch application
              |
              | HTTP request
              v
       Elasticsearch cluster
       +----------------------+
       | Node A               |
       |   Primary shard 0    |
       |   Replica shard 2    |
       +----------------------+
       | Node B               |
       |   Primary shard 1    |
       |   Replica shard 0    |
       +----------------------+
       | Node C               |
       |   Primary shard 2    |
       |   Replica shard 1    |
       +----------------------+
```

Trong sơ đồ, cluster là toàn bộ hệ thống Elasticsearch; mỗi node là một tiến trình tham gia cluster; index là tập dữ liệu logic; shard chia index thành các phần nhỏ; replica là bản sao của primary shard để tăng khả năng chịu lỗi và phục vụ đọc.

## 1. Cluster là gì?

**Cluster** là một nhóm các node Elasticsearch phối hợp với nhau và được nhìn nhận như một hệ thống tìm kiếm thống nhất. Ứng dụng có thể gửi request đến một node trong cluster; Elasticsearch sẽ định tuyến request đến node và shard phù hợp.

Một cluster có một số đặc điểm chính:

- Có tên cluster (`cluster.name`) và định danh cluster riêng.
- Quản lý danh sách node đang tham gia, các index, metadata, cấu hình và vị trí các shard.
- Phân phối shard trên các node theo trạng thái tài nguyên và các quy tắc phân bổ.
- Theo dõi tình trạng hoạt động của primary shard và replica shard.
- Có thể tiếp tục cung cấp dữ liệu khi một node gặp sự cố, nếu các shard cần thiết còn bản sao đang hoạt động ở node khác.

Cluster state là trạng thái metadata mà các node cần thống nhất, chẳng hạn danh sách index, mapping, settings, node membership và shard routing table. Một node có vai trò master được bầu sẽ chịu trách nhiệm điều phối các thay đổi của cluster state. Master không phải là nơi bắt buộc xử lý mọi truy vấn tìm kiếm hay ghi dữ liệu; các node khác vẫn có thể nhận và xử lý request.

Trong môi trường nhiều node, Elasticsearch dùng cơ chế discovery và bầu chọn master để các node tìm thấy nhau và duy trì một cluster nhất quán. Việc hai tiến trình có cùng `cluster.name` chưa đủ để bảo đảm chúng tham gia đúng cluster: discovery, địa chỉ mạng, cấu hình bảo mật và các điều kiện kết nối cũng phải phù hợp.

Ví dụ, một môi trường có thể có cluster tên `product-search` gồm ba node. Với ứng dụng Spring Data, cấu hình client trỏ đến một hoặc nhiều địa chỉ HTTP của các node này. Khi topology thay đổi, Elasticsearch cập nhật routing và việc phân phối shard; ứng dụng vẫn thao tác trên index logic đã cấu hình.

## 2. Node là gì?

**Node** là một tiến trình Elasticsearch đang chạy. Một node tham gia cluster, nhận request, lưu shard hoặc thực hiện một số nhiệm vụ quản lý tùy theo role được cấu hình.

Các node trong cùng cluster có thể có tên và vai trò khác nhau. Một số role thường gặp:

| Role | Trách nhiệm chính |
|---|---|
| Master-eligible | Có thể tham gia bầu chọn và trở thành master để quản lý cluster state. |
| Data | Lưu shard và thực hiện các thao tác đọc, ghi, tìm kiếm trên dữ liệu. Elasticsearch có các biến thể như `data_hot`, `data_warm`, `data_cold` và `data_frozen` cho các tầng lưu trữ khác nhau. |
| Ingest | Thực thi ingest pipeline để xử lý tài liệu trước khi lập chỉ mục. |
| Machine learning hoặc transform | Cung cấp các tác vụ chuyên biệt tương ứng khi tính năng đó được sử dụng. |
| Coordinating | Nhận request, phân phối request đến các shard liên quan và tổng hợp kết quả trả về. Khả năng điều phối có sẵn trên mọi node; một coordinating-only node thường được cấu hình không có role chuyên biệt khác. |

Một node có thể đảm nhiệm nhiều role. Với cluster nhỏ hoặc môi trường phát triển, một node thường kiêm nhiều nhiệm vụ. Với hệ thống lớn, có thể tách các node master-eligible, data và ingest để giới hạn mức cạnh tranh tài nguyên và giúp vận hành dễ dự đoán hơn.

Ví dụ cấu hình một node có thể chứa các thông tin như:

```yaml
cluster.name: product-search
node.name: search-data-01
network.host: 0.0.0.0
http.port: 9200
```

Đây chỉ là các thuộc tính nhận diện và kết nối cơ bản. Cấu hình discovery, bảo mật, role và các thiết lập triển khai cần được bổ sung phù hợp với môi trường thực tế. Không nên sao chép nguyên cấu hình phát triển sang production.

### Node phối hợp xử lý request

Node nhận request ban đầu thường đóng vai trò coordinating node cho request đó. Nó xác định shard đích, gửi phần việc đến các node đang giữ shard, nhận kết quả và tổng hợp phản hồi. Vì vậy, ứng dụng không cần tự tìm node nào đang giữ một tài liệu cụ thể.

Nếu client cấu hình nhiều địa chỉ node, client có thể phân phối kết nối hoặc request theo cơ chế của thư viện đang dùng. Dù request đến node nào, Elasticsearch vẫn chịu trách nhiệm định tuyến đến shard phù hợp.

## 3. Index và shard

**Index** là một tập hợp tài liệu có cùng mục đích lưu trữ và thường chia sẻ mapping, settings. Có thể hình dung index gần với một bảng dữ liệu ở mức khái niệm, nhưng Elasticsearch không phải cơ sở dữ liệu quan hệ: cách lưu trữ, truy vấn và phân phối dữ liệu khác nhau.

Một index có thể chứa lượng dữ liệu lớn. Nếu chỉ lưu toàn bộ index trên một node, khả năng mở rộng và chịu lỗi sẽ bị giới hạn. Elasticsearch giải quyết vấn đề này bằng cách chia index thành các **primary shard**.

**Shard** là một phân vùng dữ liệu độc lập của index. Về mặt lưu trữ, mỗi shard là một Lucene index riêng. Elasticsearch phân phối các shard trên các node để nhiều node có thể cùng lưu trữ và xử lý dữ liệu của một index.

Ví dụ index `products` có ba primary shard:

```text
Index: products
  ├── Primary shard 0
  ├── Primary shard 1
  └── Primary shard 2
```

### Elasticsearch chọn shard nào?

Khi ghi một document, Elasticsearch cần xác định document thuộc primary shard nào. Mặc định, hệ thống dùng giá trị `_id` kết hợp với số lượng primary shard để tính shard đích. Nếu ứng dụng dùng custom routing, giá trị routing được dùng thay cho `_id` trong phép xác định đó.

Nhờ cơ chế routing, các request đọc hoặc ghi một document có thể được chuyển thẳng đến shard phù hợp mà không cần quét toàn bộ index. Khi tìm kiếm trên index mà không chỉ rõ routing, request thường được gửi đến các shard liên quan; các shard thực hiện tìm kiếm rồi node điều phối hợp nhất kết quả.

### Số lượng primary shard

Số primary shard được thiết lập khi tạo index thông qua setting `number_of_shards`. Đây là quyết định ảnh hưởng lâu dài đến cách dữ liệu được phân vùng. Không thể chỉ thay đổi setting này như thay đổi số replica trên một index đang tồn tại. Khi cần cấu trúc primary shard khác, các hướng xử lý thường là tạo index mới rồi reindex dữ liệu, hoặc dùng thao tác split/shrink khi đáp ứng các điều kiện tương ứng.

Chọn quá ít shard có thể giới hạn khả năng phân phối dữ liệu và xử lý song song. Chọn quá nhiều shard làm tăng chi phí metadata, bộ nhớ, file handle và công việc quản lý trên cluster. Số shard phù hợp phụ thuộc vào dung lượng dữ liệu dự kiến, kích thước shard, tốc độ ghi/đọc, số node và khả năng mở rộng trong tương lai; không có một con số đúng cho mọi index.

## 4. Primary shard và replica shard

Trong mỗi nhóm shard của một index, **primary shard** là bản shard chính nhận thao tác ghi ban đầu. **Replica shard** là bản sao của primary shard tương ứng.

Nếu một index có ba primary shard và mỗi primary có một replica, cấu trúc logic là:

```text
products
  ├── Primary shard 0  ── Replica shard 0
  ├── Primary shard 1  ── Replica shard 1
  └── Primary shard 2  ── Replica shard 2
```

Elasticsearch cố gắng đặt replica trên node khác với primary tương ứng. Nhờ đó, khi node đang giữ primary bị mất, một replica đang hoạt động trên node khác có thể được nâng thành primary mới.

### Luồng ghi dữ liệu

Một luồng ghi điển hình diễn ra như sau:

1. Ứng dụng gửi yêu cầu index, update hoặc delete document đến một node Elasticsearch.
2. Node nhận request xác định primary shard dựa trên routing.
3. Request được chuyển đến node đang giữ primary shard đó.
4. Primary thực hiện thao tác và chuyển thay đổi đến các replica đang thuộc nhóm bản sao hợp lệ (in-sync copies).
5. Elasticsearch trả kết quả theo điều kiện xác nhận của request và trạng thái các bản sao liên quan.

Do đó, ứng dụng Spring Data chỉ cần gọi repository hoặc operations API. Ứng dụng không tự chọn node lưu document và cũng không gửi cùng một thao tác đến từng replica.

### Luồng đọc và tìm kiếm

Với thao tác lấy một document, Elasticsearch có thể chọn một bản shard đang hoạt động trong nhóm primary/replica để phục vụ request. Với tìm kiếm trên nhiều shard, node điều phối gửi phần truy vấn đến các shard liên quan, nhận kết quả từng phần và hợp nhất chúng trước khi trả về ứng dụng.

Replica có thể giúp tăng khả năng phục vụ đọc, đặc biệt khi có nhiều request tìm kiếm. Tuy nhiên, replica không có nghĩa mọi truy vấn sẽ nhanh hơn trong mọi trường hợp: hiệu quả còn phụ thuộc số lượng shard, tài nguyên node, kiểu truy vấn, cache, tải ghi và cách phân phối request.

### Replica có phải bản sao lưu không?

Không. Replica giúp cluster duy trì khả năng phục vụ khi một node chứa shard gặp sự cố và có thể tăng năng lực đọc. Replica vẫn thuộc cùng cluster và chịu tác động của các thao tác xóa hoặc thay đổi dữ liệu. Nếu index bị xóa nhầm hoặc dữ liệu bị ghi sai, replica cũng phản ánh thay đổi đó.

Để sao lưu và khôi phục dữ liệu, cần dùng snapshot repository và quy trình snapshot/restore phù hợp. Không nên xem replica là phương án backup.

### Số lượng replica

Số replica của một index được cấu hình bằng `number_of_replicas`. Khác với số primary shard, số replica có thể thay đổi sau khi index đã được tạo. Tăng replica tạo thêm bản sao dữ liệu và cần dung lượng lưu trữ, CPU, bộ nhớ cùng băng thông mạng cho việc đồng bộ và phục hồi shard.

Một replica không thể được đặt trên cùng node với primary tương ứng. Vì vậy, nếu cluster chỉ có một node, replica thường ở trạng thái unassigned. Đây là tình huống phổ biến khiến cluster có trạng thái `yellow`: primary shard đã được phân bổ nhưng replica chưa thể được đặt ở node khác.

## 5. Ví dụ phân phối shard trên ba node

Giả sử index `products` được tạo với:

```json
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

Index có ba primary shard và một replica cho mỗi primary, tổng cộng sáu shard copy. Một cách phân phối hợp lệ trên ba node là:

| Node | Các shard copy được lưu |
|---|---|
| Node A | Primary 0, Replica 2 |
| Node B | Primary 1, Replica 0 |
| Node C | Primary 2, Replica 1 |

Mỗi node giữ hai shard copy và không node nào giữ đồng thời primary cùng replica của cùng một shard. Nếu Node A gặp sự cố, Replica 0 trên Node B có thể được nâng thành Primary 0. Cluster vẫn có thể phục vụ shard 0 nếu bản replica đó đủ điều kiện hoạt động.

Số lượng shard copy được tính theo công thức:

```text
Tổng shard copy = số primary shard × (1 + số replica trên mỗi primary)
                = 3 × (1 + 1)
                = 6
```

Đây là tổng số bản shard logic cần phân phối, không phải số node bắt buộc. Tuy nhiên, muốn đặt một primary và replica của nó trên các node khác nhau thì cluster phải có ít nhất hai node có khả năng lưu các shard đó. Số node và role thực tế còn phụ thuộc yêu cầu chịu lỗi và chính sách allocation.

## 6. Cluster health và trạng thái shard

Elasticsearch cung cấp cluster health để quan sát mức độ sẵn sàng của shard:

| Health | Ý nghĩa |
|---|---|
| `green` | Tất cả primary shard và replica shard cần thiết đều đã được phân bổ. |
| `yellow` | Tất cả primary shard đã được phân bổ, nhưng có ít nhất một replica chưa được phân bổ. |
| `red` | Có ít nhất một primary shard chưa được phân bổ; một phần dữ liệu của index có thể không truy cập được. |

Một số trạng thái shard thường gặp:

- `UNASSIGNED`: shard chưa được gán cho node nào.
- `INITIALIZING`: shard đang được khởi tạo hoặc khôi phục trên node.
- `STARTED`: shard đã hoạt động.
- `RELOCATING`: shard đang được chuyển từ node này sang node khác.

`green` không tự động chứng minh hệ thống đã có phương án disaster recovery tốt; trạng thái này chỉ cho biết các shard copy hiện được phân bổ đầy đủ. Backup, giám sát, kiểm tra khôi phục và phân bố node qua các failure domain vẫn cần được thiết kế riêng.

### Một số API quan sát hữu ích

Các request sau có thể gửi bằng Kibana Dev Tools, curl hoặc công cụ HTTP phù hợp:

```http
GET /_cluster/health
GET /_cat/nodes?v
GET /_cat/indices?v
GET /_cat/shards/products?v
GET /products/_settings
```

Ý nghĩa:

- `/_cluster/health` cho biết trạng thái tổng thể, số node và số shard đang hoạt động hoặc chưa được phân bổ.
- `/_cat/nodes` liệt kê node, địa chỉ và một số thông tin tài nguyên.
- `/_cat/indices` liệt kê index, số primary/replica và trạng thái.
- `/_cat/shards/products` hiển thị từng shard của index `products`, loại primary/replica và node đang lưu.
- `/{index}/_settings` đọc settings của index, trong đó có `number_of_shards` và `number_of_replicas`.

Các API `_cat` được thiết kế thuận tiện cho con người quan sát. Khi xây dựng tích hợp tự động, nên ưu tiên API có response cấu trúc phù hợp với mục đích xử lý.

## 7. Các khái niệm này liên quan thế nào đến Spring Data Elasticsearch?

Spring Data Elasticsearch cung cấp mapping và abstraction để ứng dụng Java thao tác với Elasticsearch. Ví dụ:

```java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    // getters, setters, constructors
}
```

Repository có thể được khai báo như sau:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Khi ứng dụng gọi:

```java
productRepository.save(product);
```

Spring Data chuyển entity thành document và gửi thao tác qua Elasticsearch client đã cấu hình. Elasticsearch tiếp nhận request, xác định primary shard theo routing, thực hiện ghi và đồng bộ replica theo cơ chế của cluster.

`indexName = "products"` xác định index logic mà entity ánh xạ tới. Nó không có nghĩa ứng dụng đang kết nối trực tiếp với một node hoặc một shard cố định. Địa chỉ node, xác thực và kết nối được cấu hình ở tầng client; số primary shard, replica và cách phân bổ được quản lý ở tầng index/cluster.

Khi cần chủ động thiết lập topology của index, có thể khai báo index settings bằng cơ chế Spring Data hỗ trợ, chẳng hạn annotation `@Setting` hoặc API `IndexOperations`, tùy phiên bản thư viện và cách tạo index của dự án. Một ví dụ về settings ở phía Elasticsearch là:

```json
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

Các settings này cần được áp dụng khi tạo index. Nếu index đã tồn tại, thay đổi số replica có thể thực hiện bằng update settings; thay đổi số primary shard cần một quy trình chuyển đổi dữ liệu phù hợp như reindex hoặc split/shrink theo điều kiện của Elasticsearch.

## 8. Những điểm cần nhớ khi thiết kế

- **Cluster** là toàn bộ hệ thống Elasticsearch; **node** là một tiến trình tham gia hệ thống đó.
- **Index** là tập dữ liệu logic; **shard** là phân vùng vật lý của index.
- **Primary shard** nhận thao tác ghi ban đầu; **replica shard** giữ bản sao của primary.
- Tăng node giúp có thêm nơi phân phối shard và tài nguyên, nhưng không tự động thay đổi số primary shard của index đã tạo.
- Tăng replica có thể cải thiện khả năng chịu lỗi và năng lực đọc, đồng thời làm tăng dung lượng và chi phí đồng bộ.
- Replica không thay thế snapshot backup.
- Ứng dụng Spring Data thao tác với index và document qua client/repository/operations; Elasticsearch chịu trách nhiệm định tuyến request đến node và shard.
- Cần theo dõi cluster health, shard allocation, dung lượng và tải thực tế trước khi điều chỉnh số shard hoặc replica.

Hiểu đúng cluster, node, shard và replica giúp đọc được trạng thái Elasticsearch, giải thích được cách request từ Spring Data đi đến dữ liệu, và lựa chọn cấu hình index phù hợp với quy mô cũng như yêu cầu sẵn sàng của ứng dụng.
