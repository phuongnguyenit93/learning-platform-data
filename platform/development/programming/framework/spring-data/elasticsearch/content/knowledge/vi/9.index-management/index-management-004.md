# Đọc mapping, settings và đối chiếu với mô hình Java

Trong Elasticsearch, mapping mô tả cấu trúc và cách Elasticsearch hiểu từng field của document; settings mô tả cấu hình vận hành của index như số shard, replica, refresh interval và analyzer. Trong Spring Data Elasticsearch, entity Java cùng các annotation như @Document và @Field thể hiện mô hình mà ứng dụng mong muốn sử dụng.

Ba nguồn thông tin này có liên quan nhưng không đồng nhất. Annotation trong mã nguồn không chứng minh mapping thực tế trên cluster đang giống như vậy. Index có thể được tạo từ một mapping JSON, index template, migration hoặc một phiên bản ứng dụng cũ. Vì thế, khi điều tra lỗi tìm kiếm hoặc chuẩn bị thay đổi dữ liệu, cần đọc mapping và settings thật từ Elasticsearch rồi đối chiếu với mô hình Java.

Bài học này trình bày cách đọc cấu hình của index bằng REST API và Spring Data Elasticsearch, cách hiểu các phần quan trọng trong kết quả, cách so sánh với entity và cách xử lý khi phát hiện sai lệch.

## 1. Phân biệt mapping và settings

Mapping và settings trả lời hai nhóm câu hỏi khác nhau.

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Mapping | Elasticsearch hiểu field của document như thế nào? | name là text, price là double, createdAt là date |
| Settings | Index được cấu hình để lưu trữ và hoạt động ra sao? | 3 primary shard, 1 replica, refresh interval 1 giây, analyzer tùy chỉnh |
| Java entity metadata | Ứng dụng muốn chuyển thuộc tính Java thành field nào? | @Field(type = FieldType.Text), @Id, @Document(indexName = "products") |

Mapping quyết định khả năng tìm kiếm, lọc, sắp xếp và aggregation trên từng field. Settings ảnh hưởng đến cách index được tạo, phân phối và cập nhật. Java metadata điều khiển cách Spring Data chuyển đổi entity và có thể được dùng để tạo mapping ban đầu.

Không nên nhầm mapping với nội dung document. Mapping mô tả schema; _source chứa dữ liệu của từng document. Một field có thể được khai báo trong mapping nhưng chưa xuất hiện trong bất kỳ document nào.

## 2. Đọc mapping bằng Elasticsearch REST API

API phổ biến nhất để xem mapping của một index là:

~~~http
GET /products/_mapping
~~~

Kết quả có cấu trúc tương tự:

~~~json
{
  "products": {
    "mappings": {
      "properties": {
        "name": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword"
            }
          }
        },
        "category": {
          "type": "keyword"
        },
        "price": {
          "type": "double"
        },
        "createdAt": {
          "type": "date"
        }
      }
    }
  }
}
~~~

Phần properties liệt kê các field đã được định nghĩa. Mỗi field có kiểu dữ liệu và có thể có các thuộc tính bổ sung như analyzer, format, fields, properties hoặc dynamic.

### 2.1. Đọc mapping của một field cụ thể

Khi index có mapping lớn, có thể chỉ đọc field cần điều tra:

~~~http
GET /products/_mapping/field/price
~~~

Hoặc kiểm tra nhiều field:

~~~http
GET /products/_mapping/field/name,price,createdAt
~~~

API này hữu ích khi cần xác nhận một field đang là text, keyword, date, nested hay kiểu số nào. Nó cũng giúp kiểm tra multi-fields và các tùy chọn của field mà không phải đọc toàn bộ mapping.

### 2.2. Đọc mapping của nhiều index

Elasticsearch cho phép chỉ định nhiều index hoặc wildcard:

~~~http
GET /products-*/_mapping
~~~

Điều này hữu ích khi ứng dụng sử dụng index theo phiên bản hoặc theo thời gian, ví dụ products-v1, products-v2 hoặc events-2025.04. Cần kiểm tra từng index nếu truy vấn chạy trên nhiều index vì cùng một field có thể có mapping khác nhau giữa các index.

Nếu ứng dụng truy vấn qua alias, hãy xác định các index vật lý phía sau alias rồi kiểm tra mapping của từng index. Alias không làm cho mapping giữa các index tự động đồng nhất.

## 3. Hiểu các thành phần quan trọng trong mapping

### 3.1. properties và kiểu dữ liệu

properties mô tả các field của document. Một số kiểu thường gặp:

| Kiểu Elasticsearch | Mục đích thường dùng |
|---|---|
| text | Tìm kiếm toàn văn, có phân tích nội dung |
| keyword | So khớp chính xác, lọc, sort và aggregation |
| byte, short, integer, long | Số nguyên theo phạm vi |
| half_float, float, double | Số thực |
| scaled_float | Số thực lưu theo hệ số scaling |
| boolean | Giá trị đúng/sai |
| date, date_nanos | Ngày giờ và timestamp |
| object | Đối tượng JSON lồng nhau |
| nested | Mảng object cần giữ quan hệ giữa các field trong từng phần tử |
| geo_point | Tọa độ địa lý |

Kiểu field ảnh hưởng trực tiếp đến loại truy vấn hợp lệ. Ví dụ, match thường được dùng cho nội dung text; term phù hợp với giá trị keyword hoặc các field cần so khớp chính xác. Một truy vấn có thể chạy nhưng cho kết quả không đúng mong đợi nếu mapping không phù hợp với ý nghĩa dữ liệu.

### 3.2. text và multi-fields

Một field text thường được phân tích thành token khi lập chỉ mục. Nếu cần vừa tìm toàn văn vừa sort hoặc aggregation theo chuỗi nguyên bản, mapping có thể khai báo multi-fields:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Trong trường hợp này:

- name là field text phục vụ tìm kiếm toàn văn.
- name.keyword là sub-field keyword phục vụ so khớp chính xác, sort hoặc aggregation.

Nếu entity chỉ có một thuộc tính name, Spring Data vẫn có thể ánh xạ nó vào field gốc name; ứng dụng truy vấn name.keyword khi cần dùng sub-field. Sub-field không nhất thiết tương ứng với một thuộc tính Java riêng.

### 3.3. Analyzer, search analyzer và normalizer

Với field text, mapping có thể chỉ định analyzer khi lập chỉ mục và search analyzer khi truy vấn:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "standard",
    "search_analyzer": "standard"
  }
}
~~~

Analyzer quyết định cách văn bản được tách token, chuẩn hóa và xử lý. Nếu analyzer lúc index và lúc search không tương thích, kết quả tìm kiếm có thể không như mong muốn.

Với field keyword, normalizer có thể chuẩn hóa giá trị mà vẫn giữ một token duy nhất, ví dụ chuẩn hóa chữ hoa/chữ thường. Cần đọc cả analyzer, search analyzer và normalizer khi điều tra vấn đề tìm kiếm.

### 3.4. object, nested và cấu trúc lồng nhau

Mapping của object lồng nhau có thể chứa properties bên trong:

~~~json
{
  "manufacturer": {
    "type": "object",
    "properties": {
      "name": {
        "type": "keyword"
      },
      "country": {
        "type": "keyword"
      }
    }
  }
}
~~~

Với mảng object cần giữ ranh giới từng phần tử khi truy vấn, mapping có thể dùng nested:

~~~json
{
  "lines": {
    "type": "nested",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "quantity": {
        "type": "integer"
      }
    }
  }
}
~~~

Entity Java có thể dùng một object hoặc List<OrderLine> trong cả hai trường hợp. Chỉ nhìn kiểu Java không thể kết luận field Elasticsearch là object hay nested; cần đọc mapping thực tế hoặc khai báo tường minh bằng metadata tương ứng.

### 3.5. Dynamic mapping

Elasticsearch có thể tự suy luận mapping cho field mới khi nhận document, tùy cấu hình dynamic. Một số giá trị thường gặp:

- true: tự thêm mapping cho field mới.
- false: không lập chỉ mục field mới, nhưng field vẫn có thể còn trong _source.
- strict: từ chối document có field chưa được khai báo.

Nếu dynamic mapping đang bật, một field chưa có trong entity Java có thể xuất hiện trong mapping sau khi một document chứa field đó được ghi. Ngược lại, entity có thuộc tính mới nhưng chưa ghi document hoặc chưa tạo mapping tương ứng thì field có thể chưa xuất hiện trong mapping thực tế.

Dynamic mapping thuận tiện cho dữ liệu linh hoạt nhưng có thể tạo kiểu field không mong muốn. Ví dụ, một chuỗi ngày giờ có thể bị suy luận thành date theo format mặc định, hoặc một giá trị số có thể được suy luận thành kiểu số không phù hợp với miền dữ liệu dài hạn.

## 4. Đọc settings của index

Để đọc settings đã áp dụng cho index:

~~~http
GET /products/_settings
~~~

Muốn xem cả giá trị mặc định mà Elasticsearch áp dụng:

~~~http
GET /products/_settings?include_defaults=true
~~~

Có thể dùng dạng phẳng để dễ tìm tên setting:

~~~http
GET /products/_settings?flat_settings=true&include_defaults=true
~~~

Kết quả có thể chứa những giá trị như:

~~~json
{
  "products": {
    "settings": {
      "index": {
        "number_of_shards": "3",
        "number_of_replicas": "1",
        "refresh_interval": "1s",
        "analysis": {
          "analyzer": {
            "product_analyzer": {
              "type": "custom"
            }
          }
        }
      }
    }
  }
}
~~~

Các giá trị trong ví dụ chỉ minh họa. Settings thực tế phụ thuộc cấu hình index, template, phiên bản Elasticsearch và môi trường triển khai.

### 4.1. Những settings nên kiểm tra

| Setting | Ý nghĩa | Khi cần kiểm tra |
|---|---|---|
| index.number_of_shards | Số primary shard | Khi đánh giá cách phân vùng dữ liệu và dung lượng |
| index.number_of_replicas | Số replica cho mỗi primary shard | Khi kiểm tra khả năng sẵn sàng và năng lực đọc |
| index.refresh_interval | Chu kỳ refresh để document mới có thể xuất hiện trong search | Khi điều tra độ trễ nhìn thấy dữ liệu sau khi ghi |
| index.analysis | Analyzer, tokenizer, token filter và normalizer | Khi tìm kiếm văn bản cho kết quả không đúng |
| index.sort.* | Cấu hình sắp xếp vật lý lúc lập chỉ mục nếu được dùng | Khi điều tra cấu hình index sort |
| index.lifecycle.* | Một số cấu hình liên quan lifecycle nếu index được quản lý theo chính sách tương ứng | Khi điều tra rollover, retention hoặc quản lý vòng đời |

Settings có thể được chia thành loại chỉ định lúc tạo index và loại có thể cập nhật động. Ví dụ, số primary shard là một quyết định cấu trúc quan trọng và không thể thay đổi trực tiếp như một setting thông thường sau khi index đã được tạo. Số replica và refresh interval là các ví dụ về setting có thể thay đổi động trong những điều kiện được Elasticsearch hỗ trợ.

Không nên thử cập nhật setting production chỉ để quan sát kết quả. Trước khi thay đổi, kiểm tra tài liệu đúng phiên bản, phạm vi ảnh hưởng và yêu cầu vận hành.

### 4.2. Vì sao nên dùng include_defaults=true?

Nếu chỉ đọc settings thông thường, kết quả chủ yếu thể hiện cấu hình được lưu cho index. Một số giá trị có thể không xuất hiện vì đang dùng mặc định của cluster hoặc phiên bản.

include_defaults=true giúp phân biệt:

- Setting được chỉ định rõ khi tạo hoặc cập nhật index.
- Giá trị mặc định đang có hiệu lực.

Điều này quan trọng khi so sánh hai index. Hai index có thể có kết quả settings tường minh khác nhau nhưng vẫn đang sử dụng cùng giá trị hiệu lực; hoặc cùng không khai báo một setting nhưng giá trị mặc định đã thay đổi theo phiên bản.

## 5. Đọc mapping và settings bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp IndexOperations để đọc và quản lý cấu hình index. Có thể lấy đối tượng này từ ElasticsearchOperations.

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexInspector {

    private final ElasticsearchOperations operations;

    public ProductIndexInspector(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void inspect() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        Map<String, Object> mapping = indexOperations.getMapping();
        Map<String, Object> settings = indexOperations.getSettings();

        System.out.println("Mapping: " + mapping);
        System.out.println("Settings: " + settings);
    }
}
~~~

operations.indexOps(Product.class) sử dụng metadata của entity để xác định index đích, thông thường là indexName trong @Document. getMapping() đọc mapping của index và getSettings() đọc settings hiện tại theo API của phiên bản Spring Data đang dùng.

Chữ ký và kiểu trả về của một số phương thức quản lý index có thể thay đổi giữa các release train. Hãy kiểm tra Javadoc hoặc API của đúng phiên bản trong dự án trước khi dùng code này nguyên văn.

### 5.1. Tạo mapping dự kiến từ entity

IndexOperations cũng cung cấp API tạo mapping dựa trên metadata entity. Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

IndexOperations indexOperations = operations.indexOps(Product.class);
Document declaredMapping = indexOperations.createMapping();
~~~

createMapping() tạo cấu trúc mapping mà Spring Data suy ra từ entity và các annotation hiện tại. Có thể đặt cạnh kết quả getMapping() để xem sự khác biệt giữa mapping dự kiến từ Java model và mapping thực tế trên index.

Mapping sinh từ entity không phải bản sao đảm bảo giống hệt JSON mapping trên cluster. Mapping thực tế có thể có field được thêm bởi dynamic mapping, index template hoặc migration; nó cũng có thể chứa analyzer, sub-field và cấu hình được quản lý bên ngoài entity.

### 5.2. Đọc cấu hình mặc định

Một số phiên bản Spring Data Elasticsearch có overload cho phép yêu cầu lấy settings kèm giá trị mặc định. Nếu phiên bản dự án không cung cấp API tương ứng hoặc cần kết quả rõ ràng nhất, dùng REST API:

~~~http
GET /products/_settings?include_defaults=true
~~~

REST API cũng hữu ích khi cần truy cập một tham số query chưa được abstraction của phiên bản Spring Data hiện tại bộc lộ.

## 6. Khai báo settings và mapping từ Java model

Entity có thể mô tả một phần mapping bằng annotation:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

Với cấu hình phức tạp, Spring Data Elasticsearch hỗ trợ khai báo file settings và mapping thông qua các annotation ở cấp document:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = false)
@Setting(settingPath = "/elasticsearch/products-settings.json")
@Mapping(mappingPath = "/elasticsearch/products-mapping.json")
public class Product {
    // fields
}
~~~

Ví dụ này minh họa việc tách settings và mapping thành tài nguyên riêng để dễ quản lý. Đường dẫn, cách đóng gói tài nguyên và hành vi bootstrap cần được xác nhận theo phiên bản Spring Data Elasticsearch đang dùng.

Trong môi trường production, index thường được tạo bởi migration hoặc pipeline triển khai. Khi đó createIndex = false giúp repository bootstrap không tự tạo index theo metadata của entity. Settings và mapping được triển khai trước, sau đó ứng dụng mới sử dụng index.

## 7. Đối chiếu mapping thực tế với Java entity

Khi đối chiếu, không nên chỉ so tên thuộc tính. Hãy so sánh cả kiểu field và các tùy chọn ảnh hưởng đến hành vi tìm kiếm.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

Mapping mong đợi có thể tương tự:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
~~~

Đối chiếu:

| Java model | Mapping thực tế cần xác nhận | Vấn đề nếu không khớp |
|---|---|---|
| String name với FieldType.Text | name là text và analyzer phù hợp | Tìm kiếm toàn văn hoặc phân tích ngôn ngữ sai |
| String category với FieldType.Keyword | category là keyword | Lọc chính xác, sort hoặc aggregation không hoạt động như mong đợi |
| BigDecimal price với FieldType.Double | price là kiểu số phù hợp | Range query, sort hoặc độ chính xác số có thể sai |
| Instant createdAt với FieldType.Date | createdAt là date với format chấp nhận dữ liệu | Ghi hoặc truy vấn thời gian có thể lỗi |
| @Id String id | Document identity nằm ở _id | Nhầm _id với một field trong _source |

Nếu dùng @Field(name = "product_name"), hãy so sánh với field product_name trên index, không phải tên property Java name.

### 7.1. Những khác biệt thường gặp

**Field thiếu trong mapping:** entity có thuộc tính mới nhưng index đã tồn tại và chưa được cập nhật mapping. Nếu dynamic mapping tắt hoặc document chưa từng chứa field, field đó có thể chưa xuất hiện trong mapping.

**Field thừa trong mapping:** index có field do dynamic mapping, template hoặc một ứng dụng khác tạo ra nhưng entity hiện tại không khai báo. Điều này không nhất thiết là lỗi, nhưng cần biết field thuộc nguồn dữ liệu nào và có được ứng dụng sử dụng không.

**Sai kiểu field:** Java khai báo String với FieldType.Text, nhưng mapping thực tế là keyword. Converter có thể vẫn ghi chuỗi bình thường, song hành vi tìm kiếm thay đổi. Một số kiểu mapping không thể đổi trực tiếp sau khi index đã chứa dữ liệu.

**Sai analyzer hoặc normalizer:** tên và kiểu field đúng nhưng analyzer khác với dự kiến. Đây là nguyên nhân thường gặp khiến tìm kiếm trả kết quả khác giữa môi trường.

**Sai object và nested:** entity có List<OrderLine> nhưng mapping thực tế là object, trong khi query lại dùng nested query hoặc ngược lại. Kiểu collection trong Java không tự quyết định mapping nested.

**Sai format date:** Java dùng Instant nhưng mapping có format tùy chỉnh không nhận chuỗi mà converter gửi, hoặc dữ liệu cũ dùng định dạng khác.

**Multi-field không có:** entity chỉ khai báo field gốc nhưng query sort theo name.keyword, trong khi mapping thực tế chưa có sub-field này.

## 8. Đối chiếu settings với cấu hình ứng dụng

Không phải mọi setting đều được biểu diễn bằng annotation trên từng field. Settings là cấu hình cấp index và cần được so sánh với cấu hình triển khai.

Ví dụ:

| Cấu hình mong muốn | Nơi thường quản lý | Cách xác nhận |
|---|---|---|
| Số primary shard | Index provisioning hoặc template | _settings |
| Số replica | Index provisioning hoặc cấu hình vận hành | _settings |
| Refresh interval | Index settings | _settings |
| Analyzer tùy chỉnh | Settings analysis và mapping field tham chiếu analyzer | _settings và _mapping |
| Dynamic mapping policy | Mapping root hoặc object property | _mapping |
| Alias đọc/ghi | Index lifecycle/provisioning | Alias API |

Ví dụ một field có mapping:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "product_analyzer"
  }
}
~~~

Chỉ nhìn mapping field chưa đủ để xác nhận analyzer hoạt động như mong muốn. Cần đọc settings analysis để kiểm tra analyzer product_analyzer được định nghĩa bằng tokenizer và token filters nào.

## 9. Index template có thể làm cấu hình thực tế khác Java model

Khi một index được tạo, index template phù hợp có thể áp dụng settings, mappings và aliases cho index đó. Vì vậy index mới có thể nhận cấu hình từ template ngay cả khi entity Java không khai báo các chi tiết đó.

Nếu mapping hoặc settings thực tế khác với @Field hay file cấu hình trong ứng dụng, hãy kiểm tra:

- Index được tạo thủ công, bởi Spring Data hay bởi pipeline nào?
- Có index template nào khớp tên index không?
- Template nào có priority cao hơn?
- Có component template nào cung cấp mapping hoặc settings không?
- Index đã tồn tại từ phiên bản ứng dụng trước hay chưa?
- Một ứng dụng hoặc tiến trình khác có cập nhật mapping không?

Có thể đọc composable index template bằng API:

~~~http
GET /_index_template
~~~

Hoặc lấy một template cụ thể:

~~~http
GET /_index_template/products-template
~~~

Template chủ yếu được áp dụng tại thời điểm tạo index. Thay đổi template không tự động viết lại mapping hoặc settings của index đã tồn tại. Muốn thay đổi index hiện tại, cần thực hiện thao tác cập nhật được Elasticsearch hỗ trợ hoặc tạo index mới theo quy trình migration.

## 10. Cách xử lý khi mapping không khớp

Khi phát hiện sai lệch, trước tiên xác định nguồn tạo ra mapping thực tế. Sau đó phân loại thay đổi:

### 10.1. Bổ sung field mới

Nếu cần thêm một field mới, Elasticsearch thường cho phép thêm field vào mapping hiện có bằng update mapping API, miễn là không vi phạm quy tắc của field hoặc object cha.

~~~http
PUT /products/_mapping
Content-Type: application/json

{
  "properties": {
    "brand": {
      "type": "keyword"
    }
  }
}
~~~

Sau đó cập nhật Java entity để khai báo field tương ứng và triển khai ứng dụng theo trình tự phù hợp.

### 10.2. Đổi kiểu field đã tồn tại

Không thể tùy ý đổi kiểu một field đã được lập chỉ mục, ví dụ từ text sang keyword hoặc từ long sang date. Thay đổi như vậy thường cần:

1. Tạo index mới với mapping đúng.
2. Reindex dữ liệu từ index cũ sang index mới.
3. Kiểm tra số lượng document và các truy vấn quan trọng.
4. Chuyển alias hoặc cấu hình ứng dụng sang index mới.
5. Chỉ xóa index cũ sau khi xác nhận và theo chính sách lưu giữ.

Không nên sửa entity rồi kỳ vọng mapping của index cũ tự thay đổi.

### 10.3. Thay đổi analyzer hoặc settings analysis

Analyzer thường phụ thuộc cấu hình analysis ở cấp index. Một số thay đổi analyzer không thể áp dụng như cập nhật setting động thông thường; có thể cần đóng/mở index theo quy tắc hỗ trợ hoặc tạo index mới và reindex. Với production, quy trình tạo index mới thường dễ kiểm soát và kiểm thử hơn.

### 10.4. Chỉ cập nhật annotation khi index đã được quản lý riêng

Nếu pipeline triển khai là nguồn có thẩm quyền cho mapping, thay đổi entity Java cần đi kèm thay đổi file mapping hoặc migration tương ứng. Nếu chỉ cập nhật annotation, index đang chạy có thể tiếp tục giữ cấu hình cũ.

Ngược lại, nếu dùng repository bootstrap để tự tạo index, cần bảo đảm entity metadata, settings và mapping resource được cập nhật đồng bộ trước khi tạo index mới.

## 11. Quy trình kiểm tra mapping và settings trong dự án

Một quy trình điều tra có thể thực hiện theo thứ tự:

1. Xác định index vật lý mà repository hoặc alias đang truy cập.
2. Đọc mapping bằng GET /index/_mapping.
3. Đọc settings bằng GET /index/_settings?include_defaults=true.
4. Với field cụ thể, đọc GET /index/_mapping/field/fieldName.
5. Xem entity Java, @Document, @Id, @Field, @Setting và @Mapping.
6. Dùng IndexOperations.createMapping() để xem mapping Spring Data suy ra từ entity, nếu API phiên bản đang dùng hỗ trợ.
7. So sánh tên field, kiểu dữ liệu, analyzer, format, nested structure và các tùy chọn quan trọng.
8. Kiểm tra index template hoặc migration nếu cấu hình thực tế có nguồn bên ngoài entity.
9. Phân loại khác biệt thành field có thể bổ sung, setting có thể cập nhật hoặc thay đổi cần reindex.
10. Lập kế hoạch triển khai và xác nhận lại mapping/settings sau thay đổi.

Khi ghi nhận kết quả, nên lưu cả index name, thời điểm kiểm tra và phiên bản Elasticsearch. Điều này giúp so sánh giữa local, staging và production mà không nhầm cấu hình của các môi trường hoặc các index phiên bản khác nhau.

## 12. Ví dụ điều tra một lỗi tìm kiếm sản phẩm

Giả sử ứng dụng có entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    // other fields
}
~~~

Ứng dụng cần sort theo tên và aggregation theo tên chính xác, nhưng truy vấn dùng name.keyword lại báo field không tồn tại hoặc không trả kết quả.

Quy trình điều tra:

**Bước 1: Đọc mapping**

~~~http
GET /products/_mapping/field/name
~~~

Nếu kết quả chỉ có:

~~~json
{
  "name": {
    "type": "text"
  }
}
~~~

thì mapping hiện tại không có sub-field name.keyword.

**Bước 2: So sánh với yêu cầu truy vấn**

Entity khai báo name là text, điều này phù hợp tìm kiếm toàn văn. Tuy nhiên, yêu cầu sort/aggregation chính xác cần một keyword field hoặc một sub-field keyword.

**Bước 3: Xác định nguồn mapping**

Kiểm tra index được tạo từ annotation, mapping file, template hay migration. Nếu mapping được quản lý bởi pipeline, hãy sửa file mapping có thẩm quyền. Nếu index đã tồn tại và cần bổ sung multi-field, đánh giá update mapping phù hợp; dữ liệu cũ có thể cần được reindex để sub-field được lập chỉ mục đầy đủ.

**Bước 4: Xác nhận**

Sau khi cập nhật, đọc lại mapping và chạy thử truy vấn sort/aggregation. Chỉ khi mapping thực tế có name.keyword và dữ liệu đã được lập chỉ mục cho sub-field thì truy vấn mới có thể sử dụng đúng field đó.

Ví dụ này cho thấy entity Java và mapping index cần được đối chiếu với truy vấn thực tế. Kiểu String trong Java không tự quyết định có multi-field hay không.

## 13. Lưu ý khi so sánh giữa các môi trường

Hai môi trường có cùng source code nhưng index khác nhau vẫn có thể cho kết quả tìm kiếm khác nhau. Một số nguyên nhân:

- Index được tạo ở các thời điểm khác nhau, trước và sau khi mapping thay đổi.
- Một môi trường dùng template mới, môi trường kia dùng template cũ.
- Settings mặc định thay đổi theo phiên bản Elasticsearch.
- Dữ liệu đầu tiên được ghi vào môi trường này khiến dynamic mapping suy luận kiểu khác.
- Một môi trường có analyzer hoặc plugin khác.
- Alias trỏ đến các index vật lý khác phiên bản.

Khi so sánh, cần kiểm tra cùng index vật lý hoặc xác định rõ các index đứng sau alias. So sánh cả mapping lẫn settings, đồng thời ghi nhận phiên bản Elasticsearch và template áp dụng. Không nên chỉ so sánh file entity trong Git rồi kết luận hai cluster giống nhau.

## 14. Kết luận

Mapping cho biết Elasticsearch hiểu field và cấu trúc document như thế nào; settings cho biết index được cấu hình và vận hành ra sao. Spring Data Elasticsearch cung cấp IndexOperations để đọc mapping/settings và tạo mapping dự kiến từ entity metadata. REST API vẫn là cách trực tiếp để kiểm tra cấu hình đang có hiệu lực trên cluster, bao gồm cả giá trị mặc định.

Hãy đối chiếu mapping thực tế với @Document, @Id, @Field và các file cấu hình của dự án. Kiểm tra cả kiểu field, analyzer, format, multi-fields, nested structure, dynamic mapping và settings liên quan. Khi phát hiện khác biệt, xác định nguồn tạo index trước rồi chọn cách cập nhật phù hợp; đổi kiểu field hoặc thay đổi cấu trúc quan trọng thường cần index mới và reindex.

Việc đọc mapping và settings nên là một phần của quy trình triển khai và điều tra sự cố. Entity Java mô tả cách ứng dụng làm việc với document, còn mapping/settings trên cluster mới cho biết index hiện tại thực sự đang hoạt động theo cấu hình nào.
