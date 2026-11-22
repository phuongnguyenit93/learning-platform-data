# Tìm kiếm tiếng Việt, dấu tiếng Việt và yêu cầu plugin tương ứng

Tìm kiếm tiếng Việt trong Elasticsearch cần xử lý đồng thời cách viết Unicode, dấu thanh, chữ `đ`, cách tách từ và mức độ khớp mà sản phẩm mong muốn. Một cấu hình chỉ chuyển chữ hoa thành chữ thường chưa đủ để tìm kiếm không phân biệt dấu. Ngược lại, bỏ toàn bộ dấu trong mọi trường cũng có thể làm mất khác biệt ngữ nghĩa giữa các từ tiếng Việt.

Trong Spring Data Elasticsearch, ứng dụng định nghĩa analyzer trong index settings rồi ánh xạ các trường document tới analyzer đó. Elasticsearch thực hiện tokenization và phân tích văn bản ở phía server. Một số bộ lọc có sẵn như `lowercase` và `asciifolding` không cần cài plugin; nếu cần các thành phần ICU thì phải cài plugin `analysis-icu` đúng phiên bản trên các node Elasticsearch. Plugin ICU xử lý Unicode tốt hơn trong nhiều trường hợp, nhưng bản thân nó không phải bộ phân đoạn từ tiếng Việt theo từ điển.

## 1. Những đặc điểm cần xử lý khi tìm kiếm tiếng Việt

### Dấu thanh và dấu phụ

Tiếng Việt sử dụng dấu thanh và dấu phụ để phân biệt cách đọc cũng như ý nghĩa. Ví dụ:

| Có dấu | Không dấu |
|---|---|
| tiếng Việt | tieng Viet |
| Đà Nẵng | Da Nang |
| trường học | truong hoc |
| cửa hàng | cua hang |
| thủ đô | thu do |

Người dùng có thể gõ có dấu hoặc không dấu tùy thiết bị, bàn phím và thói quen. Nếu hệ thống chỉ lập chỉ mục văn bản có dấu rồi tìm theo chuỗi không dấu, truy vấn có thể không khớp. Một lựa chọn là tạo thêm trường đã bỏ dấu để phục vụ tìm kiếm linh hoạt.

### Chữ `đ` và `Đ`

Chữ `đ`/`Đ` là một chữ cái riêng trong tiếng Việt. Nó không đơn giản là chữ `d` có dấu kết hợp theo cách Unicode thông thường. Vì vậy, không nên giả định mọi bộ lọc bỏ dấu đều chuyển `đ` thành `d` theo đúng mong muốn.

Khi xây dựng analyzer không phân biệt dấu, hãy kiểm tra riêng các cặp như `điện`/`dien`, `Đà Nẵng`/`Da Nang`, `Đặng`/`Dang`. Nếu bộ lọc được chọn không xử lý chữ này như mong muốn, có thể bổ sung mapping tường minh `đ => d` và `Đ => D` trước bước lowercase.

### Unicode dựng sẵn và Unicode tổ hợp

Một ký tự tiếng Việt có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cái cơ sở cộng với dấu kết hợp. Hai chuỗi nhìn giống nhau có thể có dãy code point khác nhau. Đây là khác biệt giữa Unicode NFC và NFD.

Ví dụ, chữ `ế` có thể được biểu diễn bằng ký tự dựng sẵn hoặc bằng `e` cộng nhiều dấu kết hợp. Khi so sánh chuỗi ở tầng ứng dụng hoặc đưa dữ liệu qua nhiều hệ thống, nên chuẩn hóa Unicode nhất quán, thường là NFC. Chuẩn hóa NFC không xóa dấu; nó chỉ chuẩn hóa cách biểu diễn tương đương của cùng một văn bản.

Ví dụ Java:

```java
import java.text.Normalizer;

public final class VietnameseTextNormalizer {

    private VietnameseTextNormalizer() {}

    public static String toNfc(String value) {
        if (value == null) {
            return null;
        }
        return Normalizer.normalize(value, Normalizer.Form.NFC);
    }
}
```

Chuẩn hóa Unicode và bỏ dấu là hai thao tác khác nhau. Không nên dùng một hàm bỏ dấu để thay thế cho NFC nếu mục tiêu là giữ nguyên chính tả.

### Phân đoạn từ tiếng Việt

Tiếng Việt thường viết các âm tiết cách nhau bằng khoảng trắng. Một cụm từ có thể gồm nhiều âm tiết nhưng mang nghĩa như một đơn vị từ vựng, ví dụ `học sinh`, `nhà đất`, `công nghệ thông tin`. Tokenizer theo ranh giới từ thông thường có thể tạo token cho từng âm tiết thay vì nhận diện toàn bộ cụm từ theo từ điển.

Điều này không có nghĩa tokenizer chuẩn luôn sai. Với nhiều chức năng tìm kiếm, token theo khoảng trắng vẫn hữu ích. Tuy nhiên, nếu sản phẩm cần tìm theo từ ghép, đồng nghĩa, stemming hoặc phân đoạn từ tiếng Việt có từ điển, cần thêm bước xử lý ngôn ngữ phù hợp.

`analysis-icu` cung cấp tokenizer và bộ lọc Unicode tổng quát. Nó không tự động trở thành bộ phân đoạn từ tiếng Việt có từ điển và không tự sinh các cụm từ như `học_sinh` hay `công_nghệ_thông_tin`. Phân đoạn từ có thể được thực hiện trước khi index bằng thư viện/service tiếng Việt, hoặc bằng một plugin phân tích tiếng Việt của bên thứ ba đã được đánh giá kỹ về tính tương thích và bảo trì.

## 2. Tìm kiếm có dấu và không phân biệt dấu

Trước khi cấu hình analyzer, hãy quyết định sản phẩm cần loại tìm kiếm nào.

### Tìm kiếm phân biệt dấu

Tìm kiếm phân biệt dấu giữ nguyên khác biệt chính tả. Ví dụ, truy vấn `ma` không tự động khớp `má`, `mà`, `mả`, `mã` hoặc `mạ`. Cách này phù hợp với tên riêng, nội dung cần khớp chính xác và các trường mà dấu có thể thay đổi ý nghĩa.

### Tìm kiếm không phân biệt dấu

Tìm kiếm không phân biệt dấu cho phép truy vấn `tieng viet` khớp với `tiếng Việt`, hoặc `da nang` khớp với `Đà Nẵng` nếu analyzer xử lý cả dấu và chữ `đ` theo quy tắc đã chọn.

Điều này tăng khả năng tìm thấy dữ liệu khi người dùng không gõ dấu, nhưng làm nhiều từ khác nghĩa trở thành cùng một dạng sau khi folding. Ví dụ, `ma`, `má`, `mà`, `mả`, `mã` và `mạ` có thể cùng được quy về `ma`. Vì vậy, không nên xóa dấu khỏi dữ liệu gốc hoặc chỉ dùng trường folded cho mọi mục đích.

### Kết hợp hai cách bằng multi-field

Một thiết kế hữu ích là giữ trường chính phân biệt dấu và tạo subfield đã folding. Khi truy vấn, có thể ưu tiên trường có dấu rồi dùng trường không dấu như phương án mở rộng.

Ví dụ:

| Trường | Analyzer | Vai trò |
|---|---|---|
| `title` | `vi_sensitive` | Giữ dấu để ưu tiên kết quả đúng chính tả |
| `title.folded` | `vi_folded` | Hỗ trợ người dùng nhập không dấu |

Truy vấn có thể tăng trọng số cho `title` và giảm trọng số cho `title.folded`. Cách này giữ lại khả năng phân biệt dấu trong khi vẫn hỗ trợ tìm kiếm linh hoạt.

## 3. Các thành phần phân tích văn bản có sẵn

Elasticsearch có một số analyzer và token filter tích hợp, không yêu cầu cài plugin bổ sung:

- `standard` tokenizer: chia văn bản theo quy tắc token Unicode phổ biến.
- `lowercase` token filter: chuyển token thành chữ thường.
- `asciifolding` token filter: chuyển nhiều ký tự có dấu sang dạng ASCII tương ứng.
- `stop` token filter: loại bỏ stop words theo danh sách cấu hình.
- `synonym` hoặc `synonym_graph`: xử lý từ đồng nghĩa theo cấu hình.

Để tạo analyzer bỏ dấu cơ bản, có thể kết hợp `standard`, `lowercase` và `asciifolding`. Cấu hình này không cần `analysis-icu`.

Tuy vậy, cần kiểm tra đầu ra thực tế với dữ liệu tiếng Việt, đặc biệt là `đ`, dạng Unicode tổ hợp, dấu câu và tên riêng. Không nên mặc định rằng mọi ký tự tiếng Việt đều được chuyển thành dạng ASCII mong muốn chỉ vì đã bật `asciifolding`.

## 4. Tạo analyzer tiếng Việt cơ bản không cần plugin

Ví dụ index settings sau định nghĩa một analyzer giữ dấu và một analyzer bỏ dấu cơ bản. Mapping ký tự `đ`/`Đ` được thêm rõ ràng để không phụ thuộc vào việc folding có xử lý chữ này hay không.

```json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "vi_d_mapping": {
          "type": "mapping",
          "mappings": [
            "đ => d",
            "Đ => D"
          ]
        }
      },
      "analyzer": {
        "vi_sensitive": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        },
        "vi_folded": {
          "type": "custom",
          "char_filter": [
            "vi_d_mapping"
          ],
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
```

`vi_sensitive` chuyển chữ thường nhưng giữ dấu. `vi_folded` thay `đ`/`Đ` trước, sau đó tokenize, lowercase và folding các ký tự có dấu. Đây là analyzer cơ bản cho tìm kiếm từ theo token; nó không giải quyết phân đoạn từ tiếng Việt theo từ điển.

### Tạo index và kiểm tra analyzer

Có thể tạo index bằng REST API:

```http
PUT /articles
Content-Type: application/json

{
  "settings": {
    "analysis": {
      "char_filter": {
        "vi_d_mapping": {
          "type": "mapping",
          "mappings": ["đ => d", "Đ => D"]
        }
      },
      "analyzer": {
        "vi_sensitive": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase"]
        },
        "vi_folded": {
          "type": "custom",
          "char_filter": ["vi_d_mapping"],
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "vi_sensitive",
        "fields": {
          "folded": {
            "type": "text",
            "analyzer": "vi_folded"
          }
        }
      }
    }
  }
}
```

Kiểm tra analyzer không dấu:

```http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "vi_folded",
  "text": [
    "Tiếng Việt có dấu",
    "Đà Nẵng",
    "Đặng Thị Hòa",
    "hoà bình"
  ]
}
```

Kiểm tra analyzer phân biệt dấu:

```http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "vi_sensitive",
  "text": [
    "Tiếng Việt có dấu",
    "Đà Nẵng",
    "Đặng Thị Hòa"
  ]
}
```

Endpoint `_analyze` trả về token thực tế. Hãy dùng kết quả đó để xác nhận chữ `đ`, dấu tiếng Việt và ranh giới token đúng như yêu cầu trước khi đưa analyzer vào mapping chính thức.

## 5. Khi nào cần plugin `analysis-icu`?

ICU là bộ thư viện quốc tế hóa của Unicode. Plugin `analysis-icu` bổ sung các thành phần phân tích dựa trên ICU cho Elasticsearch, chẳng hạn:

- `icu_tokenizer`: tokenizer dựa trên quy tắc phân đoạn từ Unicode của ICU.
- `icu_folding`: token filter thực hiện Unicode case folding và folding nhiều dấu/ký tự tương đương.
- `icu_normalizer`: chuẩn hóa Unicode token theo form được cấu hình.
- Các thành phần ICU khác phục vụ collation hoặc biến đổi Unicode.

Plugin này hữu ích khi cần xử lý Unicode đa ngôn ngữ nhất quán hơn, hoặc cần các quy tắc tokenizer/normalizer của ICU. Nó không phải điều kiện bắt buộc cho mọi ứng dụng tiếng Việt. Nếu `standard` tokenizer cùng `asciifolding` đáp ứng yêu cầu và kết quả đã được kiểm tra, có thể không cần cài thêm plugin.

### ICU không đồng nghĩa với Vietnamese word segmenter

`icu_tokenizer` áp dụng quy tắc ranh giới từ Unicode tổng quát. Nó có thể cải thiện cách xử lý Unicode, dấu câu và một số hệ chữ, nhưng không tự động sử dụng từ điển tiếng Việt để nhận diện mọi từ ghép nhiều âm tiết.

Nếu yêu cầu sản phẩm là nhận diện `học sinh` như một đơn vị từ vựng, tìm từ đồng nghĩa tiếng Việt, stemming hoặc xử lý biến thể từ, cần một bước phân đoạn/ngôn ngữ chuyên biệt. Có thể:

1. Tiền xử lý văn bản bằng thư viện phân đoạn tiếng Việt trong ứng dụng hoặc một dịch vụ NLP.
2. Ghi thêm trường đã phân đoạn vào document, giữ trường nguyên bản để hiển thị.
3. Dùng plugin Elasticsearch bên thứ ba nếu dự án đã đánh giá nguồn gốc, hỗ trợ phiên bản, khả năng bảo trì và an toàn của plugin.

Không cài một plugin chỉ vì tên gọi có chữ `Vietnamese`. Cần xác minh plugin hỗ trợ đúng phiên bản Elasticsearch, cách tokenizer hoạt động, từ điển được cập nhật ra sao và cách xử lý dữ liệu tiếng Việt thực tế.

## 6. Cài đặt plugin `analysis-icu`

`analysis-icu` là plugin phía Elasticsearch server. Thêm dependency Maven/Gradle vào ứng dụng Spring Boot không cài plugin vào cluster. Plugin phải được cài trên các node Elasticsearch cần xử lý index/query và Elasticsearch phải được khởi động lại để nạp plugin.

### Cài trên máy chủ Elasticsearch

Chạy lệnh bằng tài khoản và môi trường quản trị Elasticsearch trên từng node:

```bash
bin/elasticsearch-plugin install analysis-icu
```

Plugin phải khớp phiên bản Elasticsearch đang chạy. Lệnh cài plugin đi kèm bản phân phối Elasticsearch sẽ lấy bản plugin tương ứng. Sau khi cài, khởi động lại node theo quy trình vận hành của cluster.

Kiểm tra plugin đã được nạp:

```http
GET /_nodes/plugins
```

Trong response, kiểm tra node có plugin `analysis-icu`. Tất cả node có thể nhận request tạo index hoặc thực hiện phân tích cần có plugin phù hợp. Trong cluster production, cần lên kế hoạch triển khai đồng bộ và rolling restart theo hướng dẫn vận hành Elasticsearch.

### Cài trong Docker image

Với Docker, nên tạo image tùy chỉnh có plugin được cài ở thời điểm build. Ví dụ:

```dockerfile
FROM docker.elastic.co/elasticsearch/elasticsearch:<elasticsearch-version>

RUN bin/elasticsearch-plugin install --batch analysis-icu
```

Thay placeholder bằng tag Elasticsearch cụ thể. Pin tag image để mọi node dùng cùng phiên bản server và plugin. Khi nâng Elasticsearch, build lại image và xác nhận plugin tương thích với phiên bản mới.

Không nên cài plugin thủ công vào một container đang chạy rồi chỉ cập nhật một node trong cluster. Các node không đồng nhất có thể khiến việc tạo index, phân tích document hoặc khôi phục shard gặp lỗi khi analyzer phụ thuộc plugin.

## 7. Định nghĩa analyzer dùng ICU

Sau khi plugin đã có trên node, có thể định nghĩa analyzer sử dụng ICU tokenizer và ICU folding.

Ví dụ:

```json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "vi_d_mapping": {
          "type": "mapping",
          "mappings": [
            "đ => d",
            "Đ => D"
          ]
        }
      },
      "analyzer": {
        "vi_icu_folded": {
          "type": "custom",
          "char_filter": [
            "vi_d_mapping"
          ],
          "tokenizer": "icu_tokenizer",
          "filter": [
            "icu_folding"
          ]
        }
      }
    }
  }
}
```

`icu_tokenizer` và `icu_folding` chỉ được nhận diện khi plugin đã được cài trên node. Nếu plugin chưa có, yêu cầu tạo index có thể thất bại với lỗi không nhận diện tokenizer hoặc token filter.

Có thể kiểm tra token:

```http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "vi_icu_folded",
  "text": [
    "Tiếng Việt",
    "Đà Nẵng",
    "Đặng Thị Hòa",
    "công nghệ thông tin"
  ]
}
```

Hãy xem token trả về và kiểm tra với tập truy vấn đại diện. Nếu ICU folding không xử lý một trường hợp cụ thể theo quy tắc nghiệp vụ, hãy bổ sung char mapping hoặc bước chuẩn hóa phù hợp thay vì giả định plugin sẽ tự xử lý mọi khác biệt.

## 8. Ánh xạ analyzer trong Spring Data Elasticsearch

Spring Data Elasticsearch khai báo index settings qua annotation `@Setting` hoặc qua cấu hình index riêng. `@Field` gắn analyzer vào thuộc tính document. Các analyzer phải tồn tại trong settings của index trước khi document được lập chỉ mục.

Ví dụ document dùng multi-field:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "articles")
@Setting(settingPath = "/elasticsearch/articles-settings.json")
public class ArticleSearchDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "vi_sensitive",
            searchAnalyzer = "vi_sensitive"
        ),
        otherFields = {
            @InnerField(
                suffix = "folded",
                type = FieldType.Text,
                analyzer = "vi_folded",
                searchAnalyzer = "vi_folded"
            )
        }
    )
    private String title;

    @Field(type = FieldType.Text, analyzer = "vi_sensitive")
    private String content;

    // Constructors, getters and setters
}
```

Trong ví dụ, file `articles-settings.json` nằm trong classpath tại `src/main/resources/elasticsearch/articles-settings.json` và chứa phần `analysis` tương ứng. Nếu chọn ICU analyzer, thay tên analyzer trong mapping và bảo đảm plugin đã được cài trên tất cả node liên quan.

Tạo index và mapping bằng index operations (API cụ thể có thể thay đổi theo phiên bản Spring Data):

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ArticleIndexInitializer {

    private final ElasticsearchOperations operations;

    public ArticleIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndex() {
        IndexOperations indexOperations =
            operations.indexOps(ArticleSearchDocument.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
```

Đoạn code minh họa việc tạo index theo settings và mapping gắn với document. Trong hệ thống thật, việc khởi tạo index nên được quản lý theo migration hoặc quy trình triển khai để tránh nhiều instance ứng dụng đồng thời tạo index và để kiểm soát phiên bản mapping.

### Tìm kiếm cả có dấu và không dấu

Với mapping multi-field ở trên, có thể tìm trên cả trường chính và subfield folded bằng `multi_match`:

```json
{
  "query": {
    "multi_match": {
      "query": "da nang",
      "fields": [
        "title^3",
        "title.folded"
      ],
      "type": "best_fields"
    }
  }
}
```

Trường `title` có boost cao hơn để ưu tiên kết quả khớp theo chính tả có dấu. Trường `title.folded` giúp tìm được nội dung có dấu khi người dùng nhập không dấu. Cần điều chỉnh boost bằng dữ liệu và hành vi tìm kiếm thực tế; không có một tỷ lệ boost phù hợp cho mọi ứng dụng.

Nếu người dùng nhập `Đà Nẵng`, truy vấn cũng có thể được phân tích theo cả hai field. Nếu nghiệp vụ cần phân biệt chặt chẽ, có thể áp dụng filter hoặc chế độ tìm kiếm riêng cho trường phân biệt dấu.

## 9. Phân đoạn từ tiếng Việt ở tầng ứng dụng

Nếu yêu cầu tìm kiếm cần nhận diện từ ghép tiếng Việt, có thể tiền xử lý nội dung trước khi index. Một pipeline đơn giản có thể tạo hai dạng dữ liệu:

```text
Văn bản gốc:
"Trường đại học công nghệ thông tin"

Trường hiển thị:
"Trường đại học công nghệ thông tin"

Trường đã phân đoạn (ví dụ minh họa):
"trường_đại_học công_nghệ_thông_tin"
```

Dạng phân đoạn là kết quả của một segmenter có từ điển; dấu gạch dưới ở đây chỉ minh họa cách giữ cụm nhiều âm tiết thành một token. Cách biểu diễn cụ thể phải theo thư viện được chọn và thống nhất ở cả lúc index lẫn lúc phân tích truy vấn.

Một thiết kế document có thể giữ cả trường gốc và trường phân đoạn:

```json
{
  "title": "Trường đại học công nghệ thông tin",
  "title_segmented": "trường_đại_học công_nghệ_thông_tin",
  "title_folded": "truong dai hoc cong nghe thong tin"
}
```

Không nên thay thế trường hiển thị bằng chuỗi đã chèn dấu phân cách. Trường gốc cần được giữ để hiển thị, highlight hoặc phục vụ truy vấn phân biệt dấu. Trường phân đoạn là một biểu diễn tìm kiếm bổ sung.

### Đồng bộ analyzer khi tìm kiếm

Analyzer dùng lúc index và analyzer dùng lúc search phải tương thích. Nếu ứng dụng tiền xử lý văn bản bằng segmenter khi index nhưng không dùng cùng logic khi query, token của truy vấn có thể không khớp token trong index.

Với analyzer có `search_analyzer`, có thể dùng cấu hình riêng cho query nếu có lý do rõ ràng, nhưng cần kiểm tra kết quả bằng `_analyze` ở cả hai chế độ. Một cách đơn giản là dùng cùng quy tắc phân đoạn và folding ở hai phía.

## 10. Synonym và stop words trong tiếng Việt

Synonym có thể cải thiện tìm kiếm khi người dùng sử dụng từ đồng nghĩa hoặc biến thể. Ví dụ, sản phẩm có thể dùng `điện thoại` trong nội dung nhưng người dùng tìm `smartphone`. Có thể cấu hình synonym filter hoặc synonym set theo tính năng Elasticsearch và phiên bản đang dùng.

Tuy nhiên, synonym tiếng Việt cần được xây dựng dựa trên ngữ cảnh. Một từ có thể có nhiều nghĩa; mở rộng quá rộng làm kết quả nhiễu. Cần xác định synonym áp dụng cho field nào, có phân biệt dấu hay không và có cần cập nhật synonym mà không reindex hay không.

Stop words cũng cần thận trọng. Các từ chức năng như `và`, `của`, `là`, `ở` xuất hiện thường xuyên, nhưng bỏ từ có thể làm thay đổi ý nghĩa của tên riêng hoặc cụm tìm kiếm. Chỉ tạo danh sách stop words sau khi đo lường truy vấn thực tế và đánh giá tác động tới phrase query.

## 11. Kiểm thử analyzer với bộ dữ liệu tiếng Việt

Không nên chỉ kiểm tra một ví dụ `tieng viet`. Hãy tạo tập kiểm thử đại diện cho các dạng nhập liệu và trường hợp biên:

| Nhóm kiểm thử | Ví dụ | Điều cần xác nhận |
|---|---|---|
| Có dấu và không dấu | `tiếng Việt` / `tieng viet` | Folded field tìm thấy tài liệu |
| Chữ đ | `Đà Nẵng` / `da nang` | `đ` được xử lý đúng theo chính sách |
| Chữ hoa | `ĐẶNG THỊ HÒA` / `đặng thị hòa` | Lowercase không làm mất token |
| Unicode NFC/NFD | `hòa` với dạng tổ hợp tương đương | Chuẩn hóa không tạo khác biệt ngoài ý muốn |
| Dấu thanh | `ma`, `má`, `mà`, `mả`, `mã`, `mạ` | Field phân biệt dấu và field folded có hành vi dự kiến |
| Từ ghép | `học sinh`, `công nghệ thông tin` | Tokenizer/segmenter đáp ứng truy vấn cụm |
| Dấu câu | `Hà Nội, Việt Nam` | Tokenizer xử lý dấu câu đúng |
| Tên riêng | `Nguyễn Ái Quốc`, `Trần Đại Nghĩa` | Kết quả không bị nhiễu quá mức |
| Ký tự hỗn hợp | `C++`, `Node.js`, mã sản phẩm | Ký hiệu cần thiết không bị mất ngoài ý muốn |

Kiểm tra token bằng `_analyze`, sau đó kiểm tra kết quả tìm kiếm với document thực. Tokenization đúng chưa chắc relevance đúng; cần đánh giá cả thứ tự kết quả, highlight, phrase matching và trường hợp truy vấn ngắn.

## 12. Thay đổi analyzer và reindex

Analyzer ảnh hưởng đến token được tạo khi index. Nếu thay analyzer của một field đã có dữ liệu, thay đổi settings không tự động phân tích lại các document cũ. Một số cấu hình analyzer cũng chỉ có thể đặt khi tạo index.

Khi thay đổi từ `standard` sang analyzer ICU, thêm field folded hoặc thay quy tắc phân đoạn từ, nên:

1. Tạo index mới với settings và mapping mới.
2. Đọc lại dữ liệu nguồn hoặc reindex theo cách phù hợp.
3. Chạy analyzer mới với tập từ tiếng Việt đại diện.
4. So sánh số token, kết quả truy vấn, thứ tự relevance và dung lượng index.
5. Đồng bộ các cập nhật phát sinh trong lúc backfill.
6. Chuyển alias sang index mới sau khi xác nhận.

Không giả định việc cập nhật `@Field(analyzer = "...")` trong code sẽ sửa mapping của index đã tồn tại. Mapping thực tế của index và mapping mà Spring Data dự kiến có thể khác nhau; cần quản lý thay đổi bằng quy trình index migration.

## 13. Chọn giải pháp theo yêu cầu

| Yêu cầu | Giải pháp có thể bắt đầu | Có cần plugin? |
|---|---|---|
| Chỉ chuyển chữ hoa thành chữ thường | `lowercase` | Không |
| Tìm kiếm không dấu cơ bản | `asciifolding` và mapping tường minh cho `đ` nếu cần | Không |
| Chuẩn hóa Unicode và tokenizer ICU | `icu_tokenizer`, `icu_folding`, `icu_normalizer` theo cấu hình | Có, `analysis-icu` |
| Phân đoạn từ ghép tiếng Việt theo từ điển | Segmenter tiếng Việt ở tầng ứng dụng hoặc plugin chuyên biệt đã đánh giá | Tùy giải pháp; ICU đơn thuần không đủ |
| Vừa tìm có dấu vừa tìm không dấu | Multi-field gồm field giữ dấu và field folded | Không bắt buộc |
| Tìm theo từ đồng nghĩa | Synonym filter/set và dữ liệu synonym được quản lý | Thường không cần plugin riêng; tùy tính năng phiên bản |

## 14. Kết luận

Tìm kiếm tiếng Việt cần có chính sách rõ ràng cho dấu thanh, chữ `đ`, Unicode NFC/NFD và phân đoạn từ. `lowercase` xử lý chữ hoa, `asciifolding` hỗ trợ tìm không dấu cơ bản, còn `analysis-icu` bổ sung các thành phần Unicode tổng quát khi cần. ICU không tự động thực hiện phân đoạn từ tiếng Việt theo từ điển.

Trong Spring Data Elasticsearch, hãy định nghĩa analyzer trong index settings, gắn analyzer vào field hoặc multi-field bằng mapping và kiểm tra token qua `_analyze`. Giữ trường phân biệt dấu cùng trường folded để cân bằng độ chính xác và khả năng tìm kiếm không dấu. Chỉ cài plugin khi tính năng cần đến nó; plugin phải đúng phiên bản và có trên mọi node liên quan. Nếu cần từ ghép, synonym hoặc xử lý ngôn ngữ chuyên sâu, hãy bổ sung segmenter/dictionary phù hợp và dùng cùng logic ở cả lúc index lẫn lúc search.
