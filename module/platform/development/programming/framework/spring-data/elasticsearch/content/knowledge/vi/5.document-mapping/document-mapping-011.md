# Phân biệt metadata ánh xạ phía ứng dụng và mapping đã tồn tại

Trong Spring Data Elasticsearch, các annotation trên entity Java mô tả cách ứng dụng hiểu và chuyển đổi dữ liệu. Trong Elasticsearch, mỗi index lại có một mapping được lưu ở phía server để xác định cách các field được nhận diện, phân tích, lập chỉ mục và truy vấn. Hai phần này có liên quan nhưng không phải cùng một thứ.

- **Mapping metadata phía ứng dụng** là thông tin trong mã Java, thường được khai báo bằng các annotation như @Document, @Id và @Field. Spring Data dùng metadata này để ánh xạ object Java thành document, chuyển document về object và tạo định nghĩa mapping khi cần.
- **Mapping đã tồn tại trên Elasticsearch** là cấu hình schema của một index được lưu trong cluster. Elasticsearch dùng mapping đó khi nhận document và thực hiện truy vấn.

Ví dụ, entity khai báo name là text và category là keyword chỉ mô tả ý định ánh xạ của ứng dụng. Để Elasticsearch thực sự áp dụng hai kiểu field đó, mapping tương ứng phải được tạo hoặc cập nhật trên index. Nếu index đã tồn tại với mapping khác, thay đổi annotation trong Java không tự động biến mapping phía server thành cấu hình mới.

## 1. Mapping metadata phía ứng dụng là gì?

Spring Data Elasticsearch sử dụng metadata của entity để hiểu mối quan hệ giữa class Java và document trong Elasticsearch.

Ví dụ:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text, analyzer = "standard")
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;

        @Field(type = FieldType.Double)
        private Double price;

        // constructors, getters and setters
    }

Các annotation mô tả những thông tin khác nhau:

| Annotation | Vai trò |
|---|---|
| @Document | Khai báo entity được ánh xạ vào index nào và một số tùy chọn liên quan đến document/index |
| @Id | Đánh dấu thuộc tính dùng làm định danh document |
| @Field | Mô tả tên field, kiểu dữ liệu và các thuộc tính mapping như analyzer, format hoặc khả năng index |

Spring Data xây dựng metadata của entity thông qua mapping context và sử dụng MappingElasticsearchConverter để chuyển đổi giữa object Java và dữ liệu document. Metadata này giúp framework biết thuộc tính nào tương ứng với field nào, kiểu dữ liệu nào cần chuyển đổi và cách xử lý các giá trị khi đọc hoặc ghi.

Ví dụ, khi lưu một Product, converter chuyển các thuộc tính thành document JSON có cấu trúc tương ứng. Khi đọc document, converter chuyển dữ liệu trả về thành object Product.

Metadata phía ứng dụng còn có thể được dùng để tạo định nghĩa mapping cho index. Đây là một trong những lý do Spring Data cung cấp các annotation mapping: cùng một mô hình entity có thể hỗ trợ chuyển đổi dữ liệu và mô tả mapping cần thiết cho Elasticsearch.

Tuy nhiên, annotation không phải là lệnh cập nhật schema được gửi đến Elasticsearch mỗi khi ứng dụng khởi động hoặc mỗi khi lưu một object. Việc tạo index và cập nhật mapping là thao tác riêng, phụ thuộc cấu hình và lifecycle của ứng dụng.

## 2. Mapping đã tồn tại trên Elasticsearch là gì?

Elasticsearch lưu mapping ở cấp index. Mapping mô tả cách mỗi field trong document được xử lý, ví dụ:

- Field có kiểu text, keyword, long, double, date, boolean hay kiểu khác.
- Field text dùng analyzer nào để tách token.
- Field có được lập chỉ mục để tìm kiếm hay không.
- Field có hỗ trợ doc values cho sort và aggregation hay không.
- Object hoặc nested field được biểu diễn như thế nào.
- Dynamic mapping có được phép tự suy luận field mới hay không.

Mapping của index products có thể có dạng:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          },
          "price": {
            "type": "double"
          }
        }
      }
    }

Sau khi index được tạo, mapping được lưu trong Elasticsearch cluster và áp dụng cho các thao tác ghi, tìm kiếm, sort và aggregation trên index đó.

Có thể đọc mapping hiện tại bằng REST API:

    GET products/_mapping

Response cho biết cấu hình mapping Elasticsearch đang sử dụng. Đây là dữ liệu cần kiểm tra khi muốn biết index thực tế đang hiểu field như thế nào, đặc biệt khi index đã được tạo trước khi phiên bản ứng dụng hiện tại được triển khai.

Mapping là cấu hình của index, không phải thuộc tính của class Java. Một class Product có thể được dùng để ghi vào nhiều index khác nhau, trong khi mỗi index có mapping riêng. Nếu dùng alias trỏ đến nhiều index, các index phía sau alias cũng có thể có mapping khác nhau.

## 3. Hai loại mapping liên hệ với nhau như thế nào?

Spring Data metadata có thể được dùng để tạo mapping cho Elasticsearch, nhưng sau khi mapping được lưu trên server, Elasticsearch sử dụng mapping của index để xử lý document. Có thể hình dung luồng như sau:

    Entity Java
    @Document / @Id / @Field
           |
           v
    Spring Data mapping metadata
           |
           +-----------------------------+
           |                             |
           v                             v
    MappingElasticsearchConverter   Mapping builder
    Chuyển object <-> document      Tạo mapping definition
           |                             |
           v                             v
    Document JSON                 IndexOperations
           |                             |
           v                             v
    Elasticsearch index  <------  Index mapping
           |
           v
    Elasticsearch xử lý index/search

Sơ đồ thể hiện hai mục đích liên quan nhưng khác nhau:

1. Converter dùng metadata để chuyển đổi dữ liệu giữa Java và document.
2. Mapping builder dùng metadata để tạo định nghĩa mapping có thể gửi đến Elasticsearch khi tạo index hoặc cập nhật mapping theo thao tác được hỗ trợ.

Khi ứng dụng gửi một document đến index đã tồn tại, document JSON được gửi qua client. Elasticsearch kiểm tra document theo mapping hiện tại của index. Server không tự đọc annotation @Field từ class Java; annotation chỉ có ý nghĩa trong phía ứng dụng Spring Data.

Do đó, cần phân biệt rõ:

- Metadata Java mô tả cách ứng dụng muốn ánh xạ dữ liệu.
- Mapping server quyết định Elasticsearch thực tế lập chỉ mục và truy vấn dữ liệu ra sao.
- Converter chịu trách nhiệm chuyển đổi object và document, không thay thế mapping engine của Elasticsearch.

## 4. Ví dụ khi metadata và mapping server khớp nhau

Giả sử entity khai báo:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text, analyzer = "standard")
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;
    }

Mapping trên Elasticsearch được tạo tương ứng:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Hai phía thống nhất:

- name là text, phù hợp cho tìm kiếm toàn văn bằng các query như match.
- category là keyword, phù hợp cho so khớp chính xác bằng term, filter, sort hoặc aggregation.

Khi Spring Data lưu Product, converter tạo document JSON. Elasticsearch nhận document và xử lý name, category theo mapping đã được lưu trên index. Khi tìm kiếm, Elasticsearch sử dụng cùng mapping để xác định cách query hoạt động.

Đây là trạng thái dễ vận hành nhất: metadata phía ứng dụng và mapping server phản ánh cùng một mô hình dữ liệu.

## 5. Điều gì xảy ra khi thay đổi annotation nhưng index đã tồn tại?

Giả sử phiên bản đầu của ứng dụng khai báo:

    @Field(type = FieldType.Text)
    private String category;

Sau một thời gian, đội phát triển nhận ra category cần dùng cho filter chính xác và đổi thành:

    @Field(type = FieldType.Keyword)
    private String category;

Thay đổi này chỉ sửa metadata phía ứng dụng. Nếu index products đã tồn tại với category là text, mapping server vẫn giữ kiểu text cho đến khi có thao tác mapping hợp lệ hoặc index mới được tạo.

Vì vậy, sau khi deploy phiên bản mới:

- Converter phía ứng dụng có thể đang làm việc theo metadata keyword.
- Elasticsearch vẫn xử lý field theo mapping text đã tồn tại.
- Query term, filter, sort hoặc aggregation có thể cho kết quả khác với kỳ vọng.
- Ứng dụng có thể gặp lỗi khi gửi giá trị hoặc truy vấn không phù hợp với mapping server.

Đổi annotation không đồng nghĩa với migration mapping. Không nên giả định mỗi lần ứng dụng khởi động, Spring Data sẽ xóa index cũ rồi tạo lại index theo entity mới.

### Kiểm tra tình huống lệch mapping

Có thể kiểm tra annotation trong mã nguồn và mapping thực tế:

    GET products/_mapping

Nếu server trả về:

    {
      "properties": {
        "category": {
          "type": "text"
        }
      }
    }

trong khi entity hiện khai báo FieldType.Keyword, hai phía đang không thống nhất. Cần xác định index được quản lý bởi ứng dụng hay bởi quy trình hạ tầng/migration trước khi quyết định thay đổi.

## 6. Tạo index và mapping từ Spring Data metadata

Spring Data Elasticsearch cung cấp IndexOperations để làm việc với index. Có thể lấy operations gắn với entity:

    IndexOperations indexOperations =
        operations.indexOps(Product.class);

Khi index chưa tồn tại, ứng dụng có thể yêu cầu tạo index cùng mapping được sinh từ metadata:

    boolean created = indexOperations.createWithMapping();

Thao tác này sử dụng thông tin entity để tạo index và mapping tương ứng. Tùy cấu hình, có thể cần khai báo thêm settings, analyzer hoặc mapping tùy chỉnh.

Spring Data cũng hỗ trợ thao tác tạo index và mapping riêng:

    indexOperations.create();
    indexOperations.putMapping();

create() tạo index; putMapping() gửi mapping được xây dựng từ metadata của entity. Cần dùng đúng thao tác theo trạng thái index và phiên bản Spring Data Elasticsearch đang triển khai.

Có thể kiểm tra index và mapping:

    boolean exists = indexOperations.exists();
    Map<String, Object> mapping = indexOperations.getMapping();

Các API trên minh họa cách quản lý index qua Spring Data. Với hệ thống cần kiểm soát schema chặt chẽ, các thao tác này thường nên được đặt trong quy trình triển khai hoặc migration có chủ đích, thay vì để nhiều instance ứng dụng tự thay đổi schema cùng lúc.

### Tùy chọn createIndex trên @Document

@Document có thuộc tính createIndex để điều khiển hành vi tạo index tự động trong lifecycle repository của Spring Data Elasticsearch. Ở các phiên bản phổ biến, giá trị mặc định là true; có thể đặt createIndex = false khi index được quản lý bên ngoài.

Ví dụ:

    @Document(
        indexName = "products",
        createIndex = false
    )
    public class Product {
        // fields
    }

Khi index được quản lý bởi DBA, DevOps, index template hoặc migration pipeline, đặt createIndex = false giúp thể hiện rõ ứng dụng không sở hữu việc tự tạo index trong cơ chế repository tương ứng.

Thuộc tính này không có nghĩa là Spring Data ngừng dùng metadata để chuyển đổi entity. Nó chỉ liên quan đến việc tạo index tự động; converter vẫn cần metadata @Field, @Id và các thông tin khác khi đọc/ghi document.

Hành vi khởi tạo index có thể thay đổi theo phiên bản Spring Data và cách cấu hình repository. Khi dự án phụ thuộc vào hành vi tự động này, hãy kiểm tra tài liệu đúng phiên bản đang dùng.

## 7. Cập nhật mapping của index đã tồn tại

Elasticsearch cho phép cập nhật mapping trong một số giới hạn. Ví dụ, có thể thêm field mới vào mapping hiện có:

    PUT products/_mapping
    {
      "properties": {
        "brand": {
          "type": "keyword"
        }
      }
    }

Sau khi cập nhật, document mới có thể chứa field brand và Elasticsearch sẽ xử lý field theo kiểu keyword.

Từ Spring Data, có thể gọi:

    indexOperations.putMapping();

Thao tác này xây dựng mapping từ metadata hiện tại của entity. Trước khi gọi, cần hiểu rõ mapping server hiện tại và giới hạn của Elasticsearch. putMapping() không phải công cụ tự động chuyển đổi mọi field cũ sang kiểu mới.

### Những thay đổi mapping thường được hỗ trợ

Các thao tác thường gặp:

- Thêm field mới.
- Thêm một số thuộc tính mapping được Elasticsearch cho phép cập nhật.
- Bổ sung sub-field cho multi-fields trong những trường hợp được hỗ trợ.
- Cập nhật một số thiết lập tương thích mà API mapping cho phép.

Khả năng cập nhật cụ thể phụ thuộc loại field và thuộc tính mapping. Không nên suy luận rằng mọi giá trị trong annotation đều có thể ghi đè lên mapping server bằng một lệnh putMapping.

### Những thay đổi không thể sửa trực tiếp theo cách thông thường

Một số thuộc tính định nghĩa cách dữ liệu đã được index, chẳng hạn kiểu field text sang keyword, thường không thể thay đổi trực tiếp trên field đã tồn tại. Elasticsearch không thể tự suy ra và xây dựng lại inverted index cũ theo kiểu mới chỉ từ metadata Java.

Nếu cần đổi kiểu field, analyzer hoặc cách index dữ liệu, giải pháp phổ biến là tạo index mới với mapping đúng, sau đó reindex dữ liệu và chuyển ứng dụng sang index mới.

## 8. Vì sao cần reindex khi mapping thay đổi không tương thích?

Mapping không chỉ là nhãn kiểu dữ liệu. Nó quyết định cách Elasticsearch phân tích và lập chỉ mục document. Ví dụ:

- Field text được phân tích thành token để tìm kiếm toàn văn.
- Field keyword giữ giá trị nguyên vẹn cho so khớp chính xác.
- Analyzer quyết định cách tách từ, chuẩn hóa và tạo token.
- Numeric/date mapping xác định cách lưu và so sánh giá trị.

Nếu thay đổi mapping của một field đã có dữ liệu, các document cũ đã được index theo cấu hình trước đó. Chỉ cập nhật metadata Java không thể tái tạo inverted index, doc values hoặc dữ liệu đã được phân tích.

Quy trình migration điển hình:

    Index cũ: products_v1
    Mapping cũ
          |
          v
    Tạo index mới: products_v2
    Mapping mới
          |
          v
    Reindex dữ liệu từ v1 sang v2
          |
          v
    Kiểm tra dữ liệu và truy vấn
          |
          v
    Chuyển alias products sang v2
          |
          v
    Ứng dụng tiếp tục truy cập alias products

Ví dụ tạo index mới:

    PUT products_v2
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Reindex:

    POST _reindex
    {
      "source": {
        "index": "products_v1"
      },
      "dest": {
        "index": "products_v2"
      }
    }

Sau khi kiểm tra dữ liệu, có thể chuyển alias:

    POST _aliases
    {
      "actions": [
        {
          "remove": {
            "index": "products_v1",
            "alias": "products"
          }
        },
        {
          "add": {
            "index": "products_v2",
            "alias": "products"
          }
        }
      ]
    }

Các lệnh trên minh họa quy trình cơ bản. Hệ thống đang ghi dữ liệu cần có kế hoạch đồng bộ các thay đổi phát sinh trong lúc reindex, hoặc tạm dừng ghi trong thời gian cutover. Cần kiểm tra số lượng document, dữ liệu lỗi, alias và ứng dụng trước khi loại bỏ index cũ.

Một cách tổ chức thường dùng là để @Document(indexName = "products") trỏ đến alias ổn định. Khi thay đổi mapping, ứng dụng vẫn dùng alias; quy trình migration tạo index vật lý mới rồi chuyển alias sau khi xác nhận hoàn tất.

## 9. Dynamic mapping và sự khác nhau với metadata Java

Elasticsearch có dynamic mapping để tự suy luận mapping cho field mới khi nhận document. Ví dụ, nếu index cho phép dynamic mapping và document đầu tiên có:

    {
      "name": "Coffee grinder",
      "stock": 12,
      "active": true
    }

Elasticsearch có thể tự tạo mapping cho name, stock và active dựa trên kiểu dữ liệu mà nó quan sát được.

Điều này không có nghĩa metadata Java đã được đồng bộ với server. Dynamic mapping là hành vi của Elasticsearch, được điều khiển bởi cấu hình mapping của index. Nó có thể tạo field mà entity Java không khai báo, hoặc suy luận kiểu khác với ý định trong mã nguồn.

Ví dụ, một field mã sản phẩm chỉ gồm chữ số có thể bị suy luận thành kiểu số nếu dữ liệu đầu tiên là số. Nếu sau đó ứng dụng gửi chuỗi có ký tự chữ, việc index có thể thất bại do mapping đã được xác định.

Với dữ liệu có schema rõ ràng, nên khai báo mapping tường minh cho các field quan trọng, đặc biệt là field dùng filter, sort, aggregation hoặc full-text search. Có thể dùng dynamic = false hoặc dynamic = strict tùy yêu cầu kiểm soát field mới; hai lựa chọn này có hành vi khác nhau và cần hiểu trước khi áp dụng.

## 10. Quản lý mapping như một phần của vòng đời ứng dụng

Trong dự án nhỏ hoặc môi trường học tập, cho Spring Data tự tạo index và mapping từ entity có thể thuận tiện. Khi hệ thống lớn hơn, mapping trở thành một phần của schema và cần được quản lý có kiểm soát.

Có ba cách tổ chức thường gặp:

### Ứng dụng sở hữu index

Ứng dụng chịu trách nhiệm tạo index từ entity metadata. Cách này đơn giản khi chỉ có một ứng dụng quản lý index và môi trường triển khai không có quy trình migration riêng.

Có thể sử dụng @Document(createIndex = true) và các API IndexOperations phù hợp với lifecycle của ứng dụng. Cần tránh để nhiều instance cùng thực hiện các thay đổi không được điều phối.

### Hạ tầng hoặc migration sở hữu index

Index được tạo trước bằng script, index template hoặc công cụ migration. Ứng dụng đặt createIndex = false, sau đó chỉ sử dụng index đã được chuẩn bị.

Cách này giúp kiểm soát mapping, settings, analyzer, alias và thứ tự triển khai. Tuy nhiên, đội phát triển cần duy trì sự nhất quán giữa entity metadata và mapping do hạ tầng quản lý.

### Kết hợp metadata và migration

Entity Java vẫn khai báo mapping metadata để converter làm việc và có thể dùng làm nguồn tham chiếu cho mapping. Một quy trình migration riêng chịu trách nhiệm tạo index, cập nhật mapping có thể cập nhật và reindex khi cần.

Đây là cách tổ chức phù hợp khi cần kiểm soát schema qua các phiên bản. Mỗi thay đổi mapping nên có kế hoạch triển khai rõ ràng, được kiểm tra trước trên môi trường tương ứng và có cách chuyển alias hoặc quay lại index cũ khi cần.

## 11. Quy trình xử lý khi annotation và mapping server không thống nhất

Khi phát hiện entity metadata khác với mapping thực tế, nên xử lý theo trình tự:

1. Xác định index vật lý mà ứng dụng đang ghi/đọc. Nếu dùng alias, kiểm tra tất cả index phía sau alias.
2. Đọc mapping hiện tại bằng GET index/_mapping.
3. Đối chiếu từng field quan trọng với @Field, tên field và kiểu dữ liệu Java.
4. Xác định index do ứng dụng tự tạo hay do migration/hạ tầng quản lý.
5. Phân loại thay đổi: thêm field, cập nhật thuộc tính được hỗ trợ hay thay đổi không tương thích như đổi field type.
6. Với thay đổi được hỗ trợ, cập nhật mapping có chủ đích và kiểm tra dữ liệu.
7. Với thay đổi không tương thích, tạo index mới, reindex và chuyển alias sau khi xác nhận.
8. Kiểm tra cả thao tác ghi, tìm kiếm, filter, sort và aggregation trên index mới.

Không nên xử lý lệch mapping bằng cách xóa index đang chứa dữ liệu thật rồi để ứng dụng tự tạo lại, trừ khi đã có kế hoạch sao lưu và khôi phục được phê duyệt. Xóa index làm mất dữ liệu trong index đó.

## 12. Những nhầm lẫn thường gặp

### Cho rằng @Field là mapping đã được lưu trên server

@Field là metadata trong ứng dụng. Nó có thể được dùng để sinh mapping khi tạo index hoặc cập nhật mapping theo thao tác được hỗ trợ, nhưng bản thân annotation không phải cấu hình đang lưu trên cluster.

### Cho rằng đổi annotation sẽ đổi field type của index cũ

Mapping của field đã tồn tại có những giới hạn thay đổi. Nếu cần đổi từ text sang keyword hoặc thay đổi cách phân tích dữ liệu đã index, thường phải tạo index mới và reindex.

### Cho rằng converter quyết định cách Elasticsearch tìm kiếm

Converter chuyển object và document. Elasticsearch server dùng mapping của index để phân tích, lập chỉ mục và thực thi query. Hai phía phải tương thích nhưng có trách nhiệm khác nhau.

### Cho rằng tạo repository luôn tạo lại index

Việc tạo index tự động phụ thuộc @Document(createIndex = ...), cấu hình và phiên bản Spring Data Elasticsearch. Không nên giả định repository sẽ xóa hoặc tái tạo một index đã tồn tại để đồng bộ annotation.

### Cho rằng dynamic mapping giống metadata của entity

Dynamic mapping do Elasticsearch suy luận từ document được gửi lên. Nó có thể tạo field ngoài entity hoặc suy luận kiểu không như ý định. Với schema quan trọng, nên khai báo mapping rõ ràng.

### Chỉ kiểm tra mã Java mà không kiểm tra index thực tế

Entity có thể đúng theo thiết kế nhưng index đã tồn tại từ phiên bản cũ. Khi điều tra lỗi mapping, cần đọc GET index/_mapping và xác định index vật lý thực tế mà ứng dụng đang sử dụng.

## Kết luận

Mapping metadata phía ứng dụng và mapping đã tồn tại trên Elasticsearch là hai phần liên quan nhưng độc lập. Annotation @Document, @Id và @Field mô tả cách Spring Data ánh xạ entity, chuyển đổi document và có thể tạo định nghĩa mapping. Mapping của index được lưu trên Elasticsearch mới là cấu hình server dùng để xử lý dữ liệu và truy vấn.

Khi tạo index mới, Spring Data có thể sinh mapping từ metadata thông qua IndexOperations và cơ chế tự động được cấu hình. Khi index đã tồn tại, đổi annotation không tự động thay đổi mapping server. Những thay đổi mapping không tương thích thường cần tạo index mới, reindex dữ liệu và chuyển alias. Hiểu rõ ranh giới này giúp tránh lệch schema, giảm lỗi khi deploy và quản lý vòng đời mapping một cách an toàn.
