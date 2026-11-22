# Cập nhật dữ liệu lặp và xử lý nhất quán giữa các tài liệu

Trong Elasticsearch, một thông tin nghiệp vụ có thể được sao chép vào nhiều document để truy vấn nhanh mà không cần join như trong cơ sở dữ liệu quan hệ. Ví dụ tên sản phẩm có thể xuất hiện trong document sản phẩm, đơn hàng, dòng đơn hàng và lịch sử giao dịch; tên cửa hàng có thể xuất hiện trong nhiều listing; tên danh mục có thể được lưu cùng mỗi sản phẩm. Cách tổ chức này gọi là denormalization (phi chuẩn hóa dữ liệu).

Denormalization giúp đọc nhanh và đơn giản hóa search query, nhưng tạo ra một vấn đề: khi dữ liệu gốc thay đổi, các bản sao trong những document khác cũng có thể phải thay đổi. Elasticsearch không cung cấp transaction ACID bao trùm nhiều document. Bulk request cũng không phải transaction; từng item thành công hoặc thất bại độc lập. Vì vậy, ứng dụng cần thiết kế nguồn dữ liệu chuẩn, luồng cập nhật lan truyền, xử lý sự kiện lặp hoặc sai thứ tự, retry, phát hiện lỗi và đối soát dữ liệu.

Bài học này trình bày cách chọn mô hình dữ liệu, cách cập nhật nhiều document bằng Spring Data Elasticsearch, cách kiểm soát đồng thời và cách xây dựng luồng nhất quán có thể phục hồi khi một phần công việc thất bại.

## 1. Vì sao có dữ liệu lặp giữa các document?

Giả sử hệ thống bán hàng lưu một sản phẩm và các đơn hàng đã đặt:

~~~json
{
  "_id": "product-100",
  "name": "Wireless Keyboard",
  "brandName": "KeyWorks",
  "categoryName": "Accessories"
}
~~~

Một document đơn hàng có thể lưu lại thông tin cần thiết để hiển thị lịch sử mua:

~~~json
{
  "_id": "order-900",
  "customerId": "customer-20",
  "items": [
    {
      "productId": "product-100",
      "productName": "Wireless Keyboard",
      "brandName": "KeyWorks",
      "quantity": 2,
      "unitPrice": 1299000
    }
  ]
}
~~~

Document đơn hàng giữ bản sao productName và brandName. Khi tìm đơn hàng, ứng dụng có thể hiển thị tên sản phẩm trực tiếp mà không phải tra cứu document sản phẩm cho từng dòng đơn hàng.

Một ví dụ khác là catalog tìm kiếm:

~~~json
{
  "_id": "listing-501",
  "title": "Wireless Keyboard",
  "sellerId": "seller-7",
  "sellerName": "North Star Store",
  "sellerRating": 4.8,
  "categoryName": "Accessories"
}
~~~

sellerName và sellerRating có thể được sao chép vào nhiều listing để lọc, sort và hiển thị kết quả nhanh.

Các lý do thường gặp để lặp dữ liệu:

- Giảm số lần đọc document liên quan trong một request.
- Tránh join khi query Elasticsearch.
- Tối ưu cho một màn hình hoặc một kiểu tìm kiếm cụ thể.
- Lưu snapshot lịch sử, ví dụ tên và giá tại thời điểm đặt hàng.
- Tạo projection/read model phù hợp với một use case.

Không phải bản sao nào cũng cần đồng bộ sau mọi thay đổi. Tên sản phẩm trong đơn hàng đã hoàn tất thường là snapshot lịch sử; nếu sản phẩm đổi tên sau này, hóa đơn cũ có thể vẫn phải giữ tên tại thời điểm mua. Ngược lại, sellerName trong listing đang hoạt động thường cần cập nhật để hiển thị thông tin hiện hành.

## 2. Xác định nguồn dữ liệu chuẩn và ý nghĩa của từng bản sao

Trước khi viết code cập nhật, hãy phân loại mỗi field lặp:

| Loại dữ liệu lặp | Ví dụ | Khi dữ liệu gốc thay đổi |
|---|---|---|
| Snapshot lịch sử | Tên sản phẩm và đơn giá trong đơn hàng đã xác nhận | Thường giữ nguyên theo thời điểm giao dịch |
| Projection hiện hành | Tên người bán trong listing đang hoạt động | Cần lan truyền thay đổi |
| Cache/search projection | Tên danh mục được copy vào sản phẩm | Có thể rebuild từ nguồn chuẩn |
| Counter tổng hợp | Số sản phẩm đang bán của cửa hàng | Cần cập nhật bằng event hoặc tính lại |
| Dữ liệu dẫn xuất | Search keywords, slug, normalized name | Có thể tái tạo từ field gốc |

Một field cần có quy tắc rõ ràng: ai sở hữu giá trị, khi nào bản sao được cập nhật, bản sao nào là snapshot và hệ thống nào được phép ghi.

### 2.1. Chọn một nguồn dữ liệu chuẩn

Trong nhiều hệ thống, cơ sở dữ liệu nghiệp vụ là source of truth; Elasticsearch là read model phục vụ tìm kiếm và lọc. Ví dụ:

~~~text
Database nghiệp vụ
       |
       | thay đổi sản phẩm/người bán
       v
Outbox event hoặc CDC
       |
       v
Consumer cập nhật projection
       |
       +------> product index
       |
       +------> listing index
       |
       +------> recommendation index
~~~

Khi đó, Elasticsearch không phải nơi duy nhất giữ dữ liệu chuẩn. Nếu một projection bị sai, hệ thống có thể phát lại event hoặc xây lại index từ nguồn dữ liệu gốc.

Nếu Elasticsearch là kho lưu trữ chính của ứng dụng, vẫn cần xác định document nào là chủ sở hữu của từng field và cách đồng bộ các bản sao. Không nên để nhiều service độc lập cùng ghi cùng một field mà không có quy tắc phân xử.

### 2.2. Đừng đồng bộ snapshot lịch sử một cách máy móc

Ví dụ đơn hàng lưu unitPrice tại thời điểm mua. Nếu giá catalog thay đổi, không cập nhật unitPrice của đơn hàng cũ. Tương tự, tên sản phẩm trong hóa đơn hoặc phiếu giao hàng có thể là snapshot pháp lý/nghiệp vụ.

Ngược lại, nếu listing cần hiển thị tên hiện hành của người bán, đó là projection cần được cập nhật khi sellerName thay đổi.

Phân biệt hai trường hợp này tránh một lỗi nghiêm trọng: đồng bộ mọi field trùng tên và vô tình làm thay đổi lịch sử giao dịch.

## 3. Các cách mô hình hóa quan hệ trong Elasticsearch

Không phải mọi quan hệ đều cần tạo nhiều document riêng. Cần chọn cấu trúc theo cách đọc, cách cập nhật và kích thước dữ liệu.

| Mô hình | Đặc điểm | Cập nhật và nhất quán |
|---|---|---|
| Nhúng object thường | Dữ liệu con nằm trong cùng _source, không dùng nested | Ghi lại document cha; không có document độc lập cho object con |
| Nested | Object con được lập chỉ mục thành hidden Lucene documents gắn với document cha | Cập nhật nested object vẫn là cập nhật document cha |
| Parent-child join | Parent và child là document riêng trong cùng index, cùng shard | Cập nhật riêng từng document; join query tốn chi phí và không tạo transaction |
| Denormalized documents | Sao chép field cần đọc sang nhiều document/index | Phải fan-out cập nhật hoặc chấp nhận eventual consistency |

### 3.1. Nhúng object hoặc dùng nested

Nếu dữ liệu con luôn được đọc cùng document cha và kích thước hợp lý, nhúng object có thể đơn giản hơn:

~~~json
{
  "orderId": "order-900",
  "items": [
    {
      "productId": "product-100",
      "productName": "Wireless Keyboard",
      "quantity": 2
    }
  ]
}
~~~

Với mapping nested, Elasticsearch giữ ngữ nghĩa từng object con khi query các điều kiện trên cùng một phần tử. Nhưng nested object vẫn thuộc document cha. Cập nhật một nested item đồng nghĩa cập nhật lại document cha theo cơ chế Elasticsearch.

Chọn nested khi:

- Danh sách con có kích thước vừa phải.
- Thường tìm kiếm hoặc lọc các field của object con cùng nhau.
- Cần bảo đảm các thuộc tính trong cùng object con khớp cùng một phần tử.
- Chấp nhận việc cập nhật nested item làm ghi lại document cha.

### 3.2. Parent-child join

Parent-child cho phép document cha và document con tồn tại riêng trong cùng index, dùng join field để biểu diễn quan hệ. Parent và child phải nằm trên cùng shard, vì vậy cần routing phù hợp.

Mô hình này có thể hữu ích khi:

- Một parent có rất nhiều child.
- Child thay đổi thường xuyên trong khi parent ít thay đổi.
- Cần cập nhật child riêng mà không ghi lại toàn bộ parent.

Đổi lại, join query phức tạp và tốn tài nguyên hơn query trên field đã denormalize. Parent-child cũng không cung cấp transaction để cập nhật parent và child cùng lúc. Nếu yêu cầu chính là đọc nhanh và chấp nhận cập nhật bản sao, denormalization thường dễ vận hành hơn.

### 3.3. Tách thành nhiều document và sao chép field

Ví dụ một seller document và nhiều listing document:

~~~json
{
  "_id": "seller-7",
  "name": "North Star Store",
  "rating": 4.8
}
~~~

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Store",
  "sellerRating": 4.8,
  "title": "Wireless Keyboard"
}
~~~

Khi seller đổi tên, các listing đang hoạt động cần được cập nhật nếu sellerName là projection hiện hành. Đây là bài toán cập nhật dữ liệu lặp giữa các document.

## 4. Elasticsearch không có transaction nhiều document

Một thao tác index/update/delete tác động lên một document. Bulk API cho phép gửi nhiều action trong một request, nhưng mỗi action được xử lý độc lập:

- Một item có thể thành công trong khi item khác thất bại.
- Bulk response có thể có HTTP status thành công nhưng trường errors là true.
- Elasticsearch không rollback những item đã thành công chỉ vì một item khác lỗi.
- Không có commit/rollback ACID bao trùm các document trong bulk request.

Ví dụ bulk request:

~~~http
POST _bulk
{"update":{"_index":"listings","_id":"listing-501"}}
{"doc":{"sellerName":"North Star Retail"}}
{"update":{"_index":"listings","_id":"listing-502"}}
{"doc":{"sellerName":"North Star Retail"}}
{"update":{"_index":"listings","_id":"listing-503"}}
{"doc":{"sellerName":"North Star Retail"}}
~~~

Nếu action của listing-502 lỗi, listing-501 và listing-503 vẫn có thể được cập nhật. Ứng dụng phải kiểm tra từng item và có chiến lược retry/đối soát.

### 4.1. Phân biệt atomicity, visibility và durability

Ba khái niệm thường bị nhầm:

- **Atomicity:** một nhóm thay đổi có cùng thành công hoặc cùng thất bại hay không. Bulk không cung cấp atomicity nhiều document.
- **Visibility:** document mới có xuất hiện trong search ngay hay chưa. Elasticsearch near-real-time; refresh quyết định khi nào thay đổi được nhìn thấy qua search.
- **Durability:** thay đổi đã được ghi nhận bền vững theo cơ chế của cluster hay chưa. Đây là vấn đề khác với refresh.

Đặt refresh policy thành IMMEDIATE không biến nhiều update thành transaction. Nó chỉ ảnh hưởng thời điểm thay đổi có thể được search nhìn thấy.

### 4.2. Eventual consistency

Với denormalized projection, nhiều hệ thống chọn eventual consistency: sau khi dữ liệu gốc thay đổi, các bản sao được cập nhật bất đồng bộ và sẽ hội tụ về cùng trạng thái sau khi event được xử lý thành công.

Trong khoảng thời gian lan truyền, một query có thể thấy dữ liệu mới ở document gốc nhưng dữ liệu cũ ở một số projection. Ứng dụng cần quyết định mức trễ chấp nhận được và có cách phát hiện khi một projection không hội tụ.

Nếu nghiệp vụ yêu cầu đọc nhất quán tức thời, hãy đọc field chuẩn từ nguồn dữ liệu nghiệp vụ hoặc thiết kế một luồng đồng bộ có xác nhận phù hợp. Không thể giả định một bulk update sẽ làm toàn bộ index thay đổi nguyên tử.

## 5. Chọn API Spring Data Elasticsearch cho cập nhật dữ liệu lặp

Spring Data Elasticsearch cung cấp nhiều abstraction để cập nhật document:

| API | Mục đích | Dùng khi |
|---|---|---|
| Repository save / operations.save | Index toàn bộ entity | Có trạng thái đầy đủ của document |
| operations.update(UpdateQuery, index) | Partial update một document | Biết ID và chỉ thay một số field |
| operations.bulkUpdate(...) | Nhiều partial update trong một bulk request | Đã biết danh sách ID cần cập nhật |
| operations.updateByQuery(...) | Update các document khớp query | Nhiều document nhận cùng thay đổi |
| operations.deleteByQuery(...) | Xóa các document khớp query | Xóa projection theo quan hệ hoặc điều kiện |
| operations.bulkIndex(...) | Bulk index toàn bộ document | Tạo mới hoặc thay thế nhiều document |

Không dùng save(entity) chỉ để đổi một field nếu entity đang thiếu các field khác. Index operation có thể thay thế nội dung _source của document. Partial update phù hợp hơn khi chỉ muốn thay đổi sellerName hoặc categoryName mà giữ nguyên những field còn lại.

## 6. Cập nhật một document bằng UpdateQuery

Giả sử một seller đổi tên và cần cập nhật listing có ID listing-501:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

public class ListingProjectionWriter {

    private final ElasticsearchOperations operations;

    public ListingProjectionWriter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse updateSellerName(String listingId, String sellerName) {
        UpdateQuery update = UpdateQuery.builder(listingId)
                .withDocument(Document.from(Map.of(
                        "sellerName", sellerName)))
                .build();

        return operations.update(
                update,
                IndexCoordinates.of("listings"));
    }
}
~~~

Document chỉ chứa field sellerName nên Elasticsearch áp dụng partial update cho document đó. Các field title, sellerId và sellerRating được giữ nguyên.

Nếu giá trị có thể null, cần quyết định rõ ý nghĩa:

- Bỏ field khỏi partial document: không thay đổi field hiện tại.
- Gửi null: có thể đặt field thành null trong _source theo semantics của Update API.
- Xóa field: dùng script xóa field khỏi ctx._source hoặc API phù hợp.

Không dùng Map.of nếu value có thể null vì Map.of không chấp nhận null. Trong trường hợp đó, tạo map có thể chứa null hoặc biểu diễn thao tác xóa riêng.

### 6.1. Khi nào dùng save?

Nếu service có toàn bộ trạng thái listing mới và muốn thay thế document:

~~~java
Listing listing = loadCompleteListing(listingId);
listing.setSellerName(newSellerName);

operations.save(listing);
~~~

Chỉ làm vậy khi listing là trạng thái đầy đủ và ứng dụng có quyền sở hữu toàn bộ _source. Nếu document có field do pipeline hoặc service khác quản lý, save một entity thiếu field có thể làm mất dữ liệu đó.

### 6.2. Upsert không thay thế quy tắc nhất quán

UpdateQuery có thể cấu hình upsert để tạo document nếu chưa tồn tại:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withDocument(Document.from(Map.of(
                "sellerName", "North Star Retail")))
        .withDocAsUpsert(true)
        .build();
~~~

Upsert chỉ quyết định hành vi khi document chưa có. Nó không bảo đảm các field khác của document mới đầy đủ. Chỉ dùng khi partial document có thể tạo một document hợp lệ theo mapping và nghiệp vụ; nếu không, hãy index một projection đầy đủ.

## 7. Cập nhật nhiều document đã biết ID bằng bulkUpdate

Nếu consumer đã biết danh sách listing liên quan đến seller-7, có thể tạo nhiều UpdateQuery rồi gửi bulk:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.BulkOptions;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public void updateListings(
        ElasticsearchOperations operations,
        List<String> listingIds,
        String sellerName) {

    List<UpdateQuery> updates = listingIds.stream()
            .map(id -> UpdateQuery.builder(id)
                    .withDocument(Document.from(Map.of(
                            "sellerName", sellerName)))
                    .build())
            .toList();

    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("listings"));
}
~~~

Bulk giảm số lần round-trip so với gọi update riêng cho từng document. Tuy nhiên, vẫn phải xử lý lỗi item và chia batch phù hợp. Không tạo một list chứa hàng triệu UpdateQuery trong bộ nhớ rồi gửi một request duy nhất.

### 7.1. Chia batch

Ví dụ xử lý danh sách ID theo từng lô:

~~~java
int batchSize = 500;

for (int start = 0; start < listingIds.size(); start += batchSize) {
    int end = Math.min(start + batchSize, listingIds.size());
    List<String> batch = listingIds.subList(start, end);

    updateListings(operations, batch, newSellerName);
}
~~~

Batch size nên được chọn qua đo đạc, không phải một con số cố định cho mọi hệ thống. Kích thước document, số field update, tải cluster, mạng và concurrency đều ảnh hưởng hiệu năng.

### 7.2. Bulk failure là lỗi một phần

Spring Data có BulkFailureException để thông báo các document thất bại trong thao tác bulk. Với phiên bản cung cấp FailureDetails, có thể đọc ID, status và thông tin lỗi:

~~~java
import org.springframework.data.elasticsearch.BulkFailureException;

try {
    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("listings"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        log.warn(
                "Failed to update listing {}: status={}, message={}",
                id,
                failure.status(),
                failure.errorMessage());
    });

    throw exception;
}
~~~

Chữ ký và kiểu value của getFailedDocuments() thay đổi giữa các release train. Ví dụ trên phù hợp với API hiện hành có FailureDetails; kiểm tra Javadoc của đúng phiên bản Spring Data Elasticsearch mà dự án sử dụng.

Không chỉ log rồi bỏ qua lỗi. Cần lưu các item thất bại để retry hoặc đưa vào dead-letter queue (DLQ). Nếu consumer đánh dấu event đã xử lý dù một phần item thất bại, các bản sao có thể bị lệch vĩnh viễn.

## 8. Cập nhật theo điều kiện bằng Update By Query

Nếu tất cả document có sellerId = seller-7 đều cần thay đổi cùng sellerName, không nhất thiết phải lấy toàn bộ ID về ứng dụng. Elasticsearch Update By Query có thể tìm và cập nhật ngay trong cluster.

REST API:

~~~http
POST listings/_update_by_query
{
  "query": {
    "term": {
      "sellerId": "seller-7"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.sellerName = params.name",
    "params": {
      "name": "North Star Retail"
    }
  }
}
~~~

Spring Data Elasticsearch có thể biểu diễn bằng UpdateQuery builder với query và script:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

CriteriaQuery selection = new CriteriaQuery(
        Criteria.where("sellerId").is("seller-7"));

UpdateQuery updateByQuery = UpdateQuery.builder(selection)
        .withScript("ctx._source.sellerName = params.name")
        .withParams(Map.of("name", "North Star Retail"))
        .withBatchSize(500)
        .withAbortOnVersionConflict(false)
        .build();

ByQueryResponse response = operations.updateByQuery(
        updateByQuery,
        IndexCoordinates.of("listings"));
~~~

Update By Query phù hợp khi:

- Tập document có thể được xác định bằng query.
- Mọi document nhận cùng một thay đổi hoặc cùng script.
- Không cần ứng dụng tự đọc từng document về rồi gửi update riêng.

Không nên dùng Update By Query khi mỗi document cần một giá trị khác nhau mà script không thể xác định từ source hoặc params. Trong trường hợp đó, bulkUpdate với danh sách ID và partial document thường phù hợp hơn.

### 8.1. Xử lý version conflict

Trong lúc Update By Query chạy, một document có thể bị ứng dụng khác cập nhật. Elasticsearch phát hiện version conflict. Có thể chọn dừng hoặc tiếp tục:

- Abort: dừng khi có conflict; phù hợp khi mọi document cần được cập nhật trong một lần chạy có kiểm soát.
- Proceed: tiếp tục các document khác và ghi nhận số conflict; những document conflict vẫn cần xử lý riêng.

withAbortOnVersionConflict(false) tương ứng với hành vi tiếp tục trong API Spring Data hiện hành. Nó không giải quyết conflict và không bảo đảm mọi document đã được cập nhật.

### 8.2. Update By Query bất đồng bộ

Với tập document lớn, Elasticsearch REST API hỗ trợ wait_for_completion=false để trả task ID:

~~~http
POST listings/_update_by_query?wait_for_completion=false&requests_per_second=500
{
  "query": {
    "term": {
      "sellerId": "seller-7"
    }
  },
  "script": {
    "source": "ctx._source.sellerName = params.name",
    "params": {
      "name": "North Star Retail"
    }
  }
}
~~~

Theo dõi task:

~~~http
GET _tasks/TASK_ID
~~~

Có thể hủy task:

~~~http
POST _tasks/TASK_ID/_cancel
~~~

Hủy task không rollback những document đã cập nhật trước đó. Cần ghi lại tiến độ và thiết kế lần chạy tiếp theo sao cho có thể tiếp tục an toàn.

## 9. Vì sao cần event để lan truyền thay đổi?

Giả sử seller đổi tên từ North Star Store thành North Star Retail. Hệ thống phải tìm mọi listing có sellerId tương ứng và cập nhật sellerName.

Một luồng đồng bộ đơn giản:

1. Service cập nhật seller trong database nghiệp vụ.
2. Service phát event SellerRenamed.
3. Consumer nhận event.
4. Consumer tìm các listing phụ thuộc sellerId.
5. Consumer cập nhật listing theo batch.
6. Consumer xác nhận event đã xử lý khi mọi batch cần thiết hoàn tất.

Event có thể chứa:

~~~json
{
  "eventId": "evt-2026-000091",
  "eventType": "SellerRenamed",
  "aggregateType": "Seller",
  "aggregateId": "seller-7",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-13T10:30:00Z",
  "payload": {
    "sellerName": "North Star Retail"
  }
}
~~~

Các trường có ý nghĩa:

- eventId: định danh duy nhất để phát hiện event trùng.
- aggregateId: seller nào đã thay đổi.
- aggregateVersion: phiên bản tăng dần của seller.
- occurredAt: thời điểm phát sinh event, hữu ích cho log và điều tra.
- payload: dữ liệu cần để cập nhật projection.

Không nên chỉ dựa vào occurredAt để quyết định thứ tự vì đồng hồ giữa các máy có thể lệch. Một version tăng đơn điệu theo aggregate thường phù hợp hơn để phát hiện event cũ.

## 10. Transactional Outbox để không mất event

Một lỗi thường gặp là cập nhật database thành công rồi gửi message thất bại:

~~~text
UPDATE seller trong database: thành công
Publish SellerRenamed: thất bại
=> Database đã đổi nhưng Elasticsearch không nhận được event
~~~

Lỗi ngược lại cũng có thể xảy ra: message được gửi nhưng transaction database rollback. Consumer khi đó nhận một sự kiện mô tả thay đổi chưa được commit.

Transactional Outbox giải quyết khoảng trống này bằng cách ghi dữ liệu nghiệp vụ và event vào cùng một transaction database:

~~~text
BEGIN TRANSACTION
    UPDATE sellers SET name = ...
    INSERT INTO outbox(event_id, aggregate_id, version, payload, ...)
COMMIT
          |
          v
Outbox relay đọc event chưa gửi
          |
          v
Publish message
          |
          v
Consumer cập nhật Elasticsearch
~~~

Nếu transaction commit, cả thay đổi seller và bản ghi outbox cùng tồn tại. Relay có thể retry publish cho đến khi thành công. Consumer vẫn cần idempotency vì message broker thường cung cấp delivery ít nhất một lần hoặc có thể phát lại message.

Outbox không tự tạo transaction giữa database và Elasticsearch. Nó bảo đảm event về thay đổi đã commit được lưu bền vững cùng transaction nguồn, sau đó projection được cập nhật bất đồng bộ.

### 10.1. Cấu trúc outbox tối thiểu

Một bảng outbox có thể gồm:

| Cột | Ý nghĩa |
|---|---|
| event_id | Khóa duy nhất của event |
| aggregate_type | Loại aggregate, ví dụ Seller |
| aggregate_id | ID của aggregate |
| aggregate_version | Version tại thời điểm thay đổi |
| event_type | Tên sự kiện |
| payload | Nội dung event |
| created_at | Thời điểm tạo |
| published_at | Thời điểm relay publish thành công |

Relay cần đánh dấu trạng thái publish theo cách có thể retry. Nếu relay crash sau khi publish nhưng trước khi đánh dấu published, event có thể được gửi lại; vì vậy consumer phải chịu được duplicate.

## 11. Idempotency: xử lý event lặp an toàn

Message có thể được gửi lại do timeout, retry hoặc consumer crash. Một consumer idempotent có thể xử lý cùng một event nhiều lần mà không làm sai trạng thái cuối.

Với event SellerRenamed chứa trạng thái cuối cùng:

~~~json
{
  "sellerId": "seller-7",
  "sellerName": "North Star Retail",
  "version": 18
}
~~~

Thao tác gán sellerName thành North Star Retail có tính idempotent: chạy lại nhiều lần vẫn cho cùng giá trị.

Ngược lại, script tăng counter:

~~~text
ctx._source.orderCount += params.delta
~~~

không idempotent nếu cùng event được chạy hai lần. Counter sẽ tăng hai lần.

### 11.1. Dùng event ID để phát hiện trùng

Consumer có thể lưu eventId đã xử lý trong inbox table hoặc bảng deduplication. Tuy nhiên, việc ghi inbox và cập nhật Elasticsearch cũng không nằm trong cùng transaction. Nếu đánh dấu event đã xử lý trước khi Elasticsearch cập nhật, crash có thể làm mất thay đổi. Nếu đánh dấu sau khi cập nhật, crash ở giữa có thể dẫn đến chạy lại.

Do đó, deduplication ở consumer cần kết hợp với thao tác projection idempotent và cơ chế retry. Không nên coi một bảng processed_events đơn giản là đủ để bảo đảm transaction giữa broker và Elasticsearch.

### 11.2. Dùng trạng thái cuối thay cho delta khi có thể

Event dạng delta:

~~~json
{
  "sellerId": "seller-7",
  "ratingDelta": 0.1
}
~~~

Event dạng trạng thái cuối:

~~~json
{
  "sellerId": "seller-7",
  "rating": 4.8,
  "version": 18
}
~~~

Event trạng thái cuối thường dễ retry hơn vì consumer gán giá trị đã tính sẵn thay vì cộng/trừ nhiều lần. Với counter hoặc dữ liệu cần delta, phải có event ID, version hoặc một cơ chế deduplication chính xác.

## 12. Xử lý event đến sai thứ tự

Giả sử seller đổi tên liên tiếp:

~~~text
Version 18: North Star Retail
Version 19: North Star Marketplace
~~~

Do retry hoặc partitioning, consumer có thể nhận version 19 trước rồi mới nhận version 18. Nếu áp dụng cả hai theo thứ tự nhận, dữ liệu cuối cùng sẽ bị lùi về North Star Retail.

Giải pháp là lưu aggregateVersion trong projection và chỉ chấp nhận event mới hơn phiên bản hiện tại.

### 12.1. Lưu version trong document projection

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Marketplace",
  "sellerVersion": 19
}
~~~

Consumer phải bảo đảm version cũ không ghi đè version mới. Có thể thực hiện bằng optimistic concurrency, script có điều kiện hoặc external versioning.

### 12.2. External versioning

Elasticsearch Index API hỗ trợ version và version_type external. Ví dụ:

~~~http
PUT listings/_doc/listing-501?version=19&version_type=external
{
  "sellerId": "seller-7",
  "sellerName": "North Star Marketplace",
  "sellerVersion": 19
}
~~~

Elasticsearch chỉ chấp nhận ghi khi version gửi lên lớn hơn version hiện tại. Event version 18 đến sau sẽ bị từ chối do version conflict.

external_gte chấp nhận version bằng hoặc lớn hơn. Cách này có thể hữu ích với việc replay cùng snapshot version, nhưng chỉ an toàn nếu cùng một version luôn đại diện cho cùng một payload. Hai payload khác nhau cùng version có thể làm dữ liệu bị ghi đè không xác định.

External versioning áp dụng cho thao tác index theo contract của Elasticsearch. Với partial update, hãy chọn cách kiểm soát phù hợp như if_seq_no/if_primary_term hoặc script kiểm tra version trong _source; không giả định tham số external version hoạt động giống hệt trên mọi endpoint.

### 12.3. Kiểm tra version bằng Painless script

Với Update API, có thể so sánh version event với version trong document:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withScript("""
            if (ctx._source.sellerVersion == null ||
                params.version > ctx._source.sellerVersion) {
                ctx._source.sellerName = params.name;
                ctx._source.sellerVersion = params.version;
            } else {
                ctx.op = 'noop';
            }
            """)
        .withParams(Map.of(
                "name", "North Star Marketplace",
                "version", 19))
        .build();
~~~

Script chỉ áp dụng event nếu version mới hơn. Nếu version bằng hoặc thấp hơn, thao tác trở thành noop. Cần điều chỉnh kiểu số trong params và source theo schema thực tế.

Nếu nhiều consumer cùng cập nhật một document, vẫn phải xử lý version conflict và retry. Script kiểm tra version giúp ngăn event cũ ghi đè event mới, nhưng không biến nhiều document thành một transaction.

## 13. Optimistic concurrency cho các cập nhật đồng thời

Elasticsearch cung cấp sequence number và primary term để kiểm soát ghi đồng thời. Khi đọc document, response có _seq_no và _primary_term. Có thể yêu cầu update chỉ thành công nếu document vẫn ở phiên bản đã đọc.

Ví dụ REST:

~~~http
POST listings/_update/listing-501?if_seq_no=42&if_primary_term=3
{
  "doc": {
    "sellerName": "North Star Retail"
  }
}
~~~

Nếu một writer khác đã thay đổi document, Elasticsearch trả version conflict. Ứng dụng cần đọc lại trạng thái mới, kiểm tra version nghiệp vụ và quyết định áp dụng lại hay bỏ qua.

Spring Data Elasticsearch có thể biểu diễn điều kiện này trong UpdateQuery:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withDocument(Document.from(Map.of(
                "sellerName", "North Star Retail")))
        .withIfSeqNo(42L)
        .withIfPrimaryTerm(3L)
        .build();
~~~

### 13.1. Phân biệt retry_on_conflict và optimistic concurrency

- if_seq_no + if_primary_term: chỉ ghi nếu document chưa thay đổi kể từ lần đọc cụ thể. Nếu conflict, ứng dụng tự quyết định đọc lại và thử lại.
- retry_on_conflict: yêu cầu Elasticsearch thử lại Update API khi có version conflict, bằng cách đọc phiên bản mới và áp dụng lại update/script.

Retry chỉ an toàn khi phép cập nhật có thể chạy lại. Gán sellerName bằng giá trị cuối thường có thể retry; tăng counter hoặc cộng tiền cần thiết kế idempotency riêng.

## 14. Xử lý bulk thất bại một phần

Một batch có thể có nhiều kết quả:

| Loại lỗi | Hướng xử lý |
|---|---|
| HTTP 429 / rejected execution | Retry có backoff và giới hạn tốc độ |
| Timeout hoặc lỗi mạng | Xác định trạng thái không rõ; replay action idempotent hoặc kiểm tra lại document |
| Version conflict | Đọc version hiện tại, bỏ event cũ hoặc thử lại theo chính sách |
| Mapping/parsing error | Đưa vào DLQ, sửa schema/dữ liệu rồi replay |
| Authentication/authorization | Sửa quyền/credential; tránh retry liên tục |
| Document missing khi update | Kiểm tra vòng đời document; dùng upsert chỉ khi đúng nghiệp vụ |

Không retry toàn bộ bulk vô điều kiện. Một số action đã thành công; gửi lại action không idempotent có thể áp dụng thay đổi lần thứ hai.

### 14.1. Retry có backoff

Với lỗi tạm thời, có thể retry theo exponential backoff và jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + randomJitter
~~~

Ví dụ:

| Lần thử | Delay cơ sở minh họa |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |

Đây là ví dụ cấu hình, không phải giá trị tối ưu cố định. Đặt số lần thử tối đa, giới hạn tổng thời gian retry và đưa item thất bại sang DLQ khi vượt ngưỡng.

### 14.2. Dead-letter queue

DLQ lưu event hoặc item không thể xử lý sau các lần retry. Mỗi record nên có:

- event ID và aggregate ID.
- document ID/index đích.
- payload hoặc tham chiếu tới payload gốc.
- số lần retry và thời điểm thử gần nhất.
- loại lỗi, status và message.
- phiên bản projection mong muốn.

DLQ cần có quy trình quan sát và replay. Nếu chỉ lưu log, việc phục hồi hàng triệu item lỗi sau một sự cố sẽ rất khó.

## 15. Xử lý thay đổi quan hệ và xóa dữ liệu

Đồng bộ không chỉ là cập nhật tên hoặc trạng thái. Quan hệ có thể bị thêm, chuyển hoặc xóa.

### 15.1. Khi một listing chuyển sang seller khác

Nếu listing-501 đổi sellerId từ seller-7 sang seller-9, cần cập nhật cả sellerId và các bản sao sellerName/sellerRating trong cùng document listing. Không nên cập nhật sellerName trước rồi sellerId sau bằng hai request độc lập nếu có thể tạo trạng thái lai.

Vì cả hai field nằm trong cùng document, dùng một partial update:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withDocument(Document.from(Map.of(
                "sellerId", "seller-9",
                "sellerName", "East Point Store",
                "sellerRating", 4.6)))
        .build();

operations.update(update, IndexCoordinates.of("listings"));
~~~

Một update trên cùng document giúp các field trong document được thay đổi như một đơn vị. Nhưng nếu listing còn được copy sang nhiều index khác, việc cập nhật các index đó vẫn là nhiều thao tác độc lập.

### 15.2. Khi seller bị xóa hoặc ngừng hoạt động

Hệ thống cần quyết định:

- Xóa listing liên quan.
- Đánh dấu listing inactive.
- Giữ listing nhưng bỏ thông tin seller.
- Giữ snapshot sellerName để phục vụ lịch sử.

Không tự động xóa mọi document có sellerId chỉ vì seller bị xóa trong nguồn. Quy tắc phụ thuộc nghiệp vụ, lịch sử và yêu cầu audit.

### 15.3. Delete By Query

Nếu chính sách yêu cầu xóa tất cả listing của seller:

~~~http
POST listings/_delete_by_query
{
  "query": {
    "term": {
      "sellerId": "seller-7"
    }
  }
}
~~~

Delete By Query cũng xử lý theo batch và có thể gặp version conflict. Nó không phải thao tác transaction trên toàn bộ tập document. Với thao tác quan trọng, cần lưu số lượng dự kiến, kết quả thực tế, failures và khả năng tiếp tục.

## 16. Đồng bộ nhiều index bằng projection writer

Một event có thể cần cập nhật nhiều projection:

~~~text
SellerRenamed(seller-7, version=18)
        |
        +----> sellers index
        |
        +----> listings index
        |
        +----> recommendations index
        |
        +----> analytics projection
~~~

Nên đóng gói logic cập nhật mỗi projection thành một writer riêng. Mỗi writer có thể dùng bulkUpdate hoặc updateByQuery theo cấu trúc dữ liệu và số lượng document.

Ví dụ interface:

~~~java
public interface ProjectionUpdater<E> {
    void apply(E event);
}
~~~

Consumer điều phối:

~~~java
public class SellerRenamedHandler {

    private final SellerIndexUpdater sellerUpdater;
    private final ListingIndexUpdater listingUpdater;
    private final RecommendationIndexUpdater recommendationUpdater;

    public void handle(SellerRenamed event) {
        sellerUpdater.apply(event);
        listingUpdater.apply(event);
        recommendationUpdater.apply(event);
    }
}
~~~

Ví dụ này thể hiện cách phân chia trách nhiệm. Trong triển khai thật, cần lưu tiến độ theo từng projection hoặc dùng retry độc lập. Nếu listing updater thành công nhưng recommendation updater lỗi, không được giả định cả handler đã hoàn tất hoặc có thể rollback listing index.

### 16.1. Theo dõi tiến độ theo projection

Có thể lưu trạng thái event theo từng consumer/projection:

| Event | Projection | Trạng thái |
|---|---|---|
| evt-91 | sellers | DONE |
| evt-91 | listings | RETRY |
| evt-91 | recommendations | DONE |

Khi retry, chỉ chạy projection còn thiếu hoặc chạy lại tất cả theo cách idempotent. Lựa chọn phụ thuộc chi phí và mức độ idempotent của từng updater.

## 17. CDC và rebuild projection

Ngoài outbox do ứng dụng tự ghi, hệ thống có thể dùng Change Data Capture (CDC) để đọc thay đổi từ transaction log của database rồi phát event. CDC giảm việc phải thêm publish logic vào mọi service, nhưng vẫn cần:

- Mapping thay đổi database thành event nghiệp vụ hoặc projection update.
- Bảo đảm thứ tự theo key/aggregate khi cần.
- Lưu offset và xử lý replay.
- Xử lý schema evolution.
- Chống event trùng và event cũ.

Nếu projection Elasticsearch sai hoặc cần thay đổi schema, một chiến lược mạnh là rebuild từ nguồn chuẩn:

1. Tạo index/projection mới với mapping mong muốn.
2. Đọc dữ liệu chuẩn hoặc snapshot nhất quán.
3. Index lại dữ liệu theo batch.
4. Phát lại event phát sinh trong lúc rebuild.
5. Kiểm tra số lượng và các invariant nghiệp vụ.
6. Chuyển alias sang projection mới.
7. Giữ index cũ trong thời gian rollback.

Rebuild thường đáng tin cậy hơn việc cố sửa thủ công mọi document bị lệch nếu nguồn chuẩn còn đầy đủ.

## 18. Đối soát dữ liệu lặp

Event-driven update có thể thất bại do lỗi mapping, DLQ bị bỏ quên, consumer bug hoặc sự cố vận hành. Vì vậy, hệ thống quan trọng nên có reconciliation job.

Một quy trình đối soát có thể:

1. Lấy danh sách seller có version mới hơn projection.
2. Tìm các listing có sellerId tương ứng.
3. So sánh sellerVersion và sellerName.
4. Ghi nhận document lệch.
5. Sửa bằng bulk update hoặc phát lại event trạng thái cuối.
6. Ghi metrics về số document đã kiểm tra, lệch và sửa được.

Ví dụ kiểm tra projection:

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Store",
  "sellerVersion": 17
}
~~~

Trong khi nguồn chuẩn đang ở version 18. Đây là dấu hiệu projection chưa hội tụ.

### 18.1. Chọn invariant để đối soát

Không chỉ so sánh số lượng document. Có thể kiểm tra:

- Mọi listing active tham chiếu seller đang tồn tại.
- sellerVersion trong listing không nhỏ hơn version tối thiểu cho phép.
- sellerName trong projection bằng tên canonical tại version tương ứng.
- Không còn document trỏ tới seller đã bị xóa theo chính sách.
- Counter tổng hợp khớp với phép tính lại từ dữ liệu nguồn.

Với tập dữ liệu lớn, dùng sampling, partition theo thời gian hoặc đối soát theo aggregate ID để giới hạn tải. Job đối soát không nên tạo tải đột biến lên cluster đang phục vụ search.

## 19. Refresh và read-after-write

Sau khi cập nhật document, ứng dụng có thể đọc trực tiếp theo ID hoặc tìm kiếm bằng query. Hai cách có hành vi visibility khác nhau:

- Get theo ID có thể đọc trạng thái document đã ghi mà không cần chờ search refresh theo cùng cách.
- Search chỉ nhìn thấy thay đổi sau khi shard được refresh.

Spring Data có RefreshPolicy với các lựa chọn như NONE, IMMEDIATE và WAIT_UNTIL. Với bulk hoặc fan-out update lớn, tránh refresh ngay sau từng document vì refresh thường xuyên làm giảm hiệu năng indexing.

Nếu UI cần xác nhận cập nhật đã xuất hiện trong search, có thể dùng WAIT_UNTIL cho một số thao tác phù hợp hoặc chủ động refresh sau một batch. Điều này chỉ bảo đảm visibility của thao tác liên quan sau refresh; không bảo đảm mọi projection ở các index khác đã được cập nhật.

## 20. Thiết kế event version và projection document

Một projection document nên lưu đủ metadata để nhận biết trạng thái đồng bộ:

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Marketplace",
  "sellerVersion": 19,
  "projectionUpdatedAt": "2026-11-13T10:31:00Z"
}
~~~

Trong đó:

- sellerVersion giúp bỏ qua event cũ.
- projectionUpdatedAt hỗ trợ quan sát độ trễ và điều tra.
- sellerId cho phép tìm ngược các document phụ thuộc.

Không nên chỉ dùng timestamp để phân xử thứ tự nếu có thể dùng version tăng dần. Timestamp có thể trùng hoặc đến sai thứ tự do clock skew.

Một event version nên được tăng tại source of truth trong transaction của aggregate. Nếu nhiều service có thể phát version cho cùng aggregate, cần một cơ chế cấp version duy nhất hoặc phân vùng xử lý theo aggregate.

## 21. Lựa chọn giữa bulkUpdate và updateByQuery

Hai API đều có thể cập nhật nhiều document nhưng cách sử dụng khác nhau:

| Tiêu chí | bulkUpdate | updateByQuery |
|---|---|---|
| Định danh document | Ứng dụng cung cấp ID cho từng update | Elasticsearch tìm theo query |
| Giá trị update | Có thể khác nhau cho từng document | Thường cùng script/params, có thể dựa trên source |
| Payload | Danh sách UpdateQuery | Query + script/partial document |
| Phù hợp | Event có danh sách ID và dữ liệu riêng | Tất cả document thỏa điều kiện nhận cùng thay đổi |
| Lỗi | Lỗi theo từng bulk item | Version conflict/failures theo batch |
| Kiểm soát batch | Ứng dụng chia danh sách | Elasticsearch xử lý theo batch/scroll |

Ví dụ:

- Đổi sellerName cho mọi listing của seller-7: updateByQuery phù hợp.
- Cập nhật mỗi listing một giá khác nhau theo event riêng: bulkUpdate phù hợp.
- Chỉ đổi một listing: update.

Nếu quan hệ có hàng triệu document, updateByQuery có thể giảm lượng dữ liệu phải kéo về ứng dụng. Tuy nhiên, cần theo dõi task, throttle, conflict và thời gian xử lý.

## 22. Các lỗi thường gặp

### Dùng save để cập nhật một field

Entity thiếu các field khác có thể làm mất dữ liệu khi index lại toàn bộ _source. Dùng partial update nếu chỉ thay một số field.

### Nghĩ bulk là transaction

Bulk request có thể thành công một phần. Kiểm tra từng item, lưu failures và retry có chọn lọc.

### Đánh dấu event hoàn tất khi projection còn lỗi

Nếu consumer ack event sau khi một số item thất bại, dữ liệu sẽ lệch mà không còn cơ chế tự retry. Chỉ ack khi mọi projection bắt buộc đã hoàn tất hoặc đã chuyển lỗi sang luồng phục hồi có theo dõi.

### Retry một script không idempotent

Script cộng dồn có thể chạy hai lần khi request timeout hoặc message bị gửi lại. Dùng event ID/version hoặc thiết kế thao tác gán trạng thái cuối.

### Event cũ ghi đè event mới

Chỉ dựa vào thứ tự nhận message là không đủ. Lưu aggregate version và bỏ qua event cũ.

### Chỉ lưu processed event trước khi update Elasticsearch

Consumer crash sau khi đánh dấu processed nhưng trước khi cập nhật index sẽ làm mất projection update. Kết hợp deduplication với idempotent update, retry và reconciliation.

### Coi refresh là đồng bộ nhất quán

Refresh chỉ làm dữ liệu nhìn thấy trong search. Nó không đồng bộ các index khác và không tạo transaction.

### Cập nhật snapshot lịch sử

Không lan truyền thay đổi catalog vào đơn hàng/hóa đơn nếu field đó phải phản ánh trạng thái tại thời điểm giao dịch.

### Xóa document liên quan mà không có quy tắc nghiệp vụ

Xóa seller không đồng nghĩa luôn phải xóa mọi order hoặc listing. Xác định lifecycle, soft delete, snapshot và retention trước khi triển khai.

### Không có cơ chế rebuild

Nếu chỉ có event incremental mà không thể đọc lại nguồn chuẩn, một projection bị sai có thể rất khó phục hồi. Thiết kế khả năng rebuild ngay từ đầu.

## 23. Quy trình triển khai cập nhật dữ liệu lặp

Khi một field canonical thay đổi và cần lan truyền tới các document khác:

1. Xác định nguồn dữ liệu chuẩn và owner của field.
2. Phân loại bản sao là snapshot lịch sử hay projection hiện hành.
3. Xác định toàn bộ index/document phụ thuộc và cách tìm ngược theo ID.
4. Thiết kế event chứa eventId, aggregateId, aggregateVersion và trạng thái cần áp dụng.
5. Ghi event bằng transactional outbox hoặc CDC để tránh mất thay đổi.
6. Chọn update, bulkUpdate hoặc updateByQuery theo số lượng document và cách xác định giá trị.
7. Dùng partial update để giữ nguyên field không liên quan.
8. Thiết kế idempotency và xử lý event sai thứ tự.
9. Xử lý version conflict, bulk failures, retry/backoff và DLQ.
10. Theo dõi tiến độ riêng cho từng projection/index.
11. Chạy reconciliation để phát hiện document bị bỏ lỡ hoặc stale.
12. Có khả năng rebuild projection từ nguồn chuẩn.
13. Chỉ yêu cầu refresh khi cần search visibility; không coi refresh là transaction.
14. Kiểm thử duplicate, out-of-order, timeout, partial failure và consumer restart.

## 24. Kiểm thử các tình huống nhất quán

Một bộ integration test cho projection updater nên kiểm tra:

| Tình huống | Kết quả mong muốn |
|---|---|
| Event version 18 đến lần đầu | Projection chuyển sang version 18 |
| Event version 18 được gửi lại | Không tạo thay đổi sai hoặc tăng counter lần hai |
| Version 19 đến trước version 18 | Projection giữ version 19 |
| Bulk có một item mapping error | Các item thành công được ghi nhận; item lỗi có thể retry/DLQ |
| Consumer crash sau khi cập nhật một batch | Replay không làm sai trạng thái |
| Seller đổi tên hai lần nhanh | Listing không bị lùi về tên cũ |
| Listing chuyển seller | sellerId và các field copy được đổi cùng một update trên document |
| Snapshot đơn hàng | Giá/tên lịch sử không bị cập nhật ngoài ý muốn |
| Projection rebuild | Dữ liệu sau rebuild khớp source of truth và event catch-up |

### 24.1. Kiểm thử idempotent update

Với một event gán trạng thái cuối, có thể chạy cùng event hai lần và xác nhận document không đổi sau lần thứ hai:

~~~java
@Test
void applyingSameSellerRenameTwiceKeepsSameProjection() {
    handler.handle(event);
    Listing first = operations.get(
            "listing-501",
            Listing.class,
            IndexCoordinates.of("listings"));

    handler.handle(event);
    Listing second = operations.get(
            "listing-501",
            Listing.class,
            IndexCoordinates.of("listings"));

    assertThat(second.getSellerName()).isEqualTo(first.getSellerName());
    assertThat(second.getSellerVersion()).isEqualTo(first.getSellerVersion());
}
~~~

Test này cần setup mapping, event và document phù hợp với ứng dụng. Với event delta, phải kiểm tra thêm event ID/version để chứng minh việc replay không cộng/trừ hai lần.

## 25. Tổng kết

Denormalization giúp Elasticsearch phục vụ truy vấn nhanh bằng cách sao chép field cần đọc vào nhiều document. Khi dữ liệu canonical thay đổi, các bản sao hiện hành cần được cập nhật bằng fan-out update; snapshot lịch sử thường phải được giữ nguyên theo thời điểm phát sinh nghiệp vụ. Cần phân biệt nested object, parent-child và các document denormalized vì cách cập nhật và chi phí truy vấn khác nhau.

Spring Data Elasticsearch cung cấp update cho một document, bulkUpdate cho nhiều ID đã biết và updateByQuery cho tập document được xác định bằng query. Bulk và update-by-query không phải transaction nhiều document; lỗi có thể xảy ra một phần. Hệ thống nên dùng source of truth, transactional outbox hoặc CDC, event ID/version, thao tác idempotent, kiểm soát concurrency, retry có backoff, DLQ và reconciliation.

Một thiết kế nhất quán không giả định mọi bản sao thay đổi cùng một thời điểm. Nó xác định độ trễ chấp nhận được, biết projection nào đã cập nhật, có thể phát lại event và có thể rebuild từ nguồn chuẩn. Nhờ vậy, dữ liệu lặp vẫn mang lại lợi ích đọc nhanh mà hệ thống có khả năng phục hồi khi update thất bại, event trùng hoặc đến sai thứ tự.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Parent-join field](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join)
- [Martin Fowler – Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
