# Định tuyến tài liệu đến shard và vai trò của routing

Elasticsearch chia một index thành nhiều primary shard để phân tán dữ liệu và xử lý truy vấn trên nhiều phần của tập tài liệu. Khi ghi hoặc đọc một tài liệu theo ID, Elasticsearch phải xác định shard nào chịu trách nhiệm cho tài liệu đó. Cơ chế chọn shard này được gọi là routing.

Mặc định, Elasticsearch dùng giá trị _id làm routing key, băm giá trị đó rồi xác định primary shard. Trong nhiều trường hợp, cách mặc định đã đủ. Ứng dụng có thể truyền một routing key riêng, chẳng hạn tenantId hoặc customerId, để gom các tài liệu liên quan vào cùng shard và giới hạn phạm vi shard cần tìm kiếm. Cách làm này có thể giảm chi phí truy vấn, nhưng cũng tạo ra ràng buộc khi ghi, cập nhật, đọc, xóa và phân phối tải.

Hiểu routing giúp thiết kế index và API đúng ngay từ đầu, đặc biệt với hệ thống nhiều tenant, quan hệ parent-child hoặc truy vấn chỉ cần dữ liệu thuộc một nhóm xác định.

## 1. Vì sao Elasticsearch cần routing?

Một index có thể có nhiều primary shard. Mỗi primary shard là một phân vùng dữ liệu độc lập; các replica shard là bản sao phục vụ khả năng sẵn sàng và tăng năng lực đọc. Một document thuộc về một primary shard cụ thể và các replica của shard đó.

Khi ứng dụng gửi yêu cầu index một document, Elasticsearch cần xác định primary shard đích. Khi tìm document theo ID, Elasticsearch cũng cần biết phải hỏi shard nào. Nếu một truy vấn tìm kiếm không giới hạn routing, Elasticsearch thường phải gửi truy vấn đến các shard phù hợp trong index rồi tổng hợp kết quả.

Routing giải quyết câu hỏi: **với routing key của document hoặc truy vấn này, shard nào cần xử lý?**

Có hai việc liên quan nhưng khác nhau:

- **Document routing:** xác định document thuộc primary shard nào trong index.
- **Shard allocation:** quyết định shard được đặt trên node nào trong cluster và khi nào shard được di chuyển giữa các node.

Routing key không chỉ định trực tiếp tên node hoặc máy chủ. Nó giúp Elasticsearch chọn shard; cluster allocation chịu trách nhiệm phân bố các shard đó lên các node.

## 2. Cách routing mặc định hoạt động

Khi ứng dụng không truyền tham số routing, Elasticsearch lấy _id của document làm routing value. Giá trị này được băm và kết quả được ánh xạ vào một trong các primary shard của index.

Có thể hình dung ở mức khái niệm:

~~~text
document _id
     |
     v
hash(_id)
     |
     v
chọn một primary shard
     |
     v
ghi document vào shard đó
~~~

Ví dụ, index products có ba primary shard. Các document có ID khác nhau được phân phối dựa trên kết quả băm:

| Document ID | Routing mặc định | Primary shard minh họa |
|---|---|---|
| product-101 | product-101 | shard 0 |
| product-205 | product-205 | shard 2 |
| product-330 | product-330 | shard 1 |

Các shard trong bảng chỉ minh họa kết quả có thể có; không thể suy ra shard thật chỉ bằng cách nhìn vào ID. Elasticsearch thực hiện thuật toán băm và chọn shard theo cấu hình của index.

Ưu điểm của routing mặc định:

- Ứng dụng không cần thiết kế hay lưu thêm routing key.
- Các thao tác theo cùng ID luôn có thể xác định đúng shard nếu dùng cùng index và cấu hình shard.
- Dữ liệu thường được phân tán tương đối đều khi ID có tính phân bố tốt.
- Không cần truyền routing riêng trong các lệnh index, get, update hoặc delete.

Với CRUD theo ID và tìm kiếm toàn index, routing mặc định thường là điểm khởi đầu hợp lý. Chỉ nên dùng custom routing khi có một nhu cầu truy vấn hoặc quan hệ dữ liệu cụ thể.

## 3. Custom routing: tự chọn routing key

Elasticsearch cho phép ứng dụng truyền tham số routing thay cho việc dùng _id làm routing value. Những document có cùng routing value sẽ được đưa về cùng primary shard của index.

Ví dụ, một hệ thống SaaS có nhiều tenant. Mỗi tenant có nhiều tài liệu và phần lớn truy vấn chỉ đọc dữ liệu của một tenant. Ứng dụng có thể dùng tenantId làm routing key:

~~~text
tenant-42
  ├── document A
  ├── document B
  └── document C

tenant-77
  ├── document D
  └── document E

routing("tenant-42") ──> một primary shard được chọn
~~~

Giá trị tenant-42 không có nghĩa tenant đó được cấp riêng một shard. Elasticsearch băm routing value để chọn shard. Nhiều tenant có thể cùng rơi vào một shard; một tenant có routing value cố định sẽ tập trung document vào một shard trong cấu hình routing thông thường.

### 3.1. Khai báo routing bắt buộc trong mapping

Nếu thiết kế yêu cầu mọi document phải có routing key, có thể khai báo _routing.required khi tạo index:

~~~http
PUT /tenant-documents
Content-Type: application/json

{
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "title": {
        "type": "text"
      },
      "content": {
        "type": "text"
      }
    }
  }
}
~~~

Với mapping này, thao tác index document mà không cung cấp routing sẽ bị từ chối. Đây là cách bảo vệ quy ước dữ liệu ở phía Elasticsearch, tránh một số document vô tình đi theo routing mặc định.

_routing.required chỉ yêu cầu request phải có routing value. Nó không tự kiểm tra rằng routing value bằng tenantId trong phần _source; ứng dụng vẫn phải bảo đảm hai giá trị đó khớp nhau.

### 3.2. Ghi document với routing key

Ví dụ tạo document thuộc tenant tenant-42:

~~~http
PUT /tenant-documents/_doc/doc-100?routing=tenant-42
Content-Type: application/json

{
  "tenantId": "tenant-42",
  "title": "Hướng dẫn sử dụng",
  "content": "Nội dung tài liệu của tenant."
}
~~~

Elasticsearch dùng tenant-42 để xác định primary shard đích. Giá trị tenantId trong _source là dữ liệu nghiệp vụ mà ứng dụng có thể lọc hoặc hiển thị; tham số routing là metadata điều khiển vị trí shard. Hai giá trị này có liên quan theo quy ước của ứng dụng nhưng không phải cùng một khái niệm.

### 3.3. Đọc, cập nhật và xóa phải dùng cùng routing

Khi document được ghi bằng custom routing, các thao tác định vị document theo ID cũng phải cung cấp routing value tương ứng:

~~~http
GET /tenant-documents/_doc/doc-100?routing=tenant-42
~~~

~~~http
POST /tenant-documents/_update/doc-100?routing=tenant-42
Content-Type: application/json

{
  "doc": {
    "title": "Hướng dẫn sử dụng phiên bản mới"
  }
}
~~~

~~~http
DELETE /tenant-documents/_doc/doc-100?routing=tenant-42
~~~

Nếu bỏ routing hoặc truyền một giá trị khác, Elasticsearch có thể tìm đến shard khác và không tìm thấy document. Kết quả có thể là 404, dù document thực sự vẫn tồn tại ở shard được chọn bởi routing ban đầu.

Do đó, ứng dụng phải giữ được routing key trong suốt vòng đời của document. Nếu API chỉ nhận ID nhưng không thể xác định routing value, custom routing sẽ khiến việc đọc, cập nhật và xóa phức tạp hơn.

## 4. Routing giúp truy vấn tìm kiếm như thế nào?

Khi tìm kiếm không truyền routing, Elasticsearch phải phân phối truy vấn đến các shard cần thiết trong index. Nếu ứng dụng biết trước truy vấn chỉ liên quan đến một hoặc một số routing key, có thể truyền chúng vào tham số routing của Search API.

Ví dụ, tìm tài liệu của tenant tenant-42:

~~~http
POST /tenant-documents/_search?routing=tenant-42
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-42"
          }
        }
      ],
      "must": [
        {
          "match": {
            "content": "hướng dẫn"
          }
        }
      ]
    }
  }
}
~~~

Tham số routing=tenant-42 giới hạn shard mà Elasticsearch cần hỏi. Điều kiện term trên tenantId lọc dữ liệu theo tenant trong kết quả. Hai phần có mục đích khác nhau:

- Routing giảm phạm vi shard cần truy vấn.
- Điều kiện truy vấn bảo đảm kết quả thỏa mãn điều kiện dữ liệu của ứng dụng.

**Không được coi routing là cơ chế phân quyền hoặc cô lập tenant.** Một shard có thể chứa tài liệu của nhiều tenant do các routing key khác nhau có thể băm về cùng shard. Ngoài ra, người gọi API có thể tự truyền routing value. Hệ thống vẫn phải xác thực người dùng, xác định tenant từ ngữ cảnh đáng tin cậy ở server và thêm điều kiện lọc phù hợp.

Search API có thể nhận nhiều routing value, thường được phân tách bằng dấu phẩy. Khi truy vấn dữ liệu của một nhóm tenant đã biết, điều này có thể giới hạn truy vấn vào các shard liên quan. Nếu người dùng cần tìm toàn bộ tenant hoặc toàn index, lợi ích giảm fan-out có thể không còn.

## 5. Lợi ích của custom routing

### 5.1. Giảm số shard tham gia truy vấn

Giả sử index có 12 primary shard nhưng một request chỉ cần dữ liệu của tenant tenant-42. Nếu tenant này được dùng làm routing key và request tìm kiếm truyền cùng routing value, Elasticsearch có thể chỉ truy vấn shard tương ứng thay vì fan-out đến cả 12 shard.

Điều này có thể giảm:

- Số shard phải thực hiện truy vấn.
- Công việc phối hợp và tổng hợp kết quả giữa các shard.
- Tài nguyên CPU và network cho những truy vấn theo một nhóm dữ liệu xác định.
- Độ trễ tìm kiếm trong workload phù hợp.

Hiệu quả thực tế còn phụ thuộc số document, độ phức tạp query, cache, kích thước shard và tải của cluster. Routing không bảo đảm mọi truy vấn sẽ nhanh hơn; cần benchmark bằng workload đại diện.

### 5.2. Đặt dữ liệu liên quan trên cùng shard

Một số mô hình dữ liệu cần các document liên quan nằm trên cùng shard. Ví dụ, quan hệ parent-child của Elasticsearch yêu cầu parent và child document ở cùng shard. Có thể dùng ID của parent làm routing value cho cả parent và child để bảo đảm điều kiện đó.

~~~text
parent: order-900
  routing = order-900
      |
      +-- child: item-1, routing = order-900
      |
      +-- child: item-2, routing = order-900
      |
      +-- child: item-3, routing = order-900

Tất cả được định tuyến đến cùng primary shard.
~~~

Khi thiết kế parent-child, phải giữ routing nhất quán cho toàn bộ quan hệ. Nếu parent và child bị ghi với routing khác nhau, truy vấn quan hệ có thể không hoạt động như mong đợi.

### 5.3. Phù hợp với truy vấn theo tenant hoặc nhóm dữ liệu

Routing theo tenant, khách hàng, tổ chức hoặc một khóa phân vùng nghiệp vụ có thể hữu ích khi phần lớn truy vấn có phạm vi rõ ràng. Nó giúp mô hình đọc theo nhóm dữ liệu có thể tận dụng shard routing thay vì luôn tìm kiếm toàn index.

Lợi ích chỉ xuất hiện khi ứng dụng thường xuyên biết routing key trước lúc truy vấn. Nếu phần lớn màn hình tìm kiếm xuyên tenant, routing theo tenant có thể không giảm được số shard tham gia.

## 6. Rủi ro và giới hạn cần hiểu rõ

### 6.1. Hot shard và phân phối dữ liệu không đều

Custom routing có thể tập trung lượng document hoặc lưu lượng truy vấn lớn vào một shard. Ví dụ, nếu một tenant lớn hơn các tenant còn lại hàng trăm lần, dùng tenantId làm routing key có thể khiến shard của tenant đó trở thành điểm nóng.

Hệ quả có thể gồm:

- Một shard tăng nhanh về dung lượng trong khi shard khác còn ít dữ liệu.
- CPU, disk I/O hoặc indexing pressure tập trung vào một phần cluster.
- Truy vấn của tenant lớn có độ trễ cao.
- Việc mở rộng cluster không tự động chia nhỏ phần dữ liệu đã tập trung trên shard đó.

Routing value có cardinality cao cũng không bảo đảm phân phối tải đều. Elasticsearch băm các giá trị để chọn shard, nhưng dung lượng và lưu lượng của từng giá trị có thể rất khác nhau.

### 6.2. Routing key phải ổn định

Nếu một document được ghi bằng tenant-42, nhưng lần cập nhật tiếp theo dùng tenant-77, Elasticsearch sẽ định vị shard theo giá trị mới và có thể không tìm thấy document cũ. Vì vậy routing key cần ổn định trong vòng đời document.

Nếu nghiệp vụ cho phép chuyển document từ tenant này sang tenant khác, hãy thiết kế quy trình chuyển dữ liệu rõ ràng: xác định routing cũ, đọc document cũ, ghi document vào routing mới và xử lý việc xóa bản cũ. Không nên chỉ thay đổi trường tenantId trong _source rồi giả định document tự chuyển shard.

### 6.3. Nguy cơ trùng _id trên các shard khác nhau

Với custom routing, cùng một _id nhưng hai routing value khác nhau có thể được định tuyến đến hai shard khác nhau. Tính duy nhất của _id được bảo đảm trong phạm vi shard, nên ứng dụng không nên giả định _id vẫn duy nhất trên toàn index nếu cho phép nhiều routing value cho cùng ID.

Hãy dùng routing key nhất quán và thiết kế ID phù hợp với phạm vi nghiệp vụ. Ví dụ, nếu ID chỉ duy nhất trong một tenant, có thể tạo ID kết hợp tenant và ID cục bộ hoặc bảo đảm mọi thao tác luôn dùng routing của tenant sở hữu document.

### 6.4. Thay đổi số primary shard là vấn đề thiết kế

Routing được tính dựa trên routing value và số lượng primary shard của index. Khi tạo index, số primary shard là một phần quan trọng của cách phân phối dữ liệu. Nếu cần thay đổi cấu trúc shard hoặc chiến lược routing, thường phải tạo index mới, reindex dữ liệu và chuyển alias hoặc ứng dụng sang index mới.

Không nên xem routing là một tham số có thể thay đổi tùy ý sau khi index đã chứa dữ liệu. Cần ước lượng dung lượng, số lượng tenant, mức độ lệch tải và kiểu truy vấn trước khi chốt thiết kế.

### 6.5. Routing không thay thế bộ lọc nghiệp vụ

Routing chọn shard dựa trên metadata của request. Nó không xác nhận rằng document trong _source thuộc đúng tenant mà người dùng được phép truy cập. Một shard có thể chứa nhiều tenant và một truy vấn có thể trả về document của tenant khác nếu query không có điều kiện lọc phù hợp.

Server phải tự xác định routing từ danh tính và quyền của người gọi, không tin routing do client tùy ý cung cấp. Đồng thời, query phải có điều kiện lọc tenant hoặc điều kiện phân quyền tương ứng.

## 7. Chọn routing key như thế nào?

Một routing key tốt cần phù hợp với cách ứng dụng ghi và truy vấn dữ liệu. Hãy cân nhắc các tiêu chí sau:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Phạm vi truy vấn | Phần lớn request có biết routing key trước khi tìm kiếm không? |
| Tính ổn định | Routing value có giữ nguyên trong vòng đời document không? |
| Phân phối dung lượng | Có tenant hoặc nhóm nào lớn vượt trội không? |
| Phân phối tải | Có nhóm nào ghi hoặc tìm kiếm thường xuyên hơn nhiều không? |
| Quan hệ dữ liệu | Các document cần join theo parent-child có cùng routing không? |
| Vận hành | Có thể theo dõi shard nóng và thay đổi chiến lược khi cần không? |

Một số ví dụ:

| Routing key | Khi có thể phù hợp | Rủi ro chính |
|---|---|---|
| Không truyền custom routing, dùng _id | CRUD theo ID, tìm kiếm toàn index, chưa có nhóm truy vấn rõ ràng | Truy vấn theo một tenant vẫn có thể phải fan-out |
| tenantId | Hầu hết truy vấn giới hạn trong một tenant | Tenant lớn tạo hot shard; truy vấn xuyên tenant ít được lợi |
| customerId | Dữ liệu và truy vấn thường tập trung theo một khách hàng | Khách hàng có dữ liệu hoặc lưu lượng lớn làm lệch tải |
| parentId | Cần đặt parent-child cùng shard | Mọi thao tác phải giữ routing theo parent |
| accountId hoặc organizationId | Các request chủ yếu đọc một tài khoản hoặc tổ chức | Cần xác định rõ trường hợp truy vấn nhiều tài khoản |

Đừng chọn routing key chỉ vì trường đó có sẵn trong entity. Hãy bắt đầu từ mẫu truy vấn thực tế và kiểm tra liệu request có luôn biết giá trị routing hay không.

## 8. Routing trong bulk indexing

Khi ghi nhiều document bằng Bulk API, routing được khai báo trong metadata của từng thao tác. Mỗi document có thể có routing value riêng:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "tenant-documents", "_id": "doc-100", "routing": "tenant-42" } }
{ "tenantId": "tenant-42", "title": "Tài liệu A" }
{ "index": { "_index": "tenant-documents", "_id": "doc-200", "routing": "tenant-77" } }
{ "tenantId": "tenant-77", "title": "Tài liệu B" }
~~~

Nếu dùng Bulk API, cần bảo đảm routing được thêm vào metadata cho từng document cần custom routing. Chỉ đặt routing ở một request khác hoặc lưu routing trong _source không làm Bulk API tự động dùng trường đó để chọn shard.

Khi xử lý kết quả bulk, cần kiểm tra lỗi theo từng item. Một request bulk có thể hoàn tất ở cấp HTTP nhưng một số item vẫn thất bại do thiếu routing, mapping sai hoặc lỗi ghi.

## 9. Sử dụng routing với Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp lớp ánh xạ entity và abstraction thao tác với Elasticsearch. Khi dùng custom routing, điều quan trọng là routing value phải được gắn vào metadata của thao tác Elasticsearch. Chỉ khai báo một thuộc tính tenantId trong entity hoặc lưu nó trong _source không tự động bảo đảm mọi request sẽ dùng thuộc tính đó làm routing.

Ở các phiên bản Spring Data Elasticsearch có hỗ trợ annotation @Routing, có thể đánh dấu thuộc tính chứa routing value trong entity. Ví dụ minh họa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Routing;

@Document(indexName = "tenant-documents")
public class TenantDocument {

    @Id
    private String id;

    @Routing
    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String title;

    // constructors, getters and setters
}
~~~

Trong mô hình này, tenantId vừa là dữ liệu được lưu trong document vừa là giá trị routing mà mapping layer sử dụng khi thực hiện các thao tác được hỗ trợ. Cần xác nhận annotation và hành vi cụ thể trong phiên bản Spring Data Elasticsearch của dự án, đặc biệt với các thao tác custom query hoặc client API cấp thấp.

Nếu một thao tác dùng ElasticsearchOperations, repository hoặc Elasticsearch Java Client trực tiếp, hãy kiểm tra API của đúng phiên bản để truyền routing vào request. Không nên giả định mọi truy vấn tùy chỉnh tự kế thừa routing từ entity. Với search request, routing phải được đặt trên đối tượng query/request tương ứng; với thao tác theo ID, routing phải được truyền cùng thao tác đọc, cập nhật hoặc xóa.

Một quy ước hữu ích là đóng gói việc xác định routing trong một service hoặc thành phần truy cập dữ liệu. Khi đó các luồng lưu, tìm, lấy theo ID và xóa document dùng cùng một quy tắc, tránh mỗi nơi tự ghép tham số routing khác nhau.

## 10. Kiểm thử và quan sát routing

Trước khi triển khai custom routing, hãy kiểm thử bằng dữ liệu gần với phân bố thật:

1. Tạo index với số primary shard dự kiến.
2. Sinh document theo số lượng tenant hoặc nhóm dữ liệu gần thực tế.
3. Ghi dữ liệu bằng routing key dự kiến.
4. So sánh truy vấn toàn index với truy vấn có routing.
5. Đo số shard được truy vấn, latency, CPU, dung lượng và indexing throughput.
6. Thử tenant lớn nhất và các nhóm có tần suất truy cập cao.
7. Kiểm tra get, update, delete và bulk khi có routing đúng, thiếu hoặc sai.
8. Kiểm tra phân quyền và tenant filter độc lập với routing.

Khi vận hành, quan sát kích thước và tải từng shard, indexing pressure, search latency, rejected requests và cluster health. Nếu một shard nhận lượng dữ liệu hoặc lưu lượng vượt trội, cần đánh giá lại routing key hoặc cách phân vùng dữ liệu.

## 11. Ví dụ lựa chọn routing cho hệ thống nhiều tenant

Giả sử một nền tảng quản lý tài liệu có 200 tenant. Hầu hết request tìm kiếm đều xuất phát từ một tenant đã xác thực. Mỗi tenant có hàng nghìn đến hàng triệu tài liệu, và API thường tìm theo từ khóa trong phạm vi tenant.

Một phương án có thể là:

- Dùng tenantId làm routing key để truy vấn theo tenant chỉ đến shard liên quan.
- Lưu tenantId trong _source dưới kiểu keyword để lọc chính xác.
- Đánh dấu routing bắt buộc trong mapping để tránh ghi thiếu.
- Server lấy tenant từ thông tin xác thực, tự gắn routing và điều kiện filter vào query.
- Mọi thao tác lấy theo ID, cập nhật và xóa đều nhận biết tenant sở hữu document để truyền routing nhất quán.
- Theo dõi tenant có dung lượng hoặc lưu lượng lớn để phát hiện shard nóng.

Nếu một tenant đặc biệt lớn chiếm phần lớn tải, việc định tuyến toàn bộ tenant vào một shard có thể trở thành nút thắt. Khi đó cần đánh giá lại cách phân vùng, chẳng hạn chia tenant lớn thành nhiều routing partition hoặc thiết kế index riêng theo nhóm dữ liệu. Các lựa chọn này làm tăng độ phức tạp và cần được kiểm chứng theo phiên bản Elasticsearch, cấu hình index và workload cụ thể.

Nếu ứng dụng thường xuyên tìm kiếm xuyên tất cả tenant, custom routing theo tenant có thể không đem lại lợi ích đáng kể. Routing key cần phản ánh phạm vi truy vấn chủ đạo, không chỉ phản ánh cấu trúc tổ chức của dữ liệu.

## 12. Kết luận

Routing là cơ chế Elasticsearch dùng để xác định shard xử lý một document hoặc một truy vấn. Mặc định, _id là routing value; custom routing cho phép dùng khóa nghiệp vụ như tenantId, customerId hoặc parentId để gom dữ liệu liên quan và giới hạn shard cần tìm kiếm.

Custom routing có thể cải thiện hiệu năng khi request thường biết routing key và dữ liệu được phân phối hợp lý. Đổi lại, ứng dụng phải giữ routing nhất quán qua index, get, update, delete, bulk và search; đồng thời theo dõi hot shard, tránh trùng ID giữa các routing khác nhau và không coi routing là cơ chế bảo mật.

Hãy bắt đầu với routing mặc định nếu chưa có lý do rõ ràng. Chỉ chuyển sang custom routing sau khi đã xác định mẫu truy vấn, đo tải và chứng minh lợi ích của việc giảm shard fan-out hoặc đặt document liên quan trên cùng shard.
