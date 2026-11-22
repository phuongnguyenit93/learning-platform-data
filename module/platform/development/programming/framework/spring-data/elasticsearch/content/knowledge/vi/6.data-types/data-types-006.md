# Ánh xạ mảng, tập hợp và giá trị nhiều phần tử

## 1. Elasticsearch biểu diễn giá trị nhiều phần tử như thế nào?

Trong Elasticsearch, một field có thể chứa một giá trị hoặc nhiều giá trị cùng kiểu. Elasticsearch không có một kiểu mapping riêng tên là `array`. Mảng được biểu diễn ngay trong JSON document, còn mapping mô tả kiểu dữ liệu của từng phần tử.

Ví dụ, một sản phẩm có nhiều nhãn và nhiều mức đánh giá:

~~~json
{
  "name": "Wireless Headphones",
  "tags": ["audio", "bluetooth", "wireless"],
  "ratings": [4, 5, 5, 4]
}
~~~

Mapping có thể khai báo:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "tags": {
        "type": "keyword"
      },
      "ratings": {
        "type": "integer"
      }
    }
  }
}
~~~

Ở đây:

- `name` là một giá trị văn bản được phân tích để tìm kiếm toàn văn.
- `tags` là một field keyword có nhiều giá trị. Mỗi nhãn được lập chỉ mục như một giá trị riêng của cùng field.
- `ratings` là một field số nguyên có nhiều giá trị.

Mapping không cần khai báo `type: array`. Elasticsearch suy ra việc có nhiều giá trị từ cấu trúc JSON của document. Một document khác có thể chứa một giá trị đơn cho `tags`, ví dụ `"tags": "audio"`, mà vẫn dùng cùng mapping keyword.

Điều kiện quan trọng là các giá trị của cùng field phải tương thích với một kiểu mapping. Không nên gửi document này với `ratings` là mảng số nguyên rồi document khác lại gửi chuỗi văn bản vào cùng field. Mapping của field được dùng chung trong index; một giá trị không tương thích có thể khiến thao tác lập chỉ mục thất bại.

## 2. Ánh xạ mảng và collection từ Java

Trong ứng dụng Spring Data Elasticsearch, thuộc tính Java có thể là mảng, `List`, `Set` hoặc một kiểu `Collection` phù hợp. `MappingElasticsearchConverter` chuyển đổi các thuộc tính đó thành cấu trúc JSON khi ghi document và chuyển dữ liệu từ `_source` về đối tượng Java khi đọc.

Ví dụ entity sản phẩm:

~~~java
import java.util.List;
import java.util.Set;

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

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Integer)
    private int[] ratings;

    @Field(type = FieldType.Keyword)
    private Set<String> supportedLanguages;

    // Constructors, getters và setters
}
~~~

Các thuộc tính tương ứng có thể được lưu thành JSON như sau:

~~~json
{
  "id": "p-100",
  "name": "Wireless Headphones",
  "tags": ["audio", "bluetooth", "wireless"],
  "ratings": [4, 5, 5, 4],
  "supportedLanguages": ["en", "vi"]
}
~~~

Các điểm cần hiểu:

- `List<String>` biểu diễn một dãy giá trị và giữ thứ tự trong đối tượng Java.
- `Set<String>` biểu diễn tập hợp theo ngữ nghĩa Java, thường không cho phép phần tử trùng nhau. Thứ tự phần tử phụ thuộc loại `Set` được dùng.
- `int[]` là mảng kiểu nguyên thủy; converter có thể chuyển các phần tử thành một mảng JSON.
- `@Field(type = FieldType.Keyword)` khai báo kiểu của từng giá trị trong collection. Annotation không cần một tùy chọn riêng để bật chế độ array.
- Nếu không khai báo kiểu field rõ ràng, Spring Data có thể suy luận mapping từ kiểu thuộc tính, nhưng với dữ liệu tìm kiếm nên khai báo mapping rõ ràng khi cần kiểm soát chính xác kiểu Elasticsearch.

Một collection Java không đồng nghĩa Elasticsearch lưu mọi đặc tính của collection. Ví dụ, Elasticsearch không dùng mapping để bảo đảm tính duy nhất của các phần tử trong mảng. Nếu dữ liệu đầu vào có giá trị trùng, một `List` có thể giữ chúng; còn `Set` loại trùng theo quy tắc của Java trước khi converter ghi document.

Tương tự, Elasticsearch có thể giữ thứ tự mảng trong `_source`, nhưng inverted index và các cấu trúc phục vụ tìm kiếm không được thiết kế để bảo đảm thứ tự phần tử như một danh sách Java. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy đọc dữ liệu từ `_source` hoặc biểu diễn thứ tự thành một field số rõ ràng.

## 3. Các kiểu field thường dùng với giá trị nhiều phần tử

Mảng không có kiểu mapping riêng; kiểu của field vẫn là kiểu của từng phần tử.

| Dữ liệu trong JSON | Mapping Elasticsearch | Mục đích thường gặp |
|---|---|---|
| `["audio", "video"]` | `keyword` | Nhãn, mã, danh mục, trạng thái |
| `["Spring", "Elasticsearch"]` | `text` | Nhiều đoạn văn bản cần phân tích |
| `[10, 20, 30]` | `integer` hoặc `long` | Điểm, số lượng, mã số |
| `[19.5, 25.0]` | `double` hoặc `float` | Giá trị đo, giá, điểm số |
| `["2026-01-01", "2026-02-01"]` | `date` | Nhiều mốc thời gian |
| `[true, false]` | `boolean` | Nhiều cờ trạng thái |

Với mảng `text`, Elasticsearch phân tích các giá trị theo analyzer của field. Với mảng `keyword`, mỗi giá trị vẫn là một đơn vị để so khớp chính xác, sắp xếp hoặc aggregation.

Các giá trị trong mảng cần cùng kiểu dữ liệu logic. Chẳng hạn một field `price` được ánh xạ là `double` thì các document phải cung cấp giá trị số tương thích. Không dùng chung một field để chứa lúc thì số, lúc thì chuỗi có định dạng tiền tệ.

## 4. Truy vấn trên field có nhiều giá trị

Một truy vấn trên field nhiều giá trị thường được đánh giá trên các giá trị của field đó. Với `keyword`, `term` có thể tìm document nếu ít nhất một giá trị trong field khớp chính xác.

Ví dụ document:

~~~json
{
  "name": "Wireless Headphones",
  "tags": ["audio", "bluetooth", "wireless"]
}
~~~

Truy vấn tìm document có nhãn `bluetooth`:

~~~json
{
  "query": {
    "term": {
      "tags": "bluetooth"
    }
  }
}
~~~

Truy vấn tìm document có ít nhất một nhãn trong danh sách:

~~~json
{
  "query": {
    "terms": {
      "tags": ["bluetooth", "wifi", "usb"]
    }
  }
}
~~~

`terms` thông thường có ngữ nghĩa khớp một hoặc nhiều giá trị được cung cấp. Nếu nghiệp vụ yêu cầu document phải chứa tối thiểu một số lượng giá trị nhất định trong danh sách, có thể xem xét `terms_set` và cấu hình điều kiện số lượng khớp.

Với field `text`, truy vấn `match` phân tích nội dung tìm kiếm theo search analyzer của field:

~~~json
{
  "query": {
    "match": {
      "descriptions": "wireless noise cancellation"
    }
  }
}
~~~

Nếu `descriptions` là field `text` có nhiều chuỗi, Elasticsearch lập chỉ mục các token từ các giá trị đó. Ứng dụng vẫn cần chọn analyzer và loại truy vấn phù hợp với cách người dùng tìm kiếm.

Với field số có nhiều giá trị, range query khớp document nếu có giá trị đáp ứng điều kiện:

~~~json
{
  "query": {
    "range": {
      "ratings": {
        "gte": 5
      }
    }
  }
}
~~~

Document có `ratings: [4, 5, 5, 4]` sẽ khớp vì field có giá trị thỏa mãn điều kiện `gte: 5`.

## 5. Giá trị nhiều phần tử và sắp xếp

Khi sắp xếp theo field có nhiều giá trị, Elasticsearch cần một quy tắc để chọn giá trị đại diện. Với field số, có thể cấu hình `mode`:

- `min`: lấy giá trị nhỏ nhất.
- `max`: lấy giá trị lớn nhất.
- `avg`: lấy trung bình.
- `sum`: tính tổng.
- `median`: lấy trung vị.

Ví dụ sắp xếp sản phẩm theo mức đánh giá cao nhất:

~~~json
{
  "sort": [
    {
      "ratings": {
        "order": "desc",
        "mode": "max"
      }
    }
  ]
}
~~~

Với sắp xếp tăng dần, mode mặc định thường là `min`; với sắp xếp giảm dần, mode mặc định thường là `max`. Nên khai báo `mode` rõ ràng khi kết quả có ý nghĩa nghiệp vụ cụ thể, để tránh phụ thuộc vào mặc định.

Đối với field keyword có nhiều giá trị, mode `min` hoặc `max` chọn giá trị theo thứ tự từ vựng. Đây không nhất thiết là thứ tự trong mảng JSON. Ví dụ mảng `["wireless", "audio"]` không có nghĩa Elasticsearch sẽ sắp xếp theo phần tử đầu tiên.

Nếu cần sắp xếp theo một phần tử có điều kiện, chẳng hạn giá của biến thể màu đen, cần thiết kế mapping và nested sort phù hợp. Không nên giả định sort trên mảng object tự động chọn đúng object theo điều kiện nghiệp vụ.

## 6. Aggregation trên field nhiều giá trị

Field keyword nhiều giá trị thường hữu ích cho aggregation. Ví dụ mỗi sản phẩm có nhiều tag, ứng dụng muốn đếm số sản phẩm theo tag:

~~~json
{
  "size": 0,
  "aggs": {
    "tags": {
      "terms": {
        "field": "tags"
      }
    }
  }
}
~~~

Aggregation tạo bucket cho các giá trị tag xuất hiện trong dữ liệu. Điều này hỗ trợ xây dựng facet hoặc bộ lọc trên giao diện.

Với field số nhiều giá trị, có thể tính thống kê:

~~~json
{
  "size": 0,
  "aggs": {
    "rating_stats": {
      "stats": {
        "field": "ratings"
      }
    }
  }
}
~~~

Kết quả thống kê có thể bao gồm số lượng, min, max, sum và avg của các giá trị được lập chỉ mục. Cần xác định rõ ý nghĩa của phép thống kê: trung bình trên mọi rating được lưu hay trung bình rating đã được tổng hợp ở cấp sản phẩm. Hai mô hình dữ liệu này cho kết quả khác nhau.

## 7. Mảng object và vấn đề mất quan hệ giữa các thuộc tính

Mảng giá trị đơn giản như `tags` không gây khó khăn về quan hệ giữa các phần tử. Tuy nhiên, mảng object cần được thiết kế cẩn thận.

Ví dụ sản phẩm có nhiều biến thể:

~~~json
{
  "name": "T-Shirt",
  "variants": [
    {
      "color": "black",
      "size": "S",
      "stock": 0
    },
    {
      "color": "white",
      "size": "M",
      "stock": 12
    }
  ]
}
~~~

Nếu `variants` được mapping mặc định là kiểu `object`, Elasticsearch sẽ làm phẳng các thuộc tính của các object trong mảng. Có thể hình dung dữ liệu được lập chỉ mục như:

~~~text
variants.color = ["black", "white"]
variants.size  = ["S", "M"]
variants.stock = [0, 12]
~~~

Mối liên hệ giữa `color`, `size` và `stock` trong từng object không còn được giữ nguyên trong inverted index. Vì vậy, truy vấn yêu cầu màu đen và còn hàng có thể vô tình ghép `color = black` của object thứ nhất với `stock = 12` của object thứ hai.

Ví dụ truy vấn trên object thông thường:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "variants.color": "black" } },
        { "range": { "variants.stock": { "gt": 0 } } }
      ]
    }
  }
}
~~~

Truy vấn này có thể khớp document dù không có một biến thể duy nhất nào vừa màu đen vừa còn hàng. Đây là vấn đề mất tương quan giữa các object trong cùng mảng.

## 8. Dùng nested để giữ quan hệ của từng object

Nếu cần truy vấn các thuộc tính phải thuộc cùng một phần tử của mảng object, hãy dùng kiểu mapping `nested`. Elasticsearch lưu mỗi nested object như một document nội bộ riêng biệt, nhờ đó truy vấn có thể giữ phạm vi của từng object.

Mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "size": { "type": "keyword" },
          "stock": { "type": "integer" }
        }
      }
    }
  }
}
~~~

Với Spring Data Elasticsearch, khai báo collection nested bằng `@Field(type = FieldType.Nested)`:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    @Field(type = FieldType.Integer)
    private Integer stock;

    // Constructors, getters và setters
}
~~~

Trong entity cha:

~~~java
import java.util.List;

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

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    // Constructors, getters và setters
}
~~~

`FieldType.Nested` giúp Spring Data tạo mapping nested cho thuộc tính collection. Cần bảo đảm index được tạo với mapping này trước khi nạp dữ liệu. Nếu index đã tồn tại với `variants` kiểu `object`, chỉ thay annotation không tự chuyển mapping hiện tại thành `nested`; thường cần tạo index mới và reindex dữ liệu.

Truy vấn nested để tìm sản phẩm có biến thể màu đen và còn hàng:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "black" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }
  }
}
~~~

Hai điều kiện được đánh giá trong cùng một nested object. Với dữ liệu ví dụ, sản phẩm không khớp vì biến thể màu đen có stock bằng 0, còn biến thể có stock 12 lại có màu trắng.

`nested` phù hợp khi cần giữ quan hệ giữa các thuộc tính của từng phần tử. Đổi lại, nested tạo thêm document nội bộ và làm truy vấn, aggregation, sort phức tạp hơn. Không nên dùng nested cho mọi mảng object nếu không cần truy vấn giữ tương quan.

## 9. Object hay nested: lựa chọn theo cách truy vấn

| Tiêu chí | `object` (mặc định) | `nested` |
|---|---|---|
| Cách lưu chỉ mục | Làm phẳng thuộc tính của các object | Mỗi object được lập chỉ mục như nested document riêng |
| Giữ quan hệ giữa field trong cùng object | Không giữ khi truy vấn trên mảng object | Có giữ trong phạm vi nested query |
| Truy vấn | Query field thông thường | Cần `nested` query với `path` |
| Chi phí lập chỉ mục và truy vấn | Thường thấp hơn | Cao hơn do nested document và xử lý phạm vi |
| Phù hợp | Thuộc tính không cần liên kết theo từng phần tử | Biến thể, dòng đơn hàng, địa chỉ hoặc thành viên cần lọc theo tổ hợp field |

Ví dụ:

- Danh sách nhãn `tags: ["sale", "new"]`: dùng keyword array.
- Danh sách số đo độc lập `temperatures: [21.2, 22.1]`: dùng numeric array.
- Danh sách biến thể sản phẩm, mỗi biến thể có màu, size và tồn kho: cân nhắc nested nếu truy vấn cần các điều kiện cùng thuộc một biến thể.
- Danh sách thành viên, mỗi người có vai trò và trạng thái: dùng nested khi cần kiểm tra đúng người vừa có vai trò vừa có trạng thái tương ứng.

## 10. Giá trị null, mảng rỗng và field bị thiếu

Các trường hợp sau có ý nghĩa khác nhau ở tầng JSON và tìm kiếm:

~~~json
{
  "tags": ["audio", "wireless"],
  "emptyTags": [],
  "unknownTags": null
}
~~~

- Mảng có giá trị được lập chỉ mục theo từng phần tử.
- Mảng rỗng không tạo giá trị được lập chỉ mục cho field.
- Giá trị `null` thông thường không được lập chỉ mục như một giá trị keyword hoặc số.
- Field không xuất hiện trong document cũng không có giá trị được lập chỉ mục.

Vì vậy, `exists` thường trả về false khi field không có giá trị nào được lập chỉ mục. Field chứa mảng rỗng, null hoặc chỉ gồm các phần tử null có thể được xem là không tồn tại ở góc độ truy vấn.

Một số kiểu field hỗ trợ tùy chọn `null_value` để thay thế giá trị null bằng một giá trị cụ thể trong lúc lập chỉ mục. Cần chọn giá trị thay thế không gây nhầm lẫn với dữ liệu thật. `_source` vẫn giữ giá trị null ban đầu; `null_value` chỉ ảnh hưởng biểu diễn được lập chỉ mục.

Ví dụ mapping keyword:

~~~json
{
  "mappings": {
    "properties": {
      "status": {
        "type": "keyword",
        "null_value": "unknown"
      }
    }
  }
}
~~~

Với cấu hình này, document có `status: null` có thể được tìm qua giá trị `unknown` trong index. Không nên dùng `null_value` nếu nghiệp vụ cần phân biệt rõ null, chuỗi rỗng, field bị thiếu và một giá trị thực.

## 11. Multi-fields không phải là mảng

Một khái niệm dễ nhầm với field nhiều giá trị là **multi-fields**. Multi-fields cho phép lập chỉ mục cùng một thuộc tính dưới nhiều cách mapping khác nhau. Ví dụ tên sản phẩm vừa cần full-text search vừa cần so khớp chính xác:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Document vẫn có một giá trị `name`:

~~~json
{
  "name": "Wireless Headphones"
}
~~~

Nhưng Elasticsearch lập chỉ mục giá trị đó ở cả `name` kiểu text và `name.keyword` kiểu keyword.

So sánh:

- **Multi-valued field:** một field có nhiều giá trị, ví dụ `tags: ["audio", "wireless"]`.
- **Multi-fields:** một giá trị được lập chỉ mục theo nhiều mapping, ví dụ `name` và `name.keyword`.
- **Nested array:** một field chứa nhiều object mà cần giữ quan hệ giữa các thuộc tính của từng object.

Ba khái niệm này giải quyết ba nhu cầu khác nhau và có thể được kết hợp khi thiết kế mapping.

## 12. Lưu ý về kích thước và giới hạn dữ liệu

Mảng quá lớn có thể làm tăng số lượng term, dung lượng index, chi phí lập chỉ mục và thời gian truy vấn. Một document có hàng chục nghìn hoặc hàng trăm nghìn giá trị trong cùng field cần được xem xét kỹ về mô hình dữ liệu.

Với nested, mỗi phần tử tạo thêm một nested document nội bộ. Một document cha chứa quá nhiều nested object có thể làm tăng đáng kể tài nguyên và chạm giới hạn cấu hình nested objects của Elasticsearch. Hãy kiểm tra giới hạn cluster và kích thước dữ liệu thực tế thay vì coi collection Java có thể mở rộng vô hạn.

Một số nguyên tắc thiết kế:

- Không lưu một danh sách không giới hạn vào một document nếu dữ liệu có thể tách thành các document độc lập.
- Chỉ dùng nested khi cần giữ quan hệ giữa field của cùng phần tử.
- Dùng keyword cho nhãn, mã và giá trị phân loại; dùng text cho nội dung cần phân tích.
- Xác định rõ ý nghĩa của mảng rỗng, null và field bị thiếu.
- Đặt giới hạn đầu vào để tránh document quá lớn.
- Kiểm tra mapping và query bằng dữ liệu có số lượng phần tử gần với thực tế.
- Nếu thứ tự phần tử có ý nghĩa, lưu rõ vị trí hoặc thứ tự như một field số thay vì dựa vào thứ tự trong inverted index.

## 13. Áp dụng trong ứng dụng Spring Data Elasticsearch

Khi thiết kế entity, hãy bắt đầu từ câu hỏi ứng dụng sẽ truy vấn dữ liệu như thế nào:

1. Nếu chỉ cần kiểm tra một giá trị có nằm trong danh sách hay không, dùng mảng scalar với mapping `keyword`, `text` hoặc kiểu số phù hợp.
2. Nếu cần lọc theo một trong nhiều số hoặc ngày, dùng field số/ngày có nhiều giá trị và truy vấn range.
3. Nếu mỗi phần tử có nhiều thuộc tính cần khớp đồng thời, biểu diễn bằng collection object và mapping nested.
4. Nếu một thuộc tính cần cả tìm kiếm toàn văn và so khớp chính xác, dùng multi-fields.
5. Nếu cần tính thống kê, xác định rõ aggregation tính trên từng giá trị hay trên từng document.

Spring Data Elasticsearch giúp chuyển đổi giữa model Java và document JSON. Tuy nhiên, mapping Elasticsearch vẫn quyết định cách các giá trị được lập chỉ mục và truy vấn. Vì thế, việc khai báo `List`, `Set` hoặc array trong Java chưa đủ để quyết định hành vi tìm kiếm; cần chọn đúng `FieldType`, mapping `object` hay `nested`, và query tương ứng.

Một thiết kế tốt làm rõ ba điều: kiểu dữ liệu của từng phần tử, quan hệ giữa các phần tử và các phép truy vấn mà ứng dụng cần thực hiện. Khi những điều này được xác định trước, việc ánh xạ mảng và collection từ Java sang Elasticsearch sẽ nhất quán và dễ bảo trì hơn.
