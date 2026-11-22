# Thay đổi mảng, bộ đếm và đối tượng lồng nhau

Trong Elasticsearch, thao tác cập nhật một document có thể thay đổi một vài field, tăng một bộ đếm, thêm hoặc xóa phần tử trong mảng, hay sửa một object nằm bên trong document. Những thao tác này cần được thiết kế cẩn thận vì Elasticsearch lưu document theo dạng JSON và khi cập nhật, engine thường đọc phiên bản hiện tại, áp dụng thay đổi rồi index lại document mới.

Spring Data Elasticsearch cung cấp các abstraction như **ElasticsearchOperations**, **UpdateQuery** và **Document** để thực hiện partial update. Khi thay đổi phụ thuộc vào dữ liệu hiện tại của document, có thể dùng **Painless script** để thao tác ngay trong Elasticsearch. Với cập nhật nhiều document theo điều kiện, có thể dùng update-by-query hoặc bulk update tùy phạm vi và cách xác định dữ liệu.

Bài học này tập trung vào các tình huống thường gặp: thay đổi mảng scalar, cập nhật mảng object, thay đổi object lồng nhau, tăng/giảm bộ đếm, bảo vệ cập nhật đồng thời, xử lý document chưa tồn tại và chọn giữa partial document, script, bulk update hoặc update-by-query.

## 1. Cách Elasticsearch thực hiện update

Elasticsearch cung cấp Update API cho một document theo ID. Về bản chất, engine lấy document hiện tại, áp dụng partial document hoặc script lên nội dung, rồi index phiên bản mới. Vì vậy, update một field vẫn tạo ra một phiên bản document mới trong index.

Có hai cách chính:

**Partial document** gửi những field muốn thay đổi. Elasticsearch hợp nhất nội dung được gửi với document hiện tại theo semantics của Update API.

**Scripted update** chạy script trên document hiện tại. Script có thể đọc giá trị cũ, tính toán, thêm hoặc xóa phần tử, rồi quyết định cập nhật hay bỏ qua.

Ví dụ document sản phẩm:

~~~json
{
  "id": "P-100",
  "name": "Wireless Keyboard",
  "price": 79.5,
  "stock": 12,
  "viewCount": 450,
  "tags": ["wireless", "keyboard"],
  "attributes": {
    "color": "black",
    "layout": "US"
  },
  "variants": [
    {
      "variantId": "V-1",
      "color": "black",
      "stock": 8
    },
    {
      "variantId": "V-2",
      "color": "white",
      "stock": 4
    }
  ]
}
~~~

Các yêu cầu cập nhật có thể là:

- Đổi giá sản phẩm.
- Thêm tag mới nhưng không thêm trùng.
- Xóa một tag đã hết hiệu lực.
- Tăng viewCount sau mỗi lượt xem.
- Giảm stock sau khi xác nhận đơn.
- Cập nhật stock của variant có variantId cụ thể.
- Thêm một variant mới vào mảng.
- Đổi thuộc tính color bên trong attributes.

Nên chọn cách cập nhật dựa trên việc có cần đọc giá trị hiện tại để quyết định thay đổi hay không.

## 2. Partial update bằng UpdateQuery và Document

Khi biết chính xác giá trị mới của field, partial document thường đơn giản nhất.

Ví dụ chỉ đổi giá và trạng thái:

~~~java
Document patch = Document.create();
patch.put("price", 85.0);
patch.put("status", "ACTIVE");

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withDocument(patch)
    .build();

UpdateResponse response = operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

Trong ví dụ, chỉ các field được gửi trong Document được yêu cầu cập nhật. Những field khác như name, stock và tags được giữ theo nội dung hiện tại của document.

Các kiểu dữ liệu trong Document cần tương thích với mapping:

- String cho field keyword/text.
- Boolean cho field boolean.
- Number phù hợp với kiểu numeric.
- Map hoặc Document cho object.
- List cho array.

Đừng gửi số dưới dạng chuỗi nếu mapping là numeric. Cũng không nên tự ghép JSON bằng phép nối chuỗi để tạo patch.

### Partial document không tự thực hiện phép toán

Nếu gửi:

~~~java
patch.put("viewCount", 451);
~~~

thì đây là gán giá trị mới 451. Nó không có nghĩa “đọc giá trị hiện tại rồi cộng 1”. Khi cần phép toán phụ thuộc vào trạng thái hiện tại, dùng script.

### Cập nhật object

Với object thường như attributes, có thể gửi một phần object:

~~~java
Document attributesPatch = Document.create();
attributesPatch.put("color", "blue");

Document patch = Document.create();
patch.put("attributes", attributesPatch);
~~~

Cách hợp nhất object và field con phụ thuộc semantics của Update API và cấu trúc request. Hãy kiểm tra kết quả trên phiên bản Elasticsearch đang chạy, đặc biệt khi muốn giữ các thuộc tính anh em bên trong object. Nếu mục tiêu là đổi duy nhất một thuộc tính con và không muốn vô tình thay cả object, script cập nhật trực tiếp field con sẽ thể hiện ý định rõ hơn.

### Mảng được xử lý như một giá trị

Partial update không cung cấp phép toán append/remove cho mảng. Nếu gửi field array mới, hãy coi đó là giá trị mảng cần được ghi cho field đó. Ví dụ gửi tags mới sẽ thay danh sách tags hiện tại bằng danh sách được gửi; không tự động nối phần tử vào mảng cũ.

Để thêm, xóa hoặc sửa một phần tử dựa trên nội dung hiện tại, dùng Painless script.

## 3. Dùng Painless script trong UpdateQuery

Painless là ngôn ngữ script của Elasticsearch. Script update có thể truy cập document đang cập nhật qua ctx._source và tham số truyền qua params.

Một ví dụ tăng bộ đếm:

~~~java
Map<String, Object> params = Map.of(
    "amount", 1
);

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withScript("ctx._source.viewCount = (ctx._source.viewCount == null ? 0 : ctx._source.viewCount) + params.amount")
    .withParams(params)
    .withLang("painless")
    .build();

UpdateResponse response = operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

Script thực hiện:

1. Đọc viewCount hiện tại.
2. Nếu field chưa có hoặc null, dùng giá trị khởi đầu 0.
3. Cộng params.amount.
4. Ghi kết quả vào _source.

Không nối giá trị người dùng trực tiếp vào chuỗi script. Dùng params để truyền dữ liệu; cách này tách code script khỏi dữ liệu và tránh lỗi escape hoặc tạo script khác nhau cho từng giá trị.

API builder của UpdateQuery có thể khác giữa các release train. Hãy đối chiếu overload withScript, withParams, withLang, withDocument và các option upsert trong phiên bản Spring Data Elasticsearch của dự án. Phần code trong bài minh họa API thường gặp, không thay thế việc kiểm tra dependency thực tế.

## 4. Thêm phần tử vào mảng scalar

Giả sử field tags là mảng keyword:

~~~java
@Field(type = FieldType.Keyword)
private List<String> tags;
~~~

Muốn thêm tag mới, có thể dùng script:

~~~java
Map<String, Object> params = Map.of(
    "tag", "sale"
);

String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    ctx._source.tags.add(params.tag);
    """;

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withScript(script)
    .withParams(params)
    .withLang("painless")
    .build();

operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

Script kiểm tra tags trước khi thêm. Nếu field chưa tồn tại, tạo một ArrayList rồi append phần tử.

### Tránh thêm trùng

Nếu nghiệp vụ yêu cầu mỗi tag chỉ xuất hiện một lần:

~~~java
String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    if (!ctx._source.tags.contains(params.tag)) {
        ctx._source.tags.add(params.tag);
    }
    """;
~~~

Nếu tag đã tồn tại, script không thay đổi document. Tùy cấu hình và phiên bản, có thể dùng ctx.op = 'noop' khi không có thay đổi để tránh tạo một lần index mới:

~~~java
String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    if (ctx._source.tags.contains(params.tag)) {
        ctx.op = 'noop';
    } else {
        ctx._source.tags.add(params.tag);
    }
    """;
~~~

Dùng noop khi thực sự không có thay đổi cần lưu. Nó giúp phân biệt update đã thay đổi với request không làm gì.

### Giới hạn kích thước mảng

Không nên để mảng tăng vô hạn. Với tags, lịch sử sự kiện hoặc danh sách ID, hãy đặt giới hạn số phần tử, TTL hoặc chuyển lịch sử dài sang index riêng. Mảng quá lớn làm document nặng hơn, tăng chi phí index lại và khiến mỗi lần update tốn tài nguyên.

## 5. Xóa phần tử khỏi mảng scalar

Để xóa tất cả phần tử có giá trị bằng params.tag, có thể duyệt ngược mảng:

~~~java
Map<String, Object> params = Map.of(
    "tag", "obsolete"
);

String script = """
    if (ctx._source.tags != null) {
        for (int i = ctx._source.tags.size() - 1; i >= 0; i--) {
            if (params.tag.equals(ctx._source.tags[i])) {
                ctx._source.tags.remove(i);
            }
        }
    }
    """;
~~~

Duyệt từ cuối về đầu giúp xóa phần tử mà không làm lệch chỉ số của những phần tử chưa duyệt.

Nếu chỉ cần xóa một phần tử đầu tiên khớp, có thể dùng vòng lặp và break sau khi remove. Hãy định nghĩa rõ nghiệp vụ: xóa một occurrence hay xóa mọi occurrence.

### Xóa field khi mảng rỗng

Sau khi xóa phần tử cuối cùng, có thể giữ field với mảng rỗng:

~~~json
{
  "tags": []
}
~~~

Hoặc xóa hẳn field khỏi _source:

~~~java
if (ctx._source.tags.isEmpty()) {
    ctx._source.remove('tags');
}
~~~

Hai trạng thái này có thể có ý nghĩa khác nhau đối với ứng dụng và truy vấn. Chọn một quy ước nhất quán. Nếu dùng null, empty array và missing như ba trạng thái riêng, hãy kiểm tra query, serialization và mapping tương ứng.

## 6. Thay thế hoặc thêm nhiều phần tử

Khi cần thay toàn bộ mảng bằng một danh sách đã tính ở service, partial document là lựa chọn rõ ràng:

~~~java
Document patch = Document.create();
patch.put("tags", List.of("wireless", "keyboard", "sale"));

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withDocument(patch)
    .build();
~~~

Nếu danh sách mới cần hợp nhất với danh sách hiện tại, có thể dùng script:

~~~java
Map<String, Object> params = Map.of(
    "newTags", List.of("sale", "featured")
);

String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    for (def tag : params.newTags) {
        if (!ctx._source.tags.contains(tag)) {
            ctx._source.tags.add(tag);
        }
    }
    """;
~~~

Nếu thứ tự phần tử quan trọng, hãy giữ quy tắc thứ tự rõ ràng. Nếu mảng chỉ là tập giá trị, cân nhắc chuẩn hóa và loại trùng trước khi ghi.

## 7. Cập nhật bộ đếm

Bộ đếm thường xuất hiện trong các trường như:

- viewCount: số lượt xem.
- downloadCount: số lượt tải.
- likes: số lượt thích.
- retryCount: số lần thử lại.
- stock: số lượng tồn kho.

### Tăng bộ đếm

Painless script:

~~~java
Map<String, Object> params = Map.of("delta", 1);

String script = """
    if (ctx._source.viewCount == null) {
        ctx._source.viewCount = 0;
    }
    ctx._source.viewCount += params.delta;
    """;
~~~

### Giảm bộ đếm có kiểm tra giới hạn

Ví dụ giảm stock nhưng không cho âm:

~~~java
Map<String, Object> params = Map.of("quantity", 2);

String script = """
    if (ctx._source.stock == null) {
        ctx.op = 'noop';
    } else if (ctx._source.stock < params.quantity) {
        throw new IllegalArgumentException('Insufficient stock');
    } else {
        ctx._source.stock -= params.quantity;
    }
    """;
~~~

Trong hệ thống đặt hàng, kiểm tra tồn kho và giảm số lượng cần được thực hiện trong cùng một update script để tránh khoảng thời gian giữa đọc và ghi ở phía ứng dụng. Nếu số lượng không đủ, script có thể báo lỗi để service xử lý theo quy tắc nghiệp vụ.

Tuy nhiên, Elasticsearch không phải hệ quản trị giao dịch tồn kho. Không dùng một document Elasticsearch làm nguồn sự thật duy nhất cho nghiệp vụ tài chính hoặc tồn kho cần đảm bảo giao dịch mạnh nếu hệ thống cần transaction, reservation, ledger hoặc phối hợp nhiều tài nguyên. Có thể dùng database giao dịch làm nguồn chính và đồng bộ trạng thái tìm kiếm sang Elasticsearch.

### Cộng/trừ với delta có dấu

Một script tổng quát có thể dùng delta:

~~~java
Map<String, Object> params = Map.of("delta", -3);

String script = """
    int current = ctx._source.retryCount == null
        ? 0
        : ctx._source.retryCount;
    int next = current + params.delta;
    if (next < 0) {
        throw new IllegalArgumentException('Counter cannot be negative');
    }
    ctx._source.retryCount = next;
    """;
~~~

Kiểm tra kiểu numeric của field và kiểu params. Với bộ đếm lớn, dùng kiểu long phù hợp thay vì int. Tránh ép kiểu không cần thiết nếu giá trị có thể vượt miền số nguyên 32-bit.

### Đếm theo sự kiện và tính idempotent

Script increment có thể chạy nguyên tử đối với một lần cập nhật document được Elasticsearch chấp nhận. Nhưng nếu client timeout sau khi Elasticsearch đã ghi thành công, client có thể gửi lại request và tăng bộ đếm lần nữa.

Nếu cần chống xử lý trùng sự kiện, không dựa vào phép cộng đơn thuần. Hãy dùng event ID/idempotency key, lưu dấu sự kiện đã xử lý hoặc thiết kế pipeline cập nhật có khả năng deduplicate. Một counter tổng hợp thường không đủ thông tin để biết sự kiện nào đã được áp dụng.

## 8. Cập nhật object lồng nhau

Với object thông thường:

~~~json
{
  "attributes": {
    "color": "black",
    "layout": "US",
    "backlit": true
  }
}
~~~

Muốn chỉ đổi color:

~~~java
Map<String, Object> params = Map.of(
    "color", "blue"
);

String script = """
    if (ctx._source.attributes == null) {
        ctx._source.attributes = new HashMap();
    }
    ctx._source.attributes.color = params.color;
    """;
~~~

Script thao tác trực tiếp thuộc tính con trong _source. Các thuộc tính khác như layout và backlit được giữ nguyên.

Nếu object có thể null, cần khởi tạo trước khi gán. Nếu object có cấu trúc sâu hơn, kiểm tra từng cấp trước khi truy cập để tránh lỗi null pointer trong script.

### Cập nhật field sâu

Ví dụ object:

~~~json
{
  "shipping": {
    "address": {
      "city": "Ho Chi Minh City",
      "district": "District 1"
    }
  }
}
~~~

Đổi district:

~~~java
Map<String, Object> params = Map.of(
    "district", "District 3"
);

String script = """
    if (ctx._source.shipping == null) {
        ctx._source.shipping = new HashMap();
    }
    if (ctx._source.shipping.address == null) {
        ctx._source.shipping.address = new HashMap();
    }
    ctx._source.shipping.address.district = params.district;
    """;
~~~

Chỉ tạo object trung gian khi cần. Nếu object bắt buộc phải có theo schema, có thể validate trước khi update và xem trường hợp thiếu object là lỗi dữ liệu thay vì tự khởi tạo.

## 9. Cập nhật một phần tử trong mảng object

Giả sử document có mảng variants:

~~~json
{
  "variants": [
    {
      "variantId": "V-1",
      "color": "black",
      "stock": 8
    },
    {
      "variantId": "V-2",
      "color": "white",
      "stock": 4
    }
  ]
}
~~~

Muốn cập nhật stock của variant V-2:

~~~java
Map<String, Object> params = Map.of(
    "variantId", "V-2",
    "newStock", 7
);

String script = """
    if (ctx._source.variants != null) {
        boolean found = false;
        for (def variant : ctx._source.variants) {
            if (params.variantId.equals(variant.variantId)) {
                variant.stock = params.newStock;
                found = true;
                break;
            }
        }
        if (!found) {
            ctx.op = 'noop';
        }
    } else {
        ctx.op = 'noop';
    }
    """;
~~~

Script duyệt mảng trong _source, tìm object có variantId khớp, rồi đổi stock. Ví dụ dùng break để chỉ cập nhật phần tử đầu tiên. Nếu variantId không duy nhất và cần cập nhật mọi phần tử, bỏ break.

### Kiểm tra phần tử có tồn tại

Có hai chính sách thường gặp:

- Không tìm thấy variant thì noop, vì thao tác có thể được gọi lặp hoặc variant đã bị xóa.
- Không tìm thấy variant thì báo lỗi nghiệp vụ, vì ID không hợp lệ cần được phát hiện.

Chọn chính sách rõ ràng. Không nên âm thầm thêm variant mới khi mục đích ban đầu là cập nhật một variant đã tồn tại.

### Thêm object mới vào mảng

~~~java
Map<String, Object> newVariant = Map.of(
    "variantId", "V-3",
    "color", "blue",
    "stock", 0
);

Map<String, Object> params = Map.of(
    "variant", newVariant
);

String script = """
    if (ctx._source.variants == null) {
        ctx._source.variants = new ArrayList();
    }
    boolean exists = false;
    for (def variant : ctx._source.variants) {
        if (params.variant.variantId.equals(variant.variantId)) {
            exists = true;
            break;
        }
    }
    if (exists) {
        ctx.op = 'noop';
    } else {
        ctx._source.variants.add(params.variant);
    }
    """;
~~~

Đoạn script kiểm tra ID trước khi append để tránh thêm trùng. Nếu muốn cập nhật khi đã tồn tại và thêm khi chưa có, có thể thay nhánh noop bằng logic cập nhật các field được phép.

### Xóa object khỏi mảng

Duyệt ngược để xóa phần tử theo variantId:

~~~java
Map<String, Object> params = Map.of(
    "variantId", "V-2"
);

String script = """
    if (ctx._source.variants != null) {
        for (int i = ctx._source.variants.size() - 1; i >= 0; i--) {
            if (params.variantId.equals(ctx._source.variants[i].variantId)) {
                ctx._source.variants.remove(i);
            }
        }
    }
    """;
~~~

Nếu variantId được đảm bảo duy nhất, có thể dừng sau lần xóa đầu tiên. Nếu dữ liệu cũ có thể chứa ID trùng, quyết định rõ xóa một hay tất cả và xử lý dữ liệu không nhất quán.

## 10. Nested mapping và cập nhật object lồng nhau

Một mảng object có thể được mapping là object hoặc nested. Cần phân biệt:

- **object**: các giá trị được flatten khi index; query không bảo toàn ranh giới giữa các object trong mảng.
- **nested**: mỗi phần tử được index như nested Lucene document để query/aggregation giữ quan hệ trong từng object.

Ví dụ mapping nested:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;
}
~~~

Trong _source, variants vẫn là mảng JSON object. Script update làm việc với nội dung _source của document cha, vì vậy cách thêm, sửa hoặc xóa phần tử trong mảng vẫn dùng vòng lặp Painless như các ví dụ trước.

Điểm quan trọng: nested object không phải document độc lập có ID riêng để gọi Update API trực tiếp. Update API theo ID tác động lên document cha. Khi thay đổi một nested object, Elasticsearch index lại document cha và các nested Lucene documents liên quan.

### Tại sao không cập nhật nested child bằng ID riêng?

Nested documents có quan hệ nội bộ với parent và được quản lý như một phần của document cha. Không thể dùng ID của nested object như ID document độc lập trong Update API. Muốn đổi một line hoặc variant, hãy update parent document bằng script hoặc gửi lại phần dữ liệu phù hợp.

Nếu ứng dụng cần cập nhật từng phần tử thường xuyên, độc lập và có vòng đời riêng, cân nhắc mô hình mỗi phần tử là một document riêng trong index khác, lưu parent ID để liên kết ở tầng ứng dụng.

### Nested query không tự giới hạn script vào một child

Một nested query có thể chọn parent documents có nested child phù hợp. Nhưng script update vẫn chạy trên _source của parent. Nếu cần chỉ thay đổi nested object thỏa điều kiện, script phải tự duyệt mảng và kiểm tra điều kiện đó. Không giả định nested query tự truyền một child object riêng vào script.

## 11. Upsert: cập nhật hoặc tạo mới nếu chưa tồn tại

Có những thao tác muốn tạo document nếu ID chưa tồn tại. Update API hỗ trợ upsert.

Ví dụ partial document upsert:

~~~java
Document initial = Document.create();
initial.put("name", "Wireless Keyboard");
initial.put("stock", 0);
initial.put("viewCount", 0);

UpdateQuery updateQuery = UpdateQuery.builder("P-200")
    .withDocument(Document.from(Map.of("status", "ACTIVE")))
    .withUpsert(initial)
    .build();

operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

Nếu document tồn tại, partial document được áp dụng. Nếu chưa tồn tại, nội dung upsert được dùng để tạo document.

### doc_as_upsert

Một số phiên bản UpdateQuery hỗ trợ docAsUpsert. Khi bật, partial document cũng được dùng làm nội dung tạo mới nếu document chưa tồn tại. Cần kiểm tra API và semantics của release đang dùng.

Upsert cần đủ dữ liệu bắt buộc để tạo một document hợp lệ. Nếu chỉ gửi status mà document mới cần name, mapping và các field nghiệp vụ khác, upsert có thể tạo document thiếu dữ liệu hoặc vi phạm quy ước của ứng dụng.

### scripted_upsert

Với scripted upsert, script có thể chạy cả khi document chưa tồn tại. Trong trường hợp đó, cần khởi tạo ctx._source phù hợp và phân biệt thao tác tạo mới với cập nhật. Các option scripted_upsert và upsert có semantics riêng; đừng bật chỉ vì muốn script chạy trong mọi trường hợp.

## 12. Cập nhật nhiều document bằng update-by-query

Nếu cần thay đổi mọi document thỏa một điều kiện, không nên tải toàn bộ về Java, sửa từng object rồi gửi lại. Update-by-query cho phép Elasticsearch tìm document theo query và áp dụng script cho từng document được chọn.

Ví dụ tăng version của tất cả sản phẩm thuộc category accessories:

~~~http
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.catalogVersion = params.version",
    "params": {
      "version": 3
    }
  }
}
~~~

Update-by-query chạy trên tập document khớp query. Nó có thể xử lý theo batch nội bộ và trả về số document đã cập nhật, số noop, số conflict hoặc lỗi.

### Update-by-query với mảng object

Ví dụ đặt lại stock của variant có ID V-2 trong các sản phẩm có ít nhất một variant V-2:

~~~http
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "term": {
          "variants.variantId": "V-2"
        }
      }
    }
  },
  "script": {
    "lang": "painless",
    "source": """
      for (def variant : ctx._source.variants) {
        if (params.variantId.equals(variant.variantId)) {
          variant.stock = params.stock;
        }
      }
    """,
    "params": {
      "variantId": "V-2",
      "stock": 7
    }
  }
}
~~~

Nested query chọn parent document có ít nhất một variant phù hợp. Script vẫn duyệt mảng trong _source và cập nhật đúng phần tử theo ID.

### Cập nhật theo batch và kiểm soát tải

Update-by-query có thể tác động lên lượng dữ liệu lớn. Cần xem xét:

- Query có chọn đúng tập document không.
- Có thể chạy trên alias/index nào.
- Batch size và throttling phù hợp.
- Cách xử lý version conflict.
- Timeout và task cancellation.
- Số lượng document đã cập nhật và lỗi từng phần.
- Thời điểm refresh để dữ liệu mới có thể tìm thấy.

Không chạy update-by-query diện rộng trong giờ cao điểm mà chưa đánh giá tải và kế hoạch rollback/reindex. Với thay đổi schema hoặc chuyển đổi dữ liệu lớn, có thể cần reindex sang index mới thay vì update tại chỗ.

### Dùng Elasticsearch Java API Client

Direct client có API update-by-query trong các phiên bản client hỗ trợ:

~~~java
UpdateByQueryResponse response =
    elasticsearchClient.updateByQuery(r -> r
        .index("products")
        .query(q -> q.term(t -> t
            .field("category")
            .value("accessories")
        ))
        .script(s -> s.inline(i -> i
            .lang("painless")
            .source("ctx._source.catalogVersion = params.version")
            .params("version", JsonData.of(3))
        )),
        RequestOptions.DEFAULT
    );
~~~

Đây là minh họa theo API client; kiểu response, cách truyền JsonData và request overload phụ thuộc phiên bản Elasticsearch Java API Client. Nếu dự án dùng Spring Data abstraction cho update-by-query, hãy kiểm tra API tương ứng trong release train. Không nên trộn trực tiếp request của client cũ với Java API Client mới.

## 13. Bulk update khi đã biết danh sách ID

Nếu ứng dụng đã biết tập document cần cập nhật, bulk update thường phù hợp hơn việc gửi từng request riêng lẻ.

Ví dụ cập nhật status cho nhiều ID bằng Spring Data operations:

~~~java
List<UpdateQuery> updates = List.of(
    UpdateQuery.builder("P-100")
        .withDocument(Document.from(Map.of("status", "ACTIVE")))
        .build(),
    UpdateQuery.builder("P-101")
        .withDocument(Document.from(Map.of("status", "ACTIVE")))
        .build(),
    UpdateQuery.builder("P-102")
        .withDocument(Document.from(Map.of("status", "ACTIVE")))
        .build()
);

operations.bulkUpdate(
    updates,
    IndexCoordinates.of("products")
);
~~~

API bulkUpdate và kiểu kết quả có thể thay đổi theo phiên bản Spring Data Elasticsearch. Mục tiêu của ví dụ là gửi nhiều thao tác update trong một bulk request để giảm overhead mạng.

Bulk API không đảm bảo toàn bộ items thành công hoặc rollback cùng nhau. Một số item có thể thành công trong khi item khác thất bại. Luôn đọc kết quả từng item, ghi nhận ID lỗi và thiết kế retry cho những thao tác có thể chạy lại an toàn.

### Chọn bulk hay update-by-query

| Tình huống | Cách phù hợp |
|---|---|
| Đã biết danh sách ID và patch của từng document | Bulk update |
| Một điều kiện query xác định tập document và mọi document dùng cùng script | Update-by-query |
| Chỉ cập nhật một document theo ID | Update API/UpdateQuery |
| Cần đọc và tính toán nghiệp vụ phức tạp từ nhiều nguồn | Service orchestration, sau đó bulk update |
| Thay đổi cấu trúc index hoặc mapping | Index mới và reindex |

## 14. Cập nhật đồng thời và version conflict

Hai request có thể cùng cập nhật một document gần như đồng thời. Elasticsearch sử dụng optimistic concurrency control để tránh ghi đè một phiên bản đã thay đổi mà client không biết.

Update API có thể dùng retry_on_conflict để thử lại khi xảy ra version conflict. Với script increment, retry giúp script chạy lại trên phiên bản mới nhất theo cơ chế update của Elasticsearch.

Ví dụ cấu hình retry:

~~~java
UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withScript("ctx._source.viewCount = (ctx._source.viewCount ?: 0) + params.delta")
    .withParams(Map.of("delta", 1))
    .withLang("painless")
    .withRetryOnConflict(3)
    .build();
~~~

Cú pháp toán tử null-coalescing trong script có thể phụ thuộc Painless; cách viết kiểm tra null tường minh ở phần trước dễ đọc và ít gây nhầm hơn. Quan trọng là retry không phải cơ chế đảm bảo request từ client chỉ được thực hiện một lần.

### Sequence number và primary term

Khi ứng dụng đọc document rồi quyết định ghi dựa trên chính phiên bản đã đọc, có thể dùng if_seq_no và if_primary_term để chỉ cập nhật nếu document chưa bị thay đổi kể từ lần đọc đó.

Nếu điều kiện không còn đúng, Elasticsearch trả version conflict. Service có thể đọc lại, tính toán lại hoặc trả lỗi xung đột cho client.

Cách này hữu ích khi update là một quyết định dựa trên snapshot đã đọc. Với thao tác cộng/trừ đơn giản có thể thực hiện bằng script, không nhất thiết phải tự đọc rồi ghi ở ứng dụng.

### Retry có thể lặp tác dụng bên ngoài Elasticsearch

retry_on_conflict xử lý conflict bên trong cơ chế update. Nó không giải quyết trường hợp client gửi lại cùng một nghiệp vụ sau timeout nhưng lần trước đã thành công. Với thao tác có side effect như tăng điểm, trừ tồn kho hoặc cộng tiền, cần idempotency key và nguồn sự thật giao dịch phù hợp.

## 15. Noop, delete và điều kiện cập nhật

Script có thể quyết định không thay đổi document:

~~~java
String script = """
    if (ctx._source.status == params.status) {
        ctx.op = 'noop';
    } else {
        ctx._source.status = params.status;
    }
    """;
~~~

Nếu giá trị đã đúng, đặt noop giúp tránh index lại document không cần thiết.

Script cũng có thể yêu cầu xóa document bằng ctx.op = 'delete', nhưng cần phân biệt xóa document với xóa một phần tử khỏi mảng. Chỉ dùng delete khi nghiệp vụ muốn loại toàn bộ document.

Không nên dùng script để thay thế một update đơn giản nếu partial document đã thể hiện rõ ý định. Script linh hoạt hơn nhưng khó kiểm soát và có thể tốn CPU hơn.

## 16. Script parameters và an toàn khi cập nhật

Không nối input trực tiếp vào script:

~~~java
// Tránh tạo script bằng cách nối giá trị người dùng.
String script = "ctx._source.name = '" + userInput + "'";
~~~

Thay vào đó, dùng params:

~~~java
Map<String, Object> params = Map.of(
    "name", userInput
);

String script = "ctx._source.name = params.name";
~~~

Lợi ích:

- Script source ổn định và dễ cache.
- Dữ liệu không làm thay đổi cú pháp script.
- Tránh lỗi escape khi giá trị chứa dấu nháy hoặc ký tự đặc biệt.
- Dễ kiểm thử script với nhiều giá trị khác nhau.

Chỉ cho phép script và field được kiểm soát bởi ứng dụng. Không nhận script Painless tùy ý từ client. Trong môi trường production, cân nhắc stored scripts hoặc chính sách script của cluster nếu có nhiều query/update dùng chung.

## 17. Khi nào nên thay đổi mô hình dữ liệu?

Nếu một document có mảng object lớn và thường xuyên cập nhật một phần tử nhỏ, mỗi update vẫn có thể khiến toàn bộ parent document được index lại. Điều này có thể gây chi phí đáng kể khi mảng lớn hoặc nhiều request cập nhật đồng thời.

Hãy cân nhắc tách phần tử thành document riêng khi:

- Mỗi phần tử có vòng đời độc lập.
- Một phần tử được cập nhật thường xuyên hơn parent.
- Mảng có thể tăng rất lớn.
- Cần phân quyền hoặc optimistic concurrency riêng cho từng phần tử.
- Cần tìm kiếm, phân trang và thống kê phần tử độc lập.

Ví dụ thay vì lưu variants trong product:

~~~json
{
  "productId": "P-100",
  "variants": [
    {"variantId": "V-1", "stock": 8},
    {"variantId": "V-2", "stock": 4}
  ]
}
~~~

có thể tạo index variants với mỗi variant là một document:

~~~json
{
  "variantId": "V-2",
  "productId": "P-100",
  "stock": 4
}
~~~

Khi đó, cập nhật stock của V-2 là update document riêng. Đổi lại, truy vấn cần kết hợp dữ liệu product và variant ở tầng ứng dụng hoặc qua cơ chế phù hợp. Elasticsearch không tự cung cấp join giao dịch giữa hai index như quan hệ bảng trong relational database.

## 18. Kiểm tra kết quả update

Update API thường trả thông tin như ID, version, sequence number, primary term và kết quả thao tác. Kết quả có thể phân biệt:

- **UPDATED**: document đã được thay đổi.
- **NOOP**: script không làm thay đổi document.
- **CREATED**: document được tạo qua upsert.
- **DELETED**: document bị xóa theo script.

Kiểu enum và tên thuộc tính response phụ thuộc API client/Spring Data version. Hãy đọc response để phân biệt update thành công, noop và tạo mới.

Sau khi update, document không nhất thiết xuất hiện ngay trong search request tiếp theo nếu refresh chưa xảy ra. Elasticsearch refresh làm thay đổi mới có thể tìm kiếm được. Không nên bật refresh ngay sau mọi thao tác nếu không cần độ trễ hiển thị tức thời; refresh thường xuyên có thể làm giảm hiệu năng indexing.

Nếu cần đọc ngay document theo ID, Get API có thể trả nội dung mới mà không cần chờ search visibility. Phân biệt read-by-ID và search-after-refresh trong test.

## 19. Ví dụ service cập nhật variant stock

Ví dụ service nhận product ID, variant ID và số lượng thay đổi:

~~~java
public void decreaseVariantStock(
        String productId,
        String variantId,
        int quantity) {

    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "quantity must be positive"
        );
    }

    Map<String, Object> params = Map.of(
        "variantId", variantId,
        "quantity", quantity
    );

    String script = """
        if (ctx._source.variants == null) {
            throw new IllegalArgumentException('Variants are missing');
        }

        boolean found = false;

        for (def variant : ctx._source.variants) {
            if (params.variantId.equals(variant.variantId)) {
                if (variant.stock == null || variant.stock < params.quantity) {
                    throw new IllegalArgumentException('Insufficient stock');
                }

                variant.stock -= params.quantity;
                found = true;
                break;
            }
        }

        if (!found) {
            throw new IllegalArgumentException('Variant not found');
        }
        """;

    UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(script)
        .withParams(params)
        .withLang("painless")
        .withRetryOnConflict(3)
        .build();

    operations.update(
        updateQuery,
        IndexCoordinates.of("products")
    );
}
~~~

Ví dụ này minh họa kiểm tra và giảm stock trong cùng một update script của document cha. Trong ứng dụng thực tế:

- Xử lý lỗi script thành lỗi nghiệp vụ phù hợp.
- Đảm bảo variantId là duy nhất trong một product.
- Dùng idempotency key nếu request có thể được gửi lại sau timeout.
- Cân nhắc nguồn dữ liệu giao dịch cho tồn kho.
- Ghi log kết quả mà không để lộ dữ liệu nhạy cảm.
- Kiểm tra API builder và exception mapping của phiên bản dependency đang dùng.

## 20. Kiểm thử các thao tác thay đổi mảng và object

Nên kiểm tra update với dữ liệu thật trên Elasticsearch tương thích, vì Painless, mapping và semantics của Update API không thể được xác nhận chỉ bằng unit test gọi method Java.

Các trường hợp quan trọng:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Thêm tag vào mảng hiện có | Tag mới xuất hiện |
| Thêm tag đã tồn tại với chính sách unique | Không tạo bản sao |
| Xóa tag | Các occurrence theo chính sách bị xóa |
| Mảng chưa tồn tại | Script khởi tạo hoặc xử lý theo quy tắc |
| Mảng rỗng sau khi xóa | Giữ empty hay xóa field theo quy ước |
| Tăng counter | Giá trị mới bằng giá trị cũ cộng delta |
| Counter null | Dùng giá trị khởi đầu được định nghĩa |
| Giảm stock đủ số lượng | Stock giảm đúng |
| Giảm stock không đủ | Update thất bại và không ghi giá trị âm |
| Cập nhật object con | Field mục tiêu đổi, field anh em được giữ |
| Cập nhật nested child | Đúng child được sửa trong parent source |
| Child không tồn tại | Noop hoặc lỗi theo chính sách |
| Upsert | Tạo document đủ field bắt buộc |
| Hai update đồng thời | Không âm thầm ghi đè theo chiến lược concurrency |
| Client retry sau timeout | Idempotency được xử lý ở tầng nghiệp vụ |

Skeleton integration test:

~~~java
@Test
void addsTagWithoutDuplicates() {
    // Index product có tags ["wireless"].
    // Gọi update script thêm "sale".
    // Đọc document theo ID.
    // Xác nhận tags chứa "wireless" và "sale".
    // Gọi lại cùng thao tác.
    // Xác nhận "sale" chỉ xuất hiện một lần.
}
~~~

Một test khác nên tạo product có nhiều variants cùng dữ liệu khác nhau, cập nhật một variant rồi xác nhận các variant còn lại không đổi. Với nested mapping, test cần xác nhận mapping thật là nested và truy vấn nested vẫn hoạt động sau update.

## 21. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Mảng bị thay toàn bộ | Gửi partial document chứa field array và nghĩ đó là append | Dùng script để thêm/xóa phần tử |
| Tag xuất hiện nhiều lần | Script append không kiểm tra tồn tại | Dùng contains hoặc quy tắc unique |
| Xóa phần tử nhưng bỏ sót occurrence | Dừng vòng lặp sau lần đầu | Duyệt ngược nếu cần xóa tất cả |
| Script báo null pointer | Field hoặc object trung gian chưa tồn tại | Kiểm tra và khởi tạo từng cấp |
| Counter bị tăng hai lần | Client retry sau timeout hoặc sự kiện trùng | Dùng idempotency key/deduplication |
| Stock âm | Kiểm tra và ghi tách rời ở ứng dụng | Kiểm tra rồi giảm trong cùng script |
| Update conflict | Nhiều request cập nhật cùng document | Retry có giới hạn hoặc optimistic concurrency |
| Nested child không update được bằng ID | Nested object không phải document độc lập | Cập nhật parent theo ID |
| Script không thấy child được nested query chọn | Script thao tác trên parent _source | Duyệt mảng và kiểm tra child trong script |
| Upsert tạo document thiếu field | Nội dung upsert không đầy đủ | Tạo payload upsert hợp lệ hoặc scripted upsert |
| Bulk có item lỗi | Bulk không có transaction all-or-nothing | Đọc kết quả từng item và retry có kiểm soát |
| Search chưa thấy thay đổi | Chưa refresh index | Dùng refresh policy phù hợp hoặc đọc theo ID |
| Script bị từ chối | Script không hợp lệ hoặc policy không cho phép | Kiểm tra Painless và cluster script settings |

## 22. Chọn partial document, script, bulk hay update-by-query

| Nhu cầu | Cách nên cân nhắc |
|---|---|
| Gán giá trị mới cho một vài field đã biết | Partial document với UpdateQuery |
| Tăng/giảm counter từ giá trị hiện tại | Scripted update |
| Thêm, xóa hoặc sửa một phần tử mảng | Scripted update |
| Đổi field sâu trong object | Scripted update hoặc partial object patch đã kiểm tra semantics |
| Cập nhật document chưa tồn tại bằng payload mặc định | Upsert |
| Cập nhật nhiều ID đã biết | Bulk update |
| Cập nhật mọi document thỏa một query | Update-by-query |
| Mỗi child cần cập nhật độc lập thường xuyên | Tách child thành document riêng |
| Nghiệp vụ cần transaction mạnh hoặc chống trùng sự kiện | Dùng hệ thống giao dịch/idempotency phù hợp làm nguồn sự thật |

Partial document dễ đọc và thích hợp cho thao tác gán. Script cần thiết khi thay đổi phụ thuộc trạng thái hiện tại. Bulk giảm số request khi biết danh sách ID. Update-by-query phù hợp cho thay đổi diện rộng theo điều kiện.

Không nên dùng script cho mọi update. Cũng không nên tải document về Java, sửa mảng rồi ghi toàn bộ nếu có thể thực hiện một thao tác nguyên tử theo document ở Elasticsearch.

## 23. Checklist trước khi triển khai update

- [ ] Xác định thao tác là gán giá trị hay thay đổi dựa trên trạng thái hiện tại.
- [ ] Partial document không bị nhầm với append/remove array.
- [ ] Script dùng params thay vì nối dữ liệu vào source.
- [ ] Field và object trung gian được kiểm tra null.
- [ ] Thao tác thêm phần tử có chính sách duplicate rõ ràng.
- [ ] Thao tác xóa xác định xóa một hay mọi occurrence.
- [ ] Mảng có giới hạn kích thước và quy tắc empty/missing.
- [ ] Counter có kiểu số và miền giá trị phù hợp.
- [ ] Kiểm tra điều kiện trước khi giảm stock hoặc counter.
- [ ] Nested child được cập nhật thông qua parent document.
- [ ] Upsert chứa đủ dữ liệu bắt buộc.
- [ ] Retry và optimistic concurrency phù hợp với mức tranh chấp.
- [ ] Request retry từ client có chiến lược idempotency khi cần.
- [ ] Bulk/update-by-query có giới hạn tải và đọc kết quả từng phần.
- [ ] Refresh policy phù hợp với yêu cầu hiển thị.
- [ ] Integration test xác nhận kết quả trên Elasticsearch thực tế.

Thay đổi mảng, bộ đếm và object lồng nhau cần chọn đúng cơ chế update. Partial document phù hợp với việc gán giá trị đã biết; Painless script phù hợp khi phải đọc và thay đổi cấu trúc hiện tại như append, remove, increment hoặc cập nhật một child object. Với nested mapping, child vẫn thuộc document cha nên update diễn ra trên parent. Khi cập nhật nhiều document, dùng bulk nếu đã biết ID hoặc update-by-query nếu tập dữ liệu được xác định bằng query; đồng thời thiết kế concurrency, retry và idempotency theo yêu cầu nghiệp vụ.

