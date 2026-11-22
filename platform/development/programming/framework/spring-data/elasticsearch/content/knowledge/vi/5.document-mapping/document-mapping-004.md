# @Setting, @Mapping và nạp cấu hình từ tài nguyên

Trong Spring Data Elasticsearch, một lớp tài liệu mô tả dữ liệu Java được lưu trong Elasticsearch. Ngoài các trường dữ liệu, index còn cần **settings** và **mapping** để xác định cách lưu trữ, phân tích và tìm kiếm tài liệu. Spring Data Elasticsearch cho phép khai báo hai phần này bằng annotation **@Setting** và **@Mapping**, đồng thời đọc cấu hình từ các tệp JSON đặt trong resources của ứng dụng.

Bài này dùng ví dụ index **products**. Tên sản phẩm cần tìm kiếm toàn văn, mã SKU và danh mục cần so khớp chính xác, giá cần truy vấn theo khoảng và ngày tạo cần được nhận diện là kiểu ngày. Ta sẽ tách cấu hình index ra khỏi mã Java để dễ quản lý và thay đổi.

## 1. Phân biệt settings và mapping

Settings và mapping cùng thuộc cấu hình của một index nhưng giải quyết hai vấn đề khác nhau.

**Settings** cấu hình cách Elasticsearch tổ chức và xử lý index. Một số thiết lập thường gặp:

- Số primary shard và replica.
- Refresh interval, tức khoảng thời gian Elasticsearch làm mới dữ liệu có thể tìm kiếm.
- Analyzer, tokenizer và token filter dùng khi phân tích văn bản.
- Các tùy chọn liên quan đến lưu trữ và xử lý dữ liệu của index.

**Mapping** định nghĩa cấu trúc tài liệu và kiểu dữ liệu của từng trường. Mapping cho Elasticsearch biết trường nào là văn bản, trường nào là giá trị chính xác, số, ngày giờ hoặc kiểu dữ liệu khác. Nó cũng có thể gắn analyzer cho trường văn bản.

Ví dụ, nếu trường **name** là **text**, Elasticsearch phân tích nội dung thành các token để tìm kiếm toàn văn. Nếu trường **category** là **keyword**, Elasticsearch giữ nguyên giá trị để lọc chính xác hoặc nhóm kết quả. Chọn sai kiểu có thể khiến truy vấn trả về kết quả không như mong muốn.

| Nội dung | Settings | Mapping |
|---|---|---|
| Mục đích | Cấu hình hoạt động và xử lý của index | Khai báo kiểu và cấu trúc các trường tài liệu |
| Ví dụ | Số shard, replica, refresh interval, analyzer | text, keyword, long, date, scaled_float |
| Thành phần liên quan | Analyzer, tokenizer, filter | Properties, field type, format, analyzer |
| Thời điểm áp dụng | Khi tạo index; một số setting có thể đổi sau đó theo quy tắc Elasticsearch | Khi tạo mapping; nhiều thay đổi kiểu trường cần index mới |

Settings và mapping phải nhất quán với nhau. Nếu mapping chỉ định một analyzer có tên **product_name_analyzer**, settings phải khai báo analyzer đó. Nếu không, Elasticsearch sẽ báo lỗi khi tạo mapping hoặc index.

## 2. Tổ chức tệp cấu hình trong resources

Có thể đặt các tệp JSON trong **src/main/resources** theo cấu trúc:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/catalog/
    │       ├── Product.java
    │       └── ProductRepository.java
    └── resources/
        └── elasticsearch/
            ├── settings/
            │   └── products-settings.json
            └── mappings/
                └── products-mapping.json
~~~

Các tệp nằm trong **src/main/resources** được đưa vào classpath khi ứng dụng được đóng gói. Vì vậy, ứng dụng có thể đọc chúng cả khi chạy từ IDE lẫn khi chạy từ JAR, miễn là đường dẫn được khai báo đúng.

Trong annotation, ta thường dùng đường dẫn bắt đầu bằng dấu **/**, tính từ gốc classpath. Ví dụ:

- **/elasticsearch/settings/products-settings.json**
- **/elasticsearch/mappings/products-mapping.json**

Tên thư mục và tên tệp phải khớp chính xác, kể cả chữ hoa và chữ thường khi ứng dụng chạy trên hệ thống tệp phân biệt hoa thường.

## 3. Khai báo settings trong tệp JSON

Tạo tệp **src/main/resources/elasticsearch/settings/products-settings.json**:

~~~json
{
  "index": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "refresh_interval": "1s",
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
  }
}
~~~

Giải thích cấu hình:

- **number_of_shards** chỉ định số primary shard của index. Đây là quyết định thiết kế cần cân nhắc theo dung lượng và tải dữ liệu; không nên sao chép giá trị ví dụ cho mọi môi trường.
- **number_of_replicas** chỉ định số bản sao replica cho mỗi primary shard. Giá trị 0 thường tiện cho môi trường phát triển một node; môi trường vận hành cần cân nhắc tính sẵn sàng và tài nguyên.
- **refresh_interval** đặt chu kỳ refresh. Giá trị ngắn giúp tài liệu mới xuất hiện trong tìm kiếm sớm hơn nhưng có thể tăng chi phí xử lý ghi.
- **analysis.analyzer** khai báo analyzer tùy chỉnh có tên **product_name_analyzer**.
- **tokenizer: standard** chia văn bản thành token theo quy tắc của standard tokenizer.
- **lowercase** chuyển token về chữ thường.
- **asciifolding** chuyển nhiều ký tự có dấu về dạng ASCII tương ứng, hữu ích với một số trường hợp tìm kiếm không dấu. Cần kiểm thử ngôn ngữ và yêu cầu tìm kiếm của ứng dụng trước khi chọn filter này.

Analyzer được đặt tên trong settings để mapping có thể tham chiếu đến nó. Có thể khai báo nhiều analyzer, tokenizer và filter nếu ứng dụng cần các cách phân tích khác nhau cho các trường.

Cấu hình shard và một số setting khác có quy tắc thay đổi riêng. Chẳng hạn, số primary shard không thể tùy ý đổi trực tiếp trên index đã tồn tại. Hãy xác định cấu hình phù hợp trước khi tạo index và lập kế hoạch chuyển dữ liệu nếu cần thay đổi về sau.

## 4. Khai báo mapping trong tệp JSON

Tạo tệp **src/main/resources/elasticsearch/mappings/products-mapping.json**:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text",
      "analyzer": "product_name_analyzer",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "description": {
      "type": "text",
      "analyzer": "standard"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Trong tệp trên:

- **sku** dùng **keyword** vì mã SKU thường cần so khớp nguyên vẹn.
- **name** dùng **text** và analyzer đã khai báo trong settings để tìm kiếm toàn văn.
- **name.keyword** là multi-field, cho phép dùng cùng nội dung tên sản phẩm để lọc chính xác, sắp xếp hoặc nhóm.
- **category** dùng **keyword** để lọc theo danh mục.
- **description** dùng **text** để tìm kiếm nội dung mô tả.
- **price** dùng **double** để lưu giá trị số thực trong ví dụ.
- **createdAt** dùng **date**, chấp nhận chuỗi ngày giờ theo định dạng chỉ định hoặc epoch milliseconds.

Tệp mapping ở đây chứa trực tiếp đối tượng **properties**. Đây là nội dung mapping được truyền cho thao tác tạo mapping của Spring Data Elasticsearch; không bọc thêm trong một đối tượng **mappings** như khi viết toàn bộ request tạo index bằng REST API.

Mapping phải mô tả đúng tên trường mà ứng dụng ghi vào tài liệu. Ví dụ Java dùng thuộc tính **createdAt**, nên mapping cũng khai báo **createdAt**. Nếu ứng dụng có quy tắc đổi tên trường khi chuyển đổi dữ liệu, tên trong mapping phải khớp với tên thực tế được lưu trong Elasticsearch.

**Double** thuận tiện cho ví dụ, nhưng không phải lựa chọn tối ưu cho mọi dữ liệu tiền tệ vì số thực nhị phân có thể có sai số biểu diễn. Với giá trị cần độ chính xác thập phân, hãy cân nhắc lưu theo đơn vị nhỏ nhất dưới dạng số nguyên hoặc dùng mapping **scaled_float** với hệ số phù hợp; khi đó cần đồng bộ kiểu Java, annotation và mapping JSON.

## 5. Gắn @Setting và @Mapping vào lớp tài liệu

Spring Data Elasticsearch cung cấp annotation **@Setting** và **@Mapping** trong package **org.springframework.data.elasticsearch.annotations**. Hai annotation này cho phép chỉ định tài nguyên chứa cấu hình index.

Ví dụ lớp **Product**:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Mapping;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = true)
@Setting(settingPath = "/elasticsearch/settings/products-settings.json")
@Mapping(mappingPath = "/elasticsearch/mappings/products-mapping.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text, analyzer = "product_name_analyzer")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    public Product() {
    }

    // Constructor, getter và setter được lược bỏ để tập trung vào mapping.
}
~~~

Ý nghĩa của các annotation:

- **@Document(indexName = "products")** xác định index mà lớp tài liệu đại diện.
- **createIndex = true** cho phép Spring Data Elasticsearch tạo index khi index chưa tồn tại trong quá trình khởi tạo metadata/repository theo cấu hình của ứng dụng.
- **@Setting(settingPath = "...")** chỉ định tệp settings cần nạp từ classpath.
- **@Mapping(mappingPath = "...")** chỉ định tệp mapping cần nạp từ classpath.
- **@Id** ánh xạ thuộc tính định danh Java vào **_id** của Elasticsearch.
- **@Field** khai báo metadata kiểu trường cho Spring Data.

Trong ví dụ, mapping JSON là cấu hình chi tiết của index. Các annotation **@Field** trên lớp Java giúp thể hiện ý định ánh xạ ở phía mã nguồn; chúng cần thống nhất với tệp JSON. Nếu JSON quy định **name** là **text** với analyzer tùy chỉnh thì annotation cũng cần chỉ định cùng analyzer, ví dụ **@Field(type = FieldType.Text, analyzer = "product_name_analyzer")**. Khi dùng mapping ngoài làm nguồn cấu hình chính, hãy bảo đảm các kiểu trường trong JSON là kiểu thực tế được Elasticsearch sử dụng.

Không nên khai báo cùng một trường theo hai cách mâu thuẫn. Chẳng hạn, nếu JSON quy định **price** là **scaled_float** nhưng mã Java mô tả trường đó theo kiểu khác, nhóm phát triển sẽ khó xác định cấu hình nào là chủ đích. Hãy thống nhất một nguồn cấu hình chính, sau đó giữ metadata Java tương thích với nó.

## 6. Nạp cấu hình và tạo index

Khi Spring Data Elasticsearch cần tạo index cho lớp tài liệu, metadata của lớp được dùng để lấy thông tin index, settings và mapping. Hai đường dẫn trong **@Setting** và **@Mapping** cho phép Spring Data nạp nội dung từ các tài nguyên tương ứng.

Trong trường hợp muốn chủ động kiểm soát thời điểm tạo index, có thể dùng **ElasticsearchOperations** và **IndexOperations**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void initialize() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

**indexOps(Product.class)** lấy đối tượng thao tác index dựa trên metadata của lớp **Product**. **exists()** kiểm tra index đã tồn tại hay chưa. **createWithMapping()** tạo index với settings và mapping được khai báo cho lớp tài liệu.

Có thể gọi phương thức **initialize()** từ một thành phần chạy lúc ứng dụng khởi động, chẳng hạn **ApplicationRunner** hoặc **CommandLineRunner**. Nếu ứng dụng đã bật cơ chế tự tạo index của repository, cần chọn một nơi quản lý việc khởi tạo để tránh thực hiện các thao tác tạo index trùng lặp.

Ví dụ tích hợp với **ApplicationRunner**:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ElasticsearchInitializer implements ApplicationRunner {

    private final ProductIndexInitializer productIndexInitializer;

    public ElasticsearchInitializer(
            ProductIndexInitializer productIndexInitializer) {
        this.productIndexInitializer = productIndexInitializer;
    }

    @Override
    public void run(ApplicationArguments args) {
        productIndexInitializer.initialize();
    }
}
~~~

Trong ứng dụng thực tế, cần xác định rõ thành phần nào chịu trách nhiệm tạo index. Với hệ thống mà index được quản lý bằng công cụ triển khai hoặc quy trình migration riêng, có thể đặt **createIndex = false** và không tự động tạo index từ ứng dụng. Khi đó, quy trình triển khai phải tạo index với đúng settings và mapping trước khi ứng dụng ghi dữ liệu.

## 7. Dùng mapping từ annotation hay từ tệp tài nguyên?

Spring Data Elasticsearch có thể xây dựng mapping dựa trên metadata của lớp tài liệu, ví dụ **@Field**, hoặc nạp mapping tường minh từ tài nguyên được chỉ định bởi **@Mapping**.

Dùng mapping từ annotation thường phù hợp khi:

- Cấu trúc tài liệu đơn giản.
- Mapping có ít tùy chọn đặc biệt.
- Muốn giữ mô tả kiểu trường gần với thuộc tính Java.
- Không cần quản lý analyzer hoặc cấu hình mapping phức tạp.

Dùng tệp mapping riêng thường phù hợp khi:

- Mapping có nhiều trường và multi-field.
- Cần khai báo analyzer, normalizer hoặc các tùy chọn Query DSL chuyên biệt.
- Muốn tách cấu hình index khỏi lớp Java.
- Cần xem xét và quản lý cấu hình Elasticsearch như một tài nguyên riêng.

Tương tự, **@Setting** có thể trỏ đến tệp JSON để khai báo analyzer, tokenizer, filter và các setting khác. Việc tách file giúp cấu hình dễ đọc và dễ kiểm soát thay đổi.

Không nên khai báo cùng một trường theo hai cách mâu thuẫn. Hãy thống nhất một nguồn cấu hình chính, sau đó giữ metadata Java tương thích với nó.

## 8. Kiểm tra cấu hình sau khi tạo index

Sau khi index được tạo, có thể kiểm tra settings và mapping bằng Elasticsearch Dev Tools hoặc REST API.

Đọc settings:

~~~http
GET /products/_settings
~~~

Đọc mapping:

~~~http
GET /products/_mapping
~~~

Trong kết quả, kiểm tra các điểm sau:

- Index **products** đã được tạo.
- **number_of_shards**, **number_of_replicas** và **refresh_interval** có giá trị như mong đợi.
- Analyzer **product_name_analyzer** đã được khai báo.
- Trường **name** sử dụng analyzer đó.
- Trường **name.keyword** có kiểu **keyword**.
- Trường **category** là **keyword**.
- Trường **price** có kiểu **double**.
- Trường **createdAt** là **date** với format đã khai báo.

Có thể thử một truy vấn tìm kiếm để xác nhận analyzer hoạt động:

~~~http
POST /products/_analyze
{
  "analyzer": "product_name_analyzer",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch trả về danh sách token sau khi phân tích. Đây là cách hữu ích để xác nhận tokenizer và filter đang hoạt động theo cấu hình.

Nếu kết quả mapping không đúng như mong đợi, hãy kiểm tra đường dẫn tài nguyên, nội dung JSON và thời điểm index được tạo. Đọc mapping thực tế từ Elasticsearch là cách xác nhận cấu hình đã được áp dụng, thay vì chỉ kiểm tra annotation trong mã Java.

## 9. Thay đổi settings và mapping sau khi index đã tồn tại

Một điểm quan trọng là **@Setting** và **@Mapping** được dùng trong quá trình tạo index. Khi index đã tồn tại, việc sửa tệp JSON hoặc annotation không tự động cập nhật cấu trúc index đang chạy.

Có thể phân biệt các trường hợp:

- Một số setting có thể thay đổi trực tiếp theo API cập nhật settings của Elasticsearch.
- Một số setting chỉ có hiệu lực khi tạo index hoặc cần đóng index trước khi cập nhật.
- Thay đổi kiểu dữ liệu của một trường mapping thường không thể thực hiện trực tiếp trên index đã có dữ liệu.
- Thay đổi analyzer hoặc cách phân tích văn bản thường cần tạo index mới và lập chỉ mục lại dữ liệu để áp dụng nhất quán.

Quy trình phổ biến khi cần thay đổi mapping quan trọng:

1. Tạo index mới, ví dụ **products-v2**, với settings và mapping mới.
2. Dùng reindex hoặc quy trình đồng bộ phù hợp để chuyển tài liệu từ index cũ sang index mới.
3. Kiểm tra số lượng tài liệu, mapping và kết quả tìm kiếm trên index mới.
4. Chuyển alias hoặc cấu hình ứng dụng sang index mới.
5. Chỉ xóa index cũ sau khi đã xác nhận việc chuyển đổi hoàn tất và đáp ứng yêu cầu lưu giữ dữ liệu.

Trong hệ thống cần triển khai liên tục, nên cân nhắc dùng alias làm tên index ổn định cho ứng dụng. Mỗi lần thay đổi mapping lớn, ứng dụng có thể chuyển alias sang index phiên bản mới sau khi reindex và kiểm tra xong.

## 10. Lỗi thường gặp khi nạp cấu hình từ resources

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy tệp settings hoặc mapping | Sai đường dẫn, sai chữ hoa/chữ thường hoặc tệp không nằm trong resources | Kiểm tra vị trí dưới **src/main/resources** và đường dẫn classpath trong annotation |
| JSON không hợp lệ | Thiếu dấu phẩy, ngoặc hoặc sai cấu trúc JSON | Kiểm tra cú pháp và cấu trúc theo Elasticsearch API |
| Không nhận diện analyzer | Mapping tham chiếu tên analyzer chưa được khai báo trong settings | Đảm bảo analyzer tồn tại trong settings của cùng index |
| Tạo index báo lỗi mapping | Kiểu trường, analyzer hoặc format không hợp lệ | Đọc phản hồi lỗi từ Elasticsearch và đối chiếu JSON |
| Sửa tệp nhưng mapping thực tế không đổi | Index đã tồn tại nên không chạy lại quy trình tạo index | Kiểm tra mapping hiện tại; dùng quy trình cập nhật hoặc tạo index mới khi cần |
| Ứng dụng chạy được trong IDE nhưng lỗi khi đóng gói | Tệp tài nguyên không được đưa vào artifact hoặc đường dẫn sai | Kiểm tra nội dung JAR và cấu hình build resources |
| Mapping trong JSON không khớp tài liệu Java | Tên trường hoặc kiểu dữ liệu giữa hai phần không thống nhất | Đồng bộ tên trường, kiểu dữ liệu và quy tắc chuyển đổi |

Khi gặp lỗi, nên xem log khởi động và phản hồi chi tiết của Elasticsearch. Lỗi đọc tài nguyên thường xảy ra trước khi gửi request tạo index; lỗi mapping hoặc analyzer thường xuất hiện trong phản hồi từ Elasticsearch. Phân biệt hai nhóm này giúp khoanh vùng nhanh hơn.

## 11. Ví dụ sử dụng repository sau khi index đã sẵn sàng

Sau khi index **products** đã có settings và mapping, repository có thể sử dụng như các thao tác Spring Data Elasticsearch thông thường:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findBySku(String sku);
}
~~~

Lưu tài liệu:

~~~java
Product product = new Product();
// Thiết lập SKU, tên, danh mục, giá và ngày tạo.
productRepository.save(product);
~~~

Tìm theo danh mục hoặc SKU sẽ dựa vào mapping tương ứng. Tìm kiếm toàn văn trên **name** có thể dùng truy vấn **match** để Elasticsearch phân tích nội dung theo **product_name_analyzer**. Nếu cần so khớp chính xác tên, dùng trường con **name.keyword** trong Query DSL.

Ví dụ truy vấn REST tìm kiếm toàn văn:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Ví dụ lọc danh mục chính xác và khoảng giá:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Hai ví dụ trên cho thấy mapping quyết định cách Elasticsearch hiểu từng trường trong truy vấn. **match** phù hợp với văn bản được phân tích; **term** phù hợp với giá trị chính xác; **range** dùng để lọc khoảng số hoặc thời gian.

## 12. Lưu ý về phiên bản và môi trường triển khai

Các annotation **@Setting** và **@Mapping** là cách khai báo metadata index ở tầng Spring Data Elasticsearch. Tuy nhiên, cấu hình client, API thao tác index và một số kiểu dữ liệu có thể thay đổi giữa các phiên bản Spring Data Elasticsearch và Elasticsearch.

Khi áp dụng vào dự án:

- Dùng phiên bản Spring Data Elasticsearch được Spring Boot quản lý hoặc được xác định rõ trong dependency management.
- Đối chiếu tài liệu của đúng phiên bản về thuộc tính annotation và API của **IndexOperations**.
- Kiểm tra phiên bản Elasticsearch đích có hỗ trợ analyzer, field type và setting đã khai báo.
- Thử tạo index trên môi trường phát triển trước khi triển khai cấu hình mới.
- Quản lý thông tin xác thực, TLS và quyền tạo index bằng cấu hình môi trường an toàn.
- Tránh để nhiều instance ứng dụng đồng thời chạy các migration index không được điều phối.

Tách settings và mapping thành tệp JSON giúp cấu hình Elasticsearch dễ đọc, dễ xem xét và có thể đóng gói cùng ứng dụng. **@Setting** xác định tài nguyên cấu hình hoạt động của index; **@Mapping** xác định tài nguyên mô tả trường dữ liệu. Khi hai tệp được khai báo đúng trên lớp **@Document**, Spring Data Elasticsearch có thể sử dụng chúng trong quá trình tạo index. Việc quản lý thay đổi sau đó cần dựa trên vòng đời index và quy tắc mapping của Elasticsearch.
