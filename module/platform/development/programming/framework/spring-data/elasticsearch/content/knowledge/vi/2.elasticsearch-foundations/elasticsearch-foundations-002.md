# Document, trường dữ liệu, `_id` và `_source`

Trong Elasticsearch, dữ liệu được lưu thành các **document JSON** bên trong một **index**. Mỗi document có các field mô tả đối tượng, một mã định danh `_id` do Elasticsearch quản lý và phần nội dung `_source` có thể được trả về khi đọc hoặc tìm kiếm. Spring Data Elasticsearch ánh xạ các khái niệm này từ class Java thông qua `@Document`, `@Id` và `@Field`.

Hiểu rõ ba phần document, `_id` và `_source` giúp thiết kế mapping đúng, chọn kiểu field phù hợp cho truy vấn và tránh nhầm mã định danh với dữ liệu nghiệp vụ.

## 1. Document là gì?

**Document** là đơn vị dữ liệu cơ bản mà Elasticsearch lập chỉ mục và tìm kiếm. Một document thường biểu diễn một đối tượng nghiệp vụ, chẳng hạn một sản phẩm, khách hàng, đơn hàng hoặc bài viết. Nội dung document được gửi dưới dạng JSON.

Ví dụ một document sản phẩm:

~~~json
{
  "name": "Mechanical Keyboard",
  "sku": "KB-001",
  "priceInCents": 129900,
  "active": true,
  "tags": ["keyboard", "mechanical"],
  "brand": {
    "name": "Example Tech"
  },
  "createdAt": "2026-11-13T09:30:00Z"
}
~~~

Trong ví dụ này, `name`, `sku`, `priceInCents`, `active`, `tags`, `brand` và `createdAt` là các field. Giá trị của field có thể là chuỗi, số, boolean, mảng hoặc object lồng nhau.

Các khái niệm thường gặp:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Index | Tập hợp document có cùng mục đích lưu trữ và hệ mapping. Có thể hình dung gần giống một bảng dữ liệu, nhưng cách tổ chức và truy vấn khác cơ sở dữ liệu quan hệ. |
| Document | Một đối tượng JSON được lưu trong index. |
| Field | Một thuộc tính bên trong document, tương tự thuộc tính của object hoặc cột dữ liệu. |
| Mapping | Định nghĩa kiểu dữ liệu và cách Elasticsearch lập chỉ mục cho từng field. |

Document không bắt buộc phải có cấu trúc JSON giống hệt mọi document khác. Tuy nhiên, các document trong cùng index thường nên tuân theo một mapping nhất quán để truy vấn, sắp xếp và tổng hợp dữ liệu có kết quả dự đoán được.

## 2. Field và mapping

### 2.1. Field là thuộc tính của document

Mỗi cặp tên và giá trị trong JSON tạo thành một field. Field có thể chứa:

- Giá trị đơn: `name`, `priceInCents`, `active`.
- Nhiều giá trị: `tags` là một mảng chuỗi.
- Object: `brand` chứa field con `name`.
- Mảng object: `variants` có thể chứa nhiều biến thể của sản phẩm.

Elasticsearch không có một kiểu mapping riêng tên là `array`. Một field có thể nhận một giá trị hoặc nhiều giá trị cùng kiểu. Ví dụ `tags` có thể là `"keyboard"` hoặc `["keyboard", "mechanical"]`; mapping vẫn là `keyword`.

### 2.2. Mapping quyết định cách Elasticsearch hiểu field

Mapping khai báo kiểu dữ liệu của field và một số hành vi lập chỉ mục. Những kiểu thường dùng gồm:

| Kiểu mapping | Công dụng thường gặp |
| --- | --- |
| `text` | Nội dung cần phân tích thành token để tìm kiếm toàn văn, ví dụ tên sản phẩm hoặc mô tả. |
| `keyword` | Chuỗi cần so khớp chính xác, lọc, nhóm hoặc sắp xếp, ví dụ SKU, trạng thái, mã quốc gia. |
| `long`, `integer`, `double`, `float` | Giá trị số dùng để lọc theo khoảng, sắp xếp hoặc tính toán. |
| `boolean` | Giá trị đúng hoặc sai. |
| `date` | Ngày giờ; Elasticsearch chuyển giá trị sang biểu diễn thời gian để truy vấn theo khoảng. |
| `object` | Một object JSON có các field con. |
| `nested` | Mảng object cần giữ quan hệ giữa các field trong cùng một phần tử. |
| `geo_point` | Tọa độ địa lý dùng cho truy vấn không gian. |

Phân biệt `text` và `keyword` là điều đặc biệt quan trọng:

- `text` thường được analyzer tách thành token. Truy vấn `match` phù hợp với tìm kiếm nội dung, chẳng hạn tìm sản phẩm có tên chứa các từ liên quan đến `mechanical keyboard`.
- `keyword` giữ giá trị như một đơn vị để so khớp chính xác. Truy vấn `term` phù hợp với SKU `KB-001` hoặc trạng thái `ACTIVE`.

Ví dụ hai truy vấn:

~~~json
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

~~~json
{
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

Không nên dùng `term` để tìm kiếm tùy ý trên field `text`, vì giá trị đã được analyzer xử lý. Ngược lại, `match` không phải lựa chọn mặc định cho mã định danh hoặc trạng thái cần so khớp chính xác.

### 2.3. Object và nested

Với một object đơn như `brand`, mapping kiểu `object` thường là đủ. Elasticsearch lập chỉ mục các field con theo đường dẫn, ví dụ `brand.name`.

Mảng object cần cân nhắc kỹ hơn. Giả sử một sản phẩm có hai biến thể:

~~~json
{
  "variants": [
    { "color": "black", "stock": 0 },
    { "color": "white", "stock": 5 }
  ]
}
~~~

Với mapping `object` mặc định, Elasticsearch làm phẳng các giá trị field con khi lập chỉ mục. Một truy vấn kết hợp `color = black` và `stock > 0` có thể ghép giá trị từ hai phần tử khác nhau và trả về document này, dù biến thể màu đen thực tế không còn hàng.

Nếu điều kiện truy vấn phải áp dụng trên **cùng một phần tử** trong mảng object, hãy khai báo field là `nested` và dùng nested query. Ví dụ:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "must": [
            { "term": { "variants.color": "black" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }
  }
}
~~~

`nested` có chi phí lưu trữ và truy vấn cao hơn `object` vì Elasticsearch xử lý từng phần tử nested như một document nội bộ riêng. Chỉ dùng khi cần giữ quan hệ giữa các field trong cùng phần tử.

### 2.4. Dynamic mapping và mapping tường minh

Elasticsearch có thể tự tạo mapping cho field mới khi nhận document nếu dynamic mapping đang bật. Kiểu được suy ra từ giá trị đầu tiên mà Elasticsearch quan sát được. Cách này tiện khi thử nghiệm, nhưng có thể tạo ra kiểu không phù hợp với nhu cầu truy vấn lâu dài.

Ví dụ, một chuỗi ngày tháng có thể được nhận diện thành `date`, hoặc một chuỗi mã có thể được tạo mapping theo cách không phù hợp với lọc chính xác. Khi các document sau gửi giá trị không tương thích với mapping đã tạo, thao tác ghi có thể thất bại hoặc cần xử lý chuyển đổi.

Với dữ liệu nghiệp vụ ổn định, nên khai báo mapping tường minh trước khi ghi dữ liệu quan trọng. Việc thay đổi kiểu của một field đã tồn tại thường cần tạo index mới với mapping mong muốn rồi reindex dữ liệu sang index đó; không thể tùy ý đổi trực tiếp `text` thành `keyword` trên cùng field đã được tạo.

## 3. `_id` — mã định danh của document

`_id` là metadata field Elasticsearch dùng để xác định một document trong một index. Mỗi document trong cùng index phải có `_id` duy nhất. Hai index khác nhau có thể có document trùng `_id` vì phạm vi duy nhất được tính theo từng index.

Có hai cách phổ biến để có `_id`:

- **Tự cấp mã:** ứng dụng gửi document mà không chỉ định ID; Elasticsearch tạo một ID và trả lại trong phản hồi.
- **Ứng dụng chỉ định mã:** ứng dụng gửi ID trong đường dẫn hoặc thông qua mapping của Spring Data. Cách này hữu ích khi cần địa chỉ document ổn định, ghi lặp lại theo cùng khóa hoặc tìm document trực tiếp.

Ví dụ REST API chỉ định ID:

~~~http
PUT /products/_doc/KB-001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-001",
  "active": true
}
~~~

Đọc document theo ID:

~~~http
GET /products/_doc/KB-001
~~~

Khi dùng `PUT` với cùng index và cùng `_id`, Elasticsearch ghi document tại địa chỉ đó; nội dung cũ có thể được thay thế bằng nội dung mới. Vì vậy, ID do ứng dụng chọn nên ổn định và phản ánh đúng quy tắc định danh của nghiệp vụ.

`_id` là metadata, không phải field nghiệp vụ thông thường trong mapping. Có thể dùng ID để lấy document trực tiếp hoặc dùng truy vấn `ids`. Nếu cần tìm kiếm, lọc, sắp xếp hay tổng hợp theo một mã nghiệp vụ, hãy lưu mã đó thành field `keyword` riêng, ví dụ `sku` hoặc `externalId`.

### 3.1. Ánh xạ `_id` bằng `@Id` trong Spring Data Elasticsearch

Spring Data Elasticsearch dùng annotation `@Id` để đánh dấu thuộc tính Java được dùng làm Elasticsearch `_id`. Annotation này đến từ `org.springframework.data.annotation.Id`.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    // Constructors, getters và setters
}
~~~

Khi Spring Data ghi một `Product`, giá trị `id` được dùng làm metadata `_id`. Khi đọc document, Spring Data dùng `_id` để điền lại thuộc tính `id` của entity.

Trong cơ chế mapping mặc định của Spring Data Elasticsearch, thuộc tính được đánh dấu `@Id` được dùng làm `_id` và không được ghi như một field thông thường trong `_source`. Nếu ứng dụng cần tìm kiếm theo mã nghiệp vụ, hãy khai báo thêm một thuộc tính riêng, chẳng hạn `sku`, rồi ánh xạ nó thành `keyword`.

## 4. `_source` — nội dung JSON của document

`_source` là phần nội dung JSON được gửi khi index document và được Elasticsearch lưu để có thể trả lại nội dung ban đầu. Đây là dữ liệu mà Spring Data thường đọc để chuyển đổi kết quả thành entity Java.

Ví dụ một kết quả lấy document theo ID có cấu trúc rút gọn như sau:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "_version": 1,
  "_source": {
    "name": "Mechanical Keyboard",
    "sku": "KB-001",
    "active": true
  }
}
~~~

Trong kết quả này:

- `_index` cho biết index chứa document.
- `_id` là mã định danh do Elasticsearch quản lý.
- `_version` là thông tin phiên bản nội bộ của document.
- `_source` chứa các field JSON của document.

`_source` không phải một field thông thường mà ứng dụng khai báo trong `properties` của mapping. Nó cũng không phải nơi Elasticsearch thực hiện tìm kiếm toàn văn. Việc tìm kiếm dựa trên cấu trúc chỉ mục được tạo từ mapping; `_source` chủ yếu phục vụ việc lấy lại nội dung document.

### 4.1. Lọc nội dung `_source` khi tìm kiếm

Khi chỉ cần một vài field, có thể dùng source filtering để giảm lượng dữ liệu trả về:

~~~json
{
  "_source": ["name", "sku"],
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

Kết quả vẫn có metadata `_id`, còn `_source` chỉ chứa các field được yêu cầu. Source filtering giúp giảm payload mạng và lượng dữ liệu cần chuyển đổi khi document có nhiều field.

### 4.2. `_source` khác với `store` của field

Mặc định, ứng dụng thường lấy field từ `_source`. Mapping cũng cho phép đánh dấu một số field với `store: true` để Elasticsearch lưu riêng field đó và trả về khi yêu cầu `stored_fields`.

Hai cơ chế có mục đích khác nhau:

- `_source` lưu nội dung JSON của document để có thể dựng lại document.
- `store: true` lưu riêng giá trị của field được chọn; ứng dụng phải yêu cầu lấy stored field khi đọc.

Không cần bật `store: true` chỉ để có thể đọc field từ `_source`. Chỉ cấu hình stored field khi có lý do cụ thể về cách truy xuất dữ liệu.

### 4.3. Khi tắt `_source`

Index có thể được cấu hình để không lưu `_source`, nhưng quyết định này làm mất khả năng lấy lại JSON gốc theo cách thông thường. Những thao tác phụ thuộc vào source, chẳng hạn trả về document đầy đủ hoặc cập nhật một phần nội dung, sẽ bị hạn chế. Với ứng dụng Spring Data cần chuyển đổi kết quả tìm kiếm thành entity, nên giữ `_source` trừ khi đã thiết kế rõ một cơ chế truy xuất khác.

## 5. Khai báo document và field bằng Spring Data Elasticsearch

Spring Data Elasticsearch ánh xạ entity Java thành document Elasticsearch. Các annotation quan trọng trong ví dụ:

- `@Document(indexName = "products")`: khai báo index đích cho entity.
- `@Id`: đánh dấu thuộc tính dùng làm `_id`.
- `@Field`: khai báo kiểu mapping và các tùy chọn của field.

Ví dụ entity:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Object)
    private Brand brand;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;

    // Constructors, getters và setters
}
~~~

Các class `Brand` và `Variant` có thể được khai báo như sau:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class Brand {

    @Field(type = FieldType.Keyword)
    private String name;

    // Getters và setters
}

public class Variant {

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Integer)
    private Integer stock;

    // Getters và setters
}
~~~

Với entity trên, mapping tương ứng về mặt ý tưởng có thể được biểu diễn bằng JSON như sau:

~~~json
{
  "mappings": {
    "properties": {
      "name": { "type": "text", "analyzer": "standard" },
      "sku": { "type": "keyword" },
      "priceInCents": { "type": "long" },
      "active": { "type": "boolean" },
      "createdAt": { "type": "date" },
      "brand": {
        "properties": {
          "name": { "type": "keyword" }
        }
      },
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "stock": { "type": "integer" }
        }
      }
    }
  }
}
~~~

Mapping JSON không khai báo `id` trong `properties`, vì `id` của entity đã được dùng làm metadata `_id`. Nếu cần field nghiệp vụ để truy vấn theo mã, hãy thêm một thuộc tính riêng như `sku`.

Khi Spring Data được cấu hình tạo index từ metadata entity, các annotation `@Document` và `@Field` cung cấp thông tin để tạo index và mapping. Nếu index đã tồn tại, chỉ sửa annotation trong Java không có nghĩa mapping đang chạy sẽ tự động được thay đổi. Cần quản lý vòng đời mapping và việc tạo index theo quy trình của ứng dụng.

### 5.1. Ghi và đọc document qua repository

Có thể khai báo repository với kiểu ID là `String`:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Ví dụ sử dụng:

~~~java
Product product = new Product();
product.setId("KB-001");
product.setName("Mechanical Keyboard");
product.setSku("KB-001");
product.setActive(true);

productRepository.save(product);

var result = productRepository.findById("KB-001");
~~~

`save` ghi entity vào index được khai báo trên `@Document`; `findById` tra cứu theo metadata `_id`. Các truy vấn theo thuộc tính như `sku` cần dựa trên mapping field tương ứng và cách xây dựng query của repository hoặc `ElasticsearchOperations`.

## 6. Luồng dữ liệu từ Java đến Elasticsearch

Có thể hình dung quá trình ghi và đọc theo các bước:

~~~mermaid
flowchart TD
    A["Java entity Product"] --> B["Spring Data mapping metadata"]
    B --> C["JSON document + metadata _id"]
    C --> D["Elasticsearch kiểm tra mapping"]
    D --> E["Lập chỉ mục các field"]
    D --> F["Lưu nội dung _source"]
    E --> G["Tìm kiếm theo field"]
    F --> H["Trả lại nội dung document"]
    G --> I["Search hit: _id + _source"]
    H --> I
    I --> J["Spring Data chuyển thành Product"]
~~~

Ở chiều ghi, Spring Data đọc metadata từ entity, lấy giá trị `@Id` làm `_id` và chuyển các thuộc tính còn lại thành JSON theo quy tắc mapping. Elasticsearch dùng mapping để phân tích và lập chỉ mục các field, đồng thời lưu `_source` nếu cấu hình cho phép.

Ở chiều đọc, Elasticsearch trả metadata như `_id` cùng `_source` (nếu được yêu cầu và đang bật). Spring Data dùng thông tin đó để dựng lại entity Java, bao gồm việc gán `_id` vào thuộc tính `@Id`.

## 7. Những lỗi thiết kế thường gặp

| Cách làm dễ gây lỗi | Cách xử lý phù hợp |
| --- | --- |
| Dùng field `text` cho SKU rồi truy vấn bằng `term`. | Dùng `keyword` cho mã cần so khớp chính xác. |
| Dùng `keyword` cho đoạn mô tả dài cần tìm kiếm theo từ. | Dùng `text` với analyzer phù hợp. |
| Coi `@Id` như một field nghiệp vụ luôn xuất hiện trong `_source`. | Xem `@Id` là ánh xạ tới metadata `_id`; tạo field riêng nếu cần lưu mã nghiệp vụ trong source. |
| Dùng `object` cho mảng object nhưng mong điều kiện truy vấn luôn khớp trên cùng một phần tử. | Dùng `nested` và nested query khi cần bảo toàn quan hệ giữa các field trong từng phần tử. |
| Để dynamic mapping tự chọn kiểu cho mọi field quan trọng. | Khai báo mapping tường minh cho các field có yêu cầu truy vấn rõ ràng. |
| Nghĩ rằng sửa `@Field` sẽ tự đổi mapping của index đang tồn tại. | Tạo mapping/index mới và reindex khi cần thay đổi kiểu field. |
| Tắt `_source` nhưng vẫn cần dựng lại entity đầy đủ từ kết quả tìm kiếm. | Giữ `_source` hoặc thiết kế rõ cơ chế lưu và truy xuất thay thế. |

## 8. Cách chọn thiết kế cho một document

Khi thiết kế entity Spring Data Elasticsearch, hãy bắt đầu từ cách ứng dụng sẽ tìm kiếm dữ liệu:

1. Xác định mỗi document biểu diễn một đối tượng nghiệp vụ nào và index nào chứa nó.
2. Chọn một ID ổn định nếu ứng dụng cần đọc lại hoặc ghi đè document theo cùng một định danh; đánh dấu thuộc tính đó bằng `@Id`.
3. Với từng field, xác định nhu cầu tìm kiếm: toàn văn (`text`), so khớp chính xác (`keyword`), số, ngày giờ, boolean hay dữ liệu địa lý.
4. Chọn `object` cho object lồng nhau thông thường; chọn `nested` khi truy vấn cần ghép điều kiện trên cùng một phần tử của mảng object.
5. Giữ `_source` nếu ứng dụng cần trả lại document hoặc chuyển kết quả tìm kiếm thành entity Java.
6. Tạo và kiểm tra mapping trước khi đưa lượng dữ liệu quan trọng vào index.

Khi các lựa chọn này rõ ràng, class Java, mapping Elasticsearch và các truy vấn của ứng dụng sẽ nhất quán hơn. Document mô tả dữ liệu, mapping định nghĩa cách dữ liệu được hiểu và lập chỉ mục, `_id` xác định document, còn `_source` giữ nội dung JSON để ứng dụng có thể đọc lại.
