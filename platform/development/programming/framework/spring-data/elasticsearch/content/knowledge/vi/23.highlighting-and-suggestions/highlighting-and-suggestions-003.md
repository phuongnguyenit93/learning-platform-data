# @Highlight, @HighlightField và tham số liên quan

Trong một trang tìm kiếm, người dùng thường muốn biết vì sao một kết quả xuất hiện và từ khóa khớp ở đoạn nào. Elasticsearch có thể trả về các đoạn văn bản đã đánh dấu phần khớp bằng **highlight**. Ví dụ, với từ khóa “wireless keyboard”, kết quả có thể chứa đoạn “A compact <em>wireless</em> <em>keyboard</em> for travel”.

Trong Spring Data Elasticsearch, repository method có thể khai báo yêu cầu highlight bằng **@Highlight**. Annotation **@HighlightField** xác định field nào cần tạo fragment, còn **@HighlightParameters** cấu hình cách tạo và trình bày fragment như thẻ đánh dấu, kích thước đoạn, số lượng fragment, thứ tự và encoder.

Highlight là metadata của kết quả tìm kiếm. Nó không sửa nội dung document đã lưu và không thay đổi điều kiện xác định document nào khớp query. Muốn sử dụng fragment ở tầng service hoặc API, cần giữ wrapper **SearchHit<T>** hoặc **SearchHits<T>** thay vì chỉ lấy entity content.

## 1. Highlight giải quyết vấn đề gì?

Giả sử entity sản phẩm có tên và mô tả:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    // getters and setters
}
~~~

Người dùng tìm từ khóa wireless keyboard. Query có thể tìm trong cả name và description. Elasticsearch trả các document phù hợp, nhưng chỉ có entity content thì giao diện phải tự quyết định hiển thị đoạn nào. Việc tự tìm chuỗi con ở tầng Java không nhất thiết tái tạo được cách analyzer đã token hóa và so khớp query.

Highlight cho phép Elasticsearch tạo fragment dựa trên query và nội dung đã index. Ví dụ response có thể chứa:

~~~json
{
  "_id": "p-100",
  "_source": {
    "name": "Compact keyboard",
    "description": "A wireless keyboard designed for travel."
  },
  "highlight": {
    "name": [
      "Compact <mark>keyboard</mark>"
    ],
    "description": [
      "A <mark>wireless</mark> <mark>keyboard</mark> designed for travel."
    ]
  }
}
~~~

Trong ví dụ này:

- _source vẫn chứa nội dung gốc của document.
- highlight chứa các đoạn được tạo cho từng field.
- <mark> là thẻ đánh dấu do request cấu hình.
- Một field có thể trả về nhiều fragment.

Highlight hữu ích cho trang kết quả tìm kiếm, gợi ý nội dung, trang tra cứu tài liệu và giao diện cần cho người dùng thấy vị trí từ khóa xuất hiện.

## 2. Khai báo @Highlight trên repository method

@Highlight được đặt trên method repository cần trả kết quả có highlight. Bên trong, fields liệt kê các field muốn đánh dấu:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "multi_match": {
            "query": "?0",
            "fields": ["name^3", "description"]
          }
        }
        """)
    @Highlight(fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    })
    SearchHits<Product> searchWithHighlight(String keyword);
}
~~~

Method trên có hai phần riêng:

- @Query xác định document nào khớp với từ khóa.
- @Highlight yêu cầu Elasticsearch tạo fragment cho name và description.

name^3 là boost trong full-text query. Nó ảnh hưởng relevance score, còn việc field nào được highlight được quyết định bởi @HighlightField.

Tên field trong @HighlightField phải tương ứng với field Elasticsearch được query/highlight. Nếu entity dùng tên Java khác tên field đã mapping, cần khai báo đúng tên field trong index theo mapping và cách Spring Data chuyển đổi.

### Có thể highlight nhiều field

Một method có thể yêu cầu nhiều field:

~~~java
@Highlight(fields = {
    @HighlightField(name = "name"),
    @HighlightField(name = "description"),
    @HighlightField(name = "brand")
})
SearchHits<Product> searchCatalogText(String keyword);
~~~

Mỗi field có thể có cấu hình riêng. Điều này hữu ích khi tên sản phẩm chỉ cần một fragment ngắn, còn mô tả cần nhiều đoạn để người dùng đọc ngữ cảnh.

## 3. @HighlightField và @HighlightParameters

@HighlightField mô tả một field được highlight. Thuộc tính quan trọng nhất là name; thuộc tính parameters cho phép đặt cấu hình riêng cho field đó.

Ví dụ:

~~~java
@Highlight(fields = {
    @HighlightField(
        name = "name",
        parameters = @HighlightParameters(
            preTags = {"<mark>"},
            postTags = {"</mark>"},
            numberOfFragments = 0
        )
    ),
    @HighlightField(
        name = "description",
        parameters = @HighlightParameters(
            preTags = {"<em>"},
            postTags = {"</em>"},
            fragmentSize = 160,
            numberOfFragments = 3,
            order = "score"
        )
    )
})
SearchHits<Product> searchWithFieldOptions(String keyword);
~~~

Trong ví dụ:

- Field name trả về toàn bộ field thay vì cắt thành nhiều fragment.
- Field description trả tối đa ba fragment, mỗi fragment có kích thước mục tiêu 160 ký tự.
- Fragment của description được sắp xếp theo score.
- Hai field dùng thẻ đánh dấu khác nhau.

Cấu hình cụ thể mà annotation hỗ trợ phụ thuộc phiên bản Spring Data Elasticsearch. Khi nâng phiên bản, hãy đối chiếu API Highlight, HighlightField và HighlightParameters của release train đang dùng.

### Tham số chung cho tất cả field

Một số phiên bản cung cấp parameters ở cấp @Highlight để đặt mặc định cho các field:

~~~java
@Highlight(
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        fragmentSize = 120,
        numberOfFragments = 2
    ),
    fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    }
)
SearchHits<Product> searchWithDefaultHighlight(String keyword);
~~~

Cấu hình ở cấp field giúp điều chỉnh riêng từng nội dung. Cấu hình chung giúp tránh lặp lại cùng một bộ tham số. Nếu có cả hai cấp cấu hình, kiểm tra quy tắc ưu tiên/ghi đè trong phiên bản cụ thể của Spring Data Elasticsearch.

## 4. Những tham số highlight thường dùng

Các tham số của Elasticsearch Highlighter điều khiển cách tạo fragment. Những thuộc tính thường gặp trong @HighlightParameters gồm:

| Tham số | Vai trò | Khi nào cần quan tâm |
|---|---|---|
| preTags | Thẻ hoặc chuỗi đặt trước phần khớp | Muốn đánh dấu từ khóa bằng mark, em hoặc kiểu riêng |
| postTags | Thẻ hoặc chuỗi đặt sau phần khớp | Đóng phần đánh dấu tương ứng |
| fragmentSize | Kích thước mục tiêu của mỗi fragment | Field dài cần hiển thị đoạn trích ngắn |
| numberOfFragments | Số fragment tối đa cần trả | Giới hạn độ dài response |
| order | Thứ tự fragment, thường có lựa chọn theo score | Muốn đoạn liên quan nhất xuất hiện trước |
| encoder | Cách encode nội dung fragment | Tránh nội dung văn bản được diễn giải như HTML |
| requireFieldMatch | Có yêu cầu query khớp chính field được highlight hay không | Query nhiều field hoặc cấu trúc field phức tạp |
| type | Loại highlighter | Chọn unified, plain hoặc fvh theo mapping/use case |
| noMatchSize | Số ký tự đầu được trả khi field không có fragment khớp | Muốn có snippet dự phòng |
| boundaryScanner | Cách tìm ranh giới fragment | Muốn cắt theo câu hoặc từ thay vì vị trí ký tự |
| boundaryMaxScan | Phạm vi tìm ranh giới | Điều chỉnh việc tìm ranh giới gần fragment |
| boundaryScannerLocale | Locale cho boundary scanner | Ngôn ngữ ảnh hưởng cách nhận diện ranh giới |
| maxAnalyzedOffset | Giới hạn offset được phân tích cho một số kiểu highlight | Field rất dài và giới hạn tài nguyên |

Không phải mọi tham số đều có mặt trong mọi phiên bản annotation. Tên Java có thể dùng camelCase như numberOfFragments, còn Query DSL bên dưới dùng snake_case như number_of_fragments.

### preTags và postTags

Hai tham số này quyết định phần đánh dấu quanh từ/cụm từ khớp:

~~~java
@HighlightField(
    name = "description",
    parameters = @HighlightParameters(
        preTags = {"<mark class=\"hit\">"},
        postTags = {"</mark>"}
    )
)
~~~

Có thể dùng một hoặc nhiều tag tùy API. Khi cấu hình nhiều tag, Elasticsearch có thể luân phiên chúng trong các fragment. Hãy dùng cặp mở/đóng tương ứng và thống nhất hợp đồng với frontend.

Tag chỉ ảnh hưởng chuỗi fragment trả về. Chúng không được lưu ngược vào _source.

### fragmentSize

fragmentSize xác định kích thước mục tiêu của đoạn trích. Với mô tả dài, fragment ngắn giúp response gọn và UI dễ trình bày.

~~~java
@HighlightField(
    name = "description",
    parameters = @HighlightParameters(
        fragmentSize = 180,
        numberOfFragments = 2
    )
)
~~~

Kích thước fragment được tính theo ký tự/đơn vị văn bản của highlighter, không phải số từ chính xác. Highlighter có thể điều chỉnh ranh giới để đoạn trích dễ đọc.

### numberOfFragments

numberOfFragments giới hạn số fragment trả về cho field:

- Giá trị dương: trả tối đa số fragment đã chỉ định.
- Giá trị 0: yêu cầu trả toàn bộ nội dung field thay vì chia fragment.
- Giá trị mặc định/không đặt: Elasticsearch áp dụng mặc định của highlighter.

Khi dùng 0, fragmentSize không còn tác dụng như khi chia đoạn. Không nên trả toàn bộ field dài chỉ để highlight một vài từ, vì payload có thể rất lớn.

### order

Nếu có nhiều fragment, order = "score" yêu cầu sắp xếp fragment theo mức độ liên quan. Điều này giúp đưa đoạn có nhiều nội dung khớp hoặc điểm cao lên trước.

Nếu không yêu cầu sort theo score, fragment có thể được trả theo thứ tự nội dung. Hãy chọn thứ tự theo cách giao diện sẽ hiển thị snippet.

### encoder

encoder điều khiển việc encode nội dung văn bản trong fragment. Tùy highlighter và phiên bản, giá trị thường gặp là default hoặc html.

Nếu nội dung _source có thể chứa ký tự HTML, cần cân nhắc encoder và cách render ở frontend. Encoder HTML giúp mã hóa các ký tự nội dung như dấu < và > trong fragment trong khi thẻ đánh dấu do highlighter thêm vẫn có ý nghĩa theo cấu hình. Hãy xác nhận hành vi bằng response thực tế và không mặc định mọi chuỗi fragment đều an toàn để chèn trực tiếp vào DOM.

## 5. requireFieldMatch và quan hệ giữa query với field highlight

Mặc định, highlighter thường yêu cầu field được highlight có liên quan tới field trong query. Tham số requireFieldMatch điều khiển hành vi này.

Ví dụ query tìm trên name và description:

~~~json
{
  "multi_match": {
    "query": "wireless keyboard",
    "fields": ["name", "description"]
  }
}
~~~

Khi highlight cả hai field, từng field có thể có fragment nếu nội dung của field đó khớp query.

Nếu requireFieldMatch được đặt thành false, highlighter có thể áp dụng query rộng hơn khi tạo highlight cho field. Điều này hữu ích trong một số query phức tạp, nhưng cũng có thể tạo fragment khó giải thích nếu field không thực sự tham gia phần tìm kiếm như người đọc mong đợi.

Không nên tắt requireFieldMatch như một cách chữa mọi trường hợp fragment rỗng. Trước tiên hãy kiểm tra field name, mapping, analyzer và cấu trúc query.

## 6. Các loại highlighter

Elasticsearch có nhiều highlighter. Tham số type cho phép chọn kiểu nếu phiên bản annotation hỗ trợ.

### Unified highlighter

unified là lựa chọn mặc định phổ biến trong Elasticsearch. Nó hỗ trợ nhiều loại query và có thể tạo fragment từ nội dung field theo cách phù hợp với nhiều use case.

Đây thường là điểm bắt đầu tốt khi ứng dụng chưa có yêu cầu đặc biệt về tốc độ hoặc kiểu fragment.

### Plain highlighter

plain sử dụng cơ chế phân tích nội dung của từng document trong bộ nhớ để tạo highlight. Nó có thể phù hợp với một số query đơn giản, nhưng có thể tốn chi phí hơn khi field dài hoặc số lượng document lớn.

Không chọn plain chỉ vì tên gọi dễ hiểu. Hãy đo trên dữ liệu và workload thực tế.

### Fast Vector Highlighter (fvh)

fvh có thể tận dụng term vectors chứa thông tin vị trí và offset. Muốn sử dụng, mapping field phải được cấu hình term vector phù hợp, ví dụ lưu positions và offsets.

Cấu hình term vectors làm tăng dung lượng index. Chỉ bật khi use case highlight cần lợi ích của highlighter này và đã đánh giá chi phí lưu trữ/indexing.

### Chọn highlighter theo mapping

| Loại | Đặc điểm | Cần lưu ý |
|---|---|---|
| unified | Lựa chọn tổng quát, hỗ trợ nhiều query | Thường là điểm bắt đầu phù hợp |
| plain | Xử lý nội dung document để tạo fragment | Cần theo dõi chi phí trên field dài/nhiều hit |
| fvh | Dùng term vectors để hỗ trợ highlight | Mapping phải lưu term vectors cần thiết |

Highlighter cụ thể có thể hỗ trợ một số query type hoặc tham số khác nhau. Không phải mọi tùy chọn đều có tác dụng giống nhau với mọi highlighter.

## 7. Mapping ảnh hưởng đến highlight như thế nào?

Highlight không phải một tính năng chỉ cần bật annotation là mọi field đều hoạt động như nhau. Elasticsearch cần có cách lấy nội dung và thông tin term/offset phù hợp để tạo fragment.

Các yếu tố cần kiểm tra:

- Field có được mapping và index hay không.
- Field là text, keyword hay kiểu dữ liệu khác.
- Analyzer đã dùng để index và analyzer của query có tạo token như mong đợi không.
- _source có được lưu và có chứa field hay không.
- Mapping có cấu hình term vectors hoặc offsets phù hợp nếu chọn highlighter phụ thuộc chúng không.
- Field có quá dài khiến giới hạn phân tích hoặc giới hạn tài nguyên bị ảnh hưởng không.

Ví dụ full-text field:

~~~java
@Field(type = FieldType.Text, analyzer = "standard")
private String description;
~~~

Nếu description được mapping thành keyword, highlighter có thể xử lý nội dung theo cách khác so với field text được phân tích. Cần chọn mapping dựa trên chức năng tìm kiếm và sort/filter, không chỉ dựa vào việc muốn highlight.

### Multi-field

Một property có thể có field text và subfield keyword:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Khi đó:

- Tìm nội dung tên bằng match trên name.
- Lọc hoặc sort exact theo name.keyword nếu mapping có subfield đó.

Query full-text thường dùng name; exact filter hoặc sort có thể dùng name.keyword. Nếu muốn highlight nội dung tìm kiếm, thường highlight field text đã tham gia query. Đừng mặc định highlight subfield keyword sẽ tạo snippet giống field text.

### Field rất dài

Đối với nội dung dài như bài viết, log hoặc tài liệu, highlight có thể cần phân tích một lượng văn bản lớn. Hãy giới hạn:

- Số fragment.
- Kích thước fragment.
- Số hit mỗi trang.
- Số field cần highlight.

Nếu Elasticsearch báo giới hạn phân tích hoặc fragment rỗng trên field dài, kiểm tra tham số max_analyzed_offset nếu highlighter và phiên bản hỗ trợ, cùng cấu hình tương ứng ở cluster. Không tăng giới hạn một cách máy móc nếu response và chi phí xử lý đã quá lớn.

## 8. Đọc highlight từ SearchHit và SearchHits

Kết quả repository nên giữ metadata nếu service cần fragment. Với kiểu trả về SearchHits<Product>:

~~~java
SearchHits<Product> results =
    productRepository.searchWithHighlight("wireless keyboard");

for (SearchHit<Product> hit : results.getSearchHits()) {
    Product product = hit.getContent();

    Map<String, List<String>> highlightFields =
        hit.getHighlightFields();

    List<String> nameFragments =
        highlightFields.get("name");

    List<String> descriptionFragments =
        highlightFields.get("description");
}
~~~

SearchHit<T> giữ entity content và metadata của một hit. getHighlightFields() trả về map có key là tên field và value là danh sách fragment.

Một field có thể không có key trong map nếu highlighter không trả fragment cho field đó. Một field cũng có thể có nhiều fragment. Vì vậy, code nên xử lý null hoặc danh sách rỗng.

Ví dụ lấy fragment an toàn:

~~~java
List<String> snippets =
    hit.getHighlightFields()
        .getOrDefault("description", List.of());
~~~

Không giả định mọi hit đều có fragment cho mọi field đã khai báo. Document có thể khớp query nhờ name, nhưng description không chứa từ khóa.

### Vì sao nên giữ SearchHits thay vì List<Product>?

Nếu repository trả List<Product>, caller thường chỉ nhận entity content. Metadata highlight của từng hit có thể không còn truy cập được qua kiểu kết quả đó.

Khi cần fragment, ưu tiên kiểu trả về giữ search hit metadata, ví dụ SearchHits<Product> hoặc kiểu page hỗ trợ search hit của phiên bản đang dùng. Kiểm tra return type được Spring Data Elasticsearch hỗ trợ cho repository method trong release train cụ thể.

## 9. Chuyển highlight sang DTO cho API

API thường không nên buộc frontend hiểu trực tiếp SearchHit của Spring Data. Service có thể chuyển entity và fragment thành DTO:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    List<String> nameHighlights,
    List<String> descriptionHighlights
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toSearchItem(SearchHit<Product> hit) {
    Product product = hit.getContent();
    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    return new ProductSearchItem(
        hit.getId(),
        product.getName(),
        highlights.getOrDefault("name", List.of()),
        highlights.getOrDefault("description", List.of())
    );
}
~~~

Service:

~~~java
public List<ProductSearchItem> search(String keyword) {
    SearchHits<Product> hits =
        productRepository.searchWithHighlight(keyword);

    return hits.getSearchHits().stream()
        .map(this::toSearchItem)
        .toList();
}
~~~

Cách này giữ hợp đồng API ổn định và chỉ expose các fragment mà giao diện cần. Nếu cần tổng số kết quả hoặc score, có thể tạo response DTO cấp search riêng.

### Không thay nội dung entity bằng highlight

Highlight là snippet phục vụ trình bày. Không gán fragment trở lại product.description, vì fragment có thể chỉ là một phần nội dung, có tag đánh dấu và không phải bản gốc đầy đủ.

Nên giữ hai trường riêng:

- description: nội dung document đã chuyển đổi từ _source.
- descriptionHighlights: các đoạn trích được highlighter tạo ra.

## 10. Xử lý HTML và nội dung không tin cậy

Highlight thường trả về chuỗi có thẻ đánh dấu như em hoặc mark. Đây là một phần của response, nhưng nội dung gốc có thể do người dùng hoặc nguồn ngoài cung cấp.

Không nên mặc định mọi fragment đều an toàn để render bằng innerHTML. Cần có quy ước rõ:

1. Chọn tag đánh dấu cố định do server cấu hình.
2. Dùng encoder phù hợp nếu nội dung có thể chứa markup.
3. Ở frontend, chỉ cho phép các tag highlight cần thiết.
4. Escape hoặc sanitize phần nội dung không tin cậy theo chính sách của ứng dụng.
5. Không cho người dùng truyền preTags/postTags tùy ý rồi đưa nguyên vào HTML.

Nếu frontend muốn render fragment có tag, hãy dùng component hoặc sanitizer chỉ cho phép tag được quy định, ví dụ mark hoặc em, và loại bỏ attribute không cần thiết.

Nếu API muốn trả text thuần, có thể chuyển đổi fragment thành cấu trúc riêng gồm các đoạn text và trạng thái matched thay vì trả HTML string. Cách này tránh phụ thuộc vào việc frontend diễn giải markup.

## 11. Fragment rỗng hoặc không xuất hiện

Có nhiều nguyên nhân khiến getHighlightFields() rỗng:

- Query không khớp field đã yêu cầu highlight.
- @HighlightField.name không trùng tên field trong index.
- Field không có nội dung được index hoặc không có dữ liệu trong _source khi highlighter cần nguồn này.
- Analyzer của query và analyzer của field tạo token khác kỳ vọng.
- Query type hoặc highlighter type không hỗ trợ cấu trúc query cụ thể.
- Field vượt giới hạn phân tích.
- Method repository không giữ metadata trong kiểu trả về mà caller đang dùng.

### Kiểm tra theo thứ tự

1. Chạy query trong Elasticsearch Dev Tools và thêm phần highlight tương đương.
2. Xác nhận field trong request tồn tại trong mapping.
3. Kiểm tra document thực tế có nội dung field.
4. Kiểm tra analyzer bằng Analyze API nếu token không như mong đợi.
5. Kiểm tra highlighter type và tham số.
6. Đảm bảo repository method trả về kiểu giữ SearchHit metadata.
7. Đọc getHighlightFields() trên một hit cụ thể.

Không nên chuyển requireFieldMatch thành false ngay khi fragment rỗng. Trước tiên cần xác định query có thực sự khớp field đó hay không.

### noMatchSize

Một số cấu hình cho phép noMatchSize trả một đoạn đầu của field ngay cả khi không có fragment khớp. Điều này có thể giúp giao diện luôn có snippet dự phòng, nhưng đoạn đó không phải nội dung được highlight.

Nếu dùng, cần phân biệt fragment khớp từ khóa với đoạn preview không có match. UI không nên trình bày đoạn preview như thể nó chứng minh query đã khớp field đó.

## 12. Kết hợp highlight với @Query và derived query

@Highlight có thể được đặt trên repository method cùng với query method phù hợp.

Ví dụ với @Query:

~~~java
@Query("""
    {
      "multi_match": {
        "query": "?0",
        "fields": ["name^3", "description"]
      }
    }
    """)
@Highlight(fields = {
    @HighlightField(
        name = "name",
        parameters = @HighlightParameters(
            preTags = {"<mark>"},
            postTags = {"</mark>"},
            numberOfFragments = 0
        )
    ),
    @HighlightField(
        name = "description",
        parameters = @HighlightParameters(
            preTags = {"<em>"},
            postTags = {"</em>"},
            fragmentSize = 180,
            numberOfFragments = 2
        )
    )
})
SearchHits<Product> searchCatalogText(String keyword);
~~~

Query quyết định tập document và score. Annotation highlight quyết định field và cách tạo fragment.

Với derived query, có thể khai báo highlight trên method nếu query derivation và return type được phiên bản Spring Data Elasticsearch hỗ trợ. Tuy nhiên, khi cần full-text search nhiều field, boost hoặc cấu trúc bool phức tạp, @Query thường thể hiện rõ query hơn.

## 13. Khi nào cần ElasticsearchOperations?

Annotation thuận tiện khi repository method có cấu trúc query cố định. Khi highlight cần thay đổi theo input runtime, dùng ElasticsearchOperations và query builder phù hợp.

Các trường hợp thường cần cách lập trình:

- Danh sách field highlight thay đổi theo loại tìm kiếm.
- Pre/post tags hoặc fragment policy thay đổi theo use case.
- Query chính và highlight query cần được kiểm soát riêng.
- Cần kết hợp highlight với nhiều filter động, nested query hoặc aggregation.
- Cần chọn highlighter type và tham số phức tạp theo phiên bản/API.
- Cần giữ SearchHits cùng metadata khác như score, sort values và total hits.

Trong Spring Data Elasticsearch, query API có các abstraction để biểu diễn highlight request; tên class và cách gắn highlight vào NativeQuery thay đổi theo release train. Khi dùng Operations, đối chiếu API Highlight, HighlightField, HighlightParameters, HighlightQuery và builder tương ứng trong dependency đang cài đặt. Tránh tự nối JSON highlight vào query string.

Dù dùng repository annotation hay Operations, kết quả vẫn nên được xử lý qua SearchHit<T> nếu service cần fragments.

## 14. Những lỗi thường gặp khi cấu hình highlight

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có highlight map | Query không khớp field hoặc annotation khai báo sai field | Kiểm tra query và mapping |
| Chỉ một field có fragment | Chỉ field đó thực sự chứa token khớp | Kiểm tra nội dung từng field và query |
| Fragment quá dài | fragmentSize lớn hoặc numberOfFragments = 0 | Giảm kích thước và số fragment |
| Fragment không theo mức liên quan | Chưa cấu hình order theo score | Cân nhắc order = score |
| Tag đánh dấu hiển thị như text | Frontend escape toàn bộ fragment | Thống nhất hợp đồng render fragment |
| Nội dung gốc bị thay bằng snippet | Mapper gán highlight vào property entity | Tách content và highlight DTO |
| HTML trong nội dung gây rủi ro render | Fragment được chèn trực tiếp vào DOM | Dùng encoder/sanitizer và tag allowlist |
| Highlight field không đúng | Dùng tên property Java trong khi index field có tên khác | Đối chiếu mapping và tên field thực tế |
| fvh không tạo fragment như mong đợi | Mapping không có term vectors phù hợp | Cấu hình term vectors hoặc chọn unified |
| Fragment rỗng trên field dài | Giới hạn analyzed offset hoặc highlighter option | Kiểm tra field length và giới hạn |
| Không đọc được highlight ở service | Repository chỉ trả entity thuần | Trả SearchHits<T> hoặc kiểu giữ SearchHit<T> |

## 15. Kiểm thử highlight

Highlight phụ thuộc Elasticsearch thực thi query và mapping, vì vậy integration test có giá trị hơn việc chỉ kiểm tra annotation tồn tại.

Một test nên:

1. Tạo index với mapping text cho các field cần tìm.
2. Index document có từ khóa xuất hiện ở một hoặc nhiều field.
3. Gọi repository method có @Highlight.
4. Lấy SearchHit<T> từ kết quả.
5. Kiểm tra key của getHighlightFields().
6. Kiểm tra fragment có tag mở/đóng đã cấu hình.
7. Kiểm tra field không khớp có thể không có fragment.
8. Kiểm tra số lượng fragment và trường hợp numberOfFragments = 0.
9. Kiểm tra content entity vẫn là nội dung gốc.
10. Kiểm tra mapper tạo DTO tách riêng snippet và content.

Skeleton:

~~~java
@DataElasticsearchTest
class ProductHighlightRepositoryTests {

    @Autowired
    private ProductRepository repository;

    @Test
    void returnsHighlightFragmentsForMatchingFields() {
        // Index một Product có name và description chứa từ khóa.
        // Gọi searchWithHighlight("wireless keyboard").
        // Lấy SearchHit<Product> đầu tiên.
        // Kiểm tra highlightFields có key "name"/"description".
        // Kiểm tra fragment chứa tag đánh dấu đã cấu hình.
        // Kiểm tra product.getDescription() vẫn là nội dung gốc.
    }
}
~~~

Đây là skeleton minh họa; annotation test, cấu hình index và cách tạo dữ liệu phụ thuộc phiên bản Spring Boot/Spring Data Elasticsearch của dự án. Dùng Elasticsearch version tương thích với ứng dụng để kiểm tra highlighter thật.

## 16. Checklist khi dùng @Highlight

- [ ] @Highlight được đặt trên đúng repository method.
- [ ] Mỗi @HighlightField.name trỏ tới field có trong mapping.
- [ ] Field mapping và analyzer phù hợp với query.
- [ ] Query thực sự có thể khớp field muốn highlight.
- [ ] preTags và postTags tạo cặp đánh dấu hợp lệ.
- [ ] fragmentSize phù hợp với chiều dài nội dung.
- [ ] numberOfFragments giới hạn response theo nhu cầu.
- [ ] Chỉ dùng numberOfFragments = 0 khi thật sự cần toàn bộ field.
- [ ] order = score được bật khi cần fragment liên quan nhất trước.
- [ ] requireFieldMatch được giữ theo semantics mong muốn.
- [ ] Highlighter type phù hợp mapping; fvh có term vectors cần thiết.
- [ ] Field dài được kiểm soát bằng giới hạn và số fragment.
- [ ] Repository return type giữ SearchHit metadata.
- [ ] Service tách highlight fragments khỏi entity content.
- [ ] Frontend render fragment bằng chính sách HTML an toàn.
- [ ] Integration test xác nhận fragment với Elasticsearch thực tế.

@Highlight khai báo yêu cầu highlight cho repository method, @HighlightField chọn field cần tạo fragment và @HighlightParameters điều khiển cách tạo đoạn trích. Khi giữ kết quả dưới dạng SearchHits<T>, service có thể đọc SearchHit.getHighlightFields() và chuyển fragment sang DTO cho giao diện. Chọn tham số dựa trên mapping, analyzer và trải nghiệm hiển thị; highlight chỉ là metadata trình bày của kết quả tìm kiếm, còn document content vẫn là dữ liệu gốc.

