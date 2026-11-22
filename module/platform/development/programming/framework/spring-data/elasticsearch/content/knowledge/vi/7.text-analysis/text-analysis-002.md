# Chọn analyzer theo ngôn ngữ và dạng nội dung

Trong Elasticsearch, analyzer quyết định cách văn bản được chuyển thành các token để lập chỉ mục và xử lý truy vấn. Chọn analyzer phù hợp giúp tìm kiếm đúng ngôn ngữ, giảm khác biệt do chữ hoa, dấu câu hoặc biến thể từ. Chọn sai analyzer có thể làm mất ý nghĩa của nội dung, khiến kết quả thiếu chính xác hoặc không tìm thấy tài liệu dù từ khóa có xuất hiện.

Spring Data Elasticsearch cho phép khai báo analyzer trong mapping bằng annotation **@Field**, hoặc quản lý cấu hình chi tiết bằng settings và mapping JSON thông qua **@Setting** và **@Mapping**. Bài này trình bày cách lựa chọn analyzer theo ngôn ngữ và dạng dữ liệu, với ví dụ cho nội dung tiếng Anh, tiếng Việt, mã sản phẩm và trường tìm kiếm tự động hoàn thành.

## 1. Analyzer hoạt động như thế nào?

Analyzer xử lý văn bản theo một chuỗi bước. Một analyzer hoàn chỉnh có thể gồm:

1. **Character filters**: biến đổi chuỗi đầu vào trước khi tách token, ví dụ loại bỏ thẻ HTML hoặc thay thế một số ký tự.
2. **Tokenizer**: chia chuỗi thành các token theo quy tắc, ví dụ theo ranh giới từ, khoảng trắng hoặc mẫu biểu thức chính quy.
3. **Token filters**: biến đổi token sau khi tách, ví dụ chuyển chữ thường, loại bỏ stop words, stemming, folding hoặc áp dụng từ đồng nghĩa.

Ví dụ, văn bản **"The QUICK foxes!"** qua analyzer tiếng Anh có thể được chuyển thành các token tương đương **quick** và **fox** sau khi xử lý chữ hoa, stop word và stemming. Kết quả cụ thể phụ thuộc analyzer và phiên bản Elasticsearch.

Analyzer được dùng ở hai thời điểm:

- **Index time**: xử lý giá trị trường trước khi lưu các token vào inverted index.
- **Search time**: xử lý nội dung truy vấn trước khi so khớp với các token đã lập chỉ mục.

Nếu không khai báo riêng, analyzer dùng khi tìm kiếm thường kế thừa analyzer của trường. Có thể khai báo **search_analyzer** để xử lý truy vấn theo quy tắc khác với lúc lập chỉ mục. Hai phía phải tạo ra các token tương thích; nếu không, truy vấn có thể không khớp.

### Minh họa luồng phân tích

~~~text
Văn bản đầu vào
      |
      v
Character filters
      |
      v
Tokenizer
      |
      v
Token filters
      |
      v
Danh sách token được lập chỉ mục hoặc dùng để tìm kiếm
~~~

Không phải trường nào cũng cần analyzer. Trường chứa mã định danh, trạng thái, email hoặc giá trị cần so khớp nguyên vẹn thường dùng **keyword**. Trường số và ngày giờ nên dùng kiểu dữ liệu tương ứng thay vì lưu dưới dạng văn bản chỉ để phân tích.

## 2. Các analyzer và thành phần thường dùng

Elasticsearch cung cấp nhiều analyzer tích hợp và cho phép kết hợp thành phần để tạo custom analyzer.

| Analyzer | Cách xử lý khái quát | Trường hợp phù hợp |
|---|---|---|
| **standard** | Tách theo ranh giới từ Unicode và chuẩn hóa chữ thường | Văn bản thông thường, nội dung chưa cần xử lý riêng theo ngôn ngữ |
| **simple** | Tách theo ký tự không phải chữ cái và chuyển chữ thường | Văn bản đơn giản chỉ gồm từ ngữ |
| **whitespace** | Tách theo khoảng trắng | Nội dung đã được tiền xử lý hoặc phân đoạn từ trước |
| **keyword** | Giữ toàn bộ chuỗi thành một token | Giá trị cần so khớp nguyên vẹn |
| **english**, **french**, **german** và các analyzer ngôn ngữ khác | Áp dụng quy tắc xử lý ngôn ngữ như stop words và stemming | Nội dung đơn ngữ có ngôn ngữ xác định |
| **pattern** | Tách token theo biểu thức chính quy | Log, chuỗi có định dạng hoặc nội dung có dấu phân cách đặc thù |
| **fingerprint** | Chuẩn hóa và sắp xếp token thành một token đại diện | Một số trường hợp phát hiện nội dung gần trùng lặp |

Các analyzer tích hợp có thể khác nhau về tập stop words, thuật toán stemming và quy tắc tokenization. Cần đọc tài liệu đúng phiên bản Elasticsearch và kiểm tra đầu ra thực tế bằng API **_analyze**.

### Analyzer và tokenizer không giống nhau

Tokenizer chỉ đảm nhiệm việc chia văn bản thành token. Analyzer là chuỗi xử lý đầy đủ, gồm character filters, tokenizer và token filters.

Ví dụ:

- **standard** là analyzer có sẵn, sử dụng standard tokenizer cùng các bước chuẩn hóa mặc định.
- **standard tokenizer** chỉ là tokenizer, có thể kết hợp với token filters để tạo custom analyzer.
- **lowercase** là token filter, chuyển token thành chữ thường.
- **asciifolding** là token filter, chuyển nhiều ký tự Unicode có dấu thành dạng ASCII tương ứng.
- **stop** là token filter, loại bỏ những từ được xác định là stop words.
- **stemmer** là token filter, đưa từ về dạng gốc gần đúng theo thuật toán stemming của ngôn ngữ.

Không nên chọn một analyzer chỉ vì tên của nó có vẻ phù hợp. Hãy thử văn bản thực tế của hệ thống, xem danh sách token đầu ra và đánh giá xem các token đó có hỗ trợ đúng nhu cầu tìm kiếm hay không.

## 3. Chọn analyzer theo ngôn ngữ

Ngôn ngữ quyết định cách chia từ, biến thể hình thái, stop words và quy tắc chuẩn hóa. Analyzer tiếng Anh có thể hoạt động tốt với văn bản tiếng Anh nhưng không phù hợp cho văn bản tiếng Việt hoặc tiếng Nhật.

### Tiếng Anh và các ngôn ngữ có hỗ trợ analyzer tích hợp

Elasticsearch cung cấp analyzer theo nhiều ngôn ngữ, ví dụ **english**, **french**, **german**, **spanish**, **italian**, **dutch**, **russian** và một số ngôn ngữ khác. Analyzer cụ thể áp dụng những quy tắc riêng như stop words và stemming.

Ví dụ mapping cho tiêu đề tiếng Anh:

~~~json
{
  "properties": {
    "title_en": {
      "type": "text",
      "analyzer": "english",
      "search_analyzer": "english",
      "fields": {
        "raw": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "description_en": {
      "type": "text",
      "analyzer": "english",
      "search_analyzer": "english"
    }
  }
}
~~~

Với analyzer **english**, các biến thể từ như **connect**, **connecting** hoặc **connected** có thể được đưa về dạng gốc theo thuật toán stemming. Stop words như một số mạo từ và giới từ có thể bị loại bỏ. Điều này hữu ích khi tìm kiếm nội dung tiếng Anh, nhưng có thể không phù hợp với tên thương hiệu, tên riêng hoặc thuật ngữ kỹ thuật cần giữ nguyên.

Nếu cần tìm chính xác tiêu đề, dùng multi-field **title_en.raw** với truy vấn **term**. Trường **title_en** phục vụ tìm kiếm toàn văn; trường **title_en.raw** phục vụ so khớp nguyên vẹn, sắp xếp hoặc aggregation.

### Tiếng Việt

Tiếng Việt có dấu thanh và cách viết từ nhiều âm tiết cách nhau bằng khoảng trắng. Một cụm từ có thể gồm nhiều tiếng tạo thành một đơn vị từ vựng. Vì vậy, tokenizer chỉ tách theo khoảng trắng chưa chắc đã nhận diện đúng ranh giới từ tiếng Việt.

Elasticsearch không cung cấp analyzer tiếng Việt chuyên dụng trong bộ analyzer ngôn ngữ tích hợp tiêu chuẩn. Dùng **standard** hoặc custom analyzer với **standard tokenizer** là điểm khởi đầu hữu ích cho nhiều trường hợp, nhưng cách này không thực hiện word segmentation theo từ ghép tiếng Việt.

Ví dụ, cụm **"học sinh"** có thể được tách thành hai token **học** và **sinh**. Điều đó hữu ích khi người dùng tìm từng tiếng, nhưng không biểu đạt đầy đủ việc hai tiếng kết hợp thành một đơn vị từ vựng. Với các hệ thống tìm kiếm tiếng Việt yêu cầu độ chính xác cao, cần cân nhắc bộ phân đoạn từ tiếng Việt chuyên dụng.

Một custom analyzer cơ bản cho tiếng Việt có thể chuyển chữ thường và giữ nguyên dấu:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "vietnamese_basic": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        }
      }
    }
  }
}
~~~

Giữ dấu giúp phân biệt những từ có cách viết và ý nghĩa khác nhau. Nếu sản phẩm cần tìm kiếm không dấu, có thể tạo thêm analyzer dùng **asciifolding**:

~~~json
{
  "analysis": {
    "analyzer": {
      "vietnamese_folded": {
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
~~~

Không nên mặc định bỏ dấu trên mọi trường. Việc folding làm nhiều dạng chữ khác nhau trở thành cùng một token, có thể tạo kết quả không mong muốn. Một thiết kế thường dùng là giữ trường tiếng Việt có dấu làm trường chính và tạo một multi-field không dấu để hỗ trợ nhu cầu tìm kiếm bổ sung.

Khi cần phân đoạn từ tiếng Việt, có thể dùng thư viện hoặc dịch vụ xử lý ngôn ngữ tự nhiên như VnCoreNLP, Underthesea hoặc một bộ phân đoạn tương thích với hệ thống. Có thể thực hiện phân đoạn ở tầng ứng dụng hoặc pipeline ingest, sau đó lưu kết quả đã phân đoạn vào một trường riêng. Cùng một quy tắc phân đoạn phải được áp dụng cho nội dung truy vấn; nếu chỉ phân đoạn lúc ghi dữ liệu mà không phân đoạn truy vấn, token hai phía có thể không khớp.

Một hướng thiết kế là lưu cả nội dung nguyên bản và nội dung đã phân đoạn:

- **title_vi**: giữ nguyên văn bản để hiển thị và phục vụ truy vấn cơ bản.
- **title_vi_segmented**: chứa kết quả từ bộ phân đoạn từ, dùng cho tìm kiếm theo từ tiếng Việt.
- **title_vi_folded**: tùy nhu cầu, chứa biến thể không dấu để hỗ trợ người dùng nhập không dấu.

Không nên coi việc dùng **asciifolding** là thay thế cho word segmentation. Folding xử lý dạng ký tự; segmentation xử lý ranh giới từ. Hai vấn đề này khác nhau.

### Tiếng Trung, Nhật và Hàn

Với một số ngôn ngữ Đông Á, tách từ cần quy tắc riêng. Elasticsearch có analyzer **cjk** tích hợp cho xử lý một số văn bản CJK, đồng thời có các plugin phân tích chuyên biệt:

- **analysis-smartcn** cung cấp analyzer cho tiếng Trung giản thể.
- **analysis-kuromoji** cung cấp analyzer cho tiếng Nhật.
- **analysis-nori** cung cấp analyzer cho tiếng Hàn.

Các plugin cần tương thích chính xác với phiên bản Elasticsearch và phải được cài trên các node cần thiết theo quy trình vận hành. Một số analyzer có từ điển và quy tắc phân đoạn riêng; kết quả cần được kiểm tra với dữ liệu thực tế, đặc biệt khi có tên riêng, thuật ngữ chuyên ngành hoặc văn bản trộn ngôn ngữ.

Với tiếng Nhật hoặc tiếng Hàn, dùng **standard** như một analyzer chung có thể không đáp ứng nhu cầu phân đoạn từ. Hãy thử analyzer chuyên biệt và đánh giá chất lượng kết quả trước khi triển khai.

## 4. Chọn analyzer theo dạng nội dung

Ngoài ngôn ngữ, loại nội dung cũng quyết định cách phân tích. Một index sản phẩm có thể chứa tên, mô tả, SKU, danh mục, email liên hệ và trường gợi ý tìm kiếm. Không nên dùng cùng một analyzer cho tất cả các trường này.

| Dạng nội dung | Kiểu trường hoặc analyzer gợi ý | Lý do |
|---|---|---|
| Tên và mô tả tự nhiên | **text** với analyzer theo ngôn ngữ | Tìm kiếm theo từ và biến thể từ |
| Mã SKU, mã đơn hàng, mã sản phẩm | **keyword** | Giữ nguyên giá trị để so khớp chính xác |
| Danh mục, trạng thái, nhãn | **keyword** | Lọc, nhóm và aggregation |
| Tên cần vừa tìm toàn văn vừa so khớp chính xác | **text** kèm multi-field **keyword** | Phục vụ hai loại truy vấn |
| Email và URL | **uax_url_email** tokenizer hoặc trường **keyword**, tùy yêu cầu | Bảo toàn cấu trúc địa chỉ và chuỗi |
| Log và mã kỹ thuật | **keyword**, **whitespace** hoặc **pattern** | Phụ thuộc định dạng và dấu phân cách |
| Tìm kiếm gợi ý khi đang nhập | **search_as_you_type** hoặc custom analyzer với **edge_ngram** | Tìm tiền tố và một phần nội dung |
| Số tiền, số lượng, thời gian | Kiểu **numeric** hoặc **date** | Cho phép so sánh, range và sắp xếp đúng kiểu |

### Tên sản phẩm và mô tả

Tên sản phẩm thường cần cả tìm kiếm toàn văn và so khớp chính xác. Có thể dùng multi-field:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "english",
    "fields": {
      "raw": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Truy vấn **match** trên **name** sẽ phân tích từ khóa theo analyzer tiếng Anh. Truy vấn **term** trên **name.raw** sẽ so khớp giá trị nguyên vẹn. Nếu nội dung là tiếng Việt, thay analyzer bằng analyzer tiếng Việt phù hợp với chiến lược phân đoạn và chuẩn hóa của ứng dụng.

Mô tả dài thường dùng **text** để tìm kiếm theo nội dung. Không nên áp dụng **keyword** cho toàn bộ mô tả dài nếu người dùng cần tìm theo từng từ.

### Mã định danh, SKU và trạng thái

Mã SKU như **KB-1000-BLK** thường cần được giữ nguyên. Dùng **keyword** để tránh tokenizer chia mã thành nhiều token:

~~~json
{
  "sku": {
    "type": "keyword"
  },
  "status": {
    "type": "keyword"
  }
}
~~~

Nếu mã không phân biệt chữ hoa và chữ thường, có thể dùng normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": [
            "lowercase"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Normalizer biến đổi giá trị keyword thành một token chuẩn hóa. Chỉ dùng khi quy tắc nghiệp vụ xác định mã không phân biệt hoa thường. Nếu hệ thống phân biệt **ab-12** và **AB-12**, không được tự ý chuyển cả hai về cùng dạng.

### Email và URL

Địa chỉ email và URL có dấu chấm, dấu gạch, dấu @ hoặc dấu phân cách khác. Nếu cần tìm kiếm theo toàn bộ địa chỉ, dùng **keyword** thường dễ kiểm soát. Nếu cần tách token và giữ cấu trúc URL/email, có thể cân nhắc **uax_url_email** tokenizer trong custom analyzer.

Không nên dùng analyzer ngôn ngữ thông thường cho trường URL hoặc email nếu ứng dụng cần so khớp chính xác toàn bộ chuỗi. Với truy vấn miền email, tên miền hoặc thành phần URL, nên cân nhắc lưu thêm các trường đã tách riêng như **emailDomain** hoặc **urlHost**.

### Tìm kiếm gợi ý khi nhập

Tìm kiếm tự động hoàn thành có yêu cầu khác tìm kiếm toàn văn. Người dùng có thể nhập một phần đầu của từ hoặc cụm từ. Elasticsearch cung cấp kiểu trường **search_as_you_type**, hoặc có thể tạo custom analyzer với **edge_ngram**.

Ví dụ dùng **search_as_you_type**:

~~~json
{
  "properties": {
    "suggest_name": {
      "type": "search_as_you_type"
    }
  }
}
~~~

Kiểu trường này tạo các subfield hỗ trợ tìm kiếm tiền tố và cụm từ. Khi cần kiểm soát chi tiết hơn, có thể dùng tokenizer hoặc token filter **edge_ngram** trong analyzer lập chỉ mục và dùng analyzer bình thường ở thời điểm tìm kiếm.

Không nên áp dụng **ngram** hoặc **edge_ngram** cho tất cả trường vì số lượng token có thể tăng nhanh, làm index lớn và tốn tài nguyên. Hãy tạo trường chuyên dụng cho autocomplete.

## 5. Khai báo analyzer trong Spring Data Elasticsearch

Có thể khai báo analyzer trực tiếp bằng **@Field** nếu analyzer đã tồn tại trong Elasticsearch hoặc được định nghĩa trong settings của index.

Ví dụ lớp tài liệu có trường tiếng Anh, tiếng Việt và SKU:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = true)
@Setting(settingPath = "/elasticsearch/products-settings.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(
        type = FieldType.Text,
        analyzer = "english",
        searchAnalyzer = "english"
    )
    private String titleEn;

    @Field(
        type = FieldType.Text,
        analyzer = "vietnamese_basic",
        searchAnalyzer = "vietnamese_basic"
    )
    private String titleVi;

    @Field(type = FieldType.Text, analyzer = "english")
    private String descriptionEn;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Trong ví dụ, **vietnamese_basic** là custom analyzer phải được khai báo trong tệp settings. **english** là analyzer tích hợp của Elasticsearch. Tên analyzer trong annotation phải khớp chính xác với tên được khai báo hoặc tên analyzer tích hợp.

Nếu cần multi-field, mapping JSON thường rõ ràng và linh hoạt hơn. Có thể khai báo mapping bằng **@Mapping(mappingPath = "...")** trên lớp tài liệu, sau đó giữ các annotation **@Field** nhất quán với cấu trúc JSON. Tránh khai báo cùng trường bằng hai cấu hình mâu thuẫn.

Một tệp settings minh họa:

~~~json
{
  "index": {
    "analysis": {
      "analyzer": {
        "vietnamese_basic": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        },
        "vietnamese_folded": {
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

Với một dự án đa ngôn ngữ, mapping JSON có thể khai báo các trường riêng cho từng ngôn ngữ:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "title_en": {
      "type": "text",
      "analyzer": "english",
      "fields": {
        "raw": {
          "type": "keyword"
        }
      }
    },
    "title_vi": {
      "type": "text",
      "analyzer": "vietnamese_basic",
      "fields": {
        "folded": {
          "type": "text",
          "analyzer": "vietnamese_folded"
        }
      }
    },
    "description_en": {
      "type": "text",
      "analyzer": "english"
    },
    "description_vi": {
      "type": "text",
      "analyzer": "vietnamese_basic"
    },
    "title_vi_segmented": {
      "type": "text",
      "analyzer": "whitespace",
      "search_analyzer": "whitespace"
    }
  }
}
~~~

Tên trường trong JSON cần khớp với tên trường thực tế được ghi vào Elasticsearch. Nếu ứng dụng dùng camelCase trong Java nhưng mapping dùng snake_case, hãy cấu hình quy tắc chuyển đổi nhất quán hoặc dùng tên trường tương ứng trong mapping.

Trường **title_vi_segmented** nhận nội dung đã được bộ phân đoạn từ xử lý trước, với các token được phân tách bằng khoảng trắng. Vì vậy, ví dụ dùng analyzer **whitespace** để giữ nguyên từng token do bộ phân đoạn tạo ra. Ứng dụng cũng phải phân đoạn từ khóa tìm kiếm theo cùng quy tắc trước khi gửi truy vấn.

## 6. Phân biệt analyzer, search_analyzer và normalizer

Ba khái niệm này có liên quan nhưng có phạm vi sử dụng khác nhau.

| Thuộc tính | Dùng cho | Đặc điểm |
|---|---|---|
| **analyzer** | Trường **text** khi lập chỉ mục | Chuyển nội dung thành các token được lưu trong inverted index |
| **search_analyzer** | Trường **text** khi phân tích truy vấn | Có thể khác analyzer lập chỉ mục nhưng cần tạo token tương thích |
| **search_quote_analyzer** | Truy vấn cụm từ hoặc phrase khi được cấu hình | Cho phép dùng quy tắc phân tích riêng cho truy vấn có dấu ngoặc kép |
| **normalizer** | Trường **keyword** | Chuẩn hóa toàn bộ giá trị thành một token, không thực hiện phân đoạn từ |

Ví dụ, có thể dùng analyzer tiếng Anh ở cả index time và search time:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "english",
    "search_analyzer": "english"
  }
}
~~~

Trong một số thiết kế, analyzer lập chỉ mục có thể dùng stemming hoặc n-gram, trong khi analyzer tìm kiếm chỉ chuẩn hóa chữ thường. Khi làm vậy, cần kiểm tra token đầu ra ở cả hai phía để bảo đảm truy vấn vẫn có thể khớp với token đã lưu.

**term query** không phân tích nội dung truy vấn như **match query**. Khi cần so khớp chính xác, hãy dùng trường **keyword** và truy vấn **term**. Khi cần tìm theo nội dung tự nhiên, hãy dùng trường **text** và truy vấn **match** hoặc **match_phrase** phù hợp.

## 7. Xử lý nội dung đa ngôn ngữ

Một trường có thể chứa nhiều ngôn ngữ, ví dụ mô tả sản phẩm có cả tiếng Việt và tiếng Anh. Nếu dùng analyzer tiếng Anh cho toàn bộ trường, các từ tiếng Việt có thể bị xử lý không phù hợp. Nếu dùng analyzer tiếng Việt cho toàn bộ trường, nội dung tiếng Anh cũng có thể không được stemming và lọc đúng cách.

Một số chiến lược phổ biến:

**Tách trường theo ngôn ngữ.** Lưu **description_vi**, **description_en** và chọn trường truy vấn theo ngôn ngữ người dùng. Đây là cách dễ kiểm soát khi ứng dụng biết ngôn ngữ ở thời điểm nhập dữ liệu.

**Phát hiện ngôn ngữ khi ingest.** Ứng dụng hoặc dịch vụ xử lý dữ liệu nhận diện ngôn ngữ, sau đó ghi nội dung vào trường tương ứng. Cần có cách xử lý cho nội dung ngắn, tên riêng hoặc đoạn trộn ngôn ngữ vì phát hiện ngôn ngữ có thể không chính xác.

**Lưu cả bản gốc và bản đã chuẩn hóa.** Bản gốc dùng hiển thị; bản chuẩn hóa hoặc phân đoạn dùng tìm kiếm. Cách này hữu ích với tiếng Việt và các ngôn ngữ cần tiền xử lý đặc biệt.

**Dùng analyzer chung cho nội dung trộn ngôn ngữ.** Analyzer **standard** có thể là lựa chọn nền tảng khi không thể xác định ngôn ngữ, nhưng sẽ không cung cấp đầy đủ stemming hay word segmentation theo từng ngôn ngữ.

Không nên kỳ vọng một analyzer đơn lẻ xử lý tối ưu mọi ngôn ngữ. Lựa chọn cần dựa trên thành phần ngôn ngữ thực tế, loại truy vấn, chi phí lưu trữ và mức độ chính xác mong muốn.

## 8. Kiểm tra analyzer bằng API _analyze

Trước khi tạo index trong môi trường thật, hãy thử analyzer với các chuỗi đại diện cho dữ liệu của ứng dụng.

Kiểm tra analyzer tích hợp:

~~~http
POST /_analyze
{
  "analyzer": "english",
  "text": "The running shoes are comfortable"
}
~~~

Kiểm tra custom analyzer tiếng Việt:

~~~http
POST /_analyze
{
  "analyzer": "vietnamese_basic",
  "text": "Trường đại học ở Thành phố Hồ Chí Minh"
}
~~~

Kiểm tra analyzer không dấu:

~~~http
POST /_analyze
{
  "analyzer": "vietnamese_folded",
  "text": "Thành phố Hồ Chí Minh"
}
~~~

Có thể kiểm tra analyzer gắn với một trường sau khi index đã được tạo:

~~~http
POST /products/_analyze
{
  "field": "title_vi",
  "text": "Trường đại học Bách khoa"
}
~~~

Khi xem kết quả, hãy chú ý:

- Số lượng token được tạo ra.
- Token có giữ dấu hay không.
- Chữ hoa đã được chuẩn hóa chưa.
- Từ dừng có bị loại bỏ ngoài ý muốn không.
- Các từ ghép hoặc thuật ngữ quan trọng có bị tách sai không.
- Nội dung đầu vào có tạo token giống với cách phân tích truy vấn dự kiến không.

Nên tạo một bộ dữ liệu thử gồm tên riêng, từ có dấu, từ không dấu, số, mã sản phẩm, dấu câu, từ viết tắt và nội dung trộn ngôn ngữ. Không chỉ thử một câu đơn giản vì nhiều lỗi analyzer chỉ xuất hiện ở dữ liệu thực tế.

## 9. Kiểm tra kết quả tìm kiếm sau khi chọn analyzer

API **_analyze** cho biết văn bản được chuyển thành token như thế nào, nhưng chưa chứng minh kết quả tìm kiếm đáp ứng yêu cầu nghiệp vụ. Sau khi tạo index, hãy ghi một số tài liệu mẫu và chạy các truy vấn đại diện.

Ví dụ tìm kiếm toàn văn:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "title_en": "running shoe"
    }
  }
}
~~~

Ví dụ so khớp SKU chính xác:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "sku": "KB-1000-BLK"
    }
  }
}
~~~

Ví dụ tìm kiếm tiếng Việt trên trường đã phân đoạn:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "title_vi_segmented": "học sinh"
    }
  }
}
~~~

Nếu kết quả không như mong đợi, kiểm tra cả mapping và token. Một truy vấn **term** trên trường **text** có thể không hoạt động như kỳ vọng vì trường đã được phân tích. Ngược lại, truy vấn **match** trên trường **keyword** không mang lại hành vi tìm kiếm toàn văn như một trường **text**.

Có thể dùng **_termvectors** để xem các term đã được lưu cho một tài liệu cụ thể, hoặc **_explain** để hiểu vì sao một tài liệu khớp hoặc không khớp với truy vấn. Những API này hữu ích khi cần chẩn đoán sâu hơn sau bước kiểm tra analyzer.

## 10. Những lỗi thường gặp khi lựa chọn analyzer

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Tìm kiếm tiếng Việt thiếu kết quả | Chỉ dùng tokenizer theo khoảng trắng, chưa xử lý từ ghép | Kiểm tra nhu cầu word segmentation; cân nhắc bộ phân đoạn tiếng Việt |
| Người dùng nhập không dấu nhưng không tìm thấy | Index giữ dấu còn truy vấn không dấu | Tạo trường folded riêng hoặc chuẩn hóa hai phía theo cùng quy tắc |
| Tìm kiếm mã SKU trả kết quả lạ | Dùng analyzer text làm tách mã thành nhiều token | Chuyển trường mã sang keyword |
| Tìm kiếm tiếng Anh bỏ mất từ quan trọng | Stop word hoặc stemming không phù hợp với tên riêng, thuật ngữ | Dùng analyzer khác hoặc trường riêng cho nội dung cần giữ nguyên |
| Tìm kiếm đa ngôn ngữ thiếu chính xác | Dùng một analyzer ngôn ngữ cho văn bản trộn nhiều ngôn ngữ | Tách trường, phát hiện ngôn ngữ hoặc dùng analyzer chung có chủ đích |
| Truy vấn không khớp dù từ xuất hiện trong tài liệu | Analyzer lập chỉ mục và analyzer tìm kiếm tạo token khác nhau | So sánh kết quả _analyze ở cả hai phía |
| Index tăng kích thước nhanh | Dùng n-gram hoặc nhiều multi-field không cần thiết | Chỉ tạo trường phục vụ nhu cầu tìm kiếm thực tế |
| Analyzer tùy chỉnh không tạo được index | Thiếu analyzer, tokenizer, plugin hoặc cấu hình settings sai | Kiểm tra settings, log Elasticsearch và plugin trên các node |

Một lỗi quan trọng là thay đổi analyzer trong tệp cấu hình rồi mong index hiện tại tự cập nhật. Analyzer gắn với mapping và settings của index; thay đổi có thể yêu cầu tạo index mới và reindex dữ liệu. Hãy xác định vòng đời index trước khi triển khai thay đổi.

## 11. Quy trình lựa chọn analyzer trong dự án

Có thể áp dụng quy trình sau khi thiết kế mapping:

1. **Xác định ngôn ngữ.** Ghi nhận ngôn ngữ của dữ liệu, khả năng trộn ngôn ngữ và cách nhận diện ngôn ngữ.
2. **Phân loại trường.** Xác định trường là văn bản tự nhiên, mã định danh, danh mục, email, URL, số, ngày hay nội dung gợi ý.
3. **Xác định kiểu truy vấn.** Phân biệt tìm toàn văn, so khớp chính xác, phrase, lọc, sắp xếp, aggregation và autocomplete.
4. **Chọn analyzer ban đầu.** Dùng analyzer tích hợp phù hợp nếu có; tạo custom analyzer khi cần quy tắc riêng.
5. **Thiết kế multi-field khi cần.** Một trường có thể có bản text để tìm kiếm và bản keyword để so khớp chính xác.
6. **Kiểm tra token.** Dùng API **_analyze** với bộ dữ liệu gần với dữ liệu thật.
7. **Kiểm tra truy vấn.** Tạo tài liệu mẫu và thử các truy vấn mà ứng dụng sẽ sử dụng.
8. **Đánh giá chi phí.** Cân nhắc kích thước index, tốc độ ghi, tốc độ tìm kiếm và độ chính xác.
9. **Đóng gói cấu hình.** Đưa settings và mapping vào resources, gắn với lớp tài liệu bằng **@Setting** và **@Mapping** nếu ứng dụng quản lý index theo cách này.
10. **Lập kế hoạch thay đổi.** Khi mapping hoặc analyzer thay đổi theo cách không tương thích, tạo index mới và reindex thay vì giả định cấu hình cũ được cập nhật tự động.

Analyzer tốt là analyzer phù hợp với ngôn ngữ, dạng nội dung và cách người dùng tìm kiếm trong ứng dụng. Với tiếng Anh, analyzer ngôn ngữ tích hợp có thể cung cấp stemming và stop words hữu ích. Với tiếng Việt, cần chú ý sự khác biệt giữa tách tiếng và phân đoạn từ; folding dấu chỉ giải quyết chuẩn hóa ký tự. Với mã định danh và giá trị cần so khớp nguyên vẹn, **keyword** thường phù hợp hơn analyzer văn bản. Việc thử token và truy vấn trên dữ liệu đại diện là bước cần thiết trước khi đưa mapping vào sử dụng.
