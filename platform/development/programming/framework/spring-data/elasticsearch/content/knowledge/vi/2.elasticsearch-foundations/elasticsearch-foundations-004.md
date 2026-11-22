# Mapping tường minh, dynamic mapping và dynamic templates

Trong Elasticsearch, mapping mô tả cách mỗi trường trong tài liệu được lưu trữ, phân tích và lập chỉ mục. Mapping quyết định một chuỗi được tách thành các token để tìm kiếm toàn văn hay được giữ nguyên để lọc chính xác; một giá trị ngày được hiểu theo định dạng nào; một đối tượng con được xử lý như object hay nested; và những trường mới xuất hiện trong tài liệu sẽ được xử lý ra sao.

Spring Data Elasticsearch cung cấp annotation và API để tạo mapping từ lớp Java, đồng thời cho phép dùng tệp JSON mapping của Elasticsearch. Dù khai báo bằng Java hay JSON, các quy tắc cuối cùng vẫn do Elasticsearch thực thi. Vì vậy, cần hiểu cả mapping của Elasticsearch lẫn cách Spring Data chuyển metadata của entity thành mapping.

Sau bài học này, bạn có thể:

- Giải thích vai trò của mapping và lý do nên xác định kiểu trường trước khi ghi dữ liệu.
- Khai báo mapping tường minh bằng JSON và annotation của Spring Data Elasticsearch.
- Mô tả cách Elasticsearch tự suy luận mapping khi gặp trường mới.
- Chọn giữa dynamic mapping bật, tắt hoặc strict.
- Viết dynamic templates để áp dụng quy tắc mapping có kiểm soát cho các trường mới.
- Kết hợp các cơ chế trên để hỗ trợ dữ liệu linh hoạt mà vẫn giữ được cấu trúc ổn định.

## 1. Mapping là gì?

Elasticsearch lưu dữ liệu dưới dạng các document JSON trong index. Mapping là phần định nghĩa cấu trúc và cách xử lý các trường của document. Mỗi trường có một kiểu dữ liệu, có thể kèm các thiết lập như analyzer, normalizer, định dạng ngày, trường con hoặc cách xử lý object.

Ví dụ, một document sản phẩm có thể trông như sau:

~~~json
{
  "sku": "KB-1042",
  "name": "Mechanical Keyboard",
  "price": 129.90,
  "createdAt": "2026-10-20T09:30:00Z",
  "attributes": {
    "layout": "US",
    "switchCount": 87
  }
}
~~~

Mapping có thể quy định:

- sku là keyword để so khớp chính xác, sắp xếp và aggregation.
- name là text để phân tích thành token khi tìm kiếm toàn văn; có thể có thêm trường keyword để lọc chính xác.
- price là kiểu số để lọc theo khoảng và tính toán aggregation.
- createdAt là date để sắp xếp và truy vấn theo thời gian.
- attributes là object chứa các trường con.

Elasticsearch có thể tự tạo mapping khi nhận trường mới, nhưng mapping được tạo ra sẽ ảnh hưởng đến cách dữ liệu của trường đó được lập chỉ mục về sau. Một khi trường đã có kiểu dữ liệu, không thể đổi trực tiếp sang kiểu không tương thích chỉ bằng cách cập nhật mapping.

### 1.1. Kiểu text và keyword

Hai kiểu thường gặp nhất với chuỗi là text và keyword:

| Kiểu | Cách xử lý | Trường hợp sử dụng |
| --- | --- | --- |
| text | Được analyzer phân tích thành token | Tìm kiếm nội dung, mô tả, tiêu đề |
| keyword | Giữ nguyên giá trị như một đơn vị | Mã định danh, trạng thái, nhãn, lọc chính xác, sort và aggregation |

Ví dụ, với giá trị Mechanical Keyboard, trường text có thể được phân tích thành các token mechanical và keyboard. Trường keyword giữ nguyên Mechanical Keyboard. Truy vấn match thường dùng cho text; truy vấn term thường dùng cho keyword.

Một trường có thể có nhiều cách lập chỉ mục thông qua multi-fields. Ví dụ, name có kiểu text và có thêm name.keyword kiểu keyword. Nhờ vậy, cùng một dữ liệu có thể phục vụ cả tìm kiếm toàn văn và lọc hoặc sắp xếp chính xác.

## 2. Mapping tường minh

Mapping tường minh (explicit mapping) là mapping được khai báo trước khi Elasticsearch phải tự suy luận kiểu trường. Đây là lựa chọn phù hợp cho các trường nghiệp vụ đã biết, đặc biệt là trường được dùng trong truy vấn, sắp xếp, aggregation hoặc tích hợp với hệ thống khác.

### 2.1. Khai báo mapping bằng Elasticsearch JSON

Có thể tạo index và khai báo mapping trong cùng một request:

~~~http
PUT /catalog-v1
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "createdAt": {
        "type": "date"
      },
      "attributes": {
        "type": "object",
        "dynamic": true
      }
    }
  }
}
~~~

Trong ví dụ này:

- sku được khai báo là keyword.
- name được phân tích bằng analyzer standard và có trường con keyword.
- price dùng scaled_float với scaling_factor bằng 100, phù hợp khi cần lưu số thập phân theo độ chính xác đến hai chữ số sau dấu thập phân.
- createdAt được khai báo là date.
- Mapping ở cấp document dùng dynamic strict. Riêng object attributes cho phép dynamic mapping để nhận các thuộc tính mở rộng.

Khai báo kiểu rõ ràng giúp tránh việc cùng một trường bị suy luận khác nhau do dữ liệu đầu vào. Ví dụ, nếu trường price lần đầu nhận chuỗi "129.90", Elasticsearch có thể tạo mapping kiểu chuỗi; khi ứng dụng gửi số vào trường đó sau này, dữ liệu có thể không được lập chỉ mục như mong muốn hoặc bị từ chối.

### 2.2. Khai báo mapping bằng annotation Spring Data Elasticsearch

Với Spring Data Elasticsearch, có thể khai báo metadata trên entity. Spring Data dùng metadata này khi tạo mapping cho index:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "catalog-v1", createIndex = true)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Scaled_Float, scalingFactor = 100)
    private BigDecimal price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Object)
    private Map<String, Object> attributes;

    // Constructors, getters và setters
}
~~~

Các annotation quan trọng:

- @Document xác định index đích cho entity. createIndex cho biết Spring Data có tự tạo index khi khởi tạo mapping hay không.
- @Id đánh dấu thuộc tính được dùng làm Elasticsearch document ID.
- @Field xác định kiểu và các thuộc tính mapping của một trường.
- @MultiField kết hợp trường chính với một hoặc nhiều trường con. Trong ví dụ, name là text và name.keyword là keyword.
- @InnerField khai báo một trường con trong multi-fields.

Ví dụ trên minh họa metadata thường dùng. Với dữ liệu tiền tệ cần độ chính xác cụ thể, hãy chọn kiểu và scaling factor phù hợp trong mapping JSON, đồng thời thống nhất cách biểu diễn giá trị trong Java. Không nên mặc định rằng mọi kiểu số thập phân đều có cùng hành vi làm tròn.

### 2.3. Dùng tệp JSON mapping trong Spring Data

Khi mapping có nhiều thiết lập, dynamic templates hoặc cấu trúc lồng nhau phức tạp, tệp JSON thường dễ đọc và gần với cấu hình Elasticsearch gốc hơn. Spring Data Elasticsearch hỗ trợ chỉ định tệp mapping bằng @Mapping:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;

@Document(indexName = "catalog-v1", createIndex = true)
@Mapping(mappingPath = "/mappings/catalog-mapping.json")
public class Product {
    // Các thuộc tính của entity
}
~~~

Tệp catalog-mapping.json chứa nội dung mapping theo định dạng Elasticsearch, với các thuộc tính ở cấp gốc như dynamic, properties và dynamic_templates. Ví dụ, cấu trúc rút gọn của tệp có thể là:

~~~json
{
  "dynamic": "strict",
  "properties": {
    "sku": {
      "type": "keyword"
    }
  },
  "dynamic_templates": [
    {
      "attribute_strings": {
        "path_match": "attributes.*",
        "match_mapping_type": "string",
        "mapping": {
          "type": "keyword"
        }
      }
    }
  ]
}
~~~

Đường dẫn được đặt trong tài nguyên ứng dụng để Spring Data có thể đọc khi tạo mapping.

Có thể quản lý index thông qua ElasticsearchOperations và IndexOperations. Trong ví dụ dưới đây, operations là một ElasticsearchOperations đã được inject:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

Đoạn mã minh họa việc tạo index cùng mapping lấy từ metadata của entity. Với hệ thống thực tế, cần xác định rõ thành phần nào chịu trách nhiệm tạo index: ứng dụng Spring, quy trình migration hay cấu hình index template của Elasticsearch. Tránh để nhiều thành phần cùng tạo một index với mapping khác nhau.

Nếu dùng mapping JSON tùy chỉnh, hãy xem tệp đó là một phần của schema và quản lý thay đổi cùng mã nguồn. Đồng thời kiểm tra hành vi của phiên bản Spring Data Elasticsearch đang dùng, đặc biệt khi kết hợp mapping tùy chỉnh với mapping được sinh từ annotation.

## 3. Dynamic mapping

Dynamic mapping là cơ chế Elasticsearch tự thêm mapping cho trường chưa được khai báo khi nhận document có trường đó. Cơ chế này giúp bắt đầu nhanh và phù hợp với dữ liệu có cấu trúc thay đổi, nhưng việc suy luận kiểu dựa trên giá trị Elasticsearch nhìn thấy đầu tiên.

Giả sử index chưa có trường stockCount. Ứng dụng gửi:

~~~json
{
  "sku": "KB-1042",
  "stockCount": 87
}
~~~

Nếu dynamic mapping được bật, Elasticsearch suy luận stockCount là trường số nguyên và thêm nó vào mapping. Các document sau đó sẽ được xử lý theo kiểu đã được tạo.

### 3.1. Các chế độ dynamic

Thiết lập dynamic có thể được đặt ở cấp mapping hoặc trên một object cụ thể:

| Giá trị | Hành vi khi gặp trường chưa khai báo |
| --- | --- |
| true | Tự thêm trường vào mapping và lập chỉ mục giá trị |
| false | Không thêm trường vào mapping; giá trị vẫn có thể nằm trong _source nhưng không được lập chỉ mục để tìm kiếm |
| strict | Từ chối document có trường chưa khai báo bằng lỗi mapping |

Nếu không chỉ định, dynamic mặc định là true. Ví dụ:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "attributes": {
        "type": "object",
        "dynamic": true
      }
    }
  }
}
~~~

Với cấu hình này, trường lạ ở cấp document sẽ bị từ chối. Các trường con mới trong attributes vẫn được phép tạo mapping tự động. Cách đặt chế độ ở từng cấp giúp giữ phần schema cốt lõi ổn định trong khi cho phép một vùng dữ liệu mở rộng.

Lưu ý: dynamic false không có nghĩa là Elasticsearch xóa trường khỏi document nguồn. Trường đó vẫn có thể xuất hiện trong _source, nhưng không được thêm vào mapping và không thể truy vấn như một trường đã được lập chỉ mục thông thường.

### 3.2. Elasticsearch suy luận kiểu như thế nào?

Với dynamic mapping, Elasticsearch xem kiểu JSON và áp dụng quy tắc suy luận. Một số trường hợp phổ biến:

| Giá trị JSON đầu tiên | Kiểu mapping thường được tạo |
| --- | --- |
| Chuỗi khớp định dạng ngày được nhận diện | date |
| Chuỗi thông thường | text kèm multi-field keyword |
| Số nguyên | long |
| Số thập phân | double |
| true hoặc false | boolean |
| Object JSON | object |
| Mảng | Suy luận từ phần tử khác null đầu tiên |
| null hoặc mảng rỗng | Chưa đủ thông tin để tạo mapping cho trường |

Elasticsearch bật date detection mặc định, vì vậy một chuỗi trông giống ngày có thể được suy luận thành date. Numeric detection mặc định tắt, nên chuỗi chứa chữ số không tự động trở thành kiểu số chỉ vì nội dung của nó trông giống một con số.

Ví dụ, document đầu tiên gửi giá trị:

~~~json
{
  "releaseDate": "2026-10-20"
}
~~~

Có thể khiến releaseDate được tạo thành kiểu date. Nếu một document khác gửi chuỗi không phải ngày vào cùng trường, dữ liệu có thể gây lỗi phân tích ngày. Tương tự, nếu một trường được tạo thành long thì một giá trị văn bản như "unknown" không thể được lập chỉ mục như một số long.

Mảng không có kiểu mapping riêng. Elasticsearch suy luận kiểu từ phần tử khác null đầu tiên rồi dùng kiểu đó cho trường. Vì vậy, mảng trộn nhiều kiểu như [12, "unknown"] có thể gây lỗi khi phần tử không tương thích được lập chỉ mục.

### 3.3. Rủi ro khi phụ thuộc hoàn toàn vào dynamic mapping

Dynamic mapping thuận tiện nhưng có một số rủi ro cần kiểm soát:

1. **Suy luận sai ý nghĩa trường.** Một mã sản phẩm chỉ gồm chữ số có thể bị hiểu là số, trong khi ứng dụng cần giữ số 0 ở đầu và so khớp chính xác. Trường mã thường nên được khai báo keyword.
2. **Xung đột kiểu dữ liệu.** Document đầu tiên có thể tạo trường thành date hoặc long, trong khi dữ liệu đến sau có định dạng khác. Elasticsearch không tự đổi kiểu đã có.
3. **Mapping explosion.** Nếu mỗi document tạo ra nhiều tên trường khác nhau, mapping sẽ phình to. Điều này làm tăng bộ nhớ và chi phí quản lý cluster; số lượng field cũng chịu giới hạn cấu hình.
4. **Khác biệt giữa các index.** Nếu nhiều index được tạo từ dữ liệu đến theo thứ tự khác nhau, cùng một tên trường có thể có mapping khác nhau. Truy vấn trên alias trỏ tới nhiều index khi đó có thể gặp lỗi hoặc hành vi không đồng nhất.
5. **Khó thay đổi schema.** Mapping đã được tạo không thể tùy ý đổi kiểu. Thay đổi không tương thích thường cần tạo index mới và reindex dữ liệu.

Do đó, dynamic mapping phù hợp nhất với phần dữ liệu thật sự linh hoạt và có quy tắc. Các trường nghiệp vụ cốt lõi nên được khai báo tường minh.

## 4. Dynamic templates

Dynamic templates cho phép định nghĩa quy tắc để Elasticsearch tạo mapping cho trường mới dựa trên tên trường, đường dẫn hoặc kiểu dữ liệu mà Elasticsearch suy luận. Có thể xem chúng là bộ quy tắc tùy biến cho dynamic mapping.

Dynamic templates chỉ được xét khi Elasticsearch gặp một trường chưa có mapping. Nếu trường đã được khai báo tường minh, mapping tường minh đó được sử dụng. Template cũng không tự chuyển đổi mapping của trường đã tồn tại.

### 4.1. Cấu trúc một dynamic template

Một dynamic template có tên, các điều kiện khớp và phần mapping cần áp dụng:

~~~json
{
  "mappings": {
    "dynamic_templates": [
      {
        "codes_as_keyword": {
          "match": "*_code",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      }
    ]
  }
}
~~~

Trong ví dụ này, trường mới có tên kết thúc bằng _code và được Elasticsearch nhận diện là string sẽ được tạo thành keyword. Ví dụ, supplier_code và country_code khớp quy tắc này.

Các điều kiện thường dùng:

| Điều kiện | Ý nghĩa |
| --- | --- |
| match | Khớp tên trường theo mẫu wildcard |
| unmatch | Loại trừ tên trường khớp mẫu |
| path_match | Khớp đường dẫn đầy đủ của trường, hữu ích với object lồng nhau |
| path_unmatch | Loại trừ đường dẫn đầy đủ |
| match_mapping_type | Khớp kiểu mà Elasticsearch suy luận, ví dụ string, long, double, boolean hoặc object |
| unmatch_mapping_type | Loại trừ kiểu được suy luận |
| match_pattern | Chọn cách khớp tên, thường là simple hoặc regex |

Các điều kiện trong cùng một template phải cùng thỏa mãn để template khớp. Nếu nhiều template cùng có thể khớp, Elasticsearch áp dụng template khớp đầu tiên theo thứ tự khai báo. Vì vậy, đặt quy tắc cụ thể trước quy tắc tổng quát.

### 4.2. Ví dụ: chuỗi mặc định là text nhưng mã là keyword

Một ứng dụng có nhiều trường chuỗi mới. Phần lớn cần tìm kiếm toàn văn, nhưng các trường có hậu tố _code cần so khớp chính xác:

~~~json
{
  "mappings": {
    "dynamic_templates": [
      {
        "codes_as_keyword": {
          "match": "*_code",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      {
        "other_strings_as_text": {
          "match_mapping_type": "string",
          "mapping": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "ignore_above": 256
              }
            }
          }
        }
      }
    ]
  }
}
~~~

Với thứ tự trên:

- supplier_code là keyword.
- description là text và có thêm description.keyword.
- region_code là keyword nếu Elasticsearch nhận diện giá trị của nó là string.

Template thứ hai là quy tắc tổng quát cho mọi chuỗi. Nếu đặt nó lên trước, trường mã cũng sẽ khớp template tổng quát và không bao giờ tới được template codes_as_keyword.

### 4.3. Ví dụ: áp dụng quy tắc cho object lồng nhau

Giả sử document có vùng attributes chứa các thuộc tính do nhiều nguồn dữ liệu cung cấp:

~~~json
{
  "sku": "KB-1042",
  "attributes": {
    "layout": "US",
    "switchCount": 87,
    "vendor_code": "VN-ACME"
  }
}
~~~

Có thể dùng path_match để chỉ áp dụng template trong vùng attributes:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "attributes": {
        "type": "object",
        "dynamic": true
      }
    },
    "dynamic_templates": [
      {
        "attribute_codes_as_keyword": {
          "path_match": "attributes.*",
          "match": "*_code",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      {
        "attribute_strings_as_keyword": {
          "path_match": "attributes.*",
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      }
    ]
  }
}
~~~

Mapping cấp cao nhất dùng strict để bảo vệ schema. Object attributes bật dynamic để nhận các trường con mới. Hai template giới hạn quy tắc vào đường dẫn attributes.*; template đầu xử lý các trường mã, template sau xử lý các chuỗi còn lại trong vùng này.

Nếu dữ liệu có nhiều tầng object, hãy kiểm tra đường dẫn thực tế của trường và điều chỉnh path_match cho phù hợp. Không nên giả định một mẫu đường dẫn sẽ bao phủ mọi cấu trúc lồng nhau mà chưa thử với document đại diện.

### 4.4. Kết hợp match_mapping_type với tên trường

Tên trường và kiểu dữ liệu có thể được dùng cùng nhau để tránh áp dụng sai quy tắc. Ví dụ, mọi trường có hậu tố _count và được nhận diện là số nguyên có thể được map theo quy tắc số:

~~~json
{
  "dynamic_templates": [
    {
      "counts_as_long": {
        "match": "*_count",
        "match_mapping_type": "long",
        "mapping": {
          "type": "long"
        }
      }
    }
  ]
}
~~~

Việc chỉ khớp theo tên có thể khiến một trường chuỗi bị map thành số ngoài dự kiến. Việc kết hợp tên với match_mapping_type làm quy tắc rõ ràng hơn. Nếu muốn giới hạn tên bằng biểu thức chính quy, có thể dùng match_pattern với giá trị regex; hãy kiểm tra mẫu trên các tên trường thực tế trước khi đưa vào môi trường chạy thật.

## 5. Kết hợp mapping tường minh, dynamic mapping và dynamic templates

Ba cơ chế giải quyết các nhu cầu khác nhau:

| Cơ chế | Vai trò | Nên dùng khi |
| --- | --- | --- |
| Mapping tường minh | Định nghĩa chính xác kiểu và cách xử lý trường đã biết | Trường nghiệp vụ cốt lõi, trường dùng để truy vấn, sort hoặc aggregation |
| Dynamic mapping | Tự tạo mapping khi gặp trường mới | Dữ liệu có phần cấu trúc thay đổi và quy tắc suy luận mặc định là phù hợp |
| Dynamic templates | Kiểm soát mapping tự động bằng điều kiện | Có nhiều trường mới nhưng chúng tuân theo quy ước về tên, đường dẫn hoặc kiểu |

Một chiến lược thường dùng:

1. Khai báo tường minh các trường định danh, trạng thái, thời gian, số liệu và trường tìm kiếm.
2. Đặt dynamic ở cấp document thành strict để phát hiện lỗi chính tả tên trường và thay đổi schema ngoài dự kiến.
3. Tạo một hoặc vài object mở rộng, chẳng hạn attributes, cho phép dynamic mapping.
4. Đặt dynamic templates để quy định cách map các trường mới trong object mở rộng.
5. Theo dõi số lượng field và mapping thực tế sau khi triển khai.

Chiến lược này giúp ứng dụng tiếp nhận thuộc tính linh hoạt mà vẫn phát hiện sớm các trường lạ ở phần dữ liệu chính.

## 6. Những lưu ý khi vận hành và thay đổi mapping

### 6.1. Không thể đổi tùy ý kiểu trường đã tồn tại

Khi Elasticsearch đã tạo mapping cho một trường, không thể cập nhật trực tiếp kiểu của trường đó từ text sang date, từ long sang keyword hoặc sang một kiểu không tương thích khác. Việc thay đổi kiểu thường cần:

1. Tạo index mới với mapping đúng.
2. Reindex document từ index cũ sang index mới, có thể kết hợp script hoặc bước chuyển đổi dữ liệu nếu cần.
3. Kiểm tra số lượng document và các truy vấn quan trọng trên index mới.
4. Chuyển alias đọc/ghi sang index mới theo quy trình triển khai của hệ thống.

Một số thuộc tính mapping có thể được bổ sung hoặc cập nhật theo giới hạn của Elasticsearch, nhưng không nên xem mapping là schema có thể sửa tùy ý sau khi đã ghi dữ liệu.

### 6.2. Mapping và dữ liệu trong _source

_source lưu document JSON gốc theo cấu hình index. Mapping điều khiển cách các trường được lập chỉ mục và truy vấn. Hai khái niệm này liên quan nhưng không đồng nhất:

- Một trường bị bỏ qua do dynamic false vẫn có thể còn trong _source.
- Một trường kiểu text có thể có thêm multi-field keyword để hỗ trợ truy vấn chính xác.
- Việc một trường xuất hiện trong _source không tự động có nghĩa là trường đó đã có mapping hoặc có thể dùng trong aggregation.

Khi điều tra vì sao một trường không truy vấn được, hãy kiểm tra cả document trong _source lẫn mapping của index.

### 6.3. Dynamic templates không phải index templates

Hai khái niệm có tên gần giống nhau nhưng xử lý ở hai cấp khác nhau:

- Dynamic templates là quy tắc tạo mapping cho các trường mới bên trong một index.
- Index templates là cấu hình được áp dụng khi tạo index phù hợp với mẫu tên hoặc điều kiện nhất định; chúng có thể cung cấp settings, mappings và aliases cho index mới.

Một index template có thể chứa mapping và dynamic templates. Tuy nhiên, index template không thay thế vai trò của dynamic templates khi document mới đưa thêm trường vào index đã tồn tại.

### 6.4. Kiểm tra mapping sau khi tạo index

Có thể đọc mapping thực tế bằng API:

~~~http
GET /catalog-v1/_mapping
~~~

Hãy kiểm tra mapping thực tế thay vì chỉ nhìn annotation hoặc tệp JSON. Đây là cách xác nhận Elasticsearch đã nhận đúng kiểu, analyzer, multi-fields, dynamic mode và dynamic templates.

Khi kiểm thử, nên gửi các document đại diện cho:

- Trường cốt lõi có đủ kiểu dữ liệu hợp lệ.
- Trường mở rộng có tên khớp từng dynamic template.
- Trường không khớp template nào.
- Trường có kiểu dữ liệu khác với kiểu dự kiến.
- Trường lạ ở cấp strict để xác nhận Elasticsearch từ chối document.

Các trường hợp này giúp phát hiện sớm template bị che bởi quy tắc tổng quát, sai đường dẫn path_match hoặc xung đột kiểu dữ liệu.

## 7. Lỗi thường gặp

**Dùng text cho mã định danh.** Text được phân tích thành token nên không phù hợp cho mã cần so khớp nguyên vẹn. Hãy dùng keyword hoặc multi-fields nếu trường vừa cần tìm kiếm toàn văn vừa cần lọc chính xác.

**Cho rằng dynamic false sẽ loại bỏ dữ liệu.** Trường không được thêm vào mapping nhưng vẫn có thể được giữ trong _source. Nếu cần từ chối trường lạ, dùng strict.

**Đặt template tổng quát lên trước template cụ thể.** Template đầu tiên khớp sẽ được áp dụng. Hãy đặt các quy tắc có điều kiện hẹp lên trước quy tắc bao quát.

**Thay đổi template rồi kỳ vọng trường cũ được remap.** Dynamic templates chỉ áp dụng khi tạo mapping cho trường mới. Trường đã có mapping giữ nguyên kiểu hiện tại.

**Cho rằng annotation Java tự động kiểm soát mọi trường trong JSON.** Annotation mô tả mapping cho entity, nhưng document thực tế có thể chứa dữ liệu mở rộng trong Map hoặc object. Hãy kiểm tra JSON được gửi lên Elasticsearch và mapping đã tạo.

**Để nhiều thành phần tự tạo cùng một index.** Nếu ứng dụng, migration và index template không thống nhất, index có thể được tạo với mapping khác nhau tùy thời điểm. Hãy xác định một quy trình quản lý schema rõ ràng.

## 8. Quy trình thiết kế mapping đề xuất

Khi thiết kế index mới cho một ứng dụng Spring Data Elasticsearch, có thể thực hiện theo trình tự:

1. Liệt kê các trường nghiệp vụ và xác định cách sử dụng từng trường: tìm kiếm toàn văn, lọc chính xác, sort, aggregation hay lưu trữ.
2. Chọn kiểu Elasticsearch phù hợp cho từng trường. Đặc biệt phân biệt text với keyword, object với nested, và kiểu số với chuỗi mã.
3. Khai báo tường minh các trường ổn định bằng @Field hoặc mapping JSON.
4. Xác định vùng nào được phép có thuộc tính mới. Chỉ bật dynamic ở đúng object cần thiết.
5. Viết dynamic templates theo quy ước tên, đường dẫn và kiểu dữ liệu; đặt quy tắc cụ thể trước quy tắc tổng quát.
6. Tạo index trong môi trường phát triển và đọc lại mapping bằng API _mapping.
7. Gửi document hợp lệ và không hợp lệ để kiểm tra hành vi của dynamic true, false, strict và từng template.
8. Quản lý thay đổi mapping bằng phiên bản index và quy trình reindex khi cần thay đổi kiểu không tương thích.

Mapping tốt phản ánh cách ứng dụng sử dụng dữ liệu, không chỉ phản ánh hình dạng JSON đầu vào. Hãy thiết kế dựa trên truy vấn và vòng đời dữ liệu, sau đó dùng dynamic mapping cùng dynamic templates cho phần mở rộng đã được kiểm soát.
