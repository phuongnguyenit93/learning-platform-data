# Completion suggester và dữ liệu đầu vào gợi ý

Completion suggester là cơ chế gợi ý hoàn thành từ hoặc cụm từ khi người dùng đang nhập. Ví dụ, khi người dùng gõ "mech", ứng dụng có thể gợi ý "Mechanical Keyboard", "Mechanical Switch" hoặc tên sản phẩm phù hợp khác trước khi họ gửi toàn bộ truy vấn.

Spring Data Elasticsearch hỗ trợ completion field thông qua annotation `@CompletionField`, lớp `Completion` để mô tả dữ liệu đầu vào và `NativeQuery` để gửi suggester trong search request. Kết quả được trả về trong metadata suggest của `SearchHits`, tách biệt với danh sách document hits thông thường.

Để triển khai tốt chức năng này, cần thiết kế dữ liệu gợi ý ngay từ lúc index. Một completion field có thể chứa nhiều input, trọng số và context. Các dữ liệu này quyết định nội dung nào được gợi ý, cách xếp hạng và phạm vi mà người dùng nhìn thấy.

## 1. Completion suggester giải quyết bài toán gì?

Completion suggester phục vụ autocomplete hoặc search-as-you-type. Người dùng nhập từng phần của một cụm từ và hệ thống trả về các cụm từ hoàn chỉnh bắt đầu bằng phần đã nhập.

| Input đã nhập | Các gợi ý có thể trả về |
| --- | --- |
| mech | Mechanical Keyboard, Mechanical Switch |
| key | Keyboard, Keycap Set, Keychron K8 |
| iph | iPhone 17, iPhone 17 Pro |
| wire | Wireless Mouse, Wireless Headset |

Completion suggester được tối ưu cho độ trễ thấp. Elasticsearch xây dựng cấu trúc tra cứu chuyên dụng từ dữ liệu completion khi index và giữ cấu trúc đó trong bộ nhớ. Cách làm này giúp truy vấn prefix nhanh, đổi lại quá trình xây dựng index và lượng heap sử dụng có chi phí đáng kể.

Completion suggester phù hợp với gợi ý điều hướng đến một giá trị đã biết như tên sản phẩm, thương hiệu, địa điểm, danh mục hoặc tên bài viết.

### 1.1. Phân biệt completion, term và phrase suggester

Elasticsearch có nhiều loại suggester nhưng chúng phục vụ các mục tiêu khác nhau:

| Loại | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Completion suggester | Hoàn thành prefix khi người dùng đang gõ | key → Keyboard |
| Term suggester | Đề xuất từ gần giống để sửa lỗi chính tả | keybord → keyboard |
| Phrase suggester | Đề xuất cách viết lại cả cụm từ dựa trên ngữ cảnh từ | noble prize → nobel prize |

Completion suggester không phải công cụ sửa chính tả tổng quát. Nó tập trung vào prefix và có thể bật fuzzy để chịu được một số lỗi gõ.

Nếu cần tìm chuỗi con ở giữa từ, tìm kiếm theo nội dung hoặc truy vấn nhiều điều kiện, hãy cân nhắc search_as_you_type, edge n-gram, match query hoặc các query tìm kiếm thông thường. Completion suggester chủ yếu là một danh sách gợi ý đã được chuẩn bị trước.

## 2. Mapping field kiểu completion

Elasticsearch yêu cầu field dùng cho completion suggester có mapping type completion. Không thể dùng một field text thông thường rồi gửi completion query vào field đó.

Mapping JSON tối thiểu:

~~~json
{
  "mappings": {
    "properties": {
      "suggest": {
        "type": "completion"
      }
    }
  }
}
~~~

Spring Data Elasticsearch cung cấp annotation `@CompletionField` để khai báo mapping:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions")
public class ProductSuggestionDocument {

    @Id
    private String id;

    @CompletionField
    private Completion suggest;

    // Các field nghiệp vụ khác, constructors, getters và setters
}
~~~

`@CompletionField` làm cho field suggest được tạo với kiểu completion trong mapping. Lớp `Completion` của Spring Data biểu diễn các giá trị input, weight và contexts được gửi đến Elasticsearch.

### 2.1. Các thuộc tính của CompletionField

`@CompletionField` hỗ trợ các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Giá trị mặc định |
| --- | --- | --- |
| analyzer | Analyzer dùng khi index input | simple |
| searchAnalyzer | Analyzer dùng khi phân tích prefix truy vấn | simple |
| preserveSeparators | Giữ dấu phân cách giữa các token | true |
| preservePositionIncrements | Giữ khoảng cách vị trí token, hữu ích với stop words | true |
| maxInputLength | Giới hạn độ dài mỗi input khi index | 50 |
| contexts | Khai báo category hoặc geo context | Không có |

Ví dụ cấu hình rõ ràng:

~~~java
@CompletionField(
    analyzer = "simple",
    searchAnalyzer = "simple",
    preserveSeparators = true,
    preservePositionIncrements = true,
    maxInputLength = 80
)
private Completion suggest;
~~~

`maxInputLength` giới hạn mỗi chuỗi input ở thời điểm index để tránh một input quá dài làm phình cấu trúc completion. Giá trị mặc định là 50 code point theo UTF-16. Nếu ứng dụng gợi ý tên sản phẩm hoặc địa điểm dài, hãy đặt giới hạn dựa trên dữ liệu thực tế.

### 2.2. preserveSeparators

Khi `preserveSeparators` là true, dấu phân cách giữa các từ được giữ lại trong cách phân tích input. Điều này ảnh hưởng cách prefix được khớp với cụm từ nhiều từ.

Ví dụ input Foo Fighters:

- Với separator được giữ, prefix cần phù hợp với cấu trúc từ đã index.
- Nếu tắt separator, prefix như foof có thể khớp cụm Foo Fighters.

Không nên tắt thuộc tính này chỉ để giải quyết một trường hợp đặc biệt. Có thể index thêm một input thay thế như FooFighters hoặc alias chuẩn hóa nếu muốn hỗ trợ một cách gõ khác.

### 2.3. preservePositionIncrements

Thuộc tính này liên quan đến khoảng cách vị trí token khi analyzer loại bỏ stop words. Nếu tắt, một số prefix có thể khớp từ sau stop word.

Ví dụ tên ban nhạc The Beatles: ứng dụng có thể muốn prefix b gợi ý The Beatles. Có thể cấu hình analyzer và position increments phù hợp hoặc bổ sung input Beatles như một alias. Cách bổ sung input tường minh thường dễ kiểm soát hơn nếu danh sách dữ liệu không quá lớn.

## 3. Completion input, weight và contexts

Một completion value thường có ba thành phần:

~~~json
{
  "input": ["Mechanical Keyboard", "Keyboard", "KB-1042"],
  "weight": 120,
  "contexts": {
    "category": ["keyboards", "accessories"]
  }
}
~~~

| Thành phần | Vai trò |
| --- | --- |
| input | Các chuỗi mà người dùng có thể nhập prefix để tìm thấy gợi ý |
| weight | Trọng số dùng để xếp hạng gợi ý |
| contexts | Nhãn ngữ cảnh để lọc hoặc tăng điểm gợi ý |

input là bắt buộc. Nó có thể là một chuỗi hoặc mảng chuỗi. weight là số nguyên dương tùy chọn; giá trị lớn hơn có thể giúp gợi ý được xếp cao hơn. contexts chỉ cần khi field được khai báo context mapping.

Elasticsearch cũng hỗ trợ nhiều completion entry cho cùng document, mỗi entry có input và weight riêng. Lớp Spring Data Completion biểu diễn một nhóm input với một weight và contexts chung. Nếu từng alias cần trọng số khác nhau, có thể tách thành document gợi ý riêng hoặc dùng API client cấp thấp để gửi cấu trúc entry phù hợp.

### 3.1. Dùng Completion trong entity

Lớp Completion của Spring Data có constructor nhận mảng hoặc danh sách input. Weight và contexts được gán qua setter:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.suggest.Completion;

Completion completion = new Completion(List.of(
    "Mechanical Keyboard",
    "Keyboard",
    "KB-1042"
));

completion.setWeight(120);
completion.setContexts(Map.of(
    "category", List.of("keyboards", "accessories")
));
~~~

Khi field không khai báo contexts, có thể bỏ qua setContexts. Nếu field đã khai báo context mapping, mỗi completion value phải có context tương ứng khi index, trừ khi mapping dùng path để lấy context từ field khác trong document.

### 3.2. Ví dụ entity hoàn chỉnh

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions")
public class ProductSuggestionDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String displayName;

    @CompletionField(maxInputLength = 80)
    private Completion suggest;

    public void prepareSuggestion() {
        Completion value = new Completion(List.of(
            displayName,
            sku
        ));
        value.setWeight(100);
        this.suggest = value;
    }

    // Constructors, getters và setters
}
~~~

Phương thức prepareSuggestion minh họa cách tạo completion input từ dữ liệu nghiệp vụ. Trong ứng dụng thực tế, hãy đặt việc chuẩn hóa và tạo alias trong service hoặc mapper chuyên trách để tránh entity tự chứa quá nhiều quy tắc nghiệp vụ.

Nếu có context mapping khai báo category, hãy gán context hoặc cấu hình path phù hợp trước khi lưu.

## 4. Thiết kế dữ liệu đầu vào gợi ý

Chất lượng autocomplete phụ thuộc nhiều vào dữ liệu được index hơn là số lượng tùy chọn của query. Một document sản phẩm có thể có tên hiển thị, tên chuẩn hóa, SKU, thương hiệu và alias. Không phải field nào cũng nên trở thành input.

| Dữ liệu nguồn | Có nên trở thành input? | Lý do |
| --- | --- | --- |
| Tên sản phẩm | Có | Đây thường là nội dung người dùng muốn chọn |
| Tên rút gọn phổ biến | Có | Hỗ trợ cách gọi quen thuộc |
| SKU hoặc mã sản phẩm | Có nếu người dùng hay tra mã | Hữu ích cho tìm kiếm định danh |
| Tên thương hiệu | Tùy trải nghiệm | Có thể tạo gợi ý thương hiệu riêng |
| Mô tả dài | Thường không | Dễ tạo quá nhiều input nhiễu |
| Nội dung HTML | Không | Không phải chuỗi gợi ý phù hợp |
| Từ khóa nội bộ | Chỉ khi có giá trị với người dùng | Tránh lộ dữ liệu nội bộ |

### 4.1. Chuẩn hóa input

Một pipeline chuẩn bị dữ liệu gợi ý có thể gồm:

1. Lấy tên hiển thị và alias được phép công khai.
2. Loại bỏ chuỗi rỗng hoặc chỉ có khoảng trắng.
3. Chuẩn hóa khoảng trắng và ký tự điều khiển.
4. Loại bỏ input trùng nhau sau chuẩn hóa.
5. Giới hạn độ dài input theo mapping.
6. Gắn weight dựa trên mức ưu tiên nghiệp vụ.
7. Gắn category hoặc geo context nếu field có context mapping.
8. Ghi completion value cùng document hoặc index gợi ý riêng.

Elasticsearch không chấp nhận một số ký tự điều khiển UTF-16 trong input, gồm null và các ký tự thông tin U+001F, U+001E. Nên làm sạch dữ liệu ở tầng ứng dụng trước khi index.

### 4.2. Index nhiều alias cho một document

Ví dụ một sản phẩm có các cách gọi:

~~~json
{
  "sku": "KB-1042",
  "displayName": "Mechanical Keyboard",
  "suggest": {
    "input": [
      "Mechanical Keyboard",
      "Keyboard",
      "Mechanical Keyboards",
      "KB-1042"
    ],
    "weight": 120
  }
}
~~~

Người dùng có thể tìm thấy cùng sản phẩm qua nhiều input. Completion option có thể tham chiếu về cùng document ID. Nếu nhiều document cùng có input giống nhau, kết quả có thể chứa các gợi ý trùng text; dùng skip_duplicates hoặc thiết kế index input để hạn chế trùng.

### 4.3. Chọn weight theo nghiệp vụ

Weight là số nguyên dương dùng để tăng/giảm độ ưu tiên gợi ý. Có thể tính weight từ:

- Mức độ phổ biến của sản phẩm hoặc cụm từ.
- Số lượt chọn gợi ý trong một khoảng thời gian.
- Trạng thái ưu tiên do biên tập viên thiết lập.
- Mức độ phù hợp theo loại dữ liệu.
- Chất lượng dữ liệu và trạng thái đang kinh doanh.

Ví dụ minh họa:

| Nhóm input | Weight gợi ý |
| --- | ---: |
| Tên sản phẩm nổi bật | 200 |
| Tên sản phẩm thông thường | 100 |
| Alias ít dùng | 30 |

Các con số chỉ là ví dụ. Nên chuẩn hóa weight để tránh một nhóm dữ liệu áp đảo mọi gợi ý. Có thể dùng log scale hoặc giới hạn trên nếu weight được tính từ lượt chọn rất lớn.

Weight không thay thế hoàn toàn prefix relevance. Completion suggester còn xét độ dài prefix khớp; các gợi ý chia sẻ prefix dài hơn có thể được xếp cao hơn.

## 5. Index dữ liệu gợi ý qua Spring Data

Sau khi tạo entity có field completion, có thể lưu bằng ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductSuggestionIndexer {

    private final ElasticsearchOperations operations;

    public ProductSuggestionIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void index(ProductSuggestionDocument document) {
        document.prepareSuggestion();
        operations.save(document);
    }
}
~~~

Nếu index chưa tồn tại, cần tạo index với mapping có field completion trước khi ghi dữ liệu:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductSuggestionDocument.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

createWithMapping() sử dụng metadata entity để tạo mapping. Nếu ứng dụng đã quản lý index qua migration hoặc index template, hãy bảo đảm mapping thực tế của field suggest là completion trước khi ghi.

### 5.1. Completion gần real-time

Gợi ý mới xuất hiện sau khi Elasticsearch refresh shard. Điều này có nghĩa:

- Một document vừa index có thể chưa xuất hiện ngay trong autocomplete.
- Sau refresh, completion entry mới có thể được truy vấn.
- Khi document bị xóa và thay đổi đã được refresh, gợi ý tương ứng không còn được trả về.

Không nên bật refresh ngay sau từng lần ghi nếu ứng dụng có lưu lượng lớn. Dùng refresh policy phù hợp với luồng import hoặc đồng bộ dữ liệu.

### 5.2. Cập nhật và xóa gợi ý

Completion input gắn với document được index. Khi tên hiển thị, alias, trạng thái hoặc weight thay đổi, cần cập nhật completion value tương ứng.

Ví dụ:

- Sản phẩm đổi tên: thay input cũ bằng tên mới và alias hợp lệ.
- Sản phẩm ngừng kinh doanh: xóa document gợi ý hoặc bỏ input không còn phù hợp.
- Danh mục đổi: cập nhật context category.
- Địa điểm đổi tọa độ: cập nhật geo context.
- Trọng số phổ biến thay đổi: tính lại weight và reindex.

Nếu autocomplete có vòng đời riêng với dữ liệu nghiệp vụ, có thể dùng một index gợi ý chuyên biệt để cập nhật, xóa và phân quyền độc lập.

## 6. Completion suggester bằng Query DSL

Completion suggester được khai báo trong phần suggest của search request. Mỗi suggester có tên riêng, prefix cần hoàn thành và cấu hình completion field.

~~~http
POST product-suggestions/_search
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "mech",
      "completion": {
        "field": "suggest",
        "size": 10
      }
    }
  }
}
~~~

Ý nghĩa:

- product-autocomplete là tên của suggester, dùng để lấy đúng nhóm kết quả trong response.
- prefix là phần văn bản người dùng đã nhập.
- completion.field là field có mapping type completion.
- size là số gợi ý tối đa được trả về.

Nếu không chỉ định size, completion suggester mặc định trả tối đa 5 gợi ý.

### 6.1. Bỏ gợi ý trùng nhau

Một input có thể xuất hiện trong nhiều document. Nếu giao diện chỉ muốn mỗi chuỗi gợi ý xuất hiện một lần, bật skip_duplicates:

~~~json
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "key",
      "completion": {
        "field": "suggest",
        "size": 10,
        "skip_duplicates": true
      }
    }
  }
}
~~~

skip_duplicates lọc các gợi ý trùng text. Thuộc tính này có thể làm truy vấn chậm hơn vì Elasticsearch phải duyệt thêm candidate để tìm đủ số gợi ý duy nhất.

Nếu nhiều sản phẩm có cùng tên, cần quyết định rõ giao diện muốn:

- Chỉ hiển thị một chuỗi tên và chọn document phù hợp nhất.
- Hiển thị nhiều kết quả cùng tên nhưng có thông tin phân biệt.
- Gợi ý theo tên rồi chuyển sang truy vấn tìm kiếm đầy đủ khi người dùng chọn.

Không phải trường hợp nào cũng nên bật skip_duplicates.

## 7. Dùng NativeQuery trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch hiện đại, NativeQuery nhận Suggester từ Elasticsearch Java API Client. Đây là cách tích hợp completion suggester vào luồng ElasticsearchOperations.search(...).

~~~java
import co.elastic.clients.elasticsearch.core.search.Suggester;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Suggester suggester = Suggester.of(s -> s
    .suggesters("product-autocomplete", field -> field
        .prefix("mech")
        .completion(completion -> completion
            .field("suggest")
            .size(10)
            .skipDuplicates(true)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();

SearchHits<ProductSuggestionDocument> results =
    operations.search(query, ProductSuggestionDocument.class);
~~~

Ở đây:

- Suggester là kiểu co.elastic.clients.elasticsearch.core.search.Suggester.
- NativeQuery.withSuggester(...) gắn phần suggest vào search request.
- ElasticsearchOperations.search(...) thực thi request và chuyển response về abstraction của Spring Data.

Các kiểu builder thuộc Elasticsearch Java API Client. Hãy dùng phiên bản client được dependency management của Spring Boot/Spring Data cung cấp, tránh trộn class từ High Level REST Client cũ với Java API Client hiện đại.

### 7.1. Bật fuzzy completion

Completion suggester hỗ trợ fuzzy để người dùng vẫn nhận gợi ý khi gõ sai một vài ký tự:

~~~json
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "keybord",
      "completion": {
        "field": "suggest",
        "size": 10,
        "fuzzy": {
          "fuzziness": "AUTO",
          "min_length": 3,
          "prefix_length": 1,
          "transpositions": true
        }
      }
    }
  }
}
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| fuzziness | Khoảng cách chỉnh sửa được chấp nhận; mặc định thường là AUTO |
| min_length | Độ dài prefix tối thiểu trước khi bật fuzzy |
| prefix_length | Số ký tự đầu phải khớp chính xác |
| transpositions | Có coi việc đổi chỗ hai ký tự liền nhau là một phép sửa hay không |
| unicode_aware | Đo khoảng cách theo Unicode code point thay vì byte |

Fuzzy giúp chịu lỗi gõ nhưng làm tăng số candidate cần kiểm tra. Không nên bật cho prefix quá ngắn vì có thể tạo nhiều gợi ý không liên quan. Hãy thử trên truy vấn thực tế và đo độ trễ.

### 7.2. Regex completion

Completion suggester cũng hỗ trợ regex để mô tả prefix phức tạp:

~~~json
{
  "suggest": {
    "product-autocomplete": {
      "regex": "mech.*",
      "completion": {
        "field": "suggest",
        "size": 10
      }
    }
  }
}
~~~

Regex có thể tiêu tốn CPU và bộ nhớ nếu biểu thức tạo automaton lớn. Không nhận regex tùy ý từ người dùng rồi gửi trực tiếp lên cluster. Nếu giao diện chỉ cần autocomplete thông thường, prefix query đơn giản hơn và dễ giới hạn hơn.

## 8. Đọc completion suggestion response

Completion suggester trả về một phần suggest riêng trong search response. Phần hits thông thường có thể rỗng trong khi suggestion options vẫn có dữ liệu.

~~~json
{
  "hits": {
    "total": {
      "value": 0,
      "relation": "eq"
    },
    "hits": []
  },
  "suggest": {
    "product-autocomplete": [
      {
        "text": "mech",
        "offset": 0,
        "length": 4,
        "options": [
          {
            "text": "Mechanical Keyboard",
            "_index": "product-suggestions",
            "_id": "KB-1042",
            "_score": 120,
            "_source": {
              "sku": "KB-1042",
              "displayName": "Mechanical Keyboard"
            }
          }
        ]
      }
    ]
  }
}
~~~

| Trường | Ý nghĩa |
| --- | --- |
| text | Prefix hoặc đoạn văn bản được dùng để tạo suggestion entry |
| offset, length | Vị trí và độ dài của đoạn input trong văn bản suggest |
| options[].text | Chuỗi gợi ý được trả về |
| options[]._id | ID document nguồn của gợi ý |
| options[]._index | Index chứa document nguồn |
| options[]._score | Điểm của completion option, chịu ảnh hưởng bởi weight và context boost |
| options[]._source | Nội dung document nguồn nếu source được bật |

Không nên giả định SearchHits.getTotalHits() là số lượng completion options. Gợi ý nằm trong SearchHits.getSuggest(), còn getSearchHits() chứa các document hits của phần query thông thường.

### 8.1. Lấy Suggest từ SearchHits

Spring Data cung cấp SearchHits.getSuggest():

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductSuggestionDocument> results =
    operations.search(query, ProductSuggestionDocument.class);

Suggest suggest = results.getSuggest();

if (suggest != null) {
    var productSuggestion =
        suggest.getSuggestion("product-autocomplete");
}
~~~

Suggest.getSuggestion(name) trả về kiểu suggestion tổng quát. Với completion suggester, có thể ép kiểu sang CompletionSuggestion<T> sau khi xác nhận đúng loại:

~~~java
import org.springframework.data.elasticsearch.core.suggest.response.CompletionSuggestion;

if (productSuggestion instanceof CompletionSuggestion<?> completionSuggestion) {
    for (CompletionSuggestion.Entry<?> entry : completionSuggestion.getEntries()) {
        for (CompletionSuggestion.Entry.Option<?> option : entry.getOptions()) {
            String text = option.getText();
            Double score = option.getScore();
        }
    }
}
~~~

Mỗi entry có danh sách options. option.getText() là chuỗi được gợi ý; option.getScore() là điểm trả về cho option.

### 8.2. Lấy document nguồn của suggestion

Completion option có thể chứa SearchHit<T> đại diện cho document nguồn:

~~~java
for (CompletionSuggestion.Entry<?> entry : completionSuggestion.getEntries()) {
    for (CompletionSuggestion.Entry.Option<?> option : entry.getOptions()) {
        String suggestedText = option.getText();

        var sourceHit = option.getSearchHit();
        if (sourceHit != null) {
            Object source = sourceHit.getContent();
            String documentId = sourceHit.getId();
        }
    }
}
~~~

Kiểu content cụ thể phụ thuộc generic type đã dùng khi gọi operations.search(...) và cách Spring Data ánh xạ source. Có thể đọc getSearchHit() để lấy entity và ID nguồn nếu response chứa source.

source được bật mặc định trong Elasticsearch. Nếu source bị tắt hoặc response không chứa source, option vẫn có thể cung cấp text/ID nhưng không có entity content đầy đủ.

### 8.3. Giảm kích thước source

Completion response có thể trả toàn bộ _source của document cho mỗi option. Nếu document lớn, việc fetch và truyền source có thể làm tăng chi phí.

Khi dùng _search, có thể giới hạn source:

~~~json
{
  "_source": ["sku", "displayName"],
  "suggest": {
    "product-autocomplete": {
      "prefix": "mech",
      "completion": {
        "field": "suggest",
        "size": 5
      }
    }
  }
}
~~~

Chỉ lấy các field mà giao diện cần hiển thị. Endpoint _suggest riêng không hỗ trợ source filtering theo cách giống _search; dùng suggest trong search request khi cần kiểm soát _source.

## 9. Context suggester: lọc và tăng ưu tiên theo ngữ cảnh

Completion suggester mặc định xét mọi document trong index. Nếu ứng dụng cần gợi ý theo danh mục, loại địa điểm, tenant hoặc vị trí địa lý, có thể khai báo context mapping.

Elasticsearch hỗ trợ hai loại context:

- category: gắn một hoặc nhiều nhãn danh mục cho suggestion.
- geo: gắn một hoặc nhiều vị trí địa lý cho suggestion.

Mỗi context mapping có tên riêng. Một completion field có thể khai báo tối đa 10 context mappings.

Khi field có context mapping, phải cung cấp context phù hợp lúc index và lúc query. Nếu không, request có thể bị từ chối hoặc không tạo ra gợi ý như mong muốn.

### 9.1. Category context

Mapping JSON:

~~~json
{
  "properties": {
    "category": {
      "type": "keyword"
    },
    "suggest": {
      "type": "completion",
      "contexts": [
        {
          "name": "category",
          "type": "category",
          "path": "category"
        }
      ]
    }
  }
}
~~~

path chỉ ra field khác trong document dùng làm context. Khi index document, Elasticsearch lấy giá trị category từ field đó.

Spring Data annotation:

~~~java
import org.springframework.data.elasticsearch.annotations.CompletionContext;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "place-suggestions")
public class PlaceSuggestionDocument {

    @Field(type = FieldType.Keyword)
    private String category;

    @CompletionField(
        contexts = {
            @CompletionContext(
                name = "category",
                type = CompletionContext.ContextMappingType.CATEGORY,
                path = "category"
            )
        }
    )
    private Completion suggest;

    // Constructors, getters và setters
}
~~~

Nếu không khai báo path, ứng dụng phải gán context trực tiếp vào Completion:

~~~java
Completion completion = new Completion(List.of(
    "Coffee Shop",
    "Cafe"
));

completion.setContexts(Map.of(
    "category", List.of("cafe", "food")
));
~~~

### 9.2. Query theo category

~~~json
{
  "suggest": {
    "place-suggestion": {
      "prefix": "cof",
      "completion": {
        "field": "suggest",
        "size": 10,
        "contexts": {
          "category": ["cafe", "restaurants"]
        }
      }
    }
  }
}
~~~

Nhiều category trong cùng context được kết hợp theo OR: suggestion khớp nếu có ít nhất một category được cung cấp.

### 9.3. Boost theo category

Context có thể vừa lọc vừa tăng điểm:

~~~json
{
  "suggest": {
    "place-suggestion": {
      "prefix": "cof",
      "completion": {
        "field": "suggest",
        "size": 10,
        "contexts": {
          "category": [
            { "context": "cafe" },
            { "context": "restaurants", "boost": 2 }
          ]
        }
      }
    }
  }
}
~~~

Trong ví dụ, suggestion thuộc restaurants được nhân boost 2. Điểm cuối cùng chịu ảnh hưởng của weight và context boost. Nếu một suggestion khớp nhiều context, Elasticsearch dùng điểm cao nhất trong các context khớp.

### 9.4. Geo context

Geo context cho phép gắn một hoặc nhiều vị trí địa lý vào suggestion và lọc/tăng điểm theo khu vực người dùng quan tâm.

Mapping JSON:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    },
    "suggest": {
      "type": "completion",
      "contexts": [
        {
          "name": "location",
          "type": "geo",
          "path": "location",
          "precision": "5km"
        }
      ]
    }
  }
}
~~~

Query theo tọa độ:

~~~json
{
  "suggest": {
    "place-suggestion": {
      "prefix": "cof",
      "completion": {
        "field": "suggest",
        "size": 10,
        "contexts": {
          "location": {
            "lat": 10.7769,
            "lon": 106.7009
          }
        }
      }
    }
  }
}
~~~

Geo context được mã hóa qua geohash với precision đã cấu hình. Đây là lọc theo vùng geohash, không phải phép tính khoảng cách chính xác như geo distance query. Một địa điểm rất gần tọa độ truy vấn nhưng nằm ngoài tile được mã hóa vẫn có thể không khớp. Chọn precision và neighbors dựa trên trải nghiệm địa lý thực tế.

## 10. Analyzer và cách prefix được phân tích

Completion field có index analyzer và search analyzer. Hai analyzer cần được thiết kế nhất quán để input được index và prefix được query theo cùng quy tắc tokenization.

Analyzer mặc định của completion field là simple. Nó chuyển chữ về lowercase và tách token theo ký tự không phải chữ cái. Nếu dữ liệu có mã SKU, dấu tiếng Việt, ký tự đặc biệt hoặc quy tắc ngôn ngữ riêng, cần thử nghiệm analyzer trên dữ liệu thật.

Với tiếng Việt, người dùng có thể nhập có dấu hoặc không dấu. Analyzer mặc định không tự bảo đảm mọi cách gõ sẽ tương đương.

Có thể chọn:

- Dùng custom analyzer có lowercase và asciifolding nếu muốn chuẩn hóa dấu.
- Index thêm alias không dấu nếu cần kiểm soát rõ.
- Chuẩn hóa cả input lẫn query theo cùng một quy tắc ở ứng dụng.

Không nên chỉ thay analyzer phía query mà không kiểm tra cách completion input đã được index. Nếu thay đổi analyzer hoặc mapping completion, thường cần tạo lại index và reindex dữ liệu để cấu trúc completion được xây dựng theo analyzer mới.

### 10.1. Tách token và dấu phân cách

Với cụm nhiều từ, preserveSeparators và preservePositionIncrements ảnh hưởng cách prefix được khớp. Hãy tạo bộ test gồm:

- Prefix từ ký tự đầu của cụm.
- Prefix từ từ thứ hai.
- Chuỗi có dấu gạch nối.
- Chuỗi có khoảng trắng liên tiếp.
- Tên chứa stop word.
- Tên có dấu và alias không dấu.

Nếu muốn hỗ trợ prefix bắt đầu từ giữa cụm hoặc từ bất kỳ token nào, hãy cân nhắc index thêm input riêng thay vì thay đổi separator behavior cho toàn bộ dữ liệu.

## 11. Completion suggester không thay thế truy vấn tìm kiếm

Autocomplete thường là bước điều hướng:

1. Người dùng gõ một phần từ khóa.
2. Completion suggester trả danh sách gợi ý.
3. Người dùng chọn một gợi ý.
4. Ứng dụng dùng ID hoặc text đã chọn để mở document hoặc thực hiện search query đầy đủ.

Completion suggester không phải lúc nào cũng trả đủ thông tin để hiển thị toàn bộ kết quả tìm kiếm. Nó có thể trả một số option với source đã lọc. Nếu người dùng nhấn Enter mà không chọn suggestion, ứng dụng vẫn nên chạy truy vấn tìm kiếm thông thường.

~~~text
Người dùng nhập "mech"
          |
          v
Completion suggester
          |
          v
Mechanical Keyboard
Mechanical Switch
          |
          v
Người dùng chọn Mechanical Keyboard
          |
          v
Mở sản phẩm theo document ID
hoặc chạy query tìm kiếm đầy đủ
~~~

Nếu cần hiển thị danh sách document theo nhiều điều kiện như giá, tồn kho, quyền truy cập hoặc relevance, hãy dùng query thông thường. Context suggester chỉ phù hợp với những context đã được index trong completion field.

## 12. Lấy kết quả và xây dựng DTO cho giao diện

Không nên trả nguyên cấu trúc nội bộ của Spring Data hoặc Elasticsearch client trực tiếp ra API. Có thể chuyển suggestion options thành DTO nhỏ:

~~~java
public record SuggestionItem(
    String text,
    String documentId,
    Double score
) {}
~~~

Mapper minh họa:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.suggest.response.CompletionSuggestion;

public List<SuggestionItem> toSuggestionItems(
        CompletionSuggestion<?> completionSuggestion) {

    List<SuggestionItem> items = new ArrayList<>();

    for (CompletionSuggestion.Entry<?> entry
            : completionSuggestion.getEntries()) {
        for (CompletionSuggestion.Entry.Option<?> option
                : entry.getOptions()) {

            SearchHit<?> hit = option.getSearchHit();
            String id = hit != null ? hit.getId() : null;

            items.add(new SuggestionItem(
                option.getText(),
                id,
                option.getScore()
            ));
        }
    }

    return items;
}
~~~

Nếu cần dữ liệu sản phẩm để hiển thị, có thể đọc content từ option.getSearchHit() khi có source. Nếu source không được trả về, chỉ dùng text và ID rồi tải thông tin cần thiết bằng một truy vấn khác.

## 13. Hiệu năng và thiết kế index

Completion suggester được tối ưu cho tốc độ tra cứu nhưng có chi phí bộ nhớ. Các completion structures được giữ trong heap, nên tổng số input, độ dài chuỗi, context mapping và số lượng shard ảnh hưởng tới footprint.

Một số nguyên tắc:

- Chỉ index input có ích cho trải nghiệm autocomplete.
- Không đưa toàn bộ mô tả dài vào completion field.
- Giới hạn maxInputLength.
- Khử trùng lặp input trước khi index.
- Giữ weight trong phạm vi hợp lý.
- Chỉ thêm context mapping khi có nhu cầu lọc hoặc boost thực sự.
- Theo dõi completion field statistics và heap usage.
- Đo latency với số lượng input gần production.

Elasticsearch khuyến nghị index completion trên một shard để có độ trễ tốt trong nhiều trường hợp, vì request qua nhiều shard cần thêm giai đoạn lấy document liên quan. Tuy nhiên, nếu một shard có footprint quá lớn và gây áp lực heap, nên chia nhỏ index thay vì cố giữ một shard chỉ để tối ưu completion.

### 13.1. Tách index gợi ý

Một kiến trúc có thể dùng:

| Index | Nội dung |
| --- | --- |
| products | Document sản phẩm đầy đủ, phục vụ truy vấn và lọc |
| product-suggestions | Input, weight, category context và thông tin tối thiểu để autocomplete |

Lợi ích:

- Completion index nhỏ hơn và chỉ chứa dữ liệu cần thiết.
- Có thể điều chỉnh shard và refresh policy riêng.
- Dễ loại bỏ sản phẩm không còn được phép gợi ý.
- Có thể phân quyền đọc suggestion index riêng.

Đổi lại, ứng dụng phải duy trì đồng bộ giữa document nghiệp vụ và document gợi ý. Hãy dùng event, outbox hoặc quy trình đồng bộ có thể retry để tránh gợi ý trỏ tới document đã bị xóa.

### 13.2. Refresh và tải ghi

Ghi completion thường xuyên có thể làm tăng chi phí refresh và cập nhật cấu trúc tra cứu. Nếu nhập dữ liệu theo batch, hãy cân nhắc bulk indexing và refresh sau batch thay vì refresh từng document.

Đối với autocomplete có độ trễ cập nhật vài giây chấp nhận được, near-real-time refresh thường phù hợp. Nếu yêu cầu gợi ý xuất hiện ngay sau thao tác ghi, hãy đánh giá kỹ chi phí của refresh policy.

## 14. Bảo mật và chất lượng dữ liệu gợi ý

Autocomplete có thể vô tình tiết lộ dữ liệu nếu index input chứa tên nội bộ, tài liệu chưa công bố hoặc giá trị người dùng không được phép xem.

Một số nguyên tắc:

- Chỉ index dữ liệu được phép hiển thị cho người dùng hiện tại.
- Không đưa secret, token, email riêng tư hoặc thông tin nhạy cảm vào input.
- Dùng context hoặc index riêng để phân vùng tenant nếu yêu cầu bảo mật cho phép.
- Không xem category context là cơ chế phân quyền hoàn chỉnh nếu người dùng có thể gửi query tùy ý.
- Validate prefix length và giới hạn số lượng kết quả.
- Không nhận regex tùy ý từ client.
- Giới hạn fuzzy để tránh tăng chi phí cho prefix quá ngắn.
- Kiểm soát source fields được trả về trong suggestion options.

Nếu dữ liệu gợi ý phụ thuộc quyền người dùng, cần xác thực và áp dụng điều kiện truy cập tại tầng ứng dụng. Một context filter chỉ có tác dụng trong query suggester; nó không thay thế authorization ở API.

## 15. Kiểm thử completion suggester

Nên kiểm tra cả mapping, dữ liệu index và kết quả query.

### 15.1. Kiểm tra mapping

~~~http
GET /product-suggestions/_mapping
~~~

Xác nhận:

- Field suggest có type completion.
- Analyzer và search analyzer đúng như thiết kế.
- max_input_length phù hợp.
- Context mappings được khai báo chính xác nếu sử dụng.
- Path của context trỏ tới field tồn tại và có kiểu dữ liệu phù hợp.

### 15.2. Kiểm tra dữ liệu

~~~http
GET /product-suggestions/_doc/KB-1042
~~~

Kiểm tra completion input, weight và contexts được lưu đúng. Nếu dùng path, kiểm tra field nguồn của context cũng có giá trị.

### 15.3. Kiểm tra query

~~~http
POST product-suggestions/_search
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "mech",
      "completion": {
        "field": "suggest",
        "size": 10,
        "skip_duplicates": true
      }
    }
  }
}
~~~

Thử các trường hợp:

1. Prefix khớp chính xác phần đầu input.
2. Prefix không có kết quả.
3. Prefix có chữ hoa/chữ thường khác nhau.
4. Prefix chứa dấu hoặc ký tự đặc biệt.
5. Prefix nhiều từ.
6. Prefix có lỗi gõ khi bật fuzzy.
7. Nhiều document có cùng input.
8. Context lọc ra đúng nhóm.
9. Document vừa cập nhật sau refresh.
10. Document đã xóa không còn xuất hiện sau refresh.

### 15.4. Đánh giá chất lượng gợi ý

Không chỉ đo latency. Cần đánh giá:

- Tỷ lệ gợi ý đúng trong top 5 hoặc top 10.
- Tỷ lệ gợi ý không liên quan.
- Tỷ lệ người dùng chọn gợi ý.
- Số lượng gợi ý trùng nhau.
- Mức độ bao phủ alias và mã định danh.
- Tác động của weight và context boost.

Log prefix và lựa chọn của người dùng theo chính sách dữ liệu phù hợp có thể giúp cải thiện bộ input và weight theo thời gian.

## 16. Lỗi thường gặp

**Dùng field text thay cho completion.** Completion query yêu cầu mapping type completion. Kiểm tra mapping trước khi query.

**Chỉ khai báo @CompletionField nhưng không tạo lại index cũ.** Annotation không tự sửa mapping index đã tồn tại. Tạo index mới hoặc migration phù hợp rồi reindex dữ liệu.

**Không gán input.** Completion value cần ít nhất một input hợp lệ. Kiểm tra mapper tạo dữ liệu trước khi gọi save.

**Index input quá dài.** maxInputLength có thể cắt input ở thời điểm index. Đặt giới hạn phù hợp và kiểm tra tên dài.

**Dùng completion để sửa lỗi chính tả tổng quát.** Completion tập trung prefix. Dùng term hoặc phrase suggester cho spell correction chuyên sâu.

**Mong prefix khớp ở giữa từ.** Completion không phải substring search. Index thêm alias phù hợp hoặc dùng search_as_you_type/edge n-gram cho bài toán infix.

**Bật fuzzy cho prefix quá ngắn.** Có thể sinh nhiều candidate nhiễu và tăng độ trễ. Đặt min_length và prefix_length phù hợp.

**Bật skip_duplicates mà không đo hiệu năng.** Elasticsearch phải duyệt thêm candidate để tìm đủ số gợi ý duy nhất. Chỉ bật khi trải nghiệm cần loại trùng.

**Dùng weight bằng 0 hoặc số âm.** Weight phải là số nguyên dương. Kiểm tra dữ liệu trước khi index.

**Khai báo context mapping nhưng không gửi context.** Field có context yêu cầu context ở cả lúc index và query. Kiểm tra path hoặc gán contexts trong Completion.

**Nhầm geo context với khoảng cách chính xác.** Geo context dùng geohash tiles. Dùng geo distance query nếu nghiệp vụ cần lọc khoảng cách chính xác.

**Đọc SearchHits.getSearchHits() để lấy completion options.** Completion options nằm trong SearchHits.getSuggest(). Hits thông thường có thể rỗng.

**Không giới hạn source của suggestion.** Source lớn làm tăng chi phí fetch và network. Chỉ trả các field cần hiển thị.

**Không đồng bộ index gợi ý khi document nghiệp vụ thay đổi.** Có thể xuất hiện gợi ý cũ hoặc ID không còn tồn tại. Dùng event/outbox hoặc quy trình đồng bộ có thể retry.

## 17. Ví dụ hoàn chỉnh: autocomplete sản phẩm

Giả sử ứng dụng cần gợi ý sản phẩm theo tên và SKU. Input được chuẩn bị từ tên hiển thị, tên rút gọn và mã sản phẩm; sản phẩm phổ biến có weight cao hơn.

Entity:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions")
public class ProductSuggestionDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String displayName;

    @Field(type = FieldType.Keyword)
    private String category;

    @CompletionField(maxInputLength = 80)
    private Completion suggest;

    public void buildSuggestion(int popularityWeight) {
        Completion completion = new Completion(List.of(
            displayName,
            sku
        ));
        completion.setWeight(Math.max(1, popularityWeight));
        this.suggest = completion;
    }

    // Constructors, getters và setters
}
~~~

Indexer:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSuggestionIndexer {

    private final ElasticsearchOperations operations;

    public ProductSuggestionIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void index(ProductSuggestionDocument document, int popularity) {
        document.buildSuggestion(popularity);
        operations.save(document);
    }
}
~~~

Service tìm gợi ý:

~~~java
import co.elastic.clients.elasticsearch.core.search.Suggester;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductAutocompleteService {

    private final ElasticsearchOperations operations;

    public ProductAutocompleteService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductSuggestionDocument> suggest(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }

        String normalizedPrefix = prefix.strip();

        Suggester suggester = Suggester.of(s -> s
            .suggesters("product-autocomplete", field -> field
                .prefix(normalizedPrefix)
                .completion(completion -> completion
                    .field("suggest")
                    .size(10)
                    .skipDuplicates(true)
                )
            )
        );

        NativeQuery query = NativeQuery.builder()
            .withSuggester(suggester)
            .build();

        return operations.search(
            query,
            ProductSuggestionDocument.class
        );
    }
}
~~~

Đọc options:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.CompletionSuggestion;

public List<String> getSuggestionTexts(
        SearchHits<ProductSuggestionDocument> results) {

    List<String> values = new ArrayList<>();

    if (results.getSuggest() == null) {
        return values;
    }

    var rawSuggestion =
        results.getSuggest().getSuggestion("product-autocomplete");

    if (rawSuggestion instanceof CompletionSuggestion<?> completion) {
        for (CompletionSuggestion.Entry<?> entry : completion.getEntries()) {
            for (CompletionSuggestion.Entry.Option<?> option : entry.getOptions()) {
                values.add(option.getText());
            }
        }
    }

    return values;
}
~~~

Ví dụ trên giữ phần index dữ liệu, xây dựng suggester và đọc suggestion options thành các chuỗi để giao diện hiển thị. Nếu giao diện cần ID hoặc chi tiết sản phẩm, đọc option.getSearchHit() khi có source hoặc dùng document ID để tải thông tin chi tiết.

## 18. Quy trình triển khai

Khi bổ sung autocomplete bằng Completion suggester:

1. Xác định loại input người dùng cần gợi ý: tên, alias, mã, thương hiệu hay địa điểm.
2. Tạo field có mapping type completion bằng @CompletionField.
3. Chọn analyzer, search analyzer, separator behavior và max input length.
4. Thiết kế pipeline chuẩn hóa, khử trùng lặp và tạo input.
5. Xác định cách tính weight và quy tắc cập nhật.
6. Nếu cần lọc theo danh mục hoặc vị trí, khai báo context mapping trước khi tạo index.
7. Index completion data bằng Spring Data hoặc bulk pipeline.
8. Dùng NativeQuery.withSuggester(...) để gửi prefix/fuzzy/context options.
9. Đọc kết quả qua SearchHits.getSuggest() và chuyển sang DTO.
10. Giới hạn source, số options và độ dài prefix.
11. Kiểm thử mapping, input, context, duplicate behavior và refresh.
12. Theo dõi heap, latency, completion index size và tỷ lệ người dùng chọn gợi ý.
13. Đồng bộ suggestion documents khi dữ liệu nghiệp vụ thay đổi hoặc bị xóa.

Completion suggester đem lại autocomplete nhanh khi dữ liệu input được chuẩn bị có chủ đích. Mapping xác định cách phân tích và cấu trúc tra cứu; input và weight quyết định nội dung cùng thứ tự gợi ý; context giới hạn hoặc tăng ưu tiên theo ngữ cảnh. Spring Data Elasticsearch kết nối các phần này qua Completion, @CompletionField, NativeQuery và SearchHits.getSuggest().

## 19. Tài liệu tham khảo

- [Elasticsearch - Completion suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters): mapping, input, weight, prefix, fuzzy, duplicate handling và contexts.
- [Elasticsearch - Completion field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/completion): analyzer, separators và max input length.
- [Elasticsearch - Context suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#context-suggester): category context và geo context.
- [Spring Data Elasticsearch API - CompletionField](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/CompletionField.html): các thuộc tính mapping completion.
- [Spring Data Elasticsearch API - Completion](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/suggest/Completion.html): input, weight và contexts trong model Spring Data.
- [Spring Data Elasticsearch API - NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html): cấu hình suggester bằng Elasticsearch Java API Client.
- [Spring Data Elasticsearch API - SearchHits](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html): truy cập suggest response.

Tên package và builder method có thể thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Khi triển khai, hãy đối chiếu Javadoc với dependency được quản lý trong dự án.
