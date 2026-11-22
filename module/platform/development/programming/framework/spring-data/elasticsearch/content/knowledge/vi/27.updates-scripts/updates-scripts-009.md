# Stored script, tái sử dụng và kiểm soát quyền thực thi

Elasticsearch cho phép lưu script trên cluster rồi gọi lại bằng ID trong các request tìm kiếm, cập nhật hoặc aggregation. Cơ chế này được gọi là stored script. Thay vì gửi toàn bộ source code trong mỗi request, ứng dụng chỉ gửi ID của script cùng các tham số đầu vào.

Stored script hữu ích khi một đoạn Painless được dùng ở nhiều nơi, cần triển khai tập trung hoặc muốn tách quyền thay đổi script khỏi quyền chạy nghiệp vụ của ứng dụng. Tuy nhiên, lưu script không tự động làm script an toàn, không loại bỏ chi phí thực thi và cũng không thay thế việc kiểm soát quyền trên index.

Các phần chính cần nắm:

- Vòng đời tạo, đọc, cập nhật và xóa stored script.
- Gọi script đã lưu bằng ID và truyền params.
- Những script context khác nhau trong Elasticsearch.
- Tái sử dụng, cache biên dịch và giới hạn hiệu năng.
- Tích hợp với Spring Data Elasticsearch và Elasticsearch Java API Client.
- Phân quyền người quản lý script, ứng dụng thực thi và giới hạn context được phép.

## 1. Stored script là gì?

Script là đoạn mã được Elasticsearch thực thi trong một context cụ thể. Elasticsearch hỗ trợ Painless làm ngôn ngữ script phổ biến; một số ngôn ngữ hoặc context khác có thể phụ thuộc cấu hình và phiên bản.

Một script có thể được khai báo trực tiếp trong request (inline script) hoặc lưu trước trên cluster (stored script).

| Loại | Cách sử dụng | Đặc điểm |
| --- | --- | --- |
| Inline script | Gửi source trong từng request. | Linh hoạt cho thử nghiệm hoặc logic chỉ dùng một lần; source được gửi cùng request. |
| Stored script | Lưu source bằng một ID, request chỉ tham chiếu ID. | Dùng lại giữa nhiều request, quản lý tập trung và tách quyền triển khai script khỏi ứng dụng. |

Ví dụ, ứng dụng cần tính giá sau giảm giá. Nếu nhiều endpoint đều dùng cùng công thức, có thể lưu script product-discount-v1 rồi truyền giá trị giảm qua params.

Stored script được lưu trong metadata của cluster và được phân phối tới các node qua cơ chế cluster state. Vì vậy, script ID là tài nguyên được quản lý ở cấp cluster, không phải file nằm trong thư mục của ứng dụng hay script riêng trên từng node.

## 2. Tạo stored script

Dùng Stored Scripts API để tạo script:

~~~http
PUT /_scripts/product-discount-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].size() == 0 ? null : doc['price'].value * (1 - params.discount)"
  }
}
~~~

Trong ví dụ:

- product-discount-v1 là ID của script.
- lang xác định ngôn ngữ, ở đây là painless.
- source chứa nội dung script.
- params.discount là tham số sẽ được truyền khi thực thi.

API trả về thông tin cho biết thao tác lưu thành công. Script chưa chạy chỉ vì được lưu; nó sẽ được thực thi khi một request tham chiếu ID trong context phù hợp.

### 2.1. Quy tắc đặt script ID

Script ID nên:

- Dễ hiểu và mô tả mục đích.
- Ổn định để các service tham chiếu.
- Có version hoặc hậu tố triển khai khi thay đổi logic.
- Không chứa dữ liệu nhạy cảm như token, mật khẩu hoặc thông tin khách hàng.
- Không được xây dựng trực tiếp từ input không đáng tin cậy.

Ví dụ tên:

| ID | Mục đích |
| --- | --- |
| product-discount-v1 | Tính giá sau giảm giá. |
| inventory-increment-v1 | Tăng tồn kho. |
| order-transition-v2 | Cập nhật trạng thái đơn hàng. |
| search-score-v1 | Điều chỉnh điểm relevance. |

Dùng ID có version giúp triển khai script mới và quay lại bản cũ dễ kiểm soát hơn. Không nên ghi đè script đang được nhiều ứng dụng sử dụng mà chưa xác định tác động.

Các script được dùng trong ví dụ ở những phần sau cần được lưu trước. Ví dụ tạo script kiểm tra khoảng giá:

~~~http
PUT /_scripts/price-in-range-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].size() != 0 && doc['price'].value >= params.minimum && doc['price'].value <= params.maximum"
  }
}
~~~

Script tính điểm:

~~~http
PUT /_scripts/search-score-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "_score * params.factor"
  }
}
~~~

Script tăng tồn kho:

~~~http
PUT /_scripts/inventory-increment-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.stock == null) { ctx._source.stock = params.amount; } else { ctx._source.stock += params.amount; }"
  }
}
~~~

Script chuyển trạng thái đơn hàng:

~~~http
PUT /_scripts/order-transition-v2
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.status == params.from) { ctx._source.status = params.to; } else { ctx.op = 'noop'; }"
  }
}
~~~

## 3. Đọc, cập nhật và xóa stored script

### 3.1. Đọc script theo ID

~~~http
GET /_scripts/product-discount-v1
~~~

Elasticsearch trả metadata của script, gồm language và source đã lưu. Có thể dùng API này để kiểm tra script ID tồn tại và nội dung đang được triển khai.

### 3.2. Cập nhật script

Gửi lại PUT cùng ID để thay source:

~~~http
PUT /_scripts/product-discount-v1
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value * (1 - params.discount) + params.shippingFee"
  }
}
~~~

Cập nhật script ID sẽ ảnh hưởng các request tiếp theo tham chiếu ID đó sau khi thay đổi được cluster chấp nhận và phân phối. Vì vậy, ghi đè trực tiếp một ID đang được production sử dụng có thể làm hành vi ứng dụng thay đổi mà không cần phát hành lại code.

Một quy trình an toàn hơn là tạo ID mới, kiểm thử, chuyển ứng dụng sang ID mới rồi mới ngừng bản cũ.

### 3.3. Xóa script

~~~http
DELETE /_scripts/product-discount-v1
~~~

Xóa script khiến những request tiếp theo tham chiếu ID đó không thể tìm thấy stored script. Trước khi xóa, cần kiểm tra các service, job, dashboard hoặc query template còn sử dụng ID hay không.

### 3.4. Vòng đời quản lý

~~~text
Viết source
    |
    v
Kiểm tra cú pháp và context
    |
    v
PUT /_scripts/<id>
    |
    v
Đọc lại và kiểm tra nội dung
    |
    v
Thử trong môi trường kiểm thử
    |
    v
Ứng dụng gọi bằng ID + params
    |
    v
Theo dõi lỗi, latency và compilation
    |
    v
Tạo version mới hoặc xóa khi không còn sử dụng
~~~

Việc tạo, cập nhật và xóa stored script là thay đổi tài nguyên cấp cluster. Nên quản lý chúng như artifact triển khai, có người sở hữu, version, kiểm thử và khả năng rollback.

## 4. Gọi stored script bằng ID và params

Request thực thi script tham chiếu ID trong thuộc tính id, sau đó truyền dữ liệu động qua params.

Ví dụ sử dụng stored script trong script field:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "match_all": {}
  },
  "script_fields": {
    "discounted_price": {
      "script": {
        "id": "product-discount-v1",
        "params": {
          "discount": 0.15
        }
      }
    }
  }
}
~~~

Script đọc giá từ doc values và tính giá sau giảm 15%. Giá trị được trả trong fields của hit; nó không sửa _source và không cập nhật document đã lưu.

Một hit có thể chứa:

~~~json
{
  "_id": "P-100",
  "_source": {
    "name": "Keyboard",
    "price": 100
  },
  "fields": {
    "discounted_price": [85.0]
  }
}
~~~

### 4.1. Params là dữ liệu đầu vào

Giữ source ổn định và truyền giá trị thay đổi qua params:

~~~json
{
  "script": {
    "id": "product-discount-v1",
    "params": {
      "discount": 0.15,
      "shippingFee": 5
    }
  }
}
~~~

Script có thể đọc params.discount và params.shippingFee. Không nối chuỗi input của người dùng vào source code để tạo script mới cho từng request.

Lợi ích của params:

- Source không phải thay đổi theo từng giá trị.
- Giảm các biến thể script không cần thiết.
- Dễ validate kiểu và miền giá trị ở ứng dụng.
- Tận dụng tốt hơn cơ chế cache biên dịch.
- Tránh biến input dữ liệu thành một phần cú pháp script.

## 5. Dùng stored script trong các thao tác khác nhau

Stored script có thể được tham chiếu ở nhiều API, miễn là script tương thích với context của thao tác.

### 5.1. Script field trong search

Dùng khi cần trả một giá trị tính toán trong response mà không cập nhật document:

~~~json
{
  "script_fields": {
    "normalized_price": {
      "script": {
        "id": "product-discount-v1",
        "params": {
          "discount": 0.1
        }
      }
    }
  }
}
~~~

Script field phù hợp với giá trị bổ sung để hiển thị hoặc tính toán theo request. Nếu giá trị được dùng thường xuyên cho filter, sort hoặc aggregation, hãy cân nhắc tính trước và lưu thành field có mapping phù hợp.

### 5.2. Script query

Có thể dùng stored script trong script query để quyết định document có khớp hay không:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "script": {
      "script": {
        "id": "price-in-range-v1",
        "params": {
          "minimum": 100,
          "maximum": 500
        }
      }
    }
  }
}
~~~

Script query có thể linh hoạt nhưng thường đắt hơn query chuyên dụng như range, term hoặc bool. Nếu logic có thể biểu diễn bằng Query DSL thông thường, hãy ưu tiên query đó để Elasticsearch tận dụng index và tối ưu hóa sẵn có.

### 5.3. Script score

Stored script có thể điều chỉnh relevance score trong script_score:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "script": {
        "id": "search-score-v1",
        "params": {
          "factor": 1.2
        }
      }
    }
  }
}
~~~

Script score chạy trong scoring context. Các biến có thể truy cập và kiểu giá trị hợp lệ phụ thuộc context; script cần trả về score số hợp lệ. Script score có thể làm tăng chi phí đáng kể khi áp dụng trên nhiều document, vì vậy nên giới hạn tập document đầu vào bằng query/filter phù hợp.

### 5.4. Update một document

Stored script có thể thay đổi _source trong update context:

~~~http
POST /products/_update/P-100
Content-Type: application/json

{
  "script": {
    "id": "inventory-increment-v1",
    "params": {
      "amount": 3
    }
  }
}
~~~

Nội dung stored script inventory-increment-v1 có thể là:

~~~painless
if (ctx._source.stock == null) {
    ctx._source.stock = params.amount;
} else {
    ctx._source.stock += params.amount;
}
~~~

Trong update context:

- ctx._source là nội dung document đang được cập nhật.
- params.amount là lượng tăng do caller truyền vào.
- Thay đổi source sẽ được ghi thành phiên bản document mới nếu update thành công.

Nếu chỉ muốn bỏ qua update khi điều kiện không thỏa, update script có thể đặt ctx.op = 'noop'. Nếu cần xóa document trong update context, ctx.op có thể được đặt theo giá trị thao tác được hỗ trợ. Hãy kiểm tra các giá trị context cụ thể của phiên bản Elasticsearch.

### 5.5. Update by query

Có thể dùng stored script để cập nhật nhiều document thỏa query:

~~~http
POST /products/_update_by_query
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "PENDING"
    }
  },
  "script": {
    "id": "order-transition-v2",
    "params": {
      "from": "PENDING",
      "to": "PROCESSING"
    }
  }
}
~~~

Update by query có thể tác động đến số lượng lớn document. Cần giới hạn query, kiểm tra số document dự kiến, cân nhắc slicing/throttling và theo dõi version conflict, timeout cùng task progress. Không chạy một script update diện rộng chỉ vì script đã được lưu và kiểm thử trên một document.

## 6. Script context: cùng source không có nghĩa chạy ở mọi nơi

Elasticsearch thực thi script trong một script context. Context xác định biến có sẵn, API được phép gọi và kiểu kết quả mà script phải trả về.

Một số context thường gặp:

| Context | Mục đích | Ví dụ dữ liệu/API |
| --- | --- | --- |
| Update | Thay đổi document trong update API. | ctx._source, params. |
| Ingest | Thay đổi document trong ingest pipeline. | ctx, params. |
| Score | Tính điểm relevance. | _score, doc, params. |
| Filter/query | Kiểm tra điều kiện khớp. | doc, params; kết quả boolean. |
| Field/script field | Tạo giá trị trả về cho một field. | doc, params, kết quả theo kiểu field. |
| Aggregation | Tính metric hoặc xử lý giá trị trong aggregation context. | Các biến theo aggregation context. |
| Sort | Tính giá trị sort bằng script. | Biến theo sort context. |

Tên context chính xác và biến được phép dùng phụ thuộc API, field type và phiên bản Elasticsearch. Không giả định mọi biến trong update context đều có mặt trong scoring context.

Ví dụ script sau chỉ phù hợp với update context:

~~~painless
ctx._source.stock += params.amount;
~~~

Trong script score, không có ctx._source theo cách trên. Thay vào đó, script thường đọc giá trị field thông qua doc['price'].value và trả về một số score.

### 6.1. Lưu ý về doc values và _source

Trong search script context, doc thường truy cập giá trị field thông qua doc values. Đây là cách phù hợp cho nhiều thao tác đọc field scalar.

_source có cấu trúc JSON gốc và không phải lúc nào cũng sẵn có hoặc phù hợp cho mọi context. Script truy cập source có thể tốn tài nguyên hơn. Với update context, ctx._source là cách phổ biến để sửa document.

Hãy chọn API theo mục tiêu:

- Đọc field để tính score/sort/filter: ưu tiên doc nếu field hỗ trợ.
- Sửa nội dung document: dùng update context và ctx._source.
- Xử lý dữ liệu trước khi index: dùng ingest context.
- Tạo giá trị trả về: cân nhắc script field hoặc runtime field tùy use case.

### 6.2. Kiểm tra context trước khi lưu

Một script hợp lệ về cú pháp vẫn có thể không chạy được trong context khác. Quy trình triển khai nên xác định rõ:

1. API nào sẽ gọi script?
2. Context của API đó là gì?
3. Biến nào có sẵn trong context?
4. Kiểu kết quả mong đợi là gì?
5. Field được truy cập có mapping hỗ trợ không?
6. Script có chạy trên document thiếu field hoặc null không?

Không dùng một script ID chung cho các context không tương thích chỉ để giảm số lượng script. Nếu logic giống nhau nhưng API/context khác nhau, có thể cần hai script riêng để biểu đạt rõ hợp đồng thực thi.

## 7. Stored script và tái sử dụng

Stored script có một số lợi ích trong vận hành:

### 7.1. Không gửi source trong mọi request

Request chỉ cần script ID và params. Điều này làm payload gọn hơn khi source dài hoặc được gọi thường xuyên.

### 7.2. Tập trung quản lý logic

Một công thức có thể được nhiều service hoặc job tham chiếu. Khi cần thay đổi, đội vận hành có thể triển khai script mới theo quy trình tập trung.

### 7.3. Tách quyền triển khai khỏi quyền ứng dụng

Ứng dụng có thể chỉ cần quyền search/update trên index. Tài khoản CI/CD hoặc quản trị được cấp quyền quản lý stored script để tạo và thay đổi code.

### 7.4. Giảm biến thể source động

Nếu mỗi request tạo source khác nhau bằng cách nhúng giá trị vào chuỗi, số script cần biên dịch có thể tăng nhanh. Stored script với params giúp source ổn định hơn.

### 7.5. Tái sử dụng không đồng nghĩa miễn phí

Stored script không làm mất chi phí chạy Painless. Mỗi document được đánh giá, cập nhật hoặc tính score vẫn tiêu tốn CPU và có thể đọc field/source. Script query hoặc script score trên tập document lớn vẫn có thể đắt.

Stored script chủ yếu cải thiện quản lý và cách phân phối source. Nó không biến một thuật toán tốn kém thành query miễn phí.

## 8. Compilation cache và giới hạn biên dịch

Elasticsearch biên dịch script và cache bản đã biên dịch để tránh lặp lại công việc này trong các request tiếp theo. Cache được quản lý trên các node và có giới hạn dung lượng/chính sách hết hạn theo cấu hình.

Một số nguyên tắc:

- Source ổn định giúp tận dụng cache tốt hơn.
- Params thay đổi giá trị đầu vào mà không cần nhúng giá trị vào source.
- Nhiều biến thể source gần giống nhau có thể gây compilation churn.
- Script ID được lưu không có nghĩa mọi context đã được biên dịch trước.
- Script được cập nhật có thể cần biên dịch lại khi được thực thi với source mới.
- Cache là tối ưu runtime; không dùng cache làm nơi lưu trữ hoặc version control cho script.

Elasticsearch có thiết lập như script.max_compilations_rate để giới hạn tốc độ biên dịch trong một khoảng thời gian. Nếu tạo quá nhiều source khác nhau, request có thể gặp lỗi giới hạn compilation. Không nên tăng giới hạn ngay khi gặp lỗi; trước tiên kiểm tra source có bị tạo động, params có bị nội suy vào source hay không và cache có bị churn không.

Có thể xem cấu hình node/cluster tương ứng theo phiên bản đang dùng. Tên, phạm vi áp dụng và khả năng thay đổi động của các setting có thể khác nhau giữa phiên bản, nên hãy đối chiếu tài liệu triển khai thực tế trước khi điều chỉnh.

## 9. Tích hợp với Spring Data Elasticsearch

Spring Data Elasticsearch dùng Elasticsearch Java API Client trong các phiên bản hiện đại. NativeQuery cho phép gắn Query DSL được tạo bằng client builder, trong đó script query có thể tham chiếu stored script.

Ví dụ tạo stored script model trong Java Client:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.json.JsonData;
import java.util.Map;

Script storedScript = Script.of(s -> s
    .stored(st -> st
        .id("price-in-range-v1")
        .params(Map.of(
            "minimum", JsonData.of(100),
            "maximum", JsonData.of(500)
        ))
    )
);
~~~

Sau đó dùng script trong script query:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query scriptQuery = Query.of(q -> q.script(s -> s
    .script(storedScript)
));

NativeQuery query = NativeQuery.builder()
    .withQuery(scriptQuery)
    .build();
~~~

Thực thi bằng ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Đoạn code thể hiện cách tạo Script dạng stored và đưa vào Query DSL. Kiểu JsonData giúp truyền giá trị params theo mô hình dữ liệu của Elasticsearch Java API Client.

### 9.1. Gọi stored script trong update

Với update, Elasticsearch Java API Client có kiểu Script dạng stored tương tự. Tùy phiên bản Spring Data Elasticsearch, UpdateQuery có thể nhận script, script type và params qua builder; tên method và kiểu tham số đã thay đổi giữa các thế hệ API.

Nguyên tắc request được gửi tới Elasticsearch tương đương:

~~~json
{
  "script": {
    "id": "inventory-increment-v1",
    "params": {
      "amount": 3
    }
  }
}
~~~

Khi dùng ElasticsearchOperations.update(...), hãy đối chiếu API UpdateQuery của dependency trong dự án và xác nhận request cuối cùng có script.id thay vì script.source. Nếu cần dùng trực tiếp Java API Client, có thể gọi Update API bằng Script union dạng stored rồi xử lý response theo service hiện có.

Không trộn class Script của Elasticsearch Java API Client với các class script legacy của Spring Data/High Level REST Client. Import đúng package theo phiên bản đang sử dụng.

### 9.2. Không để mapping entity quyết định quyền script

@Document, @Field và repository method mô tả dữ liệu hoặc thao tác truy cập. Chúng không tự cấp quyền quản lý stored script trong Elasticsearch security.

Quyền được quyết định ở cluster/index security layer và thông tin xác thực mà ứng dụng dùng khi kết nối. Vì vậy, cấu hình role phải được thiết kế độc lập với annotation Java.

## 10. Phân quyền quản lý và thực thi

Stored script là code chạy trên Elasticsearch cluster. Cần tách quyền thay đổi code khỏi quyền thực hiện nghiệp vụ thông thường.

Một mô hình phân quyền điển hình:

| Danh tính | Quyền cần có | Không nên có |
| --- | --- | --- |
| CI/CD hoặc script administrator | Quyền cluster cần thiết để tạo, đọc, cập nhật, xóa stored scripts; quyền triển khai đã được phê duyệt. | Quyền truy cập dữ liệu production rộng hơn nhu cầu triển khai nếu không cần. |
| Ứng dụng search | Quyền read trên các index được phép và quyền cần thiết cho truy vấn. | Quyền quản lý stored script hoặc quản trị cluster. |
| Ứng dụng cập nhật | Quyền write/update trên các index được phép. | Quyền sửa/xóa script toàn cluster. |
| Người vận hành | Quyền quan sát trạng thái và log theo vai trò. | Quyền thay đổi script nếu nhiệm vụ chỉ là giám sát. |

Trong Elasticsearch security, thao tác quản lý stored scripts là thao tác cấp cluster; quyền manage thường được dùng cho việc quản lý này. Đây là quyền rộng, vì vậy chỉ cấp cho danh tính triển khai đáng tin cậy và xác nhận privilege chi tiết theo phiên bản/distribution đang chạy.

Khi ứng dụng gọi search hoặc update có tham chiếu stored script, nó vẫn cần index privileges tương ứng với thao tác (ví dụ read cho search, write/update cho update). Không cấp cluster-level manage cho service chỉ vì service cần gọi một script ID đã được triển khai.

Các API quản lý script hoặc API thực thi script độc lập có thể có yêu cầu privilege riêng. Hãy kiểm tra API security requirements của endpoint cụ thể thay vì suy ra mọi endpoint _scripts đều có cùng quyền.

### 10.1. Least privilege theo index

Role của ứng dụng nên giới hạn:

- Danh sách index hoặc alias mà service được truy cập.
- Hành động read, write hoặc update đúng use case.
- Cluster privilege chỉ khi API thực sự cần.
- Các quyền quản trị script chỉ cho pipeline triển khai hoặc operator được ủy quyền.

Nếu một stored script có thể được dùng trên nhiều index, quyền index vẫn là lớp kiểm soát dữ liệu quan trọng. Không nên dựa vào việc script ID khó đoán để bảo vệ dữ liệu.

### 10.2. Script ID không phải cơ chế phân quyền

Biết ID của script không đồng nghĩa có quyền truy cập mọi index. Ngược lại, việc giấu ID cũng không thay thế security role.

Nếu ứng dụng cung cấp API để client chọn script, hãy dùng allowlist các script ID và thao tác được phép. Không nhận script ID tùy ý rồi chuyển tiếp vào Elasticsearch mà không kiểm soát.

## 11. Giới hạn loại script và context

Elasticsearch có các setting để kiểm soát loại script và context được phép thực thi. Hai setting thường cần quan tâm:

- script.allowed_types: giới hạn loại script như inline hoặc stored.
- script.allowed_contexts: giới hạn các script context được phép.

Ví dụ về ý tưởng cấu hình chỉ cho phép stored script:

~~~yaml
script.allowed_types: stored
~~~

Ví dụ giới hạn context là minh họa; tên context hợp lệ phải lấy từ phiên bản Elasticsearch và API mà cluster sử dụng:

~~~yaml
script.allowed_contexts: score, update
~~~

Khi áp dụng, cần xác nhận các script đang dùng trong search, update, ingest pipeline, sort hoặc aggregation có còn được phép không. Cấu hình quá chặt có thể làm request hợp lệ trước đó bị từ chối; cấu hình quá rộng làm tăng bề mặt thực thi.

Các setting này được cấu hình ở cấp node theo quy tắc của Elasticsearch. Phạm vi thay đổi động/tĩnh và cách rollout phụ thuộc phiên bản, vì vậy cần kiểm tra tài liệu của cluster trước khi chỉnh sửa. Thử trên môi trường staging và kiểm tra mọi script context mà ứng dụng thực sự gọi.

### 11.1. Chỉ cho phép stored scripts có kiểm duyệt

Trong hệ thống muốn ngăn ứng dụng gửi inline source tùy ý, có thể cân nhắc cấu hình script.allowed_types chỉ cho phép stored. Khi đó script mới phải được triển khai qua quy trình quản trị thay vì được nhúng tùy ý vào request.

Cần lập danh sách các API và tính năng có dùng inline script trước khi bật giới hạn. Một số thành phần tích hợp hoặc dashboard có thể đang dựa vào inline script.

### 11.2. Hạn chế context theo nhu cầu

Nếu hệ thống chỉ cần script score và update, không nhất thiết phải cho phép mọi context khác. Tuy nhiên, context names và cách các API sử dụng chúng phải được xác nhận trên phiên bản cluster thực tế.

Không coi allowed_contexts là thay thế cho role-based access control. Nó giới hạn nơi script được thực thi, còn security roles giới hạn ai được gọi API và truy cập dữ liệu nào.

## 12. Painless sandbox và giới hạn input

Painless được thiết kế để chạy script trong môi trường có giới hạn API. Điều đó giúp giảm khả năng script truy cập tài nguyên tùy ý, nhưng không có nghĩa mọi script đều an toàn hoặc rẻ.

Một script có thể gây tải cao nếu:

- Chạy trên hàng triệu document.
- Duyệt collection lớn trong mỗi lần gọi.
- Thực hiện phép tính phức tạp trong script score hoặc script query.
- Đọc source lớn cho từng document.
- Nhận params làm tăng độ phức tạp không giới hạn.
- Được gọi đồng thời bởi nhiều request.

Không nhận source code từ người dùng cuối. Không để người dùng tự chọn class, method hoặc field path tùy ý trong script. Validate params trước khi gửi:

- Kiểu dữ liệu phải đúng.
- Số phải nằm trong miền hợp lệ.
- Collection phải có giới hạn kích thước.
- Chuỗi phải có độ dài giới hạn.
- Field hoặc operation được chọn phải nằm trong allowlist.

Ví dụ, nếu discount chỉ được phép trong khoảng 0 đến 0.5, hãy kiểm tra ở tầng API/service trước khi truyền params. Không dựa vào script để thay thế validation đầu vào ở ứng dụng.

## 13. Parameterization thay cho nối chuỗi

Không nên tạo source động như sau:

~~~java
String source = "ctx._source.status = '" + userInput + "'";
~~~

Cách này trộn dữ liệu với cú pháp script, làm tăng biến thể source và có thể mở ra lỗi injection hoặc lỗi cú pháp.

Thay vào đó, giữ script cố định:

~~~painless
ctx._source.status = params.newStatus;
~~~

Và truyền dữ liệu:

~~~json
{
  "script": {
    "id": "order-transition-v2",
    "params": {
      "newStatus": "PROCESSING"
    }
  }
}
~~~

Parameterization làm rõ ranh giới giữa code và dữ liệu. Dù vậy, vẫn cần validate newStatus theo state transition hợp lệ của nghiệp vụ; params không tự bảo đảm giá trị là an toàn hoặc đúng logic.

## 14. Versioning và triển khai an toàn

Stored script có thể được nhiều service dùng chung. Thay source dưới cùng ID làm thay đổi hành vi của tất cả caller tham chiếu ID đó. Vì vậy, hãy version script như một API.

Quy trình khuyến nghị:

1. Lưu source trong repository hoặc hệ thống quản lý cấu hình có review.
2. Kiểm tra cú pháp và test script với dữ liệu đại diện.
3. Chọn script ID có version, ví dụ inventory-increment-v2.
4. Triển khai bằng tài khoản CI/CD được cấp quyền quản lý script.
5. Đọc lại script từ Elasticsearch để xác nhận source và ID.
6. Chạy thử trên index staging hoặc tập document giới hạn.
7. Cập nhật ứng dụng để tham chiếu ID mới.
8. Theo dõi lỗi, latency và kết quả nghiệp vụ.
9. Giữ ID cũ trong thời gian rollback cần thiết.
10. Xóa bản cũ sau khi xác nhận không còn caller.

Không nên xóa hoặc ghi đè script cũ trước khi xác định toàn bộ caller. Một stored script bị xóa có thể làm các request đang chạy hoặc request tiếp theo tham chiếu ID đó thất bại.

## 15. Kiểm thử script trước khi triển khai

Có thể dùng Stored Scripts API và các API kiểm tra script phù hợp với phiên bản Elasticsearch. Elasticsearch cung cấp execute API cho phép chạy script trong context xác định với dữ liệu mô phỏng/context setup; API và payload cụ thể phụ thuộc context.

Ngoài kiểm tra cú pháp, nên có test cho:

- Giá trị params hợp lệ.
- Giá trị biên như 0, số âm hoặc giới hạn tối đa.
- Field không tồn tại hoặc null.
- Document không đúng trạng thái.
- Document có cấu trúc cũ.
- Kết quả script đúng kiểu context yêu cầu.
- Update không tạo thay đổi ngoài dự kiến.
- Script score không trả NaN, infinity hoặc score không hợp lệ.
- Hiệu năng trên tập document đại diện.

Ví dụ logic update cần xử lý field stock chưa tồn tại:

~~~painless
if (ctx._source.stock == null) {
    ctx._source.stock = params.amount;
} else {
    ctx._source.stock += params.amount;
}
~~~

Nếu không xử lý null, script có thể lỗi trên document cũ chưa có field stock. Test cần có cả document mới và document legacy.

Với update by query, hãy kiểm tra query chọn đúng tập document trước khi thực thi script. Có thể chạy search cùng filter để ước lượng số document bị tác động, sau đó mới chạy update by query trong môi trường được kiểm soát.

## 16. Quan sát và xử lý lỗi

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| stored script not found | ID chưa được lưu, sai ID hoặc script đã bị xóa. | GET script theo ID và kiểm tra quy trình deploy. |
| compile error | Source sai cú pháp hoặc dùng API không hợp lệ. | Kiểm tra thông báo compiler và test trong đúng context. |
| script_exception | Lỗi runtime, null, kiểu dữ liệu hoặc field không có giá trị. | Kiểm tra document mẫu, params và null handling. |
| script_exception do context | Dùng biến/API không có trong context hiện tại. | Viết script riêng hoặc điều chỉnh theo context. |
| circuit_breaking_exception hoặc request bị từ chối | Script/aggregation/request tiêu thụ quá nhiều tài nguyên. | Giảm tập document, đơn giản hóa logic và kiểm tra concurrency. |
| Compilation rate limit exceeded | Quá nhiều source khác nhau được biên dịch trong thời gian ngắn. | Dùng source ổn định, params và kiểm tra cache churn. |
| security_exception khi PUT/DELETE | Danh tính gọi API thiếu cluster privilege cần thiết. | Cấp quyền quản lý script cho deploy identity phù hợp. |
| security_exception khi search/update | Thiếu index privilege hoặc context bị chặn. | Kiểm tra role, index privileges và script.allowed_contexts. |
| Script hoạt động ở staging nhưng lỗi production | Khác mapping, context, setting hoặc phiên bản. | So sánh cấu hình cluster và mapping trước khi rollout. |

Khi điều tra, ghi nhận script ID/version, context, index, params không nhạy cảm, request type và error type. Không ghi log bí mật hoặc dữ liệu cá nhân trong params.

## 17. Những trường hợp không nên dùng stored script

Stored script không phải lựa chọn mặc định cho mọi logic:

- Nếu có Query DSL chuẩn như term, range, bool, exists, hãy ưu tiên query chuẩn.
- Nếu giá trị tính toán được dùng liên tục cho filter/sort/aggregation, cân nhắc tính và lưu field dẫn xuất.
- Nếu logic chỉ chạy một lần để thử nghiệm, inline script trong môi trường kiểm soát có thể đơn giản hơn.
- Nếu thuật toán nặng và chạy trên nhiều document, hãy xem xét xử lý trước khi index hoặc xử lý ngoài Elasticsearch.
- Nếu cần quan hệ hoặc join phức tạp, script không phải cách thay thế mô hình dữ liệu phù hợp.
- Nếu nhiều ứng dụng cùng dùng script, cần quản lý version và tương thích trước khi thay đổi.

Stored script phù hợp nhất khi logic có thể tái sử dụng, có hợp đồng params rõ ràng, có context xác định và có người chịu trách nhiệm triển khai.

## 18. Checklist thiết kế và vận hành

Trước khi đưa stored script vào production, xác định:

1. Script ID và version có rõ ràng không?
2. Source có được review và lưu trong hệ thống quản lý mã/config không?
3. Script dùng Painless hay ngôn ngữ nào khác, và cluster có cho phép không?
4. Script chạy trong context nào?
5. Các biến/API được dùng có hợp lệ trong context đó không?
6. Params có kiểu và miền giá trị được validate không?
7. Có thể thay bằng Query DSL hoặc field đã tính trước không?
8. Script chạy trên bao nhiêu document mỗi request?
9. Có test dữ liệu null, legacy và biên không?
10. Ai được quyền PUT/GET/DELETE stored script?
11. Ứng dụng có cluster manage privilege không cần thiết không?
12. script.allowed_types và script.allowed_contexts có phù hợp không?
13. Cache và compilation rate có được theo dõi không?
14. Có kế hoạch versioning, rollout và rollback không?
15. Có giám sát latency, lỗi script và update conflicts không?

## 19. Tài liệu tham khảo

- [Elasticsearch — Stored scripts](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting-stored-scripts.html)
- [Elasticsearch — Script APIs](https://www.elastic.co/guide/en/elasticsearch/reference/current/script-apis.html)
- [Elasticsearch — Painless scripting language](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-lang-spec.html)
- [Elasticsearch — Painless contexts](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-contexts.html)
- [Elasticsearch — Script settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting-using.html)
- [Elasticsearch — Security privileges](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Spring Data Elasticsearch — NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

Stored script cho phép lưu source một lần và gọi lại bằng ID cùng params trong các context tương thích. Cơ chế này giúp quản lý logic tập trung, giảm source động và tách quyền triển khai khỏi quyền ứng dụng. Để vận hành an toàn, cần xác định rõ context, validate params, giới hạn loại/context script, phân quyền cluster/index theo least privilege, version hóa script và theo dõi chi phí thực thi/biên dịch.

