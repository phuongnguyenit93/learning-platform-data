# Optimistic concurrency bằng sequence number và primary term

Khi nhiều ứng dụng cùng đọc và cập nhật một document Elasticsearch, một lần ghi có thể vô tình ghi đè thay đổi của lần ghi khác. Optimistic concurrency control (OCC) giúp phát hiện tình huống này bằng cách yêu cầu lần ghi chỉ thành công nếu document vẫn ở đúng phiên bản mà client đã đọc.

Elasticsearch cung cấp hai giá trị để thực hiện cơ chế này:

- **Sequence number (_seq_no):** số thứ tự của thao tác ghi gần nhất được áp dụng trên shard chứa document.
- **Primary term (_primary_term):** thế hệ của primary shard đã cấp sequence number đó.

Client đọc document, giữ lại cả hai giá trị, rồi gửi chúng trong lần index, update hoặc delete tiếp theo qua điều kiện **if_seq_no** và **if_primary_term**. Elasticsearch chỉ chấp nhận thao tác nếu cặp token vẫn khớp với trạng thái hiện tại. Nếu document đã thay đổi hoặc primary shard đã được thay thế, thao tác bị từ chối bằng lỗi version conflict thay vì âm thầm ghi đè dữ liệu mới.

## 1. Vì sao cần optimistic concurrency?

Giả sử tồn kho của sản phẩm P-100 đang là 10. Hai request đọc cùng giá trị này:

~~~text
Thời điểm       Request A                  Request B
----------------------------------------------------------------
t1              Đọc stock = 10
t2                                         Đọc stock = 10
t3              Tính stock = 8
t4                                         Tính stock = 7
t5              Ghi stock = 8
t6                                         Ghi stock = 7
~~~

Kết quả cuối cùng là 7. Thay đổi của A bị ghi đè bởi B, dù hai request đều dựa trên cùng một giá trị ban đầu. Đây là lost update.

Nếu hai thao tác thực sự là hai lần giảm tồn kho độc lập, kết quả mong đợi có thể là 5. Nếu B thay đổi tồn kho theo một quy tắc khác, ứng dụng cũng cần biết dữ liệu nền đã thay đổi trước khi quyết định ghi.

OCC giải quyết vấn đề bằng cách gắn điều kiện phiên bản vào lần ghi:

1. Client đọc document và nhận token phiên bản.
2. Client tính giá trị mới từ document đã đọc.
3. Client gửi giá trị mới cùng token.
4. Elasticsearch so sánh token với phiên bản hiện tại.
5. Nếu token còn đúng, ghi thành công; nếu đã cũ, trả conflict.

OCC phù hợp khi xung đột không xảy ra thường xuyên và ứng dụng có thể xử lý khi phát hiện xung đột. Cơ chế này không khóa document trong lúc client suy nghĩ hoặc tính toán.

## 2. Sequence number là gì?

Mỗi thao tác ghi được Elasticsearch áp dụng trên một shard sẽ được gán sequence number. Sequence number tăng theo thứ tự hoạt động ghi trên shard đó.

Document hit có thể trả về metadata:

~~~json
{
  "_index": "products",
  "_id": "P-100",
  "_seq_no": 17,
  "_primary_term": 3,
  "_source": {
    "name": "Keyboard",
    "stock": 10
  }
}
~~~

Trong ví dụ:

- **_seq_no = 17** là sequence number của thao tác gần nhất tạo ra phiên bản document này.
- **_primary_term = 3** là primary term của primary shard đã cấp sequence number đó.
- **_source** là nội dung document được đọc.

Sequence number có phạm vi theo shard, không phải bộ đếm toàn cluster. Hai document ở hai shard khác nhau có thể có cùng sequence number. Vì vậy, không dùng riêng sequence number làm ID toàn cục hoặc so sánh thứ tự thay đổi giữa các shard.

Khi một document được ghi lại thành công, sequence number của phiên bản mới sẽ thay đổi. Client có thể dùng giá trị đó để phát hiện một lần ghi khác đã xảy ra kể từ lần đọc của mình.

## 3. Primary term là gì?

Primary term xác định thế hệ của primary shard. Khi Elasticsearch bầu một primary shard mới, primary term được tăng lên. Điều này giúp phân biệt các thao tác được cấp bởi primary cũ và primary mới.

Sequence number và primary term phải được sử dụng cùng nhau:

| Token | Cho biết | Vai trò |
| --- | --- | --- |
| _seq_no | Thứ tự thao tác trên shard. | Phát hiện document đã có thao tác ghi mới hơn. |
| _primary_term | Thế hệ primary shard. | Phân biệt thao tác thuộc primary term cũ hay mới. |
| Cặp hai giá trị | Phiên bản cụ thể mà client đã đọc. | Điều kiện optimistic concurrency cho lần ghi tiếp theo. |

Nếu chỉ kiểm tra sequence number, client có thể không phân biệt được các thao tác thuộc những thế hệ primary khác nhau. Primary term bổ sung thông tin cần thiết để bảo vệ thao tác khi có failover hoặc thay đổi primary.

Không tự tăng hoặc tự tính hai giá trị này trong ứng dụng. Elasticsearch cấp và quản lý chúng.

## 4. Lấy sequence number và primary term khi đọc

### 4.1. Get API

Với Get API, thêm tham số seq_no_primary_term=true:

~~~http
GET /products/_doc/P-100?seq_no_primary_term=true
~~~

Response có thể chứa:

~~~json
{
  "_index": "products",
  "_id": "P-100",
  "_version": 8,
  "_seq_no": 17,
  "_primary_term": 3,
  "found": true,
  "_source": {
    "name": "Keyboard",
    "stock": 10
  }
}
~~~

Ứng dụng lưu cả _seq_no và _primary_term cùng dữ liệu mà nó vừa đọc.

### 4.2. Search API

Khi lấy document bằng search, yêu cầu metadata sequence number và primary term:

~~~http
GET /products/_search
Content-Type: application/json

{
  "seq_no_primary_term": true,
  "query": {
    "term": {
      "_id": "P-100"
    }
  }
}
~~~

Mỗi hit phù hợp có thể chứa _seq_no và _primary_term bên cạnh _index, _id, _score và _source.

Nếu client cần cập nhật đúng document vừa tìm thấy, cần giữ lại:

- Index thực tế của hit.
- ID document.
- Routing value nếu document được index với custom routing.
- Sequence number.
- Primary term.
- Nội dung hoặc dữ liệu nghiệp vụ đã dùng để tính thay đổi.

Sequence number và primary term chỉ có ý nghĩa trong phạm vi document/shard mà chúng được đọc. Không lấy token của một document để ghi document khác.

### 4.3. Không nhầm token với thời điểm cập nhật

Sequence number không phải timestamp. Không dùng nó để hiển thị ngày giờ cập nhật hoặc so sánh thời gian giữa các shard. Nếu nghiệp vụ cần thời điểm cập nhật, lưu field timestamp riêng như updatedAt.

## 5. Ghi có điều kiện bằng if_seq_no và if_primary_term

Khi index một document đã tồn tại, gửi cả hai điều kiện trong request:

~~~http
PUT /products/_doc/P-100?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "name": "Keyboard",
  "stock": 8
}
~~~

Elasticsearch chỉ ghi nếu phiên bản hiện tại của P-100 vẫn có _seq_no bằng 17 và _primary_term bằng 3.

Nếu thao tác thành công, response trả metadata của phiên bản mới, ví dụ:

~~~json
{
  "_index": "products",
  "_id": "P-100",
  "_version": 9,
  "result": "updated",
  "_seq_no": 21,
  "_primary_term": 3
}
~~~

Sequence number mới là token phải dùng cho lần ghi kế tiếp. Không tiếp tục dùng token cũ sau khi ghi thành công.

### 5.1. Hai điều kiện phải đi cùng nhau

OCC theo sequence number yêu cầu cả if_seq_no và if_primary_term. Chúng tạo thành một cặp điều kiện.

Không gửi chỉ một trong hai tham số để tự mô phỏng OCC. Dùng đúng cặp token mà Elasticsearch trả về từ lần đọc trước.

### 5.2. Ghi document mới và điều kiện tồn tại

Nếu mục tiêu là tạo document mới và không ghi đè document cùng ID đã tồn tại, dùng create semantics hoặc op_type=create. Đó là kiểm soát xung đột do ID đã tồn tại, khác với OCC dựa trên token của một document đã đọc.

Ví dụ:

~~~http
PUT /products/_create/P-200
Content-Type: application/json

{
  "name": "Mouse",
  "stock": 25
}
~~~

Create-only bảo đảm không thay thế document hiện hữu có cùng ID. OCC bằng sequence number/primary term bảo đảm một lần cập nhật chỉ áp dụng lên phiên bản đã đọc.

## 6. Update API với optimistic concurrency

Update API cũng hỗ trợ cặp điều kiện:

~~~http
POST /products/_update/P-100?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "stock": 8
  }
}
~~~

Nếu document vẫn ở phiên bản được đọc, Elasticsearch áp dụng partial document. Nếu phiên bản đã đổi, thao tác trả conflict.

Có thể dùng script update cùng điều kiện:

~~~http
POST /products/_update/P-100?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = params.stock",
    "params": {
      "stock": 8
    }
  }
}
~~~

Điều kiện OCC vẫn áp dụng cho phiên bản document. Script không được chạy như một cách bỏ qua token; nó chỉ được thực hiện nếu điều kiện ghi được chấp nhận.

### 6.1. Partial update và full replacement

Hai kiểu ghi có hành vi khác nhau:

- Index API thay thế nội dung document theo source được gửi.
- Update API áp dụng partial document hoặc script lên source hiện tại.

Cả hai đều có thể dùng if_seq_no và if_primary_term. Hãy chọn API theo mục tiêu thay đổi dữ liệu, sau đó gắn cặp token tương ứng.

### 6.2. Update không có OCC

Nếu ứng dụng đọc document, tính giá trị mới ở client rồi gọi update không có điều kiện, một request khác vẫn có thể ghi vào giữa hai bước. Khi đó update thứ hai có thể ghi đè kết quả trước.

Việc dùng partial update không tự động ngăn lost update nếu phần dữ liệu được cập nhật dựa trên một snapshot cũ. OCC vẫn cần thiết khi quyết định nghiệp vụ phụ thuộc vào phiên bản đã đọc.

## 7. Delete API cũng hỗ trợ OCC

Nếu cần xóa document chỉ khi nó chưa bị thay đổi kể từ lúc đọc, gửi token trong Delete API:

~~~http
DELETE /products/_doc/P-100?if_seq_no=17&if_primary_term=3
~~~

Nếu token còn khớp, document được xóa. Nếu document đã được cập nhật hoặc primary term đã thay đổi, Elasticsearch từ chối thao tác bằng version conflict.

Điều này hữu ích khi giao diện hiển thị một bản ghi và người dùng xác nhận xóa sau một khoảng thời gian. Nếu bản ghi đã thay đổi trong lúc người dùng xem, ứng dụng có thể yêu cầu tải lại trước khi xác nhận.

## 8. Điều gì xảy ra khi token đã cũ?

Giả sử hai client cùng đọc phiên bản có token (17, 3):

~~~text
Client A                              Client B
---------------------------------------------------------------
GET document -> (17, 3)
                                      GET document -> (17, 3)
PUT if_seq_no=17
    if_primary_term=3
-> thành công, document thành
   phiên bản mới (21, 3)
                                      PUT if_seq_no=17
                                          if_primary_term=3
                                      -> 409 version conflict
~~~

Request của B không được áp dụng vì document hiện tại không còn ở phiên bản (17, 3).

Response lỗi thường có HTTP status 409 Conflict, cùng loại lỗi version_conflict_engine_exception. Ví dụ rút gọn:

~~~json
{
  "error": {
    "type": "version_conflict_engine_exception",
    "reason": "[P-100]: version conflict, required seqNo [17], primary term [3]. current document has a different version"
  },
  "status": 409
}
~~~

Nội dung reason thực tế có thể khác theo API, phiên bản và trạng thái document. Ứng dụng nên dựa vào HTTP status và error type, không parse một chuỗi thông báo cố định.

Conflict là tín hiệu cho biết quyết định dựa trên dữ liệu cũ không còn được bảo đảm. Nó không nhất thiết là lỗi hệ thống hoặc lỗi cần retry vô điều kiện.

## 9. Quy trình xử lý conflict ở ứng dụng

Khi nhận 409, ứng dụng có thể chọn một trong các chiến lược sau tùy nghiệp vụ:

### 9.1. Đọc lại và yêu cầu người dùng xác nhận

Phù hợp khi hai người dùng cùng chỉnh sửa một biểu mẫu hoặc cấu hình.

1. Thông báo dữ liệu đã được người khác thay đổi.
2. Đọc lại document và token mới.
3. Hiển thị thay đổi hiện tại.
4. Yêu cầu người dùng áp dụng lại hoặc hợp nhất thay đổi.

Đây là cách rõ ràng khi không thể tự quyết định giá trị nào được ưu tiên.

### 9.2. Đọc lại và tính lại thay đổi

Phù hợp khi thao tác có thể được đánh giá lại trên dữ liệu mới.

1. Đọc document mới nhất.
2. Kiểm tra lại điều kiện nghiệp vụ.
3. Tính giá trị mới từ snapshot mới.
4. Gửi lần ghi với cặp token mới.
5. Nếu tiếp tục conflict, retry có giới hạn.

Ví dụ: đặt hạn mức theo tỷ lệ phần trăm của giá trị hiện tại. Khi giá trị gốc thay đổi, ứng dụng phải tính lại trên giá trị mới thay vì gửi lại kết quả đã tính từ snapshot cũ.

### 9.3. Hợp nhất field độc lập

Nếu hai client cập nhật các field không phụ thuộc nhau, service có thể đọc lại document rồi áp dụng lại thay đổi trên field của mình. Tuy nhiên, phải xác định rõ field nào có thể hợp nhất và field nào có invariant liên quan.

Không tự động ghép hai bản source nếu các field có quan hệ nghiệp vụ. Ví dụ số lượng, tổng tiền và trạng thái đơn hàng có thể cần được cập nhật như một đơn vị logic.

### 9.4. Giới hạn số lần retry

Không retry vô hạn. Khi nhiều client liên tục ghi cùng một document, retry không giới hạn có thể tạo vòng lặp tải cao.

Một chính sách thực tế có thể:

- Retry tối đa một số lần nhỏ.
- Có backoff ngắn và jitter nếu workload có nhiều writer.
- Đọc lại token sau mỗi conflict.
- Tính lại logic trên dữ liệu mới.
- Ghi metric cho số lần conflict và retry.
- Trả lỗi có ý nghĩa nếu vượt ngưỡng.

Retry chỉ có ích nếu ứng dụng có thể đọc lại và đưa ra quyết định mới. Gửi lại cùng request với token cũ sẽ tiếp tục conflict.

## 10. Phân biệt OCC tường minh với retry_on_conflict

Update API có tùy chọn retry_on_conflict. Nó cho phép Elasticsearch thử lại một update nội bộ khi có version conflict trong quá trình update.

Hai cơ chế phục vụ mục đích khác nhau:

| Cơ chế | Ai quyết định retry? | Dữ liệu dùng để retry | Phù hợp khi |
| --- | --- | --- | --- |
| if_seq_no + if_primary_term | Client/service | Client kiểm soát snapshot và quyết định mới. | Cần từ chối thao tác dựa trên phiên bản cũ. |
| retry_on_conflict | Elasticsearch | Update operation được đọc và thực hiện lại theo cơ chế Update API. | Update script/partial operation có thể chạy lại an toàn trên source mới. |

Ví dụ tăng stock bằng script trên server:

~~~http
POST /products/_update/P-100?retry_on_conflict=3
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

Update API có thể đọc lại source và chạy lại script khi gặp conflict trong giới hạn retry. Vì script cộng vào giá trị hiện tại, việc chạy lại có thể phù hợp với ý nghĩa tăng thêm một đơn vị.

Ngược lại, script gán một giá trị đã tính từ snapshot cũ có thể không an toàn khi chạy lại nếu logic nghiệp vụ phụ thuộc vào dữ liệu client đã đọc.

Không coi retry_on_conflict là cách thay thế cho cặp token OCC. Khi caller cần bảo đảm “chỉ ghi nếu document vẫn đúng phiên bản tôi đã đọc”, hãy gửi if_seq_no và if_primary_term và xử lý conflict ở tầng ứng dụng. Không giả định có thể kết hợp mọi hình thức retry với điều kiện OCC mà không kiểm tra hành vi của API và phiên bản Elasticsearch.

## 11. Sequence number trong Bulk API

Bulk API cho phép gửi nhiều thao tác trong cùng request. Mỗi action có thể mang điều kiện OCC riêng.

Ví dụ update hai document:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"P-100","if_seq_no":17,"if_primary_term":3}}
{"doc":{"stock":8}}
{"delete":{"_index":"products","_id":"P-200","if_seq_no":9,"if_primary_term":2}}
~~~

Mỗi action được kiểm tra độc lập. Một item có thể thành công trong khi item khác trả conflict. Bulk response có trường errors và danh sách items; ứng dụng phải kiểm tra kết quả từng item thay vì chỉ xem HTTP request tổng thể.

Ví dụ xử lý:

- Nếu update P-100 thành công, lưu token mới từ item response nếu cần ghi tiếp.
- Nếu delete P-200 trả 409, đọc lại document và quyết định có còn cần xóa không.
- Không retry toàn bộ bulk một cách mù quáng vì các item đã thành công có thể bị thực thi lại.

Bulk giúp giảm round trip nhưng không biến toàn bộ request thành một transaction nguyên tử.

## 12. Phân biệt sequence number/primary term với _version

Elasticsearch cũng trả về _version. Đây là cơ chế versioning nội bộ khác với cặp sequence number và primary term.

| Cơ chế | Dữ liệu điều kiện | Mục đích |
| --- | --- | --- |
| Internal versioning | _version | Theo dõi version của document và kiểm soát ghi theo version trong các API hỗ trợ. |
| External versioning | version cùng version_type | Cho phép hệ thống bên ngoài cung cấp version theo quy tắc external version. |
| OCC hiện đại | if_seq_no và if_primary_term | Chỉ ghi khi document còn đúng phiên bản được đọc từ Elasticsearch. |

Không lấy _version rồi truyền vào if_seq_no; hai giá trị không cùng ý nghĩa và không thể thay thế nhau.

Spring Data Elasticsearch có annotation @Version cho cơ chế versioning của entity. Không mặc định rằng một field @Version chính là cặp _seq_no và _primary_term. Nếu use case cần OCC dựa trên token của Elasticsearch, hãy lấy sequence number và primary term từ search/get metadata rồi truyền chúng vào request ghi.

## 13. Tích hợp Spring Data Elasticsearch

Spring Data Elasticsearch có thể làm việc với metadata của search hit và cung cấp các API ghi có điều kiện tùy phiên bản. Cần giữ token từ kết quả đọc và chuyển token đó sang request index/update.

### 13.1. Đọc metadata từ SearchHit

Khi dùng ElasticsearchOperations.search, mỗi SearchHit<T> cung cấp ID, index, nội dung và metadata của hit. Các phiên bản Spring Data Elasticsearch hiện đại có getter cho sequence number và primary term:

~~~java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();

    String id = hit.getId();
    String index = hit.getIndex();
    long seqNo = hit.getSeqNo();
    long primaryTerm = hit.getPrimaryTerm();

    // Giữ product cùng seqNo và primaryTerm
    // cho lần ghi có điều kiện tiếp theo.
}
~~~

Nếu dùng Get API hoặc một API khác, kiểm tra response metadata tương ứng. Không chỉ lưu entity mà bỏ quên token; entity source thường không tự chứa _seq_no hoặc _primary_term.

### 13.2. Ghi bằng IndexQuery

Spring Data Elasticsearch có IndexQuery và builder để truyền sequence number cùng primary term trong các phiên bản hỗ trợ:

~~~java
import org.springframework.data.elasticsearch.core.IndexQuery;
import org.springframework.data.elasticsearch.core.IndexQueryBuilder;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexQuery indexQuery = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .withSeqNo(seqNo)
        .withPrimaryTerm(primaryTerm)
        .build();

operations.index(
        indexQuery,
        IndexCoordinates.of("products")
);
~~~

Index operation sẽ mang điều kiện token xuống Elasticsearch. Nếu document đã thay đổi, thao tác có thể phát sinh version conflict thay vì ghi đè phiên bản mới.

Tên builder method và kiểu nullable của sequence number/primary term phụ thuộc phiên bản Spring Data Elasticsearch. Đối chiếu API của dependency trong dự án và xác nhận request thực tế có cả hai tham số.

### 13.3. UpdateQuery

Với partial update, một số phiên bản Spring Data Elasticsearch cung cấp thuộc tính điều kiện sequence number và primary term trên UpdateQuery builder. Ví dụ dạng API thường gặp:

~~~java
import java.util.Map;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

UpdateQuery updateQuery = UpdateQuery.builder(id)
        .withDocument(Document.from(Map.of("stock", 8)))
        .withIfSeqNo(seqNo)
        .withIfPrimaryTerm(primaryTerm)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

Nếu phiên bản đang dùng không có các builder method này, có thể dùng Elasticsearch Java API Client trực tiếp. Không bỏ điều kiện OCC chỉ để code biên dịch; hãy dùng API tương ứng hoặc nâng cấp theo kế hoạch.

### 13.4. Elasticsearch Java API Client trực tiếp

Với Elasticsearch Java API Client, UpdateRequest hỗ trợ điều kiện sequence number và primary term:

~~~java
import co.elastic.clients.elasticsearch.core.UpdateRequest;
import java.util.Map;

UpdateRequest<ProductDocument, Map<String, Object>> request =
        UpdateRequest.of(u -> u
                .index(index)
                .id(id)
                .ifSeqNo(seqNo)
                .ifPrimaryTerm(primaryTerm)
                .doc(Map.of("stock", 8)));

var response = client.update(request, ProductDocument.class);
~~~

IndexRequest và DeleteRequest cũng có các điều kiện tương ứng trong Java API Client. Kiểu generic, overload và cách lấy client từ Spring Data phụ thuộc phiên bản; dùng đúng client được dependency quản lý.

### 13.5. Bắt version conflict

Spring Data có thể bọc lỗi từ Elasticsearch trong exception thuộc tầng client/operations. Tên exception cụ thể phụ thuộc phiên bản và API được gọi.

Ở tầng service, hãy nhận diện conflict từ status/error type tương ứng, sau đó:

- Đọc lại document và metadata mới.
- Kiểm tra lại điều kiện nghiệp vụ.
- Tính lại thay đổi nếu có thể.
- Gửi request mới với token vừa đọc.
- Dừng và trả lỗi nghiệp vụ nếu vượt số lần retry.

Không bắt mọi exception rồi retry. Lỗi mapping, validation, authentication hoặc script compile không phải optimistic conflict và cần được xử lý riêng.

## 14. Routing và phạm vi hiệu lực của token

Sequence number và primary term thuộc shard chứa document. Nếu document được index với custom routing, request ghi phải dùng đúng routing để đến cùng shard.

Ví dụ document được lưu với routing là tenant-42:

~~~http
GET /products/_doc/P-100?routing=tenant-42&seq_no_primary_term=true
~~~

Lần ghi có điều kiện cũng cần cùng routing:

~~~http
PUT /products/_doc/P-100?routing=tenant-42&if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "stock": 8
}
~~~

Nếu dùng sai routing, request có thể không tìm thấy document hoặc thao tác trên một shard khác. Không dùng cặp token tách khỏi index, document ID và routing context mà nó thuộc về.

## 15. Alias, data stream và index rollover

Một search qua alias có thể trả hit từ một concrete index. Cặp sequence number/primary term thuộc document trong index/shard đó.

Nếu alias chuyển sang index mới giữa lúc đọc và ghi, request ghi qua alias có thể nhắm vào index khác. Token từ index cũ không thể được dùng như token của document ở index mới.

Khi cần OCC qua alias:

- Giữ lại _index thực tế từ hit.
- Xác định chính sách ghi vào concrete index hay alias.
- Đảm bảo request ghi nhắm đúng index và routing của lần đọc.
- Nếu hệ thống rollover index, xử lý trường hợp document đã được chuyển hoặc được tạo ở index khác như một tình huống nghiệp vụ riêng.

Không giả định token OCC có hiệu lực toàn alias hoặc toàn data stream.

## 16. Các tình huống kiểm thử concurrency

Có thể kiểm thử OCC bằng hai client độc lập:

1. Tạo document P-100.
2. Client A đọc và nhận token A.
3. Client B đọc cùng document và nhận token B.
4. Client A ghi thành công với token A.
5. Client B ghi với token B.
6. Xác nhận B nhận HTTP 409 và nội dung A không bị ghi đè.

Ví dụ kỳ vọng:

| Bước | Client | Kết quả |
| --- | --- | --- |
| Đọc lần đầu | A | Nhận (17, 3). |
| Đọc lần đầu | B | Nhận (17, 3). |
| Ghi lần đầu | A | Thành công; token mới (21, 3). |
| Ghi lần đầu | B | 409 vì token cũ (17, 3). |
| Đọc lại | B | Nhận dữ liệu và token mới. |
| Tính lại, ghi lại | B | Thành công nếu điều kiện mới còn khớp. |

Cũng cần kiểm thử:

- Document bị xóa giữa lúc đọc và ghi.
- Primary shard được failover.
- Document có custom routing.
- Client gửi thiếu một trong hai token.
- Bulk request có một số item conflict.
- Retry vượt giới hạn.
- Alias rollover giữa lần đọc và lần ghi.
- Hai request cùng thay đổi field có quan hệ nghiệp vụ.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ghi trả 409 | Document đã đổi kể từ lần đọc. | Đọc lại, kiểm tra logic và retry có giới hạn. |
| Luôn conflict dù không thấy ai sửa | Token lấy từ index/shard/routing khác hoặc đã cũ. | Kiểm tra _index, ID, routing và cặp token. |
| Chỉ truyền if_seq_no hoặc if_primary_term | Thiếu một nửa điều kiện OCC. | Gửi cả hai giá trị từ cùng một lần đọc. |
| Dùng _version làm if_seq_no | Nhầm hai cơ chế versioning. | Lấy đúng _seq_no và _primary_term. |
| Retry cùng token cũ vẫn lỗi | Token không được cập nhật sau conflict. | Đọc lại document và lấy cặp token mới. |
| Update script làm tăng giá trị hai lần | Retry nghiệp vụ hoặc request lặp không có idempotency. | Thiết kế thao tác idempotent hoặc dùng operation ID/điều kiện nghiệp vụ. |
| Bulk request có HTTP thành công nhưng item lỗi | Bulk xử lý độc lập từng item. | Kiểm tra errors và kết quả từng item. |
| Spring Data không truyền OCC xuống request | Dùng API/version không hỗ trợ hoặc builder chưa được cấu hình. | Kiểm tra API đúng phiên bản và request thực tế. |
| Token không dùng được sau rollover | Token thuộc concrete index cũ. | Ghi vào đúng index hoặc xử lý chuyển index theo nghiệp vụ. |
| Request không tìm thấy document có routing | Ghi/đọc không dùng cùng routing. | Giữ routing value cùng metadata document. |

## 18. Nguyên tắc thiết kế

Khi đưa optimistic concurrency vào một service Spring Data Elasticsearch:

1. Lấy sequence number và primary term từ cùng một lần đọc.
2. Giữ index, ID và routing cùng với token.
3. Truyền cả if_seq_no và if_primary_term trong lần ghi.
4. Xử lý 409 như một xung đột dữ liệu có thể dự đoán.
5. Đọc lại và đánh giá lại logic trước khi retry.
6. Giới hạn số lần retry và quan sát conflict rate.
7. Không nhầm OCC với _version, @Version hoặc retry_on_conflict.
8. Không dùng token trên document, index hoặc shard khác.
9. Với phép cập nhật có thể thực hiện nguyên tử ở server, cân nhắc Update API và script phù hợp.
10. Kiểm tra từng item trong Bulk API.
11. Kiểm thử failover, routing và alias rollover.
12. Xác định rõ trường hợp cần yêu cầu người dùng xác nhận thay đổi.

OCC là cơ chế phát hiện ghi dựa trên snapshot cũ. Nó không tự giải quyết xung đột nghiệp vụ, không hợp nhất dữ liệu và không biến nhiều request thành transaction. Ứng dụng vẫn cần quy tắc rõ ràng để quyết định retry, merge hoặc từ chối thao tác.

## 19. Tài liệu tham khảo

- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch — Get API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-get.html)
- [Elasticsearch — Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Delete API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-delete.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Spring Data Elasticsearch — Search result types and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Version annotation](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Version.html)

Sequence number và primary term tạo thành token của phiên bản document trên một shard. Client lấy cả hai khi đọc rồi gửi lại bằng if_seq_no và if_primary_term khi index, update hoặc delete. Nếu document đã thay đổi, Elasticsearch trả 409 để ứng dụng đọc lại và quyết định cách xử lý. Spring Data có thể chuyển metadata từ SearchHit sang các API ghi có điều kiện; cần dùng đúng API theo phiên bản và giữ nguyên index, ID cùng routing của document.

