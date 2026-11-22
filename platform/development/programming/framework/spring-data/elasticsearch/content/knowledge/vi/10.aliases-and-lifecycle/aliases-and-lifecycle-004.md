# Chuyển alias nguyên tử khi thay phiên bản index

Trong Elasticsearch, **alias** là một tên tham chiếu đến một hoặc nhiều index. Ứng dụng có thể truy cập dữ liệu thông qua alias ổn định như **products-current**, trong khi index vật lý được tạo theo phiên bản như **products-v1**, **products-v2**. Khi cần thay mapping, analyzer hoặc cấu trúc dữ liệu, nhóm phát triển có thể chuẩn bị index mới rồi chuyển alias sang index đó.

Elasticsearch hỗ trợ cập nhật nhiều thao tác alias trong cùng một request **_aliases**. Khi request hợp lệ được xử lý, các thay đổi alias trong request được áp dụng nguyên tử trong cluster state. Nhờ đó, ứng dụng quan sát alias trỏ đến index cũ hoặc index mới, tránh khoảng thời gian alias bị gỡ khỏi index cũ nhưng chưa được gắn vào index mới.

Điểm cần hiểu rõ là thao tác alias nguyên tử chỉ làm cho việc đổi đích truy cập diễn ra liền mạch. Nó không tự chuyển dữ liệu, không bảo đảm index mới đã có đủ tài liệu và cũng không đồng bộ các lần ghi phát sinh trong lúc reindex. Vì vậy, quy trình thay phiên bản index cần chuẩn bị dữ liệu, kiểm tra, chuyển alias và có kế hoạch khôi phục.

## 1. Alias là gì và vì sao cần dùng?

Một index Elasticsearch thường gắn với tên cụ thể. Nếu ứng dụng truy cập trực tiếp **products-v1**, khi thay cấu trúc index sang **products-v2**, mã ứng dụng hoặc cấu hình triển khai phải thay đổi theo.

Alias cung cấp một tên logic ổn định đứng trước index vật lý:

~~~text
Ứng dụng Spring Data Elasticsearch
              |
              v
       products-current
           (alias)
              |
              v
         products-v1
       (index vật lý)
~~~

Sau khi chuyển phiên bản:

~~~text
Ứng dụng Spring Data Elasticsearch
              |
              v
       products-current
           (alias)
              |
              v
         products-v2
       (index vật lý)
~~~

Ứng dụng tiếp tục sử dụng **products-current**. Việc thay index vật lý được thực hiện ở phía Elasticsearch bằng thao tác cập nhật alias.

Alias hữu ích trong các trường hợp:

- Thay đổi mapping khi thêm trường hoặc thay đổi cách lập chỉ mục.
- Thay analyzer để cải thiện tìm kiếm.
- Tổ chức index theo phiên bản hoặc theo chu kỳ dữ liệu.
- Chuyển dữ liệu sang index mới mà không phải đổi tên index trong ứng dụng.
- Duy trì một tên truy cập ổn định cho repository và service.

Alias không lưu tài liệu. Dữ liệu vẫn nằm trong các index vật lý mà alias tham chiếu đến.

## 2. Phân biệt index, alias và write index

Ví dụ hệ thống sản phẩm có các tên sau:

| Tên | Loại | Vai trò |
|---|---|---|
| **products-v1** | Index vật lý | Lưu dữ liệu theo mapping phiên bản 1 |
| **products-v2** | Index vật lý | Lưu dữ liệu theo mapping phiên bản 2 |
| **products-current** | Alias | Tên truy cập ổn định mà ứng dụng sử dụng |

Một alias có thể trỏ đến một hoặc nhiều index. Nếu alias trỏ đến nhiều index, truy vấn đọc có thể tìm kiếm trên tất cả index được gắn với alias đó.

Đối với thao tác ghi, Elasticsearch cần biết index nào nhận tài liệu mới. Thuộc tính **is_write_index** dùng để xác định index nhận thao tác ghi thông qua alias.

Ví dụ gắn alias vào một index và đặt index đó làm write index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

Khi alias chỉ trỏ đến một index, Elasticsearch có thể mặc định index đó là write index trong nhiều trường hợp. Tuy nhiên, khai báo rõ **is_write_index: true** giúp ý định của hệ thống dễ hiểu hơn và tránh nhầm lẫn khi alias có thể trỏ đến nhiều index.

Nếu alias trỏ đến nhiều index mà không xác định write index, thao tác ghi có thể thất bại do Elasticsearch không biết phải ghi vào đâu. Với alias dùng cho cả đọc và ghi, hãy chỉ định rõ index nhận ghi.

Một thiết kế khác là dùng hai alias:

- **products-read** trỏ đến index hoặc tập index phục vụ đọc.
- **products-write** trỏ đến đúng một index nhận ghi.

Cách tách này hữu ích khi hệ thống cần đọc từ nhiều index trong giai đoạn chuyển đổi hoặc có quy tắc ghi riêng. Nếu dùng hai alias, cần cập nhật cả hai trong cùng một request khi muốn chuyển đổi đồng bộ.

## 3. Dùng alias ổn định trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch, lớp tài liệu thường khai báo tên index bằng **@Document**. Nếu ứng dụng muốn thao tác qua alias, có thể dùng tên alias làm giá trị **indexName**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-current", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    // Constructor, getter và setter được lược bỏ.
}
~~~

Trong ví dụ, **products-current** là alias. Repository hoặc **ElasticsearchOperations** dùng tên này khi thực hiện thao tác trên tài liệu.

Ví dụ repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Khi gọi **save**, **findById** hoặc truy vấn tìm kiếm qua repository, Spring Data Elasticsearch sử dụng tên được khai báo trong metadata của lớp tài liệu. Elasticsearch giải quyết alias thành index đích.

Thuộc tính **createIndex = false** phù hợp khi index và alias được quản lý bởi quy trình triển khai riêng. Ứng dụng không nên tự tạo index mang tên alias nếu tên đó đã được dành cho alias. Hãy tạo index vật lý, sau đó gắn alias vào index theo quy trình quản trị.

Nếu dùng **ElasticsearchOperations** trực tiếp, có thể chỉ định alias bằng **IndexCoordinates**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexCoordinates coordinates = IndexCoordinates.of("products-current");

operations.save(product, coordinates);
~~~

Các overload cụ thể của **save** và cách cấu hình repository có thể khác theo phiên bản Spring Data Elasticsearch. Điều quan trọng là mọi thao tác tài liệu trong ứng dụng phải dùng tên alias ổn định, không trỏ trực tiếp đến index có hậu tố phiên bản.

## 4. Chuẩn bị index phiên bản mới

Giả sử ứng dụng đang dùng **products-v1**. Mapping cũ có trường tên sản phẩm và danh mục:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword"
    }
  }
}
~~~

Phiên bản mới cần thêm analyzer tùy chỉnh, multi-field hoặc thay đổi kiểu trường. Không nên cố thay đổi mapping không tương thích trên index đang có dữ liệu. Thay vào đó, tạo index mới, ví dụ **products-v2**, với settings và mapping mong muốn.

Ví dụ tạo index mới:

~~~http
PUT /products-v2
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "product_name_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "product_name_analyzer",
        "fields": {
          "raw": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Trong Spring Data Elasticsearch, có thể tạo index bằng **IndexOperations** từ metadata của lớp tài liệu hoặc bằng quy trình quản trị index. Khi cần các phiên bản mapping khác nhau, nên quản lý cấu hình index theo từng phiên bản để có thể tái tạo index mới một cách nhất quán.

Ví dụ với lớp tài liệu và IndexOperations:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products-v2"));

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(mappingDocument);
}
~~~

Đoạn mã trên minh họa ý tưởng tạo index và áp dụng mapping. **mappingDocument** phải là đối tượng mapping đã được tạo hoặc nạp theo API của phiên bản Spring Data Elasticsearch đang dùng. Nếu settings cần khai báo, hãy cung cấp chúng trong bước tạo index. Không gọi **create()** với cấu hình mặc định rồi giả định analyzer tùy chỉnh đã được cài đặt.

Trước khi chuyển alias, cần xác nhận index mới đã có settings, mapping và quyền truy cập phù hợp. Alias chỉ chuyển tên truy cập; nó không sửa cấu trúc index.

## 5. Chuyển dữ liệu từ index cũ sang index mới

Sau khi tạo **products-v2**, cần chuyển dữ liệu từ **products-v1**. Elasticsearch cung cấp API **_reindex**:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Request này sao chép tài liệu từ index nguồn sang index đích. ID tài liệu được giữ lại nếu không có cấu hình biến đổi khác. Có thể bổ sung script hoặc query để chuyển đổi dữ liệu trong quá trình reindex nếu schema mới yêu cầu.

Ví dụ chỉ chuyển các sản phẩm đang hoạt động:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1",
    "query": {
      "term": {
        "status": "ACTIVE"
      }
    }
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Trước khi chuyển alias, hãy kiểm tra kết quả reindex:

- Request có hoàn tất hay không.
- Số tài liệu đã xử lý và số tài liệu bị lỗi.
- Có xung đột ID hoặc lỗi mapping hay không.
- Số lượng tài liệu giữa index cũ và index mới có phù hợp với điều kiện lọc hay không.
- Một số tài liệu đại diện có giữ đúng nội dung và kiểu dữ liệu hay không.

Có thể đếm tài liệu:

~~~http
GET /products-v1/_count

GET /products-v2/_count
~~~

Hai số lượng không nhất thiết phải bằng nhau nếu reindex có query lọc hoặc script biến đổi. Điều quan trọng là kết quả khớp với quy tắc chuyển đổi đã định.

### Kiểm soát các lần ghi trong khi reindex

Nếu ứng dụng tiếp tục ghi vào **products-v1** trong khi reindex đang chạy, các tài liệu mới hoặc cập nhật phát sinh sau khi reindex đọc dữ liệu có thể chưa xuất hiện trong **products-v2**. Vì vậy, việc reindex hoàn tất không tự động chứng minh hai index đồng nhất tại thời điểm chuyển alias.

Có một số chiến lược:

**Tạm dừng ghi trong thời gian chuyển đổi.** Đây là cách đơn giản và dễ kiểm soát. Dừng hoặc đưa các request ghi vào hàng đợi, hoàn tất reindex, kiểm tra dữ liệu, chuyển alias rồi cho phép ghi trở lại. Thời gian tạm dừng phụ thuộc dung lượng dữ liệu và tốc độ reindex.

**Reindex trước, sau đó đồng bộ phần thay đổi cuối.** Có thể chạy reindex ban đầu trong khi hệ thống vẫn hoạt động, sau đó tạm dừng ghi trong khoảng ngắn, đồng bộ các thay đổi còn thiếu và chuyển alias. Cần có cơ chế xác định thay đổi mới hoặc ghi lại dữ liệu phát sinh; chỉ chạy lại một lệnh reindex thông thường có thể không giải quyết đúng mọi trường hợp cập nhật và xóa.

**Dual-write hoặc dùng cơ chế CDC.** Ứng dụng ghi vào cả index cũ và mới, hoặc một luồng thay đổi dữ liệu đồng bộ sang index mới. Cách này giảm thời gian dừng ghi nhưng phức tạp hơn: cần xử lý lỗi một phía, thứ tự cập nhật, xóa tài liệu, ghi trùng và khả năng phát lại sự kiện.

Với ứng dụng đơn giản, tạm dừng ghi trong thời gian cutover thường dễ vận hành và dễ kiểm chứng. Với hệ thống có yêu cầu sẵn sàng cao, cần thiết kế đồng bộ dữ liệu riêng và thử nghiệm trước khi chuyển đổi.

## 6. Cập nhật alias nguyên tử bằng một request

Đây là bước chuyển đổi quan trọng. Không gửi hai request riêng biệt để gỡ alias khỏi index cũ rồi thêm alias vào index mới. Nếu request thứ nhất thành công nhưng request thứ hai thất bại, ứng dụng có thể gặp khoảng thời gian alias không trỏ đến index nào.

Hãy thực hiện cả hai action trong cùng một request **POST /_aliases**:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

Elasticsearch xử lý các action trong một lần cập nhật alias. Khi request được chấp nhận, alias được chuyển từ **products-v1** sang **products-v2** trong một thay đổi cluster state. Ứng dụng tiếp tục truy cập **products-current** và các request mới được định tuyến theo alias sau khi thay đổi được áp dụng.

Điểm quan trọng:

- **remove** chỉ gỡ alias khỏi index được chỉ định.
- **add** gắn alias vào index mới.
- **is_write_index: true** xác định index mới là đích nhận ghi thông qua alias.
- Hai action nằm trong cùng mảng **actions** của cùng một request.
- Nếu request thất bại, cần xử lý lỗi và kiểm tra trạng thái alias thực tế trước khi thử lại.

Không nên thực hiện như sau:

~~~http
POST /products-v1/_alias/products-current

DELETE /products-v1/_alias/products-current

PUT /products-v2/_alias/products-current
~~~

Các request riêng biệt tạo ra những thời điểm trạng thái trung gian. Cách này không bảo đảm chuyển đổi nguyên tử.

### Chuyển đồng thời read alias và write alias

Nếu hệ thống dùng hai alias **products-read** và **products-write**, có thể chuyển cả hai trong một request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Các thay đổi read và write alias cùng được gửi trong một lần cập nhật. Nhờ đó, ứng dụng không quan sát trạng thái đọc đã chuyển sang index mới trong khi alias ghi vẫn trỏ đến index cũ do hai thao tác quản trị được tách rời.

Nếu alias có filter hoặc routing, hãy khai báo lại các thuộc tính đó trong action **add**. Việc gỡ alias rồi thêm lại mà bỏ quên filter hoặc routing có thể làm thay đổi phạm vi tài liệu mà ứng dụng nhìn thấy.

## 7. Vì sao thao tác alias là nguyên tử?

API **_aliases** nhận một tập action để cập nhật alias trong cluster. Elasticsearch áp dụng thay đổi alias như một đơn vị cập nhật cluster state. Ứng dụng quan sát trạng thái trước hoặc sau khi cập nhật được áp dụng, thay vì phải đi qua trạng thái trung gian do hai request tách biệt tạo ra.

Tuy nhiên, cần hiểu đúng phạm vi nguyên tử:

- Việc thay đổi các alias trong một request được áp dụng như một đơn vị.
- Việc reindex dữ liệu không nằm trong transaction alias.
- Việc kiểm tra dữ liệu trước khi chuyển alias không tự động khóa các lần ghi mới.
- Các request đang chạy tại thời điểm chuyển alias có thể đã được định tuyến đến index cũ.
- Alias không tự sao chép tài liệu hoặc đồng bộ các lần ghi giữa index.

Vì vậy, quy trình phải bảo đảm index mới đã sẵn sàng trước khi alias được chuyển. Atomic alias switch giải quyết vấn đề thay đổi tuyến truy cập, còn tính đầy đủ và nhất quán của dữ liệu là trách nhiệm của quy trình migration.

## 8. Kiểm tra alias sau khi chuyển

Sau khi request cập nhật thành công, hãy đọc trạng thái alias:

~~~http
GET /_alias/products-current
~~~

Hoặc kiểm tra toàn bộ alias:

~~~http
GET /_cat/aliases/products-current?v
~~~

Kết quả cần xác nhận:

- Alias **products-current** trỏ đến **products-v2**.
- Alias không còn trỏ đến **products-v1**, trừ khi chủ đích là đọc từ nhiều index.
- **products-v2** là write index nếu alias được dùng để ghi.
- Filter, routing và các thuộc tính alias khác vẫn đúng.

Có thể kiểm tra index vật lý:

~~~http
GET /products-v2/_mapping

GET /products-v2/_settings

GET /products-v2/_count
~~~

Sau đó thử đọc và ghi qua alias:

~~~http
GET /products-current/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

Ví dụ ghi một tài liệu qua alias:

~~~http
POST /products-current/_doc
{
  "name": "Wireless Keyboard",
  "category": "accessories",
  "price": 79.9
}
~~~

Tài liệu mới phải được ghi vào index được đánh dấu là write index. Có thể kiểm tra bằng cách đọc tài liệu trong **products-v2** hoặc xem metadata của tài liệu sau khi ghi.

## 9. Quy trình cutover có kiểm soát

Một quy trình chuyển phiên bản index thường gồm các giai đoạn sau:

~~~text
1. Chuẩn bị products-v2
          |
          v
2. Reindex dữ liệu từ products-v1
          |
          v
3. Kiểm tra dữ liệu và truy vấn
          |
          v
4. Kiểm soát hoặc tạm dừng ghi
          |
          v
5. Đồng bộ các thay đổi cuối
          |
          v
6. Cập nhật alias bằng một request
          |
          v
7. Kiểm tra đọc/ghi qua alias
          |
          v
8. Theo dõi và giữ index cũ để khôi phục
~~~

Có thể diễn giải chi tiết như sau:

**Giai đoạn chuẩn bị**

- Chốt mapping và settings cho index mới.
- Tạo index vật lý mới.
- Kiểm tra analyzer, mapping, quyền truy cập và dung lượng.
- Xác nhận alias hiện tại đang trỏ đến index cũ.

**Giai đoạn chuyển dữ liệu**

- Chạy reindex hoặc cơ chế đồng bộ đã thiết kế.
- Theo dõi lỗi và số lượng tài liệu.
- Kiểm tra tài liệu mẫu, trường mới và kết quả tìm kiếm.
- Đồng bộ phần dữ liệu phát sinh trong lúc reindex.

**Giai đoạn cutover**

- Tạm dừng ghi hoặc bảo đảm cơ chế dual-write/CDC đã đồng bộ.
- Xác nhận index mới sẵn sàng nhận ghi.
- Gửi một request **_aliases** chứa đầy đủ action remove và add.
- Kiểm tra alias và write index sau khi request thành công.
- Mở lại luồng ghi nếu trước đó đã tạm dừng.

**Giai đoạn theo dõi**

- Kiểm tra log lỗi của ứng dụng.
- Theo dõi tỷ lệ lỗi đọc và ghi.
- Kiểm tra độ trễ truy vấn và kết quả tìm kiếm.
- Giữ index cũ trong khoảng thời gian đủ để xác nhận hệ thống hoạt động ổn định.

## 10. Khôi phục khi phiên bản mới gặp lỗi

Nếu phát hiện lỗi sau khi chuyển alias, có thể chuyển alias trở lại index cũ bằng một request tương tự:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

Thao tác này chỉ chuyển tuyến alias. Nó không đưa các tài liệu đã ghi vào **products-v2** trở lại **products-v1**.

Nếu ứng dụng đã nhận các lần ghi mới sau khi cutover, chuyển alias ngược có thể làm những dữ liệu đó không còn xuất hiện qua alias. Trước khi rollback, cần xác định dữ liệu nào đã phát sinh trên index mới và cách đồng bộ ngược hoặc phát lại các thay đổi đó.

Có thể áp dụng một trong các cách:

- Tạm dừng ghi, đồng bộ tài liệu mới từ index mới về index cũ rồi mới chuyển alias.
- Phát lại các sự kiện ghi từ hệ thống nguồn hoặc event log.
- Duy trì dual-write trong một khoảng thời gian nếu kiến trúc cho phép và có cơ chế xử lý lỗi rõ ràng.

Không xóa index mới ngay sau khi rollback. Giữ lại để điều tra nguyên nhân, đối chiếu dữ liệu và phục vụ việc thử nghiệm sửa lỗi.

## 11. Xử lý alias đã trỏ đến nhiều index

Một alias có thể trỏ đến nhiều index. Trước khi chuyển phiên bản, hãy kiểm tra trạng thái hiện tại:

~~~http
GET /_alias/products-current
~~~

Nếu alias đang trỏ đến **products-v1** và **products-archive**, action remove chỉ nhắm đến index được chỉ định:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

Sau thao tác, alias vẫn có thể tiếp tục trỏ đến **products-archive**. Đây có thể là chủ đích nếu archive cần được đọc cùng dữ liệu hiện tại. Nếu muốn alias chỉ trỏ đến index mới, phải xử lý các liên kết còn lại theo kế hoạch rõ ràng.

Với alias nhiều index, cần đặc biệt chú ý:

- Truy vấn đọc có thể trả kết quả từ tất cả index được alias tham chiếu.
- Các index có mapping khác nhau có thể tạo ra kết quả không đồng nhất.
- Ghi qua alias cần có write index xác định.
- Filter và routing của alias có thể làm thay đổi tập tài liệu được truy cập.
- Không nên xóa tất cả liên kết alias nếu chỉ muốn thay một index cụ thể.

## 12. Spring Data Elasticsearch và API quản lý alias

Spring Data Elasticsearch cung cấp **IndexOperations** để quản lý index và có các API liên quan đến alias tùy phiên bản. Đối tượng này thường được lấy từ **ElasticsearchOperations.indexOps(...)**:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

Trong ứng dụng, **IndexOperations** phù hợp cho các thao tác như kiểm tra index, tạo index, tạo hoặc đọc mapping và xóa index. Với chuyển alias nguyên tử gồm nhiều action, cần dùng API alias hỗ trợ gom các action vào cùng một request.

Tùy phiên bản Spring Data Elasticsearch, cách biểu diễn alias action và chữ ký phương thức có thể khác. Có thể sử dụng Elasticsearch Java API Client tương ứng với cluster hoặc gọi endpoint **POST /_aliases** thông qua thành phần HTTP/client được cấu hình trong ứng dụng.

Điều cần giữ nguyên về mặt thiết kế là toàn bộ action remove và add phải được gửi trong cùng một request cập nhật alias. Không tách thành nhiều lần gọi chỉ vì API wrapper của phiên bản đang dùng có cách biểu diễn khác.

Ví dụ request REST là cách thể hiện rõ nhất ý định chuyển alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

Nếu thực hiện từ Java, hãy dùng đúng Elasticsearch Java API Client và phiên bản tương thích với Spring Boot/Spring Data Elasticsearch của dự án. Không nên trộn API của RestHighLevelClient cũ với Elasticsearch Java API Client mới.

## 13. Lỗi thường gặp khi chuyển alias

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Alias không trỏ đến index mới | Action add sai tên index hoặc request thất bại | Đọc phản hồi và kiểm tra lại bằng **GET /_alias** |
| Request báo alias không tồn tại | Action remove tham chiếu alias hoặc index không đúng | Kiểm tra trạng thái alias trước khi chuyển |
| Ghi qua alias bị lỗi | Alias trỏ nhiều index nhưng chưa có write index | Đặt **is_write_index: true** cho index nhận ghi |
| Ứng dụng không tìm thấy tài liệu sau cutover | Index mới chưa được reindex đầy đủ hoặc truy vấn dùng mapping khác | Kiểm tra số lượng, dữ liệu mẫu và mapping |
| Dữ liệu mới bị thiếu | Có ghi phát sinh trong lúc reindex hoặc cutover | Tạm dừng ghi, đồng bộ thay đổi cuối hoặc dùng CDC/dual-write |
| Alias vẫn đọc dữ liệu cũ | Alias còn liên kết với index cũ hoặc nhiều index | Đọc toàn bộ alias và gỡ các liên kết không còn cần |
| Rollback làm mất dữ liệu mới qua alias | Các lần ghi sau cutover chỉ nằm trong index mới | Đồng bộ ngược hoặc phát lại sự kiện trước khi chuyển alias |
| Chuyển alias thành công nhưng truy vấn lỗi | Mapping hoặc analyzer của index mới không tương thích với ứng dụng | Kiểm tra mapping, query và phiên bản schema |
| Request bị từ chối | Tài khoản thiếu quyền quản trị alias hoặc index | Cấp quyền phù hợp theo chính sách bảo mật |

Khi gặp lỗi, không nên gửi lại request một cách mù quáng. Trước tiên, đọc trạng thái alias thực tế để biết request trước đã được áp dụng hay chưa. Điều này đặc biệt quan trọng khi client mất kết nối sau khi gửi request nhưng không nhận được phản hồi.

## 14. Các nguyên tắc vận hành cần nhớ

- Dùng alias ổn định trong cấu hình ứng dụng thay vì gắn mã ứng dụng với tên index có hậu tố phiên bản.
- Tạo và kiểm tra index mới trước khi chuyển alias.
- Bảo đảm dữ liệu đã được đồng bộ đến thời điểm cutover.
- Đặt write index rõ ràng nếu alias nhận ghi.
- Gửi action remove và add trong cùng một request **_aliases**.
- Kiểm tra alias, mapping và quyền ghi sau khi chuyển.
- Có kế hoạch rollback bao gồm cả dữ liệu phát sinh sau cutover.
- Giữ index cũ cho đến khi hệ thống mới được xác nhận ổn định.
- Chỉ xóa index cũ theo quy trình lưu giữ và dọn dẹp đã được phê duyệt.

Chuyển alias nguyên tử là kỹ thuật quan trọng để thay phiên bản index mà không phải đổi tên truy cập trong ứng dụng. Trong Spring Data Elasticsearch, lớp tài liệu có thể dùng tên alias làm **indexName**, còn thao tác quản trị alias được thực hiện qua API index tương ứng. Khi chuẩn bị dữ liệu mới, kiểm soát ghi, chuyển alias bằng một request và kiểm tra sau cutover, ứng dụng có thể chuyển sang index mới một cách có kiểm soát.
