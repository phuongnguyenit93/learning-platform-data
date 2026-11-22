# Thiết kế phi chuẩn hóa thay vì join theo mô hình quan hệ

Elasticsearch là một search engine hướng document. Ứng dụng lưu các JSON document độc lập và truy vấn trên những field đã được lập chỉ mục. Mô hình này khác cơ sở dữ liệu quan hệ, nơi ứng dụng có thể chuẩn hóa dữ liệu thành nhiều bảng rồi ghép chúng bằng JOIN trong mỗi câu SQL.

Trong Elasticsearch Query DSL không có phép JOIN tổng quát giữa hai index hoặc hai tập document tùy ý. Elasticsearch có cơ chế parent-child dựa trên join field, nhưng đây là tính năng chuyên biệt, có điều kiện về routing và thường tốn kém hơn truy vấn trên một document. Vì vậy, mô hình phổ biến là thiết kế document theo cách dữ liệu sẽ được đọc và tìm kiếm: lưu các thuộc tính cần thiết cùng nhau, chấp nhận một phần dữ liệu được lặp lại để giảm số bước truy vấn.

Đó là **phi chuẩn hóa (denormalization)**. Đây không phải là sao chép dữ liệu tùy tiện. Ứng dụng cần xác định nguồn dữ liệu chuẩn, các read model cần phục vụ, dữ liệu nào được nhúng vào document, dữ liệu nào được sao chép để lọc/tìm kiếm, và cách cập nhật các bản sao khi nguồn thay đổi.

## 1. Vì sao mô hình quan hệ không chuyển nguyên xi sang Elasticsearch?

Trong cơ sở dữ liệu quan hệ, một ứng dụng bán hàng có thể lưu:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200),
    brand_id BIGINT
);

CREATE TABLE brand (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT,
    product_id BIGINT,
    quantity INTEGER,
    unit_price DECIMAL(12, 2)
);
~~~

Khi cần tìm dòng đơn hàng theo tên sản phẩm hoặc thương hiệu, SQL có thể JOIN order_line với product rồi JOIN brand. Cơ sở dữ liệu quản lý khóa ngoại và thực hiện ghép dữ liệu tại thời điểm truy vấn.

Trong Elasticsearch, các document được index độc lập. Một query tìm kiếm trên index đơn không tự ghép field của document này với document ở index khác theo khóa ngoại. Nếu một truy vấn thường xuyên cần tên sản phẩm, tên thương hiệu và giá tại thời điểm đặt hàng, dữ liệu cần thiết nên được đưa vào document phục vụ truy vấn đó.

Ví dụ một order line có thể lưu snapshot:

~~~json
{
  "orderId": "ORD-2026-1001",
  "lineId": "LINE-01",
  "productId": "P-1042",
  "sku": "KB-1042",
  "productName": "Mechanical Keyboard",
  "brandName": "KeyWorks",
  "quantity": 2,
  "unitPrice": 129.5,
  "currency": "USD"
}
~~~

Document có thể trả lời trực tiếp các câu hỏi về đơn hàng mà không cần tìm document sản phẩm và thương hiệu để ghép vào.

### 1.1. Những chi phí được chuyển đổi

Phi chuẩn hóa làm giảm công việc đọc và truy vấn, nhưng chuyển một phần chi phí sang ghi và đồng bộ:

| Khía cạnh | Mô hình chuẩn hóa | Mô hình phi chuẩn hóa |
| --- | --- | --- |
| Dữ liệu | Một thuộc tính thường lưu một nơi | Có thể lặp lại trong nhiều document |
| Đọc | Có thể cần ghép nhiều nguồn | Thường đọc từ một document/read model |
| Ghi | Cập nhật một bản ghi nguồn | Có thể phải cập nhật nhiều bản sao |
| Tính nhất quán | Khóa ngoại và transaction trong DB quan hệ | Cần cơ chế đồng bộ và xử lý sự kiện |
| Tìm kiếm | JOIN rồi lọc/sắp xếp | Lọc trực tiếp trên field đã index |
| Dung lượng | Thường ít lặp hơn | Tăng theo số thuộc tính được sao chép |

Không có mô hình nào luôn tốt hơn. Cần chọn theo truy vấn quan trọng, tốc độ cập nhật, độ lớn dữ liệu và mức nhất quán mà nghiệp vụ yêu cầu.

## 2. Thiết kế từ access pattern

Trước khi quyết định embed hay tách document, hãy liệt kê cách ứng dụng thực sự đọc dữ liệu. Cùng một tập dữ liệu có thể cần nhiều read model khác nhau.

Ví dụ một hệ thống thương mại điện tử có các truy vấn:

- Mở trang chi tiết sản phẩm, cần tên, mô tả, thương hiệu, danh mục và các biến thể.
- Tìm kiếm sản phẩm theo tên, thương hiệu, danh mục, giá và trạng thái.
- Mở đơn hàng, cần snapshot sản phẩm và giá đã mua.
- Xem lịch sử đánh giá theo sản phẩm, có thể có hàng triệu review.
- Tìm sản phẩm theo thuộc tính của một offer cụ thể.

Không nên bắt một document model duy nhất phục vụ tất cả các trường hợp nếu chúng có yêu cầu khác nhau. Một sản phẩm có thể được biểu diễn trong index sản phẩm, trong snapshot đơn hàng và trong index gợi ý tìm kiếm.

### 2.1. Các câu hỏi cần trả lời

Khi thiết kế document, hãy xác định:

1. Truy vấn nào cần chạy thường xuyên và có yêu cầu latency cao?
2. Những field nào luôn được đọc cùng nhau?
3. Quan hệ một-một, một-nhiều hay nhiều-nhiều?
4. Số lượng phần tử con có giới hạn hay tăng không giới hạn?
5. Phần tử con có được cập nhật độc lập không?
6. Ứng dụng cần tìm kiếm trên field cha từ document con, hay ngược lại?
7. Dữ liệu sao chép có phải snapshot lịch sử hay phải luôn phản ánh trạng thái mới nhất?
8. Mức độ trễ đồng bộ nào được chấp nhận?
9. Khi cập nhật nguồn, có thể cập nhật hàng nghìn hoặc hàng triệu document hay không?

Các câu trả lời này xác định ranh giới document và chiến lược cập nhật.

### 2.2. Mô hình hóa theo truy vấn đọc

~~~text
Nguồn dữ liệu chuẩn
       |
       v
Các truy vấn quan trọng
       |
       v
Thiết kế read model
       |
   +---+---+
   |       |
   v       v
 Embed   Copy fields
   |       |
   +---+---+
       |
       v
 Elasticsearch document
       |
       v
 Search trực tiếp
~~~

Document được tối ưu cho cách đọc. Nếu một truy vấn phải ghép nhiều document ở mọi request, hãy cân nhắc đưa các field cần thiết vào cùng read model.

## 3. Embed object khi dữ liệu luôn được đọc cùng nhau

Quan hệ một-một hoặc một-một theo góc nhìn document thường phù hợp với object lồng nhau.

Ví dụ một sản phẩm có thông tin thương hiệu:

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "brand": {
    "id": "B-10",
    "name": "KeyWorks",
    "country": "US"
  }
}
~~~

Ứng dụng có thể đọc tên sản phẩm và tên thương hiệu trong một lần lấy document.

### 3.1. Entity Spring Data

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Object)
    private BrandInfo brand;

    // Constructors, getters và setters
}

public class BrandInfo {

    @Field(type = FieldType.Keyword)
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String country;

    // Constructors, getters và setters
}
~~~

`FieldType.Object` phù hợp khi các thuộc tính của object con không cần được truy vấn theo quan hệ cùng một phần tử trong một mảng object. Nếu chỉ có một brand object, object mapping thường là đủ.

### 3.2. Khi nào không cần tách brand thành index riêng?

Nếu trang sản phẩm luôn cần tên thương hiệu, thương hiệu có ít field, và thay đổi tên thương hiệu không diễn ra quá thường xuyên, nhúng một bản sao brand vào product document thường đơn giản.

Nếu thương hiệu có hàng trăm field, nội dung lớn hoặc được quản lý độc lập, không nhất thiết nhúng toàn bộ. Chỉ sao chép các thuộc tính mà truy vấn sản phẩm cần, chẳng hạn brand.id, brand.name và brand.logoUrl.

## 4. Embed mảng con: object hay nested?

Một sản phẩm có thể có các biến thể:

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "variants": [
    {
      "sku": "KB-1042-BLK",
      "color": "black",
      "price": 129.5
    },
    {
      "sku": "KB-1042-WHT",
      "color": "white",
      "price": 139.5
    }
  ]
}
~~~

Nếu chỉ hiển thị tất cả biến thể cùng sản phẩm và không cần truy vấn nhiều field trên cùng một biến thể, object array có thể đủ. Nếu cần điều kiện tương quan, chẳng hạn tìm sản phẩm có một variant vừa màu black vừa có giá dưới 130, cần cân nhắc nested.

### 4.1. Vấn đề cross-object matching với object array

Với mapping object thông thường, Elasticsearch có thể index các field con như các tập giá trị đa trị. Quan hệ giữa các field của từng phần tử có thể bị mất trong truy vấn.

Ví dụ:

~~~json
{
  "variants": [
    { "color": "black", "price": 150 },
    { "color": "white", "price": 100 }
  ]
}
~~~

Truy vấn điều kiện color=black và price<130 có thể khớp document vì các giá trị riêng lẻ tồn tại, dù không có một variant nào thỏa cả hai.

### 4.2. Nested array

Khai báo nested:

~~~java
@Field(type = FieldType.Nested)
private List<ProductVariant> variants;
~~~

Nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "range": {
                "variants.price": {
                  "lt": 130
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Nested mapping giữ quan hệ giữa các field trong cùng một phần tử. Query chỉ khớp khi một variant duy nhất đáp ứng cả hai điều kiện.

### 4.3. Chi phí của nested

Nested object được index như hidden document liên kết với parent. Một parent có nhiều nested elements làm tăng số document nội bộ và chi phí indexing/query.

Nên dùng nested khi cần giữ quan hệ giữa các field trong từng phần tử mảng. Không nên dùng nested chỉ vì JSON có object lồng nhau. Với object đơn hoặc mảng object chỉ dùng để hiển thị, object mapping có thể đơn giản và tiết kiệm hơn.

## 5. Một-nhiều: nhúng dữ liệu con hay tách document?

Quan hệ một-nhiều là quyết định quan trọng nhất khi thiết kế document.

Ví dụ đơn hàng có các dòng hàng:

~~~json
{
  "orderId": "ORD-2026-1001",
  "customerId": "C-100",
  "status": "PAID",
  "lines": [
    {
      "lineId": "L-1",
      "productId": "P-1042",
      "sku": "KB-1042",
      "productName": "Mechanical Keyboard",
      "quantity": 2,
      "unitPrice": 129.5
    },
    {
      "lineId": "L-2",
      "productId": "P-2077",
      "sku": "MS-2077",
      "productName": "Wireless Mouse",
      "quantity": 1,
      "unitPrice": 49.9
    }
  ]
}
~~~

### 5.1. Nhúng khi số phần tử có giới hạn

Nhúng lines trong order phù hợp nếu:

- Một đơn hàng có số dòng hữu hạn và thường không quá lớn.
- Trang đơn hàng luôn cần các dòng hàng.
- Dòng hàng không cần được tìm kiếm hoặc phân trang độc lập với đơn hàng.
- Việc cập nhật đơn hàng thường được thực hiện như một aggregate.

Ưu điểm là lấy đơn hàng trong một request, không cần ghép với index sản phẩm.

### 5.2. Snapshot dữ liệu tại thời điểm giao dịch

Order line thường nên lưu tên sản phẩm, SKU và đơn giá tại thời điểm mua. Đây là snapshot lịch sử, không phải bản sao cần đồng bộ theo mọi thay đổi sản phẩm.

Nếu sản phẩm đổi tên hoặc giá sau khi đơn hàng được đặt, lịch sử đơn hàng vẫn phải hiển thị dữ liệu tại thời điểm giao dịch. Vì vậy, cần phân biệt:

- Snapshot bất biến theo nghiệp vụ: giữ nguyên giá trị đã giao dịch.
- Denormalized current value: bản sao cần phản ánh dữ liệu mới nhất.

Không nên cập nhật hàng loạt lịch sử đơn hàng khi sản phẩm đổi giá nếu đó là giá mua tại thời điểm đặt.

### 5.3. Khi nào tách dòng hàng thành document?

Nếu hệ thống cần tìm kiếm hàng trăm triệu dòng hàng, lọc theo sản phẩm, phân tích từng dòng hoặc cập nhật chúng độc lập, có thể index mỗi dòng thành document riêng:

~~~json
{
  "lineId": "L-1",
  "orderId": "ORD-2026-1001",
  "customerId": "C-100",
  "orderStatus": "PAID",
  "productId": "P-1042",
  "sku": "KB-1042",
  "productName": "Mechanical Keyboard",
  "quantity": 2,
  "unitPrice": 129.5
}
~~~

Các field orderStatus, customerId và productName được sao chép để truy vấn dòng hàng trực tiếp. Đổi lại, nếu order status thay đổi, các line document có thể cần cập nhật.

### 5.4. Không nhúng mảng tăng không giới hạn

Không nên nhúng toàn bộ lịch sử hoạt động, sự kiện hoặc review vào một document cha nếu số lượng phần tử tăng liên tục.

Các rủi ro:

- Document ngày càng lớn và tốn chi phí đọc/ghi.
- Cập nhật một phần tử có thể dẫn đến reindex document lớn.
- Một document quá lớn có thể gây áp lực heap, network và merge.
- Khó phân trang riêng phần tử con.
- Giới hạn kích thước document và nested objects có thể bị chạm tới.

Với dữ liệu con tăng không giới hạn, thường nên tách thành document riêng và sao chép các field cha cần thiết để tìm kiếm.

## 6. Sao chép thuộc tính cha vào document con

Giả sử ứng dụng cần tìm tất cả review của sản phẩm thuộc thương hiệu KeyWorks. Review được lưu thành document riêng:

~~~json
{
  "reviewId": "R-10001",
  "productId": "P-1042",
  "productName": "Mechanical Keyboard",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "rating": 5,
  "content": "Excellent keyboard"
}
~~~

Document review chứa brandName và productName được sao chép từ product. Khi người dùng tìm review theo thương hiệu, query chạy trực tiếp trên index reviews:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "brandId": "B-10"
          }
        },
        {
          "range": {
            "rating": {
              "gte": 4
            }
          }
        }
      ]
    }
  }
}
~~~

Không cần JOIN review với product và brand để lọc. brandId là field ổn định để lọc; brandName là bản sao phục vụ hiển thị hoặc tìm kiếm toàn văn.

### 6.1. Cẩn thận khi thuộc tính cha thay đổi

Nếu thương hiệu đổi tên, tất cả review có brandName cũ có thể cần cập nhật. Một thương hiệu có hàng triệu review sẽ tạo ra fan-out write rất lớn.

Các lựa chọn:

- Chỉ sao chép ID ổn định và lấy tên thương hiệu từ một cache/service khi hiển thị.
- Sao chép cả tên nhưng chấp nhận eventual consistency.
- Dùng index read model tổng hợp được cập nhật theo event.
- Giữ tên tại thời điểm review nếu đó là snapshot lịch sử.

Quyết định phụ thuộc việc tên cần phản ánh hiện tại hay lịch sử.

### 6.2. Denormalize chỉ field cần thiết

Không cần sao chép toàn bộ parent object. Chỉ sao chép các field mà truy vấn con cần:

~~~json
{
  "reviewId": "R-10001",
  "productId": "P-1042",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "productCategory": "keyboards",
  "rating": 5
}
~~~

Giữ document gọn giúp giảm dung lượng index, chi phí đồng bộ và thời gian đọc.

## 7. Nhiều-nhiều: tag, category và membership

Quan hệ nhiều-nhiều trong cơ sở dữ liệu quan hệ thường được biểu diễn bằng bảng nối. Trong Elasticsearch, nhiều trường hợp có thể lưu mảng ID hoặc mảng object ngay trong document.

Ví dụ bài viết gắn nhiều tag:

~~~json
{
  "articleId": "A-100",
  "title": "Elasticsearch Data Modeling",
  "tagIds": ["search", "database", "java"],
  "tagNames": ["Search", "Database", "Java"]
}
~~~

Query tìm bài viết có tag database:

~~~json
{
  "query": {
    "term": {
      "tagIds": "database"
    }
  }
}
~~~

Với field keyword nhiều giá trị, term query khớp nếu có một giá trị phù hợp.

### 7.1. Khi cần thuộc tính của từng quan hệ

Nếu quan hệ bài viết-tag có thêm thuộc tính như thứ tự hiển thị, người gắn, thời điểm gắn hoặc mức độ ưu tiên, lưu mảng object:

~~~json
{
  "articleId": "A-100",
  "tags": [
    {
      "id": "search",
      "name": "Search",
      "position": 1
    },
    {
      "id": "database",
      "name": "Database",
      "position": 2
    }
  ]
}
~~~

Nếu cần truy vấn theo các thuộc tính phải thuộc cùng một quan hệ, dùng nested:

~~~json
{
  "query": {
    "nested": {
      "path": "tags",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tags.id": "database"
              }
            },
            {
              "range": {
                "tags.position": {
                  "lte": 2
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

### 7.2. Khi nào cần index quan hệ riêng?

Nếu một quan hệ có số lượng lớn, có vòng đời độc lập hoặc cần truy vấn và phân trang như một thực thể, có thể tạo index relation riêng:

~~~json
{
  "articleId": "A-100",
  "tagId": "database",
  "tagName": "Database",
  "position": 2,
  "createdAt": "2026-03-01T10:00:00Z"
}
~~~

Document quan hệ có thể sao chép articleTitle hoặc tagCategory nếu truy vấn cần lọc theo chúng. Không có join tự động để lấy thông tin từ article và tag.

## 8. Một document có thể phục vụ nhiều truy vấn bằng các bản sao có chọn lọc

Ví dụ product document:

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "brand": {
    "id": "B-10",
    "name": "KeyWorks"
  },
  "category": {
    "id": "C-KEY",
    "name": "Keyboards"
  },
  "searchText": "Mechanical Keyboard KeyWorks Keyboards",
  "price": 129.5,
  "available": true
}
~~~

Document vừa hỗ trợ trang chi tiết, vừa hỗ trợ filter theo brand/category, vừa hỗ trợ tìm kiếm toàn văn. Tuy nhiên, field lặp như brand.name và category.name cần được cập nhật khi dữ liệu nguồn đổi.

Không phải mọi field lặp đều phải được lưu dưới cùng một dạng:

- ID dùng cho filter chính xác và liên kết logic.
- Tên dùng cho hiển thị hoặc full-text search.
- Keyword subfield dùng cho sort/aggregation.
- Text field dùng cho match query.
- Snapshot dùng cho lịch sử giao dịch.

Mapping nên phản ánh mục đích truy vấn của từng field.

## 9. Spring Data Elasticsearch: lưu document phi chuẩn hóa

Spring Data Elasticsearch không tự thực hiện relational join. Entity được map thành một Elasticsearch document. Các object và field đã được đưa vào entity sẽ được ghi cùng document theo mapping.

Ví dụ một read model sản phẩm:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String brandName;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Keyword)
    private String categoryName;

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    // Constructors, getters và setters
}

public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Double)
    private double price;

    // Constructors, getters và setters
}
~~~

Document này lưu sẵn tên brand/category để search và hiển thị. variants được map nested vì truy vấn có thể cần điều kiện tương quan giữa color, SKU và price trong cùng một biến thể.

### 9.1. Tạo document read model từ nguồn chuẩn

Không nên để controller tự ghép các object rồi ghi trực tiếp vào Elasticsearch. Tạo mapper hoặc projector chuyên trách:

~~~java
public ProductSearchDocument toSearchDocument(
        Product product,
        Brand brand,
        Category category) {

    ProductSearchDocument document = new ProductSearchDocument();
    document.setId(product.getId());
    document.setName(product.getName());
    document.setBrandId(brand.getId());
    document.setBrandName(brand.getName());
    document.setCategoryId(category.getId());
    document.setCategoryName(category.getName());
    document.setVariants(product.getVariants().stream()
        .map(this::toVariant)
        .toList());

    return document;
}
~~~

Đoạn code minh họa projector đọc các nguồn dữ liệu chuẩn rồi tạo document phù hợp với query model. Trong dự án, các class nguồn và mapper sẽ phụ thuộc kiến trúc domain thực tế.

### 9.2. Lưu bằng ElasticsearchOperations

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchIndexer {

    private final ElasticsearchOperations operations;

    public ProductSearchIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void index(ProductSearchDocument document) {
        operations.save(document);
    }
}
~~~

save ghi document theo ID và mapping metadata. Nó không tìm các document brand/category khác để ghép tự động. Dữ liệu denormalized phải được chuẩn bị trước khi gọi save.

### 9.3. Repository và query

~~~java
public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductSearchDocument, String> {

    List<ProductSearchDocument> findByBrandId(String brandId);

    List<ProductSearchDocument> findByCategoryId(String categoryId);
}
~~~

Các query method này chạy trên field đã được sao chép trong product document. Không cần truy vấn brand index để lấy tên hoặc category index để lọc.

## 10. Duy trì nhất quán khi dữ liệu nguồn thay đổi

Phi chuẩn hóa đặt ra câu hỏi quan trọng: nếu một thuộc tính nguồn thay đổi, các bản sao trong nhiều document sẽ được cập nhật thế nào?

Giả sử brand B-10 đổi tên từ KeyWorks thành KeyWorks Labs. Tên này được sao chép vào 500.000 product documents và 2 triệu review documents.

Ứng dụng cần quyết định:

- Cập nhật tất cả bản sao ngay lập tức hay chấp nhận trễ?
- Cập nhật đồng bộ trong một request hay chạy nền?
- Nếu một phần batch thất bại, tiếp tục từ đâu?
- Làm sao tránh event cũ ghi đè dữ liệu mới?
- Làm sao phát hiện document bị bỏ sót?

### 10.1. Chọn nguồn dữ liệu chuẩn

Mỗi thuộc tính phải có nguồn chuẩn rõ ràng:

| Thuộc tính | Nguồn chuẩn | Các bản sao |
| --- | --- | --- |
| Tên sản phẩm | Product database/service | Product search document, suggestion index |
| Tên thương hiệu hiện tại | Brand database/service | Product search document, review read model |
| Giá mua tại thời điểm đặt | Order line | Order document, order line index |
| Trạng thái đơn hàng | Order service | Order document, line read model nếu cần |
| Số lượt chọn gợi ý | Analytics/event stream | Completion weight |

Không dùng Elasticsearch read model làm nguồn chuẩn cho dữ liệu giao dịch nếu nó chỉ được thiết kế để phục vụ tìm kiếm.

### 10.2. Event-driven projection

Một cách phổ biến là cập nhật read model bằng event:

~~~text
Nguồn dữ liệu chuẩn
       |
       v
  Ghi transaction
       |
       v
   Outbox event
       |
       v
  Event publisher
       |
       v
 Projector / consumer
       |
       v
 Elasticsearch index
~~~

Ví dụ event BrandRenamed:

~~~json
{
  "eventId": "EVT-9001",
  "eventType": "BrandRenamed",
  "brandId": "B-10",
  "newName": "KeyWorks Labs",
  "version": 42,
  "occurredAt": "2026-03-12T09:00:00Z"
}
~~~

Consumer nhận event rồi cập nhật những product documents có brandId=B-10. Nếu cần fan-out lớn, có thể phát lệnh cập nhật theo batch hoặc xây dựng lại read model từ nguồn chuẩn.

### 10.3. Transactional outbox

Nếu ghi DB và publish message bằng hai thao tác độc lập, có thể xảy ra:

- DB commit thành công nhưng publish thất bại.
- Publish thành công nhưng transaction DB rollback.

Transactional outbox ghi thay đổi nghiệp vụ và event vào cùng transaction DB. Một publisher riêng đọc outbox rồi gửi event. Cách này giảm nguy cơ mất event giữa hai hệ thống.

Elasticsearch vẫn được cập nhật bất đồng bộ, nên read model thường có eventual consistency.

### 10.4. Idempotent consumer

Event có thể được gửi lại khi consumer retry. Projector nên xử lý idempotent để xử lý cùng event nhiều lần không tạo sai lệch.

Các cách thường dùng:

- Dùng event ID để phát hiện sự kiện đã xử lý.
- Dùng document ID ổn định để ghi đè cùng read model.
- Dùng version nguồn để từ chối event cũ.
- Thiết kế update là phép gán giá trị xác định thay vì phép cộng không kiểm soát.
- Ghi nhận lỗi để có thể retry hoặc đưa vào dead-letter queue.

### 10.5. Tránh event cũ ghi đè dữ liệu mới

Giả sử event version 42 đổi brand name, sau đó version 43 đổi tiếp. Nếu event 42 đến trễ, consumer không nên ghi tên cũ đè lên tên mới.

Có thể lưu source version trong read model:

~~~json
{
  "brandId": "B-10",
  "brandName": "KeyWorks Labs",
  "brandVersion": 43
}
~~~

Projector chỉ áp dụng event có version mới hơn version đang lưu. Với update có điều kiện, có thể dùng Elasticsearch optimistic concurrency hoặc logic kiểm soát version ở tầng ứng dụng tùy mô hình.

## 11. Fan-out update và chi phí cập nhật

Khi một field được sao chép vào nhiều document, thay đổi của field đó có thể cần cập nhật nhiều document. Đây là fan-out write.

Ví dụ:

| Nguồn thay đổi | Số document phụ thuộc | Tác động |
| --- | ---: | --- |
| Đổi tên một brand | 500.000 product | Cập nhật brandName trong product index |
| Đổi tên một category | 2.000.000 product | Cập nhật categoryName |
| Đổi trạng thái một order | 50 order lines | Cập nhật read model line nếu cần lọc theo trạng thái |

### 11.1. Cập nhật theo batch

Không nên gửi một request update riêng cho từng document nếu số lượng lớn. Có thể dùng Bulk API, scroll/PIT để duyệt tập ID và update theo batch, hoặc tạo lại index read model.

Quy trình batch:

1. Xác định document phụ thuộc bằng field ID ổn định.
2. Lấy một batch ID hoặc document.
3. Tạo bản cập nhật từ nguồn chuẩn.
4. Gửi bulk update/index.
5. Ghi nhận số thành công/thất bại.
6. Retry các item lỗi theo chính sách.
7. Tiếp tục cho tới khi hoàn tất.
8. Ghi lại watermark/version để tiếp tục sau sự cố.

Kích thước batch cần đo theo payload, latency, heap và tải cluster. Batch quá lớn có thể gây áp lực memory và tăng thời gian xử lý.

### 11.2. Update by query

Elasticsearch hỗ trợ _update_by_query để cập nhật nhiều document thỏa điều kiện. Ví dụ đổi một field sao chép:

~~~http
POST products/_update_by_query
{
  "query": {
    "term": {
      "brandId": "B-10"
    }
  },
  "script": {
    "source": "ctx._source.brandName = params.name",
    "params": {
      "name": "KeyWorks Labs"
    }
  }
}
~~~

_update_by_query hữu ích cho một thay đổi đơn giản áp dụng đồng loạt. Tuy nhiên, nó không thay thế nguồn dữ liệu chuẩn hoặc quy trình đồng bộ đầy đủ. Nếu document cần được tái tạo từ nhiều nguồn, projector ở ứng dụng thường an toàn hơn việc chỉ sửa một field trong source.

Update by query có thể chạy lâu, tạo version conflict hoặc bị giới hạn bởi task/cancel/timeout. Hãy theo dõi task và có kế hoạch xử lý lỗi một phần.

## 12. Reindex và xây dựng lại read model

Khi thay đổi cấu trúc document hoặc quy tắc denormalization, có thể cần tạo index mới và dựng lại dữ liệu.

~~~text
Nguồn dữ liệu chuẩn
       |
       v
 Projector phiên bản mới
       |
       v
 products-v2
       |
       v
 Kiểm tra dữ liệu
       |
       v
 Chuyển alias products
~~~

Một quy trình an toàn:

1. Tạo index mới với mapping và settings đã cập nhật.
2. Chạy backfill từ nguồn chuẩn hoặc read model đáng tin cậy.
3. Tiếp tục nhận event thay đổi trong lúc backfill.
4. Đồng bộ các event phát sinh sau watermark.
5. Kiểm tra số document, field bắt buộc và kết quả truy vấn.
6. Chuyển alias đọc sang index mới.
7. Theo dõi lỗi và latency sau cutover.
8. Giữ index cũ trong thời gian rollback phù hợp rồi mới xóa.

Không nên chỉ reindex từ Elasticsearch cũ nếu read model cũ đã thiếu field hoặc mang dữ liệu sai. Khi cần sửa quy tắc denormalization, nguồn chuẩn nên là dữ liệu gốc hoặc một event log đủ để tái dựng.

## 13. CQRS và read model phi chuẩn hóa

Một kiến trúc thường dùng là CQRS: mô hình ghi và mô hình đọc được tối ưu cho mục tiêu khác nhau.

- Write model bảo vệ quy tắc nghiệp vụ và tính nhất quán của giao dịch.
- Read model được thiết kế để truy vấn nhanh, có thể chứa dữ liệu lặp lại.
- Event hoặc pipeline đồng bộ cập nhật read model từ write model.

~~~text
Command
   |
   v
Write model
   |
   v
Transaction
   |
   v
Domain event
   |
   v
Projector
   |
   v
Elasticsearch read model
   |
   v
Search API
~~~

Spring Data Elasticsearch thường nằm ở phía read model hoặc search projection. Không cần ép domain entity của ứng dụng trùng hoàn toàn với document Elasticsearch.

### 13.1. Nhiều read model cho cùng nguồn

Một product event có thể cập nhật:

- Product search index: phục vụ full-text search và filter.
- Product suggestion index: phục vụ completion.
- Category summary index: phục vụ thống kê danh mục.
- Inventory view: phục vụ hiển thị tồn kho gần nhất.

Mỗi read model có schema và tần suất cập nhật riêng. Điều này giúp tránh một document phình to để đáp ứng mọi truy vấn.

### 13.2. Eventual consistency

Sau khi write model commit, read model có thể chưa cập nhật ngay. Ứng dụng cần quyết định cách xử lý:

- Hiển thị thông báo dữ liệu có thể cập nhật sau vài giây.
- Đọc trạng thái mới trực tiếp từ write service cho màn hình giao dịch quan trọng.
- Dùng version để biết read model đã bắt kịp hay chưa.
- Cho phép truy vấn theo ID qua nguồn chuẩn khi cần read-after-write.

Không nên tuyên bố dữ liệu Elasticsearch luôn nhất quán tức thì nếu cập nhật diễn ra bất đồng bộ.

## 14. Khi nào parent-child join field đáng cân nhắc?

Elasticsearch có kiểu mapping join để biểu diễn quan hệ parent-child trong cùng một index. Đây là ngoại lệ có chủ đích so với mô hình phi chuẩn hóa.

Parent-child có thể hữu ích khi:

- Một parent có rất nhiều child documents.
- Child được cập nhật độc lập và thường xuyên.
- Không muốn reindex toàn bộ parent khi thêm/sửa một child.
- Truy vấn thực sự cần chọn parent theo child hoặc child theo parent.

Ví dụ sản phẩm là parent và review là child. Mỗi review có thể được index/cập nhật riêng.

### 14.1. Join field mapping

Mapping JSON:

~~~json
{
  "mappings": {
    "properties": {
      "relation": {
        "type": "join",
        "relations": {
          "product": "review"
        }
      },
      "sku": {
        "type": "keyword"
      },
      "rating": {
        "type": "integer"
      },
      "content": {
        "type": "text"
      }
    }
  }
}
~~~

Document parent:

~~~json
{
  "sku": "KB-1042",
  "relation": "product"
}
~~~

Document child:

~~~json
{
  "rating": 5,
  "content": "Excellent keyboard",
  "relation": {
    "name": "review",
    "parent": "P-1042"
  }
}
~~~

### 14.2. Điều kiện routing

Parent và child phải nằm trên cùng shard. Khi index child, routing phải bằng routing value của parent. Nếu parent dùng ID làm routing mặc định, child cần được gửi với routing của parent.

Đây là ràng buộc quan trọng: cùng index chưa đủ, chúng phải cùng shard. Nếu routing không khớp, parent-child query có thể không tìm thấy quan hệ hoặc việc index child có thể thất bại tùy thao tác.

### 14.3. has_child query

Tìm sản phẩm có ít nhất một review rating từ 4 trở lên:

~~~json
{
  "query": {
    "has_child": {
      "type": "review",
      "query": {
        "range": {
          "rating": {
            "gte": 4
          }
        }
      },
      "score_mode": "max"
    }
  }
}
~~~

### 14.4. has_parent query

Tìm review thuộc sản phẩm có SKU KB-1042:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "product",
      "query": {
        "term": {
          "sku": "KB-1042"
        }
      }
    }
  }
}
~~~

### 14.5. Chi phí parent-child

Parent-child tránh phải nhúng toàn bộ child vào parent, nhưng query join có chi phí cao hơn query trực tiếp trên field. Elasticsearch phải thực hiện công việc liên kết dựa trên global ordinals và quan hệ trong shard.

Một số lưu ý:

- Parent và child phải cùng index và shard.
- Child cần routing đúng theo parent.
- Join query có thể tốn CPU và heap hơn query thông thường.
- Thêm nhiều cấp quan hệ làm mô hình và query phức tạp.
- Không dùng parent-child chỉ để mô phỏng mọi khóa ngoại của SQL.

Nếu truy vấn thường xuyên cần một vài field của parent trên child, sao chép các field đó vào child thường đơn giản và nhanh hơn.

### 14.6. Parent-child trong Spring Data Elasticsearch

Spring Data Elasticsearch có abstraction cho join field, bao gồm JoinField và annotation @JoinTypeRelations/@JoinTypeRelation trong các phiên bản hỗ trợ.

Ví dụ khái quát:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "product-relations")
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "product",
            children = {"review"}
        )
    }
)
public class ProductRelationDocument {

    @Id
    private String id;

    private String sku;
    private Integer rating;
    private String content;

    private JoinField<String> relation;

    // Constructors, getters và setters
}
~~~

Parent có thể dùng new JoinField<>("product"); child dùng tên relation và parent ID theo constructor được cung cấp bởi phiên bản Spring Data. Cần đặt routing của child theo parent và bảo đảm API ghi thực sự truyền routing đó.

Các API join field và cách cấu hình routing có thể khác giữa các phiên bản Spring Data Elasticsearch. Hãy đối chiếu Javadoc của dependency dự án trước khi áp dụng code cụ thể. Với nhiều ứng dụng, một projector tạo denormalized document vẫn dễ vận hành hơn parent-child.

## 15. So sánh embed, copy fields và parent-child

| Tiêu chí | Embed object/nested | Copy field vào document | Parent-child |
| --- | --- | --- | --- |
| Đọc dữ liệu cùng nhau | Rất phù hợp | Phù hợp với field đã sao chép | Có thể cần join query |
| Cập nhật child riêng | Có thể phải cập nhật parent | Cập nhật document chứa bản sao | Có thể cập nhật child riêng |
| Số lượng child lớn | Không phù hợp nếu tăng không giới hạn | Phù hợp khi child là document riêng | Có thể phù hợp |
| Tìm parent theo child | Nested query nếu nested | Query trên read model có field phù hợp | has_child |
| Tìm child theo parent | Nested query/parent document | Copy parent ID vào child | has_parent |
| Độ phức tạp | Thấp đến trung bình | Cần đồng bộ bản sao | Cao hơn, cần routing |
| Chi phí truy vấn | Thường thấp khi document model phù hợp | Thường thấp vì field nằm cùng document | Join query tốn kém hơn |

Một nguyên tắc thực tế:

- Nhúng dữ liệu con nhỏ, có giới hạn và thường được đọc cùng cha.
- Sao chép field cha vào document con khi cần lọc/tìm kiếm child độc lập.
- Dùng parent-child khi child rất nhiều, có vòng đời cập nhật riêng và lợi ích tránh cập nhật parent lớn hơn chi phí join.

## 16. Chọn snapshot hay bản sao phản ánh trạng thái hiện tại?

Không phải mọi dữ liệu lặp đều cần được đồng bộ theo cùng một chính sách.

| Field | Loại dữ liệu | Khi nguồn đổi |
| --- | --- | --- |
| Tên sản phẩm trong order line | Snapshot giao dịch | Giữ nguyên |
| Đơn giá đã thanh toán | Snapshot giao dịch | Giữ nguyên |
| Tên brand trong product search | Bản sao trạng thái hiện tại | Cập nhật |
| Tên category trong product search | Bản sao trạng thái hiện tại | Cập nhật |
| Tên người đánh giá trong review | Tùy chính sách riêng tư/lịch sử | Có thể ẩn danh hoặc cập nhật |

Trước khi sao chép một field, hãy quyết định nó mang ý nghĩa lịch sử hay hiện tại. Nếu không, một job đồng bộ có thể phá hỏng dữ liệu lịch sử hoặc một bản sao cũ có thể gây sai lệch kết quả tìm kiếm.

## 17. Thiết kế document không quá lớn

Phi chuẩn hóa không có nghĩa đưa mọi dữ liệu liên quan vào cùng một document. Document quá lớn sẽ làm tăng chi phí đọc, ghi, truyền mạng và merge segment.

Các dấu hiệu nên tách dữ liệu:

- Mảng con tăng không giới hạn.
- Phần tử con được cập nhật thường xuyên và độc lập.
- Chỉ một số màn hình cần phần tử con.
- Cần phân trang hoặc aggregation riêng trên dữ liệu con.
- Một document được nhiều writer cập nhật đồng thời.
- Dữ liệu con có lifecycle và retention khác parent.

### 17.1. Tách lịch sử sự kiện

Không nên lưu toàn bộ lịch sử trạng thái vào một order document nếu đơn hàng có thể có rất nhiều event.

Thay vào đó, order document giữ trạng thái hiện tại:

~~~json
{
  "orderId": "ORD-2026-1001",
  "status": "SHIPPED",
  "updatedAt": "2026-03-12T09:00:00Z"
}
~~~

Mỗi event là document riêng:

~~~json
{
  "eventId": "EVT-100",
  "orderId": "ORD-2026-1001",
  "orderStatus": "SHIPPED",
  "eventType": "OrderShipped",
  "occurredAt": "2026-03-12T09:00:00Z"
}
~~~

orderStatus hoặc các field cha khác có thể được sao chép vào event nếu truy vấn lịch sử cần lọc nhanh theo chúng. Nếu trạng thái event là snapshot tại thời điểm xảy ra, không cập nhật nó theo trạng thái order hiện tại.

## 18. Xử lý cập nhật đồng thời và ghi đè

Với document denormalized, nhiều nguồn event có thể cập nhật cùng một document. Nếu hai projector cùng ghi toàn bộ entity, bản cập nhật sau có thể ghi đè field do projector khác quản lý.

Ví dụ:

- Projector product cập nhật name và price.
- Projector inventory cập nhật available và stock.
- Projector brand cập nhật brandName.

Nếu mỗi projector dựng toàn bộ ProductSearchDocument từ dữ liệu không đầy đủ rồi gọi save, chúng có thể xóa field do projector khác quản lý.

### 18.1. Chia quyền sở hữu field

Hãy quy định rõ projector nào sở hữu field nào. Có thể:

- Một projector duy nhất xây dựng toàn bộ read model từ nguồn chuẩn.
- Các projector cập nhật partial field bằng update script hoặc partial update có kiểm soát.
- Dùng event aggregate để tạo một bản cập nhật hoàn chỉnh.
- Tách index theo read model hoặc bounded context nếu các nhóm cập nhật độc lập.

Không dùng save với entity partial nếu hành vi ghi đè có thể làm mất field khác.

### 18.2. Optimistic concurrency và version

Elasticsearch hỗ trợ sequence number và primary term để bảo vệ update khỏi ghi đè không mong muốn. Spring Data có thể cung cấp các cơ chế versioning/concurrency tương ứng tùy API.

Với projector event-driven, version nghiệp vụ trong event thường hữu ích hơn chỉ dựa vào thời điểm đến. Consumer có thể so sánh version nguồn để bỏ qua event cũ.

## 19. Xây dựng index từ nhiều nguồn

Một product read model có thể cần product, brand, category và inventory. Projector cần hợp nhất chúng.

~~~text
Product source ----+
                   |
Brand source ------+----> Product projector ---> products index
                   |
Category source ---+
                   |
Inventory source -+
~~~

Có hai chiến lược phổ biến:

**Synchronous composition:** projector đọc các nguồn cần thiết rồi ghi document hoàn chỉnh. Cách này phù hợp với import hoặc cập nhật có thể thực hiện đồng bộ, nhưng cần kiểm soát latency và lỗi phụ thuộc.

**Event-driven projection:** mỗi thay đổi nguồn phát event; projector duy trì read model bằng cách cập nhật các field tương ứng. Cách này mở rộng tốt hơn cho pipeline bất đồng bộ nhưng cần xử lý event ordering, retry và rebuild.

Nếu một nguồn tạm thời không khả dụng, không nên ghi document thiếu field rồi vô tình xóa dữ liệu tốt trước đó. Có thể retry, giữ bản read model hiện tại hoặc đánh dấu trạng thái projection chưa hoàn chỉnh.

## 20. Reconciliation: phát hiện bản sao bị lệch

Event-driven projection có thể bỏ sót event do lỗi vận hành, bug hoặc migration. Cần có cách đối chiếu read model với nguồn chuẩn.

Một số kỹ thuật:

- Lưu source version hoặc updatedAt trong read model.
- So sánh số lượng document theo tenant/category.
- Lấy mẫu document và đối chiếu các field quan trọng.
- Chạy job rebuild theo partition hoặc theo ID range.
- Ghi nhận event cuối cùng đã xử lý.
- Đưa item lỗi vào dead-letter queue và có quy trình replay.

Reconciliation không cần chạy liên tục trên toàn bộ dữ liệu nếu chi phí lớn. Có thể chạy theo lịch, theo partition hoặc sau sự kiện migration.

## 21. Khi nào nên dùng nhiều index?

Một số dữ liệu có cùng nguồn nhưng phục vụ các query khác nhau. Tách index có thể giúp mapping và lifecycle phù hợp hơn:

| Index | Document model | Truy vấn chính |
| --- | --- | --- |
| products | Product + brand/category summary + variants | Tìm sản phẩm |
| reviews | Review + productId/brandId/categoryId | Tìm và phân tích review |
| orders | Order + bounded line snapshots | Đọc đơn hàng |
| order-lines | Một document mỗi line + order/product summary | Báo cáo dòng hàng |
| product-suggestions | Input, weight, contexts | Autocomplete |

Tách index làm tăng công việc đồng bộ, nhưng mỗi index có thể tối ưu mapping, shard, refresh, retention và quyền truy cập riêng.

Không nên tạo một index cho mỗi bảng quan hệ chỉ vì dữ liệu nguồn có nhiều bảng. Mỗi index nên đại diện cho một tập truy vấn/read model có lý do rõ ràng.

## 22. Quy trình quyết định mô hình

Khi chuyển một mô hình quan hệ sang Elasticsearch, có thể làm theo trình tự:

1. Liệt kê các truy vấn đọc quan trọng và field cần trả về.
2. Xác định aggregate hoặc đối tượng gốc của mỗi màn hình/search.
3. Nhúng object một-một khi chúng thường được đọc cùng nhau.
4. Với mảng object, chọn object hay nested theo nhu cầu giữ quan hệ giữa các field.
5. Nhúng mảng con có giới hạn và vòng đời gắn với parent.
6. Tách collection lớn hoặc tăng không giới hạn thành document riêng.
7. Sao chép ID và các thuộc tính cha cần filter/search vào document con.
8. Phân biệt snapshot lịch sử với bản sao trạng thái hiện tại.
9. Xác định nguồn chuẩn và cơ chế cập nhật các bản sao.
10. Dùng event/outbox, batch update, version và retry để quản lý eventual consistency.
11. Chỉ cân nhắc parent-child khi child độc lập, số lượng lớn và join thực sự cần thiết.
12. Kiểm tra kích thước document, số nested object, latency và chi phí fan-out.
13. Có kế hoạch rebuild/reindex và reconciliation khi schema hoặc quy tắc projection thay đổi.

## 23. Ví dụ tổng hợp: mô hình hóa catalog và review

Giả sử hệ thống cần:

- Tìm sản phẩm theo tên, brand, category, giá và biến thể.
- Tìm review theo sản phẩm, brand, rating.
- Trang sản phẩm hiển thị vài review mới nhất.
- Review có thể tăng lên hàng triệu bản ghi.

Một mô hình phù hợp có thể gồm:

### Product search document

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "categoryId": "C-KEY",
  "categoryName": "Keyboards",
  "price": 129.5,
  "variants": [
    {
      "sku": "KB-1042-BLK",
      "color": "black",
      "price": 129.5
    }
  ],
  "reviewSummary": {
    "count": 1250,
    "averageRating": 4.7
  }
}
~~~

Product document nhúng biến thể có giới hạn, sao chép tên brand/category để filter và giữ summary review để hiển thị nhanh.

### Review document

~~~json
{
  "reviewId": "R-10001",
  "productId": "P-1042",
  "productName": "Mechanical Keyboard",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "rating": 5,
  "content": "Excellent keyboard",
  "createdAt": "2026-03-12T09:00:00Z"
}
~~~

Review được lưu độc lập vì số lượng lớn, cần pagination, search và aggregation riêng. Các field product/brand được sao chép để filter trực tiếp.

### Luồng cập nhật

- Product đổi tên: cập nhật product index và các review read model nếu productName cần phản ánh tên hiện tại.
- Brand đổi tên: cập nhật product và review denormalized fields theo batch/event.
- Review mới: ghi review document, cập nhật reviewSummary của product qua projector.
- Review bị xóa: cập nhật count/average bằng phép tính lại hoặc quy trình aggregate có kiểm soát.

Nếu tên trong review phải là snapshot tại thời điểm viết, không cập nhật productName khi sản phẩm đổi tên. Chính sách dữ liệu quyết định projector cập nhật field nào.

## 24. Những lỗi thường gặp

**Chuyển mọi bảng SQL thành một index riêng rồi mong Elasticsearch tự JOIN.** Query DSL không cung cấp JOIN tổng quát giữa các index. Hãy thiết kế read model có field cần thiết.

**Nhúng mọi quan hệ vào một document.** Document có thể quá lớn, khó cập nhật và không thể phân trang phần tử con hiệu quả. Chỉ embed dữ liệu nhỏ, bounded và thường được đọc cùng parent.

**Dùng object array khi cần điều kiện trên cùng phần tử.** Có thể xảy ra cross-object matching. Dùng nested khi cần giữ quan hệ field trong từng object.

**Dùng nested cho mọi object.** Nested có chi phí indexing và query. Chỉ dùng khi semantics truy vấn cần nested.

**Sao chép toàn bộ parent object vào child.** Dữ liệu lặp lớn, tăng chi phí cập nhật. Chỉ sao chép field cần filter, search hoặc hiển thị.

**Không xác định nguồn chuẩn.** Khi dữ liệu lệch, không biết bản nào đúng. Mỗi field cần owner rõ ràng.

**Nhầm snapshot với dữ liệu hiện tại.** Cập nhật bản sao lịch sử có thể làm sai thông tin giao dịch. Quy định semantics trước khi đồng bộ.

**Cập nhật DB và Elasticsearch trong hai thao tác không có bảo đảm.** Có thể mất event. Dùng transactional outbox hoặc cơ chế đồng bộ bền vững.

**Consumer không idempotent.** Retry có thể làm dữ liệu sai hoặc tăng số đếm nhiều lần. Dùng event ID, version và phép cập nhật xác định.

**Ghi toàn bộ entity từ dữ liệu không đầy đủ.** Có thể ghi đè field do projector khác quản lý. Chia quyền sở hữu field hoặc dùng partial update có kiểm soát.

**Chọn parent-child chỉ để tránh sao chép vài field.** Join query tốn kém và yêu cầu routing. Sao chép field nhỏ thường đơn giản hơn.

**Không có quy trình rebuild.** Khi mapping hoặc projection logic thay đổi, read model cũ có thể không thể cập nhật đúng bằng event mới. Chuẩn bị backfill và reindex.

## 25. Tài liệu tham khảo

- [Elasticsearch - Data modeling](https://www.elastic.co/guide/en/elasticsearch/reference/current/data-modeling.html): các lựa chọn thiết kế document và quan hệ.
- [Elasticsearch - Arrays](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/array): cách Elasticsearch xử lý field nhiều giá trị.
- [Elasticsearch - Object field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/object): object mapping và giới hạn quan hệ trong mảng object.
- [Elasticsearch - Nested field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/nested): nested documents, nested query và chi phí.
- [Elasticsearch - Joining queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/joining-queries): has_child, has_parent và nested query.
- [Elasticsearch - Join field](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join): parent-child mapping, routing và giới hạn.
- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): ghi nhiều document và cập nhật theo batch.
- [Elasticsearch - Update by query](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query): cập nhật nhiều document theo query.
- [Spring Data Elasticsearch - Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): mapping entity và document.
- [Spring Data Elasticsearch - Join types](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html): hỗ trợ join field và các annotation liên quan.

Tên annotation, package và API có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy đối chiếu Javadoc của dependency trong dự án trước khi triển khai parent-child; các ví dụ mapping JSON và Query DSL thể hiện semantics phía Elasticsearch.
