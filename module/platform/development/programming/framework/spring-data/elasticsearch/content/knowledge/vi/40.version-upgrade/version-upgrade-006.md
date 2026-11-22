# Đánh giá thay đổi mapping, converter và type hint

Khi nâng cấp Spring Data Elasticsearch hoặc thay đổi cấu trúc dữ liệu, ứng dụng có thể vẫn biên dịch và khởi động bình thường nhưng đọc sai document cũ, ghi ra định dạng mới mà phiên bản đang chạy chưa hiểu, hoặc truy vấn trên mapping không còn phù hợp. Những lỗi này thường xuất hiện khi dữ liệu đã tồn tại lâu hơn vòng đời của một phiên bản ứng dụng.

Vì vậy, review một thay đổi mapping, converter hoặc type hint cần xem đồng thời ba hợp đồng:

- **Mapping contract:** Elasticsearch lưu và index từng field như thế nào.
- **Conversion contract:** Spring Data chuyển đổi kiểu Java thành document và đọc document trở lại như thế nào.
- **Type metadata contract:** Spring Data xác định class cụ thể nào cần được tạo khi đọc document đa hình.

Các hợp đồng này phải tương thích với dữ liệu đã lưu và với những phiên bản ứng dụng có thể cùng chạy trong quá trình rollout. Một thay đổi đúng với document mới vẫn có thể phá dữ liệu cũ hoặc làm hỏng rolling deployment.

## 1. Vì sao cần review trước khi nâng cấp?

Giả sử phiên bản ứng dụng hiện tại lưu sản phẩm như sau:

~~~json
{
  "_class": "com.example.catalog.ProductDocument",
  "id": "p-100",
  "price": "USD:1299",
  "status": "ACTIVE"
}
~~~

Sau khi nâng cấp, nhóm phát triển muốn:

- Đổi field price từ chuỗi sang object có amount và currency.
- Đổi status từ keyword sang một cấu trúc khác.
- Di chuyển class ProductDocument sang package mới.
- Đổi analyzer cho field name.
- Tắt type hint mặc định để document gọn hơn.

Mỗi thay đổi có thể ảnh hưởng một lớp khác nhau. Nếu chỉ kiểm tra code mới với document vừa ghi, ta chưa biết code mới có đọc được dữ liệu cũ hay không. Nếu rolling deployment vẫn còn instance phiên bản cũ, ta cũng phải xem phiên bản cũ có hiểu dữ liệu do phiên bản mới ghi ra hay không.

Một thay đổi dữ liệu cần được đánh giá theo cả ba chiều:

| Chiều đánh giá | Câu hỏi |
|---|---|
| Dữ liệu đã tồn tại | Phiên bản mới có đọc được document cũ không? |
| Dữ liệu mới | Phiên bản cũ hoặc consumer cũ có đọc được document mới không? |
| Mapping/index | Elasticsearch có thể áp dụng thay đổi trên index hiện tại hay cần index mới và reindex? |

Không mặc định rằng đổi annotation Java sẽ tự thay đổi mapping của index đang chạy. Mapping thực tế đã được lưu trên Elasticsearch và có vòng đời độc lập với class Java.

## 2. Xác định phiên bản và trạng thái hiện tại

Trước khi đánh giá thay đổi, cần biết chính xác ứng dụng và cluster đang dùng phiên bản nào:

- Spring Boot version.
- Spring Data release train và Spring Data Elasticsearch version.
- Elasticsearch Java Client version.
- Elasticsearch cluster version.
- Phiên bản mapping/index template hiện tại.
- Phiên bản converter và type metadata đã dùng để tạo dữ liệu.
- Các ứng dụng hoặc worker khác có cùng đọc/ghi index không.

Spring Data Elasticsearch có thay đổi API theo release train. Annotation, enum, constructor của custom conversions, query builder và cách cấu hình client có thể khác nhau giữa các phiên bản. Không sao chép ví dụ từ một release khác rồi giả định code tương thích.

Hãy đọc dependency tree hoặc dependency lock của dự án và kiểm tra API trong Javadoc tương ứng. Với cluster, lấy thông tin trực tiếp từ endpoint thông tin phiên bản:

~~~http
GET /
~~~

Không chỉ nhìn version trong file cấu hình. Dependency management của Spring Boot có thể quyết định phiên bản thực tế được resolve.

## 3. Phân loại thay đổi mapping

Mapping mô tả cách Elasticsearch hiểu và index field. Có thay đổi thường tương đối an toàn, có thay đổi chỉ áp dụng được cho index mới.

| Thay đổi | Tác động thường gặp | Hướng xử lý |
|---|---|---|
| Thêm field mới | Document cũ không có field | Thường có thể thêm mapping, cần chấp nhận giá trị thiếu |
| Thêm multi-field | Document cũ chưa có term cho subfield mới | Thường cần reindex để backfill |
| Đổi field type | Dữ liệu hiện tại không tương thích mapping mới | Tạo index mới và reindex |
| Đổi analyzer | Token đã index không tự được tạo lại | Tạo field/index mới và reindex |
| Đổi object thành nested | Cách index và query thay đổi | Tạo index mới và reindex |
| Đổi date format | Giá trị cũ có thể không parse được | Kiểm tra dữ liệu, migration hoặc field mới |
| Đổi dense_vector dimensions | Vector cũ không khớp schema mới | Index mới và tạo lại embedding |
| Thay index settings | Một số setting cần đóng index hoặc chỉ có hiệu lực khi tạo index | Kiểm tra setting cụ thể và kế hoạch reindex |

Đây là phân loại định hướng, không thay thế tài liệu mapping của phiên bản Elasticsearch đang chạy. Một số parameter có thể cập nhật trong điều kiện nhất định; một số parameter khác chỉ đặt được khi tạo index. Review cần kiểm tra đúng parameter, field type và version thay vì kết luận chung rằng mọi mapping đều bất biến.

## 4. Thay đổi additive: thêm field mới

Thêm một field mới thường ít rủi ro hơn đổi kiểu field hiện có:

~~~json
PUT /products-read/_mapping
{
  "properties": {
    "searchKeywords": {
      "type": "keyword"
    }
  }
}
~~~

Document cũ không có searchKeywords vẫn có thể tồn tại. Khi đọc document cũ, ứng dụng cần chấp nhận field null hoặc vắng mặt. Khi truy vấn, các document cũ có thể không khớp filter hoặc aggregation dựa trên field mới cho tới khi được backfill.

### 4.1. Thêm field không đồng nghĩa đã có dữ liệu

Sau khi thêm mapping, document cũ không tự nhận giá trị mới. Ví dụ ứng dụng thêm categoryPath để hỗ trợ filter theo đường dẫn danh mục. Mapping có thể đã tồn tại nhưng categoryPath trong các document cũ vẫn chưa có.

Kế hoạch cần chỉ rõ:

- Field mới là optional trong giai đoạn chuyển tiếp hay bắt buộc.
- Query có xử lý document thiếu field không.
- Khi nào backfill dữ liệu cũ.
- Khi nào có thể bỏ logic tương thích với document thiếu field.

### 4.2. Dynamic mapping

Nếu bật dynamic mapping, Elasticsearch có thể tự tạo mapping khi gặp field mới. Điều này tiện cho dữ liệu linh hoạt nhưng có rủi ro:

- Giá trị đầu tiên quyết định kiểu field.
- Dữ liệu không đồng nhất có thể làm mapping ngoài ý muốn.
- Field phát sinh nhiều có thể tạo mapping explosion.
- Tên field do người dùng điều khiển có thể làm schema khó kiểm soát.

Với field quan trọng, nên khai báo mapping rõ ràng hoặc dùng dynamic templates có chủ đích. Không để một document đầu tiên chứa giá trị sai kiểu quyết định mapping cho toàn index.

## 5. Đổi field type là thay đổi breaking

Giả sử field price hiện là keyword:

~~~json
{
  "price": {
    "type": "keyword"
  }
}
~~~

Nhóm phát triển muốn đổi thành numeric để range query và sort:

~~~json
{
  "price": {
    "type": "scaled_float",
    "scaling_factor": 100
  }
}
~~~

Không thể coi đây là thay đổi annotation đơn giản trên cùng index. Elasticsearch không cho đổi tùy ý field type đã được tạo với dữ liệu. Cần tạo index mới với mapping mới, chuyển đổi dữ liệu và reindex.

Quy trình thường là:

1. Tạo index version mới với mapping mong muốn.
2. Đọc document từ index cũ hoặc nguồn dữ liệu có thẩm quyền.
3. Chuyển đổi price sang representation numeric.
4. Index vào index mới.
5. Kiểm tra document lỗi, giá trị null, rounding và query.
6. Đồng bộ các thay đổi phát sinh trong khi backfill.
7. Chuyển alias sang index mới.

### 5.1. Cẩn thận với tiền tệ

Đổi chuỗi tiền sang số cần định nghĩa currency và scale. Giá trị `USD:1299` có thể biểu diễn 12.99 USD nếu amount là minor units. Không được parse thành 1299.0 rồi coi là cùng đơn vị.

Nếu index chứa nhiều currency, range query theo price có thể không có ý nghĩa nếu không chuẩn hóa tiền tệ. Có thể lưu amountMinor và currency riêng, hoặc quy đổi theo một currency chuẩn với tỷ giá và thời điểm rõ ràng.

Với scaled_float, scaling factor xác định độ phân giải lưu trữ. Kiểm tra cách làm tròn và giới hạn giá trị trước khi migrate.

## 6. Đổi analyzer hoặc normalizer

Analyzer ảnh hưởng đến token được tạo ra lúc index và lúc search. Khi thay analyzer, việc cập nhật mapping không tự chạy lại quá trình phân tích cho những term đã được index.

Ví dụ field name trước đây dùng standard analyzer, nay cần lowercase và asciifolding. Query mới có thể được phân tích theo analyzer mới nhưng document cũ vẫn được index bằng token cũ. Kết quả search có thể không nhất quán.

Các lựa chọn:

- Tạo field mới với analyzer mới, backfill/reindex rồi chuyển query sang field đó.
- Tạo index version mới và reindex toàn bộ dữ liệu.
- Với một số thay đổi settings được hỗ trợ, đóng index, cập nhật setting rồi mở lại; tuy vậy, dữ liệu đã index vẫn cần reindex nếu tokenization thay đổi.

Không chỉ kiểm tra analyzer bằng Analyze API trên chuỗi mẫu. Cần kiểm tra cả document đã index và truy vấn thực tế để xác nhận token index-time/search-time tương thích.

### 6.1. Thay normalizer cho keyword

Normalizer tác động cách chuẩn hóa keyword field, ví dụ lowercase. Nó có thể ảnh hưởng exact match, aggregation và sort. Cần đánh giá cùng các query đang dùng field đó. Không giả định thay normalizer sẽ tự cập nhật term của document cũ.

### 6.2. Multi-field

Thêm multi-field như name.keyword có thể giúp sort hoặc aggregation theo giá trị nguyên bản. Nhưng document cũ chưa có term được index cho subfield mới. Cần backfill/reindex để query trên subfield hoạt động đầy đủ với dữ liệu cũ.

## 7. Thay object, nested và cấu trúc JSON

Giả sử variants hiện là object array thông thường:

~~~json
{
  "variants": [
    { "color": "black", "size": "M" },
    { "color": "white", "size": "L" }
  ]
}
~~~

Nếu query cần bảo đảm color và size thuộc cùng một variant, có thể cần nested mapping. Đổi từ object sang nested làm thay đổi cách Elasticsearch index và query các phần tử. Cần tạo index mới và reindex dữ liệu.

Review phải kiểm tra query cũ có dùng nested query/aggregation chưa, response có thay đổi cấu trúc không, converter Java có map collection và nested object đúng không, document cũ có field null/missing hoặc shape khác không, và số lượng nested object có ảnh hưởng giới hạn/hiệu năng không.

Không chọn nested chỉ vì JSON có mảng object. Thay đổi này nên xuất phát từ ngữ nghĩa truy vấn cần bảo toàn quan hệ giữa các field trong cùng phần tử.

## 8. Thay đổi mapping cho dense_vector

Dense vector có một hợp đồng riêng:

- Số chiều.
- Kiểu vector và cách biểu diễn.
- Similarity function.
- Cấu hình index/ANN.
- Embedding model và phiên bản model.

Nếu model mới thay đổi dimensions, index hiện tại không thể nhận vector có kích thước mới trong cùng field đã khai báo dims cũ. Nếu dimensions giữ nguyên nhưng embedding model thay đổi, vector cũ và vector mới vẫn có thể thuộc hai embedding space khác nhau.

Do đó, thay model hoặc dimensions thường cần:

1. Tạo index version mới.
2. Cập nhật mapping dense_vector.
3. Re-embed toàn bộ nội dung theo model mới.
4. Kiểm tra vector dimensions và metadata model.
5. Đánh giá retrieval quality.
6. Chuyển alias hoặc query routing khi index mới sẵn sàng.

Không chỉ đổi dims trong annotation rồi chạy save. Mapping thực tế của index cũ vẫn còn và dữ liệu cũ không tự được chuyển sang embedding space mới.

## 9. Review converter: dữ liệu lưu và dữ liệu Java

Converter định nghĩa cách chuyển đổi giữa kiểu Java và representation trong Elasticsearch document.

Một custom converter có thể chuyển value object thành string hoặc number, chuyển string lưu trữ thành enum/value object, chuẩn hóa date/time, chuyển kiểu ID hoặc đọc cấu trúc legacy.

Trong Spring Data, converter có thể được đánh dấu theo chiều:

- `@WritingConverter`: chuyển Java value sang dạng ghi.
- `@ReadingConverter`: chuyển dữ liệu đọc được thành kiểu Java.

Ví dụ:

~~~java
public record Money(long minorUnits, String currency) {
}

@WritingConverter
public class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + ":" + source.minorUnits();
    }
}

@ReadingConverter
public class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Invalid money value");
        }
        return new Money(
                Long.parseLong(parts[1]),
                parts[0]
        );
    }
}
~~~

Đăng ký custom conversions trong cấu hình Spring Data Elasticsearch theo API của phiên bản đang dùng:

~~~java
@Bean
ElasticsearchCustomConversions elasticsearchCustomConversions() {
    return new ElasticsearchCustomConversions(
            List.of(
                    new MoneyToStringConverter(),
                    new StringToMoneyConverter()
            )
    );
}
~~~

Khi review, phải xác nhận converter thực sự được đăng ký vào Elasticsearch mapping converter. Tạo một bean Converter riêng nhưng không kết nối nó với ElasticsearchCustomConversions không bảo đảm Spring Data sẽ sử dụng.

## 10. Đánh giá thay đổi format converter

Giả sử phiên bản cũ lưu:

~~~json
{
  "price": "USD:1299"
}
~~~

Phiên bản mới muốn lưu:

~~~json
{
  "price": {
    "currency": "USD",
    "minorUnits": 1299
  }
}
~~~

Đây là thay đổi representation, không chỉ là đổi class Money. Cần xem cả reader và writer:

| Phiên bản | Đọc format cũ | Đọc format mới | Ghi format cũ | Ghi format mới |
|---|---:|---:|---:|---:|
| App cũ | Có | Có thể không | Có | Không |
| App mới | Phải có trong giai đoạn migration | Có | Tùy rollout | Có sau cutover |

Nếu instance cũ còn chạy trong lúc instance mới ghi document, instance cũ có thể lỗi khi đọc object mới. Vì vậy, rollout phải kiểm soát thời điểm chuyển writer.

### 10.1. Chiến lược expand-and-contract

Một cách triển khai an toàn hơn:

**Giai đoạn 1 — Expand reader:** triển khai phiên bản đọc được cả format cũ và mới, nhưng vẫn ghi format cũ. Tất cả instance và worker cần tương thích trước khi thay đổi writer.

**Giai đoạn 2 — Switch writer:** chuyển writer sang format mới. Reader mới vẫn đọc được document cũ nên dữ liệu chưa migrate vẫn hoạt động.

**Giai đoạn 3 — Backfill:** chuyển document cũ sang format mới hoặc reindex sang index mới. Theo dõi lỗi parse và số document còn format cũ.

**Giai đoạn 4 — Contract:** sau khi xác nhận không còn dữ liệu cũ và không còn consumer cũ, có thể bỏ hỗ trợ format legacy trong một release sau.

Nếu không thể triển khai reader tương thích trước, cần dùng index mới và cutover đồng bộ thay vì trộn hai format trong một index.

### 10.2. Dual-read không đồng nghĩa dual-write tùy tiện

Reader có thể hỗ trợ nhiều format để phục vụ migration. Writer nên có một format chuẩn ở mỗi giai đoạn. Ghi đồng thời hai field hoặc hai representation có thể tạo trạng thái không nhất quán nếu chỉ một field được cập nhật.

Nếu buộc phải dual-write, cần xác định field nào là nguồn, cách xử lý lỗi một phần, thời điểm ngừng ghi field cũ và cách kiểm tra hai giá trị đồng nhất.

### 10.3. Converter phải xử lý dữ liệu biên

Kiểm tra:

- Field không tồn tại.
- Giá trị null.
- Chuỗi rỗng hoặc sai delimiter.
- Amount không parse được.
- Currency không hợp lệ.
- Date không có timezone.
- Enum đã bị đổi tên hoặc xóa.
- Number vượt giới hạn kiểu Java.
- Document có format từ release cũ hơn nhiều phiên bản.

Không âm thầm chuyển dữ liệu lỗi thành giá trị mặc định. Cần log đủ metadata để điều tra mà không lộ nội dung nhạy cảm, và có chiến lược quarantine/repair cho document không đọc được.

## 11. Type hint là gì?

Khi Spring Data Elasticsearch ghi một object, mapping converter có thể lưu metadata để biết kiểu Java cụ thể khi đọc lại. Metadata mặc định thường nằm trong field `_class` trong `_source`.

Ví dụ:

~~~json
{
  "_class": "com.example.catalog.ProductDocument",
  "id": "p-100",
  "name": "Keyboard"
}
~~~

Type hint hữu ích khi có class con kế thừa một base class, một property khai báo interface hoặc abstract type, một property chứa object polymorphic, hoặc Spring Data cần khôi phục kiểu cụ thể khi đọc document.

Type hint là metadata của Spring Data trong document source. Nó không phải Elasticsearch mapping type cũ như `_type` đã bị loại bỏ khỏi Elasticsearch từ phiên bản 7. Không nhầm `_class` với `_type`.

## 12. @TypeAlias và tên class ổn định

Nếu dùng tên class đầy đủ trong `_class`, đổi package hoặc rename class có thể làm dữ liệu cũ chứa tên class không còn được resolve.

Spring Data hỗ trợ `@TypeAlias` để dùng một alias ổn định:

~~~java
@Document(indexName = "products-read")
@TypeAlias("product")
public class ProductDocument {
    @Id
    private String id;

    private String name;
}
~~~

Document có thể lưu metadata dạng:

~~~json
{
  "_class": "product",
  "id": "p-100",
  "name": "Keyboard"
}
~~~

Alias tách metadata khỏi tên package/class Java. Khi đổi package hoặc refactor tên class, alias có thể tiếp tục giữ nguyên nếu mapping context của Spring Data biết alias đó thuộc kiểu nào.

### 12.1. Mapping context phải nhận diện alias

`@TypeAlias` không phải phép biến đổi tự động trên mọi document. Spring Data cần biết entity tương ứng với alias trong mapping context. Hãy bảo đảm entity được scan/đăng ký hoặc được khai báo trong cấu hình mapping phù hợp trước khi đọc document chứa alias.

Nếu alias không được nhận diện, việc deserialize có thể thất bại hoặc không thể xác định subtype cần tạo. Test trên Spring context thật, không chỉ instantiate class và kiểm tra annotation.

### 12.2. Đổi alias là migration dữ liệu

Nếu alias cũ là `product-v1` và muốn đổi thành `catalog-product`, cần xem document đã lưu:

- Reader mới có nhận alias cũ không?
- Writer mới sẽ ghi alias nào?
- Có consumer khác đọc cùng index không?
- Có thể giữ alias cũ như legacy mapping trong một thời gian không?
- Khi nào backfill metadata cũ?

Không đổi alias trong code rồi giả định document cũ tự thay đổi. `_class` đã nằm trong `_source` của các document hiện có.

## 13. Khi nào nên tắt type hint?

Type hint có ích cho polymorphic mapping nhưng có thể không cần thiết với document chỉ được đọc thành một class cụ thể và không chứa property đa hình.

Một số phiên bản Spring Data Elasticsearch cho phép cấu hình `writeTypeHint` trên `@Document`, ví dụ:

~~~java
@Document(
        indexName = "products-read",
        writeTypeHint = WriteTypeHint.FALSE
)
public class ProductSearchDocument {
    @Id
    private String id;

    private String name;
}
~~~

API và enum hỗ trợ cần được xác nhận trong release train đang dùng. Đừng áp dụng snippet này nếu phiên bản dependency không có thuộc tính tương ứng.

Trước khi tắt type hint, đánh giá:

- Document có dùng inheritance/polymorphic property không?
- Reader có thể suy ra subtype từ field nghiệp vụ khác không?
- Có document cũ vẫn chứa `_class` không?
- Có consumer khác phụ thuộc `_class` không?
- Có cần custom type mapper để đọc dữ liệu legacy không?

Nếu bỏ type hint trong writer, document mới sẽ không có metadata đó theo cấu hình. Điều này không tự xóa `_class` khỏi document cũ. Reader vẫn có thể gặp cả document có và không có hint trong giai đoạn chuyển tiếp.

### 13.1. Không xóa _class bằng cách sửa source tùy tiện

Không nên xóa `_class` khỏi document hàng loạt trước khi xác định reader có cần nó hay không. Với property đa hình, thiếu type hint có thể khiến Spring Data không biết subtype cần khởi tạo.

Nếu muốn loại bỏ metadata, hãy chứng minh tất cả reader có thể đọc document mới, xử lý được document cũ và không còn phụ thuộc polymorphic resolution. Sau đó mới lên kế hoạch migration/cleanup.

## 14. Type hint trong nested object và polymorphism

Type metadata có thể được ghi cho root document và các complex property tùy mapping converter/cấu hình. Ví dụ:

~~~java
public interface PaymentMethod {
}

public class CardPayment implements PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String bankCode;
}

@Document(indexName = "orders-read")
public class OrderDocument {
    @Id
    private String id;

    private PaymentMethod paymentMethod;
}
~~~

Khi đọc OrderDocument, Spring Data cần biết property paymentMethod thực tế là CardPayment hay BankTransfer. Type hint hoặc một custom conversion/discriminator strategy có thể cung cấp thông tin đó.

Nếu loại bỏ type hint mà không có discriminator khác, property interface/abstract có thể không deserialize được. Nếu có field nghiệp vụ như paymentMethodType, hãy kiểm tra cách custom converter hoặc mapper sử dụng field đó để tạo subtype.

Đừng nhầm discriminator nghiệp vụ với `_class`: chúng có thể cùng tồn tại nhưng có mục đích và contract khác nhau.

## 15. Review ảnh hưởng của converter và type hint tới dữ liệu cũ

Khi đổi converter hoặc type metadata, cần kiểm tra document thực tế đã tồn tại:

| Dữ liệu cũ | Thay đổi mới | Rủi ro |
|---|---|---|
| price là string | Converter mới chỉ đọc object | Document cũ không deserialize được |
| enum lưu bằng tên cũ | Enum bị rename | Reader không tìm thấy enum constant |
| date lưu không có timezone | Reader mới yêu cầu offset | Parse sai hoặc lỗi |
| `_class` là tên package đầy đủ | Class chuyển package | Type resolution thất bại |
| `_class` là alias cũ | Alias đổi | Mapping context không nhận alias cũ |
| Nested object có type hint | Writer mới tắt type hint | Reader không khôi phục được subtype |
| Vector có model metadata cũ | Model mới được dùng | Document và query vector không cùng embedding space |

Đừng chỉ kiểm tra một document vừa tạo từ phiên bản mới. Hãy giữ fixture đại diện cho dữ liệu của các release được hỗ trợ và kiểm tra chúng bằng reader mới.

## 16. Kiểm tra mapping thực tế và dữ liệu mẫu

Các API thường dùng khi review:

Lấy mapping:

~~~http
GET /products-read/_mapping
~~~

Lấy settings:

~~~http
GET /products-read/_settings
~~~

Kiểm tra field capabilities trên một hoặc nhiều index:

~~~http
GET /products-read/_field_caps?fields=price,status,name
~~~

Field capabilities giúp phát hiện cùng một field có type không thống nhất giữa nhiều index được truy vấn qua alias. Ví dụ một index khai báo price là keyword, index khác là scaled_float; alias trỏ cả hai có thể gây lỗi hoặc query semantics không nhất quán.

Kiểm tra index template và component template nếu ứng dụng dùng template:

~~~http
GET /_index_template
~~~

Với template mới, có thể dùng API simulate phù hợp phiên bản để xem settings/mapping cuối cùng sẽ được áp dụng. Cần kiểm tra template priority và component template composition; template khác có thể ghi đè cấu hình dự kiến.

Lấy một số document đại diện:

~~~http
GET /products-read/_search
{
  "size": 5,
  "_source": [
    "id",
    "price",
    "status",
    "_class"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Mục tiêu là xác định representation thật đang lưu, bao gồm field thiếu, null, format legacy và type hint. Dữ liệu mẫu cần lấy từ các nhóm tuổi dữ liệu khác nhau, không chỉ document mới nhất.

## 17. Test compatibility giữa các phiên bản

Một bộ test nâng cấp nên bao gồm nhiều hướng:

### 17.1. Reader mới đọc document cũ

Lưu fixture JSON từ phiên bản cũ, sau đó dùng mapping converter/ElasticsearchOperations của phiên bản mới để đọc. Kiểm tra field cũ được map đúng, converter đọc được format legacy, enum/date/value object không bị sai, `_class` hoặc alias cũ được resolve và field optional được xử lý như dự kiến.

### 17.2. Writer mới tạo document đúng

Dùng phiên bản mới ghi một document và kiểm tra `_source`, mapping và type hint. Xác nhận representation đúng contract đã định.

### 17.3. Reader cũ có đọc được document mới không?

Test này quan trọng khi rolling deployment có thể còn instance cũ. Nếu writer mới tạo format mà reader cũ không hiểu, phải:

- Triển khai reader tương thích trước.
- Hoãn switch writer cho tới khi reader cũ đã được thay thế.
- Hoặc dùng index version mới và tách routing.

Không phải mọi thay đổi đều cần reader cũ hiểu dữ liệu mới. Nhưng rollout phải bảo đảm instance cũ không đọc nhầm index hoặc document mới.

### 17.4. Integration test trên đúng major version

Dùng Testcontainers hoặc môi trường test tương đương với Elasticsearch version đang hỗ trợ. Pin image version, không dùng tag latest. Kiểm tra cả mapping, converter, type hint, query và reindex behavior cần thiết.

Nếu ứng dụng hỗ trợ nhiều cluster version, chạy compatibility matrix cho những version nằm trong support policy. Không cần test mọi version lịch sử đã hết hỗ trợ.

## 18. Reindex và alias cutover

Khi thay đổi breaking như field type, analyzer, nested structure hoặc vector dimensions, thường cần index mới.

Ví dụ:

~~~http
PUT /products-v2
{
  "mappings": {
    "properties": {
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Sau đó có thể dùng Reindex API nếu source và target representation tương thích:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Nếu converter hoặc format cần chuyển đổi phức tạp, reindex trực tiếp có thể không đủ. Khi đó dùng application migration job hoặc pipeline có script phù hợp để parse và chuyển dữ liệu. Với dữ liệu lớn, chạy theo batch, lưu checkpoint, kiểm tra lỗi từng document và có khả năng tiếp tục.

### 18.1. Đồng bộ thay đổi trong lúc reindex

Nếu dữ liệu vẫn được ghi vào index cũ trong lúc reindex, các cập nhật mới có thể không có trong index đích hoặc bị ghi đè bởi bản sao cũ.

Các chiến lược thường dùng:

- Tạm dừng writer trong thời gian ngắn và thực hiện final catch-up.
- Dùng outbox/CDC để replay các thay đổi sau watermark.
- Dual-write có kiểm soát trong một giai đoạn ngắn với idempotency và versioning.

Chọn chiến lược theo write volume và khả năng chấp nhận downtime. Không dùng dual-write đơn giản trong request path nếu không có cách xử lý trường hợp chỉ một index ghi thành công.

### 18.2. Chuyển alias

Sau khi index mới đã được kiểm tra, chuyển alias bằng một request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    }
  ]
}
~~~

Alias giúp ứng dụng không cần biết tên index versioned. Nếu có write alias, cần cấu hình write index rõ ràng và kiểm tra các thao tác ghi đang trỏ đúng index.

Giữ index cũ trong thời gian rollback. Đừng xóa ngay sau cutover khi chưa xác nhận truy vấn, mapping và dữ liệu production hoạt động ổn định.

## 19. Quy trình rollout expand-and-contract

Một rollout tương thích thường chia thành các giai đoạn:

~~~text
1. Expand readers
   Đọc được dữ liệu cũ và mới
          |
          v
2. Deploy compatible application
   Tất cả instance/consumer hiểu schema mới
          |
          v
3. Switch writers
   Bắt đầu ghi representation mới
          |
          v
4. Backfill / reindex
   Chuyển dữ liệu cũ
          |
          v
5. Verify
   Không còn dữ liệu legacy
          |
          v
6. Contract
   Bỏ hỗ trợ format/type metadata cũ
~~~

Đối với mapping breaking, các giai đoạn này có thể diễn ra trên index version mới thay vì cùng index. Điểm cốt lõi là không để writer tạo dữ liệu mà reader đang hoạt động không hiểu.

## 20. Lập kế hoạch rollback

Rollback code không tự động rollback dữ liệu đã ghi. Nếu phiên bản mới đã đổi converter và ghi format mới, quay lại binary cũ có thể làm binary đó không đọc được dữ liệu mới.

Trước khi rollout, xác định:

- Binary cũ có đọc được format mới không.
- Index cũ có còn nguyên và cập nhật tới đâu.
- Có thể chuyển alias trở lại không.
- Các event/outbox phát sinh trong migration được replay thế nào.
- Dữ liệu ghi trong thời gian cutover có bị mất khi quay lại không.
- Có cần giữ reader tương thích trong nhiều release không.

Với thay đổi breaking, rollback thường an toàn hơn khi giữ index cũ và định tuyến app trở lại index đó, nhưng phải xử lý các write phát sinh sau khi bắt đầu cutover. Không coi alias switch là rollback đầy đủ nếu dữ liệu mới chỉ có trong index mới.

## 21. Những lỗi review thường gặp

| Lỗi | Hậu quả | Cách review đúng |
|---|---|---|
| Chỉ đổi @Field type rồi deploy | Mapping hiện tại vẫn giữ type cũ | Đọc mapping thật, tạo index mới nếu cần |
| Đổi analyzer mà không reindex | Document cũ giữ token cũ | Reindex hoặc backfill field mới |
| Đổi converter chỉ test dữ liệu mới | Document cũ không đọc được | Test fixture từ các release cũ |
| Rename class nhưng không xét _class | Type resolution lỗi | Dùng alias ổn định hoặc migration |
| Tắt type hint mà không kiểm tra polymorphism | Không tạo được subtype khi đọc | Test root và nested property |
| Chỉ kiểm tra annotation Java | Index template hoặc index cũ có thể khác | Kiểm tra mapping/settings thực tế |
| Deploy writer mới trước reader mới | Instance cũ lỗi khi đọc dữ liệu mới | Expand reader trước, switch writer sau |
| Reindex trong lúc ghi nhưng không replay thay đổi | Index mới thiếu hoặc stale document | Watermark, CDC/outbox hoặc controlled pause |
| Xóa index cũ ngay sau cutover | Mất đường rollback | Giữ index cũ theo retention plan |
| Chỉ so sánh số document | Không phát hiện sai converter hoặc mapping | Kiểm tra field, version, sample query và type metadata |

## 22. Checklist review một thay đổi

**Mapping**

- [ ] Đã biết mapping/settings/template thực tế của index đang chạy.
- [ ] Đã phân loại thay đổi là additive hay breaking.
- [ ] Đã kiểm tra field type, analyzer, normalizer, nested/object, date và vector dimensions.
- [ ] Đã xác định document cũ có field mới hay cần backfill.
- [ ] Đã xác định có cần index version mới và reindex không.

**Converter**

- [ ] Đã kiểm tra cả chiều đọc và ghi.
- [ ] Đã xác định representation cũ và mới.
- [ ] Reader mới đọc được dữ liệu cũ trong giai đoạn chuyển tiếp.
- [ ] Đã xử lý null, missing, malformed, enum và date/time.
- [ ] Đã kiểm tra converter được đăng ký vào ElasticsearchCustomConversions.
- [ ] Đã xác định thời điểm có thể bỏ hỗ trợ format legacy.

**Type hint**

- [ ] Đã kiểm tra _class trong document thật.
- [ ] Đã xác định class rename/package move ảnh hưởng dữ liệu ra sao.
- [ ] Đã cân nhắc @TypeAlias và mapping context.
- [ ] Đã kiểm tra root document và nested polymorphic property.
- [ ] Nếu tắt type hint, đã chứng minh reader không còn phụ thuộc metadata đó.

**Rollout và vận hành**

- [ ] Reader mới được triển khai trước writer mới khi cần.
- [ ] Có migration/reindex và checkpoint.
- [ ] Có xử lý write phát sinh trong lúc backfill.
- [ ] Có kiểm tra dữ liệu và query sau cutover.
- [ ] Có kế hoạch rollback cả code lẫn index/dữ liệu.
- [ ] Index cũ được giữ đủ lâu theo chính sách rollback.

## 23. Kết luận

Đánh giá thay đổi mapping, converter và type hint là đánh giá khả năng tương thích giữa code mới, dữ liệu đã lưu và các phiên bản ứng dụng cùng hoạt động trong quá trình nâng cấp. Mapping quyết định Elasticsearch index field ra sao; converter quyết định representation giữa Java và document; type hint giúp Spring Data khôi phục kiểu cụ thể, đặc biệt với dữ liệu đa hình.

Thêm field thường có thể triển khai theo hướng additive, nhưng đổi field type, analyzer, nested structure hoặc dense vector dimensions thường cần index mới và reindex. Thay converter phải xem cả dữ liệu cũ lẫn mới, còn thay _class hoặc @TypeAlias phải kiểm tra mapping context và polymorphic properties. Đừng coi việc code biên dịch hoặc một document mới đọc được là bằng chứng migration an toàn.

Một quy trình nâng cấp đáng tin cậy cần kiểm tra mapping/settings thực tế, giữ fixture dữ liệu cũ, triển khai reader tương thích trước writer mới, backfill hoặc reindex có kiểm soát, xác minh kết quả và giữ đường rollback. Khi các hợp đồng được version hóa và rollout theo expand-and-contract, thay đổi schema có thể tiến hành mà không làm mất khả năng đọc dữ liệu đang tồn tại.
